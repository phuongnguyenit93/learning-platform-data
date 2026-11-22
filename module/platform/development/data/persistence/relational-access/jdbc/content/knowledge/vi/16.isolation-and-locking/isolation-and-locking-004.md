# Phân biệt tên mức cô lập và hành vi thực tế của hệ quản trị trong JDBC

Khi lập trình **JDBC**, ta có thể gọi `Connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ)` và dễ nghĩ rằng mọi cơ sở dữ liệu sẽ bảo đảm chính xác cùng một kiểu đọc, cùng một loại khóa và cùng một kết quả khi hai giao dịch chạy đồng thời. Trên thực tế, **tên mức cô lập là một hợp đồng ở cấp khái niệm; cơ chế triển khai và hành vi quan sát được còn phụ thuộc hệ quản trị, phiên bản, cấu hình, kiểu câu SQL và JDBC driver**.

Bài học thuộc chương **Cô lập và khóa**, giúp đọc đúng ý nghĩa các mức cô lập JDBC, phân biệt ba hiện tượng đọc phổ biến với các bất thường ghi dữ liệu, tìm hiểu khác biệt giữa cơ chế khóa và *multiversion concurrency control* (MVCC), sau đó kiểm chứng bằng hai `Connection` độc lập. Các ví dụ dùng `DataSource`, `PreparedStatement`, `ResultSet` và các API chuẩn để hỗ trợ lựa chọn mức cô lập cho thao tác CRUD, transaction và xử lý lỗi.

## 1. Mức cô lập là gì và vì sao tên gọi chưa đủ?

Một transaction gồm một hay nhiều câu lệnh SQL cần được xử lý như một đơn vị công việc. **Isolation** trả lời câu hỏi: khi có những transaction khác cùng chạy, transaction hiện tại được phép nhìn thấy thay đổi nào và kết quả của các thao tác đồng thời có thể khác nhau đến đâu?

Ba lớp cần phân biệt:

1. **Tên và mô hình chuẩn:** các mức `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` gắn với những hiện tượng đọc được phép hoặc bị ngăn theo mô tả truyền thống của chuẩn SQL.
2. **Hành vi triển khai của hệ quản trị:** PostgreSQL, MySQL/InnoDB, SQL Server, Oracle có thể dùng khóa, MVCC, snapshot, khóa khoảng hoặc phát hiện xung đột; một số mức được nâng lên mức mạnh hơn, không hỗ trợ hoặc có ngữ nghĩa riêng.
3. **Môi trường và câu lệnh thực tế:** cấu hình phiên/cơ sở dữ liệu, `SELECT` thông thường hay `SELECT ... FOR UPDATE`, chỉ mục, thứ tự truy vấn, thao tác ghi và transaction khác đều ảnh hưởng điều người học quan sát.

Ví dụ hai hệ quản trị cùng báo `REPEATABLE READ` có thể khác nhau: một hệ thống giữ khóa đọc cho đến hết transaction, một hệ thống cho đọc lại cùng snapshot. Cả hai đều có thể tránh đọc lại hai giá trị khác nhau của cùng bản ghi, nhưng khác biệt về **blocking**, lỗi xung đột và sự xuất hiện của hàng mới trong truy vấn theo điều kiện.

> Đừng suy từ tên isolation rằng một `SELECT` cụ thể luôn khóa dòng, luôn không chặn writer, hay bảo đảm mọi quy tắc nghiệp vụ. Phải xác định hệ quản trị, phiên bản và kiểu truy vấn đang dùng.

## 2. Năm hiện tượng cần phân biệt trước khi chọn isolation

Giả sử có bảng:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL
);

INSERT INTO accounts (id, balance) VALUES (1, 100.00);
```

Hai transaction `T1` và `T2` đang chạy trên **hai kết nối riêng**. Những kịch bản sau minh họa các bất thường có thể xảy ra tùy mức cô lập và cơ sở dữ liệu.

### 2.1. Dirty read — đọc dữ liệu chưa commit

```text
T2: BEGIN
T2: UPDATE accounts SET balance = 40 WHERE id = 1
    (chưa COMMIT)

T1: SELECT balance FROM accounts WHERE id = 1
    → thấy 40 nếu dirty read được cho phép

T2: ROLLBACK
    → số dư đã commit vẫn là 100
```

`T1` đã đọc giá trị của một thay đổi **chưa commit** và sau đó bị hủy. Mức `READ UNCOMMITTED` theo mô hình truyền thống có thể cho phép trường hợp này; một số hệ quản trị dùng cơ chế mạnh hơn ngay cả khi được yêu cầu `READ UNCOMMITTED`.

### 2.2. Non-repeatable read — đọc lại một hàng ra kết quả khác

```text
T1: BEGIN
T1: SELECT balance ... WHERE id = 1   → 100

