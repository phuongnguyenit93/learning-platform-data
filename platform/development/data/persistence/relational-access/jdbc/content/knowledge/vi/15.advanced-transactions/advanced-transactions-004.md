# Phân biệt savepoint và giao dịch lồng thực sự

Khi một nghiệp vụ JDBC gồm nhiều câu SQL, đôi lúc ta muốn **giữ lại phần đã hoàn thành** nếu một bước phụ thất bại. Ví dụ, ứng dụng tạo một tác vụ mới và thử gắn nhãn; nếu nhãn không đủ hạn mức, tác vụ vẫn phải được tạo, còn thao tác gắn nhãn cần được hoàn tác. JDBC có `Savepoint` để thực hiện rollback từng phần trong **một giao dịch đang hoạt động**.

Tuy nhiên, `Savepoint` không tương đương với một **giao dịch lồng thực sự** (`true nested transaction`), và càng không tương đương với một **giao dịch độc lập** có thể commit bất kể giao dịch cha. Nhầm lẫn ba mô hình này gây ra các lỗi khó thấy: tưởng rằng thao tác con đã được commit, tưởng rằng giao dịch con có mức cô lập riêng hoặc nghĩ rằng rollback bên ngoài không ảnh hưởng dữ liệu bên trong.

Bài học thuộc chương **Giao dịch nâng cao** của module **JDBC**. Nội dung dùng các API chuẩn `DataSource`, `Connection`, `PreparedStatement`, `Savepoint`, `commit()` và `rollback()` để giải thích chính xác phạm vi của từng thao tác.

Sau bài học, bạn có thể:

- Giải thích `Savepoint` chỉ đánh dấu vị trí rollback trong một giao dịch.
- Phân biệt savepoint, giao dịch con phân cấp và giao dịch độc lập.
- Viết mã JDBC rollback đến savepoint nhưng vẫn commit các thay đổi hợp lệ trước đó.
- Hiểu ranh giới trách nhiệm khi nhiều phương thức cùng tham gia một giao dịch.
- Nhận diện các giới hạn về driver, DBMS, auto-commit, isolation, khóa và xử lý lỗi.
- Kiểm thử hành vi commit/rollback trong các tình huống lồng nhau.

## 1. Ôn lại ranh giới giao dịch JDBC

Một giao dịch tập hợp các thao tác cần được xem như một đơn vị nhất quán: hoặc toàn bộ được commit, hoặc các thay đổi chưa commit được rollback. Với JDBC, ranh giới giao dịch thường do một đối tượng `Connection` quản lý:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

