# Regex, phân biệt hoa thường và tác động đến chỉ mục

## 1. Bối cảnh và mục tiêu

Trong **Spring Data MongoDB**, `Query` và `Criteria` giúp viết điều kiện truy vấn trên document BSON mà không cần ghép chuỗi JSON thủ công. Với hệ thống bán hàng **Mini Commerce** gồm `Product`, `Customer` và `Order`, việc tìm kiếm sản phẩm theo tên, SKU, danh mục hoặc thông tin người nhận có thể phát sinh nhiều yêu cầu khác nhau:

- Tìm sản phẩm có tên **bắt đầu bằng** một tiền tố.
- Tìm tên sản phẩm **chứa** một đoạn văn bản.
- Tìm chính xác một SKU mà **không phân biệt chữ hoa/chữ thường**.
- Hỗ trợ tên tiếng Việt có dấu và không dấu theo quy tắc được xác định trước.
- Đảm bảo trang danh sách vẫn nhanh khi collection tăng từ hàng trăm lên hàng triệu document.

Một lỗi phổ biến là thay mọi phép so sánh chuỗi bằng `$regex` có tùy chọn `i`, rồi tin rằng thêm một index case-insensitive sẽ làm truy vấn nhanh. Điều đó không đúng: MongoDB **không dùng collation index để tối ưu `$regex` theo cách nó tối ưu phép equality có collation**. Bài này giải thích cụ thể sự khác biệt giữa **regex**, **collation**, **trường tìm kiếm đã chuẩn hóa** và **các loại index**.

Sau khi học, bạn có thể:

1. Viết các biểu thức `$regex` trong `mongosh` và trong `Criteria.regex(...)`.
2. Phân biệt regex **bắt đầu** (`^prefix`), **kết thúc** (`suffix$`), **chứa đoạn** và **khớp toàn chuỗi**.
3. Hiểu các tùy chọn `i`, `m`, `s` và giới hạn khi xử lý Unicode/tiếng Việt.
4. Giải thích khi nào một B-tree index giúp truy vấn regex, khi nào có `IXSCAN` nhưng vẫn quét quá nhiều khóa.
5. Sử dụng **collation** cho equality/sort không phân biệt hoa thường, với index có cấu hình collation tương ứng.
6. Thiết kế field chuẩn hóa như `nameSearch` khi cần tìm prefix có hiệu năng ổn định.
7. Bảo vệ API khỏi regex injection, pattern quá tốn CPU, truy vấn không giới hạn và sort không có index.
8. Kiểm thử semantics và quan sát `explain("executionStats")` trên MongoDB thật.

**Điều kiện đầu vào:** Java 17+, Spring Boot với `spring-boot-starter-data-mongodb`, MongoDB đang hoạt động, hiểu `@Document`, `@Id`, `@Field`, `MongoTemplate`, `MongoRepository`, `Query` và `Criteria`. Phần lớn ví dụ dùng API đồng bộ; những nguyên tắc BSON/index cũng đúng với nhánh reactive.

## 2. Phân biệt bốn nhu cầu tìm kiếm

Không có một phép tìm kiếm chuỗi tốt nhất cho mọi yêu cầu.

| Yêu cầu | Filter thường phù hợp | Ví dụ | Lưu ý index |
| --- | --- | --- | --- |
| Bằng tuyệt đối, phân biệt hoa thường | `{ sku: "KBD-001" }` | Mã sản phẩm đúng từng ký tự | Equality index rất phù hợp |
| Bằng tuyệt đối, **không** phân biệt hoa thường | Equality kèm **collation** | `"BAN PHIM"` bằng `"ban phim"` theo collation | Cần index **cùng collation** |
| Bắt đầu bằng chuỗi, phân biệt hoa thường | `{ name: { $regex: "^Ban" } }` | Tên bắt đầu `Ban` | Có thể tối ưu bằng **prefix index range** |
| Bắt đầu bằng chuỗi, không phân biệt hoa thường | `{ name: { $regex: "^ban", $options: "i" } }` | `Ban` và `BAN` | Không được tối ưu như equality bằng collation index |
| Có chứa một đoạn ở bất kỳ vị trí nào | `{ name: { $regex: "Mini" } }` | `"Chuột Mini"` | Prefix index optimization thường không áp dụng |
| Search không dấu, gõ sai, autocomplete, xếp hạng | Trường chuẩn hóa hoặc công cụ search chuyên dụng | `"ban phim"` → `"Bàn phím"` | Cần mô hình search/index riêng |

**Quy tắc khởi đầu:** nếu chỉ cần **equality**, dùng equality; nếu chỉ cần **prefix**, biểu diễn đúng prefix; nếu cần **full-text/fuzzy/autocomplete**, cân nhắc hệ thống search phù hợp. Đừng chọn regex tùy ý chỉ vì API dễ viết.

## 3. Dữ liệu Mini Commerce để thực hành

### 3.1. Product và các trường tìm kiếm

Trong bài này, entity `Product` có trường tên hiển thị `name` và một trường tùy chọn `nameSearch` dùng cho chiến lược chuẩn hóa ở phần sau.

```java
package com.example.minicommerce.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;
    private String category;
    private boolean active;

    @Field("name_search")
    private String nameSearch;

    @Field(name = "unit_price", targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    public Product() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCategory() { return category; }
    public void setCategory(String category) {
        this.category = category;
    }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public String getNameSearch() { return nameSearch; }
    public void setNameSearch(String nameSearch) {
        this.nameSearch = nameSearch;
    }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
```

Trong entity trên, Java property `nameSearch` được lưu trong BSON thành `name_search` nhờ `@Field`. Tương tự, `price` được lưu thành `unit_price` dạng Decimal128. Các method `Criteria.where(...)` gắn với `Product.class` nên dùng **tên property Java**; `mongosh` và raw driver dùng **tên BSON**.

### 3.2. Fixture thể hiện chữ hoa/thường và dấu tiếng Việt

Chạy trong database **test riêng**:

```javascript
use mini_commerce

db.products.insertMany([
  {
    _id: "regex-p1",
    sku: "KBD-001",
    name: "Ban phim Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("129900.00")
  },
  {
    _id: "regex-p2",
    sku: "KBD-002",
    name: "BAN PHIM Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("159900.00")
  },
  {
    _id: "regex-p3",
    sku: "KBD-003",
    name: "Bàn phím Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("179900.00")
  },
  {
    _id: "regex-p4",
    sku: "MOU-001",
    name: "Chuột Mini",
    name_search: "chuot mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("99000.00")
  }
]);
```

Giả định chỉ có bốn fixture trên khi đối chiếu kết quả:

| ID | `name` | `name_search` |
| --- | --- | --- |
| `regex-p1` | Ban phim Mini | ban phim mini |
| `regex-p2` | BAN PHIM Mini | ban phim mini |
| `regex-p3` | Bàn phím Mini | ban phim mini |
| `regex-p4` | Chuột Mini | chuot mini |

Fixture minh họa rõ ba kiểu “bằng nhau” khác nhau: **bằng byte/chuỗi**, **bằng nhau khi không phân biệt hoa thường**, và **bằng nhau sau khi bỏ dấu theo quy tắc của ứng dụng**. Không đánh đồng ba khái niệm này.

Lệnh `insertMany` sẽ bị duplicate `_id` nếu chạy lại. Trong integration test hãy dùng ID có phạm vi test và cleanup riêng; không chạy fixture trên production.

## 4. Cú pháp $regex trong MongoDB

MongoDB hỗ trợ regex trong filter:

```javascript
// Regex dưới dạng chuỗi:
db.products.find({ name: { $regex: "^Ban" } });

// Regex literal trong mongosh:
db.products.find({ name: /^Ban/ });

// Không phân biệt chữ hoa/chữ thường:
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

Trong MongoDB hiện đại, server dùng engine regex **PCRE2** từ MongoDB 6.1. Khi viết Java `Pattern`, cần nhớ pattern được gửi tới MongoDB để thực thi; không suy đoán mọi chức năng, Unicode flag hoặc performance của Java regex và PCRE2 giống hệt nhau trong mọi phiên bản.

### 4.1. Các ký hiệu hay dùng

| Pattern | Ý nghĩa | Ví dụ khớp |
| --- | --- | --- |
| `^Ban` | Chuỗi bắt đầu bằng `Ban` | `Ban phim Mini` |
| `Mini$` | Chuỗi kết thúc bằng `Mini` | `Chuột Mini` |
| `Mini` | `Mini` xuất hiện ở bất kỳ vị trí nào | Cả bốn fixture |
| `^Ban phim Mini$` | Khớp từ đầu đến cuối, chính xác chữ hoa/thường | Chỉ `regex-p1` |
| `^Ban.*Mini$` | Bắt đầu `Ban`, sau đó ký tự bất kỳ, kết thúc `Mini` | `regex-p1` |
| `^ban` + `i` | Bắt đầu bằng `ban`, không phân biệt hoa thường | `regex-p1`, `regex-p2` |
| `B.n` | `.` khớp một ký tự (trừ xuống dòng nếu thiếu tùy chọn `s`) | Có thể khớp `Ban` |

Regex là **ngôn ngữ pattern**, không phải phép so khớp văn bản thông thường. Ví dụ ký tự `.`, `*`, `+`, `?`, `[`, `(` hay `|` do người dùng nhập có thể thay đổi hoàn toàn ý nghĩa truy vấn nếu không được escape.

### 4.2. Phân biệt prefix, contains, suffix

```javascript
// Prefix: phân biệt hoa/thường.
db.products.find({ name: { $regex: "^Ban" } });
// Chỉ regex-p1.

// Contains: kiểm tra sự xuất hiện của Mini.
db.products.find({ name: { $regex: "Mini" } });
// regex-p1, regex-p2, regex-p3, regex-p4.

// Suffix.
db.products.find({ name: { $regex: "Mini$" } });
// Cả bốn fixture.

// Exact case-sensitive.
db.products.find({ name: { $regex: "^Ban phim Mini$" } });
// Chỉ regex-p1.
```

Nếu chỉ cần exact và không cần semantics của regex, hãy dùng:

```javascript
db.products.find({ name: "Ban phim Mini" });
```

Equality vừa dễ đọc vừa thường cho phép dùng index có hiệu quả hơn. `^...$` không phải cách thay thế mặc định cho phép bằng.

### 4.3. Các tùy chọn i, m, s, x

| Option | Ý nghĩa | Ví dụ ứng dụng |
| --- | --- | --- |
| `i` | Case-insensitive regex matching | `"^ban"` khớp `Ban`/`BAN` |
| `m` | Multiline: `^` và `$` có thể xét ranh giới dòng | Mô tả sản phẩm nhiều dòng |
| `s` | Dotall: `.` có thể khớp ký tự xuống dòng | Pattern xuyên dòng |
| `x` | Extended mode: hỗ trợ khoảng trắng/chú thích trong pattern theo quy tắc regex | Pattern phức tạp, thường không cần ở tìm kiếm sản phẩm |

```javascript
// Mẫu phải bắt đầu ở đầu của một dòng nội dung mô tả.
db.products.find({
  description: { $regex: "^Khuyen mai", $options: "im" }
});
```

Đừng bật `m`/`s` một cách máy móc: chúng thay đổi semantics và có thể làm pattern khó tối ưu hơn. Đối với prefix index, cần quan tâm pattern thực sự bị neo ở **đầu chuỗi** chứ không chỉ đầu của bất kỳ dòng nào.

## 5. Spring Data MongoDB: Criteria.regex(...)

`Criteria` có các overload dùng String, String + options, Java `Pattern` hoặc `BsonRegularExpression`. Cú pháp dưới đây minh họa những đường đi phổ biến:

```java
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// 1. Prefix phân biệt hoa/thường:
Query prefix = Query.query(
    Criteria.where("name").regex("^Ban"));

// 2. Prefix không phân biệt hoa/thường:
Query prefixIgnoreCase = Query.query(
    Criteria.where("name").regex("^ban", "i"));

// 3. Pattern Java:
Pattern exact = Pattern.compile(
    "^Ban phim Mini$", Pattern.CASE_INSENSITIVE);
Query withPattern = Query.query(
    Criteria.where("name").regex(exact));

// 4. Substring literal, phân biệt hoa/thường:
Query containsMini = Query.query(
    Criteria.where("name").regex("Mini"));

List<Product> products =
    mongoTemplate.find(prefixIgnoreCase, Product.class);
```

Cần import `Product` đúng package và inject `MongoTemplate` qua constructor trong service. `Criteria.where("name")` dùng **tên property Java**; khi Spring Data tạo BSON query cho `Product.class`, nó áp dụng metadata mapping.

### 5.1. Regex và điều kiện nghiệp vụ kết hợp

Trong Mini Commerce, API tìm sản phẩm nên giới hạn ít nhất theo `active` và danh mục (nếu đầu vào có category):

```java
Query query = Query.query(
    Criteria.where("active").is(true)
        .and("category").is("phu-kien")
        .and("name").regex("^Ban"));

List<Product> result = mongoTemplate.find(query, Product.class);
```

BSON logic:

```javascript
{
  active: true,
  category: "phu-kien",
  name: { $regex: "^Ban" }
}
```

Với schema có nhiều cửa hàng, cần bổ sung `tenantId` hoặc quyền truy cập vào filter; chỉ thêm `active = true` không đủ phân quyền. Với các điều kiện tùy chọn, dùng `Query.addCriteria(...)` hoặc xây `Criteria` có chủ đích thay vì nối chuỗi JSON.

### 5.2. Repository derived queries có thể tạo regex

`MongoRepository` có các từ khóa suy diễn:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    List<Product> findByNameStartingWith(String prefix);

    List<Product> findByNameStartingWithIgnoreCase(String prefix);

    List<Product> findByNameContainingIgnoreCase(String fragment);

    List<Product> findByNameEndingWith(String suffix);
}
```

Spring Data MongoDB thường chuyển `StartingWith` thành regex bắt đầu, `Containing` thành regex tìm chuỗi con và `IgnoreCase` thành regex với `i`. Không giả định method `findByNameStartingWithIgnoreCase(...)` tự tối ưu bằng index có collation. Hãy kiểm tra BSON và plan của truy vấn thật.

### 5.3. @Query khi cần kiểm soát filter JSON

`@Query` hỗ trợ placeholder tham số thay vì nối JSON:

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'name': { '$regex': ?0, '$options': 'i' } }")
List<Product> searchByPatternIgnoreCase(String pattern);
```

Đoạn method cần đặt trong `ProductRepository`. `?0` là tham số thứ nhất và phải được bind bởi Spring Data; tuy nhiên **binding không tự biến regex do người dùng cung cấp thành literal an toàn**. Caller vẫn cần giới hạn độ dài, định dạng và escape nội dung nếu search chỉ cho phép chuỗi thường.

Không truyền nội dung yêu cầu HTTP nguyên vẹn như `.*` hoặc `^(a+)+$` vào một API cho phép regex tùy ý.

## 6. Dữ liệu người dùng: escape pattern và giới hạn chi phí

Nếu người dùng nhập dấu `.`, họ có thể chỉ muốn tìm sản phẩm có dấu chấm trong tên, không phải ký tự wildcard regex. Dùng `Pattern.quote` để diễn đạt **chuỗi literal**:

```java
import java.util.regex.Pattern;

public List<Product> searchPrefix(String userPrefix) {
    if (userPrefix == null) {
        throw new IllegalArgumentException("Prefix is required");
    }

    String prefix = userPrefix.trim();
    if (prefix.isEmpty() || prefix.length() > 64) {
        throw new IllegalArgumentException(
            "Prefix length must be between 1 and 64");
    }

    String pattern = "^" + Pattern.quote(prefix);

    Query query = Query.query(
        Criteria.where("active").is(true)
            .and("name").regex(pattern));

    query.limit(20);
    query.maxTime(java.time.Duration.ofSeconds(2));

    return mongoTemplate.find(query, Product.class);
}
```

Đây là đoạn phương thức thuộc một service có `MongoTemplate mongoTemplate` được inject và import `Product`, `Query`, `Criteria` phù hợp. Khi tạo API production, hãy giới hạn số request, kiểm soát tenant và chỉ trả DTO cần thiết.

**Quan trọng với index:** `Pattern.quote` có thể tạo pattern chứa `\Q...\E`. Tùy query engine và phiên bản, cấu trúc escape có thể làm index prefix optimization **khác** so với một pattern đơn giản `^Ban`. Vì thế phải đo bằng `explain`; nếu cần truy vấn prefix thật nhanh và đầu vào đa dạng, cân nhắc **trường chuẩn hóa** chứa tập ký tự được phép ở phần 10.

### 6.1. Không phụ thuộc hoàn toàn vào maxTime

`maxTime`/timeout giúp giới hạn một truy vấn quá dài nhưng không thay:

- Validation đầu vào và độ dài pattern.
- Rate limiting và giới hạn page size.
- Index hoặc thiết kế search đúng.
- Kiểm soát trường nào được tìm, theo quyền nào.
- Quan sát CPU/latency, số khóa và số document đã duyệt.

Nếu người dùng cần regex nâng cao thật sự (ví dụ một công cụ quản trị nội bộ), đặt cơ chế quyền riêng, giới hạn mẫu/độ phức tạp và vận hành trên tập dữ liệu có phạm vi phù hợp.

## 7. Case-insensitive regex không giống collation

Đây là điểm trung tâm của bài:

- `{ name: { $regex: "^ban", $options: "i" } }` sử dụng **regex engine** với cờ `i`.
- `{ name: "ban phim mini" }` kèm `collation: { locale: "vi", strength: 2 }` sử dụng **quy tắc so sánh chuỗi ICU** cho equality.
- MongoDB **không coi `$regex` là collation-aware**. Một index cấu hình case-insensitive bằng collation **không giúp `$regex` tận dụng khả năng phân biệt hoa/thường của index như equality**.

### 7.1. Regex không phân biệt hoa/thường

```javascript
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

Với fixture, truy vấn trả `regex-p1` và `regex-p2`. `regex-p3` có chữ `à`, vì vậy **đừng mặc định** `i` đồng nghĩa với bỏ dấu: `"Ban"` và `"Bàn"` không tự được xem là cùng một chuỗi chỉ do bật `i`.

### 7.2. Collation trên equality

Muốn so sánh **chính xác tên** mà không phân biệt hoa/thường, có thể dùng:

```javascript
db.products.find({
  name: "ban phim mini"
}).collation({
  locale: "vi",
  strength: 2
});
```

Ở collation strength 2, việc so sánh **không phân biệt hoa thường nhưng vẫn xét khác biệt dấu**. Với fixture, `regex-p1` và `regex-p2` có thể khớp; `regex-p3` có dấu `à` không khớp cùng chuỗi không dấu.

Để tìm **không phân biệt cả hoa thường lẫn dấu** theo primary level:

```javascript
db.products.find({
  name: "ban phim mini"
}).collation({
  locale: "vi",
  strength: 1
});
```

Strength 1 chỉ so sánh ký tự cơ sở theo quy tắc locale và thường bỏ qua khác biệt về dấu/case. Tuy nhiên việc xem hai tên là tương đương còn phụ thuộc **locale ICU và quy tắc nghiệp vụ**; cần test tiếng Việt thực tế thay vì suy đoán mọi trường hợp `đ`/`d` hoặc các tổ hợp Unicode đều giống nhau.

**Collation không biến phép equality thành tìm substring.** Query equality có collation vẫn cần khớp **toàn bộ** tên theo quy tắc so sánh; nó không tìm `"Mini"` trong `"Chuột Mini"`.

### 7.3. Collation trong MongoTemplate

```java
import java.util.List;

import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Collation caseInsensitive = Collation.of("vi")
    .strength(Collation.ComparisonLevel.secondary());

Query sameNameIgnoreCase = Query.query(
    Criteria.where("name").is("ban phim mini"))
    .collation(caseInsensitive);

List<Product> matches = mongoTemplate.find(
    sameNameIgnoreCase, Product.class);
```

Phải import `Product` và inject `MongoTemplate` trong service. Đây là **equality có collation**, không phải `Criteria.regex(..., "i")`.

## 8. Index nào hỗ trợ regex?

MongoDB có thể dùng B-tree index trên một trường chuỗi cho `$regex` phân biệt hoa/thường, đặc biệt khi pattern có **tiền tố cố định**.

### 8.1. Prefix có anchor: tình huống tối ưu được

Tạo index:

```javascript
db.products.createIndex({ name: 1 });
```

Truy vấn:

```javascript
db.products.find({
  name: { $regex: "^Ban" }
}).explain("executionStats");
```

Nếu index phù hợp và planner chọn nó, MongoDB có thể tạo **index range** cho những tên bắt đầu bằng `Ban`. Điều này giúp tránh phải kiểm tra tất cả tên trong collection.

Ba pattern có vẻ tương đương:

```javascript
{ name: { $regex: "^Ban" } }
{ name: { $regex: "^Ban.*" } }
{ name: { $regex: "^Ban.*$" } }
```

Nhưng chúng **khác chi phí**. Theo MongoDB Manual, một pattern prefix gọn như `^Ban` có thể dừng sau khi hết khoảng tiền tố; thêm `.*` và `$` có thể làm công việc so khớp tốn thêm. Không thêm wildcard thừa vào cuối prefix.

**Không có cam kết tuyệt đối rằng mọi regex có `^` luôn dùng index.** Index khả dụng, collation, selectivity, version và plan của truy vấn đều ảnh hưởng lựa chọn của MongoDB.

### 8.2. Contains và suffix không có range tiền tố hữu ích

```javascript
db.products.find({
  name: { $regex: "Mini" }
}).explain("executionStats");

db.products.find({
  name: { $regex: "Mini$" }
}).explain("executionStats");
```

Vì MongoDB không biết những tên hợp lệ phải **bắt đầu bằng** một prefix cố định nào, bộ tối ưu thường không thể thu hẹp index range theo cách `^Ban` làm được. Có thể vẫn có một `IXSCAN` rộng hoặc `COLLSCAN`; `IXSCAN` **không có nghĩa** là truy vấn nhanh nếu phải duyệt rất nhiều khóa.

### 8.3. Regex với i không được tối ưu nhờ case-insensitive index

```javascript
db.products.find({
  name: { $regex: "^ban", $options: "i" }
}).explain("executionStats");
```

MongoDB `$regex` **không collation-aware**. Tạo index với `{ locale: "vi", strength: 2 }` cho `name` không biến truy vấn regex `i` thành một phép prefix range hiệu quả theo collation. Đây là lý do không nên khuyên “chỉ cần thêm case-insensitive index” cho mọi chức năng tìm kiếm tên.

So sánh trên dataset đủ lớn mới có ý nghĩa. Với vài document fixture, planner có thể chọn `COLLSCAN` ngay cả khi index hợp lệ, vì scan trực tiếp rẻ hơn.

## 9. Index với collation cho equality không phân biệt hoa/thường

Nếu nghiệp vụ cần tra **exact name** hoặc một business key theo case-insensitive equality, tạo index có collation:

```javascript
db.products.createIndex(
  { name: 1 },
  {
    name: "idx_name_vi_ci",
    collation: { locale: "vi", strength: 2 }
  }
);
```

Query phải dùng **cùng collation** để tận dụng index cho so sánh chuỗi:

```javascript
db.products.find({
  name: "ban phim mini"
})
.collation({ locale: "vi", strength: 2 })
.explain("executionStats");
```

Trong collection không có default collation như fixture, nếu bỏ `collation(...)` ở query, MongoDB dùng so sánh binary mặc định; index collation strength 2 **không tự áp dụng cho query binary**.

**Nếu cần không phân biệt dấu**, tạo index khác hoặc chọn collation strength 1 phù hợp với hợp đồng dữ liệu, rồi bảo đảm query sử dụng cùng cấu hình. Không trộn strength 1 và strength 2 tùy ý trong cùng một API.

### 9.1. Không dùng index collation để “sửa” regex i

Hai filter sau có khác biệt quan trọng:

```javascript
// Equality, case-insensitive theo collation:
db.products.find({ name: "ban phim mini" })
  .collation({ locale: "vi", strength: 2 });

// Regex, case-insensitive theo regex engine:
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

Filter thứ nhất có cơ hội tận dụng **index collation** vì là phép so sánh chuỗi theo locale. Filter thứ hai là regex; **không** hưởng lợi tương tự từ index case-insensitive.

### 9.2. Đừng nhầm collation index với full-text search

Index collation phục vụ so sánh/sắp xếp chuỗi theo quy tắc ngôn ngữ. Nó không tự cung cấp fuzzy search, stemming, tìm từ đồng nghĩa hay gợi ý hoàn thành cụm từ. Các yêu cầu đó cần thiết kế search riêng, chẳng hạn MongoDB Search với chỉ mục/analyzer tương ứng nếu nền tảng sử dụng hỗ trợ.

## 10. Trường đã chuẩn hóa: giải pháp cho prefix không dấu

Với Mini Commerce, người dùng có thể nhập `ban phim` để tìm tên hiển thị `Bàn phím`. Nếu thường xuyên cần **prefix search**, một lựa chọn là lưu **thêm** trường chuẩn hóa:

```text
name          = "Bàn phím Mini"
name_search   = "ban phim mini"

name          = "BAN PHIM Mini"
name_search   = "ban phim mini"
```

Sau đó tìm theo `name_search` bằng **regex prefix phân biệt hoa/thường**:

```javascript
db.products.createIndex({
  active: 1,
  category: 1,
  name_search: 1
});

db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
});
```

Với bốn fixture, truy vấn trả `regex-p1`, `regex-p2` và `regex-p3`. Vì `name_search` đã được chuẩn hóa thành chữ thường/không dấu theo hợp đồng Mini Commerce, **không cần bật `i`** trong regex này.

### 10.1. Một hàm chuẩn hóa minh họa

```java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchTextNormalizer {

    private SearchTextNormalizer() {}

    public static String normalize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Text required");
        }

        String lower = Normalizer.normalize(
            raw, Normalizer.Form.NFD).toLowerCase(Locale.ROOT);

        return lower
            .replace('đ', 'd')
            .replaceAll("\\p{M}+", "")
            .replaceAll("[^a-z0-9 ]+", " ")
            .replaceAll("\\s+", " ")
            .trim();
    }
}
```

Hàm minh họa chuẩn hóa Unicode, thay `đ` thành `d`, bỏ dấu kết hợp và quy về tập ký tự `a-z`, chữ số, khoảng trắng. Đây là **chính sách nghiệp vụ của ví dụ**, không phải thuật toán tìm kiếm tiếng Việt đầy đủ. Nó có thể làm mất thông tin của ký hiệu sản phẩm, model code hay các ngôn ngữ khác; cân nhắc trường riêng cho tìm kiếm nếu sản phẩm dùng nhiều ngôn ngữ.

Nếu đặt quy tắc chuẩn hóa này trong service, cần áp dụng thống nhất khi **insert**, **update name**, **import**, **migration** và **truy vấn**. Không chỉ chuẩn hóa query mà bỏ qua các document cũ chưa có `name_search`.

### 10.2. Query theo Java property đã map

```java
public List<Product> searchNormalizedPrefix(
        String rawPrefix, String category) {

    if (rawPrefix == null || rawPrefix.length() > 64) {
        throw new IllegalArgumentException("Invalid prefix");
    }

    String normalized = SearchTextNormalizer.normalize(rawPrefix);
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(
            "Prefix contains no searchable characters");
    }

    // normalize() chỉ giữ [a-z0-9 ], không còn metachar của regex.
    String safePrefixPattern = "^" + normalized;

    Query query = Query.query(
        Criteria.where("active").is(true)
            .and("category").is(category)
            .and("nameSearch").regex(safePrefixPattern));

    query.limit(20);

    return mongoTemplate.find(query, Product.class);
}
```

Trong MongoDB, Java property `nameSearch` được ánh xạ thành BSON `name_search`. Đầu vào đã được biến đổi theo tập ký tự giới hạn, nên chuỗi regex không còn metachar tùy ý. **Đừng bỏ bước bảo đảm tập ký tự an toàn** rồi tiếp tục nối thẳng user input vào regex.

### 10.3. Đánh đổi của denormalized search field

| Lợi ích | Chi phí/rủi ro |
| --- | --- |
| Prefix đơn giản có thể dùng index theo khoảng | Thêm field và index, tăng chi phí ghi |
| Không cần `$options: "i"` khi field luôn lowercase | Mọi đường ghi phải đồng bộ hóa `name` và `name_search` |
| Có thể định nghĩa chính sách bỏ dấu rõ ràng | Có thể gộp nhầm chuỗi khác nhau, cần thỏa thuận nghiệp vụ |
| Query có shape cố định, dễ benchmark | Dữ liệu legacy cần backfill; update sai có thể tạo stale search field |

Với nhu cầu tìm substring ở bất kỳ vị trí, một normalized field + regex không anchor vẫn có thể quét nhiều index entries. Không coi normalization là cách thay thế cho hệ thống search chuyên dụng trong mọi tình huống.

## 11. Compound index và cách đọc explain

Để lọc sản phẩm đang bán theo danh mục rồi tìm tên bắt đầu bằng prefix, một index đáng thử:

```javascript
db.products.createIndex({
  active: 1,
  category: 1,
  name_search: 1
});
```

Query:

```javascript
db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
})
.limit(20)
.explain("executionStats");
```

Index trên có hai trường equality phía trước (`active`, `category`) và trường prefix/range phía sau (`name_search`). Đây là một mẫu thiết kế hữu ích **khi query shape thực sự như vậy**. Nếu phần lớn truy vấn chỉ tìm theo prefix mà không có category, hoặc cần sort theo giá, index tối ưu có thể khác.

### 11.1. Các chỉ số cần đọc

| Trường trong explain | Câu hỏi cần trả lời |
| --- | --- |
| `winningPlan` | Planner chọn `IXSCAN`, `FETCH`, `COLLSCAN` hay bước `SORT` nào? |
| `indexBounds` (nếu có) | Regex prefix có tạo khoảng index hẹp hay scan rộng? |
| `totalKeysExamined` | Đã duyệt bao nhiêu mục index? |
| `totalDocsExamined` | Đã đọc/kiểm tra bao nhiêu document thật? |
| `nReturned` | Có bao nhiêu kết quả trả về? |
| `executionTimeMillis` | Thời gian thực thi của lần giải thích; cần đo thêm ở workload đại diện |

Đừng chỉ nhìn thấy `IXSCAN` rồi cho rằng truy vấn tối ưu. Nếu `totalKeysExamined` rất lớn so với `nReturned`, một index scan vẫn có thể quá đắt.

### 11.2. So sánh có kiểm soát ba query shape

```javascript
// A. Prefix case-sensitive, index name có thể hữu ích.
db.products.find({ name: { $regex: "^Ban" } })
  .explain("executionStats");

