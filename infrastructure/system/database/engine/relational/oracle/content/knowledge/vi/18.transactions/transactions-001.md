# Đơn vị công việc nghiệp vụ và các thuộc tính ACID trong Oracle

Một giao dịch chuyển tiền thường gồm nhiều thao tác: kiểm tra tài khoản, trừ tiền ở tài khoản nguồn, cộng tiền vào tài khoản đích và ghi nhận lịch sử. Nếu chỉ một bước thành công rồi ứng dụng gặp lỗi, dữ liệu có thể rơi vào trạng thái không hợp lệ: tiền đã bị trừ nhưng chưa được cộng, hoặc số dư thay đổi mà không có lịch sử tương ứng. Để tránh tình trạng đó, các thao tác thuộc cùng một **đơn vị công việc nghiệp vụ** phải được thực hiện trong một transaction có ranh giới rõ ràng.

Trong Oracle Database, transaction là đơn vị công việc mà hệ quản trị cam kết thực hiện theo các thuộc tính **ACID**:

- **Atomicity (tính nguyên tử):** tất cả thay đổi trong transaction cùng được xác nhận, hoặc các thay đổi chưa commit được hoàn tác.
- **Consistency (tính nhất quán):** transaction đưa dữ liệu từ một trạng thái hợp lệ sang một trạng thái hợp lệ khác theo các quy tắc được bảo vệ.
- **Isolation (tính cô lập):** các transaction đồng thời không nhìn thấy dữ liệu chưa commit của nhau; mức cô lập quyết định cách chúng quan sát thay đổi đã commit.
- **Durability (tính bền vững):** sau khi commit thành công theo chế độ mặc định, Oracle bảo đảm các thay đổi có thể được khôi phục sau sự cố nhờ redo.

Bài học thuộc nhóm **Giao dịch** của Database Engine Relational Oracle. Nội dung tập trung vào việc xác định ranh giới transaction theo nghiệp vụ, cách Oracle quản lý commit/rollback, undo/redo, read consistency, row locks và isolation levels, cùng cách điều khiển transaction từ PL/SQL và JDBC.

Sau bài này, bạn có thể:

- Xác định những thao tác nào phải nằm trong cùng một đơn vị công việc nghiệp vụ.
- Giải thích bốn thuộc tính ACID bằng ví dụ dữ liệu cụ thể.
- Dùng COMMIT, ROLLBACK và SAVEPOINT đúng thời điểm.
- Hiểu Oracle tạo transaction khi thực hiện DML và xử lý DDL có implicit commit.
- Phân biệt undo và redo trong rollback, read consistency và crash recovery.
- Hiểu READ COMMITTED, SERIALIZABLE và READ ONLY trong Oracle.
- Dự đoán hành vi khóa hàng, SELECT FOR UPDATE, deadlock và lỗi ORA-08177.
- Quản lý transaction trong JDBC, tránh autocommit làm vỡ một đơn vị công việc.
- Thiết kế retry, idempotency và xử lý tác động ngoài database một cách an toàn.

> **Phạm vi ví dụ:** Cú pháp minh họa theo Oracle Database 19c. Các bảng có hậu tố _LAB là bảng thực hành độc lập. Không chạy ví dụ chuyển tiền, DDL hoặc thử nghiệm khóa trên schema ứng dụng đang hoạt động.

## 1. Đơn vị công việc nghiệp vụ là gì?

Một đơn vị công việc nghiệp vụ (business unit of work) là tập hợp các thay đổi dữ liệu cần được xem như một kết quả hoàn chỉnh đối với nghiệp vụ. Nó thường tương ứng với một hành động mà người dùng hoặc hệ thống hiểu là một việc duy nhất: đặt hàng, thanh toán, chuyển tiền, xuất kho, chốt hóa đơn hoặc ghi nhận một lần đăng ký.

Ví dụ một giao dịch chuyển tiền:

1. Xác định tài khoản nguồn và tài khoản đích.
2. Trừ số tiền cần chuyển ở tài khoản nguồn.
3. Cộng cùng số tiền đó vào tài khoản đích.
4. Ghi một bản ghi lịch sử chuyển tiền.
5. Xác nhận tất cả thay đổi.

Các bước 2, 3 và 4 không nên trở thành những transaction độc lập nếu nghiệp vụ yêu cầu chúng thành công cùng nhau. Nếu bước 3 lỗi sau khi bước 2 đã commit, tiền bị mất khỏi hệ thống theo góc nhìn nghiệp vụ.

~~~text
MOT HANH DONG: CHUYEN 500
          |
          v
  Tru 500 tai khoan A
          |
          v
  Cong 500 tai khoan B
          |
          v
  Ghi lich su giao dich
          |
          v
       COMMIT
          |
          v
  MOT KET QUA HOAN CHINH

Neu mot buoc that bai truoc COMMIT:
          |
          v
       ROLLBACK
          |
          v
  Khong giu cac thay doi cua transaction
~~~

### 1.1. Ranh giới transaction không nhất thiết bằng một câu SQL

Một câu UPDATE có thể là một transaction đơn giản. Nhưng một đơn đặt hàng có thể cần nhiều câu lệnh:

- Tạo order header.
- Tạo một hoặc nhiều order lines.
- Giảm tồn kho.
- Ghi nhận khoản phải thu hoặc thanh toán.
- Cập nhật trạng thái đơn.

Nếu các thay đổi này phải cùng tồn tại, hãy đặt chúng trong một transaction do một tầng chịu trách nhiệm điều khiển. Khi tất cả bước hoàn tất, tầng đó commit. Khi có lỗi, tầng đó rollback.

### 1.2. Không gom mọi thứ vào một transaction dài

Transaction nên đủ rộng để bao phủ đơn vị công việc, nhưng đủ ngắn để không giữ khóa và undo lâu hơn cần thiết. Tránh:

- Mở transaction rồi chờ người dùng nhập thêm thông tin.
- Giữ transaction trong lúc gọi API thanh toán, gửi email hoặc tải tệp lớn.
- Đọc hàng nghìn dòng rồi giữ khóa trong khi thực hiện xử lý không liên quan.
- Commit từng bước nhỏ trong một nghiệp vụ mà các bước phải thành công cùng nhau.

Nếu nghiệp vụ kéo dài qua nhiều dịch vụ hoặc nhiều phút, thường cần một quy trình nhiều bước có trạng thái, idempotency và cơ chế bù trừ (saga), thay vì giữ một transaction database mở xuyên suốt.

## 2. ACID nhìn từ một giao dịch chuyển tiền

Giả sử tài khoản A có 1.000, tài khoản B có 300. Người dùng chuyển 200 từ A sang B. Kết quả hợp lệ phải là A còn 800 và B có 500, đồng thời lịch sử ghi đúng số tiền 200.

| Thuộc tính | Câu hỏi | Bảo đảm cần có |
| --- | --- | --- |
| Atomicity | Nếu một bước thất bại, dữ liệu còn dở dang không? | Không giữ một phần thay đổi chưa commit |
| Consistency | Số dư có thể âm hoặc lịch sử không khớp không? | Các quy tắc nghiệp vụ/constraint vẫn được thỏa |
| Isolation | Hai giao dịch chuyển tiền đồng thời có ghi đè hoặc đọc dữ liệu chưa commit không? | Transaction quan sát dữ liệu theo isolation semantics và xung đột được xử lý |
| Durability | Sau khi commit rồi máy chủ gặp sự cố, giao dịch có mất không? | Redo cho phép khôi phục thay đổi đã commit |

