# FluentCassandraOperations và chọn thao tác theo kiểu entity

## Mục tiêu học tập

Khi làm việc với **Spring Data Cassandra**, lập trình viên thường bắt đầu bằng `CassandraRepository` hoặc các phương thức trực tiếp của `CassandraTemplate` như `select`, `insert`, `update` và `delete`. Ngoài ra, Spring Data còn cung cấp phong cách **fluent operations**: bắt đầu từ **loại entity**, sau đó bổ sung điều kiện, dữ liệu hoặc tùy chọn cho thao tác.

Bài học thuộc chương **CassandraTemplate** của module `SPRING_DATA_CASSANDRA`. Trọng tâm không chỉ là cú pháp gọi method, mà là trả lời câu hỏi quan trọng: **khi một ứng dụng có nhiều entity và nhiều bảng được thiết kế theo truy vấn, nên bắt đầu fluent operation bằng kiểu nào và hệ quả của lựa chọn đó là gì?**

Sau bài này, bạn có thể:

- Giải thích vai trò của `FluentCassandraOperations` và mối liên hệ với `CassandraTemplate`.
- Hiểu bước `query(Entity.class)`, `insert(Entity.class)`, `update(Entity.class)` hoặc `delete(Entity.class)` thiết lập **ngữ cảnh mapping** cho thao tác.
- Phân biệt **domain/entity type**, **kiểu kết quả hoặc projection**, **bảng CQL** và **kiểu dữ liệu của tham số**.
- Viết truy vấn fluent có điều kiện khóa phân vùng rõ ràng; nhận diện khi nào các kiểu entity khác nhau phải tương ứng các bảng khác nhau.
- Xem xét ghi, cập nhật, xóa, paging, consistency và mapping khi dùng fluent API thay vì repository.
- Tránh lỗi chọn sai entity, thiếu khóa, lẫn lộn cập nhật một phần với lưu toàn bộ entity, hoặc mong đợi fluent API hỗ trợ truy vấn kiểu quan hệ.

## 1. FluentCassandraOperations là gì?

`FluentCassandraOperations` là giao diện API ở tầng **Spring Data Cassandra** mô tả cách xây dựng một thao tác truy cập dữ liệu từng bước. Cách sử dụng thường bắt đầu bằng một thao tác và một kiểu Java:

```text
FluentCassandraOperations
    .query(Entity.class)
       -> khai báo điều kiện -> thực thi đọc

    .insert(Entity.class)
       -> cung cấp entity -> thực thi ghi

    .update(Entity.class)
       -> chọn dữ liệu / điều kiện -> thực thi cập nhật

    .delete(Entity.class)
       -> khai báo điều kiện -> thực thi xóa
```

**`CassandraTemplate`** là thành phần cung cấp thao tác dữ liệu trong ứng dụng Spring Data Cassandra và, ở các phiên bản hỗ trợ fluent API, có thể được dùng qua giao diện `FluentCassandraOperations`. Trên thực tế, các API fluent được xây dựng để phối hợp với mapping metadata, conversions và cơ chế thực thi CQL của Spring Data.

Khác với việc tự ghép CQL từ chuỗi, fluent API giúp làm rõ **đối tượng truy cập** và các bước tạo query. Nhưng điều đó **không làm thay đổi giới hạn của Apache Cassandra**: `WHERE` vẫn phải phù hợp partition key và clustering columns, không tự có `JOIN`, không tự phân phối một truy vấn chưa xác định partition một cách miễn phí.

### Đối chiếu ba phong cách

| Cách truy cập | Ví dụ về ý định | Đặc điểm |
| --- | --- | --- |
| **Repository** | `repository.findById(id)` | Ít boilerplate, phù hợp đường truy cập phổ biến được đóng gói thành interface. |
| **CassandraTemplate trực tiếp** | `template.select(query, Entity.class)` | Thể hiện thao tác và query trong một lệnh gọi rõ ràng. |
| **FluentCassandraOperations** | `template.query(Entity.class).matching(query).all()` | Dễ đọc như một chuỗi bước; khởi đầu bằng entity type và tinh chỉnh trước khi thực thi. |
| **Java Driver/CQL trực tiếp** | `session.execute(boundStatement)` | Kiểm soát CQL/driver chi tiết hơn, đổi lại cần tự quản lý câu lệnh và mapping khi không dùng Spring Data. |

Không có lựa chọn nào **luôn nhanh hơn** các lựa chọn khác. Hiệu năng phụ thuộc chủ yếu vào câu CQL thực tế, bảng, partition key, số hàng, kích thước dữ liệu, consistency level, driver và workload.

## 2. Vì sao phải chọn kiểu entity ngay đầu thao tác?

Trong một ứng dụng Cassandra, một thực thể nghiệp vụ có thể xuất hiện ở **nhiều bảng CQL**. Mỗi bảng phục vụ một cách đọc khác nhau:

- Bảng `orders_by_id` để tìm đơn theo `order_id`.
- Bảng `orders_by_customer_month` để liệt kê đơn theo `customer_id` và tháng.
- Bảng `order_lines_by_order` để lấy các dòng hàng theo `order_id`.

Mặc dù cùng liên quan đến “đơn hàng”, ba bảng có **partition key, clustering columns và cấu trúc hàng khác nhau**. Không nên tạo một entity duy nhất rồi mong Spring Data Cassandra tự thực hiện `JOIN` giữa chúng.

