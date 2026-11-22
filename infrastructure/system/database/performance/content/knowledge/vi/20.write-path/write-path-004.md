# Checkpoint, ghi nền và các đợt tăng độ trễ

## Mục tiêu bài học

Một hệ quản trị cơ sở dữ liệu có thể xử lý giao dịch nhanh trong phần lớn thời gian nhưng thỉnh thoảng xuất hiện những đợt tăng độ trễ: nhiều câu `INSERT` hoặc `UPDATE` cùng chậm, thời gian commit tăng, I/O ghi tăng mạnh và p95/p99 xấu đi. Một nguyên nhân cần kiểm tra là checkpoint và cách hệ quản trị ghi các trang dữ liệu đã thay đổi xuống thiết bị lưu trữ.

Trong chương **Đường ghi dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này giải thích quan hệ giữa WAL, dirty page, checkpoint, background writer và các đợt tăng độ trễ. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, việc xử lý checkpoint cần kết hợp số liệu ghi, thời gian flush/sync, WAL, trạng thái buffer và độ trễ ứng dụng, thay vì chỉ tăng một tham số cấu hình.

Sau bài học, bạn có thể:

- Phân biệt WAL, dirty page, checkpoint, background writer và thao tác flush khi commit.
- Giải thích vì sao checkpoint có thể tạo ra tải ghi lớn và làm tăng độ trễ.
- Nhận diện tác động của checkpoint quá thường xuyên, full-page image và lưu lượng WAL.
- Phân biệt I/O do checkpointer với I/O do backend, WAL writer, autovacuum hoặc ứng dụng.
- Theo dõi checkpoint, WAL và I/O bằng log cùng các view thống kê PostgreSQL.
- Điều chỉnh checkpoint và ghi nền dựa trên dữ liệu, đồng thời cân nhắc dung lượng WAL và thời gian phục hồi.
- Thiết kế phép đo trước/sau để xác nhận độ trễ đã ổn định dưới tải đọc/ghi đại diện.

## 1. Đường ghi dữ liệu trong PostgreSQL

Để hiểu checkpoint, trước tiên cần phân biệt hai loại dữ liệu được ghi trong quá trình cập nhật: **WAL (Write-Ahead Log)** và **data page**.

Khi một transaction thay đổi dòng dữ liệu, PostgreSQL thường sửa trang tương ứng trong shared buffers của bộ nhớ. Trang đã thay đổi được gọi là **dirty page**. Cùng lúc, hệ quản trị tạo WAL record mô tả thay đổi cần thiết để có thể phục hồi hoặc phát lại thao tác.

Nguyên tắc write-ahead yêu cầu WAL liên quan phải được ghi bền vững trước khi data page tương ứng được ghi xuống file dữ liệu. Khi transaction commit với chế độ đồng bộ thông thường, PostgreSQL cần bảo đảm WAL của transaction đã được flush tới thiết bị lưu trữ trước khi xác nhận commit thành công. Data page có thể được ghi xuống sau đó.

```text
Ứng dụng gửi UPDATE
        |
        v
Sửa trang trong shared buffers
        |
        +------> Trang trở thành dirty page
        |
        v
Tạo WAL record trong WAL buffers
        |
        v
Flush WAL theo yêu cầu commit
        |
        v
Xác nhận COMMIT theo chính sách durability
        |
        v
Data page được ghi xuống data files sau đó
        bởi background writer / checkpointer / backend
```

Sơ đồ là mô hình khái quát. Một số chi tiết phụ thuộc loại câu lệnh, cấu hình commit, đồng bộ replication và cách hệ điều hành/thiết bị lưu trữ xử lý ghi bền vững.

### 1.1. WAL và data page có vai trò khác nhau

| Thành phần | Chứa gì? | Mục đích |
|---|---|---|
| WAL | Bản ghi mô tả thay đổi và thông tin phục hồi | Bảo đảm khả năng phục hồi sau crash; hỗ trợ replication và PITR khi cấu hình phù hợp |
| Shared buffers | Các trang dữ liệu đang được dùng trong bộ nhớ | Giảm I/O đọc và là nơi backend thực hiện thay đổi trang |
| Dirty page | Trang trong shared buffers đã thay đổi nhưng chưa được ghi xuống data file | Cần được ghi xuống lưu trữ theo cơ chế checkpoint/ghi nền |
| Data files | Các trang dữ liệu bền vững của bảng và index | Lưu trạng thái dữ liệu trên thiết bị lưu trữ |
| Checkpoint | Mốc phục hồi được ghi nhận sau khi các yêu cầu ghi cần thiết được hoàn tất | Giới hạn lượng WAL cần phát lại trong một lần crash recovery |

WAL không phải bản sao đồng bộ tức thời của mọi data page. Một transaction có thể đã commit và được xác nhận sau khi WAL được flush, trong khi data page chứa thay đổi vẫn còn dirty trong bộ nhớ. Nếu máy chủ gặp sự cố trước khi trang được ghi, PostgreSQL dùng WAL để phục hồi trạng thái cần thiết.

### 1.2. Commit latency khác checkpoint latency

Thời gian commit thường phụ thuộc vào việc WAL được ghi và đồng bộ bền vững, đặc biệt khi `synchronous_commit` bật. Checkpoint chủ yếu điều phối việc ghi dirty data page và tạo mốc phục hồi. Hai hoạt động có liên hệ qua I/O và WAL nhưng không đồng nhất.

