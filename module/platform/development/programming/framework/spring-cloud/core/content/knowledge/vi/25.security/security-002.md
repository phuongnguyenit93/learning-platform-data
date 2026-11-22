# Xác thực và phân quyền cho env, refresh, restart và serviceregistry

> **Chương:** Bảo mật
> **Module:** `SPRING_CLOUD_CORE` — hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình bên ngoài và tương thích phiên bản với Spring Boot. Người học tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử, vận hành các abstraction chung.
> **Trọng tâm:** Các Actuator endpoint do Spring Cloud bổ sung có thể đọc hoặc thay đổi Environment, làm mới bean, khởi động lại ApplicationContext và đổi trạng thái đăng ký service. Bài học tập trung vào xác thực người gọi, phân quyền theo vai trò, giới hạn endpoint được expose và bảo vệ các thao tác vận hành có ảnh hưởng đến toàn bộ service.

## 1. Vì sao các endpoint quản trị cần được bảo vệ?

Spring Boot Actuator cung cấp các endpoint để quan sát và điều khiển ứng dụng. Spring Cloud Context và Spring Cloud Commons bổ sung một số endpoint phục vụ cấu hình runtime và service registry. Chúng hữu ích cho vận hành, nhưng quyền gọi endpoint có thể tương đương quyền điều khiển một phần quan trọng của ứng dụng.

Bốn endpoint cần đặc biệt chú ý:

| Endpoint | Chức năng | Rủi ro khi bị gọi trái phép |
| --- | --- | --- |
| `/actuator/env` | Đọc Environment; POST có thể cập nhật property, rebind `@ConfigurationProperties` và cập nhật log level | Thay đổi cấu hình runtime, làm lộ tên property hoặc thông tin nội bộ |
| `/actuator/refresh` | Nạp lại cấu hình và làm mới các bean thuộc `@RefreshScope` | Thay đổi hành vi của ứng dụng khi đang chạy |
| `/actuator/restart` | Đóng và khởi động lại `ApplicationContext` | Gây gián đoạn, khởi tạo lại các bean và kết nối |
| `/actuator/serviceregistry` | GET đọc trạng thái registration; POST đổi trạng thái registration | Đưa instance ra khỏi traffic hoặc làm instance nhận traffic trở lại |

Một người gọi có quyền POST tới `env` có thể thay đổi property ảnh hưởng đến kết nối database, logging hoặc hành vi nghiệp vụ nếu không giới hạn key. Người có quyền gọi `serviceregistry` có thể thay đổi trạng thái instance theo khả năng của provider. Quyền gọi `restart` có thể tác động tới tính sẵn sàng của service.

Vì vậy, không nên xem các endpoint này như API nghiệp vụ thông thường. Chúng thuộc mặt phẳng quản trị (management plane), cần xác thực, phân quyền, giới hạn mạng và audit riêng.

### Kết quả học tập

Sau bài này, người học có thể:

1. giải thích chức năng và rủi ro của `env`, `refresh`, `restart` và `serviceregistry`;
2. phân biệt endpoint được bật, được expose và được cấp quyền truy cập;
3. cấu hình danh sách Actuator endpoint cần expose;
4. dùng Spring Security `SecurityFilterChain` và `EndpointRequest` để bảo vệ endpoint;
5. phân quyền vận hành theo role;
6. giới hạn property được cập nhật qua `env` POST;
7. bảo vệ thao tác POST và hiểu CSRF;
8. tách management port và network khỏi traffic nghiệp vụ;
9. kiểm thử các trường hợp chưa xác thực, thiếu quyền và có quyền;
10. xây dựng quy trình audit và vận hành an toàn.

## 2. Ba lớp kiểm soát khác nhau

### 2.1. Endpoint availability

Một endpoint chỉ hoạt động nếu dependency, auto-configuration và điều kiện của endpoint cho phép nó được tạo. Ví dụ, `serviceregistry` cần có `Registration` bean phù hợp trong ApplicationContext. Endpoint `restart` của Spring Cloud Context bị tắt theo mặc định trong các cấu hình được tài liệu mô tả.

Endpoint không có sẵn sẽ không thể được bật chỉ bằng cách thêm URL vào exposure list.

### 2.2. Exposure

Exposure quyết định endpoint có được công bố qua HTTP hoặc JMX hay không. Mặc định, Spring Boot chỉ expose `health` qua HTTP. Các endpoint khác không tự động trở thành URL công khai.