Khi gọi:

```java
template.query(OrderByCustomerMonth.class)
```

bạn đang nói với Spring Data: **lấy metadata mapping của loại `OrderByCustomerMonth` làm ngữ cảnh cho truy vấn**. Nó bao gồm thông tin như:

1. Tên bảng từ `@Table` hoặc quy ước naming.
2. Cột nào tương ứng với các property Java.
3. Khóa chính được ánh xạ như thế nào.
4. Converter/custom conversions nào áp dụng khi materialize kết quả.

Lựa chọn một class khác có thể khiến query được xây cho **bảng khác, cột khác và kiểu kết quả khác**. Đó là lý do bước chọn entity type không phải một tham số trang trí.

### Phân biệt bốn loại “type”

| Loại | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Entity/domain type** | `OrderByCustomerMonth.class` | Xác định metadata bảng và ánh xạ đối tượng được thao tác. |
| **ID type** | `OrderSummaryKey` | Đại diện khóa chính của entity, thường dùng với repository. |
| **Result/projection type** | `OrderCard` | Cách ứng dụng muốn nhận dữ liệu hiển thị; có thể chỉ gồm vài cột. |
| **Parameter value type** | `UUID`, `LocalDate`, `String` | Kiểu Java được bind vào điều kiện CQL. |

**Chọn kiểu hiển thị không tương đương chọn bảng.** Một DTO không có mapping của bảng sẽ không tự thay thế entity ở vị trí bắt đầu fluent query. Nếu phiên bản API cho phép ánh xạ/projection kết quả, đó là bước riêng và cần được kiểm chứng đúng với API đang dùng.

## 3. Ví dụ xuyên suốt: danh sách đơn của khách hàng theo tháng

Giả sử một tenant có nhiều khách hàng, mỗi khách hàng có nhiều đơn. API cần hiển thị **20 đơn mới nhất của một khách trong một tháng**, rồi xem chi tiết một đơn cụ thể.

Để minh họa cách chọn entity, dùng hai bảng độc lập:

```sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    placed_at timestamp,
    order_status text,
    total_cents bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    order_month text,
    placed_at timestamp,
    order_id uuid,
    order_status text,
    total_cents bigint,
    PRIMARY KEY ((tenant_id, customer_id, order_month), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id ASC);
```

Các lựa chọn khóa là **một thiết kế minh họa**:

- Bảng `orders_by_id` phục vụ tìm theo tenant và order ID, mỗi cặp định danh một partition.
- Bảng `orders_by_customer_month` nhóm danh sách theo `(tenant_id, customer_id, order_month)`, rồi sắp `placed_at DESC` trong partition.
- `order_id` là clustering column thứ hai của bảng danh sách để phân biệt các đơn có cùng timestamp.
- Việc lưu trùng thông tin như `order_status` và `total_cents` là **denormalization theo truy vấn**; ứng dụng cần đồng bộ dữ liệu ở hai bảng.

### Hai mẫu truy vấn có đường đi khác nhau

Lấy chi tiết đơn:

```sql
SELECT *
FROM orders_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Lấy danh sách tháng:

```sql
SELECT placed_at, order_id, order_status, total_cents
FROM orders_by_customer_month
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND customer_id = 33333333-3333-4333-8333-333333333333
  AND order_month = '2026-11'
LIMIT 20;
```

Vì các request biết những khóa khác nhau, **không nên dùng một kiểu entity cho cả hai chỉ vì đều là đơn hàng**. Hãy ánh xạ mỗi bảng vào một entity phù hợp, rồi chọn đúng entity khi gọi fluent operations.

## 4. Ánh xạ entity theo từng bảng

### 4.1. Entity tìm đơn theo ID

Bảng `orders_by_id` có partition key tổng hợp gồm `tenant_id` và `order_id`. Spring Data có thể mô hình hóa bằng lớp khóa:

```java
import java.io.Serializable;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderByIdKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    // Constructor, getters/setters, equals/hashCode.
}
```

Entity:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey
    private OrderByIdKey key;

    @Column("customer_id")
    private UUID customerId;

    @Column("placed_at")
    private Instant placedAt;

    @Column("order_status")
    private String status;

    @Column("total_cents")
    private Long totalCents;

    // Constructor, getters/setters.
}
```

### 4.2. Entity cho danh sách khách/tháng

Bảng danh sách có **ba thành phần partition key** và **hai clustering columns**:

```java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderByCustomerMonthKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "customer_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "order_month", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private String orderMonth;

    @PrimaryKeyColumn(name = "placed_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID orderId;

    // Constructor, getters/setters, equals/hashCode.
}
```

```java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private OrderByCustomerMonthKey key;

    @Column("order_status")
    private String status;

    @Column("total_cents")
    private Long totalCents;

    // Constructor, getters/setters.
}
```

Đây là **các khung mapping phục vụ học tập**; cần bổ sung constructor và accessors phù hợp để biên dịch/khởi tạo entity trong dự án thật. Các tên bảng và khóa chính phải khớp schema CQL đang chạy.

Điểm quan trọng là entity `OrderById` và `OrderByCustomerMonth` không chỉ khác tên class; chúng có **identity và cách truy cập dữ liệu khác nhau**.

## 5. Fluent query: chọn entity trước, thêm điều kiện sau

