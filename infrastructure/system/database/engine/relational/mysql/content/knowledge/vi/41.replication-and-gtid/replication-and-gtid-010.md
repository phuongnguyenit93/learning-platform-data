# Replication filter và rủi ro với giao dịch xuyên database

MySQL replication filter cho phép replica chỉ áp dụng một phần sự kiện nhận từ source, chẳng hạn chỉ giữ một schema hoặc một nhóm bảng. Cách làm này có thể hữu ích khi tạo replica phục vụ báo cáo hay tách một tập dữ liệu nhỏ hơn. Tuy nhiên, filter không hiểu quan hệ nghiệp vụ giữa các bảng. Một transaction trên source có thể cập nhật nhiều database nhưng replica chỉ áp dụng một phần thay đổi, khiến dữ liệu ở replica không còn phản ánh trạng thái nhất quán mà ứng dụng đã commit.

Rủi ro đặc biệt lớn với giao dịch xuyên database (cross-database transaction). Ví dụ, một giao dịch vừa cập nhật `sales.orders` vừa cập nhật `billing.invoices`. Nếu replica lọc bỏ `billing`, đơn hàng có thể chuyển sang trạng thái đã thanh toán trong khi hóa đơn vẫn chưa được đánh dấu đã thanh toán. Với GTID, việc transaction được ghi nhận là đã xử lý không có nghĩa mọi thay đổi đã bị filter bỏ sẽ tự động được phát lại sau này.

Bài học này giải thích vị trí của replication filter, sự khác nhau giữa lọc theo database và lọc theo table, tác động của `binlog_format`, cách GTID tương tác với filter và quy trình kiểm thử trước khi dùng replica đã lọc trong production.

## 1. Replication filter hoạt động ở đâu?

Trong replication bất đồng bộ, source ghi các sự kiện vào binary log. Replica nhận sự kiện, lưu vào relay log rồi applier đọc relay log và quyết định sự kiện nào được áp dụng. Các replication filter thông thường được cấu hình ở replica và tác động tại bước áp dụng.

```text
Ứng dụng
   |
   v
MySQL source
   |  commit transaction
   v
Binary log (các sự kiện của transaction)
   |
   |  kết nối replication
   v
Relay log trên replica
   |
   v
Replication applier + filter
   |                         |
   | sự kiện được giữ        | sự kiện bị lọc
   v                         v
Cập nhật bảng replica      Bỏ qua thay đổi tương ứng
```

Filter không ngăn source ghi dữ liệu vào database và cũng không phải cơ chế phân quyền truy cập. Người có quyền đọc binary log ở source vẫn có thể tiếp cận dữ liệu được ghi trong log. Nếu mục tiêu là giới hạn quyền xem dữ liệu, cần dùng tài khoản và quyền SQL phù hợp; nếu mục tiêu là tạo tập dữ liệu riêng, cần thiết kế pipeline trích xuất hoặc đồng bộ có chủ đích.

Phân biệt hai nhóm cấu hình:

- **Source-side binary log filter:** `binlog-do-db` và `binlog-ignore-db` tác động tới nội dung source ghi vào binary log. Các replica nhận log không thể áp dụng những sự kiện source đã không ghi.
- **Replica-side replication filter:** `replicate-do-db`, `replicate-ignore-db`, `replicate-do-table`, `replicate-ignore-table`, `replicate-wild-do-table` và `replicate-wild-ignore-table` tác động tới việc replica áp dụng sự kiện.

Hai nhóm này có phạm vi và cách đánh giá khác nhau. Không dùng tên tùy chọn tương tự nhau như thể chúng có cùng ngữ nghĩa. Bài này tập trung vào filter ở replica.

## 2. Các loại replication filter

Các tùy chọn thường gặp gồm:

| Tùy chọn | Mục đích |
|---|---|
| `replicate-do-db` | Chỉ áp dụng sự kiện thuộc database được chỉ định, theo quy tắc phụ thuộc định dạng log. |
| `replicate-ignore-db` | Bỏ qua sự kiện thuộc database được chỉ định, theo quy tắc phụ thuộc định dạng log. |
| `replicate-do-table` | Chỉ áp dụng thay đổi phù hợp với database và table được chỉ định. |
| `replicate-ignore-table` | Bỏ qua thay đổi phù hợp với database và table được chỉ định. |
| `replicate-wild-do-table` | Chỉ áp dụng table khớp mẫu wildcard. |
| `replicate-wild-ignore-table` | Bỏ qua table khớp mẫu wildcard. |

Ví dụ cấu hình chỉ lấy các bảng trong schema `sales`:

```ini
[mysqld]
replicate-wild-do-table=sales.%
```

Ví dụ bỏ qua các bảng audit trong schema `sales`:

```ini
[mysqld]
replicate-wild-ignore-table=sales.audit_%
```

Ký tự `%` khớp chuỗi ký tự bất kỳ trong mẫu wildcard của các tùy chọn này. Hãy kiểm tra cú pháp và cách xử lý ký tự đặc biệt theo phiên bản MySQL đang vận hành. Không đặt các quy tắc chồng lấn mà chưa xác định rõ kết quả khi nhiều filter cùng khớp.

Các filter có thể được đặt qua tùy chọn khởi động hoặc thay đổi bằng `CHANGE REPLICATION FILTER` trên những phiên bản hỗ trợ. Ví dụ minh họa:

```sql
STOP REPLICA SQL_THREAD;

CHANGE REPLICATION FILTER
  REPLICATE_WILD_DO_TABLE = ('sales.%');

START REPLICA SQL_THREAD;
```

Ví dụ này dùng cú pháp của MySQL 8.0 và minh họa thay đổi filter trong lúc dừng applier. Trước khi chạy, xác nhận quyền quản trị replication, trạng thái channel, cú pháp đúng phiên bản và ảnh hưởng của việc dừng SQL thread. Với replication nhiều channel, cần xác định filter áp dụng toàn cục hay cho một channel cụ thể bằng cú pháp `FOR CHANNEL` tương ứng. Ghi lại cấu hình cũ để có thể khôi phục.

## 3. Khác biệt giữa STATEMENT và ROW

Đây là điểm dễ gây lỗi nhất khi sử dụng filter theo database. Với `replicate-do-db` và `replicate-ignore-db`, MySQL đánh giá database theo cách khác nhau tùy định dạng binary log.

### Statement-based logging

Với `binlog_format=STATEMENT`, filter database dựa vào database mặc định đang được chọn bằng `USE`, thay vì luôn dựa vào database được ghi rõ trong tên bảng của câu SQL.

Ví dụ:

```sql
USE sales;
UPDATE billing.invoices
SET paid = 1
WHERE invoice_id = 9001;
```

Nếu replica dùng `replicate-do-db=sales`, câu lệnh trên có thể được xem là thuộc database mặc định `sales` và được áp dụng, dù bảng được cập nhật thực tế nằm trong `billing`. Ngược lại:

```sql
USE billing;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 9001;
```

Filter theo database mặc định có thể khiến câu lệnh bị bỏ qua dù bảng đích thuộc `sales`.

Vì vậy, khi dùng statement-based replication, không suy luận kết quả filter chỉ từ tên schema được ghi trước tên bảng trong câu SQL. Cần xem database mặc định tại thời điểm câu lệnh chạy và kiểm thử đúng câu lệnh thực tế của ứng dụng.

### Row-based logging

Với `binlog_format=ROW`, binary log chứa sự kiện thay đổi hàng. Filter database được đánh giá theo database chứa bảng bị thay đổi. Điều này trực quan hơn khi câu lệnh dùng tên database đầy đủ, nhưng có thể làm một transaction xuyên database chỉ được áp dụng một phần.

Ví dụ source chạy:

```sql
START TRANSACTION;

UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 9001;

UPDATE billing.invoices
SET paid = 1
WHERE order_id = 9001;

COMMIT;
```

