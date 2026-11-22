# Chuẩn bị cơ sở dữ liệu thực hành bằng Docker Compose

Để học và kiểm chứng Liquibase, trước hết cần một database có thể tạo lại nhanh, giữ được dữ liệu giữa các lần khởi động và có cách kiểm tra trạng thái rõ ràng. Docker Compose giúp mô tả database, cổng kết nối, biến môi trường, volume lưu trữ và health check trong một cấu hình có thể chia sẻ cho cả nhóm. Mỗi học viên có thể dựng cùng một môi trường local mà không phải cài trực tiếp hệ quản trị cơ sở dữ liệu lên máy.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, database thực hành là nơi thử các thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và rollback; đồng thời kiểm tra cách Liquibase phối hợp với nhiều môi trường, Spring Boot và CI/CD. Bài này dùng PostgreSQL làm ví dụ cụ thể. Các nguyên tắc về container, volume, network và readiness cũng áp dụng cho hệ quản trị khác, nhưng image, biến khởi tạo, cổng và lệnh kiểm tra phải đổi theo database được chọn.

## 1. Mục tiêu và kiến trúc môi trường thực hành

Môi trường local cần đáp ứng các yêu cầu:

- Khởi tạo database nhất quán bằng cấu hình có thể lưu cùng repository.
- Tách dữ liệu khỏi vòng đời container để có thể dừng hoặc tạo lại container mà không mất dữ liệu.
- Có health check để biết database đã sẵn sàng nhận kết nối.
- Kết nối được từ Liquibase CLI hoặc ứng dụng Spring Boot chạy trên máy host.
- Có thể kết nối từ container khác trong cùng mạng Compose bằng tên service.
- Dễ quan sát log, kiểm tra dữ liệu và chủ động xóa dữ liệu khi muốn bắt đầu lại bài thực hành.

Mô hình cơ bản gồm một service PostgreSQL, một named volume để lưu data directory và một cổng được publish từ máy host:

~~~text
Máy phát triển
  |
  | localhost:5432
  v
Docker Compose
  |
  +-- service: db
        |
        +-- PostgreSQL
        |
        +-- named volume: liquibase_pgdata

Liquibase CLI / Spring Boot chạy trên host
  |
  +-- JDBC: jdbc:postgresql://localhost:5432/liquibase_lab

Ứng dụng chạy trong Compose network
  |
  +-- JDBC: jdbc:postgresql://db:5432/liquibase_lab
~~~

Có hai địa chỉ kết nối cần phân biệt. Chương trình chạy trực tiếp trên máy phát triển dùng localhost và cổng host đã publish. Một container khác trong cùng Compose project dùng tên service db và cổng nội bộ 5432. Bên trong container database, localhost chỉ chính container đó; không dùng localhost để gọi sang service database khác.

## 2. Chuẩn bị Docker và Docker Compose

Cài Docker Desktop trên Windows hoặc Docker Engine cùng Docker Compose plugin trên Linux/macOS. Trên Windows, Docker Desktop thường chạy Linux containers thông qua WSL 2. Sau khi cài đặt, khởi động Docker Engine rồi mở terminal tại thư mục dự án.

Kiểm tra CLI và daemon:

~~~bash
docker --version
docker compose version
docker info
~~~

Hai lệnh đầu xác nhận CLI và Compose plugin có mặt. docker info kiểm tra client có giao tiếp được với Docker Engine hay không. Nếu lệnh báo không kết nối được daemon, hãy khởi động Docker Desktop hoặc dịch vụ Docker trước khi chạy Compose.

Hãy dùng docker compose là Compose plugin hiện nay và kiểm tra cú pháp cấu hình trên máy thực tế bằng docker compose config. Nếu nhóm đang dùng môi trường cũ, cần xác nhận phiên bản hỗ trợ các thuộc tính trong Compose file.

## 3. Tạo cấu hình Compose cho PostgreSQL

Trong thư mục làm việc của bài thực hành, tạo một tệp tên compose.yaml với nội dung:

~~~yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME:-liquibase_lab}
      POSTGRES_USER: ${DB_USER:-liquibase}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    ports:
      - "${DB_PORT:-5432}:5432"
    volumes:
      - liquibase_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\""]
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 10s
    restart: unless-stopped

volumes:
  liquibase_pgdata:
~~~

Cấu hình có các phần quan trọng:

- services.db khai báo service database có tên db. Tên service cũng là tên DNS mà các container cùng network có thể sử dụng.
- image chọn image PostgreSQL. Ví dụ dùng nhánh major 16-alpine để có môi trường ổn định theo major version. Khi dùng trong dự án nhóm, nên chốt patch version hoặc image digest để mọi người tải đúng một image; việc nâng major version cần có kế hoạch nâng cấp dữ liệu riêng.
- POSTGRES_DB, POSTGRES_USER và POSTGRES_PASSWORD là các biến khởi tạo của image PostgreSQL chính thức. Chúng tạo database và user ban đầu khi data directory còn trống.
- ports ánh xạ cổng trên host sang cổng PostgreSQL bên trong container. Mặc định host dùng 5432, còn container vẫn lắng nghe ở 5432.
- volumes gắn named volume vào data directory. Dữ liệu tồn tại sau khi container bị xóa và tạo lại.
- healthcheck gọi pg_isready để kiểm tra PostgreSQL có sẵn sàng nhận kết nối hay chưa. Compose đánh dấu service healthy khi các lần kiểm tra đạt yêu cầu.
- restart giúp container được khởi động lại khi Docker Engine phục hồi. Với bài thực hành, có thể bỏ trường này nếu muốn mọi lần khởi động đều do người học chủ động.

Không cần khai báo trường version ở đầu tệp Compose hiện đại. Compose sử dụng Compose Specification và tự diễn giải cấu trúc phù hợp với phiên bản đang cài.

### 3.1. Khai báo biến môi trường local

Tạo tệp .env cùng thư mục với compose.yaml:

~~~dotenv
DB_NAME=liquibase_lab
DB_USER=liquibase
DB_PASSWORD=replace-with-a-local-only-password
DB_PORT=5432
~~~

Compose tự đọc .env để thay thế các biểu thức biến trong tệp cấu hình. Thay mật khẩu mẫu bằng một giá trị riêng cho máy thực hành. Tệp này chỉ dành cho môi trường local; không đưa mật khẩu thật lên Git, không gửi trong log hoặc ảnh chụp màn hình và không tái sử dụng mật khẩu production.

Thêm .env vào .gitignore:

~~~gitignore
.env
~~~

Nếu muốn chia sẻ cấu trúc cấu hình, nhóm có thể lưu một tệp .env.example chỉ chứa giá trị mẫu, không chứa bí mật. Mỗi thành viên sao chép thành .env rồi điền giá trị local của mình. Không cần tạo tệp .env.example nếu repository đã có quy ước cấu hình khác.

Cú pháp biến bắt buộc trong Compose yêu cầu DB_PASSWORD phải được cung cấp; nếu thiếu, Compose báo lỗi ngay khi đọc cấu hình. Điều này giúp tránh vô tình khởi tạo database với mật khẩu rỗng. Các dạng có giá trị mặc định cho phép chọn giá trị dự phòng khi biến chưa được đặt hoặc rỗng; hãy phân biệt rõ hai trường hợp này khi cấu hình môi trường.

### 3.2. Vì sao phải dùng named volume?

Container là đơn vị chạy có thể thay thế. Nếu lưu database chỉ trong filesystem writable layer của container, việc xóa container sẽ làm mất dữ liệu. Named volume tách data directory khỏi container:

~~~yaml
volumes:
  - liquibase_pgdata:/var/lib/postgresql/data
~~~

liquibase_pgdata được Docker quản lý và Compose gắn vào đường dẫn dữ liệu PostgreSQL. Khi chạy docker compose down, container và network của project được gỡ bỏ, nhưng named volume mặc định vẫn còn. Khi chạy docker compose up lại, container mới dùng volume cũ.

Đặc tính này rất quan trọng khi thực hành Liquibase: lịch sử trong DATABASECHANGELOG và cấu trúc đã migration vẫn còn sau khi container được tạo lại. Nếu volume bị xóa, database trở về trạng thái khởi tạo mới và Liquibase sẽ chạy lại các changeset trên database trống.

Không gắn cùng một data directory PostgreSQL vào nhiều container database đang chạy đồng thời. Named volume không phải cơ chế nhân bản database; chỉ một tiến trình PostgreSQL phù hợp được quản lý data directory đó.

## 4. Kiểm tra cấu hình và khởi động database

