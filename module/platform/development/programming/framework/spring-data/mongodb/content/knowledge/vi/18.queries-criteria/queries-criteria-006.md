# elemMatch, all, size và điều kiện trên array

## 1. Tại sao truy vấn array cần tư duy khác truy vấn scalar?

Trong chương **Query và Criteria** của **Spring Data MongoDB**, array là một trong những nơi dễ tạo ra truy vấn **đúng cú pháp nhưng sai ý nghĩa**. MongoDB cho phép một field BSON chứa mảng số, mảng chuỗi hoặc mảng document. Các toán tử như `$elemMatch`, `$all` và `$size` giúp trả lời những câu hỏi khác nhau về mảng đó.

Giả sử sản phẩm có danh sách biến thể theo màu và kho:

~~~json
{
  "_id": "p-101",
  "tags": ["outdoor", "premium"],
  "variants": [
    { "sku": "R-1", "color": "RED", "quantity": 2, "warehouse_code": "HCM" },
    { "sku": "B-1", "color": "BLUE", "quantity": 15, "warehouse_code": "HN" }
  ],
  "ratings": [2, 5]
}
~~~

Ba yêu cầu tưởng giống nhau nhưng có ngữ nghĩa riêng:

1. **Có ít nhất một biến thể vừa màu đỏ vừa còn từ 10 sản phẩm?** Dùng `$elemMatch` để buộc các điều kiện nằm trên **cùng phần tử** của `variants`.
2. **Sản phẩm có đồng thời hai tag `outdoor` và `premium`?** Dùng `$all`, không phải `$in`.
3. **Sản phẩm có đúng hai biến thể?** Dùng `$size: 2`, không phải một phép so sánh độ dài mảng qua `$gte` trực tiếp bên trong `$size`.

Nếu viết:

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
});
~~~

MongoDB có thể trả về `p-101`: phần tử **đỏ** có số lượng 2, còn phần tử **xanh** có số lượng 15. Hai điều kiện dot path được thỏa bởi **hai phần tử khác nhau**. Muốn yêu cầu *cùng một biến thể*, cần biểu diễn rõ bằng `$elemMatch`.

Mục tiêu bài học là hiểu ngữ nghĩa toán tử array trên BSON, viết `Query`/`Criteria` qua `MongoTemplate`, xác minh mapping tên field, kiểm tra trường hợp rỗng/null/thiếu và phân tích hiệu năng với **multikey index**. Bài không chỉ nêu cú pháp mà còn hướng dẫn cách kiểm thử để phát hiện false positive.

> Các ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Cấu trúc BSON trong bài là biểu diễn minh họa phù hợp với schema nêu ở đây; cần kiểm tra hành vi chính xác trên phiên bản MongoDB/Spring Data và dữ liệu thực tế của dự án.

## 2. Bảng chọn toán tử theo câu hỏi nghiệp vụ

| Câu hỏi | Điều kiện BSON điển hình | Ý nghĩa quan trọng |
|---|---|---|
Mảng `tags` có tag `outdoor`? | `{ "tags": "outdoor" }` | Equality với scalar có thể khớp một phần tử array |
Có tag `outdoor` **hoặc** `travel`? | `{ "tags": { "$in": ["outdoor", "travel"] } }` | Bất kỳ giá trị phù hợp nào |
Có cả `outdoor` **và** `premium`? | `{ "tags": { "$all": ["outdoor", "premium"] } }` | Mọi giá trị yêu cầu phải có mặt, không xét thứ tự |
Có đúng 2 tag? | `{ "tags": { "$size": 2 } }` | Độ dài mảng bằng đúng 2 |
Có biến thể màu đỏ? | `{ "variants.color": "RED" }` | Ít nhất một phần tử có màu đỏ |
Có biến thể **đỏ và số lượng ≥ 10**? | `{ "variants": { "$elemMatch": { "color": "RED", "quantity": { "$gte": 10 } } } }` | Hai điều kiện trên cùng một phần tử |
Có rating trong khoảng [4, 5)? | `{ "ratings": { "$elemMatch": { "$gte": 4, "$lt": 5 } } }` | Một số trong mảng đồng thời thỏa hai biên |
Field `tags` có tồn tại không? | `{ "tags": { "$exists": true } }` | Kiểm tra sự có mặt của field, không kiểm tra độ dài |

`$in`, `$all` và `$elemMatch` đều có thể áp dụng trong ngữ cảnh array nhưng **không thay thế lẫn nhau**. Truy vấn đúng phải phản ánh chính xác việc các điều kiện cần được thỏa bởi *bất kỳ phần tử*, *tất cả giá trị yêu cầu* hay *một phần tử duy nhất*.

## 3. Mô hình Spring Data MongoDB dùng chung

Để chạy code, giả sử ứng dụng có `spring-boot-starter-data-mongodb`, MongoDB URI phù hợp và package `com.example.catalog` nằm trong phạm vi Spring Boot quét. Các kiểu được tạo thành những file Java tương ứng; bài viết sử dụng `MongoTemplate` để xây dựng truy vấn typed.

**Variant.java** — một document con trong mảng:

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.mapping.Field;

public record Variant(
        String sku,
        String color,
        int quantity,
        @Field("warehouse_code") String warehouseCode) {
}
~~~

**CatalogProduct.java** — document gốc:

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
        @Field("display_name") String name,
        String status,
        List<String> tags,
        List<Variant> variants,
        List<Integer> ratings,
        Instant createdAt) {
}
~~~

Những lựa chọn có chủ đích:

- `@MongoId(FieldType.STRING)` giữ `_id` là BSON String; điều kiện theo property Java `id` sẽ được ánh xạ sang `_id`.
- `@Field("display_name")` và `@Field("warehouse_code")` chứng minh mapping có thể áp dụng cả ở document gốc lẫn document con.
- `tags` là `List<String>`, `ratings` là `List<Integer>`, còn `variants` là `List<Variant>`; chúng được lưu thành các mảng BSON có kiểu phần tử khác nhau.
- `Variant` không cần `@Document` riêng vì được nhúng trong document `CatalogProduct`. Nó không tự có collection hoặc `_id` riêng.
- Trong ví dụ, `quantity` không âm và `createdAt` là thời điểm tạo; đây là quy tắc nghiệp vụ cần được xác thực ở tầng ứng dụng, không phải một bảo đảm do List tạo ra.

