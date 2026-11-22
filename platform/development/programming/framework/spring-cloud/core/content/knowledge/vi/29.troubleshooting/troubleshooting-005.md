# Nguồn cấu hình từ xa ghi đè giá trị cục bộ ngoài dự kiến

Khi một ứng dụng Spring Cloud lấy cấu hình từ Config Server, Vault, Consul hoặc Kubernetes, cùng một property có thể xuất hiện ở nhiều nơi: file `application.yml` đóng gói trong JAR, file cấu hình đặt cạnh JAR, biến môi trường, JVM system property, command line và property source từ xa. Giá trị mà bean nhận được phụ thuộc vào thứ tự ưu tiên của các nguồn này và cách ứng dụng nạp chúng.

Một tình huống thường gặp là developer đặt `catalog.timeout=2s` trong cấu hình cục bộ nhưng ứng dụng vẫn dùng `5s` từ Config Server. Đây có thể là hành vi đúng theo cơ chế bootstrap legacy của Spring Cloud, hoặc do Config Data import được đặt ở vị trí có độ ưu tiên cao hơn file khai báo import. Cũng có thể giá trị đến từ một profile, một file ngoài JAR, một biến môi trường hay một cấu hình dùng chung ở phía Config Server.

Bài học thuộc chương **Chẩn đoán sự cố** của module `SPRING_CLOUD_CORE`. Nội dung hướng dẫn xác định chính xác property source đang thắng, phân biệt Config Data với legacy bootstrap, hiểu các cờ `allowOverride`, `overrideNone`, `overrideSystemProperties`, kiểm tra server-side overrides và xử lý xung đột giữa nhiều nguồn cấu hình.

## 1. Nhận diện triệu chứng và phạm vi sự cố

Một lỗi precedence thường có các biểu hiện:

- Giá trị trong `application.yml` khác giá trị được inject vào bean.
- Thay biến môi trường nhưng ứng dụng vẫn nhận giá trị từ xa.
- Cùng một artifact chạy local và production cho kết quả khác nhau.
- Chỉ profile `prod` hoặc `staging` bị ghi đè.
- Config Server trả về đúng file nhưng client lại chọn giá trị từ property source khác.
- Sau khi refresh, bean vẫn giữ giá trị cũ hoặc nhận giá trị không mong muốn.
- Một property được định nghĩa trong `application.yml`, `bootstrap.yml`, ConfigMap và Config Server với các giá trị khác nhau.

Trước khi sửa, xác định ba thông tin:

1. **Property key:** tên chính xác mà bean đọc, ví dụ `catalog.timeout`.
2. **Effective value:** giá trị thực tế trong `Environment` hoặc bean.
3. **Winning property source:** nguồn và vị trí có độ ưu tiên cao nhất đang cung cấp key đó.

Không bắt đầu bằng việc thêm cùng một key vào nhiều file. Điều đó làm số nguồn xung đột tăng lên và khiến lần chẩn đoán sau khó hơn.

## 2. Spring Boot quyết định property nào thắng như thế nào?

Spring Boot tập hợp cấu hình thành các `PropertySource` trong `Environment`. Khi nhiều nguồn có cùng key, nguồn có độ ưu tiên cao hơn được dùng để phân giải giá trị.

Trong thứ tự mặc định của Spring Boot hiện đại, các nguồn phổ biến được xét từ thấp tới cao như sau:

| Thứ tự | Property source | Ví dụ |
| --- | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | File được nạp từ configuration class |
| 3 | Config Data | `application.yml`, file profile, file được import |
| 4 | Random value source | `random.*` |
| 5 | OS environment variables | `CATALOG_TIMEOUT=3s` |
| 6 | Java system properties | `-Dcatalog.timeout=4s` |
| 7 | JNDI | `java:comp/env/...` |
| 8 | ServletContext init parameters | Tham số cấu hình servlet |
| 9 | ServletConfig init parameters | Tham số của servlet |
| 10 | `SPRING_APPLICATION_JSON` | JSON inline trong environment hoặc system property |
| 11 | Command line arguments | `--catalog.timeout=6s` |
| 12 trở đi | Test property sources và Devtools | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`, Devtools |

Bảng này mô tả thứ tự chung của Spring Boot. Spring Cloud có thể bổ sung remote property source theo cơ chế bootstrap riêng; vì vậy phải xác định ứng dụng đang dùng cách nạp cấu hình nào trước khi áp dụng bảng này.

Ví dụ nếu cùng key xuất hiện ở file local, biến môi trường và command line:

```yaml
# application.yml
catalog:
  timeout: 2s
