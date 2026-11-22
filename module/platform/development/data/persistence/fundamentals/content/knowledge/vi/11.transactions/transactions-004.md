# Bắt đầu, commit và rollback giao dịch

Trong tầng lưu trữ dữ liệu bền vững (persistence) của ứng dụng Java, một thao tác nghiệp vụ thường cần thay đổi **nhiều bản ghi như một đơn vị**. Ví dụ, chuyển 100.000 đồng từ tài khoản A sang B đòi hỏi hai thay đổi số dư và một bản ghi lịch sử. Nếu mới trừ tiền ở A mà hệ thống gặp lỗi trước khi cộng tiền cho B, dữ liệu sẽ sai. **Giao dịch cơ sở dữ liệu (database transaction)** là cơ chế để nhóm các thao tác liên quan và quyết định: **ghi nhận tất cả bằng commit**, hoặc **hủy các thay đổi chưa được commit bằng rollback**.

Bài học thuộc chương **Giao dịch** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là biết lúc nào bắt đầu giao dịch, điều gì xảy ra khi commit/rollback, và cách triển khai ranh giới giao dịch an toàn trong JDBC hoặc một tầng persistence của Java. Các ví dụ SQL chủ yếu dùng PostgreSQL; với hệ quản trị khác cần kiểm tra cú pháp và hành vi cụ thể.

## 1. Vì sao phải có ranh giới giao dịch?

Hãy xét ba câu lệnh:

~~~sql
UPDATE accounts SET balance = balance - 100000 WHERE id = 1;
UPDATE accounts SET balance = balance + 100000 WHERE id = 2;
INSERT INTO transfer_log (operation_id, from_account_id, to_account_id, amount)
VALUES ('TX-2026-0001', 1, 2, 100000);
~~~

Nếu mỗi lệnh tự commit ngay sau khi chạy, câu lệnh đầu có thể đã được ghi nhận bền vững trong khi câu lệnh thứ hai lỗi kết nối. Sau đó, **rollback câu lệnh thứ hai không thể hoàn tác câu lệnh thứ nhất đã commit**.

Ranh giới giao dịch đúng là:

~~~text
Bắt đầu giao dịch
    |
    +--> Trừ tiền A
    |
    +--> Cộng tiền B
    |
    +--> Ghi lịch sử chuyển tiền
    |
    +--> Kiểm tra mọi bước thành công?
             |
             +--> Có ------> COMMIT ------> Hoàn tất
             |
             +--> Không ---> ROLLBACK ----> Hủy thay đổi chưa commit
~~~

Ba thao tác được đặt dưới **cùng một giao dịch trên cùng kết nối cơ sở dữ liệu**. Nếu bất cứ bước nào không đạt yêu cầu nghiệp vụ, tầng persistence yêu cầu rollback. Nếu toàn bộ thành công, tầng persistence yêu cầu commit.

Phân biệt rõ:

- **Thao tác SQL thành công**: cơ sở dữ liệu thực thi được một câu lệnh; chưa nhất thiết nghĩa là cả nghiệp vụ đã xong.
- **Giao dịch thành công**: tất cả điều kiện nghiệp vụ đạt yêu cầu và lệnh **COMMIT** hoàn tất thành công.
- **Câu lệnh ảnh hưởng 0 dòng**: không nhất thiết là lỗi cú pháp hoặc lỗi hệ quản trị, nhưng có thể là thất bại nghiệp vụ. Ví dụ trừ tiền với điều kiện đủ số dư mà cập nhật 0 dòng thì **phải quyết định rollback**.
- **Rollback**: hoàn tác những thay đổi thuộc giao dịch chưa commit; không có khả năng “quay ngược thời gian” với một commit đã được xác nhận.

## 2. Ba thao tác nền tảng: BEGIN, COMMIT, ROLLBACK

### 2.1. Bắt đầu giao dịch

Ở PostgreSQL, có thể bắt đầu một giao dịch tường minh bằng:

~~~sql
BEGIN;
-- Các câu lệnh SQL cùng một giao dịch...
~~~

