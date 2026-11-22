# Lỗi checksum, nghi ngờ hỏng dữ liệu và bảo toàn bằng chứng

Checksum là một cơ chế giúp PostgreSQL phát hiện một số dạng hỏng dữ liệu ở cấp page. Khi PostgreSQL báo checksum không khớp, xuất hiện lỗi đọc page hoặc có dấu hiệu dữ liệu không nhất quán, việc đầu tiên là bảo toàn trạng thái và bằng chứng để có thể xác định phạm vi sự cố. Một thao tác sửa chữa vội vàng có thể ghi đè page lỗi, thay đổi WAL, làm mất dấu thời điểm phát sinh hoặc khiến bản sao duy nhất còn đọc được trở nên không thể phục hồi.

Bài học này trình bày cách nhận diện cảnh báo checksum, thu thập thông tin về relation và block, kiểm tra cluster và backup, phân biệt lỗi page với lỗi index hoặc lỗi logic, rồi lựa chọn phục hồi từ bản sao an toàn. Các ví dụ giả định PostgreSQL chạy trên máy chủ do đội vận hành quản lý; đường dẫn, quyền hệ điều hành và lệnh cụ thể cần điều chỉnh theo phiên bản và nền tảng thực tế.

## 1. Phân biệt checksum, hỏng page và hỏng dữ liệu logic

PostgreSQL lưu dữ liệu trong các page có kích thước cố định, thông thường 8 KB. Table, index và nhiều đối tượng lưu trữ khác được tổ chức thành các page nằm trong các relation file. Khi bật data checksums, PostgreSQL tính checksum cho page dữ liệu và kiểm tra giá trị đó khi đọc page từ storage.

Checksum giúp phát hiện một số thay đổi ngoài dự kiến ở nội dung page. Nó không phải bản sao dữ liệu, không sửa được page và cũng không chứng minh toàn bộ database còn nguyên vẹn. Một cluster có checksum vẫn có thể gặp lỗi logic của ứng dụng, mất dữ liệu do thao tác nhầm, index không nhất quán, lỗi WAL hoặc hỏng dữ liệu ở nơi không được cơ chế checksum đó bao phủ.

Cần phân biệt các loại vấn đề sau:

| Loại vấn đề | Biểu hiện thường gặp | Cơ chế kiểm tra phù hợp |
|---|---|---|
| Data page checksum mismatch | PostgreSQL báo checksum tính lại khác checksum lưu trong page | Log server, pg_stat_database nếu phiên bản hỗ trợ, pg_checksums khi cluster offline |
| Page hỏng về cấu trúc | Page header, tuple hoặc page layout không hợp lệ | Log, công cụ kiểm tra page chuyên biệt, amcheck và phân tích trên bản sao |
| Index không nhất quán | Index trỏ tới tuple không hợp lệ, lỗi tìm kiếm hoặc lỗi amcheck | Extension amcheck; so sánh index với heap |
| WAL hoặc backup không hợp lệ | Recovery thất bại, thiếu WAL hoặc file backup không khớp manifest | Log recovery, pg_verifybackup, kiểm tra WAL và quy trình restore |
| Dữ liệu logic sai | Giá trị sai nhưng page và checksum hợp lệ | Kiểm tra nghiệp vụ, constraint, audit và lịch sử thay đổi |
| Hư hỏng storage/hệ điều hành | Lỗi I/O, reset thiết bị, lỗi filesystem hoặc kernel | Log hệ điều hành, công cụ storage và chẩn đoán phần cứng |

Một checksum mismatch cho biết page được đọc không khớp với giá trị checksum đã lưu. Nó là bằng chứng cần điều tra, nhưng chưa tự xác định nguyên nhân. Có thể liên quan đến thiết bị lưu trữ, controller, RAM, cache, filesystem, mất điện, lỗi phần mềm, lỗi khi sao chép file hoặc một thành phần khác trong đường dữ liệu.

Nếu checksum không được bật khi khởi tạo cluster, PostgreSQL không thể dùng data page checksum để phát hiện các sai lệch tương ứng. Việc truy vấn vẫn chạy thành công không chứng minh dữ liệu chưa từng bị hỏng.

## 2. Nhận diện dấu hiệu sự cố

Các dấu hiệu cần được ghi nhận gồm:

- Log PostgreSQL báo page verification failed hoặc checksum mismatch.
- Lỗi invalid page, invalid page header hoặc lỗi đọc block của relation.
- Backend báo lỗi I/O, unexpected zero page hoặc dữ liệu không giải mã được.
- PostgreSQL không thể đọc một bảng, index hoặc relation cụ thể.
- Recovery sau crash thất bại hoặc báo lỗi khi đọc WAL.
- Replica hoặc backup job xuất hiện lỗi đọc page, checksum hay WAL.
- Hệ điều hành ghi nhận I/O error, filesystem error, controller reset hoặc thiết bị lưu trữ bị timeout.
- Ứng dụng nhận kết quả khác thường, lỗi giải mã dữ liệu hoặc constraint thất bại trên một tập dữ liệu cụ thể.

