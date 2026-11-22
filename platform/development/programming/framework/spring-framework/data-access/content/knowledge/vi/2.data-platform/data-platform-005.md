# Join, tập kết quả và nguy cơ nhân bản hàng

## 1. Mục tiêu và mô hình tư duy

Khi truy vấn dữ liệu quan hệ, `JOIN` ghép các hàng dựa trên điều kiện liên kết. Một bản ghi nghiệp vụ ở bảng cha **không nhất thiết tương ứng với một hàng kết quả**: nếu bảng con có nhiều hàng phù hợp, các cột của bảng cha được lặp lại trong từng hàng kết quả. Trong tầng truy cập dữ liệu của Spring, việc nhầm **số hàng SQL** với **số đối tượng nghiệp vụ** có thể dẫn đến đếm sai, cộng tiền trùng, trả về DTO trùng lặp, phân trang thiếu phần tử hoặc ánh xạ sai quan hệ.

Sau bài này, bạn cần phân biệt được:

- **Đơn vị của hàng kết quả (row grain)**: mỗi hàng biểu diễn khách hàng, đơn hàng hay dòng hàng?
- **Lực lượng kết quả (cardinality)**: điều kiện `JOIN` có thể tạo bao nhiêu hàng cho một khóa cha?
- **Lặp hợp lệ do quan hệ 1–N** với dữ liệu trùng thật sự cần xử lý.
- **Truy vấn SQL**, **ánh xạ Spring JDBC** và **ORM/JPA**: mỗi tầng xử lý hàng lặp như thế nào?
- Cách dùng `EXISTS`, tổng hợp trước khi nối, ánh xạ theo khóa và phân trang hai bước để trả về đúng đối tượng mong muốn.

Một quy tắc thực dụng: **trước khi viết `JOIN`, hãy hoàn thành câu “mỗi hàng đầu ra đại diện cho một …”**. Nếu câu trả lời là “một dòng hàng”, đừng kỳ vọng mỗi khách hàng chỉ xuất hiện một lần.

## 2. Vì sao `JOIN` có thể nhân bản hàng?

Giả sử có quan hệ:

```text
customer (1) ──── (N) orders (1) ──── (N) order_line
     khách hàng          đơn hàng             dòng hàng
```

- `customer.id` là khóa duy nhất của khách hàng.
- `orders.customer_id` là khóa ngoại: một khách hàng có thể có nhiều đơn.
- `order_line.order_id` là khóa ngoại: một đơn có thể có nhiều dòng.
- Một `JOIN` từ khách hàng sang đơn, rồi sang dòng hàng, tạo **một hàng cho mỗi tổ hợp khóa phù hợp**. Các giá trị `customer.id` và `orders.id` được lặp lại khi cần; đây là hành vi SQL bình thường.

Với `INNER JOIN`, cha không có con phù hợp sẽ bị loại. Với `LEFT JOIN`, cha vẫn xuất hiện ít nhất một lần, các cột thuộc phía không khớp mang `NULL`. Với nhiều nhánh con độc lập, số tổ hợp có thể tăng theo phép nhân: một khách hàng có 2 đơn và 3 địa chỉ có thể tạo 2 × 3 = 6 hàng khi nối cả hai tập con. Đó thường được gọi là **fan-out** hay **row multiplication**.

Điều này khác với **dữ liệu trùng thật** (ví dụ hai hàng mang cùng một khóa chính, điều mà ràng buộc khóa chính phải ngăn). Dù một khách hàng lặp lại nhiều lần trên kết quả `JOIN`, từng hàng có thể vẫn chứa một `order_line.id` khác nhau và hoàn toàn hợp lệ.

## 3. Ví dụ SQL có thể chạy

Ví dụ sau dùng cú pháp SQL phổ biến của PostgreSQL và H2. Chạy lần lượt các câu lệnh trong một cơ sở dữ liệu thử nghiệm.

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    total_amount DECIMAL(12, 2) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, name) VALUES
    (1, 'An'), (2, 'Bình'), (3, 'Chi');

INSERT INTO orders (id, customer_id, total_amount) VALUES
    (10, 1, 120.00),
    (20, 1, 20.00),
    (30, 2, 120.00);

