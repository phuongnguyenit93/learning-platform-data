# pg_rewind, tái gia nhập cụm và điều kiện sử dụng trong PostgreSQL

Khi một PostgreSQL primary bị failover, primary cũ có thể tiếp tục nhận writes trong một khoảng thời gian nếu chưa được fencing hoặc chưa biết primary mới đã được promote. Hai server khi đó có thể tạo ra hai nhánh WAL khác nhau. Sau khi chọn một primary mới, không thể chỉ bật lại primary cũ và để nó tiếp tục ghi như trước: hai lịch sử dữ liệu đã phân kỳ.

pg_rewind giúp đưa data directory của server cũ trở lại cùng trạng thái dữ liệu với server mới bằng cách xác định điểm phân kỳ trong timeline, tìm các block đã thay đổi và copy nội dung cần thiết từ source sang target. Sau đó target được khởi động ở standby mode để replay WAL từ primary mới và tái gia nhập replication topology.

Đây là công cụ quan trọng cho quy trình failover/switchover, nhưng chỉ hoạt động khi các điều kiện về cluster identity, timeline, WAL history, data checksums hoặc hint-bit logging và trạng thái shutdown được đáp ứng. Nếu thiếu điều kiện, phương án an toàn là tạo lại standby từ một base backup mới.

~~~text
                 Trước sự cố
              Primary A (TLI 1)
                     |
              WAL timeline 1
                     |
           +---------+---------+
           |                   |
           v                   v
      Standby B            Standby C

                 Primary A lỗi
                     |
                     v
             Promote Standby B
               Primary B (TLI 2)
                     |
              WAL timeline 2
                     |
        +------------+-------------+
        |                          |
        v                          v
   New writes                 Old Primary A
                              đã phân kỳ
                                   |
                                   v
                             pg_rewind
                                   |
                                   v
                         A trở thành standby
                                   |
                                   v
                          Replay WAL từ B
                                   |
                                   v
                          Rejoin replication
~~~

Bài này thuộc chương **Tính sẵn sàng cao** của module *Database Engine Relational PostgreSQL*, tập trung vào pg_rewind, điều kiện sử dụng, cách tái gia nhập cụm sau failover và các phương án thay thế khi rewind không khả thi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao primary cũ phân kỳ timeline sau failover.
2. Phân biệt failover, switchover, promotion và rejoin.
3. Mô tả cách pg_rewind tìm common ancestor và điểm phân kỳ.
4. Phân biệt source và target trong lệnh pg_rewind.
5. Liệt kê các điều kiện bắt buộc về system identifier và major version.
6. Giải thích yêu cầu data checksums hoặc wal_log_hints.
7. Hiểu vai trò của full_page_writes trong việc xác định block thay đổi.
8. Giải thích vì sao target phải được shutdown sạch trước khi rewind.
9. Xác định WAL target cần có từ thời điểm phân kỳ.
10. Sử dụng --restore-target-wal khi cần lấy WAL từ archive.
11. Sử dụng --dry-run và --progress để kiểm tra/quan sát thao tác.
12. Dùng --write-recovery-conf để chuẩn bị target làm standby trên phiên bản hỗ trợ.
13. Chuẩn bị primary_conninfo, standby.signal và replication slot.
14. Kiểm tra tablespaces, cấu hình và quyền filesystem sau rewind.
15. Phân biệt pg_rewind với pg_basebackup và physical restore.
16. Nhận diện trường hợp không thể dùng pg_rewind.
17. Thiết kế fencing để tránh split-brain.
18. Theo dõi quá trình target bắt kịp source.
19. Xử lý rewind thất bại hoặc target WAL bị thiếu.
20. Xây dựng runbook rejoin và fallback sang rebuild standby.

## 2. Vì sao cần tái gia nhập cụm?

Trong physical streaming replication, standby nhận WAL từ primary và replay để duy trì bản sao. Khi primary gặp sự cố, một standby có thể được promote thành primary mới.

### 2.1. Timeline trước failover

Ban đầu primary A ghi WAL trên timeline 1. Các standby nhận cùng WAL history.

### 2.2. Promotion tạo timeline mới

Khi standby B được promote, PostgreSQL bắt đầu một timeline mới, ví dụ timeline 2. Timeline 2 có điểm fork từ timeline 1 và tiếp tục ghi WAL riêng.

### 2.3. Primary cũ có thể đã ghi thêm dữ liệu

Nếu primary A không bị fence kịp thời, nó có thể tiếp tục ghi trên timeline 1 sau điểm fork. Các transaction đó không tự xuất hiện trên timeline 2.

### 2.4. Hai nhánh không tự hợp nhất

PostgreSQL physical replication không merge hai nhánh WAL như công cụ version control. Khi đã chọn B làm primary mới, lịch sử của A sau điểm phân kỳ không được đưa trở lại bằng cách chỉ kết nối replication.

### 2.5. Vai trò của pg_rewind

pg_rewind đưa A về trạng thái tương thích với nhánh của B tại thời điểm chung, rồi A có thể replay WAL mới từ B. Các thay đổi chỉ tồn tại trên nhánh A sau fork sẽ bị loại khỏi target.

### 2.6. Không phải merge dữ liệu nghiệp vụ

Nếu cần giữ một số writes chỉ có trên primary cũ, phải trích xuất và reconciliation theo nghiệp vụ trước hoặc sau quy trình rejoin. pg_rewind không hợp nhất row changes từ hai nhánh.

## 3. Thuật ngữ source và target

Trong pg_rewind, hai tên này rất quan trọng:

| Thuật ngữ | Ý nghĩa trong thao tác |
| --- | --- |
| Source | Cluster có lịch sử dữ liệu được chọn làm chuẩn, thường là primary mới |
| Target | Cluster sẽ bị rewind để khớp source, thường là primary cũ |
| Common ancestor | Điểm lịch sử WAL chung trước khi hai nhánh phân kỳ |
| Divergence point | Vị trí timeline fork nơi lịch sử bắt đầu khác nhau |
| Rejoin | Đưa target trở lại làm standby của source |
| Rebuild | Tạo target mới từ base backup của source |

### 3.1. Source là nhánh được giữ

Sau failover, source thường là primary mới đã được promote và đang nhận writes.

### 3.2. Target là nhánh bị thay thế

Target thường là primary cũ hoặc standby cũ đã đi theo timeline không còn được chọn.

### 3.3. Không đảo nhầm hai vai trò

Nếu chọn nhầm source, có thể đưa server đang chứa dữ liệu chuẩn về một nhánh cũ. Trước khi chạy, xác nhận topology, timeline và quyết định failover bằng thông tin độc lập.

### 3.4. Target bị ghi đè

pg_rewind sửa data directory của target. Coi thao tác này là destructive đối với trạng thái target hiện tại. Nếu cần giữ dữ liệu riêng của target, tạo snapshot/backup trước khi thực hiện.

## 4. pg_rewind hoạt động như thế nào?

pg_rewind không copy toàn bộ data directory như một base backup thông thường. Nó xác định những phần target cần thay đổi để giống source.

### 4.1. Đọc control data

Công cụ kiểm tra control information của source và target, bao gồm system identifier, checkpoint và timeline history.

### 4.2. Tìm điểm phân kỳ

Dựa trên timeline history, pg_rewind xác định điểm chung và vị trí hai nhánh bắt đầu khác nhau.

### 4.3. Phân tích WAL của target

WAL sau điểm phân kỳ giúp xác định các data blocks mà target đã thay đổi. Thông tin này dùng để tạo danh sách block cần copy lại.

### 4.4. Đọc dữ liệu từ source

Các block cần thiết được lấy từ source. Những file không thể xử lý theo block-level copy có thể được copy lại theo file-level rules của công cụ.

