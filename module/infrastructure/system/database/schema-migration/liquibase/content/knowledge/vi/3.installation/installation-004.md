# Chạy Liquibase với Docker và gắn thư mục changelog

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi cài đặt bằng Docker, nhóm phát triển có thể chạy Liquibase trong một container dùng phiên bản công cụ đã chọn, trong khi mã changelog vẫn nằm trong repository trên máy chủ hoặc trong workspace của pipeline.

Bài này hướng dẫn cách chuẩn bị Docker, lấy image Liquibase, gắn thư mục changelog từ máy host vào container, kết nối tới cơ sở dữ liệu, chạy các lệnh kiểm tra và triển khai, rồi tổ chức cấu hình bằng Docker Compose. Trọng tâm là làm cho đường dẫn file, mạng và thông tin kết nối rõ ràng để cùng một bộ migration có thể được dùng trong môi trường phát triển và CI/CD.

Sau khi hoàn thành, người học có thể:

- Chọn và cố định phiên bản image Liquibase phù hợp với dự án.
- Ánh xạ thư mục changelog trên host vào một đường dẫn xác định trong container.
- Bảo đảm master changelog, các file include, SQL và dữ liệu tham chiếu đều có mặt trong container.
- Kết nối Liquibase container tới database container hoặc database bên ngoài.
- Chạy validate, status, update-sql và update có kiểm soát.
- Phân biệt bind mount với named volume, xử lý quyền đọc file và tránh để lộ thông tin xác thực.

## 2. Vì sao chạy Liquibase trong container?

Liquibase là công cụ Java. Nếu cài trực tiếp trên mọi máy phát triển, nhóm phải đồng bộ phiên bản Java, Liquibase CLI và JDBC driver. Container đóng gói runtime cùng phiên bản công cụ, nhờ đó lệnh chạy trong máy cá nhân và pipeline có thể nhất quán hơn.

Một mô hình phổ biến gồm ba thành phần:

1. **Repository** chứa changelog và các file liên quan như SQL, CSV hoặc file cấu hình.
2. **Liquibase container** đọc changelog từ thư mục được mount và kết nối database qua JDBC.
3. **Database** chạy trong container riêng hoặc được cung cấp bởi một máy chủ dịch vụ.

Liquibase container thường là container chạy một lần: nó thực hiện validate, tạo SQL dự kiến hoặc update rồi kết thúc. Database có vòng đời riêng và lưu dữ liệu trong volume của database. Thư mục changelog là mã nguồn cần được quản lý phiên bản, vì vậy thường được bind mount từ host vào container ở chế độ chỉ đọc.

Sơ đồ luồng dữ liệu:

~~~mermaid
flowchart LR
    A["Repository trên host<br/>db/changelog"] -->|"Bind mount, read-only"| B["Liquibase container"]
    B -->|"JDBC qua Docker network"| C["Database container hoặc DB server"]
    B --> D["Log và kết quả lệnh"]
~~~

Container không tự nhìn thấy mọi file trên host. Chỉ những đường dẫn được mount mới xuất hiện trong filesystem của container. Vì vậy, đường dẫn changelog truyền cho Liquibase phải là đường dẫn bên trong container, không phải đường dẫn trên máy phát triển.

## 3. Chuẩn bị cấu trúc dự án

Một cấu trúc đơn giản có thể như sau:

~~~text
my-service/
├── compose.yaml
├── .env
├── .gitignore
├── db/
│   └── changelog/
│       ├── db.changelog-master.yaml
│       ├── changes/
│       │   ├── 001-create-customer.yaml
│       │   └── 002-add-customer-status.yaml
│       └── data/
│           └── reference-countries.csv
└── src/
    └── main/
        └── java/
~~~

Master changelog nạp các file con bằng đường dẫn tương đối:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Một changeset có thể tham chiếu file SQL hoặc CSV. Ví dụ, một changeset sử dụng loadData có thể trỏ tới file dữ liệu trong thư mục data. Khi đó, việc mount riêng master changelog mà bỏ sót thư mục changes hoặc data sẽ khiến Liquibase không tìm thấy file được tham chiếu.

