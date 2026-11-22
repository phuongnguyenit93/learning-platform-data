# Chế độ auto-commit và giao dịch tường minh

Một ứng dụng lưu dữ liệu bền vững không chỉ cần ghi được từng câu SQL. Nó còn phải bảo đảm rằng **nhiều thay đổi có liên quan cùng thành công hoặc cùng bị hủy**, nhất là khi gặp lỗi kết nối, vi phạm ràng buộc hay hai yêu cầu xử lý đồng thời. Sự khác biệt giữa **auto-commit** và **giao dịch tường minh** quyết định ranh giới mà hệ quản trị cơ sở dữ liệu coi là một đơn vị công việc.

Đây là bài thuộc chương **Giao dịch** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu của module là hiểu nền tảng persistence cho ứng dụng Java: mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, cô lập và đồng thời; từ đó tổ chức ranh giới truy cập dữ liệu, xử lý lỗi, bảo mật và tối ưu hiệu năng. Ví dụ trong bài tập trung vào **JDBC, SQL và Spring**, sử dụng PostgreSQL để minh họa hành vi hệ quản trị; chi tiết về DDL, lỗi và chế độ kết nối có thể khác ở hệ cơ sở dữ liệu khác.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích một câu lệnh SQL được xác nhận như thế nào khi bật **auto-commit**, và vì sao nhiều lệnh nối tiếp không tự động trở thành một giao dịch duy nhất.
- Xác định ranh giới **BEGIN / COMMIT / ROLLBACK** cho một thao tác nghiệp vụ gồm nhiều bước.
- Sử dụng **Connection.setAutoCommit(false)**, **commit()**, **rollback()** trong JDBC; quản lý lỗi và vòng đời connection đúng cách.
- Hiểu vai trò của **@Transactional** trong Spring và các giới hạn khi đi qua proxy, luồng xử lý hoặc kết nối ngoài giao dịch.
- Phân biệt điều **atomicity** bảo đảm với những điều cần thêm **isolation**, ràng buộc dữ liệu, khóa, xử lý retry và thiết kế tích hợp.

## 2. Giao dịch là gì và COMMIT có nghĩa gì?

**Giao dịch (transaction)** là một tập thao tác cơ sở dữ liệu được quản lý như một đơn vị. Bốn thuộc tính ACID thường được dùng để mô tả yêu cầu với giao dịch:

| Thuộc tính | Ý nghĩa trong ứng dụng |
| --- | --- |
| **Atomicity** | Các thay đổi của một giao dịch được xác nhận cùng nhau hoặc hủy cùng nhau |
| **Consistency** | Giao dịch đúng, kết hợp với các ràng buộc và quy tắc nghiệp vụ, đưa dữ liệu giữa các trạng thái hợp lệ |
| **Isolation** | Quy định mức độ các giao dịch đang chạy được quan sát và ảnh hưởng lẫn nhau |
| **Durability** | Khi hệ quản trị xác nhận commit thành công, thay đổi có độ bền theo cam kết và cấu hình của hệ thống |

**COMMIT** yêu cầu hệ quản trị xác nhận giao dịch hiện tại; **ROLLBACK** yêu cầu hủy các thay đổi chưa được commit của giao dịch hiện tại. ROLLBACK không phải nút “hoàn tác mọi việc”: nó không thu hồi được một email đã gửi, lệnh gọi API ngoài hệ quản trị hay thay đổi đã commit ở giao dịch trước.

Trạng thái giao dịch cũng không đồng nghĩa hoàn toàn với trạng thái kết nối mạng: khi kết nối bị đứt đúng thời điểm gửi **COMMIT**, client có thể **không biết** server đã commit hay chưa. Việc xử lý trường hợp kết quả không chắc chắn cần định danh yêu cầu, kiểm tra lại trạng thái và thiết kế idempotent.

## 3. Auto-commit: mỗi câu lệnh là một ranh giới giao dịch

Khi **auto-commit được bật**, mỗi câu lệnh SQL chạy thành công sẽ được commit tự động sau khi câu lệnh hoàn tất, thay vì chờ ứng dụng gọi **commit()**. Với JDBC, kết nối mới thông thường bắt đầu ở **auto-commit = true** theo hợp đồng JDBC, nhưng mã ứng dụng nên biết rõ trạng thái thực tế của kết nối do DataSource hoặc transaction manager cung cấp.

Ví dụ một luồng dùng hai câu lệnh độc lập:

~~~sql
UPDATE accounts
SET balance = balance - 100.00
WHERE id = 101;

UPDATE accounts
SET balance = balance + 100.00
WHERE id = 202;
~~~