// B. Prefix case-insensitive, không tận dụng collation index như equality.
db.products.find({
  name: { $regex: "^ban", $options: "i" }
}).explain("executionStats");

// C. Prefix trên field chuẩn hóa, với compound index phù hợp.
db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
}).explain("executionStats");
```

Lưu lại `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `winningPlan` và độ lớn dữ liệu. Ba truy vấn ở trên **không có filter tương đương hoàn toàn**, nên so sánh latency trực tiếp không chứng minh thuật toán nào tốt hơn; cần kiểm thử query nghiệp vụ cùng mức selectivity và trên dữ liệu đủ lớn.

**Trên collection có bốn fixture**, mọi query đều có thể chạy rất nhanh với `COLLSCAN`. Muốn đánh giá index, tạo dataset thử nghiệm lớn, phân bố tên phù hợp và kiểm tra plan thay vì kết luận từ vài document.

## 12. Regex trên trường nhúng, array và dữ liệu khác kiểu

### 12.1. Document nhúng

Giả sử đơn hàng lưu:

```json
{
  "_id": "order-001",
  "customerId": "customer-001",
  "shippingAddressSnapshot": {
    "recipient": "Nguyen Thi Lan",
    "city": "TP Ho Chi Minh"
  }
}
```

Có thể tìm theo tên người nhận:

```javascript
db.orders.find({
  "shippingAddressSnapshot.recipient": {
    $regex: "^Nguyen"
  }
});
```

Với Spring Data:

```java
Query query = Query.query(
    Criteria.where("shippingAddressSnapshot.recipient")
        .regex("^Nguyen"));

List<Order> found = mongoTemplate.find(query, Order.class);
```

Khai báo `Order` cần property `shippingAddressSnapshot` có subtype nhúng chứa `recipient`. Nếu dùng `@Field("ship_to")` cho địa chỉ, mapping query gắn `Order.class` có thể chuyển đường dẫn Java thành BSON `ship_to.recipient`.

### 12.2. Array chuỗi

Ví dụ `Product.tags = ["office", "Featured"]`:

```javascript
db.products.find({
  tags: { $regex: "^fea", $options: "i" }
});
```

MongoDB kiểm tra các phần tử chuỗi trong array, có thể khớp nếu **ít nhất một phần tử** phù hợp. Index trên `tags` sẽ thành **multikey index**, nhưng regexp không anchor hoặc case-insensitive vẫn có thể quét rộng.

### 12.3. Null, missing và BSON type

Regex query thông thường áp dụng lên **giá trị chuỗi**; field thiếu, `null` hoặc số BSON không phải chuỗi phù hợp không nên được giả định là được chuyển sang chuỗi tự động trước khi so sánh.

