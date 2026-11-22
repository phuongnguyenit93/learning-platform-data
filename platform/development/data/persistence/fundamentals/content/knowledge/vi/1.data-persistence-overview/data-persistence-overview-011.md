# Lộ trình học từ thao tác lưu đơn giản đến xử lý lỗi và đồng thời

## 1. Vì sao cần một lộ trình học persistence?

Khi xây dựng ứng dụng Java, việc ghi một bản ghi xuống cơ sở dữ liệu thường khá dễ. Khó hơn là bảo đảm bản ghi **vẫn tồn tại sau khi ứng dụng khởi động lại**, **đúng với quy tắc nghiệp vụ**, **không bị ghi sai khi nhiều yêu cầu đến cùng lúc** và **có thể phục hồi khi hệ thống gặp lỗi**.

Persistence (lưu trữ bền vững) là năng lực đưa trạng thái cần giữ lâu dài ra khỏi bộ nhớ tạm của tiến trình, đọc lại trạng thái đó và duy trì tính đúng đắn của nó qua các lần chạy. Một lệnh `INSERT` thành công mới là điểm khởi đầu. Phần còn lại liên quan đến mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, cô lập, kiểm soát đồng thời, kết nối, bảo mật, sao lưu và vận hành.

Bài này là bản đồ học tập cho module `DATA_PERSISTENCE_FUNDAMENTALS`. Mục tiêu cuối cùng là thiết kế được ranh giới persistence cho ứng dụng Java, giải thích được các đánh đổi và xử lý những lỗi thực tế thay vì chỉ viết các thao tác CRUD.

### Tình huống xuyên suốt

Xét một ứng dụng đăng ký workshop có số chỗ giới hạn. Người dùng chọn một sự kiện và nhấn **Đăng ký**. Hệ thống phải thỏa mãn ba quy tắc:

1. Số chỗ còn lại không được âm; tổng số chỗ đã đăng ký không được vượt quá sức chứa.
2. Với chính sách mỗi người một suất cho một sự kiện, một người không thể có hai bản đăng ký của cùng sự kiện.
3. Khi đăng ký thành công, **việc giảm số chỗ** và **việc tạo bản đăng ký** phải cùng có hiệu lực; nếu một bước thất bại thì không được để hệ thống ở trạng thái nửa chừng.

Ba quy tắc này sẽ dẫn dắt từng chặng học. Khi hệ thống lớn lên, có thể thay quy tắc thứ hai bằng khóa chống lặp yêu cầu (idempotency key) nếu một người được đặt nhiều suất.

## 2. Bản đồ các chặng học

Hãy học theo thứ tự: tạo dữ liệu đúng, đọc đúng, cập nhật nhất quán, rồi mới xử lý lỗi và đồng thời. Có thể quay lại tối ưu từng chặng khi đã đo được vấn đề.

| Chặng | Câu hỏi cần trả lời | Sản phẩm thực hành | Dấu hiệu đã nắm vững |
| --- | --- | --- | --- |
| 1. Lưu và đọc | Dữ liệu sống ở đâu sau khi tiến trình Java kết thúc? | Tạo, đọc, sửa, xóa một bản ghi | Khởi động lại ứng dụng và vẫn đọc được dữ liệu đã lưu |
| 2. Mô hình và schema | Những ràng buộc nào phải đúng dù có nhiều đường ghi dữ liệu? | Lược đồ `events` và `reservations` | Khóa, quan hệ và ràng buộc chặn dữ liệu sai |
| 3. Truy vấn và chỉ mục | Lấy đúng dữ liệu với chi phí chấp nhận được bằng cách nào? | Truy vấn theo sự kiện và người dùng | Giải thích được vì sao thêm hoặc bỏ một chỉ mục |
| 4. Ranh giới Java | Đặt SQL, ánh xạ dữ liệu và lỗi cơ sở dữ liệu ở lớp nào? | Repository/gateway dùng `DataSource` | Mã nghiệp vụ không phụ thuộc vào chi tiết câu SQL |
| 5. Giao dịch | Nhiều thay đổi liên quan phải thành công cùng nhau thế nào? | Một thao tác đăng ký có `commit`/`rollback` | Lỗi giữa chừng không làm mất đồng bộ số chỗ |
| 6. Lỗi và khôi phục | Khi mất kết nối hoặc không biết `commit` đã thành công chưa thì sao? | Phân loại lỗi, chống lặp, thử lại có giới hạn | Không nhân đôi kết quả khi yêu cầu được gửi lại |
| 7. Đồng thời và cô lập | Hai yêu cầu cùng tranh chỗ cuối cùng được giải quyết thế nào? | Thử nghiệm đăng ký song song | Không vượt sức chứa và hiểu được cách DB bảo vệ quy tắc |
| 8. Tiến hóa và vận hành | Dữ liệu tiếp tục an toàn khi triển khai và chạy lâu dài ra sao? | Migration, kiểm soát quyền, phục hồi bản sao lưu | Thay đổi schema và phục hồi được kiểm chứng |
| 9. Hiệu năng | Chỗ chậm nằm ở câu SQL, kết nối hay tranh chấp? | Đo độ trễ, kế hoạch truy vấn và tải đồng thời | Có số đo trước và sau mỗi thay đổi |