```

```text
CATALOG_TIMEOUT=3s
```

```bash
java -jar catalog.jar --catalog.timeout=6s
```

Giá trị được chọn là `6s` vì command line có độ ưu tiên cao hơn environment variable và file cấu hình. Việc thấy `2s` trong file không chứng minh bean sẽ nhận `2s`.

### 2.1. Config Data có thứ tự riêng bên trong nhóm cấu hình

Trong nhóm Config Data, file đóng gói trong JAR và file bên ngoài JAR có thứ tự khác nhau. Các file profile-specific cũng được xét theo thứ tự tương ứng.

Ví dụ, file `application-prod.yml` bên ngoài JAR có thể ghi đè giá trị trong `application.yml` đóng gói trong JAR khi profile `prod` được kích hoạt. Các location được khai báo sau trong `spring.config.location` hoặc `spring.config.additional-location` có thể ghi đè location được xử lý trước.

Spring Boot cũng quy định cấu hình được nạp qua `spring.config.import` có độ ưu tiên cao hơn document đã khai báo import. Nếu có nhiều import, import được xử lý sau có thể ghi đè import trước.

### 2.2. `spring.config.location` và `spring.config.additional-location`

Hai thuộc tính này có mục đích khác nhau:

- `spring.config.location` thay thế các location mặc định cần tìm.
- `spring.config.additional-location` bổ sung location ngoài các location mặc định.

Ví dụ:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/catalog/
```

File cấu hình trong `/etc/catalog/` có thể ghi đè giá trị từ location mặc định. Nếu vô tình đặt cùng key trong file này, developer có thể tưởng Config Server đã ghi đè local config trong khi giá trị thực ra đến từ file ngoài JAR.

Hai thuộc tính này được đọc rất sớm trong startup. Nên cung cấp chúng bằng environment variable, system property hoặc command line thay vì đặt trong file mà chính chúng đang điều khiển việc tìm kiếm.

## 3. Phân biệt Config Data import và legacy bootstrap

Đây là bước quan trọng nhất khi chẩn đoán Spring Cloud Config. Hai cơ chế có quy tắc nạp và điều khiển precedence khác nhau.

| Cơ chế | Cách bật | Đặc điểm precedence |
| --- | --- | --- |
| Config Data import | `spring.config.import=configserver:...` | Remote data được nạp như Config Data; import có độ ưu tiên cao hơn document khai báo import |
| Legacy bootstrap | `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` | Bootstrap context nạp remote property source với độ ưu tiên cao; mặc định local config không ghi đè remote source |

Không áp dụng các cờ điều khiển legacy bootstrap cho Config Data import rồi giả định chúng thay đổi thứ tự của import. Hãy đọc tài liệu của đúng cơ chế và version đang dùng.

### 3.1. Config Data import

Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "optional:configserver:http://config-server:8888"
```

Giá trị từ Config Server được nạp qua Config Data. Vì imported data có độ ưu tiên cao hơn document khai báo import, một property trùng trong chính document đó có thể bị remote value ghi đè.

Nếu muốn cấu hình local có độ ưu tiên cao hơn remote Config Server, có thể dùng một import local riêng được khai báo sau Config Server:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:file:./config/local-overrides.yml"
```

File `local-overrides.yml`:

```yaml
catalog:
  timeout: 2s
```

Trong ví dụ này, import local được xử lý sau import Config Server nên giá trị trong file local override có độ ưu tiên cao hơn giá trị cùng key từ Config Server. Hãy xác minh thứ tự import trong log Config Data và kiểm thử bằng đúng phiên bản Spring Boot/Config Client đang chạy.

Nếu muốn override theo môi trường triển khai, có thể dùng environment variable, JVM system property hoặc command line vì các nguồn này có độ ưu tiên cao hơn Config Data.

### 3.2. Legacy bootstrap

Legacy bootstrap tạo một bootstrap context làm parent của application context. Remote property source thường được thêm với độ ưu tiên cao hơn local application configuration.

Bật bootstrap bằng starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
```

Hoặc bật bằng environment/system property:

```text
SPRING_CLOUD_BOOTSTRAP_ENABLED=true
```

Khi bootstrap được bật, ứng dụng có thể dùng `bootstrap.yml` để cấu hình thông tin kết nối Config Server:

```yaml
spring:
  application:
    name: catalog-service
  cloud:
    config:
      uri: http://config-server:8888
```

Trong mô hình này, nếu Config Server trả `catalog.timeout=5s` và `application.yml` cục bộ đặt `catalog.timeout=2s`, remote property source mặc định có thể thắng. Muốn thay đổi behavior, remote property source phải cấp quyền override cho client.

### 3.3. Không bật đồng thời hai cơ chế một cách tùy tiện

Không nên vừa dùng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`, vừa dùng `spring.config.import` để nạp cùng Config Server hay cùng một nhóm property source. Hai cơ chế có lifecycle và thứ tự khác nhau; việc nạp trùng làm khó xác định nguồn thắng.

