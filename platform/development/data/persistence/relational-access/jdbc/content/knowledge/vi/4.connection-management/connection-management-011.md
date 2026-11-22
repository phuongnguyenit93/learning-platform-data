# Quản lý thông tin phiên và ngữ cảnh truy cập theo yêu cầu

## 1. Vì sao quản lý kết nối phải gắn với ngữ cảnh yêu cầu?

Trong **JDBC (Java Database Connectivity)**, API Java để truy cập cơ sở dữ liệu quan hệ, ứng dụng gọi `DataSource.getConnection()` để nhận một `Connection` và dùng nó thực thi SQL. Với ứng dụng web hoặc dịch vụ nhiều người dùng, mỗi yêu cầu (*request*) còn có ngữ cảnh riêng: người dùng đã xác thực, tổ chức/tenant được phép truy cập, mã theo dõi yêu cầu, quyền nghiệp vụ, múi giờ hoặc phạm vi giao dịch.

Ví dụ, hai yêu cầu đến cùng một API:

- Yêu cầu A thuộc tenant `101`, được phép xem đơn hàng của tenant `101`.
- Yêu cầu B thuộc tenant `202`, chỉ được phép xem đơn hàng của tenant `202`.

Nếu ứng dụng dùng connection pool, A và B **có thể lần lượt sử dụng cùng một kết nối vật lý** đến cơ sở dữ liệu. Vì vậy, một thay đổi về schema, vai trò, biến phiên hoặc transaction do A thực hiện có thể ảnh hưởng tới B nếu trạng thái đó được giữ lại sai cách.

Mục tiêu của **quản lý thông tin phiên và ngữ cảnh truy cập theo yêu cầu** là bảo đảm mỗi thao tác JDBC chạy với **đúng dữ liệu, đúng quyền và đúng phạm vi hiệu lực**, rồi dọn dẹp tài nguyên trước khi phục vụ yêu cầu tiếp theo.

## 2. Phân biệt ba phạm vi trạng thái

Từ “phiên” dễ gây nhầm lẫn vì ứng dụng và cơ sở dữ liệu có nhiều loại phạm vi tồn tại khác nhau.

| Phạm vi | Ai sở hữu? | Ví dụ thông tin | Thời điểm kết thúc |
|---|---|---|---|
| **Ngữ cảnh yêu cầu** (*request context*) | Tầng web/dịch vụ | Người dùng đã xác thực, tenant được cấp quyền, request ID, deadline | Khi xử lý yêu cầu hoàn tất |
| **Lượt mượn `Connection` logic** | Đoạn mã dùng JDBC | `Connection`, `PreparedStatement`, kết quả truy vấn, trạng thái cần khôi phục | Khi gọi `Connection.close()` hoặc ra khỏi `try-with-resources` |
| **Phiên DB vật lý** (*database session*) | JDBC driver, DBMS và có thể là connection pool | Schema hiện hành, session variables, vai trò SQL, cấu hình phiên | Khi kết nối vật lý bị đóng; trong pool có thể sống qua nhiều lượt mượn |
| **Giao dịch DB** (*transaction*) | Mã ứng dụng hoặc transaction manager | Các thay đổi chưa commit, khóa và một số thiết lập có phạm vi giao dịch | Khi `commit()` hoặc `rollback()` |

Một HTTP request có thể thực hiện nhiều truy vấn hoặc nhiều giao dịch. Một `Connection` logic có thể tồn tại suốt một giao dịch; kết nối vật lý phía dưới có thể được tái sử dụng cho nhiều request khác nhau. **Không có quan hệ một-một mặc định giữa HTTP request, JDBC `Connection` và phiên vật lý của DBMS.**

Sơ đồ sau biểu diễn hai yêu cầu tuần tự cùng sử dụng một kết nối vật lý trong pool:

```text
HTTP request A              CONNECTION POOL                 HTTP request B
  tenant=101                       │                           tenant=202
       │                           │                               │
       ├── getConnection() ───────►│                               │
       │                  Connection logic A                        │
       │                           │                               │
       ├── SQL cho tenant 101 ─────┤──► Phiên DB vật lý #1          │
       │                           │                               │
       └── close() ───────────────►│                               │
                                   │   kiểm tra / làm sạch         │
                                   │◄──────── getConnection() ─────┤
                                   │         Connection logic B    │
                                   ├──► Phiên DB vật lý #1 ◄───────┤
                                   │           tenant 202          │
                                   │◄──────────── close() ─────────┘
```

**`Connection.close()` trên handle lấy từ pool thường trả kết nối về pool**, không nhất thiết đóng phiên DB vật lý. Vì vậy, đóng handle là điều bắt buộc nhưng chưa đủ để khẳng định mọi giá trị phiên tùy biến đã được xóa.

## 3. Phân loại thông tin ngữ cảnh trước khi đưa vào JDBC

Không phải thông tin nào trong request cũng nên được đẩy vào phiên cơ sở dữ liệu.

| Thông tin | Nguồn tin cậy và cách sử dụng | Gợi ý quản lý |
|---|---|---|
| **Tenant ID** | Lấy từ kết quả xác thực/phân quyền phía server, không tin trực tiếp ID do client khai báo | Đưa thành tham số `PreparedStatement` trong điều kiện truy vấn; nếu DB dùng RLS, kết hợp chính sách RLS phù hợp |
| **User ID / vai trò nghiệp vụ** | Đã được máy chủ xác thực và kiểm tra quyền | Dùng ở tầng phân quyền; chỉ ánh xạ sang DB role/session context khi thiết kế DB yêu cầu |
| **Request ID / trace ID** | Sinh/chuẩn hóa bởi hạ tầng ứng dụng | Ghi log/tracing; có thể đặt biến phiên **có phạm vi giao dịch** nếu DB hỗ trợ |
| **Schema/catalog** | Giá trị xác định từ cấu hình hoặc mapping tenant đã kiểm duyệt | Ưu tiên SQL đủ điều kiện hoặc chính sách định tuyến rõ ràng; chỉ `setSchema`/`setCatalog` khi driver hỗ trợ |
| **Múi giờ, locale** | Cấu hình nghiệp vụ đã chuẩn hóa | Thống nhất kiểu lưu trữ và cách chuyển đổi thời gian; tránh đổi setting phiên tùy tiện theo request |
| **Transaction settings** | Quy tắc nghiệp vụ và transaction manager | Chọn `autoCommit`, isolation/read-only trước các câu lệnh thuộc giao dịch; commit/rollback rõ ràng |

Ví dụ, `tenantId` có thể xuất hiện trong URL `/tenants/202/orders`, nhưng ứng dụng **phải xác thực quyền** của người gọi với tenant `202` trước khi dùng ID đó để truy vấn. Bản thân `PreparedStatement` giúp tránh SQL injection cho **giá trị đầu vào**, nhưng không tự xác minh tenant có thuộc quyền truy cập của người gọi hay không.

Trong thực tế, một lớp `RequestContext` ở tầng dịch vụ có thể chứa `authorizedTenantId`, `userId`, `requestId`. Lớp truy cập dữ liệu chỉ nên nhận những giá trị đã được xác thực và thật sự cần thiết. Không lưu `Connection` vào request context để sử dụng ở mọi thread hoặc giữ qua nhiều request.

## 4. Vòng đời an toàn của một request sử dụng JDBC

Một quy trình phổ biến gồm các bước:

1. **Xác thực, phân quyền trước khi truy vấn**: xác định danh tính và tenant mà request được phép truy cập.
2. **Lấy kết nối khi cần**: gọi `DataSource.getConnection()` trong phạm vi công việc, tránh giữ connection nhàn rỗi trong khi thực hiện xử lý không liên quan đến DB.
3. **Cấu hình đúng phạm vi**: nếu cần transaction hoặc biến phiên, đặt chúng trên kết nối vừa mượn **trước** các câu SQL phụ thuộc trạng thái đó.
4. **Thực thi SQL qua cùng ngữ cảnh đã xác minh**: truyền tham số bằng `PreparedStatement`, kiểm soát quyền và sử dụng nhất quán cùng giao dịch nếu cần tính nguyên tử.
5. **Hoàn tất giao dịch**: `commit()` khi thành công, `rollback()` khi lỗi; không dựa vào `close()` để ngầm quyết định nghiệp vụ.
6. **Khôi phục hoặc xóa thiết lập riêng của request**, theo hợp đồng DBMS, driver, pool và transaction manager.
7. **Đóng tài nguyên**: đóng `ResultSet`, `Statement`, `Connection`, ưu tiên `try-with-resources` để trả handle logic kể cả khi ném ngoại lệ.

```text
Xác thực request
      │
      ▼
Xác định tenant/user/context đáng tin cậy
      │
      ▼
Mượn Connection → Thiết lập transaction/context cần thiết
      │
      ▼
Thực thi SQL bằng tham số và đúng quyền
      │
      ├── Thành công ──► commit()   ──┐
      └── Thất bại ────► rollback() ──┤
                                     ▼
                        Làm sạch trạng thái cần thiết
                                     │
                                     ▼
                          Đóng / trả Connection
```

Với truy vấn chỉ đọc đơn giản ở chế độ auto-commit mặc định, không nhất thiết phải mở một giao dịch thủ công. Đối với thao tác nhiều câu lệnh phải cùng thành công hoặc cùng thất bại, cần quản lý giao dịch rõ ràng hoặc dùng transaction manager của framework.

## 5. Cách làm JDBC phổ biến và độc lập DBMS: đưa tenant vào tham số SQL

Giả sử bảng `orders` có các cột `id`, `tenant_id`, `status`. Tầng xác thực đã xác định `authorizedTenantId`; repository dùng thông tin đó để giới hạn dữ liệu trả về.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    // authorizedTenantId phải được tầng dịch vụ xác minh trước khi gọi.
    public List<String> findStatuses(long authorizedTenantId) throws SQLException {
        String sql = "SELECT status FROM orders " +
                     "WHERE tenant_id = ? ORDER BY id";
        List<String> statuses = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, authorizedTenantId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    statuses.add(rs.getString("status"));
                }
            }
        }

        return statuses;
    }
}
```

Đoạn mã này có một số tính chất cần ghi nhớ:

- **Phạm vi dữ liệu thể hiện ngay trong SQL** qua `WHERE tenant_id = ?`; không cần đổi schema hoặc biến phiên để chọn tenant.
- **Mỗi lần gọi phương thức tự lấy và trả `Connection`**; không giữ kết nối trong field dùng chung của đối tượng repository.
- **`PreparedStatement` ràng buộc `tenant_id` như giá trị**, giúp tránh ghép chuỗi SQL không an toàn.
- `try-with-resources` đóng kết quả, statement và connection khi hoàn tất, kể cả khi lỗi.

Đây là kỹ thuật giới hạn kết quả truy vấn, **không thay thế thiết kế bảo mật**. Toàn bộ các truy vấn đọc/ghi liên quan vẫn phải dùng đúng tenant và quyền; có thể tăng cường bằng phân quyền cơ sở dữ liệu, row-level security (RLS) hoặc một kiến trúc tách dữ liệu tenant phù hợp. Không nên xem việc thêm một điều kiện `WHERE` ở một API riêng lẻ là bằng chứng rằng toàn hệ thống đã cô lập tenant.

## 6. Khi cần biến phiên DB theo request: ưu tiên phạm vi giao dịch

Đôi khi DBMS, audit trigger hoặc hệ thống quan sát cần biết request ID, application context hoặc vai trò đã được xác thực. Một số DBMS cung cấp **session variables** hoặc **transaction-local settings**. Chúng khác nhau đáng kể:

| Cách thiết lập | Phạm vi điển hình | Nguy cơ khi dùng connection pool |
|---|---|---|
| **Thiết lập cấp phiên** (*session-scoped*) | Có thể còn hiệu lực đến hết phiên DB vật lý hoặc đến khi được thay đổi/reset | Yêu cầu tiếp theo có thể nhìn thấy giá trị cũ nếu pool không xóa |
| **Thiết lập cấp giao dịch** (*transaction-scoped*) | Chỉ trong giao dịch hiện tại; kết thúc khi commit/rollback | Hạn chế việc mang trạng thái sang giao dịch sau, nếu dùng đúng cơ chế DBMS |
| **Giá trị tham số truy vấn** | Chỉ có nghĩa trong câu SQL được gửi | Không thay đổi trạng thái phiên; thuận tiện cho dữ liệu nghiệp vụ |

Khi có lựa chọn, ưu tiên đưa dữ liệu nghiệp vụ thành **tham số SQL**, còn thông tin phụ trợ cho audit/tracing nên dùng **thiết lập cấp giao dịch** nếu DBMS hỗ trợ. Tránh dùng một lệnh `SET` cấp phiên cho mỗi request khi không có cơ chế reset trạng thái đáng tin cậy.

### Ví dụ PostgreSQL: đặt request ID trong một giao dịch

PostgreSQL cho phép dùng `set_config(name, value, is_local)`; tham số thứ ba `true` yêu cầu giá trị có **phạm vi giao dịch hiện tại**. Ví dụ dưới đây đặt `app.request_id` để các thao tác trong cùng transaction có thể tra cứu ngữ cảnh này. Đây là **cú pháp riêng của PostgreSQL**, không phải API SQL chung cho mọi driver JDBC.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int markReady(long authorizedTenantId, long orderId,
                         String requestId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false); // Bắt đầu dùng giao dịch tường minh.

            try {
                try (PreparedStatement context = connection.prepareStatement(
                        "SELECT set_config('app.request_id', ?, true)")) {
                    context.setString(1, requestId);
                    try (ResultSet result = context.executeQuery()) {
                        result.next(); // SELECT set_config trả về một hàng.
                    }
                }

                int updated;
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE orders SET status = ? " +
                        "WHERE id = ? AND tenant_id = ?")) {
                    statement.setString(1, "READY");
                    statement.setLong(2, orderId);
                    statement.setLong(3, authorizedTenantId);
                    updated = statement.executeUpdate();
                }

                connection.commit();
                return updated;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        } // Connection logic được đóng/trả cho pool.
    }
}
```

