# Expose endpoint theo môi trường

Spring Boot Actuator cung cấp các endpoint để kiểm tra sức khỏe ứng dụng, đọc metrics, xem cấu hình runtime và quan sát cấu trúc module. Nhưng **một endpoint tồn tại trong ứng dụng không có nghĩa endpoint đó tự động được mở qua HTTP**. Ta cần quyết định endpoint nào được expose ở từng môi trường, ai được phép truy cập, và endpoint được đặt trên cổng mạng nào.

Trong ứng dụng **Spring Modulith**, endpoint `/actuator/modulith` có thể cung cấp cấu trúc application module và các dependency đã nhận diện. Các endpoint `health`, `metrics` và `prometheus` hỗ trợ vận hành; tracing exporter và backend lại là một pipeline riêng. Vì vậy, cấu hình exposure cần cân bằng giữa khả năng quan sát và mức độ thông tin nội bộ được công khai.

Bài thuộc chương **Actuator và vận hành** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mô-đun hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation.

> Ví dụ chính trong bài dựa trên Spring Boot 4.2 và Spring Modulith 2.2. Các property cơ bản có thể khác ở nhánh Spring Boot cũ; đặc biệt mô hình endpoint access và package của Spring Security thay đổi theo major version. Hãy đối chiếu đúng BOM của dự án trước khi sao chép cấu hình.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt endpoint được **đăng ký**, được **cho phép truy cập** và được **expose qua HTTP/JMX**.
2. Dùng `management.endpoints.web.exposure.include` và `exclude` để chọn endpoint theo môi trường.
3. Tổ chức cấu hình chung và profile-specific cho local, staging và production.
4. Hiểu `management.endpoints.access.default`, `management.endpoint.<id>.access` và `max-permitted`.
5. Bảo vệ endpoint bằng Spring Security, cổng quản trị riêng và mạng nội bộ.
6. Giới hạn thông tin health, env và configprops được trả về.
7. Expose Spring Modulith `modulith` endpoint đúng cách và hiểu dữ liệu endpoint cung cấp.
8. Kiểm tra cấu hình bằng Actuator discovery page, HTTP status và các lệnh curl.
9. Chẩn đoán lỗi 404, 401, 403 và trường hợp endpoint không có trong application context.

## 2. Endpoint có sẵn không đồng nghĩa endpoint đã được expose

Spring Boot Actuator cung cấp các endpoint như:

| Endpoint ID | Mục đích | Lưu ý vận hành |
| --- | --- | --- |
| `health` | Tình trạng ứng dụng và health contributors | Có thể chứa chi tiết database, disk, broker nếu cho phép hiển thị |
| `info` | Thông tin ứng dụng do cấu hình cung cấp | Chỉ đưa thông tin phù hợp để công khai |
| `metrics` | Khám phá và đọc meters trong ứng dụng | Có thể tiết lộ tên metric, tags và cấu trúc nội bộ |
| `prometheus` | Xuất metrics cho Prometheus scrape | Cần Micrometer Prometheus registry |
| `loggers` | Đọc và thay đổi mức log runtime | Có operation ghi; nên giới hạn quyền |
| `env` | Xem environment properties | Có thể chứa thông tin nhạy cảm; mặc định sanitize values |
| `configprops` | Xem các configuration properties đã bind | Có thể tiết lộ cấu trúc cấu hình |
| `beans` | Danh sách Spring beans | Tiết lộ thành phần và cấu trúc ứng dụng |
| `conditions` | Kết quả auto-configuration conditions | Hữu ích khi debug local |
| `mappings` | Các request mappings | Có thể tiết lộ API nội bộ |
| `threaddump` | Thread dump | Dữ liệu lớn và nhạy cảm khi có tải |
| `heapdump` | Tải heap dump | Có thể rất lớn và chứa dữ liệu nhạy cảm trong bộ nhớ |
| `shutdown` | Tắt ứng dụng qua endpoint | Bị vô hiệu hóa mặc định; không bật nếu không có yêu cầu rõ ràng |
| `modulith` | Cấu trúc application module và dependency | Cần Spring Modulith Actuator support |