Nếu client thực hiện hai câu lệnh lần lượt dưới auto-commit, diễn biến có thể là:

~~~text
UPDATE tài khoản 101  --> thành công --> COMMIT #1
UPDATE tài khoản 202  --> lỗi         --> ROLLBACK #2
                                    |
                      Tiền đã trừ nhưng chưa được cộng
~~~

Một câu lệnh đơn lẻ vẫn được xử lý có tính nguyên tử ở phạm vi giao dịch của chính nó; vấn đề ở đây là **hai câu lệnh không cùng một ranh giới atomicity**.

### Khi nào auto-commit phù hợp?

Auto-commit có thể đủ cho thao tác độc lập như cập nhật một bản ghi riêng lẻ, hoặc một câu lệnh DML đã thể hiện trọn quy tắc nghiệp vụ, ví dụ:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity >= 1;
~~~

Ứng dụng phải kiểm tra số hàng cập nhật: **1** nghĩa là thao tác đã áp dụng trên một bản ghi; **0** nghĩa là không tìm thấy hàng đủ điều kiện (hoặc sản phẩm không tồn tại). Điều kiện **quantity >= 1** được đánh giá trong chính câu UPDATE, tránh kiểu kiểm tra số lượng trước rồi cập nhật sau mà không có cơ chế đồng thời.

Tuy nhiên, nếu nghiệp vụ còn phải ghi lịch sử xuất kho, tạo đơn hàng và đổi trạng thái, auto-commit từng câu có thể khiến hệ thống dừng giữa chừng. Khi ấy cần bao các thao tác liên quan trong một giao dịch.

### Điều quan trọng với SELECT

Đối với JDBC auto-commit, thời điểm “câu lệnh hoàn tất” có thể liên quan đến việc **đọc hết hoặc đóng ResultSet** và các kết quả khác của câu lệnh; không nên giả định mọi tài nguyên SELECT đều đã hoàn tất ngay khi executeQuery() trả về. Với cursor/streaming result, vòng đời tài nguyên có thể kéo dài. Luôn đóng **ResultSet, Statement và Connection** phù hợp, nhất là khi dùng connection pool.

## 4. Giao dịch tường minh: ứng dụng chọn ranh giới

Khi nghiệp vụ gồm nhiều lệnh cần thành công cùng nhau, hãy xác định giao dịch ở mức **một đơn vị nghiệp vụ có thể xác nhận**. Ví dụ luồng chuyển tiền nội bộ:

1. Trừ tiền ở tài khoản nguồn nếu số dư đủ.
2. Cộng tiền vào tài khoản đích.
3. Ghi bản ghi chuyển tiền để phục vụ đối soát.
4. Chỉ **COMMIT** sau khi mọi bước hợp lệ; nếu bất kỳ bước nào thất bại, **ROLLBACK** toàn bộ.

Ví dụ SQL minh họa cách khai báo giao dịch ở PostgreSQL:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100.00
WHERE id = 101 AND balance >= 100.00;

-- Ứng dụng phải xác nhận chính xác một hàng đã được cập nhật.
UPDATE accounts
SET balance = balance + 100.00
WHERE id = 202;

-- Ứng dụng phải xác nhận chính xác một hàng đã được cập nhật.
INSERT INTO transfers (request_id, from_account_id, to_account_id, amount)
VALUES ('9d32a7ab-3894-428c-93df-d4ee5b753821', 101, 202, 100.00);

COMMIT;
~~~

Đoạn trên minh họa **ranh giới**, không phải script có đầy đủ nhánh kiểm tra: nếu UPDATE trừ tiền hoặc cộng tiền tác động **0 hàng**, ứng dụng cần gọi **ROLLBACK** thay vì tiếp tục tới COMMIT. Cơ sở dữ liệu nên có ràng buộc **PRIMARY KEY / FOREIGN KEY / UNIQUE**, cùng **CHECK (balance >= 0)** hoặc quy tắc thích hợp. Nếu có ràng buộc duy nhất trên **transfers.request_id**, hệ thống còn có điểm tựa kiểm tra yêu cầu lặp; xử lý idempotency đầy đủ được trình bày sau.

Hình dung diễn biến:

~~~text
BEGIN
  |
  +-- UPDATE account nguồn ------+
  |                              |
  +-- UPDATE account đích -------+-- nếu cả ba thành công --> COMMIT
  |                              |
  +-- INSERT transfer -----------+
  |
  +-- bất kỳ lỗi/kiểm tra không đạt --> ROLLBACK
~~~

Trong PostgreSQL, dùng **BEGIN** và **START TRANSACTION** là cách khởi đầu giao dịch SQL. Trong JDBC, ứng dụng thường sử dụng API của **Connection** để bật chế độ thủ công thay vì gửi riêng câu BEGIN; nên chọn một cơ chế điều phối nhất quán để tránh nhầm ranh giới.