Chọn một cơ chế nhất quán, ghi rõ trong runbook và test đúng thứ tự property source. Nếu đang chuyển từ bootstrap legacy sang Config Data, xem đây là một bước migration cần kiểm thử, không chỉ xóa `bootstrap.yml` rồi đổi một dòng import.

## 4. Các cờ điều khiển override của legacy bootstrap

Spring Cloud Context cung cấp ba property để điều khiển việc local source có được ghi đè remote source hay không:

- `spring.cloud.config.allowOverride`
- `spring.cloud.config.overrideNone`
- `spring.cloud.config.overrideSystemProperties`

**Điểm dễ mắc lỗi nhất:** `spring.cloud.config.allowOverride=true` phải được đặt trong cấu hình từ xa do Config Server cung cấp. Đặt nó trong `application.yml` cục bộ không cấp quyền override cho remote property source.

### 4.1. `allowOverride=true`

Property này cho phép remote property source nhường một phần quyền ưu tiên để local property source có thể override.

Ví dụ đặt trong repository cấu hình mà Config Server phục vụ:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
```

Không đặt property này chỉ trong file local và mong Config Server thay đổi precedence. Config Client cần nhận được quyền này từ remote property source.

### 4.2. `overrideNone=true`

Khi `allowOverride=true` và `overrideNone=true`, các local property source có thể override remote property source.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideNone: true

catalog:
  timeout: 5s
```

Với legacy bootstrap, local `application.yml`, profile-specific config, environment variables, system properties và command line có thể cung cấp giá trị thay thế theo thứ tự của chúng.

Đây là lựa chọn phù hợp khi remote configuration đóng vai trò default chung và mỗi deployment được phép đặt giá trị riêng.

### 4.3. `overrideSystemProperties=false`

Khi `allowOverride=true` và `overrideSystemProperties=false`, chỉ system properties, command line arguments và environment variables được phép override remote settings; local config files không được dùng để ghi đè remote values.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideSystemProperties: false
      overrideNone: false
```

Kết quả mong muốn:

- `application.yml` cục bộ không thay thế remote value.
- Biến môi trường có thể thay thế remote value.
- JVM system property có thể thay thế remote value.
- Command line argument có thể thay thế remote value.

Cách này hữu ích khi đội nền tảng muốn Config Server quản lý cấu hình ứng dụng, nhưng vẫn cho phép deployment inject một số giá trị runtime qua environment hoặc JVM.

### 4.4. Bảng lựa chọn nhanh

| Mục tiêu với legacy bootstrap | Cấu hình trong remote repository |
| --- | --- |
| Remote config thắng local sources theo mặc định | Không cấp `allowOverride` hoặc để `false` |
| Cho phép mọi local source override remote | `allowOverride=true`, `overrideNone=true` |
| Chỉ cho env/system/command line override; file local không override | `allowOverride=true`, `overrideSystemProperties=false` |
| Muốn đổi behavior nhưng chỉ đặt cờ trong `application.yml` local | Không có hiệu lực cấp quyền override remote |

Các cờ này không thay thế quy tắc precedence của Spring Boot. Sau khi remote source cho phép override, các local source vẫn được sắp xếp theo thứ tự ưu tiên của chúng.

## 5. Phân biệt server-side overrides với property thông thường

Spring Cloud Config Server có tính năng `spring.cloud.config.server.overrides` để operator cung cấp một tập property dùng chung cho các Config Client.

Ví dụ cấu hình ở phía Config Server:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          company:
            support-url: https://support.example.com
          platform:
            request-timeout: 3s
```

Các property này được đưa vào response cấu hình cho client. Chúng hữu ích cho giá trị dùng chung, nhưng không phải cơ chế bảo mật tuyệt đối: client vẫn là ứng dụng chạy trong môi trường do operator quản lý và có thể có cách nạp hoặc sử dụng property khác.

### 5.1. `overrideNone` với server-side overrides

Tài liệu Config Server mô tả `spring.cloud.config.overrideNone=true` trong repository từ xa như một cách làm các server overrides gần với default hơn, cho phép ứng dụng cung cấp giá trị riêng qua environment hoặc system properties.

Nếu muốn thay đổi cách server-side overrides hoạt động, hãy xác định rõ:
- Property đang nằm trong `spring.cloud.config.server.overrides` hay trong file cấu hình ứng dụng ở repository.
- Client dùng Config Data hay legacy bootstrap.
- Config Server và Config Client thuộc version nào.
- Giá trị override đang đến từ property source nào.

Không nhầm `spring.cloud.config.server.overrides` (cấu hình operator ở Config Server) với `spring.cloud.config.allowOverride` (quyền override của remote property source phía client).

### 5.2. Dùng placeholder khi cần giá trị local làm đầu vào

