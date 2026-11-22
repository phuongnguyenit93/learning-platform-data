# Khai báo @Query bằng biểu thức truy vấn MongoDB

## 1. Vì sao cần @Query khi đã có derived query?

Trong Spring Data MongoDB, repository có thể tạo truy vấn từ tên phương thức, chẳng hạn **findByCategoryAndActive**. Cách đó rất tiện cho các điều kiện đơn giản. Nhưng khi cần ghép nhiều toán tử MongoDB như **$or**, **$in**, **$gte**, **$elemMatch** hoặc truy vấn theo đường dẫn document lồng nhau, tên phương thức có thể dài và khó đọc.

Annotation **@Query** cho phép viết trực tiếp **biểu thức truy vấn MongoDB dạng JSON-like string** tại phương thức repository. Nhờ vậy, ta giữ giao diện repository ngắn gọn nhưng mô tả rõ điều kiện BSON cần gửi đến MongoDB. Đây là chủ đề **Khai báo @Query bằng biểu thức truy vấn MongoDB**, thuộc chương **Truy vấn JSON**.

Trong module **SPRING_DATA_MONGODB**, @Query là một công cụ của tầng truy cập dữ liệu bên cạnh **MongoTemplate**, derived query, aggregation và các repository khác. Nó giúp triển khai yêu cầu tìm kiếm, nhưng hiệu quả phụ thuộc vào mô hình document, index, kiểu BSON, phân trang và cách kiểm thử. Annotation không tự tạo index, không bảo đảm truy vấn nhanh và không tự thay thế các quy tắc phân quyền, transaction hay xử lý reactive.

Mục tiêu sau bài học:

1. Biết cách import và khai báo **@Query** của Spring Data MongoDB trên phương thức repository.
2. Viết filter JSON với toán tử MongoDB và tham số **?0, ?1, ...**.
3. Áp dụng điều kiện range, logic, mảng, object nhúng, regex và ngày giờ.
4. Sử dụng projection qua **fields**, sắp xếp, Pageable, count và exists.
5. Hiểu cách mapping giữa thuộc tính Java và field BSON cũng như các vấn đề null/missing.
6. Nhận diện các rủi ro về query injection, index, hiệu năng và tính toàn vẹn dữ liệu.
7. Viết kiểm thử tích hợp và đối chiếu truy vấn bằng mongosh/MongoTemplate.

## 2. Dữ liệu mẫu dùng xuyên suốt

Giả sử một dịch vụ bán hàng có collection **products** chứa document sau:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  category: "BOOK",
  priceMinor: NumberLong("159000"),
  stock: NumberInt(8),
  active: true,
  tags: ["JAVA", "SPRING", "BACKEND"],
  attributes: {
    brand: "TechBooks"
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Document thứ hai cùng collection:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  sku: "PEN-002",
  name: "Bút ghi chú",
  category: "STATIONERY",
  priceMinor: NumberLong("12000"),
  stock: NumberInt(25),
  active: true,
  tags: ["OFFICE", "SALE"],
  attributes: {
    brand: "PaperLab"
  },
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

Trường **priceMinor** biểu diễn số nguyên đơn vị tiền nhỏ nhất theo hợp đồng của hệ thống, không phải Double. **createdAt** là BSON Date, **_id** là BSON ObjectId. Việc dùng đúng kiểu Java khi bind tham số sẽ giúp tránh những lỗi truy vấn tưởng rằng có dữ liệu nhưng không tìm thấy.

Entity Java ánh xạ với collection:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    String category,
    long priceMinor,
    int stock,
    boolean active,
    List<String> tags,
    Attributes attributes,
    Instant createdAt
) {
    public record Attributes(String brand) {}
}
~~~

Ví dụ dùng Java record để thể hiện immutable entity. Với phiên bản Spring Data MongoDB có hỗ trợ record, framework có thể materialize từ các component tương ứng. Điều quan trọng đối với bài này là **tên property Java** phù hợp với mô hình BSON và được sử dụng thống nhất trong repository.

## 3. Import đúng @Query

Annotation repository query của MongoDB được import:

~~~java
import org.springframework.data.mongodb.repository.Query;
~~~

Không nhầm với các annotation cùng tên của JPA hoặc thư viện khác. Một repository tối giản:

~~~java
package com.example.catalog;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query("{ 'active': true }")
    List<ProductDocument> findActiveProductsJson();
}
~~~

Biểu thức **{ 'active': true }** là filter MongoDB: tìm document có active bằng Boolean true. Khi gọi method, Spring Data dùng metadata của **ProductDocument** để xác định collection products và chuyển kết quả BSON thành ProductDocument.

### 3.1. JSON-like không phải chuỗi SQL

Trong @Query, ta viết cú pháp dựa trên **query document của MongoDB**, không viết SQL:

~~~java
@Query("{ 'category': 'BOOK', 'active': true }")
List<ProductDocument> findActiveBooks();
~~~

Điều kiện tương đương trong mongosh:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

Các ví dụ trong bài dùng **nháy đơn** trong chuỗi annotation để code Java dễ đọc. Spring Data MongoDB hỗ trợ cách biểu diễn JSON-like đó khi phân tích truy vấn. Với các công cụ JSON strict ngoài framework, dấu nháy kép mới là cú pháp JSON tiêu chuẩn; không nên đưa nguyên chuỗi annotation sang một JSON parser khác rồi kỳ vọng hành vi giống hệt.

### 3.2. Derived query và @Query

~~~java
// Truy vấn suy ra từ tên method.
List<ProductDocument> findByCategoryAndActive(
    String category, boolean active
);

// Truy vấn khai báo bằng MongoDB JSON.
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findByFilterJson(
    String category, boolean active
);
~~~

Hai cách có thể biểu đạt cùng một điều kiện. Nếu derived query ngắn và dễ hiểu, không bắt buộc chuyển sang @Query. Nên dùng @Query khi biểu thức MongoDB trực tiếp **rõ ràng hơn** hoặc cần tính năng vượt quá cách đặt tên method.

