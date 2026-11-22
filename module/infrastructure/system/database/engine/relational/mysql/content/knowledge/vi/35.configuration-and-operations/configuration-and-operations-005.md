# Quản lý systemd/service hoặc vòng đời container theo môi trường

MySQL cần một quy trình vận hành phù hợp với cách triển khai của từng môi trường. Trên máy chủ Linux, systemd thường quản lý tiến trình mysqld như một service. Trên Windows, MySQL chạy dưới dạng Windows Service. Trong môi trường container, Docker hoặc một nền tảng điều phối chịu trách nhiệm tạo, dừng, khởi động lại và giám sát container.

Các thao tác start, stop, restart có vẻ đơn giản nhưng liên quan trực tiếp đến tính toàn vẹn dữ liệu, khả năng phục hồi, cấu hình, log, quyền truy cập và thời gian gián đoạn. Đặc biệt, vòng đời container còn gắn với persistent volume: container có thể bị thay thế thường xuyên, trong khi dữ liệu database phải tồn tại độc lập với container.

Trong module **DATABASE_MYSQL**, bài học này trình bày cách quản lý MySQL service trên Linux và Windows, vận hành MySQL bằng Docker Compose, triển khai cấu hình theo môi trường, kiểm tra health/readiness, đọc log, bảo vệ secret, sao lưu và nâng cấp an toàn.

## 1. Chọn mô hình vận hành theo môi trường

Mô hình quản lý MySQL thường gặp:

| Môi trường | Cách chạy MySQL | Thành phần quản lý vòng đời |
|---|---|---|
| Máy Linux cài package | Tiến trình mysqld trên host | systemd và service unit của package |
| Máy Windows | Tiến trình mysqld chạy nền | Windows Service Manager |
| Máy phát triển cá nhân | Container hoặc package cục bộ | Docker Compose hoặc service manager |
| CI/test tạm thời | Container dùng cho một lần kiểm thử | Pipeline/Compose runner |
| Staging | Service hoặc container gần giống production | systemd, Compose hoặc nền tảng điều phối |
| Production | Service được giám sát, có backup và recovery | systemd hoặc nền tảng container/orchestrator |

Không có một lệnh quản lý duy nhất phù hợp cho mọi nơi. Cần xác định rõ:

- Ai chịu trách nhiệm khởi động MySQL sau reboot?
- Dữ liệu được lưu ở datadir hoặc volume nào?
- File cấu hình nào được nạp?
- Log được ghi vào journald, file hay container log driver?
- Ứng dụng kiểm tra database đã sẵn sàng bằng cách nào?
- Ai quản lý secret và tài khoản?
- Quy trình backup, restore, upgrade và rollback là gì?

Một môi trường phát triển có thể ưu tiên thao tác nhanh. Production cần thêm kiểm soát thay đổi, thời gian gián đoạn, giám sát, backup và kế hoạch phục hồi.

## 2. Vòng đời MySQL service trên Linux với systemd

Khi cài MySQL từ package của hệ điều hành hoặc từ Oracle MySQL repository, package thường cung cấp service unit. Tên service có thể khác nhau theo bản phân phối và package:

- Debian/Ubuntu thường dùng tên mysql.
- Một số bản phân phối RPM thường dùng tên mysqld.

Kiểm tra tên service thực tế trước khi thao tác:

```bash
systemctl list-unit-files | grep -E 'mysql|mysqld'
systemctl status mysql
```

Trong ví dụ, dùng mysql nếu đó là tên unit của package đang cài; nếu hệ thống dùng mysqld, thay tên trong lệnh status bằng mysqld. Chỉ một trong các tên trên có thể tồn tại. Nếu không tìm thấy, kiểm tra tên unit do package đã cài cung cấp thay vì tự tạo một service trùng tên.

### 2.1. Phân biệt trạng thái chạy và trạng thái tự khởi động

systemd quản lý ít nhất hai khía cạnh cần phân biệt:

- Active state: service hiện đang chạy, dừng, lỗi hoặc đang chuyển trạng thái.
- Enablement state: service có được cấu hình để tự khởi động theo target khi máy boot hay không.

Một service có thể đang chạy nhưng chưa được enable. Ngược lại, service đã enable nhưng hiện đang stopped.

Kiểm tra:

```bash
systemctl is-active mysql
systemctl is-enabled mysql
systemctl status mysql
```

Khởi động ngay và bật tự khởi động khi boot:

```bash
sudo systemctl enable --now mysql
```

Tắt tự khởi động nhưng không dừng service đang chạy:

```bash
sudo systemctl disable mysql
```

Dừng service và bỏ cấu hình tự khởi động:

```bash
sudo systemctl disable --now mysql
```

Enable và disable điều chỉnh hành vi ở lần boot tiếp theo; start, stop và restart tác động đến trạng thái hiện tại.

### 2.2. Start, stop và restart

Các lệnh cơ bản:

```bash
sudo systemctl start mysql
sudo systemctl stop mysql
sudo systemctl restart mysql
sudo systemctl status mysql
```

Restart dừng service rồi khởi động lại. Với unit MySQL được cung cấp bởi package, service manager sử dụng cơ chế stop/start đã được package định nghĩa. MySQL thực hiện quá trình shutdown có kiểm soát để đóng kết nối, hoàn tất công việc cần thiết và ghi dữ liệu bền vững.

Không dùng kill -9 như thao tác stop thông thường. SIGKILL không cho mysqld cơ hội shutdown sạch; InnoDB có thể phải crash recovery ở lần khởi động sau và thời gian phục hồi có thể dài. Chỉ dùng biện pháp cưỡng bức theo runbook xử lý sự cố khi đã hiểu rõ hậu quả.

Có thể yêu cầu MySQL shutdown bằng công cụ quản trị:

```bash
mysqladmin --defaults-extra-file=/path/to/client.cnf shutdown
```

Tài khoản cần có quyền SHUTDOWN. File client option phải được bảo vệ quyền đọc và không đưa mật khẩu trực tiếp vào lịch sử shell.

### 2.3. Kiểm tra service unit

Đọc unit đang được systemd sử dụng:

```bash
systemctl cat mysql
systemctl show mysql -p FragmentPath -p DropInPaths
```

Unit package có thể khai báo:

- User và Group chạy tiến trình.
- Đường dẫn executable và tham số khởi động.
- Cách dừng tiến trình.
- Restart policy.
- Giới hạn tài nguyên và sandbox.
- Quan hệ phụ thuộc với filesystem hoặc network.

Không thay thế unit package bằng một file tự viết nếu chưa hiểu đầy đủ cách package quản lý datadir, socket, PID file, runtime directory và quyền truy cập. Nếu cần override, ưu tiên systemd drop-in:

```bash
sudo systemctl edit mysql
```

