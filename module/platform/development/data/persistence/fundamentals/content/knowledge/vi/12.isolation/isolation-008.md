# Mức READ COMMITTED và thay đổi giữa các lần đọc

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Diễn giải ý nghĩa của mức cô lập **READ COMMITTED** trong giao dịch cơ sở dữ liệu.
- Giải thích vì sao hai lần `SELECT` trong **cùng một giao dịch** có thể trả kết quả khác nhau khi một giao dịch khác đã `COMMIT`.
- Phân biệt **dirty read**, **non-repeatable read**, **phantom read** và sai lệch khi ghép kết quả của nhiều lần đọc.
- Tái hiện hiện tượng bằng hai phiên PostgreSQL, phân tích thứ tự thao tác và xác định phần nào là cam kết chung, phần nào phụ thuộc hệ quản trị.
- Lựa chọn cách xử lý trong Java/JDBC: đọc trong một câu SQL, nâng mức cô lập khi cần, khóa hàng, cập nhật nguyên tử hoặc kiểm soát phiên bản.

Bài thuộc chương **Tính cô lập** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Khi thiết kế ranh giới persistence cho Java, cần hiểu không chỉ lúc ghi dữ liệu mà cả **những phiên bản dữ liệu** mà một giao dịch được phép nhìn thấy. Quyết định này ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ, kiểm soát đồng thời, độ trễ, khả năng retry và vận hành hệ thống.

## 1. READ COMMITTED là gì?

**READ COMMITTED** là một mức cô lập giao dịch trong đó một thao tác đọc không được quan sát những thay đổi **chưa được commit** từ giao dịch khác. Nói cách khác, nó ngăn **dirty read**: một giao dịch không thấy dữ liệu tạm của giao dịch khác nếu giao dịch kia cuối cùng `ROLLBACK`.

Tuy nhiên, READ COMMITTED **không cam kết rằng dữ liệu đã đọc lần thứ nhất sẽ giữ nguyên ở lần đọc thứ hai**, dù hai lần đọc nằm trong cùng giao dịch. Nếu giao dịch khác commit một thay đổi ở giữa, lần đọc sau có thể thấy giá trị mới.

Trong **PostgreSQL**, với những câu `SELECT` thông thường, READ COMMITTED dùng một ảnh chụp dữ liệu (*snapshot*) mới ở đầu **mỗi câu lệnh**. Ảnh chụp đó xác định những phiên bản hàng được nhìn thấy bởi câu lệnh; một `SELECT` bắt đầu sau `COMMIT` của giao dịch khác có thể thấy thay đổi mới.

Ba ý cần ghi nhớ:

1. **Chưa commit** ở giao dịch khác: `SELECT` thông thường không thấy thay đổi đó.
2. **Đã commit trước khi `SELECT` kế tiếp bắt đầu**: lần `SELECT` mới trong PostgreSQL READ COMMITTED có thể thấy thay đổi.
3. **Chính giao dịch đang đọc tự sửa dữ liệu**: các lệnh tiếp theo của giao dịch thấy thay đổi do chính nó thực hiện, dù chưa commit cho các giao dịch khác.

Đừng hiểu “committed” là “chốt trạng thái cho cả giao dịch”. Ở mức READ COMMITTED, tính nhìn thấy của các phiên bản dữ liệu có thể được đánh giá lại theo từng câu lệnh.

### 1.1. Phân biệt ba thời điểm

~~~text
Thời gian  ----->

Giao dịch A: BEGIN ---- SELECT #1 ---------------- SELECT #2 ---- COMMIT
                            |                          |
                         thấy 1000                  thấy 1200
                            |                          |
Giao dịch B:         BEGIN ---- UPDATE 1200 ---- COMMIT
                                          |
                               thay đổi mới được công bố
~~~

Sơ đồ minh họa tình huống PostgreSQL: `SELECT #1` bắt đầu trước khi B commit; `SELECT #2` bắt đầu sau khi B commit. Chính việc mở ảnh chụp mới ở câu lệnh thứ hai giải thích sự khác biệt.

**Lưu ý về phạm vi:** SQL chuẩn mô tả mức READ COMMITTED qua những hiện tượng cô lập được phép hoặc ngăn chặn; chi tiết snapshot và locking khác nhau giữa DBMS. Bài sử dụng PostgreSQL làm môi trường thực hành chính, sau đó nêu những khác biệt cần kiểm chứng ở engine khác.

