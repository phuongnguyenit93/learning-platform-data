# Lưu dữ liệu bền vững, sao lưu cấu hình và tái tạo môi trường Oracle

Một môi trường Oracle dùng để học SQL, JDBC hoặc xây dựng ứng dụng Java thường trải qua nhiều lần dừng, khởi động lại, cập nhật mã nguồn và thậm chí xóa rồi tạo lại container. Nếu không thiết kế cách lưu trữ từ đầu, người học có thể mất toàn bộ bảng và dữ liệu chỉ vì chạy sai một lệnh Docker. Ngược lại, nếu chỉ giữ lại dữ liệu mà không ghi nhận phiên bản Oracle, cấu hình kết nối và những bước tạo schema, việc dựng lại môi trường trên máy khác vẫn dễ thất bại.

Bài này hướng dẫn tổ chức **môi trường thực hành Oracle có dữ liệu bền vững**, **sao lưu cả cấu hình lẫn dữ liệu** và **tái tạo có kiểm soát**. Ví dụ sử dụng Oracle Database Free trong Docker Compose, nhưng các nguyên tắc về tính nhất quán, bản sao lưu, phiên bản và khôi phục cũng áp dụng cho môi trường Oracle chạy trực tiếp trên máy hoặc máy ảo.

## 1. Phân biệt bốn việc thường bị gọi chung là “lưu dữ liệu”

| Việc cần làm | Mục tiêu | Ví dụ | Giới hạn |
|---|---|---|---|
| **Lưu dữ liệu bền vững (persistence)** | Giữ dữ liệu sau khi ứng dụng/container dừng hoặc được tạo lại | Gắn Docker named volume vào thư mục data của Oracle | Volume vẫn có thể hỏng hoặc bị xóa; **không phải bản sao lưu** |
| **Sao lưu dữ liệu (data backup)** | Có bản dữ liệu độc lập để phục hồi sau sự cố | Oracle RMAN, Data Pump, hoặc bản chụp volume *khi database đã dừng sạch* | Một số loại backup chỉ phục hồi được schema, không phải toàn bộ database |
| **Sao lưu cấu hình (configuration backup)** | Ghi lại chính xác cách môi trường được tạo và kết nối | `compose.yaml`, phiên bản image, SQL khởi tạo, cấu hình JDBC, tài liệu vận hành | Không khôi phục được dữ liệu nghiệp vụ đã phát sinh nếu không có data backup |
| **Tái tạo môi trường (reproducibility)** | Từ bộ cấu hình đã lưu, dựng lại một hệ thống có thể hoạt động và kiểm chứng được | Compose + image đã chốt phiên bản + SQL migration/seed + hướng dẫn phục hồi | Không đồng nghĩa với việc tự có lại dữ liệu mới nhất |

Ba tình huống cần được phân biệt:

1. **Restart:** dừng và chạy lại cùng môi trường; dữ liệu đã `COMMIT` phải còn.
2. **Recreate:** xóa container rồi tạo container khác dùng **cùng volume**; dữ liệu cũ vẫn phải còn nếu volume chưa bị xóa.
3. **Disaster recovery:** volume gốc đã mất hoặc hỏng; cần **backup độc lập** để khôi phục, ngoài việc tạo lại container.

> **Nguyên tắc:** Container có thể tạo lại, nhưng dữ liệu database cần có vòng đời riêng. Một volume giúp giữ trạng thái; một backup nằm ngoài volume đó mới tạo ra khả năng phục hồi khi volume bị mất.

## 2. Oracle ghi dữ liệu bền vững như thế nào?

Oracle xử lý truy vấn bằng **instance** (bộ nhớ và các tiến trình), còn dữ liệu được tổ chức trong **database** gồm các tệp cần thiết trên lưu trữ:

- **Datafiles:** lưu các segment chứa bảng, index và nhiều đối tượng khác.
- **Control files:** ghi nhận cấu trúc và trạng thái của database, thông tin datafile và redo.
- **Online redo logs:** ghi thông tin thay đổi để hỗ trợ phục hồi sau sự cố.
- **Archived redo logs:** bản lưu redo đã đầy, khi bật `ARCHIVELOG`; chúng đặc biệt quan trọng với những chiến lược backup và phục hồi theo thời điểm.

Khi giao dịch thực thi `COMMIT`, Oracle dùng cơ chế redo để đảm bảo khả năng phục hồi giao dịch theo cấu hình thông thường. Các thay đổi không nhất thiết được ghi ngay vào datafile tại thời điểm `COMMIT`: redo đóng vai trò thiết yếu nếu instance đột ngột dừng. Không nên thay thế cơ chế này bằng cách tự chép những tệp Oracle đang mở.

Ví dụ:

~~~sql
INSERT INTO lab_notes (note_id, note_text)
VALUES (99, 'Ghi chú phải tồn tại sau khi khởi động lại');

COMMIT;
~~~

