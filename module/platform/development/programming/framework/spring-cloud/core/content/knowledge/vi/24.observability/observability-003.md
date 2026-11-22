# Quan sát thành phần trong context bằng beans

Khi một ứng dụng Spring Boot hoặc Spring Cloud khởi động, Spring tạo một hoặc nhiều `ApplicationContext` và đăng ký bean từ component scanning, Java configuration, auto-configuration và các integration được bật. Khi ứng dụng không hoạt động như dự kiến, việc xác định bean nào thực sự có mặt, thuộc context nào và phụ thuộc vào bean nào thường là bước điều tra đầu tiên.

Spring Boot Actuator cung cấp endpoint **`beans`** để xem danh sách bean trong các application context. Endpoint cho biết tên bean, alias, scope, kiểu, resource khai báo và dependency mà container ghi nhận. Nó giúp kiểm tra kết quả cuối cùng của quá trình cấu hình, đặc biệt khi nhiều module Spring Cloud cùng đóng góp bean vào một ứng dụng.

Bài học thuộc chương **Quan sát** của module `SPRING_CLOUD_CORE`. Nội dung tập trung vào cách bật và đọc endpoint `/actuator/beans`, hiểu cấu trúc dữ liệu context và bean descriptor, sử dụng thông tin đó để chẩn đoán component scanning/auto-configuration, bảo vệ endpoint quản trị và phân biệt `beans` với các endpoint Actuator khác.

## 1. Bean và ApplicationContext trong ứng dụng Spring Cloud

Bean là object do Spring IoC container khởi tạo, cấu hình và quản lý lifecycle. Một bean có thể được khai báo bằng:

- `@Component`, `@Service`, `@Repository` hoặc `@Controller`.
- Method `@Bean` trong một class `@Configuration`.
- Spring Boot auto-configuration.
- Integration do Spring Cloud hoặc thư viện khác cung cấp.
- Đăng ký programmatically thông qua API của container.

`ApplicationContext` là container chứa bean definition và quản lý bean của một phạm vi ứng dụng. Ứng dụng Spring Cloud có thể có nhiều bean đến từ nhiều starter: discovery client, load balancer, Config Client, refresh infrastructure, actuator endpoint, HTTP client và service nghiệp vụ.

Ví dụ một service nghiệp vụ:

```java
@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    public CatalogItem findById(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Catalog item not found"));
    }
}
```

Khi context khởi tạo, Spring đăng ký bean `catalogService` và liên kết dependency `catalogRepository`. Endpoint `beans` cho phép quan sát những thông tin container đang quản lý về hai bean này.

## 2. Endpoint beans của Spring Boot Actuator

Endpoint `beans` thuộc Spring Boot Actuator, có endpoint ID là `beans` và đường dẫn HTTP mặc định là:

```text
GET /actuator/beans
```

Để sử dụng endpoint, thêm Actuator starter vào ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Sau đó expose endpoint qua HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans
```

Mặc định, Actuator chỉ expose một tập endpoint HTTP nhỏ, thường có `health`. Việc endpoint có trong classpath không đồng nghĩa endpoint đã được expose qua HTTP. Cần phân biệt:

- **Có endpoint:** Actuator có implementation tương ứng trên runtime classpath.
- **Endpoint được bật/access:** chính sách endpoint cho phép sử dụng thao tác đó theo phiên bản Spring Boot.
- **Endpoint được expose:** endpoint được đưa ra qua HTTP hoặc JMX.
- **Có quyền truy cập:** network và security cho phép người gọi thực hiện request.

Nếu ứng dụng đã có cấu hình `management.endpoints.web.exposure.include`, hãy thêm `beans` vào danh sách hiện tại. Không ghi đè danh sách endpoint đang dùng mà chưa kiểm tra các endpoint cần thiết khác.

### 2.1. Gọi endpoint

Khi management server dùng cùng port với ứng dụng và base path mặc định:

```bash
curl http://localhost:8080/actuator/beans
```

Có thể thay base path:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,beans
```

Khi đó URL sẽ là `/manage/beans`.

Nếu management endpoint chạy trên port riêng:

```yaml
management:
  server:
    port: 9001
```