Ví dụ thông báo có thể có dạng:

~~~text
WARNING:  page verification failed, calculated checksum ...
          but expected ...
ERROR:    invalid page in block 42 of relation base/16384/2619
~~~

Câu chữ cụ thể thay đổi theo phiên bản, ngữ cảnh và loại lỗi. Hãy lưu nguyên văn log, timestamp, process ID, database, user, client và đường dẫn relation nếu có. Không chỉ chép phần thông báo cuối cùng vì các dòng trước đó có thể chứa nguyên nhân gốc như lỗi I/O hoặc lỗi recovery.

Một lỗi xuất hiện một lần vẫn cần được điều tra. Nếu cùng block liên tục lỗi trên nhiều lần đọc, nhiều node hoặc nhiều bản sao, mức độ nghiêm trọng và phạm vi ảnh hưởng có thể khác nhau. Không nên kết luận rằng một lỗi đơn lẻ là nhiễu rồi bỏ qua.

## 3. Data checksums trong PostgreSQL

Data checksums được thiết lập ở cấp cluster. Với cluster mới, có thể bật ngay lúc khởi tạo:

~~~bash
initdb --data-checksums -D /var/lib/postgresql/data
~~~

Đường dẫn ở ví dụ chỉ mang tính minh họa. Khi khởi tạo bằng công cụ quản lý dịch vụ, container image hoặc nền tảng cloud, hãy dùng cơ chế cấu hình tương ứng.

Có thể xem trạng thái checksum từ SQL:

~~~sql
SHOW data_checksums;
~~~

Hoặc dùng công cụ đọc control file:

~~~bash
pg_controldata /var/lib/postgresql/data
~~~

Trong kết quả pg_controldata, tìm trường Data page checksum version. Giá trị 0 thường cho biết cluster không bật data checksums; giá trị khác 0 biểu thị phiên bản checksum được sử dụng. Cần đối chiếu với tài liệu của major version đang chạy.

Data checksums có một số giới hạn quan trọng:

- Chúng bảo vệ page dữ liệu được kiểm tra theo cơ chế checksum của PostgreSQL.
- Chúng không thay thế checksum của WAL, backup manifest hoặc checksum của hệ thống lưu trữ.
- Chúng không phát hiện mọi lỗi logic trong dữ liệu.
- Chúng không sửa page bị hỏng.
- Chúng không tự khẳng định lỗi nằm ở ổ đĩa; nguyên nhân có thể xuất hiện ở bất kỳ lớp nào trên đường dữ liệu.
- Việc bật checksum sau khi cluster đã tồn tại cần thực hiện theo khả năng của major version và trong điều kiện cluster offline.

Từ PostgreSQL 12, tiện ích pg_checksums có thể kiểm tra cluster hoặc bật/tắt data checksums trên cluster đã dừng sạch, tùy trạng thái và phiên bản. Không chạy công cụ này khi server đang hoạt động. Khi thao tác bật/tắt, hãy làm theo tài liệu đúng major version, kiểm tra trạng thái shutdown và bảo đảm có bản sao lưu đã xác minh.

## 4. Bảo toàn bằng chứng trước khi điều tra sâu

Khi có nghi ngờ hỏng dữ liệu, hãy xem cluster gốc là bằng chứng. Mục tiêu đầu tiên là giữ lại dữ liệu, log, WAL và cấu hình tại thời điểm sự cố.

Một thứ tự xử lý thực tế:

1. Ghi nhận thời điểm phát hiện và người phát hiện; lưu timezone và đồng bộ thời gian của các hệ thống.
2. Xác định dịch vụ, database, relation, block và thao tác đang phát sinh lỗi.
3. Thu thập log PostgreSQL, log hệ điều hành, log storage, monitoring và log ứng dụng.
4. Ghi nhận trạng thái primary, replica, backup, recovery và các job đang chạy.
5. Tạo snapshot hoặc bản sao lưu sự cố theo cơ chế nhất quán được hỗ trợ bởi storage và PostgreSQL.
6. Giữ một bản gốc bất biến, giới hạn quyền truy cập và ghi nhận checksum của các file bằng chứng đã xuất.
7. Thực hiện phân tích và thử phục hồi trên bản sao làm việc riêng.

