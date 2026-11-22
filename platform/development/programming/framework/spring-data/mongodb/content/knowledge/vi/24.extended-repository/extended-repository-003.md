# Kết hợp MongoOperations với truy vấn có mô hình miền

> **Chương:** Repository mở rộng  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Kết hợp repository chuẩn với một custom repository fragment dùng `MongoOperations`, chuyển tiêu chí truy vấn từ ngôn ngữ nghiệp vụ sang `Criteria`/`Query` có kiểm soát, bảo toàn ánh xạ entity, tenant và thứ tự phân trang; biết khi nào nên dùng `find`, `count`, `findAndModify`, projection hoặc aggregation và cách kiểm thử truy vấn đó trên MongoDB thật.

## 1. Vì sao repository thông thường chưa đủ?

`MongoRepository<OrderDocument, String>` rất tiện cho các thao tác `findById`, `save`, `deleteById` và các derived query ngắn:

~~~java
List<OrderDocument> findByTenantIdAndState(
    String tenantId,
    OrderState state
);
~~~

Nhưng màn hình tìm kiếm đơn hàng thực tế thường có nhiều tiêu chí **tùy chọn**:

- Đơn hàng thuộc tenant đã xác thực và một hoặc nhiều trạng thái nghiệp vụ.
- Thời gian tạo thuộc một khoảng `[from, before)`.
- Tổng tiền tối thiểu.
- Có **một dòng hàng cụ thể** thỏa cả SKU và số lượng tối thiểu.
- Phân trang theo thời gian tạo giảm dần, dùng `_id` làm khóa phụ để kết quả ổn định.

Nếu tạo một derived method cho **mọi tổ hợp** trường, repository sẽ xuất hiện những tên dài, các phương thức gần giống nhau và rất khó kiểm soát điều kiện nghiệp vụ quan trọng. Tự ghép chuỗi JSON `@Query` từ request cũng làm tăng nguy cơ sai kiểu, sai tên BSON và thiếu điều kiện phân quyền.

Giải pháp: giữ **repository chuẩn** cho CRUD và dùng **custom repository fragment** cho phần truy vấn phức tạp. Fragment chứa một lớp triển khai sử dụng `MongoOperations` — interface mà `MongoTemplate` triển khai.

~~~mermaid
flowchart TD
    A["HTTP / scheduled job"] --> B["Application service"]
    B --> C["OrderRepository"]
    C --> D["MongoRepository: CRUD / derived finder"]
    C --> E["OrderSearchRepository: custom fragment"]
    E --> F["OrderSearchRepositoryImpl"]
    F --> G["MongoOperations / MongoTemplate"]
    D --> H[("MongoDB")]
    G --> H
~~~