Request sẽ đi tới management port, ví dụ `http://localhost:9001/actuator/beans`. Cổng này cần được giới hạn trong mạng quản trị phù hợp.

### 2.2. Expose qua JMX

Nếu môi trường vận hành dùng JMX thay vì HTTP, có thể cấu hình exposure riêng:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: beans
```

HTTP exposure và JMX exposure là hai cơ chế khác nhau. Chỉ expose qua phương thức quản trị mà tổ chức thực sự sử dụng.

## 3. Cấu trúc dữ liệu trả về

Endpoint `beans` trả về thông tin được nhóm theo application context. Mỗi context có định danh, thông tin parent nếu có và map các bean thuộc context đó.

Ví dụ rút gọn:

```json
{
  "contexts": {
    "application": {
      "parentId": null,
      "beans": {
        "catalogService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.catalog.CatalogService",
          "resource": "class path resource [com/example/catalog/CatalogService.class]",
          "dependencies": [
            "catalogRepository"
          ]
        },
        "catalogRepository": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.catalog.CatalogRepository",
          "resource": "class path resource [com/example/catalog/CatalogRepository.class]",
          "dependencies": []
        }
      }
    }
  }
}
```

Đây là ví dụ minh họa cấu trúc, không phải output cố định của mọi ứng dụng. Bean name, resource và danh sách dependency phụ thuộc cách bean được đăng ký.

Các trường quan trọng:

| Trường | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `contexts` | Map các application context | Xác định bean thuộc context nào |
| `parentId` | ID của parent context nếu có | Hiểu quan hệ context cha/con |
| `beans` | Map bean theo bean name | Tìm bean cụ thể |
| `aliases` | Các alias của bean | Nhận biết nhiều tên cùng trỏ tới một bean |
| `scope` | Scope của bean | Phân biệt singleton, prototype, request hoặc scope khác |
| `type` | Kiểu bean được container mô tả | Kiểm tra implementation thực tế |
| `resource` | Nguồn/resource liên quan tới bean definition nếu có | Tìm nơi bean được khai báo |
| `dependencies` | Các bean dependency mà container ghi nhận | Quan sát quan hệ phụ thuộc trực tiếp |

### 3.1. Bean name và alias

Bean name là định danh được dùng trong container. Với component, tên mặc định thường được suy ra từ tên class theo quy tắc component naming; với method `@Bean`, tên mặc định thường là tên method.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return new HttpCatalogGateway();
    }
}
```

Tên bean mặc định là `catalogGateway`. Nếu khai báo tên hoặc alias:

```java
@Bean(name = {"catalogGateway", "primaryCatalogGateway"})
CatalogGateway catalogGateway() {
    return new HttpCatalogGateway();
}
```

Endpoint có thể thể hiện bean name và alias. Alias là tên bổ sung cho cùng bean, không có nghĩa Spring đã tạo thêm một object độc lập.

### 3.2. Scope

Scope cho biết vòng đời và phạm vi bean. Các giá trị thường gặp gồm:

- `singleton`: một instance cho mỗi bean definition trong một container.
- `prototype`: container tạo instance mới mỗi khi yêu cầu bean theo cơ chế tương ứng.
- `request`: một instance trong phạm vi HTTP request khi web scope được kích hoạt.
- `session`: một instance trong phạm vi HTTP session.
- Custom scope do ứng dụng hoặc framework đăng ký.

Đừng kết luận một ứng dụng chỉ có một object trên toàn JVM chỉ vì scope là singleton. Singleton của Spring được quản lý theo container/bean definition; nhiều application context có thể có bean singleton cùng tên nhưng là các instance khác nhau.

### 3.3. Type và resource

`type` giúp xác định class/implementation mà container nhìn thấy. Điều này hữu ích khi một interface có nhiều implementation và ứng dụng vô tình chọn implementation khác dự kiến.

`resource` cung cấp thông tin về resource liên quan tới bean definition nếu có, ví dụ classpath resource hoặc nguồn khai báo. Với bean được tạo programmatically hoặc từ factory, resource có thể không mô tả trực tiếp vị trí Java method như người đọc mong đợi.