Ví dụ, cấu hình sau chỉ expose các endpoint được liệt kê:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Nếu cần expose endpoint quản trị, chỉ thêm những endpoint thực sự cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - refresh
          - serviceregistry
```

Ví dụ trên chưa expose `restart`. Chỉ thêm endpoint này sau khi có quy trình vận hành và quyền quản trị phù hợp; việc expose không tự bật endpoint đang bị disable.

Không dùng `include: "*"` trong production nếu không có yêu cầu rõ ràng và kiểm soát bảo mật tương ứng. Khi cấu hình cả `include` và `exclude`, danh sách exclude có độ ưu tiên cao hơn.

### 2.3. Authentication và authorization

- **Authentication (xác thực):** xác định người hoặc service đang gọi là ai. Ví dụ: HTTP Basic, OAuth2 Resource Server/JWT hoặc mTLS ở gateway.
- **Authorization (phân quyền):** quyết định danh tính đó được gọi endpoint nào và được thực hiện thao tác gì. Ví dụ: role `OPS_VIEWER` chỉ đọc endpoint quan sát; role `OPS_ADMIN` được phép gọi endpoint thay đổi trạng thái.

Một endpoint đã expose nhưng chưa có authentication và authorization phù hợp có thể trở thành điểm điều khiển từ xa. Ngược lại, một người dùng có role phù hợp vẫn không gọi được endpoint nếu endpoint chưa được expose hoặc chưa được bật.

## 3. Hiểu quyền của từng endpoint

### 3.1. env — đọc và cập nhật Environment

Endpoint `/actuator/env` cung cấp thông tin về property source và các property trong Environment. Giá trị nhạy cảm được Spring Boot sanitization theo mặc định ở các phiên bản hiện hành, nhưng tên property, tên nguồn cấu hình và cấu trúc môi trường vẫn có thể tiết lộ thông tin nội bộ.

POST tới `env` có thể cập nhật Environment, rebind `@ConfigurationProperties` và cập nhật log level. Để bật thao tác POST, Spring Cloud yêu cầu cấu hình:

```yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(acme\.runtime\.|feature\.).*'
```

`valid-keys-regex` là biểu thức chính quy giới hạn các property name được phép cập nhật. Ví dụ chỉ cho phép các key bắt đầu bằng `acme.runtime.` hoặc `feature.`.

Không nên dùng regex quá rộng như `.*` hoặc cho phép thay đổi tùy ý các nhóm property có thể ảnh hưởng đến bảo mật và hạ tầng, chẳng hạn:

- `management.*`;
- `spring.security.*`;
- `spring.datasource.*`;
- `server.*`;
- các property chứa endpoint hoặc credential của hệ thống bên ngoài.

Chỉ bật POST khi có use case vận hành cụ thể. Nếu chỉ cần quan sát, có thể expose GET theo chính sách quản trị mà không bật POST. Role truy cập vẫn cần được giới hạn; regex không thay thế authorization.

### 3.2. refresh — làm mới cấu hình và bean

`/actuator/refresh` yêu cầu Spring Cloud Context nạp lại cấu hình phù hợp và làm mới các bean thuộc `@RefreshScope`. Target bean bị invalidate và được tạo lại khi proxy được sử dụng ở lần tiếp theo.

Thao tác refresh có thể làm thay đổi endpoint, timeout, feature property hoặc cấu hình client đang được bean sử dụng. Nếu property mới sai, ứng dụng có thể gặp lỗi sau refresh dù process vẫn đang chạy.

Chỉ cấp quyền refresh cho nhóm vận hành hiểu tác động của cấu hình. Sau khi refresh, nên có kiểm tra sức khỏe hoặc smoke test cho chức năng liên quan.

### 3.3. restart — khởi động lại ApplicationContext

`/actuator/restart` yêu cầu đóng và khởi động lại ApplicationContext. Endpoint này bị disable theo mặc định trong tài liệu Spring Cloud Context.

Restart có ảnh hưởng lớn hơn refresh bean: context đóng, các bean lifecycle được hủy và container khởi tạo lại. Kết nối, listener, client và các thành phần phụ thuộc có thể bị gián đoạn trong quá trình này.

Chỉ bật restart khi ứng dụng có quy trình vận hành phù hợp. Trong môi trường container/orchestrator, nên cân nhắc để nền tảng triển khai quản lý rollout hoặc restart thay vì cung cấp quyền restart tùy ý qua endpoint ứng dụng.

Các endpoint `pause` và `resume` cũng có thể điều khiển lifecycle của các thành phần được hỗ trợ. Nếu expose chúng, hãy áp dụng cùng chính sách bảo vệ nghiêm ngặt.

### 3.4. serviceregistry — thay đổi trạng thái registration

Spring Cloud Commons cung cấp endpoint `/actuator/serviceregistry` khi ApplicationContext có `Registration` bean phù hợp:

- GET trả trạng thái registration hiện tại.
- POST nhận payload JSON có trường `status` và yêu cầu đổi trạng thái registration.

Ví dụ payload:

```json
{
  "status": "OUT_OF_SERVICE"
}
```

Giá trị được chấp nhận phụ thuộc service registry provider. Ví dụ Eureka hỗ trợ các trạng thái `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. Không áp dụng các giá trị này như contract chung cho Consul hoặc provider khác.

