# GTID, server_uuid, server_id và yêu cầu định danh duy nhất

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cấu trúc GTID và vai trò của UUID nguồn trong định danh transaction.
- Phân biệt `server_id` với `server_uuid`, biết nơi cấu hình và cách kiểm tra từng giá trị.
- Bảo đảm mỗi máy chủ trong topology replication có định danh duy nhất và ổn định.
- Nhận diện lỗi do sao chép datadir, snapshot hoặc cấu hình máy chủ làm trùng định danh.
- Kiểm tra `gtid_executed`, `gtid_purged`, so sánh GTID set và dùng auto-position cho replication.
- Lập kế hoạch bật GTID, thêm replica, clone máy chủ và xử lý sự cố định danh an toàn.

## 1. Vì sao replication cần định danh duy nhất?

Trong một topology MySQL, nhiều máy chủ có thể trao đổi binary log, áp dụng transaction từ nhau và tham gia failover. Máy chủ phải biết transaction nào được tạo ở đâu, transaction nào đã được thực thi và transaction nào còn cần truyền. Nếu hai máy chủ dùng chung định danh, hệ thống có thể nhầm lẫn nguồn gốc transaction, bỏ qua event hoặc phát hiện GTID trùng.

MySQL dùng hai loại định danh có vai trò khác nhau:

- **`server_id`:** số nguyên nhận diện một máy chủ trong replication topology. Nó được ghi trong metadata của binary log và được dùng trong cơ chế replication.
- **`server_uuid`:** UUID duy nhất được MySQL tạo cho máy chủ và lưu trong datadir. Trong GTID, UUID này là SID (source identifier) dùng để xác định máy chủ đã tạo transaction gốc.

GTID (Global Transaction Identifier) giúp định danh transaction trên toàn topology. Để GTID hoạt động đúng, `server_id` phải duy nhất, `server_uuid` phải duy nhất và mỗi máy chủ phải giữ định danh ổn định trong vòng đời của nó.

Ví dụ, một topology có source và hai replica:

| Máy chủ | Vai trò | `server_id` | `server_uuid` |
|---|---|---:|---|
| `mysql-source-01` | Source | 101 | `a1a1...` |
| `mysql-replica-01` | Replica | 102 | `b2b2...` |
| `mysql-replica-02` | Replica | 103 | `c3c3...` |

