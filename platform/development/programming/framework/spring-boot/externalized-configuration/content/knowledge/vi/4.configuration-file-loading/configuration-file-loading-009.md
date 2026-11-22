# Thời điểm cung cấp `spring.config.*` để Spring Boot 3.3 tìm và nạp cấu hình

## 1. Vấn đề cần giải quyết

Spring Boot 3.3 cho phép thay đổi tên file, vị trí tìm kiếm và nguồn cấu hình bổ sung thông qua các khóa `spring.config.*`. Điểm dễ nhầm là **không phải khóa nào cũng có thể đặt vào bất kỳ file cấu hình nào**. Một số khóa cần được cung cấp **ngay khi ứng dụng bắt đầu khởi động**, trước khi Spring Boot quyết định sẽ tìm và đọc `application.properties` hoặc `application.yaml` ở đâu. Một số khóa khác được đọc **trong lúc** bộ nạp Config Data xử lý chính các file cấu hình đó.

Ví dụ:

```properties
spring.config.location=optional:file:./deployment/
```

Nếu dòng này chỉ nằm trong một file `application.properties` được tìm theo vị trí mặc định, Spring Boot không dùng dòng đó để **quay lại khởi động quá trình tìm kiếm từ đầu**. Để thay đổi chính vị trí tìm file, nên đưa giá trị vào biến môi trường, JVM system property hoặc command-line argument **trước khi `SpringApplication.run(...)` xử lý Config Data**.

Ngược lại, câu lệnh sau là một use case bình thường ngay **trong** `application.properties` hoặc `application.yaml`:

```properties
spring.config.import=optional:file:./deployment/extra.properties
```

Vì đây là chỉ dẫn **nhập thêm dữ liệu trong quá trình đọc một file đã tìm thấy**, bộ nạp Config Data có thể nhận và thực hiện nó tại thời điểm file đang được xử lý.

**Quy tắc nhớ:**

- **`spring.config.name`, `spring.config.location` và `spring.config.additional-location`:** phải có **từ rất sớm**, để Spring Boot biết **tên/vị trí** cần tìm.
- **`spring.config.import` và `spring.config.activate.on-profile`:** có vai trò **bên trong quá trình Config Data**; chúng thường được khai báo ngay trong tài liệu cấu hình mà Spring Boot đã tìm thấy.
- **`spring.profiles.active` / `spring.profiles.default`:** được sử dụng để xác định profile và chọn file `application-{profile}.*`. Chúng có thể được cấu hình trong tài liệu **không đặc thù profile**, tuân thủ các quy tắc profile của Spring Boot; không được khai báo tùy tiện trong profile-specific document.
- **Các property ứng dụng thông thường** (`app.*`, `server.port`, `spring.datasource.*`...): được bind/tiêu thụ sau khi nguồn cấu hình tương ứng đã được nạp, dù vài property hệ thống như logging còn được dùng khá sớm.

## 2. Dòng thời gian nạp cấu hình trong quá trình startup

Mô hình khái quát:

```text
T0. Shell / runtime chuẩn bị tiến trình Java
    ├─ OS environment: SPRING_CONFIG_LOCATION, ...
    ├─ JVM system properties: -Dspring.config.location=...
    └─ Program args: --spring.config.location=...

T1. main(String[] args), chuẩn bị SpringApplication
    ├─ có thể setDefaultProperties(...) trước run(...)
    └─ SpringApplication.run(args)

T2. Tạo và chuẩn bị Environment trước khi refresh ApplicationContext
    ├─ nhận các nguồn sớm: system properties, environment variables,
    │  command-line options và các nguồn được SpringApplication tạo
    ├─ ConfigDataEnvironmentPostProcessor chạy
    │  ├─ đọc spring.config.name/location/additional-location
    │  ├─ quyết định các location sẽ tìm
    │  ├─ đọc application.properties / application.yaml / .yml
    │  ├─ xử lý spring.config.import và profile-specific documents
    │  └─ thêm các Config Data PropertySource vào Environment
    └─ Environment đã được bổ sung nguồn cấu hình file

T3. Chuẩn bị, tạo và refresh ApplicationContext
    ├─ @PropertySource trên @Configuration có thể được thêm tại đây
    ├─ tạo các bean / bind @ConfigurationProperties / @Value
    └─ khởi động server, runner và ứng dụng
```