Nếu replica chỉ áp dụng `sales` bằng filter database trong chế độ row-based, thay đổi ở `sales.orders` có thể được giữ còn thay đổi ở `billing.invoices` bị bỏ qua. Source đã commit cả hai thay đổi trong cùng một transaction InnoDB; replica không còn thể hiện đầy đủ kết quả nghiệp vụ của transaction đó.

Với `replicate-do-table` và các filter wildcard theo table, việc khớp được xét theo đối tượng bảng và có các quy tắc riêng đối với statement, row event và câu lệnh tác động nhiều bảng. Không suy rộng kết quả của một filter database sang filter table. Đặc biệt, DDL và các câu lệnh tác động nhiều bảng cần được kiểm thử riêng theo phiên bản và `binlog_format`.

### Bảng so sánh khi chọn filter

| Tiêu chí | Filter database | Filter table/wildcard |
|---|---|---|
| Phạm vi | Toàn database/schema | Bảng cụ thể hoặc mẫu bảng |
| Statement-based | `do-db`/`ignore-db` phụ thuộc database mặc định được chọn | Có quy tắc khớp bảng riêng; câu lệnh nhiều bảng cần thử nghiệm |
| Row-based | Dựa trên database của bảng có thay đổi | Dựa trên table được thay đổi |
| Rủi ro chính | Có thể lọc sai do giả định về database mặc định; bỏ một phần thay đổi xuyên schema | Có thể bỏ các bảng phụ thuộc trong cùng transaction hoặc bỏ sót bảng mới |
| Khi cân nhắc | Chỉ khi ranh giới database phù hợp với ranh giới nghiệp vụ | Khi cần chọn bảng cụ thể và đã lập bản đồ quan hệ phụ thuộc |

Với hệ thống mới, row-based logging thường giúp sự kiện phản ánh thay đổi dữ liệu thực tế rõ hơn, nhưng không làm replication filter trở nên an toàn về mặt nghiệp vụ. Nếu filter loại bỏ một phần row event, replica vẫn có thể thiếu dữ liệu liên quan.

## 4. Rủi ro của giao dịch xuyên database

Một transaction xuyên database là transaction cập nhật từ hai schema trở lên trong cùng một lần commit. Với InnoDB, source có thể commit các thay đổi này như một đơn vị nguyên tử. Ứng dụng có thể dựa vào điều đó để bảo đảm các bảng liên quan luôn chuyển trạng thái cùng nhau.

Ví dụ hệ thống thương mại điện tử có ba schema:

- `sales.orders`: trạng thái đơn hàng.
- `billing.invoices`: trạng thái hóa đơn.
- `inventory.stock`: số lượng tồn kho.

Một thao tác xác nhận thanh toán có thể cập nhật cả ba schema trong một transaction. Nếu replica chỉ giữ `sales`, các thay đổi hóa đơn và tồn kho không được áp dụng. Các truy vấn báo cáo trên replica có thể cho thấy đơn hàng đã thanh toán trong khi tồn kho và hóa đơn chưa thay đổi.

Các hậu quả có thể xuất hiện:

1. **Vi phạm bất biến nghiệp vụ:** trạng thái đơn hàng, thanh toán và tồn kho không còn đồng bộ.
2. **Sai lệch join:** báo cáo join các schema trả về số liệu thiếu hoặc trạng thái không tương thích.
3. **Khóa ngoại và tham chiếu logic không đầy đủ:** bản ghi được giữ có thể tham chiếu tới đối tượng bị filter bỏ, dù ràng buộc vật lý giữa các schema không được khai báo.
4. **Ứng dụng đọc replica ra quyết định sai:** một replica dùng cho báo cáo hoặc tác vụ nền có thể tạo hành động dựa trên dữ liệu thiếu.
5. **Failover không an toàn:** nếu promote replica đã lọc thành source mới, các dữ liệu bị bỏ qua sẽ không tự xuất hiện và topology có thể tiếp tục lan truyền trạng thái thiếu.

Không phải mọi transaction xuyên database đều chắc chắn bị chia cắt; kết quả phụ thuộc filter và loại sự kiện. Nhưng nếu transaction chạm vào cả bảng được giữ lẫn bảng bị loại, phải coi đó là nguy cơ cho tới khi kiểm thử chứng minh hành vi cụ thể.