Các giá trị UUID trong bảng chỉ là dạng rút gọn để minh họa. Trong MySQL, UUID đầy đủ có dạng `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

Tên máy, địa chỉ IP hoặc DNS không thay thế cho hai định danh này. Đổi hostname hoặc IP không tự tạo `server_id`/`server_uuid` mới.

## 2. Cấu trúc GTID

Với MySQL GTID, một transaction có định dạng tổng quát:

```text
source_uuid:transaction_number
```

Trong đó:

- `source_uuid` là SID, thường chính là `server_uuid` của máy chủ đã tạo transaction gốc.
- `transaction_number` là số thứ tự (GNO) tăng dần trong chuỗi GTID của SID đó.

Ví dụ:

```text
a1a1a1a1-1111-2222-3333-444444444444:57
```

GTID trên định danh transaction số 57 được tạo từ máy chủ có SID `a1a1a1a1-1111-2222-3333-444444444444`.

Một máy chủ có thể đã thực thi transaction đến từ nhiều máy chủ. Vì vậy, tập GTID (GTID set) là tập hợp nhiều SID cùng các khoảng số thứ tự tương ứng. Ví dụ:

```text
a1a1a1a1-1111-2222-3333-444444444444:1-57:60-62,
b2b2b2b2-1111-2222-3333-444444444444:1-14
```

Với SID thứ nhất, tập trên chứa các transaction từ 1 đến 57 và từ 60 đến 62; các số 58 và 59 không nằm trong tập. SID thứ hai có transaction từ 1 đến 14. GTID set có thể chứa nhiều khoảng rời rạc, không nhất thiết là một dải liên tục.

GTID gắn với transaction đã commit và được ghi nhận theo cơ chế GTID của MySQL. Khi một replica áp dụng transaction từ source, nó giữ nguyên GTID gốc đó; replica không tạo một GTID mới bằng UUID của chính nó cho cùng transaction được sao chép. Các transaction được tạo cục bộ trên replica (nếu cho phép ghi) lại có thể mang SID của replica và tạo ra lịch sử riêng.

## 3. Phân biệt `server_id` và `server_uuid`

Hai giá trị này bổ sung cho nhau, không thể thay thế nhau.

| Thuộc tính | `server_id` | `server_uuid` |
|---|---|---|
| Kiểu dữ liệu | Số nguyên không dấu 32-bit | UUID 128-bit, biểu diễn thành chuỗi 36 ký tự gồm dấu gạch nối |
| Mục đích | Nhận diện server trong metadata và luồng replication | SID dùng trong GTID để nhận diện nguồn tạo transaction |
| Nơi cấu hình/lưu | Cấu hình MySQL như `my.cnf`/`my.ini`; cũng có biến hệ thống | File `auto.cnf` trong datadir, do MySQL tự tạo |
| Cách thay đổi | Cấu hình `server_id` trên từng máy; cần lưu bền vững trong cấu hình triển khai | Không đặt bằng `SET`; MySQL tự sinh khi chưa có UUID hợp lệ trong `auto.cnf` |
| Yêu cầu | Duy nhất trong topology | Duy nhất trong topology và ổn định qua lần khởi động |

### 3.1. `server_id`

`server_id` là số nguyên không dấu 32-bit. Giá trị hợp lệ để tham gia replication là từ `1` đến `4294967295` (`2^32 - 1`). Giá trị `0` không phù hợp cho một máy chủ cần tham gia replication. Giá trị mặc định có thể là `1`, vì vậy không nên để tất cả máy chủ dùng mặc định.

Đặt một giá trị riêng cho mỗi máy chủ trong cấu hình:

```ini
[mysqld]
server_id=101
log_bin=mysql-bin
```

Trên replica khác, dùng giá trị khác, ví dụ `server_id=102`. Lưu cấu hình trong file cấu hình được triển khai cùng máy chủ để giá trị không quay về mặc định sau khi restart.

Có thể kiểm tra giá trị đang chạy:

```sql
SELECT @@GLOBAL.server_id AS server_id;
```

`server_id` được dùng trong replication event và giúp MySQL nhận diện nguồn event. Nếu hai máy chủ có cùng `server_id`, replica có thể xử lý sai event, bỏ qua event bị xem như do chính nó tạo hoặc phát sinh lỗi replication. Trong replication nhiều tầng, hãy bảo đảm mọi thành viên có ID riêng, không chỉ source và replica kết nối trực tiếp.

### 3.2. `server_uuid`

Khi MySQL khởi động lần đầu với datadir chưa có `auto.cnf`, máy chủ tạo UUID và lưu trong file này. File thường nằm ở thư mục dữ liệu, có nội dung dạng:

```ini
[auto]
server-uuid=a1a1a1a1-1111-2222-3333-444444444444
```

Kiểm tra UUID bằng SQL:

```sql
SELECT @@GLOBAL.server_uuid AS server_uuid;
```

`server_uuid` là biến chỉ đọc. Không đặt nó bằng `SET GLOBAL`, không sửa thủ công nội dung `auto.cnf` và không tạo UUID bằng cách sao chép chuỗi từ máy chủ khác.

MySQL cần giữ UUID ổn định qua các lần restart để GTID của cùng một máy chủ tiếp tục thuộc cùng SID. Nếu UUID tự thay đổi sau mỗi lần khởi động, lịch sử transaction sẽ bị chia thành nhiều SID và việc quản lý GTID trở nên khó khăn.

## 4. Quy tắc định danh duy nhất trong topology

Mọi máy chủ tham gia cùng topology replication phải có:

1. `server_id` khác nhau.
2. `server_uuid` khác nhau.
3. Định danh được lưu bền vững qua restart.
4. Hồ sơ định danh được ghi nhận cùng hostname, IP, vai trò, phiên bản và trạng thái replication.

Ví dụ bảng kiểm kê nên lưu đầy đủ:

| Hostname | IP / endpoint | Vai trò | `server_id` | `server_uuid` | GTID mode |
|---|---|---|---:|---|---|
| `mysql-source-01` | `10.20.0.11` | Source | 101 | UUID đầy đủ | ON |
| `mysql-replica-01` | `10.20.0.12` | Replica | 102 | UUID đầy đủ | ON |
| `mysql-replica-02` | `10.20.0.13` | Replica | 103 | UUID đầy đủ | ON |

Trong thực tế, không nên ghi UUID rút gọn trong bảng quản lý chính thức. Hãy lưu chuỗi đầy đủ để có thể phát hiện trùng lặp.

### 4.1. Kiểm tra trên từng máy chủ

Chạy trên source và tất cả replica:

```sql
SELECT
  @@hostname AS hostname,
  @@port AS port,
  @@GLOBAL.server_id AS server_id,
  @@GLOBAL.server_uuid AS server_uuid,
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.enforce_gtid_consistency AS enforce_gtid_consistency;
```

Ghi lại kết quả và so sánh toàn topology. SQL chạy trên một máy chủ chỉ hiển thị định danh của chính máy đó; MySQL không tự cung cấp một câu lệnh duy nhất để liệt kê toàn bộ UUID của các host không kết nối. Dùng inventory, công cụ quản lý cấu hình hoặc truy vấn từng endpoint để đối chiếu.

### 4.2. Không dùng cùng định danh cho môi trường khác

Máy chủ staging, QA hoặc disaster recovery có thể được tạo từ bản sao production. Nếu chúng cùng kết nối vào một topology replication hoặc có khả năng gửi binlog cho nhau, chúng cũng cần định danh riêng. Tốt nhất, mỗi môi trường có dải `server_id` được quy hoạch riêng và danh mục UUID được quản lý tập trung.

Nếu môi trường thử nghiệm bị cô lập hoàn toàn, việc dùng chung định danh không làm hỏng production ngay lập tức, nhưng sẽ gây rủi ro khi môi trường đó được kết nối vào topology, dùng làm nguồn failover hoặc được khôi phục thành máy chủ thật. Hãy xử lý định danh ngay từ quy trình tạo máy.

## 5. Rủi ro khi clone hoặc sao chép datadir

Một lỗi phổ biến xảy ra khi tạo replica bằng cách sao chép nguyên datadir, snapshot volume hoặc image máy ảo từ một server đang chạy. Bản sao có thể mang theo `auto.cnf` và cấu hình `server_id` của máy nguồn.

Kết quả có thể là hai máy chủ có cùng:

- `server_id` do cấu hình `my.cnf`/`my.ini` được sao chép.
- `server_uuid` do file `auto.cnf` được sao chép.

Nếu hai máy cùng tham gia replication, chúng có thể tạo ra GTID cùng SID và cùng số thứ tự, dẫn đến xung đột định danh hoặc replication không thể hoạt động đúng.

### 5.1. Quy trình với bản sao datadir vật lý

Khi tạo một máy chủ mới từ bản sao vật lý của datadir, cần xử lý identity trước khi đưa nó vào topology:

1. Dừng MySQL trên máy mới và xác nhận tiến trình đã dừng hoàn toàn.
2. Kiểm tra cấu hình được sao chép, đặt `server_id` riêng cho máy mới.
3. Nếu đây là một thành viên mới có identity riêng, loại bỏ file `auto.cnf` của **máy mới** khi MySQL đang dừng, để MySQL tự tạo UUID mới ở lần khởi động tiếp theo.
4. Khởi động máy mới và kiểm tra `@@server_uuid`, `@@server_id`.
5. So sánh hai giá trị với mọi thành viên hiện có trước khi cấu hình replication hoặc cho phép ghi.
6. Kiểm tra GTID history và thiết lập replication theo phương thức đã chọn.

Không xóa `auto.cnf` trên máy chủ gốc hoặc máy chủ đang hoạt động. Không xóa file này nếu mục tiêu là khôi phục chính máy chủ cũ với identity cũ. Việc tạo UUID mới chỉ áp dụng cho một thành viên mới cần định danh riêng.

### 5.2. Khi dùng MySQL Clone Plugin hoặc công cụ backup

Các công cụ clone, backup vật lý và snapshot có quy tắc riêng về identity, metadata replication và GTID. Không giả định mọi công cụ đều sao chép hoặc tự tạo lại `server_uuid` giống nhau. Đọc hướng dẫn của đúng công cụ/phiên bản, sau đó luôn xác minh giá trị thực tế trên máy đích trước khi kết nối replication.

Nếu hai máy có UUID trùng và đã cùng chạy, không tự ý xóa `auto.cnf` rồi restart để chữa lỗi. Máy chủ có thể đã tạo transaction với SID trùng; thay UUID không viết lại lịch sử GTID cũ. Cần ngăn các máy tiếp tục ghi ngoài ý muốn, thu thập GTID set và log, xác định máy nào là bản chuẩn, rồi lập phương án dựng lại hoặc đồng bộ lịch sử có kiểm soát.

## 6. GTID mode và điều kiện nhất quán

GTID được điều khiển bởi hai biến quan trọng:

- `gtid_mode`: quy định máy chủ có tạo và xử lý GTID hay không.
- `enforce_gtid_consistency`: ngăn các thao tác không tương thích với GTID consistency.

Để sử dụng GTID đầy đủ, cần bật binary logging, đặt `enforce_gtid_consistency=ON` và `gtid_mode=ON` trên các máy chủ liên quan. Kiểm tra:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'enforce_gtid_consistency';
```