ACID là đặc tính của transaction database, nhưng **Consistency còn phụ thuộc vào quy tắc mà ứng dụng và schema thực sự định nghĩa**. Oracle không tự biết rằng tổng tiền chuyển đi phải bằng tổng tiền nhận; lập trình viên phải biểu diễn bất biến đó bằng SQL, constraint, trigger hoặc logic nghiệp vụ phù hợp.

## 3. Atomicity — tất cả hoặc không có gì

### 3.1. Một transaction có nhiều DML

~~~sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 200
WHERE account_id = 20;

INSERT INTO transfer_history (
    transfer_id, from_account_id, to_account_id, amount, created_at
)
VALUES (
    9001, 10, 20, 200, SYSTIMESTAMP
);

COMMIT;
~~~

Ba thay đổi thuộc cùng một transaction nếu không có COMMIT/ROLLBACK xen giữa. Nếu câu INSERT lỗi và ứng dụng rollback transaction, hai UPDATE chưa commit cũng được hoàn tác.

### 3.2. Một câu lệnh lỗi không tự rollback mọi câu trước đó

Đây là điểm cần hiểu rõ trong Oracle:

- Một câu SQL bị lỗi thường được rollback ở phạm vi câu lệnh đó (statement-level rollback).
- Các câu DML thành công trước đó trong cùng transaction vẫn còn hiệu lực tạm thời và vẫn có thể được commit.
- Ứng dụng phải quyết định rollback toàn transaction khi đơn vị công việc nghiệp vụ không thể hoàn thành.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 10;

-- Cau INSERT sau co the that bai do vi pham constraint.
INSERT INTO transfer_history (
    transfer_id, from_account_id, to_account_id, amount, created_at
)
VALUES (
    9001, 10, 20, -200, SYSTIMESTAMP
);
~~~

Nếu INSERT lỗi, UPDATE trừ tiền trước đó không tự biến mất. Transaction vẫn còn thay đổi chưa commit. Nếu ứng dụng bắt lỗi rồi tiếp tục COMMIT, số dư có thể bị trừ mà không có lịch sử. Vì vậy, tầng sở hữu transaction phải rollback khi nghiệp vụ thất bại.

### 3.3. COMMIT và ROLLBACK

~~~sql
-- Xac nhan cac thay doi trong transaction hien tai.
COMMIT;

-- Huy tat ca thay doi chua commit trong transaction hien tai.
ROLLBACK;
~~~

Sau COMMIT, các thay đổi trở thành kết quả đã xác nhận và không thể được hoàn tác bằng ROLLBACK thông thường. Muốn đảo ngược một nghiệp vụ đã commit, ứng dụng cần một giao dịch bù trừ mới (ví dụ tạo bút toán hoàn tiền), có audit trail riêng.

ROLLBACK hoàn tác các thay đổi chưa commit trong transaction hiện tại. Nó không hoàn tác một transaction đã commit trước đó.

### 3.4. Transaction tự động kết thúc khi session kết thúc

Nếu session kết thúc bình thường mà transaction còn mở, client/driver thường cần rollback hoặc xử lý transaction trước khi đóng kết nối; không nên dựa vào hành vi ngầm. Nếu session bị mất bất thường, Oracle phục hồi/rollback các transaction chưa commit theo cơ chế recovery. Ứng dụng vẫn phải chủ động commit hoặc rollback để giải phóng tài nguyên đúng thời điểm.

## 4. Consistency — duy trì các bất biến dữ liệu

Consistency nghĩa là transaction phải đưa database từ một trạng thái thỏa các quy tắc sang trạng thái khác cũng thỏa các quy tắc. Những quy tắc đó có thể được bảo vệ ở nhiều tầng.

### 4.1. Dùng constraint cho bất biến dữ liệu

Ví dụ bảng tài khoản:

~~~sql
CREATE TABLE account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(60 CHAR) NOT NULL,
    balance NUMBER(18,2) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative
        CHECK (balance >= 0)
);
~~~

Các quy tắc được bảo vệ:

- Mỗi account_id là duy nhất.
- account_name không được NULL.
- balance không được NULL và không được âm.

Constraint được database kiểm tra bất kể thay đổi đến từ ứng dụng Java, PL/SQL, SQL client hay batch job. Đây là lớp bảo vệ quan trọng cho bất biến ở cấp dữ liệu.

### 4.2. Constraint không thay thế mọi quy tắc nghiệp vụ

Một CHECK constraint trên một dòng không dễ biểu diễn quy tắc tổng số tiền chuyển đi và nhận vào phải cân bằng giữa nhiều dòng. Một số bất biến cần:

- Foreign key để bảo vệ quan hệ tham chiếu.
- Unique constraint để bảo vệ tính duy nhất.
- Check constraint để bảo vệ điều kiện trên một hàng.
- Transaction logic để cập nhật nhiều bảng cùng nhau.
- Trigger hoặc cơ chế nghiệp vụ khác trong những trường hợp phù hợp.

Không nên đưa toàn bộ nghiệp vụ vào trigger một cách tùy tiện; cần xem khả năng kiểm thử, thứ tự thực thi, lỗi và tính minh bạch của quy tắc.

### 4.3. Kiểm tra số dư theo cách an toàn

Mẫu dễ mắc race condition:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10;

-- Ung dung doc balance, tu tinh balance - amount,
-- sau do gui UPDATE bang gia tri da doc.
~~~

Hai session có thể cùng đọc số dư 100, mỗi session định chuyển 80. Nếu cả hai sau đó ghi một giá trị được tính từ số dư cũ, một cập nhật có thể ghi đè hoặc kết quả nghiệp vụ không như mong muốn.

Một cách an toàn hơn là đưa điều kiện đủ số dư vào chính UPDATE:

~~~sql
UPDATE account_lab
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Sau đó kiểm tra số dòng bị ảnh hưởng:

- 1 dòng: tài khoản tồn tại và đủ số dư tại thời điểm UPDATE được thực hiện.
- 0 dòng: không tìm thấy tài khoản hoặc số dư không đủ; ứng dụng có thể truy vấn riêng để phân biệt nếu nghiệp vụ cần.

UPDATE khóa hàng cần thay đổi và điều kiện được đánh giá trong ngữ cảnh thực thi DML, tránh mẫu đọc rồi ghi dựa trên một giá trị cũ mà không có kiểm soát.

### 4.4. Deferred constraints

Oracle hỗ trợ một số constraint có thể khai báo DEFERRABLE. Khi constraint được hoãn, việc kiểm tra có thể được thực hiện tại thời điểm COMMIT thay vì sau từng câu lệnh, theo trạng thái constraint.

Ví dụ khái niệm:

~~~sql
ALTER TABLE transfer_line_lab
ADD CONSTRAINT fk_transfer_header_lab
FOREIGN KEY (transfer_id)
REFERENCES transfer_header_lab(transfer_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Trong transaction, constraint deferred có thể cho phép trạng thái trung gian tạm thời chưa thỏa quan hệ, miễn là trạng thái cuối khi commit hợp lệ. Có thể điều khiển bằng SET CONSTRAINTS với các constraint deferrable.

Không phải mọi constraint đều có thể hoãn. Constraint NOT NULL và CHECK không được điều khiển như deferred foreign key/unique constraint theo cùng cách. Hãy kiểm tra loại constraint và cú pháp Oracle trước khi thiết kế dựa vào deferred validation.

## 5. Isolation — các transaction đồng thời nhìn thấy gì?

Oracle sử dụng cơ chế multi-version read consistency. Thay vì buộc truy vấn đọc phải chờ mọi writer, Oracle có thể cung cấp phiên bản dữ liệu nhất quán từ undo để truy vấn nhìn thấy trạng thái phù hợp với thời điểm snapshot.

### 5.1. Oracle không cho đọc dữ liệu chưa commit

Giả sử Session A:

~~~sql
UPDATE account_lab
SET balance = 500
WHERE account_id = 10;
-- Chua COMMIT.
~~~

Session B:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10;
~~~

Trong READ COMMITTED mặc định, Session B không đọc giá trị 500 chưa commit của A. Nó đọc phiên bản đã commit gần nhất tại thời điểm statement của B bắt đầu. Đây là lý do Oracle không cung cấp dirty read theo kiểu READ UNCOMMITTED.

Nếu Session A rollback, giá trị chưa commit biến mất. Nếu Session A commit, một statement mới của B có thể nhìn thấy giá trị mới.

### 5.2. READ COMMITTED là mức mặc định

Trong READ COMMITTED:

- Mỗi câu SELECT có read-consistent snapshot riêng tại thời điểm statement bắt đầu.
- SELECT không thấy dữ liệu chưa commit của transaction khác.
- Hai câu SELECT trong cùng transaction có thể thấy các trạng thái đã commit khác nhau nếu transaction khác commit ở giữa hai câu.
- DML khóa các hàng mà nó thay đổi; writer khác cần thay đổi cùng hàng phải chờ hoặc xử lý theo chế độ khóa.

Ví dụ:

~~~sql
-- Session B, statement 1:
SELECT balance FROM account_lab WHERE account_id = 10;

-- Session A cap nhat va COMMIT.

-- Session B, statement 2:
SELECT balance FROM account_lab WHERE account_id = 10;
~~~

Hai câu SELECT của B có thể trả giá trị khác nhau. Điều này không phải dirty read: mỗi statement đều đọc một snapshot đã commit hợp lệ tại thời điểm riêng của nó.

### 5.3. SERIALIZABLE cung cấp snapshot ở cấp transaction

Có thể bắt đầu transaction ở mức SERIALIZABLE:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM account_lab
WHERE account_id = 10;

-- Cac truy van tiep theo trong transaction doc snapshot
-- tai thoi diem transaction bat dau.

COMMIT;
~~~

Lệnh SET TRANSACTION phải được thực hiện ở đầu transaction, trước các câu lệnh khác thuộc transaction. Với SERIALIZABLE, các truy vấn trong transaction nhìn một snapshot nhất quán từ lúc transaction bắt đầu. Nếu transaction cố sửa một hàng đã bị transaction khác thay đổi sau snapshot đó, Oracle có thể trả lỗi ORA-08177: can't serialize access for this transaction.

Ứng dụng cần rollback và có thể thử lại **toàn bộ transaction** khi nghiệp vụ cho phép. Không chỉ chạy lại câu UPDATE cuối cùng, vì các quyết định trước đó có thể dựa trên snapshot đã cũ.

### 5.4. READ ONLY transaction

Nếu cần chạy một nhóm truy vấn báo cáo trên cùng snapshot và không ghi dữ liệu:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM account_lab;
SELECT SUM(balance) FROM account_lab;
SELECT account_id, balance FROM account_lab;

COMMIT;
~~~

READ ONLY transaction dùng read-consistent snapshot cho các truy vấn và không cho phép DML trong transaction đó. Đây là lựa chọn hữu ích cho một tác vụ đọc nhiều câu cần cùng một góc nhìn dữ liệu. Nó không thay thế transaction write và không biến nhiều câu SELECT thành một báo cáo có thể đọc dữ liệu mới nhất độc lập ở từng statement như READ COMMITTED.

### 5.5. So sánh các mức transaction thường dùng

| Chế độ | Snapshot đọc | Dirty read | Ghi dữ liệu |
| --- | --- | --- | --- |
| READ COMMITTED | Mỗi statement | Không | Có |
| SERIALIZABLE | Một snapshot ở cấp transaction | Không | Có, có thể gặp ORA-08177 khi xung đột |
| READ ONLY | Một snapshot ở cấp transaction | Không | Không |

Oracle không hỗ trợ mức READ UNCOMMITTED theo cách cho phép đọc dữ liệu chưa commit. Khi cần nhất quán qua nhiều statement, hãy cân nhắc SERIALIZABLE hoặc READ ONLY và hiểu tác động đến lỗi ghi đồng thời, thời gian transaction và undo.

## 6. Durability — điều gì xảy ra sau COMMIT?

### 6.1. Redo log và cam kết commit

Oracle ghi thông tin thay đổi vào redo log. Khi COMMIT thành công theo cấu hình mặc định, redo cần thiết cho transaction được ghi bền vững vào online redo log trước khi Oracle xác nhận commit cho client. Các data block đã thay đổi có thể được DBWR ghi xuống data files sau đó; commit không đòi hỏi tất cả data block phải được ghi ngay lập tức.

Khi instance gặp sự cố, Oracle dùng redo để roll forward các thay đổi cần thiết và dùng undo để rollback các transaction chưa commit trong quá trình recovery. Vì vậy dữ liệu đã commit có thể được khôi phục ngay cả khi data block tương ứng chưa được ghi ra data file tại thời điểm sự cố.

### 6.2. COMMIT không đơn giản là ghi ngay toàn bộ bảng xuống đĩa

Các thành phần có vai trò khác nhau:

| Thành phần | Vai trò khái quát |
| --- | --- |
| Online redo log | Lưu bản ghi redo để phục hồi thay đổi |
| LGWR | Ghi redo buffer ra redo log files |
| DBWR | Ghi các dirty data blocks từ buffer cache xuống data files |
| Undo segments | Giữ thông tin cần để rollback và dựng phiên bản đọc nhất quán |
| Checkpoint | Điều phối tiến độ ghi và recovery; không thay thế redo |

Một COMMIT thành công không có nghĩa DBWR đã ghi mọi data block của transaction xuống datafile. Durability dựa trên redo đã được bảo vệ theo commit protocol.

### 6.3. Cấu hình commit có thể ảnh hưởng thời điểm phản hồi

Oracle có các tùy chọn liên quan commit write/wait. Cấu hình mặc định hướng tới commit wait cho redo cần thiết được ghi. Một số chế độ NOWAIT/không đồng bộ có thể thay đổi thời điểm client nhận phản hồi và mức bảo đảm tại thời điểm trả về. Không thay đổi COMMIT_WRITE hoặc tham số liên quan chỉ để giảm latency nếu chưa hiểu yêu cầu durability và chính sách DBA.

### 6.4. Commit đã thành công nhưng client mất kết nối

Một trường hợp khó: server có thể đã commit, nhưng phản hồi COMMIT bị mất trên đường truyền. Ứng dụng không biết chắc transaction đã commit hay chưa. Nếu tự động gửi lại yêu cầu chuyển tiền, có thể tạo giao dịch trùng.

Đây là lý do hệ thống nghiệp vụ cần **idempotency key** hoặc mã yêu cầu duy nhất. Database nên lưu mã nghiệp vụ duy nhất cùng kết quả; khi client thử lại cùng một request, ứng dụng nhận ra request đã được xử lý và trả lại kết quả cũ thay vì thực hiện lần hai.

## 7. Undo và redo: hai cơ chế khác nhau

### 7.1. Undo dùng cho rollback và read consistency

Undo giữ thông tin về phiên bản dữ liệu trước khi thay đổi. Oracle dùng undo để:

- Hoàn tác thay đổi của transaction chưa commit.
- Cung cấp phiên bản cũ cho truy vấn cần read consistency.
- Hỗ trợ một số thao tác phục hồi logic như flashback query trong phạm vi cấu hình/retention phù hợp.

Undo không phải bản sao lưu đầy đủ thay thế backup. Undo retention và dung lượng undo ảnh hưởng khả năng giữ phiên bản cũ đủ lâu cho truy vấn dài.

### 7.2. Redo dùng cho recovery

Redo ghi lại các thay đổi cần thiết để khôi phục database. Nó hỗ trợ roll forward sau instance/media recovery. Redo cũng ghi thông tin thay đổi liên quan đến undo để các thao tác phục hồi có thể tái tạo trạng thái phù hợp.

### 7.3. Bảng so sánh

| Cơ chế | Câu hỏi chính | Dùng ở đâu |
| --- | --- | --- |
| Undo | Làm sao quay lại phiên bản trước hoặc rollback thay đổi chưa commit? | ROLLBACK, consistent read, recovery |
| Redo | Làm sao tái áp dụng thay đổi sau sự cố? | Instance recovery, media recovery |

Không nên hiểu undo là “dữ liệu chưa commit” và redo là “dữ liệu đã commit” một cách tuyệt đối. Redo được tạo cho các thay đổi database, bao gồm cả thay đổi undo; việc một transaction cuối cùng commit hay rollback được xử lý trong recovery dựa trên redo và undo.

### 7.4. ORA-01555: snapshot too old

Một truy vấn đọc lâu cần phiên bản dữ liệu cũ từ undo. Nếu undo block cần thiết đã bị ghi đè/tái sử dụng trước khi truy vấn hoàn tất, Oracle có thể báo ORA-01555: snapshot too old.

Nguyên nhân và biện pháp phụ thuộc workload:

- Transaction đọc quá lâu trong khi hệ thống có nhiều DML.
- Undo tablespace/retention không đáp ứng thời gian truy vấn.
- Truy vấn quét lượng dữ liệu lớn hoặc thực hiện nhiều xử lý không cần thiết.
- Thiết kế batch commit quá thường xuyên hoặc đọc dữ liệu theo cách không phù hợp.

Không khắc phục bằng cách tăng undo retention một cách mù quáng. DBA cần xem undo usage, workload, query plan, retention guarantee và dung lượng lưu trữ.

## 8. COMMIT, ROLLBACK và SAVEPOINT

### 8.1. SAVEPOINT tạo mốc rollback bên trong transaction

~~~sql
UPDATE account_lab
SET balance = balance - 50
WHERE account_id = 10;

SAVEPOINT after_debit;

UPDATE account_lab
SET balance = balance + 50
WHERE account_id = 20;

-- Neu muon huy cac thay doi sau savepoint:
ROLLBACK TO after_debit;

-- Sau do co the tiep tuc thao tac hoac rollback/commit transaction.
~~~

ROLLBACK TO SAVEPOINT hoàn tác thay đổi sau savepoint được chỉ định, nhưng không kết thúc transaction. Các thay đổi trước savepoint vẫn còn trong transaction.

### 8.2. COMMIT xóa các savepoint

Sau COMMIT, transaction kết thúc và các savepoint cũ không còn hiệu lực. Một ROLLBACK toàn transaction sau đó không thể quay lại trước commit.

### 8.3. SAVEPOINT không thay thế transaction boundary

Savepoint hữu ích khi một đơn vị công việc có một nhánh tùy chọn có thể bỏ qua, nhưng vẫn cần giữ phần trước đó. Ví dụ ứng dụng có thể thử ghi một phần ghi chú phụ, rollback về savepoint nếu phần phụ lỗi, rồi tiếp tục phần nghiệp vụ chính nếu chính sách cho phép.

Không dùng savepoint để che lỗi làm hỏng bất biến chính. Nếu một bước bắt buộc của nghiệp vụ thất bại, cần rollback toàn transaction.

### 8.4. DDL có implicit commit trong Oracle

Oracle phát sinh implicit commit trước DDL và sau khi DDL thành công. Ví dụ CREATE TABLE, ALTER TABLE, DROP TABLE, TRUNCATE TABLE và nhiều lệnh quản trị khác không thuộc cùng transaction DML theo cách người mới có thể kỳ vọng.

~~~sql
UPDATE account_lab
SET balance = balance - 100
WHERE account_id = 10;

CREATE TABLE temporary_lab (id NUMBER);

ROLLBACK;
~~~

UPDATE có thể đã được commit ngầm trước khi CREATE TABLE thực thi; ROLLBACK sau đó không hoàn tác UPDATE đó. Vì vậy:

- Không chạy DDL xen giữa các bước của một đơn vị công việc DML cần atomicity.
- Không dùng TRUNCATE như một thao tác có thể rollback giống DELETE.
- Tách migration/schema change khỏi transaction nghiệp vụ.
- Kiểm tra công cụ triển khai có tự chạy DDL hoặc commit hay không.

## 9. Khóa hàng trong Oracle

### 9.1. DML khóa những hàng bị thay đổi

UPDATE/DELETE khóa các hàng mà chúng tác động. Khóa được giữ cho đến khi transaction COMMIT hoặc ROLLBACK. Hai transaction có thể cập nhật các hàng khác nhau đồng thời; nếu cùng cần cập nhật một hàng, transaction thứ hai phải chờ hoặc nhận lỗi theo tình huống.

Ví dụ:

~~~sql
-- Session A
UPDATE account_lab
SET balance = balance - 10
WHERE account_id = 10;
-- Chua commit.

-- Session B
UPDATE account_lab
SET balance = balance + 20
WHERE account_id = 10;
-- B se cho den khi A commit/rollback.
~~~

Sau khi A commit, B tiếp tục dựa trên trạng thái phù hợp; nếu A rollback, B tiếp tục sau khi khóa được giải phóng. Ứng dụng nên đặt timeout và xử lý chờ theo chính sách.

### 9.2. SELECT thông thường không khóa hàng để đọc

Oracle dùng multiversion read consistency. Một SELECT thông thường không lấy row lock như UPDATE. Vì vậy reader và writer thường không chặn nhau theo cách khóa đọc/ghi truyền thống: SELECT có thể đọc phiên bản đã commit trong khi writer đang sửa hàng.

Điều này không có nghĩa mọi loại khóa đều không xung đột. DDL, metadata locks, explicit locks, SELECT FOR UPDATE và các tình huống đặc biệt có thể gây chờ.

### 9.3. SELECT FOR UPDATE

Khi ứng dụng cần đọc một hàng rồi cập nhật dựa trên chính hàng đó, có thể khóa hàng trước:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Khóa được giữ đến COMMIT/ROLLBACK. Transaction khác muốn sửa hàng đó phải chờ. Mẫu này hữu ích khi cần đọc trạng thái rồi đưa ra quyết định nhiều bước, nhưng transaction phải ngắn và phải luôn kết thúc.

### 9.4. WAIT, NOWAIT và SKIP LOCKED

~~~sql
-- Cho phep cho khoa.
SELECT account_id, balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE WAIT 5;

-- Khong cho: neu hang dang bi khoa thi bao loi.
SELECT account_id, balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;

-- Bo qua hang dang bi khoa, thuong dung cho worker queue.
SELECT job_id, status
FROM job_queue_lab
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED hữu ích khi nhiều worker cùng lấy công việc từ queue: worker bỏ qua hàng đang được worker khác khóa để lấy hàng khác. Nó không đảm bảo thứ tự công bằng và cần quy trình cập nhật trạng thái/commit rõ ràng để không bỏ sót công việc vĩnh viễn.

### 9.5. Deadlock

Deadlock xảy ra khi các transaction chờ khóa lẫn nhau theo chu trình:

~~~text
Session A khoa row 1, doi row 2
Session B khoa row 2, doi row 1
             |
             v
          DEADLOCK
             |
             v
Oracle phat hien chu trinh va huy mot statement
~~~

Oracle phát hiện deadlock và báo ORA-00060 cho một statement. Transaction bị ảnh hưởng không nên tiếp tục commit như thể toàn bộ đơn vị công việc đã thành công; ứng dụng phải xử lý lỗi và thường rollback toàn transaction.

Giảm deadlock bằng cách:

- Cập nhật nhiều hàng theo cùng thứ tự khóa trong mọi luồng.
- Giữ transaction ngắn.
- Tránh gọi mạng hoặc chờ người dùng khi đang giữ khóa.
- Dùng index phù hợp cho predicate UPDATE/DELETE để tránh quét và khóa phạm vi không cần thiết.
- Xử lý lỗi deadlock có kiểm soát, retry toàn đơn vị công việc nếu nghiệp vụ idempotent và cho phép.

## 10. Isolation và các anomaly thường gặp

### 10.1. Dirty read

Dirty read là đọc dữ liệu chưa commit của transaction khác. Oracle không cho phép dirty read trong READ COMMITTED/SERIALIZABLE; reader nhìn phiên bản đã commit.

### 10.2. Non-repeatable read dưới READ COMMITTED

Một transaction chạy hai SELECT cùng điều kiện. Transaction khác commit thay đổi giữa hai câu. SELECT thứ hai có thể thấy giá trị mới vì mỗi statement có snapshot riêng.

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  UPDATE balance = 120
                                  COMMIT
SELECT balance = 120
~~~

Đây là hành vi READ COMMITTED hợp lệ. Nếu một nghiệp vụ cần nhiều câu đọc trên cùng snapshot, cân nhắc SERIALIZABLE hoặc READ ONLY; nếu cần khóa hàng để cập nhật, cân nhắc SELECT FOR UPDATE hoặc DML có điều kiện.

### 10.3. Phantom rows

Trong READ COMMITTED, một SELECT lần sau có thể nhìn thấy hàng mới được transaction khác commit phù hợp với predicate, vì snapshot statement mới được tạo. Đây là thay đổi tập hàng giữa các statement.

SERIALIZABLE/READ ONLY cung cấp snapshot ở cấp transaction để các truy vấn đọc nhất quán hơn. Tuy nhiên, SERIALIZABLE có thể gây ORA-08177 khi có xung đột ghi; không chọn mức này chỉ vì muốn “khóa toàn bộ bảng”.

### 10.4. Lost update và cách bảo vệ

Lost update có thể xảy ra khi ứng dụng đọc một giá trị, tính toán ở client, rồi ghi lại giá trị dựa trên dữ liệu đã cũ mà không kiểm tra phiên bản.

Ví dụ nguy hiểm:

~~~sql
-- Client doc balance = 100.
-- Client tinh new_balance = 90.
UPDATE account_lab
SET balance = 90
WHERE account_id = 10;
~~~

Nếu một transaction khác đã cộng tiền lên 120 sau lúc client đọc, UPDATE ghi cứng 90 có thể ghi đè thay đổi của transaction kia.

Các cách bảo vệ:

1. Tính trực tiếp trong SQL: SET balance = balance - :amount.
2. Thêm điều kiện optimistic version: WHERE account_id=:id AND version_no=:old_version, rồi tăng version_no.
3. Dùng SELECT FOR UPDATE trước khi đọc và cập nhật nếu cần giữ khóa qua quy trình.
4. Dùng SERIALIZABLE khi mô hình nghiệp vụ và khả năng retry phù hợp.

Ví dụ optimistic locking:

~~~sql
UPDATE account_lab
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
~~~

Nếu SQL%ROWCOUNT = 0, dữ liệu đã thay đổi hoặc bản ghi không còn tồn tại. Ứng dụng cần đọc lại và quyết định xử lý; không ghi đè mù.

## 11. Ví dụ chuyển tiền bằng PL/SQL

### 11.1. Tạo bảng và dữ liệu lab

~~~sql
CREATE TABLE transfer_account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(60 CHAR) NOT NULL,
    balance NUMBER(18,2) NOT NULL,
    CONSTRAINT ck_transfer_balance_lab CHECK (balance >= 0)
);