### 4.5. Đồng bộ target

Các file và block cần thiết trên target được thay thế để phản ánh trạng thái source. WAL cũ và file không còn phù hợp được xử lý theo quy trình rewind.

### 4.6. Recovery sau rewind

Target vẫn cần replay WAL để đạt trạng thái nhất quán và bắt kịp source. Khi cấu hình target làm standby, nó sẽ tiếp tục nhận WAL qua streaming hoặc archive.

### 4.7. Tại sao có thể nhanh hơn base backup?

Nếu lượng dữ liệu thay đổi kể từ điểm phân kỳ nhỏ so với toàn bộ cluster, pg_rewind chỉ phải copy phần cần thiết và các file liên quan. Với cluster lớn, điều này có thể giảm đáng kể thời gian rejoin.

### 4.8. Không phải lúc nào cũng nhanh hơn

Nếu thời gian phân kỳ dài, nhiều blocks thay đổi, WAL cần thiết không còn hoặc data layout thay đổi nhiều, pg_rewind có thể mất nhiều thời gian hoặc không khả thi. Rebuild từ base backup đôi khi đơn giản và đáng tin cậy hơn.

## 5. Điều kiện bắt buộc để dùng pg_rewind

Trước khi chạy, xác minh toàn bộ điều kiện sau.

### 5.1. Cùng PostgreSQL cluster identity

Source và target phải có cùng system identifier, nghĩa là chúng bắt nguồn từ cùng một PostgreSQL cluster. Hai cluster được initdb độc lập không thể ghép lại bằng pg_rewind chỉ vì có schema giống nhau.

Có thể xem system identifier bằng:

~~~bash
pg_controldata /path/to/PGDATA
~~~

Tìm trường Database system identifier.

### 5.2. Có lịch sử timeline chung

Source và target phải có common ancestor trong timeline history và có thể xác định điểm phân kỳ. Nếu không có history cần thiết hoặc hai cluster không cùng lineage, rewind không thể xác định đúng vùng thay đổi.

### 5.3. Cùng major version

Dùng binary pg_rewind phù hợp với major version của data directory. Source và target phải ở cùng PostgreSQL major version. pg_rewind không phải công cụ nâng cấp major version.

### 5.4. Có block change tracking cần thiết

Một trong hai điều kiện sau phải được bật từ trước khi tạo ra WAL cần phân tích:

- Data checksums được bật cho cluster.
- wal_log_hints = on.

### 5.5. full_page_writes phải bật

full_page_writes phải được bật để WAL có đủ full-page images theo yêu cầu của cơ chế rewind. Đây thường là mặc định, nhưng cần xác nhận trên cluster và không được tắt trong khoảng thời gian liên quan.

### 5.6. Target shutdown sạch

Target server phải được shutdown sạch trước khi chạy pg_rewind. Nếu target từng crash, hãy start nó, để crash recovery hoàn tất, rồi shutdown sạch trước khi rewind.

### 5.7. Có đủ WAL từ target

WAL cần thiết của target từ điểm phân kỳ phải còn trong target pg_wal hoặc có thể lấy từ archive. Nếu thiếu WAL bắt buộc, pg_rewind không thể xác định đầy đủ các blocks đã thay đổi.

### 5.8. Source có thể truy cập

Nếu dùng --source-server, source phải đang chạy và chấp nhận kết nối phù hợp. Connection role cần quyền đọc metadata và dữ liệu mà pg_rewind yêu cầu theo phiên bản.

### 5.9. Target path đúng

Target PGDATA phải là data directory đã dừng của server cần rewind. Kiểm tra path và cluster identity trước khi thực hiện.

## 6. Data checksums và wal_log_hints

pg_rewind cần nhận biết các page/block đã thay đổi kể từ điểm phân kỳ.

### 6.1. Data checksums

Data checksums ghi checksum cho database pages. Khi được bật, cơ chế này cung cấp thông tin cần cho pg_rewind phát hiện các block đã thay đổi.

### 6.2. Bật checksums khi initdb

Một cách phổ biến là khởi tạo cluster với checksum:

~~~bash
initdb --data-checksums -D /var/lib/postgresql/17/data
~~~

Tên option và cách quản lý có thể thay đổi theo major version. Kiểm tra initdb --help của bộ PostgreSQL đang sử dụng.

### 6.3. Kiểm tra checksum

Có thể xem trạng thái qua control data:

~~~bash
pg_controldata /var/lib/postgresql/17/data
~~~

Tìm trường Data page checksum version.

### 6.4. wal_log_hints

Nếu không dùng data checksums, có thể bật:

~~~conf
wal_log_hints = on
~~~

Tham số này yêu cầu restart và phải được bật trước thời điểm phân kỳ để WAL có thông tin hint-bit/page changes cần thiết.

### 6.5. Không bật sau sự cố rồi rewind ngay

Bật wal_log_hints sau khi hai nhánh đã phân kỳ không bổ sung thông tin vào WAL cũ. Điều kiện phải tồn tại trước khi tạo ra các WAL records cần pg_rewind phân tích.

### 6.6. full_page_writes

~~~conf
full_page_writes = on
~~~

Không tắt tham số này để giảm WAL mà vẫn kỳ vọng pg_rewind hoạt động bình thường.

### 6.7. Kiểm tra cả hai server

Vì source và target cùng cluster lineage, kiểm tra cấu hình thực tế và lịch sử thay đổi. Đừng chỉ xem postgresql.conf hiện tại mà bỏ qua thời điểm tham số được bật.

## 7. WAL cần thiết từ target

pg_rewind sử dụng WAL của target để tìm các block thay đổi sau divergence point.

### 7.1. WAL range

Nếu hai nhánh phân kỳ tại LSN X và target tiếp tục ghi tới LSN Y, pg_rewind cần thông tin WAL liên quan trong khoảng sau X tới Y.

### 7.2. WAL trong pg_wal

Nếu các segment còn nằm trong pg_wal của target, công cụ có thể đọc trực tiếp.

### 7.3. WAL archive

Nếu segment đã được archive và bị recycle khỏi pg_wal, có thể lấy lại từ archive nếu cấu hình phù hợp.

### 7.4. --restore-target-wal

Trên các phiên bản hỗ trợ, option này yêu cầu pg_rewind dùng restore_command của target để lấy WAL còn thiếu từ archive:

~~~bash
pg_rewind --restore-target-wal --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal dbname=postgres user=rewind_user"
~~~

Cấu hình restore_command phải truy cập được archive và hoạt động dưới quyền OS của tiến trình chạy công cụ.

### 7.5. Archive continuity

Archive phải chứa đúng timeline/segment của target. Một file WAL cùng tên từ cluster khác không thể thay thế.

### 7.6. Retention policy

Giữ WAL đủ lâu để các node có thể được rewind sau failover. Retention cần tính tới thời gian phát hiện sự cố, thời gian quyết định failover và thời gian chuẩn bị rejoin.

### 7.7. Nếu WAL bị thiếu

Nếu không có segment bắt buộc trong pg_wal hoặc archive, dừng kế hoạch rewind và đánh giá rebuild bằng base backup mới. Không giả tạo segment hoặc bỏ qua gap.

## 8. Chuẩn bị trước khi chạy

pg_rewind có thể thay đổi sâu data directory. Một quy trình preflight giúp tránh thao tác nhầm.

### 8.1. Fencing primary cũ

Đảm bảo primary cũ không còn nhận writes. Có thể dừng service, chặn network, thu hồi endpoint hoặc dùng cơ chế fencing của hạ tầng.

### 8.2. Xác nhận primary mới

Kiểm tra server được chọn làm source thực sự là primary đang hoạt động:

~~~sql
SELECT pg_is_in_recovery();
~~~

Trên source primary, kết quả mong đợi là false.