### Ba document để đối chiếu kết quả

**Sản phẩm p-101** có màu đỏ *ít hàng* và màu xanh *nhiều hàng*:

~~~json
{
  "_id": "p-101",
  "display_name": "Bình giữ nhiệt",
  "status": "ACTIVE",
  "tags": ["outdoor", "premium"],
  "variants": [
    { "sku": "R-1", "color": "RED", "quantity": 2, "warehouse_code": "HCM" },
    { "sku": "B-1", "color": "BLUE", "quantity": 15, "warehouse_code": "HN" }
  ],
  "ratings": [2, 5],
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**Sản phẩm p-102** có biến thể đỏ đủ hàng:

~~~json
{
  "_id": "p-102",
  "display_name": "Túi dã ngoại",
  "status": "ACTIVE",
  "tags": ["outdoor", "premium", "new"],
  "variants": [
    { "sku": "R-2", "color": "RED", "quantity": 12, "warehouse_code": "HCM" },
    { "sku": "B-2", "color": "BLUE", "quantity": 0, "warehouse_code": "HN" }
  ],
  "ratings": [4],
  "createdAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

**Sản phẩm p-103** có các mảng rỗng:

~~~json
{
  "_id": "p-103",
  "display_name": "Sổ tay",
  "status": "INACTIVE",
  "tags": ["premium"],
  "variants": [],
  "ratings": [],
  "createdAt": { "$date": "2026-11-20T10:00:00Z" }
}
~~~

Các truy vấn phía dưới sẽ chỉ rõ ID nào phải khớp. Khi xem kết quả từ MongoDB shell, dùng đúng tên BSON `display_name` và `warehouse_code`; trong code Java truyền `CatalogProduct.class`, ưu tiên đường dẫn property Java rồi để Spring Data mapping.

## 4. Kiểm tra có phần tử: equality, $in và dot notation

### 4.1. So khớp một giá trị trong array

Đối với mảng scalar như `tags`:

~~~javascript
db.catalog_products.find({ tags: "outdoor" });
~~~

Truy vấn trả `p-101` và `p-102` vì trong mỗi mảng `tags` có phần tử bằng `"outdoor"`. Một filter equality theo scalar **không yêu cầu toàn bộ array bằng scalar**.

Code Java tương đương:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> tagged(
        MongoTemplate mongo, String tag) {
    return mongo.find(
            Query.query(Criteria.where("tags").is(tag)),
            CatalogProduct.class);
}
~~~

Khi yêu cầu **toàn bộ mảng có đúng cấu trúc/thứ tự cho trước**, phép bằng với một mảng khác có semantics riêng và nhạy cảm thứ tự. Không dùng nó để thay thế `$all` khi thứ tự không quan trọng. Nếu dữ liệu có mảng lồng nhau, cách MongoDB so sánh array cũng phải được xem xét theo schema thực tế.

### 4.2. $in là OR trên tập giá trị

~~~javascript
db.catalog_products.find({
  tags: { $in: ["outdoor", "travel"] }
});
~~~

Một sản phẩm được trả nếu có **ít nhất một tag** nằm trong tập tìm kiếm. Đây là phép “có outdoor **hoặc** travel”, không yêu cầu cả hai.

Spring Data Criteria:

~~~java
Query query = Query.query(
        Criteria.where("tags").in("outdoor", "travel"));
List<CatalogProduct> matches =
        mongo.find(query, CatalogProduct.class);
~~~

Nếu API nhận một danh sách giá trị do client gửi, cần validate số phần tử, độ dài và kiểu dữ liệu. Một `$in` chứa hàng nghìn phần tử có thể làm query lớn và không tối ưu; cần phân lô hoặc thiết kế truy vấn khác nếu vượt phạm vi sử dụng thông thường.

### 4.3. Dot notation trên array document

~~~javascript
db.catalog_products.find({
  "variants.color": "RED"
});
~~~

Dot notation tìm document có **ít nhất một phần tử mảng** chứa `color = RED`. Trong Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("variants.color").is("RED"));
List<CatalogProduct> redProducts =
        mongo.find(query, CatalogProduct.class);
~~~

Điều này phù hợp khi chỉ có một điều kiện cần kiểm tra trên mỗi biến thể. Nhưng khi ghép các điều kiện khác nhau, cần xác định chúng phải đúng **trên cùng phần tử** hay chỉ đúng **ở đâu đó trong mảng**.

## 5. $elemMatch: các điều kiện phải đúng trên cùng một phần tử

### 5.1. Phản ví dụ: hai dot path có thể khớp hai phần tử khác nhau

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
});
~~~

Với dữ liệu mục 3, truy vấn trả cả `p-101` và `p-102`:

- `p-101`: biến thể đỏ có `quantity = 2`, biến thể xanh có `quantity = 15`. Hai điều kiện độc lập vẫn khớp.
- `p-102`: biến thể đỏ có `quantity = 12`. Hai điều kiện cùng khớp trên một biến thể.

Nếu người dùng muốn mua **sản phẩm màu đỏ còn ít nhất 10 chiếc**, `p-101` là **false positive**.

### 5.2. Viết đúng bằng $elemMatch

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: {
      color: "RED",
      quantity: { $gte: 10 }
    }
  }
});
~~~

Kết quả chỉ có `p-102`. Dưới `$elemMatch`, cả `color` và `quantity` phải được thỏa bởi **một phần tử document duy nhất** trong `variants`.

Java với `Criteria.elemMatch(...)`:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> redVariantsWithStock(
        MongoTemplate mongo, int minimumQuantity) {
    Criteria sameVariant = Criteria.where("variants").elemMatch(
            Criteria.where("color").is("RED")
                    .and("quantity").gte(minimumQuantity));

    return mongo.find(
            Query.query(sameVariant), CatalogProduct.class);
}
~~~

