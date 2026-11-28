# Không có `spring.config.import` hoặc Config Client không được kích hoạt

Khi ứng dụng Spring Boot không nhận cấu hình từ Spring Cloud Config Server, cần xác định trước Config Client có được kích hoạt hay không. Với Spring Boot 2.4 trở lên, cách tích hợp mặc định là đưa `configserver:` vào `spring.config.import`. Chỉ khai báo `spring.cloud.config.uri` không thay thế bước import này. Nếu ứng dụng dùng cơ chế Config First Bootstrap cũ, bootstrap phải được bật riêng và địa chỉ Config Server phải có sẵn trong `bootstrap.yml` hoặc biến môi trường.

Hai tình huống thường bị nhầm lẫn:

- **Config Client chưa được kích hoạt:** dependency không có trên runtime classpath, `spring.cloud.config.enabled=false`, thiếu `spring.config.import` trong Config Data mode, hoặc legacy bootstrap chưa được bật.
- **Config Client đã chạy nhưng không lấy được cấu hình:** import đã được xử lý, nhưng URL, DNS, port, credential, TLS, application name, profile, label hoặc Config Server/backend có vấn đề.

Phân biệt hai nhóm này giúp tránh thay đổi mạng hoặc Config Server khi ứng dụng chưa hề gửi request, và tránh thêm dependency/flag khi client đã chạy nhưng bị cấu hình sai.

## 1. Hiểu hai cách kích hoạt Config Client

Spring Cloud Config Client có hai cách nạp cấu hình chính. Hãy chọn một cách theo phiên bản và kiến trúc ứng dụng.

| Cách | Cơ chế | Cấu hình kích hoạt |
|---|---|---|
| Config Data Import | Spring Boot đọc `spring.config.import` trong giai đoạn Config Data và gọi Config Server | `spring.config.import=optional:configserver:` hoặc `configserver:` |
| Legacy Config First Bootstrap | Bootstrap context được khởi tạo trước Application Context và nạp remote property source | Bật bootstrap bằng `spring.cloud.bootstrap.enabled=true` hoặc `spring-cloud-starter-bootstrap`; đặt URI trong `bootstrap.yml` |

Với Spring Boot 2.4 trở lên, Config Data Import là cách mặc định được Spring Cloud khuyến nghị. Không cần `bootstrap.yml` và không cần `spring-cloud-starter-bootstrap` chỉ để dùng `spring.config.import`. Spring Boot trước 2.4 chưa có Config Data import theo cách này; dùng cơ chế bootstrap tương thích với phiên bản Spring Cloud đang chạy.

Legacy Bootstrap là cơ chế tương thích cũ. Nếu chọn cách này, phải bật bootstrap rõ ràng. Chỉ có `spring-cloud-starter-config` trên classpath không tự bật legacy bootstrap trong các release hiện hành.

## 2. Kiểm tra dependency của Config Client

Ứng dụng cần dependency `org.springframework.cloud:spring-cloud-starter-config`. Đây là starter kéo Config Client vào runtime classpath.

### Maven

Khai báo Spring Cloud BOM tương thích với Spring Boot đang dùng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
```

Không tự chọn version của starter tách rời khỏi release train. Dùng bảng tương thích Spring Boot/Spring Cloud, import đúng BOM và tránh trộn các version Spring Cloud khác release train trong cùng runtime.

### Gradle

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Nếu dùng Gradle dependency management plugin hoặc Spring dependency management, import Spring Cloud BOM tương ứng để quản lý version như Maven.

### Xác minh dependency thực sự có trên runtime classpath

Với Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-config,org.springframework.cloud:spring-cloud-config-client
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra dependency ở module tạo executable JAR/container, không chỉ ở parent POM hoặc module khác. Một dependency được khai báo trong `dependencyManagement` nhưng không được thêm vào `dependencies` thì chưa có mặt trong ứng dụng. Nếu dependency có scope `test` hoặc `provided`, nó có thể không xuất hiện trong runtime artifact.

Nếu không thấy `spring-cloud-config-client` trong dependency tree, Config Client không thể xử lý `configserver:` import. Kiểm tra dependency exclusion, version conflict và cách đóng gói fat JAR.

## 3. Cấu hình tối thiểu bằng `spring.config.import`

Spring Boot 2.4 trở lên cung cấp Config Data API thông qua `spring.config.import`. Đây là cách mặc định được Spring Cloud Config khuyến nghị để nạp cấu hình từ Config Server.

### `application.yml`

```yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config.internal:8888"
```

### `application.properties`

```properties
spring.application.name=order-service
spring.config.import=optional:configserver:http://config.internal:8888
```

Nếu bỏ địa chỉ sau `configserver:`, Config Client mặc định gọi `http://localhost:8888`:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

