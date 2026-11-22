# PostgreSQL: MVCC, ảnh chụp và các mức cô lập

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)** để cho nhiều transaction đọc và ghi dữ liệu đồng thời. Thay vì buộc mọi reader phải chờ writer hoàn tất, PostgreSQL duy trì nhiều phiên bản của một dòng và chọn phiên bản phù hợp với ảnh chụp (snapshot) của từng câu lệnh hoặc transaction.

Cơ chế này giúp truy vấn đọc thông thường ít bị blocking bởi thao tác ghi. Đổi lại, database phải quản lý các phiên bản cũ, xác định phiên bản nào được nhìn thấy và thu hồi những phiên bản không còn cần thiết. Isolation level quyết định snapshot được tạo khi nào và transaction có thể nhìn thấy thay đổi của transaction khác ra sao.

Ba mức thường cần hiểu rõ là **READ COMMITTED**, **REPEATABLE READ** và **SERIALIZABLE**. Trong PostgreSQL, REPEATABLE READ cung cấp snapshot ổn định ở cấp transaction và ngăn phantom read; SERIALIZABLE bổ sung Serializable Snapshot Isolation (SSI) để phát hiện các phụ thuộc có thể tạo ra kết quả không tuần tự hóa.

## 1. MVCC giải quyết vấn đề gì?

Trong hệ thống chỉ lưu một phiên bản hiện hành của mỗi dòng, reader có thể phải chờ writer hoặc writer phải chờ reader để tránh đọc dữ liệu đang thay đổi. Khi nhiều request cùng truy cập, việc chờ khóa có thể làm giảm concurrency.

MVCC cho phép database giữ phiên bản cũ trong khi transaction khác tạo phiên bản mới. Reader chọn phiên bản phù hợp với snapshot của mình; writer tạo thay đổi mà không nhất thiết phải chờ các truy vấn đọc thông thường kết thúc.

Ví dụ, tài khoản có số dư ban đầu 1.000:

~~~text
Thời gian
  |
  | T1 bắt đầu đọc snapshot S1
  | T1 đọc balance = 1.000
  |
  | T2 cập nhật balance = 1.200
  | T2 COMMIT
  |
  | T1 đọc lại balance
  | T1 vẫn thấy 1.000 nếu snapshot của T1 chưa đổi
  |
  +------------------------------------>

Các phiên bản:
  V1: balance = 1.000  <- T1 nhìn thấy
  V2: balance = 1.200  <- transaction mới nhìn thấy
~~~

T1 không đọc dữ liệu chưa commit của T2. Sau khi T2 commit, một transaction mới có thể nhìn thấy V2. T1 tiếp tục nhìn thấy V1 nếu isolation level của nó giữ snapshot cũ.

MVCC không tạo một bản sao vật lý toàn bộ database cho mỗi transaction. PostgreSQL lưu các phiên bản dòng trong bảng và sử dụng metadata transaction để quyết định phiên bản nào hiển thị.

## 2. PostgreSQL lưu các phiên bản dòng như thế nào?

Trong PostgreSQL, mỗi lần INSERT, UPDATE hoặc DELETE có thể làm thay đổi metadata của tuple hoặc tạo một phiên bản tuple mới.

Ở mức khái niệm, một tuple có các trường metadata quan trọng:

- **xmin:** transaction ID đã tạo phiên bản tuple đó.
- **xmax:** transaction ID liên quan đến việc xóa hoặc thay thế phiên bản đó; trong một số trường hợp metadata khóa dòng cũng có thể được biểu diễn qua header và infomask liên quan.
- **ctid:** vị trí vật lý của tuple trong trang hiện tại. UPDATE thường tạo phiên bản mới nên ctid có thể thay đổi.

Không nên dùng xmin, xmax hoặc ctid làm khóa nghiệp vụ hay mã phiên bản ứng dụng. Đây là chi tiết triển khai nội bộ; giá trị có thể thay đổi theo vacuum, freeze, update và phiên bản PostgreSQL.

### 2.1. INSERT tạo phiên bản mới

Khi transaction T1 INSERT một dòng:

~~~sql
BEGIN;

INSERT INTO account(account_id, balance)
VALUES (10, 1000);

COMMIT;
~~~

PostgreSQL tạo tuple có xmin gắn với transaction đã insert. Tuple chỉ hiển thị với transaction khác khi transaction tạo nó commit và thỏa quy tắc snapshot của reader.

Nếu T1 rollback, tuple đó không trở thành một dòng đã commit có thể nhìn thấy. Tuple vật lý có thể vẫn tồn tại tạm thời cho đến khi vacuum thu hồi.

### 2.2. UPDATE tạo phiên bản mới

Với một UPDATE thông thường, PostgreSQL thường tạo một tuple version mới thay vì ghi đè nội dung phiên bản cũ tại chỗ:

~~~sql
UPDATE account
SET balance = 1200
WHERE account_id = 10;
~~~

Có thể hình dung:

~~~text
Trước UPDATE:
  V1: balance = 1000
      xmin = transaction tạo V1
      xmax = chưa bị thay thế

Sau UPDATE và COMMIT:
  V1: balance = 1000
      xmax = transaction cập nhật V1

  V2: balance = 1200
      xmin = transaction tạo V2
      xmax = chưa bị thay thế
~~~

Reader có snapshot cũ có thể tiếp tục nhìn thấy V1. Reader có snapshot mới nhìn thấy V2. Khi không còn snapshot nào cần V1, vacuum có thể thu hồi phiên bản cũ.

PostgreSQL có tối ưu HOT (Heap-Only Tuple) cho một số UPDATE khi các cột liên quan đến index không thay đổi và trang còn đủ chỗ. HOT có thể giảm chi phí cập nhật index, nhưng vẫn là một phần của cơ chế quản lý phiên bản.

### 2.3. DELETE đánh dấu phiên bản không còn hiện hành

DELETE thường đánh dấu tuple bằng transaction ID xóa ở metadata xmax. Tuple chưa nhất thiết bị xóa vật lý ngay. Một transaction có snapshot cũ vẫn có thể cần nhìn thấy phiên bản trước khi DELETE commit.

Vì vậy, "đã DELETE" ở mức SQL và "đã thu hồi hoàn toàn khỏi file dữ liệu" là hai thời điểm khác nhau.

## 3. Snapshot là gì và PostgreSQL quyết định visibility ra sao?

Một **snapshot** là tập thông tin cho phép PostgreSQL xác định transaction nào đã hoàn tất, transaction nào còn hoạt động và phiên bản nào được phép nhìn thấy tại một mốc logic.

Có thể mô tả snapshot bằng ba thành phần chính:

- **xmin:** ranh giới transaction ID cũ nhất còn đang hoạt động tại thời điểm snapshot được tạo.
- **xmax:** ranh giới transaction ID mới tiếp theo tại thời điểm snapshot.
- Danh sách transaction ID đang hoạt động trong khoảng đó (thường được gọi là **xip**).

Khi kiểm tra một tuple, PostgreSQL kết hợp snapshot với trạng thái commit/abort của transaction tạo hoặc xóa tuple để quyết định tuple có hiển thị hay không.

Ở mức đơn giản:

- Phiên bản được tạo bởi transaction đã commit trước snapshot có thể hiển thị.
- Phiên bản được tạo bởi transaction còn hoạt động tại lúc snapshot được chụp không hiển thị với reader khác.
- Phiên bản được tạo sau mốc snapshot không hiển thị trong snapshot đó.
- Phiên bản bị xóa bởi transaction đã commit trước snapshot sẽ không còn hiển thị.
- Transaction thường nhìn thấy các thay đổi do chính nó tạo ra, theo quy tắc read-your-own-writes.

Các quy tắc thật có thêm chi tiết về subtransaction, transaction ID wraparound, hint bits và trạng thái commit. Không nên tự viết logic ứng dụng dựa trên phép so sánh xmin/xmax; hãy để PostgreSQL thực hiện visibility check.

### 3.1. Snapshot không phải thời gian đồng hồ chính xác

Snapshot xác định một trạng thái logic của transaction, không nhất thiết là bản ghi chụp tại một timestamp wall-clock duy nhất. Transaction ID và trạng thái hoạt động được dùng để quyết định phiên bản hiển thị.

Vì vậy, snapshot không phải công cụ thay thế timestamp nghiệp vụ hoặc commit timestamp. Nếu ứng dụng cần thời điểm tạo đơn, thời điểm nhận request hoặc thứ tự sự kiện, hãy lưu thông tin nghiệp vụ tương ứng hoặc dùng CDC/log với semantics phù hợp.

### 3.2. Transaction nhìn thấy thay đổi của chính nó

Một transaction có thể đọc lại dữ liệu mà chính nó vừa INSERT hoặc UPDATE, kể cả khi các thay đổi đó chưa commit. Đây là hành vi read-your-own-writes.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO account(account_id, balance)
VALUES (20, 500);

SELECT balance
FROM account
WHERE account_id = 20;

-- Transaction hiện tại nhìn thấy dòng vừa tạo.

ROLLBACK;
~~~

Transaction khác không nhìn thấy dòng này trước khi T1 commit. Nếu T1 rollback, dòng không trở thành dữ liệu đã commit.

## 4. READ COMMITTED: snapshot mới cho mỗi câu lệnh

READ COMMITTED là isolation level mặc định của PostgreSQL. Mỗi câu lệnh SQL thông thường bắt đầu với một snapshot mới. Do đó, hai câu SELECT trong cùng transaction có thể nhìn thấy các trạng thái đã commit khác nhau nếu transaction khác commit ở giữa.

~~~text
Transaction T1 (READ COMMITTED)       Transaction T2
--------------------------------       -------------
BEGIN
SELECT balance -> 1000
                                       UPDATE balance = 1200
                                       COMMIT
