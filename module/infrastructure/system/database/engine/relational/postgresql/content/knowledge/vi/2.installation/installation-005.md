# Tạo môi trường thực hành với Docker Compose và volume bền vững cho PostgreSQL

Khi học PostgreSQL, việc cài trực tiếp lên máy tính có thể làm phát sinh nhiều vấn đề: phiên bản PostgreSQL của dự án khác với phiên bản đang học; cổng mặc định `5432` đã có ứng dụng sử dụng; cấu hình và dữ liệu thử nghiệm trộn lẫn với database thật; hoặc người học xóa container rồi tưởng dữ liệu cũng bị xóa theo. **Docker Compose** giúp mô tả một môi trường PostgreSQL có thể khởi chạy lại bằng một tệp YAML, còn **Docker volume** giúp lưu dữ liệu độc lập với vòng đời của container.

Bài này xây dựng một PostgreSQL dành riêng cho thực hành, có:

- Một service `db` dùng image PostgreSQL chính thức, cố định phiên bản lớn.
- Tài khoản, mật khẩu và database khởi tạo từ biến môi trường.
- Cổng truy cập từ máy chủ được giới hạn về `127.0.0.1` để tránh vô tình mở database ra mạng ngoài.
- Một **named volume** lưu `PGDATA`, để dữ liệu vẫn còn sau khi container bị dừng hoặc tạo lại.
- Một healthcheck và thư mục chứa script SQL chỉ chạy khi dữ liệu được khởi tạo lần đầu.
- Những câu lệnh kiểm chứng: tạo bảng, ghi dữ liệu, `docker compose down`, `up` rồi đọc lại dữ liệu.

Ví dụ sử dụng image `postgres:16` để giữ ổn định đường dẫn dữ liệu bên trong container. Khi dùng phiên bản lớn khác, nhất là PostgreSQL 18 trở lên, **không tự sao chép đường mount** vì cách tổ chức `PGDATA` trong image chính thức có thể thay đổi.

## 1. Docker, image, container, Compose và volume khác nhau thế nào?

| Khái niệm | Ý nghĩa | Liên hệ với bài |
| --- | --- | --- |
| **Image** | Mẫu chứa hệ điều hành tối thiểu, PostgreSQL và entrypoint cần chạy | `postgres:16` |
| **Container** | Một tiến trình/môi trường được tạo từ image | Container chạy PostgreSQL |
| **Docker Compose** | Công cụ định nghĩa nhiều tài nguyên Docker qua một tệp YAML | `compose.yaml` định nghĩa `db` và volume |
| **Named volume** | Vùng lưu trữ do Docker quản lý, tồn tại ngoài vòng đời container | `pgdata` chứa dữ liệu PostgreSQL |
| **Bind mount** | Ánh xạ một đường dẫn thư mục/tệp trên máy chủ vào container | `./init` chứa SQL khởi tạo |
| **PGDATA** | Thư mục dữ liệu mà PostgreSQL server sử dụng | `/var/lib/postgresql/data` trong image `postgres:16` |

Hình dung quan hệ:

~~~text
Máy tính đang chạy Docker
│
├── Thư mục dự án postgres-lab/
│   ├── compose.yaml
│   ├── .env
│   └── init/
│       └── 01_schema.sql
│
├── Docker Compose project
│   └── Service db
│       └── Container chạy PostgreSQL 16
│           ├── cổng 5432 trong container
│           ├── /var/lib/postgresql/data  ← named volume pgdata
│           └── /docker-entrypoint-initdb.d ← bind mount ./init
│
└── Docker volume pgdata
    └── Database files, WAL, catalog, dữ liệu bảng...
~~~

**Điểm cốt lõi:** container có thể bị xóa và được tạo mới, nhưng named volume vẫn tồn tại cho đến khi bị xóa riêng hoặc gặp sự cố lưu trữ. Khi container mới dùng lại **đúng volume**, PostgreSQL nhìn thấy trạng thái dữ liệu cũ thay vì khởi tạo cluster mới.

### Vì sao không chỉ lưu dữ liệu trong filesystem của container?

Nếu dữ liệu nằm hoàn toàn trong lớp ghi có thể bị xóa cùng container, thay container mới sẽ không tự mang theo các tệp đó. PostgreSQL là hệ quản trị có trạng thái (*stateful*), vì vậy cần gắn đường dẫn dữ liệu với một nơi lưu trữ có vòng đời riêng.

Docker volume giải quyết **tính bền vững khi thay container**, nhưng **không thay thế backup**. Xóa nhầm bảng, hỏng ổ đĩa, mất máy chủ hoặc lỗi dữ liệu trong volume vẫn có thể làm mất dữ liệu.

## 2. Điều kiện trước khi bắt đầu

Bạn cần:

1. Docker Engine hoặc Docker Desktop đã cài và đang chạy.
2. Docker Compose plugin sử dụng cú pháp `docker compose` (có dấu cách, không nhất thiết là công cụ cũ `docker-compose`).
3. Quyền chạy Docker trong môi trường thực hành.
4. Cổng `5433` của máy chủ chưa bị ứng dụng khác chiếm.
5. Ổ đĩa còn đủ dung lượng cho image, volume và dữ liệu thử nghiệm.

Kiểm tra:

~~~bash
docker --version
docker compose version
docker info
~~~

`docker info` cần giao tiếp với Docker daemon. Nếu Docker Desktop chưa chạy hoặc tài khoản chưa được cấp quyền sử dụng Docker, lệnh có thể thất bại dù chương trình dòng lệnh đã cài.

Các lệnh có thể thực hiện bằng terminal Linux/macOS, PowerShell hoặc terminal tích hợp của IDE nếu Docker được cấu hình thích hợp. Những ví dụ dùng `docker compose` và `docker exec` không phụ thuộc riêng vào Bash; riêng thao tác đường dẫn và quản lý file trên host có thể khác giữa các hệ điều hành.

