# Phân chia cấu hình theo profile và giữ bí mật kết nối ngoài mã nguồn

Ứng dụng **Spring Data Relational JDBC** đọc và ghi dữ liệu thông qua `DataSource`, connection pool và JDBC driver. Khi chạy trên máy lập trình, trong CI hoặc ở production, ứng dụng thường cần các database, quyền truy cập và thông số vận hành khác nhau. Nếu ghi cố định URL, username và password vào mã Java hay một file YAML rồi commit lên Git, bạn có thể làm lộ thông tin xác thực và vô tình truy cập sai môi trường.

Spring Boot cung cấp **profiles** để chọn cấu hình theo môi trường và cơ chế **externalized configuration** để nạp giá trị từ bên ngoài ứng dụng. Hai cơ chế bổ sung cho nhau: profile chọn bộ thiết lập `dev`, `test` hoặc `prod`; còn secret manager, biến môi trường hoặc file secret được mount cấp mật khẩu thực tế khi chạy.

## 1. Cần tách những gì?

Một `DataSource` thông thường nhận URL kết nối JDBC, username, password và các thiết lập như kích thước connection pool:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/learning
    username: app_user
    password: ${DB_PASSWORD}
```

Ở đây `${DB_PASSWORD}` là **placeholder**, không phải mật khẩu. Spring Boot tìm property tên `DB_PASSWORD` từ các nguồn cấu hình khi khởi tạo.

| Loại dữ liệu | Ví dụ | Nơi quản lý |
| --- | --- | --- |
| Cấu hình chung, không nhạy cảm | Tên ứng dụng, timeout kết nối mặc định | `application.yml` trong Git |
| Cấu hình riêng môi trường | JDBC URL dev/staging/prod, pool size | File theo profile hoặc cấu hình ngoài ứng dụng |
| Secret | Mật khẩu database, token, private key | Secret manager, biến môi trường được cấp an toàn, file secret ngoài repo |
| Danh tính và quyền | Tài khoản service, quyền với schema | Database và hệ thống quản lý quyền |

URL và username không phải lúc nào cũng là bí mật, nhưng vẫn có thể để lộ cấu trúc mạng hoặc định danh nội bộ. Với production, có thể đưa chúng ra ngoài mã nguồn cùng với secret.

Điểm khác biệt cần ghi nhớ: **profile không bảo vệ password** và **cấp password an toàn không tự ngăn kết nối nhầm database**. Cần thiết kế cả hai.

## 2. Cơ chế Spring Profile

Spring Profile là tên logic, ví dụ `dev`, `test`, `prod`, được kích hoạt lúc ứng dụng khởi động. Spring Boot có quy ước đọc:

```text
src/main/resources/
├── application.yml           # Chung cho mọi môi trường
├── application-dev.yml       # Phần chỉ áp dụng cho dev
└── application-prod.yml      # Phần chỉ áp dụng cho prod

src/test/resources/
└── application-test.yml      # Cấu hình dùng trên test classpath
```

Với profile `dev`, các giá trị trong `application-dev.yml` ghi đè property cùng tên từ `application.yml`, trừ khi có nguồn cấu hình ưu tiên cao hơn. Tương tự cho `prod`. Biến môi trường và các nguồn cấu hình bên ngoài có thể ghi đè property trong file theo quy tắc ưu tiên của Spring Boot. Không nên dựa vào suy đoán rằng file `application-prod.yml` luôn có ưu tiên cao nhất.

Ví dụ:

```yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
```

```yaml
# application-dev.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
```

Khi chạy profile `dev` và không có cấu hình khác ghi đè, giới hạn pool là `4`; những profile không ghi đè sẽ kế thừa `10`. Không cần sao chép toàn bộ cấu hình chung vào từng file.

### 2.1. Kích hoạt profile

Cách thông dụng nhất trong hệ thống triển khai là cấp biến môi trường:

```text
SPRING_PROFILES_ACTIVE=prod
```

Ví dụ khởi chạy trong Bash:

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

Ví dụ trong Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\gradlew.bat bootRun
```

Các lệnh chỉ minh họa cách chọn profile; để kết nối được database, ứng dụng vẫn cần driver, database và credential thích hợp. Trong IDE có thể cấu hình biến `SPRING_PROFILES_ACTIVE` cho từng run configuration. Cũng có thể dùng `--spring.profiles.active=dev` ở command line; **không truyền password bằng command-line argument**, vì nó có thể lộ trong process list, log hoặc shell history.

