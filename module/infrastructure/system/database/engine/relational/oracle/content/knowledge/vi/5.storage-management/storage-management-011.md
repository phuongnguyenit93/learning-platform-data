# Undo segment, undo retention và nhu cầu đọc nhất quán

## 1. Bài toán: tại sao đang sửa dữ liệu mà người khác vẫn đọc được?

Giả sử hệ thống ngân hàng có tài khoản `A001` với số dư đã được xác nhận là **1.000.000 đồng**. Một giao dịch bắt đầu cập nhật số dư thành 800.000 đồng nhưng **chưa `COMMIT`**. Cùng lúc, một giao dịch khác cần hiển thị số dư cho khách hàng.

Oracle Database phải giải quyết nhiều yêu cầu đồng thời:

- Không cho người đọc nhìn thấy số dư **chưa được xác nhận**.
- Cho phép truy vấn đọc thông thường tiếp tục làm việc mà không phải chờ mỗi lần một phiên khác đang cập nhật hàng.
- Khi giao dịch cập nhật gặp lỗi hoặc người dùng `ROLLBACK`, có thể **khôi phục trạng thái trước thay đổi**.
- Khi một câu `SELECT` quét nhiều hàng trong thời gian dài, các hàng trả về phải phản ánh **một góc nhìn dữ liệu nhất quán**, kể cả khi các phiên khác vẫn đang cập nhật.

Đó là lý do Oracle sử dụng **undo**. Undo không đơn giản là “bản sao của cả bảng trước khi sửa”; đó là thông tin về những thay đổi cần thiết để **hoàn tác thao tác** hoặc **tái tạo phiên bản dữ liệu cũ** khi cần.

Trong chương **Lưu trữ** của Oracle, ba khái niệm cần hiểu cùng nhau là:

1. **Undo segment**: cấu trúc lưu trữ chứa các undo record, tổ chức trong undo tablespace.
2. **Undo retention**: thời gian mục tiêu Oracle cố giữ undo đã hết cần cho rollback để phục vụ việc đọc phiên bản cũ và một số chức năng khác.
3. **Read consistency (đọc nhất quán)**: cách Oracle dùng thông tin giao dịch và undo để một truy vấn thấy dữ liệu ở thời điểm phù hợp, tránh đọc thay đổi chưa commit.

Sau bài này, bạn cần giải thích được điều gì xảy ra khi `UPDATE`, `SELECT`, `COMMIT`, `ROLLBACK` diễn ra đồng thời; nhận biết vì sao truy vấn lâu có thể gặp `ORA-01555`; và biết cách xem những thông số/đối tượng liên quan đến undo.

## 2. Undo là gì và được tạo ra trong tình huống nào?

**Undo data** là dữ liệu phục vụ việc đảo ngược thay đổi do giao dịch thực hiện. Khi cập nhật hoặc xóa hàng, Oracle lưu thông tin cần thiết để khôi phục trạng thái trước thao tác. Với thao tác chèn hàng, thông tin undo giúp Oracle hoàn tác việc thêm hàng nếu giao dịch bị rollback.

Ví dụ:

```sql
UPDATE accounts
SET balance = 800000
WHERE account_id = 'A001';
```

Giả sử hàng có `balance = 1000000` trước câu lệnh. Oracle tạo thông tin undo liên quan thay đổi để khi cần có thể đưa trạng thái logic về giá trị trước. Đây là cách diễn giải đơn giản cho người học: định dạng thực của undo record phụ thuộc thao tác và cấu trúc block, **không nhất thiết là bản sao nguyên vẹn của toàn bộ hàng hoặc bảng**.

### 2.1. Những thao tác nào liên quan đến undo?

| Thao tác | Quan hệ với undo |
|---|---|
| `INSERT` | Cần thông tin để có thể hoàn tác hàng vừa chèn khi transaction rollback |
| `UPDATE` | Cần thông tin đủ để đảo ngược thay đổi đã thực hiện |
| `DELETE` | Cần thông tin đủ để khôi phục dữ liệu đã xóa nếu rollback |
| `ROLLBACK` | Sử dụng thông tin undo để hoàn tác thay đổi chưa commit |
| `SELECT` thông thường | **Sử dụng undo khi cần tái tạo phiên bản cũ**; truy vấn đọc không tạo undo cho các hàng được đọc theo cách DML tạo undo |
| `COMMIT` | Xác nhận giao dịch; undo đã tạo **không nhất thiết biến mất ngay** |
| Flashback Query | Có thể sử dụng phiên bản dữ liệu cũ dựa trên undo còn khả dụng |

Ví dụ trong một giao dịch:

```sql
SAVEPOINT before_change;

UPDATE accounts
SET balance = balance - 200000
WHERE account_id = 'A001';

ROLLBACK TO SAVEPOINT before_change;
```

`ROLLBACK TO SAVEPOINT` có thể hoàn tác những thay đổi sau savepoint trong phạm vi transaction đang chạy. `ROLLBACK` toàn phần hoàn tác những thay đổi chưa commit trong transaction. **Sau khi `COMMIT` thành công, không thể dùng `ROLLBACK` để đảo ngược commit đó**; cần một giao dịch bù trừ hoặc phương án khôi phục thích hợp.

### 2.2. Undo không phải redo

Oracle dùng cả **undo** và **redo**, nhưng hai cơ chế phục vụ mục đích khác nhau:

| Thành phần | Vai trò điển hình | Ví dụ cần dùng |
|---|---|---|
| **Undo** | Đảo ngược thay đổi của transaction; tái dựng phiên bản cũ cho consistent read | `ROLLBACK`, đọc dữ liệu khi phiên khác đang sửa |
| **Redo** | Ghi thông tin thay đổi cần thiết để phục hồi database sau sự cố | Phục hồi các thay đổi đã commit theo cơ chế recovery |
| **Backup** | Bản sao phục vụ quy trình restore/recovery | Khôi phục khi mất file hoặc hỏng môi trường |

Đừng suy luận rằng “có undo là không cần redo/backup”, hoặc “redo là bảng lịch sử cho phép ứng dụng tự tra giá trị cũ”. Đây là các thành phần riêng biệt nhưng phối hợp trong cơ chế giao dịch và phục hồi Oracle.