Với `minimumQuantity = 10`, kết quả là `p-102`. Chú ý `Criteria.where("variants")` xác định tên **mảng**; phần nằm bên trong `elemMatch` mô tả điều kiện của **phần tử**.

### 5.3. Kiểm tra nested field có @Field

Muốn tìm sản phẩm có biến thể **nằm ở kho HCM và còn hàng**, thêm `warehouseCode`:

~~~java
Criteria inStockAtHcm = Criteria.where("variants").elemMatch(
        Criteria.where("warehouseCode").is("HCM")
                .and("quantity").gt(0));

Query query = Query.query(inStockAtHcm);
List<CatalogProduct> products =
        mongo.find(query, CatalogProduct.class);
~~~

Trong Java, property là `warehouseCode`; trong BSON là `warehouse_code` vì annotation trên `Variant`. Với typed query `CatalogProduct.class`, Spring Data áp dụng metadata mapping của document con để hình thành điều kiện tương đương:

~~~json
{
  "variants": {
    "$elemMatch": {
      "warehouse_code": "HCM",
      "quantity": { "$gt": 0 }
    }
  }
}
~~~

Đừng mặc định `query.getQueryObject()` trước khi thực thi phản ánh **đầy đủ** tên field sau mapping; việc ánh xạ entity được áp dụng trong đường thực thi. Khi cần xác nhận, hãy quan sát command BSON hoặc chạy test trên raw document.

### 5.4. $elemMatch với mảng số

`$elemMatch` không chỉ dành cho mảng object. Với `ratings`, yêu cầu có **một rating từ 4 đến dưới 5**:

~~~javascript
db.catalog_products.find({
  ratings: {
    $elemMatch: { $gte: 4, $lt: 5 }
  }
});
~~~

Kết quả `p-102` (có rating 4), còn `p-101` không khớp dù mảng `[2, 5]` có một phần tử nhỏ hơn 5 và một phần tử lớn hơn hoặc bằng 4.

Trong Spring Data:

~~~java
Criteria oneRatingInRange = Criteria.where("ratings")
        .elemMatch(new Criteria().gte(4).lt(5));

List<CatalogProduct> rated =
        mongo.find(Query.query(oneRatingInRange), CatalogProduct.class);
~~~

So với hai điều kiện độc lập:

~~~javascript
db.catalog_products.find({
  ratings: { $gte: 4, $lt: 5 }
});
~~~

trong trường hợp field là mảng, các điều kiện độc lập không nên được hiểu là bắt buộc cùng một giá trị đáp ứng cả hai biên. `$elemMatch` biểu đạt yêu cầu “cùng phần tử” rõ ràng.

### 5.5. $elemMatch cũng yêu cầu field là array

Một document có `variants` là **object đơn** thay vì array có thể khớp một số điều kiện dot notation, nhưng `$elemMatch` đòi hỏi một phần tử trong array để kiểm tra. Điều này giúp phát hiện sự khác biệt schema. Đừng dựa vào `$elemMatch` để tự chuyển một object đơn thành mảng.

Với chỉ một điều kiện trên nested field, dot notation và `$elemMatch` đôi khi cho kết quả tương tự khi schema đúng, nhưng không nên coi chúng tương đương trong mọi trường hợp **mảng không tồn tại, kiểu sai hoặc có giá trị đặc biệt**.

## 6. $all: mảng chứa mọi giá trị được yêu cầu

Để tìm sản phẩm vừa có tag `outdoor` vừa có tag `premium`:

~~~javascript
db.catalog_products.find({
  tags: { $all: ["outdoor", "premium"] }
});
~~~

Kết quả là `p-101` và `p-102`. `p-103` chỉ có `premium` nên không khớp.

Spring Data Criteria:

~~~java
Query query = Query.query(
        Criteria.where("tags").all("outdoor", "premium"));

List<CatalogProduct> matches =
        mongo.find(query, CatalogProduct.class);
~~~

`$all` không yêu cầu các tag được lưu theo cùng thứ tự đầu vào. Một mảng `["premium", "outdoor"]` cũng đáp ứng yêu cầu. Nó cũng không phải phép so sánh **đúng bằng tập**: mảng `["premium", "outdoor", "new"]` vẫn khớp, nên `p-102` được trả về.

### 6.1. So sánh all, in và equality

| Dữ liệu `tags` | `tags: "outdoor"` | `$in: ["outdoor", "travel"]` | `$all: ["outdoor", "premium"]` |
|---|---|---|---|
| `["outdoor", "premium"]` | Có | Có | Có |
| `["outdoor", "premium", "new"]` | Có | Có | Có |
| `["premium"]` | Không | Không | Không |
| `["travel"]` | Không | Có | Không |
| `[]` | Không | Không | Không |

Nếu collection chứa các tag trùng lặp, `$all` được dùng để kiểm tra **sự hiện diện của các giá trị yêu cầu**, không phải đếm bao nhiêu lần một tag xuất hiện. Nếu cần “tag A xuất hiện hai lần”, mô hình dữ liệu hoặc cách đếm phải biểu diễn thêm yêu cầu đó.

### 6.2. Đừng biến danh sách lựa chọn trống thành $all rỗng

Trong API tìm kiếm, nếu người dùng không chọn tag nào, **không nên tự động sinh điều kiện `$all: []`** rồi kỳ vọng MongoDB coi đó là “không lọc”. Hãy quyết định rõ: danh sách tag trống nghĩa là **bỏ điều kiện tags**, hay là một lỗi input? Chỉ thêm `Criteria.where("tags").all(...)` khi có yêu cầu phù hợp.

Ví dụ xây query động:

~~~java
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query searchByAllTags(Collection<String> requiredTags) {
    Query query = Query.query(Criteria.where("status").is("ACTIVE"));

    if (requiredTags != null && !requiredTags.isEmpty()) {
        query.addCriteria(Criteria.where("tags").all(requiredTags));
    }
    return query;
}
~~~

Đây là phương thức xây dựng Query. Ứng dụng phải giới hạn độ dài danh sách và hợp đồng chuẩn hóa tag; nếu không, filter không mong đợi hoặc truy vấn quá lớn có thể xuất hiện.

