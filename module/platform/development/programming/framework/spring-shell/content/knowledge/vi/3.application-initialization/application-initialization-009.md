# Tách tham số cấu hình Spring Boot khỏi tham số lệnh

Một ứng dụng Spring Shell có thể nhận tham số ở nhiều thời điểm: JVM nhận tham số khi tạo tiến trình Java, Spring Boot nhận tham số khi khởi tạo `SpringApplication`, còn Spring Shell nhận tên lệnh cùng đối số và tùy chọn của lệnh. Các lớp này có thể cùng xuất hiện trong một dòng chạy ứng dụng. Nếu không phân định rõ, một tùy chọn của lệnh như `--format=csv` có thể đồng thời trở thành thuộc tính trong `Environment` của Spring Boot.

Bài viết trình bày cách phân loại từng nhóm tham số, cách Spring Boot và Spring Shell xử lý đối số, cùng cấu hình để chạy lệnh Spring Shell không tương tác mà vẫn quản lý cấu hình ứng dụng riêng biệt. Ví dụ sử dụng API command của Spring Shell 4.0.x; nếu dự án dùng Spring Shell 3.4.x, hãy đối chiếu tài liệu đúng phiên bản vì cơ chế runner và mặc định chế độ tương tác có khác biệt giữa các major.

## 1. Ba lớp tham số trong một tiến trình CLI

Hãy bắt đầu bằng cách nhìn vào vị trí của tham số trên lệnh chạy:

```bash
java -Xmx512m -Dspring.profiles.active=prod \
  -jar target/catalog-cli.jar export monthly --format=csv
```

Dòng lệnh này chứa ba nhóm thông tin:

| Nhóm | Ví dụ | Thành phần xử lý | Mục đích |
|---|---|---|---|
| Tham số JVM | `-Xmx512m`, `-Dspring.profiles.active=prod` | JVM | Điều chỉnh bộ nhớ hoặc đặt Java System Property trước khi ứng dụng chạy |
| Cấu hình Spring Boot | `spring.profiles.active`, `server.port`, `app.export.directory` | Spring `Environment` và cơ chế externalized configuration | Chọn profile, cổng, endpoint, thư mục dữ liệu và các thiết lập môi trường |
| Tham số lệnh Spring Shell | `export monthly --format=csv` | `ShellRunner` và command parser | Chọn command, đối số vị trí và tùy chọn của lần thực thi |

Tham số JVM nằm trước `-jar` vì JVM cần đọc chúng trước khi nạp ứng dụng. Một tùy chọn `-D` đặt sau tên JAR chỉ còn là application argument, không còn là Java System Property. Các token nằm sau tên JAR được truyền vào phương thức `main(String[] args)` và `SpringApplication.run(...)` dưới dạng application arguments. Spring Boot và Spring Shell có thể cùng đọc các token này theo mục đích riêng.

### Không đồng nhất application arguments với command options

`String[] args` trong `main` là mảng chuỗi thô của tiến trình. Khi truyền mảng này cho `SpringApplication.run(...)`, Spring Boot tạo `ApplicationArguments`, cung cấp cả danh sách chuỗi ban đầu lẫn cách phân loại option và non-option. Spring Shell cũng có thể nhận mảng đối số thô để phân tích thành tên command, argument và option.

Ba khái niệm cần phân biệt:

- **Application arguments:** toàn bộ chuỗi được truyền sau tên JAR vào ứng dụng.
- **Spring Boot command-line properties:** các application argument bắt đầu bằng `--` mà Spring Boot chuyển thành property trong `Environment` theo mặc định.
- **Spring Shell command arguments/options:** các token mà parser của Spring Shell gắn với command đã đăng ký.

Một token có thể đồng thời thuộc nhiều cách nhìn. Ví dụ `--format=csv` có thể là option của command `export`, đồng thời được Spring Boot hiểu là property tên `format` với giá trị `csv` nếu command-line property source vẫn bật.