Địa chỉ được ghi trực tiếp trong import có ưu tiên hơn `spring.cloud.config.uri`. Vì vậy, nếu file có `spring.config.import: configserver:http://localhost:8888` nhưng biến môi trường `SPRING_CLOUD_CONFIG_URI` trỏ sang một host khác, client vẫn dùng URL trong import.

### Phân biệt `optional` và import bắt buộc

```yaml
spring:
  config:
    import: "optional:configserver:http://config.internal:8888"
```

`optional:` cho phép ứng dụng tiếp tục khởi động nếu Config Server không thể được kết nối hoặc nguồn cấu hình tùy chọn không có. Đây vẫn là một lần import Config Server; nó không tắt Config Client.

```yaml
spring:
  config:
    import: "configserver:http://config.internal:8888"
```

Không có `optional:` nghĩa là Config Server là nguồn bắt buộc. Nếu không lấy được cấu hình, ứng dụng dừng khởi động. Cách này phù hợp khi ứng dụng không thể chạy an toàn nếu thiếu cấu hình từ xa, chẳng hạn endpoint hoặc credential bắt buộc.

Không dùng `optional:` để che giấu lỗi kết nối trong production. Nếu ứng dụng có thể khởi động mà thiếu một số cấu hình, phải có default an toàn và validation ngăn ứng dụng chạy khi thiếu giá trị bắt buộc.

## 4. Lỗi “No spring.config.import set” có nghĩa gì?

Khi Config Client có trên classpath nhưng ứng dụng không khai báo import trong Config Data mode, Spring Cloud có thể dừng startup với thông báo tương tự:

```text
No spring.config.import property has been defined

Action:
Add a spring.config.import=configserver: property to your configuration.
If configuration is not required add spring.config.import=optional:configserver: instead.
```

Thông báo này cho biết dependency Config Client được phát hiện nhưng không tìm thấy khai báo `configserver:` cần thiết. Nó chưa chứng minh Config Server bị down.

Hướng xử lý:

1. Nếu ứng dụng cần Config Server, thêm `spring.config.import=configserver:` hoặc `optional:configserver:` với URL phù hợp.
2. Nếu ứng dụng dùng legacy bootstrap, xác nhận bootstrap thực sự được bật và không trộn hai cách nạp cấu hình.
3. Nếu ứng dụng không cần Config Server ở môi trường đó, cân nhắc bỏ starter khỏi module hoặc cấu hình riêng cho môi trường đó theo cơ chế được phiên bản đang dùng hỗ trợ.
4. Không chỉ tắt import check để làm ứng dụng khởi động nếu vẫn cần remote configuration; việc bỏ qua kiểm tra không tạo ra property source từ xa.

Một số release cũ có gợi ý thuộc tính `spring.cloud.config.import-check.enabled=false` để tắt bước kiểm tra. Đây chỉ là tắt guard của phiên bản tương ứng, không phải cách cấu hình Config Server và không chứng minh client đã được kích hoạt đúng. Kiểm tra tài liệu đúng release train trước khi dùng; ưu tiên khai báo import rõ ràng.

## 5. Đặt import ở đâu để Spring Boot đọc được?

