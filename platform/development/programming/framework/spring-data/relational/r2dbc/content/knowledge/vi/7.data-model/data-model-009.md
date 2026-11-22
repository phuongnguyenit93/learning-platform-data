# Thiết kế mô hình phù hợp với mẫu truy vấn thực tế

Thiết kế mô hình dữ liệu cho một ứng dụng Spring Data R2DBC cần bắt đầu từ cách ứng dụng thực sự đọc và ghi dữ liệu. Một schema có thể chuẩn hóa rất tốt nhưng lại khiến các truy vấn quan trọng phải join nhiều bảng, đọc quá nhiều hàng hoặc thực hiện nhiều lượt round trip. Ngược lại, một schema được tối ưu cho một màn hình duy nhất có thể lặp dữ liệu quá mức và khiến việc cập nhật trở nên khó kiểm soát.

Mục tiêu là tìm được sự cân bằng giữa tính đúng đắn của dữ liệu, ranh giới aggregate, mẫu truy vấn, hiệu năng và khả năng bảo trì. Spring Data R2DBC cung cấp Repository, `R2dbcEntityTemplate` và `DatabaseClient` để truy cập dữ liệu; các API này không tự quyết định schema tối ưu thay cho ứng dụng. Lập trình viên cần hiểu các truy vấn quan trọng rồi thiết kế bảng, quan hệ, khóa và index để hỗ trợ chúng.

## 1. Bắt đầu từ access pattern thay vì bắt đầu từ entity

Một cách thiết kế thường gặp là liệt kê danh từ trong yêu cầu nghiệp vụ rồi tạo mỗi danh từ thành một entity. Cách này giúp nhận diện khái niệm miền, nhưng chưa cho biết ứng dụng cần truy cập dữ liệu như thế nào. Trước khi quyết định cấu trúc bảng, hãy liệt kê các thao tác đọc và ghi mà hệ thống phải phục vụ.

Ví dụ với một hệ thống bán hàng, các access pattern có thể gồm:

| Mã | Nhu cầu | Điều kiện truy vấn | Dữ liệu cần trả về |
|---|---|---|---|
| Q1 | Xem danh sách đơn hàng của khách | `customer_id`, trạng thái, khoảng thời gian | Mã đơn, ngày tạo, trạng thái, tổng tiền |
| Q2 | Xem chi tiết một đơn hàng | `order_id` | Thông tin đơn, khách hàng và các dòng hàng |
| Q3 | Tìm đơn hàng cần xử lý | Trạng thái, thời điểm tạo | Các đơn đang chờ, sắp xếp theo thời gian |
| Q4 | Xem lịch sử mua của một sản phẩm | `product_id`, khoảng thời gian | Các đơn có chứa sản phẩm đó |
| Q5 | Báo cáo doanh thu theo ngày | Khoảng thời gian, trạng thái hợp lệ | Ngày, số đơn, tổng doanh thu |
| W1 | Tạo đơn hàng | Khách hàng và danh sách sản phẩm | Đơn hàng và các dòng hàng được lưu nhất quán |
| W2 | Đổi trạng thái đơn | `order_id`, trạng thái mới | Trạng thái mới và thời điểm cập nhật |

Với mỗi access pattern, hãy ghi nhận thêm:

- Tần suất gọi: liên tục, theo giờ, theo ngày hay chỉ khi quản trị viên thao tác.
- Số lượng dữ liệu dự kiến: một hàng, vài chục hàng hay hàng nghìn hàng.
- Độ trễ mong muốn và mức tải đồng thời.
- Những trường nào bắt buộc phải có trong kết quả.
- Dữ liệu có cần nhất quán ngay lập tức hay có thể cập nhật trễ.
- Truy vấn có cần phân trang, sắp xếp hoặc lọc tùy chọn hay không.

Các thông tin này giúp phân biệt truy vấn trọng yếu với truy vấn hiếm gặp. Một truy vấn được gọi hàng nghìn lần mỗi phút có thể cần index hoặc read model riêng; một báo cáo chạy một lần mỗi ngày có thể chấp nhận kế hoạch truy vấn khác.

## 2. Phân biệt mô hình miền, aggregate và mô hình truy vấn

Ba khái niệm có liên quan nhưng không đồng nhất:

