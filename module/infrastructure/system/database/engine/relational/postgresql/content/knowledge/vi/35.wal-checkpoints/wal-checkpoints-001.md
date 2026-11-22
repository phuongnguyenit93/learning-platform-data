# Nguyên lý ghi log trước dữ liệu và bảo đảm khôi phục trong PostgreSQL

PostgreSQL có thể xác nhận một transaction đã COMMIT trong khi các data pages chứa thay đổi của transaction đó vẫn chưa được ghi xuống file bảng. Điều này không làm mất tính bền vững của transaction: trước khi xác nhận commit theo chế độ đồng bộ, PostgreSQL phải bảo đảm các WAL records cần thiết đã được flush theo durability policy.

Đây là nguyên tắc **Write-Ahead Logging (WAL)**: ghi log mô tả thay đổi trước khi ghi các data pages tương ứng. WAL cho phép PostgreSQL phục hồi database sau crash, hỗ trợ physical replication, lưu trữ log để khôi phục về một thời điểm và giảm lượng data pages phải đồng bộ ở mỗi lần COMMIT.

**Checkpoint** điều phối việc ghi các dirty pages từ shared buffers xuống data files và thiết lập vị trí mà crash recovery có thể bắt đầu redo. Checkpoint không thay thế WAL và cũng không phải backup.

```text
Client gửi COMMIT
       |
       v
Transaction tạo WAL records
       |
       v
WAL buffers -> WAL files -> flush bền vững
       |
       v
PostgreSQL xác nhận COMMIT
       |
       | Data pages có thể vẫn dirty trong shared buffers
       v
Checkpoint ghi dirty pages xuống data files
       |
       v
Sau crash: đọc checkpoint gần nhất + phát lại WAL cần thiết
```

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **WAL và checkpoint**, với đề tài **“Nguyên lý ghi log trước dữ liệu và bảo đảm khôi phục”**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Write-Ahead Logging và lý do PostgreSQL ghi WAL trước khi ghi data pages.
2. Phân biệt WAL records, WAL buffers, WAL files/segments và data files.
3. Giải thích LSN và vai trò của page LSN trong recovery.
4. Mô tả đường đi của một transaction từ UPDATE tới COMMIT.
5. Phân biệt ghi WAL với flush WAL và fsync.
6. Giải thích vì sao PostgreSQL có thể xác nhận COMMIT trước khi data pages được ghi xuống data files.
7. Hiểu tác động của synchronous_commit, fsync, full_page_writes và wal_sync_method.
8. Phân biệt transaction durability trên primary với synchronous replication trên standby.
9. Giải thích shared buffers, dirty pages, background writer và checkpointer.
10. Mô tả checkpoint, redo point và phạm vi WAL cần replay.
11. Phân biệt checkpoint theo thời gian với checkpoint do WAL pressure.
12. Hiểu tác động của checkpoint_timeout, max_wal_size, min_wal_size và checkpoint_completion_target.
13. Giải thích full-page images và nguy cơ torn page.
14. Mô tả crash recovery, redo và cách MVCC xử lý transaction chưa commit.
15. Phân biệt WAL recovery với backup/restore và Point-in-Time Recovery (PITR).
16. Thiết kế WAL archiving và hiểu yêu cầu về base backup.
17. Hiểu timeline và cách PostgreSQL tiếp tục WAL sau khi recovery tạo một nhánh mới.
18. Phân biệt physical streaming replication, synchronous replication và logical replication.
19. Hiểu replication slots, WAL retention và nguy cơ đầy ổ đĩa.
20. Theo dõi WAL, checkpoint, archiver và replication bằng các system views.
21. Dùng pg_waldump, pg_walinspect và pg_controldata trong chẩn đoán phù hợp.
22. Thiết kế lab kiểm tra LSN, checkpoint, WAL generation và archive.
23. Lập kế hoạch backup/restore/PITR có kiểm chứng, bao gồm RPO/RTO.
24. Nhận biết cấu hình làm suy giảm durability và giới hạn của phần cứng lưu trữ.

**Phạm vi:** PostgreSQL hiện đại. Tên cột và cấu trúc một số statistics views thay đổi theo major version. Một số ví dụ monitoring cần điều chỉnh theo phiên bản đang chạy. Không tắt các thiết lập bảo vệ dữ liệu chỉ để tăng throughput nếu chưa đánh giá khả năng mất dữ liệu và phục hồi.

---

## 2. Vì sao cần WAL?

Database phải duy trì các tính chất quan trọng khi nhiều transaction cùng ghi và khi máy chủ có thể dừng đột ngột:

- Transaction đã được xác nhận commit phải tồn tại sau sự cố theo durability policy.
- Database không được để data pages ở trạng thái không nhất quán sau khi khởi động lại.
- Các thay đổi đã ghi nhưng chưa commit không được trở thành dữ liệu hợp lệ chỉ vì server crash.
- Recovery phải có cách xác định những thay đổi cần phát lại.

Nếu PostgreSQL phải ghi mọi data page xuống storage ngay tại mỗi câu UPDATE, một transaction sửa nhiều rows trên nhiều pages sẽ gây nhiều I/O ngẫu nhiên và latency.

WAL giải quyết vấn đề bằng cách ghi một luồng log tuần tự mô tả các thay đổi cần thiết để khôi phục page state. Các data pages có thể được ghi xuống sau đó.

### 2.1. Write-ahead rule

**WAL record mô tả một thay đổi phải được flush tới storage bền vững trước khi data page chứa thay đổi tương ứng được phép ghi xuống storage.**

Nếu mất điện giữa quá trình ghi data page, PostgreSQL có thể dùng WAL để redo các thay đổi cần thiết.

### 2.2. Ghi tuần tự và ghi ngẫu nhiên

WAL được ghi theo thứ tự log, thường theo các WAL segments. Data pages có thể nằm rải rác trong nhiều relation files. Ghi log tuần tự giúp giảm chi phí đồng bộ dữ liệu ở đường commit.

### 2.3. Commit không bắt buộc flush mọi data pages

Khi transaction COMMIT, PostgreSQL cần bảo đảm commit record và WAL records cần thiết được flush theo cấu hình. Heap/index pages có thể vẫn nằm trong shared buffers và được ghi xuống sau.

### 2.4. WAL hỗ trợ những tính năng nào?

- Crash recovery.
- Physical streaming replication.
- WAL archiving.
- Point-in-Time Recovery.
- Một số hình thức backup online.
- Logical decoding và logical replication khi wal_level phù hợp.

### 2.5. WAL không phải SQL audit log

WAL là log phục vụ recovery và replication ở mức nội bộ. Nó không phải nhật ký câu lệnh SQL dễ đọc để kiểm toán người dùng. Muốn audit SQL statements, cần logging/auditing phù hợp; không suy diễn WAL thành lịch sử đầy đủ của mọi hành động nghiệp vụ.

---

## 3. WAL record, LSN và WAL segment

### 3.1. WAL record

Một WAL record mô tả thông tin cần thiết cho recovery hoặc các consumer WAL. Nội dung phụ thuộc loại thao tác: thay đổi heap page, index page, transaction commit, checkpoint, relation metadata và nhiều loại record khác.

Không phải mọi WAL record đều là một câu SQL. WAL thường không lưu câu UPDATE dưới dạng văn bản để chạy lại như SQL script.

### 3.2. Log Sequence Number (LSN)

**LSN** là vị trí logic trong luồng WAL, thường được biểu diễn dạng hexadecimal:

```sql
SELECT pg_current_wal_lsn();
```

LSN tăng theo thứ tự WAL được tạo. Nó là vị trí trong WAL stream, không phải timestamp và cũng không phải số transaction.

### 3.3. LSN của page

Data page có trường LSN trong page header để biểu diễn vị trí WAL liên quan tới trạng thái page. Trong recovery, PostgreSQL dùng thông tin này để quyết định có cần áp dụng một WAL record lên page hay page đã phản ánh thay đổi đó.

### 3.4. WAL segment

WAL được lưu trong các segment files bên trong thư mục pg_wal. Kích thước segment mặc định phổ biến là 16 MB, nhưng kích thước có thể được xác định khi build PostgreSQL và không nên giả định giống nhau ở mọi cluster.

Tên file WAL mã hóa thông tin timeline, log và segment number. Một WAL stream có thể trải qua nhiều segment liên tiếp.

### 3.5. WAL buffers

PostgreSQL có vùng bộ nhớ shared WAL buffers để giữ các WAL records trước khi ghi chúng ra file WAL. Tham số wal_buffers điều khiển kích thước vùng này, với giá trị mặc định thường được PostgreSQL tự chọn theo cấu hình.

### 3.6. WAL buffers không phải shared buffers

| Thành phần | Chứa gì? | Mục đích |
| --- | --- | --- |
| Shared buffers | Data pages của tables/indexes | Cache page và ghi dirty pages |
| WAL buffers | WAL records mới | Gom log trước khi ghi WAL files |
| OS page cache | File blocks do hệ điều hành cache | Hỗ trợ I/O file |
| WAL files | WAL stream trên storage | Recovery/replication/archive |
| Relation files | Heap/index data pages | Lưu trạng thái database lâu dài |

### 3.7. Xem WAL LSN

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

Hai giá trị có thể khác nhau vì WAL mới được tạo nhưng chưa flush xong. Các hàm LSN có thể khác ở phiên bản PostgreSQL cũ; kiểm tra tài liệu đúng major version.

---

## 4. Write-Ahead Rule và data pages

Giả sử transaction cập nhật một row trên heap page số 120:

```text
Shared buffers:
  Heap page 120: giá trị mới, trạng thái DIRTY

WAL buffers:
  WAL record mô tả thay đổi trên page 120

Thứ tự bền vững:
  1. WAL record được flush
  2. Data page 120 mới được phép ghi xuống storage
```

### 4.1. Nếu data page ghi trước WAL?

Nếu page mới đã được ghi xuống nhưng WAL mô tả thay đổi chưa bền vững, crash có thể khiến database không có log cần thiết để khôi phục hoặc xác minh trạng thái page. Điều này vi phạm write-ahead rule.

### 4.2. Nếu WAL ghi trước data page?

Nếu WAL đã bền vững nhưng data page chưa được ghi, crash recovery có thể đọc WAL và redo thay đổi để đưa page tới trạng thái đúng.

### 4.3. Vì sao PostgreSQL không cần ghi page ngay khi UPDATE?

WAL cho phép trì hoãn data page writes và gom nhiều thay đổi trên cùng page trước khi ghi. Điều này giúp transaction commit không phải đợi toàn bộ data files được cập nhật.

### 4.4. Checkpointer tuân thủ write-ahead rule

Trước khi ghi dirty data page, PostgreSQL bảo đảm WAL tới page LSN tương ứng đã được flush. Đây là điều kiện bắt buộc trong cơ chế storage.

### 4.5. Durability phụ thuộc storage thực tế

PostgreSQL có thể yêu cầu flush, nhưng thiết bị lưu trữ hoặc controller phải thực hiện đúng semantics mà hệ điều hành báo cáo. Nếu hardware/virtualization layer nói đã flush nhưng dữ liệu vẫn chỉ nằm trong cache volatile, durability có thể bị suy giảm.