## 4. Bind tham số bằng ?0, ?1, ...

Trong @Query, **?0** là tham số đầu tiên của method, **?1** là tham số thứ hai, đếm từ **0**:

~~~java
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findInCategory(
    String category, boolean active
);
~~~

Ví dụ:

~~~java
List<ProductDocument> books =
    repository.findInCategory("BOOK", true);
~~~

Spring Data sẽ bind giá trị tham số theo kiểu phù hợp rồi tạo điều kiện tương đương:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

### 4.1. Không đặt placeholder trong dấu nháy của giá trị

**Đúng:**

~~~java
@Query("{ 'sku': ?0 }")
List<ProductDocument> findBySkuJson(String sku);
~~~

**Không nên viết:**

~~~java
// Ví dụ sai: dễ biến ?0 thành phần của chuỗi literal.
@Query("{ 'sku': '?0' }")
List<ProductDocument> findBySkuWrong(String sku);
~~~

Giá trị tham số được framework bind và chuyển đổi, không phải một mẩu văn bản tự nối vào chuỗi query. Đặt placeholder bên ngoài nháy giúp cơ chế bind xử lý giá trị String, Number, Boolean, ObjectId và các kiểu khác đúng ý định.

### 4.2. Tại sao không nối chuỗi do người dùng nhập?

Không xây JSON query bằng cách ghép trực tiếp input:

~~~java
// Tránh: code minh họa một cách xây query không an toàn.
String raw = "{ 'sku': '" + userInput + "' }";
~~~

Cách này có nguy cơ sinh cú pháp sai, tạo query injection và khiến kiểm tra kiểu BSON khó khăn. Với repository, dùng **?0, ?1** để truyền giá trị như dữ liệu. Spring Data có cơ chế bind và escape tham số String cho cấu trúc truy vấn thông thường, thay vì để chúng thay đổi tùy ý các toán tử của JSON query.

Tuy nhiên, **bind an toàn không đồng nghĩa mọi giá trị đầu vào đều an toàn về nghiệp vụ**. Một regex do người dùng kiểm soát vẫn có thể quá tốn CPU; một danh sách $in hàng trăm nghìn phần tử vẫn có thể tạo truy vấn nặng. Cần kiểm soát độ dài, số lượng và các giới hạn thích hợp.

## 5. Toán tử so sánh: $gt, $gte, $lt, $lte

Trong mongosh, điều kiện giá nằm trong một khoảng:

~~~javascript
db.products.find({
  priceMinor: { $gte: NumberLong("10000"), $lte: NumberLong("200000") }
});
~~~

Trong repository:

~~~java
@Query("{ 'priceMinor': { '$gte': ?0, '$lte': ?1 } }")
List<ProductDocument> findPriceBetweenJson(
    long minimumMinor,
    long maximumMinor
);
~~~

Trường hợp gọi:

~~~java
List<ProductDocument> result =
    repository.findPriceBetweenJson(10_000L, 200_000L);
~~~

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| $gt | Lớn hơn | stock lớn hơn 0 |
| $gte | Lớn hơn hoặc bằng | priceMinor ít nhất 10.000 |
| $lt | Nhỏ hơn | stock nhỏ hơn 5 |
| $lte | Nhỏ hơn hoặc bằng | priceMinor tối đa 200.000 |
| $ne | Khác | category khác BOOK |

Chú ý **kiểu và đơn vị dữ liệu**: priceMinor là long, nên nhận tham số long. Nếu client gửi số tiền ở một đơn vị khác, phải chuyển đổi/kiểm tra tại tầng nghiệp vụ trước khi gọi repository. Không dùng Double cho tiền chỉ vì JSON của API có dạng số.

### 5.1. Kết hợp điều kiện trên các field

~~~java
@Query("{ 'active': true, 'stock': { '$gt': 0 }, 'priceMinor': { '$lte': ?0 } }")
List<ProductDocument> findAvailableUnder(long maximumMinor);
~~~

Nhiều field ở cùng cấp trong filter thường được kết hợp theo **AND**. Điều kiện này tìm sản phẩm đang bán, còn hàng và không vượt mức giá.

### 5.2. Một lỗi logic dễ gặp

Nếu người dùng nhập **minimumMinor** lớn hơn **maximumMinor**, query không thể khớp với giá trị hợp lệ. Repository không tự sửa khoảng bị đảo. Nên validate:

~~~java
if (minimumMinor < 0 || maximumMinor < minimumMinor) {
    throw new IllegalArgumentException("Invalid price range");
}
~~~

Đó là quy tắc tầng service, không phải chức năng của @Query.

## 6. Toán tử logic: $and, $or, $nor

MongoDB hỗ trợ kết hợp điều kiện:

~~~java
@Query("""
       {
         '$and': [
           { 'active': true },
           {
             '$or': [
               { 'category': ?0 },
               { 'tags': ?1 }
             ]
           }
         ]
       }
       """)
List<ProductDocument> findActiveCategoryOrTag(
    String category,
    String tag
);
~~~

Ví dụ dùng **Java text block** (Java 15+) để hiển thị JSON rõ ràng; project dùng Java cũ hơn có thể viết toàn bộ trong chuỗi String một dòng. Spring Data sẽ bind các placeholder trong query string sau khi Java cung cấp giá trị annotation.

Điều kiện tìm sản phẩm active, đồng thời thuộc một trong hai nhóm:

- category đúng giá trị được truyền;
- **hoặc** mảng tags chứa tag được truyền.

Trong MongoDB, điều kiện **{ tags: "JAVA" }** có thể khớp document mà tags là mảng chứa phần tử "JAVA", không cần viết $elemMatch cho phép so sánh đơn giản đó.

### 6.1. Khi nào cần $and tường minh?

Đối với hai điều kiện field khác nhau ở cùng cấp, một object JSON đã biểu thị AND:

~~~java
@Query("{ 'active': true, 'category': ?0 }")
List<ProductDocument> activeCategory(String category);
~~~

Dùng $and khi cấu trúc phức tạp cần ghép các biểu thức trùng khóa hoặc muốn nhóm nhiều nhánh $or rõ ràng. Đừng viết JSON object có **hai khóa $or trùng nhau** rồi kỳ vọng cả hai được áp dụng; parser có thể giữ một khóa và bỏ khóa còn lại. Hãy viết $and chứa hai object $or riêng.

### 6.2. Dùng $nor

~~~java
@Query("{ '$nor': [ { 'category': 'DISCONTINUED' }, { 'active': false } ] }")
List<ProductDocument> findNotDiscontinuedAndNotInactive();
~~~

Về logic, $nor khớp khi **không điều kiện nào** trong các nhánh đúng. Tuy nhiên, khi dữ liệu có field thiếu/null, ý nghĩa phủ định có thể khác mong đợi. Nên kiểm tra dữ liệu legacy và dùng filter trực tiếp dễ hiểu hơn nếu có thể.

## 7. Truy vấn mảng: $in, $nin, $all và $elemMatch

### 7.1. $in: thuộc một tập giá trị

~~~java
import java.util.Collection;

@Query("{ 'category': { '$in': ?0 }, 'active': true }")
List<ProductDocument> findActiveInCategories(
    Collection<String> categories
);
~~~

Gọi với:

~~~java
List<ProductDocument> result = repository.findActiveInCategories(
    java.util.List.of("BOOK", "STATIONERY")
);
~~~

Trong MongoDB, điều kiện tương đương:

~~~javascript
db.products.find({
  category: { $in: ["BOOK", "STATIONERY"] },
  active: true
});
~~~

**$nin** là phủ định của $in theo quy tắc MongoDB và cần chú ý document thiếu field cũng có thể khớp điều kiện phủ định. Không nên dùng $nin mà không kiểm tra chính sách dữ liệu thiếu field.

### 7.2. $all: chứa tất cả tag được yêu cầu

~~~java
@Query("{ 'tags': { '$all': ?0 } }")
List<ProductDocument> findWithAllTags(
    java.util.Collection<String> requiredTags
);
~~~

Nếu truyền "JAVA" và "SPRING", document phải chứa cả hai tag. Khác với việc so sánh tags bằng một String đơn lẻ, phép kiểm tra này yêu cầu nhiều phần tử có mặt.

### 7.3. $elemMatch cho array of documents

Giả sử dữ liệu thực tế có:

~~~javascript
{
  sku: "KIT-001",
  variants: [
    { color: "RED", stock: NumberInt(0) },
    { color: "BLUE", stock: NumberInt(5) }
  ]
}
~~~

Nếu cần **một phần tử variants vừa có color RED vừa có stock lớn hơn 0**, dùng $elemMatch:

~~~java
@Query("{ 'variants': { '$elemMatch': { 'color': ?0, 'stock': { '$gt': ?1 } } } }")
List<ProductDocument> findVariantWithStock(
    String color,
    int minimumExclusiveStock
);
~~~

Ví dụ method cần một domain có property **variants** tương ứng; ProductDocument của ví dụ đầu bài chưa khai báo field này, nên đây là mẫu query để mở rộng domain khi có biến thể sản phẩm.

**Vì sao $elemMatch quan trọng?** Hai điều kiện trên đường dẫn mảng độc lập có thể được thỏa bởi **hai phần tử khác nhau**. $elemMatch bảo đảm các điều kiện nằm trong **cùng một phần tử**.

## 8. Truy vấn field của object nhúng

Document mẫu có:

~~~javascript
{
  attributes: {
    brand: "TechBooks"
  }
}
~~~

Để tìm sản phẩm theo brand:

~~~java
@Query("{ 'attributes.brand': ?0 }")
List<ProductDocument> findByBrandJson(String brand);
~~~

**attributes.brand** là đường dẫn dot notation của MongoDB. Trường này được tìm trong embedded object attributes, **không phải collection khác**.

Nếu schema cũ lưu attributes là String hoặc không có attributes, truy vấn có thể không tìm thấy những document đó. @Query không tự chuẩn hóa các phiên bản schema khác nhau; cần migration hoặc một điều kiện tương thích có chủ đích.

### 8.1. Khi dùng @Field để đổi tên BSON

Giả sử Java có property **postalCode** nhưng MongoDB lưu **postal_code**, được khai báo:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public record Address(
    String city,
    @Field("postal_code") String postalCode
) {}
~~~

Với các phép truy vấn được Spring Data ánh xạ qua metadata entity, QueryMapper có thể chuyển property path sang tên field BSON tương ứng. Khi viết **mongosh hoặc driver thô**, luôn phải sử dụng tên BSON thực sự, ví dụ **address.postal_code**.

Khi dùng @Query JSON cho entity có nhiều @Field, hãy kiểm tra truy vấn được ánh xạ ra thực tế ở môi trường test. Đừng đoán rằng mọi chuỗi property path tùy ý, alias phức tạp hoặc custom converter đều được chuyển đúng theo ý định. Thống nhất quy ước tên và dùng test để phát hiện chệch giữa Java và BSON.

## 9. Dữ liệu thiếu, null và kiểu BSON

MongoDB phân biệt **field không tồn tại**, **field tồn tại với null** và **field có giá trị**. Những khác biệt đó rất quan trọng khi viết filter.

~~~java
// Tìm document thiếu hẳn field attributes.brand.
@Query("{ 'attributes.brand': { '$exists': false } }")
List<ProductDocument> findMissingBrand();

// Điều kiện null trong MongoDB có thể khớp cả null và missing.
@Query("{ 'attributes.brand': null }")
List<ProductDocument> findNullOrMissingBrand();
~~~

Nếu business yêu cầu tìm **field tồn tại và có giá trị null**, dùng điều kiện gồm hai vế:

~~~java
@Query("{ 'attributes.brand': { '$exists': true, '$eq': null } }")
List<ProductDocument> findExplicitNullBrand();
~~~

Trong mongo shell:

~~~javascript
db.products.find({
  "attributes.brand": { $exists: true, $eq: null }
});
~~~

### 9.1. Kiểm tra kiểu với $type

~~~java
@Query("{ 'priceMinor': { '$type': 'long' } }")
List<ProductDocument> findProductsWithLongPrice();
~~~

Ở đây **long** là tên kiểu BSON Int64, khác với một String chứa chữ số. Query theo kiểu có thể hữu ích trong chẩn đoán migration, nhưng **không nên biến chúng thành logic nghiệp vụ cố định** nếu dữ liệu nên được chuẩn hóa về một schema.

Kiểm tra trên mongosh:

~~~javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      priceType: { $type: "$priceMinor" },
      createdAtType: { $type: "$createdAt" }
    }
  }
]);
~~~

Nếu cùng field có document lưu priceMinor dưới dạng String, Int32 và Int64, các phép so sánh có thể cho kết quả khác mong đợi. Hãy sửa dữ liệu hoặc chuẩn hóa kiểu thay vì chỉ ép mọi tham số đầu vào thành String.

## 10. Tham số ObjectId và thời gian

### 10.1. So sánh theo ObjectId

Entity có **@Id ObjectId id**, repository có thể tra cứu bằng findById đã có. Khi cần thêm điều kiện:

~~~java
import org.bson.types.ObjectId;

@Query("{ '_id': ?0, 'active': true }")
java.util.Optional<ProductDocument> findActiveByIdJson(ObjectId id);
~~~

Tham số đầu tiên là **ObjectId**, không phải chuỗi hex tùy ý. Nếu API nhận ID dạng String, chuyển đổi/validate trước:

~~~java
ObjectId id = new ObjectId(hexId);
java.util.Optional<ProductDocument> found =
    repository.findActiveByIdJson(id);
~~~

Nếu collection thật sự lưu _id ở kiểu BSON String, phải điều chỉnh mapping và cách bind cho đúng. ObjectId in ra chuỗi 24 ký tự hex không đồng nghĩa String và BSON ObjectId có cùng kiểu.

### 10.2. Truy vấn theo thời gian

Document có createdAt kiểu BSON Date, còn Java dùng **Instant**:

~~~java
import java.time.Instant;

@Query("{ 'createdAt': { '$gte': ?0, '$lt': ?1 } }")
List<ProductDocument> findCreatedInRange(
    Instant startInclusive,
    Instant endExclusive
);
~~~

Sử dụng khoảng **[start, end)** giúp tránh trùng bản ghi trên hai khoảng liền nhau:

~~~java
Instant start = Instant.parse("2025-06-01T00:00:00Z");
Instant end = Instant.parse("2025-07-01T00:00:00Z");

List<ProductDocument> createdInJune =
    repository.findCreatedInRange(start, end);
~~~

Cần giữ thống nhất timezone khi chuyển đổi đầu vào API và so sánh theo UTC/Instant. Nếu BSON lưu ngày dưới dạng String ISO thay vì Date, truy vấn với Instant có thể không hoạt động theo hợp đồng mong muốn.

## 11. Regex và tìm kiếm chuỗi

MongoDB hỗ trợ biểu thức chính quy qua **$regex**:

~~~java
@Query("{ 'name': { '$regex': ?0, '$options': 'i' } }")
List<ProductDocument> searchNameByRegex(String regexPattern);
~~~

Ví dụ truyền mẫu bắt đầu bằng chữ **Spring**:

~~~java
List<ProductDocument> matches =
    repository.searchNameByRegex("^Spring");
~~~

**Lưu ý:** Khi tham số mang ý nghĩa regex, người dùng có thể tác động tới độ phức tạp của biểu thức. Không nên đưa trực tiếp một regex không được giới hạn vào query production. Nếu ý định chỉ là tìm văn bản literal, cần **escape regex metacharacters** và giới hạn độ dài, kết quả, thời gian thực thi.

Một cách khác để lưu ý sự khác biệt:

~~~java
// Một String thông thường được so sánh theo giá trị chính xác.
@Query("{ 'name': ?0 }")
List<ProductDocument> findExactName(String name);
~~~

findExactName tìm đúng giá trị tên theo quy tắc so sánh của truy vấn, không tự biến tham số thành regex. Nếu ứng dụng yêu cầu tìm kiếm full-text, autocomplete, tìm không dấu hay xếp hạng mức độ tương đồng, hãy xem xét index và công cụ tìm kiếm phù hợp thay vì giả định $regex giải quyết tốt mọi nhu cầu.

### 11.1. Hiệu năng của regex

Các biểu thức có prefix được neo ở đầu chuỗi có thể sử dụng index hiệu quả hơn trong một số trường hợp. Ngược lại, regex có ký tự đại diện ở đầu hoặc regex không phân biệt chữ hoa/thường có thể khó tận dụng index thông thường. Hành vi phụ thuộc index, collation, pattern và phiên bản server; phải **đo bằng explain**, không kết luận chỉ từ cú pháp.

## 12. Trả về một phần field bằng fields

Nếu màn hình danh sách chỉ cần tên và giá, không nhất thiết đọc toàn bộ document.

Annotation @Query có thuộc tính **fields** để khai báo projection ở phía MongoDB:

~~~java
public interface ProductSummary {
    ObjectId getId();
    String getName();
    long getPriceMinor();
}
~~~

Repository:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductSummary> findActiveSummaries();
~~~

Kết quả chỉ cần các field được projection, sau đó Spring Data có thể ánh xạ sang **interface projection** ProductSummary. Việc trả interface chuyên biệt giúp code sử dụng kết quả không mặc định có các field chưa được tải.

### 12.1. Include và exclude

Trong MongoDB, projection có quy tắc:

- Giá trị **1** thường chỉ định field được giữ lại.
- Giá trị **0** thường chỉ định field bị loại khỏi kết quả.
- Trừ ngoại lệ liên quan **_id**, không nên trộn include và exclude tùy ý trong một projection thông thường.

Ví dụ không cần ID:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 0, 'name': 1, 'priceMinor': 1 }"
)
List<ProductSummary> findSummariesWithoutId();
~~~

Nhưng lúc này **getId()** không có dữ liệu để trả về; trong ứng dụng thật, hãy thiết kế interface projection không có id hoặc chấp nhận null theo hợp đồng. Khi endpoint cần đường dẫn chi tiết sản phẩm, nên giữ _id.

### 12.2. Tránh trả entity đầy đủ sau khi projection thiếu field

~~~java
// Không khuyến khích nếu caller coi kết quả là ProductDocument đầy đủ.
@Query(
    value = "{ 'active': true }",
    fields = "{ 'name': 1 }"
)
List<ProductDocument> findPartialProducts();
~~~

Nếu chỉ tải name mà lại yêu cầu materialize ProductDocument với các primitive long, int, boolean và các constructor field khác, đối tượng có thể có null, giá trị mặc định hoặc lỗi materialization tùy cách mapping. Nguy hiểm hơn, code có thể đem object thiếu field đó đi save như thể là một entity đầy đủ và làm mất dữ liệu.

**Thực hành tốt:** dùng **DTO/projection phù hợp** với đúng field được tải và không save lại một entity chỉ mới đọc projection thiếu dữ liệu.

## 13. Sắp xếp và phân trang

Truy vấn có thể có nhiều kết quả. API production cần giới hạn số lượng trả về và thứ tự rõ ràng.

### 13.1. Sort cố định trong annotation

~~~java
@Query(
    value = "{ 'active': ?0 }",
    sort = "{ 'createdAt': -1, '_id': -1 }"
)
List<ProductDocument> findActiveNewestFirst(boolean active);
~~~

Trong MongoDB, **-1** là thứ tự giảm dần. Bổ sung _id làm khóa phụ giúp kết quả có thứ tự xác định hơn khi nhiều sản phẩm có cùng createdAt.

### 13.2. Sort do caller cung cấp

~~~java
import org.springframework.data.domain.Sort;

@Query("{ 'active': ?0 }")
List<ProductDocument> findActiveSorted(
    boolean active,
    Sort sort
);
~~~

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<ProductDocument> result =
    repository.findActiveSorted(true, sort);
~~~

Spring Data xử lý **Sort** như tham số đặc biệt, không phải tham số bind vào JSON filter. Khi sort theo id, metadata mapping có thể chuyển property Java id thành BSON _id.

Nếu cho client tự chọn tên trường sắp xếp, nên dùng **danh sách tên field được phép**, không nhận bất kỳ chuỗi nào mà không validate. Việc sắp xếp trên field chưa có index hoặc không giới hạn có thể gây query nặng.

### 13.3. Phân trang với Pageable

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query("{ 'active': ?0 }")
Page<ProductDocument> findActivePage(
    boolean active,
    Pageable pageable
);
~~~

Gọi:

~~~java
Pageable pageRequest = org.springframework.data.domain.PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Page<ProductDocument> page =
    repository.findActivePage(true, pageRequest);
~~~

**Page** có thể yêu cầu truy vấn đếm để biết tổng số phần tử; điều này có thể tốn chi phí với collection lớn hoặc điều kiện phức tạp. Nếu client chỉ cần biết còn trang tiếp theo, có thể thiết kế **Slice** hoặc phân trang theo khóa (keyset) khi phù hợp. Việc truyền Pageable không tự tạo index và không biến skip/limit với offset lớn thành truy vấn miễn phí.

### 13.4. Chú ý thứ tự ổn định

Nếu chỉ sort theo createdAt và nhiều document có cùng timestamp, kết quả giữa các trang có thể trùng/bỏ sót khi dữ liệu thay đổi trong lúc phân trang. Bổ sung khóa duy nhất như _id trong sort giúp thứ tự xác định; với dữ liệu ghi thường xuyên, vẫn cần lựa chọn pagination phù hợp với yêu cầu nhất quán.

## 14. Count và exists bằng @Query

Ngoài việc trả document, annotation có thể yêu cầu truy vấn trả kết quả dạng count hoặc exists:

~~~java
@Query(value = "{ 'category': ?0, 'active': true }", count = true)
long countActiveByCategoryJson(String category);
~~~

~~~java
@Query(value = "{ 'sku': ?0 }", exists = true)
boolean existsBySkuJson(String sku);
~~~

So sánh:

| Truy vấn | Kết quả |
| --- | --- |
| findBySkuJson | Danh sách hoặc đối tượng domain phù hợp với phương thức khai báo. |
| countActiveByCategoryJson | Số document thỏa điều kiện. |
| existsBySkuJson | true nếu có document thỏa điều kiện, false nếu không. |

Truy vấn exists thích hợp để kiểm tra tồn tại đơn giản, nhưng **kiểm tra exists rồi insert không thay thế unique index**. Hai request đồng thời có thể đều nhìn thấy sku chưa tồn tại và cùng cố ghi. Nếu SKU phải duy nhất, cần ràng buộc unique index trên MongoDB và xử lý duplicate key.

### 14.1. @Query không phải một API tổng quát cho mọi cập nhật

@Query chủ yếu mô tả filter và các dạng truy vấn repository. Một số phiên bản cho phép khai báo delete query qua tùy chọn chuyên biệt, nhưng không nên coi **@Query(value=...)** là lệnh update tùy ý.

Khi cần cập nhật field có điều kiện, sử dụng MongoTemplate với **Query/Update**, phương thức repository được hỗ trợ cho update, hoặc cơ chế phù hợp với phiên bản Spring Data. Khi cần tổng hợp nhiều stage, dùng **@Aggregation** hoặc MongoTemplate.aggregate thay vì cố nhồi pipeline aggregate vào @Query.