**Mô hình miền (domain model)** mô tả các khái niệm và quy tắc nghiệp vụ, ví dụ khách hàng, đơn hàng, sản phẩm và thanh toán.

**Aggregate** là ranh giới nhất quán mà ứng dụng quản lý như một đơn vị trong nghiệp vụ. Aggregate root là điểm vào để thay đổi trạng thái của aggregate. Trong ví dụ bán hàng, `PurchaseOrder` có thể là aggregate root quản lý các dòng hàng của chính đơn hàng đó. `Customer` và `Product` thường là aggregate độc lập; đơn hàng giữ định danh khách hàng và sản phẩm thay vì kéo toàn bộ object graph vào cùng một aggregate.

**Mô hình truy vấn (read model)** biểu diễn dữ liệu theo hình dạng mà một màn hình, API hoặc báo cáo cần. Một read model có thể kết hợp các trường từ nhiều bảng, tính sẵn một số giá trị hoặc chỉ chứa một phần dữ liệu. Nó không nhất thiết phải là entity có thể ghi ngược trở lại.

Trong Spring Data R2DBC, thiết kế aggregate có ý nghĩa vì Spring Data Relational ánh xạ dữ liệu theo aggregate. R2DBC không cung cấp persistence context và dirty checking như JPA/Hibernate. Ứng dụng cần thực hiện rõ các thao tác đọc và ghi; không nên kỳ vọng thay đổi một thuộc tính trong object graph sẽ tự được phát hiện và đồng bộ như một ORM truyền thống.

Một ranh giới aggregate hợp lý thường có các đặc điểm:

- Các đối tượng bên trong cần được thay đổi cùng nhau để giữ một quy tắc nghiệp vụ.
- Aggregate có một định danh và một điểm vào rõ ràng.
- Aggregate không quá lớn đến mức mọi thao tác cập nhật đều phải tải nhiều dữ liệu không cần thiết.
- Các aggregate khác được tham chiếu qua ID hoặc khóa nghiệp vụ ổn định.
- Quy tắc cập nhật qua nhiều aggregate được điều phối rõ ràng ở tầng Service hoặc quy trình nghiệp vụ.

Không nên biến mọi quan hệ khóa ngoại thành quan hệ object lồng nhau. Khóa ngoại trong database thể hiện tính toàn vẹn tham chiếu; ranh giới aggregate thể hiện cách ứng dụng bảo vệ tính nhất quán nghiệp vụ. Hai khái niệm này có thể liên quan nhưng không bắt buộc trùng nhau.

## 3. Chuẩn hóa dữ liệu và lựa chọn mức độ lặp dữ liệu

Chuẩn hóa giúp giảm dữ liệu trùng lặp và tránh các bất thường khi thêm, sửa hoặc xóa dữ liệu. Ví dụ, nếu tên khách hàng được lưu lặp trong mọi đơn hàng, việc khách hàng đổi tên có thể buộc ứng dụng cập nhật nhiều hàng. Lưu `customer_id` trong bảng đơn hàng và giữ thông tin khách hàng trong bảng riêng giúp quản lý dữ liệu gốc rõ ràng hơn.

