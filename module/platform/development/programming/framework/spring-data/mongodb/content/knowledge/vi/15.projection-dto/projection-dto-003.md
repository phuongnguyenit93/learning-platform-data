# DTO constructor và Java record

## 1. Vì sao cần DTO projection khi đã có entity?

Trong chương **Projection và DTO** của **Spring Data MongoDB**, một câu hỏi quan trọng là: *Khi API chỉ cần ba trường của một sản phẩm, có nên tải cả document rồi trả nguyên entity không?*

Giả sử collection sản phẩm lưu tên, giá, tồn kho, trạng thái, ghi chú nội bộ và metadata cập nhật. Màn hình danh mục chỉ cần **ID, tên và giá**. Trả toàn bộ entity không chỉ tăng lượng dữ liệu xử lý mà còn khiến hợp đồng API phụ thuộc chặt vào mô hình lưu trữ. Một thay đổi trong entity có thể vô tình làm thay đổi dữ liệu được serialize ra ngoài nếu API trả thẳng entity.

**DTO** (*Data Transfer Object*) là kiểu dữ liệu dành cho việc truyền kết quả giữa các lớp hoặc tới client. **Projection** là cách chọn một phần dữ liệu hoặc một hình dạng kết quả từ nguồn; trong Spring Data, projection có thể được hiện thực bằng interface hoặc class/record. Hai khái niệm liên quan nhưng **không đồng nhất**:

- Một DTO có thể được **tạo trực tiếp bởi Spring Data khi truy vấn**: đó là *class-based DTO projection*.
- Một DTO cũng có thể được **tạo thủ công từ entity đã tải đầy đủ**: vẫn là DTO, nhưng không nhất thiết giảm số field được đọc từ MongoDB.
- Một projection có thể là **interface proxy** thay vì đối tượng DTO cụ thể.
- Aggregation `$project` của MongoDB là **stage phía server**; kết quả aggregation có thể được ánh xạ tiếp sang DTO, kể cả Java record.

Mục tiêu bài học là sử dụng **constructor của class DTO** và **canonical constructor của Java record** để trả dữ liệu rõ ràng, hiểu cơ chế chọn field và biết cách kiểm tra **BSON được truy vấn thực sự**.

> Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB Java Sync Driver. Cách suy diễn field và khả năng hỗ trợ projection phụ thuộc loại truy vấn cùng phiên bản framework. Luôn kiểm chứng với integration test trước khi khẳng định một API cụ thể tối ưu số field tải về.

## 2. Các kiểu kết quả thường gặp

| Cách trả dữ liệu | Đối tượng nhận được | Cách xây dựng | Khi phù hợp |
|---|---|---|---|
Trả entity `CatalogProduct` | Entity đầy đủ | Converter ánh xạ document vào entity | Luồng nghiệp vụ cần trạng thái đầy đủ để xử lý |
Interface projection | Proxy thực hiện interface | Spring Data tạo proxy và gọi accessor | Một vài property, kể cả trường hợp nested interface projection |
Class-based DTO projection | Instance của class DTO | Constructor phù hợp và metadata tham số | Hợp đồng đầu ra cụ thể, bất biến, có logic trình bày đơn giản |
Java record projection | Instance của record | Canonical constructor | DTO nhỏ, rõ field, dễ so sánh giá trị |
Aggregation + DTO | DTO/record từ document kết quả pipeline | `$project`/`$group`/... rồi mapping | Báo cáo, nhóm, tính toán hoặc đổi hình dạng dữ liệu |

Ví dụ interface projection tối giản:

~~~java
package com.example.catalog;

public interface ProductNameView {
    String getName();
    long getPriceVnd();
}
~~~

Điểm khác biệt: interface-based projection thường được Spring Data cung cấp bằng proxy; class/record projection **không yêu cầu tạo proxy cho mỗi DTO** mà dùng constructor để khởi tạo đối tượng. Java record cũng tự cung cấp `equals`, `hashCode`, `toString` và accessor theo tên component.

Không có nghĩa “record luôn nhanh hơn interface”. Hiệu năng phải đo theo dữ liệu, số field chọn, conversion, round trip, phân trang và index.

## 3. Entity nguồn và dữ liệu BSON

