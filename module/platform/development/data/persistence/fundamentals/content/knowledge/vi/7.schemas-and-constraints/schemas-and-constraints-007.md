# Vì sao kiểm tra trước khi ghi không thay thế ràng buộc duy nhất

Trong chương **Lược đồ và ràng buộc** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một lỗi thiết kế rất phổ biến là: ứng dụng Java chạy `SELECT` để kiểm tra một giá trị chưa tồn tại, rồi mới `INSERT` và tin rằng giá trị sẽ không bao giờ bị trùng. Cách làm ấy có vẻ đúng trong thử nghiệm tuần tự, nhưng có thể thất bại khi nhiều yêu cầu được xử lý đồng thời, khi hệ thống dùng nhiều instance hoặc khi dữ liệu được ghi qua batch job và công cụ quản trị.

**Kiểm tra trước khi ghi (check-before-write)** hữu ích để hiển thị cảnh báo sớm, nhưng **ràng buộc duy nhất (UNIQUE constraint/unique index) ở nơi ghi có thẩm quyền** mới là tuyến bảo vệ chính cho bất biến “không được tồn tại hai bản ghi có cùng khóa nghiệp vụ trong phạm vi đã xác định”.

Bài học kết nối việc chọn khóa, định nghĩa lược đồ, truy vấn và chỉ mục với ACID, isolation, kiểm soát đồng thời, repository Java/JDBC, retry, tiến hóa schema, bảo mật và phục hồi dữ liệu.

**Sau bài học, người học có thể:**

- Giải thích chính xác lỗi *time-of-check to time-of-use* (TOCTOU) khi hai request cùng kiểm tra rồi cùng ghi.
- Chọn **phạm vi duy nhất** theo nghiệp vụ: toàn hệ thống, trong tenant, theo trạng thái hoặc trong một tổ hợp trường.
- Dùng `UNIQUE`, unique index và `INSERT ... ON CONFLICT` để thực thi bất biến tại database.
- Phân biệt xung đột uniqueness, lỗi kết nối lúc commit, idempotency và lỗi cập nhật đồng thời.
- Thiết kế kiểm thử nhiều giao dịch, migration và observability để chứng minh ràng buộc hoạt động khi tải cao.

## 1. Một trường hợp tưởng đúng nhưng không an toàn

Ứng dụng cho phép mỗi tenant đăng ký **tối đa một tài khoản cho mỗi email đã chuẩn hóa**. Developer viết logic:

~~~java
// Mã minh họa lỗi; KHÔNG dùng làm cơ chế bảo vệ uniqueness.
if (!userRepository.existsByTenantAndEmail(tenantId, emailCanonical)) {
    userRepository.insert(tenantId, emailCanonical);
    return "CREATED";
}
return "EMAIL_ALREADY_EXISTS";
~~~

Ở môi trường một request tại một thời điểm, logic này có vẻ hợp lý. Nhưng `exists` và `insert` là **hai hành động khác nhau**. Giữa hai hành động, hệ thống có thể thay đổi.

| Thứ tự | Request A | Request B |
| --- | --- | --- |
| T1 | `SELECT` email, kết quả: chưa có | |
| T2 | | `SELECT` cùng email, kết quả: chưa có |
| T3 | `INSERT` email thành công | |
| T4 | | `INSERT` cùng email thành công **nếu không có ràng buộc** |
| T5 | Commit | Commit |
| Kết quả | Một tài khoản | Thêm một tài khoản trùng email |

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Database không có UNIQUE
    participant B as Request B
    A->>DB: SELECT email?
    DB-->>A: Không tồn tại
    B->>DB: SELECT email?
    DB-->>B: Không tồn tại
    A->>DB: INSERT email
    DB-->>A: Thành công
    B->>DB: INSERT email
    DB-->>B: Thành công
    Note over A,B: Hai bản ghi trùng đã được chấp nhận
~~~

Đây là lỗi **TOCTOU**: kết quả đúng tại thời điểm *kiểm tra* không còn chắc chắn đúng tại thời điểm *sử dụng kết quả đó để ghi*. Độ trễ chỉ vài mili giây cũng đủ tạo cửa sổ tranh chấp. Việc chạy nhiều pod Java hoặc nhiều worker khiến lỗi dễ xảy ra hơn, nhưng chỉ hai thread cùng lúc đã đủ.

**Bất biến nghiệp vụ cần bảo vệ:** đối với cùng một tenant và một email chuẩn hóa, số hàng tài khoản còn thuộc phạm vi áp dụng uniqueness phải **không vượt quá một**. Hãy mô tả bất biến trước khi viết câu SQL.

## 2. Vì sao thêm transaction vẫn chưa tự động khắc phục?

Một phản ứng thường gặp là đặt cả `SELECT` và `INSERT` trong một transaction:

~~~sql
BEGIN;

SELECT user_id
FROM user_account
WHERE tenant_id = :tenant_id
  AND email_canonical = :email;

-- Không thấy hàng nào thì:
INSERT INTO user_account(user_id, tenant_id, email_canonical)
VALUES (:user_id, :tenant_id, :email);

