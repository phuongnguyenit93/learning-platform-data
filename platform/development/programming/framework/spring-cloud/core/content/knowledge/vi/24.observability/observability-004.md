# DiscoveryClientHealthIndicator và DiscoveryCompositeHealthContributor

Bài học thuộc chương **Quan sát** của module **SPRING_CLOUD_CORE**. Spring Cloud Commons tích hợp service discovery với Spring Boot Actuator bằng các health indicator. `DiscoveryClientHealthIndicator` kiểm tra khả năng sử dụng của blocking `DiscoveryClient` hiện tại; `DiscoveryCompositeHealthContributor` gom các `DiscoveryHealthIndicator` đã đăng ký thành một nhóm health contributor để Actuator hiển thị trạng thái tổng hợp và trạng thái từng provider.

Hai thành phần có phạm vi khác nhau. Indicator đơn lẻ thực hiện phép kiểm tra trên DiscoveryClient và tạo kết quả `UP`, `DOWN` hoặc `UNKNOWN`. Composite contributor chỉ tổ chức nhiều indicator thành cây kết quả; nó không tự truy vấn registry thay cho các indicator con. Vì vậy, khi đọc `/actuator/health`, cần xem cả trạng thái tổng hợp lẫn chi tiết của từng thành phần.

Một điểm quan trọng của implementation hiện hành là `DiscoveryClientHealthIndicator` chờ nhận `InstanceRegisteredEvent` để đánh dấu discovery đã khởi tạo. Trước sự kiện đó, health trả `UNKNOWN`. Sau khi khởi tạo, indicator mặc định gọi `getServices()`; nếu lời gọi không ném exception thì status là `UP`, kể cả khi danh sách service rỗng. Bài học giải thích giới hạn của phép kiểm tra này, cách giảm chi phí truy vấn, cấu hình bật/tắt và cách kiểm thử trong môi trường thực tế.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của `DiscoveryClientHealthIndicator` trong Spring Cloud Commons.
2. Phân biệt health indicator đơn lẻ với `DiscoveryCompositeHealthContributor`.
3. Mô tả điều kiện auto-configuration tạo blocking discovery health indicator.
4. Giải thích vì sao trạng thái ban đầu có thể là `UNKNOWN`.
5. Phân biệt `getServices()` và `probe()` khi kiểm tra discovery.
6. Cấu hình `use-services-query` để điều chỉnh chi phí health check.
7. Cấu hình description và hiểu ảnh hưởng đến kết quả health tổng hợp.
8. Bật/tắt indicator và composite contributor độc lập.
9. Đọc cây kết quả của Actuator `/actuator/health`.
10. Phân biệt discovery health với application health, readiness, liveness và service registration.
11. Nhận biết các giới hạn khi dùng nhiều discovery provider hoặc reactive discovery.
12. Thiết kế test cho trạng thái UNKNOWN, UP, DOWN, composite và các property.
13. Chẩn đoán tình huống health UP nhưng service ID không có instance cần gọi.
14. Đưa ra chính sách vận hành phù hợp để tránh health check gây tải không cần thiết lên registry.

## 2. Vai trò của DiscoveryClientHealthIndicator

### 2.1. DiscoveryClient cung cấp khả năng tìm service

`DiscoveryClient` là abstraction blocking của Spring Cloud Commons. Nó cho phép ứng dụng hỏi các service ID đã biết và lấy danh sách instance theo service ID:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

Các implementation có thể kết nối với Eureka, Consul, Zookeeper hoặc nguồn discovery khác. Ứng dụng sử dụng contract chung thay vì phụ thuộc API riêng của provider.

Tuy nhiên, việc có bean `DiscoveryClient` trong ApplicationContext không chứng minh registry đang truy cập được. Bean có thể tồn tại trong khi DNS, network, credential hoặc registry server gặp lỗi. `DiscoveryClientHealthIndicator` bổ sung một phép kiểm tra sức khỏe bằng cách gọi API discovery trong quá trình Actuator thu thập health.

### 2.2. Indicator đơn lẻ kiểm tra điều gì?

`DiscoveryClientHealthIndicator` dựa trên implementation `DiscoveryClient` hiện có. Sau khi discovery được đánh dấu đã khởi tạo, indicator gọi một trong hai thao tác:

- `getServices()` nếu `use-services-query=true`.
- `probe()` nếu `use-services-query=false`.

Nếu thao tác hoàn tất mà không ném exception, indicator trả status `UP`. Nếu có exception, indicator trả `DOWN` và gắn lỗi vào health result. Nếu indicator chưa nhận được tín hiệu khởi tạo, nó trả `UNKNOWN`.