INSERT INTO order_line (id, order_id, amount) VALUES
    (101, 10, 50.00),
    (102, 10, 70.00),
    (103, 20, 20.00),
    (104, 30, 90.00),
    (105, 30, 30.00);
```

Tập dữ liệu gốc có **3 khách hàng, 3 đơn hàng và 5 dòng hàng**. Khách hàng Chi chưa có đơn.

Truy vấn nối cả ba bảng:

```sql
SELECT c.id AS customer_id,
       c.name,
       o.id AS order_id,
       l.id AS line_id,
       l.amount
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l ON l.order_id = o.id
ORDER BY c.id, o.id, l.id;
```

Kết quả theo thứ tự truy vấn:

| customer_id | name | order_id | line_id | amount |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 10 | 101 | 50.00 |
| 1 | An | 10 | 102 | 70.00 |
| 1 | An | 20 | 103 | 20.00 |
| 2 | Bình | 30 | 104 | 90.00 |
| 2 | Bình | 30 | 105 | 30.00 |
| 3 | Chi | NULL | NULL | NULL |

**Đúng 6 hàng**, dù chỉ có 3 khách hàng. Với An, hàng thứ nhất và thứ hai có cùng `customer_id=1` và `order_id=10`, nhưng khác `line_id`. Với Chi, `LEFT JOIN` tạo một hàng có thông tin con bằng `NULL`. Thay cả hai `LEFT JOIN` bằng `INNER JOIN` thì Chi biến mất và kết quả còn 5 hàng.

Nếu nghiệp vụ cần danh sách *dòng hàng đi kèm thông tin khách hàng*, 6 hàng trên là đúng. Nếu nghiệp vụ cần danh sách *khách hàng*, dữ liệu phẳng này cần được truy vấn hoặc ánh xạ khác đi.

## 4. Đếm và tính tổng: phải biết mình đang đếm cái gì

Truy vấn sau đặt bốn phép đếm cạnh nhau để chỉ rõ sự khác biệt:

```sql
SELECT c.id AS customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.id) AS order_references,
       COUNT(DISTINCT o.id) AS distinct_orders,
       COUNT(l.id) AS line_count,
       COALESCE(SUM(l.amount), 0) AS line_amount
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l ON l.order_id = o.id
GROUP BY c.id
ORDER BY c.id;
```

| customer_id | joined_rows | order_references | distinct_orders | line_count | line_amount |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 2 | 3 | 140.00 |
| 2 | 2 | 2 | 1 | 2 | 120.00 |
| 3 | 1 | 0 | 0 | 0 | 0.00 |

- `COUNT(*)` đếm **hàng của kết quả sau JOIN**. Vì `LEFT JOIN` vẫn trả một hàng cho Chi, giá trị là 1 dù Chi chưa có đơn.
- `COUNT(o.id)` chỉ đếm giá trị không `NULL`, nhưng đơn 10 được đếm hai lần vì có hai dòng hàng. Nó **không** cho số đơn duy nhất.
- `COUNT(DISTINCT o.id)` mới là số đơn khác nhau theo khóa đơn trong truy vấn này.
- `COUNT(l.id)` đếm đúng 5 dòng hàng trên toàn bộ dữ liệu mẫu vì mỗi dòng hàng xuất hiện đúng một lần ở truy vấn hiện tại. Nếu nối thêm một bảng con độc lập gây fan-out, con số này cũng có thể bị nhân lên.
- `SUM(l.amount)` cộng đúng các dòng hàng trong ví dụ hiện tại; `COALESCE` biến tổng `NULL` của khách hàng không có dòng thành 0.

Một sai lầm nguy hiểm là cộng tổng của đơn **sau khi đã nối với dòng đơn**:

```sql
-- SAI nếu mục tiêu là tổng giá trị mỗi đơn một lần.
SELECT c.id, SUM(o.total_amount) AS wrong_total
FROM customer AS c
JOIN orders AS o ON o.customer_id = c.id
JOIN order_line AS l ON l.order_id = o.id
GROUP BY c.id
ORDER BY c.id;
```

Với An, đơn 10 có tổng 120 nhưng xuất hiện hai lần, nên phép cộng cho **260 thay vì 140** (`120 + 120 + 20`). Với Bình, đơn 30 cũng xuất hiện hai lần, nên ra **240 thay vì 120**. Đây là lỗi *double counting*, không phải lỗi cú pháp SQL.

Khi muốn tổng tiền theo khách hàng, hãy cộng ở **đơn vị đơn hàng** trước:

```sql
SELECT c.id AS customer_id,
       COALESCE(SUM(o.total_amount), 0) AS correct_total
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
GROUP BY c.id
ORDER BY c.id;
```

Kết quả: An = 140.00, Bình = 120.00, Chi = 0.00. Nếu cần đồng thời nhiều chỉ số ở các đơn vị khác nhau, hãy tổng hợp riêng từng bảng con rồi mới nối các bảng tổng hợp:

```sql
WITH order_stats AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_total
    FROM orders
    GROUP BY customer_id
),
line_stats AS (
    SELECT o.customer_id,
           COUNT(*) AS line_count
    FROM orders AS o
    JOIN order_line AS l ON l.order_id = o.id
    GROUP BY o.customer_id
)
SELECT c.id,
       COALESCE(os.order_count, 0) AS order_count,
       COALESCE(os.order_total, 0) AS order_total,
       COALESCE(ls.line_count, 0) AS line_count
