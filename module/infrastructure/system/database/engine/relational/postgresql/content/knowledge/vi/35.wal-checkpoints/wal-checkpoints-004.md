# Checkpoint, redo point và thời gian khôi phục sự cố trong PostgreSQL

PostgreSQL ghi nhận thay đổi dữ liệu trước tiên vào **Write-Ahead Log (WAL)**. Các trang dữ liệu trong data files có thể được ghi xuống đĩa muộn hơn, theo checkpoint hoặc cơ chế background writer. Khi máy chủ bị crash, PostgreSQL cần biết phải bắt đầu đọc WAL từ đâu để đưa các trang dữ liệu về trạng thái nhất quán. Vị trí bắt đầu đó được gọi là **redo point**.

Checkpoint là một mốc nhất quán quan trọng trong chuỗi WAL. Nó giúp PostgreSQL xác định phần WAL cũ hơn có thể không còn cần cho crash recovery của cluster hiện tại, sau khi các điều kiện liên quan đã được thỏa mãn. Khoảng cách từ checkpoint gần nhất tới thời điểm crash ảnh hưởng trực tiếp tới lượng WAL phải replay và là một yếu tố quan trọng của **thời gian khôi phục sự cố (recovery time)**.

Các khái niệm này liên hệ chặt chẽ nhưng không đồng nghĩa:

```text
WAL record       = nhật ký mô tả thay đổi cần redo
Checkpoint      = quá trình ghi các dirty data pages và tạo mốc checkpoint
Checkpoint LSN  = vị trí của checkpoint record
Redo LSN        = vị trí WAL mà crash recovery phải bắt đầu replay
Crash recovery  = replay WAL từ redo point để khôi phục trạng thái nhất quán
```

Một checkpoint thường xuyên hơn có thể làm giảm lượng WAL cần replay sau crash, nhưng cũng có thể tăng I/O ghi, tạo checkpoint bursts và làm tăng full-page images trong WAL. Vì vậy, tuning checkpoint là bài toán cân bằng giữa **độ bền, hiệu năng ghi, dung lượng WAL và mục tiêu RTO**, không đơn giản là đặt checkpoint càng ngắn càng tốt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao PostgreSQL cần WAL và checkpoint.
2. Phân biệt checkpoint, checkpoint record, checkpoint LSN và redo LSN.
3. Mô tả quá trình tạo checkpoint và các điều kiện để checkpoint hoàn tất an toàn.
4. Giải thích crash recovery bắt đầu từ redo point và replay WAL như thế nào.
5. Phân biệt crash recovery, archive recovery/PITR và recovery của standby.
6. Hiểu quan hệ giữa checkpoint interval, `max_wal_size`, `checkpoint_timeout` và `checkpoint_completion_target`.
7. Giải thích full-page images, `full_page_writes` và tác động của checkpoint lên WAL volume.
8. Theo dõi checkpoint bằng `pg_stat_checkpointer` hoặc view tương ứng theo PostgreSQL major.
9. Dùng `pg_control_checkpoint()` và `pg_controldata` để quan sát checkpoint/redo information.
10. Phân biệt checkpoint của primary với restartpoint của standby.
11. Phân tích WAL retention, archive backlog, replication slots và disk growth.
12. Ước lượng recovery time, xác định RTO/RPO và xây dựng bài kiểm tra phục hồi.
13. Điều chỉnh checkpoint có đo lường và tránh các cấu hình gây I/O spikes.

## 2. WAL là nền tảng của crash recovery

WAL là nhật ký tuần tự ghi lại thông tin cần thiết để khôi phục những thay đổi database. Quy tắc cốt lõi của Write-Ahead Logging:

> **WAL record mô tả một thay đổi phải được ghi bền vững trước khi data page chứa thay đổi đó được phép ghi xuống storage.**

### 2.1. Vì sao không ghi ngay từng data page?

Một transaction có thể thay đổi nhiều rows, indexes và pages. Nếu mỗi lần thay đổi đều phải ghi data page ngay lập tức, random I/O và chi phí đồng bộ sẽ rất cao. PostgreSQL gom WAL records theo luồng tuần tự, rồi có thể ghi các data pages theo lịch background/checkpoint.

Ví dụ:

```text
Transaction UPDATE account
       |
       v
Buffer page trong shared_buffers thay đổi (dirty)
       |
       +---- WAL records được tạo
       |
       v
WAL được flush tới durable storage khi cần COMMIT
       |
       v
Data page có thể được ghi xuống disk sau đó
```

Nếu máy chủ mất điện sau khi COMMIT đã được xác nhận nhưng trước khi data page được ghi, WAL vẫn cho phép PostgreSQL redo thay đổi khi khởi động lại, với điều kiện cấu hình và storage đáp ứng durability assumptions.

### 2.2. WAL record và LSN

Mỗi vị trí trong WAL được biểu diễn bằng **Log Sequence Number (LSN)**. LSN là địa chỉ byte trong luồng WAL, thường hiển thị dạng hai phần hex:

```text
0/16B6C50
0/16B7000
0/16B9A20
```

LSN có thứ tự tăng dần khi WAL được tạo. Nó không phải timestamp, transaction ID hay số thứ tự row. Hai LSN cách nhau 1 MB không có nghĩa đúng 1 giây đã trôi qua; tốc độ sinh WAL phụ thuộc workload.

### 2.3. WAL segment

WAL được chia thành các files có kích thước segment cố định (thường 16 MB mặc định, có thể chọn khác khi initdb). File nằm trong thư mục `pg_wal`. Tên segment mã hóa timeline và phạm vi LSN.

Một LSN được ánh xạ vào:

- WAL segment chứa byte tương ứng.
- Offset bên trong segment.

Không tự sửa, truncate, rename hoặc xóa files trong `pg_wal`. PostgreSQL quản lý segment recycling/removal dựa trên checkpoint, archiving, replication và các yêu cầu giữ WAL khác.

### 2.4. COMMIT và durability

Ở cấu hình thông thường `synchronous_commit=on`, PostgreSQL chờ WAL của transaction được flush tới storage bền vững trước khi báo COMMIT thành công cho client. Data pages có thể chưa được ghi, vì WAL đủ để phục hồi.

`synchronous_commit=off` có thể cho client nhận xác nhận trước khi WAL được flush; database vẫn có crash recovery consistency, nhưng những transactions vừa được xác nhận có thể mất nếu máy chủ crash trước flush. Tuning checkpoint không thay thế durability policy.

### 2.5. WAL không phải bản sao đầy đủ của database

WAL chỉ có ý nghĩa kết hợp với data files/base backup tương ứng. Không thể lấy một thư mục WAL rời rồi dựng lại toàn bộ database từ đầu nếu không có base backup hoặc data directory phù hợp.

## 3. Checkpoint là gì?

Checkpoint là một quá trình phối hợp giữa PostgreSQL để:

1. Đảm bảo WAL cần thiết đã được flush.
2. Ghi các dirty buffers liên quan xuống data files.
3. Tạo checkpoint record trong WAL.
4. Cập nhật thông tin checkpoint trong control file để startup biết checkpoint hợp lệ gần nhất.

Khi checkpoint hoàn tất, PostgreSQL có một mốc mà từ đó có thể xác định điểm redo cần thiết cho crash recovery tiếp theo.

### 3.1. Dirty page là gì?

Một page trong shared buffers được gọi là **dirty** khi nội dung trong RAM đã thay đổi so với bản trên storage. Ví dụ UPDATE một row có thể làm dirty heap page và một hoặc nhiều index pages.

Dirty page chưa ghi xuống disk không đồng nghĩa dữ liệu đã mất. Nếu WAL record tương ứng đã bền vững, PostgreSQL có thể tái áp dụng thay đổi sau crash.

### 3.2. Checkpoint không chỉ là “flush WAL”

WAL flush và data page flush là hai hoạt động khác nhau:

- **WAL flush:** ghi log đến một LSN bền vững.
- **Data page write:** ghi page của heap/index/system catalogs xuống data files.

Checkpoint phối hợp cả hai theo quy tắc WAL. Chỉ flush WAL không đủ để tạo checkpoint hoàn chỉnh; chỉ ghi data page mà WAL tương ứng chưa bền vững sẽ vi phạm WAL rule.

### 3.3. Checkpoint record

Cuối quá trình checkpoint, PostgreSQL ghi một record đặc biệt trong WAL. Record này mang thông tin checkpoint, trong đó có **redo pointer** – LSN mà crash recovery phải bắt đầu redo.

Checkpoint record được ghi ở một vị trí LSN khác với redo pointer. Đây là lý do không nên gọi chung cả hai là “checkpoint LSN”.

### 3.4. Checkpoint là mốc, không phải backup

Checkpoint không tạo bản sao độc lập để restore về thời điểm đó. Nó không thay thế base backup, WAL archive, replication hoặc snapshot storage. Nó chủ yếu giúp xác định recovery start point và đồng bộ dirty pages.

### 3.5. Checkpoint không đồng nghĩa mọi transaction đều kết thúc

Checkpoint có thể diễn ra khi các transactions khác vẫn đang chạy. Những transaction chưa COMMIT không trở thành committed chỉ vì checkpoint. Checkpoint đảm bảo data/WAL consistency, còn visibility của rows vẫn tuân theo MVCC và transaction status.

### 3.6. Shutdown checkpoint

Khi PostgreSQL shutdown theo chế độ bình thường/fast, server thực hiện checkpoint để có thể khởi động lại trong trạng thái clean. Shutdown immediate bỏ qua một số bước shutdown/checkpoint và lần startup kế tiếp phải chạy crash recovery.

## 4. Checkpoint LSN và redo LSN

Hai vị trí này rất dễ nhầm.

### 4.1. Checkpoint LSN

**Checkpoint LSN** thường chỉ vị trí của checkpoint record được ghi trong WAL. Nó nhận diện record checkpoint mà control file đang tham chiếu.

### 4.2. Redo LSN

**Redo LSN** là vị trí bắt đầu WAL replay cần thiết cho crash recovery. PostgreSQL đọc từ redo point và áp dụng các WAL records theo thứ tự cho đến WAL hợp lệ cuối cùng có sẵn trong recovery stream.

Redo point thường nằm **trước** checkpoint record, vì những thay đổi kể từ checkpoint trước đó có thể đã tạo dirty pages cần được ghi hoặc replay.

### 4.3. Ví dụ timeline

```text
WAL LSN tăng dần  ---------------------------------------------------->

      Redo LSN                Checkpoint record
         |                           |
         v                           v
---------+---------------------------+-------------------------------+
         |<---- WAL cần thiết ------>|
         |
         +-- Startup crash recovery bắt đầu từ đây

Sau checkpoint hoàn tất, crash xảy ra:
      |
      v
Recovery replay từ redo LSN tới WAL cuối cùng hợp lệ
```

Sơ đồ chỉ minh họa quan hệ khái niệm; LSN cụ thể và các record khác có thể nằm xen kẽ.

### 4.4. Vì sao redo LSN không bằng checkpoint LSN?

Checkpoint record mô tả mốc checkpoint đã hoàn thành. Nhưng để đảm bảo tất cả thay đổi có thể được phục hồi, PostgreSQL phải replay từ một LSN sớm hơn nếu các data pages chưa đảm bảo đã phản ánh toàn bộ thay đổi sau điểm đó.

Vì thế:

- Checkpoint LSN trả lời: **checkpoint record hiện tại ở đâu?**
- Redo LSN trả lời: **nếu crash ngay bây giờ, WAL phải replay từ đâu?**

### 4.5. Redo LSN không phải LSN của transaction chưa commit

Redo point không có nghĩa “transaction bắt đầu tại đây” hay “mọi transaction sau đây phải commit”. Nó là vị trí trong WAL cần để tái tạo trạng thái page nhất quán. Transaction visibility được xử lý bằng transaction status/MVCC, không suy ra chỉ từ redo LSN.

### 4.6. Redo distance

