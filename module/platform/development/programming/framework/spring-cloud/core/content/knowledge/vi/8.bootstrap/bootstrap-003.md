# Vai trò của `bootstrap.yml` so với `application.yml`

Trong một ứng dụng Spring Boot có tích hợp Spring Cloud, hai tên file **`bootstrap.yml`** và **`application.yml`** gắn với hai giai đoạn cấu hình khác nhau. `application.yml` là file cấu hình chuẩn của Spring Boot. `bootstrap.yml` thuộc cơ chế bootstrap context của Spring Cloud theo cách tích hợp legacy; nó chỉ được nạp khi cơ chế bootstrap đó được bật.

Điểm này rất quan trọng khi dùng Spring Cloud Config. Từ Spring Boot 2.4, cách tích hợp Config Server mặc định được khuyến nghị là **Config Data import** qua `spring.config.import`. Với cách này, ứng dụng khai báo nguồn Config Server trong `application.yml` hoặc `application.properties`, và **không cần `bootstrap.yml`**. Cách bootstrap context cũ vẫn có thể dùng khi dự án chủ động bật nó, thường bằng `spring-cloud-starter-bootstrap` hoặc thuộc tính bootstrap được cung cấp từ system property/environment variable.

Bài học thuộc chương **Bootstrap** của module **SPRING_CLOUD_CORE**, giúp người học phân biệt file cấu hình với context khởi tạo, hiểu cách cấu hình từ xa đi vào `Environment`, cách profile và property source được xử lý, cũng như cách kiểm thử và vận hành hai mô hình.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `bootstrap.yml`, `application.yml` và bootstrap application context.
2. Giải thích vì sao `bootstrap.yml` không tự động được nạp trong mọi ứng dụng Spring Cloud.
3. Mô tả mô hình bootstrap context legacy và quan hệ cha-con với main application context.
4. Cấu hình Spring Cloud Config bằng Config Data import trong `application.yml`.
5. Bật và cấu hình legacy bootstrap khi ứng dụng thật sự cần cơ chế này.
6. So sánh vị trí và độ ưu tiên của property source trong hai cách tích hợp.
7. Phân biệt nạp cấu hình lúc khởi động với refresh cấu hình khi ứng dụng đang chạy.
8. Lập kế hoạch kiểm thử, quan sát và chuyển đổi từ bootstrap legacy sang Config Data.

## 2. Phân biệt ba khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa | Khi nào xuất hiện? |
| --- | --- | --- |
| `application.yml` | File cấu hình chuẩn được Spring Boot nạp qua Config Data | Trong quá trình chuẩn bị `Environment` của ứng dụng Boot |
| `bootstrap.yml` | File cấu hình theo quy ước của bootstrap context Spring Cloud | Khi cơ chế bootstrap legacy được bật |
| Bootstrap application context | Một `ApplicationContext` riêng, thường là context cha của main context, dùng để chuẩn bị cấu hình và tích hợp bootstrap | Trong mô hình Spring Cloud bootstrap legacy |

**Tên file không đồng nghĩa với giai đoạn khởi tạo.** Một file tên `bootstrap.yml` nằm trong `src/main/resources` không tự động tạo bootstrap context. Cần có cơ chế bootstrap được bật và dependency phù hợp.

Tương tự, một số tài liệu dùng cụm từ *bootstrap properties* để chỉ các thuộc tính được nạp trong giai đoạn bootstrap. Cụm từ đó không chỉ nói về những key nằm trong file tên `bootstrap.yml`; ví dụ, property source từ xa do Config Server trả về cũng có thể là bootstrap property source.

## 3. `application.yml`: cấu hình chính của Spring Boot

Spring Boot tìm và nạp `application.properties`, `application.yml` hoặc `application.yaml` theo các vị trí Config Data được quy định. File này có thể chứa cấu hình dùng chung, cấu hình theo profile và khai báo import nguồn khác.

Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: dev

server:
  port: 8080

clients:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 200ms
    read-timeout: 700ms
~~~

Các nhóm thuộc tính có thể được đọc qua `Environment` hoặc bind vào bean bằng `@ConfigurationProperties`. Trong ứng dụng Spring Cloud, `application.yml` thường chứa:

- Tên ứng dụng và profile.
- Cấu hình HTTP client, timeout và endpoint downstream.
- Tùy chọn discovery hoặc service registry.
- Cấu hình Actuator, logging và health.
- `spring.config.import` để nạp Config Server hoặc nguồn Config Data khác.

`application.yml` không phải file “chỉ được đọc sau khi tất cả bean đã tạo”. Spring Boot nạp Config Data trong quá trình chuẩn bị `Environment`, trước giai đoạn tạo bean thông thường. Do đó, các thuộc tính có trong file này có thể tham gia quyết định profile, cấu hình và auto-configuration của ứng dụng.

## 4. Bootstrap application context trong mô hình legacy

### 4.1. Vì sao cần một context bootstrap riêng?

Ở mô hình bootstrap legacy, Spring Cloud tạo một **bootstrap context** làm context cha của ứng dụng chính. Context này chuẩn bị các thành phần cần thiết trước khi main application context được khởi tạo, đặc biệt là các nguồn cấu hình bên ngoài.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Khởi động SpringApplication] --> B[Bật bootstrap legacy]
    B --> C[Tạo bootstrap ApplicationContext]
    C --> D[Đọc bootstrap.yml và bootstrap profile]
    D --> E[Chạy PropertySourceLocator / Config Client]
    E --> F[Nhận remote PropertySource]
    F --> G[Tạo main ApplicationContext]
    G --> H[Nạp application.yml và cấu hình cục bộ]
    H --> I[Đăng ký bean và auto-configuration]
    I --> J[Ứng dụng sẵn sàng]
~~~

Bootstrap context có thể tạo các bean cần cho giai đoạn bootstrap, ví dụ `PropertySourceLocator` hoặc các integration phục vụ nạp cấu hình. Những property source thu được sau đó được đưa vào cấu hình của ứng dụng chính theo cơ chế context hierarchy.

Mục tiêu lịch sử của mô hình này là cho phép ứng dụng lấy cấu hình từ xa trước khi khởi tạo các bean phụ thuộc vào cấu hình đó. Ví dụ, Config Server có thể cung cấp endpoint database, thông tin kết nối hoặc các thuộc tính dùng để cấu hình client.

### 4.2. Quan hệ cha-con giữa hai context

Trong mô hình legacy:

- Bootstrap context là **parent** của main application context.
- Main context là **child**.
- Các context có thể kế thừa property source và profile theo quy tắc hierarchy của Spring.
- Main context có thể có property source riêng và giá trị của child có thể ghi đè giá trị tương ứng từ parent theo quy tắc phân giải.
- Mỗi context có thể có `Environment` riêng; việc chia sẻ cùng một `Environment` trong context hierarchy không phải mặc định.

Sơ đồ:

~~~mermaid
flowchart TB
    subgraph Parent["Bootstrap ApplicationContext"]
      P1[bootstrap.yml PropertySource]
      P2[BootstrapConfiguration beans]
      P3[Remote PropertySource từ Config Server]
    end
    subgraph Child["Main ApplicationContext"]
      C1[application.yml PropertySource]
      C2[Application @Configuration]
      C3[Business beans]
    end
    Parent --> Child
    P3 -. property source được đưa vào ứng dụng .-> C3
~~~

Sơ đồ mang tính khái niệm. Cách property source được gắn vào child và thứ tự ưu tiên phụ thuộc implementation, phiên bản Spring Cloud và cấu hình override.

### 4.3. Bootstrap context không phải một service riêng

Bootstrap context là một `ApplicationContext` trong cùng tiến trình ứng dụng. Nó không phải Config Server, không phải service registry và không phải một microservice chạy độc lập.

Config Server là hệ thống bên ngoài cung cấp cấu hình qua HTTP. Bootstrap context chỉ là một cơ chế phía client để chuẩn bị `Environment` và kết nối các nguồn cấu hình trước khi ứng dụng chính khởi tạo.

## 5. `bootstrap.yml` có vai trò gì?

Khi bootstrap legacy được bật, Spring Cloud dùng quy ước `bootstrap.yml` hoặc `bootstrap.properties` cho bootstrap context. File này phù hợp để đặt những giá trị cần thiết cho quá trình bootstrap, ví dụ:

- Địa chỉ Config Server (`spring.cloud.config.uri`).
- Tên ứng dụng hoặc profile cần dùng khi bootstrap truy vấn cấu hình từ xa.
- Cấu hình nguồn bootstrap bên ngoài.
- Một số thuộc tính logging cần có hiệu lực từ giai đoạn sớm, theo hướng dẫn của phiên bản đang sử dụng.

Ví dụ `bootstrap.yml` cho Config Client legacy:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: ${SPRING_CONFIG_URI:http://localhost:8888}
      fail-fast: true
~~~

Cấu hình này chỉ có tác dụng theo mô hình bootstrap legacy khi:

1. Ứng dụng có Config Client phù hợp trên classpath.
2. Cơ chế bootstrap đã được bật.
3. `bootstrap.yml` được đặt ở vị trí bootstrap context có thể tìm thấy.
4. Config Server có thể truy cập và trả cấu hình tương ứng, nếu chính sách yêu cầu kết nối thành công.

`bootstrap.yml` không tự tải dữ liệu từ Config Server nếu chỉ có file mà không có Config Client và cơ chế bootstrap tương ứng.

### 5.1. File theo profile của bootstrap

Tương tự `application-{profile}.yml`, bootstrap context có thể nạp file profile-specific như:

~~~text
bootstrap.yml
bootstrap-dev.yml
bootstrap-prod.yml
~~~

Khi profile đã được xác định trong giai đoạn bootstrap, file tương ứng có thể cung cấp thuộc tính cho bootstrap context. Nếu cần Config Client yêu cầu bộ cấu hình theo một profile cụ thể, profile phải được thiết lập đủ sớm và đúng cơ chế của phiên bản đang dùng.

### 5.2. Đổi vị trí bootstrap file

Trong mô hình legacy, có các thuộc tính riêng:

| Thuộc tính | Vai trò |
| --- | --- |
| `spring.cloud.bootstrap.name` | Đổi tên cơ sở, mặc định là `bootstrap` |
| `spring.cloud.bootstrap.location` | Thay thế vị trí mặc định dùng để tìm bootstrap properties |
| `spring.cloud.bootstrap.additional-location` | Bổ sung vị trí bootstrap properties |

Những thuộc tính điều khiển việc tìm bootstrap file cần được cung cấp đủ sớm, thường qua system property hoặc environment variable. Chúng không phải các thuộc tính `spring.config.*` của Config Data.

## 6. Vì sao `bootstrap.yml` không còn là mặc định cho Config Server?

Spring Boot 2.4 giới thiệu **Config Data API** và Spring Cloud Config dùng cơ chế này làm cách mặc định để kết nối Config Server trong tài liệu hiện hành. Với cách này, ứng dụng khai báo `spring.config.import` trong cấu hình chính.

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Ứng dụng cần starter Config Client tương thích. Khi khởi động, Config Data loader của Config Client lấy cấu hình từ Config Server và đưa kết quả vào quá trình chuẩn bị `Environment`.

**Không cần `bootstrap.yml` cho cách Config Data import này.** Nếu một dự án hiện đại thêm `spring-cloud-starter-bootstrap` mà không có nhu cầu tương thích legacy, nó có thể vô tình bật một cơ chế khởi tạo khác và làm việc chẩn đoán phức tạp hơn.

### 6.1. `optional:` và nguồn cấu hình bắt buộc

Hai cách khai báo có ý nghĩa khác nhau:

~~~yaml
spring:
  config:
    import: optional:configserver:http://localhost:8888
~~~

Cho phép ứng dụng tiếp tục nếu Config Server không truy cập được trong quá trình import, theo cơ chế optional của Config Data.

~~~yaml
spring:
  config:
    import: configserver:http://localhost:8888
~~~

Đánh dấu Config Server là nguồn bắt buộc. Nếu không lấy được cấu hình, quá trình khởi động có thể thất bại.

Chọn chính sách theo nghiệp vụ:

- Nếu cấu hình từ xa chỉ bổ sung một số giá trị không bắt buộc, `optional:` có thể phù hợp.
- Nếu thiếu cấu hình khiến ứng dụng không thể kết nối database hoặc không thể đảm bảo an toàn, nên coi nguồn đó là bắt buộc và fail startup có kiểm soát.
- Không dùng `optional:` chỉ để che lỗi kết nối Config Server trong production.

### 6.2. Config Data có thể gọi Config Server nhiều lần

Config Data loader có thể thực hiện quá trình hai bước: trước tiên lấy cấu hình với profile `default`, sau đó xác định profile được kích hoạt và lấy thêm cấu hình cho profile tương ứng. Vì vậy, log có thể cho thấy nhiều request tới Config Server trong một lần startup. Đây là hành vi bình thường của cơ chế import, không nhất thiết là retry hoặc lỗi.

Cách xử lý này giúp cấu hình từ xa có thể tham gia kích hoạt profile. Khi kiểm tra startup, cần phân biệt request theo các giai đoạn Config Data với request retry do lỗi mạng.

## 7. So sánh `bootstrap.yml` và `application.yml`

| Tiêu chí | `bootstrap.yml` (legacy) | `application.yml` |
| --- | --- | --- |
| Chủ sở hữu cơ chế | Spring Cloud bootstrap | Spring Boot Config Data |
| Context đọc file | Bootstrap context | Main application context / Config Data processing |
| Có tự động được đọc trong mọi ứng dụng? | Không; cần bật bootstrap legacy | Là file cấu hình chuẩn được Boot tìm theo quy ước |
| Mục đích điển hình | Cấu hình cần cho bootstrap, ví dụ Config Server URI trong legacy mode | Cấu hình ứng dụng, profile và `spring.config.import` |
| Kết nối Config Server hiện đại | Không cần cho Config Data import | Khai báo `spring.config.import` |
| Dependency liên quan | Config Client và cơ chế bootstrap được bật | Config Client starter tương thích |
| Profile-specific file | `bootstrap-{profile}.yml` | `application-{profile}.yml` |
| Vòng đời | Trước main context trong bootstrap hierarchy | Config Data được xử lý khi chuẩn bị Environment chính |
| Khi nào nên dùng? | Dự án legacy hoặc yêu cầu tích hợp phụ thuộc bootstrap context | Lựa chọn mặc định cho dự án Boot/Cloud hiện đại dùng Config Data |

**Quy tắc thực hành:** Nếu dự án mới chỉ cần lấy cấu hình từ Spring Cloud Config Server, bắt đầu bằng `application.yml` với `spring.config.import`. Chỉ dùng `bootstrap.yml` khi dự án chủ động sử dụng bootstrap legacy hoặc một integration yêu cầu bootstrap context.

## 8. Cấu hình dependency cho hai mô hình

### 8.1. Config Data import

Với Maven, dependency Config Client có thể được khai báo như sau khi project đã import Spring Cloud BOM tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Không cần thêm `spring-cloud-starter-bootstrap` chỉ để dùng `spring.config.import`.

Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.cloud:spring-cloud-starter-config"
}
~~~

