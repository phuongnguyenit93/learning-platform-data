# Đọc kết quả tổng hợp trong lúc các giao dịch chuyển dịch dữ liệu

Một truy vấn tổng hợp thường đọc nhiều hàng để tính ra một con số hoặc báo cáo: tổng số dư, tổng tồn kho, tổng doanh thu, số lượng đơn hàng hay tỷ lệ hoàn thành. Khi nhiều giao dịch đồng thời chuyển dữ liệu giữa các hàng, kết quả tổng hợp có thể phản ánh một trạng thái **chưa từng tồn tại đồng thời trong cơ sở dữ liệu**.

Ví dụ, tài khoản A có 600 và tài khoản B có 400. Một giao dịch chuyển 100 từ A sang B. Tổng số tiền phải luôn là 1.000. Nhưng nếu truy vấn báo cáo đọc A trước khi chuyển tiền và đọc B sau khi chuyển tiền, nó có thể tính được 600 + 500 = 1.100. Con số đó không phải tổng tại một thời điểm thực nào; nó ghép hai ảnh chụp khác nhau của dữ liệu.

Hiện tượng này thường được gọi là **read skew** hoặc **inconsistent analysis** trong bối cảnh đọc nhiều dữ liệu liên quan trong khi giao dịch khác đang cập nhật. Hiểu hiện tượng giúp lựa chọn isolation level, snapshot và cách tổ chức báo cáo phù hợp.

## 1. Một truy vấn tổng hợp có thể đọc qua nhiều thời điểm

Giả sử hai hàng tài khoản có dữ liệu ban đầu:

| Tài khoản | Số dư ban đầu |
| --- | ---: |
| A | 600 |
| B | 400 |
| **Tổng** | **1.000** |

Giao dịch T1 chuyển 100 từ A sang B:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
~~~

Giao dịch báo cáo T2 chạy hai lần đọc:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 'A';

SELECT balance
FROM accounts
WHERE account_id = 'B';
~~~

Nếu T2 đọc A trước khi T1 chuyển tiền, sau đó T1 commit, rồi T2 đọc B, nó có thể thấy:

| Thứ tự | Thao tác | T2 nhìn thấy |
| --- | --- | ---: |
| 1 | T2 đọc A trước khi T1 cập nhật | A = 600 |
| 2 | T1 chuyển 100 và COMMIT | A = 500, B = 500 |
| 3 | T2 đọc B sau khi T1 commit | B = 500 |
| 4 | T2 cộng hai kết quả đã đọc | 600 + 500 = **1.100** |

Tại mọi thời điểm đã commit, tổng thực tế đều là 1.000:

- Trước T1: A = 600, B = 400.
- Sau T1: A = 500, B = 500.

Tổng 1.100 chỉ xuất hiện do T2 **đọc A ở trạng thái cũ, đọc B ở trạng thái mới**. Đây là điểm cốt lõi của read skew: mỗi lần đọc riêng lẻ có thể hợp lệ theo isolation level, nhưng tập kết quả đọc không cùng mô tả một trạng thái nhất quán.

## 2. Lịch thực thi minh họa read skew

Dùng ký hiệu:

- r2(A): T2 đọc số dư A.
- r2(B): T2 đọc số dư B.
- w1(A), w1(B): T1 ghi các số dư mới.
- c1: T1 commit thành công.

Một lịch có thể tạo read skew:

~~~text
T2: r2(A = 600) --------------------- r2(B = 500)
T1:            w1(A = 500) w1(B = 500) c1
~~~

Thứ tự cụ thể:

~~~text
S = r2(A)  w1(A)  w1(B)  c1  r2(B)
~~~

Ở READ COMMITTED, nếu mỗi câu SELECT có snapshot riêng, lịch này có thể được phép: lần đọc A thấy dữ liệu trước commit của T1, còn lần đọc B thấy dữ liệu sau commit. Không có dirty read; T2 không đọc dữ liệu chưa commit. Vấn đề là T2 **không có một snapshot thống nhất cho toàn bộ phép tính**.

~~~mermaid
sequenceDiagram
    participant T2 as T2 - Báo cáo
    participant DB as Cơ sở dữ liệu
    participant T1 as T1 - Chuyển tiền

    T2->>DB: SELECT A
    DB-->>T2: A = 600 (trước chuyển tiền)
    T1->>DB: UPDATE A = 500
    T1->>DB: UPDATE B = 500
    T1->>DB: COMMIT
    T2->>DB: SELECT B
    DB-->>T2: B = 500 (sau chuyển tiền)
    Note over T2: Tổng ghép = 1.100<br/>không tồn tại tại một thời điểm đã commit