---

## 5. Đường đi của một transaction tới COMMIT

Xét ví dụ:

```sql
BEGIN;

UPDATE banking.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE banking.accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Luồng khái niệm:

```text
Client
  |
  | UPDATE
  v
Executor / heap & index operations
  |
  +--> Shared buffers: dirty heap/index pages
  |
  +--> WAL buffers: WAL records
              |
              v
         WAL writer / backend
              |
              v
         Write WAL to OS
              |
              v
         Flush WAL (fsync-equivalent)
              |
              v
         COMMIT record durable
              |
              v
         COMMIT response to client
```

### 5.1. Dirty pages

Executor sửa các data pages trong shared buffers. Những pages này được đánh dấu dirty.

### 5.2. WAL records

Các thao tác ghi sinh WAL records. WAL records có thể mô tả heap/index changes và transaction state.

### 5.3. Commit record

Khi transaction commit, PostgreSQL tạo commit record trong WAL. Với durability mode đồng bộ mặc định, server phải đợi WAL cần thiết được flush trước khi trả lời COMMIT thành công.

### 5.4. Data pages có thể chưa được ghi

Sau khi COMMIT được xác nhận, dirty pages có thể vẫn nằm trong shared buffers. Đây là hành vi bình thường, không phải transaction “chưa lưu”.

### 5.5. Group commit

Nhiều transaction có thể cùng chờ một lần WAL flush. PostgreSQL có thể gom nhiều commit records vào một lần flush, giảm số lần đồng bộ storage cho mỗi transaction.

### 5.6. COMMIT response không có nghĩa checkpoint vừa chạy

COMMIT response xác nhận transaction commit theo durability settings. Nó không có nghĩa mọi heap/index pages đã được ghi xuống data files.

---

## 6. Write, flush và fsync

Ba khái niệm này rất quan trọng:

- **Write**: chuyển bytes từ PostgreSQL buffers sang kernel/file-system layer hoặc đường ghi được cấu hình.
- **Flush**: yêu cầu các bytes WAL tới một LSN được đẩy qua ranh giới durability cần thiết.
- **fsync** (hoặc phương thức tương đương): yêu cầu hệ điều hành/storage đồng bộ dữ liệu tới thiết bị lưu trữ theo contract của hệ thống.

### 6.1. OS page cache

Một lệnh write thành công có thể chỉ có nghĩa bytes đã được kernel nhận vào page cache. Điều đó chưa luôn đồng nghĩa dữ liệu đã bền vững qua mất điện.

### 6.2. WAL flush

PostgreSQL phải flush WAL trước khi cho phép data page tương ứng được ghi xuống theo write-ahead rule và trước khi xác nhận commit đồng bộ.

### 6.3. Data page flush

Data pages được checkpointer/background writer ghi xuống. WAL liên quan phải được flush trước.

### 6.4. Vì sao commit có thể nhanh?

Commit đồng bộ chủ yếu đợi WAL flush tới commit record, thay vì buộc ghi toàn bộ các heap/index pages đã sửa. WAL là luồng tuần tự nên thường dễ đồng bộ hơn nhiều data pages rải rác.

### 6.5. Thiết bị storage phải trung thực

Đảm bảo durability cần phối hợp PostgreSQL, operating system, filesystem, storage driver/controller, virtualization/cloud volume và thiết bị vật lý có power-loss protection. Một cấu hình PostgreSQL đúng không thể bù cho storage layer báo flush thành công sai thực tế.

---

## 7. synchronous_commit: transaction chờ tới đâu?

Tham số synchronous_commit điều khiển mức độ đợi WAL khi commit.

```sql
SHOW synchronous_commit;
```

### 7.1. Giá trị on

Với primary không cấu hình synchronous standby, PostgreSQL đợi local WAL flush tới mức cần thiết trước khi xác nhận commit.

Nếu synchronous replication được cấu hình, on còn đợi xác nhận remote flush theo cơ chế synchronous replication.

### 7.2. Giá trị off

PostgreSQL có thể trả COMMIT success trước khi WAL của transaction được flush local. Nếu server crash, các transaction mới được xác nhận gần đây có thể bị mất.

Điều này không đồng nghĩa database sẽ tự động bị corrupt: PostgreSQL vẫn duy trì recovery consistency theo WAL còn bền vững. Nhưng durability guarantee đối với các commit gần nhất đã yếu đi.

### 7.3. Giá trị local

Trong cấu hình synchronous replication, local đợi local WAL flush nhưng không đợi remote standby acknowledgement.

### 7.4. Giá trị remote_write

Đợi standby báo đã ghi WAL tới hệ điều hành của standby theo semantics tương ứng, nhưng chưa nhất thiết flush tới storage bền vững như remote_flush.

### 7.5. Giá trị remote_flush

Đợi synchronous standby flush WAL tới storage trước khi primary xác nhận commit.

### 7.6. Giá trị remote_apply

Đợi synchronous standby replay WAL tới transaction để thay đổi có thể nhìn thấy trên standby theo cơ chế apply. Mức này thường tăng latency hơn vì standby cần replay.

### 7.7. Bảng so sánh

| Giá trị | Local primary flush | Remote standby write | Remote standby flush | Remote apply |
| --- | --- | --- | --- | --- |
| off | Không đợi flush cho từng commit | Không | Không | Không |
| local | Có | Không | Không | Không |
| on khi không có synchronous standby | Có | Không | Không | Không |
| on khi có synchronous standby | Có | Có acknowledgement theo sync mode | Thông thường đợi remote flush | Không nhất thiết apply |
| remote_write | Có | Có | Không nhất thiết | Không |
| remote_flush | Có | Có | Có | Không |
| remote_apply | Có | Có | Có | Có |

Chi tiết tương tác giữa synchronous_commit và synchronous_standby_names cần được đối chiếu tài liệu của phiên bản và cấu hình cụ thể.

### 7.8. Lựa chọn theo yêu cầu dữ liệu

- Giao dịch tài chính, đơn hàng, ledger: thường ưu tiên durability mạnh.
- Dữ liệu telemetry có thể tái tạo: có thể cân nhắc off trong phạm vi hẹp nếu chấp nhận mất một lượng commit gần nhất khi crash.
- Không đặt global off chỉ để tăng benchmark.
- Có thể SET LOCAL cho một transaction không quan trọng nếu ứng dụng đã chấp nhận semantics.

Ví dụ trong transaction có phạm vi kiểm soát:

```sql
BEGIN;
SET LOCAL synchronous_commit = off;

INSERT INTO telemetry.events(event_type, recorded_at)
VALUES ('heartbeat', clock_timestamp());

COMMIT;
```

Không áp dụng mẫu này cho dữ liệu không thể tái tạo hoặc cần bảo đảm commit ngay lập tức.

---

## 8. fsync, full_page_writes và các thiết lập durability

### 8.1. fsync

fsync bật yêu cầu đồng bộ dữ liệu quan trọng tới storage. PostgreSQL khuyến nghị giữ bật trong hệ thống cần độ bền vững.

Tắt fsync có thể dẫn tới database corruption không thể phục hồi sau crash hệ điều hành hoặc mất điện. Không xem đây là tuning thông thường.

### 8.2. full_page_writes

Sau checkpoint, lần đầu một page được sửa có thể ghi một **full-page image (FPI)** vào WAL, tùy full_page_writes và các điều kiện liên quan.

```sql
SHOW full_page_writes;
```

### 8.3. Torn page

Một data page có thể lớn hơn đơn vị ghi nguyên tử của storage. Nếu mất điện giữa lúc ghi page, file có thể chứa một phần bytes mới và một phần bytes cũ.

FPI cho phép recovery thay thế page bị torn bằng image đầy đủ rồi tiếp tục redo các WAL records sau đó.

### 8.4. Không tắt full_page_writes tùy tiện

Tắt full_page_writes khi storage không bảo đảm atomic page writes có thể làm tăng nguy cơ hỏng page sau crash. Chỉ cân nhắc trong môi trường có guarantee phần cứng rõ ràng và quy trình được chuyên gia đánh giá.

### 8.5. wal_sync_method

Tham số này chọn phương thức đồng bộ WAL trên nền tảng tương ứng, ví dụ phương thức sử dụng fdatasync, fsync hoặc cơ chế khác tùy OS. PostgreSQL có thể chọn default phù hợp.

Không đổi chỉ vì thấy một phương thức có tên nhanh hơn; benchmark phải đo trên storage thật và vẫn bảo đảm semantics.

### 8.6. wal_compression

Có thể nén full-page images để giảm WAL volume trong những workload phù hợp. Đổi lại có CPU cost. Các phương pháp nén được hỗ trợ phụ thuộc build/phiên bản.

### 8.7. wal_log_hints

Tham số này liên quan việc ghi WAL cho hint-bit changes trong những trường hợp cần thiết và có thể là điều kiện cho một số chế độ checksums/replication tooling. Kiểm tra tài liệu phiên bản trước khi bật/tắt.

### 8.8. Bộ thiết lập durability

Một bộ thiết lập durability thường cần xem xét cùng nhau:

- fsync = on.
- full_page_writes = on.
- synchronous_commit theo yêu cầu.
- Backup và WAL archive được kiểm chứng.
- Storage có flush semantics đáng tin.
- Monitoring WAL disk và archive backlog.

---

## 9. Shared buffers, dirty pages và background writer

### 9.1. Shared buffers

PostgreSQL giữ cache các table/index pages trong shared buffers. Khi UPDATE, pages liên quan có thể được sửa trong bộ nhớ.

### 9.2. Dirty page

Một page đã bị sửa nhưng chưa ghi về data file được gọi là dirty page.

### 9.3. Background writer

Background writer có thể ghi một số dirty buffers để giúp backend không phải tự xử lý toàn bộ việc ghi page khi cần buffer trống. Mục tiêu của nó liên quan tới buffer availability và I/O smoothing.

### 9.4. Checkpointer

Checkpointer điều phối checkpoint và ghi các dirty buffers cần thiết cho checkpoint xuống storage, đồng thời đảm bảo WAL đã được flush trước data pages.

### 9.5. Backend cũng có thể ghi dirty buffers

Không phải chỉ có checkpointer mới ghi data pages. Backend có thể tham gia ghi buffers trong một số tình huống. Background writer, checkpointer và backend có vai trò khác nhau.

### 9.6. WAL writer

WAL writer hỗ trợ ghi WAL buffers ra file WAL theo chu kỳ/điều kiện. Backend cũng có thể thực hiện WAL writes/flush khi cần, đặc biệt trên đường commit.

### 9.7. Không nhầm background writer với checkpointer

Background writer giúp duy trì buffer availability; checkpointer thực hiện checkpoint và đảm bảo các pages cần thiết được ghi để recovery có thể bắt đầu từ redo point phù hợp.

---

## 10. Checkpoint là gì?

**Checkpoint** là một điểm đồng bộ trong WAL/data-page lifecycle. PostgreSQL ghi checkpoint record vào WAL và bảo đảm các dirty buffers thuộc phạm vi checkpoint được ghi xuống data files theo quy tắc cần thiết.

Checkpoint giúp xác định vị trí bắt đầu redo trong crash recovery và cho phép WAL cũ hơn được xử lý theo các điều kiện archive/replication/recovery khác.

### 10.1. Checkpoint không phải COMMIT

COMMIT xác nhận một transaction hoàn tất theo durability policy. Checkpoint là hoạt động ở cấp cluster nhằm đồng bộ data pages và cập nhật checkpoint state.

### 10.2. Checkpoint không phải backup

Checkpoint không tạo một bản sao database có thể restore độc lập. Muốn backup/restore cần base backup hoặc logical dump cùng quy trình WAL phù hợp.

### 10.3. Checkpoint không buộc client chờ mọi transaction

Checkpoint chạy nền theo lịch và WAL pressure. Một transaction bình thường không cần tự chạy CHECKPOINT sau mỗi COMMIT.

### 10.4. Checkpoint có redo point

Checkpoint ghi thông tin về vị trí WAL mà recovery có thể cần bắt đầu redo. WAL sau redo point có thể chứa thay đổi cần phát lại để đưa data pages về trạng thái nhất quán.

### 10.5. Checkpoint record và hoàn tất checkpoint

Ở mức khái niệm, PostgreSQL ghi checkpoint record vào WAL, flush các dirty pages theo write-ahead rule, rồi cập nhật control information khi checkpoint hoàn tất. Nếu crash giữa checkpoint, recovery dùng checkpoint hoàn tất gần nhất được control file ghi nhận.

### 10.6. Checkpoint không chỉ là một record

Checkpointer cần thực hiện công việc ghi dirty buffers theo quy tắc, cập nhật trạng thái bền vững và quản lý WAL/checkpoint lifecycle. Chỉ nhìn thấy checkpoint record không có nghĩa mọi bước checkpoint đã hoàn tất.

---

## 11. Checkpoint hoạt động như thế nào?

```text
Checkpoint được kích hoạt
       |
       v