Sau khi restart thành công, dòng đã commit phải còn, miễn là database và storage không bị hỏng và không có thao tác xóa/khôi phục đè dữ liệu. Ngược lại, một giao dịch **chưa commit** có thể được rollback khi phiên mất kết nối hoặc instance phục hồi.

Trong kiến trúc multitenant, dữ liệu ứng dụng thường nằm trong **PDB** (ví dụ `FREEPDB1`) thuộc một **CDB**. PDB không có nghĩa là phải tự gắn một Docker volume riêng. Với ví dụ bên dưới, volume lưu bộ tệp database mà Oracle Free tạo ra; các PDB bên trong được phục vụ từ bộ lưu trữ đó.

## 3. Vì sao lưu dữ liệu trong container là chưa đủ?

Container có **lớp ghi riêng**. Những thay đổi chỉ nằm trong lớp ghi có thể mất khi container bị xóa và được tạo lại từ image. Docker cung cấp **volume** hoặc **bind mount** để lưu dữ liệu ngoài vòng đời của container.

~~~text
Máy người học
│
├── compose.yaml, .env, sql/       Cấu hình và scripts
│
└── Docker Engine
    │
    ├── Oracle container          Có thể dừng / xóa / tạo lại
    │   ├── Oracle instance        Bộ nhớ + tiến trình đang chạy
    │   └── /opt/oracle/oradata ───────────┐
    │                                     │ gắn volume
    └── Docker named volume               ▼
        oracle_lab_data             Các tệp database
                                     tồn tại ngoài container
~~~

Đối với image minh họa `gvenzl/oracle-free:23-slim`, thư mục lưu trữ database được gắn tại `/opt/oracle/oradata`. **Đường dẫn này phụ thuộc image**: khi dùng image Oracle khác, phải tham chiếu đúng tài liệu của image đó trước khi gắn volume. Gắn sai thư mục có thể khiến database mới được khởi tạo mỗi lần tạo container.

### Named volume và bind mount

| Cơ chế | Dùng cho | Đặc điểm cần nhớ |
|---|---|---|
| **Named volume** | Datafiles, redo, control file của môi trường lab | Docker quản lý đường dẫn và quyền; thường thuận tiện cho dữ liệu Oracle trong container |
| **Bind mount** | Scripts, cấu hình, thư mục nhận file backup/export | Người dùng nhìn thấy ngay các tệp trên host; cần lưu ý quyền truy cập và hiệu năng I/O |
| **Lớp ghi container** | Nội dung tạm thời không cần giữ | Mất khi container bị xóa; không nên đặt dữ liệu database cần bảo toàn ở đây |

Nếu chạy Docker Desktop trên Windows/macOS, named volume thường tránh được một số vấn đề hiệu năng và quyền khi đặt các file database trực tiếp trên thư mục được chia sẻ từ host. Tuy nhiên, **volume không tự đồng bộ lên Git hoặc cloud**.

## 4. Dựng Oracle thực hành với Docker Compose

Ví dụ này dùng Docker Compose v2 và image cộng đồng `gvenzl/oracle-free`, phục vụ mục đích thực hành. Cần Docker Engine/Docker Desktop, đủ RAM và dung lượng đĩa cho Oracle. Trong môi trường dùng lâu dài, nên **chốt phiên bản cụ thể hoặc image digest đã kiểm tra** thay vì để một tag chuyển động thay đổi ngoài ý muốn.

### 4.1. Cấu trúc dự án

~~~text
oracle-lab/
├── compose.yaml
├── .env.example
├── .env                      Không commit; chứa mật khẩu thật
├── .gitignore
├── sql/
│   └── 001_schema_and_seed.sql
├── backups/                  Bản sao lưu đặt ngoài volume database
└── README.md                 Cách chạy, kết nối, backup, restore
~~~

Thư mục `backups/` chỉ là một điểm nhận file trên máy; muốn chống mất máy hoặc mất đĩa thì cần sao chép backup sang nơi lưu trữ độc lập, được bảo vệ và kiểm tra khôi phục.

### 4.2. Tệp `compose.yaml`

~~~yaml
name: oracle-lab

services:
  db:
    image: gvenzl/oracle-free:23-slim
    ports:
      - "127.0.0.1:1521:1521"
    environment:
      ORACLE_PASSWORD: "${ORACLE_PASSWORD:?Set ORACLE_PASSWORD in .env}"
      APP_USER: LAB_APP
      APP_USER_PASSWORD: "${APP_USER_PASSWORD:?Set APP_USER_PASSWORD in .env}"
    volumes:
      - oracle_data:/opt/oracle/oradata
    stop_grace_period: 3m

volumes:
  oracle_data:
    name: oracle_lab_data
~~~

Giải thích:

- `db` là tên service Compose. Trong mạng nội bộ Compose, ứng dụng ở container khác có thể sử dụng host `db`.
- Cổng `1521` được công bố tại `127.0.0.1` của host để lab có thể kết nối từ máy đang chạy Docker; mặc định không mở ra mọi giao diện mạng.
- `ORACLE_PASSWORD` được cung cấp khi khởi tạo database theo quy ước image này; `APP_USER` và `APP_USER_PASSWORD` thiết lập user thử nghiệm ở lần khởi tạo đầu.
- `oracle_data` ánh xạ đến named volume **`oracle_lab_data`**, một tên cố định để dễ nhận biết và sao lưu.
- `stop_grace_period` cho Oracle thêm thời gian kết thúc trước khi Docker buộc phải dừng container. Với backup kiểu cold copy, vẫn cần xác nhận database đã dừng sạch.

Giá trị trong khối `environment` là **cú pháp riêng của image minh họa**; không mặc định áp dụng cho tất cả Oracle images. Khi dữ liệu đã được khởi tạo trong volume, thay đổi biến mật khẩu trong `.env` **không tự động đổi mật khẩu user nằm trong database**.

### 4.3. Tệp `.env.example` và `.gitignore`

~~~dotenv
# .env.example - chỉ là mẫu, không chứa mật khẩu thật
ORACLE_PASSWORD=replace-with-a-strong-admin-password
APP_USER_PASSWORD=replace-with-a-strong-app-password
~~~

~~~gitignore
# Không lưu bí mật hoặc bản backup vào repository mã nguồn
.env
backups/
*.dmp
*.bak
~~~

Tạo `.env` từ mẫu và thay hai giá trị bằng mật khẩu riêng của môi trường lab. Trên PowerShell:

~~~powershell
Copy-Item .env.example .env
# Mở .env bằng trình sửa văn bản và thay các giá trị mẫu
docker compose up -d
docker compose ps
docker compose logs -f db
~~~

Khởi tạo Oracle lần đầu có thể mất một khoảng thời gian. Chỉ kết nối sau khi log/health của image cho thấy database đã sẵn sàng. Để thoát chế độ xem log, nhấn `Ctrl+C`; lệnh này không đồng nghĩa với việc xóa volume.

### 4.4. Kết nối đến đúng PDB

Với image và cấu hình minh họa, service PDB mặc định là `FREEPDB1`; cần kiểm tra service thực tế nếu dùng phiên bản/image khác.

| Nơi chạy ứng dụng | Host | Port | Service | Ví dụ JDBC Thin |
|---|---|---|---|---|
| Java trên **host** | `localhost` | `1521` | `FREEPDB1` | `jdbc:oracle:thin:@//localhost:1521/FREEPDB1` |
| Java trong **cùng mạng Compose** | `db` | `1521` | `FREEPDB1` | `jdbc:oracle:thin:@//db:1521/FREEPDB1` |

User ứng dụng là `LAB_APP`, mật khẩu là `APP_USER_PASSWORD` đã dùng khi khởi tạo. Với ứng dụng Java/Spring Boot, lấy mật khẩu từ biến môi trường hoặc bộ quản lý secrets:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//localhost:1521/FREEPDB1
spring.datasource.username=LAB_APP
spring.datasource.password=${DB_APP_PASSWORD}
~~~

Ở đây `DB_APP_PASSWORD` là biến môi trường của **ứng dụng Java**; cần cấp giá trị phù hợp với mật khẩu user `LAB_APP`, không có sự tự động đồng bộ giữa biến của Java và `.env` do Compose dùng.

## 5. Khởi tạo schema và dữ liệu mẫu có thể chạy lại

Để tái tạo môi trường, ngoài container và volume còn cần **lược đồ dữ liệu**: bảng, index, constraint, dữ liệu khởi đầu và thứ tự thay đổi schema. Với một bài lab nhỏ, có thể lưu SQL trong `sql/`. Với ứng dụng thật, nên quản lý migration có version bằng công cụ như Flyway hoặc Liquibase.

Tệp `sql/001_schema_and_seed.sql` dưới đây có thể chạy lại mà không tạo thêm bảng hoặc bản ghi mẫu trùng lặp:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE

-- Đăng nhập bằng LAB_APP ở PDB FREEPDB1 trước khi chạy.
DECLARE
    v_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM user_tables
    WHERE table_name = 'LAB_NOTES';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE lab_notes (
                note_id    NUMBER(10) PRIMARY KEY,
                note_text  VARCHAR2(200) NOT NULL,
                created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )';
    END IF;
END;
/

MERGE INTO lab_notes t
USING (
    SELECT 1 AS note_id,
           'Ban ghi khoi tao' AS note_text
    FROM dual
) s
ON (t.note_id = s.note_id)
WHEN NOT MATCHED THEN
    INSERT (note_id, note_text)
    VALUES (s.note_id, s.note_text);

COMMIT;

SELECT note_id, note_text, created_at
FROM lab_notes
ORDER BY note_id;
~~~

Chạy trên container (PowerShell ở thư mục dự án):

~~~powershell
docker cp .\sql\001_schema_and_seed.sql "$(docker compose ps -q db):/tmp/001_schema_and_seed.sql"
docker compose exec db sqlplus -L lab_app@//localhost:1521/FREEPDB1
~~~

