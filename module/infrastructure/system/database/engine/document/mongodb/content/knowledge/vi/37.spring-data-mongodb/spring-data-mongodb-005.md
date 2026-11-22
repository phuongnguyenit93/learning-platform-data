# Phân trang, sắp xếp và giới hạn của phân trang dựa trên offset trong Spring Data MongoDB

Một màn hình quản lý đơn hàng không thể tải hàng triệu documents trong một lần gọi API. Thay vào đó, ứng dụng hiển thị từng trang 20–50 đơn, sắp xếp theo ngày tạo hoặc trạng thái và cung cấp nút chuyển trang. Trong ứng dụng **Spring Data MongoDB**, các abstraction `Pageable`, `PageRequest`, `Sort`, `Page<T>` và `Slice<T>` giúp triển khai yêu cầu này thuận tiện, trong khi `MongoTemplate` cho phép kiểm soát truy vấn chi tiết.

Tuy nhiên, **phân trang bằng offset** có hai giới hạn cơ bản mà một lời gọi `findAll(pageable)` không tự giải quyết:

1. **Chi phí của trang sâu:** để trả trang có offset lớn, MongoDB thường vẫn phải đi qua nhiều kết quả đứng trước trang cần lấy, ngay cả khi query sử dụng index. Response chỉ có 20 documents nhưng lượng công việc phía server có thể rất lớn.
2. **Kết quả không ổn định khi dữ liệu thay đổi:** một document mới được thêm hoặc một document cũ bị xóa trước vị trí offset có thể khiến các trang tiếp theo bị **trùng hoặc bỏ sót** bản ghi. Sắp xếp theo trường không duy nhất còn gây vấn đề ngay cả khi không có thay đổi đồng thời.

Bài thuộc chương **Spring Data MongoDB** của module *Database Engine Document MongoDB*. Chúng ta sẽ đi từ API phân trang cơ bản, thiết kế index và kết quả trả cho frontend đến chẩn đoán `skip`, lựa chọn `Slice` và giải pháp **keyset/seek pagination** cho danh sách lớn. Ví dụ dựa trên Java, Spring Data MongoDB, Spring Boot và `mongosh`; phiên bản framework, driver và server có thể khác nhau nên cần đối chiếu API của dependency thực tế trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích page index, page size, offset, sort và limit; phân biệt số thứ tự trang của UI với index 0-based của Spring Data.
2. Tạo `PageRequest.of(...)` và `Sort` với nhiều trường, chiều tăng/giảm và khóa tie-breaker.
3. Định nghĩa repository trả `Page<Order>` và `Slice<Order>` với filter đúng tenant.
4. Hiểu `Page` thường cần thông tin total count và khi nào nên tránh chi phí đếm.
5. Dùng `MongoTemplate` với `Query.with(Pageable)` và count query độc lập.
6. Giải thích phép ánh xạ offset pagination thành `sort + skip + limit` của MongoDB.
7. Hiểu cách index ghép theo filter/sort ảnh hưởng query plan; đọc `explain("executionStats")`.
8. Nhận diện chi phí của `skip` khi offset tăng và lý do thêm index không xóa được mọi chi phí.
9. Tạo thứ tự xác định bằng `createdAt` kết hợp `_id`; xử lý trường trùng giá trị và dữ liệu thiếu.
10. Mô tả duplicate/missing records khi thêm, xóa hoặc cập nhật dữ liệu giữa các trang.
11. Phân biệt offset pagination, cursor batching của MongoDB và keyset/seek pagination.
12. Viết truy vấn keyset dựa trên cặp `createdAt` và `_id` theo thứ tự giảm dần.
13. Hiểu `Window<T>`/`ScrollPosition` trong những phiên bản Spring Data hỗ trợ scrolling.
14. Thiết kế REST API có kiểm soát page size, whitelist sort fields, tenant scope và continuation token.
15. Đánh giá consistency, read concern, count accuracy, sharding và điều kiện chọn offset hoặc keyset.
16. Lập kế hoạch benchmark/test để xác nhận tốc độ và tính đúng của phân trang.

## 2. Vì sao phải phân trang?

Giả sử một collection `orders` có 5 triệu documents. Một API:

~~~java
List<Order> all = orderRepository.findAll();
~~~

có thể tạo các vấn đề:

- Tải quá nhiều BSON documents từ MongoDB sang backend.
- Tăng RAM/GC và thời gian chuyển dữ liệu JSON sang frontend.
- Tăng network bytes và latency.
- Khiến request bị timeout.
- Trả dữ liệu không phục vụ nhu cầu của màn hình.
- Khó bảo đảm quyền tenant và giới hạn tài nguyên khi query rộng.

Thay vì tải tất cả, API có thể trả một trang nhỏ:

~~~text
GET /api/orders?page=0&size=20

content: 20 đơn hàng đầu
page: 0
size: 20
hasNext: true
~~~

Nguyên tắc: **chỉ đọc và gửi những bản ghi phục vụ thao tác hiện tại**, với filter, sort, size và authorization rõ ràng.

### 2.1. Page không phải một bản snapshot mặc định

Trang 0 đọc lúc 10:00 và trang 1 đọc lúc 10:01 là hai truy vấn khác nhau. Nếu dữ liệu thay đổi trong một phút đó, tập kết quả không nhất thiết còn tương ứng với một danh sách bất biến. Tính đúng của business workflow quyết định liệu điều này có chấp nhận được.

### 2.2. Phân trang không thay projection

Một page 20 documents nhưng mỗi document chứa mảng 10 MiB vẫn gây tốn mạng. Phân trang phải kết hợp projection/DTO và lựa chọn trường phù hợp.

## 3. Các thuật ngữ: page, size, offset, sort, limit

Giả sử dữ liệu đã được sắp xếp:

~~~text
Vị trí:      0   1   2   3   4   5   6   7   8   9   10  11
Document:    A   B   C   D   E   F   G   H   I   J    K   L

size = 4
page 0 -> A B C D
page 1 -> E F G H
page 2 -> I J K L
~~~

Với page index bắt đầu từ 0:

\[
\text{offset} = \text{pageNumber}\times\text{pageSize}
\]

Và ở MongoDB, ý tưởng tương ứng:

~~~javascript
db.orders.find(filter)
  .sort(sort)
  .skip(offset)
  .limit(size)
~~~

| Khái niệm | Ý nghĩa |
|---|---|
| `pageNumber` | Chỉ số trang, Spring Data bắt đầu từ 0 |
| `pageSize` | Số phần tử yêu cầu tối đa mỗi trang |
| `offset` | Số kết quả đứng trước trang cần bỏ qua |
| `sort` | Thứ tự dùng để xác định phần tử nào nằm trước/sau |
| `limit` | Số bản ghi tối đa trả cho truy vấn |
| `totalElements` | Tổng số documents match filter, nếu có phép đếm |
| `totalPages` | Số trang suy ra từ totalElements và pageSize |
| `hasNext` | Có bằng chứng/trạng thái cho biết có thể lấy trang kế tiếp |

### 3.1. Ví dụ số học

`PageRequest.of(4, 25)` có offset bằng `4 × 25 = 100`. MongoDB cần bỏ qua 100 kết quả đứng trước để trả tối đa 25 kết quả.

### 3.2. Page index của UI

UI có thể hiển thị “Trang 1” cho request `page=0`. Nếu frontend dùng 1-based indexing, hãy **chuyển đổi tại một vị trí rõ ràng** trước khi tạo `PageRequest`, không trừ một ở nhiều lớp.

## 4. Ba kiểu trả kết quả cần phân biệt

Spring Data cung cấp nhiều abstraction:

| Kiểu | Dữ liệu chính | Thông tin thêm | Trade-off |
|---|---|---|---|
| `List<T>` | Danh sách elements | Không tự chứa metadata trang | Đơn giản, nhưng app tự xử lý hasNext/total |
| `Slice<T>` | Content của một lát dữ liệu | Page info, `hasNext()`, `hasPrevious()` | Không cần tổng số bản ghi |
| `Page<T>` | Content của một trang | `getTotalElements()`, `getTotalPages()`, navigation | Có thể cần thêm truy vấn count |
| `Window<T>` | Một cửa sổ của scrolling | Scroll positions và next window semantics | Dùng cho scrolling ở Spring Data version hỗ trợ |

### 4.1. `Page<T>` khi cần số trang chính xác

Ví dụ dashboard hiển thị:

~~~text
Trang 7 / 231
Tổng cộng 11.542 đơn hàng
~~~

Ứng dụng cần biết total count. `Page<Order>` có API phù hợp nhưng count query có thể đắt khi dataset lớn.

### 4.2. `Slice<T>` khi chỉ cần “Xem thêm”

Ví dụ mobile feed:

~~~text
20 đơn hàng
[Tải thêm] nếu hasNext=true
~~~

Không cần “231 trang”. `Slice` thường giảm overhead đếm bằng cách lấy thêm một phần tử để biết còn dữ liệu hay không, tùy cách repository/query được triển khai.

### 4.3. `List<T>` không tự giới hạn số lượng

Một repository method trả `List<Order>` có thể vẫn nhận `Pageable` và giới hạn kết quả theo contract đã khai báo, nhưng nếu không truyền giới hạn, nó có thể trả rất nhiều documents. Kiểu trả về `List` **không tự tạo pagination metadata**.

## 5. Mô hình Order cho ví dụ Spring Data

Giả sử các đơn hàng lưu trong collection `orders` với các trường:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "t-01",
  orderNo: "O-1001",
  status: "PAID",
  totalMinor: NumberLong(120000),
  createdAt: ISODate("2026-11-01T10:00:00Z")
}
~~~

Domain Java:

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;
    private String tenantId;
    private String orderNo;
    private String status;
    private long totalMinor;
    private Instant createdAt;

    protected Order() {}

    public ObjectId getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderNo() { return orderNo; }
    public String getStatus() { return status; }
    public long getTotalMinor() { return totalMinor; }
    public Instant getCreatedAt() { return createdAt; }

    // Constructors/setters/validation theo thiết kế aggregate của ứng dụng.
}
~~~

