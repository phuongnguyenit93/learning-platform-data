# Kiểm soát tên bảng hoặc cột động bằng danh sách cho phép trong @Query

Trong **Spring Data Cassandra**, annotation `@Query` giúp khai báo CQL trực tiếp cho một phương thức repository. Lập trình viên thường dùng bind marker `?0`, `?1` để truyền các giá trị vào điều kiện `WHERE`. Nhưng khi nghiệp vụ cho phép người dùng “chọn bảng dữ liệu”, “chọn cột hiển thị” hoặc “chọn cách sắp xếp”, có một giới hạn căn bản: **bind marker chỉ biểu diễn giá trị dữ liệu, không biểu diễn tên bảng, cột, keyspace hoặc một đoạn cú pháp CQL**.

Nếu ứng dụng nối trực tiếp chuỗi từ HTTP request vào cấu trúc CQL, hệ thống có thể truy cập nhầm bảng, lộ dữ liệu ngoài phạm vi quyền, tạo câu lệnh không hợp lệ hoặc gặp **CQL injection**. Cách tiếp cận phù hợp là **danh sách cho phép (allowlist)**: giới hạn lựa chọn vào những bảng, cột và mẫu truy vấn đã được phê duyệt trong code; những giá trị như UUID, ngày, trạng thái và giới hạn kết quả tiếp tục được bind qua driver.

Bài thuộc chương **Truy vấn @Query** của module `SPRING_DATA_CASSANDRA`. Mục tiêu là phân biệt dữ liệu với identifier, chọn an toàn giữa nhiều câu `@Query` cố định, dùng enum và `CqlOperations` khi cần chọn query ở runtime, xác định ranh giới authorization và duy trì thiết kế bảng theo truy vấn, partition key, clustering key, consistency, paging và hiệu năng của Cassandra phân tán.

> **Quy tắc cốt lõi:** Cho phép **chọn một cấu trúc CQL đã được duyệt**, tuyệt đối không trao cho input chưa tin cậy quyền quyết định tên bảng, tên cột hoặc cả mệnh đề truy vấn.

## 1. @Query là câu CQL khai báo sẵn

Một repository phương thức đọc đơn hàng theo khách và tháng:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface OrderRepository
        extends CassandraRepository<OrderByCustomerMonth, CustomerMonthOrderKey> {

    @Query("SELECT * FROM orders_by_customer_month " +
           "WHERE customer_id = ?0 AND bucket_month = ?1 LIMIT 20")
    List<OrderByCustomerMonth> recentOrders(
        UUID customerId,
        LocalDate bucketMonth
    );
}
```

Ở ví dụ này:

- `orders_by_customer_month` là tên bảng **do lập trình viên định nghĩa** trong CQL.
- `customer_id` và `bucket_month` là tên cột **cố định**.
- `?0` và `?1` nhận **giá trị nghiệp vụ** của hai tham số Java theo vị trí.
- `LIMIT 20` giới hạn tổng số hàng trả về, không phải page size của driver.

Annotation Java yêu cầu giá trị chuỗi hằng ở thời điểm biên dịch. Spring Data có thể có thêm cơ chế xử lý biểu thức trong một số phiên bản, nhưng **không nên dùng một cơ chế biểu thức để cho phép input từ client tự quyết định identifier**. Với số lượng bảng nhỏ, hãy khai báo riêng những câu truy vấn đã được review.

Lưu ý `@Query` không tự làm cho truy vấn hiệu quả: Cassandra vẫn cần CQL hợp lệ với primary key, clustering và topology. Một câu lệnh có thể đúng cú pháp Java nhưng không hợp lệ hoặc quá đắt khi chạy trên database.

## 2. Phân biệt bind value và CQL identifier

| Thành phần câu CQL | Ví dụ | Có thể thay bằng bind marker `?`? |
|---|---|---|
| Giá trị partition key | UUID của `customer_id` | **Có** |
| Giá trị bucket | Ngày của `bucket_month` | **Có** |
| Giá trị so sánh | `state = ?`, `placed_at >= ?` | **Có** |
| Giá trị ghi | `SET total_minor = ?` | **Có** |
| Một số giá trị giới hạn | `LIMIT ?` khi driver/CQL hỗ trợ | **Có** |
| Tên bảng | `orders_by_customer_month` | **Không** |
| Tên keyspace | `shop_prod` | **Không** |
| Tên cột | `customer_id`, `state` | **Không** |
| Danh sách cột SELECT | `order_id, state` | **Không** |
| Cột sắp xếp | `ORDER BY placed_at` | **Không** |
| Từ khóa và đoạn CQL | `DESC`, `ALLOW FILTERING` | **Không** |

Hai ví dụ không hợp lệ:

```sql
-- Không thể bind một tên bảng.
SELECT * FROM ? WHERE customer_id = ?;