Endpoint chỉ có thể được sử dụng khi **access được cho phép** và endpoint được **expose qua công nghệ tương ứng**. Với HTTP, endpoint ID thường được ánh xạ dưới prefix `/actuator`, ví dụ `health` thành `/actuator/health`.

### 2.1. Ba lớp cần kiểm tra

~~~mermaid
flowchart TD
    A["Endpoint có được tạo/auto-configure?"] --> B{"Access có được phép?"}
    B -->|"Không"| X["Endpoint không khả dụng<br/>có thể bị loại khỏi ApplicationContext"]
    B -->|"Có"| C{"Đã expose qua HTTP/JMX?"}
    C -->|"Không"| Y["Không có route qua công nghệ đó"]
    C -->|"Có"| D{"Network và Security cho phép?"}
    D -->|"Không"| Z["Kết nối bị chặn / 401 / 403"]
    D -->|"Có"| E["Client truy cập endpoint"]
~~~

Ba lớp có ý nghĩa khác nhau:

1. **Endpoint availability/access:** endpoint có được tạo và được phép thực hiện operation hay không.
2. **Exposure:** endpoint có được mở qua HTTP hoặc JMX hay không.
3. **Network/security:** client có tới được cổng và vượt qua xác thực/phân quyền hay không.

Chỉ đổi `include` không thể thay thế access policy hoặc Spring Security.

## 3. Exposure mặc định và include/exclude

Theo tài liệu Spring Boot 4.2, mặc định chỉ endpoint `health` được expose qua **HTTP và JMX**. Đây là lý do gọi `/actuator/metrics` hoặc `/actuator/modulith` có thể trả 404 dù ứng dụng đã có Actuator.

Hai property chính cho HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - prometheus
        exclude:
          - env
          - beans
~~~

- `include` liệt kê endpoint ID được expose.
- `exclude` liệt kê endpoint ID cần loại khỏi exposure.
- **`exclude` có độ ưu tiên cao hơn `include`**. Nếu một ID có mặt ở cả hai danh sách, endpoint bị loại.
- Có thể dùng `*` để chọn tất cả, nhưng trong YAML phải đặt trong dấu nháy.

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - beans
          - shutdown
~~~

Cấu hình này mở rất nhiều endpoint và chỉ loại một số ID. Nó phù hợp hơn cho một lab cô lập, không nên được dùng như cấu hình mặc định cho production.

### 3.1. HTTP và JMX là hai exposure độc lập

Cấu hình HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Cấu hình JMX:

~~~yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info"
~~~

Exposing `prometheus` qua HTTP không tự động expose nó qua JMX; và ngược lại. Hãy chọn công nghệ mà hệ thống monitoring thực sự sử dụng.

### 3.2. Endpoint phải có dependency tương ứng

Một endpoint không xuất hiện trong discovery page có thể do thiếu dependency hoặc điều kiện auto-configuration không thỏa mãn.

Ví dụ:

- `prometheus` cần `micrometer-registry-prometheus`.
- `modulith` cần `spring-modulith-actuator` hoặc starter tổng hợp phù hợp.
- `heapdump` phụ thuộc loại web application/JVM và endpoint support.
- `shutdown` bị vô hiệu hóa mặc định.

Với Spring Modulith 2.2, cách thuận tiện để có Actuator support và observability là starter `spring-modulith-starter-insight`:

~~~gradle
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Starter này đưa Actuator và Modulith observability support vào ứng dụng; exporter/tracer và registry cho hệ thống monitoring vẫn có thể cần dependency riêng.

Nếu chỉ cần endpoint module, có thể dùng `spring-modulith-actuator` cùng `spring-boot-starter-actuator` theo tài liệu phiên bản tương ứng. Khi dependency có mặt, endpoint ID là `modulith` và URL mặc định là `/actuator/modulith`.

## 4. Access level trong Spring Boot 4.2

Spring Boot 4.2 có mô hình **endpoint access** riêng. Property mặc định cho access toàn cục là:

`management.endpoints.access.default`

Giá trị access có thể là:

| Giá trị | Ý nghĩa |
| --- | --- |
| `none` | Không cho phép endpoint hoạt động |
| `read-only` | Chỉ cho phép các operation đọc |
| `unrestricted` | Cho phép mọi operation được endpoint cung cấp |

Ví dụ opt-in: mặc định cấm tất cả, chỉ cho phép đọc health, info và Modulith:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    modulith:
      access: read-only
~~~

Có thể đặt access riêng cho từng endpoint bằng `management.endpoint.<id>.access`. Endpoint không được phép truy cập sẽ bị loại khỏi application context. Nếu mục tiêu chỉ là thay đổi công nghệ expose, hãy dùng `include`/`exclude` thay vì thay đổi access.

### 4.1. Giới hạn access tối đa

`management.endpoints.access.max-permitted` đặt mức access tối đa được phép trên toàn ứng dụng. Property này có ưu tiên cao hơn default access hoặc access riêng từng endpoint.

Ví dụ chỉ cho phép read-only:

~~~yaml
management:
  endpoints:
    access:
      default: unrestricted
      max-permitted: read-only
~~~

Dù một endpoint được cấu hình `unrestricted`, giới hạn `max-permitted: read-only` vẫn ngăn các operation ghi/xóa. Đây là một hàng rào hữu ích khi muốn bảo đảm profile không vô tình bật operation thay đổi trạng thái.

**Phân biệt:** access level không tự expose endpoint. Endpoint vẫn phải nằm trong `management.endpoints.web.exposure.include` hoặc danh sách JMX tương ứng.

## 5. Cấu hình theo môi trường bằng Spring Profiles

Một cấu trúc dễ quản lý là đặt cấu hình chung trong `application.yml`, rồi ghi đè danh sách exposure theo profile:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
└── application-prod.yml
~~~

Trong Spring Boot, khi một property dạng list được khai báo lại ở profile có độ ưu tiên cao hơn, danh sách ở nguồn cấu hình đó **thay thế danh sách trước đó**, không tự nối thêm phần tử. Vì vậy, mỗi profile ở ví dụ dưới đây đều liệt kê lại `health` nếu vẫn cần endpoint này.

Profile được kích hoạt bằng biến môi trường `SPRING_PROFILES_ACTIVE` hoặc tham số chạy ứng dụng. Ví dụ:

~~~bash
java -jar shop-modulith.jar --spring.profiles.active=local
~~~

### 5.1. Cấu hình chung: chỉ expose health

`application.yml`:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

Đây là mức mặc định an toàn cho các môi trường chưa có profile cụ thể. Chỉ health được expose; chi tiết và danh sách components không được hiển thị.

### 5.2. Local development: expose endpoint phục vụ debug

`application-local.yml`:

~~~yaml
management:
  endpoints:
    access:
      default: unrestricted
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - prometheus
          - loggers
          - beans
          - conditions
          - mappings
          - modulith
        exclude:
          - shutdown
  endpoint:
    shutdown:
      access: none
    health:
      show-details: always
      show-components: always
~~~

Local có thể expose thêm endpoint để debug bean, conditions, mappings, loggers và module graph. Cấu hình này chỉ nên dùng trên máy phát triển hoặc môi trường cô lập, không mở cổng quản trị ra Internet.

Nếu local app có dữ liệu thật hoặc chạy trong mạng dùng chung, hãy áp dụng Spring Security và chỉ expose những endpoint cần thiết. Việc dùng profile `local` không tự bảo đảm máy chủ chỉ truy cập từ localhost.

### 5.3. Staging: chỉ mở endpoint cần cho kiểm thử/vận hành

`application-staging.yml`:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - prometheus
          - modulith
  endpoint:
    health:
      access: read-only
      show-details: when-authorized
      roles:
        - OPS
    info:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
    modulith:
      access: read-only
~~~

Staging mở các endpoint phục vụ health check, metrics scrape và kiểm tra cấu trúc module. Mọi endpoint được giới hạn ở read-only; các endpoint khác mặc định không có access.

Nếu không cần xem module graph ở staging, hãy bỏ `modulith` khỏi danh sách. Endpoint này có thể tiết lộ tên module, package gốc và dependency nội bộ.

