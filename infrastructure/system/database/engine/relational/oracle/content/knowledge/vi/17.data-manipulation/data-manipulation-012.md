# Ảnh hưởng của DML đến undo, redo, chỉ mục và khóa

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Thay đổi dữ liệu  
> **Mục tiêu:** Hiểu tác động bên trong của INSERT, UPDATE, DELETE và MERGE trong Oracle Database; phân biệt undo với redo; giải thích cách undo hỗ trợ rollback và read consistency; hiểu chi phí duy trì B-tree index, tác động của constraint/trigger; nhận diện row lock, table lock, TX/TM enqueue và deadlock; lựa chọn kích thước transaction, chiến lược commit và cách theo dõi tài nguyên DML.

## 1. Một câu DML làm thay đổi nhiều cấu trúc

Khi chạy câu lệnh:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Oracle không chỉ ghi một giá trị salary mới vào bảng. Database còn phải quản lý các công việc liên quan:

- Ghi thông tin **undo** để có thể hoàn tác thay đổi và tái dựng phiên bản dữ liệu cũ cho consistent read.
- Tạo **redo** mô tả các thay đổi cần được bảo vệ để instance recovery và media recovery có thể khôi phục dữ liệu.
- Duy trì các **index** liên quan đến hàng được sửa.
- Lấy và giữ **lock** để bảo vệ thay đổi khỏi xung đột với transaction khác.
- Kiểm tra constraint, thực thi trigger và xử lý các tác động phụ do schema quy định.
- Quản lý transaction cho đến khi COMMIT hoặc ROLLBACK.

Vì vậy, chi phí DML phụ thuộc nhiều hơn số cột được thay đổi. Một UPDATE tác động hàng triệu dòng, nhiều index, trigger và khóa ngoại có thể tạo ra lượng undo/redo lớn và giữ lock lâu.

| Thành phần | Vai trò chính |
|---|---|
| Undo | Lưu thông tin cần để đảo ngược thay đổi và dựng lại phiên bản dữ liệu cũ |
| Redo | Ghi change vector để phục hồi thay đổi sau sự cố |
| Index | Cấu trúc truy cập phụ, phải được duy trì nhất quán với bảng |
| Lock | Kiểm soát truy cập đồng thời vào dữ liệu đang được thay đổi |

## 2. Vòng đời khái quát của một DML

Khi thực hiện DML, Oracle phân tích câu SQL, xác định hàng cần tác động, kiểm tra quyền/constraint phù hợp, lấy các khóa cần thiết và thay đổi block trong buffer cache. Các thay đổi tạo ra undo record và redo record.

~~~text
SQL INSERT / UPDATE / DELETE / MERGE
                 |
                 v
       Parse và execution plan
                 |
                 v
       Tìm các hàng mục tiêu
                 |
                 v
       Lấy lock cần thiết
                 |
                 v
     Thay đổi block trong buffer cache
          /             |             \
         v              v              v
      UNDO            REDO          INDEX
  phiên bản cũ     change vector   duy trì entry
         \              |              /
          \             |             /
           v            v            v
            Transaction còn mở
                   |
             COMMIT / ROLLBACK
                   |
       COMMIT: xác nhận transaction
       ROLLBACK: dùng undo đảo thay đổi
~~~

Đây là mô hình khái niệm, không phải thứ tự vi mô cố định cho mọi operation. Oracle có thể thực hiện nhiều bước nội bộ, buffer và index operation khác nhau tùy loại DML, access path, partitioning, logging mode và phiên bản.

Một điểm quan trọng: **COMMIT không có nghĩa DBWR đã ghi tất cả block dữ liệu xuống datafile.** Commit chủ yếu cần redo bảo vệ transaction được ghi bền vững theo cơ chế LGWR và cấu hình commit. DBWR có thể ghi dirty data block xuống datafile sau đó.

## 3. Undo: lưu thông tin để quay lại phiên bản trước

Undo record chứa thông tin cần thiết để đảo ngược một thay đổi. Undo được lưu trong undo tablespace, qua các undo segment và extent do Oracle quản lý.

Ví dụ:

~~~sql
UPDATE employees
SET salary = 9000
WHERE employee_id = 100;
~~~

Giả sử salary cũ là 8000. Để rollback, Oracle cần đủ thông tin để khôi phục giá trị 8000. Undo của UPDATE chứa thông tin cần thiết để dựng lại trạng thái trước thay đổi.

Undo phục vụ ba mục đích chính:

1. **ROLLBACK:** đảo ngược thay đổi của transaction chưa commit hoặc của một phần transaction về savepoint.
2. **Read consistency:** cho phép truy vấn đọc phiên bản dữ liệu nhất quán tại SCN phù hợp, ngay cả khi transaction khác đang sửa block.
3. **Flashback:** hỗ trợ một số khả năng truy vấn/khôi phục dữ liệu quá khứ trong giới hạn undo còn được giữ và tính năng được cấu hình.

### 3.1. Undo không phải bản sao lưu toàn bộ bảng

Undo ghi lại thông tin cần thiết để đảo ngược thay đổi, không phải một bản sao đầy đủ của bảng trước mỗi DML. Lượng undo phụ thuộc:

- Số hàng thực sự bị thay đổi.
- Loại DML.
- Số cột và kiểu dữ liệu bị sửa.
- Các index cần duy trì.
- Cấu trúc hàng, partition, LOB và những chi tiết lưu trữ khác.
- Trigger hoặc thao tác phụ phát sinh thêm DML.

Không thể suy ra chính xác dung lượng undo chỉ bằng số hàng nhân số byte của cột. Cần đo trên workload thực tế.

### 3.2. Undo cho INSERT, UPDATE và DELETE

| DML | Thay đổi dữ liệu | Vai trò của undo |
|---|---|---|
| INSERT | Tạo hàng mới | Giữ thông tin cần thiết để loại bỏ hàng đã insert khi rollback |
| UPDATE | Thay giá trị một hoặc nhiều cột | Giữ giá trị/trạng thái cũ cần để khôi phục hàng |
| DELETE | Xóa hàng | Giữ thông tin cần để tái tạo hàng đã xóa khi rollback hoặc consistent read |
| MERGE | Kết hợp insert/update theo từng hàng nguồn | Undo được tạo tương ứng với nhánh insert hoặc update thực tế |

