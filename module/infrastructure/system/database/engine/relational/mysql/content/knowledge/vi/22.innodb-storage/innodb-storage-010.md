# Redo log, log sequence number và checkpoint

InnoDB dùng redo log để khôi phục các thay đổi đã được ghi nhận khi MySQL gặp sự cố trước khi mọi trang dữ liệu được ghi xuống tablespace. Khi một transaction cập nhật hàng, thay đổi thường được thực hiện trên trang trong buffer pool; redo record mô tả những thay đổi cần phát lại để trang dữ liệu có thể được đưa về trạng thái nhất quán sau crash. Cơ chế này cho phép InnoDB xác nhận commit mà không cần chờ mọi data page liên quan được ghi ngay lập tức.

Ba khái niệm cần hiểu cùng nhau là **redo log**, **log sequence number (LSN)** và **checkpoint**. Redo log lưu lịch sử thay đổi theo thứ tự; LSN định vị tiến độ của log; checkpoint cho biết tới đâu các thay đổi đã được phản ánh an toàn vào data page để vùng redo cũ có thể được tái sử dụng. Nếu redo log bị ghi quá nhanh so với tốc độ flush dirty page, checkpoint bị tụt lại và hệ thống có thể chịu áp lực ghi hoặc transaction bị chậm.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là hiểu đường đi của một thay đổi từ buffer pool tới redo log và data file, đọc được các mốc LSN, giải thích checkpoint và chọn cấu hình durability/capacity dựa trên yêu cầu thực tế.

Sau bài học, bạn có thể:

- Giải thích vai trò của redo log trong write-ahead logging và crash recovery.
- Phân biệt redo log buffer, redo log files và dirty pages trong buffer pool.
- Hiểu current LSN, flushed LSN, checkpoint LSN và page LSN.
- Mô tả fuzzy checkpoint và lý do InnoDB không cần flush toàn bộ buffer pool cùng lúc.
- Giải thích checkpoint age và áp lực khi redo log gần hết vùng có thể tái sử dụng.
- Phân biệt redo log với undo log, binary log và doublewrite buffer.
- Đánh giá tác động của `innodb_flush_log_at_trx_commit`, `sync_binlog`, `innodb_log_buffer_size` và `innodb_redo_log_capacity`.
- Quan sát tiến độ redo/checkpoint bằng `SHOW ENGINE INNODB STATUS` và status variables.
- Nhận diện dấu hiệu checkpoint pressure và đề xuất cách xử lý có căn cứ.

## 1. Redo log giải quyết vấn đề gì?

InnoDB quản lý dữ liệu theo page. Khi một transaction cập nhật một hàng, page chứa hàng đó được nạp vào buffer pool nếu chưa có sẵn, sau đó thay đổi được thực hiện trên bản sao trong bộ nhớ. Trang đã thay đổi nhưng chưa được ghi về data file được gọi là *dirty page*.

Nếu MySQL xác nhận commit ngay khi chỉ sửa page trong RAM, sự cố mất điện hoặc tiến trình bị dừng đột ngột có thể làm mất thay đổi đã báo thành công. Ngược lại, nếu mỗi commit phải ghi ngay tất cả page dữ liệu liên quan xuống vị trí cuối cùng trong tablespace, chi phí I/O và thời gian commit sẽ rất lớn.

Redo log giải quyết bài toán này bằng cách ghi lại thông tin đủ để phát lại thay đổi. InnoDB có thể ghi redo tuần tự vào redo log và bảo đảm log được flush theo chính sách durability, trong khi data pages được flush dần ở nền.

Ví dụ, một transaction cập nhật số dư từ 500 thành 400:

1. InnoDB tìm page chứa hàng tài khoản trong buffer pool.
2. Transaction thay đổi page trong bộ nhớ và tạo redo records mô tả thay đổi.
3. Redo records được đưa vào redo log buffer.
4. Theo chính sách commit, redo log được ghi và flush tới storage.
5. Transaction có thể được xác nhận commit khi điều kiện durability tương ứng đã đạt.
6. Dirty page có thể được flush xuống tablespace sau đó.

Nếu server crash sau bước 5 nhưng trước bước 6, redo log giúp InnoDB phục hồi thay đổi đã commit khi khởi động lại.

## 2. Write-ahead logging: log phải đi trước data page

InnoDB tuân theo nguyên tắc *write-ahead logging* (WAL): trước khi một dirty page được ghi xuống data file, các redo records cần thiết để phục hồi những thay đổi trên page đó phải được ghi an toàn tới redo log.

Mô hình khái niệm:

```text
                  Transaction UPDATE
                          |
                          v
                 Buffer pool page
                    (dirty page)
                          |
                          +------> Redo log buffer
                          |                |
                          |                v
                          |          Redo log files
                          |                |
                          |          write / flush
                          |                |
                          v                v
                  Data tablespace     Durable redo
                   (flush later)       for recovery
```

