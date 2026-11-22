# Khởi tạo data directory và tài khoản quản trị ban đầu

Data directory là nơi MySQL lưu dữ liệu bền vững của máy chủ: từ điển dữ liệu, các bảng hệ thống, dữ liệu InnoDB, redo log và những tệp trạng thái cần thiết để khởi động. Khởi tạo đúng thư mục này là bước tạo nền cho một instance MySQL mới. Sau đó, cần thiết lập tài khoản quản trị có thông tin xác thực rõ ràng và giới hạn nơi đăng nhập.

Bài thực hành này thuộc module `DATABASE_MYSQL`, trong chương Môi trường thực hành. Việc chuẩn bị instance và tài khoản quản trị tạo nền để thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời; các bài vận hành tiếp theo sẽ dùng môi trường này để đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và sao lưu. Bài dùng MySQL 8.0/8.4 trên Linux làm ví dụ chính. Tên service, đường dẫn cấu hình, vị trí error log và cách xác thực tài khoản `root` có thể khác theo bản phân phối Linux hoặc cách cài đặt. Hãy kiểm tra cấu hình thực tế trước khi chạy lệnh. Các bước trên một máy Windows được ghi ở phần riêng.

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định data directory và tài khoản hệ điều hành mà MySQL Server sử dụng.
- Chuẩn bị một data directory mới với quyền truy cập phù hợp.
- Khởi tạo data directory bằng `mysqld --initialize` và tìm mật khẩu tạm của tài khoản `root`.
- Đổi thông tin xác thực ban đầu, tạo tài khoản quản trị riêng và kiểm tra quyền đã cấp.
- Nhận biết các lỗi thường gặp khi khởi tạo hoặc đăng nhập.

## 1. Hiểu data directory trước khi khởi tạo

Data directory (thường được cấu hình bằng tùy chọn `datadir`) chứa dữ liệu nội bộ của một MySQL instance. Một số thành phần thường gặp gồm:

| Thành phần | Vai trò |
|---|---|
| `mysql/` | Các bảng hệ thống lưu tài khoản, quyền và metadata quản trị |
| `performance_schema/` | Dữ liệu quan sát hoạt động và hiệu năng của máy chủ |
| `sys/` | Các view hỗ trợ đọc dữ liệu chẩn đoán từ Performance Schema |
| Các tệp InnoDB | Tablespace, redo log, undo và dữ liệu lưu trữ của InnoDB |
| `auto.cnf` | Định danh server UUID của instance |
| Tệp error log | Thông tin khởi động và lỗi; vị trí cụ thể phụ thuộc `log_error` |

Không phải mọi thành phần đều nằm trong data directory ở tất cả cấu hình. Chẳng hạn, error log có thể được ghi ra một đường dẫn riêng. Giá trị `datadir` đang chạy mới là căn cứ để xác định thư mục dữ liệu thực tế.

Khi gọi `mysqld --initialize`, MySQL tạo cấu trúc hệ thống ban đầu và tài khoản `root` cục bộ. Với `--initialize`, máy chủ sinh một mật khẩu ngẫu nhiên tạm thời cho `root` và ghi mật khẩu đó vào error log. Tài khoản thường phải đổi mật khẩu ở lần đăng nhập đầu tiên. Tùy chọn `--initialize-insecure` tạo tài khoản `root` không có mật khẩu; chỉ cân nhắc nó trong môi trường lab cô lập và phải đặt mật khẩu ngay lập tức.

**Điều kiện quan trọng:** data directory dùng cho lần khởi tạo phải mới và rỗng. Không chạy `--initialize` lên thư mục đang chứa dữ liệu của một instance. Nếu MySQL được cài từ gói của hệ điều hành, trình cài đặt có thể đã khởi tạo `/var/lib/mysql`; không khởi tạo lại thư mục đó.

## 2. Kiểm tra trước khi thực hiện

Trước tiên, xác nhận phiên bản và vị trí các chương trình:

```bash
mysqld --version
mysql --version
```

Kiểm tra cấu hình máy chủ. Trên Debian/Ubuntu, cấu hình thường được nạp từ `/etc/mysql/my.cnf` cùng các tệp được include bên dưới `/etc/mysql/`. Trên nhiều hệ thống RHEL-compatible, tệp chính thường là `/etc/my.cnf`. Không giả định mọi máy đều dùng cùng một đường dẫn.

