# Quản lý trạng thái phiên khi tái sử dụng kết nối

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java kết nối với cơ sở dữ liệu quan hệ thông qua đối tượng `Connection`. Ở ứng dụng nhỏ, mỗi thao tác có thể tự mở rồi đóng kết nối vật lý. Trong dịch vụ web hoặc hệ thống có nhiều yêu cầu đồng thời, việc tạo kết nối liên tục rất tốn chi phí, nên ứng dụng thường dùng **connection pool** để tái sử dụng chúng.

Tái sử dụng kết nối giúp giảm thời gian tạo phiên DBMS, nhưng đặt ra một yêu cầu quan trọng: **một yêu cầu không được thừa hưởng trạng thái phiên ngoài ý muốn từ yêu cầu trước**. Nếu phiên còn transaction chưa hoàn tất, chế độ `autoCommit=false`, schema cũ, biến phiên xác định tenant, khóa phiên hoặc bảng tạm, thao tác tiếp theo có thể đọc/sửa sai dữ liệu, bị chặn hoặc hành xử khác thường.

Bài thuộc chương **Quản lý kết nối** này giải thích trạng thái phiên gồm những gì, connection pool xử lý đến đâu, và cách thiết kế ranh giới mượn–trả kết nối an toàn trong JDBC.

## 1. Phân biệt `Connection`, phiên DBMS và connection pool

Một lần gọi `dataSource.getConnection()` thường trả về một đối tượng `Connection` để ứng dụng sử dụng. Với pool, đối tượng nhận được có thể là **proxy kết nối logic** đại diện cho một kết nối vật lý đang có sẵn.

| Thành phần | Ý nghĩa | Vòng đời thường gặp |
| --- | --- | --- |
| **JDBC `Connection`** | Giao diện Java để thực thi SQL, điều khiển transaction và các thuộc tính của kết nối | Một đơn vị công việc hoặc request |
| **Kết nối vật lý** | Kênh giao tiếp thực sự giữa driver và DBMS | Tồn tại qua nhiều lượt mượn của pool |
| **Phiên DBMS (session)** | Ngữ cảnh phía DBMS gắn với kết nối, có thể giữ biến phiên, role, cấu hình và tài nguyên | Thường tồn tại cùng kết nối vật lý, tùy DBMS/kiến trúc |
| **Connection pool** | Quản lý tập kết nối, cho mượn và thu hồi để tái sử dụng | Suốt vòng đời ứng dụng hoặc `DataSource` |

Một pool có thể cho các request sử dụng lần lượt cùng một phiên:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant Pool as Connection pool
    participant DB as DBMS session S1
    participant B as Request B
    A->>Pool: getConnection()
    Pool-->>A: JDBC Connection logic C1
    A->>DB: SQL và thay đổi trạng thái phiên
    A->>Pool: C1.close()
    Note over Pool,DB: Pool trả lại S1 sau khi xử lý reset theo hợp đồng
    B->>Pool: getConnection()
    Pool-->>B: JDBC Connection logic C2
    B->>DB: SQL trên session S1 được tái sử dụng
~~~

Điều này giải thích tại sao gọi `Connection.close()` là bắt buộc ngay cả với pool: thông thường lời gọi ấy **trả kết nối về pool**, không nhất thiết đóng socket vật lý. Nếu không đóng, pool dần hết kết nối để cấp phát; nếu trả về khi trạng thái chưa được xử lý, yêu cầu khác có thể bị ảnh hưởng.

> **Nguyên tắc:** hãy xem mỗi lượt mượn `Connection` là một lần sử dụng tạm thời một tài nguyên có trạng thái. Đơn vị công việc phải kết thúc transaction và dọn những thay đổi phiên mà nó tạo ra trước khi kết nối được tái sử dụng.

## 2. “Trạng thái phiên” gồm những gì?

Không có một API JDBC duy nhất có thể đọc hoặc đặt lại toàn bộ trạng thái của mọi DBMS. Có thể chia các loại trạng thái thành hai nhóm chính.

### 2.1. Thuộc tính có API trên `Connection`