```javascript
db.products.find({
  name: { $type: "string", $regex: "^Ban" }
});
```

Nếu dữ liệu cũ từng lưu `name` thành object hoặc number, cần migration/validation. `$regex` không phải cơ chế làm sạch dữ liệu hay thay thế cho schema validation.

## 13. Phân trang, sort và kiểm soát tài nguyên

Một endpoint tìm kiếm có thể gọi:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Query search = Query.query(
    Criteria.where("active").is(true)
        .and("category").is("phu-kien")
        .and("nameSearch").regex("^ban"))
    .with(PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.asc("nameSearch"),
                Sort.Order.asc("id"))));

List<Product> page = mongoTemplate.find(search, Product.class);
```

Lưu ý:

- `PageRequest` bắt đầu từ **page 0**.
- Sử dụng sort có tie-breaker duy nhất như `id`/`_id` để ổn định thứ tự khi có nhiều sản phẩm cùng `nameSearch`.
- Với regex không anchor hoặc không có index, `limit(20)` không đồng nghĩa server chỉ kiểm tra đúng 20 document.
- Khi cần `Page<Product>` có `totalElements`, count query theo cùng filter có thể rất đắt. Với UX “xem thêm”, cân nhắc `Slice`, giới hạn kết quả hoặc cách duyệt bằng cursor.
- Khi sort theo `nameSearch` mà field BSON là `name_search`, dùng Java property với `MongoTemplate.find(..., Product.class)`; khi viết raw `mongosh` thì dùng tên BSON.

Với search UI, cân nhắc trả DTO gọn gồm `sku`, `name`, `price` và tránh nạp các object nhúng lớn không cần thiết. Projection làm giảm dữ liệu truyền đi nhưng không tự sửa một truy vấn regex scan toàn collection.

## 14. Reactive MongoDB và transaction

Nhánh reactive dùng `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository`. Filter BSON, quy tắc regex, collation và index **không thay đổi**, nhưng kết quả là publisher:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("active").is(true)
        .and("name").regex("^ban", "i"));

Flux<Product> products =
    reactiveMongoTemplate.find(query, Product.class);
```

Đoạn code giả định `reactiveMongoTemplate` đã được inject trong service. Khi dùng `Flux`, truy vấn được thực thi khi có subscriber. Không gọi `block()` trong event-loop WebFlux; backpressure của Reactor cũng không biến một regex scan rộng thành một truy vấn được index tối ưu.

Transaction có thể bảo đảm ghi `Order` và cập nhật `Product.stock` nhất quán trên topology hỗ trợ. Nhưng transaction không làm `$regex` nhanh hơn, không biến collation thành regex index, không bảo vệ endpoint khỏi biểu thức regex quá tốn CPU.