void updateTwoRows(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance - ? "
                    + "WHERE id = ?")) {
                ps.setBigDecimal(1,
                        new java.math.BigDecimal("100.00"));
                ps.setLong(2, 10L);
                ps.executeUpdate();
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? "
                    + "WHERE id = ?")) {
                ps.setBigDecimal(1,
                        new java.math.BigDecimal("100.00"));
                ps.setLong(2, 20L);
                ps.executeUpdate();
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
~~~

Đây là minh họa cơ chế transaction; một nghiệp vụ chuyển tiền thực tế còn phải kiểm tra số dòng bị ảnh hưởng, số dư khả dụng, kiểm soát cạnh tranh, định danh chống xử lý lặp và các quy tắc đối soát. Việc giữ toàn bộ thao tác trên **cùng một connection** và gọi `commit` sau khi mọi bước bắt buộc thành công là điểm chính.

Mặc định, nhiều JDBC connection bắt đầu với `autoCommit = true`: mỗi câu lệnh SQL được commit khi hoàn tất theo quy tắc JDBC. Để dùng `Savepoint` trong một giao dịch tự quản, cần chuyển sang `connection.setAutoCommit(false)` trước khi thực hiện các thao tác của giao dịch. Gọi `setAutoCommit` để **đổi chế độ** khi đang ở giữa một giao dịch có thể khiến giao dịch hiện tại được commit theo hợp đồng JDBC; vì vậy không đổi chế độ một cách tùy tiện ở các phương thức con.

## 2. Savepoint thực sự là gì?

`Savepoint` là một **dấu mốc bên trong giao dịch hiện tại**, giúp ứng dụng hủy những thay đổi sau dấu mốc mà vẫn giữ những thay đổi trước đó.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant DB as Giao dịch JDBC T1
    App->>DB: setAutoCommit(false)
    App->>DB: SQL A
    App->>DB: setSavepoint(S1)
    App->>DB: SQL B
    App->>DB: SQL C
    App->>DB: rollback(S1)
    Note over DB: Hoàn tác B, C; A vẫn chưa commit
    App->>DB: SQL D
    App->>DB: commit()
    Note over DB: Commit A và D
~~~

Ví dụ cú pháp chuẩn JDBC:

~~~java
import java.sql.Connection;
import java.sql.Savepoint;

connection.setAutoCommit(false);

// SQL A đã thực thi, chưa commit.
Savepoint checkpoint = connection.setSavepoint("before_optional_step");

// SQL B, C xảy ra sau checkpoint.
connection.rollback(checkpoint); // Hoàn tác phần sau checkpoint.

// SQL D vẫn có thể được thực hiện.
// Chỉ câu này mới kết thúc giao dịch bằng commit:
connection.commit();
~~~

Các nguyên tắc cốt lõi:

1. `setSavepoint()` hoặc `setSavepoint(String name)` tạo mốc rollback **trên chính connection đó**.
2. `rollback(savepoint)` hoàn tác các thay đổi sau mốc, theo ngữ nghĩa DBMS; **không rollback toàn bộ giao dịch**.
3. Những thay đổi trước savepoint vẫn là **thay đổi chưa commit** cho đến khi gọi `commit()`.
4. `releaseSavepoint(savepoint)` giải phóng dấu mốc; **không commit** dữ liệu.
5. `commit()` commit các thay đổi còn lại của toàn bộ giao dịch và làm các savepoint của giao dịch trở nên không còn hiệu lực.
6. `rollback()` không tham số rollback **toàn bộ** giao dịch; những thay đổi trước savepoint cũng bị hủy.
7. Savepoint **không tạo connection mới**, không cung cấp mức isolation riêng và không có quyền commit độc lập.

Các phương thức JDBC tương ứng:

| API | Phạm vi | Kết thúc giao dịch? |
| --- | --- | --- |
| `Connection.setSavepoint()` | Tạo mốc rollback không tên | Không |
| `Connection.setSavepoint("s1")` | Tạo mốc rollback có tên | Không |
| `Connection.rollback(Savepoint s)` | Hoàn tác đến mốc trong giao dịch hiện tại | Không |
| `Connection.releaseSavepoint(Savepoint s)` | Giải phóng mốc (nếu hỗ trợ) | Không |
| `Connection.rollback()` | Hoàn tác toàn bộ giao dịch hiện tại | Có, theo nghĩa kết thúc giao dịch hiện tại |
| `Connection.commit()` | Commit toàn bộ phần thay đổi còn lại | Có |

**Điểm dễ nhầm:** rollback đến savepoint không có nghĩa dữ liệu trước savepoint đã an toàn và bền vững. Nếu sau đó xảy ra lỗi và chương trình gọi `rollback()`, dữ liệu trước savepoint cũng bị mất.

## 3. Giao dịch lồng thực sự: một khái niệm khác

Một **giao dịch lồng thực sự** theo mô hình phân cấp có quan hệ cha–con giữa các giao dịch. Giao dịch con có phạm vi công việc riêng và có thể đưa ra quyết định commit/rollback tại mức con. Nhưng **commit của con thường chỉ là commit tạm vào phạm vi giao dịch cha**: nếu giao dịch cha rollback, kết quả của con không trở thành bền vững.

Đây là đặc điểm phân biệt quan trọng với giao dịch độc lập. Khả năng hiện thực hóa mô hình này phụ thuộc hệ quản trị cơ sở dữ liệu và các lớp transaction manager; **JDBC chuẩn không có API mở trực tiếp một giao dịch con độc lập với `Connection.beginNestedTransaction()`**.

Ba mô hình thường bị đánh đồng:

| Đặc tính | Savepoint trong một giao dịch | Giao dịch lồng phân cấp thật | Giao dịch độc lập / autonomous |
| --- | --- | --- | --- |
| Mục đích | Rollback một đoạn sau mốc | Quản lý các phạm vi giao dịch cha–con | Một giao dịch có vòng đời commit/rollback riêng |
| Bắt đầu phạm vi con | `setSavepoint` | Cơ chế begin child do DBMS/framework cung cấp | Bắt đầu transaction khác, thường qua connection khác |
| Có commit riêng ở mức con? | **Không** | Có thể có bước “commit con” theo mô hình, nhưng còn phụ thuộc commit cha | **Có**, commit độc lập |
| Cha rollback sau khi con “thành công” | Hủy cả thay đổi của con | Thường hủy cả thay đổi con đã commit tạm | Không hủy giao dịch độc lập đã commit |
| Isolation/connection riêng | Không, dùng cùng transaction/connection | Tùy cơ chế DBMS; không mặc định độc lập | Có ranh giới transaction riêng, thường có connection riêng |
| Hỗ trợ trực tiếp trong JDBC chuẩn | `Savepoint` | Không có API tổng quát | Tự quản lý một connection/transaction khác; “autonomous” có thể là tính năng riêng của DBMS |
| Mức độ phụ thuộc DBMS | Driver và `supportsSavepoints()` | Rất cao | Tùy connection pool, kiến trúc và DBMS |

Để thấy sự khác biệt giữa “commit con” và commit độc lập, hãy xét hai chuỗi thao tác:

~~~text
Mô hình nested phân cấp (khái niệm):
BEGIN parent
  A
  BEGIN child
    B
  COMMIT child       -- B được chấp nhận vào phạm vi parent
ROLLBACK parent      -- A và B đều bị hoàn tác

Mô hình giao dịch độc lập:
BEGIN outer (connection 1)
  A
  BEGIN inner (connection 2)
    B
  COMMIT inner       -- B được commit độc lập
ROLLBACK outer       -- A bị hoàn tác; B có thể vẫn tồn tại
~~~

Hai chuỗi trên là **mô hình khái niệm**, không phải cú pháp SQL chung có thể chạy nguyên văn trên mọi hệ quản trị. Ngay cả hệ quản trị hỗ trợ nhiều lệnh `BEGIN TRANSACTION` cũng không nhất thiết cung cấp phân cấp rollback/commit giống mô hình nested thật.

### Savepoint có phải giao dịch con?

Một số tài liệu và framework gọi thao tác tạo savepoint là **nested transaction** theo nghĩa *phạm vi công việc lồng nhau có thể rollback riêng*. Cách gọi đó hữu ích cho điều phối ứng dụng, nhưng về mặt JDBC vật lý:

- Không có transaction ID hoặc connection riêng cho bước bên trong.
- Không có `commit(savepoint)`.
- `releaseSavepoint` không khiến thay đổi bên trong bền vững.
- Rollback bên ngoài có thể xóa cả thay đổi trước và sau mốc.

Vì vậy, khi gặp yêu cầu “giao dịch lồng”, phải hỏi **ngữ nghĩa cần thiết**: chỉ cần rollback một phần, cần phạm vi con có quyết định commit tạm theo mô hình phân cấp, hay cần commit độc lập với giao dịch ngoài?

## 4. Ví dụ thực hành: lưu tác vụ và gắn nhãn tùy chọn

Giả sử ứng dụng có hai yêu cầu:

- **Bắt buộc:** tạo tác vụ mới trong bảng `tasks`.
- **Tùy chọn:** gắn nhãn và trừ một đơn vị hạn mức nhãn. Nếu không còn hạn mức, bỏ phần gắn nhãn nhưng **vẫn lưu tác vụ**.

Nếu nhãn được ghi nhưng không trừ được hạn mức, ta không muốn để lại bản ghi gắn nhãn sai. Đây là trường hợp phù hợp với `Savepoint`: giữ phần tạo tác vụ, hoàn tác **toàn bộ các bước sau savepoint** khi phần tùy chọn không đạt điều kiện.

### 4.1. Schema ví dụ

~~~sql
CREATE TABLE tasks (
    task_id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);

CREATE TABLE label_quotas (
    label VARCHAR(40) PRIMARY KEY,
    remaining INT NOT NULL CHECK (remaining >= 0)
);

CREATE TABLE task_labels (
    task_id BIGINT NOT NULL REFERENCES tasks(task_id),
    label VARCHAR(40) NOT NULL,
    PRIMARY KEY (task_id, label)
);
~~~

Ví dụ dữ liệu hạn mức:

~~~sql
INSERT INTO label_quotas (label, remaining)
VALUES ('urgent', 0), ('routine', 5);
~~~

Cú pháp schema minh họa dùng các kiểu và ràng buộc phổ biến. Hành vi cụ thể khi chạy phải được kiểm thử với hệ quản trị và driver đang sử dụng. `UPDATE` có điều kiện `remaining > 0` giúp thao tác giảm hạn mức kiểm tra điều kiện ngay trong database.

### 4.2. Implementation dùng JDBC chuẩn

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Savepoint;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TaskService {
    private final DataSource dataSource;

    public TaskService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    /**
     * Tạo tác vụ; chỉ gắn nhãn nếu hạn mức còn.
     *
     * @return true nếu nhãn được gắn; false nếu không gắn
     *         (không truyền nhãn hoặc không còn hạn mức).
     */
    public boolean createTask(
            long taskId,
            String title,
            String optionalLabel) throws SQLException {

        Objects.requireNonNull(title, "title");

        // Phương thức sở hữu connection và ranh giới giao dịch.
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                // Bước bắt buộc: chỉ xảy ra một lần.
                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO tasks (task_id, title) VALUES (?, ?)")) {
                    ps.setLong(1, taskId);
                    ps.setString(2, title);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Insert task khong cap nhat mot dong");
                    }
                }

                boolean labelAssigned = false;

                if (optionalLabel != null) {
                    // Mốc đặt SAU thao tác bắt buộc.
                    Savepoint beforeLabel =
                            connection.setSavepoint("before_label");

                    // Bước tùy chọn 1: gắn nhãn.
                    try (PreparedStatement ps = connection.prepareStatement(
                            "INSERT INTO task_labels (task_id, label) "
                            + "VALUES (?, ?)")) {
                        ps.setLong(1, taskId);
                        ps.setString(2, optionalLabel);

                        if (ps.executeUpdate() != 1) {
                            throw new SQLException(
                                    "Insert label khong cap nhat mot dong");
                        }
                    }

                    // Bước tùy chọn 2: trừ hạn mức nếu còn.
                    int quotaRows;
                    try (PreparedStatement ps = connection.prepareStatement(
                            "UPDATE label_quotas "
                            + "SET remaining = remaining - 1 "
                            + "WHERE label = ? AND remaining > 0")) {
                        ps.setString(1, optionalLabel);
                        quotaRows = ps.executeUpdate();
                    }

                    if (quotaRows == 0) {
                        // Nhãn đã gắn bên trên bị hủy.
                        // Tác vụ đã tạo TRƯỚC savepoint vẫn tồn tại
                        // bên trong transaction (chưa commit).
                        connection.rollback(beforeLabel);
                    } else if (quotaRows == 1) {
                        labelAssigned = true;
                    } else {
                        // Hợp đồng quota label là PRIMARY KEY;
                        // > 1 dòng là điều bất thường.
                        throw new SQLException(
                                "Quota cap nhat so dong bat thuong");
                    }

                    // Không cần releaseSavepoint trong ví dụ:
                    // commit bên dưới sẽ kết thúc transaction
                    // và vô hiệu hóa các savepoint của nó.
                }

                connection.commit();
                return labelAssigned;

            } catch (SQLException | RuntimeException failure) {
                // Bất kỳ lỗi bất ngờ nào đều hủy cả tác vụ.
                // Chỉ quotaRows == 0 mới là nhánh nghiệp vụ
                // cho phép rollback từng phần.
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

Đoạn code có một ranh giới giao dịch duy nhất: `TaskService.createTask` mở connection từ `DataSource`, tắt auto-commit và quyết định commit/rollback. Hai câu SQL tùy chọn **dùng cùng connection** nên tham gia cùng giao dịch. `try-with-resources` bảo đảm đóng các `PreparedStatement` và `Connection` khi kết thúc phạm vi.

**Vì sao không bắt mọi `SQLException` của bước nhãn rồi tiếp tục commit?** Vì lỗi kết nối, timeout, vi phạm ràng buộc hoặc lỗi SQL không phân loại có thể làm trạng thái giao dịch không còn phù hợp để tiếp tục. Chỉ trường hợp **`quotaRows == 0`**, là kết quả nghiệp vụ đã được xác định rõ, mới được phép rollback một phần; các lỗi SQL khác được chuyển ra ngoài sau khi cố rollback toàn bộ giao dịch.

Trong thực tế, nếu phân loại một `SQLException` là lỗi tùy chọn có thể phục hồi, ứng dụng phải dựa vào loại lỗi cụ thể của hệ quản trị và rollback đến savepoint trước khi thực hiện SQL tiếp theo. Không nên dùng `catch (SQLException) { /* ignore */ }`.

### 4.3. Đường đi của dữ liệu

Giả sử ban đầu:

- `tasks` chưa có `task_id = 501`.
- `label_quotas` có `('urgent', 0)` và `('routine', 5)`.

Kết quả mong đợi:

| Lời gọi | Điều xảy ra sau savepoint | Sau `commit()` |
| --- | --- | --- |
| `createTask(501, "Review PR", "urgent")` | Chèn nhãn rồi `UPDATE` trả 0; rollback đến savepoint | Tác vụ 501 tồn tại, không có nhãn `urgent`, trả `false` |
| `createTask(502, "Clean build", "routine")` | Chèn nhãn, trừ hạn mức từ 5 xuống 4 | Tác vụ 502 và nhãn `routine` cùng tồn tại, trả `true` |
| `createTask(503, "Plan sprint", null)` | Bỏ qua toàn bộ bước nhãn | Tác vụ 503 tồn tại, trả `false` |
| Tạo tác vụ bị trùng `task_id` | `INSERT tasks` ném lỗi ràng buộc | Rollback toàn bộ; không commit |
| Chèn nhãn bị lỗi SQL không được phân loại | Ném `SQLException` | Thử rollback toàn bộ; không cam kết lưu tác vụ |

Không nên kiểm tra kết quả chỉ bằng giá trị trả về `true/false`. Bài kiểm thử tích hợp cần **đọc lại cả ba bảng** để bảo đảm số dư hạn mức và liên kết nhãn nhất quán.

### 4.4. Những giới hạn cần hiểu từ ví dụ

- Việc commit **toàn bộ transaction** chỉ diễn ra một lần ở cuối. Nhánh rollback tới savepoint không tự commit tác vụ.
- Nếu `connection.commit()` thất bại, trạng thái commit cuối cùng có thể không xác định; gọi `rollback()` theo nỗ lực tốt nhất **không chứng minh** giao dịch chưa được commit. Cần cơ chế kiểm tra/idempotency theo nghiệp vụ trước khi retry.
- Nếu `connection.rollback()` thất bại, trạng thái connection không đáng tin; phải để tầng quản lý connection xử lý, tránh gọi `setAutoCommit(true)` khi transaction còn bất định vì thao tác đổi chế độ có thể commit.
- Vì phương thức **sở hữu connection** từ đầu đến cuối, nó không cố khôi phục auto-commit trên một connection của người gọi. Nếu dùng connection pool, phải cấu hình và kiểm thử cơ chế reset trạng thái khi connection được trả về pool.
- Nhiều hệ quản trị thực thi `UPDATE` có điều kiện bằng cơ chế khóa; kết quả thực tế dưới tải đồng thời phụ thuộc isolation và DBMS. Kiểm thử cạnh tranh cần nằm trong kế hoạch kiểm thử tích hợp.

## 5. Khi phương thức bên trong muốn “mở giao dịch riêng”

Một sai lầm phổ biến là mỗi phương thức repository tự gọi `setAutoCommit(false)` rồi `commit()`, dù đang được gọi bên trong một nghiệp vụ lớn. Xét luồng:

~~~text
OrderService.placeOrder()
  ├─ OrderRepository.insert()
  ├─ InventoryRepository.reserve()
  └─ AuditRepository.write()
~~~

Nếu mỗi repository mở một connection khác và commit riêng, các phần thay đổi không còn được bảo đảm nguyên tử với nhau. Nếu các phương thức **dùng chung một connection** nhưng một phương thức con tự commit, nó có thể kết thúc cả transaction của caller trước thời điểm mong muốn.

Một cách chia trách nhiệm rõ ràng:

~~~java
// Tầng service sở hữu transaction.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        orderRepository.insert(connection, order);
        inventoryRepository.reserve(connection, order);
        auditRepository.write(connection, order);

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
~~~

Trong ví dụ trên, các hàm repository nhận `Connection` đã có và **không** gọi `commit()`, `rollback()`, `setAutoCommit()` hay `close()`. Chúng chỉ chuẩn bị/thực thi câu SQL, đóng statement/result set thuộc quyền sở hữu của mình. Nếu một thao tác phụ cần rollback độc lập, **tầng đang sở hữu transaction** tạo savepoint, quyết định xử lý ngoại lệ và rollback tới mốc.

Có thể đóng gói quy tắc này vào một transaction manager nội bộ, nhưng hợp đồng phải minh bạch: phương thức con có đang tham gia transaction hiện tại hay đang tạo một transaction vật lý khác? Chỉ dùng tên phương thức `runNested` không đủ để biết hành vi.

## 6. So sánh với giao dịch độc lập trên connection khác

Giả sử nghiệp vụ cần ghi một sự kiện vận hành ngay cả khi giao dịch chính thất bại. Một cách tiếp cận là tạo transaction khác bằng một connection riêng:

~~~java
// Minh họa ý tưởng; các method này phải tự quản lý
// connection, commit, rollback và lỗi.
mainTransactionConnection.setAutoCommit(false);
try {
    // ... thao tác chính, chưa commit

    auditService.writeUsingSeparateConnection(auditEvent);
    // Audit có thể đã commit ở connection thứ hai.

    mainTransactionConnection.rollback();
    // Rollback ở đây không tự hủy audit đã commit.
} finally {
    // Dọn dẹp giao dịch chính theo hợp đồng của caller.
}
~~~

**Đoạn trên chỉ mô tả quan hệ giữa hai connection**, không phải mẫu code hoàn chỉnh để chép vào production. Việc tạo và commit audit transaction cũng phải xử lý ngoại lệ, rollback và đóng connection riêng. Đặc biệt không nên cho audit transaction dựa vào một dòng chưa commit của transaction chính: nó có thể không nhìn thấy dòng đó hoặc có thể bị chặn do khóa.

Nếu một framework cung cấp chế độ như `REQUIRES_NEW`, nó thường đình chỉ phạm vi transaction đang chạy và mở transaction vật lý mới; cơ chế cụ thể phụ thuộc transaction manager và nguồn dữ liệu. Ngược lại, một chế độ tên `NESTED` trong một số transaction manager JDBC thường được hiện thực bằng **savepoint trên cùng transaction**. Do đó:

- `NESTED` không có nghĩa “commit con bền vững dù cha rollback”.
- `REQUIRES_NEW` không bảo đảm tính nguyên tử giữa hai giao dịch.
- Tách connection có thể làm tăng nhu cầu pool, phát sinh chờ khóa và vấn đề isolation.
- Nếu cần nguyên tử giữa nhiều nguồn dữ liệu, phải xem xét cơ chế giao dịch phân tán hoặc thiết kế ứng dụng như outbox/saga theo mục tiêu; savepoint không giải quyết vấn đề đó.

Đừng dùng giao dịch độc lập chỉ để “cứu” một câu SQL tùy chọn bên trong cùng nghiệp vụ khi thực sự cần rollback cùng cha. Trong trường hợp đó, savepoint là cơ chế phù hợp hơn.

## 7. Mô hình thực tế ở một số hệ quản trị

Các hệ quản trị SQL không cung cấp cùng một ngữ nghĩa cho “nested transaction”. Kiểm tra cơ chế cụ thể trước khi viết code dựa vào tên tính năng.

| Hệ quản trị / mô hình | Điều cần nhớ |
| --- | --- |
| **PostgreSQL** | Hỗ trợ `SAVEPOINT`, `ROLLBACK TO SAVEPOINT` và `RELEASE SAVEPOINT`. `BEGIN` bên trong transaction hiện có không mở một transaction vật lý lồng độc lập. Khi câu lệnh SQL gây lỗi, transaction có thể ở trạng thái aborted; rollback đến savepoint được tạo **trước lỗi** là cách phục hồi phù hợp. |
| **MySQL (InnoDB)** | Hỗ trợ savepoint trong transaction; bắt đầu transaction mới khi đã có transaction có thể kết thúc/commit transaction hiện tại theo cơ chế SQL của MySQL. Một số DDL gây implicit commit, làm mất ý nghĩa của savepoint cho kịch bản đó. |
| **SQL Server** | Cho phép nhiều `BEGIN TRANSACTION` và theo dõi số mức bằng `@@TRANCOUNT`, nhưng `COMMIT` mức trong không làm thay đổi bền vững độc lập; `ROLLBACK TRANSACTION` không chỉ tên savepoint có thể rollback toàn bộ. `SAVE TRANSACTION` dùng cho rollback từng phần. |
| **Oracle Database** | Có savepoint; cơ chế `AUTONOMOUS_TRANSACTION` là một transaction độc lập theo đặc tính riêng của Oracle, **không** phải JDBC savepoint hoặc nested commit phụ thuộc cha. |

Bảng này chỉ cung cấp định hướng. Chi tiết của DDL, mức hỗ trợ savepoint, rollback sau lỗi, khóa và độ chính xác của SQLState còn tùy phiên bản DBMS, storage engine, driver và cấu hình. Nếu đổi cơ sở dữ liệu, đừng giả định toàn bộ logic phục hồi lỗi vẫn tương thích.

### Kiểm tra khả năng hỗ trợ trước khi phụ thuộc vào savepoint

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import javax.sql.DataSource;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    if (!metadata.supportsSavepoints()) {
        throw new UnsupportedOperationException(
                "JDBC driver khong ho tro savepoint");
    }
}
~~~

