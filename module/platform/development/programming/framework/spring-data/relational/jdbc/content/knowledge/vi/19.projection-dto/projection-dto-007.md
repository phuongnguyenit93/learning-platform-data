# RowMapper tùy chỉnh cho kết quả JOIN và báo cáo

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, repository tập trung vào việc lưu và tải aggregate root theo mô hình domain. Màn hình báo cáo thường cần dữ liệu từ nhiều bảng: đơn hàng, khách hàng, dòng hàng, tên sản phẩm hoặc số liệu tổng hợp. Kết quả như vậy thường không phải một aggregate hoàn chỉnh và không nên ép vào entity chỉ để tận dụng repository CRUD.

Một cách phù hợp là dùng **Spring JDBC** cùng **RowMapper<T>** để ánh xạ từng hàng ResultSet thành DTO/projection dành riêng cho truy vấn đọc. Spring Data JDBC và Spring JDBC có thể dùng chung DataSource trong ứng dụng Spring Boot; repository vẫn quản lý aggregate, còn JdbcTemplate hoặc NamedParameterJdbcTemplate thực hiện các truy vấn JOIN và báo cáo.

## 1. Vì sao cần RowMapper tùy chỉnh?

Giả sử trang báo cáo đơn hàng cần hiển thị:

- Mã đơn hàng và thời điểm tạo.
- Trạng thái đơn.
- Mã và tên khách hàng.
- Tổng số dòng hàng và tổng tiền của đơn.

Thông tin này đến từ nhiều bảng. Nếu tải từng Order qua OrderRepository, sau đó tải Customer và từng OrderItem riêng, ứng dụng có thể tạo nhiều truy vấn và phải tự ghép dữ liệu. Nếu cố đưa toàn bộ kết quả báo cáo vào entity Order, mô hình domain sẽ bị trộn với nhu cầu trình bày.

Thay vào đó, tạo DTO báo cáo và dùng SQL JOIN/aggregate để database trả về đúng các cột cần thiết:

~~~mermaid
flowchart TB
    Service["OrderReportService"]
    Query["NamedParameterJdbcTemplate<br/>SQL JOIN / GROUP BY"]
    DB[("Database<br/>orders + customers + order_items")]
    RS["ResultSet<br/>mỗi hàng kết quả"]
    Mapper["OrderReportRowMapper"]
    DTO["OrderReportRow DTO"]
    API["Controller / Export / Report"]
    Service --> Query --> DB --> RS --> Mapper --> DTO --> API
~~~

**RowMapper** là cầu nối giữa một hàng trong ResultSet và một object Java. Nó giúp kiểm soát rõ tên cột, kiểu dữ liệu, giá trị null và cấu trúc DTO.

## 2. RowMapper là gì?

Interface RowMapper<T> thuộc package org.springframework.jdbc.core:

~~~java
package org.springframework.jdbc.core;

import java.sql.ResultSet;
import java.sql.SQLException;

public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Framework gọi mapRow cho từng hàng kết quả và dùng object trả về để tạo danh sách. Tham số:

- ResultSet rs: hàng hiện tại của truy vấn.
- int rowNum: vị trí hàng trong tập kết quả, bắt đầu từ 0.
- Giá trị trả về: object kiểu T được dựng từ hàng hiện tại.

Thông thường một RowMapper nên **không giữ state giữa các lần gọi**. Mỗi lần mapRow chỉ ánh xạ hàng hiện tại và trả một DTO mới. Không lưu ResultSet vào field, không giữ dữ liệu của hàng trước để ghép nhóm.

### RowMapper không phải aggregate mapper của Spring Data JDBC

Hai cơ chế có mục tiêu khác nhau:

| Cơ chế | Mục đích | Kiểu dữ liệu thường nhận |
|---|---|---|
| CrudRepository<Order, Long> | Đọc/ghi aggregate theo mapping domain | Order |
| RowMapper<OrderReportRow> | Ánh xạ hàng của SQL tùy chỉnh | DTO/report row |
| ResultSetExtractor<T> | Xử lý toàn bộ ResultSet thành một cấu trúc | Một DTO tổng hợp, map hoặc danh sách đã nhóm |

RowMapper thuộc Spring JDBC. Nó không tự áp dụng quy tắc aggregate, không tự tải collection con theo @MappedCollection và không thay thế cơ chế mapping của Spring Data JDBC.