Khi `gtid_mode=ON`, các transaction được ghi vào binary log phải có GTID. Để bảo đảm lịch sử có thể phát lại an toàn, MySQL áp dụng các giới hạn consistency. Ví dụ, tạo hoặc xóa temporary table bên trong transaction hay stored program và trộn thay đổi transactional với nontransactional table trong cùng transaction có thể bị từ chối. Quy tắc với `CREATE TABLE ... SELECT` đã thay đổi theo phiên bản, vì vậy phải kiểm tra tài liệu đúng bản MySQL đang chạy trước khi đưa mẫu SQL đó vào quy trình.

Hãy xử lý warning từ `enforce_gtid_consistency=WARN` trước khi chuyển sang `ON`. Không nên tắt consistency chỉ để một batch script cũ chạy được; cần sửa quy trình SQL hoặc chia transaction theo cách tương thích.

### 6.1. Các trạng thái chuyển tiếp của GTID

MySQL hỗ trợ các trạng thái `gtid_mode`:

| Trạng thái | Ý nghĩa |
|---|---|
| `OFF` | Transaction được ghi theo kiểu anonymous, không dùng GTID |
| `OFF_PERMISSIVE` | Transaction mới có thể anonymous; vẫn chấp nhận transaction có GTID |
| `ON_PERMISSIVE` | Transaction mới dùng GTID; vẫn chấp nhận transaction anonymous đã tồn tại trong luồng replication |
| `ON` | Transaction mới phải có GTID; không chấp nhận anonymous transaction |