Không xóa log, WAL hoặc backup cũ trong lúc điều tra. Không thay thế cluster gốc bằng bản restore trước khi đã giữ snapshot hoặc bản sao cần thiết. Không chạy thao tác ghi có khả năng thay đổi page lỗi nếu chưa xác định được cách bảo toàn bằng chứng.

### 4.1. Snapshot khi PostgreSQL đang chạy

Snapshot volume đang được ghi có thể chỉ là crash-consistent. Nó có thể chứa trạng thái tương tự sau mất điện và cần recovery bằng WAL khi mở bản sao. Một snapshot crash-consistent vẫn có giá trị nếu được tạo theo cơ chế storage đã hiểu rõ, nhưng không được xem là bản sao đã kiểm tra và sẵn sàng khôi phục.

Nếu nền tảng hỗ trợ snapshot nhất quán ứng dụng, hãy dùng cơ chế tích hợp với PostgreSQL hoặc quy trình backup được hỗ trợ. Có thể cần phối hợp backup mode, filesystem freeze hoặc dừng dịch vụ tùy công cụ. Không tự áp dụng lệnh freeze hoặc dừng tiến trình khi chưa hiểu ảnh hưởng tới ứng dụng.

Nếu cần dừng sạch để chạy pg_checksums, trước hết hãy bảo toàn bản gốc hoặc snapshot theo quy trình sự cố. Sau đó mới dừng cluster theo cách có kiểm soát và chạy công cụ trên bản sao làm việc. Khi sự cố đang diễn ra, ưu tiên bảo vệ dữ liệu và khả năng phục hồi hơn việc chạy ngay một lệnh kiểm tra offline trên nguồn duy nhất.

### 4.2. Những thứ cần lưu giữ

| Nhóm bằng chứng | Nội dung nên thu thập |
|---|---|
| PostgreSQL log | Log trước, trong và sau thời điểm lỗi; PID; database; role; client; thông báo đầy đủ |
| Control và cấu hình | Phiên bản server; pg_controldata; postgresql.conf; pg_hba.conf; cấu hình include; trạng thái checksum |
| Relation | Schema, tên bảng/index, OID, filenode, đường dẫn file và block bị báo lỗi |
| WAL và recovery | WAL segment liên quan, timeline, checkpoint, trạng thái recovery và log archive |
| Replica | Trạng thái replication, replay LSN, lag và lỗi trên từng node |
| Backup | Backup manifest, thời gian tạo, loại backup, WAL cần thiết và kết quả lần restore gần nhất |
| Hệ điều hành | Kernel log, filesystem log, I/O error, thiết bị reset, SMART hoặc báo cáo từ nhà cung cấp storage |
| Ứng dụng | Request ID, thao tác nghiệp vụ, dữ liệu đầu vào, thời điểm và lỗi trả về |

Bằng chứng có thể chứa dữ liệu cá nhân, câu SQL, tên tài khoản hoặc thông tin kết nối. Lưu trong vùng hạn chế truy cập; che secret khi chia sẻ cho nhóm không cần quyền đọc chúng. Giữ nguyên bản log gốc và tạo bản đã che thông tin riêng cho mục đích trao đổi.

### 4.3. Tạo bản sao phục vụ phân tích

Nếu dùng snapshot block storage, ghi nhận ID snapshot, volume gốc, thời điểm, vùng lưu trữ và trạng thái snapshot. Nếu sao chép file, ghi nhận công cụ, thời điểm, trạng thái server, các file được sao chép và hash của bản sao.

Không tự ý sao chép một data directory đang hoạt động bằng lệnh copy thông thường rồi xem đó là physical backup hợp lệ. File có thể được thay đổi trong khi sao chép, tạo ra một tập dữ liệu không nhất quán. Dùng pg_basebackup, snapshot tích hợp đúng quy trình hoặc công cụ backup được hỗ trợ.

Giữ ít nhất một bản sao chỉ đọc hoặc được bảo vệ khỏi ghi đè. Phân tích trên một bản sao khác để các thử nghiệm, recovery hoặc thao tác sửa chữa không thay đổi bằng chứng gốc.

## 5. Thu thập thông tin từ PostgreSQL

Nếu server còn hoạt động và truy vấn quản trị vẫn chạy được, thu thập thông tin bằng các truy vấn chỉ đọc. Không thực hiện truy vấn rộng hoặc thao tác quét nặng trên hệ thống đang chịu sự cố nếu có thể làm tăng tải.

### 5.1. Phiên bản và cấu hình checksum

~~~sql
SELECT version();

SHOW data_checksums;
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW log_destination;
~~~

Một số giá trị cấu hình có thể bị giới hạn quyền xem hoặc khác nhau trên dịch vụ PostgreSQL được quản lý. Lưu kết quả cùng phiên bản server và thời điểm thu thập.