Một cách khác là để remote config định nghĩa biểu thức placeholder, rồi client resolve một giá trị local.

Ví dụ trong cấu hình server-side override:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          catalog:
            display-name: \${local.catalog.display-name:Catalog mặc định}
```

Nếu muốn placeholder được resolve ở phía client, cần escape theo cú pháp mà Spring Cloud Config quy định. Khi đó `local.catalog.display-name` có thể đến từ local property source.

Cách này hữu ích khi remote config cần định nghĩa cấu trúc chung nhưng mỗi deployment cung cấp một phần giá trị riêng. Hãy kiểm thử kết quả sau khi Config Server serialize property source và Config Client resolve placeholder; không dựa vào việc chuỗi placeholder xuất hiện đúng trong response là đủ.

## 6. Thứ tự các property source do Config Server trả về

Config Server thường kết hợp cấu hình chung, cấu hình theo profile, cấu hình theo ứng dụng và các nguồn chia sẻ.

Với cấu hình file-based mặc định, một request có dạng:

```text
GET /{application}/{profile}/{label}
```

Ba tham số thường được xác định từ client:

| Tham số | Giá trị mặc định/nguồn | Ví dụ |
| --- | --- | --- |
| `application` | `spring.application.name` | `catalog-service` |
| `profile` | Active profiles của client | `prod` |
| `label` | Label mặc định của repository | `main`, branch hoặc commit ID |

Config Server phục vụ `application.yml` như cấu hình nền cho các ứng dụng. Cấu hình ứng dụng cụ thể và profile cụ thể được thêm vào theo thứ tự của repository.

Ví dụ khi client dùng `spring.application.name=catalog-service`, profile `prod`, các nguồn có thể được trả về theo thứ tự:

1. `application.yml`
2. `application-prod.yml`
3. `catalog-service.yml`
4. `catalog-service-prod.yml`

Các property source xuất hiện sau có thể thắng các source trước trong response. Nếu dùng `spring.cloud.config.name` với danh sách nhiều tên, thứ tự tên cũng ảnh hưởng precedence: tên xuất hiện sau có thể override tên trước.

### 6.1. Kiểm tra sai application name

Một lỗi thường gặp là Config Client gửi sai application name. Ví dụ service đặt:

```yaml
spring:
  application:
    name: catalog
```

nhưng repository lại chứa `catalog-service-prod.yml`. Client có thể nhận cấu hình chung hoặc cấu hình của một tên khác với kỳ vọng.

Kiểm tra `spring.application.name`, `spring.cloud.config.name`, profile và label. Không thêm file local để bù cho việc client đang yêu cầu sai cấu hình từ server.

### 6.2. Kiểm tra active profile

Nếu `prod` chưa được kích hoạt, Config Server có thể trả về cấu hình default thay vì `prod`. Nếu nhiều profile được kích hoạt, thứ tự profile cũng ảnh hưởng cách ghép cấu hình.

Kiểm tra các nguồn cung cấp `spring.profiles.active`:
- Environment variable `SPRING_PROFILES_ACTIVE`.
- JVM argument `-Dspring.profiles.active=...`.
- Command line `--spring.profiles.active=...`.
- Local config và remote config có khả năng kích hoạt thêm profile.
- Profile group hoặc profile include nếu ứng dụng sử dụng.

Với Config Data, client có thể gọi Config Server nhiều lần trong quá trình xác định profile: lần đầu với profile `default`, sau đó với các profile được kích hoạt. Nhiều request trong startup không nhất thiết là lỗi hoặc retry.

### 6.3. Kiểm tra label và phiên bản repository

`spring.cloud.config.label` có thể trỏ tới branch, tag hoặc commit ID. Một label cũ có thể khiến client nhận giá trị đã bị thay đổi trong branch hiện tại.

Ghi nhận label thực tế mà client yêu cầu. Trong môi trường cần rollback, dùng label có thể tái tạo và kiểm tra được, thay vì phụ thuộc ngầm vào một branch di chuyển liên tục.

## 7. Nhiều nguồn remote cùng tồn tại

Một ứng dụng có thể nhận property từ Config Server, Kubernetes ConfigMap/Secret, Vault, Consul hoặc custom `PropertySourceLocator`.

Không mặc định rằng mọi remote source có cùng thứ tự. Cơ chế nạp và provider quyết định precedence.

### 7.1. Nhiều `spring.config.import`

Ví dụ:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:kubernetes:"
```

Theo Config Data ordering, import được xử lý sau có độ ưu tiên cao hơn import trước. Trong ví dụ này, Kubernetes property source có thể override Config Server cho cùng key.

Nếu đảo thứ tự, Config Server có thể override Kubernetes source.

Điều này hữu ích khi có chủ đích: Config Server giữ cấu hình chung, còn ConfigMap chứa các giá trị triển khai. Tuy nhiên, nếu không ghi rõ quy ước, operator có thể thay ConfigMap mà không hiểu nó đang thắng Config Server.