Một schema quan hệ cơ bản có thể gồm:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL,
    current_price NUMERIC(19, 2) NOT NULL
        CHECK (current_price >= 0)
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_no VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(19, 2) NOT NULL CHECK (line_total >= 0)
);
```

Đây là ví dụ theo cú pháp PostgreSQL; kiểu identity và kiểu thời gian có thể cần điều chỉnh cho hệ quản trị khác. Các constraint ở database bảo vệ dữ liệu ngay cả khi có nhiều luồng ứng dụng hoặc công cụ khác cùng ghi.

### Khi nào nên giữ dữ liệu chuẩn hóa?

Nên giữ dữ liệu chuẩn hóa khi:

- Dữ liệu là nguồn sự thật được cập nhật thường xuyên.
- Nhiều chức năng cần cùng một thông tin và cần nhìn thấy thay đổi mới nhất.
- Việc lặp dữ liệu sẽ làm phát sinh nhiều điểm phải đồng bộ.
- Quan hệ và ràng buộc nghiệp vụ cần được database bảo vệ.

Ví dụ, giá hiện tại của sản phẩm nên nằm ở bảng `product`. Tuy nhiên, đơn hàng đã xác nhận cần lưu `unit_price` tại thời điểm mua trong `order_line`. Nếu chỉ tham chiếu `product.current_price`, lịch sử đơn hàng sẽ thay đổi theo giá bán hiện tại, làm sai dữ liệu giao dịch. Đây là một bản chụp có chủ đích của giá tại thời điểm phát sinh đơn.

### Khi nào có thể lặp hoặc tính sẵn dữ liệu?

Có thể cân nhắc denormalization khi một access pattern quan trọng phải join nhiều bảng hoặc tính toán tốn kém, trong khi dữ liệu nguồn ít thay đổi hơn tần suất đọc. Ví dụ:

- Lưu `total_amount` trong đơn hàng để đọc danh sách đơn nhanh.
- Lưu số lượng đơn và tổng chi tiêu trên một bảng thống kê khách hàng.
- Tạo bảng tổng hợp doanh thu theo ngày cho dashboard.
- Duy trì read model chứa tên khách hàng và thông tin đơn hàng để phục vụ màn hình danh sách.

Mỗi trường lặp cần có quy tắc đồng bộ: cập nhật trong cùng transaction, cập nhật bất đồng bộ qua event, hoặc tái tạo định kỳ từ dữ liệu gốc. Cần xác định độ trễ tối đa chấp nhận được và cách sửa dữ liệu nếu một lần đồng bộ thất bại.

Không nên lặp dữ liệu chỉ vì một truy vấn có nhiều join. Trước hết hãy đo hiệu năng, kiểm tra index và execution plan. Denormalization làm tăng chi phí ghi, dung lượng lưu trữ và độ phức tạp khôi phục dữ liệu.

## 4. Thiết kế bảng theo các thao tác đọc và ghi

Mỗi bảng nên có trách nhiệm rõ ràng và hỗ trợ những thao tác cụ thể. Với ví dụ đơn hàng:

| Bảng | Dữ liệu chính | Access pattern quan trọng |
|---|---|---|
| `customer` | Thông tin khách hàng | Tra khách theo ID, email |
| `product` | SKU, tên và giá hiện tại | Tra sản phẩm theo ID hoặc SKU |
| `purchase_order` | Trạng thái, khách hàng, thời điểm tạo, tổng tiền | Danh sách đơn, hàng chờ xử lý, báo cáo |
| `order_line` | Sản phẩm, số lượng, giá tại thời điểm mua | Chi tiết đơn, lịch sử bán sản phẩm |

Một số nguyên tắc hữu ích:

- Mỗi bảng có primary key ổn định. Khóa kỹ thuật như ID thường thuận tiện cho tham chiếu và phân trang.
- Đặt `NOT NULL`, `UNIQUE`, `CHECK` và foreign key tại database cho các bất biến dữ liệu phù hợp.
- Dùng kiểu dữ liệu thể hiện đúng miền giá trị: `NUMERIC` cho tiền, kiểu ngày giờ phù hợp cho thời điểm, cột có giới hạn độ dài cho mã và trạng thái.
- Không lưu tiền bằng `FLOAT` hoặc `DOUBLE` nếu cần tính toán chính xác.
- Chọn cách lưu thời gian có quy ước múi giờ rõ ràng. Với hệ thống đa múi giờ, thường lưu thời điểm theo UTC hoặc kiểu tương đương có offset và chuyển đổi khi hiển thị.
- Tránh tạo một bảng quá rộng chứa nhiều cột ít dùng nếu phần lớn truy vấn chỉ cần một nhóm nhỏ; cân nhắc tách dữ liệu lớn hoặc ít truy cập khi có lợi ích đo được.
- Đặt tên bảng và cột nhất quán để mapping và SQL dễ đọc.

Không phải mọi bảng đều cần một repository công khai cho tầng Service. Một bảng con có thể được quản lý thông qua aggregate root; một bảng phục vụ báo cáo có thể chỉ được đọc qua query chuyên biệt.

## 5. Thiết kế index từ điều kiện lọc và thứ tự sắp xếp

Index hỗ trợ database tìm hàng nhanh hơn, nhưng mỗi index cũng chiếm dung lượng và làm tăng chi phí insert, update, delete. Vì vậy, index cần xuất phát từ truy vấn thực tế.

Giả sử Q1 thường xuyên lấy đơn hàng theo khách hàng, trạng thái và khoảng thời gian, sắp xếp mới nhất trước:

```sql
SELECT id, order_no, status, created_at, total_amount
FROM purchase_order
WHERE customer_id = :customerId
  AND status = :status
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Một index có thể được thử nghiệm cho mẫu truy vấn này:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at DESC, id DESC);
```

Các cột bằng điều kiện thường được đặt trước cột dùng cho range và sắp xếp. `id` là khóa phụ để thứ tự ổn định khi nhiều đơn có cùng `created_at`. Tuy nhiên, thứ tự index tốt nhất còn phụ thuộc vào độ chọn lọc của dữ liệu, các truy vấn khác, database engine và execution plan.

Nếu trạng thái là điều kiện tùy chọn và có nhiều truy vấn chỉ lọc theo `customer_id`, index có `status` ở vị trí thứ hai có thể không hỗ trợ truy vấn đó hiệu quả như mong muốn. Có thể cần index riêng, hoặc thiết kế query theo cách khác. Không nên tạo index cho mọi tổ hợp filter có thể có; hãy ưu tiên những mẫu truy vấn có tần suất và chi phí cao.

### Index cho khóa ngoại

Primary key thường được database tự tạo index, nhưng index trên cột foreign key không phải lúc nào cũng tự động xuất hiện. Ví dụ, `order_line.order_id` thường được dùng để tải các dòng hàng của một đơn, vì vậy có thể cần:

```sql
CREATE INDEX idx_order_line_order_id
    ON order_line (order_id);