-- Không thể bind một tên cột để ORDER BY.
SELECT * FROM orders_by_customer_month
WHERE customer_id = ? AND bucket_month = ?
ORDER BY ? DESC;
```

Khi gọi `session.prepare(...)`, Cassandra parse một **cấu trúc CQL đã xác định**. Bind marker biểu diễn một giá trị có kiểu CQL ở các vị trí hỗ trợ; nó không được parse lại thành bảng, tên cột hoặc keyword. Vì vậy, dùng prepared statement cho UUID nhưng nối tên bảng từ HTTP request vẫn là một **đường đưa input không tin cậy vào cấu trúc CQL**.

### Vì sao regex không đủ?

Kiểm tra identifier chỉ chứa chữ, số và dấu gạch dưới có thể giúp tránh lỗi ký tự, nhưng **không xác định quyền hoặc phạm vi bảng**. Ví dụ một tên bảng có cú pháp hoàn toàn hợp lệ vẫn có thể là bảng chứa dữ liệu hệ thống, bảng archive nhạy cảm hoặc bảng của tenant khác. Cần allowlist theo **ngữ nghĩa nghiệp vụ**, không chỉ lọc ký tự.

## 3. Một schema mẫu để thấy các lựa chọn an toàn

Giả sử API có thể đọc đơn hàng từ hai nguồn:

- **CURRENT**: bảng đang hoạt động `orders_by_customer_month`.
- **ARCHIVE**: bảng lưu trữ `archived_orders_by_customer_month`.

Cả hai có cùng cấu trúc để trả danh sách theo khách hàng và tháng:

```sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    bucket_month date,
    placed_at timestamp,
    order_id uuid,
    state text,
    total_minor bigint,
    PRIMARY KEY ((customer_id, bucket_month), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);

