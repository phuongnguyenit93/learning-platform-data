# Mức REPEATABLE READ và giới hạn bảo đảm theo hệ quản trị

Trong một giao dịch, ứng dụng có thể cần đọc cùng một dữ liệu nhiều lần. Ví dụ, dịch vụ Java đọc số dư tài khoản, thực hiện một số kiểm tra nghiệp vụ rồi đọc lại số dư để ghi báo cáo. Nếu một giao dịch khác cập nhật tài khoản giữa hai lần đọc, liệu ứng dụng thấy giá trị cũ hay mới? Câu trả lời phụ thuộc **mức cô lập giao dịch** (*transaction isolation level*) và **cách hệ quản trị hiện thực mức đó**.

**REPEATABLE READ** được đặt tên theo bảo đảm cơ bản: khi một giao dịch đọc một hàng, các thay đổi do giao dịch khác thực hiện không được khiến giao dịch đó đọc lại cùng hàng với giá trị khác trong cùng phạm vi giao dịch. Nhưng tên mức cô lập **không phải lời hứa rằng mọi truy vấn lặp lại luôn thấy cùng một tập hàng, mọi thao tác đều đọc từ một ảnh chụp duy nhất, hay mọi quy tắc nghiệp vụ đều an toàn trước chạy đồng thời**.

Bài học thuộc chương **Tính cô lập** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ kết nối các bảo đảm của REPEATABLE READ với thiết kế persistence cho Java: ranh giới giao dịch, kiểm soát đồng thời, xử lý xung đột, kết nối và hiệu năng. Các ví dụ phân biệt rõ giữa chuẩn SQL, PostgreSQL, MySQL/InnoDB, SQL Server và Oracle để tránh phụ thuộc sai vào tên gọi của một mức cô lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích *non-repeatable read*, *phantom read*, *snapshot* và *write skew* bằng lịch chạy của hai giao dịch.
2. Nêu được bảo đảm tối thiểu của REPEATABLE READ và lý do không đồng nhất REPEATABLE READ với SERIALIZABLE.
3. Phân biệt cơ chế snapshot/MVCC của PostgreSQL, consistent read và locking read của InnoDB, khóa dài hạn của SQL Server, cùng các mức cô lập thực sự hỗ trợ trong Oracle.
4. Tạo ví dụ hai phiên giao dịch để quan sát giá trị lặp lại, hàng mới phù hợp điều kiện lọc và xung đột khi ghi.
5. Chọn phạm vi transaction trong JDBC hoặc framework Java, xử lý lỗi và retry đúng ranh giới.
6. Đánh giá đánh đổi giữa tính nhất quán cần thiết và tài nguyên thực thi khi giao dịch kéo dài.

## 2. Các hiện tượng đọc khi nhiều giao dịch cùng chạy

Hãy hình dung bảng `accounts` có hàng `id = 1`, `balance = 100`. Giao dịch T1 đọc tài khoản để tính báo cáo; đồng thời T2 cập nhật số dư.

### 2.1. Non-repeatable read: đọc lại cùng hàng ra giá trị khác

~~~text
Thời gian   T1 (đọc báo cáo)            T2 (cập nhật)
---------   ------------------------    --------------------------
t1          BEGIN
t2          SELECT balance -> 100
t3                                      BEGIN
t4                                      UPDATE balance = 150
t5                                      COMMIT
t6          SELECT balance -> 150
t7          COMMIT
~~~

Đây là *non-repeatable read*: cùng một hàng và cùng điều kiện, nhưng T1 nhận hai giá trị khác nhau vì T2 đã ghi và commit. Với REPEATABLE READ theo bảo đảm chuẩn, trường hợp này **không được xảy ra** đối với thay đổi của giao dịch khác.

**Chú ý:** Nếu **chính T1** thực hiện `UPDATE` giữa hai lần đọc, T1 có thể thấy thay đổi do mình tạo ra. Tính “lặp lại” không có nghĩa giao dịch bị cấm nhìn thấy các ghi của chính nó.

### 2.2. Phantom read: một hàng mới xuất hiện trong tập kết quả

Giả sử có truy vấn đếm các đơn hàng đang chờ:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';
~~~

Lịch chạy:

~~~text
Thời gian   T1                              T2
---------   -----------------------------   --------------------------
t1          BEGIN
t2          COUNT(PENDING) -> 3
t3                                          BEGIN
t4                                          INSERT order PENDING
t5                                          COMMIT
t6          COUNT(PENDING) -> 4
t7          COMMIT
~~~

Không nhất thiết có hàng cũ nào đổi giá trị. Tập hàng thỏa điều kiện đã có thêm một **phantom**. Theo cách phân loại hiện tượng trong chuẩn SQL, REPEATABLE READ **có thể cho phép phantom**, còn SERIALIZABLE phải loại trừ kết quả không tương đương với một lịch chạy tuần tự.

Trong thực tế, một số hệ quản trị ngăn được phantom trong các lần đọc thông thường ở REPEATABLE READ nhờ snapshot giao dịch. Vì vậy không nên suy luận “REPEATABLE READ luôn có phantom” hoặc “REPEATABLE READ luôn cấm phantom” cho mọi hệ quản trị.

### 2.3. Write skew: mỗi giao dịch cập nhật hàng khác nhau nhưng cùng phá quy tắc

