# Chuyển bootstrap cũ sang Config Data khi phù hợp

> **Chương:** Nâng cấp  
> **Module:** SPRING_CLOUD_CORE

Trong các ứng dụng Spring Cloud đời cũ, `bootstrap.yml` thường được dùng để nạp cấu hình cần thiết trước khi ApplicationContext chính khởi tạo, đặc biệt là địa chỉ Spring Cloud Config Server. Cơ chế bootstrap tạo một context cha, nạp property source từ xa rồi chuyển các property source đó sang context ứng dụng. Cách làm này vẫn có thể cần cho một số hệ thống tương thích ngược, nhưng từ Spring Cloud 2020.0, bootstrap không còn được bật mặc định.

Spring Boot 2.4 giới thiệu **Config Data API** với thuộc tính `spring.config.import`. Spring Cloud Config Client hiện dùng cơ chế này làm cách mặc định để kết nối Config Server. Thay vì cần một bootstrap context riêng, ứng dụng khai báo nguồn cấu hình cần import trong `application.yml` hoặc `application.properties`. Spring Boot điều phối việc nạp cấu hình, profile và thứ tự property source trong cùng quy trình Config Data.

Bài này hướng dẫn chuyển đổi có kiểm soát trong module **SPRING_CLOUD_CORE**: xác định khi nào nên dùng Config Data, ánh xạ cấu hình cũ sang cấu hình mới, xử lý optional/fail-fast/retry, discovery-first lookup, profile, nguồn cấu hình tùy chỉnh, kiểm thử và kế hoạch rollback. Mục tiêu là đơn giản hóa vòng đời khởi động mà vẫn giữ nguyên hành vi cấu hình mà ứng dụng cần.

## 1. Bootstrap cũ giải quyết vấn đề gì?

Trước Config Data, Spring Cloud dùng bootstrap phase để nạp các thuộc tính phải có trước khi context ứng dụng chính bắt đầu. Cơ chế thường được kích hoạt bởi `spring-cloud-starter-bootstrap` hoặc property `spring.cloud.bootstrap.enabled=true`.

Một ứng dụng dùng Spring Cloud Config theo kiểu cũ có thể có:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: https://config.internal:8888
      name: order-service
      label: main
      fail-fast: true
~~~

Username và password được cung cấp bằng biến môi trường `SPRING_CLOUD_CONFIG_USERNAME` và `SPRING_CLOUD_CONFIG_PASSWORD`, thay vì lưu trực tiếp trong file.

Bootstrap context đọc các thuộc tính này để kết nối Config Server và thêm remote property source vào Environment của ứng dụng. Các module khác cũng có thể dùng bootstrap để đăng ký `PropertySourceLocator` hoặc `ApplicationContextInitializer` tùy chỉnh.

### 1.1. Vòng đời bootstrap

~~~mermaid
flowchart TB
    A["Khởi động SpringApplication"]
    A --> B["Tạo bootstrap context"]
    B --> C["Đọc bootstrap.yml / bootstrap.properties"]
    C --> D["Kết nối Config Server hoặc nguồn tùy chỉnh"]
    D --> E["Tạo remote PropertySource"]
    E --> F["Tạo ApplicationContext chính"]
    F --> G["Kế thừa property source từ bootstrap"]
    G --> H["Tạo bean ứng dụng"]
~~~

Cách làm này hữu ích khi cần một pha cấu hình riêng trước context chính. Tuy nhiên, nó tạo thêm một context và quy tắc precedence riêng cần hiểu khi chẩn đoán. Với các ứng dụng chỉ cần import cấu hình ngoài từ Config Server, Config Data thường là lựa chọn đơn giản hơn.

### 1.2. Vì sao cần chuyển đổi?

Từ Spring Cloud 2020.0, bootstrap không còn được bật mặc định. Nếu cần duy trì hành vi cũ, có thể thêm `spring-cloud-starter-bootstrap` hoặc đặt `spring.cloud.bootstrap.enabled=true` từ environment variable, JVM system property hay command-line argument trước khi ứng dụng khởi động. Cùng thời kỳ đó, Spring Cloud bổ sung tích hợp Config Data cho Config Server, Consul, Zookeeper và Vault.

Config Data đem lại các lợi ích:

