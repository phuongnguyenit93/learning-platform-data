# Field projection, sort, limit và skip

## 1. Bài toán: truy vấn đúng dữ liệu, đúng thứ tự và đúng kích thước

Một API danh sách sản phẩm có thể cần trả **20 sản phẩm còn bán thuộc danh mục BOOK**, sắp xếp từ mới nhất đến cũ nhất và chỉ hiển thị mã, tên, giá. Nếu đọc toàn bộ collection rồi lọc, sắp xếp, cắt mảng ở Java, ứng dụng vừa lãng phí mạng và bộ nhớ vừa làm tăng tải lên MongoDB.

Trong **SPRING_DATA_MONGODB**, Spring Data MongoDB cung cấp **Query** và **Criteria** để diễn đạt truy vấn, trong đó:

- **Criteria** mô tả document nào phù hợp điều kiện.
- **Query.fields()** mô tả các trường sẽ được trả về (*field projection*).
- **Query.with(Sort)** mô tả thứ tự sắp xếp.
- **Query.limit(int)** giới hạn số document trả về.
- **Query.skip(long)** bỏ qua một số document đầu tiên của tập đã sắp xếp.

Các thành phần này bổ sung cho thao tác repository và MongoTemplate khi xây dựng truy vấn, aggregation, index và các đường truy cập dữ liệu đồng bộ/reactive. Chúng cần được dùng cùng nhau theo đúng mục tiêu, không chỉ để tạo kết quả trông đúng trên một bộ dữ liệu nhỏ.

Sau bài học, bạn có thể:

1. Xây filter bằng Criteria và Query trên một entity Spring Data MongoDB.
2. Chọn trường bằng include, loại trường bằng exclude và xử lý ngoại lệ của **_id**.
3. Sắp xếp một hoặc nhiều khóa, đặc biệt cần khóa phụ ổn định khi phân trang.
4. Phân biệt **limit**, **skip**, **Pageable**, **Slice** và phép đếm tổng số.
5. Tránh lỗi phân trang sâu, thứ tự không xác định và cập nhật nhầm entity đã đọc thiếu trường.
6. Hiểu tác động của projection và sort tới index, aggregation và hiệu năng.
7. Kiểm thử một truy vấn bằng MongoDB thật và xác minh filter, thứ tự, kích thước, hình dạng BSON.

## 2. Dữ liệu mẫu và entity Java

Giả sử collection **products** lưu các document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Học Spring Data MongoDB",
  category: "BOOK",
  active: true,
  priceMinor: NumberLong("159000"),
  stock: NumberInt(8),
  supplier: {
    code: "SUP-01",
    internalNote: "Điều khoản kinh doanh nội bộ"
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  sku: "BOOK-002",
  name: "Thực hành MongoDB",
  category: "BOOK",
  active: true,
  priceMinor: NumberLong("129000"),
  stock: NumberInt(5),
  supplier: {
    code: "SUP-02",
    internalNote: "Không công bố"
  },
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

Trong Java:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    String category,
    boolean active,
    long priceMinor,
    int stock,
    Supplier supplier,
    Instant createdAt
) {
    public record Supplier(String code, String internalNote) {}
}
~~~

**_id** là tên field BSON, còn **id** là property Java ánh xạ bằng @Id. priceMinor dùng kiểu long vì lưu đơn vị tiền nhỏ nhất; createdAt dùng Instant để ánh xạ với BSON Date. Tên collection được lấy từ **@Document(collection = "products")** khi dùng MongoTemplate với kiểu ProductDocument.

## 3. Query và Criteria phân chia trách nhiệm

Ví dụ tìm sản phẩm còn bán thuộc danh mục BOOK:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
~~~

Query trên tương đương filter mongosh:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

**Criteria quyết định những document phù hợp**, không chỉ định những field được trả, thứ tự hay số lượng. Các lựa chọn ấy được bổ sung trên Query:

~~~java
import org.springframework.data.domain.Sort;

query.fields()
    .include("sku")
    .include("name")
    .include("priceMinor");

query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.skip(0);
query.limit(20);
~~~

~~~mermaid
flowchart TD
    A["Criteria: category=BOOK, active=true"] --> B["Query"]
    B --> C["fields: sku, name, priceMinor, _id mặc định"]
    C --> D["sort: createdAt DESC, _id DESC"]
    D --> E["skip: 0, limit: 20"]
    E --> F["MongoDB find"]
    F --> G["Kết quả BSON được mapping"]
~~~

Khi viết truy vấn, hãy trả lời bốn câu hỏi độc lập: **lọc gì, giữ field nào, theo thứ tự nào, lấy bao nhiêu bản ghi**. Cách tách này giúp tránh các lỗi khi thay đổi yêu cầu API.

## 4. Field projection với include

Trong MongoDB, projection mô tả hình dạng document trả về. Một projection có thể **chọn các field** (*inclusion*):

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1 }
);
~~~

Kết quả minh họa:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Học Spring Data MongoDB",
  priceMinor: NumberLong("159000")
}
~~~

**_id vẫn xuất hiện dù không có _id: 1** vì MongoDB trả _id mặc định, trừ khi chủ động loại nó.

Trong MongoTemplate:

~~~java
Query query = Query.query(
    Criteria.where("category").is("BOOK")
);
query.fields()
    .include("sku")
    .include("name")
    .include("priceMinor");
~~~

Method **include** có thể nhận nhiều field trong các phiên bản API thích hợp; viết thành từng lời gọi như trên giúp minh bạch và dễ đối chiếu kết quả.

### 4.1. Chỉ trả những field cần thiết

Với một danh sách công khai, chỉ chọn sku, name, priceMinor giúp loại khỏi dữ liệu trả về những trường không cần như supplier.internalNote, stock và createdAt. Đó là **whitelist trường được phép trả**, hữu ích để tránh vô tình công bố một trường mới được bổ sung trong tương lai.

