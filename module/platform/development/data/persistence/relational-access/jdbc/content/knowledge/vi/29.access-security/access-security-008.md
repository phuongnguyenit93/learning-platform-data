# Bảo đảm điều kiện phân quyền luôn có trong truy vấn JDBC

Trong chương **Bảo mật truy cập**, một lỗi đặc biệt nguy hiểm là ứng dụng chạy **câu SQL hợp lệ nhưng thiếu điều kiện giới hạn dữ liệu theo người dùng hoặc tổ chức**. Không cần có SQL injection: chỉ một `SELECT` thiếu `tenant_id`, một `UPDATE` chỉ lọc theo `id`, hoặc một câu `COUNT(*)` không dùng cùng phạm vi phân quyền cũng có thể làm lộ dữ liệu hoặc chỉnh sửa bản ghi của người khác.

Với **JDBC**, ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua driver và `DataSource`, dùng `PreparedStatement` để tham số hóa SQL, `ResultSet` để đọc kết quả và transaction để thực hiện CRUD nhất quán. Tuy nhiên, **tham số hóa không tự thêm điều kiện phân quyền**. Ứng dụng phải thiết kế sao cho mọi truy vấn có thể tiếp cận dữ liệu được bảo vệ đều sử dụng đúng phạm vi đã được xác thực.

Bài học này dùng ví dụ hệ thống nhiều tổ chức (*multi-tenant*) có người sở hữu tài liệu và quản lý tổ chức. Phương pháp cũng áp dụng cho dự án, phòng ban, nhóm quyền, hồ sơ bệnh án hoặc bất kỳ nguồn dữ liệu nào có chính sách “ai được xem và sửa hàng nào”.

Sau bài học, bạn có thể:

- Phân biệt **xác thực, phân quyền, điều kiện lọc nghiệp vụ và SQL injection**.
- Áp dụng nguyên tắc **deny by default / fail closed** khi thiếu ngữ cảnh quyền.
- Đưa `tenant_id`, `owner_user_id` và điều kiện quyền vào ngay `SELECT`, `COUNT`, `UPDATE` và `DELETE`.
- Tránh lỗi `OR`, `JOIN`, truy vấn động, phân trang và batch làm mất phạm vi phân quyền.
- Tổ chức tầng Java/JDBC để **khó tạo câu truy vấn không có scope**, đồng thời dùng Row-Level Security (RLS) như lớp bảo vệ bổ sung khi DBMS hỗ trợ.
- Xây dựng kiểm thử xác nhận **không đọc hoặc sửa được dữ liệu của tenant/người dùng khác**, kể cả khi định danh bản ghi bị đoán trúng.

## 1. Bốn khái niệm dễ bị trộn lẫn

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication – xác thực** | Ai đang đưa ra yêu cầu? | Người dùng `user_id = 41` đã đăng nhập |
| **Authorization – phân quyền** | Người này được làm gì đối với tài nguyên nào? | Chỉ xem tài liệu mình sở hữu trong tenant 7 |
| **Business filtering – lọc nghiệp vụ** | Người dùng muốn xem tập dữ liệu nào trong phạm vi đã được phép? | Chỉ những tài liệu `status = 'ACTIVE'` |
| **SQL parameterization – tham số hóa** | Làm sao truyền giá trị vào SQL mà không biến giá trị thành cú pháp SQL? | `WHERE tenant_id = ? AND status = ?` |

Cả bốn đều cần thiết nhưng **không thay thế nhau**.

Ví dụ câu SQL này đã dùng placeholder:

~~~sql
SELECT id, title FROM documents WHERE id = ?;
~~~

Nó chống việc tham số `id` bị diễn giải thành cú pháp SQL, nhưng **không kiểm tra tenant hoặc chủ sở hữu**. Nếu ứng dụng nhận `id` từ URL `/documents/100`, người dùng có thể thử ID của tài liệu khác. Đây là dạng rủi ro **Broken Object Level Authorization (BOLA/IDOR)**.

Một câu truy vấn có phạm vi quyền rõ ràng hơn:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = ?
  AND id = ?
  AND owner_user_id = ?;
~~~

Ba giá trị phải đến từ nguồn khác nhau:

- `tenant_id`: tenant đã được server xác thực và **xác nhận người dùng có quyền truy cập**.
- `id`: tài nguyên người dùng yêu cầu, là dữ liệu đầu vào **chưa đáng tin**.
- `owner_user_id`: định danh người dùng do server xác thực, **không lấy từ request body để quyết định quyền**.

**Nguyên tắc chính:** Quyền truy cập phải quyết định **những hàng SQL được phép chạm tới**, không chỉ quyết định có hiển thị những hàng đã đọc hay không.

## 2. Mô hình dữ liệu làm nền cho phân quyền hàng

Giả sử một hệ thống tài liệu nhiều tổ chức có hai bảng. Ví dụ DDL sau hướng tới DBMS có hỗ trợ khóa ngoại, transaction và kiểu `BIGINT`:

~~~sql
CREATE TABLE tenant_users (
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE documents (
    tenant_id BIGINT NOT NULL,
    id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, owner_user_id)
        REFERENCES tenant_users (tenant_id, user_id)
);
~~~

Ở đây, `id` chỉ cần duy nhất **trong một tenant**; do đó **khóa bản ghi đầy đủ** là `(tenant_id, id)`.

Giả sử có dữ liệu:

| tenant_id | id | owner_user_id | title |
| ---: | ---: | ---: | --- |
| 7 | 100 | 41 | Kế hoạch A |
| 7 | 101 | 42 | Báo cáo B |
| 8 | 100 | 51 | Hợp đồng C |
| 8 | 102 | 51 | Tài liệu D |

Hai tenant có thể cùng sở hữu một tài liệu `id = 100` **về mặt số ID**. Nếu truy vấn chỉ `WHERE id = 100`, có thể đọc cả hai bản ghi. Kể cả khi ID được sinh duy nhất toàn hệ thống, **vẫn phải kiểm tra tenant**: tính khó đoán của ID không phải là cơ chế phân quyền.

### Chính sách ví dụ

Để các câu SQL có ngữ nghĩa rõ ràng, giả sử chính sách sau đã được phê duyệt:

1. **MEMBER**: chỉ đọc, sửa và xóa tài liệu thuộc **tenant hiện tại** do **chính mình sở hữu**.
2. **TENANT_MANAGER**: được đọc và quản lý **mọi tài liệu trong tenant hiện tại**, không được vượt tenant.
3. Người chưa được xác thực, người không thuộc tenant, hoặc người thiếu vai trò hợp lệ: **không truy cập**.