Có thể quan sát khoảng cách giữa WAL hiện tại và redo LSN để ước lượng phạm vi WAL cần replay:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_control_checkpoint().redo_lsn AS redo_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        pg_control_checkpoint().redo_lsn
    ) AS bytes_since_redo;
```

Đây là **khoảng cách byte LSN**, không phải dự đoán chính xác thời gian recovery. Nó có thể thay đổi ngay khi checkpoint hoàn tất và không phản ánh toàn bộ chi phí I/O/CPU/replay.

## 5. Checkpoint diễn ra khi nào?

PostgreSQL có thể khởi tạo checkpoint theo nhiều lý do.

### 5.1. checkpoint_timeout

`checkpoint_timeout` giới hạn khoảng thời gian tối đa giữa các checkpoints tự động trong hoạt động bình thường. Giá trị mặc định thường là 5 phút, nhưng cần kiểm tra đúng major và cấu hình môi trường.

```sql
SHOW checkpoint_timeout;
```

Nếu workload ít WAL và chưa vượt ngưỡng WAL, timeout có thể là nguyên nhân kích hoạt checkpoint tiếp theo.

### 5.2. max_wal_size

`max_wal_size` đặt mục tiêu mềm về lượng WAL giữa checkpoints tự động. Khi lượng WAL được tạo kể từ checkpoint gần nhất vượt ngưỡng ước tính, PostgreSQL có thể yêu cầu checkpoint sớm hơn timeout.

```sql
SHOW max_wal_size;
```

Đây **không phải hard cap** cho kích thước `pg_wal`. WAL có thể vượt max_wal_size vì:

- Archive command chậm hoặc thất bại.
- Replication slot giữ WAL cũ.
- Standby chậm replay/nhận WAL.
- Checkpoint chưa thể hoàn tất hoặc workload tạo WAL rất nhanh.
- Những điều kiện vận hành khác yêu cầu giữ segment.

### 5.3. CHECKPOINT thủ công

Superuser hoặc role có quyền `pg_checkpoint` có thể gọi:

```sql
CHECKPOINT;
```

Lệnh yêu cầu checkpoint ngay. Không chạy liên tục trong ứng dụng hoặc cron chỉ vì muốn “đẩy dữ liệu xuống disk”; checkpoint thủ công dày đặc có thể tăng I/O và WAL full-page images.

### 5.4. Shutdown checkpoint

Shutdown bình thường hoặc fast thực hiện checkpoint để đóng cluster trong trạng thái clean. Shutdown immediate không chờ các bước thông thường và startup sau đó sẽ cần crash recovery.

### 5.5. Checkpoint không được kích hoạt bởi từng COMMIT

COMMIT chủ yếu cần flush WAL theo durability settings; nó không buộc mọi dirty data pages phải ghi xuống disk ngay. Nếu checkpoint chạy cho từng transaction, hệ thống sẽ bị I/O overhead rất lớn.

### 5.6. Checkpoint request và checkpoint completion

Một checkpoint có thể bắt đầu vì timeout hoặc WAL threshold, nhưng quá trình ghi pages có thể kéo dài. `checkpoint_completion_target` điều tiết tốc độ hoàn thành theo khoảng checkpoint dự kiến. Vì vậy thời điểm request, thời điểm bắt đầu và thời điểm hoàn tất không nhất thiết trùng nhau.

## 6. Quá trình checkpoint diễn ra như thế nào?

Ở mức khái niệm, checkpoint phối hợp:

1. Xác định vị trí WAL và dirty buffers cần quan tâm.
2. Đảm bảo WAL trước các page writes được flush theo WAL rule.
3. Ghi dirty buffers ra data files, có thể phân tán theo thời gian.
4. Hoàn tất checkpoint và ghi checkpoint record.
5. Cập nhật control information để lần startup sau nhận diện checkpoint hợp lệ.

Chi tiết nội bộ có thể thay đổi theo PostgreSQL major, nhưng nguyên tắc WAL-before-data và redo pointer vẫn là nền tảng.

### 6.1. Background writer và checkpointer

Background writer có thể ghi dirty buffers trước checkpoint để giảm áp lực cho backend/checkpointer. Checkpointer chịu trách nhiệm hoàn tất checkpoint và ghi các buffers cần thiết để đảm bảo checkpoint semantics.

Hai thành phần có vai trò liên quan nhưng không đồng nhất:

- Background writer làm việc nền nhằm giảm nhu cầu backend phải ghi dirty buffers khi cần cấp buffer.
- Checkpointer thực hiện công việc checkpoint có tính hệ thống và cập nhật thống kê checkpoint.

### 6.2. Backend cũng có thể ghi dirty buffers

Một backend có thể phải ghi dirty buffers trong một số tình huống, chẳng hạn cần giải phóng buffer. Không phải mọi data page write đều do checkpointer thực hiện. Vì thế thống kê checkpoint không phải tổng mọi I/O ghi của database.

### 6.3. Checkpoint flushes

Checkpoint có thể phải ghi rất nhiều pages. Nếu dồn writes vào một khoảng ngắn, storage latency và query latency có thể tăng. PostgreSQL cố gắng trải đều writes để giảm burst.

### 6.4. WAL phải đi trước data page

Khi checkpointer chuẩn bị ghi một data page có LSN mới, WAL tương ứng phải được flush tới ít nhất LSN cần thiết trước khi page được ghi. Điều này bảo vệ khả năng redo nếu data page write bị torn/mất trong crash.

### 6.5. Checkpoint hoàn tất mới cập nhật mốc

PostgreSQL không thể tuyên bố một checkpoint mới hợp lệ trước khi những điều kiện ghi page/WAL cần thiết đã hoàn thành. Nếu server crash giữa checkpoint, startup sẽ sử dụng checkpoint hợp lệ trước đó và replay WAL từ redo point cũ hơn.

### 6.6. Checkpoint không cần dừng mọi query

Queries và transactions tiếp tục hoạt động trong khi checkpoint chạy. Các locks/page latches cần thiết được quản lý ở mức nội bộ; checkpoint không phải một lệnh “đóng băng toàn bộ database”.

## 7. Crash recovery: PostgreSQL sử dụng redo point ra sao?

Khi server khởi động và phát hiện lần shutdown trước không hoàn tất sạch, PostgreSQL thực hiện crash recovery.

### 7.1. Đọc trạng thái control file

Startup đọc control file (`global/pg_control`) để biết checkpoint hợp lệ gần nhất và thông tin redo cần thiết. Control file chứa metadata quan trọng như:

- Checkpoint location.
- Redo location.
- Timeline ID.
- Trạng thái cluster và các thông tin WAL/checkpoint liên quan.

Control file là dữ liệu nội bộ quan trọng. Không tự sửa bằng hex editor hoặc copy từ một cluster khác.

### 7.2. Bắt đầu replay từ redo LSN

PostgreSQL tìm WAL segment cần thiết, đọc record theo thứ tự và thực hiện redo các thay đổi lên data pages. WAL records có thể mô tả thay đổi heap, index, catalog, transaction status và các cấu trúc nội bộ khác.

### 7.3. Page LSN giúp xác định record đã được áp dụng chưa

Data page có LSN mô tả WAL record gần nhất đã được phản ánh vào page. Trong redo, PostgreSQL có thể so sánh LSN của page với LSN của record để xác định có cần áp dụng lại thay đổi hay không.

Điều này giúp recovery xử lý tình huống một số page đã được ghi xuống disk trước crash, còn một số page thì chưa.

### 7.4. Redo và transaction visibility

PostgreSQL chủ yếu dùng **redo**, không dùng một undo log truyền thống để đảo từng thay đổi chưa commit như một số database engines khác.

Trong lúc recovery:

- WAL records cần thiết được replay để page structures nhất quán.
- Transaction commit/abort status được khôi phục từ WAL và transaction status data.
- Transaction đang hoạt động tại thời điểm crash không được xem là committed nếu không có commit record hợp lệ.
- Các tuples chưa commit sẽ không trở thành dữ liệu nhìn thấy hợp lệ cho ứng dụng; việc dọn phiên bản không còn cần thiết tiếp tục qua vacuum.

Vì vậy, “redo một page” không có nghĩa mọi dữ liệu transaction chưa commit được công bố cho users.

### 7.5. Recovery kết thúc ở WAL hợp lệ cuối cùng

Crash recovery replay WAL liên tục tới điểm cuối có thể khôi phục. Nếu cần đọc WAL archive, PostgreSQL có thể yêu cầu các segments tiếp theo theo cấu hình recovery. Với crash recovery thông thường trên primary, sau khi đạt điểm cuối hợp lệ và hoàn tất các bước startup, database mở cho connections.

### 7.6. Recovery có thể phát hiện WAL thiếu hoặc hỏng

Nếu WAL segment cần thiết không tồn tại, bị hỏng hoặc không khớp timeline/system identifier, recovery có thể dừng với lỗi. Không xóa WAL/restore nhầm segment để “cho server chạy”; cần xác định data directory, archive chain, timeline và base backup tương ứng.

### 7.7. Vì sao checkpoint rút ngắn crash recovery?

Redo LSN là điểm bắt đầu replay. Checkpoint mới hoàn tất thường đưa redo point tiến gần WAL hiện tại hơn, giảm phạm vi WAL cần đọc sau crash. Tuy nhiên recovery time còn phụ thuộc I/O, loại WAL records, data pages phải đọc/ghi và phần cứng; redo distance chỉ là một chỉ báo.

## 8. Checkpoint và full-page images (FPI)

Checkpoint có ảnh hưởng tới lượng WAL do cơ chế **full_page_writes**.

### 8.1. Torn page là gì?

Một data page có thể được ghi xuống storage qua nhiều sector/block. Nếu power loss xảy ra giữa lúc ghi, page có thể chỉ được ghi một phần (**torn page**). Khi đó, chỉ replay các thay đổi nhỏ từ WAL có thể không đủ để tái tạo page đúng.

### 8.2. full_page_writes

Khi `full_page_writes=on`, PostgreSQL ghi full-page image (FPI) của một page vào WAL ở lần thay đổi đầu tiên của page sau checkpoint (theo cơ chế tương ứng). Nếu page bị torn, recovery có thể dùng FPI để khôi phục toàn page trước khi áp dụng những thay đổi tiếp theo.

```sql
SHOW full_page_writes;
```

Đây thường là thiết lập nên giữ bật. Tắt FPI khi storage có thể torn writes có thể gây mất khả năng phục hồi page; chỉ cân nhắc thay đổi khi hiểu rõ bảo vệ phần cứng/filesystem và rủi ro.

### 8.3. Checkpoint thường xuyên có thể tăng WAL

Sau mỗi checkpoint, page có thể cần FPI ở lần sửa đầu tiên tiếp theo. Nếu checkpoint quá thường xuyên, cùng một page nóng có thể tạo nhiều FPI trong khoảng thời gian ngắn hơn. WAL volume có thể tăng đáng kể, đặc biệt với workload cập nhật nhiều pages.

### 8.4. WAL compression

`wal_compression` có thể nén full-page images để giảm dung lượng WAL, đổi lại sử dụng CPU. Tùy phiên bản PostgreSQL, có thể chọn thuật toán nén được hỗ trợ:

```sql
SHOW wal_compression;
```

Kiểm tra tài liệu đúng major trước khi đặt giá trị thuật toán cụ thể. Nén FPI không có nghĩa toàn bộ WAL records đều được nén.

### 8.5. wal_log_hints

`wal_log_hints` yêu cầu PostgreSQL ghi WAL cho một số thay đổi hint bits để hỗ trợ các cơ chế như data checksums-related page protection/pg_rewind prerequisites theo tài liệu. Nó cũng có thể ảnh hưởng tới FPI/WAL volume. Không bật/tắt theo cảm tính; xem yêu cầu replication/rewind và cấu hình cluster.

### 8.6. Đo FPI

View `pg_stat_wal` có trường `wal_fpi` trên các phiên bản hỗ trợ:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full
FROM pg_stat_wal;
```