DELETE có thể tạo lượng undo đáng kể vì Oracle phải giữ đủ thông tin để khôi phục hàng đã xóa. UPDATE nhiều cột hoặc nhiều hàng cũng có thể tạo undo lớn. INSERT thường cần undo để rollback việc thêm hàng và duy trì cấu trúc liên quan.

### 3.3. Rollback dùng undo

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

ROLLBACK;
~~~

Sau ROLLBACK, thay đổi của transaction được đảo ngược. Nếu transaction đã thực hiện nhiều câu DML, Oracle hoàn tác các thay đổi chưa commit của transaction đó.

Có thể rollback về savepoint:

~~~sql
SAVEPOINT before_adjustment;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Phát hiện sai phạm vi cập nhật
ROLLBACK TO before_adjustment;
~~~

Rollback về savepoint chỉ đảo phần thay đổi sau savepoint, transaction vẫn tiếp tục mở và các lock phù hợp vẫn có thể được giữ cho đến khi transaction kết thúc.

### 3.4. Undo và read consistency

Oracle sử dụng multiversion read consistency. Một câu SELECT thông thường đọc dữ liệu theo một SCN nhất quán của statement trong READ COMMITTED. Nếu block đã bị transaction khác thay đổi sau SCN đó, Oracle có thể dùng undo để dựng lại phiên bản cũ mà truy vấn cần.

Ví dụ:

1. Session A bắt đầu SELECT và có statement SCN.
2. Session B UPDATE một hàng nhưng chưa COMMIT.
3. Session A đọc hàng đó.
4. Session A không thấy thay đổi chưa commit của B; Oracle dùng phiên bản nhất quán phù hợp.
5. Sau khi B COMMIT, một SELECT mới của A trong READ COMMITTED có thể thấy giá trị mới.

Điều này giải thích vì sao SELECT thông thường thường không phải chờ row lock do UPDATE đang giữ. Reader dùng phiên bản nhất quán; writer có thể tiếp tục thay đổi dữ liệu.

### 3.5. Statement-level và transaction-level consistency

Trong isolation level mặc định READ COMMITTED, mỗi câu SQL có snapshot tại thời điểm statement bắt đầu. Hai SELECT trong cùng transaction có thể thấy hai trạng thái khác nhau nếu transaction khác commit ở giữa.

Trong SERIALIZABLE hoặc READ ONLY transaction, Oracle cung cấp góc nhìn nhất quán ở cấp transaction theo semantics tương ứng. Khi có xung đột ghi, SERIALIZABLE có thể phát sinh lỗi serialization như ORA-08177; ứng dụng phải có chiến lược retry transaction phù hợp.

Không nhầm read consistency với việc khóa toàn bộ bảng. Oracle thường dùng undo và SCN để cung cấp snapshot thay vì chặn mọi writer.

## 4. Undo retention và ORA-01555

Undo cần được giữ đủ lâu để transaction rollback và các query dài có thể dựng lại phiên bản cũ. Oracle quản lý việc tái sử dụng undo extent theo trạng thái transaction, nhu cầu consistent read, cấu hình undo và áp lực dung lượng.

### 4.1. UNDO_RETENTION

Tham số UNDO_RETENTION đặt mục tiêu thời gian giữ undo đã commit, tính bằng giây. Đây là mục tiêu; khả năng thực tế còn phụ thuộc dung lượng undo tablespace, workload và cấu hình.

Nếu không có đủ dung lượng, undo có thể bị tái sử dụng sớm hơn mục tiêu trong một số cấu hình. RETENTION GUARANTEE có thể yêu cầu Oracle ưu tiên giữ undo theo retention, nhưng khi hết chỗ, DML mới có thể thất bại vì không có undo space tái sử dụng. Vì vậy không bật guarantee một cách tùy tiện.

### 4.2. ORA-01555: snapshot too old

Một truy vấn chạy lâu có thể cần phiên bản cũ của block, nhưng undo cần thiết đã bị ghi đè/tái sử dụng. Khi Oracle không còn đủ undo để dựng snapshot, truy vấn có thể lỗi:

~~~text
ORA-01555: snapshot too old
~~~

Các yếu tố thường liên quan:

- Query chạy lâu trong khi bảng bị DML liên tục.
- Undo tablespace không đủ so với tốc độ sinh undo và thời gian query.
- Undo retention mục tiêu quá ngắn cho workload.
- Transaction/query có cách truy cập khiến cần nhiều phiên bản cũ.
- Một số pattern PL/SQL mở cursor rồi cập nhật dữ liệu nguồn trong cùng quá trình xử lý.

Cách xử lý cần dựa vào nguyên nhân:

- Giảm thời gian chạy query bằng SQL, index và plan phù hợp.
- Giảm transaction DML quá lớn hoặc phân chia batch theo thiết kế.
- Cấp dung lượng undo hợp lý, kiểm tra autoextend và retention.
- Tránh giữ cursor đọc quá lâu trong khi cùng tập dữ liệu bị cập nhật liên tục.
- Đánh giá RETENTION GUARANTEE chỉ khi chấp nhận tác động nếu undo tablespace đầy.

Không nên coi tăng UNDO_RETENTION đơn lẻ là cách sửa chắc chắn; nếu dung lượng không đủ, tham số đó không bảo đảm giữ được undo.

### 4.3. Theo dõi undo

Một số view DBA có thể sử dụng (quyền truy cập tùy môi trường):

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

Các cột hữu ích:

- UNDOBLKS: số block undo được tạo trong khoảng thống kê.
- TXNCOUNT: số transaction trong khoảng.
- MAXQUERYLEN: thời gian query dài nhất được ghi nhận trong khoảng.
- TUNED_UNDORETENTION: retention được điều chỉnh theo workload.
- SSOLDERRCNT: số lỗi snapshot too old được ghi nhận trong khoảng.

Để xem transaction đang dùng undo:

~~~sql
SELECT s.sid,
       s.serial#,
       t.used_ublk,
       t.used_urec,
       t.start_time
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
~~~

USED_UBLK và USED_UREC giúp nhận diện transaction đang tạo/giữ nhiều undo. Không kết luận transaction “rò rỉ” chỉ từ số undo lớn; cần xem thời gian mở, workload, tiến độ và transaction owner.

