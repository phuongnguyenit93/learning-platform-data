# Truyền cấu hình và dữ liệu đầu vào một cách có thể tái hiện

Một tác vụ CLI chỉ có thể chạy lại đáng tin cậy khi biết rõ nó đã dùng cấu hình nào, dữ liệu đầu vào nào và command nào. Nếu một lần chạy lấy cấu hình từ file mặc định, lần khác lấy từ biến môi trường, còn dữ liệu được nhập trực tiếp trong terminal, rất khó giải thích vì sao hai kết quả khác nhau.

Với Spring Shell 4.x, nên tách rõ bốn loại đầu vào: **cấu hình ứng dụng**, **tham số của command**, **file dữ liệu nghiệp vụ** và **script chứa nhiều command**. Spring Boot cung cấp cơ chế externalized configuration để nạp cấu hình từ YAML, properties, biến môi trường, JVM system properties và command-line properties. Spring Shell `NonInteractiveShellRunner` thực thi một command hoặc một script file. Bài viết kết hợp các cơ chế này thành một quy trình chạy có thể ghi nhận và tái hiện.

## 1. Phân biệt cấu hình, tham số command và dữ liệu đầu vào

Ba loại dữ liệu thường xuất hiện trong một lệnh import:

```bash
java -jar catalog-cli.jar customer-import \
  --input=./data/customers.csv \
  --batch-size=500 \
  --dry-run
```

- **Cấu hình ứng dụng:** các giá trị mặc định hoặc hành vi theo môi trường, ví dụ batch size mặc định, định dạng ngày, timezone, endpoint dịch vụ.
- **Tham số command:** giá trị chỉ áp dụng cho lần gọi này, ví dụ file cần import, mã lần chạy, chế độ dry-run hoặc batch size ghi đè.
- **Dữ liệu nghiệp vụ:** nội dung file CSV/JSON hoặc dữ liệu khác mà command xử lý.
- **Script:** file văn bản chứa một chuỗi command Spring Shell để thực thi theo thứ tự.

Không nên nhầm file script với file dữ liệu. `@commands.txt` là danh sách command; `--input=customers.csv` trỏ tới dữ liệu mà một command xử lý.

| Loại đầu vào | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| Cấu hình dùng chung | `catalog.import.batch-size` | `application.yml`, profile, environment hoặc JVM property |
| Tham số một lần chạy | `--input`, `--dry-run`, `--run-id` | Option/argument của command |
| Dữ liệu lớn | `customers.csv`, `orders.json` | File riêng, object storage hoặc nguồn dữ liệu đã định danh |
| Chuỗi thao tác | `@commands.txt` | Script Spring Shell được quản lý cùng quy trình automation |
| Bí mật | API token, mật khẩu database | Secret store hoặc config tree; không nhúng vào script |

Việc phân loại rõ ràng giúp người vận hành biết giá trị nào cần cố định để tái hiện, giá trị nào được thay đổi theo từng lần chạy và dữ liệu nào cần bảo vệ.

## 2. Đưa cấu hình ra khỏi command

Spring Boot hỗ trợ externalized configuration từ nhiều nguồn. Có thể giữ giá trị mặc định trong `application.yml`, ghi đè theo môi trường bằng `application-prod.yml`, hoặc cung cấp file cấu hình bên ngoài artifact khi triển khai.

Ví dụ `application.yml`:

```yaml
catalog:
  import:
    batch-size: 500
    charset: UTF-8
    date-pattern: yyyy-MM-dd
    zone-id: UTC
    locale: en-US
    delimiter: ","
```

File cấu hình theo profile có thể ghi đè một số giá trị. Ví dụ `application-automation.yml`:

```yaml
catalog:
  import:
    batch-size: 250
```

Kích hoạt profile `automation` khi chạy ứng dụng. Cách truyền profile sẽ được trình bày ở phần sau; với CLI non-interactive, nên đặt cấu hình khởi động qua environment hoặc JVM property để dành process arguments cho command Spring Shell.

### Dùng `@ConfigurationProperties` để bind cấu hình có cấu trúc