Tên thành phần quan trọng của Spring Boot 3.3 là `ConfigDataEnvironmentPostProcessor`. Thành phần này xử lý Config Data **trong giai đoạn chuẩn bị Environment**, trước khi `ApplicationContext` hoàn tất refresh. Vì thế, một property dùng để chỉ đường cho chính bộ nạp phải được biết **trước hoặc trong lúc thành phần này bắt đầu xử lý**, còn những giá trị được thêm qua bean, `@PostConstruct`, `ApplicationRunner` hay `CommandLineRunner` đều đến quá muộn để đổi hướng tìm file của lần startup đó.

Bảng theo thời điểm:

| Điểm cung cấp giá trị | Có sẵn khi chọn nơi tìm Config Data? | Cách dùng |
| --- | --- | --- |
| Biến môi trường OS có từ trước khi chạy Java | **Có** | `SPRING_CONFIG_LOCATION`, `SPRING_CONFIG_NAME`, `SPRING_CONFIG_ADDITIONALLOCATION` |
| JVM `-D...` trước khi `main` chạy | **Có** | `-Dspring.config.location=...` |
| Command-line `--...` được truyền vào `SpringApplication.run(args)` | **Có**, theo cấu hình mặc định | `--spring.config.additional-location=...` |
| Giá trị được đặt bằng `SpringApplication.setDefaultProperties(...)` trước `run` | **Có**, với mức ưu tiên thấp | Cấu hình sẵn bootstrap trong mã |
| `spring.config.import` bên trong một Config Data document đã tìm được | **Được xử lý trong quá trình nạp** | Nhập thêm file/config tree hoặc nguồn được hỗ trợ |
| `spring.config.location` chỉ có trong `application.yaml` đang được tìm theo mặc định | **Quá muộn để thay đổi danh sách tìm kiếm ban đầu** | Hãy đưa ra nguồn sớm |
| `@PropertySource` trên lớp `@Configuration` | **Quá muộn** | Không dùng để chọn `spring.config.location` |
| `@ConfigurationProperties`, `@Value`, `@PostConstruct`, runner | **Quá muộn** | Chỉ nên dùng để tiêu thụ cấu hình đã nạp |

Sơ đồ là mô hình khái niệm về thứ tự quan trọng, không biểu diễn mọi callback và listener của Spring Framework. Khi có thư viện tự bổ sung `EnvironmentPostProcessor`, thứ tự chính xác còn phụ thuộc `Ordered`/thứ tự đăng ký của thành phần đó.

## 3. Ba khóa phải cung cấp sớm để chọn tên/vị trí

### 3.1. `spring.config.name`: đổi basename của file

Mặc định Spring Boot tìm tên `application`, tức các file như:

```text
application.properties
application.yaml
application.yml
application-dev.properties
application-dev.yaml
...
```

Muốn tìm `service.yaml` hoặc `service.properties`, truyền trước startup:

```bash
java -jar myapp.jar --spring.config.name=service
```

Khi profile `dev` hoạt động, các biến thể theo profile tương ứng như `service-dev.yaml` cũng được xét theo quy tắc Config Data.

Có thể truyền nhiều tên basename phân tách bằng dấu phẩy nếu thiết kế cần hơn một nhóm file:

```bash
java -jar myapp.jar --spring.config.name=common,service
```

**Sai về thời điểm:** đặt `spring.config.name=service` trong `application.properties` rồi kỳ vọng Spring Boot tự bỏ tên `application` và tìm lại toàn bộ cấu hình như một lần bootstrap mới. Muốn định tuyến tìm kiếm ban đầu sang `service` thì cấu hình đó phải đến từ nguồn sớm.

### 3.2. `spring.config.location`: thay thế các vị trí tìm mặc định

Khi không tùy chỉnh, Spring Boot tìm Config Data ở các location mặc định điển hình:

```text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
```

`spring.config.location` **thay thế** tập location mặc định bằng tập do bạn chỉ định. Ví dụ:

```bash
java -jar myapp.jar \
  --spring.config.location=optional:classpath:/config/,optional:file:./deployment/
```