Chúng ta dùng collection `catalog_products`. Các class trong ví dụ thuộc package `com.example.catalog` để Spring Boot có thể quét repository theo quy ước.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String category;
    private long priceVnd;
    private int stock;
    private String status;
    private String internalNote;
    @Version
    private Long version;

    protected CatalogProduct() {
        // Phục vụ materialization của Spring Data.
    }

    public CatalogProduct(
            String id, String name, String category,
            long priceVnd, int stock, String status, String internalNote) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.priceVnd = priceVnd;
        this.stock = stock;
        this.status = status;
        this.internalNote = internalNote;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public long getPriceVnd() { return priceVnd; }
    public int getStock() { return stock; }
    public String getStatus() { return status; }
    public String getInternalNote() { return internalNote; }
    public Long getVersion() { return version; }
}
~~~

`@MongoId(FieldType.STRING)` yêu cầu lưu khóa `_id` ở dạng BSON String, tránh việc một `String` có hình dạng 24 ký tự hex bị chuyển thành BSON ObjectId ngoài ý muốn. `@Version` phục vụ optimistic locking cho các đường ghi được Spring Data hỗ trợ, không phải trường cần công khai trong danh sách sản phẩm.

Ví dụ document:

~~~json
{
  "_id": "prd-101",
  "name": "Bình nước 500 ml",
  "category": "drinkware",
  "priceVnd": 129000,
  "stock": 42,
  "status": "ACTIVE",
  "internalNote": "Giá vốn thuộc thông tin nội bộ",
  "version": 0
}
~~~

Trong màn hình danh mục, ta muốn trả:

~~~json
{
  "id": "prd-101",
  "name": "Bình nước 500 ml",
  "priceVnd": 129000
}
~~~

**Chọn ít field hơn trong response** là một mục tiêu; **chỉ đọc ít field từ MongoDB** là mục tiêu bổ sung. Hai mục tiêu cần được xác minh riêng.

## 4. Class-based DTO: ánh xạ qua constructor

DTO truyền thống có thể là class `final`, các property `private final`, constructor để nhận đủ dữ liệu và các getter.

**ProductCardDto.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.PersistenceCreator;

public final class ProductCardDto {
    private final String id;
    private final String name;
    private final long priceVnd;

    @PersistenceCreator
    public ProductCardDto(String id, String name, long priceVnd) {
        this.id = id;
        this.name = name;
        this.priceVnd = priceVnd;
    }

