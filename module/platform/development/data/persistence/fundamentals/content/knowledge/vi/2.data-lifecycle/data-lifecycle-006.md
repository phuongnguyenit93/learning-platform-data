# Theo dõi thời điểm tạo, cập nhật và nguồn thay đổi

Trong chương **Vòng đời dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, mỗi bản ghi không chỉ có giá trị hiện tại mà còn có lịch sử hình thành và biến đổi. Khi ứng dụng Java quản lý khách hàng, đơn hàng hoặc cấu hình nghiệp vụ, người vận hành thường phải trả lời: **bản ghi được tạo khi nào, lần cuối thay đổi lúc nào, ai hoặc hệ thống nào thực hiện, yêu cầu nào gây ra thay đổi và thay đổi đó đã được lưu bền vững hay chưa?**

Việc lưu metadata thời gian và nguồn thay đổi giúp truy vết lỗi, đối soát dữ liệu, phát hiện cập nhật cạnh tranh, hỗ trợ migration và khôi phục. Đây là một phần của thiết kế ranh giới persistence cùng với lược đồ, giao dịch, cô lập, bảo mật, sao lưu và tối ưu truy vấn; không nên coi là các cột bổ sung tùy ý.

**Mục tiêu học tập**

- Phân biệt thời điểm tạo/cập nhật bản ghi với thời điểm sự kiện nghiệp vụ xảy ra và thời điểm dữ liệu được hệ thống tiếp nhận.
- Thiết kế các trường thời gian, tác nhân, nguồn thay đổi, mã truy vết và phiên bản bản ghi với ngữ nghĩa rõ ràng.
- Thực hiện cập nhật dữ liệu và ghi nhật ký thay đổi trong cùng giao dịch Java/JDBC.
- Giải thích ưu và nhược điểm của audit bằng ứng dụng, trigger, CDC và event sourcing.
- Xử lý cập nhật đồng thời, retry, dữ liệu nhập muộn, bảo mật nhật ký và khôi phục lịch sử thay đổi.

## 1. Phân biệt những mốc thời gian dễ bị nhầm lẫn

Giả sử một khách hàng đổi số điện thoại lúc 09:00, nhưng thiết bị mất mạng đến 09:07 mới gửi yêu cầu. Đến 09:08, hệ thống nhập dữ liệu nhận và ghi phiên bản hồ sơ mới vào database. Nếu chỉ có một trường `updated_at`, ta khó biết mốc nào đang được biểu diễn.

| Trường gợi ý | Câu hỏi được trả lời | Ai thường xác định? |
| --- | --- | --- |
| `created_at` | Bản ghi này được tạo trong kho dữ liệu lúc nào? | Database tại thời điểm ghi |
| `updated_at` | Lần ghi thay đổi trạng thái bản ghi gần nhất được thực hiện lúc nào? | Database hoặc thành phần ghi có thẩm quyền |
| `occurred_at` | Sự kiện ngoài đời hoặc trong hệ thống nguồn xảy ra khi nào? | Hệ thống phát sinh sự kiện, có thể không hoàn toàn tin cậy |
| `received_at` / `ingested_at` | Hệ thống nhận sự kiện hoặc nhập dữ liệu lúc nào? | Thành phần nhận dữ liệu |
| `effective_at` | Quy tắc hoặc giá trị nghiệp vụ có hiệu lực từ khi nào? | Logic nghiệp vụ |
| `deleted_at` | Khi nào đối tượng được đánh dấu xóa mềm? | Thành phần sở hữu dữ liệu |
| `recorded_at` | Bản ghi kiểm toán được ghi lại lúc nào? | Hệ thống lưu nhật ký |

Các mốc có thể khác nhau mà vẫn đúng. Chẳng hạn, giá sản phẩm được nhập lúc 15:00 nhưng có hiệu lực từ 00:00 ngày hôm sau: `updated_at` nói về **thời gian ghi**, `effective_at` nói về **thời gian hiệu lực nghiệp vụ**. Khi cần hỏi “hệ thống đã biết gì tại thời điểm X?” và “giá trị có hiệu lực ở thời điểm Y là gì?”, hệ thống có thể cần lưu cả **transaction time** và **valid time** (mô hình bitemporal), thay vì suy luận từ một cột.

### 1.1. Thời gian không phải là thứ tự thay đổi đáng tin tuyệt đối

