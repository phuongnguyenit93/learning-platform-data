# Lựa chọn giữa tối ưu JPA, native SQL và truy cập JDBC

Trong ứng dụng **Spring Data JPA**, khi một màn hình hoặc tác vụ dữ liệu chạy chậm, có ba hướng thường được cân nhắc: tối ưu truy vấn và cách sử dụng JPA hiện có; viết **native SQL** nhưng vẫn thực thi qua JPA; hoặc dùng **JDBC** trực tiếp (thường thông qua `JdbcTemplate`). Chọn hướng nào phụ thuộc vào nguyên nhân gây chậm, kiểu dữ liệu cần trả về và yêu cầu nhất quán giao dịch — không phải cứ xuống tầng thấp hơn thì sẽ nhanh hơn.

Bài này dùng “tối ưu JPA” để chỉ cải thiện JPQL/Criteria, cách tải quan hệ, projection, phân trang, quản lý persistence context và batching; “native SQL” là câu SQL của cơ sở dữ liệu chạy qua `EntityManager` hoặc `@Query(nativeQuery = true)`; “JDBC” là thao tác với `Connection`/`PreparedStatement`/`ResultSet`, thường được Spring hỗ trợ bằng `JdbcTemplate`. **Cả ba cuối cùng đều gửi SQL đến cơ sở dữ liệu**.

## 1. Chẩn đoán trước khi chọn công cụ

Một API chậm có thể do những nguyên nhân rất khác nhau:

| Dấu hiệu đo được | Hướng kiểm tra trước |
| --- | --- |
| Một request phát sinh hàng trăm câu `SELECT` tương tự | N+1, lazy loading, fetch plan, batch fetching; thường sửa trong JPA |
| Một câu SQL chạy lâu cả khi thực thi trực tiếp tại database | Execution plan, index, lọc, join, thống kê, số hàng quét; đổi sang JDBC vẫn có thể chậm |
| SQL tương đối nhanh nhưng mapping hàng chục nghìn entity, bộ nhớ tăng | Projection, giới hạn số hàng, streaming/DTO, tránh persistence context quá lớn |
| Cần window function, CTE phức tạp, truy vấn phân tích riêng theo DB | Native SQL có thể diễn đạt rõ và dễ tối ưu hơn |
| Cần xuất dữ liệu khối lượng lớn, biến từng dòng thành file/luồng | JDBC với callback hoặc cursor/fetch size có thể giảm chi phí ORM |
| Cập nhật hàng loạt khiến flush/dirty checking tốn thời gian | JDBC batching, JPQL/native bulk DML, điều chỉnh batch/flush trong JPA và đánh giá tính nhất quán |

**Các bước đo tối thiểu**:

1. Xác định *một* tác vụ đại diện, số hàng trả về, số request đồng thời và mục tiêu latency (chẳng hạn p95 của endpoint).
2. Đo thời gian ở ứng dụng, số SQL statement, số row được đọc, lượng dữ liệu chuyển qua mạng, số lần round trip, CPU và bộ nhớ. Phân biệt thời gian chờ connection trong pool với thời gian chạy SQL.
3. Lấy SQL **thực tế** do Hibernate phát ra và kiểm tra query plan tại DB. Ví dụ trong PostgreSQL, với câu `SELECT` an toàn trên dữ liệu thử nghiệm:
   
   ```sql
   EXPLAIN (ANALYZE, BUFFERS)
   SELECT id, total_amount, created_at
   FROM sales_orders
   WHERE status = 'PAID'
   ORDER BY created_at DESC, id DESC
   LIMIT 100;
   ```
   
   `ANALYZE` thực thi câu truy vấn để lấy số đo; các hệ quản trị khác có công cụ và cú pháp riêng. Đọc số hàng thực tế so với ước lượng, index/scan, sort, buffer và tổng thời gian.