## 3. Tạo cấu trúc dự án

Tạo một thư mục riêng, ví dụ `postgres-lab`, với các tệp:

~~~text
postgres-lab/
├── compose.yaml
├── .env
├── .gitignore
└── init/
    └── 01_schema.sql
~~~

Tệp `compose.yaml` khai báo tài nguyên Docker; `.env` giữ các giá trị cấu hình dành cho môi trường học tập; `init/01_schema.sql` là lệnh SQL tự động chạy khi tạo cluster dữ liệu lần đầu.

Thư mục hiện hành rất quan trọng: các lệnh `docker compose ...` bên dưới được chạy từ **`postgres-lab/`**, nơi có tệp `compose.yaml`. Nếu chạy ở thư mục khác, hãy dùng tùy chọn `-f` hoặc chuyển về đúng thư mục.

### Tệp compose.yaml

~~~yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped

    environment:
      POSTGRES_USER: "${POSTGRES_USER:-lab_user}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
      POSTGRES_DB: "${POSTGRES_DB:-lab_db}"
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"

    ports:
      - "127.0.0.1:5433:5432"

    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d:ro

    healthcheck:
      test:
        - CMD-SHELL
        - 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s

volumes:
  pgdata:
~~~

Không cần khóa `version:` trong định dạng Compose hiện đại; Compose sử dụng đặc tả hiện hành và một số phiên bản có thể cảnh báo khi gặp trường `version` cũ.

### Tệp .env

~~~dotenv
POSTGRES_USER=lab_user
POSTGRES_PASSWORD=replace_with_a_long_random_local_secret
POSTGRES_DB=lab_db
~~~

**Phải thay** `replace_with_a_long_random_local_secret` bằng mật khẩu thực hành đủ mạnh trước khi chạy. Không dùng ví dụ đó như mật khẩu của một hệ thống thật.

Compose dùng `.env` để **nội suy biến** trong `compose.yaml`. Các giá trị `POSTGRES_USER`, `POSTGRES_PASSWORD` và `POSTGRES_DB` sau đó được chuyển vào container theo khai báo `environment`.

Trong Compose, biểu thức `${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}` yêu cầu biến có giá trị không rỗng; nếu thiếu hoặc rỗng, Compose sẽ dừng với thông báo thay vì khởi tạo tài khoản không có mật khẩu.

Lưu ý:

- `.env` thuận tiện cho **môi trường học tập cục bộ**, nhưng không phải kho bí mật chuyên dụng. Người có quyền kiểm tra cấu hình Docker hoặc container có thể đọc được biến môi trường.
- Biến của môi trường shell có thể **ghi đè giá trị nội suy từ `.env`** tùy quy tắc ưu tiên của Compose. Nếu thấy cấu hình khác dự kiến, kiểm tra các biến đang đặt trong terminal.
- Không commit mật khẩu thật vào Git, không chụp ảnh màn hình hoặc gửi đầu ra chứa bí mật lên hệ thống công khai.

### Tệp .gitignore

~~~gitignore
.env
*.dump
*.backup
*.sql.gz
~~~

`.gitignore` ngăn Git thêm những file này nếu chúng chưa được theo dõi; nó **không bảo vệ bí mật đã từng được commit trước đó**. Với dự án dùng Git, nên cung cấp tệp `.env.example` không chứa mật khẩu thật để hướng dẫn người khác thiết lập.

## 4. Hiểu từng phần trong compose.yaml

### 4.1. services.db và image

~~~yaml
services:
  db:
    image: postgres:16
~~~

`db` là **tên service** trong Compose, không phải tên database PostgreSQL. Bên trong mạng riêng của cùng một Compose project, service khác có thể kết nối tới host `db`, cổng `5432`.

`postgres:16` cố định **phiên bản lớn 16** để các lần kéo image không tự chuyển sang PostgreSQL 17 hoặc 18. Tuy nhiên, tag này có thể nhận những bản vá mới của nhánh 16. Với môi trường yêu cầu tái lập từng byte, cần ghim image theo digest và có kế hoạch cập nhật bảo mật.

**Đừng đổi đơn giản `postgres:16` thành `postgres:17` hoặc `postgres:18` rồi dùng lại PGDATA 16.** Dữ liệu vật lý PostgreSQL không được nâng phiên bản lớn bằng cách thay image; cần quy trình nâng cấp như `pg_upgrade` hoặc dump/restore thích hợp.

### 4.2. POSTGRES_USER, POSTGRES_PASSWORD và POSTGRES_DB

Image PostgreSQL chính thức nhận các biến khởi tạo:

| Biến | Vai trò lúc khởi tạo cluster mới |
| --- | --- |
| `POSTGRES_USER` | Tên role PostgreSQL ban đầu có quyền **superuser** |
| `POSTGRES_PASSWORD` | Mật khẩu của role khởi tạo |
| `POSTGRES_DB` | Tên database được tạo lúc khởi tạo |
| `POSTGRES_INITDB_ARGS` | Các tùy chọn chuyển tới `initdb` ở lần khởi tạo đầu |

Ở ví dụ này, image tạo role `lab_user` và database `lab_db`. **`lab_user` là superuser** do đây là bootstrap role của image, vì vậy cấu hình này chỉ dành cho môi trường học tập. Trong hệ thống thật, nên tạo tài khoản ứng dụng riêng với quyền tối thiểu và không cho ứng dụng kết nối bằng bootstrap superuser.

`POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"` chọn UTF-8 và locale C lúc tạo cluster. Locale C có thứ tự so sánh đơn giản, không tương đương quy tắc tiếng Việt; tùy bài toán có thể chọn một locale khác được image hỗ trợ.

