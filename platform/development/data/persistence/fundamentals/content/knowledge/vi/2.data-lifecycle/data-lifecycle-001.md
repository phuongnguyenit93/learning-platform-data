# Tạo, đọc, cập nhật và xóa trong vòng đời một bản ghi

## 1. Nhìn CRUD như một vòng đời dữ liệu

Trong ứng dụng Java, CRUD là bốn thao tác nền tảng đối với dữ liệu bền vững:

- **Create (tạo):** sinh một bản ghi hợp lệ và lưu lại để những phiên làm việc khác có thể dùng.
- **Read (đọc):** truy xuất bản ghi hiện có theo một định danh hoặc tiêu chí tìm kiếm.
- **Update (cập nhật):** thay đổi trạng thái có kiểm soát mà vẫn giữ danh tính của bản ghi.
- **Delete (xóa):** loại bản ghi khỏi tập dữ liệu đang hoạt động, hoặc xóa vật lý khỏi kho lưu trữ nếu chính sách cho phép.

Điểm quan trọng: bốn thao tác này là **các hành động**, còn *vòng đời dữ liệu* là toàn bộ quá trình một bản ghi được tạo ra, sử dụng, thay đổi, ngừng sử dụng và cuối cùng được lưu trữ lâu dài hoặc loại bỏ. Một ứng dụng tốt phải giải thích được trạng thái của bản ghi **trước và sau mỗi hành động**, cũng như hành vi khi yêu cầu thất bại, trùng lặp hay được thực hiện đồng thời.

Bài học thuộc chương **Vòng đời dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Từ ví dụ CRUD tối thiểu, người học sẽ nhìn thấy mối liên hệ với lựa chọn mô hình dữ liệu và lược đồ, truy vấn và chỉ mục, ranh giới persistence trong Java, giao dịch, cô lập, đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Các phần này xuất hiện tại đúng nơi chúng ảnh hưởng đến vòng đời của **một bản ghi**.

### Ví dụ xuyên suốt: công việc trong ứng dụng quản lý nhiệm vụ

Một công việc có tiêu đề, mô tả, trạng thái và thời gian cập nhật. Người dùng có thể tạo công việc, xem lại, đổi tiêu đề, đánh dấu hoàn thành và xóa. Hệ thống cần trả lời:

1. Khi tạo, làm cách nào để hai yêu cầu khác nhau không vô tình có cùng khóa chính?
2. Khi đọc, công việc đã xóa mềm có được trả về hay không?
3. Khi hai người sửa cùng công việc, làm thế nào tránh người đến sau ghi đè thay đổi của người trước?
4. Nếu việc xóa chỉ là đánh dấu, dữ liệu nào vẫn còn trong cơ sở dữ liệu?
5. Nếu mất kết nối ngay sau thao tác ghi, client có chắc thao tác thất bại không?

Ta sẽ dùng cơ sở dữ liệu quan hệ, SQL gần với **PostgreSQL** và Java/JDBC để trả lời. Các cú pháp như `GENERATED ALWAYS AS IDENTITY`, `TIMESTAMPTZ`, `RETURNING` và chỉ mục có điều kiện có thể khác ở hệ quản trị khác.

## 2. Trạng thái nghiệp vụ và trạng thái lưu trữ là hai chiều khác nhau

Một bản ghi công việc có thể đi qua các trạng thái nghiệp vụ:

```text
TODO ──bắt đầu──> IN_PROGRESS ──hoàn tất──> DONE
  └────────────────đánh dấu hoàn tất─────────┘
```

Trong khi đó, bản ghi có vòng đời lưu trữ:

```text
Chưa tồn tại --CREATE--> Đang hoạt động --DELETE mềm--> Đã ẩn
                            ^                         |
                            └---------khôi phục-------┘
                                  (nếu chính sách cho phép)

Đã ẩn --xóa vĩnh viễn theo chính sách--> Không còn bản ghi trong bảng
```

Một công việc có `status = 'DONE'` **không đồng nghĩa** với đã bị xóa. Công việc đã hoàn tất vẫn có thể được tìm thấy, thống kê và chỉnh sửa theo quyền hạn. Ngược lại, `deleted_at IS NOT NULL` thường có nghĩa nó bị ẩn khỏi những truy vấn nghiệp vụ bình thường, dù vẫn còn trên ổ đĩa.

Để thiết kế CRUD chính xác, hãy xác định trước:

| Khía cạnh | Câu hỏi cần chốt |
| --- | --- |
| Danh tính | Khóa định danh nào không thay đổi khi sửa tên/trạng thái? |
| Dữ liệu bắt buộc | Trường nào không thể để trống, giá trị nào bị cấm? |
| Trạng thái | Những chuyển trạng thái nghiệp vụ nào được phép? |
| Quyền truy cập | Ai được tạo, xem, sửa, xóa hay khôi phục? |
| Xóa | Xóa mềm hay xóa vật lý; có thời hạn giữ dữ liệu không? |
| Đồng thời | Cập nhật được bảo vệ bằng khóa, phiên bản hay điều kiện nào? |
| Truy vết | Cần biết ai làm gì, lúc nào, với dữ liệu nào? |
| Lỗi | Khi một thao tác không hoàn tất rõ ràng, client phải làm gì? |

## 3. Thiết kế bảng và các bất biến ngay từ đầu

Lược đồ dưới đây giữ một hàng cho mỗi công việc. `id` là khóa chính; `version` phục vụ kiểm soát cập nhật đồng thời; `deleted_at` phục vụ xóa mềm.

```sql
CREATE TABLE tasks (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    description TEXT,
    status      VARCHAR(20) NOT NULL DEFAULT 'TODO',
    version     BIGINT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMPTZ,

    CONSTRAINT ck_tasks_title_not_blank CHECK (length(btrim(title)) > 0),
    CONSTRAINT ck_tasks_status CHECK (
        status IN ('TODO', 'IN_PROGRESS', 'DONE')
    ),
    CONSTRAINT ck_tasks_version CHECK (version >= 0)
);
```

Đây là những nguyên tắc nền:

- **Khóa chính bất biến:** dùng `id` để nhận diện bản ghi. Tiêu đề có thể bị đổi hoặc trùng giữa nhiều công việc nên không phù hợp làm định danh.
- **Quy tắc ngay trong DB:** `NOT NULL`, `CHECK` và khóa chính bảo vệ dữ liệu kể cả khi một luồng ghi không đi qua giao diện Java.
- **Mặc định có chủ đích:** trạng thái mới là `TODO`; phiên bản mới bằng `0`; thời gian tạo/cập nhật được khởi tạo từ DB.
- **Xóa mềm là một trạng thái dữ liệu:** `deleted_at` rỗng nghĩa là đang hoạt động; có giá trị nghĩa là đã xóa mềm.
- **Dấu thời gian không thay thế phiên bản:** `updated_at` giúp quan sát, nhưng so sánh thời gian có thể không đủ tin cậy để phát hiện mọi xung đột; `version` là tín hiệu chuyên dụng.
- **Ràng buộc bảng chưa đủ cho mọi luật:** `CHECK` xác nhận giá trị `status` hợp lệ, nhưng không thể tự xác nhận liệu chuyển từ `DONE` về `TODO` có được nghiệp vụ cho phép hay không. Quy tắc chuyển trạng thái phải được thực thi bởi logic thích hợp, có xét đến đồng thời.

Với hệ thống nhiều người dùng, có thể cần thêm `owner_id` hoặc `tenant_id` và bộ lọc/kiểm soát quyền tương ứng. Ví dụ này lược bớt để tập trung vào vòng đời một bản ghi; mã thật phải đưa phạm vi người dùng vào truy vấn hoặc dùng cơ chế kiểm soát truy cập nhất quán.

## 4. Create — tạo bản ghi mới

### Đầu vào, kiểm tra và kết quả

Khi nhận yêu cầu tạo, ứng dụng nên:

1. Xác thực quyền tạo công việc và kiểm tra tiêu đề không rỗng, đúng độ dài.
2. Chuẩn hóa dữ liệu nếu nghiệp vụ yêu cầu, ví dụ loại bỏ khoảng trắng thừa ở đầu/cuối tiêu đề.
3. Chỉ cho phép client đưa vào các trường hợp lệ như `title` và `description`. Không để client tự đặt `id`, `version`, `created_at` hay `deleted_at`.
4. Ghi một hàng qua câu lệnh tham số hóa.
5. Nhận khóa định danh do DB sinh, trả về tài nguyên đã được tạo hoặc ít nhất là `id`.

Ví dụ với PostgreSQL:

```sql
INSERT INTO tasks (title, description)
VALUES ('Viết tài liệu JDBC', 'Hoàn thiện ví dụ CRUD cho nhóm')
RETURNING id, title, status, version, created_at;
```

Bản ghi sau khi tạo có `status = 'TODO'`, `version = 0` và `deleted_at = NULL`. Vì DB sinh ID, hai yêu cầu tạo độc lập không được dựa vào một biến đếm trong bộ nhớ Java. Khi cần **một yêu cầu logic chỉ tạo một bản ghi**, ID duy nhất là chưa đủ: client retry có thể tạo hai hàng khác ID. Hãy dùng khóa chống lặp yêu cầu (`idempotency_key`) có ràng buộc `UNIQUE` và lưu kết quả trong cùng phạm vi giao dịch nếu nghiệp vụ cần chống tạo trùng.

### Các lỗi cần tính đến