Xác định checkpoint state / redo point
       |
       v
Ghi checkpoint record vào WAL
       |
       v
Flush dirty buffers theo write-ahead rule
       |
       v
Ghi data pages xuống data files
       |
       v
Cập nhật control information khi hoàn tất
```

Chi tiết nội bộ có thể khác theo phiên bản và loại checkpoint, nhưng nguyên tắc WAL-before-data vẫn phải được giữ.

### 11.1. Dirty buffers có thể được ghi dần

Checkpoint không nhất thiết ghi tất cả pages trong một burst duy nhất. PostgreSQL có thể phân bổ công việc theo khoảng thời gian mục tiêu.

### 11.2. WAL không cần chờ checkpoint mới được ghi

WAL được ghi liên tục khi transaction tạo records. Checkpoint không phải thời điểm duy nhất WAL được flush.

### 11.3. Checkpoint theo timeout

checkpoint_timeout xác định khoảng thời gian tối đa giữa các checkpoint theo lịch thời gian, trong giới hạn và hành vi phiên bản.

### 11.4. Checkpoint do WAL volume

Nếu WAL được tạo nhanh và vượt mức được phép theo cấu hình, PostgreSQL có thể yêu cầu checkpoint sớm hơn để tái sử dụng WAL segments.

### 11.5. Manual CHECKPOINT

Lệnh:

```sql
CHECKPOINT;
```

yêu cầu checkpoint ngay. Đây là lệnh quản trị, cần quyền thích hợp (superuser hoặc role có quyền pg_checkpoint theo phiên bản). Không chạy định kỳ từ ứng dụng sau mỗi batch.

---

## 12. Redo point và phạm vi recovery

Giả sử checkpoint hoàn tất ở LSN C. Sau đó transaction tiếp tục tạo WAL:

```text
WAL timeline
------------------------------------------------------------>
       C                LSN D                 LSN E
       |                  |                     |
  Checkpoint         UPDATE page A         COMMIT transaction
  redo point         UPDATE page B
```

Nếu crash sau LSN E nhưng data pages A/B chưa được ghi hết xuống data files, recovery đọc WAL từ redo point phù hợp và phát lại những thay đổi cần thiết.

### 12.1. Không phải replay mọi WAL từ lúc tạo database

Checkpoint giới hạn phạm vi redo cần thiết cho crash recovery trên cùng timeline/cluster.

### 12.2. Recovery có thể cần WAL sau checkpoint

Data pages có thể chưa chứa các thay đổi sau checkpoint. WAL cung cấp thông tin để phát lại.

### 12.3. Page LSN giúp tránh redo thừa

Nếu page đã có LSN đủ mới, recovery có thể nhận biết record đã được phản ánh trên page và tránh áp dụng lại theo cách không cần thiết.

### 12.4. Redo không phải chạy lại SQL

Recovery xử lý WAL records ở mức storage/internal operations, không chạy lại câu lệnh SQL gốc từ client.

### 12.5. Checkpoint mới không đồng nghĩa WAL cũ luôn xóa ngay

WAL còn có thể cần cho archiving, replication slots, standby, backup hoặc recovery. Chỉ khi không còn retention requirement và điều kiện nội bộ cho phép, segments mới có thể được recycle/remove.

---

## 13. Checkpoint theo thời gian và theo WAL pressure

### 13.1. Timed checkpoint

Checkpoint được kích hoạt khi tới khoảng thời gian checkpoint_timeout.

### 13.2. Requested checkpoint

Checkpoint có thể được yêu cầu sớm do WAL volume vượt mức mục tiêu, manual command hoặc một số sự kiện vận hành.

### 13.3. Checkpoint quá thường xuyên

Checkpoint quá thường xuyên có thể tăng I/O ghi data pages, tăng full-page images trong WAL sau checkpoint, gây write bursts nếu công việc không được làm mượt và làm tăng storage write amplification.

### 13.4. Checkpoint quá thưa

Checkpoint thưa hơn có thể giảm overhead checkpoint và FPI frequency trong một số workload, nhưng có thể làm phạm vi WAL cần redo sau crash lớn hơn, tăng lượng WAL đang giữ, kéo dài crash recovery và tăng áp lực disk nếu max_wal_size không được điều chỉnh hợp lý.

### 13.5. Không chọn checkpoint chỉ theo một metric

Cần cân bằng recovery time objective, WAL volume, storage throughput, workload spikes và archive/replication requirements.

---

## 14. Các tham số checkpoint quan trọng

### 14.1. checkpoint_timeout

Khoảng thời gian tối đa giữa các checkpoint theo lịch thời gian. Giá trị mặc định phổ biến là 5 phút, nhưng cần xác nhận trên cluster:

```sql
SHOW checkpoint_timeout;
```

### 14.2. max_wal_size

Mức WAL size mục tiêu để PostgreSQL cân nhắc checkpoint sớm hơn. Đây **không phải hard limit tuyệt đối** cho dung lượng pg_wal.

WAL có thể vượt mức này do archive backlog, replication slots, workload spikes hoặc các điều kiện retention khác.

### 14.3. min_wal_size

Mức WAL tối thiểu PostgreSQL cố gắng giữ/recycle để giảm việc liên tục tạo/xóa segment files.

### 14.4. checkpoint_completion_target

Mục tiêu phân bố thời gian ghi checkpoint trong khoảng giữa các checkpoint. Giá trị cao có thể làm việc ghi dàn đều hơn, giảm burst, nhưng không xóa nhu cầu có đủ I/O capacity.

### 14.5. Xem các setting

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_completion_target',
    'full_page_writes',
    'wal_compression',
    'wal_buffers',
    'synchronous_commit',
    'fsync'
)
ORDER BY name;
```

### 14.6. Một điểm khởi đầu không phải prescription

Một hệ thống có thể bắt đầu bằng default, đo checkpoint frequency/WAL volume và điều chỉnh từng bước. Không sao chép cấu hình của hệ thống khác khi storage, transaction size và recovery target khác nhau.

### 14.7. max_wal_size không phải disk quota

Cần giám sát dung lượng filesystem chứa pg_wal và archive. Một slot bị giữ lâu có thể khiến WAL tăng vượt xa max_wal_size.

---

## 15. Full-page images và checkpoint

### 15.1. Vì sao FPI cần thiết?

Khi PostgreSQL ghi page xuống storage, một sự cố có thể làm page chỉ được ghi một phần. Nếu chỉ có WAL records mô tả các thay đổi nhỏ, recovery có thể không đủ thông tin để sửa page bị torn.

### 15.2. Ghi full-page image

Khi full_page_writes bật, PostgreSQL có thể ghi image đầy đủ của page vào WAL ở lần sửa đầu tiên của page sau checkpoint, theo quy tắc và điều kiện tương ứng.

### 15.3. FPI làm WAL tăng

Sau checkpoint, nhiều pages được sửa lần đầu có thể sinh FPI. Checkpoint quá thường xuyên có thể làm FPI phát sinh thường xuyên hơn.

### 15.4. wal_compression

Nén FPI có thể giảm lượng WAL bytes nếu page image có khả năng nén tốt. Nó dùng CPU và hiệu quả phụ thuộc dữ liệu/page contents.

### 15.5. FPI không phải full database snapshot

FPI là hình ảnh page trong WAL để hỗ trợ recovery. Nó không phải backup độc lập của toàn bộ database.

### 15.6. Page checksums khác FPI

Checksums có thể giúp phát hiện page corruption khi đọc page. FPI hỗ trợ phục hồi một số trường hợp torn page qua WAL. Hai cơ chế có mục tiêu liên quan nhưng không thay thế nhau.

---

## 16. Crash recovery: PostgreSQL khởi động lại sau sự cố

Giả sử máy chủ tắt đột ngột:

- Một số transaction đã commit và WAL của chúng đã flush.
- Một số data pages chưa được ghi xuống data files.
- Một số transaction đang chạy chưa commit.
- Có thể một số page writes bị gián đoạn.

Khi khởi động lại, PostgreSQL thực hiện crash recovery.

### 16.1. Đọc control information

PostgreSQL xác định checkpoint gần nhất và trạng thái cần thiết từ control file và WAL.

### 16.2. Bắt đầu redo

PostgreSQL đọc WAL từ vị trí cần thiết và phát lại những thay đổi chưa được phản ánh đầy đủ vào data pages.

### 16.3. Page LSN

Recovery kiểm tra LSN của page để biết record nào cần áp dụng. Điều này hỗ trợ phát lại an toàn.

### 16.4. Transaction status và visibility

WAL chứa thông tin về transaction completion. Một transaction chưa có commit record hợp lệ không được coi là committed chỉ vì một phần tuple của nó đã được ghi xuống heap.

### 16.5. PostgreSQL không dùng undo log kiểu truyền thống cho mọi UPDATE

PostgreSQL dựa vào MVCC tuple versions và transaction visibility. Sau crash, các thay đổi chưa commit vẫn không visible; dead tuple cleanup được xử lý sau theo quy tắc vacuum. Không hiểu recovery như việc chạy một undo script SQL cho từng câu lệnh.

### 16.6. Server chỉ mở kết nối bình thường sau recovery phù hợp

Nếu WAL cần thiết bị thiếu hoặc corruption không thể sửa bằng cơ chế recovery hiện có, PostgreSQL có thể không khởi động thành công. Không bỏ qua lỗi chỉ để server lên trạng thái accepting connections.

---