Nếu máy chủ đang chạy, đăng nhập bằng phương thức quản trị hiện có rồi kiểm tra:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'socket';
SELECT VERSION();
```

Nếu đây là máy mới cài bằng package manager, kiểm tra service và error log để biết quá trình cài đặt đã tạo data directory hay chưa. Trên Debian/Ubuntu, service thường tên `mysql`; trên RHEL-compatible, service thường tên `mysqld`:

```bash
sudo systemctl status mysql
# Hoặc:
sudo systemctl status mysqld
```

Chỉ tiếp tục với quy trình khởi tạo thủ công khi bạn đã xác định rõ đây là instance mới và data directory đích chưa có dữ liệu cần giữ. Nếu thư mục đã có dữ liệu, hãy dừng lại, xác định instance sở hữu nó và lập kế hoạch sao lưu/chuyển đổi phù hợp.

## 3. Chuẩn bị data directory trên Linux

Ví dụ dưới đây tạo thư mục riêng `/srv/mysql/data`. Bạn có thể dùng `/var/lib/mysql` nếu đó là đường dẫn đã được package và cấu hình hệ thống quy định. Không đổi `datadir` chỉ bằng cách tạo thư mục mới; cấu hình máy chủ và quyền truy cập của hệ điều hành phải cùng trỏ đến một nơi.

### 3.1. Dừng service nếu cần thay đổi cấu hình

Nếu instance đang chạy và bạn chuẩn bị thay đổi `datadir`, hãy dừng đúng service trước. Chọn tên service phù hợp với hệ điều hành:

```bash
sudo systemctl stop mysql
# Hoặc:
sudo systemctl stop mysqld
```

Không dừng một máy chủ đang phục vụ người dùng chỉ để làm theo ví dụ lab. Trong môi trường đang có dữ liệu, việc đổi data directory cần kế hoạch bảo trì và sao lưu riêng.

### 3.2. Tạo thư mục và cấp quyền

Trên nhiều bản cài Linux, tiến trình MySQL chạy dưới tài khoản hệ điều hành `mysql`. Kiểm tra tài khoản này đã tồn tại chưa, sau đó tạo thư mục với quyền chỉ cho chủ sở hữu và nhóm cần thiết truy cập:

```bash
id mysql
sudo install -d -o root -g root -m 755 /srv/mysql
sudo install -d -o mysql -g mysql -m 750 /srv/mysql/data
```

`mysql:mysql` đặt chủ sở hữu và nhóm cho data directory; quyền `750` cho phép tài khoản dịch vụ đọc, ghi và đi vào thư mục, còn người dùng khác không được truy cập. Không đặt quyền `777` để chữa lỗi permission vì điều đó mở dữ liệu cơ sở dữ liệu cho mọi tài khoản trên máy.

Nếu bản cài đặt dùng tài khoản dịch vụ khác, thay `mysql` bằng tài khoản thực tế. Thư mục cha cũng phải cho tiến trình MySQL quyền đi xuyên qua (`execute` trên thư mục), dù tiến trình không cần quyền ghi vào mọi thư mục cha.

### 3.3. Cấu hình `datadir`

Thêm hoặc cập nhật các tùy chọn tương ứng trong phần `[mysqld]` của tệp cấu hình mà service thực sự nạp. Ví dụ:

```ini
[mysqld]
user=mysql
datadir=/srv/mysql/data
```

Giữ nguyên các thiết lập `socket`, `pid-file`, `log_error`, `basedir` và những tùy chọn hiện có nếu chúng vẫn đúng. Không thay toàn bộ tệp cấu hình bằng đoạn ví dụ ngắn này. Nếu cấu hình chỉ định socket hoặc error log trong thư mục khác, hãy bảo đảm thư mục đó tồn tại và service có quyền phù hợp.

Trên hệ thống có SELinux hoặc AppArmor, quyền Unix đúng vẫn có thể chưa đủ. Chính sách bảo mật có thể chặn `mysqld` truy cập đường dẫn tùy chỉnh. Hãy cấu hình nhãn SELinux hoặc profile AppArmor theo chính sách của bản phân phối, sau đó kiểm tra log audit nếu máy chủ tiếp tục báo `Permission denied`.

## 4. Khởi tạo instance mới

Trước khi chạy lệnh, xác nhận lại ba điểm: service không chạy trên data directory đích, thư mục đích đang rỗng, và `mysqld` đang đọc đúng tệp cấu hình có `datadir` bạn vừa chọn.

Trên Linux, ví dụ với cấu hình chính `/etc/mysql/my.cnf`:

```bash
sudo mysqld --defaults-file=/etc/mysql/my.cnf --user=mysql --initialize
```

Nếu máy dùng `/etc/my.cnf`, thay đường dẫn tương ứng. `--defaults-file` cần đứng ngay sau tên chương trình để MySQL nạp đúng cấu hình chỉ định. Tùy chọn `--user=mysql` yêu cầu tiến trình sử dụng tài khoản dịch vụ `mysql` khi thao tác với dữ liệu.

Khi hoàn tất, tìm dòng thông báo mật khẩu tạm của `root` trong error log. Đường dẫn log được xác định bởi `log_error`; nếu không cấu hình riêng, vị trí mặc định có thể nằm trong data directory. Với service systemd, log khởi động service cũng có thể xem qua:

```bash
sudo journalctl -u mysql -n 100 --no-pager
# Hoặc:
sudo journalctl -u mysqld -n 100 --no-pager
```

Lệnh `journalctl` hữu ích cho log của service; nếu bạn chạy `mysqld --initialize` trực tiếp, hãy kiểm tra đúng error log mà cấu hình chỉ định. Lưu mật khẩu tạm vào nơi quản lý bí mật an toàn. Không đưa mật khẩu thật vào tài liệu, mã nguồn, lịch sử shell hoặc ảnh chụp màn hình.

Sau khi khởi tạo thành công, khởi động service:

```bash
sudo systemctl start mysql
# Hoặc:
sudo systemctl start mysqld
```

Kiểm tra trạng thái service trước khi đăng nhập. Nếu service không khởi động, đọc error log và xử lý nguyên nhân trước; không lặp lại `--initialize` một cách máy móc trên thư mục đã được khởi tạo một phần.

### 4.1. Trường hợp cài đặt bằng package manager

Một số gói MySQL do hệ điều hành phân phối tự tạo data directory và tài khoản quản trị trong quá trình cài đặt. Trên Ubuntu, chẳng hạn, tài khoản `root` có thể được cấu hình xác thực qua Unix socket. Khi đó, cách đăng nhập ban đầu có thể là:

```bash
sudo mysql
```

Nếu cách này hoạt động, kiểm tra `datadir` và phương thức xác thực hiện tại trước khi thay đổi tài khoản. Không chạy lại `mysqld --initialize` lên data directory package đã tạo. Hãy dùng quy trình quản trị do bản phân phối cung cấp hoặc cấu hình tài khoản theo chính sách của hệ thống.

## 5. Thiết lập tài khoản `root` ban đầu

Với instance được tạo bằng `--initialize`, đăng nhập bằng mật khẩu tạm:

```bash
mysql -u root -p
```

Nhập mật khẩu lấy từ error log khi được nhắc. Sau đó đổi mật khẩu ngay trong MySQL client:

```sql
ALTER USER 'root'@'localhost'
  IDENTIFIED BY 'ThayBangMatKhauManhVaRieng';
