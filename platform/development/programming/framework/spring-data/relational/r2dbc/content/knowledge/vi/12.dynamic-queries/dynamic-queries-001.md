# Xây dựng Query, Criteria và Update

Trong Spring Data Relational R2DBC, `Query`, `Criteria` và `Update` là các thành phần giúp xây dựng truy vấn động mà không phải ghép chuỗi SQL thủ công. Chúng thường được sử dụng cùng `R2dbcEntityTemplate` khi điều kiện tìm kiếm thay đổi theo request, khi cần phân trang/sắp xếp hoặc khi muốn cập nhật một số thuộc tính mà không tải toàn bộ entity trước.

`Criteria` mô tả điều kiện lọc; `Query` kết hợp điều kiện với thông tin truy vấn như sort, limit và offset; `Update` mô tả những thuộc tính cần thay đổi. `R2dbcEntityTemplate` chuyển các đối tượng này thành thao tác R2DBC, bind giá trị và ánh xạ kết quả theo metadata entity.

## 1. Vị trí của Query, Criteria và Update trong kiến trúc

Các thành phần này thuộc Spring Data Relational, nằm ở tầng thao tác entity cao hơn `DatabaseClient`:

```text
Application service
        |
        v
R2dbcEntityTemplate
        |
        +-------------------+
        |                   |
        v                   v
      Query              Update
        |                   |
        v                   v
     Criteria          các giá trị cần ghi
        |                   |
        +---------+---------+
                  |
                  v
       Spring Data Relational mapping
                  |
                  v
              R2DBC SPI
                  |
                  v
             R2DBC driver
                  |
                  v
               Database
```

Mỗi thành phần có trách nhiệm riêng:

- **`Criteria`:** biểu diễn điều kiện như bằng, lớn hơn, thuộc một tập giá trị, khớp mẫu hoặc null.
- **`Query`:** chứa điều kiện và các tùy chọn đọc như sắp xếp, giới hạn số hàng và offset.
- **`Update`:** mô tả các cột/thuộc tính cần đặt giá trị trong thao tác UPDATE.
- **`R2dbcEntityTemplate`:** thực thi select, update hoặc delete bằng `ConnectionFactory`, đồng thời sử dụng mapping metadata của entity.

Ví dụ import:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
```

Các API này hữu ích khi câu truy vấn cần được xây dựng theo từng điều kiện tùy chọn. Với câu SQL đặc thù, join phức tạp hoặc tính năng riêng của database, `DatabaseClient` và `@Query` vẫn có thể phù hợp hơn.

## 2. Query: mô tả một yêu cầu truy vấn

`Query` là đối tượng mô tả truy vấn. Nó thường được tạo từ một `Criteria`:

```java
Query query = Query.query(
    Criteria.where("status").is("ACTIVE")
);
```

Truy vấn này biểu diễn yêu cầu tìm các entity có `status` bằng `ACTIVE`. Bản thân `Query` chưa thực thi SQL; nó là mô tả được truyền cho `R2dbcEntityTemplate`.

Ví dụ đọc tất cả khách hàng phù hợp:

```java
Flux<Customer> customers = template.select(
    Query.query(Criteria.where("status").is("ACTIVE")),
    Customer.class
);
```

`select(query, Customer.class)` trả về `Flux<Customer>`. Các hàng kết quả được ánh xạ sang entity `Customer` theo metadata Spring Data Relational.

Nếu chỉ cần một kết quả, có thể dùng `selectOne`:

```java
Mono<Customer> customer = template.selectOne(
    Query.query(Criteria.where("email").is(email)),
    Customer.class
);
```

`selectOne` phù hợp khi điều kiện được kỳ vọng trả về tối đa một hàng. Nếu database trả nhiều hàng, thao tác có thể báo lỗi thay vì âm thầm chọn một hàng. Nếu chỉ cần hàng đầu tiên theo một thứ tự cụ thể, hãy thiết kế truy vấn với sort/limit phù hợp và dùng API thích hợp của template.

## 3. Criteria: xây dựng điều kiện lọc

`Criteria` là phần mô tả predicate. Có thể tạo điều kiện đơn giản bằng `Criteria.where(property)` rồi chọn phép so sánh.

```java
Criteria criteria = Criteria.where("status").is("ACTIVE");
```

Một số toán tử thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `is(value)` | Bằng giá trị | `where("status").is("ACTIVE")` |
| `not(value)` | Khác giá trị | `where("status").not("DELETED")` |
| `in(values)` | Thuộc tập giá trị | `where("status").in(statuses)` |
| `notIn(values)` | Không thuộc tập giá trị | `where("type").notIn(types)` |
| `greaterThan(value)` | Lớn hơn | `where("price").greaterThan(min)` |
| `greaterThanOrEquals(value)` | Lớn hơn hoặc bằng | `where("createdAt").greaterThanOrEquals(from)` |
| `lessThan(value)` | Nhỏ hơn | `where("price").lessThan(max)` |
| `lessThanOrEquals(value)` | Nhỏ hơn hoặc bằng | `where("createdAt").lessThanOrEquals(to)` |
| `between(from, to)` | Nằm trong khoảng | `where("price").between(min, max)` |
| `like(pattern)` | Khớp mẫu LIKE | `where("name").like("A%")` |
| `isNull()` | Giá trị null | `where("deletedAt").isNull()` |
| `isNotNull()` | Giá trị không null | `where("email").isNotNull()` |

Khả năng và tên phương thức cụ thể cần đối chiếu với phiên bản Spring Data Relational đang sử dụng. Các ví dụ minh họa cách biểu đạt phổ biến của Criteria API.

### 3.1. Kết hợp nhiều điều kiện AND

Các điều kiện có thể được nối bằng `and`:

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
    .and("age").greaterThanOrEquals(18)
    .and("country").is("VN");

Query query = Query.query(criteria);
Flux<Customer> customers = template.select(query, Customer.class);
```

