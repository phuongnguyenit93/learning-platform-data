# Đọc dữ liệu chưa commit (dirty read)

Trong chương **Tính cô lập** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, ta tìm hiểu một lỗi xảy ra khi nhiều giao dịch cùng truy cập cơ sở dữ liệu: **đọc dữ liệu chưa commit**, hay *dirty read*. Đây là một trong những hiện tượng cơ bản cần nhận diện trước khi chọn mức cô lập cho tầng persistence của ứng dụng Java.

Một ứng dụng có thể thiết kế đúng lược đồ, truy vấn và chỉ mục nhưng vẫn đưa ra quyết định sai nếu đọc dữ liệu của giao dịch khác khi giao dịch ấy chưa hoàn tất. Hiểu dirty read giúp ta xác định ranh giới transaction, chọn mức cô lập phù hợp, xử lý lỗi kết nối và kiểm tra tính đúng đắn của các thao tác đồng thời.

## 1. Dirty read là gì?

**Dirty read xảy ra khi giao dịch B đọc một giá trị do giao dịch A ghi, trong lúc A vẫn chưa commit.** Giá trị này chưa trở thành kết quả được chấp nhận của A; A có thể tiếp tục sửa hoặc rollback, khiến B đã đọc một trạng thái không bao giờ được lưu chính thức.

Để xảy ra dirty read, thường có đủ ba yếu tố:

1. **A đã thay đổi dữ liệu** nhưng còn ở trạng thái chưa commit.
2. **B là một giao dịch khác** và có quyền nhìn thấy thay đổi chưa commit đó theo cơ chế cô lập của hệ quản trị.
3. **B thực hiện truy vấn** và nhận giá trị do A ghi trước khi A kết thúc.

Giả sử tài khoản số 101 đang có số dư **1.000.000 đồng**. Giao dịch A chuẩn bị chuyển 900.000 đồng ra khỏi tài khoản, nhưng cuối cùng bị hủy. Nếu giao dịch B đọc đúng lúc A mới trừ tiền, B có thể nhận **100.000 đồng** dù giá trị cuối cùng vẫn là **1.000.000 đồng**.

| Thời điểm | Giao dịch A | Giao dịch B | Giá trị đã commit |
| --- | --- | --- | --- |
| T0 | Chưa bắt đầu | Chưa bắt đầu | 1.000.000 |
| T1 | `BEGIN`; cập nhật số dư thành 100.000, **chưa commit** | | 1.000.000 |
| T2 | Giao dịch vẫn mở | Đọc số dư = **100.000** | 1.000.000 |
| T3 | `ROLLBACK`, hủy lần trừ tiền | | 1.000.000 |
| T4 | Đã kết thúc | Có thể đã từ chối giao dịch mới vì tưởng số dư thấp | 1.000.000 |

Ở T2, B đã đọc giá trị mà A **chưa cam kết giữ lại**. Đó chính là dirty read. Nếu B dùng giá trị này để gửi thông báo hết tiền, chặn một đơn hàng hoặc ghi sang dịch vụ khác thì tác động của quyết định sai có thể tiếp tục tồn tại dù A đã rollback.

```mermaid
sequenceDiagram
    participant A as Giao dịch A
    participant DB as Cơ sở dữ liệu
    participant B as Giao dịch B
    A->>DB: BEGIN; số dư = 100.000 (chưa commit)
    B->>DB: SELECT balance
    DB-->>B: 100.000 (dirty read nếu được phép)
    B->>B: Quyết định dựa trên giá trị tạm
    A->>DB: ROLLBACK
    Note over DB: Số dư đã commit vẫn là 1.000.000
```

**Chú ý:** Một giao dịch đọc lại chính các thay đổi chưa commit **của nó** là hành vi bình thường, không gọi là dirty read. Thuật ngữ này chỉ việc nhìn thấy thay đổi chưa commit **của giao dịch khác**.

Dirty read cũng không đòi hỏi A nhất thiết phải rollback. Ngay cả khi A sau đó commit, B vẫn đọc trước lúc A cam kết hoàn tất; A có thể thay đổi giá trị thêm lần nữa trước khi commit. Rollback chỉ là tình huống làm hậu quả của dirty read dễ nhận thấy nhất.

## 2. Tại sao dirty read nguy hiểm?

Rủi ro chính không chỉ là đọc một giá trị “cũ” hay “chậm cập nhật”, mà là **đọc trạng thái tạm thời chưa có hiệu lực**.