`@Document` chọn collection. `@Id` ánh xạ property `id` sang trường BSON `_id` theo quy tắc Spring Data MongoDB. Trong ví dụ, kiểu `ObjectId` được dùng xuyên suốt để làm tie-breaker cho sort/keyset.

### 5.1. Tại sao dùng `createdAt`?

Màn hình thường cần “mới nhất trước”. Một trường thời gian tạo ổn định, được ghi nhất quán và có index phù hợp là cơ sở tự nhiên. Nhưng **nhiều documents có thể cùng createdAt**, đặc biệt khi thời gian chỉ chính xác đến mili giây.

### 5.2. Tại sao có `tenantId`?

Với ứng dụng multi-tenant, filter theo tenant phải lấy từ ngữ cảnh đã xác thực. Nếu chỉ phân trang trên toàn collection rồi lọc tenant ở application, bạn có thể trả thiếu records, lãng phí network và tạo nguy cơ lộ dữ liệu.

### 5.3. Ký hiệu tổng tiền

`totalMinor` minh họa lưu đơn vị tiền nhỏ nhất bằng số nguyên. Quyết định money type/precision thuộc schema thiết kế nghiệp vụ; phân trang không làm thay đổi semantics kiểu dữ liệu.

## 6. Repository cơ bản với MongoRepository

Định nghĩa:

~~~java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, ObjectId> {

    Page<Order> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Slice<Order> readByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );
}
~~~

Hai methods cùng điều kiện lọc nhưng **khác return type**. Prefix `findBy` và `readBy` đều có thể tham gia query derivation của Spring Data; tên này chỉ để tránh Java method signature xung đột, không hàm ý có cơ chế database read khác về mặt auth/consistency.

### 6.1. Phạm vi của repository method

`tenantId` và `status` được đưa vào filter, không phải chỉ được dùng để gắn metadata vào response. Sắp xếp/giới hạn đến từ `Pageable`.

### 6.2. Repository methods không tự enforce tenant ownership

Nếu service truyền tenant ID từ một request parameter tùy ý, repository vẫn có thể trả dữ liệu tenant khác với quyền của service account. Validate tenant qua principal/security context trước khi gọi repository.

### 6.3. Những phiên bản Spring Data khác nhau

Các API như `MongoRepository`, `Pageable`, `Page`, `Slice` được dùng rộng rãi; những giao diện repository và scrolling extensions có thể thay đổi qua Spring Data major versions. Dùng dependency version đã pin và xem JavaDoc tương ứng, không trộn imports/code từ các đời thư viện xa nhau.

## 7. `PageRequest.of()` và `Sort`

Để lấy trang đầu của danh sách PAID, mới nhất trước:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort orderByNewest = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(
    0,    // page index: 0-based
    20,   // page size
    orderByNewest
);

Page<Order> page = orderRepository.findByTenantIdAndStatus(
    "t-01", "PAID", pageable
);
~~~

Spring Data ánh xạ property `id` có `@Id` sang BSON field `_id` khi tạo MongoDB query. Cặp sort thường tương đương:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

### 7.1. Tăng dần và giảm dần

~~~java
Sort asc = Sort.by(Sort.Order.asc("totalMinor"));
Sort desc = Sort.by(Sort.Order.desc("createdAt"));
~~~

Một sort phức hợp ưu tiên field đầu, rồi dùng field sau để giải quyết các bản ghi có cùng giá trị:

~~~java
Sort stable = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

### 7.2. Trường sort là property Java

Với entity `Order`, `"createdAt"` là tên property và `"id"` ánh xạ `_id`. Nếu dùng `@Field("created_at")` cho một property, Spring Data mapping sẽ chuyển tên property sang field MongoDB tương ứng. Đừng viết tùy tiện tên field MongoDB thô vào API Spring Data mà không hiểu mapping.

### 7.3. PageRequest bắt đầu từ 0

~~~java
PageRequest.of(0, 20); // offset = 0
PageRequest.of(1, 20); // offset = 20
PageRequest.of(5, 20); // offset = 100
~~~

Số trang âm hoặc size không hợp lệ bị từ chối. Service nên validate input trước để trả HTTP error rõ thay vì để exception lan vào response khó hiểu.

## 8. Đọc metadata từ `Page<T>`

~~~java
Page<Order> page = orderRepository.findByTenantIdAndStatus(
    "t-01",
    "PAID",
    PageRequest.of(
        2, 20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    )
);

System.out.println(page.getNumber());        // 2
System.out.println(page.getSize());          // 20
System.out.println(page.getNumberOfElements());
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
System.out.println(page.hasNext());
System.out.println(page.isFirst());
System.out.println(page.isLast());
~~~

### 8.1. Page size khác content length

Trang cuối có thể chứa 7 documents khi page size là 20. Khi đó `getSize()` vẫn là 20 (request size), còn `getNumberOfElements()` là 7.

### 8.2. Total elements và total pages

Nếu count = 105, size = 20:

\[
\text{totalPages}=\left\lceil \frac{105}{20}\right\rceil=6
\]

Trang index 0–5 có thể tồn tại. Chỉ số 6 trở lên có thể trả empty page, tùy dữ liệu và query.

### 8.3. Total có thể thay đổi khi người dùng chuyển trang

`getTotalElements()` phản ánh kết quả count query trong lần request đó. Nếu có inserts/deletes đồng thời, tổng của trang 2 có thể khác tổng ở trang 1 đã lấy trước.

## 9. Vì sao `Page<T>` có thể phát sinh count query?

Để trả chính xác tổng số phần tử/trang, Spring Data cần biết **bao nhiêu documents match filter**, ngoài những documents của trang hiện tại. Ở MongoDB, điều đó thường tương ứng với:

~~~javascript
// Lấy content
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(40)
.limit(20)

// Lấy total
db.orders.countDocuments({
  tenantId: "t-01",
  status: "PAID"
})
~~~

Các ví dụ diễn đạt hai việc logic; Spring Data có thể tối ưu/lược bỏ một số count queries khi đủ thông tin để suy ra total. Không nên khẳng định mọi page đều chắc chắn chạy đúng hai commands trong mọi phiên bản.

### 9.1. Count có thể đắt

Với filter rộng, count hàng triệu documents có thể tốn CPU/index traversal, nhất là khi index không phù hợp hoặc cluster sharded. Nếu frontend không hiển thị tổng số bản ghi, chi phí đó thường không cần thiết.

### 9.2. `estimatedDocumentCount()` không thay count có filter

MongoDB có API estimate số documents dựa trên collection metadata trong những bối cảnh phù hợp, nhưng nó không cho tổng chính xác `tenantId="t-01" AND status="PAID"`. Không thay filtered count bằng estimate toàn collection để làm `totalPages`.

### 9.3. Count và page content không tự cùng snapshot

Nếu content query và count query thực hiện riêng, dữ liệu có thể thay đổi giữa chúng. `totalElements` có thể không khớp hoàn toàn với trạng thái vừa đọc. Nếu nghiệp vụ đòi một ảnh chụp nhất quán, cần cơ chế snapshot read/transaction phù hợp cùng những chi phí vận hành tương ứng; `Page` tự nó không bảo đảm snapshot consistency.

## 10. Dùng `Slice<T>` để tránh total count khi không cần

Repository method:

~~~java
Slice<Order> slice = orderRepository.readByTenantIdAndStatus(
    "t-01",
    "PAID",
    PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    )
);

System.out.println(slice.getNumberOfElements());
System.out.println(slice.hasNext());
System.out.println(slice.hasPrevious());
~~~

`Slice` cho biết có thể tiếp tục điều hướng mà **không công bố totalElements/totalPages**. Thông thường repository có thể lấy thêm một phần tử để xác định `hasNext` thay vì đếm tất cả documents; chi tiết truy vấn là implementation của framework/driver.

### 10.1. Ví dụ “Tải thêm”

~~~text
Trang 0: 20 records, hasNext=true
Trang 1: 20 records, hasNext=true
Trang 2: 11 records, hasNext=false
~~~

API không cần trả “Trang 3 trên tổng 3”, chỉ cần button Load more.

### 10.2. Slice vẫn có thể dùng offset

Đây là điểm dễ nhầm: nếu tạo `Slice` bằng `PageRequest.of(page,size,sort)` thì **vẫn dùng offset/skip** để chuyển tới trang sâu. `Slice` tránh chi phí count, **không tự giải quyết chi phí skip hoặc vấn đề trùng/thiếu khi data thay đổi**.

### 10.3. Khi nào Page vẫn hợp lý?

Quản trị viên cần đi đến trang 7 trong tổng 20 trang; dataset không quá lớn và count/index đủ nhanh. Khi đó `Page` có trải nghiệm UI tốt hơn. Không cần “cấm Page”, mà phải chọn theo use case và độ sâu dữ liệu.

## 11. `Pageable` và `MongoTemplate`

Khi cần kiểm soát query projection, criteria và collection operations, dùng `MongoTemplate`:

~~~java
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Order> getOrderPage(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        int page,
        int size
) {
    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    ).with(pageable);

    return mongoTemplate.find(query, Order.class);
}
~~~

`Query.with(pageable)` áp dụng sort, skip và limit của `Pageable` vào MongoDB query theo API Spring Data.

### 11.1. Vì sao MongoTemplate hữu ích?

- Dễ thêm dynamic filters có kiểm soát.
- Có thể cấu hình projection `query.fields().include(...)`.
- Dễ viết count query riêng.
- Cho phép xây truy vấn keyset theo nhiều trường phức tạp.
- Có quyền kiểm soát chi tiết nơi repository derivation trở nên khó đọc.

### 11.2. Dùng Pageable tại nhiều tầng

Chỉ nên tạo `PageRequest` sau validation của input API. Repository/service nhận một `Pageable` đáng tin, tránh mỗi lớp tự sửa page/size/sort làm semantics không nhất quán.

## 12. Tạo Page thủ công với MongoTemplate

Nếu cần `Page<Order>` từ `MongoTemplate`, dùng một content query và **count query không có skip/limit**:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Page<Order> findOrderPage(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        int pageNumber,
        int pageSize
) {
    Pageable pageable = PageRequest.of(
        pageNumber, pageSize,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );

    Query dataQuery = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    ).with(pageable);

    List<Order> content = mongoTemplate.find(
        dataQuery, Order.class
    );

    Query countQuery = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    );

    long total = mongoTemplate.count(countQuery, Order.class);
    return new PageImpl<>(content, pageable, total);
}
~~~

