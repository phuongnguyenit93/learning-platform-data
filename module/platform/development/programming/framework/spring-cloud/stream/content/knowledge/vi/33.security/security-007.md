# Bảo vệ Actuator và thao tác điều khiển binding

Spring Cloud Stream có thể công bố thông tin binding qua Spring Boot Actuator và cho phép người vận hành dừng, khởi động, tạm dừng hoặc tiếp tục một binding. Các endpoint này hữu ích khi xử lý sự cố, nhưng chúng cũng tiết lộ cấu hình kết nối broker và có thể thay đổi luồng message đang chạy. Vì vậy, cần kiểm soát đồng thời việc expose endpoint, quyền đọc thông tin và quyền thực hiện thao tác thay đổi trạng thái.

Trong ứng dụng xử lý sự kiện, một request không được phép vào `/actuator/bindings` có thể làm lộ tên topic, consumer group, cấu hình retry, địa chỉ broker hoặc thông tin xác thực. Một request POST trái phép còn có thể dừng consumer, làm backlog tăng, ngắt việc xử lý đơn hàng hoặc thay đổi thời điểm giao message. Bài học này trình bày cách triển khai Actuator có giới hạn, bảo vệ thao tác điều khiển binding và kiểm thử quyền truy cập.

## 1. Actuator và binding endpoint cung cấp những gì?

Spring Boot Actuator cung cấp các endpoint quản trị và quan sát ứng dụng. Spring Cloud Stream bổ sung endpoint `bindings` để xem các binding hiện tại và điều khiển vòng đời của từng binding.

Khi có dependency web và Actuator, Spring Cloud Stream có thể công bố các route sau:

| HTTP method | Endpoint | Mục đích |
|---|---|---|
| `GET` | `/actuator/bindings` | Liệt kê các binding |
| `GET` | `/actuator/bindings/{bindingName}` | Xem trạng thái một binding |
| `POST` | `/actuator/bindings/{bindingName}` | Thay đổi trạng thái binding bằng JSON |

Ví dụ tên binding của function `processOrder` có thể là `processOrder-in-0`. Đây là tên binding do Spring Cloud Stream tạo từ function definition; nó không nhất thiết giống tên topic hoặc queue trên broker.

Endpoint này có thể trả thông tin như:

- Tên binding và destination.
- Binding là input hay output.
- Consumer group.
- Binder được sử dụng.
- Trạng thái lifecycle hiện tại.
- Một số thuộc tính consumer/producer mở rộng của binder.

Thông tin chi tiết giúp chẩn đoán lỗi, nhưng cũng có thể tiết lộ cách hệ thống kết nối Kafka, RabbitMQ hoặc Pulsar. Hãy coi cả request GET là một thao tác cần được bảo vệ.

## 2. Thêm dependency và chỉ expose endpoint cần thiết

Actuator và web là dependency tùy chọn của Spring Cloud Stream. Ứng dụng cần thêm Actuator và một web stack như Spring MVC hoặc WebFlux:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu ứng dụng dùng WebFlux, thay `spring-boot-starter-web` bằng `spring-boot-starter-webflux` và chọn cấu hình Spring Security tương ứng với reactive stack. Không thêm đồng thời hai web stack chỉ để bật Actuator.

Spring Boot mặc định chỉ expose `health` qua HTTP. Để bật binding endpoint, cần thêm `bindings` vào danh sách exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,bindings"
~~~

Danh sách này chỉ expose ba endpoint được chọn. Tránh dùng `include: "*"` cho ứng dụng production vì nó có thể công bố thêm các endpoint chứa cấu hình, log, bean, heap dump hoặc thao tác quản trị khác.

Có ba điều kiện cần phân biệt:

1. **Có endpoint:** dependency và auto-configuration đã đăng ký endpoint.
2. **Được phép truy cập:** cấu hình access của Actuator cho phép operation tương ứng.
3. **Được expose:** endpoint được công bố qua HTTP hoặc JMX.