CREATE TABLE transfer_history_lab (
    transfer_id NUMBER PRIMARY KEY,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_transfer_amount_lab CHECK (amount > 0),
    CONSTRAINT fk_transfer_from_lab FOREIGN KEY (from_account_id)
        REFERENCES transfer_account_lab(account_id),
    CONSTRAINT fk_transfer_to_lab FOREIGN KEY (to_account_id)
        REFERENCES transfer_account_lab(account_id)
);

INSERT INTO transfer_account_lab VALUES (10, 'Account A', 1000);
INSERT INTO transfer_account_lab VALUES (20, 'Account B', 300);
COMMIT;
~~~

### 11.2. Khối PL/SQL chuyển tiền

Ví dụ dưới đây thực hiện hai UPDATE và một INSERT trong cùng transaction. Khối PL/SQL không tự COMMIT; caller quyết định kết thúc đơn vị công việc:

~~~sql
DECLARE
    v_amount NUMBER := 200;
    v_from_account NUMBER := 10;
    v_to_account NUMBER := 20;
BEGIN
    IF v_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Amount must be positive');
    END IF;

    IF v_from_account = v_to_account THEN
        RAISE_APPLICATION_ERROR(-20002, 'Source and destination must differ');
    END IF;

    UPDATE transfer_account_lab
    SET balance = balance - v_amount
    WHERE account_id = v_from_account
      AND balance >= v_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20003, 'Source account missing or insufficient funds');
    END IF;

    UPDATE transfer_account_lab
    SET balance = balance + v_amount
    WHERE account_id = v_to_account;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20004, 'Destination account not found');
    END IF;

    INSERT INTO transfer_history_lab (
        transfer_id, from_account_id, to_account_id, amount
    )
    VALUES (
        9001, v_from_account, v_to_account, v_amount
    );