## 15. Khi nào dùng @Query, derived query, MongoTemplate hay aggregation?

| Nhu cầu | Gợi ý lựa chọn | Lý do |
| --- | --- | --- |
| Tìm theo category và active | Derived query hoặc @Query | Đều đơn giản; ưu tiên cách dễ đọc. |
| Filter nhiều $or, $in, range | @Query | Diễn đạt rõ cấu trúc MongoDB trong repository. |
| Điều kiện linh hoạt theo nhiều tham số tùy chọn | MongoTemplate + Criteria, hoặc query builder | Tránh một chuỗi JSON với nhiều nhánh khó kiểm soát. |
| Cập nhật một phần document | MongoTemplate.updateFirst/updateMulti hoặc API update thích hợp | @Query filter không tự là lệnh update. |
| Nhóm dữ liệu, $lookup, $group, $project | Aggregation/@Aggregation | Đây là pipeline, không phải find filter đơn giản. |
| Lấy một tập field cố định | @Query(fields=...) + projection | Giảm dữ liệu truyền/ánh xạ. |
| Tương tác non-blocking | ReactiveMongoRepository/ReactiveMongoTemplate | Sử dụng luồng phản ứng phù hợp. |

Trong ứng dụng lớn, chọn một API không nhất thiết loại trừ các API còn lại. Một repository có thể cung cấp derived queries đơn giản và @Query cho điều kiện phức tạp; các tác vụ aggregation hoặc update linh hoạt có thể nằm trong custom repository dùng MongoTemplate.

## 16. Hiệu năng: từ @Query đến index

Một phương thức repository dễ đọc chưa bảo đảm query chạy nhanh. Ví dụ filter:

~~~java
@Query("{ 'category': ?0, 'active': true }")
List<ProductDocument> findActiveByCategory(String category);
~~~

Nếu truy vấn này là đường nóng của API, có thể đánh giá index:

~~~javascript
db.products.createIndex({ category: 1, active: 1 });

db.products.find({
  category: "BOOK",
  active: true
}).explain("executionStats");
~~~

Với đường đọc còn sort theo createdAt giảm dần, xem xét compound index theo mẫu filter và sort thực tế:

~~~javascript
db.products.createIndex({
  category: 1,
  active: 1,
  createdAt: -1,
  _id: -1
});

db.products.find({
  category: "BOOK",
  active: true
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

Index thứ hai chỉ là **ứng viên** cho một mẫu truy vấn cụ thể, không phải index bắt buộc mọi collection products đều cần. Thêm nhiều index làm tăng chi phí ghi, dung lượng và chi phí bảo trì. Phải đánh giá dựa trên workload thực tế và giải thích kế hoạch truy vấn.

### 16.1. Cần đọc gì trong executionStats?

- **winningPlan**: có sử dụng index phù hợp hay bị collection scan.
- **totalKeysExamined** và **totalDocsExamined**: lượng index key/document được duyệt.
- **nReturned**: số document trả về.
- **executionTimeMillis**: thời gian thực thi trong điều kiện quan sát.
- **SORT stage**: có cần sort bổ sung ngoài index hay không.

Một plan tốt không chỉ là “có IXSCAN”; nó phải phù hợp với số bản ghi quét, số bản ghi trả về, độ trễ và độ chọn lọc của query.

### 16.2. Các nguồn query chậm

1. **$or** có nhiều nhánh không được hỗ trợ bởi index thích hợp.
2. **$in** chứa quá nhiều phần tử.
3. **Regex** không thể tận dụng index hiệu quả hoặc quá phức tạp.
4. **Pageable với offset lớn** khiến server phải bỏ qua nhiều kết quả.
5. **fields projection** chọn quá nhiều field hoặc trả entity đầy đủ trong khi chỉ cần vài field.
6. **Sort** không có index phù hợp.
7. Dữ liệu có **kiểu BSON không thống nhất**, khiến filter không phù hợp với schema thực tế.

Khi chẩn đoán, cần xem **truy vấn MongoDB thực tế** cùng dữ liệu và index, không suy từ tên method hoặc sự hiện diện của @Query.

## 17. Bảo vệ hợp đồng truy vấn và phân quyền

### 17.1. @Query không tự lọc tenant

Nếu products có trường **tenantId**, một phương thức như:

~~~java
@Query("{ 'active': true }")
List<ProductDocument> findAllActive();
~~~

có thể đọc product của mọi tenant mà account MongoDB được phép đọc. @Query không tự thêm điều kiện tenantId. Trong hệ thống nhiều tenant, cần có chính sách nhất quán tại service/repository/permission và kiểm thử truy vấn với dữ liệu của nhiều tenant.

Với repository đặc thù:

~~~java
@Query("{ 'tenantId': ?0, 'active': true }")
List<ProductDocument> findActiveForTenant(String tenantId);
~~~

Ví dụ này chỉ phù hợp khi schema ProductDocument được mở rộng thực sự có tenantId và mọi đường đọc/ghi đều tuân theo chính sách tenant. Việc để caller tự chọn tenantId tùy ý cũng chưa phải kiểm soát quyền; service phải lấy và xác minh tenant từ ngữ cảnh đã xác thực.

### 17.2. Giới hạn số kết quả

Không để API trả toàn bộ collection lớn chỉ vì repository method khai báo **List<ProductDocument>**. Cân nhắc:

- Pageable hoặc giới hạn số bản ghi ở tầng query.
- Chỉ chọn field cần thiết.
- Đặt timeout/giới hạn theo hạ tầng và quan sát độ trễ.
- Với báo cáo dài, dùng xử lý batch hoặc cursor phù hợp.

### 17.3. JSON bind và SpEL

Spring Data MongoDB hỗ trợ các tính năng biểu thức trong một số ngữ cảnh truy vấn, bao gồm **SpEL** theo cú pháp mà phiên bản thư viện hỗ trợ. SpEL linh hoạt nhưng mở rộng phạm vi cần kiểm soát: đừng biến input người dùng thành **một phần cấu trúc truy vấn** mà không validation. Với phần lớn truy vấn, **?0, ?1** dễ đọc, dễ kiểm thử và ít gây lỗi hơn.

## 18. Kiểm thử tích hợp @Query

Unit test chỉ mock ProductRepository không chứng minh filter JSON được Spring Data phân tích đúng hay BSON được bind đúng kiểu. Cần thử trên MongoDB thật của môi trường test (ví dụ Testcontainers) với các document được kiểm soát.

Một repository kiểm thử có các phương thức:

~~~java
public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query("{ 'category': ?0, 'active': ?1 }")
    List<ProductDocument> findInCategory(String category, boolean active);

    @Query("{ 'priceMinor': { '$gte': ?0, '$lte': ?1 } }")
    List<ProductDocument> findPriceBetweenJson(long min, long max);

    @Query("{ 'attributes.brand': ?0 }")
    List<ProductDocument> findByBrandJson(String brand);

    @Query(value = "{ 'sku': ?0 }", exists = true)
    boolean existsBySkuJson(String sku);
}
~~~

Ví dụ test JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class ProductJsonQueryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void queryBindsValuesAndNestedPath() {
        String sku = "TEST-" + UUID.randomUUID();

        ProductDocument inserted = products.insert(
            new ProductDocument(
                null,
                sku,
                "Learning MongoDB",
                "BOOK",
                159_000L,
                3,
                true,
                List.of("JAVA", "SPRING"),
                new ProductDocument.Attributes("TechBooks"),
                Instant.parse("2025-06-01T09:00:00Z")
            )
        );

        ObjectId id = inserted.id();
        assertThat(id).isNotNull();

        try {
            assertThat(products.existsBySkuJson(sku)).isTrue();

            assertThat(products.findInCategory("BOOK", true))
                .anyMatch(p -> p.id().equals(id));

            assertThat(products.findPriceBetweenJson(150_000L, 160_000L))
                .anyMatch(p -> p.id().equals(id));

            assertThat(products.findByBrandJson("TechBooks"))
                .anyMatch(p -> p.id().equals(id));
        } finally {
            products.deleteById(id);
        }
    }
}
~~~