### 7.2. Legacy bootstrap với nhiều PropertySourceLocator

Khi dùng legacy bootstrap, các `PropertySourceLocator` có thể được chạy trong bootstrap context. Provider có thể dùng cùng order value; nếu vậy không nên dựa vào thứ tự tình cờ giữa các locator.

Ví dụ Spring Cloud Kubernetes ghi nhận ConfigMap locator và Config Server locator có cùng order trong một số cấu hình legacy. Nếu cần thứ tự xác định giữa Kubernetes và Config Server, tài liệu Spring Cloud Kubernetes khuyến nghị dùng `spring.config.import` thay cho legacy bootstrap.

Không trộn bootstrap property loading và Config Data import trong cùng một ứng dụng khi cơ chế đó không được hỗ trợ.

### 7.3. Custom PropertySourceLocator

Nếu tổ chức có custom locator, kiểm tra:
- Tên `PropertySource` mà locator trả về.
- `@Order` hoặc order metadata.
- Context nơi locator được tạo.
- Thời điểm locator chạy.
- Điều kiện theo application name/profile.
- Property source có bị trùng tên với source khác không.

Một locator tùy chỉnh có thể đưa key lên trước remote Config Server hoặc sau local config mà developer không thấy trong các file YAML.

## 8. Quy trình chẩn đoán từng bước

Khi phát hiện giá trị local bị remote source ghi đè, thực hiện theo thứ tự sau.

### Bước 1 — Chốt key và giá trị hiệu lực

Ghi lại property key, giá trị mong muốn, giá trị thực tế và bean đang sử dụng property. Nếu dùng `@ConfigurationProperties`, kiểm tra object sau binding; nếu dùng `@Value`, xác nhận placeholder chính xác.

Không dùng giá trị hiển thị trong một file riêng lẻ làm bằng chứng.

### Bước 2 — Xác định cơ chế nạp cấu hình

Kiểm tra build và startup configuration để biết ứng dụng dùng:
- `spring.config.import=configserver:...`.
- `spring-cloud-starter-bootstrap`.
- `spring.cloud.bootstrap.enabled=true`.
- Custom `PropertySourceLocator`.
- Nhiều nguồn remote như Config Server và Kubernetes.

Tìm cả environment variable và JVM arguments vì chúng có thể bật legacy bootstrap hoặc thay đổi import location.

### Bước 3 — Kiểm tra application/profile/label

Ghi lại:
- `spring.application.name`.
- `spring.cloud.config.name`.
- Active profiles.
- `spring.cloud.config.profile` nếu có.
- `spring.cloud.config.label`.
- Config Server URI hoặc discovery service ID.

Xác nhận request mà client gửi tới Config Server trỏ đúng cấu hình cần thiết.

### Bước 4 — Liệt kê tất cả nguồn có key trùng

Tìm key trong:
- `application.yml` đóng gói trong JAR.
- `application-{profile}.yml`.
- File cấu hình bên ngoài JAR.
- `bootstrap.yml` nếu legacy bootstrap được bật.
- Config Server repository.
- `spring.cloud.config.server.overrides`.
- Kubernetes ConfigMap/Secret.
- Environment variables.
- JVM system properties.
- Command line.
- Custom property source.

Ghi lại giá trị và nguồn của từng occurrence.

### Bước 5 — Xem PropertySource order trong runtime

Dùng Actuator `env` và `configprops` trong môi trường được bảo vệ để xác định property source và giá trị đã bind.

Ví dụ các endpoint:

```text
/actuator/env/catalog.timeout
/actuator/configprops
```

Endpoint `env` giúp xem nguồn cung cấp property và thông tin origin khi được hỗ trợ. Endpoint `configprops` giúp kiểm tra giá trị được bind vào `@ConfigurationProperties`.

Chỉ expose các endpoint này trong môi trường phù hợp và bảo vệ bằng authentication/authorization. Không chia sẻ output chứa password, token, connection string hoặc secret.

### Bước 6 — Bật log nạp Config Data khi cần

Nếu dùng Config Data, có thể tăng log:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Log này giúp quan sát location và config document được xử lý. Dùng trong test/staging hoặc phiên chẩn đoán có thời hạn; hạ log level sau khi điều tra.

Với legacy bootstrap, kiểm tra log của Spring Cloud bootstrap/Config Client và property source locator theo version đang dùng.

### Bước 7 — Xác định rule override mong muốn

Chọn một chính sách rõ ràng:

- Remote config là nguồn authoritative.
- Remote config là default, local file có thể override.
- Remote config là default, chỉ deployment environment/system properties được override.
- Một số key được local override, các key còn lại vẫn do remote quản lý.

