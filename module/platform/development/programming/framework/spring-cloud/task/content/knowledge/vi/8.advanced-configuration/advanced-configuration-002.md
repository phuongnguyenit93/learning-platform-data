# Thứ tự ưu tiên cấu hình, biến môi trường và tham số dòng lệnh

## Mục tiêu và bối cảnh

Một ứng dụng **Spring Cloud Task** xử lý công việc hữu hạn như tổng hợp hóa đơn, nhập dữ liệu, đối soát hoặc chạy một Spring Batch Job. Khi khởi chạy ở môi trường phát triển, kiểm thử và production, cùng một file JAR có thể dùng **cấu hình khác nhau** mà không cần biên dịch lại. Điều này đặc biệt quan trọng với `DataSource` của `TaskRepository`, thời gian chờ, kích thước lô xử lý, profile, secret và yêu cầu nghiệp vụ của từng lần chạy.

Ví dụ, tác vụ đối soát có `task.worker.batch-size=200` trong `application.yml`, nhưng Kubernetes đặt `TASK_WORKER_BATCHSIZE=500`, còn lệnh khởi chạy chứa `--task.worker.batch-size=1000`. **Giá trị cuối cùng là bao nhiêu, ai đã ghi đè và thay đổi này ảnh hưởng đến lần chạy nào?** Đó là chủ đề của bài.

Sau bài học, bạn có thể:

- Giải thích cách Spring Boot tạo `Environment` từ nhiều nguồn và **nguồn nào có quyền ghi đè**.
- Phân biệt cấu hình đóng gói, cấu hình theo profile, file ngoài JAR, biến môi trường, Java system properties và option `--...`.
- Chuyển tên thuộc tính sang biến môi trường theo quy tắc **relaxed binding**.
- Dùng `@ConfigurationProperties`, `ApplicationArguments` và placeholders để cấu hình Spring Cloud Task rõ ràng.
- Phát hiện lỗi ghi đè `TaskRepository`, tránh đưa secret lên dòng lệnh và kiểm chứng cấu hình trước khi triển khai.

## 1. Mô hình: nhiều nguồn, một giá trị hiệu lực

Spring Boot không giới hạn cấu hình trong `application.yml`. Khi khởi động, framework xây dựng một tập các `PropertySource` trong `Environment`. Cùng một tên thuộc tính có thể được định nghĩa ở nhiều nơi; **nguồn có độ ưu tiên cao hơn cung cấp giá trị hiệu lực**. Bean có thể đọc giá trị thông qua `Environment`, `@Value`, hoặc binding kiểu dữ liệu bằng `@ConfigurationProperties`.

```mermaid
flowchart TD
    A[application.yml và application-{profile}.yml] --> E[Spring Environment]
    B[File ngoài JAR / config import] --> E
    C[OS environment và Java -D] --> E
    D[SPRING_APPLICATION_JSON và --key=value] --> E
    E --> F[Binding và cấu hình bean Spring Boot / Spring Cloud Task]
    F --> G[TaskRepository, DataSource, ApplicationRunner]
    H[Business args: --business-date=...] --> I[ApplicationArguments]
    I --> G
```

Sơ đồ tách **hai cách tiêu thụ đối số** nhưng không có nghĩa hệ thống tự động tách chúng: theo mặc định, **mọi option `--key=value`** sau tên JAR vừa nằm trong `ApplicationArguments`, vừa được Spring Boot đưa vào `Environment`. Tên `--business-date=...` thường do nghiệp vụ đọc; tên `--spring.datasource.url=...` là cấu hình hạ tầng; cả hai vẫn là option dòng lệnh. Ranh giới thực tế do hợp đồng đầu vào và quyền của bên khởi chạy quyết định.

## 2. Thứ tự ưu tiên chính thức của các nguồn cấu hình

Tài liệu [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) mô tả thứ tự các `PropertySource`. Bảng dưới **đi từ ưu tiên thấp lên cao**: nguồn phía dưới có thể ghi đè cùng thuộc tính do nguồn phía trên đặt.

