# SCN và mối quan hệ giữa COMMIT với yêu cầu phục hồi trong Oracle

Trong Oracle Database, **SCN (System Change Number)** là một số thứ tự logic dùng để xác định vị trí của các thay đổi trong cơ sở dữ liệu. SCN giúp Oracle duy trì tính nhất quán khi đọc dữ liệu, ghi nhận thời điểm transaction được commit, áp dụng redo khi phục hồi và truy vấn lại phiên bản dữ liệu trong quá khứ.

Khi một transaction chạy **COMMIT**, Oracle ghi nhận việc transaction đã hoàn tất trong redo và gắn với một commit SCN. Commit không có nghĩa mọi data block đã được ghi ngay xuống datafile. Redo, undo và cơ chế phục hồi phối hợp để bảo đảm thay đổi đã commit có thể được khôi phục sau sự cố, trong khi thay đổi chưa commit không trở thành dữ liệu đã xác nhận.

Bài học này giải thích SCN là gì, quan hệ giữa SCN và COMMIT, cách Oracle dùng SCN cho read consistency, Flashback và recovery, cách quan sát SCN bằng SQL, và cách chọn mốc phục hồi theo yêu cầu nghiệp vụ.

## 1. SCN là gì?

SCN là **System Change Number**, một giá trị số do Oracle quản lý để sắp thứ tự các sự kiện/thay đổi trong database. Có thể xem SCN như một chiếc đồng hồ logic của cơ sở dữ liệu:

- SCN giúp xác định một điểm nhất quán trong lịch sử database.
- Các transaction commit được gắn với thông tin SCN.
- Redo record và thông tin phục hồi được tổ chức để Oracle có thể áp dụng thay đổi theo thứ tự phù hợp.
- Một truy vấn có thể yêu cầu đọc dữ liệu như tại một SCN trong quá khứ nếu thông tin phiên bản cần thiết vẫn còn.

SCN **không phải thời gian đồng hồ** và không phải số dòng đã thay đổi. Không thể suy ra “một SCN tương đương một giây” hoặc “mỗi UPDATE tăng SCN đúng một đơn vị”. SCN là mốc thứ tự logic; quan hệ giữa SCN và thời gian thực chỉ có thể được ánh xạ gần đúng trong phạm vi Oracle còn lưu thông tin ánh xạ.

### 1.1. SCN giúp xác định một điểm nhất quán

Giả sử bảng tài khoản ban đầu có:

| ACCOUNT_ID | BALANCE |
|---:|---:|
| 1 | 1000 |
| 2 | 500 |

Một transaction chuyển 200 từ tài khoản 1 sang tài khoản 2:

~~~sql
UPDATE account
SET balance = balance - 200
WHERE account_id = 1;

UPDATE account
SET balance = balance + 200
WHERE account_id = 2;

COMMIT;
~~~

Sau COMMIT, trạng thái mới là 800 và 700. Oracle ghi nhận transaction đã commit tại một vị trí logic trong lịch sử database. Commit SCN giúp phân biệt phiên bản trước và sau transaction.

Nếu một truy vấn cần đọc trạng thái trước lần chuyển tiền, Oracle có thể dùng thông tin undo để tái dựng phiên bản dữ liệu tại SCN cũ, miễn là dữ liệu undo cần thiết còn sẵn và các điều kiện Flashback phù hợp.

### 1.2. SCN là logic clock, không phải timestamp

| Thuộc tính | SCN | Timestamp |
|---|---|---|
| Bản chất | Số thứ tự logic do Oracle quản lý | Thời gian lịch |
| Dùng để | Thứ tự thay đổi, nhất quán, recovery | Diễn đạt thời điểm theo lịch |
| Tăng theo giây? | Không | Có đơn vị thời gian |
| Ánh xạ chính xác 1:1? | Không | Không áp dụng |
| Có thể dùng làm mốc Flashback? | Có | Có thể đổi timestamp sang SCN gần đúng |

Khi cần một mốc phục hồi chính xác, SCN thường hữu ích hơn thời gian do người vận hành nhập. Tuy nhiên, phải lấy SCN từ đúng sự kiện và đúng database/incarnation; một con số SCN tự nó không chứa backup hay redo cần thiết để phục hồi.

## 2. COMMIT tạo ra điều gì?

Transaction thường gồm một hoặc nhiều câu DML:

~~~sql
UPDATE lab_scn_account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_scn_account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Ở mức khái niệm, COMMIT làm Oracle xác nhận transaction đã hoàn tất. Cơ sở dữ liệu ghi thông tin commit vào redo; transaction được gắn với commit SCN và các session khác có thể nhìn thấy thay đổi theo quy tắc nhất quán đọc của Oracle.

Điểm quan trọng: COMMIT **không yêu cầu DBWR ghi ngay tất cả block đã thay đổi xuống datafile**. Việc ghi data block có thể diễn ra sau. Redo log là thành phần quan trọng để Oracle phục hồi các thay đổi đã commit nếu instance gặp sự cố trước khi dirty block được ghi ra datafile.

### 2.1. Redo và undo có vai trò khác nhau

| Thành phần | Vai trò chính |
|---|---|
| Redo | Ghi lại thông tin cần thiết để tái áp dụng thay đổi khi recovery |
| Undo | Giữ thông tin phiên bản cũ để rollback và cung cấp consistent read |
| Online redo log | Lưu redo theo các nhóm log của database |
| Archived redo log | Bản lưu redo log đã đầy, cần thiết cho nhiều kịch bản media recovery/PITR |
| Datafile | Lưu các block dữ liệu của database |

Mô hình đơn giản:

~~~text
SQL DML
  |
  +----> Thay đổi block trong buffer cache
  |
  +----> Tạo redo trong redo log buffer
  |
  +----> Tạo undo để có thể rollback/đọc phiên bản cũ
                 |
                 v
              COMMIT
                 |
                 v
       Ghi commit record và SCN vào redo
                 |
                 v
        LGWR ghi redo theo cơ chế commit
                 |
                 v
        COMMIT được xác nhận cho client
                 |
                 v
       DBWR ghi dirty block xuống datafile
       (có thể diễn ra sau COMMIT)
