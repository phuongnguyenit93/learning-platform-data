# Dùng Filters, Projections, Sorts và Updates cho CRUD trong MongoDB Java Driver

Trong Java, MongoDB hỗ trợ nhiều cách mô tả truy vấn và cập nhật BSON. Thay vì ghép chuỗi JSON hoặc tự tạo từng Document biểu diễn operator, MongoDB Java Sync Driver cung cấp các **builder classes**: **Filters** để chọn dữ liệu, **Projections** để giới hạn các trường trả về, **Sorts** để định nghĩa thứ tự và **Updates** để mô tả thay đổi được áp dụng ở phía MongoDB server.

Bốn nhóm builder này kết hợp tự nhiên với các API CRUD của **MongoCollection**. Chúng giúp code rõ ràng hơn, dễ kiểm thử hơn và tránh nhiều lỗi do ghép cú pháp thủ công. Tuy nhiên, builder không tự bảo đảm tính đúng đắn nghiệp vụ: cần kiểm tra tenant authorization, kiểu dữ liệu, indices, điều kiện cạnh tranh và cách xử lý kết quả ghi.

~~~text
                       MongoCollection<Document>
                                |
             +------------------+------------------+
             |                  |                  |
           CREATE              READ           UPDATE/DELETE
             |                  |                  |
         insertOne        find(Filters)        updateOne(Filters, Updates)
         insertMany        projection           updateMany(Filters, Updates)
                           (Projections)        findOneAndUpdate
                           sort(Sorts)          replaceOne
                           skip/limit           deleteOne(Filters)
                                               deleteMany(Filters)
~~~

Bài học thuộc chương **Java Driver**, module **Database Engine Document MongoDB**, tập trung vào thao tác CRUD với **MongoDB Java Sync Driver**. Các ví dụ dùng database lab riêng, không cần thay đổi môi trường production.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Kết nối MongoDB với MongoClient và MongoCollection.
2. Hiểu **Bson** và lý do các builders có thể truyền vào nhiều API driver.
3. Sử dụng Filters cho equality, range, logic, tập giá trị, arrays, nested fields và null/missing.
4. Dùng Projections.include/exclude/fields để trả về đúng các trường.
5. Dùng Sorts.ascending/descending/orderBy cho thứ tự ổn định và pagination.
6. Dùng Updates.set/inc/unset/combine/array operators để cập nhật server-side.
7. Thực hiện insertOne, find, updateOne, updateMany, replaceOne, deleteOne và findOneAndUpdate.
8. Hiểu matchedCount/modifiedCount, upsert và cách tránh lost update.
9. Thiết kế tenant-scoped CRUD, index, error handling và tests.
10. Phân biệt atomic update một document với thay đổi nhiều documents.

**Phạm vi phiên bản:** Ví dụ theo MongoDB Java Sync Driver hiện đại. Một số overload/operator và tính năng server yêu cầu phiên bản tương thích. Chọn dependency thực tế theo tài liệu driver/server đang chạy, thay vì mặc định mọi deployment dùng chung một phiên bản.

## 2. Chuẩn bị môi trường

Cần có JDK tương thích, MongoDB deployment được phép truy cập, dependency **org.mongodb:mongodb-driver-sync**, và URI qua biến môi trường MONGODB_URI.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>CHOOSE_COMPATIBLE_VERSION</version>
</dependency>
~~~

CHOOSE_COMPATIBLE_VERSION là placeholder, không phải version để build trực tiếp. Dùng một release đã kiểm tra compatibility và được quản lý nhất quán trong project.

Các imports phổ biến:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;

import org.bson.Document;
import org.bson.conversions.Bson;
~~~

### 2.1. Kết nối tối thiểu

~~~java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalArgumentException(
        "Thiếu biến môi trường MONGODB_URI"
    );
}

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db = client.getDatabase(
        "java_driver_crud_lab"
    );
    MongoCollection<Document> products =
        db.getCollection("products");

    System.out.println(products.countDocuments());
}
~~~

### 2.2. MongoClient lifecycle

Trong web service, nên tái sử dụng MongoClient và để framework/container quản lý lifecycle. Không tạo và đóng một client mới cho từng HTTP request; driver còn thực hiện connection pooling và server discovery.

### 2.3. Bảo vệ secrets

Không log MongoDB URI đầy đủ nếu có username/password. Sử dụng secret manager, TLS và credentials có quyền phù hợp.

## 3. Dữ liệu mẫu xuyên suốt

Bài dùng ba collections: **products**, **orders** và **customers**. Những ví dụ độc lập, có thể khiến dữ liệu lab đổi sau khi chạy update. Nếu cần kết quả ban đầu, tạo lại seed trên một database thử được phép.

Ví dụ mongosh trên database lab trống:

~~~javascript
use java_driver_crud_lab

db.products.insertMany([
  {
    _id: "p-001",
    tenantId: "tenant-a",
    sku: "BOOK-001",
    name: "Sách MongoDB cơ bản",
    category: "books",
    price: 220000,
    stock: 12,
    tags: ["mongodb", "java", "backend"],
    attributes: { language: "vi", edition: 2 },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "p-002",
    tenantId: "tenant-a",
    sku: "BOOK-002",
    name: "Sách Java nâng cao",
    category: "books",
    price: 350000,
    stock: 4,
    tags: ["java", "backend"],
    attributes: { language: "vi", edition: 1 },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: "p-003",
    tenantId: "tenant-a",
    sku: "DEV-001",
    name: "Bàn phím lập trình",
    category: "devices",
    price: 890000,
    stock: 0,
    tags: ["hardware", "accessories"],
    attributes: { color: "black" },
    active: false,
    version: 3,
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: "p-004",
    tenantId: "tenant-b",
    sku: "BOOK-001",
    name: "Tài liệu riêng tenant B",
    category: "books",
    price: 150000,
    stock: 8,
    tags: ["private"],
    attributes: { language: "en" },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-04T09:00:00Z")
  }
]);

db.orders.insertMany([
  {
    _id: "o-001",
    tenantId: "tenant-a",
    status: "PENDING",
    customerId: "c-001",
    items: [
      { sku: "BOOK-001", qty: 2, price: 220000 },
      { sku: "BOOK-002", qty: 1, price: 350000 }
    ],
    total: 790000,
    version: 1,
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: "o-002",
    tenantId: "tenant-a",
    status: "PAID",
    customerId: "c-002",
    items: [
      { sku: "BOOK-001", qty: 1, price: 220000 }
    ],
    total: 220000,
    version: 2,
    createdAt: ISODate("2026-11-06T09:00:00Z")
  }
]);
~~~

### 3.1. Vì sao có tenant-b?

SKU BOOK-001 xuất hiện ở hai tenants. Một CRUD operation chỉ lọc sku có thể vô tình đụng record của tenant khác. Đây là ví dụ hữu ích cho authorization và composite keys.

### 3.2. _id mẫu là String

Trong seed này, _id thuộc kiểu BSON string. Nếu production dùng ObjectId, filter phải dùng ObjectId chứ không phải string có nội dung tương tự.

### 3.3. Kiểu tiền

price được minh họa dưới dạng integer số đồng. Với tiền tệ yêu cầu phần lẻ, cân nhắc Decimal128 hoặc mô hình số nguyên đơn vị nhỏ nhất; không tùy tiện dùng floating-point để tính tiền.

## 4. Bson là giao diện chung

Các builder methods trả về **org.bson.conversions.Bson** hoặc loại triển khai tương thích.

~~~java
Bson filter = Filters.eq("category", "books");
Bson projection = Projections.include("name", "price");
Bson sort = Sorts.descending("createdAt");
Bson update = Updates.inc("stock", 1);
~~~

Driver chuyển các đối tượng này thành BSON command gửi tới MongoDB. Chúng không tự chạy query cho đến khi được truyền cho một API như find hoặc updateOne.

### 4.1. Document và Bson

Document cũng biểu diễn BSON document và có thể dùng ở nhiều nơi nhận Bson:

~~~java
Bson rawFilter = new Document(
    "category", "books"
);
~~~

Tuy nhiên builder thường dễ đọc hơn:

~~~java
Bson builderFilter = Filters.eq(
    "category", "books"
);
~~~

### 4.2. Builders không phải Java Streams

Filters là điều kiện **server-side** chứ không phải lọc một List đã tải vào Java. MongoDB dùng điều kiện để chọn records trên server, có thể tận dụng indexes.

### 4.3. Không ghép JSON string thủ công

Sai về cách thiết kế:

~~~java
String query = "{tenantId:'" + requestTenant +
    "', price:{$gte:" + minPrice + "}}";
~~~

