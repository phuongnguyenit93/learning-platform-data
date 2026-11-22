# Kiểm thử tương thích khi thay driver hoặc phiên bản cơ sở dữ liệu trong JDBC

Một ứng dụng Java có thể dùng **JDBC** ổn định trong nhiều năm với một JDBC driver và phiên bản cơ sở dữ liệu nhất định. Khi nâng driver để vá lỗi bảo mật, thay JDK, nâng phiên bản database hoặc chuyển môi trường triển khai, câu lệnh `SELECT 1` vẫn có thể thành công nhưng một chức năng khác lại thay đổi: `getGeneratedKeys()` trả khóa theo cách khác, `executeBatch()` báo số hàng khác, chuỗi Unicode bị chuyển đổi, transaction gặp lỗi isolation mới, hay timeout không còn được driver thực thi như trước.

Vì vậy, **kiểm thử tương thích** (*compatibility testing*) không chỉ trả lời “driver mới có kết nối được hay không?”, mà phải xác nhận rằng **hành vi ứng dụng phụ thuộc vào JDBC vẫn đáp ứng hợp đồng nghiệp vụ và vận hành sau thay đổi**. Đó là nội dung của bài **“Kiểm thử tương thích khi thay driver hoặc phiên bản cơ sở dữ liệu”**, thuộc chương **Kiểm thử JDBC** của module **JDBC**.

Bài tập trung vào các API tiêu biểu: `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, transaction, batching, generated keys, metadata, timeout và xử lý lỗi. Ta sẽ xây dựng một **bộ kiểm thử hợp đồng chạy lặp lại được** trên ma trận driver/database, tìm sự khác biệt có ý nghĩa, rồi đưa kết quả vào quy trình CI và triển khai nâng cấp an toàn.

**Nguyên tắc cốt lõi:** tính tương thích phải được xác nhận **ở hành vi mà ứng dụng sử dụng**, trên **đúng tổ hợp phiên bản định triển khai**. Việc mã Java biên dịch thành công, `DatabaseMetaData` báo tính năng được hỗ trợ hay một lần `getConnection()` thành công đều chưa đủ.

## 1. “Tương thích” trong JDBC có nhiều tầng

Khi đổi driver hoặc phiên bản DBMS, có ít nhất sáu tầng cần kiểm tra:

| Tầng tương thích | Câu hỏi cần trả lời | Ví dụ khác biệt có thể gặp |
| --- | --- | --- |
| **Binary/API** | Driver mới có hoạt động với phiên bản Java/JDBC đang dùng? | Yêu cầu JDK tối thiểu khác, phụ thuộc thư viện hoặc class không còn phù hợp. |
| **Kết nối và bảo mật** | URL, `DataSource`, xác thực, TLS, pooling còn hoạt động đúng? | Thuộc tính TLS đổi ý nghĩa, chứng chỉ không còn được chấp nhận, timeout khác trước. |
| **SQL và schema** | SQL trong repository, migration, kiểu dữ liệu và hàm DB còn hợp lệ? | Từ khóa mới, casting nghiêm hơn, thay đổi collation hoặc cú pháp riêng. |
| **Ánh xạ dữ liệu JDBC** | `PreparedStatement`/`ResultSet` đọc ghi đúng giá trị? | Khác biệt kiểu số, ngày giờ, `NULL`, Unicode, JSON/UUID/array. |
| **Transaction và cạnh tranh** | Commit, rollback, isolation, khóa và retry còn bảo đảm bất biến? | Truy vấn bị chặn khác trước, serialization failure nhiều hơn, xử lý auto-commit thay đổi. |
| **Hiệu năng và vận hành** | Pool, query plan, batch, timeout và tài nguyên vẫn đáp ứng SLO? | p99 tăng, câu SQL có kế hoạch khác, mở kết nối mới chậm, batch không còn tối ưu như cũ. |

Một nâng cấp có thể **tương thích chức năng** nhưng **không tương thích vận hành**: tất cả truy vấn trả đúng kết quả, nhưng p99 tăng đến mức API timeout. Ngược lại, hiệu năng có thể tốt hơn mà nghiệp vụ bị sai do một thuộc tính `BigDecimal` bị làm tròn khác.

### Hai kiểu thay đổi phải tách riêng

**Thay driver, giữ nguyên database:** tăng xác suất thay đổi ở cách JDBC URL được phân tích, protocol, ánh xạ kiểu Java, `SQLState`/exception, batching, generated keys, fetch size, timeout hoặc mặc định TLS. SQL server-side có thể chưa thay nhưng đường dẫn truy cập đã đổi.

**Thay phiên bản database, giữ nguyên driver:** tăng xác suất thay đổi ở SQL parser, optimizer, schema metadata, kiểu dữ liệu, collation, transaction, lock, quyền, trigger và giới hạn tài nguyên. Driver đang dùng có thể **không nằm trong tập phiên bản được nhà cung cấp hỗ trợ** cho server mới.

Nếu **thay cả driver và database trong một lần**, cần kiểm soát khả năng quy nguyên nhân: lỗi mới có thể đến từ driver, DB hoặc tương tác giữa chúng. Khi có thể, thử các bước nâng cấp riêng hoặc ít nhất lưu một ma trận có thể phân biệt.

## 2. Lập ma trận phiên bản và các giả định cần kiểm chứng

Một kế hoạch thử nghiệm phải nêu rõ **phiên bản gốc** và **phiên bản ứng viên**. Ví dụ minh họa, không gắn với phiên bản sản phẩm cụ thể:

| Môi trường | JDK | JDBC driver | Database server | Mục đích |
| --- | --- | --- | --- | --- |
| **Baseline** | JDK A | Driver D1 | DB S1 | Lưu hành vi đã được chấp nhận hiện tại. |
| **Driver candidate** | JDK A | Driver D2 | DB S1 | Phân biệt thay đổi do driver. |
| **Database candidate** | JDK A | Driver D1 nếu hỗ trợ | DB S2 | Phân biệt thay đổi do server; không chạy tổ hợp không được hỗ trợ. |
| **Release candidate** | JDK mục tiêu | Driver D2 | DB S2 | Xác minh tổ hợp sẽ triển khai. |

Không phải mọi tổ hợp đều hợp lệ. Trước khi chạy, hãy đối chiếu **ma trận hỗ trợ chính thức** của nhà cung cấp driver/database/JDK và chỉ triển khai các tổ hợp nằm trong chính sách hỗ trợ. Một ô không hỗ trợ phải được ghi **NOT SUPPORTED**, không tự xem là `FAIL` của chương trình hay cố dùng trong production.

Thông tin cần cố định hoặc ghi rõ:

- Phiên bản JDK, driver artifact, database product/edition, phiên bản server và bản vá.
- JDBC URL, driver properties, kiểu xác thực/TLS, cấu hình trust store và secret rotation.
- `DataSource`/pool implementation, phiên bản, `maximumPoolSize`, timeout, validation, auto-commit, isolation.
- Schema và migration version, extensions/plugins, collation, charset, time zone, database/session settings.
- OS/container image, architecture, vùng mạng, proxy/endpoint, DNS và giới hạn số kết nối.
- Kích thước dữ liệu, chỉ mục, workload, số luồng đồng thời, phương pháp dọn fixture.
- Các tính năng riêng database đang dùng: stored procedure, JSON, arrays, generated keys, server cursor...

### Thu thập danh tính môi trường từ API JDBC

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public static void printEnvironment(Connection connection)
        throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("DB product: "
            + meta.getDatabaseProductName());
    System.out.println("DB version: "
            + meta.getDatabaseProductVersion());
    System.out.println("Driver name: "
            + meta.getDriverName());
    System.out.println("Driver version: "
            + meta.getDriverVersion());
    System.out.println("JDBC API level: "
            + meta.getJDBCMajorVersion() + "."
            + meta.getJDBCMinorVersion());
    System.out.println("Current autoCommit: "
            + connection.getAutoCommit());
    System.out.println("Current isolation: "
            + connection.getTransactionIsolation());
}
```