**Các biến khởi tạo không tự chạy lại khi volume đã có cluster PostgreSQL.** Nếu sau vài ngày thay `POSTGRES_DB` từ `lab_db` thành `other_db`, image không tự tạo database mới trên volume đã khởi tạo. Muốn tạo database khác trên cluster hiện tại, dùng `CREATE DATABASE` trong PostgreSQL. Thay mật khẩu trong `.env` cũng **không tự đổi mật khẩu** role đã tồn tại; khi cần hãy dùng `ALTER ROLE` qua tài khoản có quyền phù hợp.

### 4.3. ports và kết nối từ host

~~~yaml
ports:
  - "127.0.0.1:5433:5432"
~~~

Cú pháp ở đây gồm:

~~~text
127.0.0.1 : 5433 : 5432
   │         │       │
   │         │       └── cổng PostgreSQL trong container
   │         └────────── cổng được công bố trên host
   └──────────────────── địa chỉ interface của host
~~~

Nhờ vậy:

- Công cụ trên **máy host** có thể kết nối tới `127.0.0.1:5433`.
- PostgreSQL bên trong container vẫn lắng nghe cổng `5432`.
- Địa chỉ host `127.0.0.1` hạn chế cổng được công bố ở loopback, tránh vô tình mở cổng trên mọi interface mạng.

Không nhầm `127.0.0.1` bên trong một container ứng dụng với `127.0.0.1` trên host: bên trong container, `localhost` là chính container đó. Nếu một service ứng dụng chạy trong **cùng mạng Compose**, nó thường dùng `db:5432` thay vì `127.0.0.1:5433`.

### 4.4. volumes: named volume cho dữ liệu

~~~yaml
volumes:
  - pgdata:/var/lib/postgresql/data
~~~

Trong PostgreSQL 16 image chính thức, `/var/lib/postgresql/data` là đường dẫn dữ liệu mặc định theo cấu hình image. `pgdata` bên trái là **named volume do Docker quản lý**; nội dung bên phải là đường dẫn bên trong container.

Ở cuối tệp:

~~~yaml
volumes:
  pgdata:
~~~

Compose khai báo resource volume có tên `pgdata`. Tên thực tế trong Docker thường được thêm **tiền tố tên dự án Compose**, ví dụ `postgres-lab_pgdata`. Tên dự án thường bắt nguồn từ thư mục chạy, trừ khi có thiết lập riêng.

**Hệ quả:** nếu sao chép nguyên thư mục sang vị trí khác rồi chạy với tên project khác, Compose có thể tạo **volume mới**; dữ liệu cũ không bị xóa mà đang nằm trong volume thuộc project cũ. Đây là một lý do phổ biến khiến người học tưởng dữ liệu đã mất sau khi đổi tên thư mục.

### 4.5. Bind mount cho script khởi tạo

~~~yaml
volumes:
  - ./init:/docker-entrypoint-initdb.d:ro
~~~

`./init` là đường dẫn thư mục trên host, được mount vào `/docker-entrypoint-initdb.d` bên trong container. Hậu tố `:ro` có nghĩa container chỉ đọc nội dung được mount.

Entrypoint của image PostgreSQL chính thức có cơ chế chạy những file khởi tạo phù hợp trong thư mục này **khi cluster được tạo lần đầu**. Thông thường gồm các file `.sql`, `.sql.gz` và script shell `.sh` theo quy tắc của image.

Nếu PGDATA đã có dữ liệu, những script này **không tự chạy lại** khi bạn dùng `docker compose restart` hay `up --force-recreate`. Vì vậy, thư mục `init` phù hợp cho **bootstrap dữ liệu lab**, không phải công cụ migration tự động cho database đang vận hành.

### 4.6. Healthcheck

~~~yaml
healthcheck:
  test:
    - CMD-SHELL
    - 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
  interval: 5s
  timeout: 3s
  retries: 10
  start_period: 10s
~~~

`pg_isready` kiểm tra PostgreSQL có ở trạng thái chấp nhận kết nối hay không. `$$POSTGRES_USER` và `$$POSTGRES_DB` trong Compose dùng **hai dấu dollar** để tránh Compose nội suy biến ở host; sau đó shell bên trong container nhận các biến môi trường thực.

Healthcheck hữu ích để phân biệt:

- Container đã được tạo/chạy.
- PostgreSQL bên trong đã sẵn sàng nhận kết nối.

Nhưng **`healthy` không chứng minh mật khẩu đúng, schema đã migration xong, hay mọi truy vấn ứng dụng đều thành công**. `pg_isready` là kiểm tra khả năng nhận kết nối, không thay thế kiểm tra chức năng đầy đủ.

## 5. Tạo script SQL khởi tạo dữ liệu lần đầu

Tệp `init/01_schema.sql`:

~~~sql
CREATE TABLE lab_entries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lab_entries (note)
VALUES ('Du lieu tu script khoi tao lan dau');
~~~

Đây là một bảng đơn giản để chứng minh script khởi tạo đã chạy. Khi volume trống, entrypoint tạo cluster, tạo database `lab_db` rồi thực thi script SQL trong database khởi tạo. Kết quả ban đầu có một dòng dữ liệu.

Với môi trường bài tập, dùng script khởi tạo có thể giúp mọi người bắt đầu từ trạng thái giống nhau. Trong dự án phát triển lâu dài, thay đổi schema theo nhiều phiên bản thường cần công cụ migration, ví dụ Flyway, Liquibase hoặc một quy trình được kiểm soát tương đương, vì script init chỉ chạy lúc tạo cluster lần đầu.

**Chú ý lỗi lúc khởi tạo:** nếu một script thất bại sau khi cluster đã được tạo, volume có thể vẫn chứa dữ liệu chưa hoàn tất. Lần khởi động tiếp theo không nhất thiết chạy lại toàn bộ script, vì PGDATA đã không còn trống. Với lab có thể tạo **một volume mới** sau khi đã xác nhận không cần dữ liệu cũ; với hệ thống thật phải điều tra lỗi và lập kế hoạch phục hồi, không xóa volume theo phản xạ.

