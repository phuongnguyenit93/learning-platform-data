# Querydsl và QuerydslPredicateExecutor trong phiên bản hỗ trợ

## 1. Bài toán: truy vấn động nhưng vẫn muốn kiểm tra kiểu ở Java

Trong chương **Repository mở rộng** của **Spring Data MongoDB**, repository thường bắt đầu bằng các phương thức đơn giản:

~~~java
List<CatalogProduct> findByStatus(String status);
List<CatalogProduct> findByTenantIdAndStatus(
        String tenantId, String status);
~~~

Khi màn hình danh mục có nhiều bộ lọc tùy chọn — tenant, trạng thái, giá tối thiểu, số lượng tồn kho, ngày tạo — số lượng phương thức suy diễn có thể tăng nhanh. Một phương án là `MongoTemplate` kết hợp `Query`/`Criteria`. **Querydsl** là phương án khác, cho phép mô tả điều kiện bằng các **đường dẫn có kiểu Java** được tạo từ model, thay vì chuỗi tên property ở khắp mã nguồn.

Ví dụ ý nghĩa truy vấn:

~~~text
tenantId = "tenant-a"
AND status = "ACTIVE"
AND stock >= 5
~~~

Nếu có lớp `QCatalogProduct` do Querydsl sinh ra, code có thể diễn đạt bằng:

~~~java
QCatalogProduct product = QCatalogProduct.catalogProduct;

Predicate predicate = product.tenantId.eq("tenant-a")
        .and(product.status.eq("ACTIVE"))
        .and(product.stock.goe(5));
~~~

`Predicate` đến từ `com.querydsl.core.types.Predicate`. Kiểu `QCatalogProduct` không phải entity MongoDB khác: đó là **lớp siêu mô hình truy vấn** chứa các property path như `StringPath` và `NumberPath`.

Spring Data Commons có interface `QuerydslPredicateExecutor<T>` để repository có thể thực thi predicate Querydsl trong các **module và phiên bản cung cấp adapter tương ứng**. Riêng Spring Data MongoDB, cần kiểm tra hỗ trợ của phiên bản thư viện thực tế, các dependency Querydsl và mã truy vấn mà adapter có thể chuyển sang MongoDB.

**Chủ đề của bài được giới hạn có chủ đích:** Querydsl không phải một lời hứa rằng mọi phiên bản Spring Data MongoDB, Querydsl và driver MongoDB đều tương thích. Bài giải thích cách dùng **khi phiên bản hỗ trợ**, cách tự xác minh, giới hạn thường gặp và cách chuyển sang `MongoTemplate` khi không còn adapter phù hợp.

> Ngữ cảnh ví dụ: Java 17+, Spring Boot 3.x và các bản Spring Data MongoDB có hỗ trợ Querydsl repository. Không lấy một ví dụ Querydsl JPA làm bằng chứng MongoDB hỗ trợ cùng một operator; các query translation và thế hệ thư viện có thể khác nhau. Mọi cấu hình dependency cần khóa phiên bản tương thích trong dự án và kiểm tra bằng build/integration test.

## 2. Querydsl, Q-type, Predicate và executor khác nhau thế nào?

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Entity MongoDB** | Khai báo dữ liệu và ánh xạ Java ↔ BSON | `CatalogProduct`, `@Document`, `@Field` |
| **Q-type** | Biểu diễn property path có kiểu do annotation processor tạo | `QCatalogProduct` |
| **Predicate** | Biểu thức điều kiện có thể kết hợp `and/or/not` | `product.stock.goe(5)` |
| **BooleanBuilder** | Xây dựng predicate khi đầu vào có nhiều filter tùy chọn | `new BooleanBuilder().and(...)` |
| **QuerydslPredicateExecutor** | Interface repository định nghĩa tìm/đếm/tồn tại theo Querydsl Predicate | `findAll(predicate)`, `count(predicate)` |
| **Adapter Querydsl của Spring Data MongoDB** | Chuyển predicate sang thao tác MongoDB, nếu được phiên bản hỗ trợ | Đường triển khai repository |
| **MongoTemplate/Criteria** | API Spring Data MongoDB trực tiếp, không cần Q-type | `Criteria.where("stock").gte(5)` |

Luồng thực thi khái niệm:

~~~mermaid
flowchart TD
    A["Entity Java có @QueryEntity"] --> B["Querydsl annotation processor"]
    B --> C["QCatalogProduct được sinh khi build"]
    C --> D["Predicate / BooleanBuilder"]
    D --> E["QuerydslPredicateExecutor repository"]
    E --> F["Adapter Querydsl MongoDB nếu được hỗ trợ"]
    F --> G["BSON filter / sort / pagination"]
    G --> H["MongoDB server"]
    H --> I["Entity / Page / count / exists"]
~~~

Q-type giúp trình biên dịch biết `stock` là số và `status` là chuỗi. Nó **không tự** bảo đảm kết quả đúng nghiệp vụ, có index tốt, hoặc mọi toán tử Querydsl đều dịch được sang ngôn ngữ truy vấn MongoDB.

### 2.1. Tính an toàn kiểu và giới hạn

Với Querydsl, những lỗi như gọi phép so sánh số trên một property chuỗi có thể được phát hiện sớm qua kiểu path. Nếu đổi tên property `stock` trong entity và tái sinh Q-type, code cũ dùng `product.stock` có thể không biên dịch.

Tuy nhiên:

- Một biểu thức Java hợp lệ vẫn có thể **không được MongoDB adapter hỗ trợ**.
- Null/missing field, mảng nhúng và regex có semantics đặc thù MongoDB.
- Querydsl không tự tạo index, transaction hoặc cơ chế tenant isolation.
- Q-type chỉ phản ánh metadata lúc được sinh; nếu bản sinh cũ hoặc metadata mapping không đầy đủ, cần kiểm tra lại.

Vì vậy **type-safe** không đồng nghĩa **database-semantics-safe**.

## 3. Điều kiện tiên quyết: xác nhận đúng phiên bản hỗ trợ

Trước khi triển khai, hãy trả lời các câu hỏi sau trên **dự án thật**:

1. Bản **Spring Data MongoDB** đang dùng có implementation repository cho `QuerydslPredicateExecutor<CatalogProduct>` hay không? Đừng chỉ kiểm tra interface có mặt trong Spring Data Commons.
2. Artifact Querydsl nào phù hợp với thế hệ Spring Data đó? `querydsl-core`, `querydsl-apt` và, nếu adapter cần, `querydsl-mongodb` phải có phiên bản tương thích.
3. Java đang dùng namespace `javax` hay `jakarta`? Với annotation processor phụ thuộc JPA annotations cần chọn classifier/APT configuration đúng; một dự án chỉ dùng `@QueryEntity` có thể cấu hình khác dự án JPA.
4. Có xung đột transitives với MongoDB Java Driver hoặc dependencies khác không? Querydsl-MongoDB của một số thế hệ thư viện có thể kéo theo driver cũ.
5. Build thực sự tạo `QCatalogProduct` hay chưa, và repository khởi tạo được khi chạy ứng dụng/test?
6. Các phép so sánh, sắp xếp, nested fields, arrays đang dùng có sinh BSON đúng không?

Không nên suy luận đơn giản:

~~~text
"Có dependency spring-data-commons"
     => "MongoDB chắc chắn có Querydsl adapter"
~~~

Mỗi module Spring Data chọn phạm vi tích hợp riêng. Một số ví dụ trên mạng dùng **Querydsl JPA** hoặc SQL; chúng không bảo đảm áp dụng nguyên dạng cho MongoDB.

### 3.1. Phạm vi hỗ trợ phải được kiểm tra theo release

| Môi trường | Cách tiếp cận |
|---|---|
Spring Data MongoDB phiên bản có adapter Querydsl tương thích | Có thể dùng `QuerydslPredicateExecutor` sau khi cấu hình Q-type và xác minh |
Spring Data MongoDB phiên bản mới/khác nhánh chưa xác minh | **Không giả định hỗ trợ**; kiểm tra tài liệu release/API và integration test |
Querydsl JPA cấu hình theo tutorial khác | Không tự mang sang MongoDB; kiểm tra artifact và serializer |
Không muốn phụ thuộc annotation processor/adapter | Dùng `MongoTemplate` + `Criteria` hoặc custom repository |
Truy vấn cần aggregation, array-specialized hoặc update có điều kiện | Dùng API MongoDB phù hợp thay vì cố diễn đạt mọi thứ qua Predicate |

Sự khác biệt **phiên bản hỗ trợ** là một phần của quyết định kiến trúc: nếu adapter bị thay đổi hoặc không còn khả dụng trong nhánh nâng cấp, cần có phương án thay thế, không nên xây toàn bộ business logic phụ thuộc trực tiếp vào Q-type.

## 4. Entity MongoDB và dữ liệu mẫu

Ví dụ dùng collection `catalog_products` với ba trường có thể lọc thường xuyên: tenant, trạng thái và tồn kho. Chúng ta cố tình đặt tên BSON khác tên property Java để thấy rõ ranh giới Querydsl → Spring Data mapping.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import com.querydsl.core.annotations.QueryEntity;
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@QueryEntity
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
    private Instant createdAt;
    private List<String> tags;

    protected CatalogProduct() {
        // Cho MongoDB converter.
    }

    public CatalogProduct(
            String id, String tenantId, String sku,
            String name, long stock, String status,
            Instant createdAt, List<String> tags) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.stock = stock;
        this.status = status;
        this.createdAt = createdAt;
        this.tags = tags;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public long getStock() { return stock; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public List<String> getTags() { return tags; }
}
~~~

`@QueryEntity` là annotation của **Querydsl** dùng cho việc sinh query type. `@Document`, `@MongoId` và `@Field` là metadata của Spring Data MongoDB. Hai lớp annotation phục vụ **hai giai đoạn khác nhau**:

~~~text
@QueryEntity  -> processor tạo QCatalogProduct tại compile-time
@Document     -> Spring Data biết collection/mapping runtime
@Field        -> Spring Data biết tên field BSON vật lý
~~~

Ví dụ BSON lưu trữ:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Bình nước 500 ml",
  "stock_qty": 12,
  "status": "ACTIVE",
  "createdAt": { "$date": "2026-11-20T08:00:00Z" },
  "tags": ["outdoor", "premium"]
}
~~~

Field `id` được ánh xạ thành `_id`. Đối với `String` ID, `@MongoId(FieldType.STRING)` giúp tránh việc chuỗi có dạng 24 ký tự hex bị chuyển thành BSON ObjectId ngoài ý muốn.

## 5. Sinh QCatalogProduct bằng annotation processing

`QCatalogProduct` không được người phát triển viết tay. Trong một build hỗ trợ Querydsl APT, annotation processor đọc `@QueryEntity` và tạo lớp Q tương ứng vào thư mục generated sources. Ví dụ cấu trúc (mang tính minh họa):

~~~text
src/main/java/com/example/catalog/CatalogProduct.java
build/generated/sources/annotationProcessor/java/main/
    com/example/catalog/QCatalogProduct.java
~~~

Tên đường dẫn generated sources thực tế phụ thuộc Gradle/Maven, IDE và cách cấu hình annotation processing. Không sửa trực tiếp tệp Q sinh ra; hãy chỉnh entity rồi build lại.

### 5.1. Các dependency cần được ghép tương thích

Trong dự án Gradle Groovy DSL, các thành phần cấu hình có thể có dạng:

~~~groovy
// Chọn querydslVersion tương thích với bản Spring Data MongoDB
// và MongoDB Java Driver của ứng dụng; không lấy số này làm
// khuyến nghị chung cho mọi dự án.
def querydslVersion = "5.1.0"

dependencies {
    implementation "com.querydsl:querydsl-core:$querydslVersion"
    annotationProcessor "com.querydsl:querydsl-apt:$querydslVersion"
    annotationProcessor "com.querydsl:querydsl-core:$querydslVersion"

    // Chỉ thêm khi adapter MongoDB của phiên bản yêu cầu/cho phép:
    // implementation "com.querydsl:querydsl-mongodb:$querydslVersion"
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
            "-processor", "com.querydsl.apt.QuerydslAnnotationProcessor"
    ]
}
~~~

**Đây là ví dụ cấu hình APT cho `@QueryEntity`, không phải một BOM chính thức.** Hệ thống build thực tế có thể đã quản lý processor chung với MapStruct/Lombok hoặc sử dụng Maven. Đừng ghi đè danh sách processors đang có một cách vô thức. Khi Spring Data và Querydsl khác thế hệ, một ví dụ với Querydsl 5.1.0 có thể **không** là tổ hợp phù hợp; phải áp dụng dependency matrix của phiên bản được chọn.

Với các dự án dùng `jakarta.persistence.*` trong model JPA, classifier `jakarta` của Querydsl APT có thể liên quan; **không** thêm classifier chỉ vì Spring Boot 3 sử dụng Jakarta nếu entity MongoDB chỉ có `@QueryEntity`. Cấu hình đúng phụ thuộc annotation processor được gọi và những annotation mà processor thực sự phải xử lý.

