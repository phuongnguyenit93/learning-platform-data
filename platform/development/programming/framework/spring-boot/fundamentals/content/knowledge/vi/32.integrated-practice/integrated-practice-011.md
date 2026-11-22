# Quan sát health, beans và thông tin khởi động trong phạm vi được cho phép

Spring Boot Actuator cung cấp các endpoint giúp đội phát triển và vận hành hiểu trạng thái ứng dụng đang chạy. Ba nguồn thông tin thường hữu ích khi điều tra một service là:

- **Health**: ứng dụng và các thành phần phụ thuộc đang ở trạng thái nào, có sẵn sàng nhận request không?
- **Beans**: những bean nào được Spring đăng ký trong ApplicationContext, chúng có kiểu, scope và quan hệ dependency ra sao?
- **Startup information**: những bước nào diễn ra trong quá trình khởi động, bước nào tốn thời gian và cấu hình nào cần được kiểm tra?

Những dữ liệu này giúp xử lý sự cố, nhưng cũng có thể tiết lộ cấu trúc nội bộ, tên class, dependency, topology hoặc thông tin vận hành. Vì vậy, việc quan sát phải nằm trong **phạm vi được phép**: chỉ bật endpoint cần thiết, công bố qua transport phù hợp, giới hạn người truy cập và chỉ trả về mức chi tiết cần cho công việc.

Bài học dùng Spring Boot 3.x, Spring MVC và Spring Security 6 trong ví dụ HTTP. Bạn sẽ thực hành cách bật Actuator, đọc health status, giới hạn health details, quan sát bean inventory, ghi nhận startup steps bằng `BufferingApplicationStartup`, bảo vệ endpoint bằng role, tách management network và viết kiểm thử cho cả truy cập được phép lẫn bị từ chối.

## 1. Mục tiêu quan sát và giới hạn dữ liệu

Một endpoint vận hành nên trả lời một câu hỏi cụ thể. Không nên công bố toàn bộ dữ liệu chỉ vì Actuator có sẵn endpoint.

| Nhu cầu | Thông tin phù hợp | Phạm vi truy cập gợi ý |
| --- | --- | --- |
| Load balancer kiểm tra service | Health status tổng quát | Probe được phép đọc status |
| Orchestrator kiểm tra readiness/liveness | Trạng thái sẵn sàng và còn sống | Pod/node network hoặc listener nội bộ |
| SRE kiểm tra dependency | Health components/details cần thiết | Tài khoản vận hành được phân quyền |
| Developer điều tra bean wiring | Bean names, types, dependencies | Môi trường dev/staging hoặc admin nội bộ |
| Team phân tích startup chậm | Startup steps và durations | Admin/SRE, truy cập có kiểm soát |
| Metrics scraper | Metrics đã được chọn lọc | Service identity của hệ thống monitoring |

Ba nguyên tắc nên áp dụng:

1. **Least privilege**: mỗi caller chỉ được xem đúng dữ liệu cần thiết.
2. **Data minimization**: response chỉ chứa thông tin cần cho quyết định vận hành.
3. **Defense in depth**: kết hợp endpoint exposure, authentication, authorization, network isolation và audit.

Không phải mọi endpoint chỉ đọc đều vô hại. Health details có thể tiết lộ dependency nội bộ; beans endpoint có thể liệt kê kiến trúc ứng dụng; startup endpoint có thể cho biết tên class, bean và các bước khởi tạo. Hãy xem chúng là dữ liệu vận hành nội bộ.

## 2. Thêm Spring Boot Actuator

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Actuator cung cấp các endpoint chuẩn như `health`, `info`, `beans`, `conditions`, `env`, `configprops`, `metrics`, `loggers` và các endpoint khác tùy dependency/cấu hình.

Trong ứng dụng web, base path mặc định thường là:

~~~text
/actuator
~~~

Ví dụ health URL:

~~~http
GET /actuator/health
~~~

Response status tối giản có thể là:

~~~json
{
  "status": "UP"
}
~~~

Việc thêm dependency không có nghĩa tất cả endpoint đều được công bố qua HTTP. Trong cấu hình Spring Boot 3.x tiêu chuẩn, HTTP và JMX exposure mặc định chỉ gồm `health`. Phần lớn endpoint được enable theo mặc định, nhưng enablement và exposure là hai quyết định khác nhau.

## 3. Phân biệt enablement, exposure và authorization

Một endpoint có thể được sử dụng qua HTTP khi các điều kiện chính phù hợp:

1. Endpoint được enable.
2. Endpoint được expose qua HTTP.
3. Request đi tới đúng management listener/path.
4. Caller vượt qua authentication và authorization.
5. Response policy cho phép hiển thị mức chi tiết tương ứng.

~~~mermaid
flowchart TD
    A["Request tới /actuator/..."] --> B{"Endpoint enabled?"}
    B -->|No| X["Endpoint không khả dụng"]
    B -->|Yes| C{"Exposed qua HTTP?"}
    C -->|No| Y["Không có HTTP endpoint"]
    C -->|Yes| D{"Đúng listener/network?"}
    D -->|No| Z["Không tới được management service"]
    D -->|Yes| E{"Authenticated và authorized?"}
    E -->|No| F["401 / 403"]
    E -->|Yes| G["Áp dụng response disclosure policy"]
    G --> H["Chỉ trả dữ liệu được phép"]