4. Chạy benchmark nhiều lần với cùng điều kiện lọc, cùng số hàng/cột, chỉ số index, dữ liệu và mức concurrency; làm nóng hệ thống hợp lý và chú ý cache. So sánh cả độ trễ p50/p95, tải database, CPU, GC, bộ nhớ, chứ không chỉ một lần chạy “nhanh hơn”.
5. Chỉ thay công cụ khi có giả thuyết đo được, ví dụ “90% thời gian nằm ở entity hydration” hoặc “plan SQL cần tính năng mà JPQL khó biểu diễn”.

Đừng dùng “JPA chậm” làm kết luận khi chưa biết SQL, số truy vấn, kích thước tập kết quả và workload.

## 2. Khi nên giữ JPA và tối ưu cách dùng

**JPA thường là lựa chọn mặc định** cho nghiệp vụ cần quan hệ entity, thay đổi trạng thái và dirty checking, lifecycle/cascade, optimistic locking, repository abstraction hoặc tái sử dụng mô hình domain. Nhiều vấn đề hiệu năng có thể giải quyết ngay tại đây.

### 2.1. Giảm N+1 bằng fetch plan phù hợp

Ví dụ lấy 100 `Order`, sau đó truy cập `order.getCustomer().getName()`. Nếu mỗi đơn cần thêm một `SELECT customer`, số round trip có thể tăng mạnh. Các hướng khắc phục:

- `JOIN FETCH` hoặc `@EntityGraph(attributePaths = "customer")` khi biết chắc màn hình sẽ đọc quan hệ `customer`; đặc biệt dễ kiểm soát với quan hệ **to-one**.
- Projection chọn đúng cột/thuộc tính cần hiển thị khi không cần managed entity.
- Batch fetching cho những quan hệ lazy được truy cập theo lô, ví dụ cấu hình Hibernate `hibernate.default_batch_fetch_size` phù hợp với workload.

Không đổi tất cả association thành `EAGER` để “chữa” N+1: việc đó có thể tải quá nhiều dữ liệu, dẫn đến query bổ sung hoặc join không mong muốn. `JOIN FETCH` nhiều collection cùng lúc có thể nhân số hàng do tích Descartes; fetch collection kèm pagination còn dễ gây phân trang trong bộ nhớ hoặc lỗi tùy cấu hình Hibernate. Với màn hình phân trang, thường chọn ID/page trước rồi tải thêm dữ liệu liên quan theo cách có kiểm soát.

### 2.2. Projection và phân trang trước khi bỏ ORM

Khi chỉ cần `id`, `total`, `createdAt`, đừng nạp entity lớn có hàng loạt association nếu không sử dụng. DTO projection trong JPQL giúp giảm số cột và tránh đưa toàn bộ bản ghi vào persistence context dưới dạng entity được quản lý.

- Dùng `Pageable` để giới hạn số hàng; khi chỉ cần danh sách giới hạn và không cần tổng số trang, `List<T>` với `Pageable` có thể tránh count query. `Page<T>` thường cần đếm tổng số hàng; `Slice<T>` phù hợp nếu chỉ cần biết còn trang tiếp theo.
- Với phân trang sâu trên dữ liệu lớn, offset cao có thể tốn chi phí; cân nhắc **keyset pagination** dựa trên cặp khóa sắp xếp ổn định (`created_at, id`) khi phù hợp nghiệp vụ.
- Sắp xếp có tiêu chí phụ độc nhất để tránh thứ tự không ổn định khi nhiều bản ghi trùng timestamp.

### 2.3. Tối ưu ghi và vòng đời persistence context

- Cấu hình `hibernate.jdbc.batch_size` và lựa chọn chiến lược sinh khóa phù hợp có thể giúp gom các câu `INSERT`/`UPDATE`; dùng `GenerationType.IDENTITY` có thể làm Hibernate không batch được insert theo cách thông thường. `saveAll(...)` **không tự bảo đảm** một statement SQL duy nhất.
- Với ghi hàng loạt, chia lô và cân nhắc `flush()`/`clear()` có chủ đích để giới hạn số managed entity. `clear()` làm entity đang quản lý trở thành detached, nên phải xem xét dữ liệu chưa flush và logic nghiệp vụ.
- `@Transactional(readOnly = true)` cung cấp hint tối ưu cho framework/provider trong giao dịch đọc; **không phải** bảo đảm SQL chỉ-đọc hoặc thay thế phân quyền DB.
- Index phù hợp điều kiện `WHERE`, `JOIN`, `ORDER BY`, dữ liệu chọn lọc và thống kê của database thường quan trọng hơn việc dùng JPA hay JDBC. Mọi index mới cũng có chi phí lưu trữ và ghi.