`supportsSavepoints()` là bước kiểm tra khả năng do driver công bố, không thay thế kiểm thử tích hợp. Có những hạn chế bổ sung về statement, bảng, DDL hoặc engine mà metadata không mô tả đầy đủ. Một số driver/DBMS có thể không hỗ trợ `releaseSavepoint` như kỳ vọng; nếu chỉ cần rollback từng phần, việc để `commit` hoặc `rollback` toàn bộ kết thúc transaction thường là đủ để vô hiệu hóa mốc.

## 8. Các tình huống dễ hiểu sai

### 8.1. Nhầm `releaseSavepoint` với `commit`

~~~java
connection.setAutoCommit(false);

Savepoint sp = connection.setSavepoint();
insertRow(connection);

connection.releaseSavepoint(sp);

// Lệnh này vẫn có thể hoàn tác insertRow:
connection.rollback();
~~~

`releaseSavepoint` chỉ làm mốc không còn sử dụng được. Nó không thay đổi tình trạng chưa commit của `insertRow`.

### 8.2. Tạo savepoint khi auto-commit đang bật

~~~java
// Sai về ý định dùng savepoint trong transaction tự quản:
connection.setAutoCommit(true);
Savepoint sp = connection.setSavepoint(); // Có thể ném SQLException.
~~~