## 6. Khởi chạy PostgreSQL bằng Docker Compose

Chuyển tới thư mục `postgres-lab` rồi kiểm tra cấu hình:

~~~bash
docker compose config --quiet
docker compose config --services
docker compose config --volumes
~~~

`docker compose config --quiet` kiểm tra cú pháp cấu hình và nội suy mà không in bản cấu hình đầy đủ. Điều này phù hợp khi file dùng mật khẩu từ `.env`, vì `docker compose config` **không có `--quiet` có thể in cả mật khẩu đã được nội suy**. Không chia sẻ đầu ra nhạy cảm.

Khởi động:

~~~bash
docker compose up -d
~~~

Lần đầu, Docker có thể tải image PostgreSQL, tạo mạng Compose, tạo named volume và chạy container. Tùy cấu hình image, entrypoint sẽ gọi `initdb` để khởi tạo cluster, tạo role/database và chạy script `01_schema.sql`.

Theo dõi:

~~~bash
docker compose ps
docker compose logs --tail=100 db
~~~

`docker compose ps` hiển thị container và tình trạng của service; sau khi hoàn tất init, healthcheck dự kiến chuyển sang trạng thái `healthy`. `docker compose logs --tail=100 db` cho biết thông báo khởi tạo, kết nối, lỗi và quá trình PostgreSQL khởi động.

Trong môi trường dùng container thật, log có thể chứa thông tin nhạy cảm từ ứng dụng hoặc SQL khởi tạo; không gửi nguyên log lên nơi công khai trước khi rà soát.

### Nếu PostgreSQL chưa healthy

Xem log:

~~~bash
docker compose ps
docker compose logs --tail=150 db
~~~

Nguyên nhân thường gặp gồm mật khẩu khởi tạo thiếu, script SQL lỗi, cổng host đã bị chiếm, quyền thư mục bind mount không phù hợp, volume có dữ liệu của phiên bản PostgreSQL khác, hoặc máy chủ không đủ tài nguyên.

Nếu cổng `5433` đã được dùng, hãy đổi **phía host** của mapping, chẳng hạn thành `127.0.0.1:55432:5432`. Đừng đổi cổng trong container nếu bài thực hành không có lý do đặc biệt.

## 7. Kết nối và truy vấn trong container

Sau khi service sẵn sàng, dùng `docker compose exec` để chạy `psql` trong container:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db
~~~

Trong `psql`:

~~~sql
SELECT version();
SELECT current_database(), current_user;
SELECT id, note, created_at
FROM lab_entries
ORDER BY id;
~~~

Theo script khởi tạo, bạn sẽ thấy một dòng:

~~~text
id | note
---+-----------------------------------
 1 | Du lieu tu script khoi tao lan dau
~~~

Các lệnh tiện ích trong `psql`:

~~~text
\l          -- danh sách database
\dt         -- danh sách bảng trong schema tìm kiếm
\d lab_entries
\q          -- thoát psql
~~~

Đây là **meta-command của `psql`**, không phải SQL tiêu chuẩn. Muốn chạy một câu trực tiếp từ terminal:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT COUNT(*) AS total FROM lab_entries;"
~~~

Lưu ý: kết nối cục bộ từ trong container có thể dùng quy tắc xác thực khác với kết nối TCP từ máy host. Việc `docker compose exec db psql ...` chạy được **không tự chứng minh** mật khẩu kết nối bên ngoài đã đúng.

### Kết nối từ ứng dụng trên máy host

Với cổng đã công bố trong Compose:

~~~text
Host:       127.0.0.1
Port:       5433
Database:   lab_db
Username:   lab_user
Password:   giá trị đã đặt trong .env
~~~

Nếu có `psql` cài trên host:

~~~bash
psql -h 127.0.0.1 -p 5433 -U lab_user -d lab_db
~~~

Công cụ sẽ hỏi mật khẩu nếu cơ chế xác thực yêu cầu. Không cần ghi mật khẩu trực tiếp trong lệnh hoặc lịch sử terminal.

Ví dụ JDBC URL cho ứng dụng Java chạy **trên host**:

~~~properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5433/lab_db
spring.datasource.username=lab_user
spring.datasource.password=YOUR_LOCAL_SECRET
~~~

Chỉ dùng `YOUR_LOCAL_SECRET` làm chỗ giữ chỗ, không đưa mật khẩu thật vào kho mã nguồn. Một ứng dụng Java chạy trong **container khác thuộc cùng Compose network** sẽ kết nối bằng `jdbc:postgresql://db:5432/lab_db` thay vì địa chỉ loopback của host.

## 8. Thực nghiệm: dữ liệu vẫn còn sau khi thay container

Đây là phần quan trọng nhất để hiểu **volume bền vững**. Ta sẽ thêm một dòng thủ công, dừng/xóa container, khởi động lại và kiểm tra dòng vẫn còn.

### Bước 1. Ghi một dòng sau lúc khởi tạo

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "INSERT INTO lab_entries (note) VALUES ('Du lieu duoc ghi sau khi khoi dong');"
~~~

Xem dữ liệu:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

Lúc này dự kiến có **hai dòng**: một dòng từ script init và một dòng vừa chèn.

### Bước 2. Dừng Compose và xóa container thông thường

~~~bash
docker compose down
~~~

`docker compose down` mặc định dừng và xóa các container/network do Compose tạo cho project, nhưng **không xóa named volume `pgdata`**. Dữ liệu PostgreSQL vẫn còn trong Docker volume.

Kiểm tra danh sách volume:

~~~bash
docker volume ls
~~~

Bạn thường sẽ thấy một volume có tên tương tự `postgres-lab_pgdata`. Tên thực tế phụ thuộc tên Compose project; đừng tự đoán tên và chạy lệnh xóa dựa trên một chuỗi ví dụ.