Điều này có nghĩa indicator chủ yếu kiểm tra khả năng gọi discovery API. Nó không tự xác minh một service ID cụ thể, số lượng instance tối thiểu hoặc khả năng gọi HTTP tới từng instance.

### 2.3. Luồng xử lý

~~~mermaid
flowchart TD
    A["Actuator yêu cầu health"] --> B{"Discovery đã khởi tạo?"}
    B -->|Chưa| C["UNKNOWN: Discovery Client not initialized"]
    B -->|Rồi| D{"use-services-query"}
    D -->|true| E["Gọi DiscoveryClient.getServices()"]
    D -->|false| F["Gọi DiscoveryClient.probe()"]
    E --> G{"Lời gọi có exception?"}
    F --> G
    G -->|Không| H["UP"]
    G -->|Có| I["DOWN + error detail"]
~~~

Indicator không tự retry vô hạn khi provider lỗi. Timeout, retry và hành vi kết nối phụ thuộc implementation của DiscoveryClient và cấu hình client bên dưới.

## 3. Điều kiện tạo health indicator

Spring Cloud Commons auto-configure health indicator khi các điều kiện phù hợp được đáp ứng. Với blocking indicator, các điều kiện chính gồm:

- Spring Boot Actuator health API có trên classpath.
- Có bean `DiscoveryClient` trong ApplicationContext.
- Discovery được bật.
- Blocking discovery client được bật.
- Property riêng của discovery health indicator không bị tắt.

Trong auto-configuration hiện hành, bean `DiscoveryClientHealthIndicator` được tạo trong cấu hình discovery/load-balancer. Bean composite được tạo khi có ít nhất một bean triển khai `DiscoveryHealthIndicator` và composite property vẫn bật.

| Thành phần | Điều kiện chính |
| --- | --- |
| `DiscoveryClientHealthIndicator` | Actuator health class, bean DiscoveryClient, discovery enabled, blocking discovery enabled và health-indicator enabled. |
| `DiscoveryCompositeHealthContributor` | Có bean DiscoveryHealthIndicator và composite-indicator enabled. |
| Reactive discovery health contributor | Có ReactiveDiscoveryClient/ReactiveDiscoveryHealthIndicator phù hợp, reactive discovery và reactive Actuator support. |

Chỉ thêm `spring-boot-starter-actuator` không đảm bảo indicator discovery xuất hiện. Ứng dụng còn cần discovery provider hoặc một implementation DiscoveryClient phù hợp.

## 4. Vòng đời khởi tạo và trạng thái UNKNOWN

### 4.1. Indicator lắng nghe InstanceRegisteredEvent

Implementation hiện hành của `DiscoveryClientHealthIndicator` triển khai `ApplicationListener<InstanceRegisteredEvent<?>>`. Khi nhận sự kiện `InstanceRegisteredEvent`, indicator đánh dấu discovery đã được khởi tạo.

Trước thời điểm đó, health result có dạng khái quát:

~~~json
{
  "status": "UNKNOWN",
  "description": "Discovery Client not initialized"
}
~~~

Đây là trạng thái chưa xác nhận quá trình khởi tạo discovery đã hoàn tất. Nó không đồng nghĩa registry chắc chắn đang hỏng.

### 4.2. Vì sao event quan trọng?

Với service registry auto-registration, Spring Cloud thường phát hai event:
- `InstancePreRegisteredEvent` trước khi đăng ký instance.
- `InstanceRegisteredEvent` sau khi đăng ký instance.

`DiscoveryClientHealthIndicator` sử dụng event thứ hai làm tín hiệu khởi tạo. Sau đó, các lần health check tiếp theo mới thực hiện truy vấn/probe.

Nếu ứng dụng tắt auto-registration, provider không phát event tương ứng hoặc ứng dụng có lifecycle đăng ký thủ công không phát event này, indicator có thể tiếp tục ở trạng thái `UNKNOWN` trong implementation đang dùng. Hãy kiểm tra lifecycle của provider và release train thay vì mặc định coi đây là lỗi kết nối registry.

Cấu hình tắt auto-registration:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Nếu cần tắt auto-registration nhưng vẫn muốn health indicator phản ánh discovery, hãy xác định cách provider phát tín hiệu initialization trong quy trình thủ công. Không tự giả lập event trong production chỉ để ép status thành UP khi registry chưa sẵn sàng.

### 4.3. UNKNOWN khác DOWN

| Status | Ý nghĩa |
| --- | --- |
| `UNKNOWN` | Indicator chưa xác nhận discovery đã khởi tạo hoặc không thể kết luận trạng thái. |
| `UP` | Truy vấn/probe hoàn tất mà không ném exception. |
| `DOWN` | Truy vấn/probe ném exception và indicator ghi nhận lỗi. |

