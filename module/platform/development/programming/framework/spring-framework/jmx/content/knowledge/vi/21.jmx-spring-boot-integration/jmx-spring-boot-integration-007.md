# Kiểm tra MBean Actuator bằng JConsole trong Spring Boot

## 1. Mục tiêu bài thực hành

Spring Boot Actuator cung cấp các endpoint phục vụ quan sát và quản trị ứng dụng: thông tin tình trạng hoạt động, chỉ số, thông tin bean, cấu hình và những chẩn đoán khác tùy dependency và cấu hình. Nhiều người quen truy cập Actuator bằng HTTP, ví dụ `/actuator/health`, nhưng Actuator còn có thể công bố endpoint qua **JMX**. Khi đó các endpoint có thể xuất hiện dưới dạng **MBean**, và công cụ **JConsole** của JDK có thể khám phá cũng như gọi operation trên chúng.

Bài này hướng dẫn kiểm tra từ đầu đến cuối:

1. Thêm dependency Actuator và bật JMX export phù hợp.
2. Khởi chạy Spring Boot application và xác định đúng JVM/PID.
3. Kết nối bằng JConsole tới tiến trình local.
4. Tìm domain JMX của Actuator và các MBean endpoint như `Health`, `Info`, `Metrics`.
5. Kiểm tra `MBeanInfo`, đọc metadata và gọi những operation **chỉ đọc, an toàn**.
6. Phân biệt endpoint không xuất hiện do exposure, do availability hay do kết nối nhầm JVM.
7. Giữ bề mặt quản trị được kiểm soát, không mở remote JMX chỉ để chạy thí nghiệm.

**Điểm quan trọng:** Actuator HTTP và Actuator JMX là **hai công nghệ truy cập** tới hệ thống endpoint, có cấu hình exposure riêng. Bật `management.endpoints.web.exposure.include` không có nghĩa endpoint đó tự được export qua JMX. Và ngược lại, một endpoint nhìn thấy bằng JConsole có thể không được công bố qua HTTP.

## 2. Luồng kiến trúc: từ Actuator endpoint đến JConsole

```text
                   Spring Boot Application
                            |
                    Spring ApplicationContext
                            |
                Actuator endpoint beans
                  /                    \
                 /                      \
         Web endpoint mapping       JMX endpoint exporter
                 |                      |
             HTTP server             MBeanServer
                 |                      |
         GET /actuator/...      ObjectName trong JMX
                                        |
                                    JConsole
                                        |
                                MBeans -> Operations
```

Các vai trò:

| Thành phần | Nhiệm vụ |
|---|---|
| `spring-boot-starter-actuator` | Đưa hạ tầng Actuator và các endpoint liên quan vào ứng dụng |
| `management.endpoints.jmx.exposure.*` | Kiểm soát endpoint Actuator nào được công bố qua JMX |
| `spring.jmx.enabled` | Điều khiển khả năng Spring JMX export của Boot khi phù hợp với phiên bản |
| `MBeanServer` | Registry chứa JMX MBean |
| Actuator JMX exporter | Đăng ký endpoint Actuator thành MBean |
| `JConsole` | JMX client để xem metadata và gọi operation |
| `ObjectName` | Địa chỉ của MBean trong registry |

Không phải endpoint nào cũng có output đơn giản kiểu `String` hay `int`. Actuator có thể trả dữ liệu dạng cấu trúc, và giao diện JConsole sẽ hiển thị giá trị qua những kiểu JMX/OpenData mà endpoint exporter hỗ trợ.

## 3. Chuẩn bị: JDK và ứng dụng Spring Boot

Bài sử dụng JDK có `java`, `javac` và `jconsole`, cùng một dự án Spring Boot tương thích với phiên bản Java bạn đang dùng. Ví dụ cấu hình Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Nếu muốn ứng dụng không có HTTP server, có thể dùng starter phù hợp mà không cần `spring-boot-starter-web`; bài dùng web starter để dễ so sánh HTTP và JMX, không phải vì JMX bắt buộc phải có HTTP.

Kiểm tra JDK:

```bash
java -version
jconsole
```