Nếu `wal_fpi` chiếm tỷ lệ cao trong tổng WAL, xem checkpoint frequency, workload page churn, `full_page_writes`, compression và các thay đổi cấu hình gần đây.

### 8.7. Không tắt full_page_writes để “giảm WAL” một cách tùy tiện

FPI có chi phí, nhưng tồn tại để bảo vệ page integrity sau crash. Tối ưu checkpoint, compression, storage và workload trước khi cân nhắc thay đổi durability safeguards.

## 9. Các tham số checkpoint quan trọng

Checkpoint tuning chủ yếu dùng một nhóm tham số có quan hệ với nhau.

### 9.1. checkpoint_timeout

Giới hạn khoảng thời gian giữa các automatic checkpoints. Tăng giá trị có thể giảm số checkpoint do timeout, nhưng redo distance sau crash có thể dài hơn và WAL được giữ lại lâu hơn do checkpoint.

### 9.2. max_wal_size

Mục tiêu mềm cho WAL được sinh giữa checkpoints tự động. Tăng giá trị thường cho phép checkpoints cách xa hơn theo WAL volume, giảm checkpoint frequency trong workload ghi nhiều, nhưng cần disk capacity và backup/replication planning.

### 9.3. min_wal_size

`min_wal_size` đặt lượng WAL tối thiểu mà PostgreSQL cố giữ lại để tái sử dụng trong `pg_wal`, tránh xóa rồi tạo lại files liên tục khi workload dao động.

```sql
SHOW min_wal_size;
```

Nó không phải giới hạn tối thiểu của WAL archive và không bảo đảm mọi WAL cần cho replica/archive đều được giữ vô hạn.

### 9.4. checkpoint_completion_target

Điều tiết mục tiêu trải đều checkpoint writes trong khoảng thời gian trước checkpoint tiếp theo. Giá trị cao hơn thường làm writes được phân tán đều hơn, giảm burst; không làm tổng số dirty pages cần ghi biến mất.

Ví dụ:

```sql
SHOW checkpoint_completion_target;
```

Không hiểu tham số này là “checkpoint chỉ hoàn thành đúng 90%”. Nó là tỷ lệ mục tiêu của khoảng checkpoint dự kiến dùng để trải đều công việc.

### 9.5. checkpoint_flush_after

`checkpoint_flush_after` điều khiển ngưỡng bytes ghi trước khi yêu cầu kernel flush dirty data xuống storage (nếu platform hỗ trợ semantics tương ứng). Có thể giúp hạn chế dirty data dồn trong OS cache, nhưng hiệu quả phụ thuộc filesystem/kernel/storage.

### 9.6. checkpoint_warning

`checkpoint_warning` có thể log cảnh báo nếu checkpoints do WAL volume xảy ra quá thường xuyên. Đây là công cụ phát hiện cấu hình `max_wal_size` quá thấp so với tốc độ sinh WAL; không tự động giải quyết nguyên nhân.

### 9.7. wal_buffers

`wal_buffers` là bộ nhớ đệm WAL trong shared memory, không phải kích thước checkpoint. Nó ảnh hưởng tới cách backend ghi WAL; PostgreSQL thường tự chọn giá trị hợp lý khi khởi tạo. Không tăng wal_buffers để thay cho việc điều chỉnh checkpoint nếu vấn đề là data-page I/O.

### 9.8. wal_writer_delay và wal_writer_flush_after

Các tham số WAL writer điều khiển nhịp flush WAL nền và ngưỡng flush liên quan. Chúng có thể ảnh hưởng latency/throughput WAL, nhưng không thay thế durability contract của COMMIT hoặc checkpoint.

### 9.9. Bảng tác động định tính

| Tham số | Tăng giá trị thường có xu hướng | Đánh đổi cần xem |
| --- | --- | --- |
| `checkpoint_timeout` | Ít checkpoint theo thời gian hơn. | Redo distance sau crash có thể dài hơn. |
| `max_wal_size` | Cho phép nhiều WAL hơn giữa checkpoints. | `pg_wal`/retention có thể cần nhiều disk hơn. |
| `min_wal_size` | Giữ nhiều segments để tái sử dụng hơn. | Dành trước dung lượng disk. |
| `checkpoint_completion_target` | Trải checkpoint writes lâu hơn trong interval. | Có thể đẩy writes gần checkpoint tiếp theo; workload/storage vẫn cần đo. |
| `checkpoint_flush_after` | Tăng ngưỡng bytes trước yêu cầu flush. | Dirty pages có thể dồn nhiều hơn tùy platform. |
| `wal_buffers` | Có thể giảm contention/buffer pressure trong workload WAL cao. | Shared memory tăng; không chữa checkpoint I/O. |
| `wal_compression` | Có thể giảm WAL bytes do FPI. | Dùng thêm CPU. |

Giá trị phù hợp phụ thuộc tốc độ WAL, tốc độ storage, page churn, archive/replication lag và mục tiêu RTO.

## 10. Checkpoint frequency và recovery time: mối quan hệ đánh đổi

### 10.1. Checkpoint dày

Ưu điểm:

- Redo point thường tiến gần hiện tại hơn.
- Lượng WAL phải replay sau crash có thể ít hơn.
- Một số tình huống cần recycle WAL có thể được giải phóng sớm hơn nếu không còn retention blockers.

Chi phí:

- Nhiều checkpoint writes hơn.
- Tăng I/O và có thể tạo latency spikes nếu không trải đều tốt.
- Có thể tăng full-page images và WAL volume.
- Storage phải xử lý nhiều writes hơn.

### 10.2. Checkpoint thưa

Ưu điểm:

- Giảm tần suất checkpoint.
- Có thể giảm lặp lại FPI sau các checkpoint liên tiếp.
- Giảm overhead checkpoint trong một số workloads.

Chi phí:

- Redo point có thể xa hơn WAL hiện tại.
- Crash recovery có thể cần replay nhiều WAL hơn.
- WAL segments có thể được giữ lâu hơn vì checkpoint chưa tiến.
- Sau crash, thời gian khôi phục có thể tăng.

### 10.3. Không có một giá trị checkpoint tối ưu cho mọi database

Database OLTP nhiều updates, database analytics ít ghi, hệ thống có archive/replication và workload bulk load có đặc điểm rất khác. Tuning cần dựa trên workload thực, không copy một con số từ blog.

### 10.4. checkpoint_completion_target không thay checkpoint interval

Tham số này chủ yếu **làm mượt tốc độ ghi**. Nó không tự tăng/giảm thời gian giữa các checkpoints như `checkpoint_timeout` và không thay đổi trực tiếp mục tiêu WAL volume như `max_wal_size`.

### 10.5. max_wal_size không giới hạn crash recovery WAL bytes tuyệt đối

Checkpoint, archive, replication slot và standby có thể giữ WAL vượt ngưỡng. Vì thế không suy ra “max_wal_size=4GB thì pg_wal không bao giờ vượt 4GB” hoặc “recovery chỉ replay tối đa 4GB”.

## 11. Theo dõi checkpoint và redo point

Không tuning bằng cảm giác. Hãy quan sát checkpoint counts, thời gian write/sync, số buffers đã ghi, WAL generation và redo distance.

### 11.1. Xem cấu hình đang áp dụng

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_flush_after',
    'checkpoint_warning',
    'full_page_writes',
    'wal_compression',
    'wal_buffers',
    'log_checkpoints'
)
ORDER BY name;
```

`pg_settings` cho biết giá trị hiệu lực và nguồn cấu hình. `pending_restart` giúp nhận ra tham số đã thay đổi trong file nhưng cần restart mới áp dụng.

### 11.2. PostgreSQL 17 trở lên: pg_stat_checkpointer

Trong PostgreSQL 17+, thống kê checkpoint được tách thành view `pg_stat_checkpointer`:

```sql
SELECT
    num_timed,
    num_requested,
    restartpoints_timed,
    restartpoints_requested,
    restartpoints_done,
    write_time,
    sync_time,
    buffers_written,
    stats_reset
FROM pg_stat_checkpointer;
```

Các trường quan trọng:

- `num_timed`: số checkpoint được kích hoạt theo timeout.
- `num_requested`: số checkpoint được yêu cầu do WAL threshold hoặc request khác.
- `write_time`: thời gian ghi checkpoint buffers (đơn vị milliseconds trong thống kê).
- `sync_time`: thời gian đồng bộ file trong checkpoint.
- `buffers_written`: số buffers được checkpoint ghi.
- Các trường restartpoint liên quan hoạt động recovery/standby.

Đây là counters tích lũy từ lần reset stats gần nhất, không phải số liệu của riêng phút hiện tại. Lấy snapshot theo thời gian rồi tính delta.

### 11.3. PostgreSQL 16 trở xuống: pg_stat_bgwriter

Ở các major cũ, thống kê checkpoint nằm trong `pg_stat_bgwriter`. Những cột quen thuộc gồm:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    checkpoint_write_time,
    checkpoint_sync_time,
    buffers_checkpoint,
    buffers_clean,
    maxwritten_clean,
    buffers_backend,
    buffers_backend_fsync,
    buffers_alloc,
    stats_reset
FROM pg_stat_bgwriter;
```

Schema thống kê thay đổi giữa major; không copy query PG16 vào PG17+ rồi kết luận server lỗi nếu cột đã chuyển view. Kiểm tra `server_version_num` và documentation đúng phiên bản.

### 11.4. Đo tỷ lệ checkpoint requested

Nếu `checkpoints_req` hoặc `num_requested` tăng nhanh so với checkpoint timed, có thể `max_wal_size` quá nhỏ so với tốc độ WAL hoặc workload tạo WAL bursts. Đây là tín hiệu cần điều tra, không tự động chứng minh chỉ cần tăng max_wal_size.

### 11.5. Đo checkpoint write/sync time

`write_time` và `sync_time` cao có thể cho thấy storage ghi hoặc fsync chậm. Xem thêm OS/storage metrics, latency, queue depth, WAL sync và query latency. Không chỉ nhìn tổng milliseconds tích lũy rồi kết luận checkpoint đang chậm; phải tính delta theo khoảng thời gian.

### 11.6. log_checkpoints

Bật `log_checkpoints` để ghi log chi tiết mỗi checkpoint:

```sql
SHOW log_checkpoints;
```

Ví dụ cấu hình:

```conf
log_checkpoints = on
```

Log có thể ghi checkpoint start/end, buffers written, WAL added/removed/recycled và timing tùy major. Dùng log để ghép với workload/latency cùng timestamp.

### 11.7. pg_stat_wal

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

View này giúp xem lượng WAL records/bytes và full-page images. Nếu `wal_bytes` tăng mạnh sau khi rút checkpoint interval, kiểm tra tỷ lệ `wal_fpi` và workload updates.

### 11.8. Đo redo point và checkpoint record

```sql
SELECT *
FROM pg_control_checkpoint();
```

Hàm trả thông tin checkpoint từ control file, bao gồm các trường như `checkpoint_lsn`, `redo_lsn`, `redo_wal_file`, timeline IDs và cờ liên quan. Hàm quản trị này cần quyền phù hợp (thường superuser hoặc quyền giám sát được tài liệu chỉ định).

Truy vấn tập trung:

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    prev_timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

### 11.9. Xem redo distance

```sql
WITH checkpoint_state AS (
    SELECT redo_lsn, checkpoint_lsn
    FROM pg_control_checkpoint()
)
SELECT
    checkpoint_lsn,
    redo_lsn,
    pg_current_wal_lsn() AS current_wal_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            redo_lsn
        )::bigint
    ) AS approximate_redo_distance
FROM checkpoint_state;
```

Chạy trên primary có hàm `pg_current_wal_lsn()`. Trên standby, dùng LSN replay phù hợp (ví dụ `pg_last_wal_replay_lsn()`) và hiểu rằng standby đang recovery, không tạo WAL như primary.

### 11.10. pg_controldata

Trên host có quyền đọc data directory, dùng tiện ích:

```bash
pg_controldata "$PGDATA"
```

Output có các dòng như:

- Latest checkpoint location.
- Latest checkpoint's REDO location.
- Latest checkpoint's REDO WAL file.
- Latest checkpoint's TimeLineID.
- Latest checkpoint's PrevTimeLineID.
- Latest checkpoint's full_page_writes.

`pg_controldata` đọc control file của data directory. Chọn đúng `PGDATA`/cluster; không lấy control data từ một instance khác rồi suy luận trạng thái server hiện tại.

### 11.11. Xem WAL hiện tại

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
```

Các hàm current WAL LSN dùng trên primary. Trên standby, dùng các hàm replay như `pg_last_wal_receive_lsn()` và `pg_last_wal_replay_lsn()` theo mục đích.

### 11.12. Reset statistics

Một số thống kê có thể reset bằng các hàm thống kê quản trị phù hợp. Không reset counters trong giờ điều tra production nếu dashboard/alert phụ thuộc chúng; ghi lại snapshot trước và lưu ý thời điểm `stats_reset`.

## 12. WAL retention, archive và checkpoint

Checkpoint có thể giúp WAL segments cũ đủ điều kiện recycle, nhưng không phải điều kiện duy nhất. PostgreSQL phải giữ WAL nếu một thành phần khác còn cần.

### 12.1. WAL recycling

Sau checkpoint, WAL segments cũ hơn mức không còn cần cho crash recovery có thể được recycle hoặc xóa, nếu không có yêu cầu retention khác. Recycle nghĩa là tái sử dụng file segment thay vì tạo file mới; không phải archive.

### 12.2. archive_mode và archive_command

Khi archiving được bật, PostgreSQL copy WAL segments đã hoàn tất tới archive destination theo `archive_command` hoặc archive library tương ứng. Nếu archive command thất bại, server giữ WAL segments cần archive và thử lại.

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

Archive backlog có thể làm `pg_wal` tăng vượt `max_wal_size`. Đây là bảo vệ để không xóa WAL chưa archive thành công.

### 12.3. archive_timeout

`archive_timeout` có thể buộc switch WAL segment sau khoảng thời gian cấu hình nếu có WAL đang được ghi, giúp archive nhận segments sớm hơn trong workload ít WAL. Nó không tạo một checkpoint và không đảm bảo segment chỉ có một số bytes nhỏ; segment archive vẫn có kích thước chuẩn.

### 12.4. Replication slots

Replication slots giữ WAL cần thiết cho subscribers/standbys. Nếu consumer ngừng nhận hoặc slot bị bỏ quên, WAL có thể tích lũy và làm đầy disk.

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

Các cột `wal_status`/`safe_wal_size` có ở major mới; schema view thay đổi theo phiên bản. Với major cũ, bỏ cột không được hỗ trợ và kiểm tra tài liệu.

### 12.5. max_slot_wal_keep_size

`max_slot_wal_keep_size` có thể giới hạn lượng WAL mà replication slot giữ lại, tùy major. Nếu giới hạn bị vượt, slot có thể mất khả năng tiếp tục streaming và cần resync/reinitialize. Không đặt quá thấp nếu standby/consumer không thể bắt kịp.

### 12.6. wal_keep_size

`wal_keep_size` giữ một lượng WAL tối thiểu cho standby streaming theo cấu hình. Nó không thay thế archive hoặc slot khi cần đảm bảo WAL retention cho consumer bị offline lâu.

### 12.7. Checkpoint không giải phóng WAL bị slot giữ

Ngay cả khi checkpoint đã tiến redo LSN, PostgreSQL vẫn phải giữ WAL từ restart LSN cần thiết của slot hoặc các retention constraints khác. Vì vậy tăng checkpoint frequency không chữa được một replication slot bị lag mãi.

### 12.8. Theo dõi disk growth

Theo dõi:

- Dung lượng filesystem chứa `pg_wal`.
- Số WAL segments ready/archive failed.
- Archive lag và thời gian archive command.
- Replication slot restart LSN và WAL retained.
- Standby receive/replay lag.
- Alert khi disk còn ít chỗ hoặc WAL tăng bất thường.

Không tự xóa file trong `pg_wal` để giải phóng disk. Nếu archive hoặc slot giữ WAL, xử lý nguyên nhân đúng và theo runbook.

## 13. Restartpoint trên standby

Một standby đang replay WAL cũng cần ghi các data pages đã thay đổi xuống storage để có thể khởi động lại nhanh hơn. Nhưng standby đang ở chế độ recovery, nên cơ chế tương ứng được gọi là **restartpoint**, không phải checkpoint thông thường của primary.

### 13.1. Restartpoint là gì?

Restartpoint là checkpoint-like operation trên standby, giúp ghi các thay đổi đã replay và tạo điểm có thể bắt đầu lại recovery nếu standby restart/crash.

### 13.2. Restartpoint bị ràng buộc bởi checkpoint records từ primary

Standby chỉ có thể hoàn tất restartpoint tại một checkpoint record được nhận trong WAL stream. Do đó, restartpoint không thể xảy ra thường xuyên hơn checkpoint records do primary tạo ra. Một yêu cầu restartpoint có thể phải đợi checkpoint record tiếp theo.

### 13.3. Vì sao standby cần restartpoint?

- Ghi replayed dirty pages xuống data files.
- Giảm lượng WAL phải replay lại nếu standby crash/restart.
- Cho phép recycle/remove WAL segments cũ hơn khi không còn cần cho recovery, archive hoặc replication.

### 13.4. max_wal_size trên standby

Standby cũng có thể có nhu cầu giữ WAL trong quá trình recovery. Nếu restartpoint chưa thể chạy vì chưa nhận checkpoint record mới, lượng WAL có thể vượt mục tiêu. Đừng xem `max_wal_size` là giới hạn cứng cho WAL directory.

### 13.5. Thống kê restartpoints

Trên PostgreSQL 17+, `pg_stat_checkpointer` có các counters:

```sql
SELECT
    restartpoints_timed,
    restartpoints_requested,
    restartpoints_done
FROM pg_stat_checkpointer;
```

Ở major cũ, các trường restartpoint có thể nằm trong `pg_stat_bgwriter`. Kiểm tra schema view theo phiên bản.

### 13.6. Checkpoint primary không phải restartpoint standby

Primary tạo checkpoint record và cập nhật checkpoint state của chính nó. Standby nhận record đó qua WAL, rồi có thể dùng nó làm cơ hội tạo restartpoint trên storage của standby. Hai hoạt động có quan hệ nhưng không cùng một checkpoint state.

### 13.7. Không yêu cầu checkpoint primary để chữa standby lag

Nếu standby bị lag do network, replay throughput hoặc slot/archive backlog, chạy `CHECKPOINT` trên primary không tự sửa nguyên nhân. Cần xác định receive lag, replay lag, I/O và WAL retention.

## 14. Crash recovery khác archive recovery/PITR

Hai quy trình đều replay WAL nhưng có mục đích và điểm bắt đầu khác nhau.

### 14.1. Crash recovery

Mục tiêu là khôi phục cluster sau crash tới trạng thái WAL cuối cùng hợp lệ mà data directory có thể sử dụng. PostgreSQL bắt đầu từ redo point trong checkpoint/control file hiện tại.

```text
Data directory hiện tại
       |
       v
Checkpoint state / redo LSN
       |
       v
Replay WAL còn sẵn tới điểm cuối hợp lệ
       |
       v
Mở database sau recovery
```

### 14.2. Archive recovery

Archive recovery sử dụng base backup và các WAL segments được lưu trong archive để tiếp tục replay. Nó có thể được dùng để dựng một cluster từ backup hoặc đưa cluster tới một recovery target cụ thể.

### 14.3. Point-in-Time Recovery (PITR)

PITR cho phép dừng recovery tại một thời điểm hoặc LSN trước một lỗi logic, ví dụ người dùng vô tình DROP TABLE. Cần:

- Base backup hợp lệ.
- WAL liên tục từ checkpoint/redo point của base backup tới target.
- Timeline và archive chain đúng.
- Recovery configuration đúng.

PITR không thể tạo dữ liệu chưa từng được backup hoặc WAL chưa từng được ghi/archived.

### 14.4. Checkpoint hiện tại không rút ngắn PITR từ base backup cũ

Khi restore từ một base backup, recovery phải bắt đầu từ điểm redo mà backup yêu cầu và replay WAL liên tục tới target. Checkpoint mới trên primary sau thời điểm backup không cho phép bỏ qua các WAL records cần thiết từ base backup.

Vì vậy:

- Checkpoint frequency tác động trực tiếp tới crash recovery của data directory đang chạy.
- Base backup frequency và WAL archive continuity tác động mạnh tới PITR recovery distance.
- Restartpoints giúp standby lưu tiến độ recovery trong quá trình replay.

### 14.5. Timeline

Sau promote/failover hoặc PITR, PostgreSQL có thể tạo timeline mới. Timeline history mô tả quan hệ phân nhánh giữa các dòng WAL. Khi recovery, phải chọn đúng timeline; không nối WAL từ hai nhánh khác nhau một cách tùy ý.

### 14.6. recovery.signal và standby.signal

Trong PostgreSQL 12+, recovery settings được cấu hình trong file cấu hình thông thường, và signal files xác định chế độ:

- `recovery.signal`: khởi động vào archive recovery/PITR.
- `standby.signal`: khởi động như standby và tiếp tục streaming/archive recovery theo cấu hình.

Các signal files là file rỗng dùng để báo chế độ startup; không phải nội dung cấu hình WAL. Xem tài liệu major tương ứng khi triển khai.

### 14.7. Một số recovery settings

Ví dụ các tham số trong cấu hình:

```conf
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Đây là ví dụ cấu hình khái niệm. `restore_command` phải phù hợp môi trường archive và xử lý tên file an toàn. Thời điểm target phải ở đúng timezone/format; không copy cấu hình vào production mà chưa thử restore trên cluster độc lập.

### 14.8. Recovery target

PostgreSQL hỗ trợ nhiều cách chọn target, tùy phiên bản:

- `recovery_target_time`: thời điểm.
- `recovery_target_lsn`: LSN.
- `recovery_target_xid`: transaction ID.
- `recovery_target_name`: named restore point.
- `recovery_target_inclusive`: có dừng ngay tại target hay sau target theo semantics của target.
- `recovery_target_action`: pause, promote hoặc shutdown.

Không dùng target time để thay thế kiểm tra transaction cụ thể nếu cần độ chính xác cao. Hãy tạo restore point trước thay đổi rủi ro hoặc lưu LSN/correlation data trong quy trình release.

### 14.9. recovery_target_action

`pause` cho phép kiểm tra database tại target trước khi tiếp tục/promote theo runbook. `promote` chuyển recovery instance thành primary mới. `shutdown` dừng server khi đạt target. Chọn theo kế hoạch phục hồi, không để hệ thống tự promote nhầm môi trường.

### 14.10. Archive không phải chỉ là copy file mới nhất

PITR cần **chuỗi WAL liên tục** bắt đầu từ base backup. Một archive thiếu một segment ở giữa có thể làm recovery không thể tiến tới target dù có những segment mới hơn. Kiểm tra archive integrity và test restore định kỳ.

## 15. RTO, RPO và recovery time

Checkpoint là một yếu tố trong RTO, nhưng không quyết định toàn bộ thời gian phục hồi.

### 15.1. RTO — Recovery Time Objective

**RTO** là khoảng thời gian tối đa nghiệp vụ chấp nhận hệ thống không phục vụ sau sự cố. Ví dụ RTO 15 phút có nghĩa đội vận hành cần khôi phục dịch vụ trong 15 phút theo định nghĩa đo đã thống nhất.

### 15.2. RPO — Recovery Point Objective

**RPO** là lượng dữ liệu tối đa nghiệp vụ chấp nhận mất, thường được biểu diễn bằng thời gian trước sự cố. Ví dụ RPO 1 phút cho phép mất tối đa khoảng một phút dữ liệu theo mô hình backup/replication/durability đã chọn.