Ở ví dụ này bộ nạp sử dụng các location đã cung cấp, với ý nghĩa `classpath:/config/` và `file:./deployment/` là thư mục; nếu chỉ ghi `file:./deployment/` mà không có vị trí classpath, cấu hình đóng gói ở vị trí mặc định có thể không còn được tìm như trước.

**Hai lưu ý cú pháp:**

1. **Location là thư mục cần kết thúc bằng `/`**, ví dụ `file:./deployment/`. Khi trỏ tới thư mục, Spring Boot sẽ ghép với basename từ `spring.config.name` và các phần mở rộng phù hợp.
2. **Location là file cụ thể** phải chỉ rõ tên file, ví dụ `file:./deployment/service.properties`; không thêm `/` vào cuối. Các vị trí cụ thể và các biến thể profile được xử lý theo quy tắc Config Data, không chỉ bằng phép nối chuỗi thủ công.

`file:./...` được giải theo **working directory của tiến trình Java**, không tự động theo thư mục chứa JAR. Nếu chạy từ một working directory khác, file tương đối có thể không được tìm thấy.

### 3.3. `spring.config.additional-location`: giữ defaults và bổ sung vị trí

Nếu muốn **giữ các location mặc định** nhưng nạp thêm các file ngoài JAR, ưu tiên dùng:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deployment/
```

Spring Boot vẫn xét các cấu hình mặc định, đồng thời thêm `./deployment/` ở mức ưu tiên Config Data thích hợp. Những location bổ sung được xử lý **sau các location mặc định** và có thể ghi đè giá trị cùng khóa trong các file mặc định.

Ví dụ tổ chức:

```text
myapp.jar
deployment/
  application.properties
```

Trong JAR có:

```properties
# application.properties đóng gói
app.title=Catalog
app.timeout=3s
```

File ngoài JAR:

```properties
# deployment/application.properties
app.timeout=8s
```

Chạy với `--spring.config.additional-location=optional:file:./deployment/` từ thư mục chứa `deployment` cho kết quả `app.title=Catalog` và `app.timeout=8s`, giả sử không có nguồn ưu tiên cao hơn ghi đè.

Không cần chuyển qua `spring.config.location` trong tình huống chỉ muốn bổ sung nơi đọc. `additional-location` thể hiện rõ ý định kế thừa cấu hình hiện tại và ghi đè những giá trị cần thiết ở nơi triển khai.

## 4. Cách truyền giá trị đủ sớm: ví dụ thực tế

### 4.1. Command-line argument `--spring.config.*`

```bash
java -jar myapp.jar \
  --spring.config.name=service \
  --spring.config.additional-location=optional:file:./deploy/
```

Các đối số `--key=value` phải nằm trong mảng đối số truyền cho `SpringApplication.run(args)`. Theo mặc định Spring Boot thêm chúng thành một `PropertySource` có ưu tiên cao khi bootstrap. Nếu mã ứng dụng gọi `setAddCommandLineProperties(false)` thì không thể dựa vào cơ chế thêm command-line properties đó nữa.

Trong IDE có thể cấu hình trường **Program arguments**:

```text
--spring.config.additional-location=optional:file:./deploy/
```

Đây là program argument, không phải JVM option.

### 4.2. JVM system properties `-D`

```bash
java \
  -Dspring.config.name=service \
  -Dspring.config.additional-location=optional:file:./deploy/ \
  -jar myapp.jar
```

Đặt các tùy chọn `-D` **trước `-jar`** để JVM nhận chúng làm system properties. Đây là cách hữu ích khi hệ thống chạy ứng dụng cho phép cấu hình JVM arguments.

Trong IDE có thể đặt:

```text
-Dspring.config.additional-location=optional:file:./deploy/
```

vào trường **VM options**.

### 4.3. Biến môi trường OS

Tên biến môi trường chuẩn cho relaxed binding được tạo bằng cách thay dấu chấm bằng `_`, bỏ dấu `-` và viết hoa:

```text
spring.config.name                → SPRING_CONFIG_NAME
spring.config.location            → SPRING_CONFIG_LOCATION
spring.config.additional-location → SPRING_CONFIG_ADDITIONALLOCATION
```

Ví dụ Unix-like shell:

```bash
SPRING_CONFIG_NAME=service \
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./deploy/ \
java -jar myapp.jar
```

Hoặc cấu hình các biến này trong môi trường chạy container/Kubernetes trước khi tiến trình Java được tạo. Giá trị phải có sẵn khi Java bắt đầu bootstrap; việc sửa biến môi trường ở shell **sau khi** ứng dụng đã khởi động sẽ không khiến nó tự nạp lại vị trí Config Data.

Trên Windows PowerShell, có thể thiết lập cho tiến trình con:

```powershell
$env:SPRING_CONFIG_NAME = "service"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "optional:file:./deploy/"
java -jar myapp.jar
```

### 4.4. Cấu hình bằng Java trước khi `run(...)`

Nếu cần một giá trị mặc định gắn với launcher:

```java
import java.util.Map;
import org.springframework.boot.SpringApplication;

