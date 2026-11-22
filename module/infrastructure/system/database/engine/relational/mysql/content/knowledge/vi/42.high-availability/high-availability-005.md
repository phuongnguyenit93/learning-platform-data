# Distributed recovery, clone và điều kiện thành viên gia nhập

Khi một máy chủ mới gia nhập MySQL Group Replication hoặc một thành viên cũ quay lại sau thời gian gián đoạn, máy chủ đó phải nhận đủ các giao dịch mà nhóm đã commit trong lúc nó vắng mặt. Quá trình đồng bộ trạng thái này được gọi là **distributed recovery**. Group Replication tự chọn thành viên cung cấp dữ liệu (donor) và chuyển các giao dịch còn thiếu sang thành viên đang gia nhập (joiner).

Group Replication có hai cách chuyển trạng thái chính. Nếu donor còn giữ các giao dịch cần thiết trong binary log và khoảng chênh lệch đủ nhỏ, joiner nhận các giao dịch còn thiếu qua channel `group_replication_recovery`. Nếu khoảng chênh lệch lớn hoặc binary log của các donor không còn đủ giao dịch, Group Replication có thể dùng Clone plugin để sao chép dữ liệu từ donor rồi tiếp tục nhận các giao dịch phát sinh trong lúc clone. Thành viên chỉ trở thành `ONLINE` sau khi đã áp dụng đầy đủ giao dịch của nhóm.

Bài học dùng MySQL 8.4 và cú pháp Group Replication hiện hành. Nội dung tập trung vào Group Replication gốc, nền tảng của InnoDB Cluster; các thao tác quản trị qua MySQL Shell có thể tự động hóa một số bước cấu hình tương tự.

## Mục tiêu

Sau bài học, bạn có thể:

- Mô tả các giai đoạn distributed recovery và vai trò của donor, joiner.
- Phân biệt state transfer từ binary log với remote cloning.
- Hiểu cách `group_replication_clone_threshold` quyết định khi nào dùng clone.
- Chuẩn bị Clone plugin, tài khoản recovery và các điều kiện tương thích.
- Kiểm tra điều kiện GTID, cấu hình, dữ liệu và mạng trước khi thêm thành viên.
- Theo dõi trạng thái `RECOVERING`, `ONLINE`, lỗi donor và các tình huống không thể tự phục hồi.

## 1. Distributed recovery là gì?

Group Replication duy trì một nhóm máy chủ có chung lịch sử giao dịch đã được chứng nhận và commit. Khi một thành viên mới tham gia, hoặc một thành viên quay lại sau khi bị ngắt kết nối, nó có thể thiếu một số giao dịch mà các thành viên khác đã áp dụng. Joiner phải bắt kịp lịch sử đó trước khi được phép tham gia xử lý giao dịch bình thường.

Hai vai trò trong quá trình này:

| Vai trò | Trách nhiệm |
|---|---|
| Donor | Thành viên đang `ONLINE`, cung cấp giao dịch từ binary log hoặc dữ liệu thông qua Clone plugin. |
| Joiner | Máy chủ đang gia nhập hoặc tái gia nhập nhóm; nhận và áp dụng trạng thái còn thiếu. |

Distributed recovery dùng channel riêng có tên `group_replication_recovery`. Đây là kết nối replication trực tiếp giữa joiner và donor, khác với kết nối group communication dùng để trao đổi thông điệp thành viên, chứng nhận giao dịch và thay đổi view.

### 1.1. Các giai đoạn phục hồi

Quy trình tổng quát:

```text
START GROUP_REPLICATION trên joiner
              |
              v
Kiểm tra relay log group_replication_applier
              |
              v
Chọn donor phù hợp đang ONLINE
              |
              v
Chọn phương pháp state transfer
       /                      \
      v                        v
Nhận giao dịch từ         Clone dữ liệu từ donor
binary log donor          rồi khởi động lại joiner
      |                        |
      |                 Nhận giao dịch phát sinh
      |                 trong lúc clone từ binlog
       \                      /
        v                    v
Áp dụng các giao dịch còn thiếu và giao dịch đã buffer
              |
              v
Đã bắt kịp lịch sử của nhóm
              |
              v
            ONLINE
```

Trước khi kết nối donor, joiner kiểm tra relay log của channel `group_replication_applier`. Nếu máy chủ từng ở trong nhóm và đã nhận nhưng chưa áp dụng hết một số giao dịch, nó áp dụng các giao dịch còn chờ trước. Một máy chủ hoàn toàn mới thường không có phần việc này.

Sau đó joiner kết nối tới một donor đang hoạt động để lấy trạng thái. Trong khi state transfer diễn ra, nhóm vẫn có thể commit giao dịch mới. Joiner tiếp tục nhận hoặc buffer các giao dịch mới này, áp dụng chúng sau phần state transfer ban đầu. Chỉ khi mọi giao dịch cần thiết đã được áp dụng, Group Replication mới chuyển joiner sang `ONLINE`.

## 2. State transfer từ binary log

Đây là cơ chế cơ bản của distributed recovery. Joiner kết nối tới donor bằng channel `group_replication_recovery`, hoạt động tương tự một replica bất đồng bộ. Donor gửi các giao dịch mà joiner chưa có; replication applier áp dụng chúng theo thứ tự phù hợp.

Điều kiện quan trọng là binary log của ít nhất một donor phù hợp phải còn chứa toàn bộ giao dịch joiner cần nhận. Group Replication dùng GTID set để xác định phần lịch sử còn thiếu và kiểm tra liệu các giao dịch đó còn khả dụng trong binary log hay đã bị purge.