### 5.2. Thống kê checksum

Trên các phiên bản có các cột thống kê checksum tương ứng, có thể xem:

~~~sql
SELECT
    datname,
    checksum_failures,
    checksum_last_failure
FROM pg_stat_database
ORDER BY checksum_failures DESC NULLS LAST;
~~~

Các cột checksum_failures và checksum_last_failure có mặt trong các phiên bản PostgreSQL hiện đại, nhưng không nên giả định mọi phiên bản cũ đều hỗ trợ. Nếu truy vấn báo không tồn tại cột, ghi nhận phiên bản và dùng log server cùng các công cụ tương ứng.

Bộ đếm này là dữ liệu thống kê của server. Nó không thay thế việc xác định relation và block, cũng không phải bằng chứng duy nhất về phạm vi hư hỏng. Hãy ghi nhận giá trị trước và sau mỗi lần kiểm tra nếu cần xác định sự cố mới phát sinh.

### 5.3. Xác định relation và đường dẫn file

Nếu biết bảng hoặc index bị lỗi, có thể lấy thông tin relation:

~~~sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname,
    c.relkind,
    pg_relation_filenode(c.oid) AS filenode,
    pg_relation_filepath(c.oid) AS relation_path,
    pg_relation_size(c.oid) AS relation_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'orders';
~~~

Một relation lớn có thể được chia thành nhiều segment file. Các fork như main, FSM, VM và init cũng có ý nghĩa riêng. Tên relation path là thông tin định vị file trong data directory, không nên suy luận tên bảng chỉ từ một số filenode đã cũ vì filenode có thể thay đổi sau thao tác DDL hoặc rebuild.

Nếu log cho biết block number, ghi lại đúng block cùng relation path. Không dùng block number của một relation để đọc file của relation khác.

### 5.4. Trạng thái kết nối và replication

Thu thập kết nối đang hoạt động:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start
FROM pg_stat_activity
ORDER BY backend_start;
~~~

Trên primary có thể kiểm tra sender:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Trên standby, kiểm tra trạng thái recovery và receiver bằng các view phù hợp với phiên bản. Lưu ý rằng replication đang hoạt động không chứng minh replica sạch; cần kiểm tra log và backup của từng node độc lập.

## 6. Kiểm tra cluster bằng pg_checksums

pg_checksums là tiện ích offline để kiểm tra checksum của các data page trong cluster. Nó hữu ích khi cần xác định còn bao nhiêu page checksum không khớp trong data directory.

Trước khi chạy, cần:

- Dùng pg_checksums thuộc đúng major version của cluster.
- Xác định chính xác data directory.
- Đảm bảo PostgreSQL đã dừng sạch.
- Bảo toàn snapshot hoặc bản sao gốc.
- Chạy trên bản sao làm việc nếu cluster gốc là bằng chứng duy nhất.
- Có đủ dung lượng và thời gian vì thao tác có thể đọc toàn bộ data files.

Ví dụ kiểm tra:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data
~~~

Lệnh này chỉ là ví dụ. Tùy nền tảng, có thể cần chạy bằng tài khoản hệ điều hành quản lý PostgreSQL hoặc dùng đường dẫn binary đầy đủ. Không chạy trên cluster đang hoạt động.

Kết quả cần lưu nguyên vẹn, bao gồm số block đã kiểm tra, số lỗi, file liên quan, exit code và thời gian chạy. Nếu công cụ báo checksum mismatch, ghi lại file và block tương ứng rồi đối chiếu với log server. Nếu không tìm thấy lỗi, điều đó chỉ cho biết lượt quét này không phát hiện mismatch trong phạm vi nó kiểm tra; nó không chứng minh cluster hoàn toàn không có hỏng dữ liệu logic hoặc lỗi chưa được đọc.

### 6.1. Bật checksum cho cluster hiện có

Một số phiên bản PostgreSQL hỗ trợ pg_checksums để bật checksum cho cluster đã khởi tạo khi server đã dừng sạch và thỏa điều kiện của tiện ích:

~~~bash
pg_checksums --enable -D /var/lib/postgresql/data
~~~

Không dùng thao tác enable như cách sửa lỗi checksum đang tồn tại. Nó chỉ thay đổi trạng thái checksum của cluster theo quy trình được hỗ trợ; không khôi phục nội dung page đã hỏng. Hãy xác minh bản sao lưu, phiên bản và điều kiện cluster trước khi thực hiện.

Tương tự, disable không phải cách xử lý sự cố. Tắt checksum có thể làm mất khả năng phát hiện các page sai lệch trong những lần đọc tiếp theo. Chỉ thay đổi khi có kế hoạch vận hành được phê duyệt và hiểu rõ tác động.