Config Client cần biết phải gọi Config Server trước khi có thể nhận cấu hình từ Config Server. Do đó, `spring.config.import` phải nằm trong một nguồn cấu hình cục bộ hoặc nguồn bootstrap đã có sẵn tại thời điểm Config Data được xử lý.

Các vị trí phù hợp:

- `src/main/resources/application.yml`.
- `src/main/resources/application.properties`.
- File cấu hình ngoài JAR được truyền qua `spring.config.location` hoặc `spring.config.additional-location`.
- Biến môi trường `SPRING_CONFIG_IMPORT`.
- Tham số JVM/command line tương ứng.

Ví dụ biến môi trường:

```bash
SPRING_CONFIG_IMPORT=optional:configserver:http://config.internal:8888
SPRING_APPLICATION_NAME=order-service
```

Các vị trí không thể tự kích hoạt lần nạp đầu:

- `spring.config.import` chỉ tồn tại trong repository Git mà Config Server phục vụ.
- `spring.config.import` nằm trong một file remote mà chỉ có thể đọc sau khi Config Client đã kết nối.
- Một file profile-specific không được profile nào kích hoạt.
- Một file ngoài JAR không nằm trong search path của Spring Boot.

Đây là vòng phụ thuộc: muốn đọc cấu hình từ xa thì phải biết địa chỉ và cơ chế import từ trước. Hãy giữ các thông tin tối thiểu như import, Config Server URL và thông tin xác thực ban đầu ở nguồn local/secret injection.

### Kiểm tra YAML có đúng cấu trúc

Đúng:

```yaml
spring:
  config:
    import: "optional:configserver:http://config.internal:8888"
```

Sai do đặt nhầm cấp:

```yaml
spring:
  cloud:
    config:
      import: "optional:configserver:http://config.internal:8888"
```

Thuộc tính phải là `spring.config.import`, không phải `spring.cloud.config.import`.

Nếu dùng `application.properties`, kiểm tra chính tả và dấu phân cách:

```properties
spring.config.import=optional:configserver:http://config.internal:8888
```

Không đặt giá trị import thành một key tùy ý như `config.import` hoặc `spring.cloud.config.uri` rồi mong Config Data tự kích hoạt.

## 6. Cấu hình application name, profile và label

Sau khi import được kích hoạt, Config Client cần xác định tài nguyên mà nó yêu cầu từ Config Server.

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "optional:configserver:http://config.internal:8888"
  cloud:
    config:
      name: order-service
      profile: prod
      label: main
```

Các giá trị mặc định:

| Selector | Giá trị mặc định |
|---|---|
| Application | `${spring.application.name}`, nếu thiếu thì dùng `application` |
| Profile | Active profiles của Spring Environment; nếu không có thì `default` |
| Label | Default label do Config Server/repository quy định |

Có thể ghi đè selector bằng `spring.cloud.config.name`, `spring.cloud.config.profile` và `spring.cloud.config.label`. Tên ứng dụng không nên bắt đầu bằng tiền tố dành riêng `application-`, vì có thể gây nhầm khi Config Server phân giải property source.

Kiểm tra file trong repository có đúng quy ước, ví dụ `order-service.yml`, `order-service-prod.yml` và `application.yml`. Nếu client dùng sai application name hoặc profile, request có thể tới Config Server thành công nhưng không trả các khóa mà nhóm đang tìm.

### Một số request tới Config Server khi startup là bình thường

Với Config Data import, Spring Boot có thể gọi Config Server trước với profile `default`, sau đó gọi lại với các active profile sau khi đã xử lý cấu hình có thể kích hoạt profile. Vì vậy, log có hai hoặc nhiều request không tự động là lỗi lặp vô hạn. Đối chiếu application/profile/label trong từng request.

## 7. Nếu dùng Legacy Config First Bootstrap

Với cơ chế legacy, không dùng `spring.config.import` làm bước kích hoạt. Phải bật bootstrap trước khi Config Client đọc `bootstrap.yml`.

Có thể thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
```