Ví dụ:

- Nhóm đã thực thi GTID từ `...:1-1500`.
- Joiner đã có `...:1-1450`.
- Nếu donor còn giữ binary log chứa giao dịch `1451` đến `1500`, joiner có thể nhận phần chênh lệch bằng state transfer từ binary log.
- Nếu các giao dịch cần thiết đã bị purge khỏi mọi donor, phương pháp này không thể hoàn thành.

Số GTID trong ví dụ chỉ để minh họa. Trong thực tế, GTID set có thể gồm nhiều SID và nhiều khoảng số giao dịch; không nên suy ra khoảng thiếu bằng cách trừ hai số cuối đơn giản.

### 2.1. Vì sao cần giữ binary log đủ lâu?

Binary log trên các thành viên nhóm là nguồn dữ liệu cho incremental recovery. Nếu một thành viên offline quá lâu và các giao dịch nó cần đã bị purge khỏi tất cả donor, nó không thể bắt kịp chỉ bằng binary log.

Thời gian lưu binary log cần tính đến:

- Khoảng thời gian thành viên có thể offline.
- Thời gian phát hiện sự cố và chuẩn bị máy chủ quay lại.
- Thời gian kết nối, truyền và áp dụng giao dịch.
- Lượng giao dịch phát sinh trong thời gian recovery.

Kiểm tra trạng thái GTID và chính sách lưu binary log trên từng máy chủ:

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;

SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

`gtid_executed` cho biết tập GTID đã thực thi trên instance; `gtid_purged` cho biết các GTID đã được thực thi nhưng không còn nằm trong binary log hiện có. Nếu giao dịch joiner cần nằm trong `gtid_purged` của mọi donor phù hợp, state transfer từ binary log không thể cung cấp chúng nữa.

### 2.2. Khi nào binary log recovery không đủ?

Có hai trường hợp phổ biến:

1. Joiner thiếu rất nhiều giao dịch, khiến việc truyền từng giao dịch từ binary log mất nhiều thời gian và gây tải lớn cho donor.
2. Các giao dịch joiner cần không còn trong binary log của bất kỳ donor nào.

Trong trường hợp thứ hai, Clone plugin có thể là phương án tự động để cấp lại trạng thái đầy đủ. Nếu clone không được cài đặt, không có donor phù hợp hoặc clone thất bại trên tất cả donor, joiner không thể tự hoàn tất distributed recovery. Quản trị viên phải chuẩn bị lại dữ liệu từ một nguồn snapshot hợp lệ hoặc xử lý nguyên nhân khiến clone không thể chạy.

## 3. Clone plugin trong distributed recovery

Clone plugin cho phép Group Replication sao chép dữ liệu vật lý từ donor sang joiner. Group Replication quản lý thao tác clone tự động khi các thành viên được cấu hình hỗ trợ. Người vận hành chỉ cần chuẩn bị plugin, tài khoản recovery và ngưỡng clone trước khi joiner bắt đầu gia nhập.

Clone thường phù hợp khi:

- Joiner là máy chủ mới chưa có dữ liệu của nhóm.
- Joiner đã offline lâu và thiếu lượng giao dịch lớn.
- Binary log của các donor không còn đủ các giao dịch joiner cần.
- Cần giảm thời gian truyền và áp dụng một lượng lớn giao dịch riêng lẻ.

### 3.1. Điều kiện cài đặt

Ít nhất một thành viên hiện có có khả năng làm donor và joiner phải được chuẩn bị cho remote cloning. Để có nhiều lựa chọn donor và tăng khả năng phục hồi, nên cài đặt và kích hoạt Clone plugin trên tất cả thành viên hiện tại và các thành viên dự kiến gia nhập trong tương lai.

Kiểm tra plugin trên từng máy chủ:

```sql
SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME IN ('clone', 'group_replication');
```

Nếu plugin chưa được cài, trên Linux có thể cài bằng:

```sql
INSTALL PLUGIN clone SONAME 'mysql_clone.so';
```

Clone plugin và Group Replication plugin phải được cài và ở trạng thái active trên donor và joiner. Nếu donor đang dùng plugin khác, chẳng hạn keyring plugin để quản lý khóa mã hóa, plugin tương ứng cũng phải được cài và active trên joiner để dữ liệu được giải mã đúng sau clone.

### 3.2. Tương thích giữa donor và joiner

Đối với clone trong Group Replication, donor và joiner cần đáp ứng các điều kiện sau:

- Chạy cùng hệ điều hành.
- Thuộc cùng MySQL Server release series. Ví dụ, không clone trực tiếp giữa series 8.0 và 8.4.
- Clone plugin và Group Replication plugin đã được cài, kích hoạt trên cả hai máy.
- Các plugin cần thiết trên donor, như keyring plugin, cũng có trên joiner.
- Donor đáp ứng quy tắc chọn donor của clone; trong MySQL 8.4, donor clone được chọn theo cùng patch version với joiner.
- Cấu hình TLS và chứng thư phù hợp nếu distributed recovery sử dụng SSL.

Clone thay thế dữ liệu và data dictionary trên joiner. Remote clone có thể xóa tablespace do người dùng tạo và dữ liệu hiện có trên joiner trước khi truyền dữ liệu từ donor. Nếu thao tác bị dừng giữa chừng, joiner có thể chỉ còn dữ liệu một phần hoặc không còn dữ liệu người dùng. Group Replication có cơ chế thử lại với donor khác, nhưng máy chủ vẫn cần được giữ ngoài luồng phục vụ ứng dụng cho đến khi recovery hoàn tất.

