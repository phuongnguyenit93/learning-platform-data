# `mysqldump`: phạm vi database/table và lựa chọn đối tượng đi kèm

`mysqldump` là tiện ích dòng lệnh của MySQL để xuất cấu trúc và dữ liệu thành các câu lệnh SQL. Phạm vi xuất được quyết định bởi các tên database, table và tùy chọn đi kèm. Chọn đúng phạm vi giúp tạo bản sao lưu đủ dùng cho mục tiêu khôi phục, giảm dữ liệu không cần thiết và tránh bỏ sót các đối tượng như stored procedure, event hoặc trigger.

Bài học này thuộc chương **Sao lưu và phục hồi** của module `DATABASE_MYSQL`. Module bao quát từ thiết kế bảng, truy vấn và tối ưu đến transaction, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Bài này tập trung vào việc xác định `mysqldump` sẽ xuất những gì, cách chọn database/table, cách xử lý các đối tượng liên quan và cách xác minh kết quả. Các ví dụ dùng cú pháp MySQL 8.0; hãy kiểm tra `mysqldump --help` và tài liệu đúng phiên bản client/server trước khi áp dụng trong production.

Sau bài học, bạn có thể:

- Chọn giữa dump toàn server, một hoặc nhiều database và một nhóm table.
- Phân biệt xuất cấu trúc, dữ liệu và cả hai.
- Chủ động đưa views, triggers, stored routines và events vào bản dump.
- Dùng các tùy chọn lọc table hoặc hàng khi có yêu cầu rõ ràng.
- Chọn cách tạo snapshot phù hợp với storage engine và mức độ ghi đồng thời.
- Kiểm tra file dump và khôi phục thử để xác nhận phạm vi thực tế.

## 1. Cách mysqldump xác định phạm vi

Cú pháp tổng quát có ba dạng chính:

```bash
# Một database, có thể chọn một hoặc nhiều table
mysqldump [options] db_name [table_name ...]

# Một hoặc nhiều database
mysqldump [options] --databases db_name [db_name ...]

# Tất cả database mà lệnh có thể dump
mysqldump [options] --all-databases
```

Điểm cần nhớ là vị trí và cách diễn giải các đối số thay đổi theo tùy chọn:

- Khi gọi `mysqldump db_name`, tên đầu tiên là database. Các tên tiếp theo, nếu có, là table trong database đó.
- Khi dùng `--databases`, các tên tiếp theo đều được hiểu là tên database. Không đặt tên table sau danh sách database với kỳ vọng chúng sẽ được hiểu là table.
- Khi dùng `--all-databases`, tiện ích tự chọn phạm vi database; không cần truyền tên database.

Ví dụ, lệnh sau xuất tất cả table trong database `sales`:

```bash
mysqldump -u backup_user -p sales > sales.sql
```

Lệnh dưới đây chỉ xuất hai table được chỉ định:

```bash
mysqldump -u backup_user -p sales orders order_items > sales-orders.sql
```

Để xuất nhiều database:

```bash
mysqldump -u backup_user -p --databases sales inventory > business-databases.sql
```

Và để xuất phạm vi toàn server:

```bash
mysqldump -u backup_user -p --all-databases > instance.sql
```

Tên database và table trong ví dụ là tên minh họa. Tài khoản chạy dump cần có quyền đọc metadata và dữ liệu cần xuất, cùng các quyền bổ sung tùy theo tùy chọn và phiên bản MySQL.

### 1.1. Dump một database

Đây là lựa chọn phổ biến khi một ứng dụng sở hữu một database riêng:

```bash
mysqldump --user=backup_user --password sales > sales.sql
```

Client sẽ hỏi mật khẩu tương tác. Không ghi mật khẩu trực tiếp trong dòng lệnh, script chia sẻ hoặc lịch sử shell. Trong môi trường tự động, hãy dùng cơ chế lưu credential phù hợp, chẳng hạn login path hoặc file cấu hình được giới hạn quyền đọc.

Khi chỉ truyền `sales`, mysqldump xuất các đối tượng thuộc database đó theo các tùy chọn hiện hành. Câu lệnh không có nghĩa là đã sao lưu toàn bộ server: database khác, cấu hình server và các tài nguyên bên ngoài database có thể không nằm trong file.