Tuy nhiên, nếu ứng dụng cần ID để mở trang chi tiết sản phẩm, hãy giữ _id. Nếu không cần ID, có thể loại nó theo quy tắc đặc biệt ở phần kế tiếp.

### 4.2. Thêm các field cần cho DTO

Nếu API cần cả thời gian tạo, phải include createdAt:

~~~java
query.fields().include("createdAt");
~~~

Đừng chỉ định field trong DTO nhưng quên tải từ MongoDB rồi kỳ vọng mapper tự tìm phần bị thiếu. Query projection quyết định BSON mà framework có thể dùng để dựng kết quả.

## 5. Exclude và ngoại lệ của _id

Projection loại trường (*exclusion*) chỉ ra những field không muốn trả:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.internalNote": 0 }
);
~~~

Kết quả vẫn có sku, name, category, priceMinor, stock, supplier.code, createdAt và _id. Nếu document được thêm một field mới, trường mới cũng có thể xuất hiện vì exclusion **không phải whitelist**.

Trong MongoTemplate:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .exclude("supplier.internalNote");
~~~

### 5.1. Không được trộn include và exclude tùy ý

Trong projection find thông thường, MongoDB không cho phép vừa include field A vừa exclude field B khác, **ngoại trừ _id**.

| Projection | Hợp lệ? | Giải thích |
| --- | --- | --- |
| { name: 1, priceMinor: 1 } | Có | Inclusion |
| { stock: 0, supplier: 0 } | Có | Exclusion |
| { name: 1, _id: 0 } | Có | Inclusion, ngoại lệ _id |
| { stock: 0, _id: 0 } | Có | Exclusion, ngoại lệ _id |
| { name: 1, stock: 0 } | Không | Trộn hai chế độ ngoài _id |
| { name: 1, "supplier.internalNote": 0 } | Không | Trộn hai chế độ ngoài _id |

Vì vậy, nếu mục tiêu chỉ là name và priceMinor:

~~~java
query.fields()
    .include("name")
    .include("priceMinor")
    .exclude("_id");
~~~

Đây là kết hợp **hợp lệ** vì _id là ngoại lệ.

**Không dùng:**

~~~java
// Sai: trộn include/exclude trên các field thông thường.
query.fields()
    .include("name")
    .exclude("supplier.internalNote");
~~~

Thay vì loại internalNote, chỉ cần include name cùng các field khác đã được duyệt. Nếu không cần ID, thêm **exclude("_id")**.

### 5.2. Khi nào nên loại _id?

Một báo cáo chỉ in danh sách tên có thể dùng:

~~~javascript
db.products.find(
  { active: true },
  { name: 1, _id: 0 }
);
~~~

Ngược lại, màn hình có nút “Xem chi tiết” thường cần ID. Hãy quyết định theo hợp đồng API chứ không loại _id máy móc. Ngoại lệ _id cũng quan trọng với **covered query**: nếu index không chứa _id, việc trả _id mặc định có thể khiến MongoDB phải fetch document gốc.

## 6. Projection cho document nhúng

Product có object supplier. Nếu chỉ cần supplier.code:

~~~java
Query query = new Query();
query.fields()
    .include("supplier.code")
    .exclude("_id");
~~~

BSON kết quả có thể có hình dạng:

~~~javascript
{
  supplier: {
    code: "SUP-01"
  }
}
~~~

**Dot notation** chỉ chọn field bên trong embedded object, không chuyển supplier.code thành field phẳng ở top-level.

### 6.1. Mapping với @Field

Nếu entity có property supplierCode lưu dưới tên BSON khác:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_code")
private String supplierCode;
~~~

Khi truy vấn được ánh xạ qua kiểu entity, Spring Data có thể chuyển property Java thành tên field BSON tương ứng. Trong mongosh hoặc thao tác với MongoDB Java Driver thô, phải dùng tên BSON thật. Đối với custom converter hoặc nested path phức tạp, nên kiểm thử chính xác projection BSON cuối cùng.

### 6.2. Array projection không phải lọc phần tử

Giả sử một product có:

~~~javascript
{
  variants: [
    { color: "RED", stock: 0 },
    { color: "BLUE", stock: 5 }
  ]
}
~~~

Projection:

~~~javascript
{ "variants.color": 1, _id: 0 }
~~~

có thể trả **màu của cả hai phần tử**, chứ không tự lọc chỉ variant còn hàng. Nếu muốn chỉ giữ các phần tử thỏa điều kiện, cần projection operator phù hợp như **$elemMatch** trong trường hợp đơn giản hoặc aggregation **$filter** khi muốn biến đổi mảng phức tạp.

## 7. Vì sao không nên đọc entity đã projection thiếu field rồi save?

Ví dụ ProductDocument được định nghĩa bằng record chứa nhiều property, trong đó priceMinor và stock là primitive. Nếu query chỉ trả name, framework có thể gặp vấn đề materialization, gán giá trị mặc định cho field thiếu hoặc tạo object không mang toàn bộ dữ liệu cần thiết, tùy converter và kiểu domain.

Không nên dùng:

~~~java
Query query = new Query();
query.fields().include("name");

List<ProductDocument> partial =
    mongoTemplate.find(query, ProductDocument.class);

// Không save lại mỗi phần tử partial như thể là entity đầy đủ.
~~~

Nếu ứng dụng save một entity chỉ được tải một phần, thao tác replace/update không phù hợp có thể làm mất field chưa tải. Đây là lỗi **data integrity**, không chỉ vấn đề hiệu năng.

Để trả một thẻ sản phẩm, ưu tiên **DTO/projection riêng**:

~~~java
public record ProductCard(
    String id,
    String sku,
    String name,
    long priceMinor
) {}
~~~