Redo log và data page có lịch ghi khác nhau:

- Redo log được ghi theo thứ tự LSN, thường là I/O tuần tự.
- Data pages được ghi về các vị trí tương ứng trong tablespace theo hoạt động page cleaner và flush list.
- WAL bảo đảm redo cần thiết đã được ghi trước khi data page chứa thay đổi tương ứng được ghi xuống.

Điều này cho phép commit không phải chờ mọi data page được ghi. Tuy nhiên, redo log phải đáp ứng chính sách durability của transaction. Nếu chỉ có log trong RAM hoặc mới nằm trong OS cache chưa được flush theo yêu cầu, sự cố hệ điều hành/mất điện vẫn có thể làm mất commit tùy cấu hình.

## 3. Redo log buffer và redo log files

Redo log có hai lớp chính mà người vận hành thường cần phân biệt.

### 3.1. Redo log buffer

Redo log buffer là vùng bộ nhớ trong InnoDB dùng để giữ redo records trước khi ghi ra redo log files. Kích thước được cấu hình bằng:

```sql
SHOW VARIABLES LIKE 'innodb_log_buffer_size';
```

`innodb_log_buffer_size` hữu ích với transaction tạo nhiều redo records. Nếu buffer quá nhỏ, InnoDB có thể phải ghi redo từ buffer ra log files trước khi transaction kết thúc. Điều đó không làm transaction tự commit; nó chỉ thay đổi thời điểm redo được ghi ra file.

Tăng log buffer không thay thế redo log capacity. Buffer quyết định lượng redo có thể giữ tạm trong RAM; capacity quyết định không gian redo log có thể sử dụng trước khi cần checkpoint giải phóng vùng cũ.

### 3.2. Redo log files

Redo log files là vùng lưu trữ bền vững cho redo records. InnoDB quản lý chúng theo dạng vòng (*circular log*): khi đã ghi tới vùng cuối, nó có thể tái sử dụng vùng cũ nếu checkpoint đã tiến đủ xa để các redo records trong vùng đó không còn cần cho crash recovery.