FROM customer AS c
LEFT JOIN order_stats AS os ON os.customer_id = c.id
LEFT JOIN line_stats AS ls ON ls.customer_id = c.id
ORDER BY c.id;
```

Không dùng `SUM(DISTINCT o.total_amount)` để chữa lỗi nhân hàng: hai đơn hợp lệ có thể có **cùng tổng tiền**, khiến phép cộng `DISTINCT` làm mất một đơn.

## 5. Chọn cách truy vấn theo kết quả cần trả

### 5.1. Chỉ cần biết có bản ghi con: `EXISTS`

Nếu câu hỏi là “khách hàng nào đã có ít nhất một đơn?”, không cần tạo tập hàng từ `JOIN`:

```sql
SELECT c.id, c.name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
)
ORDER BY c.id;
```

Trả đúng hai khách hàng An và Bình, mỗi người một hàng. `EXISTS` là phép kiểm tra tồn tại (semi-join về mặt ý nghĩa); nó không nhân số hàng cha theo số đơn phù hợp.

### 5.2. Chỉ cần thông tin cha duy nhất: chiếu đúng cột hoặc nhóm đúng khóa

`SELECT DISTINCT c.id, c.name ... JOIN ...` có thể cho một hàng trên mỗi khách hàng **nếu chỉ chọn các cột của khách hàng**. Nhưng nếu chọn thêm `o.id` hoặc `l.id`, các hàng vẫn khác nhau ở cột con, nên `DISTINCT` không thu gọn về một hàng cho mỗi khách hàng.

`DISTINCT` áp dụng cho **toàn bộ bộ cột được chọn**, không có nghĩa “mỗi khóa cha chỉ giữ một hàng”. Nó cũng không sửa được phép `SUM` đã bị nhân, trừ khi thay đổi thiết kế tính tổng đúng đơn vị.

### 5.3. Điều kiện của `LEFT JOIN`: phân biệt `ON` và `WHERE`

```sql
-- Vẫn giữ khách hàng chưa có dòng hàng > 50;
-- các dòng không đạt điều kiện không được ghép.
SELECT c.id, o.id, l.id
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l
       ON l.order_id = o.id AND l.amount > 50
