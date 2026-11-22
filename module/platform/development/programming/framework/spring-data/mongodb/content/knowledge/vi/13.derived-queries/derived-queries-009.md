# Distinct, First, Top, count và exists

Trong **Spring Data MongoDB**, nhiều truy vấn phổ biến có thể được định nghĩa ngay trong tên phương thức của `MongoRepository`, không cần tự viết câu lệnh MongoDB. Spring Data phân tích cú pháp như `findFirstByStatusOrderByCreatedAtDesc`, `findTop3ByStatus`, `countByCategory` hoặc `existsBySku` để tạo truy vấn tương ứng. Đây là cơ chế **derived queries** (truy vấn suy diễn).

Các từ khóa **`Distinct`, `First`, `Top`, `count` và `exists`** cùng xuất hiện trong cơ chế đặt tên, nhưng phục vụ những mục tiêu rất khác nhau: tìm giá trị không trùng lặp, lấy một hoặc một số ít document đầu tiên, đếm document và kiểm tra sự tồn tại. Hiểu đúng chúng giúp ứng dụng tránh đọc thừa dữ liệu, kết luận sai vì thiếu sắp xếp, hoặc nhầm “đếm document” với “đếm số giá trị duy nhất”.

Bài học thuộc chương **Truy vấn suy diễn** của module `SPRING_DATA_MONGODB`. Ngoài cú pháp repository, ta sẽ dùng `MongoTemplate` khi cần **distinct một field cụ thể**, xem xét index trên MongoDB Server, phép ánh xạ Java/BSON, kiểm thử và chẩn đoán hiệu năng. Một số yêu cầu phức tạp hơn có thể cần aggregation; transaction và reactive access không làm thay đổi ý nghĩa của những phép truy vấn này.

Sau bài, bạn có thể:

- Viết phương thức repository dùng `First`, `Top`, `countBy` và `existsBy` với kiểu trả về phù hợp.
- Phân biệt `Distinct` trong tên truy vấn với thao tác MongoDB `distinct(field)`, nhất là trường hợp cần danh sách **giá trị duy nhất của một field**.
- Hiểu tác động của `OrderBy`, `Sort`, `Pageable`, kiểu dữ liệu BSON và index lên kết quả.
- Chọn `MongoTemplate.findDistinct` hoặc aggregation khi phương thức suy diễn không diễn đạt rõ yêu cầu.
- Kiểm thử trường hợp không có bản ghi, trùng giá trị, đồng hạng thời gian và dữ liệu thay đổi đồng thời.

## 1. Cách Spring Data đọc tên phương thức

Trong ví dụ đơn giản, một tên derived query có hai phần:

```text
findTop3ByStatusOrderByCreatedAtDescIdDesc
└─────┘  └─┘└──────┘└─────────────────────┘
 Chủ thể   By  Điều kiện      Sắp xếp tĩnh
 (Top3)           (Status)  (createdAt DESC, id DESC)
```

Phần **trước `By`** mô tả thao tác: `find`, `count`, `exists` và các giới hạn như `First`/`Top`; phần **sau `By`** biểu diễn điều kiện qua thuộc tính Java. `And`, `Or`, `GreaterThan`, `In`, `Between`... có thể tạo điều kiện phức hợp; `OrderBy` xác định thứ tự cố định. Chỉ phần tên được Spring Data nhận diện đúng mới tạo ra truy vấn; tên method dài **không tự đảm bảo câu lệnh tối ưu**.

| Tên phương thức | Ý định | Dạng thao tác ở MongoDB |
| --- | --- | --- |
| `findFirstByStatusOrderByCreatedAtDescIdDesc` | Lấy bản ghi đầu tiên theo thứ tự xác định | `find` + `sort` + `limit(1)` |
| `findTop3ByStatusOrderByCreatedAtDescIdDesc` | Lấy tối đa 3 bản ghi đầu | `find` + `sort` + `limit(3)` |
| `countByStatus` | Đếm document khớp điều kiện | Thao tác đếm theo filter |
| `existsBySku` | Có ít nhất một document khớp không? | Truy vấn kiểm tra tồn tại |
| `findDistinct...By...` | Yêu cầu distinct trong subject của tên method | **Cần xác định rõ “distinct theo field nào” và kiểm thử hành vi** |

**Lưu ý:** việc diễn giải derived query phụ thuộc metadata entity và phiên bản Spring Data. Phần Distinct là trường hợp dễ hiểu nhầm nhất: trong MongoDB, **distinct giá trị của một field** là một phép có field đích rõ ràng, không nên suy rằng cứ đặt `Distinct` vào tên method thì sẽ tự nhận được các category duy nhất. Ta sẽ dùng API rõ nghĩa cho nhu cầu đó ở mục 5.

## 2. Dữ liệu mẫu và Repository xuyên suốt