| Ngữ cảnh | Dữ liệu tạm mà B nhìn thấy | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Chuyển khoản | A đã tạm trừ tiền nhưng chưa commit | B từ chối thanh toán hợp lệ vì tưởng thiếu số dư. |
| Kho hàng | A tạm giảm tồn kho, sau đó rollback | B thông báo hết hàng hoặc hủy đơn không cần thiết. |
| Đặt phòng | A tạm chiếm phòng nhưng chưa xác nhận | B báo phòng đã kín dù giao dịch giữ chỗ thất bại. |
| Báo cáo | A tạm sửa doanh thu trước khi kiểm tra xong | B xuất báo cáo chứa doanh thu chưa được chấp nhận. |
| Điều phối quy trình | A tạm chuyển trạng thái đơn hàng | B phát sự kiện hoặc gọi API dựa trên trạng thái chưa hợp lệ. |

Một truy vấn chỉ đọc cũng có thể gây tác dụng phụ **ở tầng ứng dụng**: kết quả của nó kích hoạt quyết định, email, cache hoặc API. Rollback của A không có cơ chế tự động đảo ngược các hiệu ứng bên ngoài ấy.

Đọc “nhanh” với dữ liệu chưa commit không phải lựa chọn an toàn mặc định cho bảng điều khiển hay báo cáo. Ngoài giá trị tạm, một số hệ quản trị ở mức cô lập thấp còn có thể cho kết quả truy vấn không ổn định theo những cách khác. Chỉ đánh đổi tính đúng đắn khi có yêu cầu rõ ràng và đã xác minh hành vi cụ thể của hệ quản trị.

## 3. Thực hành dirty read với hai kết nối MySQL/InnoDB

Ví dụ này dùng **MySQL với bảng InnoDB** vì InnoDB có thể cho dirty read khi giao dịch đọc ở mức `READ UNCOMMITTED`. Cần hai kết nối độc lập đến **cùng một cơ sở dữ liệu**, chẳng hạn hai cửa sổ SQL. Gọi chúng là **phiên A** và **phiên B**.

### 3.1. Chuẩn bị dữ liệu

Chạy một lần, ngoài các giao dịch thử nghiệm:

```sql
CREATE TABLE demo_accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO demo_accounts (id, balance)
VALUES (101, 1000000.00);

SELECT id, balance FROM demo_accounts WHERE id = 101;
-- 101 | 1000000.00
```

Đây là bảng thử nghiệm riêng. Câu lệnh khởi tạo có thể cần đổi tên bảng hoặc chạy trong schema thực hành nếu đã tồn tại bảng cùng tên.

### 3.2. Phiên A: tạo một thay đổi chưa commit

Ở **phiên A**, chạy:

```sql
START TRANSACTION;

UPDATE demo_accounts
SET balance = 100000.00
WHERE id = 101;

SELECT balance FROM demo_accounts WHERE id = 101;
-- A thấy 100000.00 vì đang đọc thay đổi của chính mình.

-- DỪNG TẠI ĐÂY: chưa COMMIT hoặc ROLLBACK.
```

Phiên A đang giữ một thay đổi chưa commit. Số dư được lưu chính thức trước giao dịch này vẫn là 1.000.000 đồng.

### 3.3. Phiên B: cố ý đọc ở READ UNCOMMITTED

Trong lúc A vẫn chưa kết thúc, chạy ở **phiên B**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT balance FROM demo_accounts WHERE id = 101;
-- Với InnoDB ở READ UNCOMMITTED, có thể thấy 100000.00:
-- đây là giá trị A chưa commit.