Chính sách này dùng để dạy cách xây SQL. Trong ứng dụng thật, hãy thay bằng ma trận quyền đã được đội sản phẩm/bảo mật xác nhận. Đừng mặc định mọi ứng dụng đều cho người quản lý xem tất cả tài liệu.

## 3. Ngữ cảnh phân quyền phải được tạo từ phía server

Một lỗi thường gặp:

~~~java
// KHÔNG AN TOÀN: tenantId lấy trực tiếp từ tham số request.
long tenantId = Long.parseLong(request.getParameter("tenantId"));
repository.findByTenant(tenantId);
~~~

Nếu người dùng tenant 7 gửi `tenantId=8`, một câu SQL có `WHERE tenant_id = ?` vẫn sẽ truy vấn sai phạm vi.

Quy trình đúng:

~~~mermaid
flowchart LR
    A["Request + token/session"] --> B["Xác thực danh tính"]
    B --> C["Xác nhận tenant và vai trò thành viên"]
    C --> D["Tạo AccessScope tin cậy"]
    D --> E["Repository chọn SQL đã ràng buộc scope"]
    E --> F["PreparedStatement bind tham số"]
    F --> G["DBMS trả hàng trong phạm vi"]
~~~

Trách nhiệm của tầng xác thực/phân quyền:

- Xác minh token/session đúng chữ ký, hạn dùng, đối tượng phát hành và các ràng buộc cần thiết.
- Xác minh tài khoản còn được phép hoạt động và có quan hệ thành viên với tenant được chọn.
- Xác định vai trò từ nguồn đáng tin như quyền trong hệ thống hoặc claim đã kiểm chứng theo chính sách cập nhật quyền.
- Từ chối khi thiếu tenant, vai trò hoặc tư cách thành viên; **không mặc định dùng tenant đầu tiên hay truy vấn toàn cục**.
- Nếu có đổi tenant trong giao diện, phải xác minh quyền thuộc tenant đích trước khi tạo scope mới.

Một kiểu dữ liệu minh họa:

~~~java
import java.util.Objects;

enum TenantRole {
    MEMBER, TENANT_MANAGER
}

record AccessScope(
        long tenantId,
        long actorUserId,
        TenantRole role
) {
    AccessScope {
        if (tenantId <= 0 || actorUserId <= 0) {
            throw new IllegalArgumentException(
                "Tenant và actor phải hợp lệ"
            );
        }
        Objects.requireNonNull(role, "role");
    }

    boolean isManager() {
        return role == TenantRole.TENANT_MANAGER;
    }
}
~~~

**Lưu ý về ranh giới tin cậy:** Constructor kiểm tra số dương và `role != null` **chưa thể chứng minh người dùng thực sự có role đó**. `AccessScope` chỉ được tạo bởi thành phần đã xác thực và xác minh quyền; không để controller xây scope từ `tenantId`, `actorUserId` hay `role` do người dùng tự gửi.

Nếu tổ chức yêu cầu quyền thu hồi có hiệu lực ngay, một claim vai trò cũ trong token có thể chưa đủ. Cần chính sách kiểm tra phiên bản quyền, hạn sống token, hoặc kiểm tra lại quyền trong DB ở thời điểm phù hợp.

## 4. Điều kiện phân quyền là bắt buộc, bộ lọc giao diện là tùy chọn

Trong mỗi truy vấn, phân biệt:

- **Mandatory authorization predicate**: luôn phải có, được tạo từ `AccessScope` đã tin cậy.
- **Optional business predicate**: người dùng có thể chọn, nhưng chỉ **thu hẹp** tập hàng đã được phân quyền.

Ví dụ user 41 của tenant 7 muốn xem tài liệu có trạng thái `ACTIVE` hoặc `REVIEW`:

~~~sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?
  AND (d.status = ? OR d.status = ?)
ORDER BY d.id;
~~~

Không được viết:

~~~sql
-- SAI: nhánh OR thứ hai có thể bỏ qua tenant và owner.
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?
  AND d.status = ?
   OR d.status = ?;
~~~

Do `AND` có độ ưu tiên cao hơn `OR`, câu sai tương đương:

~~~sql
WHERE (
    d.tenant_id = ?
    AND d.owner_user_id = ?
    AND d.status = ?
) OR d.status = ?;
~~~

Vì vậy, **mọi hàng có trạng thái ở nhánh OR cuối** có thể xuất hiện bất kể tenant và owner.

### Nếu có nhiều điều kiện OR hợp lệ?

Bọc các điều kiện lựa chọn **bên trong một nhóm** sau predicate quyền:

~~~sql
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?
  AND (
      d.status = ?
      OR d.title LIKE ?
  );
~~~

Nếu nghiệp vụ có chính sách “owner hoặc người được chia sẻ”, đó cũng là một biểu thức `OR`, nhưng **mọi nhánh được cấp quyền phải nằm trong tenant chung** và dựa trên một quan hệ chia sẻ đã được kiểm chứng. Không thêm `OR 1 = 1` hoặc điều kiện tùy biến do request quyết định để “bỏ lọc nhanh”.

### Sai lầm với bộ lọc không có giá trị

~~~java
// Rủi ro: lọc quyền biến mất khi actorId null.
if (actorId != null) {
    sql.append(" AND owner_user_id = ?");
}
~~~

Nếu không tìm được actor, hành vi đúng là **từ chối truy cập** chứ không chạy query rộng hơn.

**Fail closed:** thiếu scope hoặc điều kiện quyền → thất bại rõ ràng, không phải “trả toàn bộ dữ liệu để người dùng đỡ gặp lỗi”.

## 5. Dùng `PreparedStatement` với SQL có phạm vi quyền rõ ràng

Một repository an toàn nên cung cấp các phương thức nghiệp vụ như `findVisibleById(scope, id)` thay vì cho gọi `findById(id)` rồi để người sử dụng nhớ thêm điều kiện quyền ở bên ngoài.

Ví dụ Java 17+ cho chính sách ở phần 2:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

record Document(
    long tenantId, long id, long ownerUserId,
    String title, String status, long version
) {}

public final class DocumentRepository {
    public Optional<Document> findVisibleById(
            Connection conn, AccessScope scope, long documentId
    ) throws SQLException {
        Objects.requireNonNull(conn, "conn");
        Objects.requireNonNull(scope, "scope");

        String sql = scope.isManager()
            ? """
              SELECT tenant_id, id, owner_user_id,
                     title, status, version
              FROM documents
              WHERE tenant_id = ? AND id = ?
              """
            : """
              SELECT tenant_id, id, owner_user_id,
                     title, status, version
              FROM documents
              WHERE tenant_id = ?
                AND id = ?
                AND owner_user_id = ?
              """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, scope.tenantId());
            ps.setLong(2, documentId);