Thứ tự chuyển đổi được hỗ trợ là:

```text
OFF
  -> OFF_PERMISSIVE
  -> ON_PERMISSIVE
  -> ON
```

Đây là các bước chuyển trạng thái, không phải một giá trị cấu hình duy nhất. Khi chuyển một topology đang hoạt động, phải phối hợp tất cả source và replica theo đúng trình tự của tài liệu MySQL. Tránh chuyển một máy sang `ON` khi máy khác vẫn đang phát anonymous transaction.

Trước khi chuyển:

1. Bật `enforce_gtid_consistency=WARN` và xử lý mọi cảnh báo.
2. Bảo đảm `log_bin=ON`, `server_id` duy nhất và `server_uuid` duy nhất trên tất cả máy.
3. Chuyển lần lượt qua `OFF_PERMISSIVE`, rồi `ON_PERMISSIVE` trên toàn topology.
4. Chờ các transaction anonymous đang truyền được áp dụng hết.
5. Kiểm tra `ONGOING_ANONYMOUS_TRANSACTION_COUNT` bằng 0 trên các máy chủ phù hợp.
6. Chuyển sang `gtid_mode=ON` theo trình tự được hỗ trợ, rồi xác minh replication và GTID set.

Kiểm tra transaction anonymous còn đang chạy:

```sql
SHOW GLOBAL STATUS LIKE 'ONGOING_ANONYMOUS_TRANSACTION_COUNT';
```

Việc bật GTID trên hệ thống có dữ liệu và replication hiện hữu cần kế hoạch thay đổi có cửa sổ, backup và phương án khôi phục. Với topology mới, có thể cấu hình các điều kiện GTID ngay từ đầu thay vì thực hiện quy trình chuyển tiếp.

## 7. Kiểm tra GTID history

MySQL cung cấp các biến trạng thái quan trọng:

- `gtid_executed`: tập GTID đã được thực thi trên máy chủ, bao gồm transaction được thực thi cục bộ và transaction đã áp dụng từ source.
- `gtid_purged`: tập GTID đã được thực thi nhưng các binary log chứa những transaction đó đã bị purge khỏi máy chủ.
- `gtid_owned`: các GTID hiện đang được transaction sở hữu trong quá trình thực thi; thường dùng cho chẩn đoán nâng cao.

Kiểm tra:

```sql
SELECT @@GLOBAL.gtid_executed AS gtid_executed;
SELECT @@GLOBAL.gtid_purged AS gtid_purged;
```

`gtid_purged` là một phần của lịch sử đã thực thi. Khi một replica cần transaction đã bị purge khỏi binlog của source, source không thể gửi lại transaction đó từ log hiện có. Replica phải được seed lại từ backup phù hợp hoặc source phải lấy lại log từ kho lưu trữ nếu còn bản sao.

### 7.1. So sánh GTID set

Các hàm GTID giúp so sánh lịch sử:

```sql
-- Kiểm tra tập thứ nhất có nằm trong tập thứ hai không.
SELECT GTID_SUBSET(
  'a1a1a1a1-1111-2222-3333-444444444444:1-50',
  'a1a1a1a1-1111-2222-3333-444444444444:1-60'
);

-- Tìm các GTID có trong tập thứ nhất nhưng không có trong tập thứ hai.
SELECT GTID_SUBTRACT(
  'a1a1a1a1-1111-2222-3333-444444444444:1-60',
  'a1a1a1a1-1111-2222-3333-444444444444:1-50'
);
```

Trong ví dụ, tập `1-50` là tập con của `1-60`; phép trừ trả về khoảng `51-60`. Khi so sánh source và replica, hãy dùng GTID set đầy đủ lấy từ hai máy chủ và lưu kết quả cùng thời điểm kiểm tra.

Có thể chờ một máy chủ áp dụng đến một GTID set:

```sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'a1a1a1a1-1111-2222-3333-444444444444:1-60',
  30
);
```

Giá trị trả về `0` nghĩa là đã chờ đến khi tập GTID được thực thi; `1` nghĩa là hết thời gian chờ. Hàm này hữu ích trong kiểm thử failover hoặc đồng bộ trước khi chạy truy vấn đọc sau khi ghi.

## 8. GTID auto-positioning

Với replication dùng file/position, người vận hành phải ghi nhớ tên file binary log và vị trí byte trên source. GTID auto-position cho phép replica và source trao đổi GTID set để source chỉ gửi các transaction mà replica còn thiếu.

Trên MySQL 8.0.23 trở lên, cấu hình replica bằng cú pháp source/replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source-01.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

Ví dụ giả định thông tin tài khoản replication đã được thiết lập theo quy trình bảo mật. Nếu cần cấu hình `SOURCE_USER`, `SOURCE_PASSWORD` hoặc TLS, hãy dùng quy trình quản lý bí mật và chứng chỉ của tổ chức; không đưa mật khẩu thật vào script được commit hoặc log.