- Dùng chung cơ chế nạp cấu hình của Spring Boot.
- Khai báo nguồn cấu hình tường minh ngay trong application configuration.
- Tích hợp tự nhiên với profile và các nguồn Config Data khác.
- Không cần bootstrap context chỉ để lấy remote property source.
- Có thể dùng cú pháp import tùy chọn hoặc bắt buộc để thể hiện chính sách startup.

Chuyển đổi không có nghĩa phải xóa mọi dấu vết bootstrap trong mọi hệ thống. Trước tiên cần kiểm tra phiên bản và các extension point mà ứng dụng đang dùng.

## 2. Khi nào nên dùng Config Data, khi nào giữ bootstrap?

`spring.config.import` phù hợp khi ứng dụng dùng integration có hỗ trợ Config Data và không phụ thuộc vào các hành vi riêng của bootstrap context.

| Tình huống | Hướng xử lý |
| --- | --- |
| Spring Boot 2.4+ và Spring Cloud Config Client tương thích | Ưu tiên Config Data import |
| Dùng Config Server với cấu hình chuẩn, không có bootstrap custom | Chuyển sang `spring.config.import` |
| Dùng Consul, Zookeeper hoặc Vault có Config Data integration ở release đang dùng | Dùng scheme import do integration cung cấp |
| Spring Boot cũ hơn 2.4 | Giữ cơ chế tương thích mà phiên bản hỗ trợ hoặc nâng cấp Boot trước |
| Spring Cloud release train chưa có Config Data integration cần thiết | Giữ bootstrap tạm thời hoặc nâng cấp release train |
| Có `BootstrapConfiguration`, `PropertySourceLocator` hoặc initializer tùy chỉnh phụ thuộc bootstrap lifecycle | Đánh giá và chuyển từng extension point; giữ bootstrap trong thời gian chưa thay thế được |
| Thư viện bên thứ ba yêu cầu bootstrap context | Kiểm tra tài liệu thư viện và kiểm thử trước khi loại starter bootstrap |
| Ứng dụng cần context hierarchy hoặc property source được tạo riêng trong bootstrap | Giữ cơ chế cũ nếu chưa có thiết kế tương đương |

### 2.1. Điều kiện phiên bản

Spring Boot 2.4 là mốc giới thiệu Config Data API. Spring Cloud 2020.0 bổ sung cú pháp import cho Config Server, Consul, Zookeeper và Vault; bootstrap từ release train này không còn tự bật mặc định.

Khi nâng cấp thực tế:

1. Xác định phiên bản Spring Boot đang chạy.
2. Xác định Spring Cloud release train tương thích với Boot đó.
3. Dùng Spring Cloud BOM để quản lý phiên bản các module cùng train.
4. Kiểm tra Config Client/provider đang dùng có hỗ trợ scheme import cần thiết không.
5. Chạy ứng dụng với đúng dependency graph trước khi thay đổi file cấu hình.

Không chọn riêng phiên bản mới nhất của Config Client rồi ghép với Spring Boot tùy ý. Compatibility phụ thuộc release train và BOM. Dùng Spring Cloud compatibility verifier cùng ma trận tương thích chính thức để phát hiện tổ hợp không được hỗ trợ.

### 2.2. Trường hợp nên giữ bootstrap trong giai đoạn chuyển tiếp

Có thể giữ `spring-cloud-starter-bootstrap` khi ứng dụng còn cần một extension point được nạp trong bootstrap context, hoặc khi một thư viện tích hợp chưa hỗ trợ Config Data. Khi đó, hãy ghi lại lý do giữ bootstrap và phạm vi phụ thuộc để có thể loại bỏ sau.

Không bật cả bootstrap legacy và Config Data import một cách máy móc. Nếu cùng một remote source được nạp qua hai cơ chế, ứng dụng có thể gửi request trùng, có nhiều property source tương tự và khó dự đoán giá trị thắng. Chỉ chạy song song khi đã xác định rõ hai nguồn phục vụ hai mục đích khác nhau và đã kiểm thử precedence.

## 3. Cấu hình Config Data cho Spring Cloud Config

Với Config Data, đặt `spring.config.import` trong `application.yml` hoặc `application.properties`. Ví dụ dùng Config Server ở địa chỉ mặc định:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:
~~~

