# Phân biệt giao tiếp HTTP với giao tiếp JMX

## 1. Một khả năng vận hành có thể được truy cập qua nhiều kênh

Người vận hành có thể đọc sức khỏe ứng dụng bằng một URL HTTP, hoặc mở một công cụ JMX để gọi khả năng quản trị trong JVM. Cả hai phục vụ vận hành, nhưng cách tìm đối tượng, gửi yêu cầu và nhận kết quả khác nhau.

Trong Actuator, cần tách:

- **Endpoint:** khả năng quản trị cùng các thao tác mà nó cung cấp.
- **HTTP:** một kênh đưa thao tác đó ra ngoài bằng URL và phương thức HTTP.
- **JMX — Java Management Extensions:** cơ chế quản trị của nền tảng Java, làm việc với các đối tượng quản trị được đăng ký trong MBeanServer.

Mô hình khái quát:

~~~text
                 Endpoint Actuator
                cùng các operation
                    /         \
                   /           \
          Đưa ra HTTP       Đưa ra JMX
          URL + method      MBean + operation
                   \           /
                    \         /
                 Logic vận hành
~~~

Không phải endpoint nào cũng hỗ trợ cả hai kênh. Một endpoint có thể độc lập công nghệ, hoặc được giới hạn cho web/JMX.

Bài này dùng hợp đồng Spring Boot 3.3.x và ví dụ chạy với Boot 3.3.0, JDK 21.

## 2. So sánh theo cách sử dụng

| Tiêu chí | HTTP | JMX |
| --- | --- | --- |
| Định vị khả năng | URL, ví dụ /actuator/health | ObjectName trong một MBeanServer |
| Cách gọi | Phương thức HTTP, query/body khi operation cần | Đọc thuộc tính hoặc gọi operation qua API/công cụ JMX |
| Biểu diễn kết quả | Thường là JSON đối với endpoint phù hợp, có HTTP status/header | Giá trị và cấu trúc dữ liệu theo metadata JMX |
| Công cụ thường dùng | curl, trình duyệt cho thao tác đọc, HTTP client, bộ kiểm tra sức khỏe | JConsole hoặc JMX client |
| Cần web server không? | Có hạ tầng HTTP phù hợp | Không bắt buộc có web server |
| Cấu hình chọn endpoint | management.endpoints.web.exposure.* | management.endpoints.jmx.exposure.* |
| Bảo vệ đường truy cập | Cơ chế bảo mật web, TLS và mạng tương ứng | Quyền truy cập cục bộ hoặc cơ chế của JMX connector/agent tương ứng |

HTTP hữu ích khi hạ tầng đã sử dụng URL để kiểm tra trạng thái. JMX hữu ích khi cần tích hợp với công cụ quản trị Java hoặc truy cập trực tiếp mô hình quản trị của JVM. Không cần bật cả hai nếu không có bên sử dụng tương ứng.

JMX không đồng nghĩa một giao thức mạng duy nhất. Nó có thể được dùng ngay trong JVM; truy cập từ xa cần connector. Cơ chế quản trị từ xa có sẵn của JDK sử dụng RMI. Xem [JDK 21 — Monitoring and Management Using JMX](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html).

## 3. HTTP: endpoint được biểu diễn bằng URL và method

### 3.1. Đường dẫn web

Với cấu hình thông thường:

~~~text
Endpoint ID: health
Base path:   /actuator
HTTP:        GET http://127.0.0.1:8080/actuator/health
~~~

Một phản hồi health đơn giản khi các kiểm tra hiện có đều tốt có thể có body:

~~~json
{"status":"UP"}
~~~

Body là một phần của phản hồi HTTP; mã trạng thái và header cũng thuộc hợp đồng của giao tiếp đó.