| Trạng thái | API đọc / ghi thường gặp | Tác động nếu bị giữ lại |
| --- | --- | --- |
| **Auto-commit** | `getAutoCommit()` / `setAutoCommit(boolean)` | Thao tác mới có thể vô tình tham gia transaction hoặc không được commit |
| **Read-only** | `isReadOnly()` / `setReadOnly(boolean)` | Truy vấn ghi có thể bị từ chối hoặc hệ thống định tuyến khác tùy driver/DB |
| **Transaction isolation** | `getTransactionIsolation()` / `setTransactionIsolation(int)` | Thao tác khác có độ cô lập ngoài dự kiến; có thể ảnh hưởng khóa và tính nhất quán |
| **Catalog** | `getCatalog()` / `setCatalog(String)` | SQL không ghi rõ catalog có thể trỏ sai ngữ cảnh |
| **Schema** | `getSchema()` / `setSchema(String)` | Tên bảng không ghi schema có thể ánh xạ sang nơi khác |
| **Holdability** | `getHoldability()` / `setHoldability(int)` | Hành vi cursor qua commit có thể khác |
| **Network timeout** | `getNetworkTimeout()` / `setNetworkTimeout(Executor,int)` | Request khác bị timeout quá ngắn hoặc chờ quá lâu |
| **Client info** | `getClientInfo()` / `setClientInfo(...)` | Thông tin chẩn đoán/ứng dụng cũ có thể còn trong phiên |

Mức hỗ trợ các thuộc tính phụ thuộc driver, JDBC version và DBMS. Một số phương thức có thể ném `SQLFeatureNotSupportedException`; `setReadOnly(true)` ở nhiều hệ thống chỉ là **gợi ý** tối ưu hoặc cấu hình ở phiên, không phải cơ chế phân quyền đủ mạnh. Không mặc định mọi driver đều reset tất cả các thuộc tính trên.

### 2.2. Trạng thái do lệnh SQL và DBMS tạo ra

Ngoài API của `Connection`, hệ quản trị có thể duy trì trạng thái qua câu lệnh SQL hoặc hành động khác:

- **Session variables / session parameters**, chẳng hạn múi giờ, định dạng ngày, timeout hoặc biến ngữ cảnh ứng dụng.
- **Role / authorization context** được thay đổi trong phiên, nếu DBMS hỗ trợ.
- **Default schema / search path** được đặt bằng SQL.
- **Temporary tables**, cursor hoặc đối tượng tạm có vòng đời liên quan đến phiên.
- **Session-level advisory locks** hoặc loại khóa do ứng dụng giữ tường minh.
- **Prepared statement phía DBMS** hoặc tài nguyên phiên khác do driver/ứng dụng tạo và quản lý.
- **Trạng thái transaction đang hoạt động**, bao gồm khóa, thao tác chưa commit và trạng thái transaction bị lỗi.

Một pool có thể biết khi bạn gọi `connection.setReadOnly(true)` và đặt lại thuộc tính đó lúc trả về. Nhưng nếu ứng dụng chạy câu SQL thay đổi biến phiên, pool **không nhất thiết biết** trạng thái mới. Hợp đồng reset phải được xác định theo cả **pool lẫn DBMS**.

## 3. Điều gì xảy ra khi phiên bị “rò rỉ” trạng thái?

Giả sử một pool chỉ có một kết nối vật lý đang được hai request mượn lần lượt.

~~~text
Request A:
  mượn connection
  thay đổi schema mặc định thành tenant_a
  SELECT ... FROM orders
  trả connection về pool

Request B:
  mượn lại chính connection đó
  SELECT ... FROM orders
  -> có thể đọc tenant_a nếu schema cũ vẫn còn
~~~

Tình huống này đặc biệt nguy hiểm nếu hệ thống đa tenant dùng session state để hỗ trợ cô lập dữ liệu. **Không được xem schema hay biến phiên còn sót là bằng chứng tenant đã được xác thực.** Mỗi request phải được xác thực/phân quyền độc lập và thiết lập ngữ cảnh hợp lệ trước thao tác; hệ thống DB cũng phải có ràng buộc quyền tương ứng.

Một ví dụ khác về transaction:

~~~text
Request A:
  setAutoCommit(false)
  UPDATE account SET ...
  không commit/rollback
  trả connection

Request B:
  mượn connection cùng phiên
  SELECT ... hoặc UPDATE ...
  -> có thể thấy transaction cũ, giữ khóa hoặc hành vi auto-commit sai
