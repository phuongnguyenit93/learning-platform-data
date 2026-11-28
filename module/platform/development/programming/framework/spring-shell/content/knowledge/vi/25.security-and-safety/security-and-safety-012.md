# Giới hạn quyền của tài khoản và cấu hình dùng để chạy công cụ

Một CLI có thể đọc file, sửa dữ liệu, gọi API hoặc thay đổi tài nguyên của môi trường triển khai. Nếu công cụ chạy bằng tài khoản quản trị, dùng chung credential với ứng dụng khác hoặc nhận cấu hình quá rộng, một lỗi trong command có thể gây ảnh hưởng lớn hơn nhiều so với nhiệm vụ thực tế.

Nguyên tắc quyền tối thiểu (least privilege) yêu cầu mỗi danh tính chỉ có quyền cần thiết để hoàn thành công việc, trong phạm vi tài nguyên và thời gian cần thiết. Với Spring Shell, cần xem xét đồng thời tài khoản hệ điều hành chạy JVM, danh tính người vận hành, tài khoản database, quyền cloud/service và cấu hình runtime. Các lớp này độc lập với nhau: profile Spring chọn cấu hình, còn quyền truy cập phải được kiểm soát bằng cơ chế authorization và ACL tương ứng.

## 1. Phân biệt các danh tính trong một CLI

Một công cụ dòng lệnh có thể hoạt động với nhiều danh tính khác nhau:

| Danh tính | Được dùng ở đâu | Quyền cần giới hạn |
|---|---|---|
| Người chạy command | Người đang mở terminal hoặc khởi chạy script | Các thao tác mà người đó được phép yêu cầu |
| Tài khoản OS của tiến trình | User/group chạy JVM | File, thư mục, thiết bị, socket và process mà JVM truy cập được |
| Database principal | Username/role trong kết nối JDBC | Schema, table, sequence, function và thao tác SQL |
| Workload/service identity | Cloud, secret manager, API hoặc message broker | Tài nguyên và API mà workload được phép gọi |
| Spring Security `Authentication` | Context authorization trong ứng dụng | Authority/permission được gán cho principal hiện tại |

Các danh tính này không tự động giống nhau. Ví dụ, `System.getProperty("user.name")` có thể cho biết tên user mà JVM báo cáo, nhưng không phải bằng chứng xác thực đáng tin cậy để cấp quyền quản trị. Một process chạy bằng tài khoản OS có quyền đọc file cấu hình cũng không đồng nghĩa người đang nhập command có quyền thay đổi mọi dữ liệu trong database.

Hãy xác định rõ từng danh tính và nơi xác thực nó. Không dùng một tài khoản quản trị duy nhất cho terminal người dùng, batch job, database migration và ứng dụng runtime.

## 2. Áp dụng least privilege cho tài khoản hệ điều hành

### Công cụ chạy tương tác

Nếu người dùng khởi chạy CLI trực tiếp từ terminal, tiến trình thường chạy dưới tài khoản OS của người đó. Hãy giữ nguyên quyền của user hiện tại và chỉ yêu cầu nâng quyền cho thao tác thực sự cần thiết.

Không yêu cầu người dùng mở toàn bộ CLI bằng `root`, `Administrator` hoặc `sudo` chỉ vì một command hiếm khi cần quyền cao. Khi cả JVM chạy với quyền quản trị, mọi lỗi parser, thư viện, file import hoặc command khác cũng có thể tận dụng quyền đó.

### Công cụ chạy tự động

Với cron, systemd, Windows Service hoặc CI runner, tạo danh tính riêng cho workload. Tài khoản này chỉ nên:

- Đọc JAR và file cấu hình cần thiết.
- Đọc đúng thư mục input đã được cấp quyền.
- Ghi đúng thư mục output, log hoặc checkpoint.
- Mở kết nối tới endpoint và port cần dùng.
- Đọc secret được cấp riêng cho workload.

Tài khoản chạy tự động thường không cần shell đăng nhập, quyền cài phần mềm, quyền quản trị máy hoặc quyền đọc home directory của người khác.

### Ví dụ tạo tài khoản Linux riêng