JDBC không cho phép tạo savepoint trong chế độ auto-commit như một giao dịch do ứng dụng tự quản. Hãy thiết lập `autoCommit(false)` **trước** các thao tác cần cùng transaction; tránh chuyển chế độ trong lúc một nghiệp vụ chưa kết thúc.

### 8.3. Dùng một connection để tạo giao dịch vật lý độc lập

~~~text
Connection C:
  BEGIN / setAutoCommit(false)
  SQL A
  SAVEPOINT S
  SQL B
  RELEASE S
  COMMIT
~~~

Tất cả vẫn thuộc **một transaction vật lý**. Không thể biến `S` thành transaction độc lập chỉ bằng một tên khác. Nếu cần một commit độc lập, cần cấu trúc transaction khác và phải chấp nhận hệ quả về atomicity/isolation.

### 8.4. Lầm tưởng rollback tới savepoint luôn giải phóng mọi khóa

Các hệ quản trị có cách quản lý khóa và tài nguyên sau rollback savepoint khác nhau. Một số khóa lấy sau savepoint có thể được giải phóng, nhưng không có cam kết chung rằng mọi khóa/tài nguyên đều được thả ngay hoặc transaction không còn chặn phiên khác. Kiểm thử blocking/deadlock với DBMS thực tế; transaction vẫn mở cho tới khi commit/rollback toàn bộ.