Đổi trạng thái có thể ảnh hưởng đến việc LoadBalancer hoặc thành phần discovery chọn instance. Chẳng hạn, chuyển instance sang `OUT_OF_SERVICE` có thể làm instance ngừng nhận traffic mới theo cách provider tích hợp xử lý trạng thái đó.

Chỉ role quản trị service registry mới nên được POST. Cần audit người thực hiện, service instance, trạng thái trước/sau, thời điểm và lý do thay đổi.

## 4. Xây dựng SecurityFilterChain cho Actuator

### 4.1. Hành vi mặc định của Spring Boot

Nếu Spring Security có trên classpath và ứng dụng không khai báo `SecurityFilterChain` riêng, Spring Boot tự cấu hình bảo vệ các Actuator endpoint ngoài `health`.

Khi ứng dụng tự khai báo một `SecurityFilterChain`, cấu hình bảo mật Actuator tự động của Spring Boot sẽ lùi lại. Khi đó, ứng dụng chịu trách nhiệm viết các quy tắc cho cả endpoint quản trị và các route còn lại.

Đây là điểm thường gây lỗi: nhóm phát triển thêm một SecurityFilterChain để bảo vệ API nghiệp vụ, vô tình làm mất quy tắc Actuator mặc định mà không bổ sung matcher cho management endpoints.

### 4.2. Phân quyền theo role

Ví dụ servlet application dùng Spring Security và matcher của Actuator:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to(
                        "env",
                        "refresh",
                        "restart",
                        "serviceregistry",
                        "pause",
                        "resume"
                )).hasRole("OPS_ADMIN")
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS_VIEWER")
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Trong ví dụ:

- `OPS_ADMIN` có quyền với các endpoint quản trị nhạy cảm.
- `OPS_VIEWER` có quyền với các Actuator endpoint còn lại.
- Các route nghiệp vụ khác yêu cầu người gọi đã xác thực.

`EndpointRequest.to("env", ...)` match endpoint theo ID và các subpath của endpoint, không phụ thuộc hoàn toàn vào chuỗi URL mặc định. Điều này hữu ích khi management base path được thay đổi.

Đây là ví dụ cho servlet stack trên Spring Boot 4. Với Spring Boot 3.x, package `EndpointRequest` thường là `org.springframework.boot.actuate.autoconfigure.security.servlet`. Với WebFlux, cần dùng security configuration và matcher dành cho reactive stack.

HTTP Basic trong ví dụ chỉ minh họa cơ chế xác thực. Production nên tích hợp danh tính từ hệ thống tập trung, chẳng hạn OAuth2 Resource Server/JWT hoặc gateway có mTLS và chuyển tiếp identity an toàn.

### 4.3. Role không tự tạo danh tính

`hasRole("OPS_ADMIN")` kiểm tra authority `ROLE_OPS_ADMIN` trên Authentication hiện tại. Ứng dụng vẫn cần cấu hình nơi xác thực và ánh xạ role từ nguồn danh tính.

Không hard-code mật khẩu quản trị trong source code hoặc file cấu hình được commit. Quản lý credential bằng secret store, identity provider hoặc cơ chế cấp phát của nền tảng. Thu hồi quyền khi nhân sự hoặc service account không còn nhiệm vụ vận hành.

### 4.4. Nếu tách riêng management SecurityFilterChain

