# Điểm lưu (savepoint) và giới hạn khôi phục một phần

Trong một giao dịch cơ sở dữ liệu, đôi khi ứng dụng cần thử một thao tác có thể thất bại nhưng vẫn muốn giữ những thay đổi hợp lệ đã thực hiện trước đó. **Điểm lưu (savepoint)** là mốc nằm *bên trong một giao dịch đang mở*, cho phép quay lại mốc ấy mà không nhất thiết phải hủy toàn bộ giao dịch. Cơ chế này thường xuất hiện trong xử lý theo lô, quy trình có bước tùy chọn, hoặc đoạn mã Java cần phục hồi từ một lỗi SQL cụ thể.

Ví dụ: hệ thống tạo đơn hàng bắt buộc phải lưu bản ghi đơn và sự kiện tạo đơn. Việc gắn một nhãn phục vụ giao diện chỉ là tính năng tùy chọn; nếu mã nhãn không còn tồn tại, hệ thống có thể hủy những thay đổi liên quan đến nhãn, tiếp tục lưu sự kiện chính và hoàn tất đơn hàng. Savepoint giúp xác định chính xác phạm vi cần hủy.

Trong phạm vi **DATA_PERSISTENCE_FUNDAMENTALS**, hiểu savepoint còn đòi hỏi nắm ranh giới giao dịch của tầng persistence Java, cách xử lý lỗi kết nối và sự khác biệt giữa khôi phục một phần dữ liệu với khôi phục cả quy trình nghiệp vụ. Savepoint **không** tạo ra một giao dịch đã commit độc lập.

## 1. Ba thao tác: tạo, quay lại và giải phóng điểm lưu

Các hệ quản trị có hỗ trợ savepoint thường cung cấp các lệnh tương tự:

```sql
BEGIN;

-- Thay đổi A: bắt buộc
SAVEPOINT before_optional_step;

-- Thay đổi B: có thể hủy nếu bước tùy chọn thất bại
ROLLBACK TO SAVEPOINT before_optional_step;

-- Có thể giải phóng mốc sau khi không còn cần dùng
RELEASE SAVEPOINT before_optional_step;

-- Thay đổi C: bắt buộc, thực hiện sau khi phục hồi
COMMIT;
```

Phần trên là **sơ đồ cú pháp**; những dòng "Thay đổi A/B/C" cần được thay bằng SQL thật. Ý nghĩa từng lệnh:

| Lệnh | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `SAVEPOINT name` | Đặt một mốc trong giao dịch hiện tại. | Chỉ có ý nghĩa khi đang có giao dịch mở; cần DB/driver hỗ trợ. |
| `ROLLBACK TO SAVEPOINT name` | Hoàn tác những thay đổi thuộc giao dịch kể từ mốc đã chọn. | Những thay đổi trước mốc vẫn còn *chưa commit*; giao dịch có thể tiếp tục. |
| `RELEASE SAVEPOINT name` | Bỏ mốc savepoint khi không cần quay lại mốc đó. | **Không commit** bất kỳ thay đổi nào. |
| `COMMIT` | Xác nhận giao dịch hiện tại. | Những thay đổi còn tồn tại sau các lần rollback tới savepoint mới được commit. |
| `ROLLBACK` (không có `TO`) | Hủy toàn bộ giao dịch đang mở. | Hủy cả thay đổi trước và sau savepoint, trừ các hiệu ứng không thuộc phạm vi giao dịch. |

Hình dung dòng thời gian:

```text
BEGIN
  |
  +-- A: tạo đơn hàng            [giữ lại]
  |
  +-- SAVEPOINT s1  <----------- mốc khôi phục
  |
  +-- B1: tạo ghi chú giao diện  [hủy]
  +-- B2: gắn nhãn không hợp lệ [lỗi]
  |
  +-- ROLLBACK TO s1 ------------ trở lại trạng thái tại s1
  |
  +-- C: ghi sự kiện tạo đơn    [giữ lại]
  |
COMMIT                            A và C được commit
```