### 12.1. Sai lầm: count bằng data query đã phân trang

Không tái sử dụng query có `skip/limit` mà chưa loại chúng khi tính total:

~~~java
// Tránh dùng query đã được .with(pageable) một cách mù quáng
// để suy ra total count.
~~~

Tạo một count query riêng với **cùng filter nhưng không có pagination** giúp ý nghĩa rõ ràng và tránh phụ thuộc hành vi chi tiết của method count/framework version.

### 12.2. Tối ưu lazy count khi phù hợp

Spring Data Commons cung cấp `PageableExecutionUtils.getPage(...)` để có thể trì hoãn hoặc bỏ count trong những trường hợp suy ra total được, tùy ngữ cảnh:

~~~java
import org.springframework.data.support.PageableExecutionUtils;

Page<Order> result = PageableExecutionUtils.getPage(
    content,
    pageable,
    () -> mongoTemplate.count(countQuery, Order.class)
);
~~~

Đây là lựa chọn khi muốn giữ `Page` nhưng hạn chế count không cần thiết. Nó không giải quyết deep `skip` hay biến offset thành keyset.

## 13. Chuyển Page thành DTO: một lưu ý về projection

Một service có thể làm:

~~~java
Page<Order> orders = orderRepository.findByTenantIdAndStatus(
    tenantId, "PAID", pageable
);

Page<OrderListItem> dtoPage = orders.map(order ->
    new OrderListItem(
        order.getId().toHexString(),
        order.getOrderNo(),
        order.getStatus(),
        order.getTotalMinor(),
        order.getCreatedAt()
    )
);
~~~

Với DTO:

~~~java
import java.time.Instant;

public record OrderListItem(
    String id,
    String orderNo,
    String status,
    long totalMinor,
    Instant createdAt
) {}
~~~

### 13.1. `Page.map()` chưa chắc giảm MongoDB network

Nếu repository đã tải **full Order documents** rồi mới map sang DTO trong Java, những fields lớn như `items` hoặc `auditTrail` có thể đã được truyền qua mạng. Map chỉ giảm dữ liệu từ service tới frontend; để tối ưu MongoDB→backend, dùng **database projection**.

### 13.2. Projection với MongoTemplate

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
).with(pageable);

query.fields()
    .include("orderNo")
    .include("status")
    .include("totalMinor")
    .include("createdAt")
    .include("_id");

List<Order> projected = mongoTemplate.find(query, Order.class);
~~~

Những properties khác của `Order` không có trong projection có thể mang giá trị mặc định/null khi mapping. Để tránh xem object thiếu field là aggregate đầy đủ, nên thiết kế DTO/projection interface riêng cho read model.

### 13.3. Không đưa persistence Page ra HTTP như contract bất biến

Serializing trực tiếp `PageImpl` có thể tạo JSON shape phụ thuộc framework version/cấu hình. Với public API, nên định nghĩa response DTO chứa content, page,size,total/hasNext theo contract mà frontend sử dụng.

## 14. Sắp xếp bắt buộc có thứ tự ổn định

Giả sử ba orders có cùng `createdAt`:

~~~text
A: createdAt = 10:00:00.000
B: createdAt = 10:00:00.000
C: createdAt = 10:00:00.000
~~~

Nếu chỉ:

~~~java
Sort.by(Sort.Order.desc("createdAt"))
~~~

thì **thứ tự tương đối của A/B/C không được bảo đảm** theo yêu cầu logic: query planner, index, storage và thực thi có thể tạo thứ tự khác khi các giá trị sort bằng nhau. Phân trang theo offset với sort không duy nhất có thể bỏ sót hoặc lặp ngay cả khi dataset không đổi.

### 14.1. Thêm tie-breaker duy nhất

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Vì `_id` unique trong collection, cặp `createdAt, _id` tạo thứ tự toàn phần (giả sử các trường có kiểu dữ liệu/giá trị phù hợp).

### 14.2. Sort không mặc định theo insert order

MongoDB không bảo đảm thứ tự “natural” của documents nếu bạn không chỉ định sort. Không dựa vào việc query hôm nay “trông có vẻ theo `_id`” để triển khai pagination.

### 14.3. `ObjectId` không thay createdAt hoàn toàn

ObjectId có thành phần liên quan thời gian sinh, nhưng không phải một đồng hồ giao dịch chính xác, toàn cục hoặc chứng minh thứ tự commit giữa mọi writers. Ở đây `_id` dùng **làm tie-breaker duy nhất**, còn business sort key là `createdAt`.

## 15. Những trường hợp sort cần thiết kế thêm

| Tình huống | Rủi ro | Hướng xử lý |
|---|---|---|
| `createdAt` trùng | Thứ tự không xác định | Tie-breaker `_id` |
| `createdAt` bị sửa | Record chuyển vị trí giữa pages | Ưu tiên sort key bất biến hoặc snapshot strategy |
| Field sort có null/missing | Thứ tự và keyset token khó xử lý | Chuẩn hóa schema/filter/explicit policy |
| Field sort có nhiều BSON types | So sánh gây bất ngờ | Consistent data types và validation |
| Sort theo text có collation | Thứ tự khác binary order | Collation nhất quán ở query/index/token |
| Sort trên array/multikey | Kế hoạch/index semantics phức tạp | Benchmark và cân nhắc read model khác |
| User tự chọn field bất kỳ | Slow query hoặc truy cập field không cho phép | Whitelist sort keys |

### 15.1. Sort theo ngày tạo hay ngày cập nhật?

`updatedAt` thường thay đổi liên tục, khiến danh sách “mới cập nhật nhất” bị reorder ngay khi người dùng đang lật trang. Dù có tie-breaker, pagination không phải snapshot bất biến. Nếu UX yêu cầu cố định, cần bookmark/snapshot/anchor design phù hợp.

### 15.2. Ascending và descending phải nhất quán

Index phù hợp phụ thuộc equality prefix, thứ tự sort và chiều index. Một compound index có thể hỗ trợ một số hướng sort đảo toàn bộ, nhưng không phải mọi tổ hợp chiều đều tương đương. Dùng `explain` thay vì dựa vào một quy tắc quá đơn giản.

## 16. MongoDB thực hiện offset pagination như thế nào?

Trong Spring Data:

~~~java
PageRequest.of(
    500, 20,
    Sort.by(Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"))
)
~~~

về mặt ý tưởng tạo:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(10000)
.limit(20)
~~~

MongoDB cần xác định 10.020 phần tử đầu theo thứ tự sort để bỏ qua 10.000 rồi trả 20 records. Có index tốt, server có thể duyệt index thay vì sort toàn bộ trong RAM, nhưng **không thể nhảy trực tiếp tới “phần tử thứ 10.001” của một ordered index scan theo rank như một phép lookup khóa thông thường**.

### 16.1. Chi phí tăng theo offset

Đối với nhiều query plans, lượng index entries cần đi qua xấp xỉ:

\[
O(\text{offset}+\text{pageSize})
\]

Đây là mô hình phân tích cho deep offset scan, không phải bảo đảm toán học chính xác cho mọi optimizer/version/topology. Kích thước response vẫn chỉ bằng `pageSize`, còn lượng server work tăng.

### 16.2. Cùng pageSize, hiệu năng khác xa

~~~text
Trang đầu:       skip 0,       limit 20
Trang thứ 101:   skip 2000,    limit 20
Trang thứ 5001:  skip 100000,  limit 20
~~~

Nếu `Page` còn phải count hàng triệu matching records, tổng chi phí có thể gồm **deep skip + count**.

### 16.3. Index giúp, nhưng không xóa giới hạn

Index tối ưu filter/sort tránh full collection sort/scan không cần thiết. Tuy vậy, với offset cực lớn, server vẫn phải lướt qua nhiều vị trí. Đây là lý do keyset pagination hiệu quả khi người dùng đi tuần tự.

## 17. Thiết kế compound index cho filter và sort

Query phổ biến:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_created_id" }
)
~~~

### 17.1. Logic của thứ tự index

- `tenantId` và `status` là equality predicates.
- `createdAt` và `_id` phục vụ sort.
- Index có thể cho phép tìm phạm vi tenant/status rồi duyệt theo thứ tự mong muốn.

Đây là một ứng viên tốt cho access pattern **đã xác định**, không phải index tốt cho mọi sort/filter khác.

### 17.2. Khi filter thay đổi

Nếu query chỉ có `tenantId` mà không có `status`, index trên có thể không hỗ trợ phần sort như kỳ vọng vì field status nằm giữa equality prefix và sort fields. Có thể cần index khác cho workload “mọi trạng thái”.

### 17.3. Khi UI sort theo total

Index cho `createdAt` không mặc nhiên tối ưu `sort(totalMinor)`. Nếu UI cần nhiều kiểu sort, thiết kế whitelist + phân tích frequency/cost. Không tạo một index cho mỗi tổ hợp người dùng có thể tưởng tượng ra.

### 17.4. Index cũng có chi phí

Mỗi index dùng storage/cache và tăng chi phí insert/update/delete. Đo tần suất truy vấn, query plans và write throughput trước khi bổ sung hàng loạt compound indexes.

## 18. Index qua annotation và vấn đề vận hành

Spring Data MongoDB có thể khai báo index ở entity:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
    name = "idx_tenant_status_created_id",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': -1}"
)
public class Order {
    // Các properties của aggregate Order.
}
~~~

Đoạn này minh họa khai báo metadata trên class; không đặt trùng một class `Order` khác trong cùng file. **Auto index creation không phải lúc nào cũng được bật** theo Spring Data MongoDB version/configuration. Trong production, thường quản lý index bằng migration/runbook có kiểm soát, đo tác động build index và xác minh deployment đã tạo thành công.

### 18.1. Index name ở MongoDB và property mapping

Khi dùng annotation trên entity có `@Id`, xác nhận index definition thực tế trên MongoDB:

~~~javascript
db.orders.getIndexes()
~~~

Không chỉ đọc Java annotation rồi kết luận index đã tồn tại.

### 18.2. Index validation