## 2. Spring Boot xử lý tham số cấu hình như thế nào?

Spring Boot hỗ trợ externalized configuration để cùng một mã nguồn có thể chạy ở nhiều môi trường. Cấu hình có thể đến từ `application.properties`, `application.yml`, profile-specific file, biến môi trường, Java System Properties, JSON cấu hình và command-line arguments.

Theo mặc định, Spring Boot chuyển mọi command-line option bắt đầu bằng `--` thành property trong `Environment`. Ví dụ:

```bash
java -jar catalog-cli.jar --spring.profiles.active=prod --server.port=9090
```

Sau khi khởi động, các bean có thể đọc những giá trị đó bằng `@Value`, `Environment` hoặc `@ConfigurationProperties`. Command-line properties có độ ưu tiên cao hơn cấu hình trong file, vì vậy chúng có thể ghi đè giá trị mặc định của ứng dụng.

Ví dụ cấu hình:

```yaml
app:
  export:
    directory: ./exports
    max-rows: 5000
```

Đọc cấu hình bằng một đối tượng có kiểu:

```java
@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(String directory, int maxRows) {
}
```

Khi bật configuration properties scanning, Spring Boot bind các giá trị dưới prefix `app.export` vào `ExportProperties`. Command có thể dùng đối tượng này để biết thư mục xuất file và giới hạn số dòng mặc định.

### Nguồn cấu hình và độ ưu tiên

Các nguồn cấu hình có thứ tự ưu tiên. Ở những nguồn thường dùng trong ứng dụng CLI, thứ tự từ thấp đến cao là:

1. Giá trị mặc định do ứng dụng khai báo.
2. `application.yml` hoặc `application.properties` được đóng gói trong JAR.
3. File cấu hình theo profile được đóng gói trong JAR.
4. `application.yml` hoặc `application.properties` bên ngoài JAR.
5. File cấu hình theo profile bên ngoài JAR.
6. Biến môi trường của hệ điều hành.
7. Java System Properties, thường được đặt bằng tham số JVM `-D`.
8. `SPRING_APPLICATION_JSON`.
9. Command-line properties của Spring Boot, tức các application arguments bắt đầu bằng `--` khi cơ chế này được bật.

Thứ tự chính xác có thêm một số nguồn dành cho kiểm thử và các môi trường triển khai khác. Khi một giá trị không như mong đợi, hãy xác định property nào đang thắng và nguồn nào đã cung cấp giá trị đó. Spring Boot Actuator có các endpoint `env` và `configprops` hữu ích cho việc chẩn đoán khi ứng dụng đã bật và bảo vệ các endpoint phù hợp.

## 3. Spring Shell xử lý tham số của command như thế nào?

Trong phiên làm việc tương tác, người dùng nhập command tại prompt. Spring Shell parser đọc dòng lệnh và bind token vào các tham số đã khai báo trong command method.

Ví dụ với Spring Shell 4:

```java
@Component
public class ExportCommands {

    private final ExportProperties properties;

    public ExportCommands(ExportProperties properties) {
        this.properties = properties;
    }

    @Command(name = "export", description = "Export a report")
    public String export(
            @Argument(index = 0, defaultValue = "daily") String reportName,
            @Option(longName = "format", defaultValue = "csv") String format) {
        return "Export " + reportName
                + " as " + format
                + " into " + properties.directory()
                + " (max rows: " + properties.maxRows() + ")";
    }
}
```

Ở prompt tương tác, người dùng nhập:

```text
shell:>export monthly --format=json
Export monthly as json into ./exports (max rows: 5000)
```

Trong ví dụ này:

- `export` là tên command.
- `monthly` là argument vị trí thứ nhất, được bind vào `reportName`.
- `--format=json` là option của command, được bind vào `format`.
- `properties.directory()` và `properties.maxRows()` là cấu hình ứng dụng được bind từ Spring `Environment`.