JConsole có giao diện desktop. Nếu chạy trong container headless hoặc qua SSH không có GUI, chương trình có thể không mở cửa sổ; khi đó dùng máy desktop có quyền kết nối vào JVM hoặc Java JMX client để quan sát. Không mở cổng remote JMX công khai để “chữa” việc thiếu giao diện.

## 4. Ứng dụng Spring Boot tối giản

Lớp chính:

```java
package demo.actuatorjmx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorJmxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ActuatorJmxDemoApplication.class,
            args
        );
    }
}
```

Có thể thêm một controller đơn giản để tạo request phục vụ quan sát:

```java
package demo.actuatorjmx;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from JMX demo";
    }
}
```

Controller không phải điều kiện để Actuator JMX hoạt động. Nó chỉ tạo một điểm truy cập HTTP của ứng dụng, giúp tăng một vài chỉ số trong lúc test khi metrics backend được cấu hình.

## 5. Bật JMX và cấu hình exposure Actuator

File `src/main/resources/application.properties` dùng trong bài:

```properties
# Bật Spring JMX ở môi trường lab.
spring.jmx.enabled=true

# Chỉ expose một số Actuator endpoint qua JMX.
management.endpoints.jmx.exposure.include=health,info,metrics

# Đặt domain dễ nhận biết.
management.endpoints.jmx.domain=demo.actuator

# HTTP exposure độc lập: chỉ cho phép health/info trong lab.
management.endpoints.web.exposure.include=health,info
```

Với các phiên bản Spring Boot hỗ trợ những property trên, Actuator JMX exporter sẽ xuất các endpoint được bật và nằm trong danh sách JMX exposure. `management.endpoints.jmx.domain` giúp bạn tìm domain rõ ràng trong JConsole.

**Không nên bật `management.endpoints.jmx.exposure.include=*` trong môi trường dùng chung** chỉ để dễ học. Một số endpoint có thể tiết lộ cấu hình, dữ liệu chẩn đoán hoặc cung cấp operation không nên cho mọi client truy cập.

### 5.1. Phân biệt enable và exposure

Có ít nhất hai câu hỏi riêng:

- Endpoint có tồn tại và được enable theo điều kiện/classpath/cấu hình hay không?
- Endpoint đó có được **expose qua JMX** không?

Một endpoint được enable không có nghĩa mặc định được công bố qua mọi transport. Một endpoint chưa được tạo hoặc bị disable thì thêm tên nó vào exposure list cũng không tự làm nó có mặt.

Ngoài ra, những endpoint có dữ liệu nhạy cảm có thể áp dụng chính sách hiển thị chi tiết, sanitization và authorization riêng. Không giả định rằng JConsole sẽ thấy đúng cùng một JSON như HTTP endpoint.

### 5.2. Cú pháp wildcard

Khi thực sự cần thử tất cả endpoint trong môi trường test cô lập, cách viết wildcard trong `application.properties` có thể là:

```properties
management.endpoints.jmx.exposure.include=*
```