Dùng `explain` của query thật, không chỉ `getIndexes`, vì optimizer có thể chọn index khác nếu thống kê dữ liệu/query shape thay đổi.

## 19. Dùng `explain("executionStats")` để nhìn chi phí trang sâu

Trên database lab:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(10000)
.limit(20)
.explain("executionStats")
~~~

Các trường đáng xem:

| Chỉ số | Câu hỏi |
|---|---|
| `nReturned` | Có đúng tối đa 20 documents? |
| `totalKeysExamined` | Có phải đi qua rất nhiều index entries? |
| `totalDocsExamined` | Có FETCH nhiều documents không? |
| Winning plan | Có `IXSCAN`, `COLLSCAN`, `SORT`, `SKIP` hoặc các stages tương ứng? |
| Execution time | Thời gian thực thi phía server trong phép giải thích |
| Count query explain | Có index/filter tốt cho phép đếm? |

### 19.1. So sánh hai offsets

~~~javascript
// Trang nông:
db.orders.find({ tenantId: "t-01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0).limit(20)
  .explain("executionStats")

// Trang sâu:
db.orders.find({ tenantId: "t-01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20)
  .explain("executionStats")
~~~

Hai truy vấn cần chạy trên dataset đủ lớn để offset sâu tồn tại; với lab chỉ vài chục records thì không thể rút kết luận production.

### 19.2. Explain không phải toàn bộ thời gian API

`executionStats` không bao trùm đầy đủ HTTP serialization, connection pool wait và network tới browser. Đo thêm p95/p99 end-to-end, CPU, memory và command counts.

### 19.3. MongoDB query có thể covered

Với projection chỉ chọn fields có trong compound index, MongoDB có thể tránh FETCH documents trong điều kiện phù hợp. Điều này giảm chi phí đọc documents, nhưng **deep skip vẫn có thể phải duyệt nhiều index entries**.

## 20. Tình huống dữ liệu mới khiến offset bị trùng

Giả sử sort mới nhất trước, size = 3:

~~~text
Tại T1:
Danh sách: A B C D E F G H
page 0 (skip 0): A B C
~~~

Ngay sau khi user xem trang 0, một đơn `X` mới hơn A được thêm:

~~~text
Tại T2:
Danh sách: X A B C D E F G H
page 1 (skip 3): C D E
~~~

Record `C` xuất hiện **hai lần**: cuối page 0 và đầu page 1.

### 20.1. Vì sao tie-breaker chưa chữa được?

Ngay cả với sort `createdAt, _id` hoàn toàn xác định, `X` vẫn làm vị trí của các records phía sau tăng một. Offset là **số vị trí cần bỏ**, không phải bookmark nhận diện record cuối cùng đã thấy.

### 20.2. UX nào có thể chấp nhận?

Trang danh sách quản trị ít thay đổi có thể chấp nhận một bản ghi lặp hiếm hoi. Nhưng nếu phân trang để export dữ liệu/chạy batch xử lý với yêu cầu exactly-once, sự trùng lặp có thể gây tác động nghiệp vụ nghiêm trọng.

## 21. Xóa dữ liệu khiến offset bỏ sót record

Tiếp tục ví dụ tại T1:

~~~text
Tại T1:
Danh sách: A B C D E F G H
page 0: A B C
~~~

Sau đó `A` bị xóa:

~~~text
Tại T2:
Danh sách: B C D E F G H
page 1 (skip 3): E F G
~~~

Record `D` đã chuyển lên vị trí 2, bị nằm trong phần mà `skip(3)` bỏ qua. Người dùng không nhìn thấy `D` ở page 0 hay page 1.

### 21.1. Update sort key cũng có thể gây trùng/thiếu

Nếu `createdAt` hoặc `updatedAt` được thay đổi và document chuyển qua ranh giới trang, offset pagination có thể thay đổi các vị trí liên tiếp. Keyset cũng cần chính sách xử lý sort key mutable; không có công cụ pagination nào tự cung cấp transaction snapshot qua các HTTP requests độc lập.

### 21.2. “Đếm tổng đúng” không giải quyết

Count có thể cập nhật chính xác tại mỗi request nhưng offset vẫn dịch khi dữ liệu thay đổi. Cần phân biệt **total count correctness** với **continuation consistency**.

## 22. So sánh offset và keyset/seek pagination

| Đặc điểm | Offset `skip+limit` | Keyset/seek |
|---|---|---|
| Chọn trang số N trực tiếp | Dễ | Khó, thường đi theo continuation |
| Trang đầu | Thường hiệu quả với index | Hiệu quả |
| Trang sâu | Chi phí có thể tăng mạnh | Có thể ổn định hơn nếu index phù hợp |
| Chèn record phía trước | Có thể trùng records | Ít bị dịch vị trí khi sort key bất biến |
| Xóa record phía trước | Có thể bỏ sót | Không dùng vị trí tuyệt đối nên ổn định hơn |
| Cần sort xác định | Có | Có, đặc biệt quan trọng |
| Cần last sort key | Không | Có |
| Hỗ trợ totalPages tự nhiên | Có thể kết hợp count | Không trực tiếp |
| Sort trên field nullable/mutable | Có khó khăn | Khó hơn, cần policy/token phù hợp |
| API “load more” | Có thể dùng | Thường phù hợp |

### 22.1. Keyset không phải thuốc chữa mọi trường hợp

Keyset cần một thứ tự phù hợp và cursor/token. Nó không cho phép nhảy trực tiếp tới “trang 50” nếu không có anchor trước đó. Nếu người dùng muốn một báo cáo nhất quán theo thời điểm, keyset một mình không đủ.

### 22.2. Khi nào offset vẫn hợp lý?

- Dataset nhỏ hoặc số trang được giới hạn rõ.
- UI cần chuyển nhanh tới trang theo số.
- Dữ liệu ít biến động hoặc duplicate/missing được chấp nhận.
- Count cần thiết và có thể tính hiệu quả.
- Benchmark chứng minh `skip` ở độ sâu thực tế vẫn đạt SLA.

Đừng thay toàn bộ offset pagination bằng keyset chỉ vì nghe “offset chậm”; hãy đánh giá yêu cầu thật.

## 23. Truy vấn keyset: ý tưởng “sau record cuối”

Giả sử sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Page đầu:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

Lưu cặp giá trị của document cuối được trả, ví dụ:

~~~text
lastCreatedAt = 2026-11-01T10:00:00.000Z
lastId = ObjectId("64b000000000000000000123")
~~~

Page sau theo chiều giảm dần:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-01T10:00:00Z") } },
    {
      createdAt: ISODate("2026-11-01T10:00:00Z"),
      _id: { $lt: ObjectId("64b000000000000000000123") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

### 23.1. Tại sao dùng `$or`?

Với sort giảm dần theo hai field, record tiếp theo phải có:

1. `createdAt` nhỏ hơn mốc cuối; **hoặc**
2. `createdAt` bằng mốc cuối và `_id` nhỏ hơn lastId.

Đây là phép so sánh từ điển (lexicographic) theo cặp khóa.

### 23.2. Vì sao không dùng `skip`?

Query không nói “bỏ 100.000 phần tử” mà nói “tiếp tục sau cặp khóa này”. Với index phù hợp, server có cơ hội seek tới phạm vi khóa thay vì đi qua toàn bộ positions từ đầu. Query planner vẫn cần được kiểm chứng bằng `explain`, nhất là khi có `$or` hoặc điều kiện sharding.

### 23.3. Tại sao lưu cả `_id`?

Nếu nhiều documents có cùng timestamp, chỉ lưu lastCreatedAt sẽ bỏ mất các documents còn lại có cùng thời điểm. Tie-breaker `_id` giúp định nghĩa ranh giới chính xác.

## 24. Keyset trong MongoTemplate với Criteria

Một implementation đọc trang kế tiếp bằng last sort key:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Order> findAfter(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        Instant lastCreatedAt,
        ObjectId lastId,
        int size
) {
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("INVALID_PAGE_SIZE");
    }

    Criteria scope = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status);

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    Query query = new Query(
        new Criteria().andOperator(scope, after)
    );
    query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ));
    query.limit(size);

    return mongoTemplate.find(query, Order.class);
}
~~~

### 24.1. Giải thích query

`scope` là filter bắt buộc. `after` xác định vùng phía sau record cuối. Query dùng cùng sort như page đầu và limit tối đa size. `Criteria.where("_id")` biểu thị trường MongoDB identifier; khi dùng entity mapping, phải xác minh field names đúng trong query cuối.

### 24.2. Không dùng lastCreatedAt/current time một cách tùy ý

Cursor phải đến từ **record cuối thực sự đã trả cho client** cùng bộ filter/sort. Dùng “thời gian hiện tại” làm last key có thể bỏ dữ liệu chưa xem.

### 24.3. Giới hạn của code ví dụ

Đây là một truy vấn seek cơ bản, chưa đóng gói continuation token, page metadata, xác minh người dùng, null handling, snapshot anchor hoặc xử lý sort chiều tăng. Các phần sau mô tả những yêu cầu đó.

## 25. Lấy `hasNext` trong keyset bằng size + 1

Với API keyset page size 20, có thể query 21 documents:

~~~java
int requestedSize = 20;
query.limit(requestedSize + 1);

List<Order> fetched = mongoTemplate.find(query, Order.class);
boolean hasNext = fetched.size() > requestedSize;

List<Order> content = hasNext
    ? fetched.subList(0, requestedSize)
    : fetched;
~~~

Nếu `hasNext=true`, tạo next token từ **record cuối trong content thực sự trả**, không phải record thứ 21 bị loại để dò còn dữ liệu.

### 25.1. Vì sao không cần total count?

Button “Load more” chỉ cần biết có records sau trang hiện tại. Việc lấy thêm một record thường tiết kiệm hơn count toàn bộ dataset, dù chi phí phụ thuộc query/index và size.

### 25.2. Không phát hành next token khi content rỗng

Nếu không có records, không lấy `content.get(content.size()-1)`. Kiểm tra rỗng và dùng `hasNext=false`.

### 25.3. Token cho page đầu

Không có last key: chạy query chỉ có filter/sort/limit(size+1). Sau đó generate token nếu còn trang tiếp. Không dùng một “lastId=0” giả định vì BSON types và sort có thể không hỗ trợ cách đó.

## 26. Continuation token an toàn

Một continuation token có thể chứa về mặt logic:

~~~json
{
  "v": 1,
  "sort": "createdAt_DESC_id_DESC",
  "createdAt": "2026-11-01T10:00:00.000Z",
  "lastId": "64b000000000000000000123",
  "tenant": "t-01",
  "filterHash": "hash-of-authorized-query",
  "expiresAt": "2026-11-01T11:00:00.000Z"
}
~~~

Ví dụ chỉ mô tả **payload logic**, không phải token production. Trong API, serialize thành opaque Base64url value có **chữ ký HMAC hoặc cơ chế integrity/authentication phù hợp**, với key rotation policy.

### 26.1. Không tin token như input tự do

Client có thể sửa timestamp, tenant, filter và sort nếu token không được bảo vệ. Server phải:

- Xác minh chữ ký, version, expiry.
- Kiểm tra token thuộc principal/tenant hiện tại.
- Khớp sort và filters với request đã được phép.
- Validate ObjectId/timestamp/type.
- Giới hạn page size độc lập với token.

### 26.2. Token không phải credentials

Không đặt password/MongoDB URI/PII không cần thiết trong cursor. Base64url **không mã hóa nội dung**; người dùng có thể decode payload. Nếu cursor chứa thông tin nhạy cảm, cần mã hóa ngoài chữ ký hoặc dùng server-side state.

### 26.3. Độ chính xác timestamp

MongoDB BSON Date có độ phân giải mili giây. Khi lưu `Instant` vào token, cần round-trip đúng giá trị đã lưu, ví dụ ISO UTC với mili giây. Tự cắt timestamp sang giây có thể làm sai vị trí seek nếu nhiều records trong cùng giây.

### 26.4. Filters không thể âm thầm thay

Nếu page đầu lọc status PAID nhưng page sau đổi sang PENDING trong khi dùng lại cursor cũ, boundary không còn cùng tập dữ liệu. Token nên gắn với filter hash/policy để từ chối hoặc yêu cầu bắt đầu lại.

## 27. Spring Data Scroll API: `Window` và `ScrollPosition`

Ở các Spring Data versions có hỗ trợ repository scrolling, framework cung cấp abstraction `Window<T>` và `ScrollPosition` để duyệt kết quả từng cửa sổ. Có hai tư tưởng khác nhau:

- **Offset scrolling:** lưu vị trí số học, vẫn có giới hạn skip/offset.
- **Keyset scrolling:** lưu các field sort của phần tử cuối để truy vấn phần tiếp theo theo vùng khóa.

Về mặt khái niệm:

~~~java
// Phụ thuộc version Spring Data MongoDB / Spring Data Commons:
// Window<Order> first = repository
//     .findFirst20ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
//         tenantId, status, ScrollPosition.keyset()
//     );
//
// ScrollPosition next = first.positionAt(first.size() - 1);
// Window<Order> second = repository
//     .findFirst20ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
//         tenantId, status, next
//     );
~~~

Đây là **pseudocode minh họa cách dùng**, không cam kết method signature/query derivation tương thích với mọi release. Kiểm tra tài liệu của Spring Data MongoDB và JavaDoc của `Window`/`ScrollPosition` đang sử dụng trước khi copy vào dự án.

### 27.1. Đừng nhầm `ScrollPosition.offset()` với keyset

Một abstraction có tên “scroll” không bảo đảm tránh `skip`. Phải xác định đang dùng loại position nào.

### 27.2. Keyset có yêu cầu trường sort

Các field cần để tái tạo vị trí phải được trả trong projected result và có giá trị so sánh ổn định. Nếu projection loại `createdAt` hoặc `id` trước khi framework tạo keyset position, scrolling có thể không hoạt động như mong muốn.

### 27.3. Cursor MongoDB khác REST cursor

MongoDB server cursor/getMore dùng để chuyển **một result stream** qua batches. REST continuation token/keyset dùng để mở **những truy vấn trang độc lập**. Chúng không phải cùng một loại ID và không nên lộ MongoDB cursorId trực tiếp cho frontend.

## 28. Keyset tốt hơn offset ở đâu và chưa tốt ở đâu?

### 28.1. Lợi ích với thêm/xóa trước boundary

Nếu user đã thấy đến record C và record X mới được thêm phía trước A, request tiếp theo “sau C” vẫn tìm D/E/F theo cặp khóa, không dựa trên `skip(3)` đã bị dịch.

### 28.2. Vấn đề sort key mutable

Nếu một document cũ được chỉnh `createdAt` hoặc đang sort `updatedAt`, nó có thể nhảy qua boundary; keyset có thể vẫn trùng/thiếu khi dữ liệu thay đổi **chính những trường định vị**. Dùng sort key bất biến, anchor/snapshot hoặc chấp nhận semantics eventual feed.

### 28.3. Không nhảy trực tiếp trang N

Một token chỉ biết tiếp tục sau last key của trang trước. Không thể tính “page 1000” bằng một phép nhân đơn giản khi không có bookmark/anchor tương ứng.

### 28.4. Multi-column dynamic sort

UI cho phép sort theo status, totalMinor, createdAt và tên khách sẽ cần token format, null/collation policy và indexes phù hợp từng sort. Không tự động đưa mọi sort vào keyset mà không thiết kế.

## 29. Phân trang khi người dùng chọn sort động

Giả sử API nhận:

~~~text
GET /api/orders?sort=createdAt,desc&size=20
~~~

Không nên chấp nhận bất kỳ field path nào do người dùng truyền rồi tạo `Sort.by(rawInput)`. Một sort trên mảng lớn hoặc field không có index có thể gây query tốn tài nguyên.

### 29.1. Dùng whitelist

~~~java
import java.util.Set;
import org.springframework.data.domain.Sort;

public Sort safeSort(String requestedField, String direction) {
    Set<String> allowed = Set.of(
        "createdAt", "totalMinor", "status"
    );

    if (!allowed.contains(requestedField)) {
        throw new IllegalArgumentException("UNSUPPORTED_SORT_FIELD");
    }

    Sort.Direction dir = "asc".equalsIgnoreCase(direction)
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;

    return Sort.by(
        new Sort.Order(dir, requestedField),
        new Sort.Order(dir, "id")
    );
}
~~~

Ở đây tie-breaker `id` cùng chiều với sort chính để tạo thứ tự xác định. Khi dùng keyset với nhiều sort directions/fields, phải xây đúng toán tử so sánh cho từng direction; không áp một điều kiện `$lt` giống nhau cho mọi lựa chọn.

### 29.2. Index cho mỗi sort

Sort `createdAt desc` và `totalMinor asc` có access patterns khác nhau. Cân nhắc tạo index cho các sorts được sử dụng thường xuyên; với sort hiếm có thể giới hạn filter/size hoặc chỉ hỗ trợ trên tập dữ liệu nhỏ.

### 29.3. Collation và text

Sort theo tên khách có thể cần collation (ngôn ngữ, chữ hoa/thường, dấu). Query/index/token cần dùng collation nhất quán. Không lấy một token so sánh chuỗi theo binary order rồi áp vào query sort với locale khác.

## 30. Missing/null sort keys

Keyset đơn giản giả định `createdAt` có giá trị không null và cùng BSON type. Nếu một số documents thiếu trường này:

- MongoDB có quy tắc so sánh null/missing theo thứ tự BSON và query semantics.
- Query với `createdAt < lastCreatedAt` có thể xử lý các trường hợp null khác kỳ vọng business.
- Token không có field giá trị cần thiết có thể không mô tả vị trí đầy đủ.

### 30.1. Chuẩn hóa schema

Với danh sách quan trọng, yêu cầu `createdAt` tồn tại và được ghi một lần khi tạo document. Có thể dùng application validation, MongoDB collection validator và migration dữ liệu cũ.

### 30.2. Nếu cần sort theo nullable field

Thiết kế một **sort key chuẩn hóa** (ví dụ trạng thái có giá trị mặc định) hoặc một ordering có nhánh riêng cho null. Kiểm chứng bằng tests và explain; không tự suy một bất đẳng thức duy nhất xử lý đúng mọi BSON type.

### 30.3. Thời gian có timezone

Lưu timestamp ở representation nhất quán (thường UTC BSON Date), hiển thị timezone tại UI. Không chuyển string thời gian cục bộ thành sort key mà chưa chuẩn hóa.

## 31. Read concern và tính nhất quán giữa các trang

### 31.1. Majority không biến mọi HTTP request thành snapshot chung

`ReadConcern.MAJORITY` (khi deployment hỗ trợ) có những bảo đảm về visibility của dữ liệu committed, nhưng page 0 và page 1 ở hai thời điểm vẫn có thể thấy các tập dữ liệu khác nhau.

### 31.2. Snapshot read/transaction khi cần

Nếu business cần export một tập dữ liệu **nhất quán tại cùng thời điểm**:

- Có thể cần transaction với snapshot semantics, hoặc cơ chế snapshot read được server/driver hỗ trợ.
- Phải xét transaction duration, resource use, lifecycle và giới hạn của MongoDB.
- Không giữ một transaction dài hàng chục phút chỉ để người dùng click từng trang tùy ý mà chưa đánh giá vận hành.

### 31.3. Chiến lược cho export

Đối với báo cáo lớn, cân nhắc tạo một **export job** với snapshot/anchor rõ và ghi output ra file/object storage thay vì yêu cầu frontend lật hàng nghìn trang offset. Nếu chỉ cần tổng hợp, aggregation phía server có thể phù hợp hơn tải từng page để cộng bằng Java.

### 31.4. Page content và count là hai thao tác

Ngay cả khi dùng `Page<T>`, count và content thường không được cam kết là một phép đọc nguyên tử tại cùng timestamp. UI hiển thị total nên chấp nhận khả năng thay đổi hoặc yêu cầu cơ chế consistency rõ.

## 32. Multi-tenant pagination và security

Một số lỗi thiết kế xảy ra khi query có pagination nhưng không khóa phạm vi:

~~~java
// Anti-pattern nếu API nhiều tenant:
Page<Order> page = orderRepository.findAll(pageable);
~~~

Tài khoản service có thể đọc tất cả orders, gồm dữ liệu tenants khác. Truy vấn đúng hơn:

~~~java
Page<Order> page = orderRepository.findByTenantIdAndStatus(
    authenticatedTenantId,
    "PAID",
    pageable
);
~~~

### 32.1. Đừng tin tenantId trong token

Token có thể chứa tenant ID để kiểm tra tính liên tục nhưng server phải xác minh tenant ID **từ authentication context**. Không cấp quyền dựa riêng vào giá trị client gửi.

### 32.2. Paging không phải giới hạn dữ liệu duy nhất

Một client vẫn có thể gọi liên tục hàng nghìn pages. Cần authorization, rate limit, quotas, maximum page/size và observability theo tính chất sản phẩm.

### 32.3. Invariant về filters

Nếu page đầu có filter `status=PAID` và page sau filter khác nhưng dùng cùng offset/token, kết quả không còn cùng logical set. API nên giữ filters ổn định hoặc xem mỗi filter change là bắt đầu một pagination session mới.

## 33. Thời gian đếm và metadata trong UI

Với một feed 10 triệu records, frontend có thể hiển thị:

~~~text
20 kết quả đầu
Nút "Xem thêm"
~~~

thay vì:

~~~text
20 kết quả trên tổng 10.234.987
Trang 1 / 511.750
~~~

Nếu tổng số records không phục vụ quyết định nào của người dùng, `Slice` hoặc keyset API không count có thể giảm tải đáng kể.

### 33.1. Nếu vẫn cần tổng

Cân nhắc:

- Count theo filter trên index phù hợp.
- Cache count với TTL và ghi rõ đó là số có thể trễ.
- Precompute counters theo dữ liệu/nhu cầu nghiệp vụ.
- Tính total ở job riêng thay vì mỗi lần chuyển trang.

Nếu dùng cached/estimated count, **không trình bày nó như exact real-time total** trừ khi đã chứng minh được.

### 33.2. Count không luôn chậm

Với collection nhỏ hoặc filter rất chọn lọc, count có thể đủ nhanh. Không thay kiến trúc chỉ vì tránh một phép đếm khi benchmark cho thấy đáp ứng SLA.

## 34. Deep offset trong sharded cluster

Trong sharded MongoDB, một query có sort/skip/limit có thể đi qua `mongos` và nhiều shards tùy shard key/routing. Những khác biệt cần xem:

- Filter có đủ shard key để target một tập shards nhỏ không?
- Có phải mỗi shard thực hiện work đáng kể rồi router merge/sort?
- Các indexes trên shards có hỗ trợ filter và sort?
- Offset lớn làm tăng khối lượng đọc/truyền/trộn kết quả trung gian tới mức nào?

### 34.1. Tenant filter có thể giúp shard targeting

Nếu sharding strategy phù hợp với tenant, filter tenant chính xác có thể giới hạn các shards liên quan. Không kết luận mọi sharded cluster tự target một shard chỉ vì có tenantId; điều đó phụ thuộc shard key và chunk distribution.

### 34.2. Keyset vẫn cần đúng routing

Keyset làm giảm nhu cầu skip sâu, nhưng một query scatter-gather với sort không phù hợp vẫn có thể tốn tài nguyên trên nhiều shards. Tối ưu shard key, index và query shape song song.

### 34.3. Kết quả `explain` trên mongos

Xem plan của toàn cluster và từng shard (theo công cụ/server version). Không chỉ kiểm tra explain trên một shard rồi khẳng định API qua mongos đã tối ưu.

## 35. REST API contract cho offset pagination

Một response nên tự mô tả:

~~~json
{
  "items": [
    {
      "id": "64b000000000000000000123",
      "orderNo": "O-1001",
      "status": "PAID",
      "totalMinor": 120000,
      "createdAt": "2026-11-01T10:00:00Z"
    }
  ],
  "page": 0,
  "size": 20,
  "numberOfElements": 1,
  "totalElements": 53,
  "totalPages": 3,
  "hasNext": true,
  "sort": "createdAt,desc;id,desc"
}
~~~

Đây là response **minh họa**, không phải kết quả từ một database cụ thể. Trong sản phẩm thật, `hasNext` và total phải nhất quán với số liệu thực của request; ví dụ trang 0 có 1 record và total 53 chỉ có thể xảy ra trong những trạng thái/semantics đặc thù, nên không dùng những con số mẫu này làm assertion test. Một contract thông thường sẽ có đầy đủ items cho trang đầu nếu dữ liệu match đủ.

### 35.1. Validation đầu vào

~~~java
public PageRequest validatedPageRequest(int page, int size) {
    if (page < 0) {
        throw new IllegalArgumentException("PAGE_MUST_BE_NONNEGATIVE");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("INVALID_PAGE_SIZE");
    }
    if (page > 1000) {
        throw new IllegalArgumentException("PAGE_TOO_DEEP_USE_CURSOR");
    }

    return PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );
}
~~~

`100` và `1000` là **giới hạn API minh họa**, không phải giới hạn MongoDB mặc định. Chọn theo UX, data size, index, SLA và security policy.

### 35.2. Không dùng `Pageable.unpaged()` từ raw input

Nếu endpoint cho phép client tắt pagination, một request có thể trả toàn collection. Chỉ cho phép unpaged ở tác vụ nội bộ được kiểm soát và có cơ chế streaming/quota rõ.

### 35.3. Page too deep

Khi user cần đọc tiếp một danh sách lớn, API có thể trả thông báo chuyển sang cursor-based pagination thay vì chạy `skip` cực lớn. Định nghĩa response error và migration contract rõ cho frontend.

## 36. REST API contract cho keyset

~~~text
GET /api/orders?size=20
GET /api/orders?size=20&after=<opaque-signed-token>
~~~

Ví dụ response:

~~~json
{
  "items": [
    {
      "id": "64b000000000000000000123",
      "orderNo": "O-1001",
      "createdAt": "2026-11-01T10:00:00Z"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-token",
  "sort": "createdAt,desc;id,desc"
}
~~~

Không có `totalPages` vì không count. Token là opaque với frontend; server kiểm tra chữ ký/filter/tenant/sort và expiry.

### 36.1. Nếu đổi sort

User đổi từ newest-first sang total-desc: token cũ không còn hợp lệ. Bắt đầu pagination mới, không cố diễn giải cặp khóa cũ dưới thứ tự mới.

### 36.2. Previous page

Đi ngược với keyset cần thiết kế điều kiện/chiều sort đảo rồi đảo lại output hoặc lưu history tokens ở frontend. Không tự dùng `skip(-20)`.

### 36.3. Không đồng nhất token và quyền

Token không thay authorization. Service phải tiếp tục kiểm tra quyền đọc dữ liệu tại mỗi request.

## 37. Keyset và tập dữ liệu có thứ tự biến đổi

Một feed “newest first” liên tục có insert mới, keyset thường giữ vị trí tốt khi user đi **về các records cũ hơn**. Tuy nhiên, có một số tình huống:

1. Một record cũ được sửa `createdAt` sang mới hơn boundary: có thể biến mất khỏi hành trình hiện tại.
2. Một record đã xem được sửa sang timestamp cũ hơn: có thể gặp lại nó.
3. Một record bị xóa: nó tự nhiên không xuất hiện; khác offset, xóa record phía trước không dịch số vị trí.
4. Một field filter như `status` thay đổi: record có thể vào/ra tập kết quả trong lúc phân trang.

### 37.1. Anchor thời gian

Có thể giới hạn query theo một cutoff:

~~~javascript
{
  tenantId: "t-01",
  status: "PAID",
  createdAt: { $lte: ISODate("2026-11-14T08:00:00Z") }
}
~~~

Cutoff giúp **không đưa các record có createdAt mới hơn mốc** vào tập, nhưng không tạo snapshot ACID: delete, update status hoặc sửa createdAt của records cũ vẫn có thể ảnh hưởng. Đừng gọi anchor timestamp là snapshot nhất quán nếu không có cơ chế đảm bảo tương ứng.

### 37.2. Immutable sort key

Khi có thể, dùng trường tạo một lần và không sửa. Nếu UI phải sort theo updatedAt, xác định rõ semantics “dynamic feed” và tránh hứa không bao giờ trùng/thiếu giữa những HTTP requests cách xa nhau.

## 38. Lab mongosh: tạo dữ liệu có thời gian trùng nhau

Chỉ chạy trên MongoDB lab:

~~~javascript
use paging_lab

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
)

const base = ISODate("2026-11-01T00:00:00Z").getTime()

const docs = Array.from({ length: 120 }, (_, i) => ({
  tenantId: i % 10 === 0 ? "t-02" : "t-01",
  orderNo: "O-" + (1000 + i),
  status: i % 4 === 0 ? "PENDING" : "PAID",
  totalMinor: 10000 + i * 100,
  createdAt: new Date(base + Math.floor(i / 3) * 1000)
}))

db.orders.insertMany(docs)
~~~

Ví dụ cố ý cho ba documents có cùng timestamp để kiểm tra sort tie-breaker. `_id` tự được tạo nếu không cung cấp. Chạy lại lệnh sẽ thêm 120 records mới nữa; không dùng cùng collection lab để benchmark sau nhiều lần chạy mà không chú ý dữ liệu đã thay đổi.

### 38.1. Đọc trang đầu

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(0).limit(10)
~~~

### 38.2. Đọc trang thứ ba

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(20).limit(10)
~~~

### 38.3. Đo explain

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(20).limit(10)
.explain("executionStats")
~~~

Lab 120 records giúp hiểu cơ chế; không đại diện latency ở hàng triệu records.

## 39. Test logic thứ tự khi timestamp trùng

Từ lab, nhiều orders có cùng `createdAt`. Hãy so sánh:

~~~javascript
// Chưa có tie-breaker:
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1 })
  .limit(10)

