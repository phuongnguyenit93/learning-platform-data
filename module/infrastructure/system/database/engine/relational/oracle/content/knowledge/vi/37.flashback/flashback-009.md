# Undo retention, thời gian lưu lịch sử và giới hạn khả năng flashback

Flashback là nhóm tính năng của Oracle Database cho phép xem lại hoặc đưa dữ liệu và database về một trạng thái trong quá khứ. Khả năng quay lại thời điểm nào phụ thuộc vào loại Flashback đang sử dụng và loại thông tin lịch sử mà Oracle còn giữ.

Trong chủ đề Flashback, cần phân biệt ba cơ chế chính:

- **Flashback Query và Flashback Table** dựa vào undo data để dựng lại phiên bản dữ liệu trước đó. Khả năng truy cập lịch sử thường bị giới hạn bởi thời gian undo còn được giữ và dung lượng undo tablespace.
- **Flashback Database** dùng flashback logs trong Fast Recovery Area (FRA) để đưa toàn bộ database về một thời điểm trước đó. Thời gian mục tiêu được điều khiển bởi tham số DB_FLASHBACK_RETENTION_TARGET và còn phụ thuộc dung lượng lưu trữ.
- **Flashback Data Archive** lưu lịch sử thay đổi của các bảng được cấu hình trong một khoảng thời gian dài hơn, theo retention policy riêng. Nó không phụ thuộc vào việc undo thông thường còn tồn tại hay không cho toàn bộ thời gian lưu trữ đã cấu hình.

Vì vậy, cấu hình UNDO_RETENTION cao không tự động giúp Flashback Database quay lại xa hơn; ngược lại, tăng DB_FLASHBACK_RETENTION_TARGET cũng không bảo đảm Flashback Query có thể đọc được dữ liệu cũ. Muốn xác định giới hạn lịch sử thực tế, phải hiểu đúng cơ chế lưu trữ, theo dõi mức sử dụng và kiểm tra khả năng phục hồi.

## 1. Undo data và vai trò trong Flashback

Undo data là thông tin Oracle lưu để có thể hoàn tác thay đổi và cung cấp consistent read. Khi transaction thay đổi một block, Oracle ghi lại thông tin trước thay đổi vào undo segment. Các thông tin này phục vụ nhiều mục đích:

- **ROLLBACK**: hoàn tác thay đổi của transaction chưa commit.
- **Read consistency**: một câu SQL nhìn thấy dữ liệu nhất quán tại thời điểm bắt đầu câu lệnh, kể cả khi transaction khác đang thay đổi dữ liệu.
- **Transaction recovery**: hỗ trợ Oracle khôi phục trạng thái nhất quán sau sự cố instance.
- **Flashback Query/Table**: dựng lại phiên bản hàng dữ liệu ở thời điểm trong quá khứ khi undo cần thiết vẫn còn.

Undo được quản lý trong undo tablespace. Trong chế độ automatic undo management, Oracle tự quản lý undo segment và extent; DBA chủ yếu cấu hình undo tablespace, theo dõi dung lượng và điều chỉnh retention.

### 1.1. Undo không phải là bản sao lưu

Undo ghi lại thông tin cần thiết để hoàn tác thay đổi, không phải một bản backup đầy đủ của database. Undo có thể giúp xem lại giá trị cũ của hàng dữ liệu trong thời gian còn được giữ, nhưng không thay thế RMAN backup, archived redo log hay quy trình disaster recovery.

Undo cũng không phải nhật ký nghiệp vụ dài hạn. Khi hết nhu cầu cho read consistency hoặc retention, các extent có thể được tái sử dụng theo chính sách và tình trạng dung lượng.

### 1.2. Kiểm tra cấu hình undo

Có thể kiểm tra các tham số chính bằng SQL*Plus hoặc SQLcl:

    SHOW PARAMETER undo_management;
    SHOW PARAMETER undo_tablespace;
    SHOW PARAMETER undo_retention;

Hoặc truy vấn:

    SELECT name, value, isdefault, issys_modifiable
    FROM v$parameter
    WHERE name IN (
        'undo_management',
        'undo_tablespace',
        'undo_retention'
    )
    ORDER BY name;

UNDO_TABLESPACE xác định undo tablespace mà instance đang sử dụng. UNDO_RETENTION đặt thời gian retention mục tiêu, tính bằng giây. Trong các phiên bản Oracle hiện đại, automatic undo management thường được sử dụng; hãy kiểm tra cấu hình thực tế thay vì giả định.

## 2. UNDO_RETENTION có ý nghĩa gì?

UNDO_RETENTION chỉ định khoảng thời gian tối thiểu mà Oracle cố gắng giữ undo data sau khi transaction commit, để phục vụ read consistency và các thao tác cần dữ liệu cũ. Giá trị thường được cấu hình bằng giây.

Ví dụ:

    ALTER SYSTEM SET undo_retention = 3600 SCOPE = BOTH;