Trên các phiên bản MySQL trước 8.0.23, cú pháp cũ là `CHANGE MASTER TO ... MASTER_AUTO_POSITION=1` và `START SLAVE`. Dùng đúng tên lệnh theo phiên bản server.

### 8.1. Điều kiện để auto-position hoạt động

- GTID phải được bật và cấu hình phù hợp trên source và replica.
- Source phải giữ binary log chứa các transaction mà replica còn thiếu.
- Replica phải có GTID history đúng với backup hoặc trạng thái seed ban đầu.
- `server_id` và `server_uuid` của mọi thành viên phải duy nhất.
- Không được có transaction ngoài ý muốn chỉ xuất hiện trên replica (errant transaction) làm sai lệch lịch sử dự kiến.
- Không cấu hình đồng thời auto-position và tọa độ file/position thủ công cho cùng channel; `SOURCE_AUTO_POSITION=1` thay thế cách chỉ định file và vị trí binlog.

Nếu source đã purge các GTID mà replica chưa có, auto-position không thể tự tạo lại những transaction đó. Cần khôi phục replica từ backup mới hơn hoặc nạp lại các binary log còn thiếu từ kho lưu trữ.

### 8.2. Kiểm tra trạng thái replica

```sql
SHOW REPLICA STATUS\G
```

Một số trường cần quan sát:

| Trường | Ý nghĩa |
|---|---|
| `Source_UUID` | UUID của source mà replica đang kết nối |
| `Auto_Position` | `1` nếu channel dùng GTID auto-position |
| `Retrieved_Gtid_Set` | GTID đã nhận từ source |
| `Executed_Gtid_Set` | GTID đã thực thi trên replica |
| `Last_IO_Error` | Lỗi của luồng nhận binlog |
| `Last_SQL_Error` | Lỗi khi áp dụng transaction |
| `Seconds_Behind_Source` | Ước lượng độ trễ; không phải phép đo đầy đủ mọi dạng lag |

Nếu có nhiều replication channel, `SHOW REPLICA STATUS` hiển thị trạng thái theo channel; hãy xác định đúng channel cần kiểm tra. Có thể dùng Performance Schema để quan sát lỗi kết nối và tập GTID nhận được:

```sql
SELECT
  CHANNEL_NAME,
  SOURCE_UUID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE
FROM performance_schema.replication_connection_status;
```

## 9. Errant transaction và tác động của ghi cục bộ trên replica

Một errant transaction là transaction được tạo trực tiếp trên replica nhưng không có trên source chuẩn hoặc các thành viên còn lại. Transaction đó mang GTID có SID của replica. Khi replica được promote hoặc khi các thành viên trao đổi GTID set, lịch sử này có thể khiến hệ thống không thể chọn source mới như dự kiến.

Ví dụ, ứng dụng vô tình kết nối vào replica với `super_read_only=OFF` và chạy:

```sql
INSERT INTO maintenance_note(note)
VALUES ('created on replica');
```

Transaction này được tạo cục bộ trên replica, có thể mang SID từ `server_uuid` của replica. Source chính không có GTID đó. Khi chuyển vai trò hoặc cấu hình auto-position, transaction riêng có thể làm GTID set của replica vượt khỏi lịch sử của source.

Để tránh:

- Bật `read_only=ON` và `super_read_only=ON` trên replica phục vụ đọc khi kiến trúc yêu cầu không ghi cục bộ.
- Dùng tài khoản ứng dụng chỉ có quyền đọc trên replica.
- Không dùng tài khoản quản trị rộng cho ứng dụng.
- Theo dõi GTID set của source và replica, đặc biệt trước failover.
- Chỉ tạo transaction cục bộ trên replica khi có thiết kế rõ ràng cho multi-source hoặc quy trình vận hành đặc biệt.

Không xóa một GTID khỏi lịch sử bằng cách sửa trực tiếp bảng hệ thống. Nếu phát hiện errant transaction, dừng thao tác thay đổi vai trò, xác định nội dung và nguồn gốc transaction, rồi xử lý theo runbook phù hợp. Có thể cần rebuild replica từ source chuẩn để đưa lịch sử về trạng thái mong muốn.

## 10. Failover và phục hồi identity