### Bước 3. Khởi động lại

~~~bash
docker compose up -d
docker compose ps
~~~

Compose tạo container mới và gắn lại named volume đã có. Vì `PGDATA` trong volume chứa một cluster PostgreSQL hợp lệ, entrypoint sẽ **không chạy lại `initdb` và không chạy lại script `01_schema.sql`**.

Kiểm tra:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

Kết quả dự kiến **vẫn có hai dòng**. Điều này chứng minh dữ liệu đã tồn tại **ngoài vòng đời của container**.

### Bước 4. Tái tạo container nhưng giữ nguyên volume

Có thể thử:

~~~bash
docker compose up -d --force-recreate
~~~

Lệnh yêu cầu tạo lại container, nhưng vẫn dùng volume được khai báo. Dữ liệu sẽ tiếp tục tồn tại nếu volume cũ được gắn đúng và cluster không bị hỏng.

**Khác biệt cần nhớ:**

| Thao tác | Container | Named volume được khai báo |
| --- | --- | --- |
| `docker compose stop` | Dừng, không xóa | Giữ lại |
| `docker compose start` | Chạy container đã có | Giữ lại |
| `docker compose restart` | Khởi động lại container | Giữ lại |
| `docker compose down` | Xóa container và network của project | **Giữ lại** |
| `docker compose up -d --force-recreate` | Tạo lại container | **Giữ lại** |
| `docker compose down -v` | Xóa container và network | **Xóa named volume do Compose khai báo** |

Điều cuối rất quan trọng: **`docker compose down -v` là thao tác phá hủy dữ liệu của bài thực hành** nếu volume chỉ chứa bản dữ liệu duy nhất. Chỉ dùng khi bạn cố ý xóa môi trường lab và đã chắc chắn không còn dữ liệu cần giữ.

## 9. Named volume và bind mount: nên chọn cái nào?

Cả hai có thể lưu dữ liệu ngoài container, nhưng khác cách quản lý:

| Tiêu chí | Named volume | Bind mount |
| --- | --- | --- |
| Đường dẫn lưu | Docker quản lý | Người dùng chỉ định đường dẫn trên host |
| Ví dụ Compose | `pgdata:/var/lib/postgresql/data` | `./pg-data:/var/lib/postgresql/data` |
| Quyền truy cập | Docker hỗ trợ quản lý resource | Phụ thuộc owner, permission và file sharing của host |
| Dễ dùng trên Docker Desktop | Thường thuận tiện | Có thể chịu ảnh hưởng hiệu năng và chia sẻ file host |
| Kiểm tra trên host | Qua Docker và các công cụ volume | Có thể nhìn thư mục trực tiếp |
| Rủi ro | Vẫn có thể bị xóa bằng lệnh volume | Có thể bị xóa/sửa nhầm từ host, sai quyền hoặc thiếu hiệu năng |

Với PostgreSQL luyện tập, **named volume thường là lựa chọn đơn giản**: không phải tự xử lý permission phức tạp của thư mục dữ liệu trên Windows/macOS và tránh đặt PGDATA dưới thư mục dự án bị đồng bộ.

Bind mount vẫn phù hợp cho các tệp cấu hình, script init hoặc một môi trường Linux cần chủ động kiểm soát layout lưu trữ. Tuy vậy, khi bind mount cả PGDATA, cần quan tâm quyền sở hữu, filesystem, hiệu năng I/O và tính tương thích với PostgreSQL.

### Không lưu dữ liệu PostgreSQL bằng cách copy tùy ý các file đang chạy

Sao chép một thư mục PGDATA trong lúc PostgreSQL đang ghi **không phải cách backup nhất quán đáng tin cậy**. PostgreSQL còn có WAL, checkpoint và các yêu cầu nhất quán dữ liệu. Khi cần sao lưu, dùng `pg_dump`/`pg_restore` cho backup logic hoặc công cụ backup vật lý hỗ trợ PostgreSQL với quy trình phù hợp.

## 10. Phân biệt xóa container, xóa volume và thay đổi tên project

Một số tình huống rất dễ gây hiểu nhầm:

**Tình huống A: chạy `down` rồi `up` trong cùng thư mục.** Volume dự kiến được giữ, dữ liệu vẫn còn.

**Tình huống B: đổi tên thư mục project.** Compose có thể dùng một **project name khác**, kéo theo volume mới, rỗng. Dữ liệu cũ vẫn có thể nằm trong volume của project cũ.

**Tình huống C: đổi tên resource `pgdata` trong YAML.** Compose có thể tạo volume mới vì tên resource đã khác, nên PostgreSQL trông như cluster mới.

**Tình huống D: chạy `down -v`.** Volume do Compose quản lý có thể bị xóa thật; dữ liệu mất nếu không có backup.

**Tình huống E: thay `postgres:16` thành `postgres:17`.** Volume còn nguyên nhưng PostgreSQL 17 có thể từ chối khởi động trên data directory từ PostgreSQL 16 do khác phiên bản. Đây là **vấn đề nâng cấp dữ liệu**, không phải dấu hiệu volume mất.

### Xác định volume đang được Compose sử dụng

~~~bash
docker compose config --volumes
docker compose ps -q db
docker volume ls
~~~

Để xem các mount thực tế, có thể dùng:

~~~bash
docker inspect "$(docker compose ps -q db)"
~~~

`docker inspect` trả về JSON lớn, có thể chứa cả **biến môi trường và mật khẩu**. Chỉ xem cục bộ, không chia sẻ nguyên đầu ra. Trong phần mount, xác nhận loại `volume`, tên volume và đích `/var/lib/postgresql/data`.

Nếu dữ liệu “biến mất” sau khi đổi thư mục hoặc tệp Compose, **không vội chạy `down -v`**; hãy kiểm tra project name và volume đang gắn trước.

## 11. Dữ liệu khởi tạo chỉ chạy một lần