~~~

Pool triển khai tốt thường cố gắng rollback transaction chưa hoàn tất và đặt lại các thuộc tính JDBC đã biết trước khi cho mượn tiếp. Tuy nhiên, **không nên dựa vào việc pool sẽ luôn sửa mọi sai sót**, nhất là khi thay đổi trạng thái bằng SQL riêng của DBMS, khi kết nối không hợp lệ hoặc khi dùng pool/proxy cấu hình đặc biệt.

## 4. Các ranh giới cần quản lý khi mượn và trả kết nối

Một cách nghĩ thực tế là chia mỗi lượt sử dụng thành bốn giai đoạn:

~~~mermaid
flowchart LR
    A["Borrow: lấy Connection từ DataSource"] --> B["Setup: áp dụng cấu hình/transaction cần thiết"]
    B --> C["Work: bind SQL, thực thi, đọc kết quả"]
    C --> D["Finish: commit hoặc rollback; đóng ResultSet/Statement"]
    D --> E["Cleanup: reset trạng thái riêng; close() trả pool"]
~~~

Ở ranh giới này, cần thực hiện những việc sau:

1. **Xác lập giả định đầu vào.** Ví dụ, pool được cấu hình `autoCommit=true` và isolation mặc định; hoặc framework quản lý transaction thay ứng dụng. Mỗi mô hình phải có hợp đồng rõ.
2. **Thay đổi thuộc tính trước khi chạy công việc.** Chẳng hạn cấu hình read-only/isolation nên được thực hiện trước khi transaction bắt đầu nếu driver yêu cầu.
3. **Kết thúc transaction chủ động.** Commit khi thành công; rollback khi thất bại. Đừng dựa vào `close()` như một thao tác commit/rollback nghiệp vụ.
4. **Đóng `ResultSet` và `Statement`.** Cursor và statement có thể giữ tài nguyên DBMS dù connection còn tồn tại.
5. **Khôi phục trạng thái do đơn vị công việc thay đổi.** Gồm thuộc tính JDBC và câu SQL session state nếu pool không đảm bảo việc này.
6. **Trả hoặc loại bỏ kết nối.** Kết nối hợp lệ được trả về pool; kết nối có trạng thái không xác định hoặc lỗi mạng nghiêm trọng cần được xử lý theo cơ chế hủy/invalidate của pool.

Không dùng một `Connection` đang mượn đồng thời cho nhiều request/thread trừ khi driver và mô hình đồng bộ có hợp đồng rõ ràng. Connection và transaction thường nên thuộc về một đơn vị công việc tại một thời điểm.

## 5. Transaction là trạng thái cần xử lý trước tiên

`autoCommit=true` thường là trạng thái mặc định của `Connection` mới theo JDBC. Khi `autoCommit=false`, nhiều câu SQL có thể cùng tham gia một transaction cho tới khi ứng dụng gọi `commit()` hoặc `rollback()`. Nếu trả kết nối về pool khi transaction chưa kết thúc, thay đổi chưa commit và khóa có thể ảnh hưởng request sau.

### Ví dụ an toàn: transaction trong phạm vi mượn kết nối

Đoạn mã dưới đây giả định `DataSource`/pool được cấu hình để cho mượn kết nối ở `autoCommit=true`, đặt lại thuộc tính JDBC khi trả về và loại bỏ kết nối không còn sử dụng an toàn. Ứng dụng chủ động commit/rollback; không dùng `close()` thay cho một trong hai thao tác.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void deduct(long accountId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Pool không cung cấp trạng thái autoCommit mong đợi");
            }

            connection.setAutoCommit(false);
            try {
                String sql = """
                    UPDATE account
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """;
                try (PreparedStatement ps =
                             connection.prepareStatement(sql)) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, accountId);
                    ps.setBigDecimal(3, amount);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Không tìm thấy tài khoản hoặc không đủ tiền");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                    // Nếu rollback thất bại, trạng thái kết nối không chắc chắn.
                    // Cần để pool loại bỏ/invalidate theo cơ chế của nó.
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ dùng **text block** của Java 15 trở lên. Trong dự án sử dụng transaction manager (ví dụ framework quản lý @Transactional), **không tự tạo transaction JDBC lồng bên trong một kết nối do framework đang quản lý**. Khi framework sở hữu giao dịch, hãy để framework chịu trách nhiệm commit/rollback và ranh giới lấy/trả connection.