Thông tin này hữu ích để gắn vào báo cáo, **nhưng metadata là thông tin driver/server công bố**, không tự chứng minh hành vi thực thi. Không ghi username, password, JDBC URL thô hoặc `Properties` nhạy cảm ra log CI.

## 3. Thiết kế bộ kiểm thử theo hợp đồng, không theo chi tiết driver

Mục tiêu chính là **cùng một bộ kịch bản** chạy trên baseline và ứng viên, với **cùng các bất biến nghiệp vụ**, rồi đối chiếu kết quả.

```text
             Compatibility contract
           (kỳ vọng của ứng dụng Java)
                        │
              ┌─────────┴───────────┐
              ▼                     ▼
       Baseline profile       Candidate profile
      Driver D1 + DB S1      Driver D2 + DB S2
              │                     │
              ▼                     ▼
      Chạy cùng các test    Chạy cùng các test
              │                     │
              └─────────┬───────────┘
                        ▼
          So sánh đúng/sai + chênh lệch
          kết quả, lỗi, timing và resource
                        │
                        ▼
              Gate phát hành nâng cấp
```

Một *contract test* nên quy định:

1. **Điều kiện ban đầu:** schema, dữ liệu fixture, quyền, isolation và trạng thái connection.
2. **Thao tác:** SQL hoặc phương thức DAO được thực thi; tham số cụ thể.
3. **Kết quả chức năng:** số hàng, giá trị, thứ tự khi có `ORDER BY`, xử lý `NULL`, lỗi mong đợi.
4. **Bất biến dữ liệu:** không ghi trùng, không mất cập nhật, rollback đúng, số dư/tồn kho hợp lệ.
5. **Giới hạn vận hành:** timeout, memory, latency, số kết nối, lock wait, tỷ lệ lỗi được chấp nhận.
6. **Cách dọn dữ liệu:** rollback hoặc cleanup có kiểm soát, không dựa vào trạng thái test trước.

Nên phân biệt ba loại kết quả:

| Kết quả | Khi nào dùng | Ý nghĩa |
| --- | --- | --- |
| **PASS** | Mọi bất biến bắt buộc được thỏa mãn | Tương thích theo phạm vi contract đã kiểm tra |
| **FAIL** | Sai giá trị, hỏng transaction, mất quyền, lỗi SQL không dự kiến | Chặn nâng cấp cho đến khi được giải thích và sửa |
| **NOT APPLICABLE / UNSUPPORTED** | Tính năng không được dùng hoặc không thuộc ma trận hỗ trợ | Không coi như PASS; ghi rõ lý do và tác động |

Không biến một sự khác biệt thành PASS chỉ vì “driver mới chạy theo cách khác”. Nếu đó là thay đổi được mong muốn, cần **cập nhật hợp đồng một cách có chủ đích**, có review và bằng chứng. Ngược lại, không nên khóa cứng những chi tiết **không phải hợp đồng** như nội dung chính xác của một thông điệp lỗi bằng ngôn ngữ riêng driver.

## 4. Chuẩn bị schema và dữ liệu thử không phụ thuộc test trước

Một lỗi phổ biến là chạy các test trên database vốn đã có dữ liệu từ lần chạy trước. Khi đó lỗi unique key, trạng thái transaction và kết quả đếm rất khó diễn giải.

Cho bộ test **portable smoke** dưới đây, giả sử đã triển khai bảng bằng migration tương ứng với từng hệ quản trị:

```sql
CREATE TABLE jdbc_compat_probe (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    note VARCHAR(200),
    version BIGINT NOT NULL
);
```

Mục đích của bảng:

- `id`: chuỗi UUID do test tạo, tránh tranh chấp khi chạy song song.
- `display_name`: kiểm tra Unicode và ký tự đặc biệt.
- `amount`: kiểm tra số chính xác `BigDecimal`.
- `note`: kiểm tra giá trị SQL `NULL`.
- `version`: kiểm tra điều kiện cập nhật và xung đột phiên bản.

DDL trên là **mẫu SQL gần với SQL phổ biến**, không phải bảo đảm chạy nguyên văn ở mọi DB. Nếu một hệ quản trị dùng kiểu dữ liệu hoặc cú pháp khác, hãy triển khai schema tương đương bằng migration riêng rồi chạy **chung mã kiểm thử hành vi**. Không đổi bất biến chỉ để một nền tảng vượt qua test.

### Quản lý fixture

- Chạy bộ test trên **database dành riêng cho kiểm thử**, không dùng database production.
- Khởi tạo schema bằng chính công cụ migration của ứng dụng. Kiểm tra **migration từ schema cũ**, không chỉ tạo mới từ đầu.
- Mỗi test tạo ID riêng và không dựa vào thứ tự thực thi test. Với test transaction có thể rollback hoàn toàn, ưu tiên rollback; test DDL hoặc commit/failover cần cơ chế cleanup riêng.
- Tránh sử dụng bảng chung mà các test đồng thời sửa cùng một dòng không có chủ đích.
- Không đưa mật khẩu DB vào test source, console hay báo cáo artifact.
- Nếu dùng container DB, xác định **đúng product/version** và môi trường TLS/time zone/collation tương đương nơi triển khai; container chỉ là phương tiện tạo môi trường có thể lặp lại.

**Không lấy kết quả từ một database giả lập ở “compatibility mode” làm bằng chứng duy nhất** cho PostgreSQL, Oracle, MySQL hoặc SQL Server. Mô phỏng dialect không thay thế driver, server, khóa, transaction, lỗi và optimizer của sản phẩm thật.

## 5. Kiểm thử đầu tiên: kết nối và cấu hình hạ tầng