```bash
sudo groupadd --system catalog-cli
sudo useradd --system --gid catalog-cli --no-create-home --shell /usr/sbin/nologin catalog-cli
sudo install -d -o root -g catalog-cli -m 0750 /opt/catalog-cli
sudo install -d -o root -g catalog-cli -m 0750 /etc/catalog-cli
sudo install -d -o catalog-cli -g catalog-cli -m 0750 /var/lib/catalog-cli
sudo install -d -o root -g catalog-cli -m 0750 /var/lib/catalog-cli/in
sudo install -d -o catalog-cli -g catalog-cli -m 0750 /var/lib/catalog-cli/out
sudo install -d -o catalog-cli -g catalog-cli -m 0750 /var/lib/catalog-cli/state
sudo install -d -o catalog-cli -g catalog-cli -m 0750 /var/log/catalog-cli
```

Trong ví dụ:

- `/opt/catalog-cli` chứa artifact, user runtime chỉ cần đọc.
- `/etc/catalog-cli` chứa cấu hình, user runtime có quyền đọc theo group.
- `/var/lib/catalog-cli/in` chứa dữ liệu đầu vào, runtime chỉ cần đọc.
- `/var/lib/catalog-cli/out` và `/var/lib/catalog-cli/state` chứa output/checkpoint mà công cụ cần ghi.
- `/var/log/catalog-cli` là nơi ghi log nếu ứng dụng không dùng stdout/stderr của service manager.

Điều chỉnh owner/group theo cách triển khai thực tế. Không cấp quyền ghi vào thư mục chứa JAR nếu tiến trình chỉ cần chạy artifact đó.

### Chạy systemd bằng user/group đã giới hạn

Ví dụ unit file cho một batch command:

```ini
[Service]
Type=oneshot
User=catalog-cli
Group=catalog-cli
WorkingDirectory=/var/lib/catalog-cli
ExecStart=/usr/bin/java -Dspring.shell.interactive.enabled=false -jar /opt/catalog-cli/catalog-cli.jar customer-import --input=/var/lib/catalog-cli/in/customers.csv
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/catalog-cli/out /var/lib/catalog-cli/state /var/log/catalog-cli
```

`User` và `Group` xác định danh tính OS của process. `ProtectSystem=strict` làm hệ thống file gần như chỉ đọc trong sandbox của service; `ReadWritePaths` chỉ mở quyền ghi cho output, state và log. Thư mục input vẫn chỉ đọc. Kiểm tra các tùy chọn hardening với phiên bản systemd và ứng dụng thực tế, vì công cụ có thể cần thêm thư mục tạm, chứng thư hoặc socket.

Với Windows Service, dùng một service identity riêng và NTFS ACL để chỉ cấp quyền đọc JAR/config, đọc input và ghi output cần thiết. Tránh chạy service bằng LocalSystem hoặc tài khoản domain có quyền quản trị rộng nếu công việc không cần những quyền đó.

## 3. Cấp quyền filesystem theo đúng thư mục

Quyền đọc và ghi nên được phân chia theo vai trò:

| Đường dẫn | Quyền runtime thường cần |
|---|---|
| JAR và thư viện | Read/execute |
| File cấu hình không nhạy cảm | Read |
| File chứa credential | Read cho đúng user/group hoặc secret provider |
| Thư mục input | Read; không cần write nếu chỉ import |
| Thư mục output | Write vào đúng thư mục đích |
| Thư mục log/checkpoint | Write theo chính sách lưu trữ |
| Thư mục cài đặt và migration | Chỉ tài khoản triển khai/admin được ghi |

Ví dụ cấu hình Linux chỉ cho owner đọc/ghi và group đọc:

```bash
sudo chown root:catalog-cli /etc/catalog-cli/application-prod.yml
sudo chmod 0640 /etc/catalog-cli/application-prod.yml
sudo chown root:catalog-cli /opt/catalog-cli/catalog-cli.jar
sudo chmod 0640 /opt/catalog-cli/catalog-cli.jar
```

Nếu file chứa secret, giới hạn quyền chặt hơn nữa và ưu tiên secret manager hoặc secret mount. Không đặt secret trong file cấu hình có thể đọc bởi mọi user.

### Giới hạn đường dẫn do người dùng truyền vào

Option như `--input` hoặc `--output` là dữ liệu đầu vào không đáng tin cậy. Không cho phép người dùng chọn tùy ý các file hệ thống chỉ vì JVM có quyền đọc chúng.

Ví dụ kiểm tra file input nằm trong thư mục được cho phép:

```java
import java.io.IOException;
import java.nio.file.Path;

public Path resolveInput(Path allowedRoot, String requested) throws IOException {
    Path root = allowedRoot.toRealPath();
    Path candidate = root.resolve(requested).normalize();
    Path realCandidate = candidate.toRealPath();

    if (!realCandidate.startsWith(root)) {
        throw new SecurityException("Input path is outside the allowed directory");
    }
    if (!java.nio.file.Files.isRegularFile(realCandidate)
            || !java.nio.file.Files.isReadable(realCandidate)) {
        throw new SecurityException("Input file is not readable");
    }
    return realCandidate;
}
```

`normalize()` loại bỏ thành phần `..` về mặt cú pháp; `toRealPath()` phân giải đường dẫn thực và symbolic link. Chỉ kiểm tra `normalize()` là chưa đủ nếu kẻ gọi có thể tạo symlink trỏ ra ngoài thư mục cho phép. Với output file, cần kiểm tra thư mục cha thực, quyền ghi, symlink và chính sách ghi đè trước khi mở file.

Kiểm tra đường dẫn rồi mới mở file vẫn có thể gặp race condition nếu user không tin cậy có quyền thay đổi thư mục hoặc symlink giữa hai bước. Hãy bảo đảm các thư mục gốc không thể bị user không tin cậy sửa; với threat model nghiêm ngặt, dùng API mở file có kiểm soát symlink và giữ handle tới file đã kiểm tra thay vì resolve rồi mở lại bằng tên.

## 4. Tạo database role riêng cho runtime

Không dùng database owner, superuser hoặc tài khoản migration để chạy command hằng ngày. Tạo role runtime có đúng quyền mà các command cần.

Ví dụ PostgreSQL cho công cụ chỉ đọc và ghi một số bảng trong schema `app`:

```sql
CREATE ROLE catalog_cli_runtime LOGIN;

GRANT CONNECT ON DATABASE catalog TO catalog_cli_runtime;
GRANT USAGE ON SCHEMA app TO catalog_cli_runtime;
GRANT SELECT, INSERT, UPDATE
    ON TABLE app.customer, app.import_run, app.import_result
    TO catalog_cli_runtime;
GRANT USAGE
    ON SEQUENCE app.import_run_id_seq, app.import_result_id_seq
    TO catalog_cli_runtime;
```

Ví dụ này không cấp `DELETE`, `TRUNCATE`, `CREATE`, quyền tạo role hoặc quyền cấp quyền cho người khác. Nếu command chỉ đọc dữ liệu, bỏ `INSERT` và `UPDATE`. Nếu một command cần xóa dữ liệu, cân nhắc cấp quyền qua một role riêng hoặc một database function có kiểm soát thay vì cấp `DELETE` cho mọi command.

Role được tạo ở đây chưa chứa password trong câu lệnh mẫu. Hãy cấu hình cơ chế xác thực phù hợp với môi trường (chẳng hạn certificate hoặc password được cấp từ secret manager); không đưa password trực tiếp vào migration script hay repository. Nếu chỉ cần cập nhật một vài cột, cân nhắc column-level `GRANT UPDATE (column_a, column_b)` thay vì quyền cập nhật toàn bộ bảng.

Quyền trên sequence là độc lập với quyền trên table trong PostgreSQL. Nếu lệnh `INSERT` dùng `nextval()` để sinh ID, `USAGE` thường là quyền cần thiết; chỉ cấp thêm `SELECT` hoặc `UPDATE` khi nghiệp vụ thực sự cần đọc `currval()` hoặc thay đổi sequence. Không giả định `GRANT` trên table tự cấp mọi quyền sequence.

### Tách migration principal và runtime principal

Một mô hình thường dùng:

| Principal | Quyền |
|---|---|
| `catalog_schema_owner` | Sở hữu schema/object, chạy migration trong quy trình triển khai |
| `catalog_cli_runtime` | Chỉ `SELECT`/`INSERT`/`UPDATE` trên các bảng nghiệp vụ cần thiết |
| `catalog_cli_readonly` | Chỉ đọc báo cáo hoặc kiểm tra trạng thái |
| `catalog_cli_cleanup` | Quyền xóa giới hạn, chỉ dùng trong tác vụ cleanup riêng nếu cần |

Không đặt password của schema owner vào `application-prod.yml` của CLI runtime. Credential migration nên được cấp riêng trong pipeline triển khai và thu hồi hoặc không còn khả dụng với process runtime.

## 5. Giới hạn quyền tới API và cloud resource

