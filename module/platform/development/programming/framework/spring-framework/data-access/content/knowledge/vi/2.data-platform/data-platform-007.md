# Commit, rollback, auto-commit và ranh giới giao dịch

Trong một ứng dụng dùng Spring Framework để truy cập dữ liệu, nhiều câu lệnh SQL thường cùng phục vụ **một hành động nghiệp vụ**: chuyển tiền, tạo đơn hàng kèm chi tiết, hoặc ghi nhận nhiều thay đổi liên quan. Nếu câu lệnh đầu thành công nhưng câu lệnh sau lỗi, dữ liệu có thể bị bỏ lại ở trạng thái dở dang. Giao dịch (transaction) đặt ra một ranh giới để cơ sở dữ liệu quyết định **hoặc chấp nhận toàn bộ thay đổi thuộc giao dịch, hoặc hủy các thay đổi chưa được xác nhận**.

Bài học tập trung vào ý nghĩa và thời điểm của `commit`, `rollback`, `auto-commit`, cách nhận biết ranh giới giao dịch trong JDBC và Spring, và những lỗi thường gặp khi chuyển từ thao tác SQL đơn lẻ sang một quy trình nghiệp vụ.

## 1. Giao dịch là đơn vị công việc nào?

Giả sử tài khoản A có 100 đơn vị, tài khoản B có 50 đơn vị. Chuyển 30 đơn vị từ A sang B cần ít nhất hai thao tác:

```sql
UPDATE account SET balance = balance - 30 WHERE id = 1;
UPDATE account SET balance = balance + 30 WHERE id = 2;
```

Kết quả mong muốn là A = 70 và B = 80. Nếu chỉ thao tác trừ tiền được ghi nhận, tổng số dư sẽ sai. Hai lệnh vì vậy cần cùng **một giao dịch**:

1. Bắt đầu phạm vi giao dịch.
2. Thực hiện các thao tác liên quan trên cùng ngữ cảnh giao dịch.
3. Nếu mọi điều kiện nghiệp vụ đều đạt, `commit`.
4. Nếu có lỗi hoặc một điều kiện không đạt, `rollback`.

Đây là khía cạnh **atomicity (tính nguyên tử)** trong ACID: các thay đổi của giao dịch được chấp nhận như một đơn vị. Ba thuộc tính còn lại giúp hiểu giới hạn của cam kết đó:

- **Consistency:** ràng buộc dữ liệu và các bất biến nghiệp vụ cần được giữ đúng; cơ sở dữ liệu áp dụng các ràng buộc mà nó biết, còn ứng dụng vẫn phải kiểm tra những quy tắc nghiệp vụ của mình.
- **Isolation:** giao dịch đồng thời quan sát và ảnh hưởng lẫn nhau theo mức cô lập của cơ sở dữ liệu. Giao dịch không tự động ngăn mọi hiện tượng đọc bẩn, đọc không lặp lại hay cập nhật thất lạc.
- **Durability:** sau khi `commit` thành công, cơ sở dữ liệu chịu trách nhiệm duy trì kết quả theo bảo đảm lưu trữ và cấu hình của hệ quản trị.

**Quan trọng:** Giao dịch cơ sở dữ liệu chỉ kiểm soát những tài nguyên tham gia giao dịch ấy. Nó không tự thu hồi email đã gửi, HTTP request đã gọi hay tệp đã ghi ra hệ thống file.

## 2. Commit, rollback và trạng thái của thay đổi

| Thao tác | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `commit` | Kết thúc giao dịch hiện tại bằng cách xác nhận các thay đổi của nó. | Sau khi commit thành công, `rollback` của giao dịch đó không thể đảo ngược kết quả; phải dùng giao dịch bù nếu nghiệp vụ cần hoàn tác. |
| `rollback` | Hủy những thay đổi **chưa commit** của giao dịch hiện tại. | Không hoàn tác các giao dịch đã commit và không đảm bảo hoàn tác tác dụng phụ ngoài DB. |
| `auto-commit = true` | JDBC tự commit mỗi câu lệnh sau khi câu lệnh hoàn tất theo quy tắc của driver/JDBC. | Hai lệnh `UPDATE` kế tiếp thường là **hai giao dịch độc lập**. |
| `auto-commit = false` | Ứng dụng kiểm soát thời điểm kết thúc giao dịch qua `commit()` hoặc `rollback()`. | Cần kết thúc rõ ràng cả luồng thành công lẫn luồng lỗi. |

