# Kiểm tra từ khóa được hỗ trợ cùng BSON sinh ra

## 1. Vì sao không chỉ nhìn tên phương thức?

Trong chương **Truy vấn suy diễn** của **Spring Data MongoDB**, repository có thể suy ra truy vấn từ tên phương thức Java mà không cần tự viết câu lệnh MongoDB. Chẳng hạn `findByStatusAndStockGreaterThanEqual` diễn đạt một điều kiện lọc bằng tên property và toán tử so sánh. Cơ chế này giúp triển khai các truy vấn CRUD thường gặp nhanh và dễ đọc.

Tuy vậy, một phương thức trông đúng ngữ pháp Java chưa chắc tạo ra **BSON filter có ý nghĩa mà nghiệp vụ mong muốn**. Cần phân biệt:

- **Từ khóa được bộ phân tích tên phương thức hỗ trợ**: `And`, `Or`, `GreaterThan`, `In`, `Containing`, `IsNull`, `OrderBy` và các từ khóa khác.
- **Property Java được nhận diện**: `name`, `stock` hay `supplier.countryCode`; property phải tồn tại trong model.
- **Trường BSON thực tế**: `display_name`, `stock_qty`, `supplier.country_code` có thể khác tên property vì `@Field`.
- **Lệnh MongoDB được thực thi**: filter, sort, limit, skip, projection và đôi khi là lệnh khác nhau cho `exists` hoặc `count`.
- **Tính đúng đắn và hiệu năng**: null/missing, regex, mảng, index, collation, paging và đọc đồng thời ảnh hưởng kết quả.

Trong bài này, chúng ta sẽ lập bảng đối chiếu *tên phương thức → ý nghĩa → BSON tương đương*, rồi **quan sát lệnh thực tế** bằng integration test. Điều đó phù hợp với mục tiêu của Spring Data MongoDB: sử dụng repository cho truy vấn thông thường, biết khi nào cần `MongoTemplate` hoặc aggregation, và chẩn đoán được truy vấn chậm hoặc sai.

> Ví dụ hướng đến Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Các đoạn BSON trong bảng là **minh họa ngữ nghĩa**; driver có thể mã hóa regex, tham số và lệnh đếm/tồn tại khác cách viết Extended JSON dưới đây. Hãy dùng command monitoring hoặc MongoDB profiler trên đúng phiên bản dự án để kiểm tra BSON thực sự được gửi.

## 2. Dữ liệu mẫu và quy tắc ánh xạ

Để nhất quán, ta dùng collection `catalog_products`. Một document có hình dạng BSON như sau (lược bỏ metadata `_class`):

~~~json
{
  "_id": "prd-101",
  "sku": "BOTTLE-500",
  "display_name": "Bình nước giữ nhiệt",
  "status": "ACTIVE",
  "stock_qty": 12,
  "priceVnd": 129000,
  "featured": true,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" },
  "tags": ["drinkware", "outdoor"],
  "supplier": {
    "name": "Nhà cung cấp A",
    "country_code": "VN"
  }
}
~~~

Field `archivedAt` chưa tồn tại trong document trên; điều này sẽ quan trọng khi xét `IsNull` và `Exists`.

**SupplierInfo.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.mapping.Field;

public record SupplierInfo(
        String name,
        @Field("country_code") String countryCode) {
}
~~~

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String sku,
        @Field("display_name") String name,
        String status,
        @Field("stock_qty") int stock,
        long priceVnd,
        boolean featured,
        Instant createdAt,
        Instant archivedAt,
        List<String> tags,
        SupplierInfo supplier) {
}
~~~

Mọi ví dụ repository phía dưới đặt trong package `com.example.catalog`, nơi Spring Boot có thể quét entity và repository theo cấu hình phù hợp. `@MongoId(FieldType.STRING)` giữ `_id` ở BSON String; không nhầm một chuỗi 24 ký tự hex với BSON ObjectId.

| Property trong Java | Trường BSON được lưu |
|---|---|
| `id` | `_id` |
| `sku` | `sku` |
| `name` | `display_name` |
| `stock` | `stock_qty` |
| `status` | `status` |
| `priceVnd` | `priceVnd` |
| `supplier.countryCode` | `supplier.country_code` |
| `tags` | `tags` |
| `archivedAt` | `archivedAt` |

Spring Data ánh xạ **đường dẫn property Java sang đường dẫn BSON** khi repository tạo truy vấn dựa trên entity. Nếu dùng MongoDB shell hoặc driver với raw BSON, phải viết tên field thực tế. Trong bảng sau, dấu `...` đại diện tham số và những phương thức trả dữ liệu được giả định gọi trên `CatalogProductRepository`.

## 3. Bộ phân tích tên phương thức hoạt động như thế nào?