Khi có nhiều thuộc tính liên quan, dùng `@ConfigurationProperties` thay vì rải nhiều `@Value` trong command hoặc service.

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.import")
public record ImportProperties(
        @Min(1) int batchSize,
        @NotBlank String charset,
        @NotBlank String datePattern,
        @NotBlank String zoneId,
        @NotBlank String locale,
        @NotBlank String delimiter) {
}
```

Đăng ký quét configuration properties ở lớp ứng dụng:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogCliApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogCliApplication.class, args);
    }
}
```

Khi có dependency Bean Validation phù hợp, các constraint như `@Min` và `@NotBlank` giúp phát hiện cấu hình sai ngay lúc khởi động. Service có thể nhận `ImportProperties` qua constructor và dùng chung một cấu hình đã bind.

Để kích hoạt các constraint Jakarta Validation trên configuration properties, thêm `spring-boot-starter-validation` vào ứng dụng.

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerImportService {

    private final ImportProperties properties;

    public CustomerImportService(ImportProperties properties) {
        this.properties = properties;
    }

    public int defaultBatchSize() {
        return properties.batchSize();
    }
}
```

Với cấu hình dạng record, các giá trị được gom vào một đối tượng bất biến, dễ kiểm tra và dễ ghi lại trong báo cáo lần chạy.

## 3. Hiểu thứ tự ưu tiên của các nguồn cấu hình

Khi cùng một property xuất hiện ở nhiều nguồn, Spring Boot áp dụng thứ tự ưu tiên. Nguồn có ưu tiên cao hơn ghi đè nguồn thấp hơn. Với ứng dụng CLI thông thường, có thể ghi nhớ thứ tự khái quát sau, từ thấp đến cao:

1. Giá trị mặc định do ứng dụng khai báo.
2. Cấu hình trong file được đóng gói cùng JAR.
3. File cấu hình profile được đóng gói cùng JAR.
4. File cấu hình bên ngoài JAR và file profile bên ngoài.
5. Biến môi trường của hệ điều hành.
6. Java system properties (`-Dkey=value`).
7. `SPRING_APPLICATION_JSON`.
8. Command-line properties của Spring Boot (`--key=value`).

Thứ tự chi tiết còn có các nguồn như `@PropertySource`, JNDI và servlet parameters; các nguồn này thường không xuất hiện trong một CLI độc lập. Hãy xem tài liệu Externalized Configuration của đúng phiên bản Spring Boot nếu ứng dụng dùng thêm những nguồn đó.

Ví dụ `catalog.import.batch-size` được đặt là `500` trong `application.yml`, `250` trong `application-automation.yml` và `100` trong biến môi trường `CATALOG_IMPORT_BATCH_SIZE`. Khi profile `automation` được bật, giá trị từ environment có ưu tiên cao hơn file cấu hình và được dùng là `100`.

Không nên để người vận hành phải đoán property nào đang thắng. Với mỗi lần chạy cần tái hiện, hãy ghi lại profile, đường dẫn file cấu hình, các biến môi trường quan trọng (không ghi secret) và các override được truyền vào.

## 4. Chọn đúng `spring.config.location` hoặc `spring.config.additional-location`

Spring Boot có hai property thường dùng để nạp cấu hình ngoài JAR:

- `spring.config.location`: thay thế các vị trí mặc định mà Spring Boot tìm file cấu hình.
- `spring.config.additional-location`: thêm vị trí cấu hình mới bên cạnh các vị trí mặc định. Giá trị từ vị trí bổ sung có thể ghi đè giá trị mặc định.

Trong đa số tình huống triển khai, `spring.config.additional-location` phù hợp hơn vì vẫn giữ các giá trị mặc định đã đóng gói trong ứng dụng.

Ví dụ file `config/automation.yml`:

```yaml
catalog:
  import:
    batch-size: 1000
    charset: UTF-8
    date-pattern: yyyy-MM-dd
    zone-id: UTC
    locale: en-US
    delimiter: ","