Với YAML, dấu `*` cần được quote vì có ý nghĩa cú pháp trong YAML:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
```

Đây chỉ là ví dụ cú pháp; không sử dụng cấu hình mở rộng toàn bộ exposure làm mặc định production.

## 6. Khởi chạy và xác định tiến trình

Với Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows có thể dùng:

```powershell
.\mvnw.cmd spring-boot:run
```

Hoặc build và chạy file jar:

```bash
./mvnw package
java -jar target/actuator-jmx-demo-*.jar
```

Tên file jar thực tế tùy `artifactId` và version trong `pom.xml`. Giữ ứng dụng chạy. Có thể mở terminal thứ hai để xác định PID, sử dụng `jps -l` nếu lệnh có sẵn trong JDK, hoặc xem danh sách process ngay khi mở JConsole.

Khi chạy bằng Maven, có thể có nhiều Java process liên quan; vì vậy phải chọn **JVM chạy ứng dụng Spring Boot**, không chọn nhầm Maven launcher hoặc IDE daemon.

Dấu hiệu ứng dụng đã start thành công không tự chứng minh Actuator JMX đã export. Bước tiếp theo là kết nối và kiểm tra registry.

## 7. Mở JConsole và kết nối local

Mở terminal khác:

```bash
jconsole
```

Trong cửa sổ chọn kết nối:

1. Chọn tiến trình Java local tương ứng với ứng dụng Spring Boot.
2. Đối chiếu PID hoặc main class nếu có nhiều JVM.
3. Kết nối và mở tab `MBeans`.
4. Tìm domain `demo.actuator` mà bạn đã cấu hình.
5. Mở từng MBean bên dưới domain để xem `Attributes`, `Operations`, `Notifications` hoặc phần metadata tùy loại MBean.

JConsole có thể hiển thị danh sách domain và ObjectName theo cấu trúc cây khác với chính chuỗi ObjectName thô. Ví dụ một tên dạng:

```text
demo.actuator:type=Endpoint,name=Health
```

có thể được trình bày theo nhánh `type=Endpoint` rồi `name=Health`. Đây là ví dụ hình dạng ObjectName thường gặp; tên thực tế phải được xác nhận bằng cây MBeans hoặc API `queryNames` trên phiên bản Boot đang chạy.

Không cố đoán cây JConsole theo thứ tự cố định nếu cấu hình domain/naming hoặc Boot version khác.

## 8. Kiểm tra các MBean Actuator

### 8.1. Health

Endpoint `health` thường dùng để báo tình trạng ứng dụng hoặc nhóm health. Trong cây `MBeans`, tìm MBean tương ứng với `Health`.

Với JMX endpoint, hành vi quan sát thường nằm ở phần **Operations** (operation do endpoint exporter công bố) thay vì một property getter JavaBeans đơn giản. Tên và chữ ký operation phụ thuộc vào cách Actuator chuyển endpoint operation sang JMX.

Gọi một operation chỉ đọc, chẳng hạn operation đọc health được metadata hiển thị. Giá trị có thể là một cấu trúc đại diện cho `status` và các details phù hợp.

**Không tự giả định operation luôn tên là `health()`, `getHealth()` hay `status()` trong mọi phiên bản.** Hãy mở `MBeanInfo` hoặc JConsole Operations để xác nhận tên và tham số.

Health response có thể bị ảnh hưởng bởi cấu hình `management.endpoint.health.show-details` và policy truy cập. Một trạng thái `UP` không chứng minh mọi dependency luôn khỏe; nó phản ánh các health indicators và thời điểm kiểm tra.

### 8.2. Info

Endpoint `info` có thể công bố thông tin mô tả về ứng dụng khi có `InfoContributor` thích hợp. Nếu endpoint không có dữ liệu, output có thể trống hoặc ít trường; điều đó không nhất thiết là lỗi JMX.

Không nhầm Spring Boot build info, git info, environment và custom info. Chúng phụ thuộc dependency, resource và cấu hình của ứng dụng.

### 8.3. Metrics

Endpoint `metrics` có thể cho biết tên metric và chi tiết một metric, tùy signature được export. Trong JConsole, xem parameter của operation trước khi gọi. Nếu operation yêu cầu `requiredMetricName` hoặc tag selector, hãy nhập đúng kiểu và giá trị.

Không giả định metric name giống nhau giữa mọi dự án. Một số metric chỉ xuất hiện khi workload tương ứng phát sinh hoặc khi Micrometer registry được cấu hình. Đối chiếu các tên metric đang có trong chính ứng dụng.

Khi client gọi một metric, phân biệt **số đo tức thời**, **counter tích lũy**, **timer** và các measurement khác. Không coi mọi số đều có cùng đơn vị.

## 9. Ví dụ ghi nhận kết quả bằng bảng

Khi mở JConsole, hãy điền dữ liệu thực tế:

| Đối tượng quan sát | Kỳ vọng ở lab | Điều cần ghi |
|---|---|---|
| JVM đã chọn | Đúng Spring Boot process | PID, Java version |
| Domain | `demo.actuator` | Domain thực tế |
| Health MBean | Có nếu endpoint được enable và expose | ObjectName, operation |
| Info MBean | Có nếu endpoint được enable và expose | ObjectName, output |
| Metrics MBean | Có nếu endpoint khả dụng và expose | Operation signature |
| Health read | Trả thông tin health | Status, thời điểm gọi |
| Metrics read | Trả số liệu khi có metric | Tên metric, đơn vị |
| JMX exposure change | MBean thay đổi khi restart | Trước/sau và cấu hình |

Đây là bảng kỳ vọng để học, không phải output do bài này đã chạy. Giá trị thực tế phải lấy từ JVM của bạn.

## 10. Kiểm tra qua Java JMX API nếu JConsole khó quan sát

JConsole là client đồ họa; JMX API có thể giúp kiểm tra trực tiếp registry và metadata:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("demo.actuator:*"), null)) {

    System.out.println("MBean = " + name);

    MBeanInfo info = server.getMBeanInfo(name);
    for (var operation : info.getOperations()) {
        System.out.println(
            "  Operation = " + operation.getName()
        );
    }
}
```