### 3.3. Tài khoản và quyền cho Clone

Trong distributed recovery, Group Replication dùng chính tài khoản replication recovery làm clone user trên donor. Vì vậy, tài khoản này cần `BACKUP_ADMIN` trên các thành viên có hỗ trợ cloning, bao gồm cả joiner sau khi nó trở thành thành viên và có thể làm donor.

Các quyền cần có trên tài khoản recovery trong MySQL 8.4:

| Quyền | Mục đích |
|---|---|
| `REPLICATION SLAVE` | Thiết lập kết nối recovery và đọc giao dịch từ donor. |
| `CONNECTION_ADMIN` | Giữ kết nối Group Replication hoạt động trong một số tình huống instance chuyển sang offline mode. |
| `BACKUP_ADMIN` | Cho phép tài khoản recovery làm clone user trên donor khi sử dụng Clone plugin. |
| `GROUP_REPLICATION_STREAM` | Cần khi nhóm dùng MySQL communication stack. |

Tạo cùng tài khoản recovery trên các thành viên hiện có và joiner. Ví dụ:

```sql
CREATE USER 'rpl_user'@'10.20.30.%'
IDENTIFIED BY 'replace_with_secret';

GRANT REPLICATION SLAVE ON *.*
TO 'rpl_user'@'10.20.30.%';

GRANT CONNECTION_ADMIN ON *.*
TO 'rpl_user'@'10.20.30.%';

-- Cần khi sử dụng Clone plugin cho distributed recovery.
GRANT BACKUP_ADMIN ON *.*
TO 'rpl_user'@'10.20.30.%';

-- Chỉ cấp khi group communication stack là MYSQL.
GRANT GROUP_REPLICATION_STREAM ON *.*
TO 'rpl_user'@'10.20.30.%';
```

Nếu nhóm dùng XCom communication stack, không cần cấp `GROUP_REPLICATION_STREAM` cho mục đích này. Hãy giới hạn host theo mạng quản trị thực tế và sử dụng mật khẩu riêng. Cùng một tài khoản recovery và thông tin xác thực phải được cấu hình nhất quán trên mọi thành viên.

Trong Group Replication, joiner sử dụng tài khoản nội bộ `mysql.session` có quyền `CLONE_ADMIN` để khởi chạy clone ở phía recipient. Group Replication tự cấu hình `clone_valid_donor_list` theo donor được chọn. Vì vậy, không cần tự cấp `CLONE_ADMIN` cho tài khoản recovery hoặc tự quản lý allowlist clone cho quy trình này.

### 3.4. Cấu hình ngưỡng clone

Biến `group_replication_clone_threshold` xác định khoảng cách giao dịch giữa donor và joiner, tính theo số giao dịch, vượt quá mức nào thì Group Replication ưu tiên remote clone khi clone khả thi.

```sql
SHOW VARIABLES LIKE 'group_replication_clone_threshold';
```

Trong MySQL 8.4, giá trị mặc định là `9223372036854775807`, gần như vô hiệu hóa việc chọn clone nếu binary log recovery vẫn có thể thực hiện. Khi muốn Group Replication dùng clone cho các khoảng chênh lệch lớn, hãy đặt ngưỡng phù hợp với kích thước dữ liệu và tốc độ phát sinh giao dịch của nhóm.

Ví dụ minh họa đặt ngưỡng 100.000 giao dịch:

```sql
SET PERSIST group_replication_clone_threshold = 100000;
```

Giá trị này chỉ là ví dụ; hãy đo thời gian clone và tốc độ giao dịch thực tế trước khi chọn ngưỡng production. Thay đổi biến có thể thực hiện khi Group Replication đang chạy, nhưng chỉ có hiệu lực sau khi dừng và khởi động lại Group Replication trên thành viên đó. Nên cấu hình trước khi joiner bắt đầu recovery.

Không đặt ngưỡng quá thấp trong một nhóm đang có nhiều giao dịch. Nếu nhóm phát sinh số giao dịch vượt ngưỡng trong lúc clone đang chạy, sau khi joiner khởi động lại nó có thể lại vượt ngưỡng và bắt đầu clone thêm lần nữa. Điều này có thể tạo vòng lặp clone liên tục. Hãy chọn ngưỡng cao hơn lượng giao dịch dự kiến trong suốt thời gian một thao tác clone hoàn tất.

Ngay cả khi ngưỡng chưa bị vượt, Group Replication vẫn có thể dùng clone nếu giao dịch cần thiết không còn trong binary log của bất kỳ donor nào và clone có thể thực hiện. Trong trường hợp đó, ngưỡng không thể được dùng để tắt clone, vì clone là lựa chọn tự động còn lại ngoài việc cấp lại dữ liệu thủ công.

### 3.5. Clone hoàn tất và joiner khởi động lại

Khi clone hoàn tất, joiner được khởi động lại. Nếu `group_replication_start_on_boot=ON` và các thiết lập cần thiết đã được lưu trong file cấu hình hoặc bằng `SET PERSIST`, Group Replication có thể tự tiếp tục sau khi máy chủ khởi động. Clone cũng chuyển các replication metadata repository cần thiết để tiếp tục replication; vì vậy, credentials đã lưu trong metadata trên donor có thể được chuyển sang joiner.