## 7. Kiểm tra backup và WAL

Backup chỉ hữu ích khi có thể khôi phục. Một bản backup có manifest và checksum giúp phát hiện file bị thay đổi hoặc thiếu so với lúc tạo backup.

Với backup được tạo theo định dạng hỗ trợ backup manifest, có thể dùng pg_verifybackup:

~~~bash
pg_verifybackup /backups/basebackup_2026_11_14
~~~

Công cụ cần phiên bản phù hợp với backup và server. Nó đối chiếu các file với backup manifest và thực hiện những kiểm tra WAL mà phiên bản hỗ trợ. Hãy lưu output và exit code. Một backup verify thành công vẫn cần được thử restore trong môi trường cô lập để xác nhận quy trình phục hồi thực tế.

Backup manifest có checksum file riêng, khác với data page checksum của PostgreSQL. Kiểm tra manifest không thay thế pg_checksums trên cluster đang chạy hoặc kiểm tra tính nhất quán logic của dữ liệu.

### 7.1. Giữ WAL cần thiết

WAL cho phép PostgreSQL phục hồi thay đổi sau checkpoint và hỗ trợ point-in-time recovery khi có đủ base backup cùng chuỗi WAL liên tục. Khi nghi ngờ corruption, không xóa hoặc tái sử dụng WAL archive theo chính sách retention thông thường trước khi xác định khoảng thời gian cần điều tra.

Ghi nhận:

- Timeline và checkpoint liên quan.
- Các WAL segment có sẵn trong archive.
- Khoảng thời gian archive bị thiếu hoặc lỗi.
- LSN cuối cùng của primary và replica.
- Log về lỗi ghi, flush, archive hoặc replay WAL.

pg_waldump có thể giúp đọc và phân tích bản ghi WAL trên file hoặc segment phù hợp. Công cụ này dành cho phân tích kỹ thuật; không sửa WAL hoặc tự thay đổi control file. Kết quả cần được diễn giải theo phiên bản và ngữ cảnh transaction.

### 7.2. Restore thử nghiệm

Khôi phục backup vào một máy hoặc data directory riêng. Nếu dùng PITR, chọn thời điểm dừng dựa trên bằng chứng: thời điểm page bắt đầu lỗi, thời điểm thay đổi dữ liệu bất thường hoặc thời điểm thao tác gây sự cố. Không đoán một mốc thời gian chỉ vì backup gần nhất có vẻ hoạt động.

Sau khi restore:

1. Xác nhận PostgreSQL khởi động và recovery hoàn tất.
2. Kiểm tra log server và các lỗi page.
3. Chạy kiểm tra checksum offline khi phù hợp.
4. Kiểm tra index và cấu trúc relation bằng công cụ tương ứng.
5. Chạy truy vấn nghiệp vụ đối chiếu số lượng, tổng hợp và constraint.
6. Xác nhận ứng dụng có thể đọc dữ liệu cần thiết.
7. Lưu kết quả restore và thời điểm dữ liệu được phục hồi.

Chỉ chuyển traffic sang bản phục hồi sau khi có quyết định vận hành và xác nhận dữ liệu đạt yêu cầu.

## 8. Phân biệt lỗi heap, index và dữ liệu logic

Một lỗi khi truy vấn bảng không nhất thiết xuất phát từ heap table. Truy vấn có thể sử dụng index; index bị hỏng có thể làm lỗi xuất hiện trong một kế hoạch truy vấn cụ thể. Ngược lại, heap page hỏng có thể ảnh hưởng nhiều truy vấn khác nhau.

### 8.1. Kiểm tra index bằng amcheck

Extension amcheck cung cấp các hàm kiểm tra tính nhất quán của một số cấu trúc index, đặc biệt là B-tree. Ví dụ, sau khi cài extension trong database kiểm thử hoặc môi trường phù hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

bt_index_check là một kiểm tra cấu trúc index B-tree. Các hàm kiểm tra sâu hơn như bt_index_parent_check có thể kiểm tra thêm quan hệ giữa parent và child page, nhưng có thể tốn tài nguyên và cần khóa mạnh hơn. Hãy đọc tài liệu amcheck đúng phiên bản trước khi chạy trên production.

Nếu nghi ngờ index hỏng, kiểm tra index cụ thể và so sánh với heap trên bản sao. REINDEX có thể xây dựng lại một index bị hỏng khi heap còn đáng tin cậy. Nó không sửa page heap bị hỏng, không phục hồi tuple đã mất và không nên chạy trên cluster gốc trước khi bảo toàn bằng chứng.

