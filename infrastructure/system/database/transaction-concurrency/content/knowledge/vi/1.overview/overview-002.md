# Các thuật ngữ nền tảng: phiên, kết nối, giao dịch và câu lệnh

Khi một ứng dụng làm việc với cơ sở dữ liệu, các từ **phiên (session)**, **kết nối (connection)**, **giao dịch (transaction)** và **câu lệnh (statement)** thường xuất hiện gần nhau. Tuy nhiên, chúng trả lời bốn câu hỏi khác nhau:

- **Phiên:** Cơ sở dữ liệu đang duy trì ngữ cảnh làm việc nào cho một bên truy cập?
- **Kết nối:** Ứng dụng dùng tài nguyên và kênh giao tiếp nào để trao đổi với cơ sở dữ liệu?
- **Giao dịch:** Những thay đổi nào được xem là một đơn vị thành công hoặc thất bại?
- **Câu lệnh:** Cơ sở dữ liệu được yêu cầu thực hiện thao tác SQL cụ thể nào?

Phân biệt bốn khái niệm này giúp hiểu đúng khóa dữ liệu, khả năng nhìn thấy thay đổi, thời điểm ghi nhận kết quả và các lỗi cạnh tranh khi nhiều người dùng truy cập đồng thời.

## 1. Bức tranh tổng thể

Trong mô hình ứng dụng Java sử dụng JDBC và hệ quản trị cơ sở dữ liệu quan hệ, luồng làm việc thường có hình dạng sau:

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Connection<br/>mượn từ pool"]
    B --> C["Phiên làm việc<br/>trên DB"]
    C --> T1["Giao dịch T1"]
    C --> T2["Giao dịch T2 (sau T1)"]
    T1 --> S1["SQL: UPDATE"]
    T1 --> S2["SQL: UPDATE"]
    T2 --> S3["SQL: SELECT"]
~~~

Sơ đồ minh họa một phiên có thể phục vụ **nhiều giao dịch nối tiếp**; một giao dịch có thể thực thi **nhiều câu lệnh**. Trong cách sử dụng JDBC thông thường, các câu lệnh thuộc cùng một giao dịch được thực hiện trên cùng một kết nối giao dịch.

Đây là mô hình cơ bản, không phải quy tắc ánh xạ một-một cho mọi kiến trúc: connection pool, proxy, multiplexing và cơ chế giao dịch phân tán có thể làm mối quan hệ giữa kết nối phía ứng dụng và phiên phía máy chủ phức tạp hơn.

| Khái niệm | Bản chất | Phạm vi điển hình | Điều cần nhớ |
| --- | --- | --- | --- |
| **Phiên DB** | Ngữ cảnh phía hệ quản trị CSDL cho một bên truy cập | Từ khi phiên được thiết lập đến khi kết thúc hoặc bị hủy | Chứa trạng thái phiên, không đồng nghĩa với giao dịch |
| **Kết nối** | Tài nguyên/kênh giao tiếp được ứng dụng sử dụng | Từ lúc mở hoặc mượn đến lúc đóng hoặc trả pool | Có thể được tái sử dụng qua nhiều lần xử lý |
| **Giao dịch** | Đơn vị công việc có ranh giới xác nhận hoặc hủy bỏ | Bắt đầu giao dịch đến COMMIT/ROLLBACK hoặc kết thúc tương đương | Có thể gom nhiều câu lệnh thành một thay đổi logic |
| **Câu lệnh SQL** | Một yêu cầu SQL cụ thể được thực thi | Từ khi gửi/thực thi đến khi hoàn tất hoặc bị hủy | Có thể là SELECT, INSERT, UPDATE, DELETE… |

## 2. Phiên cơ sở dữ liệu (database session)

**Phiên** là ngữ cảnh làm việc mà hệ quản trị CSDL duy trì cho một client hoặc một kết nối logic. Tùy sản phẩm, phiên có thể lưu thông tin về:

- Danh tính đăng nhập và các quyền được áp dụng.
- Schema hiện hành, tham số hoặc biến phiên.
- Thiết lập ảnh hưởng đến hành vi truy vấn, chẳng hạn múi giờ hoặc một số tùy chọn phiên.
- Trạng thái liên quan đến các câu lệnh, con trỏ và giao dịch đang diễn ra.