Một cách minh bạch là lấy kết quả projection ở dạng **Document** và map sang DTO. Ví dụ ở phần 13 sẽ làm rõ điều này. Với API repository, có thể dùng interface projection hoặc DTO có constructor phù hợp. Không giả định một class bất kỳ có thể được ánh xạ thành công từ một kết quả thiếu property bắt buộc.

## 8. Sort: một trường và nhiều trường

MongoDB có cú pháp sắp xếp:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1 }
).sort({
  createdAt: -1
});
~~~

Giá trị **1** trong sort là tăng dần, **-1** là giảm dần. Chúng khác với số 1/0 dùng trong projection.

Spring Data MongoDB:

~~~java
import org.springframework.data.domain.Sort;

Query query = Query.query(Criteria.where("active").is(true));

query.with(
    Sort.by(Sort.Order.desc("createdAt"))
);
~~~

Để sắp xếp theo category tăng dần, giá giảm dần:

~~~java
query.with(Sort.by(
    Sort.Order.asc("category"),
    Sort.Order.desc("priceMinor")
));
~~~

MongoDB thực hiện sort dựa trên **field dữ liệu**, không phải vị trí các phần tử đã được đưa về Java. Query có sort nên được MongoDB thực thi trực tiếp để kết hợp với index và giới hạn kết quả.

### 8.1. Sort có thể dùng field không nằm trong projection

Ví dụ chỉ trả name và priceMinor nhưng sort theo createdAt:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("name")
    .include("priceMinor")
    .exclude("_id");

query.with(Sort.by(Sort.Order.desc("createdAt")));
~~~

**createdAt không nhất thiết phải được trả về** dù được dùng để sort. MongoDB có thể dùng nó để sắp xếp trước khi áp dụng projection. Tuy nhiên, với phân trang theo con trỏ dựa vào createdAt, API cần cách lưu/đọc lại giá trị cursor thích hợp.

## 9. Sort ổn định: luôn nghĩ tới khóa phụ

Nếu hai product có cùng createdAt, sort chỉ theo createdAt không tạo thứ tự tuyệt đối giữa chúng. Trong phân trang, điều này có thể khiến bản ghi xuất hiện ở các vị trí không ổn định.

Giải pháp phổ biến là bổ sung **_id**:

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Query query = Query.query(Criteria.where("active").is(true))
    .with(stableSort);
~~~

Trong mapping entity, property Java **id** được ánh xạ thành BSON **_id**. Tương đương trong mongosh:

~~~javascript
db.products.find({ active: true })
  .sort({ createdAt: -1, _id: -1 });
~~~

### 9.1. Sort không đồng nghĩa có index

Một sort hợp lệ vẫn có thể chậm nếu MongoDB phải sắp xếp nhiều document ngoài index. Cần đánh giá index theo filter, sort và mức độ chọn lọc. Một query cần **category = BOOK**, **active = true**, sort **createdAt DESC, _id DESC** có thể xem xét compound index theo chính các field đó.

### 9.2. Sort chuỗi, collation và dữ liệu thiếu

Sort trên String chịu ảnh hưởng của **collation**, kiểu dữ liệu BSON và cách server so sánh. Nếu API yêu cầu sắp xếp theo ngôn ngữ hay không phân biệt chữ hoa/thường, cần cấu hình collation phù hợp và kiểm tra xem index có cùng collation hay không. Một Sort theo name không tự trở thành sort theo thứ tự từ điển tiếng Việt trong mọi cấu hình.

Field thiếu hoặc null cũng có quy tắc sắp xếp BSON riêng. Với dữ liệu không đồng nhất, đừng suy ra thứ tự từ quan sát vài document mẫu.

## 10. Limit: giới hạn số document

**limit(n)** giới hạn tối đa số kết quả của query:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.limit(20);
~~~

Tương đương:

~~~javascript
db.products.find({ active: true })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Nếu chỉ có 7 document khớp filter, kết quả chứa tối đa 7, không tự bổ sung thành 20. **limit không có nghĩa server đã đếm toàn bộ số document phù hợp**.

### 10.1. Luôn giới hạn kích thước do client yêu cầu

Nếu client có thể truyền size=1.000.000, việc dùng trực tiếp **query.limit(size)** dễ gây truy vấn rất nặng. Tầng service nên đặt max size và validate:

~~~java
if (size < 1 || size > 100) {
    throw new IllegalArgumentException(
        "Page size must be between 1 and 100"
    );
}

query.limit(size);
~~~

Trong Spring Data Query, **limit(0)** thường biểu thị không áp dụng giới hạn theo quy ước MongoDB; vì vậy không dùng số 0 để biểu thị “không trả phần tử” khi xây API phân trang. Hãy kiểm tra input và trả trang rỗng có chủ đích nếu nghiệp vụ yêu cầu, không trông đợi limit(0) là an toàn.

### 10.2. Không dùng take() thay limit() ở MongoDB

Không nên lấy toàn bộ kết quả về Java rồi cắt:

~~~java
// Không nên trên tập dữ liệu lớn: có thể đã tải rất nhiều document.
List<ProductDocument> all = mongoTemplate.find(
    Query.query(Criteria.where("active").is(true)),
    ProductDocument.class
);

List<ProductDocument> firstTwenty =
    all.subList(0, Math.min(20, all.size()));
~~~

Giới hạn phải được đẩy vào truy vấn server. Một hạn chế tương tự áp dụng cho ReactiveMongoTemplate: dùng **Query.limit** trước khi tạo Flux thay vì đọc Flux không giới hạn rồi collect toàn bộ.

## 11. Skip: bỏ qua bao nhiêu document?

**skip(n)** bỏ qua n document đầu tiên trong tập kết quả sau khi áp dụng filter và thứ tự sort, rồi mới lấy tối đa limit bản ghi.

~~~java
Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);

query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));