Sau khi thay đổi unit hoặc drop-in, yêu cầu systemd nạp lại định nghĩa:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mysql
```

daemon-reload chỉ nạp lại unit definitions. Nó không thay thế việc restart mysqld khi thay đổi file cấu hình MySQL. Cũng không cần chạy daemon-reload chỉ vì sửa một file cấu hình my.cnf.

### 2.4. Reload khác restart

systemctl reload mysql chỉ hoạt động nếu unit có định nghĩa hành động reload phù hợp. Không phải package hoặc unit nào cũng cung cấp thao tác này.

MySQL có một số biến cấu hình thay đổi được trong runtime và một số biến chỉ đọc khi khởi động. Với biến runtime, có thể dùng lệnh SQL phù hợp; với biến startup-only, cần sửa cấu hình hoặc giá trị persisted rồi restart. Không giả định rằng gọi systemctl reload sẽ làm mysqld đọc lại mọi file cấu hình.

Trước khi thay đổi, kiểm tra thuộc tính của biến trong tài liệu đúng phiên bản và xác nhận giá trị thực tế bằng SHOW VARIABLES.

## 3. Cấu hình MySQL trên máy chủ

MySQL có thể đọc cấu hình từ nhiều file option tùy hệ điều hành, cách cài đặt và tham số khởi động. Các vị trí thường gặp gồm:

| Môi trường | Vị trí thường gặp |
|---|---|
| Linux package | /etc/my.cnf, /etc/mysql/my.cnf |
| Linux include directory | /etc/mysql/conf.d/, /etc/mysql/mysql.conf.d/ |
| Windows | my.ini trong thư mục cài đặt hoặc ProgramData |
| Docker image | /etc/mysql/conf.d/ hoặc đường dẫn cấu hình được mount |

Đây là các vị trí phổ biến, không phải danh sách cố định cho mọi bản cài. Hãy kiểm tra cách instance hiện tại được khởi động và file option thực sự được đọc.

### 3.1. Tách cấu hình theo mục đích

Ví dụ file cấu hình:

```ini
[mysqld]
port = 3306
bind-address = 127.0.0.1
max_connections = 200
innodb_buffer_pool_size = 2G
slow_query_log = ON
long_query_time = 1
```

Các tham số trên chỉ là ví dụ minh họa. Không sao chép giá trị tài nguyên sang production khi chưa đo RAM, workload, số kết nối và cấu hình phần cứng.

Có thể tách cấu hình thành các file nhỏ theo nhóm:

- server.cnf: tham số chung của server.
- innodb.cnf: cấu hình InnoDB.
- logging.cnf: general log, slow query log và error log.
- replication.cnf: thiết lập replication nếu có.

Chỉ đặt file trong include directory mà instance thực sự đọc. Tránh khai báo cùng một option ở nhiều nơi vì thứ tự nạp có thể làm giá trị cuối cùng khác với dự kiến.

### 3.2. Kiểm tra cấu hình trước khi restart

Một số phiên bản MySQL hỗ trợ kiểm tra cấu hình bằng tùy chọn --validate-config. Có thể dùng binary và option file tương ứng với package đang cài:

```bash
mysqld --validate-config
```

Tùy bản cài đặt, cần truyền đúng đường dẫn option file hoặc chạy dưới tài khoản có quyền đọc file cấu hình. Lệnh kiểm tra cú pháp/cấu hình không thay thế kiểm thử runtime và không bảo đảm mọi thay đổi đều phù hợp với workload.

Có thể xem các option mặc định mà chương trình nhận được bằng:

```bash
my_print_defaults mysqld
```

Sau khi server khởi động, kiểm tra giá trị đang hoạt động:

```sql
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
```

### 3.3. Biến runtime, startup-only và persisted configuration

Không phải biến MySQL nào cũng thay đổi được khi server đang chạy. Cần phân loại:

- Dynamic variable: có thể thay đổi ở runtime theo phạm vi GLOBAL hoặc SESSION nếu tài liệu cho phép.
- Read-only/startup-only variable: chỉ có hiệu lực khi mysqld khởi động.
- Persisted variable: có thể được lưu bằng cơ chế SET PERSIST để áp dụng qua lần restart sau, nếu biến hỗ trợ.

Ví dụ thay đổi và lưu một biến được hỗ trợ:

```sql
SET PERSIST max_connections = 300;
```

SET PERSIST ghi giá trị vào mysqld-auto.cnf. File này được MySQL quản lý; không sửa trực tiếp bằng trình soạn thảo. Giá trị persisted có thể có ưu tiên cao hơn cấu hình trong option file khi server khởi động, vì vậy cần quản lý nguồn cấu hình rõ ràng.

Nếu chỉ muốn thay đổi trong lần chạy hiện tại, dùng SET GLOBAL khi biến cho phép. Nếu cần đặt giá trị cho lần khởi động tiếp theo mà không thay đổi runtime hiện tại, kiểm tra SET PERSIST_ONLY và giới hạn của biến. Dùng RESET PERSIST để xóa giá trị persisted theo đúng tên biến khi cần rollback.

Không trộn lẫn file cấu hình, SET GLOBAL và SET PERSIST mà không ghi nhận nguồn sự thật. Một runbook nên lưu: giá trị mong muốn, nguồn quản lý, phạm vi, thời điểm áp dụng và cách rollback.

## 4. Quản lý MySQL bằng Windows Service

Trên Windows, MySQL thường được cài như một service có tên do installer hoặc quản trị viên chọn, ví dụ MySQL80. Tên service không nhất thiết trùng tên hiển thị hoặc phiên bản binary.

Kiểm tra service:

```powershell
Get-Service -Name '*MySQL*'
Get-Service -Name 'MySQL80'
```

Khởi động, dừng hoặc restart:

```powershell
Start-Service -Name 'MySQL80'
Stop-Service -Name 'MySQL80'
Restart-Service -Name 'MySQL80'
Get-Service -Name 'MySQL80'
```

Có thể dùng sc.exe query để xem trạng thái service:

```powershell
sc.exe query MySQL80
```

Tên MySQL80 trong ví dụ cần được thay bằng service name thực tế. Tài khoản service phải có quyền truy cập datadir, file cấu hình, log, certificate và các thư mục liên quan.

### 4.1. File my.ini và service arguments

MySQL trên Windows thường dùng file my.ini. Đường dẫn có thể được truyền trong service command line hoặc được chọn theo cơ chế tìm option file của bản cài.

Kiểm tra service configuration bằng công cụ quản trị Windows và đối chiếu đường dẫn binary, defaults-file, datadir và log. Không di chuyển datadir hoặc đổi service account mà chưa cập nhật ACL và kiểm tra quyền đọc/ghi.

Sau khi sửa tham số chỉ áp dụng lúc khởi động, restart service theo cửa sổ bảo trì phù hợp. Sau đó xác nhận server hoạt động và đọc error log.

## 5. Vòng đời MySQL trong Docker và Docker Compose

Container đóng gói mysqld cùng môi trường chạy. Docker quản lý container, còn dữ liệu MySQL cần được lưu ở volume bền vững.

Một container có thể bị xóa và tạo lại khi cập nhật image. Nếu datadir chỉ nằm trong writable layer của container, dữ liệu có thể mất khi container bị xóa. Vì vậy, cần gắn volume vào /var/lib/mysql.

### 5.1. Compose service mẫu

Ví dụ Compose cho môi trường phát triển hoặc staging:

```yaml
services:
  db:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: appdb
      MYSQL_USER: appuser
      MYSQL_PASSWORD_FILE: /run/secrets/db_app_password
      MYSQL_ROOT_PASSWORD_FILE: /run/secrets/db_root_password
    secrets:
      - db_app_password
      - db_root_password
    volumes:
      - mysql_data:/var/lib/mysql
      - ./mysql/conf.d:/etc/mysql/conf.d:ro
    ports:
      - "127.0.0.1:3306:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