## 2. Thực hành: cùng một hàng nhưng hai lần đọc khác nhau

Thực hiện thí nghiệm trong **cơ sở dữ liệu thử nghiệm** với hai kết nối độc lập, gọi là **Phiên A** và **Phiên B**. Các câu lệnh dưới đây viết cho PostgreSQL.

### 2.1. Chuẩn bị dữ liệu

Chạy một lần, trước khi mở hai giao dịch:

~~~sql
CREATE TABLE rc_demo_accounts (
    id       BIGINT PRIMARY KEY,
    balance  NUMERIC(12, 2) NOT NULL CHECK (balance >= 0),
    version  BIGINT NOT NULL DEFAULT 0
);

INSERT INTO rc_demo_accounts (id, balance)
VALUES (101, 1000.00);
~~~

Khởi đầu, tài khoản `id = 101` có `balance = 1000.00`. Cột `version` dành cho ví dụ kiểm soát đồng thời ở phần sau.

### 2.2. Phiên A bắt đầu và đọc lần thứ nhất

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM rc_demo_accounts
WHERE id = 101;
-- Kết quả mong đợi: 1000.00
~~~

**Chưa commit hoặc rollback Phiên A.** Phiên A đang ở trong một transaction mở.

### 2.3. Phiên B cập nhật nhưng chưa commit

Ở kết nối thứ hai:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE rc_demo_accounts
SET balance = 1200.00,
    version = version + 1
WHERE id = 101;

-- Tạm dừng tại đây: chưa COMMIT.
~~~

Phiên B đã thực hiện cập nhật trong giao dịch của nó. Với một câu `SELECT` thông thường ở Phiên A, dữ liệu mới của B vẫn **chưa được nhìn thấy**.

Quay về Phiên A, có thể đọc thêm một lần trước lúc B commit:

~~~sql
SELECT balance
FROM rc_demo_accounts
WHERE id = 101;
-- Vẫn là 1000.00
~~~

Đây là biểu hiện của việc **không đọc dữ liệu chưa commit** từ phiên khác.

### 2.4. Phiên B commit; Phiên A đọc lại

Ở Phiên B:

~~~sql
COMMIT;
~~~

Quay về Phiên A, **vẫn trong cùng giao dịch ban đầu**:

~~~sql
SELECT balance
FROM rc_demo_accounts
WHERE id = 101;
-- Bây giờ là 1200.00

COMMIT;
~~~

Phiên A đã đọc `1000.00`, sau đó đọc `1200.00` từ **cùng một hàng** mà không tự sửa nó. Đây là **non-repeatable read** (*đọc không lặp lại*).

| Thời điểm | Phiên A | Phiên B | Giá trị A đọc |
| --- | --- | --- | --- |
| T1 | BEGIN READ COMMITTED; SELECT | Chưa làm gì | 1000.00 |
| T2 | SELECT lần nữa | UPDATE chưa COMMIT | 1000.00 |
| T3 | Chờ | COMMIT bản cập nhật 1200.00 | — |
| T4 | SELECT lần tiếp theo | Đã kết thúc | 1200.00 |

Nếu Phiên B `ROLLBACK` thay vì `COMMIT`, các lần `SELECT` ở A sẽ không thấy `1200.00` từ thay đổi đó. Muốn chạy lại thí nghiệm từ đầu, khôi phục dữ liệu mẫu trong một giao dịch riêng sau khi cả hai phiên đã kết thúc:

~~~sql
UPDATE rc_demo_accounts
SET balance = 1000.00,
    version = 0
WHERE id = 101;
~~~

Không chạy bước reset khi giao dịch đang thử nghiệm còn mở.

## 3. Một câu SELECT có khác hai câu SELECT không?

Trong PostgreSQL READ COMMITTED, **mỗi `SELECT` thông thường** thấy một snapshot tính ở đầu câu lệnh. Vì vậy:

- Câu `SELECT` đầu tiên bắt đầu trước khi Phiên B commit sẽ không đột ngột thấy phiên bản mới chỉ vì B commit khi câu lệnh đó đang chạy.
- Câu `SELECT` tiếp theo, bắt đầu sau khi B commit, có thể thấy phiên bản mới.
- `BEGIN` không tự cố định snapshot cho toàn bộ transaction ở mức READ COMMITTED.