Mã ví dụ minh họa ranh giới transaction; ứng dụng thực tế còn phải giải quyết rủi ro khi `commit()` trả lỗi: đôi lúc không biết chắc DBMS đã commit hay chưa. Không tự động lặp lại nghiệp vụ chuyển tiền/trừ tiền khi kết quả commit chưa rõ nếu không có thiết kế idempotency.

### Vì sao không gọi `setAutoCommit(true)` tùy tiện để reset?

Theo hợp đồng JDBC, **thay đổi chế độ auto-commit trong khi transaction đang hoạt động có thể commit transaction hiện tại**. Vì vậy, đoạn mã sau là một lỗi nghiêm trọng:

~~~java
connection.setAutoCommit(false);
// UPDATE ...
// Quên rollback khi lỗi:
connection.setAutoCommit(true); // Có thể commit thay đổi chưa định hủy!
~~~

Phải **commit hoặc rollback trước** khi phục hồi auto-commit. Nếu rollback thất bại vì lỗi kết nối/DBMS, trạng thái transaction có thể không xác định; cần xử lý kết nối như không an toàn để tái sử dụng và dùng cơ chế invalidate của pool, không tiếp tục reset bằng các lệnh có thể vô tình commit.

### `close()` không thay thế commit/rollback

Gọi `connection.close()` với pool có thể kích hoạt cleanup/rollback do pool cung cấp, nhưng **JDBC không đảm bảo rằng đóng một connection đang còn transaction sẽ luôn tương đương rollback theo mọi driver/DBMS và cấu hình**. Hãy viết logic kết thúc transaction rõ ràng, và coi cơ chế rollback khi trả về pool là lớp bảo vệ bổ sung.

## 6. Read-only, isolation và schema: thiết lập/khôi phục có chủ đích

Với `Connection` do ứng dụng toàn quyền quản lý, có thể cần điều chỉnh một số thuộc tính cho công việc cụ thể. Ví dụ một truy vấn báo cáo:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public static long countActiveUsers(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        boolean originalReadOnly = connection.isReadOnly();

        try {
            connection.setReadOnly(true);
            String sql = "SELECT COUNT(*) FROM app_user WHERE active = ?";
            try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {
                ps.setBoolean(1, true);
                try (ResultSet rs = ps.executeQuery()) {
                    rs.next();
                    return rs.getLong(1);
                }
            }
        } finally {
            connection.setReadOnly(originalReadOnly);
        }
    }
}
~~~

Ví dụ cho thấy **lưu trạng thái ban đầu → thay đổi → sử dụng → khôi phục**. Tuy nhiên, ở hệ thống sử dụng pool thực tế, bạn phải xác nhận khả năng hỗ trợ `setReadOnly`, giai đoạn transaction phù hợp và cơ chế reset của pool; một số pool tự theo dõi thuộc tính JDBC và reset khi trả về. Khi có framework quản lý, thường nên khai báo read-only tại ranh giới transaction của framework để tránh hai nơi cùng điều khiển một kết nối.

Với isolation, quy tắc cũng tương tự:

~~~java
int originalIsolation = connection.getTransactionIsolation();
try {
    connection.setTransactionIsolation(
            Connection.TRANSACTION_READ_COMMITTED);
    // Bắt đầu và thực thi công việc theo isolation yêu cầu.
} finally {
    // Chỉ khôi phục sau khi transaction đã kết thúc.
    connection.setTransactionIsolation(originalIsolation);
}
~~~

Đoạn này là **mẫu minh họa**, không phải một transaction hoàn chỉnh. Một số driver/DBMS không cho đổi isolation trong transaction đang hoạt động, hoặc đổi isolation có hiệu lực theo quy tắc DBMS riêng. Do đó:

- Cấu hình isolation **trước** khi bắt đầu transaction được quản lý.
- Kiểm tra DBMS/driver hỗ trợ isolation mong muốn hay không; không giả định `SERIALIZABLE` có cùng hành vi trong mọi hệ quản trị.
- Khôi phục hoặc để pool/framework reset **sau khi transaction kết thúc**.