### 5.4. Production: exposure tối thiểu và management port riêng

`application-prod.yml`:

~~~yaml
management:
  server:
    port: 8081

  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - info
          - prometheus
      discovery:
        enabled: false

  endpoint:
    health:
      access: read-only
      show-details: when-authorized
      roles:
        - OPS
    info:
      access: read-only
    prometheus:
      access: read-only
~~~

Ở cấu hình này:

- HTTP management server lắng nghe cổng riêng `8081`.
- Prefix endpoint đổi từ `/actuator` sang `/manage`.
- Chỉ expose `health`, `info` và `prometheus`.
- Các endpoint còn lại bị access default chặn.
- Discovery page bị tắt để không công bố danh sách link endpoint.

Ví dụ URL health là `http://host:8081/manage/health` và Prometheus scrape là `http://host:8081/manage/prometheus`.

Nếu đội vận hành cần module graph ở production, hãy bổ sung `modulith` vào exposure list và access read-only, đồng thời bảo vệ endpoint bằng mạng nội bộ và Spring Security. Đừng mở endpoint này công khai chỉ để tiện xem sơ đồ.

### 5.5. Chọn profile không tự thay thế kiểm soát mạng

Spring Profiles giúp chọn cấu hình, nhưng profile không phải security boundary. Hãy kiểm tra profile active tại runtime, nguồn cấu hình có độ ưu tiên cao hơn (environment variables, command-line args, config server) và cấu hình triển khai.

Không đặt mật khẩu hoặc token trong file profile được commit. Dùng secret store hoặc biến môi trường và cấu hình authentication riêng.

## 6. Bảo vệ endpoint bằng Spring Security

Exposure chỉ làm endpoint có route; nó không tự xác thực người gọi. Nếu Spring Security có mặt trên classpath và không có custom `SecurityFilterChain`, Spring Boot auto-configuration bảo vệ các actuator endpoint ngoại trừ health theo cấu hình mặc định.

Nếu ứng dụng tự định nghĩa một bean `SecurityFilterChain`, auto-configuration bảo mật của Spring Boot **back off hoàn toàn**. Khi đó, ứng dụng phải tự khai báo rules cho Actuator và các route còn lại.

### 6.1. Chỉ cho role OPS truy cập Actuator

Ví dụ Spring Boot 4.2, Spring MVC/Servlet:

~~~java
package com.example.shop.config;

import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize ->
                authorize.anyRequest().hasRole("OPS"));
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là ví dụ phân vùng hai filter chains: chain đầu chỉ áp dụng cho Actuator, chain thứ hai bảo vệ phần còn lại của ứng dụng. Hệ thống thật cần bổ sung user/role provider, authentication mechanism, CSRF policy và quy tắc truy cập nghiệp vụ phù hợp.

Với Spring Boot 3.x, package của `EndpointRequest` thường là `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest`. Không copy import Boot 4.x sang Boot 3.x mà chưa kiểm tra API.

### 6.2. Chỉ mở endpoint health cho probe

Nếu load balancer hoặc orchestrator cần health check không xác thực, có thể tạo rule riêng cho health endpoint và giữ các endpoint khác cần role OPS. Dùng `EndpointRequest.to("health")` để match endpoint thay vì viết path string dễ sai khi đổi base path.

Không nên mở tất cả Actuator chỉ vì health check cần truy cập ẩn danh.

### 6.3. CSRF với endpoint có operation ghi

Spring Security bật CSRF protection mặc định. Endpoint có operation POST/PUT/DELETE như `loggers` hoặc `shutdown` có thể trả 403 khi thiếu CSRF token trong cấu hình bảo mật mặc định.

Đừng tắt CSRF toàn ứng dụng chỉ để một endpoint vận hành hoạt động. Nếu có nhu cầu thay đổi log level, thiết kế quyền OPS và quy tắc CSRF riêng cho endpoint đó; tốt hơn nữa là giới hạn exposure và quyền ghi theo nhu cầu thực tế.

## 7. Quản lý management port và base path

### 7.1. Dùng port riêng

`management.server.port` cho phép Actuator chạy trên port khác với ứng dụng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