Từ thư mục chứa compose.yaml, kiểm tra Compose có đọc được biến và cấu hình không:

~~~bash
docker compose config --quiet
~~~

Nếu không có lỗi, khởi động riêng service database:

~~~bash
docker compose up -d db
~~~

-d chạy container ở chế độ nền. Lệnh đầu tiên có thể tải image nếu máy chưa có. Kiểm tra trạng thái:

~~~bash
docker compose ps
docker compose logs --tail=100 db
~~~

Chờ cột trạng thái hiển thị healthy nếu cấu hình health check đã được áp dụng. Trạng thái running chỉ cho biết container đang chạy; nó không khẳng định database đã hoàn tất khởi tạo hoặc nhận kết nối. Nếu cần theo dõi quá trình khởi động, dùng:

~~~bash
docker compose logs -f db
~~~

Nhấn Ctrl+C để thoát chế độ theo dõi log; thao tác này không dừng container.

Có thể kiểm tra readiness trực tiếp trong container:

~~~bash
docker compose exec db pg_isready -U liquibase -d liquibase_lab
~~~

Và chạy một truy vấn SQL:

~~~bash
docker compose exec db psql -U liquibase -d liquibase_lab -c "SELECT current_database(), current_user, version();"
~~~

Kết quả cần cho biết database hiện tại là liquibase_lab, user là liquibase và phiên bản PostgreSQL đang chạy. Nếu đã cài PostgreSQL client trên host, cũng có thể kết nối từ host bằng psql -h localhost -p 5432 -U liquibase -d liquibase_lab; client sẽ yêu cầu mật khẩu. Nếu không có psql trên host, dùng docker compose exec như ví dụ trên hoặc một công cụ quản trị database có hỗ trợ PostgreSQL.

## 5. Hiểu cổng và địa chỉ kết nối

Thông tin kết nối phụ thuộc nơi tiến trình Liquibase hoặc ứng dụng chạy:

| Nơi chạy client | Host | Port | JDBC URL mẫu |
|---|---|---:|---|
| Máy phát triển (host) | localhost | 5432 | jdbc:postgresql://localhost:5432/liquibase_lab |
| Container cùng Compose network | db | 5432 | jdbc:postgresql://db:5432/liquibase_lab |
| Máy khác trong mạng LAN | Địa chỉ host Docker được phép truy cập | Cổng đã publish | Chỉ mở khi có nhu cầu và đã cấu hình firewall phù hợp |

Ánh xạ 5432:5432 có nghĩa là cổng 5432 trên host chuyển tiếp tới cổng 5432 trong container. Nếu máy đã có PostgreSQL cục bộ chiếm cổng 5432, đổi .env thành:

~~~dotenv
DB_PORT=5433
~~~

Sau đó tạo hoặc khởi động lại service với cấu hình mới. Client chạy trên host phải dùng localhost:5433; client trong Compose network vẫn dùng db:5432, vì cổng nội bộ không đổi.

Không dùng IP container làm địa chỉ kết nối cố định. IP có thể đổi khi Compose tạo lại container; tên service db được Docker DNS phân giải trong network của project và ổn định hơn.

## 6. Kết nối Liquibase với database thực hành

Liquibase cần JDBC URL, driver tương ứng, tên đăng nhập và mật khẩu có quyền phù hợp. Với PostgreSQL, JDBC URL cơ bản là:

~~~text
jdbc:postgresql://localhost:5432/liquibase_lab
~~~

Khi Liquibase chạy trên host, URL dùng localhost và cổng host. Khi Liquibase chạy trong một container được gắn vào cùng Compose network, URL dùng db:5432. Chỉ đổi địa chỉ host theo vị trí chạy client; database name và thông tin xác thực vẫn phải khớp cấu hình đã khởi tạo.

Liquibase tự quản lý các bảng lịch sử như DATABASECHANGELOG và DATABASECHANGELOGLOCK khi chạy trên database phù hợp. Không cần tự tạo hai bảng này bằng SQL trước khi chạy migration. Hãy để changelog quản lý schema ứng dụng; các bảng nội bộ của Liquibase dùng để ghi nhận trạng thái triển khai.

Trước khi áp dụng migration đầu tiên, xác nhận:

1. Database đích là đúng database local dành cho bài thực hành.
2. JDBC URL trỏ đến đúng host và cổng theo vị trí chạy Liquibase.
3. Tên user và mật khẩu khớp với database đã khởi tạo.
4. User có quyền tạo các đối tượng mà changeset yêu cầu.
5. Changelog gốc được chỉ định đúng và các tệp được include có sẵn trong ứng dụng hoặc thư mục làm việc.

Khi dùng Spring Boot với Liquibase, có thể cấu hình các thuộc tính tương ứng trong profile local:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/liquibase_lab
spring.datasource.username=liquibase
spring.datasource.password=${DB_PASSWORD}
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Ứng dụng chạy trên host dùng localhost. Nếu đóng gói ứng dụng thành service trong cùng Compose file, URL phải chuyển thành jdbc:postgresql://db:5432/liquibase_lab. Biến DB_PASSWORD cần được cung cấp cho tiến trình Spring Boot từ môi trường chạy; cú pháp placeholder ở trên là cơ chế cấu hình của Spring, không phải Compose tự động chuyển biến vào một tiến trình host.

Nếu bổ sung ứng dụng vào Compose, khai báo phụ thuộc có điều kiện readiness:

~~~yaml
services:
  app:
    # image hoặc build của ứng dụng
    depends_on:
      db:
        condition: service_healthy
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/liquibase_lab
~~~

depends_on với service_healthy giúp Compose đợi health check của database đạt trước khi khởi động service phụ thuộc. Điều này xử lý thứ tự khởi động cơ bản, nhưng ứng dụng vẫn nên có khả năng retry kết nối khi database khởi động lại hoặc mạng tạm thời gián đoạn.

## 7. Phân biệt khởi tạo container với migration của Liquibase

Image PostgreSQL chính thức hỗ trợ các biến POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD và thư mục script khởi tạo /docker-entrypoint-initdb.d. Các thiết lập và script này chỉ được áp dụng khi PostgreSQL khởi tạo một data directory trống lần đầu.

Điều đó có nghĩa:

- Thay POSTGRES_PASSWORD trong .env sau khi volume đã chứa database không tự đổi mật khẩu user hiện có.
- Đổi POSTGRES_DB không tự tạo database mới trong volume đã khởi tạo.
- Thêm script vào /docker-entrypoint-initdb.d sau lần khởi tạo đầu không khiến script chạy lại.
- Tạo lại container nhưng giữ named volume không đồng nghĩa với tạo database mới.

Đây là điểm dễ gây nhầm lẫn khi thực hành. Nếu muốn đổi mật khẩu hoặc tạo database bổ sung trong volume hiện tại, hãy dùng câu lệnh SQL quản trị phù hợp, chẳng hạn ALTER ROLE hoặc CREATE DATABASE, với quyền cần thiết. Nếu muốn bắt đầu hoàn toàn từ đầu trong môi trường học tập và chấp nhận mất dữ liệu, có thể xóa volume theo hướng dẫn ở phần dọn dẹp.

Các script trong /docker-entrypoint-initdb.d phù hợp để bootstrap môi trường ban đầu, chẳng hạn tạo extension hoặc database mẫu cho lab. Chúng không thay thế changelog. Những thay đổi schema và dữ liệu thuộc vòng đời ứng dụng nên được mô tả bằng changeset để Liquibase theo dõi, kiểm tra checksum và ghi lịch sử trên từng database.

## 8. Chuẩn bị database cho các bài thực hành Liquibase

Một database mới thường bắt đầu với database và user đã được image khởi tạo, chưa có schema nghiệp vụ. Đây là trạng thái thuận tiện để học cách Liquibase tạo bảng, constraint và dữ liệu.

Một trình tự thực hành hợp lý:

1. Khởi động PostgreSQL và xác nhận health check thành công.
2. Kết nối vào liquibase_lab, xác nhận user và database đúng.
3. Chọn schema ứng dụng sẽ sử dụng, ví dụ public cho bài đầu tiên hoặc một schema riêng như app.
4. Cấu hình Liquibase trỏ đến database và changelog gốc.
5. Xem trước thay đổi bằng lệnh hoặc tác vụ preview SQL phù hợp với phiên bản Liquibase đang dùng.
6. Chạy migration trong môi trường local.
7. Kiểm tra cấu trúc và dữ liệu bằng psql hoặc công cụ quản trị.
8. Đọc bảng lịch sử Liquibase để xác nhận changeset được ghi nhận.