// Có tie-breaker:
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
~~~

Kết quả ở lab có thể tình cờ giống nhau; điều đó **không chứng minh** sort chỉ theo createdAt luôn ổn định. Cần một thứ tự xác định từ semantics query, không từ quan sát một lần chạy.

### 39.1. Tại sao không sort `orderNo` tùy tiện?

Nếu `orderNo` không unique, hoặc thay đổi format/kiểu chuỗi, nó không nhất thiết phù hợp làm tie-breaker. `_id` unique và ổn định trong collection là lựa chọn phổ biến.

## 40. Test biến động dữ liệu giữa hai trang

Một bài mô phỏng:

1. Query page 0, size 3, lưu các `_id`.
2. Insert một document có `createdAt` mới hơn mọi document hiện tại.
3. Query page 1 bằng `skip(3)`.
4. So sánh `_id` hai trang, tìm record trùng.
5. Lặp lại với thao tác xóa một record phía trước offset trong một **lab riêng**.
6. Thử keyset query “sau lastCreatedAt,lastId” để so sánh.

Không chạy insert/delete để thử pagination trên production. Trong môi trường test, kiểm tra tổng tập dữ liệu trước/sau và dọn theo runbook của lab.

### 40.1. Kết luận cần rút ra

Sort tie-breaker giúp xác định thứ tự **trong mỗi query**, nhưng không đóng băng vị trí khi tập kết quả được cập nhật giữa các requests. Keyset dựa vào khóa đã xem thay vì số vị trí phải bỏ qua.