## 5. Redo: ghi lại thay đổi để phục hồi

Redo log ghi các change vector mô tả thay đổi đối với database block. Redo là cơ sở quan trọng cho instance recovery, media recovery, archived log và Data Guard.

Khi một block dữ liệu thay đổi, Oracle tạo redo tương ứng. Thông tin undo cũng được bảo vệ bằng redo để khi phục hồi, Oracle có thể khôi phục nhất quán cả dữ liệu và trạng thái transaction.

### 5.1. Redo khác undo

| Đặc điểm | Undo | Redo |
|---|---|---|
| Mục đích | Hoàn tác và dựng phiên bản cũ | Phục hồi thay đổi đã ghi nhận |
| Nội dung khái quát | Thông tin cần để đảo ngược thay đổi | Change vector mô tả thay đổi |
| Phục vụ ROLLBACK | Có | Không trực tiếp dùng để rollback logic |
| Phục vụ consistent read | Có | Không phải cơ chế chính dựng snapshot query |
| Phục vụ crash/media recovery | Undo được phục hồi và áp dụng theo quy trình recovery | Là nguồn ghi lại thay đổi sau checkpoint/backup |

Undo và redo có quan hệ chặt chẽ nhưng không thay thế nhau. Redo bảo vệ cả các thay đổi trên undo block; undo cho phép Oracle đảo ngược transaction chưa commit và tái dựng phiên bản cũ.

### 5.2. Online redo log và LGWR

Redo được đưa vào redo log buffer trong SGA. LGWR ghi redo từ buffer ra online redo log files theo các điều kiện hoạt động, chẳng hạn:

- Khi transaction COMMIT.
- Khi redo buffer cần được ghi.
- Theo chu kỳ hoặc điều kiện nội bộ khác.
- Trước khi DBWR ghi dirty data block có redo tương ứng xuống datafile theo write-ahead logging.

Với commit thông thường, Oracle đảm bảo redo cần thiết của transaction được ghi bền vững đến commit record trước khi báo commit thành công, theo cấu hình COMMIT WRITE và semantics được chọn.

DBWR ghi dirty buffer xuống datafile theo checkpoint và áp lực buffer; không cần ghi tất cả data block ngay tại thời điểm commit. Vì vậy commit có thể nhanh hơn nhiều so với việc ghi toàn bộ datafile.

### 5.3. COMMIT và độ bền

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

COMMIT;
~~~

COMMIT kết thúc transaction, xác nhận các thay đổi và giải phóng lock transaction. Redo cần thiết cho commit được LGWR ghi theo chính sách commit.

Nếu client mất kết nối sau khi gửi COMMIT nhưng trước khi nhận phản hồi, ứng dụng có thể không biết commit đã thành công hay chưa. Với thao tác tài chính hoặc tích hợp bên ngoài, nên có transaction ID/idempotency key để truy vấn trạng thái thay vì mù quáng chạy lại thao tác.

Oracle có các tùy chọn COMMIT WRITE WAIT/NOWAIT và IMMEDIATE/BATCH. NOWAIT có thể trả quyền điều khiển trước khi redo được ghi bền vững, tùy cấu hình và semantics; ứng dụng không nên thay đổi chính sách durability mà không hiểu rủi ro mất giao dịch khi instance failure.

### 5.4. Redo log switch và archived log

Online redo log được chia thành các log group. Khi ghi đầy, Oracle chuyển sang group khác qua log switch. Ở ARCHIVELOG mode, các redo log group đầy được archive trước khi có thể tái sử dụng theo quy tắc vận hành.

Archived redo log cho phép media recovery áp dụng thay đổi sau backup. Nếu không có archived log cần thiết hoặc log bị mất, khả năng phục hồi tới thời điểm mong muốn có thể bị giới hạn.

Theo dõi log switch và archive là nhiệm vụ vận hành database; ứng dụng DML nên tránh tạo redo bất thường do batch quá lớn hoặc cập nhật không cần thiết.

## 6. DML tạo redo/undo như thế nào?

Các mô tả dưới đây là quy tắc khái quát; lượng thực tế phụ thuộc storage, datatype, index, constraint, logging mode và cách thực thi.

### 6.1. INSERT

~~~sql
INSERT INTO employees (
    employee_id, first_name, salary, department_id
)
VALUES (1001, 'An', 8000, 50);
~~~

Tác động:

- Tạo hàng mới trong block bảng.
- Tạo undo cần thiết để rollback việc insert.
- Tạo redo cho thay đổi block và các cấu trúc liên quan.
- Thêm entry vào mỗi index có cột/biểu thức phù hợp.
- Kiểm tra NOT NULL, CHECK, UNIQUE, FOREIGN KEY và trigger.
- Lấy lock cần thiết cho transaction và đối tượng.

INSERT vào bảng có nhiều index thường tốn công hơn bảng không có index, đặc biệt khi insert số lượng lớn. Index B-tree có thể phải tìm leaf block, chèn entry và đôi lúc split block.

### 6.2. UPDATE

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Tác động:

- Tìm các hàng phù hợp.
- Lấy row lock cho các hàng được cập nhật.
- Ghi undo để có thể khôi phục giá trị cũ.
- Ghi redo cho các thay đổi block.
- Nếu cột được index thay đổi, index entry tương ứng phải được duy trì.
- Trigger/constraint có thể tạo thêm công việc.

Nếu UPDATE chỉ đổi cột không nằm trong index, Oracle thường không cần thay đổi entry của các index không phụ thuộc cột đó. Nếu đổi cột được index, database phải duy trì entry cũ và mới theo cấu trúc index.

Một UPDATE thay đổi giá trị thành chính giá trị cũ vẫn là DML và có thể tạo công việc, lock, redo/undo tùy cách thực thi. Nếu ứng dụng biết giá trị không đổi, điều kiện WHERE có thể loại các hàng không cần cập nhật, giảm write amplification.

Ví dụ:

~~~sql
UPDATE employees
SET status = :p_status
WHERE employee_id = :p_employee_id
  AND (status <> :p_status OR status IS NULL);
~~~

Predicate này minh họa bỏ qua hàng đã có cùng giá trị khi NULL được xử lý. Với nhiều cột, cần viết điều kiện null-safe phù hợp; không giả định phép so sánh khác tự xử lý NULL.