Hai lần ghi có thể có timestamp bằng nhau do độ phân giải đồng hồ. Đồng hồ ở hai máy cũng có thể lệch hoặc bị điều chỉnh; ngay cả đồng hồ database cũng không nên dùng thay thế cơ chế xác định thứ tự giao dịch. Thời điểm ghi được tính lúc bắt đầu transaction, bắt đầu statement hay lúc thực thi hàm thời gian cũng có thể khác nhau.

Vì vậy:

- Dùng **timestamp** để tra cứu, hiển thị, phân tích độ trễ và tìm khoảng thời gian.
- Dùng **version**, sequence, vị trí log hoặc định danh thứ tự do hệ thống sở hữu xác nhận để nhận biết cập nhật mới hơn hay kiểm soát tranh chấp.
- Dùng **commit status** hoặc sự kiện đã ghi bền vững để kết luận thao tác thành công; thời gian trên request không đủ làm bằng chứng.

## 2. Cần biết cả “ai”, “từ đâu” và “vì sao”

Thời gian chỉ trả lời được một phần. Hai thay đổi cùng lúc có thể đến từ người dùng, tác vụ tự động, đồng bộ từ đối tác, công cụ quản trị hoặc luồng migration. **Nguồn thay đổi (provenance)** cho biết dữ liệu đến từ đâu và qua quá trình nào; nó cần được tách khỏi **tác nhân (actor)** thực hiện.

Ví dụ: nhân viên hỗ trợ khởi tạo yêu cầu thay đổi địa chỉ giao hàng qua giao diện quản trị; một background worker xử lý và ghi database. Tác nhân nghiệp vụ là nhân viên, tác nhân thực thi là worker, còn kênh thay đổi là `ADMIN_PORTAL`. Nếu chỉ lưu tên worker, ta không biết ai đã yêu cầu.

| Metadata | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| `actor_id` / `updated_by` | Danh tính đã được xác thực của tác nhân khởi tạo | `user:42`, `service:importer` |
| `executed_by` | Dịch vụ/job thực sự thực thi lệnh ghi | `service:profile-worker` |
| `source_kind` | Kênh hoặc loại nguồn thay đổi | `API`, `ADMIN`, `IMPORT`, `WEBHOOK`, `MIGRATION` |
| `source_reference` | Khóa sự kiện ở hệ thống nguồn | `partner-event-927` |
| `request_id` | Định danh yêu cầu nghiệp vụ để phát hiện gửi lặp | UUID của một thao tác |
| `correlation_id` | Gom các bước xử lý của nhiều dịch vụ vào cùng luồng truy vết | ID của request đầu vào |
| `reason_code` | Vì sao thay đổi được cho phép hoặc bắt buộc | `CUSTOMER_REQUEST`, `DATA_CORRECTION` |
| `entity_version` | Phiên bản trạng thái sau khi thay đổi | 7 |

Không phải hệ thống nào cũng cần đầy đủ các trường trên trong mọi bảng. Hãy chọn dữ liệu cần để **truy vết, điều tra và tuân thủ nghĩa vụ vận hành**. Một bảng nghiệp vụ có thể chỉ giữ metadata mới nhất; nhật ký thay đổi giữ lịch sử chi tiết hơn. Danh tính và nguồn phải được lấy từ **ngữ cảnh xác thực hoặc hệ thống nhận sự kiện đáng tin cậy**, không được tin trực tiếp chuỗi `updated_by` do client tự gửi.

### 2.1. Source of truth và lịch sử nguồn thay đổi

Nguồn hệ thống phát sinh một giá trị chưa chắc là nguồn **có thẩm quyền cuối cùng** cho giá trị đó. Ví dụ, đối tác cung cấp địa chỉ giao hàng qua webhook, nhưng Order có thể cần kiểm tra quyền đổi địa chỉ và trạng thái đơn trước khi chấp nhận. Nhật ký nên ghi “nhận đề nghị từ đối tác” và “Order đã chấp nhận/cập nhật” là hai sự kiện khác nhau khi nghiệp vụ yêu cầu.

Cũng cần phân biệt **người đề xuất**, **người phê duyệt** và **người thực thi** trong quy trình nhiều bước. Không ghi một thao tác chưa commit thành một thay đổi thành công chỉ vì đã nhận request.

## 3. Chọn mức độ theo dõi phù hợp

Có ba mức phổ biến, tăng dần về khả năng truy vết:

| Mức theo dõi | Lưu gì | Trả lời được | Giới hạn |
| --- | --- | --- | --- |
| **Metadata hiện tại** | `created_at`, `updated_at`, `created_by`, `updated_by`, `version` | Ai sửa gần nhất, khi nào, bản ghi có đổi không | Không biết đầy đủ các lần đổi trước đó |
| **Nhật ký kiểm toán (audit log)** | Một dòng cho mỗi thao tác được xác nhận, nguồn, tác nhân, thời gian, phiên bản, loại thay đổi | Chuỗi thao tác, nguồn gốc, mối liên hệ giữa yêu cầu và bản ghi | Nếu chỉ lưu metadata, không khôi phục được các giá trị cũ |
| **Lịch sử trạng thái / event log** | Snapshot, phiên bản dữ liệu hoặc sự kiện nghiệp vụ cần thiết để tái dựng | Giá trị tại các mốc lịch sử và quá trình tiến hóa | Tốn lưu trữ, phức tạp hơn về schema, bảo mật và đọc lịch sử |

Nếu yêu cầu là hiển thị “cập nhật lần cuối”, các trường metadata có thể đủ. Nếu cần giải thích tại sao số dư thay đổi hoặc đáp ứng truy xuất kiểm toán, thường phải lưu **lịch sử bất biến có kiểm soát**. Nếu cần khôi phục một giá trị bất kỳ tại thời điểm trước, nhật ký chỉ gồm `actor_id` và `updated_at` là chưa đủ; phải có dữ liệu trạng thái hoặc sự kiện để tái dựng.

## 4. Thiết kế lược đồ minh họa

Ví dụ sau dùng **PostgreSQL** để minh họa cú pháp `UUID`, `TIMESTAMPTZ` và `RETURNING`; khi dùng hệ quản trị khác cần đổi kiểu dữ liệu, hàm thời gian và câu lệnh tương ứng.

~~~sql
CREATE TABLE customer_profile (
    customer_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    change_source TEXT NOT NULL
);

CREATE TABLE customer_change_log (
    event_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    request_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CREATED', 'UPDATED', 'DELETED')),
    entity_version BIGINT NOT NULL CHECK (entity_version >= 1),
    actor_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (customer_id, request_id),
    UNIQUE (customer_id, entity_version)
);

CREATE INDEX idx_profile_updated_at
    ON customer_profile (updated_at);

CREATE INDEX idx_change_log_customer_recorded
    ON customer_change_log (customer_id, recorded_at DESC);
~~~

**Giải thích quyết định thiết kế:**

1. `created_at` được gán lúc tạo bản ghi và không thay đổi khi cập nhật. `updated_at` được cập nhật mỗi khi có thay đổi được chấp nhận. Tại lần tạo, hai giá trị có thể bằng nhau.
2. `version` tăng khi trạng thái thay đổi, dùng cho **optimistic locking**; thời gian chỉ phục vụ thông tin và phân tích.
3. `created_by` và `updated_by` mô tả tác nhân của bản ghi hiện tại. `change_source` là nguồn của **lần thay đổi gần nhất**, không phải toàn bộ lịch sử nguồn.
4. `customer_change_log` là lịch sử metadata. Khóa duy nhất theo `(customer_id, entity_version)` phát hiện ghi nhiều log cho cùng phiên bản; theo `(customer_id, request_id)` giúp chặn tác động lặp do cùng yêu cầu, nếu ứng dụng tuân thủ hợp đồng sử dụng request ID.
5. Bảng log không có khóa ngoại trực tiếp đến bảng hồ sơ để vẫn có thể giữ dấu vết sau một thao tác xóa vật lý hợp lệ. Điều này đòi hỏi chính sách bảo vệ, phân quyền, lưu giữ và xóa dữ liệu rõ ràng.
6. Chỉ tạo chỉ mục cho các truy vấn có nhu cầu thực tế. Chỉ mục trên `updated_at` giúp tìm bản ghi mới sửa nhưng tăng chi phí ghi; index của log giúp xem lịch sử từng khách hàng. Cần đo query plan và khối lượng ghi trước khi thêm nhiều index.

`TIMESTAMPTZ` của PostgreSQL lưu một thời điểm tuyệt đối và hiển thị theo múi giờ phiên kết nối; nó **không lưu riêng tên múi giờ gốc**. Nếu cần biết địa điểm hay múi giờ người dùng đã chọn, hãy lưu trường đó riêng. Dùng `Instant` ở Java cho các mốc tuyệt đối, rồi chuyển sang múi giờ của người dùng khi hiển thị.