Nếu commit tăng độ trễ, cần xem WAL flush, độ trễ thiết bị chứa WAL, synchronous replication và cấu hình durability. Nếu nhiều truy vấn ghi chậm đồng thời với một checkpoint có thời gian write/sync lớn, checkpoint I/O có thể đang cạnh tranh với WAL hoặc I/O dữ liệu. Chỉ nhìn thời điểm checkpoint mà không đo WAL flush sẽ dễ quy nhầm nguyên nhân.

## 2. Checkpoint là gì?

**Checkpoint** là một mốc trong WAL mà tại đó PostgreSQL bảo đảm các thay đổi dữ liệu cần thiết trước mốc đó đã được ghi xuống data files theo quy trình checkpoint. Sau checkpoint, khi phục hồi sau crash, hệ quản trị có thể bắt đầu phát lại WAL từ một vị trí gần checkpoint thay vì phải xử lý toàn bộ WAL từ lúc hệ thống khởi động.

Checkpoint giúp giới hạn công việc crash recovery và quản lý vòng đời WAL. Để tạo checkpoint, PostgreSQL phải ghi các dirty buffers liên quan xuống lưu trữ, đồng bộ file theo yêu cầu, rồi ghi nhận checkpoint record trong WAL.

### 2.1. Điều gì kích hoạt checkpoint?

Checkpoint tự động có thể được kích hoạt bởi:

- **Checkpoint timeout:** đã đến giới hạn thời gian giữa các checkpoint tự động.
- **WAL pressure:** lượng WAL phát sinh đạt ngưỡng khiến PostgreSQL cần checkpoint để có thể tái sử dụng/recycle WAL segment.
- **Yêu cầu tường minh:** quản trị viên hoặc một thao tác vận hành gọi `CHECKPOINT`.

Trong PostgreSQL, hai tham số quan trọng là:

- `checkpoint_timeout`: khoảng thời gian tối đa giữa các checkpoint tự động do timeout.
- `max_wal_size`: ngưỡng WAL ước lượng mà khi tiến gần hoặc vượt có thể làm checkpoint được yêu cầu sớm hơn.

`max_wal_size` không phải giới hạn cứng của tổng dung lượng WAL. Khi tải ghi tăng đột biến, lưu trữ WAL bị giữ bởi replication slot hoặc archiving chậm, dung lượng thực tế có thể vượt giá trị này. Checkpoint cũng có thể xảy ra sớm hơn do áp lực WAL.

### 2.2. Checkpoint ghi những gì?

Trong quá trình checkpoint, checkpointer xử lý các dirty shared buffers thuộc phạm vi checkpoint. PostgreSQL phải bảo đảm WAL cần thiết đã được flush trước khi data page tương ứng được ghi. Khi các ghi cần thiết và đồng bộ hoàn tất, checkpoint record được ghi vào WAL để đánh dấu mốc phục hồi.

Checkpoint không có nghĩa là mọi dữ liệu trong toàn bộ hệ thống được ghi lại theo một bản sao đầy đủ, và cũng không phải thao tác backup. Nó là một phần của cơ chế quản lý trạng thái bền vững và crash recovery.

### 2.3. Checkpoint không phải thao tác commit

Một transaction không phải chờ checkpoint tiếp theo mới được commit. Với cấu hình đồng bộ thông thường, commit cần WAL của transaction được flush; data page có thể được ghi sau. Vì vậy:

- Một checkpoint chậm có thể làm tăng cạnh tranh I/O và ảnh hưởng gián tiếp đến transaction đang chạy.
- Một transaction commit chậm có thể do WAL flush chậm dù không có checkpoint tại thời điểm đó.
- Một hệ thống có checkpoint đều đặn vẫn có thể có commit latency cao do thiết bị WAL, synchronous replica hoặc tải ghi log lớn.

Khi chẩn đoán, hãy thu thập riêng số liệu checkpoint và WAL flush.

## 3. Checkpoint quá thường xuyên và các đợt tăng độ trễ

Nếu checkpoint xảy ra quá thường xuyên, PostgreSQL có thể phải ghi dirty page với nhịp dồn dập. Khi nhiều trang bẩn tích lũy giữa hai checkpoint, checkpointer có thể tạo ra lượng ghi lớn trong một khoảng thời gian. I/O ghi này cạnh tranh với truy vấn đọc, ghi transaction, WAL flush, autovacuum và các tiến trình khác.

Các biểu hiện có thể gặp:

- p95/p99 của `INSERT`, `UPDATE` hoặc `DELETE` tăng theo chu kỳ.
- Thông lượng ghi dao động; một số khoảng thời gian hệ thống chậm rõ rệt.
- Độ trễ ghi của thiết bị lưu trữ và queue depth tăng trong lúc checkpoint.
- Log checkpoint cho thấy nhiều buffer được ghi hoặc thời gian write/sync tăng.
- WAL được tạo nhanh và checkpoint được yêu cầu thường xuyên do chạm `max_wal_size`.

Không phải checkpoint nào cũng gây spike. Nếu lưu lượng ghi thấp, dirty page ít và thiết bị có đủ năng lực, checkpoint có thể hoàn tất mà không ảnh hưởng đáng kể tới độ trễ ứng dụng.

### 3.1. Checkpoint do timeout và checkpoint do WAL pressure