Có một ca trực với hai bác sĩ A và B; quy tắc nghiệp vụ là **mỗi ca luôn phải có ít nhất một người trực**.

~~~text
Trạng thái ban đầu:
A: on_call = true
B: on_call = true

T1                              T2
-----------------------------   -----------------------------
Đọc: có 2 người trực            Đọc: có 2 người trực
Cho A nghỉ (UPDATE hàng A)      Cho B nghỉ (UPDATE hàng B)
COMMIT                          COMMIT

Trạng thái cuối nếu cả hai đều thành công:
A = false; B = false  -> vi phạm quy tắc.
~~~

Mỗi giao dịch chỉ cập nhật **một hàng khác nhau** nên có thể không xảy ra xung đột ghi trực tiếp trên cùng hàng. Cả hai quyết định dựa vào ảnh chụp cho thấy người kia vẫn trực. Đây là *write skew*, một dạng bất thường được phép dưới một số hiện thực snapshot isolation/REPEATABLE READ.

**Không thể khắc phục chỉ bằng việc “đọc lại cùng hàng thấy giống nhau”.** Bảo đảm giá trị đọc lặp lại chưa đủ để bảo vệ một ràng buộc phụ thuộc nhiều hàng. Cần thiết kế lại thao tác đồng thời hoặc dùng mức cô lập/cơ chế khóa phù hợp.

## 3. REPEATABLE READ bảo đảm những gì theo cách phân loại SQL?

Mức cô lập diễn tả các kết quả mà chương trình có thể quan sát khi giao dịch đồng thời. Bảng sau là **khung khái niệm của chuẩn SQL** theo phân loại hiện tượng thông dụng, không phải kết quả đo của một DBMS cụ thể.

| Hiện tượng do giao dịch khác gây ra | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Dirty read: đọc dữ liệu chưa commit | Không cho phép | Không cho phép | Không cho phép |
| Non-repeatable read: cùng hàng đổi giá trị | Có thể | Không cho phép | Không cho phép |
| Phantom read: tập hàng thỏa điều kiện thay đổi | Có thể | Có thể | Không cho phép |
| Lịch chạy không thể tương đương lịch tuần tự | Có thể | Có thể | Không cho phép |

Trong bảng, “có thể” là **được phép xuất hiện**, không có nghĩa cơ sở dữ liệu bắt buộc phải tạo ra hiện tượng đó. Một hiện thực mạnh hơn yêu cầu tối thiểu của một mức cô lập có thể chặn thêm một số bất thường.

Để phân biệt đúng:

- **Repeatable read** theo tên mức SQL tập trung vào việc đọc lại hàng đã đọc, nhưng không mặc định bảo vệ mọi điều kiện tìm kiếm hoặc mọi quy tắc đa hàng.
- **Snapshot isolation (SI)** là một cơ chế/kiểu ngữ nghĩa mà một giao dịch thường quan sát một ảnh chụp nhất quán của dữ liệu đã commit, có xử lý xung đột ghi. SI có thể ngăn nhiều trường hợp phantom quan sát được nhưng vẫn cho phép *write skew*; bản thân thuật ngữ SI không đồng nghĩa SERIALIZABLE.
- **Serializable** yêu cầu kết quả của các giao dịch đã commit tương đương một thứ tự chạy tuần tự hợp lệ. Cơ chế thực thi có thể dùng khóa, kiểm tra xung đột, MVCC hoặc kết hợp.

Không thể xác định đầy đủ bảo đảm chỉ từ hằng số `TRANSACTION_REPEATABLE_READ` trong JDBC. Cần biết hệ quản trị, phiên bản, engine lưu trữ và cả **loại câu lệnh đọc/ghi**.

## 4. PostgreSQL: REPEATABLE READ dùng ảnh chụp nhất quán của giao dịch

Trong PostgreSQL, REPEATABLE READ có ngữ nghĩa snapshot isolation gần với khái niệm SI. Những câu `SELECT` thông thường trong một transaction đọc cùng một snapshot được thiết lập ở **câu lệnh đầu tiên cần snapshot**, không đơn thuần ở thời điểm gõ `BEGIN`. Giao dịch cũng nhìn thấy các thay đổi do chính nó thực hiện.

Điều này kéo theo hai kết quả quan trọng:

1. Một hàng bị giao dịch khác cập nhật rồi commit sau khi snapshot đã thiết lập vẫn xuất hiện với **phiên bản cũ** trong lần `SELECT` thông thường tiếp theo của T1.
2. Hàng mới được giao dịch khác chèn và commit sau snapshot cũng **không xuất hiện** trong truy vấn lặp lại của T1. Vì vậy PostgreSQL REPEATABLE READ ngăn cả non-repeatable read lẫn phantom read quan sát được từ thay đổi của giao dịch khác.

PostgreSQL vẫn phân biệt REPEATABLE READ với SERIALIZABLE: **write skew và các bất thường tuần tự hóa khác vẫn có thể xảy ra** ở REPEATABLE READ.

### 4.1. Thí nghiệm hai phiên PostgreSQL

Chuẩn bị trên cơ sở dữ liệu thử nghiệm:

~~~sql
CREATE TABLE account_balances (
    account_id BIGINT PRIMARY KEY,
    balance    INTEGER NOT NULL
);

INSERT INTO account_balances (account_id, balance)
VALUES (1, 100);
~~~

Mở hai kết nối độc lập (phiên A và B). Chạy theo thứ tự sau:

**Phiên A — bước 1:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM account_balances
WHERE account_id = 1;
-- 100: snapshot của A được thiết lập
~~~

**Phiên B — sau bước 1 của A:**

~~~sql
BEGIN;

UPDATE account_balances
SET balance = 150
WHERE account_id = 1;

COMMIT;
~~~

**Phiên A — bước 2:**

~~~sql
SELECT balance
FROM account_balances
WHERE account_id = 1;
-- Vẫn là 100 trong transaction A.

COMMIT;

-- Transaction mới nhìn thấy giá trị đã commit:
SELECT balance
FROM account_balances
WHERE account_id = 1;
-- 150 (nếu không có ghi thêm)
~~~

Bảo đảm này hữu ích khi một báo cáo cần đọc nhiều bảng hoặc nhiều câu truy vấn dựa trên cùng ảnh chụp dữ liệu. Tuy nhiên, **ảnh chụp nhất quán không tự bảo vệ toàn bộ quy tắc kiểm tra rồi ghi**.

### 4.2. Xung đột cập nhật cùng một hàng

Chạy lại lịch trên, nhưng sau khi B commit, cho A (đang ở REPEATABLE READ và giữ snapshot cũ) thử cập nhật cùng hàng:

~~~sql
UPDATE account_balances
SET balance = 175
WHERE account_id = 1;
~~~

PostgreSQL có thể từ chối thao tác với lỗi:

~~~text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
~~~

Trong PostgreSQL REPEATABLE READ, cập nhật một hàng đã bị giao dịch đồng thời thay đổi sau snapshot của mình có thể gây **serialization failure**, thay vì âm thầm ghi đè dựa vào phiên bản cũ. Sau lỗi, transaction cần rollback; nếu nghiệp vụ muốn thử lại thì phải **chạy lại toàn bộ transaction** với snapshot mới.

Đừng nhầm cơ chế phát hiện xung đột *trên cùng hàng* này với bảo đảm tuần tự hóa đầy đủ: hai transaction cập nhật **hai hàng khác nhau** nhưng phụ thuộc lẫn nhau qua dữ liệu đã đọc vẫn có thể tạo *write skew*.

### 4.3. Khi nào cần SERIALIZABLE trong PostgreSQL?

Nếu một transaction kiểm tra điều kiện “ít nhất một người vẫn trực” rồi cập nhật hàng của mình, hai transaction cạnh tranh có thể cùng commit tại REPEATABLE READ, gây sai quy tắc. PostgreSQL `SERIALIZABLE` sử dụng cơ chế kiểm tra phụ thuộc để loại trừ lịch chạy không thể tuần tự hóa; một trong các transaction có thể bị hủy với SQLSTATE `40001`.

Ứng dụng cần xử lý retry từ đầu và **kiểm tra lại điều kiện nghiệp vụ** trong lần chạy mới. SERIALIZABLE không biến lỗi xung đột thành điều không thể xảy ra; nó thay một số kết quả sai bằng giao dịch bị từ chối để chạy lại.

## 5. MySQL/InnoDB: REPEATABLE READ và sự khác biệt giữa hai kiểu đọc

Trong MySQL với engine **InnoDB**, REPEATABLE READ là mức cô lập mặc định ở các cấu hình thông dụng. Nhưng không thể nói mọi câu `SELECT`, `UPDATE` và `SELECT ... FOR UPDATE` đều dùng cùng một ảnh chụp.

### 5.1. Consistent nonlocking read

Với `SELECT` thông thường, InnoDB sử dụng MVCC tạo *consistent read*. Ở REPEATABLE READ, snapshot dùng cho các lần consistent read thường được thiết lập ở **lần consistent read đầu tiên của transaction**. Các consistent read sau cùng transaction tiếp tục thấy ảnh chụp đó, cộng với các thay đổi của chính transaction.

~~~sql
-- Phiên A, MySQL/InnoDB
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance FROM account_balances WHERE account_id = 1;
-- Ví dụ trả 100.

-- Phiên B cập nhật balance=150, COMMIT.

SELECT balance FROM account_balances WHERE account_id = 1;
-- Phiên A vẫn có thể thấy 100 qua consistent read.

COMMIT;
~~~

Trong trường hợp `SELECT` thông thường, hàng mới được giao dịch khác chèn sau snapshot cũng không tự xuất hiện, nên nhiều phantom được tránh trên mặt kết quả đọc.

### 5.2. Locking read và câu lệnh ghi đọc trạng thái hiện hành

`SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE` (ở các phiên bản hỗ trợ) và các câu lệnh ghi không giống consistent read thông thường. Chúng thường cần nhìn trạng thái hiện hành của dữ liệu phù hợp và lấy khóa.

~~~sql
-- Phiên A đang giữ snapshot cũ sau SELECT thường.
SELECT balance
FROM account_balances
WHERE account_id = 1
FOR UPDATE;
-- Có thể thấy giá trị đã commit mới hơn (ví dụ 150),
-- sau khi đợi/giành được khóa cần thiết.
~~~