Được expose không có nghĩa là đã được xác thực hoặc phân quyền. Spring Security vẫn cần kiểm soát ai được đọc và ai được gửi POST.

## 3. Giới hạn access của Actuator

Với Spring Boot hỗ trợ thuộc tính endpoint access, có thể chọn mặc định deny rồi bật lại đúng endpoint cần dùng:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: "health,info,bindings"
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    bindings:
      access: unrestricted
~~~

Ở đây:

- `management.endpoints.access.default: none` đóng access mặc định cho các endpoint.
- `health` và `info` chỉ được đọc.
- `bindings` cần access cho cả GET và POST vì endpoint này có thao tác điều khiển trạng thái.
- Danh sách `exposure.include` vẫn quyết định endpoint nào được công bố qua HTTP.

`unrestricted` ở đây là quyền operation của Actuator, không phải cho phép người dùng không xác thực. Hãy kết hợp với Spring Security và network policy. Nếu phiên bản Spring Boot của ứng dụng chưa hỗ trợ endpoint access properties, dùng cơ chế exposure và Spring Security phù hợp với phiên bản đó.

## 4. Tách cổng quản trị khỏi cổng API nghiệp vụ

Một cách giảm bề mặt truy cập là chạy management endpoint trên cổng riêng:

~~~yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,info,bindings"
~~~

Ví dụ này đưa Actuator sang cổng `9001`, còn API nghiệp vụ tiếp tục dùng cổng ứng dụng. Trong môi trường production, chỉ cho phép mạng quản trị, hệ thống giám sát hoặc workload vận hành được truy cập cổng này.

Có thể giới hạn địa chỉ bind bằng `management.server.address` nếu hạ tầng có interface quản trị riêng. Giá trị địa chỉ phải phù hợp với container, VM hoặc Kubernetes network; không sao chép `127.0.0.1` vào production nếu hệ thống quản trị cần truy cập từ máy khác.

Một cổng riêng không thay thế xác thực. Nếu firewall hoặc service mesh cấu hình sai, endpoint vẫn có thể bị truy cập. Hãy kết hợp:

- Private network hoặc management subnet.
- Firewall/security group/network policy chỉ cho phép nguồn quản trị.
- TLS cho kết nối quản trị.
- Authentication và authorization ở Spring Security.
- Audit cho mọi thao tác thay đổi trạng thái.

## 5. Điều khiển trạng thái binding qua HTTP

Spring Cloud Stream nhận JSON có field `state` tại endpoint của binding:

~~~bash
curl --request POST \
  --url https://stream-admin.internal:9001/actuator/bindings/processOrder-in-0 \
  --header "Authorization: Bearer <access-token>" \
  --header "Content-Type: application/json" \
  --data '{"state":"STOPPED"}'
~~~

Các trạng thái được tài liệu binding visualization/control mô tả:

| State | Ý nghĩa vận hành |
|---|---|
| `STOPPED` | Dừng binding |
| `STARTED` | Khởi động binding |
| `PAUSED` | Tạm dừng binding nếu binder hỗ trợ |
| `RESUMED` | Tiếp tục binding đã pause nếu binder hỗ trợ |

Có thể gửi `STARTED`, `PAUSED` hoặc `RESUMED` bằng cách thay giá trị trong JSON. `STOPPED` và `STARTED` là thao tác lifecycle; `PAUSED` và `RESUMED` phụ thuộc khả năng của binder và công nghệ bên dưới.

Tại Spring Cloud Stream 5.1, tài liệu hiện hành nêu Kafka và Solace hỗ trợ trạng thái `PAUSED`/`RESUMED`. Không giả định RabbitMQ hoặc Pulsar có cùng semantics chỉ vì endpoint nhận cùng JSON. Hãy kiểm tra binder version và log của ứng dụng trước khi đưa thao tác pause/resume vào runbook.

Việc dừng một input binding có thể làm consumer ngừng nhận message và backlog tăng. Dừng output binding có thể khiến đường phát message không còn sẵn sàng. Trước khi thao tác, cần xác định rõ binding name, hướng input/output, ảnh hưởng đến traffic và cách khôi phục.