Nếu cần file dump tự chứa câu lệnh tạo database khi khôi phục, dùng `--databases`:

```bash
mysqldump --user=backup_user --password --databases sales > sales-with-database.sql
```

`--databases` thêm các câu lệnh tạo/chọn database như `CREATE DATABASE` và `USE` vào output. Điều này hữu ích khi khôi phục sang server khác hoặc khi database đích chưa tồn tại. Nếu chỉ dump một database mà không có `--databases`, hãy chuẩn bị database đích trước khi import.

### 1.2. Dump nhiều database

```bash
mysqldump --user=backup_user --password \
  --databases sales inventory reporting \
  > selected-databases.sql
```

Mỗi database được đưa vào file theo phạm vi đã chọn. Khi khôi phục, các câu lệnh tạo và chọn database trong file sẽ điều khiển nơi các đối tượng được tạo. Cần kiểm tra tên database trong file trước khi import vào môi trường có dữ liệu hiện hữu.

### 1.3. Dump toàn server

```bash
mysqldump --user=backup_user --password \
  --all-databases \
  > full-instance.sql
```

`--all-databases` phù hợp khi mục tiêu là xuất phạm vi database rộng trên một MySQL instance. Tuy nhiên, đừng mặc định rằng một file `--all-databases` là bản sao lưu hoàn chỉnh của mọi thành phần server. Các schema hệ thống đặc biệt như `performance_schema` và `information_schema` có cách xử lý riêng; cấu hình ngoài database, file cấu hình, keyring, plugin, chứng chỉ TLS, binary log và các thành phần hạ tầng khác cần được xem xét theo mục tiêu phục hồi.

Với tài khoản và quyền, hãy xác định rõ yêu cầu vận hành. Nếu cần tái tạo danh tính và quyền người dùng, hãy kiểm tra chính xác nội dung database hệ thống có trong dump và quy trình khôi phục của phiên bản đang dùng; có thể cần lưu riêng kết quả `SHOW CREATE USER` và `SHOW GRANTS` cho các tài khoản quan trọng. Không xem một bản dump dữ liệu ứng dụng là bằng chứng rằng người dùng, role và chính sách truy cập đã được bảo toàn.

## 2. Chọn database và table cụ thể

### 2.1. Chỉ dump một số table

Khi chỉ cần một phần dữ liệu, đặt tên table sau tên database:

```bash
mysqldump --user=backup_user --password \
  sales orders order_items customers \
  > sales-core-tables.sql
```

Lệnh trên chọn ba table trong database `sales`. Đây là cách hữu ích để chuyển một nhóm bảng, tạo bản sao dữ liệu thử nghiệm hoặc phục hồi một phần. Hãy kiểm tra các quan hệ phụ thuộc: một table có thể tham chiếu khóa ngoại đến table khác, view có thể đọc nhiều table, và routine có thể sử dụng các bảng không nằm trong phạm vi dump.

Một bản dump table không tự động trở thành một gói phục hồi độc lập. Ví dụ, nếu `order_items` có khóa ngoại tham chiếu `orders`, khôi phục riêng `order_items` có thể thất bại hoặc tạo ra dữ liệu không đáp ứng ràng buộc nếu bảng cha và dữ liệu tương ứng chưa có.

### 2.2. Bỏ qua một table

`--ignore-table` loại một table cụ thể khỏi phạm vi dump. Giá trị cần có cả database và table:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --ignore-table=sales.audit_log \
  --ignore-table=sales.request_cache \
  > sales-without-logs.sql
```

Có thể lặp lại tùy chọn để bỏ qua nhiều table. Kiểm tra kỹ tên đầy đủ `database.table`; bỏ qua nhầm table có thể làm bản khôi phục thiếu dữ liệu nghiệp vụ hoặc thiếu đối tượng mà view/routine phụ thuộc.

Việc loại table khỏi dump có thể loại cả định nghĩa và dữ liệu của table đó. Nếu mục tiêu là giữ cấu trúc nhưng không xuất hàng dữ liệu, hãy xem xét `--no-data` cho toàn phạm vi hoặc tính năng bỏ qua dữ liệu table nếu phiên bản client hỗ trợ. Tùy chọn bỏ dữ liệu riêng từng table có thể khác nhau giữa các phiên bản; xác minh bằng `mysqldump --help` trước khi đưa vào script.

### 2.3. Lọc hàng bằng WHERE

`--where` cho phép chỉ xuất các hàng thỏa điều kiện SQL của một table được dump. Ví dụ xuất các đơn hàng tạo từ một ngày nhất định:

```bash
mysqldump --user=backup_user --password \
  sales orders \
  --where="created_at >= '2026-01-01'" \
  > recent-orders.sql
