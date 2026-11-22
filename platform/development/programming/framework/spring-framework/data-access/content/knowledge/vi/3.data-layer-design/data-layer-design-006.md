# Quy định kết quả không có dữ liệu, nhiều dữ liệu và lỗi trong tầng dữ liệu Spring

## 1. Vì sao phải quy định trước khi viết repository?

Một lời gọi tầng dữ liệu không chỉ “trả ra dữ liệu”. Nó còn mang **hợp đồng kết quả**: có thể không tìm thấy bản ghi, tìm thấy đúng một, tìm thấy nhiều, lấy lượng dữ liệu quá lớn, hoặc thất bại khi truy cập cơ sở dữ liệu. Nếu không quy định rõ từng trường hợp, hai lập trình viên có thể viết hai phương thức cùng tên nhưng một bên trả `null`, một bên trả danh sách rỗng, bên khác bắt mọi lỗi rồi trả `Optional.empty()`. Hậu quả là service không phân biệt được “không tồn tại” với “DB đang lỗi”, API trả sai mã HTTP, dữ liệu sai bị che giấu và vận hành khó chẩn đoán.

Bài này thuộc **Thiết kế tầng dữ liệu** trong Spring Framework. Mục tiêu là thiết kế **contract rõ ràng cho 0, 1, nhiều kết quả và lỗi**, áp dụng nhất quán với JDBC/`JdbcClient`, Spring Data JPA và R2DBC. “Nhiều dữ liệu” được xét ở **hai nghĩa khác nhau**:
- **Nhiều hàng kết quả** (`0/1/N`): cần quyết định danh sách nhiều kết quả có hợp lệ không, hay là vi phạm ràng buộc duy nhất.
- **Tập kết quả lớn**: cần phân trang, giới hạn, sắp xếp ổn định, streaming theo điều kiện, và bảo vệ bộ nhớ/tài nguyên.

Một quy ước tốt trả lời được bốn câu hỏi trước khi thực thi truy vấn: **Bao nhiêu bản ghi được phép trả về? Nếu không có bản ghi thì sao? Nếu thực tế có nhiều hơn dự kiến thì sao? Nếu hệ thống truy cập dữ liệu lỗi thì tầng nào chịu trách nhiệm diễn giải?**

## 2. Ma trận hợp đồng: 0, 1, N và lỗi

| Dạng truy vấn | 0 hàng | 1 hàng | N hàng (N > 1) | Kiểu kết quả khuyến nghị |
|---|---|---|---|---|
| Tra cứu **có thể vắng mặt** theo khóa duy nhất | Kết quả vắng mặt, bình thường | Trả bản ghi | **Lỗi dữ liệu/hợp đồng**, không chọn đại | `Optional<T>` / reactive `Mono<T>` |
| Tra cứu **bắt buộc có** trong một thao tác nghiệp vụ | Báo lỗi miền `NotFound` | Trả bản ghi | Lỗi dữ liệu/hợp đồng | Giá trị `T` hoặc exception miền |
| Tìm kiếm/danh sách theo bộ lọc | Danh sách rỗng | Danh sách một phần tử | Danh sách nhiều phần tử, **có giới hạn** | `List<T>`, `Slice<T>`, `Page<T>`, `Flux<T>` |
| Đếm bản ghi với `COUNT(*)` | **Một hàng số 0** | Một hàng số 1 | Vẫn **một hàng** chứa số N | `long`/`Long` |
| Cập nhật/xóa dự kiến đúng một bản ghi | `affectedRows = 0`: cần diễn giải theo hợp đồng | `affectedRows = 1`: thành công | `affectedRows > 1`: bất thường nếu kỳ vọng đúng một | `int`/`long` rồi kiểm tra số hàng |
| Lỗi SQL, timeout, mất kết nối, constraint | **Không phải “không có dữ liệu”** | **Không phải thành công** | **Không phải danh sách rỗng** | Exception có phân loại, log/trace, retry có điều kiện |

**Không tồn tại** là một *kết quả nghiệp vụ hợp lệ* đối với lookup tùy chọn, nhưng có thể là lỗi nghiệp vụ đối với lệnh yêu cầu tài nguyên phải có. **Truy cập dữ liệu thất bại** là một *lỗi thực thi*, không thể suy ra rằng kết quả thực sự rỗng. Quy định này phải nằm trong tên phương thức, kiểu trả về, tài liệu và test.

### Ví dụ về khác biệt ý nghĩa

- `findById(42)` dùng để hiện nút “xem chi tiết”: `Optional.empty()` là kết quả lookup bình thường; controller có thể chuyển thành HTTP 404.
- `findOrdersForCustomer(42)` dùng để hiển thị danh sách: không có đơn nào thường là `[]` và HTTP 200, không phải 404.
- `findByExternalCode("ORD-42")` trong bảng có `UNIQUE(external_code)`: có hai hàng là **vi phạm dữ liệu hoặc truy vấn**, không được im lặng lấy hàng đầu.
- `searchOrders(page, size)`: kết quả không có hàng ở trang sau thường là danh sách rỗng, nhưng cần xác nhận page vượt phạm vi có được phép hay báo 400 tùy contract API.
- `countOrders()` với không có đơn: `COUNT(*)` vẫn trả một hàng, giá trị `0`. Ngược lại `SUM(amount)` có thể trả một hàng có giá trị `NULL`; phải phân biệt “không có hàng” với “có hàng nhưng cột NULL”.

## 3. Thiết kế giao diện truy cập dữ liệu theo ý nghĩa