SELECT balance -> 1200
COMMIT
~~~

T1 không đọc dữ liệu chưa commit, nhưng lần đọc thứ hai có thể trả về giá trị mới hơn lần đầu. Đây là hành vi non-repeatable read.

### 4.1. Ví dụ hai session

Giả sử bảng:

~~~sql
CREATE TABLE account
(
    account_id bigint PRIMARY KEY,
    balance numeric(14, 2) NOT NULL
);

INSERT INTO account(account_id, balance)
VALUES (1, 1000);
~~~

Session A:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account
WHERE account_id = 1;

-- Tạm dừng tại đây để Session B cập nhật.

SELECT balance
FROM account
WHERE account_id = 1;

COMMIT;
~~~

Session B chạy giữa hai câu SELECT của A:

~~~sql
BEGIN;

UPDATE account
SET balance = 1200
WHERE account_id = 1;

COMMIT;
~~~

Nếu B commit trước câu SELECT thứ hai của A bắt đầu, câu SELECT thứ hai có thể thấy 1.200. Mỗi câu SELECT có snapshot riêng.

### 4.2. Ưu điểm và giới hạn

READ COMMITTED thường phù hợp với các thao tác ngắn, không cần mọi câu lệnh trong transaction nhìn thấy cùng một snapshot.

Ưu điểm:

- Reader thông thường ít bị writer chặn.
- Transaction có thể nhìn thấy dữ liệu mới đã commit ở câu lệnh tiếp theo.
- Snapshot ngắn giúp giảm thời gian giữ các phiên bản cũ.
- Đây là mặc định quen thuộc cho nhiều ứng dụng CRUD.

Giới hạn:

- Đọc lặp lại có thể cho kết quả khác nhau.
- Một truy vấn tổng hợp chạy hai lần có thể trả kết quả khác nhau.
- Các bước SELECT rồi UPDATE riêng có thể đưa ra quyết định dựa trên dữ liệu đã thay đổi.
- Các invariant trải qua nhiều câu lệnh cần được bảo vệ bằng UPDATE nguyên tử, khóa, constraint hoặc isolation mạnh hơn.

### 4.3. READ UNCOMMITTED trong PostgreSQL

PostgreSQL chấp nhận khai báo READ UNCOMMITTED, nhưng thực thi với hành vi tương đương READ COMMITTED. PostgreSQL không cho phép dirty read theo cách mà một số DBMS có thể hỗ trợ.

Do đó, không nên mong đợi:

~~~sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
~~~

sẽ làm transaction đọc được dữ liệu chưa commit. Trong PostgreSQL, nó vẫn dùng semantics READ COMMITTED.

### 4.4. UPDATE có thể đánh giá lại điều kiện sau khi chờ

Ở READ COMMITTED, nếu UPDATE hoặc DELETE tìm thấy một dòng nhưng transaction khác đang cập nhật dòng đó, câu lệnh có thể phải chờ transaction kia. Sau khi transaction kia commit, PostgreSQL thử thao tác trên phiên bản mới hơn và đánh giá lại điều kiện WHERE đối với dòng đó.

Ví dụ:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10
  AND quantity > 0;
~~~

Nếu hai transaction cùng muốn cập nhật một dòng, PostgreSQL phối hợp quyền ghi trên dòng. Transaction đến sau có thể chờ rồi đánh giá điều kiện trên phiên bản mới. Điều này làm câu UPDATE có điều kiện phù hợp hơn mẫu SELECT số lượng rồi gửi một giá trị tuyệt đối đã tính từ trước.

Tuy nhiên, với câu lệnh phức tạp có join hoặc nhiều dòng, các phần khác của câu lệnh vẫn được đánh giá theo snapshot của câu lệnh ban đầu. PostgreSQL có thể phải dùng cơ chế EvalPlanQual để kiểm tra lại dòng đích; kết quả trong một số câu lệnh phức tạp có thể khó suy luận nếu giả định toàn bộ truy vấn nhìn thấy một snapshot đồng nhất sau khi chờ. Với invariant phức tạp, hãy dùng isolation phù hợp hoặc khóa/constraint rõ ràng.

## 5. REPEATABLE READ: một snapshot ổn định trong transaction

Trong PostgreSQL, REPEATABLE READ giữ một snapshot nhất quán cho toàn transaction. Snapshot được thiết lập khi câu lệnh đầu tiên phù hợp bắt đầu thực thi, không nhất thiết ngay tại lệnh BEGIN.

Các câu SELECT tiếp theo tiếp tục đọc cùng trạng thái snapshot, dù transaction khác đã commit phiên bản mới.

~~~text
Transaction T1 (REPEATABLE READ)       Transaction T2
--------------------------------       -------------
BEGIN
SELECT balance -> 1000
                                       UPDATE balance = 1200
                                       COMMIT
SELECT balance -> vẫn là 1000
COMMIT
~~~