Config Client mặc định kết nối tới `http://localhost:8888` nếu không cấu hình địa chỉ khác.

Nếu Config Server nằm ở một địa chỉ cụ thể:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:https://config.internal:8888
~~~

Có thể dùng `spring.cloud.config.uri` để đặt URI riêng, nhưng nếu URI được ghi trực tiếp trong `spring.config.import` thì URI trong import có precedence cao hơn `spring.cloud.config.uri`.

Ví dụ dùng URI property:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:
  cloud:
    config:
      uri: https://config.internal:8888
~~~

Username/password nên lấy từ secret manager hoặc biến môi trường được bảo vệ. Với Spring Boot relaxed binding, có thể cung cấp `SPRING_CLOUD_CONFIG_USERNAME` và `SPRING_CLOUD_CONFIG_PASSWORD` mà không ghi credential vào file cấu hình.

Không commit credential thật vào repository. Nếu Config Server dùng OAuth, mTLS hoặc cơ chế xác thực riêng, hãy cấu hình theo hướng dẫn của Config Client và nền tảng triển khai.

### 3.1. Optional và bắt buộc

Hai dạng import thể hiện hai chính sách startup khác nhau:

~~~yaml
spring:
  config:
    import: optional:configserver:https://config.internal:8888
~~~

Có tiền tố `optional:`: ứng dụng có thể tiếp tục khởi động nếu Config Server không sẵn sàng và nguồn cấu hình được đánh dấu tùy chọn. Cách này thường hữu ích cho môi trường local hoặc ứng dụng có bộ cấu hình mặc định an toàn.

~~~yaml
spring:
  config:
    import: configserver:https://config.internal:8888
~~~

Không có `optional:`: Config Server trở thành nguồn cấu hình bắt buộc. Nếu không tải được nguồn cấu hình, ứng dụng không khởi động thành công. Đây là lựa chọn phù hợp khi thiếu remote configuration có thể khiến ứng dụng chạy sai hoặc không an toàn.

Không chọn optional chỉ để tránh lỗi startup. Nếu remote source chứa database endpoint, credential hoặc feature flag thiết yếu, chạy bằng giá trị mặc định có thể gây lỗi khó phát hiện. Ngược lại, nếu local development không cần Config Server, optional có thể giúp quy trình phát triển thuận tiện hơn.

### 3.2. Fail-fast và retry

Với Config Data, bỏ tiền tố `optional:` là cách thể hiện yêu cầu fail-fast khi không kết nối được Config Server. Nếu server có thể tạm thời chưa sẵn sàng khi ứng dụng khởi động, có thể cấu hình retry.

Config Client retry cần các dependency Spring Retry và Spring AOP phù hợp. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Ví dụ cấu hình retry:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
~~~

Các giá trị là ví dụ để minh họa chính sách retry. Chọn số lần thử và backoff theo startup budget, SLA và khả năng phục hồi của Config Server. Retry không sửa được lỗi xác thực, URI sai hoặc cấu hình server không hợp lệ; những lỗi này cần được chẩn đoán thay vì retry vô hạn.

Nếu khai báo `spring.config.import` trong file profile-specific, ví dụ `application-prod.yml`, tài liệu Config Client hướng dẫn đặt tham số retry trên URL import. Ví dụ:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&max-interval=5000&multiplier=1.5&initial-interval=1000"
~~~

Tham số query được ánh xạ sang các thuộc tính fail-fast/retry tương ứng. Khi dùng cách này, cần encode URL đúng và kiểm tra không làm lộ thông tin xác thực qua process arguments hoặc log startup.

## 4. Ánh xạ bootstrap.yml sang application.yml

Không nên chỉ đổi tên file `bootstrap.yml` thành `application.yml` rồi giữ nguyên toàn bộ nội dung. Hãy phân loại từng thuộc tính theo vai trò.