T2: BEGIN
T2: UPDATE accounts SET balance = 80 WHERE id = 1
T2: COMMIT

T1: SELECT balance ... WHERE id = 1   → có thể là 80
T1: COMMIT
```

Hai lần đọc của `T1` nhắm đến **cùng một bản ghi**, nhưng trả giá trị khác nhau. `READ COMMITTED` thường không ngăn hiện tượng này; `REPEATABLE READ` cần đáp ứng yêu cầu tránh non-repeatable read theo định nghĩa chuẩn, dù cách đạt được có thể khác nhau.

### 2.3. Phantom read — tập hàng thỏa điều kiện thay đổi

```sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';
```

Nếu `T1` chạy câu trên được `5` hàng, còn `T2` chèn một đơn hàng `PENDING` rồi commit, lần đọc lại của `T1` có thể được `6`. Đây là **phantom**: sự thay đổi tập hàng đáp ứng **một điều kiện truy vấn**, không nhất thiết là sửa lại giá trị của một hàng vốn đã được đọc.

Theo bảng hiện tượng SQL thường được dạy, `REPEATABLE READ` không bắt buộc ngăn phantom; `SERIALIZABLE` phải ngăn lịch thực thi không thể quy về một thứ tự transaction nối tiếp. Tuy nhiên, một triển khai `REPEATABLE READ` bằng snapshot có thể **không cho thấy phantom trong các lần đọc thông thường**.

### 2.4. Lost update — một lần cập nhật ghi đè lần cập nhật khác

```text
Số dư ban đầu: 100

T1: SELECT balance → 100
T2: SELECT balance → 100
T1: tính 100 - 10 = 90
T2: tính 100 + 20 = 120
T1: UPDATE accounts SET balance = 90 WHERE id = 1
T1: COMMIT
T2: UPDATE accounts SET balance = 120 WHERE id = 1
T2: COMMIT (nếu DB cho phép)

Kết quả cuối: 120; phép trừ 10 đã bị ghi đè.
```

Đây là vấn đề **đọc–sửa–ghi**. Tùy cơ chế cập nhật và mức cô lập, hệ quản trị có thể chặn, phát hiện xung đột và hủy một transaction, hoặc cho phép ghi đè. Ba hiện tượng đọc kinh điển không mô tả đầy đủ vấn đề này.

Với phép cộng/trừ trực tiếp lên một hàng, dùng phép cập nhật nguyên tử:

```sql
UPDATE accounts
SET balance = balance - ?
WHERE id = ? AND balance >= ?;
```

Kết hợp `executeUpdate()` để xác nhận đúng số hàng cập nhật; nếu thao tác phụ thuộc vào nhiều hàng hoặc nhiều bảng, vẫn cần lựa chọn transaction, khóa, ràng buộc hoặc kiểm tra phiên bản thích hợp.

### 2.5. Write skew — hai transaction sửa hai hàng khác nhau

Giả sử mỗi ca trực **phải có ít nhất một bác sĩ đang trực**. Hai bác sĩ An và Bình đều đang trực:

```text
T1: đọc thấy An=true, Bình=true → quyết định cho An nghỉ
T2: đọc thấy An=true, Bình=true → quyết định cho Bình nghỉ

T1: UPDATE doctors SET on_call = false WHERE id = An
T2: UPDATE doctors SET on_call = false WHERE id = Bình