## 6. Phân biệt binding state với trạng thái ứng dụng

Điều khiển một binding không đồng nghĩa với dừng toàn bộ Spring Boot application. Một ứng dụng có thể có nhiều input/output binding; dừng một binding chỉ tác động đến binding đó.

~~~text
Spring Cloud Stream application
          |
          +-- orders-in-0  ---> Kafka topic orders.events
          |
          +-- orders-out-0 ---> Kafka topic orders.processed
          |
          +-- audit-out-0  ---> RabbitMQ exchange audit.events
~~~

Nếu chỉ dừng `orders-in-0`, các binding khác có thể vẫn hoạt động. Tuy nhiên, các function phụ thuộc vào input đó sẽ không nhận dữ liệu mới từ binding đã dừng.

Thao tác lifecycle cũng không phải thay đổi cấu hình triển khai lâu dài. Khi ứng dụng khởi động lại, binding được tạo lại theo cấu hình và lifecycle policy của ứng dụng. Không dùng POST điều khiển binding như cách thay đổi vĩnh viễn `autoStartup`, destination, group hoặc binder trong cấu hình.

## 7. Phân quyền đọc và điều khiển

Nên chia quyền theo nhiệm vụ:

| Principal | Quyền |
|---|---|
| Monitoring service | Đọc health và metric cần thiết |
| Actuator viewer | Đọc thông tin Actuator được cho phép |
| Stream operator | Đọc binding và thực hiện thao tác pause/resume/stop/start theo quy trình |
| Application user | Gọi API nghiệp vụ; không tự động có quyền quản trị binding |

Một access token có scope `stream:read` có thể được dùng để đọc trạng thái. Scope `stream:control` chỉ cấp cho người hoặc workload được phép thay đổi trạng thái. Không dùng chung một token rộng quyền cho dashboard, ứng dụng nghiệp vụ và automation.

Nếu dùng role thay vì OAuth2 scope, giữ cùng nguyên tắc: quyền đọc và quyền điều khiển phải khác nhau. Không dựa vào việc endpoint có tên khó đoán hoặc nằm trên cổng khác để thay thế authorization.

## 8. Cấu hình Spring Security cho Actuator

Ví dụ dưới đây dùng Spring Boot 3.x Servlet stack và OAuth2 Resource Server với JWT bearer token. Scope được ánh xạ thành authority có tiền tố `SCOPE_`.

Binding POST yêu cầu `SCOPE_stream:control`; các request GET của binding yêu cầu `SCOPE_stream:read`; những Actuator endpoint khác yêu cầu `SCOPE_actuator:read`.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
@EnableMethodSecurity
class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        RequestMatcher bindingPost = new AndRequestMatcher(
                EndpointRequest.to("bindings"),
                request -> HttpMethod.POST.matches(request.getMethod()));

        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(bindingPost)
                            .hasAuthority("SCOPE_stream:control")
                        .requestMatchers(EndpointRequest.to("bindings"))
                            .hasAuthority("SCOPE_stream:read")
                        .anyRequest()
                            .hasAuthority("SCOPE_actuator:read"))
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Chỉ phù hợp với management API stateless dùng bearer token.
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Các điểm cần chú ý:

- `EndpointRequest.toAnyEndpoint()` giới hạn chain đầu tiên vào Actuator endpoint.
- Matcher POST của `bindings` được đặt trước matcher tổng quát của `bindings`.
- Quyền `stream:control` chỉ áp dụng cho request thay đổi trạng thái.
- Quyền `stream:read` cho phép GET binding.
- Chain thứ hai bảo vệ các route còn lại của ứng dụng.
- `@Order(1)` bảo đảm chain quản trị được xét trước chain ứng dụng.