### 8.3. Dừng target

Dừng target bằng pg_ctl hoặc service manager:

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary stop -m fast
~~~

Đợi command hoàn tất và xác nhận process đã dừng. Không chạy pg_rewind khi target đang hoạt động.

### 8.4. Nếu target crash

Nếu target bị crash, start nó với đúng data directory để PostgreSQL hoàn tất crash recovery, sau đó shutdown sạch. Kiểm tra log để chắc chắn quá trình recovery đã hoàn tất.

### 8.5. Backup target trước rewind

Tạo filesystem snapshot hoặc backup phù hợp nếu cần giữ trạng thái target để điều tra hoặc trích xuất dữ liệu riêng. Không dựa vào khả năng rollback tự động của pg_rewind.

### 8.6. Kiểm tra dung lượng

Đảm bảo đủ disk space cho copy/temporary operations, WAL replay và tablespaces. Cũng kiểm tra dung lượng source và archive.

### 8.7. Kiểm tra quyền

User OS chạy pg_rewind phải đọc được source/target files và ghi được target directory. Nếu dùng --source-server, database role cần quyền phù hợp.

### 8.8. Kiểm tra version

~~~bash
pg_rewind --version
pg_ctl --version
~~~

Dùng binary phù hợp với major version của source/target.

### 8.9. Kiểm tra tablespaces

Xác nhận mọi tablespace location có mặt và có thể truy cập. Các symlink trong pg_tblspc phải trỏ tới path hợp lệ trên target host.

### 8.10. Lập kế hoạch cấu hình

Ghi lại target-specific postgresql.conf, pg_hba.conf, SSL files, archive settings, port, listen_addresses, logging, memory settings và replication connection. Một số file nằm trong PGDATA có thể bị thay thế theo quá trình copy; kiểm tra và khôi phục cấu hình riêng sau rewind.

## 9. Kiểm tra topology và timeline

Trước khi chạy, cần hiểu nhánh WAL.

### 9.1. Kiểm tra recovery state

Trên source:

~~~sql
SELECT pg_is_in_recovery();
~~~

Source được chọn làm primary mới thường trả false.

### 9.2. Kiểm tra system identifier

~~~bash
pg_controldata /var/lib/postgresql/17/new-primary
pg_controldata /var/lib/postgresql/17/old-primary
~~~

Đối chiếu Database system identifier.

### 9.3. Kiểm tra timeline

pg_controldata cung cấp checkpoint timeline và control information. Đọc timeline history files trong archive/pg_wal để xác định fork.

### 9.4. History file

Tên file history có dạng 8 chữ số hexadecimal và hậu tố .history, ví dụ 00000002.history. File mô tả timeline cha và điểm switch.

### 9.5. Không chỉ dựa vào timeline ID

Hai cluster có thể cùng số timeline nhưng không cùng system identifier. Kết hợp system identifier, timeline history và backup lineage.

### 9.6. Chọn nhánh chuẩn

Ghi rõ primary mới, timeline hiện tại, target cũ, divergence point và các transaction trên nhánh cũ sẽ bị loại bỏ.

## 10. Cách gọi pg_rewind

Có hai cách chính để cung cấp source: kết nối tới server đang chạy hoặc đọc source data directory đã shutdown sạch.

### 10.1. Source server đang chạy

Ví dụ:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full" --progress
~~~

Source là primary mới; target là data directory primary cũ đã dừng.

### 10.2. Source data directory

Nếu source đã shutdown sạch và nằm trên cùng host/filesystem:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-pgdata=/var/lib/postgresql/17/new-primary --progress
~~~

Cách này không phù hợp khi source đang phục vụ writes; trong môi trường failover thông thường, --source-server là lựa chọn thuận tiện.

### 10.3. Chỉ dùng một source mode

Cung cấp một trong --source-server hoặc --source-pgdata theo cú pháp version. Không chỉ định cả hai.

### 10.4. --dry-run

Trước thao tác thật, có thể dùng:

~~~bash
pg_rewind --dry-run --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal dbname=postgres user=rewind_user"
~~~

Dry run kiểm tra và hiển thị kế hoạch theo khả năng phiên bản, không thực hiện thay đổi dữ liệu. Nó không thay thế preflight và backup target.

### 10.5. --progress

Hiển thị tiến độ copy, hữu ích khi cluster lớn. Không coi progress là bằng chứng target đã bắt kịp WAL.

### 10.6. --debug

Có thể dùng debug output khi điều tra lỗi. Bảo vệ log vì command line/connection metadata có thể chứa thông tin nhạy cảm.

### 10.7. --no-sync

Một số phiên bản có option bỏ fsync/sync sau copy để chạy nhanh hơn. Không dùng trong quy trình production thông thường vì mất bảo đảm durability khi host crash/power loss.

### 10.8. --sync-method

Các phiên bản hỗ trợ có thể chọn cách đồng bộ file sau khi copy. Dùng mặc định hoặc phương thức đã được kiểm thử trên filesystem/OS mục tiêu.

## 11. Ví dụ runbook pg_rewind

Giả sử:
- PostgreSQL major version 17.
- Primary mới là host new-primary.
- Primary cũ có PGDATA tại /var/lib/postgresql/17/old-primary.
- Hai node cùng system identifier.
- Target đã shutdown sạch.
- WAL archive của target còn đầy đủ.

### Bước 1. Xác nhận source

Trên source:

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả phải là false.

### Bước 2. Xác nhận target đã dừng

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary status
~~~

Không được còn postmaster process đang sử dụng PGDATA này.

### Bước 3. Kiểm tra điều kiện

Kiểm tra checksums hoặc wal_log_hints, full_page_writes, timeline ancestry và WAL availability.

### Bước 4. Dry run

~~~bash
pg_rewind --dry-run --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full"
~~~

### Bước 5. Thực hiện rewind

~~~bash
pg_rewind --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full"
~~~

Nếu target cần lấy WAL archive, dùng --restore-target-wal theo version và cấu hình restore_command.

### Bước 6. Cấu hình standby

Sau khi rewind, cấu hình primary_conninfo và standby.signal hoặc dùng --write-recovery-conf nếu phiên bản hỗ trợ và source connection string phù hợp.

### Bước 7. Kiểm tra config

Xác nhận port, hba, SSL, archive, tablespaces, memory và path đúng với target host. Khôi phục file cấu hình riêng nếu chúng đã bị thay đổi.

### Bước 8. Khởi động target

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary start
~~~

### Bước 9. Xác nhận recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

Target phải trả true khi đang hoạt động như standby.

### Bước 10. Xác nhận WAL receiver

~~~sql
SELECT status, sender_host, sender_port, latest_end_lsn, latest_end_time FROM pg_stat_wal_receiver;
~~~

### Bước 11. Xác nhận source nhìn thấy target

Trên primary mới:

~~~sql
SELECT application_name, client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication;
~~~

### Bước 12. Theo dõi catch-up

Đo receive/replay LSN, lag, slot retention và log cho tới khi standby đạt trạng thái bình thường.

## 12. --write-recovery-conf và standby configuration

Trên các phiên bản hỗ trợ, --write-recovery-conf (viết tắt -R) giúp chuẩn bị target tiếp tục ở standby mode.

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user" --write-recovery-conf
~~~

### 12.1. Signal file

Với PostgreSQL 12 trở lên, standby mode được yêu cầu bằng file standby.signal trong PGDATA.

### 12.2. Connection settings

Option -R ghi các connection settings cần thiết vào cấu hình tự động theo cơ chế của phiên bản. Kiểm tra postgresql.auto.conf sau khi chạy.

### 12.3. primary_conninfo

Nếu tự cấu hình, ví dụ:

~~~conf
primary_conninfo = 'host=new-primary.example.internal port=5432 user=replicator application_name=old_primary_rejoined sslmode=verify-full'
~~~