Nếu cả hai COMMIT: không còn bác sĩ trực
```

Hai transaction cập nhật **hai dòng khác nhau**, nên việc chỉ phát hiện xung đột ghi lên *cùng một dòng* chưa đủ. Một số triển khai snapshot isolation vẫn cho phép lịch chạy kiểu này. Đây là ví dụ quan trọng cho thấy **lặp lại cùng snapshot không đồng nghĩa với khả năng thực thi tuần tự đầy đủ**. Cần xác minh `SERIALIZABLE` của hệ quản trị, dùng khóa/phạm vi bảo vệ quy tắc nghiệp vụ phù hợp hoặc ràng buộc có thể thực thi tại cơ sở dữ liệu.

## 3. Bảng mức cô lập JDBC và những điều bảng này không nói

JDBC định nghĩa các hằng trong `java.sql.Connection`:

| Hằng JDBC | Tên SQL | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `TRANSACTION_READ_COMMITTED` | `READ COMMITTED` | Ngăn | Có thể | Có thể |
| `TRANSACTION_REPEATABLE_READ` | `REPEATABLE READ` | Ngăn | Ngăn | Có thể theo mô hình chuẩn truyền thống |
| `TRANSACTION_SERIALIZABLE` | `SERIALIZABLE` | Ngăn | Ngăn | Ngăn |

**“Có thể” là được phép xảy ra, không có nghĩa chắc chắn sẽ quan sát được**. Bảng mô tả các bảo đảm tối thiểu trên những hiện tượng đọc kinh điển, chứ không phải danh sách chính xác mọi bất thường, loại khóa hay lỗi mà mỗi sản phẩm cơ sở dữ liệu trả về. Đặc biệt:

- `REPEATABLE READ` không có một cơ chế triển khai thống nhất trên mọi hệ quản trị. Phép đọc thông thường có thể dùng snapshot, còn phép đọc có khóa dùng quy tắc khác.
- Bảng không đủ để suy ra việc **lost update** hoặc **write skew** có bị phát hiện hay không.
- `SERIALIZABLE` theo nghĩa lý thuyết đòi hỏi kết quả tương đương một lịch chạy các transaction lần lượt; cách đạt được có thể là khóa, kiểm tra xung đột hoặc hủy và yêu cầu thử lại. Tên `SERIALIZABLE` được nhà cung cấp gắn cho một mức cần được đối chiếu với tài liệu và hành vi thực tế.
- `Connection.TRANSACTION_NONE` biểu thị trường hợp không hỗ trợ transaction, **không phải một mức cô lập thứ năm** để chọn cho giao dịch.

Ngay cả khi một mức bảo đảm “đọc lặp lại”, nó không bảo đảm transaction khác không phải chờ, không bị deadlock, hoặc mọi thao tác kinh doanh sẽ tự động đúng. **Isolation** chỉ là một phần của tính đúng đắn, cùng với tính nguyên tử, ràng buộc dữ liệu, thiết kế SQL và xử lý lỗi.

## 4. Khóa và MVCC có thể tạo hành vi khác nhau dưới cùng tên

### 4.1. Cơ chế dựa trên khóa

Hệ quản trị có thể dùng **shared/read lock** và **exclusive/write lock** để điều phối truy cập. Trong một cấu hình `REPEATABLE READ` theo kiểu khóa, các hàng đã đọc có thể giữ khóa đọc đến cuối transaction, làm writer muốn sửa chúng phải chờ. Nhưng nếu hệ thống không khóa **khoảng giá trị** của điều kiện truy vấn, một transaction khác vẫn có thể chèn hàng mới làm xuất hiện phantom.

Khóa khoảng (*range lock*, *gap lock*, *next-key lock*) hoặc những biện pháp đồng bộ tương đương có thể cần thiết để bảo vệ điều kiện như “không có booking nào trùng khoảng thời gian”. Các kỹ thuật khóa cụ thể phụ thuộc hệ quản trị, chỉ mục, câu SQL và chế độ transaction.

### 4.2. MVCC và snapshot

Với *multiversion concurrency control* (MVCC), cơ sở dữ liệu duy trì các phiên bản hàng để reader có thể đọc một **phiên bản nhất quán** thay vì luôn chờ writer. Tuy nhiên cần hỏi:

- Snapshot được chốt ở **đầu câu lệnh** hay **trong phạm vi transaction**?
- Các truy vấn `SELECT` có khóa, câu `UPDATE` và câu `DELETE` có dùng cùng góc nhìn với `SELECT` thông thường không?
- Khi hai transaction ghi cạnh tranh, hệ thống bắt một bên chờ, cập nhật trên phiên bản mới, hay báo lỗi xung đột?
- Với bất biến liên quan **nhiều hàng**, hệ thống có phát hiện các phụ thuộc đọc–ghi tạo write skew không?

Hai hệ thống cùng dùng MVCC không nhất thiết trả lời các câu hỏi trên giống nhau.

### 4.3. Snapshot isolation không tự động bằng serializability

Ở snapshot isolation, các lần đọc của một transaction thường thấy một ảnh chụp nhất quán. Nếu hai transaction cùng thay đổi **cùng hàng**, có thể có quy tắc phát hiện xung đột ghi. Nhưng ví dụ hai bác sĩ trực ở phần 2.5 thay đổi **hai hàng khác nhau**: cả hai có thể quyết định dựa trên một snapshot hợp lệ riêng và cuối cùng vi phạm bất biến.

Một cơ chế `SERIALIZABLE` thực sự có thể phát hiện lịch này và buộc ít nhất một transaction bị hủy/thử lại. Vì vậy, kết quả “không thấy phantom trong một vài lần `SELECT`” là **bằng chứng quá yếu** để kết luận cơ sở dữ liệu đang bảo đảm serializability.

## 5. Một số khác biệt tiêu biểu giữa các hệ quản trị

Đây là **ví dụ định hướng** về các triển khai thông dụng, không phải cam kết bất biến cho mọi phiên bản, chế độ và driver. Khi triển khai, phải xác minh tài liệu của **phiên bản thực tế**.

| Hệ quản trị / cơ chế | Hành vi đáng chú ý khi so với tên mức cô lập |
| --- | --- |
| **PostgreSQL** | `READ UNCOMMITTED` được xử lý như `READ COMMITTED`. `READ COMMITTED` có snapshot theo câu lệnh; `REPEATABLE READ` dùng snapshot transaction, tránh phantom trong đọc thông thường nhưng vẫn có thể gặp những bất thường không tuần tự hóa như write skew. `SERIALIZABLE` dùng kiểm tra phụ thuộc (SSI), có thể hủy transaction bằng lỗi serialization. |
| **MySQL (InnoDB)** | Thường mặc định `REPEATABLE READ`. Các `SELECT` nhất quán thông thường có thể đọc snapshot được thiết lập trong transaction; `SELECT ... FOR UPDATE`, các thao tác ghi và các trường hợp locking read xử lý theo quy tắc khóa/phiên bản hiện hành. Gap/next-key locking và chỉ mục có thể làm thay đổi cách ngăn phantom hoặc mức độ chờ. |
| **SQL Server** | `READ COMMITTED` có thể dùng shared locks hoặc row versioning theo cấu hình `READ_COMMITTED_SNAPSHOT` của cơ sở dữ liệu. `REPEATABLE READ` kiểu khóa bảo vệ các hàng đã đọc nhưng không nhất thiết ngăn hàng mới đáp ứng điều kiện; `SERIALIZABLE` có thể dùng khóa khoảng. `SNAPSHOT` là mức/cơ chế riêng của SQL Server, không phải hằng `TRANSACTION_REPEATABLE_READ` trong JDBC. |
| **Oracle Database** | `READ COMMITTED` cung cấp nhất quán đọc ở mức câu lệnh; Oracle thường chỉ hỗ trợ những mức transaction được công bố như `READ COMMITTED` và `SERIALIZABLE`, không triển khai riêng `READ UNCOMMITTED` hay `REPEATABLE READ` như các mức JDBC độc lập. `SERIALIZABLE` dựa trên snapshot transaction và có thể báo `ORA-08177` khi xung đột; cần đánh giá bất biến liên hàng thay vì suy từ tên mức cô lập. |

### PostgreSQL: cùng tên nhưng mạnh hơn bảng hiện tượng

Ở PostgreSQL, yêu cầu `READ UNCOMMITTED` không khiến `SELECT` nhìn thấy thay đổi chưa commit như mô hình dirty read. Mức `REPEATABLE READ` trong PostgreSQL cũng không cho phantom xuất hiện ở các `SELECT` thông thường trong cùng snapshot. Tuy vậy, transaction vẫn có thể mắc write skew khi chỉ dựa vào snapshot và cập nhật những hàng khác nhau.

Để bảo đảm ngữ nghĩa tuần tự hóa mà PostgreSQL cung cấp ở mức `SERIALIZABLE`, ứng dụng cần **bắt lỗi serialization và chạy lại toàn bộ transaction từ đầu**; chỉ chạy lại câu SQL cuối cùng có thể lặp lại quyết định từ dữ liệu đọc cũ.

### InnoDB: phân biệt consistent read và locking read

Một `SELECT` bình thường dưới `REPEATABLE READ` của InnoDB thường đọc theo snapshot. Tuy nhiên, `SELECT ... FOR UPDATE` (nếu dùng và được hỗ trợ trong hệ quản trị) là một **locking read**: nó phục vụ nhu cầu khóa các hàng phù hợp và có quy tắc quan sát dữ liệu khác với lần đọc snapshot.

Không nên kiểm thử duy nhất bằng hai `SELECT COUNT(*)` rồi kết luận tất cả câu SQL trong cùng transaction sẽ thấy đúng tập hàng đó. Ví dụ, `UPDATE` có thể hành xử theo trạng thái mới của các hàng đang bị cạnh tranh. Gap/next-key locking có thể giúp tránh một số phantom ở locking read, nhưng phụ thuộc chỉ mục và điều kiện truy vấn.

### SQL Server: một mức `READ COMMITTED`, nhiều chính sách đọc

Nếu `READ_COMMITTED_SNAPSHOT` được bật, đọc `READ COMMITTED` có thể dùng phiên bản hàng theo **câu lệnh**. Nếu không, cơ chế đọc dùng khóa là một lựa chọn khác. Hai cấu hình có thể cùng được JDBC báo là `TRANSACTION_READ_COMMITTED`, nhưng khác nhau về chờ khóa và xung đột reader–writer.

`SNAPSHOT` của SQL Server là một thiết lập riêng; không thể giả định gọi `setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ)` là đã bật `SNAPSHOT`. Khi cần thao tác đặc thù SQL Server, hãy đọc cấu hình cơ sở dữ liệu và cú pháp driver/hệ quản trị.

### Oracle: đọc nhất quán không có nghĩa không thể có xung đột

Oracle `READ COMMITTED` có thể trả snapshot khác nhau giữa các câu lệnh, trong khi `SERIALIZABLE` có góc nhìn nhất quán hơn trong transaction. Tuy nhiên, người lập trình vẫn phải xử lý trường hợp transaction bị từ chối, chẳng hạn `ORA-08177`, và thiết kế đúng bất biến liên quan nhiều hàng. Không nên dùng nhãn `SERIALIZABLE` của một sản phẩm làm bằng chứng duy nhất rằng mọi loại xung đột nghiệp vụ sẽ được giải quyết tự động giống sản phẩm khác.

## 6. JDBC cho biết được những gì về isolation?

JDBC cung cấp các phương thức để **yêu cầu**, **đọc** và **thăm dò khả năng hỗ trợ** mức cô lập:

| API | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `connection.getTransactionIsolation()` | Trả hằng isolation do kết nối/driver báo cáo. | Không cho biết cơ chế MVCC, khóa, các tùy chọn snapshot của server hoặc mọi bất thường có thể xảy ra. |
| `connection.setTransactionIsolation(level)` | Yêu cầu mức cô lập phù hợp với JDBC driver. | Có thể ném `SQLException` nếu không hỗ trợ; kết quả khi thay đổi giữa transaction phụ thuộc triển khai. |
| `metaData.supportsTransactionIsolationLevel(level)` | Cho biết driver/database có công bố hỗ trợ mức cụ thể. | Không thay thế thử nghiệm transaction đồng thời hay đối chiếu tài liệu sản phẩm. |
| `metaData.getDefaultTransactionIsolation()` | Trả mức cô lập mặc định do driver/database báo cáo. | Kết nối hiện tại có thể đã bị pool hoặc bên gọi thay đổi so với mặc định. |
| `metaData.supportsTransactions()` | Thăm dò hỗ trợ transaction. | Không bảo đảm mọi bảng/engine hoặc câu SQL đều có cùng hành vi transaction. |

Ví dụ tự chứa để khảo sát qua `DataSource`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class IsolationInspector {
    public static void inspect(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("DB: " + meta.getDatabaseProductName()
                    + " " + meta.getDatabaseProductVersion());
            System.out.println("Driver: " + meta.getDriverName()
                    + " " + meta.getDriverVersion());
            System.out.println("Transactions: " + meta.supportsTransactions());
            System.out.println("Default isolation: "
                    + isolationName(meta.getDefaultTransactionIsolation()));
            System.out.println("Current isolation: "
                    + isolationName(connection.getTransactionIsolation()));
            System.out.println("Auto-commit: " + connection.getAutoCommit());

            int[] levels = {
                    Connection.TRANSACTION_READ_UNCOMMITTED,
                    Connection.TRANSACTION_READ_COMMITTED,
                    Connection.TRANSACTION_REPEATABLE_READ,
                    Connection.TRANSACTION_SERIALIZABLE
            };

            for (int level : levels) {
                System.out.println(isolationName(level) + ": "
                        + meta.supportsTransactionIsolationLevel(level));
            }
        }
    }

    private static String isolationName(int level) {
        switch (level) {
            case Connection.TRANSACTION_NONE:
                return "NONE";
            case Connection.TRANSACTION_READ_UNCOMMITTED:
                return "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED:
                return "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ:
                return "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE:
                return "SERIALIZABLE";
            default:
                return "Unknown JDBC isolation value: " + level;
        }
    }
}
```

