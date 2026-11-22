# Bảo vệ Actuator theo cổng quản trị, đường dẫn và chuỗi phù hợp

> **Phạm vi:** Spring Boot 3.x, Spring Security 6.x, Java 17+ trên **Servlet stack** (Spring MVC). Bài này trình bày cách bảo vệ Spring Boot Actuator theo **cổng quản trị**, **đường dẫn và tập endpoints được expose**, và **SecurityFilterChain thực sự xử lý request**. Nội dung tập trung vào vận hành ứng dụng, không biến Actuator thành API công khai. Các ví dụ minh họa cấu hình theo hai mô hình: **Actuator chung cổng với ứng dụng** và **Actuator ở cổng quản trị riêng**. Cả hai đều cần kiểm thử security trong môi trường tương ứng.

## 1. Vì sao Actuator cần một chính sách bảo vệ riêng?

Spring Boot Actuator cung cấp các endpoint phục vụ giám sát và quản trị runtime. Những endpoint này có thể cho biết tình trạng ứng dụng, thông tin build, metrics, loggers, cấu hình hoặc các dữ liệu vận hành khác. Một số endpoint chỉ cần cho hệ thống monitoring, trong khi những endpoint nhạy cảm tuyệt đối không nên mở công khai.

Nếu ứng dụng có các URL:

~~~text
GET  /api/orders
GET  /actuator/health
GET  /actuator/metrics
GET  /actuator/env
POST /actuator/loggers/com.example
~~~

thì quyền xem đơn hàng của một người dùng **không phải** quyền xem metrics, cấu hình môi trường hoặc thay đổi log level. Sử dụng cùng cơ chế login cho mọi người mà không tách policy rất dễ biến “người đã đăng nhập” thành “người có quyền vận hành”.

Đặc biệt, một số endpoint có thể chứa thông tin nhạy cảm, tăng bề mặt tấn công, hoặc thực hiện thay đổi trạng thái. Vì vậy phải quyết định rõ **cái gì được expose**, **request đến từ đâu** và **ai được phép dùng**.

### Ba lớp kiểm soát độc lập

| Lớp | Câu hỏi | Ví dụ cấu hình |
| --- | --- | --- |
| **Exposure** | Endpoint có được xuất bản qua HTTP không? | `management.endpoints.web.exposure.include` / `exclude`. |
| **Network/port** | Ai có thể kết nối đến cổng và đường mạng chứa endpoint? | `management.server.port`, `management.server.address`, firewall, ingress, ACL, mTLS. |
| **Authentication/authorization** | Khi request đến endpoint, server kiểm tra danh tính và quyền nào? | `SecurityFilterChain`, `EndpointRequest`, `hasRole("OPS")`. |

**Không được đánh đồng ba lớp này.** Endpoint không được expose qua HTTP thì `GET` thông thường không truy cập được nó qua HTTP, nhưng exposure không phải là quyết định người nào được phép. Ngược lại, endpoint có expose vẫn cần authorization và bảo vệ mạng. Đưa Actuator sang cổng 9090 **không tự biến cổng đó thành cổng an toàn** nếu nó bị mở ra Internet.

## 2. Nhóm endpoint và mức độ nhạy cảm

Một số endpoint thường gặp:

| Endpoint ID | Công dụng | Hướng bảo vệ |
| --- | --- | --- |
| `health` | Tình trạng tổng thể, các health groups, readiness/liveness nếu bật. | Có thể mở thông tin tổng quát cho load balancer/orchestrator; hạn chế details nhạy cảm. |
| `info` | Thông tin build, version hoặc metadata công bố. | Chỉ mở nếu dữ liệu đã được rà soát; không mặc định là vô hại. |
| `metrics` | Tên và giá trị đo hiệu năng/khả năng sử dụng tài nguyên. | Giới hạn cho monitoring/OPS, tránh tiết lộ thông tin runtime. |
| `prometheus` | Xuất metrics theo định dạng Prometheus, nếu có Micrometer registry tương ứng. | Dành cho scraper đáng tin; network policy/auth riêng. |
| `loggers` | Xem và có thể điều chỉnh mức ghi log theo HTTP method/khả năng. | Quyền vận hành hẹp, audit và kiểm soát thay đổi. |
| `env` | Quan sát environment properties và nguồn cấu hình. | Nhạy cảm, mặc định không expose bừa; cơ chế sanitize không thay thế bảo vệ. |
| `configprops` | Thông tin configuration properties được bind. | Nhạy cảm; cân nhắc nhu cầu và khả năng sanitize. |
| `beans`, `mappings`, `conditions` | Cấu trúc ứng dụng, routes, auto-configuration. | Chỉ dành cho chẩn đoán trong môi trường kiểm soát. |
| `threaddump`, `heapdump` | Chẩn đoán thread/heap, có thể chứa dữ liệu nhạy cảm. | Hạn chế rất chặt; heap dump có thể cực kỳ nhạy cảm. |
| `shutdown` | Yêu cầu tắt ứng dụng nếu endpoint được bật và expose. | Không bật cho môi trường công khai; giới hạn đặc quyền vận hành. |

Tên endpoint trong bảng là **ID** chứ không nhất thiết trùng toàn bộ HTTP path nếu đã đổi base path hoặc path mapping. Đặc tính endpoint còn tùy dependency, phiên bản Spring Boot, trạng thái enabled/exposed và các extension của ứng dụng. Không giả định một endpoint luôn tồn tại chỉ vì nhớ tên nó.

### Expose ít nhất có thể

Trong cấu hình thông thường, Spring Boot mặc định chỉ expose một tập HTTP management endpoints rất hạn chế (thường là `health`). Khi muốn thêm `metrics`, người triển khai phải **chủ động bật exposure** và xác định yêu cầu bảo mật kèm theo.

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Đoạn này chỉ **cho phép ba endpoint có thể truy cập qua HTTP**. Nó **không** gán quyền OPS, không khóa cổng, không tự mở firewall và không bảo đảm có endpoint `prometheus`.

**Không nên dùng** `management.endpoints.web.exposure.include: "*"` trong production trừ khi đã đánh giá đầy đủ toàn bộ endpoint và lớp bảo vệ thích hợp. Một dependency mới có thể thêm endpoint mới mà cấu hình wildcard vô tình expose.