Có thể tạo chain chỉ áp dụng cho Actuator bằng `securityMatcher(EndpointRequest.toAnyEndpoint())`. Khi làm vậy, cần có chain khác bảo vệ các route còn lại của ứng dụng.

Ví dụ:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.toAnyEndpoint());

    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(EndpointRequest.to(
                    "env", "refresh", "restart", "serviceregistry", "pause", "resume"
            )).hasRole("OPS_ADMIN")
            .anyRequest().hasRole("OPS_VIEWER")
    );

    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Chain này chỉ xử lý Actuator. Phải cấu hình thêm một SecurityFilterChain có thứ tự phù hợp để bảo vệ các endpoint nghiệp vụ. Nếu không, request không match chain Actuator có thể không được chain này bảo vệ.

## 5. Bảo vệ thao tác POST và CSRF

### 5.1. POST là thao tác thay đổi trạng thái

Trong các endpoint đang xét:

- `POST /actuator/env` cập nhật Environment;
- `POST /actuator/refresh` làm mới cấu hình và refresh scope;
- `POST /actuator/restart` khởi động lại context;
- `POST /actuator/serviceregistry` đổi trạng thái registration.

Đây là các thao tác có side effect. Không nên chỉ kiểm tra endpoint có thể truy cập bằng GET rồi kết luận endpoint đã được bảo vệ đầy đủ.

### 5.2. CSRF protection

Spring Security bật CSRF protection theo mặc định cho các ứng dụng web phù hợp. Khi POST endpoint được bảo vệ bởi CSRF, request không có CSRF token hợp lệ có thể nhận HTTP 403 dù người gọi đã đăng nhập.

Không tắt CSRF một cách toàn cục chỉ để làm cho lệnh curl POST chạy được. Với client trình duyệt dùng session/cookie, cần cung cấp và gửi CSRF token. Với management API chỉ dành cho machine-to-machine, có thể thiết kế authentication stateless bằng bearer token và chính sách CSRF phù hợp với mô hình client đó.

Tài liệu Spring Boot khuyến nghị chỉ tắt CSRF hoàn toàn khi service được sử dụng bởi non-browser clients. Hãy xác định rõ cách xác thực trước khi thay đổi chính sách này.

### 5.3. Phân biệt 401, 403 và 404

| HTTP status | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| 401 Unauthorized | Chưa xác thực hoặc credential không hợp lệ | Token, Basic credential, identity provider |
| 403 Forbidden | Đã xác thực nhưng thiếu quyền, hoặc thiếu CSRF token | Role/authority, policy CSRF |
| 404 Not Found | Endpoint chưa expose, chưa available hoặc URL/base path sai | Exposure, dependency, endpoint enablement, management base path |
| 405 Method Not Allowed | Endpoint có tồn tại nhưng không hỗ trợ HTTP method đó | Đọc operation của endpoint và dùng đúng method |
| 400 Bad Request | Payload thiếu trường hoặc sai định dạng | JSON body và tên field theo endpoint |

Không xử lý 403 bằng cách bỏ toàn bộ CSRF hoặc mở endpoint cho anonymous. Trước tiên hãy xác định request thất bại ở authentication, authorization hay CSRF filter.

## 6. Tách management port và network

### 6.1. Dùng management port riêng

Có thể đưa Actuator sang port riêng:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,info,env,refresh,serviceregistry
```

Management port riêng giúp tách traffic quản trị khỏi traffic nghiệp vụ. Tuy nhiên, việc dùng port khác không tự động tạo authentication, authorization hoặc firewall rule.

Cần giới hạn port này bằng network policy, security group, firewall hoặc service nội bộ. Chỉ hệ thống monitoring và nhóm vận hành được phép truy cập. Không publish management port ra Internet nếu không có yêu cầu và lớp bảo vệ tương ứng.

### 6.2. Management address và container

Nếu cấu hình management server chỉ bind vào loopback, các thành phần bên ngoài process có thể không truy cập được. Nếu bind lên interface mạng của container, cần giới hạn ingress ở network layer.

Hãy kiểm tra topology thực tế: Kubernetes Service, Ingress, service mesh, load balancer và firewall có thể làm endpoint management vô tình được route công khai dù ứng dụng không chủ đích như vậy.

### 6.3. Tách quyền monitoring và quyền vận hành

Monitoring thường chỉ cần đọc health, metrics và thông tin quan sát được cho phép. Nhóm vận hành có thể cần refresh hoặc xem registration. Nhóm quản trị cao hơn mới được restart hoặc đổi trạng thái registration.

Không dùng chung một tài khoản admin cho monitoring agent, deployment automation và người vận hành. Mỗi identity chỉ nên có quyền tối thiểu cần thiết.

## 7. Cấu hình an toàn theo môi trường

### 7.1. Local development

Trong local, có thể expose endpoint cần thiết để debug:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,refresh,serviceregistry
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(demo\.|feature\.).*'
```

