# Full-page write, checksum và bảo vệ tính toàn vẹn trong PostgreSQL

PostgreSQL lưu dữ liệu theo các page (block) trên đĩa và dùng **Write-Ahead Logging (WAL)** để bảo đảm khả năng phục hồi sau sự cố. Tuy nhiên, một lần ghi page từ shared buffers xuống storage không nhất thiết là thao tác nguyên tử. Nếu máy chủ mất điện giữa lúc ghi, một page có thể chỉ được ghi một phần: nửa đầu mang nội dung mới, nửa còn lại vẫn là nội dung cũ. Đây là hiện tượng **torn page write**.

PostgreSQL có hai cơ chế quan trọng để bảo vệ tính toàn vẹn của data pages:

- **Full-page writes (FPW):** ghi ảnh đầy đủ của một page vào WAL ở lần thay đổi đầu tiên của page sau checkpoint. Nếu page trên đĩa bị ghi dở trong crash, recovery có thể lấy full-page image (FPI) trong WAL để khôi phục page trước khi replay các thay đổi tiếp theo.
- **Data checksums:** lưu checksum trong mỗi data page và kiểm tra khi page được đọc. Cơ chế này giúp phát hiện một số dạng corruption của page, kể cả lỗi phát sinh ngoài crash recovery thông thường.

Hai cơ chế bổ sung cho nhau, nhưng không thay thế nhau. **Full-page writes giúp phục hồi page sau torn write; checksum giúp phát hiện page bytes bị thay đổi/hỏng.** Checksum không tự sửa page, còn FPI không phải công cụ phát hiện mọi corruption về lâu dài.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích page/block, shared buffers, dirty page và write-back xuống storage.
2. Mô tả torn page write và vì sao WAL row-level changes đơn thuần có thể không đủ.
3. Giải thích write-ahead rule và checkpoint trong chu trình crash recovery.
4. Phân biệt checkpoint, WAL flush, data page flush và commit acknowledgment.
5. Mô tả full-page image (FPI) và thời điểm PostgreSQL ghi FPI.
6. Giải thích tại sao FPI thường chỉ cần cho lần sửa đầu tiên của mỗi page sau checkpoint.
7. Đọc và cấu hình các tham số `full_page_writes`, `wal_log_hints`, `wal_compression`.
8. Hiểu trade-off giữa checkpoint frequency, WAL volume, CPU, I/O và crash recovery time.
9. Phân biệt data page checksums với CRC của WAL records.
10. Kiểm tra trạng thái checksums bằng `SHOW data_checksums`.
11. Hiểu cách bật checksums bằng `initdb --data-checksums` hoặc công cụ `pg_checksums`.
12. Biết `pg_checksums` yêu cầu cluster shutdown sạch và thao tác ở phạm vi toàn cluster.
13. Hiểu phạm vi bảo vệ và giới hạn của checksums.
14. Phân biệt phát hiện corruption, phục hồi bằng WAL/FPI và khôi phục từ backup.
15. Đọc lỗi checksum, page corruption và WAL CRC trong log.
16. Thiết kế quy trình kiểm tra backup, standby, storage và kiểm soát lỗi phần cứng.

## 2. Page và đường đi của dữ liệu

### 2.1. PostgreSQL lưu dữ liệu theo page

PostgreSQL tổ chức heap tables và indexes thành các page có kích thước cố định theo build, thường là 8 KB. Mỗi relation được lưu thành một hoặc nhiều segment files; mỗi segment chứa nhiều blocks/pages.

Một heap page chứa:

- Page header;
- Line pointers (item identifiers);
- Tuple data;
- Khoảng trống giữa line pointers và tuple data;
- Các metadata liên quan.

Một page có thể được đọc hoặc ghi qua buffer manager; query không cần truy cập filesystem trực tiếp cho mỗi row.

### 2.2. Shared buffers

PostgreSQL duy trì cache page trong **shared buffers**. Khi backend đọc một row, page tương ứng có thể được nạp vào shared buffers. Khi UPDATE/INSERT/DELETE làm page thay đổi, buffer trở thành **dirty page**.

Dirty page là page trong memory đã thay đổi so với bản tương ứng trên disk. Nó cần được ghi xuống storage vào một thời điểm thích hợp, ví dụ bởi background writer, checkpointer hoặc backend process trong một số tình huống.

### 2.3. WAL và data files là hai luồng ghi khác nhau

Một transaction thay đổi page thường tạo WAL records mô tả thay đổi. PostgreSQL phải bảo đảm WAL liên quan được ghi bền vững trước khi data page chứa thay đổi tương ứng được coi là an toàn để ghi xuống data files.

~~~text
SQL UPDATE
   |
   v
Backend sửa page trong shared buffers
   |
   +----> Tạo WAL record trong WAL buffers
   |             |
   |             v
   |        WAL file được flush theo yêu cầu
   |
   v
Dirty data page được ghi xuống data file sau đó
~~~

Đây là nguyên tắc **write-ahead logging**: WAL phải đi trước data page. Nếu hệ thống crash, PostgreSQL có thể replay WAL để đưa data files về trạng thái nhất quán.

### 2.4. Commit không nhất thiết ghi mọi data page xuống disk

Với cấu hình durability thông thường, khi transaction commit, PostgreSQL cần flush WAL commit record theo yêu cầu durability. Các data pages đã thay đổi có thể vẫn còn dirty trong shared buffers và được ghi xuống storage sau đó.

Điều này giúp commit nhanh hơn, vì không phải đợi tất cả data pages của transaction được ghi xuống disk. Crash recovery sẽ dùng WAL để replay những thay đổi chưa có trong data files.

### 2.5. WAL flush và data page flush

Hai thao tác có ý nghĩa khác nhau:

| Thao tác | Nội dung |
| --- | --- |
| WAL flush | Đưa WAL records cần thiết tới storage theo durability contract |
| Data page flush | Ghi page đã sửa từ shared buffers ra relation file |
| Checkpoint | Tạo recovery starting point và thúc đẩy ghi dirty pages theo quy trình checkpoint |
| Crash recovery | Replay WAL từ checkpoint để khôi phục trạng thái nhất quán |

**WAL đã flush không có nghĩa tất cả data pages đã flush.** Đây là một phần cốt lõi của thiết kế PostgreSQL.

## 3. Torn page write là gì?

### 3.1. Một page có thể bị ghi dở

Giả sử page có kích thước 8 KB. Storage stack có thể thực hiện một lần ghi page bằng nhiều thao tác nhỏ hơn, tùy filesystem, kernel, controller, device và alignment. Nếu mất điện hoặc kernel crash giữa các thao tác, page trên disk có thể bị trộn nội dung cũ và mới.

~~~text
Page trong shared buffers:
+----------------------------------+
|            NEW PAGE              |
+----------------------------------+

Page trên disk sau torn write:
+----------------------------------+
|       NEW       |      OLD       |
+----------------------------------+
~~~

Đây là một ví dụ khái niệm. Torn write có thể xảy ra theo nhiều dạng, không nhất thiết chia page đúng một nửa.

### 3.2. Vì sao WAL delta có thể không đủ?

Giả sử WAL chỉ lưu một thay đổi nhỏ: “đổi status của tuple X từ pending sang paid”. Trong page trên disk, phần chứa tuple header/line pointer có thể đã bị ghi dở. Khi recovery replay delta, cấu trúc page nền có thể không còn hợp lệ hoặc không còn đúng trạng thái mà WAL record mong đợi.

Một WAL record mô tả thay đổi nhỏ không nhất thiết có đủ bytes để tái tạo toàn bộ page bị torn.

### 3.3. Tình huống crash

~~~text
T0: Page P có nội dung A trên disk
T1: Transaction sửa P thành B trong memory
T2: WAL record cho thay đổi được ghi
T3: Checkpointer/background writer bắt đầu ghi P
T4: Mất điện giữa lúc ghi page
T5: Disk chứa page P trộn bytes A và B
T6: PostgreSQL khởi động và replay WAL
~~~

Nếu không có cơ chế bảo vệ full-page image, recovery có thể không có đủ thông tin để sửa một page đã bị ghi dở.

### 3.4. Atomicity của sector không đồng nghĩa atomicity của PostgreSQL page

Một storage device có thể bảo đảm atomic write ở một đơn vị sector nhất định, nhưng PostgreSQL page thường lớn hơn sector. Ngay cả khi device có atomicity ở một đơn vị nhỏ, điều đó không tự bảo đảm toàn bộ page 8 KB được ghi nguyên tử.

Đừng giả định:

- “SSD hiện đại nên không có torn writes”;
- “RAID controller có battery cache thì page luôn atomic”;
- “Filesystem journaling bảo vệ toàn bộ nội dung PostgreSQL page”;
- “WAL có rồi thì không cần full_page_writes”.

Các đảm bảo phụ thuộc storage stack cụ thể. PostgreSQL mặc định bảo vệ theo cách thận trọng.

### 3.5. Torn page khác silent corruption

Torn page thường liên quan tới ghi dở khi crash/power loss. Silent corruption có thể do:

- RAM lỗi;
- Controller/firmware lỗi;
- Media lỗi theo thời gian;
- Firmware ghi sai bytes;
- Storage/network layer trả dữ liệu không đúng;
- Software bug làm hỏng page.

Full-page writes tập trung vào phục hồi sau torn write. Data checksums có thể phát hiện nhiều trường hợp page bị hỏng khi đọc, kể cả khi không phải crash gần nhất.

## 4. WAL và checkpoint

### 4.1. WAL record

WAL (Write-Ahead Log) là chuỗi record mô tả những thay đổi cần thiết để replay database state. WAL được tổ chức theo segment files và vị trí log sequence number (LSN).

LSN là vị trí tăng dần trong WAL stream, thường được biểu diễn dạng `HEX/HEX`, ví dụ `0/16B6C50`. Nó giúp định vị record/page state trong WAL.

### 4.2. Page LSN

Data page có trường LSN trong page header để thể hiện WAL position liên quan tới lần cập nhật page gần nhất. Trong recovery, PostgreSQL dùng LSN và các quy tắc redo để xác định record nào cần replay.

Page LSN không phải checksum và không tự phát hiện mọi corruption. Nó là metadata phục vụ recovery/redo.

### 4.3. Checkpoint là gì?

Checkpoint tạo một điểm trong WAL mà từ đó PostgreSQL có thể bắt đầu crash recovery. Checkpoint process:

1. Xác định redo point;
2. Ghi các dirty buffers cần thiết xuống data files theo quy trình;
3. Đảm bảo WAL cần thiết đã được flush trước các data pages tương ứng;
4. Ghi checkpoint record và cập nhật control information;
5. Cho phép recovery bắt đầu từ checkpoint mới nhất hợp lệ.