Lưu ý khi dùng `exposure.exclude`: exclude có thể hạn chế tập endpoint, nhưng chính sách tốt nhất vẫn là **allowlist `include`** rõ ràng. Đừng trông chờ một danh sách denylist luôn theo kịp endpoint được thêm trong tương lai.

## 3. Cổng quản trị và đường dẫn: hiểu trước khi viết security matcher

### 3.1 Mặc định: Actuator chung cổng với ứng dụng

Nếu ứng dụng dùng:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,metrics
~~~

thì các endpoint HTTP (nếu được enable và expose) thường nằm tại:

~~~text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/info
http://localhost:8080/actuator/metrics
~~~

`management.endpoints.web.base-path` mặc định là `/actuator`. Nó là **prefix của các web endpoints**, không phải mật khẩu hoặc tường lửa. Thay prefix thành `/hidden-admin-92` không được coi là phương pháp bảo mật: đường dẫn vẫn có thể bị tìm ra hoặc lộ qua log, thông tin build, cấu hình proxy.

Khi Actuator dùng **chung cổng**, các web endpoints chia sẻ web server với application routes. Cần đảm bảo matcher dành cho Actuator không bị một chain chung `/**` ưu tiên trước hoặc một rule `permitAll` quá rộng.

### 3.2 Thay management base path

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
~~~

Lúc này đường đi điển hình trên cùng cổng là:

~~~text
/manage/health
/manage/info
/manage/metrics
~~~

**Cần chú ý:** khi chạy **chung cổng**, management base path chịu tác động của Servlet context path và cấu hình web server; khi chạy **cổng riêng**, management context có thể có base path riêng tùy cấu hình Boot. Proxy có thể rewrite prefix. Vì vậy phải kiểm tra **URL thực tế** thay vì suy luận từ một property đơn lẻ.

Nếu bạn hard-code security rule `requestMatchers("/actuator/**")` nhưng đổi base-path thành `/manage`, rule cũ có thể không còn match. Đó là một lý do nên sử dụng `EndpointRequest` khi bảo vệ các Actuator endpoints.

### 3.3 Tách cổng bằng management.server.port

Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
~~~

Ý nghĩa:

- Ứng dụng phục vụ API/UI trên cổng `8080`.
- Management endpoints được cấu hình phục vụ trên cổng `9090`, thường trong **management web context riêng** khi hai cổng khác nhau.
- Actuator health thường ở `http://host:9090/manage/health`, metrics ở `http://host:9090/manage/metrics`; phải kiểm tra context path, reverse proxy và thực tế runtime.
- **Không** suy ra rằng các `SecurityFilterChain` có hiệu lực trên cổng `8080` sẽ chắc chắn được áp dụng giống hệt trên cổng `9090`. Khi Boot tạo management context riêng, cách các beans/configurations được nhìn thấy và auto-configure phải được xác minh bằng test vào **chính cổng quản trị**.

Đây là **phương án cấu hình thay thế** ví dụ chung cổng: không ghép cả hai vào một file rồi tuyên bố hai mô hình đang chạy cùng lúc. Dùng mô hình nào thì kiểm thử đúng mô hình đó.

### 3.4 Bind vào interface quản trị

Trong một số môi trường, có thể giới hạn management server vào loopback:

~~~yaml
management:
  server:
    port: 9090
    address: 127.0.0.1
~~~

Cấu hình trên có ý nghĩa khi management port **tách với application port**. Khi bind thành công, service chỉ lắng nghe qua loopback của **chính network namespace/container đó**. Tuy nhiên:

- Nếu app chạy trong Docker/Kubernetes, `127.0.0.1` nằm **bên trong container/pod**, monitoring bên ngoài có thể không kết nối tới được. Cần lựa chọn cấu trúc mạng phù hợp thay vì vội đổi sang `0.0.0.0`.
- Bind vào địa chỉ riêng là một lớp giới hạn, **không thay** authentication/authorization. Các tiến trình cùng host/network namespace vẫn có thể truy cập.
- Nếu dùng Kubernetes Service/Ingress, cấu hình firewall, NetworkPolicy, security groups và ingress rules theo nhu cầu monitoring thực tế. Không route cổng management ra public ingress không cần thiết.
- Không giả định cấu hình address riêng luôn có hiệu lực khi management vẫn dùng chung cổng: nhiều container/Boot configurations yêu cầu **một cổng riêng** để bind management address khác với server chính.

## 4. SecurityFilterChain: chọn đúng Actuator endpoints

Spring Boot Actuator cung cấp `EndpointRequest` để tạo `RequestMatcher` dựa trên **endpoint ID/endpoint mappings**, không chỉ một chuỗi URL hard-coded.

Import thường dùng trên Servlet stack:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
~~~

Một số API đáng nhớ:

- `EndpointRequest.toAnyEndpoint()`: matcher cho các web Actuator endpoints trong context tương ứng.
- `EndpointRequest.to("health")`: matcher dành cho endpoint ID `health`.
- `EndpointRequest.to("health", "info")`: chọn các endpoint IDs cụ thể; chỉ nên permit khi chúng thật sự được công khai theo policy.
- `EndpointRequest.toAnyEndpoint().excluding(...)`: có thể loại những endpoint ID cụ thể khỏi matcher khi cần tổ chức nhiều chain, nhưng phải hiểu chain fallback áp dụng ra sao.

**Ưu điểm:** thay `management.endpoints.web.base-path` từ `/actuator` thành `/manage` thường không buộc phải sửa tên matcher được xây từ endpoint ID. Spring Boot ánh xạ các endpoint IDs với cấu hình web management thực tế.

Cũng cần nhớ: `EndpointRequest` và `SecurityFilterChain` không biến endpoint **chưa expose** thành có thể truy cập. Nó chỉ hỗ trợ xác định request nào **đúng là management endpoint** để áp dụng security.

### Phân biệt securityMatcher với requestMatchers

Một cấu hình dễ nhầm:

~~~java
http.securityMatcher(EndpointRequest.toAnyEndpoint())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to("health")).permitAll()
        .anyRequest().hasRole("OPS"));
~~~