Hãy ưu tiên tên hàm nói lên **cardinality** và yêu cầu nghiệp vụ:

```java
// Mã thiết kế interface trong một dự án Java 17+.
package example.orders;

import java.util.List;
import java.util.Optional;

public interface OrderReadPort {
    Optional<OrderView> findByExternalCode(String code);

    List<OrderView> findRecentByCustomer(long customerId, int limit);

    long countByCustomer(long customerId);
}
```

`findByExternalCode` chỉ có nghĩa 0 hoặc 1: dữ liệu có nhiều bản ghi cùng mã là lỗi. `findRecentByCustomer` chấp nhận nhiều bản ghi nhưng luôn có giới hạn. `countByCustomer` trả số lượng, bao gồm `0`, không bọc `Optional` chỉ vì bảng có thể trống.

Tầng **repository/adapter** biết cơ chế truy cập và kết quả từ DB. Tầng **service/use case** biết một tài nguyên có bắt buộc tồn tại để hoàn thành nghiệp vụ hay không. Tầng **HTTP/API** biết cần trả 404, 409, 500, 503, hay JSON dạng `[]`. Giữ các trách nhiệm này riêng sẽ giúp cùng một repository tái sử dụng được cho batch job, HTTP API và kiểm thử.

Không nên thiết kế một hàm kiểu `Object fetch(String sql)` rồi bắt mọi caller tự ép kiểu và suy đoán `null`. Một API có tên `findFirst...` phù hợp khi thực sự muốn **bản ghi đứng đầu theo thứ tự xác định** (ví dụ đơn mới nhất); không dùng nó để giấu lỗi trùng khi dữ liệu phải duy nhất.

## 4. Khi không có dữ liệu: vắng mặt khác với lỗi

### 4.1. Trả rỗng như một kết quả bình thường

- Một lookup tùy chọn trả `Optional.empty()` (imperative) hoặc `Mono.empty()` (reactive) nếu không tìm thấy.
- Một truy vấn nhiều hàng trả `List.of()`/danh sách rỗng hoặc `Flux.empty()`. **Không trả `null` cho collection** vì mọi caller phải kiểm tra hai trạng thái “null” và “empty”.
- Một truy vấn thống kê vẫn có thể trả hàng aggregate. `COUNT(*)` trả `0` khi không có hàng khớp; `SELECT COUNT(*) ... GROUP BY customer_id` có thể trả **không hàng nào** nếu không có group. Phân biệt rõ cấu trúc SQL.
- Nếu trường SQL có thể `NULL`, mapping sang kiểu nullable, `Optional` ở chỗ phù hợp, hoặc dùng `COALESCE` khi nghiệp vụ định nghĩa giá trị mặc định. Không áp đặt `0` cho mọi giá trị NULL: đôi khi “không biết” khác “bằng 0”.

### 4.2. Vắng mặt nhưng bắt buộc phải có

Ví dụ yêu cầu “thu tiền đơn hàng #42” không thể thực hiện nếu đơn không tồn tại. Repository trả `Optional`; service chuyển thành lỗi miền có ý nghĩa:

```java
package example.orders;

public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String code) {
        super("Order not found: " + code);
    }
}
```

```java
package example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderReadPort orders;

    public OrderLookupService(OrderReadPort orders) {
        this.orders = orders;
    }

    public OrderView requireByCode(String code) {
        return orders.findByExternalCode(code)
            .orElseThrow(() -> new OrderNotFoundException(code));
    }
}
```

`requireByCode` biểu đạt **chính sách của use case**. Một use case khác gọi `findByExternalCode` có thể xem absence là tình huống bình thường. Đừng ném `NotFound` vô điều kiện ngay trong mọi adapter nếu cùng thao tác tra cứu được dùng nhiều bối cảnh.

### 4.3. Không biến lỗi kỹ thuật thành “không tìm thấy”

**Mẫu sai:**

```java
// Anti-pattern: mất kết nối cũng bị biến thành "không tồn tại".
try {
    return repository.findByExternalCode(code);
} catch (Exception ex) {
    return Optional.empty();
}
```

Đoạn trên là **minh họa anti-pattern**, không phải chương trình độc lập. Nếu driver timeout hoặc SQL sai, người dùng thấy 404 dù DB có thể chứa dữ liệu. Monitoring cũng mất tín hiệu lỗi.

**Cách đúng:** chỉ xử lý absence qua contract kết quả; để lỗi kỹ thuật đi qua cơ chế phân loại/ghi log/quan sát và mapping HTTP phù hợp. Không dùng `catch (Exception)` để tạo dữ liệu mặc định khi chưa có chính sách fallback được chứng minh.

## 5. Khi có nhiều kết quả: mong đợi nhiều hay chỉ một?

### 5.1. Nhiều kết quả là bình thường

Tìm theo `customer_id` có thể trả 0..N đơn. Hợp đồng nên bao gồm:
- Thứ tự ổn định: `ORDER BY created_at DESC, id DESC` (có khóa phá hòa để thứ tự không ngẫu nhiên).
- Giới hạn `limit` hoặc phân trang, validate giới hạn tối đa.
- Projection chỉ lấy cột cần dùng thay vì `SELECT *`.
- Chỉ số phù hợp với `WHERE` + `ORDER BY`, đo query plan.
- Không gọi `List.size()` trên hàng triệu phần tử chỉ để “đếm”; dùng `COUNT(*)` nếu thật sự cần count, lưu ý count có thể tốn tài nguyên.

