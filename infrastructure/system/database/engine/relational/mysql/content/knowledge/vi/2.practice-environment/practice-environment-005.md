# Lưu dữ liệu bền vững bằng volume và tái tạo môi trường

Khi chạy MySQL trong Docker, dữ liệu nằm trong thư mục dữ liệu của MySQL bên trong container. Nếu chỉ lưu dữ liệu ở lớp ghi của container, việc xóa và tạo lại container có thể làm mất toàn bộ database. Để dữ liệu tồn tại qua các lần khởi động, cập nhật hoặc tái tạo container, cần gắn một volume vào thư mục dữ liệu của MySQL.

Bài thực hành này dựng một MySQL Server bằng Docker Compose, lưu dữ liệu trong named volume, tạo một bản ghi kiểm chứng, sau đó tái tạo container và xác nhận dữ liệu vẫn còn. Bài cũng phân biệt volume với backup để tránh nhầm lẫn giữa lưu trữ bền vững và khả năng phục hồi dữ liệu.

## 1. Mục tiêu và điều kiện chuẩn bị

Sau bài này, bạn có thể:

- Giải thích vì sao dữ liệu trong lớp ghi của container có thể mất khi container bị thay thế.
- Khai báo named volume và gắn volume vào `/var/lib/mysql`.
- Khởi động, kiểm tra trạng thái và kết nối đến MySQL bằng Docker Compose.
- Tái tạo container để kiểm chứng dữ liệu vẫn được giữ lại.
- Phân biệt `docker compose down` với `docker compose down -v`.
- Nhận biết vì sao volume không thay thế được backup.

Bạn cần cài Docker Desktop hoặc Docker Engine có hỗ trợ Docker Compose v2, khởi động Docker Engine và có terminal để chạy lệnh `docker`. Kiểm tra công cụ:

```bash
docker --version
docker compose version
```

Tạo một thư mục làm việc riêng, ví dụ `mysql-volume-lab`, rồi đặt các file trong bài thực hành vào thư mục đó.

## 2. Hiểu nơi Docker lưu dữ liệu

Container có một lớp ghi gắn với vòng đời của container. Khi xóa container, lớp ghi đó cũng bị xóa. Vì vậy, dữ liệu database chỉ nằm trong filesystem riêng của container sẽ không phải là dữ liệu bền vững qua việc thay thế container.

Docker volume là vùng lưu trữ được Docker quản lý độc lập với vòng đời container. Khi khai báo volume trong Compose và gắn nó vào `/var/lib/mysql`, MySQL đọc và ghi các file database trong volume. Container có thể bị dừng, xóa hoặc tạo lại; volume vẫn còn miễn là thao tác đó không yêu cầu xóa volume.

```mermaid
flowchart LR
    C["Container MySQL"] -->|"mount tại /var/lib/mysql"| V[("Named volume mysql_data")]
    R["Tạo lại container"] --> C
    V --> D["Các file database vẫn được giữ"]
```

Trong ví dụ này:

- Container cung cấp tiến trình MySQL Server và môi trường chạy.
- `/var/lib/mysql` là thư mục dữ liệu mặc định của image MySQL chính thức.
- `mysql_data` là tên volume được khai báo trong Docker Compose.
- Dữ liệu được lưu ở volume, không phụ thuộc vào lớp ghi riêng của container.

Named volume thường là lựa chọn phù hợp cho dữ liệu database vì Docker quản lý vòng đời và vị trí lưu trữ của nó. Bạn không cần tự chọn một đường dẫn vật lý bên trong Docker Desktop hoặc truy cập trực tiếp các file nội bộ của MySQL.

## 3. Tạo cấu hình MySQL bằng Docker Compose

Trong thư mục `mysql-volume-lab`, tạo ba file: `compose.yaml`, `.env.example` và `.gitignore`.

### 3.1. Tạo file biến môi trường mẫu

Nội dung `.env.example`:

```dotenv
MYSQL_ROOT_PASSWORD=replace-with-a-strong-local-root-password
MYSQL_DATABASE=appdb
MYSQL_USER=appuser
MYSQL_PASSWORD=replace-with-a-strong-local-app-password
```

Sao chép file mẫu thành `.env` để Docker Compose tự đọc các biến khi chạy:

```bash
cp .env.example .env
```

Trên Windows PowerShell, lệnh tương đương là:

```powershell
Copy-Item .env.example .env
```