~~~

**Không cần dirty read để xảy ra read skew.** T2 chỉ đọc các giá trị đã commit, nhưng các giá trị đó đến từ hai thời điểm khác nhau.

## 3. Read skew khác dirty read và non-repeatable read

Các bất thường đọc có liên hệ nhưng không đồng nhất.

| Hiện tượng | Mô tả | Ví dụ |
| --- | --- | --- |
| **Dirty read** | Đọc thay đổi chưa commit của giao dịch khác | T2 đọc A = 500 trong khi T1 ghi 500 nhưng chưa commit; T1 sau đó rollback |
| **Non-repeatable read** | Cùng một hàng được đọc hai lần trong một transaction và nhận giá trị khác do giao dịch khác commit ở giữa | T2 đọc A = 600, T1 commit A = 500, T2 đọc lại A = 500 |
| **Read skew / inconsistent analysis** | Một phép tính đọc nhiều hàng hoặc nhiều phần dữ liệu ở những phiên bản khác nhau, tạo ra tổ hợp không nhất quán | T2 đọc A = 600 trước chuyển tiền và B = 500 sau chuyển tiền, tổng thành 1.100 |
| **Phantom read** | Cùng một điều kiện truy vấn được thực hiện lại và tập hàng phù hợp thay đổi do giao dịch khác insert/delete/update predicate | T2 đếm đơn hàng status='PAID', T1 chuyển trạng thái một đơn, T2 đếm lại và số lượng khác |
| **Lost update** | Một cập nhật ghi đè kết quả cập nhật khác dựa trên dữ liệu cũ | Hai giao dịch cùng đọc tồn kho 10 rồi ghi các giá trị mới không phối hợp |

Read skew thường liên quan tới nhiều hàng, nhiều truy vấn hoặc nhiều phần của một phép tổng hợp. Non-repeatable read có thể chỉ liên quan một hàng. Một transaction có thể gặp cả hai dạng tùy cách ứng dụng đọc.

### Read skew không phải là tổng hợp sai do dữ liệu đầu vào sai

Giả sử hai hàng được cập nhật bởi những nghiệp vụ độc lập; tổng của chúng có thể thực sự thay đổi theo thời gian. Một báo cáo đọc các hàng ở những thời điểm khác nhau chưa chắc sai trong mọi ứng dụng. Vấn đề xuất hiện khi nghiệp vụ yêu cầu kết quả phải biểu diễn **một trạng thái nhất quán tại cùng một thời điểm**, chẳng hạn tổng tiền giữa hai tài khoản phải bảo toàn.

Vì thế, cần xác định bất biến nghiệp vụ nào mà báo cáo phải giữ. DBMS không thể tự suy ra mọi quan hệ logic giữa các hàng.

## 4. Ví dụ: tổng tồn kho khi hàng được chuyển giữa kho

Một hệ thống quản lý có hai kho:

| Kho | Số lượng lúc đầu |
| --- | ---: |
| Kho A | 80 |
| Kho B | 20 |
| **Tổng** | **100** |

T1 chuyển 10 sản phẩm từ kho A sang kho B:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 10
WHERE warehouse_id = 'A' AND sku = 'P-01';

UPDATE inventory
SET quantity = quantity + 10
WHERE warehouse_id = 'B' AND sku = 'P-01';

COMMIT;
~~~

T2 chạy báo cáo tổng tồn kho bằng cách truy vấn hai kho riêng:

~~~sql
SELECT quantity
FROM inventory
WHERE warehouse_id = 'A' AND sku = 'P-01';

SELECT quantity
FROM inventory
WHERE warehouse_id = 'B' AND sku = 'P-01';
~~~

Nếu T2 đọc kho A trước chuyển, nhận 80; rồi T1 commit chuyển kho; T2 đọc kho B sau chuyển, nhận 30. Báo cáo tính tổng 110 trong khi tổng đã commit luôn là 100.

~~~text
Trước giao dịch: A = 80, B = 20, tổng = 100

T2 đọc A = 80
T1 chuyển 10:  A = 70, B = 30, COMMIT
T2 đọc B = 30