| Trường hợp | Cách xử lý |
| --- | --- |
| Tiêu đề rỗng hoặc quá dài | Trả lỗi dữ liệu đầu vào; DB vẫn là lớp bảo vệ sau cùng |
| Vi phạm ràng buộc DB | Dịch thành lỗi có ý nghĩa, không trả nguyên câu SQL/bí mật cho client |
| Không lấy được kết nối | Trả lỗi tạm thời, theo dõi pool/DB; chỉ retry có kiểm soát |
| Mất phản hồi sau khi DB ghi thành công | Xem kết quả là có thể chưa xác định; đối chiếu bằng khóa chống lặp hoặc mã nghiệp vụ |

**Thực hành:** tạo hai công việc có cùng tiêu đề. Xác nhận chúng có hai `id` khác nhau và cùng phiên bản ban đầu là `0`.

## 5. Read — đọc đúng bản ghi, đúng phạm vi và đúng trạng thái

Có hai dạng đọc thường gặp:

**Đọc theo định danh:** trả về một công việc cụ thể.

```sql
SELECT id, title, description, status, version, created_at, updated_at
FROM tasks
WHERE id = 42 AND deleted_at IS NULL;
```

**Đọc danh sách:** áp dụng bộ lọc, thứ tự ổn định và phân trang.

```sql
SELECT id, title, status, version, updated_at
FROM tasks
WHERE deleted_at IS NULL
  AND status = 'TODO'
ORDER BY updated_at DESC, id DESC
LIMIT 20;
```

Một bản ghi không xuất hiện có thể do nhiều nguyên nhân: không tồn tại, đã bị xóa mềm hoặc người dùng không có quyền xem. API có thể cố ý trả cùng một phản hồi `404` cho các trường hợp này để tránh tiết lộ sự tồn tại của tài nguyên.

**Đọc không nên gây tác dụng phụ đối với bản ghi được đọc.** Nếu nghiệp vụ thực sự cần ghi nhận lần xem, hãy gọi đó là một hành vi ghi riêng, tránh để một thao tác `getById` âm thầm thay đổi trạng thái.

Các điểm cần lưu ý:

- Truy vấn phải lọc đúng phạm vi quyền; riêng `WHERE id = ?` là không đủ trong hệ thống nhiều tài khoản.
- Chỉ lấy các cột cần dùng. Dữ liệu nhạy cảm không nên được trả về chỉ vì tồn tại trong bảng.
- Đặt `LIMIT` và thứ tự rõ ràng cho danh sách; đối với dữ liệu lớn nên cân nhắc phân trang theo con trỏ, ví dụ dựa trên cặp `(updated_at, id)`.
- Khóa chính thường đã có chỉ mục; bộ lọc danh sách có thể cần chỉ mục riêng nếu đã đo được truy vấn chậm.
- Một lần đọc chỉ phản ánh trạng thái mà mức cô lập của DB cho phép tại thời điểm đọc. Dữ liệu có thể thay đổi ngay sau khi câu `SELECT` kết thúc.

**Thực hành:** đọc công việc vừa tạo theo `id`, đọc danh sách `TODO`, rồi kiểm tra phản hồi đối với `id` không tồn tại.

## 6. Update — thay đổi dữ liệu mà không ghi đè ngoài ý muốn

### Thay đổi có điều kiện

Lệnh cập nhật đơn giản:

```sql
UPDATE tasks
SET title = 'Viết tài liệu JDBC hoàn chỉnh',
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42;
```

Lệnh này hợp lệ về cú pháp nhưng chưa giải quyết hai vấn đề: nó có thể sửa bản ghi đã xóa mềm và có thể **ghi đè** thay đổi của người khác. Một bản ghi được đọc ở phiên bản `3` nên chỉ được cập nhật khi DB vẫn đang giữ phiên bản đó.

```sql
UPDATE tasks
SET title = 'Viết tài liệu JDBC hoàn chỉnh',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42
  AND version = 3
  AND deleted_at IS NULL
RETURNING id, version, updated_at;
```

Nếu một hàng được cập nhật, thao tác thành công và phiên bản trở thành `4`. Nếu không có hàng nào:

- Bản ghi có thể không tồn tại.
- Bản ghi có thể đã bị xóa mềm.
- Một yêu cầu khác có thể đã thay đổi phiên bản.

Ứng dụng nên kiểm tra thêm theo quyền và chính sách để phân biệt `404` với lỗi xung đột `409` (hoặc `412 Precondition Failed` nếu dùng HTTP `If-Match`). **Đừng coi kết quả 0 hàng là thành công** khi hợp đồng API yêu cầu phát hiện xung đột.

### Vì sao cần `version`?

Giả sử A và B cùng đọc bản ghi `version = 3`:

```text
A đọc v3: title = "Viết hướng dẫn"
B đọc v3: title = "Viết hướng dẫn"
A đổi title -> "Viết hướng dẫn JDBC", UPDATE WHERE version = 3 -> thành công, v4
B đổi title -> "Viết hướng dẫn JPA",  UPDATE WHERE version = 3 -> 0 hàng
B nhận thông báo dữ liệu đã thay đổi, phải đọc lại và quyết định
```

Đây là **optimistic locking**: không khóa hàng suốt thời gian người dùng chỉnh sửa, nhưng bắt buộc kiểm tra phiên bản tại thời điểm ghi. Kiểm tra phiên bản bằng một câu `SELECT` riêng rồi chạy `UPDATE` không điều kiện là chưa đủ, vì dữ liệu có thể thay đổi giữa hai câu lệnh. Điều kiện `version = ?` phải nằm trong chính câu ghi (hoặc dùng một cơ chế khóa/giao dịch tương đương).

Nếu cần chuyển trạng thái có luật nghiệp vụ, hãy kiểm tra trạng thái đầu vào **cùng với thao tác cập nhật**:

```sql
-- Chỉ cho phép bắt đầu công việc đang ở TODO, phiên bản 4.
UPDATE tasks
SET status = 'IN_PROGRESS',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42
  AND status = 'TODO'
  AND version = 4
  AND deleted_at IS NULL;
```

Thứ tự các trạng thái và những bước được phép bỏ qua là quyết định nghiệp vụ. Mã ví dụ cho phép đi từ `TODO` sang `IN_PROGRESS`; ứng dụng thực tế cần định nghĩa những chuyển đổi khác một cách tường minh.

### Cập nhật toàn bộ hay từng phần?

Với API, cần phân biệt:

- `PUT` thường biểu diễn **thay thế biểu diễn tài nguyên** theo hợp đồng API; client phải gửi đầy đủ các trường mà API coi là có thể thay thế.
- `PATCH` biểu diễn **thay đổi một phần**; trường vắng mặt và trường được gửi với giá trị `null` có thể mang ý nghĩa khác nhau.
- `UPDATE tasks SET title = ?` là cập nhật một trường trong DB; nó không tự quyết định phương thức HTTP hay ý nghĩa `null`.

Không biến đối tượng request thành một danh sách cột cập nhật tùy ý. Chỉ chấp nhận các trường cho phép sửa và kiểm tra quy tắc nghiệp vụ; tránh lỗi *mass assignment* khiến client sửa được quyền sở hữu, phiên bản hoặc dấu xóa.

**Thực hành:** đọc một công việc ở `version = 0`, sửa thành `version = 1` rồi cố cập nhật lần nữa với `version = 0`. Lần thứ hai phải không làm thay đổi bản ghi.

## 7. Delete — xóa mềm, xóa vật lý và khôi phục

### Xóa mềm

Xóa mềm giữ hàng trong DB nhưng loại nó khỏi truy vấn hoạt động thông thường:

```sql
UPDATE tasks
SET deleted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = 42
  AND version = 4
  AND deleted_at IS NULL;
```

Với xóa mềm:

- Truy vấn đọc/danh sách phải **nhất quán** lọc `deleted_at IS NULL`.
- Cập nhật hoạt động bình thường cũng cần từ chối bản ghi đã xóa.
- Chỉ người có quyền thích hợp mới được đọc bản ghi đã xóa hoặc khôi phục.
- Dữ liệu vẫn còn trong DB, vẫn chiếm dung lượng và vẫn chịu các quy định bảo mật/giữ dữ liệu.
- Ràng buộc duy nhất cần được thiết kế có chủ đích: bản ghi xóa mềm vẫn có thể chiếm giá trị `UNIQUE`. Một số DB hỗ trợ chỉ mục duy nhất có điều kiện cho các hàng chưa xóa; phải kiểm tra tác động nếu cho phép tạo lại dữ liệu cùng khóa nghiệp vụ.

Khôi phục (nếu yêu cầu nghiệp vụ cho phép) là một thay đổi trạng thái lưu trữ riêng:

```sql
UPDATE tasks
SET deleted_at = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = 42
  AND version = 5
  AND deleted_at IS NOT NULL;
```

Ứng dụng phải kiểm tra xem việc khôi phục có vi phạm ràng buộc với những dữ liệu được tạo sau khi xóa hay không.

### Xóa vật lý

```sql
DELETE FROM tasks
WHERE id = 42;
```

Sau xóa vật lý, hàng không còn nằm trong bảng. Tuy nhiên, điều đó **không đồng nghĩa** mọi bản sao của dữ liệu đã lập tức biến mất: bản sao lưu, nhật ký, replica, cache hay hệ thống nhận dữ liệu có thể vẫn giữ thông tin theo cơ chế riêng. Nếu bảng khác tham chiếu đến bản ghi, khóa ngoại có thể chặn xóa hoặc áp dụng hành vi `ON DELETE` đã định nghĩa. Chọn `CASCADE` phải dựa trên quan hệ sở hữu dữ liệu và tác động nghiệp vụ, không dùng tùy tiện để “xóa cho được”.

