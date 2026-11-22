# management.endpoints.jmx.exposure.include trong Spring Boot Actuator

## 1. Tổng quan

Trong Spring Boot Actuator, các **management endpoints** cung cấp thông tin và thao tác vận hành như health, info, metrics, environment, beans hoặc loggers. Một endpoint có thể được expose qua các công nghệ khác nhau, thường là **HTTP** và **JMX**, tùy cấu hình và khả năng hỗ trợ.

Thuộc tính:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

quy định **những Actuator endpoint ID nào được phép expose qua JMX**. Đây là một allowlist theo endpoint ID dành cho công nghệ JMX, không phải cấu hình mở cổng kết nối JMX remote và cũng không phải cơ chế chọn tất cả Spring beans để export thành MBean.

Điểm cần nhớ:

> **Exposure** là quyết định endpoint nào xuất hiện qua một công nghệ quản trị; **access** là quyết định endpoint có sẵn để truy cập hay bị hạn chế; **transport/security** quyết định client nào thực sự có thể kết nối và thao tác.

Các phiên bản Spring Boot có thể thay đổi danh sách endpoint mặc định, thuộc tính access và điều kiện bật JMX. Khi triển khai, đối chiếu với tài liệu đúng phiên bản đang sử dụng.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của \`management.endpoints.jmx.exposure.include\`.
2. Cấu hình include/exclude bằng \`application.properties\` hoặc YAML.
3. Phân biệt JMX exposure với HTTP exposure.
4. Hiểu quan hệ giữa Actuator JMX endpoint, \`spring.jmx.enabled\`, \`MBeanExporter\` và \`MBeanServer\`.
5. Cân nhắc rủi ro khi sử dụng ký tự \`*\` để expose rộng.
6. Kiểm tra endpoint có thực sự xuất hiện trên MBeanServer hay không.
7. Xử lý các tình huống cấu hình đúng nhưng JMX client không nhìn thấy endpoint.

## 2. Actuator endpoint và công nghệ exposure

Spring Boot Actuator sử dụng các endpoint IDs như:

\`\`\`text
health
info
metrics
env
beans
loggers
threaddump
heapdump
configprops
conditions
mappings
scheduledtasks
\`\`\`

Danh sách endpoint thực tế tùy dependency, phiên bản Spring Boot, auto-configuration, điều kiện runtime và tính phù hợp của endpoint với công nghệ exposure. Không nên giả định mọi ID trên đều luôn tồn tại hoặc luôn hỗ trợ cả HTTP và JMX.

Mô hình:

\`\`\`text
             Spring Boot Application
                        |
                        v
                Actuator endpoints
                 /            \
                /              \
        Web exposure        JMX exposure
             |                  |
     HTTP management        MBeanServer
           routes                |
             |                  |
       HTTP clients          JMX clients
\`\`\`

Hai nhánh được cấu hình độc lập:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Trong ví dụ trên, một endpoint có thể được expose qua JMX nhưng không qua HTTP, hoặc ngược lại.

**Không nhầm** \`management.endpoints.jmx.exposure.include\` với \`management.endpoints.web.exposure.include\`: thuộc tính đầu dành cho JMX, thuộc tính sau dành cho HTTP.

## 3. Cú pháp trong application.properties

Cấu hình một vài endpoint:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Cấu hình chỉ một endpoint:

\`\`\`properties
management.endpoints.jmx.exposure.include=health
\`\`\`

Cấu hình tất cả endpoint đủ điều kiện exposure qua JMX:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
\`\`\`

Dùng include và exclude cùng lúc:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

Trong cấu hình exposure, **exclude được áp dụng để loại các endpoint đã bao gồm**. Vì vậy khi có \`include=*\` và \`exclude=env,beans\`, hai endpoint ID đó không nằm trong tập expose qua JMX.

Tuy nhiên, kiểu cấu hình “mở tất cả rồi loại bớt” có thể làm xuất hiện endpoint mới khi ứng dụng nâng cấp Spring Boot hoặc thêm dependency. Đối với môi trường có yêu cầu kiểm soát nghiêm ngặt, allowlist tường minh thường dễ review hơn.

### Wildcard * có ý nghĩa gì?

\`*\` là ký hiệu chọn toàn bộ endpoint IDs đủ điều kiện, không phải JMX \`ObjectName\` pattern và không phải wildcard của HTTP route.

Đặc biệt:
- \`include=*\` không tự tạo endpoint chưa tồn tại.
- \`include=*\` không vượt qua các điều kiện endpoint bị vô hiệu hóa, bị hạn chế access hoặc không hỗ trợ JMX.
- \`include=*\` không bật remote JMX connector hay cấp quyền truy cập.
- \`include=*\` không biến mọi Spring bean thành một Actuator endpoint.

## 4. Cấu hình YAML

Trong \`application.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
        exclude: "env"
\`\`\`

Hoặc danh sách YAML:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
\`\`\`

Khi dùng \`*\` trong YAML, **phải đặt trong dấu nháy**, vì dấu sao có ý nghĩa cú pháp alias trong YAML:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
\`\`\`

Không viết:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: *
\`\`\`

vì đây không phải YAML scalar hợp lệ với ý nghĩa wildcard bạn mong muốn.

### Đọc tên property

\`\`\`text
management . endpoints . jmx . exposure . include
    |            |       |       |         |
management   Actuator    JMX   tập công   ID được
                              bố qua JMX  bao gồm
\`\`\`

Đây là cấu hình của **Spring Boot Actuator**, không phải API trực tiếp của JMX standard.

## 5. Cấu hình theo môi trường

Một ứng dụng có thể muốn exposure khác nhau giữa development và production.

\`application-dev.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
\`\`\`

\`application-prod.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
\`\`\`

Đây chỉ là ví dụ định hướng. Trong production, các endpoint được expose phải dựa vào mô hình quyền và nhu cầu thực tế, không chọn mặc định rằng health/info/metrics đều vô hại.

Có thể dùng environment variable theo quy tắc relaxed binding của Spring Boot, ví dụ:

\`\`\`text
MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
\`\`\`

Quy tắc precedence giữa file cấu hình, environment variables, command-line arguments và các property sources khác của Spring Boot vẫn được áp dụng. Nếu giá trị thực tế không giống file cấu hình, hãy kiểm tra **effective configuration** của process, không chỉ đọc một file \`application.yml\`.

## 6. Quan hệ với spring.jmx.enabled

Một thuộc tính liên quan nhưng khác mục đích là:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

\`spring.jmx.enabled\` điều khiển việc Spring Boot bật cơ chế JMX export theo cấu hình tương ứng của phiên bản.

Trong khi đó:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

quy định tập **Actuator endpoints** được expose qua JMX.

Khác biệt:

| Thuộc tính | Phạm vi |
|---|---|
| \`spring.jmx.enabled\` | Bật/tắt JMX export của Spring Boot trong ngữ cảnh auto-configuration |
| \`management.endpoints.jmx.exposure.include\` | Include các Actuator endpoint IDs qua JMX |
| \`management.endpoints.jmx.exposure.exclude\` | Loại endpoint IDs khỏi JMX exposure |
| \`management.endpoints.web.exposure.include\` | Include endpoint IDs qua HTTP |
| \`management.endpoints.web.exposure.exclude\` | Loại endpoint IDs khỏi HTTP exposure |

Nếu \`spring.jmx.enabled=false\` trong cấu hình áp dụng cho runtime, việc đặt include cho Actuator JMX không phải là cách thay thế để bật hạ tầng export.

### Một cấu hình minh họa

\`\`\`properties
spring.jmx.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=env
\`\`\`

Cấu hình này thể hiện ý định: bật JMX integration và chỉ expose các endpoint IDs được liệt kê (trừ những ID bị exclude nếu trùng).

Cần kiểm tra Spring Boot version vì default values, endpoint access properties và một số hành vi auto-configuration có thể thay đổi qua các đời Boot.

## 7. Exposure, enablement và access là ba khái niệm khác nhau

Một endpoint chỉ xuất hiện khi các điều kiện liên quan cùng thỏa mãn.

### 7.1. Enablement

Endpoint phải tồn tại và được kích hoạt theo auto-configuration/endpoint enablement. Một endpoint bị vô hiệu hóa sẽ không được khôi phục chỉ bằng \`exposure.include\`.

### 7.2. Exposure

Endpoint đã có cần được công bố qua JMX. Đây là vai trò của \`management.endpoints.jmx.exposure.include\` và \`exclude\`.

### 7.3. Access

Các phiên bản Spring Boot mới có thể sử dụng nhóm cấu hình \`management.endpoint.<id>.access\` hoặc \`management.endpoints.access.default\` để quy định mức access như none, read-only hoặc unrestricted. Các property này không thể thay thế exposure; chúng còn tùy thuộc phiên bản cụ thể.

Một mô hình diễn giải:

\`\`\`text
Endpoint definition exists?
          |
          v
Endpoint enabled?
          |
          v
Endpoint access permits operation?
          |
          v
Endpoint included for JMX?
          |
          v
JMX MBean available?
          |
          v
Connector/security permits caller?
          |
          v
Remote client can interact
\`\`\`

Thứ tự nội bộ có thể khác tùy implementation, nhưng về mặt vận hành phải đánh giá **mọi điều kiện**. Không phải cứ có dòng \`include=health\` là chắc chắn có MBean của health trên mọi JVM.

## 8. Chỉ include những gì cần thiết

Ví dụ cần ba mục tiêu quản trị:

- \`health\`: thông tin tình trạng hệ thống theo endpoint contract.
- \`info\`: metadata vận hành đã được cấu hình để cung cấp.
- \`metrics\`: truy vấn một số metric có sẵn qua Actuator.

Cấu hình:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Đây là cách dễ kiểm kê. Khi application thêm dependency có endpoint mới, endpoint ấy không tự được expose qua JMX nếu không được đưa vào include list.

Tuy nhiên cần kiểm tra:
- Health details có chứa thông tin hạ tầng không?
- Info contributors có expose thông tin không nên công bố không?
- Metrics có high-cardinality tags hoặc thông tin nhạy cảm không?
- JMX caller có quyền đọc tất cả dữ liệu đó không?
- JMX remote có được giới hạn network không?

Một endpoint read-only vẫn có thể làm lộ cấu trúc hệ thống hoặc thông tin vận hành nhạy cảm.

## 9. Những rủi ro khi include=*

Cấu hình:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
\`\`\`

có thể thuận tiện trong development hoặc test để khám phá endpoint, nhưng cần cân nhắc ở production.

Những rủi ro:

1. **Mở rộng theo dependency:** một thư viện/starter mới có thể cung cấp endpoint mà bạn chưa review.
2. **Mở rộng theo nâng cấp:** phiên bản Boot mới có thể có endpoint IDs hoặc exposure behavior mới.
3. **Metadata nhạy cảm:** một số endpoint mô tả environment, mappings, beans hoặc runtime configuration.
4. **Operations thay đổi trạng thái:** tùy endpoint/access, một số thao tác quản trị có thể không chỉ là đọc.
5. **Khó audit:** tập endpoint hiệu dụng lớn, biến đổi theo environment.
6. **Khác biệt giữa HTTP và JMX:** đóng HTTP exposure không đồng nghĩa đã đóng JMX exposure.

Cấu hình bảo thủ hơn:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Lựa chọn cuối cùng phụ thuộc yêu cầu vận hành. Không nên tuyên bố một allowlist cố định là luôn an toàn; mọi endpoint vẫn phải được review theo dữ liệu và quyền sử dụng.

## 10. Actuator JMX endpoints và MBeanServer

Khi Actuator endpoint được expose qua JMX, Spring Boot quản lý việc đăng ký các biểu diễn MBean của endpoint đó vào \`MBeanServer\`.

Mô hình:

\`\`\`text
Actuator endpoint "health"
              |
              v
Actuator JMX exposure infrastructure
              |
              v
MBeanServer
              |
              v
ObjectName (Actuator-managed)
              |
              v
JConsole / JMX client
\`\`\`

Điểm quan trọng:

- Đây không nhất thiết là cùng class hay cùng ObjectName với một bean \`@ManagedResource\` do ứng dụng tự tạo.
- Actuator dùng naming strategy và domain/quy tắc riêng theo cấu hình Spring Boot.
- Không tự suy đoán ObjectName từ endpoint ID bằng cách nối chuỗi tùy tiện.
- Nếu có nhiều ứng dụng hoặc nhiều application contexts trong cùng JVM, cần kiểm tra tên JMX có bị trùng không.
- \`MBeanServer\` có thể là platform MBeanServer hoặc server được cấu hình phù hợp.

Cách xác minh đáng tin cậy là truy vấn **MBeanServer thực tế** và xem những ObjectNames nào đã được đăng ký.

## 11. Dùng JConsole để kiểm tra

Sau khi khởi động ứng dụng có JMX support:

1. Kết nối JConsole vào **đúng JVM**.
2. Mở tab **MBeans**.
3. Tìm domain chứa Actuator MBeans của ứng dụng.
4. So sánh những endpoint IDs đã được cấu hình với MBeans thực tế.
5. Kiểm tra operations/attributes được expose.
6. Nếu thiếu endpoint, đối chiếu effective configuration, enablement, access và JMX exporter.

Chỉ kiểm tra file YAML mà không nhìn runtime dễ bỏ sót:
- Profile production đang override include list.
- \`spring.jmx.enabled\` đang tắt.
- Endpoint không được tạo do dependency/conditions.
- Endpoint bị giới hạn access.
- Kết nối sai JVM hoặc sai MBeanServer.
- JMX export hoặc registration xảy ra lỗi.

### Một lệnh kiểm tra programmatic

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    String canonical = name.getCanonicalName();

    if (canonical.contains("endpoint")) {
        System.out.println(canonical);
    }
}
\`\`\`

Đây chỉ là ví dụ khám phá sơ bộ, không phải contract naming chính thức. Trong thực tế nên chọn domain/Pattern dựa trên ObjectNames mà Spring Boot đã đăng ký, thay vì dùng \`contains("endpoint")\` làm tiêu chí kiểm thử bắt buộc.

Dùng \`getMBeanInfo()\` để kiểm tra operations và descriptions:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Nếu Spring Boot export vào một MBeanServer khác platform server, cần truy vấn đúng server ấy.

## 12. Ví dụ Spring Boot Actuator đầy đủ

Dependency Maven (phiên bản được quản lý bởi Spring Boot BOM):

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

\`application.yml\`:

\`\`\`yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - env
    web:
      exposure:
        include:
          - health
\`\`\`

Ý định cấu hình:

- Có Actuator dependency để cung cấp các endpoint phù hợp.
- Bật JMX export integration của Spring Boot.
- Expose \`health\`, \`info\`, \`metrics\` qua JMX nếu endpoint tồn tại và access cho phép.
- Không expose \`env\` qua JMX theo cấu hình này.
- Chỉ expose \`health\` qua HTTP theo web include.

Đây là ví dụ phạm vi exposure, không phải cấu hình security đầy đủ. Nếu có remote connector, phải cấu hình authentication/authorization/network protection riêng.

### Tại sao nên quản lý HTTP và JMX riêng?

Một tổ chức có thể muốn:
- HTTP health endpoint được load balancer gọi.
- JMX metrics dành cho Java operations/monitoring tools.
- JMX loggers endpoint không được expose vì thay đổi log level runtime.
- HTTP admin endpoints không công khai qua internet.

Hai công nghệ có người dùng và mô hình access khác nhau; vì vậy tách include lists giúp kiểm soát rõ mục đích.

## 13. JMX endpoint không đồng nghĩa remote JMX connector

Một điểm dễ nhầm:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

**không có nghĩa** ứng dụng bắt đầu lắng nghe trên một TCP port cho JMX remote.

Để kết nối từ máy khác, cần có **JMXConnectorServer** hoặc cơ chế remote management của JVM, ví dụ RMI connector được cấu hình.

\`\`\`text
Spring Boot Actuator
       |
       v
JMX endpoint MBeans
       |
       v
MBeanServer
       |
       v
JMXConnectorServer <-- cấu hình riêng
       |
       v
Remote JMX client
\`\`\`

Việc mở cổng còn liên quan:
- RMI registry/connector endpoint ports.
- Hostname được quảng bá.
- Docker/Kubernetes port mapping.
- Firewall, ACL và routing.
- TLS và authentication.
- Chính sách quyền gọi operations.

Một endpoint “exposed through JMX” có thể quan sát được bằng local JMX tooling mà vẫn không thể truy cập qua mạng, và đó không nhất thiết là lỗi.

## 14. Security và quyền truy cập

### Exposure không thay thế security

Có thể hình dung:

\`\`\`text
Actuator endpoint exists
         |
         v
Enabled and accessible
         |
         v
Included in JMX exposure
         |
         v
Registered in MBeanServer
         |
         v
Connector accepts client
         |
         v
Authorization permits operation
\`\`\`

Một client có thể không truy cập được dù endpoint được include, vì:
- Network bị chặn.
- JMX connector không bật.
- Credentials sai.
- Caller không được phép thao tác.
- Access level của endpoint không cho hoạt động mong muốn.

Ngược lại, nếu remote JMX được cấu hình quá rộng, endpoint exposure có thể làm tăng bề mặt quản trị. Không dùng \`include=*\` mà không đánh giá tác động.

### Những endpoint cần cân nhắc đặc biệt

Một số loại endpoint có thể chứa thông tin:
- Environment/property sources.
- Bean dependency graph.
- HTTP request mappings.
- Loggers configuration.
- Heap dump hoặc thread dump.
- Runtime state của ứng dụng.

Tính nhạy cảm phụ thuộc cách ứng dụng cấu hình endpoint và chính sách che/mask dữ liệu. **Không coi việc một endpoint hiển thị thông tin đã được sanitize nghĩa là mọi giá trị đều an toàn khi expose rộng**.

Các operation có thể thay đổi cấu hình, tạo dump hoặc làm ảnh hưởng hiệu năng. Cần đánh giá riêng trước khi cho caller truy cập.

## 15. Include và Exclude: cách suy luận tập endpoint

Giả sử có những endpoint khả dụng:

\`\`\`text
health, info, metrics, env, beans, loggers
\`\`\`

Với:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
\`\`\`

Tập được chọn để expose là:

\`\`\`text
health, info
\`\`\`

Với:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

Tập được chọn là các endpoint đủ điều kiện ngoại trừ \`env\` và \`beans\`.

Với:

\`\`\`properties
management.endpoints.jmx.exposure.include=
\`\`\`

ý định là không include endpoint nào qua JMX, nhưng khi cấu hình bằng nhiều property sources hoặc các phiên bản Boot khác nhau, cần kiểm tra giá trị ràng buộc thực tế và những mặc định áp dụng. Không lấy một dòng rỗng trong một file làm bằng chứng cuối cùng khi hệ thống có profile overrides.

### Không nhầm include theo endpoint ID với ObjectName pattern

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

khác hoàn toàn với:

\`\`\`java
new ObjectName("org.springframework.boot:*");
\`\`\`

Cái thứ nhất là policy của Actuator. Cái thứ hai là mẫu truy vấn JMX ObjectNames, vốn có thể khớp nhiều loại MBean. Dùng đúng lớp khái niệm khi debug.

## 16. Cấu hình nhiều Spring Boot applications trong một JVM

Nếu nhiều application contexts hoặc nhiều Spring Boot components dùng chung MBeanServer, có thể phát sinh collision ObjectName.

Một ứng dụng có Actuator JMX endpoints có thể dùng quy ước naming và unique names của Boot. Khi nhiều application contexts được tạo trong cùng JVM, cần tham khảo các tùy chọn đặt tên hoặc domain phù hợp phiên bản, đồng thời kiểm tra thực tế qua \`queryNames()\`.

**Không giải quyết vấn đề collision bằng cách mở rộng include list.** Include quyết định endpoint nào được expose, không tự đảm bảo tên duy nhất.

Cần:
- Có naming convention ổn định.
- Biết exporter nào sở hữu MBean.
- Tránh tạo nhiều exporter trùng chức năng.
- Kiểm tra registration failures khi startup.
- Kiểm tra cleanup khi context đóng.

## 17. Sự khác biệt giữa JMX Actuator và @ManagedResource

Đây là nhầm lẫn thường gặp trong dự án có cả Spring Framework JMX lẫn Boot Actuator.

### @ManagedResource

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
public class CacheMonitor {

    @ManagedAttribute
    public int getSize() {
        return 42;
    }
}
\`\`\`

Cơ chế Spring JMX exporter tạo MBean theo metadata quản trị.

### Actuator endpoint

\`\`\`java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "customstatus")
public class CustomStatusEndpoint {

    @ReadOperation
    public String status() {
        return "UP";
    }
}
\`\`\`

Actuator exposure infrastructure có thể expose endpoint \`customstatus\` qua JMX nếu:
- Endpoint được tạo.
- Enabled/access cho phép.
- \`customstatus\` được include qua \`management.endpoints.jmx.exposure.include\`.
- JMX integration phù hợp được bật.

Hai annotation families phục vụ hai abstraction khác nhau. Thêm \`@ManagedResource\` không tự tạo Actuator endpoint ID \`cache\`; thêm \`@Endpoint\` không đồng nghĩa đã tạo một Standard MBean theo tên do bạn tự chỉ định.

## 18. Lỗi thường gặp và cách xử lý

### 18.1. Đã include nhưng JConsole không thấy endpoint

Kiểm tra:
- Dependency \`spring-boot-starter-actuator\`.
- \`spring.jmx.enabled\` và JMX auto-configuration.
- Endpoint có tồn tại không.
- Endpoint enablement/access.
- Exclude có loại endpoint không.
- Effective profile/property overrides.
- Client kết nối đúng JVM/MBeanServer.
- Registration error hoặc ObjectName collision.

### 18.2. HTTP thấy endpoint nhưng JMX không thấy

HTTP và JMX có include/exclude lists riêng. Một endpoint được expose qua HTTP không tự được expose qua JMX.

### 18.3. JMX thấy endpoint nhưng remote client không kết nối được

JMX exposure không tạo remote connector. Cần kiểm tra RMI/JMX service URL, ports, firewall, credentials, host binding và TLS.

### 18.4. YAML bị lỗi khi dùng *

Dấu \`*\` không đặt trong nháy có thể bị YAML parser hiểu là alias syntax. Dùng:

\`\`\`yaml
include: "*"
\`\`\`

### 18.5. Include tất cả nhưng vẫn thiếu một endpoint

\`include=*\` chỉ chọn những endpoint có thể được expose, không tự bật endpoint bị disable, không cung cấp missing dependency và không vượt quyền access.

### 18.6. Spring Boot nâng cấp làm xuất hiện endpoint ngoài dự kiến

Nếu dùng include wildcard, endpoint mới đủ điều kiện có thể xuất hiện sau nâng cấp. Dùng allowlist tường minh và kiểm kê ObjectNames trong integration test khi có yêu cầu kiểm soát.

### 18.7. Nhầm endpoint management với toàn bộ JMX MBeans

Một \`@ManagedResource\` được export bởi Spring JMX không nhất thiết chịu sự chi phối của \`management.endpoints.jmx.exposure.include\`. Thuộc tính này nhắm tới **Actuator endpoints**, không phải mọi MBean trong server.

## 19. Kiểm thử cấu hình bằng automated tests

Một chiến lược kiểm thử là khởi động Spring Boot test application với property overrides, rồi kiểm tra JMX MBeans hoặc endpoint exposure state.

Ví dụ cấu hình kiểm thử:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.jmx.enabled=true",
    "management.endpoints.jmx.exposure.include=health,info",
    "management.endpoints.jmx.exposure.exclude=env"
})
class JmxExposureTests {

    @Test
    void contextStartsWithJmxExposureConfiguration() {
        // Một kiểm thử tích hợp đầy đủ có thể lấy MBeanServer
        // từ ApplicationContext và xác minh ObjectNames.
    }
}
\`\`\`

Đây chỉ là khung minh họa cách inject properties, không phải một assertion hoàn chỉnh về exposure. Để kiểm thử hiệu quả, cần:
1. Lấy đúng MBeanServer được app dùng.
2. Xác định domain/naming convention của Actuator JMX trong phiên bản Boot chạy test.
3. Query các ObjectNames thực tế.
4. Kiểm tra expected endpoint MBeans xuất hiện.
5. Kiểm tra endpoint bị exclude không xuất hiện.
6. Tránh giả định các MBeans của hạ tầng không liên quan cũng nằm trong tập cần so.

Test JMX có thể cần dọn dẹp MBeans sau khi Spring context đóng để tránh collision giữa tests chạy cùng JVM.

## 20. Khung quyết định cấu hình an toàn

Có thể dùng các câu hỏi sau:

| Câu hỏi | Quyết định cần đưa ra |
|---|---|
| Endpoint nào cần giám sát qua JMX? | Chỉ include IDs thực sự cần |
| Endpoint có chứa dữ liệu nhạy cảm? | Hạn chế hoặc không expose |
| Endpoint có operation thay đổi trạng thái? | Kiểm tra access/authorization |
| Client dùng local attach hay remote connector? | Cấu hình và bảo vệ transport tương ứng |
| Spring Boot version nào? | Kiểm tra mặc định và các access properties đúng version |
| Có HTTP management endpoints không? | Cấu hình web exposure độc lập |
| Có nhiều contexts trên cùng MBeanServer? | Quản lý naming và collision |
| Có kế hoạch nâng cấp dependencies? | Kiểm tra allowlist và ObjectNames sau upgrade |

### Một cấu hình mẫu dễ kiểm soát

\`\`\`yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
    web:
      exposure:
        include:
          - health
\`\`\`

Đây là **điểm xuất phát cho thảo luận**, không phải một chuẩn security áp dụng cho mọi hệ thống. Từng endpoint cần được chọn dựa trên nhu cầu quản trị và khả năng bảo vệ kết nối JMX của môi trường.

## 21. Bài tập thực hành

### Bài tập A — Chỉ expose health

1. Thêm \`spring-boot-starter-actuator\`.
2. Bật JMX support phù hợp.
3. Đặt \`management.endpoints.jmx.exposure.include=health\`.
4. Khởi động application và kết nối JConsole vào đúng JVM.
5. Ghi lại ObjectName được tạo cho health endpoint.
6. Xác minh \`info\` và \`metrics\` không tự xuất hiện dưới dạng Actuator JMX endpoints vì chỉ có health được include.

### Bài tập B — Include và exclude

1. Cấu hình include \`*\`.
2. Cấu hình exclude \`env,beans\`.
3. Khởi động application.
4. So sánh tập endpoint MBeans với cấu hình chỉ include \`health,info\`.
5. Giải thích tại sao exclude giúp loại mục nhưng allowlist vẫn dễ quản lý hơn khi nâng cấp.

### Bài tập C — Phân biệt HTTP và JMX

1. Đặt web include là \`health\`.
2. Đặt JMX include là \`health,info,metrics\`.
3. Xem HTTP routes của Actuator và MBeans đã xuất.
4. Giải thích vì sao hai tập không giống nhau.

### Bài tập D — Remote connector

1. Xác minh Actuator JMX MBeans bằng local JMX.
2. Cấu hình remote connector trong môi trường thử nghiệm có bảo mật.
3. Kết nối từ JMX client ở JVM khác.
4. Đọc endpoint MBean qua \`MBeanServerConnection\`.
5. Phân biệt lỗi connector với lỗi include/exclude.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** \`management.endpoints.jmx.exposure.include\` điều khiển điều gì?  
**Trả lời:** Danh sách Actuator endpoint IDs được phép expose qua công nghệ JMX.

**Câu 2.** \`include=*\` có bật toàn bộ Spring beans thành MBeans không?  
**Trả lời:** Không. Nó chọn Actuator endpoints đủ điều kiện, không phải mọi Spring beans.

**Câu 3.** \`management.endpoints.web.exposure.include\` khác gì?  
**Trả lời:** Nó chọn Actuator endpoints cho HTTP exposure, không phải JMX.

**Câu 4.** Tại sao cần chú ý \`spring.jmx.enabled\`?  
**Trả lời:** Vì JMX export integration phải được kích hoạt phù hợp thì cấu hình exposure mới có tác dụng.

**Câu 5.** Có include một endpoint nhưng vẫn không nhìn thấy, vì sao?  
**Trả lời:** Endpoint có thể không tồn tại, bị disable/access restricted, bị exclude, JMX support bị tắt hoặc client kết nối sai server.

**Câu 6.** \`include=*\` có tự mở JMX remote RMI port không?  
**Trả lời:** Không. Remote connector và bảo mật phải được cấu hình riêng.

**Câu 7.** Vì sao nên kiểm tra MBeanInfo và ObjectName sau khi bật JMX?  
**Trả lời:** Để xác nhận bề mặt quản trị thực tế, không chỉ ý định cấu hình từ properties.

## 23. Ghi nhớ

- \`management.endpoints.jmx.exposure.include\` là **allowlist Actuator endpoint IDs qua JMX**.
- \`management.endpoints.jmx.exposure.exclude\` loại endpoint IDs khỏi tập JMX exposure.
- \`management.endpoints.web.exposure.include\` hoạt động độc lập cho HTTP.
- \`spring.jmx.enabled\` liên quan việc bật JMX export integration của Spring Boot; include không thay thế nó.
- Exposure không tự enable endpoint bị vô hiệu hóa, không tự cấp quyền và không tạo remote JMX connector.
- Wildcard \`*\` thuận tiện nhưng có thể làm mở rộng bề mặt quản trị ngoài dự kiến; trong YAML phải quote.
- Actuator JMX endpoint khác với Spring \`@ManagedResource\` được xuất thông qua \`MBeanExporter\`.
- Kiểm tra effective configuration, ObjectNames và MBeanInfo trên đúng MBeanServer.
- Khi vận hành production, kết hợp include allowlist với bảo vệ remote connector và access control.

### Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Common Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/index.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