Việc "quay lại" mốc chỉ khôi phục trạng thái dữ liệu theo khả năng của hệ quản trị, không làm thời gian chạy chương trình quay ngược. Mã Java, lời gọi HTTP, email đã gửi và các hiệu ứng bên ngoài vẫn đã xảy ra.

## 2. Ví dụ SQL: một nhóm bước tùy chọn thất bại

Ví dụ sau dùng **PostgreSQL**. Giả sử ứng dụng có các bảng:

```sql
CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    status       VARCHAR(20) NOT NULL
);

CREATE TABLE tags (
    tag_id   BIGINT PRIMARY KEY,
    tag_name VARCHAR(40) NOT NULL
);

CREATE TABLE order_ui_notes (
    order_id BIGINT PRIMARY KEY REFERENCES orders(order_id),
    note     TEXT NOT NULL
);

CREATE TABLE order_tags (
    order_id BIGINT PRIMARY KEY REFERENCES orders(order_id),
    tag_id   BIGINT NOT NULL REFERENCES tags(tag_id)
);

CREATE TABLE order_events (
    order_id   BIGINT NOT NULL REFERENCES orders(order_id),
    event_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (order_id, event_type)
);
```

Quy tắc nghiệp vụ ở đây là: **đơn hàng và sự kiện tạo đơn phải thành công cùng nhau**; ghi chú và nhãn hiển thị chỉ được lưu nếu *cả hai* đều thành công. Bởi `order_tags.tag_id` có khóa ngoại đến `tags`, một mã nhãn không tồn tại sẽ gây lỗi ràng buộc.

Trong cùng một phiên kết nối, có thể thực hiện từng bước như sau (giả sử mã nhãn `999999` chưa có trong `tags`):

```sql
BEGIN;

INSERT INTO orders (order_id, customer_id, total_amount, status)
VALUES (1001, 42, 250000, 'NEW');

SAVEPOINT before_optional_tag;

INSERT INTO order_ui_notes (order_id, note)
VALUES (1001, 'Hiển thị nhãn quà tặng');

-- Lệnh sau thất bại nếu tag_id = 999999 không có trong tags.
INSERT INTO order_tags (order_id, tag_id)
VALUES (1001, 999999);

-- Sau lỗi, ứng dụng bắt ngoại lệ và thực hiện:
ROLLBACK TO SAVEPOINT before_optional_tag;
RELEASE SAVEPOINT before_optional_tag;

INSERT INTO order_events (order_id, event_type)
VALUES (1001, 'CREATED');

COMMIT;
```

Trong PostgreSQL, khi câu `INSERT INTO order_tags` vi phạm khóa ngoại (SQLSTATE `23503`), trạng thái phần giao dịch sau savepoint bị lỗi. Trước khi tiếp tục với SQL thông thường, ứng dụng cần `ROLLBACK TO SAVEPOINT before_optional_tag`. Sau lệnh này, bản ghi ghi chú tạo sau mốc cũng bị hủy; bản ghi `orders` tạo trước mốc vẫn còn trong giao dịch. Câu `INSERT INTO order_events` sau đó có thể thành công và `COMMIT` sẽ xác nhận đơn hàng cùng sự kiện.

Để chạy ví dụ lỗi theo dạng thủ công, cần cho phép tiếp tục gửi lệnh sau lỗi trong cùng phiên giao dịch; một SQL client được cấu hình dừng toàn bộ script ngay khi có lỗi sẽ không tự chạy các câu `ROLLBACK TO` ở phía sau. Trong ứng dụng thực, cần bắt lỗi và phát lệnh phục hồi một cách có kiểm soát.

**Nếu hai bước tùy chọn đều thành công**, không gọi `ROLLBACK TO`; chỉ `RELEASE SAVEPOINT before_optional_tag` trước khi tiếp tục các bước bắt buộc. Có thể tự kiểm tra trạng thái sau ví dụ lỗi bằng:

```sql
SELECT * FROM orders WHERE order_id = 1001;
SELECT * FROM order_ui_notes WHERE order_id = 1001;
SELECT * FROM order_tags WHERE order_id = 1001;
SELECT * FROM order_events WHERE order_id = 1001;
```

Kết quả kỳ vọng: có đơn hàng `1001` và sự kiện `CREATED`; không có ghi chú và nhãn đã bị hủy. Điều này đúng khi các câu lệnh thật sự chạy trong một giao dịch và `COMMIT` thành công.

## 3. Savepoint không phải giao dịch lồng độc lập

Một số tài liệu gọi savepoint là hình thức "nested transaction", nhưng cách hiểu chính xác là **mốc hoàn tác nằm trong cùng giao dịch cha**. Giả sử:

```sql
BEGIN;
INSERT INTO orders (order_id, customer_id, total_amount, status)
VALUES (1002, 42, 100000, 'NEW');

SAVEPOINT after_order;
INSERT INTO order_events (order_id, event_type)
VALUES (1002, 'CREATED');
RELEASE SAVEPOINT after_order;

ROLLBACK;
```

Dù đã `RELEASE SAVEPOINT`, lệnh `ROLLBACK` cuối cùng vẫn xóa *cả hai* bản ghi. Bởi vậy:

- Không có thao tác "commit riêng phần B" chỉ bằng `RELEASE SAVEPOINT`.
- Nếu giao dịch cha bị rollback, tất cả những thay đổi có thể hoàn tác trong giao dịch đó đều bị hủy.
- Savepoint dùng **cùng kết nối, cùng ranh giới giao dịch** và không tự tạo một cấp cô lập mới.
- Nếu cần một thao tác thực sự commit dù giao dịch chính bị hủy, đó là yêu cầu về **giao dịch khác**, với các rủi ro nhất quán riêng; savepoint không đáp ứng được.

Một giao dịch có thể có nhiều savepoint. Ví dụ `s1` rồi `s2`: khi quay về `s1`, các thay đổi sau `s1` được hủy và các mốc tạo sau `s1` không còn dùng được theo cách hoạt động của PostgreSQL. `ROLLBACK TO s1` không tự xóa `s1`; có thể quay về nó thêm lần nữa hoặc giải phóng nó sau khi phục hồi. Nên dùng tên rõ ràng và tránh đặt trùng tên trong cùng giao dịch để tránh nhập nhằng khi chọn mốc.

## 4. Những giới hạn quan trọng của khôi phục một phần

### 4.1. Không cứu được lỗi xảy ra trước mốc

Nếu câu `INSERT orders` thất bại trước khi tạo savepoint, việc quay về mốc phía sau (nếu chưa từng được tạo) là bất khả thi. Ngay cả khi đã có savepoint trước đó, hủy đến mốc ấy có thể loại bỏ các thay đổi mà nghiệp vụ coi là bắt buộc. Khi không thể giữ các bất biến của giao dịch, phải **rollback toàn bộ**.

### 4.2. Không thay thế quyết định nghiệp vụ

Chỉ nên bỏ qua lỗi ở bước tùy chọn khi nghiệp vụ cho phép. Ví dụ, nhãn giao diện bị thiếu có thể chấp nhận được; nhưng lỗi trừ tiền, cập nhật tồn kho hay ghi nhật ký bắt buộc thường phải làm thất bại cả giao dịch. Nếu người mua đã được hứa một mức giá giảm nhờ mã ưu đãi, không thể tự ý bỏ qua lỗi áp mã rồi commit ở giá khác mà không xử lý yêu cầu nghiệp vụ.

Trong code, **không bắt mọi `SQLException` rồi mặc nhiên tiếp tục**. Lỗi kết nối, lỗi giao dịch, deadlock hay lỗi dữ liệu ngoài dự kiến có thể khiến quá trình tiếp tục không an toàn. Chỉ phục hồi một phần khi đã xác định loại lỗi cụ thể, thao tác còn khả dụng và kết quả phù hợp quy tắc nghiệp vụ.

