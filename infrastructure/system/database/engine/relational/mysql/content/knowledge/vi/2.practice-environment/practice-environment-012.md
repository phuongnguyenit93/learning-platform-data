# Sao lưu cấu hình và dọn môi trường thực hành đúng phạm vi

Trong quá trình học MySQL, bạn sẽ nhiều lần thay đổi cấu hình, tạo database thử nghiệm, dựng container hoặc máy ảo rồi xóa chúng để bắt đầu lại. Nếu không ghi nhận và sao lưu đúng phần cần giữ, bạn có thể mất dữ liệu, quên cấu hình đã hoạt động, hoặc vô tình xóa nhầm một máy chủ khác trên cùng máy tính.

Bài này hướng dẫn cách nhận diện những thành phần của một môi trường MySQL, sao lưu cấu hình và dữ liệu theo đúng mục đích, thử khôi phục bản sao lưu, rồi dọn môi trường theo phạm vi đã xác định. Các ví dụ tập trung vào MySQL Community Server trên Linux, Docker Compose và máy ảo. Những nguyên tắc này áp dụng cho môi trường thực hành thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền và vận hành cơ sở dữ liệu quan hệ.

Sau bài học, bạn có thể:

- Phân biệt bản sao lưu cấu hình, bản sao lưu dữ liệu và snapshot máy ảo.
- Ghi lại phiên bản, biến cấu hình đang chạy, tài khoản và cách khởi động MySQL.
- Lưu các tệp cấu hình với quyền truy cập phù hợp và biết cách bảo vệ thông tin bí mật.
- Tạo bản sao lưu logic cho database thực hành và kiểm tra khả năng khôi phục.
- Dọn container, máy ảo hoặc gói cài đặt mà không ảnh hưởng nhầm đến môi trường khác.

## 1. Xác định chính xác môi trường cần sao lưu hoặc dọn dẹp

Trước khi thực hiện thao tác, hãy lập một bản ghi nhận diện. Một máy tính có thể đồng thời có MySQL cài trực tiếp, một container MySQL và một VM chạy MySQL. Tên dịch vụ hoặc cổng giống nhau không có nghĩa chúng dùng chung dữ liệu.

Ghi lại tối thiểu các thông tin sau:

| Thành phần | Thông tin cần ghi nhận | Ví dụ |
| --- | --- | --- |
| Máy chủ | Tên môi trường, máy host hoặc VM, địa chỉ kết nối | `mysql-lab-local`, `127.0.0.1` |
| Phiên bản | Phiên bản và bản phân phối máy chủ | MySQL Community Server 8.4 |
| Cách triển khai | Gói hệ điều hành, container hay VM | Docker Compose |
| Dịch vụ/container | Tên service, container hoặc systemd unit | `mysql`, `mysql-lab`, `mysqld` |
| Kết nối | Host, cổng, socket và phạm vi mạng | `127.0.0.1:3307` |
| Dữ liệu | Database cần giữ và vị trí lưu trữ | `labdb`, named volume `mysql_data` |
| Cấu hình | Tệp cấu hình, Compose file, systemd override | `/etc/mysql/`, `compose.yaml` |
| Phụ thuộc | Ứng dụng, script hoặc bài học đang dùng môi trường | ứng dụng demo kết nối `labdb` |

Khi đã đăng nhập vào MySQL, thu thập thông tin máy chủ:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    @@datadir AS data_directory,
    @@socket AS socket_path,
    @@log_error AS error_log;
```

Xem các biến cấu hình quan trọng đang có hiệu lực:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'bind_address',
    'character_set_server',
    'collation_server',
    'default_storage_engine',
    'innodb_buffer_pool_size',
    'log_error',
    'max_connections',
    'port',
    'sql_mode'
);
```

Lưu kết quả vào biên bản môi trường. Đây là giá trị máy chủ đang sử dụng tại thời điểm truy vấn; nó giúp đối chiếu sau khi khôi phục cấu hình. Một số biến có thể được thay đổi động và không nhất thiết phản ánh nội dung tệp cấu hình trên đĩa.