Đừng chuyển mọi trường hợp UNKNOWN thành DOWN bằng một rule giám sát chung. Cần phân biệt giai đoạn startup, cấu hình auto-registration và lỗi thật khi gọi registry.

## 5. getServices() và probe()

### 5.1. Chế độ truy vấn danh sách service

Mặc định:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: true
~~~

Indicator gọi `DiscoveryClient.getServices()`. Khi thành công, danh sách service ID được thêm vào health details với key `services`.

Ví dụ kết quả:

~~~json
{
  "status": "UP",
  "details": {
    "services": [
      "inventory-service",
      "pricing-service",
      "orders-service"
    ]
  }
}
~~~

Danh sách có thể rất lớn trong môi trường nhiều team hoặc nhiều service. Nếu health endpoint được gọi liên tục bởi orchestrator và monitoring, truy vấn toàn bộ service ID có thể tạo tải đáng kể lên registry.

### 5.2. Danh sách rỗng vẫn có thể UP

Indicator không yêu cầu danh sách trả về phải có ít nhất một phần tử. Nếu `getServices()` trả về danh sách rỗng mà không ném exception, implementation vẫn đặt status `UP`.

Do đó:

- `UP` chứng minh thao tác discovery API đã hoàn tất theo contract của indicator.
- `UP` không chứng minh service ID mà ứng dụng cần gọi đang tồn tại.
- `UP` không chứng minh service đó có instance healthy.
- `UP` không chứng minh ứng dụng gọi HTTP tới instance thành công.

Nếu nghiệp vụ cần xác minh một dependency quan trọng, hãy tạo health check riêng có kiểm tra service ID hoặc thực hiện probe tới dependency theo timeout hợp lý. Tránh biến health indicator chung thành truy vấn mọi dependency trong mỗi lần health request.

### 5.3. Chuyển sang probe()

Để tránh lấy toàn bộ service list:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Indicator sẽ gọi `DiscoveryClient.probe()` và không đưa danh sách service vào details.

`DiscoveryClient` cung cấp implementation mặc định của `probe()` bằng cách gọi `getServices()`. Provider có thể override method này để thực hiện phép kiểm tra nhẹ hơn. Vì vậy, đặt `use-services-query=false` chỉ đảm bảo indicator gọi `probe()`; mức giảm tải thực tế phụ thuộc implementation provider.

### 5.4. So sánh hai chế độ

| Tiêu chí | getServices() | probe() |
| --- | --- | --- |
| Mục tiêu | Truy vấn toàn bộ service ID đã biết. | Kiểm tra client có thể thực hiện discovery operation hay không. |
| Health detail | Có danh sách `services`. | Không có danh sách service do indicator tạo. |
| Chi phí | Có thể cao khi registry có nhiều service. | Có thể thấp hơn nếu provider override probe bằng thao tác nhẹ. |
| Mặc định của Commons | Được dùng khi `use-services-query=true`. | Được dùng khi property là false. |
| Giới hạn | Danh sách rỗng vẫn có thể trả UP. | Default probe vẫn gọi getServices; không mặc nhiên nhẹ hơn. |
## 6. Description và health details

### 6.1. include-description

`DiscoveryClient` có method `description()` để cung cấp mô tả implementation. Property `spring.cloud.discovery.client.health-indicator.include-description` mặc định là `false`. Khi đặt `true`, indicator đọc `client.description()` và gắn mô tả vào health status; mô tả có thể xuất hiện trong kết quả health tổng hợp.

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          include-description: true
          use-services-query: true
~~~

Mô tả giúp phân biệt implementation trong môi trường có nhiều provider. Không đưa endpoint nội bộ, hostname nhạy cảm hoặc credential vào chuỗi description.

### 6.2. Services detail

Khi dùng `getServices()`, indicator thêm danh sách service ID vào detail. Đây là dữ liệu chẩn đoán hữu ích, nhưng có thể tiết lộ topology nội bộ. Hãy kiểm soát ai có thể đọc chi tiết health endpoint.

### 6.3. Ẩn details không đồng nghĩa tắt indicator

Spring Boot cho phép điều khiển mức độ chi tiết được hiển thị qua Actuator:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Các giá trị phổ biến là `never`, `when-authorized` và `always`. Cấu hình này điều khiển nội dung được hiển thị; nó không ngăn health indicator thực thi phép kiểm tra.

Nếu mục tiêu là giảm tải truy vấn registry, cấu hình `use-services-query` hoặc tắt indicator. Nếu mục tiêu là hạn chế người dùng xem topology, điều chỉnh show-details/show-components và security.

## 7. DiscoveryCompositeHealthContributor là gì?

### 7.1. Composite contributor tổng hợp các indicator