Dùng passfile/secret manager để cấp mật khẩu; không lưu secret plaintext trong file được version control.

### 12.4. Replication slot

Nếu standby dùng physical replication slot, cấu hình primary_slot_name và tạo slot phù hợp trên primary mới. Slot cần tồn tại và active đúng node.

### 12.5. restore_command

Nếu standby cần archive để catch up hoặc hỗ trợ recovery, giữ restore_command phù hợp. Không để một recovery command cũ trỏ tới archive không còn đúng cluster.

### 12.6. PostgreSQL 11 trở xuống

Các phiên bản cũ dùng recovery.conf cho standby settings. Cách tạo file recovery configuration và option pg_rewind phụ thuộc major version; xem pg_rewind --help và tài liệu của chính version đó.

### 12.7. Không giả định -R hoàn tất mọi cấu hình

Kiểm tra primary_conninfo, slot, restore_command, SSL, authentication, application_name và target-specific settings sau khi option chạy.

## 13. Cấu hình replication trên primary mới

Target chỉ rejoin thành công nếu primary mới cho phép nó kết nối và gửi WAL.

### 13.1. wal_level và senders

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
~~~

Giá trị thực tế phụ thuộc số replicas, backup clients và các consumer khác.

### 13.2. Replication role

~~~sql
CREATE ROLE replicator WITH LOGIN REPLICATION;
~~~

Thiết lập credential theo secret management policy.

### 13.3. pg_hba.conf

~~~conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
~~~

Chỉ cho phép các địa chỉ node hợp lệ và dùng TLS khi phù hợp.

### 13.4. Tạo physical slot

Nếu thiết kế dùng slot:

~~~sql
SELECT pg_create_physical_replication_slot('old_primary_rejoined');
~~~

Tạo slot trên primary mới trước khi standby kết nối với primary_slot_name tương ứng.

### 13.5. Slot không tự động bắt buộc

Không phải mọi topology đều cần slot. Slot bảo vệ WAL khỏi bị recycle trước khi consumer nhận, nhưng một consumer lag lâu có thể giữ WAL và làm đầy disk. Giám sát slot retention.

### 13.6. Kiểm tra replication connection

Trên primary mới, xác nhận row của target trong pg_stat_replication và state hợp lệ.

## 14. Tablespaces, configuration và external files

pg_rewind xử lý data directory nhưng một PostgreSQL installation có thể phụ thuộc các path bên ngoài.

### 14.1. Tablespace symlinks

Kiểm tra pg_tblspc và mọi target path. Tablespace path trên source có thể khác path mong muốn trên target host.

### 14.2. Filesystem ownership

Đảm bảo owner/group và permissions của data directory, WAL directory, tablespaces và archive paths đúng OS account chạy PostgreSQL.

### 14.3. Configuration files

Các file nằm trong PGDATA có thể bị thay đổi khi pg_rewind copy file từ source. Sau rewind, so sánh và khôi phục cấu hình riêng cho node được tái gia nhập.

### 14.4. Config ngoài PGDATA

Nếu postgresql.conf hoặc pg_hba.conf nằm ngoài PGDATA, chúng không nhất thiết được xử lý cùng data files. Kiểm tra các đường dẫn được tham chiếu bởi config.

### 14.5. SSL và secrets

Khôi phục certificate/key, password file, cloud credentials và secret mounts. Kiểm tra quyền file private key.

### 14.6. Archive command

Đảm bảo archive_command/restore_command phù hợp vai trò standby và topology mới. Tránh để target tiếp tục archive vào namespace xung đột với primary mới.

### 14.7. Port và service discovery

Node rejoin có thể cần port, DNS, service name hoặc firewall rules riêng. Không đưa target trở lại endpoint ghi của ứng dụng.

## 15. pg_rewind và pg_basebackup: khác nhau thế nào?

| Tiêu chí | pg_rewind | pg_basebackup |
| --- | --- | --- |
| Mục đích | Đưa cluster đã phân kỳ về nhánh source | Tạo bản physical backup mới |
| Dữ liệu copy | Blocks/files cần đồng bộ | Toàn bộ base backup |
| Yêu cầu common lineage | Có | Không cần target lineage vì tạo data directory mới |
| Yêu cầu checksums/wal_log_hints | Có điều kiện | Không phải điều kiện pg_rewind |
| Yêu cầu target shutdown | Có, shutdown sạch | Không áp dụng cho target đang chạy; tạo backup vào đích mới |
| WAL của target sau fork | Cần để tìm changed blocks | Không cần để tạo base backup mới |
| Dung lượng truyền | Thường nhỏ hơn nếu thay đổi ít | Thường lớn hơn |
| Khi phù hợp | Rejoin node cũ cùng cluster sau failover | Rebuild standby hoặc tạo base backup |

### 15.1. Chọn pg_rewind

Dùng khi target cùng cluster lineage, có điều kiện rewind và WAL cần thiết, đồng thời muốn giảm lượng dữ liệu copy.

### 15.2. Chọn pg_basebackup

Dùng khi target không đáp ứng điều kiện rewind, WAL thiếu, lineage không rõ hoặc muốn tạo một standby sạch.

### 15.3. Không dùng pg_rewind để nâng cấp

Muốn nâng cấp major version, dùng pg_upgrade hoặc logical migration phù hợp. pg_rewind không chuyển đổi định dạng data files.

### 15.4. Không dùng pg_rewind để merge

Nếu hai nhánh có writes khác nhau cần giữ cả hai, trích xuất và reconciliation dữ liệu trước khi rewind hoặc từ snapshot backup.

## 16. Khi nào không thể dùng pg_rewind?

### 16.1. Hai cluster khác system identifier

Nếu source và target được initdb độc lập, chúng không có chung cluster identity. Rebuild target từ base backup của source.

### 16.2. Không có timeline ancestry chung

Nếu timeline history không thể nối về cùng ancestor, pg_rewind không thể xác định điểm phân kỳ.

### 16.3. Checksums và wal_log_hints đều không bật

Nếu cả hai đều tắt trong khoảng cần phân tích, pg_rewind không có thông tin cần thiết để xác định block changes.

### 16.4. full_page_writes bị tắt

Nếu điều kiện full_page_writes không được đáp ứng trong giai đoạn cần thiết, rewind không an toàn/không được hỗ trợ.

### 16.5. Target đang chạy

Dừng target sạch trước khi chạy. Không dùng pg_rewind để chỉnh data directory mà postmaster đang mở.

### 16.6. Target crash chưa recovery

Cho target start và hoàn tất crash recovery, sau đó shutdown sạch.

### 16.7. WAL target bị mất

Nếu không có WAL cần thiết trong pg_wal hoặc archive, rebuild bằng base backup.

### 16.8. Major version không khớp

Dùng cùng major version và binary phù hợp. Dùng upgrade tool cho chuyển đổi major version.

### 16.9. Không thể truy cập source

Nếu source server không kết nối được hoặc source data directory không ở trạng thái phù hợp, sửa connection/access hoặc dùng base backup.

### 16.10. Data corruption hoặc storage failure

Nếu target/source có dấu hiệu corruption, không coi pg_rewind là công cụ sửa chữa corruption. Khôi phục từ backup đã xác minh và điều tra storage.

## 17. Timeline history và phân kỳ sâu

~~~text
TLI 1:  A0 ---- A1 ---- A2 ---- A3
                         |
                         +---- fork
                                |
TLI 2:                          B0 ---- B1 ---- B2
                                              |
                                              +---- fork
                                                     |
TLI 3:                                               C0 ---- C1
~~~

### 17.1. Common ancestor

Nếu target đang ở TLI 2 và source ở TLI 3, hai nhánh có thể có common ancestor tại điểm fork TLI 2.

