# Tránh expose endpoint nhạy cảm trong production — Spring Boot và JMX

## 1. Mục tiêu bài học

Spring Boot giúp triển khai tính năng giám sát và quản trị thông qua Spring Framework JMX, Spring Boot Actuator và các giao thức như HTTP hoặc JMX. Tính tiện dụng này có một rủi ro đáng kể: **một endpoint hoặc MBean được expose quá rộng có thể tiết lộ thông tin vận hành, cấu hình hoặc cho phép người không có thẩm quyền thay đổi trạng thái ứng dụng**.

Ví dụ các hành động cần được kiểm soát:

- Đọc biến môi trường, system properties hoặc một phần cấu hình.
- Xem beans, mappings, thread dumps và heap dumps.
- Gọi operations thay đổi log level, xóa cache, đóng kết nối hoặc restart worker.
- Truy cập endpoint Actuator có khả năng thay đổi trạng thái, nếu ứng dụng có extension hoặc tích hợp tương ứng.
- Truy vấn các MBean do Spring tự export hoặc do thư viện thứ ba đăng ký.

Bài này hướng dẫn thiết kế bề mặt quản trị theo **nguyên tắc tối thiểu hóa quyền truy cập**, tách biệt môi trường, bảo vệ connector, kiểm tra những gì đã thực sự được expose và kiểm thử trước khi phát hành.

Sau bài học, bạn có thể:

1. Phân biệt exposure qua HTTP Actuator, JMX Actuator và Spring-managed MBeans.
2. Biết các lớp cấu hình điều khiển endpoint có tồn tại, có được expose và có thể truy cập hay không.
3. Lập danh sách endpoint cần được hạn chế ở production.
4. Áp dụng cấu hình giới hạn exposure, bảo mật mạng và xác thực/ủy quyền.
5. Hiểu vì sao việc ẩn đường dẫn hoặc đổi ObjectName không phải bảo mật.
6. Kiểm thử surface thực tế thay vì chỉ tin vào file cấu hình.
7. Xây dựng quy trình thay đổi an toàn khi mở thêm endpoint quản trị.

## 2. Ba bề mặt quản trị cần phân biệt