| Thứ tự tăng dần | Nguồn | Ví dụ / vai trò |
| --- | --- | --- |
| 1 | Default properties của `SpringApplication` | Giá trị mặc định do ứng dụng lập trình bằng `setDefaultProperties(...)` |
| 2 | `@PropertySource` trên lớp `@Configuration` | Bổ sung file properties tùy chỉnh; được đăng ký tương đối muộn |
| 3 | **Config data** | `application.yml`, file theo profile, file ngoài JAR, `spring.config.import` |
| 4 | `RandomValuePropertySource` | Các key `random.*`, thường không ảnh hưởng đến key nghiệp vụ |
| 5 | **Biến môi trường hệ điều hành** | `TASK_WORKER_BATCHSIZE=500`, `SPRING_DATASOURCE_URL=...` |
| 6 | **Java system properties** | `java -Dtask.worker.batch-size=700 -jar app.jar` |
| 7–9 | JNDI và tham số servlet context/config | Có ý nghĩa khi chạy trong ứng dụng web/container tương ứng |
| 10 | **`SPRING_APPLICATION_JSON`** | JSON chứa nhiều thuộc tính, được xử lý thành một `PropertySource` riêng |
| 11 | **Command-line options** | `java -jar app.jar --task.worker.batch-size=1000` |
| 12–14 | Thuộc tính do test cung cấp | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`; có ưu tiên cao trong kiểm thử |
| 15 | Devtools global settings | Chỉ liên quan khi Devtools đang hoạt động |

**Trong production thông thường:** `application.yml` < biến môi trường < Java `-D` < `SPRING_APPLICATION_JSON` < `--key=value`. Đây là cách nhớ hữu ích, nhưng **không phải toàn bộ ma trận**: profile, đường dẫn file, config import và nguồn thêm bởi thư viện có thể làm việc truy nguồn phức tạp hơn. Khi kiểm tra thực tế, luôn xem `Environment` và nguồn gốc thuộc tính.

Đặc biệt, `@PropertySource` chỉ được nạp khi `ApplicationContext` đang refresh. Một số cấu hình như `logging.*` và `spring.main.*` được đọc **sớm hơn**, nên không nên đặt chúng ở `@PropertySource` với kỳ vọng có thể điều khiển giai đoạn khởi động. Các key `spring.config.name`, `spring.config.location` và `spring.config.additional-location` cũng phải có từ **giai đoạn bootstrap**, chẳng hạn qua biến môi trường, Java system property hoặc CLI.

## 3. Thứ tự bên trong nhóm file cấu hình (Config Data)

Trong thiết lập thông dụng, Spring Boot tìm file `application.properties` hoặc `application.yml` ở classpath và những vị trí bên ngoài JAR, ví dụ thư mục hiện tại, `./config/` và các thư mục con trực tiếp của `./config/`.

Thứ tự sau đi từ ưu tiên thấp đến cao trong phạm vi các file `application`:

1. `application.yml` **đóng gói trong JAR**.
2. `application-{profile}.yml` **đóng gói trong JAR**, ví dụ `application-prod.yml`.
3. `application.yml` **bên ngoài JAR**.
4. `application-{profile}.yml` **bên ngoài JAR**.

Ví dụ nội dung đóng gói:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: settlement-task
  main:
    web-application-type: none

task:
  worker:
    batch-size: 200
    timeout: 30s
```

```yaml
# src/main/resources/application-prod.yml
task:
  worker:
    batch-size: 300
    timeout: 45s
```

Nếu chạy với profile `prod`, nhưng **không có nguồn ưu tiên cao hơn**, `batch-size` hiệu lực là `300` và `timeout` là `45s`. Nếu tạo file `./config/application-prod.yml` bên ngoài JAR với:

```yaml
task:
  worker:
    batch-size: 400
```

thì khi khởi chạy từ thư mục có `./config/`, `batch-size` là `400`, còn `timeout` vẫn `45s`, vì file ngoài JAR chỉ ghi đè thuộc tính nó khai báo. **Thư mục làm việc của tiến trình** ảnh hưởng đến việc tìm `./config/`; trong Docker/Kubernetes, hãy kiểm tra `WORKDIR` và nơi mount file thay vì giả định luôn là thư mục chứa JAR.

Nếu ở **cùng vị trí** có cả `application.properties` và `application.yml`, Spring Boot ưu tiên `.properties`; tốt nhất chuẩn hóa một định dạng để tránh khó truy vết. Trong file YAML nhiều document ngăn bằng `---`, document có thứ tự ưu tiên cao hơn và điều kiện profile phù hợp có thể ghi đè tài liệu trước. Đừng tự suy rằng profile từ tên file luôn thắng mọi nguồn khác: **biến môi trường và CLI vẫn có thể ghi đè**.

### `spring.config.location` so với `spring.config.additional-location`

```bash
# Chỉ định vị trí cấu hình cụ thể; thay danh sách vị trí tìm mặc định:
java -jar settlement-task.jar \
  --spring.config.location=optional:file:./runtime-config/ \
  --business-date=2026-11-23

# Giữ vị trí mặc định và bổ sung nơi bên ngoài để override:
java -jar settlement-task.jar \
  --spring.config.additional-location=optional:file:./runtime-config/ \
  --business-date=2026-11-23
```

- `spring.config.location` **thay** danh sách địa điểm tìm kiếm mặc định; nếu vô tình bỏ classpath location, cấu hình trong JAR có thể không được nạp như dự định.
- `spring.config.additional-location` **thêm** địa điểm vào cấu hình mặc định; thường phù hợp khi muốn một lớp override theo môi trường.
- Đường dẫn thư mục cần dấu `/` ở cuối. Tiền tố `optional:` cho phép vị trí **không tồn tại** mà vẫn khởi động; không dùng `optional:` cho cấu hình bắt buộc, vì một lỗi mount/đường dẫn có thể bị che khuất.
- `spring.config.import` trong một file có thể nạp thêm config data; giá trị ở tài liệu được import **có thể ghi đè** tài liệu khai báo import. Đây là một quy tắc riêng cần xét khi nhiều lớp file cùng khai báo một key.