~~~

### 3.1. Enablement

Có thể tắt endpoint không cần dùng:

~~~properties
management.endpoint.beans.enabled=false
~~~

Hoặc áp dụng opt-in cho các endpoint:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    beans:
      enabled: true
    startup:
      enabled: true
~~~

Với opt-in, chỉ những endpoint được enable rõ ràng mới được cung cấp. Nếu endpoint cần dùng qua HTTP, vẫn phải expose nó.

### 3.2. Exposure

Một allowlist HTTP tối giản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
~~~

Khi cần quan sát thêm beans và startup trong một môi trường nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

Endpoint `startup` còn cần cấu hình ghi nhận startup steps bằng `BufferingApplicationStartup`; chỉ thêm tên endpoint vào include list không tự tạo dữ liệu startup.

Có thể dùng exclude:

~~~properties
management.endpoints.web.exposure.include=health,beans,startup,env
management.endpoints.web.exposure.exclude=env
~~~

Exclude được ưu tiên so với include. Dù vậy, một allowlist ngắn thường dễ review hơn việc include mọi endpoint rồi loại trừ từng endpoint nguy hiểm.

### 3.3. Authorization

Exposure chỉ quyết định endpoint có xuất hiện qua HTTP. Nó không có nghĩa mọi caller đều được phép đọc endpoint đó. Dùng Spring Security hoặc một cơ chế bảo vệ tương ứng để giới hạn người dùng và service account.

Nếu ứng dụng tự định nghĩa `SecurityFilterChain`, cần kiểm tra các rules thực tế: trong cấu hình Servlet tiêu chuẩn, việc ứng dụng cung cấp chain riêng khiến Actuator security auto-configuration mặc định của Spring Boot nhường quyền cho cấu hình ứng dụng.

## 4. Health endpoint trả lời điều gì?

Health endpoint tổng hợp trạng thái từ các `HealthIndicator` và `HealthContributor` đang được cấu hình. Một ứng dụng có thể có các contributor cho database, disk space, messaging, readiness/liveness hoặc integration riêng.

Ví dụ:

~~~http
GET /actuator/health
~~~

Response công khai đơn giản:

~~~json
{
  "status": "UP"
}
~~~

Một status không phải lúc nào cũng chỉ có UP hoặc DOWN. Health status có thể được tổng hợp từ nhiều contributor và được ánh xạ theo status order/mapping đã cấu hình. Các trạng thái thường gặp gồm:

- `UP`: thành phần báo hoạt động bình thường.
- `DOWN`: thành phần báo không hoạt động.
- `OUT_OF_SERVICE`: thành phần không phục vụ request.
- `UNKNOWN`: không xác định được trạng thái.

Nếu một contributor báo trạng thái xấu, trạng thái tổng hợp của endpoint có thể phản ánh điều đó theo quy tắc status aggregation.

### 4.1. Health không phải một bài kiểm thử nghiệp vụ đầy đủ

`UP` chỉ nói rằng các health contributors được cấu hình đang báo trạng thái tốt theo logic của chúng. Nó không chứng minh mọi API đều trả kết quả đúng, mọi luồng nghiệp vụ thành công, database schema hoàn toàn đúng, hệ thống chịu được tải production hoặc mọi downstream service sẵn sàng cho mọi loại request.

Health check nên được thiết kế cho quyết định vận hành cụ thể, chẳng hạn có nên gửi traffic vào instance hay không.

### 4.2. Health contributors phổ biến

Tùy dependencies và cấu hình, ứng dụng có thể có contributors cho:

| Contributor | Điều thường được kiểm tra |
| --- | --- |
| `db` | Kết nối datasource/database |
| `diskSpace` | Dung lượng đĩa theo ngưỡng cấu hình |
| `ping` | Một kiểm tra cơ bản của application context |
| `livenessState` | Trạng thái liveness của ứng dụng |
| `readinessState` | Trạng thái readiness của ứng dụng |
| Custom indicator | Một dependency hoặc điều kiện nghiệp vụ được chọn |

Không nên giả định tất cả contributor đều tồn tại trong mọi project. Ví dụ `db` cần cấu hình database health integration phù hợp.

## 5. Tạo HealthIndicator tùy chỉnh

Một integration có thể cung cấp health indicator để báo trạng thái của dependency mà Actuator chưa có contributor phù hợp.

Ví dụ:

~~~java
package com.example.shop.monitoring;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class BillingHealthIndicator implements HealthIndicator {

    private final BillingGateway billingGateway;

    public BillingHealthIndicator(BillingGateway billingGateway) {
        this.billingGateway = billingGateway;
    }

    @Override
    public Health health() {
        boolean available = billingGateway.isAvailable();

        if (available) {
            return Health.up()
                    .withDetail("provider", "billing")
                    .build();
        }

        return Health.down()
                .withDetail("provider", "billing")
                .withDetail("reason", "dependency unavailable")
                .build();
    }
}
~~~

Đây là ví dụ khái niệm; lời gọi `isAvailable()` cần timeout và error handling phù hợp với client thực tế. Health check không nên thực hiện một thao tác mạng không giới hạn thời gian khiến probe bị treo.