Ví dụ tên phương thức:

~~~java
List<CatalogProduct> findByStatusAndStockGreaterThanEqual(
        String status, int minimumStock);
~~~

Có thể đọc thành:

1. `find`: chọn thao tác truy vấn trả entity.
2. `By`: phân cách phần mô tả truy vấn với phần điều kiện.
3. `Status`: property `status`.
4. `And`: phép kết hợp logic giữa các điều kiện.
5. `StockGreaterThanEqual`: property `stock` với toán tử so sánh `>=`.
6. Hai tham số Java được gán lần lượt cho hai điều kiện.

Điều kiện MongoDB minh họa:

~~~json
{
  "status": "ACTIVE",
  "stock_qty": { "$gte": 5 }
}
~~~

Bộ phân tích Spring Data không đọc tên field BSON từ tên phương thức. Nó nhận diện property Java thông qua metadata entity, sau đó tầng MongoDB mapping tạo trường BSON tương ứng. Vì vậy:

~~~java
// Đúng: dùng property Java được đặt tên là name.
List<CatalogProduct> findByName(String name);
~~~

Filter tương đương trên MongoDB là `{ "display_name": "..." }`, **không phải** `{ "name": "..." }`. Một phương thức như `findByDisplay_name` không phải cách diễn đạt tên BSON và có thể không được parser nhận diện như mong đợi.

Nếu tên property sai hoặc các phần tử điều kiện không phân tích được, repository có thể thất bại khi khởi tạo hoặc khi truy vấn được khởi tạo ở chế độ lazy. Lỗi phổ biến liên quan `PropertyReferenceException`. Không nên coi ứng dụng khởi động thành công là bằng chứng mọi phương thức đều đã chạy đúng với dữ liệu thực.

## 4. Các nhóm từ khóa thường dùng và BSON tương đương

Bảng dưới đây trình bày **filter minh họa**. Trong lệnh thật, thứ tự trường trong BSON không quan trọng đối với các điều kiện `AND` độc lập; driver có thể chuẩn hóa biểu thức theo cách khác. Đặc biệt, regex có thể được biểu diễn thành BSON RegularExpression chứ không nhất thiết là hai field `$regex` và `$options` trong Extended JSON.

### 4.1. Bằng nhau, phủ định và so sánh

| Phương thức suy diễn | Ý nghĩa | Filter BSON tương đương |
|---|---|---|
| `findBySku("BOTTLE-500")` | Bằng nhau | `{ "sku": "BOTTLE-500" }` |
| `findBySkuIs("BOTTLE-500")` | Tương đương equals | `{ "sku": "BOTTLE-500" }` |
| `findBySkuEquals("BOTTLE-500")` | Tương đương equals | `{ "sku": "BOTTLE-500" }` |
| `findBySkuNot("X")` | Khác giá trị | `{ "sku": { "$ne": "X" } }` |
| `findByStockGreaterThan(5)` | Lớn hơn | `{ "stock_qty": { "$gt": 5 } }` |
| `findByStockGreaterThanEqual(5)` | Lớn hơn hoặc bằng | `{ "stock_qty": { "$gte": 5 } }` |
| `findByStockLessThan(5)` | Nhỏ hơn | `{ "stock_qty": { "$lt": 5 } }` |
| `findByStockLessThanEqual(5)` | Nhỏ hơn hoặc bằng | `{ "stock_qty": { "$lte": 5 } }` |
| `findByStatusAndStockGreaterThanEqual("ACTIVE", 5)` | Kết hợp AND | `{ "status": "ACTIVE", "stock_qty": { "$gte": 5 } }` |

Mỗi từ khóa thay đổi **toán tử** trên property phía trước nó, không thay đổi tên field. Với giá trị ngày/giờ `Instant`, các phép `Before` và `After` có thể diễn đạt so sánh theo thời điểm; cần kiểm tra cách chuyển sang BSON Date và độ chính xác mili giây.

### 4.2. Tập giá trị, boolean và null

| Phương thức | Diễn giải | Filter BSON tương đương |
|---|---|---|
| `findByStatusIn(List.of("ACTIVE", "PENDING"))` | Nằm trong tập | `{ "status": { "$in": ["ACTIVE", "PENDING"] } }` |
| `findByStatusNotIn(List.of("DELETED", "BLOCKED"))` | Ngoài tập | `{ "status": { "$nin": ["DELETED", "BLOCKED"] } }` |
| `findByFeaturedTrue()` | Boolean true | `{ "featured": true }` |
| `findByFeaturedFalse()` | Boolean false | `{ "featured": false }` |
| `findByArchivedAtIsNull()` | Giá trị null hoặc field không có | `{ "archivedAt": null }` |
| `findByArchivedAtIsNotNull()` | Khác null | `{ "archivedAt": { "$ne": null } }` |
| `findByArchivedAtExists(true)` | Field BSON tồn tại | `{ "archivedAt": { "$exists": true } }` |
| `findByArchivedAtExists(false)` | Field BSON không tồn tại | `{ "archivedAt": { "$exists": false } }` |