Nếu không có profile được kích hoạt, Spring dùng profile mặc định `default`. Production nên chủ động khai báo profile thay vì phụ thuộc vào mặc định có thể trỏ nhầm database.

### 2.2. Phương án YAML nhiều tài liệu

Thay vì nhiều file, có thể dùng `spring.config.activate.on-profile` và phân cách các tài liệu YAML bằng `---`:

```yaml
spring:
  sql:
    init:
      mode: never

---
spring:
  config:
    activate:
      on-profile: dev
  datasource:
    url: jdbc:postgresql://localhost:5432/learning_dev

---
spring:
  config:
    activate:
      on-profile: prod
  datasource:
    url: ${DB_JDBC_URL}
```

Nên chọn cách tổ chức dễ hiểu và tránh lặp property ở nhiều nơi. Không đặt `spring.profiles.active` bên trong tài liệu vốn có `spring.config.activate.on-profile` hoặc file dành riêng cho một profile để cố kích hoạt profile khác; hãy chọn profile qua cấu hình không gắn profile, biến môi trường hoặc cách khởi động.

## 3. Ví dụ cấu hình Spring Data JDBC cho dev, test và prod

Giả sử ứng dụng Spring Boot dùng Gradle cùng cơ chế quản lý phiên bản dependency phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Starter Data JDBC cung cấp hạ tầng repository và Spring JDBC; ứng dụng vẫn cần **JDBC driver** tương ứng database. Trong ví dụ này, dev/prod dùng PostgreSQL; test dùng H2 in-memory. Nếu không có BOM/dependency management, phải khai báo phiên bản dependency tương thích.

### 3.1. File chung: `application.yml`

```yaml
spring:
  application:
    name: spring-data-jdbc-learning
  datasource:
    hikari:
      connection-timeout: 30000
  sql:
    init:
      mode: never
```

`connection-timeout` là thời gian chờ tối đa khi mượn connection từ pool, tính bằng mili giây; đây không phải timeout tối đa của câu SQL. `spring.sql.init.mode: never` tắt tự động chạy script `schema.sql`/`data.sql` bằng SQL initializer của Spring Boot. Nếu dùng Flyway hoặc Liquibase, phải thiết lập dependency và quy trình migration tương ứng. Spring Data JDBC **không mặc định tạo schema bảng chỉ vì có entity/repository**.

### 3.2. File dev: `application-dev.yml`

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL:jdbc:postgresql://localhost:5432/learning_dev}
    username: ${DB_USERNAME:learning_dev}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 5
```

Cú pháp `${DB_JDBC_URL:giá_trị_mặc_định}` cho phép dùng URL local khi không được cấp property từ ngoài. Tương tự, `DB_USERNAME` có fallback chỉ dành cho dev. Mật khẩu `${DB_PASSWORD}` **không có fallback**; khi giá trị bắt buộc thiếu mà Spring cần resolve, quá trình cấu hình sẽ lỗi thay vì thử password mẫu yếu. `learning_dev` là tên tài khoản minh họa cho database local và không nên có quyền trên production.

Mỗi lập trình viên có thể cấp secret từ môi trường riêng mà không phải chỉnh file được commit.

### 3.3. File test: `application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:jdbc_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    hikari:
      maximum-pool-size: 3
```

H2 in-memory tiện cho test đơn giản. `sa` là username mặc định trong ví dụ database H2 in-memory, không phải credential thật của môi trường triển khai. Để bật cấu hình này trong test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CustomerRepositoryTest {
    @Test
    void contextLoads() {
        // Bổ sung schema, fixture và assertions khi kiểm thử thực tế.
    }
}
```

Nếu test truy vấn repository, cần tạo schema bằng migration, `@Sql` hoặc phương án fixture phù hợp; chỉ cấu hình JDBC URL không tự tạo bảng. H2 không mô phỏng hoàn toàn dialect, kiểu dữ liệu, locking và transaction của PostgreSQL. Với integration test phụ thuộc hành vi DB thật, nên dùng PostgreSQL tách biệt (có thể qua Testcontainers), không sử dụng production để chạy test.

### 3.4. File prod: `application-prod.yml`

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX_SIZE:20}
      connection-timeout: 30000
  sql:
    init:
      mode: never