Tiền tố web có thể đổi bằng `management.endpoints.web.base-path`. Nếu dùng `/manage`, đường dẫn có thể thành `/manage/health`, còn ID vẫn là health. Cổng web quản trị có thể tách bằng `management.server.port`. Xem [Spring Boot 3.3 — Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.2. Cần hạ tầng web phù hợp

Một ứng dụng có starter Actuator nhưng không có môi trường web phù hợp không tự có URL ở cổng 8080. Ứng dụng Servlet hoặc reactive cần hạ tầng tương ứng để đưa endpoint ra HTTP.

Ví dụ chỉ đọc health trong một ứng dụng web đã chạy ở loopback:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

Nếu không kết nối được hoặc bị từ chối truy cập, cần kiểm tra tiến trình, cổng, đường dẫn, exposure và chính sách bảo mật. Không chuyển nguyên một URL như vậy sang ô ObjectName của JMX rồi mong hai bên hiểu cùng cú pháp.

## 4. JMX: endpoint được đăng ký thành đối tượng quản trị

### 4.1. MBean và MBeanServer

**MBean (Managed Bean)** là đối tượng quản trị theo mô hình JMX. Nó công bố metadata để công cụ biết các thuộc tính hoặc operation có thể sử dụng.

**MBeanServer** là thành phần quản lý việc đăng ký, tìm và truy cập các MBean. Các thao tác điển hình gồm:

- Kiểm tra một ObjectName đã được đăng ký chưa.
- Đọc metadata của đối tượng.
- Đọc/ghi các thuộc tính mà đối tượng hỗ trợ.
- Gọi một operation với đúng tham số và chữ ký kiểu.

MBean không đồng nghĩa mọi Spring bean. Một đối tượng được Spring quản lý chưa mặc nhiên là MBean được công bố cho công cụ JMX. Xem [JDK 21 — MBeanServer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html).

### 4.2. ObjectName khác với URL

Với tên mặc định thông dụng, endpoint health được công bố dưới dạng:

~~~text
org.springframework.boot:type=Endpoint,name=Health
~~~

Tách chuỗi này:

| Phần | Vai trò |
| --- | --- |
| `org.springframework.boot` | JMX domain |
| `type=Endpoint` | Một thuộc tính khóa để phân loại |
| `name=Health` | Một thuộc tính khóa để nhận diện đối tượng trong cách đặt tên này |

Đây không phải một địa chỉ HTTP và JMX domain không phải hostname DNS. Dấu hai chấm ở đây phân cách domain với tập thuộc tính khóa.

Một ObjectName có phần domain và các key properties; thứ tự các key properties không phải cách biểu diễn một cây URL. Khi tìm đối tượng bằng chương trình, dùng API `ObjectName` để biểu diễn và so khớp. Xem [JDK 21 — ObjectName API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html).

Tên thực tế còn có thể bị tùy chỉnh domain hoặc bổ sung thông tin để tránh trùng. Khi công cụ không tìm thấy MBean, hãy xem danh sách tên được đăng ký thay vì chỉ đoán một chuỗi cố định.

### 4.3. Spring Boot JMX không phải toàn bộ JMX của JVM

Trong Boot 3.3, `spring.jmx.enabled` mặc định không bật tính năng quản trị JMX do Spring cung cấp. Có thể bật bằng:

~~~properties
spring.jmx.enabled=true
~~~

Boot lựa chọn MBeanServer phù hợp và hỗ trợ đưa những thành phần quản trị tương ứng vào đó. Endpoint Actuator mặc định dùng domain `org.springframework.boot`; có thể tùy chỉnh tên/domain khi cần. Xem [Spring Boot 3.3 — Monitoring over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Tắt thuộc tính này không có nghĩa mọi MBean của JVM hoặc thư viện khác bị xóa. JVM có các platform MXBean cho những thành phần như bộ nhớ, luồng và hệ điều hành; chúng thuộc hạ tầng quản trị của Java. Xem [JDK 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

Vì vậy, “JConsole vẫn thấy thông tin JVM” không chứng minh endpoint Actuator đã được xuất qua JMX.

## 5. Exposure HTTP và JMX là hai lựa chọn riêng

### 5.1. Ví dụ cấu hình một ứng dụng có cả hai khả năng

~~~properties
spring.jmx.enabled=true
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health
~~~

YAML tương đương:

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health
~~~

Nếu endpoint khả dụng và các hạ tầng tương ứng đã có:

| Endpoint | Được chọn cho HTTP | Được chọn cho JMX |
| --- | --- | --- |
| health | Có | Có |
| info | Có | Không |

Bảng mô tả **phạm vi exposure**, không bảo đảm mọi yêu cầu từ mọi bên gọi đều được phép.

Cả hai danh sách dùng endpoint ID. Không đặt `/actuator/health` hoặc `org.springframework.boot:type=Endpoint,name=Health` vào include.

### 5.2. Trạng thái bật và trạng thái công bố khác nhau

Một endpoint bị tắt hoặc thiếu thành phần cần thiết sẽ không được tạo chỉ vì có tên trong include.

Ngược lại, một endpoint khả dụng có thể được chọn cho JMX nhưng không được chọn cho web. Đặt web exclude không tự đặt JMX exclude, và ngược lại.

Trong Boot 3.3, tập endpoint mặc định đưa ra mỗi giao diện là health; phía JMX còn cần tính năng Spring JMX được bật. Các thuộc tính include/exclude của từng giao diện được mô tả trong [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 5.3. HTTP không bắt buộc kéo theo kết nối JMX từ xa

`spring.jmx.enabled=true` không đồng nghĩa một cổng JMX từ xa đã được mở cho máy khác. Nó điều khiển phần quản trị do Spring cung cấp.

Tương tự, `management.server.port=8081` đặt cổng HTTP quản trị, không phải cổng RMI/JMX. Không đưa số cổng 8081 vào JConsole như thể đó chắc chắn là JMX connector.

Cần phân biệt việc đăng ký MBean vào MBeanServer với việc cấu hình một phương tiện cho client ở xa truy cập server đó.

## 6. Endpoint chung và endpoint riêng cho từng công nghệ

### 6.1. Endpoint độc lập công nghệ

`@Endpoint` mô tả một endpoint có các operation như `@ReadOperation`, `@WriteOperation` hoặc `@DeleteOperation`. Actuator có thể thích nghi các operation với công nghệ công bố tương ứng. Xem [Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

Cùng một thao tác đọc có thể được gọi qua HTTP hoặc qua operation JMX khi cả hai đều được hỗ trợ và công bố. Điều này giúp tách logic vận hành khỏi cách client kết nối.

Không nên giả định dữ liệu phức tạp luôn có biểu diễn giống hệt giữa JSON và công cụ JMX. Client cần đọc hợp đồng hoặc metadata của kênh đang dùng.

### 6.2. Giới hạn theo công nghệ

| Annotation | Phạm vi công bố theo mô hình |
| --- | --- |
| `@Endpoint` | Có thể thích nghi cho các công nghệ được hỗ trợ |
| `@WebEndpoint` | Chỉ cho HTTP |
| `@JmxEndpoint` | Chỉ cho JMX |

Thêm tên một WebEndpoint vào JMX include không biến nó thành endpoint JMX. Tương tự, JmxEndpoint không tự có URL web chỉ vì được ghi vào web include. Xem [WebEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html) và [JmxEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html).

Đây là một lý do không nên đòi hỏi danh sách endpoint ở hai công cụ phải giống nhau hoàn toàn.

## 7. Thực nghiệm JMX cục bộ không cần HTTP server

Ví dụ chạy trong một dự án Spring Boot **3.3.0**, JDK **21**, có quản lý phiên bản dependency và tác vụ chạy Boot. Mã Java sử dụng cú pháp tương thích Java 17 trở lên.

Mục tiêu là kiểm tra:

1. Một endpoint được đăng ký thành MBean.
2. Có thể gọi operation của nó qua MBeanServer.
3. Đổi exposure web không tự làm thay đổi exposure JMX.

### 7.1. Dependency và cấu hình

Trong dự án Gradle đã có Boot plugin và quản lý phiên bản 3.3.0, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là phần dependencies ghép vào dự án có sẵn. Không cần Web starter vì thực nghiệm không dùng máy chủ HTTP.

Trong `src/main/resources/application.properties`:

~~~properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,runtimecheck
management.endpoints.web.exposure.include=health
~~~

### 7.2. Tệp Java đầy đủ

Tạo `src/main/java/example/actuatorjmx/ActuatorJmxApplication.java`:

~~~java
package example.actuatorjmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorJmxApplication {
    @Bean
    public RuntimeCheckEndpoint runtimeCheckEndpoint() {
        return new RuntimeCheckEndpoint();
    }

    public static void main(String[] args) throws Exception {
        SpringApplication application =
                new SpringApplication(ActuatorJmxApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            MBeanServer server = ManagementFactory.getPlatformMBeanServer();
            ObjectName name = new ObjectName(
                    "org.springframework.boot:type=Endpoint,name=Runtimecheck");
            boolean registered = server.isRegistered(name);
            System.out.println("registered=" + registered);
            if (registered) {
                Object result = server.invoke(
                        name, "state", new Object[0], new String[0]);
                System.out.println("state=" + result);
            }
        }
    }

    @Endpoint(id = "runtimecheck")
    public static class RuntimeCheckEndpoint {
        @ReadOperation
        public String state() {
            return "READY";
        }
    }
}
~~~

Chương trình không thực hiện nghiệp vụ hoặc thay đổi trạng thái bên ngoài; operation state chỉ trả một chuỗi cố định để đối chiếu.

Các điểm cần đọc:

- Bean `RuntimeCheckEndpoint` có ID `runtimecheck`.
- `WebApplicationType.NONE` giữ ứng dụng ở chế độ không có web.
- MBeanServer được lấy trực tiếp trong JVM, không qua kết nối từ xa.
- ObjectName ở ví dụ dùng domain và quy tắc tên mặc định của Boot.
- `invoke` gọi operation `state` không có tham số.
- Context được đóng sau khi in kết quả.

Package `javax.management` trong mã là API JMX của Java SE. Không tự đổi thành `jakarta.management` chỉ vì ứng dụng dùng Spring Boot 3.

### 7.3. Lần A: endpoint được chọn cho JMX

Chạy trong thư mục dự án có Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Với cấu hình và tên MBean mặc định đã nêu, hai dòng do chương trình in là:

~~~text
registered=true
state=READY
~~~

Dòng đầu xác nhận đúng ObjectName đã được đăng ký. Dòng thứ hai xác nhận đã gọi operation qua API JMX.

Đây là stdout của chương trình thử nghiệm. Log framework nếu có không thuộc chuỗi đầu ra cố định.

### 7.4. Lần B: chỉ chọn runtimecheck ở web

Chạy lại:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.jmx.exposure.include=health --management.endpoints.web.exposure.include=health,runtimecheck"
~~~

Kết quả:

~~~text
registered=false
~~~

Runtimecheck không còn được chọn cho JMX. Việc nó có trong danh sách web không làm nó được đăng ký vào MBeanServer.

Thực nghiệm vẫn không tạo HTTP server, nên dòng web include cũng không chứng minh có URL để gọi. Nó chỉ là một lựa chọn exposure chưa có hạ tầng web trong chương trình này.

### 7.5. Lần C: loại khỏi JMX dù có trong include

Giữ tệp nền và chạy:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.jmx.exposure.exclude=runtimecheck"
~~~

Kết quả:

~~~text
registered=false
~~~

Exclude ưu tiên khi cùng chọn một ID. Web exposure không bị sửa theo lệnh này.

### 7.6. Lần D: tắt phần JMX do Spring cung cấp

~~~powershell
.\gradlew.bat bootRun --args="--spring.jmx.enabled=false"
~~~

Trong thực nghiệm này:

~~~text
registered=false
~~~

Chương trình vẫn có thể gọi `ManagementFactory.getPlatformMBeanServer()` để hỏi về ObjectName. Không tìm thấy MBean Actuator không có nghĩa API JMX hoặc hạ tầng quản trị của JVM đã biến mất.

Mỗi lệnh ở trên là một lần chạy độc lập với cùng tệp nền, không mang các đối số của lần trước sang lần sau.

### 7.7. Phạm vi mà thí nghiệm xác minh

Các lần chạy xác minh việc đăng ký MBean và gọi JMX ngay trong JVM. Chúng không kiểm tra HTTP, không bật JMX từ xa và không kiểm tra quy tắc đăng nhập của một remote connector.

Nếu đổi domain hoặc bật tên duy nhất để tránh trùng, cần cập nhật cách tìm ObjectName của chương trình. Không giữ chuỗi tên mặc định rồi suy ra endpoint không được công bố.

## 8. Dùng JConsole trong một ứng dụng đang chạy

JConsole là một JMX client có giao diện. Với ứng dụng đang chạy phù hợp để attach cục bộ, có thể:

1. Mở công cụ `jconsole` từ JDK.
2. Chọn đúng tiến trình Java đang cần quan sát.
3. Chuyển sang mục MBeans.
4. Tìm domain và ObjectName thực tế.
5. Đọc metadata, rồi gọi operation với đúng tham số nếu được phép.

Kết nối cục bộ phụ thuộc quyền và điều kiện attach của môi trường. Trong cách sử dụng phổ biến, công cụ và tiến trình chạy với cùng người dùng. Xem [JDK 21 — Using JConsole](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html).

Chương trình thử nghiệm ở phần 7 đóng ngay sau khi in kết quả, nên không dùng nó như một dịch vụ chờ JConsole kết nối. Khi học thao tác giao diện, dùng một ứng dụng thực sự còn chạy; không thêm sleep hoặc cơ chế giữ tiến trình chỉ để thay đổi ý nghĩa của thí nghiệm trên.

MBeanServer có thể chứa nhiều nhóm đối tượng: MBean Actuator, platform MXBean của JVM hoặc MBean từ thư viện khác. Cần chọn đúng domain và đối tượng trước khi kết luận về Actuator.

### Kết nối từ xa là một bước cấu hình riêng

Nếu cần JMX từ máy khác, phải cấu hình agent/connector, địa chỉ và các điều kiện mạng tương ứng. Những thuộc tính JVM như `com.sun.management.jmxremote.port` thuộc cơ chế quản trị JDK; chỉ ghi chúng vào application.yml không mặc nhiên làm JVM khởi tạo remote agent theo ý muốn.

Không sao chép chính sách xác thực HTTP sang JMX bằng cách giả định hai kênh dùng chung bộ lọc. Xác định cơ chế xác thực, quyền và mã hóa cho connector đang sử dụng.

## 9. Bảo vệ và chẩn đoán theo đúng kênh

### 9.1. Quy tắc web không tự bao phủ JMX

Trong ứng dụng web, Spring Security có thể bảo vệ yêu cầu HTTP bằng các quy tắc phù hợp. Bộ lọc web xử lý URL không phải cơ chế chung áp dụng cho mọi lần gọi qua MBeanServer. Xem [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

Vì thế, HTTP trả 401/403 không chứng minh MBean tương ứng đã bị chặn ở JMX. Ngược lại, không kết nối được JMX từ xa không chứng minh HTTP endpoint cũng ngừng phục vụ.

Tác dụng của operation vẫn cần được đánh giá: đọc thông tin cấu hình có thể tiết lộ dữ liệu; thay đổi mức log hoặc thao tác vận hành khác có thể ảnh hưởng hệ thống, dù được gọi qua kênh nào.

### 9.2. Câu hỏi chẩn đoán cho HTTP

- Đúng host, cổng và base path chưa?
- Có web server đang chạy không?
- Endpoint có được tạo và chọn cho web không?
- Operation có đúng method và tham số không?
- Yêu cầu bị security hoặc proxy xử lý như thế nào?

### 9.3. Câu hỏi chẩn đoán cho JMX

- Đang kết nối đúng JVM/MBeanServer không?
- Phần quản trị JMX của Spring đã được bật chưa?
- ID có nằm trong tập JMX exposure và có bị exclude không?
- ObjectName có đúng domain, tên và phần bổ sung chống trùng không?
- Operation và chữ ký tham số có khớp metadata không?
- Nếu kết nối từ xa, connector/agent và quyền truy cập có phù hợp không?

Một lỗi `InstanceNotFoundException` do không tìm thấy MBean khác với lỗi kết nối tới connector. Tương tự, đọc sai ObjectName không nên được xử lý bằng cách mở thêm hàng loạt cổng.

## 10. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Bật Actuator nghĩa là luôn có cả HTTP và JMX | Mỗi kênh có điều kiện hạ tầng và exposure riêng |
| JMX là URL /actuator qua một cổng khác | JMX dùng MBeanServer, ObjectName và operation theo mô hình riêng |
| Mọi Spring bean đều nhìn thấy trong JConsole | Bean cần được công bố theo cơ chế quản trị phù hợp |
| Mở web include đồng thời mở JMX include | Hai tập lựa chọn độc lập |
| spring.jmx.enabled=true mở ngay cổng quản trị từ xa | Đăng ký phần quản trị của Spring khác với cấu hình connector từ xa |
| management.server.port là cổng JMX | Đó là cổng HTTP quản trị |
| Chặn /actuator bằng security web là đủ cho cả hai kênh | Cần đánh giá riêng đường truy cập JMX |
| Tắt Spring JMX làm mất mọi platform MXBean | Phần quản trị JVM và thư viện khác có vòng đời/cấu hình riêng |
| JMX client phải nhận JSON giống curl | Biểu diễn kết quả theo hợp đồng của từng kênh |
| Không có HTTP server thì không thể quản trị ứng dụng | JMX có thể hoạt động độc lập với web |

### Tự thực hành

1. Muốn đọc health từ bộ kiểm tra HTTP, cần kiểm tra những điều kiện nào ngoài việc có starter Actuator?
2. Web include có health,info; JMX include chỉ có health. Với các hạ tầng đã sẵn sàng, endpoint nào được chọn cho từng kênh?
3. Chạy bốn tình huống thực nghiệm và giải thích registered thay đổi theo thuộc tính nào.
4. Nếu JConsole vẫn thấy java.lang:type=Memory sau khi tắt spring.jmx.enabled, điều đó có mâu thuẫn không?
5. Một ứng dụng dùng management.server.port=8081 nhưng JConsole không kết nối được tới 8081. Hãy giải thích giả định sai có thể nằm ở đâu.

**Gợi ý đối chiếu:** cần tách mô hình endpoint, việc công bố theo kênh và phương tiện kết nối. HTTP dùng URL; JMX làm việc với đối tượng quản trị trong MBeanServer. Hai kênh có thể phục vụ cùng khả năng nhưng không tự chia sẻ cấu hình exposure hoặc chính sách truy cập.