Ví dụ import:

```yaml
spring:
  config:
    import: optional:file:./runtime-config/task-override.yml
```

Nếu file `task-override.yml` tồn tại và đặt `task.worker.batch-size: 600`, giá trị được import có thể ghi đè giá trị cùng key trong file chứa `spring.config.import`. `optional:` chỉ xử lý **trường hợp không tìm thấy** location; file tồn tại nhưng không parse được vẫn có thể làm khởi động thất bại. Với nhiều import và nhiều profile, dùng quy tắc rõ ràng, không dựa vào suy đoán thứ tự.

## 4. Biến môi trường và relaxed binding

Hầu hết shell không hỗ trợ dấu chấm `.` hoặc dấu gạch nối `-` trong tên biến môi trường thông thường. Spring Boot hỗ trợ chuyển từ tên thuộc tính dạng chuẩn (*canonical kebab case*) sang biến môi trường theo đúng ba bước:

1. Thay mọi dấu chấm `.` bằng dấu gạch dưới `_`.
2. **Bỏ** dấu gạch nối `-` (không thay bằng `_`).
3. Chuyển toàn bộ thành chữ hoa.

| Thuộc tính canonical | Tên biến môi trường phù hợp | Vai trò |
| --- | --- | --- |
| `task.worker.batch-size` | `TASK_WORKER_BATCHSIZE` | Kích thước lô dữ liệu |
| `task.worker.timeout` | `TASK_WORKER_TIMEOUT` | Thời gian chờ của worker |
| `spring.application.name` | `SPRING_APPLICATION_NAME` | Tên Task được Spring Cloud Task sử dụng làm metadata |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` | JDBC URL cho DataSource/TaskRepository |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` | Tài khoản DB |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` | Chọn profile khởi động |
| `spring.cloud.task.initialize-enabled` | `SPRING_CLOUD_TASK_INITIALIZEENABLED` | Bật/tắt khởi tạo schema Task theo cấu hình |
| `task.worker.retries[0].delay` | `TASK_WORKER_RETRIES_0_DELAY` | Minh họa phần tử đầu tiên của list |

Sai lầm thường gặp: dùng `TASK_WORKER_BATCH_SIZE` rồi nghĩ chắc chắn sẽ bind vào `task.worker.batch-size`. Theo quy tắc canonical của `@ConfigurationProperties`, tên đúng là `TASK_WORKER_BATCHSIZE`. Sự linh hoạt của `Environment` và các kiểu truy xuất khác có thể khác biệt, nên hãy **tuân theo một quy tắc đặt tên chuẩn** và kiểm thử thuộc tính quan trọng.

Ví dụ shell Linux/macOS:

```bash
export SPRING_PROFILES_ACTIVE=prod
export TASK_WORKER_BATCHSIZE=500
export TASK_WORKER_TIMEOUT=60s

java -jar settlement-task.jar --business-date=2026-11-23
```

Ví dụ tương đương trong **PowerShell**:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'prod'
$env:TASK_WORKER_BATCHSIZE = '500'
$env:TASK_WORKER_TIMEOUT = '60s'

java -jar settlement-task.jar --business-date=2026-11-23
```

Cả hai đặt môi trường **cho tiến trình được khởi chạy sau đó**. Một lần chạy JVM đang hoạt động thường không tự nhận thay đổi của biến môi trường từ bên ngoài. Với Task ngắn hạn, cách vận hành phổ biến là mỗi lần launcher tạo tiến trình/pod mới với giá trị cấu hình tương ứng. Trong Kubernetes, có thể cung cấp biến qua `ConfigMap` hoặc `Secret`, nhưng `Secret` dạng biến môi trường vẫn cần kiểm soát quyền và tránh làm lộ qua công cụ chẩn đoán.

### `@ConfigurationProperties` chuyển kiểu giá trị

Khi bind, `TASK_WORKER_BATCHSIZE=500` có thể trở thành `int 500`, còn `TASK_WORKER_TIMEOUT=60s` có thể thành `Duration` 60 giây. Lỗi chuyển kiểu, ví dụ `TASK_WORKER_BATCHSIZE=hello`, thường khiến bean cấu hình không được khởi tạo: nên để ứng dụng **fail fast** trước khi xử lý giao dịch, thay vì âm thầm sử dụng giá trị sai.

Đối với **map/list** cần lưu ý quy tắc đặc biệt: **list cấu hình từ nguồn ưu tiên cao hơn thường thay toàn bộ list**, không hợp nhất từng phần tử. Đối với map, các key có thể được hợp nhất theo quy tắc binding, nhưng những key trùng nhau vẫn tuân theo ưu tiên nguồn. Hãy thử riêng trường hợp này khi cấu hình danh sách endpoint, tenant hoặc retry policy.

## 5. Java system properties khác gì option dòng lệnh?

Xét hai lệnh:

```bash
# -D là Java system property: viết TRƯỚC -jar.
java -Dtask.worker.batch-size=700 -jar settlement-task.jar \
  --business-date=2026-11-23

# --key=value là option của ứng dụng: viết SAU tên JAR.
java -jar settlement-task.jar \
  --business-date=2026-11-23 \
  --task.worker.batch-size=1000
```

Trong trường hợp đầu, JVM xử lý `-D` và đưa giá trị vào `System.getProperties()`, rồi Spring Boot đưa vào `Environment`. Trong trường hợp sau, Boot mặc định chuyển `--task.worker.batch-size=1000` thành property nguồn CLI. Option này cũng có mặt trong `ApplicationArguments`. Dùng `java -jar ... -Dtask.worker.batch-size=700` **sau** tên JAR không tạo system property của JVM; ứng dụng có thể coi nó là một đối số thường.

**Ưu tiên:** CLI option `--...` cao hơn Java `-D...`; Java `-D...` cao hơn biến môi trường thông thường. Do đó, nếu `TASK_WORKER_BATCHSIZE=500`, `-Dtask.worker.batch-size=700`, và `--task.worker.batch-size=1000` cùng có mặt, giá trị được bind vào cấu hình là `1000`.

Spring Boot còn hỗ trợ `SPRING_APPLICATION_JSON`: chẳng hạn biến môi trường chứa `{"task":{"worker":{"batch-size":800}}}` được phân tích thành property source **ưu tiên cao hơn Java system properties nhưng thấp hơn CLI**. Mặc dù giá trị JSON được truyền qua một biến môi trường, nó không nằm cùng mức ưu tiên với những biến OS thông thường. Trong JSON, `null` được coi như thiếu giá trị khi giải quyết property, nên không thể dùng `null` để xóa một giá trị từ nguồn ưu tiên thấp hơn.

```bash
export TASK_WORKER_BATCHSIZE=500
export SPRING_APPLICATION_JSON='{"task":{"worker":{"batch-size":800}}}'

# Nếu không có CLI override, hiệu lực là 800.
java -jar settlement-task.jar --business-date=2026-11-23

# Có CLI override, hiệu lực là 1000.
java -jar settlement-task.jar --business-date=2026-11-23 \
  --task.worker.batch-size=1000
```

## 6. Ví dụ Spring Cloud Task đọc giá trị theo đúng vai trò

**Bài thực hành:** chạy tác vụ `settlement-task` nhận `--business-date=YYYY-MM-DD` từ scheduler. `batch-size` và `timeout` là cấu hình vận hành; các tham số liên quan tới `DataSource`/`TaskRepository` là cấu hình hạ tầng. File build cần có bộ phiên bản **Spring Boot + Spring Cloud tương thích**, `spring-cloud-starter-task` và JDBC driver phù hợp. Đoạn mã tập trung vào binding, không thực hiện ghi nghiệp vụ thật.

File `src/main/java/com/example/task/SettlementTaskApplication.java`:

```java
package com.example.task;

import java.time.Duration;
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
@EnableConfigurationProperties(TaskWorkerSettings.class)
public class SettlementTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(SettlementTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner runSettlement(TaskWorkerSettings settings) {
        return args -> {
            List<String> values = args.getOptionValues("business-date");
            if (values == null || values.size() != 1 || values.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Cần đúng một --business-date=YYYY-MM-DD");
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            if (settings.batchSize() <= 0 || settings.timeout().isNegative()
                    || settings.timeout().isZero()) {
                throw new IllegalArgumentException("Cấu hình worker không hợp lệ");
            }

            System.out.printf("date=%s batchSize=%d timeout=%s%n",
                    businessDate, settings.batchSize(), settings.timeout());
            // Tại đây service nghiệp vụ dùng settings và businessDate.
        };
    }
}

@ConfigurationProperties(prefix = "task.worker")
record TaskWorkerSettings(int batchSize, Duration timeout) {
}
```

`TaskWorkerSettings` là một **record** được Boot constructor-bind từ các nguồn cấu hình. `ApplicationRunner` đọc `business-date` từng lần chạy bằng `ApplicationArguments`. Giữ hai loại dữ liệu tách biệt trong mã giúp giới hạn quyền override: API/scheduler có thể nhận một ngày nghiệp vụ, còn deployment quyết định `batch-size`, timeout và thông tin DB.

File cấu hình cơ sở `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: settlement-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL:jdbc:h2:mem:task_demo;DB_CLOSE_DELAY=-1}
    username: ${TASK_DB_USER:sa}
    password: ${TASK_DB_PASSWORD:}
  cloud:
    task:
      initialize-enabled: true  # Chỉ phù hợp với database thử nghiệm.

task:
  worker:
    batch-size: 200
    timeout: 30s
```

Trong bài thực hành, JDBC driver H2 phải có trên classpath để fallback `jdbc:h2:mem:...` hoạt động. **H2 in-memory không lưu lịch sử Task giữa các JVM**, nên production phải dùng RDBMS bền vững, quản lý migration của schema Task và có thể đặt `spring.cloud.task.initialize-enabled=false` khi schema đã được tạo. Không dùng mật khẩu mặc định rỗng cho cơ sở dữ liệu production.