volumes:
  mysql_data:

secrets:
  db_root_password:
    file: ./secrets/db_root_password.txt
  db_app_password:
    file: ./secrets/db_app_password.txt
```

Đây là ví dụ minh họa cho image MySQL chính thức và Docker Compose hỗ trợ file secrets. Trước khi dùng, kiểm tra tài liệu image đúng tag, phiên bản Compose và cơ chế secrets của nền tảng.

Các điểm cần chú ý:

- Pin image theo phiên bản đã kiểm thử; với production, cân nhắc tag patch cụ thể hoặc digest để tái lập chính xác image.
- Volume mysql_data giữ datadir qua vòng đời container.
- Thư mục cấu hình được mount read-only để container không ghi ngược vào cấu hình trên host.
- Port chỉ bind vào loopback trong ví dụ; production thường không cần publish cổng DB ra host nếu ứng dụng cùng Docker network.
- Secret file không được commit vào Git hoặc đưa vào image.
- restart policy unless-stopped giúp Docker khởi động lại container sau khi daemon hoặc host restart, theo chính sách đã chọn.

Nếu ứng dụng cũng nằm trong Compose, có thể cho ứng dụng chờ database healthy:

```yaml
services:
  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
```

depends_on với service_healthy điều phối thời điểm khởi chạy ban đầu. Ứng dụng vẫn phải tự xử lý reconnect và retry khi database mất kết nối sau đó.

### 5.2. Khởi động, dừng và kiểm tra container

Các lệnh thường dùng:

```bash
docker compose up -d db
docker compose ps
docker compose logs --tail=100 db
docker compose logs -f db
docker compose stop db
docker compose start db
docker compose restart db
```

- up -d tạo hoặc cập nhật container và chạy nền.
- stop dừng container nhưng giữ container và volume.
- start chạy lại container đã dừng.
- restart restart container hiện có.
- logs đọc stdout/stderr được Docker thu thập.

Kiểm tra MySQL bên trong container:

```bash
docker compose exec db mysqladmin ping -h 127.0.0.1 --silent
```

Lệnh ping giúp xác nhận server phản hồi. Với readiness ở mức ứng dụng, cần thêm kiểm tra kết nối SQL bằng tài khoản ứng dụng và câu truy vấn đơn giản, vì tiến trình có thể đang chạy nhưng quyền, schema hoặc phụ thuộc ứng dụng chưa sẵn sàng.

### 5.3. Xóa container không đồng nghĩa xóa dữ liệu

Một khác biệt quan trọng:

```bash
docker compose down
```

Lệnh trên dừng và xóa các container cùng network do Compose quản lý; named volume thông thường vẫn được giữ.

Lệnh sau có thể xóa cả named volume:

```bash
docker compose down --volumes
```

Nếu volume chứa /var/lib/mysql, dữ liệu database có thể bị xóa. Chỉ chạy lệnh có --volumes khi mục đích là hủy dữ liệu môi trường đó và đã xác nhận backup hoặc dữ liệu không cần giữ. Không đưa lệnh này vào runbook restart hằng ngày.

### 5.4. Biến khởi tạo chỉ áp dụng khi datadir mới

Các biến như MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD và MYSQL_ROOT_PASSWORD của image chính thức thường được dùng trong quá trình khởi tạo datadir trống.

Khi volume đã chứa database được khởi tạo, đổi giá trị environment trong Compose không tự động đổi mật khẩu MySQL hiện tại hoặc tạo lại database. Hãy thay đổi tài khoản bằng câu lệnh SQL quản trị phù hợp, sau đó cập nhật secret được ứng dụng sử dụng và kiểm tra kết nối.

Không xóa volume chỉ để làm cho biến khởi tạo được chạy lại nếu volume đang chứa dữ liệu cần giữ.

## 6. Health check, readiness và khả năng phục hồi

Một tiến trình đang tồn tại chưa chắc database đã sẵn sàng phục vụ ứng dụng. Nên phân biệt:

- Process/liveness: tiến trình mysqld còn chạy và phản hồi.
- Readiness: server chấp nhận kết nối và thực hiện được truy vấn cần thiết.
- Application health: ứng dụng kết nối bằng tài khoản riêng, có quyền và truy cập được schema cần thiết.

### 6.1. Kiểm tra liveness

Có thể dùng:

```bash
mysqladmin ping --silent
```

Hoặc trong container:

```bash
docker compose exec db mysqladmin ping -h 127.0.0.1 --silent
```

Liveness hữu ích để nhận biết server không phản hồi. Nó không chứng minh rằng migration đã chạy, tài khoản ứng dụng có quyền hoặc mọi dependency đã sẵn sàng.

### 6.2. Kiểm tra readiness bằng SQL

Dùng kết nối với cấu hình và tài khoản phù hợp:

```sql
SELECT 1;
SELECT CURRENT_TIMESTAMP;
SELECT DATABASE();
```

Ứng dụng nên thử kết nối lại với backoff có giới hạn khi database vừa khởi động hoặc đang failover. Tránh retry liên tục với tần suất cao vì có thể làm quá tải server trong lúc recovery.

### 6.3. Restart policy không thay thế giám sát

Docker restart policy có thể tự khởi động lại container sau khi tiến trình thoát hoặc Docker daemon khởi động lại. Nó không giải quyết được:

- Lỗi cấu hình khiến mysqld khởi động thất bại liên tục.
- Datadir bị hỏng hoặc thiếu quyền.
- Disk đầy.
- Secret sai.
- Server chạy nhưng không xử lý được truy vấn.
- Ứng dụng không reconnect.

Cần giám sát restart loop, health status, error log, disk usage và kết nối thực tế. Không cấu hình restart vô hạn mà không có cảnh báo và runbook.

## 7. Log và chẩn đoán khi service không khởi động

Log là nguồn thông tin đầu tiên khi MySQL không start, crash hoặc restart liên tục.

### 7.1. Linux systemd và journald

Xem trạng thái:

```bash
systemctl status mysql --no-pager
```

Đọc log gần đây:

```bash
journalctl -u mysql -n 200 --no-pager
journalctl -u mysql -f
```

Nếu service tên mysqld, thay tên unit tương ứng. Một số package ghi error log vào file riêng thay vì toàn bộ nội dung nằm trong journald.

### 7.2. Container logs

```bash
docker compose logs --tail=200 db
docker compose logs -f db
docker inspect <container_name>
```

Kiểm tra exit code, restart count, health status, mount và network khi container liên tục thoát.

### 7.3. MySQL error log

Có thể kiểm tra vị trí error log:

```sql
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'pid_file';
SHOW VARIABLES LIKE 'socket';
```

Nếu mysqld không khởi động được, không thể chạy SHOW VARIABLES; khi đó đọc error log theo đường dẫn được cấu hình hoặc log do service manager/container thu thập.

Không chia sẻ log nguyên bản ra ngoài khi chưa kiểm tra thông tin nhạy cảm như hostname nội bộ, username, đường dẫn, query chứa dữ liệu cá nhân hoặc thông tin kết nối.

## 8. Quyền, secret và network boundary

Quản lý service tốt phải giới hạn quyền của tiến trình và đường truy cập database.

### 8.1. Tài khoản chạy service

Trên Linux, package thường tạo tài khoản hệ thống riêng như mysql. mysqld không nên chạy bằng root trong vận hành thông thường. Tài khoản service cần quyền tối thiểu trên:

- Datadir.
- Error log và các file log được cấu hình.
- Unix socket, PID file và runtime directory.
- TLS certificate/key nếu MySQL dùng TLS.
- File cấu hình cần đọc.

Không cấp quyền ghi toàn bộ filesystem chỉ để giải quyết lỗi permission. Hãy tìm đúng file hoặc thư mục đang bị từ chối.

### 8.2. Quản lý mật khẩu và secret

Tránh đưa mật khẩu vào command line:

```bash
mysql -uroot -pMySecretPassword
```

Cách này có thể làm lộ secret trong shell history hoặc process list. Dùng prompt -p để nhập tương tác, option file có quyền truy cập hạn chế, secret manager hoặc Docker/Kubernetes secret phù hợp với môi trường.

Trong Compose, file secret phải được bảo vệ trên host và loại khỏi source control. Chỉ cấp secret cần thiết cho service tương ứng. Không mount root password vào ứng dụng nếu ứng dụng chỉ cần tài khoản database giới hạn quyền.

### 8.3. Giới hạn network

- Chỉ bind port ra interface cần thiết.
- Trong môi trường container, ưu tiên private network giữa app và database.
- Không publish 3306 ra Internet.
- Dùng firewall/security group giới hạn nguồn truy cập.
- Bật TLS khi kết nối qua network không tin cậy.
- Dùng tài khoản riêng theo ứng dụng và host pattern phù hợp.

Nếu MySQL chỉ phục vụ ứng dụng cùng host, cân nhắc Unix socket hoặc bind vào loopback. Nếu app ở container khác, dùng tên service trên network nội bộ thay vì hard-code IP container.

## 9. Backup, restore và persistent storage

Vòng đời service/container phải gắn với kế hoạch bảo vệ dữ liệu.

### 9.1. Datadir không nằm trong vòng đời container

Với container, gắn persistent volume vào datadir:

```yaml
volumes:
  - mysql_data:/var/lib/mysql