### 5.1. Không đưa secrets vào health details

Không nên trả về password, token, authorization header, connection string hoặc URL có credential trong details. Một health response có thể được gọi bởi load balancer hoặc monitoring agent. Nếu đưa credential vào details, bạn đã biến health endpoint thành một kênh rò rỉ secret.

Nên trả metadata tối thiểu, chẳng hạn tên dependency logic, status hoặc mã lỗi không chứa dữ liệu nhạy cảm:

~~~java
return Health.down()
        .withDetail("dependency", "billing")
        .withDetail("reason", "connection unavailable")
        .build();
~~~

### 5.2. Không gọi dependency nặng trên mọi probe

Probe có thể được gọi thường xuyên từ orchestrator. Một health indicator gọi nhiều remote services tuần tự, thực hiện query nặng hoặc chờ retry lâu có thể tự tạo thêm tải trong lúc hệ thống đang gặp sự cố.

Thiết kế nên có timeout ngắn và xác định, không retry kéo dài trong một lần probe, chỉ kiểm tra dependency cần cho quyết định health, tránh ghi log lặp lại với tần suất cao và cân nhắc cache trạng thái ngắn hạn nếu phù hợp semantics.

### 5.3. Reactive HealthIndicator

Ứng dụng reactive có thể dùng `ReactiveHealthIndicator` để kiểm tra dependency theo reactive API. Không nên chặn event loop bằng một lời gọi blocking dài chỉ để tạo health status.

## 6. Giới hạn health details và components

Health status tổng quát thường đủ cho probe. Các chi tiết như tên datasource, tên cluster, trạng thái broker hoặc exception message có thể chỉ dành cho SRE.

Spring Boot cung cấp hai property quan trọng:

- `management.endpoint.health.show-details`: quyết định hiển thị details.
- `management.endpoint.health.show-components`: quyết định hiển thị các health components.

Các chế độ phổ biến:

| Giá trị | Ý nghĩa |
| --- | --- |
| `never` | Không hiển thị details/components theo chế độ này |
| `when-authorized` | Chỉ hiển thị khi caller được coi là authorized |
| `always` | Luôn hiển thị cho caller truy cập endpoint |

Ví dụ giữ response đơn giản:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

Nếu admin cần chi tiết:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Với `when-authorized`, role cấu hình xác định nhóm người dùng được xem details. Nếu không giới hạn roles rõ ràng, người dùng đã authenticated có thể được coi là authorized theo mặc định của endpoint; đừng suy ra rằng chỉ admin mới thấy details nếu chưa cấu hình role.

### 6.1. Status công khai và details riêng tư

Một thiết kế thường dùng:

- Health checker không cần đăng nhập chỉ đọc được `status`.
- SRE đã xác thực và có role phù hợp mới đọc được components/details.
- Anonymous hoặc user thường không nhận được thông tin dependency nội bộ.

Cần kết hợp response policy với Spring Security. `show-details=when-authorized` không thay thế việc bảo vệ URL và management network.

### 6.2. Không đưa exception thô vào details

Exception message có thể chứa hostname, schema, SQL fragment, URL, username hoặc dữ liệu request. Với custom indicator, hãy chuyển exception thành một reason code/summary an toàn thay vì đưa toàn bộ exception object vào response.

## 7. Liveness và readiness

Trong môi trường container/orchestrator, hai câu hỏi khác nhau:

- **Liveness**: process/application có còn sống và có thể tiếp tục hoạt động không?
- **Readiness**: instance hiện có sẵn sàng nhận traffic không?

Spring Boot có application availability states và có thể công bố health groups tương ứng.

Khi bật probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Các endpoint thường dùng:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

### 7.1. Liveness không nên phụ thuộc mọi downstream service

Nếu database tạm thời mất kết nối và liveness chuyển DOWN, Kubernetes có thể liên tục restart tất cả instance. Điều này có thể làm tình hình xấu hơn khi nguyên nhân là dependency dùng chung đang gặp sự cố.

Liveness nên phản ánh việc process có cần restart để phục hồi hay không. Một dependency bên ngoài tạm thời unavailable thường phù hợp với readiness hơn, tùy kiến trúc.

### 7.2. Readiness phản ánh khả năng nhận traffic

Readiness có thể tính đến các điều kiện cần thiết để xử lý request. Ví dụ cấu hình group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,db"
        liveness:
          include: "livenessState"
~~~

Đây là một lựa chọn cần đánh giá theo ứng dụng. Chỉ đưa database vào readiness nếu request cần database để hoạt động và health check đó phản ánh đúng khả năng phục vụ.

Không thêm mọi dependency vào cả liveness và readiness theo thói quen.

### 7.3. Probe path trên main server

Nếu management endpoints chạy trên port riêng, health probe có thể kiểm tra management server trong khi main application server gặp vấn đề. Spring Boot hỗ trợ thêm các đường dẫn probe trên main server port bằng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Khi được hỗ trợ/cấu hình, các path `/livez` và `/readyz` trên main server port có thể được dùng cho probe. Hãy xác nhận URL và port thực tế trong deployment.

## 8. Beans endpoint cho biết điều gì?