## 17. Crash recovery và transaction durability

### 17.1. Transaction đã COMMIT với synchronous commit

Nếu WAL commit record đã flush bền vững, recovery có thể khôi phục thay đổi ngay cả khi data pages chưa được ghi trước crash.

### 17.2. Transaction chưa COMMIT

Các thay đổi của transaction không được coi là committed. Tuple versions có thể còn tồn tại vật lý nhưng không visible cho transaction mới theo MVCC status.

### 17.3. Transaction commit với synchronous_commit=off

Một commit response có thể đã được gửi trước local WAL flush. Nếu crash xảy ra đúng thời điểm, một số transaction gần đây có thể biến mất sau recovery. Ứng dụng phải chấp nhận khả năng này nếu bật chế độ đó.

### 17.4. fsync=off

Đây là rủi ro nghiêm trọng hơn: hệ thống có thể mất hoặc làm hỏng dữ liệu theo cách không thể phục hồi chỉ bằng WAL hiện có. Không dùng để tối ưu production.

### 17.5. Commit response mất trên network

Client có thể không biết transaction đã commit hay chưa nếu kết nối bị đứt ngay lúc server xử lý COMMIT. Đây là **ambiguous outcome** ở tầng ứng dụng. Thiết kế idempotency/business keys để retry an toàn; không giả định lỗi mạng đồng nghĩa transaction rollback.

### 17.6. Durability end-to-end

Đảm bảo transaction bền vững cần cả database config, storage flush correctness, backup/restore và quy trình vận hành. Một COMMIT thành công không thay thế backup.

---

## 18. WAL archiving

**WAL archiving** là việc sao chép các WAL segments đã hoàn tất sang một kho lưu trữ ngoài pg_wal.

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

### 18.1. Bật archive mode

archive_mode cần cấu hình phù hợp và thường cần restart để thay đổi. Archive command hoặc archive library được cấu hình để chuyển WAL segment đã hoàn tất sang nơi lưu trữ.

### 18.2. Archive command

Một ví dụ minh họa về ý tưởng:

```conf
archive_mode = on
archive_command = 'archive-helper %p %f'
```

Trong đó %p là path file WAL nguồn, %f là tên WAL file và archive-helper là script/tool do hệ thống triển khai cung cấp.

Đây là placeholder, không phải executable có sẵn. Production helper cần kiểm tra tính idempotent, quyền filesystem, lỗi copy, checksum, xử lý file đã tồn tại, atomic publish, alerting và khả năng lưu trữ bền vững. Không báo thành công trước khi archive đã được lưu an toàn theo contract.

### 18.3. Archive command trả thành công khi nào?

Archive command phải chỉ báo success sau khi segment đã được lưu an toàn. Nếu báo thành công quá sớm, PostgreSQL có thể cho phép recycle WAL segment trong khi bản archive chưa thực sự bền vững.

### 18.4. Archive backlog

Nếu archive command thất bại liên tục, các WAL segments có thể tích tụ trong pg_wal, làm đầy filesystem.

### 18.5. pg_stat_archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Các trường thường hữu ích gồm số lần archived, failed, thời điểm archive gần nhất và file gần nhất; kiểm tra schema view theo phiên bản.

### 18.6. archive_timeout

Có thể ép switch WAL segment theo khoảng thời gian để archive những thay đổi trong workload ít ghi. Điều này có thể tạo thêm segment/archive overhead. Không đặt quá thấp nếu không có nhu cầu rõ.

---

## 19. Base backup và Point-in-Time Recovery (PITR)

WAL archive một mình không đủ để khôi phục database từ lúc mất toàn bộ data directory. Cần một **base backup** phù hợp và chuỗi WAL liên tục từ thời điểm backup cần tới recovery target.

### 19.1. Base backup

Base backup là bản sao vật lý nhất quán của cluster tại một khoảng thời gian. Có thể tạo bằng pg_basebackup hoặc giải pháp backup tương thích PostgreSQL.

### 19.2. WAL trong quá trình backup

Backup online cần có WAL đủ để làm cho bản backup trở nên nhất quán. Công cụ backup phối hợp với PostgreSQL để lấy thông tin WAL cần thiết.

### 19.3. PITR

PITR cho phép khôi phục tới một thời điểm, transaction ID, restore point hoặc LSN mục tiêu phù hợp với khả năng phiên bản.

```text
Base backup tại thời điểm T0
       |
       v
Restore data directory
       |
       v
Cung cấp WAL archive liên tục từ T0
       |
       v
PostgreSQL recovery / replay WAL
       |
       v
Dừng tại recovery target T1
       |
       v
Database ở trạng thái tại T1
```

### 19.4. Không thể PITR nếu thiếu WAL giữa chừng

Nếu một segment bắt buộc bị mất, chuỗi recovery có thể bị đứt. Một archive directory có hàng nghìn file vẫn vô ích nếu thiếu đúng segment cần thiết.

### 19.5. Backup và archive cần tách failure domain

Nếu base backup và WAL archive nằm cùng một storage account/region bị xóa hoặc hỏng, khả năng phục hồi có thể mất cùng lúc. Cần cân nhắc replication, immutability, access controls và offsite copies.

### 19.6. Kiểm thử restore

Backup thành công về mặt log không chứng minh restore được. Thường xuyên dựng môi trường phục hồi, khôi phục base backup và replay WAL tới một target, sau đó xác minh dữ liệu ứng dụng.

---

## 20. PITR configuration ở mức khái niệm

Một recovery target cần cấu hình restore process theo phiên bản PostgreSQL. Các tham số thường gặp trong cấu hình recovery:

```conf
restore_command = 'restore-helper %f %p'
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
```

restore-helper là placeholder cho chương trình lấy segment từ archive. Trong các phiên bản hiện đại, việc yêu cầu archive recovery thường liên quan file signal như recovery.signal; quy trình restore/standby có file signal khác. Không tự tạo/xóa signal files ngoài quy trình tài liệu hóa cho phiên bản đang dùng.

### 20.1. restore_command

Được PostgreSQL gọi để lấy WAL segment từ archive. Lệnh phải trả về trạng thái phù hợp khi file có/không có, và phải xử lý an toàn tên file/path.

### 20.2. recovery_target_time

Dừng hoặc hành động theo thời điểm mục tiêu. Timezone cần được xác định rõ để tránh nhầm thời điểm local/UTC.

### 20.3. recovery_target_lsn

Có thể dùng LSN làm recovery target khi cần dừng tại một vị trí WAL cụ thể và biết LSN mục tiêu.

### 20.4. recovery_target_name

Có thể dùng named restore point đã được tạo trước đó bằng pg_create_restore_point.

### 20.5. recovery_target_action

Tùy chọn như pause, promote hoặc shutdown quyết định hành vi khi đạt target; giá trị được hỗ trợ phụ thuộc phiên bản.

### 20.6. Sau khi đạt target

Nếu promote để database nhận ghi mới, PostgreSQL tạo timeline mới. Không tiếp tục ghi vào cùng timeline cũ như thể không có nhánh recovery.

---

## 21. Timeline: khi recovery tạo nhánh WAL mới

Timeline giúp phân biệt các lịch sử WAL khác nhau sau failover hoặc PITR promotion.

```text
Timeline 1
Base backup
   |
   +---- WAL ---- WAL ---- Recovery target
                              |
                              | Promote
                              v
Timeline 2
                         WAL mới ---- WAL mới
```

### 21.1. Vì sao cần timeline?

Sau khi promote một standby hoặc hoàn tất PITR và tiếp tục ghi, lịch sử WAL mới có thể rẽ nhánh khỏi timeline cũ.

### 21.2. Timeline history file

PostgreSQL tạo timeline history file mô tả quan hệ timeline/ancestor và vị trí phân nhánh.

### 21.3. Backup phải lưu history files

Quản lý archive cần giữ timeline history files cùng WAL segments để khôi phục đúng nhánh.

### 21.4. Không chỉ dựa vào tên WAL segment

Hai timeline có thể có segment numbers tương tự nhưng thuộc lịch sử khác nhau. Archive tooling phải giữ tên file đầy đủ và không ghi đè segment từ timeline khác.

### 21.5. Failover và split brain

HA orchestration phải bảo đảm chỉ một primary nhận ghi tại một thời điểm. Timeline hỗ trợ recovery history nhưng không tự ngăn split brain nếu hệ thống failover điều phối sai.

---

## 22. Physical streaming replication và WAL

Physical replication truyền WAL từ primary tới standby để standby replay các thay đổi vật lý của cluster.

### 22.1. Primary gửi WAL

WAL sender processes gửi WAL stream tới standby qua replication protocol.

### 22.2. Standby nhận và replay

Standby WAL receiver nhận WAL, ghi WAL và startup process replay các records để cập nhật data pages.

### 22.3. Standby không chạy lại SQL

Physical standby áp dụng WAL records, không thực thi lại câu UPDATE gốc.

### 22.4. Standby có thể lag ở nhiều giai đoạn

- Primary tạo WAL.
- WAL được gửi.
- Standby nhận/ghi WAL.
- Standby replay WAL.

Các LSN tương ứng giúp phân biệt network lag với replay lag.

### 22.5. Xem replication status

```sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_catalog.pg_stat_replication;
```

Tên/cột view cần kiểm tra theo phiên bản.

### 22.6. Không nhầm standby nhận WAL với standby đã replay

Standby có thể đã nhận và flush WAL nhưng chưa apply. Query trên standby có thể chưa nhìn thấy dữ liệu mới nếu replay lag còn tồn tại.

---

## 23. Synchronous replication và commit acknowledgement

Synchronous replication cho phép primary đợi một hoặc nhiều standby xác nhận WAL theo chính sách.

### 23.1. synchronous_standby_names

Thiết lập này xác định standby nào được xem là synchronous và quy tắc chọn/quorum.

Ví dụ minh họa:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Cú pháp và lựa chọn FIRST/ANY cần kiểm tra theo phiên bản.

### 23.2. RPO có thể giảm

Nếu primary xác nhận commit sau khi standby flush WAL theo cấu hình, một số tình huống mất primary có thể chuyển sang standby mà không mất những commit đã được xác nhận theo policy đó.

### 23.3. Latency tăng

Primary phải đợi remote acknowledgement, vì vậy network và standby storage latency có thể tác động trực tiếp tới commit latency.

### 23.4. Standby mất kết nối

Khi không còn standby đủ điều kiện, hành vi commit phụ thuộc cấu hình synchronous replication, timeout và quyết định vận hành. Phải hiểu rõ availability trade-off.

### 23.5. Synchronous replication không thay backup

Một lỗi logic như DELETE nhầm có thể được replicate sang standby. Backup/PITR vẫn cần để quay về trước thời điểm lỗi.

---

## 24. Logical replication và WAL level

Logical replication dùng logical changes được trích xuất từ WAL thay vì chỉ replay physical page changes trên cùng cluster layout.

### 24.1. wal_level

Các mức WAL level quyết định thông tin được ghi cho recovery/replication/logical decoding. replica thường đủ cho physical replication và WAL archiving; logical ghi thêm thông tin cần cho logical decoding. minimal có các giới hạn khiến không phù hợp cho archive recovery/streaming replication thông thường.