CREATE TABLE archived_orders_by_customer_month (
    customer_id uuid,
    bucket_month date,
    placed_at timestamp,
    order_id uuid,
    state text,
    total_minor bigint,
    PRIMARY KEY ((customer_id, bucket_month), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
```

Trong cả hai bảng, `(customer_id, bucket_month)` là **composite partition key**; `placed_at` và `order_id` là clustering columns. Với câu hỏi “20 đơn gần nhất của khách X trong tháng M”, truy vấn cung cấp **đủ hai thành phần partition key** rồi dựa vào clustering order để lấy kết quả mới nhất trước.

```sql
SELECT order_id, placed_at, state, total_minor
FROM orders_by_customer_month
WHERE customer_id = ?
  AND bucket_month = ?
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Tách bảng current/archive chỉ là thiết kế minh họa. Trong hệ thống thật, cần quyết định cách chuyển dữ liệu, tính nhất quán giữa bảng, retention, quyền truy cập và chi phí schema. Không mặc nhiên khuyến nghị tạo bảng mới cho mỗi tenant hoặc mỗi yêu cầu API.

## 4. Những cách ghép CQL không an toàn

Ví dụ sai:

```java
// KHÔNG dùng với input trực tiếp từ request.
String cql =
    "SELECT order_id, placed_at, state, total_minor " +
    "FROM " + tableFromRequest + " " +
    "WHERE customer_id = ? AND bucket_month = ?";
```

Ngay cả khi `customerId` và `bucketMonth` được bind, biến `tableFromRequest` đã trở thành một phần **cú pháp** của statement.

Sai tương tự với tên cột:

```java
// requestedColumn chưa được kiểm soát.
String cql =
    "SELECT " + requestedColumn + " " +
    "FROM orders_by_customer_month " +
    "WHERE customer_id = ? AND bucket_month = ?";
```

Các vấn đề:

1. Client có thể chọn một bảng/cột ngoài phạm vi nghiệp vụ dự kiến.
2. Chuỗi không hợp lệ có thể làm truy vấn parse lỗi.
3. Việc ghép cú pháp mở ra khả năng CQL injection tùy cách xây statement.
4. Nhiều mẫu CQL không giới hạn làm tăng prepared statement cache và khó giám sát.
5. Một column hợp lệ cho SELECT **chưa chắc** hợp lệ trong ORDER BY.
6. Các cột khác kiểu CQL có thể phá vỡ một `RowMapper` duy nhất.

**Không giải quyết bằng cách quote hoặc escape chung chung toàn bộ input.** Identifier được phép phải là một giá trị đã được code phê duyệt, đồng thời còn chịu kiểm tra quyền.

## 5. Cách ưu tiên: nhiều @Query cố định, service chọn repository

Với một số ít bảng, việc khai báo từng repository và CQL cố định thường đơn giản nhất.

Repository cho current:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface CurrentOrderRepository
        extends CassandraRepository<CurrentOrder, CustomerMonthOrderKey> {

    @Query("SELECT * FROM orders_by_customer_month " +
           "WHERE customer_id = ?0 AND bucket_month = ?1 LIMIT 20")
    List<CurrentOrder> recent(UUID customerId, LocalDate month);
}
```

Repository cho archive:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface ArchivedOrderRepository
        extends CassandraRepository<ArchivedOrder, CustomerMonthOrderKey> {

    @Query("SELECT * FROM archived_orders_by_customer_month " +
           "WHERE customer_id = ?0 AND bucket_month = ?1 LIMIT 20")
    List<ArchivedOrder> recent(UUID customerId, LocalDate month);
}
```

Hai kiểu `CurrentOrder` và `ArchivedOrder` được giả định có `@Table` mapping đến bảng tương ứng. `CustomerMonthOrderKey` là key class phản ánh cả partition và clustering components; các lớp này cần được định nghĩa đúng trong ứng dụng thật.

Định nghĩa enum lựa chọn:

```java
public enum OrderDataset {
    CURRENT,
    ARCHIVE
}
```

Service điều phối:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final CurrentOrderRepository current;
    private final ArchivedOrderRepository archived;

    public OrderReadService(
            CurrentOrderRepository current,
            ArchivedOrderRepository archived) {
        this.current = current;
        this.archived = archived;
    }

    public List<OrderSummary> recent(
            OrderDataset source, UUID customerId, LocalDate month) {

        if (source == null || customerId == null || month == null) {
            throw new IllegalArgumentException("Missing query context");
        }

        return switch (source) {
            case CURRENT -> current.recent(customerId, month)
                .stream().map(OrderSummary::fromCurrent).toList();
            case ARCHIVE -> archived.recent(customerId, month)
                .stream().map(OrderSummary::fromArchive).toList();
        };
    }
}
```

`OrderSummary` cùng các factory `fromCurrent`/`fromArchive` là DTO conversion do ứng dụng triển khai, không phải method tự động của Spring Data. Với Java 17+, cú pháp `switch` expression và `Stream.toList()` phù hợp; cần kiểm tra source level của dự án.

**Điểm mạnh:** không có chỗ nào biến input người dùng thành tên bảng. Code chỉ định rõ câu truy vấn và entity mapping của từng bảng. Khi thêm bảng mới, cần một thay đổi code được kiểm soát và test.

## 6. Parse request thành enum, không thành tên bảng

Giả sử API nhận `source=current` hoặc `source=archive`. Hãy chuyển chuỗi sang **enum hữu hạn**, rồi chuyển enum sang hành động phù hợp:

```java
import java.util.Locale;

public static OrderDataset parseDataset(String input) {
    if (input == null) {
        throw new IllegalArgumentException("source is required");
    }

    return switch (input.toLowerCase(Locale.ROOT)) {
        case "current" -> OrderDataset.CURRENT;
        case "archive" -> OrderDataset.ARCHIVE;
        default -> throw new IllegalArgumentException(
            "Unsupported dataset");
    };
}
```

Các giá trị khác đều bị từ chối. Không sử dụng lại `input` nguyên văn trong câu CQL sau khi parse. Có thể so khớp hoa/thường chính xác nếu đó là hợp đồng API, nhưng phải giữ **tập tên được chấp nhận hữu hạn**.

| Lớp kiểm soát | Tác dụng |
|---|---|
| Parse enum/allowlist | Không cho input tạo identifier hay query pattern tùy ý |
| Authorization theo role | Quyết định ai được phép chọn CURRENT/ARCHIVE |
| Kiểm tra tenant/customer | Đảm bảo partition key thuộc phạm vi dữ liệu người dùng có quyền |
| Quyền Cassandra account | Hạn chế quyền CQL của tài khoản service, giảm hậu quả lỗi |
| Query-driven design | Đảm bảo query không scan rộng dù tên bảng hợp lệ |

**Allowlist không phải authorization.** Một người dùng chỉ được phép đọc current vẫn phải bị từ chối khi yêu cầu archive, dù archive có trong enum.

## 7. Nếu muốn dùng chung một DAO: chọn CQL constants qua CqlOperations

Một DAO có thể giữ hai câu CQL cố định và chọn tại runtime. Khi đó dùng `CqlOperations`/`CqlTemplate` để bind tham số và trả DTO qua `RowMapper`.

```java
import java.time.Instant;
import java.util.UUID;

public record OrderSummary(
    UUID orderId,
    Instant placedAt,
    String state,
    Long totalMinor
) {}
```

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public class SafeOrderCqlDao {
    private static final String CURRENT_CQL =
        "SELECT order_id, placed_at, state, total_minor " +
        "FROM orders_by_customer_month " +
        "WHERE customer_id = ? AND bucket_month = ? LIMIT ?";

    private static final String ARCHIVE_CQL =
        "SELECT order_id, placed_at, state, total_minor " +
        "FROM archived_orders_by_customer_month " +
        "WHERE customer_id = ? AND bucket_month = ? LIMIT ?";

    private final CqlOperations cql;

    public SafeOrderCqlDao(CqlOperations cql) {
        this.cql = cql;
    }

    public List<OrderSummary> recent(
            OrderDataset source, UUID customerId,
            LocalDate month, int requestedLimit) {

        if (source == null || customerId == null || month == null) {
            throw new IllegalArgumentException("Missing query context");
        }
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }

        String statement = switch (source) {
            case CURRENT -> CURRENT_CQL;
            case ARCHIVE -> ARCHIVE_CQL;
        };

        return cql.query(
            statement,
            (row, rowNum) -> new OrderSummary(
                row.getUuid("order_id"),
                row.getInstant("placed_at"),
                row.getString("state"),
                row.isNull("total_minor")
                    ? null : row.getLong("total_minor")
            ),
            customerId, month, requestedLimit
        );
    }
}
```

Đoạn mã minh họa overload `CqlOperations.query(String, RowMapper<T>, Object... args)` ở các dòng Spring Data Cassandra hỗ trợ; cần đối chiếu chữ ký với dependency thực tế. Hai kiểu `public` nằm ở các tệp Java riêng. Spring Data Cassandra tự thực hiện CQL binding qua infrastructure; phần mapper chủ động chuyển các cột thành DTO.

**Điểm an toàn nằm ở** `statement`: nó chỉ nhận `CURRENT_CQL` hoặc `ARCHIVE_CQL`, không bao giờ nhận chuỗi tạo từ tên bảng do client gửi. Các giá trị `UUID`, `LocalDate`, `int` được bind bằng cơ chế của driver.

**Điểm vận hành:** số mẫu CQL hữu hạn giúp tái sử dụng prepared statement và đo latency theo query pattern. Nếu hệ thống sinh hàng nghìn tên bảng từ input, cần xem lại mô hình schema và cách phân vùng dữ liệu, thay vì mở rộng allowlist vô hạn.

## 8. Danh sách cho phép cột: phân biệt projection và data type

Khi một API chỉ cần chọn một số cột đọc, có thể định nghĩa enum chứa **identifier constant được lập trình viên duyệt**:

```java
public enum OrderColumn {
    STATE("state"),
    TOTAL_MINOR("total_minor");

    private final String cqlName;

    OrderColumn(String cqlName) {
        this.cqlName = cqlName;
    }

    public String cqlName() {
        return cqlName;
    }
}
```

Một phương thức dựng câu CQL từ enum:

```java
public String selectColumn(OrderColumn column) {
    if (column == null) {
        throw new IllegalArgumentException("column is required");
    }

    return "SELECT " + column.cqlName() + " " +
           "FROM orders_by_customer_month " +
           "WHERE customer_id = ? AND bucket_month = ? LIMIT 20";
}
```

Nối chuỗi ở đây chỉ được chấp nhận vì `column.cqlName()` **không bắt nguồn trực tiếp từ input chưa tin cậy** mà từ một tập literal cố định trong code. Nhưng cần lưu ý:

- `state text` tương ứng Java `String`; `total_minor bigint` tương ứng `Long`. Không dùng một `row.getString(...)` cho mọi lựa chọn.
- Tên cột cho phép ở `SELECT` chưa chắc là cột được phép tiết lộ cho mọi vai trò.
- Các mẫu query được phép nên được test với schema thực tế, đặc biệt khi dùng identifier có quote.
- Với ít lựa chọn, **hai câu SELECT cố định và hai mapper riêng** thường rõ ràng hơn một framework chọn cột động.

Allowlist cho projection không nên tự động được tái sử dụng làm allowlist cho `ORDER BY`, `GROUP BY` hoặc mutation: **mỗi ngữ cảnh CQL có quy tắc riêng**.

## 9. ORDER BY: chỉ cho phép tổ hợp clustering hợp lệ

Với bảng có clustering order `placed_at DESC, order_id DESC`, hai kiểu sắp xếp hợp lệ thường là chiều mặc định và chiều đảo tổng thể:

```java
public enum OrderSort {
    NEWEST("ORDER BY placed_at DESC, order_id DESC"),
    OLDEST("ORDER BY placed_at ASC, order_id ASC");

    private final String clause;

    OrderSort(String clause) {
        this.clause = clause;
    }

    public String clause() {
        return clause;
    }
}
```

Dựng từ enum:

```java
public String recentQuery(OrderSort sort) {
    if (sort == null) {
        throw new IllegalArgumentException("sort is required");
    }

    return "SELECT order_id, placed_at, state, total_minor " +
           "FROM orders_by_customer_month " +
           "WHERE customer_id = ? AND bucket_month = ? " +
           sort.clause() + " LIMIT ?";
}
```

Đây là ví dụ **allowlist toàn bộ mệnh đề ORDER BY**, không chỉ tên cột. Không tự ghép `sortColumn` và `sortDirection` từ hai chuỗi tùy ý rồi cho phép mọi tổ hợp.

Ví dụ sai về mặt mô hình CQL dù tên cột `state` hợp lệ để đọc:

```sql
SELECT *
FROM orders_by_customer_month
WHERE customer_id = ?
  AND bucket_month = ?
ORDER BY state ASC;
```

`state` là cột thường, không phải clustering key. Cassandra không sắp xếp arbitrary columns theo cách SQL quan hệ làm trên một tập kết quả. Muốn sắp theo tổng tiền hoặc trạng thái, cần thiết kế bảng theo truy vấn hoặc dùng hệ thống phân tích/tìm kiếm phù hợp.

Với clustering nhiều cột và chiều ASC/DESC hỗn hợp, chỉ cho phép những thứ tự mà Cassandra và schema thực tế chấp nhận. **Allowlist tên cột không làm thay đổi ràng buộc của storage engine.**

## 10. PreparedStatement: chuẩn bị sẵn những biến thể được phép

Nếu ứng dụng cần đường đọc nhanh, Java Driver có thể prepare từng câu CQL cụ thể rồi bind giá trị khác nhau mỗi request.

```java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class PreparedOrderReader {
    private final CqlSession session;
    private final PreparedStatement newest;
    private final PreparedStatement oldest;

    public PreparedOrderReader(CqlSession session) {
        this.session = session;

        String base =
            "SELECT order_id, placed_at, state, total_minor " +
            "FROM orders_by_customer_month " +
            "WHERE customer_id = ? AND bucket_month = ? ";

        this.newest = session.prepare(
            base + "ORDER BY placed_at DESC, order_id DESC LIMIT ?");
        this.oldest = session.prepare(
            base + "ORDER BY placed_at ASC, order_id ASC LIMIT ?");
    }

    public ResultSet find(
            OrderSort sort, UUID customerId,
            LocalDate month, int limit) {

        if (sort == null || customerId == null || month == null) {
            throw new IllegalArgumentException("Missing query context");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }

        PreparedStatement query = switch (sort) {
            case NEWEST -> newest;
            case OLDEST -> oldest;
        };

        return session.execute(query.bind(customerId, month, limit));
    }
}
```

**Chỉ có hai PreparedStatement đã xác định trong code**. Giá trị `customerId`, `month`, `limit` được bind; tên bảng, cột và thứ tự không thay đổi tùy input. Trong Spring Boot, nên inject `CqlSession` được quản lý thay vì tạo session mới cho mỗi request. Lựa chọn statement options như consistency, page size hoặc timeout không thay thế kiểm tra quyền hay partition key.

## 11. Cách xử lý multi-tenant và keyspace động

Một hệ thống nhiều tenant đôi khi có schema kiểu:

```text
tenant_a.orders_by_customer_month
tenant_b.orders_by_customer_month
```

Ở đây `tenant_a` và `tenant_b` là keyspace. Keyspace cũng là **identifier**, không thể thay bằng một bind marker.

Không làm như sau:

```java
// KHÔNG làm: tenant keyspace do client tự khai.
String cql = "SELECT * FROM " + requestTenant +
             ".orders_by_customer_month " +
             "WHERE customer_id = ?";
```

Ngay cả khi tên keyspace thuộc một allowlist hợp lệ, người dùng tenant A không được chọn tenant B. Quy trình đúng về nguyên tắc:

1. **Xác thực** actor từ token/session đáng tin cậy.
2. Xác định **tenant được cấp quyền** phía server, không tin một giá trị tùy ý trong request.
3. Kiểm tra quyền truy cập bảng/dataset current, archive hoặc cột nhạy cảm.
4. Chọn một cấu hình keyspace/session/query đã được ứng dụng quản lý; không nối chuỗi tenant thô.
5. Bind `customer_id`, `bucket_month` và dữ liệu nghiệp vụ.
6. Dùng quyền Cassandra account theo nguyên tắc **least privilege** khi khả thi.
7. Log audit theo query type, actor, tenant mà không làm lộ nội dung nhạy cảm.

Nếu ứng dụng phân vùng theo `tenant_id` thay vì tách keyspace, phải bảo đảm tenant ID từ ngữ cảnh xác thực được đưa vào partition key và không để client tự đổi tenant khác. Khả năng chịu lỗi, RF và tính nhất quán của Cassandra **không thay thế kiểm soát truy cập dữ liệu**.

## 12. Quoted identifiers và escaping không thay thế allowlist

Cassandra phân biệt identifier không quote và quoted identifier. Ví dụ:

```sql
-- Tên thông thường, phù hợp naming convention lowercase.
SELECT state FROM orders_by_customer_month;

-- Tên được quote cần khớp chính xác schema đã tạo.
SELECT "DisplayName" FROM "CaseSensitiveTable";
```

Bọc dấu nháy kép không làm một bảng tùy ý thành bảng được cấp phép. Quoting sai còn có thể khiến query không parse được hoặc trỏ đến tên phân biệt hoa/thường khác. Tốt nhất:

- Dùng tên bảng/cột chữ thường, dấu gạch dưới và naming convention ổn định.
- Nếu cần quoted identifier, giữ nguyên spelling và quote trong **CQL constant đã review**.
- Không dùng một hàm escape cho string value làm hàm escape identifier.
- Không coi kiểm tra “ký tự hợp lệ” là bằng chứng người dùng có quyền đọc.

CQL identifier và bind literal là hai loại thành phần khác nhau; không nên cố mô phỏng một thứ bằng cách xử lý string của thứ còn lại.

## 13. Allowlist phải đi cùng query-driven design

Một câu truy vấn có thể dùng bảng/cột hợp lệ nhưng vẫn không có access path tốt:

```sql
SELECT *
FROM orders_by_customer_month
WHERE state = 'PAID'
ALLOW FILTERING;
```

Nếu chỉ lọc theo `state`, bảng phân vùng bằng `customer_id + bucket_month` không cho Cassandra một partition cụ thể. Query có thể quét/lọc dữ liệu rộng, và `LIMIT 20` không đồng nghĩa chỉ đọc 20 hàng trên đĩa. Một allowlist tốt phải duyệt cả **tính hợp lệ và chi phí CQL**.

| Câu hỏi | Ý nghĩa |
|---|---|
| Có đủ partition key chưa? | Đọc một partition xác định hay fan-out? |
| Clustering prefix có phù hợp chưa? | Điều kiện range/sort có được schema hỗ trợ? |
| Có cần một bảng đọc khác không? | Tránh `ALLOW FILTERING` cho đường đọc chính |
| Kích thước partition ra sao? | Tránh hot/wide partition |
| Có bao nhiêu dataset và query pattern? | Tránh prepared cache/schema tăng vô hạn |
| Có cần paging? | Tránh materialize mọi hàng vào một `List` |
| Consistency và RF đúng không? | Đảm bảo mức phục vụ mong muốn |
| Tombstone/TTL có nhiều không? | `LIMIT` nhỏ chưa chắc giúp giảm chi phí |

Nếu nghiệp vụ cần toàn bộ đơn ở trạng thái PAID trên toàn hệ thống, hãy thiết kế projection theo trạng thái + bucket + shard hoặc sử dụng hệ thống tìm kiếm/analytics phù hợp. Việc thêm `state` vào allowlist SELECT **không** biến `WHERE state = ?` thành query hiệu quả.

## 14. LIMIT, paging và các tùy chọn khác

Khi người dùng chọn source/sort, họ thường cũng muốn chọn giới hạn kết quả. Cần phân biệt:

| Cơ chế | Ý nghĩa |
|---|---|
| `LIMIT n` | Giới hạn **tổng số hàng trả về** từ câu SELECT |
| `PER PARTITION LIMIT n` | Giới hạn số hàng **trong từng partition** nếu CQL hỗ trợ |
| `QueryOptions.pageSize(n)` | Kích thước trang **fetch** của driver |
| `Pageable` và `Slice` | API phân trang Spring Data theo cơ chế Cassandra |
| Driver paging state | Token opaque để tiếp tục cùng query và ngữ cảnh |

Giới hạn `1..100` trong DAO chỉ là ví dụ chính sách API. Một số CQL version cho phép bind marker cho LIMIT; nếu dùng phiên bản không hỗ trợ hoặc cú pháp đặc thù, cần kiểm tra driver/server thay vì nối input không kiểm soát. Không thiết kế API “trang thứ 1000” bằng cách giả định Cassandra có OFFSET rẻ như SQL.

`QueryOptions`, consistency và routing metadata tác động **thực thi**, không tạo ra một identifier an toàn hay sửa câu query thiếu partition key. Một query được định tuyến token-aware vẫn có thể vi phạm quyền nghiệp vụ nếu chọn sai dataset.

## 15. Kiểm thử đầu vào lạ, quyền truy cập và cấu trúc query

Một unit test đơn giản cho parser:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class OrderDatasetParserTest {

    @Test
    void acceptsAllowedValues() {
        assertEquals(OrderDataset.CURRENT, parseDataset("current"));
        assertEquals(OrderDataset.ARCHIVE, parseDataset("archive"));
    }

    @Test
    void rejectsUnexpectedValues() {
        assertThrows(IllegalArgumentException.class,
            () -> parseDataset("unapproved_table"));
        assertThrows(IllegalArgumentException.class,
            () -> parseDataset("current extra"));
        assertThrows(IllegalArgumentException.class,
            () -> parseDataset(null));
    }
}
```

Khung test giả định `parseDataset` được định nghĩa trong lớp parser thực tế; khi copy cần import hoặc gọi qua lớp ấy. Các test tích hợp cần Cassandra test, entity/repository và môi trường seed phù hợp.

Các ca phải có:

| Ca | Kết quả mong đợi |
|---|---|
| CURRENT với đúng khách/tháng | Chỉ truy cập bảng current và partition yêu cầu |
| ARCHIVE khi role có quyền | Được phép truy cập bảng archive |
| ARCHIVE khi role không có quyền | Bị từ chối **dù enum hợp lệ** |
| Dataset lạ | Bị từ chối **trước khi tạo CQL** |
| Column hoặc sort lạ | Không được truyền nguyên văn vào câu query |
| Truy vấn thiếu `bucket_month` | Không thay bằng scan hay `ALLOW FILTERING` |
| `limit` âm, bằng 0, quá cao | Bị từ chối theo hợp đồng |
| Sort NEWEST / OLDEST | Trả hàng theo clustering order/đảo chiều |
| Query đọc cột khác kiểu | Mapper xử lý đúng `text` và `bigint` |
| Đổi schema/keyspace | Các mẫu query, quyền và converter được kiểm tra lại |

Test nên kiểm tra **CQL pattern được chọn**, bind values và quyền, không chỉ so sánh một vài object Java sau khi đọc. Nếu cần tracing, chỉ bật có chọn lọc trong lab hoặc một tập nhỏ yêu cầu để tránh overhead và rủi ro lộ dữ liệu.

## 16. Giám sát và giới hạn chi phí khi mở rộng

Một hệ thống dùng allowlist tốt có **số lượng mẫu query hữu hạn**, giúp lập dashboard theo mã truy vấn:

```text
query_type=ORDERS_BY_CUSTOMER_MONTH
source=CURRENT
sort=NEWEST
consistency=LOCAL_QUORUM
page_size=50
result_rows=20
```

Các giá trị trên chỉ là ví dụ, không phải kết quả đo thật. Nên theo dõi:

1. Số query pattern được prepare và tái sử dụng.
2. Latency p50/p95/p99 theo dataset và loại query.
3. Timeout/retry, số replica còn hoạt động và CL.
4. Số partition được truy vấn, fan-out và concurrency.
5. Dung lượng row, page size và số trang fetch.
6. Hot partition, tombstone, compaction và disk I/O.
7. Số lần reject input lạ và thất bại authorization.

Không log toàn bộ CQL cùng dữ liệu nhạy cảm chỉ để debug allowlist. Truy vấn có thể được phép về identifier nhưng vẫn tạo tải quá lớn nếu partition key hoặc giới hạn concurrency không phù hợp.

## 17. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| `FROM ` + input thô | Identifier bị client điều khiển | Enum → query constant |
| `ORDER BY ` + field thô | Injection hoặc sort không hợp lệ | Allowlist toàn bộ sort clause |
| Dùng `?` cho tên bảng | CQL không hỗ trợ bind identifier | Chọn một câu query đã định nghĩa |
| Chỉ kiểm tra regex | Tên hợp lệ vẫn có thể trái phép | Semantic allowlist và quyền |
| Dùng chung role cho mọi dataset | Có thể lộ archive/tenant | Authorization trước khi chọn query |
| Cho phép mọi cột SELECT trong ORDER BY | Cassandra không sort tùy ý | Allowlist riêng theo clustering key |
| Dùng một RowMapper cho mọi kiểu cột | Lỗi conversion hoặc kết quả sai | Mapper theo projection |
| `LIMIT 10` để sửa query scan | Chi phí đọc vẫn có thể lớn | Thiết kế bảng theo truy vấn |
| Prepare theo chuỗi bảng tự do | Nhiều statement pattern, cache pressure | Giới hạn mẫu CQL |
| Tenant keyspace từ request | Truy cập chéo tenant | Server-side tenant resolution |
| Chỉ test input hợp lệ | Bỏ sót lỗi bảo mật/vận hành | Negative tests và integration tests |

## 18. Checklist khi mở một lựa chọn bảng/cột mới

1. Input nào đến từ client? Có identifier, source, sort hoặc keyspace không?
2. Mọi dữ liệu nghiệp vụ có dùng bind marker đúng chỗ không?
3. Mọi identifier đều đến từ **enum/query constant đáng tin cậy** chứ không phải input?
4. Đã kiểm tra quyền truy cập role/tenant cho từng dataset và cột chưa?
5. Đường query có đủ partition key và tuân theo clustering prefix không?
6. ORDER BY đã được giới hạn vào tổ hợp thực sự được CQL/schema hỗ trợ chưa?
7. RowMapper/entity có tương thích kiểu CQL của projection không?
8. Giới hạn hàng, paging và số partition fan-out có hợp lý không?
9. Prepared statement có số lượng hữu hạn và được tái sử dụng không?
10. CqlSession/CqlTemplate có được Spring quản lý vòng đời và cấu hình đúng không?
11. Tài khoản Cassandra có ít đặc quyền nhất theo mô hình triển khai không?
12. Có unit test input lạ, integration test query và test authorization không?
13. Có metrics và log query ID không chứa payload nhạy cảm không?
14. Khi thay schema, đã cập nhật allowlist, code mapping và test chưa?

**Kết luận:** `@Query` phù hợp nhất với **CQL cố định và bind values**. Khi nghiệp vụ cần “tên bảng hoặc cột động”, hãy **chuyển lựa chọn từ input sang tập hữu hạn query/identifier đã được phê duyệt**, rồi gọi repository, CqlOperations hoặc prepared statement tương ứng. Biện pháp này giảm nguy cơ CQL injection và truy cập nhầm dữ liệu, nhưng vẫn phải kết hợp **authorization, thiết kế bảng theo truy vấn, partition key, clustering key, consistency, paging và đo hiệu năng thực tế**.

## Tài liệu tham khảo

- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, bind parameters và repository query methods.
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlOperations`, `CqlTemplate`, `RowMapper`.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): entity, primary key và chuyển đổi property/cột.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/): cú pháp SELECT, identifier, ORDER BY và điều kiện partition key.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): nguyên tắc allowlist cho identifier động; có thể áp dụng tương tự để kiểm soát cấu trúc CQL.