| Thuộc tính cũ | Cách xử lý khi dùng Config Data |
| --- | --- |
| `spring.application.name` | Đặt trong application config hoặc biến môi trường |
| `spring.cloud.config.uri` | Có thể giữ trong application config hoặc đặt URI trong import |
| `spring.cloud.config.name` | Giữ nếu Config Server dùng tên application khác |
| `spring.cloud.config.profile` | Giữ khi cần profile remote khác profile local |
| `spring.cloud.config.label` | Giữ để chọn branch/tag/commit của repository cấu hình |
| `spring.cloud.config.username/password` | Đưa sang secret manager hoặc biến môi trường |
| `spring.cloud.config.fail-fast` | Dùng import bắt buộc bằng cách bỏ `optional:`; kiểm tra lại retry |
| `spring.cloud.bootstrap.enabled` | Không cần bật khi chuyển hoàn toàn sang Config Data |
| `spring.cloud.config.discovery.enabled` | Có thể tiếp tục dùng nếu chọn discovery-first lookup và provider hỗ trợ |
| Custom `BootstrapConfiguration` | Phải đánh giá lại lifecycle và extension point; không tự động chuyển bằng đổi file |

Ví dụ trước chuyển đổi:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: inventory-service
  cloud:
    config:
      uri: https://config.internal:8888
      name: inventory-service
      profile: production
      label: release-2026
      fail-fast: true
~~~

Username/password được cung cấp qua biến môi trường `SPRING_CLOUD_CONFIG_USERNAME` và `SPRING_CLOUD_CONFIG_PASSWORD`.

Sau chuyển đổi:

~~~yaml
# application.yml
spring:
  application:
    name: inventory-service
  config:
    import: configserver:https://config.internal:8888
  cloud:
    config:
      name: inventory-service
      profile: production
      label: release-2026
~~~

Trong ví dụ này, import không có `optional:` nên ứng dụng yêu cầu Config Server sẵn sàng khi startup. Các thuộc tính name/profile/label vẫn giữ nguyên mục đích lựa chọn cấu hình từ xa. Hãy kiểm tra giá trị profile thực tế của ứng dụng; không cố định profile production trong file chung nếu deployment cần quyết định profile qua environment.

### 4.1. Đặt spring.application.name đủ sớm

Config Server dùng application name, profile và label để tìm cấu hình theo dạng:

~~~text
/{application}/{profile}/{label}
~~~

Mặc định application name lấy từ `spring.application.name`, profile lấy từ active profiles và label mặc định của Config Server là `master` nếu server không cấu hình default label khác. Nếu đổi tên file hoặc di chuyển property, phải bảo đảm `spring.application.name` đã có trước khi Config Data import cần nó.

Không đặt application name chỉ trong remote configuration của chính Config Server nếu client cần tên đó để tìm remote configuration. Hãy cung cấp bootstrap identity tối thiểu như application name từ local config, environment hoặc command line.

### 4.2. Đừng nhầm spring.cloud.config.profile với active profile

`spring.cloud.config.profile` chỉ định profile mà Config Client yêu cầu từ Config Server. `spring.profiles.active` điều khiển profile hoạt động của Spring Boot application. Hai thuộc tính có liên quan nhưng không đồng nghĩa.

Nếu muốn Spring Boot chạy profile production:

~~~yaml
spring:
  profiles:
    active: production
~~~

Hoặc truyền từ môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=production
~~~

Không đặt `spring.profiles.active` trong document chỉ được kích hoạt bởi chính profile đó. Spring Boot chỉ cho phép thuộc tính active/default profiles trong document không phải profile-specific.

## 5. Profile và quá trình nạp Config Data

Config Data của Spring Boot có thể nạp cấu hình theo nhiều bước. Với Config Server, client trước tiên tải cấu hình theo profile `default` để biết cấu hình từ xa có kích hoạt thêm profile nào không. Sau đó client tải cấu hình cho các profile đang hoạt động.

Vì vậy, khi dùng `spring.config.import`, có thể thấy nhiều request tới Config Server trong lúc startup. Đây là hành vi bình thường của quy trình hai bước, không nhất thiết là lỗi hoặc request bị lặp ngoài ý muốn.

### 5.1. Ví dụ cấu hình profile

Local application config:

~~~yaml
spring:
  application:
    name: inventory-service
  config:
    import: optional:configserver:
  profiles:
    active: production
~~~

Config Server có thể trả cấu hình chung và cấu hình profile-specific. Client tiếp tục tải nguồn phù hợp cho profile đã kích hoạt.