            if (!scope.isManager()) {
                ps.setLong(3, scope.actorUserId());
            }

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                return Optional.of(new Document(
                    rs.getLong("tenant_id"),
                    rs.getLong("id"),
                    rs.getLong("owner_user_id"),
                    rs.getString("title"),
                    rs.getString("status"),
                    rs.getLong("version")
                ));
            }
        }
    }
}
~~~

### Vì sao hai mẫu SQL là hợp lý?

Câu SQL được chọn theo **vai trò đã xác minh**, không theo tham số yêu cầu tùy tiện. Cả hai đều luôn có `tenant_id = ?`; riêng MEMBER còn có `owner_user_id = ?`.

So với một điều kiện phức tạp chứa `OR` hoặc cờ `isAdmin`:

- Mỗi đường quyền có SQL dễ đọc và review.
- Khi thêm role mới, repository phải **thêm chính sách tường minh**, không mặc định bỏ lọc.
- Có thể đo và kiểm thử riêng từng truy vấn.
- Không đưa tên bảng/cột từ người dùng vào SQL.

**Quan trọng:** `scope.isManager()` đáng tin chỉ khi tầng xác thực đã kiểm chứng vai trò trong tenant. Việc tạo `AccessScope(..., TENANT_MANAGER)` từ dữ liệu client sẽ phá vỡ thiết kế này.

### Truy vấn không tìm thấy tài liệu nên trả gì?

Kết quả `Optional.empty()` có thể có ít nhất ba nguyên nhân: không có tài liệu ID đó, tài liệu ở tenant khác, hoặc user không đủ quyền. Ứng dụng thường tránh tiết lộ quá nhiều chi tiết để giảm khả năng dò tài nguyên; ví dụ trả một phản hồi “không tìm thấy hoặc không có quyền” theo chính sách API.

**Không chạy thêm câu `SELECT` bỏ điều kiện quyền chỉ để phân biệt 404/403** nếu người gọi không có quyền kiểm tra sự tồn tại của tài nguyên. Việc này có thể làm lộ rằng một bản ghi nhạy cảm tồn tại.

## 6. Quy tắc áp dụng cho mọi thao tác CRUD

Điều kiện phân quyền không chỉ dành cho `SELECT`. Nó phải gắn với **hàng được phép sửa hoặc xóa**.

| Thao tác | Điều kiện cần kiểm tra |
| --- | --- |
| `SELECT` một hàng | `tenant_id` + quyền xem theo owner/role/chia sẻ |
| `SELECT` danh sách | Scope ở `WHERE` **trước** `ORDER BY`/`LIMIT` |
| `COUNT/SUM/EXISTS` | Cùng phạm vi quyền như danh sách; không tiết lộ số lượng ngoài quyền |
| `INSERT` | Tenant/owner lấy từ scope tin cậy, kiểm tra quan hệ hợp lệ |
| `UPDATE` | Scope ở **chính câu UPDATE**; có thể thêm version để chống ghi đè |
| `DELETE` | Scope ở **chính câu DELETE**; chỉ xóa hàng được phép |
| `UPSERT` | Cả đường insert và conflict/update phải giữ tenant, khóa và quyền |
| `BATCH` | Mỗi lần bind phải giữ nguyên scope tin cậy; rollback theo chính sách |
| `JOIN/CTE` | Không đưa hàng ngoài quyền vào kết quả hay phép tính trung gian có thể quan sát |

### 6.1. `INSERT`: không tin `tenant_id` từ request

~~~java
static int insertOwned(
        Connection conn, AccessScope scope,
        long newId, String title
) throws SQLException {
    String sql = """
        INSERT INTO documents (
            tenant_id, id, owner_user_id,
            title, status, version
        )
        VALUES (?, ?, ?, ?, ?, 0)
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        // Cả tenant và owner đều lấy từ context đã xác thực.
        ps.setLong(1, scope.tenantId());
        ps.setLong(2, newId);
        ps.setLong(3, scope.actorUserId());
        ps.setString(4, title);
        ps.setString(5, "DRAFT");

        return ps.executeUpdate();
    }
}
~~~

Kiểm tra đầu vào như `newId > 0`, giới hạn độ dài `title` và các ràng buộc nghiệp vụ vẫn cần thiết. Khóa ngoại tổng hợp `(tenant_id, owner_user_id)` trong lược đồ minh họa giúp chặn tài liệu liên kết với thành viên **thuộc tenant khác**.

Khi chèn tài liệu thay mặt một người khác, chính sách phải cấp rõ quyền này (ví dụ TENANT_MANAGER với một owner hợp lệ trong tenant), không dùng chung hàm `insertOwned` rồi nhận `owner_user_id` tùy ý.

### 6.2. `UPDATE`: kiểm quyền trong chính câu SQL

**Không an toàn:**

~~~java
// Sai: kiểm tra riêng, rồi câu ghi chỉ còn lọc theo id.
if (canEditDocument(scope, documentId)) {
    executeUpdate("UPDATE documents SET title = ? WHERE id = ?");
}
~~~

Giữa bước kiểm tra và ghi, quyền hoặc trạng thái tài nguyên có thể thay đổi (*time-of-check/time-of-use race*); câu ghi còn có thể sửa tài liệu cùng `id` của tenant khác.

**Mẫu tốt hơn đối với MEMBER là owner:**

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static boolean renameIfOwnedAndUnchanged(
        Connection conn, AccessScope scope,
        long documentId, long expectedVersion, String newTitle
) throws SQLException {
    String sql = """
        UPDATE documents
        SET title = ?, version = version + 1
        WHERE tenant_id = ?
          AND id = ?
          AND owner_user_id = ?
          AND version = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, newTitle);
        ps.setLong(2, scope.tenantId());
        ps.setLong(3, documentId);
        ps.setLong(4, scope.actorUserId());
        ps.setLong(5, expectedVersion);

        return ps.executeUpdate() == 1;
    }
}
~~~

Ý nghĩa:

- `tenant_id` ngăn ghi vượt tổ chức.
- `owner_user_id` ràng buộc quyền chủ sở hữu theo chính sách ví dụ.
- `version` là điều kiện **optimistic locking**, tránh ghi đè bản sửa mới hơn.
- `executeUpdate() == 0` có thể là không tồn tại, không có quyền hoặc xung đột version; không tiết lộ nguyên nhân nếu API không được phép.
- Không tự retry với `expectedVersion` cũ. Cần tải lại/giải quyết xung đột theo nghiệp vụ.

Đối với TENANT_MANAGER được phép sửa mọi tài liệu trong tenant, dùng **đường ghi riêng có kiểm chứng role** và vẫn giữ `tenant_id = ?` trong `UPDATE`. Không xóa owner predicate trong hàm MEMBER chỉ vì request gửi `isManager=true`.