Xóa mềm phù hợp khi cần hiển thị thùng rác, khôi phục hoặc điều tra thay đổi; xóa vật lý phù hợp khi thực sự phải loại bản ghi theo chính sách hoặc khi đã hết thời gian lưu giữ. Thời hạn lưu và quy trình dọn dẹp phải xuất phát từ yêu cầu cụ thể, không tự áp một con số mặc định.

### Idempotency của Delete

Lặp lại yêu cầu xóa một tài nguyên đã xóa không nên gây xóa nhầm đối tượng khác. Một API có thể trả `204` cho cả yêu cầu xóa lần đầu và yêu cầu xóa lặp lại, hoặc trả `404` cho lần sau theo hợp đồng; tính idempotent nói về **trạng thái cuối**, không yêu cầu mọi phản hồi HTTP phải giống nhau. Với optimistic locking, yêu cầu có phiên bản cũ có thể bị trả xung đột để báo client biết bản ghi đã thay đổi.

**Thực hành:** xóa mềm công việc, xác nhận API đọc thông thường không trả về nó nhưng truy vấn dành cho quản trị vẫn thấy `deleted_at`. Sau đó thử khôi phục theo phiên bản phù hợp.

## 8. Đưa CRUD vào Java qua ranh giới persistence

Ứng dụng Java thường tách ít nhất ba trách nhiệm:

```text
Controller / API
    ↓ nhận yêu cầu, xác thực, kiểm tra đầu vào
Application service
    ↓ luật nghiệp vụ, quyền, transaction boundary
TaskRepository (persistence boundary)
    ↓ JDBC, SQL, ánh xạ hàng, lỗi DB
DataSource / Connection pool
    ↓
Cơ sở dữ liệu
```

Ví dụ JDBC sau sử dụng `DataSource`, `PreparedStatement` và optimistic locking. Đây là một repository tối giản để thấy thao tác và kết quả; mã ứng dụng cần bổ sung xác thực, phân quyền, DTO, phân loại lỗi và transaction manager khi một luồng nghiệp vụ gồm nhiều bước.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Optional;
import javax.sql.DataSource;

record Task(long id, String title, String status, long version) {}

public final class TaskRepository {
    private final DataSource dataSource;

    public TaskRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long create(String title, String description) throws SQLException {
        String sql = "INSERT INTO tasks (title, description) VALUES (?, ?)";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     sql, Statement.RETURN_GENERATED_KEYS)) {
            statement.setString(1, title);
            statement.setString(2, description);
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Không tạo được bản ghi");
            }
            try (ResultSet keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("DB không trả khóa của bản ghi mới");
                }
                return keys.getLong(1);
            }
        }
    }

    public Optional<Task> findActive(long id) throws SQLException {
        String sql = "SELECT id, title, status, version FROM tasks "
                   + "WHERE id = ? AND deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Task(
                        rows.getLong("id"),
                        rows.getString("title"),
                        rows.getString("status"),
                        rows.getLong("version")));
            }
        }
    }

    public boolean rename(long id, long expectedVersion, String newTitle)
            throws SQLException {
        String sql = "UPDATE tasks "
                   + "SET title = ?, version = version + 1, "
                   + "updated_at = CURRENT_TIMESTAMP "
                   + "WHERE id = ? AND version = ? AND deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, newTitle);
            statement.setLong(2, id);
            statement.setLong(3, expectedVersion);
            return statement.executeUpdate() == 1;
        }
    }

    public boolean softDelete(long id, long expectedVersion)
            throws SQLException {
        String sql = "UPDATE tasks "
                   + "SET deleted_at = CURRENT_TIMESTAMP, "
                   + "updated_at = CURRENT_TIMESTAMP, "
                   + "version = version + 1 "
                   + "WHERE id = ? AND version = ? AND deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setLong(2, expectedVersion);
            return statement.executeUpdate() == 1;
        }
    }
}
```

**Đọc mã theo hợp đồng, không chỉ theo câu lệnh:**

- `create` trả về ID do DB cấp. Ví dụ giả định driver hỗ trợ lấy generated keys và mỗi lần tạo một hàng. Một số hệ quản trị/driver cần cách lấy khóa khác.
- `findActive` trả `Optional.empty()` khi không có hàng đang hoạt động; không nên biến tình huống bình thường này thành lỗi kết nối.
- `rename` và `softDelete` trả `false` khi không cập nhật được hàng nào. **Service phải phân loại** không tồn tại, đã xóa hoặc sai phiên bản trước khi trả kết quả API; Boolean không tự nêu nguyên nhân.
- `PreparedStatement` truyền giá trị như tham số, tránh chắp chuỗi đầu vào trực tiếp vào SQL.
- `try-with-resources` bảo đảm đóng `ResultSet`, statement và trả kết nối về pool khi hoạt động hoàn tất.
- Với một lệnh ghi đơn lẻ và chế độ auto-commit do kết nối cung cấp, DB xử lý lệnh như một đơn vị giao dịch. Khi luồng nghiệp vụ gồm nhiều bước ghi liên quan, service phải điều phối **cùng một transaction** và rollback khi cần; gọi các hàm repository mỗi hàm tự lấy kết nối sẽ không tự tạo thành một giao dịch chung.

Có thể dùng JPA/Hibernate thay JDBC, nhưng hợp đồng và các bất biến vẫn phải rõ: bản ghi nào được phép đọc, điều kiện phiên bản khi cập nhật và chính sách xóa. Nếu dùng ORM, cần hiểu cách nó sinh SQL, flush, ánh xạ `@Version` và giữ transaction.

## 9. Giao dịch, lỗi kết nối và tính nhất quán trong CRUD

Một câu `INSERT` hoặc `UPDATE` có thể trông độc lập, nhưng luồng nghiệp vụ thường cần thêm bảng nhật ký thay đổi, thông tin người thực hiện hoặc thông báo để hệ thống khác xử lý. Nếu yêu cầu “tạo công việc” phải vừa thêm `tasks` vừa thêm `task_audit`, hai thay đổi nên nằm **trong cùng giao dịch** nếu đều ở một DB:

```text
BEGIN
  INSERT tasks ...
  INSERT task_audit ...