Điều kiện trên yêu cầu đồng thời:

- `status` bằng `ACTIVE`.
- `age` lớn hơn hoặc bằng 18.
- `country` bằng `VN`.

Về mặt logic, điều kiện tương đương `status = 'ACTIVE' AND age >= 18 AND country = 'VN'`.

### 3.2. Kết hợp điều kiện OR

Khi nghiệp vụ cho phép nhiều lựa chọn, có thể kết hợp các nhánh bằng `or`:

```java
Criteria criteria = Criteria.where("status").is("NEW")
    .or("status").is("PROCESSING");

Query query = Query.query(criteria);
Flux<Order> orders = template.select(query, Order.class);
```

Điều kiện có nghĩa trạng thái là `NEW` hoặc `PROCESSING`. Khi kết hợp nhiều nhóm AND/OR, cần kiểm tra thứ tự nhóm và ngoặc logic trong SQL được sinh. Nếu biểu thức phức tạp, hãy chia thành các nhóm Criteria rõ ràng và xác nhận câu SQL bằng integration test hoặc log SQL ở môi trường phát triển.

### 3.3. Điều kiện khoảng ngày

Ví dụ lọc đơn hàng được tạo trong một khoảng thời gian:

```java
Criteria criteria = Criteria.where("createdAt")
    .greaterThanOrEquals(from)
    .and("createdAt")
    .lessThan(to);
```

Với khoảng thời gian, hãy thống nhất múi giờ và kiểu Java/database. Nếu cột lưu UTC, service nên chuyển thời gian đầu vào sang cùng quy ước trước khi tạo Criteria. Nên xác định rõ khoảng đóng/mở, ví dụ `[from, to)`, để hai trang thời gian liền nhau không trùng hoặc bỏ sót dữ liệu.

## 4. Xây dựng Criteria động từ bộ lọc tùy chọn

Trong API tìm kiếm, người dùng thường chỉ gửi một số điều kiện. Ví dụ, request có thể có status, tên, giá tối thiểu và ngày tạo bắt đầu. Không nên tạo một câu SQL riêng cho mọi tổ hợp filter. Hãy thêm Criteria khi tham số thực sự có giá trị.

Giả sử filter:

```java
public record ProductFilter(
    String status,
    String name,
    BigDecimal minPrice,
    Instant createdAfter
) {}
```

Có thể xây dựng điều kiện như sau:

```java
Criteria criteria = Criteria.empty();

if (filter.status() != null && !filter.status().isBlank()) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.name() != null && !filter.name().isBlank()) {
    criteria = criteria.and("name").like("%" + filter.name() + "%");
}

if (filter.minPrice() != null) {
    criteria = criteria.and("price").greaterThanOrEquals(filter.minPrice());
}

if (filter.createdAfter() != null) {
    criteria = criteria.and("createdAt").greaterThanOrEquals(filter.createdAfter());
}

Query query = Query.query(criteria);
Flux<Product> products = template.select(query, Product.class);
```

Khi một filter không được cung cấp, predicate tương ứng không được thêm vào. Kết quả là truy vấn chỉ chứa các điều kiện mà người dùng thực sự yêu cầu.

`Criteria.empty()` là điểm bắt đầu thuận tiện cho việc ghép điều kiện tùy chọn. Hãy kiểm tra API của phiên bản Spring Data Relational trong dự án nếu phiên bản cũ không có phương thức này; có thể bắt đầu từ điều kiện đầu tiên rồi mới nối các điều kiện tiếp theo.

### 4.1. Phân biệt filter không gửi và filter có giá trị null

Trong API PATCH hoặc tìm kiếm nâng cao, `null` có thể mang nhiều nghĩa:

- Client không gửi field: không thêm điều kiện lọc.
- Client gửi field với null: có thể muốn tìm các hàng có cột null.
- Client gửi giá trị rỗng: có thể muốn bỏ qua hoặc tìm chuỗi rỗng, tùy hợp đồng API.

Một DTO dùng `String status` đơn giản có thể không phân biệt được field bị bỏ qua với field được gửi explicit null sau khi deserialize. Nếu cần phân biệt, hãy dùng kiểu biểu diễn sự hiện diện của field, wrapper request hoặc một cấu trúc filter có cờ `provided` riêng.

Ví dụ, nếu muốn lọc các hàng có `deletedAt IS NULL`, phải thêm `Criteria.where("deletedAt").isNull()` một cách tường minh. Không nên bỏ qua predicate chỉ vì giá trị filter là null nếu null chính là điều kiện nghiệp vụ.

### 4.2. Bảo vệ truy vấn khi không có filter

Nếu tất cả filter đều trống, `Criteria.empty()` có thể tạo truy vấn không có điều kiện. Với thao tác SELECT, điều đó có thể có nghĩa đọc toàn bộ bảng. Với UPDATE hoặc DELETE, đây có thể là lỗi nghiêm trọng.

Service nên quyết định rõ có cho phép tìm kiếm không điều kiện hay không:

```java
boolean hasFilter =
    filter.status() != null ||
    filter.name() != null ||
    filter.minPrice() != null ||
    filter.createdAfter() != null;

if (!hasFilter) {
    return Flux.error(new IllegalArgumentException(
        "Cần cung cấp ít nhất một điều kiện tìm kiếm"));
}
```

Nếu endpoint cho phép đọc toàn bộ dữ liệu, vẫn nên giới hạn số hàng, áp dụng phân trang và kiểm soát quyền truy cập.

## 5. Query với sort, limit và offset

`Query` không chỉ chứa Criteria. Nó còn có thể mô tả cách sắp xếp và giới hạn kết quả.

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE"))
    .sort(Sort.by(Sort.Order.desc("createdAt")))
    .limit(50)
    .offset(0);

Flux<Customer> page = template.select(query, Customer.class);
```

Trong ví dụ:

- `sort(...)` sắp xếp theo thời gian tạo giảm dần.
- `limit(50)` giới hạn tối đa 50 hàng.
- `offset(0)` bắt đầu từ hàng đầu tiên.

Nên thêm một khóa duy nhất vào cuối thứ tự sắp xếp để có thứ tự ổn định, đặc biệt khi nhiều hàng có cùng timestamp:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Khi dùng sort động từ request, không truyền trực tiếp tên cột tùy ý vào API. Hãy ánh xạ giá trị người dùng gửi sang danh sách thuộc tính được phép:

```java
String sortProperty = switch (requestedSort) {
    case "name" -> "name";
    case "price" -> "price";
    case "createdAt" -> "createdAt";
    default -> "createdAt";
};