Đoạn code trên cần chạy trong **cùng JVM** với Spring Boot application nếu dùng platform MBeanServer local. Có thể đặt logic vào một `ApplicationRunner` hoặc một component chạy sau startup và truyền đúng MBeanServer. Nếu muốn chạy từ tiến trình khác, phải kết nối qua một JMX connector đã được cấu hình và bảo vệ; `ManagementFactory.getPlatformMBeanServer()` trong client JVM khác sẽ chỉ trỏ đến server của chính client.

Nếu ứng dụng export MBean vào một `MBeanServer` riêng, cần dùng đúng server đó; không mặc định mọi MBean luôn nằm trong platform server.

### 10.1. Kiểm tra chi tiết operation signature

```java
for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
    for (var param : op.getSignature()) {
        System.out.printf(
            "  %s : %s%n",
            param.getName(),
            param.getType()
        );
    }
}
```

Từ metadata, bạn sẽ biết operation có bao nhiêu tham số và kiểu Java/JMX nào được yêu cầu. Điều này chính xác hơn việc đoán signature từ một bài blog cho phiên bản Boot khác.

## 11. HTTP endpoint và JMX endpoint có thể khác nhau

Một cấu hình minh họa:

```properties
management.endpoints.web.exposure.include=health
management.endpoints.jmx.exposure.include=health,info,metrics
```

Khi đó `info` và `metrics` có thể xuất hiện qua JMX trong khi không được expose qua web. Đó là kết quả có chủ đích của hai danh sách exposure.

Ngược lại:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.include=health
```

có thể làm JConsole chỉ thấy MBean `Health` thuộc tập endpoint Actuator đã export, còn HTTP có thêm `Info` và `Metrics`.

Lưu ý một endpoint còn chịu các điều kiện enable và availability. Không nên dùng một URL HTTP thành công để kết luận 100% JMX đã được bật; và không dùng việc JMX hiện diện để suy ra HTTP endpoint đang công khai.

## 12. Spring JMX thường và Actuator JMX khác nhau ra sao?

Spring Framework cung cấp annotation quản trị như:

```java
@ManagedResource(objectName = "demo.custom:type=QueueMonitor")
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() {
        return 12;
    }
}
```

Đó là **MBean từ Spring JMX annotation export**. Còn Actuator endpoint có thể khai báo bằng:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueSummary")
public class QueueSummaryEndpoint {

    @ReadOperation
    public java.util.Map<String, Object> summary() {
        return java.util.Map.of("depth", 12);
    }
}
```

Với Actuator JMX exporter và exposure phù hợp, endpoint `queueSummary` có thể được công bố thành JMX MBean. Nó không cần `@ManagedResource`. Đây là hai đường export khác nhau:

```text
Spring JMX:
  @ManagedResource + @ManagedAttribute
      -> AnnotationMBeanExporter
      -> MBeanServer

Spring Boot Actuator:
  @Endpoint + @ReadOperation
      -> Actuator JMX endpoint exporter
      -> MBeanServer
```

Một ứng dụng có thể dùng cả hai. Khi kiểm kê JConsole, cần phân biệt domain và ObjectName của custom MBean với domain Actuator. Chúng đều là JMX MBean nhưng metadata và quy tắc export không giống nhau.

## 13. Lưu ý khi viết custom Actuator endpoint

Ví dụ endpoint từ phần trước trả `Map<String,Object>`. Với JMX, dữ liệu có thể được chuyển thành cấu trúc phù hợp với endpoint exporter. Nhưng không nên export object graph quá lớn, dữ liệu người dùng hay credential chỉ vì một read operation có thể trả Map.

Một endpoint quản trị tốt:

- Có tên/id ổn định.
- Chỉ công bố số liệu hoặc trạng thái cần thiết.
- Có return type đơn giản, dễ quan sát.
- Không thực hiện side effect trong `@ReadOperation`.
- Dùng `@WriteOperation`/`@DeleteOperation` chỉ khi có nhu cầu và phân quyền rõ.
- Không giả định HTTP security đồng nghĩa JMX connector security.
- Kiểm tra exposure ở từng transport.

Custom endpoint có thể bị disable theo cấu hình id; chỉ thêm `@Component` không chứng minh endpoint đã được export qua JMX.

## 14. Trường hợp JConsole không thấy MBean Actuator

Đi lần lượt từ nguyên nhân đơn giản đến phức tạp:

### 14.1. Chọn sai JVM

Nếu mở JConsole từ máy có nhiều process Java, dễ kết nối nhầm Maven daemon/IDE/process khác. Đối chiếu PID, main class, VM summary và command line. Nếu đúng process nhưng vẫn không thấy domain, chuyển sang kiểm tra configuration.

### 14.2. Chưa có Actuator dependency

Không có `spring-boot-starter-actuator` hoặc Actuator module cần thiết, ứng dụng không tạo những endpoint như dự kiến. Kiểm tra dependency tree/build configuration và runtime classpath.

### 14.3. JMX bị tắt

Kiểm tra `spring.jmx.enabled` trong cấu hình hiệu lực của Spring Boot tương ứng. Trong một số dự án, property có thể bị override bởi environment variable, command-line argument hoặc profile-specific properties. Đừng chỉ xem file `application.properties` mặc định.

### 14.4. Endpoint không được expose qua JMX

Kiểm tra `management.endpoints.jmx.exposure.include` và `exclude`. Cấu hình web exposure không thay thế JMX exposure. Nếu tên endpoint bị exclude, thêm vào include cũng có thể không giúp.

### 14.5. Endpoint không tồn tại hoặc bị disable

Một endpoint có thể phụ thuộc dependency, auto-configuration hoặc property enable. Kiểm tra endpoint beans và condition report nếu dùng Boot.

### 14.6. Domain khác dự kiến

Nếu `management.endpoints.jmx.domain` không có hiệu lực hoặc được override, tên domain có thể khác. Truy vấn ObjectName hiện có bằng API hoặc quan sát tất cả domain trong JConsole, thay vì chỉ tìm `demo.actuator`.

### 14.7. Exporter dùng MBeanServer khác

JConsole local thường quan sát platform MBeanServer. Nếu ứng dụng cấu hình một MBeanServer riêng, bạn có thể cần truy vấn đúng registry hoặc thay đổi cấu hình để exporter dùng platform server theo chủ đích.

### 14.8. Lỗi registration hoặc ObjectName collision

Hai exporter/MBean có thể muốn dùng cùng ObjectName. Xem startup logs và registration policy. Không khắc phục bằng cách bật `REPLACE_EXISTING` khi chưa biết đối tượng nào sở hữu MBean.

### 14.9. Có MBean nhưng operation gọi lỗi

Kiểm tra signature từ metadata, kiểu tham số, endpoint availability, exception trong read operation và security policy. Operation nhìn thấy trong JConsole không đồng nghĩa dữ liệu luôn trả về thành công.

## 15. Health endpoint: cẩn thận với chi tiết nhạy cảm

Một endpoint health có thể bao gồm tình trạng database, disk, messaging hoặc hệ thống bên ngoài. Dù chỉ có `UP`/`DOWN`, kết quả vẫn có ý nghĩa vận hành; còn details có thể chứa tên host, service hoặc thông tin nội bộ.

Các nguyên tắc:

1. Không coi JMX local là lý do để export raw secrets.
2. Chỉ bật health details phù hợp với đối tượng được phép xem.
3. Hạn chế endpoint custom trả URL có credential, raw exception message hoặc cấu hình.
4. Nếu cần phân tích lỗi chuyên sâu, dùng logging redaction và quy trình chẩn đoán an toàn riêng.
5. Khi dùng remote JMX, quản lý quyền truy cập ở connector/server, không dựa vào việc actuator HTTP endpoint đã được bảo vệ.

Không nên gọi operation có side effect chỉ để thử JConsole. Trong bài này ưu tiên read operation.

