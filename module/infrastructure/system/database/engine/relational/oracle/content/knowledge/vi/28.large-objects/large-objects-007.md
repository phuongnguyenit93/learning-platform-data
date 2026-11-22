# BFILE, DIRECTORY object và truy cập file phía máy chủ trong Oracle

Oracle Database có kiểu dữ liệu **BFILE** để tham chiếu tới một tệp nhị phân nằm bên ngoài database, trên hệ thống file mà database server có thể truy cập. BFILE lưu một locator gồm thông tin DIRECTORY object và tên file; nội dung file vẫn nằm ở filesystem, không được lưu trong segment của bảng như BLOB.

Để đọc BFILE, DBA tạo một **DIRECTORY object** ánh xạ một tên database tới đường dẫn thư mục trên máy chủ, sau đó cấp quyền READ cho schema cần truy cập. Tiến trình Oracle Database cũng phải có quyền hệ điều hành để đi qua thư mục và đọc file. PL/SQL dùng các routine của DBMS_LOB để kiểm tra, mở, đọc và đóng file.

BFILE phù hợp khi ứng dụng cần tham chiếu các file nhị phân được quản lý bên ngoài database, đồng thời muốn truy cập chúng thông qua SQL/PLSQL. BFILE là read-only từ góc nhìn Oracle: database có thể đọc nội dung qua locator nhưng không thể ghi hoặc sửa file bằng DBMS_LOB. Nếu cần dữ liệu được quản lý trong transaction, backup và recovery của database, BLOB thường phù hợp hơn.

Bài học thuộc chủ đề **LOB và dữ liệu lớn** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- BFILE là gì và khác BLOB như thế nào.
- DIRECTORY object ánh xạ đường dẫn filesystem phía server.
- Quyền database và quyền hệ điều hành cần có.
- Lưu locator BFILE trong bảng và tạo locator bằng BFILENAME.
- Các API DBMS_LOB dành cho file: FILEEXISTS, FILEOPEN, READ, GETLENGTH, FILECLOSE và FILEISOPEN.
- Đọc file theo chunk, xử lý exception và quản lý vòng đời file handle.
- Quyền truy cập, path injection và bảo vệ thư mục.
- Transaction, backup, RAC, giới hạn vận hành và lựa chọn BFILE hay BLOB.
- Chẩn đoán lỗi và bài thực hành SQL/PLSQL.

## 1. BFILE là gì?

BFILE là một kiểu LOB ngoài (external LOB). Cột BFILE trong bảng không chứa bytes của file; nó chứa locator để Oracle xác định file thông qua DIRECTORY object và tên file.

~~~text
Database table
  DOCUMENTS
  +------------+--------------------------------+
  | DOC_ID     | FILE_REF                       |
  +------------+--------------------------------+
  | 101        | locator -> MEDIA_DIR/report.pdf |
  +------------+--------------------------------+
                         |
                         v
              DIRECTORY object MEDIA_DIR
                         |
                         v
              Server filesystem path
              /u01/app/data/media/
                         |
                         v
              report.pdf (file bytes)
~~~

Các thành phần:

- **BFILE column/locator:** tham chiếu file, không lưu nội dung file trong database.
- **DIRECTORY object:** tên logic trong database trỏ tới một đường dẫn filesystem.
- **File name:** tên file nằm trong thư mục được ánh xạ.
- **Oracle server process:** tiến trình thực hiện thao tác đọc file.
- **OS permissions:** quyền filesystem mà tài khoản hệ điều hành chạy Oracle có trên đường dẫn và file.

### BFILE là read-only

Oracle có thể mở BFILE ở chế độ đọc và lấy bytes. DBMS_LOB không cung cấp thao tác ghi nội dung BFILE, append, trim hoặc erase file bên ngoài. Nếu cần thay đổi nội dung, ứng dụng hoặc quy trình hệ điều hành phải cập nhật file bằng công cụ riêng; database chỉ đọc lại locator khi cần.

### BFILE không tự chứa file

INSERT một locator BFILE vào bảng không upload file từ client lên server. File phải được đặt sẵn tại đường dẫn mà DIRECTORY object trỏ tới, và Oracle server phải truy cập được file đó.

### BFILE không phải đường dẫn của máy client

Đường dẫn trong DIRECTORY object là đường dẫn nhìn từ máy chủ database (hoặc filesystem được server mount), không phải đường dẫn trên máy đang chạy SQL Developer, SQL*Plus hoặc ứng dụng client. Ví dụ `C:\Users\...\report.pdf` trên laptop người dùng không tự trở thành file BFILE mà Oracle server đọc được.

## 2. So sánh BFILE với BLOB

BLOB là LOB nội bộ: nội dung nhị phân được lưu trong database. BFILE là LOB ngoài: database lưu locator, còn bytes ở filesystem.

| Tiêu chí | BFILE | BLOB |
| --- | --- | --- |
| Vị trí nội dung | Filesystem bên ngoài database | Trong database |
| Dữ liệu trong cột | Locator | Nội dung nhị phân hoặc locator nội bộ |
| Quyền ghi qua DBMS_LOB | Read-only | Có thể đọc/ghi |
| Transaction đối với nội dung | File bên ngoài không tham gia transaction Oracle | Thay đổi BLOB tuân theo transaction |
| Backup database | Không tự backup file bên ngoài | Được backup cùng database theo cơ chế backup |
| Consistency | File có thể đổi ngoài database | Nội dung được quản lý bởi database |
| Dùng khi | File đã được quản lý ở filesystem và chỉ cần đọc qua Oracle | File cần lưu, cập nhật và bảo vệ bằng transaction/database |
| Quản trị | Phải quản lý đồng bộ file, path và quyền OS | Quản lý qua tablespace, LOB storage và backup database |

### Khi nào chọn BFILE?

- File đã được đặt ở filesystem phía server bởi quy trình khác.
- Database chỉ cần đọc file, không cần cập nhật nội dung.
- Muốn lưu metadata và locator trong bảng, còn nội dung được quản lý ngoài database.
- Tệp lớn hoặc nhiều tệp ngoài database mà không muốn đưa bytes vào segment LOB nội bộ.
- Quy trình backup, đồng bộ và quyền filesystem đã được quản lý riêng.

### Khi nào chọn BLOB?