Giá trị boolean từ `supportsTransactionIsolationLevel()` chỉ là **đầu mối điều tra**. Đặc biệt, `true` không có nghĩa mọi sản phẩm hỗ trợ hiện tượng, khóa và chiến lược xung đột giống nhau. Một số driver ánh xạ yêu cầu sang mức mạnh hơn, hoặc tên báo về không mô tả hết chế độ phiên thực tế.

### Đặt isolation vào đúng thời điểm

Khi tự quản lý transaction, thông thường cần:

1. Mượn `Connection` từ `DataSource` và biết **ai đang sở hữu transaction**.
2. Ghi lại trạng thái gốc cần phục hồi, đặc biệt `getTransactionIsolation()` và `getAutoCommit()`.
3. Yêu cầu isolation **trước khi transaction bắt đầu và trước các câu lệnh đọc/ghi**; không thay giữa chừng. Theo JDBC, kết quả gọi `setTransactionIsolation(...)` trong một transaction đang hoạt động là phụ thuộc triển khai.
4. Chạy toàn bộ các câu lệnh cần được bảo vệ bằng **cùng `Connection`** với `autoCommit=false`, kết thúc bằng `commit()` hoặc `rollback()`.
5. Chỉ sau khi transaction kết thúc mới phục hồi những thuộc tính đã thay đổi và `close()` để trả kết nối về pool. Nếu rollback hoặc phục hồi trạng thái thất bại, kết nối cần được coi là không an toàn để tái sử dụng theo chính sách của pool.