## 41. Benchmark Page, Slice và keyset

Thiết kế ba biến thể với cùng filter/index:

| Biến thể | Trả nội dung | Count | Pagination |
|---|---|---|---|
| A: `Page` | 20 records | Có thể cần count | Offset |
| B: `Slice` | 20 records + hasNext | Không cần total count | Offset |
| C: Keyset | 20 records + next token | Không cần total count | Seek theo sort keys |

Chạy ở offset tương đương page 0, 50, 1.000 và 10.000 trên dataset representative, với workload phù hợp. Đối với keyset, cần có token/last key tương ứng từ quá trình đọc thực tế; **không so sánh công bằng nếu lấy ngẫu nhiên một key mà không mô tả cách tìm key đó**.

### 41.1. Metrics nên thu

- Backend p50/p95/p99.
- MongoDB query execution time và count time.
- `totalKeysExamined`/`totalDocsExamined`.
- Số commands/cursor batches.
- MongoDB CPU, memory, I/O và index cache.
- Network bytes và size của HTTP response.
- Error/timeout rate ở peak concurrency.
- Đúng số record/tie-breaker/filter tenant.

### 41.2. Benchmark warm và cold

Cache, connection pool, TLS handshake và JVM JIT warm-up ảnh hưởng kết quả. Chạy nhiều vòng, phân biệt cold/warm và giữ cùng dataset/query semantics trước khi kết luận.