Điều này ngăn non-repeatable read và phantom read trong PostgreSQL REPEATABLE READ. Đây là điểm mạnh hơn cách hiểu REPEATABLE READ tối thiểu trong tiêu chuẩn SQL.

### 5.1. Ví dụ hai session

Session A:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM account
WHERE account_id = 1;

-- Tạm dừng để Session B cập nhật và COMMIT.

SELECT balance
FROM account
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
BEGIN;

UPDATE account
SET balance = 1500
WHERE account_id = 1;

COMMIT;
~~~

Nếu snapshot của A đã được thiết lập trước khi B commit, câu SELECT thứ hai của A vẫn nhìn thấy phiên bản 1.000. Sau khi A kết thúc, transaction mới có thể nhìn thấy 1.500.

### 5.2. Phantom read trong PostgreSQL REPEATABLE READ

Giả sử T1 truy vấn tất cả booking của một phòng trong một khoảng. T2 INSERT một booking mới thỏa predicate và commit.

Trong PostgreSQL REPEATABLE READ, T1 tiếp tục dùng snapshot cũ nên truy vấn lặp lại không nhìn thấy dòng mới đó. Vì vậy, PostgreSQL ngăn phantom read ở mức này.

Tuy nhiên, điều đó **không đồng nghĩa REPEATABLE READ bảo đảm serializability**. Hai transaction vẫn có thể đọc dữ liệu liên quan rồi ghi các dòng khác nhau, tạo write skew.

### 5.3. Xung đột khi cập nhật một dòng đã bị thay đổi

Nếu T1 chạy ở REPEATABLE READ và cố UPDATE một dòng mà transaction khác đã cập nhật sau khi snapshot của T1 được thiết lập, PostgreSQL không âm thầm chuyển T1 sang phiên bản mới. T1 thường nhận serialization failure với SQLSTATE **40001**.

Ví dụ:

~~~text
T1 (REPEATABLE READ)                T2
---------------------                --
BEGIN
SELECT balance = 1000
                                     UPDATE balance = 1200
                                     COMMIT
UPDATE balance = 900
Có thể nhận lỗi 40001
ROLLBACK
~~~

T1 cần rollback và chạy lại toàn bộ transaction trên snapshot mới nếu nghiệp vụ cho phép. Chạy lại riêng UPDATE với giá trị 900 có thể giữ nguyên một quyết định được tính từ số dư 1.000 và làm sai nghiệp vụ.

### 5.4. Khi nào nên dùng REPEATABLE READ?

Phù hợp khi nhiều câu SELECT trong cùng transaction cần nhìn thấy cùng một trạng thái dữ liệu, ví dụ:

- Tạo báo cáo cần đọc nhiều bảng trên một snapshot nhất quán.
- Tính toán nhiều giá trị mà không muốn transaction khác làm thay đổi kết quả giữa các câu SELECT.
- Xử lý một tập dữ liệu cần ổn định trong thời gian transaction.
- Đọc dữ liệu trước khi cập nhật, đồng thời sẵn sàng xử lý lỗi 40001 nếu dòng đã bị transaction khác sửa.

Không nên chọn REPEATABLE READ chỉ vì muốn "không bị lỗi đồng thời". Nó có thể phát hiện xung đột bằng cách hủy transaction; đồng thời nó vẫn cho phép write skew trên các dòng khác nhau.

## 6. SERIALIZABLE: snapshot isolation cộng kiểm tra phụ thuộc

PostgreSQL SERIALIZABLE dùng Serializable Snapshot Isolation (SSI). Transaction đọc trên snapshot như REPEATABLE READ, đồng thời PostgreSQL theo dõi các quan hệ đọc/ghi có thể khiến lịch chạy không tương đương một thứ tự tuần tự hợp lệ.

Nếu phát hiện một dangerous structure có nguy cơ tạo serialization anomaly, PostgreSQL hủy một transaction và trả lỗi serialization failure.

~~~text
T1 đọc A, ghi B
T2 đọc B, ghi A

Snapshot riêng có thể cho cả hai cùng thấy trạng thái ban đầu.
SSI theo dõi phụ thuộc đọc/ghi.
Nếu có nguy cơ write skew:
  một transaction bị hủy
  ứng dụng retry toàn bộ transaction
~~~

### 6.1. Vì sao SERIALIZABLE khác REPEATABLE READ?

REPEATABLE READ bảo đảm transaction tiếp tục đọc cùng snapshot và PostgreSQL ngăn phantom read. Nhưng snapshot ổn định không tự bảo đảm các transaction đồng thời có thể được sắp xếp thành một thứ tự chạy tuần tự.

SERIALIZABLE bổ sung SSI để phát hiện các phụ thuộc nguy hiểm. Đây là bảo đảm mạnh hơn, đổi lại ứng dụng cần xử lý serialization failure.

### 6.2. Ví dụ write skew

Một ca trực có hai bác sĩ A và B, và luôn phải có ít nhất một người trực. Ban đầu cả hai đều trực.

