# Thêm bản ghi và nhận kết quả định danh

## 1. Một lệnh thêm dữ liệu cần trả lời những gì?

Trong hệ thống lưu trữ bền vững, thao tác **thêm bản ghi** (*insert/create*) không chỉ là gửi dữ liệu từ Java xuống cơ sở dữ liệu. Một thao tác tạo có ích cần thiết lập được một tài nguyên mới, giữ các ràng buộc nghiệp vụ, nhận diện tài nguyên đó và báo kết quả rõ ràng cho người gọi.

Ví dụ: người dùng tạo phiếu hỗ trợ có tiêu đề `"Không đăng nhập được"`. Sau khi ứng dụng xác nhận thành công, người dùng muốn mở lại phiếu bằng một địa chỉ ổn định như `/tickets/1245`. Hệ thống phải trả lời:

1. Bản ghi có thật sự được **ghi bền vững** hay chỉ mới được gửi đến DB?
2. **ID do ai tạo**: người dùng, Java, cơ sở dữ liệu hay một dịch vụ định danh?
3. Làm sao lấy đúng ID của bản ghi vừa tạo khi nhiều yêu cầu cùng insert?
4. Nếu DB từ chối một trường bắt buộc hoặc khóa duy nhất, kết quả là gì?
5. Nếu kết nối mất ngay sau khi DB commit, retry có tạo hai phiếu không?
6. Nếu việc tạo còn phải ghi lịch sử hoặc bản ghi con, chúng có cùng thành công hoặc rollback không?

Bài thuộc chương **Thao tác dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Từ bài toán `INSERT`, người học sẽ thực hành lựa chọn mô hình dữ liệu và schema, truy vấn và chỉ mục, thiết kế ranh giới persistence trong Java, kiểm soát giao dịch và đồng thời, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và đánh giá hiệu năng.

### Sau bài này, cần làm được

- Giải thích sự khác nhau giữa **thành công khi thực thi câu INSERT**, **nhận ID**, và **commit thành công**.
- Viết `INSERT` có tham số; hiểu `DEFAULT`, `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` và ảnh hưởng của chúng đối với thao tác tạo.
- Nhận định danh vừa sinh bằng PostgreSQL `RETURNING` hoặc JDBC `getGeneratedKeys()`.
- Đưa nhiều lệnh ghi liên quan vào cùng transaction; phân biệt lỗi dữ liệu và xung đột với lỗi hạ tầng.
- Dùng khóa chống lặp yêu cầu để tránh tạo trùng khi client retry sau timeout.
- Xây dựng tiêu chí kiểm thử để xác nhận không lộ dữ liệu, không mất bất biến và không trả ID của bản ghi chưa commit.

## 2. Định danh bản ghi là hợp đồng, không phải vị trí dòng

Một bản ghi có thể có:

| Loại định danh | Vai trò | Có nên đổi không? |
| --- | --- | --- |
| Khóa chính `id` | Nhận diện hàng trong DB và tham chiếu từ bảng khác | Thường không thay đổi |
| Mã nghiệp vụ `ticket_number` | Mã hiển thị cho người dùng, có thể theo quy tắc riêng | Phụ thuộc nghiệp vụ |
| `request_id` | Nhận diện **một yêu cầu tạo logic** để chống lặp | Cố định cho cùng lần thao tác logic |
| Khóa chủ sở hữu `owner_id` | Giới hạn phạm vi truy cập và phục vụ phân quyền | Thay đổi khi nghiệp vụ chuyển quyền sở hữu |
| Chỉ số hàng trong danh sách | Vị trí hiển thị sau sắp xếp/lọc | **Không phải định danh** |

Không dùng `SELECT COUNT(*) + 1`, vị trí trang, thứ tự trả về hoặc `MAX(id) + 1` làm khóa chính. Các giá trị đó không bảo vệ được tranh chấp giữa nhiều tiến trình. Cũng không dùng số ID để suy luận chắc chắn thứ tự commit: sequence/identity có thể sinh số có khoảng trống và các giao dịch có thể commit theo thứ tự khác thứ tự được cấp ID.

**ID là danh tính**, không phải lời hứa rằng “đã có đúng 1245 đơn hàng” hoặc “đơn hàng 1245 được tạo sau đơn hàng 1244”.

### 2.1. Các chiến lược cấp ID

| Cách cấp | Ưu điểm | Điều cần cân nhắc |
| --- | --- | --- |
| DB identity/sequence dạng `BIGINT` | Dễ dùng với DB quan hệ; khóa gọn | Phụ thuộc cơ chế của DB; ID có thể nhảy số và lộ quy mô nếu công khai trực tiếp |
| UUID sinh tại Java | Có thể cấp trước khi gọi DB, dễ hợp nhất dữ liệu từ nhiều nguồn | Kích thước khóa và index lớn hơn `BIGINT`; cần chọn chiến lược tạo hợp lý |
| UUID sinh tại DB | Không cần client quyết định ID; có kiểu `UUID` riêng ở một số DB | Cú pháp/hàm phụ thuộc DB; phải hiểu tính sẵn có và phiên bản |
| Khóa tự nhiên | Có sẵn ý nghĩa nghiệp vụ, có thể dùng làm khóa duy nhất | Có thể thay đổi, dài hoặc chứa thông tin nhạy cảm |
| Bộ sinh ID phân tán có thứ tự tương đối | Hỗ trợ nhiều writer không chung một sequence | Cần quản lý clock, node, trùng lặp và vận hành |

Dù chọn cách nào, **DB vẫn phải có ràng buộc khóa chính/duy nhất**. Một bộ sinh ID “xác suất trùng rất thấp” không thay thế yêu cầu kiểm tra trùng hoặc quy tắc xử lý xung đột tại nguồn lưu trữ.

## 3. Ví dụ xuyên suốt: tạo phiếu hỗ trợ

Giả sử một người dùng đã đăng nhập gửi yêu cầu tạo phiếu. Ta thiết kế bảng PostgreSQL:

```sql
CREATE TABLE tickets (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id          BIGINT NOT NULL,
    client_request_id UUID NOT NULL,
    title             VARCHAR(200) NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    version           BIGINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_ticket_owner_request
        UNIQUE (owner_id, client_request_id),
    CONSTRAINT ck_ticket_title_not_blank
        CHECK (length(btrim(title)) > 0),
    CONSTRAINT ck_ticket_status
        CHECK (status IN ('OPEN', 'CLOSED')),
    CONSTRAINT ck_ticket_version
        CHECK (version >= 0),
    CONSTRAINT ck_ticket_owner
        CHECK (owner_id > 0)
);
```