Phiên bản của starter nên được quản lý qua `spring-cloud-dependencies` BOM tương thích với Spring Boot; không tự ghép phiên bản Commons, Context và Config Client.

### 8.2. Bootstrap legacy

Nếu cần bật bootstrap context, có thể thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
~~~

Hoặc bật bằng thuộc tính:

~~~text
spring.cloud.bootstrap.enabled=true
~~~

Theo tài liệu Spring Cloud Config hiện hành, thuộc tính này phải được đặt như **system property hoặc environment variable** để có hiệu lực đủ sớm, ví dụ:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar orders-service.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_CLOUD_BOOTSTRAP_ENABLED = "true"
java -jar .\orders-service.jar
~~~

Cần có Config Client starter nếu mục tiêu là kết nối Config Server. `spring-cloud-starter-bootstrap` bật cơ chế bootstrap; nó không thay thế `spring-cloud-starter-config`.

**Không nên bật cả hai cơ chế chỉ để “chắc chắn cấu hình được nạp”.** Trước tiên xác định dự án đang dùng Config Data hay legacy bootstrap, sau đó giữ một mô hình có chủ đích và kiểm tra thứ tự property source.

## 9. Property source và thứ tự ưu tiên trong legacy bootstrap

Một trong những khác biệt quan trọng là cách các property source từ bootstrap context được đưa vào ứng dụng.

### 9.1. Bootstrap file và remote property source là hai nguồn khác nhau

Trong mô hình legacy:

- `bootstrap.yml` tạo property source dùng để cấu hình bootstrap context.
- Config Client có thể lấy cấu hình từ Config Server và tạo remote property source, thường được gom dưới một nguồn có tên `bootstrap`.
- Hai nguồn này không đồng nghĩa với nhau và có thể có mức ưu tiên khác nhau.