Nếu có chức năng tìm SKU **để kiểm tra trước khi insert**, phải dùng unique index hoặc điều kiện ghi nguyên tử để ngăn trùng; một query regex hay `exists` chạy trước insert đều có thể gặp race condition.

## 15. Kiểm thử bằng MongoDB thật

Một unit test chỉ kiểm tra `Pattern.compile(...)` của Java không chứng minh server MongoDB đã áp dụng cùng semantics, mapping `@Field` hoặc index. Nên chạy integration test với MongoDB thật hoặc Testcontainers trên database test cô lập.

### 15.1. Integration test đối chiếu case và dấu

```java
package com.example.minicommerce;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import com.example.minicommerce.domain.Product;

@SpringBootTest
class ProductRegexCriteriaIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void differentiatesRegexCaseCollationAndNormalizedPrefix() {
        List<String> ids = List.of(
            "regex-test-p1",
            "regex-test-p2",
            "regex-test-p3",
            "regex-test-p4");

        var raw = template.getCollection("products");
        Document fixtureFilter = new Document(
            "_id", new Document("$in", ids));
        raw.deleteMany(fixtureFilter);

        try {
            raw.insertMany(List.of(
                product(ids.get(0), "Ban phim Mini", "ban phim mini"),
                product(ids.get(1), "BAN PHIM Mini", "ban phim mini"),
                product(ids.get(2), "Bàn phím Mini", "ban phim mini"),
                product(ids.get(3), "Chuột Mini", "chuot mini")
            ));

            Query caseSensitive = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").regex("^Ban"));
            assertEquals(
                Set.of(ids.get(0)),
                resultIds(template.find(caseSensitive, Product.class)));

            Query ignoreCase = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").regex("^ban", "i"));
            assertEquals(
                Set.of(ids.get(0), ids.get(1)),
                resultIds(template.find(ignoreCase, Product.class)));

            Query equalityWithCollation = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").is("ban phim mini"))
                .collation(Collation.of("vi").strength(
                    Collation.ComparisonLevel.secondary()));
            assertEquals(
                Set.of(ids.get(0), ids.get(1)),
                resultIds(template.find(
                    equalityWithCollation, Product.class)));

            Query normalizedPrefix = Query.query(
                Criteria.where("id").in(ids)
                    .and("nameSearch").regex("^ban"));
            assertEquals(
                Set.of(ids.get(0), ids.get(1), ids.get(2)),
                resultIds(template.find(
                    normalizedPrefix, Product.class)));
        } finally {
            raw.deleteMany(fixtureFilter);
        }
    }

    private static Document product(
            String id, String name, String nameSearch) {
        return new Document("_id", id)
            .append("sku", id)
            .append("name", name)
            .append("name_search", nameSearch)
            .append("category", "phu-kien")
            .append("active", true);
    }

    private static Set<String> resultIds(List<Product> products) {
        return products.stream()
            .map(Product::getId)
            .collect(Collectors.toSet());
    }
}
```

Test chủ động insert raw BSON có `name_search` để kiểm tra ánh xạ `nameSearch` qua `@Field`. Để xác minh hiệu năng index cần benchmark riêng trên dataset lớn; test này xác minh **kết quả semantics**, không xác minh query plan.

Chỉ xóa fixture trong database test riêng và không chạy test trên production. Nếu một service khác đồng thời sửa các ID giống fixture, test có thể nhiễu; nên dùng database/collection cô lập theo test suite.

### 15.2. Ma trận test cần mở rộng

| Trường hợp | Kỳ vọng |
| --- | --- |
| `^Ban` phân biệt hoa/thường | Chỉ khớp tên bắt đầu đúng `Ban` |
| `^ban` với `i` | Khớp `Ban` và `BAN`, không tự coi `Bàn` là không dấu |
| Equality + collation strength 2 | Không phân biệt case, vẫn phân biệt dấu |
| Equality + collation strength 1 | Kiểm tra quy tắc bỏ dấu theo locale `vi` và input thực tế |
| `nameSearch` prefix `^ban` | Đọc đúng ba tên đã chuẩn hóa |
| Input regex chứa `.` hoặc `[` | Khi tìm literal, được escape, không mở rộng pattern |
| Input rỗng hoặc quá dài | API từ chối thay vì scan mọi document |
| BSON field `name_search` | Java dùng property `nameSearch`, raw query dùng tên BSON |
| Prefix index `{ name: 1 }` | `explain` đo index range và keys examined |
| Index collation `strength: 2` | Equality với đúng collation có khả năng dùng index |
| Regex `i` trên collation index | Không giả định tối ưu như equality |
| `name` thiếu hoặc null | Query không báo thành công sai; validation schema |
| Dataset lớn + phân trang | Có latency, size, sort và timeout trong giới hạn SLA |
| Reactive query | `StepVerifier` kiểm tra kết quả khi subscribe |