**Null không đồng nghĩa field thiếu.** Trong MongoDB, filter bằng `null` thường khớp cả document có field BSON null lẫn document không có field. `$exists: true` khớp cả giá trị null nếu khóa có mặt. Nếu cần **chỉ null thực sự**, có thể phải viết truy vấn bổ sung, chẳng hạn kết hợp `$exists` với `null` theo đúng semantics server. Đừng dựa vào tên phương thức `IsNull` để suy ra “chỉ những record có khóa và giá trị null”.

Đối với `$ne` và `$nin`, cần kiểm tra chính xác cách MongoDB xử lý các field thiếu; toán tử phủ định có thể trả cả document không có field đối với giá trị so sánh không-null. Khi semantics missing/null quan trọng, hãy viết integration test với ba document: **thiếu field, field null, field có giá trị**.

### 4.3. Chuỗi, regex và so khớp không phân biệt hoa/thường

| Phương thức | Ý nghĩa | Filter BSON minh họa |
|---|---|---|
| `findByNameStartingWith("Bình")` | Bắt đầu bằng | `{ "display_name": { "$regex": "^Bình" } }` |
| `findByNameEndingWith("nhiệt")` | Kết thúc bằng | `{ "display_name": { "$regex": "nhiệt$" } }` |
| `findByNameContaining("nước")` | Có chuỗi con | `{ "display_name": { "$regex": ".*nước.*" } }` |
| `findByNameIgnoreCase("BÌNH NƯỚC GIỮ NHIỆT")` | So khớp tên, bỏ qua hoa/thường | Regex có neo đầu/cuối và option `i` |
| `findByNameContainingIgnoreCase("NƯỚC")` | Chứa chuỗi, bỏ qua hoa/thường | Regex tìm chuỗi con với option `i` |
| `findByNameRegex("^Bình")` | Dùng regex do caller cung cấp | `{ "display_name": { "$regex": "^Bình" } }` |

Đây là biểu diễn **ý nghĩa tìm kiếm**, không phải cam kết rằng driver luôn gửi chính xác chuỗi `.*term.*` hoặc `^term`. Spring Data có thể escape ký tự đặc biệt của đầu vào cho các từ khóa tìm chuỗi, trong khi `Regex` thường xem tham số như mẫu regex. Hãy xác minh BSON thực tế trước khi dựa vào một cấu trúc tối ưu hóa cụ thể.

**Các lưu ý quan trọng:**

- `Containing` đối với **chuỗi** thường dựa trên regex, **không** có nghĩa là full-text search hay tìm kiếm có phân tích ngôn ngữ.
- Regex không neo đầu, có `.*` đầu mẫu, hoặc có option không phân biệt hoa/thường có thể không tận dụng được index B-tree theo cách mong muốn; đo bằng `explain`.
- Với dữ liệu người dùng, không truyền regex tùy ý khi không cần. Regex rất phức tạp có thể tốn CPU; cần giới hạn độ dài, xác thực input và timeout phù hợp.
- `IgnoreCase` và **collation** không phải cùng một cơ chế. Nếu muốn so sánh/sắp xếp văn bản theo quy tắc ngôn ngữ hoặc tận dụng collation index, hãy chọn giải pháp rõ ràng thay vì mặc định regex `i` đáp ứng mọi yêu cầu.
- Với số lượng tài liệu lớn và tìm kiếm từ ngữ, có thể cần text index hoặc công cụ tìm kiếm chuyên biệt; derived `Containing` không thay thế giải pháp tìm kiếm có ranking.

### 4.4. Đường dẫn nested property và mảng

| Phương thức | Field BSON dự kiến | Filter minh họa |
|---|---|---|
| `findBySupplier_CountryCode("VN")` | `supplier.country_code` | `{ "supplier.country_code": "VN" }` |
| `findBySupplierName("A")` | `supplier.name` | `{ "supplier.name": "A" }` |
| `findByTagsIn(List.of("outdoor", "travel"))` | `tags` | `{ "tags": { "$in": ["outdoor", "travel"] } }` |
| `findByIdIn(List.of("prd-101", "prd-102"))` | `_id` | `{ "_id": { "$in": ["prd-101", "prd-102"] } }` |

Dấu gạch dưới trong `Supplier_CountryCode` dùng để **chỉ rõ ranh giới đường dẫn property** khi Spring Data phân tích tên phương thức. Nó không biểu diễn dấu gạch dưới của field BSON; `@Field("country_code")` mới là nơi khai báo tên field lưu.