```

Môi trường production phải cấp `DB_JDBC_URL`, `DB_USERNAME` và `DB_PASSWORD` qua nguồn bên ngoài. Không thêm fallback dạng `${DB_PASSWORD:123456}`; nếu thiếu secret, ứng dụng không nên tự chọn một mật khẩu dùng chung. `DB_POOL_MAX_SIZE` có thể có default do đây là tham số hiệu năng, không phải bí mật. Với nhiều instance, tổng số connection có thể vượt giới hạn database dù pool của mỗi instance tương đối nhỏ.

## 4. Cấp thông tin kết nối bằng biến môi trường

Spring Boot có thể ánh xạ tên biến môi trường sang tên property, ví dụ:

| Biến môi trường | Property trong Spring |
| --- | --- |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` |
| `SPRING_DATASOURCE_URL` | `spring.datasource.url` |
| `SPRING_DATASOURCE_USERNAME` | `spring.datasource.username` |
| `SPRING_DATASOURCE_PASSWORD` | `spring.datasource.password` |
| `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `spring.datasource.hikari.maximum-pool-size` |

Có hai cách thường gặp:

**Cách A — dùng placeholder trong YAML:** giữ `url: ${DB_JDBC_URL}`, `username: ${DB_USERNAME}`, `password: ${DB_PASSWORD}`; môi trường cấp các biến `DB_*` tương ứng.

**Cách B — binding trực tiếp:** không đặt URL/username/password trong YAML; môi trường cấp `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME` và `SPRING_DATASOURCE_PASSWORD` để Spring Boot bind trực tiếp vào `DataSource`.

Hai cách đều hợp lệ. Nếu dùng nhiều nguồn đồng thời, phải hiểu thứ tự ưu tiên property của Spring Boot, vì giá trị cuối cùng có thể khác mong muốn.

### Vì sao biến môi trường vẫn cần bảo vệ?

Biến môi trường tách secret khỏi Git, nhưng secret vẫn tồn tại trong ngữ cảnh process. Người có quyền truy cập đủ cao có thể đọc dữ liệu cấu hình, process metadata, memory dump hoặc log debug nếu hệ thống để lộ.

- Cấp biến qua chức năng secret được quản lý của CI/CD, container platform hoặc secret manager.
- Không dùng `echo`/`printenv` để in password, không xuất toàn bộ environment vào log.
- Không nhúng password vào command line, lịch sử terminal, Dockerfile, commit, screenshot hoặc ticket.
- Giới hạn quyền đối với job, container, log, secret và endpoint quản trị.
- Không dựa vào việc che password trong một giao diện log để xem mọi bản sao cấu hình là an toàn.

## 5. Secret file và `configtree:` trong Spring Boot

Nếu nền tảng triển khai mount secret dưới dạng file, Spring Boot có thể nạp bằng **configuration tree**. Ví dụ tại thời điểm chạy container có:

```text
/run/secrets/
└── db_password       # File chứa password thật; không có trong repo
```

Trong `application-prod.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${db_password}
```

Spring Boot đọc tên file `db_password` làm property `db_password` và nội dung file làm giá trị; placeholder `${db_password}` đưa giá trị vào `spring.datasource.password`. Các giá trị URL/username ở ví dụ vẫn do môi trường cấp.

`configtree:/run/secrets/` không có tiền tố `optional:`, nên ứng dụng sẽ báo lỗi khi thư mục bắt buộc không tồn tại. Placeholder không được resolve cũng là lỗi cần khắc phục, thay vì âm thầm tiếp tục với password mặc định.

```text
application-prod.yml
      │
      │ password: placeholder
      ▼
Spring Environment ◀──── configtree:/run/secrets/ ◀──── Secret platform
      │                                             file db_password
      ▼
DataSource / HikariCP
      │
      ▼
PostgreSQL JDBC driver ──────────────────────────────── PostgreSQL
```

File secret ngoài Git vẫn cần filesystem permission chặt, mount chỉ đọc khi phù hợp và quy trình sao lưu an toàn. Không đặt file này vào Docker image layer hay nơi có thể tải công khai.

Trong Kubernetes, `Secret` có thể được mount thành file hoặc biến môi trường. Giá trị Secret viết dưới dạng Base64 trong manifest **không phải mã hóa bảo mật**; cần quản trị RBAC, truy cập etcd, cơ chế mã hóa khi lưu và quyền của workload. Không commit manifest chứa password thật.

### File cấu hình ngoài repository

Spring Boot còn hỗ trợ location bổ sung, chẳng hạn:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/relational-jdbc/
```

