# Collation cho collection, query và aggregation

> **Chương:** Collection và schema  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Hiểu collation ở cấp collection, index và từng thao tác; cấu hình đúng quy tắc so sánh chuỗi theo ngôn ngữ, chữ hoa/thường và dấu; dùng `Collation`, `Query.collation(...)`, `@Document`, `@Query` và `AggregationOptions`; kiểm tra ảnh hưởng tới `$match`, `$sort`, `$group`, unique index, query plan và migration.

## 1. Bài toán: một chuỗi, nhiều kết quả có thể đúng

Giả sử cửa hàng có ba tên sản phẩm:

~~~javascript
{ _id: "p701", display_name: "cafe" }
{ _id: "p702", display_name: "CAFÉ" }
{ _id: "p703", display_name: "Café" }
~~~

Câu hỏi “tìm sản phẩm tên `cafe`” **không có một đáp án duy nhất** nếu chưa xác định quy tắc so sánh:

- **So sánh nhị phân (`simple`):** `"cafe"` khác `"CAFÉ"` và `"Café"`.
- **Không phân biệt hoa/thường nhưng vẫn xét dấu** (ví dụ `locale:"en", strength:2`): `"CAFÉ"` tương đương `"Café"`; `"cafe"` không tương đương `"Café"`.
- **Không phân biệt cả hoa/thường lẫn dấu** (ví dụ `locale:"en", strength:1`): cả ba được coi tương đương cho các phép so sánh có hỗ trợ collation.

Tính năng **collation** của MongoDB cho phép xác định quy tắc này bằng ICU (International Components for Unicode). Collation ảnh hưởng không chỉ tới `find` mà còn tới **so sánh bằng, sắp xếp, phân nhóm, một số phép cập nhật/xóa theo điều kiện và ràng buộc duy nhất của index**.

~~~mermaid
flowchart TD
    A["Ứng dụng muốn so sánh display_name"] --> B{"Collation hiệu lực?"}
    B --> C["simple: so sánh nhị phân"]
    B --> D["en + strength 2: bỏ qua case, xét dấu"]
    B --> E["en + strength 1: bỏ qua case và dấu"]
    C --> F["$match / $sort / $group"]
    D --> F
    E --> F
    F --> G["Kết quả + khả năng dùng index tương ứng"]
~~~

**Ý quan trọng:** collation là **quy tắc so sánh**; nó không sửa chuỗi lưu trong document, không tự chuyển `"CAFÉ"` thành `"cafe"` và không phải công cụ tìm kiếm toàn văn.

## 2. Cấu trúc một collation document

MongoDB biểu diễn collation bằng một document:

~~~javascript
{
  locale: "en",
  strength: 2,
  caseLevel: false,
  caseFirst: "off",
  numericOrdering: false,
  alternate: "non-ignorable",
  backwards: false,
  normalization: false
}
~~~

`locale` là trường **bắt buộc** khi cung cấp collation. Các option khác tùy chọn; **giá trị mặc định có thể phụ thuộc locale**. Dùng `{locale:"simple"}` khi cần so sánh nhị phân.

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| `locale` | Quy tắc ngôn ngữ/ICU | `"en"`, `"fr"`, `"vi"`, `"simple"` |
| `strength` | Mức phân biệt ký tự, dấu, case | `1`, `2`, `3` |
| `caseLevel` | Có xét case riêng ở strength 1/2 | `true` hoặc `false` |
| `caseFirst` | Thứ tự ưu tiên hoa/thường khi áp dụng | `"upper"`, `"lower"`, `"off"` |
| `numericOrdering` | So sánh những phần số nguyên trong chuỗi theo giá trị | `true` |
| `alternate` | Cách xét khoảng trắng/dấu câu | `"shifted"` hoặc `"non-ignorable"` |
| `maxVariable` | Loại ký tự được coi là biến đổi khi `alternate:"shifted"` | `"space"`, `"punct"` |
| `backwards` | Xét dấu từ cuối chuỗi, dùng trong một số quy tắc ngôn ngữ | `true` |
| `normalization` | Kiểm tra/chuẩn hóa Unicode khi so sánh | `true` |

### 2.1. Strength 1, 2 và 3

| Mức | Phân biệt base letter | Phân biệt dấu/diacritic | Phân biệt hoa/thường mặc định |
| --- | --- | --- | --- |
| `strength:1` | Có | Không | Không |
| `strength:2` | Có | Có | Không |
| `strength:3` | Có | Có | Có |

Ở strength 1/2, có thể bật `caseLevel:true` để xét thêm chữ hoa/thường. Ngoài ra còn strength 4/5 cho các nhu cầu ICU đặc biệt; không chọn tùy tiện nếu nghiệp vụ không cần.

**Không nên kết luận mọi chữ tiếng Việt có quy luật so sánh giống tiếng Anh.** Ví dụ trong bài dùng locale `en` để kiểm các chữ `cafe/Café` có kết quả rõ ràng. Ứng dụng tiếng Việt nên chọn locale `vi` khi phù hợp, đồng thời kiểm thử cụ thể chữ `đ`, chữ có dấu và Unicode normalization theo dữ liệu thực.

### 2.2. Numeric ordering không biến mọi chuỗi thành số

Khi `numericOrdering:true`, các **chuỗi con liên tiếp gồm chữ số nguyên không âm** được so theo giá trị số. Ví dụ `"item2"` đứng trước `"item10"`.

Giới hạn cần nhớ:

- Không hiểu `-2.5` như một số âm/thập phân hoàn chỉnh.
- Không coi dấu chấm, dấu phẩy, dấu `+`/`-` hay biểu thức mũ là phép toán.
- Không dùng `numericOrdering` để thay thế kiểu BSON numeric thật khi tính tiền, số lượng hoặc range.

### 2.3. Một thao tác chỉ có một collation

MongoDB áp dụng **một collation cho toàn bộ thao tác**, không đặt collation khác nhau cho từng field của cùng một `find` hoặc từng stage của một `aggregate`.

~~~javascript
// Không có cú pháp để dùng strength 1 cho name và
// strength 3 cho category trong cùng một find() thông thường.
db.products.find({
  name: "cafe",
  category: "Drink"
}).collation({ locale: "en", strength: 1 });
~~~

Ở đây cả hai phép so sánh chuỗi hỗ trợ collation đều dùng cùng bộ quy tắc strength 1. Nếu một field là mã kỹ thuật phải so sánh binary, field kia là tên hiển thị cần so theo ngôn ngữ, có thể cần **hai truy vấn**, thêm **khóa chuẩn hóa riêng**, hoặc thiết kế schema/index khác.

## 3. Phạm vi collation: collection, index, operation

MongoDB cho phép cấu hình collation tại những vị trí quan trọng sau:

| Phạm vi | Cách đặt | Phạm vi ảnh hưởng |
| --- | --- | --- |
| **Collection** | `db.createCollection(...,{collation:...})` | Giá trị mặc định cho operation/index nếu không chỉ định khác |
| **Index** | `createIndex(...,{collation:...})` | Khóa index, so sánh và uniqueness theo collation của index |
| **Operation** | `find(...).collation(...)`, `aggregate(...,{collation:...})` | Ghi đè mặc định collection **cho thao tác đó** |
| **Spring Data entity** | `@Document(collation=...)` | Metadata cho thao tác mapped, collection/index creation tương ứng khi được thực hiện đúng đường |
| **Spring Data query** | `Query.collation(...)`, `@Query(collation=...)` | Quy tắc cho một query |
| **Spring Data aggregation** | `AggregationOptions.builder().collation(...)`, `@Aggregation(collation=...)` | Quy tắc cho toàn pipeline |