Ví dụ, thay vì hai truy vấn tách rời:

~~~sql
SELECT balance
FROM rc_demo_accounts
WHERE id = 101;

-- Một giao dịch khác có thể COMMIT ở đây.

SELECT version
FROM rc_demo_accounts
WHERE id = 101;
~~~

có thể đọc hai thuộc tính cần sử dụng cùng nhau trong **một** câu truy vấn:

~~~sql
SELECT balance, version
FROM rc_demo_accounts
WHERE id = 101;
~~~

Trong PostgreSQL, hai giá trị ở truy vấn thứ hai được lấy theo cùng ảnh chụp của câu `SELECT` đó. Cách này loại bỏ khoảng xen giữa **hai statement** ở ví dụ nhưng chưa đủ cho những nghiệp vụ phải thực hiện **nhiều câu lệnh ghi và đọc** trong một giao dịch.

Một snapshot nhất quán cho một `SELECT` không có nghĩa nó sẽ thấy mọi giao dịch commit trong lúc câu SQL đang thực thi. Đặc biệt, câu lệnh thay đổi dữ liệu và các truy vấn khóa như `SELECT FOR UPDATE` có thể gặp quy tắc chờ/đánh giá lại hàng khác với `SELECT` thông thường. Không suy rộng diễn giải snapshot của SELECT sang mọi loại lệnh SQL.

## 4. READ COMMITTED cho phép những hiện tượng gì?

### 4.1. Dirty read: bị ngăn

**Dirty read** là đọc dữ liệu mà giao dịch khác đã thay đổi nhưng chưa commit. READ COMMITTED ngăn hiện tượng này. Ví dụ, nếu B sửa số dư thành 1200 rồi rollback, A không nên dựa vào 1200 trong một `SELECT` thông thường.

### 4.2. Non-repeatable read: có thể xảy ra

**Non-repeatable read** là hai lần đọc cùng một hàng theo cùng tiêu chí nhưng thấy giá trị khác vì một giao dịch khác commit cập nhật hoặc xóa ở giữa. Thí nghiệm mục 2 là ví dụ trực tiếp.

Một lần đọc trước thấy hàng tồn tại; lần đọc sau có thể không còn thấy hàng nếu phiên khác xóa và commit. Điều quan trọng là **giá trị/kết quả của cùng đối tượng đọc có thể thay đổi giữa các câu lệnh**.

### 4.3. Phantom read: có thể xảy ra

**Phantom read** là chạy lại cùng một truy vấn theo **điều kiện lọc** nhưng có thêm hoặc mất hàng phù hợp do giao dịch khác commit thao tác thêm/xóa/sửa. Ví dụ, với bảng:

~~~sql
CREATE TABLE rc_demo_orders (
    id        BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status    TEXT NOT NULL
);

INSERT INTO rc_demo_orders (id, tenant_id, status)
VALUES
    (1, 42, 'PENDING'),
    (2, 42, 'PENDING');
~~~

Phiên A:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*)
FROM rc_demo_orders
WHERE tenant_id = 42 AND status = 'PENDING';
-- 2
~~~

Phiên B, trên kết nối khác:

~~~sql
BEGIN;

INSERT INTO rc_demo_orders (id, tenant_id, status)
VALUES (3, 42, 'PENDING');

COMMIT;
~~~

Phiên A đọc lại:

~~~sql
SELECT COUNT(*)
FROM rc_demo_orders
WHERE tenant_id = 42 AND status = 'PENDING';
-- 3

COMMIT;
~~~

Lần đọc sau chứa hàng `id = 3` chưa xuất hiện trong kết quả trước. Đây là phantom. Trường hợp một hàng chuyển vào/ra tập điều kiện `WHERE` do UPDATE cũng làm tập kết quả thay đổi.

### 4.4. Read skew: kết quả ghép từ nhiều thời điểm

Tưởng tượng hai tài khoản A và B có tổng tiền ban đầu 2.000:

- Giao dịch T1 đọc số dư A = 1.000.
- Giao dịch T2 chuyển 200 từ A sang B trong **một giao dịch**, sau đó commit: A = 800, B = 1.200.
- T1 đọc số dư B = 1.200, rồi cộng hai số đã đọc được: **2.200**.

