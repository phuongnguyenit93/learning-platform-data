# Xử lý khóa ghép và khóa do ứng dụng tạo

> **Chương:** CRUD và khóa sinh  
> **Ngữ cảnh:** Ứng dụng Java dùng **JDBC** để thực hiện CRUD qua `DataSource`, `PreparedStatement`, `ResultSet` và transaction, đồng thời bảo đảm toàn vẹn định danh trên cơ sở dữ liệu quan hệ.

Một hóa đơn có thể được xác định bằng cả `tenant_id` và `invoice_id`. Các dòng trong hóa đơn lại cần thêm `line_no` để phân biệt từng sản phẩm. Nếu mã hóa đơn được Java tạo trước khi gọi `INSERT`, lấy khóa bằng `getGeneratedKeys()` có còn cần thiết không? Làm thế nào để cập nhật, xóa và liên kết dữ liệu mà không dùng thiếu một phần khóa?

Đây là hai quyết định **khác nhau nhưng thường xuất hiện cùng lúc**:

- **Khóa ghép (composite key):** định danh một hàng bằng **nhiều cột**; ví dụ `(tenant_id, invoice_id)` hoặc `(tenant_id, invoice_id, line_no)`.
- **Khóa do ứng dụng tạo (application-generated key):** ứng dụng quyết định một hoặc nhiều giá trị khóa trước khi gửi `INSERT`; ví dụ `UUID.randomUUID()` hoặc mã nghiệp vụ được cấp bởi một dịch vụ định danh.

Một khóa ghép có thể chứa khóa do ứng dụng sinh; một khóa đơn cũng có thể do ứng dụng sinh. JDBC không quyết định mô hình định danh thay cho database: **ràng buộc `PRIMARY KEY`, `UNIQUE` và `FOREIGN KEY` trong schema là nguồn bảo vệ toàn vẹn cuối cùng**.

## 1. Chọn định danh phù hợp với nghiệp vụ

| Cách định danh | Ví dụ | Ưu điểm | Điểm cần chú ý |
|---|---|---|---|
| Khóa đơn do database sinh | `order_id BIGINT GENERATED ...` | Đơn giản, database quản lý cấp số | Cần đọc khóa đã sinh khi tạo các bản ghi liên quan; cú pháp tùy DBMS |
| Khóa đơn do ứng dụng sinh | `order_id UUID` | Có ID trước khi lưu, thuận tiện liên kết và phân tán | Ứng dụng phải bảo đảm tạo và tái sử dụng ID hợp lý khi retry |
| Khóa ghép có ngữ nghĩa | `(tenant_id, invoice_id)` | Thể hiện phạm vi sở hữu và ràng buộc trực tiếp trong schema | Mọi khóa ngoại và câu lệnh CRUD phải mang đủ các thành phần |
| Khóa ghép cho quan hệ cha–con | `(tenant_id, invoice_id, line_no)` | `line_no` chỉ cần duy nhất *bên trong* một hóa đơn | Phải quản lý cấp `line_no` khi nhiều giao dịch cùng thêm dòng |

**Chọn khóa theo phạm vi duy nhất thật sự.** Nếu `invoice_id` cần duy nhất trên toàn hệ thống và đã có `tenant_id` ở hàng, khóa đơn `invoice_id` cộng một chỉ mục khác đôi khi phù hợp. Nếu mô hình muốn đảm bảo khóa ngoại luôn giữ cùng tenant và phân vùng dữ liệu theo tenant, `PRIMARY KEY (tenant_id, invoice_id)` thể hiện trực tiếp điều đó. Không chọn khóa ghép chỉ vì bảng có nhiều cột nhận diện, và cũng không mặc định UUID là lựa chọn duy nhất đúng.

Đừng nhầm **khóa chính**, **khóa nghiệp vụ** và **idempotency key**:

- Khóa chính định danh hàng trong database.
- Khóa nghiệp vụ biểu diễn sự duy nhất mà domain yêu cầu, có thể được ràng buộc bằng `UNIQUE`, ví dụ `(tenant_id, invoice_number)`.
- Idempotency key nhận diện **cùng một yêu cầu tạo** khi client gửi lại; nó có thể là một cột/ràng buộc riêng, không nhất thiết trùng khóa chính.

## 2. Schema minh họa: hóa đơn đa tenant