## 3. Chặng 1 — Bắt đầu bằng một vòng ghi–đọc hoàn chỉnh

Trước khi học framework, hãy thực hiện một vòng đơn giản: mở kết nối, ghi một sự kiện, đọc lại bằng khóa định danh, cập nhật tiêu đề, rồi xóa một bản ghi thử nghiệm. Làm lại thao tác đọc sau khi tắt và khởi động lại ứng dụng.

Phân biệt các khái niệm ngay từ đầu:

- **Bộ nhớ Java:** đối tượng trong heap biến mất khi tiến trình kết thúc.
- **Bộ nhớ đệm (cache):** giúp đọc nhanh nhưng không tự bảo đảm dữ liệu đã được lưu bền vững.
- **Kho dữ liệu bền vững:** ví dụ cơ sở dữ liệu quan hệ; mức bảo đảm sau `commit` còn phụ thuộc cấu hình durability và cơ chế lưu trữ.
- **Sao lưu:** bản sao dùng để khôi phục khi dữ liệu chính bị mất hoặc hỏng; ghi thành công xuống cơ sở dữ liệu không thay thế cho sao lưu.

Một phép thử tối thiểu: ghi bản ghi, đóng kết nối, khởi động lại ứng dụng, đọc đúng bản ghi. Sau đó thử lưu một bản ghi không hợp lệ để xem lỗi được trả về ở đâu.

**Bài tập:** tạo sự kiện có `id = 42`, tên “Workshop Java” và hai chỗ. Viết các hàm tạo và tra cứu sự kiện theo `id`; ghi nhận điều gì xảy ra khi `id` đã tồn tại.

## 4. Chặng 2 — Chuyển quy tắc nghiệp vụ thành mô hình dữ liệu

Mỗi bảng nên đại diện cho một loại thực thể hoặc quan hệ có ý nghĩa. Mỗi bản ghi cần một định danh ổn định. Dùng khóa ngoại, khóa duy nhất, `NOT NULL` và `CHECK` để áp dụng các quy tắc có thể diễn đạt trực tiếp ở tầng dữ liệu; việc kiểm tra tại giao diện hoặc Java vẫn hữu ích nhưng không đủ khi có nhiều nguồn ghi.

Ví dụ sau dùng cú pháp gần PostgreSQL; cách khai báo cột tự tăng, thời gian và ràng buộc có thể khác ở hệ quản trị khác.

```sql
CREATE TABLE events (
    id              BIGINT PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    capacity        INTEGER NOT NULL CHECK (capacity >= 0),
    seats_remaining INTEGER NOT NULL
        CHECK (seats_remaining >= 0 AND seats_remaining <= capacity)
);

CREATE TABLE reservations (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id   BIGINT NOT NULL REFERENCES events(id),
    user_id    BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reservation_event_user UNIQUE (event_id, user_id)
);

INSERT INTO events (id, title, capacity, seats_remaining)
VALUES (42, 'Workshop Java', 2, 2);
```

Ở đây:

- `events.id` là khóa chính. Ứng dụng thực tế có thể chọn cơ chế tạo ID phù hợp; ví dụ dùng ID cố định để dễ thực hành.
- `reservations.event_id` là khóa ngoại; không thể đăng ký vào một sự kiện không tồn tại.
- `UNIQUE (event_id, user_id)` ngăn một người có hai bản đăng ký cho cùng sự kiện.
- `CHECK` chặn `seats_remaining` âm hoặc lớn hơn `capacity`, nhưng **chưa tự bảo đảm** số chỗ còn lại khớp số bản đăng ký. Sự nhất quán giữa hai bảng cần giao dịch và quy tắc cập nhật thích hợp.

Hãy phân biệt **quy tắc của từng dòng** với **bất biến trải qua nhiều dòng/bảng**. Quy tắc “số chỗ không âm” có thể biểu diễn bằng `CHECK`; quy tắc “giảm chỗ và thêm đăng ký phải đi cùng nhau” cần giao dịch.

**Bài tập:** thử thêm hai bản đăng ký có cùng cặp `event_id, user_id`, thử một `event_id` không tồn tại và thử đặt `seats_remaining = -1`. Giải thích vì sao mỗi thao tác bị từ chối.

## 5. Chặng 3 — Đọc đúng trước khi tối ưu truy vấn

Một truy vấn có thể đúng kết quả nhưng chậm khi dữ liệu tăng lên. Bắt đầu bằng các nhu cầu đọc cụ thể:

```sql
-- Lấy sự kiện theo khóa chính
SELECT id, title, seats_remaining
FROM events
WHERE id = 42;

-- Liệt kê đăng ký của một người dùng
SELECT id, event_id, created_at
FROM reservations
WHERE user_id = ?;
```

Khóa chính trên `events.id` đã có chỉ mục tương ứng trong đa số hệ quản trị quan hệ. Ràng buộc duy nhất trên `(event_id, user_id)` thường tạo cấu trúc chỉ mục phục vụ tìm kiếm theo `event_id` và theo cả cặp; không nên mặc định nó cũng tối ưu truy vấn chỉ lọc `user_id`. Với nhu cầu liệt kê đăng ký của người dùng, có thể cân nhắc:

```sql
CREATE INDEX idx_reservations_user_id ON reservations(user_id);
```

Quy trình quyết định chỉ mục: xác định truy vấn thực tế → đo thời gian và xem kế hoạch bằng công cụ như `EXPLAIN` → thêm chỉ mục nếu có lợi → đo lại. Chỉ mục chiếm dung lượng, làm tăng chi phí ghi và bảo trì; thêm cho mọi cột thường gây tác dụng ngược.

Cũng cần học phân trang và giới hạn kết quả. Một API liệt kê hàng triệu bản ghi mà không giới hạn vừa tốn bộ nhớ Java, vừa kéo dài kết nối DB.

**Bài tập:** tạo đủ dữ liệu thử nghiệm để so sánh kế hoạch truy vấn danh sách đăng ký theo `user_id` trước và sau khi có chỉ mục. Ghi nhận điều kiện đo, không chỉ kết luận từ một lần chạy.

## 6. Chặng 4 — Thiết kế ranh giới persistence trong Java

Mã nghiệp vụ cần diễn đạt ý định, ví dụ “đăng ký một chỗ”, thay vì rải các câu `UPDATE` và `INSERT` khắp controller. Một cách tổ chức tối thiểu:

```text
HTTP/API
   |
Application service: reserve(eventId, userId)
   |
Persistence boundary: repository / gateway
   |
JDBC + DataSource + SQL
   |
Database
```

`DataSource` cung cấp kết nối; `PreparedStatement` truyền tham số; repository chịu trách nhiệm ánh xạ dữ liệu và chi tiết truy cập DB. Lớp ứng dụng quyết định quy tắc nghiệp vụ và phạm vi giao dịch. Với thao tác trải qua nhiều repository, nên có một nơi điều phối **cùng một giao dịch**, tránh mở kết nối và `commit` riêng cho từng bước.

Có thể bắt đầu bằng JDBC thuần để nhìn thấy vòng đời kết nối và giao dịch. Sau khi hiểu cơ chế, mới chuyển sang JPA/Hibernate hoặc transaction manager của framework; lúc đó cần biết chúng đang giúp quản lý điều gì.