SQL*Plus sẽ yêu cầu mật khẩu của `LAB_APP`. Khi hiện lời nhắc `SQL>`, gõ:

~~~sql
@/tmp/001_schema_and_seed.sql
~~~

Nếu đang sử dụng SQL Developer hoặc SQLcl trên máy, bạn cũng có thể kết nối trực tiếp tới `localhost:1521/FREEPDB1` bằng `LAB_APP` và chạy nội dung SQL mà không cần `docker cp`.

**Lưu ý về tính lặp lại:** `MERGE` giúp phần dữ liệu mẫu không bị chèn trùng và `CREATE TABLE` chỉ chạy khi chưa có bảng. Với schema thay đổi qua nhiều phiên bản, không nên chỉ dùng thủ thuật “nếu chưa tồn tại thì tạo” để thay thế hệ thống migration; phải có thứ tự, version và cách xử lý những thay đổi cột/index phức tạp.

## 6. Thử độ bền của dữ liệu sau restart và recreate

Kết nối vào `LAB_APP` và tạo một dòng dữ liệu **không nằm trong file seed**:

~~~sql
INSERT INTO lab_notes (note_id, note_text)
VALUES (99, 'Dong du lieu tao trong luc thuc hanh');

COMMIT;

SELECT note_id, note_text
FROM lab_notes
WHERE note_id = 99;
~~~

Sau đó thoát SQL*Plus và chạy:

~~~powershell
# Trường hợp 1: dừng và khởi động lại service hiện có
docker compose stop db
docker compose start db

# Trường hợp 2: hủy container và mạng Compose rồi tạo container lại
# (không dùng tùy chọn -v)
docker compose down
docker compose up -d
~~~

Đợi Oracle mở xong rồi đăng nhập lại; kết quả của truy vấn `WHERE note_id = 99` phải còn. Điều này chứng minh datafiles trong named volume vẫn được sử dụng sau vòng đời container.

Kiểm tra tên và trạng thái volume:

~~~powershell
docker volume inspect oracle_lab_data
~~~

So sánh các thao tác:

| Lệnh | Container | Named volume thông thường |
|---|---|---|
| `docker compose stop` | Dừng, còn metadata/container | Giữ |
| `docker compose start` | Chạy lại container đã có | Dùng lại |
| `docker compose down` | Xóa container và mạng Compose | **Giữ**, nếu không kèm `-v` |
| `docker compose up -d` | Dùng/tạo container theo cấu hình | Gắn lại volume được khai báo |
| `docker compose down -v` | Xóa container và volume do Compose quản lý | **Có thể xóa vĩnh viễn dữ liệu lab** |
| `docker volume rm oracle_lab_data` | Không nhất thiết đụng container đã xóa | **Xóa volume** khi Docker cho phép |

Không dùng `down -v` hoặc xóa volume chỉ để “làm mới container” nếu vẫn cần dữ liệu. Trước khi cố ý reset môi trường, phải xác định rõ đang cần **tạo database trống** hay **phục hồi database cũ**.

## 7. Sao lưu dữ liệu: chọn đúng phạm vi và mức nhất quán

Ba cách sao lưu phổ biến phục vụ nhu cầu khác nhau:

| Cách sao lưu | Lưu được gì? | Khi nào dùng? | Lưu ý |
|---|---|---|---|
| **Cold backup** sau khi Oracle dừng sạch | Bộ tệp database trong phạm vi được sao chép | Lab cá nhân, snapshot trước thay đổi lớn, chuyển nguyên trạng sang môi trường tương thích | Phải dừng database đúng cách và giữ đủ các tệp liên quan; không chép nóng tùy tiện |
| **Data Pump** (`expdp`/`impdp`) | Dữ liệu và metadata logic theo phạm vi schema/table/PDB phù hợp | Chuyển dữ liệu bài tập, lưu một schema, nhập dữ liệu sang database khác | Không thay thế backup vật lý đầy đủ của CDB, redo, control file hay cấu hình instance |
| **RMAN** | Backup vật lý có nhận thức Oracle, hỗ trợ quy trình khôi phục nâng cao | Môi trường cần backup online, retention và phục hồi nghiêm túc | Phải thiết kế nơi lưu backup, archivelog, quyền, retention và thử restore |

### 7.1. Cold backup cho lab bằng named volume

Trong ví dụ này, **không** tar trực tiếp volume trong lúc Oracle đang ghi dữ liệu. Ta tắt Oracle sạch trước, dừng container, rồi sao chép volume sang file archive ở ngoài volume database.

**Bước 1 — kết thúc hoạt động database có kiểm soát.** Đảm bảo không còn bài tập hoặc ứng dụng đang chạy giao dịch cần hoàn tất. Có thể kết nối bằng quyền quản trị OS trong container và yêu cầu Oracle shutdown:

~~~powershell
docker compose exec -u oracle db bash -lc 'printf "shutdown immediate;\nexit;\n" | sqlplus -s "/ as sysdba"'
~~~