Query strings tự ghép dễ lỗi escaping/kiểu dữ liệu và có nguy cơ chấp nhận điều kiện không hợp lệ. Dùng Filters và allowlist. Tuy nhiên builders không thay thế authorization.

## 5. Filters.eq: so sánh bằng

~~~java
Bson books = Filters.eq("category", "books");

products.find(books).forEach(
    doc -> System.out.println(doc.toJson())
);
~~~

Tương đương ý nghĩa:

~~~javascript
db.products.find({ category: "books" });
~~~

Lấy theo ID:

~~~java
Document product = products.find(
    Filters.eq("_id", "p-001")
).first();

if (product == null) {
    System.out.println("Không tìm thấy");
}
~~~

### 5.1. eq so kiểu BSON

~~~java
Filters.eq("stock", 0);
Filters.eq("active", true);
Filters.eq("tenantId", "tenant-a");
~~~

Không dùng string "0" để truy vấn field lưu integer 0.

### 5.2. So ObjectId

Nếu _id là ObjectId:

~~~java
import org.bson.types.ObjectId;

Bson filter = Filters.eq(
    "_id",
    new ObjectId("507f1f77bcf86cd799439011")
);
~~~

String "507f..." và ObjectId có dạng hiển thị gần nhau nhưng không cùng BSON type.

## 6. Filters.ne và tập giá trị

Khác giá trị:

~~~java
Bson notArchived = Filters.ne(
    "status", "ARCHIVED"
);
~~~

Trạng thái thuộc danh sách cho phép:

~~~java
Bson allowed = Filters.in(
    "status", "PENDING", "PAID"
);
~~~

Loại trừ danh sách:

~~~java
Bson excluded = Filters.nin(
    "status", "CANCELLED", "FAILED"
);
~~~

### 6.1. Ne và nin có thể match missing fields

MongoDB $ne/$nin thường match cả documents **không có field**. Nếu nghiệp vụ chỉ chấp nhận PENDING hoặc PAID, dùng **in(PENDING,PAID)** thay vì chỉ loại CANCELLED.

### 6.2. In khác all

Với tags array:

~~~java
Filters.in(
    "tags", "java", "mongodb"
);
~~~

match khi có ít nhất một giá trị phù hợp.

Còn:

~~~java
Filters.all(
    "tags", List.of("java", "backend")
);
~~~

yêu cầu array chứa các giá trị cần thiết.

### 6.3. Không dùng negation thay validation

Một document thiếu status không tự trở thành hợp lệ chỉ vì nó khác "CANCELLED". Khi dữ liệu cần trạng thái xác định, dùng schema validation/allowlist.

## 7. Filters.gt, gte, lt, lte

Tìm giá từ 200000 tới dưới 500000:

~~~java
Bson range = Filters.and(
    Filters.gte("price", 200000),
    Filters.lt("price", 500000)
);
~~~

| Builder | MongoDB operator | Ý nghĩa |
| --- | --- | --- |
| gt | $gt | Lớn hơn |
| gte | $gte | Lớn hơn hoặc bằng |
| lt | $lt | Nhỏ hơn |
| lte | $lte | Nhỏ hơn hoặc bằng |
| eq | $eq | Bằng |
| ne | $ne | Khác |

### 7.1. Half-open intervals cho ngày

~~~java
import java.time.Instant;
import java.util.Date;

Date from = Date.from(
    Instant.parse("2026-11-01T00:00:00Z")
);
Date until = Date.from(
    Instant.parse("2026-12-01T00:00:00Z")
);

Bson filter = Filters.and(
    Filters.gte("createdAt", from),
    Filters.lt("createdAt", until)
);
~~~

Dùng khoảng [from, until) giúp các khung thời gian liền kề không trùng biên.

### 7.2. BSON Date khác ISO string

Nếu createdAt là BSON Date, đừng truy vấn bằng String rồi mặc định match. Giữ kiểu query phù hợp schema và codec.

## 8. Filters.and, or, nor, not

Tìm sản phẩm tenant-a còn active:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("active", true)
);
~~~

Books hoặc devices:

~~~java
Bson filter = Filters.or(
    Filters.eq("category", "books"),
    Filters.eq("category", "devices")
);
~~~

Kết hợp:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.or(
        Filters.eq("category", "books"),
        Filters.eq("category", "devices")
    )
);
~~~

Các methods khác:

~~~java
Filters.nor(
    Filters.eq("status", "FAILED"),
    Filters.eq("status", "CANCELLED")
);

Filters.not(
    Filters.gt("stock", 10)
);
~~~

### 8.1. Phép logic có semantics rõ

- **and:** mọi điều kiện phải đúng.
- **or:** ít nhất một điều kiện đúng.
- **nor:** không điều kiện nào đúng.
- **not:** phủ định expression tương ứng theo semantics MongoDB.

Với NOT/NOR và missing fields cần kiểm tra kỹ; không mặc định logic hai giá trị truyền thống luôn khớp với absent/null.

### 8.2. Tenant luôn là một điều kiện được kiểm soát

trustedTenantId phải đến từ auth context do backend xác minh, không từ tham số client tùy ý.

## 9. Null và missing fields

Một document có field:

~~~javascript
{ discount: null }
~~~

khác document không có field discount. Nhưng MongoDB equality với null thường match cả hai trường hợp.

~~~java
Filters.eq("discount", null);
~~~

### 9.1. Kiểm tra tồn tại

~~~java
Filters.exists("discount", true);
Filters.exists("discount", false);
~~~

### 9.2. Field hiện diện và bằng null

~~~java
Bson explicitNull = Filters.and(
    Filters.exists("discount", true),
    Filters.eq("discount", null)
);
~~~

### 9.3. Soft delete convention

Nếu ứng dụng quy ước deletedAt **không tồn tại** khi chưa xóa:

~~~java
Bson notDeleted = Filters.exists(
    "deletedAt", false
);
~~~

Nếu ứng dụng lưu deletedAt:null cho record chưa xóa, phải thiết kế filter khác. Không trộn hai conventions vô tình.

## 10. Nested fields và dot notation

Với:

~~~javascript
attributes: {
  language: "vi",
  edition: 2
}
~~~

dùng:

~~~java
Bson filter = Filters.and(
    Filters.eq("attributes.language", "vi"),
    Filters.gte("attributes.edition", 2)
);
~~~

### 10.1. Dot path khác whole-document equality

~~~java
Filters.eq(
    "attributes",
    new Document("language", "vi")
);
~~~

không tương đương tìm field attributes.language bằng "vi" khi attributes còn những fields khác.

### 10.2. BSON path đúng theo schema

Nếu Java POJO có property khác tên BSON stored field, builder path phải dùng đúng mapped field name.

### 10.3. Có thể index nested path

Nếu thường tìm theo attributes.language, cân nhắc index trên path đó, rồi dùng explain/metrics đánh giá.

## 11. Arrays và $elemMatch

Với tags là array strings:

~~~java
Filters.eq("tags", "java");
Filters.size("tags", 3);
Filters.all("tags", List.of("java", "backend"));
~~~

MongoDB có semantics match phần tử array cho nhiều predicates.

Với orders chứa items là array documents:

~~~javascript
items: [
  { sku: "BOOK-001", qty: 2 },
  { sku: "BOOK-002", qty: 1 }
]
~~~

Muốn **cùng một item** vừa có sku BOOK-001 vừa qty >=2:

~~~java
Bson filter = Filters.elemMatch(
    "items",
    Filters.and(
        Filters.eq("sku", "BOOK-001"),
        Filters.gte("qty", 2)
    )
);
~~~

### 11.1. Vì sao không chỉ dùng hai dot paths?

~~~java
Filters.and(
    Filters.eq("items.sku", "BOOK-001"),
    Filters.gte("items.qty", 2)
);
~~~

có thể match bằng **hai phần tử mảng khác nhau**. $elemMatch ràng buộc điều kiện trên một phần tử.

### 11.2. Query nhiều tenants

~~~java
Bson scoped = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.elemMatch(
        "items",
        Filters.eq("sku", "BOOK-001")
    )
);
~~~

### 11.3. Size không có nghĩa pagination

Filters.size("items",2) lọc documents có đúng hai elements, không giới hạn số documents được trả về.

## 12. Regex và text filters

Tìm tên bắt đầu bằng "Sách":

~~~java
import java.util.regex.Pattern;

Bson startsWith = Filters.regex(
    "name",
    Pattern.compile("^Sách")
);
~~~

### 12.1. Regex không thay full-text search

Regex phù hợp một số prefix/format queries. Với search nội dung lớn, cân nhắc text index, Atlas Search hoặc giải pháp khác.

### 12.2. Index và anchor