```

Điều kiện được gửi tới MySQL, vì vậy cần dùng cú pháp SQL hợp lệ và quote đúng cho shell đang sử dụng. Hãy thử truy vấn `SELECT` với cùng điều kiện trước khi dump để biết chính xác số hàng sẽ được xuất.

Dump theo `WHERE` thường dùng cho một table và một tập dữ liệu được chọn. Nó không tự động áp dụng một bộ lọc nghiệp vụ nhất quán lên các table liên quan. Ví dụ, lọc đơn hàng theo ngày nhưng dump toàn bộ `order_items` có thể tạo ra tập dữ liệu không khớp. Nếu cần dữ liệu mẫu nhất quán qua nhiều bảng, hãy thiết kế tập ID cần lấy và các bước trích xuất liên quan một cách có chủ đích.

Không dùng `--where` như một cơ chế che giấu dữ liệu nhạy cảm thay cho phân quyền. Bản dump vẫn có thể chứa metadata, định nghĩa đối tượng hoặc các table khác; hãy kiểm tra file và bảo vệ quyền truy cập của file đầu ra.

## 3. Chọn xuất cấu trúc, dữ liệu hoặc cả hai

Hai tùy chọn nền tảng giúp kiểm soát nội dung của file:

| Tùy chọn | Nội dung chính | Mục đích thường gặp |
|---|---|---|
| Mặc định | Cấu trúc và dữ liệu của các table được chọn | Sao lưu database để khôi phục đầy đủ phạm vi table. |
| `--no-data` | Cấu trúc, không xuất hàng dữ liệu | Tạo schema cho môi trường mới, review DDL hoặc chuẩn bị database rỗng. |
| `--no-create-info` | Dữ liệu, không xuất câu lệnh tạo table | Chuyển dữ liệu vào schema đã được tạo sẵn và tương thích. |

### 3.1. Chỉ xuất cấu trúc

```bash
mysqldump --user=backup_user --password \
  --no-data --databases sales \
  > sales-schema.sql
```

File này hữu ích khi cần dựng schema ở môi trường test hoặc so sánh định nghĩa bảng. Tuy nhiên, schema-only không đồng nghĩa với việc chỉ có `CREATE TABLE`: các đối tượng liên quan có thể được xuất tùy lựa chọn khác và mặc định của client. Nếu muốn kiểm soát routines, events hoặc triggers, hãy chỉ định rõ các tùy chọn tương ứng.

### 3.2. Chỉ xuất dữ liệu

```bash
mysqldump --user=backup_user --password \
  --no-create-info --databases sales \
  > sales-data.sql
```

File dữ liệu cần một schema đích tương thích. Số cột, thứ tự cột, kiểu dữ liệu, charset, collation, khóa và các ràng buộc phải phù hợp với cách dữ liệu được xuất. Nếu cấu trúc đã thay đổi giữa thời điểm dump và restore, import có thể thất bại hoặc ghi dữ liệu sai cột. Chỉ dùng cách này khi schema đích được quản lý và kiểm chứng riêng.

### 3.3. Điều khiển câu lệnh DROP

Tùy chọn `--add-drop-table` thêm `DROP TABLE` trước câu lệnh tạo table. Tùy chọn này thường được bật thông qua nhóm mặc định `--opt` của mysqldump. Khi restore, bảng đích cùng tên có thể bị xóa rồi tạo lại.

```bash
mysqldump --user=backup_user --password \
  --skip-add-drop-table --databases sales \
  > sales-no-drop.sql