### 5.2. Ba bước xác minh APT

1. Xác nhận `@QueryEntity` có thể được biên dịch và processor chạy.
2. Tìm tệp `QCatalogProduct` trong generated sources và kiểm tra package `com.example.catalog`.
3. Viết một biểu thức tối giản dùng `QCatalogProduct.catalogProduct.status.eq("ACTIVE")`, biên dịch và chạy repository integration test.

Nếu IDE không thấy Q-type mà build CLI sinh ra đúng, kiểm tra IDE có bật annotation processing và có thêm generated sources vào classpath hay không. Nếu không sinh Q-type cả trong CLI, hãy kiểm tra dependency scope, processor class, namespace và log annotation processing.

Không copy Q-type từ một project có schema khác sang repository để “chữa cháy”: property đã thay đổi có thể khiến truy vấn sai hoặc classpath chứa bản Q cũ.

## 6. Khai báo repository có QuerydslPredicateExecutor

Khi phiên bản **Spring Data MongoDB** hỗ trợ Querydsl adapter và dependencies tương thích, repository có thể mở rộng đồng thời hai interface:

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String>,
                QuerydslPredicateExecutor<CatalogProduct> {
}
~~~

`MongoRepository` cung cấp CRUD thông thường; `QuerydslPredicateExecutor` thêm khả năng thực thi các Querydsl `Predicate`. Spring Data tạo implementation qua repository factory theo module, miễn rằng **adapter và Querydsl classes thực sự khả dụng**.

Những phương thức cốt lõi thường có:

| Phương thức | Ý nghĩa | Kiểu trả về |
|---|---|---|
`findOne(Predicate)` | Tìm một kết quả cho predicate | `Optional<T>` |
`findAll(Predicate)` | Tìm mọi kết quả phù hợp | `Iterable<T>` |
`findAll(Predicate, Sort)` | Tìm và sắp xếp | `Iterable<T>` |
`findAll(Predicate, Pageable)` | Tìm theo trang | `Page<T>` |
`count(Predicate)` | Đếm document phù hợp | `long` |
`exists(Predicate)` | Kiểm tra có ít nhất một document khớp | `boolean` |
`findAll(Predicate, OrderSpecifier<?>...)` | Sắp xếp với Querydsl order expressions | `Iterable<T>` nếu adapter hỗ trợ |

Các bản Spring Data Commons mới có thể có thêm biến thể như fluent `findBy`; **không tự coi mọi method của interface ở một release là khả dụng và được adapter MongoDB triển khai y hệt trên mọi release**.

### 6.1. Đừng hiểu findOne là lấy bản ghi đầu tiên tùy ý

`findOne(predicate)` diễn đạt kỳ vọng tìm **một kết quả**. Nếu nhiều document cùng khớp, contract có thể báo lỗi do số lượng không duy nhất thay vì chọn ngẫu nhiên một document. Khi predicate không unique, hãy dùng `findAll` với pagination/sort phù hợp.

Nếu nghiệp vụ yêu cầu chỉ tối đa một sản phẩm có (`tenantId`, `sku`), **unique index** của MongoDB mới bảo vệ bất biến đó, không phải `findOne` hay `Optional<T>`.

### 6.2. Executor chủ yếu là API đọc

`QuerydslPredicateExecutor` không phải một DSL chung để gọi `updateMany`/`deleteMany` từ bất kỳ predicate nào. Khi cần thay đổi field, increment tồn kho hoặc xóa có điều kiện, dùng các phương thức repository chuyên biệt, `@Update`, `MongoTemplate` hoặc custom repository phù hợp. Không cố ép kiểu trả về `Page` hay `Predicate` để biểu diễn một write.

## 7. Predicate đơn giản: so sánh theo property Java

Ví dụ dùng Querydsl để lọc sản phẩm của một tenant đang hoạt động và đủ tồn kho:

~~~java
package com.example.catalog;

import com.querydsl.core.types.Predicate;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ProductQuerydslService {
    private final CatalogProductRepository products;

    public ProductQuerydslService(CatalogProductRepository products) {
        this.products = products;
    }

    public List<CatalogProduct> available(
            String tenantId, long minimumStock) {
        if (tenantId == null || tenantId.isBlank()
                || minimumStock < 0) {
            throw new IllegalArgumentException("Bộ lọc không hợp lệ");
        }

        QCatalogProduct p = QCatalogProduct.catalogProduct;
        Predicate where = p.tenantId.eq(tenantId)
                .and(p.status.eq("ACTIVE"))
                .and(p.stock.goe(minimumStock));

        List<CatalogProduct> result = new ArrayList<>();
        products.findAll(where).forEach(result::add);
        return result;
    }
}
~~~

Lưu ý `findAll(Predicate)` trả `Iterable`; ví dụ đưa kết quả vào `List` để caller tiện sử dụng. Không tải vô hạn toàn collection qua `findAll` nếu filter quá rộng. Với API production, nên giới hạn hoặc phân trang.

Predicate trên có ý nghĩa BSON như sau:

~~~json
{
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "stock_qty": { "$gte": 5 }
}
~~~

Trong Java, property vẫn là `p.stock`; BSON vật lý là `stock_qty` vì `@Field("stock_qty")`. **Đây là biểu diễn tương đương về ngữ nghĩa, không phải cam kết từng byte của command driver.** Chính việc ánh xạ property sang BSON là một trong những điều cần test khi dùng Querydsl MongoDB adapter.

### 7.1. Các phép so sánh phổ biến

| Querydsl expression | Ý nghĩa logic | BSON tương đương trong schema mẫu |
|---|---|---|
`p.status.eq("ACTIVE")` | Bằng nhau | `{ "status": "ACTIVE" }` |
`p.status.ne("DELETED")` | Khác giá trị | `{ "status": { "$ne": "DELETED" } }` |
`p.stock.gt(10)` | Lớn hơn | `{ "stock_qty": { "$gt": 10 } }` |
`p.stock.goe(10)` | Lớn hơn hoặc bằng | `{ "stock_qty": { "$gte": 10 } }` |
`p.stock.lt(10)` | Nhỏ hơn | `{ "stock_qty": { "$lt": 10 } }` |
`p.stock.loe(10)` | Nhỏ hơn hoặc bằng | `{ "stock_qty": { "$lte": 10 } }` |
`p.status.in("ACTIVE", "PENDING")` | Thuộc tập | `{ "status": { "$in": ["ACTIVE", "PENDING"] } }` |
`p.name.isNotNull()` | Giá trị không null | Cần xác minh semantics field BSON null/missing |
`p.tenantId.eq("tenant-a").and(...)` | Kết hợp AND | Nhiều điều kiện hoặc `$and` |
`p.status.eq("ACTIVE").or(p.status.eq("PENDING"))` | Kết hợp OR | `$or` hoặc biểu thức tương đương |