### 3.1. Thứ tự ưu tiên ở MongoDB server

1. Nếu **operation chỉ định collation**, dùng collation của operation.
2. Nếu không, **collection có collation mặc định**, dùng mặc định của collection.
3. Nếu cả hai không chỉ định, dùng **simple/binary**.

**Index không áp collation cho query chỉ vì nó tồn tại.** Index có collation riêng phục vụ những thao tác phù hợp; collation hiệu lực của query phải tương thích để index hỗ trợ so sánh chuỗi.

### 3.2. Không tự “lan” một collation cho mọi nơi

Ví dụ collection có mặc định `en/strength 2` nhưng một query chỉ định `en/strength 1`: query thực hiện theo **strength 1**, dù collection gốc tạo với strength 2.

Một index `en/strength 2` **không tự biến query strength 1 thành strength 2**. Nếu muốn khai thác index cho so sánh chuỗi strength 1, cần index phù hợp hoặc thay đổi thiết kế truy vấn.

## 4. Fixture: collection có collation mặc định

Các lệnh sau chỉ dùng trên **database test biệt lập**. Không dùng collection sản phẩm đang chạy; các ID cố định sẽ gặp duplicate key nếu chèn lại.

### 4.1. Tạo collection trước khi insert

~~~javascript
use spring_data_mongodb_lab

db.createCollection("catalog_collation_demo_007", {
  collation: {
    locale: "en",
    strength: 2
  }
});

const products = db.catalog_collation_demo_007;
~~~

Collection này có collation **không phân biệt hoa/thường nhưng còn phân biệt dấu** cho các phép so sánh string hỗ trợ collation.

### 4.2. Chèn dữ liệu

~~~javascript
products.insertMany([
  {
    _id: "p701",
    tenant_id: "t01",
    display_name: "cafe",
    category: "Drink",
    code: "item2",
    price_vnd: 50000
  },
  {
    _id: "p702",
    tenant_id: "t01",
    display_name: "CAFÉ",
    category: "drink",
    code: "item10",
    price_vnd: 60000
  },
  {
    _id: "p703",
    tenant_id: "t01",
    display_name: "Café",
    category: "DRINK",
    code: "item3",
    price_vnd: 65000
  },
  {
    _id: "p704",
    tenant_id: "t01",
    display_name: "Tea",
    category: "Food",
    code: "item20",
    price_vnd: 30000
  },
  {
    _id: "p705",
    tenant_id: "t01",
    display_name: "tea",
    category: "food",
    code: "item11",
    price_vnd: 32000
  },
  {
    _id: "p706",
    tenant_id: "t02",
    display_name: "cafe",
    category: "Drink",
    code: "item1",
    price_vnd: 55000
  }
]);
~~~

| ID | Tenant | Tên | Category | Code |
| --- | --- | --- | --- | --- |
| `p701` | t01 | cafe | Drink | item2 |
| `p702` | t01 | CAFÉ | drink | item10 |
| `p703` | t01 | Café | DRINK | item3 |
| `p704` | t01 | Tea | Food | item20 |
| `p705` | t01 | tea | food | item11 |
| `p706` | t02 | cafe | Drink | item1 |

Điều kiện tenant là **độc lập với collation**: nghiệp vụ nhiều tenant vẫn phải ràng buộc tenant có thẩm quyền. Không để việc so sánh tên “mềm” vô tình mở rộng sang dữ liệu tenant khác.

### 4.3. Xem collation mặc định

~~~javascript
const infos = db.getCollectionInfos({
  name: "catalog_collation_demo_007"
});

printjson(infos[0].options.collation);
// Có locale "en" và strength 2 nếu collection đã được tạo đúng.
~~~

Nếu collection **đã tồn tại**, `db.createCollection` với cùng tên sẽ thất bại; nó không “sửa collation” của collection hiện có. Không xóa collection chỉ để làm lại demo nếu có dữ liệu dùng chung.

## 5. `find`: so sánh theo mặc định và ghi đè

### 5.1. Dùng collation mặc định `en/strength 2`

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "cafe" },
  { _id: 1, display_name: 1 }
);
// p701: "cafe".
~~~

`"CAFÉ"` và `"Café"` có dấu `é`, vì thế khác `"cafe"` khi strength 2 còn xét diacritics. Chúng vẫn tương đương **với nhau** khi so sánh case-insensitive.

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "Café" },
  { _id: 1, display_name: 1 }
);
// p702 và p703.
~~~

### 5.2. Ghi đè thành strength 1

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "cafe" },
  { _id: 1, display_name: 1 }
).collation({
  locale: "en",
  strength: 1
});
// p701, p702, p703.
~~~

Điều kiện tenant vẫn giữ nguyên. Nếu bỏ tenant, còn có `p706` của t02 cũng khớp.

### 5.3. Ghi đè thành simple/binary

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "Café" },
  { _id: 1, display_name: 1 }
).collation({ locale: "simple" });
// Chỉ p703, vì chuỗi khớp chính xác theo binary comparison.
~~~

`Collation.simple()` ở Spring Data tương ứng với nguyên tắc này. Đừng hiểu `simple` là “dùng collation mặc định”: **simple là quy tắc nhị phân cụ thể**, và có thể ghi đè collection default khác simple.

### 5.4. So sánh ba kết quả

| Query trong t01 | Collation hiệu lực | ID khớp |
| --- | --- | --- |
| `display_name:"cafe"` | Collection default en/2 | `p701` |
| `display_name:"Café"` | Collection default en/2 | `p702,p703` |
| `display_name:"cafe"` | en/1 explicit | `p701,p702,p703` |
| `display_name:"Café"` | simple explicit | `p703` |

**Quan trọng:** collation không sửa giá trị được trả: `p702` vẫn có `display_name:"CAFÉ"`, không đổi thành `"Café"` hay `"cafe"`.

## 6. Collation ảnh hưởng `sort`

### 6.1. So sánh chuỗi theo ngôn ngữ

~~~javascript
products.find(
  { tenant_id: "t01" },
  { _id: 1, display_name: 1 }
).sort({ display_name: 1, _id: 1 });
~~~

Với collection default en/2, việc sắp xếp theo `display_name` dùng quy tắc ICU. Hai giá trị `CAFÉ` và `Café` bằng nhau theo strength 2; sort `display_name` không đủ phân định thứ tự giữa chúng. Thêm `_id` là **tie-breaker** để thứ tự output ổn định.

Đừng suy đoán thứ tự chữ cái theo Unicode code point là thứ tự ngôn ngữ; so sánh bằng `simple` hoặc theo ICU có thể cho thứ tự khác.

### 6.2. Sort có `numericOrdering`

Fixture chứa:

~~~text
item2, item10, item3, item20, item11
~~~

Theo so sánh chuỗi thông thường (không bật numeric ordering), `item10` có thể đứng trước `item2` vì `"1" < "2"` ở vị trí đầu tiên khác nhau.

~~~javascript
products.find(
  { tenant_id: "t01" },
  { _id: 0, code: 1 }
).sort({ code: 1, _id: 1 })
 .collation({
   locale: "en",
   strength: 2,
   numericOrdering: true
 });

