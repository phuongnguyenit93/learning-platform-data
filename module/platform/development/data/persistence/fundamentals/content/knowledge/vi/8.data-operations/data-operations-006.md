# Cập nhật có điều kiện theo trạng thái hiện tại

Trong chương **Thao tác dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một lệnh cập nhật không chỉ trả lời câu hỏi “ghi giá trị mới là gì?” mà còn phải trả lời **“chỉ được ghi nếu trạng thái hiện tại còn cho phép thay đổi này hay không?”**. Chẳng hạn, chỉ xác nhận lượt giữ chỗ đang chờ và chưa hết hạn, chỉ hủy đơn chưa giao, chỉ duyệt yêu cầu chưa được duyệt, hoặc chỉ trừ tồn kho khi số lượng còn đủ.

Nếu ứng dụng Java đọc trạng thái, kiểm tra ở bộ nhớ rồi thực hiện `UPDATE` không điều kiện, hai request đồng thời có thể cùng quyết định dựa trên dữ liệu cũ. Kết quả là một thao tác hợp lệ bị ghi đè, một chuyển trạng thái không được phép xảy ra hoặc một tác động nghiệp vụ bị lặp. **Cập nhật có điều kiện (conditional update)** chuyển điều kiện chấp nhận vào chính câu lệnh ghi tại nguồn dữ liệu có thẩm quyền.

Bài học kết hợp mô hình trạng thái, lược đồ, truy vấn, chỉ mục, giao dịch, cô lập và kiểm soát đồng thời với ranh giới persistence Java/JDBC, xử lý lỗi kết nối, retry, idempotency, audit/outbox, bảo mật, migration và tối ưu hiệu năng.

**Mục tiêu học tập**

- Xây dựng điều kiện chuyển trạng thái hợp lệ thay vì chỉ thay giá trị cột.
- Phân biệt bước *kiểm tra trước khi ghi* và lệnh `UPDATE ... WHERE` bảo vệ bất biến tại thời điểm ghi.
- Dùng điều kiện `state`, `version`, quyền sở hữu và thời hạn để ngăn cập nhật đè hoặc chuyển trạng thái sai.
- Hiểu ý nghĩa của số hàng bị ảnh hưởng, `RETURNING`, kết quả không xác định lúc commit và retry.
- Viết Java/JDBC cập nhật trạng thái và ghi outbox trong một transaction; nhận diện giới hạn khi thao tác trải qua nhiều dịch vụ.
- Kiểm thử các tình huống cạnh tranh và quan sát hiệu năng khi nhiều request cùng tác động một đối tượng.

## 1. Bắt đầu bằng bất biến và máy trạng thái

Giả sử dịch vụ đặt chỗ có một **Reservation** với bốn trạng thái:

| Trạng thái | Ý nghĩa | Có được chuyển tiếp không? |
| --- | --- | --- |
| `PENDING` | Đã tạo lượt giữ chỗ; chưa xác nhận và còn thời hạn | Có thể xác nhận, hủy hoặc đánh dấu hết hạn theo điều kiện |
| `CONFIRMED` | Giữ chỗ được xác nhận | Kết thúc trong mô hình đơn giản này |
| `CANCELLED` | Người dùng/hệ thống đã hủy trước khi xác nhận | Kết thúc |
| `EXPIRED` | Hết hạn mà không được xác nhận | Kết thúc |

Một máy trạng thái đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CONFIRMED: Xác nhận khi chưa hết hạn
    PENDING --> CANCELLED: Hủy
    PENDING --> EXPIRED: Xử lý hết hạn
    CONFIRMED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Trong ví dụ này, **không tồn tại** chuyển `CANCELLED → CONFIRMED`, `EXPIRED → CONFIRMED` hoặc `CONFIRMED → EXPIRED`. Nếu sản phẩm cho phép hoàn tiền hay mở lại chỗ, đó là **quy trình nghiệp vụ mới**, cần định nghĩa trạng thái và sự kiện riêng, không tự tùy tiện cho phép mọi thao tác ghi một state khác.

Quy tắc xác nhận có thể phát biểu chính xác:

> Chỉ chuyển reservation từ `PENDING` sang `CONFIRMED` khi đúng tenant sở hữu, phiên bản khách đã quan sát còn khớp và thời hạn xác nhận chưa qua tại thời điểm quyết định ghi.

Đây là một **bất biến có điều kiện**, khác với ràng buộc `CHECK (state IN (...))`: `CHECK` chỉ chặn giá trị trạng thái không hợp lệ, nhưng không biết lịch sử để tự chặn mọi chuyển trạng thái sai từ giá trị cũ sang giá trị mới.

## 2. Vì sao đọc, kiểm tra rồi ghi có thể sai?

Một triển khai dễ gặp:

~~~java
// Mã sai về kiểm soát đồng thời, chỉ dùng để phân tích lỗi.
Reservation current = repository.findById(reservationId);
if (current.state().equals("PENDING")) {
    repository.updateState(reservationId, "CONFIRMED");
}
~~~

Giữa `findById` và `updateState`, một request khác có thể hủy lượt giữ chỗ.

