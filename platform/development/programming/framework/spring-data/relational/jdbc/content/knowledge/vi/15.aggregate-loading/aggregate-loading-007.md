# Đánh đổi giữa tải đầy đủ aggregate và mô hình đọc chuyên biệt

Trong **Spring Data JDBC**, repository được thiết kế quanh aggregate root. Khi ứng dụng tải một aggregate, Spring Data JDBC ánh xạ root cùng các thành phần được khai báo thuộc sở hữu của nó, chẳng hạn collection con qua `@MappedCollection`. Cách này giúp domain làm việc với một đơn vị nhất quán và tránh cơ chế lazy loading phức tạp kiểu ORM.

Tuy nhiên, không phải mọi màn hình hay báo cáo đều cần toàn bộ aggregate. Một trang danh sách đơn hàng có thể chỉ cần mã đơn, ngày tạo, trạng thái, tên khách và tổng tiền. Tải cả đơn hàng cùng hàng chục dòng hàng để hiển thị năm cột sẽ tạo chi phí không cần thiết. Trong tình huống đó, một **mô hình đọc chuyên biệt** (read model/projection) dùng SQL JOIN và chỉ lấy các cột cần thiết có thể phù hợp hơn.

Bài học phân tích sự đánh đổi giữa hai cách: tải đầy đủ aggregate để thực hiện nghiệp vụ và tải mô hình đọc chuyên biệt để phục vụ truy vấn. Ta sẽ xây dựng ví dụ đơn hàng, dùng repository cho thao tác domain, dùng Spring JDBC cho read model, rồi xem cách chọn theo khối lượng dữ liệu, phân trang, transaction và tính nhất quán.

## 1. Hai nhu cầu khác nhau: thay đổi nghiệp vụ và trình bày dữ liệu

Giả sử hệ thống bán hàng có các bảng:

~~~text
purchase_orders
├── id
├── order_number
├── customer_id
├── created_at
└── status

order_lines
├── id
├── order_id
├── product_id
├── quantity
└── unit_price

customers
├── id
└── display_name
~~~

Một đơn hàng có thể có nhiều dòng hàng. Trong domain, `PurchaseOrder` là aggregate root và `OrderLine` là entity con. Khách hàng là aggregate độc lập, đơn hàng giữ tham chiếu `customerId`.

Hai use case có nhu cầu dữ liệu rất khác nhau:

**Use case A — xác nhận đơn hàng:** cần biết trạng thái hiện tại, kiểm tra các dòng hàng, áp dụng quy tắc nghiệp vụ, rồi lưu thay đổi. Đây là công việc của aggregate.

**Use case B — hiển thị danh sách đơn hàng:** chỉ cần mã đơn, tên khách, trạng thái, ngày tạo và tổng tiền. Đây là truy vấn phục vụ màn hình; không cần tạo một object graph đầy đủ để sửa nghiệp vụ.

~~~mermaid
flowchart TB
    subgraph Write["Thao tác nghiệp vụ"]
        S["OrderApplicationService"] --> R["PurchaseOrderRepository"]
        R --> A["PurchaseOrder aggregate"]
        A --> L["OrderLine collection"]
    end
    subgraph Read["Truy vấn màn hình"]
        C["OrderListController / QueryService"] --> Q["OrderSummaryDao"]
        Q --> SQL["SQL JOIN + aggregate"]
        SQL --> DTO["OrderSummary DTO"]
    end
    R --> DB[("Relational database")]
    SQL --> DB
~~~

Sơ đồ thể hiện hai đường truy cập có mục đích riêng. Cả hai vẫn có thể dùng cùng database và transaction manager; không bắt buộc phải xây hai database hay một hệ thống CQRS đầy đủ.

## 2. Tải đầy đủ aggregate trong Spring Data JDBC

### 2.1. Aggregate root và collection con

Ví dụ mapping:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    // Constructor, getters và các phương thức nghiệp vụ.
}
~~~

`OrderLine` được ánh xạ vào bảng `order_lines`. Cột `order_id` trên bảng con liên kết các dòng hàng với root. Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Khi gọi:

~~~java
PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();
~~~

Spring Data JDBC tải root và các thành phần được mapping thuộc aggregate theo chiến lược truy xuất của nó. Collection con không phải lazy association kiểu JPA: code domain có thể dùng các dòng hàng đã được tải mà không chờ lần truy cập thuộc tính sau này để tự kích hoạt lazy query.