Khi `tags` là mảng String, `$in` khớp document nếu **ít nhất một phần tử** thuộc tập cần tìm. Điều này khác với yêu cầu “chứa đồng thời mọi tag”, vốn cần một toán tử/logic truy vấn khác. Với mảng **document con**, nếu nhiều điều kiện phải cùng đúng trên một phần tử, dùng `$elemMatch` qua `MongoTemplate` hoặc `@Query` thích hợp; không suy diễn rằng nhiều điều kiện dot path độc lập tự ràng buộc vào cùng phần tử mảng.

### 4.5. Khoảng giá trị và thứ tự ưu tiên của AND/OR

Phương thức có `Between` được hỗ trợ với các kiểu dữ liệu so sánh phù hợp, nhưng **không nên đoán ranh giới bao gồm hai đầu hay không** chỉ từ chữ “between”. Hãy kiểm tra BSON thực tế và test các giá trị đúng tại biên, nhất là khi dữ liệu là thời điểm.

Khi yêu cầu rõ “giá từ 100.000 đến 200.000, bao gồm cả hai đầu”, tên phương thức tường minh sẽ an toàn hơn:

~~~java
List<CatalogProduct>
findByPriceVndGreaterThanEqualAndPriceVndLessThanEqual(
        long minimum, long maximum);
~~~

Filter tương đương:

~~~json
{
  "priceVnd": {
    "$gte": 100000,
    "$lte": 200000
  }
}
~~~

Phương thức có `And` và `Or` không hỗ trợ **ngoặc biểu thức tùy ý** như một ngôn ngữ truy vấn. Đặc biệt, khi trộn nhiều nhóm điều kiện `AND/OR`, cách parser nhóm điều kiện có thể khác ý định nghiệp vụ. Ví dụ muốn biểu diễn:

~~~text
status = "ACTIVE" AND (featured = true OR stock >= 10)
~~~

Thay vì đặt tên phương thức dài rồi đoán precedence, dùng `MongoTemplate` để chỉ rõ nhóm:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> activeFeaturedOrWellStocked(
        MongoTemplate mongo) {
    Criteria condition = new Criteria().andOperator(
            Criteria.where("status").is("ACTIVE"),
            new Criteria().orOperator(
                    Criteria.where("featured").is(true),
                    Criteria.where("stock").gte(10)));

    return mongo.find(Query.query(condition), CatalogProduct.class);
}
~~~

Với `CatalogProduct.class`, Spring Data mapping `stock` thành `stock_qty`. Filter MongoDB tương đương có nhóm `$and` chứa nhánh `status` và một `$or` của `featured`/`stock_qty`. Đây là lựa chọn dễ kiểm thử hơn một tên repository khó đọc.

## 5. Repository mẫu tổng hợp các từ khóa

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    List<CatalogProduct> findByStatus(String status);

    List<CatalogProduct> findByStatusAndStockGreaterThanEqual(
            String status, int minimumStock);

    List<CatalogProduct> findByPriceVndGreaterThanEqualAndPriceVndLessThanEqual(
            long minimum, long maximum);

    List<CatalogProduct> findByNameContainingIgnoreCase(String text);

    List<CatalogProduct> findBySupplier_CountryCode(String countryCode);

    List<CatalogProduct> findByTagsIn(Collection<String> tags);

    List<CatalogProduct> findByArchivedAtIsNull();

    List<CatalogProduct> findByArchivedAtExists(boolean exists);

    List<CatalogProduct> findByFeaturedTrue();

    boolean existsBySku(String sku);

    long countByStatus(String status);

    List<CatalogProduct> findTop5ByStatusOrderByCreatedAtDesc(String status);

    List<CatalogProduct> findByStatus(String status, Sort sort);

    Page<CatalogProduct> findByStatus(String status, Pageable pageable);
}
~~~

Đây là các phương thức suy diễn từ tên property Java, không phải câu SQL. Mỗi method phải có **chữ ký và kiểu trả về phù hợp**: `existsBy...` trả boolean, `countBy...` trả số, `findBy...` có thể trả entity/danh sách/Page. Việc repository chứa một phương thức đúng ngữ pháp không chứng minh filter của nó có index thích hợp.

Chú ý `@MongoId(FieldType.STRING)` giúp map `_id` nhất quán. Nếu thay bằng `@Id String`, Spring Data MongoDB có thể chuyển các chuỗi ID mang dạng ObjectId hợp lệ sang BSON ObjectId; đây là lý do cần kiểm tra kiểu BSON khi kết quả truy vấn theo ID gây bất ngờ.

## 6. Từ khóa điều khiển kết quả: OrderBy, Top, First, Sort và Pageable