Một pattern có tiền tố cố định thường có khả năng được index hỗ trợ tốt hơn regex unanchored, nhưng kết quả còn phụ thuộc collation và query planner. Kiểm chứng bằng explain.

### 12.3. Escape user input

Không để user tạo regular expression tùy ý thiếu kiểm soát. Nếu muốn tìm chuỗi literal, cần escape regex metacharacters và giới hạn độ dài.

### 12.4. Filters.text

~~~java
Bson filter = Filters.text(
    "MongoDB Java"
);
~~~

Yêu cầu text index và có semantics khác regex. Không phải vector embedding search.

## 13. Xây filter động bằng danh sách điều kiện

Trong REST API, category/minPrice/maxPrice/active có thể optional; tenant không optional.

~~~java
import java.util.ArrayList;
import java.util.List;

public static Bson productFilters(
    String trustedTenantId,
    String category,
    Integer minPrice,
    Integer maxPrice,
    Boolean active
) {
    List<Bson> conditions = new ArrayList<>();

    conditions.add(
        Filters.eq("tenantId", trustedTenantId)
    );
    conditions.add(
        Filters.exists("deletedAt", false)
    );

    if (category != null && !category.isBlank()) {
        conditions.add(
            Filters.eq("category", category)
        );
    }

    if (minPrice != null) {
        conditions.add(
            Filters.gte("price", minPrice)
        );
    }

    if (maxPrice != null) {
        conditions.add(
            Filters.lte("price", maxPrice)
        );
    }

    if (active != null) {
        conditions.add(
            Filters.eq("active", active)
        );
    }

    return Filters.and(conditions);
}
~~~

### 13.1. Validation trước khi build

Kiểm tra minPrice <= maxPrice, các giá trị nằm trong range được phép, category trong allowlist khi cần.

### 13.2. Không nhận raw operator từ client

Một API search tùy biến nên mapping từ các filter names công khai sang BSON paths được phép, thay vì nhận arbitrary JSON/BSON.

### 13.3. Không trả filter rỗng khi auth thất bại

Nếu chưa xác thực được tenant, trả lỗi authorization chứ không tạo unscoped query.

## 14. find và FindIterable

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("active", true)
);

products.find(filter).forEach(
    doc -> System.out.println(
        doc.getString("name")
    )
);
~~~

### 14.1. find().first()

~~~java
Document product = products.find(
    Filters.eq("_id", "p-001")
).first();
~~~

first() trả **null** khi không match.

### 14.2. for-each

~~~java
for (Document product : products.find(filter)) {
    System.out.println(product.toJson());
}
~~~

### 14.3. Query chạy ở server

Driver không tự tải toàn collection về rồi mới filter bằng Java streams.

### 14.4. Dữ liệu lớn

Không thu toàn bộ hàng triệu documents vào List không giới hạn; dùng cursor, pagination hoặc batch processing.

## 15. Projections.include và exclude

Chỉ lấy name, sku, price:

~~~java
Bson projection = Projections.include(
    "name",
    "sku",
    "price"
);

products.find(
    Filters.eq("tenantId", "tenant-a")
).projection(projection)
 .forEach(doc -> System.out.println(doc.toJson()));
~~~

### 15.1. _id được trả theo mặc định

Muốn loại _id:

~~~java
Bson projection = Projections.fields(
    Projections.include(
        "name", "sku", "price"
    ),
    Projections.excludeId()
);
~~~

### 15.2. Exclude

~~~java
Bson projection = Projections.exclude(
    "secretKey",
    "internalNotes"
);
~~~

### 15.3. Không trộn include/exclude tùy ý

Theo projection semantics, không trộn include và exclude đối với các fields khác nhau một cách tùy tiện; ngoại lệ thường là _id. Chọn một chiến lược rõ ràng.

### 15.4. Projection và authorization

Projection giảm payload và giúp tránh gửi fields ngoài ý muốn, nhưng không tự thay access control. Với public API, prefer allowlist DTO/projection và kiểm tra quyền theo record/field.

## 16. Projections.fields, nested fields và array

Một projection phối hợp:

~~~java
Bson projection = Projections.fields(
    Projections.include(
        "sku",
        "name",
        "attributes.language"
    ),
    Projections.excludeId()
);
~~~

### 16.1. Nested projection không tự flatten

Field attributes.language có thể vẫn nằm trong subdocument attributes của result, không tự trở thành root field language. DTO mapper quyết định API shape.

### 16.2. Slice array

~~~java
Projections.slice("items", 2);
~~~

Giới hạn phần tử trả về trong **items của mỗi document**, không giới hạn số documents.

### 16.3. elemMatch projection

~~~java
Projections.elemMatch(
    "items",
    Filters.eq("sku", "BOOK-001")
);
~~~

Thể hiện phép chọn phần tử array theo $elemMatch projection semantics. Nếu muốn nhiều items/transforms phức tạp, xem aggregation pipeline.

### 16.4. Text score

Với query có text index phù hợp:

~~~java
Projections.metaTextScore("textScore");
~~~

Text score không phải xác suất đúng và không áp dụng cho mọi query.

## 17. Computed projection

Nếu server/driver version hỗ trợ expression projection:

~~~java
Bson projection = Projections.computed(
    "inventoryValue",
    new Document(
        "$multiply",
        List.of("$price", "$stock")
    )
);
~~~

### 17.1. Computed field không phải dữ liệu đã lưu

Trong projection, expression tạo giá trị trả về. Không tự cập nhật inventoryValue trong document.

### 17.2. Khi nào dùng aggregation?

Với $group, $lookup hoặc nhiều bước transformation, aggregation pipeline rõ hơn.

### 17.3. Type/overflow

Nếu price/stock có numeric types khác nhau, kết quả phép nhân có thể chịu numeric promotion và giới hạn. Cần dùng loại tiền tệ phù hợp.

## 18. Sorts.ascending và descending

Giá tăng dần:

~~~java
Bson sort = Sorts.ascending("price");
~~~

CreatedAt mới nhất trước:

~~~java
Bson sort = Sorts.descending("createdAt");
~~~

Dùng:

~~~java
products.find(
    Filters.eq("tenantId", "tenant-a")
).sort(Sorts.ascending("price"))
 .forEach(System.out::println);
~~~

### 18.1. Sort không cập nhật dữ liệu

Sorts mô tả thứ tự kết quả query, không thay vị trí documents lưu trong MongoDB.

### 18.2. Không có sort thì không có thứ tự nghiệp vụ được bảo đảm

Đừng dựa vào natural order trong API.

### 18.3. Mixed BSON types

Nếu price có cả string và number, thứ tự có thể khó hiểu. Chuẩn hóa schema.

## 19. Sorts.orderBy và tie-breaker

~~~java
Bson sort = Sorts.orderBy(
    Sorts.ascending("category"),
    Sorts.descending("price"),
    Sorts.ascending("_id")
);
~~~

### 19.1. Sort ổn định

Khi nhiều documents có cùng createdAt, dùng _id làm tie-breaker:

~~~java
Bson stableSort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

### 19.2. Sort một timestamp không unique

Không bảo đảm hai pages sẽ nối nhau chính xác khi có nhiều records trùng thời điểm.

### 19.3. Concurrent changes

Tie-breaker ổn định trong một trạng thái dữ liệu, nhưng các updates/inserts giữa hai requests vẫn có thể làm pagination thay đổi.

## 20. Kết hợp Filters, Projections, Sorts và limit

Một query đọc thực tế:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.gte("price", 200000)
);

Bson projection = Projections.fields(
    Projections.include(
        "sku", "name", "price", "stock"
    ),
    Projections.excludeId()
);

Bson sort = Sorts.orderBy(
    Sorts.ascending("price"),
    Sorts.ascending("sku")
);

products.find(filter)
    .projection(projection)
    .sort(sort)
    .limit(20)
    .forEach(doc -> {
        System.out.println(doc.toJson());
    });
~~~

### 20.1. Query semantics vs thứ tự method calls

MongoDB thực hiện filter/projection/sort/limit theo semantics của lệnh find. Driver không nhất thiết lọc/sort ở client.

### 20.2. Index hỗ trợ query

Với tenantId, active và price range, cần đánh giá compound index theo workload. Builders không tự tạo indexes.

### 20.3. API response

Không trả toàn bộ Document.toJson() ra Internet trong production; map sang DTO và limit fields đúng policy.

## 21. Offset pagination: skip/limit

Ví dụ trang 3, mỗi trang 10:

~~~java
int page = 3;
int pageSize = 10;
int offset = (page - 1) * pageSize;

Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);