PostgreSQL phân biệt checkpoint tự động theo timeout và checkpoint được yêu cầu do WAL. Thống kê hoặc log có thể cho thấy loại checkpoint nào đang chiếm ưu thế.

Nếu phần lớn checkpoint là do WAL pressure, có thể workload sinh WAL nhanh hơn dự kiến hoặc `max_wal_size` quá nhỏ so với tốc độ ghi và thời gian checkpoint. Nếu checkpoint chủ yếu do timeout, cần xem liệu chu kỳ hiện tại có tạo ra lượng dirty page lớn hay không.

Đừng tăng `checkpoint_timeout` chỉ vì thấy nhiều checkpoint. Nếu WAL pressure vẫn thường xuyên xảy ra, tham số timeout cao hơn không giải quyết được nguyên nhân. Cần đo tốc độ WAL, thời gian checkpoint, khả năng lưu trữ và lượng WAL bị giữ lại.

### 3.2. Full-page image và write amplification

Khi `full_page_writes` bật (mặc định trong cấu hình PostgreSQL thông thường), lần đầu một trang được sửa sau checkpoint có thể ghi một full-page image (FPI) vào WAL. FPI giúp phục hồi trang an toàn nếu crash xảy ra trong lúc ghi trang có thể bị torn write.

Checkpoint quá thường xuyên có thể làm tăng số lần một trang đủ điều kiện tạo FPI trong một khoảng thời gian nhất định. Nếu workload thường xuyên cập nhật cùng các trang, WAL volume có thể tăng đáng kể. Điều này làm tăng I/O ghi WAL, chi phí archiving và lượng dữ liệu replication phải truyền.

`wal_compression` có thể giảm kích thước một số full-page image bằng cách nén, đổi lại tiêu thụ CPU. Khả năng và thuật toán nén phụ thuộc phiên bản. Không tắt `full_page_writes` để giảm WAL trong hệ thống cần bảo vệ dữ liệu; đó là thay đổi rủi ro đối với khả năng phục hồi sau sự cố lưu trữ.

### 3.3. Checkpoint đồng thời với các nguồn I/O khác

Một checkpoint có thể trùng với:

- Transaction tạo WAL với tốc độ cao.
- Autovacuum đang đọc/ghi bảng và index.
- Tác vụ tạo index, reindex hoặc bulk load.
- Backup, archiving hoặc sao chép dữ liệu.
- Truy vấn báo cáo đọc nhiều trang.
- Replication hoặc archive process đang bị chậm.

Tổng I/O cạnh tranh có thể vượt năng lực thiết bị dù từng hoạt động riêng lẻ đều bình thường. Khi đó cần xem lịch chạy job, IOPS, throughput, độ sâu hàng đợi, latency đọc/ghi và mức sử dụng thiết bị, không chỉ thống kê nội bộ PostgreSQL.

## 4. Checkpointer, background writer và backend ghi trang

PostgreSQL có nhiều thành phần tham gia ghi dirty buffers. Phân biệt vai trò của chúng giúp xác định vì sao ghi dữ liệu tập trung vào một thời điểm hoặc vì sao backend phải tự thực hiện I/O.

### 4.1. Checkpointer

Checkpointer thực hiện công việc ghi dirty buffers để hoàn tất checkpoint. Nó phối hợp quá trình ghi theo mục tiêu thời gian checkpoint và đồng bộ file cần thiết. Nếu checkpoint có quá nhiều trang phải ghi hoặc thiết bị lưu trữ chậm, thời gian checkpoint có thể kéo dài và cạnh tranh I/O với workload.

### 4.2. Background writer

Background writer chủ động ghi một số dirty buffers trước khi chúng bị cần đến để tái sử dụng. Mục tiêu là giúp backend tìm được buffer sạch khi cần cấp phát buffer mới, giảm khả năng backend phải tự ghi một dirty page trong đường xử lý truy vấn.

Background writer không thay thế checkpointer. Nó làm sạch buffer theo nhu cầu dự đoán và cấu hình; checkpointer vẫn chịu trách nhiệm hoàn tất checkpoint. Background writer ghi quá nhiều cũng có thể tạo I/O không cần thiết nếu các trang vừa được ghi lại tiếp tục bị sửa.

### 4.3. Backend process

Nếu backend cần một buffer sạch nhưng không tìm được buffer phù hợp, backend có thể phải tự ghi dirty buffer để giải phóng chỗ. Điều này đưa I/O ghi vào đường thực thi của request ứng dụng, có thể làm tăng latency của truy vấn đó.

Nếu số liệu cho thấy backend thường xuyên phải ghi buffer, cần xem background writer có theo kịp nhu cầu hay không, working set có quá lớn, cache churn có cao hoặc workload ghi có tăng đột biến hay không. Không nên chỉ tăng background writer mà chưa đánh giá tác động I/O.

### 4.4. WAL writer

WAL writer ghi WAL buffers ra WAL files theo cơ chế và chu kỳ của PostgreSQL. Commit đồng bộ có thể yêu cầu flush WAL ngay, nên transaction không nhất thiết chờ WAL writer theo chu kỳ thông thường. WAL writer và checkpointer là hai thành phần khác nhau: một bên xử lý WAL, bên kia phối hợp ghi data page cho checkpoint.

### 4.5. Bảng phân biệt