`spring.datasource.*`, `spring.application.name`, `spring.cloud.task.initialize-enabled` đều là cấu hình Boot/Cloud liên quan trực tiếp đến `TaskRepository` và lifecycle của Task. Chẳng hạn, ghi đè `spring.application.name` có thể làm thay đổi **tên Task trong lịch sử thực thi**, ảnh hưởng cách dashboard nhóm và giám sát theo tên. Thay `spring.datasource.url` có thể chuyển repository sang **một cơ sở dữ liệu khác**, khiến các bản ghi dường như “biến mất” khi truy vấn vào DB cũ. Đây là lý do không nên cho client nghiệp vụ truyền tùy ý các key hạ tầng này.

### Bảng kết quả thực hành

Giả sử `application.yml` có `batch-size=200`, `application-prod.yml` có `batch-size=300` và không có external config ngoài những nguồn được nêu trong từng dòng:

| Cách chạy | Giá trị `batchSize()` | Vì sao |
| --- | --- | --- |
| Chỉ `--business-date=2026-11-23` | `200` | Mặc định trong `application.yml` |
| Thêm `--spring.profiles.active=prod` | `300` | `application-prod.yml` ghi đè giá trị cơ sở |
| Profile `prod` + `TASK_WORKER_BATCHSIZE=500` | `500` | OS env ưu tiên cao hơn config data |
| Có biến OS `500` + `-Dtask.worker.batch-size=700` | `700` | Java system property ghi đè biến OS |
| Có `-D...=700` + `SPRING_APPLICATION_JSON` đặt `800` | `800` | JSON property source ưu tiên cao hơn `-D` |
| Có các nguồn trên + `--task.worker.batch-size=1000` | `1000` | CLI option ưu tiên cao hơn các nguồn runtime vừa nêu |

Không cần build lại JAR giữa các dòng: chỉ cần khởi chạy **tiến trình mới với cấu hình mới**. Nếu trong máy còn đặt biến môi trường từ một thử nghiệm trước, cần bỏ nó khi muốn kiểm chứng các dòng chỉ dùng giá trị cơ sở; ví dụ Linux/macOS: `unset TASK_WORKER_BATCHSIZE SPRING_APPLICATION_JSON`, PowerShell: `Remove-Item Env:TASK_WORKER_BATCHSIZE,Env:SPRING_APPLICATION_JSON -ErrorAction SilentlyContinue`.

## 7. Cách đọc cấu hình khác nhau và những điểm cần biết

| Cơ chế | Ví dụ | Khi nào sử dụng |
| --- | --- | --- |
| `@ConfigurationProperties` | `TaskWorkerSettings(int batchSize, Duration timeout)` | Cấu hình có nhóm thuộc tính, cần chuyển kiểu/validation, thuận tiện thử nghiệm |
| `@Value` | `@Value("${task.worker.batch-size:200}") int batchSize` | Giá trị đơn lẻ, ít thuộc tính; dùng tên chuẩn kebab-case trong placeholder |
| `Environment` | `env.getProperty("task.worker.batch-size", Integer.class)` | Trường hợp cần đọc property theo tên hoặc chẩn đoán |
| `ApplicationArguments` | `args.getOptionValues("business-date")` | Yêu cầu nghiệp vụ của lần chạy, cần xử lý thiếu/trùng/sai định dạng |

Không nên bind trực tiếp `--business-date` vào hằng số cấu hình bean nếu tác vụ coi đây là input nghiệp vụ, bởi bạn có thể mất xử lý tham số trùng/thiếu và tạo sự lẫn lộn giữa hợp đồng đầu vào với chính sách triển khai. Với `@ConfigurationProperties`, ưu tiên nhóm `task.worker.*` rõ ràng hơn những key phẳng kiểu `size`, `timeout` dễ xung đột với thư viện khác.

Nếu muốn kiểm tra *cấu hình nào thực sự có hiệu lực*, có thể log các giá trị **không nhạy cảm** sau binding:

```java
System.out.printf("batchSize=%d, timeout=%s%n",
        settings.batchSize(), settings.timeout());
```

Để tra nguồn cụ thể, Spring Boot Actuator có endpoint `env` và `configprops`, có thể cung cấp property source và origin theo cấu hình. Nhưng một Task thường chạy `web-application-type: none` và kết thúc nhanh; không nên bật HTTP server chỉ để kiểm tra cấu hình. Trong môi trường thử nghiệm, có thể dùng log `org.springframework.boot.context.config=TRACE` để quan sát quá trình tìm/nạp config data, hoặc tạo một phép kiểm tra binding riêng. **Tuyệt đối không bật hiển thị giá trị secret không kiểm soát**; Actuator phải được bảo vệ quyền truy cập, giá trị nhạy cảm cần được che.

## 8. Dòng lệnh nào được lưu vào metadata Task?