## 16. Remote JConsole và bảo mật

Bài thực hành khuyến khích **local connection**: mở JConsole trong môi trường có quyền phù hợp với JVM đang chạy. Nếu ứng dụng chạy trong container/kubernetes hoặc máy khác, không tự động mở JMX RMI port công khai.

Remote JMX có những yêu cầu:

- Authentication và authorization phù hợp.
- TLS hoặc kênh mã hóa đáng tin cậy.
- Firewall/network policy hạn chế nguồn kết nối.
- Quản lý cả RMI registry endpoint và remote object endpoint khi dùng RMI.
- Kiểm soát credential và truststore.
- Audit các thao tác quản trị có tác dụng phụ.

Không dùng `com.sun.management.jmxremote.authenticate=false` hoặc `com.sun.management.jmxremote.ssl=false` làm cấu hình mặc định cho môi trường dùng chung. Nếu chưa có cấu hình remote an toàn, hãy dùng JVM local hoặc viết một diagnostic chạy trong process để đọc metadata.

## 17. Ví dụ kiểm tra cấu hình hiệu lực bằng ApplicationContext

Bạn có thể thêm một `ApplicationRunner` để xác nhận endpoint MBean sau khi ứng dụng khởi động:

```java
package demo.actuatorjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxDiagnosticsConfiguration {

    @Bean
    ApplicationRunner jmxInspection() {
        return args -> {
            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            for (ObjectName name : server.queryNames(
                    new ObjectName("demo.actuator:*"), null)) {
                MBeanInfo info = server.getMBeanInfo(name);
                System.out.println("Actuator MBean: " + name);
                System.out.println(
                    "Operations: " + info.getOperations().length
                );
            }
        };
    }
}
```

Đây là kiểm tra metadata sau startup, không đọc giá trị nhạy cảm. Nếu không thấy MBean, xem `spring.jmx.enabled`, JMX exposure, endpoint availability và lựa chọn MBeanServer.

Khi dùng Actuator trong hệ thống production, nên giới hạn logging metadata và sử dụng structured logger phù hợp; không in mọi JMX attribute hay endpoint response vào stdout.

## 18. So sánh với lệnh curl

Nếu dùng web starter và endpoint `health` được expose qua HTTP:

```bash
curl http://localhost:8080/actuator/health
```

Có thể nhận response có `status` hoặc thông tin khác tùy cấu hình. Nhưng yêu cầu bài là kiểm tra **MBean Actuator qua JConsole**, vì vậy `curl` chỉ dùng để đối chiếu.

Một HTTP response thành công xác nhận web endpoint hoạt động; nó không xác nhận JMX registration. Ngược lại, JConsole gọi health thành công không chứng minh HTTP endpoint đang expose. Việc tách này đặc biệt quan trọng khi ứng dụng đặt management port riêng hoặc policy web endpoint chặt chẽ.

## 19. Thực hành A: bật/tắt JMX exposure và quan sát