Trên các bản MySQL mới, cấu hình tổng dung lượng redo log được điều khiển bằng `innodb_redo_log_capacity`. Từ MySQL 8.0.30, InnoDB quản lý các redo log files trong thư mục `#innodb_redo` dưới data directory; cách bố trí file cụ thể là chi tiết nội bộ và không nên được ứng dụng thao tác trực tiếp.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_log_buffer_size';
```

Không xóa, đổi tên, di chuyển hoặc chỉnh sửa redo log files khi server đang chạy. InnoDB phải quản lý vòng đời, vị trí và trạng thái của chúng.

## 4. Log Sequence Number (LSN)

LSN là số thứ tự tăng dần biểu diễn vị trí tiến triển trong redo log. Có thể hình dung LSN như một con trỏ byte trên luồng redo: khi InnoDB tạo redo records mới, LSN tiến về phía trước.

Các mốc LSN quan trọng:

| Mốc | Ý nghĩa khái niệm |
| --- | --- |
| Current LSN | Vị trí redo mới nhất đã được tạo/đánh số |
| Written LSN | Vị trí redo đã được ghi ra file theo tiến độ ghi |
| Flushed LSN | Vị trí redo đã được flush theo cơ chế đồng bộ của hệ thống |
| Checkpoint LSN | Mốc redo cũ nhất không còn cần thiết để phục hồi sau khi các page liên quan đã được flush an toàn |
| Page LSN | LSN được ghi trong một data page, thể hiện mốc redo gần nhất đã áp dụng cho page đó |

Tên trường hiển thị cụ thể trong status output có thể khác nhau theo phiên bản. Các mốc trên giúp đọc tiến độ theo khái niệm, không phải mọi giá trị đều là một biến cấu hình độc lập.

### 4.1. Current LSN

Current LSN tăng khi InnoDB tạo redo records. Nếu workload ghi nhiều, current LSN tiến nhanh hơn; nếu workload ít thay đổi dữ liệu, nó tiến chậm hơn.

Hiệu số current LSN giữa hai thời điểm có thể dùng để ước lượng lượng redo được tạo trong khoảng thời gian đó:

```text
redo generated ~= current_lsn_after - current_lsn_before
redo rate      ~= redo generated / elapsed_seconds
```

Đây là cách ước lượng tốc độ sinh redo, không phải tổng dung lượng data page được ghi. Một lượng redo nhỏ có thể dẫn tới nhiều page flush và ngược lại, tùy mẫu cập nhật và page layout.

### 4.2. Flushed LSN

Flushed LSN biểu thị tiến độ redo đã được flush theo cơ chế durability của InnoDB. Current LSN có thể đi trước flushed LSN vì redo mới được tạo nhưng chưa được flush xong.

Khoảng cách giữa current và flushed phản ánh lượng redo đang chờ ghi/flush tại thời điểm quan sát. Không nên lấy một snapshot đơn lẻ để kết luận lỗi; cần quan sát xu hướng, tốc độ ghi và chính sách flush.

### 4.3. Checkpoint LSN

Checkpoint LSN biểu thị ranh giới phục hồi: redo trước mốc checkpoint không còn cần thiết để dựng lại các page hiện tại vì những thay đổi liên quan đã được ghi an toàn xuống data files.

Checkpoint LSN không phải LSN của transaction commit cuối cùng, cũng không phải vị trí hiện tại của redo writer. Nó phản ánh tiến độ flush data pages và khả năng tái sử dụng vùng redo cũ.

### 4.4. Page LSN

Mỗi InnoDB page có thông tin LSN liên quan đến lần thay đổi gần nhất đã được áp dụng lên page. Trong crash recovery, InnoDB có thể so sánh LSN của redo record với page LSN để quyết định có cần áp dụng record đó hay không.

Nếu page đã phản ánh một LSN mới hơn redo record đang xét, phát lại record cũ sẽ không cần thiết. Page LSN là một phần giúp quá trình recovery tránh áp dụng lại thay đổi đã có trên page.

## 5. Checkpoint là gì?

Checkpoint là quá trình InnoDB bảo đảm các thay đổi có LSN trước một mốc nhất định đã được phản ánh an toàn vào data pages trên storage. Khi checkpoint tiến lên, vùng redo cũ hơn mốc đó có thể được tái sử dụng vì không còn cần cho crash recovery.

Checkpoint không có nghĩa:

- Tất cả transaction đang mở đã commit.
- Tất cả dirty pages trong buffer pool đã được flush.
- Redo log đã bị xóa hoặc reset về 0.
- Một transaction cụ thể vừa được commit.

Checkpoint là tiến độ ghi data page phục vụ quản lý vòng đời redo log và thời gian crash recovery.

### 5.1. Dirty page và flush list

Khi page trong buffer pool bị thay đổi, nó trở thành dirty page. InnoDB theo dõi các dirty pages và thứ tự thay đổi của chúng để biết page nào còn cần được flush trước khi checkpoint có thể tiến.

Page cleaner threads ghi dirty pages xuống tablespace ở nền. Việc flush có thể được kích hoạt bởi:

- Nhu cầu tạo chỗ trống trong buffer pool.
- Áp lực redo log khi checkpoint age tăng.
- Mục tiêu dirty page và chính sách flushing.
- Hoạt động định kỳ và các quyết định của adaptive flushing.

WAL yêu cầu redo tương ứng phải được ghi/flush đủ trước khi dirty page được ghi xuống data file. Nhờ vậy, nếu page write bị gián đoạn, redo vẫn có thể giúp phục hồi thay đổi.

### 5.2. Fuzzy checkpoint

InnoDB dùng cách checkpoint linh hoạt (*fuzzy checkpoint*): các dirty pages được flush rải rác theo khả năng I/O, không cần dừng toàn bộ hoạt động ghi để flush mọi page cùng một lúc.

Điều này giúp duy trì concurrency. Trong lúc page cleaner flush một số page, transaction khác vẫn có thể đọc và cập nhật các page khác. Checkpoint LSN tiến theo giới hạn của những thay đổi cũ nhất vẫn còn cần được bảo vệ.

Một page có thể được cập nhật nhiều lần trước khi được flush. Khi page được ghi xuống, nó có thể đã bao gồm nhiều thay đổi mới hơn LSN ban đầu khiến page trở thành dirty. Việc quản lý page LSN và flush list giúp InnoDB xác định mốc an toàn để tiến checkpoint.

## 6. Checkpoint age và áp lực redo log

Checkpoint age là khoảng cách giữa current LSN và checkpoint LSN:

```text
checkpoint_age = current_lsn - checkpoint_lsn
```

Nó ước lượng lượng redo đã được tạo kể từ mốc checkpoint gần nhất. Nếu redo log capacity là 1 GiB và checkpoint age là 300 MiB, khoảng cách đang sử dụng xấp xỉ 300 MiB. Đây là ví dụ đơn giản để hiểu quan hệ; không dùng phép tính này như một phép đo chính xác mọi byte file vật lý.

Khi checkpoint age tăng gần vùng redo capacity có thể sử dụng, InnoDB phải đẩy nhanh việc flush dirty pages để tạo khoảng trống tái sử dụng. Nếu tốc độ sinh redo liên tục cao hơn tốc độ flush data pages, hệ thống có thể xuất hiện:

- Adaptive flushing tăng cường độ ghi nền.
- I/O ghi data page tăng và ảnh hưởng latency của workload khác.
- Transaction ghi bị chậm hoặc phải chờ vì không gian redo sắp cạn.
- Throughput không ổn định khi workload ghi theo đợt.

Redo log capacity lớn hơn có thể hấp thụ burst dài hơn, nhưng không giải quyết được tình trạng storage không đủ tốc độ ghi cho workload ổn định. Nếu tốc độ sinh redo trung bình luôn cao hơn khả năng flush, checkpoint cuối cùng vẫn sẽ bị áp lực.

### 6.1. Ví dụ đọc checkpoint age

Giả sử trong một thời điểm đo:

```text
Current LSN:       1,200 MiB
Checkpoint LSN:      800 MiB
Redo capacity:     1,024 MiB
```

Checkpoint age xấp xỉ 400 MiB. Nếu workload tiếp tục tạo 100 MiB redo mỗi phút trong khi checkpoint chỉ tiến 60 MiB mỗi phút, khoảng cách tăng khoảng 40 MiB mỗi phút. Nếu xu hướng kéo dài, InnoDB sẽ phải tăng flush hoặc làm chậm writer để bảo vệ không gian redo.

Để đánh giá đúng, cần đo nhiều mẫu theo thời gian:

1. Lấy current LSN và checkpoint LSN.
2. Chờ một khoảng đo cố định.
3. Lấy lại hai giá trị.
4. Tính tốc độ redo sinh ra và tốc độ checkpoint tiến lên.
5. Đối chiếu với disk latency, dirty pages, throughput và commit latency.

Một giá trị checkpoint age cao trong lúc import lớn có thể là burst tạm thời; một xu hướng tăng kéo dài trong workload bình thường là dấu hiệu đáng điều tra.

## 7. Crash recovery sử dụng redo log như thế nào?

Khi MySQL khởi động sau crash, InnoDB cần đưa các page dữ liệu về trạng thái nhất quán. Ở mức khái niệm, quá trình gồm:

1. Xác định checkpoint gần nhất và đọc redo log từ vị trí cần thiết.
2. Phát lại các redo records cần thiết để đưa data pages về trạng thái đã ghi nhận trong log.
3. Xử lý các transaction chưa hoàn tất bằng undo information để rollback thay đổi chưa commit.
4. Hoàn tất các bước phục hồi cần thiết trước khi cho workload bình thường tiếp tục.

Redo phục vụ *roll forward*: tái áp dụng thay đổi đã được ghi log. Undo phục vụ *rollback*: hoàn tác thay đổi của transaction chưa commit và hỗ trợ MVCC. Hai cơ chế bổ sung cho nhau.

### 7.1. Vì sao redo log không cần chứa toàn bộ bảng?

Redo log lưu thông tin thay đổi theo page/record và metadata cần thiết để InnoDB tái áp dụng. Data files vẫn là nơi lưu trữ lâu dài của bảng và index. Redo log chỉ cần giữ phần thay đổi kể từ checkpoint còn cần cho recovery.

Khi checkpoint tiến, các redo records cũ có thể được tái sử dụng. Vì vậy redo log không phải một bản backup lịch sử đầy đủ của database.

### 7.2. Crash recovery và thời gian khởi động

Nếu checkpoint thường xuyên tiến gần current LSN, lượng redo cần xử lý sau crash thường nhỏ hơn so với trường hợp checkpoint tụt xa. Tuy nhiên, thời gian recovery còn phụ thuộc số dirty pages, kích thước database, storage throughput, transaction chưa hoàn tất và workload trước crash.

Không tăng redo capacity chỉ với mục tiêu “làm recovery nhanh hơn”. Capacity lớn có thể cho phép khoảng redo chưa checkpoint lớn hơn, làm phạm vi redo cần xử lý sau crash tăng trong một số tình huống. Hãy cân bằng burst tolerance, write throughput và mục tiêu recovery.

## 8. Redo log, undo log, binary log và doublewrite buffer

Các cơ chế này thường bị nhầm vì đều liên quan đến ghi dữ liệu và phục hồi.

| Cơ chế | Vai trò chính | Phạm vi |
| --- | --- | --- |
| Redo log | Phát lại thay đổi để phục hồi data pages sau crash | InnoDB/storage engine |
| Undo log | Hoàn tác transaction chưa commit, cung cấp phiên bản cũ cho MVCC | InnoDB/storage engine |
| Binary log (binlog) | Ghi nhận transaction/event cho replication và point-in-time recovery | MySQL server layer |
| Doublewrite buffer | Bảo vệ khỏi torn page khi ghi page không hoàn chỉnh | InnoDB page write path |

### 8.1. Redo và undo

Redo trả lời: “Làm thế nào để phát lại thay đổi cần thiết trên page?” Undo trả lời: “Làm thế nào để quay lại phiên bản trước hoặc rollback transaction chưa commit?”

Một transaction cập nhật hàng có thể tạo cả redo và undo information. Nếu transaction commit và server crash trước khi data page được flush, redo giúp khôi phục thay đổi đã commit. Nếu transaction chưa commit khi crash, recovery dùng undo để hủy thay đổi chưa hoàn tất.

### 8.2. Redo và binary log

Redo log được InnoDB dùng để crash recovery cho data pages. Binary log được MySQL dùng để ghi lại transaction/event phục vụ replication và point-in-time recovery. Khi bật binlog, MySQL phối hợp commit giữa storage engine và binary log bằng cơ chế two-phase commit để tránh trạng thái không nhất quán giữa hai luồng log.

Redo log không thay thế binlog cho replication; binlog cũng không thay thế redo log cho crash recovery của InnoDB.

### 8.3. Redo và doublewrite buffer

Redo log chứa thay đổi để phát lại. Doublewrite buffer bảo vệ việc ghi page khỏi tình huống page chỉ được ghi một phần (*torn page*). Nếu storage ghi page bị ngắt giữa chừng, bản page đầy đủ trong doublewrite area có thể được dùng để phục hồi page trước khi redo được áp dụng.

Hai cơ chế giải quyết hai vấn đề khác nhau và cùng góp phần bảo đảm tính bền vững dữ liệu.

## 9. Durability khi COMMIT: innodb_flush_log_at_trx_commit

`innodb_flush_log_at_trx_commit` điều khiển cách InnoDB ghi và flush redo log khi transaction commit.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'innodb_flush_log_at_timeout';
```