Spring Cloud Task lưu thông tin một lần chạy trong `TaskRepository`; metadata bao gồm `TaskExecution` và **danh sách chuỗi đối số lệnh** (thường ở bảng `TASK_EXECUTION_PARAMS` theo schema mặc định). Điều này có hai hệ quả:

1. `--business-date=2026-11-23` có thể giúp người vận hành biết Task được yêu cầu xử lý kỳ dữ liệu nào. Vẫn cần kiểm soát thông tin cá nhân và ghi idempotency key phù hợp nếu có retry.
2. `--spring.datasource.password=...`, `--api-token=...` hoặc secret được nối vào argument có thể bị lưu lâu hơn vòng đời tiến trình và xuất hiện trong công cụ xem process/log. **Không gửi secret theo CLI.**

Không nên giả định rằng toàn bộ biến OS, system property và tất cả file cấu hình sẽ tự được snapshot vào `TaskExecution`: Task metadata lưu các đối số thực tế và trường kết quả theo cơ chế của framework; nó **không phải bản sao hoàn chỉnh** của `Environment`. Muốn tái hiện chính xác một lần chạy, lưu thêm phiên bản artifact/config deploy không nhạy cảm, mã commit, image digest và định danh release ngoài repository theo chính sách vận hành.

### Truyền cấu hình trong container và job scheduler

Ví dụ mô hình phân công trách nhiệm:

```text
Kubernetes Job / CronJob
    environment: TASK_WORKER_BATCHSIZE=500
    environment: SPRING_PROFILES_ACTIVE=prod
    secret volume: thông tin xác thực DB
    arguments: --business-date=2026-11-23
         |
         v
Spring Boot Environment --> TaskWorkerSettings, DataSource, TaskRepository
ApplicationArguments  --> business-date (xác thực, kiểm tra idempotency)
```

Ở API kích hoạt Task, **allowlist** tên và kiểu của tham số nghiệp vụ rồi truyền từng đối số bằng danh sách arguments cho launcher. Không nối dữ liệu người dùng vào một chuỗi shell command; không cho request tùy ý mang `--spring.*`, `--management.*` hoặc `--task.worker.*` nếu người gọi không có quyền thay đổi vận hành. Nếu tổ chức cần khả năng override có kiểm soát, hãy định nghĩa một cơ chế cấu hình riêng được audit thay vì để người dùng lách bằng option CLI.

## 9. Chặn khả năng ghi đè cấu hình từ `--...`

Với hệ thống phải giữ cứng cấu hình hạ tầng do deployment cấp, Spring Boot cho phép **không thêm command-line options vào `Environment`**:

```java
public static void main(String[] args) {
    SpringApplication app = new SpringApplication(SettlementTaskApplication.class);
    app.setAddCommandLineProperties(false);
    app.run(args);
}
```

Đây là **đoạn thay thế `main`** trong ví dụ ở mục 6. Kể từ đó:

- `ApplicationRunner` vẫn nhận `ApplicationArguments`, nên `--business-date=...` vẫn được đọc để xử lý nghiệp vụ.
- `--task.worker.batch-size=1000` **không** còn ghi đè `@ConfigurationProperties` qua command-line property source.
- `--spring.profiles.active=prod` và `--spring.config.additional-location=...` cũng **không** còn là nguồn cấu hình CLI. Phải chọn profile/đường dẫn thông qua biến môi trường, Java system properties hoặc nguồn được phép khác.

Quyết định này ảnh hưởng toàn ứng dụng, gồm cả các option của Boot và thư viện. Chỉ dùng khi đó là hợp đồng triển khai bạn chủ động chọn và đã kiểm tra trên tiến trình thật. Không nên làm như một cách sửa tạm khi cấu hình hiện tại bị xung đột; tốt hơn là xác định đúng property source đã cung cấp giá trị ngoài ý muốn.

## 10. Nguồn cấu hình bí mật: môi trường, placeholder và config tree

Trong ví dụ Task, `spring.datasource.url`, `username`, `password` điều khiển DB lưu lịch sử thực thi; các giá trị này phải nhất quán giữa các lần chạy nếu muốn truy vấn cùng một repository. Có thể dùng placeholder trong file YAML:

```yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
```

Nếu biến không tồn tại và không có mặc định, việc resolve placeholder có thể khiến cấu hình không hợp lệ/khởi động thất bại. Đây thường là hành vi mong muốn với thông tin bắt buộc trong production. Cú pháp `${KEY:default}` cho phép đặt mặc định, nhưng không nên có giá trị mặc định là mật khẩu thật hoặc URL trỏ tới DB production.

Khi nền tảng cung cấp Kubernetes Secret qua **volume** (mỗi file chứa một giá trị), Spring Boot hỗ trợ nạp **config tree**:

```yaml
spring:
  config:
    import: optional:configtree:/etc/settlement-secrets/
```