Giả định bảng `orders(id, tenant_id, status)` tồn tại, `authorizedTenantId` đã được kiểm tra quyền, `requestId` do ứng dụng sinh/chuẩn hóa và transaction được quản lý trực tiếp tại đây. Khi `commit()` hoặc `rollback()` kết thúc giao dịch, giá trị đặt bởi `set_config(..., true)` hết hiệu lực theo quy tắc PostgreSQL.

**Giới hạn cần chú ý:** Đoạn mã minh họa việc quản lý transaction thủ công. Trong hệ thống thật, một connection pool phải có chính sách khôi phục `autoCommit` và các trạng thái khác trước khi cấp lượt mượn mới. Nếu framework hoặc transaction manager đang sở hữu giao dịch, phải dùng chính cơ chế đó để mở giao dịch và đặt ngữ cảnh; không tự gọi `commit()`/`rollback()` làm phá vỡ giao dịch do framework quản lý. Việc khôi phục `autoCommit` hoặc trạng thái phiên còn phụ thuộc hợp đồng pool đang dùng.

Tùy thiết kế, cơ sở dữ liệu có thể dùng `current_setting('app.request_id', true)` để đọc request ID trong giao dịch (ví dụ trong trigger audit). Giá trị này chỉ phục vụ **truy vết/điều phối đã được thiết kế**; không nên coi một biến phiên do ứng dụng có thể tự đặt là bằng chứng xác thực danh tính hoặc cơ chế bảo mật độc lập.

## 7. Nếu ngữ cảnh là schema, catalog hoặc vai trò SQL

Một kiến trúc khác lưu mỗi tenant ở một schema hoặc database riêng. Khi đó ứng dụng có thể cần chọn schema/catalog hoặc kết nối tới database đích theo mapping đáng tin cậy.