Báo cáo T2: 80 + 30 = 110
Trạng thái thật sau commit: 70 + 30 = 100
~~~

Nếu báo cáo dùng một câu SELECT SUM(quantity) ... duy nhất, kết quả tùy vào cơ chế snapshot của DBMS và isolation level. Trong nhiều hệ thống MVCC, một câu lệnh đọc ở READ COMMITTED dùng một snapshot nhất quán tại thời điểm câu lệnh bắt đầu, nên kết quả tổng hợp của riêng câu lệnh đó không ghép phiên bản từ các commit xảy ra giữa lúc quét. Nhưng nếu ứng dụng chia báo cáo thành nhiều câu lệnh, mỗi câu lệnh có snapshot khác nhau, read skew vẫn có thể xuất hiện.

## 5. Tại sao READ COMMITTED có thể cho read skew?

READ COMMITTED thường đảm bảo mỗi câu lệnh chỉ đọc dữ liệu đã commit. Tuy nhiên, ở nhiều DBMS triển khai READ COMMITTED bằng snapshot theo từng câu lệnh, **hai câu SELECT khác nhau trong cùng transaction có thể nhìn thấy hai snapshot khác nhau**.

~~~text
Transaction T2 (READ COMMITTED)

SELECT A;  -- snapshot S1, trước commit T1
           -- đọc A = 600

                 T1 commit chuyển A/B

SELECT B;  -- snapshot S2, sau commit T1
           -- đọc B = 500
~~~

Mỗi câu lệnh không đọc dữ liệu bẩn. Nhưng T2 không nhất thiết có snapshot cố định xuyên suốt transaction.

Cần tránh khái quát quá mức: cách định nghĩa snapshot, khóa đọc và hành vi READ COMMITTED khác nhau theo DBMS. Một số hệ thống triển khai mức này bằng khóa và có thể cho lịch khác. Muốn biết một hệ quản trị cụ thể có thể tạo read skew theo lịch nào, phải xem tài liệu và isolation semantics của nó.

### Một câu SELECT hay nhiều câu SELECT?

~~~sql
-- Một câu lệnh tổng hợp:
SELECT SUM(balance)
FROM accounts
WHERE account_id IN ('A', 'B');
~~~

~~~sql
-- Hai câu lệnh độc lập:
SELECT balance FROM accounts WHERE account_id = 'A';
SELECT balance FROM accounts WHERE account_id = 'B';
~~~

Ở DBMS dùng snapshot nhất quán cho mỗi statement, truy vấn đầu có thể tính trên cùng một snapshot. Truy vấn thứ hai và thứ ba có thể bắt đầu ở hai thời điểm và nhìn thấy dữ liệu khác nhau.

Tuy nhiên, **một câu SQL không phải trong mọi DBMS và mọi engine đều đồng nghĩa với một snapshot theo cùng định nghĩa**. Cần kiểm tra semantics của DBMS đang dùng, đặc biệt khi truy vấn gọi hàm, đọc dữ liệu ngoài DB, dùng linked server hoặc kết hợp nhiều nguồn.

## 6. Dùng snapshot ổn định cho toàn bộ báo cáo

Một cách giải quyết phổ biến là đảm bảo tất cả truy vấn trong báo cáo cùng nhìn một **snapshot giao dịch**. Với DBMS hỗ trợ snapshot isolation hoặc repeatable snapshot, T2 có thể đọc A và B từ cùng trạng thái dữ liệu.

Với PostgreSQL, một transaction REPEATABLE READ dùng cùng snapshot cho các câu lệnh đọc thông thường trong transaction:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT balance
FROM accounts
WHERE account_id = 'A';

SELECT balance
FROM accounts
WHERE account_id = 'B';

COMMIT;
~~~

Nếu snapshot được tạo trước khi T1 commit, cả hai truy vấn sẽ nhìn trạng thái trước chuyển tiền: A = 600, B = 400. Tổng là 1.000. Nếu snapshot được tạo sau khi T1 commit, cả hai nhìn trạng thái mới: A = 500, B = 500. Dù thời điểm nào, báo cáo dùng một ảnh chụp nhất quán.

~~~mermaid
sequenceDiagram
    participant T2 as T2 - Báo cáo
    participant DB as PostgreSQL
    participant T1 as T1 - Chuyển tiền

    T2->>DB: BEGIN REPEATABLE READ
    T2->>DB: SELECT A (snapshot S)
    DB-->>T2: A = 600
    T1->>DB: Chuyển A/B và COMMIT
    T2->>DB: SELECT B (vẫn snapshot S)
    DB-->>T2: B = 400
    Note over T2: Tổng = 1.000 trên snapshot S
    T2->>DB: COMMIT