~~~

Đây là mô hình khái niệm; chi tiết nội bộ phụ thuộc kiến trúc và cấu hình Oracle. Cần nhớ hai điều:

1. Redo bảo vệ khả năng phục hồi thay đổi đã commit.
2. Undo hỗ trợ hoàn tác và đọc phiên bản nhất quán; undo không thay thế backup hoặc archived redo log.

### 2.2. Vì sao COMMIT không chờ DBWR ghi datafile?

Nếu COMMIT phải đợi mọi data block được ghi vật lý xuống datafile, transaction sẽ bị phụ thuộc vào việc ghi nhiều vị trí dữ liệu. Oracle dùng redo để tách xác nhận transaction khỏi thời điểm DBWR ghi các block dữ liệu.

Trong cấu hình commit đồng bộ thông thường, LGWR phải ghi redo cần thiết (bao gồm commit record) ra online redo log trước khi COMMIT trả về thành công cho client. DBWR có thể ghi block dữ liệu sau đó. Nếu instance mất điện sau khi COMMIT trả về nhưng trước khi DBWR ghi block, instance recovery có thể đọc redo để áp dụng lại thay đổi đã commit.

Đừng diễn giải điều này thành “COMMIT không ghi gì xuống đĩa”. COMMIT thông thường chờ cơ chế ghi redo theo cấu hình commit; phần được chờ là redo, không phải toàn bộ datafile.

## 3. Commit SCN và thời điểm transaction được xác nhận

Khi transaction commit, Oracle ghi commit record trong redo và gắn commit SCN. Commit SCN giúp xác định phiên bản dữ liệu sau transaction.

Một vài điểm cần phân biệt:

- SCN hiện tại của database là mốc logic đang được quản lý tại thời điểm quan sát.
- Commit SCN của một transaction là mốc gắn với việc transaction đó hoàn tất.
- SCN của một câu SELECT là mốc nhất quán mà câu truy vấn dùng để đọc dữ liệu.
- Checkpoint SCN là thông tin liên quan đến tiến độ checkpoint và recovery, không đồng nghĩa với commit SCN của một transaction cụ thể.

Không nên lấy một giá trị CURRENT_SCN bất kỳ rồi khẳng định đó là commit SCN của transaction vừa chạy. Nếu cần điều tra transaction cụ thể, phải dùng nguồn thông tin phù hợp như redo/log mining, audit, Flashback Version Query hoặc các view quản trị có liên quan.

### 3.1. Thứ tự các transaction

Giả sử session A commit transaction T1, sau đó session B commit transaction T2. Oracle quản lý thứ tự logic của các sự kiện để các cơ chế đọc nhất quán và phục hồi hiểu được trạng thái database tại từng mốc. Commit SCN là một phần của thông tin đó.

Không suy luận rằng mọi câu SQL trong một transaction đều có một SCN riêng giống commit SCN. Transaction có nhiều thao tác DML nhưng chỉ hoàn tất tại ranh giới commit của nó.

## 4. COMMIT và khả năng nhìn thấy dữ liệu ở session khác

Oracle mặc định dùng mức cô lập READ COMMITTED trong nhiều ứng dụng. Mỗi câu SELECT nhìn một snapshot nhất quán tại thời điểm bắt đầu câu truy vấn (statement-level read consistency).

Ta có thể quan sát bằng hai session.

### 4.1. Chuẩn bị bảng thử nghiệm

Chạy trong schema lab của PDB thực hành. Nếu bảng đã tồn tại, dùng tên khác hoặc schema lab mới.

~~~sql
CREATE TABLE lab_scn_account (
    account_id NUMBER(6) PRIMARY KEY,
    holder_name VARCHAR2(50 CHAR) NOT NULL,
    balance NUMBER(14,2) NOT NULL
);

INSERT INTO lab_scn_account VALUES (1, 'An', 1000);
INSERT INTO lab_scn_account VALUES (2, 'Binh', 500);
COMMIT;
~~~

### 4.2. Session A cập nhật nhưng chưa commit

~~~sql
UPDATE lab_scn_account
SET balance = 800
WHERE account_id = 1;
~~~

Session A nhìn thấy số dư 800 trong transaction của chính nó.

### 4.3. Session B đọc trước khi A commit

Trong session B:

~~~sql
SELECT account_id, balance
FROM lab_scn_account
WHERE account_id = 1;
~~~

Session B đọc phiên bản đã commit trước đó, số dư 1000. Nó không nhìn thấy thay đổi chưa commit của session A. Trong trường hợp thông thường, SELECT không bị chặn chỉ vì A đang giữ row lock trên dòng được cập nhật; Oracle dùng undo để cung cấp phiên bản nhất quán.

### 4.4. Session A COMMIT, session B đọc lại

Session A:

~~~sql
COMMIT;
~~~

Sau đó session B chạy một câu SELECT mới:

~~~sql
SELECT account_id, balance
FROM lab_scn_account
WHERE account_id = 1;
~~~

Session B có thể nhìn thấy số dư 800 vì câu SELECT mới bắt đầu sau khi transaction A đã commit.

### 4.5. Một câu SELECT đang chạy không đổi snapshot giữa chừng

Một câu truy vấn dài có thể bắt đầu ở SCN S. Nếu transaction khác commit trong lúc câu SELECT đang chạy, truy vấn đó vẫn đọc dữ liệu nhất quán tại snapshot mà nó đã chọn, thay vì lấy một phần dòng từ trước commit và một phần từ sau commit.

Oracle có thể dùng undo để dựng lại phiên bản phù hợp với SCN truy vấn. Nếu undo cần thiết đã bị ghi đè trước khi truy vấn hoàn tất, có thể gặp ORA-01555: snapshot too old.

## 5. Đọc dữ liệu tại một SCN bằng Flashback Query

Flashback Query cho phép truy vấn phiên bản dữ liệu tại một SCN trong quá khứ:

~~~sql
SELECT account_id, holder_name, balance
FROM lab_scn_account AS OF SCN 123456
ORDER BY account_id;
~~~