### 8.5. Giữ đối tượng `Savepoint` quá lâu

Một `Savepoint` chỉ có ý nghĩa trong transaction/connection đã tạo ra nó. Sau `commit()`, `rollback()` toàn bộ hoặc khi savepoint bị vô hiệu, gọi `rollback(sp)` thường gây `SQLException`. Rollback về một mốc trước đó có thể vô hiệu các mốc được tạo sau mốc đó. Không lưu `Savepoint` vào cache, field dùng chung hay chuyển sang thread khác để xử lý muộn.

### 8.6. Tin rằng savepoint có thể hoàn tác mọi tác động bên ngoài

Savepoint chỉ điều khiển các tác động **được DBMS quản lý trong transaction hỗ trợ**. Nó không hoàn tác email đã gửi, HTTP request đã gọi, thông điệp đã được consumer xử lý, file đã ghi ra ngoài hoặc thao tác trong transaction độc lập khác. Kể cả trong database, một số loại DDL, sequence và thao tác chuyên biệt có thể không được rollback như DML thông thường.

Để kết hợp database với hệ thống bên ngoài, cần chiến lược thích hợp như transactional outbox, hàng đợi có cơ chế idempotency hoặc bù trừ. Không đặt hành động bên ngoài giữa hai savepoint rồi giả định `rollback(sp)` sẽ quay ngược thế giới bên ngoài.