`/actuator/beans` liệt kê bean definitions/instances mà Spring context biết đến, theo cấu trúc context. Thông tin có thể bao gồm bean name, aliases, bean type, scope, resource hoặc nguồn khai báo, dependencies liên quan và context chứa bean.

Ví dụ gọi endpoint:

~~~http
GET /actuator/beans
~~~

Response minh họa:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.shop.order.OrderService",
          "dependencies": [
            "orderRepository"
          ]
        }
      }
    }
  }
}
~~~

Đây là JSON minh họa cấu trúc khái quát, không phải schema đầy đủ cho mọi Spring Boot version.

### 8.1. Beans endpoint hữu ích khi nào?

- Kiểm tra một service có được đăng ký thành bean không.
- Xác định bean implementation thực tế đang được dùng.
- Điều tra dependency injection bị thiếu hoặc chọn sai.
- Xem một configuration/module có được load không.
- Tìm hiểu bean graph khi nhiều auto-configuration cùng tham gia.
- Hỗ trợ so sánh context giữa local, staging và production trong phạm vi được phép.

### 8.2. Beans endpoint có thể tiết lộ điều gì?

Danh sách bean có thể tiết lộ tên package và class nội bộ, integration adapter hoặc vendor library, datasource/cache/message client, cấu trúc module và dependency graph, thành phần security/configuration và những tính năng được bật trong môi trường.

Đây là metadata kiến trúc. Kẻ tấn công có thể dùng nó để suy đoán framework, dependency và bề mặt tấn công. Vì vậy không nên expose `beans` cho anonymous users hoặc public ingress.

### 8.3. Beans endpoint không phải công cụ sửa bean

Endpoint này chủ yếu để quan sát. Nó không thay thế Spring debugger, bean factory diagnostics hoặc integration tests. Nếu bean sai, hãy sửa package scan, configuration, condition hoặc dependency injection trong source/configuration.

## 9. Quan sát beans endpoint trong phạm vi được phép

Trong môi trường phát triển, bạn có thể expose `beans` tạm thời:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,beans"
~~~

Trong production, chỉ bật khi có use case vận hành rõ ràng và bảo vệ endpoint bằng role/network phù hợp.

| Caller | Health status | Health details | Beans inventory |
| --- | --- | --- | --- |
| Anonymous probe | Có thể cho phép | Không | Không |
| Authenticated user thường | Theo policy | Không | Không |
| SRE/admin | Có | Có nếu cần | Có khi được phê duyệt |
| Public internet | Không công bố dữ liệu nội bộ | Không | Không |

Nếu không cần xem bean graph liên tục, giữ `beans` không exposed và chỉ bật trong một cửa sổ điều tra được kiểm soát, sau đó thu hồi.

Không lưu toàn bộ response beans vào log chung hoặc ticket công khai. Nếu cần bằng chứng, trích xuất phần tối thiểu, loại bỏ metadata không cần thiết và lưu ở nơi có access control/retention phù hợp.

Bean names không phải public contract. Không nên để hệ thống nghiệp vụ bên ngoài phụ thuộc vào tên bean trong Actuator response.

## 10. Startup information và StartupEndpoint

Một ứng dụng Spring có thể tạo nhiều bean và chạy nhiều bước trước khi sẵn sàng nhận traffic. Khi startup chậm, log tổng quát thường chỉ cho biết tổng thời gian khởi động, chưa chỉ ra bước nào mất thời gian.

Spring Framework có abstraction `ApplicationStartup` để ghi nhận startup steps. Spring Boot cung cấp `BufferingApplicationStartup` để lưu các bước này trong một buffer có giới hạn.

Khi kết hợp Actuator startup endpoint, đội vận hành có thể xem startup steps và duration để điều tra quá trình khởi tạo.

### 10.1. Cấu hình BufferingApplicationStartup

Trong main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShopApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

Giá trị `2048` là capacity minh họa cho buffer. Chọn capacity theo số startup steps dự kiến và tài nguyên cho phép. Buffer có giới hạn; không nên giả định nó là kho lưu trữ lịch sử vô hạn.

Cần cấu hình startup recorder trước khi gọi `run` để các bước bootstrap được ghi nhận.

### 10.2. Bật và expose startup endpoint

Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

Khi application sử dụng `BufferingApplicationStartup` và endpoint được enable/expose phù hợp, có thể truy cập:

~~~http
GET /actuator/startup
~~~

Endpoint trả dữ liệu startup steps theo cấu trúc mà phiên bản Spring Boot cung cấp. Nội dung có thể chứa tên step, duration, tags hoặc thông tin liên quan bean/configuration.

Nếu endpoint không có dữ liệu, kiểm tra application có thật sự được cấu hình `BufferingApplicationStartup` trước khi startup hay không.

### 10.3. Startup endpoint khác log startup

| Nguồn | Trả lời câu hỏi |
| --- | --- |
| Application logs | Ứng dụng đã in những thông báo nào trong lúc startup? |
| Startup endpoint | Các startup steps được ghi nhận có cấu trúc và duration ra sao? |
| Metrics | Các chỉ số runtime tổng hợp như request count/latency/memory thế nào? |
| Tracing | Một request hoặc operation cụ thể đi qua các thành phần nào? |

