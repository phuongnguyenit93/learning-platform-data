# Thứ tự kết quả chỉ được bảo đảm khi truy vấn yêu cầu phù hợp

> **Nguyên tắc cốt lõi:** Truy vấn trả về các hàng dữ liệu không mặc nhiên có thứ tự xác định. Nếu ứng dụng cần "mới nhất trước", "giá thấp trước", "theo tên" hoặc phân trang nhất quán, truy vấn phải diễn đạt yêu cầu sắp xếp thích hợp. Với SQL, cơ chế chính là `ORDER BY` ở **truy vấn trả kết quả cuối cùng**; khi nhiều hàng có cùng khóa sắp xếp, cần thêm khóa phụ đủ phân biệt các hàng.

## 1. Vì sao kết quả trông có thứ tự nhưng không được bảo đảm?

Một quan hệ trong mô hình dữ liệu quan hệ không có khái niệm "hàng thứ nhất" hay "hàng thứ 20" nếu chưa đặt ra tiêu chí thứ tự. Với câu SQL không có `ORDER BY`, hệ quản trị cơ sở dữ liệu (DBMS) được phép trả các hàng khớp điều kiện theo thứ tự phụ thuộc vào kế hoạch thực thi.

Một truy vấn có thể **tình cờ** cho kết quả theo `id` tăng dần, theo thời điểm ghi, theo thứ tự trong index hoặc theo vị trí vật lý. Cùng câu truy vấn vẫn có thể đổi thứ tự khi:

- Có index mới hoặc thay đổi thống kê khiến optimizer đổi kế hoạch đọc bảng.
- DBMS chuyển giữa quét bảng, quét index, join theo hash/merge/nested loop hoặc thực thi song song.
- Dữ liệu được thêm, xóa, cập nhật hay tổ chức lại.
- Truy vấn thêm `LIMIT`/`OFFSET`, thay đổi bộ lọc hoặc thay đổi phiên bản/cấu hình DBMS.

**Không được suy ra thứ tự từ** khóa chính, thứ tự `INSERT`, clustered index, `GROUP BY`, `DISTINCT`, vị trí vật lý, hoặc việc lần chạy trước "luôn đúng". Index có thể hỗ trợ hiệu năng sắp xếp, nhưng riêng sự tồn tại của index không tạo hợp đồng thứ tự cho kết quả truy vấn.

Trong ứng dụng Spring, `JdbcTemplate` và các thành phần ánh xạ dữ liệu đọc những hàng mà DBMS trả về. Chúng không tự biến một truy vấn SQL thiếu `ORDER BY` thành truy vấn có thứ tự nghiệp vụ. Một `List` có thứ tự phần tử theo lần đọc hiện tại **không có nghĩa** thứ tự đó đã được DBMS cam kết cho những lần truy vấn tiếp theo.

## 2. Minh họa bằng dữ liệu cụ thể

Ví dụ sử dụng cú pháp PostgreSQL; phần `LIMIT`, `NULLS LAST` và so sánh bộ giá trị ở các mục sau có thể cần điều chỉnh cho cơ sở dữ liệu khác.

```sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO orders (id, customer_id, created_at, total_amount) VALUES
    (101, 7, '2026-10-28 09:00:00', 100.00),
    (102, 7, '2026-10-29 08:00:00', 130.00),
    (103, 7, '2026-10-29 08:00:00', 150.00),
    (104, 7, '2026-10-30 12:00:00', 170.00),
    (105, 7, '2026-10-30 12:00:00', 190.00),
    (201, 8, '2026-10-30 12:00:00', 210.00);
```

### Trường hợp A: Không yêu cầu sắp xếp

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7;
```

Tập kết quả gồm năm hàng có `id` 101–105, nhưng **không có cam kết** rằng hàng 101 đứng đầu hoặc 105 đứng cuối. Một thứ tự quan sát được ở môi trường hiện tại không phải điều kiện có thể đưa vào mã, test hay hợp đồng API.

### Trường hợp B: Có `ORDER BY` nhưng còn các giá trị bằng nhau

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC;
```

Kết quả được sắp giảm dần theo `created_at`, nhưng cặp 104/105 cùng thời điểm và cặp 102/103 cùng thời điểm. DBMS có thể trả 104 trước 105 hoặc ngược lại mà vẫn tuân thủ hoàn toàn câu `ORDER BY`. **Sắp xếp theo một khóa không duy nhất chưa tạo thứ tự toàn phần.**

