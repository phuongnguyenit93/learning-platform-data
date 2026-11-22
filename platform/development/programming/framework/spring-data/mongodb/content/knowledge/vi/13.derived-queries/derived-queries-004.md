# So sánh bằng, khác, lớn hơn, nhỏ hơn và khoảng giá trị

Trong **Spring Data MongoDB**, bạn có thể tạo truy vấn chỉ bằng cách khai báo tên phương thức trên interface repository. Chẳng hạn, `findByCategory` biểu diễn so sánh bằng, `findByPriceCentsGreaterThan` biểu diễn lớn hơn, còn `findByPriceCentsBetween` biểu diễn một khoảng giá trị. Spring Data phân tích tên phương thức, ánh xạ property của entity sang field BSON và tạo truy vấn MongoDB khi gọi phương thức.

Bài học thuộc chương **Truy vấn suy diễn** của module `SPRING_DATA_MONGODB`. Ngoài việc truy vấn qua repository, kiến thức này còn giúp bạn dùng `MongoTemplate`, đối chiếu lệnh MongoDB thật, thiết kế index, xử lý ngày giờ, viết kiểm thử biên và chẩn đoán truy vấn chậm. Những thao tác này có thể dùng trong hệ thống ánh xạ document, aggregation, transaction và reactive access.

Điểm quan trọng nhất là **hiểu rõ ranh giới của phép so sánh**. Tên phương thức nhìn rất giống ngôn ngữ tự nhiên nhưng khác biệt giữa `GreaterThan` và `GreaterThanEqual`, giữa `Between(a, b)` và `Between(Range.closed(a, b))`, hay giữa `Not(value)` và `NotNull()` có thể làm sai tập kết quả.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Is`/`Equals`, `Not`, `GreaterThan`, `GreaterThanEqual`, `LessThan`, `LessThanEqual`, `Between`.
2. Viết tên phương thức repository hợp lệ và dự đoán toán tử MongoDB tương ứng: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`.
3. Xác định đúng **biên mở** và **biên đóng**; dùng `org.springframework.data.domain.Range` để thể hiện khoảng một cách tường minh.
4. Kết hợp điều kiện bằng `And`, `Or`, thêm sắp xếp, giới hạn và phân trang.
5. Phân biệt `null`, field không tồn tại, chuỗi và số, và những trường hợp phép so sánh không trả kết quả như kỳ vọng.
6. Xây dựng bộ lọc khoảng thời gian theo múi giờ và dùng biên cuối **loại trừ** để tránh bỏ sót dữ liệu.
7. Viết truy vấn tương đương bằng `MongoTemplate` hoặc `@Query` khi tên phương thức quá dài hoặc thiếu linh hoạt.
8. Kiểm thử các giá trị sát biên, sử dụng index và `explain` để đánh giá hiệu năng.

## 2. Cơ chế phân tích tên phương thức

Xét ví dụ:

```java
List<Product> findByCategoryAndPriceCentsGreaterThan(
        String category, long threshold);
```

Spring Data tách tên phương thức thành:

```text
find        By   Category       And   PriceCents       GreaterThan
│           │   │               │     │                │
Chủ đề      │   Property 1      AND   Property 2       Toán tử so sánh
            Ranh giới chủ đề/điều kiện
```

Logic tương đương tại MongoDB:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gt: 100000 }
});
```

Một số nguyên tắc:

- Phần sau `By` tham chiếu **tên property Java** của entity, chẳng hạn `priceCents`, không nhất thiết là tên field BSON nếu dùng `@Field`.
- Các toán tử suy diễn được dịch sang truy vấn phụ thuộc vào **datastore**. Tên `Between` trên một hệ quản trị khác không nhất thiết có chính xác quy tắc biên của MongoDB.
- Phương thức repository được Spring Data xử lý khi tạo repository proxy, không phải bạn phải tự viết implementation cho từng phương thức.
- Sai tên property hoặc không phân tích được phương thức có thể làm application context khởi động lỗi; cần chạy integration test để kiểm chứng mapping.
- Predicate được thực thi tại MongoDB Server. Java không tự lọc toàn bộ collection trong bộ nhớ đối với các phương thức repository thông thường.

`MongoRepository` cho truy vấn đơn giản, dễ tái sử dụng; `MongoTemplate` phù hợp hơn khi cần bộ lọc phát sinh theo nhiều tham số tùy chọn, cần điều kiện phức tạp hoặc yêu cầu kiểm soát query rõ ràng.

## 3. Dữ liệu xuyên suốt bài học

Giả sử hệ thống có collection `catalog_products`. Mỗi sản phẩm có danh mục, giá lưu theo **đơn vị tiền nhỏ nhất**, số lượng tồn, trạng thái, thời điểm xuất bản và thời hạn bảo hành (có thể chưa có).

Entity Java:

```java
package dev.learning.catalog;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("catalog_products")
public record Product(
        @Id String id,
        String category,
        long priceCents,
        int stock,
        String status,
        Instant publishedAt,
        Integer warrantyMonths) {
}
```

Dùng kiểu nguyên `long` cho `priceCents` giúp ví dụ so sánh số nguyên nhất quán và tránh phụ thuộc vào biểu diễn `BigDecimal`/`Decimal128`. Nếu nghiệp vụ yêu cầu tính toán thập phân, bạn vẫn cần chọn BSON representation đúng cách.

Dữ liệu thử minh họa:

| `_id` | `category` | `priceCents` | `status` | `warrantyMonths` |
| --- | --- | ---: | --- | --- |
| `book-099` | books | 99 000 | ACTIVE | Không có field |
| `book-100` | books | 100 000 | ACTIVE | 0 |
| `book-150` | books | 150 000 | ACTIVE | 12 |
| `book-200` | books | 200 000 | ARCHIVED | 24 |
| `book-201` | books | 201 000 | ACTIVE | 12 |
| `device-150` | devices | 150 000 | ACTIVE | 12 |

Bạn có thể chèn dữ liệu để thử bằng `mongosh`:

```javascript
db.catalog_products.insertMany([
  {
    _id: "book-099", category: "books", priceCents: NumberLong("99000"),
    stock: 6, status: "ACTIVE", publishedAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "book-100", category: "books", priceCents: NumberLong("100000"),
    stock: 7, status: "ACTIVE", warrantyMonths: 0,
    publishedAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: "book-150", category: "books", priceCents: NumberLong("150000"),
    stock: 8, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: "book-200", category: "books", priceCents: NumberLong("200000"),
    stock: 9, status: "ARCHIVED", warrantyMonths: 24,
    publishedAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: "book-201", category: "books", priceCents: NumberLong("201000"),
    stock: 2, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: "device-150", category: "devices", priceCents: NumberLong("150000"),
    stock: 4, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-06T08:00:00Z")
  }
]);
```

Dùng **database thử nghiệm riêng** vì `insertMany` tạo document thật và sẽ báo trùng `_id` nếu chạy lại trên cùng collection chưa được dọn. Với Java, `priceCents` là `long` nên dữ liệu BSON `NumberLong` có ý nghĩa rõ ràng.

## 4. Khai báo repository với các phép so sánh

```java
package dev.learning.catalog;