public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DemoApplication.class);
        app.setDefaultProperties(Map.of(
            "spring.config.additional-location", "optional:file:./deploy/"
        ));
        app.run(args);
    }
}
```

Lời gọi `setDefaultProperties(...)` xảy ra **trước `run(...)`**, nên `Environment` có thể nhìn thấy nó khi bộ nạp Config Data bắt đầu xử lý. Đây là **giá trị mặc định có ưu tiên thấp**, nên nguồn khác như OS environment, JVM `-D` hoặc command line có thể ghi đè. Nếu muốn người vận hành dễ đổi nơi nạp cấu hình theo môi trường, các cách truyền tham số bên ngoài thường linh hoạt hơn.

Một số framework tích hợp có thể khởi tạo `SpringApplicationBuilder`; nguyên tắc vẫn là **đặt giá trị vào `Environment` trước khi Config Data được xử lý**, không dựa vào code chạy sau context refresh.

## 5. `spring.config.import` khác ở điểm nào?

`spring.config.import` không phải là lời yêu cầu “tìm lại tất cả file từ đầu”. Nó là chỉ dẫn **thêm nguồn Config Data tại vị trí tài liệu đã được nạp**. Vì vậy có thể xuất hiện ngay trong `application.properties` hoặc `application.yaml`:

```properties
# src/main/resources/application.properties
app.name=api
spring.config.import=optional:file:./deploy/overrides.properties
```

```properties
# ./deploy/overrides.properties
app.name=api-deployed
app.connect-timeout=6s
```

Trong ví dụ trên, Spring Boot đầu tiên tìm được `application.properties` qua location mặc định, sau đó đọc `spring.config.import` và nhập `./deploy/overrides.properties`. Các giá trị từ dữ liệu được import có quyền ưu tiên hơn các giá trị trùng khóa của tài liệu khai báo import. Kết quả `app.name=api-deployed` nếu không có PropertySource cao hơn ghi đè.

**YAML tương đương:**

```yaml
app:
  name: api
spring:
  config:
    import: "optional:file:./deploy/overrides.properties"
```

Có thể import nhiều location:

```properties
spring.config.import=optional:file:./defaults.properties,optional:file:./override.properties
```

Import khai báo **sau** được ưu tiên hơn import trước khi có xung đột theo quy tắc Config Data. Chỗ đặt dòng `spring.config.import` trong tài liệu không quyết định ưu tiên riêng của import; bộ nạp xử lý nó như chỉ dẫn của toàn tài liệu.

### `spring.config.import` chỉ có tác dụng sau khi file chứa nó đã được tìm thấy

Nếu bạn đặt `spring.config.import` trong `./custom/application.yaml` nhưng thư mục `./custom/` không nằm trong location được tìm hoặc chưa được thêm bằng `spring.config.additional-location`, bản thân import đó **không thể giúp bộ nạp phát hiện file đang bị bỏ qua**.

Quy trình đúng:

1. Dùng nguồn sớm để bảo đảm file khai báo import được tìm thấy, **hoặc** đặt `spring.config.import` trong một file đã được nạp theo mặc định.
2. Khi file đó được đọc, bộ nạp mới tiếp tục giải quyết các import được khai báo trong file.
3. Các property thông thường từ file được import trở thành một phần của `Environment` theo thứ tự ưu tiên Config Data.

Ngoài file .properties/YAML, Spring Boot có thể import nguồn như `configtree:` khi thích hợp; điều kiện bắt buộc vẫn là **một Config Data document hợp lệ được nạp rồi mới biết đến chỉ dẫn import của nó**.

## 6. Profile và thời điểm chọn `application-{profile}.*`

Trong cùng quá trình Config Data, Spring Boot xác định các profile hoạt động và dùng chúng để chọn tài liệu cấu hình thích hợp.

**Ví dụ cấu hình chung:**

```yaml
# application.yaml
spring:
  profiles:
    active: dev