Sort.Direction direction = descending
    ? Sort.Direction.DESC
    : Sort.Direction.ASC;

Sort sort = Sort.by(direction, sortProperty);
```

Giá trị filter được bind như dữ liệu; tên thuộc tính sort là identifier. Identifier không thể được bảo vệ bằng cách bind như một giá trị thông thường, vì vậy cần whitelist.

### 5.1. Tính offset an toàn

Nếu API nhận `page` và `size`, cần xác thực chúng trước khi tạo Query:

```java
int safePage = Math.max(0, page);
int safeSize = Math.max(1, Math.min(size, 100));
long offset = (long) safePage * safeSize;

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.desc("createdAt"),
                  Sort.Order.desc("id")))
    .limit(safeSize)
    .offset(offset);
```

Ép sang `long` trước phép nhân giúp tránh tràn số nguyên khi page lớn. Giới hạn `safeSize` ngăn client yêu cầu một trang quá lớn và chiếm nhiều tài nguyên.

### 5.2. OFFSET và keyset pagination

Offset pagination thuận tiện khi giao diện cần số trang cụ thể, nhưng truy vấn trang sâu có thể tốn chi phí vì database phải bỏ qua nhiều hàng. Với dữ liệu lớn được đọc tuần tự, keyset pagination có thể phù hợp hơn:

```java
Criteria criteria = Criteria.where("id").greaterThan(lastSeenId);

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.asc("id")))
    .limit(batchSize);
```

Sau mỗi batch, lấy ID cuối cùng làm `lastSeenId` cho lượt tiếp theo. Cột cursor nên có index và thứ tự phải ổn định. Nếu sắp xếp theo nhiều cột, điều kiện cursor phải phản ánh đầy đủ thứ tự đó.

## 6. Đếm số kết quả với cùng Criteria

Khi giao diện cần tổng số bản ghi phù hợp, có thể dùng `count` với cùng Query:

```java
Query query = Query.query(criteria);

Mono<Long> total = template.count(query, Product.class);
Flux<Product> products = template.select(
    query.limit(pageSize).offset(offset),
    Product.class
);
```

Count và select là hai thao tác database riêng. Nếu dữ liệu thay đổi giữa hai thao tác, tổng số và nội dung trang có thể không phản ánh cùng một snapshot, trừ khi chúng chạy trong transaction/isolation phù hợp. Không nên chạy count chính xác cho mọi endpoint nếu chi phí truy vấn lớn và giao diện không thực sự cần.

## 7. Update: cập nhật một phần entity

`Update` mô tả các giá trị cần ghi vào database. Nó thường được dùng cùng `Query` để xác định những hàng cần cập nhật.

Ví dụ đổi trạng thái một đơn hàng:

```java
Query query = Query.query(Criteria.where("id").is(orderId));

Update update = Update.update("status", "PAID")
    .set("updatedAt", Instant.now());

Mono<Long> affected = template.update(query, update, Order.class);
```

`template.update(...)` trả về `Mono<Long>` biểu diễn số hàng bị ảnh hưởng theo báo cáo của driver. Không cần tải entity rồi gọi `save` nếu chỉ cần thay đổi một số thuộc tính và nghiệp vụ không cần toàn bộ object hiện tại.

### 7.1. Cập nhật nhiều thuộc tính

Có thể nối nhiều lệnh `set`:

```java
Update update = Update.update("status", "SHIPPED")
    .set("shippedAt", Instant.now())
    .set("trackingCode", trackingCode)
    .set("updatedAt", Instant.now());

Mono<Long> affected = template.update(
    Query.query(Criteria.where("id").is(orderId)),
    update,
    Order.class
);
```

Chỉ những thuộc tính được liệt kê trong `Update` mới được cập nhật bởi thao tác này. Các cột khác giữ nguyên giá trị hiện tại trong database.

### 7.2. Update động theo request

Giả sử một request chỉ có thể thay đổi tên và mô tả sản phẩm:

```java
Update update = Update.empty();