Trên Linux, xác định đúng unit dịch vụ trước khi thao tác:

```bash
systemctl status mysql --no-pager
systemctl status mysqld --no-pager
```

Thông thường Ubuntu/Debian dùng unit `mysql`, còn các bản RHEL tương thích thường dùng `mysqld`. Một trong hai lệnh có thể không tìm thấy unit; đó không phải lý do để dừng hoặc xóa một dịch vụ có tên gần giống. Với Docker, xác định project Compose và service bằng `docker compose ps`; với VM, kiểm tra tên VM trong phần mềm ảo hóa.

## 2. Phân biệt các loại bản sao lưu

Không có một tệp sao lưu duy nhất phù hợp cho mọi mục đích. Hãy chọn loại bản sao lưu theo thứ cần phục hồi:

| Loại bản sao lưu | Nội dung | Dùng khi | Giới hạn |
| --- | --- | --- | --- |
| Cấu hình MySQL | Tệp cấu hình, cấu hình service, Compose file, thông tin phiên bản và biến đang chạy | Dựng lại cách máy chủ được cấu hình | Không chứa các bảng và bản ghi trong database |
| Sao lưu logic | Câu lệnh SQL tạo schema, dữ liệu và các đối tượng được chọn | Chuyển database, phục hồi bài thực hành hoặc kiểm tra dữ liệu | Cần client và máy chủ tương thích để nhập lại; không phải bản sao byte-for-byte của datadir |
| Sao lưu vật lý | Tệp dữ liệu và metadata của MySQL được sao lưu theo quy trình nhất quán | Phục hồi máy chủ hoặc lượng dữ liệu lớn | Phải tuân theo công cụ, phiên bản và quy trình nhất quán dữ liệu |
| Snapshot VM/đĩa | Trạng thái đĩa hoặc toàn bộ máy ảo tại một thời điểm | Quay lại trạng thái lab hoặc di chuyển VM | Không mặc nhiên là bản sao lưu database nhất quán khi MySQL đang ghi |

Với bài thực hành thông thường, hãy sao lưu cấu hình và tạo thêm bản sao lưu logic cho database cần giữ. Snapshot VM có thể hữu ích để quay lại trạng thái máy, nhưng không thay thế bản sao lưu database đã được kiểm tra khôi phục.

## 3. Sao lưu cấu hình MySQL

### 3.1. Xác định các tệp cấu hình

Các vị trí phổ biến gồm:

| Hệ điều hành | Vị trí thường gặp |
| --- | --- |
| Ubuntu/Debian | `/etc/mysql/`, gồm `my.cnf` và các thư mục được include như `conf.d/`, `mysql.conf.d/` |
| RHEL/Rocky/AlmaLinux | `/etc/my.cnf`, `/etc/my.cnf.d/` |
| Cài đặt tùy chỉnh | Đường dẫn do tham số khởi động hoặc cấu hình dịch vụ chỉ định |

Đừng giả định rằng chỉ có một tệp `my.cnf`. Một tệp có thể chứa chỉ thị `!include` hoặc `!includedir` để nạp cấu hình từ vị trí khác. Hãy đọc các chỉ thị này và kiểm tra cấu hình service trước khi sao lưu.

Trên systemd, có thể xem nội dung unit và các phần override:

```bash
systemctl cat mysql
systemctl cat mysqld
```

Chỉ lưu các unit hoặc override thực sự thuộc môi trường đang sao lưu. Đọc kỹ đầu ra trước khi chia sẻ vì một số cấu hình tùy chỉnh có thể chứa đường dẫn hoặc biến môi trường nhạy cảm.

