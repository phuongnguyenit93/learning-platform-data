# Actuator và lựa chọn có công bố endpoint quản trị hay không

Spring Boot Actuator cung cấp các endpoint phục vụ vận hành ứng dụng như health, metrics, info, loggers và environment. Những endpoint này hữu ích cho monitoring, orchestration và xử lý sự cố, nhưng một số endpoint có thể tiết lộ cấu hình, topology, thông tin runtime hoặc cho phép thay đổi trạng thái hệ thống. Vì vậy, cần quyết định riêng endpoint nào được bật, endpoint nào được expose qua HTTP, ai được truy cập và có nên đưa chúng vào tài liệu OpenAPI hay không.

Springdoc có thể hiển thị các endpoint Actuator trong Swagger UI bằng `springdoc.show-actuator=true`. Tùy chọn này phục vụ việc mô tả tài liệu; nó không tự mở endpoint Actuator ra mạng và cũng không thay thế cấu hình bảo mật của Spring Boot. Quyết định công bố endpoint phải được thực hiện đồng thời ở Actuator exposure, Spring Security, cấu hình cổng quản trị và tài liệu OpenAPI.

## 1. Actuator cung cấp những gì?

Actuator bổ sung các endpoint quản trị vào ứng dụng Spring Boot. Thư viện thường được thêm bằng starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Với ứng dụng dùng Spring MVC và Swagger UI, có thể dùng Springdoc starter tương thích với phiên bản Spring Boot của dự án:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Ứng dụng WebFlux sử dụng starter WebFlux tương ứng. Cần chọn dòng Springdoc tương thích với dòng Spring Boot đang chạy; không sao chép version tùy ý từ một ví dụ khác.

Một số endpoint Actuator thường gặp:

| Endpoint ID | Mục đích | Lưu ý khi công bố |
| --- | --- | --- |
| `health` | Tình trạng tổng quát của ứng dụng và các health indicator | Có thể tiết lộ trạng thái database, broker hoặc dependency nếu hiển thị chi tiết |
| `info` | Thông tin do ứng dụng cung cấp như build/version | Chỉ đưa dữ liệu được phép công khai vào `info` |
| `metrics` | Chỉ số runtime và metric được Micrometer ghi nhận | Có thể tiết lộ tên metric, cấu trúc hệ thống và mức tải |
| `prometheus` | Metric ở định dạng Prometheus khi có registry phù hợp | Thường dành cho hệ thống monitoring nội bộ |
| `loggers` | Xem hoặc thay đổi mức log của logger | Quyền ghi có thể làm thay đổi hành vi logging khi ứng dụng đang chạy |
| `env` | Thuộc tính môi trường và cấu hình | Có nguy cơ lộ thông tin nhạy cảm hoặc cấu trúc triển khai |
| `configprops` | Các thuộc tính cấu hình đã bind vào bean | Có thể tiết lộ cấu hình nội bộ và giá trị nhạy cảm nếu không được che đúng |
| `beans` | Danh sách bean trong ApplicationContext | Tiết lộ cấu trúc nội bộ của ứng dụng |
| `mappings` | Các request mapping đã đăng ký | Tiết lộ route và bề mặt API |
| `threaddump` | Thông tin thread tại thời điểm truy vấn | Có thể chứa thông tin vận hành nhạy cảm và dữ liệu gây tải |
| `heapdump` | Tạo heap dump để phân tích bộ nhớ | Có thể chứa dữ liệu trong bộ nhớ; không nên công bố rộng |
| `shutdown` | Yêu cầu tắt ứng dụng khi endpoint được bật | Có tác động trực tiếp đến tính sẵn sàng; endpoint này bị disable mặc định |

Với các phiên bản Spring Boot hiện hành, mặc định chỉ `health` được expose qua HTTP. Các endpoint khác có thể tồn tại trong ứng dụng nhưng không tự động xuất hiện ở web management path. Cấu hình access control và một số mặc định có thể thay đổi theo phiên bản; hãy đối chiếu tài liệu đúng dòng Spring Boot đang dùng.

## 2. Phân biệt endpoint được bật, được expose và được phép truy cập

Ba khái niệm này không giống nhau:

1. **Enabled/available:** endpoint có được bật và có thể được tạo trong ứng dụng hay không.
2. **Exposed:** endpoint có được đưa ra một phương thức truy cập như HTTP hoặc JMX hay không.
3. **Authorized:** người gửi request có được Spring Security cho phép truy cập endpoint hay không.

