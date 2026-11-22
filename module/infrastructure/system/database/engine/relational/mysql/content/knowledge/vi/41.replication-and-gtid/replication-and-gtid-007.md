# GTID auto-position và điều kiện thay thế replica

Trong MySQL replication, replica cần biết phải lấy các giao dịch nào từ source để bắt kịp dữ liệu. Với cách replication truyền thống, người vận hành cấu hình tên binary log file và vị trí byte. Khi dùng **GTID auto-position**, trong lần bắt tay kết nối replica gửi GTID set đại diện cho các giao dịch nó đã nhận, đã commit hoặc cả hai; source xác định các giao dịch còn thiếu và gửi phần có thể cung cấp. Cách này giúp việc đổi source hoặc thay thế replica dễ kiểm soát hơn, vì không phải tự tính lại file/position.

GTID auto-position không tự sửa dữ liệu sai, không khôi phục những giao dịch đã bị purge khỏi mọi source khả dụng và cũng không quyết định replica nào an toàn để promote. Muốn thay một replica hoặc chuyển vai trò primary, cần kiểm tra lịch sử giao dịch, binary log còn lưu, tính nhất quán dữ liệu và nguy cơ split-brain.

Bài học này sử dụng thuật ngữ `SOURCE` và `REPLICA` của MySQL 8.0.23 trở lên. Trên phiên bản cũ hơn, một số câu lệnh vẫn dùng tên `MASTER` và `SLAVE`, chẳng hạn `CHANGE MASTER TO` và `SHOW SLAVE STATUS`.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích GTID, GTID set và cơ chế auto-position.
- Xác định các điều kiện cần có để bật GTID replication.
- Dùng `gtid_executed`, `gtid_purged`, `GTID_SUBSET()` và `GTID_SUBTRACT()` để so sánh lịch sử giao dịch.
- Nhận biết tình huống source đã purge giao dịch replica cần hoặc replica có errant transaction.
- Thay source cho một replica và đánh giá điều kiện an toàn khi thay thế hoặc promote replica.

## 1. GTID và GTID set

GTID (Global Transaction Identifier) là định danh của một giao dịch được ghi vào binary log. Dạng thông dụng là:

```text
source_uuid:transaction_id
```

Ví dụ:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:125
```

Phần UUID nhận diện máy chủ đã tạo giao dịch; phần số thứ tự nhận diện giao dịch trong lịch sử của UUID đó. Một GTID chỉ định danh một giao dịch. Một **GTID set** là tập hợp một hoặc nhiều GTID, thường được biểu diễn bằng UUID cùng các khoảng số thứ tự:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:1-125,
24BC7850-2C16-11E8-A6A5-FA163E3D9B3B:1-48:52-60
```

Khoảng `1-125` đại diện cho các GTID từ 1 đến 125 của UUID tương ứng. Ví dụ thứ hai có hai khoảng, trong đó số 49 đến 51 không có trong tập. GTID set không phải danh sách vị trí byte trong binlog và không thể so sánh bằng cách sắp xếp chuỗi đơn giản.

### 1.1. Các GTID set quan trọng

| Biến | Ý nghĩa |
|---|---|
| `gtid_executed` | Tập GTID của các giao dịch đã được thực thi trên server, bao gồm lịch sử có thể không còn nằm trong các binary log hiện tại |
| `gtid_purged` | Tập GTID của các giao dịch đã bị purge khỏi binary log trên server |
| `Retrieved_Gtid_Set` | Trong trạng thái replication, tập GTID receiver đã lấy từ source và lưu trong relay log, chờ hoặc đang được applier xử lý |
| `Executed_Gtid_Set` | Trong trạng thái replication, tập GTID server đã thực thi; đây cũng là lịch sử được phản ánh bởi `gtid_executed` |

Kiểm tra GTID set trên một server:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_mode,
  @@GLOBAL.enforce_gtid_consistency,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
```

`gtid_executed` cho biết server từng thực thi giao dịch nào. `gtid_purged` giúp xác định phần lịch sử đã bị xóa khỏi binary log của server. Một giao dịch có trong `gtid_executed` không có nghĩa server vẫn còn file log để truyền giao dịch đó cho replica.

## 2. GTID auto-position hoạt động như thế nào?

Khi replica kết nối bằng `SOURCE_AUTO_POSITION=1`, replica gửi GTID set đại diện cho các giao dịch đã nhận, đã commit hoặc cả hai. Source so sánh tập này với các giao dịch đang có trong binary log và gửi những giao dịch chưa được replica ghi nhận. Nhờ vậy, một giao dịch đã được nhận vào relay log nhưng chưa commit cũng không bị gửi lại như thể replica chưa từng nhận nó.

Luồng khái quát:

```text
Replica kết nối source
          |
          v