import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Range;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    // Bằng / khác
    List<Product> findByCategory(String category);
    List<Product> findByCategoryIs(String category);
    List<Product> findByStatusNot(String status);

    // Ngưỡng giá
    List<Product> findByPriceCentsGreaterThan(long value);
    List<Product> findByPriceCentsGreaterThanEqual(long value);
    List<Product> findByPriceCentsLessThan(long value);
    List<Product> findByPriceCentsLessThanEqual(long value);

    // Khoảng giá
    List<Product> findByPriceCentsBetween(long lower, long upper);
    List<Product> findByPriceCentsBetween(Range<Long> range);

    // Kết hợp điều kiện
    List<Product> findByCategoryAndPriceCentsBetween(
            String category, Range<Long> range);

    // So sánh ngày giờ
    List<Product> findByPublishedAtAfter(Instant moment);
    List<Product> findByPublishedAtBefore(Instant moment);
    List<Product> findByPublishedAtBetween(Range<Instant> range);

    // Null/missing
    List<Product> findByWarrantyMonthsIsNull();
    List<Product> findByWarrantyMonthsIsNotNull();
    List<Product> findByWarrantyMonthsExists(boolean exists);
}
```

Trong các phần tiếp theo, mỗi toán tử được giải thích cùng truy vấn MongoDB và tập kết quả trên dữ liệu `books`. Khi bạn muốn chỉ lấy `books`, thêm điều kiện `Category` hoặc dùng `@Query` tương đương, bởi các phương thức `findByPriceCents…` độc lập sẽ trả cả danh mục `devices`.

## 5. So sánh bằng: Is, Equals hoặc không có hậu tố

Ba cách viết thông dụng:

```java
List<Product> findByCategory(String category);
List<Product> findByCategoryIs(String category);
List<Product> findByCategoryEquals(String category);
```

Đều biểu diễn **so sánh bằng** (dạng equality) đối với `category`. Với tham số `"books"`, query tương đương:

```javascript
db.catalog_products.find({ category: "books" });

// Biểu diễn tường minh về ý nghĩa:
db.catalog_products.find({ category: { $eq: "books" } });
```

Dữ liệu `books` trả về `book-099`, `book-100`, `book-150`, `book-200` và `book-201`.

**Cần lưu ý:**

- So sánh chuỗi mặc định có thể **phân biệt chữ hoa/thường**, tùy collation được sử dụng. `"books"` thường khác `"BOOKS"`.
- Nếu query theo `@Id String` có giá trị trông như ObjectId, Spring Data có thể chuyển kiểu khi ánh xạ `_id`. Phải xác minh BSON type thực tế.
- So sánh bằng với toàn bộ **subdocument** có thể phụ thuộc thứ tự field và cấu trúc BSON; nhiều trường hợp nên so sánh một hoặc vài **property con** thay vì cả object.
- Khi cần so sánh không phân biệt hoa/thường, Spring Data hỗ trợ `IgnoreCase` trên một số loại property, nhưng cần đánh giá query thực sự tạo ra, index và collation.

Ví dụ so sánh field con:

```java
// Nếu Product có thuộc tính supplier với property country:
List<Product> findBySupplierCountry(String country);
```

Với đường property lồng nhau, đảm bảo tên method được parser hiểu đúng; khi có tên lồng nhau dễ nhập nhằng, bạn có thể dùng dấu gạch dưới theo quy ước Spring Data để đặt ranh giới traversal (ví dụ `findBySupplier_Country`).

## 6. So sánh khác: Not và ngữ nghĩa $ne

```java
List<Product> findByStatusNot(String status);
```

Gọi:

```java
repository.findByStatusNot("ARCHIVED");
```

Truy vấn logic:

```javascript
db.catalog_products.find({
  status: { $ne: "ARCHIVED" }
});
```

Kết quả có những document có `status` khác `ARCHIVED`, gồm các sản phẩm `ACTIVE` trong tập mẫu.

### 6.1. Điểm dễ sai: $ne khớp cả field vắng mặt

Với giá trị khác `null`, toán tử `$ne` cũng có thể khớp những document **không có field** được xét.

```javascript
db.catalog_products.insertOne({
  _id: "book-missing-status",
  category: "books",
  priceCents: NumberLong("130000"),
  stock: 1,
  publishedAt: ISODate("2026-11-07T08:00:00Z")
});