ORDER BY c.id, o.id, l.id;
```

Nếu chuyển `l.amount > 50` xuống `WHERE`, các hàng có `l.amount IS NULL` sẽ bị loại; khách hàng không có dòng phù hợp có thể biến mất, làm `LEFT JOIN` hoạt động như `INNER JOIN` đối với điều kiện đó. Cần nói rõ mục tiêu: **lọc bản ghi con được ghép** hay **chỉ giữ cha có bản ghi con đạt điều kiện**. Hai mục tiêu tạo kết quả khác nhau.

### 5.4. Phân trang theo đối tượng cha, không theo hàng JOIN

Ví dụ lấy `LIMIT 2` trên tập kết quả 6 hàng ở mục 3 chỉ lấy **hai hàng của An**, không phải hai khách hàng An và Bình. Khi phân trang khách hàng có dữ liệu con, cách thường an toàn là:

1. Trang thứ nhất lấy ID khách hàng theo điều kiện và thứ tự ổn định; sử dụng `LIMIT/OFFSET` hoặc keyset pagination trên **bảng khách hàng**.
2. Truy vấn tiếp các đơn/dòng thuộc **những ID trong trang** (có thể dùng `IN`, truy vấn theo lô hoặc giải pháp tương đương).
3. Nhóm dữ liệu theo khóa cha trong ứng dụng và sắp kết quả lại theo đúng thứ tự trang ban đầu.

Nếu dữ liệu thay đổi giữa hai truy vấn, mức cô lập giao dịch (transaction isolation) và yêu cầu nhất quán của nghiệp vụ cần được cân nhắc. `ORDER BY` phải ổn định, tốt nhất có khóa duy nhất để phá hòa khi sắp xếp.

## 6. Spring JDBC: một hàng `ResultSet` không tự trở thành một đối tượng cha

Trong `JdbcTemplate`, `RowMapper<T>` ánh xạ **mỗi hàng** của `ResultSet` thành một `T`. Nếu SQL ở mục 3 có 6 hàng, `jdbcTemplate.query(sql, rowMapper)` trả về danh sách 6 phần tử (trừ khi bạn tự biến đổi nó sau đó). Viết `RowMapper<Customer>` chỉ đọc `customer_id`/`name` sẽ cho nhiều đối tượng cùng ID. `queryForObject(...)` cũng không phù hợp khi truy vấn trả nhiều hàng: nó đòi hỏi đúng một hàng và có thể ném `IncorrectResultSizeDataAccessException`.

Nếu muốn kết quả dạng `CustomerView -> orders -> lines`, cần **gom theo khóa**. `ResultSetExtractor<T>` thích hợp khi phải đọc toàn bộ `ResultSet` rồi xây cấu trúc nhiều cấp. Ví dụ dưới đây là một lớp dùng trong ứng dụng Spring đã cấu hình `JdbcTemplate` và thư viện `spring-jdbc`; đây không phải chương trình Java độc lập chỉ cần `javac`.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;

public final class CustomerReadService {
    private final JdbcTemplate jdbcTemplate;

    public CustomerReadService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<CustomerView> findAll() {
        String sql = """
            SELECT c.id AS customer_id, c.name,
                   o.id AS order_id,
                   l.id AS line_id, l.amount
            FROM customer c
            LEFT JOIN orders o ON o.customer_id = c.id
            LEFT JOIN order_line l ON l.order_id = o.id
            ORDER BY c.id, o.id, l.id
            """;

        return jdbcTemplate.query(
            sql,
            (ResultSetExtractor<List<CustomerView>>) rs -> {
                Map<Long, CustomerView> customers = new LinkedHashMap<>();
                Map<Long, Map<Long, OrderView>> ordersByCustomer =
                    new LinkedHashMap<>();

                while (rs.next()) {
                    long customerId = rs.getLong("customer_id");

                    CustomerView customer = customers.get(customerId);
                    if (customer == null) {
                        customer = new CustomerView(
                            customerId,
                            rs.getString("name"),
                            new ArrayList<>()
                        );
                        customers.put(customerId, customer);
                    }

                    Long orderId = rs.getObject("order_id", Long.class);
                    if (orderId == null) {
                        continue; // Khách hàng không có đơn.
                    }

                    Map<Long, OrderView> orders = ordersByCustomer
                        .computeIfAbsent(
                            customerId,
                            id -> new LinkedHashMap<>()
                        );

                    OrderView order = orders.get(orderId);
                    if (order == null) {
                        order = new OrderView(orderId, new ArrayList<>());
                        orders.put(orderId, order);
                        customer.orders().add(order);
                    }

                    Long lineId = rs.getObject("line_id", Long.class);
                    if (lineId != null) {
                        order.lines().add(new LineView(
                            lineId, rs.getBigDecimal("amount")
                        ));
                    }
                }

                return new ArrayList<>(customers.values());
            }
        );
    }

    public record CustomerView(
        long id, String name, List<OrderView> orders
    ) {}

    public record OrderView(
        long id, List<LineView> lines
    ) {}

    public record LineView(
        long id, BigDecimal amount
    ) {}
}
```