```sql
SHOW wal_level;
```

### 24.2. Logical decoding

Logical decoding biến WAL thành một stream các thay đổi logic mà plugin/output format có thể tiêu thụ.

### 24.3. Logical replication không đồng nghĩa physical recovery

Logical subscriber có thể có schema, indexes và data layout riêng. WAL logic phục vụ đồng bộ dữ liệu giữa objects, không phải khôi phục nguyên trạng toàn bộ physical cluster.

### 24.4. Replica identity

UPDATE/DELETE logical replication cần xác định row identity theo cấu hình replica identity và index phù hợp. Đây là vấn đề khác với HOT update, dù cả hai cùng liên quan tới update semantics.

### 24.5. WAL volume có thể tăng

wal_level=logical và logical decoding requirements có thể làm WAL/retention workload khác so với chỉ physical replication. Đo trên workload thực tế.

---

## 25. Replication slots và WAL retention

Replication slots giữ WAL cần thiết cho consumer, giúp standby/logical subscriber không mất segment trước khi đọc.

### 25.1. Xem slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Một số cột chỉ có ở các phiên bản PostgreSQL mới hơn; điều chỉnh SELECT theo schema view của cluster.

### 25.2. Slot inactive

Một logical consumer bị dừng có thể để slot inactive trong thời gian dài. WAL cần thiết vẫn được giữ, có thể làm pg_wal tăng.

### 25.3. max_slot_wal_keep_size

Giới hạn lượng WAL giữ cho replication slots theo cấu hình phiên bản. Khi vượt giới hạn, slot có thể trở nên không còn dùng được cho việc bắt kịp và consumer cần được xử lý/reinitialize.

### 25.4. wal_keep_size

Giữ một lượng WAL tối thiểu cho standby theo cấu hình, nhưng không thay thế replication slot/archive đầy đủ.

### 25.5. max_wal_size không kiểm soát slot retention tuyệt đối

Replication slot hoặc archive failure có thể làm WAL tăng vượt max_wal_size. Phải giám sát disk usage và slot lag.

### 25.6. Không drop slot đang hoạt động tùy tiện

Drop slot có thể khiến consumer không còn lấy được WAL cần thiết. Kiểm tra owner, purpose, active status và khả năng resync trước khi thay đổi.

---

## 26. WAL disk usage và nguy cơ đầy filesystem

WAL có thể tích tụ do archive command thất bại, replication slot không tiến, standby offline quá lâu, logical consumer không xác nhận flush, checkpoint/WAL generation pressure, workload burst hoặc backup/replication configuration giữ WAL lâu.

### 26.1. Theo dõi thư mục pg_wal

Dung lượng pg_wal là chỉ số vận hành quan trọng. Dùng công cụ OS/monitoring để theo dõi disk free, không chỉ dựa vào max_wal_size.

### 26.2. Không xóa file WAL thủ công

Không xóa thủ công các files trong pg_wal để giải phóng dung lượng. Làm vậy có thể khiến cluster không thể crash recover hoặc replication/recovery bị đứt.

### 26.3. Xử lý đúng nguyên nhân

- Archive failure: khắc phục destination/permissions/network.
- Slot retention: xác định consumer và tiến độ.
- Standby offline: khôi phục hoặc reinitialize theo quy trình.
- WAL generation spike: đánh giá workload/checkpoint settings.
- Disk gần đầy: tăng dung lượng hoặc xử lý retention theo kế hoạch.

### 26.4. Alert theo trend

Một pg_wal đang chiếm 60% disk nhưng tăng rất nhanh có thể nguy hiểm hơn mức 80% ổn định. Alert nên xét growth rate, remaining capacity và thời gian dự kiến tới full.

---

## 27. WAL statistics và checkpoint monitoring

### 27.1. pg_stat_wal

Trên các phiên bản hỗ trợ view này (PostgreSQL 14 trở lên):

```sql
SELECT *
FROM pg_catalog.pg_stat_wal;
```

Có thể cung cấp WAL records, full-page images, bytes, buffers full và write/sync statistics theo phiên bản.

### 27.2. pg_stat_checkpointer

Các phiên bản PostgreSQL mới (PostgreSQL 17 trở lên) có view riêng cho checkpointer:

```sql
SELECT *
FROM pg_catalog.pg_stat_checkpointer;
```

Các phiên bản cũ có một số checkpoint statistics trong pg_stat_bgwriter. Không dùng tên cột của bản mới cho cluster cũ mà không kiểm tra.

### 27.3. pg_stat_bgwriter

```sql
SELECT *
FROM pg_catalog.pg_stat_bgwriter;
```

View này cung cấp các thông tin liên quan background writer và, tùy phiên bản, checkpoint statistics.

### 27.4. pg_stat_archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Theo dõi archive success/failure và thời điểm/file archive gần nhất.

### 27.5. Replication views

- pg_stat_replication: phía primary.
- pg_stat_wal_receiver: phía standby.
- pg_replication_slots: retention state.
- pg_stat_database: một số transaction/I/O counters tổng hợp.

### 27.6. Đo WAL generation delta

Có thể lấy snapshot pg_stat_wal trước và sau một khoảng thời gian rồi tính delta wal_bytes. Các counters là tích lũy và có thể reset; cần ghi timestamp và stats_reset để so sánh đúng.

### 27.7. Không kết luận chỉ từ checkpoint count

Cần xem timed/requested checkpoints, write/sync time, buffers written, WAL bytes, disk latency, checkpoint warnings và application latency.

---

## 28. Xem LSN và WAL progress

### 28.1. Primary current/flush LSN

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

### 28.2. Tính bytes giữa hai LSN

```sql
SELECT pg_wal_lsn_diff(
    '0/5000000',
    '0/4000000'
) AS wal_bytes;
```

Giá trị minh họa; trong production hãy truyền các LSN được thu thập từ cùng một WAL history phù hợp.

### 28.3. Standby replay LSN

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

Các hàm này giúp theo dõi receive/replay progress. Nếu không có WAL mới, timestamp replay có thể cũ dù standby không bị lỗi.

### 28.4. Primary và standby LSN

Không trừ LSN từ hai timeline/cluster không tương thích như thể chúng là cùng một stream. Cần biết timeline và replication relationship.

### 28.5. LSN không phải đồng hồ

Một khoảng LSN không trực tiếp cho biết bao nhiêu giây trễ nếu không có tốc độ WAL generation và thời gian đo tương ứng.

---

## 29. Công cụ kiểm tra WAL

### 29.1. pg_waldump

pg_waldump là tiện ích dòng lệnh có thể đọc và hiển thị thông tin WAL records ở mức chẩn đoán.

```bash
pg_waldump --path=/path/to/pg_wal --start=0/4000000 --end=0/5000000
```

Tên option và khả năng đọc WAL archive phụ thuộc phiên bản. Dùng đúng binary tương thích với cluster/WAL format.

### 29.2. pg_walinspect

Extension pg_walinspect cung cấp SQL functions để xem WAL records trong những phiên bản hỗ trợ.

```sql
CREATE EXTENSION IF NOT EXISTS pg_walinspect;
```

Sau đó đọc tài liệu phiên bản để chọn hàm và tham số phù hợp. Không giả định mọi cluster đều cài extension này.

### 29.3. pg_controldata

Tiện ích pg_controldata hiển thị thông tin control file, gồm checkpoint và cluster state. Nó chạy trên data directory với quyền OS phù hợp và nên dùng trong môi trường vận hành được kiểm soát.

### 29.4. Không sửa WAL records

WAL là dữ liệu nội bộ quan trọng. Không chỉnh sửa bytes hoặc đổi tên/xóa segments bằng tay để “sửa lỗi”.

### 29.5. pg_resetwal là phương án cuối cùng

pg_resetwal có thể reset WAL/control information trong tình huống corruption đặc biệt, nhưng có nguy cơ làm mất transaction history và tạo database không nhất quán về logic. Chỉ sử dụng theo hướng dẫn phục hồi chuyên gia, sau khi có bản sao data directory và đã đánh giá khả năng mất dữ liệu. Không dùng để dọn disk hoặc chữa archive backlog.

---

## 30. WAL, unlogged tables và temporary tables

### 30.1. Logged tables

Tables thông thường được WAL-logged để hỗ trợ crash recovery và physical replication.

### 30.2. UNLOGGED tables

UNLOGGED tables giảm WAL cho dữ liệu table theo semantics PostgreSQL, nhưng dữ liệu không được bảo đảm sau crash như logged tables và không được physical standby replicate như dữ liệu logged thông thường. Các indexes/metadata liên quan có hành vi tương ứng theo loại relation.

Không dùng UNLOGGED cho ledger, đơn hàng hoặc dữ liệu không thể tái tạo chỉ để giảm WAL.

### 30.3. Temporary tables

Temporary tables có semantics riêng theo session và không cần durability/replication giống bảng thường. Chúng phù hợp dữ liệu tạm có thể tạo lại.

### 30.4. Không nhầm giảm WAL với tăng durability

Ít WAL hơn không có nghĩa dữ liệu bền vững hơn. Đối với dữ liệu quan trọng, ưu tiên semantics recovery phù hợp thay vì loại bỏ logging.

---

## 31. WAL và bảo mật dữ liệu

WAL có thể chứa thông tin đủ để tái tạo thay đổi dữ liệu, bao gồm một số nội dung row/page. Archive có thể giữ dữ liệu cũ trong thời gian dài.

- Giới hạn người/role có thể đọc WAL archives. Không đặt archive directory ở nơi public hoặc cho mọi application account đọc.
- Xem xét mã hóa disk, object storage hoặc backup repository. PostgreSQL không tự mã hóa mọi WAL archive bằng một thiết lập đơn giản trên mọi deployment.
- WAL retention phải đáp ứng backup/PITR và replication nhưng cũng cần chính sách xóa an toàn.
- Archive credentials, cloud storage keys và backup access tokens cần quản lý như secrets.
- WAL không thay thế audit logs có user/session/object/action metadata.

---

## 32. Lab: xem WAL LSN trước và sau thao tác

Lab dùng schema riêng wal_lab.

> **Cảnh báo:** Chỉ chạy trên database thử nghiệm được phép. Lệnh DROP trong lab xóa schema cùng tên và các objects bên trong.

### 32.1. Tạo schema và bảng

```sql
DROP SCHEMA IF EXISTS wal_lab CASCADE;
CREATE SCHEMA wal_lab;

CREATE TABLE wal_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 32.2. Ghi lại LSN trước thao tác

```sql
SELECT pg_current_wal_lsn() AS before_lsn;
```

Ghi lại kết quả.

### 32.3. Insert một batch

```sql
INSERT INTO wal_lab.events (event_type, payload)
SELECT
    'heartbeat',
    'device-' || g::TEXT