## 3. Chuẩn bị ví dụ JOIN

Giả sử có các bảng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE sales_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_orders(id),
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14, 2) NOT NULL
);
~~~

Một hàng sales_orders tham chiếu một Customer; một Order có thể có nhiều OrderItem. Truy vấn báo cáo có thể JOIN ba bảng và tính tổng:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.created_at AS order_created_at,
    c.customer_code AS customer_code,
    c.display_name AS customer_name,
    COUNT(i.id) AS item_count,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY
    o.id,
    o.status,
    o.created_at,
    c.customer_code,
    c.display_name
ORDER BY o.created_at DESC, o.id DESC;
~~~

LEFT JOIN giữ lại đơn chưa có dòng hàng; COUNT(i.id) trả 0 khi không có item; COALESCE biến tổng null thành 0. Hai mốc thời gian dùng khoảng nửa mở [from_time, to_time) để tránh đếm trùng thời điểm ở hai kỳ liên tiếp.

SQL trên dùng cú pháp phổ biến của PostgreSQL và MySQL. Kiểu timestamp, precision và cách bind thời gian cần khớp schema cùng JDBC driver của dự án.

## 4. Tạo DTO cho báo cáo

DTO chỉ chứa những thông tin mà báo cáo cần:

~~~java
package com.example.sales.report;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderReportRow(
    Long orderId,
    String orderStatus,
    LocalDateTime orderCreatedAt,
    String customerCode,
    String customerName,
    long itemCount,
    BigDecimal totalAmount
) {}
~~~

Đây là **read model**. Nó không cần @Id, @Table hay repository CRUD của Spring Data JDBC. DTO có thể gộp dữ liệu từ nhiều aggregate mà không làm thay đổi ranh giới domain.

Nếu database trả timestamp có timezone, cân nhắc OffsetDateTime hoặc Instant thay cho LocalDateTime, và thống nhất chính sách lưu/hiển thị timezone. Ví dụ trên giả định cột created_at là timestamp không timezone.

## 5. Viết RowMapper tùy chỉnh

~~~java
package com.example.sales.report;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Component;

@Component
public class OrderReportRowMapper
        implements RowMapper<OrderReportRow> {

    @Override
    public OrderReportRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderReportRow(
            rs.getLong("order_id"),
            rs.getString("order_status"),
            rs.getTimestamp("order_created_at").toLocalDateTime(),
            rs.getString("customer_code"),
            rs.getString("customer_name"),
            rs.getLong("item_count"),
            rs.getBigDecimal("total_amount")
        );
    }
}
~~~

Mapper sử dụng **alias** do SQL khai báo. Ví dụ o.id AS order_id giúp mapper đọc order_id, tránh nhập nhằng khi nhiều bảng cùng có cột id, status hoặc created_at.

Nếu cột bắt buộc không null theo schema, có thể dùng getter tương ứng trực tiếp. Nếu cột có thể null, phải xử lý null rõ ràng thay vì để Java primitive biến null thành 0.

### Xử lý cột nullable với primitive

ResultSet.getLong() trả 0 khi cột SQL là NULL; gọi thêm wasNull() để phân biệt:

~~~java
long rawValue = rs.getLong("optional_customer_id");
Long customerId = rs.wasNull() ? null : rawValue;
~~~

Hoặc dùng getObject với kiểu wrapper nếu JDBC driver hỗ trợ chuyển đổi phù hợp:

~~~java
Long customerId = rs.getObject("optional_customer_id", Long.class);
~~~

Với trường hợp LEFT JOIN, các cột từ bảng bên phải có thể null. DTO cần dùng kiểu tham chiếu như Long, Integer, BigDecimal, String hoặc kiểu ngày giờ nullable thay vì primitive khi cần giữ trạng thái đó.

## 6. Thực thi truy vấn với NamedParameterJdbcTemplate

NamedParameterJdbcTemplate cho phép viết placeholder theo tên như :fromTime, thay vì dấu ? theo vị trí. Ví dụ query class:

~~~java
package com.example.sales.report;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReportQuery {

    private static final String SQL = """
        SELECT
            o.id AS order_id,
            o.status AS order_status,
            o.created_at AS order_created_at,
            c.customer_code AS customer_code,
            c.display_name AS customer_name,
            COUNT(i.id) AS item_count,
            COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
        FROM sales_orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE o.created_at >= :fromTime
          AND o.created_at < :toTime
        GROUP BY
            o.id, o.status, o.created_at,
            c.customer_code, c.display_name
        ORDER BY o.created_at DESC, o.id DESC
        """;

    private final NamedParameterJdbcTemplate jdbc;
    private final OrderReportRowMapper rowMapper;

    public OrderReportQuery(
            NamedParameterJdbcTemplate jdbc,
            OrderReportRowMapper rowMapper) {
        this.jdbc = jdbc;
        this.rowMapper = rowMapper;
    }

    public List<OrderReportRow> findOrders(
            LocalDateTime fromTime,
            LocalDateTime toTime) {

        var params = new MapSqlParameterSource()
            .addValue("fromTime", fromTime)
            .addValue("toTime", toTime);

        return jdbc.query(SQL, params, rowMapper);
    }
}
~~~

Spring Boot thường tự cấu hình NamedParameterJdbcTemplate khi có starter JDBC và DataSource. Nếu dự án dùng Spring Data JDBC, các dependency JDBC tương ứng thường đã có trong dependency graph; hãy để Spring Boot dependency management quản lý phiên bản tương thích.

Gọi query:

~~~java
List<OrderReportRow> rows =
    orderReportQuery.findOrders(
        LocalDateTime.of(2026, 1, 1, 0, 0),
        LocalDateTime.of(2026, 2, 1, 0, 0)
    );
~~~

jdbc.query(sql, params, rowMapper) thực hiện truy vấn, gọi mapper cho mỗi hàng và trả về List<OrderReportRow>. Tham số được bind riêng với SQL; không nối chuỗi thời gian hoặc giá trị do người dùng gửi vào câu lệnh.

## 7. Dùng JdbcTemplate với positional parameters

Nếu thích placeholder ?, có thể dùng JdbcTemplate:

~~~java
String sql = """
    SELECT id, customer_id, status, created_at
    FROM sales_orders
    WHERE status = ?
    ORDER BY created_at DESC, id DESC
    """;

List<OrderSummary> orders = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("id"),
        rs.getLong("customer_id"),
        rs.getString("status"),
        rs.getTimestamp("created_at").toLocalDateTime()
    ),
    "CONFIRMED"
);
~~~

Với JdbcTemplate, giá trị tham số theo thứ tự dấu ?. Với NamedParameterJdbcTemplate, giá trị theo tên. Cả hai đều dùng bind parameter; lựa chọn dựa trên độ rõ ràng và số lượng tham số của truy vấn.

Lambda (rs, rowNum) -> ... là một RowMapper ngắn gọn. Khi mapping dài hoặc được tái sử dụng, tách thành class riêng giúp code dễ đọc và dễ kiểm thử.

## 8. JOIN nhiều-một: một hàng kết quả cho một DTO

JOIN Order với Customer là quan hệ nhiều-một. Mỗi Order chỉ có một Customer, nên nếu truy vấn không JOIN thêm collection nhiều hàng, mỗi Order tạo ra một hàng kết quả:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.id AS customer_id,
    c.customer_code AS customer_code,
    c.display_name AS customer_name
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id DESC;
~~~

DTO:

~~~java
public record OrderCustomerRow(
    Long orderId,
    String orderStatus,
    Long customerId,
    String customerCode,
    String customerName
) {}
~~~

Mapper:

~~~java
RowMapper<OrderCustomerRow> mapper = (rs, rowNum) ->
    new OrderCustomerRow(
        rs.getLong("order_id"),
        rs.getString("order_status"),
        rs.getLong("customer_id"),
        rs.getString("customer_code"),
        rs.getString("customer_name")
    );
~~~

Đây là trường hợp phù hợp cho RowMapper: **mỗi hàng SQL tương ứng một object DTO độc lập**. Việc JOIN chỉ nhằm lấy dữ liệu hiển thị; không có nghĩa Customer trở thành object con được Order sở hữu.

## 9. JOIN một-nhiều: tránh tạo DTO cha trùng lặp

Khi JOIN Order với OrderItem, một Order có thể xuất hiện nhiều lần:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.display_name AS customer_name,
    i.id AS item_id,
    i.sku AS item_sku,
    i.quantity AS item_quantity,
    i.unit_price AS item_unit_price
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
~~~

Nếu Order có ba item, ResultSet có ba hàng với cùng order_id. Nếu dùng RowMapper<OrderSummary> đơn giản, bạn sẽ nhận ba object OrderSummary trùng thông tin cha. RowMapper không tự ghép ba item vào một danh sách trong một Order.