Tổng thực tế ở cả trước và sau chuyển tiền là 2.000. Sai lệch 2.200 do ứng dụng ghép hai lần đọc từ **hai snapshot khác nhau**, không phải vì giao dịch chuyển tiền mất tính nguyên tử.

Nếu nghiệp vụ cần tổng nhất quán tại một thời điểm, hãy cân nhắc truy vấn tổng trong **một câu SQL** hoặc mức cô lập phù hợp cho nhiều câu SQL. Không nên giải quyết bằng cách đọc lại ngẫu nhiên cho đến khi “có vẻ đúng”.

## 5. READ COMMITTED có ngăn mất cập nhật không?

**Không nên dựa vào READ COMMITTED để bảo vệ thao tác đọc – tính – ghi ở tầng Java.** Nhiều phiên cùng đọc giá trị cũ, tự tính giá trị mới rồi ghi đè có thể gây **lost update**.

Ví dụ số dư ban đầu 1.000:

1. Giao dịch A đọc 1.000, dự định cộng 100 và tạo giá trị 1.100 trong Java.
2. Giao dịch B cũng đọc 1.000, dự định cộng 200 và tạo giá trị 1.200.
3. A gửi `UPDATE ... SET balance = 1100` và commit.
4. B gửi `UPDATE ... SET balance = 1200` dựa trên giá trị cũ và commit.

Kết quả cuối có thể là 1.200, trong khi hai phép cộng được chấp nhận sẽ cho 1.300. Cơ chế khóa hàng của database có thể làm một lệnh đợi lệnh kia, nhưng **đợi khóa không tự làm mới phép tính đã thực hiện bằng giá trị cũ trong Java**.

### 5.1. Cập nhật nguyên tử trong SQL

Khi nghiệp vụ là **tăng số dư thêm một lượng**, thay vì đọc số dư rồi ghi lại giá trị tuyệt đối, có thể biểu diễn phép biến đổi ngay trong một lệnh SQL:

~~~sql
UPDATE rc_demo_accounts
SET balance = balance + 100.00,
    version = version + 1
WHERE id = 101;
~~~

Ở PostgreSQL READ COMMITTED, những `UPDATE` cùng một hàng thường phải tuần tự hóa qua row lock; lệnh đến sau có thể chờ, rồi áp dụng biểu thức cập nhật trên phiên bản thích hợp sau khi lệnh trước commit. Vì thế, hai lệnh cộng 100 và 200 như trên thường cho kết quả cộng dồn 300, miễn cả hai giao dịch thành công.

Với nghiệp vụ **trừ tiền**, đưa bất biến vào điều kiện của lệnh:

~~~sql
UPDATE rc_demo_accounts
SET balance = balance - 200.00,
    version = version + 1
WHERE id = 101
  AND balance >= 200.00;
~~~

Ứng dụng phải kiểm tra **số hàng cập nhật**: `1` nghĩa là thao tác được áp dụng; `0` nghĩa là không thấy hàng phù hợp hoặc không đủ số dư. Ràng buộc `CHECK` là lớp bảo vệ bổ sung.

Đối với chuyển tiền giữa hai hàng, cần đặt **cả phần trừ và cộng trong cùng một giao dịch** và xử lý khóa, deadlock hoặc lỗi có thể xảy ra. Một câu SQL nguyên tử cho một hàng không tự khiến hai câu lệnh trên hai hàng trở thành một nghiệp vụ nguyên tử nếu không có transaction bao quanh.

### 5.2. Optimistic locking bằng số phiên bản

Khi nghiệp vụ thực sự cần đọc dữ liệu, tính toán hoặc yêu cầu người dùng duyệt trước khi ghi, có thể dùng số phiên bản:

~~~sql
-- Bước 1: lấy dữ liệu và số phiên bản.
SELECT balance, version
FROM rc_demo_accounts
WHERE id = 101;

-- Giả sử ứng dụng đọc được version = 0
-- và sau khi tính toán quyết định balance mới = 1100.

-- Bước 2: chỉ ghi nếu dữ liệu chưa bị cập nhật kể từ lúc đọc.
UPDATE rc_demo_accounts
SET balance = 1100.00,
    version = version + 1