Sau migration đầu tiên, có thể truy vấn bảng lịch sử (PostgreSQL chuyển tên không đặt trong dấu ngoặc kép thành chữ thường):

~~~sql
SELECT id, author, filename, dateexecuted, exectype
FROM databasechangelog
ORDER BY orderexecuted;

SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Tên cột có thể thay đổi theo phiên bản Liquibase và cấu hình, vì vậy hãy kiểm tra schema bảng thực tế nếu câu truy vấn không khớp. Bảng lock thường có một bản ghi thể hiện trạng thái khóa. Không chỉnh sửa trực tiếp các bảng lịch sử để ép Liquibase bỏ qua migration; thay đổi thủ công ở đây có thể làm sai lệch trạng thái giữa changelog và database.

Nếu cần một schema riêng, có thể tạo schema bằng một changeset đầu tiên rồi cấu hình Liquibase dùng schema phù hợp. Phân biệt schema mặc định của ứng dụng với schema chứa bảng theo dõi Liquibase nếu nhóm muốn tách metadata khỏi đối tượng nghiệp vụ. Không tạo trước bảng DATABASECHANGELOG bằng tay trừ khi đang thực hiện một quy trình quản trị được tài liệu hóa và kiểm soát riêng.

## 9. Dữ liệu bền vững, sao lưu và reset môi trường

Một named volume giúp dữ liệu tồn tại qua vòng đời container, nhưng không thay thế backup. Với bài thực hành, dữ liệu có thể không quan trọng; với dữ liệu cần giữ, hãy tạo bản sao lưu trước khi thử migration có khả năng xóa hoặc biến đổi dữ liệu.

Có thể xuất database bằng pg_dump từ trong container và chuyển nội dung ra host. Ví dụ dưới đây minh họa lệnh trên shell kiểu Bash:

~~~bash
docker compose exec -T db pg_dump -U liquibase -d liquibase_lab > liquibase_lab_backup.sql
~~~

Lệnh restore phải được thử trên database đích riêng và kiểm tra kết quả sau khi phục hồi. Không coi việc có một tệp dump là bằng chứng backup dùng được; cần kiểm tra kích thước, quyền đọc và khả năng restore.

Các lệnh quản lý vòng đời:

~~~bash
# Dừng container nhưng giữ container và volume
docker compose stop db

# Khởi động lại service đã dừng
docker compose start db

# Xóa container và network của project; named volume vẫn được giữ
docker compose down

# Xem các volume Docker
docker volume ls
~~~

Để bắt đầu lại từ database trống, lệnh docker compose down --volumes sẽ xóa cả named volume do Compose quản lý cùng project. Đây là thao tác phá hủy dữ liệu. Chỉ dùng khi đã xác nhận đúng Compose project, đúng volume và không còn dữ liệu cần giữ. Sau đó docker compose up -d db sẽ khởi tạo database mới từ các biến hiện tại.

Trong nhóm có nhiều project Compose, tên volume thực tế thường được gắn tiền tố theo project name. Đặt tên project nhất quán giúp tránh nhầm volume; không suy đoán tên volume để xóa. Trước khi xóa, xem docker compose config và docker volume ls để xác nhận tài nguyên thuộc đúng lab.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| docker compose không chạy | Chưa cài Compose plugin hoặc terminal không tìm thấy Docker CLI | Kiểm tra docker --version, docker compose version; cài hoặc cập nhật Docker phù hợp |
| Docker daemon không phản hồi | Docker Desktop chưa chạy hoặc Docker Engine chưa khởi động | Khởi động daemon, kiểm tra docker info |
| Cổng 5432 đã được sử dụng | PostgreSQL local hoặc container khác đang chiếm cổng host | Đổi DB_PORT thành 5433, khởi động lại và cập nhật JDBC URL trên host |
| Container chạy nhưng chưa healthy | Database đang khởi tạo, health check sai user/database hoặc PostgreSQL lỗi | Xem docker compose logs db, kiểm tra biến khởi tạo và lệnh pg_isready |
| password authentication failed | User/mật khẩu không khớp với cluster đã tồn tại trong volume | Xác minh .env; nhớ rằng đổi biến khởi tạo không sửa user đã được tạo trong volume |
| database does not exist | Database name không khớp hoặc biến khởi tạo chỉ được áp dụng ở lần đầu | Kiểm tra tên database trong URL và liệt kê database bằng psql |
| Host không kết nối được | Cổng chưa publish, host port sai hoặc firewall chặn | Kiểm tra docker compose ps, ánh xạ port và JDBC URL |
| Container ứng dụng không tìm thấy database | Client chạy trong container nhưng dùng địa chỉ loopback của chính nó | Dùng hostname service db và cổng nội bộ 5432 |
| Liquibase báo lock đang được giữ | Có tiến trình migration khác đang chạy hoặc lock còn lại sau sự cố | Kiểm tra pipeline, process và log trước; chỉ giải phóng lock sau khi xác nhận không còn migration đang hoạt động |
| Changelog đã chạy nhưng sửa dữ liệu cấu hình không có tác dụng | Volume cũ vẫn giữ database đã khởi tạo; script init không chạy lại | Dùng SQL hoặc changeset mới để thay đổi trạng thái hiện tại |