Tên phương thức không chỉ sinh **filter** mà còn có thể tạo **sort và limit**:

~~~java
List<CatalogProduct> findTop5ByStatusOrderByCreatedAtDesc(String status);
~~~

Ý nghĩa gần với:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1 })
  .limit(5);
~~~

Các từ khóa `Top` và `First` cho phép giới hạn số kết quả; `OrderBy...Asc/Desc` mô tả thứ tự cố định. Khi không có sort xác định, một truy vấn giới hạn N phần tử **không bảo đảm cùng N phần tử** giữa các lần gọi.

Nếu nhiều sản phẩm có cùng `createdAt`, hãy thêm tiêu chí thứ hai duy nhất (chẳng hạn `id`) để thứ tự ổn định cho pagination, với ý nghĩa:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(5);
~~~

Với Spring Data, có thể truyền `Sort` động hoặc `Pageable`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));

Page<CatalogProduct> page = repository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20, sort));
~~~

`Sort` ở đây dùng **property Java**; `id` sẽ được map đến `_id`. `PageRequest.of(0, 20, ...)` lấy trang đầu với kích thước 20. Với `Page<T>`, Spring Data có thể cần thêm truy vấn đếm để tính tổng số kết quả; không nên nhìn một lần gọi repository rồi kết luận chỉ có một round trip.

Nếu không cần tổng số bản ghi, cân nhắc return type `Slice<T>` hoặc cách phân trang phù hợp để giảm chi phí đếm; việc áp dụng cụ thể phải kiểm tra khả năng hỗ trợ ở phiên bản repository và chữ ký phương thức. Với tập dữ liệu lớn và trang sâu, `skip` tăng chi phí; seek/keyset pagination hoặc truy vấn theo cursor có thể hợp lý hơn.

**Kiểm tra sort thật:** trong MongoDB command, `sort` thường là document riêng bên cạnh `filter`, không phải một điều kiện nằm trong `filter`. Tương tự `limit` và `skip` có thể là trường của lệnh `find`.

## 7. Từ khóa tồn tại, đếm và xóa có semantics riêng

Ba phương thức:

~~~java
boolean existsBySku(String sku);
long countByStatus(String status);
long deleteByStatus(String status);
~~~

diễn đạt ba mục tiêu khác nhau:

| Mục tiêu | Điều kiện minh họa | Điều cần biết khi quan sát lệnh |
|---|---|---|
`existsBySku("BOTTLE-500")` | `{ "sku": "BOTTLE-500" }` | Có thể dùng truy vấn tối ưu chỉ cần biết có ít nhất một kết quả; không cần tải entity |
`countByStatus("ACTIVE")` | `{ "status": "ACTIVE" }` | Dùng lệnh hoặc pipeline đếm tùy phiên bản; kết quả không phải khóa dữ liệu |
`deleteByStatus("DELETED")` | `{ "status": "DELETED" }` | Là thao tác **ghi xóa dữ liệu**, cần quyền và điều kiện bảo vệ |

Trong Spring Data MongoDB, ý nghĩa `deleteBy...` có thể khác nhau theo **kiểu trả về** (ví dụ trả số document bị xóa so với trả danh sách entity đã bị xóa, khi được hỗ trợ). Không suy luận chi phí hoặc số lệnh chỉ từ chữ `delete`: nếu nghiệp vụ cần xóa hàng loạt, hãy kiểm thử hành vi thực tế của chữ ký repository, transaction và callback.

Không dùng phương thức xóa suy diễn chỉ để thử “BSON sinh ra là gì” trên dữ liệu dùng chung. Dùng database test và các bản ghi có thể xóa an toàn. Với nghiệp vụ xóa có điều kiện trạng thái/version, `MongoTemplate.remove(...)` với query rõ ràng hoặc một quy trình phù hợp có thể dễ kiểm soát hơn.

**`existsBy...` không bảo đảm có thể tạo mới.** Hai request có thể cùng nhận kết quả `false` rồi đồng thời insert; unique index và thao tác insert/conditional update mới là lớp bảo vệ ở thời điểm ghi.

## 8. Cách kiểm chứng BSON được gửi thực sự

Đọc bảng từ khóa giúp dự đoán truy vấn, nhưng yêu cầu “kiểm tra từ khóa được hỗ trợ cùng BSON sinh ra” cần đi xa hơn **chỉ dự đoán**. Có ba tầng xác minh bổ sung cho nhau:

1. **Kiểm tra kết quả của repository**: test trên dữ liệu có các giá trị biên, null, missing, chữ hoa/thường và nested fields.
2. **Quan sát command gửi tới MongoDB**: thông qua MongoDB Java Driver `CommandListener` hoặc cơ chế theo dõi query được bật trong môi trường kiểm thử.
3. **Phân tích query plan**: dùng `explain("executionStats")` và dữ liệu đại diện để xem filter, index, số key/document được duyệt.