Checkpoint **không phải RPO boundary**. RPO phụ thuộc:

- WAL có được flush bền vững trước khi COMMIT xác nhận không.
- `synchronous_commit` và replication synchronous/asynchronous.
- Archive WAL có liên tục và được chuyển ra storage an toàn không.
- Base backup và WAL retention có đáp ứng PITR không.
- Failover có thể mất những WAL chưa replicate tới standby không.

### 15.3. Các thành phần của recovery time

```text
Tổng thời gian khôi phục dịch vụ
  =
  phát hiện + quyết định failover/restore
  + khởi động PostgreSQL
  + WAL redo/replay
  + kiểm tra consistency và nghiệp vụ
  + định tuyến traffic / mở dịch vụ
```

Với PITR, cần cộng thời gian lấy/restore base backup và replay WAL archive từ backup tới recovery target. Với standby failover, thời gian phát hiện/promote và catch-up có thể là phần lớn.

### 15.4. Ước lượng redo time sơ bộ

Một ước lượng thô:

\[
T_{\text{redo}} \approx
\frac{\text{WAL bytes cần replay}}
{\text{effective replay throughput}}
\]

Ví dụ nếu phải replay 12 GB WAL và môi trường thực tế replay hiệu quả 120 MB/s, phép chia đơn giản cho kết quả khoảng 100 giây. Đây chỉ là ước lượng ban đầu, không bao gồm startup, data-page reads/writes, random I/O, CPU, decompression, fsync và kiểm tra sau recovery.

### 15.5. WAL bytes không phải chỉ số duy nhất

Hai database có cùng 10 GB WAL cần replay có thể recovery time khác nhau vì:

- WAL records mô tả loại thao tác khác nhau.
- Một workload có nhiều full-page images.
- Data pages cần đọc/ghi nằm rải rác hay có locality tốt.
- Storage có throughput/latency khác nhau.
- Cache nóng/lạnh khác nhau.
- CPU và memory khác nhau.
- Archive/restore source có tốc độ khác nhau.

### 15.6. Checkpoint gần hơn có thể giảm redo, nhưng không bảo đảm RTO

Giảm redo distance có thể giảm một thành phần recovery time. Nếu bottleneck là restore backup, archive fetch, startup checks, filesystem hoặc application warm-up, điều chỉnh checkpoint không giải quyết toàn bộ RTO.

### 15.7. Recovery time cần được đo thực nghiệm

Không suy luận RTO từ `max_wal_size` hoặc `checkpoint_timeout`. Hãy mô phỏng crash/restore trên môi trường tương tự production, đo thời gian từ detection tới khi ứng dụng xử lý request thành công.

## 16. Lab 1: quan sát checkpoint và redo point

Lab này chạy trên database thực hành, dưới role có quyền đọc control checkpoint information và thực hiện `CHECKPOINT`. Không chạy lệnh checkpoint liên tục trên production.

### 16.1. Kiểm tra phiên bản và quyền

```sql
SELECT version();
SHOW server_version_num;
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
```

Đảm bảo role có quyền cần thiết để gọi `CHECKPOINT` và đọc `pg_control_checkpoint()`. Nếu bị permission denied, dùng tài khoản DBA trong lab theo quy trình quản trị.

### 16.2. Ghi nhận checkpoint state trước

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

Ghi lại các giá trị và thời điểm lấy snapshot.

### 16.3. Ghi nhận WAL LSN hiện tại

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file;
```

### 16.4. Tạo checkpoint thủ công

```sql
CHECKPOINT;
```

Đây là lệnh quản trị có thể gây I/O. Chỉ chạy một lần trong lab.

### 16.5. Đọc lại checkpoint state

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

Checkpoint LSN mới thường khác trước; redo LSN có thể tiến. Giá trị cụ thể phụ thuộc WAL/workload và thời điểm snapshot.

### 16.6. So sánh byte distance

```sql
SELECT
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        (SELECT redo_lsn FROM pg_control_checkpoint())
    ) AS bytes_from_redo;