123456 chỉ là giá trị minh họa; phải thay bằng SCN thực đã ghi nhận từ database. Oracle dùng thông tin undo để tái dựng phiên bản dòng tại thời điểm đó.

### 5.1. Lấy SCN hiện tại

Có thể đọc SCN hiện tại qua package:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Hoặc qua dynamic performance view nếu tài khoản có quyền:

~~~sql
SELECT current_scn
FROM v$database;
~~~

DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER trả về SCN hiện tại mà database đang báo. V$DATABASE.CURRENT_SCN cũng là thông tin SCN hiện tại. Hai giá trị này dùng để quan sát mốc database; chúng không tự động đại diện cho commit SCN của một transaction cụ thể.

### 5.2. Thí nghiệm trước và sau COMMIT

Trên bảng LAB_SCN_ACCOUNT, ghi nhận SCN trước khi thay đổi:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_before
FROM dual;
~~~

Ghi lại giá trị được trả về, ký hiệu là S_BEFORE. Sau đó:

~~~sql
UPDATE lab_scn_account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_scn_account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Lấy SCN hiện tại sau COMMIT:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_after
FROM dual;
~~~

Ghi lại giá trị này, ký hiệu là S_AFTER. Có thể so sánh phiên bản:

~~~sql
-- Thay giá trị dưới đây bằng S_BEFORE đã ghi nhận.
SELECT account_id, balance
FROM lab_scn_account AS OF SCN 123456
ORDER BY account_id;

-- Thay giá trị dưới đây bằng S_AFTER đã ghi nhận.
SELECT account_id, balance
FROM lab_scn_account AS OF SCN 123789
ORDER BY account_id;
~~~

Kết quả ở SCN trước phản ánh số dư trước chuyển tiền; kết quả ở SCN sau phản ánh số dư sau chuyển tiền, nếu undo còn đủ để đọc phiên bản cũ.

Không lấy số SCN ví dụ trong code làm mốc thật. Luôn thay bằng giá trị đã ghi từ session/database của mình.

### 5.3. Điều kiện và giới hạn Flashback Query

Flashback Query phụ thuộc vào khả năng truy cập phiên bản cũ:

- Undo cần thiết vẫn còn trong undo tablespace.
- Tài khoản có quyền phù hợp để dùng tính năng Flashback Query.
- Đối tượng và loại dữ liệu đáp ứng các giới hạn của Flashback.
- Không có thao tác DDL hoặc thay đổi cấu trúc khiến phiên bản cần đọc không còn khả dụng theo giới hạn của tính năng.

UNDO_RETENTION là mục tiêu thời gian lưu undo, không phải lời hứa tuyệt đối rằng mọi phiên bản cũ luôn được giữ. Nếu undo tablespace chịu áp lực và không có cấu hình bảo đảm retention phù hợp, Oracle có thể tái sử dụng undo trước khi hết khoảng thời gian mục tiêu. Khi đó truy vấn cũ có thể gặp ORA-01555.

## 6. Flashback Version Query: xem lịch sử phiên bản dòng

Ngoài việc đọc dữ liệu tại một SCN, Oracle có thể hiển thị các phiên bản của dòng trong một khoảng SCN bằng Flashback Version Query:

~~~sql
SELECT
    versions_startscn,
    versions_endscn,
    versions_operation,
    versions_xid,
    account_id,
    balance
FROM lab_scn_account
VERSIONS BETWEEN SCN 123456 AND 123789
WHERE account_id = 1
ORDER BY versions_startscn;
~~~

Thay hai SCN minh họa bằng khoảng SCN thật.

Các cột pseudo đáng chú ý:

| Cột | Ý nghĩa |
|---|---|
| VERSIONS_STARTSCN | SCN bắt đầu phiên bản được trả về |
| VERSIONS_ENDSCN | SCN kết thúc phiên bản; có thể NULL với phiên bản hiện hành trong khoảng |
| VERSIONS_OPERATION | Loại thao tác tạo phiên bản, thường là I, U hoặc D |
| VERSIONS_XID | Transaction ID liên quan đến phiên bản |

Flashback Version Query hữu ích để điều tra một dòng đã thay đổi như thế nào, trong khoảng lịch sử mà Oracle còn đủ thông tin phiên bản.

Không coi đây là audit log vĩnh viễn. Undo có thời hạn và mục tiêu retention; nếu cần lịch sử nghiệp vụ lâu dài, hãy thiết kế audit/history table, Unified Auditing, CDC hoặc cơ chế lưu trữ phù hợp.

## 7. SCN_TO_TIMESTAMP và TIMESTAMP_TO_SCN

Oracle có các hàm ánh xạ SCN và timestamp:

~~~sql
SELECT SCN_TO_TIMESTAMP(123456) AS approximate_time
FROM dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
    TIMESTAMP '2026-11-14 10:00:00'
) AS approximate_scn
FROM dual;
~~~

Các giá trị ở đây chỉ minh họa. Thay bằng SCN và timestamp phù hợp với database thực tế.

### 7.1. Ánh xạ có tính gần đúng

SCN_TO_TIMESTAMP trả timestamp gần đúng tương ứng với SCN; TIMESTAMP_TO_SCN trả SCN gần đúng tương ứng với timestamp. Ánh xạ được lưu trong một phạm vi lịch sử có giới hạn, không phải bảng quy đổi đầy đủ mãi mãi.

Nếu SCN yêu cầu nằm ngoài phạm vi ánh xạ được lưu, Oracle có thể báo lỗi như ORA-08181: specified number is not a valid system change number.

Vì vậy:

- Dùng SCN đã ghi nhận trực tiếp khi cần mốc chính xác.
- Dùng timestamp-to-SCN để tìm mốc gần thời gian nghiệp vụ khi phù hợp.
- Xác nhận dữ liệu sau khi truy vấn Flashback; không giả định ánh xạ timestamp cho ra đúng mili-giây của commit.

### 7.2. SCN không phải thời gian commit chính xác của từng dòng

Hai transaction có thể commit gần nhau theo thời gian. Không thể suy ra thời điểm commit chính xác của một dòng chỉ bằng cách lấy SCN rồi chuyển thành timestamp. Hãy kết hợp transaction ID, audit, application log và thông tin redo khi điều tra yêu cầu có độ chính xác cao.