### Trường hợp C: Sắp xếp đủ khóa để phân biệt các hàng

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC;
```

Trên tập dữ liệu trên, thứ tự `id` được xác định là **105, 104, 103, 102, 101**. DBMS so sánh `created_at` trước; chỉ khi bằng nhau mới so sánh `id`. Vì `id` là khóa chính duy nhất và không `NULL`, hai hàng khác nhau không thể hòa nhau ở cả hai tiêu chí. Đây là thứ tự xác định **cho cùng trạng thái dữ liệu và cùng ngữ nghĩa so sánh**.

Khi chỉ muốn ba đơn hàng mới nhất:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 3;
```

Kết quả theo thứ tự là **105, 104, 103**. Đặt `LIMIT 3` mà không có `ORDER BY` phù hợp chỉ có nghĩa "lấy tối đa ba hàng bất kỳ thỏa điều kiện", không phải "ba hàng mới nhất".

## 3. Một `ORDER BY` "phù hợp" cần những gì?

1. **Đúng ý nghĩa nghiệp vụ.** "Mới nhất" thường là `created_at DESC`; "giá thấp nhất" là `total_amount ASC`; "tên A–Z" cần xét quy tắc so sánh chữ/collation. Không tự dùng `id DESC` như từ đồng nghĩa với "mới nhất" nếu ID không bảo đảm phản ánh thời gian nghiệp vụ.
2. **Đúng phạm vi kết quả.** Đặt `ORDER BY` ở truy vấn cấp ngoài tạo ra tập hàng ứng dụng nhận; chỉ sắp xếp trong một subquery/CTE không tự bảo đảm thứ tự của kết quả ngoài.
3. **Có khóa phụ khi cần ổn định tuyệt đối.** Nếu sắp xếp theo `created_at`, `score` hoặc `status` có thể trùng, thêm khóa duy nhất như `id`. Tập khóa nên tạo được thứ tự toàn phần trên các hàng được trả về.
4. **Chỉ rõ chiều sắp xếp.** `ASC` là tăng dần, `DESC` là giảm dần; có thể kết hợp nhiều chiều: `ORDER BY priority DESC, created_at ASC, id ASC`.
5. **Xử lý `NULL`, chữ hoa/thường, dấu và collation theo DBMS.** Vị trí `NULL` và cách so sánh chuỗi có khác biệt giữa hệ quản trị, cấu hình locale và collation. Nếu đó là hợp đồng API, phải thiết kế và kiểm thử cụ thể.

Ví dụ PostgreSQL khi cho phép `created_at` rỗng:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC NULLS LAST, id DESC;
```

`NULLS LAST` làm rõ vị trí giá trị `NULL` trong PostgreSQL; **không sao chép nguyên xi** sang DBMS chưa hỗ trợ cú pháp này. Với so sánh tên tiếng Việt, cần kiểm tra collation đang dùng; `ORDER BY name` không mặc nhiên mang đúng thứ tự từ điển mà sản phẩm mong muốn.

Lưu ý `ORDER BY` quyết định **thứ tự của các hàng**. Nó không bảo đảm thứ tự phần tử bên trong một cột kiểu mảng/JSON đã được tổng hợp, hoặc thứ tự phần tử trong một collection ORM được nạp riêng; các cấu trúc đó có cơ chế định thứ tự riêng.

## 4. Các cấu trúc SQL dễ gây hiểu nhầm

| Cấu trúc | Điều thực sự được bảo đảm |
| --- | --- |
| `SELECT ... WHERE ...` không có `ORDER BY` | Chỉ điều kiện lọc; thứ tự các hàng không xác định. |
| `ORDER BY created_at DESC` | Thứ tự giảm dần theo thời điểm; các hàng trùng thời điểm vẫn có thể đổi chỗ. |
| `ORDER BY created_at DESC, id DESC` với `id` duy nhất | Thứ tự toàn phần trên trạng thái dữ liệu đang truy vấn. |
| `LIMIT n` hoặc `OFFSET m` không có sắp xếp đủ rõ | Chọn/cắt trên một thứ tự không được bảo đảm; không đại diện ổn định cho "top n" hay "trang m". |
| `GROUP BY`, `DISTINCT`, `UNION` | Nhóm, loại trùng hoặc kết hợp dữ liệu; không mặc nhiên xếp kết quả cuối theo khóa. |
| `JOIN`, index, khóa chính | Có thể ảnh hưởng cách truy xuất nhưng không thay thế `ORDER BY` ngoài cùng. |
| `ORDER BY` nằm trong subquery | Có thể phục vụ logic cục bộ, nhưng truy vấn bên ngoài muốn bảo đảm thứ tự vẫn phải nêu `ORDER BY` riêng. |
| Sắp xếp `List` sau khi truy vấn | Chỉ sắp xếp tập dữ liệu đã tải vào Java; không bảo đảm chọn đúng top N/trang N từ DB. |

Với truy vấn tổng hợp, có thể yêu cầu thứ tự rõ ràng ở cấp ngoài:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC, customer_id ASC;
```