Giả sử volume có các file `/etc/settlement-secrets/spring.datasource.username` và `/etc/settlement-secrets/spring.datasource.password`, với nội dung là credential, Spring Boot có thể đưa chúng thành property tương ứng. Vị trí này phải tồn tại và được mount đúng quyền; trong production hãy bỏ `optional:` nếu thiếu secret phải làm Task **fail fast**. Không in nội dung file secret, không ghi nguyên `Environment` ra log và không dùng `--spring.datasource.password` để “chữa cháy”.

**Lưu ý về ưu tiên:** config tree được nạp bằng `spring.config.import` thuộc nhóm **config data**, nên một biến môi trường hoặc CLI có cùng key vẫn có thể ghi đè. Việc mount file secret không tự khóa quyền override theo tên thuộc tính. Quyền triển khai và kiểm soát nguồn config cao hơn vẫn phải được quản lý.

## 11. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| Đặt `batch-size=200` trong JAR nhưng task dùng `500` | Env var, file ngoài JAR hoặc CLI đã ghi đè | Kiểm tra env của launcher, `-D` và danh sách arguments; xem nguồn trong `Environment` |
| `TASK_WORKER_BATCH_SIZE` không bind như mong đợi | Tên env var không tuân theo canonical relaxed binding | Đổi thành `TASK_WORKER_BATCHSIZE`, kiểm tra với `@ConfigurationProperties` |
| CLI `--task.worker.batch-size=1000` không có tác dụng | Đã gọi `setAddCommandLineProperties(false)` hoặc có nguồn đặc biệt ưu tiên cao hơn trong test | Kiểm tra `main`, các `PropertySource` và môi trường chạy |
| Bật `prod` nhưng giá trị lại từ `application.yml` | Profile chưa được kích hoạt hoặc file profile không được nạp | Xem `spring.profiles.active`, trace config loader, tên file và vị trí |
| File ngoài JAR bị bỏ qua | `WORKDIR` khác dự kiến, sai mount, dùng `spring.config.location` thay mặc định | Dùng absolute path/config additional location, kiểm tra file trong container |
| Bật `optional:` và cấu hình biến mất mà không báo lỗi thiếu file | Location không tồn tại nhưng được cho phép bỏ qua | Bỏ `optional:` với file bắt buộc, xác minh mounting trước khi chạy |
| `TaskRepository` không thấy dữ liệu từ lần chạy trước | DB URL/profile thay đổi khiến Task ghi metadata sang database khác; hoặc đang dùng H2 in-memory | Kiểm tra JDBC URL hiệu lực, tên Task, schema/prefix và DB bền vững |
| Bean cấu hình báo lỗi chuyển kiểu | `batch-size` không phải số, `timeout` sai định dạng hoặc rỗng | Thêm validation và sửa dữ liệu từ nguồn thực sự có ưu tiên cao nhất |
| Chạy Task thành công ở CI nhưng thất bại production | Test property sources ưu tiên cao che giá trị runtime, thiếu secret/permission | Kiểm thử bằng image và config deployment gần production, đọc log bootstrap |
| Chỉ một phần list cấu hình trong profile được áp dụng | Spring Boot ghi đè **cả list**, không merge từng phần tử theo index | Khai báo lại list đầy đủ trong nguồn có ưu tiên cao hơn |

### Quy trình kiểm tra từng bước

Khi gặp một giá trị lạ ở production, thực hiện có thứ tự:

1. **Xác định key canonical và giá trị hiệu lực:** ví dụ `task.worker.batch-size`, dùng bean đã bind/log an toàn, hoặc một phép kiểm tra `Environment` trên môi trường thử nghiệm.
2. **Kiểm tra nguồn ưu tiên cao trước:** args `--...` mà scheduler/launcher truyền; `SPRING_APPLICATION_JSON`; Java `-D`; biến môi trường.
3. **Kiểm tra config data:** profile active, file ngoài JAR, `spring.config.location`/`additional-location`/`import`, `WORKDIR` và mount.
4. **Kiểm tra kiểu và ngữ nghĩa:** kiểu `Duration`, boolean, list hoặc map; namespace do framework hay ứng dụng sở hữu.
5. **Tái chạy có kiểm soát:** dùng cùng artifact và một snapshot cấu hình không nhạy cảm; xác nhận metadata Task và kết quả nghiệp vụ.

Không gửi dump toàn bộ môi trường hoặc nội dung secret ra chat/log để điều tra; chỉ lấy tên nguồn và giá trị đã làm sạch. Giới hạn quyền truy vấn các bảng `TASK_EXECUTION_PARAMS` vì đối số đã chạy có thể còn lưu trong đó.

## 12. Bài tập áp dụng

**Tình huống A.** `application.yml` đặt `task.worker.batch-size=200`; `application-prod.yml` đặt `300`; môi trường có `TASK_WORKER_BATCHSIZE=500`; JVM được gọi với `-Dtask.worker.batch-size=700`; sau tên JAR có `--task.worker.batch-size=1000`. Profile `prod` đang bật. Giá trị hiệu lực là gì?