## 16. Sai lầm thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `^ban` không tìm được `Ban` | Regex mặc định phân biệt hoa/thường | Dùng `i` nếu cần, hoặc field chuẩn hóa |
| Bật `i` vẫn không tìm `Bàn` từ `ban` | Case-insensitive **không đồng nghĩa** bỏ dấu | Dùng chuẩn hóa hoặc collation equality phù hợp |
| Tạo index collation nhưng regex vẫn chậm | `$regex` không collation-aware | Không dựa vào collation index cho regex `i` |
| Regex chứa `Mini` scan rộng | Không có prefix cố định ở đầu | Dùng search tool chuyên dụng/đổi yêu cầu về prefix |
| `^Ban.*` chậm hơn `^Ban` | Wildcard thừa buộc nhiều xử lý hơn | Giữ prefix đơn giản khi cùng semantics |
| Query có `IXSCAN` nhưng chậm | Quét nhiều khóa index, filter kém chọn lọc | Xem `totalKeysExamined`/`nReturned` |
| Prefix trong index không cải thiện | Index không khớp filter/sort/collation | Kiểm tra plan và query shape thật |
| Equality không dùng case-insensitive index | Query không đặt cùng collation với index | Khớp `locale`/`strength` ở cả index và query |
| User nhập `.*` rồi trả quá nhiều dữ liệu | User input được diễn giải thành regex | `Pattern.quote`/chính sách ký tự, limit và validation |
| User gửi pattern làm CPU tăng cao | Regex pattern phức tạp, thiếu giới hạn | Chặn pattern tùy ý, timeout/rate limit |
| Sau đổi tên sản phẩm search không cập nhật | `name_search` không được đồng bộ | Cập nhật cả hai field, test migration/backfill |
| Query `nameSearch` không thấy BSON key | Trường được lưu tên `name_search` | Kiểm tra `@Field` và raw document |
| Sort tiếng Việt không đúng kỳ vọng | Chưa cấu hình collation, dùng sort binary | Chọn collation/ngôn ngữ, index tương ứng |
| Dùng `IgnoreCase` trên repository nhưng vẫn scan | Derived query dùng regex `i` | Kiểm tra BSON/index, đổi sang equality collation nếu phù hợp |
| Search UI tải quá nhiều document | Không limit, phân trang hoặc projection | Giới hạn size, dùng DTO, đo hiệu năng |

## 17. Bài tập thực hành

**Bài tập 1 — Cơ bản về regex.** Insert bốn `Product` fixture. Viết `mongosh` và `Criteria.regex(...)` để tìm: bắt đầu bằng `Ban`, chứa `Mini`, kết thúc bằng `Mini` và khớp chính xác `Ban phim Mini`. Ghi lại danh sách ID khớp.

**Bài tập 2 — Hoa thường và dấu tiếng Việt.** Viết `^ban` với `$options: "i"`. So sánh kết quả với equality có `collation: { locale: "vi", strength: 2 }`, rồi strength 1. Giải thích vì sao ba cách đó không có cùng semantics trong mọi trường hợp.

**Bài tập 3 — Regex injection.** Cho input `M.ni`, `.*`, `[abc` và chuỗi dài. Xây service coi input là **literal** qua `Pattern.quote`, giới hạn độ dài và số kết quả. Thử xác minh chuỗi có dấu chấm không hoạt động như wildcard.

**Bài tập 4 — Index prefix.** Tạo index `{ name: 1 }` và dataset đủ lớn. So sánh `^Ban`, `Ban`, `Mini$` và `^ban` với `i` bằng `explain("executionStats")`. Kiểm tra `indexBounds`, `totalKeysExamined` và `nReturned`.

**Bài tập 5 — Collation index.** Tạo index `{ name: 1 }` có `locale: "vi", strength: 2`. Dùng query **equality** với cùng collation và thử query regex `i`. Giải thích vì sao không nên lấy hiệu quả của equality suy ra cho regex.

**Bài tập 6 — Trường chuẩn hóa.** Viết hàm tạo `nameSearch` theo quy tắc của dự án. Backfill fixture và thử prefix `^ban` trên `name_search`, có filter `active` và `category`. Tạo compound index, xem query plan; kiểm tra xử lý chữ `đ`, dấu và ký hiệu đặc biệt.

**Bài tập 7 — Tích hợp API.** Xây endpoint tìm sản phẩm có danh mục, prefix và giới hạn trang. Whitelist sort, thêm `active`/tenant filter, DTO và giới hạn thời gian. Viết integration test với MongoDB thật hoặc Testcontainers.

**Bài tập mở rộng — Chọn công cụ tìm kiếm.** Phân tích yêu cầu autocomplete, tìm tên không dấu, fuzzy typo và xếp hạng theo độ liên quan. Đánh giá khi nào không còn phù hợp với MongoDB `$regex` thông thường, mà cần MongoDB Search hoặc hệ thống search chuyên dụng.

### Câu hỏi tự kiểm tra

1. Khác nhau giữa `^Ban`, `Ban` và `^Ban.*` là gì, cả về kết quả lẫn khả năng dùng index?
2. Tùy chọn `i` có giúp bỏ dấu tiếng Việt hay chỉ hỗ trợ case-insensitive?
3. Vì sao index có collation strength 2 không tự tối ưu truy vấn regex `i`?
4. Khi nào nên dùng equality + collation thay vì `$regex`?
5. `Criteria.regex(String, String)` và `Criteria.regex(Pattern)` giúp biểu diễn filter ra sao?
6. Vì sao user input phải được escape khi mục tiêu là tìm chuỗi literal?
7. `Pattern.quote` có đảm bảo mọi regex prefix được tối ưu bằng index hay không?
8. Tại sao `IXSCAN` chưa đủ để kết luận một query nhanh?
9. Chiến lược `nameSearch` có những chi phí dữ liệu/migration nào?
10. Những yếu tố nào cần xem thêm ngoài regex để bảo vệ hiệu năng: filter, sort, limit, projection, index, timeout?

**Kết quả mong đợi:** người học viết được regex trong `Criteria` và repository đúng nhu cầu, phân biệt rõ **case-insensitive regex** với **collation-based equality**, giải thích vì sao chỉ một số regex prefix dùng index hiệu quả và biết đo `explain`. Học viên cũng có thể thiết kế một field tìm kiếm chuẩn hóa an toàn, kiểm thử với dữ liệu tiếng Việt và chọn giải pháp search phù hợp khi dữ liệu tăng trưởng.

## Tài liệu tham khảo

- [MongoDB Manual — $regex](https://www.mongodb.com/docs/manual/reference/operator/query/regex/) — cú pháp, tùy chọn, PCRE2, prefix expression và khả năng dùng index.
- [MongoDB Manual — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — collation index và lý do `$regex` không hưởng lợi từ case-insensitive index.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale, strength và index matching.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Query`, `Criteria`, query matching, collation và index hints.
- [Spring Data MongoDB — Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html) — Java API `Collation` và cách gắn vào query/index.
- [Spring Data MongoDB API — Criteria](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html) — các overload `regex(String)`, `regex(String, options)` và `regex(Pattern)`.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — các từ khóa `StartingWith`, `Containing` và `IgnoreCase`.
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `winningPlan`, `indexBounds` và `executionStats`.