Startup endpoint không phải một bản sao của log và cũng không phải profiler đầy đủ cho mọi CPU instruction. Nó giúp quan sát các bước được instrumentation ghi nhận trong startup process.

### 10.4. Startup data cũng là thông tin nội bộ

Startup steps có thể cho biết tên bean, configuration class, package hoặc integration đang được khởi tạo. Thông tin này hữu ích cho admin nhưng không cần công khai cho người dùng cuối.

Bảo vệ `/actuator/startup` như endpoint diagnostics nội bộ. Không expose chỉ vì muốn một dashboard public hiển thị startup duration.

## 11. Phân biệt startup endpoint và info endpoint

`/actuator/info` thường chứa metadata do InfoContributor cung cấp, ví dụ tên ứng dụng, version hoặc build information. Nó không tương đương startup steps.

Ví dụ cấu hình metadata đã chọn lọc:

~~~yaml
info:
  app:
    name: shop-api
    version: "1.4.0"
~~~

Có thể expose `info` nếu dữ liệu được review và phù hợp với caller. Không đưa secrets, internal repository URL hoặc thông tin nhạy cảm vào info metadata.

`/actuator/startup` dùng để quan sát quá trình bootstrap; `/actuator/beans` cho biết bean inventory; `/actuator/health` phản ánh trạng thái health. Mỗi endpoint có mục đích và disclosure risk riêng.

## 12. Bảo vệ endpoints bằng Spring Security

Nếu Spring Security có trên classpath và ứng dụng không tự khai báo `SecurityFilterChain`, Spring Boot cung cấp bảo vệ mặc định cho các Actuator endpoints khác health trong cấu hình tiêu chuẩn.

Khi ứng dụng tự định nghĩa chain, hãy chủ động đặt rules cho Actuator và application APIs. Ví dụ dưới đây dành cho Servlet/MVC application dùng Spring Security 6.

### 12.1. Tách Actuator chain và application chain

~~~java
package com.example.shop.security;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.to("beans", "startup"))
                    .hasRole("ACTUATOR_ADMIN")
                .anyRequest()
                    .denyAll()
        );

        http.httpBasic(withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
        );

        http.httpBasic(withDefaults());

        return http.build();
    }
}
~~~

Ý nghĩa:

- Chain đầu tiên chỉ áp dụng cho Actuator endpoints.
- Health status được phép truy cập anonymous để probe.
- Beans và startup yêu cầu role `ACTUATOR_ADMIN`.
- Các Actuator endpoint khác bị từ chối bởi rule cuối.
- Chain thứ hai xử lý phần còn lại của application, tránh bỏ trống bảo vệ API nghiệp vụ.

Đây là ví dụ authorization, không phải cấu hình identity production hoàn chỉnh. Ứng dụng cần một authentication mechanism thực tế như OIDC/OAuth2 resource server hoặc service identity phù hợp. HTTP Basic chỉ nên dùng trong môi trường đã có TLS và credential handling phù hợp.

### 12.2. Role mapping phải rõ ràng

`hasRole("ACTUATOR_ADMIN")` thường kiểm tra authority `ROLE_ACTUATOR_ADMIN` theo convention mặc định của Spring Security.

Nếu identity provider trả claim khác hoặc không có prefix đó, hãy cấu hình GrantedAuthority mapping hoặc dùng `hasAuthority` với authority đã được chuẩn hóa.

Đừng giả định một JWT claim tên `roles` tự động trở thành Spring Security role nếu chưa cấu hình converter.

### 12.3. Health status anonymous không đồng nghĩa details anonymous

Security chain cho phép GET health. Cấu hình health endpoint vẫn đặt:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Như vậy probe có thể đọc status, trong khi details/components chỉ hiển thị cho caller được endpoint coi là authorized.

### 12.4. Không quên các request ngoài Actuator

Nếu chỉ có chain dùng `securityMatcher(EndpointRequest.toAnyEndpoint())` mà không có chain thứ hai, các request không match chain này có thể không được bảo vệ bởi chain đó. Khi tự cấu hình security, hãy đảm bảo toàn bộ application routes có một policy phù hợp.

### 12.5. CSRF và thao tác ghi

Các endpoint trong bài chủ yếu dùng GET. Nếu sau này expose endpoint có POST/DELETE như thao tác thay đổi runtime, cần xem xét CSRF policy, authentication và authorization cho đúng loại client.

Không tắt CSRF toàn cục chỉ để một request Actuator chạy được. Với machine-to-machine management client, hãy cấu hình chain và CSRF behavior trong phạm vi hẹp, có lý do rõ ràng.

## 13. Tách management port và network

Có thể chạy management endpoints trên port riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,beans,startup"
~~~

Application API nghe ở 8080, management server nghe ở 9001. Điều này giúp tổ chức routing và network policy riêng, nhưng đổi port không tự tạo authentication.

### 13.1. Giới hạn listener theo interface

Nếu management chỉ cần truy cập local trong một số deployment:

~~~yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
~~~

Cấu hình loopback có thể phù hợp cho tiến trình giám sát cùng host. Trong container/orchestrator, hãy xác nhận network namespace và probe topology; bind loopback có thể khiến kubelet hoặc scraper từ Pod network không truy cập được.

### 13.2. Network controls