Đừng áp dụng một cờ global nếu chỉ một vài key cần hành vi khác. Có thể tách property namespace hoặc thiết kế cấu hình theo profile để giảm phạm vi xung đột.

### Bước 8 — Sửa đúng nơi và kiểm thử

- Với legacy bootstrap, thay đổi `allowOverride`/`overrideNone`/`overrideSystemProperties` trong remote repository.
- Với Config Data, sửa thứ tự import hoặc dùng nguồn có precedence cao hơn.
- Với server-side overrides, sửa `spring.cloud.config.server.overrides` nếu giá trị chung được cấu hình sai.
- Với profile/name/label sai, sửa thông tin định danh mà client yêu cầu.
- Với custom locator, sửa order hoặc điều kiện nạp.

Khởi động lại test context hoặc process theo cơ chế đang sử dụng, sau đó xác nhận winning source và giá trị bean.

## 9. Ví dụ thực tế: `catalog.timeout` vẫn là 5 giây

Giả sử local file có:

```yaml
catalog:
  timeout: 2s
```

Config Server trả:

```yaml
catalog:
  timeout: 5s
```

### Trường hợp A — Client dùng legacy bootstrap

Nếu remote property source có độ ưu tiên cao và không cấp quyền override, ứng dụng nhận `5s`.

Nếu muốn mọi local property source có thể override, đặt trong remote repository:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideNone: true

catalog:
  timeout: 5s
```

Sau khi khởi động lại client, local `application.yml` có thể cung cấp `2s`. Kiểm tra lại `/actuator/env/catalog.timeout` để xác nhận source thắng.

### Trường hợp B — Client dùng Config Data import

Cấu hình:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"

catalog:
  timeout: 2s
```

Imported Config Server data có độ ưu tiên cao hơn document khai báo import, nên `5s` có thể thắng.

Nếu muốn file override riêng thắng, khai báo sau Config Server:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:file:./config/local-overrides.yml"
```

Và đặt `catalog.timeout: 2s` trong `local-overrides.yml`. Kiểm tra log Config Data và runtime Environment để xác nhận.

### Trường hợp C — Environment variable đang thắng

Nếu deployment có:

```text
CATALOG_TIMEOUT=7s
```

thì với Config Data import, environment variable có thể thắng giá trị remote `5s` và local file `2s`.

Nếu operator kỳ vọng Config Server là nguồn duy nhất, cần xem manifest/Helm values hoặc deployment environment để tìm biến này. Đừng chỉ sửa repository Config Server vì environment vẫn có thể override.

## 10. Refresh không tự giải quyết lỗi precedence

Spring Cloud Context có `EnvironmentChangeEvent`, `@RefreshScope` và các cơ chế refresh bean. Chúng giúp ứng dụng nhận thay đổi cấu hình sau khi property source được cập nhật.

Tuy nhiên, refresh không làm cho local property source tự nhiên có độ ưu tiên cao hơn remote source. Nếu remote source vẫn thắng theo precedence, refresh sẽ tiếp tục đưa giá trị remote vào bean.

Phân biệt ba việc:

1. **Fetch/update:** property source có nhận được giá trị mới từ remote repository không?
2. **Precedence:** khi cùng key tồn tại ở nhiều nguồn, source nào thắng?
3. **Rebinding/refresh:** bean có được bind lại hoặc khởi tạo lại từ effective value không?

Kiểm tra từng lớp riêng. Nếu property source đúng nhưng bean cũ, điều tra binding hoặc refresh scope. Nếu effective value sai, sửa precedence trước.

## 11. Các lỗi dễ nhầm khi điều tra

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `allowOverride=true` nhưng local file vẫn không thắng | Cờ chỉ được đặt local, không nằm trong remote repository | Xem remote property source có cấp quyền không |
| Đã đặt `overrideNone=true` nhưng không có tác dụng | Client không dùng legacy bootstrap hoặc remote source chưa trả cờ | Xác định Config Data hay bootstrap |
| Chỉ env override được, local YAML không override | `overrideSystemProperties=false` | Kiểm tra policy legacy bootstrap |
| Config Server trả giá trị khác dự kiến | Sai application name/profile/label hoặc server override | Kiểm tra URL request và response |
| `application.yml` trong JAR đúng nhưng runtime khác | File ngoài JAR, profile hoặc import có precedence cao hơn | Kiểm tra Config Data trace và env endpoint |
| Local override file không thắng | Import nằm trước Config Server hoặc file không được nạp | Kiểm tra thứ tự `spring.config.import` |
| Một số property thắng, số khác không | Key trùng ở source khác nhau hoặc binding khác namespace | Xem từng key trong `env`/`configprops` |
| Sau refresh giá trị vẫn cũ | Remote source chưa cập nhật hoặc bean không refresh/rebind | Tách fetch, precedence và refresh |
| Chỉ production bị lỗi | Environment variable, command line, profile, ConfigMap hoặc secret khác local | Kiểm tra deployment manifest |
| ConfigMap và Config Server lúc thắng lúc thua | Legacy locator order không xác định hoặc source order trùng | Chọn Config Data import với thứ tự rõ ràng |
| Test cho kết quả khác runtime | Test property source có precedence cao hơn production source | Kiểm tra `@SpringBootTest`, `@DynamicPropertySource` và `@TestPropertySource` |

## 12. Thiết kế chính sách cấu hình để tránh tái diễn

Một hệ thống nhiều service nên có quy ước rõ ràng về ownership và precedence.

Ví dụ phân chia:

| Loại cấu hình | Nguồn đề xuất | Lý do |
| --- | --- | --- |
| Giá trị mặc định của ứng dụng | Config Server shared/application config | Dùng chung và version hóa |
| Giá trị riêng theo service | Config Server application config | Tách trách nhiệm theo service |
| Giá trị riêng theo môi trường | Profile-specific remote config hoặc deployment config theo policy | Phân biệt dev/staging/prod |
| Secret và credential | Secret manager/Kubernetes Secret | Quản lý vòng đời và quyền truy cập riêng |
| Giá trị cần thay đổi khi deploy | Environment variable hoặc system property nếu policy cho phép | Không phải sửa artifact |
| Tham số debug tạm thời | Command line hoặc test property | Có phạm vi và thời gian sử dụng rõ |

Không nên lưu secret trong `application.yml` hoặc repository cấu hình dạng plain text nếu tổ chức có secret manager. Không dùng cùng một property key cho nhiều mục đích khác nhau chỉ vì tiện.

### 12.1. Chọn một owner cho mỗi key

Với từng property quan trọng, ghi:
- Team sở hữu.
- Nguồn authoritative.
- Có cho phép override ở deployment không.
- Ai có quyền thay đổi.
- Có cần refresh hay restart.
- Cách rollback giá trị.

Ví dụ `spring.datasource.url` có thể do platform team quản lý theo môi trường; `catalog.page-size` có thể do service team quản lý trong Config Server; `logging.level.*` có thể cho phép operator override tạm thời.

### 12.2. Dùng namespace để giảm xung đột

Tách property theo chức năng:

```yaml
catalog:
  business:
    default-page-size: 25
  client:
    timeout: 2s
  feature:
    new-search-enabled: false