| Thành phần | Công việc chính | Dấu hiệu cần xem |
|---|---|---|
| Checkpointer | Ghi dirty buffers và hoàn tất checkpoint | Số checkpoint, buffers written, write time, sync time |
| Background writer | Ghi trước một số dirty buffers để giảm việc backend phải tự ghi | Số buffer clean, số lần chạm giới hạn ghi nền, mức ghi nền và I/O phát sinh |
| Backend | Thực hiện SQL; có thể phải ghi dirty buffer khi cần buffer sạch | Backend write, buffer allocation, latency của truy vấn và cache churn |
| WAL writer | Ghi WAL buffers theo chu kỳ | WAL bytes, WAL write/sync time và commit latency |
| Autovacuum | Dọn phiên bản tuple cũ, cập nhật visibility/statistics và bảo trì | I/O, CPU, thời gian chạy, dead tuples và ảnh hưởng tới workload |

## 5. Làm mượt checkpoint bằng cách nào?

PostgreSQL có cơ chế phân bố công việc ghi checkpoint theo thời gian thay vì cố ghi toàn bộ dirty page trong một đợt ngắn.

### 5.1. checkpoint_completion_target

`checkpoint_completion_target` đặt mục tiêu thời gian hoàn tất checkpoint theo tỷ lệ của khoảng thời gian checkpoint dự kiến. Giá trị cao hơn giúp phân bố I/O ghi đều hơn trong khoảng đó, giảm khả năng dồn toàn bộ ghi vào một đoạn ngắn.

Một cấu hình hiện đại thường dùng giá trị cao, ví dụ 0.9, nhưng giá trị phù hợp cần được xác nhận theo phiên bản, thiết bị lưu trữ và workload. Đặt quá thấp có thể làm checkpoint ghi dồn dập; đặt cao không tạo thêm năng lực I/O và có thể khiến ghi nền kéo dài gần tới checkpoint tiếp theo nếu thiết bị không theo kịp.

Không xem `checkpoint_completion_target` là nút tăng tốc đơn lẻ. Nó điều chỉnh nhịp phân bố công việc; tổng số trang cần ghi và năng lực thiết bị vẫn là yếu tố quyết định.

### 5.2. max_wal_size và min_wal_size

`max_wal_size` ảnh hưởng ngưỡng WAL pressure kích hoạt checkpoint. Tăng giá trị này có thể giảm số checkpoint do WAL và giảm tần suất tạo FPI lặp lại trên cùng trang. Đổi lại:

- PostgreSQL có thể giữ nhiều WAL hơn trước checkpoint.
- Nhu cầu dung lượng đĩa và archive/replication có thể tăng.
- Sau crash, lượng WAL cần phát lại có thể lớn hơn, làm recovery lâu hơn.
- `max_wal_size` không phải giới hạn cứng; tải cao hoặc WAL bị giữ bởi slot/archive vẫn có thể làm dung lượng vượt ngưỡng.

`min_wal_size` định hướng lượng WAL segment tối thiểu được giữ để tái sử dụng, giúp tránh tạo/xóa segment liên tục khi workload có chu kỳ. Nó không trực tiếp làm checkpoint nhanh hơn.

Hãy điều chỉnh dựa trên tốc độ WAL theo giờ cao điểm, thời gian checkpoint, dung lượng đĩa, archive throughput và mục tiêu crash recovery.

### 5.3. checkpoint_timeout

`checkpoint_timeout` giới hạn khoảng thời gian giữa các checkpoint tự động do timeout. Tăng tham số này có thể làm checkpoint theo thời gian thưa hơn, nhưng nếu WAL đạt ngưỡng trước thì checkpoint vẫn có thể được yêu cầu sớm. Giảm tham số có thể giúp giới hạn khoảng WAL cần phục hồi, nhưng tăng tần suất checkpoint và FPI.

Chọn timeout theo sự cân bằng giữa:

- Khả năng chịu tải ghi và mức I/O có thể phân bố.
- Dung lượng WAL và tốc độ archive/replication.
- Thời gian crash recovery có thể chấp nhận.
- Mức biến động của workload.

Không chọn giá trị chỉ dựa trên việc muốn “ít checkpoint hơn”.

### 5.4. Các tham số ghi nền

PostgreSQL có các tham số như `bgwriter_lru_maxpages`, `bgwriter_lru_multiplier` và `bgwriter_flush_after` để điều khiển một số khía cạnh của background writer và writeback. Ý nghĩa chi tiết, giá trị mặc định và khả năng cấu hình phụ thuộc phiên bản.

- Tăng mức ghi nền có thể giúp backend ít phải tự ghi buffer hơn, nhưng cũng tăng I/O do background writer.
- Ghi quá sớm có thể tạo write amplification nếu trang lại bị sửa trước checkpoint.
- Flush theo lô có thể giúp hệ điều hành xử lý writeback hiệu quả hơn trên một số thiết bị, nhưng không phải mọi storage stack đều có cùng hành vi.

Chỉ điều chỉnh khi thống kê cho thấy backend phải ghi nhiều buffer hoặc cache churn đang làm tăng latency. Sau mỗi thay đổi, theo dõi cả I/O nền, backend write, checkpoint duration và latency ứng dụng.

### 5.5. Không tắt các bảo đảm durability để che spike

Không tắt `fsync` hoặc `full_page_writes` trong hệ thống cần bảo vệ dữ liệu để giảm I/O. Tắt `fsync` có thể làm mất hoặc hỏng dữ liệu sau sự cố hệ điều hành/thiết bị; tắt `full_page_writes` làm tăng rủi ro trang bị ghi dở không thể phục hồi đúng.