Gửi tập GTID đã nhận/commit
          |
          v
Source so sánh GTID set
          |
          v
Xác định giao dịch còn thiếu
          |
          v
Gửi giao dịch từ binary log
          |
          v
Replica ghi relay log
          |
          v
Applier thực thi giao dịch
          |
          v
Cập nhật GTID đã thực thi
```

Ví dụ: source đã thực thi các GTID `uuid-A:1-120`, còn replica đã thực thi `uuid-A:1-100`. Nếu source vẫn giữ binary log chứa các GTID 101-120, source có thể gửi phần còn thiếu. Replica không cần biết giao dịch 101 bắt đầu ở file nào hoặc byte offset nào.

Để dùng cơ chế này, cả source và replica phải được cấu hình cho GTID replication. Source cần binary logging và phải giữ các binary log chứa giao dịch replica còn thiếu. Replica cần kết nối được, có quyền replication, và có GTID set phản ánh đúng lịch sử dữ liệu đã được nạp vào nó. Trong topology nhiều source hoặc diamond, GTID auto-skip giúp tránh áp dụng một giao dịch nhiều lần khi giao dịch đó đã đến replica qua một đường khác.

## 3. Điều kiện cấu hình GTID replication

### 3.1. Bật GTID mode và enforce consistency

Với topology GTID ổn định, các server tham gia cần có:

- `gtid_mode=ON` để giao dịch được quản lý bằng GTID.
- `enforce_gtid_consistency=ON` để MySQL ngăn các thao tác không tương thích với GTID consistency.
- Binary logging bật trên source (`log_bin=ON`).
- `server_id` khác 0 và duy nhất trong topology.
- `server_uuid` duy nhất trên từng instance.

Trong giai đoạn chuyển đổi, MySQL cho phép replica ở `gtid_mode=ON_PERMISSIVE` hoặc `OFF_PERMISSIVE` trong khi source phải ở `gtid_mode=ON`. Đây là các trạng thái chuyển tiếp theo quy trình nâng cấp/chuyển đổi GTID; với topology đã hoàn tất, đặt `gtid_mode=ON` trên các server tham gia.

Kiểm tra cấu hình:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'gtid_mode',
  'enforce_gtid_consistency',
  'log_bin',
  'server_id',
  'server_uuid',
  'log_replica_updates'
);
```

Việc chuyển một hệ thống đang chạy từ GTID OFF sang ON cần thực hiện theo quy trình chuyển đổi nhiều giai đoạn được MySQL hỗ trợ. Không nên đổi `gtid_mode` tùy tiện trên một node trong topology đang hoạt động. Trước khi bật GTID, cần kiểm tra ứng dụng và các câu lệnh có thể vi phạm GTID consistency, sau đó triển khai đồng bộ theo kế hoạch.

`server_uuid` thường được lưu trong file `auto.cnf` do MySQL tạo. Khi tạo replica bằng cách sao chép filesystem của một server, phải bảo đảm instance mới có UUID riêng; hai server dùng cùng UUID sẽ làm lịch sử GTID không còn đáng tin cậy.

### 3.2. Binary log và log_replica_updates

Source phải bật binary log và giữ log đủ lâu để replica có thể lấy các giao dịch còn thiếu. Nếu một replica trung gian sẽ phục vụ các replica phía sau, cần bật `log_replica_updates=ON` để các giao dịch nó nhận từ upstream cũng được ghi vào binary log cục bộ. Nếu không, node trung gian có thể không có đầy đủ log để downstream replica lấy giao dịch qua GTID auto-position.

`log_replica_updates` không tự tạo dữ liệu còn thiếu và cũng không thay thế việc giữ binary log. Hãy kiểm tra cả chính sách purge, dung lượng đĩa, backup binlog và thời gian replica có thể bị ngắt kết nối.

### 3.3. Quyền kết nối và bảo vệ replica