// Dự kiến:
// item2, item3, item10, item11, item20
~~~

`numericOrdering` chỉ giúp sort/search so sánh các **chuỗi chứa phần số nguyên**; nó không đổi BSON type thành number. Đừng dùng chuỗi `"2"`/`"10"` làm thay thế cho giá trị số trong phép tính toán.

### 6.3. Sort không ổn định khi nhiều giá trị tương đương

Nếu `display_name` được so theo strength 1, ba giá trị `cafe`/`CAFÉ`/`Café` coi như bằng nhau. Không có tie-breaker, thứ tự thực tế có thể thay đổi theo query plan và dữ liệu đồng thời.

Với phân trang, thêm một field **duy nhất, ổn định** như `_id`. Tuy vậy, sort ổn định không biến nhiều request phân trang thành một snapshot bất biến nếu có insert/delete giữa các lượt đọc.

## 7. Aggregation: collation cho toàn pipeline

Một aggregation có các stage `$match`, `$group`, `$sort` đều thực thi trong **một operation**. Collation của operation đó có thể ảnh hưởng:

- `$match` so sánh chuỗi.
- `$sort` sắp xếp chuỗi.
- `$group` gom những khóa chuỗi được coi tương đương theo collation.
- Một số phép so sánh chuỗi trong biểu thức và stage khác theo quy tắc MongoDB.

### 7.1. Nhóm theo category với collection default

~~~javascript
products.aggregate([
  { $match: { tenant_id: "t01" } },
  {
    $group: {
      _id: "$category",
      products: { $sum: 1 }
    }
  },
  { $sort: { products: -1 } }
]);
~~~

Với default `en/strength 2`:

- `"Drink"`, `"drink"`, `"DRINK"` tương đương → **nhóm 3 sản phẩm**.
- `"Food"` và `"food"` tương đương → **nhóm 2 sản phẩm**.

**Tên `_id` hiển thị của nhóm có thể giữ một cách viết từ dữ liệu đầu vào** (ví dụ `"Drink"` hoặc `"drink"`); không dựa vào việc MongoDB tự chuẩn hóa casing. Chỉ khẳng định số nhóm và số lượng. Nếu API cần tên canonical, hãy thiết kế thêm field chuẩn hóa hoặc projection rõ ràng.

### 7.2. Ghi đè bằng `strength:1`

~~~javascript
products.aggregate(
  [
    { $match: { tenant_id: "t01" } },
    {
      $group: {
        _id: "$display_name",
        products: { $sum: 1 }
      }
    }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

Trong t01, `"cafe"`, `"CAFÉ"`, `"Café"` trở thành **một nhóm 3**. `"Tea"` và `"tea"` thành **một nhóm 2**. Như vậy output có **2 nhóm**, dù input có 5 sản phẩm t01.

### 7.3. Ghi đè bằng `simple`

~~~javascript
products.aggregate(
  [
    { $match: { tenant_id: "t01" } },
    { $group: { _id: "$category", products: { $sum: 1 } } }
  ],
  { collation: { locale: "simple" } }
);
~~~

Trong t01, có năm cách viết category khác nhau:

~~~text
Drink, drink, DRINK, Food, food
~~~

Do đó simple grouping tạo **5 nhóm, mỗi nhóm 1 document**. Kết quả khác với **2 nhóm (3 và 2)** ở collation en/2.

### 7.4. Vì sao collation quan trọng cho báo cáo?

Nếu báo cáo “số sản phẩm theo category” trước đây tách `Drink` và `drink`, sau khi đổi collation có thể gộp lại. **Số nhóm thay đổi dù không thay document nào**. Khi dùng báo cáo làm cơ sở thanh toán, thưởng, thống kê hoặc đối soát, phải quy định **collation trong contract của báo cáo** và test số liệu sau thay đổi.

Không đặt collation khác nhau trên từng stage của một lệnh aggregate. Nếu thực sự cần nhiều cách so sánh, tách pipeline/operation hoặc tạo field chuẩn hóa phù hợp.

## 8. Collation ở cấp index và khả năng tận dụng index

### 8.1. Index kế thừa collection default

~~~javascript
products.createIndex(
  { tenant_id: 1, display_name: 1 },
  { name: "ix_tenant_name_en2" }
);
~~~

Vì collection đã có default `en/strength 2`, index không khai báo collation riêng sẽ **kế thừa default** khi được tạo.

~~~javascript
products.getIndexes();
// Kiểm key, name và collation của từng index.
~~~

### 8.2. Tạo index cùng khóa nhưng collation khác

~~~javascript
products.createIndex(
  { tenant_id: 1, display_name: 1 },
  {
    name: "ix_tenant_name_en1",
    collation: { locale: "en", strength: 1 }
  }
);
~~~

MongoDB cho phép có nhiều index **cùng key pattern** nhưng **khác collation**, với **tên index riêng**. Chúng có thể cùng phục vụ các query cần hai quy tắc so sánh khác nhau, đánh đổi bằng dung lượng và chi phí bảo trì index.

### 8.3. Điều kiện sử dụng index cho string comparison

Một query dùng `en/strength 1` **không thể dựa vào index en/strength 2 để hỗ trợ phần so sánh chuỗi có collation khác**. Tương tự, query `simple` không có cùng quy tắc chuỗi với index en/strength 2.

~~~javascript
products.find({
  tenant_id: "t01",
  display_name: "cafe"
}).collation({
  locale: "en",
  strength: 1
}).explain("executionStats");
~~~

Kiểm tra `winningPlan`, `indexName`, `totalKeysExamined` và `totalDocsExamined`. **Không tự khẳng định** planner luôn chọn một index nhất định trên fixture nhỏ: collection scan đôi khi vẫn rẻ hơn. Điều có thể kiểm chứng là điều kiện **tương thích collation** của index với query.

### 8.4. Compound index có phần non-string

Ở một số trường hợp, index collation không khớp vẫn có thể hỗ trợ các trường **không phải string** trong prefix theo query plan thích hợp; điều này không có nghĩa nó hỗ trợ so sánh chuỗi không tương thích. Đánh giá theo **field type, index key order và explain thực tế**.

### 8.5. Collation-aware key có chi phí lưu trữ

Index có collation ngôn ngữ dùng ICU collation keys, có thể lớn hơn index binary. Một ứng dụng duy trì cả `simple`, `en/1` và `en/2` trên cùng key pattern phải trả chi phí **lưu trữ, bộ nhớ và write amplification**. Chỉ tạo nhiều index khi workload và performance test chứng minh cần.

## 9. Unique index với collation: ràng buộc không phân biệt hoa/thường

Collation không chỉ ảnh hưởng tìm kiếm. **Unique index** áp dụng quy tắc so sánh của **chính index đó** để quyết định khóa chuỗi có trùng hay không.

### 9.1. Fixture độc lập

~~~javascript
const customers = db.customers_collation_unique_007;

customers.createIndex(
  { tenant_id: 1, username: 1 },
  {
    name: "ux_tenant_username_ci",
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
);

customers.insertOne({
  _id: "u701",
  tenant_id: "t01",
  username: "Alice"
});

customers.insertOne({
  _id: "u702",
  tenant_id: "t02",
  username: "alice"
});
// Thành công: tenant khác.

customers.insertOne({
  _id: "u703",
  tenant_id: "t01",
  username: "alice"
});
// E11000: trong t01 đã có Alice, collation strength 2 bỏ qua case.
~~~

Đây là **compound unique theo tenant**. Nếu index chỉ có `{username:1}`, hai tenant dùng cùng username tương đương cũng bị ngăn theo phạm vi **toàn collection**.

### 9.2. Accent-sensitive khác accent-insensitive

Với `strength:2`, `"Alice"` và `"alice"` tương đương về case nhưng chuỗi có dấu/không dấu có thể khác tùy locale. Với `strength:1`, collation bỏ qua cả các khác biệt dấu được xét ở secondary level.

Do đó **thay collation của unique index có thể thay đổi tập khóa trùng**. Trước khi áp dụng policy mới cho collection có dữ liệu, kiểm tra duplicate theo **quy tắc so sánh mới**, xử lý dữ liệu hợp lệ, rồi điều phối thay đổi index.

### 9.3. Unique không được “nới” theo query

Nếu một query dùng `simple` trên collection có unique index en/2, điều đó **không làm index unique en/2 ngừng cưỡng chế**. Quy tắc unique nằm trên index, còn query collation điều khiển cách query so sánh.

### 9.4. Collation không thay thế validation

Index unique case-insensitive không kiểm tra độ dài username, ký tự hợp lệ, email domain, normalizing policy hay quyền tenant. Với username/email thực tế cần:

- Quy định string input hợp lệ và normalization nhất quán.
- Xác định collation/locale theo đặc thù nghiệp vụ.
- Tạo index đúng tenant scope/partial policy nếu field tùy chọn.
- Bắt lỗi `E11000`/`DuplicateKeyException` tại write thay vì dựa vào `existsBy...` trước insert.

## 10. Spring Data: `Collation` và các option fluent

Spring Data MongoDB cung cấp `org.springframework.data.mongodb.core.query.Collation`.

~~~java
import org.springframework.data.mongodb.core.query.Collation;

Collation binary = Collation.simple();

Collation caseInsensitive = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());

Collation accentAndCaseInsensitive = Collation.of("en")
    .strength(Collation.ComparisonLevel.primary());

Collation numericNames = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary())
    .numericOrderingEnabled();
~~~

Các instance `Collation` là **giá trị cấu hình** cho operation; thay vì ghép chuỗi JSON tùy ý, có thể dùng builder fluent để tên method thể hiện chủ đích.

### 10.1. Strength cụ thể so với tên mức

~~~java
Collation strengthTwo = Collation.of("en").strength(2);

Collation namedLevel = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());
~~~