Nếu một remote property source kích hoạt profile bổ sung, Config Data có thể thực hiện request tiếp theo để lấy cấu hình cho profile đó. Đây là điểm khác biệt quan trọng so với một số hành vi bootstrap cũ vốn chỉ thực hiện một lần truy vấn.

### 5.2. Đặt import ở đâu?

Thông thường, đặt `spring.config.import` trong `application.yml` dùng chung giúp mọi profile đều biết phải import Config Server.

Nếu chỉ đặt import trong `application-prod.yml`, file đó chỉ được nạp khi profile production đã được kích hoạt từ nguồn khác. Đây là lỗi phổ biến khi người viết kỳ vọng Config Server tự kích hoạt profile nhưng import lại nằm trong file chỉ được load sau khi profile đã active.

Chỉ đặt import trong profile-specific file khi có chủ đích rõ ràng, ví dụ môi trường local không dùng Config Server nhưng production có dùng. Hãy kiểm tra profile active trước khi kiểm thử kết nối.

### 5.3. Profile-specific Config Data và precedence

Spring Boot áp dụng quy tắc precedence của Config Data và property source. File profile-specific có thể ghi đè cấu hình chung theo vị trí và thứ tự import. Khi có nhiều nguồn, hãy xác định rõ nguồn nào được ưu tiên và kiểm tra giá trị cuối cùng thay vì suy luận từ một file đơn lẻ.

Có thể dùng Actuator:

~~~text
GET /actuator/env/spring.application.name
GET /actuator/env/spring.profiles.active
GET /actuator/env/spring.cloud.config.uri
~~~

Nếu cần xác nhận bean đã nhận cấu hình đúng, kiểm tra `/actuator/configprops`. Luôn bảo vệ các endpoint này và không hiển thị secret trong response production.

## 6. Discovery-first lookup khi tìm Config Server

Mặc định client có thể kết nối trực tiếp tới URL Config Server. Nếu hạ tầng dùng Eureka hoặc Consul và muốn tìm Config Server qua DiscoveryClient, có thể bật discovery-first lookup:

~~~yaml
spring:
  config:
    import: optional:configserver:
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
~~~

Trong trường hợp này, ứng dụng cần cấu hình discovery client đủ sớm để tìm được Config Server. Với Eureka, ví dụ địa chỉ registry:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

Discovery-first lookup thêm một network round trip khi startup để tìm service registration của Config Server. Lợi ích là địa chỉ thực tế của Config Server có thể thay đổi mà client không cần biết URL cố định, miễn là Discovery Service vẫn là điểm truy cập ổn định.

Không bật discovery-first chỉ vì ứng dụng đã có Eureka. Nếu Config Server có URL ổn định và việc tìm qua registry không đem lại lợi ích vận hành, direct URL đơn giản hơn.

Nếu Config Server được bảo vệ bằng HTTP Basic hoặc có context path, provider discovery có thể cần metadata tương ứng để client biết thông tin kết nối. Không đưa password thật vào metadata công khai; dùng cơ chế secret và bảo vệ registry phù hợp.

## 7. Config Data cho các nguồn ngoài Config Server

Spring Cloud release train đã bổ sung Config Data integration cho một số nguồn ngoài khác. Ví dụ các scheme import từng được hỗ trợ trong Spring Cloud 2020.0 gồm:

| Nguồn | Scheme import minh họa |
| --- | --- |
| Spring Cloud Config Server | `configserver:` |
| Consul | `consul:` |
| Zookeeper | `zookeeper:` |
| Vault | `vault:` |

Cú pháp cụ thể, starter cần thiết và thuộc tính kết nối phụ thuộc module/provider cùng release train. Ví dụ khái quát:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal:8888,optional:consul:"
~~~

Không sao chép danh sách import trên vào ứng dụng nếu không có dependency và server tương ứng. Mỗi integration có cách xác định địa chỉ, prefix, authentication và profile riêng. Hãy dùng tài liệu của đúng module đang chạy.

Config Data cho phép phối hợp nhiều nguồn, nhưng thứ tự import ảnh hưởng precedence. Khi có hai nguồn cùng khai báo một key, cần xác định rõ nguồn nào được ưu tiên và kiểm tra giá trị cuối cùng trong Environment.