## 3. Undo được lưu ở đâu? Undo tablespace và undo segment

Trong môi trường thông dụng sử dụng **Automatic Undo Management (AUM)**, Oracle tự quản lý các **undo segment** bên trong một **undo tablespace** được cấu hình cho instance/container phù hợp.

Quan hệ lưu trữ cơ bản:

```text
                  ORACLE DATABASE
                         |
                  UNDO TABLESPACE
                    UNDOTBS1
                         |
           +-------------+--------------+
           |                            |
       DATAFILE 1                   DATAFILE 2
           |                            |
       [data blocks]                [data blocks]
           ^                            ^
           |                            |
       Extent A                     Extent B
           \                            /
            \                          /
              UNDO SEGMENT (ví dụ)
                   |
                Undo records
                   |
          Thông tin thay đổi phục vụ
          rollback và consistent read
```

Cũng như những segment khác, **undo segment** gồm các **extent**, mỗi extent gồm các Oracle data block nằm trong **một datafile**. Một undo segment có thể có nhiều extent, và việc tổ chức/cấp phát thực tế do Oracle quản lý. Các transaction có thể sử dụng undo segment được hệ quản trị phân công; không nên hình dung mỗi câu `UPDATE` tự tạo một datafile hoặc một undo segment riêng.

### 3.1. Các lớp lưu trữ cần phân biệt

| Lớp | Ý nghĩa với undo |
|---|---|
| Undo tablespace | Không gian logic được dành để chứa các undo segment |
| Datafile của undo tablespace | File lưu trữ thực tế chứa các block thuộc undo segment |
| Undo segment | Cấu trúc Oracle quản lý undo records của các transaction |
| Undo extent | Nhóm block được cấp phát cho undo segment |
| Undo block | Block bên trong extent chứa dữ liệu/cấu trúc undo |
| Undo record | Thông tin hỗ trợ hoàn tác hoặc tái dựng phiên bản cũ của dữ liệu |

Ví dụ một datafile của undo tablespace có thể được cấu hình trên filesystem như:

```text
/u02/oradata/LABDB/undotbs01.dbf
```

Ở môi trường **ASM**, đường dẫn có thể có dạng `+DATA/...` thay vì đường dẫn Linux. Một undo tablespace có thể sử dụng nhiều datafile tùy loại tablespace và cấu hình. **Không đọc hoặc sửa undo block trực tiếp bằng trình soạn thảo file**: toàn bộ dữ liệu này do Oracle quản lý.

### 3.2. AUM và các tham số cần nhận diện

| Tham số | Ý nghĩa |
|---|---|
| `UNDO_MANAGEMENT` | Chế độ quản lý undo; `AUTO` là Automatic Undo Management |
| `UNDO_TABLESPACE` | Undo tablespace được chọn trong ngữ cảnh instance/container thích hợp |
| `UNDO_RETENTION` | Mức thời gian mục tiêu (giây) giữ undo đã commit theo các quy tắc về dung lượng và retention |

Ví dụ cấu hình **minh họa**:

```text
undo_management = AUTO
undo_tablespace = UNDOTBS1
undo_retention  = 900
```

Số `900` tương ứng **900 giây = 15 phút**. Điều đó **không có nghĩa Oracle chắc chắn trả lại được mọi phiên bản dữ liệu trong đúng 15 phút**; cần xét **khả năng giữ undo thực tế**, chính sách retention và các điều kiện của truy vấn.

Trong kiến trúc multitenant (CDB/PDB), việc dùng **local undo** hoặc **shared undo** tùy phiên bản/cấu hình có thể khiến vị trí và phạm vi undo tablespace khác nhau. Khi truy vấn view quản trị, phải xác định mình đang kết nối đến **CDB root hay PDB** nào và có quyền quan sát đối tượng nào.

## 4. Undo hỗ trợ tính nguyên tử của transaction như thế nào?

Xem một transaction chuyển tiền gồm hai bước:

```text
BEGIN transaction (về mặt ý niệm)
    |
    +--> UPDATE tài khoản gửi: trừ 200.000
    |
    +--> UPDATE tài khoản nhận: cộng 200.000
    |
    +-- Nếu một bước thất bại: ROLLBACK
    |
    +-- Nếu cả hai thành công: COMMIT
```

Oracle ghi nhận các thay đổi và thông tin undo đủ để khi rollback có thể đưa các hàng bị ảnh hưởng về trạng thái phù hợp trước transaction. Khi `COMMIT`, kết quả giao dịch được xác nhận; Oracle **không lập tức xóa sạch undo liên quan**, vì những truy vấn đã bắt đầu trước thời điểm commit có thể còn cần đọc phiên bản cũ.

Một transaction **chưa kết thúc** giữ những undo cần cho khả năng rollback. Những undo đó được xem là **active undo**, không thể tùy tiện ghi đè để nhường chỗ cho transaction khác. Điều này khác với undo của transaction đã kết thúc.

**Tính nguyên tử** của các cập nhật trong **cùng một Oracle transaction** không tự bao trùm hệ thống ngoài database, ví dụ HTTP request đến cổng thanh toán. Nếu ứng dụng có cả cập nhật Oracle lẫn gọi dịch vụ bên ngoài, cần thiết kế phối hợp như idempotency/outbox/saga khi phù hợp.

## 5. Read consistency: đọc phiên bản nào và tại thời điểm nào?

### 5.1. Bài toán dirty read

Giả sử có hai phiên kết nối:

```text
                  Session A                       Session B
-----------------------------------------------------------------
t0          balance = 1.000.000
t1          UPDATE balance = 800.000
            (CHƯA COMMIT)
t2                                          SELECT balance?
t3          COMMIT hoặc ROLLBACK
```

Nếu Session B đọc `800.000` ngay khi A chưa commit, B có thể nhìn thấy một giá trị **chưa chắc tồn tại lâu dài**: A có thể rollback về `1.000.000`. Đó là dirty read.