END;
/
~~~

Sau khi khối chạy thành công, các thay đổi vẫn chưa commit. Caller có thể kiểm tra kết quả rồi COMMIT; nếu có lỗi, caller phải ROLLBACK toàn transaction.

~~~sql
COMMIT;

SELECT account_id, balance
FROM transfer_account_lab
ORDER BY account_id;
~~~

Kết quả sau commit: tài khoản 10 có 800, tài khoản 20 có 500 và lịch sử có một dòng chuyển 200.

### 11.3. Điều gì xảy ra khi có lỗi?

Nếu tài khoản đích không tồn tại hoặc INSERT lịch sử vi phạm constraint, khối PL/SQL phát sinh exception. Câu lệnh lỗi được rollback ở phạm vi statement, nhưng những câu DML trước đó trong transaction có thể vẫn còn pending. Caller cần rollback:

~~~sql
ROLLBACK;
~~~

Không bắt exception rồi bỏ qua và để caller commit nếu transaction chưa đạt trạng thái nghiệp vụ hợp lệ.

### 11.4. Tại sao không COMMIT bên trong mọi procedure?

Một procedure con thường không nên tự COMMIT nếu nó chỉ là một phần của đơn vị công việc lớn hơn. Ví dụ caller có thể cần:

1. Tạo order.
2. Ghi order lines.
3. Trừ kho.
4. Ghi payment ledger.