`synchronous_commit = off` là một lựa chọn chính sách durability khác: PostgreSQL có thể xác nhận commit trước khi WAL của transaction được flush bền vững. Một crash có thể làm mất một số transaction gần đây đã được xác nhận, dù trạng thái database vẫn có thể phục hồi nhất quán. Chỉ cân nhắc cho workload chấp nhận được rủi ro mất các commit gần nhất; đây không phải cách sửa checkpoint và không phù hợp với mọi nghiệp vụ.

## 6. Quan sát checkpoint và ghi nền

Chẩn đoán cần kết hợp log checkpoint, view thống kê PostgreSQL và số liệu thiết bị lưu trữ. Thống kê tích lũy nên được so sánh theo khoảng thời gian, không chỉ nhìn tổng số từ lúc server khởi động.

### 6.1. Bật log checkpoint

Trong PostgreSQL, `log_checkpoints` cho phép ghi log khi checkpoint bắt đầu và hoàn tất. Ví dụ một dòng log hoàn tất có thể cho biết số buffer đã ghi, thời gian write, thời gian sync và tổng thời gian checkpoint. Định dạng log thay đổi theo phiên bản.

Khi đọc log, tập trung vào:

- Thời điểm bắt đầu và kết thúc checkpoint.
- Lý do checkpoint nếu log có nêu (timeout hoặc requested).
- Số buffer được ghi.
- Thời gian ghi (`write`) và đồng bộ (`sync`).
- Tổng thời gian checkpoint.
- Số WAL segment được thêm, xóa hoặc tái sử dụng nếu log cung cấp.

Nếu write time cao, có thể lượng ghi lớn hoặc tốc độ ghi dữ liệu hạn chế. Nếu sync time cao, bước đồng bộ file có thể đang chịu độ trễ lưu trữ hoặc nhiều file cần sync. Đây là dấu hiệu điều tra, không phải kết luận cuối cùng; cần đối chiếu với số liệu thiết bị và các workload đồng thời.

### 6.2. Thống kê checkpoint theo phiên bản

Ở PostgreSQL 17 trở lên, thống kê checkpoint được tách trong view `pg_stat_checkpointer`. Các phiên bản cũ hơn đặt nhiều trường checkpoint trong `pg_stat_bgwriter`. Tên cột và phạm vi thống kê thay đổi theo phiên bản, vì vậy hãy kiểm tra tài liệu đúng phiên bản trước khi xây dashboard.

Ví dụ kiểm tra các view:

```sql
-- PostgreSQL 17 trở lên
SELECT *
FROM pg_stat_checkpointer;

-- Xem thống kê background writer
SELECT *
FROM pg_stat_bgwriter;
```

Khi theo dõi theo thời gian, ghi lại hai snapshot và tính chênh lệch của các bộ đếm như số checkpoint theo timeout/request, số buffer được ghi, write time và sync time. Các trường có thể là bộ đếm tích lũy kể từ lần reset thống kê; hãy ghi nhận `stats_reset` và uptime để diễn giải đúng.

### 6.3. Theo dõi WAL

`pg_stat_wal` cung cấp các bộ đếm liên quan tới WAL, chẳng hạn số record, số full-page image, số byte WAL và thời gian write/sync ở các phiên bản hỗ trợ. Ví dụ:

```sql
SELECT *
FROM pg_stat_wal;
```

So sánh mức tăng `wal_bytes`, `wal_fpi`, số lần write/sync và thời gian tương ứng theo khoảng đo. Nếu WAL tăng đột biến cùng lúc checkpoint dày hơn, hãy xem bulk load, update nhiều trang, index maintenance, full-page image và các transaction ghi lớn.

### 6.4. Theo dõi I/O theo backend

Ở các phiên bản PostgreSQL có `pg_stat_io` (PostgreSQL 16 trở lên), view này giúp quan sát I/O theo loại backend, đối tượng và ngữ cảnh. Có thể dùng để phân biệt hoạt động của client backend, background writer, checkpointer và các thành phần khác, tùy các chiều thống kê mà phiên bản cung cấp.

```sql
SELECT *
FROM pg_stat_io;
```

Không so sánh trực tiếp tổng số read/write của các nhóm nếu chưa hiểu đơn vị, cách đếm và loại I/O. Kết hợp với metric hệ điều hành hoặc nền tảng lưu trữ: latency đọc/ghi, IOPS, throughput, queue depth, utilization và write cache flush.

### 6.5. Lấy mẫu thống kê theo khoảng thời gian

Một quy trình quan sát có thể thực hiện như sau:

1. Ghi snapshot của `pg_stat_checkpointer` (hoặc `pg_stat_bgwriter` trên phiên bản cũ), `pg_stat_wal` và `pg_stat_io` nếu có.
2. Ghi cùng thời điểm p50/p95/p99, throughput, CPU, memory và metric storage.
3. Chờ một khoảng đo có tải đại diện, ví dụ 1–5 phút; không reset thống kê chỉ để lấy delta.
4. Lấy snapshot lần hai và tính chênh lệch bộ đếm.
5. Đối chiếu thời điểm latency spike với checkpoint log, WAL rate và I/O device.
6. Lặp lại qua nhiều chu kỳ để phân biệt tương quan lặp lại với nhiễu ngẫu nhiên.