Theo tài liệu Spring Cloud Context, property source chứa dữ liệu remote từ bootstrap context thường có độ ưu tiên cao. Trong khi đó, property source đọc trực tiếp từ `bootstrap.yml` có thể có độ ưu tiên thấp hơn cấu hình `application.yml` của child context.

Vì vậy, không nên suy luận rằng **mọi key trong `bootstrap.yml` luôn ghi đè mọi key trong `application.yml`**. Hãy phân biệt nguồn cấu hình local của bootstrap file với remote property source do bootstrap phase tạo ra.

### 9.2. Cho phép local override remote property

Với legacy bootstrap, remote property source thường không cho phép local config ghi đè theo mặc định. Config Server có thể cấp quyền override bằng thuộc tính phía server:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          # Ví dụ chỉ minh họa cấu hình server override
          banner: "Managed by platform"
~~~

Ngoài ra, tài liệu Spring Cloud Context mô tả các thuộc tính kiểm soát override cho remote property source:

- `spring.cloud.config.allowOverride=true`: quyền cho phép override phải được cấp từ nguồn remote/server; đặt cục bộ không thay thế quyền này.
- `spring.cloud.config.overrideNone=true`: cho phép các nguồn cục bộ override remote.
- `spring.cloud.config.overrideSystemProperties=false`: giới hạn kiểu nguồn có thể override theo quy tắc của bootstrap.

Cần đọc đúng tài liệu release train và cấu hình phía Config Server trước khi áp dụng. Các tùy chọn này thuộc mô hình property source legacy; không sao chép nguyên xi sang Config Data import mà chưa xác minh hành vi của phiên bản đang dùng.

### 9.3. Kiểm tra thứ tự thực tế

Có thể dùng Actuator `env` trong môi trường được bảo vệ hoặc liệt kê `PropertySource` từ `ConfigurableEnvironment` để xác định:

1. Tên các nguồn đang có.
2. Thứ tự của chúng.
3. Key được cung cấp bởi nguồn nào.
4. Giá trị cuối cùng sau phân giải.
5. Giá trị remote có bị local override hay không.

Đừng chỉ nhìn file `bootstrap.yml` và kết luận giá trị runtime. Cấu hình command line, biến môi trường, Config Data và remote source có thể tham gia cùng một `Environment`.

## 10. Discovery First Lookup cho Config Server

Spring Cloud Config Client có thể tìm Config Server thông qua discovery service thay vì dùng URI cố định. Cách này được gọi là **Discovery First Lookup**.

Trong Config Data mode, ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
~~~

Ứng dụng cần discovery implementation tương thích, chẳng hạn Eureka hoặc Consul, cùng cấu hình để tìm registry. Config Server phải đăng ký với discovery service dưới service ID mà client sử dụng.

Đổi lại, client cần thêm một network round trip khi khởi động để tìm địa chỉ Config Server. Lợi ích là tọa độ Config Server có thể thay đổi mà client không cần giữ URI cố định, miễn discovery service vẫn là điểm truy cập ổn định.

Discovery First Lookup không tự có chỉ vì khai báo `spring.cloud.config.discovery.enabled=true`. Cần kiểm tra:

- Dependency discovery provider có trong runtime classpath.
- Bean `DiscoveryClient` phù hợp đã được tạo.
- Registry endpoint và credentials chính xác.
- Config Server đã đăng ký với service ID phù hợp.
- Network và timeout cho bước lookup hoạt động.
- Import Config Data hoặc bootstrap mode được cấu hình theo cách tương ứng.

Nếu dùng legacy bootstrap, các thuộc tính cần thiết để định vị discovery service phải sẵn sàng trong bootstrap phase. Nếu dùng Config Data, phải bảo đảm cấu hình đủ sớm để Config Data loader có thể định vị Config Server; cách tổ chức cụ thể phụ thuộc integration và phiên bản.

## 11. Bootstrap và refresh là hai giai đoạn khác nhau

Bootstrap giải quyết việc **chuẩn bị cấu hình trước khi ứng dụng chính khởi tạo**. Refresh giải quyết việc **cập nhật cấu hình sau khi ứng dụng đã chạy**.