Trước khi chạy SQL chức năng, kiểm tra đường vào:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public static void checkConnection(DataSource dataSource)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        if (connection.isClosed()) {
            throw new AssertionError("Received a closed connection");
        }

        printEnvironment(connection);

        System.out.println("AutoCommit="
                + connection.getAutoCommit());
        System.out.println("ReadOnly="
                + connection.isReadOnly());
        System.out.println("Isolation="
                + connection.getTransactionIsolation());
    }
}
```

Các ca kết nối nên có:

| Kịch bản | Kiểm chứng |
| --- | --- |
| Tạo kết nối từ `DataSource` | Kết nối và đóng được; không leak hoặc giữ active connection mãi |
| Kết nối qua pool | Checkout/checkin đúng; cấu hình max/idle/validation không gây lỗi với driver mới |
| TLS và xác minh server | Chứng chỉ đúng → thành công; CA/hostname không hợp lệ → thất bại |
| Xác thực và quyền | Credential đúng, role chỉ đọc/ghi đúng quyền; không tự fallback phương thức auth yếu hơn |
| URL và driver properties | Driver mới diễn giải điểm đến, database, schema, TLS và timeout như dự kiến |
| Restart/failover | Connection hỏng được phát hiện, pool thay thế; yêu cầu đang chạy xử lý kết quả chưa rõ đúng cách |
| Session state | `autoCommit`, isolation, read-only, schema/role được phục hồi trước khi tái sử dụng connection |

**Đừng suy rằng `connection.isValid(5)` thành công chứng minh mọi SQL chạy đúng.** Nó chỉ là tín hiệu kiểm tra connection theo API và cách driver triển khai. Một kết nối sống vẫn có thể thiếu quyền, ánh xạ dữ liệu sai hoặc bị timeout ở thao tác dài.

Một lưu ý bảo mật: những test cố tình dùng chứng chỉ sai hoặc cắt mạng chỉ nên chạy trên môi trường **được phép điều khiển**, không tạo sự cố cho database dùng chung.

## 6. Kiểm thử CRUD và kiểu dữ liệu bằng một probe JDBC có thể lặp lại

Một smoke test hữu ích là dùng **cùng mã Java** cho baseline/candidate. Nó phải kiểm tra **giá trị thật** và transaction rollback, không chỉ thử lệnh `INSERT` có ném exception hay không.

Ví dụ dưới đây giả định bảng `jdbc_compat_probe` đã tồn tại theo phần 4. Lớp nhận `DataSource` do test runner cấu hình cho từng environment. Test dùng ID UUID, ghi rồi đọc Unicode, `DECIMAL`, SQL `NULL`, cập nhật có version và cuối cùng rollback.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.UUID;

public final class JdbcCompatibilityProbe {
    private JdbcCompatibilityProbe() {
    }

    public static void verify(DataSource dataSource)
            throws SQLException {

        String id = UUID.randomUUID().toString();
        String expectedName = "Cà phê Đà Lạt";
        BigDecimal expectedAmount = new BigDecimal("12345.67");

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            if (!originalAutoCommit) {
                throw new SQLException(
                        "Probe requires a connection outside a transaction");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable primary = null;

            try {
                String insert =
                        "INSERT INTO jdbc_compat_probe " +
                        "(id, display_name, amount, note, version) " +
                        "VALUES (?, ?, ?, ?, ?)";

                try (PreparedStatement statement =
                             connection.prepareStatement(insert)) {
                    statement.setString(1, id);
                    statement.setString(2, expectedName);
                    statement.setBigDecimal(3, expectedAmount);
                    statement.setNull(4, Types.VARCHAR);
                    statement.setLong(5, 1L);

                    require(
                            statement.executeUpdate() == 1,
                            "INSERT should affect one row");
                }

                String select =
                        "SELECT display_name, amount, note, version " +
                        "FROM jdbc_compat_probe WHERE id = ?";

                try (PreparedStatement statement =
                             connection.prepareStatement(select)) {
                    statement.setString(1, id);

                    try (ResultSet rs = statement.executeQuery()) {
                        require(rs.next(), "Inserted row missing");
                        require(
                                expectedName.equals(
                                        rs.getString("display_name")),
                                "Unicode text changed");

                        BigDecimal actualAmount =
                                rs.getBigDecimal("amount");
                        require(
                                actualAmount != null
                                && actualAmount.compareTo(
                                        expectedAmount) == 0,
                                "Decimal value changed");

                        require(
                                rs.getString("note") == null,
                                "SQL NULL changed");

                        require(
                                rs.getLong("version") == 1L,
                                "Version not preserved");
                        require(!rs.next(), "More than one row found");
                    }
                }

                String update =
                        "UPDATE jdbc_compat_probe " +
                        "SET amount = ?, version = version + 1 " +
                        "WHERE id = ? AND version = ?";

                try (PreparedStatement statement =
                             connection.prepareStatement(update)) {
                    statement.setBigDecimal(
                            1, new BigDecimal("23456.78"));
                    statement.setString(2, id);
                    statement.setLong(3, 1L);

                    require(
                            statement.executeUpdate() == 1,
                            "Versioned UPDATE did not match");

                    // Lần cập nhật thứ hai dùng version cũ.
                    require(
                            statement.executeUpdate() == 0,
                            "Stale version unexpectedly updated");
                }

                connection.rollback();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primary = failure;
                if (!transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;

            } finally {
                // Không bật autoCommit=true nếu rollback thất bại:
                // đổi chế độ khi transaction chưa kết thúc có thể commit.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException resetFailure) {
                        if (primary != null) {
                            primary.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
        }

        // Xác minh rollback bằng một kết nối riêng.
        try (Connection verifier = dataSource.getConnection();
             PreparedStatement statement = verifier.prepareStatement(
                     "SELECT id FROM jdbc_compat_probe WHERE id = ?")) {
            statement.setString(1, id);
            try (ResultSet rs = statement.executeQuery()) {
                require(!rs.next(),
                        "Rollback left a visible row in the database");
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

**Điểm thiết kế của probe:**

- `setString()`, `setBigDecimal()`, `setNull()` và `getBigDecimal()` giúp phát hiện thay đổi conversion giữa các driver.
- So sánh `BigDecimal` bằng `compareTo() == 0` khi ý nghĩa nghiệp vụ là **giá trị số**; `equals()` còn so cả `scale`, có thể không phải hợp đồng mong muốn. Nếu scale là yêu cầu cụ thể, hãy kiểm tra riêng `scale()`.
- `executeUpdate() == 1` là hợp đồng của `INSERT` một dòng và `UPDATE` theo khóa chính có điều kiện. Nó đáng kiểm tra sau nâng cấp.
- Truy vấn thứ hai dùng cùng `PreparedStatement` nhưng vẫn giữ `expectedVersion=1`. Kết quả `0` xác nhận cập nhật theo optimistic locking không lặp lại với version cũ.
- `rollback()` phải hoàn tác thay đổi đã thực hiện. Truy vấn từ một connection **khác** sau rollback xác nhận không còn hàng mang ID test.
- Ví dụ yêu cầu connection ban đầu ở `autoCommit=true` để sở hữu transaction của riêng probe. Trong hệ thống có transaction manager, cần một fixture riêng và không tự quản lý transaction chồng lên tầng quản lý khác.
- Nếu rollback thất bại, test **không** phục hồi auto-commit theo cách có thể vô tình commit dữ liệu; kết nối nghi vấn phải bị loại khỏi pool bằng cơ chế dành riêng cho implementation.
- `assertion` hoặc `AssertionError` phải làm test **FAIL**, không được bắt rồi bỏ qua. Mọi lỗi JDBC phải được giữ đủ ngữ cảnh để điều tra.

Nếu database mới thay đổi kiểu `VARCHAR`/Unicode, bạn có thể phải điều chỉnh **schema test** theo dialect để bảo toàn yêu cầu lưu chữ Việt; **không chỉnh `expectedName` để khớp dữ liệu đã bị sai**. Điều cần được kiểm chứng là hợp đồng giá trị end-to-end.

## 7. Những kiểu dữ liệu phải có test riêng ngoài smoke test

Bộ probe ở phần 6 chỉ là khởi đầu. Các kiểu có rủi ro tương thích cao gồm:

| Nhóm | Giá trị/bài thử đại diện | Khả năng thay đổi |
| --- | --- | --- |
| Chuỗi Unicode | `"Tiếng Việt: Đà Nẵng, ă â ê ô ơ ư"`, emoji nếu schema hỗ trợ | Encoding, collation, normalization, truncation |
| `CHAR`/`VARCHAR`/national character types | Chuỗi rỗng, có dấu cách cuối, ký tự đa byte, `NULL` | Padding, khoảng trắng, độ dài tính theo byte/ký tự |
| `DECIMAL`/`NUMERIC` | `0.00`, số âm, giá trị gần precision/scale tối đa | Làm tròn, tràn, `BigDecimal` scale/conversion |
| Số nguyên | Cực trị của `INTEGER`/`BIGINT`, `NULL` | Range, overflow, `getInt()`/`getLong()`, `wasNull()` |
| Ngày thuần | `LocalDate` qua JDBC 4.2 khi driver hỗ trợ | SQL `DATE` ↔ Java `LocalDate` |
| Thời điểm/ngày giờ | Ngày gần DST, múi giờ khác UTC, độ chính xác dưới giây | Session timezone, precision, `TIMESTAMP` vs `TIMESTAMP WITH TIME ZONE` |
| Binary/LOB | 0 byte, file lớn, dữ liệu chứa byte `0x00` | Streaming, memory, lifecycle `Blob`/`Clob` |
| Boolean và enum | `true/false`, giá trị enum mới, `NULL` | Database type, mapping `getBoolean()`/`getObject()` |
| JSON/UUID/ARRAY/STRUCT | Giá trị lồng nhau và `NULL` | Hỗ trợ API JDBC chuẩn hoặc object driver-specific |
| Alias/metadata cột | `SELECT id AS customer_id ...` | `getColumnLabel()` khác `getColumnName()` |

**Ngày giờ cần hợp đồng rõ:** SQL `TIMESTAMP WITHOUT TIME ZONE` không có cùng ngữ nghĩa với một *instant* tuyệt đối; không được áp một assertion so sánh cùng `OffsetDateTime` cho mọi kiểu và driver. Trước test hãy xác định ứng dụng muốn giữ **ngày/giờ địa phương**, **instant UTC** hay **offset** rồi kiểm tra đúng hợp đồng. Nếu ứng dụng có sử dụng `setObject(..., LocalDate)` / `getObject(..., LocalDate.class)`, hãy kiểm tra trên driver thật; sự hỗ trợ có thể phụ thuộc JDBC/driver/kiểu cột.

**SQL `NULL` với getter nguyên thủy:** `getInt()`/`getLong()` trả `0` cho SQL `NULL`; cần gọi `wasNull()` **ngay sau getter tương ứng** để phân biệt. Test phải bắt được lỗi mapper quên kiểm tra này.

**Thứ tự không tự được bảo đảm:** nếu so sánh kết quả nhiều dòng, phải dùng `ORDER BY` hoặc so sánh như tập hợp khi nghiệp vụ không yêu cầu thứ tự. Đổi driver/database có thể làm thay đổi kế hoạch truy vấn và thứ tự tự nhiên, nhưng không nên coi đó là lỗi ứng dụng nếu SQL không có hợp đồng về thứ tự.

## 8. `getGeneratedKeys()` là một điểm kiểm thử bắt buộc khi dùng khóa tự sinh

Nhiều hệ thống dùng `Statement.RETURN_GENERATED_KEYS`:

```java
String insert = "INSERT INTO customers (name) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(
        insert, java.sql.Statement.RETURN_GENERATED_KEYS)) {
    statement.setString(1, "Ngọc");

    int inserted = statement.executeUpdate();
    if (inserted != 1) {
        throw new AssertionError("Expected one inserted customer");
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new AssertionError("Generated key is missing");
        }

        Object key = keys.getObject(1);
        if (key == null) {
            throw new AssertionError("Generated key is NULL");
        }

        // Với một INSERT một dòng: kiểm tra tính hợp lệ của
        // khóa và bản ghi tương ứng trong transaction thử nghiệm.
    }
}
```

Ví dụ giả định bảng `customers` có khóa do server tạo, cột `name` và driver hỗ trợ yêu cầu trả khóa. Test này nên nằm trong **một transaction thử nghiệm có cleanup rõ ràng**, không trực tiếp ghi vào bảng nghiệp vụ ở production.

Điều cần kiểm tra sau nâng cấp:

1. `DatabaseMetaData.supportsGetGeneratedKeys()` báo gì? Đây là tín hiệu hỗ trợ, **không thay thế thực thi SQL**.
2. Driver có trả khóa sau **một lệnh `INSERT` đơn** đúng kiểu khóa đã định không?
3. Với **nhiều hàng hoặc `executeBatch()`**, có trả đủ khóa không, thứ tự trả có khớp thứ tự đầu vào theo **cam kết driver** không?
4. Khi `INSERT` đã thành công nhưng `getGeneratedKeys()` thất bại, tầng DAO có xử lý an toàn hay vô tình chạy lại `INSERT` gây trùng?
5. Nếu schema có trigger, sequence, cột identity, UUID hoặc cú pháp `RETURNING` riêng, test có kiểm tra đúng ý nghĩa khóa sinh không?

**Không viết assertion “khóa trong batch luôn theo thứ tự item”** khi driver không cam kết điều đó. Nếu ứng dụng đang dựa vào giả định ấy, cần sửa thiết kế hoặc thêm kiểm chứng thực tế được phiên bản driver hỗ trợ trước nâng cấp.

## 9. Batching: tính tương thích không chỉ là không ném lỗi

`PreparedStatement.addBatch()` và `executeBatch()` có thể được driver mới tối ưu hoặc thay đổi cách gửi lệnh. Kiểm thử nên bao gồm:

```java
import java.sql.BatchUpdateException;
import java.sql.PreparedStatement;
import java.sql.Statement;