### 6.3. DELETE

~~~sql
DELETE FROM employees
WHERE employee_id = 1001;
~~~

Tác động:

- Tìm hàng và lấy lock.
- Ghi undo đủ để rollback hoặc dựng phiên bản cũ.
- Ghi redo cho thay đổi hàng và index.
- Loại bỏ/đánh dấu các entry tương ứng trong index.
- Kiểm tra khóa ngoại, ON DELETE CASCADE nếu có, trigger và constraint.

DELETE không nhất thiết làm segment giảm ngay lập tức. Hàng bị xóa có thể để lại không gian có thể tái sử dụng trong segment; việc thu hồi không gian về tablespace cần thao tác riêng và phải cân nhắc vận hành.

### 6.4. MERGE

MERGE không có một cơ chế lưu trữ hoàn toàn riêng. Mỗi hàng thực tế đi qua nhánh UPDATE hoặc INSERT sẽ chịu tác động tương ứng:

- Hàng MATCHED được cập nhật: undo/redo, index maintenance và row locks như UPDATE.
- Hàng NOT MATCHED được chèn: undo/redo, index maintenance và các kiểm tra như INSERT.

Nguồn MERGE bị duplicate hoặc join fanout có thể khiến câu lệnh lỗi hoặc xử lý nhiều dòng ngoài dự kiến. Hãy chuẩn hóa nguồn theo khóa đích trước khi đánh giá chi phí.

## 7. Index làm tăng chi phí DML

Index giúp SELECT tìm dữ liệu nhanh hơn, nhưng mỗi DML phải duy trì các index bị ảnh hưởng. Một bảng có nhiều index có thể đọc tốt nhưng insert/update/delete đắt hơn.

### 7.1. INSERT và B-tree index

Khi thêm hàng, Oracle tạo entry trong từng B-tree index liên quan. Entry chứa khóa index và ROWID tham chiếu hàng trong bảng.

Nếu khóa index tăng tuần tự, nhiều insert có thể tập trung vào vùng leaf block ở cuối index. Với workload ghi rất cao, có thể phát sinh cạnh tranh buffer/latch hoặc hot block tùy cấu hình và workload.

Index split xảy ra khi leaf block không còn chỗ. Split không đồng nghĩa index hỏng; đó là hoạt động bình thường của B-tree nhưng có chi phí redo, undo và I/O.

### 7.2. UPDATE cột được index

~~~sql
CREATE INDEX ix_employees_salary
ON employees(salary);
~~~

Khi chạy:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100;
~~~

Oracle phải duy trì entry trong index salary vì khóa index thay đổi. Nếu chỉ cập nhật FIRST_NAME và index không chứa FIRST_NAME hay biểu thức phụ thuộc nó, index salary không cần thay entry.

Vì vậy, thêm index có thể làm tăng chi phí UPDATE ngay cả khi câu UPDATE không dùng index để tìm hàng, nếu cột bị thay đổi thuộc index.

### 7.3. DELETE và index entry

DELETE phải duy trì mọi index liên quan đến hàng bị xóa. Việc xóa entry khỏi index tạo thêm công việc và redo. Không nên xem DELETE chỉ là “đổi trạng thái hàng thành không tồn tại” với chi phí bằng không.

### 7.4. Index nhiều cột và function-based index

Index ghép và function-based index cũng cần được duy trì khi bất kỳ cột/biểu thức đầu vào nào thay đổi. Ví dụ:

~~~sql
CREATE INDEX ix_customer_email_upper
ON customers(UPPER(email));
~~~

UPDATE EMAIL sẽ làm thay đổi kết quả biểu thức UPPER(email), do đó cần cập nhật index này.

Index trên virtual column hoặc partitioned index cũng có chi phí DML tương ứng với thiết kế.

### 7.5. Bitmap index và DML đồng thời

Bitmap index phù hợp với một số workload phân tích có ít DML đồng thời và cột có cardinality thấp. Trong môi trường OLTP ghi đồng thời, bitmap index có thể gây phạm vi khóa/ảnh hưởng cạnh tranh rộng hơn so với B-tree index thông thường.

Không mặc định dùng bitmap index cho mọi cột trạng thái trong bảng giao dịch. Chọn loại index theo mô hình đọc/ghi và concurrency.

### 7.6. Có nên bỏ index trước batch DML?

Với bulk load rất lớn, một số kiến trúc có thể nạp vào staging hoặc partition mới, sau đó xây/rebuild index theo quy trình kiểm soát. Tuy nhiên:

- Index bị drop/unusable làm truy vấn và constraint phụ thuộc nó có thể không dùng được.
- UNIQUE index có thể đang bảo vệ tính toàn vẹn.
- Rebuild index cũng tiêu thụ I/O, TEMP, CPU và tạo redo tùy logging.
- Thời gian không có index phải được tính vào cửa sổ bảo trì.
- Concurrent DML và ứng dụng có thể bị ảnh hưởng.

Không drop index production chỉ để tăng tốc một batch nếu chưa đánh giá ràng buộc và thời gian gián đoạn.

## 8. Constraint, trigger và DML phụ

Một câu INSERT/UPDATE/DELETE có thể kích hoạt thêm công việc:

- PRIMARY KEY/UNIQUE: kiểm tra và duy trì index đảm bảo duy nhất.
- FOREIGN KEY: kiểm tra quan hệ cha-con; thao tác trên bảng cha có thể cần kiểm tra bảng con.
- CHECK/NOT NULL: xác thực dữ liệu.
- Trigger: chạy PL/SQL và có thể ghi thêm bảng audit hoặc bảng liên quan.
- ON DELETE CASCADE: xóa các hàng con theo quy tắc FK.
- Generated column/virtual column/index expression: tính toán và duy trì cấu trúc phụ.

Các thao tác phụ cũng có thể tạo undo, redo và lock. Vì thế, đo chi phí DML trên schema thật có đầy đủ trigger/constraint/index, không chỉ trên một bảng lab đơn giản.

### 8.1. Index trên foreign key

Oracle không tự động tạo index cho foreign key. Khi parent key bị DELETE hoặc UPDATE, nếu foreign key ở bảng con không có index phù hợp, Oracle có thể cần khóa bảng con để đảm bảo tính toàn vẹn trong lúc kiểm tra. Điều này có thể gây blocking cho DML đồng thời trên bảng con.