app:
  mode: base
```

**Ví dụ file theo profile:**

```yaml
# application-dev.yaml
app:
  mode: development
```

Khi profile `dev` được kích hoạt, `application-dev.yaml` có thể ghi đè `app.mode` bằng `development`.

Có thể chọn profile từ nguồn sớm:

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

Giá trị từ nguồn ưu tiên cao như command line có thể ghi đè `spring.profiles.active` trong file chung, từ đó làm thay đổi tập file theo profile được xét trong giai đoạn Config Data.

**Giới hạn cần nhớ:**

- `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và các property điều khiển profile tương tự **không được sử dụng trong tài liệu đặc thù profile hoặc tài liệu kích hoạt bởi `spring.config.activate.on-profile`** nếu tài liệu Spring Boot cấm trường hợp đó. Đừng đặt `spring.profiles.active=prod` trong `application-dev.properties` để hy vọng đổi profile một lần nữa.
- `spring.config.activate.on-profile` dùng để điều kiện hóa **một Config Data document** theo profile hiện tại; nó không thay thế cơ chế chọn location từ sớm.
- `spring.config.import` có thể nằm trong tài liệu Config Data phù hợp; khi tài liệu đó tham gia nạp, import liên quan cũng được xử lý theo quy tắc Config Data.
- Nếu nhiều profile cùng active, thứ tự nạp tài liệu theo profile/location group ảnh hưởng giá trị cuối cùng; đây là quy tắc ưu tiên **trong Config Data**, khác với thời điểm cung cấp `spring.config.location`.

Ví dụ YAML nhiều tài liệu:

```yaml
# application.yaml — tài liệu chung
app:
  endpoint: https://api.example.test
---
spring:
  config:
    activate:
      on-profile: dev
app:
  endpoint: http://localhost:8081
```

Với profile `dev`, tài liệu thứ hai được kích hoạt và có thể ghi đè `app.endpoint`. Tài liệu chung có thể nêu import; tài liệu theo profile có thể chứa cấu hình dành riêng cho profile. Dùng dấu `---` để ngăn cách các YAML documents; không trộn cú pháp phân cách của .properties.

## 7. `optional:` và xử lý location không tồn tại

Một location được chỉ định nhưng không tồn tại có thể làm quá trình startup thất bại với lỗi của Config Data, chẳng hạn `ConfigDataLocationNotFoundException`.

Ví dụ:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

`optional:` cho phép thiếu **location cụ thể** mà không làm startup thất bại chỉ vì location đó không tồn tại. Nếu file khác được tìm và nạp, nó vẫn tham gia vào các PropertySource bình thường.

Có thể áp dụng `optional:` cho import:

```properties
spring.config.import=optional:file:./local.properties
```

Bỏ `optional:` nếu file thật sự là phụ thuộc bắt buộc và cần báo lỗi sớm khi không tìm thấy.

Spring Boot cũng có `spring.config.on-not-found=ignore` để bỏ qua các lỗi không tìm thấy location trên diện rộng; cấu hình này cần được cung cấp đủ sớm cho quá trình Config Data. Tuy nhiên, sử dụng `optional:` trên từng location thường giúp ý định rõ ràng và tránh vô tình bỏ qua file thiết yếu.

**Chú ý:** `optional:` giúp bỏ qua lỗi location bị thiếu. Nó không biến file sai cú pháp, sai quyền truy cập, dữ liệu không hợp lệ hoặc lỗi bind thành cấu hình hợp lệ.

## 8. Thứ tự ưu tiên: cấu hình đến sớm chưa chắc là giá trị cuối cùng

**Thời điểm** một nguồn được cung cấp và **độ ưu tiên** của nguồn đó là hai khái niệm khác nhau.

Trong Spring Boot 3.3, xét các nguồn quen thuộc khi ứng dụng chạy thông thường, thứ tự ưu tiên đối với cùng khóa điển hình là:

```text
(defaultProperties) < @PropertySource < Config Data
                    < OS environment < Java -D
                    < SPRING_APPLICATION_JSON < --command-line
```