Khi điều tra lỗi, bắt đầu từ lớp thấp nhất: Docker daemon, trạng thái container, log database, readiness, cổng và xác thực. Sau khi kết nối SQL thành công mới kiểm tra cấu hình JDBC, Liquibase và changeset. Cách đi theo từng lớp giúp xác định lỗi thuộc hạ tầng local, kết nối hay migration.

## 11. Từ lab local đến cấu hình dùng chung

Cấu hình Compose trong bài phục vụ học tập và phát triển local. Trước khi dùng trong CI hoặc môi trường chia sẻ, nhóm cần bổ sung các quyết định vận hành:

- Chốt image version hoặc digest, cập nhật có kiểm soát và diễn tập nâng cấp PostgreSQL.
- Đưa thông tin xác thực vào secret manager hoặc cơ chế secret của nền tảng; không lưu bí mật trong repository.
- Giới hạn cổng database chỉ ở phạm vi cần thiết. Nếu chỉ client trên host cần truy cập, có thể bind cổng vào loopback như 127.0.0.1:5432:5432 thay vì publish trên mọi interface.
- Chọn volume và chính sách backup phù hợp với môi trường triển khai; local named volume không phải giải pháp lưu trữ production.
- Tách tài khoản migration có quyền DDL khỏi tài khoản runtime chỉ cần quyền truy cập nghiệp vụ.
- Có health check, log, giám sát, retry và quy trình phục hồi đã được thử.
- Để pipeline điều phối migration một cách có kiểm soát; tránh nhiều replica hoặc nhiều job chạy migration cùng lúc.
- Kiểm thử changelog trên đúng hệ quản trị và phiên bản database mà môi trường đích sử dụng.

Với môi trường local, có thể dùng một tài khoản đơn giản để người học tập trung vào Liquibase. Khi chuyển sang staging hoặc production, cần rà soát lại quyền, secrets, mạng, backup, khả năng tương thích ngược và quy trình triển khai. Không sao chép nguyên mật khẩu, cổng mở hoặc chính sách volume của lab sang môi trường thật.

## 12. Checklist hoàn tất trước khi học migration

| Hạng mục | Điều kiện đạt |
|---|---|
| Docker | Docker CLI giao tiếp được với Docker Engine |
| Compose | docker compose config --quiet không báo lỗi |
| Container | Service db ở trạng thái running và healthy |
| Database | Kết nối được tới liquibase_lab bằng user đã cấu hình |
| Readiness | pg_isready trả về trạng thái chấp nhận kết nối |
| Lưu trữ | Named volume được gắn vào data directory PostgreSQL |
| Địa chỉ | Host dùng localhost:DB_PORT; container cùng network dùng db:5432 |
| Bảo mật local | .env không được commit; mật khẩu chỉ dùng cho lab |
| Liquibase | JDBC URL, driver, changelog và quyền database được cấu hình đúng |
| Khả năng lặp lại | Dừng/tạo lại container vẫn giữ dữ liệu khi không xóa volume |

Khi các điều kiện trên đạt, database đã sẵn sàng cho các bài thực hành Liquibase. Người học có thể bắt đầu với changeset tạo bảng, tiếp tục thêm constraint và dữ liệu tham chiếu, rồi kiểm tra precondition, checksum, rollback và lịch sử triển khai trên cùng một database. Compose cung cấp môi trường database có thể dựng lại; Liquibase quản lý thay đổi bên trong database theo lịch sử có phiên bản.