Ví dụ tiếp theo dùng **PostgreSQL** vì hệ quản trị này hỗ trợ kiểu `UUID` và JDBC driver PostgreSQL ánh xạ `java.util.UUID` qua `PreparedStatement.setObject()`. Cú pháp `UUID`, `RETURNING` và khóa ngoại dưới đây thuộc PostgreSQL; để chạy trên MySQL, SQL Server hoặc DBMS khác, cần điều chỉnh schema và cách bind theo driver thực tế.

### 2.1. Bảng cha có khóa ghép, khóa ứng dụng sinh

```sql
CREATE TABLE invoices (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    invoice_number VARCHAR(40) NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tenant_id, invoice_id),
    UNIQUE (tenant_id, invoice_number)
);
```

- `tenant_id` đến từ ngữ cảnh người dùng/khách hàng đã được xác thực.
- `invoice_id` được Java tạo **trước** khi gọi `INSERT`.
- `invoice_number` là mã nghiệp vụ và được kiểm tra duy nhất trong từng tenant, nhưng không phải định danh kỹ thuật được dùng trong code mẫu.
- `version` phục vụ optimistic locking khi hai người cùng chỉnh sửa một hóa đơn.

**Phạm vi duy nhất** của khóa chính là *cặp* `(tenant_id, invoice_id)`. Ràng buộc này không tự bắt buộc `invoice_id` duy nhất trên toàn bảng. UUID v4 được sinh ngẫu nhiên thường có xác suất trùng rất thấp, nhưng vẫn phải giữ `PRIMARY KEY`/`UNIQUE` trong database và xử lý lỗi vi phạm ràng buộc.

### 2.2. Bảng con dùng khóa ghép ba thành phần

```sql
CREATE TABLE invoice_lines (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    PRIMARY KEY (tenant_id, invoice_id, line_no),

    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES invoices (tenant_id, invoice_id)
        ON DELETE CASCADE
);
```

Hai ràng buộc đóng vai trò khác nhau:

1. `PRIMARY KEY (tenant_id, invoice_id, line_no)` ngăn hai dòng có cùng `line_no` trong một hóa đơn.
2. `FOREIGN KEY (tenant_id, invoice_id)` bắt buộc dòng hàng liên kết với hóa đơn có **đúng cả hai** giá trị khóa cha. Không thể tham chiếu riêng `invoice_id` rồi vô tình liên kết sang tenant khác.

`ON DELETE CASCADE` khiến database tự xóa các dòng khi xóa hóa đơn cha. Đây là **quyết định nghiệp vụ**, phù hợp với dữ liệu con không tồn tại độc lập; nếu hệ thống cần giữ lịch sử hoặc không cho xóa hóa đơn có dòng, hãy thiết kế quy tắc khác thay vì sao chép `CASCADE` máy móc.

### 2.3. Quan hệ được hiểu thế nào?

```text
invoices
  PK: (tenant_id, invoice_id)
        │  1
        │
        └───────────────┐
                        │  nhiều
invoice_lines           │
  PK: (tenant_id, invoice_id, line_no)
  FK: (tenant_id, invoice_id) ──────> invoices.PK
```

Ví dụ hai tenant `A` và `B` đều có `invoice_id = X` thì đó là **hai khóa ghép khác nhau**: `(A, X)` và `(B, X)`. Một dòng hàng thuộc `(A, X)` phải liên kết đến hóa đơn ở tenant A, ngay cả khi cũng có hóa đơn `(B, X)`.

## 3. CRUD với khóa ghép: luôn bind đủ thành phần

Truy vấn JDBC cần sử dụng đầy đủ khóa theo đúng phạm vi dữ liệu. Đặc biệt với hệ thống đa tenant, **không nhận tenant từ tham số tự do của người dùng rồi mặc nhiên tin cậy**; ứng dụng phải lấy tenant được phép truy cập từ ngữ cảnh xác thực/ủy quyền.

### 3.1. Tạo bản ghi: tất cả giá trị khóa đều có sẵn

```sql
INSERT INTO invoices (
    tenant_id, invoice_id, invoice_number, customer_name
) VALUES (?, ?, ?, ?);

INSERT INTO invoice_lines (
    tenant_id, invoice_id, line_no, sku, quantity
) VALUES (?, ?, ?, ?, ?);
```

Không cần `Statement.RETURN_GENERATED_KEYS` cho `invoice_id` hoặc `line_no` ở ví dụ này: ứng dụng **đã biết giá trị khóa** trước khi insert. Việc database tự sinh `created_at` và `version` là chuyện khác; chỉ cần đọc chúng về nếu luồng nghiệp vụ thực sự cần.

### 3.2. Đọc theo định danh đầy đủ