Với JDBC, các phương thức `Connection.getSchema()`, `setSchema(String)`, `getCatalog()` và `setCatalog(String)` cho phép đọc/đề nghị đổi ngữ cảnh khi driver hỗ trợ. Tuy nhiên:

- Không phải DBMS nào cũng dùng catalog/schema theo cùng một mô hình; `setCatalog()` không nhất thiết chuyển sang một database khác.
- Một số driver không hỗ trợ `setSchema()`; có thể ném `SQLFeatureNotSupportedException` hoặc có hành vi riêng.
- **Tên schema, catalog và role là định danh**, không thể truyền như giá trị `?` thay cho phần tên bảng trong SQL. Phải chọn chúng từ mapping/danh sách cho phép, không nối chuỗi từ đầu vào tùy ý.
- Việc đổi schema chỉ thay đổi cách phân giải đối tượng theo quy tắc DBMS; **không tự động cấp hoặc giới hạn quyền**. Quyền DB và chính sách tách tenant vẫn phải được thiết kế và kiểm chứng.
- Nếu dùng cùng một pool cho nhiều schema, phải bảo đảm trạng thái schema/role được **khôi phục hoặc reset** trước khi kết nối được cấp lại.

Ví dụ truy vấn `SELECT ... FROM sales.orders` có tên schema đủ điều kiện có thể giúp tránh phụ thuộc schema mặc định nếu DBMS hỗ trợ cú pháp đó. Trong các hệ thống nhiều database riêng, một số kiến trúc định tuyến request tới **`DataSource` hoặc pool đã cấu hình cho đúng database** thay vì thử thay đổi database trên một kết nối đang tồn tại.

Riêng với PostgreSQL, `search_path` cũng là trạng thái phiên có thể ảnh hưởng tới cách giải quyết tên bảng/hàm. Nếu buộc phải đổi `search_path`, cần kiểm soát những schema được đưa vào danh sách tìm kiếm và phạm vi hiệu lực. Không xem việc thay đổi `search_path` như một thao tác cấp quyền truy cập.

## 8. Kết nối, giao dịch và thread: đừng dùng chung sai phạm vi

Thông tin của một HTTP request thường đi qua controller, service và repository. Việc dùng `ThreadLocal` để lưu request context có thể xuất hiện ở một số framework, nhưng **`ThreadLocal` không đồng nghĩa với trạng thái phiên JDBC**:

- `ThreadLocal` chỉ gắn với thread Java; một request bất đồng bộ có thể chuyển thread, và thread pool có thể tái sử dụng thread cho request khác.
- `Connection` là đối tượng quản lý truy cập và trạng thái transaction. Không nên tự chia sẻ cùng một handle cho nhiều công việc đồng thời.
- Một lời gọi repository tự tạo `Connection` mới có thể nhận kết nối vật lý khác với lời gọi trước. Nếu nhiều thao tác phải dùng chung transaction, chúng phải được quản lý trên **cùng một transaction context** theo hợp đồng framework hoặc cùng một `Connection` được truyền/giữ trong phạm vi thao tác.
- `Connection` đã `close()` không còn hợp lệ cho request hiện tại, dù kết nối vật lý phía dưới có thể vẫn sống trong pool.

Ví dụ sai về ý tưởng:

```java
// Không làm như sau: một Connection dùng chung cho các request.
class UnsafeRepository {
    private Connection sharedConnection;
    // Nhiều thread/request có thể cùng thay schema và transaction trên handle này.
}
```

Nên giữ `DataSource` là thành phần dùng chung đã được cấu hình, còn `Connection` được mượn trong đúng phạm vi công việc. Đối với transaction do framework quản lý, dùng repository và API transaction của framework để mọi truy vấn thuộc cùng giao dịch được gắn với đúng connection.

## 9. Xử lý lỗi, timeout và hủy yêu cầu

Quy trình quản lý context vẫn phải hoạt động khi request bị lỗi giữa chừng:

| Tình huống | Hệ quả tiềm ẩn | Hướng xử lý |
|---|---|---|
| Truy vấn SQL ném `SQLException` | Giao dịch có thể cần rollback, connection có thể không còn hợp lệ | Rollback nếu đang quản lý transaction; giữ nguyên nguyên nhân và đóng tài nguyên |
| Client ngắt kết nối hoặc request hết hạn | Công việc DB có thể còn đang thực thi | Áp dụng timeout phù hợp, cơ chế hủy theo framework/driver, luôn trả connection khi kết thúc |
| Pool hết kết nối rảnh | Request có thể phải chờ và cuối cùng timeout | Đo số lượt chờ, kiểm tra leak, giao dịch kéo dài và cấu hình pool |
| Reset session state thất bại | Lượt mượn tiếp theo có thể thấy trạng thái sai | Đánh dấu/loại bỏ kết nối theo chính sách của pool; không tự cấp lại tài nguyên chưa được làm sạch |
| Giao tiếp với DB bị ngắt khi `commit()` | Có thể chưa chắc giao dịch đã commit hay chưa | Không retry mù lệnh ghi; cần chiến lược idempotency và đối soát trạng thái nghiệp vụ |

`Statement.setQueryTimeout(int)` cho phép yêu cầu giới hạn thời gian thực thi statement; `Connection.setNetworkTimeout(...)` tác động tới một số thao tác mạng và phụ thuộc driver. Chúng **không tự động kết thúc toàn bộ request**, không thay thế deadline ở tầng ứng dụng và không bảo đảm hủy công việc ở máy chủ tức thì.

Khi có transaction, cần xác định timeout thuộc tầng nào (request, pool acquisition, transaction, statement, mạng) và cách xử lý rollback. Không nên giữ một connection đang chờ gọi API ngoài hoặc chạy xử lý CPU dài nếu việc đó không cần tài nguyên DB.

## 10. Quan sát và kiểm thử rò rỉ ngữ cảnh giữa các request

Các chỉ số hữu ích khi vận hành connection pool gồm **số kết nối đang mượn**, **số đang rảnh**, **thời gian chờ mượn**, **thời gian giữ kết nối**, **số timeout** và **số kết nối lỗi**. Có thể kết hợp chúng với request ID trong log của ứng dụng để xác định giao dịch hoặc request giữ kết nối quá lâu.

Tuy nhiên, không nên xuất mật khẩu, token, câu SQL chứa dữ liệu nhạy cảm hoặc toàn bộ session context vào log. Request ID phục vụ liên kết log có thể được sinh/chuẩn hóa bởi máy chủ, tránh tin vô điều kiện vào chuỗi bất kỳ do client gửi.

Một kiểm thử tích hợp quan trọng cho hệ thống có nhiều tenant:

1. Cấu hình pool nhỏ, chẳng hạn tối đa một kết nối vật lý, để tăng khả năng tái sử dụng cùng phiên DB trong hai lượt mượn tuần tự.
2. Ở request A, dùng tenant `101`, đặt ngữ cảnh request hoặc schema thử nghiệm, chạy truy vấn và kết thúc công việc.
3. Ở request B, dùng tenant `202`, mượn tiếp và kiểm tra B chỉ xem được dữ liệu được phép của mình; xác nhận không thừa hưởng ngữ cảnh chỉ dành cho A.
4. Lặp lại phép thử khi request A thất bại và rollback, khi timeout, và khi pool phải loại bỏ kết nối hỏng.
5. Nếu dùng thiết lập phiên riêng của DBMS, kiểm tra trực tiếp thông số đó theo quy ước DBMS sau khi kết thúc transaction và trong lần mượn mới.