**Quan điểm thiết kế:** Truy vấn được xây từ **khái niệm miền** (`OrderSearchFilter`, `OrderState`, “một dòng SKU A với số lượng ít nhất 5”`), chứ không để controller biết `$elemMatch`, `$gte`, tên collection hay tên trường BSON.

## 2. Phân biệt ba lớp khái niệm

| Lớp | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Tiêu chí nghiệp vụ** | `OrderSearchFilter(state, from, before, minTotal, sku, minQty)` | Diễn đạt người dùng muốn tìm gì; xác thực ràng buộc và ngữ nghĩa |
| **Spring Data query** | `Criteria.where("state").is(PAID)`, `Query`, `Pageable` | Chuyển tiêu chí thành predicate, sort, limit, projection |
| **Truy vấn BSON thực thi** | `{ state_code: "PAID", tenant_id: "t01" }` | Hợp đồng với MongoDB; dùng tên và kiểu BSON thực |

`MongoOperations` kết nối lớp thứ hai với lớp thứ ba thông qua `MappingMongoConverter`/`QueryMapper` khi bạn gọi phương thức có **entity class**. Nghĩa là:

~~~java
Criteria.where("tenantId").is("t01");
~~~

được ánh xạ thành điều kiện trên field BSON `tenant_id` nếu entity khai báo `@Field("tenant_id")`.

Ngược lại, khi dùng MongoDB Java Driver trực tiếp:

~~~java
Filters.eq("tenant_id", "t01");
~~~

bạn phải dùng **tên BSON thực**, vì driver không tự hiểu `@Field` của Spring Data. Bài này ưu tiên `MongoOperations` với metadata entity và chỉ dùng raw BSON khi kiểm chứng.

## 3. Dữ liệu mẫu để thực hành

### 3.1. Collection thử nghiệm

Mở `mongosh` trên một **database test riêng**, tạo fixture như sau. Các ID cố định chỉ để đối chiếu kết quả; không chạy lại `insertMany` nếu collection đã có các ID này.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_extended_demo_003;

orders.insertMany([
  {
    _id: "o301", tenant_id: "t01", state_code: "NEW",
    created_at: ISODate("2026-10-01T08:00:00Z"),
    total_vnd: 150000,
    line_items: [
      { sku: "A", quantity: 1 },
      { sku: "B", quantity: 8 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o302", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-02T08:00:00Z"),
    total_vnd: 450000,
    line_items: [
      { sku: "A", quantity: 6 },
      { sku: "C", quantity: 2 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o303", tenant_id: "t01", state_code: "NEW",
    created_at: ISODate("2026-10-03T08:00:00Z"),
    total_vnd: 800000,
    line_items: [
      { sku: "A", quantity: 3 },
      { sku: "A", quantity: 9 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o304", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-04T08:00:00Z"),
    total_vnd: 250000,
    line_items: [
      { sku: "B", quantity: 7 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o305", tenant_id: "t02", state_code: "PAID",
    created_at: ISODate("2026-10-05T08:00:00Z"),
    total_vnd: 900000,
    line_items: [
      { sku: "A", quantity: 10 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o306", tenant_id: "t01", state_code: "CANCELLED",
    created_at: ISODate("2026-10-06T08:00:00Z"),
    total_vnd: 100000,
    line_items: [],
    version: NumberLong(0)
  },
  {
    _id: "o307", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-04T08:00:00Z"),
    total_vnd: 650000,
    line_items: [
      { sku: "A", quantity: 5 }
    ],
    version: NumberLong(0)
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  created_at: -1,
  _id: -1
});
~~~

Các kết quả dự đoán trong bài dùng **fixture ban đầu**; những ví dụ ghi ở phần sau được coi là kịch bản độc lập trên database test.

| ID | Tenant | State | Tổng tiền (VND) | Điểm đáng chú ý |
| --- | --- | --- | ---: | --- |
| `o301` | t01 | NEW | 150.000 | Có A × 1 và B × 8; hai điều kiện không thuộc cùng dòng |
| `o302` | t01 | PAID | 450.000 | Có dòng A × 6 |
| `o303` | t01 | NEW | 800.000 | Có A × 3 và A × 9 |
| `o304` | t01 | PAID | 250.000 | Chỉ có B × 7 |
| `o305` | t02 | PAID | 900.000 | Thuộc tenant khác |
| `o306` | t01 | CANCELLED | 100.000 | Mảng dòng hàng rỗng |
| `o307` | t01 | PAID | 650.000 | Có A × 5; cùng thời điểm tạo với o304 |

`o304` và `o307` có cùng `created_at`. Khi phân trang, **không được chỉ sắp xếp theo thời gian** nếu muốn thứ tự tất định; dùng thêm `_id` làm tie-breaker.

### 3.2. Đối chiếu truy vấn mong đợi bằng `mongosh`

Ví dụ: tìm đơn của tenant t01, trạng thái PAID, tổng tiền từ 400.000 và có một dòng A với `quantity >= 5`:

~~~javascript
orders.find({
  tenant_id: "t01",
  state_code: "PAID",
  total_vnd: { $gte: 400000 },
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}).sort({ created_at: -1, _id: -1 });
// o307, o302
~~~

`o305` có A × 10 nhưng thuộc tenant t02; `o303` đủ số lượng và tiền nhưng trạng thái NEW; `o304` PAID nhưng không có A. Đây là bộ dữ liệu giúp kiểm thử cả **điều kiện miền** lẫn **phân quyền tenant**.

## 4. Domain model và metadata ánh xạ

### 4.1. Enum trạng thái

~~~java
// OrderState.java
package com.example.extended;

public enum OrderState {
    NEW, PAID, PROCESSING, CANCELLED
}
~~~

Spring Data MongoDB mặc định ánh xạ các giá trị enum phù hợp sang chuỗi như `"PAID"`. Nếu ứng dụng dùng converter riêng hoặc kiểu BSON khác, cần kiểm chứng lại với fixture thật.

### 4.2. Embedded line item

~~~java
// OrderLine.java
package com.example.extended;

public class OrderLine {
    private String sku;
    private int quantity;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

`OrderLine` là một object **nhúng trong document đơn hàng**, không phải collection riêng. Nếu thiết kế thực dùng `@DBRef` hoặc `@DocumentReference` thì truy vấn và chi phí resolve reference cần phân tích khác.

### 4.3. Aggregate root

~~~java
// OrderDocument.java
package com.example.extended;

import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_extended_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("created_at")
    private Instant createdAt;

    @Field("total_vnd")
    private long totalVnd;

    @Field("line_items")
    private List<OrderLine> lineItems;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public OrderState getState() { return state; }
    public Instant getCreatedAt() { return createdAt; }
    public long getTotalVnd() { return totalVnd; }
    public List<OrderLine> getLineItems() { return lineItems; }
    public Long getVersion() { return version; }
}
~~~

Ở ví dụ này:

- `@Document` xác định collection.
- `@MongoId(FieldType.STRING)` giữ `_id` dạng BSON string.
- `@Field("tenant_id")` và các annotation tương tự giúp `MongoOperations` ánh xạ đường dẫn Java sang tên BSON.
- `@Version` hỗ trợ cơ chế version ở những thao tác Spring Data phù hợp; **không** có nghĩa mọi query tự biết phiên bản client đã nhìn thấy.

Không nên trả thẳng entity này cho API public nếu trong hệ thống thực nó chứa thuộc tính nội bộ. Bài sẽ dùng read DTO ở service khi cần trả dữ liệu ra ngoài.

## 5. Thiết kế bộ lọc nghiệp vụ độc lập với MongoDB

Controller và service không nên nhận `Criteria`/`Query` từ client. Thay vào đó, định nghĩa một kiểu dữ liệu đại diện cho **yêu cầu tìm kiếm**:

~~~java
// OrderSearchFilter.java
package com.example.extended;

import java.time.Instant;

public record OrderSearchFilter(
    OrderState state,
    Instant createdFromInclusive,
    Instant createdBeforeExclusive,
    Long minTotalVnd,
    String sku,
    Integer minLineQuantity
) {
    public OrderSearchFilter {
        if (createdFromInclusive != null
                && createdBeforeExclusive != null
                && !createdFromInclusive.isBefore(createdBeforeExclusive)) {
            throw new IllegalArgumentException(
                "createdFrom must be before createdBefore");
        }
        if (minTotalVnd != null && minTotalVnd < 0) {
            throw new IllegalArgumentException("minTotalVnd must be >= 0");
        }
        if (sku != null && sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (minLineQuantity != null && minLineQuantity < 1) {
            throw new IllegalArgumentException(
                "minLineQuantity must be >= 1");
        }
        if (minLineQuantity != null && sku == null) {
            throw new IllegalArgumentException(
                "minLineQuantity requires sku");
        }
    }
}
~~~

`OrderSearchFilter` không chứa `tenantId`. Đây là quyết định có chủ ý: **tenant được lấy từ ngữ cảnh bảo mật ở tầng service**, không phải lựa chọn do client tự quyết định.

### 5.1. Ý nghĩa của khoảng thời gian `[from, before)`

Nếu `createdFromInclusive` có giá trị, query dùng `createdAt >= from`. Nếu `createdBeforeExclusive` có giá trị, query dùng `createdAt < before`.

~~~text
          from                        before
           [--------------------------)
     Bao gồm from                 Không bao gồm before
~~~

Quy tắc này rất hữu ích cho báo cáo theo ngày/giờ và xử lý các khoảng liên tiếp mà không đếm trùng mốc biên. Dùng `Instant`/BSON Date trên trục thời gian UTC; múi giờ hiển thị của người dùng cần được xử lý trước khi tạo filter, không tự gán một `LocalDateTime` tùy tiện vào database.

### 5.2. Không nhập thẳng field name từ HTTP

Các tiêu chí `state`, `minTotalVnd`, `sku` là một tập được thiết kế trước. Tránh API nhận:

~~~json
{
  "field": "internalDiscount",
  "operator": "$gt",
  "value": 0
}
~~~

rồi biến nó thành `Criteria.where(field)` không kiểm soát. Cách đó có thể cho client truy vấn trường ngoài phạm vi, tạo query tốn tài nguyên hoặc bỏ qua điều kiện tenant. Nếu cần query builder động theo các trường tùy chọn của UI, hãy dùng **allowlist** trường và operator do server sở hữu.

## 6. Tạo custom repository fragment

Spring Data cho phép ghép repository chính từ repository cơ sở và **những interface fragment** do dự án định nghĩa.

### 6.1. Interface của fragment

~~~java
// OrderSearchRepository.java
package com.example.extended;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository {
    Page<OrderDocument> search(
        String authorizedTenantId,
        OrderSearchFilter filter,
        Pageable pageable
    );
}
~~~

Tên `authorizedTenantId` nhấn mạnh service phải đưa **tenant đã xác thực** vào query. Trong triển khai production, có thể thay chuỗi bằng value object `TenantId` để tránh truyền nhầm tham số.

### 6.2. Repository chính ghép với fragment

~~~java
// OrderRepository.java
package com.example.extended;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSearchRepository {
    // CRUD của MongoRepository và method search của fragment.
}
~~~

Giờ tầng service có thể dùng một đối tượng `OrderRepository` để gọi `findById`, `save` và `search`. Bạn không phải tự subclass `SimpleMongoRepository` chỉ để bổ sung một truy vấn phức tạp.

### 6.3. Quy tắc tên implementation

Theo cơ chế repository composition, tên implementation của fragment thường là:

~~~text
Interface:       OrderSearchRepository
Implementation:  OrderSearchRepositoryImpl
Repository:      OrderRepository extends ..., OrderSearchRepository
~~~

Class `OrderSearchRepositoryImpl` phải nằm trong phạm vi package được Spring Data quét và có constructor injection hợp lệ. Suffix mặc định là `Impl`; nếu dự án đã cấu hình implementation postfix khác, hãy tuân theo cấu hình đó.

**Đừng đặt ngẫu nhiên `OrderRepositoryImpl` và giả định Spring Data luôn hiểu đây là implementation của riêng fragment.** Mô hình gắn class triển khai theo **tên interface fragment** rõ nghĩa hơn, tái sử dụng được và phù hợp thiết kế repository fragments hiện đại.

### 6.4. Repository composition khác tự tạo service thứ hai

Bạn hoàn toàn có thể inject `MongoOperations` vào một `@Service` riêng để chạy query. Fragment hữu ích khi muốn:

- Giữ **một cổng truy cập dữ liệu** `OrderRepository` cho cả CRUD và truy vấn tùy biến.
- Che giấu chi tiết Spring Data khỏi service gọi.
- Tái sử dụng logic query ở nhiều nghiệp vụ.
- Dễ thay đổi cách truy vấn trong fragment mà không làm đổi hợp đồng repository chính.

Không phải mọi query đều cần một fragment mới. Nếu chỉ có `findByState` hoặc `findByTenantId` đơn giản, derived query bình thường là đủ.

## 7. Triển khai fragment bằng `MongoOperations`

Lớp dưới đây chỉ sử dụng API đọc, chọn domain criteria và tách **count query** khỏi **page content query**.

~~~java
// OrderSearchRepositoryImpl.java
package com.example.extended;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final MongoOperations operations;

    public OrderSearchRepositoryImpl(MongoOperations operations) {
        this.operations = operations;
    }

    @Override
    public Page<OrderDocument> search(
            String authorizedTenantId,
            OrderSearchFilter filter,
            Pageable pageable) {

        if (authorizedTenantId == null || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        Objects.requireNonNull(filter, "filter");
        Objects.requireNonNull(pageable, "pageable");

        // Repository sở hữu quy tắc sort, không tin một sort tùy ý từ UI.
        if (pageable.isUnpaged()) {
            throw new IllegalArgumentException("Pagination is required");
        }
        if (pageable.getPageSize() > 100) {
            throw new IllegalArgumentException("Page size exceeds 100");
        }

        Criteria criteria = buildCriteria(authorizedTenantId, filter);
        Sort stableSort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        );

        Pageable stablePageable =
            org.springframework.data.domain.PageRequest.of(
                pageable.getPageNumber(),
                pageable.getPageSize(),
                stableSort
            );

        Query contentQuery = Query.query(criteria).with(stablePageable);
        List<OrderDocument> content =
            operations.find(contentQuery, OrderDocument.class);

        // Count theo đúng predicate, không mang skip/limit.
        Query countQuery = Query.query(
            buildCriteria(authorizedTenantId, filter)
        );
        long total = operations.count(countQuery, OrderDocument.class);

        return new PageImpl<>(content, stablePageable, total);
    }

    private Criteria buildCriteria(
            String tenantId, OrderSearchFilter filter) {

        List<Criteria> parts = new ArrayList<>();
        parts.add(Criteria.where("tenantId").is(tenantId));

        if (filter.state() != null) {
            parts.add(Criteria.where("state").is(filter.state()));
        }

        if (filter.createdFromInclusive() != null
                || filter.createdBeforeExclusive() != null) {
            Criteria time = Criteria.where("createdAt");
            if (filter.createdFromInclusive() != null) {
                time.gte(filter.createdFromInclusive());
            }
            if (filter.createdBeforeExclusive() != null) {
                time.lt(filter.createdBeforeExclusive());
            }
            parts.add(time);
        }

        if (filter.minTotalVnd() != null) {
            parts.add(
                Criteria.where("totalVnd").gte(filter.minTotalVnd())
            );
        }

        if (filter.sku() != null) {
            Criteria sameLine = Criteria.where("sku").is(filter.sku());
            if (filter.minLineQuantity() != null) {
                sameLine.and("quantity").gte(filter.minLineQuantity());
            }
            parts.add(
                Criteria.where("lineItems").elemMatch(sameLine)
            );
        }

        return new Criteria().andOperator(
            parts.toArray(new Criteria[0])
        );
    }
}
~~~

Ở đây `MongoOperations` là **interface**. Spring Boot/Spring Data thường cung cấp `MongoTemplate` làm bean triển khai khi MongoDB sync được cấu hình. Truy vấn dùng phương thức có `OrderDocument.class` để bộ converter biết entity nào đang được ánh xạ.

### 7.1. Vì sao code không nhận chuỗi JSON `@Query`?

Các điều kiện được xây từ những field **đã biết trước**: `tenantId`, `state`, `createdAt`, `totalVnd`, `lineItems`. Phần giá trị được đưa vào `Criteria` dưới đúng kiểu `OrderState`, `Instant`, `Long` và `String`.

Nhờ vậy, cùng một bộ lọc miền có thể đi qua:

~~~text
OrderSearchFilter
    ↓ validate
Criteria / Query
    ↓ MappingMongoConverter + QueryMapper
BSON filter với tenant_id, state_code, created_at, total_vnd, line_items
    ↓
MongoDB
~~~

Không cần tự viết một parser nhận toán tử MongoDB từ input người dùng.

### 7.2. Vì sao count query được xây riêng?

`Query` dùng cho nội dung có `skip`, `limit` và `sort` từ `Pageable`. Để trả về tổng số document theo filter, code tạo **một query khác**, không mang các giới hạn ấy.

~~~java
Query contentQuery = Query.query(criteria).with(stablePageable);

Query countQuery = Query.query(
    buildCriteria(authorizedTenantId, filter)
);
~~~

Nếu copy một query rồi quên loại `skip`/`limit`, rất dễ hiểu sai semantics của count hoặc phụ thuộc vào cách xử lý metadata của từng API/phiên bản. Tách ra hai query rõ ràng giúp giữ **cùng predicate** và phân biệt mục đích.

Lời gọi `operations.count(...)` có thể phát sinh truy vấn bổ sung, vì vậy `Page` không phải lúc nào cũng là lựa chọn tốt nhất cho infinite scroll hoặc danh sách rất lớn.

### 7.3. Thứ tự phân trang phải tất định

`createdAt` có thể trùng giữa nhiều order. Sort:

~~~java
Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

được ánh xạ thành sort BSON theo `created_at DESC, _id DESC`. `_id` là duy nhất, giúp thứ tự ổn định khi nhiều document có cùng timestamp.

Tuy nhiên, **sort ổn định không tạo snapshot bất biến**: nếu có insert/delete/update vào tập kết quả giữa các request offset-page, vẫn có thể bị lặp hoặc bỏ sót record. Khi cần duyệt liên tục ở quy mô lớn, cân nhắc keyset/seek pagination.

### 7.4. Giới hạn page size và offset

Trong ví dụ, page size bị giới hạn ở 100. Production còn nên giới hạn **offset tối đa** hoặc chuyển sang cursor cho trang sâu. Index giúp lọc/sort nhưng không khiến `skip(200000)` trở thành phép nhảy ngẫu nhiên chi phí cố định.

Nếu UI chỉ cần “Xem thêm”, có thể trả `Slice<OrderDocument>` hoặc một DTO `items/hasNext/nextCursor` thay vì trả toàn bộ `totalPages`.

## 8. Ngữ nghĩa miền cho mảng: dùng `$elemMatch` đúng chỗ

Điều kiện:

> Một order phải có **một dòng** SKU A với `quantity >= 5`.

Không tương đương với:

~~~javascript
{
  "line_items.sku": "A",
  "line_items.quantity": { $gte: 5 }
}
~~~

Hai điều kiện dot notation độc lập có thể khớp **hai phần tử khác nhau** trong mảng. `o301` có A × 1 và B × 8: document khớp cả hai điều kiện riêng, nhưng **không có dòng A × 5 trở lên**.

Khi filter vừa có SKU vừa có số lượng, fragment dùng:

~~~java
Criteria sameLine = Criteria.where("sku").is("A")
    .and("quantity").gte(5);

Criteria items = Criteria.where("lineItems")
    .elemMatch(sameLine);
~~~

Nhờ `$elemMatch`, mỗi điều kiện trong `sameLine` được xét trên **cùng một phần tử mảng**.

Truy vấn BSON về ý nghĩa:

~~~javascript
{
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}
~~~

Với fixture:

| Order | Có SKU A? | Có bất kỳ dòng quantity ≥ 5? | Có **cùng một dòng A** quantity ≥ 5? |
| --- | --- | --- | --- |
| `o301` | Có | Có, B × 8 | **Không** |
| `o302` | Có | Có, A × 6 | Có |
| `o303` | Có | Có, A × 9 | Có |
| `o304` | Không | Có, B × 7 | Không |
| `o305` | Có | Có, A × 10 | Có, nhưng khác tenant |
| `o306` | Không | Không | Không |
| `o307` | Có | Có, A × 5 | Có |

### 8.1. Phạm vi một phần tử khác phạm vi một order

`$elemMatch` là predicate **chọn order** có một dòng thỏa điều kiện. Nó **không** bảo đảm trường `lineItems` trong entity kết quả chỉ còn những phần tử đã khớp. Theo mặc định, MongoDB vẫn trả cả mảng nếu không có projection/aggregation riêng.

Nếu API cần chỉ những dòng phù hợp, hãy thiết kế phép chiếu (`$elemMatch` projection chỉ một phần tử đầu tiên; aggregation `$filter` cho tất cả phần tử phù hợp). Đừng nhầm “filter chọn document” với “lọc cấu trúc output”.

### 8.2. Tên Java và tên BSON

Trong entity:

~~~java
@Field("line_items")
private List<OrderLine> lineItems;
~~~

Với `MongoOperations.find(query, OrderDocument.class)`, Spring Data sử dụng metadata này để ánh xạ `lineItems` sang `line_items`. Nếu đi thẳng xuống Java driver qua `MongoCollection<Document>`, bạn phải dùng `"line_items"` trong BSON filter.

Việc tách truy vấn miền ra fragment tránh để tầng service phải giữ cả hai hệ tên field.

## 9. Gọi fragment từ application service

Controller có thể chuyển các input đã validate thành `OrderSearchFilter`. Service cần thêm điều kiện **tenant đã xác thực** trước khi truy cập repository:

~~~java
// OrderCard.java
package com.example.extended;

import java.time.Instant;

public record OrderCard(
    String id,
    OrderState state,
    Instant createdAt,
    long totalVnd
) {
    public static OrderCard from(OrderDocument source) {
        return new OrderCard(
            source.getId(),
            source.getState(),
            source.getCreatedAt(),
            source.getTotalVnd()
        );
    }
}
~~~

~~~java
// OrderQueryService.java
package com.example.extended;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Page<OrderCard> searchOrders(
            String authenticatedTenantId,
            OrderSearchFilter filter,
            Pageable pageable) {
        // authenticatedTenantId phải đến từ security context đã xác thực;
        // không tin client tự chỉ định tenant khác.
        return repository.search(
            authenticatedTenantId, filter, pageable
        ).map(OrderCard::from);
    }
}
~~~

`Page.map(...)` chuyển content của trang sang read DTO nhưng giữ metadata phân trang. Không trả nguyên `OrderDocument` ra API nếu aggregate chứa thông tin nội bộ, quan hệ nhúng lớn hoặc trường nhạy cảm.

**Cảnh báo hiệu năng:** Cách viết trên chuyển sang DTO **sau khi đọc entity**. Nó **không bảo đảm** MongoDB chỉ gửi về bốn trường DTO; server có thể vẫn trả toàn bộ `line_items`. Nếu yêu cầu giảm payload là quan trọng, xem field projection ở phần 11.

### 9.1. Request ví dụ

~~~java
OrderSearchFilter filter = new OrderSearchFilter(
    OrderState.PAID,
    null,
    null,
    400_000L,
    "A",
    5
);

var pageable = org.springframework.data.domain.PageRequest.of(0, 10);

Page<OrderCard> page = service.searchOrders(
    "t01", filter, pageable
);
// Dữ liệu gốc: [o307, o302], theo createdAt DESC, id DESC.
~~~

Truy vấn được tạo từ `OrderSearchFilter` và tenant do server cung cấp. Không đưa `PageRequest` từ phía client đi thẳng vào repository nếu chưa giới hạn size/sort; fragment ở mục 7 tự thay sort và đặt trần size.

## 10. Query linh hoạt nhưng không làm hỏng giới hạn miền

Một số cải tiến giúp fragment dễ bảo trì khi bộ lọc tăng lên:

### 10.1. Gom điều kiện trong một builder có phạm vi

Thay vì cho mọi nơi trong ứng dụng tự gọi `Criteria.where("tenantId")`, đưa điều kiện tenant vào một **hàm duy nhất** trong repository fragment. Điều này giảm khả năng quên tenant khi thêm bộ lọc mới.

~~~java
private Criteria mandatoryScope(String tenantId) {
    return Criteria.where("tenantId").is(tenantId);
}
~~~

Trong ứng dụng có quy tắc soft delete, có thể thêm `deletedAt == null/missing` hoặc một flag trạng thái phù hợp vào cùng phạm vi. Nhưng phải xác định chính xác semantics MongoDB của `null` vs missing, không tự thêm bộ lọc giả định nếu schema chưa quy định.

### 10.2. Tránh một “query object” đa năng vô hạn

Một record có hàng chục field nullable, operator tùy ý, kết hợp `AND/OR` nhiều cấp và biểu thức do client nhập sẽ khó validate và audit. Hãy tạo các use case riêng như:

- `searchForBackOffice(...)`: nhiều bộ lọc nhưng giới hạn được.
- `findOrdersToRetry(...)`: tiêu chí hệ thống, cố định trạng thái và thời gian.
- `claimNextOrder(...)`: thao tác tìm-và-sửa nguyên tử, không phải search pagination.

Cùng thuộc một bounded context, nhưng **mỗi hành vi có hợp đồng nghiệp vụ khác nhau**. `MongoOperations` là công cụ diễn đạt truy vấn, không thay thế việc xác định các ràng buộc miền.

### 10.3. Query nội bộ không làm lộ toán tử MongoDB

Controller nhận tiêu chí nghiệp vụ:

~~~json
{
  "state": "PAID",
  "minTotalVnd": 400000,
  "sku": "A",
  "minLineQuantity": 5
}
~~~

Nó không nhận một đoạn `{ "$where": "..." }` hoặc tên field tùy ý. Fragment có trách nhiệm chọn operator được phép. Validation của request, authentication và authorization cần được đặt ở tầng phù hợp; `OrderSearchFilter` chỉ lo tính hợp lệ **cấu trúc yêu cầu**, không phải toàn bộ quy tắc quyền.

## 11. Projection và giảm dữ liệu cần tải

Nếu màn hình danh sách chỉ cần ID, state, thời gian và tổng tiền, đọc toàn bộ `OrderDocument` có thể tải cả mảng `line_items` rất lớn. Có thể khai báo field mask **trước khi `find`**:

~~~java
Query lightQuery = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)
);

lightQuery.fields()
    .include("id")
    .include("state")
    .include("createdAt")
    .include("totalVnd");

List<OrderDocument> lightResults =
    operations.find(lightQuery, OrderDocument.class);
~~~

Với kiểu entity `OrderDocument.class`, Spring Data ánh xạ các property `id`, `state`, `createdAt`, `totalVnd` sang BSON `_id`, `state_code`, `created_at`, `total_vnd` theo metadata. Điều kiện và projection phải được kiểm tra trong integration test khi dùng `@Field` aliases hoặc converter tùy biến.

**Quan trọng:** Mỗi `OrderDocument` được trả về ở đây là **partial entity** — không có `lineItems` hoặc các field khác bị loại. **Không gọi `repository.save(lightResults.get(0))`** để cập nhật một vài trường: thao tác save có thể ghi thay thế document và làm mất trường không được tải.

Với read model, nên chuyển ngay sang `OrderCard`:

~~~java
List<OrderCard> cards = lightResults.stream()
    .map(OrderCard::from)
    .toList();
~~~

Để giảm chi phí và tránh partial entity rõ hơn, có thể dùng aggregation `$project` và ánh xạ kết quả trực tiếp sang DTO, hoặc định nghĩa projection theo use case. Với **nested projection**, không mặc nhiên cho rằng getter Java giới hạn từng field nhúng được MongoDB tải; kiểm tra BSON response và query thực tế.

### 11.1. Count query không cần lấy toàn bộ entity

Nếu chỉ cần tổng số, gọi:

~~~java
long total = operations.count(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    OrderDocument.class
);
~~~

`count` yêu cầu server đếm theo predicate; không cần `find(...).size()` và materialize mọi document. Khi quy mô lớn, filtered count vẫn có chi phí — dùng `Slice`/cursor khi UI không cần tổng trang.

## 12. Ngoài `find`: truy vấn và ghi gắn với nghiệp vụ

`MongoOperations` không chỉ cung cấp `find`. Khi logic miền là **“lấy order NEW cũ nhất và chuyển sang PROCESSING”**, việc đọc một entity rồi gọi `save` sau có thể tạo race giữa hai worker.

### 12.1. Mẫu sai: đọc rồi cập nhật không điều kiện

~~~java
// Không dùng mẫu này để claim job đồng thời:
// OrderDocument oldest = repository.search(...).getContent().get(0);
// oldest.setState(PROCESSING);
// repository.save(oldest);
~~~

Hai tiến trình có thể cùng đọc order NEW rồi cùng cho rằng mình đã claim được công việc. Nếu dùng `@Version` và cập nhật qua save thì có thể phát hiện conflict, nhưng vẫn phải xử lý retry; **không nên dựa vào một cặp thao tác đọc/ghi rời nhau** khi yêu cầu atomic claim.

### 12.2. `findAndModify` chọn và cập nhật một document

Có thể đặt một phương thức chuyên biệt trong fragment:

~~~java
// Bổ sung vào OrderSearchRepository:
OrderDocument claimOldestNew(String authorizedTenantId);
~~~

Trong `OrderSearchRepositoryImpl` thêm:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Update;

@Override
public OrderDocument claimOldestNew(String authorizedTenantId) {
    if (authorizedTenantId == null || authorizedTenantId.isBlank()) {
        throw new IllegalArgumentException("Tenant is required");
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenantId)
            .and("state").is(OrderState.NEW)
    );
    query.with(Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("id")
    ));

    return operations.findAndModify(
        query,
        new Update().set("state", OrderState.PROCESSING),
        FindAndModifyOptions.options().returnNew(true),
        OrderDocument.class
    );
}
~~~

`findAndModify` là thao tác **tìm-và-sửa một document** ở MongoDB, có thể chọn sort và trả document sau thay đổi. Với fixture ban đầu, trên tenant t01, order NEW cũ nhất là `o301`; lần gọi đầu có thể chuyển o301 sang PROCESSING, lần sau sẽ chọn `o303` nếu không có thay đổi khác.

Điều kiện `state = NEW` được đánh giá **trong cùng thao tác** với cập nhật. Điều này hữu ích cho worker queue, nhưng không đồng nghĩa nhiều lần claim trong vòng lặp trở thành một transaction nguyên tử trên cả tập.

### 12.3. Tăng bộ đếm có điều kiện

Một hành vi miền khác là “cộng một lần retry cho order đang PROCESSING”:

~~~java
import com.mongodb.client.result.UpdateResult;

UpdateResult result = operations.updateFirst(
    Query.query(
        Criteria.where("id").is("o301")
            .and("tenantId").is("t01")
            .and("state").is(OrderState.PROCESSING)
    ),
    new Update().inc("retryCount", 1),
    OrderDocument.class
);
~~~

**Ví dụ riêng:** entity `OrderDocument` ở mục 4 chưa khai báo `retryCount`. Muốn chạy đoạn này, phải bổ sung property Java (và mapping nếu BSON có tên khác), đồng thời chuẩn hóa giá trị số cho document; đây là ví dụ mở rộng mô hình, không phải lệnh chạy nguyên xi trên fixture hiện tại.

Nếu chỉ cần giữ mô hình fixture nguyên vẹn, một update đúng schema có thể là:

~~~java
UpdateResult result = operations.updateFirst(
    Query.query(Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is(OrderState.NEW)),
    new Update().set("state", OrderState.PROCESSING),
    OrderDocument.class
);
~~~

Khi không có document khớp, `getMatchedCount()` là 0. Nó có thể có nghĩa ID không tồn tại, tenant không khớp hoặc trạng thái đã thay đổi. Không tự suy rằng là `404` hay `409` nếu chưa xác định contract API.

## 13. Version, vòng đời entity và tính nhất quán

Trong entity có `@Version`. Cần phân biệt:

1. `repository.save(loadedEntity)` có cơ chế optimistic locking dựa trên version của entity phù hợp với mapping.
2. `operations.updateFirst(Query, Update, Class)` là **query update**; Spring Data có thể tự tăng version khi update không chỉ định version.
3. Nếu nghiệp vụ yêu cầu **từ chối stale writer**, query phải mang **expected version** hoặc dùng thao tác entity version-aware đúng cơ chế.

Ví dụ filter bằng ID, tenant, state và version:

~~~java
long expectedVersion = 0L;

Query guarded = Query.query(
    Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is(OrderState.NEW)
        .and("version").is(expectedVersion)
);

UpdateResult result = operations.updateFirst(
    guarded,
    new Update().set("state", OrderState.PROCESSING),
    OrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order missing, state changed or version conflict"
    );
}
~~~

`@Version` không thể suy từ query thiếu version rằng người dùng từng đọc version 0. Đừng nhầm **tự tăng version** với **kiểm tra version kỳ vọng**.

### 13.1. Một document vs nhiều document

Một `updateFirst`/`findAndModify` phù hợp có tính nguyên tử ở cấp **một document**. Nếu fragment dùng `updateMulti` để sửa nhiều order, việc cập nhật mỗi document là nguyên tử, nhưng cả tập không mặc nhiên cùng commit/rollback như một transaction.

Khi cần all-or-nothing trên nhiều document, cân nhắc `MongoTransactionManager`, cùng MongoDB database factory/session và topology hỗ trợ transaction. Transaction có chi phí và giới hạn; không áp dụng máy móc cho mọi truy vấn phức tạp.

### 13.2. Query-based write không phải `save(entity)`

Không giả định `Update`/`findAndModify` thực thi tất cả entity callbacks, Bean Validation hay logic ghi/audit custom như một lệnh `save`. Nếu có các quy tắc bất biến nghiệp vụ quan trọng, hãy:

- Đưa điều kiện chuyển trạng thái vào query.
- Chọn update operator phù hợp và kiểm tra số document khớp/sửa.
- Thiết kế audit/outbox hoặc transaction khi cần.
- Kiểm thử thật trên MongoDB và converter đúng cấu hình.

## 14. Khi nào dùng aggregation qua `MongoOperations`?

`find(Query, Class)` phù hợp khi lọc và tải các document. Nếu bài toán là **tính toán trên tập order** (doanh thu theo trạng thái, nhóm theo ngày, gom SKU), `MongoOperations.aggregate(...)` là công cụ thích hợp hơn.

Ví dụ tổng tiền theo trạng thái cho một tenant:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(Criteria.where("tenantId").is("t01")),
    Aggregation.group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("totalValueVnd")
);

var results = operations.aggregate(
    aggregation,
    OrderDocument.class,
    Document.class
);
~~~

Trong ví dụ, input type `OrderDocument.class` cung cấp ngữ cảnh mapping, giúp các trường `tenantId`/`state`/`totalVnd` được ánh xạ phù hợp theo entity. Kết quả grouping thường có `_id` và các field tổng hợp; việc chuyển sang DTO cần dựa trên shape thực tế.

**Lưu ý:** code trên dùng API aggregation cơ bản để minh họa ý tưởng, không nên phát tán `Document` raw ra controller. Nếu kết quả có shape cố định, tạo DTO thống kê và ánh xạ/kiểm thử các trường dự kiến. Với các bản Spring Data có quy tắc mapping/typed aggregation khác nhau, cần kiểm chứng pipeline BSON được gửi và kết quả của mapper.

### 14.1. Khi nào không dùng aggregation?

Đừng thay một derived query `findByTenantIdAndState` đơn giản bằng pipeline nhiều stage không cần thiết. Aggregation phù hợp khi cần `$group`, `$project` tính trường, `$unwind` mảng hoặc `$lookup`, chứ không phải giải pháp mặc định cho mọi điều kiện tùy chọn.

## 15. Index và đo hiệu năng dựa theo truy vấn miền

Fragment không tự làm một query trở nên nhanh. Cần tạo index dựa trên **filter + sort** thực tế.

Fixture đã tạo:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  created_at: -1,
  _id: -1
});
~~~

Index này phù hợp với những query có tenant, trạng thái và sort theo ngày tạo, ID. Với filter chỉ tenant nhưng không có state, hoặc thêm range trên `total_vnd` và predicate `line_items`, database có thể chọn kế hoạch khác; **không giả định một compound index tối ưu cho mọi tổ hợp**.

### 15.1. `$elemMatch` và multikey index

Nếu thường xuyên tìm order theo dòng hàng:

~~~javascript
orders.createIndex({
  "line_items.sku": 1,
  "line_items.quantity": 1
});
~~~

Khi field được index đi qua mảng embedded document, MongoDB có multikey index. `$elemMatch` không chỉ bảo đảm **cùng một phần tử**, mà còn liên quan đến khả năng kết hợp index bounds với compound multikey index khi những field nằm trên cùng array path.

Không tạo index cho tất cả các trường một cách máy móc. Index phải được chọn theo workload thực, độ chọn lọc, kích thước dữ liệu và chi phí cập nhật index mỗi lần ghi.

### 15.2. Kiểm tra query trên dữ liệu đại diện

~~~javascript
orders.find({
  tenant_id: "t01",
  state_code: "PAID",
  total_vnd: { $gte: 400000 },
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
})
  .sort({ created_at: -1, _id: -1 })
  .explain("executionStats");
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và các stage sort. Với dữ liệu chỉ vài order, `explain` giúp hiểu plan nhưng không thể dùng để kết luận hiệu năng ở quy mô hàng triệu document.

### 15.3. Count và pagination có chi phí riêng

`PageImpl` ở fragment luôn trả tổng số từ `count`. Với filter nặng, phép đếm có thể làm thời gian phản hồi tăng đáng kể. Khi UI chỉ yêu cầu “có trang tiếp không”, cân nhắc trả `Slice` hoặc cursor/keyset, và đo payload từ BSON đến Java/HTTP.

## 16. Bảo mật và phân quyền trong truy vấn có mô hình miền

Một bộ lọc miền tốt không chỉ biểu diễn **người dùng muốn gì**, mà còn bảo đảm **được phép nhìn thấy gì**. Ba nguyên tắc:

1. **Tenant ở server:** lấy tenant từ security context/call đã xác thực, không để user chọn tenant khác chỉ bằng query parameter.
2. **Filter bắt buộc không bị override:** ghép tenant bằng `AND` với các điều kiện tùy chọn; không để một `OR` từ client vô tình mở rộng ra ngoài tenant.
3. **Projection/DTO allowlist:** kết quả trả về chỉ chứa trường được quyền xem, không log entity/raw BSON nếu chứa dữ liệu nhạy cảm.

### 16.1. Bẫy `OR` thiếu scope

Sai:

~~~javascript
{
  $or: [
    { tenant_id: "t01" },
    { state_code: "PAID" }
  ]
}
~~~

Truy vấn này cho phép lấy **mọi order PAID**, kể cả tenant khác. Đúng khi muốn lọc tenant và các trạng thái tùy chọn là:

~~~javascript
{
  tenant_id: "t01",
  $or: [
    { state_code: "NEW" },
    { state_code: "PAID" }
  ]
}
~~~

Trong code dùng `Criteria`, một predicate tenant bắt buộc luôn phải là thành phần của **AND bên ngoài**. Dữ liệu test cần có ít nhất một document tenant khác cùng trạng thái để phát hiện lỗi rò dữ liệu.

### 16.2. Read model và write model

Không dùng một DTO nhẹ chỉ chứa `id/state/totalVnd` rồi `repository.save(partialEntity)`. Một phần field chưa được tải có thể bị ghi thay thế mất đi. Với cập nhật có điều kiện, gọi `MongoOperations.updateFirst`/`findAndModify` bằng operator và filter rõ ràng.

## 17. Kiểm thử fragment bằng MongoDB thật

Mock `MongoOperations` có thể kiểm tra nhánh code Java nhưng không bảo đảm:

- `@Field("tenant_id")` và `@Field("state_code")` được ánh xạ đúng BSON.
- Enum `OrderState.PAID` được serialize đúng.
- `$elemMatch` ràng buộc nhiều điều kiện trên **một dòng hàng**.
- Sorting `createdAt/id` tạo đúng thứ tự và phân trang.
- Count query không lẫn skip/limit, tenant filter không bị bỏ qua.
- `findAndModify` thực sự nguyên tử theo document.

Vì vậy phần truy vấn có mô hình miền cần **integration test** với MongoDB test riêng.

### 17.1. Ma trận test

| Trường hợp | Kỳ vọng |
| --- | --- |
| Filter tenant t01, state PAID | o302, o304, o307; không có o305 |
| Sort `createdAt DESC, id DESC` | o307 đứng trước o304 vì cùng timestamp |
| Filter PAID, minTotal 400000, SKU A, qty 5 | o307, o302 |
| Cross-element trap ở o301 | Không khớp điều kiện “một dòng A qty ≥ 5” |
| Khoảng thời gian `[from, before)` | Document tại from được lấy, tại before bị loại |
| Page 0 size 2 | Hai content và total count đúng filter |
| Page size quá 100 | Bị từ chối |
| Request unpaged | Bị từ chối theo hợp đồng fragment |
| Tenant trống | Bị từ chối |
| Sku trống hoặc qty không hợp lệ | Validation báo lỗi |
| Thiếu tenant filter trong code | Test phải thất bại khi xuất hiện o305 |
| Claim order NEW cũ nhất | Một order chuyển sang PROCESSING, không claim trùng |

### 17.2. Integration test minh họa

Test dưới đây chèn fixture riêng trong **MongoDB test độc lập**. Nó kiểm tra kết quả fragment qua `OrderRepository`, không chỉ gọi trực tiếp class implementation.

~~~java
package com.example.extended;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.Date;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class ExtendedRepositorySearchTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void fragmentAppliesTenantAndSameArrayElementFilter() {
        List<String> ids = List.of(
            "fixture-ext003-a",
            "fixture-ext003-b",
            "fixture-ext003-c"
        );
        var collection = template.getDb()
            .getCollection("orders_extended_demo_003");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "test-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-01T08:00:00Z")))
                    .append("total_vnd", 500000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 1),
                        new Document("sku", "B").append("quantity", 8)
                    )),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "test-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-02T08:00:00Z")))
                    .append("total_vnd", 600000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 6)
                    )),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "another-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-03T08:00:00Z")))
                    .append("total_vnd", 700000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 9)
                    ))
            ));

            OrderSearchFilter filter = new OrderSearchFilter(
                OrderState.PAID, null, null, 400_000L, "A", 5
            );

            var page = repository.search(
                "test-tenant-003",
                filter,
                PageRequest.of(0, 2)
            );

            assertThat(page.getContent())
                .extracting(OrderDocument::getId)
                .containsExactly("fixture-ext003-b");
            assertThat(page.getTotalElements()).isEqualTo(1L);
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

Test này bắt lỗi **hai predicate thuộc hai phần tử khác nhau**: fixture A có `A×1` và `B×8` nhưng phải bị loại; fixture B có `A×6` nên được lấy; fixture C cũng đạt nhưng thuộc tenant khác.

**Chỉ chạy test trên MongoDB riêng**: phần setup/cleanup chủ động xóa đúng ID fixture. Không chạy trên collection dùng chung. Test không thay thế đo hiệu năng hay kiểm transaction; đây là bài test **hành vi truy vấn và mapping**.

### 17.3. Test phân trang và claim

Ngoài test trên, tạo một integration test riêng:

- Hai order cùng `createdAt` nhưng ID khác nhau, xác nhận sort theo `id DESC`.
- Filter một tenant có ba record, gọi page size 2 và xác nhận total 3.
- Gọi `claimOldestNew(...)` hai lần, xác nhận hai ID khác nhau được chuyển sang PROCESSING; gọi lần ba khi hết ứng viên trả `null`.
- Nếu cần kiểm thử hai worker cạnh tranh, chạy hai tác vụ song song trên MongoDB test với điều kiện `state=NEW`, xác nhận không cùng claim một document.

Không chỉ mock `OrderSearchRepositoryImpl`: cần ít nhất một test qua **composition của `OrderRepository`** để xác nhận Spring Data đã thực sự gắn fragment implementation.

## 18. Sai lầm thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Repository không có method `search` lúc runtime | Chưa extends fragment interface hoặc implementation không được phát hiện | Kiểm package scan, tên `OrderSearchRepositoryImpl` và cấu hình postfix |
| Spring cố suy diễn `search(...)` thành property query | Fragment chưa được gắn đúng | Kiểm composition, tên class và chữ ký method |
| `MongoOperations.find` trả rỗng dù BSON có dữ liệu | Nhầm tên Java/BSON hoặc enum/ID sai kiểu | Đối chiếu `@Field`, `@MongoId` và `mongosh` |
| Kết quả có tenant khác | Thiếu tenant predicate, hoặc `OR` mở rộng scope | Luôn AND scope bắt buộc vào tất cả query |
| `o301` xuất hiện khi lọc A quantity ≥ 5 | Dùng dot notation độc lập thay vì `$elemMatch` | Đặt SKU và qty trong cùng `elemMatch` |
| Page content đúng nhưng total sai | Count dùng filter khác hoặc copy nhầm skip/limit | Xây count query riêng từ cùng tiêu chí |
| Hai order cùng thời gian đổi chỗ | Sort không có tie-breaker | Thêm `id`/`_id` duy nhất vào sort |
| Trang sâu chậm | Offset/skip lớn | Kiểm index, chuyển sang keyset/cursor khi phù hợp |
| DTO ít field nhưng tải vẫn nặng | Đọc toàn bộ entity rồi map DTO | Dùng server-side field projection/aggregation |
| Save một entity partial làm mất field | `fields().include(...)` chỉ tải vài field | Chỉ đọc partial entity; dùng update operators khi ghi |
| Claim job trùng giữa worker | Đọc rồi save riêng rẽ, thiếu trạng thái ràng buộc | `findAndModify` có predicate trạng thái và sort |
| Có `@Version` nhưng ghi stale vẫn thành công | Query không có expected version | Thêm version vào predicate hoặc dùng save entity version-aware |
| Tổng count thay đổi giữa 2 lần đọc | Dữ liệu thay đổi, không có snapshot nhất quán | Xác định yêu cầu consistency, không hứa total bất biến |
| Truy vấn chậm dù dùng custom fragment | Index/filter/sort chưa tối ưu | `explain`, metric và đo trên dữ liệu đại diện |
| Test mock pass, production sai mapping | Mock không chạy converter/driver thật | Integration test với MongoDB và fragment composition |

## 19. Checklist thiết kế một extended repository

1. **Xác định hành vi miền**: tìm order, claim order, thống kê hay cập nhật; không gộp mọi thứ vào một method đa năng.
2. **Thiết kế filter có kiểu**: enum, khoảng thời gian, số lượng, monetary amount và validation rõ ràng.
3. **Giữ tenant/authorization bắt buộc** trong service và query fragment; không nhận MongoDB predicate trực tiếp từ client.
4. **Chỉ mở rộng khi cần**: CRUD và finder đơn giản tiếp tục dùng `MongoRepository`.
5. **Tạo fragment interface + implementation** theo naming convention, dùng constructor injection của `MongoOperations`.
6. **Dùng property Java** khi gọi `MongoOperations` có entity class; kiểm tra BSON alias nếu mapping phức tạp.
7. **Ràng buộc cùng phần tử mảng** bằng `$elemMatch` khi cần nhiều điều kiện trên một `OrderLine`.
8. **Tách query content và count** và dùng sort có khóa duy nhất; giới hạn page size/offset.
9. **Xử lý projection cẩn thận**: DTO ít field không chứng minh server không tải field dư; đừng `save` partial entity.
10. **Chọn thao tác ghi đúng**: `findAndModify` để atomic claim một document, `updateFirst` với filter và version kỳ vọng để cập nhật điều kiện.
11. **Thiết kế index và đo đạc** trên dữ liệu đủ lớn, không giả định fragment tự cải thiện hiệu năng.
12. **Integration test trên MongoDB thật**, kiểm mapping alias, tenant scope, array semantics, pagination, count và atomic claim.

## 20. Bài thực hành

Các bài dùng fixture mục 3. Khi có ví dụ ghi, hãy chạy trên database test được cô lập, và xem từng bài là một kịch bản độc lập.

### Bài 1 — Vì sao cần fragment?

Hệ thống có sáu filter tùy chọn. Tại sao không tạo tất cả các derived method kết hợp?

**Đáp án:** Số tổ hợp tăng nhanh, tên method dài và dễ quên điều kiện nghiệp vụ bắt buộc. Fragment dùng `MongoOperations` giúp xây predicate có kiểu từ `OrderSearchFilter`, tập trung scope tenant và định nghĩa một API miền ổn định.

### Bài 2 — Tên Java khác BSON

Entity có `@Field("tenant_id") String tenantId;`. Khi gọi `MongoOperations.find(Query, OrderDocument.class)`, viết field nào trong `Criteria`?

**Đáp án:** `Criteria.where("tenantId")` theo tên property Java; Spring Data ánh xạ sang BSON `tenant_id`. Nếu viết trực tiếp `Filters.eq(...)` của Java driver, phải dùng `tenant_id`.

### Bài 3 — Bẫy phần tử mảng

Order `o301` có A × 1, B × 8. Nếu filter “SKU A và quantity ≥ 5” được viết bằng hai dot-notation predicate, o301 có được lấy không?

**Đáp án:** Có thể được lấy nhầm vì mỗi predicate khớp một phần tử khác nhau. Để đúng yêu cầu cùng một dòng, dùng `Criteria.where("lineItems").elemMatch(Criteria.where("sku").is("A").and("quantity").gte(5))`.

### Bài 4 — Kết quả truy vấn miền

Tìm order của t01, trạng thái PAID, tổng tiền ≥ 400.000, có dòng A quantity ≥ 5; sort theo ngày tạo giảm dần rồi ID giảm dần.

**Đáp án:** `o307` rồi `o302`; `o305` thuộc tenant t02 nên phải bị loại. Có thể thực hiện bằng `repository.search("t01", filter, PageRequest.of(0,10))`.

### Bài 5 — Total count

Vì sao `countQuery` không nên mang `skip/limit` của `contentQuery`?

**Đáp án:** Content query chọn một trang, còn count cần tổng document phù hợp **cùng filter**. Tạo query riêng không có pagination để diễn đạt rõ mục đích, tránh sai tổng số và phụ thuộc vào handling của từng API.

### Bài 6 — Order cũ nhất và race condition

Hai worker cùng tìm order NEW cũ nhất rồi gọi `save`. Điều gì có thể xảy ra?

**Đáp án:** Cả hai có thể đọc cùng order; cần optimistic-lock retry hoặc dùng `findAndModify` với filter `state=NEW` và sort trong **một thao tác nguyên tử**, để order đã claim không còn khớp worker tiếp theo.

### Bài 7 — Partial entity

Một query chỉ include `id`, `state`, `totalVnd` rồi nhận `OrderDocument`. Có nên gọi `repository.save(...)` để sửa state?

**Đáp án:** Không. Đây là partial entity; save có thể thay thế document và làm mất field không tải. Chuyển sang DTO đọc, hoặc dùng `MongoOperations.updateFirst` với `Update.set` và điều kiện phù hợp.

### Bài 8 — Scope tenant

Một developer thêm filter `$or: [{tenant_id:"t01"},{state_code:"PAID"}]`. Có đúng không?

**Đáp án:** Không. Điều kiện này cho phép xem order PAID của mọi tenant. Scope tenant phải nằm trong `AND` bắt buộc ở cấp ngoài: `tenant_id:"t01"` kết hợp với nhóm điều kiện trạng thái.

### Bài 9 — Phiên bản đã đọc

Client nhìn thấy order ở version 2, nhưng khi request cập nhật được gửi tới server, order đã có version 3. Lệnh query update chỉ lọc theo `id` có từ chối chắc chắn không?

**Đáp án:** Không. Muốn từ chối stale writer, phải có expected version trong predicate hoặc dùng save entity version-aware phù hợp. Auto-bump version không tự suy ra version client đã đọc.

### Bài 10 — Kiểm chứng fragment thật

Một unit test mock `MongoOperations` trả danh sách đúng. Nó đã chứng minh alias `@Field` và `$elemMatch` hoạt động chưa?

**Đáp án:** Chưa. Cần integration test chạy qua `OrderRepository` composition trên MongoDB thật, với fixture tạo trường BSON thật, một cross-element trap và một document thuộc tenant khác.

## Tài liệu tham khảo

- [Spring Data MongoDB — Custom Repository Implementations](https://docs.spring.io/spring-data/mongodb/reference/repositories/custom-implementations.html): repository fragments, quy tắc triển khai và thành phần repository.
- [Spring Data Commons — Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): hợp đồng fragment và convention `Impl`.
- [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `find`, `count`, `findAndModify`, `updateFirst` và `aggregate`.
- [Spring Data MongoDB — Query Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `Query`, field projection, sort và `MongoTemplate`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Document`, `@Field`, `@MongoId` và chuyển đổi entity/BSON.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `findAndModify`, `Update`, `@Version` và tính nguyên tử khi ghi.
- [MongoDB Manual — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): truy vấn embedded arrays và các giới hạn của dot notation.
- [MongoDB Manual — `$elemMatch` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemmatch/): ràng buộc nhiều điều kiện trên một phần tử mảng.
- [MongoDB Manual — Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/): multikey index và `$elemMatch`.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomicity cấp document, multi-document transaction.