CREATE INDEX idx_order_line_product_id
    ON order_line (product_id);
```

Index `product_id` hỗ trợ Q4 khi tìm các đơn chứa một sản phẩm. Nếu truy vấn thường lọc theo `product_id` rồi sắp xếp theo đơn hoặc thời điểm, có thể cần index ghép sau khi kiểm tra execution plan.

### Kiểm tra execution plan

Với PostgreSQL, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn đại diện trong môi trường phù hợp để xem database sử dụng index nào, đọc bao nhiêu hàng và tốn bao nhiêu thời gian. `ANALYZE` thực sự thực thi câu SQL, vì vậy cần cẩn thận với câu lệnh ghi và dữ liệu production.

Không nên đánh giá index chỉ bằng việc truy vấn có trả kết quả nhanh trên vài chục hàng local. Cần dùng dữ liệu có quy mô và phân bố gần thực tế, đồng thời quan sát tác động lên workload ghi.

## 6. Thiết kế phân trang và thứ tự ổn định

Danh sách đơn hàng có thể tăng lên hàng triệu bản ghi. Không nên tải tất cả rồi lọc trong Java. Hãy để database lọc, sắp xếp và giới hạn số hàng trả về.

### Offset pagination

Một truy vấn đơn giản dùng `LIMIT` và `OFFSET`:

```sql
SELECT id, order_no, status, created_at
FROM purchase_order
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
```

Offset pagination dễ triển khai và phù hợp khi người dùng cần nhảy đến trang bất kỳ trên tập dữ liệu vừa phải. Tuy nhiên, offset càng lớn thì database có thể phải duyệt và bỏ qua nhiều hàng. Khi dữ liệu thay đổi giữa hai lần gọi, bản ghi có thể xuất hiện lặp hoặc bị bỏ qua giữa các trang.

### Keyset pagination

Với danh sách lớn, có thể dùng keyset pagination. Request tiếp theo gửi cursor gồm giá trị của các cột sắp xếp cuối cùng ở trang trước:

```sql
SELECT id, order_no, status, created_at
FROM purchase_order
WHERE customer_id = :customerId
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

Điều kiện cursor cần khớp với thứ tự `ORDER BY`. Nếu chỉ dùng `created_at` mà nhiều hàng có cùng thời điểm, trang tiếp theo có thể bỏ sót hoặc lặp hàng. Thêm `id` làm tie-breaker tạo thứ tự toàn phần ổn định.