Không tự `commit()` hoặc đổi isolation trên kết nối đang thuộc transaction manager của framework: lúc đó ranh giới transaction phải được điều khiển bởi bên sở hữu.

Đây là một ví dụ **sử dụng** các phương thức JDBC trong phạm vi kết nối và transaction mà tầng gọi đã thiết lập đúng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

// Hàm này chỉ thực thi SELECT; bên gọi sở hữu Connection và transaction.
public static long countPendingOrders(Connection connection)
        throws SQLException {
    String sql = "SELECT COUNT(*) FROM orders WHERE status = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, "PENDING");
        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("COUNT query returned no row");
            }
            return result.getLong(1);
        }
    }
}
```

Tầng gọi có thể chạy `countPendingOrders(connection)` hai lần trong cùng transaction, xen vào giữa bằng việc transaction khác chèn đơn hàng `PENDING` rồi commit. Nếu hai lần đếm khác nhau, đã quan sát được một phantom. Nếu hai lần đếm bằng nhau, **chưa đủ kết luận** rằng isolation ngăn mọi phantom: cần biết transaction kia có thực sự chèn và commit đúng thời điểm không, hoặc liệu câu lệnh của nó bị chặn.

## 7. Thiết kế thử nghiệm bằng hai kết nối độc lập

Để kiểm chứng, dùng cơ sở dữ liệu thử nghiệm, hai kết nối `A` và `B` lấy độc lập từ `DataSource` (hoặc hai SQL client), và đảm bảo cả hai đều đã đặt `autoCommit=false`. Không chạy hai transaction trên cùng một `Connection`: khi đó không thể kiểm tra hành vi giữa các transaction độc lập.

### Thử nghiệm A: thay đổi giá trị trong lúc transaction đang đọc

Chuẩn bị:

```sql
CREATE TABLE isolation_demo (
    id BIGINT PRIMARY KEY,
    amount INTEGER NOT NULL
);