### 17.2. History chain

PostgreSQL dùng .history files để mô tả quan hệ timeline. Giữ các file này trong archive cùng WAL segments.

### 17.3. Nhiều lần promote

Nếu một node bị rewind chậm và topology đã promote thêm lần nữa, xác minh source timeline mới nhất và history chain trước khi thao tác.

### 17.4. Target ở nhánh xa hơn

Nếu target đã đi theo một nhánh khác không phải ancestor của source được chọn, cần kiểm tra lineage. Không suy đoán điểm fork từ tên WAL file.

### 17.5. Lưu bằng chứng timeline

Ghi system identifier, timeline ID, history files, divergence LSN và primary được chọn làm chuẩn vào incident record.

## 18. Điều gì xảy ra với dữ liệu riêng trên primary cũ?

pg_rewind làm target khớp source. Các transaction chỉ được commit trên nhánh target sau điểm phân kỳ sẽ không tồn tại trong nhánh source.

### 18.1. Không có merge tự động

pg_rewind không so sánh business rows rồi hợp nhất. Nó làm việc ở mức physical files/blocks và WAL history.

### 18.2. Backup trước khi rewind

Nếu có khả năng cần giữ dữ liệu trên nhánh cũ, snapshot/backup target trước thao tác.

### 18.3. Trích xuất dữ liệu riêng

Có thể restore snapshot target vào môi trường cô lập, đọc dữ liệu cần thiết và xuất bằng pg_dump/SQL. Sau đó reconciliation với source.

### 18.4. Xử lý duplicate IDs

Hai nhánh có thể cấp cùng sequence values sau fork. Khi merge nghiệp vụ, xử lý primary keys, unique constraints, foreign keys và external references.

### 18.5. Audit và quyết định nghiệp vụ

Ghi nhận các transaction có thể bị mất, người quyết định chọn nhánh chuẩn và cách xử lý dữ liệu chỉ có ở nhánh cũ.

## 19. Bảo vệ trước split-brain

Tái gia nhập an toàn bắt đầu từ việc bảo đảm chỉ một primary có quyền nhận writes.

### 19.1. Fencing

Fencing ngăn primary cũ tiếp tục ghi bằng cách dừng máy, tắt service, thu hồi storage/network access hoặc dùng cơ chế fencing của cluster manager.

### 19.2. Không chỉ đổi DNS

DNS cache, connection pool và client retry có thể tiếp tục kết nối primary cũ. Fencing cần ở tầng server/hạ tầng, không chỉ đổi endpoint.

### 19.3. Xác nhận một writer

Sau failover, kiểm tra topology và connection routing để chỉ primary mới nhận writes.

### 19.4. Chỉ rewind sau khi fence

Target phải dừng và không được phục vụ traffic. Không rewind một server có thể bị ứng dụng ghi đồng thời.

### 19.5. Rejoin không phải promotion

Target sau rewind phải khởi động ở standby mode. Nếu khởi động như primary độc lập, nó có thể tạo timeline mới và lại phân kỳ.

## 20. Kiểm tra sau khi rejoin

Sau khi target start, cần xác nhận cả trạng thái recovery và tiến độ replication.

### 20.1. Target ở recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả mong đợi là true.

### 20.2. WAL receiver

~~~sql
SELECT status, sender_host, sender_port, receive_start_lsn, written_lsn, flushed_lsn, latest_end_lsn, latest_end_time FROM pg_stat_wal_receiver;
~~~

### 20.3. Replay progress

~~~sql
SELECT pg_last_wal_receive_lsn() AS receive_lsn, pg_last_wal_replay_lsn() AS replay_lsn, pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

### 20.4. Primary replication view

~~~sql
SELECT application_name, client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn, sync_state FROM pg_stat_replication;
~~~

### 20.5. Replication slot

~~~sql
SELECT slot_name, slot_type, active, restart_lsn, wal_status FROM pg_replication_slots;
~~~

### 20.6. Log

Tìm thông báo kết nối streaming, WAL replay, timeline switch, missing WAL, authentication error và recovery completion.

### 20.7. Catch-up

So sánh receive/replay LSN và lag trong một khoảng thời gian. Khi source tiếp tục ghi, target cần tiến đều và không tăng lag vô hạn.

### 20.8. Không mở read traffic ngay nếu chưa sẵn sàng

Nếu target được dùng cho reporting standby, xác nhận nó đạt consistency point, quyền đọc và query behavior trước khi đưa vào read pool.

## 21. Theo dõi WAL lag và slot pressure

### 21.1. Khoảng cách receive/replay

~~~sql
SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) AS bytes_received_not_replayed;
~~~

### 21.2. Primary gửi/replay

~~~sql
SELECT application_name, pg_wal_lsn_diff(sent_lsn, replay_lsn) AS sent_not_replayed_bytes FROM pg_stat_replication;
~~~

### 21.3. Không chuyển bytes thành seconds tùy tiện

WAL generation rate thay đổi theo workload. Đo tốc độ WAL theo cửa sổ thời gian nếu cần ước lượng lag duration.

### 21.4. Slot retained WAL

Theo dõi restart_lsn, wal_status và dung lượng pg_wal trên primary. Một target chưa catch up có thể làm slot giữ WAL lâu.

### 21.5. Disk alert

Đặt alert theo dung lượng trống và tốc độ tăng pg_wal. Không chờ filesystem đầy mới xử lý slot.

### 21.6. Archive fallback

Nếu streaming bị gián đoạn nhưng WAL archive còn đủ, standby có thể dùng restore_command để catch up theo cấu hình. Kiểm tra archive path và retention.

## 22. Cấu hình target sau rewind

### 22.1. standby.signal

Với PostgreSQL 12 trở lên, target cần standby.signal để khởi động ở standby mode.

### 22.2. primary_conninfo

Đảm bảo connection string trỏ tới primary mới. Dùng application_name riêng để nhận diện trong pg_stat_replication.

### 22.3. primary_slot_name

Nếu sử dụng physical replication slot, đặt tên slot đã tạo trên primary mới.

### 22.4. restore_command

Nếu dùng WAL archive làm nguồn bổ sung, cấu hình restore_command đúng archive namespace và timeline.

### 22.5. archive_mode

Kiểm tra archive_mode/archiving policy trên standby theo topology. Nếu nhiều node archive cùng namespace, cần thiết kế tránh ghi đè/đụng tên và tuân theo hướng dẫn PostgreSQL.

### 22.6. recovery_target settings

Loại bỏ recovery target PITR cũ nếu chúng không còn phù hợp. Một standby rejoin thông thường cần tiếp tục follow primary, không dừng lại ở một target lịch sử cũ.

### 22.7. Cấu hình node riêng

Khôi phục port, listen_addresses, memory, logging, SSL, hba và service identity theo vai trò mới.

## 23. Rejoin sau switchover có kế hoạch

Switchover khác failover ở chỗ thường có thể phối hợp shutdown và promotion có kiểm soát.

### 23.1. Quiesce writes

Tạm dừng hoặc điều phối writes để primary cũ flush dữ liệu và standby bắt kịp.

### 23.2. Promote có kế hoạch

Promote standby được chọn sau khi xác nhận replay tới vị trí cần thiết.

### 23.3. Old primary shutdown

Shutdown primary cũ sạch trước khi chuẩn bị nó làm standby.

### 23.4. Divergence có thể không đáng kể

Nếu primary cũ đã shutdown trước khi nhánh mới ghi thêm dữ liệu, hai node có thể chưa phân kỳ theo cách cần rewind. Có thể tái sử dụng theo quy trình phù hợp hoặc vẫn rebuild để đơn giản hóa.

### 23.5. Không mặc định luôn cần pg_rewind