Trong API có hỗ trợ fluent query, một mẫu sử dụng thường thấy là:

```java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.FluentCassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public final class OrderListReader {

    private final FluentCassandraOperations fluent;

    public OrderListReader(FluentCassandraOperations fluent) {
        this.fluent = fluent;
    }

    public List<OrderByCustomerMonth> latestInMonth(
            UUID tenantId, UUID customerId, String orderMonth) {

        Query query = Query.query(
                Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("order_month").is(orderMonth))
            .limit(20);

        return fluent.query(OrderByCustomerMonth.class)
                .matching(query)
                .all();
    }
}
```

**Đường đi của truy vấn**:

1. `OrderByCustomerMonth.class` xác định entity/bảng được truy vấn.
2. `Query` chứa các tiêu chí định vị partition `tenant_id`, `customer_id` và `order_month`.
3. `limit(20)` giới hạn số hàng được yêu cầu.
4. `matching(query)` đưa điều kiện vào chuỗi fluent.
5. `all()` là thao tác kết thúc, yêu cầu thực thi và trả về danh sách entity.

Lưu ý: các lớp và chữ ký method trong ví dụ mô tả **phong cách API phổ biến**; khi triển khai, kiểm tra module và phiên bản Spring Data Cassandra cụ thể để điều chỉnh imports, kiểu trả về và khả năng cấu hình query. Đây không phải hướng dẫn khẳng định mọi phiên bản đều có toàn bộ overload giống nhau.

### Vì sao query này hợp lý với Cassandra?

Trước khi nhìn vào Java, hãy đối chiếu:

```text
Partition key trong schema:
  (tenant_id, customer_id, order_month)

Điều kiện của API:
  tenant_id      = ?
  customer_id    = ?
  order_month    = ?

=> Có đủ partition key.
=> Trả các hàng trong một partition theo clustering order.
=> LIMIT 20 giới hạn kết quả mong muốn.
```

Fluent API không tự hoàn thiện khóa còn thiếu. Nếu bỏ `order_month`, ứng dụng không thể giả định query sẽ tự đọc toàn bộ các tháng hoặc nối kết quả theo thời gian. Muốn hiển thị danh sách xuyên tháng, cần truy vấn nhiều bucket hoặc một bảng phục vụ truy vấn khác.

### Query trực tiếp qua CassandraTemplate tương đương

Giữ nguyên `Query` ở ví dụ trên, có thể gọi phương thức template dạng truyền trực tiếp đối tượng query và class entity:

```java
List<OrderByCustomerMonth> rows =
        cassandraTemplate.select(query, OrderByCustomerMonth.class);
```

Từ góc nhìn truy cập Cassandra, lựa chọn fluent hay phương thức trực tiếp chỉ thay đổi **cách biểu đạt ở tầng Java**. Câu hỏi quan trọng vẫn là: **đúng bảng? đúng partition key? giới hạn và tải phù hợp?**

## 6. Chọn sai entity type gây những vấn đề gì?

Giả sử lập trình viên viết:

```java
// Sai ý định: đang cần danh sách đơn theo khách/tháng.
fluent.query(OrderById.class).matching(monthQuery).all();
```

Trong ví dụ, `OrderById.class` map tới `orders_by_id` với partition key `(tenant_id, order_id)`. `monthQuery` lại chứa `customer_id` và `order_month` để phục vụ `orders_by_customer_month`.

Hậu quả có thể gồm:

- CQL được tạo cho bảng không có cột được dùng trong điều kiện, dẫn đến lỗi “unknown column”.
- Điều kiện không chỉ rõ partition key của bảng đã chọn, khiến CQL không hợp lệ cho mô hình đó.
- Nếu tên cột vô tình trùng, truy vấn vẫn không diễn đạt đúng luồng nghiệp vụ.
- Việc đọc về sai kiểu entity có thể gặp lỗi mapping hoặc tạo đối tượng không đầy đủ.

**Thay `OrderByCustomerMonth.class` bằng `OrderById.class` không phải cách chuyển kết quả thành một DTO.** Đây là thay đổi ngữ cảnh bảng truy cập.

### Quy tắc chọn entity theo request

| Request | Những khóa request biết | Entity nên dùng | Bảng CQL |
| --- | --- | --- | --- |
| Xem đơn theo mã | `tenant_id` + `order_id` | `OrderById` | `orders_by_id` |
| 20 đơn của khách trong tháng | `tenant_id` + `customer_id` + `order_month` | `OrderByCustomerMonth` | `orders_by_customer_month` |
| Tất cả dòng hàng của một đơn | `tenant_id` + `order_id` | Entity riêng cho các dòng hàng | `order_lines_by_order` nếu được thiết kế |
| Tìm đơn theo trạng thái toàn tenant | `tenant_id` + `status` | Cần một cách nhìn/bảng phù hợp hoặc thiết kế khác | Không tự suy ra từ hai bảng hiện có |

Việc chọn class bắt đầu từ **mẫu truy vấn và schema**, không chỉ từ tên nghiệp vụ.

## 7. Kiểu entity và kiểu kết quả không phải một

Giao diện danh sách đơn thường chỉ cần `order_id`, `placed_at`, `order_status` và `total_cents`. Nó không cần đọc toàn bộ metadata của entity và không cần các dòng hàng.