WHERE id = 101
  AND version = 0;
~~~

Nếu một giao dịch khác đã tăng `version`, `UPDATE` sẽ tác động **0 hàng**. Ứng dụng phải thông báo xung đột hoặc đọc dữ liệu mới để tính lại, thay vì âm thầm coi là thành công. Đây là cơ chế kiểm soát đồng thời lạc quan, cũng là ý tưởng thường được hiện thực qua `@Version` trong JPA/Hibernate.

**Không tự động retry một thao tác không thể lặp an toàn**, ví dụ nghiệp vụ đã gọi dịch vụ ngoài hoặc đã gửi thông báo không thể thu hồi. Cần thiết kế idempotency và ranh giới side effect trước khi retry toàn bộ transaction.

### 5.3. SELECT FOR UPDATE để khóa hàng cần xử lý

Nếu cần khóa một hàng đã tìm trước khi ra quyết định, PostgreSQL hỗ trợ:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM rc_demo_accounts
WHERE id = 101
FOR UPDATE;

-- Kiểm tra điều kiện nghiệp vụ và cập nhật hàng đã khóa.
UPDATE rc_demo_accounts
SET balance = balance - 200.00,
    version = version + 1
WHERE id = 101
  AND balance >= 200.00;

COMMIT;
~~~

`FOR UPDATE` có thể buộc phiên khác chờ khi muốn cập nhật cùng hàng cho đến khi giao dịch hiện tại kết thúc. Cách này có thể phù hợp khi logic cần đọc và cập nhật một hàng, nhưng tăng nguy cơ chờ khóa/deadlock nếu giữ transaction quá lâu. **Khóa các hàng đã chọn không tự ngăn phantom của những hàng chưa tồn tại hoặc chưa thuộc tập được khóa.** Nếu nghiệp vụ cần một bất biến trên cả tập hàng, phải xem xét thiết kế ràng buộc, khóa thích hợp hoặc mức SERIALIZABLE.

## 6. So sánh READ COMMITTED với các mức cô lập khác

Bảng sau mô tả **hướng phân biệt theo hiện tượng trong chuẩn SQL**, không thay thế tài liệu của DBMS cụ thể:

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read | Ghi chú |
| --- | --- | --- | --- | --- |
| READ UNCOMMITTED | Có thể | Có thể | Có thể | Một số DBMS thực thi mạnh hơn tên mức |
| **READ COMMITTED** | **Ngăn** | Có thể | Có thể | Không giữ cùng kết quả giữa các statement |
| REPEATABLE READ | Ngăn | Ngăn | Theo chuẩn có thể | Engine dùng snapshot/khóa theo cách khác nhau |
| SERIALIZABLE | Ngăn | Ngăn | Ngăn theo nghĩa lịch biểu tương đương tuần tự | Có thể tăng chờ, từ chối/abort transaction, cần retry an toàn |

**Ngoại lệ quan trọng của PostgreSQL:** PostgreSQL thực thi `READ UNCOMMITTED` tương đương `READ COMMITTED`. Ở `REPEATABLE READ`, PostgreSQL dùng ảnh chụp nhất quán cho transaction (được thiết lập theo quy tắc của engine), nên cũng tránh phantom kiểu hai lần SELECT trong một giao dịch. Ở `SERIALIZABLE`, PostgreSQL thêm cơ chế phát hiện cấu trúc phụ thuộc nguy hiểm và có thể báo `serialization_failure`, buộc ứng dụng quyết định retry.

**Không có nghĩa mọi DBMS đều dùng snapshot giống nhau:**

- **PostgreSQL:** READ COMMITTED dùng snapshot riêng cho những `SELECT` thông thường; một số thao tác ghi/khóa có quy tắc đợi và đánh giá lại phiên bản hàng.
- **MySQL InnoDB:** ở READ COMMITTED, các lượt đọc nhất quán (*consistent nonlocking reads*) lấy snapshot mới theo từng lần đọc; **locking reads** và cập nhật sử dụng cơ chế khóa riêng.
- **SQL Server:** `READ COMMITTED` có thể dùng cơ chế khóa đọc mặc định hoặc cách đọc phiên bản hàng khi bật tùy chọn `READ_COMMITTED_SNAPSHOT`. Khác biệt này làm thay đổi chi tiết quan sát và chờ khóa.