products.find(
    Filters.eq("tenantId", trustedTenantId)
).sort(sort)
 .skip(offset)
 .limit(pageSize)
 .forEach(System.out::println);
~~~

### 21.1. Validate page/pageSize

page >=1, pageSize có maximum, tránh overflow khi tính offset và các requests đòi skip cực lớn.

### 21.2. Skip lớn tốn chi phí

MongoDB có thể phải duyệt nhiều records mới tới offset, khiến pagination sâu chậm.

### 21.3. Concurrent inserts/deletes

Offset-based pages có thể bị lặp hoặc bỏ sót records khi dữ liệu thay đổi. Keyset pagination thường phù hợp hơn với danh sách lớn.

## 22. Keyset pagination với Filters và Sorts

Sort createdAt desc rồi _id desc:

~~~java
Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

Cho cursor gồm lastCreatedAt và lastId:

~~~java
Bson after = Filters.or(
    Filters.lt("createdAt", lastCreatedAt),
    Filters.and(
        Filters.eq("createdAt", lastCreatedAt),
        Filters.lt("_id", lastId)
    )
);

Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    after
);

products.find(filter)
    .sort(sort)
    .limit(20)
    .forEach(System.out::println);
~~~

### 22.1. Vì sao lt?

Với descending order, records sau cursor có thời điểm nhỏ hơn hoặc cùng thời điểm với _id nhỏ hơn.

### 22.2. Cursor phải gắn với query

Đừng dùng cursor sinh từ filter tenant-a cho một truy vấn tenant-b hoặc đổi sort mà không reset cursor.

### 22.3. Kiểu _id phải khớp

Nếu stored _id là ObjectId, lastId phải được decode thành ObjectId đúng. Lab dùng String.

### 22.4. Keyset không tạo snapshot bất biến

Nếu sort keys bị sửa giữa requests, tập kết quả vẫn có thể thay đổi. Nếu cần snapshot consistency, dùng cơ chế đọc phù hợp yêu cầu.

## 23. Đếm và distinct

Đếm theo filter:

~~~java
long count = products.countDocuments(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", true)
    )
);
~~~

Distinct category trong tenant:

~~~java
products.distinct(
    "category",
    Filters.eq("tenantId", trustedTenantId),
    String.class
).forEach(System.out::println);
~~~

### 23.1. countDocuments khác estimatedDocumentCount

estimatedDocumentCount lấy ước lượng dựa trên metadata collection trong điều kiện thích hợp, không thay thế countDocuments(filter) khi cần exact tenant-scoped count.

### 23.2. Distinct type

Đảm bảo dữ liệu field có kiểu phù hợp kiểu Java được khai báo cho kết quả.

### 23.3. Exact count có thể tốn chi phí

Với collections lớn, đo performance và cân nhắc UX/counters nếu không cần exact totals mỗi request.

## 24. CREATE bằng insertOne

~~~java
Document product = new Document("_id", "p-005")
    .append("tenantId", trustedTenantId)
    .append("sku", "BOOK-005")
    .append("name", "Học MongoDB với Java")
    .append("category", "books")
    .append("price", 280000)
    .append("stock", 5)
    .append("active", true)
    .append("version", 1)
    .append("createdAt", new Date());

products.insertOne(product);
~~~

### 24.1. insertMany

~~~java
List<Document> batch = List.of(
    new Document("_id", "p-101")
        .append("tenantId", trustedTenantId)
        .append("name", "A"),
    new Document("_id", "p-102")
        .append("tenantId", trustedTenantId)
        .append("name", "B")
);

products.insertMany(batch);
~~~

### 24.2. Duplicate key

MongoDB có unique index trên _id. Một duplicate _id sẽ gây duplicate key error. Nếu SKU unique theo tenant, cần compound unique index.

### 24.3. Không copy toàn bộ client JSON sang database

Validate required fields, ownership, numeric ranges và ngăn client tự set các fields như tenantId, createdBy, paidAt nếu không được phép.

## 25. Updates.set, unset, rename

Đổi name:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId)
);

products.updateOne(
    filter,
    Updates.set("name", "Sách MongoDB thực hành")
);
~~~

Gỡ field không dùng:

~~~java
Updates.unset("deprecatedField");
~~~

Đổi tên field:

~~~java
Updates.rename(
    "oldFieldName",
    "newFieldName"
);
~~~

### 25.1. set với nested field

~~~java
Updates.set("attributes.language", "en");
~~~

chỉ hướng tới một field con theo dot notation.

### 25.2. Đừng set toàn bộ subdocument nếu chỉ đổi một trường

~~~java
Updates.set(
    "attributes",
    new Document("language", "en")
);
~~~

có thể thay hết attributes và làm mất các fields như edition.

### 25.3. unset khác set null

unset xóa field, còn set null giữ field có giá trị null; query semantics với exists/null sẽ khác nhau.

## 26. Updates.combine nhiều toán tử

~~~java
Bson update = Updates.combine(
    Updates.set("name", "Sách MongoDB mới"),
    Updates.set("active", true),
    Updates.currentDate("updatedAt"),
    Updates.inc("version", 1)
);

products.updateOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    update
);
~~~

### 26.1. Atomicity một document

Một updateOne áp dụng các operators lên cùng document có tính nguyên tử ở cấp document.

### 26.2. Không cập nhật cùng field bằng operators mâu thuẫn

Ví dụ cùng lúc set và inc version có thể tạo conflict. Thiết kế một phép biến đổi nhất quán.

### 26.3. Không chia thành hai calls thiếu lý do

Nếu một thay đổi name và version phải đi cùng nhau, Updates.combine trong một updateOne tránh trạng thái trung gian.

## 27. Updates.inc chống lost update

Sai trong concurrency:

~~~text
Thread A reads stock=10
Thread B reads stock=10
Thread A sets stock=11
Thread B sets stock=11
Expected 12 but actual 11
~~~

Server-side increment:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.inc("stock", 1)
);
~~~

### 27.1. Hai increments được áp dụng tuần tự an toàn ở cấp document

MongoDB thực hiện increment khi write chạy trên server, không phụ thuộc tính toán từ snapshot cũ của client.

### 27.2. inc negative

~~~java
Updates.inc("stock", -1);
~~~

Không đủ an toàn nếu stock không được âm; cần conditional filter stock>=1.

### 27.3. Null và numeric type

$inc yêu cầu trường có kiểu số phù hợp. Field có giá trị null có thể gây lỗi; schema validation giúp tránh nhập sai kiểu.

### 27.4. $inc không idempotent ở cấp workflow

Nếu API làm lại cùng business request hai lần, stock có thể thay đổi hai lần. Dùng operation IDs/idempotency khi retry workflow.

## 28. Trừ stock an toàn bằng conditional update

~~~java
import com.mongodb.client.result.UpdateResult;

int quantity = 3;

Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.gte("stock", quantity)
);

Bson update = Updates.combine(
    Updates.inc("stock", -quantity),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Không đủ tồn kho hoặc sản phẩm không hợp lệ"
    );
}
~~~

### 28.1. Filter và update là một thao tác

Điều kiện stock>=quantity được xét cùng atomic write. Hai người mua không thể cùng trừ quá số lượng nếu filter giữ đúng invariant.

### 28.2. matchedCount=0 có thể nhiều lý do

Không tồn tại sản phẩm, tenant không match, active=false hoặc stock thiếu. Không tiết lộ tình trạng sản phẩm của tenant khác qua error response.

### 28.3. Nhiều sản phẩm cần transaction/workflow khác

Một updateOne không bảo đảm giảm tồn kho của nhiều products và tạo order atomically. Nếu yêu cầu all-or-nothing, cân nhắc multi-document transaction trên topology hỗ trợ.

## 29. Updates.min, max, mul và currentDate

~~~java
Updates.min("lowestPrice", 190000);
Updates.max("highestPrice", 900000);
Updates.mul("stock", 2);
Updates.currentDate("updatedAt");
~~~

### 29.1. min/max

$min và $max thay field khi giá trị đưa vào nhỏ/lớn hơn giá trị hiện tại theo BSON comparison semantics.

### 29.2. mul

$mul là phép nhân số; cần kiểm soát numeric type và quy tắc giá trị missing/null theo phiên bản.

### 29.3. currentDate

Cho phép MongoDB set timestamp theo server-side semantics, hữu ích khi client clocks không đồng bộ.

### 29.4. Không chọn operator theo tên mà bỏ invariants

Ví dụ mul(stock,2) không có nghĩa nghiệp vụ nhập kho hai lần hợp lệ. Luôn xác định phép thay đổi cần thiết trước.

## 30. Arrays: push, addToSet, pull

Thêm tag, cho phép duplicates:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.push("tags", "database")
);
~~~