Cần chọn một trong hai thiết kế:

1. **DTO phẳng:** mỗi hàng là một OrderItemReportRow, chấp nhận Order lặp lại cho từng item. Phù hợp xuất CSV, báo cáo dạng bảng hoặc bảng chi tiết.
2. **DTO phân cấp:** một Order chứa danh sách item. Dùng ResultSetExtractor hoặc một bước grouping để gom các hàng theo Order ID.

### DTO phân cấp

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderDetailReport(
    Long orderId,
    String orderStatus,
    String customerName,
    List<OrderItemReport> items
) {}

public record OrderItemReport(
    Long itemId,
    String sku,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

### ResultSetExtractor để nhóm nhiều hàng

ResultSetExtractor<T> nhận toàn bộ ResultSet, phù hợp khi một kết quả cần được gom thành cấu trúc cha-con:

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.ResultSetExtractor;

public class OrderDetailReportExtractor
        implements ResultSetExtractor<List<OrderDetailReport>> {

    @Override
    public List<OrderDetailReport> extractData(ResultSet rs)
            throws SQLException {

        Map<Long, OrderAccumulator> grouped = new LinkedHashMap<>();

        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            OrderAccumulator order = grouped.get(orderId);

            if (order == null) {
                order = new OrderAccumulator(
                    orderId,
                    rs.getString("order_status"),
                    rs.getString("customer_name")
                );
                grouped.put(orderId, order);
            }

            long itemId = rs.getLong("item_id");
            boolean itemIsNull = rs.wasNull();

            // LEFT JOIN không có item: không thêm dòng con.
            if (!itemIsNull) {
                order.items.add(new OrderItemReport(
                    itemId,
                    rs.getString("item_sku"),
                    rs.getObject("item_quantity", Integer.class),
                    rs.getBigDecimal("item_unit_price")
                ));
            }
        }

        List<OrderDetailReport> result = new ArrayList<>();
        for (OrderAccumulator order : grouped.values()) {
            result.add(order.toReport());
        }
        return result;
    }

    private static final class OrderAccumulator {
        private final Long id;
        private final String status;
        private final String customerName;
        private final List<OrderItemReport> items = new ArrayList<>();

        private OrderAccumulator(
                Long id,
                String status,
                String customerName) {
            this.id = id;
            this.status = status;
            this.customerName = customerName;
        }

        private OrderDetailReport toReport() {
            return new OrderDetailReport(
                id, status, customerName, List.copyOf(items)
            );
        }
    }
}
~~~

Điểm cốt lõi:

- LinkedHashMap giữ thứ tự Order xuất hiện theo SQL ORDER BY.
- Mỗi order_id chỉ tạo một accumulator.
- Mỗi hàng có item_id khác SQL NULL thì thêm một item.
- LEFT JOIN không có item vẫn tạo Order với danh sách rỗng.
- Cuối cùng chuyển accumulator thành DTO bất biến.

Với truy vấn này, ResultSetExtractor phù hợp hơn RowMapper vì việc ánh xạ cần quan sát nhiều hàng để tạo một object cha.

## 10. Chọn RowMapper, ResultSetExtractor hay query DTO phẳng?

| Nhu cầu | Lựa chọn |
|---|---|
| Mỗi hàng SQL là một DTO độc lập | RowMapper<T> |
| JOIN Order-Customer, một hàng cho mỗi Order | RowMapper<OrderCustomerRow> |
| Báo cáo phẳng, một hàng cho mỗi OrderItem | RowMapper<OrderItemReportRow> |
| JOIN cha-con, cần một Order chứa danh sách items | ResultSetExtractor<List<OrderDetailReport>> |
| Một giá trị tổng hợp như COUNT/SUM | queryForObject(...) hoặc mapper scalar phù hợp |
| Dữ liệu cần aggregate mapping theo domain | OrderRepository.findById(...) |

Đừng dùng RowMapper chỉ vì truy vấn có JOIN. Hãy nhìn **hình dạng ResultSet** và kiểu dữ liệu mong muốn. Nếu một hàng tương ứng một object, RowMapper đơn giản. Nếu nhiều hàng phải kết hợp thành một object, dùng extractor/grouping.

## 11. Ánh xạ kiểu dữ liệu và NULL đúng cách