- File phải được upload và lưu cùng transaction tạo bản ghi.
- Cần bảo đảm file và metadata commit/rollback cùng nhau.
- Cần backup/restore nội dung file cùng database.
- Ứng dụng phải cập nhật, xóa hoặc thay thế nội dung qua SQL/PLSQL.
- Muốn giảm phụ thuộc vào đường dẫn filesystem và quyền OS của database server.

### BFILE và external table không giống nhau

External table cho phép SQL đọc dữ liệu dạng hàng từ file theo access driver và cấu trúc được khai báo. BFILE cho phép PL/SQL đọc bytes của một file cụ thể thông qua locator. Nếu cần phân tích CSV/record bằng SQL, external table có thể phù hợp hơn; nếu cần đọc nội dung nhị phân như PDF, ảnh hoặc file nén, BFILE là một lựa chọn khác.

## 3. DIRECTORY object

DIRECTORY object là schema object trong Oracle chứa ánh xạ tên logic tới một đường dẫn thư mục trên filesystem phía database server. Nó không tạo thư mục trên OS và cũng không chứa file.

Cú pháp:

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
~~~

Sau câu lệnh này, tên MEDIA_DIR có thể được dùng trong BFILENAME hoặc các tính năng Oracle khác cần DIRECTORY object. Đường dẫn là đường dẫn tuyệt đối trên host database hoặc filesystem được mount vào host.

### Tạo DIRECTORY cần quyền gì?

Tạo DIRECTORY yêu cầu system privilege CREATE ANY DIRECTORY. Quyền này có phạm vi rộng, vì người được cấp có thể tạo directory object trỏ tới các path trên server. Thông thường DBA hoặc tài khoản triển khai được kiểm soát tạo object; schema ứng dụng chỉ nhận quyền READ cần thiết.

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
GRANT READ ON DIRECTORY media_dir TO app_user;
~~~

Nếu cần dùng các API Oracle khác có thao tác ghi file như UTL_FILE, có thể cần quyền WRITE trên DIRECTORY tương ứng. BFILE chỉ đọc file nên chỉ cấp READ khi đó là nhu cầu duy nhất.

### DIRECTORY object không phải quyền OS

GRANT READ ON DIRECTORY chỉ cấp quyền ở lớp database. Nó không tự cấp quyền đọc file cho tiến trình Oracle ở hệ điều hành. Tài khoản OS chạy Oracle phải:

- Có quyền traverse/execute trên các thư mục cha.
- Có quyền đọc file mục tiêu.
- Có thể truy cập filesystem mount hoặc shared storage tương ứng.
- Không bị chặn bởi ACL, SELinux, container boundary hoặc chính sách OS khác.

Hai lớp quyền phải cùng cho phép thao tác thì BFILE mới đọc được.

### Đổi đường dẫn DIRECTORY

Có thể thay đổi ánh xạ bằng CREATE OR REPLACE DIRECTORY:

~~~sql
CREATE OR REPLACE DIRECTORY media_dir
AS '/u02/shared/media';
~~~

Tên DIRECTORY vẫn là MEDIA_DIR nhưng path mới được dùng cho các lần truy cập tiếp theo. File locator lưu directory alias và file name; nó không đóng băng một bản sao file hoặc path cũ. Thay đổi ánh xạ có thể làm locator cũ trỏ tới vị trí khác, vì vậy phải kiểm soát thay đổi này như một thay đổi cấu hình.

### Xem DIRECTORY object

~~~sql
SELECT directory_name,
       directory_path
FROM all_directories
WHERE directory_name = 'MEDIA_DIR';
~~~

ALL_DIRECTORIES hiển thị các directory object mà user có thể thấy theo quyền. DBA có thể dùng DBA_DIRECTORIES; directory object được quản lý theo quyền toàn database.

## 4. Tạo bảng có cột BFILE và tạo locator

Cột BFILE được khai báo như một kiểu dữ liệu trong bảng:

~~~sql
CREATE TABLE documents (
    document_id NUMBER
        CONSTRAINT pk_documents PRIMARY KEY,
    file_name VARCHAR2(255) NOT NULL,
    file_ref BFILE
);
~~~

Locator có thể được tạo bằng hàm BFILENAME:

~~~sql
INSERT INTO documents (
    document_id,
    file_name,
    file_ref
)
VALUES (
    101,
    'report.pdf',
    BFILENAME('MEDIA_DIR', 'report.pdf')
);
~~~

BFILENAME nhận tên DIRECTORY object và tên file, trả về BFILE locator. Hàm này tạo locator; nó không upload file và cũng không bảo đảm file đang tồn tại hoặc Oracle OS process có thể đọc file. Kiểm tra thực tế bằng DBMS_LOB.FILEEXISTS và thao tác mở file.

### Cập nhật locator

~~~sql
UPDATE documents
SET file_ref = BFILENAME('MEDIA_DIR', 'report-v2.pdf'),
    file_name = 'report-v2.pdf'
WHERE document_id = 101;
~~~

UPDATE thay locator trong hàng. Nó không đổi tên, copy hay xóa file trên filesystem. File cũ vẫn do quy trình ngoài database quản lý.

### Lấy locator từ bảng

~~~sql
DECLARE
    l_file BFILE;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM documents
    WHERE document_id = 101;
END;
/
~~~

Biến l_file nhận locator để các routine DBMS_LOB sử dụng. Locator không phải toàn bộ nội dung file; muốn đọc bytes phải mở BFILE và gọi READ hoặc routine phù hợp.

### BFILENAME không kiểm tra file tồn tại

Có thể INSERT một locator cho tên file chưa có trên filesystem. Lỗi thường chỉ xuất hiện khi kiểm tra/open/read. Vì vậy, nếu ứng dụng cần bảo đảm file đã được đặt sẵn, hãy kiểm tra bằng API BFILE trước khi đánh dấu metadata là sẵn sàng; vẫn phải xử lý trường hợp file bị xóa hoặc thay đổi sau bước kiểm tra.

## 5. Quyền truy cập BFILE

Để đọc BFILE, cần đồng thời thỏa mãn quyền database và quyền filesystem.

### Quyền database

DBA tạo directory object và cấp READ:

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
GRANT READ ON DIRECTORY media_dir TO app_user;
~~~

