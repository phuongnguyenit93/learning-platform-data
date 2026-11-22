# Chọn @Query, truy vấn suy diễn hoặc triển khai tùy chỉnh

> **Chương:** Truy vấn JSON  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB hỗ trợ ba cách thường gặp để truy vấn document: **truy vấn suy diễn từ tên phương thức repository** (*derived query*), annotation **`@Query`** viết biểu thức JSON, và **triển khai repository tùy chỉnh** dùng `MongoTemplate`/`Criteria`. Cùng một điều kiện lọc có thể được diễn đạt theo cả ba cách, nhưng mỗi cách tối ưu cho một mức độ phức tạp khác nhau.

Nếu lạm dụng derived query, tên phương thức trở nên dài và khó sửa. Nếu dùng `@Query` cho mọi trường hợp, chuỗi JSON khó bảo trì khi các điều kiện phải bật/tắt theo yêu cầu. Nếu tạo class tùy chỉnh cho một phép so sánh đơn giản, ứng dụng tốn công xây dựng mã không cần thiết. **Chọn hình thức ít phức tạp nhất nhưng diễn đạt đúng hợp đồng nghiệp vụ** là mục tiêu chính của bài.

Bài thuộc module `SPRING_DATA_MONGODB`, gồm kết nối, ánh xạ document, thao tác qua `MongoTemplate` hoặc repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Nội dung tập trung vào cách **quyết định và hiện thực hóa truy vấn** trong một hệ thống thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn giữa derived query, `@Query` và custom repository fragment dựa trên độ phức tạp và tính động của điều kiện.
2. Dùng `@Query` với tham số vị trí `?0`, `?1`, projection và phân trang mà không ghép chuỗi từ input.
3. Viết repository fragment có interface và implementation, xây query động bằng `MongoTemplate`, `Query` và `Criteria`.
4. Hiểu ảnh hưởng của mapping field Java/BSON, enum, `Instant`, điều kiện rỗng, sorting và quyền theo tenant.
5. Kiểm thử truy vấn trên MongoDB thực, đo index và phân biệt filter thông thường với aggregation.

## 2. Bảng quyết định nhanh

| Tiêu chí | Derived query | `@Query` JSON | Custom implementation |
| --- | --- | --- | --- |
| Cách viết | Tên phương thức repository | Annotation chứa JSON cố định | Java code tạo filter |
| Tốt nhất cho | Ít điều kiện phổ biến, ổn định | Toán tử MongoDB cụ thể, query cố định | Bộ lọc tùy chọn, điều kiện thay đổi hoặc phức tạp |
| Cần class triển khai | Không | Không | Có, thường dùng fragment |
| Độ dễ đọc | Cao nếu tên ngắn | Cao nếu JSON vừa phải | Cao khi tách logic theo chức năng |
| Thêm/bỏ filter khi chạy | Không thuận tiện | Không thuận tiện với JSON tĩnh | Thuận tiện bằng các nhánh `if` |
| Projection, sorting, paging | Hỗ trợ qua repository | Hỗ trợ qua repository và `fields` | Phải áp dụng vào `Query` |
| Chi phí viết mã | Thấp | Thấp–trung bình | Cao hơn |
| Độ nhanh của truy vấn | Phụ thuộc BSON query/index | Phụ thuộc BSON query/index | Phụ thuộc BSON query/index |

**Nguyên tắc chọn:** dùng **derived query** khi tên phương thức còn dễ hiểu; dùng **`@Query`** khi JSON cố định biểu đạt yêu cầu rõ hơn tên dài; dùng **custom fragment** khi bộ lọc có thể vắng mặt, nhiều nhánh logic, hoặc cần tái sử dụng cách dựng query.

Điểm quan trọng: MongoDB server không biết Java đã dùng phương thức nào. Với cùng filter, projection, sort và index, chi phí xử lý trên MongoDB nhìn chung tương đương.

## 3. Mô hình xuyên suốt: tìm đơn hàng

Giả sử ứng dụng bán hàng lưu đơn ở collection `orders` với mã cửa hàng `storeId`, trạng thái `status`, tiền `totalMinor`, thời điểm tạo `createdAt` và mảng `tags`. Màn hình đơn giản tìm theo cửa hàng và trạng thái, còn màn hình nâng cao có filter tùy chọn và phân trang.

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String orderCode,
    String storeId,
    OrderStatus status,
    long totalMinor,
    Instant createdAt,
    List<String> tags
) {}
```

`id` là thuộc tính Java được ánh xạ sang `_id` trong BSON. Các ID như `O-101` không phải chuỗi hex của ObjectId nên giữ được dạng string như ví dụ. Nếu model thực tế dùng `@Field` hoặc custom converter, query phải được xác minh với field/kiểu BSON tương ứng.

### 3.1. Seed dữ liệu bằng mongosh

**Chỉ chạy trong database kiểm thử cô lập:**

```javascript
use shop

