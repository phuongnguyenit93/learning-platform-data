# Data directory, socket, PID file và quyền filesystem

MySQL Server cần một vùng lưu trữ bền vững cho data files, một cơ chế giao tiếp giữa client và server, cùng một cách nhận diện tiến trình đang chạy. Ba nhóm cấu hình thường gặp là:

- **Data directory (\`datadir\`)**: nơi MySQL lưu data dictionary, schema, bảng, tablespace và nhiều tệp trạng thái của server.
- **Socket hoặc named pipe**: endpoint giao tiếp cục bộ giữa client và server trên hệ điều hành hỗ trợ.
- **PID file (\`pid_file\`)**: tệp ghi process ID của tiến trình mysqld, thường được service manager hoặc công cụ vận hành dùng để theo dõi tiến trình.

Các đường dẫn này phải tồn tại đúng lúc server khởi động và phải được tài khoản hệ điều hành chạy MySQL truy cập với quyền phù hợp. Một cấu hình SQL đúng vẫn có thể không khởi động được nếu thư mục không tồn tại, quyền filesystem sai, SELinux/AppArmor chặn truy cập, volume chưa mount hoặc thư mục runtime bị xóa sau reboot.

Bài học thuộc phạm vi DATABASE_MYSQL: xác định các đường dẫn runtime, hiểu vai trò từng tệp, cấp quyền tối thiểu, cấu hình socket/PID trên Linux và Windows, chuyển data directory an toàn, xử lý lỗi khởi động và kiểm tra các giới hạn bảo mật ở filesystem.

## 1. Bản đồ các đường dẫn MySQL

Một MySQL instance có thể sử dụng nhiều thư mục khác nhau. Không phải mọi tệp đều nằm trong datadir.

| Thành phần | Vai trò | Cách xác định |
|---|---|---|
| basedir | Thư mục cài đặt chương trình, thư viện và công cụ | \`@@basedir\` |
| datadir | Thư mục dữ liệu của instance | \`@@datadir\` |
| socket | Unix-domain socket trên Unix-like OS | \`@@socket\` |
| pid_file | Tệp process ID | \`@@pid_file\` |
| tmpdir | Thư mục tệp tạm của server | \`@@tmpdir\` |
| log_error | Error log | \`@@log_error\` |
| secure_file_priv | Thư mục giới hạn cho một số thao tác import/export phía server | \`@@secure_file_priv\` |
| log_bin_basename | Prefix/path của binary log nếu bật | \`@@log_bin_basename\` |
| relay_log_basename | Prefix/path relay log nếu có replication | \`@@relay_log_basename\` |

Kiểm tra nhiều đường dẫn trong một lần:

~~~sql
SELECT
    @@basedir AS basedir,
    @@datadir AS datadir,
    @@socket AS socket_path,
    @@pid_file AS pid_file,
    @@tmpdir AS tmpdir,
    @@log_error AS error_log,
    @@secure_file_priv AS secure_file_priv;
~~~

Kiểm tra riêng các biến:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
    'basedir',
    'datadir',
    'socket',
    'pid_file',
    'tmpdir',
    'log_error',
    'secure_file_priv'
);
~~~

Đường dẫn thực tế phụ thuộc cách cài đặt, hệ điều hành, package, service manager và cấu hình instance. Không sao chép mặc định của một bản Linux sang Windows hoặc container mà chưa xác minh.

## 2. Data directory chứa những gì?

Datadir là thư mục gốc dữ liệu của một MySQL instance. Với InnoDB, nó thường chứa hoặc liên quan tới:

- Schema và metadata của database.
- Các tệp tablespace theo cấu hình.
- System tablespace nếu được cấu hình trong datadir.
- Undo tablespace nếu đặt tại đó.
- Redo log files trong thư mục redo log theo phiên bản/cấu hình.
- Binary log hoặc relay log nếu đường dẫn được đặt trong datadir.
- Error log nếu không cấu hình đường dẫn khác.
- Tệp cấu hình/trạng thái nội bộ như \`auto.cnf\`.
- Các thư mục schema hệ thống như \`mysql\`, \`performance_schema\`, \`sys\` tùy phiên bản và cách cài đặt.

Không được giả định tất cả dữ liệu đều nằm trong một thư mục duy nhất. Một số tablespace, log, keyring, plugin, temporary files hoặc file import/export có thể nằm ở đường dẫn khác.

### 2.1. Datadir không phải thư mục backup

Datadir là nơi server đang hoạt động và ghi dữ liệu. Backup là bản sao phục hồi được tạo theo quy trình nhất quán.

Không dùng cách copy datadir đang chạy bằng lệnh filesystem thông thường rồi xem đó là backup hợp lệ. Với InnoDB, các data page, redo log, undo state và metadata phải nhất quán tại cùng một thời điểm. Hãy dùng công cụ backup phù hợp:
- Logical backup như \`mysqldump\` hoặc MySQL Shell dump utilities.
- Physical backup có hỗ trợ MySQL như MySQL Enterprise Backup hoặc công cụ tương thích đã được kiểm chứng.
- Snapshot storage chỉ khi quy trình bảo đảm tính nhất quán, ví dụ phối hợp freeze/backup lock theo công cụ và phiên bản.

Backup phải được kiểm tra bằng restore thử nghiệm. Chỉ có file backup không chứng minh hệ thống có thể phục hồi.

### 2.2. Không chỉnh sửa tệp dữ liệu khi mysqld đang chạy

Không dùng editor để sửa trực tiếp file InnoDB, data dictionary, redo log hoặc system tables. Không tự xóa file đang được server sử dụng để “giải phóng dung lượng”.

Khi cần thay đổi cấu trúc, dùng SQL DDL/DML và quy trình backup/restore hoặc migration phù hợp. Khi cần di chuyển datadir, dừng server sạch trước khi sao chép file vật lý.

## 3. Xác định datadir, basedir và cấu hình đang có hiệu lực

Đừng đoán vị trí từ tên package. Hỏi chính server:

~~~sql
SELECT
    @@version AS mysql_version,
    @@version_comment AS distribution,
    @@basedir AS basedir,
    @@datadir AS datadir,
    @@server_uuid AS server_uuid;
~~~

Một số biến chỉ đọc được ở scope GLOBAL. Trong client, có thể dùng:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'basedir';
SHOW GLOBAL VARIABLES LIKE 'socket';
SHOW GLOBAL VARIABLES LIKE 'pid_file';
~~~

Trên máy chủ, có thể kiểm tra cách mysqld nhận option:

~~~bash
mysqld --print-defaults
~~~

Lệnh trên in các option lấy từ option files mà mysqld đọc. Để xem danh sách đường dẫn option file và giá trị mặc định, dùng:

~~~bash
mysqld --verbose --help
~~~

Đây là lệnh chẩn đoán từ shell; cần chạy đúng binary và môi trường của instance. Output có thể dài. Không chạy nhiều bản mysqld khác nhau một cách tùy tiện vì chúng có thể đọc các file cấu hình khác nhau.

### 3.1. Thứ tự cấu hình

MySQL có thể nhận cấu hình từ:
- Option files như \`my.cnf\` hoặc \`my.ini\`.
- Các file include hoặc include directory.
- Tham số dòng lệnh của service.
- Các biến thay đổi được runtime bằng SET GLOBAL.
- Giá trị mặc định của binary.

Một option xuất hiện ở nhiều nơi có thể bị ghi đè theo thứ tự đọc và quy tắc option file. Hãy xác minh cấu hình hiệu lực bằng biến runtime và service command line, thay vì chỉ đọc một file cấu hình.

### 3.2. Xác định service đang chạy binary nào

Trên Linux:

~~~bash
systemctl status mysql
systemctl cat mysql
ps -ef | grep '[m]ysqld'
~~~

Tên unit có thể là \`mysql\`, \`mysqld\` hoặc tên tùy package.

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'mysql' } |
  Select-Object Name, State, StartName, PathName
~~~

\`PathName\` cho biết binary/service arguments; \`StartName\` cho biết account chạy service. Không sửa service command line khi chưa lưu cấu hình hiện tại.

## 4. Cấu hình datadir trong option file

Trên Unix-like OS, cấu hình server thường nằm trong section \`[mysqld]\`:

~~~ini
[mysqld]
basedir=/usr
datadir=/var/lib/mysql
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
user=mysql
~~~

Trên Windows, file cấu hình thường là \`my.ini\` và đường dẫn dùng dạng Windows:

~~~ini
[mysqld]
basedir=C:/Program Files/MySQL/MySQL Server 8.4
datadir=C:/ProgramData/MySQL/MySQL Server 8.4/Data
port=3306
named_pipe=ON
socket=MYSQL
~~~

Ví dụ chỉ minh họa cấu trúc. Package và installer có thể chọn đường dẫn, tên service và cơ chế IPC khác.

Lưu ý:
- \`basedir\` trỏ tới nơi cài đặt, không phải nơi chứa database.
- \`datadir\` phải là thư mục dữ liệu của đúng instance.
- Không trỏ hai mysqld đang chạy đồng thời vào cùng một datadir.
- Thay đổi các đường dẫn startup thường cần restart server.
- Không di chuyển datadir chỉ bằng cách sửa option rồi khởi động lại; phải chuẩn bị và di chuyển dữ liệu đúng quy trình.

## 5. Khởi tạo data directory

Datadir mới phải được khởi tạo bằng công cụ MySQL tương ứng với phiên bản.

Ví dụ trên Linux, sau khi cài package và tạo thư mục đúng quyền:

~~~bash
mysqld --initialize --user=mysql --datadir=/var/lib/mysql
~~~

\`--initialize\` tạo system tables và khởi tạo InnoDB; MySQL tạo mật khẩu tạm cho root trong error log ở các cấu hình hỗ trợ. Đọc error log theo hướng dẫn của package và đổi mật khẩu ngay sau lần đăng nhập đầu tiên.

Một lựa chọn khác:

~~~bash
mysqld --initialize-insecure --user=mysql --datadir=/var/lib/mysql
~~~

\`--initialize-insecure\` khởi tạo root không có mật khẩu ban đầu. Chỉ dùng trong môi trường có kiểm soát và phải đặt mật khẩu an toàn ngay sau đó. Không để instance có tài khoản quản trị không mật khẩu trên mạng hoặc môi trường dùng chung.

Trên Windows có thể cần chạy từ thư mục binary với quyền phù hợp:

~~~powershell
mysqld --initialize --console --datadir="C:/ProgramData/MySQL/MySQL Server 8.4/Data"
~~~

Lệnh khởi tạo chỉ dùng cho datadir mới, trống và đúng instance. Không chạy \`--initialize\` lên datadir đang có dữ liệu. Nếu server báo datadir đã được khởi tạo, dừng lại và xác minh đường dẫn; không xóa nội dung để ép khởi tạo lại.

### 5.1. Khởi tạo khác với nâng cấp

\`--initialize\` không phải lệnh nâng cấp datadir cũ. Khi nâng cấp phiên bản:
- Đọc hướng dẫn upgrade của phiên bản đích.
- Backup có thể phục hồi.
- Kiểm tra compatibility và thay đổi data dictionary.
- Dùng quy trình upgrade được MySQL hỗ trợ.
- Không khởi tạo mới trên thư mục dữ liệu cũ.

Không dùng binary phiên bản cũ để mở datadir đã được nâng cấp bởi phiên bản mới hơn nếu tài liệu không hỗ trợ downgrade.

## 6. Quyền filesystem tối thiểu cho datadir

MySQL thường chạy dưới một tài khoản hệ điều hành riêng, ví dụ \`mysql\` trên Linux. Tài khoản này cần quyền đọc/ghi phù hợp với các file dữ liệu và quyền traverse trên mọi thư mục cha.

Một cấu hình thường gặp trên Linux:

~~~bash
chown -R mysql:mysql /var/lib/mysql
chmod 750 /var/lib/mysql
~~~

Đây chỉ là ví dụ cho datadir mới hoặc sau khi đã xác minh toàn bộ cây thư mục thuộc instance đó. Không chạy \`chown -R\` mù quáng trên thư mục đang chứa mount point, file backup, socket, log hoặc file thuộc instance khác.

Quyền cần xem xét:
- Owner của datadir và các tệp.
- Quyền đọc/ghi trên file data và log.
- Quyền execute trên thư mục để traverse.
- Quyền tạo/xóa file trong thư mục cần ghi.
- ACL nếu môi trường dùng ACL.
- SELinux/AppArmor policy.
- Mount options và quota.

### 6.1. Tránh chmod 777

Không cấp quyền đọc/ghi cho mọi user chỉ để làm MySQL khởi động được.

\`chmod 777\` có thể cho phép tài khoản không tin cậy đọc hoặc sửa database files, tạo symlink, xóa dữ liệu hoặc thay đổi file trạng thái. Hãy cấp đúng owner/group và quyền tối thiểu theo package, thay vì mở rộng quyền toàn hệ thống.

### 6.2. Quyền trên thư mục cha

Ngay cả khi datadir có quyền đúng, mysqld vẫn không truy cập được nếu một thư mục cha không có quyền traverse cho service account.

Kiểm tra đường dẫn:

~~~bash
namei -l /var/lib/mysql
ls -ld /var/lib/mysql
ls -l /var/lib/mysql
~~~

\`namei -l\` giúp kiểm tra quyền từng thành phần của đường dẫn. Trên hệ thống không có namei, kiểm tra từng thư mục cha bằng ls/stat.

### 6.3. Không chạy mysqld bằng root

Trên Unix-like OS, MySQL thường được cấu hình hạ quyền sang user riêng. Không khởi động server bằng root như một cách né permission error. Điều đó làm tăng phạm vi thiệt hại nếu có lỗi hoặc lỗ hổng.

Nếu service chạy bằng user mysql, hãy cấp quyền cho đúng user và kiểm tra service configuration.

## 7. SELinux và AppArmor

Unix permission không phải lớp kiểm soát duy nhất. Linux distribution có thể dùng SELinux hoặc AppArmor để giới hạn đường dẫn mà mysqld được truy cập.

### 7.1. AppArmor

Một số package Ubuntu/Debian dùng AppArmor profile cho mysqld. Profile có thể chỉ cho phép datadir mặc định và một số đường dẫn log/socket.

Nếu chuyển datadir sang \`/srv/mysql/data\`, mysqld có thể bị chặn dù owner và mode đã đúng.

Kiểm tra trạng thái và log:

~~~bash
sudo aa-status
sudo journalctl -k --since "10 minutes ago" | grep -i apparmor
~~~

Cách xử lý:
1. Xác định profile thực tế của mysqld.
2. Thêm rule cho đúng datadir, log, socket hoặc tmpdir cần thiết.
3. Nạp lại profile theo quy trình của distribution.
4. Khởi động lại/kiểm tra service.
5. Xác nhận không còn denial.

Không tắt AppArmor toàn hệ thống để sửa một đường dẫn sai. Cập nhật policy hẹp nhất có thể.

### 7.2. SELinux

Trên hệ thống bật SELinux, file context có thể quan trọng ngang quyền Unix.

Kiểm tra:

~~~bash
getenforce
ls -Zd /var/lib/mysql
ausearch -m AVC -ts recent
~~~

Nếu datadir chuyển sang đường dẫn tùy chỉnh, cần gán file context phù hợp với loại dữ liệu MySQL theo policy của distribution. Ví dụ quy trình thường dùng:

~~~bash
semanage fcontext -a -t mysqld_db_t "/srv/mysql/data(/.*)?"
restorecon -Rv /srv/mysql/data
~~~

Tên type và policy có thể khác theo distribution. Kiểm tra package policy trước khi áp dụng. Không dùng \`setenforce 0\` hoặc tắt SELinux làm giải pháp lâu dài.

## 8. Socket là gì?

Trên Unix-like OS, Unix-domain socket là endpoint giao tiếp cục bộ giữa client và mysqld. Nó không phải TCP port và không phải file dữ liệu database, dù filesystem hiển thị socket như một entry.

Một số package dùng đường dẫn như:

~~~text
/run/mysqld/mysqld.sock
~~~

Client có thể kết nối qua socket:

~~~bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock -u app_user -p
~~~

Kết nối TCP loopback:

~~~bash
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_user -p
~~~

Trên Unix, host \`localhost\` thường chọn Unix socket theo client behavior; \`127.0.0.1\` thường buộc TCP. Để tránh mơ hồ khi chẩn đoán, chỉ định \`--protocol\` rõ ràng.

### 8.1. Socket path phải khớp giữa server và client

Server có biến \`socket\`; client cũng có thể đọc option \`socket\` từ section \`[client]\` hoặc \`[mysql]\`.

Ví dụ:

~~~ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock

[mysql]
socket=/run/mysqld/mysqld.sock
~~~

Nếu server tạo socket ở một đường dẫn nhưng client tìm ở đường dẫn khác, client báo lỗi không tìm thấy socket dù mysqld đang chạy.

Kiểm tra phía server:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'socket';
~~~

Kiểm tra phía OS:

~~~bash
ls -l /run/mysqld/
ss -xl | grep mysql
~~~

Tên socket và công cụ kiểm tra phụ thuộc distribution.

### 8.2. Quyền trên socket và thư mục chứa socket

Client cần quyền truy cập socket file và quyền traverse thư mục cha. Socket directory thường được service manager tạo khi khởi động.

Không đặt socket trong thư mục world-writable nếu không cần thiết. Không xóa socket file khi server còn chạy. Nếu socket file còn sót sau crash, trước tiên xác minh không có mysqld instance nào đang sử dụng nó; chỉ xử lý file stale theo runbook của hệ thống.

## 9. Runtime directory như /run/mysqld

Trên nhiều Linux distribution, \`/run\` là filesystem runtime được tạo lại sau reboot và thường nằm trong tmpfs. Vì vậy, thư mục \`/run/mysqld\` có thể không tồn tại sau khi khởi động máy nếu service/package không tạo lại.

Service manager có thể tạo runtime directory và gán owner/group khi start. Một systemd unit có thể dùng các cơ chế như RuntimeDirectory; package có thể dùng tmpfiles.d hoặc script khởi động.

Kiểm tra:

~~~bash
systemctl cat mysql
systemd-tmpfiles --cat-config | grep -i mysqld
ls -ld /run/mysqld
~~~

Không tạo thư mục runtime một lần bằng tay rồi nghĩ nó sẽ tồn tại qua reboot. Hãy dùng cơ chế khởi tạo runtime directory của service manager/package.

Nếu tự quản lý systemd override:
- Chỉ override thuộc tính cần thiết.
- Giữ nguyên unit gốc.
- Kiểm tra quyền user/group.
- Chạy daemon-reload khi thay đổi unit.
- Kiểm thử restart và reboot trong staging.

## 10. PID file là gì?

PID file ghi process ID của mysqld. Ví dụ:

~~~text
/run/mysqld/mysqld.pid
~~~

Một số service script và công cụ vận hành dùng PID file để xác định tiến trình. Biến server:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'pid_file';
~~~

Trên shell:

~~~bash
cat /run/mysqld/mysqld.pid
ps -p "$(cat /run/mysqld/mysqld.pid)" -o pid,comm,args
~~~

PID file không phải cơ chế xác thực duy nhất rằng server đang hoạt động. PID có thể được tái sử dụng sau khi process kết thúc; phải xác minh command line, executable và service state.

### 10.1. PID file stale

Sau crash hoặc shutdown không sạch, có thể còn PID file cũ. Khi mysqld khởi động lại, nó có thể từ chối khởi động vì PID file tồn tại hoặc service script hiểu nhầm instance đang chạy.

Quy trình xử lý:
1. Kiểm tra service state.
2. Kiểm tra tất cả tiến trình mysqld trên host.
3. Xác minh PID trong file có còn là mysqld instance tương ứng không.
4. Kiểm tra datadir và socket của đúng instance.
5. Chỉ khi chắc chắn file stale và không có server đang chạy mới xử lý theo runbook.
6. Đọc error log và tìm nguyên nhân shutdown bất thường.

Không xóa PID file chỉ vì service không khởi động. Nếu mysqld thực sự đang chạy, xóa file có thể làm service manager mất khả năng theo dõi tiến trình.

## 11. Socket/PID và nhiều MySQL instance

Một máy có thể chạy nhiều MySQL instance, nhưng mỗi instance cần tài nguyên và đường dẫn riêng.

| Tài nguyên | Instance A | Instance B |
|---|---|---|
| datadir | /srv/mysql/a/data | /srv/mysql/b/data |
| socket | /run/mysqld/a.sock | /run/mysqld/b.sock |
| pid_file | /run/mysqld/a.pid | /run/mysqld/b.pid |
| port | 3306 | 3307 |
| error log | /var/log/mysql/a.err | /var/log/mysql/b.err |

Không dùng chung:
- Datadir.
- Socket path.
- PID file path.
- Port TCP.
- Error log path nếu cần phân biệt vận hành.
- Binary log/relay log basename khi cấu hình yêu cầu riêng.

Ví dụ cấu hình:

~~~ini
[mysqld]
port=3307
datadir=/srv/mysql/b/data
socket=/run/mysqld/b.sock
pid-file=/run/mysqld/b.pid
log-error=/var/log/mysql/b.err
server-id=102
~~~

Mỗi instance phải có quyền filesystem riêng và service unit/command line rõ ràng. Không khởi động hai mysqld trên cùng datadir; InnoDB không được thiết kế để hai server độc lập cùng mở một datadir như vậy.

## 12. Kết nối trên Windows: named pipe và TCP

Windows không sử dụng Unix-domain socket theo cách Linux. MySQL trên Windows có thể dùng TCP/IP và, nếu được bật/hỗ trợ, named pipe hoặc shared memory.

Ví dụ cấu hình named pipe:

~~~ini
[mysqld]
named_pipe=ON
socket=MYSQL
~~~

Client có thể chọn protocol pipe theo client/version hỗ trợ:

~~~powershell
mysql --protocol=PIPE --socket=MYSQL -u app_user -p
~~~

TCP:

~~~powershell
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_user -p
~~~

Không nhầm giá trị \`socket\` trên Windows với đường dẫn file Unix socket. Tùy phiên bản và cấu hình, nó có thể là tên named pipe.

### 12.1. Quyền service account và NTFS ACL

MySQL Windows service chạy dưới một account, ví dụ Network Service, Local System hoặc account chuyên dụng. Account đó cần quyền phù hợp trên:
- Datadir.
- Thư mục log.
- Thư mục tạm.
- Thư mục runtime/file liên quan.
- Thư mục keyring hoặc plugin nếu cấu hình sử dụng.

Kiểm tra service account:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'mysql' } |
  Select-Object Name, StartName, PathName
~~~

Kiểm tra ACL:

~~~powershell
icacls "C:\ProgramData\MySQL\MySQL Server 8.4\Data"
~~~

Cấp quyền theo account thực tế của service, không cấp Everyone Full Control. Khi đổi service account, phải rà soát toàn bộ đường dẫn mà mysqld cần truy cập.

## 13. Quyền filesystem khác với quyền SQL

MySQL có hai lớp quyền riêng biệt:

- **SQL privilege**: kiểm soát account được SELECT, INSERT, UPDATE, DELETE, EXECUTE, FILE... trên database/object.
- **Filesystem permission**: kiểm soát process mysqld có thể đọc, ghi, tạo hoặc xóa file trên hệ điều hành.

Một user có quyền SELECT trong MySQL không có nghĩa họ có thể đọc trực tiếp file InnoDB trên filesystem. Ngược lại, người có quyền đọc datadir ở OS có thể tiếp cận dữ liệu nhạy cảm ngoài lớp SQL authorization.

Ví dụ quyền SQL:

~~~sql
GRANT SELECT ON app_db.* TO 'report_user'@'%';
~~~

Lệnh này không cấp quyền filesystem cho report_user và cũng không thay đổi owner của datadir.

### 13.1. FILE privilege và secure_file_priv

Một số câu lệnh đọc/ghi file phía server như \`LOAD DATA INFILE\`, \`SELECT ... INTO OUTFILE\` cần quyền FILE và còn chịu giới hạn của \`secure_file_priv\`, filesystem permissions và policy OS.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
SHOW GRANTS FOR CURRENT_USER();
~~~

Nếu \`secure_file_priv\` trỏ tới một thư mục, thao tác file phía server bị giới hạn theo cấu hình đó. Nếu giá trị NULL, các thao tác file bị vô hiệu hóa theo quy tắc biến này; nếu rỗng, không có giới hạn thư mục từ biến nhưng quyền FILE và OS vẫn áp dụng. Kiểm tra tài liệu đúng phiên bản.

\`LOAD DATA LOCAL INFILE\` khác với server-side INFILE: dữ liệu được đọc từ phía client và gửi lên server, do đó có thêm yếu tố cấu hình client/server về LOCAL. Không suy luận quyền của một loại từ loại còn lại.

## 14. Di chuyển datadir an toàn

Di chuyển datadir là thao tác vận hành có rủi ro cao vì liên quan toàn bộ dữ liệu của instance. Không chỉ sửa \`datadir\` trong my.cnf rồi restart.

### 14.1. Chuẩn bị

Trước khi chuyển:
1. Xác định đúng instance và datadir hiện tại bằng \`@@datadir\`.
2. Ghi lại basedir, socket, pid_file, tmpdir, error log, binary log, relay log và các tablespace path liên quan.
3. Kiểm tra dung lượng filesystem đích, inode, mount options và quota.
4. Xác minh filesystem đích phù hợp với MySQL/InnoDB và có durability cần thiết.
5. Backup có thể restore và thử phục hồi.
6. Lên maintenance window và thông báo ứng dụng.
7. Chuẩn bị quyền owner/group/ACL.
8. Cập nhật AppArmor/SELinux policy nếu cần.
9. Chuẩn bị cấu hình mới và kế hoạch quay lại đường dẫn cũ.

### 14.2. Dừng server sạch

Dừng bằng service manager:

~~~bash
sudo systemctl stop mysql
systemctl status mysql
~~~

Xác minh không còn mysqld của instance đang chạy. Đừng chỉ dựa vào service command trả về; kiểm tra process và log shutdown.

Không copy datadir đang hoạt động bằng \`cp\` hoặc \`rsync\` thông thường rồi coi đó là physical backup nhất quán. Nếu không thể dừng server, dùng công cụ backup/clone/snapshot được thiết kế cho MySQL.

### 14.3. Copy và bảo toàn metadata

Ví dụ minh họa trên Linux khi server đã dừng sạch:

~~~bash
sudo rsync -aHAX --numeric-ids /var/lib/mysql/ /srv/mysql/data/
~~~

Các option bảo toàn metadata quan trọng có thể phụ thuộc filesystem và quyền quản trị. Kiểm tra kết quả:
- Owner/group.
- Mode.
- ACL.
- Extended attributes.
- Symlink.
- Tổng dung lượng và số file.
- Mount point thực tế.

Không xóa datadir cũ ngay. Giữ bản cũ ở trạng thái không được mysqld sử dụng cho tới khi instance mới chạy và đã xác minh.

### 14.4. Cập nhật cấu hình và policy

Sửa đúng section \`[mysqld]\`:

~~~ini
[mysqld]
datadir=/srv/mysql/data
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
~~~

Đồng thời:
- Cập nhật AppArmor/SELinux.
- Cập nhật service unit nếu có path hard-coded.
- Xác minh thư mục runtime socket/PID vẫn được tạo.
- Kiểm tra các tablespace/log path riêng.
- Không đổi socket client path ngoài dự kiến.

### 14.5. Khởi động và xác minh

~~~bash
sudo systemctl start mysql
systemctl status mysql
journalctl -u mysql -n 100 --no-pager
~~~

Sau khi kết nối:

~~~sql
SELECT
    @@datadir,
    @@socket,
    @@pid_file,
    @@log_error,
    @@server_uuid;

SHOW ENGINE INNODB STATUS;
~~~

Kiểm tra:
- Server mở đúng datadir mới.
- Schema và bảng quan trọng tồn tại.
- Dữ liệu mẫu và số lượng bản ghi phù hợp.
- Replication/binlog hoạt động nếu có.
- Ứng dụng kết nối đúng socket/port.
- Backup mới chạy được.
- Error log không có lỗi permission hoặc tablespace.

Chỉ sau khi xác minh và có backup mới, mới lên kế hoạch loại bỏ bản datadir cũ theo chính sách lưu trữ. Không xóa ngay sau lần khởi động đầu tiên.

## 15. Filesystem, mount và độ bền dữ liệu

Datadir nên nằm trên filesystem có tính bền vững và được hỗ trợ cho workload MySQL. Cần đánh giá:
- Latency và throughput I/O.
- fsync semantics và write durability.
- Dung lượng và inode.
- Quota.
- Mount options.
- RAID/storage controller cache policy.
- Snapshot/backup integration.
- Hành vi khi filesystem đầy hoặc mất mount.

Không đặt datadir trên thư mục tạm hoặc filesystem runtime như tmpfs. Không giả định network filesystem/NFS/SMB tương đương local block storage; cần kiểm tra hỗ trợ chính thức và semantics locking/fsync trước khi triển khai.

Nếu volume datadir không mount khi service start, mysqld có thể tạo hoặc nhìn thấy một thư mục rỗng ở mountpoint trên filesystem gốc. Điều này nguy hiểm vì server có thể khởi động nhầm trên thư mục rỗng. Service cần phụ thuộc mount đúng cách và startup phải xác minh volume đã mount.

### 15.1. Kiểm tra mount trên Linux

~~~bash
findmnt /srv/mysql/data
df -h /srv/mysql/data
df -i /srv/mysql/data
mount | grep '/srv/mysql'
~~~

Kiểm tra mount options và thiết bị thực tế. Trong systemd, có thể dùng dependency phù hợp như RequiresMountsFor cho service tùy chỉnh; phải kiểm tra unit và package hiện có trước khi thêm override.

### 15.2. Filesystem đầy

Nếu filesystem datadir hoặc log đầy:
- INSERT/UPDATE có thể thất bại.
- InnoDB có thể không ghi được redo/undo hoặc data page.
- Binary log có thể không tiếp tục ghi.
- Server có thể dừng hoặc chuyển trạng thái lỗi.
- Replication có thể bị gián đoạn.

Không xóa file InnoDB hoặc binary log bằng rm để giải phóng dung lượng. Dùng SQL/rotation/purge theo quy trình:
- Xác định file nào chiếm dung lượng.
- Kiểm tra backup và replication consumers.
- Purge binary logs bằng lệnh MySQL phù hợp.
- Mở rộng volume hoặc chuyển log theo kế hoạch.
- Khôi phục dung lượng tạm an toàn.
- Kiểm tra InnoDB và replication sau xử lý.

## 16. Đường dẫn liên quan nhưng không đồng nhất với datadir

Một số biến đường dẫn cần xem xét khi thiết kế filesystem:

| Biến/nhóm | Ý nghĩa |
|---|---|
| innodb_data_home_dir | Vị trí cơ sở cho system tablespace path nếu cấu hình |
| innodb_data_file_path | Định nghĩa system tablespace data file |
| innodb_undo_directory | Thư mục undo tablespace trong các cấu hình có sử dụng |
| innodb_redo_log_capacity | Dung lượng redo log được quản lý; không phải một đường dẫn |
| tmpdir | Thư mục tệp tạm server |
| log_error | Error log |
| log_bin_basename | Đường dẫn binary log |
| relay_log_basename | Đường dẫn relay log |
| secure_file_priv | Thư mục giới hạn thao tác file phía server |
| keyring_file_data | Đường dẫn keyring file nếu dùng plugin/component tương ứng |

Không thay đổi các biến này chỉ vì đang di chuyển datadir. Một số biến không còn được dùng hoặc thay đổi theo phiên bản. Kiểm tra biến có tồn tại trên server và đọc tài liệu của đúng phiên bản.

## 17. Container và volume permissions

Trong container, datadir thường được mount từ persistent volume. Container restart không nên làm mất dữ liệu; volume phải tồn tại độc lập với vòng đời container.

Các vấn đề thường gặp:
- UID/GID bên trong image không khớp owner volume trên host.
- Volume mount read-only.
- SELinux label không phù hợp.
- Thư mục host có quyền không cho mysqld ghi.
- Volume chưa mount nhưng container vẫn khởi động.
- Hai container cùng mount một datadir.

Quy trình:
1. Xác định UID/GID của user mysqld trong image thực tế.
2. Kiểm tra owner và mode trên volume.
3. Kiểm tra mount mode và SELinux labeling.
4. Chỉ thay owner/ACL cho đúng volume và đúng instance.
5. Bảo đảm một datadir chỉ được mở bởi một mysqld instance.
6. Dùng volume persistent và backup độc lập.
7. Kiểm thử restart/recreate container và restore.

Không chạy \`chmod -R 777\` trên volume. Không chia sẻ cùng một datadir cho nhiều container mysqld như một cách scale read replica; dùng replication/clone hoặc cơ chế triển khai MySQL phù hợp.

## 18. Chẩn đoán lỗi khởi động liên quan đường dẫn

Khi mysqld không khởi động, kiểm tra theo thứ tự:

1. Service manager báo lỗi gì?
2. Binary và option files nào đang được dùng?
3. Datadir có tồn tại và đúng instance không?
4. Filesystem chứa datadir đã mount chưa?
5. Owner/mode/ACL có đúng không?
6. Service account có quyền traverse mọi thư mục cha không?
7. SELinux/AppArmor có denial không?
8. Socket/PID directory có tồn tại và có quyền ghi không?
9. PID file có stale hay process cũ còn chạy không?
10. Disk/inode có đầy không?
11. Error log báo lỗi InnoDB, redo log, tablespace hay version compatibility không?

Trên Linux:

~~~bash
systemctl status mysql
journalctl -u mysql -n 200 --no-pager
tail -n 100 /var/log/mysql/error.log
namei -l /var/lib/mysql
df -h
df -i
~~~

Tên error log và unit phụ thuộc package. Ưu tiên đường dẫn được server báo qua \`log_error\` hoặc service config.

Trên Windows:

~~~powershell
Get-Service *mysql*
Get-WinEvent -LogName Application -MaxEvents 100
icacls "C:\ProgramData\MySQL\MySQL Server 8.4\Data"
~~~

Kiểm tra service PathName, account và error log cụ thể. Không thay ACL hoặc xóa PID/socket/data file khi chưa xác định nguyên nhân.

## 19. Runbook xử lý lỗi socket và PID

### 19.1. Client báo Can't connect through socket

Kiểm tra:
- mysqld có chạy không.
- Server socket path là gì.
- Client socket path là gì.
- Socket directory có tồn tại không.
- Service account có tạo socket được không.
- AppArmor/SELinux có chặn không.
- Client có đang dùng TCP thay vì socket hoặc ngược lại không.

Ví dụ:

~~~bash
mysqladmin --protocol=SOCKET \
  --socket=/run/mysqld/mysqld.sock ping
~~~

Nếu cần kiểm tra TCP:

~~~bash
mysqladmin --protocol=TCP \
  -h 127.0.0.1 -P 3306 ping
~~~

Không sửa socket path trước khi xác minh server thực sự đang lắng nghe ở endpoint nào.

### 19.2. Server báo PID file already exists

Kiểm tra process:

~~~bash
ps -ef | grep '[m]ysqld'
cat /run/mysqld/mysqld.pid
~~~

Nếu process còn chạy, xác định instance và service unit. Nếu không còn process và PID file thực sự stale, xử lý theo runbook sau khi xác minh datadir/socket tương ứng. Đọc error log để tìm lý do lần dừng trước.

### 19.3. Server không thể tạo PID/socket

Nguyên nhân thường gặp:
- /run/mysqld không tồn tại sau reboot.
- Owner/group sai.
- Service account bị đổi.
- Filesystem read-only.
- Policy AppArmor/SELinux chặn.
- Path trong option file không khớp.

Sửa nguyên nhân tại service/runtime directory và policy. Không đặt PID/socket vào datadir chỉ để tránh xử lý runtime directory nếu điều đó làm cấu hình khó quản lý hơn.

## 20. Bảo mật dữ liệu ở cấp filesystem

Datadir thường chứa dữ liệu nghiệp vụ và metadata bảo mật. Bảo vệ nó như tài sản nhạy cảm:

- Chỉ tài khoản service và nhóm quản trị được phép truy cập.
- Không để datadir nằm trong web root hoặc thư mục người dùng chia sẻ.
- Bảo vệ backup và snapshot với mức quyền tương đương hoặc cao hơn.
- Dùng encryption at rest khi yêu cầu bảo mật cần thiết.
- Quản lý keyring/key material tách biệt và có backup phục hồi.
- Không đưa mật khẩu, key hoặc dữ liệu production vào log/chẩn đoán không kiểm soát.
- Audit quyền truy cập filesystem.
- Dùng OS account riêng cho mysqld.
- Không chạy server bằng root.
- Không cấp FILE privilege rộng nếu không cần.

Encryption at rest không thay thế quyền filesystem. Người có quyền truy cập file và key có thể vẫn đọc được dữ liệu; cần bảo vệ cả data files, backup và key management.

## 21. Checklist triển khai đường dẫn production

- [ ] Đã xác định đúng instance, binary và service account.
- [ ] Đã ghi lại basedir, datadir, socket, pid_file và tmpdir từ runtime.
- [ ] Đã phân biệt datadir với backup directory.
- [ ] Đã xác định các log/tablespace/keyring path nằm ngoài datadir.
- [ ] Datadir nằm trên filesystem bền vững, đủ dung lượng và inode.
- [ ] Volume được mount trước khi mysqld khởi động.
- [ ] Không có hai mysqld dùng chung một datadir.
- [ ] Owner/group/ACL được cấp theo nguyên tắc tối thiểu.
- [ ] Mọi thư mục cha có quyền traverse cần thiết.
- [ ] SELinux/AppArmor policy cho phép đúng các đường dẫn.
- [ ] Runtime directory cho socket/PID được tạo lại sau reboot.
- [ ] Client socket path khớp server socket path.
- [ ] PID file được quản lý bởi đúng service instance.
- [ ] Không dùng chmod 777 hoặc chạy mysqld bằng root.
- [ ] FILE privilege và secure_file_priv được kiểm soát.
- [ ] Quy trình initialize chỉ dùng cho datadir mới, trống.
- [ ] Migration datadir có backup restore-tested và maintenance plan.
- [ ] Sao chép vật lý chỉ thực hiện sau shutdown sạch hoặc bằng công cụ backup phù hợp.
- [ ] Đã xác minh startup, error log, SQL query và ứng dụng sau migration.
- [ ] Đã kiểm tra restart/reboot và quyền volume nếu chạy container.
- [ ] Đã có runbook cho socket error, stale PID, disk full và permission denied.

## 22. Bài tập thực hành

### Bài 1: Khám phá đường dẫn runtime

Kết nối MySQL và truy vấn basedir, datadir, socket, pid_file, tmpdir, log_error và secure_file_priv. Đối chiếu với service configuration trên hệ điều hành.

### Bài 2: Phân biệt datadir và backup

Tạo logical backup trong một thư mục riêng. So sánh cấu trúc backup với datadir. Thử restore vào một instance lab độc lập và xác minh dữ liệu.

### Bài 3: Kiểm tra quyền filesystem

Trên Linux lab, xem owner/mode của datadir và từng thư mục cha bằng namei. Thử chạy service với quyền không đủ trong môi trường thử nghiệm, đọc error log rồi khôi phục quyền tối thiểu.

### Bài 4: Socket và TCP

Kết nối lần lượt bằng Unix socket và TCP loopback. Quan sát endpoint, dùng mysqladmin ping và giải thích vì sao localhost có thể chọn socket trong khi 127.0.0.1 dùng TCP.

### Bài 5: Runtime directory

Kiểm tra /run/mysqld sau reboot. Xác định package/systemd tạo thư mục bằng cơ chế nào. Không dựa vào mkdir thủ công; thử restart service và xác minh socket/PID được tạo lại.

### Bài 6: PID file stale

Trong VM lab, quan sát PID file khi server chạy và sau shutdown sạch. Không kill production process. Mô phỏng stale PID trên một instance disposable, xác minh process trước khi xử lý.

### Bài 7: Windows service account

Trên Windows lab, kiểm tra StartName và PathName của MySQL service. Dùng icacls xem ACL datadir. Đề xuất quyền tối thiểu cho service account.

### Bài 8: Di chuyển datadir

Tạo instance lab có dữ liệu mẫu. Backup và restore-test. Dừng server sạch, copy datadir sang volume khác, cập nhật option file và security policy, start lại, xác minh dữ liệu và endpoint.

### Bài 9: AppArmor/SELinux

Trong VM lab có policy, đổi datadir sang đường dẫn tùy chỉnh. Quan sát permission denial dù Unix mode đúng. Cập nhật policy hẹp và xác minh service khởi động.

### Bài 10: Multi-instance

Tạo hai instance disposable với datadir, socket, PID, port và error log riêng. Xác minh client kết nối đúng instance và không dùng chung data directory.

### Bài 11: Disk và inode

Quan sát df -h và df -i trên filesystem lab. Mô phỏng dung lượng thấp an toàn, đọc log và lập quy trình phục hồi. Không xóa data file để tạo dung lượng.

### Bài 12: Runbook

Viết runbook ngắn cho ba tình huống: socket không tồn tại, PID file đã tồn tại và mysqld permission denied. Mỗi tình huống cần có lệnh kiểm tra, bằng chứng cần thu thập và điều kiện trước khi sửa.

## 23. Kết luận

Data directory, socket, PID file và quyền filesystem là các phần khác nhau nhưng phải phối hợp để MySQL hoạt động ổn định. Datadir giữ dữ liệu của instance; socket hoặc named pipe cung cấp endpoint giao tiếp cục bộ; PID file giúp service manager nhận diện process. Các đường dẫn này phải khớp với cấu hình hiệu lực, service account, quyền thư mục cha, runtime directory và security policy của hệ điều hành.

Khi khởi tạo, chỉ dùng datadir mới và trống. Khi di chuyển, backup và xác minh khả năng restore, dừng server sạch, sao chép có bảo toàn metadata, cập nhật policy/configuration rồi kiểm tra đầy đủ trước khi loại bỏ bản cũ. Không copy data files đang hoạt động bằng công cụ filesystem thông thường, không xóa PID/socket khi chưa xác minh process, không dùng chmod 777 và không chạy mysqld bằng root.

Cuối cùng, luôn phân biệt quyền SQL với quyền filesystem, datadir với backup, socket với TCP port và PID file với trạng thái process thật. Ghi lại các giá trị runtime, kiểm tra sau restart/reboot và duy trì runbook cho lỗi đường dẫn, permission, mount và dung lượng.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Data Directory](https://dev.mysql.com/doc/refman/8.4/en/data-directory.html)
- [MySQL 8.4 Reference Manual – Server Configuration Defaults](https://dev.mysql.com/doc/refman/8.4/en/server-configuration-defaults.html)
- [MySQL 8.4 Reference Manual – Option Files](https://dev.mysql.com/doc/refman/8.4/en/option-files.html)
- [MySQL 8.4 Reference Manual – Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual – mysqld: The MySQL Server](https://dev.mysql.com/doc/refman/8.4/en/mysqld.html)
- [MySQL 8.4 Reference Manual – Initializing the Data Directory](https://dev.mysql.com/doc/refman/8.4/en/data-directory-initialization.html)
- [MySQL 8.4 Reference Manual – Connecting to the MySQL Server Using Unix Sockets](https://dev.mysql.com/doc/refman/8.4/en/connecting.html)
- [MySQL 8.4 Reference Manual – Connecting to the MySQL Server Using Named Pipes](https://dev.mysql.com/doc/refman/8.4/en/windows-and-named-pipes.html)
- [MySQL 8.4 Reference Manual – Secure File Privileges](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_secure_file_priv)
- [MySQL 8.4 Reference Manual – mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual – InnoDB Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/innodb-backup.html)