Cấu hình trên đặt mục tiêu retention là 3.600 giây, tương đương một giờ. Đây là mục tiêu quản lý undo; nó không mặc nhiên bảo đảm mọi undo record đều tồn tại đủ một giờ.

Giá trị mặc định thường gặp trong Oracle là 900 giây, nhưng giá trị thực tế phụ thuộc phiên bản, cấu hình và thay đổi do DBA thực hiện. Không nên dựa vào mặc định để kết luận database có thể Flashback Query trong 15 phút.

### 2.1. Retention mục tiêu và retention thực tế

Có hai khái niệm cần tách biệt:

- **UNDO_RETENTION**: thời gian retention được yêu cầu qua tham số.
- **TUNED_UNDORETENTION**: thời gian retention Oracle tính toán và điều chỉnh dựa trên workload, dung lượng undo và điều kiện vận hành.

Trong automatic undo management, Oracle có thể giữ undo lâu hơn giá trị UNDO_RETENTION nếu có đủ dung lượng. Ngược lại, khi undo tablespace thiếu chỗ và retention guarantee không được bật, Oracle có thể tái sử dụng undo đã commit trước khi hết thời gian mục tiêu để phục vụ transaction mới.

Do đó, một truy vấn Flashback Query có thể thất bại dù thời điểm cần truy vấn nằm trong khoảng UNDO_RETENTION đã cấu hình. Cần quan sát retention được tune và các lỗi thực tế trong V$UNDOSTAT.

### 2.2. Oracle tự điều chỉnh retention

Oracle xem xét thời gian chạy truy vấn, tốc độ phát sinh undo và dung lượng tablespace để quản lý undo. Với undo tablespace có kích thước cố định, Oracle có thể tự điều chỉnh thời gian retention theo khả năng chứa undo. Với tablespace có datafile autoextend, việc giữ undo lâu hơn còn phụ thuộc khả năng mở rộng đến giới hạn đã đặt và dung lượng lưu trữ vật lý.

Không nên hiểu rằng bật AUTOEXTEND sẽ làm undo retention trở thành vô hạn. Datafile có MAXSIZE, filesystem hoặc ASM disk group có giới hạn; FRA và các tài nguyên lưu trữ khác cũng có thể chịu áp lực.

## 3. NOGUARANTEE và RETENTION GUARANTEE

Undo tablespace có thuộc tính retention quyết định Oracle có được phép ghi đè undo chưa hết thời gian retention hay không.

### 3.1. NOGUARANTEE

NOGUARANTEE là chế độ mặc định thường gặp. Khi thiếu chỗ, Oracle có thể tái sử dụng undo đã commit ngay cả khi thời gian UNDO_RETENTION chưa hết. Cách này ưu tiên khả năng tiếp tục xử lý DML và tránh để database bị dừng ghi chỉ vì phải giữ undo cũ.

Đổi lại, các truy vấn dài hoặc Flashback Query cần undo cũ có thể gặp lỗi snapshot too old nếu dữ liệu cần thiết đã bị tái sử dụng.

### 3.2. RETENTION GUARANTEE

RETENTION GUARANTEE yêu cầu Oracle không ghi đè undo chưa hết thời gian retention để lấy chỗ cho transaction mới. Điều này tăng khả năng giữ lịch sử undo trong khoảng đã cấu hình, nhưng có một đánh đổi vận hành quan trọng: nếu undo tablespace đầy và không thể mở rộng, transaction DML mới có thể thất bại vì không cấp phát được undo extent.

Bật guarantee:

    ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;

Tắt guarantee:

    ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;

Tên tablespace trong ví dụ phải được thay bằng undo tablespace thật. Đây là thay đổi ở cấp tablespace và cần được DBA cân nhắc cùng với dung lượng, tốc độ phát sinh undo, thời gian truy vấn dài nhất và yêu cầu nghiệp vụ.

### 3.3. So sánh hai chế độ

| Thuộc tính | NOGUARANTEE | RETENTION GUARANTEE |
|---|---|---|
| Giữ undo chưa hết retention | Có thể bị ghi đè khi thiếu chỗ | Không bị ghi đè để lấy chỗ cho transaction mới |
| Khả năng Flashback Query trong cửa sổ mục tiêu | Có thể giảm khi workload tạo nhiều undo | Được bảo vệ tốt hơn nếu cấu hình và dung lượng đáp ứng |
| Rủi ro khi tablespace đầy | Có thể tái sử dụng undo cũ | DML có thể lỗi do không còn undo extent |
| Phù hợp | Hệ thống ưu tiên tính liên tục của DML | Hệ thống cần bảo đảm giữ undo cho một cửa sổ lịch sử xác định và có capacity plan phù hợp |

RETENTION GUARANTEE không tạo thêm dung lượng. Nếu cần giữ undo lâu hơn, DBA phải tính toán và cấp đủ dung lượng, cấu hình autoextend có giới hạn hợp lý, giám sát tăng trưởng và chuẩn bị xử lý khi không gian gần cạn.