Giả sử collection `products` của một cửa hàng có các trường `sku`, `status`, `category`, `priceVnd`, `createdAt`. Mỗi sản phẩm có một ID chuỗi ổn định:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "products")
public record CatalogProduct(
        @MongoId String id,
        String sku,
        String status,
        String category,
        long priceVnd,
        Instant createdAt
) {}
```

`@MongoId` ở đây giúp giữ ID dạng `String` theo thiết kế. Thời gian `Instant` được ánh xạ sang kiểu ngày BSON thông qua converter mặc định; cần xác minh cấu hình và timezone khi ứng dụng sử dụng các kiểu ngày khác.

Dữ liệu minh họa trong `mongosh`:

```javascript
db.products.insertMany([
  { _id: "P-100", sku: "BK-001", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("80000"),
    createdAt: ISODate("2026-11-01T00:00:00Z") },
  { _id: "P-101", sku: "BK-002", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("90000"),
    createdAt: ISODate("2026-11-05T00:00:00Z") },
  { _id: "P-102", sku: "PN-001", status: "ACTIVE",
    category: "PEN", priceVnd: NumberLong("20000"),
    createdAt: ISODate("2026-11-05T00:00:00Z") },
  { _id: "P-103", sku: "PN-002", status: "DRAFT",
    category: "PEN", priceVnd: NumberLong("21000"),
    createdAt: ISODate("2026-11-09T00:00:00Z") },
  { _id: "P-104", sku: "OF-001", status: "ACTIVE",
    category: "OFFICE", priceVnd: NumberLong("150000"),
    createdAt: ISODate("2026-11-08T00:00:00Z") },
  { _id: "P-105", sku: "BK-003", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("120000"),
    createdAt: ISODate("2026-11-08T00:00:00Z") }
]);
```

> Dữ liệu trên chỉ dùng cho **database phát triển hoặc kiểm thử riêng**. `insertMany` sẽ lỗi nếu có `_id` trùng; không chạy lại trên một collection đã có những ID này nếu chưa chủ động reset dữ liệu mẫu trong môi trường cho phép.

Repository:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Optional<CatalogProduct>
    findFirstByStatusOrderByCreatedAtDescIdDesc(String status);

    List<CatalogProduct>
    findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);

    long countByStatus(String status);

    long countByStatusAndPriceVndGreaterThan(
            String status, long minPriceVnd);

    boolean existsBySku(String sku);

    boolean existsByCategoryAndStatus(String category, String status);
}
```

Các phương thức đều dùng **tên thuộc tính Java** (`createdAt`, `priceVnd`) chứ không phải tên viết tay của document, để Spring Data ánh xạ sang trường BSON theo metadata. Một typo trong tên thuộc tính hoặc cấu trúc method không được parser hỗ trợ thường làm bean repository không khởi tạo được, hoặc tạo query khác dự định.

## 3. `First`: lấy một bản ghi đầu tiên

`First` dùng khi chỉ cần **một** bản ghi, chẳng hạn sản phẩm ACTIVE mới nhất. Với phương thức:

```java
Optional<CatalogProduct>
findFirstByStatusOrderByCreatedAtDescIdDesc(String status);
```

Lời gọi:

```java
Optional<CatalogProduct> newest =
        repository.findFirstByStatusOrderByCreatedAtDescIdDesc("ACTIVE");

newest.ifPresent(p -> System.out.println(p.id()));
// Với dữ liệu mẫu: P-105.
```

Tương đương về ý nghĩa với MongoDB:

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(1);
```

Trong dữ liệu mẫu, cả `P-104` và `P-105` có `createdAt` là ngày 08/11. Sắp xếp thêm `_id` giảm dần giúp chọn **`P-105` một cách ổn định**. Nếu chỉ dùng `OrderByCreatedAtDesc` mà nhiều document có cùng thời gian, vị trí “đầu tiên” của các document đồng hạng **không được đảm bảo**.

### 3.1. Vì sao `First` không cần con số?

`findFirstBy...` và `findTopBy...` đều biểu diễn giới hạn mặc định **một kết quả**. Khi cần nhiều hơn, dùng số như `Top3` hoặc `First5`. Tên method có thể gắn `OrderBy` hoặc nhận một tham số `Sort` trong các biến thể thích hợp.

Không dùng `First` nếu yêu cầu là “lấy một kết quả bất kỳ nhưng mọi bản ghi đều quan trọng như nhau” mà không xác định ý nghĩa của chữ *đầu tiên*. Trong nghiệp vụ, nên định nghĩa rõ tiêu chí sắp xếp (mới nhất theo ngày tạo, lớn nhất theo doanh số, ...).

### 3.2. Kiểu trả về khi không tìm thấy

`Optional<CatalogProduct>` giúp biểu diễn **không có kết quả** bằng `Optional.empty()`. Đối với API, service có thể chuyển thành 404 khi lookup đối tượng bắt buộc, hoặc trả trạng thái bình thường khi “không có sản phẩm ACTIVE nào” là hợp lệ.

Đừng dùng `get()` trên `Optional` khi chưa kiểm tra tồn tại. Cũng đừng coi `First` là phép xác nhận **duy nhất**: nếu 100 sản phẩm khớp, nó vẫn trả **một** kết quả; muốn xác thực điều kiện unique phải dùng ràng buộc/index hoặc quy tắc riêng.

## 4. `Top`: lấy tối đa N bản ghi

`TopN` tương tự `FirstN`, nhưng ngữ nghĩa thường trực quan hơn khi cần bảng xếp hạng hoặc danh sách “N mới nhất”:

```java
List<CatalogProduct>
findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);
```

```java
List<CatalogProduct> latest3 =
        repository.findTop3ByStatusOrderByCreatedAtDescIdDesc("ACTIVE");

List<String> ids = latest3.stream()
        .map(CatalogProduct::id)
        .toList();
// Với dữ liệu mẫu: [P-105, P-104, P-102].
```

Tương đương:

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3);
```

Nếu chỉ có hai document khớp thì danh sách có **hai phần tử**, không bị thêm phần tử `null`. Nếu không có bản ghi thì trả danh sách rỗng. `Top3` giới hạn **số document kết quả**, không phải ba giá trị khác nhau của category và không tính số document khớp còn lại.

### 4.1. `First` và `Top` có khác về thực thi không?