```sql
SELECT tenant_id, invoice_id, invoice_number,
       customer_name, version, created_at
FROM invoices
WHERE tenant_id = ?
  AND invoice_id = ?;

SELECT line_no, sku, quantity
FROM invoice_lines
WHERE tenant_id = ?
  AND invoice_id = ?
ORDER BY line_no;
```

Truy vấn dòng hàng theo `(tenant_id, invoice_id)` dùng phần **tiền tố** của khóa chính `(tenant_id, invoice_id, line_no)`. Với PostgreSQL, chỉ mục btree tạo cho khóa chính thường hỗ trợ tốt nhóm truy vấn theo tiền tố này; hãy dùng `EXPLAIN` trên dữ liệu thật để xác nhận kế hoạch truy vấn.

### 3.3. Cập nhật có kiểm soát phiên bản

```sql
UPDATE invoices
SET customer_name = ?,
    version = version + 1
WHERE tenant_id = ?
  AND invoice_id = ?
  AND version = ?;
```

`executeUpdate()` trả về số hàng chịu ảnh hưởng. Với `PRIMARY KEY` và điều kiện như trên, kết quả thông thường là:

- `1`: cập nhật một hóa đơn thành công.
- `0`: không có hàng phù hợp, **hoặc** `version` đã đổi vì giao dịch khác cập nhật trước.

Không nên coi `0` là lỗi database hay tự động ghi đè phiên bản mới hơn. Ứng dụng cần phản hồi xung đột hoặc tra cứu thêm khi cần phân biệt *không tồn tại* với *phiên bản cũ*. Việc tăng `version` trong cùng câu lệnh là cách kiểm tra và cập nhật nguyên tử ở phía database.

### 3.4. Xóa theo khóa đầy đủ

```sql
DELETE FROM invoices
WHERE tenant_id = ?
  AND invoice_id = ?;
```

Với schema minh họa, xóa hóa đơn cũng xóa dòng con nhờ `ON DELETE CASCADE`. **Đừng viết** `DELETE FROM invoices WHERE invoice_id = ?` chỉ vì UUID thường là duy nhất: khóa chính đã mô hình hóa phạm vi tenant và mọi thao tác phải tôn trọng phạm vi đó.

## 4. Biểu diễn khóa ghép trong Java

Java không có một lớp JDBC tiêu chuẩn tự động gom nhiều cột thành khóa ghép. Mỗi ứng dụng nên dùng một kiểu bất biến thể hiện đúng các thành phần khóa:

```java
import java.util.UUID;

public record InvoiceKey(UUID tenantId, UUID invoiceId) {}

public record InvoiceLineKey(
    UUID tenantId,
    UUID invoiceId,
    int lineNo
) {}

public record NewInvoiceLine(
    int lineNo,
    String sku,
    int quantity
) {}
```

Với Java 17+, `record` tự cung cấp `equals()`, `hashCode()` và các accessor dựa trên từng thành phần, nên dễ dùng làm tham số repository hoặc khóa cache. Dù vậy, **một object `InvoiceKey` không thay thế các dấu `?` trong SQL**: vẫn phải bind `tenantId()` và `invoiceId()` riêng biệt theo thứ tự truy vấn.

Nếu cần lưu trong DTO hoặc URL, hãy định nghĩa cách mã hóa/công bố cả hai thành phần rõ ràng. Tránh nối các chuỗi khóa không có quy tắc phân cách và escaping; các cặp như `(ab, c)` và `(a, bc)` có thể tạo cùng chuỗi `abc`.

### 4.1. Sinh khóa ở tầng ứng dụng

```java
import java.util.UUID;

UUID tenantId = authenticatedTenantId; // Từ ngữ cảnh đã được ủy quyền.
UUID invoiceId = UUID.randomUUID();     // UUID phiên bản 4 do Java tạo.
InvoiceKey key = new InvoiceKey(tenantId, invoiceId);

// Dùng cùng key cho toàn bộ hóa đơn, các dòng và kết quả trả về.
```

Tạo khóa **một lần cho một thao tác nghiệp vụ** và truyền xuống DAO. Nếu thao tác bị retry sau timeout, hãy tái sử dụng khóa cũ hoặc idempotency key đã được ghi nhận; gọi `UUID.randomUUID()` một lần nữa trong mỗi lượt retry có thể tạo **hóa đơn thứ hai** khi lượt trước đã commit nhưng client không nhận được phản hồi.

Các chiến lược tạo khóa khác nhau có trade-off riêng:

| Chiến lược | Khi phù hợp | Cần kiểm soát |
|---|---|---|
| `UUID.randomUUID()` (v4) | Tạo ID độc lập mà không cần gọi database trước | UUID ngẫu nhiên có thể làm tăng chi phí chèn chỉ mục so với ID tăng dần; vẫn cần ràng buộc uniqueness |
| UUID có tính thứ tự/ULID | Hệ thống có thư viện và quy ước thống nhất | Thứ tự, tính duy nhất, đồng hồ, tương thích lưu trữ và khả năng đoán ID |
| ID số do ứng dụng/dịch vụ cấp | Cần mã số ngắn hoặc đồng bộ qua dịch vụ cấp số | Trùng node, clock drift, phân vùng mạng và cơ chế cấp phát |
| Mã tự nhiên/khóa nghiệp vụ | Giá trị ổn định, thực sự duy nhất theo domain | Thay đổi nghiệp vụ, format, chuẩn hóa và phạm vi uniqueness |

**Không dùng kết quả của `SELECT MAX(id) + 1` làm trình cấp khóa chung**: hai giao dịch song song có thể cùng đọc một số tối đa rồi cùng cố ghi giá trị kế tiếp. Nếu cần số thứ tự, hãy chọn cơ chế cấp phát có đồng bộ hoặc sequence/identity do DBMS hỗ trợ.

## 5. Ví dụ JDBC đầy đủ: tạo hóa đơn và các dòng trong một transaction

Đoạn mã sau dùng **Java 17+**, **JDBC 4.2+** và PostgreSQL JDBC driver. Giả sử `DataSource` đã được cấu hình và schema ở mục 2 đã tồn tại. Khóa `InvoiceKey` được tạo ở tầng gọi, sau đó truyền nguyên vẹn vào repository. Các câu SQL có dấu `?` để truyền **giá trị**, không nối dữ liệu người dùng trực tiếp vào SQL.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;

// Các record InvoiceKey và NewInvoiceLine được định nghĩa ở mục 4.
public final class InvoiceRepository {
    private final DataSource dataSource;

    public InvoiceRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void create(
            InvoiceKey key,
            String invoiceNumber,
            String customerName,
            List<NewInvoiceLine> lines
    ) throws SQLException {
        Objects.requireNonNull(key);
        Objects.requireNonNull(invoiceNumber);
        Objects.requireNonNull(customerName);
        Objects.requireNonNull(lines);

        String insertInvoice = """
            INSERT INTO invoices (
                tenant_id, invoice_id, invoice_number, customer_name
            ) VALUES (?, ?, ?, ?)
            """;

        String insertLine = """
            INSERT INTO invoice_lines (
                tenant_id, invoice_id, line_no, sku, quantity
            ) VALUES (?, ?, ?, ?, ?)
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement ps =
                        connection.prepareStatement(insertInvoice)) {
                    ps.setObject(1, key.tenantId());  // PostgreSQL UUID
                    ps.setObject(2, key.invoiceId());
                    ps.setString(3, invoiceNumber);
                    ps.setString(4, customerName);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Insert invoice failed");
                    }
                }

                try (PreparedStatement ps =
                        connection.prepareStatement(insertLine)) {
                    for (NewInvoiceLine line : lines) {
                        ps.setObject(1, key.tenantId());
                        ps.setObject(2, key.invoiceId());
                        ps.setInt(3, line.lineNo());
                        ps.setString(4, line.sku());
                        ps.setInt(5, line.quantity());
                        ps.addBatch();
                    }

                    int[] counts = ps.executeBatch();
                    if (counts.length != lines.size()) {
                        throw new SQLException("Incomplete line batch");
                    }
                    for (int count : counts) {
                        // SUCCESS_NO_INFO (-2) vẫn có thể là thành công.
                        if (count == 0 ||
                                count == Statement.EXECUTE_FAILED) {
                            throw new SQLException("Insert line failed");
                        }
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    public Optional<String> findCustomerName(InvoiceKey key)
            throws SQLException {
        String sql = """
            SELECT customer_name
            FROM invoices
            WHERE tenant_id = ? AND invoice_id = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, key.tenantId());
            ps.setObject(2, key.invoiceId());
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next()
                    ? Optional.of(rs.getString("customer_name"))
                    : Optional.empty();
            }
        }
    }

    public boolean renameIfVersion(
            InvoiceKey key,
            int expectedVersion,
            String newName
    ) throws SQLException {
        String sql = """
            UPDATE invoices
            SET customer_name = ?, version = version + 1
            WHERE tenant_id = ? AND invoice_id = ? AND version = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, newName);
            ps.setObject(2, key.tenantId());
            ps.setObject(3, key.invoiceId());
            ps.setInt(4, expectedVersion);
            return ps.executeUpdate() == 1;
        }
    }

    public boolean delete(InvoiceKey key) throws SQLException {
        String sql = """
            DELETE FROM invoices
            WHERE tenant_id = ? AND invoice_id = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, key.tenantId());
            ps.setObject(2, key.invoiceId());
            return ps.executeUpdate() == 1;
        }
    }
}
```

Ví dụ gọi repository:

```java
InvoiceKey key = new InvoiceKey(
    authenticatedTenantId,
    UUID.randomUUID()
);