```

Đây là phép đo snapshot. WAL vẫn có thể tăng giữa các câu SQL; không kỳ vọng kết quả đứng yên.

### 16.7. Đọc thống kê checkpoint theo major

PostgreSQL 17+:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

PostgreSQL 16 trở xuống:

```sql
SELECT *
FROM pg_stat_bgwriter;
```

Không yêu cầu các cột hai view giống nhau. Xem đúng version documentation và ghi lại stats_reset.

## 17. Lab 2: tạo workload WAL và quan sát checkpoint request

Thử nghiệm trên database riêng, với bảng tạm hoặc bảng lab:

### 17.1. Tạo bảng ghi nhiều rows

```sql
CREATE TABLE IF NOT EXISTS public.checkpoint_lab (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

### 17.2. Chèn dữ liệu để tạo WAL

```sql
INSERT INTO public.checkpoint_lab(payload)
SELECT repeat(md5(g::text), 8)
FROM generate_series(1, 100000) AS g;
```

Khối dữ liệu này tạo heap/index writes và WAL. Dung lượng thực tế tùy compression, schema và cấu hình.

### 17.3. Update cùng một tập pages

```sql
UPDATE public.checkpoint_lab
SET
    payload = payload || 'x',
    updated_at = clock_timestamp()
WHERE id BETWEEN 1 AND 50000;
```

Lệnh tạo thêm WAL và dirty pages. Lặp lại có kiểm soát trong lab nếu cần tạo workload lớn hơn.

### 17.4. Quan sát WAL bytes

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full
FROM pg_stat_wal;
```

Lấy hai snapshots cách nhau một khoảng thời gian và tính delta. Các counters là tích lũy, nên phải biết thời điểm stats reset.

### 17.5. Quan sát checkpoint counters/logs

Nếu `log_checkpoints=on`, xem server log để biết checkpoint được kích hoạt bởi timeout hay request và thời gian write/sync. So sánh với stats checkpoint view.

### 17.6. Dọn lab

```sql
DROP TABLE public.checkpoint_lab;
```

Chỉ chạy nếu bảng được tạo riêng cho lab và không chứa dữ liệu khác.

## 18. Lab 3: quan sát crash recovery trong cluster dùng riêng

Đây là lab **có chủ ý làm PostgreSQL shutdown không sạch**. Tuyệt đối không chạy trên cluster production, shared development hoặc data directory chứa dữ liệu cần giữ.

### 18.1. Tạo cluster disposable

Trên máy đã cài PostgreSQL, tạo data directory lab mới bằng `initdb` và chạy instance trên port riêng. Ví dụ shell minh họa:

```bash
initdb -D /tmp/pg-checkpoint-lab
pg_ctl -D /tmp/pg-checkpoint-lab -o "-p 5544" -l /tmp/pg-checkpoint-lab.log start
```

Trên Windows, dùng đường dẫn riêng phù hợp và đảm bảo service không trùng port/data directory. Không trỏ `PGDATA` tới cluster thật.

### 18.2. Tạo bảng và COMMIT dữ liệu

Kết nối tới port lab:

```sql
CREATE TABLE public.crash_lab (
    id integer PRIMARY KEY,
    value text NOT NULL
);

INSERT INTO public.crash_lab
VALUES (1, 'committed-before-crash');

CHECKPOINT;
```

Ghi nhận rằng row đã được COMMIT và checkpoint được yêu cầu trước khi tạo thêm workload.

### 18.3. Tạo thay đổi đã COMMIT sau checkpoint

```sql
INSERT INTO public.crash_lab
VALUES (2, 'committed-after-checkpoint');

UPDATE public.crash_lab
SET value = 'updated-after-checkpoint'
WHERE id = 1;
```

Không gọi CHECKPOINT sau hai thay đổi này. WAL chứa thông tin cần để phục hồi.

### 18.4. Shutdown immediate trong cluster lab

Từ terminal của cluster lab:

```bash
pg_ctl -D /tmp/pg-checkpoint-lab stop -m immediate
```

`immediate` mô phỏng shutdown không sạch bằng cách dừng server mà không chờ checkpoint thông thường. Đây là thao tác phá vỡ shutdown bình thường; chỉ làm trên disposable cluster.

### 18.5. Start lại và xem recovery log

```bash
pg_ctl -D /tmp/pg-checkpoint-lab -o "-p 5544" -l /tmp/pg-checkpoint-lab.log start
```

Server log có thể ghi nhận database system was interrupted và quá trình redo/recovery. Nội dung cụ thể phụ thuộc PostgreSQL major và WAL workload.

### 18.6. Xác minh dữ liệu

```sql
SELECT *
FROM public.crash_lab
ORDER BY id;
```

Hai thay đổi đã COMMIT trước crash phải hiện diện sau crash recovery nếu storage/durability settings đáp ứng giả định. Không kỳ vọng transaction chưa commit được coi là thành công.

### 18.7. Tắt và xóa cluster lab

Sau khi hoàn tất, shutdown bình thường và chỉ xóa data directory lab đã tạo. Xác minh đường dẫn là đúng thư mục disposable trước khi xóa.

### 18.8. Giới hạn của lab

`pg_ctl stop -m immediate` mô phỏng shutdown không sạch, nhưng không tái hiện mọi dạng power loss, controller cache failure, torn writes hoặc storage corruption. Để xác nhận RTO/RPO thật, cần thử nghiệm trên hạ tầng tương tự production và kiểm tra durability hardware.

## 19. Lab 4: đo recovery time và xây dựng baseline

### 19.1. Xác định mốc bắt đầu/kết thúc

Ghi:

- Thời điểm bắt đầu sự cố (hoặc bắt đầu recovery).
- Thời điểm PostgreSQL báo recovery complete/ready.
- Thời điểm ứng dụng kết nối được.
- Thời điểm một transaction kiểm tra nghiệp vụ thành công.
- Thời điểm toàn bộ traffic được mở lại.

Định nghĩa RTO theo mốc cuối cùng có ý nghĩa nghiệp vụ, không chỉ theo thời điểm process PostgreSQL sống.

### 19.2. Thu thập redo distance trước thử nghiệm

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    pg_current_wal_lsn() AS current_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        redo_lsn
    ) AS redo_bytes;
```

Lưu kết quả cùng workload rate, WAL segment size, storage metrics và cấu hình checkpoint.

### 19.3. Thực hiện recovery test

Khôi phục bản sao lab từ base backup hoặc dùng disposable cluster để tạo crash theo quy trình. Không làm hỏng primary đang phục vụ chỉ để đo một chỉ số.

### 19.4. Ghi kết quả

| Lần thử | Redo bytes | WAL replay throughput | Server ready | App ready | Ghi chú |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | Ghi số đo | Ghi số đo | Ghi thời gian | Ghi thời gian | Storage/cache |
| 2 | Ghi số đo | Ghi số đo | Ghi thời gian | Ghi thời gian | Workload khác |
| 3 | Ghi số đo | Ghi số đo | Ghi thời gian | Ghi thời gian | Archive/restore |

Không điền số giả định thành kết quả thực. Mục tiêu là xây baseline có thể lặp lại.

### 19.5. Thay đổi từng tham số

Thử một thay đổi mỗi lần (ví dụ `max_wal_size` hoặc `checkpoint_timeout`), giữ workload và storage tương đương, rồi đo:

- Checkpoint frequency và requested checkpoints.
- WAL bytes/FPI.
- Query latency khi checkpoint chạy.
- Redo distance tại các thời điểm đại diện.
- Recovery time thực nghiệm.

### 19.6. So sánh cả steady-state và recovery

Một cấu hình có thể làm recovery nhanh hơn nhưng tăng latency bình thường hoặc tăng WAL/disk. Cần xem cả:

- p95/p99 write latency.
- Throughput.
- Checkpoint write/sync time.
- WAL generation và archive lag.
- Recovery RTO.
- Storage capacity.

### 19.7. Đừng dùng CHECKPOINT để “làm sạch” phép đo production

Nếu muốn đo crash recovery, hãy tạo checkpoint trong disposable test cluster ở thời điểm được kiểm soát. Chạy CHECKPOINT ngay trước khi restart production làm thay đổi state và I/O, khiến phép đo không còn đại diện cho sự cố tự nhiên.

## 20. Quy trình tuning checkpoint có kiểm soát

Đừng bắt đầu bằng cách tăng mọi tham số. Hãy tìm đúng bottleneck và giữ một baseline để so sánh.

### 20.1. Bước 1 — Xác định mục tiêu

Ghi rõ:

- RTO cần đạt cho crash recovery.
- Throughput và p95/p99 latency của workload bình thường.
- WAL generation trung bình và peak.
- Dung lượng filesystem cho `pg_wal`, archive và backups.
- Replication lag và slot retention.
- Storage write throughput/latency.

### 20.2. Bước 2 — Thu thập baseline

Trong một khoảng thời gian đại diện, lấy snapshots:

- `pg_stat_checkpointer` (PG17+) hoặc checkpoint counters trong `pg_stat_bgwriter` (PG16 trở xuống).
- `pg_stat_wal`.
- `pg_replication_slots`.
- `pg_stat_archiver`.
- `pg_stat_replication` trên primary và `pg_stat_wal_receiver` trên standby khi phù hợp.
- OS/storage metrics và query latency.

Tính delta theo thời gian thay vì đọc một giá trị tích lũy đơn lẻ.

### 20.3. Bước 3 — Phân biệt checkpoint pressure với retention pressure

Nếu `num_requested`/`checkpoints_req` tăng nhiều, có thể WAL threshold đang kích hoạt checkpoint thường xuyên.

Nếu `pg_wal` tăng dù checkpoint chạy đều, kiểm tra archive failure, replication slot, standby lag và WAL retention. Tăng checkpoint frequency không giải quyết được một slot giữ WAL cũ.

### 20.4. Bước 4 — Chỉ thay đổi một nhóm tham số liên quan

Ví dụ:

- Checkpoints quá thường xuyên do WAL threshold: đánh giá tăng `max_wal_size`.
- Checkpoints quá thường xuyên do thời gian: đánh giá `checkpoint_timeout`.
- I/O spikes trong checkpoint: xem `checkpoint_completion_target` và storage throughput.
- WAL bytes tăng do FPI: xem checkpoint interval, `full_page_writes` và `wal_compression`.

Không thay đổi `full_page_writes` như bước tối ưu đầu tiên.

### 20.5. Bước 5 — Kiểm tra context và reload/restart

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'wal_buffers',
    'full_page_writes'
)
ORDER BY name;
```

`context` cho biết thay đổi có cần restart hay chỉ reload. `pending_restart` cho biết giá trị đã được yêu cầu nhưng chưa có hiệu lực vì cần restart.

### 20.6. Bước 6 — Áp dụng có kế hoạch

Trong lab hoặc change window, có thể chỉnh file cấu hình:

```conf
# Giá trị minh họa, không phải khuyến nghị cho mọi workload:
checkpoint_timeout = '10min'
max_wal_size = '4GB'
checkpoint_completion_target = 0.9
log_checkpoints = on
```

Sau khi sửa, reload nếu tham số cho phép:

```sql
SELECT pg_reload_conf();
```

Xác minh lại `pg_settings` và log. Tham số cần restart sẽ vẫn có `pending_restart=true` cho tới khi restart.

### 20.7. Bước 7 — Đo lại steady-state

So sánh checkpoint count, write/sync time, WAL/FPI bytes, query latency, disk growth và replication/archive lag. Một cấu hình giảm checkpoint count nhưng tạo checkpoint dài hoặc disk pressure cao có thể không tốt hơn.

### 20.8. Bước 8 — Chạy recovery test

Tạo crash recovery test hoặc restore test trên môi trường tương tự production. Đo RTO thực tế và kiểm tra dữ liệu đã COMMIT, dữ liệu chưa COMMIT và ứng dụng sau recovery.

### 20.9. Bước 9 — Ghi lại và có rollback plan

Lưu cấu hình trước/sau, workload profile, thời gian thử nghiệm, WAL bytes, checkpoint metrics và recovery duration. Nếu latency hoặc disk usage xấu đi, khôi phục cấu hình đã biết tốt và tiếp tục điều tra.

## 21. Những khái niệm dễ nhầm

### 21.1. CHECKPOINT và pg_switch_wal

`CHECKPOINT` yêu cầu checkpoint, ghi dirty data pages và tạo checkpoint state.

`pg_switch_wal()` yêu cầu chuyển sang WAL segment mới (khi điều kiện cho phép), thường hữu ích để archive segment hiện tại sớm hơn. Nó **không phải checkpoint** và không buộc mọi dirty data pages được ghi xuống disk.

```sql
SELECT pg_switch_wal();
```

Không gọi `pg_switch_wal()` liên tục để “giải phóng pg_wal”; archive/replication/slot retention vẫn có thể giữ các segments cũ.

### 21.2. Checkpoint LSN và current WAL LSN

`pg_current_wal_lsn()` là vị trí WAL hiện tại trên primary. `checkpoint_lsn` là vị trí checkpoint record được lưu trong control state. `redo_lsn` là vị trí recovery phải bắt đầu. Ba giá trị trả lời ba câu hỏi khác nhau.

### 21.3. Checkpoint và COMMIT

COMMIT cần durability của WAL theo `synchronous_commit`; nó không cần chờ toàn bộ data pages được checkpoint. Checkpoint giúp quản lý dirty pages và recovery start point.

### 21.4. Checkpoint và backup

Checkpoint không phải backup. Base backup cần một bản sao data files nhất quán cùng WAL cần thiết; archive WAL liên tục cho phép PITR. Chạy CHECKPOINT không tạo một bản sao có thể restore độc lập.

### 21.5. Checkpoint và replication

Primary checkpoint không có nghĩa standby đã replay tới LSN đó. Standby có receive LSN, replay LSN và restartpoint state riêng. Network/replay lag vẫn có thể tồn tại.

### 21.6. max_wal_size và pg_wal disk usage

`max_wal_size` là ngưỡng checkpoint soft target, không phải quota filesystem. Archive failure/slots/standby có thể làm `pg_wal` vượt ngưỡng. Đặt max_wal_size thấp không phải cách an toàn để giới hạn disk nếu retention blockers tồn tại.

### 21.7. Crash recovery và PITR

Crash recovery đưa data directory hiện tại về trạng thái nhất quán sau crash. PITR khôi phục từ base backup và replay WAL tới target. Checkpoint hiện tại của primary không thể thay thế WAL liên tục từ base backup.

### 21.8. Restartpoint và checkpoint

Checkpoint do primary thực hiện; restartpoint là hoạt động tương ứng trên standby trong recovery, bị ràng buộc bởi checkpoint records nhận từ primary.

## 22. Troubleshooting khi checkpoint hoặc recovery có vấn đề

### 22.1. Checkpoint requested xảy ra quá thường xuyên

Nguyên nhân có thể:

- `max_wal_size` quá thấp so với WAL generation.
- Workload bulk load/update tạo WAL burst.
- Checkpoint interval không phù hợp với tốc độ ghi.

Hướng xử lý:

1. Đo WAL bytes/sec và checkpoint counters.
2. Xác định checkpoint do timeout hay WAL threshold.
3. Xem disk capacity, archive và replication retention.
4. Thử tăng max_wal_size trong môi trường kiểm soát.
5. Đo lại I/O và recovery time.

### 22.2. Checkpoint write time cao

Kiểm tra storage write throughput, queue depth, latency, checkpoint buffers written và checkpoint_completion_target. Nếu storage không theo kịp workload, chỉ tăng timeout có thể làm redo distance dài hơn mà không giải quyết bottleneck.

### 22.3. Checkpoint sync time cao

Sync time cao có thể liên quan fsync latency, filesystem, controller cache, virtualized storage hoặc nhiều file cần sync. Kiểm tra OS/storage metrics và durability configuration; không tắt fsync để che triệu chứng.

### 22.4. Query latency tăng theo chu kỳ

Nếu spikes trùng checkpoint logs, xem checkpoint writes có dồn quá nhanh không. Kiểm tra `checkpoint_completion_target`, dirty page rate, background writer và khả năng storage. Không mặc định mọi latency spike đều do checkpoint; xem query plan, lock waits, CPU và I/O.

### 22.5. pg_wal tăng không ngừng

Kiểm tra:

- Archive command/library có lỗi hoặc backlog không.
- Replication slot nào inactive/lagging.
- Standby có dừng replay/receive không.
- `restart_lsn` cũ nhất là gì.
- Filesystem còn bao nhiêu dung lượng.

Không xóa WAL segments bằng tay. Nếu slot không còn cần, đánh giá chính sách và drop slot đúng quy trình; nếu standby cần slot, khôi phục standby hoặc reinitialize theo kế hoạch.

### 22.6. Recovery mất nhiều thời gian

Thu thập redo distance, WAL replay rate, log recovery, I/O latency, CPU, cache state và loại workload. Kiểm tra checkpoint age, WAL archive fetch, base backup age nếu PITR. Tăng checkpoint frequency chỉ có ích khi redo distance là bottleneck chính.

### 22.7. Recovery dừng vì thiếu WAL

Kiểm tra segment name, timeline history, archive status, base backup checkpoint/backup_label và WAL continuity. Không trộn segment của timeline khác hoặc tạo file rỗng giả để vượt lỗi.

### 22.8. Database crash loop

Đọc log từ lần startup đầu tiên và error gốc, kiểm tra control file/data directory/storage, WAL segment và filesystem. Không xóa `postmaster.pid` hoặc thay control file trước khi xác định server process cũ có còn chạy không và dữ liệu thuộc cluster nào.

### 22.9. Standby restartpoint không tiến

Kiểm tra standby có nhận checkpoint records mới không, replay có bị lag, storage có ghi được không và WAL retention constraints. Một standby dừng replay sẽ không tạo restartpoint tiến triển bình thường.

### 22.10. Checkpoint logs quá nhiều

Log checkpoint giúp điều tra nhưng tạo log volume. Chọn retention/rotation phù hợp, ship logs tập trung và giữ thông tin đủ để phân tích checkpoint timing; không tắt logging khi cần chẩn đoán chỉ vì log tăng mà chưa xem nguyên nhân.

## 23. Best practices cho production

1. Giữ `full_page_writes=on` trừ khi có cơ sở kỹ thuật được kiểm chứng.
2. Đặt `max_wal_size` theo WAL generation và disk capacity, không theo cảm tính.
3. Dùng `checkpoint_completion_target` để làm mượt checkpoint I/O.
4. Theo dõi requested checkpoints, write/sync time và FPI/WAL bytes.
5. Theo dõi archive backlog và replication slot retention riêng với checkpoint.
6. Không chạy `CHECKPOINT` định kỳ quá dày trong application.
7. Không tự xóa hoặc sửa file trong `pg_wal`.
8. Không coi checkpoint là backup hoặc PITR capability.
9. Test crash recovery trên disposable cluster.
10. Test PITR từ base backup và WAL archive định kỳ.
11. Đo RTO từ phát hiện sự cố tới khi ứng dụng phục vụ lại.
12. Xác định RPO dựa trên WAL durability, archive và replication policy.
13. Ghi lại PostgreSQL major/version và cấu hình trước khi so sánh metrics.
14. Giữ đủ disk headroom cho WAL bursts, archive backlog và replication lag.
15. Có runbook xử lý slot/archive backlog trước khi filesystem đầy.
16. Không tắt fsync hoặc durability safeguards để giảm thời gian checkpoint.
17. Khi failover, xác định timeline và trạng thái standby trước khi mở traffic.
18. Thực hiện thay đổi checkpoint theo từng bước và có rollback plan.

## 24. Bài tập thực hành

Các bài tập dưới đây dùng một PostgreSQL lab riêng. Một số câu hỏi yêu cầu đọc output thực tế; không điền số liệu giả định vào báo cáo. Những bài mô phỏng crash/recovery phải dùng cluster disposable, không chạy trên production.

### Bài 1. WAL rule

Giải thích vì sao PostgreSQL phải ghi WAL bền vững trước khi ghi data page chứa thay đổi tương ứng xuống disk.

### Bài 2. LSN

LSN là gì? Vì sao khoảng cách 10 MB giữa hai LSN không tự động tương đương 10 giây?

### Bài 3. Phân biệt ba vị trí

Phân biệt `pg_current_wal_lsn()`, `checkpoint_lsn` và `redo_lsn`.

### Bài 4. Checkpoint record

Checkpoint record và redo pointer có nhất thiết ở cùng một LSN không? Giải thích.

### Bài 5. Dirty page

Một page đang dirty trong shared_buffers nhưng WAL tương ứng đã flush. Nếu server crash trước khi page được ghi xuống disk, PostgreSQL phục hồi thế nào?

### Bài 6. Checkpoint và COMMIT

Một transaction đã nhận COMMIT thành công nhưng data page chưa được checkpoint. Dữ liệu có mất chỉ vì chưa checkpoint không? Nêu điều kiện durability liên quan.

### Bài 7. Checkpoint trigger

Liệt kê ít nhất ba nguyên nhân có thể kích hoạt checkpoint tự động/thủ công.

### Bài 8. max_wal_size

Vì sao `max_wal_size='2GB'` không đảm bảo `pg_wal` không bao giờ lớn hơn 2 GB?

### Bài 9. checkpoint_timeout

Tăng `checkpoint_timeout` có thể ảnh hưởng redo distance và I/O như thế nào?

### Bài 10. checkpoint_completion_target

Tham số này làm gì? Nó có làm giảm tổng số dirty pages cần ghi không?

### Bài 11. Checkpoint dày

Nêu hai lợi ích và ba chi phí có thể xảy ra khi checkpoint quá thường xuyên.

### Bài 12. Checkpoint thưa

Nêu hai lợi ích và ba rủi ro có thể xảy ra khi checkpoint quá thưa.

### Bài 13. Full-page image

Vì sao `full_page_writes` ghi FPI ở lần sửa đầu tiên của page sau checkpoint? FPI giúp gì khi torn page?

### Bài 14. WAL compression

`wal_compression` có thể giảm phần WAL nào và đánh đổi tài nguyên gì?

### Bài 15. Checkpoint LSN và redo LSN

Một output cho thấy checkpoint LSN là `0/9000100` và redo LSN là `0/8F00000`. Giá trị nào được dùng làm điểm bắt đầu crash recovery? Vì sao?

### Bài 16. pg_control_checkpoint

Viết SQL lấy checkpoint_lsn, redo_lsn, redo_wal_file và timeline_id.

### Bài 17. pg_controldata

Nêu các thông tin checkpoint nào có thể đọc bằng `pg_controldata` và vì sao phải chọn đúng data directory.

### Bài 18. Thống kê major mới

Trong PostgreSQL 17+, view nào chứa checkpoint statistics? Nêu ít nhất bốn trường hữu ích.

### Bài 19. Thống kê major cũ

Trong PostgreSQL 16 trở xuống, view nào chứa checkpoint counters? Nêu hai counters phân biệt timed/requested.

### Bài 20. WAL statistics

Viết SQL đọc `wal_records`, `wal_fpi` và `wal_bytes`.

### Bài 21. Archive backlog

Archive command thất bại liên tục. Vì sao checkpoint không được phép xóa mọi WAL segments cũ cần archive?

### Bài 22. Replication slot

Một replication slot inactive giữ restart_lsn rất cũ. Điều gì có thể xảy ra với dung lượng `pg_wal`? Cần xử lý thế nào?

### Bài 23. Restartpoint

Restartpoint khác checkpoint ở điểm nào? Vì sao standby không thể tạo restartpoint tùy ý tại bất kỳ LSN nào?

### Bài 24. Crash recovery và PITR

Phân biệt điểm bắt đầu recovery của data directory hiện tại sau crash với recovery từ một base backup cũ.

### Bài 25. RTO/RPO

Checkpoint tác động tới RTO như thế nào? Nó có xác định RPO không? Giải thích.

### Bài 26. Ước lượng recovery

Một hệ thống cần replay 24 GB WAL, replay throughput đo được là 200 MB/s. Ước lượng thời gian redo thuần theo phép chia đơn giản và nêu ít nhất bốn yếu tố chưa tính.

### Bài 27. CHECKPOINT và pg_switch_wal

Hai lệnh này khác nhau thế nào? Lệnh nào ghi dirty data pages?

### Bài 28. Thí nghiệm crash

Nêu quy trình dùng cluster disposable để mô phỏng shutdown không sạch và xác minh dữ liệu đã COMMIT sau recovery.

### Bài 29. Tuning

Metrics cho thấy requested checkpoints tăng nhanh, write latency tăng khi checkpoint và archive backlog bằng 0. Đề xuất thứ tự điều tra/thử thay đổi.

### Bài 30. Thiết kế recovery plan

Một SaaS yêu cầu RTO 10 phút và RPO 1 phút. Đề xuất vai trò của checkpoint, WAL archiving, base backup, standby replication, monitoring và recovery drills. Nêu giới hạn không thể giải quyết chỉ bằng checkpoint.

## 25. Gợi ý lời giải bài tập

### Đáp án 1. WAL rule

Nếu data page được ghi xuống disk trước WAL tương ứng, crash có thể để lại page chứa thay đổi mà WAL không đủ để phục hồi/kiểm chứng. Ghi WAL trước đảm bảo PostgreSQL có nhật ký bền vững để redo nếu page write bị thiếu hoặc torn.

### Đáp án 2. LSN

LSN là vị trí byte trong WAL stream. Khoảng cách byte không biểu diễn thời gian cố định vì WAL generation rate thay đổi theo workload; 10 MB có thể được sinh trong vài mili giây hoặc nhiều phút.

### Đáp án 3. Ba vị trí

- `pg_current_wal_lsn()`: vị trí WAL hiện tại trên primary.
- `checkpoint_lsn`: vị trí checkpoint record mà control state tham chiếu.
- `redo_lsn`: vị trí WAL mà crash recovery phải bắt đầu replay.

Không dùng ba giá trị thay thế nhau.

### Đáp án 4. Checkpoint record

Không. Checkpoint record nằm ở vị trí WAL ghi nhận checkpoint; redo pointer là vị trí cần bắt đầu replay. Redo LSN thường ở trước checkpoint record vì các thay đổi kể từ checkpoint trước đó có thể cần redo.

### Đáp án 5. Dirty page

Sau crash, PostgreSQL đọc WAL từ redo point. Nếu page trên disk chưa phản ánh record, redo áp dụng thay đổi; nếu page đã có LSN đủ mới, recovery có thể bỏ qua record tương ứng. WAL-before-data bảo đảm dữ liệu cần thiết có sẵn.

### Đáp án 6. COMMIT chưa checkpoint

Không mất chỉ vì data page chưa checkpoint, miễn WAL của transaction đã được flush theo durability settings và storage thực hiện đúng giả định durability. Khi restart, WAL replay tái tạo thay đổi. `synchronous_commit` và replication durability có thể ảnh hưởng thời điểm server xác nhận COMMIT.

### Đáp án 7. Checkpoint trigger

Ví dụ: `checkpoint_timeout`, WAL vượt mục tiêu `max_wal_size`, lệnh SQL `CHECKPOINT`, và shutdown bình thường/fast.

### Đáp án 8. max_wal_size

Đây là soft target, không phải quota. Archive backlog, replication slots, standby lag và retention requirements có thể giữ WAL cũ; workload burst cũng có thể khiến kích thước vượt ngưỡng.

### Đáp án 9. checkpoint_timeout

Tăng timeout thường giảm checkpoint do thời gian, có thể giảm I/O/checkpoint frequency nhưng redo point có thể xa hơn, crash recovery replay nhiều WAL hơn. Checkpoint thưa cũng có thể thay đổi lượng FPI/WAL.

### Đáp án 10. checkpoint_completion_target

Nó trải checkpoint writes trên một phần khoảng thời gian giữa các checkpoints để giảm burst. Nó không làm tổng dirty pages cần ghi biến mất; chủ yếu điều chỉnh tốc độ phân bố I/O.

### Đáp án 11. Checkpoint dày

Lợi ích: redo distance có thể ngắn hơn; crash recovery có thể replay ít WAL hơn. Chi phí: nhiều checkpoint writes, I/O/latency spikes, nhiều FPI/WAL hơn và storage wear/throughput pressure tùy hệ thống.

### Đáp án 12. Checkpoint thưa

Lợi ích: giảm tần suất checkpoint và có thể giảm FPI lặp lại. Rủi ro: redo distance dài, recovery lâu hơn, WAL giữ lâu hơn, và checkpoint khi chạy có thể phải xử lý nhiều dirty pages hơn.

### Đáp án 13. FPI

FPI ghi ảnh toàn page ở lần thay đổi đầu tiên sau checkpoint để recovery có thể khôi phục page nếu crash gây torn write. Sau khi phục hồi ảnh page, các WAL records tiếp theo được replay.

### Đáp án 14. WAL compression

`wal_compression` nén full-page images để giảm WAL bytes/disk/network/archive, đổi lại dùng CPU để nén/giải nén. Nó không nén mọi WAL record.

### Đáp án 15. Redo LSN

`0/8F00000` là redo LSN nên là điểm bắt đầu crash recovery. `0/9000100` là checkpoint record LSN. Redo point không bằng vị trí checkpoint record.

### Đáp án 16. pg_control_checkpoint

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id
FROM pg_control_checkpoint();
```