`findFirstBy...` và `findTopBy...` đều giới hạn 1. `findFirst3By...` và `findTop3By...` đều giới hạn 3 khi được parser hỗ trợ. Chọn cách đặt tên dễ hiểu với nhóm; điều quan trọng hơn là **filter, thứ tự, giới hạn và index**.

Ví dụ khi muốn trả “năm sản phẩm ACTIVE có giá cao nhất”, hãy sắp theo giá và có tie-breaker:

```java
List<CatalogProduct>
findTop5ByStatusOrderByPriceVndDescIdAsc(String status);
```

Đừng nhầm `Top5` với số lượng phần tử mong muốn sau khi loại trùng category. Nó vẫn trả tối đa 5 **document**, kể cả tất cả cùng thuộc category BOOK.

### 4.2. `Top` không phải phân trang vô hạn

Một phương thức cố định `Top3` rất phù hợp với widget “3 mới nhất”, nhưng không nên dùng để phân trang hàng triệu sản phẩm. Với trang danh sách, hãy sử dụng `Pageable`, `Sort` và index, hoặc keyset pagination khi trang sâu. Nếu phối hợp từ khóa `Top` và `Pageable`, phải hiểu rõ phạm vi giới hạn và cách tính tổng theo phiên bản Spring Data — không nên mặc định nó tương đương truy vấn không giới hạn.

## 5. `Distinct`: phân biệt kết quả khác nhau và giá trị của một field

### 5.1. Câu hỏi nghiệp vụ phải chỉ rõ “duy nhất theo cái gì?”

Giả sử có ba sản phẩm thuộc category BOOK và một sản phẩm thuộc category PEN. Hai yêu cầu sau **khác nhau**:

- **Lấy danh sách sản phẩm không trùng ID:** các product đã có `_id` riêng; ba product BOOK vẫn là ba sản phẩm khác nhau.
- **Lấy danh sách category không trùng:** BOOK chỉ xuất hiện một lần, PEN một lần, OFFICE một lần.

Trong Spring Data, `Distinct` có thể xuất hiện trong **chủ thể** của derived method theo dạng `findDistinct...By...`. Nhưng trong MongoDB, lệnh `distinct` cần **chỉ rõ field** mà ta muốn lấy giá trị duy nhất. Đừng suy từ chữ `Distinct` trong tên một phương thức trả entity rằng repository sẽ tự chọn `category` để loại trùng.

Đặc biệt, `findDistinctByStatus("ACTIVE")` — dù được framework/parser của phiên bản đang dùng xử lý — **không phải một hợp đồng rõ ràng cho yêu cầu “trả các String category khác nhau”**. Khi mục tiêu là giá trị duy nhất trên một field, nên viết phép distinct có tên field tường minh và kiểm thử dữ liệu BSON thực tế.

### 5.2. Dùng `MongoTemplate.findDistinct` để lấy category duy nhất

Đây là cách diễn đạt rõ ràng, không phụ thuộc việc người đọc diễn giải phần subject của tên derived method:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Đoạn minh họa trong service đã có mongoTemplate được inject.
Query activeProducts = Query.query(
        Criteria.where("status").is("ACTIVE")
);

List<String> categories = mongoTemplate.findDistinct(
        activeProducts,
        "category",
        CatalogProduct.class,
        String.class
);
// Chứa BOOK, PEN, OFFICE; không dựa vào thứ tự trả về.
```

Tương đương về ý nghĩa với MongoDB:

```javascript
db.products.distinct("category", { status: "ACTIVE" });
// Ví dụ: ["BOOK", "OFFICE", "PEN"].
```

Tham số `"category"` là **field cần distinct**; `activeProducts` là filter. `CatalogProduct.class` cung cấp metadata để Spring Data mapping tên field và kiểu tương ứng; `String.class` là kiểu của các giá trị cần nhận.

**Không mặc định thứ tự kết quả của `distinct`.** Nếu giao diện cần danh sách alphabet, có thể sắp xếp kết quả tại Java cho tập giá trị nhỏ, hoặc thiết kế aggregation phù hợp khi cần sắp xếp/lọc/phân trang hoàn toàn ở server.

### 5.3. Các chi tiết dễ bị bỏ qua với distinct

- `distinct(field)` trả về **giá trị duy nhất của field**, không phải danh sách document gốc. Vì thế `List<String>` thích hợp với field chuỗi như `category`.
- Nếu field chứa **mảng**, MongoDB có thể trả mỗi phần tử duy nhất của mảng; cần kiểm thử với đúng cấu trúc dữ liệu.
- `null`, field vắng mặt và dữ liệu trộn kiểu có thể cho kết quả không như giả định. Hãy quy định schema và xử lý dữ liệu legacy trước khi kết luận “có bao nhiêu category”.
- `"BOOK"` và `"book"` có thể là hai giá trị khác nhau theo collation mặc định. Nếu muốn không phân biệt chữ hoa/thường, cần quy định collation hoặc chuẩn hóa dữ liệu một cách thống nhất.
- `distinct` không phải `unique index`. Lấy ra danh sách giá trị không trùng **không ngăn** database ghi những document trùng category hay SKU.
- Một tập giá trị distinct có cardinality quá cao có thể tốn tài nguyên hoặc vướng giới hạn kết quả; khi cần output lớn/phân trang, cân nhắc aggregation hoặc collection chuyên biệt.

### 5.4. Đếm số category duy nhất là yêu cầu khác với `countByStatus`

Với 5 document ACTIVE trong dữ liệu mẫu:

- `countByStatus("ACTIVE")` = **5 document**.
- Danh sách category ACTIVE duy nhất = **BOOK, PEN, OFFICE**, có **3 giá trị**.

Nếu muốn đếm số category không trùng trên server, có thể dùng aggregation:

```javascript
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  { $group: { _id: "$category" } },
  { $count: "distinctCategoryCount" }
]);
// Kết quả: { distinctCategoryCount: 3 }.
```

Đừng tự động hiểu các tên `countDistinct...By...` (nếu được parser xử lý) là “đếm số giá trị khác nhau của một field được suy từ tên method”. **Đếm document và đếm distinct field không đồng nghĩa**. Aggregation cho phép nêu chính xác field grouping và filter cần đếm.

## 6. `countBy`: đếm document phù hợp điều kiện

Trong repository:

```java
long countByStatus(String status);