**Lưu ý về dấu thời gian:** `CURRENT_TIMESTAMP` trong PostgreSQL biểu diễn thời điểm bắt đầu transaction, có thể giữ nguyên qua nhiều statement trong cùng transaction. `clock_timestamp()` lấy thời gian thực tế khi hàm được gọi. Lựa chọn phải thống nhất với định nghĩa nghiệp vụ; không dùng timestamp đơn thuần để phân xử thứ tự giao dịch, và không suy ra thời điểm commit tuyệt đối từ `updated_at`.

### 4.1. Quy ước cập nhật và xóa

Với lược đồ trên, mọi đường ghi phải tuân thủ cùng quy ước:

- **CREATE:** ghi phiên bản 1, `created_at`, `updated_at`, `created_by`, `updated_by`, và sự kiện `CREATED` trong cùng giao dịch.
- **UPDATE:** giữ nguyên `created_at`/`created_by`, tăng `version`, cập nhật metadata lần ghi gần nhất và thêm sự kiện `UPDATED`.
- **DELETE:** quyết định xóa mềm (`deleted_at`, `deleted_by`, trạng thái xóa) hoặc xóa vật lý theo nghiệp vụ. Nếu cần sự kiện `DELETED` với phiên bản tiếp theo, phải ghi log trước/trong cùng transaction xóa, theo quy tắc định danh phù hợp.
- **No-op:** nếu dữ liệu mới giống trạng thái cũ, cần quy định rõ có coi đó là một lần cập nhật hay không. Một cách thường dùng là không tăng version và không tạo log thay đổi nếu trạng thái thực tế không đổi, nhưng vẫn có thể lưu log *yêu cầu đã được nhận* ở nơi khác.

Quy ước cần được áp dụng cho cả API, batch job, import và migration. Chỉ thêm `updated_at` ở controller không bảo đảm tất cả đường ghi đều cập nhật trường này.

## 5. Ghi dữ liệu và lịch sử thay đổi trong cùng giao dịch

Giả sử khách hàng đổi tên hiển thị từ API. Ta muốn đảm bảo hai thay đổi **cùng thành công hoặc cùng thất bại**:

1. Cập nhật hàng trong `customer_profile` với điều kiện phiên bản hiện tại.
2. Ghi một hàng vào `customer_change_log` có đúng phiên bản sau cập nhật và metadata từ ngữ cảnh đáng tin cậy.

Nếu cập nhật được nhưng ghi audit thất bại, hệ thống sẽ mất dấu vết nguồn thay đổi. Ghi chúng trong **cùng transaction** giúp bảo đảm tính nguyên tử.

~~~mermaid
flowchart TB
    A["Yêu cầu đã xác thực / Job / Import"] --> B["Application service (Java)"]
    B --> C["Kiểm tra quyền và quy tắc nghiệp vụ"]
    C --> T["Transaction trong database"]
    T --> D["UPDATE hồ sơ nếu version khớp"]
    D --> E["INSERT nhật ký thay đổi"]
    E --> F{"Cả hai thành công?"}
    F -->|"Có"| G["COMMIT"]
    F -->|"Không"| H["ROLLBACK"]
    G --> I["Kết quả + event/outbox nếu cần"]
~~~

### 5.1. Câu lệnh cập nhật có điều kiện

~~~sql
UPDATE customer_profile
SET display_name = :display_name,
    updated_at = clock_timestamp(),
    updated_by = :actor_id,
    change_source = :source_kind,
    version = version + 1
WHERE customer_id = :customer_id
  AND version = :expected_version
RETURNING version, updated_at;
~~~

Nếu **không có hàng nào** được trả về, bản ghi không tồn tại hoặc phiên bản đã khác: ứng dụng không được ghi sự kiện `UPDATED` như thể cập nhật thành công. Cú pháp `:param` ở ví dụ này là ký hiệu dễ đọc; JDBC `PreparedStatement` thông thường dùng dấu `?`.

### 5.2. Ví dụ Java/JDBC

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;

record ChangeContext(String actorId, String sourceKind, UUID requestId) {}
record UpdateResult(long newVersion, Instant updatedAt) {}

public final class CustomerProfileWriter {
    private final DataSource dataSource;