### 8.1. Integration test với dữ liệu thực

Spring Boot 3.x có `@DataMongoTest` để nạp repository và mapping. Annotation này **không tự khởi động MongoDB**; cần kết nối database dành riêng cho test, ví dụ MongoDB trong Testcontainers.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class CatalogProductDerivedQueryTest {
    @Autowired
    CatalogProductRepository products;

    @Test
    void queriesMappedFieldsAndNestedProperty() {
        products.deleteAll();
        products.save(new CatalogProduct(
                "prd-101", "BOTTLE-500", "Bình nước giữ nhiệt",
                "ACTIVE", 12, 129000L, true,
                Instant.parse("2026-11-20T08:00:00Z"),
                null,
                List.of("drinkware", "outdoor"),
                new SupplierInfo("Nhà cung cấp A", "VN")));

        assertThat(products.findByStatusAndStockGreaterThanEqual(
                "ACTIVE", 10)).extracting(CatalogProduct::id)
                .containsExactly("prd-101");

        assertThat(products.findBySupplier_CountryCode("VN"))
                .extracting(CatalogProduct::sku)
                .contains("BOTTLE-500");

        assertThat(products.findByNameContainingIgnoreCase("NƯỚC"))
                .hasSize(1);

        assertThat(products.findByArchivedAtIsNull())
                .extracting(CatalogProduct::id)
                .contains("prd-101");
    }
}
~~~

Test xác minh kết quả và cách mapping ở mức integration. Nếu chạy test song song hoặc chia sẻ collection, `deleteAll()` có thể gây ảnh hưởng lẫn nhau; nên cấp database/collection riêng hoặc quản lý vòng đời dữ liệu test cô lập.

### 8.2. Ghi nhận CommandStartedEvent trong môi trường test

MongoDB Java Driver hỗ trợ `CommandListener`. Khi kích hoạt trên client qua `MongoClientSettingsBuilderCustomizer` (Spring Boot 3.x), listener có thể nhìn thấy command `find` và BSON `filter` do repository tạo. Phương án này hữu ích khi cần xác nhận `stock` đã được đổi thành `stock_qty`, `name` thành `display_name`, hoặc sort/limit được thêm đúng.

Ví dụ cấu hình **chỉ để thử nghiệm**:

~~~java
package com.example.catalog;

import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.bson.BsonDocument;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class MongoCommandCaptureConfig {

    @Bean
    FindCommandCapture findCommandCapture() {
        return new FindCommandCapture();
    }

    @Bean
    MongoClientSettingsBuilderCustomizer captureMongoFind(
            FindCommandCapture capture) {
        return settings -> settings.addCommandListener(capture);
    }

    static final class FindCommandCapture implements CommandListener {
        final List<BsonDocument> commands = new CopyOnWriteArrayList<>();

        @Override
        public void commandStarted(CommandStartedEvent event) {
            if ("find".equals(event.getCommandName())) {
                commands.add(BsonDocument.parse(
                        event.getCommand().toJson()));
            }
        }

        @Override
        public void commandSucceeded(CommandSucceededEvent event) {}

        @Override
        public void commandFailed(CommandFailedEvent event) {}

        void clear() {
            commands.clear();
        }
    }
}
~~~

Đoạn này không ghi ra log và có danh sách thread-safe để tránh lỗi dữ liệu khi listener nhận nhiều command đồng thời. Nếu ứng dụng chạy nhiều test hoặc collection, cần lọc thêm theo tên collection và phạm vi test, tránh lấy nhầm command từ hoạt động nền.

Ví dụ kiểm tra command với test riêng:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;

@DataMongoTest
@Import(MongoCommandCaptureConfig.class)
class DerivedQueryBsonTest {
    @Autowired CatalogProductRepository products;
    @Autowired MongoCommandCaptureConfig.FindCommandCapture capture;

    @Test
    void recordsMappedFilterInFindCommand() {
        capture.clear();
        products.findByStatusAndStockGreaterThanEqual("ACTIVE", 5);

        BsonDocument command = capture.commands.stream()
                .filter(c -> c.containsKey("find")
                        && c.getString("find").getValue()
                                .equals("catalog_products"))
                .findFirst()
                .orElseThrow();

        BsonDocument filter = command.getDocument("filter");
        assertThat(filter.getString("status").getValue())
                .isEqualTo("ACTIVE");
        assertThat(filter.getDocument("stock_qty")
                .getInt32("$gte").getValue()).isEqualTo(5);
    }
}
~~~

Trong kiểm thử thực, nếu không có document nào, lệnh `find` vẫn được gửi và filter vẫn có thể được xác minh. Nếu quan sát sai lệnh (ví dụ lệnh đếm `countDocuments` hoặc health check), phải kiểm tra tên command; không gán mặc định `existsBy`/`countBy` luôn là `find`.