COMMIT;
~~~

Cách này **chưa đủ** ở các isolation level thông dụng như `READ COMMITTED`. Hai transaction có thể cùng quan sát “chưa có hàng” và cùng ghi nếu database không có constraint hoặc một cơ chế đồng bộ mạnh khác.

### 2.1. Những cách “sửa nhanh” vẫn có lỗ hổng

| Cách thử | Vì sao chưa phải bảo đảm duy nhất tổng quát |
| --- | --- |
| Kiểm tra thêm lần nữa ngay trước INSERT | Vẫn có khoảng thời gian giữa lần kiểm tra cuối và lệnh ghi |
| Dùng `synchronized` trong Java | Chỉ khóa bên trong một JVM; không chặn instance khác, job import hay SQL trực tiếp |
| Đọc từ cache hoặc read replica | Cache/replica có thể cũ; không xác nhận trạng thái mới nhất tại nơi ghi |
| `SELECT ... FOR UPDATE` trên hàng sẽ được tạo | Khi hàng **chưa tồn tại**, thường không có hàng đó để khóa; hành vi khóa khoảng/đoạn khóa phụ thuộc DBMS và isolation |
| Tăng isolation level mà không hiểu semantics | Một số cơ chế có thể phát hiện xung đột nhưng cần retry đúng; chi phí và phạm vi khác nhau giữa các hệ quản trị |
| Dùng distributed lock nhưng không có UNIQUE | Khó bảo đảm mọi đường ghi đều giữ khóa, xử lý lease hết hạn và fencing; công cụ khóa có thể lỗi |

**Serializable isolation** trong các database hỗ trợ có thể giúp ngăn hoặc phát hiện lịch thực thi bất thường khi tất cả thao tác tuân thủ giao thức, nhưng ứng dụng phải xử lý **serialization failure** và retry cả transaction an toàn. Điều này không làm một quy tắc duy nhất trở nên thừa: khai báo `UNIQUE` trực tiếp diễn đạt bất biến tại nơi lưu trữ, kiểm soát được mọi đường ghi chịu ràng buộc và thường dễ xác minh hơn.

## 3. Khai báo uniqueness trong lược đồ

Ví dụ PostgreSQL cho một ứng dụng đa tenant:

~~~sql
CREATE TABLE user_account (
    user_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email_canonical TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_email_not_blank
        CHECK (length(btrim(email_canonical)) > 0),
    CONSTRAINT uq_user_tenant_email
        UNIQUE (tenant_id, email_canonical)
);
~~~

Ràng buộc `uq_user_tenant_email` bảo đảm không có hai hàng có **cùng cặp** `(tenant_id, email_canonical)` theo quy tắc so sánh của database. Khi hai transaction cùng `INSERT` cặp khóa đó, database phối hợp kiểm tra trong cơ chế ghi/chỉ mục duy nhất; **không thể cùng commit hai hàng vi phạm ràng buộc**. Một bên có thể phải chờ kết quả của bên kia, rồi nhận lỗi uniqueness hoặc xử lý xung đột tùy câu lệnh.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Database có UNIQUE
    participant B as Request B
    A->>DB: INSERT (tenant, email)
    B->>DB: INSERT cùng (tenant, email)
    DB-->>A: Commit thành công
    DB-->>B: Xung đột khóa duy nhất
    Note over A,B: Chỉ một giá trị khóa nghiệp vụ được chấp nhận
~~~

Sơ đồ mô tả **một kết quả khả dĩ**: A thắng, B xung đột. Thực tế thứ tự bên thắng còn phụ thuộc lịch thực thi; nếu A rollback thì B có thể tiếp tục và thành công. Quan trọng là trạng thái sau commit không vi phạm ràng buộc.

### 3.1. Khóa duy nhất khác khóa chính như thế nào?

- **`PRIMARY KEY`:** định danh mỗi hàng, không `NULL`, và bảng thường chỉ có một ràng buộc khóa chính (có thể gồm nhiều cột).
- **`UNIQUE`:** bảo vệ một hoặc nhiều khóa nghiệp vụ bổ sung; bảng có thể có nhiều ràng buộc UNIQUE.
- **Unique index:** cấu trúc chỉ mục có thể thực thi tính duy nhất; tùy DBMS còn hỗ trợ biểu thức hoặc điều kiện lọc mà `UNIQUE constraint` thông thường không biểu đạt trực tiếp.

Trong ví dụ, `user_id` định danh kỹ thuật ổn định, còn `(tenant_id, email_canonical)` là khóa nghiệp vụ. Không nên coi email là ID ổn định cho mọi quan hệ: người dùng có thể đổi email, còn lịch sử và khóa ngoại vẫn cần trỏ tới cùng `user_id`.

### 3.2. Phạm vi duy nhất phải đến từ nghiệp vụ