Nếu `group_replication_start_on_boot=OFF`, quản trị viên phải chạy lại `START GROUP_REPLICATION` sau khi clone khởi động lại. Nếu credentials chỉ được truyền trong câu lệnh `START GROUP_REPLICATION USER=..., PASSWORD=...`, phải cung cấp lại `USER` và `PASSWORD` trong lệnh sau restart vì thông tin đó chỉ lưu trong bộ nhớ. Nếu đã lưu credentials bằng `CHANGE REPLICATION SOURCE TO` cho channel recovery, lệnh `START GROUP_REPLICATION` có thể dùng thông tin trong metadata repository.

Clone chuyển trạng thái dữ liệu và metadata cần thiết để xác định điểm tiếp tục, nhưng không thay thế toàn bộ binary log và relay log của donor. Sau khi restart, joiner vẫn cần kết nối donor để nhận các giao dịch nhóm đã commit trong thời gian clone diễn ra. Vì vậy donor phải còn giữ các giao dịch đó trong binary log.

## 4. Điều kiện thành viên mới được gia nhập nhóm

Distributed recovery chỉ bắt đầu sau khi máy chủ vượt qua các kiểm tra tương thích ban đầu. Một máy chủ có thể xuất hiện ở trạng thái `OFFLINE` hoặc `ERROR` trong lúc kiểm tra cấu hình; trạng thái `RECOVERING` thể hiện nó đang nhận và áp dụng dữ liệu. Điều kiện cần được chuẩn bị trước khi chạy `START GROUP_REPLICATION`.

### 4.1. Điều kiện cấu hình máy chủ

Các thành viên trong Group Replication cần có các thiết lập nền tảng sau:

| Thiết lập | Yêu cầu |
|---|---|
| `server_id` | Số nguyên dương duy nhất trong toàn bộ topology replication. |
| `server_uuid` | Phải duy nhất giữa các instance; không dùng bản sao data directory tạo ra UUID trùng lặp. |
| `log_bin` | Bật binary logging. |
| `log_replica_updates` | Bật để ghi lại giao dịch nhận từ donor và giao dịch áp dụng từ nhóm. |
| `binlog_format` | Dùng `ROW`. |
| `gtid_mode` | Đặt `ON`. |
| `enforce_gtid_consistency` | Đặt `ON`. |
| `group_replication_group_name` | Cùng một UUID hợp lệ trên tất cả thành viên. |
| `group_replication_local_address` | Địa chỉ group communication riêng, duy nhất và có thể truy cập từ các thành viên khác. |
| `group_replication_group_seeds` | Danh sách địa chỉ các thành viên có thể dùng để khám phá nhóm. |
| `group_replication_bootstrap_group` | `OFF` trên joiner; chỉ bật tạm thời khi tạo/bootstrap nhóm theo quy trình riêng. |

Trong MySQL 8.4, binary logging, `binlog_format=ROW` và `log_replica_updates=ON` là các mặc định phổ biến, nhưng vẫn nên xác minh cấu hình thực tế. GTID và `enforce_gtid_consistency` phải được bật để Group Replication hoạt động.

Ví dụ cấu hình tối thiểu minh họa cho joiner:

```ini
[mysqld]
server_id=103
log_bin=binlog
log_replica_updates=ON
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON

group_replication_group_name="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
group_replication_local_address="db3.example.internal:33061"
group_replication_group_seeds="db1.example.internal:33061,db2.example.internal:33061"
group_replication_bootstrap_group=OFF
group_replication_start_on_boot=OFF
```

Các giá trị hostname, UUID, port và `server_id` là ví dụ. Hãy dùng `group_replication_group_name` giống hệt nhóm hiện tại; `group_replication_local_address` phải là địa chỉ riêng của joiner. Với XCom communication stack, nhóm thường dùng một cổng group communication riêng như `33061`; không nhầm cổng này với cổng SQL mà donor sử dụng cho recovery và clone.

`group_replication_bootstrap_group` phải luôn `OFF` khi một thành viên thông thường gia nhập nhóm đang chạy. Bật biến này sai thời điểm có thể tạo một nhóm độc lập cùng tên thay vì thêm thành viên vào nhóm hiện hữu.

### 4.2. Điều kiện dữ liệu và schema

Group Replication yêu cầu dữ liệu được quản lý bằng InnoDB. Các bảng được replicate phải có primary key hoặc khóa unique tương đương với các cột `NOT NULL` để xác định duy nhất từng hàng khi kiểm tra xung đột giao dịch.

Trước khi join:

- Chuyển các bảng MyISAM, MEMORY hoặc storage engine không phù hợp sang InnoDB.
- Bảo đảm mọi bảng ứng dụng có primary key hoặc khóa unique `NOT NULL` hợp lệ.
- Đối chiếu schema và phiên bản ứng dụng với các thành viên đang chạy.
- Đồng nhất `lower_case_table_names` giữa các thành viên.
- Đồng nhất `default_table_encryption` giữa các thành viên.

Có thể dùng cấu hình để ngăn tạo bảng bằng engine không phù hợp:

```ini
disabled_storage_engines="MyISAM,BLACKHOLE,FEDERATED,ARCHIVE,MEMORY"
```

Đây là thiết lập kiểm soát bổ sung; hãy đánh giá ứng dụng trước khi áp dụng vì nó có thể chặn các thao tác tạo bảng dùng engine đã liệt kê.

### 4.3. Điều kiện GTID history

