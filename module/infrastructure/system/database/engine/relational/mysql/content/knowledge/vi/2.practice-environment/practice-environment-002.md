# Cài đặt bằng gói hệ điều hành, máy ảo hoặc container

Để học MySQL, trước hết cần có một máy chủ cơ sở dữ liệu mà bạn có thể khởi động, dừng, cấu hình và tạo lại khi cần. Có ba cách dựng môi trường phổ biến: cài MySQL trực tiếp bằng trình quản lý gói của hệ điều hành, cài trong một máy ảo, hoặc chạy bằng container. Mỗi cách phù hợp với một mục đích thực hành khác nhau.

Bài này dùng MySQL Community Server 8.4 làm phiên bản ví dụ. Hãy thống nhất phiên bản với ứng dụng hoặc nội dung khóa học đang sử dụng; khi cần tái lập môi trường, hãy ghim phiên bản cụ thể thay vì dùng một thẻ ảnh có thể thay đổi như `latest`.

Sau bài học, bạn có thể:

- Chọn cách triển khai phù hợp với máy tính và mục tiêu thực hành.
- Cài, khởi động và kiểm tra MySQL trên Linux.
- Tạo một máy ảo để cô lập máy chủ cơ sở dữ liệu.
- Chạy MySQL bằng Docker Compose với dữ liệu được lưu bền vững.
- Kết nối vào máy chủ, kiểm tra phiên bản và xử lý một số lỗi khởi động thường gặp.

## 1. Chọn cách triển khai

| Cách triển khai | Khi nên dùng | Điểm cần cân nhắc |
| --- | --- | --- |
| Gói hệ điều hành | Muốn học dịch vụ hệ thống, `systemd`, tệp cấu hình và cách vận hành máy chủ Linux | MySQL gắn với vòng đời của hệ điều hành; phiên bản trong kho mặc định có thể khác phiên bản mong muốn |
| Máy ảo (VM) | Muốn có một máy Linux riêng, thử cấu hình mạng, tường lửa, nâng cấp hoặc mô phỏng máy chủ | Tốn RAM, CPU và dung lượng đĩa hơn; cần quản lý cả hệ điều hành khách |
| Container | Muốn dựng nhanh, tạo lại môi trường dễ dàng và giữ cấu hình trong mã nguồn | Cần hiểu image, port mapping, volume và vòng đời container; container không tự thay thế quy trình sao lưu |

Nếu mục tiêu trước mắt chỉ là luyện SQL trên máy cá nhân, container thường là lựa chọn gọn. Nếu muốn hiểu cách MySQL chạy như một dịch vụ Linux, hãy cài bằng gói hệ điều hành. Nếu cần thử nghiệm thay đổi có thể ảnh hưởng cả hệ điều hành hoặc mạng, hãy dùng máy ảo để giới hạn phạm vi tác động.

Các cách triển khai này đều tạo ra một máy chủ MySQL. Những kiến thức tiếp theo như thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index, transaction, phân quyền và sao lưu đều có thể thực hành trên cùng một cơ sở dữ liệu mẫu.

## 2. Chuẩn bị trước khi cài đặt

Trước khi chọn cách cài, hãy kiểm tra các điều kiện sau:

1. **Phiên bản và nền tảng:** xác định phiên bản MySQL cần học, hệ điều hành và kiến trúc CPU (x86-64 hay ARM). Kiểm tra ma trận nền tảng được hỗ trợ của bản MySQL dự định cài.
2. **Tài nguyên:** dành đủ RAM và dung lượng đĩa cho hệ điều hành, binary, log và dữ liệu. Với một VM học tập nhỏ, có thể bắt đầu ở mức 2 vCPU, 4 GB RAM và đĩa 25 GB rồi điều chỉnh theo tải.
3. **Quyền cài đặt:** cài gói hệ thống cần quyền quản trị; tạo VM cần quyền sử dụng phần mềm ảo hóa; chạy container cần Docker Engine hoặc một môi trường tương thích đã hoạt động.
4. **Cổng kết nối:** MySQL thường lắng nghe trên TCP port `3306`. Kiểm tra cổng này có đang được dịch vụ khác sử dụng không. Nếu cần ánh xạ ra máy host, có thể dùng một cổng khác, ví dụ `3307`.
5. **Dữ liệu hiện có:** nếu máy đã có MySQL hoặc MariaDB, xác định dịch vụ, thư mục dữ liệu và bản sao lưu trước khi thay đổi. Không cài đè hoặc xóa thư mục dữ liệu chỉ để xử lý lỗi khởi động.
6. **Phạm vi mạng:** môi trường học trên máy cá nhân nên chỉ cho phép kết nối từ máy local hoặc mạng lab cần thiết. Không mở cổng cơ sở dữ liệu ra Internet.