## 8. ORA_ROWSCN không phải commit SCN chính xác cho mọi dòng

Oracle cung cấp pseudo-column ORA_ROWSCN để quan sát SCN liên quan đến thay đổi của dòng:

~~~sql
SELECT
    account_id,
    balance,
    ORA_ROWSCN
FROM lab_scn_account
ORDER BY account_id;
~~~

Tuy nhiên, cần hiểu giới hạn:

- Mặc định Oracle có thể theo dõi ở mức block, nên ORA_ROWSCN của các dòng trong cùng block có thể giống nhau dù không được cập nhật cùng transaction.
- Khi bảng được tạo với ROWDEPENDENCIES, Oracle theo dõi row dependency chi tiết hơn ở mức dòng, nhưng ORA_ROWSCN vẫn không nên được xem là một audit trail hoàn chỉnh hay bằng chứng thời gian commit chính xác tuyệt đối.
- ORA_ROWSCN không thay thế Flashback Version Query, redo mining hoặc bảng lịch sử nghiệp vụ.

Nếu cần theo dõi chính xác ai thay đổi dòng nào, lúc nào, từ giá trị nào sang giá trị nào, hãy thiết kế auditing phù hợp thay vì chỉ dựa vào ORA_ROWSCN.

## 9. SCN và checkpoint

Checkpoint giúp Oracle ghi nhận tiến độ đồng bộ các thay đổi trong buffer cache xuống datafile và xác định ranh giới cần xem xét trong instance recovery.

Một số SCN liên quan:

- CURRENT_SCN: mốc SCN hiện tại database báo.
- CHECKPOINT_CHANGE#: SCN checkpoint liên quan đến database/control file.
- START_SCN hoặc các SCN trong transaction/recovery view: thông tin phục vụ mục đích quản trị cụ thể.

Không đồng nhất checkpoint SCN với commit SCN. Checkpoint không phải thao tác COMMIT cho mọi transaction; nó là cơ chế quản lý việc ghi dữ liệu và phục hồi.

Có thể xem thông tin database:

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn,
    checkpoint_change#
FROM v$database;
~~~

Truy cập V$DATABASE thường cần quyền đọc dynamic performance views hoặc quyền tương ứng được cấp. Trong môi trường không có quyền quản trị, dùng DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER nếu package được phép sử dụng.

## 10. Instance recovery: phục hồi sau sự cố instance

Giả sử máy chủ bị mất điện hoặc instance bị crash. Một số dirty block có thể chưa được DBWR ghi xuống datafile, dù transaction đã COMMIT thành công.

Khi mở lại database, Oracle thực hiện instance recovery bằng redo và undo:

1. Xác định phạm vi cần phục hồi từ thông tin checkpoint và redo.
2. Roll forward bằng cách áp dụng redo để đưa block tiến lên trạng thái cần thiết.
3. Xử lý transaction chưa commit bằng undo để loại bỏ các thay đổi chưa được xác nhận.
4. Mở database khi quá trình recovery hoàn tất theo điều kiện hoạt động.

Mô hình:

~~~text
Sự cố instance
      |
      v
Đọc thông tin checkpoint / redo
      |
      v
ROLL FORWARD bằng REDO
      |
      v
Các thay đổi cần thiết được áp dụng
      |
      v
ROLL BACK transaction chưa COMMIT bằng UNDO
      |
      v
Database nhất quán để mở
~~~

Điểm quan trọng:

- Redo có thể chứa thay đổi của cả transaction đã commit và chưa commit.
- Trong recovery, Oracle có thể áp dụng redo trước, sau đó dùng undo để rollback transaction chưa commit.
- Transaction đã commit được giữ lại ngay cả khi data block của nó chưa được ghi xuống datafile trước sự cố.

Đó là lý do commit record, SCN, redo và undo liên quan chặt chẽ với nhau.

## 11. Media recovery và vai trò của archived redo log

Instance recovery xử lý sự cố instance khi các file cần thiết vẫn còn. Nếu datafile bị mất/hỏng, cần media recovery: khôi phục backup rồi áp dụng redo để đưa file/database đến trạng thái phù hợp.

Một quy trình khái niệm:

~~~text
Backup datafile
      |
      v
Restore backup về storage
      |
      v
Apply archived redo logs
      |
      v
Apply online redo nếu có và cần
      |
      v
Đạt SCN / thời điểm mục tiêu
      |
      v
Mở database theo chế độ recovery phù hợp
~~~

SCN giúp xác định database cần được phục hồi đến đâu. Backup cung cấp ảnh dữ liệu nền; redo chứa các thay đổi tiếp theo. SCN không chứa nội dung backup hay redo.

### 11.1. ARCHIVELOG và NOARCHIVELOG

- Database ở chế độ ARCHIVELOG có thể lưu các online redo log đã đầy thành archived redo log, hỗ trợ nhiều kịch bản media recovery và point-in-time recovery.
- Database ở chế độ NOARCHIVELOG có khả năng phục hồi sau sự cố hạn chế hơn; thường cần dựa vào backup nhất quán và có thể mất các thay đổi sau backup.

Kiểm tra:

~~~sql
SELECT log_mode
FROM v$database;
~~~

Chuyển chế độ ARCHIVELOG là thao tác quản trị database, thường cần mount trạng thái phù hợp và quyền DBA. Không thực hiện tùy tiện trên môi trường đang chạy; hãy theo quy trình backup/recovery của hệ thống.

## 12. Point-in-time recovery (PITR) theo SCN

Point-in-time recovery phục hồi database hoặc một phần phù hợp của database về một thời điểm trong quá khứ. Mốc có thể được chỉ định bằng SCN hoặc thời gian tùy phương pháp.

Ví dụ nghiệp vụ:

- Một batch xóa nhầm dữ liệu đã COMMIT.
- Một lần triển khai ghi sai nhiều bảng.
- Cần phục hồi database về trước một transaction gây hỏng dữ liệu.