GTID set của joiner phải tương thích với lịch sử giao dịch của nhóm. Joiner có thể thiếu một phần giao dịch và được distributed recovery bổ sung, nhưng không được chứa giao dịch riêng không tồn tại trên các thành viên hiện có.

Các giao dịch thừa (extra transactions) thường xuất hiện khi quản trị viên chạy lệnh ghi trên máy chủ trong lúc Group Replication đang dừng. Những giao dịch này tạo GTID ngoài lịch sử chung. Nếu joiner có extra transactions:

- Clone sẽ xóa các giao dịch và dữ liệu tương ứng khi thay thế data directory.
- State transfer từ binary log có thể xung đột với các giao dịch riêng đó.
- Group Replication từ chối hoàn tất recovery để tránh làm mất hoặc trộn lịch sử dữ liệu.

Kiểm tra GTID trên joiner và các thành viên hiện có:

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
```

Nếu cần chạy thao tác quản trị cục bộ trên một thành viên khi Group Replication đang dừng và không muốn tạo GTID ngoài luồng, có thể tắt binary logging cho session quản trị:

```sql
SET SESSION sql_log_bin = 0;

-- Thực hiện thao tác quản trị cần thiết tại đây.

SET SESSION sql_log_bin = 1;
```

Chỉ thực hiện khi hiểu rõ ảnh hưởng của thao tác. Các thay đổi không được ghi binary log sẽ không được truyền sang các thành viên khác; không dùng cách này để tạo dữ liệu ứng dụng mà nhóm cần đồng bộ.

Nếu joiner đã có extra transactions, hãy kiểm tra binary log để xác định nội dung giao dịch và chọn phương án tái đồng bộ an toàn, thường là clone từ một thành viên đang ở trong nhóm. Không tự sửa `gtid_purged` hoặc xóa GTID history chỉ để vượt qua kiểm tra gia nhập.

### 4.4. Điều kiện mạng và donor

Các thành viên cần liên lạc hai chiều liên tục qua mạng group communication. Trước khi gia nhập, xác nhận:

- Joiner có thể kết nối tới các địa chỉ trong `group_replication_group_seeds`.
- Các thành viên hiện có có thể kết nối ngược tới `group_replication_local_address` của joiner.
- Firewall cho phép cổng group communication và cổng SQL dùng cho distributed recovery.
- IP allowlist của Group Replication cho phép các địa chỉ peer khi dùng XCom.
- DNS phân giải nhất quán; hostname trong cấu hình phải trỏ tới địa chỉ mà các thành viên thực sự truy cập được.
- Tài khoản recovery tồn tại và có đúng quyền trên các donor.
- TLS và chứng thư phù hợp với cấu hình bảo mật của group communication và distributed recovery.

Donor phải đang `ONLINE` và có thể phục vụ joiner. Với state transfer từ binary log, donor phải còn các giao dịch cần thiết. Với clone, donor phải thỏa các điều kiện tương thích về hệ điều hành, release series, plugin và patch version. Group Replication chọn ngẫu nhiên một donor trong danh sách thành viên `ONLINE` phù hợp; quản trị viên không phải chỉ định donor cố định cho mỗi lần join. Trong MySQL 8.4, donor cho binary log recovery có patch version thấp hơn hoặc bằng joiner; donor cho remote clone phải cùng patch version với joiner.

### 4.5. Điều kiện tương thích phiên bản

Các thành viên phải nằm trong tổ hợp phiên bản được Group Replication hỗ trợ. Trong quá trình nâng cấp, nhóm có thể tạm thời chạy các phiên bản khác nhau theo quy trình rolling upgrade và giới hạn giao thức tương thích. Không nên thêm một phiên bản tùy ý vào nhóm đang chạy; kiểm tra chính sách tương thích và communication protocol version của MySQL trước khi gia nhập.

Riêng đối với clone, điều kiện chặt hơn: donor và joiner phải chạy cùng hệ điều hành và cùng release series. Quy tắc chọn donor cho binary log recovery và clone cũng có thể khác nhau theo patch version. Nếu clone không khả thi vì khác phiên bản hoặc nền tảng, Group Replication có thể thử state transfer từ binary log nếu các giao dịch cần thiết vẫn còn.

## 5. Cấu hình recovery user và khởi động joiner

Sau khi cấu hình máy chủ và dữ liệu, chuẩn bị thông tin đăng nhập cho channel `group_replication_recovery`.

### 5.1. Lưu credentials trong replication metadata

Ví dụ trên joiner:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_USER = 'rpl_user',
  SOURCE_PASSWORD = 'replace_with_secret'
FOR CHANNEL 'group_replication_recovery';

START GROUP_REPLICATION;
```

Thông tin xác thực đặt bằng `CHANGE REPLICATION SOURCE TO` được lưu trong replication metadata repository dưới dạng văn bản rõ. Bảo vệ quyền đọc các file metadata và cân nhắc cơ chế cung cấp credentials an toàn hơn theo chính sách của hệ thống.

### 5.2. Cung cấp credentials khi khởi động

Có thể cung cấp credentials trực tiếp trong lệnh:

```sql
START GROUP_REPLICATION
  USER = 'rpl_user',
  PASSWORD = 'replace_with_secret';
```