Ý nghĩa:

- `id` là khóa chính **do DB sinh**. `GENERATED ALWAYS AS IDENTITY` thể hiện rõ DB chịu trách nhiệm cấp giá trị trong luồng thông thường.
- `owner_id` là chủ sở hữu, lấy từ ngữ cảnh xác thực của request. Ví dụ chưa thêm bảng người dùng; trong hệ thống thực, nếu có bảng cha cùng DB thì cần xem xét khóa ngoại thích hợp.
- `client_request_id` là UUID gắn với **một lần tạo logic**, do client hoặc tầng API cấp rồi giữ nguyên khi retry. Ràng buộc unique theo `(owner_id, client_request_id)` ngăn người dùng ấy tạo hai phiếu từ cùng một yêu cầu.
- `title` bắt buộc, không được chỉ có khoảng trắng; `VARCHAR(200)` giới hạn độ dài theo quy tắc của PostgreSQL.
- `status` được DB đặt mặc định `OPEN` khi không truyền; `version` bắt đầu từ 0 để dùng khi cập nhật về sau.
- `created_at` là thời điểm do DB ghi nhận. `TIMESTAMPTZ` biểu diễn thời điểm theo cách PostgreSQL quy định, không giữ tên múi giờ gốc của người dùng.

Một trường hợp nghiệp vụ khác có thể đặt `request_id` độc nhất toàn hệ thống, hoặc có thêm `tenant_id` trong khóa unique. Phạm vi unique phải phản ánh chính xác phạm vi người dùng và an toàn đa tenant; không được dựa vào ID người dùng không được xác thực.

### 3.1. Tại sao cần ràng buộc ở DB?

Java có thể kiểm tra tiêu đề trước khi ghi để trả lỗi dễ hiểu. Tuy nhiên, batch, job nền, ứng dụng khác hoặc nhiều request đồng thời có thể đi đường khác. `NOT NULL`, `CHECK`, `PRIMARY KEY` và `UNIQUE` bảo vệ dữ liệu **ngay trong DB**, không phụ thuộc duy nhất vào controller.

Không nên lưu tất cả dưới dạng `TEXT` chỉ để giảm công viết schema. Kiểu `UUID` cho request ID, `BIGINT` cho khóa, `VARCHAR` cho tiêu đề và `TIMESTAMPTZ` cho thời điểm tạo thể hiện ý nghĩa rõ hơn và hỗ trợ truy vấn/index hiệu quả theo workload phù hợp.

## 4. Thực thi INSERT: trường nào gửi, trường nào để DB tạo?

Với bảng trên, client chỉ cần dữ liệu nghiệp vụ và mã request:

```sql
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (
    25,
    '2f96a144-e0e4-471e-a999-8b875b41f511',
    'Không đăng nhập được'
);
```

DB tự điền `id`, `status`, `version` và `created_at`. Nhưng câu lệnh như trên **không tự trả ID cho chương trình** theo một hợp đồng JDBC chung; muốn nhận ID, cần dùng cơ chế trả kết quả phù hợp với hệ quản trị và driver.

### 4.1. DEFAULT không thay thế một NULL tường minh

Hai câu sau có thể khác kết quả:

```sql
-- Hợp lệ: bỏ qua status -> dùng DEFAULT 'OPEN'
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (25, '91cd6917-0a8c-46cf-8d87-5dd4f6eeb5b7', 'Cần hỗ trợ');

-- Không hợp lệ: gửi NULL tường minh -> vi phạm NOT NULL
INSERT INTO tickets (owner_id, client_request_id, title, status)
VALUES (25, '2ebfdb7a-1b42-4f94-a9cd-0e0ad9a6db3d', 'Cần hỗ trợ', NULL);
```

`DEFAULT` được áp dụng khi cột bị bỏ qua hoặc được chỉ định dùng `DEFAULT`; nó không mặc nhiên thay `NULL` được gửi tường minh. Tương tự, bản ghi có ID do DB sinh không có nghĩa client nên tự gửi giá trị `id = 0`: đó là hai mô hình khác nhau, cần giữ nhất quán.

### 4.2. Không tạo ID bằng hai câu SQL không liên quan

Mẫu nguy hiểm:

```sql
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (25, 'a8b1062e-b83a-4c73-a953-5daea3a70a88', 'Cần hỗ trợ');

SELECT MAX(id) FROM tickets; -- SAI: có thể trả ID của giao dịch khác
```

Trong môi trường nhiều người dùng, yêu cầu khác có thể vừa thêm bản ghi. Ngay cả khi truy vấn chạy trong một transaction, `MAX(id)` cũng không phải hợp đồng lấy ID của **đúng hàng vừa insert**. Hãy dùng `RETURNING` hoặc API generated keys của driver.

## 5. PostgreSQL RETURNING: nhận lại ID và các giá trị do DB sinh

PostgreSQL hỗ trợ mệnh đề `RETURNING` trên `INSERT`:

```sql
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (
    25,
    'f6d06eb6-8e39-4874-a2a4-8fb76e3994da',
    'Không đăng nhập được'
)
RETURNING id, status, version, created_at;
```

Câu lệnh này có thể trả một hàng đại diện kết quả tạo:

```text
id    | status | version | created_at
------+--------+---------+------------------------------
1245  | OPEN   | 0       | 2026-11-21 10:15:00+00
```

Đây là **dữ liệu ví dụ**, không phải số ID hoặc thời điểm mà DB thực tế bắt buộc sinh. Tên bảng, dữ liệu và cấu hình thời gian có thể cho giá trị khác.

Ưu điểm của `RETURNING`:

- Nhận khóa chính đúng hàng vừa được ghi mà không phải đoán ID tiếp theo.
- Nhận những giá trị DB quyết định như `DEFAULT` hoặc cột do cơ chế DB cấp.
- Có thể nhận thêm trường cần thiết để xây response mà không gọi `SELECT` riêng.
- Với một `INSERT` nhiều hàng, có thể nhận nhiều hàng kết quả tương ứng các hàng được tạo; **không dựa vào thứ tự trả về** nếu giao thức chưa quy định.

**Quan trọng:** `RETURNING` chạy như một phần của câu `INSERT`. Nếu ở trong transaction chưa commit, ID trả về là ID của hàng đang tồn tại trong **transaction đó**, chưa phải bằng chứng rằng thay đổi đã được xác nhận bền vững cho client. Nếu transaction rollback, bản ghi không tồn tại dù Java đã đọc được ID.