Ví dụ: ứng dụng đăng nhập CSDL bằng tài khoản dịch vụ và thiết lập một tham số ở cấp phiên. Các câu lệnh thực thi trong phiên đó có thể chịu ảnh hưởng của tham số cho đến khi phiên bị đặt lại hoặc kết thúc.

**Phiên CSDL không phải phiên HTTP.** Một người dùng đăng nhập website có thể phát sinh nhiều HTTP request; các request đó có thể mượn các kết nối DB khác nhau từ pool. Ngược lại, một phiên DB được pool giữ sống có thể lần lượt phục vụ yêu cầu của nhiều người dùng ứng dụng.

**Phiên cũng không phải tiến trình máy chủ.** Một số hệ CSDL có mô hình tiến trình chuyên trách; hệ khác có thể chia sẻ tiến trình hoặc luồng để xử lý nhiều phiên. Không nên dùng số phiên để suy trực tiếp số tiến trình hệ điều hành.

### Trạng thái phiên và tác động đến tính đúng đắn

Giả sử một request thiết lập schema, role hoặc biến phiên rồi trả kết nối về pool. Nếu trạng thái đó không được khôi phục đúng cách, request khác có thể nhận lại kết nối gắn với phiên còn mang thiết lập cũ. Đây là lý do việc quản lý pool và trạng thái phiên quan trọng với cả tính đúng đắn lẫn bảo mật.

Không nên giả định hai lần gọi lấy kết nối sẽ đi vào **cùng một phiên DB**, ngay cả khi cùng dùng một tài khoản đăng nhập. Cũng không nên giả định mọi hệ thống ánh xạ một đối tượng kết nối Java sang đúng một phiên máy chủ cố định: proxy hoặc bộ ghép kênh có thể thay đổi chi tiết này.

## 3. Kết nối cơ sở dữ liệu (database connection)

**Kết nối** là cách ứng dụng trao đổi yêu cầu và kết quả với cơ sở dữ liệu. Ở mức mạng, hệ thống thường có một kết nối vật lý tới máy chủ hoặc proxy. Ở mức JDBC, chương trình làm việc thông qua đối tượng **java.sql.Connection**.

Một đối tượng Connection cho phép ứng dụng:

- Tạo và thực thi câu lệnh qua Statement hoặc PreparedStatement.
- Kiểm soát chế độ auto-commit.
- Gọi commit() hoặc rollback() để kết thúc giao dịch do ứng dụng quản lý.
- Truy cập metadata và một số cấu hình liên quan đến kết nối.

**Kết nối vật lý** và **đối tượng kết nối mà ứng dụng đang mượn** không nhất thiết cùng vòng đời. Với connection pool, ứng dụng thường gọi close() để **trả kết nối về pool**, chứ không nhất thiết đóng ngay socket vật lý.

~~~text
Connection pool
  ├── Kết nối vật lý A ── mượn cho request 1 ── trả pool ── mượn cho request 4
  ├── Kết nối vật lý B ── mượn cho request 2 ── trả pool
  └── Kết nối vật lý C ── mượn cho request 3 ── trả pool
~~~

Mỗi lần mượn có thể thực hiện một hoặc nhiều giao dịch, tùy cấu hình và cách ứng dụng tổ chức công việc. Việc trả kết nối về pool cần đi kèm xử lý trạng thái giao dịch và thiết lập kết nối theo hợp đồng của pool; không nên kỳ vọng close() thay thế cho commit() rõ ràng.

### Kết nối có đồng nghĩa với giao dịch không?

Không. Một kết nối có thể tồn tại qua nhiều giao dịch nối tiếp. Ngược lại, trong JDBC thông thường, một giao dịch cục bộ sử dụng **một kết nối xác định** để các câu lệnh cùng thuộc ranh giới commit/rollback.

Nếu vô tình dùng hai Connection độc lập để thực thi hai câu lệnh rồi chỉ gọi commit() trên một Connection, không thể mặc nhiên coi hai thay đổi là **một giao dịch nguyên tử**. Giao dịch phân tán có cơ chế phối hợp riêng, nằm ngoài tình huống JDBC cục bộ cơ bản.

## 4. Giao dịch cơ sở dữ liệu (database transaction)

**Giao dịch** là một đơn vị công việc mà hệ quản trị CSDL xử lý theo ranh giới xác nhận hoặc hủy bỏ. Ví dụ, chuyển 100 đơn vị tiền từ tài khoản A sang tài khoản B cần hai thao tác:

1. Giảm số dư tài khoản A đi 100.
2. Tăng số dư tài khoản B thêm 100.

Hai thao tác này phải thành công cùng nhau. Nếu chỉ thực hiện được thao tác thứ nhất, dữ liệu sẽ không phản ánh một lần chuyển tiền hoàn chỉnh. Đặt chúng trong cùng một giao dịch giúp ứng dụng **COMMIT** khi cả hai thành công, hoặc **ROLLBACK** khi có lỗi.

Bốn thuộc tính thường dùng để mô tả giao dịch là **ACID**:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| **Atomicity (nguyên tử)** | Các thay đổi trong giao dịch được xác nhận như một đơn vị; khi rollback, các thay đổi chưa commit của giao dịch được hủy theo bảo đảm của hệ CSDL |
| **Consistency (nhất quán)** | Giao dịch phải tuân thủ các ràng buộc dữ liệu và quy tắc nghiệp vụ được thực thi phù hợp; CSDL không tự biết mọi quy tắc nghiệp vụ |
| **Isolation (cô lập)** | Quy định cách giao dịch đồng thời nhìn thấy hoặc ảnh hưởng đến dữ liệu của nhau; mức bảo đảm tùy isolation level và DBMS |
| **Durability (bền vững)** | Khi commit được xác nhận thành công, hệ CSDL có trách nhiệm bảo toàn kết quả theo cam kết độ bền của nó |

Một giao dịch có thể chứa một câu lệnh hoặc nhiều câu lệnh. Một phiên có thể lần lượt thực thi nhiều giao dịch. Giao dịch thường ngắn hơn vòng đời kết nối được pool duy trì.

### Giao dịch bắt đầu và kết thúc lúc nào?

Cú pháp và thời điểm bắt đầu giao dịch phụ thuộc DBMS, driver và framework. Trong JDBC, chương trình thường dùng:

- **setAutoCommit(false):** tắt chế độ tự commit để chủ động nhóm các câu lệnh.
- **commit():** xác nhận thay đổi của giao dịch hiện tại.
- **rollback():** hủy thay đổi chưa được commit của giao dịch hiện tại.

Khi **auto-commit bật** (giá trị mặc định thông thường của JDBC Connection mới), mỗi câu lệnh được thực thi và hoàn tất thường thuộc một giao dịch được tự động commit. Chi tiết về thời điểm câu lệnh được coi là hoàn tất, đặc biệt với truy vấn trả về ResultSet, tuân theo hợp đồng JDBC và driver.

Khi **auto-commit tắt**, nhiều câu lệnh có thể thuộc cùng một giao dịch cho đến khi commit()/rollback() kết thúc nó. JDBC cho phép giao dịch tiếp theo bắt đầu sau ranh giới kết thúc theo hành vi của driver và hệ CSDL.

Không thể suy rằng một lệnh SQL bất kỳ cũng khởi tạo một giao dịch mới theo cùng cách ở mọi DBMS. Chẳng hạn, một số lệnh DDL có hành vi commit ngầm trong những hệ quản trị như Oracle; các lệnh quản trị hoặc truy vấn đặc biệt cũng có quy tắc riêng. Cần đọc tài liệu của DBMS khi xác định ranh giới giao dịch thực tế.

## 5. Câu lệnh SQL (SQL statement)

**Câu lệnh** là một yêu cầu SQL cụ thể: đọc dữ liệu, sửa dữ liệu hoặc quản trị đối tượng CSDL. Những ví dụ phổ biến:

~~~sql
SELECT id, balance
FROM accounts
WHERE id = 1;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

INSERT INTO transfers(from_account_id, to_account_id, amount)
VALUES (1, 2, 100);

DELETE FROM expired_sessions
WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Trong JDBC:

- **Statement** là API để thực thi SQL, thường với chuỗi câu lệnh tĩnh.
- **PreparedStatement** là API cho SQL được tham số hóa, cho phép truyền tham số an toàn hơn và có thể hỗ trợ cơ chế chuẩn bị/tái sử dụng của driver/DBMS.
- **ResultSet** đại diện cho kết quả dạng bảng mà một truy vấn trả về.