### 8.2. Kiểm tra heap

Một số phiên bản PostgreSQL và amcheck cung cấp khả năng kiểm tra heap page. Phạm vi, chữ ký hàm và các tùy chọn phụ thuộc phiên bản. Chỉ dùng sau khi đã kiểm tra tài liệu tương ứng và hiểu tải đọc, lock cùng khả năng báo lỗi của công cụ.

Nếu lỗi xảy ra trên một block cụ thể, có thể cần chuyên gia PostgreSQL phân tích raw page bằng pageinspect hoặc công cụ chuyên biệt trên bản sao. Không tự chỉnh byte của page hoặc cập nhật file relation bằng hex editor.

### 8.3. Kiểm tra dữ liệu logic

Nếu checksum và cấu trúc page đều không có lỗi nhưng ứng dụng phát hiện dữ liệu sai, hãy kiểm tra tầng logic:

- Constraint và foreign key.
- Quy tắc nghiệp vụ và transaction.
- Audit log và lịch sử thay đổi.
- Migration, batch job và thao tác thủ công.
- Đồng bộ giữa primary, replica và hệ thống downstream.
- Dữ liệu đầu vào và cách chuyển đổi kiểu.

Checksum hợp lệ chỉ nói rằng page khớp checksum đã lưu. Một câu lệnh UPDATE hợp lệ nhưng ghi nhầm giá trị vẫn tạo page có checksum hợp lệ.

## 9. Những thao tác cần tránh khi chưa bảo toàn bằng chứng

Một số tùy chọn có thể khiến PostgreSQL tiếp tục hoạt động trong điều kiện có page hỏng, nhưng không phải là công cụ sửa chữa an toàn.

### 9.1. Không bật ignore_checksum_failure để tiếp tục nghiệp vụ

ignore_checksum_failure cho phép PostgreSQL tiếp tục trong một số tình huống checksum failure thay vì dừng truy vấn tương ứng. Điều đó có thể khiến ứng dụng đọc dữ liệu hỏng hoặc trả kết quả không đáng tin cậy. Không dùng nó như biện pháp khắc phục production hoặc để che giấu cảnh báo.

Nếu một chuyên gia cần dùng tùy chọn này để trích xuất dữ liệu khẩn cấp, chỉ thực hiện trên bản sao làm việc, với mục tiêu và phạm vi cụ thể, sau khi đã giữ nguyên nguồn bằng chứng.

### 9.2. Không dùng zero_damaged_pages như thao tác sửa thông thường

zero_damaged_pages có thể cho phép PostgreSQL thay page hỏng bằng page rỗng trong một số đường đọc. Hành vi đó có thể làm mất dữ liệu của page. Đây không phải cách khôi phục nội dung ban đầu và có thể tạo ra mất dữ liệu vĩnh viễn.

Nếu có một quy trình cứu dữ liệu đặc biệt cần thử, phải dùng bản sao riêng, ghi lại chính xác tham số và chấp nhận rằng dữ liệu ở page đó có thể bị loại bỏ. Không áp dụng lên bản gốc duy nhất.

### 9.3. Không chạy pg_resetwal để xử lý checksum mismatch

pg_resetwal dành cho tình huống WAL hoặc control information bị hỏng và chỉ là biện pháp cuối cùng trong một số kịch bản recovery. Nó không sửa checksum của data page. Dùng sai có thể khiến cluster khởi động với trạng thái transaction không nhất quán và làm hỏng thêm dữ liệu.

Không chạy pg_resetwal chỉ vì PostgreSQL báo checksum mismatch hoặc không đọc được một block. Trước khi dùng, cần đánh giá bởi người có kinh nghiệm PostgreSQL, bảo toàn bản sao gốc và hiểu rõ khả năng mất dữ liệu.

### 9.4. Không rebuild hoặc vacuum tùy tiện

VACUUM FULL, CLUSTER, REINDEX, ALTER TABLE rewrite hoặc thao tác ghi lớn có thể đọc và ghi lại nhiều page. Chúng có thể thay đổi bằng chứng, gây thêm tải và làm lỗi lan rộng trong quá trình xử lý.

REINDEX chỉ phù hợp khi đã xác định lỗi nằm ở index và heap đáng tin cậy. Không dùng nó để chữa lỗi heap hoặc storage. Không chạy VACUUM FULL chỉ để thử xem cảnh báo có biến mất hay không.

## 10. Quy trình xử lý sự cố theo giai đoạn

Có thể tổ chức ứng phó thành các giai đoạn sau để mọi người cùng hiểu trạng thái và tránh hành động xung đột.

### Giai đoạn A — Phát hiện và giới hạn ảnh hưởng