Không nên dựa vào chuỗi resource như một API ổn định để parse tự động. Nó chủ yếu phục vụ chẩn đoán.

### 3.4. Dependencies

`dependencies` thể hiện các bean mà container ghi nhận là dependency của bean đang xem. Ví dụ `catalogService` phụ thuộc `catalogRepository`.

Danh sách này hữu ích để hiểu wiring ở mức container, nhưng không phải call graph đầy đủ. Nó không cho biết mọi method mà bean gọi trong runtime, mọi object tự tạo bằng `new` hoặc toàn bộ dependency ẩn bên trong thư viện.

## 4. Quan sát context hierarchy

Một ứng dụng có thể có context cha và context con. Ví dụ, ứng dụng Spring MVC có thể tách root context và servlet context; Spring Boot cũng có thể tạo management context riêng trong một số cấu hình.

Endpoint `beans` nhóm dữ liệu theo từng context. Ví dụ minh họa:

```json
{
  "contexts": {
    "application": {
      "parentId": null,
      "beans": {
        "catalogService": {
          "scope": "singleton",
          "type": "com.example.catalog.CatalogService",
          "dependencies": ["catalogRepository"]
        }
      }
    },
    "management": {
      "parentId": "application",
      "beans": {
        "healthEndpoint": {
          "scope": "singleton",
          "type": "org.springframework.boot.actuate.health.HealthEndpoint",
          "dependencies": []
        }
      }
    }
  }
}
```

Tên context trong ví dụ chỉ mang tính minh họa. Hãy đọc ID thực tế từ response.

### 4.1. Vì sao phải quan sát đúng context?

Bean có thể nằm trong parent context nhưng được truy cập từ child context theo cơ chế tra cứu bean của Spring. Vì vậy, khi tìm bean:

1. Xác định context nào đang chứa bean definition.
2. Kiểm tra quan hệ parent-child.
3. Kiểm tra bean có cùng tên ở nhiều context hay không.
4. Không xem hai bean cùng tên ở hai context là một object duy nhất.

Điều này đặc biệt quan trọng khi ứng dụng có nhiều servlet context, management context hoặc test context hierarchy.

### 4.2. Phân biệt bean trùng tên và alias

Nếu một bean có hai alias, endpoint có thể hiển thị alias trong descriptor của bean đó. Nếu cùng một tên xuất hiện trong hai context khác nhau, đó là hai phạm vi container khác nhau. Cần kiểm tra context ID trước khi kết luận có bean bị đăng ký trùng.

## 5. Dùng beans để chẩn đoán auto-configuration

Spring Boot auto-configuration có thể tạo nhiều bean dựa trên classpath, property và các bean đã tồn tại. Endpoint `beans` cho biết kết quả cuối cùng: bean nào thực sự có trong context.

Ví dụ muốn xác minh một HTTP client load-balanced:

```java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate() {
        return new RestTemplate();
    }
}
```

Sau khi ứng dụng khởi động, tìm bean `catalogRestTemplate` trong response và kiểm tra type/scope. Nếu bean không có, cần xem tiếp:

- Configuration class có được import hoặc component scan không?
- Condition của configuration có khớp không?
- Có dependency cần thiết trong runtime classpath không?
- Có lỗi khởi tạo khiến context không khởi động hoàn chỉnh không?
- Bean được tạo trong context khác hay không?

Endpoint `beans` chỉ cho biết bean hiện diện hay không; nó không giải thích đầy đủ vì sao một auto-configuration bị bỏ qua. Dùng endpoint `conditions` hoặc condition evaluation report để điều tra điều kiện match/unmatch.

### 5.1. Phát hiện implementation không mong đợi

Giả sử ứng dụng mong muốn dùng implementation `StubCatalogGateway` qua interface `CatalogGateway`, nhưng response cho thấy bean được tạo là `StubCatalogGateway` trong khi môi trường dự kiến dùng HTTP gateway. Điều đó có thể do:

- Profile test vẫn đang bật.
- Property feature flag đang chọn stub.
- Một cấu hình test được import vào runtime.
- Một configuration có condition ưu tiên khác đã đăng ký bean.

Kiểm tra `type` và `resource` để tìm nguồn bean, sau đó đối chiếu với property/profile và condition report.