Khi chuyển hệ quản trị hoặc driver, kiểm chứng hành vi bằng transaction thật. Không áp đặt mô hình “mỗi statement có một snapshot” cho mọi cách triển khai READ COMMITTED.

### 6.1. Khi nào READ COMMITTED là hợp lý?

Phù hợp với nhiều API CRUD khi mỗi thao tác có thể chấp nhận dữ liệu đã commit gần nhất, hoặc tính đúng đắn được bảo vệ bằng **câu lệnh nguyên tử, constraint, khóa hay kiểm tra phiên bản**. Mức này thường giảm việc giữ một snapshot dài và các chi phí liên quan, nhưng không xóa hết nguy cơ chờ khóa hay xung đột ghi.

Cần cân nhắc mức mạnh hơn hoặc thiết kế lại truy vấn khi:

- Một báo cáo phải đọc nhiều bảng trong nhiều câu SQL mà vẫn cần nhìn thấy một trạng thái chung.
- Quy tắc nghiệp vụ phụ thuộc vào tập hàng và không thể kiểm tra an toàn bằng một lệnh cập nhật có điều kiện.
- Giao dịch cần bảo đảm quan sát nhất quán nhiều lần đọc trong thời gian xử lý.

**REPEATABLE READ không đồng nghĩa tự động bảo vệ mọi bất biến nghiệp vụ.** Chẳng hạn, hai giao dịch cùng kiểm tra một điều kiện rồi ghi lên **hai hàng khác nhau** có thể gây write skew ở những triển khai snapshot isolation. Với bất biến liên hàng cần tính tuần tự thực sự, hãy đánh giá `SERIALIZABLE` hoặc một cơ chế đồng bộ cụ thể.

## 7. Sử dụng READ COMMITTED trong Java/JDBC

Một `Connection` JDBC có mức cô lập giao dịch riêng. Có thể dùng `Connection.TRANSACTION_READ_COMMITTED`, nhưng phải chú ý **autocommit** và ranh giới transaction.

Ví dụ sau đọc hai lần trong một transaction để người học thấy rằng hai giá trị **có thể khác nhau** nếu giao dịch ngoài commit đúng lúc ở giữa:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class IsolationDemo {
    public record TwoReads(BigDecimal first, BigDecimal second) {}

    private final DataSource dataSource;

    public IsolationDemo(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public TwoReads readTwice(long accountId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Thiết lập trước khi bắt đầu transaction.
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            connection.setAutoCommit(false);

            try {
                BigDecimal first = readBalance(connection, accountId);

                // Để tái hiện thay đổi, một kết nối B độc lập
                // phải UPDATE và COMMIT giữa hai lần đọc.
                BigDecimal second = readBalance(connection, accountId);

                connection.commit();
                return new TwoReads(first, second);
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

    private static BigDecimal readBalance(Connection connection, long id)
            throws SQLException {
        String sql = """
                SELECT balance
                FROM rc_demo_accounts
                WHERE id = ?
                """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Account not found: " + id);
                }
                return rs.getBigDecimal("balance");
            }
        }
    }
}
~~~

Ví dụ dùng Java 17 (`record`, text block). Hai lần đọc liên tiếp **không tự tạo** ra khác biệt: cần một giao dịch khác commit ở khoảng xen giữa. Trong hệ thống thực, khoảng này có thể xuất hiện do xử lý nghiệp vụ, truy vấn khác hoặc việc ứng dụng chờ một thao tác.

**Những điểm cần kiểm tra khi triển khai:**

- `autoCommit = true` thường khiến mỗi statement tự là một transaction; muốn **so sánh hai câu SELECT trong cùng transaction**, phải kiểm soát transaction trên một connection.
- Đặt mức cô lập **trước** khi bắt đầu transaction để tránh khác biệt hoặc lỗi theo driver/DBMS.
- Dùng **cùng một Connection** cho các lời gọi repository phải thuộc một transaction; tạo connection mới ở giữa sẽ thay đổi ngữ cảnh.
- Trong môi trường connection pool, xác minh pool/transaction manager trả lại thuộc tính isolation và autocommit đúng cấu hình khi connection được hoàn trả. Không thay đổi trạng thái pool một cách tùy tiện.
- `PreparedStatement` bảo vệ cách truyền tham số SQL; phân quyền truy cập tài khoản và tenant vẫn là trách nhiệm nghiệp vụ/bảo mật riêng.
- Nếu giao dịch gặp `SQLTransientException`, deadlock hoặc serialization failure, đánh giá khả năng retry với backoff và idempotency theo mã lỗi engine thay vì retry tất cả `SQLException` vô điều kiện.