### Phân biệt MySQL và MariaDB

Một số bản phân phối Linux cung cấp MariaDB trong kho mặc định, dù tên gói hoặc lệnh cài đặt có thể khiến người mới nghĩ rằng đó là Oracle MySQL. Hai hệ quản trị có nguồn gốc liên quan nhưng là các sản phẩm riêng, có khác biệt về phiên bản và tính năng. Nếu bài học yêu cầu MySQL Community Server, hãy kiểm tra nhà cung cấp và phiên bản của gói trước khi cài. Sau khi cài, xác minh bằng câu lệnh SQL ở phần 6 thay vì chỉ dựa vào tên lệnh `mysql`.

## 3. Cài MySQL bằng gói hệ điều hành

Cài trực tiếp phù hợp khi bạn có máy Linux riêng hoặc muốn học cách quản lý dịch vụ bằng công cụ của hệ điều hành. Tên gói, tên dịch vụ và đường dẫn cấu hình có thể khác nhau giữa các bản phân phối.

### 3.1. Ubuntu hoặc Debian

Trước hết cập nhật danh sách gói và xem gói `mysql-server` sẽ được lấy từ đâu:

```bash
sudo apt update
apt-cache policy mysql-server
```

Đọc phần `Candidate` và thông tin kho gói. Trên một số bản Debian hoặc cấu hình kho mặc định, gói máy chủ mặc định có thể là MariaDB hoặc không cung cấp Oracle MySQL theo phiên bản bạn cần. Nếu yêu cầu đúng MySQL Community Server, hãy cấu hình kho APT chính thức của MySQL theo hướng dẫn dành cho bản phân phối đang dùng, sau đó kiểm tra lại ứng viên gói.

Khi đã xác nhận nguồn gói cung cấp đúng MySQL cần dùng, cài đặt và khởi động dịch vụ:

```bash
sudo apt install mysql-server
sudo systemctl enable --now mysql
sudo systemctl status mysql --no-pager
```

`enable` cấu hình dịch vụ tự khởi động cùng hệ điều hành; `--now` khởi động ngay trong lần chạy này. Nếu lệnh `status` hiển thị `active (running)`, tiến trình dịch vụ đã chạy. Trạng thái này chưa chứng minh rằng tài khoản, quyền truy cập hoặc kết nối từ máy khác đã được cấu hình đúng.

Trên một số cài đặt Ubuntu, tài khoản `root` của MySQL dùng cơ chế xác thực qua socket hệ thống. Khi đó có thể mở client bằng:

```bash
sudo mysql
```

Nếu tài khoản `root` được cấu hình mật khẩu, dùng `mysql -u root -p` và nhập mật khẩu tại dấu nhắc. Không đặt mật khẩu trực tiếp trong tham số dòng lệnh vì lệnh có thể bị lưu trong lịch sử shell hoặc lộ qua danh sách tiến trình.

### 3.2. RHEL, Rocky Linux hoặc AlmaLinux

Trên các hệ RHEL tương thích, nếu đã cấu hình kho MySQL Community chính thức, cài gói máy chủ và bật dịch vụ như sau:

```bash
sudo dnf install mysql-community-server
sudo systemctl enable --now mysqld
sudo systemctl status mysqld --no-pager
```