### 6.3. `DELETE`: không làm rộng phạm vi

~~~java
static boolean deleteOwned(
        Connection conn, AccessScope scope, long documentId
) throws SQLException {
    String sql = """
        DELETE FROM documents
        WHERE tenant_id = ?
          AND id = ?
          AND owner_user_id = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, scope.tenantId());
        ps.setLong(2, documentId);
        ps.setLong(3, scope.actorUserId());
        return ps.executeUpdate() == 1;
    }
}
~~~

Nếu bảng có quan hệ `ON DELETE CASCADE`, xóa một hàng có thể xóa thêm các hàng phụ thuộc. Hãy thiết kế khóa ngoại **cùng tenant**, kiểm tra số lượng ảnh hưởng và yêu cầu quyền xóa những tài nguyên liên quan theo chính sách.

## 7. `JOIN` và khóa ngoại: tránh ghép dữ liệu xuyên tenant

Trong hệ nhiều tenant, lọc bảng chính là cần thiết nhưng **không luôn đủ** nếu một `JOIN` ghép sai dữ liệu phụ từ tenant khác.

Giả sử có bảng:

~~~sql
CREATE TABLE document_tags (
    tenant_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, document_id, tag_id),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES documents (tenant_id, id)
);
~~~

Truy vấn phù hợp cho MEMBER:

~~~sql
SELECT d.id, d.title, t.tag_id
FROM documents AS d
JOIN document_tags AS t
  ON t.tenant_id = d.tenant_id
 AND t.document_id = d.id
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?
  AND t.tag_id = ?
ORDER BY d.id;
~~~

Trong đó:

1. `WHERE d.tenant_id = ?` xác định tenant của người dùng.
2. `WHERE d.owner_user_id = ?` giới hạn tài liệu thuộc owner theo chính sách.
3. `ON t.tenant_id = d.tenant_id` ràng buộc dữ liệu tag của **cùng tenant**.
4. Khóa ngoại tổng hợp đảm bảo dữ liệu liên kết không trỏ sang tài liệu của tenant khác, độc lập với việc ứng dụng có viết đúng JOIN hay không.

**Sai lầm cần tránh:**

~~~sql
-- Sai khi document_id chỉ duy nhất bên trong từng tenant:
SELECT d.id, t.tag_id
FROM documents d
JOIN document_tags t ON t.document_id = d.id
WHERE d.tenant_id = ?;
~~~

Câu này có thể ghép tag của tenant khác khi hai tenant cùng có `document_id = 100`.

### `LEFT JOIN`: điều kiện đặt sai vị trí có thể đổi ý nghĩa

Khi muốn lấy tài liệu kể cả khi chưa có tag, điều kiện của bảng `t` nên ở `ON`:

~~~sql
SELECT d.id, d.title, t.tag_id
FROM documents d
LEFT JOIN document_tags t
  ON t.tenant_id = d.tenant_id
 AND t.document_id = d.id
 AND t.tag_id = ?
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?;
~~~

Đưa `t.tag_id = ?` vào `WHERE` có thể biến kết quả gần với inner join, làm mất những hàng chưa có tag. Đây là lỗi về ngữ nghĩa truy vấn; đồng thời cần đảm bảo điều kiện quyền trên bảng chính vẫn luôn được áp dụng.

### `EXISTS`, `CTE` và `UNION`

Với `EXISTS`, subquery nên liên kết bằng **đủ khóa tenant và tài liệu**:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = ?
  AND d.owner_user_id = ?
  AND EXISTS (
      SELECT 1
      FROM document_tags t
      WHERE t.tenant_id = d.tenant_id
        AND t.document_id = d.id
        AND t.tag_id = ?
  );
~~~

Với `UNION ALL`, mỗi nhánh trả dữ liệu nhạy cảm phải được xem xét quyền **riêng**; một nhánh có lọc tenant không tự bảo vệ nhánh còn lại.

Không giả định việc “lọc ở ngoài” một truy vấn phức tạp luôn an toàn khi trong các subquery đã có tổng hợp, đếm, sắp xếp hoặc giới hạn dựa trên dữ liệu ngoài quyền. Hãy kiểm tra **ngữ nghĩa kết quả quan sát được**, không chỉ rà soát chuỗi SQL một cách máy móc.

## 8. Phân trang và tổng hợp phải dùng cùng phạm vi quyền

Một sai lầm phổ biến là phân trang hoặc đếm trước khi lọc quyền ở tầng Java:

~~~java
// KHÔNG AN TOÀN VÀ SAI NGỮ NGHĨA:
List<Document> page = queryAny100Documents();
page.removeIf(d -> !canView(scope, d));
~~~

Hậu quả:

- Dữ liệu ngoài quyền đã được truyền từ DB đến bộ nhớ ứng dụng, có thể bị log, cache hoặc xuất hiện ở đường xử lý khác.
- Trang có thể chỉ còn vài hàng, dù trong DB còn nhiều hàng hợp lệ.
- `totalCount`, thống kê hoặc thông báo “còn X bản ghi” có thể làm lộ dữ liệu người dùng không được xem.
- Không xử lý hiệu quả trên tập dữ liệu lớn.

**Đúng:** đưa quyền vào câu SQL **trước** `ORDER BY`, `LIMIT` và `OFFSET`:

~~~sql
-- Ví dụ dành cho MEMBER trên PostgreSQL/MySQL:
SELECT id, title, status
FROM documents
WHERE tenant_id = ?
  AND owner_user_id = ?
  AND id > ?
ORDER BY id
LIMIT ?;
~~~

`id > ?` là cursor keyset; `LIMIT ?` là cú pháp hỗ trợ bởi PostgreSQL và MySQL, không phải portable cho mọi DBMS. Với DBMS khác có thể dùng `FETCH FIRST` hoặc chức năng phân trang tương đương.

Cùng chính sách cho tổng đếm:

~~~sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = ?
  AND owner_user_id = ?;
~~~

Và tổng hợp:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM documents
WHERE tenant_id = ?
  AND owner_user_id = ?
GROUP BY status;
~~~

**Lưu ý:** Nếu có truy vấn tìm kiếm trả danh sách tài liệu với bộ lọc `status` hoặc `title`, `COUNT(*)` dùng để hiển thị “tổng kết quả” phải có **cùng điều kiện quyền và cùng bộ lọc nghiệp vụ**. Đừng chỉ thêm quyền vào truy vấn danh sách.

### Kỹ thuật không làm mất điều kiện bắt buộc

Trong một repository, có thể xây các phương thức **theo mục đích**:

- `listVisibleForMember(scope, filters, cursor)`
- `listVisibleForManager(scope, filters, cursor)`
- `countVisible(scope, filters)`
- `existsVisibleById(scope, id)`
- `updateOwned(scope, ...)`

Mỗi phương thức chứa SQL đã kiểm chứng, có test. Không cung cấp `searchAllDocuments(String arbitraryWhereClause)` cho tầng controller rồi mong mọi người nhớ tự thêm `tenant_id`.

## 9. SQL động: chỉ tham số hóa giá trị, whitelist cấu trúc

Một phần SQL được tạo động thường là bộ lọc, sắp xếp hoặc chọn trường. `PreparedStatement` giúp an toàn cho **giá trị**, nhưng không dùng placeholder làm tên bảng, tên cột hay từ khóa SQL.

Ví dụ:

~~~sql
-- KHÔNG đúng ý nghĩa: placeholder không thay tên cột.
SELECT id, title
FROM documents
WHERE tenant_id = ?
ORDER BY ?;
~~~

Phần `ORDER BY ?` thường chỉ đại diện cho một **giá trị biểu thức hằng**, không phải tên cột người dùng muốn sắp xếp.

Cách phù hợp là **chọn cấu trúc từ tập cố định do ứng dụng định nghĩa**, còn giá trị vẫn bind:

~~~java
static String sortClause(String requestedSort) {
    return switch (requestedSort) {
        case "id_asc" -> " ORDER BY id ASC";
        case "id_desc" -> " ORDER BY id DESC";
        case "title_asc" -> " ORDER BY title ASC, id ASC";
        default -> throw new IllegalArgumentException(
            "Sort không được hỗ trợ"
        );
    };
}
~~~

Áp dụng vào câu nền **đã có điều kiện quyền**:

~~~java
String sql = """
    SELECT id, title, status
    FROM documents
    WHERE tenant_id = ?
      AND owner_user_id = ?
    """ + sortClause(requestedSort);
~~~

Không dùng `requestedSort` nối trực tiếp vào SQL. Khi có các điều kiện tùy chọn, hãy ghép dưới dạng **`AND (...)`**, vẫn giữ đoạn điều kiện quyền bắt buộc không thể bị bỏ qua.

### Hạn chế của “gắn chuỗi WHERE vào mọi nơi”

Một helper như `appendTenantPredicate(sql)` có thể bị sai khi SQL chứa `GROUP BY`, `UNION`, `WITH`, subquery, điều kiện `OR` hoặc comment. Không nên thiết kế bảo mật dựa vào việc chỉnh chuỗi SQL tự do bằng regex.

Các lựa chọn an toàn hơn:

1. Repository trả các **truy vấn có scope cố định** theo use case.
2. Query builder có AST hoặc cấu trúc điều kiện tường minh, với predicate quyền **bắt buộc** theo type/interface.
3. Chính sách trên DBMS như RLS làm lớp bảo vệ phụ, đặc biệt khi có nhiều đường SQL phức tạp.

Đừng nhầm một test tìm chuỗi `"tenant_id"` trong SQL với bằng chứng phân quyền đúng. Câu `tenant_id = ? OR 1 = 1` vẫn chứa chữ đó nhưng bỏ qua phạm vi.

## 10. Transaction và batch: mọi bước vẫn phải nằm trong phạm vi

Khi một quy trình nghiệp vụ gồm nhiều câu SQL, từng câu cần được xem xét quyền. Một câu `SELECT` đúng không cứu được câu `UPDATE` sau đó thiếu điều kiện.

Ví dụ quy trình đổi trạng thái nhiều tài liệu trong tenant:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

static void markOwnedReviewed(
        Connection conn,
        AccessScope scope,
        List<Long> ids
) throws SQLException {
    String sql = """
        UPDATE documents
        SET status = 'REVIEWED', version = version + 1
        WHERE tenant_id = ?
          AND id = ?
          AND owner_user_id = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        for (long id : ids) {
            ps.setLong(1, scope.tenantId());
            ps.setLong(2, id);
            ps.setLong(3, scope.actorUserId());
            ps.addBatch();
        }

        int[] counts = ps.executeBatch();
        if (counts.length != ids.size()) {
            throw new SQLException("Kết quả batch không đủ");
        }

        for (int count : counts) {
            if (count == Statement.SUCCESS_NO_INFO) {
                // Chỉ biết lệnh được báo thành công.
                // Nếu nghiệp vụ đòi đúng 1 hàng, cần xác minh thêm.
                throw new SQLException(
                    "Không kiểm chứng được số hàng cập nhật"
                );
            }
            if (count != 1) {
                throw new SQLException(
                    "Có tài liệu không tồn tại hoặc không đủ quyền"
                );
            }
        }
    }
}
~~~

