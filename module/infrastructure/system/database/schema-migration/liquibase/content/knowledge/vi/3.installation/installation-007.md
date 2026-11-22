# Thiết lập kết nối đầu tiên và chạy một changeset mẫu với Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, bạn học cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; sau đó thực hành migration có kiểm chứng, rollback và phối hợp nhiều môi trường qua Spring Boot hoặc CI/CD. Bước cài đặt đầu tiên là kết nối một bộ Liquibase với database thử nghiệm, chạy một changeset nhỏ và xác nhận kết quả trong cả database lẫn lịch sử Liquibase.

Bài này dùng PostgreSQL làm ví dụ xuyên suốt. Các nguyên tắc về JDBC URL, driver, tài khoản database, changelog và quy trình `validate` → xem SQL → `update` cũng áp dụng cho các DBMS khác; khi đổi DBMS, hãy thay driver, URL, kiểu dữ liệu và câu lệnh quản trị theo tài liệu của hệ quản trị đó.

## 1. Kết quả cần đạt và luồng thực hiện

Sau khi hoàn thành, bạn có thể:

- Xác định phiên bản Liquibase, Java, DBMS và JDBC driver tương thích.
- Cài và chạy Liquibase CLI, hoặc tích hợp Liquibase vào ứng dụng Spring Boot.
- Cấu hình kết nối bằng JDBC URL và thông tin xác thực được quản lý an toàn.
- Tạo changelog YAML chứa một changeset tạo bảng và chèn dữ liệu mẫu.
- Kiểm tra changelog, xem SQL dự kiến, áp dụng migration và đọc lịch sử thực thi.
- Thử rollback trong database dùng riêng cho học tập và hiểu tác động của lần chạy tiếp theo.

Luồng thao tác cơ bản:

```text
Liquibase CLI hoặc Spring Boot
          |
          v
      JDBC driver
          |
          v
       Database
          |
          +---- đọc changelog
          |
          +---- validate và tạo SQL preview
          |
          +---- thực thi changeset chưa chạy
          |
          +---- ghi DATABASECHANGELOG / DATABASECHANGELOGLOCK
```

Liquibase không tự cài đặt hay khởi tạo máy chủ database cho bạn. Bạn cần có một database đang hoạt động, một tài khoản được cấp quyền phù hợp và một đường kết nối JDBC từ máy chạy Liquibase đến database đó.

## 2. Chuẩn bị môi trường

Trước khi cài đặt, xác định và ghi lại các thành phần sau:

| Thành phần | Điều cần chuẩn bị | Cách kiểm tra |
|---|---|---|
| Java | Phiên bản Java được bản Liquibase đã chọn hỗ trợ | `java -version` |
| Liquibase | Chọn một phiên bản cụ thể và cố định phiên bản đó trong nhóm | `liquibase --version` sau cài đặt |
| Database | PostgreSQL đang chạy, có host, port và tên database | Kết nối bằng công cụ quản trị hoặc `psql` |
| JDBC driver | Driver PostgreSQL tương thích với Java và DBMS | Kiểm tra dependency hoặc file JAR được nạp |
| Tài khoản | User có quyền kết nối và thay đổi schema mục tiêu | Thử đăng nhập bằng chính tài khoản migration |
| Changelog | Đường dẫn file changelog sẽ được Liquibase đọc | Kiểm tra đường dẫn từ thư mục chạy lệnh |

Phiên bản Liquibase, Java, driver và DBMS tạo thành một bộ tương thích. Không mặc định bản Liquibase mới nhất sẽ phù hợp với Java runtime cũ hoặc driver đang dùng. Hãy chọn phiên bản theo ma trận hỗ trợ của Liquibase và DBMS, sau đó khóa phiên bản trong máy phát triển, container và pipeline để kết quả có thể tái lập.