### 7.1. Framework quản lý transaction

Trong Spring, một service có thể khai báo:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountReadService {
    private final AccountRepository repository;

    public AccountReadService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED, readOnly = true)
    public AccountSnapshot readAccount(long accountId) {
        // Một câu truy vấn ở đây chỉ minh họa ranh giới transaction.
        return repository.findSnapshot(accountId);
    }
}
~~~

`AccountRepository` và `AccountSnapshot` đại diện cho các thành phần của ứng dụng, không phải class chuẩn của Java. Đoạn mã chỉ minh họa khai báo transaction; không phải ví dụ đầy đủ có thể biên dịch độc lập.

Chú ý rằng `@Transactional` cần được gọi qua cơ chế proxy/transaction manager thích hợp; phương thức tự gọi trong cùng object có thể không đi qua interceptor ở cấu hình proxy thông dụng. `readOnly = true` thường là gợi ý tối ưu, **không biến READ COMMITTED thành một snapshot cố định**. Cần kiểm tra transaction manager và mức cô lập thực mà database đang dùng.

## 8. Thiết kế nghiệp vụ khi dữ liệu có thể đổi giữa hai lần đọc

Đừng hỏi chỉ “READ COMMITTED có an toàn không?”, mà xác định **bất biến nghiệp vụ** cần được bảo vệ:

| Tình huống | Nguy cơ khi đọc nhiều lần | Hướng xử lý thường dùng |
| --- | --- | --- |
| Trang chi tiết đơn hàng đọc lại trạng thái | Hiển thị trạng thái mới sau khi người khác cập nhật | Thường chấp nhận được; cập nhật UI theo trạng thái gần nhất |
| Thực hiện phép cộng/trừ số dư | Tính từ số dư cũ, ghi đè mất thay đổi | Cập nhật nguyên tử và kiểm tra điều kiện trong SQL |
| Người dùng sửa biểu mẫu nhiều phút | Dữ liệu đã đổi khi bấm lưu | Optimistic locking với `version`; thông báo xung đột |
| Báo cáo tổng hợp nhiều câu SQL | Các con số phản ánh những thời điểm khác nhau | Gom thành một SQL, dùng snapshot nhất quán hoặc quy trình báo cáo |
| Chọn tài nguyên theo tiêu chí “còn chỗ” | Giao dịch khác cùng chọn lúc này | Ràng buộc UNIQUE, conditional UPDATE, locking hoặc SERIALIZABLE tùy bất biến |
| Phân trang danh sách đang thay đổi | Trang kế tiếp thấy thêm/bớt mục | Keyset pagination; nếu cần ảnh chụp cố định, thiết kế snapshot riêng |

**Chỉ số `version`, constraint và phép cập nhật có điều kiện thường rẻ và rõ ràng hơn việc nâng mức isolation cho toàn bộ hệ thống mà không biết nguy cơ cụ thể.** Nhưng khi bất biến liên quan tập hàng phức tạp, chỉ tăng `version` trên một hàng chưa đủ.

Đối với dữ liệu nhiều tenant, luôn giữ điều kiện tenant trong các lệnh đọc/ghi và xác thực quyền ở tầng ứng dụng; READ COMMITTED **không phải cơ chế phân quyền**. Với những transaction dài, việc giữ connection và snapshot/lock quá lâu còn có thể tác động đến throughput và cơ chế dọn dẹp phiên bản; nên giữ transaction gọn và tránh chờ HTTP bên ngoài khi đang giữ khóa.

## 9. Bài tập thực hành

### Bài tập 1: xác định loại hiện tượng

Cho chuỗi thao tác:

~~~text
T1: BEGIN READ COMMITTED
T1: SELECT price FROM products WHERE id = 7     -> 500
T2: BEGIN
T2: UPDATE products SET price = 550 WHERE id = 7
T2: COMMIT
T1: SELECT price FROM products WHERE id = 7     -> 550
T1: COMMIT
~~~