```

Thay chuỗi minh họa bằng mật khẩu mạnh được tạo và lưu trong password manager. Không sao chép nguyên mật khẩu ví dụ vào môi trường thật. Nếu chính sách xác thực của máy chủ có yêu cầu riêng, hãy tuân thủ chính sách đó. Trên cài đặt package sử dụng Unix socket, không tự ý đổi plugin xác thực chỉ để làm cho ví dụ mật khẩu này hoạt động.

Kiểm tra tài khoản và phiên đăng nhập:

```sql
SELECT CURRENT_USER();
SELECT user, host, plugin, account_locked, password_expired
FROM mysql.user
WHERE user = 'root';
```

`CURRENT_USER()` cho biết tài khoản MySQL thực sự được dùng để kiểm tra quyền. Cột `host` giúp xác nhận tài khoản `root` đang giới hạn ở `localhost`; `plugin` cho biết phương thức xác thực đang dùng. Tránh tạo hoặc mở rộng tài khoản `root` cho host `%`.

## 6. Tạo tài khoản quản trị riêng

Trong vận hành, nên dùng một tài khoản quản trị có tên riêng cho công việc hằng ngày. Tài khoản `root` có thể được giữ làm tài khoản bootstrap hoặc khôi phục trong tình huống cần thiết. Tách tài khoản giúp truy vết hoạt động và thu hồi quyền dễ hơn.

### 6.1. Tạo DBA chỉ đăng nhập từ máy chủ cục bộ

Ví dụ sau tạo `dba_admin` chỉ khớp với kết nối cục bộ:

```sql
CREATE USER 'dba_admin'@'localhost'
  IDENTIFIED BY 'ThayBangMatKhauRiengChoDba';