**Hàm này không tự commit**: tầng service phải sở hữu `Connection`, bật `autoCommit = false`, gọi các bước cần thiết và `commit()` khi toàn bộ thành công; khi có lỗi phải `rollback()`, đồng thời xử lý lỗi rollback/commit không rõ kết quả.

Phần `ids` là dữ liệu đầu vào cần giới hạn số lượng và xác thực về định dạng. Trong mỗi lần bind, `tenant_id` và `actorUserId` vẫn lấy từ `AccessScope`, không lấy theo từng item của request. `PreparedStatement` tránh SQL injection, còn `WHERE` quyết định những hàng có quyền sửa.

**Không nên coi count `0` là một lỗi kỹ thuật có thể retry vô hạn.** Nó có thể là yêu cầu sửa hàng ngoài quyền hoặc tài liệu không tồn tại. Nếu nghiệp vụ muốn sửa toàn bộ theo chính sách “all-or-nothing”, đây là lý do rollback cả transaction.

## 11. Row-Level Security (RLS): lớp bảo vệ dưới ứng dụng

Khi DBMS hỗ trợ **Row-Level Security**, chính sách lọc hàng có thể được thực thi tại phía database. Đây là một lớp **defense in depth** rất hữu ích nếu một developer quên `WHERE tenant_id = ?` trong một câu query.

Phần này dùng **PostgreSQL** để minh họa; cú pháp RLS và khả năng hỗ trợ **không portable** sang mọi DBMS.

### 11.1. Chính sách cô lập tenant

Giả sử tài khoản DB mà ứng dụng sử dụng là role `app_runtime`, **không phải superuser, không có BYPASSRLS và không sở hữu bảng**.

~~~sql
-- Thực hiện bằng tài khoản quản trị/migration có quyền phù hợp.
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_guard
ON documents
FOR ALL
TO app_runtime
USING (
    tenant_id =
      NULLIF(current_setting('app.tenant_id', true), '')::BIGINT
)
WITH CHECK (
    tenant_id =
      NULLIF(current_setting('app.tenant_id', true), '')::BIGINT
);