Một DTO có thể được định nghĩa:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderCard(
        UUID orderId,
        Instant placedAt,
        String status,
        Long totalCents) {
}
```

Hãy phân biệt:

- **Entity nguồn** cho biết truy vấn phải đi đến bảng nào.
- **Projection/result type** quyết định ứng dụng muốn nhận dữ liệu theo cấu trúc nào, nếu API phiên bản đang dùng hỗ trợ mapping ấy.
- **Danh sách cột SELECT** quyết định lượng dữ liệu được yêu cầu từ Cassandra; có thể giúp giảm payload.

Một số phiên bản Spring Data cung cấp các tùy chọn fluent để định hình loại kết quả hoặc trường cần đọc, chẳng hạn các thao tác kiểu `as(...)` hoặc projection tương ứng. **Đừng mặc định `query(OrderCard.class)` là truy vấn đúng bảng `orders_by_customer_month`**, vì `OrderCard` ở đây không được khai báo là persistent entity có mapping CQL.

Nếu công cụ đang dùng không hỗ trợ projection mong muốn, có thể:

1. Query entity theo đúng bảng rồi ánh xạ sang DTO ở service.
2. Dùng truy vấn CQL chọn đúng cột, sau đó map kết quả theo API phù hợp.
3. Định nghĩa một entity riêng phù hợp với cấu trúc bảng khi đây là đường đọc chính.

**Chi phí đọc:** chỉ chuyển entity thành DTO *sau khi đã tải toàn bộ cột* không làm giảm network. Khi cần tối ưu, phải chọn đúng các cột ngay từ CQL hoặc cấu hình projection ở tầng truy vấn.

## 8. Fluent insert: chọn kiểu entity cần ghi

Ở chiều ghi, ý tưởng fluent là tương tự:

```text
insert(OrderByCustomerMonth.class)
    -> using(orderSummary)
    -> execute
```

Tùy phiên bản, tên các bước kết thúc và overload có thể khác nhau. Ví dụ minh họa cách gọi:

```java
// Mẫu fluent insert minh họa; kiểm tra API phiên bản thực tế.
fluent.insert(OrderByCustomerMonth.class)
        .using(orderSummary)
        .execute();
```

Trong đó `orderSummary` là instance của `OrderByCustomerMonth` đã có **đủ toàn bộ giá trị khóa chính**, gồm cả `tenant_id`, `customer_id`, `order_month`, `placed_at` và `order_id`.

Ở mức CQL, một câu ghi danh sách có thể là:

```sql
INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, order_month,
    placed_at, order_id, order_status, total_cents
) VALUES (
    11111111-1111-4111-8111-111111111111,
    33333333-3333-4333-8333-333333333333,
    '2026-11',
    '2026-11-25T10:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'CREATED',
    149900
);
```

Nhớ rằng:

- Chọn `OrderByCustomerMonth.class` cho biết bảng **danh sách** cần ghi.
- Ghi vào bảng danh sách **không tự tạo** hàng ở `orders_by_id`.
- Cần đường ghi nghiệp vụ để giữ hai cách nhìn nhất quán theo mục tiêu của ứng dụng.
- CQL `INSERT` có ngữ nghĩa upsert theo primary key; không giả định cứ gọi insert là sẽ từ chối khóa đã tồn tại.
- Các tùy chọn TTL hoặc timestamp, nếu cần, phải dùng đúng khả năng của API/driver phiên bản tương ứng và hiểu hậu quả đối với dữ liệu đã ghi.

### Đừng dùng sai class khi ghi cùng một đơn vào hai bảng

Một nghiệp vụ tạo đơn có thể cần:

```text
Tạo đơn hàng
    |
    +--> OrderById         -> orders_by_id
    |
    +--> OrderByCustomerMonth -> orders_by_customer_month
```

Hai entity **khác kiểu và khác khóa chính**, mặc dù cùng `order_id`. Một số trường có thể trùng nhau, nhưng không nên kỳ vọng chuyển một instance `OrderById` sang thao tác `insert(OrderByCustomerMonth.class)` là đủ để Spring Data tự biết cách đổi hình dạng của entity.

Service nên dựng từng entity từ một mô hình nghiệp vụ chung, với các quy tắc chính xác về tháng, thời gian tạo và trạng thái. Việc thử lại phải dùng **định danh ổn định** và cơ chế phát hiện/khôi phục ghi thiếu giữa hai bảng.

## 9. Fluent update: nên sửa toàn entity hay sửa đúng cột?

Khi thay đổi trạng thái từ `CREATED` sang `SHIPPED`, chỉ một số cột cần thay đổi. Vì thế cần phân biệt:

- **Lưu entity** bằng repository/template: framework có thể tạo thao tác ghi theo dữ liệu entity và cấu hình mapping.
- **Cập nhật từng cột bằng query + update definition**: chỉ chỉ định trường cần sửa và khóa xác định hàng.

Ý tưởng fluent update có dạng:

```text
update(OrderByCustomerMonth.class)
    -> matching(query có khóa cần thiết)
    -> apply(thay đổi order_status)
    -> thực thi
```

Một cách biểu diễn có thể gặp ở các API fluent tương thích:

```java
// Minh họa ý tưởng update theo điều kiện; kiểm tra chữ ký phiên bản.
fluent.update(OrderByCustomerMonth.class)
        .matching(fullPrimaryKeyQuery)
        .apply(Update.update("order_status", "SHIPPED"))
        .all();