Với JDBC, chế độ auto-commit là thuộc tính của **`java.sql.Connection`**, không phải một công tắc cho toàn bộ ứng dụng. Theo mặc định, kết nối JDBC mới được tạo ở chế độ auto-commit bật, trừ khi môi trường hoặc tầng quản lý kết nối can thiệp. Trong thực tế, kết nối lấy từ pool có thể được thiết lập hoặc khôi phục trạng thái trước khi được giao cho ứng dụng.

Khi auto-commit bật, JDBC chỉ commit câu lệnh khi câu lệnh được coi là hoàn tất; với truy vấn trả `ResultSet`, việc đọc hết hoặc đóng kết quả có thể ảnh hưởng thời điểm hoàn tất. Vì vậy, không nên suy diễn rằng mọi câu lệnh đều đã commit ngay lúc `executeQuery()` trả về.

Khi auto-commit tắt, một loạt câu lệnh trên **cùng connection** có thể thuộc một giao dịch. Sau `commit()` hoặc `rollback()`, các lệnh tiếp theo sẽ đi vào giao dịch tiếp theo theo cách driver/hệ quản trị bắt đầu giao dịch. Cần hiểu thêm hai điểm của hợp đồng JDBC:

- Gọi `setAutoCommit(true)` khi đang có giao dịch hoạt động sẽ **commit giao dịch hiện tại**. Vì vậy, không dùng thao tác này để "hủy" một giao dịch đang lỗi.
- Không dựa vào `Connection.close()` để rollback: khi đóng connection có giao dịch đang hoạt động, kết quả có thể phụ thuộc driver và môi trường. Ứng dụng nên gọi `commit`/`rollback` rõ ràng; pool cần trả kết nối về trạng thái sạch.

Một số hệ quản trị có cơ chế *implicit commit* khi chạy DDL như `CREATE TABLE` hoặc `ALTER TABLE`. Đừng mặc định rằng mọi lệnh DDL đều rollback được chỉ vì ứng dụng đã tắt auto-commit.

## 3. Ranh giới giao dịch nằm ở đâu?

Ranh giới giao dịch là **phạm vi công việc cùng chia sẻ quyết định commit/rollback**, chứ không đơn giản là số dòng code hay số lệnh SQL. Có thể hình dung:

```text
Bắt đầu giao dịch
  ├─ Kiểm tra điều kiện nghiệp vụ
  ├─ UPDATE bảng 1
  ├─ INSERT/UPDATE bảng 2
  └─ Kiểm tra kết quả ghi (số hàng bị tác động, ràng buộc...)
       ├─ Thành công: COMMIT  → thay đổi được xác nhận
       └─ Thất bại: ROLLBACK → thay đổi chưa commit bị hủy
Kết thúc phạm vi giao dịch
```

Ranh giới tốt thường bao trùm **một thao tác nghiệp vụ cần tính nguyên tử**, chẳng hạn "chuyển tiền" hoặc "tạo đơn hàng cùng các dòng chi tiết". Đặt commit ngay sau mỗi câu lệnh khiến hệ thống không thể rollback toàn bộ thao tác nhiều bước. Ngược lại, kéo giao dịch qua các lời gọi HTTP chậm hoặc thời gian chờ người dùng có thể giữ khóa/kết nối lâu, tăng tranh chấp và gây timeout.

Cần phân biệt ba loại ranh giới:

- **Ranh giới lời gọi Java:** bắt đầu và kết thúc một phương thức. Phương thức Java không mặc nhiên tạo giao dịch.
- **Ranh giới JDBC:** các thao tác thực sự chạy trên connection và chế độ transaction của connection đó.
- **Ranh giới Spring:** interceptor/`PlatformTransactionManager` mở, tham gia, commit hoặc rollback giao dịch cho một phương thức được cấu hình `@Transactional`, và liên kết tài nguyên thích hợp với luồng thực thi hiện tại.

Một phương thức có thể gọi nhiều repository; chúng chỉ thực sự chung giao dịch khi cùng tham gia transaction manager và nguồn dữ liệu tương ứng. Hai connection hoặc hai data source không tự động tạo thành một giao dịch nguyên tử duy nhất.

## 4. Ví dụ JDBC đầy đủ: commit thành công, rollback khi bước sau thất bại