Oracle sử dụng cơ chế **multiversion read consistency** để `SELECT` thông thường có thể nhận **phiên bản đã commit phù hợp với thời điểm đọc**. Trong trường hợp này, B thường thấy `1.000.000` tại t2 mà không cần chờ A commit.

### 5.2. SCN và consistent read

Oracle dùng **System Change Number (SCN)** như một mốc logic để quản lý thứ tự và tính nhất quán của thay đổi. Trong mức cô lập `READ COMMITTED`, mỗi câu SQL truy vấn được đánh giá theo một **góc nhìn dữ liệu nhất quán ở cấp câu lệnh**.

Mô hình giản lược:

1. Câu `SELECT` bắt đầu và có **snapshot SCN** phù hợp.
2. Oracle cần đọc một block có thay đổi mới hơn snapshot đó, hoặc chứa dữ liệu đang bị transaction khác sửa.
3. Khi cần, Oracle sử dụng thông tin undo để tái dựng một **consistent read (CR) version** của block, tương ứng với góc nhìn mà câu truy vấn được phép thấy.
4. Truy vấn trả về dữ liệu từ phiên bản nhất quán thay vì lấy bừa giá trị mới nhất đang nằm trong block.

```text
Block hiện tại
  ROW A balance=800.000 (chưa commit ở A)
           |
           | cần phiên bản phù hợp với snapshot của B
           v
     Undo information
           |
           v
CR copy của block: ROW A balance=1.000.000
           |
           v
Session B nhận giá trị 1.000.000
```

Oracle tái dựng **phiên bản block/hàng hợp lý cho yêu cầu đọc** từ các thông tin thay đổi và trạng thái giao dịch; sơ đồ chỉ minh họa ý tưởng, không mô tả mọi trường hợp triển khai nội bộ của buffer cache.

### 5.3. Một câu `SELECT` dài vẫn nhìn dữ liệu nhất quán

Giả sử một câu báo cáo bắt đầu lúc 10:00, đọc hàng triệu bản ghi trong 8 phút. Trong 8 phút đó, nhiều transaction khác có thể cập nhật và commit dữ liệu.

Ở mức `READ COMMITTED`, các hàng trong **cùng câu SELECT** cần phản ánh trạng thái phù hợp với **snapshot của câu lệnh đó**, không phải mỗi hàng được đọc tại một thời điểm có thể tùy tiện thay đổi. Nếu một block đã bị cập nhật sau snapshot, Oracle dùng undo còn khả dụng để tạo phiên bản tương ứng.

Điều này rất quan trọng với báo cáo: nếu tổng tiền ở bảng đơn hàng lấy dữ liệu trước commit còn chi tiết ở một phần khác lấy dữ liệu sau commit trong **cùng statement**, kết quả có thể tự mâu thuẫn. Statement-level consistency giúp tránh hiện tượng đó trong phạm vi bảo đảm của Oracle.

### 5.4. Statement-level và transaction-level consistency

Oracle hỗ trợ nhiều mức cô lập giao dịch:

| Mức/mode | Góc nhìn đọc thông dụng | Điều cần nhớ |
|---|---|---|
| `READ COMMITTED` | Mỗi câu lệnh có snapshot riêng (mặc định phổ biến của Oracle) | Hai `SELECT` liên tiếp trong một transaction có thể cho kết quả khác nếu phiên khác commit giữa chúng |
| `SERIALIZABLE` | Các truy vấn trong transaction hướng tới snapshot nhất quán ở cấp transaction | Khi có xung đột cập nhật không thể tuần tự hóa theo cơ chế Oracle, có thể gặp `ORA-08177` |
| `READ ONLY` transaction | Các truy vấn thấy snapshot nhất quán của transaction | Transaction này không được dùng để thay đổi dữ liệu theo cách thông thường |

Ví dụ cách bắt đầu một transaction chỉ đọc trong SQL*Plus:

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM user_tables;
SELECT COUNT(*) FROM user_objects;

COMMIT;
```

`SET TRANSACTION` cần được dùng đúng thời điểm bắt đầu transaction theo quy tắc Oracle. `READ ONLY` hữu ích khi nhiều câu truy vấn cần góc nhìn nhất quán hơn, nhưng với transaction kéo dài, nhu cầu giữ undo cũng có thể tăng.

**Đừng nhầm snapshot consistency với khóa:** `SELECT` thông thường theo Oracle không đặt khóa hàng như `SELECT ... FOR UPDATE`. `SELECT ... FOR UPDATE` là yêu cầu khóa chủ động và có thể phải chờ khi hàng đang bị transaction khác giữ khóa. Hai câu SQL đó có mục tiêu khác nhau.

## 6. Ví dụ thực hành với hai phiên SQL*Plus/SQLcl

Ví dụ sử dụng **hai phiên đăng nhập vào cùng schema thực hành**. Bạn cần được phép tạo bảng và thao tác dữ liệu trong schema đó. Không sử dụng các bảng nghiệp vụ thật. Trong SQL*Plus, thiết lập `SET AUTOCOMMIT OFF` để đảm bảo bước cập nhật không tự commit; một số công cụ GUI/driver quản lý autocommit theo cách riêng.

### Bước 1. Tạo dữ liệu mẫu trong Session A

```sql
SET AUTOCOMMIT OFF

CREATE TABLE undo_lab_accounts (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL
);

INSERT INTO undo_lab_accounts (account_id, balance)
VALUES (1, 1000);

COMMIT;
```

`CREATE TABLE` là DDL và có hành vi commit ngầm theo quy tắc Oracle. Sau `COMMIT`, hàng `account_id = 1` có `balance = 1000` đã được xác nhận.

### Bước 2. Session A cập nhật nhưng chưa commit

```sql
UPDATE undo_lab_accounts
SET balance = 800
WHERE account_id = 1;

-- Chưa COMMIT và chưa ROLLBACK.
```

Trong Session A, nếu truy vấn lại hàng này, phiên A có thể nhìn thấy **thay đổi do chính mình thực hiện**:

```sql
SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Kết quả mong đợi của Session A là `800`.

### Bước 3. Session B đọc khi A chưa commit

Mở terminal/worksheet thứ hai, kết nối cùng database và schema:

```sql
SET AUTOCOMMIT OFF

SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Kết quả mong đợi của **Session B** là `1000`. B không thấy `800` vì đó là thay đổi chưa commit ở A. Đọc thông thường có thể sử dụng phiên bản nhất quán dựa trên undo thay vì chờ A.

### Bước 4. Session A rollback

Trở lại A:

```sql
ROLLBACK;

SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Kết quả mong đợi là `1000`. Chạy lại `SELECT` ở B cũng thấy `1000`.

### Bước 5. Thử commit rồi đọc lại ở B

Tại A:

```sql
UPDATE undo_lab_accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
```

Tại B, khi thực thi **một câu `SELECT` mới** ở chế độ `READ COMMITTED`:

```sql
SELECT balance
FROM undo_lab_accounts
WHERE account_id = 1;
```

Kết quả mong đợi là `900`. Lần này B nhìn thấy giá trị đã commit, vì snapshot của câu truy vấn mới được xác định ở thời điểm sau commit.

### Bước 6. Dọn dữ liệu thực hành

Chỉ làm khi đã xác nhận tên bảng do chính bạn tạo trong schema thực hành và các phiên không còn dùng bảng:

```sql
DROP TABLE undo_lab_accounts PURGE;
```

`DROP TABLE ... PURGE` xóa đối tượng, không đưa vào recycle bin theo quy tắc tương ứng; đây là thao tác phá hủy và DDL có commit ngầm. Không chạy nếu bảng chứa dữ liệu cần giữ.

### Điều bài thực hành cho thấy

```text
TIME    SESSION A                         SESSION B
----    ------------------------------    -----------------------
t0      COMMIT balance=1000
t1      UPDATE balance=800
        (uncommitted)
t2                                        SELECT -> 1000
t3      ROLLBACK
t4                                        SELECT -> 1000
t5      UPDATE balance=900; COMMIT
t6                                        SELECT -> 900
```

Trong thực tế, không nhất thiết nhìn thấy Oracle đang đọc undo trực tiếp ở mỗi `SELECT`; behavior quan sát được là **cô lập dữ liệu chưa commit** và **góc nhìn câu lệnh sau commit**.

## 7. Undo sau commit: ACTIVE, UNEXPIRED, EXPIRED

Undo của transaction đang chạy cần tồn tại để rollback và duy trì tính nhất quán. Sau khi transaction commit, undo vẫn có thể cần cho truy vấn bắt đầu trước commit hoặc cho tính năng đọc dữ liệu ở quá khứ.

Các trạng thái extent undo thường có thể quan sát qua `DBA_UNDO_EXTENTS`:

| Trạng thái | Ý nghĩa khái quát | Khả năng tái sử dụng |
|---|---|---|
| **`ACTIVE`** | Chứa undo cần cho transaction đang hoạt động | Không được ghi đè tùy tiện, vì cần cho rollback |
| **`UNEXPIRED`** | Chứa undo đã commit nhưng còn trong thời hạn retention được quản lý | Oracle cố giữ; có thể được tái sử dụng khi thiếu chỗ nếu không bật retention guarantee |
| **`EXPIRED`** | Undo không còn nằm trong khoảng giữ theo chính sách hiện tại | Có thể được tái sử dụng để ghi undo mới |

Sơ đồ vòng đời giản lược:

```text
Transaction đang UPDATE/DELETE
              |
              v
       Undo extent ACTIVE
              |
          COMMIT / kết thúc
              |
              v
      Undo extent UNEXPIRED
         (còn được giữ)
              |
       hết khoảng retention
              |
              v
       Undo extent EXPIRED
              |
              v
  Có thể tái sử dụng cho undo mới
```

Các trạng thái là cách nhìn cấp **extent** trong dictionary; vòng đời thực tế còn phụ thuộc undo record, transaction, mức độ sử dụng và cơ chế cấp phát/tái sử dụng. Đừng hiểu rằng một lần commit làm toàn bộ undo tablespace lập tức chuyển thành `EXPIRED`.

## 8. `UNDO_RETENTION`: mục tiêu giữ undo, không phải đồng hồ xóa dữ liệu

Tham số `UNDO_RETENTION` được biểu diễn bằng **giây**. Ví dụ:

```text
UNDO_RETENTION = 900  --> 15 phút
```

Ý nghĩa: đây là một **mục tiêu thời gian** giữ undo của các transaction đã commit, nhằm hỗ trợ truy vấn dài và tính năng cần dữ liệu phiên bản cũ. Tuy nhiên, thời gian thực sự giữ được phụ thuộc dung lượng undo tablespace, cấu hình `AUTOEXTEND`, khối lượng DML, cách Oracle điều chỉnh retention và chế độ **retention guarantee**.

### 8.1. Tại sao `UNDO_RETENTION = 900` chưa phải bảo đảm 15 phút?

Giả sử:

1. Một câu báo cáo chạy 12 phút.
2. Các transaction khác đang ghi dữ liệu rất mạnh, tạo nhiều undo.
3. Undo tablespace có dung lượng nhỏ và không còn khả năng mở rộng.
4. Các extent chứa undo cần cho truy vấn đã commit và được xem là có thể tái sử dụng theo chính sách không guarantee.

Nếu undo cũ cần cho consistent read bị ghi đè trước khi truy vấn dùng đến, câu báo cáo có thể thất bại với lỗi **`ORA-01555: snapshot too old`**, dù bạn nhìn thấy `UNDO_RETENTION` đặt bằng 900 giây.

**Thời gian retention được cấu hình không thay thế cho việc cấp đủ dung lượng undo.** Một transaction đang chạy, một truy vấn dài và một lượng lớn DML đồng thời đều góp phần quyết định nhu cầu thực tế.

### 8.2. Undo retention tuning

Trong chế độ Automatic Undo Management, Oracle có thể **điều chỉnh thời gian giữ undo theo tình hình sử dụng và tài nguyên sẵn có**. View `V$UNDOSTAT` cung cấp thống kê theo khoảng thời gian, trong đó có `TUNED_UNDORETENTION` trên các phiên bản hỗ trợ trường này.

Cần phân biệt:

- **`UNDO_RETENTION`**: tham số người quản trị cấu hình, thường đóng vai trò mục tiêu/tối thiểu mong muốn theo cơ chế đang áp dụng.
- **`TUNED_UNDORETENTION`**: thời gian retention Oracle đã điều chỉnh/ghi nhận trong khoảng thống kê, không phải một lời hứa mọi câu Flashback Query đều có dữ liệu theo khoảng thời gian đó.
- **Khả năng truy vấn phục hồi thực tế**: phụ thuộc undo record cần dùng còn tồn tại hay không, schema có thay đổi hay không, quyền và các điều kiện khác.

Đọc con số `TUNED_UNDORETENTION` cao trong một thời điểm không có nghĩa có thể mặc định giữ toàn bộ lịch sử để truy vấn ở mọi thời điểm trong tương lai.

### 8.3. Retention guarantee và đánh đổi

Undo tablespace có thể được cấu hình **`RETENTION GUARANTEE`**:

- Khi bật **guarantee**, Oracle bảo vệ undo **chưa hết thời hạn retention** khỏi bị ghi đè chỉ để lấy chỗ cho DML mới.
- Nếu dung lượng không đủ, **giao dịch DML mới có thể thất bại** vì không thể cấp thêm undo.
- Khi không bật guarantee, Oracle có thể tái sử dụng **unexpired undo** trong tình huống thiếu không gian, khiến truy vấn dùng phiên bản cũ có nguy cơ `ORA-01555`.

Ví dụ cú pháp quản trị, **không chạy tùy tiện trong môi trường đang sử dụng**:

```sql
-- Chi minh hoa cau lenh DBA, phai can nhac rui ro het undo space.
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;

-- Tra ve che do thong thuong khi phu hop:
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
```

Đây là thay đổi cấu hình tác động đến khả năng ghi dữ liệu của database. `RETENTION GUARANTEE` có thể giúp giữ dữ liệu cũ theo chính sách, nhưng **không tạo thêm dung lượng lưu trữ** và không bảo đảm truy cập dữ liệu ngoài khoảng retention hoặc sau những thay đổi cấu trúc không tương thích.

### 8.4. Kích thước undo cần cân đối thế nào?

Không có một mức dung lượng phù hợp cho mọi ứng dụng. Các yếu tố chính là:

- Tốc độ và kiểu DML: cập nhật hàng rộng, xóa hàng, bulk load, batch job.
- Số transaction đồng thời và thời gian mở transaction.
- Thời gian câu `SELECT` hoặc báo cáo phải duy trì snapshot.
- Tính năng Flashback cần giữ phiên bản quá khứ trong bao lâu.
- Khả năng autoextend, giới hạn datafile và tài nguyên filesystem/ASM.
- Thống kê từ `V$UNDOSTAT`, cảnh báo `ORA-01555` và các lần không thể cấp thêm undo.

Ước lượng sơ bộ theo lưu lượng:

```text
Dung lượng undo cần giữ (ước tính)
  ≈ tốc độ sinh undo trong giai đoạn tải cao
    × thời gian cần giữ phiên bản cũ
    + phần dự phòng cho biến động và transaction đang chạy
```

Ví dụ, nếu khối lượng công việc sinh trung bình khoảng **1 MB undo mỗi giây** trong một giai đoạn tải cao và muốn giữ khoảng **15 phút**, phần undo tương ứng đã vào khoảng **900 MB** trước khi cộng dự phòng và xét giới hạn thực tế. Đây chỉ là **minh họa cách suy nghĩ**; đo từ workload thật và sử dụng các công cụ tư vấn/giám sát Oracle mới cho kết quả hữu ích để lập kế hoạch dung lượng.

## 9. `ORA-01555: snapshot too old` và nhu cầu read consistency

**`ORA-01555`** thường xuất hiện khi Oracle cần tái tạo phiên bản cũ cho một truy vấn nhưng thông tin undo liên quan **không còn khả dụng**. Tình huống điển hình là một câu `SELECT` kéo dài trong khi hệ thống có nhiều DML và undo phải tái sử dụng.

### 9.1. Dòng thời gian minh họa

```text
Time
 |
 t0  Query Q bắt đầu -> snapshot SCN = S
 |
 t1  Transaction T cập nhật nhiều block
 |
 t2  T COMMIT; undo của T có thể giúp Q đọc phiên bản tại S
 |
 t3  DML khác sinh rất nhiều undo; tablespace thiếu chỗ
 |
 t4  Undo cũ cần cho Q bị tái sử dụng theo chính sách retention
 |
 t5  Q mới đi tới block đã thay đổi và cần undo từ t2
 |
 t6  Không thể dựng block tại SCN S -> ORA-01555
```

Điểm quan trọng là **tác động không nhất thiết xuất hiện ngay tại lúc undo bị ghi đè**: lỗi có thể chỉ được báo khi truy vấn thực sự cần undo đó để hoàn tất việc đọc nhất quán.

### 9.2. Những nguyên nhân cần xem xét

| Tình huống | Vì sao liên quan `ORA-01555`? |
|---|---|
| Truy vấn đọc rất lâu | Snapshot càng cũ, càng có thể cần nhiều phiên bản undo đã commit |
| DML đồng thời nhiều và undo space nhỏ | Undo mới có thể làm undo cũ bị tái sử dụng trước khi truy vấn xong |
| Batch job update/delete mạnh | Khối lượng undo tăng nhanh theo thời điểm, vượt mức sizing thông thường |
| Transaction/cursor kéo dài cùng pattern fetch và commit không phù hợp | Có thể gây áp lực lên nhu cầu giữ phiên bản đọc cũ, khó phục vụ cursor dài |
| Không đủ quan sát workload đỉnh | Cấu hình đủ trong giờ bình thường nhưng thất bại vào khung tải cao |

Oracle còn có các tình huống kỹ thuật khác liên quan consistent read và xử lý transaction; vì vậy **không kết luận mọi `ORA-01555` đều đơn thuần do thiếu megabyte trong undo tablespace**. Cần xem SQL, thời gian chạy, mức DML, thông số undo và log cụ thể.

### 9.3. Hướng khắc phục phù hợp