Thêm nếu chưa có phần tử tương đương:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.addToSet("tags", "database")
);
~~~

Xóa phần tử theo giá trị:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.pull("tags", "legacy")
);
~~~

### 30.1. addToSet không xóa duplicates có sẵn

Nếu trước đó array đã có hai strings "java", addToSet("java") không làm sạch chúng. Nó chỉ ngăn thêm phần tử mới trùng theo semantics.

### 30.2. addToSet không tạo unique index toàn collection

Muốn một SKU unique giữa documents, phải dùng unique index chứ không dùng array operator.

### 30.3. Array size và document growth

Array lớn liên tục có thể làm document tăng kích thước, tăng contention và chạm BSON size limit. Khi quan hệ one-to-many phát triển không giới hạn, cân nhắc tách collection.

## 31. Array filters và positional updates

Với order:

~~~javascript
{
  _id: "o-001",
  tenantId: "tenant-a",
  items: [
    { sku: "BOOK-001", qty: 2 },
    { sku: "BOOK-002", qty: 1 }
  ]
}
~~~

Muốn cập nhật qty của item có sku BOOK-002:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "o-001"),
    Filters.eq("tenantId", trustedTenantId)
);

Bson update = Updates.set(
    "items.$[item].qty", 5
);

UpdateOptions options = new UpdateOptions()
    .arrayFilters(
        List.of(
            new Document("item.sku", "BOOK-002")
        )
    );

orders.updateOne(filter, update, options);
~~~

### 31.1. item identifier phải khớp

Trong path items.$[item].qty, identifier item phải được khai báo trong arrayFilters. Sai tên/thiếu filter có thể gây lỗi.

### 31.2. Có thể match nhiều phần tử

Nếu items có hai phần tử cùng SKU, arrayFilters có thể cập nhật cả hai. Nếu nghiệp vụ muốn đúng một, cần định danh phần tử riêng hoặc invariant uniqueness.

### 31.3. Positional $

~~~java
orders.updateOne(
    Filters.and(
        Filters.eq("_id", "o-001"),
        Filters.eq("items.sku", "BOOK-001")
    ),
    Updates.inc("items.$.qty", 1)
);
~~~

Positional $ phụ thuộc điều kiện match array tương ứng để chọn phần tử.

### 31.4. All positional $[]

~~~java
orders.updateOne(
    Filters.eq("_id", "o-001"),
    Updates.set("items.$[].selected", false)
);
~~~

Thay mọi phần tử items. Chỉ dùng khi đúng yêu cầu.

## 32. updateOne và updateMany

Một document:

~~~java
UpdateResult result = products.updateOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    Updates.set("active", false)
);
~~~

Nhiều documents:

~~~java
UpdateResult result = products.updateMany(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("category", "books")
    ),
    Updates.set("featured", true)
);
~~~

### 32.1. updateMany không tự là multi-document transaction

Mỗi document write có atomicity ở cấp document, nhưng toàn bộ updateMany không mặc định commit/rollback all-or-nothing.

### 32.2. Không thiếu tenant trong updateMany

Thiếu tenantId có thể thay đổi dữ liệu của nhiều khách hàng. Dùng guardrail ở repository/API và review kỹ khi bulk update.

### 32.3. Bulk preview

Trước một thao tác lớn, xem count/sample các records match filter và đặt change approval/backup policy phù hợp.

## 33. UpdateResult: matched và modified

~~~java
UpdateResult result = products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.set("active", true)
);

System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getUpsertedId());
~~~

### 33.1. matchedCount

Số documents match filter. Với updateOne tối đa một.

### 33.2. modifiedCount

Số documents thực sự thay đổi. Nếu active đã true, set true có thể match=1 nhưng modified=0.

### 33.3. modified=0 không phải not found

Muốn phân biệt, đọc matchedCount.

### 33.4. Acknowledgment

Khi dùng unacknowledged writes, khả năng truy cập result counts có thể bị hạn chế. Chọn write concern theo durability/SLO.

## 34. Upsert với UpdateOptions

Nếu match thì update, nếu không match có thể insert:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("sku", "BOOK-010")
);

Bson update = Updates.combine(
    Updates.set("name", "Sách ứng dụng MongoDB"),
    Updates.set("price", 310000),
    Updates.setOnInsert(
        "createdAt", new Date()
    ),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter,
    update,
    new UpdateOptions().upsert(true)
);
~~~

### 34.1. setOnInsert

Chỉ đặt createdAt khi operation tạo document mới, không thay createdAt của record cũ.

### 34.2. Filter phải là business identity ổn định

Không upsert bằng một filter quá rộng như category="books" hoặc thiếu tenant. Có thể cập nhật nhầm document hoặc tạo record thiếu identity.

### 34.3. Unique compound index

Nếu SKU unique trong tenant:

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

Một unique index giúp ngăn race duplicates; ứng dụng vẫn cần xử lý duplicate key errors nếu nhiều writers upsert đồng thời.

### 34.4. Idempotency

Một upsert dựa identity ổn định thường dễ retry hơn insert với ID random tạo mới mỗi lần, nhưng thao tác Updates.inc hoặc external side effects vẫn có thể cần business operation ID.

## 35. ReplaceOne khác Updates.set

~~~java
Document replacement = new Document(
    "_id", "p-001"
).append("tenantId", trustedTenantId)
 .append("sku", "BOOK-001")
 .append("name", "Tên mới")
 .append("price", 250000)
 .append("stock", 10);

products.replaceOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    replacement
);
~~~

### 35.1. Replace xóa fields không còn trong replacement

Nếu original có tags, attributes, version, createdAt mà replacement không có, các fields đó có thể biến mất.

### 35.2. Chỉ thay một field? Dùng set

Updates.set("name", ...) thường phù hợp hơn replaceOne nếu update một vài fields.

### 35.3. _id immutable

Không thể thay _id của document bằng một giá trị khác thông qua replaceOne/update.

### 35.4. ReplaceOptions

Có thể dùng upsert với replacement theo API, nhưng cần phân biệt replacement semantics với các update operators.

## 36. findOneAndUpdate: cập nhật và trả document

~~~java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.gte("stock", 1)
);

FindOneAndUpdateOptions options =
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
        .projection(
            Projections.include("sku", "stock")
        );

Document after = products.findOneAndUpdate(
    filter,
    Updates.inc("stock", -1),
    options
);
~~~

### 36.1. ReturnDocument.AFTER

Trả trạng thái document sau update. Tùy options, có thể chọn BEFORE.

### 36.2. Không match thì trả null

Xử lý null khi sản phẩm không còn stock hoặc không thuộc tenant.

### 36.3. Giới hạn projection

Projection giúp không trả các fields nội bộ khi API chỉ cần số stock sau reservation.

### 36.4. Khi nào dùng?

Khi cần atomic update + đọc lại giá trị tương ứng mà không thực hiện hai operations riêng.

## 37. Optimistic locking bằng version

Document:

~~~javascript
{
  _id: "p-001",
  tenantId: "tenant-a",
  version: 5,
  name: "Tên cũ"
}
~~~

Khi client đã đọc version 5:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("version", 5)
);

Bson update = Updates.combine(
    Updates.set("name", "Tên mới"),
    Updates.inc("version", 1),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Version conflict hoặc document không tồn tại"
    );
}
~~~

### 37.1. Compare-and-set

Nếu writer khác đã tăng version từ 5 lên 6, update dựa version 5 không match. Ứng dụng có thể trả HTTP 409, reload hoặc merge.

### 37.2. Tránh lost update

Đọc name cũ rồi set mà không kiểm tra version có thể ghi đè thay đổi của người khác.

### 37.3. Không retry conflict vô hạn

Với user edits, thường nên cho người dùng biết dữ liệu đã thay đổi. Với counters, dùng server-side $inc khi phù hợp.

## 38. State transition có điều kiện

Order chỉ được chuyển PENDING sang PAID:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "o-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("status", "PENDING")
);

Bson update = Updates.combine(
    Updates.set("status", "PAID"),
    Updates.inc("version", 1),
    Updates.currentDate("updatedAt")
);

UpdateResult result = orders.updateOne(
    filter, update
);

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Order không còn ở trạng thái PENDING"
    );
}
~~~

### 38.1. Race giữa PAID và CANCELLED

Nếu hai workflows đọc PENDING rồi set trực tiếp, last writer có thể ghi đè. Filter status=PENDING khiến chỉ transition đầu tiên thỏa.

### 38.2. Business-level side effects

Cập nhật state trong MongoDB không tự charge payment hoặc gửi email nguyên tử. Cần idempotency/outbox và reconciliation với hệ thống ngoài.