Tài khoản dùng để chạy migration cần có quyền tạo và thay đổi đối tượng trong schema đích, đồng thời có quyền tạo, đọc và cập nhật các bảng metadata của Liquibase. Với PostgreSQL, các quyền thường liên quan đến `CONNECT` trên database, `USAGE` và `CREATE` trên schema, cùng quyền thao tác dữ liệu cần thiết. Tài khoản quản trị chỉ nên dùng để tạo database, schema hoặc user ban đầu; ứng dụng triển khai nên dùng một tài khoản migration có phạm vi quyền vừa đủ.

## 3. Cài đặt Liquibase và JDBC driver

### 3.1. Chọn cách chạy

Có hai cách phổ biến để bắt đầu:

| Cách chạy | Khi phù hợp | Thành phần cần có |
|---|---|---|
| Liquibase CLI | Muốn chạy migration độc lập với vòng đời khởi động ứng dụng, hoặc triển khai từ CI/CD | Liquibase CLI, Java runtime phù hợp và JDBC driver trên classpath |
| Spring Boot | Ứng dụng quản lý migration khi khởi động hoặc dùng một tác vụ triển khai tích hợp với ứng dụng | `liquibase-core`, JDBC driver và cấu hình Spring Boot |

Chọn một cơ chế thực thi làm chủ cho mỗi lần triển khai. Nếu Spring Boot tự động chạy Liquibase khi khởi động, tránh để một pipeline khác chạy migration đồng thời vào cùng database. Nếu tổ chức chọn CLI làm bước triển khai độc lập, cấu hình ứng dụng để không tự khởi chạy một lượt migration cạnh tranh.

### 3.2. Cài Liquibase CLI

Tải gói cài đặt Liquibase từ kênh phân phối chính thức, chọn đúng phiên bản đã được xác nhận với Java runtime và giải nén/cài đặt theo hệ điều hành. Thêm thư mục chứa chương trình `liquibase` vào `PATH` nếu muốn gọi lệnh từ mọi thư mục. Sau đó mở terminal mới và kiểm tra:

```bash
java -version
liquibase --version
```

Kết quả cần cho biết Java và Liquibase có thể khởi chạy. Nếu lệnh `liquibase` không được nhận diện, kiểm tra lại `PATH` và vị trí chương trình. Nếu Liquibase không khởi động được, kiểm tra phiên bản Java theo yêu cầu của bản Liquibase đang cài.

### 3.3. Đưa JDBC driver vào classpath

Liquibase giao tiếp với database thông qua JDBC. CLI cần tìm được driver tương ứng với URL kết nối. Với PostgreSQL, driver có lớp:

```text
org.postgresql.Driver
```

Tải JAR của PostgreSQL JDBC driver tương thích với Java và máy chủ PostgreSQL. Có thể đặt JAR trong thư mục `drivers` của dự án hoặc một vị trí được quản lý riêng, rồi khai báo đường dẫn trong `liquibase.properties`:

```properties
driver=org.postgresql.Driver
classpath=drivers/postgresql-<driver-version>.jar
```

Đường dẫn tương đối được tính từ thư mục làm việc khi chạy Liquibase. Hãy thay `<driver-version>` bằng phiên bản JAR thực tế và bảo đảm file có mặt trên máy chạy CLI. Không tải JAR tùy ý từ nguồn không đáng tin cậy. Trong pipeline, cố định phiên bản driver và nguồn tải; trong Spring Boot, khai báo driver như dependency của ứng dụng để build tool quản lý classpath.

Lỗi `No suitable driver` hoặc `Cannot find database driver` thường cho biết driver chưa có trên classpath, phiên bản driver không tương thích hoặc URL không được driver nhận diện. Kiểm tra đồng thời ba yếu tố: JAR, tên lớp driver và JDBC URL.

## 4. Chuẩn bị database PostgreSQL thử nghiệm

Giả sử PostgreSQL đang chạy tại `localhost:5432`. Ví dụ này sử dụng database `appdb` và user riêng `liquibase_app`. Tạo user và database bằng tài khoản quản trị hoặc giao diện quản lý của dịch vụ database:

```sql
CREATE USER liquibase_app WITH PASSWORD '<set-a-secret-outside-source-control>';
CREATE DATABASE appdb OWNER liquibase_app;
```

Thay giá trị mật khẩu bằng bí mật thực tế được cấp qua secret manager hoặc cơ chế quản lý bí mật của môi trường. Không lưu mật khẩu thật trong changelog, file cấu hình được commit, lịch sử terminal hoặc log CI/CD. Nếu database do nhà cung cấp quản lý, tạo user/database theo quy trình của nhà cung cấp và xác nhận quyền schema tương ứng.

JDBC URL cơ bản của ví dụ:

```text
jdbc:postgresql://localhost:5432/appdb
```

Ý nghĩa các phần:

- `jdbc:postgresql`: chọn PostgreSQL JDBC driver.
- `localhost`: máy chủ database có thể truy cập từ máy chạy Liquibase.
- `5432`: cổng PostgreSQL, cần thay nếu máy chủ dùng cổng khác.
- `appdb`: database cần kết nối.

Nếu Liquibase chạy trong container, `localhost` thường trỏ về chính container đó, không phải máy chủ database trên máy host. Khi ấy phải dùng hostname/service name mà container có thể phân giải. Với database từ xa, kiểm tra DNS, firewall, allowlist IP, TLS và quy tắc mạng trước khi chẩn đoán lỗi Liquibase.

Trước khi chạy migration, thử đăng nhập bằng đúng user `liquibase_app` và xác nhận user có thể truy cập database, schema mục tiêu. Ví dụ với `psql`:

```bash
psql "postgresql://liquibase_app@localhost:5432/appdb" -c "select current_database(), current_user;"
```

Lệnh trên có thể yêu cầu mật khẩu tương tác tùy cấu hình `psql`. Nếu đăng nhập thất bại, xử lý thông tin xác thực, quyền hoặc kết nối trước; Liquibase không thể sửa một kết nối JDBC vốn chưa hoạt động.

## 5. Cấu hình kết nối cho Liquibase CLI

Tạo file `liquibase.properties` trong thư mục làm việc của dự án. Đây là file cấu hình ví dụ; chỉ đưa các giá trị không bí mật vào version control:

```properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://localhost:5432/appdb
username=liquibase_app
driver=org.postgresql.Driver
classpath=drivers/postgresql-<driver-version>.jar
```

Không thêm mật khẩu thật vào file này. Cấp mật khẩu cho tiến trình qua biến môi trường `LIQUIBASE_COMMAND_PASSWORD`, được lấy từ secret store hoặc cơ chế bảo mật của máy chạy. Ví dụ trong PowerShell khi biến `DB_PASSWORD` đã được nạp an toàn:

```powershell
$env:LIQUIBASE_COMMAND_PASSWORD = $env:DB_PASSWORD
liquibase --defaults-file=liquibase.properties validate
```

Trong Bash:

```bash
export LIQUIBASE_COMMAND_PASSWORD="$DB_PASSWORD"
liquibase --defaults-file=liquibase.properties validate
```

Sau khi chạy xong, xóa biến môi trường khỏi phiên terminal nếu không cần dùng tiếp. Trong CI/CD, cấu hình secret ở cấp job/runner và giới hạn quyền đọc secret cho đúng bước triển khai. Không in giá trị biến ra log để kiểm tra.

`--defaults-file` chỉ định file cấu hình mà Liquibase đọc. Các tham số truyền trực tiếp trên dòng lệnh hoặc biến môi trường có thể ghi đè giá trị trong file theo thứ tự ưu tiên cấu hình của phiên bản đang sử dụng. Nếu một lệnh chạy với URL hoặc user ngoài dự kiến, kiểm tra cả tham số dòng lệnh, biến môi trường và defaults file.

Kiểm tra cấu hình kết nối bằng một lệnh chỉ đọc trạng thái:

```bash
liquibase --defaults-file=liquibase.properties status
```

Lệnh `status` cho biết còn changeset nào cần triển khai theo changelog và lịch sử Liquibase hiện có. Nếu chưa có bảng metadata, kết quả có thể báo các changeset đang chờ; điều đó không tự nó chứng minh database đã có bảng ứng dụng hay schema đúng như mong đợi.

## 6. Tạo changelog và changeset mẫu

Tạo cấu trúc thư mục ví dụ:

```text
project/
├── liquibase.properties
├── drivers/
│   └── postgresql-<driver-version>.jar
└── db/
    └── changelog/
        └── db.changelog-master.yaml
```

Trong `db/changelog/db.changelog-master.yaml`, khai báo một changeset tạo bảng và thêm một dòng dữ liệu:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-liquibase-demo
      author: training
      comment: Tao bang va du lieu mau de kiem tra ket noi Liquibase
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - createTable:
            tableName: liquibase_demo
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: message
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
        - insert:
            tableName: liquibase_demo
            columns:
              - column:
                  name: message
                  value: Hello Liquibase
      rollback:
        - dropTable:
            tableName: liquibase_demo
```

Trong changeset trên:

- `id` và `author` cùng với định danh file changelog tạo thành một phần nhận diện changeset trong lịch sử Liquibase. Hãy giữ các giá trị này ổn định.
- `preConditions` xác nhận database đích là PostgreSQL trước khi thay đổi; `onFail: HALT` dừng triển khai nếu điều kiện không đạt, giúp tránh chạy ví dụ vào nhầm DBMS.
- `createTable` mô tả cấu trúc bảng; Liquibase chuyển change type thành SQL phù hợp với DBMS được kết nối.
- `autoIncrement` yêu cầu cột `id` được tạo giá trị tự tăng theo cách DBMS hỗ trợ.
- `insert` thêm một dòng dữ liệu để có thể kiểm tra rằng cả thay đổi schema lẫn dữ liệu đã được thực thi.
- `rollback` khai báo cách đảo ngược changeset mẫu bằng cách xóa bảng. Thao tác này xóa cả dữ liệu trong bảng, vì vậy chỉ dùng trong database thử nghiệm có thể khôi phục.

Không chỉnh sửa nội dung changeset sau khi nó đã được triển khai ở môi trường dùng chung. Liquibase lưu checksum trong `DATABASECHANGELOG` để phát hiện nội dung changeset đã thay đổi. Nếu cần bổ sung cột hoặc thay đổi dữ liệu, tạo changeset mới với `id` mới. Đối với dự án thực tế, chia thay đổi thành các changeset nhỏ, có mục đích rõ ràng và cân nhắc precondition để xác minh trạng thái database trước khi thực thi.

## 7. Kiểm tra và chạy changeset

Thực hiện các bước dưới đây từ thư mục chứa `liquibase.properties`, nơi đường dẫn `db/changelog/...` và `drivers/...` được tính tương đối.

### Bước 1: Xác thực changelog

```bash
liquibase --defaults-file=liquibase.properties validate
```

`validate` kiểm tra changelog có thể được đọc và phân tích, đồng thời thực hiện các kiểm tra xác thực liên quan đến lịch sử Liquibase. Nếu có lỗi YAML, thiếu thuộc tính bắt buộc, include không tìm thấy hoặc checksum không khớp, xử lý nguyên nhân trước khi cập nhật database. Lệnh này không thay thế việc review SQL hay kiểm tra cấu trúc database thực tế.

### Bước 2: Xem SQL dự kiến

```bash
liquibase --defaults-file=liquibase.properties update-sql
```

`update-sql` tạo phần SQL mà Liquibase dự kiến chạy cho các changeset còn thiếu. Lệnh này phục vụ review; nó không thực thi thay đổi vào database. Đọc SQL được sinh ra và kiểm tra tên schema/bảng, kiểu dữ liệu, khóa chính, giá trị mặc định, câu lệnh insert và các thao tác có thể ảnh hưởng đến dữ liệu. Nếu SQL khác với dự kiến, xác minh lại URL, DBMS, phiên bản Liquibase, driver và nội dung changelog.

### Bước 3: Áp dụng migration

```bash
liquibase --defaults-file=liquibase.properties update
```

`update` tìm các changeset chưa được ghi nhận là đã thực thi rồi áp dụng theo thứ tự changelog. Trong lần đầu, Liquibase thường tạo hai bảng metadata trong schema mặc định hoặc schema được cấu hình:

- `DATABASECHANGELOG` lưu định danh changeset, tác giả, file, thời điểm thực thi, trạng thái thực thi và checksum.
- `DATABASECHANGELOGLOCK` dùng để khóa quá trình cập nhật, tránh nhiều tiến trình Liquibase cùng thực thi migration đồng thời trên một database.

Sau đó, Liquibase tạo bảng `liquibase_demo` và chèn dòng `Hello Liquibase`. Nếu migration thất bại, đọc lỗi SQL và trạng thái database trước khi chạy lại. Tùy DBMS và loại thao tác, không phải mọi câu lệnh đều được rollback tự động trong cùng một transaction.

### Bước 4: Xác minh kết quả trong database

Kết nối bằng công cụ SQL và chạy:

```sql
SELECT id, message FROM liquibase_demo;