Vì đây là ứng dụng Spring Boot dùng Spring Shell starter, auto-configuration của Spring Shell xử lý đăng ký command. Class chứa command vẫn phải là Spring bean được component scan phát hiện; `@EnableCommand` không bắt buộc trong trường hợp Spring Boot này.

Spring Shell hỗ trợ option dạng dài `--key=value` hoặc `--key value`, và dạng ngắn `-k=value` hoặc `-k value`. Argument vị trí được đánh chỉ số từ 0. Với command có nhiều tham số, nên ưu tiên option có tên rõ nghĩa để người dùng dễ đọc và tránh nhầm thứ tự.

## 4. Vì sao hai bộ phân tích có thể chồng lấn?

Vấn đề xuất hiện rõ nhất khi muốn gọi một command trực tiếp từ terminal thay vì mở prompt tương tác. Giả sử chạy:

```bash
java -jar catalog-cli.jar export monthly --format=csv
```

Spring Shell cần nhận toàn bộ chuỗi để tìm command `export` và bind `monthly`, `--format=csv`. Tuy nhiên, Spring Boot mặc định cũng chuyển `--format=csv` thành property `format=csv` trong `Environment`.

Điều đó có thể tạo ra một số hệ quả:

- Một bean dùng `@Value("${format:json}")` có thể nhận `csv` dù `format` vốn chỉ là tùy chọn của command.
- Một đối tượng `@ConfigurationProperties` có property trùng tên đầy đủ với option, ví dụ `--app.export.directory=...`, có thể bị ghi đè ngoài dự kiến.
- Một `ApplicationRunner` hoặc `CommandLineRunner` tự đọc `ApplicationArguments` có thể nhìn thấy option của command và xử lý nhầm nó thành cấu hình khởi động.
- Người vận hành có thể tưởng rằng `--format` chỉ ảnh hưởng một lần chạy command, trong khi property đó còn tồn tại trong `Environment` của toàn bộ ApplicationContext.

Điểm quan trọng là tiền tố `--` không tự xác định duy nhất thành phần sở hữu token. Spring Boot dùng nó để nhận diện command-line property; Spring Shell dùng nó để nhận diện option của command. Khi chạy command qua process arguments, hai cơ chế cùng có thể quan sát một token.

## 5. Tách command options khỏi Spring Boot Environment

Nếu ứng dụng được thiết kế chủ yếu để chạy một command rồi thoát, có thể yêu cầu Spring Boot không thêm command-line arguments vào `Environment` bằng API `SpringApplication.setAddCommandLineProperties(false)`.

Ví dụ:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogCliApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CatalogCliApplication.class);

        application.setAddCommandLineProperties(false);
        application.run(args);
    }
}
```

Thiết lập này có ý nghĩa cụ thể:

- Spring Boot vẫn nhận application arguments khi gọi `application.run(args)`.
- `ApplicationArguments` vẫn có thể cung cấp source arguments, option names và non-option arguments cho code khởi động.
- Spring Shell vẫn có thể nhận raw arguments qua `ShellRunner` để phân tích command.
- Spring Boot không đăng ký command-line arguments thành một `CommandLinePropertySource` trong `Environment`.

Do đó, `--format=csv` vẫn có thể được Spring Shell bind vào `@Option`, nhưng không còn tự động trở thành property `format` trong `Environment` của Spring Boot.

### Chuyển cấu hình khởi động sang nguồn phù hợp

Sau khi tắt command-line property source, không dùng các tham số `--spring.*` hoặc `--app.*` sau tên JAR để cấu hình Spring Boot nữa. Hãy chuyển những giá trị đó sang file cấu hình, biến môi trường hoặc Java System Properties.

Ví dụ `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false

app:
  export:
    directory: ${APP_EXPORT_DIRECTORY:./exports}
    max-rows: ${APP_EXPORT_MAX_ROWS:5000}
