# Không thử lại toàn bộ thao tác một cách mù quáng khi kết quả commit chưa rõ

Trong Spring Framework Data Access, một ngoại lệ lúc thực thi SQL hoặc khi kết thúc transaction **không phải lúc nào cũng cho biết chắc chắn tác động nghiệp vụ đã được commit hay chưa**. Trường hợp khó nhất xảy ra khi database đã nhận và xử lý `COMMIT`, nhưng ứng dụng mất kết nối, bị timeout hoặc không nhận được phản hồi xác nhận. Từ góc nhìn ứng dụng, kết quả lúc này là **chưa xác định** (*commit outcome unknown*): có thể dữ liệu đã được ghi vĩnh viễn, cũng có thể transaction đã thất bại.

Nếu ứng dụng lập tức chạy lại toàn bộ nghiệp vụ, một thao tác như trừ tiền, tạo đơn hàng, đặt chỗ hoặc gửi lệnh xuất kho có thể xảy ra **hai lần**. `@Transactional` và cơ chế rollback không tự bảo đảm chống trùng khi lần commit trước đã hoàn tất mà client chỉ mất kết quả trả về.

Bài học tập trung vào nhận biết trạng thái chưa rõ, phân loại ngoại lệ phù hợp, thiết kế **idempotency key** và **reconciliation** (đối soát trạng thái đã commit), rồi mới quyết định có được retry hay không.

## 1. Điều gì xảy ra nếu phản hồi của COMMIT bị mất?

Xét nghiệp vụ trừ 30 đơn vị từ tài khoản có số dư ban đầu 100:

~~~text
Ứng dụng                      Database
   |                              |
   | BEGIN                        |
   |----------------------------->|
   | UPDATE balance = 100 - 30    |
   |----------------------------->|
   | COMMIT                       |
   |----------------------------->|
   |                    commit thành công: balance = 70
   |         X mất kết nối / không nhận được ACK
   |
   | timeout / exception
   |      |
   |      +-- Không biết database đã commit hay rollback
~~~

Nếu client retry bằng một lệnh `UPDATE wallet_account SET balance = balance - 30` **mới**, giao dịch thứ hai có thể chạy thành công và làm số dư còn **40**. Database không sai: nó đã xử lý hai giao dịch hợp lệ. Lỗi là ứng dụng không có cơ chế nhận diện đây là **cùng một ý định nghiệp vụ** bị gửi lại.

Trạng thái cần phân biệt:

| Trạng thái | Bằng chứng | Hành động phù hợp |
| --- | --- | --- |
| **Đã commit** | Đọc được receipt/kết quả nghiệp vụ đã commit với cùng request ID và payload hợp lệ | Trả lại kết quả cũ; **không** áp dụng tác động lần nữa |
| **Đã rollback chắc chắn** | Transaction manager/database có bằng chứng rollback thành công và không có side effect ngoài transaction | Có thể thử lại nếu lỗi thực sự có khả năng phục hồi và các điều kiện nghiệp vụ còn đúng |
| **Chưa xác định** | Mất kết nối, timeout lúc commit, process chết gần ranh giới commit, không có xác nhận đáng tin | Đối soát theo operation ID; chưa được phép kết luận “thất bại” |
| **Đang xử lý** | Lần gọi trước chưa kết thúc hoặc một worker khác đang giữ quyền xử lý cùng ID | Trả `PENDING`/hẹn kiểm tra lại, hoặc retry an toàn bằng cùng khóa có cơ chế loại trùng |
| **Đã từ chối theo nghiệp vụ** | Có kết quả cuối cùng như không đủ số dư, yêu cầu không hợp lệ | Trả đúng kết quả nghiệp vụ; không retry nguyên request y hệt theo vòng lặp vô hạn |

**Không nhận được ACK không có nghĩa database chưa commit.** Tương tự, một timeout HTTP tới service không chứng minh service chưa chạy transaction: request có thể vẫn tiếp tục sau khi client ngừng chờ.

### Tại sao ROLLBACK không giải cứu được commit đã hoàn tất?

`ROLLBACK` chỉ tác động lên một transaction còn có thể rollback. Khi `COMMIT` đã thành công, việc gọi rollback từ ứng dụng **không thể tự đảo lại** dữ liệu đã commit. Tài liệu API `PlatformTransactionManager` của Spring còn nhấn mạnh: sau khi `commit(status)` trả về hoặc ném ngoại lệ, transaction manager xem transaction là đã hoàn tất và đã cleanup; **không gọi `rollback(status)` lần nữa trên cùng `TransactionStatus`**. Thao tác đó sẽ dẫn đến lỗi trạng thái và không thể chứng minh điều gì về kết quả commit.

Vì thế quy trình phục hồi phải dựa vào **bằng chứng nghiệp vụ đã commit** và một API lặp lại an toàn, thay vì cố gọi rollback cho một transaction có kết cục không rõ.

## 2. Ngoại lệ Spring cho biết điều gì và không cho biết điều gì?