Tài khoản replication cần quyền replication phù hợp trên source, được giới hạn host và sử dụng TLS theo chính sách bảo mật. Ví dụ tạo tài khoản trên source:

```sql
CREATE USER 'repl'@'10.20.0.12'
  IDENTIFIED BY '<mat-khau-tu-secret-manager>'
  REQUIRE SSL;

GRANT REPLICATION SLAVE
  ON *.*
  TO 'repl'@'10.20.0.12';
```

Tên privilege trong câu lệnh trên là tên được dùng phổ biến cho MySQL 8.0; hãy kiểm tra yêu cầu quyền và tên tương thích của đúng phiên bản đang chạy. Không đặt mật khẩu thật trong script được commit vào source control.

Trên replica, thường bật `read_only=ON` và `super_read_only=ON` để giảm nguy cơ ghi nhầm vào replica. Tài khoản replication applier vẫn có thể áp dụng thay đổi theo cơ chế nội bộ của MySQL. Việc bảo vệ này cần kết hợp phân quyền tài khoản, giám sát và kiểm soát thao tác vận hành.

## 4. Cấu hình auto-position

Giả sử replica đã được nạp dữ liệu từ một bản backup nhất quán, có GTID set phù hợp và cần kết nối tới source `db-source.example`:

```sql
STOP REPLICA;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'db-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = '<mat-khau-tu-secret-manager>',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

`CHANGE REPLICATION SOURCE TO` với `SOURCE_AUTO_POSITION=1` chỉ được chạy khi cả receiver thread và applier thread đã dừng; `STOP REPLICA` ở đầu ví dụ dừng cả hai. Khi dùng auto-position, không cấu hình `SOURCE_LOG_FILE`, `SOURCE_LOG_POS`, `RELAY_LOG_FILE` hoặc `RELAY_LOG_POS` trong cùng cấu hình kết nối. MySQL tự xác định giao dịch cần lấy dựa trên GTID set. Thực hiện thay đổi endpoint và thông tin xác thực qua quy trình bảo mật của hệ thống; ví dụ trên chỉ minh họa câu lệnh.

Kiểm tra trạng thái:

```sql
SHOW REPLICA STATUS\G
```

Các trường cần quan sát gồm:

- `Source_Host`: source mà replica đang kết nối.
- `Auto_Position`: xác nhận cơ chế auto-position được bật.
- `Replica_IO_Running` và `Replica_SQL_Running`: receiver và applier có đang chạy hay không.
- `Last_IO_Error` và `Last_SQL_Error`: lỗi gần nhất của hai luồng.
- `Retrieved_Gtid_Set`: các GTID đã nhận về relay log.
- `Executed_Gtid_Set`: các GTID đã thực thi trên replica.

Tên trường có thể khác đôi chút giữa các phiên bản. Hai thread chạy không có nghĩa replica đã bắt kịp hoàn toàn; cần so sánh GTID set, kiểm tra lỗi và đo độ trễ thực tế.

## 5. So sánh GTID set trước khi thay thế replica

GTID set giúp kiểm tra lịch sử giao dịch, nhưng cần đặt phép so sánh đúng theo mục tiêu. Có hai câu hỏi khác nhau:

1. **Replica có thể nối vào source này không?** Source cần chứa mọi GTID replica đã thực thi, và cần còn binary log cho các GTID replica chưa có.
2. **Replica có thể thay thế primary cũ không?** Candidate cần chứa mọi GTID đã commit trên primary cũ mà tổ chức muốn bảo toàn. Đây là điều kiện về mức độ cập nhật trước khi promote.

### 5.1. Kiểm tra replica có GTID lạ hay không

Trong topology single-source đơn giản, khi định nối candidate vào source, tập GTID đã thực thi của candidate nên là tập con của tập GTID đã thực thi trên source. Trên source, thay các placeholder bằng GTID set đã đọc từ candidate và source:

```sql
SELECT GTID_SUBSET(
  '<candidate_gtid_executed>',
  '<source_gtid_executed>'
) AS candidate_history_is_known_by_source;
```

Kết quả `1` nghĩa là mọi GTID của candidate cũng có trong lịch sử đã thực thi của source. Kết quả `0` cho thấy candidate có ít nhất một GTID mà source không có. Trong topology single-source, đây là dấu hiệu cần điều tra vì có thể là **errant transactions**: giao dịch được ghi trực tiếp trên replica hoặc đến từ một lịch sử không tương thích. Trong multi-source/diamond, GTID đến từ source khác có thể hợp lệ; cần so sánh với lịch sử của toàn bộ topology dự kiến, không kết luận mọi GTID ngoài một source đều là errant.

Để xem chính xác phần GTID lạ:

```sql
SELECT GTID_SUBTRACT(
  '<candidate_gtid_executed>',
  '<source_gtid_executed>'
) AS errant_gtids;
```

Kết quả rỗng là điều kiện cần để lịch sử candidate nằm trong lịch sử của source đơn lẻ. Nếu có GTID ngoài tập này, cần xác định giao dịch đã tạo ra nó và đối chiếu với các source khác trong topology. Đặc biệt, nếu replica có GTID thuộc UUID của source mà source không có, auto-position có thể dừng với lỗi `ER_REPLICA_HAS_MORE_GTIDS_THAN_SOURCE`. Tình huống này cũng có thể cho thấy phần cuối binary log của source bị mất hoặc truncate sau sự cố; hãy kiểm tra error log, trạng thái crash recovery và cấu hình đồng bộ binlog. Không tự ý xóa GTID khỏi `gtid_executed` hoặc chèn một giao dịch rỗng để làm cho phép so sánh có vẻ hợp lệ.

### 5.2. Kiểm tra source còn giữ các giao dịch candidate cần

Tính tập giao dịch source đã thực thi nhưng candidate chưa có:

```sql
SELECT GTID_SUBTRACT(
  '<source_gtid_executed>',
  '<candidate_gtid_executed>'
) AS transactions_candidate_needs;
```

Nếu tập này không rỗng, candidate cần lấy các GTID đó từ source. Tiếp theo, kiểm tra xem có GTID nào trong tập cần lấy đã bị purge khỏi binary log của source hay không:

```sql
SET @candidate_missing = GTID_SUBTRACT(
  '<source_gtid_executed>',
  '<candidate_gtid_executed>'
);