GRANT ALL PRIVILEGES ON *.*
  TO 'dba_admin'@'localhost'
  WITH GRANT OPTION;
```

Quyền trên `*.*` có phạm vi toàn máy chủ; `WITH GRANT OPTION` cho phép tài khoản chuyển tiếp những quyền mà nó có thể cấp. Đây là tài khoản rất mạnh, chỉ tạo cho DBA đáng tin cậy trong môi trường cần quản trị toàn instance. Nếu người dùng chỉ quản trị một schema, hãy cấp quyền trên `ten_schema.*` thay vì toàn máy chủ.

Ví dụ tài khoản chỉ thao tác trên schema lab:

```sql
CREATE USER 'lab_operator'@'localhost'
  IDENTIFIED BY 'ThayBangMatKhauRiengChoLab';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON lab_db.*
  TO 'lab_operator'@'localhost';
```

Tài khoản ứng dụng cũng nên được cấp đúng các quyền mà ứng dụng cần trên schema của nó. Không dùng `root` hoặc DBA toàn máy chủ làm tài khoản kết nối thường xuyên của ứng dụng.

### 6.2. Kiểm tra quyền

Xem các quyền đã cấp:

```sql
SHOW GRANTS FOR 'dba_admin'@'localhost';
SHOW GRANTS FOR 'lab_operator'@'localhost';
```

Thử đăng nhập bằng tài khoản mới trong một terminal khác:

```bash
mysql -u dba_admin -p
```

Trong phiên mới, kiểm tra danh tính và quyền truy cập:

```sql
SELECT CURRENT_USER();
SHOW DATABASES;
```

Nếu chỉ cần xác minh tài khoản ứng dụng, thử một truy vấn được phép trên schema của ứng dụng và xác nhận thao tác ngoài phạm vi bị từ chối. Các lệnh `CREATE USER`, `ALTER USER` và `GRANT` có hiệu lực ngay; không cần chạy `FLUSH PRIVILEGES` sau những lệnh quản trị này.

### 6.3. Nếu cần quản trị từ xa

Chỉ mở quản trị từ xa khi có yêu cầu vận hành rõ ràng. Tạo account gắn với địa chỉ IP hoặc hostname cụ thể của máy quản trị, bật TLS, giới hạn firewall và cấu hình `bind-address` phù hợp. Ví dụ về hình thức khai báo account:

```sql
CREATE USER 'dba_remote'@'10.20.30.15'
  IDENTIFIED BY 'MatKhauRiengChoMayQuanTri'
  REQUIRE SSL;
```

Sau đó cấp đúng tập quyền cần thiết cho account này. Địa chỉ `10.20.30.15` chỉ là ví dụ; thay bằng địa chỉ thực được phép. Không dùng host `%` để bỏ qua việc xác định nguồn kết nối, và không công khai cổng MySQL ra Internet nếu không có lớp kiểm soát truy cập phù hợp.

## 7. Ghi chú khi thực hiện trên Windows

Với bản cài MySQL Server trên Windows, dùng Command Prompt hoặc PowerShell có quyền phù hợp. Xác định chính xác `my.ini`, thư mục cài đặt và `datadir` trước khi khởi tạo. Ví dụ lệnh cho một data directory mới, rỗng:

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe' `
  --defaults-file='C:\ProgramData\MySQL\MySQL Server 8.4\my.ini' `
  --initialize --console
```

`--console` hiển thị thông báo khởi tạo và mật khẩu tạm trên cửa sổ console. Các đường dẫn trên chỉ là ví dụ; dùng đúng đường dẫn từ MySQL Installer/Configurator của máy. Chạy lệnh dưới tài khoản có quyền ghi vào data directory. Sau đó khởi động Windows service đã cấu hình cho instance và đăng nhập bằng MySQL client để đổi mật khẩu `root`, tạo DBA và kiểm tra quyền như các phần trên.