Khi đó:

- API nghiệp vụ: `http://localhost:8080`.
- Actuator: `http://localhost:8081/actuator`.

Có thể giới hạn địa chỉ bind bằng `management.server.address` khi management port khác application port. Ví dụ `127.0.0.1` chỉ cho client trên cùng network namespace/host truy cập loopback; Prometheus chạy trong container hoặc host khác sẽ không thể kết nối vào loopback của container ứng dụng.

Nếu Prometheus hoặc platform monitoring ở máy/container khác, hãy bind vào interface nội bộ thích hợp và giới hạn bằng firewall, Kubernetes NetworkPolicy, service mesh hoặc ingress private. **Cổng riêng không tự tạo xác thực hay mã hóa.**

### 7.2. Đổi base path

`management.endpoints.web.base-path` thay prefix mặc định:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Đường dẫn `/actuator/health` đổi thành `/manage/health`. Khi management server dùng port riêng, path được tính tương đối theo management server context; nếu cùng port, nó liên quan servlet context path hoặc WebFlux base path.

Đổi base path không phải biện pháp bảo mật. Không dựa vào URL khó đoán để bảo vệ endpoint.

### 7.3. Tắt HTTP Actuator hoàn toàn

Nếu ứng dụng chỉ quản lý qua JMX hoặc một kênh khác và không cần HTTP endpoints, có thể dùng:

~~~yaml
management:
  server:
    port: -1
~~~

Hoặc loại toàn bộ web exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
~~~

Hai cách tác động tới HTTP exposure; JMX có cấu hình riêng. Hãy xác minh monitoring stack không còn phụ thuộc HTTP Actuator trước khi tắt.

## 8. Kiểm soát thông tin nhạy cảm

Một số endpoint có thể tiết lộ thông tin sâu về ứng dụng:

- `env` và `configprops` có thể phản ánh property names và cấu trúc cấu hình.
- `beans`, `conditions` và `mappings` có thể tiết lộ component và API nội bộ.
- `heapdump` có thể chứa object, payload và dữ liệu đang nằm trong bộ nhớ.
- `threaddump` có thể tiết lộ tên thread, class, stack và thông tin vận hành.
- `modulith` có thể tiết lộ base package, tên module và quan hệ dependency.

### 8.1. Sanitize values của env và configprops

Spring Boot mặc định sanitize values của `env` và `configprops` thành `******`. Với các endpoint hỗ trợ sanitization, `show-values` có thể là:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Luôn che giá trị |
| `always` | Hiển thị cho mọi người nếu không có SanitizingFunction áp dụng |
| `when-authorized` | Chỉ hiển thị cho người được xác thực/ủy quyền theo roles |

Ví dụ chỉ role ADMIN được xem giá trị chưa sanitize của `env`:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ADMIN
~~~

Đây không phải lý do để expose `env` công khai. Sanitization là lớp bảo vệ dữ liệu, còn exposure và authorization vẫn cần được cấu hình riêng.

### 8.2. Giới hạn chi tiết health

Trong production, thường nên dùng:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles:
        - OPS
~~~

Mặc định `show-details` và `show-components` là `never`. Chỉ bật `always` trong lab hoặc môi trường có kiểm soát, vì thông tin contributor có thể tiết lộ dependency nội bộ và trạng thái hệ thống.

### 8.3. Không đưa secrets vào info

Endpoint `info` hiển thị metadata do ứng dụng cung cấp. Có thể dùng build info, git commit hoặc version; không đưa password, token, internal hostname, connection string hoặc thông tin cá nhân vào `info` chỉ để thuận tiện debug.

## 9. Expose Spring Modulith endpoint

Spring Modulith có thể expose kiến trúc module qua Actuator endpoint ID `modulith`. Với Spring Modulith 2.2, `spring-modulith-starter-insight` là lựa chọn thuận tiện vì bao gồm Actuator và observability support.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - modulith
  endpoint:
    modulith:
      access: read-only
~~~

Khi truy cập `GET /actuator/modulith`, response JSON có thể chứa:

| Trường | Ý nghĩa |
| --- | --- |
| Key cấp đầu | Technical name của application module |
| `displayName` | Tên hiển thị |
| `basePackage` | Package gốc của module |
| `parent` / `nested` | Thông tin module lồng nhau nếu có |
| `dependencies[]` | Các dependency đi ra từ module |
| `dependencies[].target` | Module đích |
| `dependencies[].types[]` | Kiểu dependency như `DEFAULT`, `USES_COMPONENT` hoặc `EVENT_LISTENER` |

Endpoint này là **ảnh chụp cấu trúc module đã được nhận diện từ code**. Nó không phải trace history, không đếm số lần module được gọi và không cho biết listener đã xử lý event thành công.

### 9.1. Kết hợp modulith với metrics và tracing

| Câu hỏi vận hành | Nguồn nên dùng |
| --- | --- |
| Ứng dụng có những module nào và phụ thuộc ra sao? | `/actuator/modulith` |
| Có bao nhiêu event được công bố? | `module.events.published` qua `/actuator/metrics` hoặc Prometheus |
| Một request cụ thể đi qua module nào? | Module entry spans trong tracing backend |
| Listener đã hoàn tất hay retry? | Event Publication Registry và logs |
| Ứng dụng có sẵn sàng nhận traffic không? | `/actuator/health` và health probes |

Expose endpoint `modulith` không tự bật tracing exporter. Muốn có trace cần thêm instrumentation, Micrometer Tracing/OpenTelemetry hoặc Brave và exporter phù hợp.

## 10. Kiểm tra cấu hình đang chạy

### 10.1. Xác nhận profile active

Khởi động với profile mong muốn:

~~~bash
java -jar shop-modulith.jar --spring.profiles.active=staging
~~~

Hoặc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Trong môi trường container, cấu hình profile thường được truyền từ deployment manifest hoặc environment variables. Hãy xác minh runtime nhận đúng profile; file profile có tồn tại không có nghĩa nó đang active.

### 10.2. Xem discovery page

Với cấu hình mặc định, gọi:

~~~bash
curl -i http://localhost:8080/actuator
~~~

Discovery page liệt kê links tới các endpoint đang expose. Nếu `management.endpoints.web.discovery.enabled=false`, discovery page bị tắt nhưng endpoint riêng vẫn có thể hoạt động.

### 10.3. Kiểm tra endpoint cụ thể

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
curl -i http://localhost:8080/actuator/modulith
~~~

Nếu management port riêng và base path là `/manage`, thay URL bằng `http://localhost:8081/manage/...`. Khi endpoint cần xác thực, dùng credential từ secret manager hoặc cơ chế auth của môi trường; không ghi mật khẩu thật vào shell history hay tài liệu.

### 10.4. Diễn giải HTTP status

| Kết quả | Ý nghĩa thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `200 OK` | Endpoint đã được route và request được chấp nhận | Kiểm tra payload có đúng profile/dữ liệu mong đợi |
| `401 Unauthorized` | Chưa xác thực hoặc credential không hợp lệ | Authentication provider, token/basic auth |
| `403 Forbidden` | Đã tới security layer nhưng thiếu quyền, hoặc CSRF chặn operation | Role, filter chain, CSRF token |
| `404 Not Found` | Sai port/path, endpoint không được expose, không có dependency hoặc endpoint bị access `none` | Discovery page, include/exclude, access property, dependency |
| Connection refused / timeout | Không tới được management server | Port, bind address, firewall, container network |
| `503 Service Unavailable` từ health | Health status báo ứng dụng/dependency không sẵn sàng | Health contributors và nguyên nhân trạng thái DOWN |

Một response 404 không đủ để kết luận endpoint chưa được cài; hãy kiểm tra cả dependency, access, exposure và management base path.

## 11. Những lỗi cấu hình thường gặp