Mở `.env` và thay hai giá trị mật khẩu mẫu bằng mật khẩu riêng cho môi trường thực hành. Không commit `.env` lên Git vì file này chứa thông tin xác thực. File `.env.example` chỉ chứa tên biến và giá trị minh họa, không chứa mật khẩu thật.

### 3.2. Không đưa thông tin bí mật vào Git

Nội dung `.gitignore`:

```gitignore
.env
backup.sql
*.sql.gz
```

Nếu dự án đã có `.gitignore`, hãy bổ sung các dòng cần thiết vào file hiện tại thay vì ghi đè các quy tắc đang có.

### 3.3. Khai báo service và named volume

Nội dung `compose.yaml`:

```yaml
services:
  db:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD in .env}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-appdb}
      MYSQL_USER: ${MYSQL_USER:-appuser}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}
    ports:
      - "127.0.0.1:3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 20s

volumes:
  mysql_data:
```

Giải thích cấu hình:

- `image: mysql:8.4` chọn image MySQL 8.4 cho môi trường thực hành. Khi triển khai thực tế, cần chọn phiên bản đã được kiểm thử và quản lý kế hoạch nâng cấp.
- `environment` truyền các biến khởi tạo cho image MySQL chính thức. `MYSQL_ROOT_PASSWORD` đặt mật khẩu root; ba biến còn lại tạo database và tài khoản ứng dụng khi khởi tạo lần đầu.
- `ports` chỉ bind cổng MySQL vào loopback `127.0.0.1` của máy host, phù hợp với lab chạy trên máy cá nhân. Nếu cổng `3306` đã được chương trình khác sử dụng, có thể đổi cổng host, ví dụ `127.0.0.1:3307:3306`.
- `mysql_data:/var/lib/mysql` gắn named volume `mysql_data` vào đúng thư mục MySQL lưu dữ liệu.
- `healthcheck` kiểm tra server đã phản hồi hay chưa. Trạng thái `healthy` giúp nhận biết MySQL đã sẵn sàng hơn so với chỉ nhìn thấy container đang chạy.
- `volumes` ở cấp cao nhất khai báo named volume do Compose quản lý. Docker thường thêm tên project làm tiền tố cho tên volume thực tế.

Nếu một ứng dụng khác cũng chạy trong cùng Compose project, ứng dụng đó kết nối tới hostname `db` và cổng `3306`. Cổng `127.0.0.1:3306` ở phần `ports` dành cho công cụ chạy trên máy host; bên trong mạng Compose, `localhost` của ứng dụng là chính container ứng dụng, không phải container MySQL.

## 4. Khởi động và kiểm tra MySQL

Chạy các lệnh từ thư mục chứa `compose.yaml`:

```bash
docker compose up -d
docker compose ps
```

Lệnh đầu tiên tải image nếu máy chưa có, tạo network, tạo named volume nếu cần và khởi động container. Lần khởi tạo database đầu tiên có thể mất thêm thời gian. Kiểm tra `docker compose ps` cho đến khi service `db` có trạng thái `healthy`.

Nếu cần xem quá trình khởi tạo:

```bash
docker compose logs -f db
```

Nhấn `Ctrl+C` để dừng theo dõi log; thao tác này không dừng container.

Kết nối vào database bằng tài khoản ứng dụng:

```bash
docker compose exec db mysql -uappuser -p appdb
```

Khi terminal hỏi mật khẩu, nhập giá trị `MYSQL_PASSWORD` trong file `.env`. Dấu `-p` không kèm mật khẩu để MySQL client hỏi tương tác, tránh đặt mật khẩu trực tiếp trong lịch sử lệnh.

Tại dấu nhắc MySQL, tạo bảng và một bản ghi kiểm chứng:

```sql
CREATE TABLE IF NOT EXISTS volume_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO volume_demo (note)
VALUES ('Du lieu van con sau khi tao lai container');

SELECT id, note, created_at
FROM volume_demo
ORDER BY id;
```

Ghi nhận kết quả truy vấn rồi thoát khỏi MySQL:

```sql
exit;
```

Bạn có thể xem các volume Docker đang quản lý bằng lệnh:

```bash
docker volume ls
```

Volume của Compose thường có tên dạng `<project>_mysql_data`; tiền tố thay đổi theo tên project hoặc cấu hình Compose. Có thể kiểm tra chi tiết một volume bằng `docker volume inspect <ten-volume>` sau khi lấy tên thực tế từ danh sách.

## 5. Tái tạo container và xác minh dữ liệu còn nguyên

Đây là bước quan trọng nhất của bài thực hành. Tái tạo service `db`:

```bash
docker compose up -d --force-recreate db
docker compose ps
```