### 41.3. Count là một cost riêng

Nếu Page chậm hơn Slice, xác minh đó là count hay page query; không quy mọi chậm trễ cho `skip` khi khác biệt chính đến từ total count.

## 42. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Thay thế |
|---|---|---|
| `findAll()` rồi `subList` ở Java | Tải full collection, OOM | Pageable/Mongo query |
| Không chỉ định sort | Thứ tự không ổn định | Sort xác định |
| Sort chỉ theo `createdAt` khi trùng | Trùng/thiếu khi phân trang | Tie-breaker `id` |
| `PageRequest.of(page,size)` cho page cực sâu | Server work tăng | Giới hạn page hoặc keyset |
| Dùng `Page` dù UI chỉ cần hasNext | Count không cần thiết | `Slice`/keyset |
| Nghĩ Slice bỏ skip | Deep offset vẫn tốn | Keyset nếu cần |
| Reuse count query đã skip/limit | Total sai/khó hiểu | Count query cùng filter, không phân trang |
| Chuyển Page entity sang DTO sau khi load full | MongoDB vẫn trả fields lớn | Database projection |
| Nhận sort field raw từ client | Slow query/field misuse | Whitelist sort |
| Bỏ tenant filter rồi lọc ở Java | Truyền dữ liệu tenant khác | Query scope từ auth |
| Không có index filter/sort | COLLSCAN hoặc blocking SORT | Compound index theo access pattern |
| Tạo index cho mọi tổ hợp sort | Write/storage overhead | Tối ưu theo usage |
| Tin ObjectId là đồng hồ commit chính xác | Ordering sai assumptions | Business time + unique tie-breaker |
| Lưu cursor không có sort/filter binding | Tiếp trang sai, lộ dữ liệu | Signed token + validation |
| Dùng Base64 như encryption | Token bị đọc/sửa | Integrity signature và policy |
| Dùng keyset với sort key mutable nhưng hứa stable | Trùng/thiếu vẫn có thể | Immutable key/snapshot semantics |
| Coi `ReadConcern.MAJORITY` là snapshot xuyên HTTP requests | Hiểu sai consistency | Thiết kế read snapshot rõ |
| Đếm toàn collection thay filtered count | totalPages sai | Count theo filter |
| Test với 100 documents rồi tuyên bố deep skip nhanh | Benchmark không đại diện | Dataset/thời gian thực tế |

## 43. Bài thực hành A — PageRequest 0-based

Cho page size 25. Hãy tính offsets của `PageRequest.of(0,25)`, `PageRequest.of(3,25)` và `PageRequest.of(40,25)`. Viết MongoDB query tương đương với sort `createdAt:-1,_id:-1`.

## 44. Bài thực hành B — repository Page và Slice

Tạo `MongoRepository<Order,ObjectId>` có một method trả `Page<Order>` và một method trả `Slice<Order>` lọc theo `tenantId`, `status`. Nêu trường hợp UI cần totalPages và khi chỉ cần Load more.

## 45. Bài thực hành C — MongoTemplate và count

Viết `MongoTemplate.find` dùng `PageRequest.of(2,20,stableSort)`. Viết count query **không có skip/limit**. Giải thích vì sao tổng số documents match phải được đếm trên cùng filter, không phải chỉ trên content trang 2.

## 46. Bài thực hành D — sort tie-breaker

Ba documents có cùng `createdAt` nhưng khác `_id`. Tại sao chỉ sort theo createdAt không đủ? Nếu user thêm `_id` vào sort, vấn đề gì được giải quyết và vấn đề gì **vẫn chưa được giải quyết**?

## 47. Bài thực hành E — index và explain

Cho query filter `tenantId:"t-01",status:"PAID"`, sort `createdAt:-1,_id:-1`. Đề xuất compound index. Nếu explain cho page 5000 có `totalKeysExamined` lớn dù `nReturned=20`, giải thích nguyên nhân.

## 48. Bài thực hành F — insert khiến duplicate

Ban đầu `A B C D E F` (mới nhất trước), size 3, user đã xem `A B C`. Sau khi thêm `X` vào đầu, page 1 theo offset trả gì? Đề xuất keyset boundary tránh record lặp.

## 49. Bài thực hành G — delete khiến missing

Ban đầu `A B C D E F`, user đã xem page 0 `A B C`. `A` bị xóa trước khi request page 1. Query `skip(3)` trả gì? Record nào bị bỏ sót?

## 50. Bài thực hành H — keyset query

Với sort giảm dần `createdAt,-_id`, last key là timestamp T và ObjectId I. Viết điều kiện `createdAt < T OR (createdAt = T AND _id < I)`. Nêu vì sao phải dùng cả hai fields.

## 51. Bài thực hành I — continuation token

Thiết kế token chứa version, timestamp, last ObjectId, filter hash, tenant, sort và expiry. Những trường nào phải kiểm tra với authentication context? Tại sao Base64 không đủ để chống chỉnh sửa?

## 52. Bài thực hành J — sort động

API hỗ trợ newest-first, oldest-first, total-desc. Hãy tạo whitelist sort keys/directions và nêu index candidates. Giải thích khi nào keyset comparator dùng `$gt` thay vì `$lt`.

## 53. Bài thực hành K — dữ liệu mutable

Feed sort theo `updatedAt`, một record được update ngay sau khi user đọc page đầu. Tại sao cả offset và keyset đều có thể thay đổi hành vi? Khi nào cần một snapshot/export job thay vì live feed?

## 54. Bài thực hành L — multi-tenant và sharding

Một collection sharded chứa dữ liệu của hàng nghìn tenants. API quên filter `tenantId` nhưng vẫn dùng `limit(20)`. Nêu lỗi security và network/query routing. Nếu đã filter tenant, điều kiện gì giúp query target shards hiệu quả?

## 55. Bài thực hành M — projection và DTO

Entity Order có `items` và `auditTrail` rất lớn. Service dùng repository `Page<Order>` rồi gọi `Page.map(...)` để lấy summary. Điều này có chắc giảm BSON bytes MongoDB→Java không? Đề xuất projection tại tầng query.

## 56. Bài thực hành N — chọn thiết kế API

Ba màn hình:

1. Danh mục 300 sản phẩm, người dùng muốn nhảy “trang 7/15”.
2. Activity feed hàng triệu events, chỉ có nút “Load more”.
3. Export phục vụ audit cần ảnh chụp dữ liệu ổn định tại một thời điểm.

Hãy chọn Page/offset, Slice/keyset hoặc snapshot/export job tương ứng, và giải thích trade-offs.

## 57. Gợi ý đáp án thực hành

**A:** Offsets lần lượt 0, 75, 1000; MongoDB dùng `skip(offset).limit(25)` sau sort xác định.

**B:** `Page<Order> findByTenantIdAndStatus(...,Pageable)` phục vụ totalPages; `Slice<Order> readByTenantIdAndStatus(...,Pageable)` phục vụ hasNext. Slice không tự loại deep offset.

**C:** Content query dùng `Query.with(pageable)`. Count query mới dùng đúng tenant/status criteria, không có skip/limit; total là số matching records toàn tập.

**D:** Thêm `_id` làm tie-breaker tạo thứ tự xác định trong mỗi query; vẫn không ngăn inserts/deletes dịch offset giữa requests.

**E:** `{tenantId:1,status:1,createdAt:-1,_id:-1}` là index ứng viên. Deep skip vẫn duyệt nhiều index entries trước trang cần đọc.

**F:** Sau insert X, danh sách là X A B C D E F, page 1 skip 3 trả C D E; C trùng. Keyset “sau C” trả D E F nếu keys bất biến.

**G:** Sau xóa A, danh sách B C D E F, page 1 skip 3 trả E F; D bị bỏ sót.