1. **Xác định câu SQL bị lỗi** và thời gian thực thi, đặc biệt các báo cáo đọc dữ liệu lớn hoặc giữ cursor lâu.
2. **Xem số liệu undo thực tế** trong thời điểm gặp lỗi: `V$UNDOSTAT`, dung lượng các undo datafile, trạng thái extent, `MAXQUERYLEN`, `SSOLDERRCNT`, `NOSPACEERRCNT`.
3. **Rút ngắn truy vấn khi có thể** bằng thiết kế index, lọc dữ liệu, kế hoạch thực thi tốt hơn hoặc chia công việc theo cách không phá hỏng yêu cầu snapshot.
4. **Cấp đủ undo space và chính sách autoextend** khi bằng chứng cho thấy đang thiếu dung lượng; lưu ý giới hạn trên storage thật.
5. **Xem lại thời gian mở transaction và cách commit**. Commit quá thường xuyên trong vòng lặp/cursor không phải giải pháp cho mọi vấn đề undo, và có thể tăng khó khăn cho việc duy trì góc nhìn nhất quán.
6. **Chỉ bật retention guarantee sau khi đánh giá đánh đổi** với rủi ro DML không thể cấp thêm undo.

Nếu báo cáo yêu cầu một snapshot xuyên nhiều câu SQL, có thể cân nhắc transaction `READ ONLY` hoặc một cách chốt dữ liệu phù hợp. Nhưng việc giữ snapshot lâu hơn thường **tăng nhu cầu undo**, nên phải tính cùng chính sách dung lượng.

### 9.4. Phân biệt với lỗi hết không gian undo `ORA-30036`

Lỗi dạng:

```text
ORA-30036: unable to extend segment ... in undo tablespace ...
```

cho biết Oracle không thể cấp thêm không gian cần thiết cho undo segment trong cấu hình hiện tại. Một số nguyên nhân gồm: undo tablespace hết không gian có thể cấp, datafile không thể mở rộng, active undo không thể ghi đè, hoặc retention guarantee giữ unexpired undo.

Hai triệu chứng khác nhau:

- **`ORA-01555`**: một truy vấn **thiếu undo cũ cần để đọc nhất quán**.
- **`ORA-30036`**: một thao tác **không thể cấp thêm undo mới** theo khả năng lưu trữ/chính sách.

Tăng retention hoặc bật guarantee có thể cải thiện một mặt nhưng làm tình trạng **thiếu chỗ cho DML** nghiêm trọng hơn nếu không cấp đủ dung lượng. Cần xem cả hai loại lỗi và các đỉnh tải của hệ thống.

## 10. Undo và Flashback Query

Oracle cho phép một số truy vấn đọc phiên bản dữ liệu ở một thời điểm trước đó bằng **Flashback Query** (`AS OF TIMESTAMP` hoặc `AS OF SCN`), khi cơ chế và dữ liệu cần thiết còn đáp ứng.

Ví dụ **minh họa** trên bảng `ACCOUNTS` đã tồn tại ổn định từ trước thời điểm truy vấn (yêu cầu có quyền phù hợp):

```sql
SELECT account_id, balance
FROM accounts AS OF TIMESTAMP
     (SYSTIMESTAMP - INTERVAL '5' MINUTE)
WHERE account_id = 'A001';
```

Ý nghĩa: yêu cầu Oracle dựng góc nhìn của bảng cách thời điểm hiện tại khoảng 5 phút. Câu SQL này **không đảm bảo luôn thành công**:

- Undo cần thiết có thể đã bị tái sử dụng.
- Bảng có thể chưa tồn tại ở thời điểm đó hoặc đã trải qua DDL làm giới hạn khả năng flashback.
- Cần quyền và chức năng phù hợp theo môi trường.

Flashback Query không phải một hệ thống lưu trữ toàn bộ lịch sử vĩnh viễn. Nó cũng khác với sao lưu/khôi phục database và khác các tính năng Flashback Database/Flashback Data Archive có mục đích, cơ chế lưu trữ và điều kiện sử dụng riêng.

## 11. Quan sát undo trong môi trường thực hành

Phần dưới đây là các lệnh **chỉ đọc**. Tên view `V$...` là dynamic performance views và `DBA_...` là dictionary views; tài khoản ứng dụng thường không được cấp quyền truy vấn chúng. Nếu nhận lỗi thiếu quyền, cần dùng tài khoản giám sát/DBA phù hợp, **không tự mở rộng quyền của tài khoản sản xuất**.

### 11.1. Xem tham số undo đang dùng

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
)
ORDER BY name;
```

Trong SQL*Plus, có thể dùng lệnh client:

```sql
SHOW PARAMETER undo_management
SHOW PARAMETER undo_tablespace
SHOW PARAMETER undo_retention
```

Kết quả cần được đọc trong ngữ cảnh instance/PDB đang kết nối. `SHOW PARAMETER` là lệnh của SQL*Plus/SQLcl, không phải SQL thuần để đưa thẳng vào JDBC.

### 11.2. Xem undo tablespace và chế độ retention

```sql
SELECT tablespace_name,
       contents,
       status,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO'
ORDER BY tablespace_name;
```

`RETENTION` cho biết chế độ như `GUARANTEE` hoặc `NOGUARANTEE`; đừng nhầm với tham số thời gian `UNDO_RETENTION` (giây).

Xem datafile của các undo tablespace:

```sql
SELECT f.tablespace_name,
       f.file_name,
       ROUND(f.bytes / 1024 / 1024, 2) AS size_mb,
       f.autoextensible,
       ROUND(f.maxbytes / 1024 / 1024, 2) AS max_mb
FROM dba_data_files f
JOIN dba_tablespaces t
  ON t.tablespace_name = f.tablespace_name