Keyset pagination hiệu quả khi có index phù hợp với filter và thứ tự. Đổi lại, nó phù hợp với điều hướng tiếp/lùi theo cursor hơn là nhảy trực tiếp tới một số trang bất kỳ.

## 7. Thiết kế read model cho truy vấn kết hợp nhiều bảng

Một màn hình danh sách thường không cần toàn bộ entity. Ví dụ, màn hình lịch sử mua hàng cần mã đơn, tên khách hàng, trạng thái và tổng tiền. Việc tải từng `PurchaseOrder`, sau đó gọi thêm repository để lấy khách hàng có thể tạo ra N+1 query: một truy vấn lấy danh sách và thêm một truy vấn cho mỗi đơn.

Có thể dùng một truy vấn join và ánh xạ trực tiếp thành projection:

```sql
SELECT o.id,
       o.order_no,
       o.status,
       o.created_at,
       o.total_amount,
       c.display_name AS customer_name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE o.customer_id = :customerId
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit;
```

Read model có thể là DTO riêng:

```java
public record OrderSummary(
    Long id,
    String orderNo,
    String status,
    OffsetDateTime createdAt,
    BigDecimal totalAmount,
    String customerName
) {}
```

Với truy vấn join và projection tùy chỉnh, `DatabaseClient` cho phép kiểm soát SQL và ánh xạ kết quả:

```java
public Flux<OrderSummary> findOrderSummaries(Long customerId, int limit) {
    return databaseClient.sql("""
            SELECT o.id,
                   o.order_no,
                   o.status,
                   o.created_at,
                   o.total_amount,
                   c.display_name AS customer_name
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.customer_id = :customerId
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit
            """)
        .bind("customerId", customerId)
        .bind("limit", limit)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("created_at", OffsetDateTime.class),
            row.get("total_amount", BigDecimal.class),
            row.get("customer_name", String.class)
        ))
        .all();
}
```

Đoạn code minh họa mapping cho PostgreSQL và kiểu `TIMESTAMP WITH TIME ZONE`; kiểu Java thực tế cần phù hợp với driver và cấu hình mapping đang dùng. Khi driver trả kiểu thời gian khác, hãy điều chỉnh DTO hoặc converter tương ứng.

Read model chỉ chứa dữ liệu cần cho use case. Nó không nhất thiết phải được lưu thành bảng riêng; có thể là DTO tạo ra từ một câu SQL. Nếu query join quá đắt và được gọi rất thường xuyên, mới cân nhắc lưu read model vật lý hoặc bảng tổng hợp.

## 8. Chọn Repository, R2dbcEntityTemplate hay DatabaseClient

Spring Data R2DBC cung cấp nhiều mức abstraction. Chọn API theo hình dạng truy vấn:

| Nhu cầu | API phù hợp | Lý do |
|---|---|---|
| CRUD và truy vấn theo thuộc tính entity | `ReactiveCrudRepository` hoặc Repository mở rộng | Tên method diễn tả rõ access pattern, ít code lặp |
| Truy vấn entity với điều kiện được xây dựng động | `R2dbcEntityTemplate` | Dùng mapping metadata và API query của Spring Data |
| Join nhiều bảng, projection riêng, SQL tối ưu theo database | `DatabaseClient` | Kiểm soát câu SQL, bind parameter và mapping kết quả |
| Tích hợp cấp thấp với driver | R2DBC SPI | Dùng khi abstraction cấp cao không đáp ứng yêu cầu cụ thể |

Ví dụ Repository cho thao tác đơn giản:

```java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerIdAndStatusOrderByCreatedAtDesc(
        Long customerId,
        String status
    );
}
```

Tên method có thể diễn đạt truy vấn cơ bản, nhưng khi cần nhiều filter tùy chọn, cursor phức tạp hoặc projection join, một query chuyên biệt thường dễ đọc và kiểm soát hơn. Không nên ép mọi access pattern vào tên method dài.

`R2dbcEntityTemplate` hữu ích cho query entity linh hoạt:

```java
public Flux<PurchaseOrder> findOrders(Long customerId, String status) {
    Criteria criteria = Criteria.where("customerId").is(customerId)
        .and("status").is(status);

    return template.select(PurchaseOrder.class)
        .matching(Query.query(criteria)
            .sort(Sort.by(Sort.Order.desc("createdAt"))))
        .all();
}
```