Đối với dữ liệu mẫu, `findAll()` trả về **3 `CustomerView`**, chứa lần lượt 2, 1 và 0 đơn. Đơn 10 chứa 2 dòng; đơn 20 chứa 1 dòng; đơn 30 chứa 2 dòng. Trong ví dụ này, `LinkedHashMap` giữ thứ tự phát hiện khóa, còn tập lệnh SQL có `ORDER BY` quyết định thứ tự hàng đầu vào.

Ba chi tiết quan trọng khi ánh xạ:

1. **Khóa phải đủ để nhận diện duy nhất.** Gom đơn theo `order_id` và dòng theo `line_id`, không gom theo tên khách hàng hay giá trị tiền. Nếu khóa chỉ duy nhất trong phạm vi một cha, dùng khóa ghép (ví dụ `(orderId, lineNumber)`).
2. **Khóa ngoại bên phải có thể `NULL` khi `LEFT JOIN`.** `getLong()` trả `0` với SQL `NULL` và cần gọi `wasNull()` để phân biệt; ở đây `getObject("order_id", Long.class)` cho phép kiểm tra `null`. Kiểm tra ngay trước khi tạo đối tượng con.
3. **Khi nối thêm các tập con độc lập**, một `line_id` có thể bị lặp trong nhiều hàng tổ hợp. Khi đó ví dụ trên cần thêm tập khóa `line_id` đã thấy cho từng đơn, hoặc tốt hơn, tách các truy vấn để không tạo fan-out. Đừng tùy tiện xóa trùng theo toàn bộ giá trị trường.

Ví dụ sử dụng `List` có thể thay đổi được bên trong `record` để dễ minh họa việc gom. Với DTO trả ra API, có thể tạo bản sao bất biến sau khi gom nhằm tránh thay đổi ngoài ý muốn.

### 6.1. Java 17 độc lập: mô phỏng sự khác nhau giữa số hàng và số đơn

Đoạn sau không cần Spring hay cơ sở dữ liệu; nó mô phỏng các hàng đã JOIN ở mục 3 để kiểm tra việc đếm theo khóa.

Tạo tệp `FanOutDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class FanOutDemo {
    record Row(int customerId, Integer orderId) {}

    public static void main(String[] args) {
        List<Row> resultRows = List.of(
            new Row(1, 10), new Row(1, 10), new Row(1, 20),
            new Row(2, 30), new Row(2, 30), new Row(3, null)
        );

        Map<Integer, Integer> joinedRows = new LinkedHashMap<>();
        Map<Integer, Set<Integer>> uniqueOrders = new LinkedHashMap<>();

        for (Row row : resultRows) {
            joinedRows.merge(row.customerId(), 1, Integer::sum);
            Set<Integer> ids = uniqueOrders.computeIfAbsent(
                row.customerId(), ignored -> new LinkedHashSet<>()
            );
            if (row.orderId() != null) {
                ids.add(row.orderId());
            }
        }

        for (int customerId : joinedRows.keySet()) {
            System.out.printf(
                "customer=%d rows=%d orders=%d%n",
                customerId,
                joinedRows.get(customerId),
                uniqueOrders.get(customerId).size()
            );
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FanOutDemo.java
java FanOutDemo
```

Kết quả chuẩn:

```text
customer=1 rows=3 orders=2
customer=2 rows=2 orders=1
customer=3 rows=1 orders=0
```

Ví dụ này giải thích vì sao **đếm hàng thô** và **đếm khóa đơn duy nhất** cho kết quả khác nhau. Nó chỉ mô phỏng dữ liệu sau truy vấn; trong hệ thống thật, luôn ưu tiên đưa phép lọc, đếm hoặc tổng hợp thích hợp xuống SQL khi có thể để tránh tải thừa dữ liệu.