Đây là phần rút gọn của toàn bộ danh sách PropertySource mặc định; các nguồn như `random.*`, JNDI, Servlet init params, test và Devtools cũng có các mức riêng.

Ví dụ:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./from-env/ \
java -Dspring.config.additional-location=optional:file:./from-jvm/ \
  -jar myapp.jar \
  --spring.config.additional-location=optional:file:./from-cli/
```

Đối với **cùng một khóa** `spring.config.additional-location`, command line có mức ưu tiên cao hơn JVM property và biến môi trường, nên giá trị có hiệu lực là `optional:file:./from-cli/` theo cơ chế mặc định.

Tuy nhiên, **một file Config Data được nạp sau không thể dùng giá trị `spring.config.location` bên trong nó để thay đổi quyết định bootstrap đã diễn ra**. Nó có thể chứa các property ứng dụng bình thường và `spring.config.import`, nhưng không được xem như một nguồn dùng để khởi động lại bước chọn search location.

Một cách suy nghĩ chính xác:

1. **Trước Config Data:** nguồn sớm cung cấp `name/location/additional-location`; Spring Boot xác định đường tìm kiếm ban đầu từ giá trị có hiệu lực trong các nguồn này.
2. **Trong Config Data:** bộ nạp đọc file, xử lý imports/profiles và sắp thứ tự các Config Data PropertySource.
3. **Sau khi nạp:** các property đã có mặt trong `Environment` được giải quyết theo mức ưu tiên thực tế; một property ứng dụng như `server.port` vẫn có thể bị command-line hoặc JVM system property ghi đè.

Vì thế, nếu cần thay đổi nơi nạp cấu hình theo môi trường triển khai, hãy đặt **khóa bootstrap** vào nguồn đã sẵn sàng trước giai đoạn Config Data, đồng thời sử dụng `additional-location`/`import` phù hợp để quản lý phần nội dung cấu hình.

## 9. Các trường hợp “có cấu hình nhưng Spring Boot không nhận”

### Tình huống A — Đặt `spring.config.location` trong file mặc định

```properties
# src/main/resources/application.properties
spring.config.location=file:./server-config/
```

**Kỳ vọng sai:** Boot đọc file này, sau đó tìm lại cấu hình ở `./server-config/` và thay thế các location ban đầu.

**Giải thích:** location ban đầu đã được quyết định trước khi file được nạp; chỉ dẫn đổi location trong file không phải cơ chế redirect tìm kiếm. Nếu ứng dụng cần đọc `./server-config/`, đưa `spring.config.location` hoặc `spring.config.additional-location` ra command line/JVM/OS environment.

### Tình huống B — `@PropertySource` khai báo đường dẫn

```java
@Configuration
@PropertySource("classpath:bootstrap.properties")
class EarlyProperties {
}
```

Trong `bootstrap.properties`:

```properties
spring.config.name=service
```

**Vấn đề:** `@PropertySource` được thêm khi context refresh, muộn hơn giai đoạn xử lý Config Data. Không dựa vào `@PropertySource` để điều khiển file nào phải được nạp. Đây cũng là một lý do Spring Boot khuyến nghị các khóa như `logging.*` và `spring.main.*` được cung cấp từ nguồn đủ sớm khi hành vi cần diễn ra trước refresh.

### Tình huống C — Đổi biến môi trường sau khi tiến trình đã chạy

```bash
# ứng dụng đã chạy ở terminal hoặc container khác
export SPRING_CONFIG_LOCATION=file:./new-location/
```

Việc chỉnh environment của shell **không thay đổi Environment của tiến trình Java đang chạy**. Cần khởi động một tiến trình mới (hoặc thiết kế riêng một cơ chế refresh cấu hình với semantics phù hợp) để lựa chọn nơi nạp Config Data được áp dụng.

### Tình huống D — Dùng path tương đối nhưng working directory khác

```bash
java -jar /opt/apps/myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

Nếu lệnh chạy từ `/home/operator`, location là `/home/operator/deploy/`, không phải `/opt/apps/deploy/`. Dùng đường dẫn tuyệt đối hoặc cố định working directory trong service manager/container manifest khi cần tính xác định.

### Tình huống E — Dùng location thay vì additional-location

```bash
java -jar myapp.jar --spring.config.location=file:./deploy/
```