```

Không lưu database duy nhất trong writable layer của container. Không mount nhầm một thư mục host rỗng vào datadir đang có dữ liệu vì có thể làm mysqld khởi động với thư mục khác hoặc gặp lỗi quyền/khởi tạo.

Với service cài trực tiếp trên host, xác định rõ datadir và bảo đảm backup bao phủ dữ liệu, log cần thiết, cấu hình và key material theo chính sách.

### 9.2. Logical backup

Có thể dùng mysqldump để xuất dữ liệu logic:

```bash
mysqldump --single-transaction --routines --triggers --events appdb > appdb.sql
```

--single-transaction tạo snapshot nhất quán cho bảng transactional như InnoDB trong điều kiện phù hợp. Nếu có bảng không transactional hoặc thao tác DDL đồng thời, cần kế hoạch khóa/backup riêng. Cần đánh giá kích thước, thời gian, charset, quyền và nhu cầu backup toàn instance.

Không ghi password trực tiếp trong command line. Dùng client option file hoặc secret mechanism.

### 9.3. Physical backup và volume snapshot

Physical backup hoặc snapshot volume cần phối hợp với trạng thái MySQL và công cụ backup hỗ trợ. Không sao chép thô datadir đang hoạt động như thể đó là một bản backup nhất quán. Có thể dùng công cụ physical backup phù hợp, snapshot theo quy trình có kiểm soát hoặc shutdown sạch trước khi copy trong trường hợp phù hợp.

Backup chỉ có giá trị khi đã thử restore. Định kỳ diễn tập phục hồi vào môi trường riêng, xác minh dữ liệu, quyền, cấu hình và thời gian khôi phục.

### 9.4. Stop/restart không phải backup

Shutdown sạch giúp InnoDB ghi trạng thái cần thiết và đóng file đúng cách. Tuy nhiên, nó không tạo bản sao lưu độc lập. Một ổ đĩa hỏng hoặc thao tác xóa volume vẫn có thể làm mất dữ liệu.

Cần có backup ngoài volume/datadir, retention, mã hóa, quyền truy cập hạn chế và kiểm tra khả năng restore.

## 10. Nâng cấp MySQL service hoặc container

Nâng cấp server có thể thay đổi data dictionary, định dạng dữ liệu, hành vi optimizer hoặc yêu cầu cấu hình. Không xem việc đổi tag image hoặc thay binary là một thao tác restart thông thường.

Quy trình tổng quát:

1. Xác định phiên bản hiện tại, phiên bản đích và đường nâng cấp được hỗ trợ.
2. Đọc release notes và upgrade notes cho các phiên bản liên quan.
3. Kiểm tra plugin, component, replication, backup tool và driver ứng dụng.
4. Kiểm tra cấu hình không dùng option đã bị loại bỏ hoặc đổi nghĩa.
5. Tạo backup và xác minh có thể restore.
6. Thử nâng cấp trên bản sao dữ liệu trong staging.
7. Xác định cửa sổ bảo trì hoặc chiến lược chuyển đổi/failover.
8. Pin image/package version và thực hiện upgrade.
9. Theo dõi error log, trạng thái service và kết quả kiểm tra SQL.
10. Chạy smoke test và workload kiểm thử.
11. Theo dõi latency, replication lag, error rate và tài nguyên.
12. Thực hiện rollback theo kế hoạch đã kiểm chứng nếu điều kiện không đạt.

Không hạ phiên bản binary rồi mở trực tiếp datadir đã được nâng cấp nếu quy trình MySQL không hỗ trợ. Rollback thường cần khôi phục backup hoặc chuyển về instance cũ có dữ liệu tương thích, thay vì chỉ đổi image tag.

### 10.1. Cập nhật container image

Có thể kéo image đã pin và recreate service:

```bash
docker compose pull db
docker compose up -d --no-deps db
docker compose ps
docker compose logs --tail=200 db
```

Lệnh mẫu không tự tạo quy trình backup, kiểm tra tương thích hoặc rollback. Trước khi chạy trên production, phải hoàn tất các bước nâng cấp và xác nhận volume được giữ nguyên.

### 10.2. Cập nhật package trên host

Với MySQL cài bằng package manager, dùng quy trình nâng cấp được hỗ trợ cho hệ điều hành và repository. Không thay binary thủ công trong khi service đang chạy. Sau khi package update, kiểm tra service unit, file cấu hình, error log, version và trạng thái database.

## 11. Quy trình triển khai theo môi trường

| Môi trường | Cấu hình và vòng đời | Kiểm soát cần có |
|---|---|---|
| Local development | Docker Compose hoặc package; dữ liệu có thể tái tạo | Volume riêng, secret thử nghiệm, port loopback |
| CI/test | Container tạm, khởi tạo schema/fixture | Pin version, health check, cleanup rõ ràng |
| Staging | Gần production về version, config và topology | Migration rehearsal, backup/restore test, smoke test |
| Production | systemd hoặc orchestrator, datadir bền vững | Change window, monitoring, backup, access control, rollback |

Cấu hình giữa các môi trường nên khác nhau ở những giá trị có chủ đích như tài nguyên, endpoint, secret, TLS và log retention. Tránh để local/staging dùng một phiên bản MySQL khác xa production vì hành vi SQL, optimizer hoặc plugin có thể khác.

Không đưa dữ liệu production vào môi trường phát triển nếu chưa có quy trình masking và kiểm soát truy cập.

## 12. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| systemd báo failed | Cấu hình sai, quyền datadir, port bị chiếm, disk đầy | status, journalctl, error log, filesystem |
| Container restart liên tục | mysqld thoát, secret sai, config lỗi, volume permission | compose logs, inspect, health status, mount |
| Service chạy nhưng app không kết nối | Network, bind-address, firewall, user/host grant, TLS | Kết nối từ đúng network, kiểm tra tài khoản và endpoint |
| MySQL khởi động lâu | InnoDB crash recovery, redo log lớn, storage chậm | Error log, disk I/O, recovery progress |
| Đổi environment nhưng password không đổi | Datadir đã được khởi tạo trước đó | Đổi password bằng SQL và cập nhật secret |
| Mất dữ liệu sau khi recreate | Datadir nằm trong container layer hoặc volume bị xóa | Kiểm tra mount và backup; không chạy down --volumes |
| systemctl reload không có tác dụng | Unit không hỗ trợ reload hoặc biến cần restart | Kiểm tra unit và variable scope |
| Service start được nhưng health check fail | Server chưa ready, check sai host/socket hoặc quyền | Xem log và thử kết nối SQL đúng tài khoản |
| Upgrade xong không start | Option cũ, plugin không tương thích, lỗi data dictionary | Upgrade log, error log, release notes và restore plan |

Khi điều tra, thu thập trạng thái trước khi restart liên tục. Restart loop có thể làm mất dấu thời điểm lỗi đầu tiên và tăng tải trên storage.

## 13. Runbook restart MySQL có kiểm soát

Một quy trình restart trên production nên có các bước rõ ràng:

**Trước khi restart:**

1. Xác nhận instance, service name, môi trường và người chịu trách nhiệm.
2. Xác định lý do restart: cấu hình, bản vá, lỗi hay bảo trì.
3. Kiểm tra replica/failover nếu có; xác định node nào được phép restart.
4. Thông báo ứng dụng hoặc chuyển traffic theo quy trình.
5. Kiểm tra backup gần nhất và trạng thái restore test.
6. Xác nhận disk còn đủ dung lượng và không có recovery/DDL quan trọng.
7. Ghi lại version, uptime, error log và trạng thái kết nối.

**Trong khi restart:**

1. Dừng service bằng systemd/Windows Service hoặc lệnh điều phối container.
2. Chờ shutdown hoàn tất; không kill -9 nếu chưa xử lý tình huống khẩn cấp.
3. Áp dụng thay đổi đã được duyệt.
4. Khởi động lại service/container.
5. Theo dõi error log và trạng thái health.

**Sau khi restart:**

1. Xác nhận process/service active.
2. Xác nhận MySQL chấp nhận kết nối.
3. Chạy SELECT 1 bằng tài khoản ứng dụng.
4. Kiểm tra schema, quyền, TLS và kết nối từ application network.
5. Kiểm tra replication, event scheduler hoặc plugin nếu instance dùng chúng.
6. Chạy smoke test và theo dõi latency/error rate.
7. Ghi nhận kết quả, thời gian gián đoạn và cấu hình thay đổi.

Nếu health/readiness không đạt, dừng rollout và chuyển sang quy trình xử lý sự cố hoặc rollback đã chuẩn bị. Không lặp restart vô hạn với hy vọng lỗi tự biến mất.

## 14. Những lỗi vận hành cần tránh

| Lỗi | Rủi ro | Thực hành phù hợp |
|---|---|---|
| Dùng kill -9 để stop thường xuyên | Bỏ qua shutdown sạch, có thể kéo dài crash recovery | Dùng service manager hoặc mysqladmin shutdown |
| Nhầm enable với start | Service không tự chạy sau reboot hoặc đang chạy ngoài ý muốn | Kiểm tra active và enabled riêng |
| Chạy daemon-reload sau mọi thay đổi my.cnf | Không giải quyết việc mysqld nạp lại cấu hình | Restart khi biến cần startup; daemon-reload chỉ cho unit |
| Giả định systemctl reload luôn hỗ trợ | Cấu hình mới không được áp dụng | Kiểm tra unit và variable scope |
| Chỉ lưu datadir trong container layer | Mất dữ liệu khi xóa container | Gắn persistent volume |
| Chạy docker compose down --volumes như thao tác dọn thường ngày | Xóa volume chứa database | Dùng stop/down không kèm --volumes khi cần giữ dữ liệu |
| Đổi MYSQL_ROOT_PASSWORD trong Compose để rotate password | Environment init không đổi tài khoản đã tạo | Đổi password trong MySQL rồi cập nhật secret |
| Đưa mật khẩu vào command line hoặc Git | Lộ credential | Secret manager, option file có ACL hoặc Docker secret |
| Publish 3306 ra mọi interface | Tăng bề mặt tấn công | Private network, loopback, firewall và TLS |
| Dùng tag latest trong production | Upgrade ngoài kế hoạch | Pin version/digest và kiểm thử trước |
| Copy datadir đang chạy để backup | Bản sao có thể không nhất quán | Công cụ backup phù hợp hoặc shutdown sạch |
| Rollback chỉ bằng cách đổi image tag | Binary cũ có thể không đọc datadir mới | Restore backup hoặc quy trình downgrade được hỗ trợ |

## 15. Checklist vận hành

**Service và cấu hình:**

- Xác nhận đúng service name hoặc Compose project/service.
- Phân biệt trạng thái active và enabled/restart policy.
- Xác định chính xác option files và include directories.
- Ghi nhận nguồn cấu hình: file, SET GLOBAL hay SET PERSIST.
- Kiểm tra biến dynamic/startup-only trước khi restart.
- Dùng daemon-reload khi thay unit, không nhầm với reload MySQL.
- Chạy service bằng tài khoản ít quyền.

**Container và dữ liệu:**

- Pin image version đã kiểm thử.
- Mount persistent volume vào datadir.
- Không xóa volume trong quy trình restart.
- Hiểu rõ biến khởi tạo chỉ áp dụng với datadir mới.
- Giới hạn port publish và dùng private network.
- Bảo vệ secret file và không commit secret.

**Health, log và recovery:**

- Có liveness và readiness check phù hợp.
- Theo dõi error log, journald hoặc container logs.
- Có cảnh báo restart loop, disk full và health failure.
- Có backup ngoài datadir/volume.
- Đã thử restore và đo thời gian phục hồi.
- Có runbook restart, upgrade và rollback.

**Triển khai:**

- Local, CI, staging và production dùng version tương thích.
- Thử thay đổi cấu hình và nâng cấp trên staging.
- Có change window và người chịu trách nhiệm.
- Kiểm tra ứng dụng sau restart/upgrade.
- Ghi nhận thay đổi và kết quả vận hành.

## 16. Ghi nhớ

- Linux package thường quản lý MySQL bằng systemd service; tên unit có thể là mysql hoặc mysqld.
- Windows có thể chạy MySQL dưới dạng Windows Service với service name do installer đặt.
- Phân biệt trạng thái active với enablement; enable không đồng nghĩa start.
- Dùng service manager hoặc mysqladmin shutdown để dừng có kiểm soát; tránh kill -9 trong vận hành thường ngày.
- daemon-reload nạp lại unit definitions, không làm mysqld đọc lại my.cnf.
- systemctl reload chỉ có tác dụng khi unit hỗ trợ và không thay thế restart cho biến startup-only.
- MySQL có thể nhận cấu hình từ option files, persisted variables và tham số khởi động; cần quản lý nguồn cấu hình nhất quán.
- Container có vòng đời ngắn; datadir phải nằm trên persistent volume.
- docker compose down thông thường giữ named volumes; docker compose down --volumes có thể xóa dữ liệu.
- Biến khởi tạo của MySQL container không tự cập nhật tài khoản trong datadir đã khởi tạo.
- Health check cần phân biệt process liveness và SQL readiness.
- Secret, service account, port và network phải được giới hạn theo nguyên tắc least privilege.
- Backup phải độc lập với datadir và cần thử restore.
- Upgrade MySQL phải theo đường nâng cấp được hỗ trợ, có backup, staging, smoke test và rollback plan.

Vận hành MySQL ổn định đòi hỏi quản lý nhất quán cả tiến trình lẫn dữ liệu. Service manager hoặc container orchestrator chỉ quản lý vòng đời tiến trình; persistent storage, cấu hình, secret, health check, backup và quy trình nâng cấp mới quyết định khả năng phục hồi của database trong từng môi trường.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Starting and Stopping MySQL: https://dev.mysql.com/doc/refman/8.4/en/starting-stopping.html
- MySQL 8.4 Reference Manual — Using Systemd: https://dev.mysql.com/doc/refman/8.4/en/using-systemd.html
- MySQL 8.4 Reference Manual — Windows Service: https://dev.mysql.com/doc/refman/8.4/en/windows-start-service.html
- MySQL 8.4 Reference Manual — Using Option Files: https://dev.mysql.com/doc/refman/8.4/en/option-files.html
- MySQL 8.4 Reference Manual — Persisted System Variables: https://dev.mysql.com/doc/refman/8.4/en/persisted-system-variables.html
- MySQL 8.4 Reference Manual — mysqldump: https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html
- Docker Docs — Start containers automatically: https://docs.docker.com/engine/containers/start-containers-automatically/
- Docker Compose Docs — Services: https://docs.docker.com/reference/compose-file/services/
- Docker Compose Docs — Volumes: https://docs.docker.com/reference/compose-file/volumes/
- Docker Docs — Manage sensitive data with Docker secrets: https://docs.docker.com/compose/how-tos/use-secrets/
- Docker Hub — Official MySQL image: https://hub.docker.com/_/mysql