~~~text
T1 (SERIALIZABLE)                  T2 (SERIALIZABLE)
------------------                  ------------------
Đọc: A và B đều trực               Đọc: A và B đều trực
Cho A nghỉ                          Cho B nghỉ
UPDATE A = FALSE                   UPDATE B = FALSE
COMMIT                              COMMIT
~~~

Hai transaction cập nhật hai dòng khác nhau. Snapshot isolation đơn thuần có thể để cả hai commit và vi phạm quy tắc. PostgreSQL SSI theo dõi các phụ thuộc rw và hủy một transaction nếu phát hiện nguy cơ không tuần tự hóa.

### 6.3. SIREAD predicate locks không chặn writer như khóa S

PostgreSQL dùng dấu vết đọc SIREAD để ghi nhận dòng, trang, quan hệ hoặc predicate mà transaction SERIALIZABLE đã đọc.

SIREAD:

- Hỗ trợ phát hiện transaction khác ghi vào vùng đã được đọc.
- Không phải khóa chia sẻ thông thường để chặn INSERT/UPDATE.
- Có thể được giữ để theo dõi phụ thuộc ngay cả sau khi transaction đọc kết thúc, nếu transaction khác còn có thể tạo cấu trúc phụ thuộc liên quan.
- Có thể được gộp từ phạm vi chi tiết lên phạm vi rộng để giới hạn bộ nhớ.

Nếu các phụ thuộc tạo dangerous structure, PostgreSQL có thể hủy transaction. Vì vậy, SERIALIZABLE không có nghĩa mọi xung đột đều được xử lý bằng blocking; một số được phát hiện bằng cách abort.

### 6.4. Retry SQLSTATE 40001

Khi gặp serialization failure, ứng dụng cần:

1. Rollback transaction cũ.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu trên snapshot mới.
4. Kiểm tra lại invariant.
5. Tính toán lại và thực hiện ghi.
6. Commit nếu không còn xung đột.

Không chỉ chạy lại câu UPDATE cuối bằng tham số cũ. Nếu transaction gửi email, gọi payment gateway hoặc phát message, cần idempotency/outbox để retry không lặp side effect.

### 6.5. Transaction chỉ đọc và DEFERRABLE

PostgreSQL hỗ trợ:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT ...
FROM orders;

COMMIT;
~~~

Một transaction SERIALIZABLE READ ONLY DEFERRABLE có thể chờ trước khi lấy snapshot cho đến khi database xác định được safe snapshot. Khi đã có snapshot an toàn, transaction chỉ đọc có thể chạy mà không có nguy cơ bị hủy do serialization failure.

Chế độ này hữu ích cho báo cáo dài hoặc tác vụ phân tích chỉ đọc có thể chấp nhận chờ lúc bắt đầu. Nó không dành cho transaction có ghi.

## 7. So sánh các isolation level trong PostgreSQL

| Isolation level | Snapshot | Dirty read | Non-repeatable read | Phantom read | Serialization anomaly |
|---|---|---|---|---|---|
| READ UNCOMMITTED | Tương đương READ COMMITTED | Không | Có thể | Có thể | Có thể |
| READ COMMITTED | Mỗi câu lệnh | Không | Có thể | Có thể | Có thể |
| REPEATABLE READ | Một snapshot cho transaction | Không | Không | Không trong PostgreSQL | Có thể |
| SERIALIZABLE | Snapshot transaction + SSI | Không | Không | Không | Được ngăn bằng cách hủy transaction xung đột |

Bảng mô tả hành vi PostgreSQL. Không nên áp dụng trực tiếp bảng này cho SQL Server, MySQL InnoDB hoặc Oracle chỉ dựa trên tên isolation level. Các sản phẩm có thể triển khai snapshot và khóa khác nhau.

### 7.1. Chọn mức theo yêu cầu

**READ COMMITTED** phù hợp với nhiều thao tác CRUD ngắn, khi mỗi câu lệnh có thể nhìn thấy dữ liệu mới nhất đã commit tại lúc câu lệnh bắt đầu. Dùng UPDATE có điều kiện và constraint để bảo vệ thay đổi quan trọng.

**REPEATABLE READ** phù hợp khi nhiều lần đọc trong cùng transaction cần cùng một snapshot. Chuẩn bị xử lý serialization failure khi cập nhật dòng đã bị thay đổi kể từ snapshot.

**SERIALIZABLE** phù hợp khi transaction cần bảo vệ invariant nhiều dòng hoặc predicate và không thể chấp nhận write skew. Đo tỷ lệ 40001 và thiết kế retry toàn transaction.

Không nên nâng mọi transaction lên SERIALIZABLE mà không đo. Isolation mạnh hơn có thể tăng số lần abort và chi phí xử lý, đặc biệt khi nhiều transaction đọc/ghi cùng predicate.

## 8. Snapshot được thiết lập khi nào?

Trong PostgreSQL, thời điểm tạo snapshot phụ thuộc isolation level:

- READ COMMITTED: mỗi câu lệnh có snapshot mới.
- REPEATABLE READ: snapshot transaction được thiết lập khi câu lệnh đầu tiên phù hợp thực thi.
- SERIALIZABLE: tương tự transaction-level snapshot, kết hợp theo dõi phụ thuộc SSI.

Ví dụ:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

-- Chưa nhất thiết đã chụp snapshot chỉ vì BEGIN chạy.
-- Câu lệnh đọc đầu tiên phù hợp sẽ thiết lập snapshot.

SELECT count(*) FROM orders;

-- Các SELECT tiếp theo dùng cùng snapshot.
~~~

Nếu ứng dụng cần thay đổi isolation level, phải đặt trước khi transaction thực hiện các câu lệnh cần snapshot:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT ...
FROM orders;

COMMIT;
~~~

Không thể tùy ý đổi isolation level sau khi transaction đã bắt đầu thực thi các câu lệnh cần snapshot. Hãy cấu hình ở đầu transaction hoặc qua transaction manager.

Có thể kiểm tra mặc định:

~~~sql
SHOW default_transaction_isolation;
~~~

Đặt isolation level cho session:

~~~sql
SET SESSION CHARACTERISTICS AS TRANSACTION
ISOLATION LEVEL REPEATABLE READ;
~~~

Thay đổi session default không tự thay đổi transaction đã mở. Cần chú ý connection pool có thể tái sử dụng session; ứng dụng nên đặt/reset cấu hình đúng cách để không rò isolation setting sang request khác.

## 9. MVCC và khóa: reader ít chặn writer nhưng không phải không có khóa

Một hiểu lầm phổ biến là MVCC khiến PostgreSQL không cần khóa. Thực tế PostgreSQL vẫn dùng nhiều loại khóa:

- Row-level locks phối hợp các UPDATE/DELETE và locking reads.
- Table-level locks bảo vệ truy cập và thay đổi cấu trúc bảng.
- Predicate SIREAD locks hỗ trợ SSI.
- Advisory locks cho ứng dụng phối hợp tài nguyên logic nếu được sử dụng.
- DDL có thể yêu cầu table lock mạnh và chặn truy cập khác.

Điểm khác biệt là một SELECT thông thường không lấy row-level shared lock chỉ để đọc tuple. Vì thế, reader thường không chặn writer và writer thường không chặn reader thông thường. Tuy nhiên:

- Hai transaction UPDATE cùng một dòng có thể phải chờ nhau.
- SELECT ... FOR UPDATE/SHARE có thể chờ transaction đang giữ khóa dòng.
- DDL có thể chặn SELECT hoặc DML tùy loại khóa.
- Foreign key checks, unique index checks và các ràng buộc có thể tạo chờ.
- SERIALIZABLE có thể hủy transaction vì phụ thuộc dù không có lock wait trực tiếp.

### 9.1. Locking read khác với snapshot read

SELECT thông thường:

~~~sql
SELECT *
FROM account
WHERE account_id = 1;
~~~

Đọc phiên bản phù hợp với snapshot và không khóa dòng theo kiểu SELECT FOR UPDATE.

Locking read:

~~~sql
SELECT *
FROM account
WHERE account_id = 1
FOR UPDATE;
~~~

Yêu cầu khóa dòng để phối hợp với writer khác. Ở READ COMMITTED, nếu phải chờ transaction khác cập nhật dòng, PostgreSQL có thể trả về phiên bản mới nhất sau khi chờ nếu dòng vẫn thỏa điều kiện. Ở REPEATABLE READ hoặc SERIALIZABLE, nếu dòng đã thay đổi kể từ snapshot, transaction có thể nhận lỗi serialization failure.

Dùng FOR UPDATE khi cần bảo vệ một dòng sẽ được cập nhật hoặc cần tuần tự hóa thao tác trên dòng đó. Không thêm locking read vào mọi truy vấn vì nó làm tăng blocking.

## 10. Vacuum và vòng đời phiên bản cũ

MVCC tạo ra nhiều phiên bản tuple. Sau UPDATE hoặc DELETE, phiên bản cũ không thể bị thu hồi ngay nếu một transaction đang mở vẫn có thể nhìn thấy nó trong snapshot.

**VACUUM** dọn các tuple version không còn cần thiết và giúp không gian có thể được tái sử dụng. Autovacuum tự động chạy dựa trên các ngưỡng cấu hình và thống kê bảng.

~~~text
UPDATE một dòng nhiều lần

V1 -> V2 -> V3 -> V4

Transaction cũ còn cần V1?
  Có  -> chưa thể thu hồi V1
  Không -> VACUUM có thể thu hồi V1

Các phiên bản không còn cần thiết:
  được đánh dấu là có thể tái sử dụng không gian
~~~

VACUUM thường làm không gian bên trong relation có thể tái sử dụng cho các tuple mới; nó không nhất thiết thu nhỏ file hệ điều hành ngay. VACUUM FULL có hành vi khác, cần rewrite bảng và thường yêu cầu khóa mạnh hơn.