Hai cách biểu diễn cùng mức strength 2. Cách dùng `ComparisonLevel` rõ nghĩa trong code review, còn số nguyên có thể gần với biểu diễn BSON MongoDB.

### 10.2. Tạo một bộ quy tắc với nhiều option

~~~java
Collation rules = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary())
    .numericOrderingEnabled()
    .normalizationEnabled();
~~~

Chỉ bật normalization khi có yêu cầu dữ liệu/Unicode phù hợp; đây là chi phí xử lý và cần đo trong workload. Không dùng nó thay cho chuẩn hóa định danh hoặc validator ở ứng dụng.

### 10.3. In collation BSON khi debug

~~~java
org.bson.Document bson = rules.toDocument();
System.out.println(bson.toJson());
~~~

Trong hệ thống thực không nên log một query chứa dữ liệu cá nhân hay token. Collation document thông thường là cấu hình, nhưng command chứa filter có thể mang thông tin nhạy cảm.

## 11. Tạo collection qua `MongoTemplate` đúng collation

### 11.1. Entity và `@Document(collation=...)`

~~~java
// ProductDocument.java
package com.example.collation;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(
    collection = "catalog_collation_demo_007",
    collation = "{ 'locale': 'en', 'strength': 2 }"
)
public class ProductDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("display_name")
    private String displayName;

    private String category;
    private String code;

    @Field("price_vnd")
    private long priceVnd;

    protected ProductDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getDisplayName() { return displayName; }
    public String getCategory() { return category; }
    public String getCode() { return code; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

`@Document(collation=...)` là **metadata của Spring Data** để áp dụng vào query/index/collection creation khi chạy qua các API mapped phù hợp. Nó **không bảo đảm** MongoDB collection đã có default đó nếu collection đã được tạo **ngầm** lúc ghi lần đầu.

### 11.2. Tạo collection tường minh

~~~java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;

// template là MongoTemplate được inject.
Collation defaultRules = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());

if (!template.collectionExists(ProductDocument.class)) {
    template.createCollection(
        ProductDocument.class,
        CollectionOptions.just(defaultRules)
    );
}
~~~

Trong production, tốt nhất coi tạo collection là **migration/DDL có điều phối**; chỉ `if (!exists)` là ví dụ ứng dụng học tập, **không phải khóa chống race** giữa nhiều instance khi startup. Cần chọn thời điểm tạo, kiểm quyền DDL và đối chiếu options thực trước khi mở traffic.

### 11.3. Bẫy auto-create

Nếu gọi:

~~~java
template.insert(productDocument);
~~~

khi collection **chưa tồn tại**, MongoDB có thể tự tạo collection. Tài liệu Spring Data lưu ý **collation từ `@Document` không được sử dụng cho trường hợp MongoDB tự tạo collection qua tương tác đầu tiên**.

Vì vậy: annotation `@Document(collation=...)` **không thay thế** việc tạo collection tường minh khi database default collation là yêu cầu bắt buộc.

### 11.4. Collation mặc định không thể đổi tại chỗ

MongoDB yêu cầu xác định collation mặc định lúc **tạo collection**; sau khi collection đã được tạo, không thể đổi default collation bằng một `collMod` thông thường.

Nếu cần đổi mặc định cho collection production:

- Phân tích các query/index đang dựa vào default cũ.
- Chuẩn bị collection mới với default mới và chiến lược sao chép/migration phù hợp.
- Đánh giá unique conflicts theo collation mới.
- Điều phối cutover, quyền DDL, backfill, kiểm metadata và rollback.
- Nếu chỉ **một số thao tác** cần quy tắc khác, cân nhắc operation-level collation và index tương ứng thay vì thay collection.

**Không tự `drop()` collection production để “sửa collation”**: hành động này làm mất dữ liệu và index nếu không có quy trình migration an toàn.

## 12. Spring Data `MongoTemplate` query với collation

### 12.1. Query mặc định theo entity/collection

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
);

List<ProductDocument> values =
    template.find(query, ProductDocument.class);
~~~

Với `ProductDocument.class`, Spring Data ánh xạ `tenantId` sang `tenant_id` và `displayName` sang `display_name`. Collation được chọn theo quy tắc metadata/operation/server; khi muốn guarantee một quy tắc cho use case, có thể đặt **tường minh** trên `Query`.

### 12.2. Explicit query collation

~~~java
Query flexible = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
).collation(
    Collation.of("en")
        .strength(Collation.ComparisonLevel.primary())
);

List<ProductDocument> matches =
    template.find(flexible, ProductDocument.class);

// Trên fixture gốc: p701, p702, p703 (thứ tự chưa xác định).
~~~

Nếu cần thứ tự:

~~~java
import org.springframework.data.domain.Sort;

flexible.with(Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
));
~~~