`DiscoveryCompositeHealthContributor` là adapter chuyển collection các bean `DiscoveryHealthIndicator` thành một `CompositeHealthContributor` của Spring Boot Actuator.

Nó không gọi `DiscoveryClient.getServices()` thay cho từng indicator và cũng không tự kết nối registry. Mỗi indicator con tự thực hiện phép kiểm tra; composite contributor cung cấp một cấu trúc có tên để Actuator hiển thị từng kết quả.

Ví dụ, ApplicationContext có:
- Indicator chung `DiscoveryClientHealthIndicator`.
- Indicator riêng của một provider.
- Indicator riêng của một provider thứ hai.

Composite contributor gom chúng vào một nhóm health.

~~~mermaid
flowchart TD
    ACT["Actuator HealthEndpoint"] --> ROOT["DiscoveryCompositeHealthContributor"]
    ROOT --> GENERIC["DiscoveryClientHealthIndicator"]
    ROOT --> PROVIDER_A["Provider A DiscoveryHealthIndicator"]
    ROOT --> PROVIDER_B["Provider B DiscoveryHealthIndicator"]
    GENERIC --> CLIENT["Blocking DiscoveryClient"]
    PROVIDER_A --> REG_A["Registry A health check"]
    PROVIDER_B --> REG_B["Registry B health check"]
~~~

### 7.2. Composite không phải CompositeDiscoveryClient

Hai khái niệm có tên gần nhau nhưng chức năng khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `DiscoveryCompositeHealthContributor` | Gom nhiều `DiscoveryHealthIndicator` thành một cây health contributor. |
| `CompositeDiscoveryClient` | Kết hợp nhiều implementation `DiscoveryClient` để thực hiện thao tác discovery. |

Composite health dùng để quan sát tình trạng của các discovery indicator. Composite discovery client dùng để truy vấn các nguồn discovery. Một ứng dụng có thể có một, cả hai hoặc không có, tùy provider và cấu hình.

### 7.3. Điều kiện tạo composite

Composite contributor được auto-configure khi:
1. Có ít nhất một bean triển khai `DiscoveryHealthIndicator`.
2. `spring.cloud.discovery.client.composite-indicator.enabled` không bị tắt.
3. Auto-configuration discovery tương ứng được kích hoạt.

Nếu không có indicator con, composite không có dữ liệu để gom và bean composite không được tạo theo điều kiện hiện hành.

## 8. Đọc kết quả /actuator/health

### 8.1. Cấu hình Actuator

Ứng dụng cần dependency Actuator và discovery provider phù hợp. Endpoint health thường được truy cập qua:

~~~text
GET /actuator/health
~~~

Để hiển thị các component và details trong môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

Trong production, thay `always` bằng `when-authorized` hoặc giới hạn quyền truy cập bằng Spring Security và management network.

### 8.2. Ví dụ response có composite

Response minh họa khi có indicator chung và provider-specific indicator:

~~~json
{
  "status": "UP",
  "components": {
    "discoveryComposite": {
      "status": "UP",
      "components": {
        "discoveryClient": {
          "status": "UP",
          "details": {
            "services": [
              "inventory-service",
              "pricing-service"
            ]
          }
        },
        "registryProvider": {
          "status": "UP",
          "details": {
            "description": "Provider-specific discovery health"
          }
        }
      }
    }
  }
}
~~~

Tên child cụ thể phụ thuộc bean và implementation được đăng ký. `discoveryClient` là tên mà `DiscoveryClientHealthIndicator` hiện hành cung cấp; provider-specific indicator có thể dùng tên riêng.

### 8.3. Composite status và child status

Composite hiển thị trạng thái của từng contributor con và trạng thái tổng hợp. Spring Boot sử dụng status aggregation strategy để tính trạng thái tổng thể. Với status tùy chỉnh, cần cấu hình thứ tự hoặc cung cấp StatusAggregator phù hợp.

Ví dụ cấu hình thứ tự severity:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: down,out-of-service,unknown,up
~~~

Không giả định status tổng hợp luôn là UP chỉ vì một child trả UP. Hãy xem từng child và thứ tự status aggregation của ứng dụng.

### 8.4. HTTP status code không thay thế JSON status

Theo mapping mặc định của Spring Boot:
- `DOWN` và `OUT_OF_SERVICE` thường ánh xạ HTTP 503.
- `UP` và `UNKNOWN` không có mapping riêng nên thường trả HTTP 200.

Vì vậy, hệ thống monitoring nên đọc field `status` trong response thay vì chỉ dựa vào HTTP 200. Nếu ứng dụng cấu hình custom HTTP status mapping, hãy kiểm tra lại behavior sau khi thay đổi.

## 9. Cấu hình bật/tắt độc lập

Các property liên quan có phạm vi khác nhau:

| Property | Mục tiêu | Mặc định theo Commons config metadata |
| --- | --- | --- |
| `spring.cloud.discovery.client.health-indicator.enabled` | Bật/tắt generic blocking DiscoveryClientHealthIndicator. | `true` |
| `spring.cloud.discovery.client.health-indicator.include-description` | Có đưa description của DiscoveryClient vào health hay không. | `false` |
| `spring.cloud.discovery.client.health-indicator.use-services-query` | Chọn getServices hay probe. | `true` |
| `spring.cloud.discovery.client.composite-indicator.enabled` | Bật/tắt DiscoveryCompositeHealthContributor. | `true` |
| `spring.cloud.discovery.enabled` | Bật/tắt discovery tổng thể và các auto-configuration liên quan. | `true` |
| `spring.cloud.discovery.blocking.enabled` | Bật/tắt blocking discovery client. | `true` |
| `spring.cloud.discovery.reactive.enabled` | Bật/tắt reactive discovery client. | `true` |

### 9.1. Tắt generic health indicator

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
~~~

Thao tác này ngăn auto-configuration tạo `DiscoveryClientHealthIndicator`. Provider-specific `DiscoveryHealthIndicator` khác có thể vẫn tồn tại. Nếu chúng tồn tại và composite vẫn bật, composite vẫn có thể được tạo từ các indicator còn lại.

### 9.2. Tắt composite contributor

~~~yaml
spring:
  cloud:
    discovery:
      client:
        composite-indicator:
          enabled: false
~~~

Các indicator con vẫn có thể được tạo và xuất hiện như health component riêng. Chỉ nhóm tổng hợp discovery bị tắt.

### 9.3. Chỉ bỏ description

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          include-description: false
~~~

Indicator vẫn chạy. Cấu hình này chỉ loại description của DiscoveryClient khỏi health result.

### 9.4. Chuyển sang probe

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Indicator vẫn hoạt động nhưng dùng `probe()`. Mức giảm tải phụ thuộc implementation provider.

### 9.5. Tắt toàn bộ discovery

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

Đây là công tắc phạm vi rộng. Nó ảnh hưởng discovery auto-configuration, không chỉ health indicator. Không dùng property này nếu mục tiêu chỉ là ẩn health details hoặc giảm chi phí truy vấn.

### 9.6. Tắt riêng blocking discovery

~~~yaml
spring:
  cloud:
    discovery:
      blocking:
        enabled: false
~~~

Blocking health indicator phụ thuộc blocking DiscoveryClient và điều kiện auto-configuration tương ứng, nên có thể không được tạo. Reactive discovery có thể vẫn được bật nếu provider và reactive stack hỗ trợ.

## 10. Blocking và reactive health contributors

Bài học tập trung vào `DiscoveryClientHealthIndicator` và `DiscoveryCompositeHealthContributor` dành cho blocking discovery.

Spring Cloud Commons cũng có các abstraction reactive:
- `ReactiveDiscoveryClient`.
- `ReactiveDiscoveryHealthIndicator`.
- `ReactiveDiscoveryCompositeHealthContributor`.

Reactive contributor phù hợp với reactive health infrastructure và provider có reactive discovery support. Không giả định blocking indicator tự kiểm tra reactive client hoặc ngược lại.

Property `spring.cloud.discovery.client.composite-indicator.enabled` được dùng trong cấu hình composite discovery tương ứng; hãy xác minh cả blocking và reactive contributor trong ApplicationContext nếu ứng dụng bật cả hai stack.
## 11. Phân biệt discovery health với readiness và liveness

### 11.1. Discovery health không phải readiness

Discovery health trả lời câu hỏi: ứng dụng có thể gọi discovery API theo phép kiểm tra hiện tại hay không?

Readiness trả lời câu hỏi: instance có nên nhận traffic mới hay chưa?

Một ứng dụng có thể có discovery API UP nhưng một dependency service cụ thể không có instance. Ngược lại, discovery registry có thể tạm thời mất kết nối nhưng ứng dụng vẫn phục vụ request đang xử lý hoặc cache được danh sách instance gần đây.

Nếu service discovery là điều kiện bắt buộc để nhận traffic mới, cân nhắc đưa component discovery vào readiness group. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,discoveryComposite
~~~

Tên component cần khớp với health contributor ID thực tế trong ứng dụng. Kiểm tra response `/actuator/health` trước khi đưa vào deployment probe.

### 11.2. Tránh dùng discovery làm liveness mặc định

Liveness nên phản ánh process có bị kẹt hoặc không thể tiếp tục chạy hay không. Nếu registry bên ngoài tạm thời mất kết nối mà liveness chuyển DOWN, orchestrator có thể restart hàng loạt instance dù lỗi nằm ở hạ tầng registry.