```

`--skip-add-drop-table` giúp output không chủ động thêm lệnh drop table. Hãy đọc file dump trước khi restore; các tùy chọn khác, script triển khai hoặc nội dung đã được tùy biến vẫn có thể tác động đến dữ liệu đích. Với database đang có dữ liệu, luôn thử restore vào môi trường cô lập trước.

## 4. Các đối tượng đi kèm table và database

Sao lưu không chỉ là sao chép hàng trong table. Một ứng dụng có thể phụ thuộc vào view, trigger, stored procedure, function và event scheduler. Mỗi nhóm đối tượng có cách xuất riêng.

| Đối tượng | Hành vi của mysqldump | Tùy chọn cần biết |
|---|---|---|
| Table và dữ liệu | Xuất theo phạm vi database/table đã chọn | Mặc định; điều chỉnh bằng `--no-data` hoặc `--no-create-info`. |
| View | Được xuất trong phạm vi database/table phù hợp như định nghĩa view | Kiểm tra view phụ thuộc vào table hoặc view khác. |
| Trigger | Được dump mặc định cho các table được chọn trong các phiên bản hiện hành | `--skip-triggers` tắt việc xuất trigger. |
| Stored procedure và function | Không được xuất mặc định trong nhiều cấu hình | `--routines` bật xuất stored routines. |
| Event | Không được xuất mặc định | `--events` bật xuất scheduled events. |

### 4.1. View

View lưu định nghĩa truy vấn dựa trên một hoặc nhiều table hoặc view khác. Khi dump một database, các view trong phạm vi đó thường được đưa vào output. Tuy nhiên, nếu chỉ dump một số table, không nên mặc định rằng mọi view phụ thuộc sẽ được xuất như mong muốn. Hãy kiểm tra danh sách view và các phụ thuộc trước khi chọn phạm vi table.

Ví dụ kiểm tra view trong database:

```sql
SELECT TABLE_NAME, VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'sales';
```

Quyền hiển thị định nghĩa view có thể phụ thuộc quyền tài khoản và phiên bản. Với view quan trọng, kiểm tra thêm `SHOW CREATE VIEW sales.order_summary`.

### 4.2. Trigger

Trigger gắn với table và tự chạy khi có sự kiện như `INSERT`, `UPDATE` hoặc `DELETE`. mysqldump xuất trigger cho table được dump theo mặc định; `--skip-triggers` tắt việc này.

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --triggers \
  > sales-with-triggers.sql
```

`--triggers` được bật mặc định ở các phiên bản MySQL hiện hành, nhưng ghi rõ trong script giúp thể hiện ý định và dễ review. Trigger có thể phụ thuộc table khác, routine hoặc quyền của DEFINER. Nếu chỉ dump một table, hãy kiểm tra các đối tượng mà trigger gọi hoặc cập nhật.

### 4.3. Stored procedure và function

Stored procedure và stored function không được xuất mặc định trong nhiều cấu hình. Dùng `--routines` khi cần bảo toàn chúng:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --routines \
  > sales-with-routines.sql
```

Nếu cần cả cấu trúc, dữ liệu, routines và events, có thể kết hợp:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --routines --events --triggers \
  > sales-application-backup.sql
```

Khi khôi phục routine, chú ý `DEFINER`, `SQL SECURITY`, quyền của tài khoản sở hữu routine và các đối tượng mà routine truy cập. Một routine có thể được dump thành công nhưng không hoạt động sau restore nếu tài khoản DEFINER không tồn tại, quyền của tài khoản đó khác đi hoặc dependency chưa được khôi phục.

### 4.4. Event

Event là tác vụ được MySQL Event Scheduler thực thi theo lịch. Dùng `--events` để xuất định nghĩa event:

```bash
mysqldump --user=backup_user --password \
  --databases reporting \
  --events \
  > reporting-with-events.sql
```

Sau khi restore, kiểm tra trạng thái Event Scheduler trên server đích và trạng thái từng event. Không bật lịch chạy tự động một cách thiếu kiểm soát khi khôi phục production sang môi trường staging hoặc môi trường kiểm thử; event có thể gửi thông báo, xóa dữ liệu hoặc chạy tác vụ định kỳ ngoài dự kiến.

### 4.5. Bảng tổng hợp một lệnh sao lưu ứng dụng

Một lệnh thường dùng khi muốn dump database ứng dụng cùng routine, event và trigger:

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales \
  > sales-backup.sql