Schema APP_USER có thể tạo locator dùng MEDIA_DIR và gọi các API đọc BFILE nếu các quyền khác cần thiết cũng đã có.

### Quyền hệ điều hành

Tài khoản OS chạy Oracle Database phải đọc được file. Ví dụ thư mục có quyền database READ nhưng file thuộc sở hữu user OS khác và không có quyền đọc thì FILEOPEN/READ vẫn thất bại.

Trên Linux/Unix, cần quyền traverse (thường là execute) trên từng thư mục cha và quyền read trên file. Trên Windows, kiểm tra ACL của tài khoản dịch vụ Oracle. Nếu thư mục nằm trên NFS/SMB hoặc shared storage, kiểm tra mount, credentials, availability và quyền ở phía storage.

### Quyền của stored PL/SQL

Khi BFILE được đọc từ stored procedure/package, cần xem AUTHID:

- Definer's rights là mặc định. Chương trình chạy với quyền của owner trong phạm vi quy tắc definer rights; cấp quyền DIRECTORY READ trực tiếp cho schema owner là cách rõ ràng và dễ vận hành.
- Invoker's rights dùng quyền của invoker theo quy tắc AUTHID CURRENT_USER; người gọi phải có quyền phù hợp tại runtime.
- Quyền qua role có thể không được áp dụng trong definer-rights stored PL/SQL như quyền trực tiếp; hãy cấp quyền object trực tiếp cho owner khi chương trình cần truy cập directory.

Ví dụ:

~~~sql
GRANT READ ON DIRECTORY media_dir TO app_owner;

CREATE OR REPLACE PROCEDURE read_document (
    p_document_id IN NUMBER
)
AUTHID DEFINER
AS
    -- BFILE read code
BEGIN
    NULL;
END;
/
~~~

Ví dụ chỉ minh họa nơi đặt AUTHID; phần thân cần được bổ sung theo nghiệp vụ. Không cấp CREATE ANY DIRECTORY cho schema ứng dụng chỉ để nó đọc file. DBA quản lý mapping; ứng dụng chỉ nhận quyền tối thiểu trên các directory được phê duyệt.

### Quyền không thay thế xác thực file name

Nếu người dùng có thể gửi file name tùy ý, không nối trực tiếp chuỗi đó vào BFILENAME. Dù directory object giới hạn path gốc, ứng dụng vẫn nên dùng danh sách tên file được phép hoặc ID metadata đã được kiểm tra, giới hạn ký tự, từ chối path separator và các dạng path traversal. Không cho caller tự chọn directory alias.

## 6. DBMS_LOB API dành cho BFILE

Package DBMS_LOB cung cấp các routine làm việc với BFILE:

| Routine | Mục đích |
| --- | --- |
| FILEEXISTS | Kiểm tra file được locator tham chiếu có tồn tại và có thể được nhận diện hay không. |
| FILEOPEN | Mở file để đọc. |
| FILEISOPEN | Kiểm tra locator có đang mở hay không. |
| GETLENGTH | Lấy độ dài LOB/file theo bytes đối với BFILE. |
| READ | Đọc bytes từ một offset vào RAW buffer. |
| FILECLOSE | Đóng file đã mở. |
| FILECLOSEALL | Đóng tất cả BFILE đang mở trong session. |
| FILEGETNAME | Lấy directory alias và file name từ locator. |

### FILEEXISTS

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_exists INTEGER;
BEGIN
    l_exists := DBMS_LOB.FILEEXISTS(l_file);

    IF l_exists = 1 THEN
        DBMS_OUTPUT.PUT_LINE('File exists');
    ELSE
        DBMS_OUTPUT.PUT_LINE('File not found');
    END IF;
END;
/
~~~

FILEEXISTS trả 1 nếu file tồn tại và 0 nếu không tồn tại theo khả năng kiểm tra của Oracle. Đây chỉ là kiểm tra tại một thời điểm; file có thể bị xóa hoặc thay đổi ngay sau đó. FILEEXISTS không thay thế xử lý exception khi FILEOPEN/READ.

### FILEOPEN và FILECLOSE

~~~sql
DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
...
DBMS_LOB.FILECLOSE(l_file);
~~~

BFILE chỉ được mở ở chế độ FILE_READONLY. Sau khi mở, gọi READ/GETLENGTH theo nhu cầu rồi đóng. Không để file handle mở lâu hơn thời gian cần thiết.

### FILEISOPEN

~~~sql
IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
    DBMS_LOB.FILECLOSE(l_file);
END IF;
~~~

FILEISOPEN trả 1 nếu file đang mở và 0 nếu đóng. Dùng trong exception handler để chỉ đóng khi cần.

### GETLENGTH

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_length INTEGER;
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('Bytes = ' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

Độ dài BFILE tính theo bytes. Đối với file văn bản có encoding nhiều byte, số byte không bằng số ký tự.

### FILEGETNAME

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_dir_alias VARCHAR2(30);
    l_file_name VARCHAR2(255);
BEGIN
    DBMS_LOB.FILEGETNAME(
        l_file,
        l_dir_alias,
        l_file_name
    );

    DBMS_OUTPUT.PUT_LINE(l_dir_alias || '/' || l_file_name);
END;
/
~~~

FILEGETNAME lấy tên DIRECTORY alias và file name từ locator. Nó không trả về nội dung file và không chứng minh rằng file đang tồn tại.

## 7. Đọc BFILE bằng DBMS_LOB.READ

BFILE chứa bytes, vì vậy routine READ dùng buffer RAW. Offset của LOB bắt đầu từ 1. Tham số amount vừa là số bytes yêu cầu đọc, vừa nhận lại số bytes thực tế đã đọc.

Cú pháp khái quát:

~~~sql
DBMS_LOB.READ(
    lob_loc IN BFILE,
    amount  IN OUT INTEGER,
    offset  IN INTEGER,
    buffer  OUT RAW
);
~~~

Ví dụ đọc một chunk:

~~~sql
DECLARE
    l_file   BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_amount INTEGER := 32767;
    l_offset INTEGER := 1;
    l_buffer RAW(32767);
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

    DBMS_LOB.READ(
        l_file,
        l_amount,
        l_offset,
        l_buffer
    );

    DBMS_OUTPUT.PUT_LINE('Bytes read = ' || l_amount);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

Ví dụ này chỉ đọc chunk đầu tiên. RAW buffer trong PL/SQL có giới hạn kích thước 32767 bytes; muốn đọc file dài hơn, lặp qua nhiều chunk và xử lý mỗi buffer trước khi đọc chunk tiếp theo.

### Đọc toàn bộ file theo chunk

~~~sql
DECLARE
    l_file       BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_file_length INTEGER;
    l_offset     INTEGER := 1;
    l_amount     INTEGER;
    l_chunk_size CONSTANT PLS_INTEGER := 32767;
    l_buffer     RAW(32767);
    l_total_read INTEGER := 0;
BEGIN
    IF DBMS_LOB.FILEEXISTS(l_file) = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'BFILE does not exist');
    END IF;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_file_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_file_length LOOP
        l_amount := LEAST(
            l_chunk_size,
            l_file_length - l_offset + 1
        );

        DBMS_LOB.READ(
            l_file,
            l_amount,
            l_offset,
            l_buffer
        );

        -- Xử lý l_buffer tại đây, ví dụ ghi vào BLOB hoặc giải mã.
        l_total_read := l_total_read + l_amount;
        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
    DBMS_OUTPUT.PUT_LINE('Total bytes read = ' || l_total_read);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