List<NewInvoiceLine> lines = List.of(
    new NewInvoiceLine(1, "BOOK-JAVA", 2),
    new NewInvoiceLine(2, "BOOK-SQL", 1)
);

InvoiceRepository repository = new InvoiceRepository(dataSource);
repository.create(key, "INV-2026-001", "Khách hàng A", lines);

System.out.println(repository.findCustomerName(key));
// Optional[Khách hàng A]

boolean renamed = repository.renameIfVersion(
    key, 0, "Khách hàng A (đã cập nhật)"
);
```

Vì `invoice_id` có trước thao tác ghi, repository có thể liên kết bảng cha và con mà **không cần** gọi `getGeneratedKeys()`. Trong ví dụ này, kết quả của `create()` chỉ có ý nghĩa khi `commit()` đã hoàn tất. Nếu insert dòng con bị lỗi khóa ngoại, trùng `line_no` hoặc giá trị `quantity` vi phạm `CHECK`, transaction cần rollback cả hóa đơn cha.

**Lưu ý về connection:** phương thức `create` sở hữu một connection riêng và đóng nó khi hoàn thành. Trong hệ thống dùng pool, cần cấu hình/kiểm tra cơ chế khôi phục trạng thái connection (đặc biệt `autoCommit`) khi trả vào pool. Ví dụ cũng minh họa việc giữ nguyên lỗi gốc nếu rollback thất bại, bằng cách bổ sung lỗi rollback vào `suppressed exceptions`. Nếu `commit` báo lỗi do mất kết nối, trạng thái giao dịch đôi khi **không thể xác định từ client**; cần dùng khóa yêu cầu ổn định và tra cứu/reconcile trước khi gửi lại thao tác tạo.

### Phân biệt số hàng trả về với trạng thái nghiệp vụ

`executeUpdate() == 0` trong `UPDATE` có thể có nghĩa hàng không tồn tại hoặc phiên bản đã thay đổi; một phép `DELETE` trả về `0` cũng có thể có nghĩa hàng đã bị xóa từ trước. Không gom mọi trường hợp vào một exception chung. API tầng service nên quyết định rõ có trả `404`, `409` hoặc xử lý xóa idempotent hay không dựa trên hợp đồng nghiệp vụ.

Với batch, kết quả `Statement.SUCCESS_NO_INFO` có thể xuất hiện khi driver biết câu lệnh đã thực thi nhưng không cung cấp số hàng cụ thể. Lỗi batch thường làm `executeBatch()` ném `BatchUpdateException`; đừng kết luận transaction thành công chỉ vì một vài phần tử đầu trả về số dương. **Chỉ commit sau khi toàn bộ nhóm thao tác đã qua kiểm tra.**

## 6. Cấp số thứ tự cho thành phần khóa ghép một cách an toàn

Khóa do ứng dụng tạo không nhất thiết là UUID. Trong `invoice_lines`, `line_no` do ứng dụng chỉ định và có phạm vi **mỗi hóa đơn**.

Nếu tất cả dòng được tạo một lần cùng hóa đơn, ứng dụng có thể đánh số `1, 2, 3, ...` trong một transaction như ví dụ. Nếu nhiều request cùng **thêm dòng** vào một hóa đơn đang tồn tại, cách sau dễ gây race condition:

```sql
-- Không an toàn khi nhiều transaction cùng thêm dòng:
SELECT COALESCE(MAX(line_no), 0) + 1
FROM invoice_lines
WHERE tenant_id = ?
  AND invoice_id = ?;
```

Hai giao dịch có thể cùng thấy `MAX(line_no) = 5` rồi cùng chọn `6`. Ràng buộc `PRIMARY KEY` sẽ chặn một trong hai, nhưng thao tác có thể thất bại và cần retry. Để cấp `line_no` tuần tự một cách có kiểm soát trên PostgreSQL, có thể khóa hàng cha **trước khi** tính số tiếp theo:

```sql
BEGIN;