### Ví dụ minh họa trạng thái sai lệch

**Trước transaction:**

| Bảng | Trạng thái |
|---|---|
| `sales.orders` | `PENDING` |
| `billing.invoices` | `UNPAID` |
| `inventory.stock` | `10` |

Source commit một transaction: đổi đơn hàng thành `PAID`, hóa đơn thành `PAID` và tồn kho giảm còn `9`. Replica chỉ lọc để giữ schema `sales`:

| Bảng | Source sau commit | Replica đã lọc |
|---|---|---|
| `sales.orders` | `PAID` | `PAID` |
| `billing.invoices` | `PAID` | `UNPAID` |
| `inventory.stock` | `9` | `10` |

Replica không còn đại diện cho một trạng thái nghiệp vụ hoàn chỉnh. Nếu báo cáo tính doanh thu từ `sales.orders` nhưng đối chiếu hóa đơn từ `billing.invoices`, kết quả sẽ không đáng tin cậy.

## 5. GTID và transaction bị filter

GTID (Global Transaction Identifier) định danh transaction được ghi vào binary log. Replica dùng GTID auto-position để trao đổi tập transaction đã thực thi và xác định transaction còn thiếu khi kết nối lại.

Replication filter và GTID giải quyết hai vấn đề khác nhau:

- Filter quyết định thay đổi nào được áp dụng lên dữ liệu replica.
- GTID theo dõi transaction nào đã được xử lý trong luồng replication.

Khi một transaction bị filter bỏ toàn bộ hoặc một phần, replica vẫn có thể ghi nhận GTID tương ứng là đã xử lý. Với transaction bị lọc, GTID không phải bằng chứng rằng mọi bảng trên replica đã nhận đủ thay đổi của transaction. Vì vậy, `Executed_Gtid_Set` có thể tiến lên trong khi dữ liệu của một số schema hoặc bảng vẫn thiếu so với source.

Hệ quả quan trọng: nếu sau này gỡ filter hoặc thay đổi filter để bao gồm thêm bảng, GTID auto-position không tự yêu cầu source gửi lại các transaction mà replica đã đánh dấu đã thực thi. Những thay đổi bị bỏ trước đó có thể không được bù. Cần nạp lại dữ liệu bị thiếu bằng một quy trình đồng bộ có kiểm soát, chẳng hạn tạo lại replica từ snapshot phù hợp hoặc thực hiện resync các bảng liên quan.

Kiểm tra GTID và trạng thái replication:

```sql
SHOW REPLICA STATUS\G

SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
```

Các trường `Retrieved_Gtid_Set` và `Executed_Gtid_Set` trong `SHOW REPLICA STATUS` giúp xem transaction đã nhận và đã xử lý. Chúng không đo mức đầy đủ của dữ liệu sau khi filter. Để xác minh dữ liệu, cần so sánh nội dung bảng hoặc checksum trên các schema thuộc phạm vi replica.

Không dùng thao tác thêm GTID giả vào `gtid_purged` hoặc sửa `gtid_executed` để che sai lệch dữ liệu. Các thao tác đó có thể khiến MySQL tin rằng transaction đã được xử lý mà không phục hồi được các thay đổi đã mất. Hãy xác định rõ transaction và lập kế hoạch resync trước khi sửa trạng thái GTID.

## 6. Thiết kế filter an toàn hơn

Trước khi đặt filter, lập bản đồ phụ thuộc nghiệp vụ và dữ liệu. Ranh giới schema trong MySQL không nhất thiết trùng với ranh giới dịch vụ hoặc transaction. Một ứng dụng có thể cập nhật nhiều schema trong cùng transaction, dùng trigger ghi sang schema khác hoặc gọi stored procedure tác động nhiều bảng.

Thực hiện các bước sau:

1. **Liệt kê bảng cần giữ:** xác định bảng nguồn, bảng tham chiếu, bảng tra cứu, bảng cấu hình và bảng audit cần thiết cho workload trên replica.
2. **Lập bản đồ phụ thuộc:** tìm transaction, trigger, procedure, event và tác vụ ứng dụng có thể ghi sang nhiều schema.
3. **Chọn phạm vi lọc:** ưu tiên chọn một tập dữ liệu có ranh giới nghiệp vụ rõ. Nếu cần bảng cụ thể, dùng filter table/wildcard và kiểm tra quy tắc matching.
4. **Xác định loại log:** ghi lại `binlog_format` và kiểm thử cả các câu lệnh statement-based còn tồn tại nếu topology có sử dụng.
5. **Kiểm tra DDL:** thử `CREATE`, `ALTER`, `RENAME`, `DROP`, `TRUNCATE`, trigger và procedure có liên quan. DDL thường được ghi dưới dạng query event nên không thể suy ra hoàn toàn từ thử nghiệm row event.
6. **Định nghĩa bất biến:** viết các điều kiện phải đúng trên replica, ví dụ mọi đơn `PAID` trong phạm vi phải có hóa đơn tương ứng.
7. **Kiểm tra failover:** xác định replica đã lọc có được phép promote hay chỉ được dùng cho workload đọc giới hạn.
8. **Lập kế hoạch resync:** xác định cách dựng lại dữ liệu nếu filter thay đổi hoặc phát hiện transaction bị bỏ nhầm.

Nếu mục tiêu chỉ là giảm tải truy vấn đọc, hãy cân nhắc replica đầy đủ và giới hạn quyền đọc theo schema hoặc workload. Nếu mục tiêu là cung cấp một tập dữ liệu nhỏ cho hệ thống khác, pipeline ETL/CDC có mapping và kiểm soát transaction rõ ràng thường dễ quản trị hơn việc dùng replication filter như một công cụ phân phối dữ liệu tổng quát.

## 7. Ví dụ cấu hình và cách kiểm tra

Giả sử một replica báo cáo chỉ cần các bảng trong schema `reporting` và một số bảng dimension trong `reference`. Một cấu hình wildcard minh họa:

```ini
[mysqld]
replicate-wild-do-table=reporting.%
replicate-wild-do-table=reference.dim_%
```

Trước khi triển khai, xác minh cách cấu hình nhiều giá trị của tùy chọn trong file cấu hình, cách hợp nhất nhiều rule và hành vi khi một bảng mới được tạo. Cách biểu diễn lặp tùy chọn có thể phụ thuộc parser/cấu hình MySQL; dùng đúng hình thức được tài liệu phiên bản hỗ trợ. Không sao chép ví dụ này vào production khi chưa thử trên bản clone của topology.

Kiểm tra trạng thái:

```sql
SHOW REPLICA STATUS\G
```

Chú ý các trường liên quan filter như `Replicate_Do_DB`, `Replicate_Ignore_DB`, `Replicate_Do_Table`, `Replicate_Ignore_Table`, `Replicate_Wild_Do_Table` và `Replicate_Wild_Ignore_Table`. Đồng thời theo dõi:

- `Replica_IO_Running` và `Replica_SQL_Running` để biết receiver và applier có hoạt động không.
- `Last_SQL_Error` và `Last_IO_Error` để tìm lỗi áp dụng hoặc nhận log.
- `Seconds_Behind_Source` như một chỉ báo độ trễ, không phải bằng chứng dữ liệu đầy đủ.
- `Retrieved_Gtid_Set` và `Executed_Gtid_Set` để hiểu tiến độ transaction.

Tên trường thay đổi theo phiên bản; với MySQL 8.0 hiện đại, dùng `SHOW REPLICA STATUS`. Các bản cũ có thể dùng tên `SHOW SLAVE STATUS` và trường tương ứng.