long countByStatusAndPriceVndGreaterThan(
        String status, long minPriceVnd);
```

Ví dụ:

```java
long activeTotal = repository.countByStatus("ACTIVE");
// 5

long expensiveActive = repository
        .countByStatusAndPriceVndGreaterThan("ACTIVE", 100_000L);
// 2: P-104 và P-105.
```

Tương đương về ý nghĩa với lệnh đếm có filter trên server:

```javascript
db.products.countDocuments({ status: "ACTIVE" });
// 5

db.products.countDocuments({
  status: "ACTIVE",
  priceVnd: { $gt: NumberLong("100000") }
});
// 2
```

`GreaterThan` tương ứng **lớn hơn** (`$gt`), không bao gồm bằng. Nếu nghiệp vụ muốn “giá từ 100.000 trở lên”, dùng `GreaterThanEqual`/`$gte`. Những sai khác ở ranh giới ngưỡng là lỗi phổ biến khi tính thống kê.

### 6.1. `countBy` khác `findAll().size()`

Không nên tải toàn bộ document để đếm:

```java
// Tránh cho dữ liệu lớn:
long count = repository.findAll().stream()
        .filter(p -> "ACTIVE".equals(p.status()))
        .count();
```

Đoạn trên đọc tất cả document từ MongoDB về ứng dụng rồi mới lọc, gây tốn bộ nhớ, băng thông và CPU không cần thiết. `countByStatus` chuyển điều kiện đếm xuống server; response chỉ cần giá trị số, giúp ứng dụng tránh tải document.

Tuy nhiên **đếm có filter không mặc định có chi phí O(1)**. Server vẫn phải thực thi điều kiện, sử dụng index nếu hiệu quả, và có thể phải xem xét nhiều index key/document. Với tập dữ liệu lớn hoặc dashboard gọi rất thường xuyên, cần đo hiệu năng và cân nhắc summary/counter được duy trì có kiểm soát.

### 6.2. `count` chính xác theo filter khác với ước lượng số lượng

`countBy...` biểu diễn việc **đếm những document khớp predicate tại thời điểm truy vấn** theo hành vi truy vấn MongoDB. Nó không phải API ước lượng dựa trên metadata collection. MongoDB cũng có cơ chế estimated count cho những tình huống khác; không thay `countByStatus` bằng một phép đếm ước lượng nếu yêu cầu cần số document ACTIVE đúng theo filter.

Ngay cả khi một phép đếm phản ánh đúng các document thấy được tại thời điểm đọc, **dữ liệu có thể thay đổi sau khi đếm**. Không dùng một kết quả `countBy...` để khóa cứng điều kiện nghiệp vụ trong tương lai mà không có thao tác cập nhật có điều kiện/transaction phù hợp.

### 6.3. Dùng `MongoTemplate` khi điều kiện động hơn

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query filter = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("priceVnd").gte(100_000L)
);

long total = mongoTemplate.count(filter, CatalogProduct.class);
```

Đây là đoạn code trong service đã có `mongoTemplate`. `MongoTemplate` phù hợp khi filter được xây dựng có điều kiện theo nhiều tham số đầu vào; không nhất thiết tạo hàng chục tên method dài khó đọc.

## 7. `existsBy`: kiểm tra ít nhất một document có tồn tại

`existsBy` phù hợp cho câu hỏi đúng/sai như “SKU này đã xuất hiện chưa?” hoặc “có sản phẩm ACTIVE thuộc category PEN không?”:

```java
boolean existsBySku(String sku);
boolean existsByCategoryAndStatus(String category, String status);
```

Sử dụng:

```java
boolean skuExists = repository.existsBySku("PN-002");
// true: P-103, dù trạng thái là DRAFT.

boolean activePenExists =
        repository.existsByCategoryAndStatus("PEN", "ACTIVE");
// true: P-102.

boolean unknownExists = repository.existsBySku("UNKNOWN-SKU");
// false.
```

MongoDB có thể kiểm tra tồn tại bằng cách tìm một document khớp filter mà không cần tải toàn bộ kết quả:

```javascript
db.products.find(
  { sku: "PN-002" },
  { _id: 1 }
).limit(1);
```

Đây là **minh họa ngữ nghĩa**, không khẳng định mọi phiên bản Spring Data sinh chính xác lệnh trên. Điểm cần nhớ là `existsBy...` trả **boolean**, không trả entity, không trả số lượng và không chứng minh chỉ có đúng một bản ghi.

### 7.1. Khi nào nên dùng `existsBy` thay vì `countBy`?

Nếu chỉ cần biết “có ít nhất một bản ghi không”, `existsBy` diễn đạt ý định rõ hơn `countBy... > 0` và có thể tránh công việc đếm thêm. Nhưng không nên đưa ra kết luận tốc độ tuyệt đối khi chưa kiểm tra query/index trên MongoDB Server.