- `http.securityMatcher(...)` xác định **cả filter chain** có nhận request Actuator hay không.
- `authorizeHttpRequests(...requestMatchers(...))` chọn **quy tắc quyền** bên trong filter chain đã khớp.
- Nếu không có chain nào khớp, request có thể đi tiếp mà **không được Spring Security bảo vệ**. Vì vậy thường cần **fallback chain** cho các request ứng dụng khác.
- Với nhiều chains, `FilterChainProxy` dùng **chain đầu tiên khớp** theo thứ tự cấu hình. Chain bao phủ mọi đường dẫn nếu đặt quá sớm có thể che Actuator chain chuyên dụng.
- Với management server trên **cổng riêng**, chain phải thực sự được gắn vào **management context/port đó**. Tên matcher đúng nhưng bean chưa được nạp ở đúng context thì vẫn chưa đạt yêu cầu.

## 5. Cấu hình Spring Security mẫu: health công khai, metrics chỉ cho OPS

Đây là ví dụ hoàn chỉnh về **cách đặt policy khi Actuator dùng chung cổng ứng dụng**. Các class sử dụng Spring Boot 3.x, Spring Security 6.x trên Servlet, Java 17+, và các dependencies phù hợp. Bản demo có HTTP Basic để quan sát status rõ ràng.

Policy mong muốn:

1. `health` được phép cho monitoring health check nhưng **không công bố details nhạy cảm** cho anonymous.
2. `info` và `metrics` chỉ cho user có role `OPS`.
3. Các Actuator endpoints khác nếu được expose phải yêu cầu `OPS`; điều này không có nghĩa nên expose chúng.
4. Application requests nằm trong **fallback chain** riêng.
5. Mọi POST đổi trạng thái chỉ được xử lý nếu policy và các bảo vệ khác (như CSRF nếu áp dụng) cho phép.

### 5.1 Các dependencies Maven

Trong `pom.xml` của Spring Boot project đã dùng Boot parent/BOM, phần dependencies tối thiểu cho demo web + actuator + security + tests:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **mảnh XML**, không phải POM chạy độc lập. Thường nên dùng dependency management của Spring Boot để các module Spring Security/Actuator có phiên bản tương thích.

### 5.2 application.yml cho demo chung cổng

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS

app:
  ops:
    username: ${OPS_USERNAME:ops}
    password: ${OPS_PASSWORD}
~~~

Phân tích:

- `/manage` là base path, không phải “ẩn bí mật”. URL cụ thể của metrics trên cùng cổng là `/manage/metrics`.
- Chỉ expose `health`, `info`, `metrics`. Không expose `env`, `beans`, `heapdump`, `shutdown` chỉ vì dễ kiểm tra.
- `management.endpoint.health.show-details=when_authorized` kết hợp `management.endpoint.health.roles=OPS` để health details chỉ xuất hiện theo điều kiện role được cấu hình. Đường health có thể public nhưng body cho người chưa có quyền chỉ nên gồm thông tin tổng quát; hãy kiểm tra response cụ thể trong phiên bản Boot đang dùng.
- `app.ops.username/password` là biến cấu hình của **ứng dụng demo**, **không phải** thuộc tính Actuator/Spring Security chuẩn. Phải có biến môi trường `OPS_PASSWORD` trước khi khởi động. Không để password thật trong Git.
- Spring Boot có thể thêm các health contributors khác nhau theo dependencies; status health `UP`/`DOWN` và status HTTP phụ thuộc runtime. Test status health cần xét môi trường (nếu disk/db không khỏe có thể trả `503`).

### 5.3 Main class

File `src/main/java/com/example/management/ManagementDemoApplication.java`:

~~~java
package com.example.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagementDemoApplication.class, args);
    }
}
~~~

### 5.4 SecurityFilterChain có @Order và EndpointRequest

File `src/main/java/com/example/management/ManagementSecurityConfig.java`:

~~~java
package com.example.management;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ManagementSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Mô hình bảo vệ:**

- `@Order(1)` ưu tiên Actuator chain trước fallback chain.
- `EndpointRequest.toAnyEndpoint()` chọn các Actuator requests hiện có trong context phù hợp.
- `EndpointRequest.to("health")` cho phép health endpoint, không phải toàn bộ `/manage/**`.
- `anyRequest().hasRole("OPS")` của Actuator chain yêu cầu `ROLE_OPS` cho metrics, info và những endpoint khác mà chain match.
- `@Order(2)` là chain ứng dụng với fallback `anyRequest().authenticated()`; các endpoint không thuộc nhóm management vẫn phải xác thực, ngoại trừ `/public/**`. Demo không dùng form login nên HTTP Basic entry point thường tạo `401` khi thiếu credentials.
- Cả hai chains dùng Basic **chỉ để minh họa test**. Production có thể dùng OAuth2/mTLS/service account/SSO tùy kiến trúc, nhưng cần đảm bảo credentials và quyền dành cho management được cô lập. HTTP Basic yêu cầu HTTPS trên đường mạng thực.
- Không khai báo `csrf.disable()`. Các endpoint GET trong demo không gây thay đổi trạng thái; nếu expose Actuator operations qua POST, phải đánh giá CSRF, authentication và quyền thay đổi trạng thái một cách riêng biệt. **Đừng tắt CSRF toàn app vì một request management POST không chạy**.

**Tại sao không viết `.requestMatchers("/manage/**").permitAll()`?** Vì lỡ mở cả metrics, env/loggers hoặc endpoint mới. Hơn nữa nó gắn policy với string path; `EndpointRequest` hiểu mapping thực tế của Actuator.

### 5.5 UserDetailsService và PasswordEncoder (chỉ demo)

File `src/main/java/com/example/management/OpsUserConfig.java`:

~~~java
package com.example.management;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class OpsUserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            @Value("${app.ops.username}") String username,
            @Value("${app.ops.password}") String password,
            PasswordEncoder encoder) {

        return new InMemoryUserDetailsManager(
            User.withUsername(username)
                .password(encoder.encode(password))
                .roles("OPS")
                .build()
        );
    }
}
~~~

`roles("OPS")` tạo authority `ROLE_OPS` phù hợp `hasRole("OPS")` của Actuator chain. Mật khẩu phải nạp an toàn qua biến môi trường/secret manager; nó được hash bằng BCrypt khi khởi tạo demo user. Không commit password thật. Đây **không** phải cách thiết kế user store production có audit/rotation/MFA.

**Giới hạn mô hình demo:** một `UserDetailsService` được cả hai chains cùng nhìn thấy. User `ops` cũng có thể vượt qua `authenticated()` ở fallback application chain. Nếu yêu cầu cách ly chặt **operator identity** khỏi end-user sessions, phải thiết kế authentication managers/providers khác nhau hoặc identity policy rõ ràng cho từng chain, thay vì chỉ có một store dùng chung. Tách port không tự tách danh tính.