Kết quả mong đợi là **không có thông tin đặc thù A gây ảnh hưởng đến B**. Đừng chỉ kiểm tra trên máy phát triển với một request đơn lẻ: lỗi rò rỉ context thường chỉ xuất hiện khi kết nối vật lý được tái sử dụng hoặc khi hai request chạy xen kẽ.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao nguy hiểm? | Cách đúng |
|---|---|---|
| “Mỗi HTTP request luôn có một phiên DB vật lý mới.” | Pool có thể tái sử dụng phiên cũ mang session state | Phân biệt request context, lượt mượn logic, transaction và phiên vật lý |
| “`close()` luôn xóa mọi `SET` của database.” | Nhiều cấu hình phiên riêng của DBMS có thể còn tồn tại | Dùng phạm vi giao dịch hoặc reset đã kiểm chứng |
| “Tenant ID trong URL là tenant đã được phép.” | Client có thể đổi ID để truy cập dữ liệu tenant khác | Xác thực và phân quyền trước khi truyền ID tới JDBC |
| “`PreparedStatement` bảo đảm phân quyền.” | Nó ràng buộc giá trị, không kiểm soát quyền truy cập | Phân quyền ở tầng ứng dụng và/hoặc DBMS |
| “Có thể dùng biến phiên làm bằng chứng người dùng đã xác thực.” | Biến phiên có thể bị thay đổi bởi mã sở hữu kết nối | Thiết kế cơ chế xác thực, quyền DB/RLS và nguồn context đáng tin cậy |
| “Đổi `setSchema()` là đủ cô lập tenant.” | Schema không thay thế quyền truy cập và còn nguy cơ rò rỉ qua pool | Kiểm tra mapping, quyền và chính sách reset |
| “`ThreadLocal` tự truyền sang mọi tác vụ bất đồng bộ.” | Request có thể chuyển thread hoặc thread được tái sử dụng | Truyền context theo hợp đồng của framework, làm sạch khi kết thúc |
| “SQL ghi lỗi kết nối thì cứ gửi lại ngay.” | Có thể chưa biết câu lệnh/giao dịch đã được DB thực hiện hay chưa | Dùng idempotency, đối soát và retry có điều kiện |

## 12. Tình huống tổng hợp

Một ứng dụng cho thuê lưu các đơn đặt chỗ của nhiều tenant chung bảng `bookings(booking_id, tenant_id, status)`. Request A được xác thực thuộc tenant `10`, request B thuộc tenant `20`. Hai request chạy tuần tự và pool có một kết nối vật lý.

**Câu hỏi 1:** B có thể dùng lại phiên DB mà A vừa dùng không?

**Có.** Mỗi request nhận một handle `Connection` logic khác nhau nhưng pool có thể cấp lại cùng kết nối vật lý.

**Câu hỏi 2:** Nếu A đặt biến phiên `app.tenant_id = '10'` bằng một thiết lập cấp phiên rồi trả connection mà không reset, B có thể gặp vấn đề gì?

**Có nguy cơ rò rỉ ngữ cảnh.** Nếu B hoặc chính sách truy cập DB phụ thuộc vào giá trị đó, B có thể bị xử lý theo ngữ cảnh cũ. B cần thiết lập lại ngữ cảnh phù hợp theo cơ chế đã kiểm chứng, hoặc hệ thống nên dùng thiết lập cấp giao dịch để tự hết hiệu lực khi transaction kết thúc.

**Câu hỏi 3:** Đâu là lựa chọn độc lập DBMS để giới hạn truy vấn theo tenant?

Sau khi xác thực quyền, truyền `authorizedTenantId` vào `PreparedStatement` và sử dụng điều kiện `WHERE tenant_id = ?` một cách nhất quán; đồng thời thiết kế các lớp bảo vệ cần thiết ở DBMS để tránh bỏ sót điều kiện tại một đường truy cập khác.

**Ghi nhớ:** Trong JDBC, ngữ cảnh truy cập phải được xác định từ yêu cầu đã xác thực và sử dụng trong **phạm vi công việc/giao dịch phù hợp**. `Connection` logic có thể được trả về pool trong khi phiên DB vật lý vẫn tồn tại. Vì vậy, truyền đúng tham số, kết thúc transaction, đóng connection và kiểm soát trạng thái phiên còn sót là những phần liên kết chặt chẽ của quản lý kết nối an toàn.