| Câu hỏi | Nên dùng | Giá trị trả về |
| --- | --- | --- |
| Có SKU `BK-001` không? | `existsBySku("BK-001")` | `boolean` |
| Có bao nhiêu sản phẩm ACTIVE? | `countByStatus("ACTIVE")` | `long` |
| Sản phẩm ACTIVE mới nhất là gì? | `findFirstByStatusOrderBy...` | `Optional<CatalogProduct>` |
| Ba sản phẩm ACTIVE mới nhất là gì? | `findTop3ByStatusOrderBy...` | `List<CatalogProduct>` |
| Các category ACTIVE khác nhau là gì? | `MongoTemplate.findDistinct(..., "category", ...)` | `List<String>` |

### 7.2. `existsBy` không thay thế unique index hoặc cập nhật nguyên tử

Giả sử hai request cùng chạy:

```java
if (!repository.existsBySku("BK-999")) {
    // Request khác có thể chèn BK-999 ngay tại đây.
    repository.insert(newProduct);
}
```

Cả hai request đều có thể thấy `false` rồi cùng chèn. Vì vậy **check-then-insert không phải bảo đảm duy nhất trong môi trường đồng thời**. Với SKU phải unique, tạo index:

```javascript
db.products.createIndex({ sku: 1 }, { unique: true });
```

Sau đó ứng dụng cần xử lý `DuplicateKeyException`/lỗi `E11000` khi insert xảy ra cạnh tranh. `existsBySku` có thể giúp hiển thị cảnh báo sớm trên UI, nhưng unique index trên server mới là lớp bảo vệ dữ liệu cuối cùng.

Tương tự, nếu cần “chỉ cho thêm sản phẩm khi còn dưới giới hạn N”, một bước `countBy...` hoặc `existsBy...` riêng không thể ngăn request khác cùng lúc làm điều kiện thay đổi. Cần thiết kế thao tác nguyên tử trên một document, version hoặc transaction khi nghiệp vụ đòi hỏi.

## 8. Kết hợp điều kiện, sắp xếp và kiểu trả về

Cơ chế derived query cho phép kết hợp nhiều keyword để mô tả nhu cầu cụ thể. Ví dụ cần ba sản phẩm ACTIVE thuộc category BOOK có giá cao nhất:

```java
import java.util.List;

List<CatalogProduct>
findTop3ByStatusAndCategoryOrderByPriceVndDescIdAsc(
        String status, String category);
```

Tương đương về ý nghĩa:

```javascript
db.products.find({
  status: "ACTIVE",
  category: "BOOK"
})
.sort({ priceVnd: -1, _id: 1 })
.limit(3);
```

Kết quả từ dữ liệu mẫu: `P-105` (120.000), `P-101` (90.000), `P-100` (80.000). Khi thêm `Or`, hãy cẩn thận với cách parser nhóm điều kiện; các truy vấn có ngoặc logic phức tạp thường rõ ràng hơn bằng `@Query`, `Criteria` hoặc aggregation thay vì tên method quá dài.

### 8.1. Sắp xếp động khi người dùng thay đổi tiêu chí

Nếu UI cho chọn “mới nhất” hoặc “giá cao nhất”, không nhất thiết tạo hai mươi phương thức `OrderBy...`. Có thể khai báo:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

// Phương thức bổ sung trong CatalogProductRepository:
List<CatalogProduct> findTop3ByStatus(String status, Sort sort);
```

Gọi:

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(Sort.Order.desc("priceVnd"),
                    Sort.Order.asc("id"));

List<CatalogProduct> mostExpensive =
        repository.findTop3ByStatus("ACTIVE", sort);
```

`Sort` sử dụng tên thuộc tính được mapping. Với input từ client, nên **whitelist các field được phép sắp xếp** (ví dụ `priceVnd` và `createdAt`), tránh mở ra đường dẫn trường tùy ý khiến truy vấn khó kiểm soát và index không phù hợp.

### 8.2. Kiểu trả về phải khớp ý nghĩa

| Phép truy vấn | Kiểu Java khuyến nghị | Không nên nhầm với |
| --- | --- | --- |
| `findFirst...` hoặc `findTop...` giới hạn 1 | `Optional<CatalogProduct>` | Bảo đảm bản ghi duy nhất |
| `findTop3...` | `List<CatalogProduct>` | Một trang có đủ dữ liệu tổng hoặc một tập đã loại trùng category |
| `countBy...` | `long` | `int` khi số document có thể lớn |
| `existsBy...` | `boolean` | Số lượng hoặc chính bản ghi |
| Distinct một field bằng template | `List<String>` nếu field String | `List<CatalogProduct>` |

Spring Data hỗ trợ nhiều hình dạng kết quả (entity, projection, `Page`, `Slice`, `Stream`, reactive publisher...), nhưng không phải tổ hợp phương thức và kiểu trả về nào cũng có cùng ngữ nghĩa/hiệu năng. Hãy chọn kiểu **phản ánh đúng API muốn trả**, xác minh các trường hợp 0, 1, N bản ghi trong test và đối chiếu phiên bản framework.

## 9. Index: để các phương thức suy diễn chạy tốt khi dữ liệu tăng

Derived query chỉ tạo **truy vấn**, không tự bảo đảm MongoDB Server chọn kế hoạch tối ưu. Với dữ liệu mẫu và màn hình minh họa, có thể bắt đầu từ các index:

```javascript
// First/Top: lọc ACTIVE, sắp xếp theo thời gian và ID.
db.products.createIndex({
  status: 1,
  createdAt: -1,
  _id: -1
});

// Count theo status và khoảng giá.
db.products.createIndex({
  status: 1,
  priceVnd: 1
});

// Exists theo SKU, đồng thời bảo đảm tính duy nhất nếu nghiệp vụ yêu cầu.
db.products.createIndex({ sku: 1 }, { unique: true });

// Distinct category có lọc theo status.
db.products.createIndex({
  status: 1,
  category: 1
});
```

Các index trên là **gợi ý theo truy vấn của ví dụ**, không phải danh sách phải tạo hết trong mọi dự án. Mỗi index tiêu tốn lưu trữ và làm tăng chi phí ghi. Ví dụ `{status: 1, priceVnd: 1}` có thể hỗ trợ filter kết hợp khoảng giá, nhưng không đồng nghĩa một phép `count` luôn miễn phí; phải đo trên server.

### 9.1. Kiểm tra truy vấn First/Top

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats");
```

Quan sát các trường/thông tin như kế hoạch `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, số document trả về và thời gian thực thi. Với chỉ sáu document mẫu, MongoDB có thể chọn collection scan dù index tồn tại; không nên dùng dữ liệu quá nhỏ để kết luận chiến lược index.

### 9.2. Kiểm tra count, exists và distinct

```javascript
db.products.find({ sku: "BK-001" }, { _id: 1 })
  .limit(1)
  .explain("executionStats");

db.products.find({
  status: "ACTIVE",
  priceVnd: { $gt: NumberLong("100000") }
}).explain("executionStats");

db.products.distinct("category", { status: "ACTIVE" });
```

Query cuối dùng `distinct` nên cách thu thập thông tin explain khác nhau theo MongoDB Server và API; khi chẩn đoán có thể dùng command explain thích hợp hoặc xây aggregation tương đương để khảo sát dữ liệu. Không coi output của `find` ở giữa là **bằng chứng chi phí đếm chính xác**, vì engine có thể thực thi phép count theo kế hoạch khác. Mục đích các ví dụ là **kiểm tra filter và chỉ số sử dụng index**, sau đó đo trực tiếp thao tác thật từ ứng dụng.

### 9.3. Thứ tự trường trong index ghép có ý nghĩa

Index `{status: 1, createdAt: -1, _id: -1}` phù hợp với truy vấn lọc `status` bằng equality rồi sắp xếp theo `createdAt`/`_id`. Nếu `status` có ít giá trị (độ chọn lọc thấp), MongoDB vẫn cân nhắc chi phí quét và số document cần trả. Với truy vấn `Top3`, việc có thứ tự từ index có thể giúp server ngừng sớm sau khi đủ kết quả.

Đừng thêm `_id` làm tie-breaker chỉ vì “ID đã có index nên miễn phí”: index ghép là một cấu trúc riêng, việc bổ sung `_id` có chi phí dung lượng/ghi. Chọn nó khi cần thứ tự ổn định và đo trade-off.

## 10. Reactive access và giới hạn đồng thời

Spring Data MongoDB hỗ trợ `ReactiveMongoRepository` với các phương thức suy diễn tương tự nhưng trả về `Mono` hoặc `Flux`. Ví dụ:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Mono<CatalogProduct>
    findFirstByStatusOrderByCreatedAtDescIdDesc(String status);

    Flux<CatalogProduct>
    findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsBySku(String sku);
}
```

`Mono<CatalogProduct>` có thể hoàn thành mà không có giá trị khi không tìm thấy document; `Flux<CatalogProduct>` có thể phát từ 0 đến 3 document trong ví dụ `Top3`. Các publisher chỉ được thực thi khi có subscription theo mô hình Reactive Streams.

**Reactive không thay đổi filter, giới hạn hay tính nhất quán của dữ liệu**. Nó không tự thêm index, không tự bảo đảm thứ tự nếu bỏ `OrderBy`, và không loại bỏ race condition của `existsBySku` rồi insert. Nếu cần viết logic tạo mới có ràng buộc duy nhất, vẫn phải dựa vào unique index và xử lý lỗi ghi.

## 11. Kiểm thử trên MongoDB thực

Để kiểm tra parser derived query, cách ánh xạ Java/BSON, thứ tự và kết quả count/exists, nên dùng **`@DataMongoTest` với MongoDB test instance cô lập**, chẳng hạn Testcontainers. Mock repository chỉ chứng minh service gọi một method, không kiểm tra query thật được sinh ra hoặc số document khớp.

Test minh họa cho Spring Boot 3.x dùng `CatalogProduct` và `CatalogProductRepository` ở mục 2:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class DerivedQueryKeywordsTest {

    @Autowired CatalogProductRepository repository;
    @Autowired MongoTemplate template;

    @BeforeEach
    void seed() {
        // Chỉ thực hiện trên MongoDB test được cô lập.
        repository.deleteAll();
        repository.insert(List.of(
            p("P-100", "BK-001", "ACTIVE", "BOOK",   80_000, "2026-11-01"),
            p("P-101", "BK-002", "ACTIVE", "BOOK",   90_000, "2026-11-05"),
            p("P-102", "PN-001", "ACTIVE", "PEN",    20_000, "2026-11-05"),
            p("P-103", "PN-002", "DRAFT",  "PEN",    21_000, "2026-11-09"),
            p("P-104", "OF-001", "ACTIVE", "OFFICE",150_000, "2026-11-08"),
            p("P-105", "BK-003", "ACTIVE", "BOOK",  120_000, "2026-11-08")
        ));
    }

    private CatalogProduct p(String id, String sku, String status,
                             String category, long price, String date) {
        return new CatalogProduct(
                id, sku, status, category, price,
                Instant.parse(date + "T00:00:00Z"));
    }

    @Test
    void firstAndTopHaveStableOrder() {
        assertThat(repository
                .findFirstByStatusOrderByCreatedAtDescIdDesc("ACTIVE")
                .map(CatalogProduct::id))
                .contains("P-105");

        List<String> topIds = repository
                .findTop3ByStatusOrderByCreatedAtDescIdDesc("ACTIVE")
                .stream().map(CatalogProduct::id).toList();
        assertThat(topIds).containsExactly(
                "P-105", "P-104", "P-102");
    }

    @Test
    void countAndExistsDoNotNeedToLoadAllProducts() {
        assertThat(repository.countByStatus("ACTIVE")).isEqualTo(5);
        assertThat(repository
                .countByStatusAndPriceVndGreaterThan("ACTIVE", 100_000L))
                .isEqualTo(2);
        assertThat(repository.existsBySku("PN-002")).isTrue();
        assertThat(repository.existsBySku("INVALID")).isFalse();
        assertThat(repository
                .existsByCategoryAndStatus("PEN", "ACTIVE")).isTrue();
    }

    @Test
    void distinctCategoriesAreNotDistinctProducts() {
        Query query = Query.query(Criteria.where("status").is("ACTIVE"));
        List<String> categories = template.findDistinct(
                query, "category", CatalogProduct.class, String.class);

        assertThat(categories)
                .containsExactlyInAnyOrder("BOOK", "PEN", "OFFICE");
    }
}
```