SELECT @candidate_missing AS transactions_candidate_needs,
       GTID_SUBTRACT(
         @candidate_missing,
         @@GLOBAL.gtid_purged
       ) AS needed_gtids_not_purged,
       GTID_SUBTRACT(
         @candidate_missing,
         GTID_SUBTRACT(@candidate_missing, @@GLOBAL.gtid_purged)
       ) AS needed_gtids_already_purged;
```

`needed_gtids_not_purged` là phần GTID candidate cần mà source chưa ghi nhận đã purge; `needed_gtids_already_purged` là phần candidate cần nhưng đã nằm trong `gtid_purged`. Nếu tập cần lấy không rỗng và `needed_gtids_already_purged` cũng không rỗng, source đã purge ít nhất một giao dịch candidate cần. Auto-position không thể yêu cầu source gửi lại giao dịch đã bị xóa khỏi các binary log mà source còn giữ. Nếu có GTID cần lấy chưa bị purge, vẫn phải xác minh source thực sự có binary log tương ứng, đặc biệt khi source là replica trung gian và `log_replica_updates` không được bật.

Một cách kiểm tra khác là đối chiếu phần giao giữa tập GTID cần lấy và `gtid_purged`. Kết quả này chỉ phản ánh lịch sử trên source đang kiểm tra; một source khác hoặc backup binlog có thể vẫn còn dữ liệu cần thiết.

### 5.3. Ví dụ hai replica có mức cập nhật khác nhau

Giả sử primary cũ đã commit GTID `uuid-P:1-500`. Replica A đã thực thi `uuid-P:1-500`, còn replica B mới thực thi `uuid-P:1-470`.

- A có thể là candidate thay thế primary cũ về mặt GTID vì A đã thực thi toàn bộ lịch sử `uuid-P:1-500`.
- B còn thiếu 30 giao dịch. B chỉ có thể bắt kịp từ primary cũ nếu binary log của primary còn chứa các GTID 471-500, hoặc từ một source khác có đủ các giao dịch đó.
- Nếu primary cũ đã purge `uuid-P:471-500` và không còn nguồn log/backup nào khác, B không thể tự bắt kịp chỉ bằng auto-position.

Đây là phép so sánh lịch sử GTID. Trước khi promote A, vẫn phải xác nhận dữ liệu, trạng thái ứng dụng, các giao dịch chưa được replicate và việc primary cũ đã bị fence để tránh hai primary cùng nhận ghi.

## 6. Điều kiện thay thế một replica

Thay một replica là tạo hoặc chọn một server mới để đảm nhận vai trò replica của source hiện tại. Mục tiêu là để server mới có cùng baseline dữ liệu và có thể lấy đủ phần giao dịch còn thiếu.

### 6.1. Baseline dữ liệu phải nhất quán

Candidate nên được tạo từ backup nhất quán, MySQL Clone Plugin hoặc quy trình provisioning đã được kiểm chứng. GTID set đi kèm backup phải phản ánh chính xác trạng thái dữ liệu được chụp. Nếu chỉ sao chép file dữ liệu khi server đang thay đổi mà không có cơ chế đảm bảo nhất quán, GTID set có thể không đại diện cho dữ liệu thực tế.

Khi chuẩn bị candidate, xác nhận:

- Phiên bản MySQL, storage engine, schema và cấu hình tương thích với source.
- Dữ liệu được seed từ một snapshot nhất quán, có checkpoint/GTID set được ghi nhận.
- `server_id` và `server_uuid` là duy nhất.
- GTID mode và consistency phù hợp với topology.
- Binary log và `log_replica_updates` được bật nếu candidate sẽ làm source trung gian cho replica khác.
- Có đủ dung lượng cho relay log, binary log, temporary files và hoạt động bình thường.

### 6.2. Source phải cung cấp được phần giao dịch còn thiếu

Sau khi nạp backup, lấy `gtid_executed` của candidate và source. Dùng `GTID_SUBTRACT(source_set, candidate_set)` để xác định phần candidate còn thiếu. Kiểm tra các GTID đó chưa bị purge khỏi binary log của source.

Nếu source đã purge GTID cần thiết, có ba hướng xử lý:

1. Tìm một replica hoặc source khác vẫn giữ đủ binary log để candidate lấy phần còn thiếu.
2. Dùng backup mới hơn có GTID checkpoint phù hợp, rồi nạp lại candidate.
3. Nếu không có nguồn log phù hợp, tạo lại candidate từ một snapshot nhất quán mới và cấu hình replication từ snapshot đó.

Không bỏ qua GTID chỉ để làm replication chạy tiếp. Bỏ qua giao dịch có thể tạo chênh lệch dữ liệu mà GTID status không còn giúp phát hiện đơn giản.

### 6.3. Kết nối candidate bằng auto-position

Sau khi xác minh lịch sử GTID và baseline dữ liệu, cấu hình endpoint source mới bằng `SOURCE_AUTO_POSITION=1`, khởi động replica và theo dõi receiver/applier. Chỉ đưa candidate vào phục vụ workload sau khi đã xác nhận bắt kịp, không có lỗi replication và dữ liệu quan trọng được đối chiếu.

Nếu sử dụng replication channel có tên hoặc multi-source replication, hãy chỉ rõ đúng channel khi dừng, thay đổi source và kiểm tra trạng thái. Không thay đổi cấu hình của channel khác trong cùng instance.

## 7. Điều kiện promote replica thành primary

Promote replica là chuyển một replica thành source nhận ghi. Đây là thao tác failover có rủi ro cao hơn việc thay replica thông thường, vì phải xác định dữ liệu nào đã được commit trên primary cũ và ngăn primary cũ tiếp tục nhận ghi.

### 7.1. Chọn candidate có lịch sử đầy đủ nhất

Nếu primary cũ còn truy cập được, lấy GTID set đã commit trên primary và so sánh với candidate:

```sql
SELECT GTID_SUBSET(
  '<old_primary_gtid_executed>',
  '<candidate_gtid_executed>'
) AS candidate_contains_old_primary_history;
```

Kết quả `1` cho biết candidate đã thực thi mọi GTID trong tập của primary cũ. Kết quả `0` nghĩa là candidate còn thiếu giao dịch. Nếu primary cũ đã ngừng hoạt động đột ngột và không thể đọc GTID set cuối cùng, cần dùng thông tin từ các replica, binlog được lưu trữ, log ứng dụng và chính sách RPO để xác định phần giao dịch có thể đã mất.

Phép kiểm tra này chỉ chứng minh candidate chứa lịch sử của primary cũ. Cần kiểm tra thêm GTID lạ của candidate:

```sql
SELECT GTID_SUBTRACT(
  '<candidate_gtid_executed>',
  '<old_primary_gtid_executed>'
) AS candidate_extra_gtids;
```

Nếu `candidate_extra_gtids` không rỗng, điều tra từng giao dịch trước khi promote. Trong topology single-source, đây có thể là giao dịch ghi riêng trên candidate; trong topology multi-source, một số GTID ngoài primary cũ có thể đến từ source hợp lệ khác. Không nên coi candidate là bản thay thế nhất quán chỉ vì nó có toàn bộ GTID của primary cũ; phải phân loại phần GTID bổ sung và đối chiếu dữ liệu.

Trong asynchronous replication, một giao dịch được client xác nhận trên primary có thể chưa kịp tới replica trước khi primary hỏng. Vì vậy, promote một replica chưa bắt kịp có thể làm mất các giao dịch đã được xác nhận. GTID giúp đo lịch sử đã nhận, nhưng không thể phục hồi giao dịch mà không replica nào hoặc backup nào còn giữ.

### 7.2. Fence primary cũ để tránh split-brain

Trước khi cho candidate nhận ghi, phải bảo đảm primary cũ không thể tiếp tục nhận ghi từ ứng dụng hoặc từ node khác. Tùy hạ tầng, việc fence có thể gồm dừng dịch vụ MySQL, chặn kết nối ghi ở mạng/proxy, thu hồi quyền ghi hoặc cơ chế điều phối HA. Chỉ đặt `read_only` không phải lúc nào cũng đủ nếu còn tài khoản có thể ghi hoặc cơ chế failover khác có thể đưa node cũ trở lại.

Sau khi primary cũ đã được fence, kiểm tra candidate, cấu hình read-only theo quy trình promote, cập nhật endpoint ghi của ứng dụng và cấu hình các replica còn lại trỏ tới primary mới bằng GTID auto-position. Không mở ghi trên hai node cùng lúc.

### 7.3. Đánh giá candidate khi primary cũ không còn

Khi không thể lấy GTID set cuối cùng từ primary cũ, hãy so sánh `gtid_executed` của tất cả replica có thể truy cập. Candidate có tập GTID lớn nhất thường có nhiều giao dịch nhất, nhưng phép so sánh phải xét cả các UUID và phần GTID lạ. Hai tập có thể không phải quan hệ subset; số lượng GTID lớn hơn không tự chứng minh candidate chứa toàn bộ lịch sử hợp lệ.

Nếu các replica có các GTID khác nhau, hãy tìm nguồn gốc từng tập và xác định có giao dịch ghi trực tiếp trên replica hay không. Không gộp lịch sử một cách máy móc. Chọn candidate theo tính đầy đủ của giao dịch, tính nhất quán dữ liệu và RPO đã chấp nhận; sau đó ghi nhận rõ các giao dịch có thể bị mất.

## 8. Lỗi thường gặp khi auto-position

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Source đã purge GTID replica cần (`ER_SOURCE_HAS_PURGED_REQUIRED_GTIDS`) | Binary log cần thiết không còn trên source | Dùng source khác còn log hoặc seed lại từ backup mới hơn |
| Replica có GTID thuộc UUID của source mà source không có | Có thể do ghi ngoài replication hoặc phần cuối binary log của source bị mất/truncate sau sự cố | Kiểm tra error log và crash recovery, xác định GTID nào đã commit thực sự, rồi đối chiếu dữ liệu trước khi sửa topology |
| Receiver không kết nối được | Host, port, tài khoản, TLS, firewall hoặc quyền replication sai | Kiểm tra `Last_IO_Error`, thông tin kết nối và quyền trên source |
| Applier dừng | Lỗi dữ liệu, schema, transaction hoặc cấu hình replication | Kiểm tra `Last_SQL_Error`, xác định giao dịch lỗi và xử lý theo quy trình phục hồi |
| Replica không bắt kịp | Thiếu tài nguyên, transaction lớn, I/O chậm hoặc source tải cao | Theo dõi receiver/applier, disk, CPU, transaction apply và replica lag |
| UUID bị trùng | Clone/copy instance không tạo `server_uuid` mới | Dừng topology liên quan và sửa identity theo quy trình MySQL được hỗ trợ |

Khi source báo không thể gửi GTID cần thiết vì đã purge, không dùng thao tác skip transaction để che lỗi. Khi replica có GTID lạ, không xóa metadata GTID để ép kết nối. Hai tình huống này đòi hỏi điều tra lịch sử và dữ liệu trước khi tiếp tục.

## 9. Checklist thay thế replica

Trước khi chuyển vai trò, thực hiện các bước theo thứ tự:

1. Xác định mục tiêu: thay một replica bị lỗi, reparent replica sang source khác hay promote replica thành primary.
2. Ghi lại phiên bản MySQL, `server_id`, `server_uuid`, `gtid_mode`, `enforce_gtid_consistency`, `gtid_executed` và `gtid_purged` của các node liên quan.
3. Xác nhận backup hoặc clone dùng để seed candidate là nhất quán và GTID checkpoint khớp với dữ liệu.
4. So sánh GTID set để phát hiện giao dịch thiếu và errant GTID.
5. Xác nhận source còn giữ mọi GTID candidate cần, hoặc có source/backup khác cung cấp được chúng.
6. Kiểm tra replication user, host, TLS, quyền và `SOURCE_AUTO_POSITION`.
7. Khởi động replication, kiểm tra receiver/applier, lỗi và GTID set cho đến khi candidate bắt kịp.
8. Nếu promote, fence primary cũ trước khi mở ghi trên candidate; đánh giá giao dịch chưa replicate theo RPO.
9. Reparent các replica còn lại sang source mới bằng GTID auto-position và theo dõi toàn topology.
10. Kiểm tra dữ liệu ứng dụng, backup, binlog retention và khả năng PITR sau thay đổi.

Checklist này là khung kiểm tra kỹ thuật. Mỗi môi trường cần gắn nó với cơ chế HA, quy trình phê duyệt thay đổi và phương án rollback cụ thể.

## 10. Bài thực hành

Một topology có primary `db-a` và hai replica `db-b`, `db-c`. Cả ba server bật GTID mode. `db-a` gặp sự cố; `db-b` đã thực thi GTID `uuid-a:1-900`, còn `db-c` đã thực thi `uuid-a:1-875` và có thêm `uuid-c:1-3` do một lần ghi trực tiếp ngoài replication.

Hãy xử lý các yêu cầu sau:

1. Viết câu lệnh dùng `GTID_SUBSET()` và `GTID_SUBTRACT()` để xác định `db-c` có GTID lạ so với `db-a` hay không, giả sử bạn có GTID set cuối cùng của `db-a`.
2. Nếu `db-a` còn binary log chứa `uuid-a:876-900`, điều kiện nào cho phép `db-c` bắt kịp bằng auto-position sau khi xử lý GTID lạ?
3. Nếu các binary log chứa GTID 876-900 đã bị purge và không có bản backup binlog, bạn sẽ chọn phương án nào để thay thế `db-c`?
4. Nếu `db-a` không thể khôi phục, `db-b` là candidate promote. Bạn cần xác minh điều gì về giao dịch đã commit, RPO và khả năng fence `db-a`?
5. Sau khi promote `db-b`, cần kiểm tra và thay đổi những gì trên `db-c` để nó trở thành replica của primary mới?
6. Vì sao `db-b` có nhiều GTID hơn không tự động chứng minh nó là candidate an toàn nếu tập GTID của nó chứa giao dịch lạ?

Một phương án tốt phải phân biệt rõ phần GTID thiếu, phần GTID lạ, binary log còn giữ và trạng thái dữ liệu thực tế. Hãy ghi lại kết quả kiểm tra trước khi thay đổi topology.

## Kết luận

GTID auto-position giúp MySQL tìm giao dịch replica còn thiếu dựa trên lịch sử GTID, nhờ đó đơn giản hóa việc kết nối lại và reparent. Điều kiện quan trọng là các server có GTID configuration tương thích, identity duy nhất, dữ liệu seed nhất quán và source còn giữ binary log cần thiết. Khi thay replica, phải phát hiện GTID lạ và GTID đã purge; khi promote, phải xác nhận candidate chứa đủ giao dịch cần bảo toàn và fence primary cũ để tránh split-brain. GTID set là bằng chứng về lịch sử giao dịch mà server ghi nhận, còn tính đúng đắn cuối cùng vẫn cần được xác minh trên dữ liệu và quy trình vận hành thực tế.