### 8.7. Nuốt lỗi và commit khi transaction không còn hợp lệ

~~~java
try {
    optionalSql(connection);
} catch (SQLException ignored) {
    // Nguy hiểm: transaction có thể không thể chạy tiếp.
}
connection.commit();
~~~

Thay vào đó, cần biết **lỗi nào** được phép phục hồi, savepoint nào vẫn hợp lệ và DBMS yêu cầu rollback tới mốc trước lỗi hay không. Nếu không chắc chắn, rollback toàn bộ và trả lỗi lên tầng gọi. Với PostgreSQL, tiếp tục thực thi SQL trong transaction bị đánh dấu aborted sau lỗi mà chưa rollback tới savepoint có thể khiến các lệnh sau cũng thất bại.

### 8.8. Trộn giao dịch của caller với giao dịch của callee

Một method được truyền `Connection` dùng chung không nên âm thầm `commit`, `rollback` toàn bộ hoặc `close` connection đó. Điều này phá ranh giới transaction của tầng gọi. Nếu cần một phần tùy chọn, caller tạo savepoint; nếu thực sự cần transaction riêng, một lớp khác phải chịu trách nhiệm mở connection và quản lý nhất quán.

## 9. Thiết kế chiến lược lỗi và kiểm thử

Khi dùng savepoint, trước tiên hãy xác định lỗi nào được phép **giữ giao dịch ngoài**:

| Kịch bản | Phương án thường hợp lý | Vì sao |
| --- | --- | --- |
| Bước tùy chọn bị từ chối theo quy tắc đã biết | `rollback(savepoint)`, tiếp tục và `commit` phần hợp lệ | Phần còn lại của nghiệp vụ vẫn nhất quán |
| Một bước bắt buộc lỗi | `rollback()` toàn bộ | Không cho phép kết quả thiếu bước bắt buộc |
| SQL của bước tùy chọn lỗi nhưng chưa phân loại được | `rollback()` toàn bộ, báo lỗi | Trạng thái có thể không an toàn để tiếp tục |
| Lỗi DB đã được phân loại và driver cho phép phục hồi qua savepoint | `rollback(savepoint)` rồi tiếp tục theo chính sách | Hoàn tác câu SQL lỗi và phần sau mốc trước khi tiếp tục |
| Mất kết nối hoặc commit không rõ thành công | Đánh dấu kết quả bất định, kiểm tra lại trạng thái | Retry mù có thể ghi trùng |
| Cần ghi audit tồn tại ngay cả khi giao dịch chính rollback | Transaction độc lập, outbox hoặc mô hình phù hợp | Savepoint không cung cấp commit độc lập |

### Bộ kiểm thử tích hợp gợi ý

1. **Không có savepoint:** một lỗi ở bước bắt buộc khiến toàn bộ DML bị rollback.
2. **Rollback một phần:** chèn A, đặt `S1`, chèn B, rollback `S1`, chèn C, commit; chỉ A và C tồn tại.
3. **Rollback toàn bộ sau rollback một phần:** chèn A, đặt `S1`, chèn B, rollback `S1`, rollback toàn bộ; không còn A hoặc B.
4. **Nhiều savepoint:** đặt `S1` rồi `S2`, rollback `S1`; xác minh kết quả DML và việc `S2` không thể dùng theo DBMS.
5. **Release không commit:** đặt `S1`, chèn B, release `S1`, rollback toàn bộ; B vẫn bị hoàn tác.
6. **Transaction khác không nhìn thấy dữ liệu chưa commit:** dùng hai connection với isolation thích hợp, kiểm tra visibility trước và sau `commit` (kết quả phụ thuộc mức isolation).
7. **Mô phỏng SQL error:** gây lỗi trong bước tùy chọn sau savepoint, kiểm tra khả năng `rollback(sp)` và tiếp tục với DBMS cụ thể.
8. **Connection pooling:** trả connection sau commit/rollback, mượn lại, xác minh auto-commit/isolation đã được reset theo cấu hình pool.
9. **Concurrency:** hai request cùng cập nhật hạn mức, xác minh không trừ xuống âm và không tạo nhãn không được cấp quota.
10. **Commit uncertainty:** mô phỏng mất kết nối lúc commit (nếu công cụ kiểm thử cho phép), xác minh cơ chế kiểm tra/idempotency thay vì tự động chèn lại vô điều kiện.