WHERE t.contents = 'UNDO'
ORDER BY f.tablespace_name, f.file_name;
```

`MAXBYTES` là giá trị được Oracle ghi nhận trong view, không nói lên toàn bộ dung lượng storage thật còn trống. Với hệ thống dùng ASM/OMF, `FILE_NAME` có thể là tên được Oracle quản lý.

### 11.3. Xem extent ACTIVE, UNEXPIRED, EXPIRED

```sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
```

Kết quả là ảnh chụp trạng thái extent tại lúc đọc. Một môi trường ít DML có thể có nhiều extent `EXPIRED`; môi trường tải cao có thể có mức `ACTIVE`/`UNEXPIRED` lớn hơn. **Không sử dụng trực tiếp số liệu này để xóa file undo**: các extent do Oracle tự quản lý.

### 11.4. Xem lịch sử sử dụng undo và dấu hiệu thiếu retention

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt,
       tuned_undoretention
FROM v$undostat
WHERE begin_time >= SYSDATE - 1
ORDER BY begin_time DESC;
```

Ý nghĩa các cột quan trọng:

| Cột `V$UNDOSTAT` | Ý nghĩa thường dùng |
|---|---|
| `BEGIN_TIME`, `END_TIME` | Khoảng thời gian thống kê |
| `UNDOBLKS` | Số undo block đã tiêu thụ trong khoảng |
| `TXNCOUNT` | Số transaction được ghi nhận trong khoảng |
| `MAXQUERYLEN` | Thời lượng lớn nhất của một truy vấn được theo dõi trong khoảng, tính bằng giây |
| `SSOLDERRCNT` | Số lần lỗi snapshot too old (`ORA-01555`) được thống kê trong khoảng |
| `NOSPACEERRCNT` | Số lần không đủ chỗ cần thiết trong undo theo thống kê |
| `TUNED_UNDORETENTION` | Khoảng retention Oracle đã tuning, tính bằng giây |

Các khoảng thống kê của `V$UNDOSTAT` thường xấp xỉ **10 phút**; số lượng lịch sử mà view giữ và việc tổng hợp phụ thuộc phiên bản. `MAXQUERYLEN` phản ánh thống kê các truy vấn được Oracle theo dõi, **không phải cam kết tuyệt đối rằng mọi truy vấn của ứng dụng đã được đo đúng cách như nhau**.

Nếu `SSOLDERRCNT` tăng trong khoảng báo cáo lỗi, đó là manh mối quan trọng để điều tra `ORA-01555`. Nếu `NOSPACEERRCNT` tăng, cần xem khả năng cấp phát undo mới. Đọc các số liệu cùng workload và cấu hình mới giúp kết luận đúng nguyên nhân.

### 11.5. Xem transaction nào đang dùng nhiều undo