Checkpoint **không phải backup** và không tạo một bản sao đầy đủ database có thể phục hồi độc lập.

### 4.4. Redo point

Redo point là vị trí WAL từ đó recovery có thể cần replay. Khi khởi động sau crash, PostgreSQL đọc checkpoint metadata, tìm redo start và áp dụng WAL records tiếp theo.

### 4.5. Checkpoint quá thường xuyên

Checkpoint cần flush dirty pages. Nếu xảy ra quá thường xuyên:

- Nhiều data pages phải được ghi xuống disk thường xuyên;
- Storage write load có thể tăng;
- Sau mỗi checkpoint, nhiều pages có lần sửa đầu tiên mới cần FPI;
- WAL volume có thể tăng vì full-page images;
- I/O bursts có thể ảnh hưởng latency.

### 4.6. Checkpoint quá thưa

Checkpoint thưa hơn có thể giảm tần suất FPI và write bursts, nhưng:

- Recovery sau crash có thể cần replay lượng WAL lớn hơn;
- Dirty pages tồn tại lâu hơn trước khi checkpoint;
- WAL retention và storage requirements có thể tăng;
- Thời gian recovery cần được kiểm tra theo SLA.

### 4.7. Checkpoint timeout và max_wal_size

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW checkpoint_completion_target;
~~~

- `checkpoint_timeout`: khoảng thời gian tối đa giữa các checkpoint tự động theo cấu hình.
- `max_wal_size`: ngưỡng mềm của WAL volume có thể thúc đẩy checkpoint; không phải giới hạn cứng tuyệt đối.
- `min_wal_size`: mức WAL tối thiểu được giữ/tái sử dụng theo cơ chế quản lý segment.
- `checkpoint_completion_target`: mục tiêu phân bố công việc ghi checkpoint trong khoảng thời gian giữa các checkpoints.

Các defaults thay đổi theo major version và workload. Đừng áp dụng con số từ một bài blog mà không đo hệ thống.

### 4.8. CHECKPOINT thủ công

~~~sql
CHECKPOINT;
~~~

Lệnh này yêu cầu checkpoint ngay. Nó có thể tạo I/O đáng kể và làm thay đổi thời điểm các pages cần FPI trong chu kỳ kế tiếp. Không chạy CHECKPOINT liên tục như một cách “flush database cho sạch” trong production.

## 5. Full-page writes (FPW)

### 5.1. Cơ chế chính

Khi `full_page_writes` bật, PostgreSQL ghi **toàn bộ nội dung page** vào WAL trong lần sửa đầu tiên của page đó sau checkpoint.

Ví dụ:

~~~text
Checkpoint C1
   |
   v
Page P được sửa lần đầu
   |
   +--> WAL chứa full-page image của P
   |
Page P được sửa lần thứ hai, thứ ba...
   |
   +--> WAL ghi các thay đổi thông thường (không cần FPI lặp lại cho P)
   |
Checkpoint C2
   |
   v
Lần sửa tiếp theo của P có thể tạo FPI mới
~~~

### 5.2. Vì sao chỉ cần FPI ở lần đầu sau checkpoint?

Crash recovery bắt đầu từ một checkpoint hợp lệ. Nếu page P bị ghi dở sau checkpoint, FPI đầu tiên trong WAL có thể khôi phục page P về trạng thái nguyên vẹn trước khi replay các WAL records tiếp theo.

Sau khi FPI đã có trong WAL, những lần sửa tiếp theo có thể được phục hồi bằng redo records tương ứng. Checkpoint mới tạo một chu kỳ mà lần sửa đầu tiên tiếp theo của page lại cần FPI.

### 5.3. FPI chứa gì?

FPI là ảnh page đầy đủ tại thời điểm được ghi vào WAL. Nó bao gồm page contents cần thiết để phục hồi page, không chỉ một thay đổi row nhỏ. Khi replay, PostgreSQL có thể thay thế page bị hỏng/torn bằng image rồi tiếp tục redo.

FPI có thể được nén trong WAL nếu `wal_compression` được bật và phương pháp nén phù hợp.

### 5.4. Full-page writes mặc định

~~~sql
SHOW full_page_writes;
~~~

Giá trị mặc định của PostgreSQL là `on`. Đây là cấu hình bảo vệ durability quan trọng. Tắt nó có thể làm normal operation nhanh hơn trong một số trường hợp nhưng có nguy cơ unrecoverable hoặc silent data corruption sau system failure.

### 5.5. Không tắt FPW để giảm WAL một cách tùy tiện

Tắt `full_page_writes` không phải tối ưu hóa vô hại. Nếu storage stack không bảo đảm atomic page writes, crash có thể để lại page bị torn mà WAL delta không thể phục hồi đầy đủ.

Chỉ xem xét thay đổi nếu có bằng chứng/đảm bảo cụ thể về atomic writes của toàn bộ storage stack và chấp nhận rủi ro theo đúng mức độ như các thiết lập durability nguy hiểm khác. Với hệ thống production thông thường, giữ `on`.

### 5.6. FPI không phải backup

FPI là một thành phần của WAL phục vụ crash recovery/redo, không phải bản backup đầy đủ:

- Nó chỉ được ghi cho những page cần theo quy tắc FPW;
- Không chứa mọi relation page tại một thời điểm;
- Không thay thế base backup;
- Không thay thế WAL archiving/PITR;
- Không đảm bảo phục hồi khi WAL chain hoặc storage bị mất.

### 5.7. FPI và base backup

Trong các chế độ backup/WAL logging phù hợp, PostgreSQL có thể ghi FPI liên quan để bảo đảm tính nhất quán của page khi backup được thực hiện. Chi tiết phụ thuộc backup API/protocol và phiên bản; không tự xây backup bằng cách copy data files đang chạy mà không theo quy trình PostgreSQL.

## 6. wal_log_hints và hint bits

### 6.1. Hint bits là gì?

Tuple header chứa transaction visibility metadata. PostgreSQL có thể cập nhật một số **hint bits** để ghi nhớ rằng transaction tạo/xóa tuple đã commit hoặc aborted, giúp lần đọc sau kiểm tra visibility nhanh hơn.

Hint bits là thông tin có thể suy ra từ transaction status trong một số điều kiện; chúng không giống một business UPDATE thông thường.

### 6.2. Vì sao hint bit có liên quan full-page writes?

Nếu page bị thay đổi bởi hint bit và sau đó ghi xuống disk, một torn write vẫn có thể ảnh hưởng page. Khi `wal_log_hints=on`, PostgreSQL ghi full-page image ở lần sửa đầu tiên sau checkpoint ngay cả với các hint-bit changes không quan trọng khác.

### 6.3. Cấu hình

~~~sql
SHOW wal_log_hints;
~~~

`wal_log_hints` mặc định `off` và chỉ có thể đặt khi server khởi động (server-start parameter). Bật nó làm tăng WAL logging do FPI của hint-bit modifications.

### 6.4. Data checksums làm thay đổi nhu cầu wal_log_hints

Khi data checksums được bật, các hint-bit updates được WAL-log theo cơ chế cần thiết; `wal_log_hints` không còn cần thiết cho mục đích đó và bị bỏ qua theo tài liệu PostgreSQL. Khi checksum tắt, `wal_log_hints=on` có thể được dùng để kiểm tra mức WAL overhead tương tự khi bật data checksums.

### 6.5. pg_rewind

`pg_rewind` cần đủ thông tin để đồng bộ các page thay đổi giữa hai data directories. Một trong những điều kiện liên quan là data checksums đã bật hoặc `wal_log_hints=on` (tùy version/tool requirements). Trước khi thiết kế failover/rewind, đọc đúng tài liệu `pg_rewind` của major version đang chạy và cấu hình trước khi cần.

### 6.6. Không nhầm wal_log_hints với full_page_writes

| Tham số | Vai trò |
| --- | --- |
| `full_page_writes` | FPI cho lần sửa đầu tiên của page sau checkpoint để bảo vệ torn writes |
| `wal_log_hints` | Bổ sung WAL/FPI cho hint-bit changes trong điều kiện checksum chưa bật |
| Data checksums | Kiểm tra tính toàn vẹn của data pages khi đọc/verify |

`wal_log_hints=on` không phải lý do để tắt `full_page_writes`.

## 7. wal_compression và chi phí của full-page images

### 7.1. Vì sao FPI làm WAL tăng?

Một WAL record thông thường có thể chỉ chứa thông tin về thay đổi nhỏ. FPI lại chứa gần như toàn bộ page image, thường lớn hơn nhiều so với delta record. Với workload sửa nhiều pages ngay sau checkpoint, lượng WAL có thể tăng đáng kể.

Ví dụ minh họa:

| Thành phần | WAL bytes giả định |
| --- | ---: |
| Một delta record | 100 bytes |
| Một full-page image | 8.192 bytes trước nén |

Đây chỉ là con số để hiểu tỷ lệ, không phải kích thước record thực tế. WAL record còn có headers, alignment, block references và các thông tin khác.

### 7.2. wal_compression

~~~sql
SHOW wal_compression;
~~~

`wal_compression` cho phép nén full-page images được ghi vào WAL. Khi recovery replay, PostgreSQL giải nén image trước khi sử dụng.

### 7.3. Các phương pháp nén

Ở các phiên bản hiện đại, các phương pháp có thể gồm:

- `pglz`;
- `lz4` nếu PostgreSQL được build với hỗ trợ LZ4;
- `zstd` nếu PostgreSQL được build với hỗ trợ Zstandard.

Danh sách phương pháp và cách cấu hình phụ thuộc major version/build. Giá trị `on` là cách viết lịch sử cho `pglz` ở các phiên bản đã chuyển sang enum.

### 7.4. Trade-off

Nén FPI có thể giảm WAL bytes, network transfer và archive storage, nhưng dùng CPU để compress lúc ghi WAL và decompress khi replay. Phương pháp tốt phụ thuộc:

- Page contents có nén tốt không;
- CPU headroom;
- WAL generation rate;
- Network/archive throughput;
- Recovery time objective;
- Compression method có được build hỗ trợ.

### 7.5. Không phải mọi WAL đều được nén

`wal_compression` chủ yếu nén full-page images. Nó không phải compression tổng quát cho mọi WAL records, cũng không nén tất cả data files.

### 7.6. Đo thay vì đoán

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

`wal_fpi` đếm số full-page images và `wal_bytes` là WAL bytes tích lũy theo thống kê của cluster. Các counters reset theo statistics reset. Ghi baseline trước/sau thay đổi, quan sát cùng workload window.

### 7.7. Tỷ lệ FPI

~~~sql
SELECT
    wal_records,
    wal_fpi,
    round(
        100.0 * wal_fpi / NULLIF(wal_records, 0),
        2
    ) AS fpi_per_100_records,
    pg_size_pretty(wal_bytes) AS wal_written