## 39. DELETE: deleteOne và deleteMany

~~~java
import com.mongodb.client.result.DeleteResult;

DeleteResult result = products.deleteOne(
    Filters.and(
        Filters.eq("_id", "p-003"),
        Filters.eq("tenantId", trustedTenantId)
    )
);

System.out.println(result.getDeletedCount());
~~~

Xóa nhiều records theo điều kiện:

~~~java
DeleteResult result = products.deleteMany(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", false)
    )
);
~~~

### 39.1. Empty filter nguy hiểm

~~~java
products.deleteMany(new Document());
~~~

có thể xóa toàn collection. Không tạo delete filter trống nếu request không có điều kiện.

### 39.2. Hard delete và retention

Xóa vật lý có thể không đáp ứng yêu cầu audit/legal hold. Tùy hệ thống dùng soft delete hoặc archive.

### 39.3. deleteMany không all-or-nothing

Mỗi document được xóa theo semantics tương ứng; không tự là một transaction nhiều documents.

## 40. Soft delete bằng Updates

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-003"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.exists("deletedAt", false)
);

Bson update = Updates.combine(
    Updates.currentDate("deletedAt"),
    Updates.set("active", false)
);

products.updateOne(filter, update);
~~~

### 40.1. Filter đọc mặc định

~~~java
Bson activeScope = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.exists("deletedAt", false)
);
~~~

### 40.2. Duy trì một convention

Nếu deletedAt=null cho record active, không áp máy móc exists(false). Có thể dùng status + timestamp nhưng cần giữ chúng nhất quán.

### 40.3. Unique index với soft delete

Một record đã soft delete vẫn tồn tại trong unique index bình thường. Nếu muốn reuse SKU chỉ sau khi delete, cân nhắc partial unique index và business policy.

### 40.4. Compliance

Soft delete không xóa bytes thật; dữ liệu vẫn tồn tại trong database/backups đến khi purge theo chính sách.

## 41. Repository pattern bảo vệ tenant

~~~java
public final class ProductRepository {
    private final MongoCollection<Document> products;

    public ProductRepository(
        MongoCollection<Document> products
    ) {
        this.products = products;
    }

    public Document findVisibleById(
        String trustedTenantId,
        String productId
    ) {
        Bson filter = Filters.and(
            Filters.eq(
                "tenantId", trustedTenantId
            ),
            Filters.eq("_id", productId),
            Filters.exists("deletedAt", false)
        );

        Bson projection = Projections.include(
            "sku", "name", "price", "stock"
        );

        return products.find(filter)
            .projection(projection)
            .first();
    }
}
~~~

### 41.1. Trusted tenant

Tenant ID do auth middleware/service xác minh; không lấy trực tiếp từ arbitrary client request.

### 41.2. Apply scope cho cả write/delete

Một repository có thể bảo vệ find nhưng quên updateOne/deleteOne. Cần nhất quán.

### 41.3. API field allowlist

Không trả Document.toJson() chứa internal metadata/secret fields. Use DTOs và projections.

### 41.4. API methods theo nghiệp vụ

Ưu tiên findVisibleById, reserveStock, transitionOrder, softDelete thay vì một endpoint cho phép client truyền arbitrary MongoDB operators.

## 42. Indexes cho filter và sort

Một query phổ biến:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true)
);

Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

Index có thể cân nhắc:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  active: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 42.1. Equality, Sort, Range

Một nguyên tắc thiết kế compound index thường xét equality predicates, sort keys và range, nhưng thứ tự tốt nhất phụ thuộc workload thực tế.

### 42.2. Unique constraints

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

Cho phép SKU trùng giữa tenants nhưng không trùng trong một tenant.

### 42.3. Index có chi phí

Mỗi index tiêu tốn storage và write maintenance. Không tạo index cho mọi field.

## 43. Explain query trong Java

~~~java
import com.mongodb.ExplainVerbosity;

Document plan = products.find(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", true)
    )
).sort(
    Sorts.descending("createdAt")
).explain(
    ExplainVerbosity.EXECUTION_STATS
);

System.out.println(plan.toJson());
~~~

Quan sát:

- Winning plan.
- IXSCAN/COLLSCAN.
- Blocking SORT.
- totalKeysExamined/totalDocsExamined.
- nReturned.
- executionTimeMillis.

### 43.1. Index usage không thay security

Một query dùng index đúng vẫn có thể thiếu tenant check và làm lộ dữ liệu.

### 43.2. Explain không phải latency end-to-end

Cần đo cả application/driver/network và server load.

### 43.3. Dataset quá nhỏ

Với bốn sản phẩm, COLLSCAN có thể hoàn toàn hợp lý. Benchmark trên tập dữ liệu representative.

## 44. Cursor và memory

~~~java
import com.mongodb.client.MongoCursor;

Bson filter = Filters.eq(
    "tenantId", trustedTenantId
);

try (MongoCursor<Document> cursor =
         products.find(filter).iterator()) {

    while (cursor.hasNext()) {
        Document doc = cursor.next();
        System.out.println(
            doc.getString("name")
        );
    }
}
~~~

### 44.1. Đóng cursor

try-with-resources bảo đảm cursor được close khi kết thúc hoặc có exception.

### 44.2. Không tải cả collection vào List

Một triệu documents có thể làm ứng dụng tràn heap. Sử dụng cursor/limit/batch processing.

### 44.3. Timeout và cancellation

Điều chỉnh timeout theo SLO, xử lý server selection/network failures và dừng stream khi HTTP client cancel.

### 44.4. MongoClient được chia sẻ

Tạo/đóng client mỗi request gây overhead và không tận dụng tốt connection pool.

## 45. POJO codecs thay cho Document

Có thể định nghĩa:

~~~java
public class Product {
    private String id;
    private String tenantId;
    private String sku;
    private String name;
    private long price;
    private int stock;

    public Product() {}

    // Getters/setters/annotations theo POJO codec.
}
~~~

Khi cấu hình codec registry phù hợp:

~~~java
MongoCollection<Product> products =
    db.getCollection("products", Product.class);
~~~

### 45.1. Builders vẫn dùng BSON field names

~~~java
products.find(
    Filters.eq("tenantId", trustedTenantId)
);
~~~

Nếu Java property mapping khác BSON field name, phải dùng path thực tương ứng.

### 45.2. POJO không thay validation ở database

Services khác, shell hoặc legacy data vẫn có thể ghi sai kiểu. Có thể dùng MongoDB JSON Schema validation.

### 45.3. Decimal128 và Date types

Đảm bảo codec/mapping cho money/time fields thống nhất giữa service và BSON.

## 46. BulkWrite và transaction boundaries

~~~java
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.BulkWriteOptions;

List<WriteModel<Document>> writes = List.of(
    new UpdateOneModel<>(
        Filters.eq("_id", "p-001"),
        Updates.inc("stock", 1)
    ),
    new UpdateOneModel<>(
        Filters.eq("_id", "p-002"),
        Updates.inc("stock", 1)
    )
);

products.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(true)
);
~~~

### 46.1. Bulk không đồng nghĩa atomic nhiều documents

BulkWrite gom operations nhưng không mặc định all-or-nothing. Cần transaction nếu business invariant yêu cầu.

### 46.2. Ordered/unordered

Cấu hình ảnh hưởng thứ tự thực thi và xử lý lỗi. Không chọn unordered khi thứ tự phụ thuộc.

### 46.3. External side effects

MongoDB transaction không tự include payment API, email hoặc object storage. Sử dụng outbox/idempotency/saga pattern khi cần.

## 47. Error handling và retries

| Lỗi | Khả năng nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| Duplicate key | Unique index conflict | Conflict/retry có điều kiện |
| Server selection timeout | Network/election/URI | SDAM logs, backoff |
| Write concern error | Acknowledgement không đạt | Kiểm tra trạng thái commit |
| Validation error | Field/type sai | Sửa input/schema |
| Unauthorized | Role/credentials/TLS | Điều chỉnh quyền đúng |
| No match | Not found/tenant/state conflict | Kết quả nghiệp vụ rõ |
| Timeout sau write | Outcome có thể chưa rõ | Idempotency, không retry mù |
| Cursor error | Network/long query | Timeout, index, resource cleanup |

### 47.1. Duplicate key 11000

MongoDB duplicate key error thường có mã 11000. Dùng exception types/codes của driver để map lỗi, không parse chuỗi tự do.

### 47.2. Retryable writes

Driver hỗ trợ retry một số writes trong điều kiện topology/semantics nhất định. Nhưng retry ở cấp API workflow có thể nhân đôi business side effects nếu không có operationId.

### 47.3. Idempotency của $inc