    // Constructor tiện dụng cho code tự tạo DTO, không dùng để đọc projection.
    public ProductCardDto(String name, long priceVnd) {
        this(null, name, priceVnd);
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

Đối với **class-based projection**, Spring Data dựa vào metadata constructor để biết DTO cần những property nào. Ở đây tên tham số `id`, `name`, `priceVnd` trùng với property của `CatalogProduct`. `id` của entity tương ứng `_id` trong BSON.

### 4.1. Vì sao cần chọn constructor rõ ràng?

Với class có nhiều constructor như ví dụ, `@PersistenceCreator` chỉ ra **constructor dùng để materialize đối tượng**. Nếu class chỉ có một constructor phù hợp, framework thường có thể tự chọn constructor đó mà không cần annotation.

Tên tham số rất quan trọng:

- `ProductCardDto(String id, String name, long priceVnd)` diễn tả các property đầu vào.
- Nếu biên dịch class Java mà không giữ metadata tên tham số, Spring Data có thể không xác định được các property cần bind.
- Với dự án Java thông thường, bật tùy chọn biên dịch `-parameters` hoặc dùng cơ chế metadata được phiên bản Spring Data hỗ trợ.
- Đổi tên tham số từ `name` thành `label` mà không đổi mô hình mapping tương ứng **không phải** thay đổi thuần hình thức trong mọi kiểu projection.

Nếu DTO có nhiều constructor và không thể xác định constructor cần chọn, lỗi có thể chỉ xuất hiện khi repository khởi tạo query hoặc khi mapping kết quả, tùy cơ chế bootstrap của phiên bản.

### 4.2. Class DTO khác entity ở điểm nào?

`ProductCardDto` không có `@Document`, `@Id` hay `save`. Nó là **hình dạng đầu ra**, không phải một aggregate root cần được cập nhật. Đừng dùng DTO chỉ có ba field rồi gọi `save` lên collection sản phẩm, vì các field khác có thể không được giữ nguyên theo ý định nghiệp vụ.

Constructor DTO cũng không nên gửi email, đọc HTTP API hoặc làm I/O. Một truy vấn trả 100 document có thể materialize 100 DTO; constructor phải là thao tác tạo dữ liệu nhẹ và xác định.

## 5. Java record: DTO projection ngắn gọn và bất biến

Với Java 17+, record là lựa chọn tự nhiên cho DTO chỉ chứa dữ liệu:

**ProductCardRecord.java**

~~~java
package com.example.catalog;

public record ProductCardRecord(
        String id,
        String name,
        long priceVnd) {
}
~~~

Record có **canonical constructor** nhận các component theo khai báo. Spring Data có thể dùng constructor và metadata component của record để ánh xạ kết quả. Không cần viết getter theo quy ước JavaBean; accessor mặc định là `id()`, `name()`, `priceVnd()`.

Ưu điểm của record:

- Mô tả chính xác hợp đồng dữ liệu được phép trả.
- Không có setter; component reference không thể được gán lại sau khi tạo.
- Có `equals`/`hashCode` theo thành phần, hữu ích cho kiểm thử và cache theo giá trị.
- Giảm mã lặp so với class DTO có các field/getter/constructor thủ công.

**Bất biến nông, không tự bất biến sâu.** Record chứa `List<String> tags` vẫn có thể bị thay đổi thông qua list mutable được truyền vào. Với DTO chứa collection, cân nhắc sao chép phòng vệ:

~~~java
package com.example.catalog;

import java.util.List;

public record ProductDetailRecord(
        String id,
        String name,
        List<String> tags) {

    public ProductDetailRecord {
        tags = tags == null ? List.of() : List.copyOf(tags);
    }
}
~~~

Đây là ví dụ **record DTO khác** với `ProductCardRecord`. Cách xử lý `null` thành list rỗng phù hợp nếu hợp đồng API không cần phân biệt “không có field” với “field rỗng”. Khi giá trị đó mang ý nghĩa nghiệp vụ, phải chọn chính sách rõ ràng thay vì âm thầm chuyển đổi.

### 5.1. Constructor có invariant cần chú ý dữ liệu lịch sử

Record có thể kiểm tra tham số:

~~~java
public ProductCardRecord {
    if (id == null || name == null || priceVnd < 0) {
        throw new IllegalArgumentException("Dữ liệu sản phẩm không hợp lệ");
    }
}
~~~

Đoạn trên là **phần thân compact constructor khi bổ sung vào khai báo `ProductCardRecord`**, không phải một class Java độc lập. Khi đọc document cũ thiếu `name` hoặc lưu giá âm, constructor có thể ném lỗi. Vì vậy các ràng buộc mới trên DTO phải được đánh giá cùng schema dữ liệu nguồn và chiến lược migration.

Không dùng constructor DTO để tự động “sửa” mọi dữ liệu không hợp lệ một cách khó quan sát. Nếu nguồn có schema không nhất quán, hãy xác định rõ dữ liệu nào được chấp nhận, bị loại hoặc cần chuyển đổi.

## 6. Trả class DTO và record từ MongoRepository

Tạo repository trên entity gốc:

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    // Projection theo record: chỉ khai báo contract mà màn hình cần.
    List<ProductCardRecord> findByStatus(String status);

    // Projection theo class DTO có constructor được chọn tường minh.
    List<ProductCardDto> findTop10ByStatusOrderByPriceVndAsc(String status);

    // Dynamic projection: caller quyết định loại kết quả khi gọi.
    <T> List<T> findByCategory(String category, Class<T> type);

    // Khi cần total count và phân trang.
    Page<ProductCardRecord> findByStatus(String status, Pageable pageable);
}
~~~

Ứng dụng chỉ cần thêm starter Spring Data MongoDB và cấu hình kết nối phù hợp; Spring Data xây dựng implementation của interface lúc runtime. Các method dùng **tên property Java** của `CatalogProduct`, không cần lấy tên field BSON để ghép vào tên phương thức.

Service ví dụ:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CatalogReadService {
    private final CatalogProductRepository products;

    public CatalogReadService(CatalogProductRepository products) {
        this.products = products;
    }

    public List<ProductCardRecord> activeCards() {
        return products.findByStatus("ACTIVE");
    }

    public List<ProductCardDto> cheapestTenActive() {
        return products.findTop10ByStatusOrderByPriceVndAsc("ACTIVE");
    }
}
~~~

Với record `ProductCardRecord`, kết quả có thể được tạo với `id`, `name` và `priceVnd` mà không cần tạo entity đầy đủ rồi viết mã mapping thủ công, khi Spring Data MongoDB hỗ trợ class-based projection cho kiểu truy vấn được dùng.

### 6.1. Projection chọn field nào trên MongoDB?

Một câu lệnh `find` có projection chỉ chứa các field DTO sẽ có ý nghĩa tương tự:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE" },
  { _id: 1, name: 1, priceVnd: 1 }
);
~~~