```

Có thể chỉ định file này bằng JVM system property trước `-jar`:

```bash
java \
  -Dspring.shell.interactive.enabled=false \
  -Dspring.config.additional-location=file:./config/automation.yml \
  -jar catalog-cli.jar \
  customer-import --input=./data/customers.csv --run-id=import-2026-11-26
```

Nếu file cấu hình bắt buộc phải tồn tại, không dùng tiền tố `optional:`. Khi file không tồn tại, ứng dụng sẽ dừng lúc khởi động và báo lỗi cấu hình thay vì âm thầm chạy bằng default.

Nếu cần thay toàn bộ vị trí tìm kiếm mặc định, dùng `spring.config.location`. Hãy cẩn thận vì các file `application.yml` đã đóng gói có thể không còn được nạp nếu không được thêm lại vào danh sách location.

## 5. Tách cấu hình khởi động khỏi command arguments của Spring Shell

Spring Shell 4 mặc định chạy interactive mode. Để thực thi command từ process arguments, đặt `spring.shell.interactive.enabled=false`. Non-interactive runner nhận một command hoặc script file rồi kết thúc.

Một điểm dễ nhầm là Spring Boot cũng đọc các application arguments bắt đầu bằng `--` và mặc định đưa chúng vào Spring `Environment` như command-line properties. Các property này có độ ưu tiên cao hơn file cấu hình. Vì vậy, nếu dùng cùng một dòng lệnh cho cả cấu hình Boot và option command, cần xác định rõ token nào thuộc lớp nào.

Quy ước dễ tái hiện:

- Đặt property khởi động như profile, config location và interactive mode trong biến môi trường hoặc JVM `-D` trước `-jar`.
- Đặt tên command và option nghiệp vụ sau tên JAR.
- Không dùng cùng một tên cho property Spring Boot và option command nếu chúng mang ý nghĩa khác nhau.
- Không đưa toàn bộ cấu hình nghiệp vụ vào hàng chục option mỗi lần chạy; lưu phần mặc định trong file cấu hình có version.

Ví dụ:

```bash
java \
  -Dspring.shell.interactive.enabled=false \
  -Dspring.profiles.active=automation \
  -Dspring.config.additional-location=file:./config/automation.yml \
  -jar catalog-cli.jar \
  customer-import --input=./data/customers.csv --batch-size=750 --dry-run
```

Ở đây, các tham số `-D...` nằm trước `-jar` là JVM system properties được Spring Boot đọc như cấu hình khởi động. Các token sau tên JAR là command và option mà Spring Shell xử lý.

Nếu ứng dụng chủ động gọi `SpringApplication.setAddCommandLineProperties(false)`, Spring Boot sẽ không thêm `CommandLinePropertySource` vào `Environment`. Thiết lập này chỉ thay đổi cách Boot công bố command-line arguments thành property; nó không thay đổi cú pháp parser của Spring Shell. Hãy giữ config bootstrap ở environment/JVM properties và kiểm thử runner của ứng dụng nếu thay đổi cách xử lý command-line properties.

Với môi trường CI, có thể đặt cùng các giá trị bằng environment variables. Spring Boot dùng relaxed binding nên dấu chấm trong property được đổi thành dấu gạch dưới và tên biến được viết hoa:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
SPRING_PROFILES_ACTIVE=automation \
SPRING_CONFIG_ADDITIONAL_LOCATION=file:./config/automation.yml \
java -jar catalog-cli.jar @commands.txt
```

