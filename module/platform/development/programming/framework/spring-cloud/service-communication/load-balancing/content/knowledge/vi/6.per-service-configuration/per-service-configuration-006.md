# Đối chiếu thuộc tính được hỗ trợ theo Release Train đang dùng

Trong module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`, Spring Cloud LoadBalancer thực hiện cân bằng tải phía client: nhận một **service ID**, lấy các `ServiceInstance` từ cơ chế discovery, có thể lọc theo health check hoặc chính sách định tuyến, rồi chọn instance để `RestClient`, `WebClient` hay OpenFeign gửi request. Khi cấu hình khác nhau cho từng dịch vụ, một câu hỏi quan trọng xuất hiện: **thuộc tính mà ta định dùng có thực sự được Spring Cloud Release Train của ứng dụng hỗ trợ hay không?**

Ví dụ, `order-service` gọi `inventory-service` và `payment-service`. Ta muốn `inventory-service` kiểm tra sức khỏe thường xuyên hơn, còn `payment-service` có chính sách retry chặt chẽ hơn. Việc đặt một khóa vào `application.yml` chưa chứng minh khóa đó được phiên bản thư viện hiện tại nhận diện hoặc cơ chế tương ứng đã được kích hoạt.

Bài này cung cấp phương pháp đối chiếu theo phiên bản, phân biệt phạm vi global/per-client, kiểm tra các ngoại lệ quan trọng và thực hành xác minh cấu hình có hiệu lực. Không có một bảng thuộc tính bất biến dùng được cho mọi Spring Cloud Release Train: hãy lấy **phiên bản dependency thực tế được resolve** làm mốc kiểm chứng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định Spring Boot, Spring Cloud Release Train và phiên bản `spring-cloud-commons`/`spring-cloud-loadbalancer` của ứng dụng.
2. Tìm đúng trang tài liệu tham khảo và danh mục configuration properties ứng với phiên bản đó.
3. Phân loại thuộc tính global, thuộc tính có thể override theo `clientId`, thuộc tính dạng map theo service ID và tính năng cần cấu hình bằng Java.
4. Đối chiếu sự khác biệt giữa các nhánh Spring Cloud Commons 4.1, 4.2, 4.3 và 5.0 thay vì sao chép cấu hình giữa các dự án.
5. Chứng minh cấu hình được bind và thực sự tác động lên hành vi discovery, health check, retry, cache, lựa chọn instance và quan sát lỗi.

## 1. Chốt đúng bộ phiên bản trước khi đọc tài liệu

**Spring Cloud Release Train** là tập hợp các phiên bản dự án Spring Cloud được phát hành và quản lý tương thích cùng nhau. Spring Cloud LoadBalancer được phát hành trong hệ sinh thái Spring Cloud Commons; vì vậy cần xem cả Release Train và phiên bản artifact đang chạy.

Các nhánh thường gặp để đối chiếu:

| Spring Cloud Release Train | Thế hệ Spring Boot tương thích | Nhánh Spring Cloud Commons để tra tài liệu | Ghi chú |
|---|---|---|---|
| `2023.0.x` (Leyton) | `3.2.x`, `3.3.x` theo các mốc service release được công bố | `4.1.x` | Dùng tài liệu Commons nhánh `4.1`, không lấy mặc định từ trang latest |
| `2024.0.x` (Moorgate) | `3.4.x` | `4.2.x` | Tra tài liệu và configprops nhánh `4.2` |
| `2025.0.x` (Northfields) | `3.5.x` | `4.3.x` | Tra tài liệu và configprops nhánh `4.3` |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` từ `2025.1.2` trở đi | `5.0.x` | Tra tài liệu và configprops nhánh `5.0` |