Một số hệ quản trị cũng hỗ trợ **START TRANSACTION**. Trong Java JDBC, cách thông dụng là tắt chế độ tự commit của **Connection**:

~~~java
connection.setAutoCommit(false);
~~~

Khi đó, các câu lệnh tiếp theo được thực thi trong một giao dịch do ứng dụng kiểm soát; giao dịch được bắt đầu theo hành vi của JDBC và driver, thường khi thực thi câu lệnh đầu tiên sau khi tắt auto-commit. Không nhất thiết phải gửi thêm **BEGIN** qua SQL trên cùng JDBC Connection.

**Cần kiểm tra trạng thái auto-commit thực tế.** JDBC Connection mới thường có **autoCommit = true** theo đặc tả JDBC; một connection do pool/framework quản lý có thể đã được cấu hình khác. Khi auto-commit bật, **mỗi câu lệnh SQL thường được commit riêng khi hoàn tất**. Điều đó rất khác với yêu cầu “ba thao tác cùng thành công hoặc cùng thất bại”.

### 2.2. COMMIT: chấp nhận giao dịch

~~~sql
BEGIN;

UPDATE accounts SET balance = balance - 100000 WHERE id = 1;
UPDATE accounts SET balance = balance + 100000 WHERE id = 2;

COMMIT;
~~~

**COMMIT** yêu cầu DBMS kết thúc giao dịch bằng cách xác nhận các thay đổi. Khi cơ sở dữ liệu trả về thành công, các thay đổi đã được commit theo bảo đảm của DBMS và cấu hình độ bền của nó; các kết nối khác có thể quan sát các thay đổi theo mức cô lập của chúng. Khóa do giao dịch giữ sẽ được giải phóng theo cơ chế hệ quản trị.

Lưu ý: đoạn SQL chỉ minh họa cú pháp. Trong ứng dụng thật, phải kiểm tra **số dòng cập nhật**, số dư hợp lệ, tài khoản tồn tại và các ràng buộc trước khi commit. Nếu câu lệnh trừ tiền cập nhật 0 dòng nhưng lệnh cộng tiền cập nhật 1 dòng, **không được commit**.

### 2.3. ROLLBACK: hủy phần việc chưa commit

~~~sql
BEGIN;

UPDATE accounts SET balance = balance - 100000 WHERE id = 1;
-- Phát hiện nghiệp vụ không hợp lệ hoặc câu lệnh tiếp theo lỗi.

ROLLBACK;
~~~

**ROLLBACK** kết thúc giao dịch bằng cách hủy các thay đổi dữ liệu chưa commit trong giao dịch đó. Tùy DBMS, nó cũng giải phóng các khóa liên quan đến giao dịch. Sau rollback, ứng dụng có thể khởi động một giao dịch mới trên kết nối còn sử dụng được.

Một ví dụ để tự thử nghiệm:

~~~sql
BEGIN;
UPDATE accounts SET balance = balance + 500 WHERE id = 1;
SELECT balance FROM accounts WHERE id = 1; -- Trong giao dịch có thể thấy +500.
ROLLBACK;
SELECT balance FROM accounts WHERE id = 1; -- Không còn thay đổi +500 ở trên.
~~~

Ví dụ này giả định không có giao dịch đồng thời can thiệp vào bản ghi và các câu lệnh chạy thành công. **SELECT trong cùng giao dịch** thường nhìn thấy các thay đổi do chính giao dịch đó thực hiện, dù thay đổi chưa commit.

## 3. Vòng đời giao dịch và các trạng thái cần hiểu

~~~mermaid
flowchart TD
    A["Chưa bắt đầu / Auto-commit"] --> B["Bắt đầu giao dịch"]
    B --> C["Thực thi SQL"]
    C --> D{"Các bước hợp lệ?"}
    D -->|Có| E["COMMIT"]
    D -->|Không| F["ROLLBACK"]
    E --> G["Đã commit"]
    F --> H["Đã rollback"]
    C -->|Lỗi SQL khiến giao dịch bị lỗi| I["Giao dịch ở trạng thái lỗi"]
    I --> F