### 5.1. INSERT nhiều hàng

```sql
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES
    (25, '0ab0ebfd-196f-497b-9aae-9f6d6d915e95', 'Lỗi thanh toán'),
    (25, 'b29a218b-f7f1-4111-ae96-d2ece8ee0a50', 'Cập nhật hồ sơ')
RETURNING client_request_id, id, status;
```

Khi cần ánh xạ mỗi ID với input tương ứng, **trả kèm khóa tương quan** như `client_request_id`. Không ghép hai danh sách dựa vào giả định DB/driver sẽ luôn trả hàng theo thứ tự trong câu `VALUES`.

### 5.2. Cú pháp giữa DB khác nhau

`RETURNING` ở ví dụ là lựa chọn của PostgreSQL. Các hệ quản trị khác có cơ chế tạo và trả khóa khác nhau, ví dụ API generated keys của JDBC hoặc cú pháp riêng của SQL Server, Oracle, SQLite... Không dùng câu `SELECT MAX(id)` như phương án dự phòng mang tính chung.

## 6. Java/JDBC: INSERT và nhận ID qua RETURNING

Đoạn Java 17 sau minh họa đường tạo một phiếu bằng PostgreSQL JDBC. Nó giả định tầng API đã xác thực người dùng và truyền `ownerId` tin cậy; ví dụ vẫn kiểm tra dữ liệu đầu vào ở service/repository.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;
import javax.sql.DataSource;

record CreatedTicket(
        long id,
        String status,
        long version,
        Instant createdAt
) {}

public final class TicketRepository {
    private final DataSource dataSource;

    public TicketRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public CreatedTicket insert(long ownerId, UUID requestId, String title)
            throws SQLException {
        if (ownerId <= 0) {
            throw new IllegalArgumentException("ownerId không hợp lệ");
        }
        Objects.requireNonNull(requestId, "requestId");
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title không được rỗng");
        }

        String cleanedTitle = title.strip();
        String sql = """
            INSERT INTO tickets (owner_id, client_request_id, title)
            VALUES (?, ?, ?)
            RETURNING id, status, version, created_at
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, ownerId);
            statement.setObject(2, requestId);
            statement.setString(3, cleanedTitle);

            try (ResultSet row = statement.executeQuery()) {
                if (!row.next()) {
                    throw new SQLException("INSERT không trả hàng kết quả");
                }

                CreatedTicket created = new CreatedTicket(
                        row.getLong("id"),
                        row.getString("status"),
                        row.getLong("version"),
                        row.getObject(
                                "created_at", OffsetDateTime.class).toInstant()
                );

                if (row.next()) {
                    throw new SQLException("INSERT trả nhiều hơn một hàng");
                }
                return created;
            }
        }
    }
}
```

**Cách đọc ví dụ:**

1. `DataSource` cấp kết nối, thường thông qua pool có giới hạn.
2. `PreparedStatement` đưa input thành **giá trị tham số**, không nối chuỗi input trực tiếp vào SQL. Điều này giúp chống SQL injection ở vị trí truyền giá trị.
3. `setObject(2, requestId)` truyền UUID cho driver hỗ trợ ánh xạ UUID tới kiểu `UUID` PostgreSQL.
4. `executeQuery()` dùng ở đây vì `INSERT ... RETURNING` trả về `ResultSet`. Nếu dùng `INSERT` không trả hàng và lấy generated keys theo JDBC, cách gọi sẽ khác.
5. `row.getLong("id")` nhận ID vừa tạo; `OffsetDateTime` biểu diễn thời điểm từ `TIMESTAMPTZ` theo driver rồi chuyển sang `Instant`.
6. `try-with-resources` đóng result set, statement và kết nối khi hoàn tất; với pool, thao tác đóng thường trả kết nối về pool.
7. Ví dụ sử dụng **auto-commit mặc định của kết nối**, giả định pool cung cấp kết nối ở chế độ thích hợp. Cần quản lý cấu hình/pool rõ ràng; nếu kết nối đang ở chế độ `autoCommit=false` do transaction manager, ID chỉ được xác nhận sau `commit`.
8. Logic kiểm tra độ dài `VARCHAR(200)` chưa được lặp trong Java; DB sẽ từ chối input vượt giới hạn, nhưng tầng API nên validate sớm để trả lỗi dễ hiểu.

Một repository có thể trả riêng `id`, nhưng trả một DTO gồm ID và các giá trị DB đã quyết định giúp caller tránh phỏng đoán `status`, `version` hoặc `createdAt`.

## 7. Cách thứ hai: JDBC getGeneratedKeys()

JDBC hỗ trợ API lấy khóa phát sinh từ thao tác insert, tùy driver và khả năng của DB. Cách này không yêu cầu ứng dụng viết cú pháp `RETURNING` trong SQL nếu driver hỗ trợ.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class TicketIdWriter {
    private final DataSource dataSource;

    public TicketIdWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long insertAndReturnId(long ownerId, UUID requestId, String title)
            throws SQLException {

        String sql = """
            INSERT INTO tickets (owner_id, client_request_id, title)
            VALUES (?, ?, ?)
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     sql, new String[] { "id" })) {

            statement.setLong(1, ownerId);
            statement.setObject(2, requestId);
            statement.setString(3, title);

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new SQLException(
                        "Kỳ vọng tạo đúng một bản ghi, thực tế: " + affectedRows);
            }

            try (ResultSet keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("Driver không trả generated ID");
                }
                long id = keys.getLong(1);
                if (keys.next()) {
                    throw new SQLException("Driver trả nhiều hơn một generated ID");
                }
                return id;
            }
        }
    }
}
```

Cơ chế đáng chú ý:

- `new String[]{"id"}` yêu cầu driver trả khóa từ cột `id`. Một số driver hỗ trợ `Statement.RETURN_GENERATED_KEYS` thay vì danh sách cột, nhưng số cột trả về và cách triển khai khác nhau.
- `executeUpdate()` báo số hàng tác động; `getGeneratedKeys()` trả result set chứa giá trị khóa mà driver cung cấp.
- **Không gọi `getGeneratedKeys()` như cách lấy hàng `RETURNING` sau `executeQuery()`** trong cùng một ví dụ; đó là hai đường API khác nhau.
- Đối với bảng có khóa ghép hoặc ID tạo ở ứng dụng, mô hình trả kết quả khác; hãy thiết kế mapping đúng khóa đã chọn.
- Driver/DB có thể có giới hạn khi insert nhiều hàng, batch insert hoặc có trigger. Cần chạy kiểm thử tích hợp trên **chính DB và phiên bản driver** đang triển khai.

Đoạn ngắn này không lặp validation của `TicketRepository` trước đó để tập trung vào API generated keys; trong mã sản xuất phải áp dụng cùng ràng buộc input, phân quyền và xử lý lỗi. Nếu muốn nhận `status` và `created_at`, `RETURNING` thường thuận tiện hơn ở PostgreSQL.

## 8. Đã có ID chưa có nghĩa đã commit: ranh giới giao dịch

Ví dụ nghiệp vụ yêu cầu **tạo phiếu** và **ghi lịch sử “phiếu được tạo”**. Nếu insert phiếu thành công mà insert audit lỗi, hệ thống không được trả thành công rồi để lịch sử bắt buộc bị thiếu.

Thiết kế một bảng audit đơn giản:

```sql
CREATE TABLE ticket_audit (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id   BIGINT NOT NULL REFERENCES tickets(id),
    action      VARCHAR(40) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_ticket_audit_action
        CHECK (action IN ('TICKET_CREATED'))
);
```

Quy trình trên **cùng một transaction DB**:

```sql
BEGIN;

INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (
    25,
    '86e1b71b-7af5-4e94-87af-cdd86bd58e11',
    'Cần trợ giúp'
)
RETURNING id;

-- Dùng ID vừa nhận (ví dụ 1246) để ghi audit trong CÙNG transaction.
INSERT INTO ticket_audit (ticket_id, action)
VALUES (:new_ticket_id, 'TICKET_CREATED');

COMMIT;
```

`:new_ticket_id` là ký hiệu tham số mang tính minh họa. Với JDBC thuần, dùng `?` trong `PreparedStatement`, lấy ID ở bước đầu rồi đưa vào bước tiếp theo. Cả hai lệnh phải dùng **cùng connection** hoặc một transaction manager thực sự điều phối chúng.

### 8.1. Java: commit trước khi trả kết quả thành công

Ví dụ service minh họa việc nhận ID giữa transaction rồi chỉ trả sau khi cả hai câu SQL được commit:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class TicketCreationService {
    private final DataSource dataSource;

    public TicketCreationService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long createWithAudit(long ownerId, UUID requestId, String title)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                long ticketId;
                String create = """
                    INSERT INTO tickets
                        (owner_id, client_request_id, title)
                    VALUES (?, ?, ?)
                    RETURNING id
                    """;

                try (PreparedStatement statement =
                        connection.prepareStatement(create)) {
                    statement.setLong(1, ownerId);
                    statement.setObject(2, requestId);
                    statement.setString(3, title);

                    try (ResultSet rows = statement.executeQuery()) {
                        if (!rows.next()) {
                            throw new SQLException("Không có ticket ID");
                        }
                        ticketId = rows.getLong(1);
                    }
                }

                try (PreparedStatement statement =
                        connection.prepareStatement("""
                            INSERT INTO ticket_audit (ticket_id, action)
                            VALUES (?, 'TICKET_CREATED')
                            """)) {
                    statement.setLong(1, ticketId);
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Không thể ghi audit");
                    }
                }

                connection.commit(); // Chỉ sau đây mới trả thành công.
                return ticketId;

            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Các lưu ý triển khai:

- Giả định `DataSource` cấp một kết nối mới hoặc được pool đưa về trạng thái quản lý transaction phù hợp. Khi sử dụng framework transaction, hãy để framework kiểm soát commit/rollback và vòng đời kết nối.
- Nếu insert audit thất bại **trước commit**, rollback bỏ cả phiếu và audit; dù Java đã tạm đọc `ticketId`, ID đó **không trỏ tới bản ghi đã được commit**.
- Một sequence/identity có thể đã cấp số ID và không trả lại sau rollback; **khoảng trống ID là bình thường**, không phải bằng chứng mất bản ghi.
- Nếu lỗi mạng xảy ra ngay lúc `connection.commit()`, việc gọi `rollback()` trong `catch` **không chứng minh** transaction đã thất bại; commit có thể đã thành công nhưng phản hồi bị mất. Cần đường đối chiếu theo `requestId`.
- Khi cần gửi email, cập nhật search index hoặc gọi dịch vụ khác, không đặt lời gọi mạng đó vào DB transaction rồi tưởng có thể rollback cả hai. Dùng transactional outbox/workflow có trạng thái nếu cần độ tin cậy.

## 9. Khi đồng thời xảy ra: ID duy nhất khác request duy nhất

Hai người tạo hai phiếu khác nhau cùng lúc là bình thường: DB cấp hai ID khác nhau. Nhưng một người nhấn nút hai lần hoặc HTTP client retry cùng một yêu cầu có thể tạo **hai bản ghi** dù cả hai ID hoàn toàn duy nhất.

Phân biệt:

| Bài toán | Cơ chế bảo vệ |
| --- | --- |
| Hai hàng không được có cùng ID | `PRIMARY KEY` và bộ cấp ID phù hợp |
| Một yêu cầu tạo logic không sinh nhiều hàng | `client_request_id` ổn định + `UNIQUE(owner_id, client_request_id)` |
| Mỗi chủ sở hữu chỉ có một tài nguyên theo một khóa nghiệp vụ | `UNIQUE` theo khóa nghiệp vụ đã định, có thể khác request ID |
| Không ghi đè khi nhiều người cập nhật một hàng | Điều kiện `version`, lock/transaction |
| Không vượt sức chứa khi tạo đăng ký | Cập nhật tài nguyên có điều kiện và tạo đăng ký **trong cùng transaction** |

ID duy nhất giải quyết **danh tính hàng**, chứ không tự giải quyết **trùng ý định nghiệp vụ**.

### 9.1. Hai request giống nhau đến đồng thời

Giả sử hai request có cùng `owner_id = 25` và `client_request_id = R`:

```text
Request A ---- INSERT(owner=25, request=R) ---- COMMIT -> id=1247
Request B -------- INSERT(owner=25, request=R)
                                  |
                        UNIQUE conflict hoặc chờ kết quả A
                                  |
                     Không được tạo thêm phiếu id=1248
```

DB duy trì tính unique theo cơ chế của nó. Khi B nhận lỗi unique sau khi A đã commit, service có thể tra cứu phiếu gắn với `R` và trả kết quả cũ **nếu** đó thực sự là cùng request logic.

Tuy nhiên, nếu hai request có **cùng request ID nhưng khác tiêu đề**, không được lặng lẽ trả “tạo thành công” cho nội dung khác. Phải kiểm tra dữ liệu yêu cầu được gắn với ID (có thể lưu fingerprint/hash của payload chuẩn hóa cùng metadata), phạm vi chủ thể và quyền trước khi cho phép tái sử dụng kết quả.

### 9.2. Timeout ngay lúc commit: kết quả chưa xác định

Một tình huống quan trọng:

```text
Client ---> Java ---> DB: INSERT ... ; COMMIT
                            |
                      DB commit xong
                            |
                      Mạng ngắt trước ACK
                            |