Đoạn test trên cần có phụ thuộc test JUnit/AssertJ/Spring Boot Test và **MongoDB Server thật cho môi trường test**. `@DataMongoTest` không tự bảo đảm khởi tạo một MongoDB Server trong mọi dự án. Không chạy `repository.deleteAll()` trên database chia sẻ hay production.

### 11.1. Những test biên nên bổ sung

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không có sản phẩm `ARCHIVED` | `findFirstByStatus...` trả `Optional.empty()`; `findTop3...` trả danh sách rỗng |
| Chỉ có 2 sản phẩm khớp | `Top3` trả 2 document, không thêm `null` |
| Hai sản phẩm có cùng `createdAt` | Khóa phụ `_id` quyết định thứ tự ổn định |
| Nhiều sản phẩm cùng category | Distinct field chỉ trả category đó một lần |
| Một document thiếu `category` | Xác minh chính sách dữ liệu thiếu/null và kết quả distinct |
| Chuỗi `BOOK` và `book` | Kiểm tra collation/chuẩn hóa chữ hoa-thường |
| Giá đúng bằng 100.000 | `GreaterThan` không tính; `GreaterThanEqual` có tính |
| Có một SKU trùng do dữ liệu cũ | `existsBySku` vẫn là true, không chứng minh duy nhất |
| Hai request tạo cùng SKU đồng thời | Unique index ngăn ghi trùng; service xử lý xung đột |
| Tập dữ liệu lớn | Kiểm tra index, latency, số document quét cho query quan trọng |

Kiểm thử kết quả là bước đầu; để khẳng định hiệu năng, cần quan sát command thật của driver, `explain` trên server, thời gian thực thi và kích thước dữ liệu trả về. Tránh đưa toàn bộ query chứa thông tin nhạy cảm vào production log.

## 12. Những nhầm lẫn phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `findFirstByStatus` không có `OrderBy` để lấy “mới nhất” | Không có thứ tự xác định; kết quả có thể đổi khi dữ liệu hoặc kế hoạch truy vấn đổi | Thêm `OrderByCreatedAtDesc` và tie-breaker như `IdDesc` |
| Dùng `Top3` rồi nghĩ đã lấy đủ tất cả sản phẩm ACTIVE | `Top3` chỉ giới hạn tối đa 3 document | Dùng `countBy` riêng nếu cần tổng; dùng phân trang nếu cần danh sách đầy đủ |
| Dùng `Distinct` rồi mặc định nhận category không trùng | Distinct trên document khác với distinct **giá trị của một field** | Chỉ rõ field qua `findDistinct`/aggregation và kiểm thử kết quả |
| Coi `countByStatus` là số category ACTIVE | Phép count đếm document phù hợp filter | Dùng `distinct("category")` hoặc aggregation `$group` khi cần số category duy nhất |
| Dùng `findAll().size()` để đếm | Tải toàn bộ document không cần thiết | `countBy...` hoặc `MongoTemplate.count` |
| Dùng `countBy... > 0` trong mọi trường hợp tồn tại | Có thể thực hiện công việc đếm thừa | `existsBy...` diễn đạt đúng mục đích |
| Dùng `existsBySku` như ràng buộc unique | Hai request có thể cùng thấy false rồi insert | Unique index tại MongoDB Server và xử lý duplicate key |
| Tưởng `First` chỉ trả kết quả nếu duy nhất | Nhiều document khớp vẫn trả một | Thiết kế unique constraint nếu nghiệp vụ yêu cầu duy nhất |
| Không phân biệt `GreaterThan` và `GreaterThanEqual` | Sai kết quả ở ngưỡng giá | Kiểm thử giá bằng ngưỡng để phân biệt `$gt` và `$gte` |
| Trả trực tiếp `List` không giới hạn cho một bảng lớn | Dễ đọc quá nhiều document và tăng độ trễ | Dùng `TopN` cho widget giới hạn; `Pageable`/cursor cho danh sách lớn |
| Chỉ nhìn tên method, không kiểm tra index | Query đúng chức năng vẫn có thể chậm | Đo `explain` và tạo index theo filter/sort thực tế |
| Ghép field user tùy ý vào `Sort` hoặc query | Khó kiểm soát hiệu năng và hợp đồng API | Chỉ cho phép field hợp lệ, xác thực tham số |