| Chủ đề | Bootstrap | Refresh |
| --- | --- | --- |
| Thời điểm | Trước khi main context khởi tạo (legacy) | Sau khi ứng dụng đã chạy |
| Mục tiêu | Nạp nguồn cấu hình cần cho startup | Cập nhật Environment và bean liên quan |
| Cơ chế | Bootstrap context / Config Data import | Environment change event, refresh scope, actuator/bus tùy cấu hình |
| File liên quan | `bootstrap.yml` trong legacy hoặc `application.yml` trong Config Data | Không phụ thuộc việc file có tên bootstrap hay application |
| Tự polling Config Server? | Không phải mặc định | Config Client không tự polling mặc định |
| Tác động đến bean | Cấu hình có mặt trước khi bean được tạo | Chỉ bean có cơ chế rebind/refresh phù hợp mới nhận thay đổi |

### 11.1. `@RefreshScope`

Một bean cần được tạo lại sau refresh có thể dùng `@RefreshScope`:

~~~java
@Component
@RefreshScope
public class CatalogBanner {
    @Value("${catalog.banner:Welcome}")
    private String banner;

    public String getBanner() {
        return banner;
    }
}
~~~

Khi Environment thay đổi và refresh được kích hoạt phù hợp, proxy refresh scope có thể tạo lại target bean ở lần truy cập tiếp theo. Chỉ sửa file `bootstrap.yml` hoặc `application.yml` trên đĩa không tự làm bean đang chạy cập nhật.

### 11.2. Phát tán thay đổi đến nhiều instance

Trong hệ thống có nhiều replica, gọi refresh trên một instance không tự động cập nhật những instance còn lại. Có thể dùng Spring Cloud Bus hoặc cơ chế điều phối riêng để phát sự kiện tới các instance, sau đó quan sát trạng thái refresh của từng instance.

Không nên dùng bootstrap context để giải quyết bài toán đồng bộ cấu hình runtime. Hãy chọn cơ chế refresh và broadcast phù hợp với kiến trúc.

## 12. Chuyển từ bootstrap legacy sang Config Data

Nếu ứng dụng hiện có `bootstrap.yml`, không nên xóa file ngay. Trước tiên xác định file đang được nạp nhờ cơ chế nào.

### 12.1. Kiểm kê hiện trạng

Kiểm tra:

- Có dependency `spring-cloud-starter-bootstrap` không?
- Có `spring.cloud.bootstrap.enabled=true` được đặt ở system property/environment variable không?
- Có `spring-cloud-starter-config` không?
- `bootstrap.yml` chứa URI Config Server, application name, profile hay thuộc tính khác?
- Có `BootstrapConfiguration`, `PropertySourceLocator` hoặc custom initializer nào phụ thuộc bootstrap context không?
- Có cấu hình remote override hoặc mã dựa trên context hierarchy không?
- Có test nào khởi tạo bootstrap context theo cơ chế cũ không?

### 12.2. Chuyển phần Config Client cơ bản

Một cấu hình legacy:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal.example
      fail-fast: true
~~~

Có thể chuyển sang Config Data:

~~~yaml
# application.yml
spring:
  application:
    name: orders-service
  config:
    import: configserver:https://config.internal.example
~~~

Việc bỏ `optional:` thể hiện Config Server là bắt buộc. Nếu muốn cho phép khởi động khi server tạm thời không có, dùng `optional:configserver:...` và đánh giá rủi ro khi thiếu cấu hình.

Sau đó:

1. Giữ Config Client starter.
2. Kiểm tra profile và application name được gửi tới Config Server.
3. Xác minh giá trị nhận được trong `Environment`.
4. Kiểm thử thứ tự ưu tiên giữa remote và local property source.
5. Kiểm tra custom bootstrap code có thể thay bằng Config Data hoặc cơ chế khác không.
6. Chỉ bỏ starter bootstrap và file legacy khi không còn thành phần nào phụ thuộc nó.

### 12.3. Những khác biệt có thể làm migration thất bại