**Hỏi:** Có dirty read hay không? Hiện tượng nào xảy ra?

*Đáp án gợi ý:* Không có dirty read vì T1 thấy giá trị mới sau khi T2 đã commit. Hai lần đọc cùng hàng trả kết quả khác nhau, nên đây là non-repeatable read.

### Bài tập 2: kiểm tra phantom

T1 đọc `COUNT(*)` của các đơn hàng `PENDING` trong tenant 42, được 7. T2 insert một đơn `PENDING` mới, commit; T1 đọc lại cùng điều kiện được 8. Đây là thay đổi trên tập kết quả, nên được xem là phantom read.

**Hỏi thêm:** Vì sao tạo chỉ mục trên `(tenant_id, status)` không tự ngăn phantom?

*Gợi ý:* Chỉ mục tăng tốc đường tìm hàng; nó không tự bảo đảm hai câu SELECT sử dụng một snapshot chung hay khóa toàn bộ phạm vi điều kiện ở READ COMMITTED.

### Bài tập 3: thiết kế cập nhật an toàn

Hai request cùng cộng điểm thưởng vào một tài khoản. Mỗi request đang làm:

~~~text
SELECT points -> tính points + delta trong Java -> UPDATE SET points = ?
~~~

Hãy viết lại bằng `UPDATE SET points = points + ? WHERE id = ?` và nêu cách đọc số hàng cập nhật. Nếu cần xét giới hạn điểm tối đa, hãy đưa điều kiện nghiệp vụ vào `WHERE` hoặc kiểm tra ràng buộc phù hợp. So sánh với phương án dùng cột `version`.

### Bài tập 4: thử mức cô lập

Lặp lại bài thực hành ở phần 2 với `REPEATABLE READ` của **PostgreSQL**. Xác định kết quả hai lần `SELECT` sau khi Phiên B commit, đồng thời tìm hiểu một số kịch bản cập nhật đồng thời có thể phát sinh lỗi serialization ở PostgreSQL. Chú ý kết quả này là đặc trưng triển khai cụ thể, không được tự suy ra cho mọi DBMS.

## 10. Những nhầm lẫn cần tránh

- **“READ COMMITTED khóa giá trị đến COMMIT.”** Sai: cùng một hàng có thể được nhìn thấy với phiên bản mới ở statement sau.
- **“Không dirty read tức là mọi phép tính trong transaction nhất quán.”** Sai: hai `SELECT` có thể ghép dữ liệu ở hai thời điểm.
- **“Có transaction là tránh lost update.”** Sai với mẫu đọc – tính – ghi giá trị tuyệt đối; cần thiết kế bảo vệ cụ thể.
- **“Dùng SELECT FOR UPDATE sẽ ngăn mọi phantom.”** Sai: khóa những hàng đã thấy không mặc định khóa mọi hàng có thể xuất hiện sau.
- **“Tăng isolation là giải pháp duy nhất.”** Chưa chắc: một SQL tổng hợp, conditional UPDATE, constraint hoặc optimistic locking có thể giải quyết chính xác hơn.
- **“READ COMMITTED ở mọi database đều dùng cùng snapshot/lock.”** Sai: PostgreSQL, MySQL/InnoDB và SQL Server có khác biệt đáng kể.

## Ghi nhớ

Ở mức **READ COMMITTED**, một transaction không được đọc thay đổi chưa commit của transaction khác, nhưng **kết quả đọc có thể thay đổi giữa các câu lệnh** sau khi giao dịch khác commit. Trong PostgreSQL, `SELECT` thông thường dùng snapshot mới cho từng câu lệnh, nên non-repeatable read và phantom read là những hiện tượng có thể quan sát được.

Khi xây dựng persistence cho Java, hãy quyết định theo **bất biến cần giữ**: một truy vấn thống nhất cho dữ liệu cần đọc cùng thời điểm, cập nhật nguyên tử cho thay đổi số lượng, kiểm soát phiên bản cho thao tác sửa dựa trên dữ liệu cũ, hoặc mức cô lập/khóa cao hơn khi cần bảo vệ quy tắc liên giao dịch. Kiểm chứng bằng hai kết nối độc lập và trên đúng DBMS đang vận hành.