Tên dịch vụ thường là `mysqld` trên nhóm bản phân phối này. Nếu kho MySQL Community chưa được cấu hình, hãy làm theo hướng dẫn cài đặt kho chính thức phù hợp với phiên bản hệ điều hành trước khi chạy lệnh cài gói. Kiểm tra thông tin gói bằng `dnf info mysql-community-server` để xác nhận nguồn cung cấp.

Ở một số cài đặt RPM mới, MySQL tạo mật khẩu tạm cho `root` và ghi vào log. Có thể tìm dòng liên quan bằng:

```bash
sudo grep 'temporary password' /var/log/mysqld.log
```

Đăng nhập bằng `mysql -u root -p`, dùng mật khẩu tạm vừa tìm được và đổi mật khẩu theo chính sách của môi trường. Đường dẫn log hoặc cách khởi tạo có thể khác theo phiên bản và cấu hình gói; nếu không tìm thấy dòng này, hãy kiểm tra log dịch vụ thay vì đoán mật khẩu.

### 3.3. Hoàn tất cấu hình ban đầu

Trên hệ thống có cung cấp tiện ích này, chạy:

```bash
sudo mysql_secure_installation
```

Đọc từng câu hỏi và chọn cấu hình phù hợp với môi trường học. Các việc thường cần xem xét gồm đặt mật khẩu quản trị mạnh, loại bỏ tài khoản ẩn danh, hạn chế đăng nhập `root` từ xa và xóa cơ sở dữ liệu thử nghiệm mặc định nếu không dùng. Không bật truy cập từ xa cho `root` chỉ để tiện kết nối từ máy khác.

Đường dẫn cấu hình phụ thuộc bản phân phối. Ubuntu/Debian thường có các tệp dưới `/etc/mysql/`, còn các bản RPM thường dùng `/etc/my.cnf` và thư mục cấu hình đi kèm. Trước khi chỉnh sửa, hãy xác định tệp cấu hình thực sự được dịch vụ nạp. Sau khi thay đổi cấu hình máy chủ, kiểm tra cú pháp nếu công cụ hỗ trợ, khởi động lại dịch vụ và xem log nếu dịch vụ không lên.

```bash
# Ubuntu/Debian
sudo systemctl restart mysql

# RHEL và các bản tương thích
sudo systemctl restart mysqld
```

## 4. Cài MySQL trong máy ảo

Máy ảo mô phỏng một máy tính riêng với hệ điều hành, ổ đĩa và giao diện mạng của chính nó. Cách này hữu ích khi muốn thực hành quy trình cài đặt gần với máy chủ thật mà vẫn giữ môi trường thử nghiệm tách khỏi hệ điều hành chính.

### 4.1. Tạo máy ảo

Bạn có thể dùng VirtualBox, Hyper-V, VMware hoặc một nền tảng ảo hóa phù hợp với máy tính. Các bước tổng quát:

1. Tải ISO của một bản Linux còn được hỗ trợ và tương thích với phiên bản MySQL đã chọn.
2. Tạo VM với cấu hình khởi đầu phù hợp, chẳng hạn 2 vCPU, 4 GB RAM và đĩa ảo 25 GB. Tăng tài nguyên nếu dữ liệu hoặc tải thử nghiệm lớn hơn.
3. Chọn mạng NAT cho lần cài đặt đầu tiên để VM có thể truy cập Internet mà không cần xuất hiện trực tiếp trên mạng LAN.
4. Cài hệ điều hành, tạo tài khoản quản trị thông thường và cập nhật các gói hệ thống.
5. Cài MySQL bên trong VM theo quy trình ở phần 3, sau đó kiểm tra dịch vụ và đăng nhập ngay trên VM.

Tạo snapshot sau khi hệ điều hành và MySQL đã hoạt động ổn định. Snapshot thuận tiện để quay lại trạng thái thử nghiệm, nhưng không thay thế bản sao lưu cơ sở dữ liệu: snapshot có thể phụ thuộc vào trạng thái máy ảo và không phải lúc nào cũng là bản sao lưu nhất quán cho dữ liệu đang ghi.

### 4.2. Kết nối từ máy host

Để kết nối từ máy host, bạn cần một đường mạng tới VM. Có hai cách thường dùng:

- **SSH tunnel:** giữ MySQL chỉ lắng nghe trên loopback của VM, sau đó chuyển tiếp cổng qua SSH. Ví dụ, từ máy host chạy:

  ```bash
  ssh -L 3307:127.0.0.1:3306 ten_nguoi_dung@dia_chi_vm
  ```

  Giữ phiên SSH đang mở, rồi kết nối MySQL từ máy host tới `127.0.0.1`, port `3307`. Cách này không cần công khai trực tiếp cổng MySQL trên mạng.

- **Port forwarding của NAT:** cấu hình cổng host `3307` chuyển tới cổng guest `3306` trong phần cài đặt mạng VM. Đảm bảo MySQL lắng nghe trên giao diện phù hợp và tường lửa trong guest cho phép đúng luồng kết nối. Chỉ dùng trong mạng lab đáng tin cậy; không tạo quy tắc chuyển tiếp từ router Internet vào máy chủ cơ sở dữ liệu.

Khi kết nối không thành công, kiểm tra lần lượt địa chỉ IP của VM, quy tắc chuyển tiếp, trạng thái dịch vụ, `bind-address` và tường lửa. Việc mở cổng ở firewall không có tác dụng nếu MySQL chỉ lắng nghe trên một địa chỉ khác.

## 5. Chạy MySQL bằng Docker Compose

Container đóng gói MySQL cùng môi trường chạy cần thiết. Docker Compose cho phép mô tả image, biến môi trường, cổng và volume trong một tệp để có thể dựng lại môi trường bằng cùng một cấu hình.

### 5.1. Chuẩn bị thông tin đăng nhập

Cài Docker Engine và Docker Compose plugin theo hướng dẫn dành cho hệ điều hành. Xác nhận Docker hoạt động:

```bash
docker version
docker compose version
```

Tạo một thư mục riêng cho bài thực hành, rồi tạo tệp `.env` trong thư mục đó:

```dotenv
MYSQL_ROOT_PASSWORD=thay-bang-mat-khau-quan-tri-dai-va-ngau-nhien
MYSQL_PASSWORD=thay-bang-mat-khau-cho-nguoi-dung-hoc
```

Thay giá trị ví dụ bằng chuỗi ngẫu nhiên đủ mạnh. Không commit `.env` lên Git và không dùng lại mật khẩu thật. Có thể thêm `.env` vào `.gitignore` của dự án. Hạn chế quyền đọc tệp này trên hệ thống dùng chung.

### 5.2. Tạo tệp compose.yaml

Tạo `compose.yaml` cùng thư mục với `.env`:

```yaml
services:
  mysql:
    image: mysql:8.4
    container_name: mysql-lab
    environment:
      MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD in .env}"
      MYSQL_DATABASE: labdb
      MYSQL_USER: labuser
      MYSQL_PASSWORD: "${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}"
    ports:
      - "127.0.0.1:3307:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    restart: unless-stopped

volumes:
  mysql_data:
```

Ý nghĩa của cấu hình:

- `image` chọn MySQL 8.4. Khi cần tái lập chính xác hơn giữa các máy hoặc các thời điểm, hãy ghim patch version hoặc image digest đã kiểm chứng.
- `MYSQL_ROOT_PASSWORD` đặt mật khẩu ban đầu cho tài khoản `root`.
- `MYSQL_DATABASE`, `MYSQL_USER` và `MYSQL_PASSWORD` yêu cầu image tạo một database và tài khoản ứng dụng khi khởi tạo thư mục dữ liệu lần đầu.
- `127.0.0.1:3307:3306` ánh xạ cổng `3306` trong container ra cổng `3307` trên loopback của máy host. Máy khác trong mạng không thể kết nối qua ánh xạ loopback này.
- `mysql_data` là named volume giữ dữ liệu ngoài vòng đời của container. Xóa hoặc tạo lại container không làm mất volume này.

Các biến khởi tạo chỉ được áp dụng khi thư mục dữ liệu còn trống. Nếu volume `mysql_data` đã được khởi tạo, thay mật khẩu trong `.env` không tự đổi mật khẩu của tài khoản đang tồn tại; hãy đăng nhập và thay đổi bằng câu lệnh SQL phù hợp.