`JdbcTemplate` chuyển đổi nhiều `SQLException` của JDBC thành hệ `DataAccessException`. Lớp transaction manager có thể ném `TransactionException` khi commit/rollback hoặc quản lý transaction thất bại. Những tên lớp này rất hữu ích để chẩn đoán, nhưng **không tự động trả lời câu hỏi “nghiệp vụ này đã có tác động một lần hay chưa?”**.

| Tín hiệu | Thường gợi ý | Quy tắc an toàn |
| --- | --- | --- |
| `TransientDataAccessException` / các subclass | Một lỗi hạ tầng hoặc cạnh tranh có khả năng biến mất ở lần thử sau | “Có thể hồi phục bằng retry” **khác với** “retry toàn bộ nghiệp vụ là an toàn”; phải biết trạng thái và idempotency |
| `CannotGetJdbcConnectionException` trước khi bắt đầu thao tác DB | Không lấy được kết nối để thực hiện công việc lần này | Vẫn kiểm tra liệu **một lần gọi trước** với cùng request ID đã commit chưa; không suy luận từ riêng exception hiện tại |
| `DataAccessResourceFailureException` hoặc mất kết nối khi đang ghi | Tài nguyên DB gặp lỗi; SQL có thể đã được gửi | Kết quả từng câu lệnh, giao dịch hoặc các side effect ngoài DB cần được đối soát |
| `TransactionSystemException` ở commit/rollback | Transaction manager gặp lỗi hệ thống, ví dụ SQLException từ JDBC commit | Không kết luận tự động COMMIT đã thất bại; kiểm tra nguyên nhân và tình trạng commit |
| `UnexpectedRollbackException` | Transaction coordinator đã rollback khi caller kỳ vọng commit | Đây là tín hiệu rollback của transaction do coordinator quản lý; vẫn kiểm tra side effect ngoài transaction hoặc các transaction độc lập đã commit |
| `DuplicateKeyException` | Vi phạm unique constraint | Với idempotency key có thể là lần gọi trùng hợp lệ, hoặc **một payload khác dùng lại key**; phải truy vấn và so sánh request |
| `OptimisticLockingFailureException` hoặc lỗi đồng thời tương tự | Một bản ghi không còn thỏa điều kiện version/concurrency | Cần nạp lại trạng thái, kiểm tra tính hợp lệ trước khi lập kế hoạch retry |
| Lỗi validation, foreign key hoặc kiểu dữ liệu | Yêu cầu không hợp lệ hoặc sai contract | Retry y nguyên thường không giúp gì; sửa nguyên nhân hoặc trả lỗi cho client |

`DataSourceTransactionManager` có thể bọc lỗi JDBC commit/rollback trong `TransactionSystemException`; `JdbcTransactionManager` còn dịch được một số lỗi tài nguyên thành `DataAccessException` tương ứng. Vì vậy **không viết quy tắc “chỉ bắt TransactionSystemException thì outcome unknown, còn DataAccessException thì rollback chắc chắn”**. Phải xem *lỗi xảy ra ở pha nào*, có bằng chứng commit/rollback hay không, và backend thuộc loại nào.

### Phân biệt lỗi trước COMMIT và lỗi chính tại COMMIT

- **Lỗi SQL bên trong transaction**, exception unchecked thoát ra và transaction manager rollback thành công: có cơ sở kết luận các thay đổi **của transaction đó** đã rollback. Các hiệu ứng bên ngoài transaction hoặc một `REQUIRES_NEW` đã commit trước đó vẫn độc lập.
- **Lỗi trong quá trình commit**: database có thể đã nhận/ghi commit trước khi kết nối đứt. Một lỗi I/O không có bằng chứng là rollback thành công.
- **Lỗi sau commit, trước phản hồi API**: transaction thực tế đã commit, nhưng caller có thể chỉ thấy timeout hoặc kết nối HTTP bị đóng.
- **Process bị kill gần lúc commit**: sau khi restart, không còn exception ban đầu để suy luận; cần truy vấn kết quả theo ID ổn định.

Mã SQLState, vendor error code, stack trace và log JDBC giúp tìm nguyên nhân, nhưng **không thay thế phép đối soát** trong các trường hợp chưa có bằng chứng cuối cùng.

## 3. Retry khác với chạy lại thao tác có side effect

Một thao tác **idempotent** cho cùng ý định lặp lại vẫn dẫn tới cùng hiệu ứng nghiệp vụ cuối cùng. Một phép đọc thuần túy thường dễ retry. Một phép cập nhật gia tăng hoặc trừ dần thì khác.

| Phép toán | Điều xảy ra khi thực thi hai lần | Điều cần làm |
| --- | --- | --- |
| `SELECT` chỉ đọc từ DB | Thường không tạo side effect | Có thể retry theo chính sách read timeout; cân nhắc consistency khi đọc replica |
| `UPDATE balance = balance - 30` | Trừ 60 nếu cả hai lần commit | Bắt buộc key nghiệp vụ + transaction/unique constraint để ngăn lặp |
| `INSERT` có primary key cố định | Lần hai có thể vi phạm unique constraint | Dùng key để nhận diện cùng intent, trả lại kết quả đã lưu và xác minh payload |
| `UPDATE status = 'CLOSED'` | Giá trị cuối có thể vẫn là `CLOSED` | Chưa chắc an toàn nếu có trigger, phiên bản, audit, email, event hoặc điều kiện chuyển trạng thái |
| Tạo đơn với ID server sinh mới mỗi lần | Có thể có hai đơn khác nhau | Client tạo/stabilize operation ID, chống trùng tại DB |
| Gửi email, gọi cổng thanh toán hoặc publish message | Có thể thực hiện hai side effect ở hệ thống khác | Dùng idempotency API của hệ thống ngoài, outbox, dedup hoặc đối soát hai phía |