Tổng thời gian chờ cộng dồn của nhiều phiên có thể lớn hơn thời gian đồng hồ thực tế. Tương tự, bộ đếm tích lũy không cho biết một spike xảy ra vào đúng thời điểm nào nếu không có snapshot hoặc log theo thời gian.

## 7. Phân biệt các nguyên nhân gây tăng độ trễ

Checkpoint chỉ là một giả thuyết. Hãy so sánh các dấu hiệu để tìm đúng thành phần.

| Dấu hiệu | Nguyên nhân cần kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| Latency ghi tăng trùng checkpoint; checkpoint write/sync kéo dài | Checkpoint I/O cạnh tranh với workload | Checkpoint log, buffers written, storage write latency và queue depth |
| Commit chậm, WAL sync time tăng nhưng checkpoint bình thường | WAL flush hoặc thiết bị WAL chậm | `pg_stat_wal`, WAL device latency, synchronous replication và commit settings |
| Backend ghi nhiều buffer khi xử lý truy vấn | Background writer không đáp ứng nhu cầu hoặc cache churn | `pg_stat_bgwriter`, `pg_stat_io`, buffer allocation và working set |
| WAL bytes tăng mạnh, checkpoint requested thường xuyên | Write burst, `max_wal_size` thấp so với WAL rate hoặc FPI tăng | WAL delta, checkpoint reason, `wal_fpi`, bulk load/index maintenance |
| Read latency tăng cùng lúc write queue tăng | Thiết bị lưu trữ bị bão hòa do ghi checkpoint hoặc workload khác | Read/write latency, queue depth, IOPS và throughput theo thiết bị |
| Latency tăng nhưng I/O/checkpoint không đổi | CPU, lock contention, plan regression, network hoặc ứng dụng | Wait events, EXPLAIN, CPU run queue, connection pool và tracing |
| Checkpoint lâu nhưng ứng dụng không chậm | Thiết bị còn dư năng lực hoặc I/O được làm mượt tốt | So sánh p95/p99 và storage utilization, không tối ưu chỉ vì duration cao |

Đặc biệt, một checkpoint có tổng thời gian dài không tự động là vấn đề. Nó có thể đang phân bố ghi trong một khoảng rộng để giảm tác động lên ứng dụng. Chỉ xem là nút thắt khi có bằng chứng tương quan với latency, I/O saturation hoặc suy giảm thông lượng.

## 8. Ví dụ chẩn đoán một đợt tăng độ trễ ghi

Giả sử API cập nhật trạng thái đơn hàng thường có p95 khoảng 25 ms. Cứ vài phút, p95 tăng lên vài trăm mili giây trong một khoảng ngắn. CPU không tăng đáng kể, nhưng độ trễ ghi của volume dữ liệu tăng và log cho thấy checkpoint ghi nhiều buffer.

### Bước 1 — Xác nhận tương quan thời gian

Thu thập metric theo cùng trục thời gian:

- p50/p95/p99 của API và thời gian commit.
- Số transaction ghi/giây và WAL bytes/giây.
- Checkpoint start/complete, buffers written, write time và sync time.
- Storage write latency, queue depth và throughput.
- CPU, memory, I/O của autovacuum và tác vụ nền.

Nếu spike latency xuất hiện lặp lại cùng checkpoint và write queue tăng, checkpoint I/O là một giả thuyết mạnh hơn. Nếu commit latency tăng nhưng checkpoint không đổi, hãy điều tra WAL flush và synchronous replication.

### Bước 2 — Xác định lý do checkpoint dày

Kiểm tra số checkpoint do timeout so với checkpoint được yêu cầu bởi WAL. Nếu checkpoint requested chiếm tỷ lệ cao, so sánh WAL generation rate với `max_wal_size`, thời gian checkpoint và dung lượng WAL đang bị giữ bởi archiving/replication slot.

Nếu checkpoint timed chiếm ưu thế nhưng mỗi lần có lượng dirty buffer lớn, xem lại chu kỳ checkpoint và phân bố tải ghi. Nếu WAL tăng bất thường, kiểm tra bulk update, index maintenance, full-page image và các batch job.

### Bước 3 — Chọn điều chỉnh có kiểm soát

Tùy bằng chứng, có thể thử:

- Tăng `max_wal_size` để giảm checkpoint do WAL pressure nếu storage có đủ dung lượng và mục tiêu recovery cho phép.
- Điều chỉnh `checkpoint_timeout` nếu chu kỳ timeout quá ngắn, đồng thời xác nhận WAL không tiếp tục kích hoạt checkpoint sớm.
- Đặt `checkpoint_completion_target` ở mức giúp phân bố I/O đều hơn.
- Điều chỉnh background writer nếu backend phải tự ghi nhiều buffer.
- Dời bulk load hoặc maintenance khỏi giờ cao điểm, hoặc chia batch để giảm burst.
- Xem lại index và câu SQL ghi để tránh ghi nhiều trang không cần thiết.

Không thay nhiều tham số cùng lúc. Chọn một thay đổi có giả thuyết rõ, ghi lại giá trị trước đó và chuẩn bị cách rollback.

### Bước 4 — Kiểm chứng

Chạy lại cùng workload và so sánh:

- p95/p99 của API và commit latency.
- Checkpoint frequency, duration, buffers written, write/sync time.
- WAL bytes và FPI rate.
- Storage latency, queue depth và throughput.
- Throughput transaction, CPU và thời gian crash recovery trong thử nghiệm phù hợp.

Một thay đổi có ích khi giảm biến động độ trễ mà không làm WAL/storage tăng vượt giới hạn, không kéo dài recovery quá mức và không gây tác động xấu lên replication hoặc archiving.

## 9. Những đánh đổi khi điều chỉnh checkpoint

| Điều chỉnh | Lợi ích có thể có | Đánh đổi/rủi ro |
|---|---|---|
| Tăng `max_wal_size` | Ít checkpoint do WAL pressure hơn; có thể giảm FPI lặp lại | Giữ nhiều WAL hơn, cần thêm dung lượng; crash recovery có thể lâu hơn |
| Tăng `checkpoint_timeout` | Giảm checkpoint do timeout | Có thể tích lũy nhiều dirty page; không ngăn checkpoint do WAL pressure |
| Tăng `checkpoint_completion_target` | Phân bố ghi checkpoint đều hơn | I/O kéo dài gần hết chu kỳ; không tăng năng lực storage |
| Điều chỉnh background writer | Giảm backend phải tự ghi dirty buffer | Có thể tăng I/O nền hoặc ghi trang quá sớm |
| Chia batch ghi lớn | Giảm burst và thời gian giữ tài nguyên theo đợt | Tăng số transaction hoặc thời gian hoàn tất tổng thể; cần idempotency |
| Giảm index không cần thiết | Giảm số trang và WAL phải cập nhật khi ghi | Có thể làm truy vấn đọc chậm hơn; cần phân tích workload |
| Dùng `wal_compression` | Giảm kích thước FPI/WAL trong trường hợp phù hợp | Tăng CPU; hiệu quả phụ thuộc dữ liệu và phiên bản |

Checkpoint tuning phải nằm trong kế hoạch dung lượng và phục hồi. Nếu tăng WAL để giảm tần suất checkpoint, hãy kiểm tra disk free space, archive throughput, replication slots, standby lag và thời gian crash recovery có thể chấp nhận.

## 10. Các cấu hình liên quan và lưu ý vận hành

### 10.1. Xem cấu hình hiện tại

```sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW checkpoint_completion_target;
SHOW full_page_writes;
SHOW wal_compression;
SHOW log_checkpoints;
SHOW fsync;
```