query.skip(20);
query.limit(20);
~~~

Ví dụ trên lấy **trang thứ hai** nếu mỗi trang có 20 bản ghi và trang được đánh số từ 0. Tương đương:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
})
.sort({ createdAt: -1, _id: -1 })
.skip(20)
.limit(20);
~~~

### 11.1. Công thức offset

Với pageNumber bắt đầu từ 0:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

| Page | Size | Skip | Limit |
| --- | --- | --- | --- |
| 0 | 20 | 0 | 20 |
| 1 | 20 | 20 | 20 |
| 2 | 20 | 40 | 20 |
| 5 | 10 | 50 | 10 |

**Không nhầm page=1 với trang đầu** trong PageRequest của Spring Data, vì page index bắt đầu từ 0. Một client UI hiển thị “Trang 1” có thể cần chuyển thành page=0 trước khi gọi service.

### 11.2. Phải sort trước khi dùng skip

Trong query API, thứ tự gọi method skip/limit/with không nên được hiểu là thứ tự Java xử lý kết quả; chúng cấu hình các phần của truy vấn gửi xuống server. Điều quan trọng là **có sort tường minh**.

Nếu không sort, skip dựa trên thứ tự kết quả không được bảo đảm. Một thay đổi index, cách truy vấn hoặc ghi đồng thời có thể làm cùng offset cho kết quả khác nhau.

## 12. Pageable và Query.with(Pageable)

Thay vì tự tính skip và limit, có thể dùng **Pageable**:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    2,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
query.with(pageable);
~~~

Pageable ở đây có **offset=40**, **limit=20** và sort theo createdAt, id. Query.with(Pageable) áp dụng các thành phần đó vào Query.

**Không kết hợp tùy tiện** Query.with(pageable) với những lời gọi skip/limit độc lập nếu không có lý do rõ. Lời gọi sau có thể thay đổi cấu hình trước, dẫn đến kết quả không đúng page mà client yêu cầu.

### 12.1. Tránh nhân offset trùng hai lần

Ví dụ dễ nhầm:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.skip(pageable.getOffset());
query.with(pageable);
~~~

Đừng viết theo kiểu tưởng rằng hai lời gọi cộng dồn offset. Chỉ cần **query.with(pageable)** hoặc chủ động thiết lập **skip, limit và sort** một cách thống nhất.

### 12.2. Chọn cách nào?

| Trường hợp | Cách phù hợp |
| --- | --- |
| API trang có page, size, sort | Pageable + Query.with(pageable) |
| Báo cáo chỉ lấy N sản phẩm mới nhất | Query.with(sort) + Query.limit(N) |
| Cursor/seek pagination | Query filter theo cursor + sort + limit |
| Query động theo nhiều filter | Criteria động + Query + phương thức phân trang tương ứng |

Chỉ chọn một nguồn chân lý cho offset/limit trong mỗi đường xử lý, giúp việc review và kiểm thử dễ hơn.

## 13. Ví dụ service hoàn chỉnh: projection + sort + skip + limit

Để trả DTO gọn, ví dụ sau truy vấn **Document BSON thô**, rồi map tường minh sang kiểu public:

~~~java
package com.example.catalog;

import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public record ProductCard(
    String id,
    String sku,
    String name,
    long priceMinor
) {}

public class ProductCatalogService {

    private final MongoTemplate mongoTemplate;

    public ProductCatalogService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ProductCard> listActiveBooks(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page/size");
        }

        long offset = Math.multiplyExact((long) page, size);

        Query query = Query.query(
            Criteria.where("category").is("BOOK")
                .and("active").is(true)
        );
        query.fields()
            .include("_id")
            .include("sku")
            .include("name")
            .include("priceMinor");

        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("_id")
        ));
        query.skip(offset);
        query.limit(size);

        List<Document> docs =
            mongoTemplate.find(query, Document.class, "products");

        return docs.stream()
            .map(this::toCard)
            .toList();
    }

    private ProductCard toCard(Document doc) {
        ObjectId id = doc.getObjectId("_id");
        return new ProductCard(
            id.toHexString(),
            doc.getString("sku"),
            doc.getString("name"),
            doc.getLong("priceMinor")
        );
    }
}
~~~

Ví dụ sử dụng **Document.class** và tên collection tường minh để kiểm tra projection BSON dễ dàng. Nó giả định dữ liệu priceMinor được lưu ở kiểu BSON Int64 và _id là ObjectId. Nếu dữ liệu cũ dùng Int32/String cho giá hoặc _id dạng khác, cần chuẩn hóa dữ liệu và điều chỉnh mapping, không giả định mọi kiểu tự được chuyển thành Long/ObjectId.

Một lựa chọn khác là dùng entity metadata cùng DTO/interface projection phù hợp để không phải tự thao tác Document. Tuy nhiên, chỉ lấy các field cần thiết và **không save entity partial** vẫn là nguyên tắc quan trọng.

### 13.1. Query có sort field không được trả về

Service trên sort theo createdAt nhưng projection không trả createdAt. Điều này hợp lệ cho offset pagination: MongoDB dùng createdAt trong sort, sau đó chỉ trả những field được chọn.

Nếu chuyển sang keyset pagination, cursor cần createdAt và _id của bản ghi cuối. Khi ấy cần giữ createdAt trong dữ liệu truy vấn hoặc có một cơ chế giữ cursor riêng, không tự bỏ trường đang dùng làm mốc chuyển trang.

### 13.2. Service không cần trả total

Hàm listActiveBooks trả **List<ProductCard>** của một trang. Số phần tử trong list không bằng tổng số product phù hợp. Nếu UI cần **totalElements**, phải thực hiện truy vấn count riêng với đúng filter; phần 15 giải thích rõ cách làm.

## 14. Lấy hasNext mà không đếm: limit(size + 1)