Do repository truy vấn trên collection chung, test dùng SKU ngẫu nhiên để tránh xung đột với dữ liệu khác. Tuy nhiên, các assertion lọc category/price/brand có thể trả nhiều document; test kiểm tra bản ghi vừa insert có trong kết quả thay vì đòi cả collection chỉ có một document.

Trong thực tế, nên dùng **database test riêng** và fixture có phạm vi rõ; nếu muốn kiểm tra exact count, cần cách ly dữ liệu để kết quả không phụ thuộc các test chạy song song.

### 18.1. Test những trường hợp nào?

| Trường hợp | Kỳ vọng |
| --- | --- |
| Bind String và Boolean qua ?0/?1 | Truy vấn tìm đúng document phù hợp. |
| Bind long theo priceMinor | Range filter đúng đơn vị và kiểu. |
| Truy vấn attributes.brand | Đọc đúng embedded field. |
| $in với danh sách nhiều category | Trả các category thuộc tập truyền vào. |
| $all trên tags | Yêu cầu tất cả tags có mặt. |
| Null và missing | Phân biệt khi nghiệp vụ cần. |
| ObjectId từ API | Chuyển/kiểm tra kiểu trước khi bind. |
| Projection fields | Chỉ dựa vào các property đã tải; không save entity partial. |
| Sort/Pageable | Thứ tự xác định, giới hạn page và metadata phù hợp. |
| count/exists | Trả kiểu số/Boolean đúng và xử lý kết quả rỗng. |
| Regex người dùng nhập | Được giới hạn hoặc escape theo hợp đồng. |
| Đa tenant | Không trả document của tenant khác. |
| Index trên query quan trọng | explain cho thấy kế hoạch phù hợp workload. |

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| Repository không khởi động | JSON query sai cú pháp hoặc method/property không hợp lệ | Kiểm tra chuỗi @Query, dấu ngoặc và thông báo parser. |
| Truy vấn không thấy String mong đợi | Đặt nháy quanh placeholder hoặc khác kiểu/giá trị | Dùng ?0 đúng cách, kiểm tra BSON và bind. |
| ObjectId trông đúng mà không match | String và BSON ObjectId khác kiểu | Kiểm tra _id thật, parse hoặc mapping ID thích hợp. |
| Range giá trả kết quả lạ | Nhầm đơn vị tiền, kiểu BSON hoặc dấu so sánh | Kiểm tra priceMinor, type và tham số long. |
| $or chỉ áp dụng một nhánh | Có khóa $or trùng ở cùng một object | Dùng $and kết hợp các object $or riêng. |
| Array query khớp phần tử ngoài ý muốn | Không dùng $elemMatch cho điều kiện cùng item | Dùng $elemMatch khi cần một phần tử thỏa toàn bộ. |
| Field lồng nhau không match | Sai dot path, @Field alias hoặc schema cũ | Xem BSON thực tế và mapping metadata. |
| Projection trả null/giá trị mặc định | fields không tải đủ cho entity | Dùng DTO/interface projection phù hợp. |
| Regex làm API chậm | Pattern phức tạp hoặc không tận dụng index | Giới hạn regex, đo explain, cân nhắc search index. |
| Pageable chậm ở trang sâu | Skip lớn hoặc sort chưa tối ưu | Đo query, cân nhắc keyset pagination. |
| count quá chậm | Query/count phức tạp trên tập lớn | Đánh giá Slice và nhu cầu tổng số thật. |
| Có dữ liệu tenant khác trong kết quả | Filter thiếu tenantId | Ràng buộc tenant ở mọi đường truy vấn và kiểm thử. |
| Derived query và @Query cho kết quả khác | Khác filter, field name, sort hoặc null semantics | So sánh query thật trên cùng fixture. |