Quy tắc thực hành là mount toàn bộ thư mục gốc chứa master changelog và các tài nguyên mà changelog tham chiếu. Giữ nguyên cấu trúc thư mục khi ánh xạ sang container. Nếu đổi cấu trúc, hãy kiểm tra lại đường dẫn include, sqlFile, loadData và các file tham chiếu khác.

## 4. Chọn image và phiên bản Liquibase

Image chính thức thường có tên **liquibase/liquibase**. Nên chọn tag phiên bản cụ thể thay vì dùng tag trôi nổi như latest. Cố định tag giúp nhóm biết chính xác phiên bản Liquibase được sử dụng trong lần chạy, hỗ trợ tái lập kết quả và điều tra khác biệt giữa các lần triển khai.

Ví dụ tải image với tag đã chọn:

~~~bash
docker pull liquibase/liquibase:4.31.1
~~~

Tag 4.31.1 trong ví dụ chỉ là phiên bản minh họa. Hãy chọn phiên bản được dự án phê duyệt, kiểm tra tương thích với changelog hiện có, Java runtime, JDBC driver và hệ quản trị cơ sở dữ liệu. Trong pipeline, nên ghim cả tag image và cách lấy image để các lần chạy không âm thầm chuyển sang phiên bản khác.

Kiểm tra image:

~~~bash
docker image inspect liquibase/liquibase:4.31.1
docker run --rm liquibase/liquibase:4.31.1 --version
~~~

Liquibase cần JDBC driver phù hợp với DBMS. Một số image có sẵn driver cho các hệ quản trị phổ biến, nhưng không nên giả định mọi driver hoặc mọi phiên bản driver đều có trong tag đang dùng. Kiểm tra tài liệu của image đã chọn và thử kết nối trên đúng DBMS. Nếu thiếu driver, có thể tạo image mở rộng từ image Liquibase đã ghim phiên bản rồi thêm JAR driver vào classpath theo hướng dẫn của image.

Ví dụ Dockerfile cho image tùy chỉnh:

~~~dockerfile
FROM liquibase/liquibase:4.31.1
COPY drivers/postgresql-42.7.4.jar /liquibase/lib/
~~~

Đặt driver trong repository hoặc build context theo chính sách của dự án. Không tải driver không rõ nguồn gốc trong lúc container đang chạy. Khi thay driver, hãy kiểm tra tương thích với Java, Liquibase và phiên bản máy chủ database.

## 5. Bind mount: đưa changelog từ host vào container

**Bind mount** ánh xạ một thư mục hoặc file có thật trên host vào một đường dẫn trong container. Đây là cách phù hợp để Liquibase đọc changelog do nhóm phát triển quản lý trong Git.

Cú pháp tổng quát:

~~~bash
docker run --rm \
  --mount type=bind,source=/absolute/path/to/db/changelog,target=/liquibase/changelog,readonly \
  liquibase/liquibase:4.31.1 \
  --version
~~~

Trong ví dụ:

- source là đường dẫn tuyệt đối trên host.
- target là đường dẫn sẽ xuất hiện bên trong container.
- readonly gắn thư mục ở chế độ chỉ đọc.
- --rm xóa container tạm sau khi lệnh kết thúc; image và dữ liệu trên host vẫn còn.

Khi mount thư mục dự án, master changelog trong container sẽ có đường dẫn:

~~~text
/liquibase/changelog/db.changelog-master.yaml
~~~

Do đó, lệnh Liquibase phải tham chiếu đường dẫn này hoặc đường dẫn tương đối tính từ working directory của container. Ví dụ:

~~~bash
--changelog-file=/liquibase/changelog/db.changelog-master.yaml
~~~

Không truyền đường dẫn host như /home/user/project/db/changelog/db.changelog-master.yaml vào CLI nếu đường dẫn đó không tồn tại bên trong container.

### 5.1. Chạy trên Linux hoặc macOS

Giả sử terminal đang ở thư mục gốc dự án. Có thể chạy:

~~~bash
docker run --rm \
  --mount "type=bind,source=$PWD/db/changelog,target=/liquibase/changelog,readonly" \
  liquibase/liquibase:4.31.1 \
  --changelog-file=/liquibase/changelog/db.changelog-master.yaml \
  validate
~~~

Lệnh trên chỉ kiểm tra changelog theo chức năng validate. Để kết nối database, truyền thêm JDBC URL và thông tin xác thực qua cấu hình an toàn. Ví dụ dưới đây minh họa cách truyền bằng biến môi trường được Docker đưa vào container:

~~~bash
docker run --rm \
  --mount "type=bind,source=$PWD/db/changelog,target=/liquibase/changelog,readonly" \
  -e LIQUIBASE_COMMAND_URL="$LIQUIBASE_URL" \
  -e LIQUIBASE_COMMAND_USERNAME="$LIQUIBASE_USERNAME" \
  -e LIQUIBASE_COMMAND_PASSWORD="$LIQUIBASE_PASSWORD" \
  liquibase/liquibase:4.31.1 \
  --changelog-file=/liquibase/changelog/db.changelog-master.yaml \
  status --verbose
~~~

Các biến LIQUIBASE_COMMAND_URL, LIQUIBASE_COMMAND_USERNAME và LIQUIBASE_COMMAND_PASSWORD là cách cấu hình tham số lệnh qua môi trường trong image Liquibase chính thức. Cần kiểm tra quy ước biến môi trường theo phiên bản image đang dùng. Không ghi password trực tiếp vào repository hoặc file compose được commit.

### 5.2. Chạy trên Windows PowerShell

Với Docker Desktop, dùng đường dẫn tuyệt đối do PowerShell cung cấp để tránh nhầm dấu gạch chéo và ký tự ổ đĩa:

~~~powershell
docker run --rm --mount "type=bind,source=$($PWD.Path)\db\changelog,target=/liquibase/changelog,readonly" liquibase/liquibase:4.31.1 --changelog-file=/liquibase/changelog/db.changelog-master.yaml validate
~~~

Nếu dự án nằm trong ổ đĩa hoặc thư mục có khoảng trắng, giữ toàn bộ giá trị mount trong dấu nháy kép như ví dụ. Docker Desktop phải được cấu hình để truy cập ổ đĩa hoặc thư mục đó. Khi mount thất bại, kiểm tra lại đường dẫn host, quyền chia sẻ file của Docker Desktop và thông báo lỗi của Docker.

### 5.3. Mount các tài nguyên khác

Nếu changelog tham chiếu SQL, CSV hoặc file YAML khác, mount cả thư mục cha chứa chúng. Ví dụ, khi chỉ mount file master changelog mà không mount thư mục changes, Liquibase có thể đọc được file gốc nhưng thất bại khi xử lý include.

Nếu Liquibase cần ghi báo cáo hoặc file đầu ra, tạo một mount riêng có quyền ghi cho đúng thư mục output. Không cấp quyền ghi cho toàn bộ thư mục changelog chỉ vì một tác vụ cần ghi kết quả. Tách rõ nguồn đầu vào chỉ đọc và thư mục đầu ra có thể ghi.

## 6. Kết nối database từ Liquibase container

Liquibase kết nối database bằng JDBC URL. Địa chỉ máy chủ phải được hiểu từ network namespace của container.

- Nếu database chạy trong một service khác của cùng Docker Compose, dùng tên service làm hostname, ví dụ jdbc:postgresql://db:5432/app.
- Nếu database chạy trên máy host, localhost bên trong Liquibase container trỏ về chính container đó. Trên Docker Desktop thường có thể dùng host.docker.internal để truy cập host.
- Nếu database nằm trên máy chủ bên ngoài, dùng hostname/IP và port có thể truy cập từ Docker network; kiểm tra DNS, firewall, TLS và quyền truy cập.
- Nếu hai container được tạo bằng docker run riêng, chúng cần cùng một Docker network để gọi nhau bằng tên container hoặc alias.