Readiness thường là nơi phù hợp hơn nếu việc mất discovery khiến instance không thể phục vụ request mới. Quyết định phụ thuộc kiến trúc và khả năng phục vụ bằng cache/fallback.

### 11.3. Bảng phân biệt

| Cơ chế | Câu hỏi |
| --- | --- |
| DiscoveryClientHealthIndicator | Discovery client có thể thực hiện getServices/probe sau khi khởi tạo không? |
| DiscoveryCompositeHealthContributor | Các discovery health indicators con có trạng thái tổng hợp nào? |
| Liveness | Process còn hoạt động đủ để tiếp tục chạy không? |
| Readiness | Instance có sẵn sàng nhận traffic mới không? |
| Business dependency check | Một dependency cụ thể có đáp ứng yêu cầu nghiệp vụ không? |

## 12. Chi phí và tần suất health check

### 12.1. Polling thường xuyên có thể tạo tải

Orchestrator, load balancer và monitoring platform có thể gọi health endpoint theo chu kỳ ngắn. Nếu mỗi lần gọi đều thực hiện `getServices()` trên registry lớn, tổng số truy vấn có thể tăng đáng kể.

Ước lượng tải theo cách đơn giản:

~~~text
Tổng số lần health check mỗi phút
= số instance ứng dụng × 60 / chu kỳ kiểm tra (giây)
~~~

Ví dụ 120 instance, chu kỳ 10 giây:

~~~text
120 × 60 / 10 = 720 lần kiểm tra mỗi phút
~~~

Nếu mỗi lần kiểm tra kéo theo truy vấn danh sách service lớn, cần xem xét `probe()`, cache ở provider hoặc điều chỉnh tần suất monitoring.

### 12.2. Giảm dữ liệu trả về

`use-services-query=false` loại bỏ bước lấy danh sách service và detail tương ứng. Tuy nhiên, nó không bảo đảm provider không thực hiện truy vấn danh sách ở bên trong `probe()`.

Đọc implementation provider hoặc quan sát metrics để xác định probe có thực sự nhẹ hơn.

### 12.3. Giới hạn timeout

Health indicator cần trả kết quả trong thời gian mà Actuator, orchestrator và monitoring chờ. Timeout phải được cấu hình ở discovery provider/client phù hợp. Nếu timeout quá dài, health request có thể kéo dài và làm các lần kiểm tra chồng lấn.

Không tăng timeout vô hạn để che lỗi registry. Hãy đặt deadline phù hợp với chu kỳ probe và tổng thời gian phản hồi của health endpoint.

## 13. Nhiều discovery provider trong cùng ứng dụng

### 13.1. Nhiều DiscoveryClient

Spring Cloud Commons cho phép nhiều implementation DiscoveryClient cùng tồn tại. Các client có thể được kết hợp qua `CompositeDiscoveryClient` và được sắp xếp theo order.

Health indicator chung nhận một DiscoveryClient từ ApplicationContext theo cơ chế wiring hiện hành. Nếu context có nhiều candidate, kiểm tra bean chính hoặc composite client mà indicator thực sự sử dụng.

### 13.2. Nhiều DiscoveryHealthIndicator

Composite health contributor thu thập tất cả bean `DiscoveryHealthIndicator`. Nhờ vậy, provider có thể công bố health check riêng, bên cạnh indicator chung.

Ví dụ:
- Generic discovery client check.
- Provider A health check.
- Provider B health check.

Nếu provider A DOWN nhưng generic client UP, composite vẫn hiển thị cả hai kết quả để đội vận hành biết lớp nào gặp lỗi. Trạng thái tổng hợp được tính theo StatusAggregator của Spring Boot.

### 13.3. Không nhầm composite discovery và composite health

Một CompositeDiscoveryClient có thể chọn hoặc kết hợp các kết quả service instance. DiscoveryCompositeHealthContributor chỉ tổng hợp health. Hai thành phần không có cùng trách nhiệm và không thay thế nhau.

## 14. Kiểm thử DiscoveryClientHealthIndicator

### 14.1. Các trạng thái cần kiểm tra

Một bộ test indicator nên xác minh:

1. Trước khi nhận initialization event, status là UNKNOWN.
2. Sau initialization event, getServices trả danh sách thì status là UP.
3. getServices trả danh sách rỗng nhưng không exception vẫn là UP.
4. getServices ném exception thì status là DOWN.
5. use-services-query=false gọi probe thay vì gọi trực tiếp getServices từ indicator.
6. include-description điều khiển description.
7. Services detail chỉ xuất hiện trong chế độ getServices.

Các trường hợp này phản ánh logic của indicator và giúp tránh hiểu nhầm rằng nó kiểm tra sự tồn tại của một service cụ thể.