db.catalog_products.find({
  status: { $ne: "ARCHIVED" }
});
// Có thể bao gồm "book-missing-status" dù document không có status.
```

Nếu nghiệp vụ “khác ARCHIVED” còn yêu cầu field `status` **phải tồn tại và khác null**, hãy biểu đạt cả hai điều kiện. Một cách rõ ràng là dùng `$nin` để loại các giá trị không hợp lệ và `$exists` để loại document thiếu field:

```javascript
db.catalog_products.find({
  status: { $nin: ["ARCHIVED", null], $exists: true }
});
```

Trong Spring Data, khi điều kiện phức tạp hoặc phải phân biệt tồn tại/không null, dùng `MongoTemplate` hoặc `@Query` để thể hiện ý định rõ ràng. Không suy từ `findByStatusNot("ARCHIVED")` rằng tất cả kết quả đều có status hợp lệ.

### 6.2. Not(null) khác IsNotNull như thế nào?

Spring Data hỗ trợ `IsNull` / `IsNotNull` và `Not`:

```java
List<Product> findByWarrantyMonthsIsNull();
List<Product> findByWarrantyMonthsIsNotNull();
List<Product> findByWarrantyMonthsNot(Integer value);
```

Các trường hợp BSON:

| Query | Diễn giải |
| --- | --- |
| `{ warrantyMonths: null }` | Khớp field bằng null **hoặc không có field**. |
| `{ warrantyMonths: { $ne: null } }` | Khớp field **tồn tại và khác null**. |
| `{ warrantyMonths: { $exists: true } }` | Khớp field có mặt, kể cả có giá trị null. |
| `{ warrantyMonths: { $exists: false } }` | Chỉ khớp field vắng mặt. |
| `{ warrantyMonths: { $ne: 12 } }` | Khớp các giá trị khác 12; thường gồm field null/missing. |

Ví dụ `findByWarrantyMonthsIsNull()` trả `book-099` nếu field bị thiếu; `findByWarrantyMonthsIsNotNull()` trả các document có bảo hành 0, 12, 24. Phân biệt dữ liệu **chưa biết**, **không áp dụng** và giá trị số 0 ngay trong mô hình nghiệp vụ.

## 7. Lớn hơn và lớn hơn hoặc bằng

| Phương thức suy diễn | Toán tử MongoDB | Điều kiện logic |
| --- | --- | --- |
| `findByPriceCentsGreaterThan(x)` | `$gt` | `priceCents > x` |
| `findByPriceCentsGreaterThanEqual(x)` | `$gte` | `priceCents >= x` |

Với `x = 150000`:

```java
List<Product> strict =
        repository.findByPriceCentsGreaterThan(150_000L);

List<Product> inclusive =
        repository.findByPriceCentsGreaterThanEqual(150_000L);
```

MongoDB tương đương:

```javascript
db.catalog_products.find({
  priceCents: { $gt: NumberLong("150000") }
});

db.catalog_products.find({
  priceCents: { $gte: NumberLong("150000") }
});
```

Trong danh mục `books`:

- `$gt: 150000` chỉ gồm `book-200` và `book-201`.
- `$gte: 150000` gồm `book-150`, `book-200` và `book-201`.

Khi gọi hai phương thức như trong Java mà **không có filter category**, sản phẩm `device-150` cũng thuộc kết quả của `$gte`. Hãy đọc đầy đủ điều kiện thay vì ngầm giả định query chỉ áp dụng một danh mục.

**Nguyên tắc:** với giá tối thiểu có thể chấp nhận, chọn `GreaterThanEqual`. Với yêu cầu “đắt hơn giá X”, chọn `GreaterThan` nếu X không được tính vào.

## 8. Nhỏ hơn và nhỏ hơn hoặc bằng

| Phương thức suy diễn | Toán tử MongoDB | Điều kiện logic |
| --- | --- | --- |
| `findByPriceCentsLessThan(x)` | `$lt` | `priceCents < x` |
| `findByPriceCentsLessThanEqual(x)` | `$lte` | `priceCents <= x` |

Với `x = 150000`:

```java
List<Product> strict =
        repository.findByPriceCentsLessThan(150_000L);

List<Product> inclusive =
        repository.findByPriceCentsLessThanEqual(150_000L);
```

```javascript
db.catalog_products.find({
  priceCents: { $lt: NumberLong("150000") }
});

db.catalog_products.find({
  priceCents: { $lte: NumberLong("150000") }
});
```

Trong danh mục `books`:

- `$lt: 150000` gồm `book-099` và `book-100`.
- `$lte: 150000` thêm `book-150`.

Không có bất kỳ quy tắc “tự cộng 1” nào khi chọn toán tử. Đối với dữ liệu dạng số nguyên, bạn *có thể* biến một điều kiện `x < k` thành `x <= k - 1` trong trường hợp có kiểm soát, nhưng cách làm này dễ sai khi kiểu dữ liệu hoặc đơn vị đo thay đổi. Hãy dùng đúng toán tử quan hệ.

## 9. Between: phải xác định biên mở hay đóng

Đây là phần quan trọng nhất của bài.

Theo bảng từ khóa của **Spring Data MongoDB**, phương thức `Between` có **hai tham số** được dịch thành **khoảng mở**:

```java
List<Product> findByPriceCentsBetween(
        long lower, long upper);

repository.findByPriceCentsBetween(100_000L, 200_000L);
```

```javascript
db.catalog_products.find({
  priceCents: {
    $gt: NumberLong("100000"),
    $lt: NumberLong("200000")
  }
});
```

Kết quả thuộc `books` chỉ có `book-150`. Cả giá trị 100 000 và 200 000 **không được đưa vào**.

### 9.1. Range<T> thể hiện ý định chính xác

Spring Data MongoDB cũng hỗ trợ `org.springframework.data.domain.Range` trong `Between`:

```java
import org.springframework.data.domain.Range;

List<Product> findByPriceCentsBetween(Range<Long> range);
```

Có bốn cách khai báo biên:

| Java Range | Ký hiệu toán học | BSON filter trên priceCents |
| --- | --- | --- |
| `Range.open(100_000L, 200_000L)` | `(100000, 200000)` | `$gt: 100000, $lt: 200000` |
| `Range.closed(100_000L, 200_000L)` | `[100000, 200000]` | `$gte: 100000, $lte: 200000` |
| `Range.leftOpen(100_000L, 200_000L)` | `(100000, 200000]` | `$gt: 100000, $lte: 200000` |
| `Range.rightOpen(100_000L, 200_000L)` | `[100000, 200000)` | `$gte: 100000, $lt: 200000` |

Với dữ liệu `books`:

| Biên | Các sản phẩm khớp |
| --- | --- |
| Mở cả hai | `book-150` |
| Đóng cả hai | `book-100`, `book-150`, `book-200` |
| Mở trái | `book-150`, `book-200` |
| Mở phải | `book-100`, `book-150` |

Mã Java:

```java
Range<Long> inclusive =
        Range.closed(100_000L, 200_000L);