db.orders.insertMany([
  {
    _id: "O-101",
    orderCode: "ORD-101",
    storeId: "STORE-HCM",
    status: "NEW",
    totalMinor: NumberLong(120000),
    createdAt: ISODate("2026-11-19T02:00:00Z"),
    tags: ["web", "priority"]
  },
  {
    _id: "O-102",
    orderCode: "ORD-102",
    storeId: "STORE-HCM",
    status: "PAID",
    totalMinor: NumberLong(850000),
    createdAt: ISODate("2026-11-19T04:00:00Z"),
    tags: ["web"]
  },
  {
    _id: "O-103",
    orderCode: "ORD-103",
    storeId: "STORE-HCM",
    status: "CANCELLED",
    totalMinor: NumberLong(400000),
    createdAt: ISODate("2026-11-20T01:00:00Z"),
    tags: ["app"]
  },
  {
    _id: "O-104",
    orderCode: "ORD-104",
    storeId: "STORE-HCM",
    status: "PAID",
    totalMinor: NumberLong(1500000),
    createdAt: ISODate("2026-11-20T03:00:00Z"),
    tags: ["app", "priority"]
  },
  {
    _id: "O-105",
    orderCode: "ORD-105",
    storeId: "STORE-HN",
    status: "PAID",
    totalMinor: NumberLong(2000000),
    createdAt: ISODate("2026-11-20T04:00:00Z"),
    tags: ["priority"]
  }
])
```

Mọi ví dụ truy vấn từ giao diện nghiệp vụ đều chứa `storeId` để giữ phạm vi dữ liệu của từng cửa hàng. Trong hệ thống thật, service phải xác minh `storeId` dựa trên người dùng đã đăng nhập; không xem giá trị do client gửi là quyền truy cập.

## 4. Trường hợp 1: truy vấn suy diễn

Derived query dùng tên property và keyword của Spring Data, ví dụ `And`, `In`, `GreaterThanEqual`, `LessThan`, `True`. Với điều kiện nhỏ, đây thường là cách dễ đọc và dễ bảo trì nhất.

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByStoreIdAndStatus(
        String storeId, OrderStatus status);

    Page<OrderDocument> findByStoreIdAndStatusIn(
        String storeId,
        Collection<OrderStatus> statuses,
        Pageable pageable);

    List<OrderDocument>
    findByStoreIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        String storeId,
        Instant fromInclusive,
        Instant toExclusive);
}
```

Gọi:

```java
List<OrderDocument> paid =
    repository.findByStoreIdAndStatus(
        "STORE-HCM", OrderStatus.PAID);
```

Query tương ứng về mặt logic:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  status: "PAID"
})
// O-102 và O-104
```

Phương thức lọc thời gian dùng `>= fromInclusive` và `< toExclusive`, là khoảng nửa mở `[from, to)` thích hợp để ghép nhiều khoảng liên tiếp mà không đếm trùng ranh giới.

### 4.1. Khi nên chọn derived query

- Chỉ có vài field cố định.
- Keyword phản ánh đúng yêu cầu và thứ tự tham số rõ.
- Không cần nhóm điều kiện JSON đặc biệt hoặc pipeline aggregation.
- Hầu hết người đọc hiểu được phương thức mà không cần mở file khác.

Nếu chỉ cần `findByStoreIdAndOrderCode(...)` thì tạo custom class sẽ làm tăng chi phí mà không thêm lợi ích đáng kể.

### 4.2. Dấu hiệu cần phương án khác

Tên như:

```java
findByStoreIdAndStatusInAndCreatedAtGreaterThanEqualAndCreatedAtLessThanAndTotalMinorGreaterThanEqual(...)
```

vẫn có thể suy diễn theo property nhưng rất khó kiểm tra. Nếu mọi điều kiện đều bắt buộc và ổn định, `@Query` JSON có thể rõ ràng hơn. Nếu nhiều điều kiện *tùy chọn*, custom query builder thường phù hợp hơn; không cần một phương thức derived riêng cho mọi tổ hợp filter.

## 5. Trường hợp 2: @Query với JSON cố định

`@Query` nằm ở `org.springframework.data.mongodb.repository.Query`. Biểu thức JSON của annotation được Spring Data dùng để tạo filter MongoDB. Các placeholder `?0`, `?1`, ... bind với tham số Java tương ứng theo **vị trí**.

### 5.1. Bộ lọc nhiều toán tử nhưng không thay đổi

File `OrderJsonQueryRepository.java`, minh họa một **lựa chọn thay thế** cho các phương thức trong repository gốc:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderJsonQueryRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("""
        {
          'storeId': ?0,
          'status': { '$in': ?1 },
          'createdAt': { '$gte': ?2, '$lt': ?3 },
          'totalMinor': { '$gte': ?4 }
        }
        """)
    List<OrderDocument> findWithFixedFilters(
        String storeId,
        Collection<OrderStatus> statuses,
        Instant fromInclusive,
        Instant toExclusive,
        long minimumTotalMinor
    );
}
```

Ví dụ dùng **Java text block** (Java 15 trở lên). `@Query` vẫn nhận một chuỗi String; cú pháp JSON nháy đơn trong ví dụ được Spring Data MongoDB chấp nhận. Khi dùng Java cũ, có thể đặt chuỗi trên một dòng hoặc ghép các string literal tĩnh.

Gọi:

```java
jsonRepository.findWithFixedFilters(
    "STORE-HCM",
    List.of(OrderStatus.PAID),
    Instant.parse("2026-11-19T00:00:00Z"),
    Instant.parse("2026-11-21T00:00:00Z"),
    500000L
);
// O-102 và O-104
```

`jsonRepository` là instance của `OrderJsonQueryRepository`. Các vị trí bind là `?0 = storeId`, `?1 = statuses`, `?2 = from`, `?3 = to`, `?4 = mức tiền`. Đổi thứ tự tham số mà quên sửa placeholder là lỗi có thể xảy ra dù biểu thức JSON vẫn hợp lệ.

**Không đặt hai repository tương đương và hai tập cấu hình quét cùng quản lý một nhóm entity mà không có chủ đích.** Trong sản phẩm, bạn thường gom phương thức derived và annotated vào cùng `OrderRepository`; việc tách interface ở đây chỉ để minh họa rõ từng lựa chọn.

### 5.2. Dùng placeholder, không nối input vào JSON

Không xây query từ chuỗi người dùng theo cách:

```java
// PHẢN VÍ DỤ: tránh dùng chuỗi ghép từ input.
String unsafeQuery =
    "{ 'storeId': '" + storeId + "' }";
```

Thay vào đó:

```java
@Query("{ 'storeId': ?0 }")
List<OrderDocument> byStore(String storeId);
```

Placeholder giúp framework thực hiện binding/escaping theo cơ chế mapping thay vì tự chèn dấu nháy. Nhưng vẫn phải kiểm tra đầu vào, phân quyền, số phần tử `$in` và không cho phép người dùng quyết định cấu trúc operator MongoDB tùy ý.

### 5.3. Toán tử MongoDB trực quan hơn tên hàm

Giả sử muốn đơn hàng có **tất cả** nhãn trong danh sách:

```java
@Query("{ 'storeId': ?0, 'tags': { '$all': ?1 } }")
List<OrderDocument> findHavingAllTags(
    String storeId, Collection<String> requiredTags);
```

Query tương ứng:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  tags: { $all: ["web", "priority"] }
})
// O-101
```

`$all` yêu cầu mảng thỏa **tất cả** phần tử, còn `$in` chỉ cần một giá trị khớp. Khi cần đặt nhiều điều kiện trên **cùng một phần tử** của array document, cân nhắc `$elemMatch`. Trường hợp này dùng JSON ngắn sẽ dễ kiểm tra hơn một tên phương thức cố ghép nhiều keyword.

### 5.4. Không hiểu null là “bỏ qua điều kiện”

```java
@Query("{ 'storeId': ?0, 'status': ?1 }")
List<OrderDocument> byStoreAndStatus(
    String storeId, OrderStatus status);
```

Nếu `status` là null, điều kiện thường vẫn được bind như truy vấn so khớp với null của MongoDB; **không** mặc nhiên biến mất. Với request có nhiều tham số không bắt buộc, nên xây `Criteria` theo từng nhánh hoặc quy định phương thức riêng có mục đích rõ ràng.

## 6. Projection, Pageable và @Aggregation

### 6.1. Projection dành cho danh sách chỉ đọc

Nếu màn hình chỉ cần vài field, không cần nạp đầy đủ entity:

```java
package com.example.shop.orders;

import java.time.Instant;

public interface OrderBrief {
    String getOrderCode();
    OrderStatus getStatus();
    long getTotalMinor();
    Instant getCreatedAt();
}
```

Trong repository:

```java
@Query(
    value = "{ 'storeId': ?0, 'status': { '$in': ?1 } }",
    fields = """
        {
          'orderCode': 1,
          'status': 1,
          'totalMinor': 1,
          'createdAt': 1
        }
        """
)
List<OrderBrief> findBriefByStatuses(
    String storeId,
    Collection<OrderStatus> statuses);
```

`fields` mô tả **projection BSON**. Trả interface `OrderBrief` thay vì entity đầy đủ giúp tránh dùng một object chỉ có vài field để ghi lại bằng `save`, hành vi có thể làm mất các field chưa tải. Field `_id` thường được kèm trừ khi bị loại trừ rõ ràng.

### 6.2. Phân trang và sort

Với `@Query` cũng có thể dùng `Pageable`:

```java
@Query("{ 'storeId': ?0, 'status': { '$in': ?1 } }")
Page<OrderDocument> pageByStatuses(
    String storeId,
    Collection<OrderStatus> statuses,
    Pageable pageable);
```

Caller:

```java
Pageable pageable = PageRequest.of(
    0, 20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"))
);

Page<OrderDocument> page =
    repository.pageByStatuses(
        "STORE-HCM",
        List.of(OrderStatus.NEW, OrderStatus.PAID),
        pageable);