FROM generate_series(1, 1000) AS g;
```

### 32.4. COMMIT và lấy LSN sau

Nếu dùng autocommit, câu INSERT được commit khi hoàn tất. Sau đó:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

### 32.5. Tính delta

So LSN trước/sau bằng pg_wal_lsn_diff với hai giá trị đã ghi lại:

```sql
SELECT pg_wal_lsn_diff(
    '0/LSN_AFTER',
    '0/LSN_BEFORE'
) AS generated_bytes;
```

Thay các placeholder bằng LSN thực tế; ví dụ trên không phải một câu SQL có thể chạy nguyên trạng.

### 32.6. Vì sao delta không bằng đúng số bytes row data?

WAL còn có record headers, transaction records, index changes, full-page images, alignment và các thay đổi hệ thống khác. WAL generation có thể gồm cả hoạt động đồng thời của cluster.

### 32.7. Chạy nhiều lần

Ghi lại baseline và delta trong thời gian workload yên tĩnh nếu muốn hiểu gần đúng lượng WAL do lab tạo.

---

## 33. Lab: manual checkpoint và quan sát checkpoint state

### 33.1. Xem setting

```sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
```

### 33.2. Ghi LSN trước checkpoint

```sql
SELECT pg_current_wal_lsn();
```

### 33.3. Yêu cầu checkpoint

```sql
CHECKPOINT;
```

Lệnh cần quyền thích hợp và có thể gây I/O. Chỉ chạy trong lab hoặc cửa sổ vận hành đã được chấp thuận.

### 33.4. Đọc lại LSN

```sql
SELECT
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
```

Checkpoint có thể sinh WAL record và làm thay đổi state; không mong đợi LSN quay về 0 hoặc các files WAL lập tức biến mất.

### 33.5. Đọc checkpoint stats

Trên phiên bản có pg_stat_checkpointer:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

Trên phiên bản cũ, xem checkpoint-related columns trong pg_stat_bgwriter.

### 33.6. Manual checkpoint không phải thao tác thường xuyên cho ứng dụng

Không chạy CHECKPOINT sau từng transaction hoặc request. Nó có thể gây write I/O lớn và phá vỡ lịch checkpoint được thiết kế cho workload.

---

## 34. Lab: quan sát archive và WAL switch

Lab này cần cluster đã bật WAL archiving và có archive destination được cấu hình an toàn. Nếu không có quyền quản trị cấu hình server, chỉ đọc trạng thái hiện có.

### 34.1. Kiểm tra cấu hình

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

### 34.2. Xem archiver statistics

```sql
SELECT *
FROM pg_stat_archiver;
```

### 34.3. Yêu cầu switch WAL

Trong lab có archive cấu hình đúng:

```sql
SELECT pg_switch_wal();
```

Hàm này yêu cầu chuyển sang WAL segment mới; segment cũ có thể được archive khi đủ điều kiện. Không gọi liên tục để ép archive từng vài giây trong production.

### 34.4. Kiểm tra archive destination

Dùng công cụ OS/storage phù hợp để xác minh file đã đến nơi, size/checksum hợp lệ và không bị ghi đè. Không chỉ dựa vào một câu SQL.

### 34.5. Kiểm tra failure path

Trong môi trường test, mô phỏng archive destination tạm thời không truy cập được và quan sát failed count, thời gian lỗi và disk growth. Khôi phục destination rồi xác nhận archiver bắt kịp.

Không cố tình làm hỏng archive production để thực hiện bài lab.

---

## 35. Lab: thử nghiệm PITR trong môi trường riêng

PITR cần quyền OS và một base backup. Không thể hoàn thành chỉ bằng SQL trong một database session.

### 35.1. Chuẩn bị

1. Tạo một PostgreSQL lab cluster riêng.
2. Bật archive_mode và cấu hình archive destination.
3. Tạo base backup bằng pg_basebackup hoặc công cụ tương thích.
4. Xác nhận WAL archive liên tục.
5. Ghi lại thời gian và restore point.

### 35.2. Tạo restore point

```sql
SELECT pg_create_restore_point('before_test_change');
```

Lưu LSN trả về cùng timestamp.

### 35.3. Tạo dữ liệu thử

```sql
INSERT INTO wal_lab.events(event_type, payload)
VALUES ('pitr-test', 'created-after-restore-point');
```

Ghi thời điểm/LSN và xác nhận row có mặt trên primary.

### 35.4. Restore bản sao riêng

Dùng base backup, WAL archive và cấu hình recovery target để khôi phục tới named restore point hoặc thời điểm đã ghi.

### 35.5. Xác minh

- Row trước restore point phải tồn tại.
- Row sau restore point phải không xuất hiện nếu recovery dừng trước nó.
- Database phải khởi động ở trạng thái mong đợi.
- Timeline/history phải được lưu đúng.
- Ứng dụng phải vượt qua smoke tests.

### 35.6. Đo RTO

Ghi thời gian từ lúc bắt đầu restore tới khi database và ứng dụng sẵn sàng. Không chỉ đo thời gian copy backup.

### 35.7. Đo RPO

Xác định khoảng dữ liệu có thể mất theo thời điểm recovery target và mức độ WAL được archive/flush. RPO không phải giá trị tự động được đảm bảo chỉ vì đã bật archive_mode.

---

## 36. Checkpoint tuning theo workload

### 36.1. Workload ghi nhiều

Một hệ thống ingest liên tục có thể tạo WAL nhanh. max_wal_size quá nhỏ có thể dẫn tới requested checkpoints thường xuyên.

### 36.2. Workload burst

Một batch import lớn có thể tạo nhiều WAL trong thời gian ngắn, kích hoạt checkpoint sớm. Cần theo dõi I/O và checkpoint statistics trước/sau batch.

### 36.3. Workload đọc nhiều

Nếu ít ghi, checkpoint pressure có thể thấp. Không cần tăng mọi WAL settings chỉ vì hệ thống có nhiều queries.

### 36.4. Storage throughput

Checkpoint ghi nhiều dirty pages. Storage có IOPS/throughput thấp có thể không hoàn thành công việc mượt dù checkpoint_completion_target cao.

### 36.5. Recovery time

Checkpoint quá thưa có thể làm lượng WAL redo sau crash lớn hơn. Test recovery time trên dữ liệu/volume thực tế.

### 36.6. Điều chỉnh từng tham số

1. Ghi baseline checkpoint/WAL metrics.
2. Xác định timed hay requested checkpoints chiếm ưu thế.
3. Xem WAL generation rate và disk capacity.
4. Kiểm tra full-page images.
5. Đánh giá storage write latency.
6. Thay một tham số có giả thuyết rõ.
7. Chạy workload tương đương.
8. Đo commit latency, checkpoint duration, WAL bytes và recovery time.
9. Giữ hoặc rollback dựa trên dữ liệu.

### 36.7. Không ép checkpoint quá nhanh

checkpoint_completion_target thấp có thể khiến writes tập trung hơn. Đặt giá trị quá thấp có thể tạo I/O spikes. Default thường là điểm khởi đầu tốt trước khi có evidence.

---

## 37. Những sự cố WAL/checkpoint thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| pg_wal tăng liên tục | Archive failure, slot lag, standby offline | Archiver, slots, disk trend |
| Requested checkpoints quá nhiều | WAL generation cao hoặc max_wal_size thấp | Checkpoint stats, WAL rate |
| Commit latency tăng | Storage flush chậm, sync replication lag | WAL sync stats, standby state |
| Standby replay lag | I/O/CPU standby, WAL burst | receive/replay LSN, standby load |
| Archive không bắt kịp | Destination/network/permissions | pg_stat_archiver, logs |
| Startup recovery lâu | WAL replay volume lớn, storage chậm | Checkpoint interval, WAL size |
| Invalid WAL record | WAL corruption, storage/transfer issue | logs, archive checksum, hardware |
| Page checksum error | Page corruption | backup, storage, FPI/recovery evidence |
| Recent commit mất sau crash | synchronous_commit=off, storage flush không đáng tin | durability settings, hardware |
| Database không khởi động | WAL/control/data corruption hoặc thiếu WAL | logs, backup, recovery plan |
| Disk đầy | Slot/archive retention hoặc workload spike | pg_wal usage, archive, slots |
| Archive file thiếu | Retention/permission/tool bug | timeline, archive inventory |
| PITR dừng sớm | Thiếu WAL segment hoặc target/timezone sai | archive continuity, target config |
| Standby cần resync | WAL bị recycle trước khi standby bắt kịp | slot, wal_keep_size, base backup |
| WAL volume tăng sau checkpoint | Full-page images | pg_stat_wal, FPI counters |

### 37.1. Không xóa WAL để chữa disk full

Nếu disk đầy, xử lý retention causes, tăng disk hoặc giải quyết archive/slot backlog theo quy trình. Xóa WAL thủ công có thể làm cluster không recovery được.

### 37.2. Không chạy pg_resetwal như bước đầu tiên

Cần xác định nguyên nhân và bảo toàn bản sao data directory trước khi cân nhắc recovery cực đoan.

### 37.3. Phân biệt archive failure và replication lag

Archive destination và standby streaming là hai đường tiêu thụ WAL khác nhau. Một đường có thể khỏe trong khi đường kia bị kẹt.

### 37.4. Log server là bằng chứng quan trọng

Thu thập PostgreSQL logs quanh thời điểm lỗi, OS/storage logs, archive logs và metrics. Không suy ra nguyên nhân chỉ từ một thông báo disk usage.

---

## 38. Backup strategy và recovery objectives

### 38.1. RPO

**Recovery Point Objective** là lượng dữ liệu tối đa doanh nghiệp chấp nhận mất, thường được diễn đạt bằng thời gian hoặc một điểm dữ liệu.

### 38.2. RTO

**Recovery Time Objective** là thời gian mục tiêu để khôi phục dịch vụ sau sự cố.

### 38.3. WAL archive interval ảnh hưởng RPO

Nếu WAL chỉ được archive khi segment đầy hoặc theo archive_timeout, thời điểm gần nhất có thể khôi phục từ archive phụ thuộc việc segment đã được archive an toàn và các điều kiện khác.

### 38.4. Base backup cadence ảnh hưởng recovery cost

Base backup mới hơn có thể giảm số WAL cần replay nhưng tốn storage/backup bandwidth. Chọn lịch dựa vào RTO, storage và khả năng vận hành.

### 38.5. Full backup không thay WAL continuity

Một base backup không tự cho phép PITR tới mọi thời điểm. Cần chuỗi WAL liên tục từ backup start/consistent point tới recovery target.

### 38.6. Logical dump có mục tiêu khác

pg_dump tạo logical backup để restore schema/data theo objects. Nó không thay thế physical base backup + WAL archive cho PITR vật lý liên tục.

### 38.7. Thực hành restore định kỳ

Một lịch backup không hoàn chỉnh nếu không có restore drills, checksum verification, quyền truy cập archive và runbook được cập nhật.

---

## 39. Các thiết lập cần xem trước khi thay đổi

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart,
    source
FROM pg_catalog.pg_settings
WHERE name = ANY (ARRAY[
    'wal_level',
    'wal_buffers',
    'wal_writer_delay',
    'wal_writer_flush_after',
    'wal_sync_method',
    'fsync',
    'full_page_writes',
    'wal_compression',
    'synchronous_commit',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'archive_mode',
    'archive_timeout',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'max_wal_senders',
    'max_replication_slots'
])
ORDER BY name;
```

### 39.1. Context

pg_settings.context cho biết tham số có thể đổi ở session, reload hay cần restart theo phiên bản/cấu hình.

### 39.2. pending_restart