Điểm quan trọng:

- Kiểm tra file và mở trước khi đọc.
- Dùng offset 1-based; sau mỗi lần đọc, cộng số bytes thực tế vào offset.
- Giới hạn mỗi chunk theo kích thước RAW buffer.
- Đóng file cả khi thành công lẫn khi có exception.
- Không in nội dung RAW trực tiếp như chuỗi ký tự; bytes có thể là PDF, ảnh, ZIP hoặc dữ liệu nhị phân bất kỳ.

### File rỗng

Nếu file có độ dài 0, vòng WHILE không chạy và không gọi READ. Đây là kết quả hợp lệ, không cần coi file rỗng là lỗi trừ khi quy tắc nghiệp vụ cấm.

### Offset vượt quá độ dài

Tránh gọi READ với offset lớn hơn độ dài file. Một lần READ không có dữ liệu tại offset có thể phát sinh NO_DATA_FOUND. Dùng GETLENGTH để giới hạn vòng lặp và xử lý trường hợp file bị thay đổi trong lúc đọc.

### BFILE không được sửa bởi READ

READ chỉ lấy bytes vào buffer PL/SQL. Nó không thay đổi file trên filesystem và không cập nhật locator trong bảng.

## 8. Đóng file an toàn và xử lý exception

File handle là tài nguyên của session. Khi mở BFILE thủ công, luôn đóng file trong đường chạy bình thường và exception. Nếu không, session có thể giữ các file handle mở cho tới khi được đóng hoặc tài nguyên session được giải phóng.

Mẫu quản lý:

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_length INTEGER;
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('Length = ' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

### Không đóng locator chưa mở

FILECLOSE trên locator chưa mở có thể phát sinh lỗi invalid file operation. Dùng FILEISOPEN để kiểm tra trước khi đóng trong cleanup handler.

### FILECLOSEALL

~~~sql
BEGIN
    DBMS_LOB.FILECLOSEALL;
END;
/
~~~

FILECLOSEALL đóng tất cả BFILE đang mở trong session. Đây là biện pháp cleanup tổng quát, nhưng có thể đóng file mà phần code khác trong cùng session còn đang cần. Ưu tiên quản lý và đóng đúng locator mà chương trình đã mở; chỉ dùng FILECLOSEALL khi kiểm soát được toàn bộ file handle trong session.

### File handle và transaction là hai vòng đời khác nhau

FILECLOSE không COMMIT hoặc ROLLBACK. COMMIT/ROLLBACK cũng không phải cách thay thế cho việc đóng file. Quản lý tài nguyên BFILE riêng với transaction của bảng metadata.

## 9. Đọc file text và encoding

BFILE đọc bytes. Nếu file là văn bản UTF-8, UTF-16 hoặc encoding khác, không thể giả định mỗi byte tương ứng một ký tự. Cần biết encoding của file và chuyển đổi đúng trước khi xử lý nội dung như VARCHAR2/CLOB.

### Phân biệt bytes và ký tự

- GETLENGTH trên BFILE trả số bytes của file.
- Offset READ là vị trí theo bytes, bắt đầu từ 1.
- Số ký tự Unicode có thể khác số bytes.
- Chia chunk tùy tiện có thể cắt giữa một chuỗi byte của ký tự nhiều byte.
- Đọc file văn bản cần xử lý charset boundary hoặc dùng API chuyển đổi LOB phù hợp.

### Không dùng UTL_RAW.CAST_TO_VARCHAR2 như bộ giải mã tổng quát

CAST_TO_VARCHAR2 không phải phép chuyển đổi charset tổng quát cho mọi file. Nó chỉ diễn giải bytes theo khả năng và charset của môi trường, có thể tạo ký tự sai hoặc mất dữ liệu. Với văn bản có encoding xác định, dùng DBMS_LOB.LOADCLOBFROMFILE hoặc UTL_I18N với charset ID phù hợp; với nội dung nhị phân, giữ RAW/BLOB.

### Đưa BFILE vào CLOB

Khi cần đọc file văn bản vào CLOB nội bộ, có thể dùng DBMS_LOB.LOADCLOBFROMFILE với charset ID phù hợp. Cần tạo CLOB đích, mở BFILE, truyền charset id, lang_context và warning theo chữ ký API của phiên bản Oracle. Ví dụ khái niệm:

~~~sql
DECLARE
    l_src BFILE := BFILENAME('TEXT_DIR', 'notes.txt');
    l_dest CLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    INSERT INTO text_documents(document_id, content)
    VALUES (1, EMPTY_CLOB())
    RETURNING content INTO l_dest;

    DBMS_LOB.FILEOPEN(l_src, DBMS_LOB.FILE_READONLY);

    DBMS_LOB.LOADCLOBFROMFILE(
        dest_lob     => l_dest,
        src_bfile    => l_src,
        amount       => DBMS_LOB.LOBMAXSIZE,
        dest_offset  => l_dest_offset,
        src_offset   => l_src_offset,
        bfile_csid   => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning      => l_warning
    );

    DBMS_LOB.FILECLOSE(l_src);
END;
/
~~~

Đây là mẫu minh họa cho trường hợp bảng TEXT_DOCUMENTS có cột CONTENT CLOB và file thực sự được mã hóa UTF-8. Cần kiểm tra warning, exception và charset thực tế; không sao chép AL32UTF8 cho file có encoding khác. CLOB đích được lưu trong transaction Oracle, còn BFILE nguồn vẫn ở filesystem.

## 10. Sao chép BFILE vào BLOB

Một quy trình có thể nhận file ngoài qua BFILE rồi sao chép nội dung vào BLOB để đưa file vào vùng lưu trữ được database quản lý. Sau khi copy, nội dung BLOB tuân theo transaction, backup và recovery của database.

Ví dụ với file nhỏ hơn giới hạn amount của API:

~~~sql
CREATE TABLE stored_documents (
    document_id NUMBER PRIMARY KEY,
    content BLOB
);

DECLARE
    l_src BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_dest BLOB;
    l_amount INTEGER;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
BEGIN
    IF DBMS_LOB.FILEEXISTS(l_src) = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Source file not found');
    END IF;

    INSERT INTO stored_documents(document_id, content)
    VALUES (101, EMPTY_BLOB());

    SELECT content
    INTO l_dest
    FROM stored_documents
    WHERE document_id = 101
    FOR UPDATE;

    DBMS_LOB.FILEOPEN(l_src, DBMS_LOB.FILE_READONLY);
    l_amount := DBMS_LOB.GETLENGTH(l_src);

    DBMS_LOB.LOADBLOBFROMFILE(
        dest_lob    => l_dest,
        src_bfile   => l_src,
        amount      => l_amount,
        dest_offset => l_dest_offset,
        src_offset  => l_src_offset
    );

    DBMS_LOB.FILECLOSE(l_src);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_src) = 1 THEN
            DBMS_LOB.FILECLOSE(l_src);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Ví dụ giả định file đủ nhỏ để amount nằm trong giới hạn kiểu của routine và có quyền tạo bảng. Với file lớn, dùng cách đọc/copy theo chunk hoặc API phù hợp phiên bản, theo dõi offset và giới hạn bộ nhớ. BLOB đích được khóa bằng SELECT FOR UPDATE để cập nhật locator trong transaction.