### 14.2. Kiểm thử trong ApplicationContext

Dùng Spring Boot test context với Actuator và một DiscoveryClient test double. Có thể tạo provider test để:
- Trả một danh sách service xác định.
- Trả danh sách rỗng.
- Ném exception khi getServices/probe được gọi.
- Phát `InstanceRegisteredEvent` sau khi test fixture hoàn tất bước khởi tạo.

Test cần xác minh bean `DiscoveryClientHealthIndicator` thực sự được auto-configure khi các condition và property phù hợp.

### 14.3. Kiểm thử composite contributor

Đăng ký hai bean `DiscoveryHealthIndicator` có tên khác nhau, một trả UP và một trả DOWN. Gọi HealthEndpoint và xác minh:
- Composite contributor được tạo khi property bật.
- Hai child contributor đều có mặt.
- Mỗi child giữ trạng thái riêng.
- Root/composite status theo StatusAggregator.
- Khi composite property tắt, các indicator con vẫn có thể xuất hiện riêng.

Không chỉ assert bean composite tồn tại. Cần kiểm tra kết quả health endpoint để xác minh tên và cây contributor được lắp đúng.

### 14.4. Kiểm thử property

| Property | Test bật/tắt |
| --- | --- |
| `health-indicator.enabled` | Indicator chung có/không có trong context. |
| `composite-indicator.enabled` | Composite contributor có/không có khi có indicator con. |
| `include-description` | Description có/không xuất hiện trong health output. |
| `use-services-query` | getServices/probe được gọi đúng nhánh. |
| `spring.cloud.discovery.enabled` | Auto-configuration discovery tổng thể được kích hoạt hoặc loại bỏ. |
| `spring.cloud.discovery.blocking.enabled` | Blocking indicator có được cấu hình hay không. |

## 15. Kiểm thử qua HTTP health endpoint

### 15.1. Gọi endpoint

~~~bash
curl --request GET \
  http://localhost:8080/actuator/health
~~~

Để đọc chi tiết khi kiểm thử local, có thể cấu hình:

~~~yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

Trong môi trường production, chỉ cấp quyền xem details cho principal phù hợp.

### 15.2. Assertion nên dựa trên status và component

Một HTTP test nên kiểm tra:
- HTTP status code theo mapping đã cấu hình.
- Root health status.
- Có hoặc không có component discovery composite.
- Status của từng child.
- Services detail khi use-services-query bật.
- Description khi include-description bật.

Đừng chỉ assert HTTP 200. UNKNOWN cũng có thể được ánh xạ HTTP 200 theo default status mapping của Spring Boot.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Discovery component không xuất hiện. | Thiếu Actuator, DiscoveryClient bean, blocking discovery hoặc property đã tắt. | Kiểm tra dependency, bean và các condition. |
| Status luôn UNKNOWN. | Indicator chưa nhận InstanceRegisteredEvent hoặc lifecycle registration không phát event. | Kiểm tra auto-registration/provider lifecycle và phiên bản đang dùng. |
| Status UP nhưng không có service. | getServices trả danh sách rỗng mà không exception. | Kiểm tra service registration, namespace và service ID; UP không xác minh danh sách có phần tử. |
| Status DOWN. | getServices/probe ném exception. | Kiểm tra registry endpoint, DNS, network, credential, TLS và timeout. |
| Probe mode vẫn tốn nhiều tài nguyên. | Provider không override probe và default probe vẫn gọi getServices. | Kiểm tra implementation hoặc metrics provider. |
| Composite không xuất hiện. | Không có DiscoveryHealthIndicator bean hoặc composite property bị tắt. | Kiểm tra indicator con và composite-indicator.enabled. |
| Composite UP dù một provider UNKNOWN. | StatusAggregator hoặc contributor khác làm trạng thái tổng hợp theo severity order. | Xem child status và cấu hình status.order. |
| Chỉ thấy generic indicator. | Provider không cung cấp DiscoveryHealthIndicator riêng hoặc provider health auto-config chưa chạy. | Kiểm tra provider integration và bean health indicator. |
| Tắt health-indicator nhưng vẫn thấy discovery component. | Provider-specific indicator vẫn được đăng ký hoặc composite chứa indicator khác. | Xem bean contributors; tắt composite nếu cần bỏ nhóm tổng hợp. |
| Tắt composite nhưng vẫn thấy health child. | Các indicator con vẫn được Spring Boot đăng ký độc lập. | Đây là hành vi có thể xảy ra; composite flag chỉ tắt composite contributor. |
| Health endpoint trả 200 dù status UNKNOWN. | Default HTTP mapping của Spring Boot không map UNKNOWN sang 503. | Đọc field status trong JSON và cấu hình mapping nếu chính sách yêu cầu. |
| Health endpoint chậm. | getServices truy vấn danh sách lớn hoặc provider timeout cao. | Cân nhắc probe, timeout, chu kỳ probe và provider-specific optimization. |
| Liveness làm pod restart khi registry lỗi. | Discovery health bị gắn vào liveness group. | Chuyển sang readiness nếu discovery chỉ ảnh hưởng khả năng nhận traffic mới. |
| Không thấy health details qua HTTP. | show-details/show-components hoặc security policy đang ẩn details. | Cấu hình Actuator theo môi trường và quyền truy cập. |
| Reactive discovery có nhưng không có blocking indicator. | Ứng dụng chỉ bật reactive DiscoveryClient. | Kiểm tra ReactiveDiscoveryHealthIndicator và reactive composite contributor riêng. |