| Thời điểm | Request A: xác nhận | Request B: hủy |
| --- | --- | --- |
| T1 | Đọc trạng thái `PENDING` | |
| T2 | | Đọc trạng thái `PENDING` |
| T3 | | Ghi `CANCELLED`, commit |
| T4 | Ghi `CONFIRMED` **không có điều kiện** | |
| T5 | Commit | |
| Hậu quả | Lượt giữ chỗ đã hủy lại thành xác nhận | |

Đây là biến thể của lỗi **time-of-check to time-of-use (TOCTOU)** và có thể gây *lost update*: quyết định được đưa ra từ dữ liệu cũ rồi ghi đè trạng thái mới hơn.

Chỉ thêm một transaction quanh `SELECT` và `UPDATE` chưa bảo đảm đúng ở mọi isolation level thông dụng. Hai transaction có thể cùng đọc một giá trị trước khi một transaction thay đổi nó. Để bảo vệ quy tắc, có thể dùng khóa hàng và một protocol nhất quán hoặc, cho trường hợp một hàng đơn giản, đưa predicate vào lệnh cập nhật.

~~~sql
UPDATE reservation
SET state = 'CONFIRMED'
WHERE reservation_id = :id
  AND state = 'PENDING';
~~~

Ở đây, **điều kiện thuộc chính câu lệnh ghi**. Khi hàng đã chuyển sang `CANCELLED` và transaction đó commit trước khi lệnh xác nhận có thể cập nhật hàng, điều kiện `state = 'PENDING'` không còn đúng. Lệnh xác nhận không được coi là thành công nếu không sửa được hàng.

## 3. Lược đồ minh họa cho dữ liệu có trạng thái

Các ví dụ tiếp theo sử dụng **PostgreSQL** và một reservation có định danh toàn cục, tenant, thời hạn và phiên bản. Khi dùng hệ quản trị khác, cần đổi cú pháp `TIMESTAMPTZ`, `RETURNING`, hàm thời gian và kiểm tra semantics concurrency tương ứng.

~~~sql
CREATE TABLE reservation (
    reservation_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'EXPIRED')
    ),
    expires_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version >= 1),
    confirmed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT confirmed_requires_time CHECK (
        state <> 'CONFIRMED' OR confirmed_at IS NOT NULL
    )
);

CREATE INDEX idx_reservation_pending_expiry
ON reservation (expires_at, reservation_id)
WHERE state = 'PENDING';
~~~

**Vai trò từng trường:**

- `state` biểu diễn giai đoạn nghiệp vụ hiện tại; không dùng các chuỗi không khai báo.
- `version` tăng sau mỗi thay đổi được chấp nhận, phục vụ **optimistic locking**.
- `tenant_id` bảo vệ phạm vi sở hữu; giá trị phải lấy từ ngữ cảnh xác thực, không tin trực tiếp tenant do client tự chọn.
- `expires_at` là thời điểm tuyệt đối để kiểm tra quyền xác nhận; dùng kiểu có ngữ nghĩa múi giờ rõ.
- `confirmed_at`, `cancelled_at` ghi thời điểm thực thi chuyển trạng thái tương ứng.
- Index partial hỗ trợ worker tìm các reservation `PENDING` hết hạn. Truy vấn một reservation theo `reservation_id` đã có khóa chính; không nên tạo thêm chỉ mục `state` cho đường ghi này một cách máy móc.

Các `CHECK` ở đây giữ giá trị cột hợp lệ nhưng **không thay thế quy tắc chuyển trạng thái**. Nếu đường import hoặc lệnh SQL quản trị có quyền `UPDATE reservation SET state = 'CONFIRMED'` không điều kiện, họ vẫn có thể vượt qua chính sách ở application service. Cần giới hạn quyền ghi, thống nhất repository/procedure hoặc dùng trigger khi thật sự cần buộc mọi đường ghi tuân thủ quy tắc.

## 4. UPDATE theo trạng thái, version và thời gian

### 4.1. Xác nhận có điều kiện và trả kết quả

~~~sql
-- PostgreSQL, cú pháp :parameter được dùng để dễ đọc;
-- JDBC PreparedStatement thông thường dùng dấu ?.
UPDATE reservation
SET state = 'CONFIRMED',
    confirmed_at = clock_timestamp(),
    updated_at = clock_timestamp(),
    version = version + 1
WHERE reservation_id = :reservation_id
  AND tenant_id = :tenant_id
  AND state = 'PENDING'
  AND version = :expected_version
  AND expires_at > clock_timestamp()
RETURNING reservation_id, version, confirmed_at;
~~~

Lệnh trên đặt các **điều kiện chấp nhận** và **tác động ghi** trong cùng một câu SQL. Nếu một hàng được trả về, lệnh đã tìm và cập nhật đúng một reservation theo các predicate ở thời điểm cập nhật. Tuy nhiên, kết quả chỉ có thể được coi là **thành công bền vững sau khi transaction commit**; nếu transaction còn phải ghi audit hoặc outbox mà bước đó thất bại, tất cả phải rollback.

Nếu không có hàng được trả về (hoặc `executeUpdate()` trả `0` với câu lệnh không dùng `RETURNING`), có nhiều khả năng:

- Không có reservation với ID/tenant tương ứng.
- Reservation không còn `PENDING`: đã xác nhận, hủy hoặc hết hạn.
- `version` hiện tại khác `expected_version`: client gửi yêu cầu dựa trên dữ liệu cũ.
- Hạn xác nhận đã hết trước khi predicate được thỏa.