Nếu CLI gọi cloud provider, secret manager, object storage hoặc REST API nội bộ, cấp quyền cho workload theo đúng resource và action.

Ví dụ:

- Công cụ export chỉ cần đọc object trong một bucket/prefix.
- Công cụ import chỉ cần ghi vào một prefix được quy định.
- Công cụ triển khai chỉ cần cập nhật một nhóm tài nguyên trong một environment.
- Công cụ đọc secret chỉ cần truy cập một vài secret/version được chỉ định.

Tránh cấp `Administrator`, `Owner`, `*:*` hoặc quyền đọc tất cả secret chỉ để command chạy được. Không dùng cùng một cloud role cho dev, staging và production nếu quyền hoặc dữ liệu khác nhau.

Với CI/CD, ưu tiên workload identity federation hoặc credential ngắn hạn do nền tảng cấp. Nếu buộc phải dùng credential tĩnh, giới hạn phạm vi, lưu trong secret manager, xoay vòng định kỳ và có quy trình thu hồi khi lộ.

Không lưu access key, private key hoặc token vào JAR, Docker image, Git repository hoặc file script. Không ghi secret vào log hoặc output của command.

## 6. Phân quyền thao tác ở tầng command/service

Quyền OS và database không thay thế authorization nghiệp vụ. Một tài khoản database có thể được phép `UPDATE` bảng `user_account`, nhưng người vận hành chỉ được phép vô hiệu hóa user thuộc một nhóm nhất định.

Hãy kiểm tra quyền tại service method thực hiện hành động. Không chỉ ẩn command khỏi `help` hoặc bỏ menu item; người dùng có thể gọi trực tiếp command nếu nó vẫn được đăng ký.

### Dùng Spring Security method security

Spring Security hỗ trợ authorization ở tầng method qua `@PreAuthorize`, `@PostAuthorize` và các annotation liên quan. Cần bật method security tường minh:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class CliAuthorizationConfiguration {
}
```

Sau đó bảo vệ service method:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class UserAdministrationService {

    @PreAuthorize("hasAuthority('tool:user:disable')")
    public void disableUser(String userId) {
        // Load target, validate scope and update its status.
    }
}
```

`@PreAuthorize` chỉ có tác dụng khi method được gọi qua Spring-managed proxy và `SecurityContext` có `Authentication` đã được xác thực với authority phù hợp. Spring Shell không tự tạo danh tính người dùng đã xác thực chỉ vì một người mở terminal. Ứng dụng CLI phải tích hợp bước đăng nhập, identity provider hoặc workload identity và thiết lập context trước khi gọi service.

Với shell chạy lâu và cho phép đăng nhập/đổi người vận hành trong cùng process, hãy giới hạn `SecurityContext` theo từng invocation hoặc phiên đã xác thực. Nếu ứng dụng tự đặt context, luôn xóa hoặc khôi phục context trong `finally` khi kết thúc phạm vi đó để principal trước không bị dùng nhầm cho command tiếp theo.

Spring Boot Security starter không tự bật method security. Các method không có annotation cũng không tự động được bảo vệ chỉ vì đã thêm `@EnableMethodSecurity`; hãy rà soát toàn bộ service method có side effect và áp dụng chính sách mặc định từ chối.

### Không dùng option làm bằng chứng quyền

Ví dụ sau không phải authorization:

```text
user disable --id=123 --admin=true --force
```

`--admin=true` và `--force` chỉ là dữ liệu người gọi cung cấp. Không dùng chúng để tự gán role hoặc bỏ qua quyền. Nếu có `--force`, nó chỉ nên thay đổi quy trình xác nhận sau khi service đã xác thực người gọi có quyền thực hiện hành động.

### Nếu CLI không dùng Spring Security

Có thể tạo `AuthorizationService` riêng để kiểm tra principal và permission. Dù dùng giải pháp nào, kiểm tra phải diễn ra tại service/use-case trước side effect, nhận identity từ nguồn đã xác thực và từ chối khi không có thông tin hoặc không đủ quyền.

## 7. Cấu hình runtime theo môi trường

Spring Boot externalized configuration cho phép nạp giá trị từ file YAML/properties, profile, environment variables, JVM system properties và các nguồn cấu hình khác. Hãy dùng cấu hình để chọn endpoint, thư mục làm việc, timeout và feature được phép theo môi trường.

Ví dụ `application.yml` chứa default an toàn:

```yaml
spring:
  shell:
    interactive:
      enabled: true

tool:
  workspace:
    input-directory: ./input
    output-directory: ./output
  operations:
    allow-delete: false
    allow-production-write: false
```

Profile `application-production.yml` có thể định nghĩa endpoint và thư mục production:

```yaml
spring:
  shell:
    interactive:
      enabled: false

tool:
  workspace:
    input-directory: /var/lib/catalog-cli/input
    output-directory: /var/lib/catalog-cli/output
```

Ví dụ `spring.shell.interactive.enabled` áp dụng cho Spring Shell 4.x. Nếu ứng dụng dùng Spring Shell 3.x, hãy kiểm tra đúng phiên bản vì mặc định và cách chọn runner đã thay đổi giữa các minor version.

`allow-delete` và `allow-production-write` trong ví dụ là custom application properties, không phải property có sẵn của Spring Shell. Nếu ứng dụng dùng chúng, cần bind và kiểm tra rõ ràng trong code. Một cờ cấu hình không thay thế authorization của principal.

Kích hoạt profile cho một lần chạy:

```bash
SPRING_PROFILES_ACTIVE=production \
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar catalog-cli.jar report-export --format=csv
```

Trong PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "production"
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\catalog-cli.jar report-export --format=csv
```

Profile chọn bộ cấu hình, không cấp quyền cho người dùng. Không coi việc bật profile `admin` hoặc `production` là bằng chứng principal có quyền quản trị.

## 8. Quản lý thứ tự ưu tiên và nguồn cấu hình

Spring Boot nạp cấu hình từ nhiều nguồn. Giá trị ở nguồn có độ ưu tiên cao có thể ghi đè giá trị trong file cấu hình thấp hơn. Với CLI, các nguồn thường gặp gồm:

1. Default properties do `SpringApplication` cung cấp.
2. `@PropertySource` trên configuration class.
3. Config data, gồm `application.yml`, file profile và file cấu hình bên ngoài.
4. `RandomValuePropertySource` cho các property thuộc `random.*`.
5. Environment variables.
6. JVM system properties (`-D...`).
7. `SPRING_APPLICATION_JSON`.
8. Command-line properties `--key=value`.

Đây là thứ tự rút gọn của các nguồn thường gặp trong CLI; Spring Boot còn có các nguồn JNDI, servlet và nguồn riêng cho test. Trong nhóm config data, file profile-specific được ưu tiên hơn file không gắn profile; file bên ngoài JAR có thể ghi đè file đóng gói. Hãy kiểm tra Spring Boot Externalized Configuration khi có nhiều nguồn cùng đặt một property.

`spring.config.additional-location` bổ sung file/vị trí bên ngoài vào các vị trí mặc định; `spring.config.location` thay thế các vị trí mặc định. Ví dụ:

```bash
java \
  -Dspring.config.additional-location=file:/etc/catalog-cli/ \
  -Dspring.profiles.active=production \
  -Dspring.shell.interactive.enabled=false \
  -jar /opt/catalog-cli/catalog-cli.jar report-export