### 5.6 Endpoint ứng dụng để đối chiếu

File `src/main/java/com/example/management/AppController.java`:

~~~java
package com.example.management;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/app/private")
    public String privateEndpoint() {
        return "private";
    }
}
~~~

Dự kiến `GET /public/ping` trả `pong` không cần authentication, còn `GET /app/private` phải có credentials hợp lệ. Với policy nâng cao, có thể yêu cầu role riêng cho application thay vì chỉ `authenticated()`.

## 6. Đổi base-path hoặc path mapping mà không làm hở endpoint

Giả sử ban đầu management base path là `/manage`; sau đó muốn đổi sang `/internal/ops`:

~~~yaml
management:
  endpoints:
    web:
      base-path: /internal/ops
      exposure:
        include: health,info,metrics
~~~

Điều cần làm:

1. Kiểm tra thật các URL `/internal/ops/health` và `/internal/ops/metrics` trong runtime (có thể thêm Servlet context path).
2. Vì chain dùng `EndpointRequest.toAnyEndpoint()` và `EndpointRequest.to("health")`, policy có khả năng tiếp tục chọn **đúng endpoint IDs**, không phụ thuộc hoàn toàn hard-coded `/manage/**`.
3. Kiểm tra route `/manage/metrics` cũ không còn là management endpoint được expose; một request tình cờ tới URL cũ có thể rơi vào fallback chain, nhưng không được tạo ra controller nhạy cảm có tên cũ ngoài Actuator.
4. Kiểm tra reverse proxy, monitoring scrape configs, load balancer health checks và alert rules đã cập nhật đường dẫn.
5. Test trực tiếp cả anonymous và OPS sau thay đổi; đừng chỉ thử một request OPS thành công rồi kết luận anonymous đã bị chặn.

Nếu muốn đổi riêng đường dẫn health (không đổi ID), Spring Boot hỗ trợ `management.endpoints.web.path-mapping.<id>`. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

Trong mô hình này, đường health web điển hình là `/manage/status` thay vì `/manage/health`, nhưng **ID vẫn là `health`**. `EndpointRequest.to("health")` là một cách biểu đạt quyền nhất quán theo endpoint. Nếu dùng reverse proxy rewrite, phải kiểm chứng cả upstream path và external path.

**Lưu ý về route khác:** health groups có thể có subpaths như `/manage/health/readiness` khi cấu hình probes. Đừng tưởng một matcher `requestMatchers("/manage/health")` luôn bảo vệ mọi nhánh; dùng matcher endpoint-aware hoặc test từng URL cần thiết.

## 7. Cổng quản trị riêng: điều gì thay đổi về security?

Một biến thể `application.yml` cho deployment có network segment quản trị:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS

app:
  ops:
    username: ${OPS_USERNAME:ops}
    password: ${OPS_PASSWORD}
~~~

Cấu hình này minh họa ý định để application phục vụ `8080` và management chỉ nghe trên `127.0.0.1:9090`, nếu hạ tầng hỗ trợ. Nó không phải một file để chép nguyên vào Kubernetes nếu Prometheus nằm ngoài network namespace; thiết kế mạng production phải phù hợp.

### Hai lớp bảo vệ khi dùng cổng riêng

**Lớp 1 — Network:** chỉ monitoring/ops network có quyền kết nối. Có thể chọn loopback, internal interface, firewall/security group hoặc Kubernetes NetworkPolicy. Nếu phải đi qua reverse proxy, chỉ cho proxy tin cậy route vào cổng quản trị; không cấu hình public ingress tùy tiện.

**Lớp 2 — Spring Security:** request đã đến management port vẫn phải được xác thực/phân quyền theo yêu cầu. `metrics` chỉ cho OPS/monitoring identity; `health` có thể public trong mạng nội bộ với chi tiết đã ẩn.

**Đặc biệt:** Spring Boot có thể tạo **management child ApplicationContext** khi khác cổng. Để chứng minh policy hiệu lực trên port này, phải test **chính cổng quản trị**, không chỉ chạy MockMvc ở main web application context. Nếu child context không nhận SecurityFilterChain tùy chỉnh bạn kỳ vọng, hãy cấu hình management security ở đúng context theo cách Boot version hỗ trợ, và kiểm tra startup/test logs. Không dùng suy luận “config class đã có trong app” làm bằng chứng rằng cổng 9090 đã được bảo vệ.

### Cổng riêng không phải là tường lửa

Cổng TCP `9090` có thể bị scan, NAT, ingress hoặc Service mở. Thay số port không tăng quyền bảo mật theo nghĩa thực tế. Hãy kiểm tra network effective configuration (container port mappings, service endpoints, load balancer listener, host firewall, cloud security group và reverse proxy).

Nếu deployment dùng Docker, `127.0.0.1` của container có thể chỉ được truy cập trong container. Nếu đổi sang bind tất cả interfaces để scraper truy cập, hãy bổ sung firewall/network policy và authentication; đừng bỏ một lớp bảo vệ chỉ để scrape hoạt động.

## 8. Management server context, bean scope và mặc định tự động bảo vệ

Spring Boot có auto-configuration cho Actuator Security **khi Spring Security có mặt**. Trong cấu hình phổ biến, nếu ứng dụng **chưa tự khai báo** một `SecurityFilterChain`, Boot có thể tự thiết lập những giới hạn mặc định cho management endpoints. Tuy nhiên khi ứng dụng khai báo **bất kỳ custom SecurityFilterChain bean** phù hợp, auto-configuration bảo vệ management endpoints có thể **back off**. Khi đó bạn **phải chủ động** đặt authorization cho Actuator.

### Vì sao thêm một filter chain ứng dụng có thể gây rủi ro?

Giả sử trước đây:

~~~text
Spring Boot auto security:
  /actuator/health -> accessible
  other actuator endpoints -> authenticated
~~~

Sau đó bạn thêm một `SecurityFilterChain` chỉ cho `/api/**` nhưng không có chain bao phủ Actuator. Không được suy luận Boot vẫn sẽ tự chặn `/actuator/metrics`. Tùy điều kiện auto-config, custom bean có thể làm phần security mặc định không còn được tạo; endpoint management được expose nhưng không bị chain bạn viết match sẽ trở thành lỗ hổng.

