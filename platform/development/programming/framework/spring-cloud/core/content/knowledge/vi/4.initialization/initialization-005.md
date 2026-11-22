# Bổ sung Actuator và chỉ mở endpoint cần dùng

Trong một hệ thống Spring Boot gồm nhiều dịch vụ, đội phát triển và vận hành cần biết ứng dụng có đang chạy, có sẵn sàng nhận request, đang dùng phiên bản nào và có dấu hiệu lỗi gì. **Spring Boot Actuator** cung cấp các endpoint quản trị và quan sát để trả lời những câu hỏi đó. Tuy nhiên, một endpoint quản trị có thể tiết lộ cấu hình, thông tin runtime hoặc cho phép thay đổi trạng thái ứng dụng. Vì vậy, việc bổ sung Actuator phải đi cùng quyết định **endpoint nào thực sự cần được truy cập, ai được truy cập và truy cập qua mạng nào**.

Bài học thuộc chương **Khởi tạo** của module **SPRING_CLOUD_CORE**. Người học sẽ thêm Actuator vào ứng dụng Spring Boot, cấu hình danh sách endpoint theo nguyên tắc allowlist, bảo vệ dữ liệu health/info, bố trí management port, tích hợp health probe và kiểm tra kết quả trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Actuator cung cấp gì và phân biệt endpoint được bật, được cho phép truy cập và được expose qua HTTP/JMX.
- Thêm `spring-boot-starter-actuator` vào Maven hoặc Gradle mà không tự ghim phiên bản ngoài dependency management của Spring Boot.
- Chỉ expose những endpoint có mục đích rõ ràng bằng `management.endpoints.web.exposure.include`.
- Giới hạn mức truy cập endpoint, bảo vệ endpoint bằng Spring Security và giới hạn đường mạng quản trị.
- Cấu hình health details, liveness/readiness probe và nhận diện nguy cơ khi health check phụ thuộc hệ thống bên ngoài.
- Kiểm tra bằng HTTP, log và integration test để xác nhận endpoint ngoài allowlist không thể truy cập.

## 2. Actuator nằm ở đâu trong ứng dụng Spring Cloud?

Actuator là tính năng của **Spring Boot**. Nó cung cấp một tập endpoint và các abstraction quan sát như `HealthContributor`, `HealthIndicator`, `InfoContributor` và metrics. Các dự án Spring Cloud có thể bổ sung thành phần tích hợp hoặc health indicator của riêng chúng; Actuator là nơi tổng hợp và công bố thông tin đó theo cấu hình của ứng dụng.

Ví dụ, một `order-service` có thể sử dụng Spring Cloud Discovery Client để tìm `inventory-service`. Actuator giúp quan sát tình trạng ứng dụng và các `HealthContributor` hiện diện. Tuy nhiên:

- Thêm Actuator **không tự tạo service registry** và không tự đăng ký dịch vụ.
- Expose `/actuator/health` không có nghĩa mọi chi tiết discovery, cấu hình hay dependency đều được công khai.
- Có health indicator trên classpath không đồng nghĩa indicator đó phải xuất hiện trong mọi health group hoặc được trả chi tiết cho mọi người dùng.
- Actuator không thay thế logging, tracing, metrics backend, alerting hay cơ chế xác thực.

Luồng tổng quát:

~~~mermaid
flowchart LR
    APP[Spring Boot application] --> HC[HealthContributor / InfoContributor]
    APP --> MET[Micrometer metrics]
    HC --> ACT[Spring Boot Actuator]
    MET --> ACT
    ACT --> AUTH[Access control and Security]
    AUTH --> EXP[HTTP / JMX exposure]
    EXP --> OPS[Probe / Monitoring / Operations]
~~~

Các bước **access control**, **exposure** và **security** là những lớp kiểm soát riêng. Một cấu hình tốt cần kiểm tra cả ba.

## 3. Thêm dependency Actuator