```

Ở đây:

- `spring.shell.interactive.enabled: false` chọn `NonInteractiveShellRunner` để Spring Shell thực thi command từ process arguments rồi kết thúc.
- `APP_EXPORT_DIRECTORY` và `APP_EXPORT_MAX_ROWS` cho phép môi trường triển khai thay đổi cấu hình mà không sửa JAR.
- Giá trị sau dấu `:` trong placeholder là mặc định nếu biến môi trường chưa được đặt.

Khi cần chọn profile hoặc đặt bộ nhớ JVM, có thể dùng Java System Properties và tham số JVM trước `-jar`:

```bash
java -Xmx512m -Dspring.profiles.active=prod \
  -jar target/catalog-cli.jar export monthly --format=csv
```

Trong lệnh này, `-Xmx512m` được JVM xử lý, `-Dspring.profiles.active=prod` trở thành Java System Property mà Spring Boot đọc được, còn `export monthly --format=csv` được truyền vào ứng dụng và Spring Shell phân tích thành command. `spring.shell.interactive.enabled=false` đã được đọc từ `application.yml` trước khi Shell runner được chọn.

Nếu muốn dùng biến môi trường trong PowerShell, có thể đặt trước khi chạy:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:APP_EXPORT_DIRECTORY = ".\reports"
java -jar .\target\catalog-cli.jar export monthly --format=csv
```

## 6. Chọn cách chạy tương tác hay không tương tác

Hai cách chạy có mục đích khác nhau. Hãy chọn rõ chế độ khi thiết kế cách khởi động ứng dụng.

| Chế độ | Cách nhập command | Cấu hình Spring Shell | Trường hợp sử dụng |
|---|---|---|---|
| Interactive | Nhập từng dòng tại prompt | `spring.shell.interactive.enabled=true` hoặc cấu hình mặc định phù hợp phiên bản | Người dùng cần chạy nhiều command trong một phiên, dùng trợ giúp và tự hoàn thành |
| Non-interactive | Truyền tên command và option sau tên JAR | `spring.shell.interactive.enabled=false` | Script, automation, CI hoặc lệnh một lần |

Ví dụ interactive:

```bash
java -jar target/catalog-cli.jar --spring.profiles.active=dev
```

Sau khi ứng dụng mở prompt, nhập:

```text
shell:>export monthly --format=csv
```

Các token người dùng gõ tại prompt do Spring Shell phân tích; chúng không phải application arguments lúc Spring Boot khởi động.

Ví dụ non-interactive:

```bash
java -Dspring.profiles.active=prod -jar target/catalog-cli.jar export monthly --format=csv
```

Với Spring Shell 4.0.x, interactive mode được bật mặc định kể cả khi có command-line arguments. Muốn thực thi command từ process arguments, phải đặt `spring.shell.interactive.enabled=false`. Nếu không, ứng dụng có thể mở prompt thay vì chạy command một lần. Khi đã tắt Boot command-line property source, hãy đặt thuộc tính chọn mode trong `application.yml`, biến môi trường hoặc Java System Property, không đặt nó dưới dạng `--spring.shell.interactive.enabled=false` sau tên JAR.

### Lưu ý khi dùng Spring Shell 3.4.x

Spring Shell 3.3.x trở lên có các runner riêng cho interactive, non-interactive và script; cấu hình bật/tắt từng runner được quản lý bằng các thuộc tính `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled`. Tài liệu dòng 3.3 ghi nhận chỉ `NonInteractiveShellRunner` được bật mặc định từ 3.3.x, trong khi các phiên bản đến 3.2.x bật tất cả runner theo mặc định. Spring Shell 4 thay đổi cách chọn mode: interactive được bật mặc định và phải tắt rõ ràng nếu muốn chạy command từ process arguments. Luôn kiểm tra tài liệu của đúng dòng đang dùng trước khi chuyển cấu hình giữa 3.x và 4.x.