**Cách phòng tránh:**

- Khai báo chain chuyên dụng với `EndpointRequest.toAnyEndpoint()` khi Actuator và app chung servlet context/port.
- Đặt `@Order` nhất quán, có fallback chain bảo vệ application routes.
- Nếu khác port, kiểm tra chính management child context, endpoint request mappings và chain được nạp ở đó.
- Bổ sung test anonymous với metrics/info không chỉ test OPS dương tính.
- Kiểm tra runtime thực tế sau khi nâng cấp Spring Boot, đổi app context, thêm filter chain hoặc thay ingress rules.

Tài liệu Spring Boot về actuator security là nguồn quyết định cho **phiên bản đang chạy**; không mặc định rằng hành vi từ một phiên bản cũ vẫn chính xác sau nâng cấp.

## 9. Kiểm thử Actuator chung cổng bằng MockMvc

Với mô hình chung cổng phần 5, `@SpringBootTest` + `@AutoConfigureMockMvc` có thể chạy request qua Spring Security filters đang có trong ApplicationContext. Điều này kiểm tra các matcher/authorization tại Servlet layer mà **không cần mở TCP port**.

File `src/test/java/com/example/management/ActuatorSecurityTest.java`:

~~~java
package com.example.management;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "management.endpoints.web.base-path=/manage",
    "management.endpoints.web.exposure.include=health,info,metrics",
    "app.ops.username=ops",
    "app.ops.password=local-only-test-password"
})
@AutoConfigureMockMvc
class ActuatorSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsAllowed() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousMetricsIsRejected() throws Exception {
        mvc.perform(get("/manage/metrics"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/manage/metrics")
                .with(httpBasic("ops", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void operatorCanReadMetrics() throws Exception {
        mvc.perform(get("/manage/metrics")
                .with(httpBasic("ops", "local-only-test-password")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousInfoIsRejected() throws Exception {
        mvc.perform(get("/manage/info"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousPrivateApplicationIsRejected() throws Exception {
        mvc.perform(get("/app/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void healthIsAccessibleIfHealthy() throws Exception {
        mvc.perform(get("/manage/health"))
            .andExpect(status().isOk());
    }
}
~~~

**Đây là test thuộc cùng project demo**. Mật khẩu `local-only-test-password` dùng riêng trong test context; không dùng cho môi trường thật. Với app và các health contributors đều khỏe, `GET /manage/health` kỳ vọng 200. Nếu health status `DOWN`, Actuator có thể trả `503` theo status mapping, nên test `healthIsAccessibleIfHealthy` phải được diễn giải theo health state đang thử, không coi 503 luôn là lỗi authentication.

Các test quan trọng:

1. `anonymousMetricsIsRejected` xác nhận endpoint có expose nhưng không công khai.
2. `operatorCanReadMetrics` xác nhận đường tích cực cho OPS.
3. `wrongBasicPasswordIsRejected` đi qua HTTP Basic authentication provider thật của **demo**; khác với gắn sẵn `@WithMockUser(roles="OPS")`.
4. `anonymousInfoIsRejected` đảm bảo không vì info nghe “không nhạy” mà tự public.
5. `anonymousPrivateApplicationIsRejected` kiểm tra fallback chain; Actuator policy không làm ứng dụng còn lại bị mở.
6. `healthIsAccessibleIfHealthy` thể hiện health tổng quát có thể được phép, nhưng không khẳng định health details hay các contributors đều công khai.

Chạy theo Maven dự án đã cấu hình:

~~~bash
mvn test
~~~

Không bịa stdout Maven cố định: kết quả thực phụ thuộc plugins, system health và test classes khác. Đừng chỉ xem build xanh; phải biết test đã chạy **đúng FilterChainProxy**, đúng endpoints exposure và đúng management port.

### Kiểm thử method/path cũ sau đổi base-path

Thêm một test cho `/actuator/metrics` sau khi đã dùng `/manage` nếu hệ thống có reverse proxy hoặc route cũ. Kỳ vọng không nên được quyết định chỉ bằng tên URL: nếu không có controller, thường 404 sau security; nếu fallback chain yêu cầu login, anonymous có thể nhận 401 **trước khi tới MVC**. Mục tiêu là chứng minh endpoint nhạy cảm **không còn được truy cập công khai tại đường cũ**, không chỉ assert máy móc “phải 404”.

## 10. Kiểm thử cổng quản trị riêng bằng HTTP trên cổng đó

Khi management dùng cổng khác, **đừng chỉ test MockMvc main context** rồi kết luận management context được bảo vệ. Một integration test có thể khởi chạy application web server và management web server với hai random ports, gửi HTTP thật tới **management port**.

Ví dụ cấu hình test `@SpringBootTest`:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.server.port=0",
        "management.endpoints.web.base-path=/manage",
        "management.endpoints.web.exposure.include=health,metrics",
        "app.ops.username=ops",
        "app.ops.password=local-only-test-password"
    }
)
class ManagementPortSecurityTest {
    // Dùng @LocalManagementPort để lấy đúng cổng management runtime.
}
~~~

Đoạn trên chỉ minh họa cấu hình test class, chưa phải file test hoàn chỉnh. Khi `management.server.port=0`, Spring Boot có thể cấp một cổng HTTP ngẫu nhiên riêng cho management, và test có thể inject `@LocalManagementPort` (trong Spring Boot Test). Cần chắc chắn security chain ứng dụng được áp dụng **thật tại context đó**.

### Ví dụ test đầy đủ dùng TestRestTemplate

File `src/test/java/com/example/management/ManagementPortSecurityTest.java`:

~~~java
package com.example.management;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.server.port=0",
        "management.endpoints.web.base-path=/manage",
        "management.endpoints.web.exposure.include=health,metrics",
        "app.ops.username=ops",
        "app.ops.password=local-only-test-password"
    }
)
class ManagementPortSecurityTest {

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate rest;

    @Test
    void anonymousCannotReadMetricsOnManagementPort() {
        String url = "http://localhost:" + managementPort
                + "/manage/metrics";

        ResponseEntity<String> response =
                rest.getForEntity(url, String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void operatorCanReadMetricsOnManagementPort() {
        String url = "http://localhost:" + managementPort
                + "/manage/metrics";

        ResponseEntity<String> response =
                rest.withBasicAuth("ops", "local-only-test-password")
                    .getForEntity(url, String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }
}
~~~

**Mục đích:** test này không chỉ đọc beans trong main application context; nó **truy cập trực tiếp cổng management runtime**. Nếu anonymous đọc metrics thành công (HTTP 200), đó là tín hiệu fail nghiêm trọng cho policy mong muốn; cần kiểm tra management context wiring và auto-configuration, không sửa test thành 200 “cho qua”.

Đây là test HTTP trên localhost của JVM test: HTTP không mã hóa chỉ dùng trong môi trường thử nghiệm loopback được kiểm soát. Production phải áp dụng HTTPS/mTLS hoặc đường truyền trusted phù hợp. Nếu test runtime có proxy/port khác hoặc actuator không expose `metrics`, test 404 không chứng minh auth; hãy kiểm tra endpoint tồn tại bằng đường operator tích cực cùng bộ test.

**Lưu ý về `@LocalManagementPort`:** annotation chỉ có ý nghĩa khi bootstrapping web environment và management server đang nghe cổng thích hợp. Nếu trong môi trường triển khai không có management context riêng, hãy điều chỉnh test setup để đo đúng cổng/namespace thay vì tự hard-code 9090.

## 11. Health và probes: làm sao vừa giám sát vừa giữ bí mật?

Một load balancer hoặc Kubernetes orchestrator thường chỉ cần biết **ứng dụng còn sống/sẵn sàng nhận request**; chúng không cần danh sách bean, credentials, SQL diagnostics hay toàn bộ environment.

### Health details

Có các lựa chọn thông dụng cho `management.endpoint.health.show-details`:

| Giá trị | Ý nghĩa tổng quát |
| --- | --- |
| `never` | Không hiển thị chi tiết health components cho caller. |
| `when_authorized` | Hiển thị chi tiết theo điều kiện authorized health access; có thể kết hợp `management.endpoint.health.roles`. |
| `always` | Cho phép chi tiết xuất hiện rộng hơn; rủi ro khi health endpoint public. |

Nếu cho anonymous truy cập health, thông thường nên chỉ công bố tình trạng tổng quát; test body thật để tránh lộ tên database, thành phần nội bộ, lỗi chi tiết. `when_authorized` với `roles: OPS` là một lựa chọn cân bằng khi operator cần xem details và anonymous chỉ cần status.

### Readiness/liveness cho Kubernetes

Có thể bật probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi có health groups tương ứng, URLs thường là:

~~~text
/manage/health/liveness
/manage/health/readiness
~~~

Các đường này là **nhánh của health endpoint**. Nếu policy cho phép toàn bộ health theo ID, các nhóm tương ứng có thể truy cập không cần authentication; hãy đánh giá có đúng yêu cầu không. Một số deployment cần health path trên cổng ứng dụng chính để kiểm tra chính web server nhận traffic, vì cổng quản trị riêng có thể còn hoạt động dù cổng ứng dụng đã lỗi; Spring Boot cung cấp những cách cấu hình bổ sung cho probes trên application port tùy phiên bản. Không coi “management health trả 200” là bằng chứng tất cả tầng ứng dụng phục vụ request vẫn khỏe.

**Kubernetes đặc thù:** việc để liveness phụ thuộc một database ngoài có thể khiến pod restart hàng loạt khi DB tạm lỗi. Thiết kế health contributors/groups theo semantics readiness/liveness, không chỉ security.

## 12. Prometheus, Metrics và service identity

Nếu cần endpoint `/prometheus`, phải có Micrometer Prometheus registry thích hợp, ngoài Spring Boot Actuator. Ví dụ Maven dependency (bổ sung cho project đã có starter actuator):

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

**Exposing Prometheus ≠ Cho mọi người trên Internet scrape.** Thông thường cần:

- NetworkPolicy/firewall cho monitoring network hoặc Prometheus instance.
- Dedicated service identity có quyền **chỉ đọc metrics**; khi phù hợp, Basic auth qua HTTPS hoặc mTLS. Không bắt buộc dùng chính operator account có quyền đổi loggers/shutdown.
- Hạn chế labels chứa PII, customer IDs, tokens hoặc dữ liệu cardinality cao gây tràn bộ nhớ và tiết lộ thông tin.
- Giám sát scrape failures sau khi thay port/path, proxy rewrites hoặc xác thực.
- Tránh exposure wildcard chỉ vì cần một endpoint `prometheus`.

### Tách quyền MONITOR và OPS

Mô hình tốt hơn một role OPS toàn năng:

~~~text
Anonymous / load balancer -> health status tổng quát
MONITOR service identity  -> metrics, prometheus (read-only)
OPS operator identity     -> info, các endpoint chẩn đoán được cho phép
Không ai qua HTTP          -> shutdown/heapdump trừ khi có phê duyệt đặc biệt
~~~

Để thực hiện thật, cần chỉnh matcher/authorities rõ ràng và có chính sách riêng cho HTTP methods/endpoint IDs. Ví dụ đoạn DSL minh họa trong Actuator chain:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to("health")).permitAll()
    .requestMatchers(EndpointRequest.to("metrics", "prometheus"))
        .hasAnyRole("MONITOR", "OPS")
    .anyRequest().hasRole("OPS")
)
~~~

Đoạn trên là **mảnh cấu hình thay thế policy `authorizeHttpRequests` phần 5**, không phải Java class độc lập. Endpoint `prometheus` chỉ tồn tại khi có registry/exposure. Nếu cho OPS có quyền write tới bất kỳ actuator endpoint nào được expose, cần cân nhắc mô hình quyền mạnh hơn và **giới hạn exposure** thay vì chỉ thêm MONITOR. Bạn có thể chia chain theo endpoint nếu cần authentication manager, CSRF hoặc session policy khác nhau; kiểm tra chain selection và thứ tự thật.

## 13. Security của Actuator không chỉ ở Spring Security

### Reverse proxy và path rewriting

Một proxy có thể ánh xạ:

~~~text
Public /internal-monitor/status
    -> http://127.0.0.1:9090/manage/health
~~~

Nếu proxy nhận request public rồi chuyển vào management port, ranh giới mạng thực tế đã mở rộng. Cần kiểm tra:

- Proxy có yêu cầu identity không, có strip headers do người dùng tự gửi không?
- Có allowlist nguồn và TLS giữa proxy, app, scraper phù hợp không?
- Request path nào được phép route? Có thể vô tình proxy cả `/manage/**` thay vì chỉ health?
- `X-Forwarded-*` có được chỉ nhận từ trusted proxy không? Host/header spoofing có thể làm sai URL hoặc chính sách.
- Auth response/status/headers có được proxy giữ nguyên không? Đừng biến 401/403 thành 200 “health okay”.
- Actuator startup logs và actual endpoints có khớp external path không?

Đừng cho rằng security matcher viết bằng URI external do user nhìn thấy. Spring Security chạy trên **request đã tới backend** theo servlet context và path rewriting; hãy kiểm thử thực tế ở cả proxy lẫn application.

### TLS và management.ssl

Spring Boot có các cấu hình SSL cho server/management server tùy phiên bản và topology. Dùng TLS cho credentials/metrics nếu qua mạng không hoàn toàn được tin; HTTPS termination ở reverse proxy phải kiểm soát đường sau proxy. Với mTLS, cần trust store và certificate lifecycle rõ ràng, không chỉ bật HTTPS rồi coi client đã được xác thực.

### Spring Security và Actuator JMX

`management.endpoints.web.exposure.*` kiểm soát exposure qua **web HTTP**, **không đồng nghĩa** với JMX exposure. Nếu ứng dụng bật JMX hoặc remote JMX, phải đánh giá cấu hình JMX access/transport riêng. Không vì đã chặn `/manage/metrics` qua HTTP mà suy ra mọi kênh quản trị đều đóng.

### Credentials và secret rotation

Mật khẩu monitoring/OPS trong YAML có thể bị đọc bởi người có quyền truy cập config hoặc logs nếu cấu hình sai. Sử dụng secret manager/Kubernetes Secret qua cơ chế an toàn, phân quyền đọc, rotation có kiểm soát. Kiểm tra mô hình account riêng cho production: user operator không mặc nhiên có quyền vào business endpoints.

## 14. POST management operations: authentication, authorization và CSRF

Nhiều người thấy Actuator dùng chủ yếu GET health/metrics, rồi tắt CSRF chung cho toàn ứng dụng để một POST management endpoint hoạt động. Điều này dễ tạo lỗ hổng cho các thao tác nghiệp vụ dùng session/cookie.

Cần tách ba vấn đề:

1. **Endpoint có được enable và expose không?** Một endpoint không nằm trong HTTP exposure không cần có đường gọi qua web.
2. **Người gọi có authority phù hợp không?** Đừng chỉ dùng `authenticated()` cho thao tác như đổi log levels hoặc shutdown.
3. **Request có rủi ro CSRF không?** Khi dùng cookie/session được browser tự gửi, request đổi trạng thái cần chống CSRF theo threat model; HTTP Basic trên browser cũng có các yếu tố cần cân nhắc về cached credentials. Đừng mặc định “Actuator là machine-to-machine nên không có CSRF” nếu đường management có thể được browser truy cập.

Với các endpoint cần thay đổi trạng thái, cân nhắc:
- Không expose HTTP operation nếu không cần; ưu tiên kênh vận hành riêng hoặc công cụ quản trị có audit.
- Dùng operator/service identity mạnh, quyền tối thiểu, mTLS hoặc mạng riêng.
- Bảo vệ CSRF đúng phần request/credential model thay vì tắt toàn ứng dụng.
- Có change logging/audit và rollback cho thay đổi cấu hình vận hành.
- Kiểm thử HTTP method cụ thể (GET/POST) và cả anonymous, read-only monitor, operator.

### Vì sao chỉ ẩn Actuator endpoint khỏi menu không có giá trị bảo mật?

Actuator endpoints được gọi trực tiếp bởi HTTP client/monitoring tools, không cần UI. Chỉ cần URL bị lộ qua cấu hình hoặc người dùng dò được, request sẽ đến Spring MVC. UI security, CORS hoặc một đường dẫn “bí mật” không thay thế FilterChain authorization.

## 15. Các lỗi cấu hình cần tránh

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Anonymous đọc được metrics | Endpoint expose nhưng custom SecurityFilterChain không match, chain mặc định back off hoặc management context không có chain dự kiến. | Gửi request anonymous tới đúng **management port/path**, kiểm tra chain logs và auto-config. |
| Sau đổi base path, metrics trở thành public | Matcher hard-coded `/actuator/**` không còn match `/manage/**`; fallback quá rộng. | Dùng EndpointRequest theo ID và test sau mọi thay đổi path. |
| Health check bị 401 | Actuator chain yêu cầu OPS cho cả health; thiếu rule riêng hoặc request đi vào chain khác. | Kiểm tra `EndpointRequest.to("health")`, chain order, health path và proxy route. |
| Health tổng quát 200 nhưng lộ details | `management.endpoint.health.show-details=always` hoặc custom health body lộ nội dung. | Test response anonymous và role OPS riêng; hạn chế details. |
| Có management.server.port nhưng endpoint vẫn trên cổng cũ | Cấu hình không được nạp, profile sai hoặc context/port khác mong đợi. | Kiểm tra effective config/startup logs và request tới cả hai cổng. |
| Management port 9090 mở từ Internet | Firewall/ingress/security group hoặc container port mapping quá rộng. | Kiểm tra external network path, không chỉ bind localhost trong tài liệu. |
| Prometheus trả 404 | Chưa có micrometer registry, endpoint không enable/expose hoặc path sai. | Kiểm tra dependency, `exposure.include`, base path và scrape target. |
| Prometheus trả 401 | Scraper thiếu credential/mTLS hoặc auth middleware chưa đồng bộ. | Cấp identity read-only và kiểm tra status; không mở anonymous chỉ để scrape. |
| Metrics gọi bằng OPS vẫn 403 | Authority prefix sai hoặc auth manager/role mapper trả quyền khác. | Kiểm tra `ROLE_OPS`, `hasRole("OPS")` và Authentication. |
| Một chain bao phủ `/**` khiến Actuator chain không chạy | Thứ tự `@Order` sai hoặc chain default đặt trước. | Kiểm tra chain đầu tiên khớp, thêm negative tests. |
| Metrics public sau thêm custom filter chain | Boot management security auto-config có thể back off; chain mới không bảo vệ management. | Xác minh Actuator matcher và anonymous endpoint response sau thay đổi. |
| MockMvc test pass nhưng management port khác public | Test chỉ chạy main context, không gọi management child context. | Viết HTTP integration test dùng `@LocalManagementPort` hoặc test qua deployment thực. |
| Request ngoài proxy bị từ chối nhưng qua proxy được | Rewrite/matcher/forwarded headers không nhất quán hoặc ingress bypass. | Kiểm tra route external và backend cùng lúc. |
| Đổi log level qua POST nhận 403 | Thiếu CSRF token hoặc thiếu authority, endpoint chưa expose. | Xác định đúng nguyên nhân; không disable CSRF toàn site. |
| Không thấy readiness/liveness endpoints | Probes chưa bật hoặc thiếu health groups trong môi trường test. | Kiểm tra `management.endpoint.health.probes.enabled` và health groups. |
| App vẫn chạy khi management health trả 503 | Một health contributor DOWN dù HTTP server còn sống. | Phân biệt readiness/liveness và health status mapping. |

## 16. Checklist bảo vệ Actuator trước khi mở production

1. **Kiểm kê endpoint IDs** đang enable/expose trên mỗi profile; giữ `web.exposure.include` ở mức tối thiểu. Đặc biệt tránh wildcard trong production.
2. **Tách cổng** nếu cần phân vùng mạng quản trị, nhưng không coi cổng riêng là authentication. Kiểm tra địa chỉ bind và khả năng kết nối thực tế.
3. **Khóa network route** bằng firewall/security group/NetworkPolicy/ingress; chỉ monitoring/operator được tới cổng nhạy cảm.
4. **SecurityFilterChain** được áp dụng đúng web/management context, đúng thứ tự `@Order`, và matcher `EndpointRequest.toAnyEndpoint()` không bị chain khác che.
5. **Health public có giới hạn** chỉ khi cần; details, groups và status payload đã được đánh giá. Info/metrics/prometheus không mặc định công khai.
6. **Tách MONITOR và OPS** theo least privilege nếu hệ thống cần cả scraper và operator; xem xét endpoint READ/WRITE và authentication manager khác nhau.
7. **Không tắt CSRF đại trà** để làm một POST management operation chạy; đánh giá credential/session model thực tế.
8. **Kiểm thử anonymous và credential sai**, không chỉ OPS được xem metrics. Test cả status/body và không leak dữ liệu.
9. **Kiểm thử hai cổng** nếu management port tách biệt: gửi HTTP tới đúng management port, không chỉ MockMvc main context.
10. **Kiểm thử base-path/path-mapping** sau khi đổi, kể cả reverse proxy và URL cũ; không hard-code matcher sai.
11. **Credentials/TLS** được bảo vệ: secret store, rotation, HTTPS/mTLS, tránh log password và metric labels chứa PII.
12. **Đánh giá JMX** như kênh quản trị riêng, không suy luận từ HTTP exposure.
13. **Quan sát runtime**: cảnh báo khi management path trả 401/403/404/503 bất thường, nhưng tránh tự động mở endpoint để “sửa” monitoring.
14. **Test sau nâng cấp Boot/Security** và sau khi đổi dependency/management topology; endpoint mappings, management context và auto-configuration có thể thay đổi.
15. **Rà soát đặc quyền**: bảo đảm identity OPS không vô tình truy cập tất cả business endpoints chỉ vì fallback chain dùng `authenticated()`.

## 17. Tình huống thực tế: chọn topology đúng

### A. Một máy nội bộ, ứng dụng đơn giản

- Giữ Actuator chung cổng với API nếu hạ tầng không yêu cầu phân tách.
- Expose `health` và chỉ những endpoints giám sát cần thiết.
- Dùng Actuator chain `EndpointRequest` ưu tiên trước fallback.
- Health có thể public trong mạng nội bộ với ít details; metrics yêu cầu authentication.

### B. Dịch vụ dùng Prometheus/Kubernetes

- Chọn network service dành cho monitoring, tránh đưa metrics lên public ingress.
- Bật `prometheus` chỉ khi có Micrometer registry và scrape target phù hợp.
- Dùng identity/role `MONITOR` read-only và network policies; hạn chế sensitive metric labels.
- Thiết kế health/readiness/liveness theo semantics orchestrator, cân nhắc cổng quản trị riêng có phản ánh sức khỏe application port hay không.

### C. Enterprise production có operator và SSO

- Management port riêng có thể giúp phân vùng mạng nhưng cần test đúng management context.
- Operator auth nên qua identity/provider đã được quản lý và MFA ở tầng truy cập phù hợp; không tự dùng một user in-memory password hard-coded như demo.
- Giới hạn endpoints vận hành nhạy cảm theo quyền tối thiểu, audit thay đổi log levels hoặc actions gây side effect.
- Kiểm thử cả ingress/proxy, TLS, account revocation và credential rotation; không chỉ MockMvc.

### D. Chỉ cần health cho load balancer

- Đừng expose toàn bộ `metrics`, `env`, `configprops` khi không có nhu cầu.
- Cân nhắc chỉ expose health status (và probes khi cần); ẩn details nội bộ.
- Nếu health public, kết hợp network restriction hoặc response minimization theo threat model.

## 18. Ghi nhớ

Bảo vệ Actuator là **một bài toán phối hợp ba lớp**:

~~~text
Exposure tối thiểu
   +
Cổng / mạng quản trị được kiểm soát
   +
SecurityFilterChain chọn đúng endpoint, yêu cầu đúng quyền
   =
Bề mặt quản trị được bảo vệ tốt hơn
~~~

`management.server.port` giúp tách traffic **nhưng không tự xác thực**. `management.endpoints.web.base-path` đổi URL **nhưng không phải biện pháp giấu bí mật**. `management.endpoints.web.exposure.include` quyết định **endpoint nào có thể xuất hiện qua HTTP**, còn `EndpointRequest` và `SecurityFilterChain` quyết định **ai được phép gọi**. Nếu management server dùng **cổng riêng**, phải kiểm thử chính cổng đó để xác nhận chain và permissions thực sự có hiệu lực.

**Quy tắc thực hành:** *Chỉ expose những thứ cần giám sát, chỉ cho những hệ thống được phép kết nối, và luôn kiểm tra anonymous/OPS trên đúng cổng cùng đúng đường dẫn đang vận hành.*

## Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Security Reference — Servlet Architecture and SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