### Khi nào copy BFILE sang BLOB?

- Muốn chụp một phiên bản file bất biến tại thời điểm nhập.
- Cần file được backup/restore cùng database.
- Cần nội dung file tham gia transaction với metadata.
- Muốn giảm phụ thuộc vào filesystem sau khi import.

Sau khi copy thành công, quy trình ngoài có thể lưu trữ hoặc xóa file nguồn theo chính sách riêng. Không xóa nguồn trước khi transaction chứa BLOB commit và đã xác nhận kết quả.

## 11. Transaction và consistency của file ngoài

BFILE locator có thể được lưu trong transaction, nhưng bytes ở filesystem không thuộc transaction Oracle:

- INSERT/UPDATE locator có thể COMMIT hoặc ROLLBACK.
- Tạo, xóa, thay thế hoặc sửa file trên OS không được Oracle rollback.
- FILEOPEN không khóa file theo cơ chế row lock của Oracle.
- Database read consistency không tạo snapshot cho nội dung filesystem.
- File có thể bị đổi giữa FILEEXISTS và FILEOPEN, hoặc trong lúc một quy trình khác đang cập nhật.

### Race giữa kiểm tra và mở file

Một luồng xử lý có thể:

1. FILEEXISTS trả 1.
2. Một tiến trình OS khác xóa hoặc đổi tên file.
3. FILEOPEN phát sinh lỗi.

Vì vậy, FILEEXISTS là kiểm tra tiện ích, không phải bảo đảm file sẽ còn tồn tại. Luôn bắt lỗi ở FILEOPEN/READ.

### Quy trình publish file an toàn

Với file được tạo bởi một hệ thống khác, nên dùng tên file bất biến theo version hoặc ID, ghi file vào tên tạm rồi publish bằng thao tác rename/atomic move trên filesystem khi file đã hoàn chỉnh. Sau đó mới ghi locator vào bảng. Tránh ghi đè nội dung một file đang được nhiều session đọc.

Nếu phải thay thế file, cân nhắc versioned filename và cập nhật locator trong database sau khi file mới đã sẵn sàng. Việc thay file trên OS và cập nhật metadata trong database vẫn không phải một transaction phân tán tự động; cần thiết kế quy trình khôi phục khi một bước thành công còn bước kia thất bại.

## 12. Bảo mật DIRECTORY và file name

DIRECTORY object là ranh giới truy cập filesystem do database quản lý. Cấp quyền READ cho một user đồng nghĩa user đó có thể yêu cầu Oracle đọc file trong directory được cấp, theo quyền OS của Oracle process. Vì vậy, chọn path và grantee rất quan trọng.

### Nguyên tắc least privilege

- Chỉ DBA/tài khoản triển khai được kiểm soát mới tạo hoặc thay đổi DIRECTORY object.
- Chỉ cấp READ cho schema cần đọc file.
- Không cấp WRITE nếu chỉ dùng BFILE.
- Không cấp quyền trên thư mục chứa file cấu hình nhạy cảm, wallet, password hoặc file hệ thống.
- Tách thư mục theo ứng dụng và loại dữ liệu; không dùng một directory gốc quá rộng.
- Không cấp CREATE ANY DIRECTORY cho schema ứng dụng thông thường.
- Rà soát và thu hồi quyền khi ứng dụng/người dùng không còn cần truy cập.

### GRANT và REVOKE

~~~sql
GRANT READ ON DIRECTORY media_dir TO app_user;

REVOKE READ ON DIRECTORY media_dir FROM app_user;
~~~

Quyền DIRECTORY là object privilege. GRANT READ không tạo file, không thay đổi OS permissions và không cho phép user tùy ý đọc mọi path trên server.

### Không nhận directory alias tùy ý từ người dùng

Không để request truyền tên DIRECTORY object và dùng trực tiếp:

~~~sql
-- Thiết kế không an toàn nếu p_directory do client tùy ý gửi.
l_file := BFILENAME(p_directory, p_file_name);
~~~