Chỉ tiếp tục nếu lệnh shutdown hoàn tất thành công. Nếu image hoặc quyền OS khác đi, cần dùng cách shutdown do image đó hỗ trợ. Một lần Docker ép dừng do timeout hoặc kill tiến trình **không được coi là đã shutdown sạch**.

**Bước 2 — dừng container và tạo thư mục backup trên host.**

~~~powershell
docker compose stop -t 180 db
New-Item -ItemType Directory -Force .\backups\cold | Out-Null
~~~

**Bước 3 — tạo archive từ volume bằng container phụ.**

~~~powershell
docker run --rm --mount "type=volume,src=oracle_lab_data,dst=/source,readonly" --mount "type=bind,src=$((Resolve-Path .\backups\cold).Path),dst=/backup" alpine:3.20 tar -czf /backup/oracle_lab_data.tar.gz -C /source .
~~~

Lệnh dùng volume ở chế độ chỉ đọc, ghi file `backups/cold/oracle_lab_data.tar.gz` tại host. Trên Linux/macOS, có thể thay biểu thức đường dẫn PowerShell `$((Resolve-Path ...).Path)` bằng đường dẫn tuyệt đối của thư mục backup trên host.

**Bước 4 — tạo checksum và đưa Oracle hoạt động trở lại.**

~~~powershell
(Get-FileHash .\backups\cold\oracle_lab_data.tar.gz -Algorithm SHA256).Hash | Set-Content .\backups\cold\oracle_lab_data.tar.gz.sha256
docker compose up -d db
~~~

Nên ghi cùng bản backup các thông tin: thời điểm, image/tag **và digest** đang dùng, tên CDB/PDB, loại backup, trạng thái shutdown, dung lượng archive, checksum SHA-256 và cách restore. Archive phải được giữ ngoài volume gốc; một bản chỉ nằm trên cùng ổ đĩa với volume vẫn có thể mất khi ổ đĩa hỏng.

> **Giới hạn của ví dụ:** Đây là bản sao lưu tệp sau khi đã đóng database và phù hợp nhất cho một lab một container với volume lưu đầy đủ các file Oracle cần thiết. Nếu hệ thống dùng nhiều volume, tệp nằm ngoài thư mục gắn volume, ASM, RAC hoặc cấu hình lưu trữ khác, việc chỉ archive một volume có thể **không đầy đủ**. Khi cần backup nóng hoặc phục hồi theo thời điểm, hãy dùng phương pháp Oracle hỗ trợ như RMAN.

### 7.2. Data Pump: sao lưu logic một schema

Khi chỉ cần mang bảng, dữ liệu và metadata của `LAB_APP` sang môi trường khác, **Oracle Data Pump** là một lựa chọn. Một lệnh export ở mức ý tưởng:

~~~text
expdp lab_app@//localhost:1521/FREEPDB1 \
  schemas=LAB_APP \
  directory=LAB_DUMP_DIR \
  dumpfile=lab_app_01.dmp \
  logfile=lab_app_01.log
~~~

Trước khi chạy, DBA phải tạo một **Oracle DIRECTORY object** (ví dụ `LAB_DUMP_DIR`), trỏ tới thư mục hệ điều hành mà tiến trình Oracle có quyền ghi và cấp quyền `READ`/`WRITE` cần thiết cho user export. `directory=LAB_DUMP_DIR` là tên **database object**, không phải đường dẫn được truyền tùy ý từ máy client. File `.dmp` được ghi **trên phía server Oracle**; sau khi export phải chép nó ra nơi backup độc lập và giữ kèm log, version/tham số export. Trong một số cấu hình, phạm vi export hoặc import cần quyền cao hơn user ứng dụng.

Khi nhập bằng `impdp`, cần cân nhắc user/schema đích, tablespace, quyền, sự tương thích phiên bản và các object đã có. **Không** xem Data Pump của một schema là bản thay thế cho backup đầy đủ của CDB.

### 7.3. RMAN: khi cần phục hồi bài bản

**Recovery Manager (RMAN)** là công cụ backup/restore vật lý do Oracle cung cấp. Nó có thể quản lý backup của database và archivelog, hỗ trợ kiểm tra và quy trình phục hồi theo thiết kế. Ví dụ một lệnh RMAN thường gặp trong chiến lược có archivelog:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Đây là ví dụ ngữ nghĩa, **không phải** một cấu hình backup hoàn chỉnh. Trước khi chạy trong môi trường thật cần xác định database đang ở chế độ nào, vị trí chứa backup, dung lượng, quyền, chính sách giữ bản backup, trạng thái archivelog và thao tác phục hồi đã thử nghiệm. Trên lab đơn giản, cold backup có thể dễ hiểu hơn; trong hệ thống phải hoạt động liên tục, cần đánh giá RMAN.

## 8. Sao lưu cấu hình: những gì phải nằm trong “bộ tái tạo”

Một bản backup chỉ có các tệp database mà thiếu thông tin cách tạo môi trường có thể khiến người khôi phục mất nhiều thời gian dò phiên bản, tài khoản và endpoint. Hãy tạo một bộ cấu hình có thể kiểm soát phiên bản:

~~~text
oracle-lab/
├── compose.yaml                  Dịch vụ, volume, port, image
├── .env.example                  Danh sách biến cần cung cấp
├── sql/
│   ├── 001_schema_and_seed.sql
│   └── ...                       Migration/seed sau này
├── app-config.example            URL JDBC và tên biến env
├── README.md                     Cài đặt, chạy, reset, backup, restore
└── backup-manifest.txt           Phiên bản, thời điểm và checksum của bản backup
~~~

Các nội dung nên được ghi rõ:

- **Phiên bản phần mềm:** image Oracle cụ thể và digest; phiên bản Docker/Compose liên quan; nếu có ứng dụng Java, ghi phiên bản Java, JDBC driver và schema migration.
- **Cấu hình dịch vụ:** service name/PDB, cổng, mạng Docker, volume mount, giới hạn tài nguyên và các tùy chọn listener/Oracle Net do bạn chỉnh.
- **Cấu hình dữ liệu:** SQL tạo bảng, constraint, index, user/quyền cần thiết và dữ liệu seed; nếu có migration, ghi version đã áp dụng.
- **Bí mật:** *tên* biến cần cấp (`ORACLE_PASSWORD`, `APP_USER_PASSWORD`...), nơi cất secrets được kiểm soát và cách cấp chúng. Không đẩy giá trị thật vào repository, log hoặc ảnh chụp màn hình.
- **Thao tác vận hành:** lệnh start/stop, cách kiểm tra readiness, lưu backup, kiểm tra checksum, phục hồi, kiểm chứng dữ liệu và cảnh báo trước thao tác xóa volume.

**Chốt image bằng digest** giúp bản mô tả có thể tái tạo tốt hơn vì tag `23-slim` có thể được cập nhật. Digest cụ thể phụ thuộc image mà nhóm thực sự đã pull và kiểm thử; ghi lại nó cùng backup và dùng đúng image tương thích khi khôi phục. Không nâng version database bằng cách tự ý thay image rồi gắn nguyên một volume data của bản trước, trừ khi đã chuẩn bị quy trình nâng cấp được Oracle/image hỗ trợ.

`.env.example` có thể commit vì chỉ chứa chỗ trống/giá trị giả. **`.env` thực tế** cần được bảo vệ; nếu cần sao lưu để phục hồi, phải sao lưu mã hóa và kiểm soát quyền truy cập, tránh để mật khẩu admin trong Git.

## 9. Tái tạo môi trường: hai đường đi khác nhau

Có hai mục tiêu nghiệp vụ khác nhau, dẫn đến hai quy trình khác nhau:

~~~text
                    Đã lưu compose + SQL + image version?
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
        Tạo môi trường mới, sạch               Khôi phục dữ liệu đã có
                    │                                   │
          Khởi động DB trên volume mới            Lấy bản backup độc lập
                    │                                   │
         Chạy migration + dữ liệu seed         Phục hồi vào volume/DB đích
                    │                                   │
         Có schema và dữ liệu mẫu               Có trạng thái dữ liệu lúc backup
                    └─────────────────┬─────────────────┘
                                      ▼
                        Kết nối, kiểm tra schema,
                        dữ liệu và luồng ứng dụng
~~~

### 9.1. Tạo mới hoàn toàn từ cấu hình

Quy trình:

1. Lấy đúng repository cấu hình, xem `README.md` và cài image/phiên bản được chỉ định.
2. Cung cấp các biến bí mật bằng nguồn an toàn, không lấy mật khẩu từ repository.
3. Tạo **volume trống mới** và chạy `docker compose up -d`.
4. Chờ Oracle sẵn sàng, xác nhận PDB `FREEPDB1` và đăng nhập user ứng dụng.
5. Chạy migration/SQL seed theo đúng thứ tự.
6. Kiểm tra cấu trúc bảng, số dòng mẫu, URL kết nối JDBC và một thao tác đọc/ghi của ứng dụng.

Kết quả là **một môi trường cùng cấu trúc**, nhưng không có dữ liệu mới phát sinh trước đó. Bản tái tạo này phù hợp để onboarding hoặc chạy bài tập tự động từ trạng thái ban đầu.

### 9.2. Khôi phục cold backup vào volume **khác** để không đụng dữ liệu gốc

Thử restore trên một volume mới an toàn hơn so với ghi đè trực tiếp volume đang dùng. Giả sử đã có file `backups/cold/oracle_lab_data.tar.gz` từ bước 7, và image khôi phục tương thích với image tạo backup.

**Bước 1 — kiểm tra archive và checksum đã lưu:**

~~~powershell
$expected = (Get-Content .\backups\cold\oracle_lab_data.tar.gz.sha256).Trim()
$actual = (Get-FileHash .\backups\cold\oracle_lab_data.tar.gz -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "Backup checksum mismatch" }
~~~

**Bước 2 — tạo volume khôi phục hoàn toàn mới:**