Credentials truyền theo cách này chỉ lưu trong bộ nhớ và bị xóa khi `STOP GROUP_REPLICATION` hoặc máy chủ khởi động lại. Nếu dùng cách này, đặt `group_replication_start_on_boot=OFF` và chuẩn bị quy trình chạy lại `START GROUP_REPLICATION` sau khi clone hoặc restart. Không trộn hai phương pháp mà không xử lý credentials cũ trong metadata repository, vì thông tin đã lưu có thể được dùng khi Group Replication tự khởi động.

Lưu ý khi dùng Clone plugin: nếu trước đó đã lưu credentials bằng `CHANGE REPLICATION SOURCE TO` nhưng sau đó chuyển sang cung cấp credentials trong `START GROUP_REPLICATION`, hãy xóa credentials cũ khỏi metadata repository theo quy trình bảo mật distributed recovery của MySQL trước khi clone. Nếu không, thông tin cũ có thể được chuyển từ donor sang joiner và channel recovery có thể khởi động bằng credentials ngoài dự kiến.

## 6. Cách Group Replication chọn IST hay Clone

Group Replication tự chọn phương pháp sau khi nhận lệnh `START GROUP_REPLICATION` trên joiner. Việc lựa chọn dựa trên:

1. Các donor hiện có và donor nào đủ điều kiện phục vụ joiner.
2. Khoảng cách giao dịch giữa GTID set của joiner và donor.
3. Các giao dịch joiner cần có còn nằm trong binary log của donor hay không.
4. Clone plugin đã được chuẩn bị trên donor và joiner hay chưa.

| Tình huống | Phương pháp thường được chọn |
|---|---|
| Khoảng giao dịch nhỏ, donor còn đủ binary log | State transfer từ binary log. |
| Khoảng giao dịch vượt `group_replication_clone_threshold`, clone khả thi | Remote clone, sau đó state transfer các giao dịch phát sinh trong lúc clone. |
| Giao dịch cần thiết đã bị purge khỏi mọi donor, clone khả thi | Remote clone bất kể ngưỡng. |
| Clone không được cài hoặc không tương thích, binary log còn đủ | State transfer từ binary log. |
| Không có binary log cần thiết và không clone được | Recovery thất bại; cần provision lại dữ liệu hoặc sửa điều kiện clone. |

Ngưỡng clone là khoảng cách giao dịch, không phải dung lượng dữ liệu theo GB hoặc thời gian offline. Một thành viên offline một ngày trong nhóm ít giao dịch có thể chỉ thiếu ít GTID; một thành viên offline vài phút trong nhóm tải cao có thể thiếu rất nhiều giao dịch.

### 6.1. Donor có lỗi và cơ chế thử lại

Group Replication có thể tự chọn donor khác và thử lại khi gặp lỗi kết nối, lỗi replication receiver/applier, lỗi clone hoặc donor rời nhóm trong khi đang truyền dữ liệu. Bảng `replication_applier_status_by_worker` có thể cho biết lỗi gần nhất dẫn đến retry.

Quy trình không thể hoàn tất nếu:

- Giao dịch cần thiết đã bị purge khỏi mọi donor và không thể clone.
- Joiner có extra transactions không tồn tại trong nhóm.
- Đã thử hết donor phù hợp nhưng không thể clone hoặc nhận binary log.
- Số lần kết nối lại vượt `group_replication_recovery_retry_count`.
- Joiner rời nhóm hoặc quản trị viên dừng Group Replication khi recovery đang diễn ra.

Khi không còn phương án, joiner rời nhóm và thực hiện exit action theo `group_replication_exit_state_action`. Hãy đọc error log và trạng thái worker trước khi thử lại; không lặp lệnh start mà chưa xử lý nguyên nhân.

## 7. Theo dõi quá trình join

### 7.1. Kiểm tra trạng thái thành viên

Truy vấn từ một thành viên đang hoạt động:

```sql
SELECT MEMBER_ID,
       MEMBER_HOST,
       MEMBER_PORT,
       MEMBER_STATE,
       MEMBER_ROLE,
       MEMBER_VERSION
FROM performance_schema.replication_group_members;
```

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| `OFFLINE` | Plugin đã được nạp nhưng thành viên chưa tham gia nhóm. |
| `RECOVERING` | Thành viên đang nhận và áp dụng dữ liệu trong distributed recovery. |
| `ONLINE` | Thành viên đã đồng bộ đầy đủ và tham gia hoạt động bình thường. |
| `ERROR` | Thành viên gặp lỗi khi kiểm tra cấu hình, recovery hoặc áp dụng giao dịch. |
| `UNREACHABLE` | Failure detector nghi ngờ không thể liên lạc với thành viên đó. |

Chỉ xem joiner đã hoàn tất khi trạng thái là `ONLINE`. `RECOVERING` không đồng nghĩa đã sẵn sàng phục vụ ứng dụng; `ERROR` cần được điều tra trước khi thử gia nhập lại.

### 7.2. Kiểm tra channel recovery và applier

```sql
SELECT CHANNEL_NAME,
       SERVICE_STATE,
       LAST_ERROR_NUMBER,
       LAST_ERROR_MESSAGE
FROM performance_schema.replication_connection_status
WHERE CHANNEL_NAME = 'group_replication_recovery';

SELECT CHANNEL_NAME,
       WORKER_ID,
       SERVICE_STATE,
       LAST_ERROR_NUMBER,
       LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_worker
WHERE CHANNEL_NAME = 'group_replication_applier';
```