**Số hàng cập nhật bằng 0 không đủ phân biệt các nguyên nhân này.** Ứng dụng có thể đọc lại một cách có phân quyền để xác định phản hồi phù hợp. Cũng không mặc nhiên cho rằng `0` đồng nghĩa “lỗi hệ thống”: đó thường là kết quả xung đột nghiệp vụ dự kiến.

### 4.2. Vì sao cần cả state lẫn version?

Khi chỉ cần chặn chuyển trạng thái không hợp lệ, `WHERE state = 'PENDING'` có thể đủ cho một hàng. Khi client đọc nhiều thông tin trước khi quyết định, `version` còn chặn thay đổi đã xảy ra nhưng **state vẫn giống cũ**:

1. Client A đọc reservation phiên bản 3, state `PENDING`, giá trị `expires_at = T1`.
2. Quản trị viên gia hạn thành `T2`, cập nhật version lên 4 nhưng vẫn để state `PENDING`.
3. Client A gửi xác nhận với phiên bản 3. Nếu chỉ kiểm tra state, lệnh có thể được chấp nhận dù quyết định của A dựa trên hạn cũ. Nếu kiểm tra version, lệnh bị từ chối để client đọc lại.

Điều này tương đương **compare-and-set (CAS)** hoặc **compare-and-swap** ở cấp bản ghi: “chỉ ghi trạng thái mới nếu dữ liệu hiện tại vẫn khớp điều kiện dự kiến”. Trong SQL, thao tác không bắt buộc phải thực hiện bằng một câu lệnh chuyên biệt tên CAS; điều kiện `WHERE` và hàng được cập nhật quyết định kết quả.

### 4.3. Đồng hồ và ranh giới thời hạn

Ví dụ dùng `clock_timestamp()` của PostgreSQL để so sánh với `expires_at` tại lúc đánh giá điều kiện. Không dùng giờ của client làm nguồn quyết định, vì đồng hồ thiết bị có thể sai hoặc bị sửa. Hai lần gọi `clock_timestamp()` trong một statement có thể không hoàn toàn giống nhau, vì hàm trả thời gian khi được gọi; điều đó không ảnh hưởng đến nguyên tắc kiểm tra hạn ở predicate nhưng nên được tính đến nếu cần một mốc thời gian duy nhất cho toàn bộ quyết định.

Nếu nghiệp vụ yêu cầu đúng **một thời điểm quyết định** dùng cho cả so hạn và ghi `confirmed_at`, cần tính một giá trị ở nguồn có thẩm quyền trong cơ chế thích hợp, và giữ semantics của nó trong khi chờ khóa. Cũng cần định nghĩa chính xác “hết hạn” là trước thời điểm bắt đầu command, thời điểm hàng được cập nhật hay thời điểm commit. Mẫu trên coi điều kiện **chưa hết hạn tại thời điểm predicate được đánh giá** là cơ sở chấp nhận, không hứa rằng commit sẽ xảy ra trước `expires_at` nếu transaction bị chậm.

## 5. Hai chuyển trạng thái cạnh tranh: xác nhận và hết hạn

Ngoài request xác nhận, một background worker có thể đánh dấu reservation hết hạn:

~~~sql
UPDATE reservation
SET state = 'EXPIRED',
    updated_at = clock_timestamp(),
    version = version + 1
WHERE reservation_id = :reservation_id
  AND state = 'PENDING'
  AND expires_at <= clock_timestamp()
RETURNING reservation_id, version;
~~~

Khi hai lệnh cùng muốn thay đổi một hàng, database phải phối hợp quyền ghi/khóa hàng. Trong PostgreSQL ở `READ COMMITTED`, khi một `UPDATE` chờ transaction khác thay đổi cùng hàng, điều kiện của lệnh chờ được đánh giá lại với phiên bản hàng mới sau khi transaction kia hoàn tất. Nhờ vậy, nếu xác nhận đã chuyển hàng sang `CONFIRMED`, worker hết hạn không còn thỏa `state = 'PENDING'`; nếu worker đã chuyển sang `EXPIRED`, yêu cầu xác nhận không còn thỏa điều kiện.

~~~mermaid
sequenceDiagram
    participant C as Confirm request
    participant D as Database
    participant E as Expiry worker
    C->>D: UPDATE ... WHERE state=PENDING AND chưa hết hạn
    E->>D: UPDATE ... WHERE state=PENDING AND đã hết hạn
    Note over D: Đồng bộ ghi lên cùng hàng
    D-->>C: Có thể cập nhật 1 hoặc 0 hàng
    D-->>E: Có thể cập nhật 1 hoặc 0 hàng
    Note over C,E: Không được chấp nhận hai trạng thái kết thúc khác nhau cho cùng version
~~~

Tại đúng ranh giới thời hạn, cách diễn giải hai predicate phải thống nhất: lệnh xác nhận dùng `expires_at > now`, lệnh hết hạn dùng `expires_at <= now`. Không nên để hai service tự tính hạn với các múi giờ, độ làm tròn hoặc đồng hồ khác nhau.

**Lưu ý:** kết quả “xác nhận thành công” chỉ mang ý nghĩa database đã chấp nhận một chuyển trạng thái. Nó không tự chứng minh một khoản thanh toán bên ngoài đã được xử lý đúng một lần. Side effect ngoài database có thể cần workflow, idempotency và đối soát riêng.