```

Thư mục location kết thúc bằng `/`. Bảo vệ thư mục cấu hình bằng quyền OS; người dùng không có quyền sửa cấu hình runtime không nên có quyền ghi file đó.

Các thuộc tính bootstrap như `spring.config.location`, `spring.config.additional-location` và `spring.profiles.active` cần có sẵn rất sớm trong quá trình khởi động. Đặt chúng bằng environment variables hoặc JVM system properties trước khi ứng dụng tạo context; không dựa vào `@PropertySource` được nạp muộn để chọn file cấu hình ban đầu.

Không đặt secret trong `-D...` hoặc `--key=value` trên command line vì giá trị có thể xuất hiện trong process listing, shell history hoặc log của wrapper. Dùng secret manager hoặc secret mount được bảo vệ.

## 9. Cấp secret cho runtime mà không nhúng vào artifact

Ưu tiên secret manager của nền tảng hoặc workload identity. Khi môi trường triển khai mount secret thành file, Spring Boot có thể nạp config tree:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Ví dụ các file được mount:

```text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
```

Tên file trở thành tên property và nội dung file là giá trị. Ứng dụng có thể dùng `spring.datasource.username` và `spring.datasource.password` như cấu hình thông thường. Với credential bắt buộc, không dùng `optional:` nếu thiếu secret phải khiến ứng dụng dừng khởi động.

Không commit secret vào `application-production.yml`. Không đóng gói secret trong JAR hoặc Docker image vì artifact có thể được phân phối qua nhiều môi trường và khó xoay vòng khi lộ.

## 10. Kiểm tra cấu hình và từ chối khi quyền không đủ

Các cấu hình ảnh hưởng đến bảo mật cần có default an toàn và được kiểm tra ngay khi khởi động:

- Endpoint production phải rõ ràng, không fallback về endpoint test khi cấu hình thiếu.
- Thư mục input/output phải nằm trong vùng cho phép.
- Database username phải là runtime principal, không phải owner/migration account.
- Secret bắt buộc phải tồn tại và đọc được bởi đúng process identity.
- Interactive mode phải tắt trong môi trường automation.
- Các thao tác phá hủy phải mặc định bị vô hiệu hóa nếu chưa có policy và authorization tương ứng.

Nếu không xác định được identity hoặc quyền cần thiết, từ chối thao tác. Không tự động thử lại bằng tài khoản admin hoặc bật chế độ bypass để “cho command chạy được”.

Một command chẩn đoán có thể hiển thị thông tin không nhạy cảm:

```text
runtime profile: production
process user: catalog-cli
database principal: catalog_cli_runtime
workspace: /var/lib/catalog-cli
interactive mode: disabled
```

Không in password, token, secret file content hoặc toàn bộ `Environment`. Nếu ứng dụng không thể xác định an toàn database principal, hãy hiển thị `unknown` thay vì suy đoán từ URL hay tên biến môi trường.

## 11. Audit và giám sát quyền sử dụng

Đối với command thay đổi dữ liệu hoặc tài nguyên, ghi audit event tối thiểu:

- Principal đã xác thực.
- Tên command/use-case.
- Tài nguyên hoặc định danh mục tiêu.
- Thời điểm và correlation/run ID.
- Kết quả: allowed, denied, success hoặc failure.
- Nguồn gọi: interactive, script hoặc automation.

Không ghi password, token, private key hoặc dữ liệu nhạy cảm trong audit event. Với thao tác bị từ chối, ghi lại permission bị thiếu hoặc mã lý do phù hợp nhưng không tiết lộ dữ liệu mà principal không được phép xem.

Định kỳ rà soát các tài khoản không còn dùng, quyền đã cấp, secret cũ, role thành viên và log truy cập. Khi nhân sự rời nhóm hoặc workload ngừng hoạt động, thu hồi quyền và credential tương ứng.

## 12. Kiểm thử bằng danh tính có quyền tối thiểu

Chạy test bằng tài khoản developer/admin thường che khuất lỗi quyền. Integration test nên dùng principal runtime thực tế hoặc một role test có quyền tương đương.

| Kiểm thử | Kết quả cần xác nhận |
|---|---|
| OS user không có quyền đọc thư mục khác | Command bị từ chối khi truy cập ngoài workspace |
| OS user chỉ đọc input | Import đọc được file nhưng không thể sửa file nguồn |
| Runtime DB role | Chỉ truy cập bảng và thao tác đã grant |
| Migration role | Không xuất hiện trong environment runtime |
| Principal thiếu authority | Service method bị từ chối trước side effect |
| Principal đủ authority | Chỉ use-case được cấp quyền chạy thành công |
| Không có Authentication | Command nhạy cảm từ chối theo mặc định |
| Profile thiếu endpoint/secret bắt buộc | Ứng dụng dừng hoặc từ chối command với lỗi cấu hình rõ ràng |
| Config file bị user không tin cậy sửa | Quyền file/ACL ngăn sửa hoặc startup kiểm tra nguồn cấu hình |
| `--force` hoặc `--admin` do người dùng truyền | Không làm tăng authority của principal |
| Script/CI | Dùng workload identity hoặc secret provider đã cấu hình |
| Audit | Có principal/action/result nhưng không có secret |

Với Spring Security, có thể dùng `@WithMockUser` trong test method security để kiểm tra authority. Đồng thời cần ít nhất một integration test chứng minh CLI thực sự thiết lập `SecurityContext` đúng cách; test annotation riêng không chứng minh luồng xác thực terminal đã hoàn chỉnh.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| CLI cần chạy bằng root mới đọc được file | Quyền filesystem được cấp sai hoặc thư mục dùng chung quá chặt | Cấp đúng owner/group/ACL cho đúng đường dẫn |
| Runtime dùng database owner | Tái sử dụng credential migration | Tạo runtime role riêng với quyền table/schema cần thiết |
| Người dùng gọi command admin dù menu đã ẩn | Chỉ ẩn giao diện, không kiểm tra authorization | Kiểm tra permission ở service/use-case |
| `@PreAuthorize` không có tác dụng | Chưa bật `@EnableMethodSecurity`, không đi qua proxy hoặc thiếu Authentication | Kiểm tra security infrastructure và identity context |
| `production` profile được xem như quyền admin | Nhầm cấu hình môi trường với danh tính | Kiểm tra authority riêng, không cấp quyền dựa trên profile |
| Người dùng sửa được file cấu hình | File owner/group/ACL không phù hợp | Chỉ cấp quyền ghi cho deployment/config administrator |
| Secret nằm trong process arguments | Truyền secret bằng `--password` hoặc `-Dpassword` | Dùng secret manager hoặc protected config tree |
| Một service account dùng chung nhiều workload | Khó truy vết và blast radius lớn | Tách identity theo ứng dụng, môi trường và nhiệm vụ |
| Command có `--force` bỏ qua kiểm tra quyền | Tin input là quyền | Xác thực principal và permission độc lập với option |
| Không biết process đang dùng tài khoản nào | Không có diagnostic metadata | Hiển thị OS principal/database principal an toàn hoặc `unknown` |
| Thiếu secret nhưng ứng dụng dùng default | Cấu hình fallback quá rộng | Fail closed khi credential bắt buộc không có |

## 14. Checklist triển khai least privilege

- [ ] Đã phân biệt người vận hành, OS process user, DB principal và workload identity.
- [ ] Interactive CLI chạy bằng tài khoản người dùng thông thường.
- [ ] Batch/service chạy bằng tài khoản riêng, không phải root/Administrator.
- [ ] JAR và thư mục cài đặt chỉ cần read/execute đối với runtime.
- [ ] Input/output/log/config có quyền riêng theo mục đích.
- [ ] Đã giới hạn và kiểm tra đường dẫn do command nhận vào.
- [ ] Database runtime role không có quyền owner, DDL hoặc grant role nếu không cần.
- [ ] Migration principal tách khỏi runtime principal.
- [ ] Cloud/service identity chỉ có quyền trên resource và action cần thiết.
- [ ] Service/use-case kiểm tra authorization trước side effect.
- [ ] Không coi menu ẩn, profile hoặc option `--force` là cơ chế cấp quyền.
- [ ] Method security đã bật và Authentication được thiết lập rõ ràng nếu dùng Spring Security.
- [ ] Config file và secret source có ACL/permission phù hợp.
- [ ] Không truyền secret qua command line hoặc đóng gói trong artifact.
- [ ] Profile runtime được chọn rõ ràng; thiếu cấu hình bắt buộc thì fail closed.
- [ ] Có audit principal/action/target/result mà không ghi secret.
- [ ] Đã kiểm thử bằng tài khoản runtime có quyền tối thiểu.
- [ ] Có quy trình rà soát, xoay vòng và thu hồi quyền/credential.

## Tài liệu tham khảo

1. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) – vị trí file cấu hình, profile, environment variables, system properties và thứ tự ưu tiên.
2. [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) – bật `@EnableMethodSecurity`, `@PreAuthorize` và authorization ở service layer.
3. [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) – least privilege cho CI/CD, workload identity, quản lý và xoay vòng secret.
4. [PostgreSQL – GRANT](https://www.postgresql.org/docs/current/sql-grant.html) – cấp quyền database object và role theo từng loại thao tác.
5. [PostgreSQL – Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) – quyền trên database, schema, table, sequence và object owner.
6. [systemd.exec – User and Group Identity](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html) – chọn `User=`, `Group=` và giới hạn quyền của service process.

Quyền tối thiểu phải được áp dụng ở từng lớp: tài khoản chạy JVM, filesystem, database, API/cloud và authorization của use-case. Hãy cấp đúng quyền cho đúng danh tính, giữ cấu hình theo môi trường ở nguồn được bảo vệ và kiểm tra quyền tại service trước khi thay đổi dữ liệu. Một CLI an toàn cần từ chối thao tác khi identity hoặc cấu hình không rõ ràng, đồng thời có thể giải thích quyền nào đã được dùng mà không tiết lộ secret.