### 3.4. Kiểm tra retention của undo tablespace

    SELECT
        tablespace_name,
        contents,
        status,
        retention
    FROM dba_tablespaces
    WHERE contents = 'UNDO';

Cột RETENTION cho biết tablespace đang dùng GUARANTEE hay NOGUARANTEE. Cần có quyền đọc data dictionary phù hợp.

## 4. Dung lượng undo quyết định thời gian lưu lịch sử

Một undo tablespace chỉ chứa được một lượng undo hữu hạn. Thời gian giữ được undo phụ thuộc chủ yếu vào:

- Kích thước undo tablespace có thể sử dụng.
- Tốc độ phát sinh undo của workload.
- Thời gian retention mục tiêu.
- Transaction đang chạy và lượng undo mà chúng đang sử dụng.
- Khả năng autoextend và giới hạn MAXSIZE.
- RETENTION GUARANTEE hay NOGUARANTEE.
- Mức tăng tải đột biến, batch job và các thao tác DML lớn.

Nếu ứng dụng ghi dữ liệu với tốc độ cao, cùng một undo tablespace sẽ lưu được lịch sử trong thời gian ngắn hơn. Nếu workload ít ghi, cùng dung lượng có thể giữ được undo lâu hơn.

### 4.1. Ước lượng dung lượng theo undo generation rate

Một phép ước lượng ban đầu:

\[
UndoSpace \approx UndoGenerationRate \times RetentionDuration
\]

Trong đó:

- UndoGenerationRate là lượng undo phát sinh trung bình hoặc ở mức tải cao, tính theo byte/giây.
- RetentionDuration là số giây lịch sử muốn giữ.

Ví dụ, nếu hệ thống phát sinh khoảng 2 MB undo mỗi giây và muốn giữ undo trong 3.600 giây:

\[
2\ MB/s \times 3600\ s = 7200\ MB
\]

Kết quả khoảng 7,2 GB chỉ là lượng undo phát sinh lý thuyết trong cửa sổ đó. Capacity thực tế cần thêm headroom cho transaction dài, biến động tải, metadata và các điều kiện vận hành. Hãy dùng peak hoặc percentile phù hợp từ workload thật thay vì chỉ dùng trung bình ngày.

### 4.2. Lấy undo generation rate từ V$UNDOSTAT

V$UNDOSTAT cung cấp thống kê undo theo các khoảng thời gian, thường là bucket 10 phút. UNDOBLKS là số block undo được sử dụng trong khoảng đó. Có thể kết hợp DB_BLOCK_SIZE và độ dài bucket để ước lượng tốc độ phát sinh undo.

    SELECT
        begin_time,
        end_time,
        undoblks,
        ROUND(
            undoblks * TO_NUMBER(p.value)
            / NULLIF((end_time - begin_time) * 86400, 0)
        ) AS undo_bytes_per_second,
        maxquerylen,
        tuned_undoretention,
        ssolderrcnt,
        nospaceerrcnt,
        unxpstealcnt
    FROM v$undostat
    CROSS JOIN (
        SELECT value
        FROM v$parameter
        WHERE name = 'db_block_size'
    ) p
    ORDER BY begin_time DESC;

Khi đánh giá capacity, hãy lọc khoảng thời gian đại diện cho tải cao, ví dụ giờ cao điểm, batch window hoặc ngày có lượng giao dịch lớn. Một ngày tải thấp có thể không phản ánh được dung lượng cần thiết cho cuối tháng hoặc mùa cao điểm.

### 4.3. Xem dung lượng datafile của undo tablespace

    SELECT
        df.tablespace_name,
        ROUND(SUM(df.bytes) / 1024 / 1024) AS allocated_mb,
        ROUND(SUM(
            CASE
                WHEN df.autoextensible = 'YES' THEN df.maxbytes
                ELSE df.bytes
            END
        ) / 1024 / 1024) AS max_possible_mb
    FROM dba_data_files df
    JOIN dba_tablespaces ts
      ON ts.tablespace_name = df.tablespace_name
    WHERE ts.contents = 'UNDO'
    GROUP BY df.tablespace_name;

Allocated_mb là dung lượng datafile đã cấp phát hiện tại. Max_possible_mb là giới hạn tối đa theo cấu hình autoextend của các datafile; giá trị này không có nghĩa storage vật lý chắc chắn còn đủ chỗ để mở rộng đến mức đó.

Để xem từng datafile:

    SELECT
        tablespace_name,
        file_name,
        ROUND(bytes / 1024 / 1024) AS size_mb,
        autoextensible,
        ROUND(maxbytes / 1024 / 1024) AS max_size_mb
    FROM dba_data_files
    WHERE tablespace_name = (
        SELECT value
        FROM v$parameter
        WHERE name = 'undo_tablespace'
    )
    ORDER BY file_name;

## 5. Theo dõi undo retention và dấu hiệu thiếu undo

Không nên chỉ nhìn giá trị UNDO_RETENTION. Cần theo dõi dữ liệu runtime để biết Oracle thực sự giữ được bao lâu và có đang gặp áp lực không gian hay không.