```

Không đặt key quá chung như `timeout`, `enabled`, `url` ở nhiều module vì rất dễ trùng tên và gây hiểu nhầm khi xem `/env`.

### 12.3. Ghi nhận nguồn và giá trị hiệu lực

Dashboard hoặc startup diagnostic có thể ghi:
- Application name.
- Active profiles.
- Config Server label/version.
- Build version.
- Property key quan trọng.
- Tên property source thắng.
- Giá trị đã mask nếu có dữ liệu nhạy cảm.

Không log toàn bộ `Environment`. Ghi một allowlist property cần thiết và mask secrets.

## 13. Kiểm thử precedence có tính quyết định

Tạo test cho chính sách override thay vì chỉ kiểm tra ứng dụng có khởi động.

Ví dụ test với Spring Boot Config Data:

```java
@SpringBootTest(properties = {
    "catalog.timeout=9s"
})
class CatalogConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void testPropertySourceOverridesConfigData() {
        assertThat(environment.getProperty("catalog.timeout"))
            .isEqualTo("9s");
    }
}
```

Ví dụ này kiểm tra test property source có thể override Config Data. Nó không thay thế integration test với Config Server thật.

Các test cần có:

1. Local file và remote Config Server cùng định nghĩa một key.
2. Environment variable override remote Config Data.
3. Command line/system property override theo thứ tự mong muốn.
4. Legacy bootstrap với `allowOverride` không được cấp.
5. Legacy bootstrap với `allowOverride=true`, `overrideNone=true`.
6. Legacy bootstrap với `overrideSystemProperties=false`.
7. Server-side overrides có giá trị mong đợi.
8. Profile và label khác nhau trả đúng property source.
9. Hai hoặc nhiều `spring.config.import` có thứ tự xác định.
10. Refresh cập nhật bean từ effective value, không phải từ source thấp hơn.

Với test cần Config Server, dùng repository test hoặc server giả lập có response cố định. Không để test phụ thuộc vào Config Server production.

## 14. Checklist xử lý sự cố

- [ ] Đã xác định property key và effective value.
- [ ] Đã xác định bean đọc property bằng `@Value` hay `@ConfigurationProperties`.
- [ ] Đã xác định client dùng Config Data import hay legacy bootstrap.
- [ ] Đã kiểm tra `spring.application.name`, profile và label.
- [ ] Đã tìm tất cả nơi định nghĩa cùng key.
- [ ] Đã kiểm tra external config location và profile-specific files.
- [ ] Đã kiểm tra `spring.config.import` ordering nếu dùng Config Data.
- [ ] Đã kiểm tra `allowOverride` ở remote repository nếu dùng legacy bootstrap.
- [ ] Đã kiểm tra `overrideNone` và `overrideSystemProperties` theo policy.
- [ ] Đã kiểm tra Config Server `server.overrides`.
- [ ] Đã kiểm tra ConfigMap, Secret, Vault, Consul và custom property sources nếu có.
- [ ] Đã xem `/actuator/env` và `/actuator/configprops` trong môi trường bảo vệ.
- [ ] Đã xác nhận property source thắng và giá trị bean sau startup/refresh.
- [ ] Đã thêm test để ngăn lỗi precedence tái diễn.
- [ ] Đã ghi lại owner và nguồn authoritative của property.

### Câu hỏi tự kiểm tra

1. Vì sao `application.yml` local có thể không thắng remote Config Server?
2. Spring Boot quyết định effective value bằng cách nào?
3. Config Data import khác legacy bootstrap về precedence như thế nào?
4. Vì sao `spring.cloud.config.allowOverride=true` phải nằm trong remote repository?
5. `overrideNone=true` thay đổi điều gì?
6. `overrideSystemProperties=false` cho phép những nguồn nào override remote?
7. `spring.cloud.config.server.overrides` khác `allowOverride` thế nào?
8. Vì sao nhiều import trong `spring.config.import` có thể tạo precedence khác nhau?
9. Làm sao xác định application name/profile/label client đang yêu cầu?
10. Vì sao refresh không tự cập nhật lỗi property source precedence?
11. Khi nào nên dùng Actuator `env` và `configprops`?
12. Vì sao không nên bật đồng thời legacy bootstrap và Config Data import cho cùng nguồn?

**Gợi ý đáp án:** (1) Vì remote property source hoặc imported Config Data có thể có độ ưu tiên cao hơn; (2) Bằng thứ tự các PropertySource trong Environment; (3) Config Data theo quy tắc import của Spring Boot, legacy bootstrap thêm remote source ưu tiên cao và mặc định không cho local override; (4) Client phải nhận quyền từ remote property source, cờ local không cấp quyền; (5) Cho phép mọi local property source override remote source trong legacy bootstrap; (6) Environment variables, JVM system properties và command line, không gồm local config files; (7) Một bên là map property operator phát cho client, một bên là quyền override của remote property source; (8) Import sau có độ ưu tiên cao hơn import trước; (9) Kiểm tra `spring.application.name`, `spring.cloud.config.name/profile/label`, active profiles và request Config Server; (10) Refresh chỉ cập nhật/rebind theo effective value, không tự thay thứ tự source; (11) Khi cần xác định nguồn và giá trị hiệu lực, trong môi trường được bảo vệ; (12) Vì lifecycle và ordering khác nhau, có thể nạp trùng và làm kết quả khó dự đoán.

## 15. Những nguyên tắc cần nhớ

- Luôn xác định cơ chế nạp cấu hình trước khi thay đổi precedence.
- Config Data import và legacy bootstrap có quy tắc khác nhau; không dùng lẫn các cờ điều khiển của chúng.
- Trong legacy bootstrap, remote property source mặc định có ưu tiên cao và không bị local config override.
- `spring.cloud.config.allowOverride=true` phải được cung cấp từ remote repository.
- `overrideNone=true` cho phép local property source override remote trong legacy bootstrap.
- `overrideSystemProperties=false` giới hạn override ở environment variables, system properties và command line.
- Trong Config Data, import có ưu tiên cao hơn document khai báo import; import sau có thể thắng import trước.
- Kiểm tra application name, profile, label và server-side overrides trước khi sửa local file.
- Nhiều remote source có thể có order phụ thuộc provider; dùng Config Data import khi cần thứ tự xác định.
- Dùng Actuator `env`/`configprops` và log Config Data để tìm source thắng.
- Refresh không thay thế việc sửa precedence; kiểm tra fetch, ordering và bean binding riêng.
- Ghi rõ owner và nguồn authoritative cho từng property quan trọng.

Khi xác định được property source thắng và chính sách override mong muốn, việc sửa lỗi trở nên rõ ràng: thay đổi đúng nguồn, giữ thứ tự nhất quán và thêm test để bảo vệ behavior. Điều này giúp cấu hình từ xa phục vụ quản trị tập trung mà vẫn cho phép các giá trị cục bộ hoặc theo môi trường hoạt động đúng với quyền đã được thiết kế.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Context — Overriding Remote Properties](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
- [Spring Cloud Kubernetes — PropertySource Precedence](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html)