Trong PowerShell:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
$env:SPRING_PROFILES_ACTIVE = "automation"
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = "file:./config/automation.yml"
java -jar .\catalog-cli.jar "@commands.txt"
```

## 6. Truyền dữ liệu nghiệp vụ bằng file có định danh

Với dữ liệu lớn như CSV, JSON hoặc XML, nên truyền đường dẫn file qua option thay vì đưa nội dung dữ liệu vào command line. Ví dụ:

```text
customer-import --input=./data/customers.csv --run-id=import-2026-11-26
```

Một command có thể khai báo:

```java
import java.nio.file.Path;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    private final CustomerImportService importService;

    public CustomerCommands(CustomerImportService importService) {
        this.importService = importService;
    }

    @Command(name = "customer-import", description = "Import customers from a CSV file")
    public String importCustomers(
            @Option(longName = "input", required = true) String input,
            @Option(longName = "run-id", required = true) String runId,
            @Option(longName = "batch-size") Integer batchSize,
            @Option(longName = "dry-run", defaultValue = "false") boolean dryRun) {

        Path inputFile = Path.of(input);
        return importService.importFile(inputFile, runId, batchSize, dryRun);
    }
}
```

`batchSize` dùng wrapper `Integer` để phân biệt trường hợp người gọi không truyền option. Service có thể dùng giá trị cấu hình `ImportProperties.batchSize()` khi `batchSize == null`; nếu người vận hành truyền `--batch-size`, giá trị đó chỉ ghi đè cho lần chạy hiện tại.

### Xác định rõ working directory

Đường dẫn tương đối như `./data/customers.csv` được phân giải theo working directory của tiến trình. Nếu chạy từ thư mục khác, cùng một command có thể đọc file khác hoặc không tìm thấy file.

Để chạy lại chính xác:

- Quy định working directory trong script/CI.
- Hoặc truyền đường dẫn tuyệt đối.
- Ghi lại đường dẫn đã chuẩn hóa trong log của lần chạy.
- Kiểm tra file tồn tại và có quyền đọc trước khi bắt đầu import.

Không nên dựa vào thư mục hiện tại của IDE hoặc terminal cá nhân khi triển khai automation.

## 7. Cố định encoding, timezone và định dạng dữ liệu

Một file đầu vào giống nhau vẫn có thể cho kết quả khác nếu ứng dụng đọc bằng charset, timezone hoặc quy tắc parse khác nhau. Hãy cấu hình rõ các giá trị có thể phụ thuộc môi trường:

| Thuộc tính | Giá trị nên công bố | Ví dụ |
|---|---|---|
| Encoding | UTF-8 hoặc charset đã thống nhất | `charset: UTF-8` |
| Ngày | Mẫu ngày rõ ràng | `date-pattern: yyyy-MM-dd` |
| Timezone | Tên vùng thời gian hoặc UTC | `zone-id: UTC` |
| Locale | Locale cụ thể khi parse/format | `locale: vi-VN` hoặc `en-US` |
| CSV delimiter | Ký tự phân cách cố định | `delimiter: ","` |
| Decimal separator | Dấu thập phân đã quy ước | `.` |
| Sort order | Thứ tự xử lý rõ ràng | `customer-id ASC` |

Ví dụ đọc file với charset cấu hình rõ ràng:

```java
import java.io.BufferedReader;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;

Charset charset = Charset.forName(properties.charset());
try (BufferedReader reader = Files.newBufferedReader(inputFile, charset)) {
    // Parse rows with the configured date pattern and delimiter.
}
```

Đoạn code trên giả định service đã nhận `ImportProperties` qua constructor và `inputFile` là đường dẫn đã được xác thực. Với ngày giờ, không dùng timezone mặc định của máy nếu kết quả nghiệp vụ phụ thuộc thời điểm. Với số thập phân, không để parser tự suy đoán dấu phẩy hay dấu chấm từ locale máy chạy.

## 8. Chạy nhiều command bằng script `@file`

Trong Spring Shell 4, `NonInteractiveShellRunner` hỗ trợ chạy một command hoặc một script chứa nhiều command. Script được truyền bằng cách đặt ký tự `@` trước tên file trong process arguments.

Ví dụ `commands.txt`:

```text
help
customer-import --input=./data/customers.csv --run-id=customers-2026-11-26 --dry-run
customer-import --input=./data/orders.csv --run-id=orders-2026-11-26 --dry-run
```

Chạy script:

```bash
java \
  -Dspring.shell.interactive.enabled=false \
  -Dspring.config.additional-location=file:./config/automation.yml \
  -jar catalog-cli.jar \
  @commands.txt