Khi tự khai báo `SecurityFilterChain`, Spring Boot không còn áp dụng cấu hình bảo mật Actuator tự động như khi không có chain tùy chỉnh. Vì vậy, phải cấu hình đầy đủ cả Actuator lẫn API nghiệp vụ. Nếu ứng dụng đã có chain bảo mật riêng, hãy tích hợp các matcher vào thứ tự chain hiện tại thay vì tạo cấu hình xung đột.

Ví dụ trên dành cho bearer token không dựa vào cookie hoặc HTTP session. Vì chain Actuator là stateless và xác thực bằng `Authorization: Bearer`, CSRF được tắt trong riêng chain đó. Nếu endpoint được truy cập bằng browser session, cookie hoặc Basic authentication tự động từ trình duyệt, hãy giữ CSRF protection và gửi CSRF token hợp lệ cho POST. Không tắt CSRF toàn ứng dụng chỉ để làm cho lệnh curl hoạt động.

Import của `EndpointRequest` khác nhau giữa các thế hệ Spring Boot. Đoạn mã dùng package của Spring Boot 3.x; hãy kiểm tra API đúng với Spring Boot BOM mà ứng dụng đang sử dụng.

## 9. Chỉ cho phép binding name đã được phê duyệt

Ngay cả người vận hành có quyền cũng nên bị giới hạn vào danh sách binding được phép điều khiển. Một lỗi gõ tên có thể dừng nhầm luồng; một automation nhận binding name tùy ý có thể tác động ngoài phạm vi dự kiến.

Danh sách có thể được quản lý trong cấu hình:

~~~yaml
stream:
  operations:
    controllable-bindings:
      - processOrder-in-0
      - enrichOrder-in-0
~~~

Trước khi gửi lệnh:

1. Kiểm tra binding name có nằm trong allowlist.
2. Kiểm tra binding có tồn tại và đang ở trạng thái dự kiến.
3. Kiểm tra thao tác có hợp lệ với binder và hướng input/output.
4. Yêu cầu lý do vận hành hoặc incident ID.
5. Ghi lại người gọi, binding, state cũ, state mới và kết quả.

Không cho phép client gửi wildcard như `*` hoặc tự ghép tên binding từ dữ liệu không tin cậy. Với thao tác nhiều binding, thực hiện từng binding có kiểm soát và ghi nhận kết quả riêng; không giả định một POST có tính nguyên tử cho toàn bộ ứng dụng.

## 10. Điều khiển binding bằng API trong Java

Từ Spring Cloud Stream 3.1, ứng dụng có thể inject `BindingsLifecycleController` để truy vấn và thay đổi lifecycle của từng binding. API này hữu ích khi cần tích hợp thao tác vào một service quản trị nội bộ.

Ví dụ các thao tác:

~~~java
BindingsLifecycleController controller =
        applicationContext.getBean(BindingsLifecycleController.class);

var bindingState = controller.queryState("processOrder-in-0");

controller.stop("processOrder-in-0");
controller.start("processOrder-in-0");
controller.pause("processOrder-in-0");
controller.resume("processOrder-in-0");
~~~

Các thao tác pause/resume vẫn phụ thuộc binder hỗ trợ. `BindingsLifecycleController` là API trong cùng application context; Spring Security bảo vệ HTTP endpoint không tự động bảo vệ lời gọi Java trực tiếp.

Nếu bọc API này trong service quản trị, bật method security và kiểm tra quyền tại service:

~~~java
import java.util.Set;

import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class BindingOperations {

    private static final Set<String> ALLOWED_BINDINGS =
            Set.of("processOrder-in-0", "enrichOrder-in-0");

    private final BindingsLifecycleController lifecycle;

    BindingOperations(BindingsLifecycleController lifecycle) {
        this.lifecycle = lifecycle;
    }

    @PreAuthorize("hasAuthority('SCOPE_stream:control')")
    public void stop(String bindingName) {
        requireAllowed(bindingName);
        lifecycle.stop(bindingName);
    }

    @PreAuthorize("hasAuthority('SCOPE_stream:control')")
    public void start(String bindingName) {
        requireAllowed(bindingName);
        lifecycle.start(bindingName);
    }

    private void requireAllowed(String bindingName) {
        if (!ALLOWED_BINDINGS.contains(bindingName)) {
            throw new IllegalArgumentException(
                    "Binding is not approved for runtime control");
        }
    }
}
~~~