### 4.3. Không hoàn tác tác động ngoài cơ sở dữ liệu

Savepoint chỉ tác động đến dữ liệu và tài nguyên mà hệ quản trị có khả năng quản lý trong giao dịch. Nó không thu hồi email/SMS đã gửi, file đã ghi, HTTP request sang đối tác, sự kiện đã publish trực tiếp hay tiền đã thu ở một dịch vụ thanh toán riêng. Những hệ thống cần phối hợp các tác động này thường sử dụng transactional outbox, xử lý idempotent, saga hoặc các bước bù trừ phù hợp. Không nên gửi sự kiện ra broker trước khi biết trạng thái commit nếu hệ thống đòi hỏi thông tin chính xác.

### 4.4. Không đảo ngược tất cả bộ đếm hay trạng thái phụ

Trong PostgreSQL, giá trị được cấp từ `SEQUENCE` / `nextval()` không bị lấy lại khi rollback về savepoint. Vì vậy có thể có khoảng trống ID dù bản ghi tương ứng đã bị hủy. Nhiều hệ quản trị có cơ chế cấp ID tương tự; không nên suy diễn rằng ID phải liên tục hoặc chính xác về số lượng giao dịch thành công.

Khóa và tài nguyên cũng có quy tắc riêng: PostgreSQL thông thường giải phóng các khóa được lấy sau savepoint khi rollback đến mốc đó; ở những hệ khác như InnoDB, một số khóa có thể tiếp tục được giữ. Vì vậy không thiết kế kiểm soát đồng thời dựa trên giả định rằng `ROLLBACK TO SAVEPOINT` luôn giải phóng *mọi* khóa đã lấy.

### 4.5. Không chống được lỗi commit hoặc mất kết nối

Lệnh `ROLLBACK TO SAVEPOINT` cũng có thể thất bại, chẳng hạn do kết nối hỏng hoặc savepoint không còn hợp lệ. Sau khi phục hồi thành công, `COMMIT` vẫn có thể thất bại vì kiểm tra ràng buộc trì hoãn, xung đột cô lập hoặc lỗi hệ thống. Khi mất kết nối đúng thời điểm gửi `COMMIT`, phía ứng dụng thậm chí có thể **không biết chắc** giao dịch đã commit hay chưa. Cách xử lý cần dựa vào khóa nghiệp vụ duy nhất, truy vấn đối soát và retry có idempotency, không coi savepoint là bảo đảm giao dịch sẽ hoàn tất.

### 4.6. Không vượt qua ranh giới transaction hoặc DDL

Khi giao dịch cha đã `COMMIT` hoặc `ROLLBACK`, các savepoint trong đó không còn dùng được. Một số câu DDL hoặc thao tác đặc biệt có thể gây *implicit commit* tùy hệ quản trị (đáng chú ý là nhiều lệnh DDL trong MySQL). Vì vậy phải kiểm tra đặc tính của DB đang dùng trước khi kỳ vọng rollback tới savepoint có thể hoàn tác thay đổi schema.

## 5. Sử dụng savepoint bằng JDBC trong Java

JDBC cung cấp `java.sql.Savepoint` và các phương thức trên `Connection`:

```java
Savepoint point = connection.setSavepoint("before_optional_tag");
connection.rollback(point);           // quay lại mốc
connection.releaseSavepoint(point);   // giải phóng mốc
```

Những lời gọi này thường yêu cầu `autoCommit = false` và driver/database hỗ trợ savepoint. Có thể kiểm tra qua `connection.getMetaData().supportsSavepoints()`. Không sử dụng savepoint trên kết nối đang ở chế độ tự động commit từng câu lệnh; trong tình huống đó không có một giao dịch dài để quay về.