COMMIT
```

Nếu thao tác thứ hai lỗi, rollback tránh tạo công việc mà thiếu sự kiện audit bắt buộc. Ngược lại, gửi email hay gọi dịch vụ ngoài DB **không** tự được rollback cùng giao dịch DB; có thể dùng cơ chế outbox và người nhận chống xử lý trùng khi cần độ tin cậy cao.

Cần phân biệt kết quả thao tác:

| Kết quả quan sát được | Diễn giải và phản ứng |
| --- | --- |
| `INSERT` trả khóa, `commit` được xác nhận | Có thể trả thông tin bản ghi đã tạo |
| `SELECT` không có hàng | Trả kết quả không tìm thấy theo hợp đồng và phạm vi truy cập |
| `UPDATE` có điều kiện tác động 0 hàng | Kiểm tra không tồn tại/đã xóa/xung đột phiên bản |
| SQL vi phạm `CHECK` hoặc ràng buộc khác | Lỗi dữ liệu; phản ánh thành thông điệp nghiệp vụ |
| Deadlock hoặc serialization failure | Có thể thử lại **toàn bộ giao dịch** khi nghiệp vụ cho phép và có giới hạn |
| Timeout/mất kết nối lúc `commit` | Trạng thái ghi có thể chưa xác định; cần cơ chế đối chiếu/idempotency |
| DB tạm không truy cập được | Giới hạn timeout và số lần retry; không tạo vòng lặp vô hạn |

**Điểm dễ nhầm:** một HTTP request trả lỗi hoặc timeout không bảo đảm DB đã rollback. Có thể DB đã commit nhưng phản hồi trên mạng bị mất. Đặc biệt với Create, retry mù có thể sinh thêm bản ghi. Với Update kiểu `SET title = ?`, lặp lại trên một phiên bản cũ sẽ bị chặn nhờ điều kiện `version`, nhưng client cần đọc lại để hiểu kết quả cuối.

## 10. Cô lập và đồng thời: bản ghi không đứng yên giữa các thao tác

Các thao tác có thể xen kẽ theo thứ tự:

```text
Thời gian →
A: READ(v7) ---------------- UPDATE WHERE version = 7 → 1 hàng, v8
B: ------- READ(v7) -------- UPDATE WHERE version = 7 → 0 hàng
```

Nhờ điều kiện phiên bản trong câu ghi, ứng dụng phát hiện thay đổi đồng thời và tránh *lost update*. Nếu không có điều kiện hoặc cơ chế khóa tương đương, người B có thể vô tình ghi đè sửa đổi của người A.

Các cách bảo vệ cần chọn theo tình huống:

| Cách | Ý nghĩa | Phù hợp khi |
| --- | --- | --- |
| Optimistic locking (`version`) | Phát hiện xung đột khi ghi; client quyết định thử lại hay hợp nhất | Nhiều người đọc, ít người sửa cùng bản ghi |
| Cập nhật có điều kiện trong một SQL | DB kiểm tra bất biến ngay trong lệnh ghi | Trạng thái/đếm/số lượng thuộc một hàng |
| Khóa bi quan như `SELECT ... FOR UPDATE` | Giữ khóa hàng trong giao dịch khi ra quyết định | Cần phối hợp nhiều bước và chấp nhận chờ khóa |
| Mức cô lập cao hơn | Hạn chế một số hiện tượng khi giao dịch đồng thời | Luật đa hàng phức tạp, phải đánh giá chi phí và retry |

Mức cô lập của hệ quản trị cụ thể ảnh hưởng những gì một transaction nhìn thấy, nhưng không tự thay thế thiết kế điều kiện cập nhật. Không dựa vào việc “mới đọc xong” để giả định bản ghi vẫn y nguyên.

## 11. Chỉ mục, audit, bảo mật và sự tiến hóa của bản ghi

### Tối ưu truy vấn đúng nhu cầu

Tìm theo `id` thường tận dụng chỉ mục của khóa chính. Danh sách theo trạng thái và thời gian cập nhật có thể cân nhắc chỉ mục sau trên PostgreSQL khi kiểm tra `EXPLAIN` cho thấy cần:

```sql
CREATE INDEX idx_tasks_active_status_updated
ON tasks (status, updated_at DESC, id DESC)
WHERE deleted_at IS NULL;
```

Chỉ mục này phù hợp hơn với truy vấn lọc công việc đang hoạt động theo `status`, sắp xếp `updated_at` và `id`. Tuy nhiên, nó chiếm dung lượng và làm tăng chi phí `INSERT`/`UPDATE`/`DELETE`; mỗi lần đổi `updated_at` có thể phải cập nhật chỉ mục. Đo cả tải đọc lẫn tải ghi trước/sau khi thêm.

### Audit không đồng nghĩa với một cột thời gian

`created_at` và `updated_at` mô tả thời điểm; chúng không cho biết ai đã sửa trường nào, giá trị cũ là gì và vì sao. Nếu nghiệp vụ yêu cầu lịch sử, thiết kế bảng audit hoặc cơ chế sự kiện phù hợp với chính sách lưu trữ, quyền truy cập và giao dịch. Không coi việc ghi log ứng dụng là một lịch sử dữ liệu đáng tin cậy khi log có thể mất hoặc không giao dịch cùng bản ghi.

### Bảo mật trong từng bước CRUD

- **Create/Update:** giới hạn trường được phép ghi, dùng tham số hóa, kiểm tra dữ liệu đầu vào và quyền theo vai trò.
- **Read:** lọc theo chủ sở hữu/tenant khi có, chỉ trả trường cần thiết, tránh lộ sự tồn tại của bản ghi không có quyền xem.
- **Delete:** phân quyền xóa/khôi phục/xóa vĩnh viễn rõ ràng; cân nhắc nghĩa vụ giữ và xóa dữ liệu.
- **Kết nối:** cấp quyền DB tối thiểu, bảo vệ thông tin xác thực, thiết lập TLS và theo dõi lỗi bất thường.

### Thay đổi schema khi có dữ liệu cũ

Ví dụ bổ sung cột `priority`. Một thay đổi an toàn phải tính đến phiên bản ứng dụng cũ, giá trị mặc định, dữ liệu đã tồn tại và cách triển khai:

1. Thêm cột tương thích với phiên bản cũ, có thể tạm cho phép `NULL`.
2. Cập nhật ứng dụng mới để ghi/đọc cột mới; bổ sung dữ liệu cho hàng cũ theo lô.
3. Kiểm tra dữ liệu và chuyển hết ứng dụng sang phiên bản mới.
4. Sau khi bảo đảm tương thích, mới siết `NOT NULL`, ràng buộc hoặc bỏ cấu trúc cũ.

Đây là tiến hóa schema theo hướng mở rộng rồi thu hẹp. Với bảng lớn, thời gian khóa và chi phí backfill phải được kiểm tra trên DB tương ứng môi trường thực tế.

### Sao lưu và khôi phục

Xóa nhầm hoặc migration lỗi có thể cần phục hồi. Xác định mục tiêu mất dữ liệu cho phép (**RPO**) và thời gian phục hồi (**RTO**), sao lưu theo chính sách và **thử khôi phục** bằng quy trình lặp lại được. Xóa mềm là một tính năng nghiệp vụ, không thay thế cho backup; backup cũng không thay thế cho quyền truy cập và kiểm soát tính đúng đắn của thao tác.

## 12. Ánh xạ CRUD vào hợp đồng API

Nếu triển khai REST, một cách thiết kế nhất quán có thể là:

| Mục đích | Phương thức và đường dẫn | Kết quả thành công thường gặp | Điều kiện quan trọng |
| --- | --- | --- | --- |
| Tạo công việc | `POST /tasks` | `201 Created`, trả `id`/Location | Xác thực đầu vào; hỗ trợ chống lặp nếu cần |
| Đọc một công việc | `GET /tasks/{id}` | `200 OK` hoặc `404` | Không lộ bản ghi đã xóa/người dùng không được xem |
| Liệt kê công việc | `GET /tasks?status=TODO` | `200 OK`, danh sách có phân trang | Bộ lọc và thứ tự ổn định |
| Sửa từng phần | `PATCH /tasks/{id}` | `200 OK` hoặc `204` | Dùng phiên bản/`If-Match` để chống ghi đè |
| Xóa mềm | `DELETE /tasks/{id}` | `204 No Content` | Quyền xóa, idempotency, chính sách phiên bản |
| Khôi phục | `POST /tasks/{id}/restore` | Theo hợp đồng | Quyền và bất biến khi khôi phục |

Bảng trên là một lựa chọn thiết kế, không phải quy tắc bắt buộc cho mọi API. Đặc biệt, hãy thống nhất mã lỗi không tìm thấy/xung đột/đầu vào không hợp lệ, và cách client mang phiên bản bản ghi (ví dụ trường `version` hoặc HTTP `ETag` và `If-Match`).

## 13. Bài thực hành tổng hợp: đi trọn vòng đời một công việc

Thực hiện trên một DB thử nghiệm thật với một ứng dụng Java nhỏ. Tối thiểu cần có các thao tác tạo, đọc, sửa và xóa mềm, kèm truy vấn quản trị xem hàng đã xóa.

| Bước | Thao tác | Kết quả cần kiểm chứng |
| --- | --- | --- |
| 1 | Tạo công việc hợp lệ | Có `id`, `status = TODO`, `version = 0`, thời gian tạo |
| 2 | Tạo công việc tiêu đề rỗng | Bị từ chối, không sinh hàng không hợp lệ |
| 3 | Đọc theo `id` và liệt kê | Đúng dữ liệu, đúng bộ lọc, có phân trang |
| 4 | Hai client đọc cùng phiên bản rồi sửa | Chỉ một `UPDATE WHERE version` thành công |
| 5 | Thử sửa bằng phiên bản cũ | Không thay đổi bản ghi; service trả lỗi xung đột |
| 6 | Xóa mềm theo phiên bản đúng | `deleted_at` có giá trị, `version` tăng |
| 7 | Đọc/cập nhật bình thường sau xóa mềm | Không đọc/sửa được hàng đã ẩn |
| 8 | Khôi phục theo chính sách | Hàng trở lại danh sách hoạt động, phiên bản tăng |
| 9 | Mô phỏng lỗi kết nối hoặc timeout | Ứng dụng phân loại được lỗi; không retry vô hạn |
| 10 | Kiểm tra chỉ mục và sao lưu | Có bằng chứng đo truy vấn và thử đọc từ bản khôi phục |

Để kiểm tra dữ liệu, ngoài phản hồi API hãy truy vấn trực tiếp bảng thử nghiệm:

```sql
SELECT id, title, status, version, created_at, updated_at, deleted_at
FROM tasks
ORDER BY id;
```

Đừng đánh giá thành công chỉ vì nhận HTTP `200`. Hãy so sánh dữ liệu trước và sau từng thao tác, đặc biệt sau lỗi, xung đột hoặc thử lại.

### Câu hỏi tự đánh giá

1. Tại sao `title` không phải là lựa chọn tốt để làm khóa chính của công việc?
2. Vì sao xóa mềm phải được thể hiện nhất quán trong `SELECT` lẫn `UPDATE`?
3. Hai người cùng đọc `version = 5`. Câu SQL nào giúp ngăn cập nhật cũ ghi đè cập nhật mới?
4. Vì sao một `UPDATE` tác động 0 hàng có thể mang nhiều ý nghĩa khác nhau?
5. Khi `POST` trả timeout, dựa vào đâu để biết có được tạo bản ghi lần nữa hay không?
6. `updated_at` có thay thế được audit trail hoặc `version` không? Vì sao?
7. Khi nào nên dùng xóa vật lý và cần cân nhắc điều gì với bản sao lưu, khóa ngoại và dữ liệu liên quan?
8. Một chỉ mục có thể làm truy vấn đọc nhanh hơn nhưng khiến thao tác ghi chậm hơn như thế nào?

Nếu giải thích được mỗi bước bằng **điều kiện trước → thao tác → điều kiện sau**, chỉ ra cách DB giữ bất biến và tự tái hiện được trường hợp lỗi/đồng thời, người học đã có nền tảng vững để đi từ CRUD sang các chủ đề persistence sâu hơn: thiết kế giao dịch, kiểm soát đồng thời nhiều bản ghi, schema migration và vận hành hệ thống dữ liệu đáng tin cậy.