Với quyền truy vấn phù hợp:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
```

`USED_UBLK` và `USED_UREC` là những chỉ số liên quan undo block/record mà transaction đang dùng; chúng không đồng nghĩa “chỉ cần một phiên dùng undo lớn là có lỗi”. Một batch ghi dữ liệu lớn có thể hoàn toàn hợp lệ. Cần xem thêm thời gian transaction chạy, tác vụ nghiệp vụ và tình trạng tài nguyên trước khi can thiệp.

## 12. Các tình huống dễ hiểu nhầm trong hệ thống ứng dụng

### Tình huống A: “`COMMIT` xong thì undo đã được xóa?”

**Không.** Commit giải phóng nhu cầu rollback cho transaction vừa commit, nhưng phiên bản trước commit có thể vẫn cần cho một câu `SELECT` đã bắt đầu trước đó hoặc Flashback Query. Undo có thể tiếp tục được giữ và sau đó được tái sử dụng theo chính sách retention.

### Tình huống B: “Tăng `UNDO_RETENTION` là sửa được mọi `ORA-01555`?”

**Không.** Nếu undo tablespace thiếu dung lượng hoặc không thể mở rộng, đặt mục tiêu retention cao hơn không tự tạo thêm file/space. Cần kiểm tra tải DML, duration của truy vấn, cấu hình datafile, thông số động và các lỗi thực tế.

### Tình huống C: “`SELECT` luôn bị chặn nếu `UPDATE` đang giữ khóa hàng?”

`SELECT` thông thường trong Oracle có thể sử dụng phiên bản nhất quán và không phải chờ `UPDATE` commit trong trường hợp phổ biến. Tuy nhiên, `SELECT ... FOR UPDATE` nhằm khóa hàng nên có thể phải chờ; các thao tác DDL và tình huống khóa đặc thù cũng có quy tắc riêng. Không nên coi tất cả hình thức đọc là tương đương.

### Tình huống D: “Tôi đang ở `READ COMMITTED`, vì sao hai lần SELECT cùng transaction ra kết quả khác?”

Vì `READ COMMITTED` cung cấp **statement-level read consistency**. Mỗi câu `SELECT` mới có thể có snapshot mới. Nếu cần các câu đọc chia sẻ một snapshot trong phạm vi phù hợp, hãy tìm hiểu `READ ONLY` hoặc `SERIALIZABLE` transaction và cân nhắc yêu cầu nghiệp vụ.

### Tình huống E: “Bật retention guarantee thì database ổn định hơn?”

Không phải luôn. Guarantee ưu tiên **giữ undo chưa hết hạn**, nên có thể khiến transaction mới không có chỗ để ghi và thất bại khi không đủ dung lượng. Quyết định dùng guarantee phải dựa trên mức độ quan trọng của truy vấn phiên bản cũ so với khả năng tiếp nhận DML.

### Tình huống F: “Phát hiện undo tablespace đầy, tôi xóa file `.dbf` để lấy chỗ?”

**Không được.** Undo datafile là thành phần cơ sở dữ liệu được Oracle quản lý; tự xóa/sửa file có nguy cơ làm hỏng database hoặc không khởi động được. DBA dùng cơ chế Oracle phù hợp để quản lý không gian và phục hồi.

### Tình huống G: “Ứng dụng Java đã dùng `@Transactional`, có phải không cần biết undo nữa?”

`@Transactional` giúp ứng dụng xác lập ranh giới transaction khi cấu hình đúng, còn Oracle vẫn dùng undo để hỗ trợ rollback và consistent read. Transaction kéo dài, batch DML lớn hoặc nhiều transaction đồng thời vẫn tiêu thụ undo; framework không tự giải quyết mọi vấn đề retention/dung lượng.

## 13. Thiết kế ứng dụng với undo và read consistency

### 13.1. Giữ transaction gọn

Trong backend Java, thông thường nên giữ những phần đọc/ghi database cần tính nguyên tử trong một transaction ngắn, rõ ràng. Tránh mở transaction rồi chờ nhập liệu, gọi dịch vụ HTTP chậm hoặc xử lý tác vụ CPU rất dài nếu các bước đó không cần nằm trong cùng ranh giới transaction.

Transaction mở lâu có thể giữ khóa và active undo lâu hơn, làm tăng áp lực tài nguyên. Tuy nhiên, **đừng chia một giao dịch nghiệp vụ bắt buộc phải nguyên tử thành nhiều commit tùy tiện** chỉ để giảm undo: cách đó có thể phá vỡ tính nhất quán nghiệp vụ.

### 13.2. Hiểu snapshot khi đọc báo cáo

Một câu SQL tổng hợp có thể đọc dữ liệu theo cùng một snapshot statement-level. Nếu báo cáo cần nhiều truy vấn có quan hệ chặt chẽ, hãy quyết định có cần transaction-level snapshot hay không. Khi sử dụng snapshot dài, phải dự trù undo cho khoảng thời gian đọc tương ứng.

Việc tách một truy vấn lớn thành nhiều truy vấn nhỏ có thể giảm thời gian mỗi câu, nhưng cũng có thể khiến các câu nhìn **các snapshot khác nhau**. Đó là đánh đổi cần đánh giá theo yêu cầu báo cáo.

### 13.3. Theo dõi workload thật trước khi đổi thông số

Khi hệ thống tăng tải, nên theo dõi đồng thời:

- `V$UNDOSTAT` theo thời điểm cao tải.
- Thời lượng truy vấn và thời gian transaction mở.
- Các lỗi `ORA-01555`, `ORA-30036`.
- Kích thước/autoextend của undo tablespace và khả năng lưu trữ thực tế.
- Các batch cập nhật/xóa, lịch chạy báo cáo, thời điểm cao tải.

Chỉ tăng `UNDO_RETENTION` hoặc chỉ tăng kích thước file trong khi query/report vẫn quá chậm có thể không xử lý tận gốc. Kết hợp điều chỉnh truy vấn, thiết kế giao dịch và dung lượng undo mới là cách tiếp cận bền vững.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Session A cập nhật hàng nhưng chưa `COMMIT`. Session B chạy `SELECT` thông thường trong `READ COMMITTED`. B có nhìn thấy giá trị mới chưa commit không?

**Trả lời:** Không. B đọc phiên bản dữ liệu nhất quán phù hợp với snapshot của statement, có thể được tái dựng nhờ undo.

**Câu 2.** Session A đã commit. Undo của A có lập tức bị xóa?

**Trả lời:** Không nhất thiết. Undo đã commit có thể được giữ để phục vụ truy vấn có snapshot cũ và Flashback Query, sau đó được tái sử dụng theo quy tắc retention.

**Câu 3.** `UNDO_RETENTION = 1800` có nghĩa mọi dữ liệu quá khứ đều truy vấn được trong 30 phút?

**Trả lời:** Không. Đây là thời gian mục tiêu (giây), còn khả năng giữ được phụ thuộc dung lượng undo, policy guarantee, workload, loại thao tác và điều kiện Flashback Query.

**Câu 4.** `ORA-01555` và `ORA-30036` khác nhau thế nào?

**Trả lời:** `ORA-01555` liên quan thiếu undo cũ cần dựng phiên bản dữ liệu cho consistent read; `ORA-30036` liên quan không thể cấp thêm không gian mới cho undo segment.

**Câu 5.** Nếu `SELECT` chạy 20 phút trong khi nhiều transaction khác commit, liệu các hàng cuối câu truy vấn có thể phản ánh snapshot khác các hàng đầu hay không?

**Trả lời:** Oracle cố bảo đảm read consistency ở cấp statement theo snapshot của câu lệnh; nếu không thể dựng phiên bản cũ vì undo không còn, câu truy vấn có thể lỗi thay vì tùy ý trộn dữ liệu từ các thời điểm khác nhau.

**Câu 6.** `UNEXPIRED` undo có được ghi đè trong chế độ `NOGUARANTEE` không?

**Trả lời:** Có thể khi Oracle cần chỗ cho undo mới theo chính sách/cơ chế sử dụng không gian. Bật `GUARANTEE` thay đổi đánh đổi: giữ unexpired undo nhưng có thể khiến DML mới không đủ chỗ.

**Câu 7.** Một transaction `SERIALIZABLE` có phải giải pháp miễn phí để báo cáo luôn nhất quán không?

**Trả lời:** Không. Nó thay đổi cách quản lý snapshot/xung đột và có thể giữ nhu cầu đọc dữ liệu phiên bản cũ lâu hơn; cần xét hoạt động ghi, thời lượng transaction, tài nguyên undo và khả năng gặp lỗi khi có xung đột.

## 15. Kết luận

**Undo segment** là nơi Oracle tổ chức thông tin cần cho việc **rollback** và **tái dựng phiên bản dữ liệu cũ**. Những undo record được lưu trong các segment của undo tablespace, theo cấu trúc extent và data block mà Oracle tự quản lý.

**Read consistency** cho phép câu `SELECT` thông thường thấy trạng thái dữ liệu phù hợp với snapshot của nó, kể cả khi các transaction khác đang thay đổi cùng bảng. Trong chế độ `READ COMMITTED`, snapshot thường gắn với **từng câu lệnh**; một câu lệnh dài có thể phải dùng nhiều undo để duy trì góc nhìn đó.

**Undo retention** quyết định mục tiêu giữ lại undo đã commit trong một thời gian, nhưng khả năng đáp ứng thực tế phụ thuộc khối lượng DML, thời gian truy vấn, kích thước/khả năng mở rộng undo tablespace và chế độ retention guarantee. Vì thế, xử lý `ORA-01555` hay `ORA-30036` đòi hỏi xem **cả nhu cầu đọc nhất quán lẫn khả năng cấp phát không gian**, thay vì chỉ thay đổi một thông số.