Ở đây:

- `{ status: "ACTIVE" }` là **filter**.
- `{ _id: 1, name: 1, priceVnd: 1 }` là **field projection** của lệnh find.
- `_id` được MongoDB trả mặc định trừ khi bị loại trừ; ghi tường minh trong ví dụ để dễ hiểu.
- `stock` và `internalNote` không cần được truyền về client trong một truy vấn có field projection đúng.

**Quan trọng:** Bảng trên minh họa mục tiêu field selection, **không cam kết** mọi derived repository method với DTO đều gửi chính xác lệnh BSON như vậy. Spring Data có thể tối ưu selection dựa trên constructor properties ở các dạng projection được hỗ trợ; khi dùng annotation, query tùy chỉnh hoặc các kiểu đặc biệt, cần kiểm tra lệnh thực tế. Việc API chỉ trả DTO không tự chứng minh MongoDB đã đọc ít field.

### 6.2. Page, Sort và dữ liệu trả về

Ví dụ:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<ProductCardRecord> page = repository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20,
                Sort.by(Sort.Order.asc("priceVnd"),
                        Sort.Order.asc("id"))));
~~~

`repository` ở đây có kiểu `CatalogProductRepository`. Sort dùng property Java; `id` được mapping sang `_id`. Trường thứ hai giúp kết quả ổn định khi nhiều sản phẩm có cùng giá.

Trả `Page<T>` có thể phát sinh phép đếm tổng để tính metadata trang; kiểm tra số lệnh thật. Nếu chỉ cần biết còn trang tiếp theo, có thể cân nhắc `Slice<T>` hoặc cursor/keyset pagination tùy hỗ trợ của từng API. Việc thu hẹp field của DTO không làm mất chi phí `skip` ở trang sâu.

## 7. Dynamic projection: cùng truy vấn, nhiều kiểu kết quả

Phương thức:

~~~java
<T> List<T> findByCategory(String category, Class<T> type);
~~~

cho phép caller chọn loại projection:

~~~java
List<ProductCardRecord> cards =
        repository.findByCategory("drinkware", ProductCardRecord.class);

List<ProductCardDto> classDtos =
        repository.findByCategory("drinkware", ProductCardDto.class);

List<CatalogProduct> fullEntities =
        repository.findByCategory("drinkware", CatalogProduct.class);
~~~

Khác biệt:

- `ProductCardRecord.class`: nhận đối tượng record với ba component.
- `ProductCardDto.class`: nhận instance class DTO qua constructor.
- `CatalogProduct.class`: nhận entity cho luồng cần toàn bộ state.

Đây là **dynamic projection**, không phải việc trả `Object` rồi ép kiểu thủ công. Tham số `Class<T>` thường được Spring Data sử dụng như một dấu hiệu để xác định projection type và có thể không được xem là một query parameter bình thường; khi viết `@Query`/SpEL cần kiểm tra cách bind tham số đó.

**Đừng tùy tiện chuyển mọi controller sang nhận `Class<T>` từ đầu vào HTTP.** Kiểu DTO được phép trả phải do server quyết định theo contract và quyền truy cập; không để người gọi lựa chọn class bất kỳ để yêu cầu trường không được phép công khai.

## 8. Dùng MongoTemplate và fluent projection

Không phải trường hợp nào cũng cần viết thêm phương thức repository. `MongoTemplate` hỗ trợ xây dựng `Query` động; fluent API có thể chỉ định kiểu dữ liệu đầu ra:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCardQueryService {
    private final MongoTemplate mongo;

    public ProductCardQueryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<ProductCardRecord> activeAbovePrice(long minimumPrice) {
        Query query = Query.query(
                Criteria.where("status").is("ACTIVE")
                        .and("priceVnd").gte(minimumPrice));

        return mongo.query(CatalogProduct.class)
                .as(ProductCardRecord.class)
                .matching(query)
                .all();
    }
}
~~~

`mongo.query(CatalogProduct.class)` thiết lập entity nguồn và metadata mapping; `as(ProductCardRecord.class)` chỉ định projection type. Đây là cách diễn đạt rõ ràng khi điều kiện truy vấn tùy thuộc đầu vào.