| Yêu cầu | Khóa/điều kiện cần cân nhắc |
| --- | --- |
| Mỗi tenant chỉ có một email hoạt động | `(tenant_id, email_canonical)` với quy tắc active thích hợp |
| Mã sản phẩm duy nhất trong một cửa hàng | `(store_id, product_code)` |
| Mã đơn hàng duy nhất toàn hệ thống | `order_code` hoặc ID được cấp duy nhất |
| Một lần xử lý cho mỗi sự kiện bên ngoài | `(provider, provider_event_id)` |
| Mã phiếu ưu đãi duy nhất trong một chiến dịch | `(campaign_id, coupon_code)` |

Đặt `UNIQUE(email_canonical)` toàn hệ thống khi email chỉ cần duy nhất **trong tenant** sẽ từ chối sai dữ liệu hợp lệ. Ngược lại, đặt `UNIQUE(tenant_id, email_canonical)` khi email bắt buộc duy nhất toàn hệ thống sẽ bỏ lọt trùng liên tenant. **Đúng phạm vi quan trọng không kém việc có ràng buộc.**

## 4. Chuẩn hóa đầu vào: hai chuỗi khác nhau có thể là một giá trị nghiệp vụ

Giả sử hệ thống coi `User@Example.com` và `user@example.com` là cùng email đăng nhập. Nếu chỉ dùng `UNIQUE(email)` nhưng lưu chuỗi chưa chuẩn hóa, cách so sánh của database có thể cho phép cả hai.

Một số quyết định cần công bố:

1. Có trim khoảng trắng quanh input không?
2. Có quy tắc so sánh không phân biệt hoa/thường không?
3. Với Unicode, có cần chuẩn hóa dạng ký tự hay collation cụ thể không?
4. Với email, tên miền, dấu cộng và local-part được xử lý thế nào? Không nên tự ý gộp hai địa chỉ chỉ vì một số nhà cung cấp email có quy tắc riêng.
5. Nếu dữ liệu nhập từ hệ thống khác, mọi đường ghi có áp dụng cùng quy tắc không?

**Mô hình A:** application service chuẩn hóa thành `email_canonical`, database đặt `UNIQUE(tenant_id, email_canonical)`. Khi đó phải kiểm thử các đường ghi, import và migration để không có đường nào bỏ qua chuẩn hóa.

**Mô hình B:** dùng unique index dựa trên biểu thức nếu DBMS phù hợp. Ví dụ PostgreSQL với quy tắc nghiệp vụ *chỉ* cần bỏ khoảng trắng hai đầu và lower-case theo semantics của database:

~~~sql
CREATE UNIQUE INDEX uq_user_tenant_email_folded
ON user_account (tenant_id, lower(btrim(email_canonical)));
~~~

Ví dụ này minh họa công cụ **expression unique index**, không khuyến nghị tạo đồng thời với `uq_user_tenant_email` trong mọi hệ thống. Nó cũng không đủ giải quyết mọi vấn đề chuẩn hóa Unicode, quy tắc địa chỉ email hoặc collation. Để tránh bất nhất, chọn **một hợp đồng canonicalization rõ ràng**, bổ sung ràng buộc phù hợp và kiểm tra những dữ liệu đã lưu trước khi áp dụng index.

## 5. Giá trị NULL, cột tùy chọn và xóa mềm

### 5.1. UNIQUE và NULL

Không được mặc định `UNIQUE(nullable_column)` có nghĩa “chỉ một hàng được `NULL`”. Trong PostgreSQL và nhiều DBMS, mặc định các giá trị `NULL` được xem là **khác nhau khi kiểm tra tính duy nhất**, nên nhiều hàng có `NULL` vẫn được phép. Một số DBMS hoặc cấu hình có semantics khác.

Nếu khóa nghiệp vụ **bắt buộc phải có**, dùng `NOT NULL` cùng `UNIQUE`. Nếu thật sự cần xem `NULL` là một giá trị trùng nhau, PostgreSQL 15+ có lựa chọn `UNIQUE NULLS NOT DISTINCT`; cần kiểm tra phiên bản và nhu cầu nghiệp vụ trước khi áp dụng. Không thay `NULL` bằng chuỗi rỗng một cách tùy tiện để “né” ràng buộc.

### 5.2. Chỉ duy nhất với bản ghi đang hoạt động

Một khách hàng có thể đăng ký tài khoản mới bằng email của tài khoản đã bị xóa mềm, trong khi lịch sử tài khoản cũ vẫn được giữ. Khi đó khóa duy nhất vô điều kiện sẽ chặn việc tái sử dụng. Có thể mô hình hóa bằng **partial unique index** trên PostgreSQL:

~~~sql
CREATE TABLE customer_account (
    account_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email_canonical TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_customer_active_email
ON customer_account (tenant_id, email_canonical)
WHERE deleted_at IS NULL;
~~~

Ràng buộc này bảo vệ **các tài khoản chưa xóa mềm**, nhưng không ngăn nhiều hàng cũ đã xóa dùng cùng email. Nếu khôi phục tài khoản đã xóa mềm trong khi email đã được dùng lại, thao tác đổi `deleted_at` thành `NULL` có thể bị từ chối: đây là kết quả **đúng** của bất biến, cần quy trình xử lý xung đột khôi phục.

**Lưu ý:** partial unique index khác với một `UNIQUE constraint` thông thường. Khi dùng `ON CONFLICT`, cú pháp conflict target phải phù hợp với index và predicate; không thể mặc nhiên dùng tên một partial index với `ON CONFLICT ON CONSTRAINT`. Điều kiện index nên dựa trên trạng thái đã lưu, không dùng `now()` để tự coi một bản ghi là hết hạn theo đồng hồ động.

### 5.3. Một ghế chỉ có một giữ chỗ hiệu lực

Với đặt vé, yêu cầu thường là “một ghế không có hai giữ chỗ **đang hiệu lực**”, không phải “mỗi ghế chỉ từng có một giao dịch trong lịch sử”.

~~~sql
CREATE TABLE seat_hold (
    hold_id UUID PRIMARY KEY,
    event_id UUID NOT NULL,
    seat_code TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('HELD', 'CONFIRMED', 'EXPIRED', 'CANCELLED')
    ),
    expires_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_seat_occupied
ON seat_hold (event_id, seat_code)
WHERE state IN ('HELD', 'CONFIRMED');
~~~

Khi giữ chỗ hết hạn, worker hoặc transaction có thẩm quyền phải chuyển `HELD → EXPIRED` **trước khi** cho phép giữ chỗ mới. Một hàng vẫn có state `HELD` sẽ tiếp tục chiếm khóa, kể cả `expires_at` đã qua; điều này giúp tránh việc một index phụ thuộc đồng hồ động tự thay đổi ngầm. Ứng dụng cần xử lý job hết hạn, retry và trường hợp khách thanh toán đúng sát thời hạn với giao dịch nhất quán.

**Giới hạn:** unique index phù hợp cho bất biến “một khóa hoạt động”. Với bất biến phức tạp như *hai khoảng thời gian đặt phòng không được chồng lấn*, equality `UNIQUE(room_id, start_time)` là chưa đủ; có thể cần exclusion constraint, khóa/transaction hoặc mô hình đặt chỗ chuyên biệt tùy DBMS.

## 6. Cách ghi an toàn: INSERT, xử lý conflict và UPSERT

### 6.1. Để database quyết định, không xem SELECT là quyền ghi

Với lược đồ `user_account` có `uq_user_tenant_email`, có thể dùng:

~~~sql
INSERT INTO user_account(user_id, tenant_id, email_canonical)
VALUES (:user_id, :tenant_id, :email);
~~~

Ứng dụng gửi lệnh ghi, database áp dụng ràng buộc. Nếu khóa đã tồn tại, trên PostgreSQL thường nhận **SQLSTATE `23505` (unique_violation)**. Đây là **xung đột dữ liệu**, không nhất thiết là sự cố hạ tầng.

Nhưng `23505` có thể đến từ **bất kỳ ràng buộc duy nhất nào** trong câu lệnh, chẳng hạn trùng `user_id` hay trùng email. Không được chỉ dựa trên SQLSTATE rồi báo “email đã tồn tại” nếu không biết constraint nào bị vi phạm. Có thể dùng metadata lỗi của driver để nhận tên constraint, hoặc viết SQL nêu rõ conflict target như phần tiếp theo.

### 6.2. INSERT ... ON CONFLICT DO NOTHING

Trong PostgreSQL, khi muốn trả kết quả rõ ràng cho trường hợp email đã được dùng:

~~~sql
INSERT INTO user_account(user_id, tenant_id, email_canonical)
VALUES (:user_id, :tenant_id, :email)
ON CONFLICT ON CONSTRAINT uq_user_tenant_email
DO NOTHING
RETURNING user_id;
~~~

- Nếu tạo thành công, `RETURNING` trả `user_id` mới.
- Nếu có xung đột đúng constraint `uq_user_tenant_email`, `DO NOTHING` không tạo hàng và không trả dòng mới.
- Lỗi ở constraint khác hoặc lỗi hạ tầng **không tự động bị nuốt** bởi conflict target này.

Trong ngữ cảnh đăng ký tài khoản, không nên tự động trả ID của tài khoản có email trùng cho người gửi yêu cầu: cần kiểm tra danh tính và chính sách chống dò tài khoản. `DO NOTHING` cũng không chứng minh hai request có cùng payload nghiệp vụ, nên chưa phải toàn bộ cơ chế idempotency.

### 6.3. UPSERT không đồng nghĩa “an toàn để ghi đè”

`ON CONFLICT ... DO UPDATE` có thể rất hữu ích cho phép cập nhật có chủ đích, ví dụ bộ đếm hoặc dữ liệu đồng bộ theo khóa. Tuy nhiên, nếu dùng nó ở nghiệp vụ đăng ký tài khoản mà không kiểm tra quyền, một request mới có thể ghi đè hồ sơ đã thuộc người khác.

Hãy phân biệt:

| Ý định nghiệp vụ | Cách xử lý phù hợp |
| --- | --- |
| Tạo mới, trùng khóa thì từ chối | `INSERT` cùng `UNIQUE`, bắt conflict hoặc `DO NOTHING` |
| Cùng request gửi lại sau mất kết nối | Idempotency key, tra cứu kết quả đã xử lý; không tự gộp theo email |
| Cập nhật tài khoản đã xác thực | `UPDATE` có kiểm tra owner/quyền và version |
| Nhập dữ liệu từ nguồn có thẩm quyền với upsert | Quy tắc merge, version và xung đột đã được thiết kế rõ |

## 7. Java/JDBC: ánh xạ kết quả xung đột có chủ đích

Ví dụ Java 17+ sau sử dụng PostgreSQL và `PreparedStatement`. Hệ thống giả định đã xác thực tenant, kiểm tra định dạng email và tạo **`emailCanonical` theo một chính sách thống nhất** trước khi gọi repository:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class UserRegistrationRepository {
    public enum Outcome { CREATED, EMAIL_TAKEN }

    private final DataSource dataSource;

    public UserRegistrationRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Outcome create(UUID tenantId, UUID newUserId, String emailCanonical)
            throws SQLException {
        String sql = """
                INSERT INTO user_account
                    (user_id, tenant_id, email_canonical)
                VALUES (?, ?, ?)
                ON CONFLICT ON CONSTRAINT uq_user_tenant_email
                DO NOTHING
                RETURNING user_id
                """;

        // Một statement đã có tính nguyên tử và bảo vệ bởi UNIQUE.
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, newUserId);
            statement.setObject(2, tenantId);
            statement.setString(3, emailCanonical);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    return Outcome.CREATED;
                }
                return Outcome.EMAIL_TAKEN;
            }
        }
    }
}
~~~