Channel `group_replication_recovery` cho biết trạng thái kết nối và nhận dữ liệu từ donor. Channel `group_replication_applier` áp dụng các giao dịch của nhóm. Nếu receiver đã nhận dữ liệu nhưng applier dừng, cần kiểm tra lỗi worker và giao dịch gây lỗi thay vì chỉ kiểm tra kết nối mạng.

### 7.3. Theo dõi Clone plugin

Khi remote clone đang diễn ra, kiểm tra:

```sql
SELECT *
FROM performance_schema.clone_status\G

SELECT *
FROM performance_schema.clone_progress;
```

`clone_status` hiển thị trạng thái của thao tác clone gần nhất; `clone_progress` hiển thị tiến độ theo từng stage. Kết hợp thông tin này với error log để xác định clone đang chạy, đã hoàn tất hay gặp lỗi. Sau clone, joiner còn cần state transfer từ binary log và áp dụng giao dịch mới trước khi lên `ONLINE`.

### 7.4. Đối chiếu GTID

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
```

Khi recovery hoàn tất, joiner phải có lịch sử giao dịch phù hợp với nhóm. Đừng chỉ dựa vào `Seconds_Behind_Source` hoặc số lượng giao dịch nhận được; Group Replication dùng GTID set để theo dõi lịch sử và cần xác nhận thành viên đã chuyển sang `ONLINE`.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Joiner ở `RECOVERING` rất lâu | Thiếu nhiều giao dịch hoặc donor truyền chậm | Kiểm tra GTID gap, dung lượng binary log, tải donor và tốc độ mạng; cân nhắc clone. |
| Không tìm được giao dịch cần thiết | Binary log đã purge trên mọi donor | Kiểm tra `gtid_purged`; chuẩn bị clone hoặc provision lại từ snapshot phù hợp. |
| Clone không được chọn | Plugin chưa active, thiếu `BACKUP_ADMIN`, threshold quá cao hoặc donor không tương thích | Kiểm tra plugin, quyền recovery, ngưỡng và release series/nền tảng. |
| Clone lặp đi lặp lại | Threshold quá thấp so với lượng giao dịch phát sinh trong thời gian clone | Tăng ngưỡng phù hợp với tốc độ ghi và thời gian clone; dừng/khởi động lại Group Replication để áp dụng. |
| Clone thất bại do keyring | Plugin quản lý khóa trên donor không có hoặc không hoạt động trên joiner | Cài và cấu hình plugin tương ứng trên joiner trước khi clone. |
| Recovery báo lỗi xác thực | Tài khoản recovery không tồn tại trên donor hoặc sai mật khẩu/host | Đồng nhất tài khoản và quyền trên các thành viên; kiểm tra TLS và phương thức xác thực. |
| Joiner bị từ chối do extra transactions | Joiner có GTID không tồn tại trong nhóm | Kiểm tra binary log của joiner và tái đồng bộ từ donor hợp lệ; không sửa GTID set tùy tiện. |
| Joiner không qua kiểm tra cấu hình | Sai group name, server_id trùng, local address hoặc cấu hình không tương thích | Đối chiếu cấu hình của joiner với các thành viên đang `ONLINE`. |
| Joiner không liên lạc được donor | Firewall, DNS, allowlist hoặc cổng SQL/group communication sai | Kiểm tra kết nối hai chiều và log của cả donor lẫn joiner. |
| Clone xong nhưng chưa `ONLINE` | Joiner chưa nhận và áp dụng hết giao dịch phát sinh trong lúc clone | Theo dõi recovery channel và applier worker; đợi state transfer hoàn tất. |

Nếu clone bị ngắt, recipient có thể còn dữ liệu một phần. Không mở luồng ứng dụng ghi dữ liệu vào instance này. Cho phép Group Replication thử donor khác hoặc chuẩn bị lại joiner từ một bản sao hợp lệ sau khi xác định lỗi.

## 9. Quy trình thực hành: thêm một thành viên vào nhóm

Giả sử nhóm đang có `db1` và `db2` ở trạng thái `ONLINE`. Máy `db3` là joiner. Nhóm sử dụng MySQL 8.4, XCom communication stack và Clone plugin để hỗ trợ recovery.

### Bước 1: Kiểm tra nhóm hiện tại

Trên một thành viên đang hoạt động:

```sql
SELECT MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;