Bảng này dùng để **định hướng nhánh tài liệu**. Phải xác nhận version chính xác bằng dependency resolution; không giả định mọi patch version của Boot đều đi kèm mọi patch version Spring Cloud. Tình trạng hỗ trợ và bản phát hành mới cũng thay đổi theo thời gian. Kiểm tra danh sách tương thích và lịch sử phát hành tại [Spring Cloud project](https://spring.io/projects/spring-cloud/) trước khi nâng cấp.

### 1.1. Kiểm tra file khai báo phụ thuộc

Với Maven, tìm BOM Spring Cloud trong `pom.xml` hoặc dependency management của parent:

```xml
<properties>
    <!-- Giá trị minh họa: thay bằng Release Train của dự án -->
    <spring-cloud.version>2025.0.x</spring-cloud.version>
</properties>

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
```

`2025.0.x` trong ví dụ trên chỉ là ký hiệu **nhánh phiên bản**, không phải giá trị version hợp lệ để copy vào build. Trong dự án thật, thay nó bằng một bản phát hành cụ thể có tồn tại, ví dụ `2025.0.1` nếu đã được chọn theo chính sách nâng cấp của nhóm.

Trong Gradle, tìm BOM hoặc cấu hình tương đương, ví dụ `mavenBom "org.springframework.cloud:spring-cloud-dependencies:<version>"` khi sử dụng Spring dependency-management plugin. Dù khai báo bằng cách nào, hãy kiểm tra các artifact đã được giải quyết thực tế vì một dependency trực tiếp hoặc cấu hình quản lý version khác có thể ghi đè kết quả mong đợi.

### 1.2. Kiểm tra dependency đã resolve

Ví dụ lệnh trong terminal dự án Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-commons,org.springframework.cloud:spring-cloud-loadbalancer
./mvnw help:effective-pom
```

Ví dụ với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
```

Nếu dự án không có Maven/Gradle Wrapper, dùng công cụ build đã cài trong máy. Ghi lại version cụ thể, chẳng hạn `spring-cloud-commons:4.3.z` và `spring-cloud-loadbalancer:4.3.z`, thay vì chỉ ghi “Spring Cloud 2025”. Cần xác minh cả hai vì cấu hình LoadBalancer liên quan đến lớp properties và các thành phần tự động cấu hình của Commons và LoadBalancer.

## 2. Tra đúng nguồn và xếp mức độ tin cậy

Nên kiểm tra theo thứ tự sau:

1. **Tài liệu chính thức đúng nhánh**: mô tả cách sử dụng tính năng, phạm vi áp dụng và điều kiện cần để nó có hiệu lực.
2. **Configuration Properties cùng nhánh**: xác nhận tên khóa, kiểu giá trị, mô tả và default được sinh từ metadata của phiên bản thư viện.
3. **Artifact và mã nguồn đúng tag đã resolve**: đối chiếu `@ConfigurationProperties`, `LoadBalancerProperties`, auto-configuration hoặc mã sử dụng thuộc tính nếu tài liệu chưa rõ.
4. **Kết quả chạy ứng dụng**: xác nhận thuộc tính được bind và có hành vi tương ứng. Đây là bằng chứng quyết định cho môi trường hiện tại.

Các trang chính thức để mở trực tiếp:

| Nhánh Commons | LoadBalancer reference | Configuration Properties |
|---|---|---|
| `4.1` | [LoadBalancer 4.1](https://docs.spring.io/spring-cloud-commons/reference/4.1/spring-cloud-commons/loadbalancer.html) | [Configprops 4.1](https://docs.spring.io/spring-cloud-commons/reference/4.1/configprops.html) |
| `4.2` | [LoadBalancer 4.2](https://docs.spring.io/spring-cloud-commons/reference/4.2/spring-cloud-commons/loadbalancer.html) | [Configprops 4.2](https://docs.spring.io/spring-cloud-commons/reference/4.2/configprops.html) |
| `4.3` | [LoadBalancer 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/loadbalancer.html) | [Configprops 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/configprops.html) |
| `5.0` | [LoadBalancer của bản ổn định hiện tại](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html) | [Configprops của bản ổn định hiện tại](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) |

Tại thời điểm đối chiếu, các liên kết `/reference/` không kèm version đang hiển thị Spring Cloud Commons **5.0.4**. Chúng có thể chuyển sang nhánh mới trong tương lai, nên phải đọc **version hiển thị ở đầu trang** trước khi sử dụng và chọn nguồn theo artifact/version đã resolve nếu đầu trang không còn là `5.0.x`. Đừng xem trang latest là bằng chứng cho một dự án đang dùng nhánh cũ. Không dùng tài liệu milestone, release candidate hoặc snapshot để mặc định kết luận về bản GA đã triển khai.

### 2.1. Cách đọc một thuộc tính từ tài liệu

Với mỗi khóa, ghi đủ bốn yếu tố:

| Câu hỏi | Thông tin cần xác nhận | Ví dụ |
|---|---|---|
| **Có tồn tại?** | Khóa có trong configprops hoặc metadata của artifact đang dùng không? | `spring.cloud.loadbalancer.health-check.interval` |
| **Phạm vi?** | Toàn cục, override theo `clients.<id>`, hay map dùng service ID? | `clients.inventory-service.health-check.interval` |
| **Điều kiện kích hoạt?** | Tính năng cần dependency/bean/supplier/HTTP client nào? | `HealthCheckServiceInstanceListSupplier` |
| **Cách kiểm chứng?** | Log, metric, thời gian, response hoặc danh sách instance thay đổi ra sao? | Chu kỳ health check được điều chỉnh |

Một khóa xuất hiện trong metadata mới chỉ xác nhận **có cơ chế bind**. Nếu service chưa có `HealthCheckServiceInstanceListSupplier`, đặt `health-check.interval` sẽ không tự động khiến hệ thống kiểm tra sức khỏe định kỳ. Tương tự, có `retry.max-retries-*` trong YAML không đồng nghĩa retry chắc chắn xảy ra nếu cơ chế retry hoặc dependency yêu cầu chưa có.

## 3. Phân biệt global và per-client trước khi cấu hình

Với các nhánh nêu trên, cú pháp thông thường cho cấu hình theo dịch vụ là:

```text
spring.cloud.loadbalancer.<property>                   # Giá trị chung
spring.cloud.loadbalancer.clients.<clientId>.<property> # Giá trị riêng
```

`<clientId>` là **tên LoadBalancer client**, thường chính là service ID mà `RestClient`, `WebClient` hoặc OpenFeign sử dụng, ví dụ `inventory-service`. Giá trị chung được kết hợp với cấu hình riêng và cấu hình riêng được ưu tiên khi thuộc tính hỗ trợ override. Mỗi service ID có LoadBalancer context riêng; trong thực tế context thường được khởi tạo khi phát sinh yêu cầu đầu tiên tới service đó.

### 3.1. Các ngoại lệ global quan trọng

Đây là nhóm cần kiểm tra đặc biệt trong tài liệu **Configuring Individual LoadBalancerClients**:

| Thuộc tính | Phạm vi / giới hạn | Điều dễ nhầm |
|---|---|---|
| `spring.cloud.loadbalancer.enabled` | Công tắc bật/tắt LoadBalancer **toàn cục** | Không thể bật riêng một client khi LoadBalancer bị vô hiệu hóa toàn bộ |
| `spring.cloud.loadbalancer.retry.enabled` | Cờ cho phép retry **toàn cục**; nếu global bật, có thể vô hiệu retry cho client cụ thể, nhưng global tắt thì client không tự bật ngược lại được | Đặt `clients.payment-service.retry.enabled=true` không vượt qua `retry.enabled=false` toàn cục |
| `spring.cloud.loadbalancer.cache.enabled` | Công tắc cache **toàn cục**; khi cache global bật, muốn loại cache khỏi client riêng thường cần cấu hình supplier riêng không sử dụng `CachingServiceInstanceListSupplier` | Không coi `clients.inventory-service.cache.enabled=false` là công tắc độc lập đáng tin cậy |
| `spring.cloud.loadbalancer.stats.micrometer.enabled` | Công tắc đo metric LoadBalancer **toàn cục** | Muốn metric chỉ cho một client cần giải pháp lọc/quan sát khác; không giả định có thể bật global=false rồi bật riêng client |

Với retry, việc cấu hình các con số `max-retries-on-same-service-instance` hoặc `max-retries-on-next-service-instance` theo client vẫn có ý nghĩa **khi retry đã được bật trên toàn ứng dụng và stack tương ứng hỗ trợ retry**. Phạm vi của các thông số này khác phạm vi của công tắc `retry.enabled`.

### 3.2. Các thuộc tính thường cấu hình riêng được

Những nhóm sau được mô tả trong các nhánh tài liệu đã liên kết; khi sử dụng vẫn cần xem metadata và điều kiện áp dụng của đúng bản thư viện:

| Nhóm | Ví dụ thuộc tính | Ý nghĩa / điều kiện |
|---|---|---|
| Health check | `health-check.initial-delay`, `health-check.interval`, `health-check.refetch-instances` | Điều chỉnh lịch hoặc cách cập nhật của supplier health check; supplier phải được cấu hình |
| Retry | `retry.max-retries-on-same-service-instance`, `retry.max-retries-on-next-service-instance`, `retry.retryable-status-codes` | Giới hạn lần thử và xác định lỗi được retry; phải xét global enable, retry implementation và idempotency |
| Retry reactive | `retry.backoff.enabled`, `retry.backoff.min-backoff`, `retry.backoff.max-backoff`, `retry.backoff.jitter` | Có ý nghĩa với cơ chế backoff reactive được hỗ trợ; không suy ra RestClient và Feign dùng chung hành vi |
| Instance selection | `zone`, `hint`, `subset.size` | Chỉ có tác dụng khi đúng supplier/chính sách nhận giá trị tương ứng |
| Caching | `cache.ttl`, `cache.capacity` | Điều chỉnh cache nếu cache được bật và cơ chế cache đang sử dụng đọc các thông số này |
| Discovery | `service-discovery.timeout` | Thời gian chờ lấy thông tin từ discovery, **không phải** timeout HTTP tới instance đích |

Đặc biệt, `health-check.path` và `hint` có dạng **map theo service ID** được tài liệu duy trì cho tương thích ngược:

```yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness
      hint:
        inventory-service: warehouse-a
```

Đoạn trên minh họa cú pháp map của các nhánh tài liệu đã đối chiếu. Nó không có nghĩa ứng dụng tự động chọn instance theo hint: phải cấu hình supplier xử lý hint; `inventory-service` cần có metadata `hint` tương ứng hoặc logic lựa chọn phù hợp. Khi nâng major version, ưu tiên kiểm tra lại cách bind các map này trong tài liệu và mã nguồn đúng bản sử dụng.

### 3.3. Thuộc tính cấu hình không thay thế được Java configuration

Ví dụ sau là **không có căn cứ** nếu không tìm thấy property tương ứng trong metadata:

```yaml
# KHÔNG sử dụng nếu chỉ tự suy ra tên khóa
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          algorithm: random
```

Để đổi `RoundRobinLoadBalancer` sang `RandomLoadBalancer` cho riêng `inventory-service`, tham khảo cơ chế `@LoadBalancerClient(name = "inventory-service", configuration = ...)` và khai báo `ReactorLoadBalancer<ServiceInstance>` phù hợp. Cấu hình bằng annotation/bean và cấu hình bằng `@ConfigurationProperties` là **hai con đường khác nhau**; không được suy rằng mọi lựa chọn trong Java đều có một khóa YAML cùng tên.

Tương tự, các giá trị `connect-timeout` hay `response-timeout` dành cho `RestClient`, `WebClient` hoặc OpenFeign thường thuộc HTTP transport/client cụ thể. Không tự tạo `spring.cloud.loadbalancer.clients.<id>.connect-timeout` rồi xem như đã cấu hình timeout tới instance. Cần đọc tài liệu timeout của đúng HTTP client đang dùng.

## 4. Bảng đối chiếu mẫu giữa các nhánh Commons

Quy ước: **Có** nghĩa là khóa/nhóm có mặt trong danh mục thuộc tính của nhánh được kiểm tra; **Chưa thấy** nghĩa là danh mục đó không liệt kê và phải xác minh trước khi sử dụng. Ký hiệu này không thay thế việc đọc mã nguồn đúng patch version hoặc kiểm thử hành vi thực tế.

| Nhóm thuộc tính | Commons 4.1 | Commons 4.2 | Commons 4.3 | Commons 5.0 | Kết luận sử dụng |
|---|---|---|---|---|---|
| `health-check.interval` | Có | Có | Có | Có | Xác minh supplier health check đã được kích hoạt |
| `health-check.path` | Có | Có | Có | Có | Kiểm tra cú pháp map theo service ID và endpoint health |
| `retry.enabled` | Có | Có | Có | Có | Nhớ giới hạn global và khả năng tắt theo client |
| `retry.max-retries-on-next-service-instance` | Có | Có | Có | Có | Kiểm tra thư viện retry và loại HTTP client |
| `retry.backoff.*` | Có | Có | Có | Có | Chỉ kỳ vọng backoff khi cơ chế retry tương ứng hỗ trợ |
| `cache.enabled`, `cache.ttl` | Có | Có | Có | Có | Phân biệt enable global và cấu hình cache cụ thể |
| `stats.micrometer.enabled` | Có | Có | Có | Có | Cần `MeterRegistry` và công tắc global |
| `call-get-with-request-on-delegates` | Có | Có | Có | Có | Kiểm tra cách supplier nhận `Request` và thứ tự delegate |
| `service-discovery.timeout` | Có | Có | Có | Có | Chỉ áp dụng cho hoạt động discovery, không thay HTTP timeout |
| `api-version.*` | Chưa thấy | Chưa thấy | Chưa thấy | Có | Tính năng phụ thuộc nhánh; không copy cấu hình 5.0 sang 4.x nếu chưa kiểm chứng |

Một khác biệt đáng chú ý là nhóm `spring.cloud.loadbalancer.api-version.*`: danh mục Spring Cloud Commons `5.0` liệt kê các khóa như `header`, `query-parameter`, `path-segment`, `required` và `fallback-to-available-instances`, trong khi danh mục `4.1`, `4.2`, `4.3` được đối chiếu không liệt kê nhóm này. Tài liệu LoadBalancer `5.0` cũng mô tả các supplier chọn instance theo API version. Đây là ví dụ thực tế vì sao cần ghim tài liệu theo Release Train.

**Cảnh báo khi đối chiếu:** “có trong configprops” và “dùng được theo client” là hai cột thông tin khác nhau. `retry.enabled` có trong cả bốn nhánh nhưng là công tắc có giới hạn global; `health-check.interval` có thể override theo client nhưng chỉ phát huy khi health-check supplier có mặt. Đừng đánh dấu thuộc tính là “đã chạy đúng” chỉ vì nó tồn tại trong danh mục.

## 5. Ví dụ cấu hình hai service trong cùng ứng dụng

Giả sử `order-service` dùng hai service ID `inventory-service` và `payment-service`. Ví dụ dưới đây minh họa cách kết hợp giá trị chung với override theo client trên các nhánh Commons được đối chiếu:

```yaml
spring:
  cloud:
    loadbalancer:
      enabled: true

      # Bật khả năng retry ở mức toàn cục.
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1

      # Giá trị dùng chung; chỉ có tác dụng khi có HealthCheck supplier.
      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness

      # Phần override theo tên LoadBalancer client / service ID.
      clients:
        inventory-service:
          health-check:
            interval: 10s
          retry:
            enabled: false

        payment-service:
          health-check:
            interval: 30s
          retry:
            max-retries-on-same-service-instance: 0
            max-retries-on-next-service-instance: 0
```

Giải thích cách đọc, với điều kiện phiên bản và cơ chế thực thi hỗ trợ:

| Thành phần | Giá trị mong đợi từ cấu hình | Điều kiện kiểm chứng |
|---|---|---|
| `inventory-service` | `health-check.initial-delay=1s`, `health-check.interval=10s` | Supplier health check của service này phải có mặt; endpoint `/actuator/health/readiness` phải khả dụng |
| `payment-service` | `health-check.initial-delay=1s`, `health-check.interval=30s` | Cùng điều kiện có supplier health check; nếu không có override path, dùng path mặc định |
| Retry của `inventory-service` | Bị tắt riêng, dù global retry bật | Kiểm thử bằng lỗi có khả năng retry và đối chiếu số lần attempt |
| Retry của `payment-service` | Giới hạn cả retry trên instance cũ lẫn instance mới về `0` | Phải xét thêm retry implementation; xác nhận bằng log số request thực tế |

Kịch bản này **không** tự cài đặt health check. Nếu muốn kiểm tra sức khỏe theo chu kỳ, cần tạo hoặc lựa chọn cấu hình có `HealthCheckServiceInstanceListSupplier` (ví dụ dùng `ServiceInstanceListSupplier.builder().withDiscoveryClient().withHealthChecks()` với stack phù hợp). Nếu dùng discovery registry đã cung cấp trạng thái health và không cần health supplier độc lập, không nên bật thêm health check chỉ để thấy khóa `interval` hoạt động.

### 5.1. Phản ví dụ: bật retry theo client khi global tắt

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        payment-service:
          retry:
            enabled: true
```

Theo giới hạn global được mô tả trong tài liệu, cấu hình trên **không mở lại retry** cho `payment-service`. Nếu mục tiêu là cho một số client retry và một số client không retry, đặt global `retry.enabled=true`, sau đó tắt ở các client cần loại trừ và kiểm chứng cơ chế retry bằng thử nghiệm thực tế.

### 5.2. Phản ví dụ: cố bật cache cho một client khi global tắt

```yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
      clients:
        inventory-service:
          cache:
            enabled: true
```

Không được kết luận client `inventory-service` đã có cache riêng từ cấu hình này. Theo tài liệu, công tắc cache là global; muốn dùng cấu hình supplier khác nhau theo dịch vụ, phải xây dựng `ServiceInstanceListSupplier` cho từng client và kiểm chứng cache delegate được tạo đúng cách. Tác dụng của `cache.ttl` cũng cần xét cơ chế cache thực tế và việc discovery có tự cache hay không.

## 6. Quy trình thực hành đối chiếu và kiểm chứng

### Bước 1 — Lập hồ sơ phiên bản

Từ một ứng dụng Spring Boot có `spring-cloud-starter-loadbalancer`, ghi lại:

- Spring Boot version chính xác.
- Spring Cloud BOM version chính xác.
- `spring-cloud-commons` và `spring-cloud-loadbalancer` đã resolve.
- Kiểu gọi đang dùng: `RestClient`, `WebClient`, OpenFeign; phiên bản và dependency retry nếu có.
- Discovery implementation: Eureka, Consul, Kubernetes, `SimpleDiscoveryClient` hoặc custom supplier.

Ví dụ phiếu kiểm tra:

```text
Application: order-service
Spring Boot: 3.5.z
Spring Cloud BOM: 2025.0.z
spring-cloud-commons: 4.3.z
spring-cloud-loadbalancer: 4.3.z
HTTP clients: RestClient + WebClient + OpenFeign
Service IDs: inventory-service, payment-service
Tài liệu đối chiếu: Spring Cloud Commons 4.3
```

Các ký hiệu `z` trong phiếu là chỗ điền patch version thực tế, không phải version literal để khai báo trong build.

### Bước 2 — Chọn danh sách khóa cần kiểm tra

Chỉ lấy các khóa ảnh hưởng tới yêu cầu. Ví dụ:

```text
spring.cloud.loadbalancer.enabled
spring.cloud.loadbalancer.clients.inventory-service.health-check.interval
spring.cloud.loadbalancer.clients.inventory-service.retry.enabled
spring.cloud.loadbalancer.clients.payment-service.retry.max-retries-on-next-service-instance
spring.cloud.loadbalancer.health-check.path.inventory-service
spring.cloud.loadbalancer.cache.enabled
spring.cloud.loadbalancer.stats.micrometer.enabled
```

Với từng khóa, kiểm tra sự tồn tại, kiểu giá trị, default, phạm vi cấu hình và phụ thuộc chức năng. Không lấy tên khóa bằng cách suy luận từ một đối tượng Java hoặc từ một thư viện khác.

### Bước 3 — Đối chiếu trang configprops và tài liệu hành vi

Tìm **tên khóa gốc** trong trang configprops. Sau đó đọc phần **Configuring Individual LoadBalancerClients** để xác định việc thêm `clients.<clientId>` có được hỗ trợ hay thuộc trường hợp ngoại lệ. Cuối cùng đọc phần tài liệu của tính năng như **Instance Health-Check**, **Caching**, **Retry** hoặc **Hint-Based Load-Balancing** để biết khi nào property có tác dụng.

Ví dụ, đối với `health-check.interval`, trang configprops cho biết giá trị và default; phần health-check xác nhận cần có `HealthCheckServiceInstanceListSupplier`. Đối với `stats.micrometer.enabled`, ngoài property còn cần `MeterRegistry` phù hợp. Đối với `retry.*`, cần kiểm tra retry implementation đã hoạt động cho stack client, sự kiện nào được retry và giới hạn tổng số lần gọi.

### Bước 4 — Kiểm chứng cấu hình được bind

Khi bật Spring Boot Actuator trong môi trường lab, có thể dùng endpoint `configprops` để xem các bean `@ConfigurationProperties` đã bind; `env` giúp xác định nguồn giá trị nếu cần. Chỉ mở các endpoint này cho môi trường phát triển hoặc kênh truy cập được bảo vệ; cấu hình cần tránh lộ secret.

Các child context của từng LoadBalancer client có thể được tạo **lười** ở lần gọi đầu tiên. Vì vậy, nếu chưa thấy bean/cấu hình riêng trong bước kiểm tra ban đầu, hãy gọi service đó một lần, rồi kiểm tra lại theo cơ chế của phiên bản đang dùng. Nếu Actuator không trình bày đầy đủ giá trị riêng của child context, dùng log hoặc kiểm thử hành vi để xác nhận, không kết luận property bị bỏ qua chỉ vì một màn hình thiếu dữ liệu.

### Bước 5 — Kiểm chứng hành vi thực tế

Thực hiện lần lượt các bài test có kiểm soát:

| Thử nghiệm | Dữ liệu vào | Bằng chứng kỳ vọng |
|---|---|---|
| Override health interval | `inventory-service=10s`, `payment-service=30s` | Khi health supplier được bật, lịch/nhật ký health check khác nhau như cấu hình |
| Global retry disabled | `retry.enabled=false`; client đặt `true` | Không có retry do LoadBalancer phát sinh |
| Global retry enabled, một client disabled | Global `true`; `inventory-service` `false` | Một request lỗi tới inventory không được retry bởi LoadBalancer; client khác tuân theo cấu hình riêng |
| Retry count | `payment-service.retry.max-retries-on-next-service-instance=0` | Số lần attempt phù hợp với giới hạn và chính sách hiện tại |
| Discovery stale entry | Dừng một instance, giữ discovery/cached list cũ trong thời gian ngắn | Log lỗi, cache/health check và thời điểm instance bị loại được đối chiếu |
| API version trên nhánh cũ | Đặt khóa `api-version.*` theo ví dụ của 5.0 vào dự án Commons 4.x | Không tự giả định property được hỗ trợ; kiểm tra metadata và hành vi, hoặc không dùng tính năng |

Khi thử retry, ưu tiên endpoint `GET` đọc dữ liệu và mô phỏng lỗi tạm thời. Tránh thử tự động lại thao tác ghi không idempotent vì có thể tạo trùng giao dịch. Khi quan sát timeout, kiểm tra timeout của client HTTP và thời gian chờ discovery riêng biệt để tránh quy lỗi nhầm cho LoadBalancer.

### Bước 6 — Ghi kết quả đối chiếu thành bảng cho nhóm

Một mẫu hữu ích để lưu cùng quyết định cấu hình:

| Thuộc tính yêu cầu | Artifact/version đã kiểm tra | Có trong configprops? | Scope | Điều kiện kích hoạt | Bằng chứng runtime | Quyết định |
|---|---|---|---|---|---|---|
| `health-check.interval` | `spring-cloud-commons:4.3.z` | Có | Có thể override per-client | Health check supplier | Thời gian các lần probe | Dùng |
| `retry.enabled` | `spring-cloud-commons:4.3.z` | Có | Global; có thể tắt riêng client | Retry implementation | Số lần attempt | Giữ global bật, tắt chọn lọc |
| `api-version.header` | `spring-cloud-commons:4.3.z` | Chưa thấy | Chưa kết luận | Phải đối chiếu tính năng theo nhánh | Chưa có | Không đưa vào cấu hình 4.3 khi chưa có bằng chứng |

Bảng trên chỉ là mẫu minh họa cho nhánh 4.3; thay `z` và điền kết quả runtime thật khi thực hiện trên dự án. Cột “Quyết định” nên nêu rõ khóa được dùng, thay bằng Java configuration hay tạm loại bỏ vì chưa có bằng chứng hỗ trợ.

## 7. Tình huống thường gây nhầm lẫn khi nâng Release Train

### 7.1. Đọc tài liệu latest rồi copy vào dự án cũ

Nhóm phát triển thấy tài liệu Commons 5.0 có `spring.cloud.loadbalancer.api-version.header` và thêm ngay vào ứng dụng đang dùng Commons 4.3. Ứng dụng có thể vẫn khởi động, nhưng điều đó không chứng minh API version-based instance selection đã được bật. Cách xử lý: dùng trang configprops 4.3 và mã nguồn 4.3 để xác nhận; nếu cần tính năng chỉ có trong nhánh sau, lên kế hoạch nâng cấp phù hợp thay vì để một khóa không có hiệu lực trong YAML.

### 7.2. Cấu hình health check nhưng không tạo health-check supplier

Thiết lập `spring.cloud.loadbalancer.clients.inventory-service.health-check.interval=10s` là thao tác cấu hình giá trị. Health check định kỳ cần `HealthCheckServiceInstanceListSupplier` hoặc cấu hình dựng supplier tương ứng. Nếu ứng dụng chỉ dùng supplier discovery mặc định và không bật health check, không có lịch probe để thay đổi. Kiểm tra bean và chuỗi delegate trước khi tăng/giảm interval.

### 7.3. Nhầm service ID với tên bean hoặc tên ứng dụng caller

Đường dẫn `clients.inventory-service` áp dụng cho LoadBalancer client gọi `inventory-service`. Nó không được xác định theo `spring.application.name` của `order-service`. Nếu OpenFeign dùng `@FeignClient(name = "inventory-service")`, thì tên đó cần khớp với ID đang cấu hình. Tên tùy ý như `clients.order-service` sẽ không ảnh hưởng đến lời gọi inventory nếu LoadBalancer chọn theo service ID khác.

### 7.4. Nhầm retry của Spring Cloud LoadBalancer với retry của thư viện khác

OpenFeign, Spring Retry, Reactor, HTTP client và các thư viện resilience có thể có cấu hình retry riêng. Cần kiểm tra request được retry ở lớp nào, có xảy ra retry chồng nhau không và tổng số attempt là bao nhiêu. Việc đổi `spring.cloud.loadbalancer.retry.max-retries-on-next-service-instance` không bảo đảm mọi cơ chế retry khác cũng thay đổi theo.

### 7.5. Nhầm timeout của discovery với timeout của HTTP request

`spring.cloud.loadbalancer.service-discovery.timeout` liên quan đến việc gọi service discovery; nó không trực tiếp thay thế connect/read/response timeout của `RestClient`, `WebClient` hoặc OpenFeign. Khi một request chậm, đo riêng thời gian lấy danh sách instance, lựa chọn instance, kết nối và phản hồi của server.

### 7.6. Hiểu sai phạm vi của metric

`spring.cloud.loadbalancer.stats.micrometer.enabled` là công tắc global. Để xem số request lỗi tới từng service/instance, cần `MeterRegistry`, metric thực sự được phát sinh và các tag phù hợp. Đừng mặc định một thuộc tính `clients.<id>.stats.micrometer.enabled=true` có thể bật metric cho client riêng khi global tắt. Khi dữ liệu metric thiếu, kiểm tra instrumentation và cấu hình quan sát trước khi kết luận request không đi qua LoadBalancer.

## 8. Bài thực hành tổng hợp: quyết định thuộc tính nào được phép dùng

**Bối cảnh:** hai môi trường chạy `order-service`. Môi trường A dùng Spring Cloud `2024.0.x`/Commons `4.2.x`, môi trường B dùng Spring Cloud `2025.1.x`/Commons `5.0.x`. Cả hai đều gọi `inventory-service` và `payment-service` bằng `RestClient`, `WebClient` hoặc OpenFeign qua service ID.

Yêu cầu bài thực hành:

1. Ghi lại patch version chính xác của mỗi môi trường qua công cụ quản lý dependency.
2. Mở trang configprops và LoadBalancer reference tương ứng `4.2` và `5.0`; lập bảng cho `health-check.interval`, `retry.enabled`, `retry.max-retries-on-next-service-instance`, `cache.enabled`, `stats.micrometer.enabled` và `api-version.*`.
3. Đánh dấu phạm vi global/per-client/map của từng khóa, kèm điều kiện để nó có hiệu lực.
4. Dùng một service gọi bằng `RestClient`, một bằng `WebClient` hoặc Feign để xác nhận service ID được dùng làm `clientId` cấu hình. Ghi log instance ID của từng request.
5. Cấu hình global retry bật, disable retry cho `inventory-service` và giới hạn retry của `payment-service`. Quan sát số attempt khi endpoint GET báo lỗi tạm thời.
6. Nếu có health-check supplier, điều chỉnh interval hai client khác nhau và kiểm tra thời điểm phát sinh probe. Nếu không có supplier, bổ sung đúng cấu hình trước khi kiểm thử.
7. Với `api-version.*`, chỉ dùng trong môi trường B sau khi xác minh implementation và dependency yêu cầu; ghi nhận lý do không sao chép trực tiếp sang môi trường A.
8. Đối chiếu log, metric và thời gian phản hồi; viết một đoạn quyết định về các khóa nên giữ, bỏ hoặc thay bằng Java configuration.

**Tiêu chí hoàn thành:** mỗi khóa được lựa chọn có nguồn tài liệu đúng nhánh, phạm vi cấu hình xác định, dependency/supplier phù hợp và một bằng chứng runtime. Với khóa chưa có trong bản đang chạy, phải ghi “chưa được xác minh hỗ trợ” và không dùng chỉ dựa vào tài liệu của phiên bản mới hơn.

## 9. Checklist trước khi đưa cấu hình vào môi trường thật

- [ ] Đã xác nhận Spring Boot, Spring Cloud BOM và phiên bản artifact đã resolve.
- [ ] Đã dùng đúng trang LoadBalancer reference và configprops tương ứng với nhánh Commons.
- [ ] Đã kiểm tra khóa thuộc global, per-client hoặc map theo service ID.
- [ ] Đã xem các ngoại lệ của `enabled`, `retry.enabled`, `cache.enabled`, `stats.micrometer.enabled`.
- [ ] Đã xác minh supplier cần thiết cho health check, hint, zone hoặc chính sách lựa chọn tùy chỉnh.
- [ ] Đã kiểm tra dependency/implementation retry theo loại client và giới hạn tổng số attempt.
- [ ] Đã tách timeout discovery khỏi HTTP transport timeout.
- [ ] Đã kiểm tra `clients.<clientId>` khớp service ID gọi thực tế.
- [ ] Đã thử cả trường hợp instance khỏe, instance lỗi và không có instance phù hợp.
- [ ] Đã lưu bảng bằng chứng: version, tài liệu, property, scope và kết quả chạy.

## Tài liệu tham khảo chính thức

- [Spring Cloud — Compatibility và Release Train](https://spring.io/projects/spring-cloud/).
- [Spring Cloud Commons 4.1 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.1/configprops.html) và [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.1/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 4.2 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.2/configprops.html) và [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.2/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.3/configprops.html) và [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 5.0.4 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) và [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html) (kiểm tra version hiển thị ở đầu trang vì liên kết latest có thể thay đổi).

Điểm cốt lõi của việc đối chiếu thuộc tính là theo dõi **đúng phiên bản, đúng phạm vi, đúng điều kiện kích hoạt và đúng bằng chứng vận hành**. Nhờ đó, cấu hình cân bằng tải theo dịch vụ sẽ có cơ sở kiểm chứng rõ ràng khi kết hợp discovery, health check, chính sách định tuyến, retry/timeout và các loại HTTP client trong hệ thống microservices.