Một index trên các cột FK thường được cân nhắc nếu hệ thống thường xuyên xóa/cập nhật khóa cha hoặc có DML đồng thời ở bảng con:

~~~sql
CREATE INDEX ix_order_items_order_id
ON order_items(order_id);
~~~

Không phải mọi FK đều bắt buộc có index. Quyết định dựa vào workload, kích thước bảng con, tần suất thao tác parent key và locking behavior.

## 9. Lock trong Oracle DML

Lock bảo vệ tính toàn vẹn khi nhiều session truy cập cùng dữ liệu.

Oracle sử dụng nhiều loại enqueue/lock. Hai khái niệm thường gặp trong DML là:

- **TX enqueue:** liên quan đến transaction và row-level locking.
- **TM enqueue:** table-level DML lock bảo vệ cấu trúc/quyền thao tác tương thích trên bảng.

DML thường lấy table lock ở mức Row Exclusive (TM mode 3) trên bảng bị thay đổi và row locks cho các hàng thực sự được sửa. Cụ thể còn phụ thuộc operation, constraint và quan hệ liên quan.

### 9.1. Row lock

Khi UPDATE một hàng:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
~~~

Session giữ row lock trên hàng bị cập nhật đến khi COMMIT hoặc ROLLBACK. Session khác muốn UPDATE/DELETE cùng hàng phải chờ transaction đang giữ lock kết thúc.

DML trên hàng khác của cùng bảng thường có thể tiến hành đồng thời, miễn không xung đột qua index, constraint, khóa cha-con hoặc tài nguyên khác.

Oracle không thường xuyên nâng cấp hàng loạt row lock thành table lock theo cơ chế lock escalation như một số DBMS khác. Dù một transaction sửa nhiều hàng, nó vẫn có thể giữ nhiều row lock; table DML lock tương ứng được quản lý riêng.

### 9.2. Table lock (TM)

DML trên bảng thường lấy TM Row Exclusive lock để cho phép DML tương thích khác và ngăn một số thao tác DDL xung đột. Table lock không có nghĩa toàn bộ hàng của bảng bị khóa độc quyền.

Các chế độ TM khác có thể xuất hiện do LOCK TABLE, DDL, constraint hoặc operation cụ thể. Khi điều tra blocking, cần xem cả object, lock mode, session và blocker.

### 9.3. SELECT thông thường và SELECT FOR UPDATE

SELECT thông thường không lấy row lock để chặn UPDATE; nó đọc snapshot nhất quán nhờ undo.

Nếu ứng dụng cần đọc rồi khóa hàng để cập nhật theo quyết định nghiệp vụ, có thể dùng:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE;
~~~

Hàng được khóa cho đến khi transaction kết thúc. Các session khác muốn khóa/sửa cùng hàng có thể phải chờ.

Có thể dùng NOWAIT hoặc WAIT n để kiểm soát hành vi chờ:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE WAIT 5;
~~~

SKIP LOCKED phù hợp với một số mô hình queue/worker, nơi session bỏ qua hàng đang bị session khác khóa:

~~~sql
SELECT task_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED không phải giải pháp tổng quát để né mọi lock; phải thiết kế trạng thái claim, commit và retry để không bỏ quên công việc.

### 9.4. Lock tồn tại đến khi transaction kết thúc

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Hàng vẫn bị khóa ở đây.
-- Session khác có thể phải chờ.

COMMIT;
~~~

Không COMMIT sau từng dòng chỉ để giải phóng lock nếu nghiệp vụ cần atomicity trên cả batch. Ngược lại, transaction quá dài giữ lock lâu và tăng khả năng blocking. Cần chọn ranh giới transaction phù hợp với đơn vị nghiệp vụ.

## 10. Blocking và deadlock

### 10.1. Blocking

Session A:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
-- Chưa commit
~~~

Session B:

~~~sql
UPDATE accounts
SET balance = balance + 50
WHERE account_id = 10;
~~~

B phải chờ vì A đang giữ row lock. Khi A COMMIT hoặc ROLLBACK, B mới có thể tiếp tục tùy trạng thái và điều kiện.

Blocking là hiện tượng chờ lock, không nhất thiết là lỗi. Cần xác định blocker, thời gian chờ, SQL đang chạy và lý do transaction chưa kết thúc.

### 10.2. Deadlock

Deadlock xảy ra khi các session chờ tài nguyên khóa theo vòng tròn.

Session A:
~~~sql
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;
~~~

Session B:
~~~sql
UPDATE accounts SET balance = balance - 10 WHERE account_id = 2;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 1;
~~~

Một thứ tự thực thi có thể xảy ra:

1. A khóa account 1.
2. B khóa account 2.
3. A chờ account 2 do B giữ.
4. B chờ account 1 do A giữ.
5. Oracle phát hiện vòng chờ và chọn một statement để báo lỗi ORA-00060.

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

Oracle thường rollback statement gây deadlock, không tự động rollback toàn bộ transaction của ứng dụng. Ứng dụng phải xử lý transaction đang ở trạng thái phù hợp, rollback nếu cần và retry toàn bộ đơn vị nghiệp vụ theo chính sách an toàn.

### 10.3. Giảm nguy cơ deadlock

- Cập nhật nhiều bảng/hàng theo một thứ tự khóa thống nhất.
- Giữ transaction ngắn, tránh chờ người dùng hoặc gọi API bên ngoài khi đang giữ lock.
- Tìm đúng blocker và câu SQL gây xung đột.
- Dùng khóa theo thứ tự ổn định khi xử lý danh sách nhiều ID.
- Thiết kế batch để các worker không tranh cùng business key.
- Retry có giới hạn, backoff và idempotency; không lặp vô hạn.
- Không dùng COMMIT rải rác giữa một nghiệp vụ cần atomicity chỉ để né deadlock.

## 11. Chi phí DML khi có nhiều index

Giả sử bảng ORDERS có:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);

CREATE INDEX ix_orders_status_date
ON orders(status, created_at);

CREATE INDEX ix_orders_external_ref
ON orders(external_reference);
~~~