Thay vào đó, cố định alias ở server-side code hoặc ánh xạ một mã nghiệp vụ được kiểm tra sang một directory đã được phê duyệt. Caller chỉ nên chọn document ID mà họ được phép truy cập.

### Không nhận file path hoàn chỉnh từ client

BFILENAME nhận directory alias và file name riêng. Không nối đường dẫn tuyệt đối từ client, không chấp nhận các thành phần thư mục như `..` hoặc dấu phân cách path trong file name nếu nghiệp vụ chỉ cho phép tên file đơn. Dùng danh sách ký tự cho phép, giới hạn độ dài và tra cứu file name từ metadata đã được xác thực.

### Không tin tên file chỉ vì nó được lưu trong bảng

Tên file có thể đến từ upload hoặc tích hợp ngoài. Nếu file name được lưu trong bảng mà không chuẩn hóa, kẻ tấn công có thể lợi dụng path traversal, tên đặc biệt hoặc ký tự điều khiển để yêu cầu truy cập file ngoài dự kiến. Hãy kiểm tra file name lúc tiếp nhận, giới hạn thư mục, dùng generated ID và không để dữ liệu không tin cậy quyết định directory alias.

### Quyền OS nên tối thiểu

Tài khoản dịch vụ Oracle chỉ nên có quyền đọc các thư mục cần thiết. Tránh cấp quyền đọc toàn bộ home directory, thư mục backup, wallet hoặc thư mục chứa credential. DIRECTORY object giới hạn mapping ở database, nhưng OS permission là lớp bảo vệ cuối cùng đối với file.

## 13. Vận hành: backup, restore và đồng bộ file

BFILE bytes nằm ngoài database nên không được RMAN backup như BLOB. Backup database có thể lưu locator và metadata, nhưng không tự lưu nội dung file.

### Backup phải bao gồm cả hai phía

Một quy trình backup BFILE cần:

1. Backup bảng metadata và database theo chính sách RMAN.
2. Backup thư mục/file bên ngoài bằng công cụ filesystem hoặc storage.
3. Ghi nhận mapping DIRECTORY object và path trên từng môi trường.
4. Đảm bảo snapshot database và snapshot file tương thích về thời điểm.
5. Kiểm thử restore database và file cùng nhau.

Nếu chỉ restore database, locator có thể trỏ tới file đã bị xóa, thay thế hoặc chưa được khôi phục. Nếu chỉ restore file về phiên bản mới hơn trong khi metadata được point-in-time restore về trước, dữ liệu ứng dụng có thể không nhất quán.

### Data Guard và standby

Data Guard bảo vệ database files và metadata theo cơ chế redo transport/apply, nhưng không tự nhân bản các file BFILE trên filesystem ngoài database. Hệ thống cần một quy trình đồng bộ file riêng tới standby host, đồng thời bảo đảm DIRECTORY object trỏ đúng path và tài khoản Oracle trên standby có quyền đọc.

Khi switchover/failover, file có thể không tồn tại trên host mới nếu chưa replicate. Hãy kiểm tra BFILE availability như một phần của readiness check cho DR.

### Oracle RAC

Trong RAC, mỗi instance có thể chạy trên node khác nhau. Nếu DIRECTORY trỏ tới local filesystem chỉ có trên node 1, session được route sang node 2 có thể không đọc được cùng file. Dùng shared filesystem/cluster filesystem hoặc đồng bộ file và path một cách có kiểm soát trên mọi node có thể phục vụ service.

Kiểm tra:

- Path có cùng ý nghĩa trên tất cả node không?
- File có tồn tại và cùng checksum/version trên mỗi node không?
- Oracle OS account trên mỗi node có quyền đọc không?
- Mount có sẵn sau reboot/failover không?
- Quy trình deploy file có hoàn tất trước khi service nhận request không?

Result cache/LOB cache không thay thế việc bảo đảm file có sẵn trên node.

### Immutable file và checksum

Với file quan trọng, lưu metadata như kích thước, checksum, version, created_at và trạng thái publish cùng locator. Có thể tính checksum ở tầng ứng dụng hoặc pipeline ingest; BFILE không tự bảo đảm file không bị thay đổi ngoài database.

Tên file có version/UUID giúp tránh việc thay nội dung dưới cùng một tên trong khi session đang đọc. Khi file mới đã sẵn sàng, cập nhật locator trong transaction rồi giữ phiên bản cũ theo retention policy.

## 14. Giới hạn và đặc điểm cần nhớ

### BFILE là read-only và external

- Không dùng DBMS_LOB.WRITE, APPEND, TRIM hoặc ERASE với BFILE.
- Không dùng locator để upload nội dung từ client.
- Không có transaction rollback cho thay đổi filesystem.
- Không có backup/recovery file tự động từ RMAN.
- Không có row lock Oracle bảo vệ bytes của file.

### Giới hạn kích thước

BFILE có giới hạn kích thước theo phiên bản Oracle; tài liệu Oracle truyền thống quy định tối đa khoảng 4 GB cho một BFILE. Kiểm tra giới hạn chính xác của release/platform đang dùng và kiểu số của các API amount/offset trước khi xử lý file gần giới hạn. Không giả định mọi routine PL/SQL nhận được toàn bộ kích thước file trong một lần gọi; đọc theo chunk là cách an toàn hơn cho file lớn.

### Số lượng file mở

Mỗi BFILE đang mở sử dụng tài nguyên file handle. Session có giới hạn tài nguyên và OS cũng có giới hạn file descriptor/handle. Đóng file sớm, không mở hàng nghìn file rồi mới đóng cuối batch; xử lý exception và theo dõi lỗi vượt giới hạn.

### Directory object và file có thể thay đổi độc lập

DBA có thể CREATE OR REPLACE DIRECTORY để ánh xạ cùng alias sang path khác. File có thể bị rename/delete/replace ngoài database. Locator không bảo đảm tính bất biến của path hoặc nội dung. Cần quy trình quản lý cấu hình và file version.

### BFILE không tự giải mã định dạng file

BFILE chỉ cung cấp bytes. Oracle không tự phân tích PDF, JPEG, ZIP, Office document hoặc định dạng riêng. Ứng dụng phải dùng parser phù hợp hoặc chuyển nội dung vào LOB nội bộ/processing service.

