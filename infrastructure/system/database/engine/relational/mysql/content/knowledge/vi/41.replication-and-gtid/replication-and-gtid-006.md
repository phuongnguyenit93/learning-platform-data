# `gtid_executed`, `gtid_purged` và quan hệ với backup

Trong MySQL dùng GTID, mỗi transaction được nhận diện bằng một mã duy nhất có dạng `source_uuid:transaction_number`. Tập GTID giúp server và replica biết transaction nào đã được thực thi, transaction nào còn cần truyền và transaction nào đã bị loại khỏi binary log. Hai trạng thái quan trọng là `gtid_executed` và `gtid_purged`.

Khi tạo backup để dựng replica hoặc phục hồi sang server khác, metadata GTID phải khớp với dữ liệu thực sự có trong backup. Nếu ghi nhận thiếu GTID, replica có thể phát lại transaction đã nằm trong dữ liệu; nếu ghi nhận thừa GTID, replica có thể bỏ qua transaction mà backup chưa chứa. Hiểu đúng hai tập này giúp tránh mất dữ liệu và lỗi auto-position replication.

Bài học thuộc chương **Replication và GTID** của module `DATABASE_MYSQL`. Module bao quát thiết kế bảng, truy vấn, index, transaction, phân quyền, sao lưu và vận hành MySQL. Các ví dụ sử dụng cú pháp MySQL 8.0; hãy kiểm tra tài liệu của đúng phiên bản trước khi thực hiện thao tác thay đổi GTID trên production.

Sau bài học, bạn có thể:

- Đọc và diễn giải GTID set.
- Phân biệt `gtid_executed` với `gtid_purged`.
- Giải thích vì sao `gtid_purged` là tập con của `gtid_executed`.
- Chọn cách ghi nhận GTID khi tạo và restore backup.
- Nhận biết rủi ro của `mysqldump --set-gtid-purged` với dump một phần database/table.
- Dựng replica bằng GTID auto-position và xử lý tình huống thiếu binary log.

## 1. GTID set là gì?

GTID (Global Transaction Identifier) là định danh duy nhất cho một transaction được ghi nhận trong hệ thống replication. Trong MySQL, một GTID có cấu trúc:

```text
source_uuid:transaction_number
```

Ví dụ:

```text
24bc7850-2c16-11ee-be56-0242ac120002:105
```

`source_uuid` xác định nguồn đã tạo GTID; `transaction_number` là số thứ tự trong nguồn đó. Một GTID set là tập hợp một hoặc nhiều khoảng số liên tục thuộc một hoặc nhiều UUID.

Ví dụ một tập GTID:

```text
24bc7850-2c16-11ee-be56-0242ac120002:1-105:110-115,
7a1d5c12-3a44-11ee-9b12-0242ac120002:1-20
```

Tập trên chứa các GTID từ `1` đến `105` và từ `110` đến `115` của UUID thứ nhất, cùng `1` đến `20` của UUID thứ hai. Khoảng `106-109` của UUID thứ nhất không có trong tập.

Các ví dụ dùng `uuid-A` ở phần giải thích là nhãn rút gọn để dễ theo dõi. Trong câu lệnh SQL chạy thật, UUID phải có định dạng UUID hợp lệ như ví dụ đầy đủ ở trên.

GTID set được dùng để biểu diễn trạng thái replication theo transaction, thay vì chỉ dựa vào tên file binary log và byte position. Điều này giúp replica tự yêu cầu những transaction còn thiếu khi dùng auto-position.

## 2. `gtid_executed`: những transaction đã thực thi

`@@GLOBAL.gtid_executed` là tập GTID mà server ghi nhận đã thực thi. Tập này bao gồm transaction có GTID vẫn còn trong binary log và transaction có GTID đã bị purge khỏi binary log. Vì vậy, nó biểu diễn lịch sử thực thi được server ghi nhận, không chỉ những transaction còn có thể đọc từ các file binlog hiện tại.

Kiểm tra giá trị:

```sql
SELECT @@GLOBAL.gtid_executed;
```

Hoặc xem các biến GTID cùng lúc:

```sql
SHOW VARIABLES LIKE 'gtid_executed';
SHOW VARIABLES LIKE 'gtid_purged';
```

Giả sử server đã thực thi các GTID `uuid-A:1-500`. Khi đó `gtid_executed` có thể chứa:

```text
uuid-A:1-500
```

Nếu binary log hiện chỉ còn các transaction `uuid-A:201-500`, những GTID cũ hơn vẫn nằm trong `gtid_executed`, dù file chứa chúng không còn trên server.

`gtid_executed` là thông tin trạng thái do MySQL quản lý. Không chỉnh sửa trực tiếp các bảng hệ thống hoặc cố tạo tập GTID bằng cách sửa file dữ liệu. Khi cần nạp trạng thái GTID từ backup, dùng cơ chế được MySQL hỗ trợ và tuân thủ các điều kiện của `gtid_purged`.

## 3. `gtid_purged`: GTID đã bị loại khỏi binary log

`@@GLOBAL.gtid_purged` là tập GTID đã được thực thi nhưng không còn nằm trong các binary log hiện có trên server. Tập này cũng có thể được thiết lập khi nạp trạng thái GTID từ backup vào một server mới.

Kiểm tra:

```sql
SELECT @@GLOBAL.gtid_purged;
```

Ví dụ:

```text
gtid_executed = uuid-A:1-500
gtid_purged   = uuid-A:1-200
```

Điều đó có nghĩa server đã thực thi các transaction `1-500`, trong đó `1-200` không còn trong binary log. Những transaction `201-500` vẫn thuộc phần lịch sử GTID còn được giữ trong binlog, giả sử không có UUID hoặc khoảng khác.

Trong trạng thái thông thường:

\[
\texttt{gtid\_purged} \subseteq \texttt{gtid\_executed}
\]

`gtid_purged` không phải danh sách file đã xóa, cũng không phải lệnh xóa dữ liệu trong table. Nó là tập định danh transaction mà server không còn cung cấp trong binary log hiện tại.

Khi chạy `PURGE BINARY LOGS`, MySQL cập nhật trạng thái GTID tương ứng với các transaction bị loại khỏi log. Việc purge file không làm các transaction đó biến mất khỏi `gtid_executed`; dữ liệu mà transaction đã tạo vẫn còn trong database cho đến khi có thao tác dữ liệu khác thay đổi nó.

## 4. Phân biệt hai tập GTID

| Nội dung | `gtid_executed` | `gtid_purged` |
|---|---|---|
| Ý nghĩa | Tất cả GTID được server ghi nhận đã thực thi | GTID đã thực thi nhưng không còn trong binary log hiện tại |
| Có bao gồm GTID còn trong binlog? | Có | Không |
| Có bao gồm GTID đã purge? | Có | Có |
| Dùng để auto-position? | Cho biết replica đã có transaction nào | Giúp biết transaction nào source không còn khả năng gửi từ binlog hiện tại |
| Quan hệ | Tập bao ngoài | Là tập con của `gtid_executed` |

Hình dung server có `gtid_executed = uuid-A:1-500` và `gtid_purged = uuid-A:1-200`:

```text
gtid_executed:  [1 ----------------------------------------- 500]
gtid_purged:    [1 ------------- 200]
binlog còn lại:                 [201 ----------------------- 500]
```

Replica có GTID `1-350` chỉ còn thiếu `351-500`, nên source có thể gửi phần thiếu nếu binlog tương ứng còn được giữ. Replica chỉ có GTID `1-150` còn thiếu `151-500`; source đã purge `151-200`, vì vậy source không thể cung cấp đầy đủ chuỗi transaction cần thiết cho replica đó.

## 5. Xem trạng thái GTID trên source và replica

Trên source:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_mode,
  @@GLOBAL.enforce_gtid_consistency,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
```

Trên replica:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;

SHOW REPLICA STATUS\G
```

Đối chiếu các thông tin sau:

- `server_uuid`: mỗi server phải có UUID riêng. Không sao chép nguyên `auto.cnf` sang một server độc lập đang chạy như một thành viên khác của replication topology.
- `gtid_executed`: replica đã ghi nhận những transaction nào.
- `gtid_purged`: các transaction nào không còn trong binary log của từng server.
- Trạng thái I/O và SQL applier: replica có đang nhận và áp dụng transaction hay đang lỗi.
- GTID thiếu: replica cần những GTID nào mà source còn hoặc không còn giữ.

Không so sánh hai chuỗi GTID bằng cách nhìn độ dài văn bản. Cần dùng phép toán tập hợp GTID hoặc công cụ MySQL để biết tập nào bao hàm tập nào và phần nào còn thiếu.