~~~

Sơ đồ thể hiện logic ứng dụng, không mô phỏng mọi trạng thái nội bộ của từng DBMS. Đặc biệt trong PostgreSQL, một lỗi SQL thông thường bên trong giao dịch có thể khiến giao dịch **ở trạng thái aborted**: các lệnh tiếp theo sẽ bị từ chối cho đến khi **ROLLBACK** hoặc, nếu có savepoint phù hợp, **ROLLBACK TO SAVEPOINT**.

| Tình huống | Hành động đúng |
|---|---|
| Bắt đầu giao dịch và tất cả bước thành công | Kiểm tra điều kiện nghiệp vụ, rồi **COMMIT** |
| Một câu lệnh SQL hoặc điều kiện nghiệp vụ thất bại | **ROLLBACK**, trả lỗi có ngữ cảnh |
| Đã commit thành công nhưng ứng dụng đổi ý | Thực hiện nghiệp vụ bù trừ ở **giao dịch mới** nếu cần; rollback cũ không còn tác dụng |
| Kết nối mất ngay khi gửi COMMIT | **Chưa biết chắc kết quả**, cần đối soát qua mã giao dịch/idempotency |
| Ứng dụng chưa chủ động commit nhưng kết nối bị đóng | Không dựa vào hành vi đóng connection để bảo đảm rollback; quản lý giao dịch rõ ràng |

**Ranh giới giao dịch nên trùng ranh giới bất biến nghiệp vụ (business invariant).** Nếu chuyển tiền yêu cầu tổng số dư được bảo toàn và ghi lịch sử thành công, tất cả thao tác liên quan phải nằm trong cùng giao dịch khi chúng thuộc cùng một cơ sở dữ liệu hỗ trợ giao dịch.

## 4. BEGIN–COMMIT–ROLLBACK liên hệ với ACID như thế nào?

Bốn thuộc tính ACID thường được dùng để giải thích giao dịch, nhưng **không nên hiểu chỉ cần viết BEGIN/COMMIT là mọi vấn đề đồng thời đều biến mất**.

| Thuộc tính | Ý nghĩa trong ví dụ chuyển tiền | Điều cần nhớ |
|---|---|---|
| **Atomicity (nguyên tử)** | Trừ A, cộng B, ghi log được chấp nhận cùng nhau hoặc hoàn tác cùng nhau | Cần kiểm tra kết quả từng bước và rollback khi không đạt |
| **Consistency (nhất quán)** | Dữ liệu chuyển từ trạng thái hợp lệ sang trạng thái hợp lệ | Ràng buộc DB, quy tắc ứng dụng và thiết kế giao dịch cùng chịu trách nhiệm |
| **Isolation (cô lập)** | Giao dịch đồng thời không được phá các giả định nghiệp vụ | Phụ thuộc mức cô lập, khóa, câu lệnh nguyên tử và cách ứng dụng đọc/ghi |
| **Durability (bền vững)** | Giao dịch đã commit được lưu theo bảo đảm độ bền của DBMS | Phụ thuộc cơ chế ghi log, lưu trữ và cấu hình cụ thể |

**Atomicity** là lý do trực tiếp để gom các thao tác vào một transaction. **Isolation** liên quan đến cách các transaction khác nhau tương tác; một ứng dụng có thể commit thành công nhưng vẫn tạo sai lệch nghiệp vụ do **lost update** hoặc **write skew** nếu thiếu kiểm soát đồng thời phù hợp.

**Durability** không đồng nghĩa “không thể mất dữ liệu trong mọi thảm họa”. Bảo vệ trước hỏng ổ đĩa, lỗi vận hành hoặc mất vùng triển khai còn cần sao lưu, phục hồi và kiến trúc lưu trữ phù hợp.

## 5. Ví dụ thực tế với SQL: chuyển tiền an toàn

Giả sử PostgreSQL đã có hai bảng sau:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE transfer_log (
    operation_id VARCHAR(80) PRIMARY KEY,
    from_account_id BIGINT NOT NULL REFERENCES accounts(id),
    to_account_id BIGINT NOT NULL REFERENCES accounts(id),
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0)
);
~~~