~~~

Thời điểm snapshot thực sự được xác lập phụ thuộc DBMS và khi transaction thực hiện truy vấn đầu tiên hoặc bắt đầu theo quy tắc cụ thể. Ví dụ trên giả định T2 đã lấy snapshot trước khi T1 commit. Nếu snapshot được tạo sau commit, T2 sẽ nhìn cả A = 500 và B = 500.

### Repeatable Read có ý nghĩa gì ở đây?

Trong mô hình snapshot của PostgreSQL, REPEATABLE READ ngăn các câu lệnh đọc trong cùng transaction thay đổi snapshot giữa chừng. PostgreSQL còn có các quy tắc xử lý cập nhật/xung đột riêng. Không nên suy rằng REPEATABLE READ ở mọi DBMS đều cung cấp cùng một tập bảo đảm.

Ví dụ, tên REPEATABLE READ của một hệ quản trị có thể chủ yếu nói về khóa và khả năng đọc lại hàng, trong khi hệ khác dùng MVCC snapshot. Phantom và write skew cần được phân tích theo semantics cụ thể.

## 7. SERIALIZABLE và yêu cầu nhất quán mạnh hơn

Nếu báo cáo chỉ đọc, một transaction snapshot ổn định thường đã đáp ứng yêu cầu đọc nhất quán. Nhưng khi giao dịch **đọc dữ liệu để quyết định có thực hiện cập nhật hay không**, snapshot ổn định riêng lẻ chưa chắc đủ để duy trì mọi bất biến nghiệp vụ trước các transaction đồng thời.

Ví dụ quy tắc: trong một nhóm trực, luôn phải có ít nhất một nhân viên trực. Ban đầu Alice và Bình đều trực. Hai giao dịch đồng thời đọc trạng thái của cả hai rồi mỗi giao dịch cho một người nghỉ:

~~~text
T1 đọc Alice=ON, Bình=ON
T2 đọc Alice=ON, Bình=ON

T1 đặt Alice=OFF
T2 đặt Bình=OFF

T1 COMMIT
T2 COMMIT
~~~

Kết quả cuối Alice=OFF và Bình=OFF, vi phạm quy tắc. Hai giao dịch sửa hai hàng khác nhau nên có thể không xung đột ghi trực tiếp. Đây là ví dụ kinh điển về **write skew** trong những hệ thống cho phép lịch này dưới snapshot isolation.

Read skew và write skew không giống nhau:

- **Read skew:** một transaction đọc các phần dữ liệu ở những snapshot không thống nhất.
- **Write skew:** các transaction dùng những lần đọc nhất quán nhưng cập nhật những phần khác nhau, khiến bất biến tổng thể bị vi phạm.

SERIALIZABLE hướng tới bảo đảm lịch tương đương thực thi tuần tự, theo cơ chế của DBMS. Hệ thống có thể chặn, chờ hoặc hủy một transaction khi phát hiện lịch đồng thời không hợp lệ; ứng dụng phải sẵn sàng retry transaction được báo lỗi serialization khi điều đó an toàn.

Với PostgreSQL:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Đọc các hàng và thực hiện logic nghiệp vụ.
-- Các thao tác ghi tiếp theo chịu kiểm tra serializable.

COMMIT;
~~~

PostgreSQL sử dụng Serializable Snapshot Isolation (SSI) để phát hiện một số chu trình phụ thuộc nguy hiểm; ứng dụng có thể nhận lỗi serialization và cần thử lại toàn bộ giao dịch phù hợp. Đây là đặc tính triển khai của PostgreSQL, không phải mô tả thuật toán SERIALIZABLE chung cho mọi DBMS.

## 8. Các lựa chọn xử lý read skew

Không có một lựa chọn tối ưu cho mọi ứng dụng. Quyết định phụ thuộc báo cáo có cần đúng tại một thời điểm không, dữ liệu được cập nhật thường xuyên đến đâu và chi phí giữ snapshot hoặc khóa.