-- Tùy chiến lược quản lý owner, có thể cân nhắc:
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE
ON documents TO app_runtime;
~~~

Đây là **một policy cấp tenant**, không phải đầy đủ chính sách owner/role ở phần 2. Ứng dụng vẫn phải kiểm tra quyền của MEMBER hoặc TENANT_MANAGER; nếu muốn DBMS cũng thực thi ràng buộc owner, cần thiết kế thêm policy/role phù hợp và kiểm chứng cấu trúc kết hợp policy.

**Cẩn thận với PostgreSQL:** Nhiều policy *permissive* thường được kết hợp bằng **OR**, không phải AND. Một policy cho phép rộng vô tình có thể làm mất tính hạn chế của policy khác. Nếu có nhiều policy, cần hiểu sự kết hợp permissive/restrictive, phép `USING`/`WITH CHECK`, quyền của role và test từng thao tác. Không giả định “có một policy tenant” đồng nghĩa chắc chắn mọi policy khác cũng bắt buộc tenant.

### 11.2. Nếu thiếu tenant, phải đóng quyền

Hàm:

~~~sql
current_setting('app.tenant_id', true)
~~~

trả giá trị cài đặt theo transaction/session nếu có, và trả `NULL` khi không có thiết lập tương ứng. Trong biểu thức chính sách, `tenant_id = NULL` không thành `TRUE`, vì vậy **không cho hàng nào đi qua**. `NULLIF(..., '')::BIGINT` cũng xử lý chuỗi rỗng thành `NULL`; giá trị không thể chuyển thành số sẽ gây lỗi thay vì tự biến thành truy vấn toàn cục.

Điều này chỉ có tác dụng nếu DB role thực thi truy vấn **thực sự chịu RLS**, policy có hiệu lực và không có đường bypass. Superuser, role có `BYPASSRLS` hoặc table owner trong một số cấu hình có thể bỏ qua RLS. `FORCE ROW LEVEL SECURITY` giúp áp dụng với table owner nhưng không thay thế quy tắc về superuser/BYPASSRLS.

### 11.3. Gắn tenant vào **transaction hiện tại**, không làm rò sang connection khác

Trong PostgreSQL có thể đặt cài đặt transaction-local bằng `set_config(..., true)`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static void setPostgresTenantForTransaction(
        Connection conn, AccessScope scope
) throws SQLException {
    if (conn.getAutoCommit()) {
        throw new SQLException(
            "Cần manual transaction để đặt tenant transaction-local"
        );
    }

    String sql = "SELECT set_config('app.tenant_id', ?, true)";
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, Long.toString(scope.tenantId()));

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "Không thể thiết lập tenant context"
                );
            }
        }
    }
}
~~~

Tầng service dùng:

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        setPostgresTenantForTransaction(conn, scope);

        // Các câu SQL tiếp theo trên CHÍNH connection/transaction này.
        runScopedBusinessOperation(conn, scope);

        conn.commit();

    } catch (SQLException | RuntimeException failure) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
        throw failure;
    }
}
~~~

Ở ví dụ này, `runScopedBusinessOperation` chỉ là hàm minh họa. Code production cần xử lý việc trả `autoCommit` về trạng thái ban đầu sau khi transaction kết thúc an toàn và chính sách loại connection không đáng tin khi rollback thất bại.

**Vì sao `true` trong `set_config` quan trọng?** Đó là tham số `is_local` của PostgreSQL: cài đặt gắn với transaction hiện tại thay vì vô tình tồn tại qua các lượt dùng cùng connection trong pool. Không dùng session variable lâu dài mà không có cơ chế reset đáng tin cậy.

**RLS không thay thế xác thực:** nếu ứng dụng cho phép client điều khiển trực tiếp `app.tenant_id` hoặc chạy SQL tùy ý trên role `app_runtime`, người dùng vẫn có thể lạm dụng session context. Chỉ tầng server đã xác minh tenant mới được gọi hàm gắn scope; áp dụng least privilege và tham số hóa.

### 11.4. Kiểm thử RLS bằng role giống production

Đừng test RLS bằng tài khoản migration/superuser rồi kết luận dữ liệu được cô lập. Kiểm thử bằng **role thực sự dùng trong production**:

1. Không đặt `app.tenant_id` → câu `SELECT` trên bảng có RLS phải không thấy hàng.
2. Đặt tenant 7 → chỉ thấy tài liệu tenant 7.
3. Cố `INSERT` hoặc `UPDATE` làm hàng thuộc tenant 8 → phải bị chặn bởi policy/constraint.
4. Chuyển connection qua các transaction tenant 7 rồi tenant 8 → không được rò scope từ transaction trước.
5. Xác minh các view, function `SECURITY DEFINER`, stored procedure và quyền owner có thể làm thay đổi ngữ nghĩa RLS. Phải xem xét riêng trước khi cho role ứng dụng gọi.

Nếu table này có foreign key, trigger hoặc function đặc quyền, cần đánh giá đường thực thi dữ liệu liên quan; RLS không tự bảo đảm mọi function hoặc side effect ngoài bảng đều có chính sách quyền giống nhau.

## 12. Bảo mật không nên phụ thuộc vào mỗi cơ chế duy nhất

Một thiết kế nhiều lớp thường gồm:

~~~mermaid
flowchart TD
    A["Người dùng đã xác thực"] --> B{"Có quyền vào tenant?"}
    B -- "Không" --> X["Từ chối"]
    B -- "Có" --> C["AccessScope tin cậy"]
    C --> D["Repository có predicate tenant/owner"]
    D --> E["PreparedStatement tham số hóa"]
    E --> F["DB role tối thiểu + RLS nếu có"]
    F --> G["Constraint PK/FK cùng tenant"]
    G --> H["Transaction + kiểm tra số hàng cập nhật"]
    H --> I["Chỉ trả dữ liệu được phép"]
~~~

Mỗi tầng xử lý một nhóm rủi ro:

| Tầng | Mục đích |
| --- | --- |
| Authentication/tenant membership | Ngăn người chưa có quyền tạo scope |
| Repository scoped SQL | Không bỏ lọc quyền trong từng câu SELECT/CRUD |
| `PreparedStatement` | Ngăn dữ liệu đầu vào trở thành cú pháp SQL |
| DB runtime role ít đặc quyền | Giảm ảnh hưởng nếu một câu truy vấn sai hoặc bị lạm dụng |
| Row-Level Security | Bảo vệ cấp hàng phía DBMS, khi được cấu hình đúng |
| PK/FK tổng hợp | Ngăn liên kết dữ liệu xuyên tenant do sai logic |
| Optimistic locking/transaction | Giảm ghi đè và giữ nhất quán nghiệp vụ |
| Test + review + observability | Phát hiện đường truy cập mới làm mất phạm vi |