Khi INSERT một đơn hàng, Oracle phải duy trì cả ba index. Khi UPDATE STATUS, index status/date cần được cập nhật. Khi UPDATE CUSTOMER_ID, index customer cần được cập nhật. Khi UPDATE một cột không nằm trong các index và không ảnh hưởng expression/constraint, các index này có thể không cần thay entry.

| Thay đổi | Table block | Index customer | Index status/date | Index external ref |
|---|---|---|---|---|
| INSERT hàng mới | Có | Thêm entry | Thêm entry | Thêm entry |
| UPDATE STATUS | Có | Thường không đổi | Cập nhật entry | Thường không đổi |
| UPDATE CUSTOMER_ID | Có | Cập nhật entry | Thường không đổi | Thường không đổi |
| UPDATE ghi chú không index | Có | Không đổi | Không đổi | Không đổi |
| DELETE hàng | Xóa/đánh dấu hàng | Duy trì xóa entry | Duy trì xóa entry | Duy trì xóa entry |

Bảng chỉ minh họa index trực tiếp phụ thuộc cột; trigger, function-based index, virtual column, partitioning và constraint có thể tạo thêm công việc.

### 11.1. Index nhiều hơn không phải lúc nào cũng tốt

Index giúp giảm chi phí SELECT nhưng tăng chi phí DML. Mỗi index có dung lượng, redo/undo, CPU, buffer và bảo trì riêng.

Khi đánh giá một index, cân nhắc tần suất và latency của truy vấn đọc, tần suất INSERT/UPDATE/DELETE, cột thường xuyên bị thay đổi, selectivity, index trùng lặp/prefix, dung lượng và khả năng index phục vụ constraint.

Không xóa index chỉ vì thấy DML chậm; phải xác nhận index không cần thiết và không bảo vệ tính toàn vẹn.

## 12. Batch DML, kích thước transaction và COMMIT

Một transaction quá lớn có thể tạo nhiều undo, redo và giữ lock lâu. Nhưng commit từng dòng lại tạo nhiều transaction nhỏ, tăng round trip/commit overhead và làm mất atomicity của batch.

### 12.1. Tránh COMMIT từng hàng

Anti-pattern:

~~~sql
BEGIN
    FOR r IN (SELECT employee_id FROM stage_employees) LOOP
        UPDATE employees
        SET status = 'PROCESSED'
        WHERE employee_id = r.employee_id;

        COMMIT;
    END LOOP;
END;
/
~~~

Nếu batch có 100.000 hàng, code có thể tạo 100.000 transaction. Điều này gây overhead và nếu lỗi giữa chừng, batch đã commit một phần mà không còn atomic.

Nếu nghiệp vụ cần tất cả hoặc không có gì, commit một lần sau khi hoàn thành và kiểm tra batch. Nếu batch quá lớn, chia thành các đơn vị commit có định danh và khả năng resume rõ ràng.

### 12.2. Dùng set-based DML

Thường ưu tiên một câu UPDATE cho tập hàng thay vì vòng lặp từng hàng:

~~~sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login_at < :p_cutoff_date
  AND status <> 'INACTIVE';
~~~

Set-based DML giảm số lần parse/execute và round trip, để optimizer xử lý tập dữ liệu. Điều kiện status còn giúp tránh update hàng đã ở trạng thái mong muốn; cần xử lý riêng NULL nếu cột nullable.

### 12.3. FORALL và BULK COLLECT

Khi bắt buộc xử lý bằng PL/SQL collection, BULK COLLECT và FORALL giảm context switch giữa PL/SQL và SQL:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM stage_employee_ids
    WHERE batch_id = :p_batch_id;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'PROCESSED'
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

Đây là ví dụ cơ bản. Với tập lớn, BULK COLLECT không giới hạn có thể tiêu thụ nhiều PGA; dùng LIMIT trong vòng lặp fetch khi cần kiểm soát bộ nhớ. FORALL có thể kết hợp SAVE EXCEPTIONS để thu thập lỗi từng phần tử, nhưng phải xác định cách xử lý transaction và dữ liệu lỗi.

Nếu thao tác có thể viết bằng một câu SQL set-based, đó thường là lựa chọn đơn giản hơn.

### 12.4. Chọn batch size

Không có một batch size tối ưu cho mọi hệ thống. Cần cân nhắc số hàng/kích thước hàng, undo/redo sinh ra, thời gian giữ lock, thời gian phục hồi nếu lỗi, PGA/TEMP và I/O, tần suất commit, yêu cầu atomicity, khả năng chạy lại và số worker song song.

Đo với batch đại diện, theo dõi undo/redo, elapsed time, waits và blocking. Chọn điểm cân bằng giữa throughput, khả năng phục hồi và mức độ ảnh hưởng ứng dụng.

## 13. Direct-path INSERT và NOLOGGING

Với nạp dữ liệu lớn, Oracle có thể hỗ trợ direct-path INSERT trong một số điều kiện:

~~~sql
INSERT /*+ APPEND */ INTO sales_archive
SELECT *
FROM sales_stage
WHERE batch_id = :p_batch_id;
~~~

Direct path có thể ghi dữ liệu theo đường riêng, thường tránh một số thao tác buffer cache thông thường và có thể giảm chi phí trong bulk load. Hành vi cụ thể phụ thuộc bảng, partition, constraint, trigger, parallelism và release.

### 13.1. LOGGING và NOLOGGING

NOLOGGING không phải công tắc tắt redo cho mọi UPDATE/DELETE. Nó chỉ giảm redo cho một số operation đủ điều kiện, ví dụ một số direct-path load hoặc tạo/rebuild cấu trúc, tùy chế độ và cấu hình.

Các lưu ý:

- FORCE LOGGING ở database/tablespace có thể ghi đè lựa chọn NOLOGGING.
- NOLOGGING operation có thể làm data block không thể phục hồi từ redo/archived log theo cách thông thường cho khoảng operation đó.
- Cần backup phù hợp ngay sau operation NOLOGGING theo quy trình recovery.
- Index và metadata liên quan vẫn có thể tạo redo.
- NOLOGGING không làm mất yêu cầu undo/transaction/constraint theo một quy tắc chung.

Không dùng NOLOGGING cho bảng giao dịch đang cần khả năng media recovery đầy đủ nếu chưa được DBA và quy trình backup/recovery chấp thuận.