Phương thức này không cần thêm `SELECT` kiểm tra trước. **Kết quả xung đột là kết quả kỳ vọng**, còn lỗi kết nối, lỗi constraint khác hoặc lỗi SQL sẽ ném `SQLException` để tầng ứng dụng phân loại và xử lý.

Đây chỉ là ví dụ **một lệnh tạo hàng**. Khi đăng ký cần tạo hồ sơ, nhật ký audit và sự kiện outbox cùng lúc, phải đặt các lệnh phụ thuộc trong một transaction. Nếu ORM/JPA được dùng thay JDBC, vẫn cần unique constraint ở database; `existsBy...` của Spring Data chỉ là hỗ trợ tiền kiểm tra, không bảo vệ được bất biến dưới tải đồng thời.

### 7.1. Khi nào dùng 409, khi nào dùng lỗi khác?

| Tình huống | Cách xử lý ở API |
| --- | --- |
| Email trùng trong phạm vi đã xác định | Thường trả `409 Conflict` nếu API cho phép công bố; với đăng ký công khai có thể dùng thông báo không tiết lộ sự tồn tại tài khoản |
| Trường email sai định dạng | `400 Bad Request` hoặc mã lỗi validation theo hợp đồng |
| Trùng `user_id` do sinh ID/cấu hình lỗi | Không báo sai thành “email đã tồn tại”; ghi log và điều tra |
| Kết nối database bị timeout | Lỗi hạ tầng/tạm thời, không diễn giải là uniqueness conflict |
| Client mất kết nối đúng lúc commit | Kết quả có thể chưa xác định từ góc nhìn client; dùng request ID để đối soát |

Lỗi uniqueness nên được phát hiện qua **mã lỗi/constraint có cấu trúc** thay vì so khớp chuỗi thông báo của database; chuỗi lỗi có thể thay đổi theo phiên bản, ngôn ngữ hoặc driver.

## 8. Uniqueness khác idempotency và optimistic locking

Ba khái niệm thường đi cùng nhau nhưng bảo vệ ba vấn đề khác nhau:

| Cơ chế | Bất biến bảo vệ | Ví dụ |
| --- | --- | --- |
| **UNIQUE** | Không có hai hàng cùng khóa nghiệp vụ đã định | Trong tenant, email chuẩn hóa không trùng |
| **Idempotency** | Retry **cùng một ý định** không tạo tác động nghiệp vụ lặp | Cùng `request_id` đăng ký/ghi thanh toán trả cùng kết quả |
| **Optimistic locking** | Không ghi đè im lặng một trạng thái đã bị đổi kể từ lúc đọc | `UPDATE ... WHERE version = :expected_version` |

Hai request có cùng email nhưng **khác người dùng hoặc khác ý định** không tự trở thành một request idempotent. Ngược lại, hai lần gửi cùng `request_id` nhưng payload khác phải được phát hiện là xung đột, không trả lại thành công một cách mù quáng.

Một mô hình có thể dùng bảng xử lý yêu cầu:

~~~sql
CREATE TABLE processed_registration (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    payload_hash TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES user_account(user_id),
    PRIMARY KEY (tenant_id, request_id)
);
~~~

Application service phải tạo user và ghi nhận `request_id`/hash của payload trong **cùng transaction**. Khi retry, tra kết quả cũ theo `(tenant_id, request_id)`, so sánh hash/các thuộc tính đã xác thực và trả kết quả cũ hoặc từ chối nếu payload khác. Việc đối chiếu request và xử lý xung đột phải được thiết kế atomically; **một bảng có unique request ID chưa tự làm cả quy trình trở nên idempotent**.