### 5.1. Các chỉ số quan trọng trong V$UNDOSTAT

| Chỉ số | Ý nghĩa |
|---|---|
| BEGIN_TIME / END_TIME | Khoảng thời gian của bucket thống kê |
| UNDOBLKS | Số block undo được sử dụng trong bucket |
| TXNCOUNT | Số transaction được ghi nhận trong bucket |
| MAXQUERYLEN | Thời lượng truy vấn dài nhất trong bucket, tính bằng giây |
| TUNED_UNDORETENTION | Retention Oracle đã tune, tính bằng giây |
| SSOLDERRCNT | Số lỗi ORA-01555 được ghi nhận trong bucket |
| NOSPACEERRCNT | Số lỗi không cấp phát được undo space trong bucket |
| UNXPSTEALCNT | Số lần Oracle cố lấy lại extent undo chưa hết retention |
| EXPSTEALCNT | Số lần lấy lại extent undo đã hết retention |

Các bộ đếm thường được ghi nhận theo bucket. Hãy quan sát xu hướng qua nhiều bucket thay vì kết luận từ một dòng thống kê riêng lẻ.

### 5.2. Truy vấn lịch sử gần đây

    SELECT *
    FROM (
        SELECT
            begin_time,
            end_time,
            undoblks,
            txncount,
            maxquerylen,
            tuned_undoretention,
            ssolderrcnt,
            nospaceerrcnt,
            unxpstealcnt
        FROM v$undostat
        ORDER BY begin_time DESC
    )
    WHERE ROWNUM <= 24;

Truy vấn trên hiển thị tối đa 24 bucket gần nhất. Với bucket 10 phút, đây thường tương đương khoảng bốn giờ gần đây, nhưng khoảng thời gian thực tế phụ thuộc dữ liệu thống kê đang có.

### 5.3. Đọc các chỉ số cùng nhau

- TUNED_UNDORETENTION thấp hơn thời gian truy vấn dài nhất cần hỗ trợ là dấu hiệu cần điều tra. Có thể thiếu dung lượng hoặc workload phát sinh undo quá nhanh.
- SSOLDERRCNT lớn hơn 0 cho thấy đã có lỗi snapshot too old trong bucket. Cần ghép với thời điểm, SQL ID và log ứng dụng để xác định câu truy vấn liên quan.
- NOSPACEERRCNT lớn hơn 0 cho thấy có vấn đề cấp phát undo do thiếu không gian.
- UNXPSTEALCNT tăng cho thấy Oracle đã phải cố lấy lại extent undo chưa hết retention. Trong NOGUARANTEE, đây là tín hiệu cần xem xét áp lực dung lượng và khả năng ảnh hưởng đến truy vấn lịch sử.
- UNDOBLKS tăng mạnh trong các bucket tải cao cho thấy tốc độ phát sinh undo tăng; cần tính lại capacity theo workload đó.

Không nên dùng một chỉ số riêng lẻ để tự động tăng UNDO_RETENTION. Nếu undo generation rate tăng gấp đôi, chỉ tăng retention mà không tăng dung lượng có thể làm tablespace nhanh đầy hơn.

## 6. Flashback Query và giới hạn từ undo

Flashback Query cho phép truy vấn dữ liệu như thể câu SQL được thực hiện ở một thời điểm hoặc SCN trước đó. Oracle dùng undo data để dựng lại phiên bản hàng dữ liệu tương ứng.

Ví dụ xem trạng thái tài khoản tại thời điểm 30 phút trước:

    SELECT account_id, balance
    FROM accounts AS OF TIMESTAMP
        (SYSTIMESTAMP - INTERVAL '30' MINUTE)
    WHERE account_id = 1001;

Có thể truy vấn theo SCN:

    SELECT account_id, balance
    FROM accounts AS OF SCN 123456789
    WHERE account_id = 1001;

SCN là System Change Number, mốc logic Oracle dùng để xác định thứ tự thay đổi database. Khi cần tái hiện chính xác một giao dịch hoặc điều tra sự cố, SCN thường là mốc rõ ràng hơn timestamp vì tránh sự mơ hồ do chuyển đổi thời gian.

### 6.1. Truy vấn nhiều phiên bản hàng

Flashback Versions Query cho phép xem các phiên bản của hàng trong một khoảng SCN hoặc thời gian:

    SELECT
        versions_startscn,
        versions_endscn,
        versions_operation,
        versions_xid,
        account_id,
        balance
    FROM accounts
         VERSIONS BETWEEN SCN 123450000 AND 123456789
    WHERE account_id = 1001
    ORDER BY versions_startscn;

Các pseudocolumn VERSIONS_STARTSCN, VERSIONS_ENDSCN, VERSIONS_OPERATION và VERSIONS_XID giúp xác định phiên bản, thao tác và transaction liên quan. Giá trị NULL ở một số cột có thể xuất hiện tùy loại phiên bản hoặc ranh giới truy vấn.

### 6.2. Flashback Table