Một số tham số có thể cần reload hoặc restart tùy phiên bản và cấu hình. Kiểm tra `pg_settings` để xem giá trị, nguồn cấu hình, khả năng áp dụng và trạng thái pending restart:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_completion_target',
    'full_page_writes',
    'wal_compression',
    'log_checkpoints',
    'fsync'
)
ORDER BY name;
```

### 10.2. Kiểm tra WAL bị giữ lại

WAL có thể không được recycle dù checkpoint đã hoàn tất nếu replication slot, archiving hoặc standby còn cần các segment cũ. Kiểm tra:

- Replication slot inactive hoặc lag lớn.
- `restart_lsn` của slot quá cũ.
- Archive command lỗi hoặc archive backlog tăng.
- Standby ngừng nhận/apply WAL.
- WAL directory tăng dung lượng liên tục.

Không xóa thủ công WAL segment khỏi thư mục dữ liệu để giải phóng dung lượng. Hãy xử lý nguyên nhân giữ WAL theo quy trình replication/archiving; xóa nhầm segment có thể làm hỏng khả năng phục hồi hoặc replication.

### 10.3. Thao tác CHECKPOINT thủ công

Lệnh `CHECKPOINT` yêu cầu PostgreSQL thực hiện checkpoint ngay. Nó có thể hữu ích trong một số quy trình quản trị có chủ đích, nhưng gọi lặp lại trong giờ cao điểm có thể tạo thêm đợt ghi lớn, làm tăng I/O và latency.

Không dùng `CHECKPOINT` như cách “xả cache”, dọn WAL tùy tiện hoặc sửa commit chậm. Hãy để cơ chế tự động hoạt động trừ khi có lý do vận hành rõ ràng và đã đánh giá tác động.

## 11. Quy trình theo dõi và tối ưu checkpoint

**Bước 1 — Thiết lập baseline.** Ghi nhận cấu hình checkpoint/WAL, tốc độ WAL, số checkpoint, thời gian write/sync, storage latency và p95/p99 của workload ghi.

**Bước 2 — Bật quan sát phù hợp.** Bật `log_checkpoints` theo chính sách log; thu thập các view thống kê phù hợp với phiên bản PostgreSQL. Lưu snapshot theo khoảng thời gian.

**Bước 3 — Xác định dạng spike.** Phân biệt commit latency, checkpoint I/O, backend write, autovacuum, bulk load, archive/replication và storage saturation.

**Bước 4 — Tìm nguyên nhân kích hoạt checkpoint.** So sánh timed/requested checkpoint, WAL generation rate, `max_wal_size`, `checkpoint_timeout` và dung lượng WAL bị giữ.

**Bước 5 — Xác định vị trí ghi.** Dùng thống kê background writer, checkpointer và I/O theo backend để biết thành phần nào đang ghi nhiều. Đối chiếu với metric của hệ điều hành và thiết bị.

**Bước 6 — Chọn một điều chỉnh.** Thay đổi tham số hoặc lịch workload theo giả thuyết đã xác định. Ghi lại giá trị cũ, phạm vi ảnh hưởng, điều kiện rollback và yêu cầu dung lượng/recovery.

**Bước 7 — Chạy tải đại diện.** Bao gồm transaction ngắn, batch ghi, truy vấn đọc đồng thời, autovacuum và replication nếu có. Không chỉ benchmark một truy vấn cô lập.

**Bước 8 — Đo lại.** So sánh latency, throughput, WAL, checkpoint, buffer writes, storage queue, archive/replication lag và dung lượng.

**Bước 9 — Đánh giá khả năng phục hồi.** Xác nhận mục tiêu RTO/RPO, dung lượng WAL và thời gian recovery vẫn phù hợp. Tăng checkpoint interval có thể cải thiện throughput nhưng kéo dài recovery.

**Bước 10 — Ghi nhận và giám sát lâu dài.** Lưu cấu hình, kết quả, ngưỡng cảnh báo và cách nhận diện spike tái diễn. Đánh giá lại sau thay đổi dữ liệu hoặc tăng tải.

## 12. Những nhầm lẫn thường gặp

- **“Checkpoint là lúc transaction commit.”** Commit đồng bộ chủ yếu cần WAL được flush; checkpoint là mốc ghi data page và phục hồi.
- **“Mọi dirty page đều do checkpointer ghi.”** Background writer và backend cũng có thể ghi dirty buffers.
- **“Background writer và checkpointer là một tiến trình.”** Chúng có vai trò khác nhau và cần được quan sát riêng.
- **“Checkpoint càng ít càng tốt.”** Checkpoint quá thưa có thể giữ nhiều WAL hơn và kéo dài crash recovery.
- **“max_wal_size là giới hạn cứng của WAL.”** Đây là ngưỡng mục tiêu kích hoạt checkpoint, không phải hard cap; slot và archiving có thể giữ WAL.
- **“Checkpoint duration cao chắc chắn gây chậm ứng dụng.”** Cần chứng minh tương quan với latency hoặc storage saturation.
- **“Tăng checkpoint_completion_target làm giảm tổng I/O.”** Tham số này chủ yếu phân bố nhịp ghi; tổng lượng dữ liệu cần ghi không tự biến mất.
- **“Tăng work_mem sửa được checkpoint spike.”** `work_mem` dành cho một số thao tác sort/hash, không điều khiển lượng dirty data page cần checkpoint.
- **“Tắt fsync hoặc full_page_writes là cách tối ưu an toàn.”** Các thiết lập này bảo vệ durability và khả năng phục hồi; tắt chúng có thể gây mất hoặc hỏng dữ liệu sau sự cố.
- **“Commit chậm luôn do checkpoint.”** WAL flush, thiết bị WAL, synchronous replication và tải I/O cũng có thể làm commit chậm.
- **“Có thể xóa WAL segment cũ bằng tay.”** Không xóa thủ công WAL do PostgreSQL quản lý; xử lý replication slot, archive hoặc standby giữ WAL.

## 13. Checklist chẩn đoán checkpoint và write latency

- [ ] Đã ghi nhận p50/p95/p99, throughput và thời điểm spike.
- [ ] Đã phân biệt commit latency với thời gian checkpoint.
- [ ] Đã thu thập checkpoint log: reason, buffers written, write time và sync time.
- [ ] Đã so sánh checkpoint theo timeout và checkpoint do WAL pressure.
- [ ] Đã đo WAL bytes, full-page image và WAL write/sync theo khoảng thời gian.
- [ ] Đã kiểm tra vai trò checkpointer, background writer và backend write.
- [ ] Đã đối chiếu I/O PostgreSQL với latency, IOPS, throughput và queue depth của storage.
- [ ] Đã kiểm tra autovacuum, bulk load, index maintenance, backup và replication cùng thời điểm.
- [ ] Đã xem WAL bị giữ bởi replication slot hoặc archiving.
- [ ] Đã cân nhắc dung lượng WAL và thời gian crash recovery trước khi tăng checkpoint interval/size.
- [ ] Đã thay đổi từng yếu tố có kiểm soát và có phương án rollback.
- [ ] Đã benchmark tải đọc/ghi hỗn hợp và xác nhận độ trễ ổn định sau thay đổi.

## Kết luận

Checkpoint giúp PostgreSQL ghi các dirty data page và tạo mốc phục hồi, trong khi WAL bảo đảm có thể tái tạo thay đổi đã commit. Checkpointer, background writer, backend và WAL writer đảm nhiệm những phần việc khác nhau. Khi checkpoint quá thường xuyên hoặc ghi dồn vào thiết bị lưu trữ đang bận, I/O cạnh tranh có thể tạo các đợt tăng độ trễ; nhưng commit chậm cũng có thể bắt nguồn từ WAL flush hoặc synchronous replication.

Hãy dùng checkpoint log, thống kê checkpointer/background writer, WAL metrics và số liệu storage để xác định thành phần gây spike. Điều chỉnh `max_wal_size`, `checkpoint_timeout`, `checkpoint_completion_target` hoặc ghi nền chỉ sau khi hiểu nguyên nhân và đánh giá dung lượng WAL, archiving, replication cùng thời gian recovery. Kết quả chỉ được xem là tốt khi độ trễ và thông lượng ổn định hơn dưới tải đại diện mà các yêu cầu durability và khả năng phục hồi vẫn được đáp ứng.