Chạy ứng dụng với:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.domain=demo.actuator
```

Kiểm tra JConsole, ghi lại ObjectName của `Health` và `Info`.

Sau đó đổi thành:

```properties
management.endpoints.jmx.exposure.include=health
```

Khởi động lại ứng dụng (không mặc định cấu hình sẽ hot-reload), kết nối lại JConsole, so sánh. Dự kiến `Info` không còn trong tập endpoint JMX được expose nếu nó không được đưa vào qua cơ chế khác.

Lưu ý có thể có những MBean không thuộc Actuator vẫn tồn tại trong các domain khác. Bài tập chỉ so sánh **tập endpoint Actuator đã export**.

## 20. Thực hành B: custom endpoint

Tạo endpoint:

```java
@Component
@Endpoint(id = "workerSummary")
public class WorkerSummaryEndpoint {
    @ReadOperation
    public java.util.Map<String, Object> read() {
        return java.util.Map.of(
            "activeJobs", 3,
            "mode", "RUNNING"
        );
    }
}
```

Thêm `workerSummary` vào danh sách JMX exposure theo cấu hình. Sau khi restart, tìm MBean của endpoint này trong JConsole và xem operation metadata.

Không thêm `@WriteOperation` cho một bài chỉ cần đọc. Nếu sau này cần thao tác thay đổi trạng thái, phải có validation và quyền tương ứng.

## 21. Thực hành C: đối chiếu một metric

Để có dữ liệu thay đổi, gửi vài request tới `/hello` rồi quan sát endpoint `metrics` qua JConsole. Tên metric cụ thể có thể phụ thuộc phiên bản Boot, Micrometer, registry và instrumentation.

Các bước:

1. Kiểm tra `Metrics` MBean có xuất hiện không.
2. Xem operation liệt kê metric name nếu có.
3. Chọn một metric đang hiện diện.
4. Gọi operation với tham số đúng kiểu.
5. Ghi measurement, đơn vị và thời điểm.
6. Tạo thêm một số request, đọc lại để so sánh.

Không đoán số request từ một measurement nếu không hiểu tên, tags, sampling và cách metric được tổng hợp. Hãy dùng metadata và output thực tế.

## 22. Các sai lầm dễ gặp

### 22.1. “Actuator có /health nên JConsole chắc có Health”

Không chắc: HTTP và JMX exposure độc lập, JMX có thể bị tắt hoặc chọn server khác.

### 22.2. “JMX enabled nghĩa là expose mọi endpoint”

Không: endpoint availability và JMX exposure còn giới hạn tập được công bố.

### 22.3. “Mọi endpoint Actuator đều có attribute getStatus”

Không: endpoint operation được export theo mô hình Actuator; tên, tham số, output cần đọc từ `MBeanInfo`.

### 22.4. “Muốn thấy hết thì bật wildcard ở production”

Không nên: tăng bề mặt quản trị và khả năng lộ dữ liệu/operation. Dùng allowlist theo nhu cầu.

### 22.5. “JConsole local luôn nhìn thấy mọi MBeanServer trong JVM”

Không nên mặc định: có thể tồn tại nhiều MBeanServer. Kiểm tra registry mà exporter sử dụng.

### 22.6. “Có thể đọc mọi health detail qua JMX mà không cần quan tâm quyền”

Không: health detail và endpoint output có thể nhạy cảm, cần mô hình exposure và access control phù hợp.

### 22.7. “Metric không thấy chắc chắn Actuator hỏng”

Có thể endpoint không expose, meter chưa được tạo, classpath thiếu instrumentation, hoặc tên metric khác kỳ vọng.

### 22.8. “Gọi thử mọi operation là cách kiểm tra an toàn”

Sai: một số operation có tác dụng phụ hoặc trả dữ liệu nhạy cảm. Chỉ kiểm thử operation đã hiểu trong môi trường phù hợp.

## 23. Câu hỏi tự kiểm tra

1. `spring-boot-starter-actuator` có vai trò gì?
2. `spring.jmx.enabled` liên quan đến điều gì trong Spring Boot?
3. `management.endpoints.jmx.exposure.include` khác `management.endpoints.web.exposure.include` như thế nào?
4. Vì sao phải chọn đúng JVM/PID trước khi tìm Actuator MBean?
5. `management.endpoints.jmx.domain` giúp ích gì?
6. Tại sao endpoint `Health` có thể nằm trong Operations thay vì Attributes?
7. `MBeanInfo` cho biết thông tin gì trước khi gọi endpoint?
8. Vì sao `/actuator/health` hoạt động không bảo đảm JMX `Health` xuất hiện?
9. Những nguy cơ nào xuất hiện khi mở remote JMX tới máy khác?
10. Khi custom `@Endpoint`, vì sao không nên trả credential hoặc raw configuration?

## 24. Ghi nhớ

**Actuator JMX là một cách công bố Spring Boot endpoint thành MBean để JMX client như JConsole có thể truy cập.** Để kiểm tra đúng, cần bật Spring JMX, đảm bảo endpoint có mặt và được expose qua JMX, kết nối đúng JVM, tìm ObjectName trong domain cấu hình và đọc `MBeanInfo` trước khi gọi operation.

Đừng đồng nhất cấu hình HTTP với JMX, đừng suy đoán tên operation từ source của phiên bản khác và không mở remote JMX hoặc wildcard exposure không kiểm soát. Một quy trình kiểm tra đáng tin cậy đi từ dependency và cấu hình hiệu lực tới registry thực tế và kết quả lời gọi an toàn.