Hoặc bật bằng system property/biến môi trường:

```bash
SPRING_CLOUD_BOOTSTRAP_ENABLED=true
```

Trong `bootstrap.yml`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://config.internal:8888
      name: order-service
      profile: prod
      label: main
```

Property `spring.cloud.bootstrap.enabled=true` cần có sẵn ở system property hoặc environment variable để bootstrap được kích hoạt đủ sớm. Nếu chỉ đặt nó trong `application.yml`, file đó có thể được đọc sau thời điểm bootstrap cần biết cờ này.

Trong legacy mode, `bootstrap.yml` cung cấp các thuộc tính tối thiểu để kết nối. Nếu Config Client đang chạy Config Data mode, `bootstrap.yml` không được tự đọc chỉ vì file tồn tại; cần chuyển sang legacy bootstrap một cách có chủ đích.

Không nên thêm `spring-cloud-starter-bootstrap` vào mọi dự án chỉ để khắc phục lỗi thiếu import. Hãy xác định mode hiện tại và chỉ dùng bootstrap khi cần tương thích với kiến trúc legacy.

## 8. Nếu dùng Discovery First Lookup

Discovery First cho phép client tìm Config Server qua service registry thay vì cố định URL. Trong Config Data mode, vẫn cần khai báo import:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:"
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
```

Discovery Client implementation, ví dụ Eureka hoặc Consul, phải có trên classpath và registry address phải được cấu hình. `spring.cloud.config.discovery.enabled` mặc định là `false`; service ID mặc định là `configserver`.

Nếu Config Server đăng ký bằng service ID khác, cập nhật `spring.cloud.config.discovery.service-id` cho khớp. Kiểm tra registry có instance healthy và client có thể resolve service ID đó.

Discovery First thêm một network round trip để tra cứu service registration trước khi gọi Config Server. Nếu service registry không sẵn sàng, client có thể không tìm thấy Config Server dù Config Server vẫn đang chạy. Phân biệt lỗi discovery với lỗi Config Server HTTP.

## 9. Kiểm tra Config Client có bị tắt không

`spring.cloud.config.enabled` là cờ bật/tắt remote configuration và mặc định là `true`.

```yaml
spring:
  cloud:
    config:
      enabled: true
```

Kiểm tra tất cả nguồn có thể ghi đè cờ này:

- `application.yml` và `application-<profile>.yml`.
- Biến môi trường `SPRING_CLOUD_CONFIG_ENABLED`.
- JVM system property `-Dspring.cloud.config.enabled=false`.
- Command-line option `--spring.cloud.config.enabled=false`.
- Config import/profile-specific documents và cấu hình bootstrap trong legacy mode.

Nếu cờ cuối cùng là `false`, Config Client không thực hiện remote configuration theo cấu hình đó. Đừng nhầm `health.config.enabled=false` với `spring.cloud.config.enabled=false`: cờ `health.config.enabled` chỉ tắt Config Client Health Indicator, không có nghĩa là tắt việc nạp cấu hình từ xa.

Nếu một số profile không dùng Config Server, hãy xác định rõ chiến lược:

- Tách dependency khỏi artifact/module không cần Config Client.
- Dùng import `optional:configserver:` nếu vẫn chấp nhận thử kết nối nhưng không yêu cầu server phải có.
- Dùng cấu hình disable theo môi trường nếu release đang dùng hỗ trợ đúng luồng Config Data đó; xác minh bằng log và test rằng không phát request remote.

Không để một `spring.cloud.config.enabled=false` vô tình nằm trong file chung hoặc biến môi trường của production.

## 10. Kiểm tra URL và kết nối sau khi import đã được kích hoạt

Config Client mặc định giả định Config Server ở `http://localhost:8888`. Server chỉ thực sự lắng nghe tại địa chỉ đó nếu cấu hình/triển khai đặt port tương ứng. `localhost` bên trong container là chính container đó, không phải host hay container Config Server khác.