SHOW VARIABLES LIKE 'group_replication_group_name';
SHOW VARIABLES LIKE 'group_replication_clone_threshold';
SHOW BINARY LOGS;
```

Xác nhận nhóm có quorum, ít nhất một donor đang `ONLINE`, donor giữ đủ binary log cần thiết hoặc có thể clone, và không có lỗi recovery chưa xử lý.

### Bước 2: Chuẩn bị db3

Đặt `server_id` và `server_uuid` duy nhất. Cấu hình GTID, binary log, ROW format, InnoDB, primary key, group name, local address, seeds và `group_replication_bootstrap_group=OFF`. Đồng nhất `lower_case_table_names` và `default_table_encryption` với nhóm.

### Bước 3: Cài plugin và tài khoản recovery

Cài và kích hoạt `group_replication` cùng `clone` trên db3 và các donor dự kiến. Tạo tài khoản recovery trên tất cả thành viên và joiner, cấp `REPLICATION SLAVE`, `CONNECTION_ADMIN` và `BACKUP_ADMIN`. Với MySQL communication stack, cấp thêm `GROUP_REPLICATION_STREAM`.

### Bước 4: Cấu hình credentials và clone threshold

Trên db3, thiết lập credentials cho channel `group_replication_recovery`. Chọn `group_replication_clone_threshold` dựa trên số giao dịch dự kiến phát sinh trong thời gian clone; không dùng giá trị quá thấp. Nếu thay đổi ngưỡng trên instance đã chạy Group Replication, dừng rồi khởi động lại plugin để giá trị có hiệu lực.

### Bước 5: Khởi động gia nhập

Trên db3:

```sql
START GROUP_REPLICATION;
```

Group Replication tự kiểm tra joiner, chọn donor và thực hiện binary log recovery hoặc clone tùy điều kiện. Không chạy `CLONE INSTANCE` thủ công cho quy trình distributed recovery tự động này.

### Bước 6: Theo dõi đến ONLINE

Kiểm tra `replication_group_members`, recovery channel, applier worker và clone status. Nếu clone được sử dụng, chờ db3 khởi động lại; nếu `group_replication_start_on_boot=OFF`, chạy lại `START GROUP_REPLICATION` sau restart. Chỉ đưa db3 vào phục vụ ứng dụng khi trạng thái là `ONLINE` và GTID history đã bắt kịp.

### Bước 7: Xác nhận khả năng làm donor trong tương lai

Kiểm tra db3 có Clone plugin active, tài khoản recovery có `BACKUP_ADMIN` và các cấu hình mạng/TLS cần thiết. Điều này giúp db3 có thể trở thành donor cho thành viên khác trong các lần recovery tiếp theo.

## 10. Nguyên tắc vận hành

1. **Giữ binary log đủ lâu.** Recovery bằng binary log phụ thuộc việc donor còn các giao dịch joiner cần.
2. **Chuẩn bị clone trước sự cố.** Cài plugin và cấp quyền trên các thành viên từ trước để có nhiều donor phù hợp.
3. **Chọn clone threshold theo tải thực tế.** Tính cả lượng giao dịch phát sinh trong thời gian clone.
4. **Giữ GTID history sạch.** Không tạo giao dịch riêng trên thành viên khi Group Replication dừng nếu giao dịch đó không thuộc lịch sử chung.
5. **Đồng nhất cấu hình quan trọng.** Group name, GTID, InnoDB, primary key, encryption và lower-case table settings phải đáp ứng yêu cầu của nhóm.
6. **Kiểm tra quyền recovery.** Cùng tài khoản recovery cần đúng quyền trên mọi donor và joiner.
7. **Bảo vệ kết nối.** Giới hạn host, bật TLS và kiểm soát quyền truy cập binary log.
8. **Theo dõi đến ONLINE.** `RECOVERING` nghĩa là state transfer chưa xong; không đưa joiner vào luồng phục vụ trước khi đồng bộ hoàn tất.
9. **Không bỏ qua lỗi GTID.** Extra transactions hoặc purged transactions cần được xử lý bằng cách tái đồng bộ có kiểm soát.

## 11. Bài tập tự kiểm tra

1. Khi joiner chỉ thiếu một số giao dịch và donor còn giữ chúng trong binary log, Group Replication dùng cơ chế nào để phục hồi?
2. Vì sao một joiner thiếu nhiều giao dịch có thể được clone thay vì nhận từng giao dịch từ binary log?
3. Nếu giao dịch joiner cần đã bị purge khỏi mọi donor, điều kiện nào cho phép recovery tiếp tục?
4. Vì sao `group_replication_clone_threshold` quá thấp có thể gây vòng lặp clone?
5. Tài khoản recovery cần quyền nào để vừa đọc binary log vừa làm clone user trên donor?
6. Vì sao Group Replication từ chối joiner có extra transactions?
7. Trạng thái nào chứng minh joiner đã bắt kịp nhóm và có thể tham gia bình thường?
8. Vì sao joiner phải đặt `group_replication_bootstrap_group=OFF` khi gia nhập một nhóm đang chạy?

**Gợi ý đáp án:** (1) State transfer từ binary log qua channel `group_replication_recovery`. (2) Clone sao chép trạng thái dữ liệu vật lý nhanh hơn việc truyền và áp dụng một lượng lớn giao dịch riêng lẻ. (3) Clone plugin phải được cài và có donor tương thích; nếu không, cần provision lại dữ liệu thủ công. (4) Giao dịch mới có thể vượt ngưỡng trong lúc clone; sau restart joiner lại bị yêu cầu clone, dẫn đến lặp. (5) `REPLICATION SLAVE`, `CONNECTION_ADMIN` và `BACKUP_ADMIN`; thêm `GROUP_REPLICATION_STREAM` khi dùng MySQL communication stack. (6) Clone sẽ xóa chúng, còn binary log recovery có thể gây xung đột với lịch sử nhóm. (7) `ONLINE`. (8) Bật bootstrap trên joiner có thể tạo nhóm độc lập thay vì gia nhập nhóm hiện hữu.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-distributed-recovery.html)
- [MySQL 8.4 Reference Manual: Cloning for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-cloning.html)
- [MySQL 8.4 Reference Manual: Configuring Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-tuning-recovery.html)
- [MySQL 8.4 Reference Manual: Fault Tolerance for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-distributed-recovery-fault.html)
- [MySQL 8.4 Reference Manual: Group Replication Requirements](https://dev.mysql.com/doc/refman/8.4/en/group-replication-requirements.html)
- [MySQL 8.4 Reference Manual: User Credentials for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-user-credentials.html)
- [MySQL 8.4 Reference Manual: Group Replication Server States](https://dev.mysql.com/doc/refman/8.4/en/group-replication-server-states.html)