### 5.3. Khởi động và kết nối

Trong thư mục có `compose.yaml` và `.env`, chạy:

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 mysql
```

Lần khởi động đầu có thể mất thêm thời gian để tạo thư mục dữ liệu và khởi tạo hệ thống. Chờ container ở trạng thái chạy ổn định rồi đăng nhập:

```bash
docker compose exec mysql mysql -u root -p
```

Nhập mật khẩu `MYSQL_ROOT_PASSWORD` tại dấu nhắc. Hoặc từ máy host, nếu đã cài MySQL client:

```bash
mysql -h 127.0.0.1 -P 3307 -u labuser -p labdb
```

Để dừng container nhưng giữ dữ liệu:

```bash
docker compose stop
```

Để xóa container và mạng do Compose tạo nhưng giữ named volume:

```bash
docker compose down
```

Lệnh `docker compose down -v` còn xóa named volume và dữ liệu trong đó. Chỉ chạy khi chủ ý xóa toàn bộ dữ liệu thực hành và đã xác nhận không cần giữ lại. Không dùng lệnh này như bước dọn dẹp mặc định.

## 6. Kiểm tra máy chủ sau khi cài

Khi đã đăng nhập được bằng client MySQL, chạy các câu lệnh sau:

```sql
SELECT VERSION(), @@version_comment, @@port, @@datadir;
SHOW DATABASES;
```

Kết quả giúp xác nhận phiên bản máy chủ, cổng đang lắng nghe, thư mục dữ liệu và các database hiện có. Hãy đối chiếu `VERSION()` và `version_comment` để chắc chắn bạn đang dùng Oracle MySQL theo yêu cầu, thay vì một máy chủ tương thích khác.

Tiếp theo, kiểm tra tài khoản học tập được tạo trong container:

```sql
SELECT CURRENT_USER();
USE labdb;
CREATE TABLE environment_check (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO environment_check (note) VALUES ('MySQL lab is ready');
SELECT id, note, created_at FROM environment_check;
```

Nếu các câu lệnh chạy thành công, bạn đã xác nhận được cả kết nối, quyền tạo bảng, ghi dữ liệu và đọc dữ liệu. Trong môi trường cài bằng gói hệ điều hành hoặc VM, hãy tạo một database và tài khoản riêng cho bài học theo cùng nguyên tắc phân quyền tối thiểu; không dùng `root` cho ứng dụng hoặc bài thực hành hằng ngày.

## 7. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Dịch vụ không khởi động | Cấu hình sai, thư mục dữ liệu không truy cập được, thiếu dung lượng hoặc cổng đã được dùng | Xem `systemctl status` và log bằng `journalctl -u mysql -n 100 --no-pager` hoặc `journalctl -u mysqld -n 100 --no-pager`; sửa nguyên nhân được ghi trong log rồi khởi động lại |
| `Address already in use` hoặc không bind được port | Một tiến trình khác đang chiếm cổng `3306` | Trên Linux, dùng `sudo ss -ltnp | grep ':3306'`; xác định dịch vụ đang giữ cổng trước khi dừng nó hoặc chọn cổng ánh xạ khác |
| `Access denied` | Sai mật khẩu, dùng nhầm tài khoản, hoặc tài khoản không được phép kết nối từ host hiện tại | Kiểm tra username, mật khẩu, host của tài khoản và phương thức xác thực; nhập mật khẩu ở dấu nhắc thay vì đưa vào dòng lệnh |
| `Can't connect` hoặc kết nối bị từ chối | Dịch vụ chưa sẵn sàng, sai host/port, `bind-address`, firewall hoặc port mapping sai | Kiểm tra trạng thái dịch vụ, log, địa chỉ lắng nghe và quy tắc mạng; với Compose, xem `docker compose ps` và `docker compose logs mysql` |
| Container chạy nhưng ứng dụng chưa kết nối được ngay | MySQL vẫn đang khởi tạo dữ liệu | Chờ log báo máy chủ sẵn sàng rồi thử lại; trạng thái container `running` chưa chắc đồng nghĩa MySQL đã sẵn sàng nhận kết nối |
| Đổi `.env` nhưng mật khẩu trong MySQL không đổi | Volume đã có dữ liệu từ lần khởi tạo trước | Đổi mật khẩu bên trong MySQL bằng tài khoản có quyền quản trị; biến môi trường chỉ thiết lập tài khoản trong lần khởi tạo đầu tiên |
| MySQL không mở được thư mục dữ liệu sau khi đổi phiên bản | Dữ liệu được tạo bởi phiên bản khác hoặc quyền truy cập không phù hợp | Kiểm tra phiên bản trước và sau, log và quyền sở hữu thư mục; sao lưu dữ liệu trước khi thử nâng cấp hoặc khôi phục |

Trên Linux, log dịch vụ thường là nơi hữu ích nhất để tìm nguyên nhân:

```bash
# Ubuntu/Debian
sudo journalctl -u mysql -n 100 --no-pager

# RHEL và các bản tương thích
sudo journalctl -u mysqld -n 100 --no-pager
```

Với container:

```bash
docker compose ps
docker compose logs --tail=100 mysql
```

Không xóa thư mục dữ liệu hoặc volume để “thử lại” trước khi xác định dữ liệu đó có cần giữ không. Nếu phải tạo lại môi trường, hãy sao lưu dữ liệu cần thiết, ghi nhận phiên bản MySQL và cấu hình đang dùng, rồi mới thực hiện thao tác xóa.

## 8. Nguyên tắc an toàn cho môi trường học

- Chỉ mở port MySQL cho các máy thực sự cần kết nối. Khi học trên máy cá nhân, ưu tiên loopback hoặc SSH tunnel.
- Dùng mật khẩu riêng cho tài khoản quản trị và tài khoản ứng dụng; cấp đúng quyền trên đúng database.
- Không cho phép `root` đăng nhập từ xa nếu bài học không có yêu cầu quản trị cụ thể.
- Lưu dữ liệu ở volume hoặc đĩa bền vững. Container có thể được tạo lại, nhưng dữ liệu phải có vòng đời và bản sao lưu riêng.
- Trước khi nâng cấp phiên bản hoặc thay đổi cấu hình lưu trữ, sao lưu và kiểm tra khả năng khôi phục.
- Không đưa mật khẩu, tệp `.env` hoặc dữ liệu thật vào Git, ảnh chụp màn hình hay log chia sẻ.

## 9. Bài tập thực hành

1. Dựng một máy chủ MySQL bằng một trong ba cách ở trên. Ghi lại hệ điều hành, phiên bản MySQL, phương thức cài đặt và cổng kết nối.
2. Khởi động lại máy hoặc môi trường chạy. Xác nhận MySQL tự khởi động (với cài đặt gói hệ điều hành) hoặc khởi động lại được bằng Compose/VM.
3. Kết nối bằng client và chạy `SELECT VERSION(), @@port, @@datadir;`. Giải thích từng giá trị.
4. Tạo database `practice_db`, một tài khoản `practice_user` với quyền cần thiết trên database đó, rồi đăng nhập bằng tài khoản mới.
5. Với container, chạy `docker compose down` rồi `docker compose up -d`; xác nhận bảng và dữ liệu vẫn còn. Sau đó giải thích vì sao `docker compose down -v` có kết quả khác.
6. Cố ý cấu hình sai cổng kết nối trong client, đọc thông báo lỗi và tìm đúng nguyên nhân. Khôi phục cổng đúng rồi kết nối lại.

## 10. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tự dựng một máy chủ MySQL, khởi động và dừng nó, đăng nhập bằng client, xác nhận đúng phiên bản, tạo và truy vấn được một bảng, giải thích nơi dữ liệu được lưu, và tìm log khi kết nối hoặc khởi động thất bại. Hãy giữ lại thông tin phiên bản và cách dựng môi trường để các bài thực hành về SQL, index, transaction, phân quyền và sao lưu có thể dùng lại cùng một thiết lập.