Mục đích của **CHECK (balance >= 0)** là để DB không chấp nhận số dư âm. **PRIMARY KEY** trên **operation_id** giúp chống ghi trùng mã giao dịch, là nền tảng cho xử lý yêu cầu gửi lại. Trong hệ thống thật còn cần mô hình tiền tệ, quyền truy cập, kiểm toán và quy tắc nghiệp vụ phù hợp.

### 5.1. Thực hiện các bước trong một giao dịch

~~~sql
BEGIN;

-- Trừ tiền chỉ khi tài khoản nguồn tồn tại và đủ số dư.
UPDATE accounts
SET balance = balance - 100000
WHERE id = 1 AND balance >= 100000;
-- Ứng dụng phải xác nhận đúng 1 dòng được cập nhật.

-- Cộng tiền vào tài khoản đích.
UPDATE accounts
SET balance = balance + 100000
WHERE id = 2;
-- Ứng dụng phải xác nhận đúng 1 dòng được cập nhật.

INSERT INTO transfer_log (
    operation_id, from_account_id, to_account_id, amount
) VALUES ('TX-2026-0001', 1, 2, 100000);

-- Chỉ chạy khi TẤT CẢ kiểm tra đều thành công:
COMMIT;

-- Nếu bất kỳ kiểm tra nào thất bại, thực hiện ROLLBACK
-- thay vì COMMIT.
~~~

Trong đoạn trên, các chú thích **“phải xác nhận đúng 1 dòng”** là điều kiện bắt buộc do ứng dụng thực hiện. Tự chạy liên tiếp cả script mà không có logic kiểm tra số dòng là **chưa đủ an toàn cho chuyển tiền**. Phần JDBC dưới đây thể hiện logic đó một cách tường minh.

**Vì sao trừ tiền bằng UPDATE có điều kiện?** Câu lệnh **UPDATE ... WHERE balance >= amount** kiểm tra điều kiện và cập nhật trên bản ghi trong cùng thao tác của DBMS. Nó tránh lỗi phổ biến của quy trình “đọc số dư -> kiểm tra ở Java -> ghi số dư mới” trong môi trường nhiều giao dịch đồng thời. Dù vậy, ứng dụng vẫn phải xét các giao dịch đồng thời, deadlock và quy tắc toàn cục khác.

### 5.2. Đừng chia một giao dịch ra nhiều connection

Nếu thao tác trừ A dùng Connection 1 và thao tác cộng B dùng Connection 2, việc bật **setAutoCommit(false)** trên cả hai connection **không tự biến chúng thành một giao dịch nguyên tử**. Mỗi connection có ranh giới commit/rollback riêng. Với thao tác thuộc cùng một DB, hãy giữ một connection trong một giao dịch.

Giao dịch qua nhiều cơ sở dữ liệu hoặc hệ thống ngoài (API thanh toán, email, message broker) đòi hỏi cơ chế riêng, ví dụ giao dịch phân tán nếu hạ tầng hỗ trợ, hoặc thiết kế **outbox/saga** và bước bù trừ khi thích hợp.

## 6. Kiểm soát giao dịch trong Java JDBC

### 6.1. Mặc định auto-commit và việc tắt nó

Trong JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean originallyAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);
    try {
        // Các câu SQL liên quan cùng nghiệp vụ...
        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    } finally {
        // Chỉ khôi phục cấu hình khi giao dịch đã kết thúc an toàn.
        // Xem ví dụ hoàn chỉnh bên dưới để tránh commit ngầm.
    }
}
~~~

Khi đổi **autoCommit** từ **false** sang **true**, JDBC có thể **commit giao dịch đang mở**. Vì vậy, nếu rollback thất bại và không biết giao dịch đã kết thúc hay chưa, **không được mù quáng gọi setAutoCommit(true)**. Đây là lý do ví dụ hoàn chỉnh theo dõi việc commit/rollback đã kết thúc thành công.