Khái niệm “safe to retry” luôn gắn với **toàn bộ hiệu ứng** của yêu cầu, không chỉ câu SQL chính. Một câu lệnh `UPDATE` idempotent về dữ liệu có thể vẫn tạo thêm bản ghi audit hoặc gửi sự kiện ở mỗi lần thực thi.

Ví dụ đối chiếu:

~~~sql
-- KHÔNG an toàn khi retry mù: mỗi lần chạy đều giảm số dư
UPDATE wallet_account SET balance = balance - 30 WHERE id = 1;

-- Có điều kiện giúp tránh số dư âm nhưng KHÔNG chống trừ hai lần:
UPDATE wallet_account
SET balance = balance - 30
WHERE id = 1 AND balance >= 30;
~~~

Điều kiện số dư là bảo vệ nghiệp vụ cần thiết, nhưng **không phải idempotency**. Nếu tài khoản có đủ tiền cho hai lần, cả hai phép cập nhật vẫn có thể thành công.

## 4. Mô hình đúng: request ID + receipt + transaction

Mỗi **ý định nghiệp vụ** phải có một định danh ổn định, ví dụ `request_id = 'debit-2026-0042'`. Client **giữ nguyên ID khi gửi lại** do mất phản hồi. Không tạo UUID mới ở từng retry, vì như vậy database sẽ xem đó là những yêu cầu khác nhau.

Dữ liệu lưu cùng transaction gồm:

~~~text
wallet_account
  id                 PRIMARY KEY
  balance

request_receipt
  request_id         PRIMARY KEY  <-- chống trùng tại database
  account_id
  amount
  balance_after      <-- kết quả nghiệp vụ đã commit
~~~

Trong **cùng một** transaction:

1. Kiểm tra `request_receipt` theo `request_id`.
2. Nếu đã tồn tại, so sánh `account_id`, `amount` và các trường quan trọng với request hiện tại. Nếu khớp, trả lại kết quả cũ; nếu khác, từ chối reuse ID.
3. Nếu chưa tồn tại, thực hiện nghiệp vụ (ví dụ kiểm tra đủ tiền rồi debit), ghi receipt và kết quả cuối cùng.
4. Commit **cả cập nhật và receipt**. Nếu transaction rollback, cả hai đều bị rollback.

Ràng buộc `PRIMARY KEY(request_id)` là lớp bảo vệ cấp DB; không chỉ dựa vào `if (!exists) insert` ở Java. Trong cạnh tranh đồng thời, **hai transaction đều có thể kiểm tra và thấy “chưa tồn tại”**. DB unique constraint phải quyết định chỉ một bản ghi receipt được commit cho key. Transaction thua cuộc phải rollback, sau đó caller kiểm tra receipt đã commit và trả kết quả phù hợp. Với isolation level và driver khác nhau, cần kiểm thử lỗi khóa, chờ lock hoặc deadlock thực tế.

**Đừng ghi receipt ở một transaction riêng trước khi cập nhật tài khoản**, vì có thể xuất hiện receipt “thành công” nhưng debit thất bại. Tương tự, không commit debit rồi mới lưu receipt ở transaction sau; khi app chết giữa hai bước, không còn khả năng phân biệt đã debit hay chưa chỉ bằng receipt.

### Một request ID không được dùng cho hai ý định khác nhau

Ví dụ cùng `request_id` nhưng lần sau đổi số tiền từ 30 sang 80. Đó **không phải retry** mà là yêu cầu khác. Phải trả lỗi conflict/validation và không giả vờ kết quả cũ áp dụng cho request mới. Với payload nhiều trường, lưu một **fingerprint** từ bản canonical của những trường xác định ý định (tài khoản, số tiền, tiền tệ, người nhận, loại thao tác, phiên bản schema); cần định nghĩa thứ tự, chuẩn hóa chuỗi và version của fingerprint ổn định.

Key nên được gắn với tenant/người dùng nếu ID chỉ unique trong phạm vi đó: ví dụ unique `(tenant_id, request_id)`. Việc đối chiếu payload phải tránh lộ dữ liệu của tenant khác. Thời gian lưu receipt phải bao phủ cửa sổ retry và yêu cầu kiểm toán nghiệp vụ; xóa receipt quá sớm có thể khiến một retry đến muộn tạo tác động lặp.

## 5. Ví dụ Java 17 chạy được: giả lập mất phản hồi sau commit

Ví dụ dùng **Spring JDBC, `TransactionTemplate` và H2 in-memory**. Chương trình thể hiện hai kịch bản:

- **Không có chống trùng**: gọi debit hai lần tạo số dư từ 100 thành 40.
- **Có receipt cùng transaction**: debit 30 thành 70; giả lập client mất phản hồi **sau khi commit thực sự thành công**; đọc receipt và retry bằng **cùng request ID** không debit thêm.

Điểm quan trọng: ví dụ **không giả mạo lỗi JDBC xảy ra bên trong `Connection.commit()`**. Lỗi giả lập chỉ nằm ở tầng phản hồi sau khi transaction hoàn tất. Nó minh họa vì sao trạng thái client “UNKNOWN” có thể khác trạng thái database “COMMITTED”.

Cấu trúc dự án:

~~~text
commit-unknown-demo/
├── pom.xml
└── src/main/java/example/CommitUnknownDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>commit-unknown-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.CommitUnknownDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/CommitUnknownDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.Optional;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class CommitUnknownDemo {

    record Receipt(String requestId, long accountId,
                   int amount, int balanceAfter) {}

    record Result(boolean newlyApplied, int balanceAfter) {}

    static final class ReplyLostException extends RuntimeException {}

    static final class DebitService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;

        DebitService(JdbcDataSource dataSource) {
            this.jdbc = new JdbcTemplate(dataSource);
            this.tx = new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));
        }

        Result debitOnce(String requestId, long accountId, int amount) {
            if (requestId == null || requestId.isBlank() || amount <= 0) {
                throw new IllegalArgumentException("Invalid request");
            }

            return tx.execute(status -> {
                Optional<Receipt> prior = findReceipt(requestId);
                if (prior.isPresent()) {
                    Receipt saved = prior.get();
                    if (saved.accountId() != accountId
                            || saved.amount() != amount) {
                        throw new IllegalArgumentException(
                                "Same key, different intent");
                    }
                    return new Result(false, saved.balanceAfter());
                }

                int changed = jdbc.update("""
                        UPDATE wallet_account
                        SET balance = balance - ?
                        WHERE id = ? AND balance >= ?
                        """, amount, accountId, amount);
                if (changed != 1) {
                    throw new IllegalStateException(
                            "Account missing or insufficient balance");
                }

                int balance = jdbc.queryForObject(
                        "SELECT balance FROM wallet_account WHERE id = ?",
                        Integer.class, accountId);

                jdbc.update("""
                        INSERT INTO request_receipt
                            (request_id, account_id, amount, balance_after)
                        VALUES (?, ?, ?, ?)
                        """, requestId, accountId, amount, balance);

                return new Result(true, balance);
            });
        }

        Optional<Receipt> findReceipt(String requestId) {
            List<Receipt> rows = jdbc.query("""
                    SELECT request_id, account_id, amount, balance_after
                    FROM request_receipt
                    WHERE request_id = ?
                    """,
                    (rs, rowNum) -> new Receipt(
                            rs.getString(1), rs.getLong(2),
                            rs.getInt(3), rs.getInt(4)),
                    requestId);
            return rows.stream().findFirst();
        }

        int balance(long accountId) {
            return jdbc.queryForObject(
                    "SELECT balance FROM wallet_account WHERE id = ?",
                    Integer.class, accountId);
        }
    }

    private static void applyThenLoseReply(DebitService service) {
        service.debitOnce("debit-2026-0042", 1L, 30);
        // TransactionTemplate.execute đã hoàn tất và COMMIT thành công.
        // Giả lập phản hồi bị mất trên đường về client.
        throw new ReplyLostException();
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:commit_unknown;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE wallet_account (
                    id BIGINT PRIMARY KEY,
                    balance INT NOT NULL
                )
                """);
        jdbc.execute("""
                CREATE TABLE request_receipt (
                    request_id VARCHAR(80) PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    amount INT NOT NULL,
                    balance_after INT NOT NULL
                )
                """);
        jdbc.update("INSERT INTO wallet_account(id, balance) VALUES (1,100)");
        jdbc.update("INSERT INTO wallet_account(id, balance) VALUES (2,100)");

        // Đối chứng: retry mù trên tài khoản số 2.
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - 30 WHERE id = 2
                """);
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - 30 WHERE id = 2
                """);
        int naiveBalance = jdbc.queryForObject(
                "SELECT balance FROM wallet_account WHERE id = 2",
                Integer.class);
        System.out.println("naive balance=" + naiveBalance);

        // Tài khoản số 1 có receipt lưu cùng transaction.
        DebitService service = new DebitService(dataSource);
        try {
            applyThenLoseReply(service);
        } catch (ReplyLostException ex) {
            System.out.println("client result=UNKNOWN");
        }

        // Đối soát bằng khóa ổn định, sau khi transaction đã kết thúc.
        String key = "debit-2026-0042";
        System.out.println("reconcile="
                + (service.findReceipt(key).isPresent()
                        ? "APPLIED" : "ABSENT"));

        // Nếu caller vẫn cần gửi lại, dùng CÙNG key và cùng payload.
        Result retry = service.debitOnce(key, 1L, 30);
        System.out.println("same-key retry newlyApplied="
                + retry.newlyApplied());
        System.out.println("safe balance=" + service.balance(1L));
        int count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM request_receipt",
                Integer.class);
        System.out.println("receipts=" + count);
    }
}
~~~

Trong thư mục gốc dự án, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng mà chương trình in ra với H2 và dữ liệu ở trên:

~~~text
naive balance=40
client result=UNKNOWN
reconcile=APPLIED
same-key retry newlyApplied=false
safe balance=70
receipts=1
~~~

Giải thích diễn biến:

1. Hai lệnh update “ngây thơ” trừ 30 trên tài khoản 2, nên số dư 100 → 70 → 40.
2. Lần gọi `debitOnce` đầu với ID ổn định trên tài khoản 1 cập nhật 100 → 70 rồi ghi receipt **cùng transaction**. `TransactionTemplate.execute` trở về nghĩa là transaction đã kết thúc thành công trong ví dụ.
3. `ReplyLostException` chỉ được ném **sau** lần commit đầu. Nó đại diện cho lỗi client không nhận được kết quả, không phải chứng cứ rollback.
4. Truy vấn receipt từ một lần đọc sau đó trả `APPLIED`.
5. Lần gọi lại với cùng ID và payload đọc receipt, trả `newlyApplied=false`; không chạy thêm câu lệnh debit. Số dư vẫn 70, chỉ có một receipt.

Điều ví dụ **không chứng minh**: tính bền vững của H2 in-memory qua process restart, mọi chiến lược lock/concurrency của DB production, hay cách một JDBC driver xử lý kết nối đứt đúng giữa `COMMIT`. H2 chỉ mô phỏng logic ứng dụng khi ACK bị mất. Cần thử với hệ quản trị đích và test fault injection phù hợp trước khi dùng cho giao dịch có giá trị lớn.

### Vì sao dữ liệu và receipt phải dùng cùng DataSource?

`TransactionTemplate` dùng `DataSourceTransactionManager(dataSource)` và `JdbcTemplate` dùng **chính DataSource đó**. Khi callback transaction đang chạy, `JdbcTemplate` lấy kết nối được Spring liên kết với transaction hiện tại. Vì vậy `UPDATE wallet_account` và `INSERT request_receipt` tham gia cùng transaction.

Nếu một thao tác tự tạo kết nối bằng `DriverManager.getConnection`, dùng một DataSource khác, hoặc mở `REQUIRES_NEW` rồi commit độc lập, receipt và debit có thể **không còn nguyên tử**. Thiết kế phải dựa vào ranh giới transaction thật, không chỉ vị trí các dòng Java.

### Cạnh tranh đồng thời vẫn cần unique constraint

Trong demo tuần tự, kiểm tra receipt có trước insert trông đã đủ. Production có thể có hai request cùng key đến hai instance:

~~~text
Instance A               Instance B
  SELECT receipt: none     SELECT receipt: none
  UPDATE account           UPDATE account (có thể bị chờ lock)
  INSERT receipt           INSERT receipt (đụng unique)
  COMMIT                   rollback hoặc nhận duplicate-key
~~~

Cần để database enforce unique key. Khi xảy ra `DuplicateKeyException` hoặc lock timeout, xử lý **bên ngoài transaction đã thất bại**, rồi tra cứu receipt đã commit và so sánh payload. Không bắt lỗi unique ngay trong callback rồi cố commit như thể mọi câu SQL trước đó đều hợp lệ. Hành vi transaction sau SQL error khác nhau giữa database và isolation level; phải để transaction rollback nếu cần.

Khi receipt chưa thấy vì transaction đầu vẫn đang chạy, kết quả vẫn có thể là `IN_PROGRESS/UNKNOWN`. Có thể retry bằng **cùng key** nếu toàn bộ ghi và dedup bảo đảm, có retry budget, timeout và backoff; hoặc trả trạng thái đang xử lý để client hỏi lại. Không đổi key để “né duplicate key”.

## 6. Quy trình xử lý commit chưa rõ trong ứng dụng Spring

Một quy trình thực tế có thể biểu diễn như sau:

~~~text
Nhận yêu cầu có request_id ổn định + payload đã chuẩn hóa
            |
            v
Tra receipt/trạng thái nghiệp vụ theo request_id
            |
       +----+-------------------+
       |                        |
   Có kết quả                 Chưa có kết quả
       |                        |
So sánh payload             Xác định có in-flight?
       |                        |
  +----+----+                 +--+----------------+
  |         |                 |                   |
Khớp      Khác            Đang chạy          Chắc chắn không chạy?
  |         |                 |                   |
Trả lại  CONFLICT       PENDING/RECONCILE     Gọi attempt an toàn
kết quả                    (chờ trạng thái)    với cùng request_id
                                                  |
                                                  v
                                        DB transaction + unique key
                                                  |
                                        +---------+---------+
                                        |                   |
                                      Commit             Lỗi/timeout
                                        |                   |
                                    Trả kết quả     Phân loại và reconcile
~~~

Ở đây “chắc chắn không chạy” không phải lúc nào cũng chứng minh được bằng một phép `SELECT` đơn lẻ. Một lần ghi có thể đang in-flight, chưa commit, hoặc replica đọc chậm. Vì vậy phương án **gọi lại một operation được thiết kế idempotent** thường thực tế hơn việc cố suy diễn “absence = failed” từ một truy vấn.

Trình tự áp dụng:

1. **Phân loại lỗi:** là lỗi nhập liệu, rollback xác nhận, concurrency failure, tài nguyên transient hay commit/response unknown? Có side effect nào đã chạy ngoài transaction không?
2. **Giữ nguyên identity:** lấy lại cùng `request_id`, tenant, payload fingerprint của ý định ban đầu.
3. **Tra nguồn sự thật:** ưu tiên đọc trạng thái đã commit từ DB chính/nguồn authoritative, tránh đọc replica lag rồi kết luận vội.
4. **So khớp semantic:** receipt của cùng key nhưng khác payload là conflict, không trả “thành công”.
5. **Quyết định:** `APPLIED` → trả kết quả cũ; `REJECTED` cuối cùng → trả lỗi cũ; `PENDING/UNKNOWN` → tiếp tục đối soát; chỉ tạo attempt mới khi đã có chống trùng đúng.
6. **Giới hạn retry:** timeout tổng, số lần tối đa, exponential backoff có jitter, theo dõi tình trạng DB. Nếu vẫn không rõ, giữ yêu cầu ở trạng thái chờ phục hồi/đối soát và đưa ra mã tra cứu, không báo “thất bại chắc chắn”.
7. **Ghi log có cấu trúc:** `request_id`, attempt number, pha bắt lỗi, SQLState/vendor code (nếu có), transaction status được biết, kết quả đối soát. Không ghi mật khẩu hay payload nhạy cảm.

### Quyết định trả API response

Với HTTP API, quy tắc ví dụ:

| Trạng thái nội bộ | HTTP response có thể dùng | Ý nghĩa trả cho client |
| --- | --- | --- |
| `APPLIED` | `200 OK` hoặc `201 Created` theo contract | Thành công; cung cấp cùng operation ID/kết quả trên lần gọi lặp |
| `PENDING/UNKNOWN` | `202 Accepted` kèm URL tra trạng thái hoặc response “pending” theo contract | Chưa có kết quả cuối; client **không tạo yêu cầu mới** |
| `SAME_KEY_DIFFERENT_PAYLOAD` | `409 Conflict` | Request ID đã gắn với ý định khác |
| `REJECTED` hợp lệ | `4xx` thích hợp theo contract | Từ chối nghiệp vụ cuối cùng, không retry y nguyên |
| Hạ tầng tạm thời chưa phục hồi | `503 Service Unavailable` hoặc timeout theo contract | Chỉ retry khi endpoint có idempotency, giữ nguyên key và tuân thủ `Retry-After` nếu cung cấp |

Những mã HTTP trên là **gợi ý thiết kế API**, không phải mapping tự động từ `DataAccessException` sang HTTP. Điều quan trọng nhất là contract phải cho phép client biết cùng ID sẽ được xử lý/tra cứu an toàn, kể cả khi response ban đầu bị mất.

## 7. Vì sao chỉ thêm `@Transactional` hoặc `@Retryable` chưa đủ?

`@Transactional` đảm bảo ranh giới giao dịch của các thao tác **thực sự tham gia transaction phù hợp**, khi lời gọi đi qua proxy Spring (với kiểu transaction quản lý qua proxy mặc định). Nó giúp rollback nếu exception được nhận diện theo quy tắc rollback. Nhưng nếu commit đã thành công rồi ACK mất, một lần gọi service **mới** với payload y hệt vẫn là transaction mới, và có thể debit lần thứ hai.

Một đoạn như sau là **không đủ để chống ghi trùng**:

~~~java
@Service
class WalletService {
    private final JdbcTemplate jdbc;

    WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void debit(long id, int amount) {
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - ?
                WHERE id = ?
                """, amount, id);
    }
}
~~~