Như vậy, **trộn consistent read với locking/current read trong cùng transaction có thể cho kết quả không đồng nhất về phiên bản dữ liệu**. Đây không phải lý do để bỏ khóa khi nghiệp vụ cần sửa dữ liệu; nó là lý do phải hiểu rõ cơ chế trước khi thiết kế chuỗi “đọc, kiểm tra, ghi”.

InnoDB dùng **record locks**, **gap locks** và **next-key locks** trong nhiều tình huống truy vấn có khóa ở REPEATABLE READ. Khi khóa phạm vi qua chỉ mục, next-key lock có thể ngăn giao dịch khác chèn hàng mới vào khoảng đang được bảo vệ, giúp tránh phantom cho thao tác khóa phạm vi. Chi tiết phụ thuộc điều kiện, chỉ mục, kiểu câu lệnh và tối ưu truy vấn; chẳng hạn tra cứu chính xác bằng khóa duy nhất có thể chỉ cần khóa bản ghi thay vì khóa khoảng.

**Kết luận cho InnoDB:** truy vấn consistent read có tính lặp lại theo snapshot; truy vấn khóa hoặc ghi có quy tắc hiển thị và khóa khác. Một ứng dụng phải thiết kế dựa trên loại câu SQL đang chạy, không chỉ dựa trên tên REPEATABLE READ.

### 5.3. Lưu ý về snapshot và hiệu năng InnoDB

Transaction đọc giữ snapshot lâu có thể khiến lịch sử phiên bản trong undo log cần được duy trì lâu hơn, làm tăng áp lực bảo trì và tài nguyên. Transaction giữ khóa lâu có thể làm tăng chờ khóa, deadlock và độ trễ của các thao tác khác. Đặt REPEATABLE READ cho mọi thao tác trong cả một request HTTP dài không mặc nhiên là cách tiếp cận phù hợp.

## 6. SQL Server: REPEATABLE READ dựa vào khóa, phantom vẫn có thể xuất hiện

Trong SQL Server theo cơ chế cô lập **REPEATABLE READ dựa vào khóa**, những hàng đã đọc được bảo vệ bằng **shared locks** giữ tới hết transaction. Một giao dịch khác không thể tùy ý cập nhật hoặc xóa các hàng mà T1 đang giữ shared lock theo cách tạo non-repeatable read.

Tuy nhiên, REPEATABLE READ **không mặc nhiên dùng khóa phạm vi khóa (*key-range locks*) để bảo vệ mọi khoảng điều kiện**. Giao dịch khác có thể chèn một hàng mới thỏa điều kiện tìm kiếm; T1 đọc lại điều kiện và thấy thêm hàng, tức *phantom read* vẫn được phép.

Ví dụ ý tưởng:

~~~sql
-- SQL Server, phiên A
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;

SELECT COUNT(*) AS pending_count
FROM dbo.orders
WHERE status = 'PENDING';

-- Phiên B chèn thêm một hàng PENDING và COMMIT
-- (nếu thao tác không bị các khóa khác cản trở).

SELECT COUNT(*) AS pending_count
FROM dbo.orders
WHERE status = 'PENDING';
-- Có thể tăng: phantom không bị REPEATABLE READ cấm.

COMMIT TRANSACTION;
~~~

Kết quả và mức chờ khóa thực tế phụ thuộc chỉ mục, kế hoạch đọc, số lượng hàng, cấp độ khóa và cạnh tranh; ví dụ minh họa **khả năng** phantom, không phải dự báo chắc chắn mỗi lần thực thi.

Để kiểm soát phantom bằng cơ chế khóa phạm vi trong SQL Server, cần xem xét `SERIALIZABLE`. Nếu cần ngữ nghĩa snapshot, SQL Server có mức `SNAPSHOT` riêng, phải được cấu hình cho phép trên database. Tùy chọn `READ_COMMITTED_SNAPSHOT` ảnh hưởng cách hiện thực **READ COMMITTED**, không tự biến REPEATABLE READ thành snapshot isolation.

Hậu quả thực tế của REPEATABLE READ dựa vào khóa là một transaction dài có thể **chặn writer** trên hàng đã đọc và làm tăng chờ khóa/deadlock. Vì vậy quyết định về isolation level liên quan trực tiếp tới thời gian giữ transaction và thông lượng dịch vụ.

## 7. Oracle: không có mức REPEATABLE READ mang tên đó

Oracle Database không cung cấp mức `REPEATABLE READ` như một tùy chọn isolation level riêng theo tên. Các lựa chọn chính thường gặp là:

- **READ COMMITTED**: đọc nhất quán ở mức từng câu lệnh; hai câu `SELECT` liên tiếp trong cùng transaction có thể quan sát kết quả khác nhau khi có commit ở giữa.
- **SERIALIZABLE**: dùng ảnh chụp nhất quán ở mức transaction và cơ chế xử lý xung đột theo quy tắc của Oracle; một số tình huống có thể lỗi `ORA-08177: can't serialize access for this transaction`.
- **READ ONLY**: transaction chỉ đọc với ảnh chụp nhất quán xuyên suốt transaction, phù hợp với một số báo cáo nhiều bước.