Các getter của ResultSet cần phù hợp kiểu cột:

| SQL | Getter thường dùng | Kiểu Java |
|---|---|---|
| BIGINT không null | getLong() | long/Long |
| INTEGER không null | getInt() | int/Integer |
| VARCHAR | getString() | String |
| DECIMAL/NUMERIC | getBigDecimal() | BigDecimal |
| DATE | getDate() hoặc getObject(..., LocalDate.class) | LocalDate |
| TIMESTAMP | getTimestamp() | Timestamp/LocalDateTime |
| BOOLEAN | getBoolean() | boolean/Boolean |

Với kiểu primitive, getLong, getInt và getBoolean trả giá trị mặc định khi cột SQL NULL; gọi wasNull() ngay sau getter để kiểm tra. wasNull() nói về giá trị vừa đọc gần nhất, vì vậy đừng gọi một getter khác trước khi kiểm tra.

Ví dụ an toàn:

~~~java
long raw = rs.getLong("optional_quantity");
Integer quantity = rs.wasNull() ? null : Math.toIntExact(raw);
~~~

Hoặc:

~~~java
Integer quantity = rs.getObject("optional_quantity", Integer.class);
~~~

Với LEFT JOIN, việc kiểm tra khóa chính bảng con là cách đáng tin cậy để biết có hàng con hay không. Không suy luận “không có item” chỉ từ một cột mô tả có thể nullable như SKU hoặc ghi chú.

## 12. Tách SQL và RowMapper để dễ bảo trì

Với báo cáo lớn, nên tách các thành phần:

- **Query class/repository đọc:** chứa SQL và gọi NamedParameterJdbcTemplate.
- **RowMapper:** ánh xạ một hàng thành DTO.
- **DTO/projection:** biểu diễn kết quả cho use case.
- **Service:** điều phối tham số, quyền truy cập và nghiệp vụ đọc.

Ví dụ tổ chức:

~~~text
com.example.sales
├── order/
│   ├── Order.java
│   └── OrderRepository.java
└── report/
    ├── OrderReportRow.java
    ├── OrderReportRowMapper.java
    ├── OrderReportQuery.java
    └── OrderReportService.java
~~~

Không đặt mọi câu SQL báo cáo vào aggregate entity. Cấu trúc riêng giúp báo cáo thay đổi theo nhu cầu hiển thị mà không làm phức tạp mô hình domain.

## 13. Transaction và @Transactional(readOnly = true)

Một query báo cáo thường chỉ đọc. Có thể đánh dấu service:

~~~java
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReportService {

    private final OrderReportQuery query;

    public OrderReportService(OrderReportQuery query) {
        this.query = query;
    }

    @Transactional(readOnly = true)
    public List<OrderReportRow> report(
            LocalDateTime from,
            LocalDateTime to) {
        return query.findOrders(from, to);
    }
}
~~~

readOnly = true là metadata/hint cho transaction manager và provider/driver; mức độ tối ưu hoặc hành vi cụ thể tùy cấu hình. Nó **không phải cơ chế bảo mật** bảo đảm mọi câu SQL ghi đều bị database từ chối. Nếu cần ngăn ghi, phải dùng quyền database hoặc chính sách kết nối phù hợp.

Khi cùng use case đọc dữ liệu bằng Spring Data JDBC repository và NamedParameterJdbcTemplate, hai thành phần có thể tham gia cùng transaction nếu dùng chung DataSource và transaction manager được cấu hình tương ứng. Điều này hữu ích khi cần một góc nhìn nhất quán trong phạm vi transaction.

## 14. Hiệu năng của JOIN và báo cáo

RowMapper giúp chuyển đổi kết quả; nó không tự làm SQL nhanh hơn. Hiệu năng chủ yếu phụ thuộc truy vấn, index, số hàng trả về và dữ liệu được đọc.

Một số nguyên tắc:

1. Chỉ SELECT các cột cần thiết; tránh SELECT * trong báo cáo có nhiều bảng.
2. Dùng alias duy nhất cho cột trùng tên như id, status, created_at.
3. Tạo index cho cột JOIN/filter thường dùng, ví dụ sales_orders.customer_id, order_items.order_id và các cột ngày tháng phù hợp workload.
4. Kiểm tra execution plan trước khi tối ưu dựa trên phỏng đoán.
5. Dùng phân trang hoặc giới hạn kết quả cho báo cáo lớn.
6. Tránh JOIN collection nhiều-một cách thiếu kiểm soát khiến số hàng phình lớn.
7. Với báo cáo tổng hợp, tính COUNT, SUM, AVG trong SQL khi database có thể làm hiệu quả; ánh xạ kết quả scalar vào DTO.