Nếu cần kiểm soát các field MongoDB thực sự trả, có thể yêu cầu field projection trên `Query` rồi quan sát command:

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));
query.fields().include("name").include("priceVnd").include("id");

// Thực hiện với source entity để áp dụng metadata ánh xạ phù hợp.
List<ProductCardRecord> cards = mongo.query(CatalogProduct.class)
        .as(ProductCardRecord.class)
        .matching(query)
        .all();
~~~

Trong một truy vấn typed, `id` được ánh xạ sang `_id` của source entity theo cấu hình mapping. Việc projection class có đủ field của constructor và cách ánh xạ tên khi có `@Field` cần được test. Tránh đặt `fields().exclude(...)` loại bỏ một property bắt buộc của constructor rồi ngạc nhiên khi DTO nhận null hoặc không tạo được.

### DTO không phải entity được quản lý

Spring Data MongoDB không cung cấp một persistence context/identity map kiểu JPA cho DTO. Một DTO đã trả về là dữ liệu kết quả, **không tự đồng bộ** khi document nguồn đổi. Muốn cập nhật database, dùng API ghi dành cho entity/collection với kiểm soát concurrency phù hợp, không `save` DTO thiếu field như thể là toàn bộ aggregate.

## 9. Khi query tạo hình dạng mới: aggregation ra record

Class-based DTO projection từ truy vấn `find` thích hợp khi ta chỉ chọn field hiện có. Nhưng nếu cần **tính tổng, nhóm, đổi tên và kết hợp dữ liệu**, aggregation thường rõ ràng hơn.

Ví dụ thống kê tổng tồn kho theo danh mục cho các sản phẩm đang ACTIVE:

**CategoryStockReport.java**

~~~java
package com.example.catalog;

public record CategoryStockReport(
        String category,
        long totalStock) {
}
~~~

Ví dụ aggregation:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class CategoryStockReportService {
    private final MongoTemplate mongo;

    public CategoryStockReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CategoryStockReport> activeStockByCategory() {
        Aggregation pipeline = newAggregation(
                match(Criteria.where("status").is("ACTIVE")),
                group("category").sum("stock").as("totalStock"),
                project("totalStock").and("_id").as("category"));

        return mongo.aggregate(
                pipeline, CatalogProduct.class, CategoryStockReport.class)
                .getMappedResults();
    }
}
~~~

Ý nghĩa pipeline MongoDB:

~~~javascript
db.catalog_products.aggregate([
  { $match: { status: "ACTIVE" } },
  {
    $group: {
      _id: "$category",
      totalStock: { $sum: "$stock" }
    }
  },
  {
    $project: {
      _id: 0,
      category: "$_id",
      totalStock: 1
    }
  }
]);
~~~

`CategoryStockReport` nhận **hình dạng kết quả của aggregation**, không phải hình dạng document nguồn. Với stage `$group`, trường `_id` của kết quả nhóm biểu diễn khóa nhóm chứ không phải ID của một sản phẩm. Vì vậy phải tạo field `category` tường minh.

Ví dụ code Java và pipeline minh họa cùng **ý nghĩa đầu ra**; framework có thể tạo cấu trúc projection khác nhưng tương đương. Khi mapping aggregation sang record, chú ý kiểu `$sum`, null/missing và tên trường kết quả. Đừng sử dụng DTO constructor projection thông thường để thay cho phép tính toán phải chạy ở database.

## 10. DTO, trường lồng nhau và giới hạn projection

### 10.1. Trường lồng nhau không đồng nghĩa nested DTO

Giả sử entity có `SupplierInfo supplier` với `name`, `email` và `address`. Ta muốn DTO:

~~~java
public record SupplierMini(String name) {}
public record ProductWithSupplier(String id, SupplierMini supplier) {}
~~~

Hai record này là **ví dụ mô hình đầu ra**, không thể mặc định rằng class-based DTO projection sẽ tự động tạo nested DTO projection cho từng tầng như interface-based nested projection. Trong Spring Data, **class-based projection không cung cấp nested projection proxy** theo cách interface projection thường làm.

Các hướng an toàn:

1. Dùng interface-based nested projection nếu kiểu truy vấn và cơ chế mapping hỗ trợ, đồng thời đo các field thực được tải.
2. Dùng `MongoTemplate` hoặc aggregation `$project` để tạo đúng cấu trúc kết quả và ánh xạ vào kiểu phù hợp.
3. Trả DTO phẳng chứa `supplierName` rồi ghép thành cấu trúc API ở tầng ứng dụng.
4. Nếu đã tải entity đầy đủ, dùng mapper thủ công; chấp nhận rằng cách này không nhất thiết giảm I/O.