Đừng cố gửi `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` tới Oracle như thể mọi hệ quản trị nhận cùng một cú pháp và cung cấp cùng bảo đảm. Cũng không nên mặc định tên **SERIALIZABLE** ở Oracle có cùng mọi đặc tính thực thi và mọi xử lý xung đột như PostgreSQL; cần đọc tài liệu và kiểm thử đúng phiên bản, tình huống.

Với ứng dụng Java hỗ trợ nhiều DBMS, việc đặt `Connection.TRANSACTION_REPEATABLE_READ` có thể không được driver/hệ quản trị hỗ trợ. Hãy kiểm tra khả năng hỗ trợ bằng metadata JDBC và chọn chính sách cô lập tương ứng với yêu cầu nghiệp vụ, đồng thời kiểm thử thực tế.

## 8. Bảng đối chiếu giữa các hệ quản trị

| Môi trường / mức được gọi | Cơ chế đọc tiêu biểu | Đọc lại cùng hàng sau commit của T2 | Phantom khi T2 chèn hàng mới | Rủi ro cần nhớ |
|---|---|---|---|---|
| Chuẩn SQL — REPEATABLE READ (mức tối thiểu) | Không quy định thuật toán thực thi | Không được đổi vì T2 | Có thể xảy ra | Chưa bảo đảm tương đương lịch tuần tự |
| PostgreSQL — REPEATABLE READ | Snapshot transaction qua MVCC | `SELECT` thường vẫn thấy phiên bản cũ | `SELECT` thường không thấy hàng mới sau snapshot | Write skew; cập nhật cùng hàng có thể lỗi `40001` |
| MySQL/InnoDB — REPEATABLE READ | Snapshot cho consistent read; khóa cho locking/current read | `SELECT` thường ổn định; locking read có thể thấy mới hơn | Consistent read tránh nhiều phantom; locking read phụ thuộc khóa khoảng | Pha trộn cách đọc; gap locks, deadlock, write skew tùy lịch |
| SQL Server — REPEATABLE READ | Shared locks giữ đến cuối transaction | Writer trên hàng đã đọc thường phải chờ | Có thể xảy ra | Chặn ghi, deadlock; cần SERIALIZABLE nếu phải bảo vệ phạm vi |
| Oracle Database | **Không có mức REPEATABLE READ riêng** | Phụ thuộc chọn READ COMMITTED, SERIALIZABLE hoặc READ ONLY | Phụ thuộc mức chọn | Không thể ánh xạ tên mức cô lập một cách máy móc |

Hai lời nhắc khi đọc bảng:

1. “Không thấy phantom” qua `SELECT` snapshot **không đồng nghĩa** mọi thao tác lọc rồi ghi đều an toàn trước sai lệch nghiệp vụ.
2. Trạng thái **khóa** có thể thay đổi giữa các kiểu câu lệnh trên cùng một engine. Những tối ưu như chỉ mục, kế hoạch quét và thời điểm bắt đầu transaction còn ảnh hưởng đường khóa thực tế.

## 9. Thực hành write skew trong PostgreSQL

Thí nghiệm sau cho thấy một lịch chạy **không có non-repeatable read và không có phantom trên lần đọc thường**, nhưng vẫn làm hỏng ràng buộc ứng dụng. Chỉ chạy trên môi trường thử nghiệm.

### 9.1. Tạo dữ liệu

~~~sql
CREATE TABLE on_call_roster (
    shift_id  INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    on_call   BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);

INSERT INTO on_call_roster (shift_id, doctor_id, on_call)
VALUES (7, 101, TRUE),
       (7, 102, TRUE);
~~~

Quy tắc nghiệp vụ: ca `shift_id = 7` phải có ít nhất một bác sĩ với `on_call = TRUE`. Đây là ràng buộc **liên hàng**, không được thể hiện chỉ bằng `NOT NULL` hoặc `CHECK` trên một hàng riêng lẻ.

### 9.2. Chạy hai phiên xen kẽ

**Phiên A:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM on_call_roster
WHERE shift_id = 7 AND on_call = TRUE;
-- 2
~~~

**Phiên B (phải đọc trước khi A commit):**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM on_call_roster
WHERE shift_id = 7 AND on_call = TRUE;
-- 2
~~~

**Phiên A tiếp tục:**

~~~sql
-- A tin rằng bác sĩ 102 vẫn còn trực:
UPDATE on_call_roster
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 101;

COMMIT;
~~~

**Phiên B tiếp tục:**

~~~sql
-- B vẫn tin rằng bác sĩ 101 còn trực theo snapshot của B:
UPDATE on_call_roster
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 102;

COMMIT;
~~~

**Kiểm tra sau cùng bằng transaction mới:**

~~~sql
SELECT COUNT(*) AS doctors_on_call
FROM on_call_roster
WHERE shift_id = 7 AND on_call = TRUE;
-- Có thể là 0: cả hai COMMIT thành công ở PostgreSQL REPEATABLE READ.
~~~

Hai transaction ghi lên **hai hàng khác nhau**; REPEATABLE READ không tự phát hiện mối phụ thuộc nghiệp vụ “mỗi bên chỉ nghỉ nếu người còn lại vẫn trực”.