Đối chiếu:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
```

Kiểm tra DNS và TCP từ chính môi trường chạy Config Client. Ví dụ trong container hoặc pod, `config-server` phải phân giải được tới service/host mà ứng dụng có thể truy cập.

Gọi trực tiếp endpoint Config Server để phân biệt lỗi client với lỗi server:

```bash
curl -i http://config-server:8888/order-service/prod/main
```

Nếu Config Server dùng context path hoặc gateway prefix, URL trong import phải chứa đúng prefix đó. Nếu server yêu cầu HTTP Basic, OAuth2 hoặc client TLS, Config Client phải có credential/certificate tương ứng.

Ví dụ HTTP Basic:

```yaml
spring:
  config:
    import: "configserver:https://config.internal:8888"
  cloud:
    config:
      username: ${CONFIG_SERVER_USER}
      password: ${CONFIG_SERVER_PASSWORD}
```

Không đưa password/token vào Git hoặc command line dễ bị lưu trong process listing. Dùng secret manager hoặc biến môi trường do nền tảng quản lý.

## 11. Timeout, fail-fast và retry

Nếu Config Server là nguồn bắt buộc, dùng import không có `optional:` để startup thất bại khi không lấy được cấu hình. Nếu muốn retry khi server tạm thời không sẵn sàng, bật retry theo phiên bản:

```yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Với Config Data import, bỏ `optional:` đã tạo hành vi fail nếu Config Server không thể được truy cập. `spring.cloud.config.fail-fast` vẫn được dùng trong một số cấu hình retry và legacy bootstrap. Tài liệu Spring Cloud Config 5.1 cho biết retry dùng hỗ trợ của Spring Framework, không cần Spring Retry dependency bổ sung; trước 5.1, retry tích hợp dựa trên Spring Retry. Kiểm tra đúng release train trước khi thêm dependency.

Nếu `spring.config.import` nằm trong file profile-specific, các tham số retry có thể cần truyền dưới dạng query parameter trên import URI theo tài liệu phiên bản tương ứng:

```properties
spring.config.import=configserver:https://config.internal:8888?fail-fast=true&max-attempts=10&initial-interval=1000&max-interval=5000&multiplier=1.5
```

Retry chỉ xử lý lỗi tạm thời. Nó không khắc phục URL sai, `401/403`, application name sai, label không tồn tại hoặc lỗi YAML trong repository.

## 12. Kiểm tra bằng log và Actuator

### Bật log tạm thời

Trong lúc điều tra, có thể tăng log level cho Config Client và Config Data:

```yaml
logging:
  level:
    org.springframework.cloud.config: DEBUG
    org.springframework.boot.context.config: TRACE
```

Log giúp xác nhận Config Data resolver có nhận `configserver:` import, URI nào được dùng, profile nào được yêu cầu và request kết thúc ra sao. `TRACE` có thể tạo nhiều log; chỉ bật trong thời gian ngắn, giới hạn quyền truy cập log và không ghi credential/header nhạy cảm.

### Kiểm tra `/actuator/env`

Nếu ứng dụng có Actuator và endpoint được expose/bảo vệ, kiểm tra property source `configserver:`:

```bash
curl -sS http://localhost:8080/actuator/env
```

Nếu có property source `configserver:...`, client đã nạp ít nhất một nguồn cấu hình từ xa. Nếu không có, quay lại kiểm tra dependency, import, enablement flag, log startup và request network.

`/actuator/env` có thể cho thấy Config Server đã được gọi nhưng giá trị mong muốn vẫn vắng mặt do sai application/profile/label hoặc file repository. Endpoint này phản ánh Environment của client, không chỉ response thô từ Config Server.

Theo mặc định, Actuator chỉ expose `health` qua HTTP. Muốn dùng `env`, phải expose rõ ràng và bảo vệ endpoint bằng authentication/authorization; giữ sanitization cho password, token và secret.