Ví dụ, `env` có thể được bật trong ứng dụng nhưng không nằm trong danh sách web exposure. Khi đó, endpoint không xuất hiện tại HTTP management base path. Nếu endpoint được expose qua HTTP, Spring Security vẫn có thể yêu cầu role quản trị.

Tương tự, thêm `health` vào `management.endpoints.web.exposure.include` không đồng nghĩa mọi chi tiết health đều công khai. `management.endpoint.health.show-details` và chính sách xác thực quyết định mức chi tiết được trả về.

Springdoc cũng là một lớp riêng: `springdoc.show-actuator` quyết định có đưa operation Actuator vào tài liệu OpenAPI hay không. Nó không thay thế hai bước enabled/exposure và không cấp quyền truy cập runtime.

## 3. Chỉ expose các endpoint cần thiết

Management endpoint thường có base path mặc định là `/actuator`. Có thể chỉ công bố `health` và `info` qua HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

Trong ví dụ, `/actuator/health` và `/actuator/info` được expose qua HTTP. Chi tiết health chỉ hiển thị cho người có role `OPS` đã xác thực. Health tổng quát có thể được dùng bởi hệ thống giám sát mà không cần công bố thông tin chi tiết của từng dependency.

Nếu cần thêm metrics hoặc Prometheus cho monitoring, chỉ thêm endpoint thật sự cần dùng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Endpoint `prometheus` cần dependency registry phù hợp, ví dụ `micrometer-registry-prometheus`. Việc đưa ID vào `include` không tự cài registry hoặc tạo metric nếu ứng dụng chưa cấu hình Micrometer tương ứng.

Có thể loại trừ endpoint khỏi danh sách expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,configprops,beans,shutdown,heapdump,threaddump
```

Khi dùng wildcard `*`, phải đặt trong dấu nháy để YAML không hiểu đó là ký hiệu đặc biệt. `exclude` giúp loại một số endpoint khỏi danh sách web exposure, nhưng chiến lược an toàn hơn là chỉ include danh sách cần thiết.

## 4. Không nhầm việc ẩn endpoint với việc tắt endpoint

Nếu một endpoint không cần tồn tại trong ứng dụng, có thể disable endpoint đó theo cấu hình Spring Boot. Ví dụ:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

Nếu endpoint chỉ không được công bố qua HTTP nhưng vẫn cần cho JMX hoặc công cụ quản trị khác, giữ endpoint enabled và loại nó khỏi `management.endpoints.web.exposure.include`.

Với các phiên bản Spring Boot hỗ trợ endpoint access control, có thể giới hạn endpoint theo quyền truy cập như read-only hoặc unrestricted bằng các thuộc tính `management.endpoints.access.*` và `management.endpoint.<id>.access`. Cú pháp và khả năng này phụ thuộc phiên bản; hãy đối chiếu tài liệu Spring Boot đang dùng. Dù có access control, vẫn cần kiểm tra exposure và Spring Security.

Không nên bật `shutdown` chỉ để tiện thao tác trên Swagger UI. Một nút thao tác quản trị có thể gây dừng ứng dụng và cần quy trình kiểm soát riêng.

## 5. Kiểm soát chi tiết của Health endpoint

Health thường là endpoint duy nhất được dùng rộng rãi bởi load balancer hoặc orchestrator. Tuy nhiên, trả toàn bộ chi tiết cho mọi người dùng có thể làm lộ tên database, message broker, trạng thái dịch vụ bên thứ ba hoặc thông tin nội bộ.

Ví dụ:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

Các lựa chọn thường gặp cho `show-details` gồm:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Không hiển thị chi tiết health |
| `when-authorized` | Chỉ hiển thị chi tiết cho người đã xác thực và có role phù hợp |
| `always` | Luôn hiển thị chi tiết; chỉ dùng khi môi trường và chính sách cho phép |

Trong Kubernetes, có thể bật health probes để cung cấp liveness và readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Liveness cho biết tiến trình có cần được khởi động lại hay không; readiness cho biết instance có sẵn sàng nhận traffic hay không. Không nên đưa các chi tiết health nội bộ vào tài liệu công khai nếu client bên ngoài không có nhu cầu vận hành tương ứng.

## 6. Springdoc có thể đưa Actuator vào OpenAPI như thế nào?

Mặc định, Springdoc không hiển thị Actuator endpoints trong tài liệu OpenAPI. Khi có nhu cầu tài liệu hóa chúng, bật:

```yaml
springdoc:
  show-actuator: true