Không nên nhầm **đối tượng java.sql.Statement** với **giao dịch**. Một PreparedStatement có thể được gọi executeUpdate() nhiều lần; mỗi lần gọi là một lần thực thi. Những lần thực thi đó thuộc cùng hay khác giao dịch tùy cách Connection đang quản lý ranh giới commit.

**SELECT cũng là một câu lệnh.** Việc chỉ đọc dữ liệu không làm cho khái niệm transaction trở nên vô nghĩa: khả năng nhìn thấy phiên bản dữ liệu, snapshot và khóa đọc có thể phụ thuộc mức cô lập và cơ chế của hệ CSDL.

Ngoài DML (INSERT/UPDATE/DELETE), SQL còn có DDL (CREATE/ALTER/DROP) và các lệnh điều khiển giao dịch như COMMIT/ROLLBACK. Tác động của từng loại lên transaction phụ thuộc hệ quản trị, không nên áp một quy tắc cho tất cả.

## 6. Theo dõi một giao dịch bằng ví dụ JDBC

Giả sử hai tài khoản ban đầu có số dư A = 1.000 và B = 500. Ứng dụng muốn chuyển 100 từ A sang B. Hai câu lệnh UPDATE phải cùng được commit; nếu một câu lệnh thất bại, ứng dụng rollback cả giao dịch.

Đoạn mã dưới đây minh họa cơ chế JDBC cục bộ. Các biến amount, fromId, toId và dataSource được giả định đã có; nghiệp vụ thực tế còn cần kiểm tra quyền, idempotency và các ràng buộc phù hợp.

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try (
        PreparedStatement debit = connection.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?");
        PreparedStatement credit = connection.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance + ? " +
            "WHERE id = ?")
    ) {
        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromId);
        debit.setBigDecimal(3, amount);

        if (debit.executeUpdate() != 1) {
            throw new SQLException("Không thể trừ tiền từ tài khoản nguồn");
        }

        credit.setBigDecimal(1, amount);
        credit.setLong(2, toId);

        if (credit.executeUpdate() != 1) {
            throw new SQLException("Không thể cộng tiền vào tài khoản đích");
        }

        connection.commit();
    } catch (SQLException | RuntimeException exception) {
        connection.rollback();
        throw exception;
    } finally {
        connection.setAutoCommit(previousAutoCommit);
    }
}
~~~

Trong ví dụ này:

1. **dataSource.getConnection()** cho chương trình một Connection, thường là kết nối logic mượn từ pool; phiên DB cụ thể được cơ sở hạ tầng kết nối quản lý.
2. **setAutoCommit(false)** cho phép chủ động kiểm soát giao dịch.
3. **debit.executeUpdate()** và **credit.executeUpdate()** là **hai lần thực thi câu lệnh** trên cùng Connection.
4. **commit()** xác nhận cả hai thay đổi của giao dịch; **rollback()** hủy các thay đổi chưa commit khi gặp lỗi trước đó.
5. **close()** được try-with-resources gọi ở cuối để giải phóng/trả kết nối. Hoàn trả kết nối và xác nhận giao dịch là hai thao tác có ý nghĩa khác nhau.

Khi thành công, số dư trở thành A = 900 và B = 600. Nếu cập nhật tài khoản đích không thành công, rollback đưa các thay đổi chưa commit của giao dịch trở về trạng thái trước giao dịch.

Đây là ví dụ về **ranh giới giao dịch**, không phải thiết kế hoàn chỉnh cho hệ thống chuyển tiền: ứng dụng thật phải xử lý cả lỗi không chắc chắn trạng thái commit, khả năng retry, tài khoản trùng nhau, giới hạn số tiền, số dư và các quy tắc nghiệp vụ khác. Một lỗi khi rollback hoặc trả kết nối cũng cần được ứng dụng thực tế xử lý thích hợp.

### Nếu bật auto-commit thì sao?

Giả sử ứng dụng thực thi cùng hai UPDATE nhưng để auto-commit bật:

~~~text
UPDATE A thành công  --> có thể đã commit
UPDATE B thất bại   --> không thể dùng ROLLBACK để hủy commit của A
~~~

Kết quả có thể là A mất 100 mà B không nhận được 100. **Hai câu lệnh riêng biệt không tự tạo thành một giao dịch nghiệp vụ nguyên tử.** Muốn nhóm chúng, phải cấu hình và quản lý ranh giới giao dịch đúng cách.

## 7. Hai giao dịch đồng thời: ai nhìn thấy điều gì?