## 6. Các phép toán tập hợp GTID hữu ích

MySQL cung cấp các hàm để kiểm tra quan hệ giữa GTID set:

```sql
-- Kiểm tra tập A có nằm trong tập B hay không
SELECT GTID_SUBSET(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-100',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-150'
);

-- Lấy phần GTID có trong A nhưng không có trong B
SELECT GTID_SUBTRACT(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-150',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-100'
);
```

Hai hàm thường dùng nhất là:

- `GTID_SUBSET(set1, set2)`: trả về `1` nếu mọi GTID trong `set1` đều có trong `set2`; ngược lại trả về `0`.
- `GTID_SUBTRACT(set1, set2)`: trả về các GTID có trong `set1` nhưng không có trong `set2`.

Ví dụ xác định GTID source còn thiếu so với replica:

```sql
SELECT GTID_SUBTRACT(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-500',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-350'
);
```

Kết quả là `uuid-A:351-500`. Trong thực tế, thay chuỗi minh họa bằng `@@GLOBAL.gtid_executed` của source và replica. Hãy chạy phép so sánh trên các giá trị được thu thập cùng thời điểm hoặc hiểu rằng trạng thái có thể tiếp tục thay đổi trong lúc truy vấn.

## 7. GTID và vòng đời của một binary log

Một transaction mới được commit trên source và ghi vào binary log sẽ làm tăng `gtid_executed`. Khi file binlog chứa transaction đó vẫn còn trên server, GTID tương ứng chưa thuộc `gtid_purged`.

Khi các file cũ bị purge:

1. File binlog chứa một số transaction cũ bị xóa khỏi server.
2. GTID của các transaction đã purge được phản ánh trong `gtid_purged`.
3. Các GTID đó vẫn thuộc `gtid_executed`.
4. Source không thể gửi lại transaction từ file đã bị xóa cho replica chưa nhận chúng.

Minh họa:

```text
Thời điểm A:
  gtid_executed = uuid-A:1-300
  gtid_purged   = uuid-A:1-100
  binlog còn    = uuid-A:101-300

Sau khi purge các file cũ hơn:
  gtid_executed = uuid-A:1-300
  gtid_purged   = uuid-A:1-180
  binlog còn    = uuid-A:181-300
```

`gtid_executed` không giảm khi purge log; `gtid_purged` mở rộng để phản ánh phần lịch sử không còn có thể đọc từ binary log.

## 8. Vì sao backup phải lưu metadata GTID?

Một backup phục hồi được dữ liệu nhưng thiếu metadata GTID có thể không đủ để dựng replica bằng auto-position. Replica cần biết những transaction nào đã được bao gồm trong dữ liệu backup để chỉ yêu cầu transaction còn thiếu.

Giả sử backup được tạo tại trạng thái source đã thực thi đến `uuid-A:500`. Khi restore backup, dữ liệu trong server đích đã bao gồm kết quả của các transaction đến mốc đó. Nếu server đích không ghi nhận các GTID tương ứng, khi kết nối replication nó có thể yêu cầu lại các transaction đã nằm trong backup. Hệ quả có thể là duplicate key, dữ liệu bị áp dụng hai lần hoặc lỗi khi applier thực thi.

Ngược lại, nếu metadata backup ghi nhận `uuid-A:1-700` nhưng snapshot dữ liệu chỉ chứa đến `uuid-A:500`, replica sẽ nghĩ rằng các transaction `501-700` đã được thực thi và bỏ qua chúng. Đây là trường hợp nguy hiểm hơn vì có thể dẫn tới thiếu dữ liệu mà không có lỗi rõ ràng.

Do đó, backup dùng để provision replica cần gắn với một GTID set phản ánh chính xác trạng thái dữ liệu được chụp. Cần lưu cùng backup:

- Thời điểm tạo backup và phiên bản MySQL.
- `server_uuid`, `gtid_executed` và `gtid_purged` tại mốc backup theo cách công cụ hỗ trợ.
- Tên file/position binlog nếu quy trình có dùng tọa độ file/position.
- Danh sách database/table thực sự có trong backup.
- Tùy chọn dump hoặc chế độ snapshot đã sử dụng.
- Danh sách binlog được archive liên tục sau mốc backup.