| Cách tiếp cận | Ý tưởng | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| **Một câu truy vấn tổng hợp** | DBMS thực hiện phép tổng hợp trong một statement | Có thể biểu diễn phép tính bằng SQL và DBMS cung cấp statement snapshot thích hợp | Truy vấn có thể phức tạp; phải xác minh semantics |
| **REPEATABLE READ / snapshot transaction** | Nhiều SELECT dùng một snapshot giao dịch | Báo cáo gồm nhiều truy vấn cần cùng một trạng thái | Snapshot lâu có thể giữ phiên bản cũ, ảnh hưởng dọn dẹp và tài nguyên |
| **SERIALIZABLE** | Yêu cầu kết quả tương đương lịch tuần tự | Logic đọc rồi quyết định ghi phải bảo toàn bất biến | Có thể tăng xung đột, chờ hoặc lỗi serialization; cần retry |
| **Khóa tường minh** | Khóa các hàng hoặc phạm vi liên quan trong thời gian tính toán | Dữ liệu và phạm vi khóa xác định được, cần ngăn cập nhật đồng thời | Có thể giảm concurrency, tăng deadlock; khóa đủ phạm vi rất quan trọng |
| **Bản chụp/bảng tổng hợp đã dựng** | Tính trước và công bố một bộ kết quả nhất quán | Báo cáo lớn, chấp nhận độ trễ cập nhật có kiểm soát | Cần quy trình cập nhật, freshness và phục hồi |
| **Một truy vấn trên replica hoặc kho phân tích** | Đọc từ nguồn chuyên phục vụ báo cáo | Tải báo cáo nặng và có thể chấp nhận độ trễ | Replica có thể lag; cần hiểu thời điểm dữ liệu được đồng bộ |

### Chọn một statement khi có thể

Nếu báo cáo là tổng, đếm hoặc thống kê có thể viết thành một câu SQL, đó thường là cách đơn giản giúp DBMS áp dụng một phạm vi snapshot của statement theo isolation semantics đang dùng:

~~~sql
SELECT
    SUM(balance) AS total_balance,
    COUNT(*) AS account_count
FROM accounts
WHERE status = 'ACTIVE';
~~~

Nên giữ các biểu thức liên quan trong cùng câu truy vấn nếu chúng phải biểu diễn cùng trạng thái. Khi cần nhiều truy vấn, hãy dùng transaction với snapshot phù hợp.

### Chọn khóa tường minh khi logic yêu cầu

Một số nghiệp vụ cần khóa dữ liệu trong lúc tính toán:

~~~sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id IN ('A', 'B')
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng xác minh và thực hiện thay đổi dựa trên
-- các hàng đã khóa theo semantics của DBMS.

COMMIT;
~~~

Đây là ví dụ khái niệm; cú pháp và phạm vi khóa phụ thuộc DBMS. Việc khóa phải bao phủ đủ những hàng/predicate cần thiết và theo một thứ tự nhất quán để giảm deadlock. FOR UPDATE trên hai hàng không tự động khóa mọi hàng mới có thể được insert thỏa một điều kiện tổng hợp.

## 9. Lưu ý khi triển khai bằng JDBC và Spring

Một báo cáo nhiều câu lệnh cần một transaction thực sự bao quanh các truy vấn. Nếu mỗi lần truy vấn lấy một connection riêng hoặc mỗi truy vấn tự commit, không có gì đảm bảo chúng cùng sử dụng snapshot.

Ví dụ JDBC với một connection:

~~~java
long readTotal(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        boolean oldAutoCommit = connection.getAutoCommit();
        int oldIsolation = connection.getTransactionIsolation();
        boolean transactionOpened = false;

        try {
            connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            connection.setReadOnly(true);
            connection.setAutoCommit(false);
            transactionOpened = true;

            long balanceA;
            long balanceB;

            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT balance FROM accounts WHERE account_id = ?")) {
                ps.setString(1, "A");
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Missing account A");
                    }
                    balanceA = rs.getLong(1);
                }
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT balance FROM accounts WHERE account_id = ?")) {
                ps.setString(1, "B");
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Missing account B");
                    }
                    balanceB = rs.getLong(1);
                }
            }

            connection.commit();
            transactionOpened = false;
            return balanceA + balanceB;
        } catch (SQLException | RuntimeException ex) {
            if (transactionOpened) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
            }
            throw ex;
        } finally {
            // Mã minh họa cần phối hợp với chính sách reset của connection pool.
            connection.setAutoCommit(oldAutoCommit);
            connection.setReadOnly(false);
            connection.setTransactionIsolation(oldIsolation);
        }
    }
}
~~~