Bảng này minh họa **các toán tử thường kỳ vọng**; MongoDB adapter không nhất thiết hỗ trợ tất cả expression của Querydsl Core, và một số phép so sánh kiểu ngày, chuỗi hoặc null có semantics cần kiểm tra cụ thể.

Với `$ne` trên field thiếu, MongoDB có thể coi document thiếu field là một kết quả phù hợp. Không nhầm `isNotNull`/`ne` với kiểm tra “field bắt buộc tồn tại và hợp lệ” trong mọi trường hợp.

## 8. BooleanBuilder: tạo bộ lọc động có kiểm soát

Đây là tình huống Querydsl hữu ích nhất: một endpoint có nhiều filter tùy chọn. Không nên tạo hàng chục phương thức `findByStatusAndStockGreaterThan...` tương ứng mọi tổ hợp.

**ProductSearch.java**

~~~java
package com.example.catalog;

public record ProductSearch(
        String status,
        Long minimumStock,
        Long maximumStock,
        String exactSku) {
}
~~~

**ProductSearchService.java**

~~~java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {
    private final CatalogProductRepository products;

    public ProductSearchService(CatalogProductRepository products) {
        this.products = products;
    }

    public Page<CatalogProduct> search(
            String authenticatedTenantId,
            ProductSearch filter,
            int page,
            int size) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || filter == null
                || page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Bộ lọc hoặc trang không hợp lệ");
        }

        QCatalogProduct p = QCatalogProduct.catalogProduct;
        BooleanBuilder where = new BooleanBuilder();

        // Luôn đưa tenant đáng tin cậy vào filter.
        where.and(p.tenantId.eq(authenticatedTenantId));

        if (filter.status() != null && !filter.status().isBlank()) {
            where.and(p.status.eq(filter.status()));
        }
        if (filter.minimumStock() != null) {
            if (filter.minimumStock() < 0) {
                throw new IllegalArgumentException("minimumStock phải >= 0");
            }
            where.and(p.stock.goe(filter.minimumStock()));
        }
        if (filter.maximumStock() != null) {
            if (filter.maximumStock() < 0) {
                throw new IllegalArgumentException("maximumStock phải >= 0");
            }
            where.and(p.stock.loe(filter.maximumStock()));
        }
        if (filter.minimumStock() != null
                && filter.maximumStock() != null
                && filter.minimumStock() > filter.maximumStock()) {
            throw new IllegalArgumentException("Khoảng tồn kho không hợp lệ");
        }
        if (filter.exactSku() != null && !filter.exactSku().isBlank()) {
            where.and(p.sku.eq(filter.exactSku()));
        }

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id"));

        return products.findAll(
                where,
                PageRequest.of(page, size, sort));
    }
}
~~~

Ý tưởng:

1. `BooleanBuilder` tạo một predicate có nhiều điều kiện độc lập.
2. `tenantId` được thêm **vô điều kiện từ ngữ cảnh đã xác thực**; client không được loại bỏ nó.
3. Các filter khác chỉ bổ sung khi được truyền hợp lệ.
4. `PageRequest` giới hạn dữ liệu và có sort ổn định theo `createdAt DESC, _id ASC`.
5. `Page<CatalogProduct>` trả dữ liệu trang cùng metadata tổng số, có thể khiến framework thực hiện thêm phép đếm.

Với tập dữ liệu lớn, không nên coi `Page` luôn rẻ. Nếu UI chỉ cần biết còn trang sau, cân nhắc API scrolling/cursor được hỗ trợ hoặc viết custom repository với `MongoTemplate`. `QuerydslPredicateExecutor` không tự cung cấp mọi đặc tính `Slice`/keyset của các API khác.

### 8.1. Vì sao không trả Predicate thẳng từ client?

Một request HTTP có thể khai báo:

~~~json
{
  "status": "ACTIVE",
  "minimumStock": 5,
  "maximumStock": 20,
  "exactSku": null
}
~~~

Hãy parse vào DTO có các field **được phép**, validate và tạo Predicate ở server. Không cho phép client gửi tên class Querydsl, field path hoặc biểu thức tùy ý rồi thực thi trên database, vì có thể dẫn đến đọc field nội bộ, truy vấn regex rất tốn tài nguyên hoặc vượt qua điều kiện tenant.

Nếu Spring Data Web của một phiên bản hỗ trợ `@QuerydslPredicate` để bind query parameters, đó là một tính năng **tùy chọn của web binding**, không tự thay thế authorization, whitelist field, giới hạn sort/pagination hoặc validation. Một resolver tạo Predicate tự động có thể để lộ nhiều property hơn dự kiến nếu không được cấu hình.

## 9. Dùng findOne, findAll, count và exists

Ngoài `findAll(predicate)`, executor có các thao tác kiểm tra dữ liệu:

~~~java
QCatalogProduct p = QCatalogProduct.catalogProduct;

Predicate specific = p.tenantId.eq("tenant-a")
        .and(p.id.eq("p-101"));

Optional<CatalogProduct> one = products.findOne(specific);
boolean hasItem = products.exists(specific);
long exactMatches = products.count(specific);
~~~

Ở đây giả sử có biến `products` kiểu `CatalogProductRepository` và import `java.util.Optional`. Predicate chọn ID cùng tenant nên phù hợp kỳ vọng chỉ có tối đa một document.

### 9.1. Các loại kết quả

- `findOne` trả `Optional<CatalogProduct>` khi adapter hỗ trợ. Không được dereference kết quả khi `Optional.empty()`.
- `findAll` trả `Iterable<CatalogProduct>`, không phải mặc định `List`.
- `count` trả số document khớp điều kiện tại thời điểm đọc; không phải count đã thay đổi do lệnh ghi trước.
- `exists` trả boolean, nhưng đó chỉ là câu trả lời tại thời điểm truy vấn.

**`exists` không là lock.** Hai request có thể cùng thấy `exists == false` rồi cùng insert một sản phẩm với business key trùng. Dùng unique index và xử lý duplicate key thay vì xem `exists` là cơ chế bảo vệ tính duy nhất.

### 9.2. Không coi findOne là API “Top 1”

Ví dụ `p.status.eq("ACTIVE")` có thể khớp hàng nghìn document. Đừng dùng `findOne` để chọn “sản phẩm mới nhất”; thay bằng predicate cộng sort và page size 1:

~~~java
Page<CatalogProduct> newest = products.findAll(
        p.tenantId.eq("tenant-a").and(p.status.eq("ACTIVE")),
        PageRequest.of(0, 1,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.asc("id"))));
~~~

Đây là ví dụ dễ hiểu nhưng `Page` có thể cần count cho metadata. Nếu chỉ cần một bản ghi đầu tiên mà không cần total count, `MongoTemplate.findOne` với Query và Sort có thể tiết kiệm hơn; chọn theo yêu cầu thực tế.

## 10. AND/OR, nhóm ngoặc và tính đúng đắn của logic

Predicate có thể kết hợp nhiều điều kiện bằng `and` và `or`. Khi yêu cầu có ngoặc, hãy diễn đạt **nhóm** rõ ràng:

~~~text
tenant = "tenant-a"
AND status = "ACTIVE"
AND (stock >= 10 OR sku = "SPECIAL")
~~~

Querydsl:

~~~java
QCatalogProduct p = QCatalogProduct.catalogProduct;

Predicate predicate = p.tenantId.eq("tenant-a")
        .and(p.status.eq("ACTIVE"))
        .and(
                p.stock.goe(10)
                        .or(p.sku.eq("SPECIAL")));
~~~

MongoDB filter tương đương:

~~~json
{
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "$or": [
    { "stock_qty": { "$gte": 10 } },
    { "sku": "SPECIAL" }
  ]
}
~~~

Không thay biểu thức trên bằng:

~~~java
Predicate wrong = p.tenantId.eq("tenant-a")
        .and(p.status.eq("ACTIVE"))
        .and(p.stock.goe(10))
        .or(p.sku.eq("SPECIAL"));
~~~

Vì ở biểu thức `wrong`, nhánh `sku = "SPECIAL"` có thể làm predicate đúng **mà không thỏa tenant**, tức là dữ liệu tenant khác có thể lọt vào kết quả.

**Đây là lỗi bảo mật thật sự:** khi có OR, tenant filter phải nằm ngoài toàn bộ nhóm OR. Cần test trường hợp một document của tenant khác có `sku = SPECIAL` để chứng minh nó bị loại.

Nếu predicate phức tạp đến mức khó nhìn ngoặc và khó tối ưu index, có thể diễn đạt bằng `MongoTemplate`/`Criteria.andOperator`/`orOperator`, kèm unit test và integration test.

## 11. Querydsl và mapping tên field BSON

Trong entity mẫu:

~~~java
@Field("display_name")
private String name;

@Field("stock_qty")
private long stock;
~~~

Q-type được sinh dựa trên **property Java**, ví dụ `p.name` và `p.stock`. Khi truy vấn thực thi, adapter MongoDB phải tạo BSON tương thích schema thực tế:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
});
~~~

Không nên hardcode `p.stock_qty`: Q-type không tự tạo property Java theo tên `@Field`. Trong các phiên bản có cơ chế mapping Querydsl MongoDB được hỗ trợ, hãy kiểm tra adapter sử dụng đúng metadata Spring Data khi chuyển property sang BSON.

**Một cách kiểm chứng đáng tin:**

1. Lưu document bằng `MongoTemplate.insert(entity)`.
2. Dùng raw MongoDB collection đọc BSON và xác nhận tồn tại `stock_qty`, `display_name`.
3. Gọi `repository.findAll(p.stock.goe(...))`.
4. Đối chiếu kết quả với query `MongoTemplate` hoặc lệnh MongoDB shell dùng tên field thật.
5. Nếu cần, capture `CommandStartedEvent` của MongoDB driver để xem `filter` chính xác.

Một kết quả integration test khớp mong đợi giúp xác minh đường mapper của phiên bản đó. Nếu Querydsl adapter không xử lý đúng `@Field` hoặc path nested, hãy chuyển riêng truy vấn đó sang `MongoTemplate` thay vì xóa annotation mapping hay đổi schema tùy tiện.

## 12. String, null, nested property và array: không mặc định hỗ trợ tất cả

Querydsl Core có nhiều expression như so khớp chuỗi, bất đẳng thức, kiểm tra null, truy cập collection và nested path. Nhưng **Querydsl MongoDB serializer/adapter** phải ánh xạ các expression đó sang MongoDB tương ứng. Khả năng hỗ trợ có thể **khác** JPA/SQL.

| Nhu cầu | Ví dụ/điểm cần kiểm tra | Lý do |
|---|---|---|
So khớp chuỗi một phần | `p.name.contains("nước")` | MongoDB có thể dùng regex, khác full-text search |
Không phân biệt hoa/thường | `p.name.containsIgnoreCase("NƯỚC")` | Cần xác minh regex/collation, index và Unicode |
Kiểm tra null | `p.name.isNull()` | MongoDB phân biệt field null và field thiếu tùy toán tử |
Đường dẫn document lồng nhau | `p.supplier.countryCode.eq("VN")` nếu Q-type có path đó | Cần mapping nested `@Field` |
Mảng chuỗi | `p.tags.any().eq("outdoor")` nếu path/operator được adapter hỗ trợ | MongoDB có multikey và array semantics riêng |
Nhiều điều kiện trên một array document | Cần cùng một phần tử | Phải biểu đạt `$elemMatch`, không chỉ ghép dot paths |
Truy vấn tồn tại field | Semantics `$exists` | Không đồng nghĩa so sánh khác null |
Geo/text/aggregation | Toán tử MongoDB chuyên dụng | Predicate executor không phải DSL đầy đủ cho pipeline |

Những expression trong bảng là **những thứ cần xác minh**, không phải danh sách cam kết mọi adapter đều hỗ trợ.

### 12.1. Bẫy cùng phần tử với array of documents

Giả sử có array:

~~~json
{
  "variants": [
    { "color": "RED", "quantity": 2 },
    { "color": "BLUE", "quantity": 15 }
  ]
}
~~~

Truy vấn MongoDB:

~~~javascript
{
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
}
~~~

có thể khớp document dù **không có biến thể RED nào đủ 10 chiếc**, vì hai điều kiện được thỏa trên hai phần tử khác nhau. Nếu muốn cùng phần tử, cần `$elemMatch`.