if (request.name() != null && !request.name().isBlank()) {
    update = update.set("name", request.name());
}

if (request.description() != null) {
    update = update.set("description", request.description());
}

if (!update.hasAssignments()) {
    return Mono.error(new IllegalArgumentException(
        "Không có thuộc tính nào cần cập nhật"));
}

Query query = Query.query(Criteria.where("id").is(productId));
return template.update(query, update, Product.class);
```

Đoạn code minh họa cách thêm assignment có điều kiện. Tùy phiên bản Spring Data Relational, API khởi tạo `Update.empty()` và kiểm tra assignment có thể khác hoặc không được công khai. Có thể xây dựng `Update` từ map hoặc tạo từ assignment đầu tiên rồi mới nối `set`; hãy dùng API được cung cấp bởi phiên bản dự án.

Điều quan trọng là xác định rõ ý nghĩa của null. Trong ví dụ trên, `description == null` được coi là không cập nhật. Nếu request muốn xóa nội dung bằng cách đặt cột thành SQL NULL, cần biểu diễn sự hiện diện của field riêng và thêm assignment null theo API binding được hỗ trợ. Không được gộp “không gửi field” và “gửi null để xóa giá trị” thành cùng một trường hợp.

### 7.3. Cập nhật theo điều kiện để tránh ghi đè dữ liệu mới

Có thể đưa trạng thái hiện tại vào Query để chỉ cập nhật khi điều kiện vẫn đúng:

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("status").is("PAID")
);

Update update = Update.update("status", "SHIPPED");

Mono<Long> affected = template.update(query, update, Order.class);
```

Đây là dạng compare-and-set: chỉ chuyển trạng thái nếu đơn hàng vẫn đang `PAID`. Nếu số hàng bị ảnh hưởng bằng 0, có thể đơn hàng không tồn tại hoặc trạng thái đã thay đổi. Service cần quyết định cách phân biệt các trường hợp đó, có thể đọc lại entity khi cần.

## 8. Update và optimistic locking

Nếu entity có `@Version`, Spring Data có thể dùng version để kiểm soát cập nhật đồng thời khi thao tác entity theo cơ chế hỗ trợ. Với câu lệnh `Update` tùy chỉnh, không nên giả định mọi quy tắc version được áp dụng tự động giống `save` trên entity.

Khi cần compare-and-set thủ công, có thể đưa version hiện tại vào Criteria và tăng version trong Update theo cách database/driver hỗ trợ:

```java
Query query = Query.query(
    Criteria.where("id").is(id)
        .and("version").is(expectedVersion)
);

Update update = Update.update("status", newStatus)
    .set("version", expectedVersion + 1);

Mono<Long> affected = template.update(query, update, Order.class);
```

Nếu `affected` bằng 0, version không còn khớp hoặc hàng không tồn tại. Đây là minh họa optimistic compare-and-set ở tầng SQL; hãy xác nhận kiểu version, quy tắc tăng version và transaction với database mục tiêu. Không nên vừa tự tăng version trong `Update` vừa kỳ vọng framework tự tăng lần nữa.

## 9. Delete bằng Query và Criteria

`Query` và `Criteria` cũng có thể xác định các hàng cần xóa:

```java
Query query = Query.query(
    Criteria.where("status").is("EXPIRED")
        .and("expiresAt").lessThan(Instant.now())
);

Mono<Long> deleted = template.delete(query, Session.class);
```

Thao tác trả về số hàng bị xóa. Với dữ liệu quan trọng, hãy kiểm tra predicate kỹ và cân nhắc soft delete thay vì xóa vật lý.

Không dùng Criteria rỗng cho UPDATE hoặc DELETE trừ khi nghiệp vụ thực sự yêu cầu thay đổi toàn bộ bảng và có quy trình kiểm soát riêng. Một filter bị bỏ qua do lỗi deserialize có thể biến một thao tác giới hạn thành thao tác trên toàn bộ dữ liệu.