### 8.1. Hai thao tác UPDATE cũng có thể đụng UNIQUE

Giả sử A và B đang sở hữu hai tài khoản khác nhau rồi cùng sửa email thành `new@example.com`. Dù không tạo hàng mới, hai lệnh `UPDATE` vẫn tranh chấp khóa duy nhất. Database phải từ chối một kết quả vi phạm.

Nếu có cả cập nhật trạng thái và kiểm soát phiên bản, một câu lệnh có thể kiểm tra:

~~~sql
UPDATE user_account
SET email_canonical = :new_email
WHERE user_id = :user_id
  AND tenant_id = :tenant_id
  AND version = :expected_version;
~~~

Câu lệnh này **giả định** bảng đã có cột `version` và ứng dụng đồng thời tăng version trong cập nhật thực tế; đây là mẫu điều kiện, chưa phải SQL hoàn chỉnh cho schema ở phần 3. Với hệ thống thật, cần thêm `version = version + 1` trong `SET` và kiểm tra số hàng bị thay đổi. **Optimistic locking không thay thế UNIQUE**: version xử lý sửa đè cùng hàng, còn UNIQUE bảo vệ xung đột giữa nhiều hàng khác nhau.

## 9. Những giới hạn của ràng buộc duy nhất

Một ràng buộc duy nhất không thể thay toàn bộ thiết kế dữ liệu:

- **Đúng phạm vi:** nếu uniqueness có điều kiện active, phải mô hình hóa trạng thái active rõ và bảo vệ các chuyển trạng thái; một `CHECK` hay khóa phụ khác có thể vẫn cần.
- **Đúng cách so sánh:** canonicalization, collation và `NULL` phải phù hợp với quy tắc nghiệp vụ.
- **Đúng ranh giới:** unique index trong một database không tự bảo đảm tính duy nhất toàn cục nếu các dịch vụ có nguồn ghi độc lập.
- **Đúng bất biến:** hai khoảng đặt phòng chồng lấn, số lượng tồn kho không âm hoặc chuyển tiền cân bằng không thể giải quyết chỉ bằng unique email.
- **Đúng quyền:** uniqueness không kiểm soát việc người dùng có được tạo/xem/sửa hàng đó hay không.

Nếu có nhiều primary nhận ghi độc lập hoặc replication bất đồng bộ giữa vùng, **không được suy ra rằng hai unique index cục bộ tạo ra uniqueness toàn cục tức thời**. Cần chọn nơi chấp nhận ghi có thẩm quyền, cơ chế phân vùng khóa, giao thức phân tán hoặc hệ lưu trữ có cam kết global uniqueness phù hợp.

Ở hệ thống event-driven, mỗi consumer có thể dùng UNIQUE trên `(source, event_id)` để hỗ trợ loại trùng **trong phạm vi kho của chính nó**. Dù vậy, thao tác với hệ ngoài vẫn cần thiết kế outbox/inbox, retry và khả năng quan sát trạng thái từng bước.

## 10. Migration: thêm UNIQUE vào dữ liệu đã tồn tại

Nếu một bảng đã có dữ liệu trùng, lệnh thêm constraint có thể thất bại. Không nên tự xóa các hàng “bị trùng” khi chưa biết chúng có ý nghĩa khác nhau hay không.

### 10.1. Khảo sát và phân loại dữ liệu

~~~sql
-- Các nhóm trùng theo chính khóa nghiệp vụ dự định bảo vệ:
SELECT tenant_id, email_canonical, COUNT(*) AS occurrences
FROM user_account
GROUP BY tenant_id, email_canonical
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;
~~~

Nếu schema cũ lưu email chưa canonicalize, kiểm tra thêm những nhóm sẽ trùng **sau** khi áp dụng quy tắc chuẩn hóa mới. Đồng thời khảo sát giá trị trống, `NULL`, dấu cách, case và Unicode trong dữ liệu lịch sử.

Quy trình sửa có thể gồm: xác minh tài khoản chủ sở hữu, hợp nhất có kiểm toán, đổi khóa ở những bản ghi có thể sửa, giữ lịch sử cần thiết và cập nhật khóa ngoại. Với dữ liệu cá nhân hoặc giao dịch, cần người sở hữu nghiệp vụ xác nhận chính sách giải quyết trùng.

### 10.2. Triển khai ràng buộc mà không mở cửa sổ phát sinh trùng mới

Một kế hoạch hợp lý:

1. Định nghĩa khóa và cách chuẩn hóa; chọn chính xác bảng, tenant, điều kiện active.
2. Đảm bảo đường ghi hiện tại tuân thủ hợp đồng; ghi nhận và xử lý các conflict đã phát hiện.
3. Dọn dữ liệu cũ có kiểm toán, đối soát bản ghi trước/sau.
4. Thiết lập quy trình triển khai index/constraint an toàn cho dữ liệu lớn, tính đến các ghi đồng thời trong lúc dựng index.
5. Xác minh bằng concurrency test và query plan, kiểm tra lỗi trả về từ JDBC/ORM.
6. Theo dõi conflict rate và dọn lớp tiền kiểm tra không cần thiết, hoặc giữ nó chỉ để cải thiện UX.