```

Đây là đoạn ví dụ với `repository` chứa `pageByStatuses` và các import `Page`, `Pageable`, `PageRequest`, `Sort`, `List`. `id` là property Java ánh xạ tới `_id`, dùng làm khóa phụ để sort ổn định khi `createdAt` trùng. `Page` có thể kéo theo truy vấn count; nếu chỉ cần biết còn trang sau, xem xét `Slice` hoặc phân trang theo khóa phù hợp.

Không cho phép request tùy ý đặt page size quá lớn hay sort theo field chưa kiểm tra. Projection, sorting, paging là **phần của hợp đồng truy vấn**, không phải chi tiết UI vô hại.

### 6.3. Khi nào cần @Aggregation?

Nếu yêu cầu là nhóm doanh thu theo ngày, `$lookup` collection khác, `$unwind` mảng hoặc tính toán qua pipeline, nên dùng **`@Aggregation`** hoặc `MongoTemplate.aggregate(...)`. `@Query` thông thường là lựa chọn cho filter/projection của document, không phải thay thế toàn bộ Aggregation Framework.

## 7. Trường hợp 3: repository fragment với MongoTemplate

Khi request có nhiều điều kiện **tùy chọn**, JSON tĩnh có thể phải mã hóa nhiều biểu thức phức tạp. Fragment tách interface tìm kiếm riêng và implementation dựng query từng bước:

```text
OrderRepository
  ├── MongoRepository<OrderDocument, String>
  └── OrderSearchRepository
         └── OrderSearchRepositoryImpl
                └── MongoTemplate + Criteria + Query
```

### 7.1. Interface fragment

File `OrderSearchRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository {

    List<OrderDocument> search(
        String storeId,
        Collection<OrderStatus> statuses,
        Instant fromInclusive,
        Instant beforeExclusive,
        Long minimumTotalMinor,
        Pageable pageable
    );
}
```

Quy ước minh họa do ứng dụng chủ động chọn:

- `storeId` bắt buộc và phải được service kiểm tra quyền.
- `statuses == null`: không áp bộ lọc status; `statuses.isEmpty()`: không có trạng thái được phép, trả kết quả rỗng.
- `fromInclusive`/`beforeExclusive` là hai ranh giới thời gian tùy chọn.
- `minimumTotalMinor == null`: không lọc mức tiền.
- `pageable` phải được giới hạn và có paging thực.

### 7.2. Implementation

File `OrderSearchRepositoryImpl.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final MongoTemplate template;

    public OrderSearchRepositoryImpl(MongoTemplate template) {
        this.template = template;
    }

    @Override
    public List<OrderDocument> search(
            String storeId,
            Collection<OrderStatus> statuses,
            Instant fromInclusive,
            Instant beforeExclusive,
            Long minimumTotalMinor,
            Pageable pageable) {

        Objects.requireNonNull(storeId, "storeId");
        Objects.requireNonNull(pageable, "pageable");

        if (storeId.isBlank()) {
            throw new IllegalArgumentException("storeId rỗng");
        }
        if (pageable.isUnpaged() || pageable.getPageSize() > 100) {
            throw new IllegalArgumentException(
                "Phải phân trang, pageSize <= 100");
        }
        if (fromInclusive != null && beforeExclusive != null
                && !fromInclusive.isBefore(beforeExclusive)) {
            throw new IllegalArgumentException(
                "Khoảng thời gian không hợp lệ");
        }
        if (statuses != null && statuses.stream()
                .anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "statuses chứa null");
        }
        if (statuses != null && statuses.isEmpty()) {
            return List.of();
        }

        Query query = Query.query(
            Criteria.where("storeId").is(storeId));

        if (statuses != null) {
            query.addCriteria(
                Criteria.where("status").in(statuses));
        }
        if (fromInclusive != null || beforeExclusive != null) {
            Criteria time = Criteria.where("createdAt");
            if (fromInclusive != null) {
                time.gte(fromInclusive);
            }
            if (beforeExclusive != null) {
                time.lt(beforeExclusive);
            }
            query.addCriteria(time);
        }
        if (minimumTotalMinor != null) {
            query.addCriteria(
                Criteria.where("totalMinor")
                    .gte(minimumTotalMinor));
        }

        query.with(pageable);
        return template.find(query, OrderDocument.class);
    }
}
```

`Query` luôn giữ điều kiện `storeId`. Các điều kiện khác chỉ được thêm khi đầu vào yêu cầu. Cách này tránh tình trạng truyền null vào một biểu thức `@Query` cố định và kỳ vọng điều kiện tự biến mất.

**Chú ý:** kiểm tra `storeId` không rỗng không đồng nghĩa xác thực người dùng có quyền với store đó. Việc xác thực phải thực hiện trước khi gọi fragment, và nên có integration test bảo đảm mọi nhánh đều giữ điều kiện phạm vi.

### 7.3. Kết hợp fragment với repository chính

File `OrderRepository.java` khi chọn cấu trúc fragment:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSearchRepository {
}
```

Spring Data có thể ghép `OrderSearchRepositoryImpl` vào repository theo quy ước interface fragment và hậu tố `Impl`, miễn các class ở trong cấu trúc package/quét repository thích hợp. Nếu dự án tùy chỉnh hậu tố hoặc có nhiều bean cùng tên, cần kiểm tra cấu hình composition thực tế.

Trong bài học, các biến thể `OrderRepository` ở các mục là **lựa chọn tổ chức khác nhau**; khi triển khai, hợp nhất các phương thức được giữ lại vào **một interface repository** theo kiến trúc dự án.

### 7.4. Nếu cần Page<OrderDocument>