Starter chính thức là `org.springframework.boot:spring-boot-starter-actuator`. Phiên bản của starter nên được quản lý bởi Spring Boot parent/BOM hoặc Spring Boot Gradle plugin đã chọn. Không thêm một version tùy ý chỉ cho Actuator.

### 3.1. Maven

Thêm dependency vào `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn trên giả định dự án đã có Spring Boot dependency management. Nếu dự án dùng parent nội bộ, hãy import `spring-boot-dependencies` BOM theo quy ước của dự án để quản lý phiên bản.

### 3.2. Gradle

Với Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Khi ứng dụng dùng Spring Cloud, tiếp tục giữ cặp Spring Boot/Spring Cloud tương thích theo release train đã chọn. Actuator thuộc Spring Boot; không cần một Spring Cloud starter riêng chỉ để tạo endpoint `/actuator/health`.

### 3.3. Chạy thử sau khi thêm starter

Khởi động ứng dụng và gửi request:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Đường dẫn mặc định của HTTP endpoint có dạng `/actuator/{id}`. Nếu ứng dụng web đã expose health endpoint, response thường có trạng thái `UP` khi các health contributor liên quan đều khỏe. Nếu ứng dụng không có web server, Actuator vẫn có thể được dùng qua JMX hoặc các cơ chế quản trị khác.

Chỉ thêm dependency không có nghĩa mọi endpoint đều được expose. Mặc định Spring Boot chỉ expose endpoint `health` qua HTTP và JMX. Đây là điểm xuất phát an toàn để chọn thêm endpoint khi có yêu cầu cụ thể.

## 4. Hiểu ba lớp: access, exposure và xác thực

Một endpoint chỉ có thể được gọi khi endpoint đó sẵn sàng trong ứng dụng, được expose qua giao thức đang dùng và request vượt qua quy tắc bảo mật.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Endpoint access / enablement** | Endpoint có được phép tồn tại và thao tác nào được phép? | `management.endpoint.health.access=read-only` |
| **Exposure** | Endpoint được công bố qua HTTP hay JMX? | `management.endpoints.web.exposure.include=health,info` |
| **HTTP authorization / network security** | Ai được gọi và request có đi qua mạng được phép? | Spring Security role, firewall, management port riêng |

Không nên coi `include=health,info` là cơ chế xác thực. Thuộc tính này chọn endpoint nào có URL, nhưng không tự xác định danh tính người gọi. Tương tự, Spring Security bảo vệ URL không làm cho một endpoint bị loại khỏi exposure.

Ở các phiên bản Spring Boot mới, có thể cấu hình thêm mức truy cập endpoint bằng `management.endpoints.access.*`. Cơ chế này độc lập với danh sách exposure. Khi endpoint không có access được cho phép, nó có thể bị loại khỏi application context.

## 5. Chỉ expose endpoint cần dùng

### 5.1. Bắt đầu với allowlist

Ví dụ `application.yml` cho một dịch vụ nội bộ cần health check và metadata ứng dụng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Khi đó, ứng dụng chỉ công bố hai HTTP endpoint:

| Endpoint | Mục đích | Người/hệ thống tiêu thụ điển hình |
| --- | --- | --- |
| `/actuator/health` | Trạng thái tổng thể của ứng dụng | Orchestrator, load balancer nội bộ, monitoring |
| `/actuator/info` | Metadata đã chọn của ứng dụng/build | Dashboard hoặc đội vận hành |

Các endpoint như `env`, `configprops`, `beans`, `conditions`, `mappings`, `loggers`, `heapdump`, `threaddump` và `shutdown` không nằm trong allowlist trên. Chúng sẽ không được công bố qua HTTP chỉ vì Actuator có khả năng cung cấp chúng.

Nếu hệ thống chỉ cần health probe, cấu hình tối thiểu có thể là:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
~~~

**Không dùng `include: "*"` trong cấu hình production nếu chưa có một lý do cụ thể và biện pháp kiểm soát tương ứng.** Wildcard có thể làm endpoint mới được thêm ở bản nâng cấp trở nên truy cập được mà nhóm vận hành chưa đánh giá.

### 5.2. `exclude` có ưu tiên cao hơn `include`

Có thể dùng `exclude` để chặn một số ID khỏi danh sách được include:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,beans,heapdump,threaddump"
~~~

`exclude` thắng `include`, nhưng cấu hình wildcard vẫn có rủi ro khi dự án bổ sung endpoint mới. Với nhu cầu “chỉ mở endpoint cần dùng”, allowlist tường minh thường dễ review và bảo trì hơn.

Trong YAML, ký tự `*` có ý nghĩa riêng nên phải đặt trong dấu nháy. Không cần dùng wildcard nếu chỉ có vài endpoint đã xác định.

### 5.3. HTTP và JMX là hai cấu hình exposure riêng

`management.endpoints.web.exposure.*` điều khiển HTTP. `management.endpoints.jmx.exposure.*` điều khiển JMX. Không giả định thay đổi allowlist HTTP sẽ tự thay đổi JMX.

Nếu tổ chức không sử dụng JMX để quản trị Actuator, có thể chủ động loại toàn bộ endpoint khỏi JMX:

~~~yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
~~~

Nếu dùng JMX, chỉ include các endpoint cần thiết và bảo vệ JMX theo cơ chế quản trị của JVM/nền tảng. Tránh mở JMX remote cho mạng không tin cậy.

### 5.4. Đường dẫn quản trị

Prefix mặc định là `/actuator`. Có thể đổi prefix:

~~~yaml
management:
  endpoints:
    web:
      base-path: "/management"
      exposure:
        include: "health,info"
~~~

Khi đó, health endpoint là `/management/health`. Đổi tên đường dẫn không phải biện pháp xác thực; người dùng vẫn có thể dò hoặc biết URL từ cấu hình, log hay tài liệu.

Trang discovery liên kết các HTTP endpoint có thể xuất hiện tại `/actuator` (hoặc management base path tương ứng). Nếu không cần trang này, có thể tắt:

~~~yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
~~~

Tắt discovery page không thay đổi quy tắc exposure của các endpoint con.

## 6. Cấu hình endpoint access theo nguyên tắc từ chối mặc định

Ở Spring Boot có hỗ trợ endpoint access control (chẳng hạn các dòng 3.4.x, 3.5.x và 4.x), có thể đặt mặc định `none`, rồi chỉ cấp quyền read-only cho endpoint cần dùng:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
~~~

Ý nghĩa:

- `default: none` từ chối access cho các endpoint không được cấp quyền riêng.
- `health.access: read-only` và `info.access: read-only` cho phép các thao tác đọc của hai endpoint.
- `max-permitted: read-only` đặt trần quyền, ngăn endpoint được cấu hình riêng có mức truy cập cao hơn trần này.
- `exposure.include` vẫn phải chọn endpoint được công bố qua HTTP.

Các giá trị access thường dùng là `none`, `read-only` và `unrestricted`. `read-only` cho phép các thao tác đọc phù hợp với loại endpoint; nó không có nghĩa request không cần xác thực.

**Lưu ý tương thích:** kiểm tra tài liệu đúng phiên bản Spring Boot trước khi dùng `management.endpoints.access.*`. Với các dòng cũ chưa hỗ trợ thuộc tính này, dùng cơ chế enablement/exposure có trong phiên bản đó và bảo vệ URL bằng Spring Security cùng network policy. Không sao chép cấu hình của Boot 4 vào dự án Boot 3.x cũ mà không kiểm tra metadata của configuration properties.

## 7. Bảo vệ endpoint bằng Spring Security

### 7.1. Khi nào Boot tự bảo vệ?

Nếu Spring Security có trên classpath và ứng dụng **không khai báo `SecurityFilterChain` tùy chỉnh**, Spring Boot tự cấu hình bảo vệ các Actuator endpoint ngoại trừ health theo mặc định. Khi ứng dụng định nghĩa một `SecurityFilterChain` bean, cấu hình security tự động của Boot sẽ nhường quyền kiểm soát; nhóm phát triển phải tự viết quy tắc cho cả Actuator và các URL nghiệp vụ.

Vì vậy, không nên thêm một filter chain chỉ dành cho Actuator rồi quên chuỗi bảo vệ phần API chính.

### 7.2. Ví dụ phân quyền endpoint

Ví dụ dưới đây minh họa cách dùng `EndpointRequest` để match endpoint Actuator và yêu cầu role `ENDPOINT_ADMIN`. Cấu hình dùng Spring MVC/Servlet và HTTP Basic để tập trung vào quy tắc; production nên tích hợp cơ chế xác thực phù hợp với tổ chức, bật HTTPS và quản lý credential an toàn.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

// Spring Boot 4.x:
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
// Với Spring Boot 3.x, dùng import:
// org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ENDPOINT_ADMIN"))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là ví dụ cấu trúc cho ứng dụng có hai vùng bảo vệ. Chuỗi đầu tiên chỉ match Actuator. Chuỗi thứ hai xử lý các request còn lại; thay `authenticated()` bằng quy tắc phù hợp với API, OAuth2 Resource Server, form login hoặc cơ chế hiện có của dự án. Không thay toàn bộ security config hiện hữu bằng ví dụ này mà chưa xem xét các matcher và thứ tự filter chain của ứng dụng.

`EndpointRequest.toAnyEndpoint()` theo dõi management base path đã cấu hình, vì vậy an toàn hơn việc hard-code `/actuator/**` khi ứng dụng có thể đổi prefix. Trong Spring Boot 4, package của `EndpointRequest` là `org.springframework.boot.security.autoconfigure.actuate.web.servlet`; ở Spring Boot 3.x là `org.springframework.boot.actuate.autoconfigure.security.servlet`. Hãy dùng import phù hợp với dòng Boot của dự án.

### 7.3. Tránh để health details lộ ra ngoài

Health endpoint có thể tổng hợp trạng thái của database, message broker, cache hoặc các `HealthIndicator` do thư viện tích hợp cung cấp. Thông tin chi tiết có thể tiết lộ tên thành phần, topology hoặc thông tin chẩn đoán nội bộ.

Thiết lập mặc định an toàn:

~~~yaml
management:
  endpoint:
    health:
      show-details: "never"
      show-components: "never"
~~~

Nếu đội vận hành cần chi tiết sau khi xác thực:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: "ENDPOINT_ADMIN"
~~~

`when-authorized` chỉ hiển thị details/components cho người dùng được xác thực và có role được cấu hình. Nếu không cấu hình role riêng, Spring Boot xem người dùng đã xác thực là được phép xem. Không đặt `always` trên endpoint có thể truy cập công khai.

Health status tổng thể vẫn có thể trả `UP`, `DOWN` hoặc `OUT_OF_SERVICE` mà không cần công khai chi tiết từng contributor.

## 8. Chọn endpoint theo mục đích vận hành

Không phải endpoint nào cũng có cùng mức rủi ro. Bảng sau giúp quyết định trước khi thêm một ID vào allowlist:

| Endpoint | Dữ liệu/tác động | Khuyến nghị |
| --- | --- | --- |
| `health` | Trạng thái tổng thể và health groups | Thường cần cho probe/monitoring; ẩn details với người chưa được phép |
| `info` | Metadata ứng dụng, build và git nếu contributor tương ứng hoạt động | Chỉ công bố dữ liệu đã rà soát; không đưa secret hoặc thông tin nội bộ nhạy cảm |
| `prometheus` | Metrics để Prometheus scrape | Chỉ mở nếu có `micrometer-registry-prometheus`; giới hạn mạng scraper |
| `metrics` | Danh sách và giá trị metric theo tên | Chỉ dùng khi công cụ cần; bảo vệ vì metric có thể tiết lộ tên luồng xử lý hoặc nhãn |
| `loggers` | Đọc/thay đổi mức log runtime | Chỉ dành cho operator có quyền; có thể thay đổi log level gây tăng tải hoặc lộ dữ liệu |
| `env`, `configprops` | Environment và cấu hình ứng dụng (có sanitization) | Không expose công khai; thông tin cấu hình vẫn nhạy cảm dù có che một số giá trị |
| `beans`, `conditions`, `mappings` | Cấu trúc bean, auto-configuration và route mapping | Dùng khi chẩn đoán nội bộ; không mở mặc định ra Internet |
| `heapdump`, `threaddump`, `logfile` | File dump, thread stack hoặc nội dung log | Chỉ bật trong quy trình hỗ trợ có kiểm soát; có thể chứa dữ liệu nhạy cảm và tạo tải lớn |
| `shutdown` | Tắt ứng dụng | Không expose nếu không có yêu cầu vận hành đặc biệt và quy trình xác thực/ủy quyền chặt |

### 8.1. Thêm `info` một cách có chủ đích

`info` tập hợp dữ liệu từ các `InfoContributor`. Ví dụ, có thể bật contributor `env` để công bố một số thuộc tính bắt đầu bằng `info.`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    env:
      enabled: true
info:
  app:
    name: order-service
    version: "1.4.0"
    description: "Order processing API"
~~~

Không đặt mật khẩu, token, connection string, URL nội bộ hoặc thông tin khách hàng dưới `info.*`. Chỉ công bố metadata giúp phân biệt service và bản build.

Nếu build tạo `META-INF/build-info.properties` hoặc `git.properties`, các contributor build/git có thể thêm dữ liệu vào response theo cấu hình phiên bản. Kiểm tra kết quả thực tế và tắt contributor không cần thiết, ví dụ:

~~~yaml
management:
  info:
    git:
      enabled: false
~~~

### 8.2. Chỉ expose Prometheus khi có nhu cầu

Endpoint `prometheus` cần dependency registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Sau đó mới cân nhắc thêm `prometheus` vào allowlist:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

Chỉ cho phép Prometheus server hoặc mạng giám sát truy cập endpoint này. Metrics có thể tiết lộ tên service, route, loại lỗi và hoạt động nội bộ. Tránh gắn nhãn có cardinality rất cao như user ID, request ID hoặc email vào metric.

## 9. Management port và mạng truy cập

Mặc định Actuator HTTP dùng cùng cổng với web server chính. Có thể tách management endpoint sang cổng riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Khi đó, API nghiệp vụ phục vụ ở `8080`, còn Actuator HTTP ở `8081`. Tách cổng giúp áp dụng network policy, ingress hoặc firewall riêng; **không tự biến cổng 8081 thành cổng an toàn**. Vẫn cần kiểm soát exposure, authentication/authorization và giới hạn nguồn kết nối.

Nếu chỉ muốn quản trị từ loopback của máy:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Không dùng cấu hình loopback này một cách máy móc trong Kubernetes: kubelet hoặc Prometheus có thể cần truy cập qua địa chỉ mạng của Pod. Hãy thiết kế binding và NetworkPolicy theo cách probe/scraper thực sự kết nối.

Nếu không cần HTTP management endpoint, có thể tắt HTTP exposure hoàn toàn bằng cách loại tất cả endpoint khỏi exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
~~~

Hoặc cấu hình management server port `-1` khi phiên bản và cách triển khai hỗ trợ lựa chọn đó. Trước khi tắt, xác nhận ứng dụng không phụ thuộc vào HTTP health probe.

## 10. Health, liveness và readiness trong hệ thống phân tán

### 10.1. Health không đồng nghĩa với “có thể nhận traffic”

`/actuator/health` trả trạng thái tổng hợp từ các `HealthContributor` đang được đăng ký. Nếu ứng dụng dùng database, Redis hoặc message broker và có health indicator tương ứng, các contributor đó có thể ảnh hưởng kết quả tổng thể.

Trong môi trường có orchestrator, cần phân biệt:

- **Liveness:** tiến trình ứng dụng còn sống và không bị kẹt đến mức cần restart hay không.
- **Readiness:** instance có sẵn sàng nhận request nghiệp vụ tại thời điểm này hay không.
- **Startup probe:** ứng dụng đã hoàn tất giai đoạn khởi động dài hay chưa, để orchestrator không restart quá sớm.

Không dùng liveness để kiểm tra database, registry hoặc một dịch vụ bên ngoài. Nếu dependency bên ngoài lỗi và liveness chuyển sang fail, Kubernetes có thể restart hàng loạt instance, làm tình hình quá tải nghiêm trọng hơn.

Readiness có thể xét dependency bên ngoài khi nghiệp vụ thật sự không thể phục vụ nếu thiếu dependency đó. Hãy chọn contributor cẩn thận, vì một readiness check quá rộng có thể rút toàn bộ instance khỏi load balancer trong một sự cố chung.

### 10.2. Bật health probes

Spring Boot có health group `liveness` và `readiness` khi cơ chế probes được kích hoạt. Có thể cấu hình tường minh:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Hai path bổ sung mặc định là `/livez` và `/readyz` trên cổng ứng dụng chính. Các path health group vẫn có thể được truy cập dưới `/actuator/health/liveness` và `/actuator/health/readiness` trên management server. Điều này hữu ích khi management port riêng nhưng probe cần xác nhận cả web server chính.

Nếu chỉ cần dùng path mặc định của health groups, có thể bỏ `add-additional-paths`. Hãy xác nhận phiên bản Spring Boot và môi trường triển khai đã kích hoạt probes như mong đợi.

### 10.3. Ví dụ cấu hình Kubernetes

Đoạn manifest minh họa probe gọi hai path trên cổng ứng dụng:

~~~yaml
containers:
  - name: order-service
    ports:
      - name: http
        containerPort: 8080
      - name: management
        containerPort: 8081
    livenessProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 10
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: http
      periodSeconds: 5
      failureThreshold: 3
~~~

Đây là đoạn trích phần `containers` để minh họa, cần ghép vào Pod/Deployment manifest thực tế. Khi cấu hình `management.server.port` riêng, không bắt buộc probe phải gọi cổng management nếu đã bật additional paths trên cổng ứng dụng.

## 11. Kiểm thử cấu hình Actuator

Sau khi khởi động ứng dụng, cần kiểm tra cả endpoint được phép và endpoint không được phép.

### 11.1. Kiểm tra thủ công

~~~bash
# Health endpoint nằm trong allowlist
curl -i http://localhost:8080/actuator/health

# Info endpoint chỉ tồn tại nếu đã include và có dữ liệu contributor
curl -i http://localhost:8080/actuator/info

# Env không nằm trong allowlist nên không được expose qua HTTP
curl -i http://localhost:8080/actuator/env

# Beans cũng không được expose qua HTTP
curl -i http://localhost:8080/actuator/beans
~~~

Kết quả cần hiểu đúng:

| Kết quả HTTP | Ý nghĩa thường gặp |
| --- | --- |
| `200 OK` | Endpoint tồn tại, request được phép và xử lý thành công |
| `401 Unauthorized` | Endpoint có thể truy cập nhưng request chưa xác thực |
| `403 Forbidden` | Request đã bị từ chối bởi quy tắc quyền hoặc CSRF |
| `404 Not Found` | URL không được map, endpoint không được expose hoặc không tồn tại |
| `503 Service Unavailable` | Health status có thể là `DOWN`/`OUT_OF_SERVICE` theo status mapping |

Mã trạng thái thực tế còn phụ thuộc security filter, management base path và cách reverse proxy xử lý. Vì vậy, kết hợp HTTP response với log khởi động và cấu hình runtime để tìm nguyên nhân.

### 11.2. Checklist kiểm tra trước khi release

- [ ] Dependency `spring-boot-starter-actuator` được quản lý bởi phiên bản Spring Boot tương thích.
- [ ] HTTP allowlist chỉ chứa ID đã được đội phát triển và vận hành chấp thuận.
- [ ] Không dùng wildcard ngoài môi trường thử nghiệm nếu chưa có đánh giá bảo mật.
- [ ] `env`, `configprops`, `beans`, `heapdump`, `threaddump` và `shutdown` không bị expose ngoài ý muốn.
- [ ] Health details/components không tiết lộ thông tin cho người chưa được phép.
- [ ] Security chain cho Actuator và API nghiệp vụ đều được định nghĩa khi có custom `SecurityFilterChain`.
- [ ] Management port, bind address, firewall, ingress và NetworkPolicy đúng với luồng truy cập dự kiến.
- [ ] Liveness không phụ thuộc vào database, registry hay hệ thống bên ngoài.
- [ ] Readiness chỉ kiểm tra dependency thực sự cần thiết để phục vụ request.
- [ ] Đã thử request trái phép, request thiếu xác thực và request có role đúng.
- [ ] Đã xác minh cả HTTP và JMX exposure theo chính sách của tổ chức.

### 11.3. Kiểm thử tự động

Có thể dùng `@SpringBootTest` cùng `MockMvc` cho ứng dụng Servlet hoặc `WebTestClient` cho WebFlux/HTTP test phù hợp. Những điều cần xác minh:

1. `/actuator/health` được expose và trả response theo cấu hình.
2. `/actuator/info` chỉ trả các trường metadata đã chọn.
3. `/actuator/env` và `/actuator/beans` không thể được gọi từ HTTP khi không nằm trong allowlist.
4. User thiếu role không đọc được endpoint quản trị bị bảo vệ.
5. Health details bị ẩn với user chưa được phép.
6. Khi chạy với profile production, cấu hình management port và base path đúng như mong đợi.

Test cấu hình exposure nên chạy với profile hoặc application context gần với production. Một test chỉ kiểm tra file YAML có chứa chuỗi `health,info` không chứng minh endpoint thực tế đã được bảo vệ.

## 12. Tình huống thực tế: chuẩn bị order-service cho vận hành

Giả sử `order-service` là một dịch vụ Spring Cloud chạy trong Kubernetes. Dịch vụ dùng database và gọi `inventory-service` thông qua discovery/load balancing. Đội vận hành cần:

- Kubernetes biết khi nào container sống và sẵn sàng nhận traffic.
- Monitoring đọc được trạng thái service.
- Dashboard phân biệt bản build đang chạy.
- Prometheus scrape metrics trong mạng nội bộ.
- Người dùng Internet không đọc được cấu hình hay cấu trúc bean.

Một cấu hình ban đầu có thể là:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      access: read-only
      show-details: when-authorized
      show-components: when-authorized
      roles: "ENDPOINT_ADMIN"
      probes:
        enabled: true
        add-additional-paths: true
    info:
      access: read-only
    prometheus:
      access: read-only
  info:
    git:
      enabled: false
~~~

Cấu hình giả định phiên bản Spring Boot hỗ trợ `management.endpoints.access.*`, dependency registry Prometheus đã có và Security được cấu hình đúng. Nếu không sử dụng Prometheus, bỏ `prometheus` khỏi allowlist và bỏ dependency registry. Nếu không cần `info`, bỏ `info` khỏi allowlist. Nếu quản lý health detail bằng role khác, đồng bộ role với cấu hình Spring Security.

Trong mô hình này, probe có thể gọi `/livez` và `/readyz` trên `8080`, còn monitoring/operator truy cập management port `8081` qua mạng nội bộ. Phải cấu hình service/network policy chỉ cho phép đúng nguồn truy cập cổng 8081; không đưa management port ra public ingress.

Đội vận hành cũng cần xác định health indicator nào phản ánh dependency discovery và database. Nếu registry tạm thời không khả dụng nhưng instance vẫn có thể xử lý request hiện tại, không nhất thiết đánh dấu liveness fail. Quy tắc readiness phải theo hợp đồng phục vụ thực tế của `order-service`.

## 13. Những sai lầm thường gặp

**Expose tất cả endpoint để tiện debug.** Điều này có thể công bố cấu hình, biến môi trường, thông tin bean, route và file dump. Hãy bắt đầu từ allowlist.

**Nghĩ rằng đổi `/actuator` thành `/manage` là đủ bảo mật.** Đổi path chỉ thay URL, không thay xác thực hoặc quyền truy cập.

**Nghĩ rằng có Spring Security thì Actuator tự động được bảo vệ theo mong muốn.** Boot chỉ áp dụng cấu hình tự động khi không có `SecurityFilterChain` tùy chỉnh. Khi tự định nghĩa filter chain, phải rà soát cả Actuator lẫn API nghiệp vụ.

**Cho phép `show-details: always` vì monitoring cần biết database nào lỗi.** Monitoring thường chỉ cần trạng thái tổng thể; chi tiết nên dành cho người vận hành đã xác thực.

**Dùng liveness để kiểm tra mọi dependency.** Điều này có thể biến một sự cố database hoặc service registry thành vòng lặp restart hàng loạt.

**Tách management port rồi cho rằng đã an toàn.** Port riêng vẫn cần firewall, network policy, authentication và exposure allowlist.

**Mở endpoint `prometheus` mà quên registry dependency và network scope.** Endpoint cần Micrometer Prometheus registry và nên chỉ cho scraper nội bộ truy cập.

## 14. Tổng kết

Actuator giúp ứng dụng Spring Boot cung cấp health, info, metrics và các thông tin quản trị có cấu trúc. Khi dùng trong hệ thống Spring Cloud, nó hỗ trợ quan sát các service và những health contributor được tích hợp, nhưng không thay thế discovery, registry hay security.

Quy trình khởi tạo nên bắt đầu bằng `spring-boot-starter-actuator`, sau đó xác định endpoint theo nhu cầu, dùng **allowlist** qua `management.endpoints.web.exposure.include`, giới hạn endpoint access nếu phiên bản hỗ trợ, bảo vệ bằng Spring Security và kiểm soát đường mạng. Health details phải được giới hạn, liveness/readiness phải phản ánh đúng vai trò, và mọi thay đổi cần được kiểm tra bằng request thực tế cùng integration test.

Chỉ mở endpoint có người tiêu thụ, mục đích và quyền truy cập đã rõ ràng. Đây là cách để Actuator hỗ trợ vận hành mà không biến giao diện quản trị thành một bề mặt tấn công không cần thiết.

## Tài liệu tham khảo

- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html): thêm `spring-boot-starter-actuator`.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint access, exposure, security, health details, health groups và Kubernetes probes.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management base path, management port/address và tắt HTTP endpoints.
- [Spring Boot — Actuator REST API](https://docs.spring.io/spring-boot/api/rest/actuator/): URL và response của các endpoint HTTP.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): tra cứu đầy đủ thuộc tính `management.*` theo phiên bản.
- [Spring Security — Servlet Security](https://docs.spring.io/spring-security/reference/servlet/index.html): cấu hình filter chain, authentication và authorization.

Luôn chọn tài liệu đúng dòng Spring Boot đang dùng. Một số thuộc tính access control và package Java của `EndpointRequest` thay đổi theo thế hệ Boot; cấu hình trong bài cần được đối chiếu với phiên bản thực tế trước khi đưa vào production.