**Dùng JPA đã tối ưu** khi dữ liệu thực sự là entity, cần lifecycle/transaction/locking, câu truy vấn có thể biểu diễn rõ bằng JPQL/Criteria, và số SQL/row/mapping đã ở mức hợp lý.

## 3. Khi nào native SQL qua Spring Data JPA phù hợp?

Native SQL cho phép dùng cú pháp và tính năng của database: CTE, window function (`ROW_NUMBER`, `RANK`), phép toán JSON/array, truy vấn đệ quy, hint, tính năng riêng của PostgreSQL/Oracle/SQL Server, hoặc những phép tổng hợp mà JPQL khó thể hiện.

Spring Data JPA hỗ trợ `@Query(value = "...", nativeQuery = true)` và ở các phiên bản hỗ trợ còn có `@NativeQuery`. Ví dụ:

```java
@Query(
    value = """
        SELECT o.id, o.total_amount
        FROM sales_orders o
        WHERE o.status = :status
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT :limit
        """,
    nativeQuery = true
)
List<Object[]> recentByNativeSql(
        @Param("status") String status,
        @Param("limit") int limit);
```

Đây là **đoạn phương thức repository**, không phải chương trình Java độc lập. `LIMIT` minh họa cú pháp của PostgreSQL; SQL, kiểu tham số và cách ánh xạ kết quả phải tương thích database thật. `Object[]` phù hợp trình diễn ngắn, nhưng với ứng dụng nên ưu tiên projection/DTO có kiểu rõ ràng hoặc result-set mapping.

**Native SQL không tự động bỏ qua JPA.** Nếu truy vấn trả về entity được quản lý, Hibernate vẫn thực hiện mapping và duy trì persistence context. Nếu native query trả scalar/DTO projection thì chi phí quản lý entity có thể giảm, nhưng việc tăng tốc đến từ **SQL và dạng kết quả cụ thể**, không đơn thuần từ cờ `nativeQuery`.

Các đánh đổi cần tính:

- Phụ thuộc schema vật lý, tên bảng/cột và dialect của database; refactor entity không tự sửa chuỗi SQL.
- Native pagination/sorting với câu SQL phức tạp có thể cần `countQuery` do bạn cung cấp và kiểm thử cú pháp thực tế; việc Spring Data tự sửa SQL không xử lý mọi truy vấn.
- Ánh xạ cột sang interface projection/DTO phải rõ ràng, đặc biệt alias và kiểu số/thời gian; entity mapping và scalar mapping không giống nhau.
- Dùng bind parameter thay vì nối chuỗi giá trị nhập. Với tên cột hoặc `ORDER BY` động, chỉ chọn từ whitelist đã kiểm soát; bind parameter không thể thay tên định danh SQL.
- Bulk `UPDATE`/`DELETE` chạy thẳng tại DB có thể làm managed entity trong persistence context bị **cũ**. Cần cân nhắc `flush` trước thao tác và `clear`/`refresh` có chọn lọc sau thao tác, trong đúng ranh giới transaction.

## 4. Khi nào JDBC là lựa chọn hợp lý?

JDBC phù hợp khi bạn muốn **điều khiển SQL, PreparedStatement, ResultSet và cách tiêu thụ từng hàng** mà không cần ánh xạ entity: xuất CSV lớn, ETL, batch thao tác với bảng đơn giản, báo cáo đọc nhiều cột dạng phẳng, hoặc tích hợp SQL do DBA tối ưu.