Một số kiểm thử nên dùng **cơ sở dữ liệu thực cùng driver production**, vì bộ nhớ giả hoặc mock `Connection` khó mô phỏng trạng thái transaction aborted, implicit commit do DDL, deadlock và hành vi khóa.

## 10. Bài tập tình huống

### Tình huống 1: Rollback chỉ bước tùy chọn

Có transaction T thực hiện:

~~~text
BEGIN T
  INSERT order A
  SAVEPOINT S
  INSERT optional_tag B
  ROLLBACK TO S
  INSERT order_line C
COMMIT T
~~~

**Hỏi:** Sau commit, A, B, C tồn tại hay không?

**Gợi ý:** A và C được commit; B bị hoàn tác. A không được commit tại thời điểm rollback đến S; A chỉ được commit cuối transaction.

### Tình huống 2: Parent rollback sau “commit con”

Một framework cho phép bạn chạy công việc con bằng savepoint, nhưng team gọi thành công của công việc con là “commit child”. Sau đó caller rollback transaction ngoài.

**Hỏi:** Dữ liệu do công việc con ghi có còn trong DB không?

**Gợi ý:** Không, nếu tất cả cùng transaction JDBC và chỉ dùng savepoint. Chỉ commit của transaction ngoài mới làm thay đổi đó bền vững.

### Tình huống 3: Audit bắt buộc tồn tại sau rollback

Hệ thống muốn ghi một bản ghi audit về một lần thanh toán thất bại, ngay cả khi transaction cập nhật số dư rollback.

**Hỏi:** Vì sao savepoint không đáp ứng? Bạn cần quyết định gì khi tách audit sang connection khác?

**Gợi ý:** Savepoint không commit độc lập; cần transaction độc lập hoặc kiến trúc ghi sự kiện phù hợp. Phải xét visibility, khóa, độ tin cậy khi audit lỗi, idempotency và tính nhất quán giữa các hệ thống.

### Tình huống 4: SQL lỗi sau savepoint

~~~text
BEGIN
  INSERT task
  SAVEPOINT S
  INSERT task_label -- bị lỗi constraint
  UPDATE label_quotas ...
  COMMIT
~~~

**Hỏi:** Có nên chỉ bắt ngoại lệ rồi tiếp tục chạy `UPDATE` không?

**Gợi ý:** Không. Cần phân loại lỗi và rollback đến savepoint nếu đây là lỗi cho phép phục hồi. Trên PostgreSQL, sau lỗi SQL transaction cần rollback về savepoint hợp lệ trước khi tiếp tục; lỗi không phân loại nên rollback toàn bộ.

### Tình huống 5: Sắp xếp trách nhiệm giữa các repository

Một `PaymentService` gọi `DebitRepository` và `CreditRepository`. Hai repository cùng nhận `Connection` từ service nhưng mỗi repository đều gọi `commit()` khi hoàn thành.

**Hỏi:** Rủi ro là gì và nên sửa hợp đồng như thế nào?

**Gợi ý:** `commit()` trong repository có thể commit cả transaction của service trước khi công việc còn lại hoàn tất. Service nên sở hữu ranh giới giao dịch; repository chỉ thao tác trên connection được truyền vào và không đóng/commit nó.

---

### Checklist ngắn trước khi áp dụng vào hệ thống

- [ ] Tôi đã xác định rõ phần nghiệp vụ **bắt buộc** và phần có thể rollback riêng.
- [ ] Mọi câu SQL cần cùng giao dịch đều dùng **một connection**.
- [ ] `setAutoCommit(false)` được gọi trước khi thực hiện giao dịch.
- [ ] Savepoint được tạo **trước phần tùy chọn cần hoàn tác**.
- [ ] Tôi biết chính xác lỗi nào được rollback từng phần, lỗi nào phải rollback toàn bộ.
- [ ] Tôi không coi `releaseSavepoint` hay “commit con” dựa trên savepoint là commit bền vững.
- [ ] Tôi đã kiểm tra `supportsSavepoints()` và kiểm thử trên đúng DBMS/driver.
- [ ] Tôi đã xét tác động của DDL, khóa, isolation, lỗi rollback và kết quả commit không chắc chắn.
- [ ] Nếu cần transaction độc lập, tôi đã thiết kế rõ ranh giới connection và hậu quả khi cha rollback.

**Nguyên tắc ghi nhớ:** `Savepoint` là công cụ *rollback từng phần của một transaction JDBC*. Giao dịch lồng thực sự là mô hình *cha–con* với ngữ nghĩa do hệ quản trị hiện thực; “commit con” trong mô hình phân cấp vẫn có thể bị rollback bởi cha. Giao dịch độc lập là một transaction vật lý khác với ranh giới commit riêng. Chọn cơ chế theo yêu cầu nghiệp vụ về **phục hồi lỗi, tính nguyên tử và độ bền dữ liệu**, không chỉ theo tên gọi “nested”.