### 13.2. Direct path không đồng nghĩa “không có undo, redo hoặc lock”

Direct-path INSERT có thể thay đổi cách ghi data block và lượng undo/redo so với conventional insert, nhưng vẫn có các quy tắc về transaction, metadata, index, constraint và logging. Không khái quát rằng APPEND loại bỏ hoàn toàn undo hoặc redo. Kiểm tra đúng operation, release và logging mode.

## 14. DML lỗi giữa chừng và tính nguyên tử

Một câu DML đơn lẻ có tính atomic ở mức statement: nếu statement lỗi, Oracle hoàn tác các thay đổi của statement đó. Các thay đổi trước đó trong transaction vẫn có thể còn nếu chưa rollback transaction.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 999999;
~~~

Nếu câu thứ hai không cập nhật hàng nào, đó không phải lỗi SQL tự động. Nếu câu thứ hai phát sinh constraint violation, statement thứ hai bị rollback; statement đầu vẫn thuộc transaction và chưa tự động biến mất. Ứng dụng cần quyết định COMMIT hay ROLLBACK transaction.

Có thể dùng SAVEPOINT để giới hạn phần rollback:

~~~sql
SAVEPOINT before_second_step;

-- DML tiếp theo
-- Nếu bước này lỗi:
ROLLBACK TO before_second_step;
~~~

### 14.1. LOG ERRORS cho một số lỗi DML theo hàng

Oracle hỗ trợ DML error logging cho một số trường hợp, giúp lưu lỗi của các hàng riêng lẻ và tiếp tục xử lý hàng khác khi cú pháp/điều kiện cho phép:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'CUSTOMERS',
        err_log_table_name => 'ERR$_CUSTOMERS'
    );
END;
/
~~~

Sau đó:

~~~sql
INSERT INTO customers(customer_id, customer_name)
SELECT customer_id, customer_name
FROM stage_customers
LOG ERRORS INTO err$_customers ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

DML error logging không xử lý mọi loại lỗi và không thay thế việc xác định tính hợp lệ của batch. Kiểm tra loại constraint, lỗi statement-level, trigger và operation cụ thể theo tài liệu Oracle. Bảng error log cũng cần được quản lý và đối soát.

## 15. Theo dõi lock và blocking

Khi ứng dụng báo câu UPDATE bị treo, cần xác định session chờ và session chặn.

### 15.1. Xem session đang chờ

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Các cột giúp nhận diện session đang chờ, event, thời gian chờ, blocker và SQL ID.

### 15.2. Xem object bị khóa

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

LOCKED_MODE là mã chế độ khóa; cần tra tài liệu Oracle để diễn giải chính xác theo loại lock. View DBA_OBJECTS và V$LOCKED_OBJECT có thể yêu cầu quyền cao hơn tài khoản ứng dụng.

### 15.3. Xem TX/TM lock

~~~sql
SELECT l.sid,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
WHERE l.type IN ('TX', 'TM')
ORDER BY l.type, l.sid;
~~~

TX/TM là loại enqueue thường liên quan đến transaction và table DML. Các cột LMODE/REQUEST thể hiện mode đang giữ và mode đang yêu cầu. Muốn hiểu một lock cụ thể, kết hợp V$SESSION, object ID, SQL đang chạy và blocker chain.

Không kill session chỉ dựa trên việc thấy lock. Trước tiên xác định transaction owner, công việc chưa commit, ảnh hưởng nghiệp vụ và quy trình vận hành.

## 16. Theo dõi redo và hiệu năng DML

Một số chỉ số hữu ích:

- Redo size/redo entries: lượng redo tạo ra.
- Logical reads và physical reads.
- Buffer gets và elapsed time.
- Undo blocks/records.
- Wait events liên quan đến log file sync, log file parallel write, buffer busy waits, enq: TX và enq: TM.
- Số hàng được xử lý, số lỗi constraint và số lần retry.
- Số index/trigger và thời gian chạy của từng bước batch.

Có thể xem thống kê hệ thống tổng quát:

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'user commits',
    'user rollbacks',
    'db block changes'
)
ORDER BY name;
~~~

Đây là bộ đếm tích lũy từ lúc instance khởi động hoặc reset thống kê. Để đo một batch, chụp giá trị trước/sau trong cùng khoảng và hiểu rằng workload khác cũng có thể đóng góp vào tổng hệ thống. Trong môi trường nhiều ứng dụng, cần dùng công cụ giám sát/SQL trace phù hợp để quy trách nhiệm chính xác hơn.

### 16.1. LOG FILE SYNC

Session foreground thường chờ LGWR hoàn tất ghi redo commit khi COMMIT theo chế độ WAIT. Wait event `log file sync` có thể tăng nếu commit quá thường xuyên, redo I/O chậm hoặc LGWR bị tải cao.

Không nên mặc định mọi log file sync đều do commit từng dòng. Đối chiếu thời gian wait, số commit, LGWR write latency, redo generation và workload.

### 16.2. Enqueue waits

Các event như `enq: TX - row lock contention` thường chỉ ra session đang chờ transaction khác nhả khóa hàng hoặc một tình huống TX enqueue liên quan. `enq: TM - contention` liên quan table enqueue. Cần xem blocker và SQL cụ thể; không phải mọi TX wait đều có cùng nguyên nhân.

## 17. Ví dụ lab: quan sát undo, redo và row lock

Chỉ chạy trên schema lab được phép. Không thực hiện thử nghiệm khóa trên bảng production.

### 17.1. Tạo bảng thử

~~~sql
CREATE TABLE lab_dml_account (
    account_id NUMBER PRIMARY KEY,
    balance NUMBER(12,2) NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL
);

INSERT INTO lab_dml_account VALUES (1, 1000, 'OPEN');
INSERT INTO lab_dml_account VALUES (2, 2000, 'OPEN');
COMMIT;
~~~

### 17.2. Session A: cập nhật nhưng chưa commit

~~~sql
UPDATE lab_dml_account
SET balance = balance - 100
WHERE account_id = 1;
~~~

Transaction A giữ row lock trên account 1. Undo cho phép rollback về balance 1000 và hỗ trợ reader dựng phiên bản nhất quán trước thay đổi.

### 17.3. Session B: đọc và ghi