Query collation điều khiển **toàn bộ phép so sánh chuỗi trong thao tác**, bao gồm sort. Đừng truyền một collation khác vào sort riêng lẻ — MongoDB không cho phép nhiều collation khác nhau trong cùng operation.

### 12.3. Cố ý dùng binary

~~~java
Query exact = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("Café")
).collation(Collation.simple());

List<ProductDocument> rows =
    template.find(exact, ProductDocument.class);
// Chỉ p703 trên fixture.
~~~

Đây là cách rõ ràng khi giá trị giống `SKU`, token hoặc mã định danh kỹ thuật yêu cầu so sánh nhị phân.

### 12.4. Collation và update/delete theo filter

`Query.collation(...)` không chỉ dành cho `find`. Với các API update/delete hỗ trợ collation, bộ lọc string cũng có thể tuân theo quy tắc ấy:

~~~java
Query byName = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
).collation(
    Collation.of("en")
        .strength(Collation.ComparisonLevel.primary())
);

// Minh họa nguy cơ phạm vi: query có thể khớp 3 document.
// Không thực thi updateMulti nếu chỉ muốn sửa 1 sản phẩm!
// template.updateMulti(byName, new Update().set("priceVnd", 0),
//                      ProductDocument.class);
~~~

Nếu đổi từ binary sang strength 1, số document khớp có thể tăng; điều này đặc biệt nguy hiểm khi dùng `updateMulti` hoặc `remove`. Trước mọi thao tác ghi diện rộng, kiểm predicate, tenant, số bản ghi dự kiến và quyền truy cập.

## 13. Collation trên Spring Data repository

### 13.1. `@Query(collation=...)` tĩnh

~~~java
// ProductRepository.java
package com.example.collation;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'displayName': ?1 }",
        collation = "{ 'locale': 'en', 'strength': 1 }"
    )
    List<ProductDocument> findAccentInsensitive(
        String authorizedTenantId,
        String displayName
    );

    @Query(
        value = "{ 'tenantId': ?0, 'displayName': ?1 }",
        collation = "{ 'locale': 'en', 'strength': 2 }"
    )
    List<ProductDocument> findCaseInsensitive(
        String authorizedTenantId,
        String displayName
    );
}
~~~

Spring Data có thể bind tham số và ánh xạ property Java trong `@Query` theo metadata entity. `@Query(collation=...)` chỉ định rules cho **method đó**, có thể khác với `@Document`/collection default.

### 13.2. Truyền `Collation` động theo method parameter

Spring Data MongoDB hỗ trợ tham số `Collation` trên repository query method:

~~~java
// Thêm vào ProductRepository:
List<ProductDocument> findByTenantIdAndDisplayName(
    String tenantId,
    String displayName,
    org.springframework.data.mongodb.core.query.Collation collation
);
~~~

Gọi:

~~~java
Collation primary = Collation.of("en").strength(1);

List<ProductDocument> products = repository
    .findByTenantIdAndDisplayName("t01", "cafe", primary);
~~~

Đây là một dạng derived finder; `Collation` là **tham số đặc biệt điều khiển query**, không phải phần thuộc tính để suy ra `By...`.

### 13.3. Thứ tự ưu tiên trong Spring Data repository

Theo tài liệu Spring Data, trong phạm vi repository query:

1. **Method argument `Collation`** được cung cấp cụ thể (không null) có thể ghi đè.
2. **Collation khai báo trên method** qua `@Collation`/`@Query(collation=...)`.
3. **Domain metadata** `@Document(collation=...)`.
4. **Collection default/server default** ở các thao tác không có option ứng dụng.

`@Collation` trực tiếp trên method là một lựa chọn riêng và có thứ tự ưu tiên theo annotation cụ thể; khi dùng đồng thời nhiều annotation, phải đọc tài liệu phiên bản Spring Data đang triển khai và kiểm query thực tế.

Đừng giả định `@Document` đã “khóa” collation cho mọi method; một repository method hoặc parameter vẫn có thể thay đổi quy tắc.

### 13.4. Một kiểm thử cần cả method và metadata

Chạy cùng input `("t01","cafe")`:

- `findCaseInsensitive` với en/2: **p701**.
- `findAccentInsensitive` với en/1: **p701,p702,p703**.
- Derived finder với parameter `Collation.simple()`: **p701**.

Chỉ test số lượng output là đủ cho ví dụ nhỏ, nhưng production cần kiểm thêm **ID**, tenant và kế hoạch index.

## 14. Spring Data aggregation với `AggregationOptions.collation`

### 14.1. DTO tổng hợp

~~~java
// CategoryTotal.java
package com.example.collation;

public record CategoryTotal(
    String categoryName,
    long total
) {
}
~~~

### 14.2. Typed aggregation dùng rules en/strength 2

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Collation;

TypedAggregation<ProductDocument> pipeline =
    Aggregation.newAggregation(
        ProductDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.group("category")
            .count().as("total"),
        Aggregation.project("total")
            .and("_id").as("categoryName")
            .andExclude("_id")
    ).withOptions(
        AggregationOptions.builder()
            .collation(
                Collation.of("en")
                    .strength(Collation.ComparisonLevel.secondary())
            )
            .build()
    );

List<CategoryTotal> totals =
    template.aggregate(pipeline, CategoryTotal.class)
        .getMappedResults();
~~~

Với fixture t01, phải có **hai nhóm** với số lượng **3** và **2**. Giá trị `categoryName` có thể giữ casing từ một document đại diện; khi so sánh expected output nên chuẩn hóa **chỉ ở test** hoặc so counts, không giả định MongoDB đổi tên group thành lowercase.

### 14.3. Ghi đè aggregation thành binary

~~~java
TypedAggregation<ProductDocument> strictGroups =
    Aggregation.newAggregation(
        ProductDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.group("category")
            .count().as("total"),
        Aggregation.project("total")
            .and("_id").as("categoryName")
            .andExclude("_id")
    ).withOptions(
        AggregationOptions.builder()
            .collation(Collation.simple())
            .build()
    );
~~~

Nhóm theo `category` bây giờ phân biệt năm cách viết `Drink`, `drink`, `DRINK`, `Food`, `food`, tức **5 nhóm**. Tên/BSON field nguồn không đổi, chỉ quy tắc nhóm của operation khác đi.

### 14.4. `strictMapping` và collation là hai việc khác nhau

~~~java
AggregationOptions options =
    AggregationOptions.builder()
        .strictMapping()
        .collation(Collation.of("en").strength(2))
        .build();
~~~

`strictMapping()` kiểm tham chiếu property/domain mapping khi Spring Data render pipeline; `collation(...)` điều khiển **so sánh chuỗi trên MongoDB server**. Bật strict mapping không làm query trở nên case-insensitive, và dùng collation không sửa lỗi property name gõ sai.

## 15. `@Aggregation(collation=...)` trên repository

Repository aggregation cũng có thuộc tính `collation`, giúp định nghĩa rules cùng với pipeline.

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductReportRepository
        extends MongoRepository<ProductDocument, String> {

    @Aggregation(
        pipeline = {
            "{ '$match': { 'tenantId': ?0 } }",
            "{ '$group': { '_id': '$category', " +
                "'total': { '$sum': 1 } } }",
            "{ '$project': { '_id': 0, " +
                "'categoryName': '$_id', 'total': 1 } }"
        },
        collation = "{ 'locale': 'en', 'strength': 2 }"
    )
    List<CategoryTotal> groupCategories(String tenantId);
}
~~~