Đây là ví dụ **đặt trong Spring application** có cấu hình transaction và imports tương ứng; nó minh họa thiếu request ID/receipt, không phải chương trình đầy đủ. Gọi `debit(1, 30)` hai lần, mỗi lần transaction commit, sẽ trừ hai lần.

Gắn thêm một retry annotation và retry khi có `TransientDataAccessException` **không tự sửa tính chất này**. Nếu retry advice nằm bên ngoài ranh giới transaction, mỗi attempt có thể tạo transaction riêng; nếu nằm bên trong, có thể gặp transaction rollback-only hoặc một transaction đã không còn hợp lệ. Thứ tự advice/proxy cũng ảnh hưởng hành vi. Hãy cấu hình nơi retry diễn ra có chủ đích, kiểm thử thực tế, và quan trọng hơn: **endpoint/operation phải idempotent trước**.

Tương tự, không nên gắn `@Transactional` lên cả một vòng lặp retry trong cùng method rồi hy vọng rollback “đặt lại” trạng thái sau một lỗi commit. Khi transaction kết thúc không rõ, phải **tạo lại phạm vi transaction hợp lệ cho attempt mới** và kiểm tra receipt, không tái sử dụng `TransactionStatus` đã hoàn thành.

## 8. Công việc đa bước, service ngoài DB và transactional outbox