Client chỉ thấy timeout; DB có thể đã có phiếu.
```

Từ một timeout phía client không thể suy luận “chắc chắn chưa tạo”. Các bước đúng:

1. Giữ nguyên `client_request_id` khi thử lại cùng yêu cầu logic.
2. Đọc theo `(owner_id, client_request_id)` từ nguồn có độ mới phù hợp (thường là DB có thẩm quyền), đồng thời kiểm tra quyền/chủ thể.
3. Nếu có bản ghi với input tương đương, trả ID và kết quả đã commit, không insert lại.
4. Nếu chưa thấy và nguồn có thể xác nhận trạng thái, có thể thử insert lại với cùng request ID theo chính sách. DB unique vẫn là lớp bảo vệ khi có tranh chấp.
5. Nếu DB đang không sẵn sàng hoặc trạng thái chưa thể kết luận, trả trạng thái chưa xác định/tạm thất bại phù hợp; **không tự hứa thao tác chưa xảy ra**.

Không áp dụng retry không giới hạn; cần timeout, backoff có giới hạn, đo lỗi và đối chiếu sau khi nguồn hồi phục.

### 9.3. Mẫu tra cứu theo khóa chống lặp

```sql
SELECT id, title, status, version, created_at
FROM tickets
WHERE owner_id = :owner_id
  AND client_request_id = :request_id;
```

Khi dùng JDBC thuần, thay tham số đặt tên bằng `?`. Bảng `tickets` ở ví dụ có unique trên hai cột, nên truy vấn có thể tra hiệu quả theo index tương ứng. Kết quả rỗng không tự chứng minh chưa từng commit nếu đang đọc từ read replica chậm; tuyến đọc phải đáp ứng yêu cầu về độ mới.

## 10. INSERT bị từ chối: phân loại lỗi đúng

Có ba nhóm kết quả cần phân biệt:

1. **Không hợp lệ ngay từ input:** thiếu tiêu đề, ID chủ sở hữu không hợp lệ, kích thước vượt giới hạn API, request ID sai định dạng.
2. **Vi phạm ràng buộc ở DB:** null, dữ liệu ngoài miền, unique, FK (nếu có), kiểu không chuyển đổi được.
3. **Lỗi hạ tầng/giao dịch:** hết kết nối, timeout, deadlock, serialization failure, lỗi commit chưa xác định.

Với PostgreSQL, một số mã SQLSTATE thường gặp:

| SQLSTATE | Nghĩa | Cách phản ứng điển hình |
| --- | --- | --- |
| `23502` | `not_null_violation` | Lỗi dữ liệu bắt buộc |
| `23505` | `unique_violation` | Đối chiếu request ID hoặc báo xung đột khóa nghiệp vụ |
| `23514` | `check_violation` | Lỗi miền giá trị |
| `22001` | `string_data_right_truncation` | Tiêu đề vượt giới hạn |
| `23503` | `foreign_key_violation` (nếu schema có FK) | ID tham chiếu không có |
| `40001` | `serialization_failure` | Rollback, cân nhắc retry toàn transaction |
| `40P01` | `deadlock_detected` | Rollback, retry có giới hạn nếu an toàn |
| Nhóm `08` | Lỗi kết nối | Có thể phải đối chiếu trạng thái commit |

SQLSTATE không phải cách thay thế cho hợp đồng nghiệp vụ. Để phân biệt unique do request trùng với unique theo khóa nghiệp vụ, kiểm tra **constraint name** hoặc đường logic được thiết kế thay vì coi mọi `23505` là “retry đã thành công”.

Không lộ nguyên câu SQL, connection string, stack trace hoặc dữ liệu nhạy cảm từ driver cho người dùng. API nên trả lỗi có mã dễ hiểu; log nội bộ chứa correlation ID, nhóm lỗi và thông tin đủ để điều tra mà không làm lộ bí mật.

### 10.1. Một lỗi trong transaction ảnh hưởng các lệnh tiếp theo

Ở PostgreSQL, khi câu SQL trong transaction không có savepoint vi phạm ràng buộc, transaction thường vào trạng thái lỗi; các câu sau sẽ không tiếp tục như bình thường cho tới khi rollback (hoặc xử lý bằng savepoint đã thiết kế). Vì vậy xử lý lỗi không phải “ghi thêm câu INSERT khác rồi vẫn commit”.

Với thao tác tạo có các bước phụ thuộc, rollback toàn bộ thường là lựa chọn đơn giản, an toàn; nếu cần xử lý từng hàng độc lập trong batch, nên định nghĩa rõ ranh giới transaction nhỏ hơn hoặc savepoint phù hợp.

## 11. INSERT, UPSERT và “tạo hoặc lấy cái đã có”

Một số ứng dụng muốn đảm bảo “cùng khóa nghiệp vụ chỉ có một hàng” và xử lý cả trường hợp đã tồn tại. Trong PostgreSQL có `INSERT ... ON CONFLICT`.

Ví dụ **bỏ qua yêu cầu trùng**:

```sql
INSERT INTO tickets (owner_id, client_request_id, title)
VALUES (:owner_id, :request_id, :title)
ON CONFLICT (owner_id, client_request_id) DO NOTHING
RETURNING id;
```

Nếu insert được hàng mới, `RETURNING` trả ID. Nếu conflict và `DO NOTHING`, câu lệnh **không trả hàng**. Lúc đó service cần đường tra cứu bản ghi cũ và kiểm tra payload/quyền trước khi xem là thành công.

Không thay `DO NOTHING` bằng `DO UPDATE` chỉ để “buộc có RETURNING” mà không cân nhắc: một lệnh update không cần thiết có thể kích hoạt trigger, ghi WAL, thay timestamp/version hoặc tạo tác dụng phụ. Một chiến lược upsert có ý nghĩa nghiệp vụ phải định nghĩa **conflict nào được chấp nhận** và **trường nào được sửa**.

### 11.1. Tránh race condition kiểu “SELECT rồi INSERT”

Quy trình sau không đủ để chống trùng:

```text
A: SELECT theo requestId -> không thấy
B: SELECT theo requestId -> không thấy
A: INSERT -> thành công
B: INSERT -> có thể tạo trùng nếu DB không UNIQUE
```

Kiểm tra trước giúp trả lỗi sớm nhưng không thay ràng buộc unique. Với unique đúng, B bị từ chối; ứng dụng rollback và đọc lại kết quả. Không chạy một chuỗi “SELECT thì không có → chắc chắn insert được” mà bỏ qua cạnh tranh.

### 11.2. Khi nào nên dùng ON CONFLICT DO UPDATE?

Ví dụ đồng bộ catalog sản phẩm từ hệ thống ngoài có `external_product_id` làm khóa nghiệp vụ: hệ thống có thể định nghĩa “nếu đã tồn tại thì cập nhật tên/giá”. Đây là **upsert** thật sự, khác với thao tác “tạo phiếu hỗ trợ một lần” vốn cần chống tạo trùng và không nên âm thầm sửa phiếu cũ. Không lạm dụng upsert để che việc client gửi lại yêu cầu với payload khác.

## 12. Khóa chính số, UUID và khóa ghép: chọn theo phạm vi sử dụng

### 12.1. Identity/sequence

`BIGINT GENERATED ALWAYS AS IDENTITY` phù hợp khi DB giao dịch là nơi sở hữu việc tạo hàng. Nó cho phép Java không phải giữ bộ đếm trong bộ nhớ, và tránh `MAX(id) + 1`. Đừng coi ID tăng liên tục không có lỗ hổng hoặc bảo đảm thứ tự commit. Sau rollback, DB có thể đã cấp một số không được tái sử dụng.

### 12.2. UUID

Nếu cần tạo ID trước khi gọi DB hoặc hợp nhất dữ liệu từ nhiều nguồn độc lập, có thể cấp UUID ở Java:

```java
import java.util.UUID;