Đây là đặc tính quan trọng của Spring Data JDBC. Nó giúp hành vi truy xuất rõ ràng hơn: khi một use case tải aggregate, lập trình viên biết rằng aggregate được tải để làm việc như một đơn vị. Nhưng nếu aggregate có hàng nghìn phần tử con, tải toàn bộ có thể tốn thời gian, bộ nhớ và tài nguyên database.

### 2.2. Khi nào cần tải đầy đủ?

Tải đầy đủ phù hợp khi use case cần các phần tử để bảo vệ bất biến hoặc thay đổi trạng thái của aggregate:

- Kiểm tra đơn có dòng hàng hay không trước khi gửi.
- Tính toán và xác nhận tổng tiền dựa trên dữ liệu domain.
- Thêm hoặc xóa dòng hàng thông qua phương thức của root.
- Kiểm tra giới hạn số lượng, trạng thái và quy tắc nghiệp vụ.
- Thực hiện thay đổi cần được lưu nhất quán trong một aggregate.

Ví dụ:

~~~java
@Transactional
public void submitOrder(long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow(() ->
            new NoSuchElementException("Không tìm thấy đơn hàng"));

    order.submit(); // Root kiểm tra status và collection lines.
    orders.save(order);
}
~~~

Nếu quy tắc `submit()` cần xác nhận đơn có ít nhất một dòng hàng, aggregate phải có thông tin về các dòng hàng để kiểm tra. Đọc riêng một cờ hoặc một con số có thể đủ trong một số domain, nhưng khi thao tác cần các thuộc tính và hành vi của từng dòng, tải aggregate là cách rõ ràng.

### 2.3. Chi phí của aggregate lớn

Giả sử một đơn có 500 dòng hàng, mỗi dòng chứa nhiều thuộc tính. Một màn hình danh sách chỉ cần 5 trường nhưng tải toàn bộ aggregate sẽ:

1. Tạo nhiều object Java không cần dùng cho màn hình.
2. Đọc nhiều cột và nhiều hàng hơn mức cần thiết.
3. Tốn bộ nhớ khi tải một trang gồm nhiều đơn.
4. Tăng công việc mapping và xử lý ở ứng dụng.
5. Có thể kéo theo nhiều truy vấn để tải các thành phần aggregate, tùy mapping và chiến lược của framework.

Không nên khẳng định mọi lần tải aggregate luôn tạo đúng N+1 query hoặc luôn là một câu JOIN. Cần quan sát SQL thực tế của phiên bản Spring Data JDBC, cấu trúc aggregate, driver và database. Điều chắc chắn về mặt thiết kế là mô hình aggregate yêu cầu tải các thành phần được mapping cần thiết để làm việc với aggregate; không có lazy loading tùy tiện như JPA.

## 3. Mô hình đọc chuyên biệt là gì?

**Read model** là cấu trúc dữ liệu được thiết kế để trả lời một câu hỏi đọc cụ thể. Nó có thể là:

- DTO chứa các cột đã JOIN từ nhiều bảng.
- Projection chỉ lấy một số thuộc tính.
- Kết quả tổng hợp như `COUNT`, `SUM`, `MAX`.
- Một bản ghi denormalized được tạo riêng để phục vụ truy vấn.

Read model không nhất thiết là entity có thể lưu lại bằng repository. Nó thường không có vòng đời domain, không cần `@Id`, và không được dùng làm aggregate root.

Ví dụ màn hình danh sách đơn cần:

| Trường | Nguồn |
|---|---|
| `orderId` | `purchase_orders.id` |
| `orderNumber` | `purchase_orders.order_number` |
| `customerName` | `customers.display_name` |
| `status` | `purchase_orders.status` |
| `createdAt` | `purchase_orders.created_at` |
| `lineCount` | `COUNT(order_lines.id)` |
| `totalAmount` | `SUM(quantity * unit_price)` |

SQL có thể tính các trường này ngay tại database:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    c.display_name AS customer_name,
    o.status,
    o.created_at,
    COUNT(l.id) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY
    o.id,
    o.order_number,
    c.display_name,
    o.status,
    o.created_at
ORDER BY o.created_at DESC, o.id DESC;
~~~