Range<Long> exclusive =
        Range.open(100_000L, 200_000L);

Range<Long> halfOpen =
        Range.rightOpen(100_000L, 200_000L);

List<Product> products =
        repository.findByPriceCentsBetween(inclusive);
```

**Quy tắc chọn:** khi giao diện người dùng ghi “giá từ 100 000 đến 200 000” và hai đầu đều được tính, dùng `Range.closed` hoặc `GreaterThanEqual/ LessThanEqual`. Khi nghiệp vụ yêu cầu cắt khoảng thời gian hoặc phân đoạn liên tiếp không chồng lấn, khoảng `[from, to)` thường phù hợp hơn.

### 9.2. Range với một biên không xác định

API `Range` của Spring Data Commons hỗ trợ biên không giới hạn, chẳng hạn `Range.rightUnbounded(...)` hoặc `Range.leftUnbounded(...)`. Tuy nhiên, với bộ lọc tìm kiếm tùy chọn, cách rõ ràng đôi khi là **xây `Query` động** theo tham số thực có:

- Không có min/max: không tạo điều kiện giá.
- Chỉ có min: dùng `$gte`.
- Chỉ có max: dùng `$lte`.
- Có cả hai: tạo khoảng có quy tắc inclusive/exclusive do nghiệp vụ quy định.

Tránh ép mọi request vào `Between(min, max)` rồi tự tạo sentinel như 0 hoặc `Long.MAX_VALUE` mà không cân nhắc ý nghĩa dữ liệu.

### 9.3. Bắt lỗi đầu vào trước khi query

```java
public Range<Long> priceRange(long min, long max) {
    if (min < 0 || max < 0 || min > max) {
        throw new IllegalArgumentException("Khoảng giá không hợp lệ");
    }
    return Range.closed(min, max);
}
```

Với min = max, khoảng **đóng** `[x,x]` có ý nghĩa tương đương bằng x; khoảng **mở** `(x,x)` không chứa giá trị nào. Đừng tự hoán đổi min/max khi người dùng nhập ngược nếu hợp đồng API phải phản hồi lỗi validation.

## 10. Kết hợp nhiều điều kiện bằng And/Or

Ví dụ “sản phẩm thuộc books, giá nằm trong khoảng 100 000–200 000 và đang ACTIVE”:

```java
List<Product> findByCategoryAndPriceCentsBetweenAndStatus(
        String category,
        Range<Long> priceRange,
        String status);
```

Lời gọi:

```java
repository.findByCategoryAndPriceCentsBetweenAndStatus(
        "books",
        Range.closed(100_000L, 200_000L),
        "ACTIVE");
```

BSON tương đương:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 },
  status: "ACTIVE"
});
```

Kết quả: `book-100` và `book-150`; `book-200` bị loại vì `ARCHIVED`.

### 10.1. Khi có Or, làm rõ ngoặc logic

Một tên phương thức như:

```java
List<Product> findByCategoryAndStatusOrPriceCentsGreaterThan(
        String category, String status, long threshold);
```

Có thể mang ngữ nghĩa **(category AND status) OR priceCents > threshold**, không phải **category AND (status OR priceCents > threshold)**. Nếu cần cấu trúc ngoặc rõ ràng, ưu tiên `@Query` hoặc `MongoTemplate`:

```javascript
db.catalog_products.find({
  category: "books",
  $or: [
    { status: "ACTIVE" },
    { priceCents: { $gt: 200000 } }
  ]
});
```

Đặt tên phương thức theo domain càng ngắn và rõ thì việc review càng dễ. Đối với nhiều điều kiện động, việc tạo repository method cho mọi tổ hợp tham số thường dẫn đến API quá dài và khó duy trì.

## 11. So sánh ngày giờ: After/Before và khoảng nửa mở

Các từ khóa `After`/`Before` thường dùng với thời điểm:

```java
List<Product> findByPublishedAtAfter(Instant time);
List<Product> findByPublishedAtBefore(Instant time);
List<Product> findByPublishedAtBetween(Range<Instant> range);
```

Tương đương:

```javascript
db.catalog_products.find({
  publishedAt: { $gt: ISODate("2026-11-01T00:00:00Z") }
});

db.catalog_products.find({
  publishedAt: { $lt: ISODate("2026-11-02T00:00:00Z") }
});
```

`After` là **lớn hơn nghiêm ngặt**, `Before` là **nhỏ hơn nghiêm ngặt**. Nếu muốn lấy các document xuất bản trong **một ngày theo UTC**, nên dùng `[startOfDay, nextStartOfDay)`:

```java
import java.time.Instant;
import org.springframework.data.domain.Range;

Instant start =
        Instant.parse("2026-11-03T00:00:00Z");
Instant nextStart =
        Instant.parse("2026-11-04T00:00:00Z");

Range<Instant> dayRange =
        Range.rightOpen(start, nextStart);

List<Product> results =
        repository.findByPublishedAtBetween(dayRange);
```

Ưu điểm của khoảng nửa mở:

- Bao gồm mọi thời điểm từ `start` (kể cả đúng nửa đêm).
- Loại bỏ đúng điểm bắt đầu ngày tiếp theo.
- Không cần tính “23:59:59.999” hay giả định độ chính xác của từng nguồn dữ liệu.
- Hai ngày liên tiếp `[day1, day2)` và `[day2, day3)` **không chồng lấn**.

### 11.1. Ngày theo múi giờ người dùng