## 13. Ma trận chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
|---|---|---|
| Startup báo `No spring.config.import property has been defined` | Config Client có trên classpath nhưng thiếu `configserver:` import trong Config Data mode | Thêm `spring.config.import=optional:configserver:` hoặc import bắt buộc |
| Đã có `spring.cloud.config.uri` nhưng vẫn báo thiếu import | URI chỉ đặt địa chỉ, không kích hoạt Config Data import | Thêm `spring.config.import=configserver:` |
| Có `bootstrap.yml` nhưng remote config không được nạp | Legacy bootstrap chưa bật; file bootstrap không được đọc trong Config Data mode | Bật `spring.cloud.bootstrap.enabled` đúng thời điểm hoặc chuyển sang Config Data import |
| Có `spring.config.import` nhưng không có request | Thiếu starter, `spring.cloud.config.enabled=false`, import nằm sai file/profile hoặc URI không được resolve | Kiểm tra runtime dependency, effective properties và Config Data logs |
| App khởi động nhưng không thấy remote property source | Import có `optional:`, server unreachable hoặc không trả property source mong muốn | Kiểm tra log, gọi trực tiếp Config Server, kiểm tra `/actuator/env` |
| Request đi `localhost:8888` trong container | Import không có URL và dùng default localhost | Trỏ tới DNS/service name có thể truy cập từ container |
| Client gọi đúng server nhưng nhận 404 | Sai application/profile/label, context path hoặc server backend không tìm thấy resource | Kiểm tra endpoint `/{application}/{profile}/{label}` và repository |
| Nhận 401/403 | Credential/token/certificate hoặc quyền đọc Config Server sai | Kiểm tra auth và TLS; không retry vô hạn |
| Discovery First không tìm thấy Config Server | Thiếu DiscoveryClient, discovery disabled hoặc service ID sai | Bật discovery, kiểm tra registry và `service-id` |
| Local profile không cần Config Server nhưng startup vẫn gọi | Import ở file chung hoặc dependency được bật cho mọi profile | Thiết kế import theo profile hoặc disable/remove client đúng môi trường |
| Nhiều request trong startup | Config Data nạp default profile rồi nạp active profiles | Đối chiếu profile; đây có thể là hành vi bình thường |
| Remote config được nạp nhưng giá trị không như mong đợi | Application/profile/label sai hoặc local property source override | Kiểm tra `/actuator/env/{property}` và thứ tự PropertySource |
| `spring.cloud.config.enabled=false` nhưng vẫn thấy lỗi import | Cấu hình được áp dụng quá muộn hoặc hành vi phụ thuộc version/import resolver | Kiểm tra đúng release, import-check và log; đừng dựa vào cờ ở remote config |

## 14. Quy trình kiểm tra từ đầu đến cuối

Thực hiện tuần tự trên đúng artifact và đúng môi trường gặp lỗi:

1. **Xác định version:** ghi Spring Boot, Spring Cloud release train và version thực tế của `spring-cloud-config-client`.
2. **Kiểm tra dependency:** xác nhận `spring-cloud-starter-config` có trong runtime classpath.
3. **Chọn mode:** Config Data Import hay legacy Config First Bootstrap; không dựa vào file `bootstrap.yml` nếu bootstrap chưa được bật.
4. **Kiểm tra import:** xác nhận `spring.config.import` có trong local Config Data và có prefix `configserver:`; xác định optional hay required.
5. **Kiểm tra enablement:** xác nhận `spring.cloud.config.enabled` không bị đặt `false` ngoài ý muốn.
6. **Kiểm tra selectors:** xác nhận application name, active profile và label.
7. **Kiểm tra URL:** xác nhận import URI hoặc `spring.cloud.config.uri`, context path, DNS, port và TLS.
8. **Kiểm tra server độc lập:** gọi endpoint Config Server trực tiếp với application/profile/label tương ứng.
9. **Kiểm tra startup logs:** xác nhận resolver, request, response và lỗi cụ thể.
10. **Kiểm tra Environment:** nếu đã expose Actuator an toàn, xác nhận property source `configserver:` và giá trị hiệu lực.
11. **Kiểm tra nhiều replica:** đối chiếu artifact, env var, profile và import của từng pod/instance.
12. **Kiểm thử lại:** khởi động sạch với đúng cấu hình triển khai và xác nhận không còn cảnh báo/lỗi import.