Ví dụ này dùng tên thuộc tính entity trong Criteria. Khi cần SQL join hoặc projection không tương ứng với một entity, `DatabaseClient` thường là lựa chọn rõ ràng hơn.

## 9. Truy vấn động an toàn

Một màn hình tìm kiếm có thể cho phép lọc theo khách hàng, trạng thái, khoảng ngày và từ khóa. Không nên ghép trực tiếp giá trị người dùng vào chuỗi SQL:

```java
// Không an toàn: không ghép dữ liệu đầu vào trực tiếp vào SQL.
String sql = "SELECT * FROM purchase_order WHERE order_no = '" + orderNo + "'";
```

Hãy dùng bind parameter cho giá trị:

```java
databaseClient.sql("SELECT id, order_no FROM purchase_order WHERE order_no = :orderNo")
    .bind("orderNo", orderNo)
    .map((row, metadata) -> new OrderKey(
        row.get("id", Long.class),
        row.get("order_no", String.class)
    ))
    .one();
```

Bind parameter dùng cho giá trị, không dùng để thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu người dùng có thể chọn cột sắp xếp, hãy ánh xạ lựa chọn đó qua một allow-list trong code:

```java
String sortColumn = switch (sortBy) {
    case "createdAt" -> "created_at";
    case "totalAmount" -> "total_amount";
    default -> "id";
};
```

Sau đó chỉ đưa tên cột đã được kiểm soát vào phần SQL động, còn mọi giá trị lọc vẫn phải bind. Với nhiều điều kiện tùy chọn, có thể xây dựng SQL theo các nhánh đã xác định trước hoặc dùng API Criteria của `R2dbcEntityTemplate` khi truy vấn thao tác trên entity.

## 10. Ghi aggregate nhất quán

Một đơn hàng mới thường gồm bản ghi đơn và nhiều dòng hàng. Đây là một thao tác ghi cần bảo đảm tính nguyên tử: nếu một dòng hàng không thể lưu, đơn hàng không nên ở trạng thái chỉ được tạo một phần.