COMMIT;
```

Phiên B đã đọc 100.000 đồng trong khi A chưa commit. Việc B commit một giao dịch chỉ đọc **không biến** thay đổi của A thành dữ liệu đã commit.

### 3.4. Phiên A rollback và kiểm tra lại

Quay lại **phiên A**:

```sql
ROLLBACK;
```

Sau đó, ở **phiên B**, truy vấn lại:

```sql
SELECT balance FROM demo_accounts WHERE id = 101;
-- 1000000.00
```

Giá trị 100.000 mà B đã nhận trước đó biến mất vì A rollback. Một hành động nghiệp vụ dựa trên lần đọc đầu tiên có thể đã sai và không thể tự đảo ngược.

**Điều kiện để tái hiện đúng:** Hai phiên phải là **hai kết nối riêng**; truy vấn B chạy **sau UPDATE nhưng trước ROLLBACK** của A; phiên B phải thật sự ở `READ UNCOMMITTED`; bảng sử dụng engine InnoDB. Nếu A commit quá sớm hoặc B dùng mức cô lập cao hơn thì kết quả có thể khác. Lệnh `SET SESSION` thay đổi cấu hình của phiên B cho cả các giao dịch tiếp theo trên kết nối này; không để cấu hình thực hành ấy vô tình rò rỉ sang phiên nghiệp vụ khác.

## 4. Ngăn dirty read bằng READ COMMITTED

Mức cô lập **READ COMMITTED** yêu cầu một giao dịch không đọc các thay đổi chưa commit của giao dịch khác. Trong ví dụ tài khoản, nếu A tạm sửa số dư thành 100.000 nhưng chưa commit, B phải đọc được trạng thái đã commit thích hợp, thay vì tin vào giá trị tạm ấy.

Hãy thực hiện lại thí nghiệm sau khi số dư đã về 1.000.000:

**Phiên A:**

```sql
START TRANSACTION;

UPDATE demo_accounts
SET balance = 100000.00
WHERE id = 101;

-- Giữ giao dịch mở; chưa commit.
```

**Phiên B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance FROM demo_accounts WHERE id = 101;
-- Với truy vấn SELECT thông thường trên MySQL/InnoDB:
-- đọc phiên bản đã commit trước đó: 1000000.00.

COMMIT;
```

**Phiên A** kết thúc bằng `ROLLBACK`.

Với truy vấn đọc nhất quán (*consistent read*) của InnoDB, phiên B nhận được phiên bản dữ liệu đã commit. Hệ quản trị khác có thể **chờ khóa** thay vì trả ngay phiên bản cũ, tùy cơ chế kiểm soát đồng thời và loại truy vấn; điểm chung của `READ COMMITTED` là **không cho thấy thay đổi chưa commit**.

Đây là một khác biệt quan trọng giữa việc đọc:

- **Dữ liệu đã commit nhưng có thể sắp thay đổi**: được phép ở `READ COMMITTED`.
- **Dữ liệu do giao dịch khác đang sửa nhưng chưa commit**: không được phép ở `READ COMMITTED`.

`READ COMMITTED` ngăn dirty read nhưng **không bảo đảm** rằng mọi lần đọc trong một giao dịch đều có cùng kết quả. Một giao dịch khác có thể commit giữa hai lần `SELECT`, khiến lần đọc thứ hai thấy giá trị mới. Đó là hiện tượng khác, sẽ được phân biệt ở phần tiếp theo.

## 5. Phân biệt dirty read với các lỗi đồng thời khác

| Hiện tượng | Điều kiện đặc trưng | Ví dụ |
| --- | --- | --- |
| **Dirty read** | Đọc giá trị do giao dịch **khác chưa commit** ghi. | B thấy số dư 100.000 khi A còn có thể rollback. |
| **Non-repeatable read** | Đọc lại **cùng hàng**, nhận giá trị khác vì giao dịch khác đã **commit** giữa hai lần đọc. | B đọc 1.000.000; A commit 800.000; B đọc lại 800.000. |
| **Phantom read** | Chạy lại truy vấn theo điều kiện, tập hàng phù hợp thay đổi vì giao dịch khác commit. | B đếm 10 đơn chờ xử lý; A thêm và commit một đơn; B đếm 11. |
| **Lost update** | Một phép ghi vô tình làm mất kết quả ghi của giao dịch khác. | Hai phiên đọc cùng số dư cũ rồi lần lượt ghi đè số dư được tính trong Java. |
| **Dirty write** | Một giao dịch ghi đè dữ liệu do giao dịch khác sửa nhưng chưa commit. | B ghi lên hàng mà A đang sửa trước khi A kết thúc. |

Hai ví dụ tối giản:

**Dirty read:**

```text
A: UPDATE số dư = 100.000  (chưa commit)
B: SELECT -> 100.000       (đã đọc giá trị tạm)
A: ROLLBACK                (số dư quay lại 1.000.000)
```

**Non-repeatable read:**

```text
B: SELECT -> 1.000.000
A: UPDATE số dư = 800.000; COMMIT
B: SELECT -> 800.000       (đã đọc thay đổi được commit)
```

Ở ví dụ thứ hai, B không đọc dữ liệu chưa commit. B chỉ thấy **hai trạng thái đã commit khác nhau** trong cùng một giao dịch. Vì vậy một giải pháp ngăn dirty read chưa chắc ngăn non-repeatable read, phantom hoặc lost update.