Trong ứng dụng Spring, `JdbcTemplate`/`NamedParameterJdbcTemplate` thường thuận tiện hơn tự mở/đóng `Connection` vì chúng xử lý tài nguyên, exception translation và tham gia quản lý giao dịch của Spring khi cấu hình đúng. Dùng raw JDBC chỉ khi cần khả năng điều khiển mà các template chưa đáp ứng.

Tuy nhiên, JDBC **không có** dirty checking, lazy loading, association mapping, entity lifecycle hay optimistic-locking tự động theo entity. Bạn phải tự tổ chức SQL, row mapping, locking/version check và ảnh hưởng của thay đổi schema. JDBC cũng **không bảo đảm streaming** chỉ bằng việc gọi callback: driver có thể buffer `ResultSet` nếu fetch size, loại cursor và transaction chưa cấu hình phù hợp.

**Quản lý kết nối và giao dịch:** JPA dùng JDBC bên dưới. Hai lối truy cập có thể cùng tham gia một giao dịch Spring khi cấu hình transaction manager và `DataSource` tương thích (ví dụ `JpaTransactionManager` có quyền truy cập JDBC Connection của cùng DataSource). Không suy đoán rằng dùng chung database đồng nghĩa mặc định dùng chung connection/transaction. Khi kết hợp JPA + JDBC trong một transaction, JPA có thể còn thay đổi **chưa flush** nên câu JDBC chưa nhìn thấy; chiều ngược lại, JDBC cập nhật DB không tự làm managed entity đã nạp được refresh.

## 5. Ví dụ thống nhất: dữ liệu đơn hàng

Giả sử hệ thống PostgreSQL có bảng:

```sql
CREATE TABLE sales_orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at   TIMESTAMP NOT NULL
);
```

`status` có giá trị chuỗi `PAID` hoặc `CANCELLED`. Cột `created_at` dùng `TIMESTAMP` không có timezone trong ví dụ; hệ thống thực phải thống nhất quy ước thời gian. Mô hình rút gọn cho JPA:

```java
// SalesOrder.java — thuộc package com.example.sales
package com.example.sales;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {
    @Id
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal total;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected SalesOrder() {}
}
```

Entity này minh họa **đọc** các trường cần thiết. Với nghiệp vụ tạo/sửa đơn hàng, ứng dụng còn phải thiết kế constructor, phương thức domain, chiến lược ID, version và validation. DTO dùng chung cho projection và JDBC:

```java
// OrderRow.java — package com.example.sales
package com.example.sales;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderRow(
        Long id,
        BigDecimal total,
        LocalDateTime createdAt) {}
```

Các ví dụ Spring phía dưới là **các thành phần tích hợp trong dự án** có Spring Data JPA, Spring JDBC, PostgreSQL driver và schema trên; không thể chạy chỉ bằng `javac` một file mà thiếu dependency, bean, DB và cấu hình kết nối.

### 5.1. Yêu cầu A: màn hình 100 đơn mới nhất — ưu tiên JPA projection

```java
// SalesOrderRepository.java — package com.example.sales
package com.example.sales;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @Query("""
        select new com.example.sales.OrderRow(
            o.id, o.total, o.createdAt)
        from SalesOrder o
        where o.status = :status
          and o.createdAt >= :from
        order by o.createdAt desc, o.id desc
        """)
    List<OrderRow> recentOrders(
            @Param("status") String status,
            @Param("from") LocalDateTime from,
            Pageable pageable);
}
```

Cách gọi trong service đã tiêm `SalesOrderRepository repository`:

```java
var rows = repository.recentOrders(
        "PAID",
        LocalDateTime.of(2026, 1, 1, 0, 0),
        org.springframework.data.domain.PageRequest.of(0, 100));
```

Ưu điểm: JPA chỉ tạo `OrderRow` với ba trường, không nạp nguyên entity và association; `Pageable` giới hạn dữ liệu; logic truy vấn còn được viết bằng thuộc tính entity, dễ bảo trì. Không có lý do phải chuyển sang native SQL/JDBC nếu SQL phát ra có plan tốt và latency đạt mục tiêu.