## 9. Logical backup bằng mysqldump và `--set-gtid-purged`

`mysqldump` có tùy chọn `--set-gtid-purged` để điều khiển việc ghi câu lệnh thiết lập GTID vào file dump. Các giá trị thường dùng:

| Giá trị | Hành vi |
|---|---|
| `AUTO` | Tự quyết định dựa trên trạng thái GTID của server nguồn; đây là giá trị mặc định ở các phiên bản MySQL hiện hành. |
| `ON` | Ghi câu lệnh `SET @@GLOBAL.GTID_PURGED` vào dump khi GTID được bật. |
| `OFF` | Không ghi câu lệnh thiết lập `GTID_PURGED`. |
| `COMMENTED` | Ghi câu lệnh liên quan dưới dạng comment để người vận hành xem xét và áp dụng thủ công. |

Khi bật `ON`, mysqldump thường ghi thêm lệnh tắt binary logging cho session import để các câu lệnh khôi phục không tạo ra một bộ GTID mới thay cho lịch sử nguồn. Hãy kiểm tra đầu file dump thực tế vì chi tiết output có thể phụ thuộc phiên bản và tùy chọn kết hợp.

Ví dụ dump toàn bộ instance để dựng replica mới:

```bash
mysqldump --user=backup_user --password \
  --single-transaction \
  --routines --events --triggers \
  --set-gtid-purged=ON \
  --all-databases \
  > full-instance.sql
```

Với dump toàn instance, GTID set được ghi trong file có thể đại diện cho toàn bộ lịch sử GTID đã thực thi trên source tại thời điểm được lấy. Sau khi restore vào server đích phù hợp, trạng thái GTID giúp auto-position nhận ra transaction đã có trong backup.

### 9.1. Cảnh báo quan trọng với dump một phần

GTID set mà mysqldump ghi không chỉ gồm transaction thay đổi database/table được dump. Nó có thể bao gồm toàn bộ `gtid_executed` trên source, kể cả transaction chỉ thay đổi database hoặc table bị bỏ khỏi dump.

Ví dụ source có hai database `sales` và `payroll`. Bạn chỉ dump `sales`, nhưng GTID set trong dump vẫn chứa transaction của cả hai database. Nếu restore file đó và dùng trạng thái GTID để dựng replica của source, replica có thể coi transaction của `payroll` đã được thực thi dù dữ liệu `payroll` chưa từng được đưa vào backup. Source sẽ không gửi lại các transaction đó vì GTID đã được đánh dấu là có.

Vì vậy:

- Không dùng `--set-gtid-purged=ON` một cách máy móc cho dump chỉ gồm một database, một nhóm table hoặc một tập hàng nếu mục tiêu là dựng replica của toàn source.
- Với dump một phần dùng để di chuyển dữ liệu độc lập hoặc dựng môi trường thử nghiệm, thường cân nhắc `--set-gtid-purged=OFF` để không đánh dấu toàn bộ lịch sử source là đã có trên đích.
- Nếu cần dựng replica từ dữ liệu một phần, phải thiết kế rõ topology và phạm vi dữ liệu replication; không thể dựa vào một GTID set toàn server để đại diện chính xác cho tập dữ liệu con.

### 9.2. Lưu ý về snapshot và thay đổi đồng thời