    public CustomerProfileWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<UpdateResult> rename(
            UUID customerId, long expectedVersion,
            String newName, ChangeContext context) throws SQLException {

        // Application service phải xác thực actor, source và quyền trước khi gọi.
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                UpdateResult changed;
                try (PreparedStatement statement = connection.prepareStatement("""
                        UPDATE customer_profile
                        SET display_name = ?,
                            updated_at = clock_timestamp(),
                            updated_by = ?,
                            change_source = ?,
                            version = version + 1
                        WHERE customer_id = ? AND version = ?
                        RETURNING version, updated_at
                        """)) {
                    statement.setString(1, newName);
                    statement.setString(2, context.actorId());
                    statement.setString(3, context.sourceKind());
                    statement.setObject(4, customerId);
                    statement.setLong(5, expectedVersion);

                    try (ResultSet result = statement.executeQuery()) {
                        if (!result.next()) {
                            connection.rollback();
                            return Optional.empty();
                        }
                        changed = new UpdateResult(
                                result.getLong("version"),
                                result.getTimestamp("updated_at").toInstant()
                        );
                    }
                }

                try (PreparedStatement statement = connection.prepareStatement("""
                        INSERT INTO customer_change_log
                            (event_id, customer_id, request_id, action,
                             entity_version, actor_id, source_kind)
                        VALUES (?, ?, ?, 'UPDATED', ?, ?, ?)
                        """)) {
                    statement.setObject(1, UUID.randomUUID());
                    statement.setObject(2, customerId);
                    statement.setObject(3, context.requestId());
                    statement.setLong(4, changed.newVersion());
                    statement.setString(5, context.actorId());
                    statement.setString(6, context.sourceKind());
                    statement.executeUpdate();
                }

                connection.commit();
                return Optional.of(changed);
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Ví dụ minh họa **một thao tác UPDATE** dùng Java text block (Java 15+), PostgreSQL và JDBC. Các bước CREATE/DELETE cũng phải ghi log trong transaction, theo chính sách tương ứng. Để đưa vào sản phẩm thật, cần bổ sung kiểm tra dữ liệu đầu vào, quyền truy cập, quản lý transaction ở tầng ứng dụng, mapping lỗi và giới hạn timeout. `Optional.empty()` đang gộp hai tình huống “không tìm thấy bản ghi” và “xung đột phiên bản”; API hoàn chỉnh nên trả lỗi phù hợp sau khi kiểm tra có kiểm soát.

**Retry cần được thiết kế riêng:** ràng buộc `request_id` giúp ngăn hai log cho một yêu cầu nhưng chưa tự động trả lại kết quả cũ nếu client gửi lại sau khi `COMMIT` thành công mà phản hồi bị mất. Để idempotency hoàn chỉnh, ứng dụng phải tra cứu yêu cầu đã xử lý, kiểm tra payload tương ứng và trả lại kết quả đã lưu; không tạo request ID mới cho mỗi lần retry cùng thao tác nghiệp vụ. Lỗi mất kết nối trong lúc commit có thể khiến trạng thái thành công **không xác định từ phía client**; cần đối soát bằng request ID hoặc phiên bản.

## 6. Đồng thời và độ chính xác của “cập nhật lần cuối”

Hai người cùng mở phiên bản 4 của hồ sơ:

1. Người A gửi lệnh đổi tên với `expectedVersion = 4`.
2. Người B cũng gửi yêu cầu đổi tên từ phiên bản 4.
3. Yêu cầu đến database trước và được commit sẽ cập nhật thành phiên bản 5.
4. Yêu cầu còn lại không thể ghi đè phiên bản 5 bằng điều kiện `WHERE version = 4`; ứng dụng trả xung đột, đọc lại dữ liệu rồi để người dùng quyết định.

Nếu chỉ kiểm tra `updated_at` ở tầng Java rồi thực hiện `UPDATE` không điều kiện, một luồng có thể ghi đè thay đổi của luồng khác, gây **lost update**. Kiểm tra phiên bản ngay trong câu lệnh SQL giúp kiểm soát trường hợp này.

Khi cần lưu lịch sử thứ tự, `version` xác định chuỗi thay đổi của **một bản ghi**, nhưng không tự tạo một thứ tự toàn cục giữa nhiều bảng hoặc dịch vụ. Nếu hệ thống dùng event stream/outbox, cần thêm thông tin về aggregate, phiên bản và cách bảo đảm thứ tự xử lý cho từng aggregate. Một cột `recorded_at` không đủ giải quyết các vấn đề về thứ tự commit và truyền sự kiện.

## 7. Các cơ chế ghi lịch sử và nguồn thay đổi

Không có một cơ chế phù hợp cho mọi hệ thống. Hãy chọn theo mức độ chi tiết, số đường ghi và yêu cầu truy vết.

| Cơ chế | Cách hoạt động | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Application-managed audit** | Application service ghi trạng thái và log cùng transaction | Có ngữ cảnh nghiệp vụ, actor, lý do và request ID | Mọi đường ghi phải tuân thủ quy ước |
| **Database trigger** | Trigger chạy khi bảng bị INSERT/UPDATE/DELETE | Bao phủ nhiều đường SQL, kể cả thao tác ngoài ứng dụng | Khó biết actor nghiệp vụ nếu không truyền context an toàn; logic ẩn trong DB |
| **Change Data Capture (CDC)** | Đọc luồng thay đổi từ WAL/binlog hoặc cơ chế tương đương | Phát hiện thay đổi đã ghi trong database, hữu ích cho đồng bộ | Không tự biết lý do nghiệp vụ hoặc người khởi tạo; cần quản lý log retention, schema và lag |
| **Event sourcing** | Lưu chuỗi sự kiện nghiệp vụ làm nguồn chuẩn và dựng trạng thái từ sự kiện | Lịch sử hành vi nghiệp vụ rất rõ nếu sự kiện được mô hình tốt | Đòi hỏi thiết kế sự kiện, replay, versioning và sửa dữ liệu phức tạp |
| **Temporal/history tables** | DB hoặc ứng dụng lưu các phiên bản bản ghi theo thời gian | Dễ truy vấn trạng thái quá khứ khi được cấu hình đúng | Hỗ trợ thay đổi theo DB; vẫn cần ngữ cảnh actor/nguồn |

Ví dụ, CDC có thể phát hiện `display_name` đổi từ giá trị A sang B, nhưng không suy ra đáng tin cậy đây là yêu cầu của khách hàng hay thao tác sửa lỗi của quản trị viên. Nếu thông tin đó cần cho điều tra, hãy lưu context ở nơi ghi hoặc phát sự kiện nghiệp vụ chứa metadata đã xác thực.

### 7.1. Outbox giúp truyền thông tin nguồn thay đổi sang hệ thống khác

Khi cần thông báo cho dịch vụ tìm kiếm, phân tích hoặc cache, có thể ghi thêm một **outbox event** cùng transaction với bản ghi và audit. Tiến trình phát sự kiện đọc bản ghi outbox đã commit rồi gửi vào broker. Nếu gửi thất bại, nó có thể thử lại; người nhận phải xử lý được thông điệp lặp.

~~~mermaid
flowchart LR
    A["Java command"] --> DB[("Transaction: business row + audit + outbox")]
    DB --> P["Outbox publisher"]
    P --> Q["Message broker"]
    Q --> R["Read model / cache / analytics"]
~~~

Outbox và CDC có thể **bổ sung** cho audit, nhưng không mặc nhiên thay thế lịch sử nghiệp vụ. Nội dung outbox cần mang định danh sự kiện, aggregate, phiên bản, nguồn và correlation ID phù hợp, đồng thời tránh lộ dữ liệu cá nhân không cần thiết cho các bên nhận.

## 8. Dữ liệu nhập muộn, backfill và tiến hóa schema

Một batch import lịch sử có thể tạo bản ghi trong database hôm nay nhưng chứa giao dịch đã phát sinh từ năm trước. Nếu ghi `created_at` bằng thời gian lịch sử, người vận hành sẽ hiểu nhầm thời điểm hệ thống *tạo bản ghi*; nếu thay `occurred_at` bằng thời gian hiện tại, báo cáo nghiệp vụ sẽ sai.

Với dữ liệu nhập muộn, nên ghi:

- `occurred_at`: thời điểm sự kiện ở hệ thống nguồn.
- `ingested_at`: thời điểm ứng dụng tiếp nhận.
- `created_at`: thời điểm tạo bản ghi trong kho hiện tại.
- `source_kind`, `source_reference`: hệ thống nguồn và khóa đối soát.

Khi thêm các cột này vào bảng đang hoạt động, cần thực hiện migration thận trọng:

1. **Mở rộng schema:** thêm cột mới, ban đầu có thể cho phép NULL để không làm hỏng phiên bản ứng dụng đang chạy.
2. **Bổ sung logic ghi:** tất cả đường ghi mới điền metadata đúng nguồn, tránh giá trị mặc định giả như `updated_by = 'system'` cho mọi thao tác.
3. **Backfill dữ liệu cũ:** chỉ điền những giá trị có bằng chứng từ log hoặc hệ nguồn. Nếu không biết chính xác thời điểm hoặc actor, dùng NULL hoặc trạng thái “không xác định” theo hợp đồng dữ liệu; không gán bừa thời gian migration thành thời gian tạo thực tế.
4. **Kiểm chứng:** so sánh số bản ghi, tính hợp lệ của các mốc và nguồn, đo ảnh hưởng tới tốc độ ghi và chỉ mục.
5. **Siết ràng buộc:** sau khi tất cả đường ghi và dữ liệu cũ đã đạt điều kiện, mới áp dụng `NOT NULL`, index hoặc quy định mới.

Một bản ghi được import trong quá trình migration có thể cần cả **thời gian gốc** và **thời gian đưa vào hệ thống**. Hãy ghi rõ ý nghĩa để không trộn số liệu lịch sử với số liệu hoạt động hiện tại.

## 9. Bảo mật, độ tin cậy và lưu giữ nhật ký

Nhật ký thay đổi thường là dữ liệu nhạy cảm: nó có thể tiết lộ danh tính người dùng, lịch sử chỉnh sửa hồ sơ, mã giao dịch và thông tin vận hành. Vì vậy, phải thiết kế bảo vệ ngay từ đầu:

- **Xác thực nguồn:** lấy `actor_id` và `source_kind` từ ngữ cảnh server đã kiểm chứng; phân biệt người dùng với service account. Với webhook, phải xác minh chữ ký, token hoặc cơ chế xác thực được thống nhất.
- **Quyền truy cập:** hạn chế ai được đọc toàn bộ lịch sử; tài khoản ứng dụng chỉ có quyền ghi phù hợp; không cấp quyền sửa/xóa log tùy tiện.
- **Tính toàn vẹn:** ưu tiên log dạng append-only, ràng buộc định danh, sao lưu, theo dõi can thiệp trái phép; với yêu cầu kiểm toán cao có thể dùng kho lưu trữ bất biến, chữ ký hoặc chuỗi hash theo thiết kế đã kiểm chứng.
- **Tối thiểu hóa dữ liệu:** không ghi mật khẩu, token, khóa bí mật, thông tin thanh toán nhạy cảm hay toàn bộ payload nếu không cần. Nếu cần lưu before/after, định nghĩa field được phép, mã hóa và kiểm soát truy cập theo trường hợp sử dụng.
- **Retention và xóa dữ liệu:** quy định thời gian lưu, cách lưu trữ dài hạn và xử lý yêu cầu xóa dữ liệu cá nhân theo nghĩa vụ áp dụng. Audit không phải lý do để giữ mọi dữ liệu vô thời hạn.
- **Khả năng khôi phục:** sao lưu đồng bộ dữ liệu nghiệp vụ và dữ liệu kiểm toán với một điểm phục hồi nhất quán. Khi restore, đối soát version, nhật ký, outbox và các hệ thống đã nhận sự kiện trước đó.

Đừng đồng nhất **application log** với **audit log**: log kỹ thuật phục vụ debug thường có thời hạn ngắn, có thể mất dòng, bị lọc hoặc chứa lỗi nhạy cảm; audit phục vụ truy vết nghiệp vụ cần hợp đồng cấu trúc, độ bền và quyền truy cập được xác định.

## 10. Tra cứu và giám sát lịch sử thay đổi

Những câu hỏi vận hành điển hình là “bản ghi vừa được sửa bởi nguồn nào?” hoặc “trong 24 giờ gần đây có bao nhiêu cập nhật từ batch import?”. Tùy nhu cầu, có thể truy vấn bảng trạng thái và bảng log:

~~~sql
-- Bản ghi được cập nhật gần đây:
SELECT customer_id, updated_at, updated_by, change_source, version
FROM customer_profile
WHERE updated_at >= :from_time
ORDER BY updated_at DESC;

-- Lịch sử một khách hàng theo phiên bản:
SELECT entity_version, action, actor_id, source_kind,
       request_id, recorded_at
FROM customer_change_log
WHERE customer_id = :customer_id
ORDER BY entity_version DESC;

-- Số thay đổi theo nguồn trong một khoảng thời gian:
SELECT source_kind, COUNT(*) AS change_count
FROM customer_change_log
WHERE recorded_at >= :from_time
  AND recorded_at < :to_time
GROUP BY source_kind;
~~~

Trong JDBC, các tham số ở ví dụ SQL tương ứng với giá trị bind bằng `PreparedStatement`, tránh ghép chuỗi từ dữ liệu người dùng. Với bảng audit tăng nhanh, cân nhắc index theo truy vấn thật, partition theo thời gian, lưu trữ lạnh và retention đã định; tránh scan toàn bảng trong luồng API.

Các chỉ số đáng theo dõi gồm: tỷ lệ cập nhật xung đột phiên bản, tỷ lệ lỗi ghi audit, số request ID trùng, độ trễ giữa `occurred_at` và `ingested_at`, độ trễ outbox/CDC, số event chưa xử lý và số bản ghi thiếu nguồn thay đổi. Các phép đo giúp phân biệt lỗi ghi thực sự với dữ liệu chậm đồng bộ ở mô hình đọc.

## 11. Tình huống thực hành

Một đơn hàng có trạng thái “đã thanh toán” trong bảng chính, còn hệ thống chăm sóc khách hàng vẫn thấy “đang chờ”. Trên bảng đơn hàng:

| Trường | Giá trị minh họa |
| --- | --- |
| `order_id` | `ORD-205` |
| `status` | `PAID` |
| `updated_at` | 10:05:13 UTC |
| `updated_by` | `service:payment-consumer` |
| `change_source` | `WEBHOOK` |
| `version` | 9 |

Nhật ký audit ghi bản cập nhật phiên bản 9 với `request_id` của webhook. Mô hình đọc chăm sóc khách hàng mới nhận đến phiên bản 8.

**Cách phân tích:**

1. Xác định Order là nguồn có thẩm quyền cho trạng thái đơn hàng; mô hình đọc hỗ trợ hiển thị nên có thể trễ.
2. Đối chiếu `version = 9` trong audit với phiên bản mà mô hình đọc đã áp dụng. Không kết luận dựa riêng vào timestamp.
3. Truy vết `request_id` và `correlation_id` qua outbox, broker, consumer; kiểm tra event chưa phát, xử lý lỗi hoặc trùng.
4. Chỉ cho mô hình đọc áp dụng sự kiện hợp lệ theo quy tắc thứ tự phiên bản. Nếu thiếu sự kiện, phát lại hoặc tái dựng từ nguồn có thẩm quyền theo quy trình đáng tin cậy.
5. Nếu audit cho biết payment webhook được xử lý hai lần, kiểm tra ràng buộc idempotency và chính sách retry; xác minh sự kiện nghiệp vụ chỉ làm thay đổi trạng thái một lần.

**Câu hỏi tự kiểm tra:** Nếu có bản ghi `updated_at = 10:05:13` nhưng không có `updated_by` hoặc `request_id`, có thể khẳng định ai đã thay đổi không? Không: timestamp không chứng minh danh tính, mục đích hay đường đi của thao tác. Nếu audit log chỉ lưu “UPDATED” nhưng không lưu giá trị cũ, có thể dựng lại tên cũ từ log không? Không: cần snapshot, các phiên bản trạng thái hoặc sự kiện mang thông tin đủ để tái dựng.

## 12. Checklist thiết kế trước khi triển khai

- [ ] Đã định nghĩa rõ `created_at`, `updated_at`, `occurred_at`, `ingested_at`, `effective_at` khi có dùng.
- [ ] Có quy tắc thời gian tuyệt đối, UTC/múi giờ hiển thị, nguồn đồng hồ và độ phân giải.
- [ ] Xác định actor, nguồn, request ID và correlation ID từ ngữ cảnh đã được kiểm chứng.
- [ ] Mỗi đường ghi CREATE/UPDATE/DELETE áp dụng cùng quy ước metadata và audit.
- [ ] Audit và thay đổi nghiệp vụ được ghi nguyên tử khi yêu cầu toàn vẹn đòi hỏi.
- [ ] Version/locking bảo vệ khỏi lost update; timestamp không được dùng thay điều kiện đồng thời.
- [ ] Retry và trường hợp kết nối đứt tại thời điểm commit có đường đối soát theo định danh.
- [ ] Đã chọn mức lịch sử phù hợp: metadata hiện tại, audit metadata, snapshot hoặc event log.
- [ ] Có chỉ mục, retention, backup/restore, quyền truy cập và quy trình xử lý dữ liệu nhạy cảm.
- [ ] Migration/backfill không biến dữ liệu “không biết” thành thông tin thời gian hoặc danh tính tưởng như chính xác.

**Ghi nhớ:** Theo dõi vòng đời dữ liệu cần kết hợp **thời gian**, **tác nhân**, **nguồn**, **định danh yêu cầu** và **phiên bản**. `created_at`/`updated_at` giúp biết trạng thái gần nhất; audit được ghi bền vững trong cùng giao dịch giúp giải thích chuỗi thay đổi; lịch sử đầy đủ hoặc event log mới hỗ trợ tái dựng giá trị cũ. Một ranh giới persistence tốt trong Java luôn làm rõ ý nghĩa của từng thông tin này và cách kiểm chứng khi hệ thống gặp lỗi.