## 7. Khi nào nên giữ command-line properties của Spring Boot?

Không phải ứng dụng nào cũng cần tắt `setAddCommandLineProperties`. Nếu ứng dụng dùng command line chủ yếu để chọn cấu hình lúc khởi động, ví dụ `--spring.profiles.active=prod`, `--server.port=9090` hoặc `--app.export.directory=/data/out`, giữ mặc định của Spring Boot là hợp lý.

Có thể áp dụng các nguyên tắc sau:

- Với ứng dụng interactive, ưu tiên để Spring Boot nhận cấu hình khởi động qua file, biến môi trường, `-D` hoặc command-line property. Command nhập trong prompt do Spring Shell xử lý riêng.
- Với ứng dụng non-interactive, nếu muốn các option sau tên command chỉ thuộc về command, cân nhắc tắt command-line property source và chuyển cấu hình Boot sang file, biến môi trường hoặc `-D`.
- Nếu giữ command-line property source, đặt tên option command rõ ràng và tránh trùng với property mà bean Spring đang bind. Dù vậy, Boot vẫn đưa các option `--...` vào `Environment`.
- Không tắt command-line property source một cách máy móc nếu quy trình triển khai đang phụ thuộc vào `--spring.profiles.active`, `--spring.config.location` hoặc các tham số cấu hình Boot khác.

`setAddCommandLineProperties(false)` chỉ tắt việc đăng ký command-line properties vào `Environment`. Nó không loại bỏ application arguments, không đổi cách JVM xử lý `-D` và không ngăn các `ApplicationRunner`/`CommandLineRunner` đọc chuỗi đối số. Nếu ứng dụng có runner tùy chỉnh, hãy quy định rõ runner nào sở hữu đối số nào và tránh để nhiều thành phần thực thi cùng một tác vụ.

## 8. Kiểm tra ứng dụng sau khi phân tách

Có thể dùng `ApplicationArguments` để quan sát application arguments trong lúc khởi động:

```java
@Component
public class StartupArgumentsLogger implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(StartupArgumentsLogger.class);

    @Override
    public void run(ApplicationArguments args) {
        log.info("Raw arguments: {}", Arrays.toString(args.getSourceArgs()));
        log.info("Option names: {}", args.getOptionNames());
        log.info("Non-option arguments: {}", args.getNonOptionArgs());
    }
}
```

Ví dụ khi chạy `export monthly --format=csv`, `ApplicationArguments` vẫn có thể hiển thị các token này theo cách phân tích option/non-option của Spring Boot. Đây là dữ liệu phục vụ code khởi động; việc Spring Shell bind `monthly` vào `@Argument` và `csv` vào `@Option` là bước xử lý command riêng.

Sau khi cấu hình, kiểm tra các điểm sau:

1. Với interactive mode, ứng dụng mở prompt và command nhập tại prompt được thực thi đúng.
2. Với non-interactive mode, command sau tên JAR được thực thi một lần rồi tiến trình kết thúc.
3. Giá trị cấu hình `app.export.*` đến từ `application.yml`, profile hoặc biến môi trường như dự kiến.
4. Khi `setAddCommandLineProperties(false)` được bật, option command như `--format=csv` không xuất hiện như một command-line property trong `Environment`.
5. `ApplicationArguments` và các runner tùy chỉnh không vô tình xử lý lại option vốn thuộc về command.
6. Kiểm tra output và exit code khi chạy command từ script hoặc CI.