Đoạn fragment trả `List` đã có skip/limit/sort theo `Pageable` nhưng **chưa có tổng số bản ghi**. Nếu UI cần `Page`, thực hiện count theo cùng filter **không có paging** rồi dựng `PageImpl`/utility phù hợp. Không dùng nhầm số phần tử của trang làm `totalElements` và không mặc định có count query chỉ vì interface fragment nhận `Pageable`.

## 8. Ví dụ chọn cách làm theo yêu cầu

| Yêu cầu | Lựa chọn hợp lý | Vì sao |
| --- | --- | --- |
| Tìm đơn bằng `storeId` + `orderCode` | Derived query | Tên ngắn, ổn định, dễ hiểu |
| Tìm đơn có mọi nhãn trong `tags` | `@Query` | `$all` biểu diễn rõ yêu cầu |
| Tìm theo nhiều bộ lọc có thể bỏ qua | Custom fragment | Điều kiện được thêm động theo request |
| Nhóm doanh thu theo ngày/tiền tệ | `@Aggregation`/Aggregation API | Cần `$group` và phép tính, không chỉ filter |
| Truy vấn phức tạp dùng `$or`, `$elemMatch` động | Custom fragment | Dễ nhóm điều kiện và test từng nhánh |
| Query cố định có projection cho danh sách | `@Query(fields=...)` | Dễ xem các field trả về |

Việc chọn cơ chế không phụ thuộc vào câu hỏi “công cụ nào mạnh hơn”, mà phụ thuộc **bản chất truy vấn**, cách thay đổi filter và khả năng người đọc bảo trì.

## 9. Những điểm dễ sai khi chuyển đổi giữa ba cách truy vấn

### 9.1. Tên property Java và tên field BSON

Giả sử một model có:

```java
@Field("created_at")
private Instant createdAt;
```

Truy vấn suy diễn phải dùng property Java:

```java
findByCreatedAtGreaterThanEqual(Instant start);
```

Với `@Query` khai báo trên repository của entity và `Criteria` dùng thông qua `MongoTemplate`, Spring Data thông thường áp dụng metadata mapping cho tên field và kiểu giá trị. Đường truy cập trực tiếp qua `MongoTemplate.getCollection(...)` hoặc MongoDB Java driver **không tự xử lý metadata entity như vậy**. Vì thế, nên kiểm tra BSON thực tế sau khi `@Field` hoặc converter thay đổi; đừng chỉ dựa vào tên hiển thị trong IDE.

### 9.2. Kiểu BSON và converter

`OrderStatus.PAID` thường được ánh xạ thành chuỗi `"PAID"` nếu không có converter tùy chỉnh. `Instant` được biểu diễn dưới dạng BSON Date theo cấu hình mapping. `long` trong model tương ứng giá trị số, còn tài liệu cũ có thể đã lưu chuỗi.

Nếu bản ghi cũ lưu `totalMinor: "850000"` (BSON String) nhưng query mới dùng phép so sánh số, document đó có thể **không khớp** mặc dù custom reading converter giúp ứng dụng đọc nó vào object. MongoDB áp dụng filter trên BSON **trước khi** Spring Data chuyển kết quả thành Java.

Tương tự, phân trang/range query không thể sửa lỗi lệch timezone nếu dữ liệu cũ đã lưu `LocalDateTime` bằng quy tắc khác. Cần có fixture từ phiên bản cũ và chiến lược migration rõ ràng.

### 9.3. Đặt điều kiện tenant bên ngoài các nhánh OR