### 10.2. @Field và mapping tên BSON

Khi entity khai báo:

~~~java
@Field("display_name")
private String name;
~~~

thì field BSON thực sự là `display_name`, nhưng property Java vẫn là `name`. Constructor DTO dùng `name` cần được đối chiếu với metadata mapping của entity và loại projection được chọn; không nên đổi constructor thành `display_name` chỉ vì collection dùng snake_case.

Đặc biệt với JSON query raw, DTO tùy chỉnh hoặc aggregation `$project`, **tên field trong output** có thể khác tên field của entity. Nếu record có component `name` nhưng kết quả pipeline trả `display_name`, cần chọn/mapping/alias về tên phù hợp hoặc converter được kiểm thử.

### 10.3. Field thiếu, null và primitive

DTO có `long priceVnd` không thể nhận `null` như một reference type. Nếu projection không trả `priceVnd`, document cũ thiếu field hoặc converter không phù hợp, việc materialize có thể thất bại hoặc gây giá trị không như mong muốn tùy đường mapping. Với dữ liệu tùy chọn, cân nhắc `Long` hoặc record có chính sách default rõ ràng.

Với property nhạy cảm, **không chỉ dựa vào DTO để bảo vệ thông tin**:

- Chỉ sử dụng DTO đã được cho phép tại từng API và kiểm tra quyền trước truy vấn.
- Kiểm tra field projection thực sự gửi xuống MongoDB để không tải thừa dữ liệu nhạy cảm.
- Đừng log toàn bộ entity/document trước khi map sang DTO.
- Với hệ thống đa tenant, đặt điều kiện `tenantId`/quyền truy cập **trong query**, không chỉ lọc sau khi trả dữ liệu.

## 11. Kiểm tra BSON projection và dữ liệu trả về

Một test chỉ xác nhận JSON response có ba field **chưa chứng minh** MongoDB đã trả đúng ba field. Nên kiểm tra ba tầng:

| Tầng | Điều cần xác minh | Kỹ thuật |
|---|---|---|
Repository/service | Kiểu `ProductCardRecord` và giá trị chính xác | Integration test repository |
MongoDB command | `filter`, `projection`, `sort`, `limit` được gửi như dự kiến | Java Driver `CommandListener` hoặc profiler an toàn |
Server performance | Số key/documents examined, index được chọn, lượng dữ liệu trả | `explain("executionStats")` và metrics |

### 11.1. Integration test cho record và class DTO

Trong Spring Boot 3.x, `@DataMongoTest` hỗ trợ test slice Spring Data MongoDB, nhưng **không tự chạy MongoDB server**. Hãy cung cấp MongoDB thực trong môi trường test, chẳng hạn Testcontainers, với collection/database được cô lập.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class CatalogProductProjectionTest {
    @Autowired
    CatalogProductRepository products;

    @BeforeEach
    void setUp() {
        products.deleteAll();
        products.save(new CatalogProduct(
                "prd-101",
                "Bình nước 500 ml",
                "drinkware",
                129000,
                42,
                "ACTIVE",
                "Không công khai ghi chú này"));
    }

    @Test
    void recordProjectionContainsPublicFields() {
        ProductCardRecord card = products.findByStatus("ACTIVE")
                .get(0);

        assertThat(card.id()).isEqualTo("prd-101");
        assertThat(card.name()).isEqualTo("Bình nước 500 ml");
        assertThat(card.priceVnd()).isEqualTo(129000);
    }

    @Test
    void classDtoAndDynamicProjectionReadExpectedValues() {
        ProductCardDto cheapest =
                products.findTop10ByStatusOrderByPriceVndAsc("ACTIVE")
                        .get(0);
        assertThat(cheapest.getName()).isEqualTo("Bình nước 500 ml");

        ProductCardRecord dynamic =
                products.findByCategory(
                        "drinkware", ProductCardRecord.class).get(0);
        assertThat(dynamic.id()).isEqualTo("prd-101");

        CatalogProduct entity =
                products.findByCategory(
                        "drinkware", CatalogProduct.class).get(0);
        assertThat(entity.getInternalNote())
                .isEqualTo("Không công khai ghi chú này");
    }
}
~~~