Xác định trạng thái timeline thực tế. Nếu node cũ đã đồng nhất và có thể tiếp tục standby an toàn, dùng runbook phù hợp; nếu đã phân kỳ, rewind hoặc rebuild.

## 24. Rejoin sau failover ngoài kế hoạch

### 24.1. Fence old primary

Ngay khi failover, cô lập old primary để ngăn writes song song.

### 24.2. Promote node mới

Xác nhận standby được chọn có replay progress phù hợp và promote theo failover procedure.

### 24.3. Đánh giá old primary

Khi old primary truy cập lại, không cho ứng dụng kết nối ghi. Kiểm tra nó đã crash hay còn chạy, timeline và system identifier.

### 24.4. Shutdown sạch

Nếu target còn chạy, dừng theo quy trình. Nếu crash, để crash recovery hoàn tất rồi shutdown sạch.

### 24.5. Chọn rewind hoặc rebuild

Đánh giá checksums/wal_log_hints, full_page_writes, WAL range và lineage. Nếu thiếu điều kiện, dùng base backup mới.

### 24.6. Rejoin và monitor

Sau khi target theo primary mới, theo dõi WAL receiver, replay lag, slots và logs trước khi đánh dấu hoàn tất.

## 25. Xử lý pg_rewind thất bại

### 25.1. Thiếu WAL

Lỗi thiếu WAL có thể chỉ ra segment cần thiết không có trong pg_wal hoặc archive. Kiểm tra restore_command, timeline và archive retention.

### 25.2. Checksums/hints không bật

Nếu không đáp ứng điều kiện block tracking, không cố chạy tiếp bằng cách bật tham số sau sự cố. Rebuild target từ base backup.

### 25.3. Timeline không khớp

Đối chiếu history files và system identifier. Nếu source không phải nhánh được chọn hoặc lineage không chung, xác định lại topology.

### 25.4. Target chưa shutdown

Dừng postmaster và xác nhận clean shutdown. Không chạy lại trong khi target đang được mở.

### 25.5. Quyền filesystem

Kiểm tra owner, group, permissions, tablespace mounts và disk space.

### 25.6. Source connection failure

Kiểm tra pg_hba, TLS, role permissions, network và source server state.

### 25.7. Tablespace path lỗi

Xác minh symlink và directory. Không tự xóa tablespace hoặc symlink khi chưa đối chiếu metadata.

### 25.8. Target đã bị sửa một phần

Nếu lần chạy trước thất bại sau khi bắt đầu thay đổi target, coi target là không đáng tin cậy. Đánh giá lại từ snapshot hoặc rebuild từ base backup thay vì giả định có thể start an toàn.

### 25.9. Fallback

Tạo base backup mới từ primary hiện tại, restore vào PGDATA sạch, cấu hình standby và xác nhận replication. Đây là phương án tổng quát khi rewind không đáp ứng điều kiện.

## 26. Fallback bằng pg_basebackup

Ví dụ tạo standby mới:

~~~bash
pg_basebackup -h new-primary.example.internal -p 5432 -U replicator -D /var/lib/postgresql/17/rebuilt-standby -F plain -X stream -R -P -v
~~~

### 26.1. Data directory sạch

Đích cần rỗng hoặc được chuẩn bị theo quy trình rebuild đã kiểm soát. Không ghi đè một PGDATA đang chạy.

### 26.2. -R

Tạo cấu hình standby phù hợp theo version, thường gồm standby.signal và connection settings.

### 26.3. Slot

Nếu dùng slot, bảo đảm slot đã được tạo và connection string/slot settings đúng.

### 26.4. Tablespaces

Đảm bảo tablespace destinations tồn tại và có mapping đúng.

### 26.5. So sánh thời gian

Base backup copy toàn bộ dữ liệu nên có thể lâu hơn pg_rewind, nhưng không phụ thuộc WAL của target cũ để xác định block changes.

## 27. Bảo vệ dữ liệu trên nhánh cũ trước rewind

Một số sự cố có thể có transaction chỉ tồn tại trên old primary.

### 27.1. Chụp snapshot

Nếu cần điều tra, tạo snapshot storage hoặc copy data directory sau khi shutdown sạch và trước khi rewind.

### 27.2. Restore cô lập

Khởi tạo một bản sao cô lập từ snapshot để truy xuất dữ liệu riêng. Không đưa nó vào replication topology.

### 27.3. Trích xuất có chọn lọc

Dùng pg_dump hoặc SQL để trích xuất table/rows cần giữ. Có thể cần xử lý schema dependencies và sequences.

### 27.4. Reconciliation

Đối chiếu business keys, timestamps, unique constraints và external events. Xác định bản ghi nào được giữ, bỏ hoặc chuyển đổi.

### 27.5. Tránh nhập WAL branch cũ vào source

Không cố replay WAL của nhánh cũ vào primary mới sau fork. Việc hợp nhất cần thực hiện ở mức logical/business data.

## 28. Bảo mật khi rejoin

### 28.1. Replication credentials

Dùng role riêng với quyền replication cần thiết và giới hạn source addresses.

### 28.2. TLS

Dùng SSL mode phù hợp và xác minh server identity. Không tắt certificate verification chỉ để làm kết nối hoạt động.

### 28.3. Password files

Dùng .pgpass/secret store với permissions chặt chẽ. Kiểm tra pg_rewind -R có ghi credential nhạy cảm vào file cấu hình hay không theo version/client behavior.

### 28.4. OS permissions

Data directory và tablespaces chỉ nên thuộc OS account chạy PostgreSQL. Không mở quyền ghi rộng.

### 28.5. Audit trail

Ghi người thực hiện, source/target, system identifier, timeline, command options, thời điểm shutdown, rewind result và thời điểm target rejoin.

## 29. Giới hạn và rủi ro cần hiểu

### 29.1. Không merge writes

Mọi writes chỉ có trên target branch sau divergence sẽ bị loại khi target khớp source.

### 29.2. Không sửa corruption tổng quát

pg_rewind không phải công cụ sửa data corruption, disk failure hoặc sai checksum tùy ý.

### 29.3. Cần WAL history

Nếu WAL target cần thiết bị mất, rewind có thể không hoạt động dù archive mới nhất vẫn có nhiều file.

### 29.4. Cùng cluster lineage

Không dùng để hợp nhất hai PostgreSQL cluster độc lập hoặc di chuyển giữa major versions.

### 29.5. Có thể mất cấu hình target riêng

Kiểm tra file config trong PGDATA và các path ngoài PGDATA sau khi copy. Không khởi động target với config source không phù hợp.

### 29.6. Cần downtime target

Target phải shutdown trong quá trình rewind. Thời gian dừng phụ thuộc lượng thay đổi và I/O.

### 29.7. Không thay backup

Tạo backup/snapshot phù hợp trước thao tác nếu cần khả năng điều tra hoặc rollback. pg_rewind không phải backup artifact.

### 29.8. Fallback phải sẵn sàng

Runbook cần có đường đi rebuild từ base backup nếu rewind thất bại hoặc điều kiện không còn đáp ứng.

## 30. Monitoring và alert cho rejoin

| Metric / sự kiện | Mục đích |
| --- | --- |
| pg_is_in_recovery() | Xác nhận target vẫn là standby |
| WAL receiver status | Xác nhận streaming connection |
| Receive LSN | Tiến độ WAL nhận |
| Replay LSN | Tiến độ WAL áp dụng |
| Replay lag | Đo mức bắt kịp |
| pg_stat_replication | Source thấy target |
| Replication slot restart_lsn | WAL retained bởi slot |
| pg_wal disk usage | Tránh đầy filesystem |
| Archive failures | Phát hiện WAL archive lỗi |
| PostgreSQL logs | Tìm missing WAL/auth/recovery errors |
| Timeline history | Xác nhận nhánh đúng |
| System identifier | Xác nhận cùng cluster lineage |