Giả sử client cần nút “Tải thêm” nhưng không cần tổng số trang. Thay vì count, có thể lấy **một bản ghi dư**:

1. Client yêu cầu page=2, size=20.
2. Tính skip=40 như bình thường.
3. Đặt limit=21.
4. Nếu truy vấn trả 21 bản ghi, hasNext=true; chỉ công bố 20 bản ghi đầu.

~~~java
int page = 2;
int size = 20;
long offset = Math.multiplyExact((long) page, size);

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.skip(offset);
query.limit(size + 1);

List<ProductDocument> fetched =
    mongoTemplate.find(query, ProductDocument.class);

boolean hasNext = fetched.size() > size;
List<ProductDocument> content = fetched.subList(
    0, Math.min(size, fetched.size())
);
~~~

Ở đây không dùng projection thiếu field nên MongoTemplate có thể materialize ProductDocument đầy đủ cho ví dụ về Slice. Với API thực, có thể dùng DTO projection như phần 13.

### 14.1. Lỗi khi thay size trong PageRequest

**Sai:** dùng PageRequest.of(2, 21) để đọc thêm phần tử, vì offset lúc ấy bằng **42**.

**Đúng:** giữ offset theo **page * size = 40**, chỉ tăng limit lên **size+1 = 21**.

Nếu dùng Query.with(PageRequest.of(2, 20, sort)), có thể áp dụng **query.limit(21)** sau đó, giữ nguyên offset được tính từ 20. Phải kiểm thử hành vi theo phiên bản Spring Data mà dự án sử dụng.

### 14.2. hasNext không phải total

Nếu có một bản ghi dư, chỉ suy ra có ít nhất một bản ghi sau trang hiện tại tại thời điểm query. Không thể kết luận chính xác tổng số phần tử hay số trang còn lại. Với collection bị ghi/xóa đồng thời, lần truy vấn kế tiếp vẫn có thể cho kết quả khác.

## 15. Count riêng: đừng dùng query đã skip/limit để đếm tổng

Khi UI cần “Đang hiển thị trang 3/25” hoặc “Có 482 sản phẩm”, cần count tương ứng với filter:

~~~java
Query countQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);

long total = mongoTemplate.count(
    countQuery, ProductDocument.class
);
~~~

Count query trên không có projection, sort, skip hoặc limit. Vì vậy total đại diện cho **toàn bộ tập document thỏa filter** theo trạng thái database mà query nhìn thấy.

**Không nên tái sử dụng trực tiếp Query đã gọi skip/limit để tính tổng**, vì semantics của count có thể chịu ảnh hưởng các tùy chọn phân trang và phiên bản Spring Data. Tạo **một Query chỉ chứa filter** là cách đơn giản và rõ nghĩa.

### 15.1. Page và Slice khác nhau ở metadata

| Dạng kết quả | Có content trang? | Có hasNext? | Có total? |
| --- | --- | --- | --- |
| List<T> | Có | Không tự động | Không |
| Slice<T> | Có | Có | Không |
| Page<T> | Có | Có | Có |

Muốn tạo Page:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;

Page<ProductDocument> result = new PageImpl<>(
    content,
    pageable,
    total
);
~~~

Ví dụ này giả định content đã được đọc đúng trang, pageable là cấu hình trang tương ứng và total được lấy bằng count chỉ filter. Khi không cần total, Slice/hasNext thường tiết kiệm một truy vấn.

### 15.2. Count và dữ liệu trang có thể lệch thời điểm

Khi hai query chạy riêng, một writer có thể insert/xóa document ở giữa. Do đó content và total không nhất thiết phản ánh đúng cùng một snapshot. Nếu nghiệp vụ đòi tính nhất quán chặt, cần thiết kế read concern/transaction/snapshot phù hợp với MongoDB deployment; chỉ ghép kết quả Java không tạo snapshot tự động.

## 16. Skip sâu và keyset pagination

Offset pagination tiện vì client có thể nhảy trực tiếp đến trang N. Nhưng skip ở trang sâu có thể đắt:

~~~javascript
db.products.find({ category: "BOOK", active: true })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
~~~

Dù chỉ trả 20 document, MongoDB có thể vẫn phải duyệt nhiều index key trước vị trí skip. Có index không đồng nghĩa skip sâu sẽ rẻ.

### 16.1. Keyset/seek theo bản ghi cuối

Nếu client chỉ cần “trang tiếp theo”, có thể dùng cursor gồm:

- **createdAt** của bản ghi cuối trang trước;
- **_id** của bản ghi đó.

Với sort createdAt DESC, _id DESC, các bản ghi tiếp theo có điều kiện:

\[
\text{createdAt} < T
\quad \text{hoặc} \quad
(\text{createdAt} = T \land \_id < I)
\]