FROM pg_stat_wal;
~~~

Đây là tỷ lệ số lượng FPI trên số WAL records, không phải tỷ lệ bytes. Một FPI có thể lớn hơn nhiều delta record; không dùng tỷ lệ này thay cho phân tích `wal_bytes`.

## 8. Data checksums bảo vệ page như thế nào?

### 8.1. Checksum trên data page

Khi checksums được bật, mỗi data page có một checksum được tính khi page được ghi và được kiểm tra khi page được đọc. PostgreSQL có thể phát hiện page bytes không khớp với checksum đã lưu.

Checksum gắn với page/block number, giúp phát hiện một số trường hợp page bị đặt nhầm vị trí hoặc nội dung không tương ứng. Đây là kiểm tra tính toàn vẹn, không phải cơ chế mã hóa.

### 8.2. Checksum có thể phát hiện gì?

Ví dụ:

- Một số lỗi media/storage làm bytes thay đổi;
- Page bị ghi dở hoặc hỏng sau khi đã được ghi;
- Controller/firmware trả dữ liệu sai;
- Một số lỗi truyền/ghi đọc làm page content không còn khớp checksum.

Checksum không xác định chính xác thiết bị hay tầng phần mềm nào gây lỗi. Nó báo rằng page không vượt qua phép kiểm tra.

### 8.3. Checksum không sửa dữ liệu

Nếu checksum mismatch, PostgreSQL phát hiện page có vấn đề và thường báo lỗi khi đọc. Nó **không thể suy ra bytes đúng chỉ từ checksum**. Cần recovery từ WAL/FPI nếu có thể, restore từ backup hoặc một quy trình phục hồi dữ liệu phù hợp.

### 8.4. Phạm vi bảo vệ

Data checksums bảo vệ **data pages**. Chúng không bao phủ mọi file hoặc mọi byte trong data directory. Theo tài liệu PostgreSQL:

- Các data pages của relations được checksum;
- Internal data structures như một số transaction status/state files không được trực tiếp bảo vệ bằng data page checksums;
- Temporary files dùng cho sort/materialization/intermediate query data không được checksum theo cơ chế này;
- Các cấu trúc khác có thể có cơ chế WAL/CRC riêng.

Vì vậy, bật checksums không có nghĩa “mọi file trên server đều được checksum”.

### 8.5. Checksum không phải cryptographic hash

Data page checksum được thiết kế để phát hiện lỗi dữ liệu ngẫu nhiên, không phải chống kẻ tấn công cố tình sửa page. Nó không thay thế HMAC, digital signatures, encryption hoặc kiểm soát truy cập.

### 8.6. Xác suất bỏ sót

Checksum có độ rộng hữu hạn. Một số tổ hợp lỗi có thể tạo ra collision và không bị phát hiện. Vì vậy checksum giảm rủi ro silent corruption nhưng không thể bảo đảm mọi corruption đều bị phát hiện.

### 8.7. Overhead

Việc tính checksum khi ghi và kiểm tra khi đọc sử dụng CPU. Tác động hiệu năng thường nhỏ nhưng có thể khác nhau theo workload/hardware. Với PostgreSQL 18, data checksums được bật mặc định khi initdb, trừ khi dùng tùy chọn tắt.

## 9. Data page checksum khác WAL CRC

PostgreSQL bảo vệ nhiều lớp dữ liệu với các cơ chế khác nhau.

### 9.1. WAL record CRC-32C

Mỗi WAL record được bảo vệ bằng CRC-32C 32-bit. PostgreSQL tính CRC khi ghi WAL record và kiểm tra khi crash recovery, archive recovery và replication đọc record.

Nếu WAL record bị hỏng, CRC có thể phát hiện record contents không còn đúng.

### 9.2. Data page checksum

Data page checksum bảo vệ page content khi page được ghi/đọc. Nó là cơ chế riêng với WAL record CRC.

### 9.3. Full-page image cũng được bảo vệ trong WAL

Full-page images được ghi trong WAL records và WAL record CRC bảo vệ record chứa image. Vì vậy FPI trong WAL không chỉ là một blob không có kiểm tra.

### 9.4. Bảng so sánh

| Cơ chế | Đối tượng | Mục tiêu | Tự sửa dữ liệu? |
| --- | --- | --- | --- |
| Full-page write / FPI | Data page image trong WAL | Phục hồi page bị torn trong crash recovery | Có thể phục hồi page khi WAL còn nguyên và đúng |
| Data page checksum | Data pages | Phát hiện page corruption khi đọc/verify | Không |
| WAL CRC-32C | WAL records | Phát hiện WAL record corruption | Không |
| Backup manifest checksums | Backup files | Kiểm tra file backup có khớp manifest | Không |

### 9.5. Vì sao cần nhiều lớp?

Một page có thể bị ghi dở khi crash; FPI hỗ trợ phục hồi. Một page có thể bị hỏng nhiều ngày sau do media; checksum giúp phát hiện khi đọc hoặc scan verify. Một WAL segment có thể bị lỗi khi lưu trữ/truyền; WAL CRC giúp phát hiện record corruption.

Không một cơ chế nào bao phủ tất cả loại lỗi.

## 10. Bật data checksums khi tạo cluster

### 10.1. initdb --data-checksums

Khi tạo một cluster mới, có thể chỉ định:

~~~bash
initdb -D /var/lib/postgresql/data --data-checksums
~~~

Tùy chọn này bật checksums cho data pages trên toàn cluster.

### 10.2. Mặc định theo major version

Điểm cần đặc biệt chú ý:

| PostgreSQL version | Mặc định data checksums khi initdb |
| --- | --- |
| PostgreSQL 17 và các major trước đó | Tắt theo mặc định; có thể bật bằng `--data-checksums` |
| PostgreSQL 18 trở lên | Bật theo mặc định; dùng `--no-data-checksums` để tắt |

Do default thay đổi ở PostgreSQL 18, **không đoán trạng thái cluster chỉ dựa trên version**. Kiểm tra trực tiếp:

~~~sql
SHOW data_checksums;
~~~

### 10.3. initdb --no-data-checksums

Trên phiên bản mà checksums mặc định bật, có thể tắt lúc khởi tạo:

~~~bash
initdb -D /var/lib/postgresql/data --no-data-checksums
~~~

Chỉ sử dụng nếu đã có lý do vận hành cụ thể và hiểu trade-off. Với cài đặt production mới, checksum là lớp bảo vệ hữu ích.

### 10.4. Không bật checksum ở từng database/table

Data checksums là thiết lập **toàn cluster**. Không thể bật riêng cho database A, schema B hoặc table C trong cùng cluster.

### 10.5. Không đặt trong postgresql.conf

`data_checksums` là trạng thái read-only, không phải GUC có thể đổi bằng:

~~~conf
data_checksums = on
~~~

Đổi checksum state cho cluster hiện hữu cần công cụ offline `pg_checksums` và server phải shutdown sạch.

## 11. Kiểm tra trạng thái checksums

### 11.1. SHOW data_checksums

~~~sql
SHOW data_checksums;
~~~

Kết quả:

- `on`: cluster có bật data page checksums;
- `off`: cluster không bật.

Đây là cách nhanh nhất để biết trạng thái hiện tại từ SQL.

### 11.2. Kiểm tra qua pg_controldata

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Output có trường liên quan checksum version (ví dụ `Data page checksum version`). Giá trị và cách hiển thị phụ thuộc major version. `pg_controldata` hữu ích khi kiểm tra cluster offline hoặc từ máy chủ có quyền đọc data directory.

### 11.3. pg_checksums --check

Với cluster đã shutdown sạch:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data --progress
~~~

Lệnh scan các files/blocks phù hợp trong cluster để xác minh checksums. Exit status:

- `0`: không phát hiện checksum errors;
- khác `0`: có ít nhất một checksum failure hoặc thao tác kiểm tra thất bại.

Phân biệt lỗi checksum với lỗi command/permission/path; đọc stdout/stderr đầy đủ.

### 11.4. Server phải shutdown cleanly

`pg_checksums` không chạy trên cluster đang hoạt động. Server phải được shutdown sạch trước khi check/enable/disable. Không chạy cùng lúc với PostgreSQL server hoặc process khác có thể ghi vào data directory.

### 11.5. Checksum scan là công việc I/O

Với cluster nhiều terabytes, `pg_checksums --check` phải đọc một lượng lớn relation files. Lập kế hoạch thời gian, storage throughput và maintenance window. Kiểm tra trên replica hoặc bản copy có thể hữu ích nếu quy trình/consistency cho phép.

### 11.6. pg_checksums --filenode

Một số phiên bản cung cấp tùy chọn kiểm tra riêng relation theo filenode:

~~~bash
pg_checksums --check --filenode=12345 -D /var/lib/postgresql/data
~~~

Filenode là định danh vật lý relation, có thể thay đổi sau rewrite/REINDEX/DDL. Không lưu một filenode cũ rồi dùng lâu dài như tên bảng. Đọc `pg_checksums --help` của đúng version để xác nhận tùy chọn.

### 11.7. Tên công cụ theo version

Các bản PostgreSQL cũ từng dùng tên công cụ `pg_verify_checksums`. Các phiên bản hiện hành dùng `pg_checksums`. Sử dụng binary thuộc đúng major version và xác nhận bằng:

~~~bash
pg_checksums --version
pg_checksums --help
~~~

## 12. Bật hoặc tắt checksums cho cluster hiện hữu

### 12.1. pg_checksums --enable

Nếu cluster hiện tại chưa bật checksums, có thể bật offline:

~~~bash
pg_checksums --enable -D /var/lib/postgresql/data --progress
~~~

Trong quá trình enable, công cụ cập nhật checksum và ghi lại các relation file blocks cần thiết. Với cluster lớn, thao tác có thể kéo dài đáng kể và tạo lượng I/O lớn.

### 12.2. Quy trình an toàn

1. Xác định chính xác data directory và major version của binary.
2. Kiểm tra backup gần nhất và khả năng restore.
3. Lập maintenance window và thông báo downtime.
4. Shutdown PostgreSQL **sạch**.
5. Đảm bảo không có process khác ghi vào data directory/tablespaces/WAL directory.
6. Chạy `pg_checksums --enable` bằng binary đúng version.
7. Chờ command hoàn tất và đồng bộ dữ liệu xuống storage.
8. Khởi động server.
9. Xác nhận `SHOW data_checksums;` trả `on`.
10. Theo dõi logs, checksum statistics và replication health.

### 12.3. Không dùng --no-sync trên production

`pg_checksums` mặc định đợi các file được ghi an toàn xuống disk. Tùy chọn `--no-sync` bỏ bước chờ đồng bộ, nhanh hơn nhưng nếu OS crash sau đó có thể để cluster corrupt. Nó chủ yếu hữu ích cho testing; không nên dùng trong production.