## 8. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `--initialize` báo data directory không rỗng | Thư mục đã có dữ liệu hoặc lần chạy trước đã tạo một phần tệp | Xác minh đúng instance và nội dung thư mục. Không xóa dữ liệu theo phản xạ; chỉ dùng thư mục mới sau khi chắc chắn không có dữ liệu cần giữ. |
| `Permission denied` khi khởi tạo hoặc khởi động | Sai owner/group, thiếu quyền đi qua thư mục cha, hoặc bị SELinux/AppArmor chặn | Kiểm tra `id mysql`, quyền từng thư mục, error log và log audit; sửa quyền/chính sách cho đúng đường dẫn. |
| Không tìm thấy mật khẩu tạm | Đang xem sai error log hoặc `log_error` trỏ đến nơi khác | Đọc `SHOW VARIABLES LIKE 'log_error'` nếu máy chủ đã chạy; nếu chưa, kiểm tra cấu hình được dùng khi khởi tạo và log của lần chạy đó. |
| Service không khởi động sau khi đổi `datadir` | Service nạp tệp cấu hình khác, đường dẫn sai, quyền không đủ hoặc chính sách bảo mật chưa cho phép | Kiểm tra service unit, tệp cấu hình được nạp và error log; xác nhận `datadir` trong cấu hình khớp thư mục đã khởi tạo. |
| `Access denied for user 'root'@'localhost'` | Mật khẩu tạm nhập sai, tài khoản dùng plugin khác, hoặc đang kết nối tới instance khác | Kiểm tra socket/port và đúng instance; xác định plugin xác thực qua phiên quản trị còn truy cập được. Không tạo thêm tài khoản `root` để né lỗi. |
| `Can't connect to local MySQL server through socket` | Service chưa chạy hoặc client dùng socket path khác máy chủ | Kiểm tra trạng thái service, `socket` trong cấu hình và error log; chỉ định đúng socket nếu cần. |

## 9. Bài thực hành và tiêu chí hoàn thành

Thực hiện trên một máy lab hoặc instance dùng riêng cho bài học:

1. Ghi lại phiên bản MySQL, service name, tệp cấu hình, `datadir` và `log_error` hiện tại.
2. Tạo một data directory mới, rỗng; cấp quyền cho đúng tài khoản dịch vụ và cập nhật `datadir` trong cấu hình.
3. Khởi tạo bằng `mysqld --initialize`. Tìm mật khẩu tạm trong error log và đăng nhập bằng tài khoản `root`.
4. Đổi mật khẩu `root`, tạo `dba_admin` chỉ đăng nhập từ `localhost`, rồi xem `SHOW GRANTS`.
5. Tạo thêm `lab_operator` với quyền giới hạn trên một schema thử nghiệm. Kiểm tra thao tác được phép và thao tác bị từ chối.
6. Đối chiếu `CURRENT_USER()`, `@@datadir`, `@@socket` và `VERSION()` để chắc chắn đang làm việc với đúng instance.

Bạn hoàn thành bài khi service khởi động ổn định, MySQL dùng đúng data directory đã chọn, tài khoản quản trị đăng nhập được, quyền cấp ra đúng phạm vi và không cần dùng tài khoản `root` cho kết nối ứng dụng.

## 10. Nguyên tắc cần ghi nhớ

- Khởi tạo data directory là thao tác một lần cho một instance mới; không chạy lại trên thư mục đang có dữ liệu.
- `--initialize` tạo mật khẩu `root` tạm; đổi mật khẩu ngay và bảo vệ error log vì log có thể chứa thông tin xác thực ban đầu.
- Chủ sở hữu và quyền của thư mục phải phù hợp với tài khoản chạy MySQL; SELinux/AppArmor cũng phải cho phép truy cập.
- Giữ tài khoản quản trị giới hạn theo host, dùng tài khoản riêng cho từng mục đích và cấp quyền theo nguyên tắc tối thiểu.
- Sao lưu trước mọi thay đổi có thể ảnh hưởng đến data directory. Không di chuyển, xóa hoặc chỉnh sửa trực tiếp các tệp dữ liệu khi MySQL đang chạy.