| Sai sót | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `include: "*"` không đặt dấu nháy | YAML parse sai hoặc cấu hình không như mong đợi | Dùng `"*"` |
| `exclude` chỉ bị coi là gợi ý | Endpoint trong exclude vẫn bị loại dù có trong include | Kiểm tra exclude precedence |
| Nhầm HTTP exposure với JMX exposure | Monitoring dùng JMX không thấy endpoint mong muốn | Cấu hình đúng nhóm web hoặc jmx |
| Chỉ đổi `include`, bỏ qua endpoint access | Endpoint có thể không được tạo vì access `none` | Kiểm tra `management.endpoints.access.*` |
| Dùng custom `SecurityFilterChain` nhưng quên Actuator | Auto-config security backs off; endpoint có thể thiếu rule | Tạo chain riêng cho Actuator và ứng dụng |
| Expose `env`/`configprops` để debug production | Tiết lộ cấu trúc cấu hình | Giữ kín, dùng `show-values` và roles phù hợp |
| Expose `heapdump` trên mạng công khai | Rủi ro dữ liệu nhạy cảm và tải lớn | Không expose hoặc chỉ dùng kênh quản trị hạn chế |
| Expose `modulith` công khai | Tiết lộ module names, packages và dependencies | Giới hạn mạng, auth và exposure |
| Chỉ mở port riêng nhưng không giới hạn network | Bất kỳ client tới được port vẫn có thể thử endpoint | Firewall/NetworkPolicy và Security |
| Dùng profile local trên production | Mở nhiều endpoint debug | Xác minh `SPRING_PROFILES_ACTIVE` và config precedence |

## 12. Quy trình thiết kế exposure theo môi trường

Khi thêm một endpoint mới, thực hiện lần lượt:

1. **Xác định câu hỏi cần trả lời:** health check, scrape metrics, xem module graph hay debug cấu hình?
2. **Xác định client:** kubelet, Prometheus, operator, developer hay dashboard nội bộ?
3. **Chọn endpoint ID:** chỉ thêm đúng ID cần thiết.
4. **Chọn công nghệ:** HTTP, JMX hoặc cả hai nếu có lý do.
5. **Đặt access level:** mặc định none rồi opt-in read-only cho endpoint cần đọc.
6. **Đặt exposure theo profile:** local/staging/prod có danh sách riêng.
7. **Bảo vệ network và authentication:** management port riêng, internal network, Spring Security.
8. **Kiểm soát payload:** health details, env/configprops sanitization, thông tin Modulith.
9. **Kiểm tra runtime:** profile active, discovery page, HTTP status, payload và logs.
10. **Theo dõi thay đổi:** khi thêm endpoint hoặc đổi dependency, cập nhật policy và kiểm tra lại.

### 12.1. Checklist trước khi triển khai production

- [ ] Chỉ expose endpoint thực sự cần.
- [ ] `include` không dùng wildcard nếu không có yêu cầu rõ.
- [ ] `exclude` được rà soát và có độ ưu tiên như mong muốn.
- [ ] Endpoint access default và max-permitted phù hợp.
- [ ] Các endpoint thay đổi trạng thái bị giới hạn hoặc vô hiệu hóa.
- [ ] Health details không hiển thị cho người dùng không được phép.
- [ ] `env` và `configprops` không làm lộ secrets.
- [ ] Actuator port chỉ reachable từ network quản trị/monitoring.
- [ ] SecurityFilterChain bao phủ cả Actuator và application routes.
- [ ] Profile active được xác minh tại runtime.
- [ ] Prometheus và Modulith endpoints có dependency cần thiết.
- [ ] Discovery page được bật/tắt theo yêu cầu.
- [ ] Đã thử request không xác thực, user sai role và monitoring client hợp lệ.

## 13. Bài thực hành

### Bài 1 — Tạo ba profile

Tạo `application.yml`, `application-local.yml`, `application-staging.yml` và `application-prod.yml` theo các ví dụ ở trên. Chạy từng profile và ghi endpoint nào xuất hiện ở discovery page.

### Bài 2 — Kiểm tra include/exclude

Expose `health,info,metrics,prometheus,modulith`, sau đó thêm `exclude: modulith`. Kiểm tra vì sao `/actuator/modulith` không còn truy cập được dù ID vẫn nằm trong include.

### Bài 3 — Phân biệt access với exposure