Nếu chọn database PITR, DBA phải xác định target SCN, backup hợp lệ trước mốc đó và toàn bộ archived redo cần thiết để áp dụng đến target.

### 12.1. Ví dụ lệnh RMAN ở mức minh họa

Trong một môi trường phục hồi riêng, cấu trúc RMAN có thể như sau:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456;
  RESTORE DATABASE;
  RECOVER DATABASE;
}

SQL> ALTER DATABASE OPEN RESETLOGS;
~~~

123456 là SCN minh họa, không phải giá trị dùng thật. Cần xác định chính xác semantics của target SCN theo cú pháp RMAN và phiên bản đang dùng; mốc UNTIL SCN của RMAN có quy tắc biên riêng (thông thường là không bao gồm chính SCN được chỉ định). Hãy đối chiếu tài liệu RMAN của phiên bản triển khai trước khi chạy.

Đây là thao tác DBA có thể thay đổi trạng thái của toàn database. Mở RESETLOGS tạo incarnation mới cho nhánh database sau incomplete recovery; cần lập kế hoạch backup mới và xác nhận chiến lược tiếp tục phục hồi. Không chạy các lệnh mẫu trên production như một thử nghiệm.

### 12.2. Vì sao cần RESETLOGS?

Sau incomplete recovery hoặc một số quy trình phục hồi, database được mở bằng RESETLOGS để bắt đầu một nhánh redo mới. Những redo thuộc nhánh cũ sau điểm phục hồi không thể được áp dụng tiếp như thể lịch sử không bị phân nhánh.

RMAN quản lý database incarnation để phân biệt các nhánh. Sau RESETLOGS, nên thực hiện backup phù hợp để có điểm khôi phục mới trên incarnation hiện tại.

## 13. Flashback Query, Flashback Table và Flashback Database khác nhau

Oracle có nhiều tính năng Flashback. Chúng dùng SCN hoặc timestamp nhưng phạm vi và yêu cầu khác nhau.

| Tính năng | Phạm vi | Cơ chế chính | Mục đích |
|---|---|---|---|
| Flashback Query (AS OF SCN) | Truy vấn phiên bản cũ của dữ liệu | Undo | Đọc dữ liệu tại SCN quá khứ |
| Flashback Version Query | Lịch sử các phiên bản dòng trong khoảng SCN | Undo và thông tin phiên bản | Điều tra thay đổi |
| Flashback Table | Khôi phục một/vài bảng về mốc cũ | Undo | Sửa lỗi DML ở phạm vi bảng |
| Flashback Database | Đưa toàn database về mốc cũ | Flashback logs và cơ chế database | Phục hồi database về thời điểm trước |
| RMAN PITR | Database/tablespace/datafile tùy kịch bản | Backup và redo | Phục hồi vật lý đến target SCN/time |

### 13.1. Flashback Table

Flashback Table có thể đưa bảng về trạng thái tại SCN hoặc timestamp trước đó, trong giới hạn undo và điều kiện tính năng:

~~~sql
FLASHBACK TABLE lab_scn_account
TO SCN 123456;
~~~

Ví dụ trên cần thay SCN thật. Flashback Table thường yêu cầu bật row movement:

~~~sql
ALTER TABLE lab_scn_account ENABLE ROW MOVEMENT;
~~~

Row movement cho phép ROWID của dòng thay đổi khi Oracle khôi phục phiên bản bảng. Hãy kiểm tra quyền, constraint, trigger, phụ thuộc và giới hạn của Flashback Table trước khi dùng. Khi có quan hệ cha-con, cần lập kế hoạch cho toàn bộ các bảng liên quan để không vi phạm referential integrity.

Flashback Table là thao tác phục hồi dữ liệu bảng, không làm SCN toàn database quay ngược về quá khứ. Nó tạo các thay đổi mới trong database và SCN tiếp tục tiến về phía trước.

### 13.2. Flashback Database

Flashback Database đưa toàn bộ database về một SCN quá khứ bằng flashback logs, nếu tính năng đã được bật và còn đủ log. Đây là thao tác phạm vi database, khác với việc chỉ SELECT dữ liệu cũ.

Một số yêu cầu quản trị:

- Cấu hình ARCHIVELOG theo yêu cầu tính năng.
- Cấu hình Fast Recovery Area (FRA) và dung lượng phù hợp.
- Bật Flashback Database trước khi xảy ra sự cố.
- Có flashback logs bao phủ target SCN.
- Đánh giá ảnh hưởng đến các ứng dụng và database incarnation.

Flashback Database không thay thế backup. Flashback logs có phạm vi thời gian và dung lượng hữu hạn; backup vẫn cần cho mất/hỏng file hoặc phục hồi vượt quá cửa sổ flashback.

## 14. Khi nào dùng Flashback và khi nào dùng RMAN PITR?

Chọn phương pháp theo phạm vi lỗi và khả năng sẵn có:

| Tình huống | Hướng thường xem xét |
|---|---|
| Muốn xem dữ liệu trước một UPDATE/DELETE đã commit | Flashback Query AS OF SCN |
| Muốn điều tra các phiên bản của một dòng | Flashback Version Query |
| Muốn đưa một bảng về trước thao tác DML nhầm | Flashback Table nếu đủ điều kiện |
| Muốn đưa toàn database về trước sự cố | Flashback Database nếu đã bật và còn flashback logs |
| Datafile bị mất/hỏng | RMAN restore và media recovery |
| Cần phục hồi đến SCN dựa trên backup và archived redo | RMAN PITR |

Flashback Query là cách **đọc** dữ liệu cũ; nó không tự khôi phục dữ liệu hiện tại. Flashback Table/Database là thao tác khôi phục. RMAN PITR dựa trên backup và redo, có thể yêu cầu mở RESETLOGS tùy phạm vi và phương pháp.

## 15. COMMIT WRITE: WAIT, NOWAIT, IMMEDIATE và BATCH

Oracle có các tùy chọn điều khiển cách COMMIT chờ LGWR ghi redo:

~~~sql
COMMIT WRITE WAIT IMMEDIATE;
~~~

~~~sql
COMMIT WRITE WAIT BATCH;
~~~

~~~sql
COMMIT WRITE NOWAIT BATCH;
~~~