## 7. JPA/Hibernate: một thực thể có thể xuất hiện trong nhiều hàng SQL

Trong JPA, một câu truy vấn có `JOIN FETCH` trên quan hệ tập hợp có thể tạo nhiều hàng SQL cho cùng một thực thể cha. Chẳng hạn:

```jpql
SELECT o
FROM OrderEntity o
LEFT JOIN FETCH o.lines
WHERE o.customer.id = :customerId
```

Nếu một đơn có hai dòng, SQL thường cần hai hàng để nạp chúng. **Persistence context** bảo đảm một thực thể JPA với cùng danh tính được quản lý như một đối tượng nhất quán trong ngữ cảnh đó; nhưng không vì thế mà có thể đồng nhất số hàng SQL, số tham chiếu trong danh sách kết quả và số thực thể khác nhau ở mọi phiên bản/provider.

Các điểm cần kiểm tra trong ứng dụng thực tế:

- Với **Hibernate 6**, các thực thể cha lặp do `join fetch` thường được tự loại trùng trong bộ nhớ sau khi hiện thực hóa kết quả. Với provider hoặc phiên bản cũ hơn, quy tắc trả danh sách có thể khác; hãy kiểm tra hành vi cụ thể.
- `SELECT DISTINCT o` ở JPQL có thể ảnh hưởng đến danh sách thực thể hoặc SQL được tạo, nhưng **không làm biến mất các tổ hợp hàng SQL cần thiết để lấy dữ liệu con**. Không dùng nó thay cho việc thiết kế đúng truy vấn và phép tổng hợp.
- `JOIN FETCH` tập hợp cùng phân trang (`setFirstResult`/`setMaxResults`, `Pageable`) có thể khiến Hibernate phải phân trang trong bộ nhớ hoặc cảnh báo/báo lỗi tùy cấu hình. Dùng trang ID cha rồi tải dữ liệu liên quan ở bước tiếp theo khi cần phân trang đáng tin cậy.
- Nạp đồng thời nhiều tập hợp một-nhiều có thể tạo tích Descartes lớn. Với Hibernate, fetch đồng thời nhiều **bag** còn có thể gặp `MultipleBagFetchException`. Cân nhắc truy vấn theo lô, `@BatchSize`, hai truy vấn độc lập hoặc DTO projection được nhóm rõ ràng.
- `JOIN FETCH` có thể giải quyết một số trường hợp **N+1 query**, nhưng không đồng nghĩa nó luôn rẻ hơn. Đo cả số truy vấn, số hàng trả về, dữ liệu truyền qua mạng và thời gian ánh xạ.

Phân biệt rõ: **SQL quyết định tập hàng**, **JDBC đọc từng hàng**, còn **ORM quyết định cách tạo và liên kết thực thể** từ những hàng đó. Lỗi có thể xuất hiện ở bất kỳ tầng nào.

## 8. Cách chẩn đoán khi thấy dữ liệu “bị lặp”

Khi một màn hình báo “khách hàng bị nhân đôi” hoặc “tổng tiền tăng bất thường”, kiểm tra theo thứ tự:

1. **Xác định đơn vị mong muốn:** một khách hàng, một đơn, một dòng hàng, hay một cặp khóa? Xem các khóa chính/khóa ngoại và ràng buộc duy nhất thực tế.
2. **Kiểm tra số hàng ở từng bước JOIN:** bắt đầu từ bảng cha, nối từng bảng con một và so sánh `COUNT(*)`, `COUNT(DISTINCT parent.id)`, `COUNT(DISTINCT child.id)`. Không chỉ nhìn những cột tên hiển thị.
3. **Xem dữ liệu ví dụ kèm các khóa:** đưa `customer.id`, `orders.id`, `order_line.id` vào truy vấn tạm để biết hàng nào tạo ra tổ hợp nào.
4. **Kiểm tra `ON`, `WHERE` và loại JOIN:** đặc biệt các điều kiện đặt trong `WHERE` trên bảng nằm bên phải của `LEFT JOIN`.
5. **Kiểm tra phép tổng hợp:** một giá trị tiền thuộc đơn hàng có đang bị cộng lại theo từng dòng hàng? Có nối thêm bảng con khác trước khi `SUM`/`COUNT` không?
6. **Kiểm tra ánh xạ:** `RowMapper` có tạo đối tượng cha cho từng hàng? `ResultSetExtractor`/ORM có gom đúng khóa? Có mất trường hợp cha không có con vì xử lý `NULL` sai?
7. **Kiểm tra phân trang và hiệu năng:** `LIMIT` đang áp lên hàng JOIN hay đối tượng cha? Xem `EXPLAIN`/`EXPLAIN ANALYZE` trong môi trường phù hợp; chỉ số quan trọng là số hàng thực tế đi qua phép nối, không chỉ thời gian một truy vấn nhỏ.