### 5.2. Nhiều kết quả là vi phạm

Khi query theo khóa được định nghĩa duy nhất, **kết quả có hơn một hàng là lỗi**, không phải “danh sách dài hơn dự tính”. Cần:
1. Áp đặt `PRIMARY KEY`/`UNIQUE` tại database để chống race condition.
2. Dùng API 0..1 có kiểm tra số hàng (ví dụ `JdbcClient.optional()` hoặc repository `Optional<T>`).
3. Nếu dữ liệu cũ đã bị trùng, sửa root cause bằng migration/cleanup được kiểm soát; không che giấu bằng `LIMIT 1`.
4. Nếu mục đích thật sự là “mới nhất”, diễn đạt rõ `findLatest...` và sắp xếp ổn định. Khi đó `LIMIT 1` là đúng, không phải sửa lỗi tùy tiện.

**Đặc biệt:** `findFirstBy...`/`first()` có thể lấy một phần tử khi query cho nhiều hàng; chúng **không xác minh tính duy nhất**. `Mono.next()` từ một `Flux` cũng chỉ lấy phần tử đầu. Đừng dùng chúng cho khóa yêu cầu duy nhất.

### 5.3. Kết quả rất lớn cần giới hạn và phân trang

Có ba chiến lược cơ bản:
- **Page**: nội dung một trang cùng metadata tổng số khi cần “trang 1/120”; có thể phải chạy thêm count query.
- **Slice/Window**: lấy một đoạn và biết còn dữ liệu hay không, phù hợp infinite scroll; có thể tránh count toàn bộ.
- **Keyset/cursor pagination**: lấy tiếp sau cặp khóa sắp xếp, giảm vấn đề `OFFSET` sâu. Cần điều kiện và index phù hợp, cursor phải gắn với filter/sort và chính sách dữ liệu thay đổi.

Ví dụ cursor với PostgreSQL, chỉ lấy các hàng **cũ hơn** cursor (khi cả hai cột không NULL):