\`\`\`text
                         Spring Boot application
                                  |
              +-------------------+---------------------+
              |                   |                     |
              v                   v                     v
     Actuator over HTTP   Actuator over JMX     Spring/custom MBeans
              |                   |                     |
      HTTP management       MBeanServer             MBeanExporter
         endpoint                 ^                     |
              |                  |                     v
      Web server/router          +------------- MBeanServer
              |                                        |
       HTTP client                         Local / remote JMX client
\`\`\`

**HTTP và JMX là hai bề mặt truy cập khác nhau.** Cấu hình chỉ giới hạn HTTP exposure chưa chắc giới hạn JMX exposure. Bên cạnh Actuator endpoints, ứng dụng hoặc thư viện vẫn có thể đăng ký MBean trực tiếp.

| Bề mặt | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Actuator HTTP | \`/actuator/health\`, \`/actuator/info\` | endpoint được enable, web exposure, HTTP authorization, network |
| Actuator JMX | Actuator endpoint được xuất thành JMX MBean | JMX exposure, MBeanServer, JMX connector và quyền |
| Spring JMX custom | \`@ManagedResource\`, \`@ManagedOperation\` | exporter/assembler, ObjectName, operation, connector |
| JVM platform MBeans | \`java.lang:type=Memory\`, \`java.lang:type=Threading\` | remote JMX access, principal/role, JVM settings |
| Third-party MBeans | Connection pool, message broker, cache | thư viện đăng ký gì, operation nhạy cảm nào |

Một ứng dụng có thể không expose \`/actuator/env\` qua HTTP nhưng vẫn để lộ một attribute cấu hình nhạy cảm qua custom MBean. Vì thế security review phải nhìn toàn bộ **management surface**, không chỉ một nhóm URL.

## 3. “Enable”, “Expose”, “Accessible” và “Authorized” không đồng nghĩa

Cần tách bốn câu hỏi:

1. **Endpoint được tạo/kích hoạt không?** Có bean và chức năng quản trị tương ứng không?
2. **Endpoint được expose qua công nghệ nào?** HTTP, JMX hoặc custom connector?
3. **Client có kết nối tới bề mặt đó không?** Network, routing, port, connector?
4. **Client có được phép xem/gọi chức năng không?** Authentication, authorization, role, policy?

\`\`\`text
Endpoint implemented
       |
       v
Enabled?
       |
       v
Exposed over HTTP/JMX?
       |
       v
Reachable from client?
       |
       v
Authenticated?
       |
       v
Authorized for requested action?
\`\`\`

Một endpoint không xuất hiện trên HTTP không đồng nghĩa nội dung quản trị của nó không có ở một giao diện khác. Một endpoint reachable cũng không có nghĩa nó được phép cho mọi người gọi.

### 3.1. Tối thiểu hóa exposure trước, rồi mới đặt security

Cách an toàn là **không expose những chức năng không cần thiết**, thay vì expose hết rồi hy vọng filter/security cấu hình luôn đúng. Authentication và authorization là lớp phòng vệ bổ sung, không phải lý do để mở tất cả endpoints.

### 3.2. Không coi “chỉ dùng nội bộ” là đủ

Một endpoint trên mạng private vẫn có rủi ro từ lateral movement, cấu hình proxy sai, container network, VPN và tài khoản bị lộ. Endpoint quản trị nhạy cảm cần nhiều lớp: network segmentation, identity, authorization, TLS, logging và giới hạn thao tác.

## 4. Cấu hình exposure trong Spring Boot Actuator

Các property Spring Boot thường được dùng để điều khiển endpoints:

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
\`\`\`

Ý nghĩa:

- \`management.endpoints.web.exposure.include\`: chọn endpoints được expose qua web.
- \`management.endpoints.jmx.exposure.include\`: chọn endpoints được expose qua JMX.
- Danh sách cụ thể tùy phiên bản Spring Boot, endpoints có sẵn và trạng thái enable.
- Đây là **một ví dụ policy** hạn chế surface; không phải bảo đảm tuyệt đối rằng toàn bộ custom MBeans và JMX connectors đã được vô hiệu hóa.

Nếu ứng dụng không có nhu cầu JMX Actuator, có thể cấu hình:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
\`\`\`

Tùy yêu cầu, còn có thể xem xét cấu hình enable/disable JMX của Spring Boot để giảm MBean exporter và hạ tầng tương ứng. Phải kiểm tra phiên bản Boot đang sử dụng và tác động đến các công cụ monitoring khác, tránh vô tình làm mất telemetry đang cần.

### 4.1. Vì sao không chọn \`include: "*"\` ở production?

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
\`\`\`

Cấu hình này làm tăng surface theo những endpoints được enable và có thể khiến một endpoint mới xuất hiện sau nâng cấp hoặc thêm dependency. Nếu app dùng cấu hình exposure rộng, nên có đánh giá security rõ, quy tắc authorization đầy đủ và kiểm thử tự động trên danh sách endpoints thực tế.

Một **allowlist có chủ đích** dễ review hơn wildcard.

### 4.2. \`exclude\` không thay thế kiểm thử thực tế

Cấu hình:

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,beans
\`\`\`

chỉ điều khiển exposure theo phạm vi và phiên bản tương ứng; không loại bỏ các đường truy cập khác đến cùng thông tin, như custom controllers hoặc MBeans. Danh sách exclude dễ bị quên khi có endpoint mới. Với production, thường nên định nghĩa explicit allowlist và kiểm tra route/MBean đã thực sự được đăng ký.

## 5. Những endpoint cần đánh giá chặt chẽ

| Endpoint hoặc nhóm tính năng | Rủi ro tiềm ẩn | Gợi ý production |
|---|---|---|
| \`health\` | Lộ chi tiết dependencies, trạng thái hạ tầng | Chỉ expose nội dung phù hợp và phân quyền phần detail |
| \`info\` | Lộ build/version/host/metadata | Giảm dữ liệu không cần thiết |
| \`env\` | Cấu hình và thông tin môi trường | Không expose rộng; kiểm soát dữ liệu và role |
| \`configprops\` | Cấu hình đã bind | Hạn chế truy cập, kiểm tra sanitization |
| \`beans\` | Cấu trúc ứng dụng nội bộ | Chỉ dùng nơi quản trị được bảo vệ |
| \`mappings\` | Route/API topology | Hạn chế disclosure |
| \`threaddump\` | Tên thread, stack traces và logic nội bộ | Chỉ quyền vận hành được cấp phép |
| \`heapdump\` | Heap chứa dữ liệu ứng dụng, có thể rất nhạy cảm | Không expose công khai; lưu trữ và xử lý an toàn |
| \`loggers\` | Thông tin cấu hình logging, có thể cho thay đổi mức log | Read/write authorization tách biệt |
| \`shutdown\` nếu được enable | Dừng ứng dụng | Không bật tùy tiện; hạn chế nghiêm ngặt |
| Custom endpoints/operations | Phụ thuộc nghiệp vụ; có thể có side effect mạnh | Phân loại và bảo vệ theo tác động |

**Lưu ý phiên bản:** danh sách endpoints và availability thay đổi theo phiên bản Spring Boot, dependencies và cấu hình. Một endpoint không tồn tại mặc định trong dự án của bạn không có nghĩa mọi dự án Boot khác đều như vậy. Không suy ra bảo mật chỉ từ tên endpoint.

## 6. Kiểm soát HTTP management surface

### 6.1. Tách management port khi phù hợp

Ví dụ:

\`\`\`yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
\`\`\`

Đây là ví dụ cho môi trường local hoặc triển khai có sidecar/tunnel phù hợp. \`127.0.0.1\` khiến management listener bị giới hạn loopback trong network namespace tương ứng; nếu liveness probes từ hệ thống orchestration chạy qua địa chỉ khác, cần thiết kế mạng cho đúng thay vì áp dụng nguyên xi.

Tách port làm policy mạng rõ hơn, nhưng **không tự tạo xác thực hoặc authorization**. Khi management port được publish bởi container/orchestrator hoặc reverse proxy, cần kiểm tra đường truy cập thực tế.

### 6.2. Dùng authorization ở tầng HTTP

Ví dụ Spring Security minh họa:

\`\`\`java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(basic -> {});
        return http.build();
    }
}
\`\`\`

Đây là ví dụ policy logic: health có thể công khai ở mức phù hợp, endpoints khác đòi hỏi vai trò vận hành. Trong production cần cấu hình authentication provider thực, TLS, security filter chains còn lại, CSRF khi có thao tác trạng thái và policy cụ thể cho các đường quản trị. Với Spring Boot/Spring Security phiên bản khác, cần kiểm tra API tương ứng.

Khi ứng dụng tự khai báo \`SecurityFilterChain\`, đừng giả định Boot vẫn tự áp dụng default security policy cho tất cả endpoints. Phải kiểm tra quy tắc matcher và thứ tự filter chains.

### 6.3. Health details cũng là dữ liệu

Một phản hồi health có thể tiết lộ database, message broker, disk và dependency statuses. Có thể giới hạn detail theo authorization:

\`\`\`yaml
management:
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS
\`\`\`

Thiết lập được hỗ trợ và cách roles được kiểm tra tùy version; hãy thử bằng cả principal thường lẫn principal có quyền OPS. Liveness/readiness probes có thể cần path riêng hoặc cơ chế truy cập hạn chế mà không yêu cầu quyền admin đầy đủ.

## 7. JMX Actuator không đồng nghĩa JMX remote connector

Spring Boot có thể expose MBeans trong platform MBeanServer khi JMX được bật. Nhưng từ đó **không suy ra** remote JMX đã được bật. Remote clients cần JMX management agent hoặc connector server.

\`\`\`text
Spring Boot Actuator JMX endpoint
               |
               v
          MBeanServer
               |
       +-------+---------+
       |                 |
  Local JMX          Remote connector
  access             (nếu được mở)
                        |
                   Auth/TLS/network
\`\`\`

Vì vậy security review cần tách:

- Endpoint/MBean nào được đăng ký vào server?
- Remote connector có hoạt động không?
- Connector gắn với server nào?
- Ai có thể kết nối tới endpoint?
- Ai có thể gọi read/write/operations?

Chỉ đổi \`management.endpoints.jmx.exposure.*\` không thay việc bảo mật các MBeans mà application/library tự đăng ký.

## 8. Remote JMX: bảo vệ management agent và RMI

Một số JDK/JVM cho phép bật remote JMX bằng các system properties như:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.internal.example
\`\`\`

Đây **không phải cấu hình production hoàn chỉnh**. Các cổng và host minh họa chỉ nên truy cập trong mạng quản trị được kiểm soát. Khi bật remote JMX, phải xem xét xác thực, TLS, truststore, password/access files, firewall và các đặc tính RMI (registry port, server port, hostname trong stub).

Một policy vận hành nên yêu cầu:

1. Không public management ports ra Internet.
2. Chỉ allowlist nguồn quản trị hoặc kết nối qua tunnel được cấp quyền.
3. Sử dụng TLS và xác thực phù hợp theo JDK/connector.
4. Bảo vệ secrets và file chứa credential bằng filesystem permissions.
5. Phân quyền thao tác theo role; không cho mọi operator quyền gọi operation phá hủy.
6. Theo dõi connections, authentication failures và thay đổi cấu hình.
7. Đóng connector khi không còn nhu cầu.

Không sử dụng:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

như một giải pháp mặc định để “dễ kết nối” ở production. Nếu tài liệu lab minh họa cấu hình không bảo vệ, phải cô lập hoàn toàn môi trường và không copy nguyên xi sang hệ thống thật.

## 9. Custom @ManagedResource và @ManagedOperation: nguồn rủi ro bị bỏ sót

Một ứng dụng có thể tự export bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Primary")
public class MaintenanceControl {

    @ManagedAttribute
    public int getPendingJobs() {
        return 42;
    }

    @ManagedOperation
    public void restartWorker() {
        // Side effect: restart worker.
    }
}
\`\`\`

Nếu exporter đăng ký class này, JMX client có quyền tương ứng có thể tìm và gọi \`restartWorker\`. Việc custom bean không phải Actuator endpoint **không làm nó an toàn hơn**.

Cần phân loại:

| Member | Ý nghĩa | Chính sách đề xuất |
|---|---|---|
| \`getPendingJobs\` | Read-only số liệu | Có thể expose trong domain phù hợp |
| \`getSystemConfiguration\` | Có thể tiết lộ secrets | Không export trực tiếp raw config |
| \`setEnabled(boolean)\` | Thay đổi trạng thái | Phân quyền ghi và audit |
| \`restartWorker()\` | Có side effect lớn | Giới hạn đặc biệt, xem xét API khác |
| \`clearAllData()\` | Phá hủy dữ liệu | Tránh expose JMX nếu không có yêu cầu quản trị được kiểm soát |

**Không nhầm metadata với authorization:** \`@ManagedOperation\` công bố một method; annotation này không tự kiểm tra operator có đủ quyền hay không.

### 9.1. Không dựa vào tên khó đoán

Đổi ObjectName từ \`Maintenance\` thành \`XzQ42\` không phải bảo mật. Một JMX client có quyền query có thể dùng \`queryNames("*:*")\` để phát hiện MBeans. Cần bảo vệ quyền kết nối và quyền thực thi, đồng thời hạn chế export những methods không cần thiết.

## 10. Giảm thông tin nhạy cảm trong attributes

Một getter có thể vô tình expose dữ liệu:

\`\`\`java
@ManagedAttribute
public String getJdbcUrl() {
    return jdbcUrl;
}
\`\`\`

Ngay cả khi URL không chứa password, nó vẫn có thể tiết lộ topology và tên hạ tầng. Tệ hơn:

\`\`\`java
@ManagedAttribute
public String getApiToken() {
    return apiToken;
}
\`\`\`

không nên được công bố qua JMX. Người thiết kế cần chọn **safe summaries**, không trả raw configuration.

Ví dụ tốt hơn:

\`\`\`java
@ManagedAttribute
public boolean isExternalServiceConfigured() {
    return credentialsPresent;
}

@ManagedAttribute
public String getExternalServiceStatus() {
    return lastCheckStatus; // e.g. "UP", "DOWN", "UNKNOWN"
}
\`\`\`

Tránh trả tên người dùng, access token, full connection string, certificate private material, thông tin thanh toán hoặc stack traces chứa dữ liệu cá nhân. Nếu buộc cần diagnostics sâu, sử dụng quy trình truy cập tạm thời, có audit và thời hạn lưu trữ phù hợp.

## 11. Sanitization và giới hạn của nó

Spring Boot Actuator có những cơ chế xử lý/sanitization dữ liệu nhạy cảm cho một số endpoints. Tuy nhiên:

- Không giả định mọi custom endpoint đều được sanitization.
- Không giả định mọi MBean attribute đều đi qua cùng policy với \`/actuator/env\`.
- Giá trị được che trên UI có thể vẫn xuất hiện ở endpoint khác hoặc log.
- Sanitization có thể thay đổi theo phiên bản và extension.
- Dữ liệu nhạy cảm không nên được đưa vào response từ đầu nếu không cần.

Hãy test cụ thể bằng secret giả (canary) để xác định client với quyền thấp không thể nhận được raw value qua HTTP, JMX hoặc custom surface.

## 12. Tách cấu hình local, test và production

Một cấu hình phù hợp cho local development có thể không được chấp nhận ở production.

### 12.1. Local development

\`\`\`yaml
# application-local.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
    jmx:
      exposure:
        include: health,info
\`\`\`

Dù là local, không nên mở interface ngoài máy khi không cần, vì laptop có thể kết nối mạng công cộng hoặc VPN.

### 12.2. Production

\`\`\`yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when_authorized
\`\`\`

Cấu hình này chỉ minh họa allowlist. Tùy hạ tầng, monitoring có thể yêu cầu metrics hoặc Prometheus endpoint; nếu có, cần bảo vệ bằng mạng và xác thực phù hợp. Không có một danh sách endpoints đúng cho mọi hệ thống.

### 12.3. Production configuration phải được kiểm chứng sau khi merge

Spring Boot nhận cấu hình từ nhiều sources: files, profiles, environment variables, command-line arguments và external config. Một file \`application-prod.yml\` có thể bị override bởi biến môi trường hoặc deploy manifest.

Ví dụ \`MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=*\` (tùy binding và môi trường) có thể mở rộng exposure so với YAML. Vì vậy chỉ xem source repository không đủ; cần xác nhận **effective configuration** và endpoint thực tế sau deployment.

## 13. Phân quyền theo hành động thay vì một role admin chung

Có thể phân cấp:

| Vai trò | Quyền gợi ý |
|---|---|
| Health probe | Chỉ xem trạng thái sức khỏe tối thiểu |
| Monitoring reader | Đọc metrics và safe attributes |
| Operator | Truy cập diagnostics theo nhu cầu đã duyệt |
| Administrator | Gọi operations thay đổi trạng thái trong workflow kiểm soát |

Một số JMX connector mặc định có cơ chế quyền \`readonly\`/\`readwrite\`, nhưng điều đó không tương đương phân quyền chi tiết cho từng business operation. Nếu cần authorization theo operation, có thể phải triển khai cơ chế riêng phù hợp connector, MBeanServer hoặc management service.

Không nên expose destructive MBean operation chỉ vì toàn bộ role \`OPS\` được đọc metrics. Hãy thiết kế quyền đọc và quyền thay đổi trạng thái tách biệt.

## 14. Audit và khả năng truy vết

Các thao tác quản trị nhạy cảm cần lưu đủ dấu vết:

- Ai thực hiện (principal hoặc service identity)?
- Operation nào, trên ObjectName/endpoint nào?
- Thời điểm, correlation/request ID?
- Kết quả thành công, thất bại hay không chắc chắn?
- Có yêu cầu phê duyệt hoặc break-glass không?
- Giá trị bị thay đổi thuộc phạm vi nào, không ghi secret thô?

Với JMX/RMI, không mặc định tất cả \`MBeanServer.invoke\` đều được log đầy đủ. Phải kiểm tra các lớp audit ở connector, authorization middleware và business operation. Một Spring aspect có thể hỗ trợ audit cho managed bean nếu lời gọi đi đúng proxy, nhưng không nên chỉ dựa vào AOP nếu exporter có đường gọi bỏ qua proxy.

## 15. Kiểm tra bề mặt HTTP và JMX thực tế

### 15.1. HTTP

Trong môi trường được cấp quyền, kiểm tra những endpoint thực sự accessible qua management host/port với nhiều loại principal:

\`\`\`bash
curl -i https://management.internal.example/actuator/health
curl -i https://management.internal.example/actuator/info
\`\`\`

Với \`env\`, \`beans\`, \`configprops\` và những endpoints nhạy cảm, không lấy raw response để đưa lên log công khai. Test có thể chỉ assert HTTP status hoặc schema an toàn, tùy policy.

### 15.2. JMX

Trong JVM test hoặc từ JMX client được phép:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    connection.queryNames(
        new ObjectName("com.example:*"), null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Trong ví dụ này, \`ManagementFactory.getPlatformMBeanServer()\` trả local server của chính JVM. Để kiểm tra một process khác, cần JMX connector tương ứng. Query chỉ cho biết **MBeans nào được đăng ký trên server đích**, không tự kiểm tra network exposure hay quyền của remote principal.

### 15.3. Kiểm tra MBeanInfo và operations

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Dựa vào danh sách này để review các actions có side effect. Một operation có tên vô hại vẫn có thể thay đổi trạng thái; phải hiểu implementation hoặc hợp đồng nghiệp vụ.

## 16. Kiểm thử bảo mật trước khi phát hành

Một bộ kiểm thử có thể gồm:

1. **Allowlist HTTP:** chỉ endpoints được phê duyệt truy cập được.
2. **Authentication:** request không có identity bị từ chối khi phải xác thực.
3. **Authorization:** principal chỉ có quyền đọc không thể gọi endpoint thay đổi trạng thái.
4. **Health details:** response public không tiết lộ dependency topology.
5. **Sensitive data canary:** secret giả không xuất hiện trong responses dành cho quyền thấp.
6. **JMX ObjectNames:** danh sách MBeans được đăng ký đúng với tài liệu quản trị.
7. **JMX operations:** destructive operations không được expose hoặc được bảo vệ phù hợp.
8. **Remote network:** management ports không reachable từ mạng không được phép.
9. **Configuration override:** môi trường production không bị wildcard exposure từ environment/deploy.
10. **Upgrade regression:** sau nâng cấp Boot/JDK/dependency, surface không bất ngờ mở rộng.

### 16.1. Ví dụ test HTTP đơn giản

Với Spring Boot Test và test setup có web server:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class ActuatorExposureTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void sensitiveEndpointIsNotPubliclyAccessible() {
        var response = http.getForEntity(
            "/actuator/env", String.class);

        assertThat(response.getStatusCode().value())
            .isIn(401, 403, 404);
    }
}
\`\`\`

Đây là một **ví dụ kiểm tra truy cập không xác thực**, không phải kết luận tổng quát về bảo mật. Một endpoint có thể trả \`404\` do chưa expose, hoặc \`401/403\` do policy. Cần test thêm với principal được xác thực và đối chiếu mục tiêu authorization cụ thể.

### 16.2. Test không chỉ nhìn status

Một endpoint nhạy cảm có thể trả \`200\` cho người có quyền, nhưng response vẫn cần được kiểm tra không chứa secret. Ngược lại, \`401\` ở HTTP không chứng minh JMX endpoint tương ứng an toàn. Các test phải bao phủ đúng bề mặt.

## 17. Những lỗi cấu hình phổ biến

| Sai lầm | Rủi ro | Giải pháp |
|---|---|---|
| \`include: "*"\` trên production | Endpoint mới được expose ngoài dự kiến | Dùng allowlist |
| Chỉ bảo vệ HTTP nhưng mở remote JMX | Lộ MBean operations qua connector | Bảo vệ/giới hạn JMX riêng |
| Dựa vào mạng nội bộ là đủ | Lateral movement và credential misuse | Defense in depth |
| MBean getter trả raw config | Rò rỉ secret và topology | Trả safe summary |
| \`@ManagedOperation\` trên method phá hủy | Người có quyền JMX gọi được action | Giảm exposure, authorization/audit |
| Chỉ dùng tên khó đoán | Query JMX vẫn tìm thấy ObjectName | Kiểm soát quyền thực |
| Tin vào YAML nhưng bỏ qua env override | Production mở endpoint do deploy setting | Kiểm tra effective config |
| Tắt xác thực/TLS để debug | Mở kênh quản trị không bảo vệ | Dùng lab cô lập hoặc tunnel an toàn |
| Export nhiều beans bằng autodetection quá rộng | Surface lớn không chủ đích | Explicitly restrict managed interface |
| Dùng admin role cho monitoring reader | Quyền ghi vượt nhu cầu | Tách read/write/admin |

## 18. Checklist triển khai production

### Trước khi deploy

- [ ] Liệt kê HTTP Actuator endpoints được phép.
- [ ] Liệt kê JMX Actuator endpoints và custom MBeans.
- [ ] Xác nhận không có wildcard exposure ngoài chủ đích.
- [ ] Kiểm tra management port/address và Kubernetes Service/Ingress.
- [ ] Đảm bảo remote JMX chỉ reachable qua mạng quản trị được phép.
- [ ] Xác nhận TLS, authentication, authorization và secrets handling.
- [ ] Review các MBean operations có side effect.
- [ ] Kiểm tra dữ liệu nhạy cảm không bị trả qua attributes/HTTP.
- [ ] Thiết lập audit và alert cho truy cập quản trị bất thường.
- [ ] Có integration tests cho exposure và quyền truy cập.

### Sau khi deploy

- [ ] Kiểm tra chính xác effective routes và JMX registrations.
- [ ] Thử từ một mạng/principal không được phép.
- [ ] Xác nhận monitoring được phép vẫn hoạt động.
- [ ] Đối chiếu logs/audit với yêu cầu tuân thủ.
- [ ] Ghi nhận sự khác biệt so với inventory đã phê duyệt.

**Nguyên tắc:** cấu hình tốt là điều cần, nhưng **kiểm tra bằng hành vi thực tế** mới chứng minh policy đang được áp dụng.

## 19. Bài tập thực hành

### Bài tập A — HTTP allowlist

Tạo Spring Boot Actuator app và cấu hình \`management.endpoints.web.exposure.include=health,info\`. Kiểm tra \`/actuator/health\`, \`/actuator/info\`, \`/actuator/env\` bằng test client không xác thực. Giải thích khác biệt giữa endpoint không expose và endpoint yêu cầu xác thực.

### Bài tập B — JMX inventory

Bật JMX trong lab, dùng JConsole hoặc API \`queryNames\` liệt kê Actuator MBeans và custom MBeans. Phân loại attributes chỉ đọc, setters và operations có side effect. Đề xuất allowlist phù hợp cho production.

### Bài tập C — So sánh HTTP và JMX exposure

Chặn \`env\` trên HTTP nhưng giữ một custom MBean trả dữ liệu cấu hình giả. Quan sát một JMX client được cấp quyền vẫn có thể đọc custom MBean. Rút ra kết luận về sự độc lập giữa hai bề mặt.

### Bài tập D — Sanitization

Đặt một secret giả trong cấu hình test. Kiểm tra rằng principal đọc thông thường không nhận raw value qua HTTP, JMX hoặc log. Không dùng secret thật trong bài tập.

### Bài tập E — Production config overrides

Đặt allowlist trong \`application-prod.yml\`, sau đó dùng một environment variable trong môi trường lab làm thay đổi exposure. Kiểm tra effective surface thực tế và thêm regression test/policy deployment để ngăn wildcard ngoài ý định.

### Bài tập F — Role separation

Thiết kế ba roles: health probe, monitoring reader, operator. Quy định endpoints và operations nào từng role có thể truy cập. Viết tests chứng minh monitoring reader không thể gọi operation có side effect.

## 20. Câu hỏi tự kiểm tra

1. Sự khác biệt giữa “enabled”, “exposed”, “reachable” và “authorized” là gì?
2. Tại sao HTTP exposure và JMX exposure phải kiểm tra riêng?
3. \`management.endpoints.web.exposure.include=health,info\` có giới hạn tất cả custom MBeans không?
4. \`@ManagedOperation\` có tự phân quyền người gọi không?
5. Vì sao \`heapdump\` và \`env\` cần hạn chế?
6. Vì sao nên dùng allowlist thay vì \`include: "*"\`?
7. Management port riêng có tự tạo security không?
8. Tại sao ObjectName khó đoán không phải access control?
9. Cần kiểm tra gì sau khi có environment override?
10. Làm sao chứng minh một endpoint không bị công khai ngoài ý muốn?

## 21. Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Security Reference: https://docs.spring.io/spring-security/reference/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Oracle JDK — Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/

**Ghi nhớ:** production JMX/Actuator phải tuân nguyên tắc ít đặc quyền và ít exposure nhất. Giới hạn endpoint ở cả HTTP lẫn JMX, bảo vệ remote connector, không xuất secrets qua attributes, phân quyền read/write rõ ràng và kiểm tra surface thực tế sau mỗi thay đổi cấu hình hoặc nâng cấp.