Không dùng localhost trong JDBC URL khi database nằm trong container khác. Ví dụ, với Compose service tên db, URL đúng thường có dạng:

~~~text
jdbc:postgresql://db:5432/app
~~~

Cổng 5432 là cổng bên trong network của Compose. Nếu Compose ánh xạ cổng database ra host, chẳng hạn 5433:5432, Liquibase container vẫn dùng cổng nội bộ 5432 khi kết nối service db. Cổng 5433 chỉ dành cho ứng dụng chạy trực tiếp trên host.

Tài khoản Liquibase nên có đúng quyền cần thiết để tạo hoặc sửa schema và dữ liệu. Không nên dùng tài khoản quản trị toàn quyền của database cho mọi môi trường. Với môi trường sản xuất, áp dụng nguyên tắc quyền tối thiểu, quản lý secret tập trung và kiểm soát ai được phép chạy migration.

## 7. Chạy bằng Docker Compose

Docker Compose giúp khai báo database, Liquibase, network, volume và biến môi trường trong cùng một cấu hình. Ví dụ dưới đây tạo PostgreSQL cho môi trường phát triển và một service Liquibase chạy theo yêu cầu.

~~~yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app_migrator
      POSTGRES_PASSWORD: $DB_PASSWORD
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_migrator -d app"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - postgres-data:/var/lib/postgresql/data

  liquibase:
    image: liquibase/liquibase:4.31.1
    profiles: ["migration"]
    depends_on:
      db:
        condition: service_healthy
    environment:
      LIQUIBASE_COMMAND_URL: jdbc:postgresql://db:5432/app
      LIQUIBASE_COMMAND_USERNAME: app_migrator
      LIQUIBASE_COMMAND_PASSWORD: $DB_PASSWORD
    volumes:
      - type: bind
        source: ./db/changelog
        target: /liquibase/changelog
        read_only: true

volumes:
  postgres-data:
~~~

Tạo file .env ở thư mục có compose.yaml để cung cấp DB_PASSWORD cho Compose:

~~~text
DB_PASSWORD=replace-with-a-local-development-secret
~~~

Không commit file .env chứa mật khẩu thật. Thêm .env vào .gitignore và dùng secret manager hoặc cơ chế secrets phù hợp khi triển khai môi trường dùng chung. Biến môi trường thuận tiện cho môi trường phát triển nhưng có thể xuất hiện trong metadata của container hoặc thông tin chẩn đoán; không xem chúng là kho bí mật an toàn cho mọi môi trường.

Service Liquibase có profile migration để không tự khởi chạy như một ứng dụng thường trực khi chạy toàn bộ stack. Nó chờ database healthy rồi chạy một lệnh và kết thúc. Các lệnh ví dụ:

~~~bash
docker compose up -d db
docker compose run --rm liquibase --changelog-file=/liquibase/changelog/db.changelog-master.yaml validate
docker compose run --rm liquibase --changelog-file=/liquibase/changelog/db.changelog-master.yaml status --verbose
docker compose run --rm liquibase --changelog-file=/liquibase/changelog/db.changelog-master.yaml update-sql
docker compose run --rm liquibase --changelog-file=/liquibase/changelog/db.changelog-master.yaml update
~~~

Lệnh update-sql tạo SQL dự kiến để review, còn update mới thực sự áp dụng migration. Trước khi chạy update trên môi trường dùng chung, hãy xem SQL dự kiến, kiểm tra database đích, context/label, quyền tài khoản và kế hoạch rollback. Với PostgreSQL trong ví dụ, volume postgres-data giữ dữ liệu database khi container bị thay thế; bind mount changelog chỉ cung cấp mã migration và không phải nơi lưu dữ liệu database.

## 8. Phân biệt bind mount và named volume