Ý nghĩa khái quát:

- WAIT: session chờ cho đến khi redo cần thiết được ghi theo cơ chế commit trước khi COMMIT trả về.
- NOWAIT: session có thể nhận xác nhận trước khi redo được ghi bền vững; nếu instance gặp sự cố trong khoảng đó, transaction vừa được báo thành công có thể chưa được bảo đảm theo mức durability thông thường.
- IMMEDIATE: yêu cầu LGWR thực hiện ghi redo ngay theo chế độ này.
- BATCH: cho phép gom các yêu cầu ghi commit để tăng hiệu quả ghi nhóm.

Không phải mọi ứng dụng đều cần tự chỉ định các tùy chọn này. Hành vi mặc định còn phụ thuộc cấu hình database/session và tham số commit liên quan; không nên giả định chỉ dựa vào một ví dụ cú pháp.

### 15.1. Vì sao NOWAIT có rủi ro?

Nếu dùng NOWAIT, client có thể nhận kết quả COMMIT trước khi redo commit được ghi bền vững. Nếu instance gặp sự cố đúng trong khoảng thời gian đó, transaction có thể bị mất dù ứng dụng đã nhận phản hồi thành công.

Vì thế, với nghiệp vụ cần durability rõ ràng như chuyển tiền, thanh toán, ghi nhận đơn hàng hoặc cập nhật số dư, không tùy tiện bật NOWAIT để giảm độ trễ. Chỉ cân nhắc khi ứng dụng chấp nhận rủi ro mất một số transaction gần thời điểm crash và đã đánh giá đầy đủ yêu cầu RPO.

### 15.2. COMMIT và Data Guard

Trong cấu hình Data Guard, yêu cầu durability có thể còn liên quan đến việc redo được vận chuyển và áp dụng ở standby. Các chế độ bảo vệ như Maximum Performance, Maximum Availability hoặc Maximum Protection có hành vi chờ/đảm bảo khác nhau.

COMMIT thành công ở primary không tự có nghĩa mọi standby đã apply redo. Cần phân biệt:

- Redo đã được tạo ở primary.
- Redo đã được ghi local vào online redo log.
- Redo đã được chuyển đến standby.
- Redo đã được ghi/áp dụng tại standby.

Độ trễ vận chuyển và apply, chế độ protection và cấu hình synchronous/asynchronous quyết định mức bảo vệ khi primary gặp sự cố. Đây là phần quản trị Data Guard, cần xem cấu hình thật thay vì suy ra từ SCN đơn lẻ.

## 16. SCN và các chế độ transaction

### 16.1. READ COMMITTED

Trong READ COMMITTED, mỗi câu SELECT có snapshot riêng tại thời điểm bắt đầu câu lệnh. Hai SELECT liên tiếp trong cùng transaction có thể nhìn thấy dữ liệu khác nhau nếu session khác commit ở giữa.

### 16.2. SERIALIZABLE

Trong SERIALIZABLE, transaction đọc theo snapshot nhất quán ở thời điểm bắt đầu transaction và Oracle kiểm soát xung đột ghi theo quy tắc của mức cô lập này. Một transaction có thể gặp lỗi serialization nếu thay đổi đồng thời gây xung đột.

### 16.3. SET TRANSACTION READ ONLY

Transaction READ ONLY cho phép nhiều truy vấn đọc cùng một snapshot nhất quán trong suốt transaction:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM lab_scn_account;
SELECT SUM(balance) FROM lab_scn_account;

COMMIT;
~~~

Hai câu SELECT trong transaction đọc cùng một snapshot, ngay cả khi session khác commit thay đổi trong lúc đó, theo cơ chế read consistency. Undo phải còn đủ để cung cấp phiên bản cần thiết.

Không dùng transaction READ ONLY để thực hiện DML; đây là chế độ chỉ đọc.

## 17. Ghi nhận SCN để phục hồi và điều tra

Nếu hệ thống có yêu cầu phục hồi đến một mốc nghiệp vụ, nên ghi lại các thông tin quan trọng:

- SCN tại thời điểm trước khi triển khai hoặc chạy batch quan trọng.
- Thời điểm bắt đầu/kết thúc theo đồng hồ ứng dụng.
- Transaction ID hoặc mã batch nghiệp vụ.
- Người/tiến trình thực hiện thay đổi.
- Backup và archived redo log bao phủ mốc đó.
- Database incarnation và trạng thái Data Guard nếu liên quan.

Ví dụ ghi SCN trước một batch:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS batch_start_scn
FROM dual;
~~~

Ứng dụng/DBA có thể lưu giá trị trả về vào deployment log hoặc bảng quản trị riêng. Nếu lưu trong bảng database, bản ghi log đó cũng phải được commit và có chính sách bảo vệ phù hợp; không để chính log bị xóa cùng batch đang cần điều tra.

Một mốc SCN đơn lẻ không bảo đảm có thể phục hồi. Phải có backup, redo/undo hoặc flashback logs phù hợp với phương pháp chọn.

## 18. SCN trong Data Dictionary và dynamic performance views

Một số view quản trị có thể giúp quan sát SCN:

~~~sql
SELECT
    current_scn,
    checkpoint_change#,
    resetlogs_change#,
    resetlogs_time,
    log_mode
FROM v$database;
~~~

Các cột:

- CURRENT_SCN: SCN hiện tại database báo.
- CHECKPOINT_CHANGE#: SCN liên quan checkpoint.
- RESETLOGS_CHANGE#: SCN gắn với lần RESETLOGS của incarnation hiện tại.
- RESETLOGS_TIME: thời điểm RESETLOGS được ghi nhận.
- LOG_MODE: chế độ ARCHIVELOG/NOARCHIVELOG.

Để xem các archived log và phạm vi SCN, DBA có thể dùng:

~~~sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    archived,
    applied
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

Trong RAC có thể có nhiều redo thread; không được giả định chỉ có một thread. FIRST_CHANGE# và NEXT_CHANGE# cho biết phạm vi SCN của archived log theo metadata. Các view này cần quyền đọc phù hợp.