Ở PostgreSQL, có thể sử dụng `CREATE UNIQUE INDEX CONCURRENTLY` trong một số trường hợp để giảm thời gian chặn ghi, nhưng thao tác này **không chạy trong transaction block thông thường**, vẫn có thể thất bại do bản ghi trùng xuất hiện trong quá trình dựng index và có thể để lại index không hợp lệ cần xử lý. Không coi đây là “một lệnh online an toàn tuyệt đối”. Phải lên lịch, quan sát tiến độ và có kế hoạch rollback.

Với hệ cần giữ giao dịch liên tục, cách migration còn tùy dung lượng bảng, tốc độ ghi và phiên bản database. Hãy thử trên bản dữ liệu đại diện và xác định rõ thời gian khóa chấp nhận được.

## 11. Kiểm thử đồng thời: chứng minh không còn hai bản ghi trùng

Một bài kiểm thử chỉ gửi lần lượt 100 request có thể không phát hiện TOCTOU. Cần **nhiều kết nối và transaction độc lập**, cùng cạnh tranh một khóa nghiệp vụ:

1. Chuẩn bị một tenant thử nghiệm và một email canonical chưa tồn tại.
2. Khởi tạo 20–50 task có kết nối database độc lập, dùng hàng rào bắt đầu để gửi lệnh tạo gần đồng thời.
3. Mỗi task dùng `user_id` mới, nhưng `tenant_id` và `email_canonical` giống nhau.
4. Chờ tất cả task kết thúc, phân loại `CREATED`, conflict, timeout và lỗi bất thường.
5. Truy vấn database để xác nhận **chính xác một hàng đã commit** cho cặp khóa; những task còn lại không tạo tác động phụ hoặc event trùng.
6. Lặp lại với các case khác tenant, email khác hoa/thường, email null, soft delete/restore và đổi email bằng UPDATE.

Ví dụ câu truy vấn kiểm chứng:

~~~sql
SELECT COUNT(*) AS matching_rows
FROM user_account
WHERE tenant_id = :tenant_id
  AND email_canonical = :email;
-- Kỳ vọng: 1 sau khi mọi task và transaction hoàn tất.
~~~

### 11.1. Bộ ca kiểm thử cần thiết

| Ca | Điều cần quan sát |
| --- | --- |
| Hai INSERT đồng thời cùng khóa | Chỉ một bản ghi được chấp nhận; bên còn lại bị conflict hoặc no-op rõ ràng |
| Hai INSERT cùng email ở hai tenant | Cả hai hợp lệ nếu khóa là `(tenant_id, email)` |
| Hai UPDATE từ hai user sang cùng email | Không cùng commit hai hàng có email trùng |
| Ghi dữ liệu bằng batch/import bỏ qua API Java | Database vẫn chặn vi phạm uniqueness |
| Hệ dùng cache hoặc read replica trễ | Kết quả precheck có thể cũ nhưng lần ghi vẫn bảo vệ bất biến |
| Retry cùng request ID sau khi mất kết nối khi commit | Không phát sinh hai tác động; có đối soát trạng thái |
| Tạo tài khoản sau khi tài khoản cũ soft delete | Phù hợp với uniqueness của các bản ghi active |
| Khôi phục tài khoản cũ trong lúc email đã được dùng | Phát sinh conflict, không tự ghi đè hoặc vượt ràng buộc |
| Chạy migration trên dữ liệu trùng lịch sử | Có danh sách xử lý trùng và chỉ hoàn tất khi unique được xác minh |

Quan sát chỉ số conflict rate, thời gian chờ khóa/index, tỷ lệ rollback, retry và p95/p99. Một mức conflict tăng không nhất thiết chứng minh database lỗi; có thể phản ánh người dùng cùng tranh chấp một khóa. Tuy nhiên, việc retry vô hạn hoặc trả `500` cho mọi conflict có thể gây tải và trải nghiệm xấu.

## 12. Bảo mật, sao lưu và phục hồi

Tính duy nhất không chỉ là tối ưu dữ liệu:

- **Thông tin nhạy cảm:** API đăng ký có thể không nên nói rõ email đã tồn tại để tránh dò tài khoản. Dù thông báo phản hồi được làm chung, database vẫn phải bảo vệ constraint.
- **Quyền ghi:** không cho job quản trị hoặc API bỏ qua ràng buộc để “cứu lỗi” mà không có chính sách rõ ràng; mọi đường ghi phải đi qua nơi có thẩm quyền.
- **Audit:** ghi loại xung đột, constraint, request/correlation ID theo mức cần thiết; không đưa mật khẩu, token hoặc dữ liệu cá nhân không cần thiết vào log.
- **Backup/restore:** cần có bản phục hồi nhất quán trước migration dữ liệu và thử restore. Replica không thay thế backup; lỗi cập nhật trùng hoặc xóa sai có thể lan theo replication.
- **Tiến hóa schema:** nếu thay khóa uniqueness, triển khai theo các giai đoạn tương thích với nhiều phiên bản ứng dụng, kiểm tra dữ liệu trước khi siết constraint.
- **Khôi phục sau lỗi commit:** trạng thái giao dịch từ góc nhìn client có thể không chắc chắn, nên phải dùng kết quả idempotency/khóa nghiệp vụ để đối soát, không tự tạo yêu cầu mới và hy vọng UNIQUE giải quyết toàn bộ nghiệp vụ.