INSERT INTO isolation_demo (id, amount) VALUES (1, 100);
```

Lịch chạy mẫu:

| Bước | Kết nối A | Kết nối B |
| ---: | --- | --- |
| 1 | Đặt isolation cần thử **trước** transaction, rồi bắt đầu transaction | Chưa làm gì |
| 2 | `SELECT amount FROM isolation_demo WHERE id = 1` → 100 | |
| 3 | | Bắt đầu transaction; `UPDATE isolation_demo SET amount = 200 WHERE id = 1` |
| 4 | | `COMMIT` |
| 5 | Chạy lại đúng `SELECT` ở bước 2, ghi giá trị hoặc ghi nhận việc bị chờ/lỗi | |
| 6 | `COMMIT` hoặc `ROLLBACK`, đóng tài nguyên | |

Chạy lại với `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Ghi nhận **giá trị quan sát được, việc B có phải chờ hay không, lỗi serialization/deadlock** và cách server cấu hình. Nếu `B` bị chặn, không ép bước 4 hoàn thành mà bỏ qua thứ tự sự kiện đã định; hãy ghi rõ tình huống blocking, rồi thay đổi phương án điều phối thử nghiệm.

### Thử nghiệm B: thêm một hàng thỏa điều kiện

```sql
CREATE TABLE isolation_orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

INSERT INTO isolation_orders (id, status) VALUES (1, 'PENDING');
```