**Bảo mật:** Command monitoring có thể chứa thông tin nhạy cảm trong filter, update hoặc dữ liệu nghiệp vụ. Chỉ bật ở môi trường kiểm thử/điều tra được kiểm soát, không log toàn bộ query parameter từ production. Tắt capture hoặc loại bỏ nội dung khi không cần thiết.

### 8.3. Kiểm tra query plan

Ví dụ dùng truy vấn MongoDB shell tương đương:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE", stock_qty: { $gte: 5 } }
).explain("executionStats");
~~~

Một index ứng viên:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, stock_qty: 1 },
  { name: "idx_status_stock" }
);
~~~

Đối chiếu `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và thời gian thực thi giữa query có/không index trong môi trường có số liệu phù hợp. Không lấy kết quả vài document làm kết luận hiệu năng production. Chú ý index có thể tăng chi phí ghi, chiếm dung lượng, và không phải phương án tốt nhất cho mọi thứ tự sort hoặc mọi mức chọn lọc.

## 9. Những giới hạn cần nhận biết để không lạm dụng derived query

Từ khóa suy diễn tiện lợi cho điều kiện tương đối đơn giản. Dấu hiệu nên chuyển sang `@Query`, `MongoTemplate` hoặc aggregation:

| Nhu cầu | Vì sao tên method dễ bất tiện | Phương án |
|---|---|---|
Nhiều nhóm ngoặc AND/OR | Không biểu diễn nhóm logic tùy ý rõ ràng | `Criteria.andOperator/orOperator` hoặc `@Query` |
Aggregation với `$group`, `$lookup`, `$facet` | Method name không diễn đạt pipeline | `Aggregation`/`MongoTemplate.aggregate` hoặc `@Aggregation` |
Truy vấn mảng object cần `$elemMatch` | Các điều kiện độc lập có thể khớp phần tử khác nhau | `Criteria.elemMatch` hoặc `@Query` |
Kiểu tìm kiếm full-text, ranking, geo | Cần cú pháp/chỉ mục chuyên dụng | API/truy vấn phù hợp với MongoDB |
Update nguyên tử có điều kiện | `findBy` chỉ đọc dữ liệu | `MongoTemplate.updateFirst`/`findAndModify` |
Lọc động nhiều trường tùy chọn | Bùng nổ số phương thức repository | Query builder theo criteria hoặc custom repository |
Phân trang lớn hoặc sort động phức tạp | Cần quản lý cursor, keyset, index | Thiết kế query và pagination tường minh |

Một phương thức có tên dài 80–120 ký tự không tự trở nên “đúng chuẩn” vì Spring Data parse được. Đổi sang query tường minh khi logic khó kiểm chứng hoặc không rõ cú pháp tạo BSON.

### @Query không miễn việc kiểm tra tên field

Ví dụ:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'status': ?0, 'stock_qty': { '$gte': ?1 } }")
List<CatalogProduct> activeWithStock(
        String status, int minimumStock);
~~~

Đoạn trên **minh họa declaration bên trong interface repository**, với import `org.springframework.data.mongodb.repository.Query`, không phải một phương thức độc lập ở cấp package. Với `@Query`, cần kiểm tra quy tắc mapping của framework cho JSON query và tên field; dùng tên BSON vật lý khi viết cấu trúc thô nhưng không áp dụng máy móc nếu API đã mapping lại property. Nếu cần truy vấn tạo động có ngữ cảnh entity rõ, `MongoTemplate` với `Criteria.where("stock")` và `CatalogProduct.class` thường dễ kiểm soát.

## 10. Bẫy thường gặp khi kiểm tra keyword và BSON

| Sai lầm | Hệ quả | Cách kiểm tra/sửa |
|---|---|---|
Viết `findByDisplayName` vì BSON tên `display_name` trong khi Java property là `name` | Parser không tìm được property hoặc truy vấn khác ý | Đọc entity metadata và dùng `findByName` |
Nhìn `GreaterThan` và nghĩ nó bao gồm giá trị biên | Sai điều kiện nghiệp vụ | So sánh `$gt` với `$gte` và test tại biên |
Chỉ kiểm tra `Between` bằng số nằm giữa | Bỏ sót lỗi inclusive/exclusive | Test đúng hai đầu và quan sát BSON |
Cho rằng `Containing` luôn dùng full-text index | Truy vấn regex quét nhiều dữ liệu | Phân tích regex, explain và chọn search/index phù hợp |
Cho rằng `IgnoreCase` tương đương collation index | Kế hoạch truy vấn và kết quả so sánh không như mong đợi | Kiểm tra regex option, collation và index thực tế |
Nghĩ `IsNull` chỉ tìm field có BSON null | Lấy cả document thiếu field | Test null/missing và dùng điều kiện `$exists` khi cần |
Trộn `And`/`Or` mà không xác minh nhóm | Trả tập dữ liệu sai | Viết `Criteria` có ngoặc logic tường minh |
Điều kiện mảng không có `$elemMatch` | Điều kiện khớp trên hai phần tử khác nhau | Viết truy vấn phần tử có cùng điều kiện |
Suy ra performance từ độ ngắn tên method | N+1, regex, count hoặc sort chậm | Đo command, query plan và index |
`Page` được cho là chỉ chạy một truy vấn | Chi phí đếm và skip bị bỏ qua | Quan sát lệnh và cân nhắc `Slice`/cursor |
Chạy `deleteBy` để xem filter trên dữ liệu thật | Mất dữ liệu ngoài ý muốn | Chỉ dùng database test cô lập |
Giả định filter Extended JSON là byte-for-byte BSON thật | Assertion quá cứng theo driver version | Kiểm tra cấu trúc toán tử và semantics thay vì chuỗi cố định |

## 11. Bài tập thực hành

**Bài 1 — Lập bảng query.** Với entity `CatalogProduct` ở mục 2, tự viết bảng “method name → property → BSON field → toán tử” cho `findBySku`, `findByNameStartingWith`, `findByStockLessThanEqual`, `findByArchivedAtIsNull`, `findBySupplier_CountryCode`. Sau đó kiểm tra filter qua command monitoring.

**Bài 2 — Kiểm tra giá trị biên.** Đưa vào MongoDB bốn sản phẩm có `stock_qty` bằng 0, 5, 10 và 11. So sánh kết quả `GreaterThan(5)`, `GreaterThanEqual(5)`, `LessThan(10)`, `LessThanEqual(10)`. Dự đoán rồi xác minh bộ lọc `$gt`/`$gte`/`$lt`/`$lte`.

**Bài 3 — Null và thiếu field.** Tạo ba document: không có `archivedAt`, có `archivedAt: null` và có BSON Date. Gọi `findByArchivedAtIsNull`, `findByArchivedAtExists(true)` và `findByArchivedAtExists(false)`. Ghi rõ các tập ID trả về và lý do.

**Bài 4 — Nested mapping.** Đổi `@Field("country_code")` thành một tên field khác trong model thử nghiệm rồi chạy lại derived query `findBySupplier_CountryCode`. Phân biệt thay đổi metadata với migration dữ liệu BSON cũ. Kiểm tra failure mode nếu chưa sửa dữ liệu.

**Bài 5 — Regex và index.** Với vài chục nghìn tên sản phẩm, so sánh query tên bằng exact match, prefix, `Containing` và `ContainingIgnoreCase`. Xem filter thực tế, `explain` và chi phí index. Đề xuất phương án tìm kiếm văn bản dài hạn.

**Bài 6 — Sort và pagination.** Viết `findTop5ByStatusOrderByCreatedAtDesc` và truy vấn `Pageable` có sort (`createdAt DESC`, `id ASC`). Kiểm tra command có `filter`, `sort` và `limit/skip`; so sánh số lệnh thực hiện cho `Page` và phương án không cần total count.

**Bài 7 — Chuyển truy vấn phức tạp.** Viết lại yêu cầu `ACTIVE AND (featured OR stock >= 10)` bằng `Criteria.andOperator/orOperator`. Tạo một document chỉ có `featured=true` nhưng `status=DELETED` và chứng minh nó không được trả về. Giải thích vì sao tên derived query dài có thể gây nhầm nhóm điều kiện.

## 12. Ghi nhớ

**Derived query** trong Spring Data MongoDB ánh xạ **từ khóa của tên phương thức** thành điều kiện query dựa trên **property Java**, sau đó dùng metadata của entity để tạo **field BSON**. Những nhóm từ khóa thường gặp gồm so sánh, tập giá trị, boolean, null/existence, chuỗi/regex, nested property, sort/limit và thao tác đếm/tồn tại.

Để xác minh một truy vấn, đừng chỉ đọc tên method: hãy **kiểm tra dữ liệu biên, quan sát BSON command thực, phân tích index và query plan**. Khi gặp điều kiện nhiều nhóm logic, mảng cần `$elemMatch`, aggregation hoặc cập nhật nguyên tử, hãy dùng `MongoTemplate`, `@Query` hoặc API chuyên dụng thay vì cố nhồi logic vào tên phương thức.

Một repository dễ đọc là nơi tên method, ý nghĩa nghiệp vụ, field BSON và kết quả test **khớp nhau** — không chỉ là nơi Spring Data chấp nhận một tên phương thức dài.