Database chỉ trả những cột màn hình cần. Ứng dụng không phải tải từng `PurchaseOrder`, sau đó duyệt tất cả `OrderLine` để tính tổng tiền và tìm tên khách hàng.

## 4. Viết read DAO bằng Spring JDBC

Spring Data JDBC và Spring JDBC có thể cùng tồn tại trong một ứng dụng. Repository quản lý aggregate, còn `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` thực hiện SQL đọc tùy chỉnh.

### 4.1. DTO cho danh sách đơn

Tạo record:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        LocalDateTime createdAt,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

`OrderSummary` là DTO/read model. Nó không phải `PurchaseOrder` aggregate root. Không tạo `OrderSummaryRepository` kế thừa `CrudRepository` chỉ để đọc kết quả này.

### 4.2. DAO dùng `NamedParameterJdbcTemplate`

~~~java
package com.example.orders.read;

import java.util.List;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSummaryDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSummaryDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findAllSummaries() {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.display_name AS customer_name,
                o.status,
                o.created_at,
                COUNT(l.id) AS line_count,
                COALESCE(
                    SUM(l.quantity * l.unit_price),
                    0
                ) AS total_amount
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN order_lines l ON l.order_id = o.id
            GROUP BY
                o.id,
                o.order_number,
                c.display_name,
                o.status,
                o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """;

        return jdbc.query(sql, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

Đoạn code giả định schema có cột `created_at` kiểu timestamp và bảng `customers` với `display_name`. Điều chỉnh kiểu thời gian theo database/driver nếu dùng `TIMESTAMP WITH TIME ZONE` hoặc kiểu thời gian khác.

### 4.3. Vì sao `LEFT JOIN` với order_lines?

Nếu dùng `JOIN` thông thường, các đơn không có dòng hàng sẽ bị loại khỏi kết quả. `LEFT JOIN` giữ đơn hàng ngay cả khi chưa có dòng con; `COUNT(l.id)` trả `0`, còn `SUM(...)` trả `NULL`, nên `COALESCE(..., 0)` chuyển tổng tiền thành `0`.

Đối với bảng khách hàng, ví dụ dùng `JOIN` vì giả định mỗi đơn phải có khách hàng hợp lệ. Nếu hệ thống cho phép dữ liệu khách bị xóa hoặc tham chiếu không còn, có thể cần `LEFT JOIN` và quy tắc hiển thị phù hợp.

### 4.4. Tầng query service

Có thể tạo service chỉ phục vụ đọc:

~~~java
@Service
public class OrderQueryService {

    private final OrderSummaryDao summaries;

    public OrderQueryService(OrderSummaryDao summaries) {
        this.summaries = summaries;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> listOrders() {
        return summaries.findAllSummaries();
    }
}
~~~

`readOnly = true` là gợi ý/cấu hình transaction cho tầng truy vấn trong Spring; nó không tự bảo đảm database sẽ cấm mọi thao tác ghi. Mục đích chính là diễn đạt use case đọc và cho transaction manager/database cơ hội tối ưu phù hợp.

## 5. Dùng projection hay viết DAO riêng?

Spring Data JDBC hỗ trợ repository query và mapping kết quả. Với truy vấn đơn giản, có thể khai báo `@Query` hoặc method derived query. Với kết quả DTO và JOIN nhiều bảng, có thể dùng `@Query` cùng kiểu projection/DTO theo khả năng mapping của phiên bản Spring Data JDBC đang dùng.

Chọn cách triển khai dựa trên độ phức tạp và mức độ kiểm soát cần thiết:

| Cách | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| `CrudRepository` trả aggregate | Nghiệp vụ cần thao tác domain | Tải aggregate theo mapping |
| Derived query | Điều kiện đọc đơn giản theo thuộc tính | Khả năng biểu đạt giới hạn ở tên method |
| `@Query` trên repository | SQL tùy chỉnh gắn chặt với repository/root | Cần quản lý mapping kết quả và tính rõ nghĩa |
| `JdbcTemplate`/`NamedParameterJdbcTemplate` | JOIN, aggregate function, báo cáo, DTO tùy chỉnh | Tự quản lý SQL và mapping hàng |
| View/materialized view | Truy vấn phức tạp, dùng lại nhiều nơi hoặc cần snapshot | Cần quản lý refresh, migration và độ trễ dữ liệu |

DAO riêng không có nghĩa phải tạo thêm một database hay vi phạm Spring Data JDBC. Đây là cách tách query phục vụ màn hình khỏi API lưu aggregate.

## 6. Đánh đổi chính giữa hai cách tải

### 6.1. So sánh theo mục đích

| Tiêu chí | Tải đầy đủ aggregate | Read model chuyên biệt |
|---|---|---|
| Mục đích | Thực hiện hành vi và bảo vệ invariant | Trả lời câu hỏi đọc cụ thể |
| Dữ liệu trả về | Root và các thành phần được mapping thuộc aggregate | Chỉ các cột/giá trị cần thiết |
| Kiểu object | Domain aggregate | DTO/projection/read model |
| Có thể gọi `save()`? | Có, qua repository root | Thường không |
| Tính nhất quán nghiệp vụ | Phù hợp cho thay đổi trong aggregate | Không tự bảo vệ invariant của aggregate |
| JOIN nhiều bảng | Không phải mục tiêu chính | Rất phù hợp |
| Tổng hợp `COUNT`, `SUM` | Có thể tính trong Java nếu dữ liệu đã tải | Database thường làm hiệu quả hơn |
| Phân trang danh sách | Cần cân nhắc chi phí tải aggregate | Thường thuận tiện và nhẹ hơn |
| Chi phí mapping | Có thể lớn khi aggregate nhiều child | Thường thấp hơn nếu DTO nhỏ |
| Khả năng tái sử dụng | Hành vi domain | Theo từng nhu cầu đọc |

### 6.2. Khi tải đầy đủ aggregate là lựa chọn đúng

Chọn aggregate khi:

- Use case thay đổi trạng thái hoặc dữ liệu.
- Cần kiểm tra nhiều bất biến nằm trong cùng aggregate.
- Cần dùng phương thức domain thay vì tự thao tác SQL từng bảng.
- Phạm vi aggregate có kích thước hợp lý.
- Việc tải các phần tử con là cần thiết để thực hiện hành vi.

Ví dụ: gửi đơn hàng cần xác nhận danh sách dòng hàng và tổng tiền trước khi đổi trạng thái. Nếu chỉ đọc `status` và `line_count` mà không tải aggregate, domain method có thể không đủ dữ liệu để kiểm tra các quy tắc khác như giới hạn số lượng hoặc điều kiện từng dòng.

### 6.3. Khi read model chuyên biệt phù hợp hơn

Chọn read model khi:

- Màn hình chỉ cần một số trường.
- Cần JOIN nhiều aggregate để hiển thị.
- Cần thống kê, đếm, tổng hợp hoặc sắp xếp theo giá trị tính toán.
- Danh sách có nhiều bản ghi và cần phân trang.
- Truy vấn là báo cáo hoặc dashboard, không dùng kết quả để thay đổi aggregate.

Ví dụ: dashboard cần tổng doanh thu theo ngày, số đơn theo trạng thái và tên khách. Tải mọi aggregate rồi cộng trong Java có thể lãng phí tài nguyên; SQL `GROUP BY` thường là cách phù hợp hơn.

### 6.4. Không biến mọi truy vấn thành một read model

Nếu chỉ cần tải một đơn theo ID để gọi `submit()`, việc viết một DAO đọc status, một DAO đọc lines, rồi tự ghép thành object domain sẽ làm phức tạp luồng nghiệp vụ và bỏ qua ranh giới aggregate. Tách read model chỉ khi nó phục vụ một nhu cầu đọc có lý do rõ ràng.

## 7. Phân trang: tránh tải hàng nghìn aggregate chỉ để hiển thị một trang

Một danh sách có 100.000 đơn hàng không nên tải toàn bộ aggregate vào bộ nhớ rồi mới cắt lấy 20 đơn đầu. Cần phân trang ở database.

### 7.1. Phân trang read model bằng `LIMIT` và `OFFSET`

Ví dụ SQL cho một trang:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    c.display_name AS customer_name,
    o.status,
    o.created_at
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
ORDER BY o.created_at DESC, o.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Thứ tự có thêm `o.id` làm tiêu chí phụ để kết quả ổn định khi nhiều đơn có cùng `created_at`. Nếu thiếu thứ tự xác định, một bản ghi có thể xuất hiện ở trang khác nhau giữa các lần truy vấn.

Với màn hình cần tổng số dòng và tổng tiền, có thể dùng subquery hoặc CTE để tổng hợp dòng hàng trước, sau đó phân trang các đơn. Cách này tránh nhân bản root trong kết quả JOIN khi mỗi đơn có nhiều dòng:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS total_amount
    FROM order_lines
    GROUP BY order_id
)
SELECT
    o.id,
    o.order_number,
    o.status,
    COALESCE(t.line_count, 0) AS line_count,
    COALESCE(t.total_amount, 0) AS total_amount
FROM purchase_orders o
LEFT JOIN line_totals t ON t.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

CTE giúp tách bước tổng hợp khỏi bước lấy đơn. Tùy database và dữ liệu, query optimizer có thể xử lý CTE khác nhau; hãy xem execution plan khi cần tối ưu.

### 7.2. Hạn chế của OFFSET trên trang sâu

Khi `OFFSET` rất lớn, database có thể phải duyệt và bỏ qua nhiều hàng trước khi trả trang. Với danh sách lớn hoặc cuộn vô hạn, cân nhắc **keyset pagination** (seek pagination):

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Client gửi lại cặp `lastCreatedAt`, `lastId` của bản ghi cuối trang trước. Index phù hợp trên `(created_at, id)` giúp database tìm trang tiếp theo mà không phải bỏ qua offset lớn. Cần xử lý timezone và độ chính xác timestamp nhất quán giữa cursor và database.

### 7.3. Khi nào phân trang aggregate?

Nếu giao diện hiển thị danh sách đơn và mỗi hàng cần thao tác domain ngay sau khi chọn, vẫn không nhất thiết tải đầy đủ aggregate cho tất cả hàng. Có thể:

1. Query trang danh sách bằng read model nhẹ.
2. Người dùng chọn một đơn.
3. Tải aggregate đầy đủ theo ID khi cần xem chi tiết hoặc thực hiện hành vi.

Cách này giữ trang danh sách nhẹ, nhưng khi thực hiện nghiệp vụ vẫn đi qua aggregate root.

## 8. Tránh nhân bản dữ liệu khi JOIN một-nhiều

JOIN trực tiếp bảng root với bảng con có thể tạo nhiều hàng cho cùng một đơn:

~~~sql
SELECT o.id, o.order_number, l.product_id
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id;
~~~

Nếu đơn `1001` có ba dòng, kết quả có ba hàng mang `o.id = 1001`. Đây là kết quả đúng của quan hệ one-to-many, nhưng nếu ánh xạ trực tiếp thành danh sách `OrderSummary`, bạn có thể thấy cùng một đơn lặp ba lần.

Để có một dòng cho mỗi đơn, dùng:

- `GROUP BY` và các hàm tổng hợp.
- Subquery/CTE tổng hợp bảng con trước khi JOIN.
- `EXISTS` nếu chỉ cần kiểm tra có dòng con.
- Projection phù hợp nếu kết quả cần nhiều cấp dữ liệu.

Ví dụ chỉ lấy đơn có ít nhất một dòng hàng:

~~~sql
SELECT o.id, o.order_number, o.status
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
)
ORDER BY o.id;
~~~

Không cần JOIN nếu không cần cột từ bảng con. `EXISTS` thường diễn đạt đúng ý định và tránh nhân bản root trong kết quả.

## 9. Tính nhất quán giữa read model và aggregate

Nếu read model và repository cùng truy cập một database, dữ liệu có thể được đọc từ cùng nguồn, nhưng thời điểm đọc và transaction isolation vẫn quan trọng.

### 9.1. Cùng transaction khi cần một ảnh chụp nhất quán

Giả sử một màn hình đọc thông tin đơn và tổng tiền từ nhiều bảng. Nếu các query chạy ở các transaction hoặc thời điểm khác nhau, một đơn có thể thay đổi giữa các lần đọc. Kết quả có thể kết hợp status mới với tổng tiền cũ.

Nếu use case cần snapshot nhất quán, hãy xác định transaction boundary và isolation level phù hợp. Không nên thêm transaction chỉ vì thói quen; hãy dựa vào yêu cầu consistency và database.

### 9.2. Read model được tính trực tiếp hay lưu sẵn?

Có hai lựa chọn:

**Tính trực tiếp khi truy vấn:** SQL JOIN/aggregate đọc từ bảng nguồn mỗi lần. Dữ liệu mới nhất theo transaction isolation, nhưng query có thể nặng.

**Lưu read model denormalized:** cập nhật một bảng summary, materialized view hoặc projection riêng khi dữ liệu nguồn thay đổi. Đọc nhanh hơn, nhưng có thể có độ trễ và cần xử lý đồng bộ, rebuild, retry.

Nếu lưu sẵn summary, phải xác định rõ:

- Bao lâu summary được cập nhật?
- Có chấp nhận eventual consistency không?
- Làm gì khi consumer xử lý event nhiều lần?
- Có thể rebuild projection từ dữ liệu nguồn không?
- Khi ghi aggregate thất bại, summary có bị cập nhật sai không?

Không cần dùng CQRS đầy đủ cho một trang danh sách đơn giản. Chỉ chuyển sang read model lưu sẵn khi đo đạc cho thấy truy vấn trực tiếp không đáp ứng yêu cầu.

### 9.3. Read model không phải nguồn quyết định nghiệp vụ cuối cùng

Một danh sách hiển thị trạng thái `DRAFT` có thể đã cũ khi người dùng bấm gửi đơn. Service vẫn cần tải aggregate mới nhất và kiểm tra lại điều kiện trước khi thay đổi. Không dùng DTO từ màn hình làm căn cứ duy nhất để ghi dữ liệu.

Luồng an toàn:

~~~text
Danh sách (read model)
       |
       v
Người dùng chọn đơn
       |
       v
Tải PurchaseOrder mới nhất
       |
       v
Kiểm tra invariant
       |
       v
Thay đổi domain + repository.save()
~~~

Đây là sự phân biệt giữa dữ liệu hiển thị và trạng thái domain tại thời điểm ghi.

## 10. Có nên tách aggregate chỉ vì tải quá nặng?

Aggregate lớn có thể là dấu hiệu ranh giới chưa phù hợp, nhưng **không nên tách aggregate chỉ để một màn hình đọc nhanh hơn**. Trước hết hãy xác định vì sao aggregate phải tải nhiều dữ liệu:

- Các entity con có thực sự thuộc cùng vòng đời và cần thay đổi nhất quán?
- Một collection có tăng không giới hạn theo thời gian?
- Có lịch sử hoặc log được gắn vào root dù có thể quản lý độc lập?
- Use case nghiệp vụ thực sự cần toàn bộ collection hay chỉ cần một phép tổng hợp?
- Có thể dùng query read model để phục vụ màn hình?

Ví dụ, `OrderLine` thường thuộc `PurchaseOrder` vì các dòng hàng tạo nên nội dung của đơn. Nhưng `OrderStatusHistory` có thể tăng liên tục và chỉ phục vụ audit. Nếu lịch sử có thể quản lý độc lập, việc đưa toàn bộ lịch sử vào aggregate có thể làm tải đơn ngày càng nặng.

Một thiết kế khác có thể là:

~~~text
PurchaseOrder aggregate
├── id
├── status
└── OrderLine collection

OrderStatusHistory aggregate (hoặc dữ liệu audit riêng)
├── id
├── orderId
├── oldStatus
├── newStatus
└── changedAt
~~~

`OrderStatusHistory` tham chiếu `orderId`, nhưng có thể có repository/query riêng nếu vòng đời và yêu cầu audit độc lập. Khi đó cần quyết định cách bảo đảm audit được ghi cùng sự kiện thay đổi trạng thái, chẳng hạn cùng transaction hoặc outbox.

## 11. Một ví dụ service kết hợp write model và read model

Ví dụ service dùng repository để thay đổi trạng thái và DAO để hiển thị danh sách:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OrderSummaryDao summaries;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OrderSummaryDao summaries) {
        this.orders = orders;
        this.summaries = summaries;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> listOrders() {
        return summaries.findAllSummaries();
    }

    @Transactional
    public void submit(long orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() ->
                new NoSuchElementException("Không tìm thấy đơn hàng"));

        order.submit();
        orders.save(order);
    }
}
~~~

Ví dụ cho thấy một application service có thể điều phối cả read DAO và repository. Trong dự án lớn, có thể tách thành `OrderQueryService` và `OrderCommandService` để trách nhiệm rõ ràng hơn. Không có quy tắc bắt buộc mọi query và command phải ở hai class khác nhau.

Điểm quan trọng:

- `listOrders()` trả DTO cho màn hình.
- `submit()` tải aggregate root để kiểm tra và thay đổi nghiệp vụ.
- DTO không được gửi ngược vào `repository.save()`.
- Repository không bị biến thành nơi chứa mọi truy vấn báo cáo.

## 12. Hiệu năng: đo trước khi tối ưu

Không có quy tắc rằng read model luôn nhanh hơn hoặc aggregate loading luôn chậm. Kết quả phụ thuộc dữ liệu, index, số truy vấn, network round-trip, database và cách mapping.

Khi so sánh hai phương án, đo ít nhất:

| Chỉ số | Câu hỏi |
|---|---|
| Số hàng đọc | Aggregate tải bao nhiêu child? Read query trả bao nhiêu dòng? |
| Số cột đọc | Có lấy nhiều cột không dùng không? |
| Số SQL statement | Mapping aggregate thực hiện bao nhiêu câu truy vấn? |
| Thời gian database | JOIN/aggregate có index phù hợp không? |
| Thời gian mapping | Có tạo object graph lớn không? |
| Bộ nhớ | Trang kết quả giữ bao nhiêu object trong heap? |
| Kích thước trang | Có giới hạn số bản ghi không? |
| Độ mới dữ liệu | Projection lưu sẵn có độ trễ bao lâu? |

Một số index có thể cân nhắc cho ví dụ:

~~~sql
CREATE INDEX idx_purchase_orders_created_id
    ON purchase_orders(created_at, id);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);

CREATE INDEX idx_purchase_orders_customer_id
    ON purchase_orders(customer_id);
~~~

Index cụ thể cần dựa vào truy vấn thực tế và hệ quản trị. Mỗi index làm tăng chi phí ghi và dung lượng lưu trữ; không thêm index theo mọi cột một cách máy móc.

Dùng execution plan của database để xem JOIN, sort và aggregate có tận dụng index hay không. SQL ít dòng hơn không tự động có nghĩa nhanh hơn.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Tải mọi aggregate để hiển thị một danh sách nhỏ | Đọc và mapping nhiều dữ liệu không cần | Dùng DTO/projection với các cột cần thiết |
| Dùng DTO để cập nhật aggregate | Bỏ qua invariant và trạng thái mới nhất | Tải root, gọi method domain, lưu qua repository |
| Coi collection con là lazy | Truy cập sau đó không tạo lazy query như JPA | Tải aggregate có chủ đích hoặc dùng read query |
| JOIN root với child rồi trả một DTO cho mỗi hàng | Một đơn xuất hiện nhiều lần | `GROUP BY`, subquery hoặc `EXISTS` |
| Phân trang sau khi tải toàn bộ object graph | Tốn bộ nhớ và thời gian | Phân trang tại database bằng read model |
| Tạo read model lưu sẵn mà không xác định độ trễ | Người dùng thấy dữ liệu cũ khó giải thích | Định nghĩa consistency, rebuild và xử lý event |
| Tách aggregate chỉ để tối ưu một màn hình | Làm yếu ranh giới nghiệp vụ | Tách query trước; chỉ tách root khi lifecycle/invariant yêu cầu |
| Dùng dữ liệu danh sách để quyết định ghi | Trạng thái có thể đã thay đổi | Tải aggregate mới và kiểm tra lại khi command |
| Viết SQL JOIN nhưng thiếu index FK | Query chậm khi dữ liệu tăng | Xem execution plan và index phù hợp |

## 14. Quy trình lựa chọn cho một use case mới

Khi thiết kế truy vấn trong Spring Data JDBC, hãy trả lời lần lượt:

1. **Đây là command hay query?** Nếu cần thay đổi nghiệp vụ, bắt đầu từ aggregate root. Nếu chỉ hiển thị/tổng hợp, cân nhắc read model.
2. **Có cần invariant của aggregate không?** Nếu có, tải root và các thành phần cần thiết để domain kiểm tra.
3. **Cần những trường nào?** Nếu chỉ cần vài cột từ nhiều bảng, viết projection/DTO.
4. **Khối lượng dữ liệu là bao nhiêu?** Nếu có danh sách lớn, phân trang ở database.
5. **Cần độ nhất quán nào?** Tính trực tiếp từ bảng nguồn, dùng transaction snapshot hoặc projection lưu sẵn.
6. **Có đo được nút thắt không?** Xem SQL, query plan, số hàng và bộ nhớ trước khi tách aggregate hoặc thêm cơ chế phức tạp.

### Ma trận quyết định nhanh

| Nhu cầu | Cách bắt đầu |
|---|---|
| Đọc một đơn để xác nhận | `PurchaseOrderRepository.findById()` |
| Thay đổi trạng thái đơn | Tải aggregate, gọi domain method, `save()` |
| Danh sách đơn có tên khách | Read DAO với JOIN và DTO |
| Tổng doanh thu theo ngày | SQL `GROUP BY` |
| Trang danh sách lớn | Projection + database pagination |
| Chi tiết đơn có toàn bộ dòng hàng | Tải aggregate nếu cần hành vi domain; DTO JOIN nếu chỉ đọc |
| Audit history dài | Query riêng hoặc mô hình audit độc lập |
| Dashboard cần dữ liệu tổng hợp rất nhanh | Cân nhắc view/materialized view/projection sau khi đo |

## 15. Bài tập thực hành

### Bài 1 — So sánh aggregate và DTO

1. Tạo `PurchaseOrder` có 20 `OrderLine`.
2. Đọc đơn bằng `findById()` và ghi nhận số câu SQL, số hàng đọc và thời gian.
3. Viết query `OrderSummaryDao` trả mã đơn, trạng thái và tổng tiền.
4. So sánh dữ liệu được tải và lượng object được tạo.
5. Giải thích vì sao DTO không thay thế aggregate khi cần gọi `submit()`.

### Bài 2 — Phân trang danh sách

1. Tạo vài nghìn đơn hàng.
2. Viết query phân trang 20 dòng với thứ tự `created_at DESC, id DESC`.
3. Thử `OFFSET` ở trang đầu và trang sâu.
4. Viết phiên bản keyset pagination dùng `created_at` và `id`.
5. So sánh execution plan và thời gian.

### Bài 3 — JOIN một-nhiều

1. JOIN `purchase_orders` và `order_lines`.
2. Quan sát một đơn có nhiều dòng làm kết quả bị lặp.
3. Viết lại bằng `GROUP BY` hoặc CTE tổng hợp trước.
4. Kiểm tra đơn không có dòng hàng có còn xuất hiện không.

### Bài 4 — Quyết định ranh giới

Giả sử một đơn có 10.000 bản ghi trạng thái lịch sử. Xác định:

- Bản ghi lịch sử có cần được thay đổi nhất quán cùng aggregate không?
- Có thể là dữ liệu audit riêng không?
- Màn hình chi tiết cần tải tất cả hay chỉ 10 bản ghi gần nhất?
- Có nên dùng read DAO phân trang cho lịch sử?
- Nếu tách mô hình, làm sao bảo đảm audit được ghi cùng thay đổi trạng thái?

## 16. Kết luận

**Tải đầy đủ aggregate** phù hợp khi use case cần hành vi domain và các invariant của aggregate root. Trong Spring Data JDBC, các thành phần được mapping thuộc aggregate được tải theo chiến lược của framework, không dựa vào lazy loading tùy thời điểm truy cập như JPA. Điều này giúp hành vi rõ ràng, nhưng aggregate lớn có thể làm tăng số hàng đọc, số object và bộ nhớ.

**Mô hình đọc chuyên biệt** phù hợp khi màn hình cần một tập cột nhỏ, JOIN nhiều bảng, thống kê hoặc phân trang. `JdbcTemplate`, `NamedParameterJdbcTemplate`, `@Query`, projection hoặc view có thể cung cấp DTO nhẹ mà không cần tạo repository CRUD cho từng bảng.

Hai cách bổ sung cho nhau: dùng repository để thay đổi aggregate, dùng read model để trả lời câu hỏi đọc. Khi người dùng thực hiện command, hãy tải aggregate mới nhất và kiểm tra lại quy tắc nghiệp vụ. Chỉ tách aggregate khi lifecycle và invariant cho thấy ranh giới mới hợp lý; đừng thay đổi domain chỉ vì một màn hình cần ít cột hơn.