- Ghi nhận thông báo lỗi, thời điểm và truy vấn liên quan.
- Xác định database, relation, block, primary/replica và ứng dụng bị ảnh hưởng.
- Hạn chế các thao tác có thể tiếp tục ghi lên vùng nghi ngờ nếu có thể làm an toàn.
- Thông báo cho DBA, SRE và chủ sở hữu ứng dụng theo quy trình sự cố.
- Không xóa log, WAL, backup hoặc tự chạy lệnh sửa chữa.

Việc dừng traffic hoặc chuyển ứng dụng sang read-only phải dựa trên tác động thực tế và quy trình vận hành. Không tự kill toàn bộ backend hoặc tắt máy chủ nếu chưa đánh giá ảnh hưởng đến transaction, recovery và khả năng thu thập bằng chứng.

### Giai đoạn B — Bảo toàn

- Thu thập log, cấu hình, thống kê và metadata relation.
- Lưu WAL và thông tin timeline.
- Snapshot hoặc tạo backup theo cơ chế nhất quán.
- Giữ bản gốc bất biến và tạo bản sao làm việc.
- Ghi nhận hash, nguồn, thời điểm và người thực hiện mỗi lần thu thập.

### Giai đoạn C — Chẩn đoán

- Xác định checksum có được bật hay không.
- Đối chiếu lỗi PostgreSQL với lỗi I/O và log storage.
- Chạy pg_checksums trên cluster đã dừng sạch hoặc bản sao phù hợp.
- Xác minh backup bằng pg_verifybackup và thử restore.
- Dùng amcheck hoặc công cụ chuyên biệt để phân biệt lỗi index, heap và lỗi logic.
- Kiểm tra replica độc lập, không mặc định replica không bị ảnh hưởng.

### Giai đoạn D — Lựa chọn phục hồi

Các phương án thường gặp:

| Tình huống | Hướng xử lý có thể cân nhắc |
|---|---|
| Chỉ index bị hỏng, heap đáng tin cậy | Rebuild index trên bản sao hoặc theo quy trình DBA đã xác nhận |
| Một page heap bị hỏng, có backup và WAL hợp lệ | Restore/PITR sang cluster mới, sau đó đối chiếu dữ liệu |
| Primary có lỗi storage, replica đã xác minh độc lập | Đánh giá failover theo quy trình HA và kiểm tra dữ liệu replica |
| Backup manifest lỗi hoặc thiếu WAL | Tìm bản backup khác và chuỗi WAL đầy đủ; xác định RPO có thể đạt |
| Nhiều page hỏng hoặc cluster không thể recovery | Bảo toàn bản gốc, thử các bản backup/PITR và chuyển chuyên gia xử lý |
| Dữ liệu logic sai nhưng page checksum hợp lệ | Phục hồi theo lịch sử nghiệp vụ, audit hoặc PITR tới trước thao tác sai |

Failover không tự động là cách chữa corruption. Nếu nguyên nhân là lỗi logic hoặc thao tác sai đã được replication truyền sang standby, replica có thể chứa cùng dữ liệu sai. Nếu nguyên nhân là hỏng storage riêng trên một node, replica có thể còn tốt, nhưng vẫn phải kiểm tra độc lập trước khi promote.

### Giai đoạn E — Xác nhận và đóng sự cố

- Khôi phục vào cluster mới hoặc môi trường thay thế.
- Chạy kiểm tra checksum, cấu trúc và nghiệp vụ.
- Xác nhận backup, WAL archive và quy trình restore hoạt động.
- Theo dõi log, replication, latency và lỗi truy vấn sau khi chuyển traffic.
- Ghi lại nguyên nhân đã xác định, tác động, dữ liệu mất (nếu có), hành động phục hồi và biện pháp ngăn tái diễn.
- Giữ bằng chứng theo chính sách lưu trữ và yêu cầu điều tra.

## 11. Ma trận bằng chứng và quyết định

Bảng sau giúp đội vận hành ghi lại căn cứ trước khi chọn phương án:

| Bằng chứng | Câu hỏi cần trả lời | Ý nghĩa đối với quyết định |
|---|---|---|
| Checksum mismatch ở block | Relation và block nào bị ảnh hưởng? Có tái hiện trên bản sao? | Xác định page cần điều tra |
| Log I/O hoặc filesystem | Có lỗi thiết bị hoặc filesystem cùng thời điểm không? | Hướng điều tra storage/hệ điều hành |
| pg_checksums | Bao nhiêu block lỗi trên bản sao offline? | Xác định phạm vi checksum mismatch trong cluster |
| pg_stat_database | Bộ đếm checksum failure thay đổi thế nào? | Theo dõi dấu hiệu trên server hỗ trợ cột này |
| Backup manifest | File backup có khớp manifest không? | Đánh giá tính toàn vẹn file backup |
| WAL archive | Chuỗi WAL có liên tục và đọc được không? | Đánh giá khả năng PITR |
| Replica | Replica có cùng lỗi hoặc dữ liệu sai không? | Đánh giá khả năng failover |
| amcheck | Index có lỗi cấu trúc không? | Xác định có thể rebuild index hay không |
| Kiểm tra nghiệp vụ | Dữ liệu có đáp ứng quy tắc và tổng đối chiếu không? | Xác nhận tính đúng đắn sau phục hồi |