Chờ service trở lại trạng thái `healthy`, sau đó truy vấn bản ghi đã tạo:

```bash
docker compose exec db mysql -uappuser -p appdb -e "SELECT id, note, created_at FROM volume_demo ORDER BY id;"
```

Nhập lại mật khẩu ứng dụng khi được hỏi. Bản ghi vẫn xuất hiện vì container mới đã gắn lại volume `mysql_data` chứa thư mục dữ liệu cũ. Có thể thực hiện thêm một vòng dừng và khởi động toàn bộ project:

```bash
docker compose down
docker compose up -d
```

Sau khi MySQL healthy, chạy lại câu lệnh `SELECT` để xác nhận dữ liệu vẫn còn. `docker compose down` xóa container và network thuộc project nhưng giữ named volume mặc định.

### Vì sao các biến khởi tạo không chạy lại?

Image MySQL chính thức sử dụng các biến như `MYSQL_DATABASE`, `MYSQL_USER` và `MYSQL_PASSWORD` trong quá trình khởi tạo datadir còn trống. Khi `/var/lib/mysql` đã có database, image giữ nguyên dữ liệu hiện có và không chạy lại toàn bộ quá trình khởi tạo.

Vì vậy, nếu sửa `MYSQL_PASSWORD` trong `.env` rồi chỉ recreate container, mật khẩu của user đã tồn tại trong MySQL không tự đổi theo. Hãy đổi mật khẩu bằng câu lệnh SQL phù hợp, hoặc dùng một volume mới khi thực sự muốn tạo một database lab hoàn toàn mới. Không coi việc sửa `.env` là thao tác migration dữ liệu.

## 6. Hiểu rõ lệnh nào giữ hoặc xóa volume

Các thao tác thường gặp có tác động khác nhau:

| Lệnh | Container / network | Named volume của project |
| --- | --- | --- |
| `docker compose stop` | Dừng container | Giữ lại |
| `docker compose start` | Khởi động container đã dừng | Dùng lại volume cũ |
| `docker compose up -d --force-recreate` | Tạo lại container | Giữ và gắn lại volume cũ |
| `docker compose down` | Xóa container và network của project | Giữ lại theo mặc định |
| `docker compose down -v` | Xóa container và network của project | Xóa các named volume được khai báo trong project và volume liên quan |

**Cẩn thận với `docker compose down -v`:** lệnh này có thể xóa volume chứa database và làm mất dữ liệu lab. Chỉ dùng khi bạn chủ động muốn xóa dữ liệu và đã kiểm tra đúng project/volume. Các lệnh `docker volume rm` và `docker volume prune` cũng có thể xóa dữ liệu volume; hãy xác định chính xác mục tiêu trước khi chạy.

Nếu muốn làm lại lab từ đầu, trước hết hãy xác nhận không còn dữ liệu cần giữ và kiểm tra project hiện tại. Sau đó mới dùng `docker compose down -v`, rồi `docker compose up -d` để Compose tạo volume trống và MySQL khởi tạo database mới từ `.env`.

## 7. Named volume và bind mount khác nhau thế nào?

Docker có hai cách gắn dữ liệu phổ biến:

| Tiêu chí | Named volume | Bind mount |
| --- | --- | --- |
| Ví dụ | `mysql_data:/var/lib/mysql` | `./mysql-data:/var/lib/mysql` |
| Vị trí | Docker quản lý | Đường dẫn cụ thể trên máy host |
| Phù hợp | Dữ liệu database cần vòng đời độc lập với container | Khi cần truy cập một thư mục host theo yêu cầu cụ thể |
| Lưu ý | Cần quản lý vòng đời và backup volume | Dễ gặp vấn đề quyền truy cập, đường dẫn và khác biệt filesystem giữa các hệ điều hành |

Với bài thực hành MySQL này, named volume là lựa chọn mặc định. Bind mount có thể hữu ích trong một số quy trình phát triển, nhưng cần hiểu quyền sở hữu file và hành vi filesystem của hệ điều hành/VM Docker đang sử dụng. Không sửa trực tiếp file dữ liệu InnoDB khi server đang chạy; hãy dùng SQL hoặc công cụ backup phù hợp.

## 8. Volume không thay thế backup

Volume bảo vệ dữ liệu khỏi việc xóa hoặc thay thế riêng container, nhưng bản thân volume vẫn có thể bị xóa, hỏng hoặc mất cùng máy host/ổ đĩa. Volume không tạo ra một bản sao độc lập và không giúp khôi phục dữ liệu bị người dùng xóa nhầm hoặc bị ứng dụng ghi sai.