## 10. Tên thuộc tính, tên cột và mapping metadata

`Criteria` và `Update` được sử dụng trong ngữ cảnh entity class, vì vậy cần thống nhất tên thuộc tính với mapping metadata của Spring Data Relational. Nếu entity dùng `@Column`, naming strategy hoặc tên cột khác tên field, hãy kiểm tra quy tắc chuyển đổi mà phiên bản framework áp dụng.

Ví dụ:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
```

Khi tạo Criteria/Update, dùng tên thuộc tính theo cách API và mapping context của phiên bản dự án yêu cầu; không tự suy luận rằng tên Java luôn trùng tên cột vật lý. Với `DatabaseClient`, ngược lại, SQL được viết trực tiếp nên phải dùng tên cột thật trong câu lệnh.

Đây là một lý do nên viết integration test với schema thật hoặc kiểm tra SQL được sinh khi đổi `@Column` hay naming strategy.

## 11. Criteria và Update có an toàn trước SQL injection không?

Khi dùng API Criteria/Update đúng cách, các giá trị điều kiện và giá trị cập nhật được framework bind như tham số thay vì nối trực tiếp vào SQL. Ví dụ:

```java
Criteria criteria = Criteria.where("email").is(request.email());
Query query = Query.query(criteria);
```

Giá trị `request.email()` được xử lý như dữ liệu. Tuy nhiên, điều đó không có nghĩa mọi thành phần động đều tự động an toàn.

Các identifier như tên thuộc tính sort, tên cột được đưa vào Criteria/Update hoặc tên bảng không phải là giá trị bind thông thường. Không cho client gửi chuỗi tùy ý để chọn identifier. Hãy dùng whitelist:

```java
String property = switch (request.sortBy()) {
    case "name" -> "name";
    case "createdAt" -> "createdAt";
    case "price" -> "price";
    default -> "createdAt";
};
```

Với `LIKE`, ký tự `%` và `_` có ý nghĩa wildcard. Nếu nghiệp vụ muốn tìm chuỗi literal, hãy escape các ký tự wildcard theo quy tắc database/dialect và khai báo escape clause phù hợp nếu API hỗ trợ. Không để người dùng vô tình hoặc cố ý biến một tìm kiếm chính xác thành mẫu khớp quá rộng.

## 12. Xử lý collection rỗng trong điều kiện IN

Điều kiện `IN` hữu ích khi lọc theo một tập ID hoặc trạng thái:

```java
Criteria criteria = Criteria.where("status").in(statuses);
```

Nhưng cần xác định hành vi khi `statuses` rỗng. Một số database hoặc cách tạo SQL không chấp nhận `IN ()`; ngay cả khi framework xử lý được, ý nghĩa nghiệp vụ có thể không rõ.

Hãy xử lý trước:

```java
if (statuses == null || statuses.isEmpty()) {
    return Flux.empty();
}

Criteria criteria = Criteria.where("status").in(statuses);
return template.select(Query.query(criteria), Order.class);
```

Nếu collection rỗng có nghĩa không áp dụng filter, có thể bỏ predicate. Nếu có nghĩa không có kết quả nào được phép, trả `Flux.empty()` thường rõ ràng hơn. Không để một tập rỗng vô tình trở thành truy vấn không điều kiện.

## 13. Transaction khi kết hợp nhiều thao tác

Một use case có thể cần đọc, cập nhật và ghi audit trong cùng transaction. Có thể compose các publisher từ template và dùng reactive transaction management.

Ví dụ:

```java
@Service
public class OrderService {

    private final R2dbcEntityTemplate template;