```

Springdoc sẽ thêm một group tài liệu riêng cho Actuator endpoints. Nếu ứng dụng chưa có group API riêng, Springdoc cũng có thể tạo group mặc định cho API ứng dụng. Trong Swagger UI, người đọc có thể chọn group Actuator để xem các operation quản trị được hỗ trợ.

Điều này chỉ quyết định việc hiển thị endpoint trong tài liệu. Để gọi được endpoint, Actuator vẫn phải bật và expose qua phương thức tương ứng; Spring Security, network policy và management server vẫn quyết định ai có thể truy cập.

Ví dụ, nếu `health` được expose nhưng `env` không được expose, bật `springdoc.show-actuator=true` không phải lý do để tự mở `env` qua HTTP. Hãy kiểm tra group Actuator được sinh và so sánh với các endpoint thực sự có thể truy cập.

Không bật `show-actuator` chỉ vì muốn có một danh sách endpoint đầy đủ trong Swagger UI. Hãy xác định người đọc tài liệu có thực sự cần gọi endpoint quản trị hay không và liệu nội dung được phép công bố cho họ.

## 7. Khi nào nên đưa Actuator vào tài liệu OpenAPI?

| Tình huống | Quyết định gợi ý | Lý do |
| --- | --- | --- |
| API public cho khách hàng | Thường không đưa Actuator vào group public | Endpoint quản trị không thuộc hợp đồng nghiệp vụ dành cho khách hàng |
| Tài liệu nội bộ cho SRE/operations | Có thể tạo group Actuator riêng và bảo vệ bằng role | Người vận hành cần tra cứu health, metrics hoặc thao tác được cấp quyền |
| Monitoring tự động | Thường dùng endpoint/format chuẩn của Actuator và Prometheus | Monitoring không cần Swagger UI để đọc metric định kỳ |
| Môi trường local/dev | Có thể bật để học tập và debug | Thuận tiện khám phá endpoint trong môi trường kiểm soát |
| Production với management network riêng | Chỉ công bố tài liệu trên cổng quản trị nếu có nhu cầu | Tách bề mặt quản trị khỏi cổng ứng dụng |

OpenAPI thường phù hợp với hợp đồng API mà client cần tích hợp. Actuator lại phục vụ quản trị và vận hành. Có thể tài liệu hóa cả hai, nhưng nên tách group, đối tượng sử dụng và quyền truy cập rõ ràng.

## 8. Tách management port khỏi application port

Spring Boot cho phép phục vụ Actuator trên cổng quản trị riêng:

```yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,info,openapi,swagger-ui

springdoc:
  use-management-port: true
```

Với cấu hình Springdoc hỗ trợ Actuator management port, `openapi` và `swagger-ui` là các Actuator endpoint do Springdoc đăng ký để phục vụ tài liệu trên management port. Các URL thường có dạng:

```text
http://localhost:9090/actuator
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
```

Management port phải khác application port. Khi `springdoc.use-management-port=true`, các tùy chỉnh path Springdoc thông thường không áp dụng cho các endpoint được expose dưới Actuator base path; hãy dùng URL theo management base path được cấu hình.

Chỉ thêm `openapi` và `swagger-ui` vào exposure khi thật sự muốn cung cấp tài liệu trên management port. Nếu muốn expose health và info ở cùng cổng, thêm các ID đó vào danh sách. Nếu dùng `include` tường minh, nhớ rằng endpoint không có trong danh sách sẽ không được expose qua web.

Tách cổng không tự tạo ranh giới bảo mật hoàn chỉnh. Cần bind management server vào interface phù hợp, giới hạn truy cập bằng firewall, service network hoặc ingress nội bộ và áp dụng Spring Security. Nếu management port được publish ra Internet, lợi ích tách cổng có thể mất đi.

## 9. Kết hợp `show-actuator` và management port

Hai thuộc tính phục vụ hai mục tiêu khác nhau:

- `springdoc.show-actuator=true`: thêm Actuator endpoints vào tài liệu OpenAPI, thường qua một group Actuator riêng.
- `springdoc.use-management-port=true`: phục vụ OpenAPI/Swagger UI dưới Actuator management port thay vì application port.

Có thể dùng cả hai khi đội vận hành muốn xem tài liệu Actuator ngay trên cổng quản trị:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,openapi,swagger-ui

springdoc:
  show-actuator: true
  use-management-port: true
```

Khi đó, Swagger UI trên management port có thể cung cấp group Actuator. Nếu `show-actuator` được bật nhưng `use-management-port` không bật, Swagger UI vẫn được phục vụ trên application port; group Actuator vẫn được thêm vào tài liệu. Nếu Actuator endpoints nằm trên cổng khác, cần kiểm tra CORS và quyền truy cập cho đường dẫn thực tế.