Mã minh họa giả định DBMS/driver hỗ trợ REPEATABLE READ và read-only transaction, đồng thời connection được trả về ở trạng thái phù hợp. Trong ứng dụng thật, transaction manager và pool thường là nơi chịu trách nhiệm thiết lập/khôi phục trạng thái; không nên tự ý thay đổi thuộc tính trên connection đang do framework quản lý.

Với Spring, có thể đặt isolation ở phạm vi phương thức:

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.REPEATABLE_READ
)
public AccountSummary loadSummary() {
    // Các repository call phải tham gia cùng transaction.
    // Không tự mở connection độc lập ngoài transaction manager.
    return accountRepository.loadSummary();
}
~~~

Cần bảo đảm các lời gọi repository thật sự dùng transaction do Spring quản lý. Nếu một phương thức dùng REQUIRED tham gia transaction đã có sẵn, isolation khai báo ở bên trong không tự thay đổi transaction hiện hành. Nếu báo cáo chạy qua nhiều nguồn dữ liệu hoặc nhiều transaction manager, một annotation không tự tạo snapshot phân tán nhất quán cho tất cả.

### Giữ transaction báo cáo trong thời gian hợp lý

Snapshot dài có thể khiến DBMS phải giữ lại phiên bản dữ liệu cũ lâu hơn, làm tăng áp lực version cleanup, undo retention hoặc dung lượng lưu trữ tùy hệ quản trị. Truy vấn báo cáo lâu cũng có thể giữ tài nguyên và làm chậm các công việc khác.

Một số thực hành hữu ích:

- Tính toán trong một transaction đọc ngắn nhất có thể.
- Không gọi API bên ngoài, chờ người dùng hay thực hiện xử lý chậm trong khi giữ transaction mở.
- Chia nhỏ báo cáo chỉ khi chấp nhận rõ ràng rằng các phần có thể dùng snapshot/thời điểm khác nhau; hoặc dùng cơ chế snapshot/batch nhất quán.
- Theo dõi transaction tuổi cao, snapshot cũ, lock wait và hiệu năng truy vấn.

## 10. Báo cáo trên replica và dữ liệu nhiều nguồn

Read skew cũng có thể xuất hiện khi báo cáo đọc từ các replica khác nhau hoặc từ nhiều hệ thống được đồng bộ bất đồng bộ.

Ví dụ một replica nhận cập nhật A trước, một replica khác nhận cập nhật B sau. Nếu ứng dụng đọc A từ replica thứ nhất và B từ replica thứ hai, kết quả có thể ghép dữ liệu từ những mốc replication khác nhau.

~~~text
Primary commit giao dịch chuyển A -> B
           |
           +---- Replica R1 đã áp dụng thay đổi
           |
           +---- Replica R2 vẫn còn ở trạng thái trước

Báo cáo đọc A từ R2 và B từ R1
           |
           +---- Có thể ghép hai phiên bản không cùng một mốc
~~~

Ngay cả khi mỗi replica nhất quán nội bộ, việc đọc từ nhiều replica hoặc nhiều dịch vụ có thể không tạo ra một snapshot chung. Cần xem khả năng consistent read, read-your-writes, watermark/LSN, snapshot timestamp hoặc cơ chế phối hợp do nền tảng cung cấp.

Một báo cáo chấp nhận dữ liệu trễ có thể dùng replica chuyên dụng để giảm tải primary. Nhưng cần nêu rõ thời điểm dữ liệu và độ trễ đồng bộ để người dùng không nhầm nó là tổng số liệu tức thời đã nhất quán.

## 11. Cách điều tra một báo cáo có số liệu bất thường

Khi thấy tổng tiền hoặc tồn kho bất hợp lý, hãy kiểm tra theo hướng thời gian và phạm vi snapshot:

1. Xác định báo cáo dùng **một câu SQL hay nhiều câu SQL**.
2. Xác định các câu lệnh có nằm trong **cùng một transaction và cùng connection** không.
3. Kiểm tra isolation level thực sự của transaction tại thời điểm chạy, không chỉ annotation hoặc cấu hình mặc định.
4. Ghi thời điểm bắt đầu truy vấn, bắt đầu transaction, các lần đọc, commit của giao dịch ghi và commit của báo cáo.
5. Xác định mỗi giá trị được đọc từ **phiên bản nào** hoặc từ replica nào.
6. Đối chiếu tổng với bất biến nghiệp vụ ở những mốc dữ liệu đã commit.
7. Nếu cần sửa, chọn statement snapshot, transaction snapshot, khóa hoặc mô hình báo cáo phù hợp với semantics cần có.
8. Tái hiện bằng hai transaction đồng thời và kiểm tra trên đúng DBMS, driver, storage engine, pool và transaction manager.