### 5.2. Phát hiện nhiều bean cùng interface

Một interface có thể có nhiều implementation cùng tồn tại. Endpoint `beans` giúp liệt kê bean name và type để xác định số lượng implementation.

Nếu injection bị lỗi do nhiều candidate, cần xem code sử dụng `@Qualifier`, `@Primary` hoặc điều kiện auto-configuration. `@Primary` chỉ ảnh hưởng lựa chọn candidate khi inject; nó không xóa các bean khác khỏi context.

## 6. Đọc và lọc kết quả

Trong ứng dụng lớn, response `/actuator/beans` có thể khá dài. Có thể lưu output phục vụ điều tra:

```bash
curl -s http://localhost:8080/actuator/beans > beans.json
```

Dùng `jq` để xem context ID:

```bash
jq '.contexts | keys' beans.json
```

Tìm bean theo tên:

```bash
jq '.contexts[].beans.catalogService' beans.json
```

Liệt kê bean name và type trong các context:

```bash
jq -r '.contexts | to_entries[] as $context
  | $context.value.beans | to_entries[]
  | [$context.key, .key, .value.type] | @tsv' beans.json
```

Lệnh lọc chỉ hỗ trợ phân tích dữ liệu đã nhận; nó không thay đổi Spring context. Nếu tên bean có ký tự đặc biệt, dùng cú pháp truy cập map an toàn của JSON query tool thay vì giả định mọi bean name là identifier hợp lệ.

Không nên lưu response chứa thông tin nội bộ vào nơi công khai hoặc đính kèm vào issue bên ngoài mà chưa rà soát.

## 7. Phân biệt beans với các endpoint Actuator khác

Endpoint `beans` thường được dùng cùng các endpoint chẩn đoán khác, nhưng mỗi endpoint trả lời một câu hỏi riêng:

| Endpoint | Trả lời câu hỏi | Dùng khi |
| --- | --- | --- |
| `/actuator/beans` | Bean nào tồn tại trong context và chúng được mô tả ra sao? | Kiểm tra bean name, type, scope, dependencies và context |
| `/actuator/conditions` | Vì sao một auto-configuration/condition match hoặc không match? | Điều tra bean không được tạo do condition |
| `/actuator/configprops` | Các `@ConfigurationProperties` nào đã được bind? | Kiểm tra cấu hình đã bind vào properties object |
| `/actuator/env` | Property source và giá trị Environment là gì? | Điều tra precedence và nguồn cấu hình |
| `/actuator/mappings` | HTTP handler mapping nào được đăng ký? | Kiểm tra controller và endpoint HTTP |
| `/actuator/health` | Các health indicator báo trạng thái gì? | Kiểm tra tình trạng hệ thống và dependency |
| `/actuator/metrics` | Những metric nào được công bố? | Theo dõi số liệu vận hành |

Ví dụ:

- Bean không xuất hiện: kiểm tra `beans`, sau đó `conditions`.
- Bean xuất hiện nhưng có giá trị cấu hình sai: kiểm tra `configprops` và `env`.
- Controller tồn tại nhưng route không hoạt động: kiểm tra `mappings`.
- Bean kết nối Redis nhưng Redis không sẵn sàng: kiểm tra `health` và log kết nối.

Dùng đúng endpoint sẽ giảm thời gian điều tra và tránh suy luận từ một loại dữ liệu không trả lời câu hỏi cần tìm.

## 8. Quan sát các thành phần Spring Cloud

Trong ứng dụng Spring Cloud, endpoint `beans` có thể giúp kiểm tra những nhóm thành phần như:

| Nhóm | Ví dụ loại bean cần tìm | Ý nghĩa chẩn đoán |
| --- | --- | --- |
| Discovery | DiscoveryClient implementation | Xác nhận provider discovery được tạo |
| Service registration | ServiceRegistry/Registration integration | Xác định integration quản lý đăng ký |
| Load balancing | LoadBalancerClient, supplier hoặc client integration | Kiểm tra các bean load balancing có mặt |
| Configuration | Config Client và property-related infrastructure | Kiểm tra thành phần nạp cấu hình |
| Refresh | Refresh-related scope/endpoint infrastructure | Kiểm tra các bean phục vụ refresh |
| Circuit breaker | Factory/implementation integration | Xác định circuit breaker integration đã được nạp |
| Actuator | Endpoint và health contributor | Kiểm tra các thành phần quản trị |