### Đáp án 17. pg_controldata

Có thể đọc latest checkpoint location, REDO location, REDO WAL file, timeline IDs, full_page_writes và các control metadata khác. Chọn đúng data directory vì mỗi cluster có control file/system identifier/checkpoint state riêng; đọc nhầm cluster dẫn đến kết luận sai.

### Đáp án 18. PG17+

View `pg_stat_checkpointer`. Trường hữu ích: `num_timed`, `num_requested`, `write_time`, `sync_time`, `buffers_written`, `restartpoints_done` và `stats_reset`.

### Đáp án 19. PG16 trở xuống

View `pg_stat_bgwriter`. Hai counters phân biệt: `checkpoints_timed` và `checkpoints_req`. Các cột khác gồm checkpoint write/sync time và buffers checkpoint.

### Đáp án 20. WAL statistics

```sql
SELECT wal_records, wal_fpi, wal_bytes
FROM pg_stat_wal;
```

### Đáp án 21. Archive backlog

WAL segments chưa archive thành công có thể cần cho PITR/standby. Xóa chúng sẽ làm đứt chuỗi WAL và mất khả năng phục hồi. PostgreSQL giữ lại để archive thử lại; vận hành phải sửa archive destination/command.

### Đáp án 22. Replication slot

Slot inactive có thể giữ WAL từ restart_lsn cũ, khiến `pg_wal` tăng và filesystem đầy. Xác định slot còn cần không; khôi phục consumer/standby, hoặc drop slot theo change plan nếu không còn cần. Không xóa file WAL thủ công.

### Đáp án 23. Restartpoint

Restartpoint là checkpoint-like operation trên standby trong recovery, giúp lưu tiến độ replay. Nó chỉ có thể hoàn tất tại checkpoint record nhận từ primary nên không thể tạo tùy ý tại bất kỳ LSN nào.

### Đáp án 24. Crash recovery và PITR

Crash recovery của data directory hiện tại bắt đầu từ redo LSN trong checkpoint/control state hiện tại. PITR bắt đầu từ redo point của base backup, cần replay WAL liên tục từ backup tới recovery target. Checkpoint mới trên primary không cho phép bỏ qua WAL từ backup.

### Đáp án 25. RTO/RPO