Trong trường hợp này, có thể xem xét index, ví dụ PostgreSQL:

```sql
CREATE INDEX idx_sales_orders_status_created_id
    ON sales_orders (status, created_at DESC, id DESC);
```

Index chỉ là **ứng viên**: kiểm tra `EXPLAIN` và thực tế đọc/ghi trước khi tạo trên hệ thống đang hoạt động. Nếu truy vấn lấy nhiều phần lớn bảng hoặc bộ lọc ít chọn lọc, DB có thể chọn scan khác hợp lý hơn.

### 5.2. Yêu cầu B: lấy đơn PAID mới nhất của *mỗi khách hàng* — native SQL có lợi thế biểu đạt

Bài toán “mỗi customer chỉ một đơn mới nhất, hòa điểm theo id” được diễn đạt trực tiếp bằng window function:

```java
// LatestOrderRepository.java — package com.example.sales
package com.example.sales;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LatestOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    interface LatestOrderView {
        Long getId();
        Long getCustomerId();
        BigDecimal getTotal();
    }

    @Query(value = """
        WITH ranked AS (
            SELECT o.id, o.customer_id, o.total_amount,
                   ROW_NUMBER() OVER (
                       PARTITION BY o.customer_id
                       ORDER BY o.created_at DESC, o.id DESC
                   ) AS rn
            FROM sales_orders o
            WHERE o.status = :status
        )
        SELECT id AS "id",
               customer_id AS "customerId",
               total_amount AS "total"
        FROM ranked
        WHERE rn = 1
        ORDER BY id
        LIMIT :maxRows
        """, nativeQuery = true)
    List<LatestOrderView> latestByCustomer(
            @Param("status") String status,
            @Param("maxRows") int maxRows);
}
```

Ví dụ gọi `latestByCustomer("PAID", 100)`. `ROW_NUMBER` chọn một hàng trong mỗi `customer_id`; thêm `id DESC` làm tiêu chí phá hòa khi nhiều đơn có cùng `created_at`. `ORDER BY id` ngoài cùng xác định kết quả nào được lấy khi dùng `LIMIT`. Trong PostgreSQL, alias có dấu ngoặc kép `"customerId"` giữ đúng tên thuộc tính cho interface projection.

Điểm mạnh ở đây là **SQL mô tả bài toán rõ ràng**. Không kết luận nó nhanh hơn JPA chỉ vì là native SQL: cần xem số row được xếp hạng, cách dùng index, bộ nhớ sort và kế hoạch thực tế. `LIMIT 100` ở truy vấn ngoài không bảo đảm database chỉ phải đọc 100 hàng bên trong CTE.

### 5.3. Yêu cầu C: xuất rất nhiều đơn PAID — JDBC callback để xử lý từng hàng

`JdbcTemplate` dưới đây dùng `PreparedStatement` có bind parameter, đặt fetch size và gọi `Consumer<OrderRow>` cho từng hàng thay vì tạo một `List<OrderRow>` khổng lồ.

```java
// OrderExportJdbc.java — package com.example.sales
package com.example.sales;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.function.Consumer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OrderExportJdbc {
    private static final String SQL = """
        SELECT id, total_amount, created_at
        FROM sales_orders
        WHERE status = ? AND created_at >= ?
        ORDER BY id
        """;

    private final JdbcTemplate jdbc;

    public OrderExportJdbc(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public void forEachPaidSince(
            LocalDateTime from,
            Consumer<OrderRow> consumer) {

        jdbc.query(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    SQL,
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY);
            ps.setString(1, "PAID");
            ps.setTimestamp(2, Timestamp.valueOf(from));
            ps.setFetchSize(500);
            return ps;
        }, (RowCallbackHandler) rs -> consumer.accept(
                new OrderRow(
                        rs.getLong("id"),
                        rs.getBigDecimal("total_amount"),
                        rs.getTimestamp("created_at")
                                .toLocalDateTime())));
    }
}
```