### 12.4. Tắt checksums

Về kỹ thuật có thể:

~~~bash
pg_checksums --disable -D /var/lib/postgresql/data
~~~

Nhưng tắt checksums làm mất lớp phát hiện page corruption. Không dùng disable như biện pháp chữa lỗi checksum hoặc tối ưu performance mà không có đánh giá rủi ro và phê duyệt vận hành.

### 12.5. Thao tác toàn cluster

Checksum state áp dụng cho cả cluster, không phải một database. Mọi databases, shared relations và tablespaces liên quan đều nằm trong phạm vi thao tác.

### 12.6. Replication topology

Nếu có primary/standby hoặc công cụ như `pg_rewind` sao chép trực tiếp relation blocks, việc enable/disable checksum không nhất quán giữa các nodes có thể tạo page có checksum version không khớp.

Theo tài liệu PostgreSQL, khi thay đổi checksum state trong replication setup, nên shutdown tất cả clusters và chuyển đổi đồng bộ; một phương án an toàn khác là loại bỏ standbys, đổi trên primary rồi tạo lại standbys từ đầu. Thực tế cần theo runbook của sản phẩm/managed service.

### 12.7. Nếu pg_checksums bị dừng giữa chừng

Tài liệu PostgreSQL nêu rằng nếu công cụ bị abort/killed trong quá trình enable/disable, checksum configuration của cluster vẫn giữ trạng thái ban đầu và có thể chạy lại để thực hiện cùng thao tác. Tuy nhiên, không vì vậy mà chủ động kill process. Đọc exit status/log, giữ cluster offline và xử lý theo version documentation.

### 12.8. Không chạy công cụ khác version trên PGDATA

Luôn dùng `pg_checksums` từ installation có major version tương ứng. Không lấy binary PostgreSQL 18 chạy trên data directory PostgreSQL 16 hoặc ngược lại.

## 13. Theo dõi checksum failures

### 13.1. pg_stat_database

Ở các phiên bản hỗ trợ, view `pg_stat_database` có:

- `checksum_failures`: số data page checksum failures được phát hiện;
- `checksum_last_failure`: thời điểm phát hiện gần nhất.

~~~sql
SELECT
    datname,
    checksum_failures,
    checksum_last_failure,
    stats_reset
FROM pg_stat_database
ORDER BY checksum_failures DESC NULLS LAST;
~~~

Nếu checksums bị tắt, các giá trị liên quan có thể là NULL. Đây là counters tích lũy từ lần reset statistics; ghi nhận snapshot và so sánh theo thời gian.

### 13.2. Checksum failures không phải số page corrupt duy nhất

Một page có thể được đọc nhiều lần và failure counter có thể tăng theo số lần phát hiện. Không nhất thiết mỗi đơn vị counter tương ứng một page vật lý khác nhau.

### 13.3. Kiểm tra trạng thái hiện tại

~~~sql
SELECT
    current_setting('data_checksums') AS data_checksums,
    current_setting('full_page_writes') AS full_page_writes,
    current_setting('wal_log_hints') AS wal_log_hints,
    current_setting('wal_compression') AS wal_compression,
    current_setting('fsync') AS fsync;
~~~

Đây là cấu hình session đang quan sát; một số tham số chỉ thay đổi được qua cấu hình server/startup. Với managed service, cần đối chiếu cấu hình hiệu lực và quyền thay đổi.

### 13.4. Theo dõi WAL/FPI

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

View này cung cấp WAL records, full-page images, WAL bytes và một số counters liên quan write/sync. Các cột thay đổi theo version; đọc đúng tài liệu major version và so sánh cùng khoảng thời gian.

### 13.5. Theo dõi checkpoint

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Trên các major version có view này, xem số timed/requested checkpoints, buffers written và thời gian write/sync. Ở version cũ hơn, checkpoint counters có thể nằm trong `pg_stat_bgwriter`. Kiểm tra catalog views của server thực tế.

### 13.6. Log checkpoints

~~~sql
SHOW log_checkpoints;
~~~

Khi bật logging phù hợp, log checkpoint có thể cho biết lý do checkpoint, số buffers ghi và thời gian thực hiện. Dùng log để phát hiện checkpoint quá thường xuyên hoặc I/O bất thường.

### 13.7. Log checksum errors

Khi PostgreSQL phát hiện checksum mismatch, log thường có thông tin database, relation/block hoặc expected/calculated checksum tùy context/version. Ghi lại:

- Timestamp và server/node;
- Database, relation và block nếu được cung cấp;
- Expected checksum và calculated checksum;
- Query/session đã đọc page;
- Storage/OS/kernel/controller logs cùng thời điểm;
- Replication/backup state.

Không chỉ xóa log hoặc reset counters sau khi phát hiện lỗi.

## 14. Phân biệt lỗi checksum, WAL CRC và page structure

### 14.1. Data page checksum failure

Một page được đọc nhưng checksum tính lại không khớp giá trị lưu trong page. Đây là dấu hiệu page content đã thay đổi hoặc hỏng.

### 14.2. WAL CRC failure

Một WAL record không vượt qua CRC-32C khi recovery/replication/archive processing. Đây là lỗi ở WAL stream, không đồng nhất với data page checksum failure.

### 14.3. Invalid page header

PostgreSQL có thể báo page header không hợp lệ, page size/version mismatch hoặc page không có cấu trúc hợp lệ. Điều này không nhất thiết tạo cùng thông báo với checksum mismatch; page header có thể hỏng tới mức không thể thực hiện checksum bình thường.

### 14.4. OS/storage errors

Các thông báo I/O error, read failure, write failure, device reset hoặc filesystem errors có thể là nguyên nhân gốc. PostgreSQL log thường không thể một mình xác định chính xác phần cứng nào lỗi.

### 14.5. Bảng phân loại

| Dấu hiệu | Lớp có thể gặp lỗi | Việc cần làm đầu tiên |
| --- | --- | --- |
| Data page checksum mismatch | Relation data page/storage | Ghi lại relation/block, bảo vệ dữ liệu và điều tra storage |
| WAL CRC mismatch | WAL record/segment/archive | Bảo vệ WAL chain, kiểm tra archive/replication/storage |
| Invalid page header | Data page structure | Xác định page, tránh ghi đè và lập phương án restore |
| OS I/O error | Kernel/filesystem/device/controller | Kiểm tra system logs, device health và storage path |
| Backup manifest checksum mismatch | Backup artifact/transfer/storage | Cách ly backup, xác minh source/destination và bản backup khác |

## 15. ignore_checksum_failure và xử lý page hỏng

### 15.1. Mặc định là báo lỗi

Khi data checksum mismatch xảy ra lúc đọc, PostgreSQL thông thường báo lỗi và abort transaction đang thực hiện. Đây là hành vi bảo vệ: ứng dụng không nên tiếp tục xử lý dữ liệu mà server đã xác định không đáng tin.

### 15.2. ignore_checksum_failure

~~~sql
SHOW ignore_checksum_failure;
~~~

Tham số này mặc định `off`. Khi bật, PostgreSQL có thể bỏ qua checksum failure sau khi vẫn phát warning và tiếp tục trong một số tình huống nếu page header còn đủ hợp lệ.

### 15.3. Đây không phải giải pháp sửa chữa

> Bật `ignore_checksum_failure` có thể dẫn đến crash, lan truyền hoặc che giấu corruption và gây hậu quả nghiêm trọng. Nó chỉ có thể hữu ích trong tình huống khẩn cấp để cố gắng đọc các tuples còn nguyên trên một page hỏng, khi đã hiểu rõ rủi ro và đang thực hiện recovery.

Không bật nó như cấu hình thường trực, không dùng để làm cho monitoring “xanh”, và không coi dữ liệu đọc được là đáng tin cậy.

### 15.4. zero_damaged_pages

PostgreSQL có tùy chọn recovery đặc biệt `zero_damaged_pages` để cho phép bỏ qua một số damaged pages bằng cách thay page hỏng bằng page zeroed. Điều này có thể làm mất toàn bộ rows nằm trong page đó. Nó là biện pháp cứu hộ dữ liệu có chọn lọc, không phải sửa chữa không mất dữ liệu.

### 15.5. Các bước phản ứng ban đầu

1. Ghi lại lỗi và page/relation/block;
2. Hạn chế writes có thể làm tình trạng tệ hơn nếu cần và theo runbook;
3. Kiểm tra storage, kernel, filesystem và hardware logs;
4. Kiểm tra checksum failures, WAL/archive integrity và standby state;
5. Xác định page có thể được phục hồi từ WAL/FPI trong recovery hay cần restore;
6. Bảo vệ backup hiện có trước khi thử thao tác destructive;
7. Khôi phục trên bản copy/standby/backup phù hợp và xác minh kết quả.

### 15.6. Không tự sửa bytes trong relation file

Không dùng hex editor, `dd`, script tự ghi bytes hoặc copy một page từ node khác vào relation file đang hoạt động. Page format có metadata/LSN/visibility state và có thể khác transaction history. Một thao tác ghi trực tiếp có thể làm mất dữ liệu hoặc khiến cluster không thể recovery.

## 16. FPI trong crash recovery

### 16.1. Recovery bắt đầu từ checkpoint

Khi PostgreSQL khởi động sau crash, nó đọc control information và checkpoint gần nhất hợp lệ, sau đó replay WAL từ redo point. Những record đã được áp dụng vào data files có thể được bỏ qua dựa trên page LSN/redo logic; những thay đổi còn thiếu sẽ được replay.

### 16.2. FPI xử lý page bị ghi dở

Giả sử:

1. Checkpoint C hoàn tất;
2. Page P được sửa lần đầu sau C và WAL ghi FPI của P;
3. P được ghi xuống disk nhưng bị torn;
4. Máy chủ crash;
5. Recovery bắt đầu từ C;
6. PostgreSQL replay WAL và dùng FPI để đưa P về page image nguyên vẹn;
7. Các WAL changes sau FPI được redo theo thứ tự.

Đó là cách FPI bảo vệ page khỏi torn writes trong crash recovery.

### 16.3. Nếu WAL chứa FPI cũng bị hỏng?

WAL record có CRC-32C. Nếu record chứa FPI bị hỏng, CRC có thể phát hiện vấn đề. Khi WAL chain/segment cần thiết không còn nguyên vẹn, recovery có thể không hoàn tất. Cần kiểm tra WAL archive, base backup và standby theo recovery plan.

### 16.4. FPI không tự khôi phục corruption xảy ra sau recovery

Nếu page bị hỏng do media failure nhiều giờ sau khi cluster đã khởi động và chạy bình thường, PostgreSQL không tự tua lại từ checkpoint cũ chỉ vì checksum mismatch. Cần phục hồi page/cluster từ backup và WAL hoặc dùng phương án phục hồi đã được kiểm chứng.