### 5.1. Hủy cũng phải có điều kiện

Trong máy trạng thái đang dùng, chỉ cho phép hủy khi còn `PENDING`:

~~~sql
UPDATE reservation
SET state = 'CANCELLED',
    cancelled_at = clock_timestamp(),
    updated_at = clock_timestamp(),
    version = version + 1
WHERE reservation_id = :reservation_id
  AND tenant_id = :tenant_id
  AND state = 'PENDING'
RETURNING reservation_id, version;
~~~

Nếu có chính sách hủy sau xác nhận, phải thêm chuyển trạng thái và hành động bù phù hợp, chẳng hạn hoàn tiền; không đổi `CONFIRMED → CANCELLED` một cách âm thầm và giả định toàn bộ nghiệp vụ đã hoàn tất.

## 6. Thực hiện transaction và outbox trong Java/JDBC

Trong ứng dụng Java, đường ghi nên tập trung ở application service/repository sở hữu trạng thái. Ví dụ dưới đây dùng PostgreSQL, Java 17+ và JDBC để cập nhật một reservation **và ghi bản ghi outbox** trong cùng transaction. Nếu ghi outbox lỗi, trạng thái xác nhận cũng bị rollback.

Schema outbox tối giản:

~~~sql
CREATE TABLE reservation_outbox (
    event_id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL
        REFERENCES reservation(reservation_id),
    version_after BIGINT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'ReservationConfirmed',
            'ReservationCancelled',
            'ReservationExpired'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    UNIQUE (reservation_id, version_after)
);
~~~

Ví dụ Java:

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

record Confirmation(UUID reservationId, long version, Instant confirmedAt) {}

public final class ReservationWriter {
    private final DataSource dataSource;