Ví dụ sau minh họa **một service tự sở hữu giao dịch**: nhận `DataSource`, lấy kết nối riêng và đóng kết nối khi xong. Nhãn và ghi chú là tùy chọn; nếu mã nhãn không tồn tại và gây lỗi khóa ngoại PostgreSQL `23503`, service loại bỏ *cả hai* thay đổi tùy chọn và vẫn có thể hoàn tất đơn hàng. Các lỗi khác sẽ làm hủy toàn bộ giao dịch.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;

public final class OrderWriter {
    private final DataSource dataSource;

    public OrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(long orderId, long customerId,
                            BigDecimal total, Long optionalTagId)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                insertOrder(connection, orderId, customerId, total);

                if (optionalTagId != null) {
                    Savepoint sp = connection.setSavepoint("before_optional_tag");
                    try {
                        insertUiNote(connection, orderId);
                        insertTag(connection, orderId, optionalTagId);
                        connection.releaseSavepoint(sp);
                    } catch (SQLException optionalError) {
                        // PostgreSQL: phục hồi subtransaction lỗi trước
                        // khi thực hiện các câu SQL tiếp theo.
                        connection.rollback(sp);
                        connection.releaseSavepoint(sp);
                        if (!"23503".equals(optionalError.getSQLState())) {
                            throw optionalError;
                        }
                        // Nhãn không tồn tại: nghiệp vụ cho phép bỏ qua
                        // cả nhãn lẫn ghi chú, rồi tiếp tục tạo đơn.
                    }
                }