Trong session B, SELECT thông thường:

~~~sql
SELECT balance
FROM lab_dml_account
WHERE account_id = 1;
~~~

Ở READ COMMITTED, B thường đọc giá trị đã commit trước đó (1000), không thấy thay đổi chưa commit của A.

Tiếp theo thử UPDATE cùng hàng:

~~~sql
UPDATE lab_dml_account
SET balance = balance + 50
WHERE account_id = 1;
~~~

B phải chờ A kết thúc transaction.

### 17.4. Kết thúc Session A

~~~sql
COMMIT;
~~~

Sau khi A commit, B có thể tiếp tục và cập nhật theo trạng thái mới nhất phù hợp với statement execution. Nếu A ROLLBACK, B sẽ tiếp tục trên trạng thái đã khôi phục.

### 17.5. Quan sát rollback

Trong session khác, chạy:

~~~sql
UPDATE lab_dml_account
SET balance = 0
WHERE account_id = 2;

ROLLBACK;
~~~

Kiểm tra lại balance của account 2 vẫn là 2000.

### 17.6. Dọn bảng lab

~~~sql
DROP TABLE lab_dml_account PURGE;
~~~

Chỉ xóa bảng lab do chính bạn tạo.

## 18. Quy trình đánh giá một batch DML

Trước khi chạy batch lớn, có thể dùng quy trình:

1. **Xác định phạm vi hàng.** Chạy SELECT với cùng predicate để ước lượng số hàng và xác nhận điều kiện.
2. **Kiểm tra plan.** Xem access path, index, cardinality estimate và số lần truy cập.
3. **Đánh giá index.** Xác định cột nào bị thay đổi và index nào phải duy trì.
4. **Đánh giá constraint/trigger.** Tính cả cascade, audit và DML phụ.
5. **Ước lượng undo/redo.** Dùng batch thử đại diện và theo dõi V$UNDOSTAT, V$TRANSACTION, redo statistics.
6. **Chọn transaction boundary.** Đảm bảo atomicity nghiệp vụ, nhưng tránh giữ lock quá lâu.
7. **Chọn set-based hoặc bulk.** Ưu tiên set-based; dùng FORALL khi thực sự cần xử lý theo collection.
8. **Xử lý lỗi và retry.** Có savepoint, error logging hoặc quarantine theo yêu cầu.
9. **Theo dõi blocking.** Kiểm tra TX/TM waits, blocker và thời gian transaction.
10. **Đối soát kết quả.** Đếm số hàng, kiểm tra tổng và ghi audit batch.
11. **Xác nhận recovery.** Với direct path/NOLOGGING, kiểm tra logging mode và backup/recovery policy.

## 19. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| COMMIT ghi toàn bộ data block xuống datafile | COMMIT cần redo commit bền vững theo cấu hình; DBWR có thể ghi data block sau |
| Undo và redo là một loại log | Undo đảo ngược/dựng phiên bản cũ; redo phục hồi thay đổi |
| SELECT luôn chờ UPDATE | Consistent read thường dùng undo, không cần chờ row lock của writer |
| UPDATE một cột không index không tạo redo | Thay đổi bảng vẫn tạo undo/redo; chỉ có thể không cần cập nhật entry của index không liên quan |
| Có nhiều index chỉ ảnh hưởng SELECT | Mọi index bị ảnh hưởng đều tăng công việc DML |
| DELETE lập tức trả không gian cho tablespace | Không gian có thể được tái sử dụng trong segment; thu hồi về tablespace là vấn đề riêng |
| COMMIT từng dòng luôn nhanh hơn | Có thể tăng commit overhead và làm mất atomicity |
| Undo retention luôn được bảo đảm bởi UNDO_RETENTION | Đây là mục tiêu, khả năng giữ thực tế còn phụ thuộc dung lượng và retention guarantee |
| NOLOGGING tắt redo cho mọi DML | Chỉ áp dụng cho một số operation đủ điều kiện; FORCE LOGGING và recovery policy ảnh hưởng |
| Oracle tự nâng row lock thành table lock khi sửa nhiều dòng | Oracle không thường dùng lock escalation kiểu đó; row lock và TM lock là cơ chế riêng |
| MERGE chỉ tốn một lần ghi | Mỗi hàng insert/update vẫn có chi phí undo, redo, index, constraint và lock |

## 20. Ghi nhớ cốt lõi

- DML thay đổi bảng và có thể kéo theo undo, redo, index maintenance, lock, constraint và trigger.
- **Undo** phục vụ rollback và consistent read; **redo** bảo vệ thay đổi cho recovery.
- Reader thông thường dùng multiversion read consistency; writer xung đột trên cùng hàng phải chờ transaction giữ lock.
- COMMIT xác nhận transaction và ghi redo theo commit semantics; DBWR có thể ghi data block xuống datafile sau đó.
- INSERT/UPDATE/DELETE đều có chi phí undo/redo và index tương ứng; MERGE kết hợp các tác động đó theo nhánh thực tế.
- Nhiều index cải thiện một số truy vấn nhưng tăng chi phí ghi và lưu trữ.
- TX enqueue gắn với transaction/row locking; TM enqueue bảo vệ thao tác DML ở cấp bảng.
- Transaction dài giữ lock lâu và có thể tạo nhiều undo; commit quá thường xuyên cũng gây overhead.
- Dùng set-based DML hoặc FORALL phù hợp; chọn batch size dựa trên đo đạc và ranh giới nghiệp vụ.
- Direct-path/NOLOGGING có giới hạn và hệ quả recovery; không đồng nghĩa loại bỏ mọi undo/redo.
- Theo dõi undo, redo, lock waits, blocking, execution plan và đối soát số hàng để hiểu chi phí thực tế.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, undo, redo, locking và read consistency.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Undo management, redo log files, ARCHIVELOG và recovery.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — INSERT, UPDATE, DELETE, MERGE, SELECT FOR UPDATE và DML error logging.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Wait events, redo, buffer activity và execution plan.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — FORALL, BULK COLLECT và exception handling.

Hành vi chi tiết của direct path, NOLOGGING, undo retention, lock mode và commit write có thể khác theo phiên bản/cấu hình Oracle. Đối chiếu đúng release và đo trên schema có cùng index, constraint, trigger và workload với môi trường triển khai.