## 15. Chẩn đoán lỗi BFILE

Khi FILEOPEN hoặc READ thất bại, kiểm tra theo thứ tự:

1. Locator có NULL không?
2. DIRECTORY alias trong locator có tồn tại không?
3. DIRECTORY object có trỏ tới đúng path server không?
4. User/effective PL/SQL principal có quyền READ trên directory không?
5. Oracle OS process có quyền traverse thư mục và read file không?
6. File có tồn tại, đúng tên, đúng case sensitivity và đúng node không?
7. File có bị khóa, thay thế hoặc xóa trong lúc truy cập không?
8. Session có còn file handle mở vượt giới hạn không?

### Một số lỗi thường gặp

| Mã lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| ORA-22285 | Directory hoặc file không tồn tại cho thao tác file | Kiểm tra DIRECTORY object, path, filename và file trên server. |
| ORA-22288 | Thao tác file/LOB thất bại | Xem lỗi OS đi kèm, quyền filesystem, mount và trạng thái file. |
| ORA-22290 | Thao tác vượt giới hạn số file/LOB đang mở | Đóng locator đúng cách, kiểm tra FILEISOPEN và số handle. |
| ORA-22289 | Locator/file operation không hợp lệ trong ngữ cảnh gọi | Kiểm tra locator, trạng thái open/close và thứ tự API. |
| ORA-01031 | Insufficient privileges | Kiểm tra READ privilege trên DIRECTORY và quyền hiệu lực của stored code. |
| ORA-06502 | Numeric/value error | Kiểm tra buffer RAW, amount, offset và chuyển đổi dữ liệu. |

Thông báo cụ thể có thể kèm OS error hoặc mã lỗi khác. Ghi lại DIRECTORY alias, file name đã chuẩn hóa, operation thất bại và SQLCODE/SQLERRM; không ghi toàn bộ nội dung file hoặc đường dẫn nhạy cảm vào log công khai.

### Kiểm tra quyền directory

~~~sql
SELECT grantee,
       table_name AS directory_name,
       privilege
FROM all_tab_privs
WHERE table_name = 'MEDIA_DIR'
ORDER BY grantee, privilege;
~~~

ALL_TAB_PRIVS hiển thị object grants mà user có thể thấy. DBA có thể kiểm tra DBA_TAB_PRIVS. Nếu stored code dùng definer rights, xác nhận quyền trực tiếp của owner thay vì chỉ dựa vào role.

### Kiểm tra đường dẫn và trạng thái object

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'MEDIA_DIR';

SELECT object_name, object_type, status
FROM user_objects
WHERE object_type IN ('TABLE', 'PROCEDURE', 'FUNCTION', 'PACKAGE')
ORDER BY object_type, object_name;
~~~

Directory object không phải table/object PL/SQL thông thường trong USER_OBJECTS. Dùng ALL_DIRECTORIES/DBA_DIRECTORIES để tra mapping.

## 16. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE. DBA cần chuẩn bị thư mục và file trên máy chủ database trước. DDL có implicit commit trong Oracle; không chạy các lệnh tạo/xóa object trên schema nghiệp vụ thật.

### Chuẩn bị phía DBA và hệ điều hành

1. Tạo thư mục trên database server, ví dụ `/u01/app/data/media`.
2. Đặt file thử nghiệm `sample.bin` vào thư mục đó.
3. Cấp quyền OS để tài khoản dịch vụ Oracle có thể traverse thư mục và đọc file.
4. Tạo DIRECTORY object và cấp READ:

~~~sql
CREATE OR REPLACE DIRECTORY lab_media_dir
AS '/u01/app/data/media';

GRANT READ ON DIRECTORY lab_media_dir TO lab_user;
~~~

Đường dẫn phải tồn tại trên host database. Nếu dùng Windows hoặc shared filesystem, thay bằng path phù hợp với OS/database service account. Người học không thể thay bước này bằng đường dẫn trên máy client.

### Bước 1: kiểm tra directory mapping

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'LAB_MEDIA_DIR';
~~~

Xác nhận path đúng với vị trí file mà Oracle server nhìn thấy.

### Bước 2: tạo bảng lưu locator

~~~sql
CREATE TABLE lab_bfile_documents (
    document_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255) NOT NULL,
    file_ref BFILE
);
~~~

### Bước 3: tạo và lưu locator

~~~sql
INSERT INTO lab_bfile_documents (
    document_id,
    file_name,
    file_ref
)
VALUES (
    1,
    'sample.bin',
    BFILENAME('LAB_MEDIA_DIR', 'sample.bin')
);

COMMIT;
~~~

Lệnh INSERT chỉ lưu locator. Nó không copy bytes của sample.bin vào database.

### Bước 4: kiểm tra FILEEXISTS

~~~sql
DECLARE
    l_file BFILE;
    l_exists INTEGER;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    l_exists := DBMS_LOB.FILEEXISTS(l_file);

    IF l_exists = 1 THEN
        DBMS_OUTPUT.PUT_LINE('File exists');
    ELSE
        DBMS_OUTPUT.PUT_LINE('File does not exist');
    END IF;
END;
/
~~~

Nếu trả 0, kiểm tra tên file, path, case sensitivity và việc file đã được đặt trên server chưa.

### Bước 5: mở file và lấy độ dài

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    DBMS_OUTPUT.PUT_LINE('File bytes = ' || l_length);
    DBMS_OUTPUT.PUT_LINE(
        'Is open = ' || DBMS_LOB.FILEISOPEN(l_file)
    );

    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

Quan sát rằng GETLENGTH trả số bytes, không phải số ký tự.

### Bước 6: đọc file theo chunk

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_buffer RAW(32767);
    l_total INTEGER := 0;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);
        DBMS_LOB.READ(l_file, l_amount, l_offset, l_buffer);

        -- Có thể xử lý l_buffer hoặc chuyển tiếp sang LOB đích.
        l_total := l_total + l_amount;
        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
    DBMS_OUTPUT.PUT_LINE('Read bytes = ' || l_total);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

Thử với file lớn hơn 32767 bytes để quan sát nhiều lần READ. Không in RAW buffer như văn bản nếu chưa xác định encoding.

### Bước 7: kiểm tra tên directory và file từ locator