Điểm này thường gây ngạc nhiên khi làm lab. Hãy phân biệt ba trường hợp.

### 11.1. Sửa tệp 01_schema.sql sau lần chạy đầu

Giả sử bạn thêm:

~~~sql
CREATE TABLE another_table (
    id integer PRIMARY KEY
);
~~~

vào `init/01_schema.sql`, rồi:

~~~bash
docker compose restart db
~~~

**Bảng `another_table` sẽ không tự xuất hiện** chỉ vì bạn sửa script init. Volume đang chứa cluster đã khởi tạo nên entrypoint không chạy lại script.

Nếu muốn áp dụng thay đổi trên database hiện tại, hãy dùng lệnh SQL hoặc migration rõ ràng:

~~~bash
docker compose exec -T db \
  psql -U lab_user -d lab_db \
  < init/02_add_table.sql
~~~

Trong ví dụ trên, `init/02_add_table.sql` là file SQL do người học tự tạo. `-T` tắt cấp phát pseudo-TTY, hữu ích khi chuyển nội dung file qua stdin. Chỉ chạy script đã đọc và tin cậy; nếu script không có tính idempotent, chạy lại có thể báo lỗi hoặc tạo trùng dữ liệu.

### 11.2. Muốn dựng một lab hoàn toàn sạch

Nếu không cần giữ bất kỳ dữ liệu nào:

~~~bash
# CẢNH BÁO: xóa volume và toàn bộ dữ liệu lab liên quan.
docker compose down -v
docker compose up -d
~~~

Đây là quy trình **cố ý xóa dữ liệu** để tạo lại môi trường học tập từ đầu. Chỉ chạy sau khi xác minh đây là đúng Compose project và volume, không phải một service đang dùng thật. Dữ liệu mới sẽ được tạo từ các script `init` hiện tại.

### 11.3. Muốn giữ dữ liệu và nâng cấp schema

Không xóa volume. Thay vì dựa vào script init, dùng migration có version, ví dụ:

~~~text
V1__create_lab_entries.sql
V2__add_category_column.sql
V3__create_indexes.sql
~~~

Thực thi migration bằng công cụ hoặc quy trình phù hợp, theo dõi phiên bản schema và có phương án rollback khi thay đổi thất bại. Compose lo **vòng đời container**, còn công cụ migration lo **lịch sử thay đổi cấu trúc database**.

## 12. Sao lưu và khôi phục dữ liệu lab

Named volume bảo vệ dữ liệu khi thay container, nhưng không bảo vệ trước xóa nhầm, hỏng ổ hoặc lệnh `down -v`. Ngay cả với môi trường thực hành, nên biết cách tạo bản sao lưu logic.

### 12.1. Sao lưu bằng pg_dump

Ví dụ sau dùng `pg_dump` chạy **bên trong container**, ghi file định dạng custom vào `/tmp` của container:

~~~bash
docker compose exec db \
  pg_dump -U lab_user -d lab_db \
  -F c -f /tmp/lab_db.dump
~~~

Sau đó sao chép file backup từ container về thư mục làm việc trên host:

~~~bash
docker cp "$(docker compose ps -q db):/tmp/lab_db.dump" ./lab_db.dump
~~~

Hai lệnh này tránh phải chuyển **luồng nhị phân** của `pg_dump -Fc` qua tính năng chuyển hướng shell trên host, vốn có thể xử lý byte khác nhau giữa các shell (đặc biệt trên những môi trường PowerShell cũ).

`lab_db.dump` ở host là bản backup logic của database `lab_db`. Nó phải được giữ ở nơi an toàn nếu dữ liệu có giá trị; không nên coi bản sao nằm trong `/tmp` của container là nơi lưu bền vững.

### 12.2. Thử restore sang database khác trong lab

Trong môi trường thực hành, có thể kiểm tra backup bằng cách phục hồi vào database **mới**, thay vì ghi đè database đang dùng:

~~~bash
docker compose exec db \
  createdb -U lab_user lab_restore

docker cp ./lab_db.dump "$(docker compose ps -q db):/tmp/lab_db.dump"

docker compose exec db \
  pg_restore -U lab_user -d lab_restore \
  /tmp/lab_db.dump
~~~

Sau đó xác minh:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_restore \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

Bảng `lab_entries` và dữ liệu từ backup nên xuất hiện trong `lab_restore`. Đây là cách luyện tập ý tưởng **restore test**: backup chỉ đáng tin khi có thể khôi phục và đọc lại dữ liệu.

**Lưu ý phạm vi:** `pg_dump -d lab_db` là bản sao lưu của **một database**, không tự bao gồm mọi role toàn cluster, các database khác hoặc tất cả cấu hình instance. Trong hệ thống thật, cần kế hoạch backup bao gồm đúng những tài nguyên phải phục hồi. Ngoài ra, `pg_dump` dạng logic không thay thế PITR với WAL nếu có yêu cầu phục hồi đến thời điểm chính xác.

### 12.3. Vì sao không backup chỉ bằng docker volume?

Docker volume là nơi chứa file; nó không tự tạo các điểm phục hồi lịch sử. Một bản sao volume khi database đang chạy có thể không nhất quán nếu không thực hiện đúng quy trình backup vật lý của PostgreSQL. Với lab, `pg_dump` dễ hiểu và thuận tiện để bắt đầu. Với hệ thống lớn, cân nhắc `pg_basebackup`, WAL archiving và công cụ sao lưu được kiểm thử.

## 13. Nâng cấp image PostgreSQL mà không mất dữ liệu

Có ba loại thay đổi cần phân biệt:

1. **Khởi động lại cùng image:** dữ liệu trên volume vẫn còn.
2. **Cập nhật phiên bản vá trong cùng phiên bản lớn:** thường có thể sử dụng lại PGDATA, nhưng vẫn cần backup và kiểm tra ghi chú phát hành trước khi cập nhật.
3. **Nâng phiên bản lớn**, ví dụ PostgreSQL 16 → 17: **không chỉ thay tag image**. Cần quá trình nâng cấp database phù hợp với cơ chế của PostgreSQL.