Các lệnh `my_print_defaults mysqld` hoặc `mysqld --print-defaults` có thể giúp xem tùy chọn được đọc từ cấu hình. Đầu ra có thể chứa giá trị nhạy cảm nếu tệp cấu hình có thông tin xác thực; không đăng nguyên đầu ra lên kho mã nguồn, diễn đàn hoặc log công khai.

### 3.2. Tạo bản sao lưu tệp cấu hình

Trên Ubuntu/Debian, nếu `/etc/mysql/` là thư mục cấu hình đang dùng:

```bash
backup_dir="$HOME/mysql-lab-backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

sudo tar --acls --xattrs -czf "$backup_dir/mysql-config-$(date +%F).tar.gz" -C / etc/mysql
sudo chown "$(id -u):$(id -g)" "$backup_dir/mysql-config-$(date +%F).tar.gz"
chmod 600 "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

Trên RHEL/Rocky/AlmaLinux, nếu máy dùng `/etc/my.cnf` và `/etc/my.cnf.d/`:

```bash
backup_dir="$HOME/mysql-lab-backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

sudo tar --acls --xattrs -czf "$backup_dir/mysql-config-$(date +%F).tar.gz" -C / etc/my.cnf etc/my.cnf.d
sudo chown "$(id -u):$(id -g)" "$backup_dir/mysql-config-$(date +%F).tar.gz"
chmod 600 "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

Các lệnh trên là ví dụ cho đường dẫn phổ biến. Trước khi chạy, xác nhận các đường dẫn tồn tại và bổ sung những tệp cấu hình tùy chỉnh, systemd override hoặc chứng thư TLS mà môi trường thực sự sử dụng. Nếu một đường dẫn trong lệnh không tồn tại, hãy điều chỉnh danh sách nguồn theo máy của bạn; không tạo tệp rỗng chỉ để làm lệnh sao lưu chạy qua.

Kiểm tra archive:

```bash
tar -tzf "$backup_dir/mysql-config-$(date +%F).tar.gz"
sha256sum "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

Lưu checksum cùng biên bản sao lưu để phát hiện tệp bị thay đổi hoặc hỏng khi di chuyển. Nếu archive chứa cấu hình có mật khẩu, khóa riêng hoặc thông tin xác thực, hãy mã hóa trước khi chuyển sang nơi lưu trữ khác và chỉ cấp quyền truy cập cho người cần thiết. Quyền `600` bảo vệ tệp trên máy hiện tại nhưng không thay thế mã hóa khi lưu trữ hoặc truyền qua mạng.

### 3.3. Sao lưu cấu hình container

Với Docker Compose, các thành phần cấu hình thường cần giữ là:

- `compose.yaml` hoặc `docker-compose.yml`.
- Tệp cấu hình MySQL được mount vào container.
- Dockerfile hoặc script khởi tạo tùy chỉnh nếu có.
- Phiên bản image hoặc digest đã dùng.
- Thông tin tên project, port mapping và volume.

Tệp `.env` có thể chứa mật khẩu. Không commit tệp này vào Git và không chép nó vào archive không mã hóa. Nếu cần khôi phục, lưu secret trong trình quản lý bí mật hoặc một bản sao lưu được mã hóa và kiểm soát quyền truy cập. Ghi tên biến cần thiết và cách cung cấp chúng trong tài liệu mà không ghi giá trị bí mật.

Để ghi lại trạng thái Compose, có thể dùng `docker compose ps` và `docker image inspect` cho image đang dùng. `docker compose config` hữu ích để kiểm tra cấu hình đã được nội suy, nhưng đầu ra có thể làm lộ giá trị trong `.env`; chỉ xem ở môi trường tin cậy và không lưu hoặc chia sẻ đầu ra chưa được rà soát.

Ví dụ ghi lại image ID và trạng thái service:

```bash
docker compose ps
docker compose images
docker image inspect mysql:8.4 --format '{{.Id}} {{.RepoDigests}}'
```

Hãy thay `mysql:8.4` bằng image thực tế nếu Compose file dùng tên khác. Một tag như `8.4` có thể trỏ tới bản vá mới hơn theo thời gian; lưu digest giúp nhận diện chính xác image đã chạy.

## 4. Sao lưu database thực hành

Sao lưu cấu hình không bảo vệ bảng và bản ghi. Nếu cần giữ kết quả thực hành, hãy tạo bản sao lưu database riêng.

### 4.1. Sao lưu logic bằng mysqldump

Ví dụ sao lưu database InnoDB `labdb`:

```bash
mkdir -p "$HOME/mysql-lab-backups"
chmod 700 "$HOME/mysql-lab-backups"