Có thể kết hợp firewall/security group chỉ cho phép management port từ mạng vận hành, Kubernetes NetworkPolicy giới hạn Pod/service nào được truy cập, internal Service riêng cho management, reverse proxy/ingress không route management paths ra public, TLS hoặc mTLS cho management traffic và service account riêng cho monitoring/admin.

Không coi một port khác là biện pháp bảo mật duy nhất. Nếu 9001 vẫn được route ra internet, endpoint vẫn có thể bị truy cập từ bên ngoài.

### 13.3. JMX là transport riêng

HTTP exposure không quyết định JMX exposure. Nếu ứng dụng dùng JMX, hãy đặt JMX allowlist và bảo vệ connector riêng. Spring MVC/Spring Security HTTP filter chain không tự bảo vệ một JMX connector.

## 14. Cấu hình mẫu theo môi trường

### 14.1. Production: health status và metrics cần thiết

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

`prometheus` cần registry/dependency phù hợp và chỉ nên truy cập được từ monitoring system được phép. Nếu project không dùng Prometheus, bỏ endpoint này khỏi allowlist.

### 14.2. Staging: thêm diagnostics có kiểm soát

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,beans,startup"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - ACTUATOR_ADMIN
    startup:
      enabled: true
~~~

Đồng thời cấu hình `BufferingApplicationStartup` và Spring Security để beans/startup chỉ dành cho admin. Không nên expose staging management port ra public chỉ vì dữ liệu staging ít nhạy cảm hơn production.

### 14.3. Local development

Ở local, developer có thể cần nhiều endpoint hơn để học và debug. Tuy nhiên, không dùng production credentials hoặc dữ liệu thật trong một cấu hình local mở rộng.

Dùng profile rõ ràng:

~~~yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,beans,startup,conditions"
~~~

Đảm bảo profile dev không vô tình được kích hoạt trong production. Network/security controls vẫn cần tồn tại độc lập.

## 15. Quan sát startup và bean graph theo một quy trình

Khi một service khởi động chậm hoặc thiếu bean, nên điều tra có thứ tự:

### Bước 1: Xác nhận health status

Gọi `/actuator/health` để biết ứng dụng có startup thành công và health contributors báo gì. Nếu health status DOWN, xem tiếp details chỉ khi có quyền.

### Bước 2: Xác nhận bean cần thiết

Nếu nghi ngờ bean chưa được đăng ký, dùng `/actuator/beans` trong môi trường và quyền phù hợp. Tìm bean theo tên/type hoặc dependency.

### Bước 3: Kiểm tra cấu hình module

Nếu bean thiếu, xem package scan, `@Import`, conditions, profile và configuration properties. Beans endpoint cho biết kết quả đăng ký, còn source/configuration giải thích vì sao.

### Bước 4: Đọc startup steps

Nếu app khởi động chậm, xem `/actuator/startup` sau khi đã bật `BufferingApplicationStartup`. Xác định step duration cao, loại step và các bean/configuration liên quan.

### Bước 5: Đối chiếu startup logs

Startup endpoint và logs bổ sung cho nhau. Logs có thể cho biết lỗi hoặc remote connection; startup steps có thể cho biết phần nào trong bootstrap tiêu tốn thời gian.

### Bước 6: Đánh giá sau thay đổi

Sau khi sửa configuration hoặc dependency, chạy lại startup trong môi trường tương ứng. So sánh health, bean inventory và startup steps theo đúng access policy.

## 16. Ví dụ kiểm thử endpoint access

Kiểm thử nên xác nhận cả người được phép và người không được phép.