```

Lệnh này chọn database `sales`, xuất schema và dữ liệu theo mặc định, đồng thời yêu cầu xuất routines, events và triggers. `--single-transaction` và `--quick` ảnh hưởng cách đọc dữ liệu; chúng không mở rộng phạm vi database.

## 5. Chọn tùy chọn theo mục tiêu dump

Các tùy chọn dưới đây thường được dùng khi viết script sao lưu. Hãy đọc `mysqldump --help` trên đúng máy chạy backup để xác nhận tùy chọn có sẵn.

| Tùy chọn | Tác dụng | Lưu ý |
|---|---|---|
| `--databases` | Chọn một hoặc nhiều database, đưa câu lệnh tạo/chọn database vào output | Các đối số sau đó là tên database. |
| `--all-databases` | Chọn phạm vi database toàn instance | Không thay thế sao lưu cấu hình và thành phần ngoài database. |
| `--ignore-table=db.table` | Loại table được chỉ định khỏi dump | Có thể lặp lại; cần ghi lại lý do loại bỏ. |
| `--where='condition'` | Lọc hàng của table theo điều kiện SQL | Kiểm tra điều kiện và tính nhất quán với dữ liệu liên quan. |
| `--no-data` | Chỉ xuất cấu trúc | Hữu ích cho schema-only. |
| `--no-create-info` | Bỏ câu lệnh tạo table | Chỉ phù hợp khi schema đích đã tồn tại và tương thích. |
| `--routines` | Xuất stored procedure và function | Kiểm tra DEFINER và quyền khi restore. |
| `--events` | Xuất scheduled events | Kiểm tra Event Scheduler trên server đích. |
| `--triggers` | Xuất trigger của table trong phạm vi | Thường bật mặc định; `--skip-triggers` để tắt. |
| `--single-transaction` | Tạo snapshot nhất quán cho dữ liệu transactional như InnoDB | Không bảo đảm snapshot cho table nontransactional; tránh DDL đồng thời. |
| `--quick` | Đọc và ghi từng hàng theo luồng thay vì giữ toàn bộ result set trong bộ nhớ client | Thường được bật trong nhóm tùy chọn mặc định `--opt`. |
| `--hex-blob` | Xuất dữ liệu nhị phân dưới dạng hexadecimal | Hữu ích với BINARY, VARBINARY, BLOB và dữ liệu nhị phân. |
| `--default-character-set=utf8mb4` | Chỉ định charset kết nối khi dump | Charset phải tương thích với dữ liệu và môi trường. |
| `--no-tablespaces` | Bỏ các câu lệnh thông tin tablespace/logfile group khỏi output | Dùng khi không cần tái tạo các định nghĩa này hoặc khi muốn tránh yêu cầu quyền liên quan. |

Không nên sao chép nguyên một bộ tùy chọn vào mọi hệ thống. Hãy xác định mục tiêu phục hồi, storage engine, dung lượng dữ liệu, quyền của tài khoản backup và khả năng của phiên bản client trước khi chốt lệnh.

## 6. Tính nhất quán của bản dump

Chọn đúng database và table chưa đủ. Bản dump còn phải phản ánh trạng thái dữ liệu phù hợp tại một thời điểm.

### 6.1. InnoDB và `--single-transaction`

Với các table InnoDB, `--single-transaction` yêu cầu mysqldump mở một transaction để đọc snapshot nhất quán. Các thao tác ghi thông thường vẫn có thể tiếp tục trong khi dump, và bản dump phản ánh dữ liệu theo snapshot của transaction.

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --databases sales \
  > sales-consistent.sql
```

Để kết quả có ý nghĩa, cần chú ý:

- Snapshot này phù hợp với transactional engine như InnoDB.
- Table MyISAM hoặc engine nontransactional khác không được bảo vệ bởi snapshot transaction; dữ liệu có thể thay đổi trong lúc dump.
- Tránh các thao tác DDL đồng thời như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE` trên đối tượng đang dump. DDL có thể làm dump lỗi hoặc khiến kết quả không còn phản ánh trạng thái mong muốn.
- `--single-transaction` không thay thế chiến lược khóa nếu phạm vi có table nontransactional.

`--quick` giúp client đọc hàng theo luồng, giảm nhu cầu giữ toàn bộ kết quả truy vấn trong bộ nhớ. Nó hữu ích với table lớn và thường được bật mặc định thông qua `--opt`.

### 6.2. Khi có table nontransactional

Nếu cần tính nhất quán cho table nontransactional, có thể phải dùng cơ chế khóa đọc phù hợp, chẳng hạn `--lock-all-tables`. Tùy chọn này lấy global read lock trong quá trình dump và có thể chặn các thao tác ghi, ảnh hưởng trực tiếp đến hoạt động production.

```bash
mysqldump --user=backup_user --password \
  --lock-all-tables --quick \
  --databases legacy_app \
  > legacy-app-locked.sql