mysqldump -u root -p \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --databases labdb \
  --result-file="$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
```

Client sẽ yêu cầu nhập mật khẩu. Không ghi mật khẩu trực tiếp sau `-p`, trong URL kết nối hoặc trong script được commit lên Git. `--single-transaction` tạo consistent snapshot logic cho các bảng transactional như InnoDB mà không cần khóa toàn bộ bảng trong suốt quá trình dump. Tránh chạy các thao tác DDL như `ALTER TABLE`, `DROP TABLE` hoặc `RENAME TABLE` trên database trong lúc dump; với bảng không hỗ trợ transaction, cần quy trình khóa hoặc sao lưu phù hợp riêng.

Kiểm tra tệp sau khi dump:

```bash
test -s "$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
sha256sum "$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
```

Một tệp SQL tồn tại chưa chứng minh có thể khôi phục. Bước kiểm tra quan trọng là nhập thử vào một MySQL instance riêng hoặc một database kiểm thử có tên khác, rồi xác minh schema và dữ liệu.

### 4.2. Ghi nhận quyền của tài khoản

Nếu bài thực hành có tạo tài khoản riêng, hãy ghi lại username, host và quyền đã cấp. Ví dụ:

```sql
SHOW GRANTS FOR 'labuser'@'localhost';
```

Lưu đầu ra cùng biên bản cấu hình nếu cần dựng lại quyền. Không sao chép trực tiếp các bảng hệ thống trong schema `mysql` như một cách tùy tiện để chuyển tài khoản giữa các phiên bản. Lệnh `SHOW CREATE USER` có thể hiển thị thông tin xác thực; nếu thực sự cần lưu đầu ra đó, hãy bảo vệ nó như một bí mật. Khi khôi phục, tạo tài khoản với phương thức xác thực và mật khẩu mới phù hợp chính sách, rồi cấp lại quyền tối thiểu cần thiết.

### 4.3. Khi nào cần sao lưu vật lý

Không dùng lệnh `cp` hoặc `tar` để sao chép trực tiếp datadir của một máy chủ đang chạy rồi coi đó là bản sao lưu đầy đủ. MySQL có thể đang thay đổi nhiều tệp dữ liệu và log đồng thời. Bản sao như vậy có thể không nhất quán.

Với bài lab nhỏ, `mysqldump` thường dễ hiểu và dễ kiểm tra. Nếu cần sao lưu vật lý, hãy dùng công cụ được hỗ trợ cho phiên bản và cấu hình cụ thể, chẳng hạn MySQL Enterprise Backup hoặc Percona XtraBackup trong phạm vi tương thích. Một cold backup ở mức tệp yêu cầu dừng máy chủ sạch sẽ trước khi sao chép và phải bảo toàn quyền sở hữu, quyền truy cập cùng các tệp cần thiết. Snapshot lưu trữ cần được tạo theo quy trình đảm bảo tính nhất quán của dữ liệu.

## 5. Thử khôi phục trước khi dọn môi trường

Một bản sao lưu chỉ có giá trị vận hành khi bạn biết cách khôi phục. Hãy thử trên một instance hoặc VM riêng để tránh ghi đè database đang sử dụng.

### 5.1. Kiểm tra và khôi phục cấu hình

Trước hết liệt kê nội dung archive:

```bash
tar -tzf "$HOME/mysql-lab-backups/mysql-config-YYYY-MM-DD.tar.gz"
```

Thay ngày bằng tên tệp thực tế. Đọc danh sách để chắc chắn archive chứa đúng thư mục cấu hình mong muốn. Nếu khôi phục cấu hình cho máy chủ đang hoạt động, hãy lập kế hoạch bảo trì và dừng đúng dịch vụ trước khi thay thế tệp. Không giải nén archive chưa kiểm tra trực tiếp vào `/`.

Với MySQL 8.0 trở lên, có thể kiểm tra cấu hình trước khi khởi động lại bằng:

```bash
sudo mysqld --validate-config
```

Lệnh này kiểm tra cấu hình mà `mysqld` đọc được theo môi trường khởi chạy. Nếu cấu hình dùng đường dẫn hoặc option file tùy chỉnh, hãy bảo đảm lệnh kiểm tra đang đọc đúng tệp. Khi xác thực thành công, khởi động lại đúng unit và xem log:

```bash
sudo systemctl restart mysql
sudo systemctl status mysql --no-pager
sudo journalctl -u mysql -n 100 --no-pager
```

Trên hệ dùng unit `mysqld`, thay tên unit tương ứng. Sau khi máy chủ lên, chạy lại các câu `SELECT VERSION()` và `SHOW GLOBAL VARIABLES` ở phần 1 để so sánh với biên bản trước sao lưu.

### 5.2. Khôi phục bản dump SQL

Trên instance kiểm thử, tạo môi trường đích sạch và nhập bản dump:

```bash
mysql -u root -p < "$HOME/mysql-lab-backups/labdb-YYYY-MM-DD.sql"
```

Vì ví dụ dump dùng `--databases labdb`, tệp chứa câu lệnh tạo/chọn database. Chỉ nhập vào instance đích đã xác định; nếu database cùng tên đã tồn tại, hãy hiểu rõ tác động của các câu lệnh trong dump trước khi chạy.

Sau khi nhập, kiểm tra:

```sql
SHOW DATABASES;
USE labdb;
SHOW TABLES;
SELECT COUNT(*) FROM environment_check;
```

Thay `environment_check` bằng bảng thực tế có trong bản sao lưu. Đối chiếu số bảng, số bản ghi mẫu, view, trigger, routine và event cần thiết. Nếu ứng dụng demo có thể kết nối, hãy chạy một thao tác đọc và ghi thử bằng tài khoản ứng dụng.

### 5.3. Biên bản khôi phục

Ghi lại ngày kiểm tra, phiên bản MySQL nguồn và đích, tên bản sao lưu, checksum, kết quả nhập và các đối tượng đã xác minh. Nếu khôi phục thất bại, ghi thông báo lỗi và xử lý nguyên nhân trước khi dọn môi trường nguồn. Không xóa bản duy nhất đang còn dùng được chỉ vì đã tạo ra một tệp backup.

## 6. Dọn môi trường Docker đúng phạm vi

Docker Compose có thể quản lý nhiều project trên cùng máy. Trước khi dọn, chuyển tới đúng thư mục có Compose file và xác nhận project/service:

```bash
docker compose ps
docker compose config --services
docker compose images
```

Nếu dùng `-p` hoặc `COMPOSE_PROJECT_NAME`, hãy ghi nhận tên project đang sử dụng. Tên volume thường được Compose tạo theo project và tên volume logic; đừng tự đoán tên rồi xóa.

### 6.1. Dừng container nhưng giữ dữ liệu

Để dừng môi trường lab:

```bash
docker compose stop
```

Để xóa container và network do project tạo nhưng giữ named volume:

```bash
docker compose down
```

Đây là lựa chọn phù hợp khi muốn tạo lại container trong khi giữ database. Sau đó có thể chạy `docker compose up -d` để dựng lại service từ cấu hình.

### 6.2. Xóa dữ liệu lab có chủ đích

Named volume chứa datadir MySQL. Trước khi xóa, xác định volume thuộc đúng project và kiểm tra bằng:

```bash
docker volume ls
docker volume inspect ten_volume_da_xac_minh
```

Nếu đã xác nhận bản sao lưu khôi phục được và thực sự muốn xóa dữ liệu của project hiện tại, chạy từ đúng thư mục Compose:

```bash
docker compose down -v
```

Lệnh này xóa named volume được khai báo trong Compose và các anonymous volume gắn với container của project. Dữ liệu trong volume bị xóa và không thể lấy lại bằng cách chạy `up` lần nữa. Volume khai báo external có vòng đời riêng và không bị Compose xóa theo cách này.

Không dùng `docker system prune --all --volumes` để dọn một bài lab cụ thể. Lệnh prune có thể ảnh hưởng image, container, network và volume không thuộc project đang xử lý. Nếu cần xóa một volume riêng, hãy xác minh tên và nội dung bằng `docker volume inspect`, kiểm tra không có container khác sử dụng rồi mới xóa volume chính xác đó.

## 7. Dọn môi trường máy ảo đúng phạm vi

Trước khi xóa VM, xác nhận tên máy ảo, thư mục lưu đĩa ảo, snapshot, thư mục chia sẻ và các dịch vụ khác có đang dùng VM hay không.

Quy trình an toàn:

1. Đăng nhập vào VM và kiểm tra MySQL còn chạy hay không; hoàn tất dump dữ liệu cần giữ.
2. Tắt MySQL sạch sẽ hoặc shutdown hệ điều hành khách theo quy trình bình thường.
3. Nếu cần tái sử dụng, tạo bản export VM hoặc bản sao đĩa ảo và lưu kèm thông tin phiên bản, mạng, RAM, CPU và checksum.
4. Xác nhận bản export có thể được nhận diện hoặc import trên môi trường đích nếu mục tiêu là di chuyển.
5. Xóa đúng VM đã chọn trong phần mềm ảo hóa. Chỉ chọn xóa các đĩa và snapshot thuộc VM đó khi đã xác nhận chúng không còn cần thiết.
6. Kiểm tra lại cấu hình NAT, port forwarding và shared folder. Chỉ gỡ quy tắc dành riêng cho VM này; không xóa mạng ảo đang được VM khác sử dụng.

Snapshot hữu ích để quay lại trạng thái trước đó, nhưng snapshot không phải lúc nào cũng độc lập với đĩa gốc. Nếu muốn giữ VM lâu dài, hãy export hoặc sao lưu toàn bộ chuỗi đĩa/snapshot theo hướng dẫn của nền tảng ảo hóa thay vì chỉ chụp một snapshot rồi xóa máy.

## 8. Gỡ MySQL cài bằng gói hệ điều hành

Gỡ gói MySQL có thể ảnh hưởng đến dịch vụ đang chạy và các ứng dụng dùng chung máy chủ. Chỉ thực hiện trên máy lab mà bạn quản lý và đã xác định đúng gói, unit, datadir và database cần giữ.

Trước khi gỡ, ghi lại danh sách gói liên quan và xác nhận tên dịch vụ:

```bash
# Ubuntu/Debian
dpkg -l | grep -E 'mysql|mariadb'
systemctl status mysql --no-pager