Một request tăng stock hai lần do HTTP retry có thể tăng hai lần. Cần record business operation hoặc idempotency key khi thao tác phải exactly-once theo nghiệp vụ.

### 47.4. Logging

Log trace ID, tenant-safe identifiers, operation category, latency và error class. Tránh log credentials/PII hoặc toàn bộ documents.

## 48. Ví dụ Java kết hợp đầy đủ

Đây là chương trình lab nhỏ dùng Filters, Projections, Sorts, Updates, readback và update result. Đặt vào project đã cấu hình dependency mongodb-driver-sync và MONGODB_URI.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;

import com.mongodb.client.result.UpdateResult;

import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

public class CrudBuildersDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase(
                "java_driver_crud_lab"
            );

            MongoCollection<Document> products =
                db.getCollection("products");

            String id = "demo-p-001";
            String tenant = "tenant-a";

            Bson identity = Filters.and(
                Filters.eq("_id", id),
                Filters.eq("tenantId", tenant)
            );

            Bson upsertUpdate = Updates.combine(
                Updates.set("name", "Demo Builders"),
                Updates.set("sku", "DEMO-001"),
                Updates.set("category", "demo"),
                Updates.set("price", 100),
                Updates.setOnInsert("stock", 10),
                Updates.setOnInsert(
                    "createdAt", new Date()
                )
            );

            products.updateOne(
                identity,
                upsertUpdate,
                new UpdateOptions().upsert(true)
            );

            Bson filter = Filters.and(
                Filters.eq("tenantId", tenant),
                Filters.eq("category", "demo"),
                Filters.gte("price", 50)
            );

            Bson projection = Projections.fields(
                Projections.include(
                    "sku", "name", "price", "stock"
                ),
                Projections.excludeId()
            );

            Bson sort = Sorts.orderBy(
                Sorts.ascending("price"),
                Sorts.ascending("sku")
            );

            products.find(filter)
                .projection(projection)
                .sort(sort)
                .limit(10)
                .forEach(doc ->
                    System.out.println(
                        "READ: " + doc.toJson()
                    )
                );

            UpdateResult result = products.updateOne(
                identity,
                Updates.combine(
                    Updates.inc("stock", 2),
                    Updates.currentDate("updatedAt")
                )
            );

            System.out.println(
                "matched=" + result.getMatchedCount()
                + ", modified=" + result.getModifiedCount()
            );

            Document after = products.find(
                identity
            ).first();

            if (after == null) {
                throw new IllegalStateException(
                    "Demo record not found"
                );
            }

            System.out.println(
                "AFTER: " + after.toJson()
            );

            // Cleanup optional in lab:
            // products.deleteOne(identity);
        }
    }
}
~~~

### 48.1. Demo có thể chạy lại

Upsert theo stable _id tạo record nếu thiếu. setOnInsert(stock,10) không reset stock khi đã tồn tại; mỗi lần chương trình chạy vẫn dùng $inc +2, minh họa sự khác nhau giữa repeatable upsert và increment theo workflow.

### 48.2. Không tự xóa record

Dòng delete để comment vì cleanup là thao tác ghi có rủi ro. Chỉ bật khi đang ở môi trường lab được phép.

### 48.3. Giới hạn của demo

Chưa có authentication middleware, DTO mapping, logging, metrics, retries, unique business index và integration tests đầy đủ.

## 49. Kế hoạch kiểm thử CRUD builders

Tối thiểu nên kiểm tra:

1. Equality match đúng fields.
2. Range boundaries inclusive/exclusive.
3. AND/OR logic.
4. Missing/null behavior.
5. Nested dot path.
6. $elemMatch với cùng array element.
7. Tenant isolation với SKU trùng ở nhiều tenants.
8. Projection include/exclude và _id.
9. Sort có tie-breaker.
10. Offset và keyset pagination.
11. Atomic $inc dưới concurrent requests.
12. Conditional decrement không làm stock âm.
13. matchedCount và modifiedCount.
14. Upsert insert vs update.
15. Unique index dưới concurrent upsert.
16. Version optimistic locking.
17. State transition PENDING→PAID.
18. ArrayFilters target đúng phần tử.
19. Soft delete không bị query public trả về.
20. DeleteMany không vượt tenant scope.
21. Cursor resource cleanup.
22. Explain/index behavior với dữ liệu representative.

### 49.1. Test bằng môi trường độc lập

Không chạy insert/update/delete test trên production. Dùng database lab, test container hoặc môi trường staging có dữ liệu thử.

### 49.2. Test concurrency thật

Nếu mục tiêu chống lost update, chạy concurrent operations và assert final stock/version; test tuần tự không đủ chứng minh race safety.

### 49.3. Test dữ liệu sai schema

Thử missing version, price string và null numeric fields để kiểm tra validation/failure behavior.

## 50. Các sai lầm phổ biến

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Ghép raw JSON filter | Sai cú pháp/kiểu, nguy cơ input không kiểm soát | Builders + allowlist |
| Thiếu tenant filter | Đọc/sửa/xóa dữ liệu tenant khác | Trusted auth scope |
| ObjectId bị so bằng String | Không match | Đúng BSON type |
| Numeric field lưu String | Range/sort sai | Schema validation |
| eq(null) được hiểu là chỉ null | Match missing | exists/type checks |
| ne/nin được hiểu là field tồn tại | Match missing | Positive allowlist |
| Hai array dot filters thay elemMatch | Match nhờ hai phần tử khác nhau | elemMatch |
| Không check first()==null | NullPointerException | Not-found handling |
| Trả toàn document ra API | Lộ internal fields | Projection + DTO |
| Trộn include/exclude không hợp lệ | Query error | Projection policy |
| Quên _id behavior | Payload không mong muốn | excludeId khi cần |
| Sort chỉ createdAt | Pagination thiếu tie-breaker | Sort thêm _id |
| Skip offset cực lớn | Scan tốn tài nguyên | Keyset |
| Sort không có index phù hợp | Blocking sort | Compound index/explain |
| Read rồi set stock+1 | Lost update | $inc |
| Trừ stock không filter gte | Stock âm | Conditional update |
| Set toàn attributes | Mất sibling fields | Dot path |
| Push thay addToSet | Trùng array entries | Chọn đúng operator |
| addToSet được hiểu là unique toàn collection | Duplicate SKU | Unique index |
| ArrayFilters sai identifier | Update lỗi/sai target | Tests và stable IDs |
| updateMany thiếu tenant | Bulk corruption | Guardrails |
| modifiedCount=0 coi not found | False not-found | matchedCount |
| Upsert filter quá rộng | Ghi nhầm document | Business identity |
| Không có unique index | Race duplicates | Compound unique index |
| replaceOne khi chỉ sửa một field | Mất fields cũ | Updates.set |
| Retry workflow $inc thiếu idempotency | Double increment | Operation ID |
| deleteMany empty filter | Xóa toàn collection | Scope/approval |
| Soft delete không lọc khi đọc | Hiện records đã xóa | Shared scope |
| Admin account là test duy nhất | Bỏ lỗi app permissions | Least privilege |
| Toàn bộ kết quả đưa vào List | Memory pressure | Cursor/limit |
| MongoClient mới mỗi request | Resource overhead | Shared client |
| Bỏ qua explain/indexes | Hiệu năng giảm khi scale | Benchmark |
| Coi bulkWrite là transaction | Partial changes | Transaction khi cần |

## 51. Bài tập về Filters

### Bài 1 — Equality
Viết filter tìm products tenant-a thuộc category books, active=true. Nêu nguồn trustedTenantId trong backend.

### Bài 2 — Range
Tìm price từ 200000 đến dưới 500000 và stock>0.

### Bài 3 — In/nin
Tìm orders ở PENDING hoặc PAID. Tại sao nin(CANCELLED) có thể bao gồm documents thiếu status?

### Bài 4 — Null và missing
Viết điều kiện discount missing và discount hiện diện nhưng null.

### Bài 5 — Nested
Tìm attributes.language="vi" và edition>=2.

### Bài 6 — Array
Tìm tags chứa cả "java" lẫn "backend". So sánh all với in.

### Bài 7 — elemMatch
Order có BOOK-001 qty=1 và BOOK-002 qty=3. Filter yêu cầu cùng item BOOK-001 qty>=2 trả kết quả gì?

### Bài 8 — Dynamic filter
Thiết kế buildProductFilter nhận minPrice/maxPrice/category nullable nhưng luôn ép tenantId, deletedAt filter.

## 52. Bài tập về Projections và Sorts

### Bài 9 — Include fields
Chỉ trả sku, name, price và không trả _id.