Dấu `/` ở cuối cho biết đó là thư mục. Các file tên phù hợp được nạp theo quy tắc cấu hình Spring Boot. Thiếu location bắt buộc sẽ gây lỗi; chỉ dùng `optional:file:/.../` nếu deployment thực sự cho phép không có thư mục này. File ngoài repo vẫn chứa secret nếu có mật khẩu, nên cần kiểm soát người đọc, quyền file, mount và backup.

## 6. Quản lý Git và file cấu hình cục bộ

Một cấu trúc có thể dùng cho nhóm:

```text
project/
├── build.gradle
├── .gitignore
├── .env.example              # Không có credential thật
└── src/
    ├── main/resources/
    │   ├── application.yml
    │   ├── application-dev.yml
    │   └── application-prod.yml
    └── test/resources/
        └── application-test.yml
```

Ví dụ `.env.example` chỉ mô tả hợp đồng cấu hình:

```dotenv
SPRING_PROFILES_ACTIVE=dev
DB_JDBC_URL=jdbc:postgresql://localhost:5432/learning_dev
DB_USERNAME=learning_dev
DB_PASSWORD=REPLACE_WITH_PRIVATE_SECRET
```

`REPLACE_WITH_PRIVATE_SECRET` chỉ là ký hiệu hướng dẫn, không phải password nên sử dụng. Có thể đặt file riêng chứa giá trị thật bên ngoài repo, hoặc để IDE/secret manager cấp biến trực tiếp.

Ví dụ `.gitignore`:

```gitignore
.env
.env.*
!.env.example
secrets/
config/private/
```

`.gitignore` chỉ ngăn theo dõi **file chưa track**. Nếu password đã được commit, xóa nó khỏi phiên bản mới nhất không xóa được lịch sử Git. Cần **đổi/thu hồi credential**, đánh giá mức độ lộ, kiểm tra log/bản sao liên quan và phối hợp xử lý lịch sử repository nếu cần. Secret scanning trong CI/review giúp phát hiện nhầm lẫn sớm.

## 7. Bảo vệ database riêng theo môi trường

`SPRING_PROFILES_ACTIVE=dev` không ngăn việc ứng dụng truy cập production nếu `DB_JDBC_URL` bị cấp nhầm và account có quyền trên production. Phải kết hợp profile với database, tài khoản và quy tắc mạng tách biệt:

| Profile | Database | Tài khoản | Quyền đề xuất |
| --- | --- | --- | --- |
| `dev` | DB dev độc lập | User dev | Không có quyền tới production |
| `test` | DB test có thể tạo lại | User test | Quyền theo nhu cầu migration/fixture kiểm thử |
| `staging` | DB staging | User staging | Dữ liệu được tách hoặc làm sạch theo chính sách |
| `prod` | DB production | User runtime prod | Quyền tối thiểu trên schema/bảng cần thiết |

Các nguyên tắc vận hành:

1. **Least privilege:** chỉ cấp quyền `SELECT`/`INSERT`/`UPDATE`/`DELETE` cần thiết; khi phù hợp, dùng tài khoản riêng cho migration có quyền DDL.
2. **Giới hạn mạng:** chỉ workload được cho phép mới kết nối được cổng database; tài khoản/password không nên là lớp bảo vệ duy nhất.
3. **Mã hóa đường truyền:** bật SSL/TLS và xác minh chứng chỉ theo yêu cầu bảo mật; tham số URL riêng cho PostgreSQL, MySQL hoặc driver khác có thể khác nhau.
4. **Connection pool hợp lý:** giới hạn pool theo tổng số instance và khả năng xử lý của database.
5. **Secret rotation:** có quy trình cấp, thu hồi, thay mật khẩu và làm mới workload khi cần.

### Chuyện gì xảy ra khi đổi mật khẩu?

Connection pool có thể giữ connection đã xác thực. Khi đổi password, connection cũ có thể còn hoạt động, còn connection mới cần credential mới. Thay đổi file secret hoặc biến môi trường **không đồng nghĩa** `DataSource` đang chạy tự nhận giá trị mới. Quy trình rotation phải tính đến cách cập nhật pool, thứ tự triển khai, việc reconnect và khả năng gián đoạn.

## 8. Cấu hình ảnh hưởng thế nào đến Spring Data JDBC?

Giả sử có entity và repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("customers")
record Customer(@Id Long id, String email) {}