Dù chạy local, không nên dùng cấu hình này cho production chỉ bằng cách copy file. Tách profile và kiểm tra profile đang active.

### 7.2. Production mặc định tối thiểu

Nếu production chỉ cần health và info:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      post:
        enabled: false
```

Không expose env, refresh, restart hoặc serviceregistry nếu không có quy trình quản trị cần chúng. Restart endpoint vốn bị disable theo mặc định trong tài liệu Spring Cloud Context; hãy giữ trạng thái này nếu không có lý do rõ ràng.

### 7.3. Production có nhu cầu refresh

Nếu quy trình vận hành cần refresh cấu hình, chỉ expose endpoint refresh trong management network và yêu cầu role vận hành:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

SecurityFilterChain vẫn phải yêu cầu authentication và role phù hợp. Exposure list không phải cơ chế phân quyền.

### 7.4. Bảo vệ dữ liệu Environment

Không cấu hình Actuator để trả secret nguyên văn cho mọi người dùng. Ở các phiên bản hỗ trợ cấu hình show-values, giữ chế độ sanitization mặc định hoặc chỉ cho role quản trị được xem giá trị sau khi đánh giá rủi ro.

Không đưa password, token, private key hoặc connection secret vào request body của ticket, log hay audit record. Nếu cần thay secret, dùng secret management workflow có rotation và audit thay vì POST trực tiếp giá trị bí mật qua endpoint mở rộng.

## 8. Audit và kiểm soát thao tác vận hành

Với endpoint có side effect, cần ghi lại:

- danh tính người hoặc service account thực hiện;
- endpoint và HTTP method;
- instance/application/environment mục tiêu;
- thời điểm và kết quả;
- property key đã thay đổi (tránh ghi giá trị secret);
- registration status trước và sau;
- lý do, change ticket hoặc mã phê duyệt nếu quy trình yêu cầu.

Audit record cần đủ để truy vết nhưng không làm lộ credential. Đồng bộ thời gian giữa các instance để đối chiếu log. Bảo vệ log khỏi sửa/xóa trái phép và giới hạn người được đọc.

Nên có quy trình xác nhận trước thao tác có ảnh hưởng rộng. Ví dụ, trước khi gọi restart hoặc chuyển registration sang `OUT_OF_SERVICE`, kiểm tra số instance còn lại và tình trạng traffic. Đây là kiểm soát vận hành; role authorization một mình không bảo đảm thao tác an toàn.

## 9. Kiểm thử bảo mật endpoint

### 9.1. Kiểm tra người chưa xác thực

Với endpoint được expose và bảo vệ, request không credential phải bị từ chối:

```java
mockMvc.perform(get("/actuator/env"))
        .andExpect(status().isUnauthorized());