### 16.5. WAL phải được giữ đủ lâu

Crash recovery dùng WAL còn trong cluster. PITR cần base backup và chuỗi WAL liên tục bắt đầu từ backup đó tới thời điểm mục tiêu. FPI không giúp nếu các WAL segments cần thiết đã bị xóa hoặc archive bị thiếu.

## 17. Full-page writes, fsync và các thiết lập durability

### 17.1. full_page_writes không thay fsync

`full_page_writes` bảo vệ page khỏi torn write bằng FPI. `fsync` giúp PostgreSQL yêu cầu hệ điều hành đồng bộ dữ liệu/WAL xuống storage theo durability contract.

Nếu `fsync=off`, PostgreSQL có thể không bảo đảm WAL/data đã được ghi bền vững trước khi hệ thống báo thành công. FPW không thể bù cho một storage stack bỏ qua yêu cầu flush hoặc mất WAL đã được xác nhận.

### 17.2. Kiểm tra fsync

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW wal_sync_method;
SHOW full_page_writes;
~~~

Với hệ thống production cần durability thông thường, `fsync` nên bật. Không tắt nó như cách khắc phục I/O chậm mà không hiểu nguy cơ mất/corrupt database.

### 17.3. synchronous_commit khác full_page_writes

`synchronous_commit` điều khiển thời điểm transaction được xác nhận commit so với WAL flush (và synchronous replication acknowledgment nếu cấu hình). Đặt `synchronous_commit=off` có thể làm mất các transaction vừa được báo commit khi crash, nhưng đó là trade-off durability/latency khác với việc tắt FPW.

Không nhầm:

- `synchronous_commit`: độ bền của commit acknowledgment;
- `fsync`: đồng bộ dữ liệu xuống storage;
- `full_page_writes`: FPI để bảo vệ page khỏi torn write;
- `data_checksums`: phát hiện page corruption.

### 17.4. Storage cache phải thực sự honor flush

PostgreSQL gửi yêu cầu đồng bộ theo `wal_sync_method`/OS. Nếu controller hoặc drive báo flush thành công trong khi dữ liệu vẫn nằm trong volatile cache, power loss có thể làm mất WAL/data đã được coi là bền vững.

Quản trị viên cần xác minh:

- Controller write cache có battery/flash-backed protection hay không;
- SSD/drive có honor cache flush/FUA đúng không;
- Filesystem/storage stack có đảm bảo ordering và flush semantics không;
- Firmware, kernel và multipath có lỗi đã biết không;
- Cloud/block storage có durability contract phù hợp.

### 17.5. ECC RAM và hardware monitoring

PostgreSQL không thể phát hiện mọi lỗi RAM trước khi bytes được ghi thành page/WAL hợp lệ. Sử dụng ECC RAM hoặc lớp bảo vệ tương đương, theo dõi machine-check events, SMART/device health và controller logs.

### 17.6. Full-page writes không phải anti-malware

FPW và checksums không bảo vệ khỏi người có quyền sửa/xóa database, ransomware, lỗi ứng dụng logic, SQL injection hay xóa nhầm dữ liệu. Phải có authentication, least privilege, backup tách biệt/immutable và disaster recovery.

## 18. Checksum, backup và PITR

### 18.1. Base backup vẫn cần thiết

Data checksums giúp phát hiện page lỗi; WAL giúp replay thay đổi; nhưng nếu relation file bị hỏng nghiêm trọng hoặc WAL cần thiết không còn, vẫn cần base backup hợp lệ để phục hồi.

### 18.2. PITR

Point-in-time recovery thường cần:

- Một base backup hợp lệ;
- WAL liên tục từ thời điểm backup yêu cầu đến target recovery time;
- Archive/restore command đúng;
- Cấu hình recovery target phù hợp;
- Storage và capacity đủ để restore.

FPI trong WAL giúp replay page changes an toàn hơn trong quá trình recovery; nó không thay thế base backup.

### 18.3. pg_verifybackup

`pg_verifybackup` có thể kiểm tra backup directory dựa trên manifest và xác minh một số tính nhất quán/WAL theo options của phiên bản. Nó là công cụ khác với `pg_checksums`:

- `pg_checksums`: kiểm tra page checksums trên một cluster offline;
- `pg_verifybackup`: kiểm tra tính toàn vẹn backup theo backup manifest và các kiểm tra được hỗ trợ.

Không kết luận backup có thể restore chỉ vì một checksum scan thành công. Phải thực hiện **restore test** định kỳ.

### 18.4. Backup không nên nằm cùng failure domain

Nếu backup, WAL archive và primary cùng nằm trên một storage failure domain, một lỗi controller/volume hoặc thao tác xóa nhầm có thể ảnh hưởng tất cả. Giữ bản backup tách biệt theo kiến trúc DR, có retention, access controls và kiểm thử phục hồi.

### 18.5. Kiểm tra backup định kỳ

Một lịch kiểm tra nên bao gồm:

1. Xác nhận backup job thành công;
2. Xác minh manifest/checksums của backup;
3. Kiểm tra WAL archive continuity;
4. Restore vào môi trường tách biệt;
5. Xác nhận server khởi động và recovery hoàn tất;
6. Chạy query validation/ứng dụng smoke tests;
7. Ghi lại RPO/RTO thực tế.

### 18.6. Page checksum không phải backup checksum

Checksum của page được lưu trong page header và dùng để kiểm tra page. Backup manifest checksum bảo vệ file backup trong quá trình lưu/truyền. Hai loại checksum có mục tiêu và phạm vi khác nhau.

## 19. FPI và checkpoint tuning

### 19.1. Tăng checkpoint interval có thể giảm FPI frequency

Vì mỗi page thường chỉ cần FPI ở lần sửa đầu tiên sau checkpoint, checkpoint dày hơn làm nhiều pages phải ghi FPI thường xuyên hơn. Tăng `checkpoint_timeout` hoặc `max_wal_size` có thể giảm số checkpoint và giảm FPI volume trong một số workload.

### 19.2. Đổi lại crash recovery có thể lâu hơn

Checkpoint thưa hơn có thể làm redo distance lớn hơn. Sau crash, PostgreSQL có thể cần replay nhiều WAL records hơn trước khi phục vụ đầy đủ.

### 19.3. Checkpoint completion target

`checkpoint_completion_target` giúp trải đều ghi dirty buffers trong khoảng thời gian checkpoint. Mục tiêu là tránh write burst, không phải giảm trực tiếp số FPI theo cách độc lập.

### 19.4. max_wal_size không phải hard cap

WAL có thể vượt `max_wal_size` trong một số tình huống như high load, archive failure hoặc replication retention. Không dùng con số này làm giới hạn cứng cho dung lượng `pg_wal`.

### 19.5. WAL retention và replication slots

Replication slots/archiving có thể giữ WAL segments lâu hơn checkpoint/recycle policy thông thường. Kiểm tra slot lag, archive failures và disk headroom; không xóa WAL files thủ công.

### 19.6. Đo checkpoint và FPI trước khi tune

Ghi lại:

- Số checkpoint theo thời gian;
- Timed vs requested checkpoints;
- `wal_fpi` và `wal_bytes`;
- Checkpoint write/sync time;
- Disk write latency/IOPS;
- Recovery time trong test;
- Replication/archive throughput.

Thay đổi từng tham số trong staging hoặc một cửa sổ có kiểm soát, rồi so sánh cùng workload. Không tăng `checkpoint_timeout` chỉ vì muốn giảm WAL mà bỏ qua recovery SLA.

### 19.7. Không tắt full_page_writes để chữa checkpoint pressure

Nếu FPI làm WAL tăng, trước hết xem checkpoint interval, `wal_compression`, storage throughput và workload. Tắt FPW loại bỏ một lớp bảo vệ torn page và không phải giải pháp mặc định an toàn.

## 20. Lab: quan sát FPI và WAL trong môi trường thử nghiệm

Lab này dùng một database/schema riêng và chỉ quan sát thống kê WAL. Không cố tình làm hỏng relation files, tắt fsync hoặc tắt full_page_writes để tạo crash. Việc mô phỏng torn write cần storage/fault-injection environment chuyên biệt và không phù hợp trên máy đang chứa dữ liệu thật.

### 20.1. Kiểm tra cấu hình ban đầu

~~~sql
SHOW server_version;
SHOW full_page_writes;
SHOW wal_log_hints;
SHOW wal_compression;
SHOW fsync;
SHOW data_checksums;
~~~

Ghi lại kết quả và version. `data_checksums` là read-only; giá trị mặc định phụ thuộc major version và cách cluster được khởi tạo.

### 20.2. Xem baseline WAL stats

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

Lưu kết quả cùng timestamp. Nếu đây là shared lab có người khác chạy query, các counters sẽ bao gồm hoạt động của toàn cluster.

### 20.3. Tạo table lab

~~~sql
CREATE SCHEMA copy448;

CREATE TABLE copy448.fpw_demo (
    id integer PRIMARY KEY,
    payload text NOT NULL
);

INSERT INTO copy448.fpw_demo(id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 10000) AS g;
~~~

### 20.4. Tạo checkpoint trong lab

~~~sql
CHECKPOINT;
~~~

Lệnh checkpoint cần quyền phù hợp và có thể tạo I/O. Chỉ thực hiện trong lab không có workload quan trọng; không dùng lệnh này lặp đi lặp lại trên production để “ép” FPI.

### 20.5. Sửa một số rows

~~~sql
UPDATE copy448.fpw_demo
SET payload = payload || '-updated'
WHERE id BETWEEN 1 AND 100;
~~~

UPDATE làm thay đổi các heap pages chứa rows. Với `full_page_writes=on`, lần sửa đầu tiên của mỗi page sau checkpoint có thể tạo FPI.

### 20.6. Đọc WAL stats sau UPDATE

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

So sánh với baseline. `wal_fpi` có thể tăng; mức tăng phụ thuộc page layout, checkpoint, indexes, concurrent activity và loại WAL records.

### 20.7. Sửa cùng vùng page lần nữa

~~~sql
UPDATE copy448.fpw_demo
SET payload = payload || '-again'
WHERE id BETWEEN 1 AND 100;
~~~

Nếu vẫn trong cùng checkpoint cycle, cùng page thường không cần một FPI mới cho mỗi UPDATE. Tuy nhiên, không suy ra số FPI phải bằng zero: những pages khác có thể bị sửa lần đầu và các hoạt động khác trong cluster vẫn tạo FPI.

### 20.8. Tạo checkpoint tiếp theo

~~~sql
CHECKPOINT;
~~~

Sau checkpoint, lần sửa đầu tiên tiếp theo của mỗi page lại có thể tạo FPI mới.

### 20.9. Không reset thống kê shared trên production