## 5. Auto-commit trong JDBC: thao tác nào thay đổi điều gì?

| Lệnh JDBC | Ý nghĩa |
| --- | --- |
| **connection.getAutoCommit()** | Đọc chế độ auto-commit hiện tại |
| **connection.setAutoCommit(false)** | Chuyển sang quản lý giao dịch thủ công; các câu lệnh kế tiếp thuộc giao dịch cho đến khi commit/rollback |
| **connection.commit()** | Xác nhận giao dịch hiện tại khi đang quản lý thủ công |
| **connection.rollback()** | Hủy phần thay đổi chưa commit của giao dịch hiện tại |
| **connection.setSavepoint()** | Đặt mốc có thể rollback một phần trong giao dịch đang mở (nếu driver/hệ quản trị hỗ trợ) |
| **connection.rollback(savepoint)** | Quay về mốc savepoint, không hủy toàn bộ giao dịch |
| **connection.setAutoCommit(true)** | Bật lại auto-commit; theo JDBC, nếu đổi chế độ khi giao dịch đang hoạt động, giao dịch hiện tại được commit |

**Cảnh báo về setAutoCommit(true):** Không dùng thao tác này thay cho **rollback()** sau lỗi. Đổi từ false sang true khi còn giao dịch mở có thể **commit dữ liệu dở dang**. Cần kết thúc giao dịch một cách chủ động trước khi thay đổi trạng thái.

JDBC định nghĩa một giao dịch mới được bắt đầu khi thực thi câu SQL tiếp theo sau commit/rollback trong chế độ thủ công; không cần gọi **beginTransaction()** trên JDBC **Connection**. Tùy hệ quản trị, **DDL** (CREATE, ALTER, DROP) có thể được phép rollback hoặc có hành vi commit ngầm: PostgreSQL hỗ trợ giao dịch cho nhiều lệnh DDL, trong khi một số hệ quản trị khác tự commit đối với nhiều loại DDL. Không giả định tính di động của DDL nếu chưa kiểm tra tài liệu hệ đang sử dụng.

## 6. Ví dụ Java: chuyển tiền qua một Connection