**Trả lời:** `1000` vì option CLI mặc định ưu tiên cao hơn Java system properties, biến môi trường và config data. Nếu tắt command-line property source, trong các nguồn trên còn lại giá trị `700`.

**Tình huống B.** Người vận hành cung cấp `SPRING_APPLICATION_JSON` chứa `{"task":{"worker":{"batch-size":800}}}`, đồng thời vẫn có `TASK_WORKER_BATCHSIZE=500`; không có CLI override. Kết quả?

**Trả lời:** `800` vì Boot tạo một property source riêng từ JSON, có ưu tiên cao hơn biến môi trường thông thường.

**Tình huống C.** Scheduler chạy `--business-date=2026-11-23 --spring.datasource.url=jdbc:postgresql://another-db:5432/tasks`, sau đó dashboard không còn thấy lịch sử mới ở DB cũ. Vì sao?

**Trả lời:** Boot có thể dùng giá trị `spring.datasource.url` từ CLI, vốn ưu tiên cao, để tạo `DataSource` khác. Nếu TaskRepository dùng DataSource đó thì metadata được ghi vào DB khác. Phải chặn khả năng truyền key hạ tầng từ request và đối chiếu DB thực tế.

**Tình huống D.** Một `configtree:` đã nạp đúng `spring.datasource.password` từ volume. Người dùng truyền `--spring.datasource.password=abc` trong launcher và làm hỏng kết nối. Vì sao file secret không thắng?

**Trả lời:** `configtree:` là config data, trong khi CLI option có ưu tiên cao hơn. Ngoài việc sửa launcher, cần chính sách cấm override key hạ tầng và không đưa mật khẩu lên dòng lệnh, nơi giá trị có thể lộ hoặc bị ghi lại trong metadata Task.

**Tình huống E.** Một list endpoint có hai phần tử trong `application.yml`, còn file profile chỉ ghi `endpoints[0]`. Có thể coi phần tử thứ hai từ cấu hình gốc vẫn được kế thừa không?

**Trả lời:** Không mặc định. Với `@ConfigurationProperties`, list từ nguồn ưu tiên cao hơn thường thay **toàn bộ list**. Khai báo list hoàn chỉnh ở nguồn cần override và kiểm tra kết quả sau binding.

## 13. Checklist vận hành an toàn

- [ ] Ghi rõ bảng nguồn cấu hình ưu tiên cho môi trường đang dùng; có một tên canonical cho mỗi thuộc tính quan trọng.
- [ ] Giữ `application.yml` làm mặc định không nhạy cảm; dùng profile/file bên ngoài/biến môi trường cho khác biệt môi trường.
- [ ] Đặt biến môi trường đúng quy tắc **dấu chấm → `_`, bỏ dấu `-`, viết hoa**; kiểm thử binding với `@ConfigurationProperties`.
- [ ] Kiểm tra đủ `WORKDIR`, vị trí mount và ý nghĩa của `spring.config.location` so với `spring.config.additional-location`.
- [ ] Scheduler/API chỉ nhận danh sách tham số nghiệp vụ hợp lệ, không chấp nhận tùy ý key `spring.*` hoặc `task.worker.*`.
- [ ] Không truyền token/mật khẩu qua CLI; dùng cơ chế secret an toàn, giới hạn quyền xem Task metadata và log.
- [ ] Với DB của TaskRepository, xác minh URL, username, schema và prefix thực sự hiệu lực ở từng môi trường.
- [ ] Cấu hình `@ConfigurationProperties` có validation, giá trị mặc định rõ ràng và không âm thầm nuốt lỗi bind.
- [ ] Khi triển khai Spring Batch cùng Task, kiểm tra riêng cấu hình Job/Step và điều kiện retry/restart, không giả định các tham số CLI luôn là `JobParameters`.
- [ ] Có cách tái hiện cấu hình không nhạy cảm của một lần chạy bằng image digest, release ID, profile và version config; giám sát mã thoát và lịch sử Task.

## Tài liệu chính thức

1. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự `PropertySource`, config data, biến môi trường, `SPRING_APPLICATION_JSON` và CLI.
2. [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, relaxed binding, quy tắc list và map.
3. [Spring Boot — Configuring External Properties](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): thay đổi vị trí file, log nạp config.
4. [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): DataSource, TaskRepository, table initialization và vòng đời Task.
5. [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html): dữ liệu `TASK_EXECUTION` và `TASK_EXECUTION_PARAMS` phục vụ quan sát thực thi.

**Nguyên tắc ghi nhớ:** Spring Boot cho phép nhiều nguồn cùng định nghĩa một thuộc tính; **giá trị từ nguồn ưu tiên cao nhất có khai báo key sẽ được dùng để resolve/bind**, và nếu giá trị sai kiểu thì quá trình bind có thể thất bại thay vì tự lấy giá trị ở nguồn thấp hơn. Trong Spring Cloud Task, hãy giới hạn quyền ghi đè cấu hình hạ tầng, truyền tham số nghiệp vụ theo từng lần chạy và kiểm tra `TaskRepository` đang kết nối đúng nơi lưu lịch sử.