UUID id = UUID.randomUUID();
```

Sau đó lưu vào cột `UUID PRIMARY KEY` và trả lại chính ID đó. UUID do Java sinh không chứng minh đã ghi thành công; chỉ khi DB chấp nhận và commit thì tài nguyên được tạo. `UUID.randomUUID()` cho UUID ngẫu nhiên dạng version 4 trong Java; nếu chọn một cơ chế UUID khác có tính thứ tự phục vụ index, cần đánh giá tính đúng, tính riêng tư và hỗ trợ của thư viện.

### 12.3. Khóa ghép

Một bảng quan hệ đôi khi dùng `PRIMARY KEY (tenant_id, external_id)` hoặc `PRIMARY KEY (order_id, line_number)` để định danh trong phạm vi nghiệp vụ. Khi đó “nhận ID” có thể là nhận **cả cặp khóa** chứ không phải một số do DB sinh. Repository và API phải biểu diễn khóa ghép rõ, không tự bịa một số `id` mới nếu không có yêu cầu.

### 12.4. ID công khai và quyền truy cập

ID khó đoán hơn không thay thế phân quyền. Một API nhận `GET /tickets/1245` phải kiểm tra người dùng có quyền xem phiếu 1245 hay không; một URL chứa UUID cũng phải kiểm tra tương tự. Nếu ID tăng dễ đoán và có nguy cơ tiết lộ quy mô hoặc bị quét, cân nhắc mã công khai riêng nhưng **bảo mật chính là kiểm soát truy cập ở server**, không chỉ cách tạo ID.

## 13. Trả kết quả cho API sau khi tạo

Một API REST có thể dùng:

```text
POST /tickets
Content-Type: application/json
Idempotency-Key: <UUID ổn định cho cùng yêu cầu>

{
  "title": "Không đăng nhập được"
}
```

Sau khi **commit thành công**, một phản hồi thường gặp:

```text
HTTP/1.1 201 Created
Location: /tickets/1245
Content-Type: application/json

{
  "id": 1245,
  "status": "OPEN",
  "version": 0,
  "createdAt": "2026-11-21T10:15:00Z"
}
```

Các giá trị ID và thời gian là minh họa. Hợp đồng thật có thể thêm `requestId`, mã nghiệp vụ hoặc URL đầy đủ theo cấu trúc API.

Điểm cần tuân thủ:

- **Chỉ trả `201 Created` khi thao tác tạo đã được xác nhận commit** theo hợp đồng lưu trữ. Không trả thành công dựa trên việc đã đọc generated key trong transaction chưa commit.
- `Location` phải trỏ tới tài nguyên mà người gọi được quyền truy cập. Không đưa đường dẫn nội bộ DB, connection string hay dữ liệu nhạy cảm vào response.
- Nếu lặp lại cùng idempotency key, API có thể trả cùng kết quả đã tạo hoặc mã phản hồi được hợp đồng định nghĩa; không buộc mọi response retry đều phải giống byte-by-byte.
- Nếu gặp unique conflict do khóa nghiệp vụ khác, có thể trả `409 Conflict`; nếu input sai, trả `400`/`422` theo hợp đồng; nếu commit chưa xác định, không tuyên bố tài nguyên chắc chắn không tồn tại.
- Khi thao tác tạo chỉ được **nhận vào hàng đợi** và chưa thực hiện, `202 Accepted` có thể thích hợp hơn `201`; cần phân biệt “đã nhận yêu cầu” với “đã tạo và commit bản ghi”.

### 13.1. Trách nhiệm từng tầng trong Java

```text
Controller/API
  - Xác thực chủ thể, parse request, gắn request/correlation ID
          |
Application Service
  - Kiểm tra quyền và luật nghiệp vụ, quyết định transaction/idempotency
          |
TicketRepository
  - INSERT, tham số SQL, generated keys, ánh xạ kết quả, phân loại DB errors
          |
DataSource / Connection Pool
          |