Trong MongoDB:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true,
  $or: [
    { createdAt: { $lt: ISODate("2025-06-02T09:00:00Z") } },
    {
      createdAt: ISODate("2025-06-02T09:00:00Z"),
      _id: { $lt: ObjectId("507f1f77bcf86cd799439012") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

Trong Query/Criteria:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

Instant cursorCreatedAt = Instant.parse(
    "2025-06-02T09:00:00Z"
);
ObjectId cursorId = new ObjectId(
    "507f1f77bcf86cd799439012"
);

Criteria afterCursor = new Criteria().orOperator(
    Criteria.where("createdAt").lt(cursorCreatedAt),
    new Criteria().andOperator(
        Criteria.where("createdAt").is(cursorCreatedAt),
        Criteria.where("id").lt(cursorId)
    )
);

Criteria filter = new Criteria().andOperator(
    Criteria.where("category").is("BOOK"),
    Criteria.where("active").is(true),
    afterCursor
);

Query query = Query.query(filter)
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ))
    .limit(21);
~~~

Khi chạy **mongoTemplate.find(query, ProductDocument.class)**, Spring Data map property id thành _id. Lần đầu chưa có cursor, query chỉ cần filter/sort/limit; các lần tiếp theo thêm điều kiện cursor và không dùng skip.

**Điều kiện cursor phải khớp chiều sort.** Nếu đổi sort sang ASC mà vẫn dùng $lt thì sẽ bỏ qua hoặc trả sai các phần tử. Trong ứng dụng thật, nên validate và bảo vệ cursor token, đồng thời ràng buộc tenant/filter từ ngữ cảnh xác thực.

### 16.2. Keyset không phải snapshot bất biến

Keyset có thể giảm lỗi do insert mới phía trước cursor làm dịch offset, nhưng không ngăn document phía sau bị sửa/xóa. Với nghiệp vụ cần xuất dữ liệu đầy đủ nhất quán tại một thời điểm, phải thiết kế thêm cơ chế snapshot hoặc quy trình đối soát, không dựa hoàn toàn vào keyset.

## 17. Index cho filter, sort và projection

Một truy vấn thường xuyên:

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
)
.sort({ createdAt: -1 });
~~~

Có thể đánh giá một index theo equality filter, khóa sort và các field cần cho projection:

~~~javascript
db.products.createIndex({
  category: 1,
  active: 1,
  createdAt: -1,
  sku: 1,
  name: 1,
  priceMinor: 1
});
~~~

Đây là **một ứng viên** cho mẫu query, không phải thiết kế index bắt buộc. Nếu có rất nhiều đường truy vấn khác nhau, index quá rộng có thể làm tăng chi phí ghi và bộ nhớ index. Cần đo với dữ liệu thật và tối ưu cho workload quan trọng.

### 17.1. Projection có thể tạo covered query

Nếu filter, sort và tất cả các field được trả đều có thể được cung cấp từ index, MongoDB có thể tránh đọc document gốc. Trường hợp này thường gọi là **covered query**.

Nếu index trên **không có _id**, projection mặc định trả _id có thể làm mất điều kiện covered. Khi API không cần ID, thêm **_id: 0** giúp query trở thành ứng viên cho việc được index bao phủ.

### 17.2. Dùng explain("executionStats")

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
)
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
~~~

| Chỉ số/kế hoạch | Ý nghĩa |
| --- | --- |
| winningPlan | MongoDB chọn đường thực thi nào |
| totalKeysExamined | Số index key đã duyệt |
| totalDocsExamined | Số document gốc đã đọc |
| nReturned | Số kết quả trả về |
| FETCH stage | Có cần đọc document từ collection không |
| SORT stage | Có sort bổ sung ngoài index không |
| executionTimeMillis | Độ trễ quan sát được |

Với một covered query điển hình, totalDocsExamined có thể bằng 0. Nhưng nReturned nhỏ không tự chứng minh query hiệu quả: skip sâu có thể khiến totalKeysExamined rất lớn.

## 18. ReactiveMongoTemplate dùng cùng Query

Query, Criteria, fields, sort, skip và limit cũng được dùng với **ReactiveMongoTemplate**:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> recentBooks(
        ReactiveMongoTemplate template, int size) {

    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Invalid size"));
    }

    Query query = Query.query(
        Criteria.where("category").is("BOOK")
            .and("active").is(true)
    );

    query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ));
    query.limit(size);

    return template.find(query, ProductDocument.class);
}
~~~

Hàm trả **Flux** chứa tối đa size ProductDocument. Nó không thực hiện query cho tới khi có subscriber. Không gọi **block()** trong WebFlux để chuyển Flux thành List đồng bộ.

### 18.1. Dùng projection trong reactive query

~~~java
import org.bson.Document;

Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("sku")
    .include("name")
    .exclude("_id");
query.with(Sort.by(Sort.Order.asc("name")));
query.limit(50);

Flux<Document> cards =
    reactiveTemplate.find(query, Document.class, "products");
~~~

Ví dụ giả định reactiveTemplate được inject và sử dụng collection products. Nếu cần trả DTO, có thể map các Document phát ra thành kiểu kết quả phù hợp. Reactor backpressure không thay thế việc đặt limit tại MongoDB.

### 18.2. collectList chỉ sau khi đã giới hạn

~~~java
Mono<List<Document>> batch = cards.collectList();
~~~

Ở đây batch đã giới hạn 50 phần tử nên việc gom thành List có chi phí bộ nhớ được kiểm soát. Không dùng **findAll().collectList()** trên collection lớn chỉ để lấy vài bản ghi đầu.

## 19. Query so với aggregation và repository

MongoTemplate Query phù hợp với nhiều thao tác find động. Một repository có thể diễn đạt filter và sort qua method name, @Query hoặc Pageable. Khi query cần:

- **$group** để tổng hợp số lượng;
- **$lookup** để ghép collection;
- **$project** với biểu thức tính toán;
- **$filter** để lọc phần tử mảng;
- nhiều stage biến đổi cấu trúc;

thì aggregation là lựa chọn phù hợp hơn một find projection đơn giản.

Một pipeline ví dụ:

~~~javascript
db.products.aggregate([
  { $match: { category: "BOOK", active: true } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 20 },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      sku: 1,
      displayName: "$name",
      priceMinor: 1
    }
  }
]);
~~~

**Chú ý thứ tự các stage trong aggregation có thể ảnh hưởng kết quả**: $sort trước $skip/$limit để xác định trang; nếu $limit đứng trước $skip, nhiều trường hợp sẽ cho kết quả sai hoặc rỗng. Với find, các phương thức sort/skip/limit cấu hình một truy vấn; không nên suy từ thứ tự gọi Java rằng xử lý giống một pipeline stage bất kỳ.

Nếu phải dựng aggregation pipeline nhiều bước trong Java, dùng các API aggregation Spring Data MongoDB hoặc @Aggregation theo khả năng phiên bản dự án.