Một service có thể điều phối các repository trong transaction reactive:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;
    private final OrderLineRepository lines;

    public OrderCommandService(
            PurchaseOrderRepository orders,
            OrderLineRepository lines) {
        this.orders = orders;
        this.lines = lines;
    }

    @Transactional
    public Mono<PurchaseOrder> create(CreateOrder command) {
        PurchaseOrder order = new PurchaseOrder(
            null,
            command.customerId(),
            command.orderNo(),
            "PENDING",
            Instant.now(),
            command.totalAmount()
        );

        return orders.save(order)
            .flatMap(saved -> Flux.fromIterable(command.lines())
                .map(line -> new OrderLine(
                    null,
                    saved.id(),
                    line.productId(),
                    line.quantity(),
                    line.unitPrice(),
                    line.lineTotal()
                ))
                .concatMap(lines::save)
                .then(Mono.just(saved)));
    }
}
```

Đây là ví dụ minh họa luồng điều phối; các record `CreateOrder`, `OrderLine` và repository cần được định nghĩa theo schema thực tế. Trong code thực tế, không cần inject transaction manager nếu Spring đã cấu hình `@Transactional` với reactive transaction manager phù hợp. Tránh gọi `subscribe()` bên trong service; hãy trả publisher để Spring quản lý transaction theo subscription.

Nếu cần kiểm tra tồn kho hoặc giá hiện tại trước khi ghi, hãy xác định các quy tắc đó thuộc cùng transaction hay cần một quy trình riêng. Không nên giữ transaction database mở trong lúc chờ một dịch vụ HTTP bên ngoài lâu hơn cần thiết.

## 11. Thiết kế truy vấn báo cáo và dữ liệu tổng hợp

Truy vấn báo cáo thường khác truy vấn giao dịch. Ví dụ Q5 tổng hợp doanh thu theo ngày:

```sql
SELECT CAST(created_at AS DATE) AS order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM purchase_order
WHERE status IN ('PAID', 'COMPLETED')
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day;
```

Với lượng dữ liệu vừa phải, database có thể tính trực tiếp từ bảng giao dịch. Khi báo cáo quét lượng dữ liệu lớn và chạy thường xuyên, có thể cân nhắc:

- Bảng tổng hợp theo ngày hoặc theo tháng.
- Materialized view nếu database hỗ trợ và độ trễ refresh chấp nhận được.
- Read model được cập nhật bất đồng bộ từ sự kiện nghiệp vụ.
- Hệ thống phân tích riêng nếu workload báo cáo ảnh hưởng đến giao dịch.

Khi dùng dữ liệu tổng hợp, cần ghi rõ định nghĩa chỉ số. Ví dụ, doanh thu tính theo thời điểm tạo đơn, thanh toán hay hoàn tất? Đơn bị hoàn tiền có bị trừ không? Các quy tắc nghiệp vụ phải nhất quán giữa dữ liệu giao dịch và báo cáo.

## 12. Tránh N+1 query và tải dữ liệu quá mức

N+1 query xảy ra khi ứng dụng lấy danh sách N bản ghi rồi thực hiện thêm một truy vấn cho từng bản ghi để lấy dữ liệu liên quan. Ví dụ, lấy 100 đơn hàng và gọi `customerRepository.findById()` 100 lần để hiển thị tên khách hàng.

Có thể xử lý bằng cách:

- Viết một truy vấn join để lấy projection cần thiết.
- Lấy danh sách ID rồi truy vấn theo tập ID bằng một câu SQL phù hợp.
- Thiết kế read model cho màn hình thường xuyên được sử dụng.
- Chỉ tải các cột cần thiết thay vì `SELECT *`.
- Phân trang và giới hạn số hàng ngay tại database.

Không nên tải toàn bộ aggregate chỉ để hiển thị vài trường. Với chi tiết đơn hàng, có thể tải root và các dòng hàng theo hai truy vấn có chủ đích. Với danh sách đơn hàng, một projection join có thể hiệu quả hơn việc tạo object graph đầy đủ.

Spring Data R2DBC không có lazy loading kiểu JPA. Việc tải dữ liệu liên quan cần được thể hiện rõ bằng query hoặc API mapping phù hợp. Điều này giúp số lần truy cập database có thể dự đoán và kiểm soát.

## 13. Chọn chiến lược quan hệ giữa các bảng

Quan hệ trong schema cần phản ánh cả quy tắc dữ liệu và cách truy vấn:

**One-to-one:** chỉ dùng khi hai phần dữ liệu có vòng đời hoặc quyền truy cập khác nhau đủ rõ để tách bảng. Nếu luôn được đọc và ghi cùng nhau, một bảng có thể đơn giản hơn.

**One-to-many:** ví dụ một đơn hàng có nhiều dòng hàng. Có thể dùng foreign key ở bảng con. Nếu các dòng hàng thuộc vòng đời của đơn hàng, ứng dụng có thể quản lý chúng qua aggregate root; nếu có nhu cầu truy vấn độc lập đáng kể, có thể xây dựng repository hoặc query riêng.

**Many-to-many:** thường cần bảng liên kết. Nếu quan hệ có thuộc tính riêng như số lượng, thời điểm thêm hoặc trạng thái, hãy mô hình hóa bảng liên kết thành entity riêng. Ví dụ `order_line` không chỉ nối đơn hàng và sản phẩm mà còn lưu số lượng và giá tại thời điểm mua.

**Reference giữa aggregate:** thường lưu ID của aggregate khác. Khi cần dữ liệu của aggregate đó, truy vấn rõ ràng theo access pattern. Cách này tránh tải và cập nhật một object graph lớn ngoài ranh giới nhất quán.

Foreign key có thể bảo vệ tính toàn vẹn tham chiếu. Tuy nhiên, việc chọn `ON DELETE CASCADE`, `RESTRICT` hay `SET NULL` cần theo vòng đời dữ liệu và yêu cầu audit. Không nên cascade xóa dữ liệu giao dịch chỉ vì một entity cha bị xóa khỏi ứng dụng.

## 14. Các yếu tố cần cân nhắc khi tối ưu schema

Khi một truy vấn chậm, hãy xem xét nhiều yếu tố trước khi đổi mô hình:

- **Selectivity:** điều kiện lọc có loại bỏ được phần lớn hàng hay không?
- **Index:** index có khớp với điều kiện lọc và thứ tự sắp xếp không?
- **Join:** các cột join có kiểu dữ liệu tương thích và index phù hợp không?
- **Projection:** truy vấn có đọc nhiều cột không cần thiết không?
- **Cardinality:** một join có làm nhân số hàng vượt dự kiến không?
- **Pagination:** có đang dùng offset rất lớn không?
- **Locking:** thao tác ghi có chờ khóa hoặc xung đột cập nhật không?
- **Round trip:** ứng dụng có phát sinh nhiều truy vấn nhỏ nối tiếp nhau không?
- **Pool:** truy vấn chậm do database hay do phải chờ connection?
- **Consistency:** có thể dùng read model hoặc dữ liệu tổng hợp với độ trễ chấp nhận được không?

Chỉ thay đổi schema sau khi có bằng chứng từ truy vấn đại diện, execution plan, metrics hoặc profile. Một index mới có thể cải thiện truy vấn đọc nhưng làm chậm ghi; một bảng tổng hợp có thể giảm tải đọc nhưng tăng công việc đồng bộ.

## 15. Quy trình thiết kế mô hình theo truy vấn thực tế

Có thể áp dụng quy trình sau cho từng bounded context hoặc nhóm chức năng:

**Bước 1 — Liệt kê access pattern.** Ghi lại mọi thao tác đọc và ghi quan trọng, điều kiện lọc, thứ tự, projection, tần suất và số lượng dữ liệu.

**Bước 2 — Xác định quy tắc nghiệp vụ.** Tìm các bất biến cần được bảo vệ cùng nhau và xác định aggregate root. Phân biệt reference giữa aggregate với quan hệ object trong code.

**Bước 3 — Phác thảo schema chuẩn hóa.** Chọn bảng, primary key, foreign key, unique constraint, check constraint và kiểu dữ liệu đúng miền giá trị.

**Bước 4 — Viết SQL đại diện.** Viết truy vấn cho các access pattern quan trọng trước khi tối ưu index. Xác định rõ cột được lọc, join, sắp xếp và trả về.

**Bước 5 — Thiết kế index.** Tạo index theo workload thực tế, cân nhắc index ghép, index khóa ngoại và chi phí ghi.

**Bước 6 — Chọn read model.** Dùng entity cho thao tác aggregate, DTO/projection cho màn hình và báo cáo. Chỉ denormalize khi có lý do đo được và quy tắc đồng bộ rõ ràng.

**Bước 7 — Chọn API R2DBC.** Dùng Repository cho CRUD và truy vấn ổn định, `R2dbcEntityTemplate` cho query entity linh hoạt, `DatabaseClient` cho join và SQL tùy chỉnh.

**Bước 8 — Kiểm tra tải và tính nhất quán.** Dùng dữ liệu gần thực tế để kiểm tra execution plan, latency, transaction, concurrent write và hành vi phân trang.

**Bước 9 — Theo dõi sau triển khai.** Quan sát truy vấn chậm, pool, lỗi timeout và thay đổi phân bố dữ liệu. Điều chỉnh schema khi workload thực tế thay đổi.

## 16. Kết luận

Mô hình dữ liệu tốt cần phục vụ được cả quy tắc nghiệp vụ lẫn những truy vấn mà ứng dụng phải thực hiện. Hãy bắt đầu từ access pattern, xác định aggregate để bảo vệ tính nhất quán, chuẩn hóa dữ liệu gốc và thiết kế index theo điều kiện lọc cùng thứ tự sắp xếp. Với truy vấn kết hợp nhiều bảng, hãy dùng projection hoặc read model phù hợp; chỉ lặp dữ liệu khi có lý do hiệu năng và chiến lược đồng bộ rõ ràng.

Trong Spring Data R2DBC, Repository phù hợp với thao tác aggregate quen thuộc, `R2dbcEntityTemplate` hỗ trợ query entity linh hoạt và `DatabaseClient` phù hợp với SQL join hoặc projection chuyên biệt. Việc chọn đúng abstraction cùng schema dựa trên truy vấn thực tế giúp số lần truy cập database dễ dự đoán, dữ liệu giữ được tính nhất quán và hiệu năng có cơ sở để đo lường, cải thiện.