~~~powershell
docker volume create oracle_lab_restore_data
~~~

**Bước 3 — giải nén vào volume khôi phục đang trống:**

~~~powershell
docker run --rm --mount "type=volume,src=oracle_lab_restore_data,dst=/target" --mount "type=bind,src=$((Resolve-Path .\backups\cold).Path),dst=/backup,readonly" alpine:3.20 sh -c 'test -z "$(ls -A /target)" && tar -xzf /backup/oracle_lab_data.tar.gz -C /target'
~~~

Điều kiện `test -z "$(ls -A /target)"` yêu cầu volume đích trống, tránh giải nén đè lên một database có sẵn. Không dùng volume gốc `oracle_lab_data` làm đích thử nghiệm.

**Bước 4 — chạy một Compose project riêng cho bản restore:**

Tạo `compose.restore.yaml` (dùng cùng image/digest tương thích đã được ghi trong manifest):

~~~yaml
name: oracle-lab-restore

services:
  db:
    image: gvenzl/oracle-free:23-slim
    ports:
      - "127.0.0.1:1522:1521"
    environment:
      ORACLE_PASSWORD: "${ORACLE_PASSWORD:?Set ORACLE_PASSWORD in .env}"
    volumes:
      - restored_data:/opt/oracle/oradata
    stop_grace_period: 3m

volumes:
  restored_data:
    external: true
    name: oracle_lab_restore_data
~~~

~~~powershell
docker compose -f compose.restore.yaml up -d
docker compose -f compose.restore.yaml ps
docker compose -f compose.restore.yaml logs -f db
~~~

Trong ví dụ, port `1522` trên host được chuyển tới port `1521` trong container restore, giúp chạy song song với môi trường lab gốc trên port `1521`. Đăng nhập bằng **mật khẩu của bản database tại thời điểm backup**: biến `ORACLE_PASSWORD` của Compose không đặt lại mật khẩu đã lưu sẵn trong volume.

Từ host, dùng:

~~~text
jdbc:oracle:thin:@//localhost:1522/FREEPDB1
~~~

Rồi kiểm tra dữ liệu đã commit trước thời điểm backup:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS pdb_name
FROM dual;

SELECT note_id, note_text
FROM lab_notes
WHERE note_id = 99;
~~~

Kết quả của dòng `99` phụ thuộc **thời điểm tạo backup**: có trong bản backup nếu dòng được commit trước snapshot; các thay đổi phát sinh sau snapshot không tự xuất hiện khi restore. Nếu muốn dùng chính bản restore làm database chính, cần lên kế hoạch đổi endpoint/service, xử lý xung đột dữ liệu và ngừng ứng dụng ghi trên nguồn cũ theo quy trình phù hợp.

## 10. Kiểm chứng bản backup có thực sự dùng được

Một file `.tar.gz` hoặc `.dmp` tồn tại trên ổ đĩa chỉ xác nhận có file, chưa chứng minh khả năng phục hồi. Bài lab có thể thực hành một lần phục hồi độc lập theo các tiêu chí:

1. **Archive toàn vẹn:** kích thước và SHA-256 khớp với manifest; file đọc được từ nơi lưu backup.
2. **Môi trường tương thích:** image Oracle, cấu trúc volume, cấu hình PDB và tài nguyên cần thiết đã được ghi lại.
3. **Database khởi động:** instance và PDB mở thành công, listener/service phục vụ kết nối.
4. **Đúng dữ liệu:** một số dòng mẫu đã biết, khóa chính/index, schema owner và các truy vấn cơ bản hoạt động.
5. **Ứng dụng kết nối:** JDBC dùng đúng host, port, service và user; một câu `SELECT` thành công, và nếu phù hợp có thể thử ghi/rollback giao dịch.
6. **Bí mật được bảo vệ:** mật khẩu không bị in vào Git/log backup và có thể được lấy qua quy trình được phép.

Nên lưu ngày thử restore gần nhất cùng manifest. Với dự án thực tế, đặt lịch thử restore định kỳ và lưu backup ở vị trí độc lập với nơi chạy database. Nhiều bản backup theo thời gian cũng giúp phát hiện sự cố xảy ra trước khi bản gần nhất được tạo.

### RPO và RTO ở mức nhập môn

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian. Nếu chỉ backup lạnh vào tối Chủ nhật và mất volume tối Thứ Ba, bạn có thể mất dữ liệu phát sinh từ sau bản backup.
- **RTO (Recovery Time Objective):** phải phục hồi hệ thống trong bao lâu. Một bản archive rất lớn, tải chậm hoặc thiếu mật khẩu/image tương thích sẽ làm thời gian khôi phục tăng lên.

Các chỉ số này giúp quyết định nên sao lưu mỗi ngày/tuần, dùng Data Pump hay RMAN và cần giữ bao nhiêu bản. Đối với bài thực hành cá nhân, mục tiêu có thể đơn giản; vẫn nên hiểu rằng **persistence không quyết định RPO/RTO**.