Về thiết kế cơ sở dữ liệu, ràng buộc `PRIMARY KEY`, `FOREIGN KEY` và `UNIQUE` (khi nghiệp vụ yêu cầu) giúp giữ quan hệ đúng. Chỉ mục trên `orders.customer_id` và `order_line.order_id` thường hỗ trợ truy vấn nối, nhưng hiệu quả phụ thuộc bộ dữ liệu và kế hoạch thực thi; **index không sửa được fan-out về mặt ngữ nghĩa**.

## 9. Bài tập tự kiểm tra

**Tình huống A.** Với bảng mẫu, `SELECT COUNT(*)` từ ba bảng bằng `LEFT JOIN` trả bao nhiêu? `COUNT(DISTINCT c.id)` trả bao nhiêu?

**Đáp án:** 6 và 3. Đếm hàng không đồng nghĩa đếm khách hàng.

**Tình huống B.** Vì sao `SUM(o.total_amount)` sau khi nối `order_line` cho An bằng 260? Cách sửa đáng tin là gì?

**Đáp án:** Đơn 10 có hai dòng nên tổng 120 bị cộng hai lần; hãy tổng hợp theo đơn trước, hoặc tính tổng từ `orders` mà không nối `order_line`.

**Tình huống C.** Muốn tìm khách hàng đã đặt hàng mà mỗi khách hàng xuất hiện một lần, có cần `JOIN` rồi `DISTINCT` không?

**Đáp án:** Không bắt buộc. `WHERE EXISTS` trực tiếp thể hiện phép kiểm tra tồn tại và không nhân bản hàng cha.

**Tình huống D.** API trả 20 khách hàng mỗi trang cùng danh sách đơn. Vì sao `LIMIT 20` sau `LEFT JOIN orders` có thể trả ít hơn 20 khách hàng?

**Đáp án:** Giới hạn tác động lên 20 **hàng SQL**, và nhiều hàng có thể thuộc cùng một khách hàng. Hãy phân trang khóa khách hàng trước rồi tải các đơn của trang đó.

## 10. Ghi nhớ

- `JOIN` tạo hàng theo **các tổ hợp khớp điều kiện**, không theo số đối tượng bạn muốn trả cho ứng dụng.
- Một hàng lặp khóa cha có thể là dữ liệu hợp lệ của quan hệ 1–N; hãy nhìn **khóa con** trước khi kết luận bị trùng.
- `COUNT(*)`, `COUNT(child.id)`, `COUNT(DISTINCT child.id)` và `SUM(...)` có ý nghĩa khác nhau sau JOIN. Chọn phép tổng hợp đúng **đơn vị dữ liệu**.
- `EXISTS` cho phép hỏi “có tồn tại không”; tổng hợp trước khi nối giúp tránh cộng trùng; ánh xạ theo khóa giúp xây DTO lồng nhau; phân trang theo khóa cha giúp tránh mất phần tử.
- Trong Spring JDBC, `RowMapper` làm việc theo từng hàng; khi cần một đối tượng cha cùng các tập con, dùng chiến lược gom theo khóa như `ResultSetExtractor` hoặc thiết kế truy vấn phù hợp. Trong JPA/Hibernate, vẫn phải tính đến fan-out SQL, hành vi fetch và phân trang.