### 6.2. Ví dụ JDBC có kiểm tra số dòng và rollback

Đoạn sau giả định bảng **accounts** và **transfer_log** đã tồn tại như ở mục 5; ứng dụng sử dụng một **DataSource** được cấu hình sẵn. Ví dụ dành cho JDBC 4.x và không phụ thuộc một ORM cụ thể.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            long fromId, long toId, BigDecimal amount, String operationId
    ) throws SQLException {
        if (fromId == toId || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Giao dịch không hợp lệ");
        }
        if (operationId == null || operationId.isBlank()) {
            throw new IllegalArgumentException("Thiếu operationId");
        }

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ này chủ động sở hữu một giao dịch mới.
            if (!connection.getAutoCommit()) {
                throw new SQLException("Connection đã thuộc giao dịch khác");
            }
            connection.setAutoCommit(false);

            boolean transactionEnded = false;
            try {
                try (PreparedStatement debit = connection.prepareStatement(
                        "UPDATE accounts "
                        + "SET balance = balance - ? "
                        + "WHERE id = ? AND balance >= ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    requireOneRow(debit.executeUpdate(), "Không đủ số dư hoặc thiếu tài khoản nguồn");
                }

                try (PreparedStatement credit = connection.prepareStatement(
                        "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    requireOneRow(credit.executeUpdate(), "Thiếu tài khoản đích");
                }

                try (PreparedStatement log = connection.prepareStatement(
                        "INSERT INTO transfer_log "
                        + "(operation_id, from_account_id, to_account_id, amount) "
                        + "VALUES (?, ?, ?, ?)")) {
                    log.setString(1, operationId);
                    log.setLong(2, fromId);
                    log.setLong(3, toId);
                    log.setBigDecimal(4, amount);
                    requireOneRow(log.executeUpdate(), "Không ghi được lịch sử");
                }

                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Tránh bật auto-commit nếu rollback thất bại:
                // bật auto-commit khi transaction còn mở có thể commit ngầm.
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
            }
        }
    }

    private static void requireOneRow(int rows, String message) throws SQLException {
        if (rows != 1) {
            throw new SQLException(message + "; affected rows=" + rows);
        }
    }
}
~~~

**Diễn biến bình thường:** cả ba câu lệnh ảnh hưởng đúng một dòng; **commit()** thành công; cấu hình auto-commit được phục hồi; try-with-resources đóng hoặc trả connection về pool.

**Diễn biến lỗi:** tài khoản đích không tồn tại hoặc **operation_id** bị trùng gây lỗi; chương trình thử **rollback()** để hủy bước trừ tiền đã chạy, giữ lỗi gốc và gắn lỗi rollback (nếu có) dưới dạng **suppressed exception**.

**Giới hạn của ví dụ:** mã này minh họa một giao dịch JDBC do phương thức tự sở hữu. Nếu rollback, kết nối hoặc khôi phục cấu hình gặp lỗi, tầng hạ tầng cần có chính sách loại bỏ/kiểm tra connection lỗi trước khi cho mượn lại. Nếu COMMIT gặp lỗi mạng, trạng thái giao dịch có thể **không xác định từ phía client**; thậm chí lần rollback tiếp theo thành công cũng không chứng minh commit trước đó chưa có hiệu lực. Không được tự động thử lại lệnh chuyển tiền với **operation_id mới** mà thiếu đối soát.

### 6.3. Nếu dùng Spring hoặc JPA

Một ứng dụng Spring thường khai báo ranh giới giao dịch ở service:

~~~java
@Service
public class TransferApplicationService {
    private final TransferRepository repository;