Trên kết nối A, đếm `WHERE status = 'PENDING'` trong transaction. Trên B, thử `INSERT INTO isolation_orders (id, status) VALUES (2, 'PENDING')` rồi commit. A đếm lần nữa trong **cùng transaction**. Với mức cách ly có cơ chế khóa phạm vi, B có thể phải chờ hoặc xảy ra deadlock; với một số MVCC, A tiếp tục thấy snapshot cũ.

**Không kiểm định chỉ bằng một con số cuối cùng.** Hãy lưu thêm: thời điểm snapshot được tạo, SQL thực thi, loại câu `SELECT`, việc chờ khóa, mã `SQLState`, thời gian chờ và kết quả commit/rollback.

### Thử nghiệm C: bất biến liên hàng

Tạo hai hàng bác sĩ trực như phần 2.5. Trong hai transaction, cùng đọc số bác sĩ đang trực và cùng quyết định tắt trạng thái của **hai bác sĩ khác nhau**. Ghi nhận liệu cả hai transaction cùng commit, một bên bị chặn, hay có lỗi buộc retry. Đây là phép thử có giá trị hơn nhiều để phân biệt **snapshot ổn định** với **khả năng bảo vệ bất biến liên hàng**.

Chạy các thử nghiệm trên **cùng phiên bản driver, hệ quản trị và cấu hình** sẽ dùng khi triển khai. Nếu thử bằng H2 hay một DB nhúng khác, không suy kết quả sang PostgreSQL, Oracle, SQL Server hoặc MySQL. Isolation và cơ chế khóa là những phần có thể khác nhau đáng kể giữa các sản phẩm.

## 8. Isolation liên quan thế nào đến khóa, hiệu năng và xử lý lỗi?

Mức cô lập mạnh hơn thường làm tăng chi phí **theo một cách nào đó**, nhưng không phải lúc nào cũng chỉ là giữ nhiều khóa hơn:

- Hệ khóa có thể tăng thời gian chờ, deadlock và khóa phạm vi.
- Hệ MVCC có thể cần giữ nhiều phiên bản dữ liệu, quản lý snapshot và phát hiện xung đột.
- Cơ chế serializable dựa trên kiểm tra phụ thuộc có thể cho nhiều transaction chạy song song nhưng **hủy một số transaction lúc kết thúc**.
- Transaction mở quá lâu tăng khả năng xung đột, giữ tài nguyên và gây khó cho việc dọn các phiên bản cũ.

### Khi transaction phải retry

Nếu database báo lỗi serialization, deadlock hoặc xung đột có thể retry, quyết định retry phải dựa trên **mã lỗi và hợp đồng của driver/database**. Không bắt tất cả `SQLException` rồi lặp vô hạn.

```text
Bắt đầu transaction mới
  → đọc dữ liệu cần thiết
  → tính quyết định nghiệp vụ
  → thực thi cập nhật
  → COMMIT
      ├─ Thành công: hoàn tất
      └─ Lỗi retryable: ROLLBACK / giải phóng connection
                         → tạo transaction mới
                         → đọc lại dữ liệu và tính lại
                         → thử lại có giới hạn
```

Với PostgreSQL, lỗi serialization thường có SQLSTATE `40001`. Nhiều hệ quản trị cũng có mã riêng cho deadlock hoặc lock timeout; **không mặc định mọi mã đều có thể retry an toàn**. Retry phải bao trùm **toàn bộ phần đọc–quyết định–ghi** của transaction. Với tác động bên ngoài cơ sở dữ liệu (gửi email, gọi thanh toán, publish sự kiện), cần idempotency hoặc outbox; nếu không, chạy lại transaction có thể tạo tác động lặp.

### Isolation không thay thế ràng buộc dữ liệu

Giả sử hai người dùng cùng đặt cùng một ghế. Ngoài isolation phù hợp, một `UNIQUE` constraint hoặc thiết kế khóa tài nguyên có thể là lớp bảo vệ quyết định để tránh tạo hai bản ghi trùng. Khi cập nhật một phiên bản của hàng, có thể dùng optimistic locking:

```sql
UPDATE documents
SET content = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Nếu `executeUpdate()` trả `0`, dữ liệu đã thay đổi hoặc hàng không còn tồn tại; tầng nghiệp vụ phải quyết định tải lại, báo xung đột hay retry. Cần phân biệt rõ ràng **mức cô lập toàn transaction** với **cơ chế kiểm soát cạnh tranh cho một thao tác cụ thể**.

## 9. Cách chọn mức cô lập trong ứng dụng JDBC

Không có một mức cô lập duy nhất tối ưu cho mọi transaction. Một cách ra quyết định thực tế:

| Nhu cầu | Điều nên kiểm tra trước |
| --- | --- |
| Đọc và ghi một hàng bằng điều kiện nguyên tử | Câu `UPDATE ... WHERE ...` và ràng buộc đã đủ bảo vệ bất biến chưa? |
| Cần đọc lại cùng dữ liệu trong báo cáo | Snapshot kéo dài bao lâu, query được xem là consistent read hay locking read, dữ liệu thay đổi có cần hiển thị không? |
| Đặt chỗ, cấp số lượng tồn kho, chống trùng lịch | Đang bảo vệ một khóa hàng hay một **tập hàng theo điều kiện**? Cần khóa phạm vi, ràng buộc hoặc serializable không? |
| Nghiệp vụ có bất biến liên nhiều hàng | Snapshot alone có thể gặp write skew; thử nghiệm xung đột thực tế và kế hoạch retry. |
| Hệ thống đọc nhiều, ghi liên tục | Đo blocking, throughput, chi phí MVCC và tần suất serialization failure trên dữ liệu thật. |
| Transaction qua nhiều repository | Dùng cùng `Connection` và một chủ sở hữu transaction; nhất quán cấu hình isolation và logic rollback. |

Quy trình đề xuất:

1. **Viết rõ bất biến cần bảo vệ**: “không bán quá tồn kho”, “ít nhất một người trực”, “không có hai booking trùng ghế”.
2. **Xác định câu SQL thực tế**: các lệnh đọc, ghi, điều kiện, chỉ mục và phạm vi transaction.
3. **Xác nhận hệ quản trị và chế độ phiên**: tên mức isolation, cách snapshot được chốt, tác động của read-only/locking reads.
4. **Chạy kiểm thử với nhiều connection**: cả thành công, blocking, rollback, deadlock và retry.
5. **Đo rồi chọn**: cân bằng tính đúng đắn với latency, throughput và chi phí giữ transaction.
6. **Ghi lại quyết định**: driver/version, các thiết lập server có ảnh hưởng, mức cô lập được yêu cầu và hành vi đã kiểm chứng.

Nếu dùng connection pool, hãy khôi phục isolation về giá trị trước khi thay đổi **sau khi transaction đã kết thúc**. Không đổi isolation giữa transaction và không trả kết nối còn transaction dang dở. Đây cũng là yêu cầu quan trọng khi xử lý exception trong CRUD và batching.

## 10. Bài thực hành và câu hỏi tự kiểm tra

1. Dùng `IsolationInspector.inspect(...)` để in driver, mức mặc định và các mức được báo là hỗ trợ. Giải thích vì sao kết quả `supportsTransactionIsolationLevel(...) = true` chưa đủ để kết luận có hay không có phantom.
2. Dùng hai kết nối A/B chạy kịch bản cập nhật `isolation_demo`. So sánh `READ COMMITTED` với `REPEATABLE READ`. Khi B bị chặn, hãy ghi nhận blocking thay vì tự cho đó là một lần đọc không lặp.
3. Chạy kịch bản đếm `isolation_orders` hai lần. Nếu kết quả không đổi, hãy nêu ít nhất **ba lý do khác nhau**: transaction snapshot cố định, B chưa commit, hoặc B đang chờ khóa.
4. Thử tình huống hai bác sĩ trực; chỉ ra vì sao việc không thấy non-repeatable read chưa chứng minh bất biến liên hàng được bảo vệ.
5. Tạo một lần xung đột phiên bản của câu `UPDATE ... WHERE version = ?`. Kiểm tra `executeUpdate() == 0` và mô tả chiến lược ứng dụng báo lỗi hoặc retry.
6. Ghi ngắn gọn mức cô lập thực sự của hệ quản trị trong môi trường thử: loại `SELECT`, cấu hình liên quan, SQLSTATE nhận được và các khác biệt so với bảng JDBC.

**Ghi nhớ:** `Connection.TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ` hay `TRANSACTION_SERIALIZABLE` là tên giao diện JDBC, không phải bản mô tả hoàn chỉnh về khóa, snapshot và lịch thực thi. Muốn bảo đảm đúng nghiệp vụ, phải hiểu **hiện tượng cần ngăn**, **cách hệ quản trị triển khai**, **cấu hình hiện tại** và **câu SQL thực tế**. Hãy kiểm chứng bằng các transaction đồng thời, ghi nhận blocking/lỗi và chuẩn bị cơ chế retry phù hợp.