Một yêu cầu thực tế có thể gồm:

~~~text
1. Ghi trạng thái đơn hàng vào DB
2. Trừ kho trong DB
3. Gửi event Kafka
4. Gọi dịch vụ thanh toán
5. Gửi email
~~~

Một transaction JDBC cục bộ chỉ kiểm soát những câu SQL trên cùng tài nguyên DB tham gia transaction. Nó **không tự rollback** Kafka event, HTTP request, email hoặc transaction ở một DB khác. Ngay cả khi phần DB có receipt chống trùng, lần retry nguyên workflow vẫn có thể phát lại các bước ngoài DB.

### Transactional outbox cho event

Một lựa chọn thường gặp là ghi **trạng thái nghiệp vụ + outbox event** vào **cùng transaction DB**:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(80) PRIMARY KEY,
    request_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload VARCHAR(4000) NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Trong transaction nghiệp vụ, thêm outbox record cùng `request_id`; sau commit, một publisher riêng đọc và gửi event. Nếu publisher gửi thành công nhưng chết trước khi đánh dấu `published`, nó có thể gửi lại event. Vì vậy consumer cũng phải idempotent theo `event_id`. Outbox giúp tránh DB commit thành công mà không có thông tin để phát event, **không biến toàn bộ workflow thành exactly-once**.