Ý nghĩa từng điểm:

- `PreparedStatement` bảo đảm dữ liệu `from` đi qua bind parameter; không nối input vào SQL.
- `RowCallbackHandler` cho phép xử lý từng hàng khi JDBC duyệt kết quả. Callback có thể ghi lần lượt vào output stream/file của tầng service; đừng tích lũy các hàng lại trong một list nếu mục tiêu là tiết kiệm bộ nhớ.
- `setFetchSize(500)` là hint đến driver. Với PostgreSQL JDBC, streaming bằng cursor còn phụ thuộc vào cấu hình transaction (đặc biệt auto-commit), chế độ result set và driver; nên đo bộ nhớ thực tế.
- `@Transactional(readOnly = true)` giữ ranh giới thao tác nếu method được gọi qua Spring proxy và transaction manager quản lý đúng `DataSource`. Không giữ transaction/connection quá lâu khi bên nhận dữ liệu rất chậm.
- `ORDER BY id` tạo thứ tự xuất ổn định theo ID; với xuất dữ liệu kéo dài trong lúc bảng thay đổi, còn phải xác định yêu cầu snapshot/isolation hoặc chia batch theo keyset để tránh bỏ/lặp hàng.

Đoạn này **không có entity lifecycle** và không hydrate managed entity. Nhưng số row phải đọc, plan SQL, network I/O và tốc độ ghi output vẫn có thể là nút thắt lớn hơn ORM.

## 6. Bảng quyết định theo tình huống

| Tiêu chí | Tối ưu JPA/JPQL | Native SQL qua JPA | JDBC/JdbcTemplate |
| --- | --- | --- | --- |
| Thích hợp nhất | CRUD, quan hệ domain, DTO list có thể diễn đạt bằng JPQL | SQL phân tích/phức tạp hoặc đặc trưng DB | Report/export/batch phẳng, kiểm soát từng row và statement |
| Quản lý entity và dirty checking | Có khi trả về managed entity; projection DTO không cần entity management cho kết quả | Có khi map entity; ít hơn khi chỉ lấy scalar/DTO | Không |
| Tính gắn với schema DB | Thường ít hơn, do query theo thuộc tính entity | Cao; SQL theo bảng, cột, dialect | Cao; viết SQL và mapper trực tiếp |
| Khả năng tận dụng tính năng SQL riêng | Có giới hạn qua JPQL/Criteria/provider | Rộng | Rộng |
| Kiểm soát fetch/cursor, batch SQL | Qua provider và API JPA/Hibernate | Một phần qua JPA/provider | Trực tiếp qua JDBC/driver/template |
| Rủi ro chính | N+1, over-fetching, collection pagination, persistence context lớn | SQL khó port, mapping/count, đồng bộ persistence context | Mapper thủ công, xử lý transaction/cursor/locking, code SQL nhiều hơn |
| Khuyến nghị | Bắt đầu tại đây nếu phù hợp mô hình | Chọn khi query/plan cần SQL cụ thể | Chọn khi workload cần điều khiển dữ liệu ở mức hàng/batch |

**Quy trình chọn nhanh:**

1. **SQL đã nhanh, chỉ tốn nhiều query?** Sửa fetch plan/N+1 và projection của JPA.
2. **SQL chạy chậm trong database?** Xem execution plan, index, thống kê, dữ liệu và thuật toán SQL trước; native/JDBC chạy *cùng SQL* thường không giải quyết lỗi plan.
3. **Cần truy vấn có window/CTE/dialect-specific?** Dùng native SQL trong repository nếu vẫn muốn Spring Data JPA quản lý boundary và mapping.
4. **Cần duyệt rất nhiều row, batch SQL chuyên biệt, tránh hàng nghìn entity managed?** Cân nhắc JDBC với callback/cursor và transactions đúng.
5. **Có cả CRUD entity và report nặng?** Có thể dùng JPA cho luồng nghiệp vụ, JDBC/native cho điểm nóng đã đo; cần quy định nhất quán dữ liệu giữa hai hướng.