Checkpoint có thể giảm lượng WAL phải replay và qua đó giảm một phần RTO của crash recovery. Nó không xác định RPO; RPO phụ thuộc WAL durability, archive continuity, backup, synchronous/asynchronous replication và failover policy.

### Đáp án 26. Ước lượng

24 GB ÷ 200 MB/s ≈ 120 giây nếu dùng quy ước 1 GB = 1000 MB. Nếu dùng 1 GiB = 1024 MiB thì phép tính xấp xỉ 123 giây. Chưa tính startup, random I/O, data page writes, CPU, decompression, fsync, archive fetch và kiểm tra ứng dụng.

### Đáp án 27. CHECKPOINT và pg_switch_wal

`CHECKPOINT` ghi dirty pages và checkpoint state. `pg_switch_wal()` chuyển WAL sang segment mới để segment hiện tại có thể được archive sớm hơn; nó không tạo checkpoint và không buộc flush toàn bộ dirty data pages.

### Đáp án 28. Thí nghiệm crash

Tạo cluster riêng bằng initdb, start port riêng, tạo bảng và COMMIT dữ liệu, gọi CHECKPOINT, thực hiện thêm thay đổi đã COMMIT, stop bằng `pg_ctl stop -m immediate`, start lại, đọc log recovery và SELECT xác minh. Chỉ thao tác trên disposable data directory.

### Đáp án 29. Tuning

1. Xác nhận requested checkpoint counter tăng do WAL threshold hay nguyên nhân khác.
2. Đo WAL generation rate, FPI, checkpoint write/sync time.
3. Vì archive backlog bằng 0, tiếp tục kiểm tra slots/standby retention và disk.
4. Xem storage write latency và checkpoint completion.
5. Thử tăng `max_wal_size` nếu WAL threshold thực sự gây checkpoint dày và disk headroom đủ.
6. Đo lại steady-state latency, WAL bytes, checkpoint stats và recovery time.

Không thay `full_page_writes` hoặc tắt fsync để giảm số liệu.

### Đáp án 30. Recovery plan

- **Checkpoint:** tune để redo distance và steady-state I/O phù hợp; không coi là RPO control.
- **Base backup:** lập lịch đủ thường xuyên, lưu ở failure domain độc lập và test restore.
- **WAL archive:** archive liên tục, alert khi archive failure và kiểm tra chuỗi WAL để đạt RPO 1 phút theo khả năng thực tế.
- **Standby:** dùng streaming/synchronous replication phù hợp với RPO, cân nhắc synchronous commit/standby acknowledgement và khả năng failover.
- **Monitoring:** checkpoint stats, WAL bytes, archive lag, slot retention, standby receive/replay lag, disk headroom và backup age.
- **Recovery drills:** test crash recovery, standby promotion và PITR để đạt RTO 10 phút; đo từ detection tới app-ready.

Checkpoint không thể tự bảo đảm RPO 1 phút, không thay base backup/archive, không xử lý failover mất WAL chưa replicate và không đảm bảo RTO nếu restore/archive/storage/application startup là bottleneck.

## 26. Case study vận hành

### 26.1. Checkpoint request tăng sau khi tăng traffic

**Triệu chứng:** `num_requested` tăng nhanh, WAL bytes/sec cao, query latency tăng theo các đợt checkpoint.

**Phân tích:** workload tạo WAL nhanh hơn mức cấu hình hiện tại. Nếu checkpoint bị request liên tục do `max_wal_size`, checkpointer có thể phải ghi dirty pages thường xuyên.

**Hướng xử lý:** đo WAL rate và checkpoint timing; kiểm tra disk headroom; thử tăng `max_wal_size`/điều chỉnh timeout trong change window; đo lại p95/p99 và recovery test. Không đơn giản giảm `checkpoint_timeout` vì có thể làm checkpoint dày hơn.

### 26.2. pg_wal chiếm gần hết filesystem dù checkpoint chạy đều

**Triệu chứng:** log checkpoint bình thường nhưng thư mục `pg_wal` vẫn tăng.

**Phân tích:** checkpoint không phải retention blocker duy nhất. Archive command có thể thất bại hoặc replication slot giữ WAL cũ.

**Hướng xử lý:** xem `pg_stat_archiver`, archive logs, `pg_replication_slots.restart_lsn` và standby replay. Sửa archive/consumer hoặc xử lý slot không còn cần. Không xóa WAL thủ công.

### 26.3. Crash recovery chậm dù redo distance không lớn

**Triệu chứng:** LSN distance nhỏ nhưng startup vẫn lâu.

**Phân tích:** recovery time còn phụ thuộc I/O random, data page reads/writes, WAL record types, FPI, cache state, storage latency và CPU. Có thể có startup tasks hoặc recovery từ archive.

**Hướng xử lý:** xem recovery logs và OS/storage metrics; tách thời gian redo với thời gian restore/startup/validation; không chỉ tăng checkpoint frequency.

### 26.4. PITR mất nhiều thời gian dù checkpoint vừa chạy trên primary

**Triệu chứng:** đội vận hành kỳ vọng checkpoint mới làm PITR nhanh, nhưng restore từ base backup cũ vẫn replay WAL dài.

**Phân tích:** PITR từ base backup bắt đầu tại redo point của backup, không phải checkpoint hiện tại của primary. Checkpoint sau backup không cho phép bỏ qua WAL cần thiết.

**Hướng xử lý:** tối ưu lịch base backup, archive throughput và restore parallelism phù hợp; kiểm thử PITR với backup age đại diện.

### 26.5. Standby không giải phóng WAL

**Triệu chứng:** restartpoints_done không tăng, WAL retained lớn.

**Phân tích:** standby có thể chưa nhận checkpoint record mới, replay bị lag hoặc storage chậm. Replication slot cũng có thể giữ WAL theo restart_lsn.

**Hướng xử lý:** xem receive/replay LSN, wait events, slot retention và logs của standby. Khôi phục streaming/replay hoặc reinitialize standby theo quy trình.

### 26.6. FPI/WAL tăng sau khi rút checkpoint_timeout

**Triệu chứng:** checkpoint count và `wal_fpi` tăng, WAL archive bandwidth tăng.

**Phân tích:** page nóng bị thay đổi lần đầu nhiều lần sau các checkpoint ngắn hơn, dẫn tới nhiều full-page images.

**Hướng xử lý:** so sánh FPI ratio, workload, `wal_compression` và checkpoint interval; cân bằng recovery time với WAL/storage cost. Không tắt `full_page_writes` chỉ để giảm WAL.

## 27. Checklist cho thiết kế và vận hành checkpoint

### 27.1. Hiểu trạng thái

1. Có phân biệt checkpoint LSN với redo LSN không?
2. Có biết checkpoint hiện tại từ `pg_control_checkpoint()`/`pg_controldata` không?
3. Có ghi nhận PostgreSQL major để chọn đúng thống kê view không?
4. Có biết WAL generation rate trong peak workload không?
5. Có đo redo distance thay vì chỉ nhìn `max_wal_size` không?

### 27.2. Tuning và hiệu năng

6. `checkpoint_timeout` có phù hợp với workload không?
7. `max_wal_size` có đủ cho WAL burst và disk headroom không?
8. `checkpoint_completion_target` có làm mượt I/O không?
9. Checkpoint write/sync time có được theo dõi bằng delta không?
10. Có theo dõi FPI/WAL bytes và ảnh hưởng của checkpoint frequency không?
11. `full_page_writes` có được giữ bật theo durability assumptions không?
12. Có đánh giá `wal_compression` bằng CPU/WAL metrics không?
13. Có kiểm tra checkpoint warnings và requested checkpoints không?
14. Có phân biệt checkpoint pressure với archive/slot retention pressure không?

### 27.3. WAL và retention

15. Archive command có được giám sát và alert khi thất bại không?
16. WAL archive có liên tục từ base backup tới recovery target không?
17. Replication slots inactive/lagging có được cảnh báo không?
18. Có disk alert cho filesystem chứa `pg_wal` không?
19. Có tránh xóa/sửa WAL segment bằng tay không?
20. Có hiểu `max_wal_size` là soft target không?

### 27.4. Recovery

21. Có phân biệt crash recovery, archive recovery/PITR và standby restartpoint không?
22. Có base backup gần đây và đã test restore không?
23. Có chọn đúng timeline khi failover/PITR không?
24. Có RTO/RPO rõ ràng theo business requirements không?
25. Có test crash recovery bằng disposable cluster không?
26. Có test PITR từ backup và WAL archive thực tế không?
27. Có đo app-ready time, không chỉ process-ready time không?
28. Có kiểm tra consistency/transaction results sau recovery không?
29. Có runbook cho WAL missing, archive backlog và standby lag không?
30. Có capacity planning cho WAL, archive, backup, replica và restore staging không?

## 28. Tổng kết

**Checkpoint** là quá trình PostgreSQL đồng bộ WAL và dirty data pages, ghi checkpoint record và cập nhật trạng thái để xác định điểm bắt đầu crash recovery. **Redo LSN** là vị trí WAL cần replay; **checkpoint LSN** là vị trí checkpoint record. Hai giá trị này có liên quan nhưng không đồng nhất.

Những nguyên tắc cần nhớ:

- WAL-before-data bảo đảm WAL cần thiết đã bền vững trước khi data page tương ứng được ghi.
- Crash recovery bắt đầu từ redo point của checkpoint hợp lệ và replay WAL theo thứ tự.
- Checkpoint mới thường làm redo distance ngắn hơn, nhưng recovery time còn phụ thuộc storage, CPU, data pages, WAL record types và startup workflow.
- Checkpoint quá dày có thể tăng I/O, latency spikes và full-page images; checkpoint quá thưa có thể làm redo distance và recovery time tăng.
- `checkpoint_timeout` điều khiển thời gian, `max_wal_size` là soft target WAL, `checkpoint_completion_target` trải đều checkpoint writes.
- `full_page_writes` giúp bảo vệ khỏi torn pages; không tắt tùy tiện.
- `pg_stat_checkpointer` có từ PostgreSQL 17; các major cũ dùng checkpoint counters trong `pg_stat_bgwriter`.
- `pg_control_checkpoint()` và `pg_controldata` giúp đọc checkpoint/redo information.
- Archive failure và replication slots có thể giữ WAL dù checkpoint đã chạy.
- Standby dùng restartpoints, bị ràng buộc bởi checkpoint records nhận từ primary.
- Crash recovery khác PITR: PITR cần base backup và WAL liên tục từ backup tới target.
- RTO đo thời gian khôi phục dịch vụ; RPO đo lượng dữ liệu có thể mất. Checkpoint không tự quyết định RPO.
- Cấu hình phải được benchmark và recovery-tested trên môi trường tương tự production.

Nguyên tắc thực hành:

> **Tối ưu checkpoint để cân bằng I/O bình thường với redo distance; thiết kế RTO/RPO bằng cả backup, WAL archive, replication và recovery drills.**

## 29. Tài liệu tham khảo

Tài liệu PostgreSQL chính thức; chọn trang khớp major server đang vận hành:

- [WAL Introduction](https://www.postgresql.org/docs/current/wal-intro.html): Write-Ahead Logging và durability.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): checkpoint, WAL buffers, full_page_writes, max_wal_size và các tham số WAL.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records, LSN và segment organization.
- [WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): bảo vệ WAL và các giả định về storage.
- [Routine Database Maintenance — WAL](https://www.postgresql.org/docs/current/wal-configuration.html): cấu hình WAL/checkpoint và tuning.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, archive WAL và PITR.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication, standby recovery và restartpoints.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_checkpointer, pg_stat_bgwriter, pg_stat_wal và các views liên quan.
- [Administrative Functions](https://www.postgresql.org/docs/current/functions-admin.html): pg_control_checkpoint, LSN functions và WAL control functions.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html): đọc control information từ data directory.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html): start/stop server và các shutdown modes.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo base backup và checkpoint mode.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backup, không thay physical base backup cho PITR.