## 8. Retry và nhiều Config Server URL

Có thể khai báo nhiều location trong `spring.config.import`. Các location được xử lý theo thứ tự; các import phía sau có thể có precedence cao hơn. Hành vi khi một URL lỗi còn phụ thuộc fail-fast và cấu hình multiple URI của phiên bản Config Client.

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config-a.internal:8888,optional:configserver:https://config-b.internal:8888"
~~~

Đừng coi danh sách nhiều URL là load balancing tự động. Hãy xác nhận semantics fallback của phiên bản đang dùng, nhất là khi server trả HTTP 401, 500 hoặc lỗi cấu hình thay vì lỗi kết nối.

### 8.1. Retry khi import nằm trong profile-specific file

Nếu import nằm trong `application-prod.yml`, tài liệu Config Client yêu cầu đưa tham số retry vào URL import. Ví dụ:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&max-interval=5000&multiplier=1.5&initial-interval=1000"
~~~

Tham số query được ánh xạ sang các thuộc tính fail-fast/retry tương ứng. Khi dùng cách này, cần encode URL đúng và kiểm tra không làm lộ thông tin xác thực qua process arguments hoặc log startup.

## 9. Xử lý custom bootstrap extension

Đây là phần cần thận trọng nhất khi nâng cấp một hệ thống đã tùy biến sâu.

Bootstrap cũ cho phép đăng ký các class qua `BootstrapConfiguration` trong `spring.factories`. Một trong các extension point phổ biến là `PropertySourceLocator`, dùng để lấy property source từ một hệ thống riêng. Các bean `ApplicationContextInitializer` cũng có thể được đăng ký để tác động vào startup sequence.

### 9.1. Không chỉ đổi tên file

Nếu ứng dụng có custom `PropertySourceLocator`, việc chuyển `bootstrap.yml` thành `application.yml` và thêm `spring.config.import` không tự động chuyển locator đó sang Config Data. Locator phụ thuộc lifecycle và context nơi nó được tạo.

Trước khi chuyển, hãy xác định:

- Locator có cần chạy trước khi profile được xác định không?
- Nó có phụ thuộc bean chỉ tồn tại trong bootstrap context không?
- Nó có cần property source precedence đặc biệt không?
- Nó có được đăng ký qua `spring.factories` không?
- Nó có dùng context hierarchy hoặc initializer riêng không?
- Có integration Config Data chính thức thay thế không?

### 9.2. Chọn chiến lược thay thế

Nếu nguồn cấu hình tùy chỉnh cần tham gia trực tiếp quy trình Config Data, hãy xem xét triển khai extension phù hợp với Config Data như `ConfigDataLocationResolver` và `ConfigDataLoader` theo API của Spring Boot mà ứng dụng hỗ trợ. Nếu nguồn đã có integration chính thức, ưu tiên dùng integration đó.

Nếu chưa thể thay thế an toàn, có thể giữ bootstrap legacy trong giai đoạn chuyển tiếp. Ghi rõ module, extension point và lý do giữ lại; không loại `spring-cloud-starter-bootstrap` cho tới khi test xác nhận nguồn cấu hình tùy chỉnh vẫn hoạt động.

### 9.3. Kiểm tra property source precedence

Bootstrap context cũ có thể tạo remote property source với precedence khác với Config Data import. Sau chuyển đổi, cùng một property có thể nhận giá trị từ nguồn khác nếu thứ tự import hoặc file profile-specific thay đổi.

Lập bảng các property quan trọng trước và sau chuyển đổi:

| Property | Nguồn cũ | Giá trị cũ | Nguồn mới | Giá trị mới |
| --- | --- | --- | --- | --- |
| `spring.datasource.url` | Config Server | URL production | Config Server import | Phải giống |
| `catalog.client.timeout` | bootstrap remote source | 2s | Config Data remote source | Phải giống |
| `logging.level.root` | application.yml | INFO | application.yml | Phải giữ theo policy |
| `feature.catalog.enabled` | profile-specific source | true | profile-specific Config Data | Phải giống |

Không chỉ so sánh nội dung YAML. So sánh Environment sau startup vì đó là kết quả của mọi property source, profile và override.

## 10. Quy trình migration từng bước