Với database InnoDB của lab, có thể tạo logical backup bằng `mysqldump`. Ví dụ sau chạy từ Bash hoặc Git Bash tại thư mục project; shell chuyển nội dung dump từ container ra file `backup.sql` trên máy host:

```bash
docker compose exec -T db sh -c 'exec mysqldump --single-transaction --no-tablespaces -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' > backup.sql
```

`--single-transaction` tạo snapshot nhất quán cho các bảng transactional như InnoDB trong điều kiện phù hợp; tránh để các thao tác DDL làm thay đổi cấu trúc bảng trong lúc dump. File backup có dữ liệu nhạy cảm, cần được bảo vệ, giới hạn quyền truy cập và lưu ở nơi độc lập với volume nguồn.

Khi cần phục hồi vào database đích đã được tạo và đang ở trạng thái phù hợp, có thể dùng:

```bash
docker compose exec -T db sh -c 'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < backup.sql
```

Không import mù quáng vào database đang có dữ liệu vì có thể gặp lỗi bảng đã tồn tại hoặc thay đổi dữ liệu hiện hữu. Hãy thử restore trên môi trường riêng, kiểm tra số lượng bản ghi và khả năng đọc dữ liệu sau phục hồi. Một backup chỉ đáng tin khi quy trình restore cũng đã được kiểm tra.

## 9. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Container liên tục `starting` hoặc `unhealthy` | MySQL đang khởi tạo, biến môi trường thiếu hoặc cấu hình sai | Xem `docker compose logs db`, kiểm tra `.env` và chờ lần khởi tạo đầu tiên hoàn tất |
| `Access denied` khi đăng nhập | Sai user/password hoặc `.env` đã đổi nhưng volume đang chứa tài khoản cũ | Xác nhận tài khoản hiện có; đổi mật khẩu bằng SQL hoặc dùng quy trình reset có chủ đích |
| Cổng `3306` đã được sử dụng | Có MySQL khác đang nghe trên host | Đổi cổng host thành `127.0.0.1:3307:3306` và kết nối từ host qua cổng `3307` |
| Dữ liệu biến mất sau khi recreate | Chưa mount volume đúng đường dẫn, volume bị xóa hoặc project đang dùng volume khác | Kiểm tra `compose.yaml`, `docker volume ls` và `docker volume inspect` |
| Thay `MYSQL_DATABASE` nhưng database không đổi | Datadir đã được khởi tạo nên biến init không chạy lại | Thực hiện thay đổi bằng SQL/migration hoặc tạo volume mới nếu muốn reset lab |

Không xóa volume ngay khi gặp lỗi đăng nhập hoặc lỗi khởi động. Trước hết hãy đọc log, xác định volume đang gắn và kiểm tra xem dữ liệu có cần được giữ lại hay không.

## 10. Bài tập tự thực hành

1. Khởi động project và tạo ít nhất ba bản ghi trong `volume_demo`.
2. Dùng `docker compose up -d --force-recreate db`, sau đó kiểm tra lại đủ ba bản ghi.
3. Chạy `docker compose down`, khởi động lại bằng `docker compose up -d` và xác nhận dữ liệu vẫn tồn tại.
4. Chạy `docker volume ls`, xác định tên volume của project và dùng `docker volume inspect` để xem metadata.
5. Tạo `backup.sql`, kiểm tra file có nội dung SQL và thực hành restore trên một database lab riêng.
6. Giải thích điều gì sẽ xảy ra nếu chạy `docker compose down -v`; chỉ thực hiện khi đã chấp nhận xóa toàn bộ dữ liệu lab.

## 11. Ghi nhớ

Để dữ liệu MySQL tồn tại qua vòng đời container, hãy mount một named volume vào `/var/lib/mysql`. Docker Compose giữ named volume khi chạy `down` thông thường hoặc recreate service, nhưng `docker compose down -v` có thể xóa volume và database bên trong. Các biến khởi tạo của image MySQL chỉ áp dụng khi datadir được khởi tạo lần đầu; thay đổi `.env` không tự cập nhật tài khoản hay schema đã tồn tại.

Volume giúp dữ liệu sống độc lập với container. Backup độc lập và kiểm tra restore giúp dữ liệu có thể phục hồi khi volume hoặc máy host gặp sự cố. Một môi trường thực hành tốt cần hiểu cả hai cơ chế, xác minh dữ liệu sau khi tái tạo container và kiểm soát cẩn thận mọi thao tác xóa volume.