```

Ví dụ CQL tương ứng:

```sql
UPDATE orders_by_customer_month
SET order_status = 'SHIPPED'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND customer_id = 33333333-3333-4333-8333-333333333333
  AND order_month = '2026-11'
  AND placed_at = '2026-11-25T10:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Để cập nhật chính xác **một hàng** trong bảng này, đã chỉ ra:

1. Toàn bộ partition key: `tenant_id`, `customer_id`, `order_month`.
2. Toàn bộ clustering key: `placed_at`, `order_id`.
3. Cột regular cần sửa: `order_status`.

Không đưa primary key vào phần `SET` để “đổi khóa” cho một hàng. Trong Cassandra, đổi partition key hoặc clustering key cần thiết kế việc **ghi ở khóa mới và xóa ở khóa cũ**.

### Vì sao cập nhật theo entity có thể nguy hiểm khi DTO thiếu field?

Nếu API chỉ gửi `orderId` và trạng thái mới, rồi dựng một entity với các regular columns khác bằng `null` và gọi `save()`, hành vi ghi cột `null` có thể không phù hợp ý định “chỉ đổi trạng thái”. Trong Cassandra, việc ghi giá trị `null` cho regular column có thể tạo tác dụng xóa/tombstone tùy thao tác.

Vì vậy, khi ứng dụng chỉ muốn sửa một cột:

- Dùng lệnh cập nhật mục tiêu hoặc API update có điều kiện rõ ràng.
- Cung cấp đầy đủ khóa để không tạo/xóa nhầm phạm vi dữ liệu.
- Kiểm tra hành vi `null`, ghi không có giá trị và TTL theo phiên bản đang dùng.
- Đừng nhầm việc “đã có entity class” với việc “mọi field của entity phải ghi lại mỗi lần”.

## 10. Fluent delete: khóa nào định danh bản ghi bị xóa?

Với fluent delete, ý tưởng tương tự:

```text
delete(OrderByCustomerMonth.class)
    -> matching(fullPrimaryKeyQuery)
    -> thực thi xóa
```

Ví dụ mô tả:

```java
// Minh họa fluent delete; API cụ thể có thể khác theo phiên bản.
fluent.delete(OrderByCustomerMonth.class)
        .matching(fullPrimaryKeyQuery)
        .all();
```

CQL tương ứng để xóa một hàng danh sách:

```sql
DELETE FROM orders_by_customer_month
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND customer_id = 33333333-3333-4333-8333-333333333333
  AND order_month = '2026-11'
  AND placed_at = '2026-11-25T10:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Nếu một lệnh CQL xóa **chỉ với partition key**, phạm vi tác động có thể là **toàn bộ partition**, không phải một hàng. Đó là điểm cần kiểm tra cẩn thận khi viết fluent delete theo `Query`.

### Không có cascade giữa các bảng

Xóa ở `orders_by_customer_month` không tự xóa ở `orders_by_id`; ngược lại cũng vậy. Nếu nghiệp vụ hủy hoặc xóa đơn:

1. Xác định những cách nhìn dữ liệu cần sửa/xóa.
2. Xác định khóa đầy đủ ở từng bảng.
3. Điều phối các thay đổi và xử lý khi một thao tác thất bại.
4. Cân nhắc **soft delete** hoặc trạng thái nghiệp vụ trước khi dọn dữ liệu vật lý.

Cassandra lưu dấu xóa (*tombstone*) để quản lý xóa phân tán. Xóa quá nhiều trên partition lớn có thể ảnh hưởng truy vấn đọc và compaction. Fluent API **không biến DELETE thành thao tác dọn dữ liệu miễn phí**.

## 11. Những trường hợp không nên dùng fluent API như một lớp che CQL

Fluent API có cú pháp dễ đọc, nhưng không làm các thao tác sau tự nhiên hợp lệ hoặc hiệu quả:

```sql
-- Bảng orders_by_customer_month định tuyến theo
-- (tenant_id, customer_id, order_month).

-- Không thể suy ra đây là truy vấn phù hợp chỉ vì order_id có giá trị:
-- SELECT * FROM orders_by_customer_month WHERE order_id = ...;

-- Không nên xóa theo một regular column tùy ý:
-- DELETE FROM orders_by_customer_month WHERE order_status = 'CANCELLED';