Ví dụ với Spring MVC, Spring Security Test, MockMvc và một ứng dụng đã có hai security chains như trên:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,beans",
        "management.endpoint.health.show-details=when-authorized",
        "management.endpoint.health.roles=ACTUATOR_ADMIN"
})
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerCanReadHealthStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void ordinaryUserCannotReadBeans() throws Exception {
        mvc.perform(get("/actuator/beans"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void adminCanReadBeans() throws Exception {
        mvc.perform(get("/actuator/beans"))
                .andExpect(status().isOk());
    }
}
~~~

Để chạy ví dụ, project cần dependency Spring Security Test phù hợp, ví dụ starter test và module test support của Spring Security theo cấu hình project. Cần bảo đảm Actuator endpoints đã enable và chain đang áp dụng trên cùng web context.

### 16.1. Kiểm thử startup endpoint

Nếu muốn test `/actuator/startup`, application test bootstrap phải cấu hình `BufferingApplicationStartup` trước khi context chạy và expose startup endpoint. Một test chỉ thêm `startup` vào HTTP include list nhưng không cấu hình recorder chưa chứng minh endpoint có startup data.

### 16.2. Kiểm thử cả trường hợp không được phép

Các test nên xác nhận anonymous chỉ đọc được health status nếu policy cho phép, user thường không đọc được beans/startup, admin có thể đọc endpoint được cấp, endpoint không nằm trong allowlist không được công bố, health details không chứa raw secret và management port không được route qua public ingress theo topology deployment.

Một security test pass trên MockMvc không tự chứng minh firewall hoặc Kubernetes NetworkPolicy đúng. Những lớp network cần integration/deployment checks tương ứng.

## 17. Không đưa dữ liệu nhạy cảm vào diagnostics

Dù đã giới hạn endpoint, hãy thiết kế dữ liệu gốc an toàn:

- Không ghi password/token vào health details.
- Không đặt secret trong bean name hoặc configuration metadata.
- Không đưa credential vào startup step tags tùy chỉnh.
- Không log toàn bộ Environment để điều tra nhanh.
- Không đưa user IDs/emails/token vào metric labels.
- Không công bố exception message thô nếu có thể chứa connection string hoặc request data.
- Không gửi toàn bộ beans response vào log/ticket công khai.

Endpoint security bảo vệ đường truy cập, nhưng không thể bù cho việc application tự tạo ra response chứa dữ liệu quá nhạy cảm.

### 17.1. Startup tags cũng cần được cân nhắc

Nếu code tự tạo startup steps hoặc gắn tags, chỉ dùng giá trị phục vụ phân tích như tên feature hoặc operation category. Không gắn credential, token, email hay payload vào tags.

Startup endpoint có thể lưu các tags trong buffer và trả chúng cho caller được phép. Hãy xem chúng như một dạng telemetry data.

### 17.2. Health reason nên ổn định và ít thông tin

Một reason như `database unavailable` thường hữu ích hơn exception thô chứa hostname, SQL statement hoặc user. Chi tiết điều tra sâu có thể được ghi vào log nội bộ đã được redaction và phân quyền phù hợp.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `/actuator/health` hoạt động nhưng `/actuator/beans` trả 404 | Beans không được HTTP exposed hoặc disabled | Kiểm tra enablement và exposure |
| `/actuator/startup` không có dữ liệu | Chưa cấu hình BufferingApplicationStartup | Cấu hình recorder trước khi chạy app |
| Beans trả 401 | Caller chưa authenticated | Dùng identity được cấp quyền |
| Beans trả 403 | Caller không có role admin | Kiểm tra role/authority mapping |
| Health chỉ có status | `show-details=never` hoặc caller không authorized | Đây có thể là behavior đúng theo policy |
| Health details lộ cho user thường | `show-details=always` hoặc roles quá rộng | Thu hẹp disclosure và role |
| Readiness DOWN dù process còn chạy | Dependency cần cho readiness chưa sẵn sàng | Xem indicator/group và semantics |
| Liveness DOWN khi database tạm lỗi | DB bị đưa vào liveness không phù hợp | Tách liveness khỏi readiness |
| Beans list quá lớn | Context chứa nhiều module/bean | Lọc theo nhu cầu, kiểm tra module composition |
| Startup endpoint không thấy step mong đợi | Buffer capacity, recorder hoặc instrumentation | Kiểm tra cấu hình và startup lifecycle |
| Custom security chain làm endpoint mở ngoài ý muốn | Chain không có rule phù hợp hoặc không có catch-all chain | Review toàn bộ filter chain/matcher |
| Management port bị public | Ingress/firewall route quá rộng | Tách internal service và network policy |
| MockMvc test pass nhưng cluster probe fail | Network path/port/path khác test context | Kiểm tra deployment topology thực tế |

## 19. Quy trình xử lý sự cố thực tế

Khi được giao điều tra “service không khỏe”, “thiếu bean” hoặc “startup chậm”, hãy phân loại trước.

### 19.1. Service không khỏe

1. Đọc status tổng quát.
2. Xác định health group nào DOWN.
3. Chỉ xem details khi có quyền.
4. Tìm contributor gây trạng thái xấu.
5. Kiểm tra dependency và timeout.
6. Không công bố exception/secret trong response.
7. Xác nhận liveness/readiness được thiết kế đúng.

### 19.2. Bean không được đăng ký

1. Kiểm tra beans endpoint trong môi trường nội bộ.
2. Xác nhận bean name/type và context.
3. Kiểm tra package scan và module configuration.
4. Kiểm tra profile/conditional configuration.
5. Kiểm tra dependency có trong runtime classpath.
6. Sửa source/configuration và viết test boundary.

### 19.3. Startup chậm

1. Xác nhận BufferingApplicationStartup được bật từ trước khi run.
2. Đọc startup steps.
3. Tìm những step có duration cao.
4. Đối chiếu startup logs và external calls.
5. Kiểm tra bean initialization, migrations và network dependencies.
6. Tối ưu đúng bước đã xác định.
7. Đo lại trong cùng điều kiện.

### 19.4. Endpoint không truy cập được

Kiểm tra lần lượt endpoint enabled, exposure, base path, management port, network route, authentication, role mapping và response policy. Đừng mở wildcard exposure chỉ để loại trừ một nguyên nhân.

## 20. Checklist trước khi công bố endpoint

Trước khi bật một endpoint trong môi trường dùng chung hoặc production, hãy xác định:

1. Ai cần dữ liệu và mục đích cụ thể là gì?
2. Endpoint có thực sự cần thiết không?
3. Dữ liệu có thể tiết lộ class names, topology, secrets hoặc user information không?
4. Có thể chỉ trả status/summary thay vì full details không?
5. Endpoint có nằm trong HTTP/JMX allowlist không?
6. Caller có authentication phù hợp không?
7. Role/authority có giới hạn đúng người không?
8. Management listener có nằm trong internal network không?
9. Có audit/log access phù hợp không?
10. Có negative security tests không?
11. Có review lại khi nâng cấp dependency hoặc thêm endpoint không?
12. Có thời hạn đóng exposure nếu chỉ phục vụ incident không?

Đối với ba endpoint trong bài:

| Endpoint | Default HTTP exposure trong cấu hình chuẩn | Dữ liệu chính | Policy gợi ý |
| --- | --- | --- | --- |
| `health` | Có | Status, optional components/details | Probe chỉ status; admin xem details |
| `beans` | Không | Bean inventory/dependency metadata | Chỉ admin/SRE nội bộ |
| `startup` | Không | Startup steps/durations/tags | Chỉ admin/SRE, bật recorder có chủ đích |

Endpoint `startup` cần recorder phù hợp; `beans` và `startup` không nên được xem như public API.

## 21. Bài tập thực hành

### Bài tập 1 — Bật Actuator

Thêm `spring-boot-starter-actuator` vào một ứng dụng MVC. Gọi `/actuator/health` và ghi lại response status. Kiểm tra vì sao `/actuator/beans` chưa chắc truy cập được theo default exposure.

### Bài tập 2 — Tạo custom HealthIndicator

Viết `BillingHealthIndicator` kiểm tra một dependency giả lập. Trả về UP/DOWN và chỉ dùng reason an toàn. Không đưa URL có credential hoặc exception thô vào details.

### Bài tập 3 — Giới hạn health details

Đặt `show-details=never` và `show-components=never`. Sau đó đổi sang `when-authorized` với role `ACTUATOR_ADMIN`. So sánh response của anonymous, user thường và admin.

### Bài tập 4 — Thiết kế liveness/readiness

Bật health probes. Đưa `livenessState` vào liveness group và xác định dependency nào thực sự cần thiết cho readiness. Giải thích vì sao database tạm thời DOWN không nhất thiết phải làm process bị restart liên tục.

### Bài tập 5 — Quan sát bean inventory

Expose `beans` trong môi trường local. Tìm một service, repository và configuration bean. Ghi lại những thông tin kiến trúc có thể suy ra từ response và đề xuất ai được phép xem.

### Bài tập 6 — Bật startup recording

Cấu hình `BufferingApplicationStartup` với capacity phù hợp. Bật startup endpoint và truy cập `/actuator/startup`. Xác định một số startup steps và duration; giải thích giới hạn của buffer.

### Bài tập 7 — Tách startup endpoint khỏi info

Cấu hình `info` chỉ trả tên/version đã được duyệt và `startup` dành cho admin. Giải thích vì sao hai endpoint có audience và disclosure risk khác nhau.

### Bài tập 8 — SecurityFilterChain

Tạo chain riêng cho Actuator: health permitAll, beans/startup yêu cầu `ACTUATOR_ADMIN`, endpoint khác deny. Tạo chain thứ hai bảo vệ application routes. Kiểm tra anonymous, user thường và admin.

### Bài tập 9 — Management port

Đặt application port 8080 và management port 9001. Cấu hình network để chỉ monitoring/admin network truy cập port 9001. Xác nhận port quản trị không được route qua public ingress.

### Bài tập 10 — Security regression tests

Viết test xác nhận anonymous không đọc được beans, user thường bị 403, admin đọc được beans và health details chỉ xuất hiện cho role được phép. Thêm negative test cho endpoint ngoài allowlist.

### Bài tập 11 — Điều tra startup chậm

Dùng startup endpoint để xác định bước khởi tạo có duration lớn. Đối chiếu logs và xác định đó là bean creation, migration hay external dependency. Đề xuất cách đo lại sau khi sửa.

### Bài tập 12 — Review disclosure

Tạo một response health có chi tiết giả lập chứa hostname, connection string và token. Thiết kế lại để chỉ trả trạng thái và reason an toàn. Viết test xác nhận marker secret không xuất hiện trong response.

## 22. Ghi nhớ

Spring Boot Actuator giúp quan sát trạng thái ứng dụng, bean graph và startup process. `/actuator/health` phục vụ health status và có thể cung cấp components/details; `/actuator/beans` cho biết bean inventory; `/actuator/startup` cung cấp startup steps khi ứng dụng được cấu hình `BufferingApplicationStartup`.

Trong cấu hình Spring Boot tiêu chuẩn, HTTP exposure mặc định chỉ gồm health. Muốn dùng beans hoặc startup cần enable/expose phù hợp và giới hạn caller. Health details nên để `never` hoặc `when-authorized` với role rõ ràng. Beans và startup chứa metadata nội bộ nên chỉ dành cho admin/SRE trong mạng được kiểm soát.

Hãy kết hợp allowlist exposure, Spring Security authorization, management port/network policy, response minimization và negative tests. Health probe chỉ cần status; người vận hành mới có thể cần details. Developer/SRE có thể cần bean inventory hoặc startup timings nhưng người dùng cuối không cần các thông tin đó.

**Quan sát tốt là quan sát đủ để ra quyết định, trong phạm vi người gọi được phép.** Không expose mọi endpoint để thuận tiện debug, không đưa secrets vào health details hoặc startup tags, và luôn xác nhận cả truy cập được phép lẫn bị từ chối trong đúng môi trường triển khai.