Cạnh tranh xuất hiện khi nhiều giao dịch đang hoạt động trên dữ liệu chung. Ví dụ hai người dùng cùng cập nhật một bản ghi hàng tồn kho:

| Thời điểm | Giao dịch T1, kết nối C1 | Giao dịch T2, kết nối C2 |
| --- | --- | --- |
| 1 | Đọc tồn kho hiện tại: 10 | |
| 2 | | Đọc tồn kho hiện tại: 10 |
| 3 | Tính tồn kho mới là 9 | |
| 4 | | Tính tồn kho mới là 8 |
| 5 | Ghi 9 rồi commit | |
| 6 | | Ghi 8 rồi commit, nếu DBMS và mức cô lập cho phép |

Nếu cả hai lần ghi đều được chấp nhận theo lịch trình này, kết quả cuối là 8, trong khi hai nghiệp vụ lần lượt trừ 1 và 2 phải cho ra 7. Đây là dạng **lost update** có thể xảy ra khi chương trình đọc rồi ghi lại giá trị cũ mà thiếu cơ chế bảo vệ phù hợp.

Không phải DBMS nào cũng cho phép lịch trình trên hoàn tất như vậy. Một số mức cô lập, cơ chế khóa hoặc kiểm tra xung đột có thể chặn hay từ chối một giao dịch. Cách xử lý thường liên quan đến câu lệnh cập nhật có điều kiện, cập nhật số học trực tiếp trên DB, optimistic locking bằng version hoặc isolation level phù hợp.

Điều cần phân định là:

- **Kết nối/phiên** cho biết các luồng làm việc truy cập DB qua ngữ cảnh nào.
- **Giao dịch** cho biết ranh giới công việc và mức cô lập giữa các đơn vị công việc.
- **Câu lệnh** cho biết thao tác SQL nào thực sự đọc hoặc sửa dữ liệu.
- **Khóa, MVCC, snapshot và isolation level** quyết định chi tiết một giao dịch có thể quan sát hoặc chặn giao dịch khác ra sao.

Có giao dịch không đồng nghĩa với không bao giờ xảy ra xung đột. ACID phải được hiểu cùng với mức cô lập và cơ chế thực thi của DBMS.

## 8. So sánh vòng đời qua một request ứng dụng

Một HTTP request không nhất thiết tương ứng với một transaction hay một DB session. Hãy xét ứng dụng có connection pool:

~~~text
Ứng dụng khởi động
    |
    +-- Pool tạo/duy trì các kết nối vật lý và phiên DB
            |
Request R1 mượn Connection X
    |
    +-- Transaction T1 bắt đầu
    |      |
    |      +-- SQL SELECT
    |      +-- SQL UPDATE
    |      +-- COMMIT
    |
    +-- Trả Connection X về pool
            |
Request R2 có thể mượn lại Connection X
    |
    +-- Transaction T2 bắt đầu
           |
           +-- SQL SELECT
           +-- ROLLBACK hoặc COMMIT
~~~

Ở mô hình phổ biến này, **T1 và T2 là hai giao dịch khác nhau** dù có thể sử dụng lại cùng kết nối vật lý hoặc phiên DB theo thời gian. Không thể lấy thời gian tồn tại của Connection để suy ra thời gian tồn tại của transaction.