| Tiêu chí | Bind mount | Named volume |
|---|---|---|
| Nguồn dữ liệu | Một đường dẫn cụ thể trên host | Vùng lưu trữ do Docker quản lý |
| Mục đích phổ biến | Chia sẻ mã nguồn, changelog, cấu hình hoặc output | Lưu dữ liệu lâu dài của database và ứng dụng |
| Đồng bộ với host | Thấy trực tiếp file trong thư mục host | Không nhất thiết có thư mục dự án tương ứng để chỉnh sửa |
| Quyền truy cập | Có thể mount read-only | Có thể gắn quyền chỉ đọc hoặc đọc/ghi |
| Vòng đời | Phụ thuộc file/thư mục host | Có vòng đời độc lập với container; tồn tại qua lần tạo lại container |

Changelog nên được bind mount vì đó là file nguồn cần review và quản lý trong Git. Dữ liệu PostgreSQL nên nằm trong named volume để không mất khi container database được tạo lại. Không dùng named volume như cách thay thế repository changelog nếu nhóm cần chỉnh sửa file trực tiếp trên host và review thay đổi qua Git.

Một điểm cần phân biệt: --rm chỉ xóa container sau khi lệnh kết thúc, không xóa named volume. Lệnh docker compose down cũng không xóa named volume trừ khi yêu cầu rõ bằng tùy chọn -v. Hãy cẩn thận với thao tác xóa volume vì volume database có thể chứa dữ liệu cần giữ lại.

## 9. Quy trình kiểm tra và triển khai an toàn

Có thể tổ chức quy trình chạy Liquibase container theo các bước sau:

1. **Kiểm tra image:** xác nhận tag Liquibase đã ghim, driver JDBC và phiên bản tương thích với database.
2. **Kiểm tra mount:** xác nhận master changelog và toàn bộ file include, SQL, CSV có thể đọc tại đường dẫn trong container.
3. **Kiểm tra kết nối:** xác nhận JDBC URL dùng đúng hostname/port theo network của container; tài khoản có quyền phù hợp.
4. **Validate:** chạy liquibase validate để phát hiện vấn đề cấu trúc changelog trước khi triển khai.
5. **Xem trạng thái:** chạy status --verbose để biết changeset nào còn chờ và kiểm tra context/label đang áp dụng.
6. **Review SQL:** chạy update-sql, lưu hoặc kiểm tra SQL dự kiến theo quy trình review của dự án.
7. **Triển khai:** chỉ chạy update sau khi đã xác nhận database đích và có kế hoạch xử lý sự cố.
8. **Đối chiếu kết quả:** xem log container, DATABASECHANGELOG, schema thực tế và kiểm tra nghiệp vụ sau migration.

Với pipeline CI/CD, checkout repository ở một bước, sau đó chạy Liquibase container với thư mục changelog được mount từ workspace pipeline. Secret database được cấp qua secret store của CI/CD. Nên tách quyền của job kiểm tra changelog khỏi job triển khai database nếu quy trình yêu cầu phê duyệt. Ghim image tag và ghi lại phiên bản Liquibase trong log giúp truy vết lần chạy.

Nếu ứng dụng Spring Boot cũng tự chạy Liquibase khi khởi động, cần thống nhất một đầu mối thực hiện migration. Khi pipeline đã chạy migration bằng container riêng, cấu hình Spring Boot có thể cần tắt auto-run Liquibase trong giai đoạn khởi động ứng dụng để tránh hai tiến trình cùng chịu trách nhiệm triển khai. Ngược lại, nếu Spring Boot là migration runner được chọn, không cần chạy thêm một container Liquibase độc lập cho cùng một lần phát hành.

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy master changelog | Đường dẫn truyền vào CLI là đường dẫn host hoặc target mount không đúng | Dùng docker run với lệnh kiểm tra file, xác nhận file nằm dưới /liquibase/changelog |
| Không tìm thấy file include/SQL/CSV | Chỉ mount file gốc, bỏ sót thư mục con hoặc đường dẫn tương đối sai | Mount thư mục gốc và giữ nguyên cấu trúc; kiểm tra relativeToChangelogFile |
| Database connection refused | JDBC URL dùng localhost, DB chưa sẵn sàng hoặc sai port | Dùng tên service trong Compose; chờ healthcheck và kiểm tra port nội bộ |
| Unknown host | Container không cùng network hoặc hostname không đúng | Kiểm tra network, service name, DNS và cấu hình Compose |
| No suitable driver / driver class not found | JDBC driver chưa có trong image hoặc classpath | Xác minh driver theo image tag; tạo image tùy chỉnh có driver tương thích |
| Permission denied | Docker không được phép đọc thư mục host hoặc quyền file không phù hợp | Kiểm tra chia sẻ ổ đĩa, ACL và quyền đọc; chỉ cấp quyền cần thiết |
| Changelog parse error | YAML/XML sai cú pháp, encoding hoặc version Liquibase không tương thích | Chạy validate, kiểm tra file và phiên bản CLI |
| Update bị dừng | Precondition không đạt, SQL lỗi hoặc schema đã drift | Đọc log và DATABASECHANGELOG; đối chiếu schema trước khi thử lại |
| Container thoát với mã lỗi khác 0 | Lệnh Liquibase thất bại | Kiểm tra exit code và log; không coi container đã kết thúc là migration thành công |