Khi Swagger UI trên management port gọi endpoint nghiệp vụ trên application port, hai cổng là hai origin khác nhau theo quy tắc same-origin của trình duyệt. Nếu cần dùng **Try it out**, phải cấu hình CORS ở application server cho origin Swagger UI, cùng các method/header cần thiết. CORS không thay thế authentication.

## 10. Bảo vệ Actuator bằng Spring Security

Exposure không phải authentication. Nếu `env` được expose qua HTTP, người không có quyền vẫn có thể gọi endpoint trừ khi Spring Security hoặc lớp mạng chặn họ.

Ví dụ Spring Security 6 bảo vệ endpoint quản trị:

```java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/actuator/health").permitAll()
            .requestMatchers("/actuator/**").hasRole("OPS")
            .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Ví dụ trên dùng path mặc định `/actuator`. Nếu ứng dụng đổi `management.endpoints.web.base-path`, có thể dùng matcher chuyên biệt `EndpointRequest` để không phụ thuộc chuỗi path:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to("health")).permitAll()
    .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
    .anyRequest().authenticated()
);
```

Đây là API matcher cho ứng dụng servlet/Spring MVC. Với WebFlux, dùng `SecurityWebFilterChain` và reactive matcher tương ứng. Khi tự khai báo `SecurityFilterChain`, Spring Boot lùi cấu hình security Actuator tự động để ứng dụng tự chịu trách nhiệm về toàn bộ quy tắc; cần chắc chắn không vô tình mở endpoint quản trị.

Trong ví dụ, health tổng quát có thể được probe mà không cần đăng nhập; các Actuator endpoint còn lại yêu cầu authority `ROLE_OPS`. Nếu cần bảo vệ cả chi tiết health, cấu hình `show-details: when-authorized` và role phù hợp.

Nếu Springdoc phục vụ Swagger UI/OpenAPI trên management port, cần xác minh security chain áp dụng cho management context và URL dưới `/actuator/openapi`, `/actuator/swagger-ui`. Không giả định matcher của application port tự động bảo vệ một management context được cấu hình riêng. Với nhiều `SecurityFilterChain`, kiểm tra `securityMatcher`, `@Order` và matcher thực tế cho từng cổng.

Đối với môi trường production, có thể dùng OAuth2 Resource Server hoặc cơ chế SSO nội bộ thay cho HTTP Basic. Không nhúng mật khẩu hoặc token quản trị vào `application.yml` đã commit.

## 11. Giữ tài liệu nghiệp vụ tách khỏi tài liệu quản trị