Nếu gọi payment gateway, cần dùng **idempotency key do gateway hỗ trợ**, query transaction/payment status bằng mã giao dịch hoặc cơ chế đối soát nhà cung cấp. Không phát lại lệnh charge bằng mã mới chỉ vì ứng dụng bị timeout. Mọi thao tác bù trừ (refund, reverse, cancel) là **nghiệp vụ mới có ID riêng và audit riêng**; không coi nó là rollback kỹ thuật của transaction đã commit.

### Không nhầm exactly-once effect với exactly-once delivery

Một message có thể được giao nhiều lần trong hệ thống at-least-once, nhưng consumer kiểm tra key rồi chỉ ghi một tác động nghiệp vụ. Hãy dùng cách diễn đạt chính xác: **at-most-once effect trong phạm vi tài nguyên/contract chống trùng đã triển khai**, còn việc giao message hay request không nhất thiết chỉ diễn ra một lần.

## 9. Các lỗi triển khai thường gặp

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Client tạo UUID mới mỗi lần HTTP retry | DB xem đó là nhiều yêu cầu | Giữ ID của **ý định gốc** xuyên mọi attempt |
| Chỉ kiểm tra `SELECT ... WHERE request_id=?` rồi mới INSERT | Hai request đồng thời cùng thấy “không có” | Unique constraint ở DB + transaction rollback/đọc lại receipt |
| Receipt commit riêng, debit commit riêng | App chết giữa hai commit tạo trạng thái không nhất quán | Ghi receipt và debit trong cùng transaction |
| Receipt tồn tại nhưng không lưu payload gốc | Không phát hiện cùng key dùng cho ý định khác | Lưu payload fingerprint/field bất biến và so sánh |
| Bắt `DuplicateKeyException` rồi trả success ngay | Duplicate có thể do ID bị reuse sai intent, hoặc lỗi unique khác | Đọc đúng receipt và so sánh request trước khi trả |
| Bắt exception trong `@Transactional` rồi chỉ log | Method có thể trở về bình thường và bị commit ngoài ý muốn | Propagate lỗi hoặc đánh dấu rollback-only khi cần |
| Chỉ đọc replica ngay sau timeout | Replica lag gây false “không tồn tại” | Đọc nguồn authoritative, chấp nhận `UNKNOWN` nếu chưa đủ bằng chứng |
| Retry mọi `TransientDataAccessException` | Loại lỗi nói về khả năng hồi phục, không bảo đảm side effect chưa xảy ra | Retry chỉ khi operation được thiết kế idempotent |
| Giữ receipt vài phút nhưng client retry sau vài giờ/ngày | Key đã bị xóa khiến phát sinh thao tác lần hai | Đặt retention theo contract, hạn chót retry và nghĩa vụ kiểm toán |
| Có idempotency DB nhưng gửi email/charge ngoài transaction trong cùng method | Lần lặp vẫn tạo side effect bên ngoài | Dùng outbox và idempotency/đối soát phía dịch vụ ngoài |
| Khi commit lỗi gọi `rollback(status)` lần hai | `TransactionStatus` đã hoàn tất/cleanup; không giải quyết ambiguity | Đọc kết quả nghiệp vụ, retry attempt mới có key ổn định |
| Cấu hình retry đồng loạt ở HTTP client, service, DB layer | Khuếch đại số lần gọi và tải khi hệ thống đang lỗi | Chọn một tầng sở hữu retry budget và backoff |

**Điểm quyết định:** một đoạn catch/retry đẹp về kỹ thuật không có giá trị nếu không định nghĩa rõ “cùng một nghiệp vụ” được nhận diện như thế nào và state nào xác nhận kết quả sau commit.

## 10. Kiểm thử tình huống kết quả commit chưa rõ