## 7. Những sai lầm dễ mắc

**“Native SQL/JDBC luôn nhanh hơn JPA.”** Sai. Với cùng SQL, cùng kết quả và cùng đường truy cập database, lợi ích có thể nhỏ; đôi khi bạn chỉ chuyển chi phí sang mapper viết tay. So sánh cần giữ công bằng về số hàng, cột, tính năng cache, count query và vòng đời transaction.

**“`JOIN FETCH` tất cả quan hệ sẽ giảm query.”** Có thể giảm round trip nhưng tăng bội số hàng, băng thông và bộ nhớ. Đặc biệt thận trọng với nhiều to-many association và phân trang collection.

**“Chỉ cần dùng `Pageable` thì truy vấn đã tối ưu.”** `Page<T>` có thể cần count; offset sâu có chi phí cao. Cần giới hạn số hàng, index đúng `WHERE`/`ORDER BY` và xem keyset nếu cần.

**“`saveAll` nghĩa là batch SQL.”** Không mặc định. Phải kiểm tra Hibernate batching, strategy ID, transaction/flush và SQL log.

**“Dùng JDBC để update rồi đọc entity JPA ngay sẽ thấy dữ liệu mới.”** Entity đã có trong persistence context có thể trả giá trị cũ; pending changes của JPA cũng có thể chưa được flush khi JDBC chạy. Cần quyết định thứ tự flush, cách refresh/clear và transaction trước khi trộn API. `clear()` làm detach toàn bộ managed entity; không gọi tùy tiện.

**“`setFetchSize` bảo đảm tiết kiệm bộ nhớ.”** Tùy driver và chế độ cursor/transaction. `RowCallbackHandler` không tự ngăn driver buffer mọi row; hãy kiểm chứng bằng dữ liệu đủ lớn và đo heap thực tế.

**“`@Transactional(readOnly = true)` cấm ghi dữ liệu.”** Đây là hint và hành vi cụ thể phụ thuộc transaction manager/provider/database; phân quyền và ranh giới giao dịch phải được thiết kế riêng.

**“Thay giá trị người dùng bằng nối chuỗi vào native SQL là nhanh.”** Nối chuỗi input làm tăng rủi ro SQL injection và khó tái sử dụng query plan. Bind parameter cho giá trị; whitelist riêng cho tên bảng/cột/chiều sắp xếp động.

## 8. Checklist xác nhận hiệu năng sau khi đổi giải pháp

- **Đúng nghiệp vụ:** tập row, duplicate, null, thứ tự khi hòa điểm, phân trang, cập nhật đồng thời và transaction nhất quán.
- **Đúng SQL:** kiểm tra câu SQL phát ra thực tế, bind parameters, số query, DB execution plan, index có được chọn hay không.
- **Đúng tài nguyên:** latency p50/p95, CPU ứng dụng và database, connection-pool wait, heap/GC, lượng row/byte tải về.
- **Đúng vận hành:** load test với độ lớn dữ liệu và mức concurrency thực tế; xem ảnh hưởng lên ghi khi thêm index và thời gian giữ transaction khi streaming.
- **Đúng kiến trúc:** ghi rõ ai sở hữu SQL, mapping DTO, quy định phối hợp EntityManager/JDBC, cách cập nhật test khi schema thay đổi.

Không cần “chọn một công nghệ cho mọi truy vấn”. Trong một module Spring Data JPA, hướng có cơ sở thường là: **sửa SQL/fetch plan/index và giảm dữ liệu dư trong JPA trước; dùng native SQL cho câu truy vấn chuyên biệt; dùng JDBC khi cần điều khiển row/batch ở tầng thấp và đã xác định lợi ích.** Mỗi lựa chọn phải được xác nhận trên workload thật.

### Tài liệu tham khảo

- Spring Data JPA — Query Methods, Native Queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA — Projections: https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html
- Spring Framework — JDBC Core / JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Hibernate ORM — User Guide (fetching, persistence context, batching): https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html