Nếu thử lại từ dữ liệu ban đầu bằng `BEGIN ISOLATION LEVEL SERIALIZABLE` trong cả hai phiên PostgreSQL, hệ quản trị sẽ bảo vệ tính tuần tự hóa của lịch này; một transaction có thể nhận `40001` và phải retry. Sau retry, ứng dụng phải **kiểm tra lại số bác sĩ còn trực trước khi cho nghỉ**.

### 9.3. Các hướng giải quyết

- **Serializable + retry cả transaction:** nếu yêu cầu quy tắc liên hàng phải đúng và hệ quản trị cung cấp bảo đảm phù hợp, đây là phương án rõ ràng. Cần có kiểm tra lại nghiệp vụ ở lần retry.
- **Khóa một hàng bảo vệ chung:** lưu một bản ghi đại diện cho ca trực, rồi cho tất cả thao tác thay ca lấy `SELECT ... FOR UPDATE` trên cùng hàng đó trước khi kiểm tra/sửa roster. Mọi đường cập nhật phải tuân theo cùng giao thức khóa.
- **Thiết kế lại phép ghi/ràng buộc:** có thể mô hình hóa một nguồn sự thật duy nhất cho người phụ trách ca, hoặc dùng cơ chế đồng bộ phù hợp, sao cho trạng thái vi phạm khó có thể được commit. Ràng buộc `CHECK` đơn giản trên từng hàng không kiểm soát được tổng số hàng còn trực.

Không áp dụng một đoạn SQL khóa của PostgreSQL nguyên xi cho SQL Server hoặc Oracle khi chưa đối chiếu cú pháp và cơ chế khóa.

## 10. Thiết kế ranh giới transaction trong Java

Mức cô lập thuộc **transaction trên kết nối đến cơ sở dữ liệu**, chứ không phải thuộc đối tượng entity hay câu lệnh repository độc lập. Nếu một nghiệp vụ cần hai câu đọc chia sẻ snapshot, chúng phải được thực thi **trên cùng transaction** (và đúng loại truy vấn đọc của hệ quản trị).

### 10.1. JDBC: đặt isolation trước khi thực hiện nghiệp vụ