```sql
SELECT id, external_code, customer_id, total_cents, created_at
FROM order_records
WHERE customer_id = :customerId
  AND (created_at, id) < (:cursorCreatedAt, :cursorId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

**Trang đầu tiên** bỏ điều kiện cursor, nhưng dùng cùng `WHERE customer_id` và `ORDER BY`. Cursor phải lấy từ bản ghi cuối trang trước, `pageSize` phải nằm trong ngưỡng cho phép. Việc thêm/xóa dữ liệu giữa các request có thể làm nội dung trang thay đổi: cần quy định mức nhất quán mong muốn, không hứa snapshot ổn định nếu không duy trì snapshot thực sự.

## 6. Ví dụ schema cho một contract thống nhất

Dùng PostgreSQL để minh họa:

```sql
CREATE TABLE order_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total_cents BIGINT NOT NULL CHECK (total_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_customer_recent
    ON order_records (customer_id, created_at DESC, id DESC);
```

`external_code` được database bảo vệ tính duy nhất. `customer_id` **không duy nhất**, do đó query danh sách phải cho phép N hàng. Index thứ hai hỗ trợ bộ lọc và thứ tự danh sách gần đây. Schema và index là phần quan trọng của contract: Java type một mình không thể bảo vệ uniqueness khi hai giao dịch cập nhật đồng thời.

DTO dùng chung cho các ví dụ:

```java
// OrderView.java
package example.orders;

public record OrderView(
    long id,
    String externalCode,
    long customerId,
    long totalCents
) {}
```

Những snippet Spring bên dưới thuộc **dự án Spring Boot/Spring Framework có dependency phù hợp**, không biên dịch được chỉ với `javac` trần vì cần thư viện Spring, driver và kết nối DB. Để thử thực tế, tạo schema, cấu hình datasource/connection factory, thêm dependency và chạy ứng dụng/test bằng Gradle/Maven. Các ví dụ JDBC, JPA, R2DBC là **ba implementation minh họa** cho cùng chính sách; không yêu cầu bật cả ba.

## 7. JDBC/JdbcClient: phân biệt `optional()`, `single()` và `list()`

Với Spring Framework 6.1+ (Spring Boot 3.2+), `JdbcClient` cung cấp giao diện fluent trên JDBC. Dependency mẫu:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderJdbcReader.java`:

```java
package example.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcReader implements OrderReadPort {
    private static final RowMapper<OrderView> MAPPER = (rs, rowNum) ->
        new OrderView(
            rs.getLong("id"),
            rs.getString("external_code"),
            rs.getLong("customer_id"),
            rs.getLong("total_cents")
        );

    private final JdbcClient jdbc;

    public OrderJdbcReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<OrderView> findByExternalCode(String code) {
        return jdbc.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE external_code = :code
                """)
            .param("code", code)
            .query(MAPPER)
            .optional();
    }

    @Override
    public List<OrderView> findRecentByCustomer(long customerId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return jdbc.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE customer_id = :customerId
                ORDER BY created_at DESC, id DESC
                LIMIT :maxRows
                """)
            .param("customerId", customerId)
            .param("maxRows", limit)
            .query(MAPPER)
            .list();
    }

    @Override
    public long countByCustomer(long customerId) {
        return jdbc.sql("""
                SELECT COUNT(*)
                FROM order_records
                WHERE customer_id = :customerId
                """)
            .param("customerId", customerId)
            .query(Long.class)
            .single();
    }
}
```

**Hành vi cần nhớ:**
- `.query(MAPPER).optional()`: 0 hàng → `Optional.empty()`; 1 hàng → `Optional.of(value)`; nhiều hơn 1 → `IncorrectResultSizeDataAccessException`. Nếu khóa có `UNIQUE` thì trường hợp cuối chỉ xảy ra khi truy vấn hoặc thiết kế schema sai, hay từ view/join làm nhân bản hàng.
- `.query(MAPPER).single()`: bắt buộc một kết quả; 0 hàng → `EmptyResultDataAccessException`; >1 → `IncorrectResultSizeDataAccessException`. Dùng khi **bản chất SQL bảo đảm một hàng**, chẳng hạn `COUNT(*)` không có `GROUP BY`.
- `.query(MAPPER).list()`: 0 hàng → danh sách rỗng; N hàng → danh sách N. Không gọi `list()` với truy vấn không giới hạn khi tập dữ liệu có thể rất lớn.
- Giá trị bind bằng `.param` tránh ghép input vào SQL. Tên cột/đoạn `ORDER BY` động phải được chọn từ **allowlist**, không thể bind SQL identifier như giá trị.

**Với `JdbcTemplate` cũ:** `queryForObject(...)` thường kỳ vọng đúng một hàng và có thể ném `EmptyResultDataAccessException` khi rỗng; `query(...)` trả danh sách và không xem rỗng là lỗi. Không dùng `queryForObject` để thực hiện tìm kiếm 0..N.

### Một lần đọc không đồng nghĩa với một lần ghi thành công

Với `UPDATE`/`DELETE`, số hàng được thay đổi là dữ kiện khác số hàng query:
- `0` có thể là không tìm thấy, trạng thái không khớp, version đã đổi hoặc dữ liệu bị xóa giữa hai thao tác.
- `1` thường là thành công nếu câu SQL dùng khóa đơn.
- `>1` là **vi phạm mong đợi** nếu nghiệp vụ chỉ cho phép thay đổi một bản ghi.

Ví dụ cập nhật có điều kiện:

```sql
UPDATE order_records
SET total_cents = :newTotal
WHERE id = :orderId
  AND total_cents = :expectedOldTotal;
```

Nếu affected rows bằng 0, **không được kết luận ngay “id không tồn tại”**: có thể phiên bản giá trị đã thay đổi. Muốn phân biệt “không tìm thấy” với “conflict”, cần chính sách tra cứu bổ sung hoặc version/optimistic-lock contract. Quyết định update phải luôn ưu tiên điều kiện nguyên tử tại DB thay vì `SELECT` rồi `UPDATE` vô điều kiện.

## 8. Spring Data JPA: Optional cho một bản ghi, List/Page/Slice cho nhiều

Spring Data JPA dựa trên JPA provider như Hibernate, thường dùng các chữ ký:

```java
// OrderJpaRepository.java - ví dụ interface trong một dự án JPA
package example.orders;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, Long> {
    Optional<OrderEntity> findByExternalCode(String externalCode);

    Page<OrderEntity> findByCustomerId(Long customerId, Pageable pageable);
}
```

`OrderEntity` ở đây là entity đã được mapping tới bảng `order_records`, với các thuộc tính `externalCode`, `customerId` tương ứng; đoạn trên **là một phần dự án, cần khai báo entity** và không phải chương trình độc lập.

- `findById(id)` của repository trả `Optional<T>`. Khi không có entity là `Optional.empty()`.
- Query method `Optional<T> findByExternalCode(...)` biểu đạt **0..1**. Nếu query trả nhiều hơn một entity, Spring Data có thể ném `IncorrectResultSizeDataAccessException`; unique constraint bảo vệ trực tiếp tại database.
- Query `Page<T> findByCustomerId(..., Pageable)` biểu đạt nhiều bản ghi theo trang. Khi không có dữ liệu, nội dung trang rỗng; page metadata cho biết thông tin trang/tổng số (đôi khi cần count query). Nếu chỉ cần biết có trang tiếp theo, cân nhắc `Slice<T>` để giảm chi phí count.
- Collection-returning repository methods thường trả collection rỗng thay vì `null`. Có thể dùng projection/DTO để tránh load entity graph không cần thiết.
- Spring Data không bắt mọi method trả `Optional`: chọn theo cardinality. Một method trả `T` không có nullable contract rõ có thể gây khó hiểu; nếu kết quả bắt buộc, nên làm rõ ở service và kiểm tra absence.

**Cẩn thận với JPA trực tiếp:** `EntityManager.getSingleResult()` có thể ném `NoResultException` hoặc `NonUniqueResultException`. Spring Data repository thường chuyển exception sang abstraction của Spring tùy ngữ cảnh. Không nên viết code gắn chặt với một exception cụ thể từ provider mà không xác nhận ranh giới gọi.

**N+1 và “nhiều dữ liệu”**: một page có 20 entity nhưng mỗi entity lazy-load một quan hệ có thể phát sinh 21+ query. Phân trang không tự giải quyết N+1; cần projection, `JOIN FETCH`/`@EntityGraph` thích hợp và giám sát số query. Đừng trả trực tiếp entity lớn ra REST API nếu chỉ cần vài cột.

**Stream từ JPA:** stream có thể giữ connection/`ResultSet`/transaction. Đọc streaming trong transaction phù hợp và đóng `Stream` (try-with-resources). Nó không đảm bảo driver fetch từng row mà không buffer; phải kiểm tra fetch size, provider và memory behavior.

## 9. R2DBC: `Mono.empty()`, `Flux.empty()` và tín hiệu lỗi

Với Spring R2DBC, truy vấn tạo reactive publisher. Dùng `DatabaseClient`/Spring Data R2DBC và driver tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
```

`ReactiveOrderReader.java`:

```java
package example.orders;

import java.util.Objects;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveOrderReader {
    private final DatabaseClient db;

    public ReactiveOrderReader(DatabaseClient db) {
        this.db = db;
    }

    public Mono<OrderView> findByExternalCode(String code) {
        return db.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE external_code = :code
                """)
            .bind("code", code)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("external_code", String.class),
                ((Number) Objects.requireNonNull(
                    row.get("customer_id"))).longValue(),
                ((Number) Objects.requireNonNull(
                    row.get("total_cents"))).longValue()))
            .one();
    }

    public Flux<OrderView> findRecentByCustomer(
            long customerId, int limit) {
        if (limit < 1 || limit > 100) {
            return Flux.error(
                new IllegalArgumentException("limit must be 1..100"));
        }
        return db.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE customer_id = :customerId
                ORDER BY created_at DESC, id DESC
                LIMIT :maxRows
                """)
            .bind("customerId", customerId)
            .bind("maxRows", limit)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("external_code", String.class),
                ((Number) Objects.requireNonNull(
                    row.get("customer_id"))).longValue(),
                ((Number) Objects.requireNonNull(
                    row.get("total_cents"))).longValue()))
            .all();
    }
}
```

- `.one()`: 0 hàng → `Mono.empty()`; một hàng → phát một `OrderView`; hơn một hàng → lỗi `IncorrectResultSizeDataAccessException`.
- `.first()`: trả hàng đầu và bỏ phần còn lại. Chỉ dùng khi truy vấn thực sự yêu cầu “đầu tiên” và `ORDER BY` có ý nghĩa.
- `.all()`: phát 0..N hàng, 0 hàng → publisher hoàn thành mà không phát phần tử; không tạo `null`.
- `Mono.empty()` **khác** `Mono.error(...)`. Lỗi trong truy cập DB được phát qua tín hiệu `onError` khi publisher được subscribe; không coi nó là dữ liệu rỗng.
- `Mono`/`Flux` được thực thi theo vòng đời subscription; không gọi `subscribe()` thủ công trong service rồi trả `Mono.empty()` cho caller. Điều đó tách xử lý lỗi/transaction khỏi request.
- Reactive không có nghĩa kết quả có thể vô hạn mà không tốn tài nguyên. Driver, số connection, query, pagination, fetch behavior và sức chịu tải của consumer vẫn quyết định mức sử dụng tài nguyên.

Chuyển absence thành lỗi use case trong Reactor:

```java
// Phương thức trong reactive service đã inject ReactiveOrderReader.
public Mono<OrderView> requireOrder(String code) {
    return reader.findByExternalCode(code)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(code)));
}
```

Đoạn này là **method minh họa đặt trong service có field `reader`**, không phải file Java hoàn chỉnh. `switchIfEmpty` chỉ xử lý trạng thái hoàn tất rỗng; lỗi SQL/connection vẫn đi đường `onError`. Không viết `onErrorResume(ex -> Mono.empty())` cho toàn bộ lỗi vì nó biến lỗi kỹ thuật thành 404/không tồn tại. Nếu cần fallback, chỉ bắt **loại lỗi xác định** với điều kiện fallback bảo đảm nghiệp vụ đúng.

### Kiểm tra reactive bằng StepVerifier

`StepVerifier` kiểm tra **onNext/onComplete/onError**, không chỉ giá trị trả về. Các tình huống cần test:
- Không hàng → `verifyComplete()` ngay, không có `onNext`.
- Một hàng → `expectNextMatches(...)` rồi `verifyComplete()`.
- Nhiều hàng khi kỳ vọng một → `expectError(IncorrectResultSizeDataAccessException.class)`.
- Query lỗi/driver lỗi → nhận tín hiệu `onError`, không chuyển thành `Mono.empty()`.
- Có thể đã phát vài row trước khi gặp lỗi khi dùng `Flux`. Nếu caller cần tính nguyên tử của kết quả trả về, phải quy định chính sách riêng; reactive stream có thể đã truyền dữ liệu trước khi báo lỗi.

## 10. Lỗi tầng dữ liệu: phân loại và chọn chính sách xử lý

Spring cung cấp hệ phân cấp `org.springframework.dao.DataAccessException` để che bớt khác biệt giữa driver/provider. Đây là **unchecked exception**, có nhiều subtype. Không giả định mọi JDBC/JPA/R2DBC lỗi đều được dịch thành cùng subtype trong mọi dialect/phiên bản; kiểm thử với DB thật.

| Tình huống | Dấu hiệu hay gặp | Xử lý gợi ý |
|---|---|---|
| Lookup 0 hàng, **được phép vắng mặt** | `Optional.empty()`, `Mono.empty()` | Trả rỗng, không ghi ERROR |
| Lookup 0 hàng, **bắt buộc có** | `EmptyResultDataAccessException` nếu API yêu cầu đúng một; hoặc service tự ném `NotFound` | Chuyển thành lỗi miền rõ ràng, thường HTTP 404 ở HTTP layer |
| Lookup >1 hàng nhưng contract 0..1 | `IncorrectResultSizeDataAccessException` | Báo lỗi invariant/contract, điều tra dữ liệu và uniqueness |
| Trùng khóa khi ghi | `DuplicateKeyException`/`DataIntegrityViolationException` tùy driver/translator | Chuyển thành conflict miền **chỉ khi** xác định đúng constraint nghiệp vụ |
| Vi phạm FK, NOT NULL, CHECK | `DataIntegrityViolationException` hoặc exception liên quan | Sửa dữ liệu đầu vào/logic; không mặc định gắn tất cả vào 409 |
| Xung đột optimistic locking | `OptimisticLockingFailureException` hoặc subtype từ JPA | Trả conflict/stale update, hoặc retry có giới hạn khi an toàn |
| Timeout, deadlock, không lấy được lock | Exception liên quan timeout/lock, có thể thuộc nhóm transient | Đánh giá retry có backoff và giới hạn; kiểm tra idempotency |
| Không kết nối được DB, pool cạn | Data access resource/connection failure | Log/monitor, có thể báo 503 theo API policy; không trả rỗng |
| SQL sai/cột không tồn tại/mapping sai | Bad SQL grammar/type conversion/mapping errors | Lỗi lập trình/cấu hình, sửa root cause, không tự động retry |
| Null cột không đúng giả định | Mapping failure, NPE hoặc type mismatch | Kiểm tra schema/null contract; không biến thành not-found |

**Không có dữ liệu** và **SQL bị lỗi** phải tạo ra tín hiệu khác nhau trong log, metrics và API. `catch (DataAccessException)` ở mọi repository method để trả giá trị mặc định làm mất lợi ích của Spring exception translation.

### Quy tắc về retry

- Chỉ retry khi lỗi thực sự **tạm thời** và thao tác an toàn để lặp; tránh retry chung mọi `DataAccessException`.
- Read-only query thường dễ retry hơn write có side effect, nhưng timeout có thể xảy ra **sau khi DB đã commit write** dù client chưa nhận xác nhận.
- Với write, dùng idempotency key, unique request id, trạng thái/version, hoặc cơ chế outbox nếu cần.
- Retry có **giới hạn số lần, exponential backoff/jitter**, deadline chung và metrics; không tạo vòng retry vô tận khi DB đang cạn tài nguyên.
- Transaction bị rollback phải được khởi tạo lại hợp lệ khi retry, không “tiếp tục transaction” đã thất bại.
- Không mặc định retry `DuplicateKeyException` hay `IncorrectResultSizeDataAccessException`: chúng thường báo lỗi nghiệp vụ/invariant chứ không phải nhiễu ngẫu nhiên.

## 11. Tách lỗi miền, lỗi hạ tầng và lỗi HTTP

Một hệ thống điển hình có ba bề mặt:

```text
Database / JDBC / JPA / R2DBC
    ↓ result 0/1/N hoặc DataAccessException