Hai hướng phổ biến cho nâng phiên bản lớn:

- **Dump/restore:** xuất dữ liệu từ PostgreSQL cũ, tạo cluster mới bằng image phiên bản đích rồi nhập dữ liệu.
- **pg_upgrade:** nâng cấp cluster theo quy trình tương thích với hai bản PostgreSQL và đường dẫn dữ liệu/thư viện cần thiết.

Với Docker Compose, việc tạo volume mới cho phiên bản đích và **giữ lại volume cũ đến khi kiểm chứng xong** thường là hướng an toàn hơn so với đụng vào dữ liệu đang hoạt động.

Ngoài ra, PostgreSQL 18 có thay đổi quan trọng về cách bố trí thư mục dữ liệu trong image Docker chính thức; không nên giả định đường mount `/var/lib/postgresql/data` của ví dụ `postgres:16` áp dụng nguyên xi cho mọi tag mới.

## 14. Những lỗi thường gặp khi tạo lab bằng Compose

### 14.1. Thiếu hoặc rỗng POSTGRES_PASSWORD

**Dấu hiệu:** Compose báo thiếu biến, hoặc container khởi tạo lỗi liên quan tới mật khẩu.

**Cách xử lý:** kiểm tra tệp `.env` nằm trong phạm vi Compose sử dụng, biến `POSTGRES_PASSWORD` có giá trị không rỗng và không bị biến môi trường shell ghi đè thành chuỗi rỗng.

Không sửa bằng cách bật cơ chế `trust` cho mọi host trong một môi trường có kết nối mạng, vì điều đó làm giảm kiểm soát xác thực.

### 14.2. Cổng 5433 bị chiếm

**Dấu hiệu:** Docker không thể publish port vì địa chỉ/cổng đã được dùng.

**Cách xử lý:** đổi cổng **host** ở phần `ports`, ví dụ `127.0.0.1:55432:5432`. Không cần thay cổng PostgreSQL bên trong service nếu không có yêu cầu riêng.

### 14.3. Thay POSTGRES_DB nhưng database mới không được tạo

**Nguyên nhân:** volume đã có PGDATA nên entrypoint không chạy bước bootstrap nữa.

**Cách xử lý:** dùng `CREATE DATABASE` trong cluster hiện tại, hoặc khởi tạo lab mới trên một volume mới có chủ đích.

### 14.4. Sửa script init rồi không thấy bảng mới

**Nguyên nhân:** script trong `/docker-entrypoint-initdb.d` chỉ chạy khi khởi tạo cluster lần đầu.

**Cách xử lý:** chạy SQL migration hoặc tạo môi trường lab sạch nếu đã xác nhận không cần dữ liệu cũ.

### 14.5. Dùng localhost từ container ứng dụng khác

**Nguyên nhân:** `127.0.0.1` bên trong container ứng dụng trỏ tới chính container đó.

**Cách xử lý:** nếu cùng mạng Compose, dùng service name `db` và cổng nội bộ `5432`. Chỉ dùng `127.0.0.1:5433` cho ứng dụng chạy trực tiếp trên host.

### 14.6. Compose dùng volume mới sau khi đổi tên thư mục

**Nguyên nhân:** tên project Compose đổi, kéo theo tên volume thực tế đổi.

**Cách xử lý:** kiểm tra volume cũ bằng `docker volume ls`, cấu hình project name và mount thực tế. Đừng vội chạy `down -v` khi chưa xác định volume đang chứa dữ liệu nào.

### 14.7. Container báo “database files are incompatible with server”

**Nguyên nhân có thể gặp:** image phiên bản lớn khác với phiên bản đã dùng để tạo PGDATA.

**Cách xử lý:** dùng lại image đúng phiên bản lớn cũ để truy cập và backup dữ liệu, rồi xây dựng quá trình nâng cấp có kiểm soát; không xóa PGDATA để làm thông báo lỗi biến mất.

### 14.8. Số kết nối đã được healthcheck xác nhận nhưng ứng dụng vẫn lỗi

`pg_isready` chủ yếu báo tình trạng server chấp nhận kết nối, không xác minh đầy đủ mật khẩu, quyền truy cập hoặc schema. Cần thử kết nối thực bằng user/database/host/port tương ứng và xem log ứng dụng.

### 14.9. Container khởi động lại liên tục

Xem:

~~~bash
docker compose ps
docker compose logs --tail=150 db
~~~

Kiểm tra lỗi init SQL, quyền mount, cấu hình, phiên bản data directory, mức sử dụng RAM và đĩa. `restart: unless-stopped` giúp container thử khởi động lại sau lỗi nhưng **không tự sửa được nguyên nhân lỗi**.

## 15. Bảo mật cơ bản cho môi trường thực hành

Dù môi trường chỉ phục vụ học tập, nên có các thói quen sau:

- **Không công bố cổng database ra toàn bộ mạng** nếu không cần. Mapping `127.0.0.1:5433:5432` phù hợp với lab chạy trên host đơn lẻ.
- **Không dùng mật khẩu mẫu**, không đưa bí mật vào Git, và không xem `.env` là kho bí mật an toàn cho sản xuất.
- **Không cho ứng dụng thật dùng `POSTGRES_USER` bootstrap superuser.** Khi xây hệ thống thực tế, tạo role ứng dụng riêng với quyền trên schema/table phù hợp.
- **Không chạy lệnh xóa volume theo tên đoán mò.** Luôn xác minh đúng project và dữ liệu trước.
- **Không chạy container PostgreSQL lab để lưu dữ liệu sản xuất** mà chưa có chính sách sao lưu, giám sát, hardening và vận hành đầy đủ.
- **Không mount Docker socket hay cấp đặc quyền container không cần thiết** chỉ để truy cập database.