### 30.1. Alert khi receiver mất kết nối

Nếu target không còn row trong pg_stat_wal_receiver hoặc status không streaming, điều tra network/auth/source.

### 30.2. Alert khi replay lag tăng

Lag tăng liên tục có thể do WAL volume, I/O hoặc conflict/recovery issue. Không chỉ dựa vào một snapshot metric.

### 30.3. Alert slot retained WAL

Theo dõi restart_lsn và disk growth. Giới hạn dung lượng slot theo policy và có kế hoạch rebuild nếu slot bị invalidated.

### 30.4. Alert archive gap

Kiểm tra continuity cho timeline và WAL range mà standby có thể cần.

### 30.5. Rejoin completion

Chỉ đánh dấu rejoin xong khi receiver ổn định, replay tiến đều, primary thấy standby và logs không có lỗi lặp lại.

## 31. Runbook rejoin chuẩn

1. Xác nhận failover decision và primary mới.
2. Fence old primary để chỉ còn một writer.
3. Ghi system identifier, timeline và divergence context.
4. Kiểm tra old primary có cần trích xuất dữ liệu riêng không.
5. Tạo snapshot/backup target nếu cần lưu bằng chứng.
6. Xác nhận source và target cùng system identifier.
7. Xác nhận cùng major version và binary phù hợp.
8. Xác nhận timeline ancestry và history files.
9. Xác nhận checksums hoặc wal_log_hints đã bật trước divergence.
10. Xác nhận full_page_writes đã bật trong giai đoạn cần thiết.
11. Xác nhận WAL target từ divergence point còn trong pg_wal/archive.
12. Cấu hình restore_command nếu cần lấy WAL từ archive.
13. Shutdown target sạch.
14. Kiểm tra tablespaces, filesystem permissions và disk.
15. Chạy pg_rewind --dry-run nếu phiên bản hỗ trợ.
16. Chạy pg_rewind với source/target chính xác và theo dõi progress.
17. Kiểm tra kết quả và file configuration sau rewind.
18. Cấu hình standby.signal/primary_conninfo/slot/restore_command.
19. Khởi động target.
20. Xác nhận pg_is_in_recovery() trả true.
21. Xác nhận pg_stat_wal_receiver và pg_stat_replication.
22. Theo dõi receive/replay LSN, slot retention và disk.
23. Xác nhận target bắt kịp source.
24. Đưa target vào read pool nếu cần và policy cho phép.
25. Ghi lại kết quả, thời gian, timeline và các dữ liệu riêng đã reconciliation.

## 32. Bài tập thực hành

Các bài tập thực hiện trong PostgreSQL lab có primary/standby riêng. Không chạy pg_rewind trên production khi chưa có runbook và xác nhận source/target.

### Bài 1. pg_rewind

pg_rewind giải quyết vấn đề gì sau failover?

### Bài 2. Timeline

Vì sao promotion tạo ra một timeline mới?

### Bài 3. Split-brain

Split-brain xảy ra khi nào?

### Bài 4. Source và target

Trong tình huống old primary tái gia nhập, source và target là node nào?

### Bài 5. Common ancestor

Common ancestor có ý nghĩa gì với pg_rewind?

### Bài 6. System identifier

Vì sao source và target phải cùng system identifier?

### Bài 7. Major version

pg_rewind có nâng cấp PostgreSQL 15 lên 16 không?

### Bài 8. Checksums

Data checksums hỗ trợ pg_rewind như thế nào?

### Bài 9. wal_log_hints

Nếu không bật checksums, cần điều kiện nào thay thế?

### Bài 10. full_page_writes

Vì sao full_page_writes cần bật?

### Bài 11. Timing

Có thể bật wal_log_hints sau khi phân kỳ rồi chạy rewind ngay không?

### Bài 12. Target shutdown

Target phải ở trạng thái nào trước pg_rewind?

### Bài 13. Crash target

Nếu target crash, cần làm gì trước khi rewind?

### Bài 14. WAL range

WAL nào cần có để pg_rewind xác định changed blocks?

### Bài 15. Archive

Option nào cho phép pg_rewind lấy target WAL từ archive?

### Bài 16. Source mode

Hai cách chính để chỉ định source là gì?

### Bài 17. Dry run

--dry-run dùng để làm gì?

### Bài 18. Progress

--progress cung cấp thông tin gì?

### Bài 19. Rewind destructive

Vì sao cần snapshot target trước khi rewind trong một số sự cố?

### Bài 20. Write recovery config

Option nào có thể tạo cấu hình để target chạy lại như standby trên version hỗ trợ?

### Bài 21. standby.signal

Vai trò của standby.signal trên PostgreSQL 12+ là gì?

### Bài 22. primary_conninfo

Sau rewind, primary_conninfo phải trỏ tới đâu?

### Bài 23. Replication slot

Khi dùng primary_slot_name, slot phải được tạo ở server nào?

### Bài 24. Fencing

Vì sao phải fence old primary trước khi rejoin?

### Bài 25. Writes trên nhánh cũ

Các transaction chỉ có trên old primary sau fork được pg_rewind xử lý thế nào?

### Bài 26. Merge

pg_rewind có merge rows từ hai nhánh không?

### Bài 27. Fallback

Khi thiếu target WAL, phương án phổ biến là gì?

### Bài 28. pg_basebackup

Nêu một khác biệt chính giữa pg_rewind và pg_basebackup.

### Bài 29. Tablespaces

Vì sao cần kiểm tra tablespace paths sau rewind?

### Bài 30. Config files

Vì sao phải kiểm tra cấu hình riêng của target sau rewind?

### Bài 31. Source state

Nếu dùng --source-server, source cần ở trạng thái nào trong quy trình rejoin thông thường?

### Bài 32. Timeline history

File .history giúp gì cho việc xác định ancestry?

### Bài 33. WAL retention

Retention policy cần giữ WAL target trong khoảng nào?

### Bài 34. Recovery state

Viết SQL xác nhận target đang là standby.

### Bài 35. Receiver

Viết SQL kiểm tra WAL receiver.

### Bài 36. Primary view

Viết SQL kiểm tra primary đã thấy target trong pg_stat_replication.

### Bài 37. Slot pressure

Vì sao slot có thể làm đầy pg_wal khi target catch-up chậm?

### Bài 38. Failure handling

Nếu pg_rewind đã sửa một phần target rồi thất bại, cần làm gì?

### Bài 39. Data riêng

Nếu cần giữ một số rows chỉ có trên nhánh cũ, xử lý theo cách nào?

### Bài 40. Runbook

Liệt kê các bước chính để đưa old primary trở lại thành standby an toàn.

## 33. Lời giải tham khảo

### Bài 1–5. Timeline và vai trò

pg_rewind đưa một node đã phân kỳ về nhánh source để node đó có thể rejoin. Promotion tạo timeline mới vì WAL sau fork thuộc một lịch sử khác. Split-brain xảy ra khi nhiều primary cùng nhận writes. Với old primary rejoin, source là primary mới và target là primary cũ. Common ancestor là điểm WAL history chung trước divergence.

### Bài 6–11. Điều kiện

System identifier xác nhận cùng cluster lineage. pg_rewind không nâng cấp major version. Data checksums giúp nhận diện page changes; nếu không có checksums thì cần wal_log_hints=on từ trước divergence. full_page_writes phải bật để WAL có full-page images theo yêu cầu. Bật wal_log_hints sau divergence không bổ sung thông tin cho WAL cũ.

### Bài 12–15. Target và WAL

Target phải shutdown sạch. Nếu crash, start để crash recovery hoàn tất rồi shutdown sạch. Cần WAL của target sau divergence point để xác định changed blocks. --restore-target-wal dùng restore_command để lấy WAL thiếu từ archive theo phiên bản hỗ trợ.