Repository (truy cập và ánh xạ, bảo toàn cardinality)
    ↓ Optional/List/Page/Mono/Flux hoặc lỗi
Service / use case (require / allow absence; resolve conflict)
    ↓ domain result hoặc domain exception
HTTP controller + @RestControllerAdvice (mapping ra status/body)
```

Ví dụ Spring MVC 6.x với `ProblemDetail`:

```java
// OrderApiErrors.java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderApiErrors {
    @ExceptionHandler(OrderNotFoundException.class)
    public ProblemDetail notFound(OrderNotFoundException ignored) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("No order matches the requested code.");
        return problem;
    }
}
```

Đây là mapping **một loại lỗi miền**. Hệ thống production thường còn mapping validation, conflict, access denied và lỗi hạ tầng tại lớp HTTP chung. Không trả nội dung `SQLException`, connection URL, tên bảng nội bộ, stack trace hoặc dữ liệu nhạy cảm cho client. Lưu lỗi chi tiết trong log an toàn kèm trace/correlation id, đưa ra problem code ổn định cho phía client.

### Gợi ý hợp đồng API

| Tác vụ | Kết quả | HTTP thường dùng |
|---|---|---|
| `GET /orders/{code}` | Có một đơn | `200` + DTO |
| `GET /orders/{code}` | Không tìm thấy | `404` + problem detail |
| `GET /customers/{id}/orders` | Không có đơn | `200` + `[]` hoặc page rỗng |
| `POST /orders` | Tạo thành công | `201` + location/body theo contract |
| `POST /orders` | Trùng mã đơn thuộc unique constraint nghiệp vụ | `409` nếu xác định conflict |
| `PATCH /orders/{id}` | Version/trạng thái bị thay đổi đồng thời | `409` hoặc `412` khi dùng HTTP conditional request đúng chuẩn |
| Endpoint bất kỳ | Tham số client sai | `400` / validation response |
| Endpoint bất kỳ | DB lỗi, mất kết nối | `5xx`/`503` tùy chính sách và bản chất lỗi |

Mã HTTP là quyết định của boundary, không phải giá trị tự động của mọi `DataAccessException`. Ví dụ “đơn không thấy” đôi khi còn phụ thuộc phân quyền; API có thể cố ý dùng 404 thay vì 403 theo policy bảo mật. Không để repository quyết định HTTP status.

## 12. Thao tác ghi: số hàng ảnh hưởng là kết quả quan trọng

Xét một lệnh update dự kiến đúng một đơn:

```java
// Phương thức trong một JDBC repository đã có JdbcClient jdbc.
public boolean updateTotalIfUnchanged(
        long id, long expectedTotal, long nextTotal) {
    int count = jdbc.sql("""
            UPDATE order_records
            SET total_cents = :nextTotal
            WHERE id = :id AND total_cents = :expectedTotal
            """)
        .param("nextTotal", nextTotal)
        .param("id", id)
        .param("expectedTotal", expectedTotal)
        .update();

    if (count > 1) {
        throw new IllegalStateException(
            "Expected at most one updated order");
    }
    return count == 1;
}
```

Đoạn này là **method minh họa trong class có field `jdbc`**; validate `nextTotal >= 0` ở tầng ứng dụng, DB `CHECK` cũng bảo vệ ràng buộc. Hợp đồng boolean chỉ cho biết **lệnh có thay đổi đúng một row hay không**. Nếu `false`, nó không tự chứng minh row đã bị xóa; có thể row đang mang giá trị khác. Nếu nghiệp vụ cần phân loại, thiết kế outcome rõ, ví dụ `UPDATED`, `NOT_FOUND`, `STALE_VERSION`, và tránh tạo race mới khi tra cứu lại.

Dùng `@Version` (JPA) hoặc version column với điều kiện `WHERE version = :expectedVersion` để phát hiện stale write. Nếu gọi hai lệnh trong một use case, đặt transaction tại service và kiểm tra rollback khi lỗi; không giả định hai repository calls nằm cùng transaction nếu chưa cấu hình. Với reactive, transaction gắn với Reactor context; không trộn JDBC và R2DBC và tự coi chúng có cùng ACID transaction.

**Với insert trùng unique key:** tránh chiến thuật “kiểm tra tồn tại rồi mới insert” như biện pháp bảo đảm duy nhất; giữa hai bước có race. Giữ unique constraint ở DB và xử lý lỗi conflict một cách có chủ đích. PostgreSQL có `INSERT ... ON CONFLICT ...` cho upsert khi nghiệp vụ thực sự muốn upsert; hành vi upsert phải là contract rõ ràng, không phải fallback bất ngờ.

## 13. Không “nuốt lỗi” bằng Optional, List rỗng hoặc fallback reactive

Đây là các anti-pattern cần nhận biết:

```java
// SAI: lỗi hạ tầng hoặc bug query bị che thành danh sách rỗng.
try {
    return jdbcReader.findRecentByCustomer(customerId, 50);
} catch (RuntimeException ex) {
    return java.util.List.of();
}
```

```java
// SAI trong service reactive: bất kỳ lỗi nào cũng thành "không thấy".
return reactiveReader.findByExternalCode(code)
    .onErrorResume(ex -> Mono.empty());