Đặt `management.endpoints.web.exposure.include: health,info,modulith`, nhưng `management.endpoints.access.default: none`. Sau đó opt-in read-only cho health và modulith. Quan sát endpoint nào khả dụng và giải thích hai lớp cấu hình.

### Bài 4 — Bảo vệ bằng role OPS

Tạo SecurityFilterChain cho Actuator bằng `EndpointRequest.toAnyEndpoint()`, yêu cầu role `OPS`. Gọi endpoint với user chưa xác thực, user không có role và user OPS. Ghi nhận HTTP status từng trường hợp.

### Bài 5 — Đặt management port riêng

Chuyển Actuator sang port 8081, base path `/manage`. Kiểm tra API nghiệp vụ vẫn ở port 8080, Actuator ở port 8081, và thử truy cập từ một container khác để hiểu tác động của bind address/network.

### Bài 6 — Expose Modulith endpoint

Thêm Spring Modulith Insight starter, expose `modulith` trong local/staging và gọi `/actuator/modulith`. Đọc module keys, basePackage và dependencies; sau đó bỏ `modulith` khỏi production profile và giải thích lý do vận hành.

### Bài 7 — Kiểm tra thông tin nhạy cảm

Thử cấu hình `env.show-values` ở `never`, `when-authorized` và `always` trong môi trường lab. Kiểm tra user thường và user OPS; không dùng secrets thật. Khôi phục `never` sau bài thực hành.

## 14. Câu hỏi ôn tập

1. Khi nào một Actuator endpoint được coi là available?
2. HTTP exposure mặc định của Spring Boot gồm endpoint nào?
3. `include` và `exclude` khác nhau thế nào?
4. Vì sao `exclude` thắng `include`?
5. Tại sao wildcard trong YAML phải đặt trong dấu nháy?
6. Exposure qua HTTP và JMX có liên quan tự động với nhau không?
7. `management.endpoints.access.default` và `management.endpoint.<id>.access` khác nhau thế nào?
8. `max-permitted: read-only` có tác dụng gì?
9. Vì sao custom SecurityFilterChain khiến Spring Boot security auto-configuration backs off?
10. `management.server.port` và `management.endpoints.web.base-path` điều khiển phần nào?
11. Vì sao cổng riêng không tự thay thế firewall hoặc authentication?
12. `show-values: when-authorized` bảo vệ `env` như thế nào?
13. Spring Modulith endpoint có thể tiết lộ loại thông tin nào?
14. Vì sao `module graph`, event metrics và tracing là các nguồn quan sát khác nhau?
15. Làm thế nào phân biệt 404 do exposure với 401/403 do security?

## 15. Ghi nhớ

**Expose endpoint theo môi trường là quyết định về khả năng truy cập vận hành.** Hãy tách endpoint access, công nghệ exposure (HTTP/JMX), và network/security thành các lớp riêng. Spring Boot mặc định chỉ expose `health`; `include` chọn endpoint, `exclude` loại endpoint và có độ ưu tiên cao hơn. Spring Boot 4.2 còn cho phép đặt access default, access riêng và giới hạn tối đa.

Dùng Spring Profiles để local có đủ công cụ debug, staging có endpoint phục vụ kiểm thử và production chỉ mở những gì monitoring thực sự cần. Kết hợp management port riêng, firewall/NetworkPolicy, Spring Security và sanitization để kiểm soát thông tin.

Với Spring Modulith, endpoint `modulith` cung cấp cấu trúc module và dependency; `metrics`/`prometheus` cung cấp số liệu; tracing backend cung cấp đường đi của từng lần thực thi. Không dùng một endpoint để suy ra dữ liệu mà nó không được thiết kế để trả lời.

### Tài liệu tham khảo chính thức

- [Spring Boot 4.2 — Actuator Endpoints: access, exposure, security và sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Monitoring and Management Over HTTP: management port và base path](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).
- [Spring Boot — Common Application Properties: management endpoint properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).
- [Spring Boot — Profiles và externalized configuration](https://docs.spring.io/spring-boot/reference/features/profiles.html).
- [Spring Modulith 2.2 — Production-ready Features: Application Module Actuator](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Security — Servlet Architecture and SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