Test này xác minh **construction và mapping kết quả**, chưa khẳng định field selection ở mức driver. Không chạy `deleteAll` trên database chung với những test song song; cô lập dữ liệu hoặc dọn theo ID riêng.

### 11.2. Kiểm tra command projection

MongoDB Java Driver có `CommandListener` nhận `CommandStartedEvent`. Trong môi trường test, có thể dùng `MongoClientSettingsBuilderCustomizer` để đăng ký listener với client do Spring Boot tạo, rồi lọc các lệnh `find` tới `catalog_products`.

Một lệnh `find` có thể mang:

~~~json
{
  "find": "catalog_products",
  "filter": { "status": "ACTIVE" },
  "projection": {
    "_id": 1,
    "name": 1,
    "priceVnd": 1
  }
}
~~~

Đây là **minh họa**. Khi capture, kiểm tra *BSON document thật*: driver có thể tạo biểu thức hoặc cú pháp khác nhưng cùng hiệu quả. Nếu lệnh không có `projection`, nghĩa là truy vấn đó có thể đang yêu cầu đủ field dù code Java trả DTO. Khi ấy cần dùng query field selection tường minh hoặc điều chỉnh đường truy vấn, và đo lại.

Không bật log toàn bộ command production nếu filter chứa ID người dùng, email, thông tin thanh toán hoặc dữ liệu nhạy cảm. Hạn chế capture trong test, tránh giữ listener chứa dữ liệu trên nhiều test/instance.

### 11.3. Kiểm tra index và lượng dữ liệu

Ví dụ một index phục vụ lọc `status` và sắp xếp theo giá:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, priceVnd: 1 },
  { name: "idx_status_price" }
);
~~~

Đánh giá một truy vấn có projection:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE" },
  { _id: 1, name: 1, priceVnd: 1 }
).sort({ priceVnd: 1, _id: 1 })
 .explain("executionStats");
~~~

Projection **không tự bảo đảm covered query**. Để tránh fetch document gốc chỉ dựa vào index, các field lọc, sort và projection cần được index phù hợp bao phủ theo khả năng của MongoDB, gồm cả `_id` nếu được trả; một compound index nhỏ chỉ có `status` và `priceVnd` chưa đủ để cover `name`. Việc tạo index rộng hơn tăng chi phí ghi và dung lượng, nên chỉ làm khi workload thực sự được lợi.

## 12. DTO trong reactive access

Với `ReactiveMongoRepository` và `ReactiveMongoTemplate`, projection có thể được biểu diễn bởi các publisher `Flux`/`Mono` khi loại truy vấn và kiểu projection được hỗ trợ:

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Flux<ProductCardRecord> findByStatus(String status);
}
~~~

Đọc ví dụ:

~~~java
Flux<ProductCardRecord> activeCards =
        reactiveProducts.findByStatus("ACTIVE");
~~~

Trong ví dụ, `reactiveProducts` là bean kiểu `ReactiveCatalogProductRepository`. Publisher được subscribe bởi tầng gọi phù hợp; không gọi `block()` trên event-loop chỉ để ép DTO trở thành dữ liệu đồng bộ.

**Projection không thay đổi bảo đảm nhất quán của database**. Nếu sản phẩm đổi sau lần đọc, record đã được tạo không tự cập nhật. Việc sử dụng DTO/reactive không giải quyết transaction, read concern, replica lag hay tranh chấp ghi; các chủ đề đó phải được xử lý ở ranh giới nghiệp vụ tương ứng.