Ví dụ index minh họa:

~~~sql
CREATE INDEX idx_sales_orders_created_at
    ON sales_orders(created_at);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
~~~

Index cụ thể cần căn cứ vào điều kiện WHERE, JOIN, ORDER BY và dữ liệu thực tế. Thêm index làm tăng dung lượng và chi phí INSERT/UPDATE; không tạo mọi index chỉ vì cột xuất hiện trong một truy vấn.

## 15. Phân trang cho truy vấn báo cáo tùy chỉnh

Với SQL tùy chỉnh qua NamedParameterJdbcTemplate, có thể tự quản lý giới hạn và offset:

~~~java
String sql = """
    SELECT
        o.id AS order_id,
        o.status AS order_status,
        c.display_name AS customer_name
    FROM sales_orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.status = :status
    ORDER BY o.created_at DESC, o.id DESC
    LIMIT :limit OFFSET :offset
    """;

var params = new MapSqlParameterSource()
    .addValue("status", "CONFIRMED")
    .addValue("limit", pageSize)
    .addValue("offset", (long) pageNumber * pageSize);

List<OrderCustomerRow> rows =
    namedParameterJdbcTemplate.query(sql, params, rowMapper);
~~~

Cú pháp LIMIT/OFFSET ở ví dụ phù hợp PostgreSQL/MySQL; database khác có thể dùng cú pháp khác. Kiểm tra pageNumber >= 0, pageSize > 0 và giới hạn page size tối đa trước khi tính offset. Dùng phép nhân kiểu long để tránh tràn số nguyên 32 bit.

Nếu cần tổng số trang, chạy thêm query count phù hợp với cùng điều kiện lọc. Nếu chỉ cần “còn dữ liệu không”, có thể lấy dư một hàng (pageSize + 1) rồi loại hàng dư khỏi content. Đây là logic do query class/service tùy chỉnh quản lý; NamedParameterJdbcTemplate không tự tạo Page/Slice metadata như repository query method.

## 16. An toàn truy vấn và xử lý dữ liệu đầu vào

Luôn bind giá trị:

~~~java
var params = new MapSqlParameterSource()
    .addValue("status", requestedStatus)
    .addValue("fromTime", fromTime)
    .addValue("toTime", toTime);
~~~

Không ghép chuỗi trực tiếp:

~~~java
// Không an toàn
String sql = "SELECT * FROM sales_orders WHERE status = '"
    + requestedStatus + "'";
~~~

Bind parameter bảo vệ giá trị đầu vào khỏi bị diễn giải thành cú pháp SQL. Tuy nhiên, placeholder không dùng để bind tên bảng, tên cột hoặc keyword ORDER BY. Nếu sort được chọn từ request, ánh xạ lựa chọn đó qua danh sách property/identifier đã cho phép trước khi xây dựng câu SQL.

Ngoài ra:

- Giới hạn ngày bắt đầu/kết thúc và page size theo chính sách nghiệp vụ.
- Không trả dữ liệu cá nhân không cần thiết trong báo cáo.
- Kiểm tra quyền truy cập trước khi truy vấn dữ liệu theo khách hàng/đơn hàng.
- Không ghi SQL parameter nhạy cảm vào log production.

## 17. Kiểm thử RowMapper và truy vấn báo cáo

Có thể kiểm tra mapper riêng bằng ResultSet mock, nhưng kiểm thử tích hợp với database thực tế thường hữu ích hơn để xác minh tên cột, kiểu dữ liệu, null và dialect.

Các trường hợp nên kiểm tra:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Order có một Customer và nhiều item | DTO chứa đúng dữ liệu join |
| Order chưa có item với LEFT JOIN | itemCount = 0, tổng tiền bằng 0 |
| Cột nullable từ bảng bên phải | DTO nhận null thay vì 0 ngoài ý muốn |
| Nhiều Order cùng Customer | Mỗi Order tạo đúng hàng báo cáo |
| Một Order có nhiều item | DTO phẳng có nhiều hàng hoặc extractor gom đúng một Order |
| Khoảng thời gian rỗng | Danh sách trả về rỗng |
| Tham số có dấu nháy | Bind parameter vẫn là dữ liệu |
| Tổng tiền lớn hoặc có phần thập phân | Dùng BigDecimal, không chuyển sang double |