-- Không thể mặc định sắp xếp mọi đơn qua mọi tháng
-- bằng ORDER BY đặt trên toàn bộ bảng.
```

**`Criteria` trong Java không phải query planner của SQL.** Một điều kiện có cú pháp hợp lệ ở tầng Java vẫn có thể dẫn đến CQL không được Cassandra hỗ trợ vì thiếu partition key, điều kiện clustering không đúng thứ tự hoặc truy cập phạm vi không phù hợp.

Khi xây query:

| Câu hỏi | Cách tự kiểm tra |
| --- | --- |
| Đã chọn đúng `Entity.class` chưa? | Đối chiếu `@Table` với schema và request. |
| Điều kiện có **đủ partition key** không? | Đọc `PRIMARY KEY ((...))` của bảng CQL. |
| Có cần clustering columns để xác định một hàng? | Đặc biệt quan trọng với update/delete. |
| Có đang cố tìm theo regular column không? | Cân nhắc cách nhìn/bảng theo truy vấn hoặc cơ chế index phù hợp. |
| Kết quả có thể rất lớn không? | Thiết kế limit, page size, paging state và API trả dữ liệu. |
| Có cần dữ liệu từ hai bảng không? | Điều phối tại service; không mong fluent API tự JOIN. |

## 12. Paging và LIMIT trong fluent query

Một kết quả truy vấn 20 đơn trong một partition có thể đơn giản. Nhưng nếu UI cho cuộn lịch sử nhiều trang, ứng dụng phải phân biệt:

- **CQL `LIMIT`:** giới hạn số hàng trả về từ một câu truy vấn trong phạm vi điều kiện.
- **Driver page size:** cách driver nhận các trang kết quả từ Cassandra.
- **Paging state/cursor:** thông tin để tiếp tục lấy trang trong cùng kiểu truy vấn.
- **OFFSET:** khái niệm phổ biến ở SQL nhưng không phải giải pháp Cassandra để nhảy đến trang thứ 1.000.

Fluent API có thể cho phép truyền các tùy chọn phân trang thông qua `Query` hoặc cấu hình thực thi tương ứng, tùy phiên bản. Tuy nhiên, **khả năng paging không phụ thuộc vào việc bắt đầu bằng `query(Entity.class)`**.

Nếu danh sách đơn được chia theo `order_month`, một paging state của tháng 11 **không tự tiếp tục** sang tháng 10. Để hiển thị lịch sử xuyên tháng, service cần biết bucket nào sẽ truy cập tiếp, quản lý thứ tự và cursor hợp lý.

### Mẹo thiết kế API cho màn hình danh sách

Thay vì cung cấp `page=1000&size=20` như một API SQL truyền thống, có thể thiết kế theo cursor và key:

```text
GET /tenants/{tenantId}/customers/{customerId}/orders
    ?month=2026-11
    &pageSize=20
    &cursor=<opaque-token>
```

Cursor nên là token mờ đục đối với client, do server xây dựng và xác thực theo cấu trúc được phép. Không để client tự sửa paging state hoặc ghép input tùy ý thành CQL. Khi dữ liệu thay đổi giữa các trang, cần xác định cách xử lý trùng/lệch kết quả theo yêu cầu trải nghiệm; paging không tạo một snapshot bất biến.

## 13. Consistency level, timeout và prepared queries

Trong Cassandra, consistency level của một request ảnh hưởng số replica cần phản hồi theo replication và topology. Ví dụ `LOCAL_QUORUM` có ngữ nghĩa khác `ONE`, và lựa chọn tác động đến độ trễ/khả dụng.

Điều quan trọng với fluent operations:

1. **Không suy ra consistency từ tên phương thức.** `query(...).all()` hay `delete(...).all()` không nói thao tác đang chạy ở level nào.
2. Kiểm tra cấu hình driver/session và các tùy chọn query/statement được phiên bản Spring Data hỗ trợ.
3. Đặt timeout hợp lý; phân biệt query timeout, driver timeout và yêu cầu HTTP timeout.
4. Với request cần tối ưu, kiểm tra cách dùng prepared statements và bind parameters.
5. Khi định nghĩa retry, phải phân biệt thao tác ghi có thể lặp lại an toàn với thao tác counter, update điều kiện hoặc workflow có tác dụng phụ.

Ví dụ, khi cả `orders_by_id` và `orders_by_customer_month` được cập nhật cho một đơn, **tăng consistency level không biến hai lần ghi thành một transaction ACID có isolation trên hai partition**. Đường ghi vẫn cần idempotency, kiểm tra lỗi giữa chừng và đối soát.

### Khi nào cần CqlSession trực tiếp?

Nếu yêu cầu điều khiển một tính năng CQL/driver mà API fluent của phiên bản hiện tại không diễn đạt rõ, cân nhắc:

- Dùng một overload của `CassandraTemplate` có hỗ trợ tùy chọn đó.
- Dùng prepared CQL với `CqlSession` cho truy vấn đặc thù.
- Chỉ viết adapter nhỏ, có kiểm thử và binding tham số, thay vì trộn raw CQL vào mọi service.

Việc đi xuống tầng thấp hơn không làm mất yêu cầu thiết kế partition key; nó chỉ giúp bạn kiểm soát đường thực thi cụ thể.

## 14. Fluent API và custom conversions

Giả sử entity có trường `Price` là value object, còn CQL `total_cents` được lưu dưới dạng `bigint`. Nếu dùng custom conversions, metadata mapping và converter phải nhất quán với kiểu thực của cột.

```text
OrderByCustomerMonth (Java entity)
        |
        v
CassandraMappingContext
        |  xác định @Table, @PrimaryKey, @Column
        v
MappingCassandraConverter (+ CassandraCustomConversions)
        |  biến Java value object thành kiểu có thể bind
        v
CassandraTemplate / FluentCassandraOperations
        |
        v