Trong lab riêng có thể reset WAL stats nếu cần một phép đo sạch và có quyền:

~~~sql
SELECT pg_stat_reset_shared('wal');
~~~

Không reset shared statistics trên production chỉ để làm một biểu đồ. Reset làm mất baseline tích lũy của các dashboards/monitoring khác.

### 20.10. Kiểm tra data checksum state

~~~sql
SHOW data_checksums;

SELECT
    datname,
    checksum_failures,
    checksum_last_failure
FROM pg_stat_database;
~~~

Nếu checksums đang bật, thông thường không có failure và `checksum_failures` bằng 0. Không tạo checksum mismatch giả bằng cách sửa bytes relation file.

### 20.11. Lab pg_checksums offline

Trên máy lab có PostgreSQL installation và data directory riêng, tạo cluster không checksum theo cú pháp phù hợp major version, dừng server sạch, rồi chạy:

~~~bash
pg_checksums --enable -D /path/to/lab-data --progress
pg_checksums --check -D /path/to/lab-data --progress
~~~

Sau khi bật, khởi động cluster và xác nhận `SHOW data_checksums;` là `on`. Chỉ chạy trên **cluster lab offline**; tuyệt đối không trỏ vào PGDATA production đang chạy.

### 20.12. Không mô phỏng corruption bằng file thật

Không dùng `dd`, hex editor hoặc script ghi byte ngẫu nhiên vào relation file để thử checksum trên cluster đang dùng. Nếu cần kiểm thử phát hiện corruption, sử dụng một disposable cluster, bản sao có thể bỏ, và quy trình fault injection đã được DBA phê duyệt.

### 20.13. Dọn schema lab

~~~sql
DROP SCHEMA copy448 CASCADE;
~~~

Chỉ chạy nếu schema đúng là schema thử nghiệm và không chứa dữ liệu cần giữ.

## 21. Quy trình vận hành và kiểm tra tính toàn vẹn

### 21.1. Khi tạo cluster mới

1. Chọn major version được hỗ trợ.
2. Kiểm tra default checksum của version.
3. Bật data checksums theo policy (PG18 mặc định bật).
4. Giữ `full_page_writes=on`.
5. Giữ `fsync=on`.
6. Đảm bảo WAL và data nằm trên storage có flush semantics đáng tin cậy.
7. Thiết kế base backup, WAL archive và restore test.
8. Ghi lại checksum state và durability settings vào inventory.

### 21.2. Khi nâng cấp major version

Đừng giả định checksum state tự thay đổi theo default của major version mới. Cluster được nâng cấp vẫn mang trạng thái checksum đã có theo quy trình upgrade; kiểm tra `SHOW data_checksums` sau upgrade và theo tài liệu của phương thức upgrade đang dùng.

### 21.3. Khi clone/restore cluster

Kiểm tra:

- Backup source có checksum state nào;
- Tool restore/copy có giữ đúng page bytes và control metadata không;
- Standby/new primary có checksum state nhất quán không;
- `pg_rewind` prerequisites;
- WAL archive/backup manifest integrity;
- `SHOW data_checksums` sau khi start.

### 21.4. Khi có checksum failure

- Ghi lại error và relation/block;
- Không bật `ignore_checksum_failure` như cấu hình thường trực;
- Kiểm tra OS/storage/hardware logs;
- Xác minh backup/WAL/standby;
- Chạy checksum verification trên bản offline phù hợp;
- Chọn restore/PITR hoặc salvage theo runbook;
- Mở incident với storage provider nếu có bằng chứng lỗi phần cứng;
- Sau phục hồi, chạy kiểm tra và theo dõi lại.

### 21.5. Khi có WAL CRC error

- Bảo vệ bản WAL/segment bị lỗi và log;
- Kiểm tra archive copy/replica copy;
- Xác định lỗi ở primary, standby, archive store hay transfer;
- Không xóa/đổi tên WAL files để ép server start;
- Dùng base backup và WAL chain hợp lệ để restore nếu cần.

### 21.6. Khi thay đổi full_page_writes/wal_compression

Ghi lại:

- Lý do thay đổi;
- Current value và target value;
- Version hỗ trợ;
- WAL FPI/bytes trước/sau;
- CPU, I/O, replication/archive throughput;
- Crash recovery test time;
- Rollback plan.

Không thay đổi nhiều durability parameters cùng lúc nếu không có lý do và cách đo tách biệt.

### 21.7. Kiểm tra định kỳ

Một lịch vận hành có thể gồm:

- Mỗi ngày: checksum failure counters, database logs, disk/controller alerts;
- Mỗi tuần: WAL generation, checkpoint frequency, archive/replication health;
- Theo lịch backup: `pg_verifybackup`, restore test và PITR drill;
- Theo maintenance window: offline `pg_checksums --check` khi phù hợp;
- Sau firmware/storage changes: kiểm thử flush/durability và theo dõi lỗi.

Tần suất thực tế phụ thuộc dung lượng, SLA, chi phí downtime và policy tổ chức.

## 22. Troubleshooting: các tình huống thường gặp

### 22.1. pg_checksums báo server đang chạy

Nguyên nhân: cluster chưa shutdown hoặc một PostgreSQL process khác vẫn đang truy cập data directory.

Hướng xử lý:

1. Xác nhận đúng PGDATA và instance;
2. Shutdown sạch bằng service manager/pg_ctl;
3. Xác minh không còn server process;
4. Kiểm tra không có tool khác đang ghi vào tablespaces/WAL directory;
5. Chạy lại binary đúng major version.

Không kill -9 server chỉ để công cụ chạy được.

### 22.2. pg_checksums báo checksum failure

Đây là bằng chứng có block không vượt qua checksum check. Ghi lại file/relation/filenode/block và output đầy đủ. Bảo vệ data directory, backup và logs; kiểm tra storage path và restore plan. Không disable checksum để làm lệnh trả exit code 0.

### 22.3. SHOW data_checksums trả off

Điều này có thể là cluster được initdb trên PG17 hoặc cũ hơn mà không dùng `--data-checksums`, hoặc PG18+ được tạo với `--no-data-checksums`, hoặc checksum đã bị disable offline. Không suy ra lỗi; kiểm tra policy, lịch sử tạo/upgrade và đánh giá bật offline.

### 22.4. PostgreSQL 18 mới tạo nhưng checksum không như mong đợi

PG18 mặc định bật checksums, nhưng người cài đặt có thể dùng `--no-data-checksums`. Kiểm tra `SHOW data_checksums`, không chỉ nhìn version.

### 22.5. FPI tăng mạnh sau checkpoint

Điều này có thể là hành vi bình thường khi nhiều pages được sửa lần đầu sau checkpoint. So sánh `wal_fpi`, `wal_bytes`, checkpoint frequency và workload. Kiểm tra checkpoint bị requested quá thường xuyên, base backup và các hoạt động ghi nhiều pages.

### 22.6. WAL volume tăng sau khi bật wal_log_hints

`wal_log_hints=on` có thể làm nhiều hint-bit page modifications tạo FPI. So sánh trước/sau với workload tương tự. Nếu data checksums đã bật, hint-bit updates đã được WAL-log và setting này bị bỏ qua theo semantics tài liệu.

### 22.7. wal_compression không nhận lz4/zstd

Có thể server build không hỗ trợ codec đó hoặc major version không có option tương ứng. Xem `SHOW wal_compression`, `pg_settings` và tài liệu/build options; không ép cấu hình từ server khác.

### 22.8. pg_stat_database checksum_failures là NULL

NULL có thể nghĩa data checksums đang tắt, không phải counter bằng 0. Xác nhận bằng `SHOW data_checksums`.

### 22.9. Checksum failure nhưng pg_checksums --check không báo

Có thể trạng thái page đã thay đổi, relation được rewrite, lỗi không còn tái hiện hoặc công cụ/check path khác với nơi phát hiện ban đầu. Giữ log gốc, đối chiếu filenode/block, server/node và thời điểm. Một lần scan sạch không xóa bỏ incident đã xảy ra.

### 22.10. WAL CRC error nhưng page checksums vẫn bật

Hai lớp kiểm tra khác nhau. Data page checksums không xác minh mọi WAL segment. Bảo vệ WAL segment/archive và kiểm tra CRC, transfer, filesystem/storage, backup và replication path.

### 22.11. Checksum failure sau khi restore/copy standby

Kiểm tra:

- Các nodes có cùng checksum state/version không;
- Công cụ copy có chuyển đúng relation blocks và control files không;
- Có đổi checksum state khi standby vẫn hoạt động không;
- Restore/copy có hoàn tất và đồng bộ files không;
- Version binary/tool có tương thích không.

### 22.12. pg_rewind không chạy được

Kiểm tra điều kiện prerequisites của đúng version, gồm data checksums hoặc `wal_log_hints` nếu cần, WAL availability, timeline/history và quyền truy cập. Không bật `wal_log_hints` sau khi divergence đã xảy ra rồi mặc định rằng WAL cũ đã có đủ thông tin.

### 22.13. FPI tăng dù không có nhiều UPDATE

Các hoạt động khác như VACUUM, hint-bit changes (tùy checksum/wal_log_hints), index maintenance, bulk operations hoặc base backup có thể làm WAL/FPI tăng. Dùng `pg_stat_wal`, checkpoint logs và workload tracing để xác định nguồn.

### 22.14. Tắt FPW làm giảm WAL nhưng recovery không an toàn

Đây là trade-off nguy hiểm. Bật lại `full_page_writes` theo cấu hình server, kiểm tra storage atomic-write guarantees và thực hiện test crash/recovery trên staging. Không dùng số WAL bytes thấp hơn làm tiêu chí duy nhất.

### 22.15. Disk đầy khi pg_checksums enable

Không khởi động cluster hoặc tiếp tục ghi thêm nếu operation chưa rõ trạng thái. Đọc exit status/log và tài liệu version; bảo vệ bản sao/backup, xác nhận checksum config state, xử lý disk capacity rồi mới chạy lại theo quy trình offline. Không xóa relation/WAL files để giải phóng chỗ.

## 23. Bài tập thực hành: WAL, FPI và checksums

Các bài tập dùng một PostgreSQL lab riêng. Những câu hỏi về corruption chỉ yêu cầu suy luận hoặc mô tả recovery plan; **không được sửa bytes của data files trên database thật**. Một số câu yêu cầu kiểm tra documentation theo major version đang học.

### Bài 1 — Page và block

Giải thích page/block trong PostgreSQL là gì, thường có kích thước bao nhiêu và heap page chứa những thành phần nào.

### Bài 2 — Dirty page

Sau một UPDATE, page trong shared buffers thay đổi. Vì sao nó được gọi là dirty page? Process nào có thể ghi page xuống data file?

### Bài 3 — WAL trước data page