```

Mỗi dòng là một command Spring Shell. Giữ script ở version control hoặc phát hành cùng bộ automation để có thể xem lại chính xác chuỗi thao tác đã chạy.

Script `@commands.txt` không phải file CSV/JSON đầu vào của command. Nó chứa cú pháp command; mỗi command có thể tham chiếu đến một file dữ liệu riêng qua `--input`.

### Quy tắc tổ chức script

- Một command trên mỗi dòng để dễ đọc và truy vết.
- Ghi chú mục tiêu và thứ tự chạy bằng comment theo cú pháp script được phiên bản Spring Shell đang dùng hỗ trợ.
- Dùng tên file dữ liệu và run ID rõ ràng.
- Không đặt mật khẩu hoặc token trực tiếp trong script.
- Giữ đường dẫn ổn định hoặc xác định working directory trước khi chạy.
- Tách bước kiểm tra đầu vào, chạy dry-run và chạy ghi dữ liệu thành các command riêng nếu quy trình cần xác nhận.

## 9. Không dùng file script thay cho stdin một cách mặc định

`@commands.txt` là cơ chế nạp **các dòng command** của Spring Shell non-interactive runner. Nó không tự biến nội dung file thành stdin của command nghiệp vụ.

Nếu command cần đọc dữ liệu từ stdin, ứng dụng phải triển khai và kiểm thử cơ chế đọc stdin một cách tường minh. Nếu chưa có hợp đồng đó, hãy dùng option như `--input=path/to/file.csv` để chỉ rõ nguồn dữ liệu. Cách này giúp log, kiểm tra quyền đọc và tính toán checksum của dữ liệu dễ hơn.

Không giả định rằng lệnh kiểu Unix `cat data.csv | java -jar app.jar import` sẽ tự động đưa nội dung CSV vào tham số command. Hành vi pipe phụ thuộc vào cách ứng dụng đọc `System.in` hoặc input provider; Spring Shell non-interactive runner không tự định nghĩa quy ước stdin cho mọi command nghiệp vụ.

## 10. Quản lý secret riêng khỏi script và command arguments

Không truyền password, API token hoặc private key trực tiếp trong script hoặc option command nếu có thể tránh. Các giá trị này có thể xuất hiện trong shell history, danh sách process, log CI hoặc báo cáo chạy.

Với triển khai hỗ trợ mounted secret files, Spring Boot có thể nạp cấu hình dạng config tree:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Ví dụ volume:

```text
/run/secrets/
  catalog.api-token
  catalog.database.password
```

Tên file trở thành tên property; nội dung file trở thành giá trị. Service có thể nhận các property này qua `@ConfigurationProperties` hoặc `Environment`. Với hệ thống có secret manager, dùng integration phù hợp để cấp secret theo quyền và vòng đời của workload.

Chỉ thêm tiền tố `optional:` nếu ứng dụng thực sự được phép khởi động khi thư mục secret chưa được mount. Với credential bắt buộc, để location là bắt buộc và kiểm tra property cần thiết lúc khởi động.

Secret không nên được ghi vào manifest tái hiện. Chỉ ghi nguồn secret hoặc phiên bản secret nếu hệ thống quản lý secret cung cấp định danh an toàn; không ghi nội dung secret hoặc giá trị hash có thể giúp dò secret yếu.

## 11. Tạo manifest để ghi lại một lần chạy

Để tái hiện một lần import, chỉ lưu command là chưa đủ. Cần ghi lại phiên bản ứng dụng, cấu hình, profile, dữ liệu đầu vào và các tham số có ảnh hưởng đến kết quả.

Ví dụ manifest không chứa secret:

```yaml
run:
  id: customers-2026-11-26
  command: customer-import
  application-version: 1.4.2
  spring-shell-version: 4.0.4
  active-profile: automation
  config-file: config/automation.yml
  config-sha256: 9b1d...example
  input-file: data/customers.csv
  input-sha256: 2a7c...example
  input-size-bytes: 184320
  charset: UTF-8
  date-pattern: yyyy-MM-dd
  zone-id: UTC
  locale: en-US
  delimiter: ","
  batch-size: 500
  dry-run: true