# RHEL/Rocky/AlmaLinux
rpm -qa | grep -Ei 'mysql|mariadb'
systemctl status mysqld --no-pager
```

Sau khi sao lưu và xác minh đúng máy chủ, có thể dừng dịch vụ và yêu cầu trình quản lý gói gỡ gói máy chủ cụ thể. Ví dụ:

```bash
# Ubuntu/Debian: xem lại danh sách gói sẽ bị gỡ trước khi xác nhận
sudo apt remove mysql-server

# RHEL/Rocky/AlmaLinux: thay bằng đúng tên gói đã kiểm tra
sudo dnf remove mysql-community-server
```

Tên gói có thể khác theo kho và phiên bản. Đọc kỹ danh sách thay đổi mà trình quản lý gói hiển thị; hủy nếu thao tác định gỡ các thành phần không thuộc môi trường lab. Gỡ package thường không đồng nghĩa với xóa toàn bộ cấu hình và dữ liệu.

Chỉ dùng thao tác purge hoặc xóa dữ liệu khi mục tiêu là loại bỏ hoàn toàn môi trường lab và đã xác nhận bản sao lưu. Cấu hình thường nằm dưới `/etc/mysql/` hoặc `/etc/my.cnf*`; dữ liệu thường nằm dưới datadir mà `@@datadir` trả về, phổ biến là `/var/lib/mysql`. Log có thể nằm ở vị trí khác. Không chạy `rm -rf` với đường dẫn suy đoán hoặc wildcard để dọn MySQL. Xác minh từng đường dẫn, chủ sở hữu và nội dung trước khi xóa; nếu còn nghi ngờ, giữ lại để kiểm tra sau.

## 9. Checklist trước khi xác nhận đã dọn xong

Đánh dấu từng mục sau khi đã kiểm tra:

- [ ] Đã xác định đúng máy chủ, project Compose hoặc VM cần xử lý.
- [ ] Đã ghi lại phiên bản MySQL, cách triển khai, cổng, datadir và cấu hình quan trọng.
- [ ] Đã sao lưu các tệp cấu hình và bảo vệ archive có thông tin bí mật.
- [ ] Đã sao lưu database cần giữ bằng phương thức phù hợp.
- [ ] Đã kiểm tra checksum và thử khôi phục bản sao lưu trên môi trường đích.
- [ ] Đã xác định volume, đĩa ảo, snapshot, package và thư mục dữ liệu thuộc đúng môi trường.
- [ ] Đã dừng hoặc xóa đúng tài nguyên được chọn.
- [ ] Đã kiểm tra các môi trường MySQL khác vẫn hoạt động và không bị ảnh hưởng.
- [ ] Đã ghi lại những gì được giữ, những gì đã xóa và vị trí bản sao lưu.

## 10. Bài tập thực hành

1. Dựng một môi trường MySQL lab và ghi lại `VERSION()`, `@@port`, `@@datadir` cùng các biến cấu hình quan trọng.
2. Tìm tệp cấu hình MySQL và các tệp include. Tạo archive cấu hình, đặt quyền truy cập hạn chế và tạo checksum.
3. Tạo database `labdb` với ít nhất một bảng InnoDB, thêm dữ liệu mẫu và sao lưu bằng `mysqldump`.
4. Dựng một instance MySQL kiểm thử khác, khôi phục bản dump vào đó và xác minh bảng, dữ liệu cùng quyền của tài khoản thực hành.
5. Nếu dùng Docker Compose, chạy `docker compose down` rồi `up -d`; kiểm tra dữ liệu còn nguyên nhờ volume. Sau đó chỉ ra volume nào sẽ bị xóa nếu chạy `down -v`.
6. Tạo một bản ghi nhận diện VM hoặc package installation. Lập danh sách tài nguyên sẽ được giữ và tài nguyên sẽ được dọn; giải thích cách xác minh không ảnh hưởng đến MySQL khác trên cùng máy.
7. Sau khi hoàn tất, viết một biên bản ngắn gồm phiên bản, ngày sao lưu, checksum, kết quả restore và phạm vi cleanup.

## 11. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể chỉ ra chính xác môi trường MySQL nào đang được quản lý, sao lưu được cấu hình và dữ liệu theo hai quy trình riêng, chứng minh bản sao lưu có thể khôi phục, và dọn đúng container, VM hoặc gói cài đặt theo phạm vi đã chọn. Bạn cũng cần giải thích được vì sao xóa container không nhất thiết xóa volume, vì sao snapshot không luôn thay thế backup database, và vì sao phải xác minh tài nguyên trước khi xóa.