Mô tả write-ahead rule. Điều gì có thể xảy ra nếu data page được ghi bền vững trước WAL records cần thiết?

### Bài 4 — Commit không flush mọi data page

Một transaction commit thành công nhưng một số dirty pages vẫn ở shared buffers. Vì sao điều này không vi phạm durability khi WAL được flush đúng?

### Bài 5 — Torn page write

Một page 8 KB được ghi bằng nhiều sector writes. Máy chủ mất điện sau khi một số sector đã ghi. Mô tả page trên disk có thể ở trạng thái nào.

### Bài 6 — WAL delta không đủ

WAL chỉ mô tả thay đổi một tuple, nhưng page nền bị torn. Giải thích vì sao replay delta có thể không khôi phục được cấu trúc page.

### Bài 7 — FPI

Định nghĩa full-page image. FPI được ghi vào WAL vào thời điểm nào khi `full_page_writes=on`?

**Đáp án:** lần sửa đầu tiên của mỗi page sau checkpoint.

### Bài 8 — FPI sau checkpoint

Một page được sửa 5 lần sau checkpoint C1, rồi checkpoint C2 chạy. Lần sửa đầu tiên sau C2 có thể tạo FPI mới không? Giải thích.

### Bài 9 — Tại sao không FPI mỗi UPDATE?

Phân tích chi phí WAL nếu PostgreSQL ghi full page image cho mỗi thay đổi nhỏ, thay vì lần sửa đầu sau checkpoint.

### Bài 10 — Checkpoint

Giải thích checkpoint làm gì và tại sao checkpoint không phải backup.

### Bài 11 — Redo point

Redo point là gì? PostgreSQL dùng nó như thế nào khi crash recovery?

### Bài 12 — Page LSN

Page LSN dùng để làm gì? Vì sao nó không phải checksum?

### Bài 13 — Checkpoint quá thường xuyên

Một server có checkpoint mỗi phút và FPI tăng mạnh. Giải thích mối quan hệ giữa checkpoint interval và WAL full-page images.

### Bài 14 — Checkpoint quá thưa

Một DBA tăng `checkpoint_timeout` rất cao để giảm WAL. Nêu ít nhất ba trade-offs cần đánh giá.

### Bài 15 — max_wal_size

Giải thích tại sao `max_wal_size` là soft limit, không phải hard cap của `pg_wal`.

### Bài 16 — CHECKPOINT thủ công

Tại sao không nên chạy `CHECKPOINT` liên tục trên production để ép ghi data pages?

### Bài 17 — full_page_writes

Kiểm tra bằng `SHOW full_page_writes`. Mặc định là gì? Điều gì có thể xảy ra nếu tắt nó khi storage không bảo đảm atomic page writes?

### Bài 18 — FPI và backup

Giải thích vì sao FPI trong WAL không thay thế base backup và WAL archiving/PITR.

### Bài 19 — wal_log_hints

Hint bits là gì? `wal_log_hints=on` ảnh hưởng WAL như thế nào?

### Bài 20 — Data checksums và wal_log_hints

Khi data checksums được bật, vì sao `wal_log_hints` không còn cần thiết cho hint-bit WAL logging?

### Bài 21 — pg_rewind

Nêu lý do một hệ thống chuẩn bị dùng pg_rewind cần kiểm tra data checksums hoặc `wal_log_hints` từ trước.

### Bài 22 — wal_compression

Nêu dữ liệu nào được nén bởi `wal_compression`, những codec có thể hỗ trợ và trade-off CPU.

### Bài 23 — WAL stats

Viết query đọc `wal_records`, `wal_fpi`, `wal_bytes` từ `pg_stat_wal`. Vì sao phải so sánh trong cùng workload window?

### Bài 24 — FPI ratio

Một dashboard hiển thị FPI/records = 20%. Có thể kết luận 20% WAL bytes là FPI không? Giải thích.

### Bài 25 — Page checksum

Data page checksum được tính khi nào và kiểm tra khi nào? Nó giúp phát hiện loại lỗi nào?

### Bài 26 — Checksum không tự sửa

Một page checksum mismatch. Vì sao PostgreSQL không thể tự khôi phục bytes đúng chỉ từ checksum?

### Bài 27 — Page checksum vs WAL CRC

So sánh mục tiêu, đối tượng và độ rộng của data page checksum với WAL record CRC-32C.

### Bài 28 — FPI checksum

Vì sao full-page images được ghi trong WAL cũng được bảo vệ bởi WAL record CRC?

### Bài 29 — Checksum không phải cryptographic hash

Giải thích tại sao page checksum không chống được một attacker có quyền chủ động sửa bytes.

### Bài 30 — Phạm vi checksum

Nêu ví dụ các internal structures và temporary files không được data page checksums bảo vệ trực tiếp.

### Bài 31 — PostgreSQL 17 vs 18

Nêu khác biệt default data checksums khi initdb giữa PostgreSQL 17 và PostgreSQL 18. Vì sao phải chạy `SHOW data_checksums` thay vì đoán từ version?

### Bài 32 — initdb

Viết lệnh initdb bật data checksums khi tạo cluster mới. Lệnh này áp dụng cho phạm vi nào?

### Bài 33 — Cluster đã tồn tại

Có thể đổi `data_checksums` bằng cách thêm vào postgresql.conf rồi reload không? Vì sao?

### Bài 34 — pg_checksums offline

Mô tả điều kiện bắt buộc trước khi chạy `pg_checksums --check`, `--enable` hoặc `--disable`.

### Bài 35 — pg_checksums exit status

Giải thích exit code 0 và non-zero khi chạy `pg_checksums --check`. Vì sao cần đọc cả logs/output?

### Bài 36 — Enable checksums

Lập thứ tự các bước enable checksums cho cluster lớn: backup, shutdown, scan/enable, sync, restart, verify.

### Bài 37 — Replication

Primary và standby có checksum state không nhất quán sau thao tác offline. Nêu rủi ro với công cụ sao chép page trực tiếp và phương án xử lý an toàn.

### Bài 38 — pg_stat_database

Viết query đọc `checksum_failures` và `checksum_last_failure`. Nếu giá trị là NULL, điều gì có thể được suy ra?

### Bài 39 — Checksum failure lặp lại

Một page checksum failure tăng nhiều lần. Vì sao counter không nhất thiết tương ứng với số page vật lý duy nhất?

### Bài 40 — pg_checksums scan

Một cluster 8 TB cần `pg_checksums --check`. Hãy lập kế hoạch thời gian, I/O, downtime và nơi lưu kết quả.

### Bài 41 — ignore_checksum_failure

Giải thích tác dụng và rủi ro của `ignore_checksum_failure`. Vì sao không nên để on thường trực?

### Bài 42 — zero_damaged_pages

Vì sao tùy chọn này có thể giúp cứu một phần dữ liệu nhưng cũng làm mất rows? Khi nào cần cân nhắc?

### Bài 43 — WAL CRC error

Phân biệt WAL CRC error với data page checksum failure. Nêu các vị trí cần kiểm tra: primary, archive, standby và transfer.

### Bài 44 — Storage cache

Một controller có write-back cache không được bảo vệ bằng battery/flash. Vì sao PostgreSQL có thể nhận tín hiệu flush thành công nhưng dữ liệu vẫn mất khi mất điện?

### Bài 45 — fsync

Vì sao full_page_writes không bù được cho `fsync=off`? Phân biệt hai tham số.

### Bài 46 — synchronous_commit

Phân biệt `synchronous_commit=off` với `full_page_writes=off`. Một tham số liên quan commit acknowledgment, tham số còn lại bảo vệ điều gì?

### Bài 47 — Backup verification

So sánh vai trò của `pg_checksums`, `pg_verifybackup` và một restore test thực tế.

### Bài 48 — PITR

Một base backup tốt nhưng WAL archive thiếu segment ở giữa. Có thể PITR tới thời điểm sau segment bị thiếu không? Giải thích.

### Bài 49 — Checksum incident

Thiết kế runbook khi production phát hiện checksum mismatch: bảo vệ evidence, kiểm tra hardware, backup/WAL/standby, salvage và restore.

### Bài 50 — Capstone: thiết kế durability cho PostgreSQL

Một hệ thống thanh toán cần durability cao, 3 TB data, primary/standby, WAL archive và backup hàng ngày. Team muốn giảm WAL vì storage archive tốn chi phí.

**Yêu cầu:**

1. Vẽ đường đi của UPDATE từ shared buffers qua WAL tới data files.
2. Giải thích torn page write và vai trò của FPI.
3. Xác định `full_page_writes`, `fsync` và checksum policy.
4. Xác định checksum defaults theo major version và cách xác minh trạng thái.
5. Đề xuất `wal_compression` theo codec được build hỗ trợ.
6. Đo `wal_fpi`, `wal_bytes`, checkpoint frequency và recovery time trước/sau.
7. Tối ưu checkpoint interval nhưng giữ crash recovery trong SLA.
8. Định nghĩa quy trình enable/checksum verification offline cho cluster và standbys.
9. Xây monitoring cho checksum failures, WAL CRC errors, archive lag và storage health.
10. Lập quy trình backup manifest verification và restore/PITR drill.
11. Viết incident runbook cho checksum mismatch và WAL corruption.
12. Nêu rõ những thao tác tuyệt đối không chạy trực tiếp trên production khi chưa có backup/maintenance plan.

**Tiêu chí đạt:** người học phải phân biệt được cơ chế **ngăn/khôi phục torn page**, cơ chế **phát hiện corruption**, và cơ chế **khôi phục từ backup/WAL**; đồng thời chứng minh durability không phụ thuộc một tham số đơn lẻ.

## 24. Checklist bảo vệ tính toàn vẹn

### 24.1. Khi khởi tạo cluster

- [ ] Đã xác nhận major version và default data checksum của version đó.
- [ ] Đã kiểm tra `SHOW data_checksums` sau khi khởi tạo.
- [ ] Đã giữ `full_page_writes=on` theo policy durability.
- [ ] Đã giữ `fsync=on` cho production durability thông thường.
- [ ] Đã kiểm tra storage/controller/drive có honor flush đúng.
- [ ] Đã thiết kế WAL archive, base backup và restore test.
- [ ] Đã kiểm thử restore trên môi trường tách biệt.
- [ ] Đã ghi lại cấu hình checksum/WAL vào inventory/runbook.

### 24.2. Khi vận hành thường ngày

- [ ] Theo dõi checksum failures và last failure time.
- [ ] Theo dõi WAL bytes, FPI count và checkpoint frequency.
- [ ] Theo dõi WAL archive failures và replication lag.
- [ ] Theo dõi disk capacity, I/O latency và controller/device alerts.
- [ ] Theo dõi logs cho checksum mismatch, WAL CRC và OS I/O errors.
- [ ] Duy trì backup tách biệt khỏi primary failure domain.
- [ ] Không xóa WAL files thủ công.
- [ ] Không tắt autovacuum/fsync/full_page_writes để che triệu chứng.