Để `@PreAuthorize` hoạt động, cần bật method security bằng `@EnableMethodSecurity` trong cấu hình. Nếu service được gọi qua một controller nội bộ, endpoint đó cũng phải được bảo vệ. Không công khai một controller wrapper mới mà quên áp dụng authentication, authorization và audit.

## 11. Ghi audit cho thao tác điều khiển

Thay đổi lifecycle binding là một hành động vận hành, không chỉ là một request HTTP thông thường. Mỗi lần thay đổi nên ghi được:

| Trường audit | Ví dụ |
|---|---|
| Thời điểm | Timestamp UTC |
| Principal | Subject hoặc service account |
| Hành động | `STOPPED`, `STARTED`, `PAUSED`, `RESUMED` |
| Binding | `processOrder-in-0` |
| Trạng thái trước | `RUNNING` |
| Trạng thái sau | `STOPPED` |
| Lý do | Incident hoặc change ticket |
| Request ID | Correlation ID |
| Kết quả | Thành công hoặc exception |

Không ghi bearer token, password, SASL JAAS string hoặc toàn bộ payload cấu hình binder vào audit log. Audit cần đủ thông tin để truy vết mà không sao chép bí mật sang một hệ thống log có phạm vi truy cập rộng hơn.

Có thể gửi sự kiện audit đến hệ thống quản trị tập trung hoặc lưu trong kho audit có retention và quyền đọc riêng. Nếu dùng `AuditEventRepository` của Spring Boot, cần xác định nơi lưu, thời hạn giữ và cách truy cập dữ liệu audit; việc có endpoint `auditevents` không tự tạo một kho audit bền vững.

## 12. Không để lộ credential qua GET bindings

Binding endpoint có thể hiển thị extended properties của binder. Một số cấu hình Kafka chứa `sasl.jaas.config`; cấu hình TLS cũng có thể có đường dẫn hoặc password của keystore/truststore. Vì vậy, quyền GET cũng là quyền nhạy cảm.

Spring Cloud Stream hướng dẫn cung cấp `SanitizingFunction` để che các giá trị như `sasl.jaas.config`. Ví dụ:

~~~java
import java.util.Locale;
import java.util.Set;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ActuatorDataSanitization {

    private static final Set<String> SENSITIVE_KEYS = Set.of(
            "sasl.jaas.config",
            "ssl.keystore.password",
            "ssl.truststore.password",
            "ssl.key.password");

    @Bean
    SanitizingFunction bindingSecretsSanitizer() {
        return data -> {
            String key = data.getKey().toLowerCase(Locale.ROOT);
            return SENSITIVE_KEYS.contains(key)
                    ? data.withValue("******")
                    : data;
        };
    }
}
~~~

**Không giả định `SanitizingFunction` chắc chắn được áp dụng cho mọi phiên bản của `/actuator/bindings`.** Đã có báo cáo về phiên bản Spring Boot 3.2.4 và Spring Cloud 2023.0.1 trong đó `sasl.jaas.config` xuất hiện trong response và function sanitization không được gọi bởi binding endpoint. Tài liệu Spring Cloud Stream có ví dụ cấu hình sanitizer, nhưng hành vi thực tế cần được xác minh với đúng phiên bản và payload của ứng dụng.

Vì vậy:

- Không expose `bindings` công khai chỉ vì đã khai báo `SanitizingFunction`.
- Dùng secret manager hoặc environment injection để quản lý credential, không hard-code trong source.
- Kiểm tra response GET thật trong integration test để xác nhận từng khóa nhạy cảm đã được che.
- Nếu endpoint vẫn trả dữ liệu bí mật, không cấp quyền GET rộng; cân nhắc endpoint quản trị tùy chỉnh chỉ trả trường cần thiết hoặc loại bỏ dữ liệu nhạy cảm khỏi response theo cách phù hợp với phiên bản.
- Không đưa response đầy đủ của `/actuator/bindings` vào log hoặc ticket công khai.