`--single-transaction` tạo snapshot nhất quán cho table InnoDB, nhưng không khóa mọi DDL. Tránh chạy `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc thay đổi cấu trúc khác trên các đối tượng đang dump. Table nontransactional không được bảo vệ bởi snapshot InnoDB.

Khi backup sẽ được dùng để dựng replica, cần bảo đảm GTID metadata và snapshot dữ liệu phản ánh cùng một mốc logic. Hãy dùng đúng quy trình backup được tài liệu phiên bản hỗ trợ, giữ log thay đổi trong lúc backup, và kiểm thử restore cùng auto-position. Không tự ghép một giá trị `gtid_executed` lấy tùy tiện sau khi dump với dữ liệu snapshot được tạo trước đó.

## 10. Restore backup và thiết lập GTID

Khi restore một dump có chứa `SET @@GLOBAL.GTID_PURGED`, server đích phải thỏa các điều kiện của MySQL cho việc thiết lập tập GTID. Thông thường, thao tác này được thực hiện trên instance mới hoặc instance đã được chuẩn bị sạch cho mục tiêu restore. Nếu đích đã có GTID khác hoặc có transaction phát sinh sau khi tạo backup, câu lệnh có thể bị từ chối do xung đột hoặc điều kiện không hợp lệ.

Quy trình khái quát cho một replica mới:

1. Chuẩn bị server đích mới, bảo đảm `server_uuid` là duy nhất và cấu hình GTID phù hợp.
2. Restore backup theo đúng phiên bản và phạm vi đã ghi nhận.
3. Kiểm tra `@@GLOBAL.gtid_executed` và `@@GLOBAL.gtid_purged` trên đích.
4. Xác nhận GTID của dữ liệu backup đã được phản ánh trong trạng thái GTID của đích.
5. Cấu hình replication auto-position và bắt đầu replica.
6. Kiểm tra trạng thái I/O/applier, GTID đã nhận và độ trễ.

Không chạy `SET GLOBAL gtid_purged` trên một server đã có dữ liệu tùy ý để “làm cho replication chạy”. Việc này có thể đánh dấu nhầm transaction là đã thực thi, khiến source bỏ qua dữ liệu replica thực sự còn thiếu.

### 10.1. Ví dụ thiết lập replica bằng auto-position

Sau khi restore backup và kiểm tra GTID set, cấu hình kết nối tới source:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'replace-with-managed-secret',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

Trong production, dùng TLS và cơ chế quản lý secret thích hợp. Tài khoản replication cần quyền phù hợp; không đưa mật khẩu thật vào script, lịch sử terminal hoặc tài liệu.

Với auto-position, replica gửi tập GTID mà nó đã thực thi cho source. Source xác định transaction nào replica còn thiếu và gửi các transaction đó nếu chúng vẫn còn trong binary log. Cơ chế này giảm phụ thuộc vào file/position nhưng không thể tái tạo transaction mà source đã purge.

Kiểm tra:

```sql
SHOW REPLICA STATUS\G
```

Quan sát `Auto_Position`, trạng thái receiver/applier, lỗi SQL/I/O, file log và thông tin GTID. Tên trường trong output có thể khác theo phiên bản.

## 11. Khi source đã purge GTID mà replica cần

Giả sử source có:

```text
gtid_executed = uuid-A:1-1000
gtid_purged   = uuid-A:1-700
```

Replica vừa restore backup cũ và chỉ có:

```text
gtid_executed = uuid-A:1-500
```

Replica cần các GTID `501-1000`, nhưng source đã purge `501-700`. Source chỉ còn binlog cho phần `701-1000`, vì vậy không thể gửi đầy đủ lịch sử còn thiếu. Auto-position sẽ thất bại với lỗi cho biết source không có một hoặc nhiều GTID được yêu cầu.

Hướng xử lý:

- Khôi phục một backup mới hơn có chứa ít nhất các transaction đã bị purge.
- Tìm bản archive binary log liên tục chứa các GTID còn thiếu và nạp theo quy trình phục hồi phù hợp.
- Nếu không còn backup hoặc binlog đầy đủ, dựng lại replica từ một backup hợp lệ mới hơn và cấu hình replication lại.

Không giải quyết bằng cách thêm các GTID thiếu vào `gtid_purged` của replica. Việc đó chỉ đánh dấu chúng như đã thực thi; nó không tái tạo dữ liệu mà các transaction đó từng tạo ra.

## 12. Các quy tắc khi đặt `gtid_purged`

`gtid_purged` là biến global đặc biệt, có điều kiện khi gán. Quy tắc chính xác thay đổi theo phiên bản MySQL; trước khi thực hiện, đọc tài liệu của đúng phiên bản và kiểm tra trạng thái hiện tại.

Các nguyên tắc an toàn:

- Chỉ đặt GTID set khi bạn biết chắc dữ liệu tương ứng đã có trong server đích.
- Không thêm một GTID set tùy ý để bỏ qua lỗi replication.
- Kiểm tra overlap với `gtid_executed` và `gtid_purged` hiện tại theo quy tắc của phiên bản.
- Thực hiện trên instance mới hoặc trong cửa sổ bảo trì có kế hoạch restore rõ ràng.
- Không chỉnh sửa trực tiếp bảng `mysql.gtid_executed`.
- Lưu lại GTID set gốc và kế hoạch rollback trước khi thay đổi trạng thái GTID.

Một số phiên bản MySQL hỗ trợ cú pháp thêm hoặc loại khoảng GTID khi gán `gtid_purged`; cú pháp và điều kiện không giống nhau giữa các phiên bản. Không sao chép câu lệnh `SET GLOBAL gtid_purged` từ một bài hướng dẫn cũ mà chưa xác minh. Với dump do mysqldump tạo, ưu tiên dùng câu lệnh metadata đã sinh ra và restore theo quy trình được hỗ trợ.

## 13. Backup vật lý và metadata GTID

Backup vật lý thường sao chép file dữ liệu InnoDB và các thành phần cần thiết để khôi phục instance. Tùy công cụ, metadata backup có thể lưu GTID set, binary log coordinates hoặc thông tin transaction đã chuẩn hóa trong quá trình prepare.

Khi sử dụng công cụ backup vật lý:

1. Đọc metadata hoặc file thông tin do công cụ tạo ra để lấy GTID set chính xác của backup.
2. Bảo đảm quy trình backup đã hoàn tất bước prepare/recovery cần thiết trước khi khởi động server từ bản sao.
3. Không lấy `gtid_executed` hiện tại của source sau khi backup hoàn tất nếu nó đã tiến xa hơn snapshot.
4. Khôi phục vào instance đích với UUID riêng và cấu hình replication phù hợp.
5. Đối chiếu GTID set sau restore với metadata backup trước khi bật auto-position.

Với công cụ như MySQL Enterprise Backup hoặc Percona XtraBackup, tên file và định dạng metadata phụ thuộc công cụ/phiên bản. Hãy dùng GTID set được chính công cụ xác định tại điểm backup, không tự suy luận từ timestamp hoặc kích thước file.

## 14. Quy trình backup dùng cho replication

Một quy trình có thể kiểm toán nên gồm các bước:

1. **Xác định mục tiêu.** Backup sẽ dùng để dựng replica toàn instance, di chuyển một database hay tạo bản sao phục vụ kiểm thử?
2. **Chọn phạm vi dữ liệu.** Ghi rõ database/table có trong backup và các đối tượng đi kèm.
3. **Chọn phương pháp snapshot.** Dùng snapshot phù hợp với storage engine; điều phối DDL và ghi nhận điểm nhất quán.
4. **Ghi GTID metadata.** Lưu GTID set do công cụ backup xác định tại cùng mốc logic với snapshot.
5. **Bảo vệ chuỗi binlog.** Giữ binary log từ mốc backup đến khi mọi replica cần nó đã bắt kịp; archive log nếu retention source không đủ.
6. **Restore thử.** Khôi phục vào môi trường độc lập, kiểm tra dữ liệu và GTID set.
7. **Cấu hình auto-position.** Chỉ bật replication sau khi xác nhận GTID set phản ánh chính xác transaction đã có trong backup.
8. **Giám sát sau restore.** Kiểm tra applier, lỗi replication, độ trễ và dữ liệu nghiệp vụ đại diện.

Nếu backup được tạo mỗi ngày nhưng replica mới có thể mất nhiều ngày để restore và bắt kịp, retention source phải đủ dài để giữ log từ mốc backup đến khi replica đọc xong. Nếu không, phải archive binlog ở nơi lưu trữ bền vững.

## 15. Lỗi thường gặp khi backup và GTID

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Restore báo lỗi khi gán `GTID_PURGED` | Đích đã có GTID hoặc tập mới không đáp ứng điều kiện gán | Kiểm tra `gtid_executed`, `gtid_purged`, overlap và phiên bản. Chuẩn bị instance sạch nếu mục tiêu là provision replica mới. |
| Replica báo cần GTID đã purge | Backup quá cũ so với retention binlog source | Đối chiếu GTID thiếu với `gtid_purged`; dùng backup mới hơn hoặc archive log đầy đủ. |
| Replica không nhận transaction của một database | Dump chỉ chứa một phần dữ liệu nhưng GTID set đánh dấu toàn bộ source đã thực thi | Kiểm tra `--set-gtid-purged`; không dùng ON cho dump một phần để provision replica toàn source. |
| Dữ liệu bị duplicate khi bắt đầu replication | GTID trong backup không được ghi nhận hoặc import tạo GTID mới không đúng kế hoạch | Kiểm tra đầu file dump, `SQL_LOG_BIN`, `gtid_executed` và quy trình restore. |
| Replica bỏ qua một số thay đổi | GTID đã bị đánh dấu executed dù dữ liệu tương ứng không có trong backup | Không tự sửa tập GTID; dựng lại từ backup nhất quán và đúng phạm vi. |
| GTID set backup lớn hơn trạng thái dữ liệu | Lấy GTID ở thời điểm khác với snapshot hoặc dump không đồng bộ | Kiểm tra quy trình snapshot, DDL đồng thời và nguồn metadata GTID. |
| Server không thể cung cấp GTID cho replica cũ | Binlog đã hết hạn hoặc purge thủ công | Kiểm tra `SHOW BINARY LOGS`, `gtid_purged`, replica lag và archive. |

## 16. Bài tập thực hành

### Bài 1: Đọc hai tập GTID

Giả sử:

```text
gtid_executed = uuid-A:1-900
gtid_purged   = uuid-A:1-600
```

Trả lời:

1. Các GTID nào còn trong binary log, nếu chỉ có UUID này và không có khoảng trống?
2. Replica có `uuid-A:1-750` còn thiếu tập nào?
3. Replica có `uuid-A:1-500` có thể bắt kịp chỉ từ binlog hiện tại không?

Dùng `GTID_SUBTRACT()` để tính phần còn thiếu và giải thích vì sao source có hoặc không có khả năng gửi chúng.

### Bài 2: Kiểm tra ảnh hưởng của dump một phần

Source có database `sales` và `payroll`, với các transaction GTID thay đổi cả hai database. Tạo hai file dump: một file `--all-databases` và một file chỉ dump `sales`. So sánh đầu file khi dùng `--set-gtid-purged=ON` và `OFF`.

Giải thích vì sao GTID set của dump `sales` có thể chứa transaction của `payroll`, và tại sao điều đó gây thiếu dữ liệu nếu dùng file này để provision replica toàn source.

### Bài 3: Dựng replica từ backup

Tạo full backup trên source thử nghiệm, lưu GTID set tại mốc backup, restore vào một instance mới rồi cấu hình `SOURCE_AUTO_POSITION=1`. Kiểm tra GTID set trước khi chạy `START REPLICA`, sau đó xác nhận replica bắt kịp các transaction phát sinh sau backup.

### Bài 4: Xử lý replica bị thiếu log

Tạo tình huống replica dùng backup cũ hơn thời gian retention. Quan sát lỗi auto-position khi source đã purge GTID replica cần. Viết quy trình khôi phục bằng backup mới hơn hoặc archive binlog, đồng thời nêu rõ vì sao chỉ sửa `gtid_purged` không khôi phục được dữ liệu.

## 17. Checklist trước khi dùng backup để dựng replica

- [ ] Backup chứa đúng phạm vi database/table dự kiến.
- [ ] Phương pháp snapshot tạo dữ liệu nhất quán theo storage engine.
- [ ] GTID metadata được lấy tại cùng mốc logic với snapshot.
- [ ] Đã kiểm tra `gtid_executed` và `gtid_purged` trên source.
- [ ] Nếu dùng mysqldump, đã xem xét kỹ `--set-gtid-purged` và phạm vi dump.
- [ ] Không dùng GTID set toàn source cho dump một phần khi dựng replica toàn source.
- [ ] Binary log sau mốc backup được giữ hoặc archive đến khi replica bắt kịp.
- [ ] Server đích có `server_uuid` riêng.
- [ ] GTID state trên đích đã được kiểm tra sau restore.
- [ ] Auto-position được bật sau khi xác nhận dữ liệu và GTID tương ứng.
- [ ] Đã kiểm tra replication status và dữ liệu nghiệp vụ sau khi bắt đầu.
- [ ] Có restore test định kỳ và tài liệu xử lý khi source purge log quá sớm.

`gtid_executed` cho biết server đã thực thi những transaction nào; `gtid_purged` cho biết phần nào trong lịch sử đó không còn nằm trong binary log hiện tại. Backup dùng cho replication phải bảo toàn mối quan hệ giữa dữ liệu snapshot và GTID set tương ứng. Hãy ghi nhận metadata tại đúng mốc, giữ chuỗi binlog đủ lâu và kiểm thử auto-position sau restore để replica chỉ nhận đúng những transaction mà backup chưa chứa.