Nếu ứng dụng phục vụ người dùng tại Việt Nam, một ngày dân sự ở `Asia/Ho_Chi_Minh` không bắt đầu lúc 00:00 UTC. Chuyển **đầu ngày theo `ZoneId`** sang `Instant` trước khi query:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 3);

Instant start = day.atStartOfDay(zone).toInstant();
Instant nextStart = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();

Range<Instant> localDayRange =
        Range.rightOpen(start, nextStart);
```

Cách này cũng đúng về nguyên tắc với các vùng có daylight saving time, miễn dùng `ZoneId` thực tế thay vì cộng số mili giây cố định. Dữ liệu BSON Date thường đại diện thời điểm UTC, còn giao diện “ngày” theo múi giờ là **quy tắc ở ranh giới ứng dụng**.

## 12. BSON type, null và tính đúng đắn của so sánh

MongoDB sử dụng **BSON**, nên khi so sánh số, chuỗi và thời gian cần xem giá trị thực lưu trong document.

### 12.1. Số và chuỗi là hai kiểu khác nhau

Hai document sau không giống nhau về kiểu:

```javascript
{ _id: "P-1", priceCents: NumberLong("150000") }
{ _id: "P-2", priceCents: "150000" }
```

Một truy vấn phạm vi số:

```javascript
db.catalog_products.find({
  priceCents: { $gte: 100000, $lte: 200000 }
});
```

sẽ khớp giá trị **BSON numeric**, không nên trông đợi nó tự parse chuỗi `"150000"` thành số. MongoDB dùng quy tắc **type bracketing** cho `$gt`/`$gte`/`$lt`/`$lte`. Các kiểu số BSON `int`, `long`, `double`, `decimal` được xử lý như nhóm số trong so sánh, còn string không thuộc nhóm đó.

**Lỗi thường gặp:** một converter ghi `BigDecimal` thành BSON string, nhưng ứng dụng mong so sánh/sort như số. Khi format thay đổi, cần migration và test query thật, không chỉ test Java đọc lại được số.

### 12.2. String comparison và collation

```javascript
{ category: "books" }
{ category: "BOOKS" }
```

Equality hoặc range trên string phụ thuộc collation. Mặc định, thứ tự so sánh theo BSON/string có thể không giống thứ tự ngôn ngữ của người dùng. `IgnoreCase` có thể tạo một truy vấn khác kiểu (theo tài liệu Spring Data MongoDB, có thể dựa trên regex), nên không tự đảm bảo dùng index như equality thường.

Khi tìm kiếm chuỗi có phân biệt dấu và sắp xếp theo ngôn ngữ, cân nhắc collation phù hợp và index với cùng collation. Không nhầm `LessThan` trên string với việc so sánh số được lưu trong string.

### 12.3. Null và field vắng mặt

Giá trị `null` trong MongoDB và **field không tồn tại** là hai trạng thái khác nhau, nhưng một số predicate khớp cả hai. Đặc biệt:

- `{ warrantyMonths: null }`: thường khớp **null hoặc missing**.
- `{ warrantyMonths: { $ne: null } }`: khớp **field tồn tại và khác null**.
- `{ warrantyMonths: { $ne: 12 } }`: có thể khớp **field vắng mặt**.
- `{ warrantyMonths: { $exists: true } }`: khớp field tồn tại, **kể cả null**.

Nếu nghiệp vụ cần phân biệt “chưa thiết lập” với “giá trị bằng 0”, tránh dùng primitive `int` cho property có thể thiếu. Dùng `Integer`, enum trạng thái hoặc field riêng cùng schema validation phù hợp.

### 12.4. Array và nested field

Các toán tử so sánh trong MongoDB cũng có quy tắc khi field chứa array; ví dụ một điều kiện số có thể khớp khi array chứa phần tử thỏa điều kiện. Đừng suy từ một query `greater-than` trên array rằng *mọi* phần tử trong array đều lớn hơn ngưỡng.

Đối với nhiều điều kiện cần khớp **cùng một phần tử object** trong array, hãy xem `$elemMatch` thay vì đưa hai điều kiện lên các đường dẫn array tách biệt. Còn đối với embedded object, Spring Data có thể suy diễn property path, nhưng bạn vẫn cần xác minh BSON field được tạo.

## 13. Khi nào dùng @Query hoặc MongoTemplate?

Query derivation phù hợp khi phương thức đơn giản và ý nghĩa ổn định. Với bộ lọc động hoặc ngoặc logic phức tạp, dùng query tường minh dễ kiểm soát hơn.

### 13.1. @Query: rõ biên và field BSON

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    @Query("{ 'category': ?0, 'priceCents': " +
           "{ '$gte': ?1, '$lte': ?2 } }")
    List<Product> findProductsWithinInclusivePrice(
            String category, long lower, long upper);
}
```

Ví dụ dùng `@Query` đặt ngay trên method repository cùng tên khác các method suy diễn ở trên. Ở đây `?0` là `category`, `?1` là lower, `?2` là upper; biên đóng được biểu thị tường minh bởi `$gte` và `$lte`.

Không nối trực tiếp giá trị người dùng vào chuỗi JSON query bằng phép cộng string. Sử dụng binding tham số để tránh lỗi escaping và nguy cơ injection từ dữ liệu ngoài.

### 13.2. MongoTemplate: khoảng giá tùy chọn

```java
package dev.learning.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {
    private final MongoTemplate template;

    public ProductSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<Product> search(
            String category, Long min, Long max) {

        if (min != null && min < 0) {
            throw new IllegalArgumentException("min không hợp lệ");
        }
        if (max != null && max < 0) {
            throw new IllegalArgumentException("max không hợp lệ");
        }
        if (min != null && max != null && min > max) {
            throw new IllegalArgumentException("min phải <= max");
        }

        Query query = new Query();

        if (category != null && !category.isBlank()) {
            query.addCriteria(
                Criteria.where("category").is(category));
        }

        if (min != null || max != null) {
            Criteria price = Criteria.where("priceCents");
            if (min != null) {
                price = price.gte(min);
            }
            if (max != null) {
                price = price.lte(max);
            }
            query.addCriteria(price);
        }

        return template.find(query, Product.class);
    }
}
```