Trong các hệ quản trị giao dịch phổ biến, ghi đè thay đổi chưa commit của người khác thường bị ngăn bằng khóa ghi; khả năng xuất hiện một hiện tượng cụ thể luôn phụ thuộc hệ quản trị, engine, mức cô lập và kiểu truy vấn.

## 6. Mức cô lập nào cho phép dirty read?

Các mức cô lập SQL thường được nhắc đến như sau:

| Mức cô lập | Dirty read có được phép theo mô hình mức cô lập SQL? | Ghi chú thực hành |
| --- | --- | --- |
| `READ UNCOMMITTED` | **Có thể** | Mức yếu nhất; đọc giá trị chưa commit là hành vi có thể gặp ở một số hệ quản trị. |
| `READ COMMITTED` | **Không** | Mỗi lần đọc thông thường chỉ thấy dữ liệu đã commit theo quy tắc của hệ quản trị. |
| `REPEATABLE READ` | **Không** | Còn tăng bảo đảm cho việc đọc lặp lại; hiện thực giữa các CSDL khác nhau. |
| `SERIALIZABLE` | **Không** | Các giao dịch thành công có kết quả tương đương một lịch thực thi tuần tự. |

**“Cho phép” không có nghĩa là “luôn xảy ra”.** Cách một CSDL hiện thực mức cô lập có thể nghiêm ngặt hơn mức tối thiểu mà tên gọi gợi ra:

- **MySQL/InnoDB:** `READ UNCOMMITTED` cho phép đọc chưa commit ở truy vấn đọc thông thường. Ví dụ hai phiên ở phần 3 dùng đặc điểm này.
- **PostgreSQL:** chấp nhận cú pháp `READ UNCOMMITTED` nhưng xử lý như `READ COMMITTED`; ví dụ dirty read ở phần 3 **không thể tái hiện theo cùng cách** trên PostgreSQL.
- **SQL Server:** mức `READ UNCOMMITTED` và gợi ý `WITH (NOLOCK)` có thể đọc dữ liệu chưa commit. `NOLOCK` còn có những sai lệch quét dữ liệu khác, nên không coi đây là “cách đọc nhanh vô hại”.

Sự khác biệt không làm thay đổi định nghĩa dirty read; nó nhắc rằng tên mức cô lập không đủ để dự đoán mọi chi tiết thực thi. Khi cấu hình một ứng dụng, hãy xác nhận **hệ quản trị, phiên bản, engine, chế độ khóa/MVCC và cách tài xế JDBC ánh xạ mức cô lập**.

### Tại sao MVCC giúp tránh dirty read?

Nhiều CSDL dùng **Multi-Version Concurrency Control (MVCC)** để giữ nhiều phiên bản của dữ liệu. Một truy vấn chỉ được đọc những phiên bản phù hợp với quy tắc hiển thị của giao dịch; ở `READ COMMITTED`, nó không lấy phiên bản còn chưa commit của giao dịch khác.

```text
Hàng tài khoản 101
    ├─ Bản đã commit: balance = 1.000.000
    └─ Bản A đang sửa: balance = 100.000 (chưa commit)

B đọc ở READ COMMITTED → thấy bản đã commit phù hợp
B đọc ở READ UNCOMMITTED → có thể thấy bản A đang sửa (nếu CSDL hỗ trợ)
```

MVCC thường giúp truy vấn đọc không phải chờ khóa ghi cho mọi trường hợp. Tuy nhiên, truy vấn khóa như `SELECT ... FOR UPDATE`, lệnh `UPDATE`, các mức cô lập mạnh hơn hoặc các quyết định lập lịch nội bộ vẫn có thể chờ hoặc xung đột. Cần phân biệt **không dirty read** với **không bao giờ bị chặn bởi khóa**.

## 7. Cấu hình và sử dụng mức cô lập trong Java/JDBC

JDBC biểu diễn mức cô lập qua các hằng số của `java.sql.Connection`, chẳng hạn:

```java
Connection.TRANSACTION_READ_UNCOMMITTED
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
```