interface CustomerRepository extends CrudRepository<Customer, Long> {}
```

Lệnh ứng dụng:

```java
Customer saved = repository.save(new Customer(null, "an@example.test"));
Optional<Customer> found = repository.findById(saved.id());
```

Mã Java giống nhau ở dev và prod. Điểm khác nằm ở cấu hình được nạp khi chạy:

```text
1. Launcher/CI/container cấp SPRING_PROFILES_ACTIVE.
2. Spring Boot nạp application.yml và file/tài liệu theo profile.
3. Biến môi trường hoặc secret file cung cấp giá trị còn thiếu.
4. Spring resolve placeholder và cấu hình DataSource.
5. HikariCP sử dụng JDBC driver để thiết lập connection.
6. Spring Data JDBC repository thực thi SQL qua hạ tầng JDBC.
7. Transaction manager/pool quản lý connection theo ngữ cảnh thực thi.
```

Với service dùng `@Transactional`, hãy để Spring quản lý transaction và connection qua repository, `JdbcTemplate` hoặc `DataSource` đã được cấu hình. Nếu tự gọi `DriverManager.getConnection(...)` bằng URL/password hardcode trong business logic, kết nối đó không tự động tham gia transaction mà Spring đang quản lý.

## 9. Lỗi hay gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Kết nối nhầm môi trường | Profile sai hoặc JDBC URL bị ghi đè từ pipeline | Kiểm tra profile và định danh DB không nhạy cảm |
| `Could not resolve placeholder 'DB_PASSWORD'` | Thiếu biến hoặc mount secret | Kiểm tra secret đã được cấp, **không in giá trị** |
| `Failed to configure a DataSource` | Thiếu driver, JDBC URL không hợp lệ | Kiểm tra dependency runtime, URL, profile |
| `password authentication failed` / `Access denied` | Sai credential/quyền hoặc rotation lệch | Kiểm tra account, quyền database và nguồn secret |
| `Connection refused` / timeout | Host, DNS, port, mạng hoặc database chưa sẵn sàng | Kiểm tra service, network policy và TLS |
| `Table not found` / `relation does not exist` | Schema/migration chưa có, nhầm DB hoặc schema | Kiểm tra migration và database đích |
| Pool exhaustion | Connection leak, transaction dài, quá tải | Quan sát active/idle/pending, thời gian query và transaction |
| Sau rotation vẫn lỗi auth | Pool/workload chưa có credential mới | Kiểm tra vòng đời secret và restart/refresh pool |

Có thể ghi log tên profile và một định danh database đã được làm sạch dữ liệu nhạy cảm. Không log password, token, URL có embedded credential hoặc toàn bộ `Environment`. Endpoint Actuator như `env`/`configprops` vẫn phải giới hạn exposure và quyền truy cập, ngay cả khi Spring có cơ chế masking các giá trị nhạy cảm.

## 10. Bài tập vận dụng

**Bài 1 — Tách hai môi trường.** Tạo `application-dev.yml` dùng PostgreSQL local và `application-test.yml` dùng H2. Chuyển profile qua biến môi trường và `@ActiveProfiles("test")`, xác định repository đang kết nối đúng database.

**Bài 2 — Loại bỏ password khỏi mã nguồn.** Chuyển password hardcode trong YAML dev sang `${DB_PASSWORD}`. Cấp mật khẩu bằng run configuration hoặc secret facility của môi trường. Kiểm tra ứng dụng báo lỗi khi thiếu secret bắt buộc.

**Bài 3 — Thử secret mount.** Trong môi trường riêng, tạo file `/run/secrets/db_password` ngoài repo, nạp bằng `configtree:` và ánh xạ `${db_password}` vào `spring.datasource.password`. Xác định quyền đọc file và trường hợp thiếu mount.

**Bài 4 — Tách quyền thật.** Tạo database/user dành cho test với quyền trên schema riêng, thử thao tác vào schema khác và quan sát database từ chối. Qua đó phân biệt cấu hình profile với cơ chế bảo mật của database.

Tư duy cần giữ trong suốt quá trình phát triển: **chọn profile rõ ràng → nạp cấu hình theo môi trường → nhận secret từ nguồn được bảo vệ → khởi tạo `DataSource` và driver → thực hiện repository/transaction trên database đúng đích với quyền tối thiểu**. Nhờ vậy một codebase Spring Data JDBC có thể chạy trong dev, CI và production mà không cần sửa mã nguồn để đổi credential.