Giả sử bảng **accounts** có **id** duy nhất và **balance NUMERIC**, tài khoản nguồn/đích đã được xác minh quyền sử dụng. Ví dụ JDBC sau giữ hai UPDATE trong **cùng một kết nối, cùng một giao dịch**. Nó kiểm tra cả số hàng tác động, xử lý lỗi và không để ứng dụng lặng lẽ commit một nửa thao tác.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (fromId == toId) {
            throw new IllegalArgumentException("Hai tài khoản phải khác nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                String debitSql = """
                    UPDATE accounts
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """;
                try (PreparedStatement debit =
                             connection.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
                    }
                }

                String creditSql = """
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id = ?
                    """;
                try (PreparedStatement credit =
                             connection.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Tài khoản đích không tồn tại");
                    }
                }

                connection.commit();
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
~~~

**Giải thích từng quyết định quan trọng:**

1. **DataSource** cấp một connection cho toàn bộ thao tác. Nếu mỗi repository method tự mở một connection mới, hai câu UPDATE sẽ không tự động nằm trong cùng giao dịch.
2. **setAutoCommit(false)** chuyển connection sang chế độ điều phối thủ công. Không gọi **commit()** trước khi cả hai lệnh đã thành công.
3. Câu UPDATE nguồn chứa luôn điều kiện **balance >= amount**. Đây là một thao tác cập nhật có điều kiện có thể phối hợp với khóa hàng của cơ sở dữ liệu; không thay bằng **SELECT balance** rồi mới UPDATE nếu chưa đánh giá nguy cơ tranh chấp.
4. **executeUpdate() != 1** được coi là lỗi nghiệp vụ; nó cũng phải dẫn đến rollback, dù câu SQL không ném SQLException.
5. Nhánh **catch** cố gắng rollback cả lỗi SQL lẫn lỗi nghiệp vụ. Nếu rollback cũng lỗi, exception rollback được đính kèm để không che mất nguyên nhân ban đầu.
6. **try-with-resources** đóng statement và connection. Trong môi trường có connection pool, **close()** thường trả logical connection về pool; pool/transaction manager phải quản lý việc reset trạng thái và loại bỏ kết nối hỏng.

Ví dụ cố ý tập trung vào giao dịch của **hai UPDATE**. Hệ thống chuyển tiền thật cần thêm ghi lịch sử, chống thực hiện lại, kiểm soát người dùng/tenant, chính sách làm tròn/đơn vị tiền, trạng thái tài khoản, nhật ký kiểm toán và các ràng buộc khác. Không coi một ví dụ kỹ thuật về atomicity là thiết kế đầy đủ cho nghiệp vụ tài chính.

### Vì sao không cần tự bật lại auto-commit trong đoạn ví dụ?

Connection trong ví dụ được **sở hữu riêng cho một lời gọi** và được đóng ngay sau khi giao dịch kết thúc. Hệ thống dùng pool phải xác minh pool khôi phục thuộc tính connection khi trả về; nếu không, cần một chiến lược reset và xử lý lỗi đúng với pool đang dùng. Không nên gọi **setAutoCommit(true)** một cách mù quáng trong **finally** khi **rollback đã thất bại**: thao tác này có thể dẫn đến commit ngoài ý muốn trên kết nối còn hoạt động. Với connection do framework hoặc nơi khác sở hữu, hãy để thành phần sở hữu connection điều phối trạng thái; không tự thay chế độ.

## 7. Đối chiếu ba cách thực thi cùng một nghiệp vụ

| Cách triển khai | Ranh giới giao dịch | Nếu bước thứ hai lỗi |
| --- | --- | --- |
| Hai lệnh SQL khi **auto-commit = true** | Mỗi lệnh tự commit | Bước thứ nhất có thể đã lưu vĩnh viễn |
| JDBC **setAutoCommit(false)**, commit/rollback có kiểm soát | Các lệnh trên **cùng Connection** | Ứng dụng có thể rollback cả hai |
| Spring **@Transactional** với transaction manager đúng cấu hình | Phạm vi method được proxy điều phối trên tài nguyên tham gia giao dịch | Manager rollback theo quy tắc rollback của framework |

Một giao dịch không tự mở rộng ra mọi loại tài nguyên chỉ vì nhiều method được gọi trong cùng luồng Java. Giao dịch cần một thành phần điều phối và mọi câu SQL phải dùng đúng connection hoặc context giao dịch. Nếu một dịch vụ gọi hai kho dữ liệu độc lập, hoặc vừa ghi DB vừa gửi message, đó là bài toán phối hợp nhiều tài nguyên; một local transaction chỉ bảo đảm atomicity trong phạm vi tài nguyên nó quản lý.

## 8. Dùng @Transactional trong Spring

Trong ứng dụng Spring dùng Spring JDBC/JPA, transaction manager có thể quản lý lấy connection, bắt đầu giao dịch, commit và rollback. Ví dụ một lớp service có hai thao tác repository cùng tham gia giao dịch:

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final AccountDao accountDao;

    public TransferService(AccountDao accountDao) {
        this.accountDao = accountDao;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (fromId == toId || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Yêu cầu không hợp lệ");
        }
        int debited = accountDao.debitIfEnough(fromId, amount);
        if (debited != 1) {
            throw new IllegalStateException("Không đủ tiền");
        }
        int credited = accountDao.credit(toId, amount);
        if (credited != 1) {
            throw new IllegalStateException("Không tìm thấy tài khoản đích");
        }
    }
}
~~~

Đoạn code giả định **AccountDao** dùng một công nghệ được transaction manager điều phối, ví dụ **JdbcTemplate** với **DataSourceTransactionManager** thích hợp, hoặc repository JPA với **JpaTransactionManager**. Hai phương thức **debitIfEnough** và **credit** phải thực thi SQL thực sự trên tài nguyên tham gia giao dịch. Việc đặt annotation không tự làm đúng một DAO lấy connection tùy ý qua **DriverManager**.

Những quy tắc cần nắm:

- Theo cấu hình mặc định thường gặp của Spring, **@Transactional** dùng propagation **REQUIRED**: tham gia giao dịch hiện có hoặc mở giao dịch mới nếu chưa có.
- Theo mặc định, Spring rollback với **RuntimeException** và **Error**; các checked exception thông thường không nhất thiết kích hoạt rollback nếu không cấu hình, ví dụ **@Transactional(rollbackFor = Exception.class)**. Chính sách mặc định có thể được cấu hình lại ở cấp ứng dụng.
- Với mô hình **proxy** thường dùng, lời gọi phải đi qua proxy Spring. Một method trong cùng bean gọi trực tiếp method **@Transactional** khác qua **this.method()** thường không kích hoạt interceptor cho lời gọi nội bộ đó.
- Không được **nuốt exception** rồi trả kết quả thành công nếu cần rollback. Nếu chuyển exception thành kết quả nghiệp vụ, phải quyết định rõ có đánh dấu rollback-only hay không.
- Giao dịch thường gắn với **context thực thi** do transaction manager quản lý. Tự khởi tạo thread, dùng async hoặc chuyển qua luồng reactive không bảo đảm giữ nguyên local transaction theo cơ chế thread-bound của transaction manager đồng bộ.
- **@Transactional(readOnly = true)** chủ yếu là gợi ý tối ưu và có thể ảnh hưởng hành vi tùy công nghệ; không phải cơ chế phân quyền hoặc lời hứa mọi lệnh ghi đều bị chặn.

### JPA: flush khác commit

Với JPA/Hibernate, **flush** đồng bộ các thay đổi đang theo dõi xuống DB trong giao dịch nhưng không đồng nghĩa **commit**. Sau flush thành công, rollback giao dịch vẫn có thể hủy những thay đổi chưa commit. Khi debug, phân biệt lệnh SQL đã được gửi đến DB, giao dịch đã commit và trạng thái object trong persistence context.

### Tránh hai transaction manager cùng nhận trách nhiệm cho một thao tác

Nếu đã dùng Spring **@Transactional**, không nên để DAO bên trong tự gọi **setAutoCommit(false)** hoặc **commit()** trên connection khác. Hãy dùng công cụ truy cập dữ liệu tham gia transaction manager đang hoạt động, và kiểm tra cấu hình khi có nhiều DataSource hoặc nhiều transaction manager.

## 9. Khi nào rollback được và không được?

| Tình huống | Kết quả có thể kỳ vọng |
| --- | --- |
| Một UPDATE trong giao dịch thất bại, ứng dụng gọi rollback | Các thay đổi **chưa commit** của giao dịch đó bị hủy |
| Hai UPDATE chạy auto-commit, lệnh thứ hai thất bại | Lệnh thứ nhất có thể đã commit; rollback lệnh thứ hai không đảo ngược lệnh thứ nhất |
| Đã commit giao dịch, sau đó client yêu cầu rollback | Không thể dùng rollback giao dịch cũ để hoàn tác dữ liệu đã commit |
| Giao dịch ghi DB và gửi email ra ngoài | Rollback DB không thu hồi email |
| SQL thành công, mạng đứt khi client đang chờ kết quả commit | Trạng thái commit có thể chưa biết từ phía client; không được tự cho rằng rollback đã xảy ra |
| Giao dịch rollback sau khi sử dụng sequence/identity | Nhiều cơ chế cấp số không rollback số đã cấp; có thể có khoảng trống ID |

Trong PostgreSQL, nhiều lỗi SQL đặt giao dịch đang mở vào trạng thái aborted; sau đó các câu lệnh bình thường sẽ tiếp tục bị từ chối cho đến khi **ROLLBACK**, hoặc xử lý bằng **ROLLBACK TO SAVEPOINT** nếu đã tạo savepoint đúng cách. Không nên cố tiếp tục thực thi phần còn lại của nghiệp vụ trên giao dịch đã lỗi.

## 10. Savepoint: rollback một phần, không thay thế ranh giới tổng

Trong một giao dịch lớn, có thể cần thử một bước tùy chọn rồi hủy riêng bước đó nếu thất bại:

~~~sql
BEGIN;
UPDATE orders SET status = 'PROCESSING' WHERE id = 9001;
SAVEPOINT before_optional_note;
INSERT INTO order_notes(order_id, note) VALUES (9001, 'Ghi chú phụ');

-- Nếu thao tác tùy chọn thất bại và ngữ nghĩa cho phép bỏ qua:
ROLLBACK TO SAVEPOINT before_optional_note;

-- Các thay đổi trước savepoint vẫn thuộc giao dịch đang mở.
COMMIT;
~~~

Trong kịch bản thực tế, chỉ gọi **ROLLBACK TO SAVEPOINT** khi nhánh tùy chọn thất bại; nếu thành công có thể **RELEASE SAVEPOINT** hoặc tiếp tục giao dịch. Cú pháp trên minh họa rollback một phần, không phải đoạn SQL chạy tuần tự với ý định giữ bản ghi note. Lỗi ở bước bắt buộc vẫn phải rollback **toàn bộ**. Savepoint cũng không tự giải quyết truy cập đồng thời hay hoàn tác tác dụng phụ bên ngoài DB.

JDBC hỗ trợ các API tương ứng:

~~~java
import java.sql.Savepoint;

// Bên trong Connection đang quản lý giao dịch thủ công:
Savepoint beforeOptionalWork = connection.setSavepoint("before_optional_work");
try {
    // Thực thi nhóm SQL tùy chọn.
    performOptionalWork(connection);
    connection.releaseSavepoint(beforeOptionalWork);
} catch (java.sql.SQLException optionalFailure) {
    connection.rollback(beforeOptionalWork);
    // Chỉ bỏ qua lỗi nếu nghiệp vụ cho phép và connection vẫn dùng được.
}
~~~

Đoạn code phác họa giả định method **performOptionalWork** do ứng dụng cung cấp; không dùng như chương trình Java độc lập. Hỗ trợ savepoint và cách xử lý lỗi phụ thuộc driver/hệ quản trị.

## 11. Giao dịch không tự giải quyết tất cả vấn đề đồng thời

Ngay cả khi nhiều câu lệnh cùng một transaction, hai giao dịch chạy đồng thời vẫn có thể tranh chấp tài nguyên, gây deadlock hoặc làm kết quả không đúng kỳ vọng nếu nghiệp vụ dùng kiểu **đọc rồi ghi** mà không có biện pháp phù hợp.

Ví dụ một luồng sai về mặt đồng thời:

~~~text
T1 đọc stock = 1              T2 đọc stock = 1
T1 thấy còn hàng              T2 thấy còn hàng
T1 tạo đơn                    T2 tạo đơn
T1 giảm stock                 T2 giảm stock
~~~

Trong một số mức cô lập và cách viết SQL, cả hai luồng có thể đưa ra quyết định dựa trên thông tin cũ. Để bảo vệ tồn kho, có thể dùng **UPDATE có điều kiện** và kiểm tra số hàng, ràng buộc dữ liệu, **SELECT ... FOR UPDATE**, khóa lạc quan qua trường version hoặc tăng mức cô lập, tùy nghiệp vụ.

### Mức cô lập và transaction boundary là hai lựa chọn khác nhau

Giao dịch tường minh xác định **cái gì commit/rollback cùng nhau**. Mức cô lập (như READ COMMITTED, REPEATABLE READ, SERIALIZABLE) xác định **những gì các giao dịch đồng thời có thể thấy và cách các xung đột được xử lý**. Bật setAutoCommit(false) không tự động đưa giao dịch lên SERIALIZABLE hoặc chặn mọi race condition.

Ví dụ mức SERIALIZABLE trong PostgreSQL có thể phát hiện xung đột và yêu cầu một bên **retry toàn bộ giao dịch**; kết quả đúng phụ thuộc ứng dụng xử lý lỗi và thử lại phù hợp. Không chỉ retry câu SQL cuối cùng sau lỗi serialization.

### Deadlock và thời gian giữ khóa

Hai giao dịch cập nhật các hàng theo thứ tự khác nhau có thể tạo deadlock:

~~~text
T1 khóa A, chờ B
T2 khóa B, chờ A
--> DB phát hiện deadlock, hủy một giao dịch
~~~

Nên cố gắng cập nhật các tài nguyên theo một thứ tự ổn định, giữ giao dịch ngắn và có chính sách retry cho lỗi có thể phục hồi. Với PostgreSQL, mã lỗi SQLSTATE **40P01** thường chỉ deadlock và **40001** chỉ serialization failure. Chỉ retry khi nghiệp vụ idempotent hoặc có cơ chế chống trùng phù hợp; backoff và giới hạn số lần thử là thiết yếu để tránh tạo thêm áp lực.

## 12. Giao dịch dài, connection pool và lỗi kết nối

Một giao dịch giữ connection và có thể giữ khóa hoặc snapshot tới khi kết thúc. Nếu mở transaction rồi gọi API chậm, chờ người dùng nhập liệu hoặc thực hiện xử lý CPU dài, ứng dụng có nguy cơ:

- Giữ khóa quá lâu, làm các giao dịch khác chờ, tăng nguy cơ deadlock.
- Giữ connection khỏi pool, khiến các request mới hết connection.
- Kéo dài vòng đời snapshot/MVCC, ảnh hưởng dọn dữ liệu cũ tùy hệ quản trị.
- Khi timeout hoặc mạng đứt, tạo ra tình huống kết quả khó xác định.

Vì vậy, hãy lấy dữ liệu cần thiết, kiểm tra điều kiện hợp lệ rồi mở **giao dịch ngắn nhất vẫn đúng nghiệp vụ**. Cấu hình timeout phù hợp cho kết nối, statement và transaction, và dùng metrics để quan sát số giao dịch mở lâu.

### Không trả connection về pool với giao dịch chưa xử lý

Một connection đi qua nhiều request theo thời gian là tài nguyên dùng lại; trạng thái auto-commit, isolation, schema hay các thay đổi session-level có thể gây lỗi khó tái hiện nếu không được reset đúng. Hãy để **pool và transaction manager** chịu trách nhiệm thiết lập và khôi phục trạng thái; trong JDBC thủ công, luôn commit hoặc rollback rõ ràng trước khi close. Nếu **rollback()** cũng thất bại, coi kết nối là có trạng thái không tin cậy, ghi nhận lỗi và dựa vào pool để loại bỏ/kiểm tra kết nối thay vì cố tiếp tục làm nghiệp vụ trên nó.

### Lỗi kết nối ở thời điểm commit

Giả sử đã gửi **COMMIT** nhưng kết nối đứt trước khi nhận phản hồi:

~~~text
Ứng dụng         mạng              Database
   |---- COMMIT -------------------->|
   |         (mất kết nối)           | có thể đã commit
   X<---------- kết quả không rõ ----|
~~~

Không được coi mọi lỗi khi commit là chắc chắn đã rollback, rồi vô điều kiện thực hiện lại một lệnh thanh toán hay chuyển tiền. Nên gắn thao tác với **request_id** duy nhất, đặt **UNIQUE constraint**, lưu trạng thái giao dịch nghiệp vụ, đối chiếu lại sau lỗi và thiết kế retry idempotent. Nếu request lặp, ứng dụng có thể trả về kết quả đã lưu thay vì thực hiện lại tác động.

## 13. Giao dịch DB không bao trùm hệ thống bên ngoài

Một tình huống phổ biến:

~~~text
BEGIN
  UPDATE orders SET status = 'PAID'
  Gọi API gửi thông báo  ---> thông báo đã gửi
  INSERT audit_log         ---> lỗi
ROLLBACK
~~~

DB có thể rollback đơn hàng, nhưng thông báo đã gửi không thể bị thu hồi bằng rollback. Tương tự, một giao dịch DB thông thường không tự làm cho message broker hoặc hệ thống thanh toán bên ngoài trở thành cùng một đơn vị atomicity.

Khi cần phối hợp ghi DB và phát sự kiện, một lựa chọn phổ biến là **transactional outbox**: ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào **cùng giao dịch DB**, commit, rồi một tiến trình khác đọc outbox để gửi thông điệp. Vì gửi có thể lặp, consumer cần xử lý idempotent; outbox giải quyết nhất quán giữa dữ liệu và sự kiện cần gửi, nhưng không bảo đảm gửi đúng một lần ở mọi hệ thống.

~~~text
Giao dịch DB:
  UPDATE orders
  INSERT outbox_event
  COMMIT
       |
       v
Worker đọc outbox --> gửi message --> consumer chống xử lý trùng
~~~

Với nghiệp vụ cần phối hợp nhiều hệ thống độc lập, còn có các mô hình như saga/compensation. Các mô hình này có bảo đảm và đánh đổi khác giao dịch ACID của một DB; không thể thay thế chúng chỉ bằng việc tắt auto-commit.

## 14. Quy trình chọn chế độ giao dịch cho tầng persistence

Trước khi triển khai một thao tác nghiệp vụ Java, hãy trả lời lần lượt:

1. **Có bao nhiêu thay đổi phải được xác nhận cùng nhau?** Nếu một câu SQL biểu diễn trọn thao tác, auto-commit có thể đủ. Nếu nhiều câu SQL phụ thuộc nhau, xác định một transaction boundary.
2. **Ai sở hữu transaction boundary?** JDBC thuần thường là lớp service/unit-of-work điều phối một Connection; trong Spring, ưu tiên transaction manager và **@Transactional** đúng vị trí.
3. **Lỗi nghiệp vụ nào phải dẫn đến rollback?** Bao gồm trả về 0 hàng, vi phạm ràng buộc, thiếu quyền, thiếu dữ liệu và lỗi SQL. Không chỉ xét exception do JDBC ném ra.
4. **Cần những bảo đảm đồng thời nào?** Chọn mức cô lập, khóa hoặc câu UPDATE nguyên tử theo nguy cơ cụ thể. Kiểm tra ràng buộc ở DB khi khả thi.
5. **Có tác dụng phụ ngoài DB không?** Tách phát sự kiện hoặc thao tác mạng ra khỏi ranh giới local transaction bằng kiến trúc thích hợp.
6. **Làm sao khi commit không rõ kết quả?** Có request ID, unique constraint, kiểm tra trạng thái và retry có giới hạn.
7. **Giao dịch kéo dài bao lâu?** Giảm công việc ngoài DB trong giao dịch; quan sát lock wait, pool pressure, timeout và lỗi deadlock.

## 15. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Để auto-commit bật cho nhiều UPDATE phải đi cùng nhau | Một câu thành công trước có thể đã commit khi câu sau thất bại | Tạo một giao dịch cho toàn bộ đơn vị nghiệp vụ |
| Bắt exception rồi trả về thành công | Transaction manager có thể commit dữ liệu dở dang | Truyền lỗi ra ngoài hoặc chủ động đánh dấu rollback-only khi phù hợp |
| Mỗi DAO tự mở connection mới trong giao dịch JDBC thủ công | Mỗi connection có trạng thái giao dịch riêng | Truyền cùng connection hoặc để framework điều phối |
| Gọi **setAutoCommit(true)** trong finally sau lỗi rollback | Có nguy cơ commit phần chưa xử lý | Kết thúc giao dịch an toàn, dùng pool/manager đúng chuẩn |
| Nhầm **flush** với commit | Có thể nghĩ dữ liệu đã bền vững dù còn trong giao dịch | Phân biệt gửi SQL, flush và commit |
| Chỉ tin @Transactional trên method gọi nội bộ | Self-invocation qua this có thể bỏ qua proxy | Đặt boundary ở service được gọi qua proxy hoặc cấu hình cơ chế phù hợp |
| Giữ transaction khi gọi API ngoài hoặc chờ người dùng | Kéo dài khóa, tốn connection, tăng timeout | Đưa xử lý ngoài DB ra khỏi giao dịch khi bảo đảm nghiệp vụ cho phép |
| Retry mù quáng sau lỗi commit | Có thể lặp thao tác đã thành công | Idempotency key, đối chiếu trạng thái, chỉ retry an toàn |
| Coi giao dịch là đủ để loại bỏ race condition | Isolation mặc định không nhất thiết chặn các bất thường nghiệp vụ | Ràng buộc, atomic UPDATE, khóa hoặc isolation phù hợp |

## 16. Tự kiểm tra

**Câu 1.** Dưới JDBC auto-commit = true, ứng dụng chạy hai lệnh: tạo **orders** rồi tạo **order_items**. Nếu lệnh thứ hai vi phạm foreign key và thất bại, bản ghi orders có được tự động hủy không?

**Gợi ý:** Không. Nếu lệnh đầu đã hoàn tất và commit, rollback của lệnh thứ hai không ảnh hưởng giao dịch đã commit. Hai lệnh nên ở cùng transaction nếu nghiệp vụ yêu cầu tạo cùng nhau.

**Câu 2.** Trong JDBC thủ công, sau **setAutoCommit(false)** có một UPDATE thành công, một UPDATE thất bại. Lệnh gọi **setAutoCommit(true)** có phải cách an toàn để “quay về mặc định” không?

**Gợi ý:** Không. Việc đổi mode trong lúc giao dịch còn hoạt động có thể commit phần thay đổi chưa giải quyết. Phải xử lý lỗi và rollback trước; nếu rollback thất bại, không tiếp tục dùng connection như thể nó đang ở trạng thái sạch.

**Câu 3.** Lớp Spring service có **@Transactional** trên method A; method B của cùng bean gọi **this.A()**. Trong mô hình Spring proxy mặc định, có chắc annotation chạy không?

**Gợi ý:** Không. Lời gọi nội bộ không đi qua proxy của bean; cần thiết kế điểm vào giao dịch đi qua proxy hoặc dùng cơ chế transaction phù hợp khác.

**Câu 4.** Một hệ thống ghi DB thành công nhưng đứt kết nối khi nhận phản hồi **COMMIT**. Có nên gửi lại yêu cầu chuyển tiền ngay lập tức không?

**Gợi ý:** Không được mặc định giao dịch đã thất bại. Cần xác định trạng thái theo mã yêu cầu duy nhất hoặc hệ thống đối soát và bảo đảm thực hiện lại không tạo tác động lần hai.

**Câu 5.** Vì sao hai câu UPDATE đều nằm trong một transaction vẫn có thể gây deadlock?

**Gợi ý:** Atomicity không loại bỏ tranh chấp khóa. Nếu hai transaction giữ khóa theo thứ tự ngược nhau, DB có thể hủy một bên để phá deadlock; ứng dụng cần thứ tự truy cập nhất quán và retry phù hợp.

## 17. Ghi nhớ

**Auto-commit** chọn ranh giới theo **từng câu lệnh**; **giao dịch tường minh** chọn ranh giới theo **một thao tác nghiệp vụ cần tính nguyên tử**. Trong Java, hãy giữ những câu SQL liên quan trên đúng connection/context giao dịch, chỉ commit khi tất cả bước hợp lệ và rollback khi thất bại. Sau đó đánh giá riêng mức cô lập, điều kiện đồng thời, việc dùng connection pool và tình huống commit chưa rõ kết quả. Đó là nền tảng để xây dựng tầng persistence vừa đúng dữ liệu, vừa chịu được lỗi thực tế.