```

Chỉ chọn phương án khóa sau khi đánh giá thời gian dump, dung lượng, tải ghi và mức chấp nhận gián đoạn. Không bật khóa toàn server theo thói quen cho mọi database. Nếu hệ thống dùng nhiều storage engine, hãy phân loại table trước khi chọn chiến lược.

### 6.3. DDL và thay đổi schema trong lúc dump

Một snapshot dữ liệu không tự bảo vệ khỏi thay đổi cấu trúc đồng thời. Trong cửa sổ backup, hãy phối hợp với quy trình migration để tránh sửa hoặc đổi tên đối tượng đang được dump. Với hệ thống triển khai liên tục, nên có quy ước rõ ràng về thời điểm migration, backup và restore test.

## 7. Quyền và credential cần cho mysqldump

Tài khoản backup cần quyền đủ để đọc dữ liệu và metadata trong phạm vi chọn. Các tùy chọn như dump routines, events, tablespaces hoặc thông tin replication có thể yêu cầu thêm quyền tùy phiên bản và cấu hình server.

Tạo tài khoản chuyên biệt và cấp quyền theo phạm vi backup. Ví dụ minh họa cho một database:

```sql
CREATE USER 'backup_user'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT, SHOW VIEW, TRIGGER, EVENT
ON sales.*
TO 'backup_user'@'10.20.%';
```

Đây chỉ là ví dụ quyền cơ bản cho một số nhu cầu dump; không phải bộ quyền đầy đủ cho mọi phiên bản và mọi tùy chọn. Hãy kiểm tra tài liệu phiên bản đang dùng, thử lệnh bằng đúng tài khoản backup và bổ sung quyền tối thiểu cần thiết nếu có lỗi cụ thể. Một số hoạt động có thể yêu cầu quyền global hoặc quyền động.

Không sử dụng tài khoản `root` chỉ để tránh xử lý quyền. Lưu credential bằng cơ chế phù hợp, giới hạn quyền đọc file cấu hình, bảo vệ file dump vì nó có thể chứa dữ liệu nhạy cảm, và không đưa mật khẩu vào command line hoặc log.

## 8. Khôi phục file dump

File do mysqldump tạo thường là các câu lệnh SQL. Dùng client `mysql` để thực thi file.

Nếu file được tạo bằng `--databases`:

```bash
mysql --user=restore_user --password < sales-with-database.sql
```

Các câu lệnh `CREATE DATABASE` và `USE` trong file xác định database đích. Nếu file chỉ được tạo bằng `mysqldump sales` và không có câu lệnh tạo database, hãy tạo database trước rồi import:

```sql
CREATE DATABASE sales;
```

```bash
mysql --user=restore_user --password sales < sales.sql
```

Với dump chỉ gồm một vài table, hãy chuẩn bị các table phụ thuộc và schema đích trước khi import. Với dump có `--no-create-info`, bắt buộc kiểm tra schema đã tồn tại và tương thích. Với dump chứa routines hoặc events, kiểm tra tài khoản restore có quyền tạo các đối tượng đó và DEFINER có hợp lệ trên server đích.

Trước khi restore vào production, hãy xác định file có chứa các lệnh `DROP` hay không, database đích có trùng tên với database nguồn không, và dữ liệu hiện tại sẽ bị ghi đè như thế nào. Dùng môi trường cô lập để kiểm thử toàn bộ quy trình.

## 9. Kiểm tra phạm vi và chất lượng file dump

Một lệnh kết thúc với exit code thành công chưa đủ để chứng minh bản backup dùng được. Hãy kiểm tra cả file, nội dung và khả năng khôi phục.

### 9.1. Kiểm tra lệnh và file đầu ra

Ghi nhận phiên bản client:

```bash
mysqldump --version
mysql --version
```

Trong script tự động, kiểm tra exit code của mysqldump trước khi đánh dấu job thành công. Khi dùng redirect `>`, shell có thể tạo file rỗng ngay cả khi lệnh dump thất bại; hãy kiểm tra kích thước, thời gian cập nhật và log lỗi. Có thể ghi log stderr riêng trong script để điều tra.

### 9.2. Kiểm tra các đối tượng có mặt

Mở file dump bằng công cụ đọc văn bản và xác nhận có các phần dự kiến:

- `CREATE DATABASE` và `USE` nếu đã chọn `--databases`.
- `CREATE TABLE` cùng câu lệnh chèn dữ liệu nếu dump cả cấu trúc và dữ liệu.
- `CREATE VIEW` cho view nằm trong phạm vi.
- `CREATE TRIGGER` cho trigger cần khôi phục.
- `CREATE PROCEDURE` hoặc `CREATE FUNCTION` khi dùng `--routines`.
- Định nghĩa event khi dùng `--events`.

Có thể tìm chuỗi bằng `grep` hoặc công cụ tương đương, nhưng việc tìm chuỗi chỉ là bước rà soát nhanh. Cú pháp, điều kiện DEFINER và dependency phải được xác minh bằng cách restore thật.

### 9.3. Restore thử

Khôi phục vào instance hoặc database thử nghiệm có phiên bản tương thích. Sau đó:

1. Kiểm tra số database, table, view và routine đã được tạo.
2. So sánh số lượng hàng của các table quan trọng với số liệu tại thời điểm backup hoặc báo cáo kiểm soát phù hợp.
3. Chạy truy vấn nghiệp vụ đại diện và kiểm tra ràng buộc khóa ngoại.
4. Kiểm tra trigger, stored routine và event; không để event staging chạy tác vụ production ngoài ý muốn.
5. Xem log restore để phát hiện warning, lỗi charset, thiếu DEFINER hoặc thiếu quyền.

Một bản backup chỉ được xem là đáng tin cậy khi có thể khôi phục trong thời gian và điều kiện đáp ứng yêu cầu vận hành. Hãy lên lịch restore test định kỳ, không đợi đến khi có sự cố mới kiểm tra.

## 10. Các kịch bản mẫu

### Kịch bản A: Sao lưu database bán hàng để khôi phục toàn bộ

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales \
  > sales-full.sql
```