### 19.1. Quy trình chẩn đoán

1. Xác nhận database và collection thực sự được repository sử dụng.
2. Đọc nguyên biểu thức @Query, số lượng và thứ tự **?0, ?1**.
3. Xác nhận kiểu dữ liệu truyền vào (ObjectId, String, long, Instant, Collection).
4. Xem document BSON thật, bao gồm field thiếu/null, mảng và object lồng nhau.
5. Chạy filter tương đương trong mongosh và so sánh các document trả về.
6. Kiểm tra projection, sort, Pageable, count/exists và các điều kiện tenant.
7. Với truy vấn chậm, dùng **explain("executionStats")** và xem index/workload; không kết luận chỉ từ số dòng annotation.
8. Thêm test hồi quy với fixture tái hiện lỗi.

## 20. Bài tập thực hành

### Bài tập 1: bind hai tham số

Viết repository method nhận category và active để tìm sản phẩm phù hợp.

**Gợi ý đáp án:**

~~~java
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findByCategoryAndState(
    String category, boolean active
);
~~~

### Bài tập 2: khoảng giá

Yêu cầu tìm product có giá từ 20.000 đến dưới 100.000 đơn vị tiền nhỏ nhất. Vì sao sử dụng $lte ở phía trên có thể sai?

**Gợi ý đáp án:** dùng **$gte: ?0** và **$lt: ?1**, với tham số 20_000L và 100_000L. Nếu dùng $lte, giá đúng bằng 100.000 cũng được trả về, trái với yêu cầu dưới 100.000.

### Bài tập 3: query mảng

Yêu cầu product chứa đồng thời tags JAVA và SPRING. Nên dùng $in hay $all?

**Đáp án:** dùng **$all**, vì $in chỉ đòi ít nhất một giá trị nằm trong tập; $all đòi tất cả giá trị cần thiết có mặt.

### Bài tập 4: tìm dữ liệu thiếu field

Yêu cầu tìm product chưa có attributes.brand, không bao gồm document có brand = null. Dùng điều kiện nào?

**Đáp án:** dùng **{ 'attributes.brand': { '$exists': false } }** để tìm missing. Điều kiện so sánh bằng null có thể khớp cả missing và null nên không phù hợp với yêu cầu phân biệt.

### Bài tập 5: projection

API danh sách chỉ cần id, name và priceMinor. Có nên dùng fields chỉ lấy name rồi trả toàn bộ ProductDocument?

**Đáp án:** không. Dùng fields chọn **_id, name, priceMinor** và một DTO/interface projection tương ứng. Trả entity đầy đủ từ dữ liệu bị cắt field dễ gây lỗi hoặc mất dữ liệu nếu code tiếp tục save.

### Bài tập 6: tìm kiếm tên

Client nhập cụm ký tự tùy ý, API đang truyền trực tiếp vào $regex. Nêu hai rủi ro và cách cải thiện.

**Gợi ý đáp án:** regex metacharacters có thể làm đổi ý nghĩa tìm kiếm; regex phức tạp có thể tiêu tốn nhiều CPU/khó dùng index. Giới hạn độ dài, escape ký tự khi tìm literal, giới hạn kết quả và xem xét chức năng search phù hợp hơn.

### Bài tập 7: index cho filter và sort

API thường lọc category = BOOK, active = true, sort createdAt giảm dần. Đề xuất index cần đánh giá và cách kiểm chứng.

**Gợi ý đáp án:** thử compound index theo **category, active, createdAt**, có thể thêm _id theo khóa sort phụ. Chạy cùng filter/sort với explain("executionStats"), so sánh nReturned, keys/docs examined, sort stage và chi phí duy trì index.

### Bài tập 8: query và tenant

Trong hệ thống nhiều tenant, repository có method @Query chỉ lọc active. Vì sao nó có thể không an toàn dù placeholder được bind đúng?

**Đáp án:** vì thiếu điều kiện tenant và quyền truy cập. Bind đúng chỉ bảo vệ cách chuyển giá trị tham số, không tự thực thi chính sách phân tách dữ liệu. Cần filter tenant được xác minh và cơ chế bảo vệ nhất quán trên toàn bộ đường truy cập.

## 21. Nguyên tắc ghi nhớ

1. **@Query của Spring Data MongoDB** cho phép khai báo filter MongoDB JSON-like trực tiếp trong repository.
2. **?0, ?1... là placeholder theo vị trí bắt đầu từ 0**; không ghép input thô thành JSON và không đặt placeholder trong nháy như literal.
3. **Các toán tử MongoDB giữ nguyên ý nghĩa**: $gte/$lt cho khoảng, $or/$and cho logic, $in/$all/$elemMatch cho mảng.
4. **Kiểu BSON quyết định khả năng match**. ObjectId khác String; Instant cần được map đúng thành BSON Date; tiền phải thống nhất đơn vị và kiểu số.
5. **@Query(fields=...) thích hợp cho projection**, nhưng không nên lưu lại entity chỉ được tải một phần.
6. **Sort và Pageable cần giới hạn và index phù hợp**. Page/count có chi phí; regex và $in lớn cũng cần được kiểm soát.
7. **Count và exists không thay thế ràng buộc dữ liệu** như unique index hay chính sách bảo mật tenant.
8. **MongoTemplate và aggregation bổ sung cho @Query** khi cần filter động, update hoặc pipeline xử lý dữ liệu.
9. **Kiểm thử trên MongoDB và dùng explain** để xác nhận kết quả, hiệu năng, field mapping và các tình huống legacy.

Nắm chắc cách khai báo **@Query bằng biểu thức truy vấn MongoDB** giúp dịch vụ **SPRING_DATA_MONGODB** xây dựng repository có điều kiện tìm kiếm rõ ràng, bind tham số đúng kiểu và duy trì khả năng kiểm thử, tối ưu index, chẩn đoán truy vấn trong các luồng truy cập dữ liệu đồng bộ hoặc reactive.