Flashback Table có thể đưa một hoặc nhiều bảng trở lại trạng thái tại một thời điểm trong quá khứ. Nó cũng dựa trên undo và chịu giới hạn bởi lịch sử undo còn có thể sử dụng.

Ví dụ:

    ALTER TABLE accounts ENABLE ROW MOVEMENT;

    FLASHBACK TABLE accounts
    TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '30' MINUTE);

ROW MOVEMENT cần được bật cho bảng theo yêu cầu của Flashback Table. Lệnh có thể làm thay đổi dữ liệu hiện tại và ảnh hưởng đến các thao tác ứng dụng; phải xác định chính xác bảng, thời điểm và tác động trước khi thực hiện. Flashback Table có các giới hạn về DDL, quan hệ ràng buộc và một số loại đối tượng; cần xem tài liệu phiên bản Oracle đang dùng.

### 6.3. ORA-01555: snapshot too old

ORA-01555 xuất hiện khi Oracle không còn undo cần thiết để dựng lại phiên bản dữ liệu nhất quán mà truy vấn yêu cầu. Trong ngữ cảnh Flashback Query, điều này thường có nghĩa thời điểm cần truy vấn đã vượt quá lịch sử undo còn sẵn có hoặc undo cần thiết đã bị tái sử dụng.

Các nguyên nhân thường gặp:

- Truy vấn chạy quá lâu trong khi workload khác tạo nhiều undo.
- Undo tablespace nhỏ so với tốc độ phát sinh undo.
- UNDO_RETENTION thấp so với thời gian truy vấn hoặc khoảng lịch sử cần đọc.
- RETENTION đang ở NOGUARANTEE và Oracle phải tái sử dụng undo chưa hết thời gian retention.
- Một số thao tác DML lớn tạo ra lượng undo đột biến.

Hướng xử lý cần dựa trên bằng chứng:

1. Xác định SQL, thời điểm lỗi và thời lượng truy vấn.
2. Đối chiếu MAXQUERYLEN, TUNED_UNDORETENTION và SSOLDERRCNT trong V$UNDOSTAT.
3. Đo tốc độ phát sinh undo ở đúng khoảng tải xảy ra lỗi.
4. Kiểm tra kích thước undo tablespace, autoextend, MAXSIZE và tình trạng storage.
5. Tối ưu truy vấn hoặc chia nhỏ công việc nếu có thể.
6. Điều chỉnh retention và dung lượng sau khi tính toán lại capacity.
7. Chỉ bật RETENTION GUARANTEE khi hệ thống có đủ dung lượng và chấp nhận rủi ro DML bị chặn khi undo tablespace đầy.

Không nên coi việc tăng UNDO_RETENTION đơn lẻ là cách chữa ORA-01555. Nếu dung lượng không đổi và workload liên tục tạo undo, Oracle có thể không giữ được thời gian dài hơn trong chế độ NOGUARANTEE.

## 7. Flashback Database có cửa sổ lịch sử riêng

Flashback Database đưa toàn bộ database về một thời điểm trong quá khứ bằng cách sử dụng flashback logs. Flashback logs được lưu trong Fast Recovery Area và khác với undo data trong undo tablespace.

Tham số DB_FLASHBACK_RETENTION_TARGET đặt mục tiêu giữ flashback logs, tính bằng phút. Giá trị 1.440 phút tương đương 24 giờ.

    SHOW PARAMETER db_flashback_retention_target;

    ALTER SYSTEM SET db_flashback_retention_target = 1440 SCOPE = BOTH;

Đây là cửa sổ mục tiêu. Thời gian thực tế có thể ngắn hơn nếu FRA thiếu dung lượng hoặc database không thể giữ đủ flashback logs. Cấu hình retention target lớn hơn không tự động cấp thêm storage.

### 7.1. Điều kiện sử dụng Flashback Database

Các điều kiện triển khai thường gồm:

- Database chạy ở ARCHIVELOG mode.
- Flashback Database được bật.
- FRA được cấu hình với dung lượng phù hợp.
- Có đủ quyền và quy trình vận hành để thực hiện Flashback Database.
- Đã đánh giá ảnh hưởng tới Data Guard, RAC và các cấu hình database liên quan nếu có.

Kiểm tra trạng thái:

    SELECT
        log_mode,
        flashback_on,
        open_mode,
        database_role
    FROM v$database;

Kiểm tra FRA:

    SELECT
        name,
        space_limit,
        space_used,
        space_reclaimable,
        number_of_files
    FROM v$recovery_file_dest;

Bật Flashback Database thường cần đưa database về trạng thái MOUNT theo quy trình DBA:

    SHUTDOWN IMMEDIATE;
    STARTUP MOUNT;
    ALTER DATABASE FLASHBACK ON;
    ALTER DATABASE OPEN;

Cần xác minh cấu hình ARCHIVELOG và FRA trước khi bật. Với RAC hoặc Data Guard, thao tác phải tuân theo quy trình riêng của kiến trúc đó.