Nếu Querydsl adapter chưa chuyển được một expression thành `$elemMatch` đúng semantics, dùng `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query sameVariant = Query.query(
        Criteria.where("variants").elemMatch(
                Criteria.where("color").is("RED")
                        .and("quantity").gte(10)));
~~~

Ví dụ `sameVariant` này giả định entity thực tế có field `variants` chứa document con; entity `CatalogProduct` của mục 4 chưa khai báo property đó. Khi dùng typed MongoTemplate, cần mở rộng schema/entity tương ứng và kiểm tra mapping.

### 12.2. Regex không tự có index tốt

Ngay cả khi adapter hỗ trợ `containsIgnoreCase`, truy vấn có thể tạo regex quét nhiều document và không sử dụng index B-tree theo cách mong muốn. Đừng suy ra query nhanh vì nó được xây dựng từ một method type-safe. Với tìm kiếm từ ngữ, cân nhắc text index hoặc giải pháp search chuyên biệt và đo query plan.

## 13. Phân trang, sort và hiệu năng Querydsl

Một truy vấn dùng:

~~~java
Page<CatalogProduct> page = products.findAll(
        p.tenantId.eq("tenant-a")
                .and(p.status.eq("ACTIVE")),
        PageRequest.of(0, 20,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.asc("id"))));
~~~

Giả sử `p` là `QCatalogProduct.catalogProduct`. `Sort` ở đây dùng property Java; `id` tương ứng BSON `_id`.

### 13.1. Vì sao cần thứ tự ổn định?

Nếu chỉ sort theo `createdAt` và nhiều document có timestamp bằng nhau, các trang có thể không ổn định dù dữ liệu không đổi. Thêm `id` làm tie-breaker giúp có thứ tự xác định.

Tuy nhiên, sort ổn định **không tạo snapshot giữa nhiều request**. Khi có insert/delete hoặc field sort thay đổi, offset pagination vẫn có thể lặp/bỏ sót phần tử.

### 13.2. Page có thể yêu cầu count

`Page<T>` cung cấp `getTotalElements()`/`getTotalPages()`. Adapter có thể phải đếm document phù hợp thêm một lần để cung cấp metadata; không mặc định mọi lần gọi chạy đúng hai command, vì framework có thể tối ưu các trường hợp cụ thể.

Nếu giao diện chỉ cần nút *Xem thêm*, đừng ép mọi truy vấn vào `Page` vô thời hạn. Với yêu cầu phân trang sâu, kiểm tra `Slice`/scrolling API có được repository/phiên bản hỗ trợ hay không, hoặc triển khai keyset cursor bằng `MongoTemplate`.

### 13.3. Index và explain

Với filter tenant + status và sort mới nhất trước:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_tenant_status_created_id" }
);
~~~

Đối chiếu query tương đương bằng MongoDB shell:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20)
.explain("executionStats");
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và latency. Index này không nhất thiết tối ưu cho thêm điều kiện range `stock_qty >= 5`; thứ tự field trong compound index, selectivity và sort cần được thiết kế theo query workload.

Querydsl không thay thế kế hoạch index. Nếu truy vấn kết hợp OR, regex hoặc range trên nhiều field, kế hoạch thực thi có thể khác đáng kể so với truy vấn equality đơn giản.

## 14. Bảo mật: tenant predicate không được là bộ lọc tùy chọn

Trong hệ thống đa tenant, điều kiện:

~~~java
Predicate tenantScope = p.tenantId.eq(authenticatedTenantId);
~~~

phải được kết hợp với các filter do người dùng lựa chọn theo quy tắc **AND bao ngoài**, không để một nhóm OR làm mất phạm vi tenant.

Sai:

~~~java
Predicate unsafe = p.tenantId.eq(authenticatedTenantId)
        .and(p.status.eq("ACTIVE"))
        .or(p.sku.eq("SPECIAL"));
~~~

Đúng:

~~~java
Predicate safe = p.tenantId.eq(authenticatedTenantId)
        .and(
                p.status.eq("ACTIVE")
                        .or(p.sku.eq("SPECIAL")));
~~~

Người dùng có thể được phép chọn trạng thái hoặc SKU, nhưng **không được bỏ điều kiện tenant**. `authenticatedTenantId` phải đến từ authentication context đáng tin cậy, không phải client tự gửi rồi được tin nguyên trạng.

Nếu service có nhiều phương thức truy vấn và việc thêm tenant thủ công dễ bị bỏ quên, nên thiết kế một custom repository layer hoặc truy vấn đã đóng gói để mọi đường đọc/ghi đều áp dụng scope. Querydsl không tự cung cấp row-level security.

Ngoài tenant, kiểm tra:

- Quyền xem sản phẩm theo nhóm người dùng, trạng thái ẩn và ownership.
- Những property được phép lọc/sort từ HTTP; không expose arbitrary Q-path.
- Giới hạn kích thước trang và tần suất truy vấn để tránh filter quá rộng.
- Không log predicate/BSON có thông tin nhạy cảm vào nơi không được phép.
- Không dùng kết quả `exists` để suy luận thông tin tài nguyên của tenant khác.

## 15. Kiểm thử trên MongoDB thật

Kiểm thử mock repository chỉ chứng minh service **đã gọi** một predicate nào đó, không chứng minh Spring Data MongoDB adapter có khả năng **chuyển predicate thành BSON đúng**. Do đó cần integration test có MongoDB thật trong database/collection cô lập. `@DataMongoTest` của Spring Boot 3.x không tự khởi động MongoDB; có thể cấp server qua Testcontainers hoặc môi trường test được cấu hình.

### 15.1. Test điều kiện, count, exists, Page và mapping

**CatalogProductQuerydslTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class CatalogProductQuerydslTest {
    @Autowired
    CatalogProductRepository products;

    @Autowired
    MongoTemplate mongo;

    private CatalogProduct product(
            String id, String tenant, String status,
            long stock, String sku, int hour) {
        return new CatalogProduct(
                id, tenant, sku, "Product " + id, stock, status,
                Instant.parse("2026-11-20T00:00:00Z")
                        .plusSeconds(hour * 3600L),
                List.of("outdoor"));
    }

    @BeforeEach
    void seed() {
        // Chỉ dùng trong database test cô lập.
        mongo.remove(new Query(), CatalogProduct.class);
        mongo.insert(List.of(
                product("p-101", "tenant-a", "ACTIVE", 12, "A", 8),
                product("p-102", "tenant-a", "ACTIVE", 3, "B", 9),
                product("p-103", "tenant-a", "INACTIVE", 20, "C", 10),
                product("p-104", "tenant-b", "ACTIVE", 30, "SPECIAL", 11)),
                CatalogProduct.class);
    }

    @Test
    void predicateSelectsTypedFieldAndTenant() {
        QCatalogProduct p = QCatalogProduct.catalogProduct;

        var predicate = p.tenantId.eq("tenant-a")
                .and(p.status.eq("ACTIVE"))
                .and(p.stock.goe(5L));

        assertThat(products.findAll(predicate))
                .extracting(CatalogProduct::getId)
                .containsExactly("p-101");

        Document bson = mongo.getCollection("catalog_products")
                .find(new Document("_id", "p-101")).first();
        assertThat(bson).isNotNull();
        assertThat(bson.get("stock_qty"))
                .isInstanceOf(Number.class);
        assertThat(bson.containsKey("stock")).isFalse();
        assertThat(bson.containsKey("display_name")).isTrue();
    }

    @Test
    void countExistsAndFindOneReflectFilteredData() {
        QCatalogProduct p = QCatalogProduct.catalogProduct;

        var activeForTenant = p.tenantId.eq("tenant-a")
                .and(p.status.eq("ACTIVE"));

        assertThat(products.count(activeForTenant)).isEqualTo(2);
        assertThat(products.exists(
                activeForTenant.and(p.stock.goe(5L)))).isTrue();
        assertThat(products.exists(
                activeForTenant.and(p.stock.goe(50L)))).isFalse();

        assertThat(products.findOne(p.id.eq("p-101")))
                .isPresent()
                .get()
                .extracting(CatalogProduct::getSku)
                .isEqualTo("A");
    }

    @Test
    void pageablePredicateUsesStableSort() {
        QCatalogProduct p = QCatalogProduct.catalogProduct;

        Page<CatalogProduct> page = products.findAll(
                p.tenantId.eq("tenant-a")
                        .and(p.status.eq("ACTIVE")),
                PageRequest.of(0, 1,
                        Sort.by(Sort.Order.desc("createdAt"),
                                Sort.Order.asc("id"))));

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().get(0).getId())
                .isEqualTo("p-102");
        assertThat(page.getTotalElements()).isEqualTo(2);
    }

    @Test
    void groupedOrDoesNotLeakOtherTenant() {
        QCatalogProduct p = QCatalogProduct.catalogProduct;

        var safe = p.tenantId.eq("tenant-a")
                .and(p.status.eq("ACTIVE")
                        .or(p.sku.eq("SPECIAL")));

        assertThat(products.findAll(safe))
                .extracting(CatalogProduct::getId)
                .containsExactlyInAnyOrder("p-101", "p-102");
    }
}
~~~

Test sử dụng `QCatalogProduct` được annotation processor tạo khi build. Khi không tạo được Q-type hoặc repository factory không hỗ trợ Querydsl ở phiên bản thực tế, test sẽ không biên dịch/không khởi tạo; đó là **tín hiệu xác minh tương thích**, không phải lỗi cần che bằng cast hoặc mock.

### 15.2. Kiểm tra đúng kiểu BSON

Không chỉ assert số lượng: hãy đối chiếu raw document `stock_qty`, `display_name` và phép query tương đương bằng `MongoTemplate` hoặc shell. Nếu một test query thành công nhờ document có cả hai field Java/BSON do dữ liệu lịch sử lẫn lộn, kết quả đó chưa chứng minh mapping đúng. Nên seed theo **schema BSON canonical** và test document thiếu/sai field.

### 15.3. Kiểm tra translator/operator

Tạo test nhỏ riêng cho:

1. `eq`/`ne` và phép so sánh số.
2. `and`/`or` có ngoặc.
3. `isNull` với field null và field thiếu.
4. Chuỗi `contains`/`containsIgnoreCase` nếu adapter của phiên bản hỗ trợ.
5. Array path `any()` và nested `@Field` nếu dự án sử dụng.
6. `findAll(Predicate, Pageable)` với sort ổn định và số lệnh count.
7. `findOne` khi predicate không unique, theo contract của phiên bản.

Đối với một operator bị từ chối hoặc có BSON sai, không nên gán nhãn “Querydsl MongoDB luôn hỗ trợ” chỉ vì cùng operator hoạt động trong Querydsl JPA.

### 15.4. Command monitoring

MongoDB Java Driver hỗ trợ `CommandListener`, có thể được đăng ký vào `MongoClientSettings` trong cấu hình test. `CommandStartedEvent` cho phép quan sát `find`/`count` và filter/sort gửi tới MongoDB.

Ví dụ BSON minh họa:

~~~json
{
  "find": "catalog_products",
  "filter": {
    "tenantId": "tenant-a",
    "status": "ACTIVE",
    "stock_qty": { "$gte": 5 }
  }
}
~~~

Không coi JSON trên là byte-for-byte command thật; cần lọc theo collection, operation và driver version. **Không log toàn bộ command production** nếu query chứa thông tin nhạy cảm hoặc nếu không có chính sách lưu trữ/quyền truy cập phù hợp.

## 16. Khi không có Querydsl adapter: MongoTemplate và custom repository

Nếu phiên bản Spring Data MongoDB của dự án không cung cấp/không tương thích với Querydsl adapter, **không cố giữ một interface `QuerydslPredicateExecutor` không khởi tạo được**. Mô hình thay thế rõ ràng là:

1. Giữ `MongoRepository` cho CRUD và derived queries đơn giản.
2. Thêm **repository fragment** hoặc service query dùng `MongoTemplate`.
3. Biểu diễn filter đầu vào bằng DTO riêng để giới hạn field được phép.
4. Dùng `Criteria` theo property Java khi có entity type và test BSON.

Ví dụ cùng logic tìm sản phẩm:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCriteriaSearchService {
    private final MongoTemplate mongo;

    public ProductCriteriaSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> available(
            String authenticatedTenantId, long minimumStock) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || minimumStock < 0) {
            throw new IllegalArgumentException("Bộ lọc không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(minimumStock));

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(50);

        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

Trong một typed query, Spring Data sẽ map `stock` thành `stock_qty` khi dùng metadata `CatalogProduct.class`. Khi filter động phức tạp hơn, có thể ghép `Criteria.andOperator/orOperator` hoặc tạo nhiều điều kiện theo DTO.

Điều quan trọng khi chuyển từ Querydsl sang `MongoTemplate` là **giữ nguyên semantics**, không chỉ thay tên hàm. Hãy dùng cùng tập integration test kiểm tra tenant, null/missing, sort, array và hiệu năng để so sánh hai implementation.

### So sánh lựa chọn

| Yêu cầu | Querydsl executor khi được hỗ trợ | MongoTemplate/Criteria |
|---|---|---|
Type-safe path do code generation | Có | Dùng tên property chuỗi |
Không cần annotation processor | Không | Có |
CRUD repository đơn giản | Kết hợp với MongoRepository | MongoRepository vẫn hữu ích |
Filter động nhiều điều kiện | Thuận tiện với BooleanBuilder | Thuận tiện với Criteria/Query |
Truy vấn array phức tạp/$elemMatch | Phụ thuộc translator hỗ trợ | Trực tiếp hơn |
Aggregation/$lookup/$group | Không phải API chính | `Aggregation`/`MongoTemplate` |
Update/transaction có điều kiện | Không phải nhiệm vụ PredicateExecutor | Hỗ trợ Query/Update và transaction tương ứng |
Nâng cấp khi adapter Querydsl không tương thích | Cần di chuyển code | Ít phụ thuộc Querydsl |

## 17. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
Không tìm thấy `QCatalogProduct` | Annotation processing không chạy | Kiểm tra `@QueryEntity`, APT, generated source |
IDE thấy Q-type nhưng CI không biên dịch | Generated sources chỉ có cục bộ, pipeline build thiếu APT | Cấu hình build tái tạo Q-type từ nguồn |
Repository không khởi tạo khi thêm executor | Bản MongoDB chưa hỗ trợ adapter hoặc dependencies không tương thích | Xác minh release và runtime classpath, cân nhắc custom repository |
Lỗi `NoClassDefFoundError` liên quan Querydsl | Lệch phiên bản core/mongodb/apt hoặc driver transitives | Đồng bộ dependency graph, loại bỏ conflict đúng cách |
Nhầm ví dụ Querydsl JPA sang MongoDB | Operator/serialization không tương thích | Dùng test MongoDB thật, không dựa vào SQL |
Filter `p.stock` không khớp data | BSON là `stock_qty` hoặc schema cũ khác | Kiểm tra Spring Data mapping và raw BSON |
`findOne` với điều kiện không unique | Có thể báo lỗi nhiều kết quả | Tạo unique index hoặc chuyển sang phân trang |
`containsIgnoreCase` chậm | Regex không dùng index tốt | Đo explain, dùng search strategy phù hợp |
`p.tags.any()` hoặc nested path gây lỗi | Mongo serializer không hỗ trợ expression mong muốn | Dùng Criteria/`$elemMatch` hoặc thiết kế lại query |
`and(...).or(...)` làm lộ dữ liệu tenant khác | Nhóm OR sai | Đặt tenant condition ngoài toàn bộ OR |
Trang kết quả lặp hoặc thiếu | Sort thiếu khóa duy nhất, offset bị dịch | Tie-breaker ID; keyset/cursor khi cần |
Tin `exists` bảo đảm uniqueness | Race giữa exists và insert | Unique index và xử lý duplicate |
Nhầm count predicate với count cập nhật | API đọc không phải write result | Dùng `UpdateResult`/`DeleteResult` |
Không kiểm tra server command | Query dịch khác kỳ vọng | CommandListener và integration test |

## 18. Bài tập thực hành

**Bài 1 — Sinh Q-type.** Định nghĩa `CatalogProduct` có `@QueryEntity` và `@Document`. Cấu hình annotation processor, xác nhận sinh `QCatalogProduct`, đổi tên một property rồi build lại để quan sát lỗi biên dịch ở code cũ.

**Bài 2 — Repository executor.** Khai báo repository kế thừa `MongoRepository` và `QuerydslPredicateExecutor`. Gọi `findAll` với predicate `tenantId = tenant-a AND status = ACTIVE`, kiểm tra ID mong đợi trên MongoDB test.

**Bài 3 — BooleanBuilder.** Tạo DTO lọc tùy chọn `status`, `minimumStock`, `maximumStock`, `sku`. So sánh kết quả với cùng bộ filter viết bằng `MongoTemplate`. Test không truyền filter tùy chọn vẫn chỉ trả tenant đã xác thực.

**Bài 4 — Count và exists.** Với 4 sản phẩm và hai tenant, gọi `count(predicate)` và `exists(predicate)`. Chứng minh hai phương thức chỉ phản ánh lần đọc hiện tại, không ngăn race khi insert.

**Bài 5 — Logic OR.** Tạo sản phẩm tenant-b có SKU `SPECIAL`. So sánh `tenant.and(status).or(skuSpecial)` với `tenant.and(status.or(skuSpecial))`; kiểm chứng predicate sai làm lộ sản phẩm tenant khác.

**Bài 6 — BSON mapping.** Ánh xạ `stock` thành `stock_qty` và `name` thành `display_name`. Ghi entity bằng Spring Data, đọc raw BSON, chạy Querydsl predicate rồi đối chiếu `MongoTemplate`. Nếu kết quả không khớp, ghi rõ phiên bản, lỗi và giải pháp thay thế.

**Bài 7 — Null và mảng.** Tạo document thiếu field, field null, mảng scalar và mảng document con có điều kiện cross-element. Kiểm tra những Querydsl expressions adapter thực sự hỗ trợ, viết lại bằng `Criteria` khi cần `$exists`/`$elemMatch`.

**Bài 8 — Paging và index.** So sánh `findAll(predicate, Pageable)` với truy vấn `MongoTemplate` có sort, filter và limit tương đương. Đo số command, `getTotalElements()` và `explain("executionStats")`; tạo compound index chỉ sau khi xác minh workload.

**Bài 9 — Nâng cấp phiên bản.** Lập bảng dependency Spring Boot/Spring Data MongoDB/Querydsl/driver hiện tại. Kiểm tra adapter, chạy build tạo Q-type và integration test. Thiết kế fallback `MongoTemplate` nếu nhánh mới không hỗ trợ hoặc một operator không được dịch đúng.

## 19. Ghi nhớ

**Querydsl** cung cấp các **Q-type** và `Predicate` để diễn đạt điều kiện truy vấn theo property Java có kiểu. **`QuerydslPredicateExecutor<T>`** là interface repository dùng những predicate đó cho các thao tác đọc, đếm, kiểm tra tồn tại và phân trang **khi adapter Spring Data MongoDB của phiên bản đang sử dụng hỗ trợ**.

Để dùng đúng cần có **annotation processor sinh Q-type**, dependencies tương thích và integration test xác minh **mapping Java → BSON**, cách translator xử lý operators, null/missing, array và sort. Không coi toàn bộ Querydsl Core hoặc ví dụ Querydsl JPA là bằng chứng MongoDB hỗ trợ mọi biểu thức.

Về thiết kế, luôn gắn **tenant/quyền truy cập đáng tin cậy** vào predicate, giới hạn dữ liệu trả về và đo query plan. Khi adapter không khả dụng hoặc truy vấn cần `$elemMatch`, aggregation, update/transaction chuyên dụng, **`MongoTemplate` + `Criteria`** là lối đi rõ ràng hơn. Mức độ đúng đắn được chứng minh bởi **BSON và kết quả MongoDB thực tế**, không chỉ bởi việc biểu thức Java biên dịch thành công.