    public TransferApplicationService(TransferRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(TransferRequest request) {
        repository.debit(request);
        repository.credit(request);
        repository.recordTransfer(request);
    }
}
~~~

Đây là **mã minh họa**: các lớp **TransferRepository** và **TransferRequest** đại diện cho những thành phần do ứng dụng tự định nghĩa. Với Spring, transaction manager sẽ điều phối commit khi method hoàn tất và rollback theo quy tắc lỗi/cấu hình giao dịch.

Mặc định phổ biến của Spring là rollback trên **RuntimeException** và **Error**, còn checked exception cần cấu hình thêm nếu muốn rollback, chẳng hạn **@Transactional(rollbackFor = Exception.class)**. Việc gọi một method **@Transactional** từ method khác trong cùng đối tượng (self-invocation) có thể bỏ qua proxy nên giao dịch mong muốn không được tạo. Tầng ứng dụng cần xác minh cấu hình framework và phạm vi proxy trong dự án thật.

**Không trộn vô ý** transaction do framework quản lý với việc tự gọi **setAutoCommit**, **commit** hoặc **rollback** trên connection do framework cấp. Chọn một cơ chế sở hữu ranh giới giao dịch rõ ràng.

## 7. Lỗi, đồng thời và thời điểm commit

### 7.1. Một transaction không tự giải quyết mọi race condition

Giả sử hai yêu cầu cùng đọc **balance = 100000**, sau đó mỗi yêu cầu tự tính và ghi giá trị mới theo kiểu **SET balance = 0**. Nếu thiếu kiểm soát đồng thời, giá trị cuối cùng có thể không phản ánh cả hai thao tác.

Có ba cách thường được kết hợp tùy tình huống:

- **UPDATE có điều kiện và phép toán trên giá trị hiện tại**: như **SET balance = balance - ? WHERE balance >= ?**, cho DB thực hiện kiểm tra và cập nhật nguyên tử.
- **Khóa bản ghi**: ví dụ **SELECT ... FOR UPDATE** trước khi kiểm tra và thay đổi; lưu ý thứ tự lấy khóa nhất quán giữa các giao dịch giúp giảm deadlock.
- **Mức cô lập phù hợp**: **READ COMMITTED**, **REPEATABLE READ**, **SERIALIZABLE** có bảo đảm khác nhau theo DBMS. Ở các mức có thể phát sinh lỗi serialization, ứng dụng cần biết khi nào retry lại **toàn bộ giao dịch**.

Thời điểm **COMMIT** rất quan trọng: càng giữ giao dịch mở lâu, càng dễ kéo dài thời gian giữ khóa, tăng tranh chấp, nguy cơ timeout và chi phí phiên bản dữ liệu ở một số hệ quản trị.

### 7.2. Deadlock và retry

Hai giao dịch có thể khóa hai tài khoản theo thứ tự ngược nhau: giao dịch A giữ tài khoản 1 và chờ 2; giao dịch B giữ 2 và chờ 1. DBMS thường phát hiện deadlock và hủy một giao dịch để bên kia tiếp tục.

Khi gặp lỗi deadlock hoặc serialization được xác nhận là **có thể retry**, tầng nghiệp vụ có thể thử lại **cả transaction** sau khi rollback, với số lần giới hạn và khoảng chờ phù hợp. **Không retry riêng lệnh cộng tiền** sau khi phần trừ tiền của transaction trước đã thất bại.

Để giảm deadlock khi chuyển tiền hai chiều, có thể khóa hai tài khoản theo **thứ tự ID tăng dần** trước khi cập nhật, nhưng cách khóa phải được thiết kế và thử trên DBMS cụ thể.

### 7.3. Mất kết nối đúng lúc COMMIT

Có một khác biệt cực kỳ quan trọng:

- **COMMIT trả về thành công**: client nhận xác nhận commit từ DBMS.
- **COMMIT trả về lỗi kết nối hoặc timeout**: client có thể không biết DBMS đã commit xong trước khi phản hồi bị mất hay chưa.

Vì vậy, **“commit() ném SQLException” không luôn đồng nghĩa “giao dịch chắc chắn chưa commit”**. Với nghiệp vụ quan trọng, cần có **operation_id duy nhất** ghi cùng giao dịch, cho phép tra cứu/đối soát trạng thái và xử lý request gửi lại mà không nhân đôi tác dụng. Nếu operation_id đã tồn tại, phải kiểm tra nội dung nghiệp vụ tương ứng; không được mặc định một mã trùng luôn đại diện cùng dữ liệu đầu vào.

## 8. SAVEPOINT: rollback một phần trong giao dịch

**SAVEPOINT** đánh dấu một điểm bên trong giao dịch. Có thể hủy các thay đổi sau savepoint mà vẫn tiếp tục giao dịch chính:

~~~sql
BEGIN;

UPDATE accounts SET balance = balance + 100 WHERE id = 1;

SAVEPOINT before_optional_note;
INSERT INTO optional_notes (account_id, note) VALUES (1, 'Ghi chú thử nghiệm');

ROLLBACK TO SAVEPOINT before_optional_note;
RELEASE SAVEPOINT before_optional_note;

COMMIT;
~~~

Ví dụ giả định bảng **optional_notes** tồn tại. **UPDATE** trước savepoint vẫn được commit, còn **INSERT** sau savepoint đã bị hoàn tác. Trong PostgreSQL, **ROLLBACK TO SAVEPOINT** đưa trạng thái về điểm đánh dấu nhưng **không kết thúc giao dịch**; có thể tiếp tục thực thi các lệnh hợp lệ.

JDBC hỗ trợ savepoint qua **Connection.setSavepoint()** và **Connection.rollback(savepoint)** nếu driver/DBMS hỗ trợ:

~~~java
Savepoint point = connection.setSavepoint("before_optional");
try {
    writeOptionalNote(connection);
} catch (SQLException error) {
    connection.rollback(point);
    // Chỉ tiếp tục nếu việc bỏ bước này không phá bất biến nghiệp vụ.
} finally {
    connection.releaseSavepoint(point);
}
~~~

Đây là đoạn mã minh họa, giả định **connection** đang ở chế độ giao dịch thủ công và **writeOptionalNote** là phương thức do ứng dụng định nghĩa. Việc **releaseSavepoint** hoặc **rollback(savepoint)** có thể thất bại; mã production cần xử lý ngoại lệ đó và quyết định rollback toàn bộ giao dịch khi cần.

**SAVEPOINT không phải transaction độc lập**: không có commit riêng để thay đổi sau savepoint trở thành bền vững trước transaction cha. Không dùng savepoint để “cứu” một nghiệp vụ nếu bước lỗi thực chất là bắt buộc.

## 9. Những bẫy phổ biến khi triển khai

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Quên tắt auto-commit khi có nhiều câu lệnh liên quan | Mỗi lệnh có thể được commit riêng; rollback về sau không cứu được lệnh trước | Chủ động mở ranh giới transaction bằng JDBC hoặc framework |
| Commit ngay sau mỗi câu UPDATE | Phá tính nguyên tử của nghiệp vụ | Chỉ commit sau toàn bộ bước và kiểm tra |
| Không kiểm tra số dòng bị ảnh hưởng | Có thể chuyển tiền sai khi tài khoản thiếu hoặc không đủ số dư | Kiểm tra kết quả **executeUpdate()** |
| Nuốt exception và vẫn commit | Lưu dữ liệu nửa chừng | Trả lỗi hoặc buộc rollback khi một bước bắt buộc thất bại |
| Bật auto-commit trong finally bất kể trạng thái | Có nguy cơ commit ngầm giao dịch chưa kết thúc | Chỉ khôi phục cấu hình sau khi giao dịch đã kết thúc rõ ràng |
| Giữ transaction mở khi gọi API mạng chậm | Giữ khóa lâu, tăng tranh chấp và timeout | Giữ transaction DB ngắn, dùng outbox/saga khi cần |
| Nghĩ rollback DB sẽ hủy email hoặc HTTP request | Hệ thống ngoài không tự hoàn tác | Thiết kế idempotency, outbox hoặc bù trừ |
| Retry sau lỗi COMMIT với mã nghiệp vụ mới | Có thể thực hiện hai lần cùng thao tác | Dùng operation ID ổn định, đối soát trạng thái trước khi retry |
| Cho rằng DDL luôn rollback được | Một số DBMS tự commit hoặc giới hạn DDL transaction | Kiểm tra tài liệu DBMS và thiết kế migration |
| Mở transaction ở nhiều connection không điều phối | Không có atomicity chung | Giữ cùng connection hoặc dùng thiết kế giao dịch phân tán thích hợp |

Thêm hai điểm vận hành: **(1)** thư viện kết nối/pool cần có timeout, giới hạn kích thước và chính sách xử lý kết nối hỏng; **(2)** ghi log nên có mã tương quan nghiệp vụ, nhưng tuyệt đối tránh ghi mật khẩu hoặc dữ liệu nhạy cảm không cần thiết. Tối ưu truy vấn, chỉ mục và chiến lược khóa có ảnh hưởng trực tiếp đến thời gian transaction giữ tài nguyên.

## 10. Thực hành tự kiểm tra

**Bài 1 — Auto-commit.** Một Java service chạy ba câu lệnh với **autoCommit = true**. Câu đầu thành công, câu thứ hai lỗi. Service gọi **rollback()** và nghĩ rằng dữ liệu trở về ban đầu. Sai ở đâu?

> **Gợi ý:** câu đầu có thể đã commit ngay khi hoàn tất; rollback chỉ áp dụng cho giao dịch còn mở, không hoàn tác commit trước đó.

**Bài 2 — Số dòng cập nhật.** Trong transaction chuyển tiền, câu trừ tiền có điều kiện **balance >= ?** cập nhật 0 dòng; câu cộng tiền cập nhật 1 dòng. Có được commit không?

> **Gợi ý:** không. Điều kiện nghiệp vụ “trừ và cộng đúng một lần” chưa đạt; cần rollback toàn bộ transaction.

**Bài 3 — Lỗi COMMIT.** Ứng dụng gửi **COMMIT**, kết nối mất ngay sau đó. Khi người dùng gửi lại yêu cầu, service định tạo operation ID mới. Rủi ro là gì?

> **Gợi ý:** DB có thể đã commit, nên mã mới sẽ tạo một thao tác thứ hai. Giữ mã nghiệp vụ ổn định và tra cứu/đối soát trạng thái trước khi xử lý lại.

**Bài 4 — Savepoint.** Giao dịch cập nhật dữ liệu chính, sau đó ghi chú không bắt buộc bị lỗi. Khi nào có thể rollback tới savepoint rồi vẫn commit phần chính?

> **Gợi ý:** chỉ khi dữ liệu chính đã hợp lệ độc lập và việc thiếu ghi chú được nghiệp vụ chấp nhận; nếu ghi chú là một phần bắt buộc của bất biến, phải rollback toàn bộ.

**Bài 5 — Giao dịch dài.** Một method mở transaction rồi gọi HTTP API mất 30 giây trước khi commit. Vấn đề gì có thể xuất hiện?

> **Gợi ý:** khóa và tài nguyên DB bị giữ trong lúc chờ mạng; tăng tranh chấp, timeout và khả năng deadlock. Cân nhắc rút ngắn transaction, outbox hoặc mô hình phối hợp giữa hệ thống.

## 11. Ghi nhớ và áp dụng

**Bắt đầu transaction** xác định nhóm câu lệnh cần đi cùng nhau. **COMMIT** xác nhận các thay đổi khi tất cả bước và điều kiện nghiệp vụ đạt yêu cầu. **ROLLBACK** hoàn tác các thay đổi chưa commit khi có lỗi hoặc quyết định từ chối nghiệp vụ. **SAVEPOINT** cho phép rollback một phần, nhưng không tạo ra commit độc lập.

Trong ứng dụng Java, hãy đặt ranh giới giao dịch ở nơi thể hiện trọn vẹn một nghiệp vụ, dùng **cùng một JDBC Connection** hoặc transaction manager đúng cấu hình, kiểm tra số dòng cập nhật, xử lý lỗi và quản lý connection rõ ràng. Kết hợp transaction với ràng buộc lược đồ, cơ chế cô lập, kiểm soát đồng thời, idempotency và giám sát vận hành để dữ liệu vừa **nhất quán** vừa **bền vững**.