### 10.1. Transaction dài giữ snapshot cũ

Một transaction REPEATABLE READ hoặc SERIALIZABLE mở lâu có thể giữ snapshot cũ. Khi đó, vacuum phải giữ lại những phiên bản mà snapshot ấy vẫn có thể nhìn thấy.

Ví dụ:

1. T1 mở transaction REPEATABLE READ và đọc dữ liệu.
2. T2 liên tục UPDATE cùng bảng rồi commit.
3. T1 vẫn giữ snapshot cũ.
4. Autovacuum không thể thu hồi một số phiên bản mà T1 còn cần.
5. Dead tuples tích lũy, làm bảng và index phình to hơn.

Transaction **idle in transaction** đặc biệt đáng chú ý: ứng dụng đã gửi câu SQL nhưng không commit/rollback, trong khi connection vẫn giữ transaction mở.

### 10.2. Ảnh hưởng của replication slot

Replication slot có thể giữ lại WAL hoặc giới hạn vacuum cleanup để phục vụ logical decoding/replica. Một slot bị bỏ quên hoặc consumer chậm có thể làm dung lượng WAL tăng và giữ xmin/catalog_xmin lâu hơn cần thiết.

Vì vậy, khi điều tra bloat hoặc vacuum không dọn được tuple cũ, cần kiểm tra cả transaction mở lâu lẫn replication slot, không chỉ nhìn autovacuum log.

### 10.3. XID wraparound và VACUUM FREEZE

Transaction ID của PostgreSQL có phạm vi hữu hạn và cần được xử lý để tránh wraparound. VACUUM có thể freeze các tuple đủ cũ, cho phép hệ thống quản lý tuổi transaction an toàn.

Nếu vacuum freeze không theo kịp, database có thể tiến gần giới hạn wraparound và buộc phải thực hiện vacuum khẩn cấp. Đây là lý do vận hành quan trọng để không giữ transaction mở quá lâu và không để autovacuum bị vô hiệu hóa hoặc thiếu tài nguyên.

## 11. Chẩn đoán snapshot, transaction và vacuum

### 11.1. Xem transaction đang mở lâu

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các cột hữu ích:

- **xact_start:** thời điểm transaction hiện tại bắt đầu.
- **transaction_age:** tuổi transaction tại thời điểm truy vấn.
- **backend_xmin:** xmin mà backend đang giữ, có thể ảnh hưởng đến khả năng vacuum thu hồi phiên bản cũ.
- **state:** phân biệt active, idle, idle in transaction và các trạng thái khác.
- **wait_event_type/wait_event:** cho biết backend đang chờ điều gì.

Một transaction mở lâu không phải lúc nào cũng gây sự cố, nhưng cần hiểu nó có đang giữ snapshot cũ, khóa hoặc connection quan trọng hay không.

### 11.2. Xem dead tuple và hoạt động vacuum

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

n_dead_tup là ước lượng từ thống kê, không phải số đo chính xác tại mọi thời điểm. Dùng nó để xác định bảng cần điều tra, sau đó kết hợp với kích thước relation, autovacuum log và transaction age.

Có thể xem tiến trình vacuum đang chạy trên các phiên bản PostgreSQL hỗ trợ view này:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

### 11.3. Xem khóa và blocking

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
~~~

Truy vấn này giúp tìm session đang bị block. Nếu không có blocker nhưng ứng dụng vẫn nhận lỗi 40001, nguyên nhân có thể là serialization conflict của SSI chứ không phải lock wait.

### 11.4. Kiểm tra isolation level

~~~sql
SHOW transaction_isolation;
SHOW default_transaction_isolation;
~~~

Lệnh đầu cho biết isolation level của transaction hiện tại; lệnh sau cho biết mặc định của session. Khi dùng connection pool, hãy kiểm tra cấu hình ở đúng connection mà request đang sử dụng.

## 12. Thực hành chọn isolation và viết transaction an toàn

Một số mẫu thường dùng trong PostgreSQL:

### Đọc thông thường, mỗi câu lệnh có thể thấy dữ liệu mới

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account
WHERE account_id = 1;

UPDATE account
SET balance = balance + 100
WHERE account_id = 1;

COMMIT;
~~~

Đây là lựa chọn phù hợp cho nhiều thao tác CRUD ngắn. Nếu logic phụ thuộc vào một điều kiện, nên đặt điều kiện ngay trong UPDATE hoặc dùng constraint thay vì dựa trên một SELECT cũ.

### Đọc nhiều bảng trên cùng snapshot

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT ...
FROM orders
JOIN order_items USING (order_id);

SELECT ...
FROM customers;

COMMIT;
~~~

Các câu SELECT dùng cùng snapshot, giúp một báo cáo đọc nhiều phần dữ liệu trên một trạng thái nhất quán. Nếu transaction ghi vào dòng đã bị transaction khác thay đổi sau snapshot, có thể nhận 40001.