Không kết luận nguyên nhân chỉ dựa vào một dòng log. Một kết luận đáng tin cậy cần ghép thời điểm, relation, block, trạng thái checksum, log storage, backup, WAL, replica và kết quả restore.

## 12. Phòng ngừa và chuẩn bị trước sự cố

Phần lớn giá trị của xử lý sự cố đến từ việc chuẩn bị trước khi xảy ra lỗi.

### 12.1. Bật checksum khi khởi tạo cluster

Với cluster mới, cân nhắc bật data checksums ngay từ initdb. Với cluster hiện có, đánh giá khả năng bật bằng pg_checksums trên phiên bản đang dùng và lên lịch downtime phù hợp. Không xem việc bật checksum là thay thế backup.

### 12.2. Kiểm tra backup định kỳ

- Tạo backup theo RPO/RTO đã thống nhất.
- Lưu WAL archive và kiểm tra khả năng phục hồi theo thời gian.
- Xác minh backup manifest khi có.
- Thử restore định kỳ trên môi trường cô lập.
- Bảo vệ backup bằng quyền riêng, mã hóa và bản sao ngoài vùng lỗi của database.
- Ghi nhận thời gian restore thực tế và các bước thủ công còn phụ thuộc.

Một backup chưa từng được restore thử chỉ là một giả định về khả năng phục hồi.

### 12.3. Giám sát storage và hệ điều hành

Theo dõi I/O latency, lỗi đọc/ghi, filesystem, dung lượng, controller reset, SMART hoặc báo cáo từ nhà cung cấp cloud storage. Đồng bộ thời gian để đối chiếu log. Nếu có lỗi phần cứng, cần đánh giá toàn bộ volume, node và các bản sao liên quan.

### 12.4. Giữ quy trình vận hành rõ ràng

Tài liệu runbook nên có:

- Người chịu trách nhiệm và kênh liên lạc sự cố.
- Cách thu thập log và metadata.
- Vị trí snapshot, backup và WAL archive.
- Quy trình clone môi trường làm việc.
- Lệnh kiểm tra đúng major version.
- Điều kiện dừng, điều kiện failover và điều kiện restore.
- Quy trình phê duyệt các thao tác có thể làm thay đổi dữ liệu.
- Chính sách bảo quản, truy cập và xóa bằng chứng.

## 13. Checklist bảo toàn bằng chứng

Khi phát hiện checksum mismatch hoặc nghi ngờ hỏng dữ liệu, hãy ghi nhận:

- [ ] Lưu nguyên văn log PostgreSQL cùng timestamp, PID, database, role và client.
- [ ] Ghi nhận phiên bản PostgreSQL, trạng thái checksum và đường dẫn data directory.
- [ ] Xác định relation, filenode, relation path và block nếu log cung cấp.
- [ ] Lưu log hệ điều hành, filesystem, storage, monitoring và ứng dụng.
- [ ] Ghi nhận trạng thái primary, replica, WAL archive và backup.
- [ ] Tạo snapshot hoặc bản sao theo cơ chế nhất quán được hỗ trợ.
- [ ] Giữ bản gốc bất biến, hạn chế quyền truy cập và ghi nhận hash bằng chứng.
- [ ] Chạy kiểm tra sâu trên bản sao làm việc.
- [ ] Xác minh backup và thử restore trong môi trường riêng.
- [ ] Không dùng các tùy chọn bỏ qua checksum hoặc zero page trên nguồn gốc.
- [ ] Không chạy pg_resetwal, REINDEX hoặc thao tác rewrite trước khi có căn cứ và bản sao.
- [ ] Ghi lại người thực hiện, lệnh, output, thời điểm và quyết định phục hồi.

Một checksum mismatch là tín hiệu để điều tra có hệ thống. Bảo toàn page, log, WAL, backup và trạng thái cấu hình giúp DBA phân biệt lỗi storage, lỗi cấu trúc và lỗi logic; từ đó chọn được bản phục hồi có căn cứ và giảm nguy cơ mất thêm dữ liệu trong quá trình xử lý.