Khi debug đường dẫn, có thể chạy một container tạm với lệnh liệt kê file:

~~~bash
docker run --rm \
  --mount "type=bind,source=$PWD/db/changelog,target=/liquibase/changelog,readonly" \
  --entrypoint sh \
  liquibase/liquibase:4.31.1 \
  -c "find /liquibase/changelog -maxdepth 4 -type f -print"
~~~

Nếu image tùy chỉnh không có shell hoặc lệnh find, dùng công cụ tương đương có trong image hoặc kiểm tra mount bằng một image chẩn đoán riêng. Không cài thêm công cụ vào container sản xuất chỉ để debug tạm thời.

Khi update thất bại, không xóa DATABASECHANGELOG hoặc DATABASECHANGELOGLOCK để thử chạy lại một cách mù quáng. Kiểm tra xem lệnh có thực hiện một phần thay đổi hay không, database có hỗ trợ transaction cho các thao tác đó hay không và Liquibase ghi nhận changeset thế nào. Sau khi hiểu trạng thái thực tế, mới quyết định sửa nguyên nhân, rollback đã kiểm chứng hoặc tạo changeset khắc phục.

## 11. Checklist trước khi dùng Docker cho migration

- [ ] Image Liquibase dùng tag phiên bản cụ thể và đã được kiểm tra.
- [ ] JDBC driver tương thích với DBMS và có sẵn trong image.
- [ ] Thư mục master changelog được bind mount đúng target path.
- [ ] Các file include, SQL và dữ liệu tham chiếu đều nằm trong mount.
- [ ] Changelog được mount read-only nếu Liquibase chỉ cần đọc.
- [ ] JDBC URL dùng hostname và port nhìn thấy từ container.
- [ ] Database đã sẵn sàng trước khi chạy lệnh migration.
- [ ] Credentials được cấp từ biến môi trường hoặc secret manager, không commit vào Git.
- [ ] validate, status và update-sql đã được chạy/review theo quy trình.
- [ ] Chỉ một đầu mối được giao thực thi migration trong mỗi lần triển khai.
- [ ] Kết quả được đối chiếu qua log, DATABASECHANGELOG và schema thực tế.

## 12. Ghi nhớ

Docker image cung cấp môi trường chạy Liquibase có phiên bản xác định; bind mount đưa changelog từ repository vào filesystem của container; JDBC URL và Docker network quyết định container kết nối tới database nào. Khi mount đúng thư mục gốc, giữ nguyên các đường dẫn tương đối, cấp driver và secret phù hợp, nhóm có thể chạy cùng một bộ migration trên máy phát triển và pipeline.

Hãy tách biệt mã changelog với dữ liệu database: changelog là đầu vào được quản lý phiên bản và thường chỉ đọc trong container Liquibase; database lưu dữ liệu trong volume hoặc dịch vụ lưu trữ riêng. Trước khi thực thi update, luôn kiểm tra file đã được mount, kết nối đang trỏ tới đúng database và SQL dự kiến đã được review.