| Khác biệt | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Remote property source precedence | Giá trị local/remote có thể thắng khác trước | So sánh `env` và giá trị thực tế |
| Bootstrap custom `PropertySourceLocator` | Integration có thể không chạy trong Config Data mode | Đánh giá Config Data extension hoặc cơ chế import tương ứng |
| Profile được kích hoạt từ remote config | Số lần fetch và thời điểm nạp có thể khác | Kiểm tra log Config Data và request theo profile |
| `spring.application.name` | Config Server trả nhầm bộ cấu hình nếu tên khác | Xác minh endpoint `{application}/{profile}/{label}` |
| Fail-fast / optional | Chính sách startup thay đổi | Kiểm thử khi Config Server ngắt kết nối |
| Discovery First Lookup | Registry chưa sẵn sàng tại thời điểm import | Kiểm tra dependency và thứ tự sẵn sàng của registry |
| Bootstrap context hierarchy | Bean/initializer cũ có thể phụ thuộc parent context | Viết integration test cho context thực tế |

## 13. Kiểm thử và chẩn đoán

### 13.1. Kiểm tra file nào thực sự được nạp

Trong môi trường local, có thể bật debug khi chạy:

~~~bash
java -jar orders-service.jar --debug
~~~

Kết hợp log Config Data để xem:

- Vị trí file được xét.
- `bootstrap.yml` có được nạp hay không.
- Profile nào hoạt động.
- Config Server có được gọi hay không.
- Import có optional hay bắt buộc.
- Property source nào được thêm vào Environment.

`--debug` chủ yếu giúp xem condition evaluation report; để chẩn đoán Config Data, hãy chú ý thêm các log liên quan đến config loading. Không để mức debug quá chi tiết kéo dài trong production nếu có nguy cơ log thông tin nhạy cảm.

### 13.2. Kiểm tra bằng Actuator

Các endpoint hữu ích:

| Endpoint | Điều cần kiểm tra |
| --- | --- |
| `/actuator/env` | Property source, active profiles và giá trị đã resolve |
| `/actuator/conditions` | Auto-configuration nào match hoặc không match |
| `/actuator/beans` | Bean nào đã được đăng ký trong context |
| `/actuator/health` | Trạng thái health contributor và Config Client nếu được bật |

Chỉ expose endpoint cần thiết và bảo vệ bằng authentication/authorization cùng network policy. Không mở `/env`, `/beans` hoặc `/conditions` công khai để tiện debug.

### 13.3. Các kịch bản kiểm thử cần có

| Kịch bản | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Config Server sẵn sàng | Server trả cấu hình đúng application/profile | Environment có property từ xa |
| Config Server không sẵn sàng, import optional | Dùng `optional:configserver:` | Startup có thể tiếp tục với cấu hình còn lại |
| Config Server không sẵn sàng, import bắt buộc | Bỏ `optional:` | Startup thất bại có kiểm soát |
| Legacy bootstrap chưa bật | Có `bootstrap.yml` nhưng không có bootstrap starter/property | Không giả định file bootstrap được nạp |
| Legacy bootstrap được bật | Có Config Client và bootstrap starter | Bootstrap context được tạo và Config Client dùng bootstrap properties |
| Profile khác nhau | `dev`, `prod` | Client nhận đúng cấu hình theo profile |
| Remote và local cùng key | Khai báo override ở cả hai nguồn | Giá trị cuối cùng đúng quy tắc của mô hình đang dùng |
| Refresh sau startup | Cập nhật remote config và phát refresh event | Bean phù hợp nhận giá trị mới; các bean khác có thể giữ giá trị cũ |

### 13.4. Kiểm tra bootstrap mode trong dependency tree

Khi ứng dụng có hành vi bootstrap không mong muốn, kiểm tra dependency tree để tìm `spring-cloud-starter-bootstrap`. Sau đó tìm nơi đặt `spring.cloud.bootstrap.enabled` trong system properties, environment variables hoặc script triển khai.