## 13. Bảo vệ management endpoint ở tầng mạng

Spring Security là lớp bảo vệ ứng dụng; network policy giảm số nguồn có thể chạm đến endpoint:

~~~text
Operator / Monitoring
        |
        v
Private management network
        |
        v
Firewall / Network Policy
        |
        v
Management port 9001
        |
        v
Spring Security
        |
        v
/actuator/bindings
~~~

Trong Kubernetes, có thể dùng NetworkPolicy chỉ cho phép namespace hoặc service account của hệ thống vận hành truy cập cổng quản trị. Trên VM hoặc cloud network, dùng security group/firewall tương ứng. Nếu management endpoint nằm sau ingress hoặc gateway, cấu hình gateway không được bỏ qua authentication của ứng dụng.

CORS không thay thế authorization. Việc chỉ cho phép một origin trình duyệt không ngăn được curl, service khác hoặc client không phải browser. Tương tự, một URL khó đoán hoặc cổng không phổ biến không phải cơ chế xác thực.

## 14. Kiểm thử authorization với MockMvc

Kiểm thử cần xác nhận cả quyền đọc và quyền thay đổi trạng thái. Ví dụ sau giả định Actuator chain dùng JWT bearer và CSRF chỉ tắt trong chain stateless quản trị:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BindingActuatorSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerCanInspectBindings() throws Exception {
        mockMvc.perform(get("/actuator/bindings")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_stream:read"))))
                .andExpect(status().isOk());
    }

    @Test
    void readerCannotStopBinding() throws Exception {
        mockMvc.perform(post("/actuator/bindings/processOrder-in-0")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_stream:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"state\":\"STOPPED\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operatorCanRequestBindingControl() throws Exception {
        mockMvc.perform(post("/actuator/bindings/processOrder-in-0")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_stream:control")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"state\":\"STOPPED\"}"))
                .andExpect(status().isOk());
    }
}
~~~

Test cuối cần có binding `processOrder-in-0` thật trong test context và binder phù hợp. Nếu binding không tồn tại, kết quả có thể là lỗi khác với authorization; vì vậy cần tạo binding test rõ ràng trước khi đánh giá status code.

Ngoài ba test trên, hãy kiểm tra:

- Request không có token bị từ chối.
- Token có scope `stream:read` không thể POST.
- Token có scope `stream:control` chỉ điều khiển binding trong allowlist.
- POST với state không hợp lệ bị từ chối.
- Binding name không tồn tại không làm thay đổi binding khác.
- Response GET không chứa credential.
- Endpoint vẫn không truy cập được từ mạng ngoài management network.

Nếu dùng browser session, thêm test POST thiếu CSRF token phải bị từ chối và POST có CSRF token hợp lệ mới được xử lý.

## 15. Quy trình vận hành an toàn khi dừng binding

Trước khi dừng binding:

1. Xác nhận binding name và destination từ GET có quyền.
2. Kiểm tra consumer group, partition assignment hoặc queue/subscription liên quan.
3. Xác nhận tác động đến backlog, SLA và các function phụ thuộc.
4. Ghi incident/change ID và lý do.
5. Thực hiện thao tác bằng token có scope điều khiển.
6. Đọc lại trạng thái để xác nhận binding đã đổi.
7. Theo dõi backlog và lỗi xử lý sau khi dừng.
8. Khởi động hoặc resume theo runbook đã duyệt.
9. Xác nhận consumer tiếp tục nhận message và backlog giảm.
10. Đóng incident sau khi xác nhận kết quả nghiệp vụ.