RLS hữu ích nhưng không phải lý do để bỏ `WHERE` tenant trong toàn bộ code: điều kiện vẫn giúp **thể hiện rõ hợp đồng quyền**, hỗ trợ hiệu năng/index và cho phép code có chính sách owner/role chi tiết. Đồng thời, chỉ dựa vào code ứng dụng mà không có ràng buộc DB làm tăng hậu quả của một lỗi query bị bỏ sót.

## 13. Kiểm thử phân quyền: phải kiểm tra cả trường hợp bị từ chối

Một bộ test tốt phải tạo **ít nhất hai tenant và hai user trong một tenant**, với các ID cố ý trùng nhau hoặc dễ đoán:

~~~text
Tenant 7:
  user 41 MEMBER
  user 42 MEMBER
  user 43 TENANT_MANAGER
  documents: (id=100, owner=41), (id=101, owner=42)

Tenant 8:
  user 51 MEMBER
  documents: (id=100, owner=51), (id=102, owner=51)
~~~

### Ma trận test tối thiểu

| Người gọi | Thao tác | Mong muốn |
| --- | --- | --- |
| Tenant 7, user 41 MEMBER | Đọc tài liệu (7,100), owner 41 | Thành công |
| Tenant 7, user 41 MEMBER | Đọc tài liệu (7,101), owner 42 | Không thấy |
| Tenant 7, user 41 MEMBER | Đọc tài liệu (8,100), owner 51 | Không thấy |
| Tenant 7, user 43 TENANT_MANAGER | Đọc tài liệu (7,101) | Thành công theo policy |
| Tenant 7, user 43 TENANT_MANAGER | Đọc tài liệu (8,102) | Không thấy |
| Tenant 7, user 41 MEMBER | Update/Delete (7,101) | 0 hàng, không sửa dữ liệu |
| Tenant 7, user 41 MEMBER | Update/Delete (8,100) | 0 hàng, không sửa dữ liệu |
| Request không có scope hợp lệ | Mọi thao tác đọc/ghi | Từ chối |
| Tenant 7, user 41 MEMBER | Count và list tài liệu | Chỉ tính những hàng của user 41 |
| Request cố đặt `isManager=true` | Mọi thao tác | Không tăng quyền |
| RLS runtime role, không tenant context | `SELECT` trên `documents` | 0 hàng |
| Dùng lại pooled connection từ tenant 7 sang 8 | Đọc dữ liệu tenant 8 | Không rò hàng tenant 7 |

### Những kiểu test cần có

**1. Kiểm thử API/repository tích hợp.** Chạy với DBMS/driver thật của hệ thống, dùng đúng SQL đã triển khai. Hãy kiểm tra cả dữ liệu **không trả về**, không chỉ kiểm tra dữ liệu hợp lệ trả về.

**2. Kiểm thử mutation.** Sau một `UPDATE` hoặc `DELETE` không được phép, dùng kết nối/role test có thẩm quyền kiểm tra bản ghi gốc **không thay đổi**. Không chỉ dựa vào HTTP status.

**3. Kiểm thử input xấu.** Tenant khác, ID trùng qua tenant, ID không tồn tại, role giả, bộ lọc `OR`, trường sort không hợp lệ, danh sách batch chứa ID ngoài quyền.

**4. Kiểm thử luồng gián tiếp.** Export CSV, báo cáo thống kê, search/autocomplete, endpoint đếm số lượng, background job, stored procedure và API download file cũng phải áp dụng policy.

**5. Kiểm thử connection pool/RLS.** Tái sử dụng connection qua hai tenant trong hai transaction, rollback/timeout/exception và xác minh session context không bị giữ lại.

### Không chỉ kiểm tra rằng SQL “có chữ tenant_id”

Một test như:

~~~text
assertTrue(sql.contains("tenant_id"))
~~~

không đủ. Nó không phát hiện biểu thức `OR 1=1`, thiếu điều kiện owner, JOIN sai hoặc một nhánh `UNION` không giới hạn quyền.

Mục tiêu là **test hành vi**: từ người dùng tenant 7, không cách nào đọc/sửa được dữ liệu tenant 8 qua những đường truy vấn đã cung cấp.

## 14. Quan sát và vận hành: tìm lỗi thiếu scope trước khi xảy ra sự cố

Trong code review và khi chạy production, nên kiểm tra:

- Phương thức truy vấn tài liệu có **bắt buộc nhận `AccessScope`** hay không.
- Có đường `findAll()`/`deleteById()`/`countAll()` dùng được từ API người dùng mà không có scope không.
- Những query dùng SQL động, join, view, báo cáo, batch hoặc stored procedure có được kiểm tra chính sách riêng không.
- Có biến `tenantId` hoặc `isAdmin` lấy thẳng từ request mà chưa xác minh không.
- Có code lọc quyền **sau** khi đã phân trang/đếm/trả dữ liệu không.
- Có xử lý `executeUpdate() == 0` như xung đột/không có quyền, thay vì tự thử update thiếu điều kiện không.
- Kết nối DB dùng role ít quyền; RLS policy/test có chạy dưới cùng role không.
- Có cơ chế ghi audit cho thao tác quản trị vượt quyền owner hay không, và log có tránh lộ dữ liệu nhạy cảm không.

### Log đúng mà không tự tiết lộ dữ liệu

Có thể ghi tên thao tác, ID yêu cầu, vai trò đã xác thực, tenant identifier đã được phân loại nhạy cảm đúng mức, số hàng ảnh hưởng, mã lỗi và kết quả quyền. Tránh log toàn bộ nội dung tài liệu, token hoặc SQL có giá trị nhạy cảm.

**Cần thận trọng với `404`/`403`:** trong một số API, việc trả khác nhau giữa “không tồn tại” và “không có quyền” có thể tiết lộ sự tồn tại của tài nguyên. Chính sách phản hồi nên được thiết kế có chủ đích và thống nhất giữa read/update/delete.

### Hiệu năng của predicate quyền

Điều kiện phân quyền là yêu cầu bắt buộc, không phải phần tùy chọn để tối ưu:

~~~sql
-- Khóa tổng hợp đã hỗ trợ tra cứu theo tenant và id:
PRIMARY KEY (tenant_id, id);

-- Có thể bổ sung chỉ mục phù hợp với workload của MEMBER:
CREATE INDEX idx_documents_tenant_owner_id
ON documents (tenant_id, owner_user_id, id);
~~~