## 20. Kiểm thử Query, Criteria, projection và paging

Chỉ mock MongoTemplate không chứng minh MongoDB thực thi filter/sort/skip/limit như mong đợi. Nên có kiểm thử tích hợp trên MongoDB **test riêng**, ví dụ Testcontainers hoặc một instance test được quản lý.

### 20.1. Những điều cần xác minh

| Kịch bản | Kỳ vọng |
| --- | --- |
| category=BOOK, active=true | Không trả product category khác hoặc inactive |
| limit=2 | Kết quả có tối đa 2 document |
| skip=2, limit=2 | Lấy phần thứ ba và thứ tư theo cùng sort |
| Hai document có createdAt trùng | Sort phụ _id tạo thứ tự xác định |
| Include sku, name | Không trả field thường khác; _id vẫn xuất hiện |
| Include sku, exclude _id | Không trả _id |
| Include name và exclude stock | Projection bị từ chối |
| Exclude supplier.internalNote | Không còn internalNote trong BSON |
| Count với query chỉ filter | Trả tổng khớp filter, không bị giới hạn bởi page |
| Page vượt cuối dữ liệu | Trả danh sách rỗng |
| Projection thiếu field | Không đem entity partial đi save |
| Index và sort | Đo explain trên workload thực tế |

### 20.2. Test tích hợp với MongoTemplate

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductQueryPagingTest {

    @Autowired
    private MongoTemplate template;

    @Test
    void projectionSortSkipAndLimitWorkTogether() {
        String prefix = "TEST-" + UUID.randomUUID() + "-";
        Instant time = Instant.parse("2025-06-01T09:00:00Z");
        List<ObjectId> insertedIds = new ArrayList<>();

        try {
            for (int i = 0; i < 5; i++) {
                ProductDocument saved = template.insert(
                    new ProductDocument(
                        null,
                        prefix + i,
                        "Product " + i,
                        "BOOK",
                        true,
                        (i + 1) * 10_000L,
                        i + 1,
                        new ProductDocument.Supplier("S", "PRIVATE"),
                        time.plusSeconds(i)
                    )
                );
                insertedIds.add(saved.id());
            }

            Query query = Query.query(
                Criteria.where("sku").regex(
                    "^" + java.util.regex.Pattern.quote(prefix)
                )
            );
            query.fields()
                .include("sku")
                .include("name")
                .exclude("_id");
            query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
            ));
            query.skip(2);
            query.limit(2);

            List<Document> page = template.find(
                query, Document.class, "products"
            );

            assertThat(page).hasSize(2);
            assertThat(page.get(0).getString("sku"))
                .isEqualTo(prefix + 2);
            assertThat(page.get(1).getString("sku"))
                .isEqualTo(prefix + 1);
            assertThat(page.get(0).containsKey("_id")).isFalse();
            assertThat(page.get(0).containsKey("supplier")).isFalse();
        } finally {
            for (ObjectId id : insertedIds) {
                template.remove(
                    Query.query(Criteria.where("_id").is(id)),
                    ProductDocument.class
                );
            }
        }
    }
}
~~~

Test này ghi năm document với thời gian tăng lần lượt. Sort createdAt DESC cho thứ tự 4,3,2,1,0; skip hai phần tử rồi limit hai phần tử cho **2,1**. Việc kiểm tra BSON Document thô xác minh **không có _id và supplier** trong kết quả.

Ví dụ cần MongoDB test instance được cấu hình sẵn và phiên bản Spring Boot hỗ trợ @DataMongoTest. Không chạy test trên production. Một test đầy đủ khác nên seed document category khác và inactive để xác minh filter, đồng thời test trường hợp hai document có cùng createdAt.

### 20.3. Test count tách khỏi skip/limit

~~~java
Query dataQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
dataQuery.with(Sort.by(Sort.Order.desc("createdAt")));
dataQuery.skip(20).limit(20);

Query countQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
long total = template.count(countQuery, ProductDocument.class);
~~~

Đừng dùng dữ liệu test chung để assert một total cụ thể khi có test khác insert đồng thời. Tạo tập test riêng hoặc filter bằng mã thử nghiệm/tenant phù hợp.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ include name nhưng _id vẫn có | MongoDB trả _id mặc định | Thêm exclude("_id") khi không cần |
| Projection bị server từ chối | Trộn include/exclude ngoài _id | Dùng một mode và ngoại lệ _id |
| DTO bị null/default | Thiếu field cho constructor/property | Chọn đủ field hoặc đổi kiểu projection |
| save làm mất dữ liệu | Save entity đọc thiếu field | Dùng update theo field hoặc đọc đầy đủ |
| Trang 1 và 2 có phần tử trùng | Sort không ổn định hoặc dữ liệu thay đổi | Sort có khóa phụ _id, xem keyset |
| Page bắt đầu sai | Nhầm trang từ 0 hay 1 | Chuẩn hóa pageNumber ở API |
| limit không giới hạn như tưởng | Truyền 0 hoặc input không được validate | Bảo đảm 1 <= size <= max |
| Trang rất sâu chậm | Skip phải duyệt nhiều phần tử | Dùng index, xem keyset |
| Count nhỏ hơn total mong đợi | Count dùng query có skip/limit hoặc filter lệch | Tạo countQuery chỉ chứa đúng filter |
| Truy vấn thiếu sản phẩm | Sai category/active hoặc kiểu BSON | So sánh filter và dữ liệu thật |
| Sort không đúng ngôn ngữ | Chưa cấu hình collation | Chọn collation và index phù hợp |
| API trả field nội bộ | Dùng exclusion không chặn field mới | Dùng inclusion whitelist và DTO |
| Truy vấn chậm dù ít field | Filter/sort/index chưa phù hợp | Dùng explain, đo keys/docs examined |
| Reactive code bị block | block() hoặc collectList quá nhiều | Đưa limit xuống MongoDB, giữ Flux/Mono |