Dùng `Long` thay vì `long` cho filter min/max tùy chọn giúp phân biệt **không truyền tham số** với giá trị **0**. Service validate khoảng trước khi gửi query; việc tự động hoán đổi hai biên có thể che giấu lỗi người dùng.

### 13.3. Truy vấn động và nhiều điều kiện Or

```java
Criteria wanted = new Criteria().orOperator(
        Criteria.where("status").is("ACTIVE"),
        Criteria.where("priceCents").gt(200_000L));

Query query = new Query()
        .addCriteria(Criteria.where("category").is("books"))
        .addCriteria(wanted);
```

Query tương đương với điều kiện `category == "books" AND (status == "ACTIVE" OR priceCents > 200000)`. Đối chiếu kết quả trên dữ liệu thử để tránh đảo ý nghĩa ngoặc logic.

## 14. Sắp xếp, giới hạn và phân trang

Các phép so sánh thường được dùng cùng sắp xếp:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Range;

Page<Product> findByCategoryAndPriceCentsBetween(
        String category,
        Range<Long> range,
        Pageable pageable);

List<Product> findTop5ByCategoryOrderByPriceCentsAsc(
        String category);
```

Lời gọi:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest page = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("priceCents"),
            Sort.Order.asc("id")
        )
);

Page<Product> products =
        repository.findByCategoryAndPriceCentsBetween(
                "books",
                Range.closed(100_000L, 200_000L),
                page);
```

**Vì sao sort thêm ID?** Nhiều sản phẩm có thể có cùng giá. Khi phân trang, thêm `id` làm khóa phụ giúp thứ tự **ổn định** hơn giữa các bản ghi cùng giá. Tuy vậy, khi dữ liệu được cập nhật đồng thời, offset pagination vẫn có thể lặp hoặc bỏ qua bản ghi giữa các lần gọi; cần thiết kế pagination theo yêu cầu nhất quán của ứng dụng.

`Page<T>` thường cần query đếm tổng số phần tử. Nếu UI chỉ cần biết còn trang kế tiếp, `Slice<T>` có thể tránh một số chi phí đếm. Nếu dữ liệu có hàng triệu bản ghi và người dùng di chuyển sâu vào danh sách, đánh giá keyset pagination dựa trên giá + ID thay vì offset lớn.

## 15. Index và kế hoạch truy vấn

Có query đúng về mặt logic chưa đủ để đáp ứng hiệu năng. Với truy vấn phổ biến:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 }
}).sort({ priceCents: 1, _id: 1 });
```

Một compound index tham khảo:

```javascript
db.catalog_products.createIndex(
  { category: 1, priceCents: 1, _id: 1 },
  { name: "category_price_id" }
);
```

**Lý do chọn thứ tự trên:** `category` là điều kiện **bằng**, `priceCents` là điều kiện **range** và sort, `_id` giúp cố định thứ tự trong nhóm có cùng giá. Đây là lựa chọn xuất phát từ dạng workload minh họa, không phải công thức chung cho mọi schema.

### 15.1. Equality trước range

Nguyên tắc thường được áp dụng khi thiết kế compound index là xem các điều kiện equality, sort và range (ESR). Vị trí của mỗi field ảnh hưởng khả năng sử dụng index cho filter và sort. Khi workload đa dạng, có thể cần nhiều index; không nên tạo một index cho từng query method mà không đo chi phí ghi và kích thước index.

### 15.2. $ne thường không có tính chọn lọc cao

Query `{ status: { $ne: "ARCHIVED" } }` có thể lấy rất nhiều document. Có index trên `status` không bảo đảm nó nhanh; server có thể chọn collection scan nếu đọc hầu hết collection. Khi nghiệp vụ có trạng thái hữu hạn, một query **chọn trực tiếp những trạng thái mong muốn** đôi khi rõ nghĩa và chọn lọc hơn:

```javascript
db.catalog_products.find({
  status: { $in: ["ACTIVE", "DRAFT"] }
});
```

Việc thay `Not` bằng `In` chỉ hợp lệ nếu tập trạng thái được nghiệp vụ định nghĩa đầy đủ; không tự sửa query khi còn những trạng thái mới có thể được thêm sau này.

### 15.3. Kiểm tra bằng explain

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 }
}).sort({ priceCents: 1, _id: 1 })
  .explain("executionStats");
```

Quan sát:

- `winningPlan` có dùng index mong muốn hay không.
- `totalKeysExamined` và `totalDocsExamined` so với `nReturned`.
- Có stage `SORT` trong memory hay không (tùy plan).
- Thời gian chạy dưới dữ liệu/tải đại diện.

Index làm tăng chi phí lưu trữ và cập nhật khi ghi. Đừng tối ưu dựa trên vài document seed; cần xem phân bố dữ liệu thật, cardinality, hot categories và truy vấn thường gặp.

## 16. Kiểm thử tự động các giá trị biên

Bài kiểm thử quan trọng nhất cho `Between` là đưa **cả hai giá trị đúng bằng biên** vào dữ liệu. Nếu chỉ thử một giá trị ở giữa, bạn không phân biệt được `$gt/$lt` với `$gte/$lte`.

### 16.1. Test tích hợp với MongoDB

Ví dụ dưới đây dùng Spring Boot test, repository và database test riêng đã cấu hình kết nối. Test xóa dữ liệu collection trong môi trường test trước khi seed, vì vậy **không chạy class này với cấu hình production**.