Cho biết giá trị cấu hình có hiệu lực sau restart hay không trong những trường hợp tương ứng.

### 39.3. Quản lý cấu hình

Sử dụng quy trình quản lý config có versioning, review và kiểm tra restart requirements. ALTER SYSTEM có thể ghi postgresql.auto.conf; cần biết precedence và quản lý file đó.

### 39.4. Đổi durability settings cần review

Thay fsync, full_page_writes hoặc synchronous_commit có thể thay đổi cam kết mất dữ liệu. Đánh giá theo RPO, hardware và business policy trước khi áp dụng.

---

## 40. Thiết kế WAL retention an toàn

### 40.1. Xác định consumer

Liệt kê các nhu cầu WAL:

- Crash recovery nội bộ.
- WAL archiver.
- Physical standby.
- Logical replication slots.
- Logical decoding consumers.
- Base backup/PITR windows.

### 40.2. Xác định retention target

Lập kế hoạch số ngày archive, số standby có thể offline, tốc độ WAL generation tối đa và dung lượng dự phòng.

### 40.3. Theo dõi slot lag

Một logical slot không hoạt động có thể giữ WAL vô hạn nếu không có giới hạn phù hợp. Cần alert theo retained bytes và tuổi inactivity.

### 40.4. Archive cleanup theo backup dependency

Không xóa WAL archive chỉ vì segment đã cũ. Kiểm tra mọi base backups còn được giữ và khoảng WAL cần thiết để restore chúng.

### 40.5. Kiểm tra timeline history

Giữ timeline history files và WAL segments liên quan; không xóa một nhánh cần cho backup còn tồn tại.

### 40.6. Không dùng max_wal_size làm archive retention policy

max_wal_size điều khiển checkpoint pressure, không phải thời gian giữ WAL cho PITR hoặc consumer slots.

---

## 41. Tình huống A: COMMIT thành công nhưng data file chưa đổi

**Bối cảnh:** Ứng dụng ghi đơn hàng và nhận COMMIT success. Người vận hành kiểm tra file relation ngay sau đó và nghĩ rằng data chưa được ghi.

### 41.1. Giải thích

COMMIT success theo synchronous durability có nghĩa WAL commit record đã được flush theo policy. Data pages có thể vẫn dirty trong shared buffers.

### 41.2. Điều gì bảo vệ dữ liệu?

WAL-before-data rule bảo đảm khi page được ghi xuống, WAL liên quan đã bền vững. Nếu crash trước khi page ghi, recovery redo từ WAL.

### 41.3. Checkpoint khi nào?

Checkpoint diễn ra theo timeout/WAL pressure/manual request, không phải sau từng COMMIT.

### 41.4. Cách kiểm chứng

Sử dụng SQL, transaction semantics, WAL metrics và recovery tests. File layout là implementation detail; không kiểm tra relation file trực tiếp để kết luận transaction.

---

## 42. Tình huống B: ổ đĩa pg_wal sắp đầy

**Bối cảnh:** Monitoring báo filesystem chứa pg_wal còn 5% free.

### 42.1. Điều tra nhanh

- Kiểm tra pg_stat_archiver và archive errors.
- Kiểm tra replication slots inactive/lag.
- Kiểm tra standby receive/replay LSN.
- Xem WAL generation rate.
- Kiểm tra dung lượng archive destination.
- Xem PostgreSQL logs.

### 42.2. Hành động

- Khắc phục archive destination nếu lỗi.
- Khôi phục standby/consumer nếu có thể.
- Xác định slot không còn dùng và xử lý theo runbook.
- Tăng storage capacity nếu cần.
- Điều tiết workload nếu WAL generation spike.

### 42.3. Không xóa WAL file

WAL có thể đang cần cho recovery/replication. Xóa thủ công có thể khiến database không khởi động hoặc standby không bắt kịp.

### 42.4. Sau sự cố

Đánh giá retention settings, alert thresholds, capacity forecast và kiểm tra archive completeness.

---

## 43. Tình huống C: crash và mất commit gần nhất

**Bối cảnh:** Một service đã nhận COMMIT success nhưng sau restart không thấy một số transaction gần nhất.

### 43.1. Kiểm tra synchronous_commit

Nếu transaction/session dùng synchronous_commit=off, PostgreSQL có thể đã trả response trước khi WAL flush.

### 43.2. Kiểm tra fsync/storage

Nếu fsync=off hoặc storage không thực hiện flush đúng semantics, durability có thể bị vi phạm nghiêm trọng.

### 43.3. Kiểm tra synchronous replication expectations

Nếu ứng dụng hiểu nhầm on luôn có nghĩa remote standby đã apply, có thể có sai lệch giữa kỳ vọng và cấu hình thực tế. on với sync standby thường đợi remote flush, không nhất thiết remote apply.

### 43.4. Network ambiguous outcome

Nếu client timeout lúc COMMIT, transaction có thể đã commit dù client không nhận response. Đây là trường hợp khác với transaction đã nhận success rồi mất sau crash.

### 43.5. Cải thiện ứng dụng

Dùng idempotency keys, transaction identifiers nghiệp vụ và quy trình reconciliation để xử lý retry/ambiguous outcomes.

---

## 44. Tình huống D: recovery kéo dài sau restart

**Bối cảnh:** Database mất nhiều phút hoặc giờ để hoàn tất crash recovery.

### 44.1. Các yếu tố

- Khoảng WAL từ checkpoint redo point tới crash.
- WAL generation rate.
- Storage read/write throughput.
- Full-page images và workload.
- Số lượng records cần replay.
- Page cache và checkpoint history.

### 44.2. Điều tra

- Đọc PostgreSQL startup/recovery logs.
- Xem checkpoint frequency và requested checkpoints.
- Kiểm tra WAL segment availability/continuity.
- Đánh giá storage throughput.
- So sánh recovery time với RTO.

### 44.3. Không chỉ tăng checkpoint frequency

Checkpoint thường xuyên hơn có thể giảm lượng redo nhưng tăng I/O/FPI. Phải benchmark cả steady-state workload và recovery time.

### 44.4. Recovery test

Dùng bản sao production-sized hoặc môi trường tương đương để đo thời gian restart/replay thực tế.

---

## 45. Tình huống E: standby lag sau bulk load

**Bối cảnh:** Một import lớn bằng COPY hoàn tất trên primary, nhưng read replica bị trễ.

### 45.1. WAL burst

COPY trên bảng logged tạo WAL cho data changes và indexes/constraints tương ứng.

### 45.2. Receive lag và replay lag

So sánh sent/write/flush/replay LSN để biết standby chưa nhận đủ WAL hay đã nhận nhưng apply chậm.

### 45.3. Checkpoint I/O

Bulk load có thể làm checkpoint writes và storage I/O tăng, ảnh hưởng cả primary lẫn standby.

### 45.4. Giải pháp vận hành

- Lên lịch batch vào thời gian phù hợp.
- Đo WAL rate và standby apply capacity.
- Kiểm tra indexes/constraints và batch size.
- Theo dõi disk, WAL archive và slot retention.
- Không tắt durability để che replication bottleneck.

---

## 46. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| COMMIT success nghĩa mọi data pages đã ghi xuống | WAL đã flush theo policy; pages có thể vẫn dirty |
| WAL là SQL log | WAL là log nội bộ phục vụ recovery/replication |
| Write thành công nghĩa dữ liệu đã bền vững | Có thể mới ở OS page cache |
| Checkpoint là COMMIT | Checkpoint là hoạt động đồng bộ cluster |
| Checkpoint là backup | Không; cần base backup và WAL |
| Mỗi transaction cần một checkpoint | Checkpoint chạy theo lịch/pressure |
| WAL chỉ ghi khi checkpoint | WAL được tạo liên tục theo thao tác ghi |
| Data page được ghi trước WAL | Vi phạm write-ahead rule |
| WAL flush không liên quan durability | Flush là phần cốt lõi của commit durability |
| synchronous_commit=off làm database luôn corrupt | Có thể mất commit gần đây, nhưng recovery consistency vẫn được duy trì theo WAL bền vững |
| fsync=off chỉ tăng tốc nhẹ | Có nguy cơ corruption sau crash |
| full_page_writes off luôn an toàn | Có nguy cơ torn page khi storage không atomic |
| FPI là backup toàn database | FPI là page image trong WAL |
| Page checksum thay thế full_page_writes | Hai cơ chế có mục tiêu khác nhau |
| Background writer và checkpointer là một | Vai trò khác nhau |
| max_wal_size là giới hạn cứng | WAL có thể vượt do slots/archive/retention |
| WAL cũ có thể xóa khi checkpoint xong | Có thể còn cần cho archive/standby/backup |
| Archive mode bật nghĩa PITR chắc chắn hoạt động | Cần base backup và WAL continuity |
| pg_dump + WAL archive luôn tương đương physical PITR | Logical backup và physical recovery có mục tiêu khác |
| Standby nhận WAL là đã có thể đọc thay đổi mới | Có thể chưa replay |
| Synchronous replication là backup | Lỗi logic cũng replicate |
| remote_write tương đương remote_flush | Chưa chắc bền vững tới storage |
| remote_flush nghĩa standby đã apply | Flush khác apply |
| Replication slot luôn an toàn | Slot inactive có thể giữ WAL làm đầy disk |
| max_wal_size kiểm soát slot retention | Không phải retention cap |
| wal_keep_size thay thế replication slots/archive | Không |
| Logical replication là physical replication | Hai cơ chế và mục đích khác nhau |
| WAL không chứa dữ liệu nhạy cảm | Có thể chứa thông tin đủ để tái tạo thay đổi |
| pg_resetwal là cách dọn pg_wal | Đây là công cụ recovery cực đoan, có rủi ro mất dữ liệu |
| LSN là timestamp | LSN là vị trí trong WAL stream |
| LSN diff luôn là độ trễ thời gian | Là byte distance, không phải time |
| Checkpoint càng nhiều càng tốt | Tăng I/O và có thể tăng FPI |
| Checkpoint càng thưa càng tốt | Có thể tăng recovery time/WAL retention |
| WAL compression miễn phí | Có CPU cost và hiệu quả tùy dữ liệu |
| UNLOGGED table vẫn physical replicate như logged | Không theo semantics logged tables |
| Backup thành công nghĩa restore được | Cần restore drills và validation |
| Một lần PITR lab chứng minh mọi backup | Cần kiểm tra nhiều target/failure modes |
| COMMIT timeout nghĩa transaction rollback | Có thể là ambiguous outcome |
| Archive file tồn tại nghĩa file hoàn chỉnh | Cần checksum/size/continuity verification |

---

## 47. Bài tập thực hành

### Bài 1 — Write-Ahead Logging

Giải thích nguyên tắc WAL và điều gì có thể xảy ra nếu data page được ghi trước WAL tương ứng.

### Bài 2 — WAL vs data files

Phân biệt WAL records, WAL segments, heap files và index files. Nêu mục tiêu của mỗi loại.

### Bài 3 — LSN

Chạy pg_current_wal_lsn() trước/sau một INSERT. Vì sao LSN tăng không nhất thiết bằng số bytes row data?

### Bài 4 — Page LSN

Giải thích vai trò page LSN khi recovery quyết định áp dụng WAL record.