Ví dụ dưới dùng **Java 17+, H2 in-memory và JDBC**. Dữ liệu tài khoản được khởi tạo; lần chuyển thứ nhất thành công, lần thứ hai cố chuyển tới tài khoản không tồn tại. Thao tác trừ ở lần thứ hai được rollback vì bước cộng không thành công.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-transactions-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/TransactionDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public class TransactionDemo {
    private static final String URL =
            "jdbc:h2:mem:transaction_demo;DB_CLOSE_DELAY=-1";

    private static Connection open() throws SQLException {
        return DriverManager.getConnection(URL, "sa", "");
    }

    public static void main(String[] args) throws SQLException {
        try (Connection c = open(); Statement st = c.createStatement()) {
            st.executeUpdate(
                    "CREATE TABLE account (" +
                    "id INT PRIMARY KEY, " +
                    "balance INT NOT NULL CHECK (balance >= 0))");
            st.executeUpdate(
                    "INSERT INTO account (id, balance) VALUES (1, 100), (2, 50)");
        }

        show("Initial");
        transfer(1, 2, 30);
        show("After commit");

        try {
            transfer(1, 99, 10); // Tài khoản 99 không tồn tại.
        } catch (SQLException ex) {
            System.out.println("Transfer failed; rolled back");
        }
        show("After rollback");
    }

    private static void transfer(int from, int to, int amount)
            throws SQLException {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                changeBalance(c, from, -amount);
                changeBalance(c, to, amount);
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static void changeBalance(Connection c, int id, int delta)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "UPDATE account SET balance = balance + ? WHERE id = ?")) {
            ps.setInt(1, delta);
            ps.setInt(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Account not found: " + id);
            }
        }
    }

    private static void show(String title) throws SQLException {
        try (Connection c = open();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT id, balance FROM account ORDER BY id");
             ResultSet rs = ps.executeQuery()) {
            List<String> values = new ArrayList<>();
            while (rs.next()) {
                values.add(rs.getInt("id") + "=" + rs.getInt("balance"));
            }
            System.out.println(title + ": " + String.join(", ", values));
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=TransactionDemo
```

```text
Initial: 1=100, 2=50
After commit: 1=70, 2=80
Transfer failed; rolled back
After rollback: 1=70, 2=80
```

Giải thích theo từng ranh giới:

1. Phần tạo bảng và dữ liệu mẫu chạy trên connection mặc định auto-commit; mỗi lệnh khởi tạo thành công được ghi nhận.
2. `transfer(1, 2, 30)` mở connection khác, gọi `setAutoCommit(false)`, thực hiện hai `UPDATE` và `commit()`. Hai thay đổi cùng được chấp nhận.
3. `transfer(1, 99, 10)` đã trừ 10 ở tài khoản 1 nhưng `UPDATE` tài khoản 99 tác động **0 hàng**. Code coi đó là lỗi nghiệp vụ, ném `SQLException` và `rollback()` trước khi đóng connection; số dư tài khoản 1 quay về 70.
4. Câu lệnh `show` chạy trên connection mới chỉ thấy dữ liệu đã được commit. Demo không kiểm tra các mức isolation hoặc các tương tác đồng thời.

**Điểm thiết kế đáng chú ý:** `executeUpdate()` không nhất thiết ném exception khi `WHERE` không khớp hàng nào. Muốn coi "không tồn tại tài khoản" là thất bại, ứng dụng phải kiểm tra số hàng bị ảnh hưởng. Với chuyển tiền thật, còn cần chống âm tiền, xử lý đồng thời, kiểu `DECIMAL` cho số tiền và các quy tắc nghiệp vụ khác; demo dùng số nguyên để tách rõ cơ chế commit/rollback.

## 5. Nếu giữ auto-commit bật thì sao?

Xem hai lệnh trừ và cộng khi thực hiện tuần tự trên connection auto-commit bật:

```java
// Đoạn minh họa: c là Connection đang có auto-commit = true.
debitAccount(c, fromId, amount);   // Lệnh SQL này có thể đã commit.
creditAccount(c, toId, amount);    // Nếu lỗi, rollback không cứu được lệnh trước.
```

Đây là **đoạn mã minh họa**, không phải một chương trình độc lập; hai hàm tên `debitAccount` và `creditAccount` đại diện cho các thao tác SQL. Khi câu lệnh trừ đã được commit riêng, việc câu lệnh cộng thất bại không cho phép rollback giao dịch trước. Thậm chí gọi `rollback()` khi connection vẫn ở auto-commit true không phải cách hợp lệ để hoàn tác lệnh trước (JDBC có thể ném `SQLException`).

Sự khác biệt không nằm ở việc có `try/catch` hay không; nó nằm ở **thời điểm dữ liệu được commit** và phạm vi các lệnh tham gia chung giao dịch.

## 6. Spring quản lý commit/rollback như thế nào?

Khi ứng dụng dùng Spring JDBC, JPA hoặc tầng truy cập dữ liệu khác tích hợp với transaction manager, có thể đặt ranh giới ở một phương thức service bằng `@Transactional`. Spring mở hoặc tham gia giao dịch theo cấu hình, dùng tài nguyên tương ứng để thực thi các thao tác và quyết định commit/rollback khi lời gọi kết thúc.

Ví dụ sau là **đoạn service trong ứng dụng Spring đã cấu hình `DataSource`, `JdbcTemplate` và transaction manager thích hợp**; không phải class Java chạy độc lập. Bảng `account` ở đây được giả định lưu tiền bằng kiểu số thập phân phù hợp.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (fromId == toId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Debit rejected");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Receiver not found");
        }
    }
}
```

Trong cấu hình thông thường, một thành phần khác gọi `transferService.transfer(...)` **qua Spring bean/proxy**:

- Nếu chưa có transaction hiện hành, propagation mặc định `REQUIRED` tạo transaction mới. Nếu đã có transaction phù hợp, phương thức thường tham gia transaction đó.
- `JdbcTemplate` dùng connection liên kết với transaction đang hoạt động; các cập nhật không được auto-commit riêng lẻ như khi tự mở connection độc lập ngoài Spring.
- Nếu phương thức kết thúc bình thường và transaction này do interceptor sở hữu, Spring yêu cầu commit; nếu lỗi kích hoạt rollback, Spring yêu cầu rollback.
- Mặc định Spring rollback khi `RuntimeException` hoặc `Error` thoát ra ngoài; checked exception không tự động kích hoạt rollback, trừ khi cấu hình (chẳng hạn `@Transactional(rollbackFor = Exception.class)`) hoặc đánh dấu rollback-only.
- Ném `IllegalStateException` trong ví dụ khiến cả hai cập nhật thuộc cùng transaction bị rollback, kể cả khi lệnh đầu đã thực thi thành công.

Không gọi `connection.commit()`, `connection.rollback()` hay đổi auto-commit tùy tiện trên connection do Spring đang quản lý: điều đó có thể làm lệch ranh giới giao dịch mà transaction manager nắm giữ.

### Những điều kiện để `@Transactional` thực sự có hiệu lực

`@Transactional` **không phải câu lệnh SQL**. Annotation chỉ phát huy tác dụng khi cơ chế transaction của Spring được kích hoạt, có transaction manager áp dụng cho tài nguyên cần dùng, và lời gọi đi qua cơ chế interception thích hợp.

- Với proxy mode thông thường, phương thức của bean gọi `this.transfer(...)` trên chính bean đó là **self-invocation**; lời gọi này không đi qua proxy nên không kích hoạt ranh giới `@Transactional` mới của phương thức được gọi. Một giao dịch đã tồn tại ở phương thức gọi thì vẫn tồn tại.
- Method không được Spring quản lý, hoặc object tự tạo bằng `new`, sẽ không nhận interception của proxy.
- Giao dịch Spring thường gắn với luồng đang thực thi. Chuyển thao tác sang `@Async`, thread tự tạo hay công việc nền không mặc nhiên mang cùng transaction sang đó.
- Có annotation trên service không bảo đảm tác vụ qua hai data source hoặc thông điệp bên ngoài cùng commit nguyên tử. Điều này cần kiến trúc điều phối tài nguyên/nhất quán phù hợp.

Với một unit of work đã nằm trong transaction cấp trên, phương thức con `REQUIRED` không tự commit độc lập ngay khi return. Quyết định commit thuộc **ranh giới giao dịch bên ngoài**. Nếu một nhánh bên trong đánh dấu rollback-only mà nhánh ngoài vẫn cố commit, Spring có thể báo `UnexpectedRollbackException` để tránh báo thành công giả.

## 7. Khi exception bị bắt: giao dịch có rollback không?

Xét tình huống:

```java
@Transactional
public void placeOrder() {
    saveOrder();
    try {
        reserveInventory();
    } catch (Exception ex) {
        logFailure(ex); // Chỉ ghi log rồi kết thúc bình thường.
    }
}
```

Đây là đoạn minh họa. Nếu lỗi đã bị bắt và phương thức kết thúc bình thường, interceptor có thể **commit** các thay đổi trước đó; bắt exception không tự đồng nghĩa rollback. Mặt khác, một lời gọi con có transaction interceptor đã đánh dấu giao dịch rollback-only có thể khiến lần commit ngoài thất bại. Kết quả cụ thể tùy nơi lỗi phát sinh, propagation và cách transaction manager theo dõi trạng thái.

Khi điều kiện nghiệp vụ yêu cầu hủy toàn bộ, có thể để exception thích hợp truyền ra ngoài, cấu hình `rollbackFor` cho checked exception, hoặc chủ động đánh dấu rollback-only qua API transaction của Spring. Đừng lạm dụng việc nuốt exception rồi trả về "thành công".

Nếu dùng `TransactionTemplate` thay vì annotation, callback xác định phạm vi transaction và có thể gọi `status.setRollbackOnly()`. Đây là lựa chọn rõ ràng cho trường hợp điều khiển giao dịch bằng code; vẫn cần transaction manager thích hợp.

## 8. Savepoint và phạm vi rollback từng phần

`rollback()` thông thường hủy các thay đổi chưa commit của **toàn giao dịch**. Nếu driver và database hỗ trợ savepoint, JDBC còn cho phép quay về một mốc bên trong giao dịch:

```java
// Đoạn minh họa bên trong try với c.setAutoCommit(false).
Savepoint mark = c.setSavepoint();
try {
    performOptionalWrite(c);
} catch (SQLException ex) {
    c.rollback(mark); // Hủy phần sau savepoint; phần trước đó vẫn còn chờ commit.
}
c.commit();           // Vẫn cần quyết định cuối cùng cho giao dịch.
```

`Savepoint` và `performOptionalWrite` trong đoạn trên là thành phần của một luồng xử lý lớn hơn; đây không phải chương trình độc lập. Rollback về savepoint **không commit** phần trước nó. Nếu giao dịch cuối cùng rollback toàn bộ, phần trước savepoint cũng bị hủy.

Trong Spring, `Propagation.NESTED` có thể dựa trên savepoint nếu transaction manager và tài nguyên hỗ trợ. `REQUIRES_NEW` lại dùng một giao dịch độc lập, có thể commit riêng ngay cả khi giao dịch ngoài sau đó rollback. Không coi hai cơ chế này là tương đương hoặc mặc định chúng được hỗ trợ ở mọi cấu hình.

## 9. Commit/rollback không thay thế kiểm soát đồng thời

Một giao dịch thành công không chứng minh rằng kết quả đúng khi hai yêu cầu chạy cùng lúc. Chẳng hạn, hai người đồng thời đọc số dư 100 rồi đều quyết định trừ 80; nếu kiểm tra số dư tách khỏi câu lệnh update, vẫn có nguy cơ ghi đè hoặc vi phạm logic dù từng giao dịch có commit/rollback.

Trong ví dụ Spring, điều kiện `WHERE balance >= ?` được đưa trực tiếp vào lệnh trừ, kết hợp kiểm tra số hàng cập nhật. Đây là một cách giảm rủi ro trừ tiền vượt số dư trong nhiều cơ sở dữ liệu, nhưng ứng dụng vẫn cần hiểu **isolation level, khóa, thứ tự lock, deadlock, retry và ràng buộc dữ liệu** tùy hệ quản trị và mô hình nghiệp vụ.

Một số khái niệm cần phân biệt:

- **Uncommitted changes:** thay đổi đang nằm trong một transaction chưa commit, có thể rollback; khả năng transaction khác nhìn thấy chúng phụ thuộc isolation.
- **Committed changes:** thay đổi đã xác nhận; transaction khác có thể nhìn thấy theo isolation và thời điểm snapshot/read của nó.
- **Flush (JPA):** đồng bộ SQL pending xuống DB trong một giao dịch, **không đồng nghĩa commit**; flush thành công vẫn có thể rollback.
- **Read-only transaction:** trong Spring thường là hint tối ưu/định hướng; không mặc định coi nó là cơ chế bảo vệ cứng chống mọi lệnh ghi ở mọi driver/DB.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Thực thi hai `UPDATE` với auto-commit bật rồi hy vọng `catch` sẽ hoàn tác cả hai | Lệnh đầu có thể đã commit độc lập | Đưa cả hai vào cùng transaction JDBC hoặc service `@Transactional` |
| Chỉ commit ở nhánh thành công, bỏ qua rollback ở nhánh lỗi | Transaction dở dang có thể giữ lock và khiến connection khó tái sử dụng an toàn | Rollback rõ ràng, kể cả khi câu lệnh thất bại; xử lý cả lỗi rollback |
| Gọi `setAutoCommit(true)` để "reset" trong lúc transaction chưa kết thúc | Theo JDBC, thao tác này có thể commit thay đổi đang chờ | Commit/rollback trước, rồi mới trả connection về trạng thái mong muốn |
| Không kiểm tra `executeUpdate()` trả về `0` | Không có exception nhưng mục tiêu nghiệp vụ không được cập nhật | Kiểm tra số hàng bị tác động và báo lỗi nghiệp vụ |
| Tự mở connection ngoài `JdbcTemplate` trong phương thức `@Transactional` | Connection mới có thể không tham gia transaction do Spring quản lý | Dùng DAO/repository cùng transaction manager và nguồn dữ liệu |
| Tự gọi phương thức `@Transactional` trong cùng bean, tưởng sẽ mở giao dịch riêng | Lời gọi có thể bỏ qua proxy interceptor | Đặt ranh giới tại service được gọi qua bean hoặc dùng `TransactionTemplate` |
| Bắt exception, log rồi return thành công | Interceptor có thể commit phần công việc trước đó | Ném lỗi thích hợp, cấu hình rollback hoặc đánh dấu rollback-only |
| Gửi email/call API trước commit rồi giả định rollback DB sẽ thu hồi | Tác dụng phụ ngoài DB đã xảy ra | Cân nhắc outbox, idempotency, retry hoặc quy trình bù ở tầng kiến trúc |
| Giao dịch kéo dài qua I/O mạng và chờ người dùng | Giữ kết nối, lock lâu, tăng tranh chấp | Giữ transaction ngắn, bao quanh những thao tác dữ liệu thật sự cần nguyên tử |

## 11. Quy tắc ra quyết định khi thiết kế một thao tác dữ liệu

Trước khi thêm `@Transactional` hoặc `setAutoCommit(false)`, hãy trả lời những câu hỏi sau:

1. **Một hành động nghiệp vụ bao gồm những thao tác ghi nào?** Nếu một thao tác thất bại, các thao tác ghi trước có cần bị hủy không?
2. **Chúng có cùng tham gia một tài nguyên/transaction manager không?** Nếu không, transaction cục bộ không đủ để bảo đảm atomicity xuyên tài nguyên.
3. **Khi nào kết quả được coi là thành công?** Chỉ commit sau khi hoàn thành toàn bộ kiểm tra và ghi liên quan; đừng dùng sự hiện diện của `try/catch` làm bằng chứng về transaction.
4. **Lỗi nào cần rollback?** Kiểm tra exception mặc định, checked exception, validation và các điều kiện trả về số hàng bằng 0.
5. **Có tác dụng phụ ngoài cơ sở dữ liệu không?** Nếu có, thiết kế riêng cho chúng thay vì gộp vào lời hứa rollback của DB.
6. **Có rủi ro đồng thời hay giao dịch dài không?** Ranh giới nguyên tử đúng vẫn cần isolation/lock phù hợp và thời gian giữ transaction hợp lý.

### Ghi nhớ

- `commit` là **xác nhận**; `rollback` là **hủy phần chưa xác nhận**; cả hai chỉ có ý nghĩa trong **đúng giao dịch**.
- `auto-commit` bật phù hợp với nhiều thao tác đơn lẻ, nhưng không tự bảo đảm nguyên tử cho một chuỗi thao tác nghiệp vụ.
- Với JDBC, các lệnh cần chung transaction phải dùng cùng connection trong phạm vi transaction được quản lý và phải có quyết định kết thúc rõ ràng.
- Với Spring, thường đặt `@Transactional` tại **service chứa toàn bộ đơn vị nghiệp vụ**, để các thao tác dữ liệu tham gia một ranh giới commit/rollback thống nhất.
- Sau commit, muốn đảo ngược nghiệp vụ phải thực hiện thay đổi mới có kiểm soát; rollback không phải nút "undo" xuyên thời gian hay xuyên hệ thống.