Không chỉ kiểm tra `application.yml`: thuộc tính bật bootstrap phải có mặt đủ sớm. Một key đặt trong file chỉ được đọc sau khi bootstrap context lẽ ra phải được tạo không thể tự kích hoạt chính quá trình đó.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `bootstrap.yml` không có tác dụng | Bootstrap legacy chưa được bật | Kiểm tra starter bootstrap hoặc system/environment property |
| Có Config Client nhưng không gọi Config Server | Chưa có `spring.config.import` và cũng không bật legacy bootstrap | Xác định mô hình tích hợp đang dùng |
| Đã có `spring-cloud-starter-bootstrap` nhưng thiếu remote config | Thiếu Config Client, sai URI, profile hoặc kết nối | Kiểm tra dependency, bootstrap property và startup log |
| Đặt `spring.cloud.bootstrap.enabled=true` trong application.yml nhưng không chạy bootstrap | Thuộc tính được đọc quá muộn | Đưa thành system property hoặc environment variable |
| Remote config bị local override hoặc ngược lại | Khác biệt property source precedence/override | Kiểm tra `Environment` và cấu hình server |
| Startup gọi Config Server nhiều lần | Config Data lấy default profile rồi active profile | Đối chiếu log profile, không mặc định đó là retry |
| Refresh không cập nhật bean | Chỉ đổi file hoặc chưa phát refresh event | Kiểm tra Environment update, scope và cơ chế broadcast |
| Discovery First Lookup không tìm thấy Config Server | Thiếu registry provider hoặc registration | Kiểm tra `DiscoveryClient`, service ID và registry |
| Migration làm đổi giá trị cấu hình | Hai cơ chế nạp có thứ tự khác nhau | So sánh property source và viết test cho các key quan trọng |

## 15. Bài tập vận dụng

**Bài tập 1 — Phân biệt file và context.** Giải thích vì sao một file `bootstrap.yml` có trong `src/main/resources` nhưng không được đọc khi ứng dụng chạy theo Config Data import. Nêu điều kiện cần để bật bootstrap legacy.

**Bài tập 2 — Cấu hình Config Server theo hai cách.** Viết một cấu hình dùng `spring.config.import` trong `application.yml`, sau đó viết cấu hình tương đương theo legacy bootstrap với `bootstrap.yml`. Liệt kê dependency cần thiết ở mỗi cách.

**Bài tập 3 — Thứ tự ưu tiên.** Config Server trả `clients.inventory.read-timeout=900ms`, còn `application.yml` đặt `700ms`. Hãy kiểm tra giá trị cuối cùng ở cả hai mô hình và giải thích vì sao không nên mặc định cùng một kết quả.

**Bài tập 4 — Optional và fail-fast.** Thử khởi động ứng dụng khi Config Server dừng. So sánh `optional:configserver:` với `configserver:` và giải thích mô hình nào phù hợp nếu cấu hình database là bắt buộc.

**Bài tập 5 — Discovery First Lookup.** Đăng ký Config Server vào Eureka hoặc Consul. Cấu hình client tìm service ID `configserver`; quan sát số lần gọi mạng lúc startup và xử lý trường hợp registry chưa sẵn sàng.

**Bài tập 6 — Migration.** Một ứng dụng đang dùng `spring-cloud-starter-bootstrap`, `bootstrap.yml` và custom `PropertySourceLocator`. Lập kế hoạch chuyển sang Config Data, chỉ ra phần nào có thể thay bằng `spring.config.import` và phần nào cần thiết kế lại.

## 16. Ghi nhớ và nguồn tra cứu

- `application.yml` là file cấu hình chuẩn của Spring Boot, được nạp qua Config Data.
- `bootstrap.yml` thuộc quy ước của bootstrap context legacy và **không tự động được nạp trong mọi ứng dụng**.
- Bootstrap context là một `ApplicationContext` cha trong mô hình legacy; nó không phải Config Server hay service độc lập.
- Với Config Client hiện đại, `spring.config.import` là cách mặc định; không cần `bootstrap.yml`.
- Muốn dùng legacy bootstrap, cần bật bằng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` được cung cấp đủ sớm qua system property/environment variable.
- Bootstrap file local và remote property source là hai nguồn khác nhau, có thể có mức ưu tiên khác nhau.
- Bootstrap xử lý cấu hình trước startup; refresh xử lý cập nhật cấu hình khi ứng dụng đã chạy.
- Khi migration, kiểm tra dependency, profile, property source precedence, custom bootstrap code và hành vi khi Config Server không sẵn sàng.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Cloud Config Client – Spring Boot Config Data Import và Config First Bootstrap](https://docs.spring.io/spring-cloud-config/reference/client.html)
2. [Spring Cloud Context – The Bootstrap Application Context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
3. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
4. [Spring Cloud Config – Client Quickstart](https://docs.spring.io/spring-cloud-config/reference/quickstart.html)
5. [Spring Cloud – release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