-- Tất cả luồng ghi phải áp dụng cùng quy ước khóa hàng cha.
SELECT 1
FROM invoices
WHERE tenant_id = ? AND invoice_id = ?
FOR UPDATE;

SELECT COALESCE(MAX(line_no), 0) + 1 AS next_line_no
FROM invoice_lines
WHERE tenant_id = ? AND invoice_id = ?;

INSERT INTO invoice_lines (
    tenant_id, invoice_id, line_no, sku, quantity
) VALUES (?, ?, ?, ?, ?);

COMMIT;
```

Đây là **một chuỗi thao tác phải chạy trong cùng transaction, cùng connection**, không phải bốn query độc lập qua các connection khác nhau. Luồng gọi phải kiểm tra câu `SELECT ... FOR UPDATE` thật sự tìm được hóa đơn cha trước khi tính số dòng. Mọi writer thêm dòng cần tuân thủ quy ước khóa này; nếu bỏ khóa ở một luồng, vẫn có thể xảy ra tranh chấp. Với hệ quản trị và mức isolation khác, cần kiểm tra lại hành vi khóa và retry.

Nếu nhiều luồng phải thêm dòng với lưu lượng cao, nên đánh giá cách định danh khác (chẳng hạn ID riêng cho dòng, đồng thời giữ `line_no` như thuộc tính thứ tự được quản lý) hoặc cơ chế cấp số chuyên dụng. Đừng dùng timestamp độ phân giải mili giây làm `line_no`/ID thay thế: nhiều sự kiện có thể cùng một mốc thời gian.

## 7. So sánh với khóa database sinh và `getGeneratedKeys()`

`getGeneratedKeys()` hữu ích khi database **thực sự tạo giá trị cần đọc lại**, ví dụ cột `IDENTITY`/`AUTO_INCREMENT`. Với JDBC:

```java
String sql = "INSERT INTO customers (display_name) VALUES (?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "Khách hàng A");
    if (ps.executeUpdate() != 1) {
        throw new SQLException("Insert failed");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Database returned no generated key");
        }
        long customerId = keys.getLong(1);
        System.out.println(customerId);
    }
}
```

Đoạn này là mẫu JDBC cho trường hợp **schema `customers` có cột ID tự sinh**; cú pháp DDL và hỗ trợ `getGeneratedKeys()` khác nhau theo driver/DBMS. Nó **không được chạy trực tiếp** trên schema hóa đơn ở mục 2 vì `invoice_id` không phải identity do database cấp.

| Tình huống | API/hướng xử lý |
|---|---|
| Ứng dụng đã tạo đầy đủ giá trị khóa chính | Bind tất cả thành phần vào `INSERT`, dùng lại `InvoiceKey`; không cần `getGeneratedKeys()` cho chúng |
| Database tự sinh một khóa identity | `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()` theo hỗ trợ của driver |
| Muốn lấy các cột mặc định hoặc giá trị trả về từ server trong PostgreSQL | `INSERT ... RETURNING ...`, thực thi và đọc `ResultSet` với `executeQuery()` |
| Khóa ghép gồm một phần do app tạo và một phần do DB sinh | App bind phần biết trước; đọc phần DB sinh theo cú pháp/API được driver hỗ trợ; ghép lại thành key đầy đủ |

Ví dụ PostgreSQL trả về cột mặc định mà không thay đổi cách tạo `invoice_id`:

```sql
INSERT INTO invoices (
    tenant_id, invoice_id, invoice_number, customer_name
) VALUES (?, ?, ?, ?)
RETURNING created_at, version;
```

`RETURNING` là cú pháp PostgreSQL, **không thuộc cú pháp SQL được mọi driver JDBC thực thi giống nhau**. Nếu dùng nó, gọi `executeQuery()` và đọc `ResultSet`; nếu chỉ cần biết tạo thành công, `executeUpdate()` với câu `INSERT` không có `RETURNING` là đủ.

### Vì sao không lấy key bằng `SELECT MAX(id)`?

Giữa thao tác insert và câu `SELECT MAX(id)`, giao dịch khác có thể chèn một hàng có ID lớn hơn. Do đó kết quả không xác định được khóa của **hàng vừa chèn**. Với ID do database sinh, dùng cơ chế trả khóa được hỗ trợ đúng driver/database. Với ID do ứng dụng sinh, giá trị đã có sẵn.

## 8. Trùng khóa, retry và idempotency

`PRIMARY KEY`/`UNIQUE` phải luôn tồn tại ngay cả khi ứng dụng dùng UUID ngẫu nhiên. Một lỗi `duplicate key` có thể xuất phát từ:

- UUID hoặc mã do ứng dụng tạo bị trùng (hiếm nhưng phải xử lý).
- Hai request cùng dùng một mã nghiệp vụ trong cùng tenant.
- Client retry **cùng request** sau khi lần đầu có thể đã commit.
- Hai luồng cùng cấp `line_no` hoặc cùng ghi một khóa ghép.

**Không xử lý mọi xung đột bằng cách tạo UUID mới rồi chèn lại.** Nếu đó là retry của cùng một yêu cầu, sinh UUID mới có thể tạo bản ghi trùng nghiệp vụ. Nếu mã nghiệp vụ vi phạm `UNIQUE (tenant_id, invoice_number)`, đổi `invoice_id` cũng không giải quyết nguyên nhân.

Một luồng an toàn cho API tạo hóa đơn có thể là:

1. Nhận **idempotency key** của request và xác định tenant đã được xác thực.
2. Ánh xạ cặp `(tenant_id, idempotency_key)` tới một kết quả tạo duy nhất bằng bảng/ràng buộc unique hoặc cơ chế tương đương có transaction.
3. Tạo và lưu `InvoiceKey` ổn định cho yêu cầu; khi client gửi lại cùng key thì trả cùng kết quả, không tạo hóa đơn thứ hai.
4. Với xung đột, đọc lại bản ghi liên quan và **so sánh payload/quyền truy cập** theo hợp đồng API; không mặc định bất cứ hàng trùng khóa nào cũng là yêu cầu đã thành công.
5. Nếu giao dịch lỗi do deadlock/serialization failure, retry toàn bộ transaction theo chính sách giới hạn với backoff, tái sử dụng định danh của cùng yêu cầu.

Trong PostgreSQL, `SQLSTATE 23505` thường chỉ `unique_violation` và `SQLSTATE 23503` chỉ `foreign_key_violation`. Các mã này **riêng cho PostgreSQL**; JDBC bọc chúng trong `SQLException` (hoặc subtype). Không dựa vào chuỗi `ex.getMessage()` để suy luận ràng buộc nào đã lỗi nếu ứng dụng cần xử lý đáng tin cậy.

Ví dụ PostgreSQL có `ON CONFLICT ... DO NOTHING`, nhưng chỉ nên dùng sau khi đã quyết định rõ hợp đồng idempotency. Không coi việc bỏ qua một lệnh chèn xung đột là bằng chứng dữ liệu cũ có cùng nội dung.

## 9. Khóa ghép ảnh hưởng đến hiệu năng và thiết kế API

### Chỉ mục và thứ tự cột

Khóa chính `PRIMARY KEY (tenant_id, invoice_id)` tạo chỉ mục phù hợp với truy vấn lọc theo `tenant_id` rồi `invoice_id`. Truy vấn chỉ có `invoice_id = ?` có thể kém thuận lợi hơn vì bỏ qua cột đầu của chỉ mục ghép. Khi thiết kế, cần xem tần suất truy vấn và điều kiện lọc thực tế để chọn thứ tự cột và chỉ mục bổ sung.

UUID v4 được tạo ngẫu nhiên có ưu điểm sinh độc lập, nhưng phân bố giá trị trong chỉ mục có thể khác ID tuần tự. Tác động phụ thuộc DBMS, kiểu chỉ mục, kích thước bảng, cách ghi và thời gian chạy; hãy đo bằng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường thử nghiệm PostgreSQL với dữ liệu đại diện trước khi quyết định chiến lược ID.

### Chuỗi khóa trên mạng và trong log

Khóa ghép làm mỗi URL/DTO/sự kiện cần nhiều thành phần. Bảo đảm:

- Các API đọc, sửa, xóa nhận đủ `tenant_id` và `invoice_id` hoặc suy ra `tenant_id` **từ ngữ cảnh xác thực** một cách thống nhất.
- Khi log truy vấn thất bại, ghi định danh cần thiết để tìm bản ghi nhưng tránh in dữ liệu bí mật, toàn bộ SQL kèm giá trị nhạy cảm hoặc token truy cập.
- Mọi hàng con có khóa ngoại ghép giữ đúng tenant của cha; bảo vệ ủy quyền ở service/database vẫn cần thiết, vì FK chỉ đảm bảo toàn vẹn tham chiếu.
- Mapper và cache key sử dụng kiểu `InvoiceKey` hoặc cách mã hóa không nhập nhằng; không bỏ quên thành phần khóa trong `equals/hashCode`.

### Thay khóa chính sau khi đã có dữ liệu

Thay `invoice_id` hay `tenant_id` trên một hàng là thay **định danh**, có thể ảnh hưởng nhiều khóa ngoại, cache và tham chiếu ngoài. Tránh dùng những thuộc tính có thể đổi (email, tên, số hiển thị có thể tái cấp) làm thành phần khóa chính nếu không có lý do mạnh. Khi bắt buộc đổi, cần migration có quy tắc cập nhật quan hệ cha–con và kiểm tra đồng thời, thay vì sửa một hàng đơn lẻ.

## 10. Checklist và bài thực hành

Khi triển khai CRUD với khóa ghép và khóa do ứng dụng tạo, hãy tự xác nhận:

| Câu hỏi | Kiểm chứng bằng gì? |
|---|---|
| Phạm vi uniqueness của khóa đã đúng nghiệp vụ chưa? | `PRIMARY KEY`, `UNIQUE` và dữ liệu thử trùng khóa theo tenant |
| Toàn bộ CRUD có lọc đủ khóa chưa? | Xem SQL `WHERE` của `SELECT`/`UPDATE`/`DELETE` và thử dữ liệu hai tenant |
| Dòng con có thể trỏ nhầm sang tenant khác không? | Thử `INSERT` với `(tenant_id, invoice_id)` không tồn tại; FK phải chặn |
| ID có ổn định qua retry không? | Mô phỏng timeout sau commit rồi gửi lại cùng request |
| Tạo cha và con có nguyên tử không? | Cố ý cho một dòng vi phạm `CHECK`/`PRIMARY KEY`, xác nhận rollback cả nhóm |
| Cấp `line_no` có an toàn dưới tải đồng thời không? | Hai transaction thêm dòng cùng hóa đơn; kiểm tra khóa cha hoặc chiến lược cấp số |
| Khóa do app tạo có bị đọc sai bằng `getGeneratedKeys()` không? | Phân biệt cột app sinh với cột DB sinh trong từng statement |
| `UPDATE` 0 hàng được xử lý đúng chưa? | Thử version cũ và bản ghi không tồn tại |

### Bài thực hành có hướng dẫn

1. **Tạo hai tenant:** tạo các `UUID` khác nhau cho tenant A và B; sử dụng cố ý **cùng một `invoice_id`** ở hai tenant rồi chèn hai hóa đơn. Kiểm tra rằng `PRIMARY KEY (tenant_id, invoice_id)` cho phép cả hai, còn `UNIQUE (tenant_id, invoice_number)` vẫn áp dụng riêng cho mỗi tenant.
2. **Kiểm tra khóa ngoại ghép:** cố gắng chèn `invoice_lines` với tenant A nhưng `invoice_id` chỉ tồn tại ở B. Xác nhận database từ chối ngay cả khi giá trị `invoice_id` khớp một hóa đơn khác.
3. **Luyện CRUD:** với một `InvoiceKey`, chạy `INSERT`, `SELECT`, `UPDATE ... AND version = ?`, `DELETE`. Xem `executeUpdate()` để xử lý trường hợp cập nhật phiên bản cũ.
4. **Đo rollback:** cố gắng thêm hai dòng cùng `line_no` trong transaction tạo hóa đơn. Kiểm tra rằng không có hóa đơn cha và dòng nào từ transaction lỗi được commit.
5. **Phát hiện race condition:** mở hai transaction thêm dòng vào cùng hóa đơn dựa trên `MAX(line_no) + 1`; giải thích rủi ro trùng số, rồi thử lại với quy ước `SELECT ... FOR UPDATE` trên hàng cha.
6. **Mô phỏng retry:** tạo hóa đơn, giả lập mất phản hồi sau commit và gửi lại cùng yêu cầu. So sánh hành vi khi dùng lại `InvoiceKey` với khi tạo UUID mới; đề xuất ràng buộc idempotency phù hợp.

**Tiêu chí hoàn thành:** người học phân biệt được khóa ghép, khóa nghiệp vụ và khóa ứng dụng sinh; thiết kế được `PRIMARY KEY`/`FOREIGN KEY` ghép đúng phạm vi; thao tác CRUD qua JDBC với đầy đủ thành phần khóa, transaction và batching; không dùng sai `getGeneratedKeys()`; đồng thời giải thích được rủi ro cấp số đồng thời, trùng khóa, retry và idempotency.