Tên class và bean name cụ thể thay đổi theo release train, starter và provider. Không nên viết script phụ thuộc cứng vào một tên bean nội bộ nếu có thể kiểm tra theo interface hoặc hành vi được hỗ trợ.

### 8.1. Kiểm tra DiscoveryClient

Nếu ứng dụng mong đợi Eureka hoặc Consul nhưng không thấy implementation tương ứng, kiểm tra:

- Starter discovery có trong runtime classpath không?
- Auto-configuration có bị loại trừ không?
- Property có tắt discovery không?
- Bean có nằm trong context khác không?

Sau đó dùng `conditions` và log startup để tìm nguyên nhân. Việc thấy DiscoveryClient bean không chứng minh registry đang reachable hoặc trả instance hợp lệ; kiểm tra health, log và lời gọi discovery thực tế.

### 8.2. Kiểm tra LoadBalancer

Nếu client gọi URL service ID nhưng bị `UnknownHostException`, endpoint `beans` có thể giúp xác minh bean HTTP client được tích hợp load balancing và các thành phần LoadBalancer có được tạo không.

Tuy nhiên, response bean không chứng minh request interceptor/filter đã xử lý một URL cụ thể. Cần integration test hoặc trace/log của request để xác minh hành vi thực tế.

### 8.3. Kiểm tra Refresh infrastructure

Nếu ứng dụng cần refresh scope, có thể tìm các bean infrastructure liên quan trong context. Nhưng sự hiện diện của bean refresh infrastructure không chứng minh mọi bean cấu hình đã được đánh dấu đúng scope hoặc property đã refresh thành công. Kiểm tra thêm scope của bean mục tiêu, refresh endpoint, log và giá trị cấu hình sau refresh.

## 9. Bảo vệ endpoint beans

Response của `beans` có thể tiết lộ:

- Tên class và package nội bộ.
- Bean name phản ánh cấu trúc nghiệp vụ.
- Quan hệ phụ thuộc giữa các thành phần.
- Resource path hoặc vị trí khai báo.
- Các integration và thư viện đang được nạp.

Đây là dữ liệu hữu ích cho vận hành nhưng cũng là thông tin kiến trúc. Không nên expose endpoint rộng rãi ra Internet.

### 9.1. Chỉ expose endpoint cần thiết

Chỉ thêm `beans` vào exposure list nếu có nhu cầu vận hành:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans
```

Tránh cấu hình `include: "*"` trong môi trường production nếu chưa đánh giá đầy đủ tất cả endpoint được đưa ra.

### 9.2. Giới hạn bằng Spring Security

Nếu ứng dụng dùng Spring Security, bảo vệ các Actuator endpoint bằng role quản trị phù hợp. Ví dụ minh họa cho servlet application:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR")
                .anyRequest()
                    .authenticated()
        );

        return http.build();
    }
}
```

Đây là ví dụ chính sách, cần tích hợp với cơ chế authentication/authorization hiện có. Khi ứng dụng đã định nghĩa `SecurityFilterChain` riêng, auto-configuration security mặc định của Actuator có thể không còn áp dụng; hãy bảo đảm chain thực tế bảo vệ endpoint quản trị.

Ngoài security ở ứng dụng, nên giới hạn management port bằng network policy, firewall, private network hoặc reverse proxy có xác thực.

### 9.3. Không nhầm exposure với authorization

`management.endpoints.web.exposure.include` quyết định endpoint nào được đưa ra qua HTTP. Spring Security quyết định ai được gọi endpoint. Cấu hình exposure không tự tạo xác thực; cấu hình role không làm endpoint chưa expose trở nên khả dụng.

## 10. Beans endpoint không phải công cụ introspection toàn diện

Endpoint `beans` là giao diện chẩn đoán cho thông tin container công bố. Nó có những giới hạn:

- Không dump toàn bộ field/value bên trong object.
- Không cho biết mọi lời gọi method hoặc call graph runtime.
- Không hiển thị mọi object được tạo thủ công bằng `new` ngoài container.
- Không chứng minh bean đang khỏe hoặc kết nối downstream thành công.
- Không phải nguồn API ổn định để ứng dụng nghiệp vụ tự quyết định luồng xử lý.
- Có thể chứa lượng dữ liệu lớn trong ứng dụng có nhiều context và starter.

Nếu cần quan sát trạng thái nghiệp vụ, hãy dùng metric, health indicator, log hoặc tracing. Nếu cần kiểm tra property, dùng `env` và `configprops`. Nếu cần kiểm tra điều kiện auto-configuration, dùng `conditions`.

Không viết ứng dụng production phụ thuộc vào việc parse response `beans` để tìm một tên bean nội bộ rồi thay đổi hành vi. Tên bean và cấu trúc auto-configuration có thể thay đổi khi nâng cấp Spring Boot hoặc starter.

## 11. Quy trình chẩn đoán bean không xuất hiện

Giả sử ứng dụng mong đợi bean `catalogClient` nhưng không thấy trong response.

1. Xác nhận request đến đúng application/management port và đúng context của instance đang điều tra.
2. Tìm key `catalogClient` trong từng context, không chỉ context đầu tiên.
3. Kiểm tra package component scan hoặc configuration import.
4. Kiểm tra bean method có được khai báo và configuration có được nạp không.
5. Kiểm tra profile, property và `@ConditionalOnProperty`.
6. Mở `/actuator/conditions` để xem auto-configuration condition report.
7. Kiểm tra runtime dependency tree nếu bean đến từ starter.
8. Kiểm tra log startup để tìm lỗi khởi tạo hoặc auto-configuration bị loại trừ.
9. Nếu ứng dụng có context hierarchy, xác định bean ở parent hay child context.
10. Tạo integration test nhỏ để xác nhận bean có mặt với bộ property/classpath tương ứng.

Ví dụ tìm bean trong response:

```bash
jq '.contexts | to_entries[]
  | {context: .key, bean: .value.beans.catalogClient}' beans.json
```

Nếu kết quả là `null` trong mọi context, bean không được mô tả dưới tên đó trong response. Nó có thể có tên khác, được tạo ở context khác chưa được kiểm tra hoặc chưa được đăng ký. Hãy dùng type và configuration source để xác định tên chính xác.

## 12. Quy trình chẩn đoán bean xuất hiện sai hoặc trùng

Nếu có nhiều bean cùng interface:

1. Liệt kê bean name và type trong từng context.
2. Xem aliases để phân biệt alias với bean độc lập.
3. Xác định scope và context chứa từng bean.
4. Kiểm tra configuration class tạo bean và điều kiện áp dụng.
5. Kiểm tra `@Primary`, `@Qualifier` và injection point.
6. Xem condition report nếu bean đến từ auto-configuration.
7. Kiểm thử injection trong context nhỏ để xác nhận candidate được chọn.

Ví dụ lọc các bean có type liên quan tới gateway:

```bash
jq -r '.contexts | to_entries[] as $context
  | $context.value.beans | to_entries[]
  | select(.value.type | contains("CatalogGateway"))
  | [$context.key, .key, .value.type] | @tsv' beans.json
```

Đừng xóa bean chỉ vì có nhiều implementation. Nhiều implementation có thể là thiết kế có chủ đích; lỗi chỉ xảy ra khi injection không có qualifier hoặc selection rule phù hợp.

## 13. Kiểm thử quan sát bean trong context

Không cần gọi endpoint HTTP thật trong mọi unit test. Với test cấu hình, có thể khởi động context và kiểm tra bean trực tiếp:

```java
@SpringBootTest
class CatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersCatalogService() {
        assertThat(context.containsBean("catalogService"))
                .isTrue();

        assertThat(context.getBean("catalogService"))
                .isInstanceOf(CatalogService.class);
    }
}
```