```

Các chuỗi checksum ở ví dụ chỉ minh họa định dạng; khi triển khai cần tính SHA-256 thực tế trên file cấu hình và dữ liệu. Nếu config file chứa secret, không lưu nguyên file hoặc checksum của toàn bộ secret-bearing file vào nơi công khai; hãy tách cấu hình không nhạy cảm khỏi secret và ghi nhận phiên bản/định danh an toàn của nguồn secret.

Tính checksum trên Linux:

```bash
sha256sum config/automation.yml data/customers.csv
```

Trên macOS:

```bash
shasum -a 256 config/automation.yml data/customers.csv
```

Trên Windows PowerShell:

```powershell
Get-FileHash .\config\automation.yml -Algorithm SHA256
Get-FileHash .\data\customers.csv -Algorithm SHA256
```

Manifest nên được ghi cùng log hoặc artifact của pipeline. Nó giúp xác định chính xác dữ liệu và tham số nào đã tạo ra kết quả, đồng thời hỗ trợ so sánh hai lần chạy.

## 12. Kiểm tra cấu hình thực tế trước khi chạy

Khi một property có giá trị khác mong đợi, kiểm tra các nguồn theo thứ tự ưu tiên. Với ứng dụng có Spring Boot Actuator và được phép bật endpoint quản trị, `env` và `configprops` có thể giúp xác định property source và giá trị đã bind. Không mở các endpoint này công khai chỉ để debug CLI.

Trong ứng dụng CLI nhỏ, có thể cung cấp command chẩn đoán chỉ hiển thị các cấu hình không nhạy cảm:

```java
@Command(name = "config-show", description = "Show effective import settings")
public String showConfig() {
    return "batch-size=" + properties.batchSize()
            + ", charset=" + properties.charset()
            + ", date-pattern=" + properties.datePattern()
            + ", zone-id=" + properties.zoneId()
            + ", locale=" + properties.locale()
            + ", delimiter=" + properties.delimiter();
}
```

Không in token, mật khẩu hoặc toàn bộ `Environment`. Command chẩn đoán nên chọn danh sách property được phép hiển thị và ghi rõ nguồn nếu ứng dụng có khả năng truy xuất nguồn đó.

Có thể bật log cấu hình ở mức trace trong thời gian điều tra:

```bash
java -Dlogging.level.org.springframework.boot.context.config=TRACE \
  -Dspring.shell.interactive.enabled=false \
  -jar catalog-cli.jar config-show
```

Log trace có thể tiết lộ đường dẫn file hoặc chi tiết cấu hình. Chỉ bật trong môi trường kiểm soát và rà soát log trước khi chia sẻ.

## 13. Ví dụ quy trình automation có thể chạy lại

Một pipeline import khách hàng có thể tổ chức thành các artifact:

```text
automation/
├── config/
│   └── automation.yml
├── scripts/
│   └── import-customers.txt
├── data/
│   └── customers.csv
└── runs/
    └── customers-2026-11-26.yml
```

`config/automation.yml` chứa batch size, charset, date format, timezone, locale và delimiter. `scripts/import-customers.txt` chứa command. `data/customers.csv` là dữ liệu. Manifest trong `runs/` ghi version, profile, checksum và các tham số thực tế.

Chạy dry-run trước:

```bash
java \
  -Dspring.shell.interactive.enabled=false \
  -Dspring.profiles.active=automation \
  -Dspring.config.additional-location=file:./automation/config/automation.yml \
  -jar catalog-cli.jar \
  customer-import \
  --input=./automation/data/customers.csv \
  --run-id=customers-2026-11-26 \
  --dry-run