Một truy vấn hợp lý:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  $or: [
    { status: "PAID" },
    { totalMinor: { $gte: NumberLong(1000000) } }
  ]
})
```

`storeId` ở ngoài `$or` nên mọi nhánh vẫn bị giới hạn trong cửa hàng được phép. Nếu vô tình đặt `storeId` **chỉ vào một nhánh**, các nhánh khác có thể trả bản ghi của tenant khác. Cần test rõ điều này, nhất là khi dùng custom query builder dựng các nhóm `andOperator`/`orOperator`.

### 9.4. Toán tử không biến mất khi input null

Với điều kiện `{ status: ?0 }`, tham số null có thể tạo query khớp `null`/field missing theo ngữ nghĩa MongoDB, chứ không phải bỏ filter. Với `$in: []` không có document nào khớp; với `$nin: []` có thể khớp gần như mọi document. Service cần quyết định **ý nghĩa nghiệp vụ** của input rỗng.

Trong custom fragment ở mục 7, `statuses = null` nghĩa là không lọc, còn `statuses = []` nghĩa là không được phép tìm trạng thái nào. Đây là contract của **ứng dụng**, không phải mặc định phổ quát của framework.

### 9.5. JSON binding không thay thế validation

Dùng placeholder `?0` giúp tránh tự nối chuỗi user input vào JSON. Nhưng service vẫn phải:

- Giới hạn kích thước danh sách truyền vào `$in`, `$all` hoặc `$nin`.
- Kiểm tra phép lọc có đúng quyền của người dùng hay không.
- Cẩn trọng với regex do người dùng nhập: escape hoặc thiết kế chế độ tìm kiếm chữ thường, đặt giới hạn độ dài và chi phí thực thi.
- Không cho phép client gửi tùy ý field name/operator MongoDB hoặc một mảnh JSON được ghép trực tiếp vào query.

Nếu cần trường tìm kiếm người dùng chọn, nên ánh xạ từ một **allowlist field** đã được ứng dụng định nghĩa sang `Criteria`, thay vì dùng bất cứ tên field nào client gửi.

## 10. Ranh giới giữa filter, projection và aggregation

| Yêu cầu | Dùng gì? | Vì sao |
| --- | --- | --- |
| Chọn document có trạng thái phù hợp | Derived, `@Query` hoặc `Query`/`Criteria` | Filter thông thường |
| Chỉ trả vài field | Projection qua repository hoặc `Query.fields()` | Giảm dữ liệu đọc/truyền |
| Sắp xếp và phân trang document | `Pageable`/`Sort` hoặc `Query.with(...)` | Hỗ trợ danh sách |
| Tổng hợp số đơn và doanh thu theo ngày | Aggregation API, `@Aggregation` | Cần `$group`/`$dateTrunc` |
| Join dữ liệu từ collection khác | Aggregation `$lookup` hoặc đọc riêng phù hợp | Filter thông thường không tự join |
| Update hàng loạt theo filter | `MongoTemplate.updateMulti(...)`/update API | Thao tác ghi, không phải chỉ đọc |

`@Query` có các lựa chọn như `fields` cho projection. Nó không biến một phép tính grouping thành aggregation. Một custom repository có thể gọi `MongoTemplate.aggregate(...)` nếu nghiệp vụ cần, nhưng việc chọn **tầng chứa code** và việc chọn **loại lệnh MongoDB** là hai quyết định khác nhau.

## 11. Phân trang an toàn, index và chẩn đoán hiệu năng

Ứng dụng thường tìm đơn theo `storeId`, `status` và thời điểm tạo, sau đó sort mới nhất:

```javascript
db.orders.createIndex({
  storeId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

Đây là **index ứng viên**, không phải cấu hình tối ưu bắt buộc. Nếu màn hình tìm theo cửa hàng và thời gian nhưng **không có điều kiện `status`**, index trên có thể không phục vụ thứ tự sort giống với index:

```javascript
db.orders.createIndex({
  storeId: 1,
  createdAt: -1,
  _id: -1
})
```

Không nên tạo mọi index có thể nghĩ ra: mỗi index tăng chi phí dung lượng và cập nhật khi ghi. Cần đo theo truy vấn thường gặp và số lượng dữ liệu đại diện.

Kiểm tra:

```javascript
db.orders
  .find({
    storeId: "STORE-HCM",
    status: { $in: ["NEW", "PAID"] }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Theo dõi `totalKeysExamined`, `totalDocsExamined`, `nReturned`, khả năng dùng index và có phải sort ngoài index không. Nếu so sánh hiệu năng ba lựa chọn Java, cần bảo đảm cả ba **sinh ra cùng BSON filter/projection/sort/limit**. Đổi cách gọi Java nhưng giữ nguyên query thường không làm MongoDB nhanh hơn về bản chất.

Các chi phí ngoài query đơn lẻ cần đo thêm: query count khi trả `Page`, network round-trip, ánh xạ BSON → Java, serialization, các lần truy vấn bổ sung và tính chọn lọc của điều kiện `$in`/`$nin`. `explain` của một lệnh không phải toàn bộ latency của API.

## 12. Kiểm thử tích hợp: cùng yêu cầu, cùng kết quả

Một mock repository có thể trả danh sách đúng dù tên phương thức bị parse sai, `@Query` bind nhầm tham số hoặc custom fragment bỏ điều kiện `storeId`. Vì vậy cần kiểm thử với MongoDB cô lập và BSON thật. `@DataMongoTest` của Spring Boot (với package import phù hợp phiên bản) giúp kiểm thử lớp dữ liệu; cấu hình hạ tầng có thể sử dụng MongoDB test instance/Testcontainers.

### 12.1. Seed và kiểm thử derived query

Ví dụ JUnit 5/AssertJ:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderQueryIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @BeforeEach
    void seed() {
        // Chỉ dùng với database kiểm thử cô lập.
        template.dropCollection(OrderDocument.class);

        template.insertAll(List.of(
            new OrderDocument(
                "O-101", "ORD-101", "STORE-HCM",
                OrderStatus.NEW, 120000L,
                Instant.parse("2026-11-19T02:00:00Z"),
                List.of("web", "priority")),
            new OrderDocument(
                "O-102", "ORD-102", "STORE-HCM",
                OrderStatus.PAID, 850000L,
                Instant.parse("2026-11-19T04:00:00Z"),
                List.of("web")),
            new OrderDocument(
                "O-103", "ORD-103", "STORE-HCM",
                OrderStatus.CANCELLED, 400000L,
                Instant.parse("2026-11-20T01:00:00Z"),
                List.of("app")),
            new OrderDocument(
                "O-104", "ORD-104", "STORE-HCM",
                OrderStatus.PAID, 1500000L,
                Instant.parse("2026-11-20T03:00:00Z"),
                List.of("app", "priority")),
            new OrderDocument(
                "O-105", "ORD-105", "STORE-HN",
                OrderStatus.PAID, 2000000L,
                Instant.parse("2026-11-20T04:00:00Z"),
                List.of("priority"))
        ));
    }

    @Test
    void derivedQueryFiltersStoreAndStatus() {
        var ids = repository.findByStoreIdAndStatus(
                "STORE-HCM", OrderStatus.PAID)
            .stream()
            .map(OrderDocument::id)
            .toList();

        assertThat(ids).containsExactlyInAnyOrder(
            "O-102", "O-104");
    }
}
```

Trong ứng dụng, test phải import/cấu hình đúng repository được lựa chọn. Test `dropCollection` xóa dữ liệu và chỉ được chạy trên **database dành riêng cho test**, tuyệt đối không kết nối tới database chung/production.

### 12.2. Kiểm thử @Query

Nếu inject `OrderJsonQueryRepository` từ mục 5 (hoặc đã chuyển phương thức vào `OrderRepository`), kiểm tra đúng tham số:

```java
var ids = jsonRepository.findWithFixedFilters(
        "STORE-HCM",
        List.of(OrderStatus.PAID),
        Instant.parse("2026-11-19T00:00:00Z"),
        Instant.parse("2026-11-21T00:00:00Z"),
        500000L)
    .stream()
    .map(OrderDocument::id)
    .toList();

assertThat(ids).containsExactlyInAnyOrder(
    "O-102", "O-104");
```

Đây là **đoạn thân test minh họa**; biến `jsonRepository` phải được inject đúng kiểu đã khai báo. Nên bổ sung một test hoán đổi min/max thời gian hoặc giá trị ngưỡng để phát hiện lỗi do bind nhầm `?2`, `?3` và `?4`.

### 12.3. Kiểm thử custom fragment theo ma trận

Với `OrderRepository` đã ghép fragment ở mục 7, chạy các trường hợp:

| Input | Kỳ vọng |
| --- | --- |
| `storeId=STORE-HCM`, filter khác bằng null | Chỉ đơn của HCM, có paging |
| `statuses=[PAID]`, `minimumTotalMinor=1000000` | Chỉ `O-104` |
| `statuses=[]` | Trả list rỗng theo contract |
| `fromInclusive >= beforeExclusive` | Ném lỗi input không hợp lệ |
| `pageable=unpaged` hoặc page size quá lớn | Ném lỗi validation |
| `storeId=STORE-HCM`, dữ liệu HN vẫn thỏa filter | Không có `O-105` |
| Có đúng một ranh giới thời gian | Query vẫn hợp lệ và đúng khoảng |

Trong các test phạm vi truy cập, đừng chỉ xác nhận những ID đúng xuất hiện: phải **khẳng định ID của tenant khác không xuất hiện**. Test nên gồm cả dữ liệu lưu theo định dạng BSON cũ khi nâng cấp model hoặc converter.

### 12.4. Kiểm tra câu BSON được phát ra

Với query do `MongoTemplate` dựng, có thể quan sát `Query.getQueryObject()` và ghi log phù hợp trong test, nhưng object ở tầng `Query` có thể vẫn dùng property Java trước khi mapping sang tên BSON. Để kiểm tra query chính xác gửi xuống driver, sử dụng **MongoDB command monitoring** hoặc công cụ logging phù hợp, tránh giả định một đối tượng Criteria là toàn bộ lệnh cuối cùng.

Không bật profiler/command debug không giới hạn trên production. Khi đo chi phí truy vấn, cần xét dữ liệu thực và quyền truy cập log.

## 13. Reactive access và những giới hạn chung

Với `ReactiveMongoRepository` và `ReactiveMongoTemplate`, cách lựa chọn tương tự, nhưng phương thức trả `Flux<T>` hoặc `Mono<T>`:

```java
import java.util.Collection;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByStoreIdAndStatusIn(
        String storeId,
        Collection<OrderStatus> statuses);

    @Query("{ 'storeId': ?0, 'totalMinor': { '$gte': ?1 } }")
    Flux<OrderDocument> findExpensiveOrders(
        String storeId, long minimumTotalMinor);
}
```

Với filter động, custom reactive fragment phải dùng `ReactiveMongoTemplate` thay vì gọi `MongoTemplate` blocking trong luồng reactive rồi kỳ vọng nó tự chuyển thành non-blocking. Test reactive cần **subscribe** publisher, chẳng hạn bằng `StepVerifier`.

Các quyết định về field mapping, type BSON, tenant, phân trang, index và nhất quán không thay đổi chỉ vì dùng reactive. Nếu thao tác nghiệp vụ cần cập nhật nhiều document cùng một giao dịch, đó là vấn đề thiết kế **transaction** độc lập với ba cách tổ chức truy vấn đọc.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Lỗi parse tên hàm repository | Sai property Java hoặc keyword derived query | Kiểm tra model, rút tên hàm hoặc dùng `@Query` |
| `@Query` trả sai do vị trí tham số | Thứ tự `?0`, `?1` không khớp chữ ký | Kiểm thử với giá trị khác nhau ở từng tham số |
| JSON trong annotation không hợp lệ | Sai cấu trúc operator/dấu ngoặc | Integration test, chuyển sang Criteria nếu query quá dài |
| Request không có filter nhưng kết quả rỗng | Truyền null/empty theo semantics của operator | Định nghĩa contract cho input rỗng tại service |
| Rò rỉ dữ liệu tenant | Quên `storeId` trong một nhánh `$or` hoặc query fallback | Kiểm tra quyền, giữ điều kiện tenant mọi nhánh và anti-leak test |
| Projection chỉ chứa một phần entity | Dùng `fields` nhưng trả entity đầy đủ rồi `save` | Dùng read-only projection/DTO |
| Custom repository method không được gọi | Fragment implementation sai tên/package hoặc chưa ghép interface | Kiểm tra interface fragment, hậu tố `Impl`, repository scan |
| Custom query rất chậm | Điều kiện ít chọn lọc hoặc index không phù hợp | Xem `explain` và thống kê chi phí toàn request |
| `Page` tốn kém | Count query lớn hoặc truy vấn sort thiếu index | Cân nhắc `Slice`/keyset, điều chỉnh index |
| Dữ liệu cũ bị bỏ qua | Kiểu BSON cũ khác kiểu query hiện tại | Golden fixtures, kiểm kê dữ liệu, migration |
| Reactive endpoint vẫn chặn luồng | Dùng `MongoTemplate` hoặc repository blocking | Dùng reactive infrastructure thực sự |

## 15. Checklist chọn kỹ thuật truy vấn

Trước khi tạo phương thức:

1. **Điều kiện cố định hay tùy chọn?** Bao nhiêu nhánh cần thêm/bỏ trong runtime?
2. **Tên derived query có dễ đọc không?** Nếu chỉ vài điều kiện, không cần abstraction thêm.
3. **Có toán tử MongoDB phù hợp biểu thức JSON rõ hơn không?** Ví dụ `$all`, `$elemMatch`.
4. **Có đang làm aggregation không?** Nếu có, chọn `@Aggregation` hoặc Aggregation API.
5. **Có cần projection và paging không?** Tránh save lại entity chỉ đọc một phần.
6. **Điều kiện tenant luôn có mặt và được xác thực không?**
7. **Rỗng, null và giá trị thiếu có ý nghĩa gì trong nghiệp vụ?**
8. **Converter, enum, ID, thời gian và field name có khớp BSON đã lưu không?**
9. **Có index phục vụ filter/sort và đã đo `explain` không?**
10. **Đã test với MongoDB và dữ liệu nhiều tenant/legacy chưa?**

## 16. Bài tập vận dụng

Một hệ thống logistics có collection `shipments` với `tenantId`, `trackingCode`, `status`, `priority`, `createdAt` và mảng `events` gồm `{ at, kind, locationCode }`. Cần hỗ trợ:

1. Tìm shipment bằng `tenantId` và `trackingCode`.
2. Tìm shipment có trạng thái thuộc danh sách và `priority >= 5`, với bộ lọc cố định.
3. Tìm kiếm nâng cao có trạng thái, khoảng thời gian và vị trí sự kiện tùy chọn, có phân trang.
4. Thống kê số shipment theo trạng thái và tuần trong múi giờ kinh doanh.

**Định hướng:**

- Bài toán 1: derived query, chẳng hạn `findByTenantIdAndTrackingCode(...)`.
- Bài toán 2: `@Query` với `$in` và `$gte`, hoặc derived query nếu tên vẫn dễ hiểu.
- Bài toán 3: custom fragment với `Criteria`; dùng `$elemMatch` nếu nhiều điều kiện phải khớp **cùng phần tử** của `events`.
- Bài toán 4: Aggregation API/`@Aggregation` với `$group` và phép nhóm ngày/tuần có timezone.

Hãy kiểm tra thêm các trường hợp danh sách trạng thái rỗng, ranh giới thời gian không hợp lệ và kết quả của tenant khác. Viết test chứng minh mọi cách truy vấn đều giữ `tenantId`, sau đó đo index trên dữ liệu tương đương sản xuất.

## 17. Tài liệu tham khảo

- Spring Data MongoDB — [Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived query, `@Query` và repository.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments và quy ước implementation.
- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `MongoTemplate`, `Query` và `Criteria`.
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): pipeline và Aggregation API.
- MongoDB Manual — [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/): bộ lọc và toán tử MongoDB.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): kế hoạch và chỉ số thực thi.

## Ghi nhớ

**Truy vấn suy diễn** tối ưu cho điều kiện ngắn, ổn định và có tên dễ hiểu. **`@Query`** phù hợp với filter JSON cố định, toán tử đặc thù và projection. **Custom repository fragment với `MongoTemplate`** phù hợp khi phải ghép điều kiện động hoặc tái sử dụng query builder. Khi cùng gửi một BSON query, ba cách không có phép màu hiệu năng khác nhau; điều quyết định là **đúng hợp đồng nghiệp vụ, phạm vi tenant, kiểu BSON, index và kiểm thử tích hợp**. Chọn cách đơn giản nhất vẫn giữ được những yêu cầu đó.