Một đợt migration an toàn nên thực hiện theo từng thay đổi nhỏ và có thể rollback.

1. **Chụp baseline:** ghi nhận Spring Boot version, Spring Cloud release train, dependency graph, active profiles và các property source hiện tại.
2. **Kiểm kê bootstrap:** liệt kê toàn bộ key trong `bootstrap.yml`, biến môi trường và JVM argument liên quan.
3. **Tìm extension point:** tìm `BootstrapConfiguration`, `PropertySourceLocator`, `ApplicationContextInitializer` và starter bootstrap trong dependency tree.
4. **Xác nhận hỗ trợ:** kiểm tra phiên bản Config Client/provider có Config Data integration.
5. **Chuyển cấu hình tối thiểu:** đưa `spring.application.name`, Config Server location, name/profile/label và authentication reference sang application config.
6. **Thêm import:** dùng `spring.config.import` với optional hoặc required theo chính sách startup.
7. **Chuyển retry:** kiểm tra dependency Spring Retry/AOP và cách khai báo retry khi import ở profile-specific file.
8. **Chuyển discovery lookup:** chỉ bật nếu Config Server thực sự được tìm qua DiscoveryClient.
9. **Xử lý custom source:** thay extension point hoặc giữ bootstrap nếu chưa có phương án tương đương.
10. **Chạy local:** kiểm tra cả khi Config Server sẵn sàng và khi server bị tắt.
11. **So sánh Environment:** dùng `env` và `configprops` để xác nhận property source và bean binding.
12. **Kiểm thử profile:** chạy default, dev, staging, production và profile được kích hoạt từ remote config.
13. **Triển khai canary:** chuyển một service hoặc một nhóm instance trước, theo dõi lỗi startup và cấu hình thực tế.
14. **Loại bootstrap starter:** chỉ xóa dependency và file cũ sau khi toàn bộ consumer đã dùng Config Data.
15. **Theo dõi sau chuyển đổi:** kiểm tra số request Config Server, thời gian startup, retry, authentication và refresh behavior.

## 11. Kiểm thử sau migration

Không chỉ kiểm tra ứng dụng khởi động được. Hãy xác nhận các hành vi cấu hình quan trọng.

### 11.1. Ma trận kiểm thử

| Trường hợp | Kết quả cần xác nhận |
| --- | --- |
| Config Server hoạt động | Ứng dụng tải đúng remote property source |
| Config Server không sẵn sàng, import optional | Ứng dụng khởi động theo fallback được thiết kế |
| Config Server không sẵn sàng, import required | Startup thất bại rõ ràng |
| Credential sai | Lỗi xác thực được phát hiện; không che giấu bằng fallback ngoài ý muốn |
| Profile mặc định | Cấu hình chung được tải |
| Profile production | Cấu hình profile-specific được tải và ghi đè đúng |
| Remote config kích hoạt profile | Client tải thêm cấu hình cho profile được kích hoạt |
| Config Server discovery-first | Client tìm đúng service ID và URL/context path |
| Custom property source | Giá trị và precedence không thay đổi ngoài dự kiến |
| Retry | Số lần thử/backoff nằm trong startup budget |
| Config label thay đổi | Đúng branch/tag/commit được sử dụng |

### 11.2. Kiểm tra giá trị qua Actuator

Trong môi trường kiểm thử được bảo vệ, có thể truy vấn:

~~~text
GET /actuator/env/spring.application.name
GET /actuator/env/spring.profiles.active
GET /actuator/env/spring.cloud.config.uri
~~~

`env` cho biết property source nào đang cung cấp giá trị hiệu lực và origin nếu có. `configprops` cho biết bean `@ConfigurationProperties` đã bind giá trị ra sao. Hai endpoint giúp phát hiện trường hợp remote config đã tải nhưng bean không nhận giá trị như mong đợi.

Không expose các endpoint này công khai và không bật hiển thị secret trong production chỉ để so sánh cấu hình.

### 11.3. Kiểm tra số request startup

Config Data có thể tạo nhiều request Config Server do bước tải profile `default` và bước tải profile active. Đây là hành vi bình thường. Khi quan sát log, đừng kết luận ngay có vòng lặp hoặc retry storm chỉ vì thấy nhiều request.

Hãy phân biệt:

- Request theo giai đoạn profile discovery.
- Retry do Config Server tạm thời không sẵn sàng.
- Nhiều URL fallback.
- Request trùng do ứng dụng đồng thời bật bootstrap legacy và Config Data import.

## 12. Lỗi thường gặp và cách tránh

1. **Chỉ đổi tên bootstrap.yml thành application.yml:** cần chuyển sang `spring.config.import` và kiểm tra lifecycle.
2. **Quên bỏ spring-cloud-starter-bootstrap:** bootstrap legacy có thể vẫn được bật dù đã thêm Config Data.
3. **Dùng optional trong production mà không có fallback an toàn:** ứng dụng có thể chạy với cấu hình mặc định thiếu hoặc sai.
4. **Không dùng optional ở môi trường local cần chạy độc lập:** startup có thể thất bại khi Config Server không chạy.
5. **Đặt import trong application-prod.yml nhưng profile chưa active:** Config Data import không được nạp đúng lúc.
6. **Nhầm spring.cloud.config.profile với spring.profiles.active:** hai thuộc tính có vai trò khác nhau.
7. **Quên spring.application.name:** Config Server tìm sai application configuration.
8. **Cho rằng Config Data chỉ tạo một request:** quy trình profile có thể cần nhiều lần tải.
9. **Giữ cả bootstrap và Config Data cùng một remote source:** tăng độ phức tạp và khó đoán precedence.
10. **Không chuyển custom PropertySourceLocator:** nguồn cấu hình tùy chỉnh có thể biến mất hoặc chạy ở lifecycle khác.
11. **Retry quá nhiều:** kéo dài startup và có thể tăng tải Config Server khi outage.
12. **Dùng nhiều URL mà không hiểu fallback:** lỗi xác thực hoặc lỗi cấu hình không nhất thiết được xử lý như lỗi kết nối.
13. **Đưa credential vào URL/file cấu hình:** có nguy cơ lộ qua repository, process list hoặc log.
14. **Nâng Spring Boot mà không đồng bộ Spring Cloud BOM:** có thể gặp compatibility verifier failure hoặc lỗi runtime.
15. **Xóa bootstrap starter quá sớm:** một integration khác vẫn có thể cần bootstrap context.

## 13. Checklist hoàn tất chuyển đổi

Trước khi kết thúc migration, xác nhận:

- [ ] Spring Boot và Spring Cloud release train nằm trong ma trận tương thích.
- [ ] Config Client/provider có Config Data integration cần thiết.
- [ ] `spring.config.import` nằm ở file được nạp trong giai đoạn phù hợp.
- [ ] Chính sách optional/required đúng với từng môi trường.
- [ ] `spring.application.name`, profile, config name và label đúng.
- [ ] Credential lấy từ secret source an toàn.
- [ ] Retry và timeout nằm trong startup budget.
- [ ] Discovery-first lookup chỉ bật khi thực sự cần.
- [ ] Custom bootstrap extension đã được thay thế hoặc có lý do giữ lại.
- [ ] Property precedence trước/sau đã được so sánh.
- [ ] Các profile và remote profile activation đã được kiểm thử.
- [ ] Config Server outage và authentication failure đã được kiểm thử.
- [ ] Actuator env/configprops được bảo vệ.
- [ ] Không còn remote source bị nạp trùng ngoài ý muốn.
- [ ] Có kế hoạch rollback và đã thử trên canary.
- [ ] Chỉ gỡ bootstrap starter sau khi mọi integration đã được xác nhận.

**Điểm cần ghi nhớ:** Config Data với `spring.config.import` là cách chuẩn hiện nay để nạp cấu hình từ Config Server và các integration Spring Cloud hỗ trợ. Migration cần giữ đúng chính sách optional/fail-fast, profile, property precedence và retry; custom bootstrap extension phải được đánh giá riêng. Chỉ loại bootstrap legacy khi ứng dụng không còn phụ thuộc bootstrap lifecycle và các kiểm thử xác nhận hành vi cấu hình trước/sau tương đương trong **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Spring Boot Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration and Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud 2020.0 Release Notes — Bootstrap and Config Data Changes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2020.0-Release-Notes)
- [Spring Cloud Commons — Application Context Services and Bootstrap Property Sources](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