### 6.3. $all với nhiều $elemMatch

Trong trường hợp cần tìm sản phẩm có **một biến thể đỏ còn hàng** *và* **một biến thể xanh còn hàng**, ta có thể viết:

~~~javascript
db.catalog_products.find({
  variants: {
    $all: [
      { $elemMatch: { color: "RED", quantity: { $gt: 0 } } },
      { $elemMatch: { color: "BLUE", quantity: { $gt: 0 } } }
    ]
  }
});
~~~

`p-101` khớp vì có biến thể đỏ 2 chiếc và biến thể xanh 15 chiếc. `p-102` không khớp vì biến thể xanh có `quantity = 0`.

**Hai `$elemMatch` nằm trong `$all` có thể được thỏa bởi hai phần tử khác nhau.** Đây chính là ý định “phải tồn tại một phần tử thỏa nhóm A và một phần tử thỏa nhóm B”. Trái lại, **một `$elemMatch`** với cả hai nhóm chỉ phù hợp khi điều kiện có thể cùng đúng trên một phần tử.

## 7. $size: độ dài array phải bằng đúng một giá trị

MongoDB dùng `$size` để kiểm tra số **phần tử trực tiếp** trong array:

~~~javascript
db.catalog_products.find({
  variants: { $size: 2 }
});
~~~

Kết quả là `p-101` và `p-102`, vì mỗi document có hai biến thể. `p-103` có `variants: []` nên chỉ khớp `$size: 0`.

Trong Java:

~~~java
Query withTwoVariants = Query.query(
        Criteria.where("variants").size(2));

List<CatalogProduct> products =
        mongo.find(withTwoVariants, CatalogProduct.class);
~~~

`$size` đếm phần tử ngay bên dưới `variants`, **không** đếm số field của một biến thể, không cộng tất cả `quantity` và không đếm số document trong collection. Nếu mỗi phần tử là một document lồng, độ dài mảng vẫn tính mỗi document là một phần tử.

### 7.1. Không có cú pháp $size: { $gte: ... }

Yêu cầu “có ít nhất 3 biến thể” **không thể viết**:

~~~javascript
// Sai ngữ nghĩa/cú pháp: $size dùng một số đếm chính xác, không nhận $gte.
db.catalog_products.find({
  variants: { $size: { $gte: 3 } }
});
~~~

Nếu cần đếm tương đối, phải chọn giải pháp khác:

- Một filter theo **vị trí phần tử thứ ba** như `{ "variants.2": { "$exists": true } }` có thể phát hiện array dài ít nhất 3 trong schema mảng nhất quán; đây là kỹ thuật dựa trên chỉ số mảng, không phải query đếm tổng quát cho mọi kiểu field.
- Dùng `$expr` kết hợp toán tử aggregation `$size` và phép so sánh.
- Nếu thường xuyên lọc theo độ dài, cân nhắc lưu field `variantCount` được đồng bộ nhất quán khi thêm/xóa biến thể và tạo index phù hợp. Giá trị đếm denormalized có thể bị sai nếu có đường ghi bỏ qua cơ chế đồng bộ.

Ví dụ `$expr` với `$ifNull` để coi mảng thiếu hoặc null là mảng rỗng:

~~~javascript
db.catalog_products.find({
  $expr: {
    $gte: [
      { $size: { $ifNull: ["$variants", []] } },
      3
    ]
  }
});
~~~

Đoạn này giả sử `variants` khi tồn tại là **array hoặc null**. Nếu schema lỗi và `variants` là scalar/document không phải array, `$size` trong expression vẫn có thể gây lỗi; phải validate hoặc dùng điều kiện `$isArray`/`$cond` thích hợp.

### 7.2. Chi phí hiệu năng của $size

Index multikey không tự tạo một chỉ số đếm số phần tử cho mỗi document để `$size` suy ra số lượng trực tiếp từ index. Những truy vấn theo độ dài mảng có thể cần kiểm tra các document ứng viên và khó tận dụng index cho **phần độ dài**. Đo bằng `explain("executionStats")`, đặc biệt khi collection lớn và `$size` là điều kiện lọc chủ đạo.

Nếu yêu cầu nghiệp vụ là “ít nhất một biến thể” và schema đảm bảo `variants` luôn là array, các cách như `"variants.0": { "$exists": true }` có thể phù hợp, nhưng cần test null/missing và cân nhắc khi schema không nhất quán.

## 8. Kết hợp elemMatch, all, size với filter và sort

Ví dụ tìm **sản phẩm ACTIVE**, có cả hai tag `outdoor` và `premium`, đồng thời có **một biến thể tại kho HCM còn hàng**:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductArraySearchService {
    private final MongoTemplate mongo;

    public ProductArraySearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> findAvailableAtHcm() {
        Criteria conditions = new Criteria().andOperator(
                Criteria.where("status").is("ACTIVE"),
                Criteria.where("tags").all("outdoor", "premium"),
                Criteria.where("variants").elemMatch(
                        Criteria.where("warehouseCode").is("HCM")
                                .and("quantity").gt(0)));

        Query query = Query.query(conditions);
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        query.limit(20);

        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

Đoạn code dùng `Criteria.andOperator` để ghép các điều kiện cấp document. `$elemMatch` chỉ đặt ranh giới **cùng phần tử** cho điều kiện kho và tồn kho; yêu cầu về tag vẫn áp dụng trên mảng `tags` riêng.

Ý nghĩa BSON tương đương:

~~~json
{
  "$and": [
    { "status": "ACTIVE" },
    { "tags": { "$all": ["outdoor", "premium"] } },
    {
      "variants": {
        "$elemMatch": {
          "warehouse_code": "HCM",
          "quantity": { "$gt": 0 }
        }
      }
    }
  ]
}
~~~

Trên ba document mẫu, `p-101` và `p-102` đều khớp vì cả hai có ít nhất một biến thể HCM với số lượng lớn hơn 0. Nếu đổi điều kiện sang `quantity >= 10`, chỉ `p-102` khớp.

Khi xây filter từ request HTTP, đừng nhận tên field hoặc toán tử BSON tùy ý từ client rồi ghép thành raw JSON. Hãy whitelist điều kiện được hỗ trợ, validate giá trị, thêm điều kiện tenant từ ngữ cảnh xác thực và giới hạn `limit`.

## 9. $elemMatch trong filter khác $elemMatch trong projection

Một điều rất dễ nhầm:

- **`$elemMatch` ở phần query filter:** xác định **document nào khớp** dựa trên ít nhất một phần tử mảng thỏa điều kiện.
- **`$elemMatch` ở phần projection của lệnh find:** hạn chế **phần array trả về** thành **phần tử phù hợp đầu tiên** theo điều kiện projection.

### 9.1. Filter không tự cắt mảng trong kết quả

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: { color: "RED", quantity: { $gte: 10 } }
  }
});
~~~