Đối với nghiệp vụ yêu cầu dữ liệu đáng tin cậy, có thể chủ động đặt `READ_COMMITTED` trước khi thực thi truy vấn. Ví dụ sau chỉ thực hiện **một lần đọc**; với một câu `SELECT` đơn lẻ, mỗi lần gọi là một giao dịch riêng khi auto-commit được bật theo mặc định:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountReader {
    private final DataSource dataSource;

    public AccountReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal readCommittedBalance(long accountId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Cấu hình trước khi thực thi câu lệnh hoặc bắt đầu transaction.
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);

            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT balance FROM demo_accounts WHERE id = ?")) {
                statement.setLong(1, accountId);

                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        throw new SQLException("Tai khoan khong ton tai");
                    }
                    return result.getBigDecimal("balance");
                }
            }
        }
    }
}
```

`setTransactionIsolation(...)` yêu cầu driver và CSDL hỗ trợ mức được chọn. Một số hệ thống có thể từ chối, ánh xạ hoặc hiện thực mức này khác nhau. Cần kiểm tra tài liệu và có thể dùng `DatabaseMetaData.supportsTransactionIsolationLevel(...)` để xác nhận khả năng hỗ trợ. Khi sử dụng **connection pool**, bảo đảm cấu hình isolation của kết nối được khôi phục theo quy ước của pool trước khi giao cho luồng nghiệp vụ khác.

Để kiểm tra mức hiện tại:

```java
int currentLevel = connection.getTransactionIsolation();
boolean supportsReadCommitted = connection.getMetaData()
        .supportsTransactionIsolationLevel(
                Connection.TRANSACTION_READ_COMMITTED);
```

Ở các ứng dụng dùng Spring, có thể khai báo `@Transactional(isolation = Isolation.READ_COMMITTED)` trên phương thức service có transaction do Spring quản lý. Hiệu lực phụ thuộc transaction manager, driver và việc lời gọi thật sự đi qua cơ chế quản lý transaction của Spring.

### READ COMMITTED giải quyết được vấn đề gì, và chưa giải quyết điều gì?

Trong ví dụ trên, `READ COMMITTED` đủ để B **không đọc số dư A đang sửa nhưng chưa commit**. Tuy vậy, khi thực hiện **đọc → tính toán → ghi** trong Java, hai giao dịch vẫn có thể cùng dựa trên một giá trị đã commit nhưng sau đó ghi đè kết quả của nhau nếu thiếu kiểm soát đồng thời.

Ví dụ nguy hiểm:

```text
B1: SELECT balance -> 1.000.000
B2: SELECT balance -> 1.000.000
B1: UPDATE balance = 900.000; COMMIT
B2: UPDATE balance = 800.000; COMMIT
```

Nếu B1 muốn trừ 100.000 và B2 muốn trừ 200.000, số dư đúng phải là **700.000**, không phải 800.000. Đây là bài toán *lost update*, khác với dirty read. Để bảo vệ thao tác trừ tiền, có thể dùng cập nhật có điều kiện ở ngay SQL:

```sql
UPDATE demo_accounts
SET balance = balance - 200000.00
WHERE id = 101
  AND balance >= 200000.00;