    public OrderService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Transactional
    public Mono<Long> markShipped(Long orderId) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("status").is("PAID")
        );

        Update update = Update.update("status", "SHIPPED")
            .set("updatedAt", Instant.now());

        return template.update(query, update, Order.class);
    }
}
```

Phương thức trả về `Mono` để Spring quản lý ranh giới reactive transaction. Không gọi `block()` bên trong phương thức. Transaction manager và template phải sử dụng cùng `ConnectionFactory` để thao tác tham gia cùng transaction.

Nếu một use case cần cập nhật nhiều bảng, hãy xác định điều kiện rollback và số hàng bị ảnh hưởng. Một thao tác trả về 0 hàng có thể là kết quả nghiệp vụ bình thường hoặc dấu hiệu dữ liệu đã thay đổi; cần quyết định rõ có tiếp tục transaction hay phát lỗi.

## 14. So sánh Query/Criteria/Update với các lựa chọn khác

| Cách tiếp cận | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Derived query trong repository | Điều kiện ổn định, tên phương thức diễn đạt rõ | Không thuận tiện khi filter thay đổi nhiều tổ hợp |
| `@Query` trong repository | SQL cố định, cần kiểm soát câu lệnh | SQL gắn với repository method; dynamic SQL phức tạp khó tổ chức |
| `Query` + `Criteria` | Truy vấn entity động, filter tùy chọn, sort/page | Cần quản lý predicate, identifier và trường hợp rỗng |
| `Update` cùng `R2dbcEntityTemplate` | Cập nhật một phần các thuộc tính theo điều kiện | Cần kiểm tra số hàng ảnh hưởng và concurrency |
| `DatabaseClient` | SQL đặc thù, join/projection tùy chỉnh hoặc dialect-specific | Ứng dụng tự viết SQL và mapper |

Các cách tiếp cận có thể cùng tồn tại. Repository phù hợp với hợp đồng CRUD/queries phổ biến; template phù hợp với thao tác entity động; DatabaseClient phù hợp khi cần kiểm soát SQL trực tiếp.

## 15. Kiểm thử truy vấn động

Kiểm thử nên xác nhận cả cách ghép điều kiện và kết quả SQL trên database tương thích.

Các trường hợp nên có:

- Không có filter và filter rỗng.
- Chỉ có một điều kiện; nhiều điều kiện AND; các nhánh OR.
- Giá trị null, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- `IN` với tập có giá trị và tập rỗng.
- `LIKE` với `%`, `_` và ký tự escape.
- Sort theo từng thuộc tính được whitelist và hướng tăng/giảm.
- Page đầu, page sâu, size bằng 0, size âm và size vượt giới hạn.
- Update một field, nhiều field và không có assignment.
- Update không tìm thấy hàng hoặc predicate không còn đúng.
- Delete với điều kiện hẹp và trường hợp không có hàng phù hợp.
- Transaction rollback khi một thao tác tiếp theo phát lỗi.
- Optimistic locking hoặc compare-and-set khi có cập nhật đồng thời.

`StepVerifier` có thể kiểm tra kết quả reactive:

```java
StepVerifier.create(productService.search(filter))
    .expectNextMatches(product -> product.getStatus().equals("ACTIVE"))
    .verifyComplete();
```

Với thao tác update, kiểm tra số hàng bị ảnh hưởng:

```java
StepVerifier.create(productService.changeStatus(id, "ARCHIVED"))
    .expectNext(1L)
    .verifyComplete();