Dữ liệu ví dụ trả về khách 7 (5 đơn) trước khách 8 (1 đơn). Thứ tự này đến từ `ORDER BY`, **không phải** từ `GROUP BY`.

## 5. Trong Spring Framework JDBC: SQL phải phát biểu thứ tự

`JdbcTemplate` nhận SQL, thực thi qua JDBC, rồi áp dụng `RowMapper` cho từng hàng theo trình tự `ResultSet` mà driver cung cấp. Nó không tự thêm một tiêu chí sắp xếp nghiệp vụ.

Ví dụ dưới đây là tệp `OrderReader.java` dùng trong **dự án Java 17+ đã có Spring JDBC và một `JdbcTemplate` được cấu hình** (chẳng hạn ứng dụng Spring Boot có JDBC starter và `DataSource`). Đây là lớp truy cập dữ liệu để tích hợp vào dự án, không phải chương trình `main` độc lập chạy bằng `javac` thuần.

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReader {
    private final JdbcTemplate jdbcTemplate;

    public OrderReader(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderRow> newestForCustomer(long customerId, int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }

        String sql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        return jdbcTemplate.query(
            sql,
            (rs, rowNum) -> new OrderRow(
                rs.getLong("id"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getBigDecimal("total_amount")
            ),
            customerId,
            limit
        );
    }
}

record OrderRow(long id, LocalDateTime createdAt, BigDecimal totalAmount) {}
```

Điểm cần đọc đúng:

- `WHERE customer_id = ?` và `LIMIT ?` dùng tham số bind, không ghép trực tiếp giá trị người dùng vào SQL; `LIMIT ?` được PostgreSQL hỗ trợ trong ngữ cảnh này.
- `ORDER BY created_at DESC, id DESC` mới là yêu cầu thứ tự. `RowMapper` chỉ chuyển từng hàng thành `OrderRow`; danh sách trả về giữ trình tự đọc từ `ResultSet`.
- Nếu gọi `newestForCustomer(7, 3)` trên dữ liệu ví dụ và không có thay đổi đồng thời, danh sách có `id` **105, 104, 103** theo đúng thứ tự. Đây là kết quả suy ra từ dữ liệu và SQL đã cho, không phải stdout của một chương trình độc lập.
- Với hệ quản trị khác PostgreSQL, điều chỉnh cú pháp giới hạn số hàng theo dialect. Nếu chỉ cần một hàng, vẫn phải định nghĩa tiêu chí "đầu tiên" trước khi chọn nó.

Có thể dùng `NamedParameterJdbcTemplate` hoặc `JdbcClient` để viết truy vấn thuận tiện hơn; nguyên tắc không thay đổi: **SQL gửi xuống DB phải chứa thứ tự cần thiết**. Nếu đọc bằng `ResultSetExtractor` tự tạo collection không giữ thứ tự (ví dụ `HashSet`), thứ tự cũng có thể bị mất trong Java dù SQL đúng.

## 6. Với Spring Data JPA: yêu cầu sort ở Repository/query

Spring Data JPA là thành phần thuộc hệ Spring Data, **không phải API tự có của Spring JDBC**. Khi dự án sử dụng JPA repository, thứ tự có thể được khai báo bằng phương thức truy vấn, `Sort`, `Pageable` hoặc JPQL `ORDER BY`.

Ví dụ minh họa tích hợp trong ứng dụng đã có entity `OrderEntity` với các thuộc tính `customerId`, `createdAt` và `id`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    Page<OrderEntity> findByCustomerId(long customerId, Pageable pageable);
}

// Trong service có biến repository kiểu OrderRepository:
Sort ordering = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Page<OrderEntity> page0 = repository.findByCustomerId(
    7L,
    PageRequest.of(0, 20, ordering)
);
```

Đoạn `PageRequest` là mã sử dụng **bên trong method của service** (không phải các câu lệnh đứng tự do ngoài lớp Java); muốn biên dịch phải có `OrderEntity` và Spring Data JPA thực tế. `createdAt` là **tên thuộc tính Java của entity**, không nhất thiết là tên cột SQL `created_at`.

Tương tự, có thể định nghĩa phương thức có thứ tự tĩnh nếu hợp đồng nghiệp vụ cố định:

```java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    List<OrderEntity> findByCustomerIdOrderByCreatedAtDescIdDesc(
        long customerId
    );
}
```

Nếu viết truy vấn bằng `@Query`/JPQL, phải xem rõ `ORDER BY` được cung cấp tĩnh hay kết hợp với `Sort` động; không giả định mọi dạng native SQL hoặc truy vấn tùy chỉnh đều hỗ trợ gắn `Sort` theo cùng một cách. Khi cho phép client chọn cách sắp xếp, chỉ chấp nhận danh sách thuộc tính đã phê duyệt, ví dụ `createdAt` hoặc `totalAmount`, và vẫn bổ sung khóa định danh cần thiết. Không chèn nguyên văn tham số `sort` của người dùng vào chuỗi `ORDER BY`.

**Phân biệt quan trọng:** `findAll()` hoặc `findByCustomerId(...)` không kèm định nghĩa sort không cho phép ứng dụng giả định thứ tự. `PageRequest.of(page, size)` chỉ chỉ định phần trang; muốn thứ tự có ý nghĩa cần cung cấp `Sort` phù hợp.

## 7. Phân trang: ổn định thứ tự chưa đồng nghĩa bất biến giữa các lần gọi

### 7.1. Offset pagination

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 0;
```

Trang đầu trong dữ liệu ví dụ là 105, 104. Trang sau:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
```

Là 103, 102 **nếu dữ liệu không thay đổi giữa hai truy vấn**. Dù đã dùng thứ tự toàn phần, khi một đơn hàng mới được thêm hoặc một hàng trước đó bị xóa trong khoảng giữa hai yêu cầu, vị trí `OFFSET` có thể dịch chuyển: người dùng nhìn thấy bản ghi lặp hoặc bỏ sót. Điều này không mâu thuẫn với `ORDER BY`; mỗi truy vấn chỉ cam kết thứ tự trên tập hàng mà nó thấy tại thời điểm thực thi và theo mức cô lập giao dịch.

### 7.2. Keyset/cursor pagination cho luồng "xem thêm"

Với thứ tự `created_at DESC, id DESC`, để lấy trang tiếp theo sau hàng cuối của trang trước, dùng khóa của hàng cuối làm cursor. Giả sử hàng cuối trang đầu là `(created_at='2026-10-30 12:00:00', id=104)`:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
  AND (created_at, id) < (TIMESTAMP '2026-10-30 12:00:00', 104)
ORDER BY created_at DESC, id DESC
LIMIT 2;
```

Trong PostgreSQL, phép so sánh tuple theo thứ tự từ trái sang phải; với hai khóa đều `DESC` và không `NULL`, điều kiện `<` này đi tới những bản ghi **sau cursor**. Kết quả trên dữ liệu ví dụ là **103, 102**. Ở hệ quản trị không hỗ trợ so sánh tuple, có thể viết điều kiện tương đương:

```sql
AND (
    created_at < :cursorTime
    OR (created_at = :cursorTime AND id < :cursorId)
)
```

Phần `AND (...)` trên chỉ là **mảnh điều kiện WHERE để chèn vào truy vấn đầy đủ**, với `:cursorTime` và `:cursorId` là tham số được bind bằng `NamedParameterJdbcTemplate` hoặc cơ chế tương đương; không phải câu SQL độc lập.

Cursor dựa trên khóa toàn phần, không rỗng và tương đối bất biến giúp giảm tác động của dữ liệu mới chèn *trước* vị trí cursor và tránh chi phí quét qua offset lớn. Nhưng cursor **không tạo snapshot cố định**: nếu hàng chưa đọc bị xóa hay thay đổi khóa sắp xếp, tập trang sau vẫn có thể khác. Nếu yêu cầu chính xác một ảnh chụp dữ liệu qua nhiều trang, cần thiết kế thêm transaction/snapshot hoặc cơ chế phiên bản tùy DBMS.

### 7.3. Chọn chiến lược

- **Offset/page number**: phù hợp danh sách nhỏ, nhu cầu "trang 5", dữ liệu thay đổi ít; vẫn phải dùng sort đủ khóa.
- **Keyset/cursor**: hợp lý cho "xem thêm", feed lớn, lặp truy vấn theo một thứ tự cố định; cần cursor chứa mọi khóa sort và điều kiện so sánh đúng chiều.
- **Snapshot/phiên bản dữ liệu**: cần thiết khi nghiệp vụ đòi hỏi cùng một tập dữ liệu không thay đổi giữa nhiều lần đọc (ví dụ xuất báo cáo đối soát).

Không nên lấy dữ liệu từ DB bằng `LIMIT/OFFSET` **rồi mới** gọi `list.sort(...)` để "sửa" thứ tự toàn cục: lúc đó DB đã chọn sai tập hàng cho trang hoặc top N trước khi Java sắp xếp cục bộ.

## 8. Tương tác giữa thứ tự, hiệu năng và xử lý Java

`ORDER BY` có thể yêu cầu DBMS sắp xếp nhiều hàng; index phù hợp đôi khi giúp DBMS đọc trực tiếp theo thứ tự hoặc giảm chi phí. Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_orders_customer_newest
    ON orders (customer_id, created_at DESC, id DESC);
```

Index này có thể hỗ trợ truy vấn lọc theo `customer_id` và lấy đơn mới trước. Tuy nhiên, lợi ích cụ thể phụ thuộc kích thước bảng, tỷ lệ lọc, thống kê và kế hoạch thực thi. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường kiểm thử phù hợp để đánh giá; **không bỏ `ORDER BY` vì thấy index đã "có thứ tự"**.

Sau khi nhận kết quả, các bước chuyển đổi Java cũng phải giữ trật tự mong muốn:

- `List` và một luồng tuần tự có thứ tự nguồn có thể giữ trình tự nếu phép xử lý không làm thay đổi encounter order.
- Gom vào `HashSet`/`HashMap` hoặc dùng cấu trúc/thuật toán không cam kết thứ tự có thể làm mất thứ tự.
- Sắp xếp lại trên UI là một yêu cầu khác với bảo đảm **chọn đúng** các hàng từ DB. UI chỉ sắp xếp những gì nó đã nhận, không thể tự khôi phục hàng thuộc một trang đã bị DB cắt bỏ.

Nên phát biểu rõ quy tắc ở tầng API, chẳng hạn: "Danh sách đơn hàng trả về theo `createdAt` giảm dần, rồi `id` giảm dần." Khi API cho đổi thứ tự, tên field, chiều sort, xử lý đồng hạng và độ ổn định khi phân trang đều là một phần hợp đồng cần kiểm thử.

## 9. Cách kiểm thử đúng

Đừng viết test kiểu "chạy truy vấn thiếu `ORDER BY` mười lần vẫn ra đúng thứ tự, vậy đã ổn": những lần chạy đó có thể tình cờ dùng cùng kế hoạch.

Thay vào đó:

1. Tạo dữ liệu **chèn không theo thứ tự ID/thời gian** và có ít nhất hai hàng trùng giá trị ở khóa sort chính.
2. Gọi đúng truy vấn, kiểm tra danh sách ID theo thứ tự đã định nghĩa, không chỉ kiểm tra số lượng hoặc tập phần tử.
3. Kiểm tra `LIMIT`, trang đầu, trang cuối và các hàng đồng hạng ngay ranh giới trang.
4. Kiểm tra quy ước `NULL`/collation nếu nghiệp vụ có sử dụng.
5. Với phân trang nhiều lần gọi, test rõ hành vi mong muốn khi có insert/delete/update giữa các trang; không nhầm thứ tự nhất quán trong một query với snapshot bất biến.

Ví dụ trên dữ liệu ở mục 2, các khẳng định mong đợi khi truy vấn không bị cập nhật đồng thời:

| Truy vấn | Danh sách `id` mong đợi |
| --- | --- |
| `ORDER BY created_at DESC, id DESC` | `[105, 104, 103, 102, 101]` |
| Cùng thứ tự với `LIMIT 3` | `[105, 104, 103]` |
| Cùng thứ tự với `LIMIT 2 OFFSET 2` | `[103, 102]` |
| Không `ORDER BY` | **Không viết expected order cố định** |

## 10. Những lỗi cần tránh và cách sửa

- **"Có primary key nên `findAll()` sẽ tăng dần theo ID."** Sai: phải yêu cầu `ORDER BY id ASC` hoặc `Sort.by("id")`.
- **"Đã `ORDER BY created_at` nên hai bản ghi cùng timestamp luôn có thứ tự cố định."** Sai: bổ sung khóa duy nhất như `id`.
- **"`GROUP BY` hoặc `DISTINCT` đã gom/sắp xếp rồi."** Sai: thêm `ORDER BY` ở truy vấn trả kết quả.
- **"`LIMIT 10` nghĩa là lấy 10 bản ghi mới nhất."** Sai: cần định nghĩa "mới nhất" và sắp xếp trước khi giới hạn.
- **"`Pageable` tự bảo đảm phân trang ổn định."** Sai: cần `Sort` đủ khóa, và phải xét thay đổi dữ liệu giữa các request.
- **"Sắp xếp `List` sau khi lấy một trang là đủ."** Sai: DB phải chọn đúng các hàng theo thứ tự toàn cục trước khi cắt trang.
- **"Có index phù hợp nên xóa `ORDER BY` để tăng tốc."** Sai: index là tối ưu thực thi, không thay thế hợp đồng thứ tự.
- **"Mọi DB đều xử lý `NULL` và collation giống nhau."** Sai: xác định rõ theo DBMS/locale và kiểm thử.

## 11. Tự kiểm tra

**Câu 1.** Truy vấn `SELECT id FROM orders WHERE customer_id = 7 LIMIT 2` có bảo đảm lấy hai ID nhỏ nhất không?

**Đáp án:** Không. Thiếu `ORDER BY` nên không có tiêu chí nào chỉ ra "nhỏ nhất". Muốn vậy phải dùng `ORDER BY id ASC LIMIT 2`.

**Câu 2.** `ORDER BY created_at DESC` có đủ để phân trang ổn định khi nhiều đơn hàng tạo trong cùng một giây không?

**Đáp án:** Chưa đủ. Các đơn có cùng timestamp có thể đổi chỗ; thêm khóa duy nhất như `id DESC`. Vẫn phải xét tác động insert/delete giữa các trang khi dùng offset.

**Câu 3.** Khi đang lấy trang theo `created_at DESC, id DESC` và cursor cuối cùng là `(t, 104)`, điều kiện cho trang sau trong PostgreSQL là gì nếu hai cột không rỗng?

**Đáp án:** `(created_at, id) < (t, 104)`, giữ cùng `ORDER BY created_at DESC, id DESC`; `t` phải được bind bằng giá trị thời gian thực của bản ghi cuối. Với chiều sort khác, phải thiết kế lại phép so sánh.

**Câu 4.** Tại sao một test chỉ so sánh `Set` ID không chứng minh được thứ tự?

**Đáp án:** `Set` bỏ qua thứ tự. Phải kiểm tra chuỗi ID theo thứ tự trong `List` nhận từ truy vấn, nhất là khi có các giá trị sort trùng nhau.

## Tài liệu tham khảo

- [PostgreSQL — Sorting Rows (`ORDER BY`)](https://www.postgresql.org/docs/current/queries-order.html): thứ tự không được chỉ định, sắp xếp nhiều khóa và xử lý giá trị bằng nhau.
- [PostgreSQL — `LIMIT` và `OFFSET`](https://www.postgresql.org/docs/current/queries-limit.html): giới hạn/trang và yêu cầu thứ tự có tính dự đoán.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): sử dụng `Sort`, `PageRequest`, giới hạn và lưu ý về phương thức truy vấn.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): truy vấn SQL với `JdbcTemplate` và ánh xạ `RowMapper`.

**Ghi nhớ:** DBMS chỉ phải trả kết quả theo thứ tự mà truy vấn đã yêu cầu; muốn kết quả có thể dự đoán, cần đúng tiêu chí nghiệp vụ, `ORDER BY` ở cấp truy vấn trả về, và khóa phụ đủ phân biệt các hàng khi cần. Với phân trang, còn phải xác định cách xử lý dữ liệu thay đổi giữa các lần gọi.