Các giá trị chính:

| Giá trị | Hành vi khi commit | Đánh đổi |
| --- | --- | --- |
| `1` | Ghi redo log và flush tới storage theo mỗi commit; mặc định | Durability mạnh nhất theo thiết kế thông thường, có thể tăng chi phí flush nhưng group commit giúp chia sẻ I/O |
| `2` | Ghi redo log ra file ở mỗi commit nhưng flush định kỳ, thường khoảng mỗi giây | Có thể mất transaction gần nhất khi OS crash hoặc mất điện trước flush; thường vẫn sống qua riêng tiến trình mysqld crash nếu OS còn hoạt động |
| `0` | Không yêu cầu ghi/flush redo tại từng commit; ghi và flush định kỳ, thường khoảng mỗi giây | Có thể mất transaction gần nhất khi mysqld crash, OS crash hoặc mất điện |

Flush định kỳ không phải cam kết chính xác từng giây; lịch flush và hành vi thực tế còn phụ thuộc hoạt động, scheduler, OS và storage. Giá trị `0`/`2` đánh đổi durability lấy khả năng giảm chi phí đồng bộ trong một số workload.

Với dữ liệu giao dịch quan trọng, thường giữ `innodb_flush_log_at_trx_commit = 1`. Không hạ xuống 0 hoặc 2 chỉ vì thấy commit chậm; trước tiên đo fsync latency, group commit, storage và transaction pattern.