## 13. Bài tập áp dụng và đáp án tham khảo

Một hệ thống quản lý đơn hàng có collection `orders` với các trường `_id`, `customerId`, `status`, `totalVnd` và `createdAt`. Các yêu cầu:

1. Lấy **đơn hàng đã giao gần nhất** của một khách hàng; nếu không có thì kết quả vắng mặt.
2. Lấy **5 đơn hàng giá trị cao nhất** của khách hàng theo `totalVnd`; trường hợp bằng tổng tiền thì ưu tiên `_id` tăng dần.
3. Đếm số đơn có `status = "PAID"` và `totalVnd` từ 1 triệu đồng trở lên.
4. Kiểm tra xem một khách hàng đã từng có đơn `DELIVERED` hay chưa.
5. Lấy danh sách **các trạng thái khác nhau** mà khách hàng đó từng có, không tải toàn bộ đơn hàng về bộ nhớ Java.

Một bộ phương thức repository có thể viết:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {

    Optional<Order>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDescIdDesc(
            String customerId, String status);

    List<Order>
    findTop5ByCustomerIdOrderByTotalVndDescIdAsc(
            String customerId);

    long countByStatusAndTotalVndGreaterThanEqual(
            String status, long minimum);

    boolean existsByCustomerIdAndStatus(
            String customerId, String status);
}
```

Ở đây `Order` là entity minh họa được ánh xạ tới collection `orders` với các thuộc tính đúng tên trong phương thức; cần định nghĩa class/import và cấu hình database khi đưa vào dự án. Với yêu cầu số 5, `MongoTemplate` nêu field distinct rõ ràng:

```java
Query query = Query.query(
        Criteria.where("customerId").is(customerId)
);

List<String> statuses = mongoTemplate.findDistinct(
        query, "status", Order.class, String.class);
```

Đoạn trên là phần thân phương thức service đã inject `mongoTemplate`, cần import `Query`, `Criteria` và `List`. Các giá trị status được trả về **không có thứ tự được bảo đảm**; sắp xếp ở tầng Java nếu cần trình bày.

Index khởi đầu để cân nhắc:

```javascript
// Truy vấn đơn đã giao gần nhất của một khách hàng:
db.orders.createIndex({
  customerId: 1, status: 1, createdAt: -1, _id: -1
});

// Top 5 theo tổng giá trị trong phạm vi khách hàng:
db.orders.createIndex({
  customerId: 1, totalVnd: -1, _id: 1
});

// Count PAID và lọc theo ngưỡng giá trị:
db.orders.createIndex({ status: 1, totalVnd: 1 });
```

Đây là phương án sơ bộ dựa trên các query cụ thể; số lượng và thứ tự index cuối cùng phải được xác minh bằng truy vấn thực tế và thống kê dữ liệu. Câu hỏi thêm cho bài tập: nếu `totalVnd` được lưu bằng BSON String thay vì số nguyên, kết quả `GreaterThanEqual` và sắp xếp có còn đúng như kỳ vọng không? **Không**: kiểu dữ liệu quyết định so sánh trên server; phải kiểm tra BSON type và chuẩn hóa mapping.

### Checklist trước khi đưa derived query vào ứng dụng

1. **Mục tiêu là một document, N document, số lượng, tồn tại hay giá trị field duy nhất?** Chọn `First`, `Top`, `countBy`, `existsBy` hoặc distinct theo mục tiêu.
2. **“Đầu tiên” theo tiêu chí gì?** Có `OrderBy` và khóa phụ để xử lý đồng hạng chưa?
3. **Distinct của field nào?** Có cần xử lý `null`, array, chữ hoa–thường hoặc collation không?
4. **Điều kiện so sánh có đúng ranh giới không?** `GreaterThan` khác `GreaterThanEqual`.
5. **Kiểu trả về có diễn đạt trường hợp rỗng không?** Dùng `Optional`/`List`/`boolean`/`long` thích hợp.
6. **Index hỗ trợ filter và sort chưa?** Đã đo `explain` trên dữ liệu đại diện chưa?
7. **Kết quả count/exists có bị thay đổi bởi ghi đồng thời không?** Có đang dùng chúng sai như một ràng buộc dữ liệu không?
8. **Tên derived method có còn dễ đọc không?** Nếu quá dài hoặc yêu cầu aggregation, chuyển sang `@Query`/`MongoTemplate`.
9. **Có dùng reactive không?** Cần đúng kiểu `Mono`/`Flux` và không chặn event loop.
10. **Đã có integration test trên MongoDB thật chưa?** Kiểm tra các kết quả 0/1/N, dữ liệu trùng, sorting và kiểu BSON.

**Quy tắc ghi nhớ:** `First`/`Top` chọn **một hoặc vài document theo thứ tự**; `countBy` đếm **document**; `existsBy` kiểm tra **ít nhất một document**; còn distinct một field dùng để lấy **giá trị không trùng**. Derived query giúp viết CRUD ngắn gọn, nhưng vẫn phải chọn **kiểu trả về, sort, index, ràng buộc dữ liệu và kiểm thử** đúng với MongoDB Server.