## 15. Checklist cấu hình chuẩn

| Hạng mục | Điều kiện đạt |
|---|---|
| Runtime dependency | `spring-cloud-starter-config` có trên classpath chạy thật |
| BOM | Spring Cloud BOM tương thích với Spring Boot và không trộn release train |
| Config mode | Chọn Config Data Import hoặc Legacy Bootstrap rõ ràng |
| Import | `spring.config.import` có `configserver:` ở nguồn local nếu dùng Config Data |
| Optional policy | `optional:` chỉ dùng khi remote config thực sự có thể thiếu |
| Config enabled | `spring.cloud.config.enabled` không bị tắt ngoài ý muốn |
| Legacy bootstrap | Bootstrap được bật qua starter hoặc system property/env var; `bootstrap.yml` chứa URI |
| URL | Host, port, scheme, context path truy cập được từ workload |
| Application | `spring.application.name` khớp file cấu hình; tránh tiền tố `application-` |
| Profile | Active profiles đúng với cấu hình trên Config Server |
| Label | Label đúng branch/tag/commit hoặc server default |
| Authentication | Credential/token/certificate có sẵn trước khi Config Data import chạy |
| Discovery | Có DiscoveryClient và service ID đúng nếu dùng Discovery First |
| Logs | Có thể xác nhận resolver và request mà không lộ secret |
| Actuator | `/env` chỉ expose nội bộ, có phân quyền và sanitization |

## 16. Nguyên tắc cần ghi nhớ

- Với Spring Boot 2.4 trở lên, `spring.config.import=configserver:` là cách mặc định để kích hoạt Config Client.
- `spring.cloud.config.uri` chỉ cung cấp địa chỉ; nó không thay thế `spring.config.import` trong Config Data mode.
- `optional:configserver:` vẫn thực hiện import nhưng cho phép ứng dụng khởi động nếu remote Config Server không sẵn sàng.
- Không cần `bootstrap.yml` cho Config Data Import.
- Legacy Config First cần bootstrap được bật trước khi bootstrap configuration được đọc.
- `spring-cloud-starter-config` phải có trên runtime classpath và Spring Cloud BOM phải tương thích.
- `spring.cloud.config.enabled=false` tắt remote configuration; `health.config.enabled=false` chỉ tắt health indicator.
- `spring.config.import` phải có sẵn ở local Config Data; không thể chỉ khai báo trong repository mà nó cần tải.
- Config Data có thể gọi server với `default` profile rồi gọi lại với active profiles; nhiều request startup có thể là bình thường.
- Nếu Config Client đã gọi server nhưng không thấy property mong muốn, kiểm tra application/profile/label và local override thay vì tiếp tục sửa import.
- Sau khi khắc phục, xác minh property source `configserver:` trên đúng client instance và kiểm tra giá trị cuối cùng trong Environment.

Chẩn đoán lỗi thiếu `spring.config.import` bắt đầu bằng việc xác định Config Client có nằm trên runtime classpath và ứng dụng đang dùng Config Data hay legacy bootstrap. Sau đó kiểm tra import local, cờ enablement, URL và selectors. Khi phân biệt được “client chưa được kích hoạt” với “client đã gọi server nhưng không lấy được đúng dữ liệu”, quá trình xử lý sẽ ngắn hơn và tránh thay đổi sai tầng.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Config Data Import và Legacy Bootstrap](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Quick Start, dependency và client setup](https://docs.spring.io/spring-cloud-config/reference/quickstart.html)
- [Spring Boot — Externalized Configuration và Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/spring-cloud-commons.html)