Quy trình chẩn đoán:

1. Xác nhận collection và BSON thực tế.
2. Kiểm tra Criteria có đúng điều kiện và kiểu dữ liệu không.
3. Kiểm tra fields() là inclusion hay exclusion, đã xử lý _id chưa.
4. Kiểm tra Sort và khóa phụ xác định thứ tự.
5. Kiểm tra skip, limit và PageRequest có dùng cùng page size không.
6. Nếu có count, dùng cùng filter nhưng không vô tình áp dụng pagination.
7. Dùng mongosh và explain để phân biệt lỗi logic với vấn đề hiệu năng.
8. Thêm test hồi quy cho dữ liệu bị thiếu field, đồng thời thay đổi và phân trang sâu.

## 22. Bài tập thực hành

### Bài tập 1: chọn trường và bỏ _id

Tìm product active, chỉ trả sku và name, không trả ID.

**Gợi ý đáp án:**

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("sku")
    .include("name")
    .exclude("_id");
~~~

### Bài tập 2: sửa projection sai

Một developer viết:

~~~java
query.fields()
    .include("name")
    .exclude("supplier.internalNote");
~~~

**Câu hỏi:** vì sao sai?

**Đáp án:** trộn inclusion và exclusion cho hai field thường. Nếu chỉ cần name, dùng include("name") và tùy chọn exclude("_id"). Trường internalNote tự bị loại vì không được include.

### Bài tập 3: tính skip

Client yêu cầu trang thứ tư theo UI đánh số từ 1, size=25. Spring Data pageNumber cần là bao nhiêu? Skip bao nhiêu?

**Đáp án:** pageNumber=3, skip=75, limit=25.

### Bài tập 4: sort ổn định

Hai product có createdAt giống nhau. Nên sort thế nào để các page có thứ tự xác định?

**Đáp án:** sort createdAt DESC, id DESC (ánh xạ thành _id). Nếu dữ liệu thay đổi giữa các request, offset vẫn có thể lệch; cân nhắc keyset.

### Bài tập 5: hasNext không có count

Page=2, size=20. Bạn muốn biết còn trang sau hay không mà không chạy count. Đọc bao nhiêu bản ghi? Skip bao nhiêu?

**Đáp án:** skip=40, limit=21; chỉ công bố 20 bản ghi đầu. Nếu query trả 21 bản ghi thì hasNext=true.

### Bài tập 6: count riêng

Data query có category=BOOK, active=true, sort createdAt DESC, skip=100, limit=20. Bạn nên dùng query nào để đếm total?

**Đáp án:** tạo Query mới chỉ chứa Criteria category=BOOK và active=true; không dùng sort, skip, limit cho total toàn tập.

### Bài tập 7: index và projection

Filter category/active, sort createdAt DESC, projection sku/name/priceMinor nhưng không cần _id. Đề xuất cách xác định có thể covered query không.

**Gợi ý:** đánh giá index có các field filter, sort và projection, loại _id bằng _id:0 nếu index không có ID, chạy explain("executionStats") và kiểm tra FETCH/totalDocsExamined. Không khẳng định có covered query chỉ vì đã tạo index.

### Bài tập 8: phân trang sâu

Một API trả trang ở skip=500.000 rất chậm. Có nên chỉ giảm số field projection để xử lý hoàn toàn?

**Đáp án:** không. Projection có thể giảm dữ liệu trả, nhưng server vẫn phải vượt qua offset lớn. Đánh giá index/filter/sort và chuyển sang keyset/seek nếu use case là duyệt tuần tự.

### Bài tập 9: reactive

Service reactive lấy findAll().collectList() rồi cắt thành trang. Nên sửa theo hướng nào?

**Đáp án:** tạo Query có Criteria, sort, skip/limit trực tiếp tại MongoDB, sau đó gọi ReactiveMongoTemplate.find(...) trả Flux. Chỉ collectList khi luồng đã được giới hạn kích thước.

## 23. Nguyên tắc cần ghi nhớ

1. **Criteria lọc document; Query điều khiển projection, sort, skip và limit.**
2. **fields().include** trả các field được chọn; **fields().exclude** loại các field chỉ định.
3. **Không trộn inclusion/exclusion ngoài _id**. Trường _id được trả mặc định và có thể loại riêng.
4. **Sort ổn định cần khóa phụ** như id/_id, đặc biệt khi phân trang.
5. **limit giới hạn số bản ghi**, không có nghĩa tự đếm; **skip bỏ qua** vị trí theo thứ tự đã sắp xếp.
6. **Pageable** có page index bắt đầu từ 0; nên dùng một nguồn xác định skip/limit để tránh nhầm.
7. **Slice đọc size+1** giúp phát hiện hasNext mà không phải đếm; tổng số cần query count riêng.
8. **Count toàn tập phải dùng filter-only query**, không tái sử dụng tùy tiện query đã phân trang.
9. **Skip sâu có chi phí**, keyset/seek là lựa chọn tốt cho “tải tiếp” trên dữ liệu lớn.
10. **Projection và index có thể phối hợp cho covered query**, nhưng phải đo explain trên workload thực.
11. **Không save lại entity đã projection thiếu field**; dùng DTO riêng và update có điều kiện.
12. **Reactive và aggregation có các cách dùng tương ứng**, nhưng vẫn phải đảm bảo sort, limit và phân quyền đúng.

Hiểu và kết hợp đúng **field projection, sort, limit và skip** giúp dịch vụ **SPRING_DATA_MONGODB** xây dựng truy vấn MongoTemplate rõ ràng, trả DTO gọn, phân trang đáng tin cậy và tối ưu hiệu năng theo đúng nhu cầu thực tế.