try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO jdbc_compat_probe " +
        "(id, display_name, amount, note, version) " +
        "VALUES (?, ?, ?, ?, ?)")) {

    for (String id : twoUniqueIds) {
        statement.setString(1, id);
        statement.setString(2, "Batch row");
        statement.setBigDecimal(
                3, new java.math.BigDecimal("10.00"));
        statement.setNull(4, java.sql.Types.VARCHAR);
        statement.setLong(5, 1L);
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();

    if (counts.length != twoUniqueIds.size()) {
        throw new AssertionError("Unexpected batch count length");
    }
    for (int count : counts) {
        if (count == Statement.EXECUTE_FAILED) {
            throw new AssertionError("Batch command failed");
        }
        if (count != Statement.SUCCESS_NO_INFO && count < 0) {
            throw new AssertionError(
                    "Unknown negative update count: " + count);
        }
    }
} catch (BatchUpdateException failure) {
    // Báo cả getUpdateCounts(), getNextException(), SQLState.
    // Bên sở hữu transaction phải rollback nếu cần.
    throw failure;
}
```

Đoạn mã nằm trong test có `Connection connection`, danh sách `twoUniqueIds` và transaction được tạo từ bên ngoài; không phải chương trình độc lập. `SUCCESS_NO_INFO` nghĩa là **lệnh thành công nhưng không rõ số hàng**, không phải lỗi. Nếu nghiệp vụ yêu cầu **chính xác một hàng** cho từng thao tác, chỉ biết `SUCCESS_NO_INFO` là chưa đủ.

Các tình huống cần có trong suite:

- Batch thành công với 1, 2, hàng chục hoặc hàng trăm phần tử.
- Batch ở kích thước sử dụng thực tế, chứa Unicode, `NULL` và dữ liệu gần giới hạn kiểu.
- Một phần tử vi phạm unique/foreign key để kiểm tra `BatchUpdateException` và `getUpdateCounts()`.
- Driver **dừng tại lỗi** hoặc **tiếp tục phần tử sau lỗi**, theo hành vi cụ thể; không giả định toàn batch chưa chạy.
- Batch trong transaction `autoCommit=false` và kiểm tra rollback thật sự xóa các ghi chưa commit.
- `getGeneratedKeys()` sau batch, nếu nghiệp vụ có sử dụng.
- Hiệu năng dưới tải có và không có tính năng driver rewrite batch, nếu driver có cung cấp.

**Thay đổi update count có thể là breaking change với ứng dụng**. Nếu code đang coi `-2` là lỗi, một driver mới bắt đầu trả `SUCCESS_NO_INFO` có thể làm các batch hợp lệ thất bại. Nếu code đòi số hàng `1`, thì không thể chấp nhận `-2` một cách mù quáng: phải điều chỉnh hợp đồng hoặc cách xác minh.

## 10. Kiểm thử transaction, isolation và khóa bằng nhiều kết nối

Một smoke test rollback đơn lẻ là cần thiết nhưng chưa đủ. Khi nâng database, quan trọng nhất là **bất biến dưới tải đồng thời**, vì cùng tên isolation không nhất thiết cho cùng hành vi chi tiết ở mọi sản phẩm/phiên bản.

| Chủ đề | Bài kiểm thử | Kỳ vọng cần xác định |
| --- | --- | --- |
| Auto-commit | `getAutoCommit()`, `setAutoCommit(false)`, `commit()`, `rollback()` | Cùng transaction khi cần và khôi phục trạng thái đúng |
| Read-only | `Connection.setReadOnly(true)`, DB role/permission | Phân biệt hint JDBC với phân quyền DB thật |
| Isolation | `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE` khi được hỗ trợ | Non-repeatable read, phantom, blocking, serialization failure theo hợp đồng |
| Optimistic locking | `UPDATE ... WHERE id=? AND version=?` | Lần ghi version cũ bị từ chối (`0` hoặc lỗi phù hợp) |
| Pessimistic lock | `SELECT ... FOR UPDATE` nếu dialect hỗ trợ | Khóa hàng và thời gian chờ đúng theo engine/driver |
| Deadlock/serialization | Hai transaction cập nhật theo thứ tự đối nghịch | Lỗi được phân loại đúng; retry **toàn transaction** |
| Pool cleanup | Trả connection sau transaction | Không truyền auto-commit/isolation/schema/role của request trước sang request sau |

### Kịch bản hai kết nối kiểm tra optimistic locking

Dùng **hai `Connection` độc lập** A và B, mỗi bên sở hữu một transaction:

```text
Ban đầu: id=101, version=1

A: SELECT id, version FROM products WHERE id=101
B: SELECT id, version FROM products WHERE id=101
   → cả hai đọc version=1

A: UPDATE products
   SET price=?, version=version+1
   WHERE id=101 AND version=1
   → thành công, COMMIT (version=2)

B: UPDATE products
   SET price=?, version=version+1
   WHERE id=101 AND version=1
   → không khớp (0 hàng) hoặc transaction báo xung đột
     tùy isolation/engine; KHÔNG được âm thầm ghi đè A
```

Test này nên xác nhận **bất biến không mất cập nhật**, chứ không khóa cứng mọi driver phải trả đúng `0`. Ở isolation nhất định, B có thể nhận serialization failure thay vì số hàng cập nhật `0`; ứng dụng phải xử lý cả kết quả `executeUpdate()` và `SQLException`.

Các tình huống cần đo thêm: đọc trong cùng transaction sau khi B commit, phantom khi thêm hàng mới, cập nhật hai hàng liên quan dẫn tới write skew, lock wait, timeout và cơ chế retry. Đừng coi việc `supportsTransactionIsolationLevel(...)` trả `true` là chứng nhận toàn bộ các bất biến đó.

**Tránh test đồng thời không xác định lịch chạy:** dùng `CountDownLatch`/`CyclicBarrier` hoặc một bộ điều phối có timeout để kiểm soát các mốc đọc/ghi. Mỗi thread phải sở hữu connection riêng và dọn tài nguyên; không chia sẻ một `Connection` giữa các thread như mặc định là thread-safe. Test deadlock không nên treo CI vô hạn: đặt giới hạn thời gian, phát hiện lỗi và cleanup.

## 11. Kiểm thử `ResultSet`, metadata và API nâng cao

Một driver mới có thể vẫn chạy `SELECT` đơn giản nhưng thay đổi ở giao diện kết quả. Hãy ưu tiên những khả năng ứng dụng **thực sự sử dụng**:

| Tính năng | API JDBC | Cần xác minh |
| --- | --- | --- |
| Nhãn và kiểu cột | `ResultSetMetaData.getColumnLabel()`, `getColumnType()` | Alias, kiểu và lớp Java nhận được có đúng với mapper không |
| Cursor | `ResultSet.getType()`, `getConcurrency()` | Driver có thực sự cung cấp scrollable/updatable result set được yêu cầu không |
| Fetch size | `Statement.setFetchSize()` | Có streaming/chia đợt như tài liệu không, memory có tăng khi nâng driver không |
| Cập nhật cursor | `ResultSet.updateRow()`, `insertRow()` | Chỉ kiểm tra nếu hệ thống dùng; điều kiện xung đột và trigger |
| Metadata schema | `DatabaseMetaData.getTables()`, `getColumns()` | Schema/catalog/case/pattern/permission được diễn giải đúng |
| Batch/keys | `supportsBatchUpdates()`, `supportsGetGeneratedKeys()` | Hành vi thực tế chứ không chỉ cờ hỗ trợ |
| Stored procedure | `CallableStatement`, `registerOutParameter()` | `IN`/`OUT`, function vs procedure, result sets và cursor |
| Kiểu SQL nâng cao | `SQLXML`, `Array`, `Struct`, `Blob`/`Clob` | Mapping, SQL `NULL`, lifetime, `free()` và driver-specific classes |

Ví dụ kiểm tra type/concurrency thực tế sau khi yêu cầu cursor:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id, name FROM customers",
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
     ResultSet rs = statement.executeQuery()) {

    int actualType = rs.getType();
    int actualConcurrency = rs.getConcurrency();

    if (actualType != ResultSet.TYPE_SCROLL_INSENSITIVE) {
        throw new AssertionError(
                "Scrollable ResultSet was not provided");
    }
    if (actualConcurrency != ResultSet.CONCUR_READ_ONLY) {
        throw new AssertionError(
                "Unexpected ResultSet concurrency");
    }
}
```

Test này chỉ nên là **gate bắt buộc** nếu sản phẩm thật sự cần cursor loại đó. Một driver có thể hạ cấp yêu cầu hoặc ném ngoại lệ; test sẽ phát hiện thay đổi, nhưng không có lý do buộc mọi sản phẩm phải hỗ trợ scrollability nếu ứng dụng vốn chỉ dùng `TYPE_FORWARD_ONLY`.

Tương tự, `ParameterMetaData` có thể thiếu hoặc không chính xác trong những cú pháp phức tạp; nếu ứng dụng không phụ thuộc vào nó, đừng khóa release chỉ vì một chỉ số metadata không cần thiết khác baseline. Nếu ứng dụng dùng để sinh mapper hoặc validate, cần các test riêng trên SQL thật.

## 12. Lỗi và cảnh báo: kiểm tra theo phân loại, không so thông điệp

Khi database thay đổi, **SQLState**, mã lỗi nhà cung cấp và lớp `SQLException` có thể thay đổi. Những tầng ứng dụng đang chuyển `SQLException` thành lỗi truy cập dữ liệu cần được kiểm thử.

Ví dụ danh sách kịch bản:

| Trường hợp gây lỗi | Hợp đồng ứng dụng cần giữ |
| --- | --- |
| Vi phạm unique key | Được phân loại là vi phạm constraint; không tự kết luận trùng email nếu chưa biết ràng buộc |
| Foreign key/check constraint | Không bị nhầm thành lỗi timeout hoặc mất kết nối |
| Lỗi SQL hoặc quyền | Báo lỗi định nghĩa truy vấn/quyền, không retry mãi |
| Deadlock/serialization | Có thể retry **toàn bộ transaction** khi an toàn |
| Timeout thực thi | Không trả thành công giả; xử lý kết quả server có thể chưa rõ |
| Mất kết nối tại commit | Không khẳng định giao dịch chưa commit; có đối soát/idempotency |
| `BatchUpdateException` | Không làm mất `getUpdateCounts()` và `getNextException()` |
| `SQLWarning` | Cảnh báo được xử lý theo hợp đồng, không tự coi mọi warning là lỗi |

Một hàm gom chẩn đoán không làm lộ dữ liệu:

```java
import java.sql.SQLException;

public static void logSqlCategories(SQLException root) {
    int index = 0;
    for (SQLException current = root;
         current != null && index < 20;
         current = current.getNextException(), index++) {

        System.out.println(
                "errorIndex=" + index
                + " class=" + current.getClass().getSimpleName()
                + " state=" + current.getSQLState()
                + " vendorCode=" + current.getErrorCode());
    }
}
```

Trong ứng dụng thật, dùng logger nội bộ có cấu trúc. Không log password, URL chứa secret, tham số nhạy cảm hoặc nguyên thông điệp từ server ra phản hồi công khai.

**Assertion tốt:** lỗi vi phạm unique được mapper của ứng dụng chuyển thành `CONSTRAINT_VIOLATION` và dữ liệu không bị ghi sai.

**Assertion dễ vỡ:** `SQLException.getMessage()` phải bằng chính xác một chuỗi tiếng Anh hoặc mã vendor phải giống giữa hai hệ quản trị. Chỉ kiểm tra mã vendor cụ thể khi logic ứng dụng **thực sự phụ thuộc** và đã giới hạn đúng driver/database.

## 13. Timeout, cancellation và lỗi mạng cần bài thử có kiểm soát

Driver upgrade có thể làm khác cách thực thi `Statement.setQueryTimeout()`, `Statement.cancel()` và `Connection.setNetworkTimeout()`, ngay cả khi SQL đúng.

| Trường hợp | Cần xác nhận |
| --- | --- |
| `DataSource.getConnection()` bị chờ pool | Borrow timeout thuộc pool, không bị nhầm với SQL query timeout |
| Connect/login/TLS timeout | Driver phát lỗi có kiểm soát và không làm leak thread/connection |
| `Statement.setQueryTimeout(seconds)` | Câu SQL chậm bị giới hạn trong khoảng thời gian phù hợp với cách driver hỗ trợ |
| `Statement.cancel()` | Yêu cầu hủy không bị mất; không kết luận cancel đồng nghĩa rollback |
| `Connection.setNetworkTimeout(...)` | Kết nối bị xử lý/loại bỏ đúng khi network không phản hồi |
| `ResultSet` fetch lâu | Không chỉ đo `executeQuery()`; cần đo cả vòng đọc `rs.next()` |
| Lỗi sau `executeUpdate()` / `commit()` | Không retry lệnh ghi khi kết quả chưa xác định |
| Failover/connection reset | Pool phát hiện connection hỏng và tạo kết nối hợp lệ, session state được reset |

**Giới hạn quan trọng:** JDBC timeout và cancel thường mang tính **best effort** theo khả năng driver/database. `setQueryTimeout(1)` không phải bảo đảm mọi tác vụ kết thúc đúng 1000 ms, và `cancel()` trả về không chứng minh transaction đã rollback. Khi test, nên đánh giá ngưỡng có dư địa và hậu điều kiện dữ liệu, không assertion thời gian quá sát gây flaky.

Đừng dùng thao tác ngắt mạng hoặc cố tạo deadlock trên database dùng chung. Dùng môi trường riêng, giới hạn thời gian test và có cơ chế dọn dẹp ngay cả khi bước thử lỗi.

## 14. CI: chạy cùng contract suite trên baseline và ứng viên

Một pipeline có thể bố trí:

```text
Build ứng dụng / kiểm tra bytecode với JDK mục tiêu
                    │
                    ▼
        Tạo database thử nghiệm theo version
          ├─ baseline DB / driver
          └─ candidate DB / driver
                    │
                    ▼
         Áp migration từ schema tương ứng
                    │
                    ▼
        Chạy contract test cùng fixture
          ├─ CRUD / Unicode / decimal / NULL
          ├─ generated keys / batching
          ├─ transaction / isolation / concurrency
          ├─ metadata / advanced APIs đang dùng
          └─ lỗi / TLS / timeout / cleanup
                    │
                    ▼
         So sánh + phân loại sai khác
          ├─ Bắt buộc giống nhau: giá trị, bất biến
          ├─ Có thể khác: nội dung lỗi, plan, timing
          └─ Chấp nhận có điều kiện: thay đổi đã review
                    │
                    ▼
           Gating release + báo cáo kết quả
```

Khi cần chạy trên nhiều profile, có thể cấu hình job CI riêng cho từng tổ hợp. Ví dụ *pseudo-configuration* thể hiện mục đích, không phải cấu hình dành cho một CI provider cụ thể:

```yaml
matrix:
  - id: baseline
    jdk: "<supported-jdk>"
    driver: "<baseline-driver>"
    database: "<baseline-db-version>"
  - id: candidate
    jdk: "<target-jdk>"
    driver: "<candidate-driver>"
    database: "<candidate-db-version>"

steps:
  - provision_database
  - apply_migrations
  - run_jdbc_contract_tests
  - collect_results_and_metrics
  - compare_with_baseline
  - enforce_release_gate
```

**Không đặt secret trong file matrix**. Credentials lấy từ kênh secret CI, có phạm vi quyền tối thiểu và không ghi vào build log. Test phải báo đủ driver/server version đã chạy, không chỉ tên job “candidate”.

### Hai cách kiểm thử khác nhau cần cùng có

**Fresh install:** tạo schema mới trên DB phiên bản mục tiêu rồi chạy suite. Nó phát hiện lỗi câu DDL hoặc code hoạt động trên schema mới.

**Upgrade path:** bắt đầu từ **schema/dữ liệu phiên bản hiện hành**, chạy đúng migration theo thứ tự, sau đó chạy suite và kiểm tra dữ liệu lịch sử còn đúng. Đây là phép thử thường bắt được lỗi không xuất hiện khi cài mới: đổi cột, chuyển encoding, thay index, constraint mới, default value và xử lý dữ liệu không đồng nhất.

Cần thêm một bước kiểm tra compatibility trong giai đoạn **ứng dụng cũ và mới cùng tồn tại** nếu hệ thống triển khai rolling deployment. Đừng chỉ thử phiên bản Java mới với schema mới.

## 15. Báo cáo sai khác theo rủi ro, không chỉ so PASS/FAIL

Kết quả tốt phải giúp người quyết định nâng cấp hiểu **điều gì khác và hậu quả là gì**:

| Trường | Ví dụ nên ghi |
| --- | --- |
| Contract ID | `JDBC-COMPAT-BATCH-004` |
| Loại thay đổi | Driver D1 → D2, giữ DB S1 |
| Bối cảnh | JDK, driver, DB, schema version, pool, timezone |
| Dữ liệu đầu vào | Bộ fixture và số dòng, không chứa PII thật |
| Baseline | `executeBatch()` trả số hàng chính xác |
| Candidate | Trả `SUCCESS_NO_INFO` cho một số lệnh |
| Tác động | DAO đang đòi row count = 1 → không thể xác nhận cập nhật |
| Mức độ | Blocking nếu nghiệp vụ cần chính xác từng hàng |
| Hướng xử lý | Đổi chiến lược update/kiểm chứng hoặc giới hạn driver config đã test |
| Quyết định | Block release / chấp nhận có điều kiện / không ảnh hưởng |

Một số sai khác có thể chấp nhận:

- `SQLException.getMessage()` đổi ngôn ngữ nhưng mapper của ứng dụng vẫn phân loại đúng.
- Thứ tự kết quả không có `ORDER BY` thay đổi, trong khi nghiệp vụ không đòi thứ tự.
- `BigDecimal.scale()` khác nhưng giá trị số trùng và nghiệp vụ không phụ thuộc scale.

Một số sai khác phải điều tra trước khi phát hành:

- Chữ Unicode bị sai, số tiền bị làm tròn không đúng.
- Transaction rollback không hoàn tác đầy đủ.
- Một lệnh cập nhật có điều kiện giờ ghi đè dữ liệu cũ.
- Generated key bị thiếu hoặc ghép sai vào đối tượng khác.
- TLS/hostname verification hoặc quyền database yếu đi.
- p99 tăng đáng kể vượt SLO, lock wait/deadlock tăng không được xử lý.

**Điều tra nguyên nhân:** nếu cả driver và DB cùng đổi, dùng lại ma trận ở phần 2 hoặc test bổ sung trên các tổ hợp được nhà cung cấp hỗ trợ để xác định phần gây thay đổi. Không tự giả định “vì driver mới” chỉ vì lỗi xuất hiện sau cập nhật.

## 16. Hiệu năng phải được kiểm tra như một hợp đồng vận hành

Một bản nâng cấp có thể làm kế hoạch SQL thay đổi. Cùng một query:

```sql
SELECT id, total
FROM orders
WHERE customer_id = ?
ORDER BY id;
```

có thể chạy với kế hoạch và độ trễ khác sau khi database nâng phiên bản, index statistics thay đổi hoặc driver đổi fetch size. Vì vậy nên giữ một **performance regression suite** đại diện:

- Các truy vấn đọc/ghi quan trọng, đặc biệt N+1/bulk/batch có nhiều request.
- `executeBatch()` với kích thước lô nhỏ, vừa và lớn đã được nghiệp vụ sử dụng.
- ResultSet nhiều dòng và dữ liệu lớn; đo cả tổng thời gian duyệt, memory, GC và thời gian giữ connection.
- Connection creation, pool acquisition p50/p95/p99, active/idle/pending.
- Transaction dài, lock wait, deadlock/serialization error rate.
- Throughput và p95/p99 latency dưới **mức đồng thời tương tự** môi trường thật.

Các nguyên tắc đo:

1. Dùng **cùng dữ liệu và thiết lập index/statistics phù hợp** trên baseline/candidate.
2. Ghi cấu hình driver (batch rewrite, prepared statement cache, fetch size, SSL), pool và server.
3. Chạy warm-up, nhiều vòng đo, báo biến thiên và percentile; không chỉ một lần benchmark.
4. Không so số lệnh `executeBatch()` với round trip mạng như thể chúng tương đương.
5. Đặt ngưỡng regression dựa trên SLO và sai số đo, không khóa release vì chênh lệch 1 ms ngẫu nhiên.
6. Tách *functionally compatible* với *operationally acceptable*: phải đạt **cả hai** để phát hành an toàn.

Nếu hiệu năng xấu, kiểm tra execution plan, stats, index, protocol/driver settings, fetch/pool behavior trước khi tăng `maximumPoolSize`. Tăng pool quá mức có thể làm DB bão hòa nhanh hơn.

## 17. Thử nghiệm nâng cấp/triển khai: không bỏ qua rollback

Đưa driver mới vào artifact Java thường dễ đảo ngược hơn một migration database đã thay đổi dữ liệu. Vì vậy cần kế hoạch riêng cho hai loại nâng cấp.

### Thay driver

1. Đóng băng phiên bản driver hiện hành và kiểm tra JDK/DB compatibility của phiên bản mới.
2. Chạy contract suite trên baseline/candidate, ghi những thuộc tính mới và mặc định thay đổi.
3. Triển khai canary cho một phần nhỏ lưu lượng nếu hạ tầng hỗ trợ.
4. Quan sát kết nối lỗi, TLS/auth errors, SQLState bất thường, batch, generated keys, timeout, p95/p99 và memory.
5. Nếu có regression, rollback artifact hoặc cấu hình driver theo kế hoạch đã diễn tập.

**Chú ý:** rollback driver không nhất thiết giải quyết dữ liệu đã được ghi sai khi canary chạy. Cần test bất biến và đối soát dữ liệu, không chỉ chuyển jar về phiên bản cũ.

### Nâng phiên bản database

1. Kiểm tra đường hỗ trợ nâng cấp, backup/snapshot, cơ chế restore và yêu cầu downtime của sản phẩm.
2. Thử migration trên bản sao dữ liệu thử nghiệm đại diện; xác minh encoding, kiểu, khóa, trigger, stored procedure, quyền.
3. Chạy contract suite với driver hiện hành (nếu còn được hỗ trợ) và driver mục tiêu.
4. Thử **app cũ + schema mới** và **app mới + schema mới** trong giai đoạn rolling deploy. Nếu có yêu cầu tương thích ngược, cân nhắc mô hình **expand → migrate → contract**.
5. Thiết lập canary/giám sát, kế hoạch failover và phương án khôi phục được hỗ trợ.
6. Định nghĩa rõ **điểm không thể quay lại** khi schema/data đã đổi hoặc ghi bằng format mới; không coi rollback DDL là luôn an toàn.

### Tính tương thích khi cùng tồn tại hai phiên bản ứng dụng

Giả sử ứng dụng mới ghi thêm giá trị enum hoặc cấu trúc JSON mà ứng dụng cũ không hiểu. Database và driver có thể hoạt động hoàn hảo, nhưng rolling deployment vẫn lỗi. Vì vậy phải kiểm tra **kho dữ liệu dùng chung giữa phiên bản app cũ và mới**, gồm đọc dữ liệu do bản kia ghi, quyền, schema và invariants.

**Không khẳng định “rollback thành công” chỉ vì ứng dụng cũ khởi động lại được.** Cần xác minh dữ liệu/transaction sau quá trình quay lại.

## 18. Những sai lầm dễ gặp khi thiết kế compatibility test

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ thử `SELECT 1` | Bỏ qua conversion, transaction, batch, error, TLS | Dùng contract suite có dữ liệu và lỗi đại diện |
| Test trên DB giả lập thay vì DB đích | Không thấy khác biệt driver, SQL dialect, locking | Dùng database/driver thật cho integration |
| Chỉ kiểm tra kiểu trả về không kiểm tra giá trị | Sai Unicode/scale/NULL không bị phát hiện | Round-trip các dữ liệu biên |
| So toàn bộ exception message | Test vỡ vì wording khác, không phản ánh nghiệp vụ | Kiểm tra loại lỗi/SQLState/mapper ở mức phù hợp |
| Bỏ qua rollback và cleanup | Fixture rò rỉ, flaky, khóa tồn đọng | Transaction có rollback và kiểm tra hậu điều kiện |
| Dựa vào metadata `supports...()` | Tính năng được quảng bá nhưng SQL cụ thể vẫn lỗi | Test đúng lời gọi JDBC ứng dụng dùng |
| Chạy test đồng thời không điều phối | Kết quả may rủi, khó tái hiện | Latch/barrier và timeout, ID fixture riêng |
| Chỉ chạy fresh install | Không thấy lỗi migration dữ liệu cũ | Có cả upgrade-path test |
| Chỉ thử một tổ hợp ứng viên | Khó phân biệt nguyên nhân driver/DB/JDK | Lập ma trận phiên bản được hỗ trợ |
| Dùng một benchmark đơn luồng | Không thấy pool contention/lock và p99 | Đo theo tải đồng thời và SLO |
| Thấy test PASS là triển khai 100% ngay | Chưa quan sát lỗi ngoài dữ liệu thử | Canary, monitoring, rollback plan |
| Lấy bản cũ làm “chân lý” tuyệt đối | Duy trì hành vi sai hoặc không được cam kết | So với contract nghiệp vụ và tài liệu driver |

Một bộ test tốt không cố bao phủ **mọi** API JDBC nếu ứng dụng không sử dụng chúng. Hãy xuất phát từ đường đi dữ liệu và lỗi **có tác động lớn**, sau đó mở rộng test khi bổ sung tính năng hoặc gặp regression.

## 19. Kế hoạch kiểm thử thực hành

### Bài tập 1 — xây ma trận tương thích

Chọn một ứng dụng JDBC nhỏ với một baseline và một bản driver ứng viên. Ghi đầy đủ JDK, driver, server DB, schema version, pool, timezone, TLS và quyền. Nếu có kế hoạch nâng DB, thêm release candidate phù hợp ma trận hỗ trợ.

### Bài tập 2 — xây bộ dữ liệu hợp đồng

Tạo `jdbc_compat_probe` ở phần 4. Viết test:

1. `INSERT` chuỗi Unicode và `BigDecimal`.
2. `SELECT` đọc đúng các cột, xử lý SQL `NULL`.
3. `UPDATE WHERE version=?` làm tăng version và ngăn cập nhật dùng phiên bản cũ.
4. `rollback()` và dùng connection khác xác minh bản ghi đã bị hoàn tác.

Chạy **cùng mã kiểm thử** trên baseline và candidate.

### Bài tập 3 — bổ sung batch và generated keys

Tạo một bảng identity phù hợp dialect, dùng `RETURN_GENERATED_KEYS`; chèn một hàng và đọc khóa sinh. Sau đó chạy batch có phần tử gây unique violation trên DB thử nghiệm, ghi `getUpdateCounts()` và `getNextException()`. Đừng viết test dựa trên thứ tự batch keys nếu tài liệu driver không bảo đảm.

### Bài tập 4 — thử transaction đồng thời

Dùng hai connection độc lập để gây stale version, lock wait hoặc serialization conflict trong môi trường riêng. Xác định **bất biến nghiệp vụ**, các loại `SQLException` có thể chấp nhận và chính sách rollback/retry. Không chia sẻ một connection giữa nhiều thread như thể JDBC chuẩn bảo đảm thread-safety.

### Bài tập 5 — kiểm thử nâng cấp dữ liệu lịch sử

Tạo database phiên bản baseline, nạp dữ liệu chứa Unicode, decimal, `NULL`, chuỗi dài và ngày giờ ở các biên. Chạy đúng migration lên schema mục tiêu, sau đó chạy suite trên dữ liệu cũ và dữ liệu mới. Kiểm tra các lỗi conversion và tính toàn vẹn sau migration.

### Bài tập 6 — đánh giá hiệu năng và triển khai

Chọn hai truy vấn quan trọng và một batch writer. Đo latency end-to-end, p95/p99, throughput, số round trip nếu có metric, lock wait và pool active/idle/pending trên hai tổ hợp. Lập kế hoạch canary, ngưỡng rollback và phương án đối soát dữ liệu nếu sau phát hành phát hiện lỗi.

### Câu hỏi tự đánh giá

- Vì sao một lần `getConnection()` và `SELECT 1` thành công không chứng minh driver mới tương thích với ứng dụng?
- Khi `BigDecimal.compareTo() == 0` nhưng `scale()` khác nhau, đó có phải lỗi hay không? Ai quyết định?
- Nếu driver mới trả `SUCCESS_NO_INFO` cho batch thay vì `1`, DAO có thể tiếp tục khẳng định cập nhật đúng một hàng không?
- Với hai transaction cùng đọc `version=1`, test nên khóa cứng `executeUpdate() == 0` hay kiểm tra bất biến không bị ghi đè?
- Tại sao cần cả test fresh install lẫn test migration từ schema hiện hành?
- `DatabaseMetaData.supportsGetGeneratedKeys()` có thay thế test `getGeneratedKeys()` sau batch không?
- Vì sao không so sánh nguyên `SQLException.getMessage()` giữa hai database?
- Nếu canary của driver mới được rollback, những thay đổi dữ liệu đã ghi trong giai đoạn canary có tự biến mất không?
- Làm thế nào tách regression của driver khỏi regression của phiên bản server khi cả hai cùng đổi?

## 20. Checklist trước khi chấp nhận phiên bản mới

- [ ] Driver và DB mục tiêu nằm trong **ma trận phiên bản được hỗ trợ**; JDK tương thích.
- [ ] Đã ghi tên và phiên bản thực tế từ `DatabaseMetaData`, không chỉ từ tên artifact CI.
- [ ] Các cấu hình JDBC URL, TLS, xác thực, secret và quyền được kiểm chứng ở môi trường đích.
- [ ] CRUD với `PreparedStatement` và `ResultSet` giữ đúng số hàng, Unicode, `BigDecimal` và SQL `NULL`.
- [ ] Kiểu thời gian và các kiểu SQL nâng cao **đang được ứng dụng sử dụng** có test round-trip.
- [ ] Generated keys, batch update counts, `BatchUpdateException` và lỗi ràng buộc được xử lý đúng.
- [ ] Commit/rollback, isolation, optimistic locking và ít nhất một tình huống đồng thời được thử trên database thật.
- [ ] Pool, fetch size, cursor, timeout và cancellation không gây leak hoặc mất kết quả mà ứng dụng không phát hiện.
- [ ] Error translator hoạt động với SQLState/vendor code/class mới, không dựa vào thông điệp lỗi.
- [ ] Có test **schema hiện hành → migration → schema mới**, không chỉ cài mới.
- [ ] Có báo cáo phân loại mọi khác biệt PASS/FAIL/UNSUPPORTED và mức độ ảnh hưởng.
- [ ] Performance regression theo workload thật và p95/p99 nằm trong ngưỡng chấp nhận.
- [ ] Có kế hoạch canary/giám sát, rollback/failover và đối soát dữ liệu sau khi triển khai.
- [ ] CI secrets, log và artifact kết quả không chứa credential hoặc dữ liệu khách hàng thật.

## 21. Tổng kết

1. **Kiểm thử tương thích JDBC là kiểm thử hành vi, không chỉ API.** Mọi thay đổi driver/database có thể ảnh hưởng kiểu dữ liệu, SQL, transaction, timeout, security và hiệu năng.
2. **Chạy cùng contract suite trên baseline và ứng viên.** Khóa những bất biến có ý nghĩa nghiệp vụ, không khóa cứng chi tiết không được JDBC/driver cam kết.
3. **Kiểm tra đường lỗi và cạnh tranh, không chỉ đường thành công.** Batch thất bại, lost update, rollback, deadlock, timeout và trạng thái commit không rõ là những trường hợp quan trọng.
4. **Dùng database thật và dữ liệu đại diện.** Driver, SQL dialect, locking và migration không thể được chứng minh đầy đủ bởi mock hoặc DB giả lập.
5. **Bảo vệ cả tính đúng và hiệu năng.** Cần kiểm tra p95/p99, tài nguyên pool, lock wait, timeout và TLS/role; functional PASS chưa đủ.
6. **Kiểm thử đường nâng cấp và khả năng quay lại.** Fresh install, upgrade migration, rolling deployment, canary, giám sát và data reconciliation là các phần của quyết định phát hành.
7. **Để kết quả hỗ trợ quyết định.** Mỗi khác biệt phải có bằng chứng, tác động, owner và hành động; không bỏ qua chỉ vì phiên bản mới có tính năng hấp dẫn.

**Kết luận:** Khi nâng driver hoặc phiên bản cơ sở dữ liệu trong một ứng dụng Java dùng JDBC, hãy định nghĩa **hợp đồng dữ liệu và giao dịch cần được giữ**, chạy bộ kiểm thử đó trên **đúng ma trận phiên bản được hỗ trợ**, rồi kết hợp kiểm thử tích hợp, benchmark và canary có kế hoạch khôi phục. Một lần kết nối thành công chỉ là bước đầu; **giữ đúng hành vi nghiệp vụ và vận hành sau nâng cấp** mới là tiêu chí tương thích có giá trị.