Nếu ứng dụng có nhiều nhóm tài liệu, hãy đặt ranh giới rõ ràng:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/**")
        .build();
}
```

Actuator group do `springdoc.show-actuator=true` tạo ra được quản lý riêng bởi Springdoc. Không nên thêm các path `/actuator/**` vào group public một cách vô tình bằng `pathsToMatch("/**")` nếu mục tiêu là giữ endpoint quản trị tách biệt.

Nếu cần tài liệu nội bộ tổng hợp, có thể tạo group riêng và bảo vệ cả URL OpenAPI của group đó. Tuy nhiên, group OpenAPI chỉ phân loại nội dung; nó không thay thế web exposure hoặc Spring Security. Một endpoint bị ẩn khỏi tài liệu vẫn có thể được gọi nếu runtime expose và cho phép truy cập.

## 12. Kiểm tra cấu hình Actuator và OpenAPI

Sau khi khởi động ứng dụng, kiểm tra các URL phù hợp với cấu hình:

```bash
# Health
curl -i http://localhost:8080/actuator/health

# Info
curl -i http://localhost:8080/actuator/info

# Actuator endpoint discovery
curl -i http://localhost:8080/actuator

# OpenAPI document của ứng dụng
curl -i http://localhost:8080/v3/api-docs
```

Nếu sử dụng management port và `springdoc.use-management-port=true`:

```bash
curl -i http://localhost:9090/actuator
curl -i http://localhost:9090/actuator/openapi
curl -i http://localhost:9090/actuator/swagger-ui
```

Kiểm tra theo các câu hỏi:

1. Endpoint có được bật và có sẵn trong ứng dụng không?
2. Endpoint có được expose qua HTTP không?
3. Request không xác thực nhận status nào?
4. User có role vận hành truy cập được không?
5. Health details có bị lộ cho user không có quyền không?
6. `springdoc.show-actuator` có tạo group Actuator như mong muốn không?
7. Swagger UI và OpenAPI document có được phục vụ trên đúng cổng không?
8. Group public có vô tình chứa endpoint quản trị không?

Nếu endpoint trả `404`, kiểm tra ID và web exposure. Nếu trả `401` hoặc `403`, kiểm tra Spring Security và role. Nếu endpoint hoạt động nhưng không xuất hiện trong Swagger UI, kiểm tra `springdoc.show-actuator`, phiên bản Springdoc và group document. Nếu Swagger UI tải được nhưng không gọi được API trên cổng khác, kiểm tra CORS và xác thực.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có dependency Actuator nhưng `/actuator/metrics` trả `404` | Endpoint chưa được expose qua web hoặc chưa có registry phù hợp | Kiểm tra `management.endpoints.web.exposure.include` và dependency metric |
| Đưa `env` vào OpenAPI nhưng không gọi được | Tài liệu mô tả operation nhưng Actuator không expose endpoint | Kiểm tra enabled/exposure và Security riêng |
| `/actuator/env` truy cập được không cần đăng nhập | Endpoint đã expose nhưng thiếu authorization rule | Bảo vệ bằng Spring Security và giới hạn network |
| `health` tiết lộ database hoặc broker | `show-details: always` hoặc role quá rộng | Dùng `when-authorized`, giới hạn role và chỉ công khai trạng thái tổng quát |
| Bật `springdoc.show-actuator` nhưng không thấy group | Phiên bản/cấu hình Springdoc không tương thích hoặc Actuator chưa được nhận diện | Kiểm tra starter và version, endpoint Actuator và OpenAPI output |
| Swagger UI vẫn nằm trên application port | Chỉ bật `show-actuator`, chưa bật `use-management-port` | Bật `springdoc.use-management-port` và cấu hình management port khác |
| `/actuator/openapi` hoặc `/actuator/swagger-ui` trả `404` | Chưa expose Actuator endpoint `openapi`/`swagger-ui` | Thêm hai ID vào `management.endpoints.web.exposure.include` |
| Swagger UI trên management port không gọi được API | CORS giữa management port và application port chưa được cấu hình | Cho phép origin UI trên application endpoint cần gọi |
| Endpoint vẫn gọi được dù bị ẩn trong Swagger UI | Nhầm tài liệu với runtime exposure/security | Kiểm tra web exposure và authorization trực tiếp |
| Tắt Swagger UI nhưng Actuator vẫn hoạt động | Hai nhóm endpoint có cấu hình độc lập | Cấu hình riêng `springdoc` và `management` theo mục tiêu |

## 14. Checklist quyết định có công bố Actuator hay không

- [ ] Đã xác định endpoint nào phục vụ health, monitoring và vận hành.
- [ ] Chỉ expose những endpoint HTTP thực sự cần thiết.
- [ ] Đã xem xét riêng endpoint nhạy cảm như `env`, `configprops`, `beans`, `mappings`, `heapdump`, `threaddump`, `loggers` và `shutdown`.
- [ ] Đã phân biệt enabled, exposed và authorized.
- [ ] Health details không hiển thị rộng hơn nhu cầu vận hành.
- [ ] Đã quyết định có cần `springdoc.show-actuator=true` hay không.
- [ ] Nếu công bố tài liệu Actuator, đã tách group và đối tượng sử dụng khỏi API public.
- [ ] Nếu dùng management port, port khác application port và exposure gồm `openapi`, `swagger-ui` khi cần.
- [ ] Management port chỉ có thể truy cập từ mạng/interface được phép.
- [ ] Spring Security bảo vệ endpoint quản trị bằng role/authority phù hợp.
- [ ] Đã kiểm tra cả request trực tiếp lẫn tài liệu OpenAPI/Swagger UI.
- [ ] Đã xác minh CORS nếu UI trên management port gọi API ở application port.
- [ ] Không dựa vào việc ẩn endpoint trong Swagger UI để bảo vệ runtime.

Actuator là bề mặt quản trị và vận hành của ứng dụng. Hãy chọn endpoint cần bật, giới hạn endpoint được expose, bảo vệ request bằng Spring Security và chỉ đưa chúng vào OpenAPI khi đúng đối tượng cần sử dụng. `springdoc.show-actuator` giúp tài liệu hóa endpoint quản trị; `springdoc.use-management-port` giúp phục vụ tài liệu trên cổng quản trị riêng. Hai tùy chọn này hỗ trợ tổ chức tài liệu, còn quyền truy cập thực tế vẫn phải được quyết định ở Actuator, security và hạ tầng mạng.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Springdoc OpenAPI v2 — Actuator support](https://springdoc.org/v2/modules.html)
- [Springdoc OpenAPI v2 — Configuration properties](https://springdoc.org/v2/core-properties.html)