Nếu procedure trừ kho tự COMMIT, caller không thể rollback toàn bộ khi ghi payment ledger lỗi. Thông thường, tầng application service hoặc procedure điều phối nghiệp vụ là nơi sở hữu transaction boundary và quyết định COMMIT/ROLLBACK.

## 12. Quản lý transaction bằng JDBC

### 12.1. Autocommit mặc định có thể phá vỡ đơn vị công việc

JDBC Connection thường bắt đầu với auto-commit bật theo mặc định. Khi auto-commit true, mỗi câu lệnh SQL được commit riêng khi hoàn tất. Nếu chuyển tiền bằng ba câu DML mà không tắt auto-commit, các bước có thể được commit độc lập:

~~~java
// Khong phu hop cho mot business unit co nhieu DML:
connection.setAutoCommit(true);
updateSourceAccount();
updateDestinationAccount();
insertTransferHistory();
~~~

Nếu câu thứ ba lỗi, hai câu trước có thể đã commit. Đây là vi phạm atomicity của nghiệp vụ chuyển tiền.

### 12.2. Tắt autocommit và commit/rollback tường minh

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debitSource(connection, fromAccountId, amount);
        creditDestination(connection, toAccountId, amount);
        insertTransferHistory(
            connection, transferId, fromAccountId, toAccountId, amount
        );

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Ý nghĩa:

- Lấy một connection cho đơn vị công việc.
- Tắt auto-commit để các câu DML tham gia cùng transaction.
- Chạy tất cả bước nghiệp vụ.
- Commit khi toàn bộ bước bắt buộc thành công.
- Rollback khi có lỗi.
- Đóng/hoàn trả connection sau khi transaction đã kết thúc.

Trong ứng dụng dùng connection pool, cần tuân thủ cách pool quản lý/reset connection state. Không để connection đang có transaction chưa kết thúc quay lại pool.

### 12.3. PreparedStatement và kiểm tra số dòng