Trong môi trường không có quyền DBA, chỉ dùng package/view mà tài khoản được cấp quyền. Không cấp quyền rộng chỉ để chạy một truy vấn quan sát SCN trong schema lab.

## 19. ORA_ROWSCN, Flashback và audit: chọn công cụ đúng

Các cách theo dõi thay đổi có mục tiêu khác nhau:

| Công cụ | Trả lời câu hỏi | Giới hạn chính |
|---|---|---|
| ORA_ROWSCN | Dòng/block có SCN liên quan nào? | Không phải lịch sử đầy đủ; có thể ở mức block |
| Flashback Query | Dữ liệu tại SCN cũ trông như thế nào? | Phụ thuộc undo và thời gian lưu |
| Flashback Version Query | Những phiên bản dòng nào còn truy vấn được trong khoảng SCN? | Không phải audit lưu vĩnh viễn |
| Unified Auditing / audit | Ai thực hiện hành động nào theo policy? | Phụ thuộc policy, cấu hình và retention |
| Bảng history do ứng dụng thiết kế | Giá trị cũ/mới và ngữ cảnh nghiệp vụ | Phải thiết kế, ghi và bảo vệ dữ liệu |
| LogMiner | Phân tích nội dung redo theo khả năng hỗ trợ | Cần quyền, archived/online redo và cấu hình phù hợp |

Nếu yêu cầu là “ai sửa số dư từ bao nhiêu thành bao nhiêu và vì lý do gì”, SCN một mình không trả lời đầy đủ. Hãy kết hợp transaction ID, audit, application log và dữ liệu lịch sử.

## 20. SCN, Flashback và giới hạn undo

Flashback Query/Version Query dựa vào thông tin phiên bản mà Oracle còn giữ. Các yếu tố ảnh hưởng:

- UNDO_RETENTION.
- Kích thước undo tablespace.
- Tốc độ phát sinh DML và mức độ cạnh tranh undo.
- Cấu hình RETENTION GUARANTEE nếu có.
- Độ dài truy vấn và lượng undo cần đọc.

Kiểm tra cấu hình:

~~~sql
SHOW PARAMETER undo_retention;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN ('undo_retention', 'undo_tablespace');
~~~

UNDO_RETENTION là thời gian mục tiêu tính bằng giây. Nếu không có retention guarantee, Oracle có thể ghi đè undo hết hạn hoặc cần tái sử dụng trong điều kiện thiếu chỗ. Retention guarantee có thể bảo vệ undo chưa hết thời gian mục tiêu nhưng làm DML thất bại nếu không còn không gian undo; cần quản trị dung lượng cẩn thận.

Không nên tăng undo_retention một cách máy móc mà không tính dung lượng, tốc độ DML và thời gian truy vấn Flashback dự kiến.

## 21. Phân biệt rollback, Flashback và recovery

Các cơ chế này đều có thể đưa dữ liệu về trạng thái cũ, nhưng hoạt động ở phạm vi và thời điểm khác nhau:

| Cơ chế | Khi dùng | Phạm vi | Cần transaction còn mở? |
|---|---|---|:---:|
| ROLLBACK | Hủy thay đổi chưa commit | Transaction hiện tại | Có |
| ROLLBACK TO SAVEPOINT | Hủy một phần thay đổi chưa commit | Phần sau savepoint | Có |
| Flashback Query | Đọc phiên bản cũ | SELECT | Không |
| Flashback Table | Khôi phục bảng về mốc cũ | Một/vài bảng | Không |
| Flashback Database | Đưa database về mốc cũ | Database | Không |
| RMAN PITR | Phục hồi từ backup và redo đến mốc | Database/tablespace/datafile theo phương pháp | Không |

Sau COMMIT, ROLLBACK thông thường không thể hủy transaction đó. Muốn khôi phục dữ liệu đã commit nhầm, hãy đánh giá Flashback, RMAN PITR hoặc quy trình bù trừ nghiệp vụ. Đừng nhầm ROLLBACK với Flashback: ROLLBACK xử lý transaction chưa commit; Flashback/recovery xử lý trạng thái đã được ghi nhận ở các mốc trước.

## 22. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| ORA-01555: snapshot too old | Undo cần cho consistent read/Flashback không còn | Điều chỉnh undo capacity/retention, giảm thời gian query, cân nhắc retention guarantee |
| ORA-08181: specified number is not a valid system change number | SCN không hợp lệ hoặc ngoài phạm vi ánh xạ timestamp/SCN | Kiểm tra nguồn SCN, database/incarnation và phạm vi ánh xạ |
| Flashback Query không trả phiên bản mong muốn | Undo không còn, DDL hoặc giới hạn đối tượng | Xác định SCN, retention và loại đối tượng |
| ORA-01466 khi Flashback | Cấu trúc bảng đã thay đổi trong khoảng cần flashback | Kiểm tra DDL và giới hạn Flashback Query |
| COMMIT đã trả về nhưng datafile chưa cập nhật | DBWR ghi block sau COMMIT; redo bảo vệ thay đổi | Đây là hành vi bình thường; kiểm tra redo/recovery, không yêu cầu DBWR flush mọi block |
| Mất transaction vừa báo thành công trong cấu hình đặc biệt | Có thể dùng COMMIT NOWAIT hoặc cấu hình durability khác | Kiểm tra COMMIT_WRITE/commit mode và yêu cầu durability |
| PITR không thể tới target SCN | Thiếu backup hoặc redo bao phủ khoảng cần thiết | Kiểm tra backup, archived log, incarnation và recovery catalog/control file |
| Chọn sai mốc phục hồi | Dùng timestamp gần đúng hoặc SCN không thuộc đúng incarnation | Ghi SCN theo sự kiện, kiểm tra RESETLOGS và target semantics |
| Dữ liệu standby chậm hơn primary | Redo transport/apply lag | Kiểm tra Data Guard transport/apply và protection mode |

## 23. Bài tập thực hành

### Bài 1 — Lấy SCN hiện tại

Viết truy vấn dùng DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER và truy vấn dùng V$DATABASE.CURRENT_SCN.

**Câu hỏi:** Hai giá trị này cho biết điều gì? Có thể khẳng định chúng là commit SCN của một transaction vừa chạy không?