Ở đây người viết có thể vô tình **thay toàn bộ vị trí mặc định**, làm file `application.properties` đóng trong JAR không còn được tìm như mong đợi. Khi chỉ muốn bổ sung cấu hình triển khai vào cấu hình đã đóng gói, dùng:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/
```

### Tình huống F — File cấu hình chứa import lại không được nạp

```text
conf/hidden/application.yaml
  spring.config.import: file:./extra.properties
```

Nếu `conf/hidden/` không phải location đang được tìm, Boot không đọc được dòng import này. Đầu tiên cần nạp được **file chứa import**. Import không phải cơ chế tự tìm toàn bộ tệp trên ổ đĩa.

### Tình huống G — Chỉnh `spring.config.*` từ bean trong `@PostConstruct`

```java
@PostConstruct
void init() {
    System.setProperty("spring.config.name", "service");
}
```

Lời gọi này chạy khi bean đã được tạo, quá muộn so với quá trình Config Data. Nó có thể làm thay đổi một JVM property tại thời điểm sau đó, nhưng không khiến Boot tự bắt đầu lại quá trình tìm và nạp file của startup hiện tại.

## 10. Khi nào nên tự viết `EnvironmentPostProcessor`?

`EnvironmentPostProcessor` cho phép mở rộng cách chuẩn bị `Environment` trước khi tạo/refresh context. Tuy nhiên, **không phải mọi implementation đều chạy trước bộ xử lý Config Data**: chúng có thứ tự `Ordered` và được Spring Boot gọi trong chuỗi xử lý Environment.

Nếu cần bổ sung một property **để `ConfigDataEnvironmentPostProcessor` đọc được**, implementation phải được **đăng ký và chạy sớm hơn** Config Data processor; chỉ viết một `EnvironmentPostProcessor` rồi đặt thuộc tính là chưa đủ. Ngoài ra, nếu muốn nạp một định dạng cấu hình mới như một phần của Config Data, có thể cần cơ chế `ConfigDataLocationResolver`/`ConfigDataLoader` phù hợp, tùy mục đích.

Đối với việc đơn thuần truyền đường dẫn file tại môi trường triển khai, command line, `-D`, OS environment hoặc `setDefaultProperties` trước `run` đơn giản và rõ ràng hơn. Các extension point kể trên dành cho yêu cầu framework/launcher thực sự cần tùy biến.

Không nên dùng `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct` hoặc `@Value` trong bean để thay đổi `spring.config.location` của cùng lần khởi động.

## 11. Cách kiểm tra cấu hình được nạp từ đâu

1. **Xác định giá trị bootstrap trước startup.** Ghi lại command-line options, JVM `-D`, các biến `SPRING_CONFIG_*` và mã cấu hình `SpringApplication` trước `run`.
2. **Phân biệt `location` và `additional-location`.** Kiểm tra có vô tình mất tập location mặc định hay không.
3. **Kiểm tra `spring.config.name`.** Nếu đã đổi basename thành `service`, đừng tìm `application.yaml` theo mặc định mà bỏ qua `service.yaml`.
4. **Xác định working directory.** Với `file:./...`, kiểm tra thư mục thực tế tiến trình dùng, dấu `/` ở cuối location thư mục và việc file có tồn tại hay không.
5. **Đọc thứ tự các import và profile.** Import được xử lý từ tài liệu chứa nó; file theo profile chỉ tham gia khi profile được kích hoạt.
6. **Dùng log khi cần.** Có thể thử mức log `TRACE` cho `org.springframework.boot.context.config` để quan sát việc nạp Config Data (phạm vi chi tiết log phụ thuộc cấu hình logging và thời điểm khởi tạo).
7. **Kiểm tra kết quả sau startup.** `Environment` hoặc Actuator `env` có thể cho biết giá trị và nguồn PropertySource thực tế; bảo vệ endpoint chẩn đoán và tránh in cấu hình nhạy cảm.

Ví dụ cung cấp cấu hình log khi chạy:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deploy/ \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Tuy nhiên, log lúc startup chỉ là công cụ hỗ trợ; việc xác nhận đường dẫn vẫn cần dựa trên **giá trị được cung cấp trước khi xử lý Config Data** và hành vi thực tế.

## 12. Bảng tra cứu nhanh

| Property | Dùng để làm gì? | Nên khai báo ở đâu? | Vì sao? |
| --- | --- | --- | --- |
| `spring.config.name` | Chọn basename thay `application` | CLI `--`, JVM `-D`, OS env, default properties trước `run` | Phải biết tên file trước khi đi tìm |
| `spring.config.location` | **Thay thế** location mặc định | CLI/JVM/OS env hoặc launcher đủ sớm | Phải biết nơi tìm trước khi đọc Config Data |
| `spring.config.additional-location` | **Bổ sung** location vào defaults | CLI/JVM/OS env hoặc launcher đủ sớm | Phải thêm nơi tìm trước khi đọc file |
| `spring.config.import` | Nhập thêm Config Data từ tài liệu đã tìm thấy | `application.properties`/YAML hoặc nguồn Config Data phù hợp | Được đọc **trong** lúc xử lý Config Data |
| `spring.config.activate.on-profile` | Kích hoạt một document theo profile | Trong Config Data document | Là điều kiện chọn tài liệu đang được xử lý |
| `spring.profiles.active` | Xác định active profiles | Nguồn ngoài hoặc tài liệu chung hợp lệ | Chọn biến thể profile trong quá trình Config Data, tuân thủ hạn chế profile-specific |
| `spring.config.on-not-found` | Chính sách xử lý location không tìm thấy | Nguồn đủ sớm cho Config Data | Cần được biết khi xử lý lỗi location |
| `app.*`, `server.port`... | Các giá trị cấu hình ứng dụng | File Config Data, OS env, JVM, CLI… | Tiêu thụ sau khi nguồn tương ứng có mặt trong `Environment` |

## 13. Một kịch bản triển khai hoàn chỉnh

Giả sử ứng dụng có cấu trúc:

```text
myapp.jar
deployment/
  application-prod.properties