Đừng chỉ có happy-path test. Một bộ kiểm thử tương đối đầy đủ nên gồm:

1. **Mất response sau commit:** cho transaction DB thành công, sau đó giả lập timeout/đứt kết nối API trước khi trả response. Retry **cùng ID**; xác nhận chỉ một lần debit và một receipt.
2. **Lỗi trước commit:** gây lỗi constraint trong transaction và cho rollback; xác nhận không có debit hoặc receipt nửa vời.
3. **Hai caller cùng key:** chạy concurrent trên DB/driver mục tiêu. Một caller ghi được, caller còn lại xử lý collision/lock hợp lệ; kết quả cuối chỉ một tác động. Không dựa vào test tuần tự để suy luận concurrency.
4. **Cùng key, payload khác:** bị từ chối; số dư và receipt không thay đổi.
5. **Đọc status khi có transaction in-flight:** không trả “FAILED” chỉ vì status chưa commit; xử lý `PENDING/UNKNOWN`, timeout có giới hạn và đối soát sau.
6. **DB restart/kết nối đứt gần COMMIT:** fault injection cần quan sát trạng thái database thật sau hồi phục; mô phỏng mất ACK sau commit chỉ kiểm tra *một* nhánh.
7. **Side effect ngoài DB:** gửi lại cùng event/payment request ID và kiểm tra consumer/gateway xử lý lặp an toàn.
8. **Retention và late retry:** gửi lại sau thời gian dài, kiểm tra chính sách đã công bố; không vô tình cho key cũ được coi là yêu cầu mới.
9. **Đo traffic khi nhiều lỗi cùng xảy ra:** xác nhận retry count, exponential backoff, jitter, deadline và circuit breaker không khiến DB quá tải.
10. **Giao dịch nhiều bảng:** xác nhận receipt, dòng dữ liệu chính và outbox đều cùng commit/rollback theo một transaction.

Với unit test thuần, bạn có thể kiểm tra logic so sánh fingerprint và phân loại trạng thái. Với lỗi commit/thất lạc ACK thực, cần **integration test** ở lớp Spring/JDBC, DB thật hoặc một fault proxy cho mạng. Test được bọc `@Transactional` ở lớp test có thể tự rollback và che mất ranh giới commit bạn định kiểm tra; nên tổ chức test từ bên ngoài transaction của service.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một `TransactionSystemException` được ném khi `commit()` gặp lỗi mạng. Có chắc DB đã rollback không?

**Trả lời:** Không. Có thể database đã commit nhưng ACK bị mất. Phải đối soát theo key và state đáng tin, không chạy lại nghiệp vụ chưa có chống trùng.

**Câu 2.** Thêm điều kiện `WHERE balance >= amount` đã đủ để retry debit chưa?

**Trả lời:** Chưa. Điều kiện chỉ tránh âm số dư; nếu tiền đủ cho hai lần, cùng nghiệp vụ bị trừ hai lần. Cần một key ổn định và bảo vệ uniqueness/transaction.

**Câu 3.** `@Transactional` có bảo đảm retry cùng API request không tạo hai đơn hàng?

**Trả lời:** Không. Mỗi lần gọi có thể được commit trong transaction mới. `@Transactional` bảo vệ tính nguyên tử *bên trong một transaction*, không tự nhận diện hai lần gọi là một ý định.

**Câu 4.** Truy vấn receipt theo ID không thấy row. Có thể kết luận lần trước chưa chạy?

**Trả lời:** Chưa chắc. Lần trước có thể chưa commit, kết nối đọc đang dùng replica lag, hoặc hệ thống chưa phục hồi. Tiếp tục kiểm tra nguồn authoritative, trạng thái in-flight hoặc dùng retry đã được thiết kế idempotent với cùng key.

**Câu 5.** `DuplicateKeyException` khi insert receipt có nghĩa cả nghiệp vụ đã thành công rồi?

**Trả lời:** Không đủ. Nó cho biết có xung đột uniqueness; phải đọc record gốc và so sánh payload, đồng thời bảo đảm transaction đang thất bại đã rollback. Nếu cùng key nhưng payload khác, trả conflict.

**Câu 6.** DB và outbox trong cùng transaction có bảo đảm Kafka consumer xử lý đúng một lần không?

**Trả lời:** Không. Publisher có thể gửi message lại, consumer vẫn cần chống trùng theo event ID.

## Tài liệu tham khảo

- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html) — hợp đồng commit/rollback và transaction đã hoàn tất.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html) — `TransactionTemplate` và ranh giới transaction.
- [Spring Framework — JDBC Connections and Transaction Managers](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html) — `DataSourceTransactionManager`/`JdbcTransactionManager` và dịch ngoại lệ.
- [Spring Framework — JDBC Exception Translation](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — `SQLExceptionTranslator`/`DataAccessException`.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html) — quy tắc rollback.
- [AWS Builders' Library — Making Retries Safe with Idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) — client request ID, kết quả tương đương, yêu cầu đến muộn và trùng key khác payload.
- [PostgreSQL — COMMIT](https://www.postgresql.org/docs/current/sql-commit.html) — ý nghĩa commit của transaction.