~~~java
String sql = """
    UPDATE transfer_account_lab
    SET balance = balance - ?
    WHERE account_id = ?
      AND balance >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setLong(2, fromAccountId);
    ps.setBigDecimal(3, amount);

    int updated = ps.executeUpdate();
    if (updated != 1) {
        throw new SQLException("Source account missing or insufficient funds");
    }
}
~~~

Không chỉ gửi UPDATE rồi giả định nó thành công. Hãy kiểm tra update count để biết điều kiện WHERE có khớp đúng một hàng hay không.

### 12.4. Không đổi autocommit trước khi kết thúc transaction

Trong JDBC, đổi autoCommit từ false sang true khi transaction đang mở có thể commit transaction hiện tại theo JDBC contract. Vì vậy không nên bật lại autoCommit trước khi đã chủ động commit hoặc rollback. Với connection pool, hãy để pool quản lý việc reset state theo cấu hình và bảo đảm connection đã sạch transaction trước khi trả về.

### 12.5. Một transaction nên có một chủ sở hữu

Một tầng nên chịu trách nhiệm:

- Bắt đầu hoặc cấu hình transaction.
- Gọi các repository/DAO cần thiết trên cùng connection.
- Commit khi nghiệp vụ hoàn tất.
- Rollback khi lỗi.

Các DAO con không nên tự mở connection khác hoặc tự commit nếu chúng cần tham gia cùng đơn vị công việc. Nếu mỗi DAO lấy connection riêng, các câu lệnh có thể nằm trong những transaction khác nhau và mất atomicity.

## 13. Transaction, lỗi mạng và retry

### 13.1. Không phải mọi lỗi đều an toàn để retry một câu SQL

Các lỗi có thể xảy ra:

- ORA-00060: deadlock detected.
- ORA-08177: không thể serialize access trong transaction SERIALIZABLE.
- ORA-00054: resource busy and acquire with NOWAIT specified hoặc timeout tình huống tương ứng.
- Lỗi constraint như ORA-00001, ORA-02290.
- Lỗi kết nối xảy ra trước, trong hoặc sau COMMIT.

Mỗi loại lỗi có cách xử lý khác nhau. Lỗi dữ liệu/constraint thường không thể giải quyết bằng retry ngay với cùng input. Lỗi xung đột có thể retry nếu nghiệp vụ cho phép và dữ liệu được đọc lại từ đầu.

### 13.2. Retry toàn bộ transaction

Khi lỗi cho thấy transaction phải được thử lại, quy trình thường là:

1. Rollback transaction hiện tại.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu cần thiết.
4. Tính lại quyết định nghiệp vụ.
5. Thực hiện lại toàn bộ các bước.
6. Commit nếu thành công.

Không chỉ chạy lại câu UPDATE cuối vì các bước trước có thể dựa trên snapshot hoặc số dư đã cũ.

Retry cần có giới hạn số lần, backoff có jitter và phân loại lỗi. Retry vô hạn có thể làm hệ thống quá tải trong lúc database đang có contention.

### 13.3. Idempotency key

Một yêu cầu có thể được gửi lại do timeout hoặc client mất kết nối. Để tránh tạo hai lần cùng một giao dịch, lưu một request_id duy nhất:

~~~sql
CREATE TABLE transfer_request_lab (
    request_id VARCHAR2(64 CHAR) PRIMARY KEY,
    transfer_id NUMBER NOT NULL UNIQUE,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL
);
~~~

Khi xử lý request:

- Tạo/đăng ký request_id trong cùng transaction với các thay đổi tiền.
- Nếu request_id đã tồn tại, trả kết quả của lần xử lý trước theo quy tắc nghiệp vụ.
- Nếu hai request cùng đến đồng thời, unique constraint là lớp bảo vệ cuối cùng chống tạo bản ghi trùng.

Idempotency không có nghĩa mọi thao tác đều chạy hai lần nhưng kết quả giống nhau; nó là thiết kế để cùng một request định danh chỉ tạo một tác động nghiệp vụ.

## 14. Transaction database và tác động bên ngoài

Oracle transaction chỉ điều khiển thay đổi trong phạm vi transaction resource/database tương ứng. Nó không tự rollback một email đã gửi, một cuộc gọi REST đã thành công hoặc một lệnh thanh toán ở nhà cung cấp bên ngoài.

Ví dụ:

1. Database tạo order và commit.
2. Ứng dụng gọi dịch vụ gửi email.
3. Dịch vụ email lỗi.

Database không thể rollback việc gửi email (nếu email đã được gửi) chỉ bằng ROLLBACK. Tương tự, nếu gọi cổng thanh toán trước rồi transaction database rollback, khoản thanh toán bên ngoài có thể đã thành công.

### 14.1. Transactional outbox

Một mẫu phổ biến là ghi sự kiện cần gửi vào outbox trong cùng transaction với dữ liệu nghiệp vụ:

~~~sql
INSERT INTO orders (...);

INSERT INTO order_outbox (
    event_id, aggregate_id, event_type, payload, status, created_at
)
VALUES (
    :event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING', SYSTIMESTAMP
);

COMMIT;
~~~

Một worker đọc outbox, gửi sự kiện đến hệ thống bên ngoài, rồi đánh dấu đã xử lý. Nếu worker lỗi sau khi gửi nhưng trước khi đánh dấu, nó có thể gửi lại; consumer vẫn cần idempotency hoặc event_id để chống xử lý trùng.

Outbox bảo đảm thay đổi order và yêu cầu phát sự kiện được commit cùng nhau trong database. Nó không biến việc gửi thông điệp và commit database thành một thao tác phân tán nguyên tử; nó cung cấp một quy trình tin cậy để eventual delivery.

### 14.2. Saga và bù trừ

Với quy trình nhiều dịch vụ, mỗi bước có thể là transaction cục bộ riêng. Nếu bước sau thất bại, hệ thống chạy hành động bù trừ cho các bước trước theo nghiệp vụ:

- Đặt chỗ tồn kho → hủy đặt chỗ.
- Tạo authorization thanh toán → void authorization.
- Tạo đơn → chuyển trạng thái hủy.

Bù trừ không phải rollback vật lý của transaction cũ. Nó là một giao dịch mới, có thể thất bại và cần retry/đối soát.

## 15. Autonomous transaction trong PL/SQL

Oracle hỗ trợ autonomous transaction bằng pragma AUTONOMOUS_TRANSACTION. Nó cho phép một routine thực hiện và commit/rollback một transaction độc lập với transaction gọi nó.

Ví dụ khái niệm ghi log độc lập:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log_lab (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO error_log_lab(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Log được commit trong autonomous transaction có thể tồn tại ngay cả khi transaction nghiệp vụ bên ngoài rollback. Điều này hữu ích cho một số loại log chẩn đoán, nhưng phải hiểu rõ:

- Autonomous transaction không chia sẻ transaction context/commit của caller.
- Nó có thể gây deadlock nếu cố truy cập tài nguyên đang bị transaction cha giữ khóa.
- Không dùng nó để commit một phần thay đổi nghiệp vụ mà caller kỳ vọng rollback cùng nhau.
- Cần kiểm soát lỗi trong routine log để việc ghi log không che mất lỗi gốc.

Autonomous transaction là công cụ chuyên biệt, không phải cách thay thế transaction boundary thông thường.

## 16. Thực hành hai session: quan sát commit, rollback và khóa

Thực hiện trên schema lab riêng, mở hai SQL session độc lập. Tạo bảng:

~~~sql
CREATE TABLE tx_acid_lab (
    id NUMBER PRIMARY KEY,
    value NUMBER NOT NULL
);

INSERT INTO tx_acid_lab VALUES (1, 100);
COMMIT;
~~~

### Bước 1 — Quan sát thay đổi chưa commit

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 200
WHERE id = 1;
~~~

Session B:

~~~sql
SELECT value
FROM tx_acid_lab
WHERE id = 1;
~~~

Session B vẫn thấy giá trị đã commit là 100, không thấy 200 chưa commit.

### Bước 2 — Commit và đọc lại

Session A:

~~~sql
COMMIT;
~~~

Session B chạy lại SELECT. Statement mới có thể thấy 200.

### Bước 3 — Rollback

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 300
WHERE id = 1;

ROLLBACK;
~~~

Session B đọc lại và thấy 200. Thay đổi 300 chưa commit đã bị hoàn tác.

### Bước 4 — Quan sát writer chờ writer

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 250
WHERE id = 1;
-- Chua commit.
~~~

Session B:

~~~sql
UPDATE tx_acid_lab
SET value = value + 10
WHERE id = 1;
~~~

Session B sẽ chờ khóa hàng do A giữ. Session A COMMIT hoặc ROLLBACK sẽ giải phóng khóa và cho B tiếp tục.

### Bước 5 — Quan sát SAVEPOINT

Trong một session:

~~~sql
UPDATE tx_acid_lab SET value = 210 WHERE id = 1;
SAVEPOINT before_second_change;
UPDATE tx_acid_lab SET value = 220 WHERE id = 1;
ROLLBACK TO before_second_change;
SELECT value FROM tx_acid_lab WHERE id = 1;
ROLLBACK;
~~~

Sau rollback về savepoint, giá trị trong transaction là 210; rollback toàn transaction sau đó đưa dữ liệu về trạng thái đã commit trước đó.

### Bước 6 — Dọn bảng lab (tùy chọn)

~~~sql
-- Chi chay neu chac chan day la bang lab cua ban.
DROP TABLE tx_acid_lab PURGE;
~~~

DROP TABLE là DDL và gây implicit commit theo quy tắc Oracle. Chỉ chạy sau khi đã kết thúc các transaction thực hành và chắc chắn không cần bảng nữa.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Mỗi câu SQL luôn là một transaction riêng | Với auto-commit tắt, nhiều câu DML có thể cùng một transaction |
| Một câu DML lỗi sẽ rollback mọi câu trước đó | Oracle rollback statement lỗi; các câu trước có thể còn pending |
| COMMIT ghi ngay mọi data block xuống datafile | Commit bảo vệ redo theo commit protocol; DBWR có thể ghi data block sau |
| SELECT thường luôn chặn UPDATE | Oracle dùng read consistency; reader thường không chặn writer theo row lock |
| READ COMMITTED cho snapshot xuyên suốt transaction | Mỗi statement có snapshot riêng |
| SERIALIZABLE khóa toàn bộ database | Nó cung cấp transaction-level snapshot và có thể phát ORA-08177 khi xung đột |
| ROLLBACK có thể đảo ngược COMMIT đã thành công | Cần một transaction bù trừ mới |
| SAVEPOINT tương đương COMMIT từng phần | Savepoint không kết thúc transaction |
| DDL có thể rollback cùng DML | Oracle DDL phát sinh implicit commit |
| Procedure con nên tự commit để chắc chắn dữ liệu được lưu | Commit bên trong procedure có thể phá atomicity của caller |
| Retry một UPDATE lỗi là đủ | Thường cần rollback và chạy lại toàn bộ transaction sau khi đọc lại trạng thái |
| Database rollback được email/API đã gửi | Tác động ngoài DB cần outbox/saga/idempotency |

## 18. Hướng dẫn thiết kế transaction cho ứng dụng

Khi triển khai một nghiệp vụ mới, có thể đi theo các bước:

1. **Xác định kết quả hoàn chỉnh:** những bản ghi và bất biến nào phải cùng tồn tại?
2. **Chọn transaction owner:** service hoặc procedure nào có quyền commit/rollback?
3. **Đặt DML liên quan trên cùng connection/session:** không mở connection khác cho từng repository nếu chúng phải cùng transaction.
4. **Đưa bất biến vào database:** primary key, foreign key, unique, check và conditional DML.
5. **Chọn isolation phù hợp:** READ COMMITTED thường đủ; SERIALIZABLE/READ ONLY chỉ khi yêu cầu snapshot phù hợp.
6. **Giảm thời gian giữ khóa:** không gọi mạng hoặc chờ tương tác trong transaction.
7. **Xử lý lỗi:** rollback khi đơn vị công việc thất bại; phân loại lỗi có thể retry.
8. **Chống request trùng:** dùng idempotency key cho thao tác có thể được gửi lại.
9. **Xử lý tác động ngoài DB:** outbox hoặc saga khi cần phối hợp nhiều hệ thống.
10. **Quan sát và kiểm thử:** đo lock waits, deadlocks, undo, redo, transaction duration và actual execution plans.

### 18.1. Mẫu phân lớp đơn giản

~~~text
HTTP / MESSAGE HANDLER
        |
        v
APPLICATION SERVICE
  begin/configure transaction
        |
        +---- CUSTOMER DAO
        |
        +---- ORDER DAO
        |
        +---- INVENTORY DAO
        |
        +---- OUTBOX DAO
        |
        v
  commit if all required steps succeed
  rollback if the unit of work fails
~~~

Các DAO nhận cùng connection hoặc transaction context. Application service điều phối nghiệp vụ và là nơi quyết định commit. Cách triển khai cụ thể có thể dùng transaction manager/framework, nhưng nguyên tắc ownership vẫn cần rõ.

## 19. Câu hỏi tự kiểm tra

1. Một business unit of work là gì? Vì sao nó có thể chứa nhiều câu DML?
2. Atomicity khác Consistency ở điểm nào?
3. Nếu câu INSERT cuối transaction lỗi, UPDATE thành công trước đó có tự rollback không?
4. Vì sao transaction owner cần rollback khi một bước bắt buộc thất bại?
5. Constraint nào có thể giúp bảo vệ số dư không âm?
6. Vì sao UPDATE có điều kiện balance >= amount an toàn hơn đọc số dư rồi ghi giá trị tính ở client?
7. READ COMMITTED của Oracle tạo snapshot ở cấp nào?
8. Hai SELECT trong cùng READ COMMITTED transaction có thể thấy hai giá trị đã commit khác nhau không?
9. SERIALIZABLE khác READ COMMITTED như thế nào?
10. ORA-08177 có thể xảy ra trong trường hợp nào?
11. READ ONLY transaction có cho phép DML không?
12. Vì sao Oracle không cần ghi mọi data block xuống datafile ngay khi COMMIT?
13. Undo và redo khác nhau thế nào?
14. ORA-01555 liên quan đến cơ chế nào?
15. SAVEPOINT có kết thúc transaction không?
16. Vì sao không nên chạy DDL giữa một transaction nghiệp vụ cần atomicity?
17. SELECT thông thường có lấy row lock như UPDATE không?
18. SELECT FOR UPDATE dùng để giải quyết tình huống nào?
19. Deadlock ORA-00060 nên được xử lý ở phạm vi nào?
20. Vì sao autocommit true nguy hiểm khi một nghiệp vụ cần ba câu DML?
21. Khi retry do lỗi serialization, nên chạy lại một câu hay toàn bộ transaction?
22. Idempotency key giúp xử lý trường hợp client mất phản hồi COMMIT như thế nào?
23. Vì sao database transaction không thể rollback email đã gửi?
24. Transactional outbox bảo đảm điều gì và không bảo đảm điều gì?
25. Autonomous transaction có thể gây rủi ro gì nếu truy cập hàng đang bị transaction cha khóa?

**Gợi ý trả lời:**

1. Là nhóm thao tác cần được xem như một kết quả nghiệp vụ hoàn chỉnh.
2. Atomicity là tất cả hoặc không có gì; Consistency là trạng thái cuối thỏa các bất biến.
3. Không. Câu lỗi được rollback ở phạm vi statement; DML trước đó có thể còn pending.
4. Để tránh commit một trạng thái nghiệp vụ dở dang.
5. CHECK (balance >= 0), kết hợp UPDATE có điều kiện và transaction logic.
6. Điều kiện được kiểm tra trong DML khi cập nhật, giảm nguy cơ ghi dựa trên giá trị cũ.
7. Mỗi statement.
8. Có, nếu transaction khác commit giữa hai statement.
9. SERIALIZABLE dùng snapshot ở cấp transaction; READ COMMITTED dùng snapshot từng statement.
10. Khi transaction SERIALIZABLE cố sửa hàng đã bị transaction khác thay đổi sau snapshot của nó.
11. Không.
12. Redo được bảo vệ theo commit protocol; DBWR có thể ghi data block sau.
13. Undo hỗ trợ rollback/consistent read; redo hỗ trợ roll forward/recovery.
14. Undo cần thiết cho snapshot đọc đã bị tái sử dụng trước khi truy vấn kết thúc.
15. Không, rollback to savepoint chỉ hoàn tác phần sau mốc.
16. DDL phát sinh implicit commit, có thể commit DML trước đó.
17. Không, SELECT thường dùng read consistency; SELECT FOR UPDATE mới lấy row locks.
18. Khi cần đọc rồi cập nhật cùng hàng trong khi giữ khóa.
19. Xử lý lỗi và thường rollback toàn transaction rồi retry có kiểm soát nếu phù hợp.
20. Mỗi câu có thể commit riêng, phá atomicity giữa các bước.
21. Toàn bộ transaction sau rollback và đọc lại dữ liệu.
22. Request ID duy nhất giúp nhận ra lần xử lý trước và tránh tác động nghiệp vụ trùng.
23. Email thuộc hệ thống bên ngoài, không nằm trong transaction resource của Oracle.
24. Outbox ghi yêu cầu phát sự kiện cùng dữ liệu nghiệp vụ; gửi ra ngoài là eventual và consumer vẫn cần idempotency.
25. Có thể deadlock do autonomous transaction chờ tài nguyên mà transaction cha đang giữ.

## Tài liệu Oracle tham khảo

- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction, commit, rollback và tính chất transaction.
- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, khóa và xử lý đồng thời.
- [Oracle Database SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): isolation level, READ ONLY và transaction characteristics.
- [Oracle Database SQL Language Reference — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): xác nhận transaction và commit behavior.
- [Oracle Database SQL Language Reference — ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html): hoàn tác transaction và savepoint.
- [Oracle Database SQL Language Reference — SAVEPOINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SAVEPOINT.html): tạo mốc rollback trong transaction.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo-data.html): undo, read consistency và recovery.
- [Oracle Database Concepts — Redo Log](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/redo-log.html): redo log và phục hồi thay đổi.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): quản lý connection, transaction và JDBC.