### Bài 5 — WAL buffers

Phân biệt wal_buffers và shared_buffers. Một transaction ghi vào vùng bộ nhớ nào?

### Bài 6 — Write và flush

Giải thích vì sao write vào OS page cache chưa luôn có nghĩa dữ liệu đã bền vững qua mất điện.

### Bài 7 — Commit path

Vẽ luồng từ UPDATE tới COMMIT, bao gồm heap/index dirty pages, WAL record, commit record và flush.

### Bài 8 — Group commit

Nhiều transaction cùng commit có thể giảm số lần fsync như thế nào?

### Bài 9 — Dirty pages

Vì sao PostgreSQL có thể xác nhận COMMIT khi data pages vẫn dirty trong shared buffers?

### Bài 10 — synchronous_commit

So sánh off, local, remote_write, remote_flush và remote_apply. Giá trị nào đợi standby replay?

### Bài 11 — fsync

Nêu rủi ro khi tắt fsync trên production. Vì sao không thể coi đây là một tuning option bình thường?

### Bài 12 — full_page_writes

Giải thích torn page và cách full-page images hỗ trợ recovery.

### Bài 13 — wal_compression

Nêu lợi ích và CPU trade-off khi nén full-page images.

### Bài 14 — Checkpoint

Giải thích checkpoint, redo point và checkpoint record. Vì sao checkpoint không phải backup?

### Bài 15 — Checkpoint pressure

Phân biệt timed checkpoint và requested checkpoint. Những metrics nào cho biết checkpoint quá thường xuyên?

### Bài 16 — max_wal_size

Vì sao max_wal_size không phải hard cap của pg_wal?

### Bài 17 — checkpoint_completion_target

Giải thích mục tiêu của tham số này và ảnh hưởng khi đặt quá thấp.

### Bài 18 — Crash recovery

Một transaction commit đã flush WAL nhưng data page chưa ghi. Server crash. Mô tả quá trình khôi phục.

### Bài 19 — Transaction chưa commit

Một transaction sửa page rồi server crash trước COMMIT. Vì sao dữ liệu của transaction không trở thành committed sau recovery?

### Bài 20 — WAL replay

Vì sao recovery phát lại WAL records thay vì chạy lại câu SQL gốc?

### Bài 21 — Archive

Thiết kế archive helper idempotent và mô tả điều kiện trả success.

### Bài 22 — Archive failure

Archive command lỗi liên tục. Vì sao pg_wal có thể tăng và cách điều tra?

### Bài 23 — Base backup

Giải thích vì sao WAL archive không đủ nếu không có base backup phù hợp.

### Bài 24 — PITR

Thiết kế quy trình restore tới một recovery_target_time. Những file/configuration nào cần có theo phiên bản?

### Bài 25 — Timeline

Vẽ timeline 1 và timeline 2 sau promotion. Vì sao archive cần giữ history files?

### Bài 26 — Physical replication

Phân biệt WAL send, write, flush và replay LSN. Một standby đã flush nhưng chưa replay có thể đọc dữ liệu mới chưa?

### Bài 27 — Synchronous replication

Giải thích RPO và latency trade-off khi dùng synchronous standby.

### Bài 28 — Logical replication

Phân biệt logical decoding với physical replay. Vì sao wal_level=logical có thể tăng overhead?

### Bài 29 — Replication slots

Một logical slot inactive giữ WAL trong nhiều ngày. Điều gì xảy ra và nên alert theo chỉ số nào?

### Bài 30 — wal_keep_size

Vì sao wal_keep_size không thay thế một kế hoạch archive/slot retention?

### Bài 31 — Monitoring

Viết truy vấn lấy pg_stat_archiver, pg_stat_replication, pg_replication_slots và các checkpoint stats phù hợp phiên bản.

### Bài 32 — WAL delta

Dùng pg_wal_lsn_diff tính bytes giữa hai LSN. Vì sao không thể diễn giải trực tiếp là seconds of lag?

### Bài 33 — pg_waldump

Mô tả cách dùng pg_waldump trong chẩn đoán và vì sao binary phải tương thích WAL format.

### Bài 34 — pg_resetwal

Vì sao pg_resetwal chỉ là biện pháp cuối cùng? Nêu những rủi ro về transaction history/data consistency.

### Bài 35 — UNLOGGED

So sánh logged và UNLOGGED tables về WAL, crash recovery và physical replication.

### Bài 36 — Backup restore drill

Thiết kế một restore drill có base backup, WAL archive, recovery target và application smoke tests.

### Bài 37 — RPO/RTO

Một hệ thống có RPO 5 phút, RTO 30 phút. Đề xuất backup cadence, WAL archiving, monitoring và restore testing để kiểm chứng mục tiêu.

### Bài 38 — Disk full

Filesystem pg_wal còn 5%. Lập thứ tự điều tra archive, slots, standby, WAL generation và storage. Vì sao không xóa WAL bằng tay?

### Bài 39 — Durability incident

Ứng dụng nhận COMMIT success nhưng mất transaction sau crash. Liệt kê các cấu hình/storage conditions cần kiểm tra.

### Bài 40 — Ambiguous commit

Client timeout trong lúc COMMIT. Thiết kế idempotency/reconciliation để retry không tạo giao dịch trùng.

### Bài 41 — Bulk load

Một COPY lớn làm standby lag. Dùng LSN để xác định receive lag hay replay lag, rồi đề xuất điều chỉnh batch/replication capacity.

### Bài 42 — Checkpoint benchmark

Thiết kế thử nghiệm thay đổi checkpoint_timeout/max_wal_size trên staging. Đo steady-state I/O, WAL volume, commit latency và recovery time.

### Bài 43 — Archive security

WAL archive chứa dữ liệu nhạy cảm. Đề xuất access control, encryption, retention, immutability và credential rotation.

### Bài 44 — Version compatibility

Một query trên pg_stat_checkpointer lỗi trên PostgreSQL cũ. Xây dựng cách xác định version và chọn view tương ứng.

### Bài 45 — Production runbook

Viết runbook xử lý WAL archive backlog, slot retention, disk pressure và standby lag, gồm escalation và validation.

### Bài 46 — Thiết kế end-to-end

Một hệ thống order processing cần RPO gần 0 khi primary mất, PITR 14 ngày, standby đọc báo cáo và lượng ghi cao. Thiết kế WAL settings, synchronous replication, archive/base backup, slot policy, checkpoint tuning, monitoring, storage capacity và restore drills. Nêu các trade-offs về latency, availability và chi phí.

---

## 48. Checklist vận hành WAL và checkpoint

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| WAL được bật và ở level phù hợp? | wal_level |
| fsync có bật? | Durability policy |
| full_page_writes có bật? | Torn-page protection |
| synchronous_commit phù hợp transaction? | Commit durability |
| Storage có flush semantics đáng tin? | OS/controller/cloud volume |
| WAL disk còn đủ dung lượng? | pg_wal capacity/trend |
| Timed/requested checkpoints ra sao? | Checkpointer stats |
| Checkpoint write/sync time? | I/O pressure |
| FPI/WAL bytes tăng? | pg_stat_wal |
| max_wal_size hợp lý? | WAL rate và recovery |
| checkpoint_completion_target? | Write smoothing |
| Archive mode và command? | archive_mode, archive settings |
| Archive success/failure? | pg_stat_archiver |
| Archive destination bền vững? | Checksum/replication/immutability |
| WAL archive liên tục? | Missing segment checks |
| Base backup gần nhất? | Backup catalog |
| WAL từ base backup tới target đủ? | PITR continuity |
| Restore drill gần nhất? | RTO/RPO evidence |
| Timeline history được giữ? | Archive inventory |
| Standby receive/flush/replay lag? | pg_stat_replication |
| Synchronous standby state? | sync_state/quorum |
| Logical slots inactive? | pg_replication_slots |
| Slot retained WAL bytes? | Capacity/alerts |
| max_slot_wal_keep_size? | Version/config policy |
| Standby offline lâu? | Rebuild/resync plan |
| Không xóa WAL thủ công? | Runbook |
| WAL archive access restricted? | Least privilege |
| Archive encrypted? | At-rest protection |
| Retention policy rõ? | Backup dependency |
| Secret được quản lý? | Rotation/access logs |
| Monitoring theo trend? | Time-to-full alerts |
| Commit latency có baseline? | p95/p99 |
| Crash recovery time có đo? | RTO test |
| pg_resetwal có bị dùng sai? | Emergency-only procedure |
| Version-specific stats được xử lý? | View/column compatibility |
| Backup không cùng failure domain? | Offsite/independent copy |
| Ứng dụng xử lý ambiguous commit? | Idempotency/reconciliation |
| Có kế hoạch rollback config? | Versioned settings |

## Kết luận

**WAL và checkpoint** là nền tảng để PostgreSQL vừa xử lý transaction ghi hiệu quả vừa có thể khôi phục database sau crash.

Những nguyên tắc cần nhớ:

1. **WAL phải được ghi bền vững trước data pages tương ứng.** Đây là write-ahead rule, bảo đảm recovery có log để redo khi data page chưa được ghi hoàn tất.
2. **COMMIT và checkpoint là hai sự kiện khác nhau.** COMMIT xác nhận transaction theo durability settings; checkpoint đồng bộ dirty pages và thiết lập redo point.
3. **WAL flush là trọng tâm của commit durability.** Data pages có thể vẫn dirty sau khi client nhận COMMIT success.
4. **fsync và full_page_writes bảo vệ tính toàn vẹn sau crash.** Tắt chúng có thể tạo rủi ro mất dữ liệu hoặc corruption nghiêm trọng.
5. **synchronous_commit quyết định mức đợi khi commit.** remote_flush và remote_apply có semantics khác nhau; synchronous replication làm tăng latency nhưng có thể giảm RPO.
6. **Checkpoint cần được cân bằng.** Quá thường xuyên làm tăng I/O/FPI; quá thưa có thể tăng WAL retention và recovery time.
7. **WAL archive cần đi cùng base backup.** PITR chỉ đáng tin khi có chuỗi WAL liên tục và đã được kiểm thử restore.
8. **Timeline phải được quản lý đúng.** Failover hoặc promotion tạo nhánh WAL mới; archive cần giữ timeline history.
9. **Replication slots có thể giữ WAL rất lâu.** Theo dõi slot lag và dung lượng disk; không xóa WAL thủ công.
10. **Monitoring phải phân biệt write, flush và replay.** Current LSN, flush LSN, standby receive/replay LSN và archiver stats trả lời các câu hỏi khác nhau.
11. **Backup thành công chưa chứng minh khôi phục được.** Cần restore drills, checksum/continuity checks và đo RTO/RPO.
12. **Durability là cam kết end-to-end.** PostgreSQL, hệ điều hành, storage, archive và runbook đều phải thực hiện đúng vai trò.

Một hệ thống PostgreSQL đáng tin cậy không chỉ ghi được transaction nhanh. Nó phải biết transaction nào đã bền vững, WAL nào còn cần giữ, checkpoint đang tiến triển ra sao, standby đã replay tới đâu và liệu một base backup cùng WAL archive có thể khôi phục dữ liệu đúng mục tiêu sau sự cố hay không.