extras/
  feature-flags.properties
```

File đóng gói trong JAR:

```properties
# classpath:/application.properties
app.name=order-service
app.timeout=3s
spring.config.import=optional:file:./extras/feature-flags.properties
```

File import:

```properties
# ./extras/feature-flags.properties
app.feature.new-checkout=true
```

File ngoài JAR theo profile:

```properties
# ./deployment/application-prod.properties
app.timeout=10s
```

Command line:

```bash
java -jar myapp.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./deployment/
```

**Diễn tiến nạp:**

1. Trước Config Data, `Environment` đã nhận `spring.profiles.active=prod` và `spring.config.additional-location=optional:file:./deployment/` từ command line.
2. Bộ nạp tìm file theo các vị trí mặc định và thêm `./deployment/` theo giá trị đã được cung cấp sớm.
3. Khi đọc `classpath:/application.properties`, bộ nạp thấy `spring.config.import`, rồi nạp `./extras/feature-flags.properties` nếu file tồn tại.
4. Vì profile `prod` active, `./deployment/application-prod.properties` tham gia vào nhóm Config Data tương ứng.
5. Sau khi nạp, `app.name` đến từ file trong JAR, `app.feature.new-checkout` từ file import, và `app.timeout` là `10s` từ file ngoài JAR theo profile, nếu không có nguồn ưu tiên cao hơn ghi đè.

Đây là ví dụ kết hợp **cấu hình bootstrap từ sớm**, **import từ file đã tìm thấy** và **override theo profile ở location bổ sung** trong một lần startup.

## 14. Tài liệu tham khảo

- Spring Boot 3.3 Reference — *Externalized Configuration*, các phần **Config Data Files**, **Optional Locations**, **Wildcard Locations**, **Profile Specific Files**, **Importing Additional Data**, **PropertySource Order**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigDataEnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.3 Reference — *Application Events and Listeners*, *EnvironmentPostProcessor*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Ghi nhớ:** `spring.config.name`, `spring.config.location` và `spring.config.additional-location` là **đầu vào để chọn file**, nên phải có **trước khi bộ nạp Config Data quyết định nơi tìm kiếm**. `spring.config.import` là **chỉ dẫn trong file đã được tìm**, nên được xử lý khi file đó đang được nạp. Phân biệt đúng hai thời điểm này giúp tránh phần lớn lỗi “đã khai báo `spring.config.*` nhưng Spring Boot không đọc được cấu hình mong muốn”.