Kết quả vẫn là **hai nhóm** cho t01. `@Aggregation` pipeline sẽ được áp mapping của domain type ở các vị trí framework hỗ trợ; output DTO phải khớp alias `categoryName`, `total` của stage cuối cùng.

### 15.1. Khi cần dynamic collation

Annotation `@Aggregation` cũng hỗ trợ placeholder tham số trong thuộc tính `collation` theo tài liệu:

~~~java
@Aggregation(
    pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$category', 'total': { '$sum': 1 } } }"
    },
    collation = "?1"
)
List<org.bson.Document> groupByDynamicRules(
    String tenantId,
    String locale
);
~~~

Ví dụ này chỉ thay **locale** dưới dạng chuỗi được framework chấp nhận; các option chi tiết như strength cần được khai báo bằng JSON collation hoặc object phù hợp. Không truyền một locale tùy ý từ client mà không kiểm tra **allowlist**, vì quy tắc query/index/chi phí có thể thay đổi đáng kể.

Nếu logic collation động phức tạp, `MongoTemplate` với `AggregationOptions` typed thường dễ kiểm soát và kiểm thử hơn.

### 15.2. Không nhầm `Pageable` với collation

`Pageable`/`Sort` trên repository aggregation tác động tới output/sort/skip/limit theo hợp đồng của `@Aggregation`, nhưng chúng **không tự tạo collation**. Nếu muốn sort chuỗi theo rules cụ thể, phải cung cấp collation qua annotation hoặc options tương ứng.

## 16. Views, text index và `$regex`: các giới hạn

### 16.1. View có collation riêng

MongoDB view không tự kế thừa collation mặc định của collection nguồn. Khi tạo view không khai báo collation, nó dùng **simple**; khi tạo view có collation, thao tác trên view dùng collation đó và không cho ghi đè theo cách áp dụng cho collection thường.

Khi pipeline dùng nhiều views (ví dụ `$lookup`/`$graphLookup`), MongoDB có ràng buộc các views phải có collation tương thích. Đây là trường hợp cần xác minh trước khi xây báo cáo liên collection.

### 16.2. `$regex` không trở thành collation-aware

~~~javascript
products.find({
  display_name: { $regex: "^caf", $options: "i" }
}).collation({
  locale: "en",
  strength: 1
});
~~~

Không được suy rằng `$regex` sẽ dùng mọi quy tắc `strength:1` như phép so sánh bằng. MongoDB `$regex` **không collation-aware**, và **case-insensitive index** dựa trên collation không tăng tốc `$regex` chỉ nhờ collation.

Muốn tìm tên chính xác không phân biệt dấu/case, dùng **equality với collation** khi phù hợp. Muốn search theo tiền tố, fuzzy/full-text, thiết kế index/search engine theo khả năng được hỗ trợ; đừng kỳ vọng thay collation chữa mọi truy vấn regex.

### 16.3. Text index và 2d index

MongoDB text index và 2d index chỉ hỗ trợ **simple binary collation**. Nếu collection default khác simple mà cần tạo các index này, phải khai báo `collation:{locale:"simple"}` đúng quy tắc MongoDB cho index tương ứng.

Collation của B-tree thông thường cũng không thay thế tokenizer/analyzer của text search hoặc tìm kiếm ngôn ngữ toàn văn.

## 17. Collation và thay đổi schema/collection an toàn

Đổi chính sách từ `simple` sang `en/2` hoặc `vi/2` có thể ảnh hưởng đồng thời:

- **Query result:** một phép bằng string có thể trả nhiều document hơn.
- **Sort:** thứ tự chuỗi thay đổi; nhiều giá trị có thể trở nên tương đương.
- **Group:** số nhóm giảm hoặc tăng.
- **Unique index:** những giá trị từng khác nhau có thể trở thành **duplicate**.
- **Index performance:** query cần index cùng collation mới.
- **API expectation:** phân trang và số liệu báo cáo thay đổi.

### 17.1. Quy trình thay đổi đề xuất

1. **Định nghĩa lại hợp đồng nghiệp vụ:** locale, strength, case, dấu, numericOrdering, từng use case.
2. **Kiểm kê dữ liệu** theo quy tắc mới: tìm các khóa khác biệt bằng ký tự nhưng sẽ trở thành tương đương.
3. **So sánh query/report** trên dữ liệu đại diện, xác nhận số match/group trước-sau.
4. **Kiểm unique conflicts** trước khi tạo unique collation index.
5. **Đánh giá collection và view:** default collation hiện tại, collection có tạo ngầm không, index đang tồn tại.
6. **Thiết kế index phù hợp** với query mới, giới hạn số index để tránh write overhead.
7. **Chọn đường triển khai:** operation-level collation nếu chỉ vài truy vấn khác; migration collection nếu đổi default là yêu cầu tổng thể.
8. **Triển khai theo lô/staging**, giám sát errors, latency, explain plan, raw BSON.
9. **Định nghĩa rollback:** quay lại operation/index nào, xử lý dữ liệu được ghi dưới quy tắc mới ra sao.

### 17.2. Chẩn đoán duplicate theo collation mới

Nếu muốn tạo unique `username` không phân biệt hoa/thường cho từng tenant, trước khi tạo index:

~~~javascript
db.customers_collation_unique_007.aggregate(
  [
    {
      $group: {
        _id: {
          tenant: "$tenant_id",
          username: "$username"
        },
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    { $match: { count: { $gt: 1 } } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Khi group dưới collation en/2, những username chỉ khác case có thể thuộc **cùng nhóm**. Đây là cách kiểm kê gần với quy tắc của unique index đích. Với collection khổng lồ, không tùy tiện `$push` mọi ID vào một document nhóm (có giới hạn BSON); cần kế hoạch phân lô/truy vấn chi tiết.

**Không tự xóa duplicate** theo một kết quả group: hợp nhất danh tính là quyết định nghiệp vụ.

## 18. Integration test: kiểm cả collection, query và aggregation

Mock `MongoTemplate` sẽ không chứng minh collation được gửi đúng xuống MongoDB, không kiểm metadata collection và cũng không phát hiện sự khác biệt group theo ICU. Cần MongoDB test instance riêng (ví dụ Testcontainers) và dữ liệu fixture kiểm soát được.

### 18.1. Các ca kiểm thử tối thiểu

| Test | Kỳ vọng |
| --- | --- |
| Collection default `en/2` | Có trong metadata collection |
| Query `cafe`, default `en/2` | p701 trong tenant t01 |
| Query `Café`, default `en/2` | p702, p703 |
| Query `cafe`, explicit `en/1` | p701, p702, p703 |
| Query `Café`, explicit simple | Chỉ p703 |
| Aggregation group category default `en/2` | 2 nhóm với count 3 và 2 |
| Aggregation group category simple | 5 nhóm với count 1 |
| Sort code, numericOrdering true | item2, item3, item10, item11, item20 |
| Unique index en/2 | Alice và alice cùng tenant xung đột |
| Unique index en/2, khác tenant | Có thể cùng username |
| Index collation khớp query | Có thể hỗ trợ so sánh chuỗi; xác minh explain |
| Query collation khác index | Không dùng index đó để so sánh chuỗi không tương thích |
| Repository `@Query`, `@Aggregation` | Gửi đúng collation và nhận kết quả đúng |
| `$regex` | Không giả định collation index giúp regex |
| Tenant khác | Không lọt vào kết quả t01 |

### 18.2. Test Java với MongoDB thật

Ví dụ test tạo một collection riêng bằng driver, sau đó dùng `MongoTemplate` với entity metadata để kiểm collation. Chỉ chạy trên **database test biệt lập** và không dùng tên collection này chung với test song song.

~~~java
package com.example.collation;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.CollationStrength;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class CollationMongoOperationsTest {
    @Autowired MongoTemplate template;

    @Test
    void collectionDefaultCanBeOverriddenPerQuery() {
        String collection = "catalog_collation_it_007";

        // Trong test database biệt lập, tạo collection trước khi insert.
        if (!template.collectionExists(collection)) {
            var nativeRules =
                com.mongodb.client.model.Collation.builder()
                    .locale("en")
                    .collationStrength(CollationStrength.SECONDARY)
                    .build();

            template.getDb().createCollection(
                collection,
                new CreateCollectionOptions().collation(nativeRules)
            );
        }

        var nativeCollection =
            template.getDb().getCollection(collection);
        var ids = List.of(
            "it-collation-701",
            "it-collation-702",
            "it-collation-703",
            "it-collation-other"
        );

        nativeCollection.deleteMany(Filters.in("_id", ids));

        try {
            nativeCollection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "cafe"),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "CAFÉ"),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "Café"),
                new Document("_id", ids.get(3))
                    .append("tenant_id", "another-tenant")
                    .append("display_name", "cafe")
            ));

            Query defaultQuery = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("cafe")
            );
            // Không truyền Query.collation: dùng default en/strength 2.
            var defaultMatches = template.find(
                defaultQuery, ProductDocument.class, collection
            );
            assertThat(defaultMatches)
                .extracting(ProductDocument::getId)
                .containsExactly(ids.get(0));

            Query accentInsensitive = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("cafe")
            ).collation(Collation.of("en").strength(1));

            var allBaseNames = template.find(
                accentInsensitive, ProductDocument.class, collection
            );
            assertThat(allBaseNames)
                .extracting(ProductDocument::getId)
                .containsExactlyInAnyOrder(
                    ids.get(0), ids.get(1), ids.get(2)
                );

            Query binary = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("Café")
            ).collation(Collation.simple());
            var exact = template.find(
                binary, ProductDocument.class, collection
            );
            assertThat(exact)
                .extracting(ProductDocument::getId)
                .containsExactly(ids.get(2));
        } finally {
            nativeCollection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

**Lưu ý khi thực thi:** Entity `ProductDocument` ở mục 11 có `@Document(collation=en/2)`. Nếu test muốn chứng minh **riêng hành vi server default**, phải đảm bảo không có option collation tường minh từ mapping entity phủ lên query; tốt nhất bổ sung một kiểm tra raw driver `nativeCollection.find(Filters.eq("display_name","cafe"))` song song. Trong ví dụ, option entity en/2 trùng với server default en/2 nên kết quả vẫn đúng dù hai tầng cùng chỉ định cùng rules.

### 18.3. Test aggregation không phụ thuộc casing của `_id` nhóm

Khi group `Drink`/`drink`/`DRINK` dưới en/2, assert:

~~~java
// Ví dụ ý tưởng, với CategoryTotal có categoryName và total:
assertThat(totals)
    .extracting(CategoryTotal::total)
    .containsExactlyInAnyOrder(3L, 2L);
~~~

Đừng assert tên nhóm nhất định là `"Drink"` nếu pipeline chưa tạo canonical label, vì collation làm các chuỗi tương đương nhưng không tự lưu một dạng casing mới.

### 18.4. Test về index phải xem metadata và explain

Ngoài output, kiểm `getIndexes()` chứa đúng:

- `key` theo BSON `tenant_id/display_name`.
- `collation` của index en/2 hoặc en/1.
- `unique` và các options nếu đây là unique index.

Sau đó kiểm `explain("executionStats")` trên query tiêu biểu. Không assert một winning plan cứng chỉ dựa trên sáu document fixture; planner có thể chọn collection scan hợp lý với tập dữ liệu nhỏ.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@Document(collation=...)` nhưng collection vẫn simple | Collection đã được MongoDB tạo ngầm trước | Tạo collection tường minh trước khi ghi; xem metadata |
| Tạo collection mới với tên cũ lỗi | Collection đã tồn tại | Không coi createCollection là lệnh cập nhật default; lập migration |
| Query `cafe` không khớp `Café` | Đang strength 2 hoặc simple, còn phân biệt dấu | Nếu nghiệp vụ muốn bỏ qua dấu, dùng strength 1 đúng locale |
| Query khớp quá nhiều document | Dùng strength 1 khi cần phân biệt dấu hoặc thiếu tenant | Ràng buộc tenant và chọn strength theo contract |
| Sort trông không đúng alphabet địa phương | Đang simple hoặc locale/strength không phù hợp | Dùng locale đúng; kiểm dữ liệu có dấu/Unicode |
| Phân trang lặp thứ tự | Nhiều tên tương đương theo collation, thiếu tie-breaker | Sort thêm `_id`; xử lý consistency |
| `$group` chỉ còn 2 nhóm thay vì 5 | Collation đang gom case/diacritic | Kiểm collection default, operation override và output |
| Query không dùng index | Index/query collation không tương thích | So `getIndexes()`, operation collation, `explain` |
| Case-insensitive regex vẫn chậm | `$regex` không collation-aware | Dùng equality có collation hoặc search/index phù hợp |
| Unique insert `Alice`/`alice` thất bại | Unique index en/2 coi tương đương | Đây là ràng buộc đúng; xử lý conflict |
| Cùng username khác tenant bị chặn | Index global unique, không compound theo tenant | Xem lại key pattern/index cũ |
| Dùng `Collation.simple()` tưởng là mặc định | simple là binary override cụ thể | Bỏ option khi muốn server default hoặc chỉ định rules rõ |
| `@Query(collation=...)` không được áp trong test mock | Mock không thực thi driver | Integration test MongoDB thật |
| Repository query và aggregation khác kết quả | Hai operation có collation khác hoặc filter khác | Đối chiếu effective collation của từng command |
| `numericOrdering` cho thứ tự số âm sai | Chỉ hỗ trợ phần chữ số nguyên không âm | Lưu số dưới numeric BSON type |
| `@Field` alias khiến query không thấy dữ liệu | Dùng tên BSON ở DSL cần property Java hoặc ngược lại | Kiểm mapping entity và BSON thực |
| Text/2d index trên collection collated lỗi | Index chỉ hỗ trợ simple | Tạo index với collation simple theo quy tắc |
| View query không chấp nhận override collation | View có collation cố định | Xem collation của view và thiết kế lại nếu cần |

## 20. Checklist thiết kế collation

1. **Xác định nhu cầu:** so sánh chính xác, không phân biệt case, không phân biệt dấu, sort tự nhiên hay uniqueness.
2. **Chọn locale và strength** cụ thể; thử dữ liệu có dấu/case thực, nhất là tiếng Việt.
3. **Phân biệt collection default, entity annotation, operation override và index collation.**
4. **Tạo collection tường minh** khi default collation là yêu cầu bắt buộc.
5. **Không nghĩ `@Document` tự sửa** collection đã tạo ngầm hoặc đang tồn tại.
6. **Một operation chỉ có một collation**; không mong field hay stage có rules riêng.
7. **Ràng buộc tenant/authorization** ngay trong filter, đặc biệt với strength 1.
8. **Sort có tie-breaker** khi nhiều chuỗi được coi tương đương.
9. **Kiểm `$group` output**, không giả định label canonical khi khác casing/diacritic.
10. **Tạo index đúng collation với workload**, đánh giá chi phí của nhiều index.
11. **Kiểm unique conflicts** khi thay chính sách so sánh.
12. **Không dựa vào regex** để tận dụng case-insensitive collation index.
13. **Kiểm cách áp collation trong Spring Data:** `Query.collation`, repository `@Query`, `AggregationOptions` và `@Aggregation`.
14. **Viết integration test** với BSON thật, metadata collection/index và dữ liệu phân biệt case/dấu.
15. **Migration có rollback** khi đổi default collation hoặc unique policy.

## 21. Bài thực hành

Mỗi bài dựa trên fixture mục 4, không có writer đồng thời và không thay đổi dữ liệu giữa các câu.

### Bài 1 — Cấp collection

Vì sao phải gọi `db.createCollection(...,{collation:...})` **trước** khi insert lần đầu?

**Đáp án:** Nếu MongoDB tự tạo collection ngầm, default collation không được lấy tự động từ `@Document` Spring Data; collection có thể thành `simple`. Default được đặt tại thời điểm tạo collection và không đổi trực tiếp sau đó.

### Bài 2 — Strength 2

Tìm `display_name:"cafe"` trong t01 trên collection en/2. Khớp những ID nào?

**Đáp án:** `p701`. `CAFÉ` và `Café` có dấu, strength 2 vẫn phân biệt dấu so với `cafe`.

### Bài 3 — Strength 1

Ghi đè en/1 và tìm `"cafe"` trong t01. Khớp những ID nào?

**Đáp án:** `p701,p702,p703`. Cả hoa/thường và khác biệt dấu ở secondary level được bỏ qua.

### Bài 4 — `simple`

Tìm `"Café"` trong t01 với `Collation.simple()`.

**Đáp án:** Chỉ `p703`; MongoDB dùng binary comparison.

### Bài 5 — Group theo category

Với en/2 và tenant t01, `$group` theo `category` trả bao nhiêu nhóm? Simple trả bao nhiêu?

**Đáp án:** En/2 có **2 nhóm** với count 3 và 2; simple có **5 nhóm** vì `Drink`/`drink`/`DRINK` và `Food`/`food` khác nhau ở binary comparison.

### Bài 6 — Numeric ordering

Cho các code `item2,item10,item3,item20,item11`. Sort en/2 có numericOrdering true cho thứ tự nào?

**Đáp án:** `item2,item3,item10,item11,item20`. Không dùng cách này để phân tích số âm hoặc số thực trong string.

### Bài 7 — Index tương thích

Collection có index `{tenant_id:1,display_name:1}` en/2. Query en/1 có chắc dùng được index đó để so sánh `display_name` không?

**Đáp án:** Không. Index/query collation phải phù hợp cho string comparison. Có thể tạo index cùng pattern với collation en/1 và tên khác nếu workload cần, rồi đo `explain`.

### Bài 8 — Unique index và case

`(t01,"Alice")` đã tồn tại trong index compound unique en/2. Insert `(t01,"alice")` thì sao? `(t02,"alice")` thì sao?

**Đáp án:** Cùng tenant bị `E11000`; khác tenant được phép vì khóa compound khác.

### Bài 9 — Annotation Spring Data

`@Document(collation = "{'locale':'en','strength':2}")` có thay default của collection được tạo ngầm trước đó không?

**Đáp án:** Không. Nó là metadata của Spring Data cho thao tác mapped; default server của collection phải được tạo đúng từ đầu, hoặc cần migration.

### Bài 10 — Query và aggregation

Viết cách cấu hình en/1 cho một query và một aggregation.

**Đáp án:**

~~~java
Query query = Query.query(
    Criteria.where("displayName").is("cafe")
).collation(Collation.of("en").strength(1));

AggregationOptions options = AggregationOptions.builder()
    .collation(Collation.of("en").strength(1))
    .build();
~~~

Khi dùng aggregation, gắn options bằng `withOptions(options)` vào pipeline.

### Bài 11 — Raw aggregation so với DTO

Collation en/2 gom `Drink`/`drink`/`DRINK` vào một nhóm. Có chắc `_id` nhóm là chữ thường `"drink"` không?

**Đáp án:** Không. Collation định nghĩa **tương đương khi so sánh**, không tự chuẩn hóa output. Tạo canonical label riêng nếu API yêu cầu một tên cố định.

### Bài 12 — Multi-tenant update

Một lệnh `updateMulti` tìm tên `"cafe"` dưới en/1 mà không lọc tenant có thể sửa những ai?

**Đáp án:** Trong fixture, cả `p701,p702,p703` (t01) và `p706` (t02). Đưa tenant có thẩm quyền vào predicate, không chỉ dựa vào tên sản phẩm.

### Bài 13 — Regex

Vì sao `/cafe/i` không tự tận dụng index en/1 và không tự hiểu mọi biến thể dấu?

**Đáp án:** MongoDB `$regex` không collation-aware; case-insensitive index theo collation không tối ưu regex. Với equality dùng collation, còn search cần công cụ/index phù hợp.

### Bài 14 — Thay đổi collation của collection đang dùng

Có thể sửa ngay default từ en/2 sang en/1 bằng một lệnh `collMod` đơn giản không?

**Đáp án:** Không. Default được đặt lúc tạo collection; muốn đổi cần quy trình migration hoặc áp operation-specific collation nếu chỉ một số use case cần.

### Bài 15 — Testing

Unit test mock `MongoTemplate.find` trả ba sản phẩm có chứng minh MongoDB đã áp en/1 không?

**Đáp án:** Chưa. Phải có integration test với MongoDB thật, fixture case/dấu, collation metadata và kết quả truy vấn/aggregation.

## Tài liệu tham khảo

- [Spring Data MongoDB — Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html): `Collation` fluent, `@Document`, tạo collection/index, `Query.collation` và `AggregationOptions`.
- [Spring Data MongoDB — Repository Query Methods, Collation Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Query(collation=...)`, tham số `Collation` và thứ tự ưu tiên.
- [Spring Data MongoDB — `@Aggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Aggregation.html): thuộc tính `collation` của repository aggregation.
- [Spring Data MongoDB — `Collation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Collation.html): `simple`, `of`, `strength`, `numericOrderingEnabled`.
- [Spring Data MongoDB — `@Document` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Document.html): metadata collation trên entity.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed aggregation, pipeline stages và output mapping.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale, strength, case, numericOrdering, view, index restrictions.
- [MongoDB Manual — `db.createCollection()`](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): collection default collation, thời điểm tạo và giới hạn thay đổi.
- [MongoDB Manual — `db.collection.createIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/): index collation và điều kiện tận dụng index.
- [MongoDB Manual — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/): index strength 1/2 và hạn chế với `$regex`.
- [MongoDB Manual — `$regex`](https://www.mongodb.com/docs/manual/reference/operator/query/regex/): regex không collation-aware.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): `$match`, `$group`, `$sort`.