```

Sau khi kiểm tra kết quả, chạy script hoặc command chính thức với run ID được ghi nhận. Với thao tác ghi dữ liệu, service nên hỗ trợ idempotency hoặc cơ chế chống chạy lặp dựa trên run ID nếu nghiệp vụ yêu cầu. Cùng một input được chạy lại không nên vô tình tạo bản ghi trùng hoặc áp dụng side effect hai lần.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chạy lại cùng command nhưng kết quả khác | Profile, env hoặc config file khác | Ghi active profile, nguồn cấu hình và checksum |
| Property không nhận giá trị trong file ngoài | Dùng sai `spring.config.location` hoặc đường dẫn | Dùng `spring.config.additional-location` khi muốn bổ sung và kiểm tra URI `file:` |
| Giá trị trong file bị ghi đè ngoài dự kiến | Environment, JVM hoặc command-line property có ưu tiên cao hơn | Kiểm tra thứ tự property source và các override |
| Spring Shell báo không nhận ra `--spring.config...` | Bootstrap property bị đặt sau tên JAR và bị runner xem như command input | Đưa property vào environment hoặc `-D` trước `-jar` |
| File input không tìm thấy trong CI | Working directory khác môi trường phát triển | Dùng working directory cố định hoặc đường dẫn tuyệt đối |
| CSV đọc sai dấu tiếng Việt | Charset không được cố định | Dùng UTF-8 rõ ràng và kiểm tra file thực tế |
| Ngày bị lệch một ngày hoặc lệch giờ | Timezone hoặc định dạng ngày phụ thuộc máy | Cố định date pattern và zone ID |
| Script chạy được nhưng không đọc CSV | Nhầm `@commands.txt` là stdin dữ liệu | Dùng `--input` để trỏ file nghiệp vụ hoặc triển khai stdin tường minh |
| Bí mật xuất hiện trong log | Truyền token/mật khẩu qua option hoặc in toàn bộ cấu hình | Dùng secret store/config tree và redaction |
| Chạy lại import tạo dữ liệu trùng | Command không có run ID/idempotency | Định nghĩa khóa lần chạy và chính sách xử lý lặp |

## 15. Checklist trước khi đưa script vào CI/CD

- [ ] Đã tách cấu hình ứng dụng, command options, file dữ liệu và script.
- [ ] Cấu hình mặc định nằm trong file có version và được bind bằng `@ConfigurationProperties`.
- [ ] Đã xác định profile và nguồn override cho từng môi trường.
- [ ] Dùng `spring.config.additional-location` khi cần thêm file ngoài JAR; hiểu rằng `spring.config.location` thay thế vị trí mặc định.
- [ ] Đã đặt `spring.shell.interactive.enabled=false` cho non-interactive run.
- [ ] Đặt cấu hình bootstrap bằng environment hoặc JVM `-D` trước `-jar`.
- [ ] Process arguments sau JAR chỉ chứa command và dữ liệu điều khiển lần chạy.
- [ ] File dữ liệu có đường dẫn ổn định, charset và định dạng rõ ràng.
- [ ] Đã cố định timezone, locale, delimiter và thứ tự xử lý nếu chúng ảnh hưởng kết quả.
- [ ] Script `@file` chỉ chứa command; file dữ liệu được truyền riêng cho command.
- [ ] Secret được cấp qua secret store/config tree, không nhúng vào script hoặc manifest.
- [ ] Có run ID, version ứng dụng, checksum config và checksum input.
- [ ] Có dry-run, kiểm tra input và idempotency phù hợp trước side effect.
- [ ] Đã thử chạy lại cùng artifact, config và input trong môi trường tương đương.

## Tài liệu tham khảo

1. [Spring Shell 4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html) – interactive/non-interactive mode và property `spring.shell.interactive.enabled`.
2. [Spring Shell 4 – `NonInteractiveShellRunner` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html) – chạy một command hoặc script file với tiền tố `@`.
3. [Spring Boot 4 – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) – nguồn cấu hình, thứ tự ưu tiên, file ngoài JAR, config location, config tree và `@ConfigurationProperties`.
4. [Spring Boot 4 – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) – kích hoạt profile và quy tắc ghi đè profile.
5. [Spring Boot – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties) – bind cấu hình có cấu trúc và validation.

Một lần chạy có thể tái hiện khi command, profile, cấu hình hiệu lực, dữ liệu, định dạng và phiên bản ứng dụng đều được xác định. Hãy lưu cấu hình trong file có version, truyền dữ liệu qua file có định danh, tách secret khỏi script và ghi manifest của từng lần chạy. Cách tổ chức này giúp người khác có thể kiểm tra và chạy lại cùng một quy trình mà không phải đoán các giá trị ẩn trong terminal cá nhân.