### Bài 10 — Sensitive fields
API customer không được trả passwordHash, resetToken, internalNotes. Tại sao allowlist include + DTO thường an toàn hơn blacklist exclude?

### Bài 11 — Slice
So sánh Projections.slice("items",2) và find.limit(2).

### Bài 12 — Sort nhiều keys
Sắp category asc, price desc, _id asc. Tại sao cần tie-breaker?

### Bài 13 — Offset
Trang 4, pageSize 25. Nêu nguy cơ khi skip lớn và concurrent writes.

### Bài 14 — Keyset
Sort createdAt desc, _id desc. Viết điều kiện next page từ lastCreatedAt/lastId.

### Bài 15 — Index
Đề xuất compound index cho filter tenantId, active và sort createdAt desc, _id desc; dùng explain xác nhận.

## 53. Bài tập về Updates

### Bài 16 — Lost update
Hai threads đọc stock=10 rồi ghi stock=11. Tại sao sai? Viết $inc.

### Bài 17 — Conditional stock
Giảm stock 4 nếu stock>=4, product active và tenant đúng. Xử lý matchedCount=0.

### Bài 18 — Dot path
Chỉ đổi attributes.language, không làm mất edition.

### Bài 19 — combine
Cùng lúc set name, currentDate updatedAt và inc version.

### Bài 20 — Array updates
Thêm tag "java" nếu chưa có, thêm vô điều kiện, xóa tag "legacy". Chọn addToSet/push/pull.

### Bài 21 — ArrayFilters
Cập nhật qty của item BOOK-002 trong order bằng $[item] và UpdateOptions.

### Bài 22 — Upsert
Lấy tenantId+sku làm identity, set price/name và setOnInsert(createdAt). Cần unique index nào?

### Bài 23 — CAS
Hai users cùng sửa document version=5. Viết filter và update tăng version. User thứ hai phải xử lý gì?

### Bài 24 — State transition
Chuyển order PENDING sang PAID chỉ khi hiện tại PENDING. Vì sao update thiếu status filter nguy hiểm?

### Bài 25 — findOneAndUpdate
Giảm stock 1 nếu còn hàng, trả về stock sau update với ReturnDocument.AFTER.

## 54. Bài tập về CRUD và hiệu năng

### Bài 26 — Integration CRUD
Trên lab, insert một record, find/projection, update, readback và delete. Assert mọi kết quả.

### Bài 27 — ReplaceOne
Một replacement chỉ có _id/name/price. Những fields cũ nào có thể mất và khi nào nên dùng Updates.set?

### Bài 28 — DeleteMany
Vì sao empty filter nguy hiểm? Thiết kế require tenantId và preview affected rows.

### Bài 29 — Soft delete
Thiết kế deletedAt missing convention, repository filters mặc định, cùng uniqueness của SKU sau soft delete.

### Bài 30 — Count
So sánh countDocuments(filter) và estimatedDocumentCount khi đếm products theo tenant.

### Bài 31 — Explain
Trên 1 triệu records, query range + sort có p95 cao. Dùng winning plan, docs examined, nReturned và indexes để phân tích.

### Bài 32 — Concurrency
Chạy 100 Updates.inc đồng thời, so final stock với expected. Thêm một bài thử update bằng read-then-set và quan sát race.

### Bài 33 — Retry
HTTP timeout sau khi $inc đã commit. Vì sao retry toàn bộ business request có thể tăng lần thứ hai? Thiết kế idempotency key.

### Bài 34 — Cursor
Lấy 1 triệu products từng phần mà không đưa toàn bộ vào heap; dùng MongoCursor và try-with-resources.

### Bài 35 — Transaction
Một order giảm stock hai products và thêm booking. Vì sao hai updateOne không tự all-or-nothing? Khi nào cần multi-document transaction?

## 55. Checklist trước khi đưa CRUD vào production

1. MongoDB URI/secrets được quản lý an toàn.
2. MongoClient được tái sử dụng.
3. Driver và server tương thích.
4. Bson/Document/POJO codec khớp schema.
5. Field names và BSON types nhất quán.
6. Mọi read/update/delete có tenant/authorization scope.
7. Không cho client gửi raw arbitrary BSON.
8. Optional filters được validate.
9. Null/missing/ne/nin semantics đã kiểm thử.
10. Arrays sử dụng elemMatch khi cần cùng phần tử.
11. Projection allowlist cho public API.
12. DTO không trả secret/PII ngoài quyền.
13. Sort có deterministic tie-breaker.
14. Page size và offset được giới hạn.
15. Keyset cursor được kiểm tra kiểu/scope.
16. Dùng $inc hoặc conditional update để tránh read-then-write races.
17. Stock/state invariants nằm trong filter update.
18. Version optimistic locking khi concurrent edits.
19. updateOne/updateMany theo đúng intent.
20. matchedCount và modifiedCount được xử lý đúng.
21. Upsert có stable identity và unique index.
22. Không dùng replaceOne khi chỉ đổi vài fields.
23. ArrayFilters được test.
24. DeleteMany có guardrails.
25. Soft delete convention áp dụng nhất quán.
26. Multi-document transaction khi cần all-or-nothing.
27. External effects có idempotency/outbox.
28. Duplicate key, timeout, network/election errors có policy.
29. Cursor được close.
30. Indexes được benchmark bằng explain.
31. Read/write concern phù hợp durability/SLO.
32. Logs không lộ credentials/PII.
33. Có integration/concurrency/security tests.
34. Bulk changes có backup và rollback strategy.

## 56. Bảng tra nhanh Builders

| Nhu cầu | Builder/API |
| --- | --- |
| So bằng | Filters.eq |
| So khác | Filters.ne |
| So khoảng | Filters.gt/gte/lt/lte |
| Kết hợp AND/OR | Filters.and/or |
| Thuộc tập giá trị | Filters.in/nin |
| Field tồn tại | Filters.exists |
| Cùng phần tử array | Filters.elemMatch |
| Mảng chứa nhiều giá trị | Filters.all |
| Regex | Filters.regex |
| Chỉ lấy một số fields | Projections.include |
| Loại field | Projections.exclude |
| Loại _id | Projections.excludeId |
| Kết hợp projections | Projections.fields |
| Giới hạn array output | Projections.slice |
| Sort tăng | Sorts.ascending |
| Sort giảm | Sorts.descending |
| Sort nhiều khóa | Sorts.orderBy |
| Gán field | Updates.set |
| Tăng/giảm atomic | Updates.inc |
| Xóa field | Updates.unset |
| Đổi field name | Updates.rename |
| Current timestamp | Updates.currentDate |
| Gộp nhiều operators | Updates.combine |
| Array append | Updates.push |
| Array no-duplicate append | Updates.addToSet |
| Array remove | Updates.pull |
| Chỉ khi upsert insert | Updates.setOnInsert |
| Cập nhật một document | updateOne |
| Cập nhật nhiều documents | updateMany |
| Cập nhật rồi trả document | findOneAndUpdate |
| Tạo nếu không match | UpdateOptions.upsert |
| Xóa document | deleteOne/deleteMany |

## 57. Kết luận

**Filters, Projections, Sorts và Updates** là bộ công cụ cốt lõi để diễn đạt MongoDB CRUD trong Java Sync Driver:

- **Filters** chọn documents dựa trên điều kiện. Hãy hiểu chính xác null/missing, range, arrays và quan trọng nhất là **tenant authorization**.
- **Projections** giới hạn những fields trả về. Kết hợp include allowlist và DTO để giảm payload và tránh lộ dữ liệu nhạy cảm.
- **Sorts** tạo thứ tự. Thêm tie-breaker và cân nhắc keyset pagination với dữ liệu lớn.
- **Updates** mô tả phép sửa ở server. Server-side $inc, conditional filters, version compare-and-set và arrayFilters giúp tránh những race conditions hay nhầm nested-field updates.
- **MongoCollection CRUD methods** thực sự chạy thao tác, còn builders là các BSON expressions được đưa vào thao tác đó.

Code CRUD hoàn chỉnh cho production không dừng ở chuyện câu lệnh chạy thành công. Nó còn phải **không làm mất cập nhật đồng thời, không sửa sai document, không bỏ qua quyền tenant, không gây truy vấn quá chậm và có khả năng xử lý retry/errors rõ ràng**. Khi hiểu cả builders, data modeling, index và write semantics, lập trình viên có thể xây repository Java vừa dễ đọc vừa an toàn trước concurrency và dữ liệu tăng trưởng.

## Tài liệu tham khảo

- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Delete Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/delete-documents/)
- [MongoDB Manual — Query Predicates](https://www.mongodb.com/docs/manual/reference/operator/query/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Projection](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Single-Document Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