```

Các đoạn trên là **mã chống ví dụ** trong ngữ cảnh service có dependency tương ứng. Hậu quả: monitoring báo thành công giả, cache có thể lưu kết quả rỗng, UI không phân biệt DB lỗi và tài khoản chưa từng đặt hàng.

**Được phép fallback khi nào?** Chỉ khi yêu cầu cho phép dữ liệu thay thế và có chính sách rõ, ví dụ read model có cache với freshness/expiry đã công bố. Cần:
- Chỉ fallback cho nhóm lỗi được chỉ định; không fallback trên constraint/authorization/bug mapping.
- Ghi log, metric “degraded”, trace và thời điểm dữ liệu cache; không đánh dấu kết quả dự phòng như dữ liệu mới.
- Không để fallback biến update thất bại thành “đã cập nhật”.
- Test trường hợp cả primary và fallback đều thất bại.

## 14. Bài học về truy vấn “một hàng”: kiểm tra chất lượng dữ liệu từ database

Nếu `external_code` phải duy nhất, thiết kế cần có ít nhất:
- Cột `NOT NULL` nếu không cho phép vắng mã.
- `UNIQUE` constraint trong schema/migration. Trên DB nhất định, unique với NULL có đặc điểm riêng; cần kiểm tra nếu cho phép NULL.
- Query theo đầy đủ scope uniqueness. Ví dụ hệ multi-tenant với `UNIQUE(tenant_id, external_code)` thì method phải truyền **tenant id**; query chỉ theo `external_code` có thể hợp lệ trả N bản ghi từ nhiều tenant.
- Test hai transaction đồng thời tạo cùng mã: một bên thành công, bên kia nhận unique violation; response và retry logic phải rõ.
- Không dùng `DISTINCT` hay `LIMIT 1` để che lỗi JOIN khiến kết quả nhân bản. Nếu JOIN thực sự nhiều-to-một, projection/aggregate cần xác định rõ đơn vị kết quả.

Một hàng khác một *thực thể logic*: SQL có thể tạo nhiều row cho cùng entity khi JOIN quan hệ một-nhiều. Hãy hỏi “cardinality của **entity** hay của **row SQL**?” trước khi áp dụng phương thức single-result. Với projection khác nhau, cùng một đơn hàng có thể xuất hiện nhiều dòng; đừng tự suy luận uniqueness chỉ từ cột id trong projection.

## 15. Kiểm thử hợp đồng với các tình huống bắt buộc

### Ma trận test tối thiểu

| Input/database state | Expected repository | Expected service/API |
|---|---|---|
| Mã đơn không tồn tại | `Optional.empty()` / `Mono.empty()` | Lookup tùy chọn bình thường; require → 404/domain NotFound |
| Tìm theo khách hàng không có đơn | `List` rỗng / `Flux` hoàn tất rỗng | `200` + `[]` hoặc trang rỗng |
| Đúng một đơn theo mã | Một `OrderView` | `200` + DTO |
| Hai row khớp một query **cam kết duy nhất** | Exception cardinality | Alert/invariant error; không âm thầm lấy row đầu |
| 1000 đơn nhưng giới hạn 20 | Tối đa 20, sort ổn định | Metadata/cursor phù hợp, không trả hết |
| `COUNT(*)` khi không có hàng khớp | `0` (một hàng aggregate) | Số 0 hợp lệ |
| DB mất kết nối/timeout | Lỗi hạ tầng | 5xx/503 theo policy, metrics và trace, không 404/[] |
| Trùng unique key khi insert | Lỗi constraint | Conflict miền nếu xác định rõ constraint |
| Update có expected version cũ | 0 affected row hoặc optimistic locking exception | Conflict/stale state theo contract |
| SQL mapping sai/NULL bất ngờ | Lỗi kỹ thuật | Log và sửa schema/mapping, không trả rỗng |

### Kiểm thử Java 17 thuần để hiểu cardinality

Đoạn sau **độc lập**, không cần Spring; nó minh họa nguyên tắc 0..1 khác 0..N. Tên file `CardinalityDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class CardinalityDemo {
    static <T> Optional<T> atMostOne(List<T> rows) {
        if (rows.size() > 1) {
            throw new IllegalStateException(
                "Expected at most one result");
        }
        return rows.stream().findFirst();
    }

    public static void main(String[] args) {
        System.out.println(atMostOne(List.<String>of()));
        System.out.println(atMostOne(List.of("ORD-1")));
        try {
            atMostOne(List.of("ORD-1", "ORD-2"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CardinalityDemo.java
java CardinalityDemo
```

Stdout chính xác:

```text
Optional.empty
Optional[ORD-1]
Expected at most one result
```

Không được diễn giải việc dòng cuối ném exception như “dữ liệu rỗng”. Spring dùng các API/exception khác, nhưng **hợp đồng cardinality** giống nhau.

### Integration test cần có

- Chạy test với DB thật phù hợp sản phẩm (ví dụ PostgreSQL qua Testcontainers), vì H2 không luôn mô phỏng constraint, isolation, lock, null và SQL dialect đúng.
- Với JDBC, test `optional()/single()/list()` và lỗi truy vấn không bị nuốt.
- Với JPA, test Optional, query theo natural key, projection, paging/slicing, SQL count và số query khi load association.
- Với R2DBC, dùng `StepVerifier` để kiểm tra tín hiệu rỗng, phần tử, lỗi. Với `Flux`, kiểm tra resource cleanup/cancel và hành vi lỗi sau khi đã emit.
- Với transaction, test rollback và hai request cạnh tranh, version/constraint. Với HTTP, test mapping 404, 409, 5xx và không lộ chi tiết DB.
- Với tập kết quả lớn, đo memory, p95/p99, connection pool, query plan và số row thực tế. Không lấy dữ liệu production nhạy cảm làm test fixture.

## 16. Checklist áp dụng trước khi tạo method repository

- [ ] Tôi đã định nghĩa cardinality: `0..1`, `exactly 1`, `0..N`, hay update count.
- [ ] Tôi đã ghi rõ absence là kết quả bình thường hay lỗi nghiệp vụ tại use case.
- [ ] Nếu kỳ vọng duy nhất, có `UNIQUE`/`PRIMARY KEY` hoặc lý do logic rõ; query dùng đúng toàn bộ scope uniqueness.
- [ ] Nếu nhiều bản ghi hợp lệ, method trả collection/reactive sequence, có giới hạn và thứ tự ổn định.
- [ ] Nếu dữ liệu lớn, có page/slice/cursor và kế hoạch index/query; không thu gom hết vào bộ nhớ.
- [ ] Tôi phân biệt zero rows với SQL NULL và với `COUNT(*) = 0`.
- [ ] Tôi không chuyển `DataAccessException`/`onError` thành `null`, `[]`, `Optional.empty()` hoặc `Mono.empty()` vô điều kiện.
- [ ] Tôi xác định cách xử lý constraint, optimistic conflict, timeout, connection failure và retry an toàn.
- [ ] Tầng HTTP có status/body ổn định; log không để lộ SQL, credential hay dữ liệu nhạy cảm.
- [ ] Test đã bao phủ 0, 1, >1, dữ liệu lớn, lỗi DB, rollback/concurrency và response API.

## 17. Ghi nhớ cốt lõi

**Không có dữ liệu** chỉ là kết quả bình thường nếu contract cho phép; với use case yêu cầu tài nguyên, chuyển vắng mặt thành lỗi miền. **Nhiều dữ liệu** là bình thường khi query công bố 0..N, nhưng là **lỗi** nếu query cam kết 0..1; còn tập dữ liệu lớn phải có chính sách giới hạn/phân trang. **Lỗi thực thi** như mất kết nối, SQL sai, timeout hoặc vi phạm constraint phải giữ được tín hiệu riêng để service/API xử lý chính xác, không thay bằng kết quả rỗng.

Các công cụ Java/Spring thể hiện cùng một ý tưởng qua kiểu kết quả khác nhau: `Optional/List`, `Page/Slice`, `Mono/Flux` và `DataAccessException`. Điều quan trọng nhất không nằm ở việc chọn một API “tiện”, mà ở việc **định nghĩa hợp đồng rồi kiểm chứng đúng từng trường hợp**.

## Tài liệu tham khảo

- Spring Framework — JDBC Core và JdbcClient: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — R2DBC DatabaseClient: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Data Commons — Query Return Types: https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html
- Spring Data Commons — Scrolling: https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html
- Spring Data JPA — Repository Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Framework — Error Responses và ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