Database (constraints + transaction + storage durability)
```

Repository không nên quyết định người dùng có quyền tạo phiếu cho `ownerId` nào nếu nó không có ngữ cảnh xác thực; service phải truyền phạm vi đã được xác nhận. Controller cũng không nên tự viết câu SQL tùy ý từ input người dùng. Tách ranh giới giúp kiểm thử logic và thay đổi công nghệ persistence mà vẫn giữ hợp đồng nghiệp vụ.

## 14. ORM/JPA: ID được quản lý thế nào?

Khi dùng JPA/Hibernate, thao tác tạo thường được biểu diễn bằng `persist` hoặc `save` và một chiến lược sinh khóa, ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Đây là **đoạn mô tả mapping**, không phải toàn bộ một entity có thể biên dịch độc lập; cần import JPA, các thuộc tính/mapping còn lại và cấu hình provider. Những điểm phải hiểu:

- `IDENTITY` thường để DB sinh khóa khi insert; thời điểm provider thực thi SQL và lấy khóa phụ thuộc chiến lược ID, flush, transaction và triển khai ORM.
- `SEQUENCE` có thể cấp khóa từ sequence trước khi câu `INSERT` thực sự được ghi; **có ID trong entity không đồng nghĩa đã commit**.
- `flush` đồng bộ các thao tác đang chờ với DB trong phạm vi transaction, nhưng **flush không đồng nghĩa commit**.
- Vi phạm unique/FK/NOT NULL có thể được phát hiện khi flush hoặc commit, chứ không nhất thiết ngay lúc gọi `persist`.
- Khi ghi một quan hệ cha–con, phải thiết kế cascade và transaction đúng; không coi việc entity đã có ID là đủ để gửi kết quả thành công cho client.

Nếu ứng dụng dùng ORM, vẫn cần đọc log SQL/trace phù hợp để biết số câu insert, thời điểm cấp ID và chi phí batch. Các khái niệm về khóa duy nhất, idempotency, transaction và quyền không biến mất khi đổi từ JDBC sang JPA.

## 15. Insert theo lô và hiệu năng

Trong hệ thống nhập dữ liệu, một request có thể cần tạo hàng nghìn bản ghi. Gọi một round trip riêng cho mỗi dòng sẽ tăng độ trễ mạng; **batch insert** hoặc `INSERT ... VALUES (...), (...)` có thể giảm chi phí.

Nhưng tốc độ không phải mục tiêu duy nhất. Cần lựa chọn:

| Câu hỏi | Tác động |
| --- | --- |
| Cả lô phải thành công hoặc rollback cùng nhau? | Quyết định ranh giới transaction |
| Mỗi input cần nhận ID riêng? | Cần khóa tương quan, generated-key mapping hoặc `RETURNING` |
| Một hàng lỗi có được làm hỏng cả lô? | Chính sách fail-fast, tách lô hoặc savepoint |
| Có unique/FK/CHECK/trigger/index nào? | Chi phí ghi và cách phân loại lỗi |
| Lô quá lớn có giữ khóa/giao dịch lâu không? | Chia lô có checkpoint và giới hạn tải |
| Chạy trên nhiều node có bị tạo trùng? | Idempotency/unique tại DB |
| Sau lỗi, có cách retry một phần an toàn? | Request ID và kết quả từng hàng |

### 15.1. Lưu ý về generated keys trong batch

`addBatch()` / `executeBatch()` của JDBC và `getGeneratedKeys()` có hành vi phụ thuộc DB/driver và kiểu statement. Không nên mặc định tất cả driver trả đúng một ID theo thứ tự input trong mọi tình huống, nhất là khi có xung đột, rewrite batch hoặc trigger. Nếu ánh xạ ID theo từng input là bắt buộc, hãy thiết kế khóa tương quan, kiểm thử tích hợp và xét việc dùng `INSERT ... RETURNING` với một trường định danh input.

### 15.2. Chỉ mục giúp đọc nhưng tốn chi phí ghi

`PRIMARY KEY` và `UNIQUE(owner_id, client_request_id)` tạo các cấu trúc giúp tra cứu/kiểm tra trùng, nhưng cũng cần cập nhật mỗi lần insert. Một số chỉ mục bổ sung phục vụ danh sách có thể cải thiện truy vấn đọc và tăng chi phí ghi. Chỉ thêm index theo bộ lọc và thứ tự thực tế, đo latency insert, tốc độ hàng/giây, dung lượng index, lock wait và contention.

### 15.3. Khi nào phải dùng transaction lớn?

Một transaction quá dài có thể giữ kết nối, khóa và tài nguyên DB lâu. Nếu nghiệp vụ yêu cầu tính nguyên tử trên toàn lô, chấp nhận và đo chi phí. Nếu mỗi hàng độc lập, chia thành lô nhỏ với checkpoint, retry có kiểm soát và cơ chế idempotency thường dễ vận hành hơn. Không tự tuyên bố “tạo hết” nếu chỉ một phần lô commit.

## 16. Tiến hóa schema, sao lưu và khả năng khôi phục

Một cột bắt buộc mới như `category` có thể khiến phiên bản ứng dụng cũ không insert được khi schema đã siết `NOT NULL`. Quy trình thường cần:

1. Thêm cột nullable hoặc có mặc định **đúng về nghiệp vụ**, theo khả năng và thời điểm triển khai.
2. Triển khai đường ghi mới để cung cấp giá trị.
3. Backfill dữ liệu cũ dựa trên nguồn hợp lệ; kiểm tra sự đầy đủ.
4. Thêm/validate ràng buộc miền và siết `NOT NULL` sau khi mọi writer tương thích.
5. Theo dõi lỗi insert và khả năng đọc dữ liệu cũ trong thời gian có nhiều phiên bản ứng dụng.

Không gán bừa một giá trị giả chỉ để migration qua kiểm tra. Nếu giá trị cũ không thể xác định, phải định nghĩa rõ cách lưu trạng thái chưa biết hoặc thay đổi yêu cầu.

Sao lưu giúp phục hồi dữ liệu đã commit khi xảy ra sự cố. Tuy nhiên, backup không thay thế giao dịch, và một generated ID không chứng minh có dữ liệu bền vững trên mọi bản sao. Cần xác định mục tiêu RPO/RTO, sao lưu schema và dữ liệu theo quy trình nhất quán, diễn tập khôi phục và kiểm tra khóa định danh/quan hệ sau phục hồi.

Nếu dữ liệu vừa insert được phục vụ qua read replica có độ trễ, API tra cứu ngay sau khi tạo có thể không nhìn thấy hàng. Cần thiết kế đường đọc **read-your-writes** hoặc đọc từ nguồn có mức độ mới phù hợp, thay vì suy luận rằng `INSERT` không thành công.

## 17. Bảo mật và an toàn của thao tác tạo

- **Không tin `owner_id` đến từ JSON client.** Lấy chủ thể đã xác thực và kiểm tra quyền được phép tạo tài nguyên trong phạm vi đó.
- **Dùng tham số hóa.** `PreparedStatement` ngăn input tiêu đề trở thành cú pháp SQL tại vị trí giá trị. Nếu câu SQL phải lựa chọn tên bảng/cột động, dùng danh sách cho phép thay vì ghép chuỗi không kiểm soát.
- **Giới hạn tài nguyên.** Kiểm tra kích thước request, độ dài tiêu đề và tần suất tạo để ngăn spam/DoS; dùng connection pool, timeout và backpressure.
- **Không tiết lộ kết quả của người khác khi xử lý idempotency.** Tra request ID phải gắn đúng chủ thể và kiểm tra payload.
- **Không coi UUID khó đoán là biện pháp phân quyền.** Kiểm tra quyền ở mọi đường đọc và cập nhật sau tạo.
- **Hạn chế log và response.** Không log mật khẩu, token, dữ liệu cá nhân không cần thiết hoặc nguyên SQL có tham số nhạy cảm.
- **Giữ audit và dữ liệu liên quan nhất quán.** Khi nghiệp vụ yêu cầu lịch sử hoặc phát thông báo, ghi thông tin cần thiết trong cùng transaction hoặc qua outbox và quy trình đối soát phù hợp.
- **Hiểu chính sách xóa và lưu giữ.** Một hàng được tạo có thể đi vào backup, replica, cache, search index; cần biết nơi nào có dữ liệu và cách xóa/giữ theo chính sách.

## 18. Bài thực hành tổng hợp

Dùng một DB PostgreSQL thử nghiệm, Java 17 và driver JDBC tương ứng. Thực hiện các thao tác dưới đây trên dữ liệu giả; không yêu cầu dùng một framework web cụ thể.

### Phần A — Tạo và nhận ID

1. Tạo bảng `tickets` theo DDL. Thêm ít nhất ba phiếu với `client_request_id` khác nhau.
2. Chạy `INSERT ... RETURNING id, status, version, created_at`; xác nhận có đúng một hàng kết quả cho mỗi câu thêm một phiếu.
3. Viết repository Java sử dụng `PreparedStatement` và `executeQuery()` để nhận ID.
4. Viết đường thay thế dùng `executeUpdate()` + `getGeneratedKeys()`; xác minh với driver thật.
5. So sánh khóa trả về với `SELECT` theo khóa `(owner_id, client_request_id)`.
6. Thử tiêu đề rỗng/chỉ khoảng trắng/quá dài, `owner_id` âm và `status = NULL`; kiểm tra lỗi hợp lý.

### Phần B — Giao dịch và lỗi

1. Tạo bảng `ticket_audit`. Thêm phiếu và audit trên cùng connection, `autoCommit=false`.
2. Cố ý làm `INSERT ticket_audit` thất bại trước commit; xác nhận cả hai hàng đều rollback.
3. Quan sát khoảng trống ID sau rollback; giải thích vì sao không dùng ID để đếm số phiếu.
4. Giả lập mất phản hồi ngay sau khi gửi commit; không vội insert lại với request ID mới.
5. Tra theo request ID để đối chiếu kết quả; định nghĩa trạng thái khi DB tạm không truy cập được.
6. Chạy hai request đồng thời với cùng owner và request ID; DB chỉ cho một tài nguyên được tạo.

### Phần C — API và quyền truy cập

1. Thiết kế `POST /tickets` trả `201 Created` và `Location` khi đã commit.
2. Thiết kế xử lý input sai, request trùng cùng payload, request trùng khác payload và lỗi DB tạm thời.
3. Kiểm tra user A không thể tra cứu ID hoặc request ID của user B.
4. Tạo ngay rồi đọc theo ID; nếu sử dụng replica/cache, thử mô phỏng trễ và đảm bảo đường đọc phù hợp.

### Phần D — Batch và migration

1. Tạo một lô 100 bản ghi với khóa request khác nhau, đối chiếu số hàng và ID.
2. Thử một bản ghi lỗi trong lô, ghi rõ lựa chọn rollback toàn lô hay tách lô.
3. Đo tổng thời gian insert từng hàng so với insert theo lô trên môi trường cùng tải.
4. Thêm trường `category` theo quy trình expand/backfill/contract; chạy thử phiên bản Java cũ và mới.
5. Phục hồi backup DB thử nghiệm và xác minh các ID, ràng buộc unique và quan hệ audit vẫn nhất quán.

### Checklist nghiệm thu

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Mỗi yêu cầu tạo hợp lệ chỉ sinh tài nguyên tương ứng | Query theo `(owner_id, client_request_id)` |
| Nhận đúng ID của hàng mới, không dùng `MAX(id)` | Kết quả `RETURNING`/`getGeneratedKeys` đối chiếu DB |
| Không công bố thành công trước commit | Test rollback sau khi đã đọc ID |
| Ràng buộc DB chặn giá trị sai | Test `NOT NULL`, `CHECK`, `UNIQUE` |
| Retry không tạo trùng | Test hai request cùng idempotency key và lỗi commit mơ hồ |
| Đúng quyền | Test hai chủ thể khác nhau |
| Không mất audit bắt buộc | Test lỗi audit trong transaction |
| Khôi phục được sau sự cố | Diễn tập backup/restore và kiểm tra khóa |

### Câu hỏi tự đánh giá

1. Vì sao `MAX(id)` và `COUNT(*) + 1` không thể thay cơ chế lấy generated ID?
2. `INSERT ... RETURNING` và `getGeneratedKeys()` khác nhau ở đâu trong JDBC?
3. Khi ID đã được trả trong transaction nhưng chưa commit, có nên trả HTTP `201` chưa?
4. Vì sao dãy ID có thể có lỗ hổng sau rollback?
5. Khóa chính duy nhất đã đủ để chống hai request retry tạo hai phiếu chưa?
6. Khi `client_request_id` trùng nhưng payload khác, service nên làm gì?
7. Tại sao một timeout sau commit không chứng minh thao tác chưa xảy ra?
8. Vì sao thêm phiếu và ghi audit bắt buộc phải chung transaction?
9. Khi nào cần `ON CONFLICT DO NOTHING`; kết quả `RETURNING` ra sao nếu conflict?
10. Dữ liệu ở replica trễ ngay sau khi tạo có ý nghĩa gì với trải nghiệm người dùng?
11. Batch insert phải bảo đảm điều gì nếu mỗi input cần một ID riêng?
12. Vì sao `id` khó đoán hoặc UUID không thay thế kiểm tra quyền?

Bài học hoàn thành khi bạn có thể thực hiện **tạo hàng → nhận đúng định danh → xác nhận commit → tra lại đúng bản ghi**, đồng thời chứng minh các trường hợp lỗi không tạo trùng hoặc phá bất biến. Đây là bước nền tảng để xây dựng các thao tác đọc, cập nhật, xóa và những luồng nghiệp vụ phức tạp hơn trong hệ thống persistence Java đáng tin cậy.