Nếu cần cho một máy khác truy cập PostgreSQL, phải thiết kế lại phạm vi mạng, firewall, xác thực, mã hóa kết nối và quyền của từng role; **không chỉ thay `127.0.0.1` bằng `0.0.0.0` rồi coi là cấu hình an toàn**.

## 16. Bài tập thực hành

Các bài tập dùng môi trường `postgres-lab` đã tạo ở trên. Những câu lệnh phá hủy volume chỉ được nêu để phân biệt; không thực hiện nếu bạn cần giữ dữ liệu.

### Bài 1. Hiểu lệnh Compose

Với `compose.yaml` ở phần 3, hãy cho biết:

1. Tên service PostgreSQL là gì?
2. Cổng truy cập từ máy host là bao nhiêu?
3. Bên trong container PostgreSQL dùng cổng nào?
4. Dữ liệu vật lý của PostgreSQL được gắn với named volume nào?

### Bài 2. Kiểm tra tính bền vững

Sau khi thêm một dòng vào `lab_entries`, bạn chạy:

~~~bash
docker compose down
docker compose up -d
~~~

Hỏi: dữ liệu có nên còn không? Vì sao? Điều kiện nào có thể khiến bạn nhìn thấy database trống dù volume cũ chưa bị xóa?

### Bài 3. Nhận diện lệnh phá hủy dữ liệu

So sánh:

~~~bash
docker compose down
docker compose down -v
~~~

Lệnh nào giữ named volume? Lệnh nào có thể xóa dữ liệu của PostgreSQL?

### Bài 4. Biến môi trường chỉ hoạt động lúc khởi tạo

Một người dùng đã khởi tạo database `lab_db`, rồi sửa `POSTGRES_DB=other_db` trong `.env` và chạy `docker compose restart`. Database `other_db` có tự được tạo không? Phương án đúng nếu muốn có thêm database mà vẫn giữ `lab_db` là gì?

### Bài 5. Kết nối từ container khác

Một ứng dụng Java chạy trong service `api` trên cùng Compose network, dùng JDBC URL `jdbc:postgresql://localhost:5433/lab_db` và báo lỗi. Hãy đề xuất URL phù hợp và giải thích lý do.

### Bài 6. Backup logic

Hãy nêu cách tạo file `lab_db.dump` bằng `pg_dump` trong container và sao chép file ra host. Tại sao không nên chỉ dựa vào named volume như một bản backup?

### Bài 7. Thay image lên phiên bản lớn mới

Một người đổi `postgres:16` thành `postgres:17` khi volume `pgdata` vẫn chứa cluster PostgreSQL 16. Tại sao server có thể từ chối khởi động? Nên làm gì trước khi nâng cấp?

### Bài 8. Healthcheck và mật khẩu

Container hiển thị `healthy` nhưng ứng dụng đăng nhập thất bại với mật khẩu mới sửa trong `.env`. Hai điểm nào cần kiểm tra về healthcheck và cơ chế bootstrap biến môi trường?

### Đáp án tham khảo

| Bài | Hướng giải |
| --- | --- |
| 1 | Service `db`, host port `5433`, container port `5432`, volume `pgdata` gắn với `/var/lib/postgresql/data` |
| 2 | Dữ liệu còn vì `down` không xóa named volume. Có thể đang dùng project name hoặc volume khác, hoặc kết nối nhầm database |
| 3 | `down` giữ named volume; `down -v` xóa named volume do project khai báo và có thể xóa dữ liệu |
| 4 | Không. Biến `POSTGRES_DB` chỉ tạo database trong bootstrap. Dùng `CREATE DATABASE other_db;` hoặc `createdb` trên cluster hiện tại |
| 5 | Dùng `jdbc:postgresql://db:5432/lab_db` vì service khác kết nối qua tên `db` và cổng nội bộ của container |
| 6 | Dùng `pg_dump -F c` tạo backup, `docker cp` đưa ra host; volume không có lịch sử backup và có thể mất/hỏng |
| 7 | PGDATA không được nâng phiên bản lớn chỉ bằng thay image. Giữ dữ liệu cũ, backup và làm dump/restore hoặc `pg_upgrade` theo quy trình tương thích |
| 8 | `pg_isready` không xác thực đầy đủ tài khoản; thay `POSTGRES_PASSWORD` sau bootstrap không đổi mật khẩu role trong PGDATA hiện hữu |

## 17. Danh sách lệnh thực hành nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Kiểm tra cấu hình | `docker compose config --quiet` |
| Tạo và chạy container | `docker compose up -d` |
| Xem trạng thái | `docker compose ps` |
| Xem log | `docker compose logs --tail=100 db` |
| Mở PostgreSQL CLI | `docker compose exec db psql -U lab_user -d lab_db` |
| Dừng mà vẫn giữ container | `docker compose stop` |
| Chạy lại container đã dừng | `docker compose start` |
| Xóa container/network nhưng giữ named volume | `docker compose down` |
| Tạo container mới vẫn dùng volume cũ | `docker compose up -d --force-recreate` |
| Xem danh sách volume Docker | `docker volume ls` |
| Xóa lab **kèm dữ liệu** | `docker compose down -v` — chỉ khi chủ động muốn hủy dữ liệu |

**Ghi nhớ:** Trong môi trường Docker Compose, **image** chứa phần mềm PostgreSQL, **container** là tiến trình đang chạy, còn **named volume** giữ dữ liệu bền vững khi container được tạo lại. Lựa chọn đúng đường mount cho phiên bản PostgreSQL, hiểu các biến bootstrap chỉ có hiệu lực ở lần khởi tạo đầu và tránh xóa volume ngoài ý muốn là ba nguyên tắc quan trọng nhất để có một môi trường thực hành PostgreSQL có thể dùng lại an toàn.