Truy vấn chỉ trả `p-102`, nhưng document trả về **vẫn có thể chứa toàn bộ mảng `variants`** với cả biến thể đỏ và xanh, trừ khi lệnh có một projection thích hợp.

### 9.2. Projection lấy một phần tử khớp

~~~javascript
db.catalog_products.find(
  { _id: "p-102" },
  {
    display_name: 1,
    variants: { $elemMatch: { color: "RED", quantity: { $gte: 10 } } }
  }
);
~~~

Khi phần tử khớp tồn tại, phần `variants` trong kết quả projection chỉ gồm **phần tử đầu tiên đáp ứng điều kiện**, không phải mọi phần tử đỏ. Nếu ứng dụng cần tất cả các phần tử phù hợp, hãy cân nhắc aggregation `$filter` và xác định projection output rõ ràng.

Spring Data `Query.fields()` có API projection liên quan `elemMatch` ở các phiên bản hỗ trợ. Tuy nhiên, filter và projection phải được kiểm thử riêng: API repository trả đúng entity không đồng nghĩa client chỉ nhận các phần tử mảng được quan tâm.

**Không lưu lại** một entity được đọc bằng field projection thiếu các phần tử khác thông qua `save` như thể đó là toàn bộ document. Điều đó có thể thay thế/mất các phần tử chưa được tải.

## 10. Mảng rỗng, null, field thiếu và kiểu dữ liệu sai

Không phải mọi document lịch sử đều có schema chuẩn. Các biến thể sau cần được phân biệt:

~~~json
{ "_id": "legacy-missing" }
~~~

~~~json
{ "_id": "legacy-null", "tags": null }
~~~

~~~json
{ "_id": "legacy-empty", "tags": [] }
~~~

~~~json
{ "_id": "legacy-one", "tags": ["outdoor"] }
~~~

| Điều kiện | Missing | Null | `[]` | `["outdoor"]` |
|---|---|---|---|---|
| `{ "tags": { "$exists": true } }` | Không | Có | Có | Có |
| `{ "tags": null }` | Có | Có | Không | Không |
| `{ "tags": { "$size": 0 } }` | Không | Không | Có | Không |
| `{ "tags": "outdoor" }` | Không | Không | Không | Có |
| `{ "tags": { "$all": ["outdoor"] } }` | Không | Không | Không | Có |

Nếu cần đúng **array rỗng**, `$size: 0` thể hiện ý định rõ hơn `tags = null`. Nếu muốn phân biệt **field không tồn tại** với **field có giá trị null**, phải dùng toán tử phù hợp, chẳng hạn kết hợp `$exists` và kiểm tra null; tránh mặc định hai trường hợp là một.

Một field scalar `tags: "outdoor"` có thể khớp equality theo chuỗi nhưng không phải một array hợp lệ của schema. Khi bộ lọc phụ thuộc loại array, có thể cần dùng `$type: "array"` hoặc validation/schema migration để không trộn hai representation.

### 10.1. Null trong mảng và phần tử document thiếu property

Array có thể chứa `null` hoặc một document con thiếu field. Với `List<Variant>`, khi đọc về Java, converter có thể materialize phần tử với giá trị null/default hoặc thất bại nếu constructor/constraint không tương thích. Query theo `variants.quantity` cũng có ngữ nghĩa khác với trường hợp một phần tử thực sự có số lượng 0.

Không dùng `int quantity` trong record rồi mặc định việc thiếu field ở document lịch sử luôn hợp lệ. Nếu dữ liệu cũ có schema không đồng nhất, cần migration hoặc kiểu nullable/validation được thiết kế rõ.

### 10.2. Array có thứ tự và tính trùng lặp

MongoDB giữ thứ tự các phần tử mảng khi lưu. Tuy nhiên:

- `$all` kiểm tra sự hiện diện của giá trị, không yêu cầu cùng thứ tự.
- `$size` đếm cả các phần tử trùng lặp.
- `$elemMatch` quan tâm phần tử thỏa điều kiện, không yêu cầu phần tử đầu tiên, trừ khi kết quả được projection theo cách riêng.
- Nếu nghiệp vụ yêu cầu thứ tự các biến thể, vị trí trong array là dữ liệu có nghĩa; cập nhật mảng phải giữ chính sách thứ tự hoặc một trường `position` tường minh.

## 11. Index multikey và hiệu năng truy vấn array

Khi tạo index trên một field chứa array, MongoDB sử dụng cơ chế **multikey index**. Thay vì một khóa index duy nhất cho cả mảng, các giá trị phần tử có thể tham gia index để hỗ trợ các điều kiện truy vấn.

Ví dụ các index ứng viên:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, tags: 1 },
  { name: "idx_status_tags" }
);

db.catalog_products.createIndex(
  { status: 1, "variants.color": 1, "variants.quantity": 1 },
  { name: "idx_status_variant_color_qty" }
);
~~~

Index thứ hai truy cập hai field **cùng nguồn từ mảng `variants`**. Compound multikey index có ràng buộc đối với việc index **nhiều array độc lập** trong cùng một document; không thể tùy ý ghép mọi field array vào một compound index mà mong MongoDB chấp nhận.

### 11.1. $elemMatch còn liên quan cách MongoDB xét index bounds