Khi promote một replica thành source mới, identity của máy chủ được promote vẫn là identity của nó. Không đổi `server_uuid` chỉ vì vai trò thay đổi. GTID set đã nhận từ source cũ tiếp tục là lịch sử đã thực thi; transaction mới tạo trên source mới sẽ dùng SID của `server_uuid` của source mới.

Trước khi promote:

1. Xác nhận source cũ đã dừng ghi hoặc được cô lập để tránh split-brain.
2. So sánh `gtid_executed` giữa các replica và chọn máy có lịch sử phù hợp, đầy đủ nhất.
3. Kiểm tra không có errant transaction ngoài dự kiến.
4. Chờ replica được chọn áp dụng hết GTID cần thiết theo tiêu chí RPO.
5. Promote theo runbook, cấu hình các replica còn lại trỏ đến source mới bằng GTID auto-position.
6. Kiểm tra `server_id`, `server_uuid`, GTID set, replication channel và quyền ghi.

Không tái sử dụng cùng một `server_id` hoặc `server_uuid` cho hai tiến trình mysqld đang chạy trong topology. Nếu máy chủ cũ được khôi phục để làm replica mới, phải xác định nó là cùng logical server hay một thành viên mới. Nếu là thành viên mới được tạo từ bản sao vật lý, xử lý identity như phần clone trước khi kết nối.

## 11. Chẩn đoán lỗi định danh và GTID

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lỗi báo source và replica có cùng UUID | `auto.cnf` bị sao chép từ máy khác hoặc hai instance dùng cùng datadir clone | Dừng kết nối replication; xác định node mới; tạo UUID riêng đúng quy trình khi mysqld đã dừng; xác minh trước khi kết nối lại |
| Hai máy có cùng `server_id` | Cấu hình máy chủ được sao chép hoặc dùng giá trị mặc định | Gán ID riêng, lưu trong file cấu hình và xác minh toàn topology |
| Auto-position báo source không có transaction cần thiết | Source đã purge binlog chứa GTID replica còn thiếu | Nạp lại log từ kho lưu trữ hoặc seed replica từ backup mới hơn |
| GTID set của replica có SID lạ | Replica có transaction cục bộ, hoặc được seed từ một lịch sử khác | Dùng `GTID_SUBTRACT` để tìm phần khác biệt; xác định nguồn gốc trước khi thay đổi topology |
| Replication dừng khi bật GTID | Còn anonymous transaction, thao tác không GTID-consistent hoặc cấu hình chưa đồng nhất | Kiểm tra `gtid_mode`, `enforce_gtid_consistency`, anonymous count và error log; hoàn tất chuyển đổi theo từng bước |
| Replica báo lỗi duplicate GTID | Lịch sử transaction bị trùng hoặc identity/seed history không đúng | Ngừng thay đổi tự động; thu thập GTID set và binlog, xác định source chuẩn và xây dựng lại replica nếu cần |
| GTID set không tiến triển dù kết nối đang chạy | I/O thread, SQL applier, filter, lỗi event hoặc source không còn log cần thiết | Kiểm tra `SHOW REPLICA STATUS`, Performance Schema, error log và relay log |

Không dùng `RESET MASTER`, `RESET BINARY LOGS AND GTIDS` hoặc chỉnh `gtid_purged` như một bước thử lỗi thông thường. Các lệnh reset có thể xóa binary log hoặc thay đổi lịch sử GTID và làm mất khả năng phục hồi. Chỉ dùng khi đã có kế hoạch được kiểm chứng, backup và hiểu rõ ảnh hưởng trên đúng phiên bản MySQL.

## 12. Checklist trước khi đưa máy chủ vào topology

Trước khi thêm một source hoặc replica mới, xác nhận:

- [ ] `server_id` là số khác 0, nằm trong phạm vi hợp lệ và chưa được cấp cho máy khác.
- [ ] `server_uuid` được MySQL tạo riêng và khác UUID của tất cả thành viên khác.
- [ ] `auto.cnf` không phải bản sao identity của máy chủ khác.
- [ ] `log_bin=ON` nếu máy chủ cần phát binlog.
- [ ] `gtid_mode` và `enforce_gtid_consistency` phù hợp với topology.
- [ ] GTID history của backup/seed được hiểu rõ; không có transaction lạ ngoài dự kiến.
- [ ] Phiên bản MySQL và cấu hình replication tương thích với source.
- [ ] Replica có `read_only`/`super_read_only` theo chính sách.
- [ ] Tài khoản replication, TLS và quyền truy cập được cấu hình an toàn.
- [ ] `SHOW REPLICA STATUS` không có lỗi và GTID set tiến triển đúng.

## 13. Bài tập thực hành

Một nhóm vận hành tạo `mysql-replica-03` bằng cách copy datadir của `mysql-source-01`. Sau khi khởi động, cả hai máy trả về cùng `server_uuid` và cùng `server_id`. Replica chưa được thêm vào topology.

Hãy thực hiện các bước trên môi trường lab:

1. Thu thập `@@hostname`, `@@server_id`, `@@server_uuid`, `@@gtid_mode` và `@@gtid_executed` trên hai máy.
2. Xác định file cấu hình cung cấp `server_id` và vị trí datadir chứa `auto.cnf` trên replica mới.
3. Dừng mysqld trên replica mới; đặt `server_id` chưa được sử dụng và xử lý `auto.cnf` để MySQL sinh UUID mới khi khởi động.
4. Khởi động lại replica, xác nhận UUID mới khác source và giữ nguyên UUID source.
5. So sánh GTID history và kiểm tra backup/seed đã phù hợp trước khi thiết lập auto-position.
6. Cấu hình replication bằng `SOURCE_AUTO_POSITION=1`, khởi động replica và theo dõi `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, lỗi I/O và lỗi SQL.
7. Chứng minh replica không tạo transaction cục bộ bằng cách kiểm tra quyền ứng dụng và trạng thái `super_read_only`.

Không thực hiện bài tập trên máy production hoặc datadir duy nhất đang phục vụ hệ thống. Mục tiêu là hiểu cách identity được tạo, lưu và kiểm chứng trước khi kết nối replication.

**Câu hỏi tự kiểm tra:**

1. Trong GTID `a1a1...:57`, phần UUID và số `57` biểu thị điều gì?
2. Vì sao `server_id` và `server_uuid` đều phải duy nhất?
3. File nào lưu `server_uuid`, và vì sao không được chỉnh sửa thủ công file đó?
4. Điều gì xảy ra nếu sao chép nguyên datadir và `auto.cnf` sang một thành viên mới?
5. `gtid_executed` khác `gtid_purged` ở điểm nào?
6. GTID auto-position chọn transaction cần truyền dựa trên thông tin nào?
7. Vì sao transaction được tạo cục bộ trên replica có thể trở thành errant transaction?
8. Khi promote replica thành source, có cần tạo `server_uuid` mới không? Giải thích.

## Kết luận

`server_id` nhận diện máy chủ trong luồng replication; `server_uuid` cung cấp SID để định danh nguồn tạo GTID. Mỗi thành viên cần hai giá trị duy nhất và ổn định. GTID set cho biết transaction nào đã được thực thi, còn auto-position dùng các tập này để tự xác định phần transaction replica còn thiếu. Hãy kiểm tra identity trước khi kết nối, xử lý cẩn thận datadir clone, bảo vệ GTID history và xác minh toàn bộ topology trước failover hoặc phục hồi.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Replication and Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.4/en/replication-options.html)
- [MySQL 8.4 Reference Manual — Global Transaction Identifiers](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids.html)
- [MySQL 8.4 Reference Manual — GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html)
- [MySQL 8.4 Reference Manual — GTID Mode](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-mode.html)
- [MySQL 8.4 Reference Manual — The `server_id` System Variable](https://dev.mysql.com/doc/refman/8.4/en/replication-options.html#sysvar_server_id)
- [MySQL 8.4 Reference Manual — The `server_uuid` System Variable](https://dev.mysql.com/doc/refman/8.4/en/replication-options.html#sysvar_server_uuid)