Một request cũng có thể dùng nhiều transaction hoặc không thực thi truy vấn DB nào. Với Spring, **@Transactional** có thể xác định phạm vi giao dịch do transaction manager quản lý; phạm vi thực sự còn phụ thuộc proxy/interceptor, transaction propagation và cách lấy kết nối. Tên annotation không phải bằng chứng rằng một phương thức chỉ chạy một câu lệnh hoặc rằng mọi lời gọi sang tài nguyên khác tự tham gia cùng một giao dịch.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Mở một Connection nghĩa là đã bắt đầu một transaction dài hạn.” | Kết nối là tài nguyên truy cập. Thời điểm bắt đầu giao dịch phụ thuộc chế độ auto-commit, DBMS và framework. |
| “Một phiên DB chỉ thực hiện được một giao dịch.” | Một phiên có thể thực hiện nhiều giao dịch **nối tiếp** trong vòng đời của nó. |
| “Một giao dịch chỉ chứa một câu lệnh.” | Giao dịch có thể chứa nhiều SELECT/UPDATE/INSERT/DELETE, cùng chịu một ranh giới commit/rollback. |
| “Mọi câu lệnh SQL đều tự commit.” | Điều này phụ thuộc auto-commit, loại câu lệnh và quy tắc của DBMS. |
| “Gọi close() đồng nghĩa với commit().” | Đóng/trả Connection là giải phóng tài nguyên; commit xác nhận giao dịch. Hãy xác định ranh giới rõ ràng. |
| “Có transaction là tránh được mọi lỗi concurrency.” | Còn phải xét isolation level, khóa, MVCC và xử lý xung đột. |
| “Mỗi request HTTP có một DB session riêng.” | Request thường mượn kết nối từ pool; cùng kết nối/phiên có thể phục vụ nhiều request nối tiếp. |
| “Hai câu lệnh trên hai Connection sẽ cùng rollback.” | Không đúng với hai giao dịch JDBC cục bộ độc lập nếu không có cơ chế phối hợp giao dịch. |
| “SELECT không liên quan đến transaction.” | Khả năng nhìn thấy dữ liệu, snapshot và khóa đọc vẫn có thể chịu tác động của transaction và isolation. |

### Một vài câu hỏi tự kiểm tra

**1. Có thể thực thi 10 câu lệnh trong một giao dịch không?** Có, nếu 10 câu lệnh được thực thi trong đúng phạm vi giao dịch và hệ CSDL hỗ trợ những thao tác đó trong giao dịch.

**2. Một Connection từ pool được dùng cho nhiều người dùng ứng dụng có phải tất cả dùng chung một transaction?** Không. Connection có thể được dùng lại tuần tự cho những giao dịch tách biệt. Pool phải quản lý trạng thái giao dịch và phiên khi cho mượn/trả.

**3. Hai giao dịch trên hai Connection sửa cùng một hàng dữ liệu thì điều gì xảy ra?** Có thể xảy ra chờ khóa, xung đột, lỗi deadlock, từ chối commit hoặc thứ tự cập nhật tùy DBMS, loại SQL và isolation level. Cần quan sát chính câu lệnh, lock và transaction boundary để giải thích.

**4. Nếu UPDATE thứ nhất thành công, UPDATE thứ hai thất bại, dữ liệu sẽ ra sao?** Nếu cả hai cùng một giao dịch chưa commit và rollback thành công, thay đổi của UPDATE thứ nhất được hủy. Nếu UPDATE thứ nhất đã commit riêng, rollback giao dịch thứ hai không thể tự hủy kết quả đã commit trước đó.

## 10. Cách đọc log và chẩn đoán thực tế

Khi điều tra vấn đề concurrent update, deadlock hoặc giao dịch kéo dài, nên lần lượt xác định:

1. **Request/luồng ứng dụng:** thao tác nghiệp vụ nào gọi DB, có retry hoặc xử lý bất đồng bộ không?
2. **Connection/phiên:** câu lệnh đang chạy qua kết nối nào, có mượn từ pool hay mất kết nối giữa chừng không?
3. **Transaction:** bắt đầu khi nào, đã commit/rollback chưa, isolation level nào đang áp dụng?
4. **Statement:** câu SQL nào thực thi, tham số gì, ảnh hưởng bao nhiêu hàng, có lock/wait hay lỗi gì?
5. **Tương tác với giao dịch khác:** cùng truy cập bản ghi nào, thứ tự lock ra sao, có thời điểm chờ hoặc phát hiện deadlock không?

Log tốt thường cần mã định danh request và transaction, cùng thông tin connection/session khi hệ thống có thể thu thập một cách đáng tin cậy. Các mã này có phạm vi riêng và không thể thay thế cho nhau. Chẳng hạn, connection id trùng qua hai thời điểm không chứng minh hai câu lệnh nằm trong cùng một transaction; ngược lại, hai request id khác nhau có thể tiếp tục cùng một nghiệp vụ nhưng dùng các giao dịch khác nhau.

**Ghi nhớ mối quan hệ cốt lõi:** ứng dụng dùng **kết nối** để nói chuyện với DB; hệ CSDL duy trì **phiên** làm ngữ cảnh; ứng dụng/DBMS đặt các **câu lệnh** vào **giao dịch** để kiểm soát commit, rollback và tính cô lập. Hiểu đúng bốn tầng này là nền tảng để phân tích các bài toán transaction và concurrency tiếp theo.