## 17. Nguyên tắc vận hành

1. **Hiểu đúng ý nghĩa UP.** UP chỉ xác nhận getServices/probe hoàn tất mà không exception theo contract của indicator.
2. **Xử lý UNKNOWN theo lifecycle.** Kiểm tra InstanceRegisteredEvent và auto-registration trước khi kết luận registry lỗi.
3. **Chọn chế độ query có chủ đích.** Dùng probe nếu provider có implementation nhẹ và không cần service list.
4. **Không giả định probe luôn rẻ.** Default probe có thể gọi getServices.
5. **Tách indicator và composite.** Tắt một indicator không đồng nghĩa tắt mọi provider health indicator.
6. **Quan sát child status.** Composite status có thể che mất thông tin chi tiết nếu chỉ nhìn root.
7. **Không dùng health để xác minh mọi service.** Dependency quan trọng cần health check riêng với timeout và semantics rõ ràng.
8. **Phân biệt readiness và liveness.** Registry outage không nên tự động kích hoạt restart loop.
9. **Bảo vệ health details.** Danh sách service và mô tả provider có thể tiết lộ topology nội bộ.
10. **Đặt timeout hợp lý.** Health request phải kết thúc trước deadline của orchestrator/monitoring.
11. **Theo dõi chi phí.** Đo thời gian indicator, số lần probe và tải lên registry.
12. **Đối chiếu release train.** Điều kiện auto-configuration và reactive counterpart có thể thay đổi theo Spring Cloud/Spring Boot version.

## 18. Checklist hoàn thành

- [ ] Giải thích được DiscoveryClientHealthIndicator kiểm tra gì.
- [ ] Phân biệt indicator đơn lẻ với DiscoveryCompositeHealthContributor.
- [ ] Phân biệt DiscoveryCompositeHealthContributor với CompositeDiscoveryClient.
- [ ] Biết các điều kiện auto-configuration của blocking indicator.
- [ ] Giải thích được trạng thái UNKNOWN trước initialization event.
- [ ] Hiểu vai trò của InstanceRegisteredEvent.
- [ ] Biết getServices thành công có thể trả UP dù danh sách rỗng.
- [ ] Phân biệt use-services-query=true và false.
- [ ] Hiểu default probe có thể vẫn gọi getServices.
- [ ] Cấu hình include-description và hiểu default false.
- [ ] Cấu hình health-indicator.enabled.
- [ ] Cấu hình composite-indicator.enabled.
- [ ] Phân biệt tắt indicator, tắt composite và tắt toàn bộ discovery.
- [ ] Đọc được component tree trong /actuator/health.
- [ ] Hiểu status aggregation và HTTP status mapping.
- [ ] Phân biệt discovery health với readiness và liveness.
- [ ] Nhận biết reactive health contributor là nhánh riêng.
- [ ] Có test cho UNKNOWN, UP, DOWN, empty service list và probe.
- [ ] Có test cho composite child status và các property bật/tắt.
- [ ] Bảo vệ health details và theo dõi chi phí health polling.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClientHealthIndicator, DiscoveryCompositeHealthContributor và các property bật/tắt.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): default của health-indicator, composite-indicator, include-description và use-services-query.
- [DiscoveryClientHealthIndicator source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/health/DiscoveryClientHealthIndicator.java): initialization event, getServices/probe và status.
- [CommonsClientAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java): điều kiện tạo blocking health indicator và composite contributor.
- [ReactiveCommonsClientAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ReactiveCommonsClientAutoConfiguration.java): reactive discovery health contributor.
- [Spring Boot Actuator – Health Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): show-details, show-components, status aggregation và HTTP mapping.

Health indicator là tín hiệu vận hành có giới hạn. Hãy kiểm tra response thực tế, child contributors và hành vi provider trong môi trường kiểm thử; sau đó chọn readiness/liveness policy phù hợp với khả năng phục vụ của ứng dụng khi registry gặp sự cố.