CqlSession -> Cassandra
```

Chọn `OrderByCustomerMonth.class` bảo đảm đúng **ngữ cảnh metadata**, nhưng không bảo đảm:

- Converter cho `Price` đã được đăng ký.
- Giá trị không bị mất scale hoặc tràn số khi chuyển sang `long`.
- Các field khóa luôn có giá trị ổn định.
- Dữ liệu cũ tương thích với converter mới.

Khi dùng một DTO làm kết quả, phải xác nhận cơ chế projection/mapping thực tế có thể tạo DTO từ các cột đã lấy. Một vài property có thể null vì dữ liệu lịch sử thiếu cột; không nên che bằng giá trị mặc định khi nghiệp vụ cần phân biệt thiếu dữ liệu.

## 15. Chẩn đoán lỗi chọn entity và tạo thao tác

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Query báo không tìm thấy bảng | Chọn nhầm entity có `@Table` khác hoặc keyspace không đúng. | Kiểm tra mapping và schema thực. |
| CQL báo cột không tồn tại | Điều kiện được viết cho bảng khác hoặc tên cột mapping sai. | Đối chiếu query sinh ra với CQL schema. |
| Query thiếu partition key | API chỉ biết một phần khóa hoặc chọn sai bảng. | Đọc toàn bộ `PRIMARY KEY` của bảng. |
| Trả về entity thiếu thông tin | Chỉ chọn một số cột nhưng lại yêu cầu materialize entity đầy đủ. | Kiểm tra projection và các field bắt buộc. |
| `insert` ghi vào bảng khác dự kiến | Dùng class có mapping khác hoặc đổi table context không chủ ý. | Kiểm tra `@Table` và entity được truyền vào. |
| `update`/`delete` ảnh hưởng nhiều hàng | Query chỉ định partition nhưng không định danh hàng mong muốn. | Kiểm tra clustering key và phạm vi CQL. |
| Lỗi chuyển kiểu hoặc `null` | Converter thiếu, kiểu Java/CQL không tương thích. | Kiểm tra `CassandraCustomConversions` và round-trip. |
| Kết quả phân trang thiếu hoặc lặp | Cursor không gắn đúng query/bucket hoặc dữ liệu thay đổi giữa trang. | Kiểm tra paging state, sort order và nguồn dữ liệu. |
| Truy vấn chậm dù fluent chain ngắn | Partition lớn/nóng, tombstone, payload nặng, fan-out. | Đo p95/p99 latency, số hàng đọc và phân bố tải. |

### Cách debug có trình tự

1. **Viết CQL dự kiến trước:** bảng nào, cột nào, `WHERE` có đủ partition key?
2. **Kiểm tra entity:** `@Table`, khóa chính và các cột cần đọc/ghi có chính xác không?
3. **Kiểm tra fluent chain:** bước khởi tạo đang dùng class nào? Các điều kiện và giá trị bind là gì?
4. **Kiểm tra mapping/conversion:** property Java có được đọc/ghi đúng kiểu không?
5. **Kiểm tra đường thực thi:** query thực hiện trên keyspace nào, với timeout/consistency/page size nào?
6. **Kiểm tra workload:** partition có quá lớn, thường bị truy cập đồng thời hoặc chứa nhiều tombstone không?

Đừng sửa một lỗi CQL thiếu partition key bằng cách đổi ngẫu nhiên `Entity.class` hoặc thêm `ALLOW FILTERING`. Hãy quay về thiết kế bảng theo truy vấn.

## 16. Kiểm thử thao tác theo entity type

Khi hai entity phục vụ hai bảng của một nghiệp vụ, test nên xác nhận **đường truy cập và kết quả thực**, không chỉ cú pháp Java hợp lệ.

### Những trường hợp tối thiểu

| Ca kiểm thử | Điều muốn xác nhận |
| --- | --- |
| Fluent query với `OrderByCustomerMonth.class` | Trả hàng theo đúng tenant/khách/tháng và thứ tự mong muốn. |
| Cùng điều kiện nhưng dùng `OrderById.class` | Không bị hiểu lầm là cách lấy danh sách; lỗi được nhận diện đúng nguyên nhân. |
| Insert summary | Ghi vào bảng `orders_by_customer_month` với đủ khóa và giá trị. |
| Insert detail | Ghi vào `orders_by_id`, không phụ thuộc việc summary đã có hay chưa. |
| Update status của một hàng danh sách | Chỉ cập nhật hàng có đủ primary key, không thay đổi khóa. |
| Delete một summary row | Không xóa toàn bộ partition khách/tháng. |
| Read projection/DTO | Các trường cần hiển thị được ánh xạ đúng và không tải cột ngoài nhu cầu nếu đã tối ưu query. |
| Pagination | Cursor tiếp tục đúng điều kiện, page size và thứ tự. |
| Chuyển đổi kiểu custom | Ghi/đọc lại không mất thông tin và xử lý null phù hợp. |
| Ghi một phần giữa hai bảng | Có cơ chế retry/đối soát để bảo đảm trải nghiệm nghiệp vụ. |

### Unit test hay integration test?

Unit test có thể kiểm tra cách tạo `Query` và chọn entity ở service. Nhưng cần **integration test với Cassandra thực hoặc môi trường test tương đương** để biết:

- CQL do Spring Data tạo ra có hợp lệ không.
- Mapping class và khóa có khớp schema thật không.
- Converter có được áp dụng khi đọc/ghi không.
- Các thao tác update/delete có đúng phạm vi mong muốn không.
- Tính năng phân trang hoạt động thế nào với dữ liệu đủ lớn.

Ví dụ dữ liệu có ít hàng trong cùng một partition không thể thay thế thử tải với nhiều khách, nhiều tháng hoặc hot partitions.

## 17. Quy tắc chọn API trong ứng dụng thực tế

Khi thiết kế tầng truy cập Spring Data Cassandra, có thể dùng bảng quyết định sau:

| Nhu cầu | Hướng tiếp cận | Lý do |
| --- | --- | --- |
| CRUD một bảng với khóa chính ổn định | Repository | Ngắn gọn, domain-specific interface rõ. |
| Query linh hoạt nhưng vẫn đúng một entity/bảng | FluentCassandraOperations | Bước chọn class, matching và thực thi dễ đọc. |
| Thao tác tương tự nhưng muốn gọi method ngắn gọn | CassandraTemplate trực tiếp | Đơn giản khi đã có `Query` và class entity. |
| Tùy chọn CQL/driver chuyên biệt | CassandraTemplate overload hoặc CqlSession | Kiểm soát chi tiết hơn khi cần và phiên bản hỗ trợ. |
| Ghi vào nhiều bảng theo cùng nghiệp vụ | Service điều phối các repository/template | Mỗi bảng có khóa riêng; cần idempotency và xử lý thất bại từng phần. |
| Xem danh sách theo khóa khác với bảng hiện tại | Thiết kế bảng theo truy vấn mới | Không phải vấn đề chọn fluent hay repository. |

**Quy tắc ngắn gọn:** trước khi chọn method, hãy chọn **mẫu truy vấn**; trước khi chọn entity type, hãy chọn **bảng CQL** phục vụ mẫu truy vấn ấy; sau đó mới quyết định dùng fluent, template trực tiếp hay repository.

## 18. Bài tập vận dụng

**Bài 1 — Chọn đúng entity.** Ứng dụng có `OrderById` map đến `orders_by_id` và `OrderByCustomerMonth` map đến `orders_by_customer_month`. API có `tenantId`, `customerId`, `orderMonth` và cần 20 đơn mới nhất. Nên bắt đầu fluent query bằng class nào?

**Gợi ý:** `OrderByCustomerMonth.class`, vì bảng đó có partition key tương ứng với ba giá trị mà API biết. Không chọn `OrderById.class` chỉ vì cả hai đều đại diện đơn hàng.

**Bài 2 — Tìm sai khóa.** Một lập trình viên dùng `fluent.query(OrderByCustomerMonth.class)` nhưng chỉ lọc `order_id`. Vì sao không thể kỳ vọng query hiệu quả?

**Gợi ý:** `order_id` là clustering column, không phải toàn bộ partition key; Cassandra cần định vị partition qua `tenant_id`, `customer_id` và `order_month`.

**Bài 3 — DTO khác entity.** UI muốn trả `OrderCard` nhưng bảng được map bởi `OrderByCustomerMonth`. Có nên đổi phần bắt đầu thành `query(OrderCard.class)` không?

**Gợi ý:** Không nên nếu `OrderCard` chỉ là DTO. Tiếp tục chọn entity nguồn đúng bảng, rồi dùng projection/mapping kết quả theo cơ chế được phiên bản hiện tại hỗ trợ.

**Bài 4 — Cập nhật trạng thái.** Tại sao một query chỉ biết `tenant_id`, `customer_id` và `order_month` không đủ để nói “cập nhật đúng một đơn” trong bảng danh sách?

**Gợi ý:** Ba giá trị chỉ xác định partition, bên trong còn nhiều đơn phân biệt bằng `placed_at` và `order_id`. Cần đủ khóa cho hàng mục tiêu và một câu update hợp lệ với quy tắc CQL.

**Bài 5 — Ghi hai cách nhìn.** Fluent insert vào `OrderById` đã thành công. Có thể mặc định danh sách theo khách sẽ thấy đơn đó không?

**Gợi ý:** Không. Bảng danh sách là cách nhìn khác, cần được ghi và duy trì đồng bộ bởi đường ghi nghiệp vụ.

**Bài 6 — Paging.** Người dùng xem danh sách đơn tháng 11 và kéo xuống tháng 10. Paging state của query tháng 11 có tự đại diện cho query tháng 10 không?

**Gợi ý:** Không. Các bucket tháng là partition khác nhau; ứng dụng phải điều phối các truy vấn và quản lý cursor tương ứng.

**Bài 7 — Hiệu năng.** Thay `repository.findBy...` bằng `fluent.query(...).matching(...).all()` có tự giải quyết hot partition không?

**Gợi ý:** Không. Cả hai đi đến bảng CQL với cùng mô hình partition; cần điều chỉnh thiết kế khóa, bucket/shard, cửa sổ truy vấn hoặc cách đọc/ghi khi workload đòi hỏi.

## Tổng kết

`FluentCassandraOperations` cho phép diễn đạt truy cập Cassandra theo chuỗi bước, thường khởi đầu bằng **kiểu entity**: truy vấn, thêm, sửa hoặc xóa. Kiểu entity được chọn quyết định **ngữ cảnh mapping** và, thông qua `@Table`, bảng CQL mà thao tác hướng đến. Điều kiện `Query`, projection kết quả và giá trị tham số là những thành phần khác, không được đánh đồng với lựa chọn entity nguồn.

Trong hệ thống Spring Data Cassandra, hãy luôn chọn bảng theo truy vấn trước, xác định chính xác partition key và clustering columns, rồi dùng API fluent khi nó làm mã rõ hơn. Dù gọi qua `CassandraTemplate`, repository hay CQL trực tiếp, ứng dụng vẫn phải kiểm soát **consistency, paging, denormalization, ghi/xóa theo khóa và hiệu năng của mô hình dữ liệu phân tán**.