`setSchema(...)` và `setCatalog(...)` có thể thay đổi cách tên đối tượng SQL không ghi đầy đủ được phân giải. Nếu cần truy cập nhiều schema, thường an toàn hơn khi tổ chức một `DataSource`/quy ước truy cập rõ ràng cho từng phạm vi hoặc dùng tên đối tượng được kiểm soát. Với multi-tenant, việc thay schema không thể thay cho kiểm tra quyền và cô lập tenant.

## 7. Trạng thái thay đổi bằng SQL không tự biến mất khi trả pool

Đây là nhóm rủi ro dễ bị bỏ qua nhất. Ví dụ, một ứng dụng dùng SQL đặc thù của DBMS để đổi search path, timezone hoặc role trong session:

~~~sql
-- Ví dụ theo cú pháp PostgreSQL:
SET search_path TO tenant_a, public;
SET TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Những thiết lập phiên dạng này có thể **tồn tại sau khi câu SQL hoàn tất**, và một pool chỉ reset các thuộc tính `Connection` có thể không nhận biết chúng. Request sau mượn cùng kết nối vật lý có thể nhận trạng thái mới.

Một số cách kiểm soát:

1. **Tránh thay đổi session lâu dài nếu không cần thiết.** Ưu tiên cấu hình cố định của datasource/connection initialization theo mục đích.
2. **Ưu tiên phạm vi transaction** khi DBMS hỗ trợ, ví dụ biến chỉ có hiệu lực trong transaction.
3. **Có quy trình reset tương ứng** với mọi thay đổi session-level mà ứng dụng chủ động thực hiện.
4. **Kiểm tra đặc tính DBMS cụ thể**, vì lệnh reset, vòng đời bảng tạm/cursor và cơ chế role khác nhau.
5. **Đánh dấu kết nối không an toàn** nếu không thể xác nhận reset thành công; pool cần hủy phiên vật lý và tạo mới theo cấu hình của nó.

### Ví dụ riêng PostgreSQL: biến ngữ cảnh trong phạm vi transaction

PostgreSQL hỗ trợ hàm `set_config(name, value, is_local)`. Khi `is_local = true` và lệnh được thực thi trong một transaction, giá trị được đặt có phạm vi **transaction hiện tại** và được phục hồi theo quy tắc của PostgreSQL khi transaction kết thúc.

~~~java
// Cần chạy sau connection.setAutoCommit(false) và trước truy vấn nghiệp vụ.
// Đây là API riêng của PostgreSQL, không phải SQL/JDBC portable.
String sql = "SELECT set_config('app.tenant_id', ?, true)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, Long.toString(authenticatedTenantId));
    try (ResultSet rs = ps.executeQuery()) {
        rs.next();
    }
}
~~~

Giá trị `authenticatedTenantId` phải được lấy từ ngữ cảnh **đã xác thực và đã phân quyền**, không tin trực tiếp vào tham số client gửi lên. Nếu dùng row-level security hoặc cơ chế phân quyền theo session variable, chính sách DBMS phải được thiết kế sao cho biến thiếu/sai không mở quyền rộng hơn; việc bind tham số chỉ ngăn SQL injection, **không tự chứng minh quyền truy cập**.

Không áp dụng ví dụ `set_config` cho MySQL/SQL Server/Oracle mà không đổi thiết kế theo cú pháp và cơ chế phiên của DBMS đó.

## 8. Temporary table, cursor và khóa phiên

Một số trạng thái không thể “reset” chỉ bằng `setAutoCommit(true)`, `setReadOnly(false)` hoặc `rollback()`:

| Tài nguyên phiên | Rủi ro khi trả kết nối | Điểm cần kiểm tra |
| --- | --- | --- |
| **Temporary table** | Bảng hoặc dữ liệu tạm có thể tồn tại qua transaction/lượt mượn theo cách DBMS định nghĩa | Vòng đời `ON COMMIT`, khi nào drop, session reset có xóa không |
| **Cursor / open result set** | Giữ tài nguyên, gây cản trở truy vấn tiếp theo hoặc pool không thể tái sử dụng đúng | Đóng `ResultSet`, `Statement`, xử lý streaming theo driver |
| **Session-level advisory lock** | Khóa có thể còn giữ sau commit/rollback tùy DBMS | Mở/giải phóng có cặp; phân biệt session lock và transaction lock |
| **SQL session variables** | Biến của request trước ảnh hưởng logic, format hoặc phân quyền | Thiết lập scope, cleanup, kiểm thử mượn lại |
| **Server-side prepared objects** | Chiếm tài nguyên trong phiên; hành vi cache khác theo driver/pool | Đóng statement và hiểu cơ chế cache/prepared statement |