```

Ví dụ giả định chỉ có một hàng phù hợp. Test thực tế cần chuẩn bị dữ liệu xác định, kiểm tra cả trường hợp 0 hàng và nhiều hàng nếu nghiệp vụ cho phép.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghép chuỗi SQL để tạo filter | Khó bảo trì và có nguy cơ SQL injection | Dùng Criteria để bind giá trị |
| Không kiểm tra filter rỗng | Có thể đọc toàn bảng hoặc cập nhật/xóa quá rộng | Đặt guard theo nghiệp vụ |
| Dùng tên sort do client gửi trực tiếp | Identifier động không được bảo vệ như giá trị bind | Whitelist thuộc tính được phép |
| Không giới hạn page size | Truy vấn có thể trả quá nhiều hàng | Xác thực page/size và đặt maximum |
| Dùng offset sâu để quét dữ liệu lớn | Chi phí truy vấn có thể tăng | Cân nhắc keyset pagination |
| Dùng `IN` với collection rỗng mà không xử lý | SQL hoặc ý nghĩa filter không rõ | Trả rỗng hoặc bỏ filter theo hợp đồng API |
| Xem null là luôn đồng nghĩa bỏ qua filter | Không thể tìm các hàng có cột null | Biểu diễn explicit-null filter và dùng `isNull()` |
| Cập nhật cả entity khi chỉ cần một field | Tốn thao tác và có thể ghi đè dữ liệu khác | Dùng `Update` cho partial update |
| Không kiểm tra số hàng update/delete | Không biết hàng có tồn tại hoặc predicate có khớp | Xử lý `Mono<Long>` trả về |
| Cho rằng Update tự áp dụng optimistic locking | Có thể mất cập nhật khi nhiều transaction đồng thời | Đưa version vào predicate hoặc dùng cơ chế entity phù hợp |
| Nhầm tên property và tên cột vật lý | Criteria/Update có thể không ánh xạ như mong đợi | Kiểm tra `@Column`, naming strategy và SQL thực tế |
| Dùng API Criteria khác phiên bản | Lỗi compile hoặc hành vi không mong muốn | Đối chiếu Javadoc của Spring Data Relational đang dùng |

## 17. Quy trình xây dựng truy vấn động

Khi triển khai một endpoint tìm kiếm hoặc cập nhật, có thể đi theo trình tự:

1. **Xác định hợp đồng filter:** field nào tùy chọn, field nào cho phép explicit null, collection rỗng có nghĩa gì.
2. **Xác thực đầu vào:** giới hạn chuỗi, khoảng số/ngày, page size và thuộc tính sort.
3. **Xây dựng Criteria:** thêm từng predicate theo giá trị và trạng thái hiện diện của filter.
4. **Tạo Query:** thêm sort ổn định, limit và offset/cursor.
5. **Thực thi bằng template:** dùng `select`, `selectOne`, `count`, `update` hoặc `delete` phù hợp.
6. **Kiểm tra cardinality:** xử lý 0, 1 hoặc nhiều hàng theo hợp đồng nghiệp vụ.
7. **Quản lý transaction:** bao các thao tác cần tính nguyên tử trong reactive transaction.
8. **Kiểm thử SQL thực tế:** chạy trên database tương thích, bao gồm trường hợp filter rỗng và cập nhật đồng thời.

## 18. Nguyên tắc cần nhớ

- `Criteria` mô tả điều kiện lọc; `Query` kết hợp điều kiện với sort và giới hạn kết quả; `Update` mô tả các giá trị cần thay đổi.
- Dùng `R2dbcEntityTemplate` để thực thi các đối tượng Query/Criteria/Update trong mô hình Spring Data Relational.
- Thêm predicate theo trạng thái thực tế của filter và phân biệt field không gửi với explicit null.
- Kiểm soát truy vấn rỗng trước SELECT, UPDATE và DELETE.
- Giới hạn page size, dùng sort ổn định và cân nhắc keyset pagination cho dữ liệu lớn.
- Whitelist identifier động như sort property; bind các giá trị đầu vào.
- Xử lý collection rỗng trước khi dùng `IN`.
- Dùng `Update` cho partial update và kiểm tra số hàng bị ảnh hưởng.
- Không mặc định thao tác Update tùy chỉnh tự áp dụng optimistic locking; đưa version vào điều kiện nếu cần compare-and-set.
- Kiểm tra mapping tên thuộc tính/cột, `@Column` và naming strategy.
- Dùng transaction reactive khi nhiều thao tác phải nguyên tử và không gọi `block()` trong pipeline.
- Kiểm thử với database và driver mục tiêu để xác nhận SQL, mapping và hành vi đồng thời.

`Query`, `Criteria` và `Update` giúp xây dựng truy vấn động theo cách có cấu trúc trong Spring Data Relational R2DBC. Khi tách rõ điều kiện, tùy chọn truy vấn và assignment cập nhật, service có thể hỗ trợ nhiều tổ hợp filter mà vẫn dễ đọc. Việc xác thực filter rỗng, whitelist identifier, giới hạn phân trang và kiểm tra số hàng bị ảnh hưởng giúp các thao tác này an toàn và có thể dự đoán trong môi trường thực tế.