### 7.2. Kiểm tra flashback logs đang có

    SELECT
        oldest_flashback_scn,
        oldest_flashback_time,
        retention_target,
        flashback_size,
        estimated_flashback_size
    FROM v$flashback_database_log;

OLDEST_FLASHBACK_TIME và OLDEST_FLASHBACK_SCN cho biết mốc lịch sử cũ nhất hiện còn được hỗ trợ theo thông tin flashback log. Đây là dữ liệu quan trọng để đánh giá khả năng quay về một thời điểm cụ thể; không nên chỉ dựa vào DB_FLASHBACK_RETENTION_TARGET.

### 7.3. Flashback Database và undo retention khác nhau

| Đặc điểm | Flashback Query/Table | Flashback Database |
|---|---|---|
| Dữ liệu lịch sử sử dụng | Undo data | Flashback logs |
| Khu vực lưu trữ | Undo tablespace | Fast Recovery Area |
| Tham số retention chính | UNDO_RETENTION | DB_FLASHBACK_RETENTION_TARGET |
| Phạm vi | Truy vấn hoặc đưa bảng về trạng thái cũ | Đưa toàn bộ database về thời điểm cũ |
| Rủi ro khi thiếu dung lượng | Undo bị tái sử dụng hoặc DML không cấp phát được nếu guarantee | Cửa sổ flashback thực tế bị thu hẹp; guaranteed restore point có thể giữ log và làm FRA đầy |

Một hệ thống có thể hỗ trợ Flashback Database trong 24 giờ nhưng Flashback Query chỉ đọc được một khoảng undo ngắn hơn. Ngược lại, undo có thể giữ đủ lịch sử cho Flashback Query nhưng Flashback Database chưa được bật hoặc không có flashback logs phù hợp.

## 8. Guaranteed restore point và áp lực lên FRA

Restore point là mốc SCN có tên để tham chiếu trong quá trình Flashback Database hoặc phục hồi. Guaranteed restore point yêu cầu Oracle giữ đủ flashback logs để có thể quay về mốc đó, miễn các điều kiện cần thiết vẫn đáp ứng.

Tạo guaranteed restore point:

    CREATE RESTORE POINT before_release
    GUARANTEE FLASHBACK DATABASE;

Xem restore point:

    SELECT
        name,
        scn,
        time,
        guarantee_flashback_database,
        storage_size
    FROM v$restore_point
    ORDER BY time DESC;

Khi không còn cần mốc này, xóa restore point:

    DROP RESTORE POINT before_release;

Guaranteed restore point có thể khiến flashback logs được giữ lại ngay cả khi FRA chịu áp lực. Nếu không giám sát, FRA có thể đầy; database có thể không tiếp tục ghi các file recovery cần thiết và hoạt động database có thể bị ảnh hưởng nghiêm trọng.

Vì vậy:

- Chỉ tạo guaranteed restore point khi có kế hoạch rõ ràng và thời hạn sử dụng.
- Ghi nhận người chịu trách nhiệm và thời điểm phải xóa restore point.
- Theo dõi FRA space limit, space used và tốc độ tăng trưởng flashback logs.
- Xác minh storage còn đủ dung lượng cho archived log, backup và các file recovery khác.
- Xóa restore point sau khi thay đổi hoặc nâng cấp đã được xác nhận ổn định.

Guaranteed restore point bảo vệ khả năng Flashback Database tới một mốc cụ thể; nó không kéo dài undo retention cho Flashback Query.

## 9. Flashback Data Archive: lưu lịch sử dài hạn

Flashback Data Archive (FDA), còn được gọi là Oracle Total Recall trong một số tài liệu, cho phép lưu lịch sử thay đổi của các bảng được cấu hình trong một archive. Dữ liệu lịch sử được lưu trong các bảng history do Oracle quản lý và có retention policy riêng.

FDA hữu ích khi nghiệp vụ cần tra cứu lịch sử hàng trong thời gian dài hơn cửa sổ undo thông thường, chẳng hạn cần xem lại trạng thái hồ sơ, hợp đồng hoặc dữ liệu tài chính tại thời điểm trước đó.

Các điểm cần phân biệt:

- FDA không biến UNDO_RETENTION thành thời gian lưu lịch sử dài hạn.
- FDA không phải Flashback Database và không đưa toàn bộ database về trạng thái cũ.
- Chỉ các bảng được cấu hình archive mới có lịch sử theo chính sách FDA.
- Retention của FDA được quản lý riêng, cùng với dung lượng tablespace và quy trình dọn lịch sử.
- FDA không thay thế RMAN backup hoặc yêu cầu bảo vệ dữ liệu ở cấp database.

Ví dụ cấu hình khái quát:

    CREATE FLASHBACK ARCHIVE app_history
    TABLESPACE history_ts
    RETENTION 5 YEAR;

    ALTER TABLE employee
    FLASHBACK ARCHIVE app_history;

Tên tablespace và thời gian retention cần phù hợp với phiên bản, quyền và chính sách lưu trữ. Tạo archive và bật archive cho bảng cần được DBA triển khai, giám sát dung lượng, quyền truy cập và yêu cầu bảo mật.