Ví dụ, một số DBMS hỗ trợ **khóa phiên** tồn tại qua commit và chỉ được nhả bằng lệnh riêng hoặc khi kết nối vật lý đóng. Nếu ứng dụng quên nhả rồi trả về pool, lời gọi `close()` trên proxy không đảm bảo đã hủy phiên vật lý, nên khóa có thể kéo dài.

Để tránh sự cố, xác định trước **tài nguyên nào gắn với transaction, tài nguyên nào gắn với session**. Đặc biệt thận trọng với câu SQL tự tạo bảng tạm, đổi role, tạo cursor thủ công hoặc dùng advisory lock theo phiên.

## 9. Ai chịu trách nhiệm reset: ứng dụng, pool hay framework?

Trách nhiệm cụ thể phụ thuộc stack. Không nên giả định mọi connection pool đều có cùng tập thuộc tính được reset hoặc cùng thời điểm reset.

| Bên sở hữu | Trách nhiệm cần được xác định |
| --- | --- |
| **Code nghiệp vụ / DAO** | Kết thúc transaction do nó quản lý; đóng `ResultSet`/`Statement`; dọn session state riêng do nó tạo |
| **Transaction manager** | Điều phối commit/rollback, binding connection theo thread/request và reset trạng thái transaction theo hợp đồng |
| **Connection pool** | Quản lý mượn–trả, kiểm tra/loại bỏ kết nối hỏng, reset các thuộc tính JDBC mà pool hỗ trợ |
| **DBMS / driver** | Triển khai chính xác semantics session, transaction, lệnh reset, cursor và các giới hạn |

Một số trường hợp cần trao đổi rõ trách nhiệm:

- Dự án dùng framework transaction: **service** đánh dấu transaction, **framework** giữ connection đến lúc commit/rollback, sau đó trả pool. DAO không đóng connection do framework cấp ngoài hợp đồng.
- Dự án thuần JDBC: phương thức nghiệp vụ có thể tự `getConnection`, quản lý commit/rollback và `close()` theo `try-with-resources`.
- Dự án dùng biến SQL/session tạm: kể cả khi framework quản lý transaction, ứng dụng vẫn phải xác định cách đưa trạng thái đó về baseline.

### “Reset về mặc định” cần một baseline cụ thể

Baseline là các giá trị mà pool/framework và ứng dụng đã thống nhất cho mỗi lần sử dụng: chẳng hạn `autoCommit=true`, read-only false, isolation được cấu hình, schema/catelog mặc định, không có transaction đang hoạt động và không có session variables do request trước để lại.

Không nên suy đoán “mặc định” bằng các giá trị cố định như `READ_COMMITTED` hay schema `public` trong mọi DBMS. Dự án có thể chủ động dùng isolation hoặc schema khác. **Reset đúng là reset về cấu hình đã thỏa thuận**, không nhất thiết về mặc định của một DBMS bất kỳ.

## 10. Khi lỗi xảy ra trong lúc cleanup

Một lỗi SQL có thể khiến transaction trở thành trạng thái **aborted/failed** và không cho chạy câu SQL khác cho tới khi rollback (tùy DBMS). Mạng có thể mất ngay khi đang commit/rollback. Trong những trường hợp này:

1. **Giữ lại lỗi gốc** của nghiệp vụ, đồng thời ghi nhận lỗi rollback/cleanup bằng `addSuppressed` hoặc cơ chế log phù hợp.
2. Nếu rollback thất bại, **không mặc định kết nối an toàn để trả cho người khác**; sử dụng cơ chế invalidate/evict/close vật lý theo hợp đồng của pool.
3. Nếu kết quả commit không rõ vì lỗi mạng, **không tự động retry thao tác không idempotent**. Cần xác minh trạng thái nghiệp vụ hoặc có khóa/idempotency key.
4. Khi câu lệnh SQL thay đổi session state bị lỗi giữa chừng, kiểm tra DBMS xem trạng thái đã áp dụng hay chưa; không giả định lỗi đồng nghĩa mọi thay đổi phiên đều được hoàn tác.
5. Ghi log có kiểm soát: loại lỗi, SQLState, vendor code, kết nối/pool metrics; không ghi password hoặc dữ liệu nhạy cảm.