### 24.3. Khi bật/tắt checksums

- [ ] Dùng `pg_checksums` đúng major version.
- [ ] Cluster đã shutdown sạch.
- [ ] Không có process khác ghi vào data directory/tablespaces/WAL directory.
- [ ] Có backup và kế hoạch restore.
- [ ] Đã tính thời gian scan/rewrite và I/O.
- [ ] Không dùng `--no-sync` trong production.
- [ ] Đã có kế hoạch nhất quán cho primary/standbys/pg_rewind.
- [ ] Sau thao tác đã start và kiểm tra `SHOW data_checksums`.
- [ ] Đã chạy checksum verification phù hợp.

### 24.4. Khi tune checkpoint/FPI

- [ ] Có baseline `wal_fpi`, `wal_bytes` và checkpoint counts.
- [ ] Hiểu checkpoint interval ảnh hưởng FPI frequency.
- [ ] Hiểu checkpoint thưa hơn có thể tăng recovery time.
- [ ] Đã đo `wal_compression` theo CPU/WAL/archive throughput.
- [ ] Không tắt `full_page_writes` chỉ để giảm WAL.
- [ ] Đã test crash recovery trong môi trường phù hợp.
- [ ] Đã theo dõi replication/archive lag sau thay đổi.

### 24.5. Khi phát hiện corruption

- [ ] Bảo vệ logs, WAL, backup và bản sao liên quan.
- [ ] Ghi lại relation/block/node/time/error message.
- [ ] Phân biệt data checksum, WAL CRC và OS I/O errors.
- [ ] Kiểm tra hardware, firmware, filesystem, kernel và storage path.
- [ ] Không tự ghi/sửa bytes relation file.
- [ ] Không bật `ignore_checksum_failure` thường trực.
- [ ] Có phương án restore/PITR và xác minh sau phục hồi.
- [ ] Có incident report và theo dõi nguyên nhân gốc.

## 25. Câu hỏi thường gặp

### 25.1. Full-page writes có bật mặc định không?

Có. PostgreSQL mặc định bật `full_page_writes`. Cơ chế này ghi full-page image cho lần sửa đầu tiên của mỗi page sau checkpoint để hỗ trợ phục hồi torn page.

### 25.2. Vì sao FPI chỉ ghi một lần sau checkpoint?

Vì crash recovery bắt đầu từ checkpoint. FPI đầu tiên có thể phục hồi page nguyên vẹn; các WAL changes tiếp theo được replay theo thứ tự. Sau checkpoint mới, page có thể cần FPI mới ở lần sửa đầu tiên.

### 25.3. FPI có thay thế backup không?

Không. FPI chỉ là một phần WAL phục vụ crash recovery. Backup/PITR cần base backup và WAL chain hợp lệ.

### 25.4. Data checksum có sửa page hỏng không?

Không. Nó phát hiện page không khớp checksum và thường báo lỗi. Phục hồi cần WAL/FPI phù hợp, backup/PITR hoặc quy trình salvage.

### 25.5. Checksum và WAL CRC khác nhau thế nào?

Data page checksum kiểm tra page contents. WAL CRC-32C kiểm tra từng WAL record. Hai cơ chế bảo vệ hai loại dữ liệu khác nhau.

### 25.6. Checksums có bật mặc định không?

PostgreSQL 18 trở lên bật mặc định khi initdb. PostgreSQL 17 và các major trước đó tắt theo mặc định. Cluster hiện hữu có thể có trạng thái khác; kiểm tra `SHOW data_checksums`.

### 25.7. Có thể bật checksums mà không downtime không?

`pg_checksums` yêu cầu server shutdown sạch và thao tác offline trên toàn cluster. Lập maintenance window hoặc dùng quy trình chuyển đổi phù hợp nền tảng.

### 25.8. pg_checksums --check có chạy khi server đang hoạt động không?

Không. Server phải shutdown sạch trước khi chạy công cụ.

### 25.9. pg_checksums có kiểm tra WAL CRC không?

Không. Nó kiểm tra data page checksums. WAL record CRC được kiểm tra trong quá trình đọc/replay WAL và các công cụ liên quan.

### 25.10. pg_checksums có scan toàn cluster không?

Chế độ check scan các files trong cluster để xác minh checksums theo định dạng hỗ trợ. Đây là công việc I/O lớn; lập kế hoạch cho cluster dung lượng lớn.

### 25.11. Data checksums có bảo vệ temporary files không?

Không. Temporary files dùng cho query execution không được data page checksums bảo vệ theo cơ chế này.

### 25.12. WAL compression có nén tất cả WAL không?

Không. Nó nén full-page images được ghi vào WAL, không phải compression chung cho mọi WAL records.

### 25.13. Tăng checkpoint_timeout có luôn tốt?

Không. Có thể giảm số FPI/checkpoint và write bursts, nhưng crash recovery có thể cần replay nhiều WAL hơn. Phải cân bằng WAL, I/O và RTO.

### 25.14. Có nên tắt full_page_writes trên ZFS?

Một số filesystem có cơ chế ngăn partial page writes, nhưng quyết định phụ thuộc filesystem, storage stack, phiên bản và đảm bảo thực tế. PostgreSQL mặc định bật FPW; chỉ tắt sau khi xác minh atomic-write guarantee end-to-end và chấp nhận rủi ro.

### 25.15. Battery-backed controller có làm FPW không cần thiết?

Không tự động. Controller phải bảo đảm toàn bộ page write nguyên tử hoặc cung cấp bảo vệ tương đương. BBU chỉ giữ cache qua mất điện không đồng nghĩa page 8 KB luôn được ghi atomic.

### 25.16. Nếu checksum failure xuất hiện một lần rồi biến mất?

Vẫn là incident cần điều tra. Page có thể đã được rewrite/restore hoặc lỗi không còn tái hiện. Giữ logs và kiểm tra storage/hardware/backup trước khi kết luận lỗi đã hết.

### 25.17. Có thể dùng ignore_checksum_failure để query chạy tiếp?

Có thể trong một số tình huống salvage khẩn cấp, nhưng rất rủi ro: dữ liệu sai có thể lan truyền, backend có thể crash hoặc corruption bị che. Không dùng thường trực và không xem dữ liệu lấy được là đáng tin cậy.

### 25.18. synchronous_commit=off có làm page bị torn không?

Nó chủ yếu thay đổi thời điểm commit được xác nhận so với WAL flush, nên có thể mất các transaction vừa được báo commit khi crash. Nó không giống full_page_writes=off, vốn làm giảm bảo vệ torn page.

### 25.19. pg_verifybackup thay pg_checksums được không?

Không. `pg_verifybackup` kiểm tra backup artifact/manifest theo khả năng của nó; `pg_checksums` kiểm tra data page checksums trên cluster offline. Restore test vẫn cần thiết.

### 25.20. Checksum có chống attacker sửa dữ liệu không?

Không. Page checksum là cơ chế phát hiện lỗi ngẫu nhiên, không phải cryptographic authentication. Cần kiểm soát truy cập, audit, backup bảo vệ và security controls khác.

## 26. Tài liệu PostgreSQL chính thức

Các liên kết sau trỏ tới tài liệu PostgreSQL hiện hành. Một số defaults thay đổi giữa major versions, đặc biệt default data checksums ở PostgreSQL 18; hãy chọn tài liệu đúng version server:

- [Write Ahead Log (WAL)](https://www.postgresql.org/docs/current/wal-intro.html): tổng quan WAL, crash recovery và write-ahead principle.
- [Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): storage caches, partial page writes, full-page images, WAL CRC và data checksums.
- [Write Ahead Log Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): `full_page_writes`, `wal_log_hints`, `wal_compression`, `fsync`, `wal_sync_method` và checkpoint-related parameters.
- [WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint frequency, `checkpoint_timeout`, `max_wal_size`, checkpoint completion và FPI trade-offs.
- [Data Checksums](https://www.postgresql.org/docs/current/checksums.html): phạm vi bảo vệ, trạng thái checksum và enable/disable offline.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): kiểm tra, bật/tắt checksums, options và yêu cầu shutdown sạch.
- [initdb](https://www.postgresql.org/docs/current/app-initdb.html): `--data-checksums` và `--no-data-checksums`, defaults theo version.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_wal`, `pg_stat_database`, `pg_stat_checkpointer` và checksum failure counters.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): prerequisites và vai trò của data checksums/`wal_log_hints`.
- [Backup Manifest](https://www.postgresql.org/docs/current/backup-manifest-format.html): checksum và metadata của backup manifest.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): kiểm tra backup directory theo manifest.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và PITR.
- [Reliability and the Write-Ahead Log](https://www.postgresql.org/docs/current/wal.html): chương tổng hợp về độ tin cậy và WAL.

## 27. Tổng kết

**Full-page writes, data checksums và WAL CRC bảo vệ các lớp khác nhau của PostgreSQL.**

| Cơ chế | Bảo vệ | Hành vi chính |
| --- | --- | --- |
| `full_page_writes` | Torn data page khi crash | Ghi FPI trong WAL ở lần sửa đầu tiên của page sau checkpoint |
| `data_checksums` | Data page corruption | Kiểm tra checksum khi page được đọc/verify |
| WAL CRC-32C | WAL record corruption | Kiểm tra CRC của từng WAL record |
| `fsync` và storage flush | Durability của writes | Yêu cầu dữ liệu/WAL được đồng bộ xuống nonvolatile storage |
| Base backup + WAL archive | Phục hồi database/PITR | Tạo điểm khởi đầu và chuỗi replay tới thời điểm mục tiêu |

Để bảo vệ tính toàn vẹn:

1. Giữ `full_page_writes` và `fsync` bật theo policy durability.
2. Bật data checksums cho cluster; lưu ý PG18 đã đổi default sang bật.
3. Hiểu `wal_log_hints` và `wal_compression` trước khi điều chỉnh.
4. Theo dõi FPI, WAL bytes, checkpoint và checksum failures.
5. Dùng `pg_checksums` đúng version, khi cluster shutdown sạch.
6. Bảo vệ WAL archive, backup và replication topology.
7. Kiểm thử hardware/storage flush behavior.
8. Có restore/PITR drills và incident runbook.

Không một tham số nào có thể thay thế toàn bộ hệ thống durability. **FPI giúp recovery sau torn writes; checksums phát hiện page corruption; WAL CRC phát hiện record corruption; backup và WAL archive giúp khôi phục khi dữ liệu không còn sử dụng được.** Kết hợp đúng các lớp này và kiểm thử phục hồi định kỳ mới tạo được nền tảng bảo vệ dữ liệu đáng tin cậy.