**H:** `$or` kết hợp timestamp nhỏ hơn hoặc timestamp bằng và ObjectId nhỏ hơn; cần ID vì timestamp có thể trùng.

**I:** Server kiểm tra chữ ký, expiry, tenant, filter/sort binding và typed keys; Base64 chỉ encode, không bảo vệ integrity.

**J:** Chỉ cho một số fields/directions, có unique tie-breaker. Sort tăng dần thường dùng comparator `$gt` cho bước “sau”, với điều kiện tổng hợp nhiều trường đúng thứ tự.

**K:** UpdatedAt mutable có thể đẩy records qua ranh giới ngay cả với keyset. Với snapshot consistency chặt, dùng export/snapshot strategy được hỗ trợ.

**L:** Bỏ tenant filter có thể lộ dữ liệu và khiến scatter-gather; filter phải đến từ principal. Target shard tốt khi filter khớp shard key/routing policy.

**M:** `Page.map` xảy ra sau khi đọc entity, không chắc giảm bytes từ MongoDB. Dùng `query.fields()` hoặc repository projection.

**N:** Danh mục nhỏ nhảy trang: Page/offset hợp lý. Feed lớn: keyset/scroll có hasNext, không cần total. Audit export: controlled snapshot/export pipeline để nhất quán.

## 58. Những câu hỏi ôn tập

**1. `PageRequest.of(0,20)` có nghĩa gì?** — Trang đầu, tối đa 20 records.

**2. Offset của page 5 size 20 là bao nhiêu?** — 100.

**3. `Page<T>` trả thông tin gì thêm so với content?** — Total elements/pages và navigation metadata.

**4. Khi nào dùng `Slice<T>`?** — Khi chỉ cần content và hasNext, không cần total count.

**5. Slice có tránh skip sâu không?** — Không nếu vẫn dùng PageRequest offset.

**6. Vì sao Page có thể chậm hơn Slice?** — Có thể cần thêm filtered count.

**7. `countDocuments` và `estimatedDocumentCount` có giống nhau không?** — Không; estimate toàn collection không thay count theo filter chính xác.

**8. `MongoTemplate.with(pageable)` làm gì?** — Áp các thông số sort/skip/limit của Pageable vào Query.

**9. Count query nên dùng skip/limit của content không?** — Không nếu cần total matching records.

**10. Vì sao cần sort trước pagination?** — Để định nghĩa thứ tự kết quả.

**11. Sort chỉ theo createdAt có luôn xác định?** — Không nếu nhiều records có cùng timestamp.

**12. Vì sao thêm _id?** — Để tạo tie-breaker duy nhất và keyset boundary.

**13. ObjectId có chứng minh thứ tự commit chính xác không?** — Không.

**14. Deep skip có thể chậm ngay cả khi có index?** — Có vì phải duyệt nhiều kết quả đứng trước.

**15. Compound index gợi ý cho tenant/status + time sort?** — `{tenantId:1,status:1,createdAt:-1,_id:-1}`.

**16. Index có tự loại mọi chi phí skip không?** — Không.

**17. `explain("executionStats")` giúp xem gì?** — Keys/docs examined, winning plan, nReturned và execution stats.

**18. Insert mới trước page boundary gây gì?** — Offset có thể lặp document.

**19. Xóa document trước boundary gây gì?** — Offset có thể bỏ sót document.

**20. Tie-breaker có chữa insert/delete drift không?** — Không.

**21. Keyset dựa trên gì?** — Giá trị sort của record cuối đã trả, không dựa trên rank offset.

**22. Keyset có nhảy ngay tới trang 500 không?** — Không tự nhiên, thường cần continuation/anchor.

**23. `ScrollPosition.offset()` có phải keyset không?** — Không, nó biểu thị offset scrolling.

**24. Keyset cần sort key bất biến không?** — Rất có lợi; key mutable vẫn có thể gây sai lệch giữa pages.

**25. Token Base64 có chống sửa không?** — Không, cần chữ ký/integrity policy.

**26. Token có thay authorization không?** — Không; mỗi request vẫn phải kiểm tra quyền.

**27. Tại sao không dùng raw sort field từ client?** — Có thể làm query chậm hoặc truy cập field không được phép.

**28. `Page.map` có tự tạo DB projection không?** — Không.

**29. ReadConcern.MAJORITY có tạo snapshot giữa hai HTTP requests không?** — Không.

**30. Có nên dùng transaction kéo dài khi người dùng click từng trang?** — Không mặc định; cần đánh giá giới hạn/tài nguyên.

**31. Sharding có làm deep skip miễn phí không?** — Không, có thể còn overhead routing/merge.

**32. Vì sao API nên giới hạn maxPage/maxSize?** — Tránh query quá sâu/lớn và bảo vệ tài nguyên.

**33. Tại sao phải đo p95/p99, không chỉ average?** — Trang sâu/concurrent writes có thể gây tail latency xấu.

**34. Khi nào offset vẫn ổn?** — Dataset nhỏ/độ sâu thấp/nhảy số trang và SLA đạt.

**35. Khi nào nên cân nhắc keyset?** — Feed/danh sách lớn, tải tiếp tuần tự, cần tránh deep skip.

## 59. Bảng ghi nhớ nhanh

| Mục đích | API/ý tưởng |
|---|---|
| Tạo page request | `PageRequest.of(page,size,sort)` |
| Sort nhiều trường | `Sort.by(Order.desc("createdAt"),Order.desc("id"))` |
| Repository Page | `Page<T> findBy...(filters,Pageable)` |
| Repository Slice | `Slice<T> readBy...(filters,Pageable)` |
| Lấy content | `page.getContent()` |
| Total elements/pages | `page.getTotalElements()/getTotalPages()` |
| Có trang sau | `slice.hasNext()` |
| MongoTemplate | `Query.query(criteria).with(pageable)` |
| Tổng filtered records | `mongoTemplate.count(countQuery,Order.class)` |
| Tránh count không cần | `Slice` hoặc keyset |
| Offset query | `sort + skip + limit` |
| Sort ổn định | `createdAt DESC, _id DESC` |
| Index ứng viên | `tenantId,status,createdAt DESC,_id DESC` |
| Query plan | `explain("executionStats")` |
| Giới hạn deep skip | Chuyển keyset/seek khi phù hợp |
| Keyset boundary | `createdAt<T OR (createdAt=T AND _id<I)` |
| Keyset API | `nextCursor` có integrity validation |
| Spring Data scrolling | `Window`/`ScrollPosition` ở version hỗ trợ |
| Projection | `Query.fields().include(...)` |
| Security | Filter theo tenant từ principal + whitelist sort |
| Stable export | Snapshot/export job thay vì live offset |

## 60. Checklist trước khi triển khai production

- [ ] Page index 0-based đã được thống nhất giữa frontend và backend?
- [ ] `pageSize` tối đa và `pageNumber` tối đa đã được kiểm soát?
- [ ] Repository/MongoTemplate filter theo tenant và quyền đã xác thực?
- [ ] Có sort rõ ràng, không dựa vào natural order?
- [ ] Sort có tie-breaker unique như `_id`?
- [ ] Field sort có type/giá trị nhất quán và được index phù hợp?
- [ ] Đã xem `explain` với offsets đại diện, gồm trang sâu nhất thường dùng?
- [ ] Đã đo `totalKeysExamined`/`totalDocsExamined`?
- [ ] Có phân biệt chi phí count và chi phí page query?
- [ ] UI thật sự cần `totalElements/totalPages` hay chỉ cần hasNext?
- [ ] Nếu dùng `Slice`, đã hiểu rằng offset/skip vẫn còn?
- [ ] Nếu dùng keyset, token có đủ keys, sort/filter binding và validation?
- [ ] Token được ký, kiểm tra tenant, expiry và không chứa secrets?
- [ ] Khi đổi sort/filter, có bắt đầu pagination mới?
- [ ] Keyset xử lý timestamp precision, ObjectId, null và collation đúng?
- [ ] Dữ liệu có mutable sort key không và UX chấp nhận semantics nào?
- [ ] Có chiến lược nhất quán riêng cho export/audit nếu yêu cầu?
- [ ] Không dùng raw user input cho sort fields hoặc database namespace?
- [ ] Có filter theo shard key/routing khi sharded cluster phù hợp?
- [ ] Đã giảm payload bằng projection thay vì chỉ `Page.map` sau khi tải?
- [ ] API response contract không phụ thuộc JSON shape nội bộ của PageImpl?
- [ ] Có tests cho timestamp trùng, insert/delete giữa pages và page cuối?
- [ ] Có performance benchmark đủ dữ liệu, p95/p99 và peak concurrency?
- [ ] Có monitoring cho deep page requests, slow count và timeouts?
- [ ] Có khả năng rollback thiết kế pagination/API nếu deployment có regression?

## 61. Kết luận

Spring Data MongoDB làm phân trang rất thuận tiện nhờ **`Pageable`, `PageRequest`, `Sort`, `Page` và `Slice`**. Với dataset nhỏ và nhu cầu nhảy đến trang số N, offset pagination là lựa chọn rõ ràng, dễ triển khai. Nhưng phải cấu hình **filter và sort ổn định**, dùng index phù hợp và tránh tải full documents không cần thiết.

Giới hạn cốt lõi của offset là MongoDB thường phải duyệt những kết quả đứng trước trang cần đọc: `skip(100000)` vẫn có thể tốn tài nguyên dù chỉ trả 20 records. Đặc biệt, khi có insert/delete trước ranh giới trang, **record có thể bị trùng hoặc bỏ sót** giữa các lần request. `Slice` tránh total count nhưng không xóa được các giới hạn này nếu vẫn dùng offset.

Với danh sách lớn, đọc tiếp tuần tự và yêu cầu latency ổn định hơn ở trang sâu, **keyset/seek pagination** dựa trên cặp khóa như `createdAt` và `_id` thường đáng cân nhắc. Tuy vậy, keyset không tự tạo snapshot dữ liệu, cần sort keys ổn định, indexes, token an toàn và API contract phù hợp. Hãy quyết định giữa **Page/offset, Slice hay keyset/scrolling** theo UX, dữ liệu, tính đúng, consistency và benchmark — không chỉ theo độ ngắn của đoạn code.