## 13. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
Trả entity đầy đủ từ API dù chỉ cần vài field | Lộ thêm state, phụ thuộc schema, payload lớn | Dùng DTO được kiểm soát, kiểm tra quyền |
Nghĩ trả record đồng nghĩa MongoDB chỉ trả ba field | Tải quá nhiều dữ liệu dù response gọn | Kiểm tra `projection` trong command thật |
Constructor DTO có tham số khác tên property Java | Spring Data không chọn/mapping đúng field | Thống nhất tên, metadata và test |
Có nhiều constructor nhưng không chỉ rõ constructor materialization | Chọn sai hoặc lỗi khi tạo DTO | `@PersistenceCreator` hoặc một constructor rõ ràng |
Quên `-parameters` cho class DTO dùng constructor binding | Không có metadata tên tham số | Cấu hình compile phù hợp và test |
Nhầm getter record với JavaBean getter | Code gọi `getName()` trên record bị lỗi | Dùng `name()` với record, `getName()` với class DTO |
Projection loại field constructor bắt buộc | Record/class tạo lỗi hoặc dữ liệu thiếu | Giữ field cần thiết hoặc thiết kế nullable/default |
Cho rằng class-based DTO tự tạo nested projection mọi tầng | Mapping lỗi hoặc tải nested document không mong muốn | Interface nested projection, aggregation hoặc mapper tường minh |
Dùng DTO chưa đủ field để `save` lại entity | Mất state hoặc cập nhật sai | Dùng entity/update với kiểm soát concurrency |
Cho rằng Java record bất biến sâu | List/map lồng vẫn có thể bị sửa | Sao chép phòng vệ khi cần |
Aggregation `$group` trả `_id` nhưng DTO chờ tên field khác | DTO nhận null hoặc lỗi conversion | Dùng `$project` để alias field đầu ra |
Gắn DTO làm lựa chọn tùy ý từ HTTP input | Client yêu cầu kiểu chứa trường nội bộ | Server kiểm soát danh sách projection được phép |
Chạy test DTO không có MongoDB thật | Không kiểm chứng BSON, driver và query behavior | Testcontainers/MongoDB cô lập và command capture |

## 14. Bài tập vận dụng

**Bài 1 — Class DTO.** Tạo `ProductCardDto` với một constructor chứa `id`, `name`, `priceVnd` và một constructor tiện dụng. Đánh dấu `@PersistenceCreator` trên constructor phù hợp, khai báo phương thức repository trả `List<ProductCardDto>` và kiểm chứng ba giá trị được gán đúng.

**Bài 2 — Java record.** Chuyển DTO ở bài 1 thành `ProductCardRecord`. So sánh lượng mã, accessor, bất biến và hành vi `equals`. Bổ sung một component dạng list; thử thay đổi list bên ngoài sau khi tạo record và đề xuất defensive copy.

**Bài 3 — Dynamic projection.** Khai báo `<T> List<T> findByCategory(String category, Class<T> type)`. Gọi với entity, class DTO và record; giải thích trường hợp nào cần trạng thái đầy đủ và vì sao không expose `Class<T>` trực tiếp qua API công khai.

**Bài 4 — Xem BSON được gửi.** Dùng MongoDB CommandListener trong test để quan sát `find` khi gọi repository trả record. Ghi lại `filter`, `projection` và kích thước payload. Thử MongoTemplate fluent projection và so sánh kết quả; đừng suy đoán mức tối ưu chỉ từ kiểu trả về.

**Bài 5 — Mapping field khác tên.** Thêm `@Field("display_name")` lên property `name` của entity, chuẩn bị dữ liệu MongoDB thực. Kiểm tra record projection, constructor DTO và aggregation với `$project`. Viết migration hoặc alias cần thiết nếu dữ liệu cũ vẫn lưu `name`.

**Bài 6 — Report bằng aggregation.** Dùng `$match`, `$group` và `$project` để tính tồn kho theo category; trả `CategoryStockReport`. Thử category thiếu/null, kiểm tra kiểu tổng và số document theo kết quả.

**Bài 7 — Hiệu năng.** Tạo dữ liệu sản phẩm có trường ghi chú lớn, so sánh: (a) tải entity rồi map thủ công, (b) repository DTO projection, (c) MongoTemplate với field selection. Đo số byte truyền, thời gian truy vấn, thời gian conversion, plan và index, rồi quyết định phương án.

## 15. Ghi nhớ

Trong **Spring Data MongoDB**, **class-based DTO projection** dựa trên constructor và tên property được Spring Data xác định; `@PersistenceCreator` hữu ích khi class có nhiều constructor. **Java record** là lựa chọn gọn cho DTO bất biến nông, có canonical constructor, accessor và semantics theo giá trị.

`MongoRepository` có thể trả DTO/record từ truy vấn suy diễn và dynamic projection. `MongoTemplate` cung cấp điều kiện/field selection linh hoạt; aggregation `$project`/`$group` giúp tạo một **hình dạng kết quả mới** trước khi ánh xạ sang DTO.

Hãy phân biệt **DTO gọn trong Java/API** với **projection BSON thực sự tiết kiệm dữ liệu đọc**. Kiểm chứng constructor metadata, field BSON, dữ liệu null/missing, nested mapping, sort/pagination và query plan bằng integration test. Không dùng DTO để thay thế kiểm soát quyền truy cập hay để ghi đè entity chưa đầy đủ.