Phạm vi: database `sales`, cấu trúc và dữ liệu table, routines, events và triggers. Snapshot nhất quán áp dụng cho table InnoDB; cần phối hợp tránh DDL đồng thời. File có câu lệnh tạo/chọn database do `--databases`.

### Kịch bản B: Sao lưu riêng các table phục vụ báo cáo

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  reporting daily_sales monthly_sales \
  > reporting-tables.sql
```

Phạm vi: hai table được chọn trong database `reporting`. Cần kiểm tra view, routine hoặc table phụ thuộc nếu báo cáo cần chúng để hoạt động sau restore.

### Kịch bản C: Tạo schema rỗng cho môi trường thử nghiệm

```bash
mysqldump --user=backup_user --password \
  --no-data --databases sales \
  > sales-empty-schema.sql
```

Phạm vi: cấu trúc database và table được chọn, không có hàng dữ liệu. Kiểm tra thêm view, trigger, routine và event có được đưa vào đúng yêu cầu hay không.

### Kịch bản D: Xuất một tập con đơn hàng để phân tích

```bash
mysqldump --user=backup_user --password \
  sales orders \
  --where="created_at >= '2026-01-01' AND status = 'completed'" \
  > completed-orders-sample.sql
```

Phạm vi: các hàng trong `sales.orders` thỏa điều kiện. Nếu cần các dòng chi tiết `order_items`, hãy thiết kế thêm bước trích xuất theo danh sách `order_id` đã chọn; không giả định mysqldump tự suy ra quan hệ dữ liệu.

### Kịch bản E: Bỏ table log khỏi bản dump

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --ignore-table=sales.audit_log \
  --ignore-table=sales.api_request_log \
  > sales-without-logs.sql
```

Phạm vi: database `sales` ngoại trừ hai table log. Trước khi áp dụng, xác nhận các table này thực sự có thể tái tạo hoặc không cần cho mục tiêu phục hồi. Ghi lại ngoại lệ trong tài liệu backup để người khôi phục hiểu được phần dữ liệu bị loại.