**Đáp án định hướng:** đây là thông tin SCN hiện tại của database; không tự động xác định commit SCN của một transaction cụ thể.

### Bài 2 — Quan sát READ COMMITTED

Mở hai session. Session A UPDATE một tài khoản nhưng chưa COMMIT; session B SELECT cùng dòng; sau đó A COMMIT và B SELECT lại.

**Câu hỏi:** Vì sao session B đọc giá trị cũ trước COMMIT và giá trị mới ở câu SELECT sau COMMIT?

**Đáp án định hướng:** statement-level read consistency và undo cung cấp snapshot đã commit tại thời điểm mỗi câu SELECT bắt đầu.

### Bài 3 — Flashback Query

Ghi SCN trước khi UPDATE số dư, UPDATE rồi COMMIT, sau đó dùng AS OF SCN để đọc lại.

**Câu hỏi:** Nếu undo cần thiết đã bị ghi đè, điều gì có thể xảy ra?

**Đáp án:** Flashback Query có thể thất bại, thường gặp ORA-01555 tùy trường hợp.

### Bài 4 — So sánh Flashback Version Query

Dùng VERSIONS BETWEEN SCN ... AND ... để xem các phiên bản của một tài khoản sau hai lần UPDATE và COMMIT.

**Yêu cầu:** hiển thị VERSIONS_STARTSCN, VERSIONS_ENDSCN, VERSIONS_OPERATION và số dư.

### Bài 5 — Timestamp và SCN

Chạy SCN_TO_TIMESTAMP và TIMESTAMP_TO_SCN với các giá trị trong phạm vi database còn ánh xạ.

**Câu hỏi:** Vì sao không dùng kết quả ánh xạ như một timestamp commit chính xác tuyệt đối?

**Đáp án định hướng:** đây là ánh xạ gần đúng và có phạm vi lưu lịch sử giới hạn.

### Bài 6 — COMMIT và DBWR

Giải thích vì sao transaction đã COMMIT vẫn có thể có dirty block chưa được DBWR ghi xuống datafile.

**Đáp án định hướng:** COMMIT thông thường chờ redo cần thiết được ghi; DBWR ghi data block theo cơ chế checkpoint/background sau đó.

### Bài 7 — Chọn phương pháp phục hồi

Với từng tình huống, chọn Flashback Query, Flashback Table, Flashback Database hoặc RMAN PITR:

1. Chỉ cần xem số dư trước UPDATE.
2. Muốn khôi phục một bảng sau DELETE nhầm.
3. Muốn đưa toàn database về trước batch lỗi.
4. Datafile bị hỏng và cần restore từ backup.

**Định hướng:** lần lượt là Flashback Query; Flashback Table nếu đủ điều kiện; Flashback Database hoặc RMAN PITR theo cấu hình; RMAN restore/recovery.

### Bài 8 — Commit durability

Giải thích khác biệt giữa COMMIT WRITE WAIT và NOWAIT, và vì sao giao dịch tài chính thường cần cân nhắc kỹ trước khi dùng NOWAIT.

### Bài 9 — SCN và audit

Một điều tra viên cần biết ai đổi số dư, từ giá trị nào sang giá trị nào và lý do. Hãy giải thích vì sao ORA_ROWSCN một mình không đủ.

**Định hướng:** ORA_ROWSCN không phải audit log; cần audit/history, transaction ID và application context.

## 24. Quy trình chọn SCN và phương pháp phục hồi

Khi có sự cố dữ liệu, hãy xác định mục tiêu trước khi chọn lệnh:

1. **Sự cố đã COMMIT chưa?** Nếu transaction còn mở, ROLLBACK hoặc ROLLBACK TO có thể đủ.
2. **Chỉ cần đọc dữ liệu cũ hay khôi phục dữ liệu hiện tại?** Đọc thì Flashback Query; khôi phục bảng/database cần tính năng tương ứng.
3. **Phạm vi ảnh hưởng là gì?** Một dòng, một bảng, nhiều bảng hay toàn database?
4. **SCN mục tiêu lấy từ đâu?** Deployment log, batch log, audit, transaction investigation hay mốc do DBA ghi nhận?
5. **Undo/flashback logs còn không?** Kiểm tra retention và dung lượng.
6. **Có backup và archived redo phù hợp không?** Cần thiết cho media recovery/PITR.
7. **Có Data Guard hoặc nhiều incarnation không?** Kiểm tra redo transport/apply, RESETLOGS và nhánh database.
8. **Có thể kiểm tra kết quả trong môi trường cô lập không?** Xác nhận trước khi đưa database trở lại phục vụ.

Sơ đồ chọn hướng:

~~~text
Phát hiện thay đổi sai
          |
          v
Transaction đã COMMIT?
       /          \
     Chưa          Rồi
      |              |
      v              v
ROLLBACK /       Chọn phạm vi cần xử lý
ROLLBACK TO           |
      |          +----+------------------+
      |          |           |          |
      |          v           v          v
      |       Chỉ đọc     Một/vài bảng  Toàn database
      |          |           |          |
      |          v           v          v
      |    Flashback     Flashback    Flashback DB
      |      Query        Table       hoặc RMAN PITR
      |          |           |          |
      +----------+-----------+----------+
                         |
                         v
              Kiểm tra SCN, undo,
              backup và redo cần thiết
                         |
                         v
                 Xác nhận kết quả
~~~

SCN cung cấp mốc logic để Oracle xác định phiên bản dữ liệu và vị trí phục hồi. COMMIT ghi nhận transaction đã hoàn tất và tạo ranh giới mà các session, redo và recovery có thể sử dụng. Redo bảo vệ khả năng tái áp dụng thay đổi đã commit; undo hỗ trợ rollback và consistent read; Flashback và RMAN dùng các mốc SCN cùng thông tin lưu trữ phù hợp để đọc hoặc phục hồi trạng thái cũ. Khi phân biệt rõ các vai trò đó, ta sẽ chọn đúng phương pháp cho từng sự cố và không nhầm một con số SCN với bản thân dữ liệu phục hồi.