Nếu mục tiêu là xác minh endpoint Actuator được expose, viết integration test gọi endpoint bằng MockMvc hoặc HTTP client phù hợp với test setup:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BeansEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesBeansEndpointWhenConfigured() throws Exception {
        mockMvc.perform(get("/actuator/beans"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contexts").exists());
    }
}
```

Ví dụ test endpoint cần dependency Actuator, cấu hình exposure `beans` trong test property và cấu hình security phù hợp. Nếu endpoint được bảo vệ, test phải cung cấp authentication đúng thay vì tắt security trong production configuration.

### 13.1. Test component có điều kiện

Có thể tạo hai test context với property khác nhau để xác nhận bean chỉ được đăng ký khi condition khớp:

```java
@SpringBootTest(properties = "catalog.client.stub=true")
class StubCatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersStubGateway() {
        assertThat(context.getBean(CatalogGateway.class))
                .isInstanceOf(StubCatalogGateway.class);
    }
}
```

Test này xác minh kết quả wiring. Nếu condition không match, kiểm tra report của `conditions` để tìm lý do.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/actuator/beans` trả 404 | Chưa thêm Actuator, endpoint chưa expose hoặc base path khác | Kiểm tra starter và `management.endpoints.web.exposure` |
| 401/403 | Security yêu cầu authentication/role | Kiểm tra SecurityFilterChain và quyền của user |
| Không thấy bean mong đợi | Component scan, import hoặc condition không khớp | Kiểm tra `conditions`, profile và package |
| Thấy bean nhưng type khác | Implementation được chọn bởi profile/condition khác | Kiểm tra `type`, `resource` và property |
| Tên bean xuất hiện nhiều lần | Bean nằm trong nhiều context hoặc có cấu hình đăng ký trùng | Kiểm tra context ID, aliases và configuration |
| Không hiểu dependency | Danh sách dependencies không phải call graph đầy đủ | Kiểm tra constructor, `@Bean` method và code |
| Không thấy property đã cấu hình | Đang xem nhầm endpoint | Dùng `env` hoặc `configprops` |
| Không biết vì sao auto-configuration bỏ qua bean | Beans chỉ cho kết quả cuối | Dùng `conditions` |
| Response quá lớn | Ứng dụng có nhiều bean/context | Lọc JSON bằng jq và truy vấn đúng context |
| Management port không truy cập được | Port riêng bị chặn hoặc gọi nhầm port | Kiểm tra `management.server.port` và network policy |
| Bean singleton có nhiều bản | Nhiều ApplicationContext có bean definition riêng | Kiểm tra context hierarchy và scope |

Trình tự điều tra ngắn gọn:

1. Xác nhận endpoint và context đúng.
2. Kiểm tra bean name, alias, type, scope và dependencies.
3. Đối chiếu context hierarchy.
4. Dùng `conditions` nếu bean không được tạo.
5. Dùng `env`/`configprops` nếu property ảnh hưởng cấu hình.
6. Kiểm tra log và health khi bean có mặt nhưng hoạt động lỗi.
7. Xem lại security và management network nếu endpoint không truy cập được.

## 15. Thực hành: kiểm tra bean của Catalog trong ứng dụng Spring Cloud

Giả sử ứng dụng có các thành phần:

- `CatalogService` xử lý nghiệp vụ.
- `CatalogRepository` truy cập dữ liệu.
- `CatalogGateway` gọi một catalog service khác.
- `DiscoveryClient` tra cứu instance.
- `RestTemplate` load-balanced để gọi bằng service ID.

### Bước 1 — Thêm Actuator

Thêm `spring-boot-starter-actuator` vào dependency của ứng dụng và đồng bộ version bằng Spring Boot dependency management.