Ví dụ minh họa dùng JDBC và `DataSource` để đọc hai chỉ số trong một transaction. Truy vấn đầu tiên xác lập bối cảnh đọc; truy vấn thứ hai vẫn nằm trong cùng transaction.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountSnapshotService {
    private final DataSource dataSource;

    public AccountSnapshotService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long[] readTwice(long accountId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            int previousIsolation = connection.getTransactionIsolation();
            boolean previousAutoCommit = connection.getAutoCommit();

            try {
                connection.setTransactionIsolation(
                    Connection.TRANSACTION_REPEATABLE_READ);
                connection.setAutoCommit(false);

                long first = readBalance(connection, accountId);
                // Các truy vấn khác của cùng nghiệp vụ có thể chạy tại đây.
                long second = readBalance(connection, accountId);

                connection.commit();
                return new long[] {first, second};
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                // Khôi phục cấu hình trước khi trả kết nối về pool.
                try {
                    connection.setAutoCommit(previousAutoCommit);
                } finally {
                    connection.setTransactionIsolation(previousIsolation);
                }
            }
        }
    }

    private static long readBalance(Connection connection, long accountId)
            throws SQLException {
        String sql = """
            SELECT balance
            FROM account_balances
            WHERE account_id = ?
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, accountId);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException("Account not found: " + accountId);
                }
                return rows.getLong("balance");
            }
        }
    }
}
~~~

Đoạn mã giả định driver hỗ trợ `TRANSACTION_REPEATABLE_READ` và bảng `account_balances` tồn tại. Nó minh họa ranh giới transaction và việc trả kết nối về pool; trong ứng dụng thật, transaction manager hoặc connection pool có thể có quy tắc riêng về khôi phục thuộc tính kết nối và xử lý lỗi khi rollback/cleanup.

Lưu ý:

- Gọi `setTransactionIsolation(...)` trước các câu lệnh nghiệp vụ, theo yêu cầu của driver và hệ quản trị. Không thay isolation giữa một transaction đang chạy.
- `setAutoCommit(false)` cho phép nhiều câu SQL nằm chung transaction; nếu mỗi câu chạy autocommit riêng, hai lần đọc thuộc hai transaction khác nhau.
- `commit()` hoặc `rollback()` để giải phóng transaction sớm. Dùng `try-with-resources` để trả tài nguyên JDBC.
- Nếu dùng connection pool, cần bảo đảm cấu hình session được khôi phục theo chính sách của pool. Không để mức cô lập bị “rò” sang yêu cầu tiếp theo.
- Với các truy vấn chỉ đọc, việc trả cùng số ở PostgreSQL REPEATABLE READ phản ánh snapshot. Không suy rộng điều đó sang locking read InnoDB hoặc mọi implementation khác.

### 10.2. Framework Java và transaction boundary

Với Spring, ví dụ:

~~~java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public AccountReport createReport(long accountId) {
    var header = repository.readHeader(accountId);
    var items = repository.readItems(accountId);
    return new AccountReport(header, items);
}
~~~

`@Transactional` cần được xử lý qua transaction manager thích hợp. Các lời gọi nội bộ không đi qua proxy trong cấu hình Spring phổ biến có thể không mở một transaction mới như mong đợi. Ngoài ra, `readOnly = true` thường là một *hint*/tùy chọn cho framework và driver, **không phải bảo đảm mọi câu lệnh ghi sẽ bị chặn** ở tất cả hệ quản trị.

Với transaction có ghi, ranh giới nên bao trọn việc **đọc điều kiện, quyết định nghiệp vụ và ghi**. Không đọc điều kiện ở một transaction rồi ghi ở transaction khác nếu bảo đảm đồng thời phụ thuộc vào giá trị vừa đọc.

### 10.3. Serialization failure, deadlock và retry

Một transaction có thể thất bại do cạnh tranh, ngay cả khi isolation được nâng lên để bảo vệ tính đúng đắn.

- PostgreSQL có thể báo SQLSTATE `40001` khi không thể tuần tự hóa/xử lý xung đột cập nhật ở các mức phù hợp; deadlock thường có mã `40P01`.
- MySQL/InnoDB có thể báo lỗi deadlock hoặc xung đột khóa theo mã riêng. SQLSTATE và chính sách retry phải dựa vào driver, phiên bản và loại lỗi cụ thể.
- SQL Server có lỗi deadlock victim như mã `1205`; xử lý theo mã lỗi của hệ quản trị/driver.

**Nguyên tắc retry:** phải bắt đầu lại **toàn bộ transaction**, lấy dữ liệu/snapshot mới và đánh giá lại điều kiện nghiệp vụ. Không chỉ retry câu `UPDATE` cuối cùng trong transaction đã thất bại.

Ví dụ pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    try:
        BEGIN transaction with required isolation
        READ current business state
        VALIDATE invariants
        WRITE changes
        COMMIT
        return success
    catch recognized retryable concurrency error:
        ROLLBACK if transaction is still active
        if final attempt: return/error
        back off briefly; restart all steps on a new transaction
~~~

Giới hạn số lần thử, có backoff phù hợp và quan sát số lần retry. Không để transaction chứa các tác dụng phụ bên ngoài khó đảo ngược như gửi email hay gọi API thanh toán rồi tự động lặp lại. Với công việc cần phát sự kiện, cân nhắc thiết kế outbox hoặc cơ chế idempotency để kết quả cuối không bị nhân đôi.

## 11. Ranh giới bảo đảm và chi phí vận hành

REPEATABLE READ không miễn phí, đặc biệt nếu giao dịch giữ tài nguyên quá lâu:

| Tình huống | Điểm cần cân nhắc |
|---|---|
| Báo cáo nhiều câu `SELECT` cần cùng ảnh chụp | Snapshot transaction của PostgreSQL hoặc consistent read InnoDB có thể hữu ích; SQL Server dùng chiến lược khác nếu cần snapshot |
| Giao dịch đọc rồi cập nhật cùng một hàng | PostgreSQL có thể báo `40001` khi gặp cập nhật xung đột; cơ chế khóa khác có thể chờ/deadlock |
| Kiểm tra tổng/đếm rồi ghi nhiều hàng | REPEATABLE READ có thể không giữ được bất biến liên hàng; xem write skew/phantom |
| Transaction đọc quá lâu ở PostgreSQL | Snapshot dài có thể cản trở thu gom các phiên bản hàng cũ, làm tăng áp lực lưu trữ |
| Transaction đọc quá lâu ở InnoDB | Lịch sử undo cần lưu dài hơn; khóa của locking read có thể gây chờ |
| Transaction đọc quá lâu ở SQL Server REPEATABLE READ | Shared locks giữ lâu, làm chậm giao dịch ghi và tăng nguy cơ deadlock |
| Connection pool lớn, transaction dài | Nhiều kết nối bị giữ, tăng thời gian chờ và giảm thông lượng |

Một giao dịch “đọc nhất quán” vẫn có thể đọc **dữ liệu đã cũ** so với thời điểm nó kết thúc. Đó là đặc trưng của snapshot: giữ một góc nhìn ổn định, không phải cam kết đọc sự kiện vừa commit ở nơi khác ngay tức thì.

**Không có mức cô lập nào tự giải quyết hết vấn đề ứng dụng.** Ngay cả SERIALIZABLE cũng cần giao dịch được định nghĩa đúng ranh giới, kiểm tra nghiệp vụ đúng chỗ và xử lý lỗi đúng cách. Việc quản lý lock order, timeout, độ dài transaction, pool, chỉ mục và kế hoạch truy vấn còn quyết định hệ thống có hoạt động ổn định dưới tải hay không.

## 12. Quy trình chọn REPEATABLE READ trong dự án Java

Khi một nhóm đề xuất nâng isolation từ READ COMMITTED lên REPEATABLE READ, hãy làm rõ:

1. **Hiện tượng cần ngăn:** đọc lại cùng hàng đổi giá trị, tập kết quả thay đổi, hay kiểm tra ràng buộc đa hàng bị tranh chấp?
2. **Loại câu SQL:** chỉ có `SELECT` thông thường, hay còn `SELECT ... FOR UPDATE`, `UPDATE`, `DELETE`, thao tác theo khoảng/điều kiện?
3. **Hệ quản trị và engine:** PostgreSQL, InnoDB, SQL Server hay Oracle? Bảo đảm thực tế của mức này là gì trên phiên bản đang chạy?
4. **Độ dài transaction:** bao nhiêu câu SQL, bao lâu, có chờ HTTP/API hay xử lý CPU lâu giữa lúc giữ transaction không?
5. **Cách xử lý xung đột:** có xử lý deadlock/serialization failure, retry cả transaction và giữ các tác dụng phụ bên ngoài idempotent không?
6. **Cách kiểm chứng:** đã chạy thí nghiệm hai session với đúng lịch cạnh tranh và dữ liệu/điều kiện đại diện chưa?

Nếu mục tiêu chỉ là lấy một hàng theo khóa và cập nhật số lượng an toàn, một **câu UPDATE nguyên tử có điều kiện** có thể đơn giản hơn việc giữ transaction lâu:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-001'
  AND available > 0;
~~~

Ứng dụng kiểm tra số hàng bị ảnh hưởng để biết có trừ tồn kho thành công không. Tính đúng đắn của quy tắc cụ thể vẫn phụ thuộc ràng buộc dữ liệu và cách hệ quản trị thực thi thao tác ghi. Ví dụ này minh họa việc đưa phép kiểm tra và ghi vào **một câu lệnh** khi có thể, thay vì đọc giá trị ra Java rồi cập nhật mù.

Đối với cập nhật theo phiên bản, có thể dùng optimistic locking:

~~~sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Nếu số hàng cập nhật là 0, giá trị đã thay đổi hoặc hàng không tồn tại; ứng dụng phải nạp lại dữ liệu hoặc thông báo xung đột. Đây là cơ chế bổ sung kiểm soát đồng thời, không thay thế mọi yêu cầu cô lập và ràng buộc liên hàng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** T1 ở PostgreSQL REPEATABLE READ đọc `balance = 100`. T2 cập nhật lên `150` và commit. T1 chỉ chạy lại `SELECT balance`. T1 nhìn thấy gì?

*Gợi ý:* T1 tiếp tục thấy `100` qua snapshot cũ; transaction mới sau khi T1 kết thúc sẽ nhìn thấy `150` nếu không có ghi khác.

**Câu 2.** Cũng lịch trên ở SQL Server REPEATABLE READ dựa vào khóa. T2 có thể cập nhật hàng T1 đã đọc và commit ngay không?

*Gợi ý:* Thông thường không; shared lock mà T1 giữ trên hàng đã đọc buộc T2 phải chờ hoặc gặp xử lý xung đột theo lịch khóa.

**Câu 3.** T1 ở PostgreSQL REPEATABLE READ chạy hai lần `COUNT(*) WHERE status = 'PENDING'`. T2 chèn hàng PENDING sau snapshot rồi commit. Có phantom quan sát được trong T1 không?

*Gợi ý:* Các `SELECT` thông thường của T1 nhìn cùng snapshot nên không thấy hàng mới từ T2. Điều đó không chứng minh an toàn trước write skew.

**Câu 4.** Ở InnoDB, vì sao `SELECT balance` và `SELECT balance FOR UPDATE` trong cùng transaction có thể cho hai giá trị khác nhau sau khi transaction khác commit?

*Gợi ý:* Một câu là consistent read từ snapshot, câu còn lại là locking/current read theo trạng thái hiện hành và cơ chế khóa.

**Câu 5.** Hai bác sĩ cùng đọc “hiện có hai người trực”, rồi mỗi người cập nhật một hàng khác nhau thành nghỉ. Bảo đảm “đọc lại cùng hàng không đổi” có đủ ngăn cả hai nghỉ không?

*Gợi ý:* Không. Đây là write skew; dùng cách bảo vệ quy tắc liên hàng như Serializable với retry hoặc khóa chung theo giao thức nhất quán.

**Câu 6.** Ứng dụng Java gặp SQLSTATE `40001` sau khi đọc và tính toán trong transaction. Có thể chỉ gọi lại câu `UPDATE` cuối cùng không?

*Gợi ý:* Không. Phải rollback và retry toàn bộ nghiệp vụ giao dịch với dữ liệu mới; số lần retry cần có giới hạn và xử lý idempotency cho tác dụng phụ.

## 14. Ghi nhớ

**REPEATABLE READ bảo vệ việc đọc lại dữ liệu, nhưng giới hạn thực tế phải được hiểu theo hệ quản trị.** PostgreSQL thường dùng snapshot nhất quán xuyên transaction và ngăn phantom ở `SELECT` thông thường, nhưng vẫn có write skew. MySQL/InnoDB phân biệt rõ consistent read với locking/current read và dùng các loại khóa khoảng trong nhiều tình huống. SQL Server REPEATABLE READ dựa vào khóa giữ trên hàng đã đọc, có thể cho phép phantom và gây chờ ghi. Oracle không có mức REPEATABLE READ riêng theo tên.

Trong persistence cho Java, kết quả đúng đến từ **mẫu SQL, ranh giới transaction, lựa chọn isolation đúng engine và xử lý cạnh tranh**, chứ không phải chỉ từ một hằng số JDBC. Hãy kiểm chứng lịch chạy hai phiên, bảo vệ các bất biến nghiệp vụ đa hàng bằng cơ chế phù hợp, giữ transaction ngắn và sẵn sàng retry toàn bộ transaction khi hệ quản trị phát hiện xung đột.