Ví dụ bổ sung ngoại lệ rollback mà không che mất nguyên nhân ban đầu:

~~~java
try {
    // Các câu SQL và connection.commit().
} catch (SQLException | RuntimeException original) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        original.addSuppressed(rollbackError);
        // Pool cần được thông báo để loại kết nối không an toàn,
        // theo API riêng của thư viện pool đang dùng.
    }
    throw original;
}
~~~

Đoạn mã trên chỉ minh họa cách bảo toàn lỗi; `connection` là biến đã được khai báo bên ngoài. Không có API **pool invalidate** chung cho mọi `DataSource` trong JDBC; cách đánh dấu kết nối hỏng phụ thuộc thư viện pool hoặc framework. `Connection.abort(Executor)` là một API khác nhưng không nên mặc định gọi lên mọi connection proxy mà không hiểu hợp đồng pool.

## 11. Kiểm tra trạng thái khi nhận kết nối

Ở giai đoạn phát triển/diagnostics, có thể ghi nhận các thuộc tính JDBC cơ bản trước và sau một đơn vị công việc:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

public static void printJdbcState(Connection connection)
        throws SQLException {
    System.out.println("autoCommit=" + connection.getAutoCommit());
    System.out.println("readOnly=" + connection.isReadOnly());
    System.out.println("isolation=" +
            connection.getTransactionIsolation());
    System.out.println("catalog=" + connection.getCatalog());
    // getSchema() chỉ dùng khi driver/JDBC version có hỗ trợ.
    System.out.println("schema=" + connection.getSchema());
}
~~~

Chương trình này không đọc được mọi session variable hay khóa riêng của DBMS, và một số phương thức có thể không được driver hỗ trợ. Khi triển khai đo đạc dài hạn, chỉ log thông tin cần thiết; tên schema, catalog hoặc session context có thể chứa thông tin nhạy cảm.

### Kiểm thử tái sử dụng theo hai lượt mượn

Một kiểm thử hữu ích nên chủ động tạo trạng thái trong **lượt mượn A**, trả kết nối, rồi xác minh baseline trong **lượt mượn B**:

~~~text
Chuẩn bị:
  Pool test kích thước 1 (hoặc bảo đảm hai lần mượn cùng kết nối vật lý).
  Xác định baseline: autoCommit, isolation, readOnly, schema và session state.

Lượt A:
  Mượn kết nối.
  Thay đổi thuộc tính JDBC và một biến SQL phiên được phép thử.
  Thực hiện truy vấn.
  Kết thúc transaction/cleanup theo thiết kế và close().

Lượt B:
  Mượn lại kết nối.
  Đọc các thuộc tính JDBC.
  Kiểm tra cả biến SQL/session state bằng câu truy vấn theo DBMS.
  Xác nhận không còn trạng thái của A.

Lượt lỗi:
  Tạo lỗi SQL giữa transaction.
  Đảm bảo rollback/đánh dấu kết nối hỏng được xử lý.
  Mượn lại và xác minh hệ thống vẫn hoạt động đúng.
~~~

Cỡ pool bằng 1 giúp dễ tái sử dụng một kết nối, nhưng không bảo đảm tuyệt đối nếu pool loại bỏ kết nối hỏng, hết tuổi hoặc chủ động khởi tạo kết nối mới. Nếu cần chứng minh **cùng phiên**, dùng cách định danh phiên an toàn do DBMS cung cấp trong môi trường test.

Các tình huống nên thử thêm:

| Tình huống | Kỳ vọng |
| --- | --- |
| Request A đổi `readOnly` rồi kết thúc | B nhận cấu hình đã quy định |
| A đổi isolation | B không thừa hưởng isolation trái hợp đồng |
| A rollback do lỗi SQL | B không thấy thao tác chưa commit, không giữ khóa cũ |
| A đổi schema/search path bằng SQL | B không còn schema của A nếu thiết kế yêu cầu baseline khác |
| A dùng biến ngữ cảnh tenant | B không thể đọc dữ liệu tenant của A do state còn sót |
| A bị lỗi mạng khi commit | Hệ thống không mượn lại kết nối có trạng thái mơ hồ |
| A để mở cursor/statement | Cleanup hoàn tất hoặc pool có cơ chế phát hiện rò rỉ |

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Không gọi `close()` trên kết nối lấy từ pool | Cạn pool, request chờ rồi timeout | Dùng `try-with-resources` hoặc để transaction manager điều phối |
| Tin rằng `close()` của proxy luôn đóng phiên vật lý | Biến SQL/session lock vẫn tồn tại | Xác định vòng đời phiên và cơ chế reset thực tế |
| Thay `autoCommit=false` rồi quên commit/rollback | Giao dịch chưa kết thúc, khóa và thay đổi còn treo | Kết thúc transaction rõ ràng trong mọi nhánh |
| Reset `autoCommit=true` khi rollback chưa chắc thành công | Có thể commit thay đổi lẽ ra phải hủy | Rollback/commit trước; loại bỏ kết nối nếu trạng thái không xác định |
| Đổi isolation hoặc read-only giữa transaction | Lỗi driver hoặc hành vi ngoài dự kiến | Cấu hình trước transaction, khôi phục sau transaction |
| Dùng SQL `SET ...` rồi giả định pool tự reset | Request sau nhận cấu hình của request trước | Dùng scope transaction hoặc cleanup DB-specific |
| Dùng session variable như nguồn xác thực duy nhất | Rủi ro truy cập chéo tenant nếu state còn sót hoặc bị kiểm soát sai | Xác thực/ủy quyền riêng, thiết lập state có kiểm chứng, bảo vệ ở DB |
| Dùng một `Connection` cho nhiều request đồng thời | Transaction và trạng thái bị đan xen, khó tái hiện lỗi | Mỗi đơn vị công việc mượn kết nối riêng |
| Dựa vào cỡ pool lớn để che rò rỉ | Lỗi xuất hiện muộn nhưng vẫn tồn tại | Đóng tài nguyên và giám sát active/idle/leak metrics |

## 13. Quy trình thực hành cho một chức năng JDBC

Khi chuẩn bị đưa chức năng truy cập dữ liệu lên môi trường dùng chung:

1. **Xác định chủ sở hữu transaction:** mã JDBC thuần hay framework transaction manager?
2. **Xác định baseline của pool:** auto-commit, isolation, read-only, catalog/schema, timeout và hành vi reset.
3. **Liệt kê mọi thay đổi trạng thái phiên:** cả lời gọi `setXxx` của `Connection` lẫn câu SQL `SET`, biến tenant, bảng tạm hoặc khóa phiên.
4. **Thiết kế phạm vi sống ngắn:** chỉ mượn connection lúc cần, không giữ xuyên request hoặc giữa các thread.
5. **Tạo nhánh kết thúc transaction rõ ràng:** thành công commit, thất bại rollback; xử lý riêng kết nối không chắc chắn.
6. **Dọn tài nguyên và state phụ:** đóng result set/statement, phục hồi các thay đổi chưa được pool đảm bảo reset.
7. **Đóng connection logic đúng cách:** trả pool bằng `close()` hoặc giao cho framework đang sở hữu.
8. **Kiểm thử lượt A → B trên cùng phiên:** gồm cả đường thành công và đường lỗi, với các biến SQL riêng của DBMS.
9. **Giám sát ở runtime:** kết nối đang mượn, thời gian chờ, transaction kéo dài, lỗi rollback và kết nối bị loại bỏ.

**Điều cần ghi nhớ:** pool tái sử dụng **kết nối và có thể cả phiên DBMS**, vì vậy session state phải được coi là một phần của dữ liệu cần quản lý. Khi ứng dụng hoàn thành transaction, khôi phục trạng thái đã thay đổi và trả kết nối đúng cách, các request tiếp theo có thể sử dụng lại tài nguyên JDBC mà không bị ảnh hưởng bởi công việc trước đó.