### Bài 16–20. Công cụ

Hai source modes là --source-server và --source-pgdata. --dry-run kiểm tra kế hoạch mà không sửa dữ liệu; --progress hiển thị tiến độ. Snapshot target có thể giữ dữ liệu nhánh cũ để điều tra/trích xuất. --write-recovery-conf hoặc -R chuẩn bị cấu hình standby trên version hỗ trợ.

### Bài 21–24. Rejoin

standby.signal yêu cầu PostgreSQL 12+ chạy standby mode. primary_conninfo phải trỏ primary mới. Slot được tạo trên primary mới. Fencing ngăn old primary tiếp tục ghi và tạo thêm phân kỳ.

### Bài 25–30. Giới hạn

Writes chỉ có trên old branch sau fork sẽ bị loại khỏi target; pg_rewind không merge rows. Nếu WAL thiếu, rebuild bằng base backup mới. pg_rewind copy phần thay đổi, pg_basebackup tạo bản sao vật lý mới. Tablespace paths cần tồn tại trên target. Config riêng phải được kiểm tra vì file trong PGDATA có thể bị thay thế.

### Bài 31–37. Monitoring

Với --source-server, source thông thường là primary mới đang chạy. History files mô tả timeline ancestry. Giữ target WAL từ divergence tới khi rewind hoàn tất. Kiểm tra standby bằng:

~~~sql
SELECT pg_is_in_recovery();
~~~

Receiver:

~~~sql
SELECT status, sender_host, latest_end_lsn FROM pg_stat_wal_receiver;
~~~

Primary:

~~~sql
SELECT application_name, state, sent_lsn, replay_lsn FROM pg_stat_replication;
~~~

Slot giữ WAL từ restart_lsn mà consumer còn cần. Nếu consumer lag lâu, WAL được giữ lại và pg_wal có thể tăng.

### Bài 38–40. Recovery và runbook

Nếu rewind thất bại sau khi đã thay đổi target, coi target là trạng thái không đáng tin cậy; phục hồi từ snapshot hoặc rebuild sạch. Dữ liệu riêng trên nhánh cũ cần snapshot, restore cô lập và logical reconciliation. Runbook gồm fence, xác nhận source/target/lineage, kiểm tra prerequisites/WAL, shutdown sạch, backup target, dry run, rewind, cấu hình standby, start, xác minh receiver/replay và monitor catch-up.

## 34. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/tham số |
| --- | --- |
| Rewind target theo source server | pg_rewind --source-server |
| Rewind từ source data directory | pg_rewind --source-pgdata |
| Chọn target PGDATA | --target-pgdata |
| Kiểm tra trước khi ghi | --dry-run |
| Hiện tiến độ | --progress |
| Lấy target WAL từ archive | --restore-target-wal |
| Tạo standby recovery config | --write-recovery-conf / -R |
| Kiểm tra cluster identity | pg_controldata |
| Bật block hint logging | wal_log_hints |
| Bật full page images | full_page_writes |
| Kiểm tra checksum metadata | pg_controldata |
| Tạo base backup fallback | pg_basebackup |
| Xác nhận standby state | pg_is_in_recovery() |
| Kiểm tra receiver | pg_stat_wal_receiver |
| Kiểm tra primary replication | pg_stat_replication |
| Kiểm tra slot | pg_replication_slots |
| Đo WAL distance | pg_wal_lsn_diff() |
| Standby mode PG12+ | standby.signal |
| Standby connection | primary_conninfo |
| Standby slot | primary_slot_name |

## 35. Checklist điều kiện và vận hành pg_rewind

1. Đã chọn và ghi nhận primary mới làm source.
2. Old primary đã được fencing, không nhận writes.
3. Source và target có cùng Database system identifier.
4. Source và target cùng PostgreSQL major version.
5. Timeline history cho thấy common ancestor và divergence point.
6. Data checksums hoặc wal_log_hints đã bật từ trước divergence.
7. full_page_writes đã bật trong khoảng WAL cần thiết.
8. Target đã shutdown sạch.
9. Nếu target crash, crash recovery đã hoàn tất trước clean shutdown.
10. Target WAL từ divergence point còn trong pg_wal hoặc archive.
11. restore_command hoạt động nếu dùng --restore-target-wal.
12. Source server truy cập được và có quyền phù hợp.
13. Target PGDATA path đã xác nhận chính xác.
14. Target snapshot/backup được tạo nếu cần giữ trạng thái cũ.
15. Disk space và tablespace mounts đã sẵn sàng.
16. Binary pg_rewind đúng major version.
17. Dry run được thực hiện khi phiên bản hỗ trợ.
18. Source/target parameters được ghi lại trong incident log.
19. Rewind chạy với progress/log phù hợp.
20. Sau rewind, kiểm tra config files và tablespace paths.
21. primary_conninfo trỏ primary mới.
22. standby.signal được tạo trên PostgreSQL 12+.
23. Replication slot tồn tại nếu target sử dụng slot.
24. restore_command/archive path trỏ đúng repository.
25. Target start thành công và pg_is_in_recovery() trả true.
26. WAL receiver kết nối ổn định.
27. Primary thấy target trong pg_stat_replication.
28. Receive/replay LSN tiến triển và lag giảm.
29. Slot retained WAL và disk usage nằm trong giới hạn.
30. Read routing chỉ được bật sau khi standby sẵn sàng.
31. Dữ liệu riêng trên old branch được reconciliation riêng nếu cần.
32. Nếu rewind không đủ điều kiện, rebuild bằng base backup.
33. Sau rejoin, kiểm tra archive, backups và failover policy.
34. Lưu command, logs, timeline, LSN và thời gian hoàn tất.

## 36. Tổng kết

pg_rewind giúp tái sử dụng một PostgreSQL node đã phân kỳ sau failover bằng cách xác định common ancestor, phân tích WAL của target và copy các blocks/files cần thiết từ source. Khi lượng dữ liệu thay đổi kể từ divergence nhỏ, thao tác này có thể nhanh hơn tạo lại toàn bộ standby bằng pg_basebackup.

Để rewind an toàn, source và target phải thuộc cùng cluster lineage và cùng major version; target phải shutdown sạch; timeline history và WAL của target từ điểm phân kỳ phải còn đầy đủ; data checksums hoặc wal_log_hints phải được bật từ trước; full_page_writes phải đáp ứng yêu cầu. Bật các tham số sau sự cố không thể tái tạo thông tin đã thiếu trong WAL cũ.

Sau rewind, target cần được cấu hình để chạy lại như standby của primary mới: standby.signal trên PostgreSQL 12+, primary_conninfo, slot nếu dùng và restore_command khi cần. Kiểm tra configuration, tablespaces, permissions, WAL receiver, replay LSN và primary replication view trước khi đưa node vào read pool hoặc coi rejoin đã hoàn tất.

pg_rewind không merge writes từ hai nhánh. Các transaction chỉ có trên old primary sau fork sẽ bị loại khi target khớp source. Nếu cần giữ chúng, snapshot old branch và reconciliation dữ liệu ở mức logical. Khi thiếu WAL, không có common lineage hoặc prerequisites không đáp ứng, rebuild bằng base backup mới là fallback rõ ràng.

Một quy trình rejoin tốt luôn bắt đầu bằng fencing để chỉ có một writer, xác nhận source/target và timeline, kiểm tra mọi prerequisites, giữ lại target snapshot khi cần, thực hiện rewind có kiểm soát và giám sát catch-up. Hãy duy trì WAL retention, kiểm thử pg_rewind trong restore/failover drills và luôn có phương án rebuild để giảm thời gian node nằm ngoài cụm.