### Bước 2 — Expose beans trong môi trường local/test

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
```

Không expose endpoint này công khai trong production nếu chưa có kiểm soát security và network.

### Bước 3 — Khởi động ứng dụng và lấy danh sách

```bash
curl -s http://localhost:8080/actuator/beans > beans.json
```

### Bước 4 — Kiểm tra bean nghiệp vụ

```bash
jq '.contexts[].beans.catalogService' beans.json
jq '.contexts[].beans.catalogRepository' beans.json
```

Xác nhận bean name, type, scope và dependencies.

### Bước 5 — Kiểm tra integration Spring Cloud

Tìm bean discovery/load balancer theo type hoặc tên thực tế trong response. Nếu không thấy implementation dự kiến, kiểm tra dependency và condition report.

### Bước 6 — Kiểm tra context hierarchy

```bash
jq '.contexts | to_entries[] | {id: .key, parentId: .value.parentId}' beans.json
```

Xác định bean nằm ở context nào. Nếu cùng tên xuất hiện ở nhiều context, xác minh đó là cấu hình context riêng hay đăng ký trùng không mong muốn.

### Bước 7 — Kiểm tra an toàn endpoint

Xác nhận chỉ user/role quản trị được đọc endpoint và management port không được mở ngoài mạng quản trị. Không lưu output có thông tin kiến trúc vào artifact công khai.

### Câu hỏi tự kiểm tra

1. Endpoint `beans` của Spring Boot Actuator dùng để quan sát điều gì?
2. Dependency nào cung cấp endpoint Actuator?
3. Vì sao thêm Actuator starter chưa chắc gọi được `/actuator/beans` qua HTTP?
4. `contexts` và `parentId` giúp hiểu điều gì?
5. Các trường `aliases`, `scope`, `type`, `resource` và `dependencies` có ý nghĩa gì?
6. Alias có phải một bean instance mới không?
7. Vì sao singleton trong hai ApplicationContext có thể là hai instance khác nhau?
8. Endpoint `beans` có cho biết mọi method call runtime không?
9. Dùng endpoint nào để biết vì sao auto-configuration không match?
10. Khi cần xem property đã bind, nên dùng endpoint nào?
11. Vì sao cần bảo vệ endpoint `beans`?
12. Khi nào nên dùng integration test thay vì chỉ đọc Actuator output?

**Gợi ý đáp án:** (1) Danh sách bean theo application context và descriptor của chúng; (2) `spring-boot-starter-actuator`; (3) Vì endpoint cần được expose qua HTTP và được phép truy cập; (4) Quan hệ giữa các context cha/con; (5) Alias, scope, kiểu, resource khai báo và dependency container ghi nhận; (6) Không, alias là tên khác của cùng bean; (7) Singleton được quản lý theo từng container; (8) Không, endpoint không phải call graph; (9) `conditions`; (10) `configprops` hoặc `env` tùy câu hỏi; (11) Vì nó tiết lộ tên class, package, cấu trúc bean và quan hệ nội bộ; (12) Khi cần xác minh lifecycle/context isolation hoặc hành vi thực tế thay vì chỉ xem trạng thái hiện tại.

## 16. Những nguyên tắc cần nhớ

- Endpoint `beans` của Actuator cho biết các bean mà Spring quản lý trong từng ApplicationContext.
- Cần thêm Actuator starter, expose endpoint và cấu hình quyền truy cập phù hợp.
- Bean descriptor có thể chứa alias, scope, type, resource và dependency.
- Context ID và parent ID giúp phân biệt bean trong context cha/con.
- Alias không tạo bean instance mới; singleton được quản lý theo container.
- Endpoint `beans` mô tả container, không phải call graph hay health report.
- Dùng `conditions` để điều tra auto-configuration, `env`/`configprops` để kiểm tra property, `mappings` để kiểm tra HTTP route và `health` để kiểm tra trạng thái dependency.
- Trong Spring Cloud, endpoint giúp xác minh discovery, load balancer, config và refresh infrastructure đã được tạo; nó không chứng minh các integration đó đang hoạt động đúng.
- Chỉ expose endpoint trên mạng quản trị và giới hạn bằng authentication/authorization.
- Dùng integration test để xác minh bean wiring và hành vi request thực tế; không để logic nghiệp vụ phụ thuộc vào việc parse output của endpoint.

Quan sát bean bằng `/actuator/beans` giúp nhìn thấy kết quả wiring của Spring container thay vì chỉ suy luận từ source code. Khi kết hợp endpoint này với `conditions`, `env`, `configprops` và log, người vận hành có thể xác định rõ bean nào đã được tạo, thuộc context nào và cần điều tra tiếp ở tầng cấu hình hay runtime.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Exposing Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.exposing)
- [Spring Boot API — BeansEndpoint](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/beans/BeansEndpoint.html)
- [Spring Framework Reference — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