### 9.1. Binlog và sync_binlog

Nếu bật binary log và cần độ bền vững giữa InnoDB và binlog, xem xét:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'sync_binlog';
```

`sync_binlog = 1` yêu cầu đồng bộ binlog tới storage theo mỗi commit (có thể được group commit gom chung). Một cấu hình thường dùng khi ưu tiên durability là:

```ini
innodb_flush_log_at_trx_commit = 1
sync_binlog = 1
```

Hai biến bảo vệ hai luồng log khác nhau. Chỉ đặt một biến thành 1 không thay thế việc đồng bộ luồng còn lại nếu hệ thống cần durability và replication/PITR nhất quán.

Độ bền thực tế vẫn phụ thuộc OS, filesystem, controller, thiết bị lưu trữ và việc chúng thực thi đúng lệnh flush/sync. Cache phần cứng không có bảo vệ mất điện có thể làm suy yếu giả định durability.

### 9.2. Group commit

Khi nhiều transaction commit gần nhau, MySQL có thể gom các yêu cầu flush log để nhiều transaction chia sẻ một lần đồng bộ storage. Đây là group commit. Nó giúp giảm số lần fsync trên mỗi transaction mà vẫn giữ chính sách durability.

Vì vậy, `innodb_flush_log_at_trx_commit = 1` không đồng nghĩa mỗi transaction luôn tạo một lệnh fsync riêng biệt. Hiệu năng commit phụ thuộc số transaction đồng thời, binlog group commit, latency storage và cách workload được tổ chức.

## 10. Cấu hình redo log capacity và log buffer

### 10.1. innodb_redo_log_capacity

`innodb_redo_log_capacity` xác định tổng dung lượng redo log mà InnoDB quản lý. Trên các phiên bản MySQL hỗ trợ biến này (từ 8.0.30), có thể thay đổi động ở phạm vi GLOBAL:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_redo_log_capacity';

-- Ví dụ đặt capacity thành 2 GiB; chỉ dùng sau khi đánh giá workload và disk.
SET GLOBAL innodb_redo_log_capacity = 2147483648;
```

Tăng capacity có thể:

- Cho phép hấp thụ burst ghi lâu hơn trước khi checkpoint phải bắt kịp.
- Giảm tần suất áp lực checkpoint trong workload ghi theo đợt.
- Tăng dung lượng disk dành cho redo log.
- Có thể làm phạm vi redo cần xử lý sau crash lớn hơn nếu checkpoint age tăng tương ứng.

Giảm capacity có thể buộc InnoDB flush dirty pages mạnh hơn để đưa checkpoint về vùng an toàn. Không thay đổi capacity liên tục theo cảm tính; đo redo rate, checkpoint age, dirty pages, I/O latency và dung lượng đĩa trước khi chọn giá trị.

### 10.2. innodb_log_buffer_size

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
```

Log buffer quá nhỏ có thể làm transaction lớn phải đẩy redo ra file nhiều lần trong khi transaction vẫn đang chạy. Tăng buffer có thể giúp transaction tạo nhiều redo giảm các lần ghi sớm, nhưng không giải quyết checkpoint pressure do capacity hoặc storage throughput không đủ.

Chỉ tăng khi có bằng chứng transaction lớn thường xuyên làm log buffer đầy hoặc gây ghi sớm đáng kể. Với workload thông thường, buffer mặc định có thể đã đủ.

### 10.3. Tốc độ flush và adaptive flushing

Các biến thường liên quan đến page flushing:

```sql
SHOW VARIABLES LIKE 'innodb_adaptive_flushing';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_io_capacity_max';
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct';
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct_lwm';
```

- `innodb_adaptive_flushing` cho phép InnoDB điều chỉnh tốc độ flush theo redo generation và checkpoint pressure.
- `innodb_io_capacity` định hướng năng lực I/O nền mà InnoDB có thể dùng cho các hoạt động như flushing.
- `innodb_io_capacity_max` đặt giới hạn cao hơn cho hoạt động I/O nền khi cần tăng tốc.
- Các ngưỡng dirty pages ảnh hưởng tới quyết định flush dựa trên tỷ lệ dirty pages trong buffer pool.

Các biến này không phải nút tăng tốc độc lập. Đặt quá thấp có thể làm checkpoint tụt lại; đặt quá cao có thể chiếm I/O của query foreground và các dịch vụ khác. Cần dựa vào khả năng thực tế của storage và đo latency toàn hệ thống.

## 11. Quan sát LSN và checkpoint

### 11.1. SHOW ENGINE INNODB STATUS

Lệnh hữu ích nhất để xem snapshot nội bộ của InnoDB:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `LOG`, tùy phiên bản có thể thấy các dòng như:

- `Log sequence number`
- `Log buffer assigned up to`
- `Log buffer completed up to`
- `Log written up to`
- `Log flushed up to`
- `Added dirty pages up to`
- `Pages flushed up to`
- `Last checkpoint at`

Đọc chúng để so sánh tiến độ tạo redo, ghi/flush redo và flush data pages. Các mốc không nhất thiết bằng nhau tại mọi thời điểm vì chúng đại diện các giai đoạn khác nhau của pipeline.

### 11.2. Status variables về LSN

Trên các phiên bản MySQL có cung cấp các status variables tương ứng, có thể truy vấn:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_lsn%';
```