## 13. Bài tập tình huống

Một hệ thống bán vé có ứng dụng Java, PostgreSQL và ba instance API. Mã hiện tại:

~~~text
if (!seatHoldRepository.exists(eventId, seatCode)) {
    seatHoldRepository.save(newHold);
    return SUCCESS;
}
return SEAT_TAKEN;
~~~

Khi một chương trình mở bán, nhiều người có thể cùng đặt ghế `A12`. Hệ thống còn hỗ trợ hủy giữ ghế sau 10 phút, thanh toán xác nhận ghế và lưu lịch sử giữ ghế đã hủy.

**Yêu cầu giải quyết:**

1. Chỉ ra lịch thực thi khiến hai người cùng nhận `SUCCESS` nếu không có constraint.
2. Định nghĩa rõ “một ghế không có hai giữ chỗ **đang hiệu lực**” bao gồm những trạng thái nào.
3. Đề xuất bảng và partial unique index (nếu dùng PostgreSQL), hoặc cơ chế tương đương đã được kiểm chứng.
4. Nêu điều gì xảy ra khi thời hạn giữ ghế đã qua nhưng hàng vẫn có state `HELD`.
5. Thiết kế giao dịch xác nhận thanh toán và chuyển trạng thái giữ ghế để không tạo hai chủ sở hữu khi có tranh chấp.
6. Phân biệt constraint vi phạm với lỗi database timeout và với retry cùng `request_id`.
7. Đưa ra ít nhất năm kiểm thử cạnh tranh hoặc phục hồi.

**Hướng giải:** tạo khóa duy nhất có điều kiện theo `(event_id, seat_code)` đối với các trạng thái `HELD` và `CONFIRMED`. Giao dịch hết hạn cần đổi `HELD` sang `EXPIRED` trước khi ghế có thể được giữ lại. Mỗi yêu cầu có ID ổn định và chỉ được trả thành công sau khi giao dịch được xác nhận; xử lý callback thanh toán phải idempotent, kiểm tra trạng thái và hạn giữ trong cùng cơ chế đồng thời có thẩm quyền. Tiền kiểm tra vẫn có thể giúp UI hiển thị “có vẻ còn chỗ”, nhưng **kết quả cuối phải do đường ghi có constraint quyết định**.

## 14. Checklist áp dụng

- [ ] Đã viết rõ bất biến “duy nhất” cùng **phạm vi** và các trạng thái được tính.
- [ ] Mọi khóa nghiệp vụ được chuẩn hóa và so sánh nhất quán theo quy tắc được công bố.
- [ ] `PRIMARY KEY`, `UNIQUE`/unique index, `NOT NULL` và các ràng buộc liên quan được đặt tại nơi ghi có thẩm quyền.
- [ ] Không dùng `exists`, `SELECT` hoặc cache như bằng chứng đảm bảo thao tác INSERT kế tiếp an toàn.
- [ ] Java/JDBC/ORM phân biệt đúng constraint conflict, validation, hạ tầng và commit chưa rõ kết quả.
- [ ] Có idempotency riêng khi retry có thể tạo tác động lặp; không đồng nhất idempotency key với email hay khóa nghiệp vụ.
- [ ] Với soft delete, partial index và khôi phục tài khoản, đã xác định quy tắc tái sử dụng khóa.
- [ ] Các thao tác UPDATE cũng được thử khi hai hàng khác nhau cạnh tranh cùng một giá trị.
- [ ] Migration bổ sung unique có khảo sát dữ liệu trùng và kế hoạch xử lý ghi đồng thời.
- [ ] Đã chạy concurrent test qua nhiều kết nối và kiểm tra trạng thái **sau commit**.
- [ ] Có giám sát conflict, lock wait, rollback, retry và ảnh hưởng p95/p99.
- [ ] Bảo mật phản hồi API, audit và kế hoạch backup/restore vẫn đáp ứng yêu cầu nghiệp vụ.

**Ghi nhớ:** Một lần `SELECT` trả “chưa có” chỉ chứng minh **ở thời điểm và mức quan sát đó chưa nhìn thấy hàng**, không cấp quyền độc quyền cho lần `INSERT` tiếp theo. **Ràng buộc UNIQUE ở database có thẩm quyền** mới bảo vệ tính duy nhất trước những thao tác ghi đồng thời, còn tiền kiểm tra chỉ hỗ trợ trải nghiệm. Để có persistence đáng tin cậy trong Java, cần phối hợp unique constraint đúng phạm vi, xử lý conflict, transaction, idempotency, migration và kiểm thử concurrency.