## 11. Những lỗi thiết kế phạm vi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Dùng `--databases sales orders` với ý định dump table `orders` | `orders` bị hiểu là tên database thứ hai | Dùng `mysqldump sales orders` để dump table trong một database. |
| Dump một vài table nhưng quên khóa ngoại hoặc bảng phụ thuộc | Restore thất bại hoặc dữ liệu thiếu quan hệ | Lập danh sách dependency trước khi chọn table. |
| Không thêm `--routines` | Thiếu procedure và function | Xác định ứng dụng có gọi stored routine không; bật `--routines` khi cần. |
| Quên `--events` | Tác vụ theo lịch không được khôi phục | Kiểm kê event và đưa `--events` vào script nếu cần. |
| Dùng `--skip-triggers` ngoài ý muốn | Logic tự động gắn với table bị mất | Giữ trigger trong dump hoặc ghi rõ lý do loại bỏ. |
| Dùng `--no-create-info` với schema đích khác phiên bản | Dữ liệu không khớp cấu trúc hoặc import lỗi | Kiểm tra DDL đích và restore thử. |
| Dùng `--single-transaction` với MyISAM và cho rằng mọi table nhất quán | Table nontransactional có thể phản ánh thời điểm khác nhau | Phân loại storage engine và chọn chiến lược khóa phù hợp. |
| Chạy DDL trong lúc dump | Dump có thể lỗi hoặc không phản ánh trạng thái schema mong muốn | Điều phối migration và backup theo cửa sổ rõ ràng. |
| Chỉ kiểm tra file tồn tại | Có thể giữ file rỗng hoặc dump thiếu đối tượng | Kiểm tra exit code, nội dung và restore test. |

## 12. Quy trình chọn và xác minh mysqldump

Trước khi viết lệnh backup, hãy trả lời các câu hỏi theo thứ tự:

1. **Mục tiêu phục hồi là gì?** Khôi phục toàn instance, một database, một nhóm table hay chỉ dữ liệu mẫu?
2. **Đối tượng nào phải có?** Liệt kê table, view, trigger, stored procedure, function và event mà ứng dụng cần.
3. **Cần cấu trúc và dữ liệu hay một phần?** Chọn mặc định, `--no-data`, `--no-create-info`, `--where` hoặc `--ignore-table` theo mục tiêu.
4. **Dữ liệu có thể thay đổi trong lúc dump không?** Xác định storage engine và chọn `--single-transaction` hoặc chiến lược khóa phù hợp.
5. **Tài khoản backup có quyền đủ hẹp không?** Thử bằng đúng tài khoản chạy job và bổ sung quyền tối thiểu theo lỗi thực tế.
6. **Có thể restore ở đâu?** Chuẩn bị môi trường thử nghiệm, phiên bản tương thích và tài khoản restore.
7. **Đã xác minh file chưa?** Kiểm tra exit code, dung lượng, nội dung, đối tượng và kết quả restore.

### Checklist vận hành

- [ ] Lệnh chọn đúng phạm vi: `db_name`, `--databases` hoặc `--all-databases`.
- [ ] Danh sách table được chọn hoặc loại bỏ đã được review.
- [ ] Cấu trúc và dữ liệu được xuất đúng mục tiêu.
- [ ] Views, triggers, routines và events đã được kiểm tra.
- [ ] Chiến lược snapshot phù hợp với InnoDB và các engine khác đang dùng.
- [ ] Không có migration DDL xung đột trong thời gian dump.
- [ ] Credential được bảo vệ và tài khoản backup có quyền tối thiểu cần thiết.
- [ ] File đầu ra được kiểm tra kích thước, log và exit code.
- [ ] Đã restore thử và xác minh các thao tác nghiệp vụ quan trọng.
- [ ] Các thành phần ngoài file SQL như cấu hình, keyring, plugin và binary log được xử lý theo kế hoạch phục hồi riêng.

`mysqldump` chỉ hữu ích khi phạm vi xuất khớp với phạm vi cần khôi phục. Hãy xác định database và table trước, kiểm kê các đối tượng phụ thuộc, chọn tùy chọn snapshot theo storage engine, rồi chứng minh bản dump có thể restore bằng một lần thử nghiệm có kiểm soát.