```

Kết quả cụ thể phụ thuộc authentication entry point. Nếu endpoint không expose, response có thể là 404 thay vì 401; test phải xác định cấu hình dự kiến.

### 9.2. Kiểm tra user có role viewer

User chỉ có role `OPS_VIEWER` có thể đọc endpoint được cho phép nhưng không thể gọi endpoint quản trị:

```java
mockMvc.perform(post("/actuator/refresh")
        .with(user("observer").roles("OPS_VIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

Ví dụ này giả định CSRF protection đang bật và endpoint đã expose. `csrf()` thêm token hợp lệ để assertion tập trung vào authorization.

### 9.3. Kiểm tra user có role admin

User có role `OPS_ADMIN` được phép gọi thao tác quản trị nếu endpoint đã available và payload hợp lệ:

```java
mockMvc.perform(post("/actuator/refresh")
        .with(user("operator").roles("OPS_ADMIN"))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

Trong test thật, cần kiểm tra side effect phù hợp hoặc mock collaborator để xác nhận refresh được gọi. Không chỉ kiểm tra HTTP 2xx nếu mục tiêu là xác minh bean đã thực sự được làm mới.

### 9.4. Kiểm tra env valid-keys-regex

Test POST `env` với một property key được cho phép và một key bị cấm. Xác nhận key ngoài whitelist bị từ chối hoặc không được áp dụng theo hành vi của phiên bản đang dùng.

Đặc biệt kiểm tra các namespace nhạy cảm như security, datasource, management và server. Một regex quá rộng có thể biến endpoint env thành cơ chế thay đổi cấu hình không giới hạn.

### 9.5. Kiểm tra serviceregistry

Kiểm thử:

1. GET trả status registration hiện tại;
2. user viewer không được POST thay đổi status;
3. user admin có thể POST giá trị status hợp lệ theo provider;
4. status không hợp lệ bị từ chối theo provider;
5. audit ghi lại danh tính và trạng thái trước/sau;
6. thay đổi status có tác động đúng đến discovery/load balancing theo integration.

Không hard-code danh sách status của Eureka cho test dùng Consul hoặc provider khác.

### 9.6. Kiểm tra restart trong context riêng

Restart có thể đóng context test đang chạy. Hãy kiểm tra endpoint enablement và authorization bằng test riêng, tránh gọi restart trong suite dùng chung ApplicationContext. Nếu cần xác minh restart end-to-end, chạy ứng dụng thử trong process hoặc container riêng và quan sát lifecycle từ bên ngoài.

## 10. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/env` trả 404 | Endpoint chưa expose hoặc endpoint không available | Kiểm tra Actuator dependency, exposure và endpoint availability |
| POST `/actuator/env` trả 404/405 | POST chưa được enable hoặc endpoint không hỗ trợ operation | Kiểm tra `management.endpoint.env.post.enabled` và phiên bản |
| POST `/actuator/env` bị từ chối với key | Key không khớp `valid-keys-regex` | Kiểm tra whitelist và tên property |
| Request trả 401 | Thiếu hoặc sai credential/token | Kiểm tra authentication |
| Request trả 403 | Thiếu role hoặc thiếu CSRF token | Phân biệt authorization và CSRF |
| User admin vẫn bị 403 | Role mapping không tạo `ROLE_OPS_ADMIN`, hoặc CSRF chưa hợp lệ | Kiểm tra authority và request token |
| Endpoint refresh trả 404 | Spring Cloud Context endpoint chưa có hoặc chưa expose | Kiểm tra dependency, endpoint availability và exposure |
| Restart không hoạt động | Endpoint disabled theo mặc định hoặc không được expose | Kiểm tra endpoint enablement theo release và quy trình vận hành |
| `/serviceregistry` trả 404 | Không có Registration bean phù hợp | Kiểm tra discovery provider và registration lifecycle |
| POST serviceregistry bị từ chối | Status không được provider hỗ trợ hoặc thiếu quyền | Đọc provider contract và security policy |
| Actuator mất bảo vệ sau khi thêm SecurityFilterChain | Custom chain khiến Boot security auto-configuration lùi lại | Bổ sung matcher và rule cho Actuator |
| Management port vẫn truy cập từ Internet | Network route/firewall/security group mở rộng | Kiểm tra ingress và network policy |

## 11. Quy trình thiết kế quyền quản trị

Khi thêm một endpoint vào production, thực hiện lần lượt:

1. Xác định thao tác cần thiết và lý do nghiệp vụ/vận hành.
2. Xác định endpoint ID, HTTP method và side effect.
3. Xác nhận endpoint có available trong phiên bản Spring Cloud đang dùng.
4. Chỉ expose endpoint qua management interface cần thiết.
5. Đặt authentication bằng identity provider hoặc service identity.
6. Ánh xạ role riêng cho viewer, operator và admin.
7. Bảo vệ POST bằng authorization và CSRF policy phù hợp.
8. Với env POST, giới hạn property key bằng valid-keys regex.
9. Giới hạn network access vào management port.
10. Bật audit cho thao tác thay đổi trạng thái.
11. Viết test 401, 403, success và invalid payload.
12. Diễn tập refresh/restart/registry status change ở môi trường staging trước production.

## 12. Bài tập vận dụng

### Bài tập 1 — POST env có thể thay đổi cấu hình nhạy cảm

Một ứng dụng bật POST `/actuator/env`. Người vận hành có thể cập nhật cả `feature.*` và `spring.datasource.*`.

Hãy giải thích rủi ro và thiết kế `valid-keys-regex` chỉ cho phép nhóm property runtime được phê duyệt. Nêu các role và audit field cần có.

### Bài tập 2 — Viewer gọi refresh

Một tài khoản monitoring có role `OPS_VIEWER` gọi POST `/actuator/refresh` và nhận 403.

Hãy giải thích vì sao đây là kết quả đúng. Đề xuất role tối thiểu cần thiết cho refresh và cách kiểm tra request không bị chặn nhầm bởi CSRF.

### Bài tập 3 — Thêm SecurityFilterChain làm Actuator không còn bảo vệ

Sau khi nhóm phát triển thêm một SecurityFilterChain cho API nghiệp vụ, `/actuator/env` không còn yêu cầu authentication.

Hãy giải thích vì sao Boot security auto-configuration đã lùi lại. Viết matcher cho các endpoint nhạy cảm và quy tắc bảo vệ những endpoint còn lại.

### Bài tập 4 — Restart endpoint trong production

Một nhóm muốn expose `/actuator/restart` để người dùng support tự khởi động lại service.

Hãy phân tích tác động lên ApplicationContext, availability và tài nguyên lifecycle. Đề xuất quy trình thay thế hoặc role vận hành có kiểm soát.

### Bài tập 5 — Đổi registration status

Một instance Eureka đang nhận traffic. Người vận hành POST `OUT_OF_SERVICE` qua `/actuator/serviceregistry`.

Hãy giải thích ảnh hưởng dự kiến đến discovery và load balancing, cách kiểm tra status hợp lệ, và các thông tin cần ghi audit.

### Bài tập 6 — Management port riêng nhưng chưa an toàn

Ứng dụng chuyển Actuator sang port 9001 nhưng load balancer công khai vẫn route tới port này.

Hãy xác định vì sao port riêng không thay thế authentication/authorization và đề xuất network policy để chỉ monitoring và nhóm vận hành truy cập được.

## 13. Tự kiểm tra nhanh

1. Spring Boot mặc định expose endpoint nào qua HTTP? **Health.**
2. Exposure có đồng nghĩa người gọi được phép thao tác không? **Không, còn cần authentication và authorization.**
3. POST `/actuator/env` cần bật property nào? **`management.endpoint.env.post.enabled=true`.**
4. Property nào giới hạn key được cập nhật qua env POST? **`management.endpoint.env.post.valid-keys-regex`.**
5. `/actuator/refresh` làm gì? **Nạp lại cấu hình phù hợp và refresh các bean thuộc RefreshScope.**
6. `/actuator/restart` có được bật mặc định không? **Không, endpoint này bị disable theo mặc định trong Spring Cloud Context.**
7. `/actuator/serviceregistry` cần bean nào? **Registration bean phù hợp với provider.**
8. Status serviceregistry có giống nhau giữa mọi provider không? **Không, phụ thuộc implementation.**
9. Khi có custom SecurityFilterChain, Boot có tiếp tục tự cấu hình bảo mật Actuator không? **Không, ứng dụng phải tự cấu hình các rule.**
10. `EndpointRequest.to("env")` có match subpath endpoint không? **Có, matcher theo endpoint ID và các subpath của endpoint.**
11. CSRF protection mặc định của Spring Security có thể làm POST trả 403 không? **Có, nếu request không có token hợp lệ.**
12. Management port riêng có tự động bảo vệ endpoint không? **Không, vẫn cần security và network policy.**

**Thông điệp cốt lõi:** `env`, `refresh`, `restart` và `serviceregistry` là các điểm điều khiển quan trọng của service. Hãy chỉ bật và expose endpoint thật sự cần thiết, xác thực identity, phân quyền theo role, giới hạn property được cập nhật, bảo vệ POST/CSRF, tách management network và audit mọi thao tác có side effect. Một management API an toàn phải kiểm soát được cả người gọi, phạm vi thao tác và môi trường mà thao tác tác động tới.

**Tài liệu tham khảo:**

- [Spring Cloud Commons — Application Context Services and Actuator Endpoints](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Commons — Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Boot — Actuator Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot API — EndpointRequest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/servlet/EndpointRequest.html)

Endpoint availability, package name của matcher, access policy và một số property có thể thay đổi theo phiên bản Spring Boot/Spring Cloud. Đối chiếu release train tương thích của dự án trước khi áp dụng.