    public ReservationWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Confirmation> confirm(
            UUID tenantId, UUID reservationId, long expectedVersion)
            throws SQLException {

        if (expectedVersion < 1) {
            throw new IllegalArgumentException("Invalid expected version");
        }

        String updateSql = """
                UPDATE reservation
                SET state = 'CONFIRMED',
                    confirmed_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    version = version + 1
                WHERE reservation_id = ?
                  AND tenant_id = ?
                  AND state = 'PENDING'
                  AND version = ?
                  AND expires_at > clock_timestamp()
                RETURNING version, confirmed_at
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                Confirmation confirmed;
                try (PreparedStatement statement =
                        connection.prepareStatement(updateSql)) {
                    statement.setObject(1, reservationId);
                    statement.setObject(2, tenantId);
                    statement.setLong(3, expectedVersion);

                    try (ResultSet result = statement.executeQuery()) {
                        if (!result.next()) {
                            connection.rollback();
                            return Optional.empty();
                        }
                        confirmed = new Confirmation(
                                reservationId,
                                result.getLong("version"),
                                result.getTimestamp("confirmed_at").toInstant()
                        );
                    }
                }

                String outboxSql = """
                        INSERT INTO reservation_outbox
                            (event_id, reservation_id, version_after, event_type)
                        VALUES (?, ?, ?, 'ReservationConfirmed')
                        """;
                try (PreparedStatement statement =
                        connection.prepareStatement(outboxSql)) {
                    statement.setObject(1, UUID.randomUUID());
                    statement.setObject(2, confirmed.reservationId());
                    statement.setLong(3, confirmed.version());
                    statement.executeUpdate();
                }

                connection.commit();
                return Optional.of(confirmed);
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

**Đọc đúng ví dụ:**

- Trước khi gọi repository, tầng ứng dụng phải xác thực actor và tenant, kiểm tra quyền xác nhận cũng như yêu cầu đầu vào.
- `Optional.empty()` có nghĩa **không có hàng nào thỏa điều kiện cập nhật**, không tự phân biệt không tồn tại, đã hủy, hết hạn hay xung đột version.
- Khi update trả hàng, outbox ghi sự kiện gắn với **version sau cập nhật** trong cùng transaction.
- Mã này không phát sự kiện tới broker trong transaction. Publisher riêng đọc outbox **sau commit**, gửi lại khi lỗi; consumer phải xử lý được thông điệp lặp.
- `result.getTimestamp(...).toInstant()` đọc thời điểm xác nhận; cần kiểm chứng mapping `TIMESTAMPTZ` của driver và chính sách UTC/múi giờ.
- Ví dụ này chưa có **idempotency key**, audit actor, xử lý mã lỗi HTTP, timeout, metrics hay cơ chế phân loại kết quả commit không chắc chắn; phần tiếp theo bổ sung cách thiết kế.

Tại thời điểm `connection.commit()`, nếu client mất kết nối, có thể **không xác định được từ phía ứng dụng** liệu transaction đã commit hay chưa. Do đó không được biến mọi `SQLException` thành chỉ thị “retry tạo lại thao tác” mà không đối soát.

## 7. Trạng thái đích không phải bằng chứng về cùng một yêu cầu

Giả sử request A xác nhận thành công, nhưng phản hồi bị mất. Client gửi lại cùng lệnh; điều kiện `state = 'PENDING'` không còn đúng nên nhận `0` hàng cập nhật. Nếu API trả “không xác nhận được” ngay, người dùng có thể hiểu nhầm rằng thao tác trước đó thất bại.

Mặt khác, nếu state đang là `CONFIRMED` do một **yêu cầu khác** đã thành công, API không được trả “đây là xác nhận của bạn” chỉ vì thấy trạng thái đích giống nhau.

**Idempotency** cần nhận diện *cùng một ý định nghiệp vụ*, thường qua `request_id` ổn định và fingerprint của payload:

~~~sql
CREATE TABLE reservation_command (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    reservation_id UUID NOT NULL,
    command_type TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reservation_version BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, request_id)
);
~~~

Một luồng command hoàn chỉnh nên:

1. Nhận `request_id` do client/nguồn gửi ổn định qua các lần retry, cùng payload đã xác thực.
2. Trong transaction, đảm bảo chỉ một người xử lý cùng key (ví dụ ghi một hàng lệnh duy nhất rồi khóa/kiểm tra theo chiến lược phù hợp).
3. Nếu key đã hoàn tất, so sánh payload hash và trả **kết quả đã lưu**; nếu payload khác, từ chối tái sử dụng key sai.
4. Nếu là key mới, thực hiện conditional update, ghi trạng thái/kết quả lệnh và outbox **cùng transaction**.
5. Nếu kết nối bị đứt ở commit, yêu cầu retry tra kết quả theo key sau khi database phục hồi; không tạo lệnh độc lập với ID mới.

Bảng `reservation_command` minh họa cấu trúc, **chưa phải một triển khai idempotency hoàn chỉnh**. Việc đặt `PRIMARY KEY(request_id)` không tự giải quyết tiến trình xử lý song song, trạng thái đang xử lý, timeout và kết quả trả về. Cần thiết kế giao thức ghi/đọc và xử lý xung đột tương ứng. `reservation_outbox` và `reservation_command` cũng phục vụ hai mục tiêu khác nhau: **phát sự kiện đáng tin cậy** và **ghi nhớ kết quả của một ý định**.

## 8. So sánh các chiến lược kiểm soát đồng thời

| Chiến lược | Cách dùng | Điểm mạnh | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **UPDATE có điều kiện** | `UPDATE ... WHERE state = ...`; kiểm tra hàng cập nhật | Gọn, nguyên tử cho một lệnh, ngăn chuyển state sai | Có thể thiếu đủ dữ kiện cho bất biến nhiều hàng |
| **Optimistic locking** | Thêm `WHERE version = :expected`, tăng version | Chặn ghi đè quyết định dựa trên dữ liệu cũ | Conflict tăng khi cùng hàng bị sửa nhiều; cần đọc lại |
| **Pessimistic locking** | `SELECT ... FOR UPDATE` trong transaction, sau đó kiểm tra/ghi | Dễ diễn tả logic nhiều bước trên cùng hàng | Chờ khóa, deadlock, timeout; transaction phải ngắn |
| **Serializable transaction** | Database kiểm tra lịch thực thi tương đương tuần tự | Có thể bảo vệ nhiều bất biến nếu toàn bộ transaction tuân thủ | Cần xử lý lỗi serialization và retry an toàn |
| **Unique/foreign key/CHECK** | Ràng buộc lược đồ | Bảo vệ tính đúng đắn trên mọi đường ghi trong phạm vi ràng buộc | Không thể tự mô tả mọi chuyển trạng thái lịch sử |

Không có lựa chọn “mạnh nhất luôn tốt nhất”. Một câu `UPDATE inventory SET available = available - ? WHERE available >= ?` có thể đủ cho bất biến số lượng không âm trên một hàng. Với thao tác di chuyển tiền qua hai tài khoản, cần cập nhật cả hai số dư, ghi sổ và bảo vệ các ràng buộc liên quan **trong cùng transaction**; chỉ điều kiện ở một hàng không đủ.

### 8.1. Ví dụ trừ tồn kho có điều kiện

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND available >= :quantity
RETURNING available, version;
~~~

Phải kiểm tra `quantity > 0` trước khi ghi và đặt ràng buộc `CHECK (available >= 0)` nếu database phù hợp. Khi `quantity = -5`, predicate `available >= -5` có thể đúng và phép trừ số âm sẽ **tăng tồn kho**, nên không thể bỏ validation. Tương tự, không được suy ra mọi bước tạo đơn và thu tiền đã commit chỉ vì một lệnh trừ tồn kho thành công: cần transaction và ranh giới nghiệp vụ rõ.

## 9. API, quyền truy cập và phân loại kết quả

Ứng dụng không nên trả cùng một thông báo cho mọi trường hợp `UPDATE` không sửa hàng:

| Kết quả được xác minh | Phản hồi có thể phù hợp | Ghi chú |
| --- | --- | --- |
| Không có ID trong phạm vi được phép quan sát | `404 Not Found` | Không lộ thông tin của tenant khác |
| Đối tượng có nhưng trạng thái không cho phép thao tác | `409 Conflict` | Có thể trả trạng thái hiện tại nếu người gọi có quyền |
| Client dùng version cũ | `409 Conflict` hoặc `412 Precondition Failed` | `412` thường dùng khi có điều kiện HTTP như `If-Match` không thỏa |
| Yêu cầu đã xử lý với cùng idempotency key | Trả kết quả đã ghi nhận | Chỉ sau khi kiểm tra key và payload tương ứng |
| Payload không hợp lệ | `400` hoặc `422` theo hợp đồng API | Không thử ghi khi vi phạm validation rõ |
| Database không truy cập được, lỗi hạ tầng | Lỗi 5xx/thử lại theo chính sách | Không báo nhầm “đã hủy” hay “không tồn tại” |

Khi API có ETag/version, client có thể gửi `If-Match` để yêu cầu “chỉ cập nhật nếu phiên bản tôi đã thấy vẫn là phiên bản hiện tại”. Tầng server ánh xạ điều kiện này vào `WHERE version = :expected` hoặc cơ chế tương đương. **ETag phải được phát sinh và so sánh theo hợp đồng của API**, không tự dùng thời gian `updated_at` có độ phân giải thấp làm token đồng thời.

**Quyền là một điều kiện độc lập:** `tenant_id`, owner và quyền hành động cần được kiểm tra từ danh tính đã xác thực. Đặt `tenant_id` vào `WHERE` giúp thu hẹp phạm vi cập nhật nhưng không thay thế hoàn toàn chính sách phân quyền, và không được lấy tenant tùy ý từ request chưa xác minh.

## 10. Khi quy tắc liên quan đến nhiều hàng hoặc nhiều hệ thống

### 10.1. Nhiều hàng trong cùng database

Ví dụ xác nhận một đặt chỗ đồng thời phải:

- Chuyển trạng thái reservation.
- Trừ quota một sự kiện hoặc đánh dấu ghế đã dùng.
- Ghi biên nhận nghiệp vụ và outbox.

Mỗi lệnh ghi phải có điều kiện thích hợp. Nếu quota hết, **rollback toàn transaction** thay vì giữ trạng thái `CONFIRMED` nhưng không có chỗ. Cần chọn thứ tự khóa nhất quán để giảm deadlock và đặt constraint cho các bất biến có thể biểu đạt (ví dụ ghế không bị chiếm hai lần bằng unique index phù hợp).

Một `UPDATE reservation ... WHERE state = 'PENDING'` không tự bảo vệ quan hệ một-một giữa ghế và người giữ khi nhiều reservation cùng nhắm một ghế. Thiết kế đúng cần điều kiện ở **đúng dữ liệu có thẩm quyền** của bất biến đó, cùng khóa/ràng buộc và transaction tương ứng.

### 10.2. Giữa nhiều dịch vụ hoặc database

Giả sử xác nhận reservation cần gọi cổng thanh toán bên ngoài. Database và cổng thanh toán thường **không cùng một transaction ACID**. Không nên giữ transaction database mở trong lúc gọi network không kiểm soát; cũng không được giả định có thể rollback một khoản tiền đã thu bằng `connection.rollback()`.

Một phương án là:

~~~mermaid
flowchart LR
    A["Command xác nhận"] --> B[("DB: conditional update + outbox")]
    B --> C["Publisher / worker"]
    C --> D["Dịch vụ bên ngoài"]
    D --> E["Webhook / result có idempotency key"]
    E --> F["Conditional update trạng thái tiếp theo"]
~~~

Quy trình thực tế có thể cần trạng thái trung gian như `PAYMENT_PENDING`, `PAYMENT_CONFIRMED` và hành động bù khi thất bại. Sơ đồ minh họa mô hình tổng quát, **không có nghĩa phải đánh dấu `CONFIRMED` trước khi thật sự đạt điều kiện thanh toán**. Chọn thời điểm chuyển trạng thái theo cam kết nghiệp vụ; mọi webhook và lệnh retry phải được khử trùng/đối soát bằng ID, version và trạng thái.

## 11. Worker xử lý hàng loạt với điều kiện trạng thái

Một worker hết hạn có thể xử lý từng reservation, nhưng với hàng triệu dòng cần tránh một lệnh khổng lồ làm tăng thời gian giữ khóa, WAL và độ trễ request giao dịch. Một chiến lược trên PostgreSQL là:

~~~sql
WITH due AS (
    SELECT reservation_id
    FROM reservation
    WHERE state = 'PENDING'
      AND expires_at <= clock_timestamp()
    ORDER BY expires_at, reservation_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE reservation AS r
SET state = 'EXPIRED',
    version = version + 1,
    updated_at = clock_timestamp()
FROM due
WHERE r.reservation_id = due.reservation_id
  AND r.state = 'PENDING'
  AND r.expires_at <= clock_timestamp()
RETURNING r.reservation_id, r.version;
~~~

Ví dụ chọn một nhóm hàng cần xử lý, khóa những hàng chọn được và bỏ qua hàng đang bị khóa để nhiều worker có thể cùng chạy. **`SKIP LOCKED` không bảo đảm thứ tự công bằng hoặc xử lý hết mọi hàng ngay trong một lượt**; worker cần chạy lặp và theo dõi backlog. Câu lệnh cũng chưa ghi sự kiện outbox tương ứng; trong sản phẩm thật, phải lưu event/việc cần làm trong **cùng transaction** trước khi commit nếu hệ thống khác phụ thuộc vào thông tin hết hạn.

Đo batch size, thời gian transaction, lock wait và tốc độ worker. Nếu hàng bị bỏ qua liên tục do khóa nóng, cần cảnh báo và chính sách retry. Không tự ý dùng thao tác xóa trạng thái hàng loạt khi các đối tượng phải giữ lịch sử.

## 12. Migration, audit và bảo mật

### 12.1. Thay đổi máy trạng thái theo phiên bản ứng dụng

Giả sử sau này thêm trạng thái `PAYMENT_PENDING`. Đây không chỉ là thêm một chuỗi vào `CHECK`: phải xem mọi đường ghi, câu `WHERE state IN (...)`, UI, consumer, dashboard và báo cáo.

Quy trình nên theo **expand–migrate–contract**:

1. Mở rộng schema/contract để các phiên bản đang chạy đọc được trạng thái mới mà không lỗi.
2. Cập nhật producer/consumer và repository để hỗ trợ chuyển trạng thái mới, giữ tương thích trong giai đoạn triển khai cuốn chiếu.
3. Backfill dữ liệu lịch sử **chỉ khi có đủ bằng chứng**; không suy đoán trạng thái cũ từ timestamp đơn lẻ.
4. Triển khai logic ghi mới rồi kiểm thử các phiên bản ứng dụng chạy xen kẽ.
5. Sau khi chắc chắn không còn đường ghi cũ phá vỡ bất biến, mới siết ràng buộc và loại bỏ trường/transition cũ.

Không để một worker cũ tiếp tục chạy `UPDATE ... WHERE state = 'PENDING'` theo ngữ nghĩa cũ nếu từ phiên bản mới `PENDING` cần thêm điều kiện thanh toán khác.

### 12.2. Nhật ký trạng thái và quyền can thiệp

Các thông tin hữu ích trong audit là `reservation_id`, trạng thái cũ/mới, version, actor, nguồn lệnh, request ID, thời điểm và lý do. Việc chỉ có trạng thái hiện tại không giải thích được chuỗi thay đổi.

Nếu audit là yêu cầu bắt buộc, **ghi nó cùng transaction** với cập nhật hoặc dùng event/outbox mang đủ thông tin theo hợp đồng. Outbox dùng để phát thông điệp không đương nhiên là audit log lâu dài: có thể được dọn sau khi phát, thiếu thông tin actor hoặc không đủ kiểm soát tính bất biến.

Đường cập nhật phải kiểm tra quyền; không cho một client tự gửi `state = 'CONFIRMED'` rồi dùng câu SQL update không điều kiện. Hạn chế quyền SQL trực tiếp cho những thành phần không sở hữu state machine. Những bản ghi bị sai do thao tác quản trị hoặc migration cần được xử lý theo quy trình có audit, backup và kiểm chứng, không sửa lịch sử một cách âm thầm.

## 13. Quan sát hiệu năng và các lỗi thường gặp

| Hiện tượng | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Nhiều cập nhật trả 0 hàng | Tỷ lệ state/version conflict, request lặp, hạn đã qua | Phân loại nghiệp vụ, điều chỉnh UX/retry; không tăng timeout mù quáng |
| p99 tăng khi nhiều request cùng ghi | Hot row, lock wait, transaction dài, pool chờ | Rút ngắn transaction, giảm tranh chấp, cân nhắc mô hình dữ liệu |
| Hết hạn chậm xử lý | Worker backlog, partial index, batch size, hàng khóa lâu | Theo dõi lag, retry, chia nhóm và giới hạn batch |
| API trả thành công nhưng không có event | Outbox không nằm cùng transaction, publisher lỗi | Ghi outbox nguyên tử và theo dõi publish/replay |
| Event phát lặp | At-least-once delivery, publisher retry | Consumer idempotent bằng event ID/version |
| Transaction commit nhưng client nhận lỗi | Kết nối đứt ở thời điểm commit | Đối soát bằng request ID/receipt, không thực hiện lại mù quáng |
| Data ở replica khác state primary | Replication lag hoặc cache chưa invalidation | Dùng nơi đọc đáp ứng cam kết read-your-writes cho quyết định ghi |

**Chỉ mục:** với cập nhật theo `reservation_id` (primary key), database thường tìm hàng nhanh nhờ index khóa chính rồi kiểm tra `state`, `tenant_id` và `version`. Không nên tự thêm index cho từng điều kiện trong `WHERE` vì mỗi index tăng chi phí ghi. Với truy vấn worker `WHERE state='PENDING' AND expires_at <= ...`, partial index theo thời hạn có thể hữu ích; cần xác minh bằng query plan và số liệu thật.

Khi các transaction cùng nhắm một hàng, **index không thể loại bỏ tranh chấp do bất biến đòi hỏi tuần tự hóa quyết định trên hàng đó**. Nếu một sự kiện nhận hàng chục nghìn lượt giữ chỗ, phải xem lại ranh giới/thiết kế quota, sharding hoặc phân phối quyền ghi chứ không chỉ tìm cách tối ưu SQL.

## 14. Kiểm thử cạnh tranh và lỗi kết nối

Một bài kiểm thử tuần tự không chứng minh conditional update có ý nghĩa. Cần nhiều kết nối độc lập và barrier để tạo tình huống cạnh tranh:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Hai client cùng xác nhận reservation `PENDING` phiên bản 1 | Chỉ một lệnh sửa hàng và commit; lệnh khác nhận kết quả xung đột hoặc no-op hợp lệ |
| Client A xác nhận, worker B đánh dấu hết hạn | Không commit cả hai trạng thái kết thúc; kết quả phù hợp ranh giới thời gian đã định |
| Client dùng version cũ sau khi quản trị viên gia hạn | Không sửa hàng; đọc lại version mới theo quyền |
| Hủy reservation đã `CONFIRMED` | Bị chặn theo state machine hiện tại |
| Xác nhận ngay sát hoặc qua `expires_at` | Tuân thủ ranh giới `>` và `<=` đã chọn |
| Outbox INSERT thất bại sau UPDATE | Cả thay đổi state và outbox rollback |
| Mất kết nối ngay lúc commit | Không mặc định thất bại; có đường đối soát request ID |
| Retry cùng request ID và payload | Trả kết quả cũ, không sinh event/tác động lặp |
| Cùng request ID nhưng payload khác | Phát hiện xung đột thay vì tái sử dụng kết quả |
| Tenant B đoán ID reservation của tenant A | Không thay đổi dữ liệu và không lộ thông tin bị cấm |
| Hàng triệu reservation hết hạn | Batch xử lý có giới hạn, đo lag và không làm sập p99 API |

Khi kết thúc các request, kiểm tra **trạng thái đã commit**, version, số sự kiện outbox và receipt/idempotency; không kết luận chỉ từ mã HTTP trả về. Với các bài test race cần chạy lặp và có điều khiển lịch thực thi để giảm khả năng lỗi chỉ xuất hiện ngẫu nhiên.

### 14.1. Bài tập ứng dụng

Một đơn hàng có trạng thái `CREATED → PAID → SHIPPED`; người mua được hủy khi đơn ở `CREATED`, còn worker thanh toán cập nhật `CREATED → PAID`. Một người dùng và một webhook cùng thao tác trong lúc mạng không ổn định.

**Hãy làm các việc sau:**

1. Viết bảng chuyển trạng thái hợp lệ và xác định rõ điều kiện chấp nhận hủy.
2. Viết `UPDATE ... WHERE` để chỉ chuyển `CREATED → PAID` nếu version khớp; viết lệnh hủy tương ứng.
3. Giải thích kết quả nếu hủy và xác nhận thanh toán cùng đến một lúc; chọn thứ tự ưu tiên nghiệp vụ nếu có.
4. Cho biết vì sao `SELECT status` trước rồi `UPDATE` không điều kiện là sai.
5. Thiết kế request ID để callback thanh toán lặp không tạo hai tác động, kể cả khi lần đầu đã commit nhưng phản hồi bị mất.
6. Đề xuất ba chỉ số giám sát và năm ca kiểm thử đồng thời hoặc lỗi kết nối.

**Hướng giải:** cả hai lệnh chỉ cập nhật nếu `status = 'CREATED'` và điều kiện version/quyền phù hợp; đúng một chuyển trạng thái được chấp nhận theo lịch ghi ở database. Callback thanh toán cần idempotency theo định danh sự kiện từ nhà cung cấp và có quy trình xử lý trường hợp tiền đã thu nhưng đơn bị hủy trước khi ghi nhận. Không tự coi việc update thất bại là đã hoàn tiền; đây là một bước nghiệp vụ khác cần đối soát và có thể phát sinh bù trừ.

## 15. Checklist thiết kế cập nhật có điều kiện

- [ ] Đã xác định máy trạng thái, trạng thái kết thúc và các chuyển tiếp hợp lệ.
- [ ] Mỗi lệnh thay đổi trạng thái có điều kiện `WHERE state = ...` ngay tại nguồn ghi có thẩm quyền.
- [ ] Đã thêm điều kiện `version` khi phải bảo vệ quyết định dựa trên dữ liệu đã đọc.
- [ ] Điều kiện tenant, owner, quyền và thời hạn được lấy từ ngữ cảnh đáng tin cậy.
- [ ] Phân biệt `0` hàng cập nhật với lỗi SQL/timeout và xác minh nguyên nhân khi cần.
- [ ] Không xem kết quả trả về từ `UPDATE` là commit thành công nếu transaction còn việc chưa hoàn tất.
- [ ] Các thay đổi trạng thái, dữ liệu phụ thuộc, audit/outbox bắt buộc được ghi nguyên tử.
- [ ] Đã thiết kế idempotency, request ID và đối soát khi kết nối mất tại thời điểm commit.
- [ ] Không để worker/import/migration đi vòng quy tắc chuyển trạng thái hoặc bỏ qua quyền.
- [ ] Đã đo lock wait, hot row, p95/p99, backlog worker và ảnh hưởng của chỉ mục.
- [ ] Có kiểm thử các lệnh cạnh tranh, version cũ, thời hạn, rollback và retry.
- [ ] Có kế hoạch migration state machine, backup/restore và giám sát dữ liệu sai trạng thái.

**Ghi nhớ:** Điều kiện “được phép chuyển từ trạng thái hiện tại sang trạng thái đích” phải được **kiểm tra ngay trong thao tác ghi có thẩm quyền**, thay vì chỉ được kiểm tra trước bằng Java. `UPDATE ... WHERE state ... AND version ...` cùng việc kiểm tra số hàng thay đổi tạo nền tảng cho chuyển trạng thái an toàn dưới tải đồng thời. Để bảo vệ toàn bộ nghiệp vụ, vẫn cần transaction, ràng buộc, quyền, idempotency, audit/outbox, đối soát lỗi kết nối và kiểm thử tình huống cạnh tranh.