Sau khi bật FDA, có thể sử dụng các truy vấn Flashback Query trên bảng được archive để tra cứu lịch sử trong phạm vi retention của archive. Cần kiểm tra các giới hạn của loại bảng, DDL và tính năng Oracle đang sử dụng.

## 10. Các giới hạn khác ảnh hưởng đến khả năng flashback

Ngay cả khi thời gian retention có vẻ đủ, một thao tác Flashback cụ thể vẫn có thể không thực hiện được. Cần xem xét thêm các yếu tố sau.

### 10.1. DDL và thay đổi cấu trúc bảng

Một số thay đổi cấu trúc như DROP, TRUNCATE hoặc thay đổi kiểu dữ liệu có thể ảnh hưởng đến khả năng Flashback Query/Table. Không phải mọi thay đổi đều có thể được đảo ngược bằng undo thông thường.

Trước khi triển khai DDL quan trọng, cần có backup, restore point hoặc phương án phục hồi phù hợp. Nếu cần lịch sử nghiệp vụ dài hạn, cân nhắc FDA thay vì giả định undo sẽ giữ được dữ liệu qua mọi thay đổi cấu trúc.

### 10.2. Quyền truy cập

Flashback Query, Flashback Table, Flashback Database và Flashback Data Archive có yêu cầu quyền khác nhau. Người dùng cần quyền phù hợp trên đối tượng hoặc quyền hệ thống do DBA cấp. Không cấp quyền SYSDBA cho tài khoản ứng dụng chỉ để truy vấn dữ liệu lịch sử.

### 10.3. SCN, timestamp và incarnation

Timestamp cần được chuyển đổi sang SCN theo cách phù hợp khi thao tác yêu cầu. Một thời điểm có thể không có snapshot tương ứng trong phạm vi undo còn tồn tại. Sau một số thao tác recovery và OPEN RESETLOGS, database có thể chuyển sang incarnation mới; việc chọn mốc và backup cần tính đến incarnation.

Khi điều tra sự cố, nên ghi nhận SCN, timestamp có timezone, DBID và incarnation để tránh nhầm lẫn giữa các giai đoạn của database.

### 10.4. Transaction dài và workload ghi lớn

Một transaction dài có thể giữ lượng undo đáng kể. Các batch UPDATE/DELETE lớn có thể tạo ra đỉnh undo generation và làm giảm thời gian lịch sử có thể giữ. Không chỉ số lượng session mà loại thao tác DML và thời gian transaction mới quyết định mức tiêu thụ undo.

### 10.5. Các bảng và tính năng có giới hạn riêng

Một số kiểu dữ liệu, bảng, đối tượng hoặc tính năng database có hạn chế khi sử dụng Flashback. Cần kiểm tra tài liệu Oracle cho phiên bản cụ thể trước khi thiết kế ứng dụng phụ thuộc vào lịch sử flashback. Không nên giả định mọi bảng đều hỗ trợ mọi loại Flashback giống nhau.

## 11. Quy trình xác định vì sao không thể flashback đủ xa

Khi người dùng báo rằng truy vấn AS OF TIMESTAMP hoặc thao tác Flashback không thể quay về thời điểm mong muốn, hãy điều tra theo thứ tự:

1. **Xác định loại Flashback**: Flashback Query, Flashback Table, Flashback Database hay Flashback Data Archive.
2. **Xác định mốc thời gian/SCN**: thời điểm cần quay về, timezone, SCN nếu có và database incarnation.
3. **Kiểm tra trạng thái tính năng**: tham số, quyền, archive mode, flashback_on và cấu hình tablespace.
4. **Đọc số liệu retention thực tế**: TUNED_UNDORETENTION, OLDEST_FLASHBACK_TIME, thời lượng truy vấn và các bộ đếm lỗi.
5. **Kiểm tra dung lượng**: undo tablespace, autoextend/MAXSIZE, FRA và storage vật lý.
6. **Xác định workload**: tốc độ undo generation, transaction dài, batch job, DML lớn và thời điểm tải cao.
7. **Chọn cách xử lý**: tối ưu truy vấn, tăng dung lượng, điều chỉnh retention, thay đổi guarantee hoặc dùng FDA/Flashback Database phù hợp với yêu cầu.
8. **Kiểm thử**: chạy thao tác trong môi trường kiểm thử hoặc theo quy trình được phê duyệt, sau đó xác nhận dữ liệu và hiệu năng.

Không nên thay đổi retention guarantee hoặc xóa restore point chỉ để giải phóng dung lượng mà chưa đánh giá tác động tới khả năng phục hồi. Đó là những thay đổi có thể làm mất cửa sổ lịch sử mà hệ thống đang dựa vào.

## 12. Ví dụ capacity planning cho undo retention

Một ứng dụng cần hỗ trợ truy vấn lịch sử trong 60 phút. Qua thống kê ở giờ cao điểm, DBA đo được tốc độ phát sinh undo ở mức cao khoảng 1,5 MB/giây. Ước lượng sơ bộ:

\[
1.5\ MB/s \times 3600\ s = 5400\ MB
\]

Tức khoảng 5,4 GB undo được phát sinh trong một giờ ở mức tải đo được. Nhóm vận hành cần bổ sung headroom cho dao động tải, transaction dài và các hoạt động đồng thời. Nếu chọn hệ số dự phòng 1,3 trong mô hình nội bộ, dung lượng sơ bộ là:

\[
5400\ MB \times 1.3 = 7020\ MB
\]

Khoảng 7 GB là điểm bắt đầu để kiểm thử capacity, không phải giá trị cấu hình mặc định. Cần kiểm tra peak cao hơn, giới hạn storage, số transaction đồng thời và kết quả V$UNDOSTAT sau khi triển khai.

Nếu database dùng NOGUARANTEE, Oracle vẫn có thể tái sử dụng undo chưa hết retention khi thiếu chỗ. Nếu nghiệp vụ yêu cầu bảo đảm lịch sử trong cửa sổ 60 phút, DBA có thể đánh giá RETENTION GUARANTEE sau khi chứng minh tablespace có đủ dung lượng và có cảnh báo trước khi đầy. Khi guarantee được bật, rủi ro DML lỗi do hết undo space phải được chấp nhận và kiểm soát.

Đối với Flashback Database, nhóm cần lập một capacity plan riêng cho FRA dựa trên flashback log generation rate, DB_FLASHBACK_RETENTION_TARGET, backup và archived log. Không lấy con số 7 GB undo ở ví dụ này làm dung lượng FRA.

## 13. Giám sát và cảnh báo

Nên có cảnh báo theo từng lớp:

| Lớp | Chỉ số | Dấu hiệu cần điều tra |
|---|---|---|
| Undo retention | TUNED_UNDORETENTION | Thấp hơn cửa sổ truy vấn lịch sử cần hỗ trợ |
| Query | MAXQUERYLEN, SSOLDERRCNT | Query dài, lỗi snapshot too old |
| Undo capacity | UNDOBLKS, NOSPACEERRCNT, UNXPSTEALCNT | Undo generation tăng, thiếu chỗ hoặc phải tái sử dụng undo chưa hết retention |
| Undo storage | Allocated size, autoextend, MAXSIZE, storage free | Tablespace gần giới hạn hoặc không thể mở rộng |
| Flashback Database | OLDEST_FLASHBACK_TIME, FLASHBACK_SIZE | Mốc flashback cũ nhất gần hơn mục tiêu nghiệp vụ |
| FRA | SPACE_USED, SPACE_RECLAIMABLE, SPACE_LIMIT | FRA gần đầy hoặc tăng trưởng bất thường |
| Restore point | Guaranteed restore point và STORAGE_SIZE | Restore point tồn tại quá thời hạn dự kiến |

Cảnh báo cần dựa trên SLA thực tế. Nếu nghiệp vụ cần tra cứu 24 giờ, chỉ báo khi undo retention còn 30 phút là quá muộn. Nên đặt ngưỡng sớm đủ để DBA có thời gian tăng dung lượng hoặc giảm tải trước khi lịch sử bị mất.

## 14. Nguyên tắc vận hành

- UNDO_RETENTION là thời gian mục tiêu, không mặc nhiên là cam kết lưu lịch sử.
- TUNED_UNDORETENTION và V$UNDOSTAT phản ánh khả năng giữ undo thực tế; hãy theo dõi cùng dung lượng và workload.
- NOGUARANTEE cho phép tái sử dụng undo chưa hết retention khi thiếu chỗ; RETENTION GUARANTEE bảo vệ undo đó nhưng có thể khiến DML thất bại nếu tablespace đầy.
- Flashback Query và Flashback Table dựa trên undo, vì vậy thường bị giới hạn bởi thời gian undo còn sẵn có.
- Flashback Database dựa trên flashback logs trong FRA và có retention target riêng.
- Flashback Data Archive giữ lịch sử bảng theo policy riêng, phù hợp với nhu cầu lịch sử dài hạn cho các bảng được cấu hình.
- Tăng retention mà không tính lại dung lượng có thể làm tăng áp lực undo hoặc FRA.
- Không dùng trạng thái backup RMAN để kết luận Flashback Query hay Flashback Database chắc chắn hoạt động.
- Phải kiểm thử thao tác flashback trên môi trường phù hợp và xác nhận dữ liệu sau khi thực hiện.

Khả năng flashback là kết quả của cơ chế lưu lịch sử, dung lượng, workload và cấu hình retention phối hợp với nhau. Khi thiết kế, hãy xác định rõ nghiệp vụ cần xem lại một hàng, phục hồi một bảng hay đưa toàn bộ database về thời điểm cũ; sau đó chọn đúng cơ chế, đo tốc độ phát sinh lịch sử và bảo đảm storage đủ cho cửa sổ cần hỗ trợ.