Khi có nhiều điều kiện trên các field trong cùng array of documents, `$elemMatch` không chỉ sửa ngữ nghĩa *cùng phần tử*, mà còn có thể giúp query planner sử dụng **bounds kết hợp** trên một multikey index phù hợp. Tuy nhiên, việc tối ưu thực tế phụ thuộc vào index path, cấu trúc array, MongoDB version, filter và selectivity. Không suy luận rằng mọi truy vấn `$elemMatch` đều nhanh hơn.

So sánh:

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: {
      color: "RED",
      quantity: { $gte: 10 }
    }
  }
}).explain("executionStats");
~~~

với:

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
}).explain("executionStats");
~~~

Hai truy vấn **khác ngữ nghĩa**, nên không đánh giá hiệu năng một cách tách rời vấn đề tính đúng đắn. Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và thời gian thực thi trên dữ liệu đại diện.

### 11.2. Index không tự tối ưu mọi trường hợp $all hoặc $size

- Với `$all` trên tag, index multikey của `tags` có thể có ích, nhưng hiệu quả còn phụ thuộc số tag bắt buộc, tần suất từng tag và cách planner thực hiện intersection.
- Với `$size`, index không tự cung cấp thông tin độ dài array của từng document để lọc nhanh bằng một phép index lookup thông thường.
- Khi sort theo `createdAt` trong truy vấn vừa lọc mảng, có thể cần index khác hoặc sort stage; thiết kế index phải bám **query thực tế**, không chỉ một filter đơn lẻ.
- Index của mảng dài làm tăng số index entries và chi phí update; cần giới hạn kích thước mảng và đo write amplification.

Nếu mảng có hàng chục nghìn phần tử và liên tục tăng, hãy xem xét **tách sang collection riêng** với khóa tham chiếu tới document cha. MongoDB giới hạn kích thước một BSON document ở **16 MiB**; ngay trước giới hạn đó, index và chi phí cập nhật có thể đã trở thành vấn đề.

## 12. Khi nào nên dùng aggregation thay vì Criteria đơn giản?

`Criteria` với `$elemMatch`, `$all` và `$size` rất phù hợp khi mục tiêu là **chọn document**. Nhưng nếu cần:

1. Chỉ trả **tất cả biến thể** đáp ứng một điều kiện, không phải toàn bộ array.
2. Tính **số biến thể còn hàng** thay vì số biến thể tổng.
3. Tổng hợp `quantity` của các biến thể thuộc một kho.
4. Nhóm sản phẩm theo thuộc tính trong array.

thì aggregation thường rõ hơn. Ví dụ dùng `$filter` để giữ các biến thể có `quantity >= 10` trong kết quả:

~~~javascript
db.catalog_products.aggregate([
  { $match: { status: "ACTIVE" } },
  {
    $project: {
      display_name: 1,
      availableVariants: {
        $filter: {
          input: "$variants",
          as: "v",
          cond: { $gte: ["$$v.quantity", 10] }
        }
      }
    }
  }
]);
~~~

Ở đây `$match` chọn document, còn `$project` với `$filter` biến đổi mảng **trong kết quả**. Nếu tài liệu có `variants` null/missing hoặc sai kiểu, phải kiểm tra cách `$filter` xử lý để có chính sách fallback phù hợp. `$lookup` là một stage khác dùng để liên kết collection, không phải giải pháp trực tiếp cho toán tử array khi dữ liệu đã nhúng.

Với Spring Data có thể biểu diễn pipeline bằng `Aggregation`/`MongoTemplate.aggregate`; cú pháp builder cụ thể phụ thuộc phép biến đổi và phiên bản. Đừng cố nhồi logic lọc phần tử hoặc tính tổng phức tạp vào một derived repository method khi một pipeline rõ ràng sẽ dễ kiểm thử hơn.

## 13. Tác động tới cập nhật array và tính nhất quán

Truy vấn đúng cùng phần tử **không tự động đồng nghĩa** cập nhật đúng phần tử. Ví dụ:

~~~javascript
db.catalog_products.updateOne(
  {
    _id: "p-102",
    variants: { $elemMatch: { sku: "R-2", quantity: { $gte: 2 } } }
  },
  { $inc: { "variants.$.quantity": -2 } }
);
~~~

Ví dụ này dùng **positional operator `$`** gắn với phần tử của array thỏa điều kiện tìm kiếm trong dạng cập nhật được MongoDB hỗ trợ. Các trường hợp nhiều mảng, nhiều phần tử hoặc điều kiện phức tạp có thể cần `$[]` hoặc `$[identifier]` cùng `arrayFilters`.

Một lựa chọn tường minh để thay đổi nhiều phần tử theo điều kiện:

~~~javascript
db.catalog_products.updateOne(
  { _id: "p-102" },
  { $set: { "variants.$[v].quantity": 0 } },
  {
    arrayFilters: [
      { "v.warehouse_code": "HN" }
    ]
  }
);
~~~

Đoạn này **đổi số lượng của mọi biến thể ở kho HN thành 0**, không phải chỉ phần tử đầu tiên. Sự khác nhau giữa filter chọn **document** và array filter chọn **phần tử để sửa** phải được hiểu rõ.

Với `MongoTemplate.Update` và array filters, cần kiểm tra quy tắc mapping field name trong array filter của API/phiên bản; một số đường truyền array filter dùng BSON/raw document mà không mapping lại tên property. Khi sử dụng `@Field("warehouse_code")`, đọc command BSON thật trước khi triển khai.

MongoDB bảo đảm tính nguyên tử của một thao tác cập nhật **trên một document**, nhưng không bảo đảm hai thao tác đọc/sửa/ghi riêng rẽ không xảy ra lost update. Khi quantity là tồn kho, thêm điều kiện đủ hàng vào lệnh cập nhật và kiểm tra matched/modified count thay vì chỉ đọc trước rồi trừ sau.

## 14. Kiểm thử array query trên MongoDB thật

Unit test chỉ gọi builder `Criteria` không chứng minh điều kiện BSON sẽ được Spring Data mapping đúng với `@Field`, hoặc MongoDB sẽ diễn giải `$elemMatch` đúng trong array thực. Nên có integration test sử dụng MongoDB thật, ví dụ Testcontainers. Với Spring Boot 3.x, `@DataMongoTest` chuẩn bị hạ tầng MongoDB cho test nhưng **không tự chạy MongoDB server**.