Không dừng hàng loạt binding chỉ dựa trên một pattern tên. Khi cần bảo trì toàn bộ consumer group, phải xác định rõ thứ tự dừng, cách xử lý message đang in-flight và cách khởi động lại để tránh tạo tải đột biến lên broker.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/actuator/bindings` trả 404 | Chưa thêm Actuator/web hoặc chưa expose `bindings` | Kiểm tra dependency và `management.endpoints.web.exposure.include` |
| GET hoạt động nhưng POST trả 403 | Thiếu quyền control hoặc CSRF token | Kiểm tra scope/role và CSRF policy của management chain |
| Có Spring Security nhưng Actuator không được bảo vệ như mong đợi | Custom `SecurityFilterChain` làm Boot auto-security back off | Tạo chain riêng cho Actuator và chain cho API còn lại |
| `PAUSED` không có tác dụng | Binder hoặc công nghệ không hỗ trợ pause/resume | Kiểm tra binder version và dùng lifecycle operation được hỗ trợ |
| Binding dừng nhưng backlog tăng | Consumer không nhận message trong thời gian dừng | Theo dõi lag/queue depth và có kế hoạch resume |
| GET bindings để lộ cấu hình nhạy cảm | Response chứa extended binder properties chưa được sanitize | Giới hạn quyền GET, kiểm thử response và che dữ liệu theo version |
| Operator điều khiển nhầm binding | Không có allowlist hoặc kiểm tra tên | Áp dụng allowlist và xác nhận destination trước khi thay đổi |
| API nghiệp vụ vô tình bị mở | Custom security chain chỉ xử lý Actuator, thiếu chain còn lại | Bổ sung chain bảo vệ toàn bộ request không phải Actuator |
| Audit thiếu thông tin | Chỉ ghi HTTP status hoặc log chung | Ghi principal, binding, state cũ/mới, lý do và request ID |

## 17. Checklist trước khi production

- Chỉ expose `health`, `info` và endpoint thực sự cần thiết.
- Không dùng wildcard exposure nếu không có lý do và kiểm soát chặt.
- Cấu hình access Actuator rõ ràng; chỉ mở `bindings` cho thao tác cần dùng.
- Dùng management port/private network và firewall/network policy.
- Bảo vệ Actuator bằng authentication và authorization.
- Tách quyền đọc binding khỏi quyền POST điều khiển.
- Chỉ cấp scope điều khiển cho operator hoặc automation được duyệt.
- Giữ CSRF nếu dùng browser session/cookie; chỉ tắt trong chain stateless bearer phù hợp.
- Bảo vệ các route ứng dụng còn lại khi có custom `SecurityFilterChain`.
- Giới hạn binding name bằng allowlist.
- Kiểm tra binder hỗ trợ `STOPPED`, `STARTED`, `PAUSED`, `RESUMED` như thế nào.
- Kiểm tra response bindings không chứa credential hoặc secret.
- Không mặc định `SanitizingFunction` đã che dữ liệu trên binding endpoint.
- Ghi audit cho mọi thao tác thay đổi trạng thái.
- Có runbook dừng, khởi động lại và theo dõi backlog.
- Có test 401, 403, quyền operator, binding không hợp lệ và secret leakage.

Actuator giúp quan sát binding và điều khiển vòng đời message flow, nhưng endpoint `bindings` có thể tiết lộ cấu hình broker và nhận lệnh làm thay đổi hoạt động consumer/producer. Hãy chỉ expose endpoint cần thiết, đặt nó trong management network, xác thực mọi request, tách quyền đọc khỏi quyền điều khiển, giới hạn binding được phép và audit từng thao tác. Đặc biệt, kiểm thử response thực tế để chắc chắn credential không bị lộ; không coi việc khai báo sanitizer là bằng chứng endpoint đã che mọi dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Boot 3.5 — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot — SanitizingFunction API](https://docs.spring.io/spring-boot/docs/3.0.x/api/org/springframework/boot/actuate/endpoint/SanitizingFunction.html)
- [Spring Cloud Stream issue #2932 — Binding endpoint and sensitive data sanitization](https://github.com/spring-cloud/spring-cloud-stream/issues/2932)