Hoặc:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_lsn_current',
    'Innodb_lsn_flushed',
    'Innodb_lsn_last_checkpoint'
)
ORDER BY VARIABLE_NAME;
```

Tên và khả năng hiển thị status variables có thể khác giữa các bản phát hành; kiểm tra kết quả trên đúng server. Nếu biến không tồn tại, dùng các mốc trong `SHOW ENGINE INNODB STATUS`.

### 11.3. Lấy mẫu theo thời gian

Một snapshot chỉ cho biết trạng thái tại một thời điểm. Để xác định checkpoint có tụt lại hay không, lấy nhiều mẫu cách nhau một khoảng thời gian và ghi nhận:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Current LSN | Redo được sinh nhanh tới mức nào? |
| Flushed LSN | Redo writer/flush có theo kịp current LSN không? |
| Checkpoint LSN | Checkpoint tiến nhanh hay chậm? |
| Checkpoint age | Vùng redo đã dùng kể từ checkpoint tăng hay giảm? |
| Dirty pages | Buffer pool đang tích lũy bao nhiêu page chưa flush? |
| Disk write latency/IOPS | Storage có đủ năng lực ghi không? |
| Commit latency | Client có đang chờ flush redo/binlog không? |

Đối chiếu các chỉ số cùng thời điểm để phân biệt log flush bottleneck với data page flushing bottleneck.

## 12. Chẩn đoán checkpoint pressure

Checkpoint pressure xảy ra khi InnoDB không flush dirty pages đủ nhanh để tái sử dụng vùng redo log theo tốc độ workload tạo redo.

Các dấu hiệu cần kiểm tra:

- Checkpoint age tăng liên tục và tiến gần redo capacity.
- `Pages flushed up to` hoặc checkpoint LSN tiến chậm so với current LSN.
- I/O ghi data files tăng mạnh trong khi workload ghi cao.
- Latency của transaction ghi tăng không tương xứng với số lượng SQL.
- InnoDB tăng adaptive flushing hoặc writer phải chờ không gian redo.
- Dirty page ratio cao kéo dài, storage có queue/latency lớn.

Không kết luận chỉ từ một dấu hiệu. Ví dụ commit latency cao nhưng checkpoint age thấp có thể là redo fsync/binlog fsync chậm, không phải checkpoint pressure. Ngược lại, checkpoint age cao nhưng commit latency vẫn ổn trong một burst ngắn có thể chưa phải sự cố.

### 12.1. Quy trình điều tra

1. Xác nhận `innodb_redo_log_capacity`, `innodb_flush_log_at_trx_commit` và `sync_binlog`.
2. Lấy `SHOW ENGINE INNODB STATUS` và các LSN variables ở nhiều thời điểm.
3. Ước lượng redo generation rate và checkpoint advance rate.
4. Quan sát dirty pages, page cleaner activity, disk latency, IOPS và queue depth.
5. Xác định workload gây redo: batch update lớn, import, secondary index maintenance, transaction nhiều hàng hoặc một đợt ghi tăng đột biến.
6. Kiểm tra storage có bị chia sẻ với binlog, temporary files, backup hoặc workload khác không.
7. Thử điều chỉnh một biến trong môi trường kiểm thử hoặc cửa sổ vận hành có giám sát, sau đó so sánh trước/sau.

### 12.2. Hướng xử lý

- Tăng `innodb_redo_log_capacity` nếu vấn đề là burst ngắn và disk còn đủ dung lượng; capacity lớn hơn tạo thêm khoảng đệm.
- Cải thiện storage throughput/latency nếu tốc độ flush data pages không đáp ứng được workload ổn định.
- Điều chỉnh `innodb_io_capacity`/`innodb_io_capacity_max` theo khả năng I/O thực tế, tránh đẩy tải nền quá cao.
- Chia batch ghi lớn thành các transaction có kích thước hợp lý nếu nghiệp vụ cho phép, giảm burst và thời gian giữ lock.
- Giảm lượng cập nhật không cần thiết, tránh cập nhật cùng một hàng/index quá thường xuyên.
- Xem xét index và schema để giảm page modifications dư thừa, nhưng không bỏ index/constraint cần thiết cho tính đúng đắn.
- Giữ transaction ngắn và tránh để client bỏ quên transaction mở.

Không hạ `innodb_flush_log_at_trx_commit` như một cách chữa checkpoint pressure. Biến này liên quan durability của redo flush tại commit; checkpoint pressure chủ yếu liên quan tốc độ flush dirty pages và khả năng tái sử dụng redo space. Hai bottleneck có thể cùng xuất hiện nhưng không phải một vấn đề.

## 13. Redo log capacity và crash recovery: cân bằng thay vì tối đa hóa

Redo capacity quá nhỏ có thể khiến workload ghi burst thường xuyên đẩy checkpoint vào áp lực. Capacity quá lớn có thể:

- Dùng thêm dung lượng disk.
- Cho phép checkpoint age lớn hơn trước khi phải tăng flush.
- Làm lượng redo có thể cần quét khi crash lớn hơn, tùy vị trí checkpoint tại thời điểm crash.
- Che giấu storage throughput không đủ trong một khoảng thời gian.

Chọn capacity dựa trên:

- Tốc độ sinh redo cao điểm và trung bình.
- Thời lượng burst ghi thường gặp.
- Khả năng flush data pages của storage.
- Dung lượng disk và yêu cầu recovery time.
- Tỷ lệ dirty pages và pattern update.

Ví dụ, nếu workload có burst ghi 200 MiB redo trong 30 giây rồi trở về mức thấp, capacity lớn hơn có thể giúp InnoDB hấp thụ burst mà không phải flush quá gấp. Nếu workload tạo 200 MiB mỗi 30 giây liên tục trong khi storage chỉ flush được 100 MiB mỗi 30 giây, tăng capacity chỉ trì hoãn lúc áp lực xuất hiện; cần tăng khả năng ghi hoặc giảm redo generation.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ commit phải flush mọi data page | Hiểu sai vì sao redo log cần thiết | Phân biệt redo flush với data page flush |
| Nghĩ checkpoint là commit | Nhầm tiến độ ghi page với transaction state | Checkpoint là ranh giới redo có thể tái sử dụng |
| Nhầm redo log với undo log | Không hiểu crash recovery và MVCC | Redo roll forward; undo rollback và dựng phiên bản cũ |
| Nhầm redo log với binlog | Kỳ vọng redo phục vụ replication/PITR | Dùng redo cho InnoDB recovery, binlog cho replication/PITR |
| Chỉ tăng redo capacity khi checkpoint age tăng | Che giấu storage throughput thiếu | So sánh redo rate với checkpoint advance và disk capacity |
| Hạ flush-at-commit để chữa checkpoint pressure | Đánh đổi durability nhưng không giải quyết page flushing | Xác định bottleneck redo fsync hay checkpoint/data page flush |
| Tăng log buffer để xử lý mọi vấn đề redo | Không giải quyết capacity/checkpoint pressure | Chỉ tăng khi transaction lớn làm log buffer đầy |
| Đọc một snapshot LSN rồi kết luận | Bỏ qua xu hướng và workload | Lấy mẫu theo thời gian và đối chiếu I/O |
| Xóa hoặc sửa redo files thủ công | Có thể làm hỏng khả năng recovery | Để InnoDB quản lý redo files |
| Nghĩ capacity càng lớn càng tốt | Tăng disk usage và có thể tăng recovery work | Cân bằng burst, throughput và RTO |

## 15. Bài tập thực hành

1. Chạy `SHOW VARIABLES LIKE 'innodb_redo_log_capacity'` và `SHOW VARIABLES LIKE 'innodb_log_buffer_size'`. Ghi nhận cấu hình server lab.
2. Chạy `SHOW ENGINE INNODB STATUS\G`; tìm current LSN, flushed LSN, pages flushed và last checkpoint.
3. Nếu server cung cấp `Innodb_lsn_current`, `Innodb_lsn_flushed` và `Innodb_lsn_last_checkpoint`, lấy hai mẫu cách nhau 30 giây và tính redo generation/checkpoint advance rate.
4. Tạo workload cập nhật nhiều hàng trong bảng lab, quan sát current LSN và checkpoint LSN thay đổi.
5. So sánh một transaction lớn với nhiều transaction nhỏ có tổng số hàng cập nhật tương đương. Quan sát redo rate, commit latency và dirty pages.
6. Thử tăng `innodb_redo_log_capacity` trong môi trường lab có đủ disk. Quan sát checkpoint pressure và dung lượng redo files; khôi phục cấu hình sau thử nghiệm nếu cần.
7. So sánh cấu hình `innodb_flush_log_at_trx_commit` trong môi trường kiểm thử, không dùng dữ liệu cần durability. Giải thích rủi ro của giá trị 0, 1 và 2.
8. Nếu binlog bật, kiểm tra `sync_binlog` và giải thích vì sao redo flush và binlog sync là hai luồng riêng.
9. Đọc `SHOW ENGINE INNODB STATUS` để phân biệt log flush lag với checkpoint lag.
10. Viết một báo cáo ngắn: workload tạo redo bao nhiêu mỗi giây, checkpoint tiến bao nhiêu mỗi giây, storage có đủ năng lực không và thay đổi nào nên thử trước.

## 16. Checklist vận hành redo log và checkpoint

- [ ] Đã hiểu redo log bảo vệ thay đổi trước khi data page được flush.
- [ ] WAL được bảo đảm: redo cần thiết được ghi trước dirty page tương ứng.
- [ ] Đã phân biệt redo log buffer, redo log files và buffer pool dirty pages.
- [ ] Đã hiểu current, written, flushed, checkpoint và page LSN.
- [ ] Đã biết checkpoint không đồng nghĩa commit hoặc flush toàn bộ buffer pool.
- [ ] Đã theo dõi checkpoint age theo thời gian, không dựa vào một snapshot.
- [ ] Đã kiểm tra `innodb_redo_log_capacity` và `innodb_log_buffer_size` theo đúng bottleneck.
- [ ] Đã xác định durability cần thiết trước khi đổi `innodb_flush_log_at_trx_commit`.
- [ ] Nếu bật binlog, đã đánh giá `sync_binlog` cùng chính sách redo flush.
- [ ] Đã đối chiếu redo generation với checkpoint advance và storage throughput.
- [ ] Đã đánh giá tác động dung lượng redo tới burst tolerance và recovery time.
- [ ] Không thao tác thủ công trên redo log files khi server đang chạy.
- [ ] Có kế hoạch đo trước/sau cho mọi thay đổi cấu hình.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể mô tả đường đi của thay đổi từ buffer pool tới redo log và data file, giải thích WAL, LSN, page LSN và fuzzy checkpoint, tính checkpoint age từ các mốc LSN, phân biệt redo/undo/binlog/doublewrite, chọn được chính sách flush phù hợp với yêu cầu durability và chẩn đoán được checkpoint pressure bằng dữ liệu quan sát theo thời gian.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — InnoDB Redo Log](https://dev.mysql.com/doc/refman/8.4/en/innodb-redo-log.html)
- [MySQL 8.4 Reference Manual — Configuring InnoDB Redo Logging](https://dev.mysql.com/doc/refman/8.4/en/innodb-redo-log.html#innodb-redo-log-configuration)
- [MySQL 8.4 Reference Manual — InnoDB Parameters](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual — Binary Log Group Commit](https://dev.mysql.com/doc/refman/8.4/en/replication-features-transactional.html)