Ví dụ log hữu ích nên có mã request, mã transaction, connection/session id khi khả dụng, thời điểm câu lệnh bắt đầu/kết thúc và nguồn đọc. Không ghi thông tin nhạy cảm của dữ liệu vào log chỉ để phân tích concurrency.

Một ảnh chụp số liệu do báo cáo tạo ra nên kèm thời điểm hoặc watermark dữ liệu. Điều đó giúp giải thích vì sao hai lần chạy cùng câu hỏi có thể trả kết quả khác nhau khi dữ liệu tiếp tục được cập nhật.

## 12. Tự kiểm tra

**Câu 1.** T2 đọc A = 600 trước khi T1 chuyển tiền, rồi đọc B = 500 sau khi T1 commit. T2 có đọc dirty data không?

**Trả lời:** Không. T2 đọc các giá trị đã commit nhưng từ hai thời điểm khác nhau. Đây là read skew.

**Câu 2.** READ COMMITTED có luôn bảo đảm hai câu SELECT trong một transaction thấy cùng snapshot không?

**Trả lời:** Không. Trong nhiều hệ thống MVCC, READ COMMITTED cấp snapshot theo từng câu lệnh, nên hai SELECT có thể thấy hai trạng thái đã commit khác nhau.

**Câu 3.** Một câu SELECT SUM(balance) có thể giảm nguy cơ read skew thế nào?

**Trả lời:** Nếu DBMS cung cấp snapshot nhất quán cho statement, toàn bộ phép tổng hợp dùng cùng snapshot thay vì lấy từng phần ở các câu lệnh khác thời điểm. Cần xác minh semantics của DBMS.

**Câu 4.** Transaction REPEATABLE READ đọc A và B trong cùng snapshot nhưng có bảo đảm mọi bất biến nghiệp vụ trước giao dịch đồng thời không?

**Trả lời:** Không nhất thiết. Snapshot isolation có thể vẫn cho write skew khi các giao dịch đọc cùng dữ liệu nhưng ghi những hàng khác nhau. Một số nghiệp vụ cần SERIALIZABLE hoặc khóa/ràng buộc phù hợp.

**Câu 5.** Replica đã nhất quán nội bộ thì truy vấn từ hai replica có chắc tạo một snapshot toàn cục không?

**Trả lời:** Không. Hai replica có thể đang ở các mốc replication khác nhau. Cần một cơ chế đồng bộ snapshot hoặc watermark nếu báo cáo đòi hỏi trạng thái chung.

**Câu 6.** Vì sao gọi hai repository method trong cùng một phương thức Java chưa chắc đủ?

**Trả lời:** Cần bảo đảm chúng tham gia cùng một transaction được transaction manager quản lý và dùng nguồn dữ liệu/connection tương thích. Nếu mỗi lần gọi chạy transaction độc lập hoặc đọc từ replica khác nhau, snapshot có thể không giống nhau.

## 13. Ghi nhớ

**Read skew là vấn đề tính nhất quán của một tập dữ liệu được đọc qua nhiều thời điểm.** Mỗi câu SELECT có thể hoàn toàn hợp lệ, không hề đọc dữ liệu chưa commit, nhưng kết quả tổng hợp cuối cùng lại ghép các phiên bản không cùng tồn tại đồng thời.

Khi nghiệp vụ yêu cầu báo cáo phản ánh một thời điểm thống nhất, hãy ưu tiên một truy vấn tổng hợp trong snapshot statement phù hợp hoặc đặt toàn bộ truy vấn trong transaction có snapshot ổn định. Khi giao dịch còn dựa vào dữ liệu đọc để quyết định cập nhật, hãy xét thêm write skew và yêu cầu serializability.

Điều cần làm rõ trước khi lựa chọn isolation là **báo cáo cần nhất quán ở cấp câu lệnh, cấp transaction hay trên nhiều nguồn dữ liệu**. Phạm vi đó quyết định cơ chế DBMS có thể cung cấp và chi phí vận hành cần chấp nhận.