~~~sql
DECLARE
    l_file BFILE;
    l_directory VARCHAR2(128);
    l_name VARCHAR2(255);
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEGETNAME(
        l_file,
        l_directory,
        l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_directory || '/' || l_name);
END;
/
~~~

### Bước 8: quan sát quyền

~~~sql
SELECT grantee, table_name, privilege
FROM all_tab_privs
WHERE table_name = 'LAB_MEDIA_DIR';
~~~

Nếu không thấy quyền hoặc FILEOPEN bị từ chối, nhờ DBA kiểm tra grants và quyền OS của Oracle process.

### Bước 9: dọn dữ liệu

~~~sql
DROP TABLE lab_bfile_documents PURGE;
~~~

DBA có thể thu hồi quyền và xóa DIRECTORY object sau khi không còn ứng dụng sử dụng:

~~~sql
REVOKE READ ON DIRECTORY lab_media_dir FROM lab_user;
DROP DIRECTORY lab_media_dir;
~~~

DROP DIRECTORY chỉ xóa object ánh xạ trong Oracle; nó không xóa thư mục hoặc file trên filesystem. Chỉ xóa file/thư mục bằng quy trình OS riêng sau khi xác nhận không còn locator hoặc ứng dụng nào sử dụng.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| BFILENAME tạo locator nhưng FILEEXISTS trả 0 | File không tồn tại ở path server hoặc sai tên | Kiểm tra directory mapping và file trên host database. |
| ORA-22285 khi mở | Directory/file không tồn tại hoặc tên không đúng | Kiểm tra ALL_DIRECTORIES, filename và case sensitivity. |
| ORA-22288 khi mở/đọc | OS permission, mount hoặc file operation thất bại | Kiểm tra lỗi OS đi kèm và quyền Oracle service account. |
| ORA-01031 | Thiếu READ privilege hoặc stored code dùng sai effective principal | Cấp quyền đúng cho schema/definer hoặc invoker. |
| File tồn tại trên laptop nhưng Oracle không thấy | Path là trên client, không phải server | Đưa file lên filesystem mà database server truy cập được. |
| DIRECTORY READ đã grant nhưng vẫn không đọc được | OS process không có quyền traverse/read | Sửa OS ACL/permissions và mount. |
| FILECLOSE báo lỗi | Locator chưa mở hoặc đã đóng | Kiểm tra FILEISOPEN trước cleanup. |
| ORA-22290 | Quá nhiều file handle đang mở | Đóng file sau mỗi thao tác, rà soát exception path. |
| File text bị lỗi dấu | Encoding không đúng hoặc chunk cắt giữa multibyte character | Dùng LOAD CLOB API với charset ID chính xác. |
| BFILE locator còn nhưng file đã mất | File bị xóa/di chuyển ngoài database | Đồng bộ metadata và filesystem; kiểm tra file khi mở. |
| Sau failover không đọc được file | File chưa được đồng bộ tới node/standby mới | Replicate file và path/permissions trên tất cả host cần phục vụ. |
| Backup database restore nhưng file không có | BFILE bytes không nằm trong RMAN backup | Backup/restore filesystem riêng và đồng bộ point-in-time. |

## 18. Câu hỏi tự kiểm tra

1. **BFILE lưu gì trong bảng?** Locator tham chiếu DIRECTORY object và tên file, không lưu bytes của file.
2. **BFILE nằm ở đâu?** Trên filesystem mà database server có thể truy cập.
3. **BFILE có thể ghi bằng DBMS_LOB không?** Không; BFILE read-only.
4. **DIRECTORY object có tạo thư mục OS không?** Không; nó chỉ ánh xạ tên logic tới path.
5. **Tạo DIRECTORY cần quyền nào?** System privilege CREATE ANY DIRECTORY.
6. **BFILE cần quyền DIRECTORY nào?** READ; WRITE không cần nếu chỉ đọc BFILE.
7. **GRANT READ có cấp quyền OS không?** Không; Oracle service account vẫn phải có quyền filesystem.
8. **BFILENAME có kiểm tra file tồn tại không?** Không; nó tạo locator.
9. **FILEEXISTS trả về gì?** 1 nếu file tồn tại theo kiểm tra, 0 nếu không.
10. **Offset của DBMS_LOB.READ bắt đầu từ đâu?** Từ 1 và tính theo bytes với BFILE.
11. **Vì sao đọc theo chunk?** RAW buffer PL/SQL có giới hạn; chunk giúp xử lý file lớn và kiểm soát bộ nhớ.
12. **Tại sao phải FILECLOSE trong exception handler?** Để giải phóng file handle khi thao tác thất bại.
13. **FILECLOSEALL có nên dùng tùy tiện không?** Không; nó đóng tất cả BFILE đang mở trong session.
14. **GETLENGTH trả số ký tự hay bytes?** Bytes đối với BFILE.
15. **BFILE có transaction semantics cho file ngoài không?** Không; transaction chỉ quản lý locator/metadata trong database.
16. **RMAN có backup nội dung BFILE không?** Không; file ngoài cần backup riêng.
17. **RAC cần chú ý gì?** Path/file phải sẵn sàng và có quyền đọc trên mọi node có thể nhận session.
18. **Data Guard có tự replicate BFILE file không?** Không; cần cơ chế đồng bộ filesystem riêng.
19. **Khi nào chuyển BFILE sang BLOB?** Khi cần nội dung file được database quản lý, backup và transaction.
20. **BFILE khác external table thế nào?** BFILE đọc bytes qua locator; external table đọc dữ liệu file như các hàng/cột SQL.

BFILE cho phép Oracle tham chiếu và đọc file nhị phân nằm ngoài database thông qua DIRECTORY object. Muốn truy cập thành công, cần đồng thời có locator đúng, quyền READ trong database và quyền filesystem cho Oracle server process. Dùng DBMS_LOB để kiểm tra, mở, đọc theo chunk và đóng file; luôn xử lý exception và không nhầm file handle với transaction. Vì bytes nằm ngoài database, phải quản lý backup, restore, version, RAC/standby availability và tính nhất quán file riêng. Chọn BFILE khi chỉ cần đọc file ngoài; chọn BLOB khi nội dung cần được database quản lý như dữ liệu nội bộ.