```java
package dev.learning.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Range;

@SpringBootTest
class ProductDerivedQueryIntegrationTest {

    @Autowired
    ProductRepository repository;

    @BeforeEach
    void prepare() {
        repository.deleteAll(); // Chỉ dành cho database test.
        Instant published =
                Instant.parse("2026-11-03T08:00:00Z");

        repository.insert(List.of(
            new Product("book-099", "books",  99_000L, 6,
                    "ACTIVE", published, null),
            new Product("book-100", "books", 100_000L, 7,
                    "ACTIVE", published, 0),
            new Product("book-150", "books", 150_000L, 8,
                    "ACTIVE", published, 12),
            new Product("book-200", "books", 200_000L, 9,
                    "ARCHIVED", published, 24),
            new Product("book-201", "books", 201_000L, 2,
                    "ACTIVE", published, 12),
            new Product("device-150", "devices", 150_000L, 4,
                    "ACTIVE", published, 12)
        ));
    }

    @Test
    void betweenTwoArgumentsUsesOpenBounds() {
        var ids = repository.findByCategoryAndPriceCentsBetween(
                "books", Range.open(100_000L, 200_000L))
                .stream()
                .map(Product::id)
                .toList();

        assertThat(ids).containsExactlyInAnyOrder("book-150");
    }

    @Test
    void inclusiveBoundsIncludeBothEndpoints() {
        var ids = repository.findByCategoryAndPriceCentsBetween(
                "books", Range.closed(100_000L, 200_000L))
                .stream()
                .map(Product::id)
                .toList();

        assertThat(ids).containsExactlyInAnyOrder(
                "book-100", "book-150", "book-200");
    }

    @Test
    void greaterThanDiffersFromGreaterThanEqual() {
        var greater = repository
                .findByPriceCentsGreaterThan(200_000L)
                .stream().map(Product::id).toList();

        var inclusive = repository
                .findByPriceCentsGreaterThanEqual(200_000L)
                .stream().map(Product::id).toList();

        assertThat(greater).containsExactlyInAnyOrder("book-201");
        assertThat(inclusive)
                .containsExactlyInAnyOrder("book-200", "book-201");
    }

    @Test
    void missingWarrantyCanMatchIsNull() {
        var ids = repository.findByWarrantyMonthsIsNull()
                .stream().map(Product::id).toList();

        assertThat(ids).contains("book-099");
        assertThat(ids).doesNotContain("book-100");
    }
}
```

Các đoạn assert sử dụng `containsExactlyInAnyOrder` vì query không có sort, nên MongoDB không bảo đảm thứ tự kết quả.

**Bổ sung cần thiết:** phương thức `findByCategoryAndPriceCentsBetween(String, Range<Long>)` phải có trong `ProductRepository` như phần trên. Test kiểm tra biên của overload `Range`; hãy thêm test trực tiếp cho overload **hai tham số** để bảo đảm nó dùng `$gt/$lt`.

### 16.2. Test trực tiếp hai tham số

```java
@Test
void betweenWithTwoScalarArgumentsExcludesEndpoints() {
    var ids = repository
            .findByPriceCentsBetween(100_000L, 200_000L)
            .stream().map(Product::id).toList();

    // Cả hai danh mục đều có giá 150000.
    assertThat(ids).containsExactlyInAnyOrder(
            "book-150", "device-150");
}
```

Bộ dữ liệu kiểm thử còn cần các trường hợp:

| Tình huống | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| Đúng bằng min | 100 000 | Có trong `$gte`, không có trong `$gt`. |
| Đúng bằng max | 200 000 | Có trong `$lte`, không có trong `$lt`. |
| Nằm giữa | 150 000 | Có trong cả khoảng mở/đóng. |
| Nhỏ hơn min | 99 000 | Bị loại khỏi range tương ứng. |
| Lớn hơn max | 201 000 | Bị loại khỏi range tương ứng. |
| Min = max | 150 000, 150 000 | Khoảng đóng có giá trị; khoảng mở không. |
| Min > max | 200 000, 100 000 | Service từ chối trước khi query. |
| Field null/missing | warranty không có | Kiểm tra `IsNull`, `IsNotNull`, `Not`. |
| Giá sai kiểu BSON | `"150000"` | Không lẫn với so sánh số. |
| Ngày đúng nửa đêm | `00:00:00Z` | Xử lý đúng biên ngày. |

## 17. Reactive repository với cùng toán tử

Với dự án reactive, Spring Data MongoDB có `ReactiveMongoRepository`. Từ khóa so sánh vẫn có ý nghĩa tương ứng, nhưng kết quả là `Flux` hoặc `Mono`:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByPriceCentsGreaterThanEqual(long value);

    Flux<Product> findByPriceCentsBetween(Range<Long> range);

    Mono<Long> countByCategory(String category);
}
```

Ví dụ:

```java
Flux<Product> filtered =
        reactiveRepository.findByPriceCentsBetween(
                Range.closed(100_000L, 200_000L));