## 11. Những lỗi thường gặp và cách phân biệt

| Biểu hiện | Khả năng thường gặp | Điều cần kiểm tra |
|---|---|---|
| Tạo lại container nhưng mất bảng | Không gắn volume đúng thư mục; vô tình chạy `down -v`; dùng tên volume/project khác | `compose.yaml`, mount của container, `docker volume ls` |
| Đổi `APP_USER_PASSWORD` trong `.env` nhưng không đăng nhập được | User đã được tạo ở lần khởi tạo volume đầu tiên | Password đang lưu trong database; muốn đổi phải dùng câu lệnh quản trị thích hợp |
| Restore archive rồi Oracle không mở được | Archive không nhất quán/thiếu file; image không tương thích; quyền file hoặc dung lượng | Cách shutdown khi backup, manifest, log Oracle, bộ file khôi phục |
| Khôi phục thành công nhưng không thấy dòng vừa thêm | Dòng được thêm **sau thời điểm backup** hoặc chưa `COMMIT` | Thời điểm backup và transaction; RPO |
| Kết nối tới `localhost:1521` từ container Java khác bị từ chối | `localhost` trong container Java là chính container đó | Dùng hostname service Compose `db` và service `FREEPDB1` |
| Đăng nhập được nhưng không thấy bảng | Kết nối nhầm PDB/service hoặc user/schema; thiếu quyền | `SYS_CONTEXT('USERENV','CON_NAME')`, `CURRENT_SCHEMA`, chủ sở hữu bảng |
| Có file `.dmp` nhưng chưa thể import | Thiếu DIRECTORY object/quyền, file nằm sai chỗ hoặc khác version | Đường dẫn trên server, quyền READ/WRITE, log expdp/impdp |
| Sao lưu `compose.yaml` mà không khôi phục được dữ liệu cũ | Chỉ lưu cấu hình, chưa có data backup | Bộ backup của datafiles/RMAN/Data Pump và điểm khôi phục mong muốn |

## 12. Bài tập thực hành

### Bài tập 1 — Kiểm tra persistence

Tạo bảng `LAB_NOTES`, commit một dòng có `note_id = 99`, chạy `docker compose down` rồi `docker compose up -d`. Kết nối lại, xác nhận dòng 99 vẫn tồn tại. Giải thích tại sao datafile không mất dù container đã được tạo lại.

**Gợi ý:** so sánh vòng đời container với vòng đời named volume `oracle_lab_data`; không dùng `down -v`.

### Bài tập 2 — Khôi phục điểm thời gian

Sau khi ghi dòng 99, tạo cold backup. Sau khi Oracle chạy lại, ghi thêm dòng `note_id = 100` rồi commit. Khôi phục archive lên volume mới `oracle_lab_restore_data`. Truy vấn cả hai dòng ở database restore.

**Kết quả mong đợi:** dòng 99 có trong bản restore; dòng 100 không có nếu nó được commit sau khi backup. Đây là minh họa trực quan cho **RPO**.

### Bài tập 3 — Chuyển sang máy khác

Giả sử bạn chỉ được đem theo bộ file cấu hình, scripts SQL, bản archive và thông tin bí mật qua kênh được phép. Hãy xác định trình tự để dựng lại Oracle ở máy mới, đổi cổng host nếu `1521` đã được ứng dụng khác sử dụng, rồi kết nối JDBC và xác nhận dữ liệu.

**Gợi ý:** đừng mặc định container name/IP giống máy cũ. Đích kết nối được xác định bởi hostname/port trên máy mới và service name của Oracle; dữ liệu được lấy từ bản backup, không phải từ file Compose.

### Bài tập 4 — Chọn loại backup

Bạn có ba yêu cầu: (a) chỉ chuyển bảng của schema `LAB_APP`; (b) khôi phục toàn bộ lab sau khi mất volume; (c) backup một hệ thống vẫn phải phục vụ người dùng và có yêu cầu phục hồi theo thời điểm. Chọn Data Pump, cold backup hoặc RMAN thích hợp, nêu thêm điều kiện để cách đó có hiệu lực.

**Định hướng:** (a) Data Pump; (b) cold backup nhất quán và đủ file cho lab; (c) RMAN trong chiến lược archive/retention/restore đã thiết kế. Mỗi loại giải quyết một phạm vi khác nhau.

## Kết luận

Một môi trường Oracle thực hành có thể tái tạo đáng tin cậy cần **ba lớp song hành**: volume để giữ dữ liệu sau vòng đời container, **backup độc lập và nhất quán** để phục hồi sau mất mát, và **cấu hình cùng SQL có version** để dựng lại môi trường đúng cách. Hãy tập thói quen ghi nhớ phiên bản image, PDB/service, đường dẫn volume, nơi chứa backup, cách giữ secrets và quy trình thử restore. Khi đó, việc khởi động lại, đổi máy hoặc làm mới bài tập sẽ là một thao tác có kiểm soát thay vì một lần đánh cược với dữ liệu.