Ví dụ dưới đây minh họa một giao dịch bằng JDBC. Đây là ví dụ cơ sở học tập; hệ thống dùng Spring hoặc thư viện khác nên để transaction manager của chính framework quản lý giao dịch.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ReservationService {
    private final DataSource dataSource;

    public ReservationService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(long eventId, long userId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                int updated;
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE events "
                      + "SET seats_remaining = seats_remaining - 1 "
                      + "WHERE id = ? AND seats_remaining > 0")) {
                    statement.setLong(1, eventId);
                    updated = statement.executeUpdate();
                }

                if (updated != 1) {
                    throw new IllegalStateException(
                        "Sự kiện không tồn tại hoặc đã hết chỗ");
                }

                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO reservations (event_id, user_id) "
                      + "VALUES (?, ?)")) {
                    statement.setLong(1, eventId);
                    statement.setLong(2, userId);
                    statement.executeUpdate();
                }

                connection.commit();
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
```

Điểm cần quan sát:

1. `PreparedStatement` gắn tham số riêng với cú pháp SQL, giúp tránh ghép chuỗi dữ liệu đầu vào vào câu lệnh.
2. Cập nhật có điều kiện `seats_remaining > 0` là thao tác ở DB, thay vì Java đọc số chỗ rồi tính trừ trên bản sao có thể đã cũ.
3. Hai câu lệnh chạy trên **cùng một kết nối và cùng một giao dịch**. Nếu chèn đăng ký vi phạm `UNIQUE`, rollback sẽ hoàn tác cả bước giảm chỗ.
4. `try-with-resources` đóng statement và kết nối. Trong ứng dụng thật, cần dùng connection pool cấu hình đúng và theo dõi tình trạng kết nối.
5. Lỗi tại `commit` có thể xảy ra sau khi DB đã xác nhận giao dịch ở phía máy chủ nhưng phản hồi bị mất; gọi `rollback` khi ấy không đủ để khẳng định giao dịch chưa thành công. Chặng xử lý lỗi sẽ giải quyết điểm này.

**Bài tập:** cố tình tạo một đăng ký trùng. Sau khi ứng dụng trả lỗi, kiểm tra số chỗ của sự kiện không bị giảm.

## 7. Chặng 5 — Hiểu giao dịch qua bất biến

Giao dịch là một đơn vị công việc gồm nhiều thay đổi cùng được chấp nhận hoặc cùng bị hủy. Với đăng ký workshop, giao dịch bao quanh hai câu lệnh: trừ số chỗ và tạo bản đăng ký.

Một số thuộc tính thường được tóm tắt bằng ACID:

| Thuộc tính | Ý nghĩa thực hành |
| --- | --- |
| Atomicity | Không để tồn tại tình huống chỉ giảm chỗ hoặc chỉ tạo bản đăng ký sau khi giao dịch bị hủy |
| Consistency | Giao dịch và các ràng buộc cùng đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác |
| Isolation | Xác định mức độ các giao dịch đồng thời có thể quan sát tác động của nhau |
| Durability | Sau khi `commit` được xác nhận, DB cung cấp mức bền vững theo bảo đảm và cấu hình đã chọn |

Đừng đồng nhất **transaction DB** với một luồng nghiệp vụ chứa mọi tác động bên ngoài. Ví dụ DB không thể rollback một email đã gửi hoặc một yêu cầu HTTP đã hoàn tất tại hệ thống khác. Khi cần phát sự kiện sau khi lưu dữ liệu, hãy tìm hiểu **transactional outbox**: ghi bản ghi sự kiện cần gửi vào cùng giao dịch DB, rồi có tiến trình gửi riêng xử lý và chống gửi lặp ở nơi nhận.

**Bài tập:** thêm một lỗi chủ động ngay sau khi trừ chỗ nhưng trước khi chèn bản đăng ký. Sau khi rollback, đối chiếu cả `events` lẫn `reservations`.

## 8. Chặng 6 — Xử lý lỗi kết nối, thử lại và yêu cầu trùng

Lỗi persistence không chỉ là “SQL chạy thất bại”. Hãy phân loại để chọn phản ứng phù hợp.

| Tình huống | Cách phản ứng phù hợp | Điều cần tránh |
| --- | --- | --- |
| Vi phạm khóa duy nhất hoặc khóa ngoại | Dịch thành lỗi nghiệp vụ có thể hiểu; giữ nguyên ràng buộc DB | Thử lại vô hạn một yêu cầu chắc chắn không hợp lệ |
| Không lấy được kết nối hoặc DB tạm quá tải | Giới hạn thời gian chờ; thử lại có giới hạn, giãn cách và quan sát mức quá tải | Mở kết nối không giới hạn để “cứu” hệ thống |
| Deadlock hoặc lỗi serialization | Rollback và có thể thử lại **toàn bộ giao dịch** nếu an toàn | Chỉ chạy lại một nửa chuỗi thao tác |
| Mất mạng trước khi gửi yêu cầu | Có thể gửi lại khi xác định chưa có tác động, theo chính sách idempotency | Coi mọi timeout là cùng một loại lỗi |
| Mất kết nối ngay lúc `commit` | Trạng thái có thể **chưa biết**; xác minh theo định danh yêu cầu hoặc bản ghi nghiệp vụ | Kết luận chắc chắn thất bại rồi trừ chỗ lần nữa |

Một yêu cầu đăng ký có thể được gửi lại do người dùng nhấn hai lần, client retry hoặc proxy retry. Với chính sách mỗi người một chỗ, ràng buộc `UNIQUE(event_id, user_id)` giúp tránh thêm bản đăng ký trùng. Tuy nhiên, lỗi trả về cho client cần phân biệt “đã đăng ký trước đó” với “không còn chỗ” sau khi truy vấn trạng thái hiện tại.

Nếu một người được phép đặt nhiều chỗ, cần thêm **khóa chống lặp** do client gắn cho từng yêu cầu logic, ví dụ `request_id` duy nhất. Ghi khóa đó trong cùng giao dịch với kết quả nghiệp vụ; khi xử lý lại cùng khóa, trả kết quả đã lưu thay vì thực hiện thao tác lần hai. Đây là cách đạt hành vi idempotent cho nghiệp vụ, không phải lời hứa mạng sẽ gửi đúng một lần.

Nhật ký cần có mã tương quan yêu cầu, loại lỗi, thời lượng truy vấn và thông tin truy vết thích hợp; tránh ghi mật khẩu, token hoặc dữ liệu cá nhân không cần thiết. Kết nối lỗi nên được đóng/loại bỏ theo cơ chế của driver và pool; không tiếp tục sử dụng một giao dịch có trạng thái không chắc chắn.

**Bài tập:** mô phỏng client gửi lặp một yêu cầu. Đảm bảo chỉ có một bản đăng ký và một lần trừ chỗ; sau đó thử ngắt kết nối quanh thời điểm `commit` và giải thích vì sao kết quả có thể chưa xác định chỉ từ phía client.

## 9. Chặng 7 — Cô lập giao dịch và kiểm soát đồng thời

Giả sử chỉ còn **một** chỗ và hai người cùng đăng ký. Cách viết sau dễ phát sinh race condition:

```text
Yêu cầu A đọc seats_remaining = 1
Yêu cầu B đọc seats_remaining = 1
A quyết định có thể đặt
B quyết định có thể đặt
A ghi 0 và tạo đăng ký
B ghi 0 và tạo đăng ký
=> Có thể có hai đăng ký cho một chỗ
```

Vấn đề là quyết định “còn chỗ” dựa trên một giá trị đọc trước đó, không được bảo vệ trong lúc ghi. Ví dụ JDBC phía trên dùng một câu `UPDATE ... WHERE seats_remaining > 0` và kiểm tra số dòng bị tác động. Trên các DB quan hệ hỗ trợ cập nhật có điều kiện nguyên tử và khóa ghi phù hợp, những yêu cầu tranh cùng một hàng sẽ được điều phối để không cùng trừ từ 1 xuống 0 thành công.

Các mức cô lập thường gặp là `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`; tên mức giống nhau không bảo đảm mọi DB triển khai giống hệt nhau. Cần hiểu các hiện tượng như dirty read, non-repeatable read, phantom read, lost update và write skew rồi đối chiếu tài liệu của DB đang dùng.

| Chiến lược | Khi nào xem xét | Đánh đổi |
| --- | --- | --- |
| Cập nhật có điều kiện nguyên tử | Quy tắc nằm trên một hàng, như số chỗ còn lại | Đơn giản, nhưng chưa đủ cho mọi bất biến đa hàng |
| Khóa bi quan (`SELECT ... FOR UPDATE`) | Cần giữ một tập hàng ổn định khi quyết định | Có thể tăng chờ khóa và deadlock |
| Khóa lạc quan (`version`, cập nhật kèm phiên bản) | Va chạm không thường xuyên | Phải phát hiện xung đột và xử lý thử lại |
| `SERIALIZABLE` | Bất biến phức tạp cần tương đương một thứ tự tuần tự | Chi phí/khả năng phải thử lại giao dịch có thể tăng |

Một mức cô lập cao không thay thế cho thiết kế ràng buộc, thứ tự khóa nhất quán và kiểm tra kết quả cập nhật. Đối với quy tắc liên quan **nhiều hàng**, ví dụ giới hạn số đăng ký theo nhóm sự kiện, hãy đánh giá cụ thể nguy cơ write skew và chiến lược bảo vệ bất biến đó.

Đo đồng thời bằng kết quả cuối, không bằng cảm giác “test không lỗi”. Với sự kiện có hai chỗ, chạy nhiều yêu cầu đặt song song của các người dùng khác nhau. Sau khi tất cả kết thúc, kiểm tra:

- `seats_remaining = 0` nếu có ít nhất hai yêu cầu hợp lệ và DB hoạt động bình thường.
- Đúng hai bản đăng ký thành công; các yêu cầu còn lại bị từ chối hoặc được xử lý theo chính sách chờ.
- Không có bản đăng ký trùng và tổng số chỗ không vượt sức chứa.
- Khi ép lỗi ở bước chèn, mọi phần của giao dịch đều được rollback.

Các phép thử song song có giá trị khi chạy trên **DB thật tương ứng môi trường triển khai**, vì hành vi khóa và cô lập có thể khác DB giả lập trong bộ nhớ.

## 10. Chặng 8 — Tiến hóa schema, bảo mật và khả năng phục hồi

Ứng dụng đang chạy sẽ cần đổi schema, ví dụ thêm trạng thái đăng ký, thời điểm hủy hoặc khóa chống lặp. Hãy học quy trình migration có phiên bản; trong môi trường triển khai nhiều phiên bản ứng dụng cùng tồn tại, cân nhắc cách **mở rộng → chuyển dữ liệu → thu hẹp**:

1. Thêm cột/bảng hoặc chỉ mục theo cách phiên bản ứng dụng cũ vẫn vận hành được.
2. Triển khai ứng dụng ghi/đọc tương thích và backfill dữ liệu cũ theo lô nếu cần.
3. Kiểm tra dữ liệu, chuyển lưu lượng/phiên bản, rồi mới bỏ cấu trúc cũ khi đã an toàn.

Đọc kế hoạch migration, xem tác động khóa bảng, thời gian chạy và khả năng rollback trước khi triển khai. Không mặc định một thay đổi schema lớn là tức thời hoặc không ảnh hưởng đến thao tác ghi.

Các yêu cầu nền tảng phải đi cùng:

- **Bảo mật:** dùng truy vấn tham số hóa; cấp tài khoản ứng dụng quyền tối thiểu; quản lý bí mật ngoài mã nguồn; mã hóa đường truyền và dữ liệu nhạy cảm theo yêu cầu; kiểm soát truy cập dữ liệu theo người dùng.
- **Sao lưu và khôi phục:** xác định RPO (mức dữ liệu có thể mất) và RTO (thời gian cần phục hồi); thử khôi phục từ bản sao lưu, không chỉ kiểm tra có file backup. Cân nhắc khả năng khôi phục theo thời điểm (point-in-time recovery) nếu DB hỗ trợ.
- **Vận hành kết nối:** cấu hình connection pool, timeout, giới hạn số kết nối, giám sát lỗi và thời gian chờ; tránh giữ giao dịch mở trong lúc gọi dịch vụ bên ngoài hoặc thực hiện công việc tốn thời gian.
- **Quan sát:** đo số giao dịch thành công/thất bại, truy vấn chậm, độ trễ lấy kết nối, khóa chờ và deadlock. Đặt cảnh báo dựa trên triệu chứng có ảnh hưởng đến người dùng.

**Bài tập:** bổ sung cột `status` cho `reservations` theo migration có phiên bản. Mô tả cách triển khai khi phiên bản Java cũ vẫn chạy trong lúc triển khai phiên bản mới. Sau đó thực hành khôi phục DB thử nghiệm từ bản sao lưu.

## 11. Chặng 9 — Tối ưu dựa trên bằng chứng

Trước khi tối ưu, hãy biết hệ thống đang chậm ở đâu:

- **Truy vấn:** xem execution plan, chỉ mục, lọc, sắp xếp, số hàng đọc và lượng dữ liệu trả về.
- **Kết nối:** thời gian lấy connection, cấu hình pool, giới hạn phía DB và hành vi khi hết connection.
- **Giao dịch:** thời gian giữ khóa, số lần retry, deadlock và thao tác bên ngoài làm kéo dài transaction.
- **Mô hình truy cập:** tránh N+1 query, đọc quá nhiều cột hoặc trang kết quả quá lớn; cân nhắc batch/bulk operation khi đúng ngữ nghĩa.
- **Môi trường:** dùng dữ liệu, khối lượng ghi và mức đồng thời gần thực tế; kiểm tra cả độ trễ phần trăm cao, không chỉ trung bình.

Ví dụ, tạo thêm chỉ mục có thể tăng tốc danh sách đăng ký theo `user_id` nhưng làm chậm thao tác thêm đăng ký. Vì vậy, cần đo cả luồng đọc lẫn luồng ghi. Tối ưu chỉ được coi là có ích khi cải thiện mục tiêu đo được mà vẫn giữ đúng các bất biến ở phần đầu.

## 12. Bài thực hành tổng hợp và tiêu chí hoàn thành

Xây dựng API đăng ký workshop bằng Java và cơ sở dữ liệu quan hệ. Giữ chức năng ở mức nhỏ để tập trung vào persistence:

1. Tạo sự kiện với sức chứa cụ thể; đọc chi tiết và danh sách đăng ký.
2. Có migration tạo bảng, khóa, ràng buộc và các chỉ mục được chứng minh là cần thiết.
3. Thao tác đăng ký giảm số chỗ và tạo bản ghi trong cùng giao dịch; lỗi giữa chừng trả dữ liệu về trạng thái ban đầu.
4. Xử lý trường hợp đã đăng ký, hết chỗ, mất kết nối và yêu cầu gửi lặp theo những kết quả có thể giải thích.
5. Chạy nhiều yêu cầu song song tranh chỗ cuối cùng; kiểm tra kết quả cuối và số lần rollback.
6. Theo dõi truy vấn chậm, cấu hình timeout/pool, thử phục hồi một bản sao lưu và mô tả một migration tương thích.

**Tự đánh giá bằng các câu hỏi sau:**

- Dữ liệu có tồn tại sau khi ứng dụng khởi động lại không? Khi nào dữ liệu có thể mất dù vừa thấy phản hồi thành công?
- Ràng buộc nào đặt ở DB, ràng buộc nào cần logic nghiệp vụ, và vì sao?
- Nếu `INSERT reservations` thất bại sau `UPDATE events`, điều gì bảo vệ số chỗ còn lại?
- Tại sao `SELECT` số chỗ rồi `UPDATE` ở hai bước có thể sai khi có nhiều yêu cầu?
- Khi client không nhận được phản hồi `commit`, làm sao biết có thể thử lại?
- Khi tăng mức cô lập, có hiện tượng nào giảm đi và chi phí nào có thể tăng?
- Bản sao lưu gần nhất đã được **khôi phục thử** chưa, và thời gian phục hồi có đáp ứng mục tiêu không?
- Số đo nào chứng minh một chỉ mục hoặc thay đổi pool thực sự cải thiện hệ thống?

Hoàn thành lộ trình nghĩa là người học có thể nối kết **thiết kế dữ liệu → truy cập từ Java → giao dịch → xử lý lỗi → kiểm soát đồng thời → vận hành** thành một hành vi đáng tin cậy. Điểm quyết định không phải số câu SQL đã viết mà là khả năng **chỉ ra bất biến cần giữ, cơ chế giữ nó và phép thử chứng minh cơ chế hoạt động**.