-- Ứng dụng phải kiểm tra số hàng được cập nhật = 1.
```

Với nghiệp vụ có bất biến trên nhiều hàng, có thể cần thêm ràng buộc, khóa, kiểm soát phiên bản hoặc mức cô lập mạnh hơn. **Ngăn dirty read là một yêu cầu của tính cô lập, nhưng chưa đủ để bảo đảm mọi bất biến nghiệp vụ khi có giao dịch đồng thời.**

## 8. Kiểm chứng và xử lý sự cố liên quan đến dirty read

Khi nghi ngờ hệ thống đang đọc giá trị chưa commit, cần thu thập thông tin giúp tái hiện chính xác:

1. Xác nhận **hai truy vấn thuộc hai transaction/kết nối độc lập**, không phải hai câu lệnh của cùng transaction.
2. Ghi nhận thời điểm `BEGIN`, `UPDATE`, `SELECT`, `COMMIT` hoặc `ROLLBACK`; lần đọc đáng nghi có xảy ra **trước commit** của giao dịch ghi không?
3. Kiểm tra mức cô lập thực tế của **kết nối đọc** và các hint riêng trên truy vấn; không chỉ dựa vào cấu hình mặc định của ứng dụng.
4. Kiểm tra loại CSDL và cơ chế truy cập dữ liệu (InnoDB, MVCC, khóa, query hint) để biết `READ UNCOMMITTED` có cho dirty read thật hay không.
5. Tái hiện trên dữ liệu thử nghiệm với giao dịch ghi được giữ mở, rồi rollback; so sánh kết quả ở `READ UNCOMMITTED` và `READ COMMITTED`.
6. Nếu đã có quyết định nghiệp vụ dựa trên dữ liệu tạm, truy dấu tác động tiếp theo: cache, thông báo, đơn hàng hoặc API bên ngoài.

**Không nên diễn giải mọi kết quả “khác mong đợi” là dirty read.** Nếu A đã commit rồi B mới đọc, đó không phải dirty read; nếu B đọc lại sau một commit mới và thấy giá trị khác, có thể là non-repeatable read. Nếu ứng dụng đọc từ replica bất đồng bộ và thấy dữ liệu cũ, đó thường là vấn đề độ trễ sao chép, cũng không phải dirty read theo định nghĩa trên.

### Những lỗi thiết kế thường gặp

- Tạm thời hạ isolation xuống `READ UNCOMMITTED` hoặc thêm `NOLOCK` chỉ để xử lý chậm truy vấn mà chưa đánh giá dữ liệu nghiệp vụ cần chính xác đến mức nào.
- Không kiểm soát isolation của kết nối được lấy từ pool; một thay đổi cấu hình ở chỗ này có thể ảnh hưởng chỗ khác.
- Hiểu sai rằng `READ COMMITTED` đảm bảo mọi lần đọc trong cùng transaction đều giống nhau.
- Gửi email hoặc gọi API dựa trên dữ liệu tạm rồi tin rằng rollback một transaction khác sẽ tự đảo ngược hành động đó.
- Viết kiểm thử một kết nối duy nhất rồi kết luận ứng dụng không gặp dirty read khi có nhiều phiên đồng thời.

## 9. Tự kiểm tra mức độ hiểu bài

**Tình huống 1:** A cập nhật điểm thưởng của khách hàng từ 50 thành 100 nhưng chưa commit. B đọc 100, gửi thông báo “đã đủ điểm đổi quà”. A rollback, điểm về 50. B gặp hiện tượng gì?

Đó là **dirty read**: B nhìn thấy kết quả chưa commit của A, rồi dùng giá trị ấy để tạo hiệu ứng bên ngoài. Chuyển truy vấn đọc sang mức ngăn dirty read và kiểm soát thời điểm gửi thông báo có thể tránh tình huống này.

**Tình huống 2:** B đọc 50 điểm. A cập nhật thành 100 và commit. B đọc lại 100 trong cùng transaction. Đây có phải dirty read?

**Không.** B chỉ đọc các trạng thái đã commit; đây là ví dụ của **non-repeatable read** nếu mức cô lập và cơ chế của CSDL cho phép.

**Tình huống 3:** Chương trình Java chạy PostgreSQL và đặt `Connection.TRANSACTION_READ_UNCOMMITTED`. Có thể mặc định kỳ vọng tái hiện dirty read như MySQL/InnoDB không?

**Không.** PostgreSQL xử lý mức đó như `READ COMMITTED`, do vậy không cho dirty read theo ví dụ này.

**Tình huống 4:** Một giao dịch đọc được chính giá trị mà nó vừa `UPDATE` trước khi commit. Đó có phải dirty read?

**Không.** Một transaction đọc thay đổi của chính mình là bình thường. Dirty read liên quan đến **giao dịch khác**.

**Tình huống 5:** Đặt tất cả truy vấn ở `READ COMMITTED` có đủ để giải quyết mọi sai lệch tiền trong nghiệp vụ chuyển khoản không?

**Không.** Mức này bảo vệ khỏi dirty read; luồng chuyển khoản còn cần transaction nguyên tử, ràng buộc, thao tác cập nhật có điều kiện hoặc các cơ chế đồng thời phù hợp.

## 10. Ghi nhớ khi thiết kế tầng persistence

Khi một giao dịch chưa commit, giá trị nó vừa ghi vẫn là **trạng thái tạm**. Nếu giao dịch khác đọc trạng thái ấy và hành động dựa vào nó, hệ thống có thể đưa ra quyết định dựa trên dữ liệu chưa từng tồn tại như một kết quả giao dịch hợp lệ.

Vì vậy, với truy vấn nghiệp vụ Java cần dữ liệu đáng tin cậy, hãy kiểm tra isolation thực tế, tránh đọc chưa commit và xây các kiểm tra đồng thời phù hợp với bất biến cần bảo vệ. `READ COMMITTED` là một biện pháp phổ biến để **ngăn dirty read**, trong khi những vấn đề như lost update, phantom và write skew cần được đánh giá riêng.