Đối với phép tính tiền, dùng BigDecimal/DECIMAL thay cho double để tránh sai số nhị phân. Đối với thời gian, kiểm tra timezone và precision trên database đang dùng.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng RowMapper để cố dựng collection từ JOIN một-nhiều | Parent bị lặp theo từng hàng con | Dùng DTO phẳng hoặc ResultSetExtractor để group |
| Không alias cột JOIN | id/status bị trùng tên, đọc nhầm cột | Đặt alias rõ như order_id, customer_id |
| Dùng getLong() cho cột nullable mà không wasNull() | SQL NULL bị hiểu thành 0 | Kiểm tra wasNull() hoặc dùng wrapper qua getObject |
| Dùng INNER JOIN khi muốn giữ parent không có child | Parent không có item bị loại khỏi báo cáo | Dùng LEFT JOIN và xử lý cột con null |
| Đếm COUNT(*) sau LEFT JOIN | Parent không có child vẫn có một hàng join, count có thể là 1 | Dùng COUNT(child.id) |
| Tính tổng sau JOIN nhiều collection độc lập | Hàng bị nhân bản và tổng bị nhân lên | Tổng hợp từng collection trước khi join hoặc dùng subquery/CTE |
| Dùng SELECT * cho DTO | Mapping phụ thuộc thứ tự/tên cột và dễ xung đột | Chọn cột cần thiết và alias rõ |
| Nối input vào SQL | SQL injection | Dùng bind parameter |
| Trả DTO báo cáo như aggregate root | Trộn read model với domain model | Tạo DTO riêng cho use case đọc |
| Nghĩ @Transactional(readOnly = true) là quyền DB chỉ đọc | Đường ghi khác vẫn có thể thực hiện | Dùng quyền database nếu cần bảo vệ |
| Dùng double cho tiền | Sai số số học | Dùng DECIMAL/BigDecimal |

## 19. Bài thực hành

1. Tạo ba bảng customers, sales_orders và order_items với dữ liệu mẫu gồm hai khách hàng, ba đơn hàng và nhiều dòng hàng.
2. Viết SQL JOIN Order với Customer; ánh xạ mỗi hàng thành OrderCustomerRow bằng RowMapper.
3. Viết báo cáo tổng số item và tổng tiền theo Order bằng COUNT, SUM, COALESCE và GROUP BY.
4. Tạo OrderReportRowMapper và gọi truy vấn bằng NamedParameterJdbcTemplate.
5. Thêm một Order chưa có item; xác minh LEFT JOIN giữ Order và tổng tiền bằng 0.
6. Viết query JOIN Order-OrderItem. Trước tiên ánh xạ thành DTO phẳng; sau đó dùng ResultSetExtractor để gom item thành danh sách trong một DTO Order.
7. Tạo một cột nullable từ LEFT JOIN; thử getLong() kết hợp wasNull() và so sánh với getObject(..., Long.class).
8. Thêm phân trang LIMIT/OFFSET và kiểm tra page number, page size, offset được giới hạn.
9. Dùng EXPLAIN để xem index nào hỗ trợ điều kiện JOIN và WHERE.
10. Kiểm tra truy vấn có bind parameter với đầu vào chứa dấu nháy đơn; bảo đảm giá trị không thể thay đổi cấu trúc SQL.

## 20. Ghi nhớ

**RowMapper<T> của Spring JDBC ánh xạ mỗi hàng ResultSet thành một object.** Đây là cách phù hợp để tạo DTO/projection cho kết quả JOIN và báo cáo mà không phải đưa dữ liệu trình bày vào aggregate domain.

Khi một hàng SQL tương ứng một DTO, dùng RowMapper. Khi JOIN một-nhiều khiến parent lặp lại và cần gom nhiều hàng thành một cấu trúc cha-con, dùng ResultSetExtractor hoặc grouping rõ ràng. Luôn alias cột, xử lý SQL NULL, bind tham số, chọn kiểu Java phù hợp và để database thực hiện phép JOIN/tổng hợp. Spring Data JDBC tiếp tục quản lý aggregate qua repository; các query báo cáo tùy chỉnh có thể dùng Spring JDBC với DTO riêng.