Đánh giá chỉ mục với query plan thực tế; không tự thêm hàng chục index không cần thiết. Nếu có câu truy vấn chậm, hãy tối ưu index, thứ tự lọc, batch size hoặc phân trang, **không bỏ `tenant_id`/owner predicate** để “chạy nhanh hơn”.

## 15. Bài tập tình huống

**Tình huống A.** Một controller truyền `documentId` vào câu `SELECT ... WHERE id = ?`. Câu SQL dùng `PreparedStatement`. Đã đủ an toàn chưa?

**Đáp án:** Chưa. Tham số hóa chống injection nhưng không quyết định người gọi có quyền xem hàng đó không. Cần `tenant_id` và điều kiện owner/role phù hợp.

**Tình huống B.** User 41 của tenant 7 gửi `tenantId=8` qua query string. Repository vẫn dùng `WHERE tenant_id = ?`. Có thể truy cập dữ liệu tenant 8 không?

**Đáp án:** Có nguy cơ nếu server bind tenant lấy trực tiếp từ request. `tenantId` phải được xác nhận người dùng có quyền hoặc lấy từ ngữ cảnh tenant đã kiểm chứng.

**Tình huống C.** Câu SQL có `WHERE tenant_id = ? AND owner_user_id = ? AND status = ? OR status = ?`. Lỗi gì?

**Đáp án:** Do ưu tiên `AND` trước `OR`, nhánh status cuối không còn ràng buộc tenant/owner. Cần `AND (status = ? OR status = ?)`.

**Tình huống D.** Ứng dụng kiểm tra `canEdit(id)` trả true, sau đó chạy `UPDATE documents SET title=? WHERE id=?`. Vì sao vẫn nguy hiểm?

**Đáp án:** Câu UPDATE thiếu điều kiện quyền và tenant; có thể ghi nhầm hàng cùng ID hoặc gặp race khi quyền/dữ liệu đổi giữa check và update. Đặt predicate ngay trong UPDATE và dùng version khi cần.

**Tình huống E.** Tenant 7 và tenant 8 đều có `document_id = 100`. JOIN `ON t.document_id = d.id` có thể gặp lỗi gì?

**Đáp án:** Có thể ghép tag của tenant khác. JOIN đủ khóa `tenant_id` và `document_id`, đồng thời dùng khóa ngoại tổng hợp.

**Tình huống F.** Truy vấn danh sách đã lọc owner, nhưng `SELECT COUNT(*) FROM documents WHERE tenant_id=?` dùng cho tổng kết quả thì sao?

**Đáp án:** Count có thể tiết lộ số tài liệu của các owner khác trong tenant. Phải áp cùng điều kiện quyền và bộ lọc nghiệp vụ với danh sách.

**Tình huống G.** Trong một batch, 9 lệnh update trả 1 hàng, lệnh thứ 10 trả 0. Yêu cầu nghiệp vụ là tất cả hoặc không có gì. Có nên commit 9 lệnh đầu?

**Đáp án:** Không. Vì một lệnh không thỏa hậu điều kiện quyền/tồn tại, nên rollback toàn transaction và báo kết quả phù hợp. Không bỏ điều kiện scope để “cứu” lệnh thứ 10.

**Tình huống H.** RLS PostgreSQL bật nhưng ứng dụng dùng superuser để chạy SQL. Có thể coi tenant đã được bảo vệ chắc chắn không?

**Đáp án:** Không. Superuser có thể bypass RLS. Phải dùng runtime role ít quyền, kiểm tra `BYPASSRLS`/ownership và test bằng role giống production.

**Tình huống I.** Có hai policy PostgreSQL permissive: một tenant scope và một policy khác cho phép tất cả tài liệu `status='PUBLIC'`. Có nguy cơ gì?

**Đáp án:** Policies permissive có thể kết hợp bằng OR, khiến tài liệu PUBLIC của tenant khác lọt qua dù đã có tenant policy. Cần thiết kế policy kết hợp đúng (ví dụ restrictive tenant guard khi có nhiều policy) và test cross-tenant.

**Tình huống J.** Sau lỗi transaction, pooled connection được dùng cho tenant khác nhưng biến session `app.tenant_id` vẫn giữ giá trị tenant cũ. Điều gì có thể xảy ra?

**Đáp án:** Dữ liệu có thể bị lọc theo tenant sai hoặc rò quyền nếu cơ chế RLS dựa vào session variable. Dùng transaction-local setting, rollback/cleanup đúng và kiểm thử tái sử dụng pool.

**Tình huống K.** Member có quyền xem tài liệu của mình, nhưng yêu cầu search có `sortBy` là chuỗi do client gửi. Có thể viết `ORDER BY ` + sortBy không?

**Đáp án:** Không. Placeholder không thay identifier và nối SQL tùy ý có thể gây injection. Chọn tên cột/order từ whitelist cố định; giá trị lọc vẫn bind bằng PreparedStatement.

**Tình huống L.** Một endpoint chỉ trả tổng doanh thu, không trả tài liệu cá nhân. Có cần scope quyền trong `SUM` không?

**Đáp án:** Có. Tổng số cũng là thông tin quan sát được và có thể tiết lộ dữ liệu ngoài phạm vi. Cần điều kiện tenant/role/owner đúng chính sách.

## Ghi nhớ

- **Phân quyền phải ở ngay câu SQL chạm tới dữ liệu**: mọi `SELECT`, `COUNT`, `SUM`, `EXISTS`, `UPDATE`, `DELETE`, `INSERT` và batch đều cần chính sách phù hợp.
- **`PreparedStatement` chống SQL injection cho giá trị nhưng không tự kiểm tra quyền**. Scope phải đến từ context xác thực/đã xác minh thành viên và vai trò phía server.
- **Predicate quyền là bắt buộc, bộ lọc nghiệp vụ chỉ được thu hẹp kết quả**. Chú ý ngoặc với `OR`, mọi nhánh `UNION`, `JOIN` đủ khóa tenant và phân trang sau khi lọc quyền.
- **Fail closed**: không có actor/tenant/role hợp lệ thì từ chối; không bỏ predicate để hệ thống “vẫn hoạt động”.
- **Điều kiện quyền nằm trong UPDATE/DELETE**, kết hợp version khi cần; số hàng cập nhật bằng 0 không phải lý do chạy lại SQL rộng hơn.
- **PostgreSQL RLS là lớp defense in depth**, cần runtime role ít quyền, hiểu policy permissive/restrictive và đặt tenant transaction-local khi dùng connection pool.
- **Kiểm thử hành vi vượt quyền với ít nhất hai tenant**, cả đọc, đếm, ghi, batch, join và tái sử dụng connection. Không chỉ kiểm tra chuỗi SQL có chứa `tenant_id`.