```

Không dùng `block()` trong event loop để đưa dữ liệu reactive về `List` một cách tùy tiện. Bản chất BSON và biên mở/đóng không đổi khi chuyển sang reactive; khác biệt nằm ở mô hình thực thi và cách xử lý backpressure, error, cancellation.

Một reactive query không tự tạo transaction nhiều document. Nếu nghiệp vụ phải thay đổi nhiều document nguyên tử, cần thiết lập transaction manager/session và topology MongoDB phù hợp.

## 18. Sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `Between(a,b)` bao gồm cả hai biên | Thiếu sản phẩm bằng min/max | Dùng `Range.closed` hoặc `$gte/$lte`. |
| Dùng `GreaterThan` thay `GreaterThanEqual` | Bỏ mất đúng ngưỡng | Xác nhận yêu cầu biên và test điểm đúng bằng ngưỡng. |
| Dùng `Not(value)` để tìm “giá trị hợp lệ” | Có thể lấy field null hoặc missing | Định nghĩa rõ trạng thái hợp lệ; dùng điều kiện thích hợp. |
| Nghĩ `IsNull` chỉ khớp BSON null | Có thể khớp field không tồn tại | Thêm điều kiện `$exists` hoặc `$type` khi cần. |
| Lưu giá dưới dạng string rồi so sánh như số | Filter, sort và aggregation sai | Lưu BSON numeric phù hợp, migration dữ liệu cũ. |
| So sánh `Instant` bằng ngày local chưa đổi timezone | Lệch ngày khi lọc | Chuyển local-day sang khoảng `Instant` theo `ZoneId`. |
| Viết derived method quá dài với Or/And | Dễ sai ưu tiên và khó review | Dùng `@Query`/`MongoTemplate` có nhóm điều kiện rõ. |
| Dùng index theo mỗi property một cách máy móc | Index tăng, query vẫn chậm | Thiết kế compound index dựa trên workload, đo `explain`. |
| Giả định dữ liệu trả về có thứ tự | Test/flaky pagination không ổn định | Thêm sort tường minh và khóa phụ. |
| Dùng phương thức so sánh với field nằm trong array mà không hiểu semantics | Kết quả khác kỳ vọng | Kiểm tra array comparison và `$elemMatch`. |
| Chỉ kiểm tra compilation | Query sai property hoặc index kém | Chạy integration test và xem BSON query plan. |

## 19. Bài tập thực hành có gợi ý

**Bài 1 — Giá trong khoảng đóng.** Viết repository method tìm các sản phẩm books có giá từ 100 000 tới 200 000, **kể cả hai biên**. Mô tả BSON và tập ID từ dữ liệu mẫu.

*Gợi ý:* `findByCategoryAndPriceCentsBetween("books", Range.closed(100_000L, 200_000L))` → `$gte/$lte` → `book-100`, `book-150`, `book-200`.

**Bài 2 — Giá trong khoảng mở.** Dùng overload `findByPriceCentsBetween(long, long)` cho ngưỡng 100 000 và 200 000. Vì sao `book-100` bị loại?

*Gợi ý:* Spring Data MongoDB dùng `$gt` và `$lt` cho hai tham số của `Between`; không lấy giá bằng ngưỡng.

**Bài 3 — Kiểm tra trường bảo hành.** Chọn câu truy vấn cho ba nhu cầu: (a) thiếu field, (b) field tồn tại và khác null, (c) có giá trị khác 12 kể cả chưa cấu hình. So sánh `Exists`, `IsNotNull` và `Not`.

*Gợi ý:* (a) `$exists:false`, (b) `$ne:null`, (c) `$ne:12`. Đừng nhầm (c) với “field phải tồn tại”.

**Bài 4 — Lọc một ngày theo giờ Việt Nam.** Từ `LocalDate` và `ZoneId.of("Asia/Ho_Chi_Minh")`, tạo `Range.rightOpen(start, nextStart)`. Giải thích vì sao không dùng `[00:00,23:59:59]` theo UTC.

*Gợi ý:* Múi giờ người dùng xác định ranh giới ngày; khoảng nửa mở không chồng lấn và không cần biết độ chính xác mili giây của mọi nguồn.

**Bài 5 — Tối ưu tìm kiếm sản phẩm.** Workload truy vấn equality trên `category`, range trên `priceCents` và sort giá tăng, ID tăng. Đề xuất một compound index rồi dùng `explain("executionStats")` để xác minh.

*Gợi ý:* thử `{ category:1, priceCents:1, _id:1 }`; đánh giá số key/doc được xét và chỉ giữ index nếu có ích với workload.

**Bài 6 — Viết bộ lọc tùy chọn.** API có `category`, `minPrice`, `maxPrice`, từng tham số có thể không truyền. Viết `MongoTemplate` với `Criteria.gte/lte` chỉ khi có tham số; kiểm tra min > max.

*Gợi ý:* dùng `Long` nullable cho filter và validate trước khi tạo `Query`; không tạo một method name cho mọi tổ hợp.

## 20. Checklist và tài liệu tham khảo

Trước khi đưa một phương thức suy diễn vào service, hãy tự kiểm tra:

- [ ] Tên property Java và đường mapping BSON đúng.
- [ ] Chọn đúng `Equal/Not/GreaterThan/GreaterThanEqual/LessThan/LessThanEqual`.
- [ ] Với `Between`, xác định rõ biên mở/đóng và dùng `Range` khi cần.
- [ ] Kiểm thử giá trị **bằng từng biên**, thấp hơn và cao hơn biên.
- [ ] Xác định semantics của `null` và missing field, đặc biệt với `$ne`.
- [ ] Kiểm tra BSON type cho số, date, ObjectId và chuỗi; không trộn số với string.
- [ ] Chuẩn hóa đơn vị tiền, múi giờ và precision trước khi lập query.
- [ ] Thêm điều kiện `And/Or` có ngoặc rõ ràng nếu nghiệp vụ phức tạp.
- [ ] Dùng sort tường minh khi cần thứ tự ổn định và phân trang.
- [ ] Tạo index dựa trên workload, xác minh qua `explain`.
- [ ] Có integration test trên MongoDB Server và driver phù hợp môi trường đích.

### Nguồn chính thức

1. [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): bảng từ khóa `Not`, `GreaterThan`, `LessThan`, `Between`, `After`, `Before` và biểu diễn BSON.
2. [Spring Data MongoDB — Defining Query Methods](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html): cơ chế parse method name, `And/Or`, sort, paging và limiting.
3. [Spring Data Commons — Range API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Range.html): `open`, `closed`, `leftOpen`, `rightOpen` và biên không giới hạn.
4. [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria` và các phép so sánh.
5. [MongoDB Manual — Comparison Query Predicate Operators](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/comparison/): toán tử `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`.
6. [MongoDB Manual — Type Bracketing](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/): ảnh hưởng của BSON type với phép so sánh.
7. [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): phân biệt giá trị null và field vắng mặt.
8. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): đọc kế hoạch query và số liệu thực thi.
9. [MongoDB Manual — The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): nguyên tắc thiết kế compound index cho equality, sort và range.

**Ghi nhớ:** Tên phương thức repository là một cách viết truy vấn có cấu trúc. Tính đúng đắn đến từ việc hiểu toán tử MongoDB được sinh ra, loại dữ liệu BSON, biên mở/đóng và ngữ nghĩa null/missing. Hãy xác minh chúng bằng dữ liệu sát biên và kiểm tra kế hoạch thực thi trước khi dựa vào truy vấn trong nghiệp vụ thực tế.