                insertCreatedEvent(connection, orderId);
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback(); // lỗi không phục hồi được
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    private static void insertOrder(Connection c, long orderId,
                                    long customerId, BigDecimal total)
            throws SQLException {
        String sql = """
            INSERT INTO orders (order_id, customer_id, total_amount, status)
            VALUES (?, ?, ?, 'NEW')
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setLong(2, customerId);
            ps.setBigDecimal(3, total);
            ps.executeUpdate();
        }
    }

    private static void insertUiNote(Connection c, long orderId)
            throws SQLException {
        String sql = """
            INSERT INTO order_ui_notes (order_id, note)
            VALUES (?, 'Hiển thị nhãn tùy chọn')
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.executeUpdate();
        }
    }

    private static void insertTag(Connection c, long orderId, long tagId)
            throws SQLException {
        String sql = "INSERT INTO order_tags (order_id, tag_id) VALUES (?, ?)";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setLong(2, tagId);
            ps.executeUpdate();
        }
    }

    private static void insertCreatedEvent(Connection c, long orderId)
            throws SQLException {
        String sql = """
            INSERT INTO order_events (order_id, event_type)
            VALUES (?, 'CREATED')
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.executeUpdate();
        }
    }
}
```

Điểm cần đọc kỹ:

1. `setAutoCommit(false)` khiến các lệnh chạy chung một giao dịch. Kết nối được service tự lấy và đóng, vì thế service được phép quyết định `commit` hoặc `rollback`. Nếu nhận kết nối/giao dịch do tầng gọi quản lý, **không tự commit hoặc đổi auto-commit**: phải tuân theo quyền sở hữu giao dịch của tầng đó.
2. Savepoint được tạo **sau** bản ghi đơn bắt buộc, **trước** hai câu ghi dữ liệu tùy chọn. Nếu `insertTag` thất bại, `rollback(sp)` hủy cả `insertUiNote`.
3. Lỗi khóa ngoại `23503` được bỏ qua theo quy tắc nghiệp vụ **chỉ trong phạm vi bước tùy chọn này**. Nếu thêm các ràng buộc khóa ngoại khác vào đoạn ghi tùy chọn, phải nhận diện lỗi đủ cụ thể để tránh vô tình bỏ qua lỗi sai đối tượng. Với các lỗi ngoài dự kiến, service ném lại ngoại lệ để rollback toàn phần.
4. Nếu `rollback(sp)` hoặc `releaseSavepoint(sp)` thất bại, ngoại lệ lan ra vòng `catch` ngoài, nơi service cố gắng rollback toàn bộ. Việc xử lý lỗi kết nối có thể cần phân loại riêng ở tầng điều phối và có chiến lược retry/idempotency.
5. `PreparedStatement` gắn các tham số dữ liệu và đóng tài nguyên bằng `try-with-resources`. Dù `releaseSavepoint` thành công, chỉ `connection.commit()` mới xác nhận giao dịch.

Đây là ví dụ JDBC có chủ đích minh họa savepoint trên PostgreSQL. Trong sản phẩm thực tế, hãy kiểm tra `SQLException.getSQLState()` đúng với DB/driver, theo dõi lỗi được bỏ qua và chọn thông báo phù hợp cho khách hàng. Nếu lỗi chỉ là mã nhãn không hợp lệ, xác thực hoặc kiểm tra tồn tại trước khi ghi cũng đáng cân nhắc; savepoint vẫn hữu ích khi nhiều thay đổi tùy chọn đã được thực hiện và cần hoàn tác theo nhóm.

## 6. Savepoint với framework và các hệ quản trị

| Môi trường | Cách dùng / giới hạn thường gặp |
| --- | --- |
| PostgreSQL | Hỗ trợ `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, `RELEASE SAVEPOINT`. Sau nhiều loại lỗi SQL trong transaction, cần rollback đến savepoint hợp lệ hoặc rollback toàn bộ trước khi tiếp tục. Có thể có tác động không được rollback như `nextval()`. |
| MySQL với InnoDB | Có savepoint trong transaction; cần lưu ý các lệnh gây implicit commit và việc giải phóng khóa sau rollback đến savepoint không hoàn toàn giống PostgreSQL. |
| SQLite | Hỗ trợ `SAVEPOINT`, `ROLLBACK TO` và `RELEASE`; có thể dùng với cơ chế transaction lồng theo ngăn xếp savepoint. `RELEASE` một savepoint bên trong không nhất thiết là commit bền vững cho toàn giao dịch bên ngoài. |
| JDBC | Dùng `Connection.setSavepoint()`, `rollback(Savepoint)` và `releaseSavepoint()` nếu driver hỗ trợ; cần quản lý `autoCommit` và vòng đời kết nối. |
| Spring | `Propagation.NESTED` có thể dùng JDBC savepoint trên cùng giao dịch vật lý **nếu** transaction manager và tài nguyên hỗ trợ; `REQUIRES_NEW` thường tạo giao dịch vật lý độc lập. Không thể mặc định mọi cấu hình JPA đều hỗ trợ `NESTED`. |

Một lưu ý về framework: lỗi xảy ra trong một transaction do Spring quản lý có thể đã khiến trạng thái giao dịch bị đánh dấu `rollback-only`; thao tác tạo hoặc quay lại savepoint ở tầng thấp không tự xóa mọi quyết định rollback của transaction manager. Vì vậy hãy đặt ranh giới quản lý lỗi tại cùng lớp sở hữu giao dịch, cấu hình propagation phù hợp và kiểm thử trường hợp ngoại lệ thực tế.

## 7. Khi nào nên dùng và khi nào nên tránh?

**Các tình huống hợp lý:** một bước bổ sung không bắt buộc gồm nhiều câu SQL, mỗi phần tử trong một đợt xử lý có thể bị bỏ qua theo quy tắc rõ ràng, hoặc một đoạn thao tác dự kiến có thể gặp lỗi ràng buộc mà vẫn khôi phục được và vẫn giữ được các bất biến nghiệp vụ.

**Các tình huống cần giải pháp khác:** ghi dữ liệu qua nhiều database, gọi cổng thanh toán, phát sự kiện cho dịch vụ khác, nghiệp vụ đòi hỏi rollback toàn bộ khi một bước thất bại, hoặc cần xác nhận độc lập một phần dữ liệu trước khi giao dịch chính hoàn tất.

Savepoint có chi phí quản lý trạng thái transaction. Nếu tạo hàng chục nghìn savepoint tồn tại đồng thời trong một giao dịch dài, có thể tốn tài nguyên và làm việc quản lý lỗi/khóa phức tạp. Ưu tiên giao dịch có thời lượng hợp lý; giải phóng mốc khi không còn cần; dùng batch, upsert hoặc xử lý lại theo lô nếu thích hợp. Với trường hợp xử lý trùng khóa đơn giản, câu lệnh như PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` đôi khi dễ hiểu và ít phức tạp hơn việc cố ý gây lỗi rồi rollback đến savepoint.

## 8. Thực hành và câu hỏi kiểm tra

**Bài tập 1 — theo dõi trạng thái.** Một transaction lần lượt chạy:

```sql
BEGIN;
INSERT INTO orders (order_id, customer_id, total_amount, status)
VALUES (2001, 9, 120000, 'NEW');

SAVEPOINT s1;
INSERT INTO order_events (order_id, event_type)
VALUES (2001, 'CREATED');

SAVEPOINT s2;
INSERT INTO order_ui_notes (order_id, note)
VALUES (2001, 'Mẫu ghi chú');

ROLLBACK TO SAVEPOINT s2;
ROLLBACK TO SAVEPOINT s1;
COMMIT;
```

Hãy dự đoán hàng nào còn tồn tại ở ba bảng `orders`, `order_events` và `order_ui_notes`. Sau đó tự chạy trên cơ sở dữ liệu thử nghiệm và so sánh. **Đáp án:** chỉ bản ghi `orders(2001, ...)` còn lại; sự kiện bị rollback ở `s1`, ghi chú bị rollback ở `s2`.

**Bài tập 2 — xử lý lỗi.** Nếu `insertCreatedEvent` trong ví dụ Java gặp lỗi kết nối, có nên dùng savepoint tùy chọn để bỏ qua lỗi rồi commit đơn không? **Không:** đây là bước bắt buộc và cũng có thể là lỗi khiến kết nối không còn dùng được. Cần rollback toàn bộ khi khả thi, ném lỗi cho tầng gọi và xử lý khả năng kết quả commit không rõ ràng theo thiết kế ứng dụng.

**Bài tập 3 — phân biệt cơ chế.** Trong Spring, hãy giải thích vì sao `NESTED` (khi thực sự dùng savepoint trên cùng transaction) và `REQUIRES_NEW` cho kết quả khác nhau nếu transaction cha cuối cùng bị rollback. **Gợi ý:** savepoint chỉ cho phép hoàn tác từng phần của giao dịch cha; giao dịch độc lập có thể commit riêng, đồng thời cần xét rủi ro không nhất quán giữa hai giao dịch.

### Checklist trước khi dùng savepoint trong dịch vụ Java

- Đã xác định những thay đổi nào **bắt buộc** và nhóm thay đổi nào được phép hủy độc lập theo nghiệp vụ chưa?
- Code có sở hữu giao dịch/kết nối không? Driver có hỗ trợ savepoint, và `autoCommit` có phù hợp không?
- Sau một lỗi SQL, có rollback đến savepoint **trước** khi tiếp tục? Có xử lý được trường hợp rollback đến savepoint cũng thất bại không?
- Chỉ những lỗi dự kiến, được nhận diện đủ cụ thể mới được bỏ qua? Giao dịch cha còn giữ được các bất biến dữ liệu không?
- Có side effect ngoài DB, cấp ID, DDL, khóa hoặc kiểm tra ràng buộc tại commit khiến việc "khôi phục" chưa đầy đủ không?
- Đã kiểm tra tình huống thành công, lỗi tùy chọn, lỗi bắt buộc và lỗi commit bằng dữ liệu thử nghiệm chưa?

Điểm cốt lõi của savepoint là **giảm phạm vi hoàn tác bên trong một giao dịch đang mở**. Kết quả cuối cùng vẫn phụ thuộc vào giao dịch cha, đặc tính của hệ quản trị và quyết định nghiệp vụ về những lỗi được phép phục hồi.