Trong kiểm thử Spring Shell, có thể dùng `ShellTestClient` để tạo phiên interactive hoặc non-interactive và xác nhận command nhận đúng argument/options. Với Spring Shell 3.4.2 trở lên, API kiểm thử non-interactive dùng `nonInteractive(String...)`; kiểm tra tài liệu test của đúng phiên bản để chọn API tương ứng.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Truyền command sau JAR nhưng ứng dụng mở prompt | Spring Shell 4 vẫn bật interactive mode mặc định | Đặt `spring.shell.interactive.enabled=false` trong cấu hình khởi động |
| `@Value("${format}")` nhận giá trị từ `--format=csv` | Boot command-line property source đang bật | Với CLI non-interactive, cân nhắc `setAddCommandLineProperties(false)` |
| Sau khi tắt command-line properties, profile không chuyển sang `prod` | `--spring.profiles.active=prod` không còn được đưa vào Environment | Dùng `-Dspring.profiles.active=prod`, `SPRING_PROFILES_ACTIVE` hoặc profile config phù hợp |
| Tắt command-line properties nhưng Shell không chuyển sang non-interactive | Thuộc tính chọn runner được truyền bằng `--spring.shell.interactive.enabled=false` nên bị bỏ khỏi Environment | Đặt thuộc tính trong YAML, biến môi trường hoặc Java System Property |
| `ApplicationRunner` vẫn nhìn thấy `--format` | `ApplicationArguments` vẫn chứa application arguments | Không xem việc tắt property source là xóa đối số; chỉ để runner đọc những đối số mà nó thực sự sở hữu |
| Giá trị `app.export.directory` không đúng | Nguồn cấu hình có độ ưu tiên cao hơn ghi đè giá trị file | Kiểm tra biến môi trường, Java System Properties, JSON và command-line properties |

## 10. Checklist thiết kế ranh giới tham số

- [ ] Đã xác định tham số nào thuộc JVM, Spring Boot và Spring Shell.
- [ ] Cấu hình môi trường được nhóm dưới prefix riêng, ví dụ `app.export`.
- [ ] Cấu hình nhiều môi trường được đặt trong file/profile hoặc biến môi trường.
- [ ] Command dùng `@Argument` cho dữ liệu vị trí và `@Option` cho tùy chọn có tên.
- [ ] Đã quyết định rõ ứng dụng chạy interactive hay non-interactive.
- [ ] Với Spring Shell 4 chạy command từ process arguments, đã đặt `spring.shell.interactive.enabled=false`.
- [ ] Nếu cần cô lập command options khỏi Spring Boot `Environment`, đã cân nhắc `setAddCommandLineProperties(false)`.
- [ ] Sau khi tắt command-line property source, các tham số Boot trước đây truyền bằng `--...` đã được chuyển sang YAML, biến môi trường hoặc `-D`.
- [ ] Các `ApplicationRunner` và `CommandLineRunner` không xử lý nhầm option của command.
- [ ] Đã kiểm tra cả chế độ interactive và non-interactive cùng output, exit code.

## Tài liệu tham khảo

1. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) – nguồn cấu hình, thứ tự ưu tiên và cách Spring Boot xử lý command-line properties.
2. [Spring Boot – SpringApplication](https://docs.spring.io/spring-boot/reference/features/spring-application.html) – `ApplicationArguments`, `ApplicationRunner`, `CommandLineRunner` và tùy chỉnh `SpringApplication`.
3. [Spring Shell 4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html) – interactive/non-interactive mode và `ShellRunner`.
4. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – cú pháp argument và option của command.
5. [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – đăng ký command bằng annotation và yêu cầu component scanning.
6. [Spring Shell 4 – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – thay đổi giữa Spring Shell 3 và 4.
7. [Spring Shell 3.3 – Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html) – runner và cấu hình chế độ chạy trong dòng 3.x.
8. [Spring Shell – Testing](https://docs.spring.io/spring-shell/reference/testing/basics.html) – kiểm thử command trong chế độ interactive và non-interactive.

Khi thiết kế CLI, hãy giữ cấu hình môi trường ổn định và có thể triển khai độc lập với command mà người dùng đang gọi. Một command nên nhận những đối số mô tả tác vụ hiện tại; Spring Boot nên nhận các giá trị điều khiển cách ứng dụng được khởi tạo và kết nối với môi trường chạy.