SELECT id, author, filename, exectype, md5sum
FROM databasechangelog
WHERE id = '001-create-liquibase-demo';
```

Truy vấn đầu tiên phải trả về dòng `Hello Liquibase`. Truy vấn thứ hai giúp xác nhận changeset đã xuất hiện trong lịch sử. Tên cột trong metadata table có thể được DBMS chuẩn hóa theo quy tắc chữ hoa/chữ thường; với PostgreSQL, tên không đặt trong dấu nháy kép thường được lưu và truy vấn ở dạng chữ thường.

Chạy lại:

```bash
liquibase --defaults-file=liquibase.properties update
```

Kết quả mong đợi là không có changeset mới cần áp dụng. Liquibase dựa vào lịch sử và checksum để nhận diện changeset đã chạy; câu lệnh `insert` trong changeset mẫu không được chạy lặp lại chỉ vì bạn gọi `update` lần nữa. Đây là cơ chế theo dõi lịch sử migration, không phải cơ chế chống trùng cho mọi câu lệnh SQL mà ứng dụng tự chạy ngoài Liquibase.

## 8. Thử rollback trong database riêng

Chỉ thực hành rollback trên database thử nghiệm hoặc database có thể khôi phục. Vì rollback của changeset mẫu dùng `dropTable`, nó xóa bảng và dữ liệu mẫu.

Với phiên bản CLI hỗ trợ lệnh `rollback-count`, có thể đảo ngược một changeset gần nhất bằng:

```bash
liquibase --defaults-file=liquibase.properties rollback-count --count=1
```

Sau lệnh này, kiểm tra bảng `liquibase_demo` đã bị xóa và changeset tương ứng đã được loại khỏi trạng thái đã triển khai trong lịch sử theo cơ chế rollback. Chạy `update` lại sẽ thực thi changeset một lần nữa và tạo lại bảng cùng dòng dữ liệu mẫu.

Trước khi dùng lệnh rollback trong dự án thật, xác nhận cú pháp theo phiên bản Liquibase đang chạy, đọc SQL rollback dự kiến nếu phiên bản hỗ trợ preview và đánh giá tác động đến dữ liệu. Rollback cấu trúc không thể tự khôi phục dữ liệu đã bị xóa hoặc ghi đè nếu không có bản sao lưu hay thao tác bù phù hợp. Với thay đổi dữ liệu quan trọng, cần thiết kế rollback tường minh hoặc phương án forward-fix.

## 9. Tích hợp cùng Spring Boot

Nếu ứng dụng Spring Boot chịu trách nhiệm chạy migration khi khởi động, thêm dependency `liquibase-core` và JDBC driver của DBMS vào ứng dụng. Ví dụ Maven với phiên bản được quản lý tập trung:

```xml
<properties>
    <liquibase.version>4.x.y</liquibase.version>
    <postgresql.version>42.x.y</postgresql.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>${liquibase.version}</version>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>${postgresql.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Thay các giá trị `4.x.y` và `42.x.y` bằng phiên bản thực tế đã kiểm tra tương thích; nếu dự án dùng Spring Boot dependency management, có thể để BOM quản lý phiên bản theo quy ước của dự án.

Đặt changelog trong `src/main/resources/db/changelog/db.changelog-master.yaml`, rồi cấu hình `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: liquibase_app
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
```

`DB_PASSWORD` phải được cung cấp từ môi trường chạy hoặc secret manager. Không đưa mật khẩu thật vào `application.yml` được commit. Khi ứng dụng khởi động, Spring Boot cấu hình DataSource và Liquibase; Liquibase đọc changelog, kết nối database và áp dụng các changeset còn thiếu trước khi ứng dụng hoàn tất khởi động, theo cấu hình và thứ tự khởi tạo của ứng dụng.

Đừng vô tình để cả Spring Boot và Liquibase CLI cùng chạy migration cho một lần phát hành. Hãy chọn nơi sở hữu bước migration, thống nhất phiên bản `liquibase-core`/CLI và bảo đảm hai cách chạy dùng cùng changelog, schema và cấu hình DBMS. Nếu CLI được dùng trong pipeline, ứng dụng có thể cần tắt auto-run bằng cấu hình phù hợp với môi trường triển khai.

## 10. Đưa quy trình vào CI/CD và nhiều môi trường

Khi chuyển từ máy cá nhân sang pipeline, giữ nguyên changelog đã review và thay đổi cấu hình kết nối theo từng môi trường:

| Môi trường | Cấu hình kết nối | Kiểm soát cần có |
|---|---|---|
| Local | Database dùng cho phát triển | User riêng, dữ liệu thử nghiệm, dễ tạo lại |
| Test/CI | Database tạm hoặc database kiểm thử dùng chung có kiểm soát | Chạy validate, SQL preview và migration tự động; thu thập log không chứa bí mật |
| Staging | DBMS và phiên bản gần production | Kiểm thử thời gian chạy, dữ liệu, rollback và quyền truy cập |
| Production | Endpoint và secret do vận hành quản lý | Phê duyệt triển khai, backup/khôi phục, cửa sổ thay đổi và theo dõi kết quả |

Pipeline nên cố định phiên bản Liquibase và JDBC driver, nạp mật khẩu từ secret manager, chạy `validate`, tạo SQL preview để review và chỉ thực thi `update` sau khi đạt điều kiện phát hành. Không đặt mật khẩu trong tham số được ghi vào log hoặc trong file changelog. Với database production, tài khoản migration cần quyền cần thiết cho thay đổi đã phê duyệt; tài khoản runtime của ứng dụng thường nên có quyền thấp hơn.

Các môi trường phải triển khai cùng một chuỗi changeset theo thứ tự. Không chỉnh sửa changeset đã chạy ở môi trường trước để làm cho môi trường sau “khớp”; hãy tạo changeset bổ sung. Theo dõi `DATABASECHANGELOG` để phát hiện môi trường thiếu hoặc có lịch sử khác biệt, và xử lý trạng thái `DATABASECHANGELOGLOCK` chỉ sau khi xác minh không còn tiến trình migration đang chạy.

## 11. Chẩn đoán lỗi kết nối và triển khai ban đầu

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Connection refused hoặc timeout | Host/port sai, database dừng, firewall hoặc mạng container | Kiểm tra trạng thái server, DNS, cổng, route và allowlist |
| Password authentication failed | User, mật khẩu hoặc chính sách xác thực không đúng | Kiểm tra secret, user và phương thức xác thực của PostgreSQL |
| No suitable driver | JDBC JAR thiếu hoặc không tương thích; URL sai định dạng | Kiểm tra classpath, phiên bản driver và tiền tố `jdbc:postgresql:` |
| Database does not exist | Sai tên database hoặc chưa tạo database | Kiểm tra URL và database trên server |
| Permission denied for schema/table | User thiếu quyền trên schema hoặc đối tượng | Kiểm tra quyền `CONNECT`, `USAGE`, `CREATE` và quyền thao tác cần thiết |
| Changelog file not found | Đường dẫn tương đối được tính từ thư mục chạy khác dự kiến | Kiểm tra `changeLogFile`, `--defaults-file` và working directory |
| Checksum validation failed | Changeset đã chạy bị chỉnh sửa hoặc nội dung được nạp khác | So sánh lịch sử, file và phiên bản; không tự ý xóa checksum để bỏ qua lỗi |
| Liquibase lock đang được giữ | Một tiến trình cập nhật khác đang chạy hoặc lần trước kết thúc bất thường | Xác minh tiến trình và trạng thái database trước khi xử lý lock |

Khi có lỗi, lưu lại thông báo lỗi đã loại bỏ thông tin bí mật, lệnh đã chạy, phiên bản Liquibase, DBMS và môi trường. Phân biệt lỗi kết nối JDBC với lỗi SQL của changeset: kết nối thành công không đảm bảo câu lệnh migration được DBMS chấp nhận.

Không xóa `DATABASECHANGELOG` hoặc `DATABASECHANGELOGLOCK` để “reset” một lần triển khai lỗi. Những bảng này là sổ lịch sử và cơ chế khóa của Liquibase. Can thiệp trực tiếp có thể làm Liquibase chạy lại thay đổi đã áp dụng, gây trùng dữ liệu hoặc làm sai lệch lịch sử giữa các môi trường. Chỉ xử lý lock sau khi chắc chắn không còn tiến trình cập nhật hoạt động và đã hiểu nguyên nhân lock tồn tại.

## 12. Checklist hoàn tất cài đặt

Trước khi coi kết nối đầu tiên đã sẵn sàng, kiểm tra:

- [ ] Phiên bản Java, Liquibase và JDBC driver đã được xác định và tương thích.
- [ ] CLI tìm thấy driver hoặc ứng dụng Spring Boot đã nạp đúng dependency.
- [ ] Database đang hoạt động và có thể truy cập từ máy chạy migration.
- [ ] JDBC URL, database, user và schema mục tiêu đã được xác minh.
- [ ] Tài khoản migration có quyền vừa đủ; bí mật được cấp từ môi trường/secret manager.
- [ ] Liquibase đọc đúng defaults file và đúng changelog.
- [ ] `validate` thành công và SQL từ `update-sql` đã được xem xét.
- [ ] `update` tạo bảng mẫu và một dòng dữ liệu như mong đợi.
- [ ] `DATABASECHANGELOG` ghi nhận changeset; lần `update` tiếp theo không chạy lại changeset đó.
- [ ] Rollback đã được thử trong database có thể khôi phục và tác động dữ liệu đã được hiểu.
- [ ] Cách chạy migration trong Spring Boot hoặc CI/CD đã được thống nhất để tránh chạy đồng thời.

Khi tất cả điều kiện trên đạt, bạn đã có một kết nối Liquibase có thể kiểm chứng và một changeset mẫu được ghi nhận trong lịch sử. Từ nền tảng này, hãy mở rộng changelog bằng các changeset nhỏ, kiểm tra precondition cho trạng thái database cần thiết, giữ nguyên changeset đã triển khai để checksum ổn định và đưa cùng một quy trình đã xác nhận qua các môi trường phát triển, kiểm thử, staging và production.