Có thể kiểm tra nội dung sự kiện source ghi bằng `mysqlbinlog` trên file không mã hóa hoặc qua remote reader nếu log đã mã hóa:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000456
```

Với row-based event, tùy chọn `-vv` giúp hiển thị chi tiết giá trị hàng ở dạng chú giải. Cần bảo vệ đầu ra vì nó có thể chứa dữ liệu nhạy cảm. Nếu binary log được mã hóa, dùng phương thức đọc từ server có keyring thay vì giả định đọc trực tiếp file trên đĩa sẽ thành công.

## 8. Quy trình thử nghiệm transaction xuyên database

Thử nghiệm nên chạy trên source và replica cô lập có cùng phiên bản, cấu hình log và filter dự kiến. Tạo hai schema mẫu:

```sql
CREATE DATABASE sales;
CREATE DATABASE billing;

CREATE TABLE sales.orders (
  order_id BIGINT PRIMARY KEY,
  status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE billing.invoices (
  invoice_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  paid TINYINT NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales.orders VALUES (1001, 'PENDING');
INSERT INTO billing.invoices VALUES (5001, 1001, 0);
```

Trên source, chạy một transaction cập nhật hai schema:

```sql
START TRANSACTION;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;

UPDATE billing.invoices
SET paid = 1
WHERE order_id = 1001;
COMMIT;
```

Sau khi replica bắt kịp, so sánh từng bảng trên source và replica. Thực hiện lại thử nghiệm với `STATEMENT` và `ROW` trên topology thử nghiệm riêng, đồng thời thay đổi database mặc định bằng `USE` và dùng tên bảng đầy đủ. Thêm các trường hợp:

- Transaction chỉ cập nhật schema được giữ.
- Transaction chỉ cập nhật schema bị loại.
- Transaction cập nhật đồng thời schema được giữ và schema bị loại.
- Câu lệnh cập nhật nhiều bảng hoặc gọi procedure/trigger có ghi chéo schema.
- DDL tạo, đổi tên hoặc xóa bảng trong phạm vi filter.
- Thay đổi filter sau khi replica đã xử lý một số GTID.

Ghi lại kết quả từng phép thử: bảng nào thay đổi, GTID nào được thực thi, lỗi applier nếu có và các bất biến nghiệp vụ có còn đúng không. Chỉ số replication chạy xanh không thay thế việc so sánh dữ liệu.

## 9. Chẩn đoán và khôi phục sai lệch

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Replica có GTID tiến lên nhưng một bảng thiếu dữ liệu | Transaction đã bị filter bỏ toàn bộ hoặc một phần | So sánh filter với transaction; lập kế hoạch resync bảng hoặc dựng lại replica. |
| Bảng ở schema được giữ có thay đổi, schema khác không đổi | Transaction xuyên database bị lọc theo schema | Xác định bất biến nghiệp vụ bị vi phạm; không dùng replica này cho truy vấn cần cả hai schema. |
| Câu SQL đủ tên schema nhưng filter cho kết quả bất ngờ | `replicate-do-db`/`ignore-db` với statement-based phụ thuộc database mặc định | Kiểm tra `USE`, `binlog_format` và sự kiện thực tế; cân nhắc filter theo table sau khi thử nghiệm. |
| Sau khi bỏ filter, replica vẫn không có dữ liệu lịch sử | GTID đã được đánh dấu xử lý khi transaction bị filter | Nạp bù/resync dữ liệu; GTID auto-position không tự phát lại transaction đã đánh dấu. |
| Replica SQL thread dừng | Lỗi áp dụng, DDL không tương thích, thiếu đối tượng hoặc sai lệch schema | Đọc `Last_SQL_Error`, kiểm tra sự kiện và schema; sửa nguyên nhân rồi tiếp tục theo quy trình vận hành. |
| Replica được promote nhưng ứng dụng phát hiện thiếu bảng/dòng | Replica vốn được thiết kế chỉ giữ một tập dữ liệu | Không promote replica đã lọc như bản thay thế đầy đủ; khôi phục từ bản replica đầy đủ hoặc backup thích hợp. |

Khi phát hiện filter sai, trước tiên dừng việc mở rộng traffic đọc hoặc promote replica. Lưu trạng thái replication, filter, GTID set và log liên quan. Sau đó xác định phạm vi dữ liệu bị bỏ, chọn phương án resync và xác minh bằng so sánh dữ liệu. Chỉ tiếp tục sau khi các bất biến của workload đã được khôi phục.

Không nên gỡ filter rồi chỉ chạy `START REPLICA` và cho rằng dữ liệu sẽ tự đầy đủ. Transaction đã được đánh dấu thực thi có thể không được gửi lại theo GTID auto-position. Việc nạp bù cần có snapshot hoặc export nhất quán, xử lý ghi đồng thời và kế hoạch tránh ghi đè thay đổi mới.

## 10. Khuyến nghị sử dụng trong kiến trúc production

Replication filter phù hợp khi tập dữ liệu replica đã được xác định rõ, phụ thuộc bảng được kiểm soát và workload chấp nhận việc dữ liệu bị lược bỏ. Một replica chỉ chứa một số bảng có thể phục vụ báo cáo giới hạn, nhưng cần mô tả rõ schema nào có mặt và truy vấn nào không được phép chạy trên đó.

Các nguyên tắc nên áp dụng:

- Không dùng replica đã lọc làm bản dự phòng failover đầy đủ nếu chưa có quy trình dựng lại các dữ liệu bị loại.
- Tránh transaction xuyên database giữa schema được giữ và schema bị loại; nếu không thể tránh, không giả định replica giữ được tính nguyên tử nghiệp vụ.
- Không xem GTID đã thực thi là bằng chứng mọi row event đã được áp dụng.
- Theo dõi thay đổi schema và bảng mới; wildcard filter có thể tự bao gồm đối tượng mới ngoài dự kiến.
- Dùng quyền SQL để giới hạn người dùng, không dùng replication filter như ranh giới bảo mật.
- Duy trì một bản backup đầy đủ và replica đầy đủ nếu yêu cầu HA cần khả năng thay thế source.
- Định kỳ kiểm tra checksum hoặc so sánh dữ liệu theo bảng thuộc phạm vi replica.

Nếu ứng dụng cần tính nhất quán giữa nhiều schema, lựa chọn an toàn thường là replication đầy đủ. Nếu chỉ cần cung cấp dữ liệu đã chọn lọc cho hệ thống khác, hãy cân nhắc CDC hoặc ETL với hợp đồng dữ liệu, thứ tự transaction và quy tắc xử lý quan hệ được xác định rõ.

## 11. Checklist trước khi đưa filter vào production

- [ ] Đã xác định rõ mục tiêu và workload của replica; mọi consumer biết dữ liệu nào bị loại.
- [ ] Đã ghi nhận phiên bản MySQL, `binlog_format` và loại filter sử dụng.
- [ ] Đã phân biệt source-side `binlog-do-db`/`binlog-ignore-db` với replica-side `replicate-*`.
- [ ] Đã lập bản đồ trigger, procedure, event và transaction có ghi sang nhiều schema.
- [ ] Đã thử transaction xuyên database với `STATEMENT` và `ROW` theo cấu hình thực tế.
- [ ] Đã kiểm tra DDL, câu lệnh nhiều bảng, wildcard và bảng mới được tạo.
- [ ] Đã xác minh kết quả filter trên dữ liệu, không chỉ dựa vào trạng thái SQL thread hoặc GTID.
- [ ] Đã hiểu rằng thay đổi filter không tự bù transaction trước đó đã được đánh dấu thực thi.
- [ ] Có quy trình resync và kiểm tra dữ liệu khi filter thay đổi hoặc bị cấu hình sai.
- [ ] Replica đã lọc được đánh dấu rõ là không đủ điều kiện failover nếu không có bước phục hồi dữ liệu bị loại.
- [ ] Có backup đầy đủ và phương án phục hồi độc lập với replica đã lọc.

Replication filter là công cụ chọn sự kiện để áp dụng, không phải bộ máy hiểu transaction nghiệp vụ. Khi một transaction source cập nhật nhiều database, filter có thể làm replica chỉ nhận một phần kết quả đã commit. Kết hợp kiểm thử theo `binlog_format`, theo dõi GTID và xác minh dữ liệu thực tế giúp tránh dùng nhầm replica thiếu dữ liệu cho báo cáo, xử lý nghiệp vụ hoặc failover.