### 14.1. Seed dữ liệu có chủ đích tạo false positive

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
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ArrayCriteriaIntegrationTest {

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void seed() {
        // Chỉ xóa trong database test được cô lập.
        mongo.remove(new Query(), CatalogProduct.class);

        mongo.insert(new CatalogProduct(
                "p-101", "Bình giữ nhiệt", "ACTIVE",
                List.of("outdoor", "premium"),
                List.of(
                        new Variant("R-1", "RED", 2, "HCM"),
                        new Variant("B-1", "BLUE", 15, "HN")),
                List.of(2, 5),
                Instant.parse("2026-11-20T08:00:00Z")));

        mongo.insert(new CatalogProduct(
                "p-102", "Túi dã ngoại", "ACTIVE",
                List.of("outdoor", "premium", "new"),
                List.of(
                        new Variant("R-2", "RED", 12, "HCM"),
                        new Variant("B-2", "BLUE", 0, "HN")),
                List.of(4),
                Instant.parse("2026-11-20T09:00:00Z")));

        mongo.insert(new CatalogProduct(
                "p-103", "Sổ tay", "INACTIVE",
                List.of("premium"),
                List.of(),
                List.of(),
                Instant.parse("2026-11-20T10:00:00Z")));
    }

    @Test
    void elemMatchRequiresTheSameVariant() {
        Query twoIndependentPaths = Query.query(
                Criteria.where("variants.color").is("RED")
                        .and("variants.quantity").gte(10));

        List<String> looselyMatchedIds =
                mongo.find(twoIndependentPaths, CatalogProduct.class)
                        .stream().map(CatalogProduct::id).toList();
        assertThat(looselyMatchedIds)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query sameElement = Query.query(
                Criteria.where("variants").elemMatch(
                        Criteria.where("color").is("RED")
                                .and("quantity").gte(10)));

        List<String> strictlyMatchedIds =
                mongo.find(sameElement, CatalogProduct.class)
                        .stream().map(CatalogProduct::id).toList();
        assertThat(strictlyMatchedIds)
                .containsExactly("p-102");
    }

    @Test
    void allSizeAndScalarElemMatchHaveDifferentMeanings() {
        Query hasAllTags = Query.query(
                Criteria.where("tags").all("outdoor", "premium"));
        assertThat(mongo.find(
                hasAllTags, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query hasTwoVariants = Query.query(
                Criteria.where("variants").size(2));
        assertThat(mongo.find(
                hasTwoVariants, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query ratingInRange = Query.query(
                Criteria.where("ratings")
                        .elemMatch(new Criteria().gte(4).lt(5)));
        assertThat(mongo.find(
                ratingInRange, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactly("p-102");
    }

    @Test
    void mapsNestedPropertyNameToActualBsonField() {
        Query atHcm = Query.query(
                Criteria.where("variants").elemMatch(
                        Criteria.where("warehouseCode").is("HCM")
                                .and("quantity").gte(10)));

        assertThat(mongo.find(atHcm, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactly("p-102");

        Document raw = mongo.getCollection("catalog_products")
                .find(new Document("_id", "p-102")).first();
        assertThat(raw).isNotNull();
        List<Document> rawVariants =
                raw.getList("variants", Document.class);
        assertThat(rawVariants).hasSize(2);
        assertThat(rawVariants.get(0).getString("warehouse_code"))
                .isEqualTo("HCM");
        assertThat(rawVariants.get(0).containsKey("warehouseCode"))
                .isFalse();
    }
}
~~~

Test được tổ chức để một yêu cầu truy vấn **sai ngữ nghĩa** (`variants.color` và `variants.quantity` độc lập) trả nhiều hơn yêu cầu **đúng ngữ nghĩa** (`$elemMatch`). Đây là kiểu test quan trọng hơn chỉ kiểm tra một sản phẩm khớp.

Nếu test chạy song song, cần database/collection riêng thay vì `remove(new Query(), ...)` trên collection dùng chung. Các kết quả được so sánh theo tập ID nếu truy vấn không có sort, tránh phụ thuộc thứ tự trả tự nhiên của MongoDB.

### 14.2. Kiểm tra null/missing bằng raw BSON

Để test document cũ thiếu array, có thể insert raw BSON vào collection **test**:

~~~java
mongo.getCollection("catalog_products").insertOne(
        new Document("_id", "legacy-missing")
                .append("status", "ACTIVE"));

boolean missingTags = mongo.exists(
        Query.query(Criteria.where("tags").exists(false)),
        CatalogProduct.class);

assertThat(missingTags).isTrue();
~~~

Đoạn này chỉ minh họa bổ sung **bên trong test** có MongoTemplate và AssertJ. Dùng `mongo.exists(...)` để kiểm tra điều kiện mà không phải materialize `CatalogProduct` có các field thiếu. Nếu cần phân biệt document cụ thể, thêm điều kiện ID để tránh khớp nhầm một bản ghi khác.

### 14.3. Quan sát BSON và query plan

Với driver, `CommandListener` có thể nhận `CommandStartedEvent` để quan sát lệnh `find` và field `filter`. Khi muốn xác minh `warehouseCode` đã được mapping thành `warehouse_code`, capture lệnh thực tế trên database test; không chỉ log `query.toString()` rồi suy ra mọi thao tác mapping đã áp dụng.

Trên MongoDB shell, dùng:

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: { color: "RED", quantity: { $gte: 10 } }
  }
}).explain("executionStats");
~~~

Từ đó so sánh số key/document được duyệt, index và độ trễ. Khi filter chứa dữ liệu người dùng hoặc dữ liệu nhạy cảm, không ghi toàn bộ command vào log production nếu chưa có chính sách bảo vệ.

## 15. Lỗi phổ biến và cách giải quyết

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
Ghép `variants.color` và `variants.quantity` rồi nghĩ cùng phần tử | False positive khi điều kiện nằm ở hai phần tử | Dùng một `$elemMatch` cho các điều kiện phải cùng đúng |
Nhầm `$in` với `$all` | OR thành AND hoặc ngược lại | Viết rõ “ít nhất một” hay “tất cả giá trị” |
Cho rằng `$all` yêu cầu chính xác tập, không có giá trị thừa | Trả document có tag bổ sung | Nếu cần exact-set, thiết kế thêm điều kiện độ dài/chuẩn hóa |
Cho rằng `$size` tính tổng `quantity` | Trả số biến thể thay vì tổng hàng | Dùng aggregation `$sum` hoặc field tổng được quản lý |
Viết `$size: { $gte: 3 }` | Truy vấn không hợp lệ | Dùng `$expr`/`$size` hoặc mô hình field đếm |
Dùng `tags: null` để tìm array rỗng | Lẫn null/missing với empty | Dùng `$size: 0` và test schema |
Giả định field tồn tại nghĩa là array có ít nhất một phần tử | Nhầm array rỗng và null | Dùng điều kiện array length/type phù hợp |
Không để ý `@Field` trên document con | Truy vấn raw dùng `warehouseCode` sai | Kiểm tra BSON `warehouse_code` thực tế |
Chỉ kiểm thử array có một phần tử | Không phát hiện điều kiện cross-element | Seed array có nhiều phần tử trái ngược nhau |
Nghĩ `$elemMatch` filter sẽ cắt array trả về | Trả cả array chứa dữ liệu không cần | Tách filter, projection và aggregation `$filter` |
Tạo compound index trên nhiều array độc lập | Vi phạm ràng buộc multikey hoặc chi phí ghi lớn | Thiết kế index theo đường dữ liệu thực tế |
Nghĩ `$size` đã được index tối ưu hoàn toàn | Quét quá nhiều document | Đo explain, cân nhắc field đếm được đồng bộ |
`save` entity chỉ tải một phần array | Mất phần tử chưa tải khi thay thế document | Dùng update/arrayFilters hoặc tải đầy đủ và kiểm soát concurrency |
Nhúng array phát triển vô hạn | Document lớn, tăng chi phí đọc/ghi, có thể vượt 16 MiB | Giới hạn mảng hoặc tách collection |

## 16. Bài tập thực hành

**Bài 1 — Tìm đúng cùng phần tử.** Tạo một document có biến thể RED số lượng 2 và BLUE số lượng 15. Chạy điều kiện `variants.color = RED` kết hợp `variants.quantity >= 10` rồi viết lại bằng `$elemMatch`. Giải thích vì sao kết quả thay đổi.

**Bài 2 — Tập tag.** Với `tags = ["outdoor", "premium", "new"]`, so sánh kết quả `$in` và `$all` khi yêu cầu `["outdoor", "premium"]`. Thử đảo thứ tự tag và thêm tag thứ tư; giải thích khác biệt giữa subset và exact-set.

**Bài 3 — Kích thước mảng.** Viết `Criteria.where("variants").size(0)`, `size(2)` và một query tìm ít nhất 3 phần tử. Test mảng rỗng, null, field thiếu và mảng gồm 3 document.

**Bài 4 — Nested @Field.** Thay tên Java `warehouseCode` bằng một property khác trong bản thử nghiệm, giữ field BSON theo `@Field("warehouse_code")`. Viết query typed bằng `MongoTemplate` rồi kiểm tra raw BSON. Giải thích vì sao sửa annotation không tự migrate document cũ.

**Bài 5 — Rating range.** Dùng dữ liệu `ratings = [2, 5]` và `ratings = [4]`. So sánh query hai điều kiện độc lập với `$elemMatch` cho khoảng [4, 5). Dùng integration test để chứng minh chỉ một rating thỏa cả hai biên.

**Bài 6 — Chỉ trả phần tử khớp.** Viết filter `$elemMatch` tìm document có biến thể RED còn hàng, sau đó dùng aggregation `$filter` để chỉ trả biến thể RED. Phân biệt kết quả “document khớp” và “mảng đầu ra đã được lọc”.

**Bài 7 — Index và explain.** Tạo index trên `status`, `variants.color`, `variants.quantity`; so sánh query dot path và `$elemMatch` với dữ liệu nhiều biến thể. Ghi lại `keysExamined`, `docsExamined`, thời gian và kết quả thực tế. Không kết luận một truy vấn “nhanh hơn” nếu nó trả sai tập tài liệu.

**Bài 8 — Cập nhật biến thể.** Thiết kế lệnh giảm số lượng một SKU chỉ khi đủ hàng. So sánh array positional operator với array filters, xác định điều kiện nguyên tử và matched/modified count. Kiểm thử đồng thời hai request trừ tồn kho của cùng biến thể.

## 17. Ghi nhớ

Trong **Spring Data MongoDB**, các truy vấn array phải diễn đạt đúng **mối quan hệ giữa phần tử và điều kiện**:

- `$in`: có **ít nhất một** giá trị thuộc tập.
- `$all`: mảng chứa **mọi giá trị yêu cầu**, không bắt buộc cùng thứ tự và vẫn cho phép giá trị bổ sung.
- `$size`: số phần tử trực tiếp của mảng **bằng chính xác** một số nguyên.
- `$elemMatch`: tồn tại **một phần tử** đồng thời thỏa các điều kiện bên trong, ngăn false positive từ nhiều phần tử khác nhau.

Với `MongoTemplate` và `Criteria`, hãy viết bằng **property Java** trên entity typed rồi kiểm tra cách `@Field` mapping sang BSON, đặc biệt với document con. Đừng nhầm `$elemMatch` ở phần filter với projection, đừng dùng `$size` như toán tử so sánh khoảng và đừng cho rằng index multikey giải quyết mọi truy vấn mảng.

Cuối cùng, hãy kiểm thử có chủ đích các trường hợp **mảng nhiều phần tử trái ngược, mảng rỗng, null, field thiếu, dữ liệu sai kiểu và cập nhật đồng thời**. Sự đúng đắn của tập kết quả luôn là ưu tiên trước khi tối ưu bằng multikey index, projection hoặc aggregation.