### Bảo vệ invariant nhiều dòng

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10
  AND on_call;

-- Kiểm tra invariant và cập nhật trong cùng transaction.

COMMIT;
~~~

Ứng dụng phải có cơ chế rollback và retry toàn bộ transaction khi nhận SQLSTATE 40001. Nếu invariant có thể được bảo vệ đơn giản hơn bằng constraint hoặc guard row, hãy cân nhắc giải pháp đó để giảm số lần abort.

### Dùng UPDATE nguyên tử cho điều kiện một dòng

~~~sql
UPDATE inventory
SET quantity = quantity - $2
WHERE product_id = $1
  AND $2 > 0
  AND quantity >= $2
RETURNING quantity;
~~~

Nếu UPDATE trả về một dòng, số lượng đã được trừ. Nếu không có dòng, sản phẩm không tồn tại hoặc không đủ số lượng. Kiểm tra số dòng trả về và xử lý kết quả trong cùng transaction với các thay đổi nghiệp vụ liên quan.

## 13. Các lỗi thường gặp khi làm việc với MVCC

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Hai SELECT trong một transaction trả kết quả khác nhau | READ COMMITTED tạo snapshot mới cho từng câu lệnh | Dùng REPEATABLE READ nếu cần snapshot transaction ổn định |
| REPEATABLE READ nhận 40001 khi UPDATE | Dòng đã bị transaction khác thay đổi sau snapshot | Rollback và retry toàn bộ transaction |
| Cả hai transaction commit nhưng invariant bị vi phạm | Write skew dưới snapshot isolation | Dùng SERIALIZABLE, guard row hoặc constraint phù hợp |
| SELECT thông thường không chờ UPDATE | MVCC cho reader thấy phiên bản phù hợp | Đây là hành vi bình thường; dùng locking read nếu cần khóa |
| Transaction idle in transaction lâu | Ứng dụng chưa kết thúc transaction | Kết thúc transaction sớm, kiểm tra connection lifecycle |
| Bảng tăng kích thước dù đã DELETE | Tuple cũ chờ vacuum hoặc không gian chỉ được tái sử dụng nội bộ | Kiểm tra vacuum, transaction age và replication slot |
| Autovacuum không thu hồi dead tuple | Snapshot cũ hoặc xmin horizon bị giữ lâu | Tìm transaction/replication slot giữ xmin |
| SERIALIZABLE có nhiều lỗi 40001 | Các transaction chồng lấn và tạo phụ thuộc nguy hiểm | Retry có giới hạn, tối ưu phạm vi đọc và rút ngắn transaction |

## 14. Những nguyên tắc cần ghi nhớ

- PostgreSQL dùng MVCC để duy trì nhiều phiên bản tuple và chọn phiên bản phù hợp với snapshot của transaction.
- xmin và xmax là metadata nội bộ về vòng đời phiên bản; không dùng chúng làm ID nghiệp vụ.
- UPDATE thường tạo tuple version mới; DELETE đánh dấu phiên bản cũ để visibility và vacuum xử lý.
- READ COMMITTED tạo snapshot mới cho mỗi câu lệnh, nên đọc lặp lại có thể thấy dữ liệu mới đã commit.
- PostgreSQL READ UNCOMMITTED hoạt động tương đương READ COMMITTED; dirty read không xảy ra.
- REPEATABLE READ giữ một snapshot cho transaction và trong PostgreSQL ngăn cả phantom read, nhưng vẫn có thể xảy ra write skew.
- SERIALIZABLE dùng SSI và SIREAD để phát hiện phụ thuộc nguy hiểm; transaction có thể bị hủy với SQLSTATE 40001.
- Khi nhận serialization failure, rollback và thực thi lại toàn bộ transaction trên snapshot mới.
- SELECT thông thường ít chặn writer, nhưng UPDATE, locking read, DDL và các constraint vẫn có thể tạo blocking.
- Transaction dài giữ snapshot cũ có thể ngăn vacuum thu hồi tuple version, làm tăng bloat và áp lực vận hành.
- Autovacuum, VACUUM FREEZE và quản lý replication slot đều quan trọng để duy trì vòng đời MVCC.
- Chọn isolation level theo invariant nghiệp vụ; kết hợp UPDATE nguyên tử, constraint, khóa và retry khi phù hợp.

MVCC giúp PostgreSQL phục vụ nhiều lượt đọc và ghi đồng thời bằng cách cho mỗi transaction nhìn thấy phiên bản dữ liệu phù hợp với snapshot của nó. Isolation level quyết định snapshot có ổn định qua nhiều câu lệnh hay không và database phải phát hiện những phụ thuộc nào trước khi cho phép commit. Khi hiểu cách snapshot, tuple version và vacuum phối hợp, bạn có thể chọn isolation phù hợp, xử lý xung đột có chủ đích và tránh để transaction dài làm tăng chi phí lưu giữ phiên bản cũ.

