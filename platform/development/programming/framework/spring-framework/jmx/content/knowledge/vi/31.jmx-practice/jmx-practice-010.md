# Thực hành kết hợp JMX với Spring Boot Actuator

## 1. Mục tiêu và kết quả cần đạt

Spring Boot Actuator cung cấp các endpoint quản trị, chẩn đoán và quan sát ứng dụng, còn JMX (Java Management Extensions) là một giao thức và mô hình chuẩn của Java để quản lý các MBean trong `MBeanServer`. Khi kết hợp hai cơ chế, bạn có thể:

- Công bố **Actuator endpoints** như Health, Info hoặc Metrics qua JMX, bên cạnh HTTP khi được cấu hình.
- Tạo **custom Spring JMX MBean** với `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation`.
- Kiểm tra các MBean trong **JConsole** hoặc qua `MBeanServer` API.
- So sánh dữ liệu quan sát được giữa `/actuator/health`, `/actuator/metrics` và cây JMX.
- Phân biệt phạm vi exposure của Actuator với cấu hình export MBean của Spring.
- Đánh giá những rủi ro khi mở rộng bề mặt quản trị, đặc biệt với operation có tác dụng phụ.

Bài thực hành này dùng một Spring Boot application nhỏ chứa một bộ đếm xử lý tác vụ, một MBean tùy chỉnh và Actuator. Các bước có thể áp dụng trong một JVM local mà **không mở remote JMX**. Đây là lựa chọn mặc định an toàn và đơn giản cho mục đích học tập.

Một kết quả mong đợi:

```text
Spring Boot process
    |
    +-- Spring ApplicationContext
    |       |
    |       +-- TaskService
    |       +-- TaskManagement (custom @ManagedResource)
    |       +-- Actuator endpoint beans
    |
    +-- Platform MBeanServer
            |
            +-- company.demo:type=TaskManagement,name=primary
            +-- actuator domain -> Health / Info / Metrics (tùy exposure)
            +-- java.lang / java.nio / other JVM MXBeans
```

Các ObjectName Actuator thực tế phụ thuộc phiên bản Spring Boot và cấu hình domain. Vì vậy bài dùng `queryNames` hoặc JConsole để xác nhận tên thật, không bắt buộc một chuỗi ObjectName cứng cho mọi phiên bản.

## 2. JMX và Actuator khác nhau như thế nào?

Hai cơ chế phục vụ cùng miền quan sát nhưng không cùng abstraction.

| Khía cạnh | Spring Framework JMX | Spring Boot Actuator |
|---|---|---|
| Thành phần chính | `MBeanExporter`, `MBeanServer`, MBean | Endpoint beans, auto-configuration, exposure |
| Cách tạo API | Standard MBean hoặc annotation `@ManagedResource` | `@Endpoint` với `@ReadOperation`, `@WriteOperation`... |
| Giao thức truy cập | JMX local/remote | HTTP và JMX khi cấu hình |
| Định danh | `ObjectName` | Endpoint ID, ánh xạ thành ObjectName hoặc URL |
| Monitoring | Attribute, notification, operation | Health, info, metrics, custom endpoints |
| Quản trị | Writable attribute/operation | Write/delete operations tùy endpoint |
| Lịch sử số liệu | Không có mặc định | Actuator metrics thường dựa trên Micrometer, backend lưu time series nếu được cấu hình |

Một bean có `@ManagedResource` **không tự trở thành Actuator endpoint**. Ngược lại, `@Endpoint(id="tasks")` không nhất thiết trở thành Spring annotation MBean theo cơ chế `@ManagedResource`. Actuator có hạ tầng export riêng để chuyển endpoint đủ điều kiện thành JMX MBean.

Khi ứng dụng dùng cả hai, JConsole có thể thấy **cả custom MBean lẫn Actuator endpoint MBeans**. Cần phân biệt domain và quyền quản trị của từng nhóm.

## 3. Chuẩn bị môi trường

Bạn cần:

- JDK tương thích với phiên bản Spring Boot đã chọn.
- Maven hoặc Gradle, ví dụ dùng Maven Wrapper.
- IDE tùy chọn.
- JConsole đi kèm JDK có giao diện desktop, hoặc Java JMX API để kiểm tra nếu chạy headless.
- Một cổng HTTP local còn trống cho ví dụ web.

Bài không yêu cầu server JMX remote. Nếu JVM chạy trong Docker/Kubernetes, dùng kiểm tra bằng Java API hoặc một môi trường desktop local trước. Không bật RMI không xác thực và không mã hóa chỉ để làm JConsole nhìn thấy ứng dụng.

### 3.1. Cấu trúc dự án

```text
actuator-jmx-lab/
  pom.xml
  src/main/java/example/actuatorjmx/
    ActuatorJmxApplication.java
    TaskService.java
    TaskManagement.java
    TaskController.java
    JmxInspectionConfiguration.java
  src/main/resources/
    application.properties
  src/test/java/example/actuatorjmx/
    TaskManagementJmxTest.java
```

Đây là dự án minh họa. Trong thực tế có thể đặt những lớp trên vào module và package tương ứng mà không thay đổi bản chất tích hợp.

## 4. Dependency Spring Boot Actuator

Ví dụ `pom.xml` dùng Spring Boot parent đã chọn theo phiên bản đang vận hành:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>actuator-jmx-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Phần này giả định parent/BOM của Spring Boot đã được khai báo bởi dự án hoặc bổ sung khi khởi tạo bằng Spring Initializr. Không có BOM hoặc parent cung cấp dependency versions, Maven sẽ yêu cầu cấu hình version cụ thể. `java.version=17` chỉ là ví dụ và phải phù hợp với Spring Boot đang dùng.

Không cần dependency Prometheus để hoàn thành lab JMX/Actuator cơ bản. Nếu muốn export metrics ra Prometheus, có thể bổ sung `micrometer-registry-prometheus` cùng cấu hình exposure thích hợp ở phần mở rộng.

## 5. Khởi tạo Spring Boot application

```java
package example.actuatorjmx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorJmxApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorJmxApplication.class, args);
    }
}
```

`@SpringBootApplication` bật auto-configuration và component scan theo package. Đặt các lớp ví dụ cùng package hoặc package con để chúng được phát hiện. Nếu lớp nằm ngoài phạm vi scan, bean có thể không tồn tại dù source có annotation JMX.

Khi ứng dụng startup, Spring Boot có thể cấu hình những infrastructure beans liên quan JMX và Actuator tùy classpath/properties/version. **Không mặc định tự thêm một `MBeanExporter` nữa**, vì hai exporter có thể tìm và đăng ký cùng custom MBean.

## 6. Tạo TaskService làm nguồn trạng thái duy nhất

Service bên dưới ghi nhận số tác vụ đã hoàn thành và số tác vụ đang chạy:

```java
package example.actuatorjmx;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class TaskService {
    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();
    private volatile int warningThreshold = 10;

    public void startTask() {
        active.incrementAndGet();
    }

    public void completeTask() {
        active.updateAndGet(n -> Math.max(0, n - 1));
        completed.incrementAndGet();
    }

    public long completedCount() {
        return completed.get();
    }

    public int activeCount() {
        return active.get();
    }

    public int warningThreshold() {
        return warningThreshold;
    }

    public void setWarningThreshold(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException(
                "warningThreshold must be 1..1000"
            );
        }
        warningThreshold = value;
    }

    public void resetCounters() {
        completed.set(0);
        active.set(0);
    }
}
```

Đây là state holder phục vụ lab, không phải mô hình queue production hoàn chỉnh. `startTask()` và `completeTask()` giúp tăng giảm các bộ đếm để quan sát. Không dùng `resetCounters()` trong production nếu đang có job thật chạy.

Việc dùng một service làm nguồn dữ liệu giảm nguy cơ custom MBean và Actuator trả những giá trị mâu thuẫn do tự duy trì hai counter riêng.

## 7. Tạo custom JMX MBean bằng annotation

```java
package example.actuatorjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "company.demo:type=TaskManagement,name=primary",
    description = "Demo task management"
)
public class TaskManagement {
    private final TaskService service;

    public TaskManagement(TaskService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Completed tasks")
    public long getCompletedTasks() {
        return service.completedCount();
    }

    @ManagedAttribute(description = "Active tasks")
    public int getActiveTasks() {
        return service.activeCount();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return service.warningThreshold();
    }

    @ManagedAttribute(description = "Update warning threshold")
    public void setWarningThreshold(int value) {
        service.setWarningThreshold(value);
    }

    @ManagedOperation(description = "Reset task counters")
    public void resetCounters() {
        service.resetCounters();
    }

    public String getInternalImplementationDetail() {
        return "not exported intentionally";
    }
}
```

Các annotation mô tả bề mặt JMX mong muốn:

- `CompletedTasks` và `ActiveTasks`: read-only attributes.
- `WarningThreshold`: read-write attribute.
- `resetCounters`: operation có tác dụng phụ, chỉ dùng trong lab.
- `getInternalImplementationDetail()`: method công khai của Java class nhưng **không được đánh dấu để export**.

Trong context có hạ tầng annotation JMX thích hợp, exporter sẽ tạo MBean cho resource này. Đây là ví dụ dùng metadata `@ManagedResource`; nó không cần implement interface `TaskManagementMBean` của Standard MBean.

Không dùng một reflective assembler quá rộng chỉ để làm method hiện ra trong JConsole, vì có thể vô tình export các method nội bộ hoặc dữ liệu nhạy cảm.

## 8. Cấu hình Spring Boot JMX và Actuator exposure

File `src/main/resources/application.properties`:

```properties
spring.application.name=actuator-jmx-lab
server.port=8080

# Bật hỗ trợ Spring JMX export trong phiên bản Boot phù hợp.
spring.jmx.enabled=true

# Chỉ expose nhóm endpoint Actuator cần thiết qua JMX.
management.endpoints.jmx.exposure.include=health,info,metrics

# Domain riêng để dễ nhận diện trong JConsole.
management.endpoints.jmx.domain=company.actuator

# HTTP exposure độc lập với JMX.
management.endpoints.web.exposure.include=health,info,metrics
```

`spring.jmx.enabled` điều khiển việc Spring Boot tạo hạ tầng Spring JMX export khi điều kiện auto-configuration được đáp ứng. Endpoint Actuator qua JMX còn chịu `management.endpoints.jmx.exposure.*` và enable/availability của từng endpoint.

**Không đồng nhất `spring.jmx.enabled` và `management.endpoints.jmx.exposure.include`.** Cái thứ nhất liên quan hạ tầng JMX export, cái thứ hai quyết định tập Actuator endpoint được công bố qua JMX khi hạ tầng đó hoạt động.

Cấu hình trên chủ đích không dùng wildcard `*` và không mở remote connector. Một số phiên bản Spring Boot có default exposure khác nhau; dùng cấu hình tường minh làm lab dễ quan sát hơn.

### 8.1. Hai domain JMX trong cùng JVM

Bạn sẽ có thể quan sát:

```text
company.demo
  type=TaskManagement, name=primary

company.actuator
  ... các endpoint Health/Info/Metrics theo ObjectName thực tế ...
```

`company.demo` là domain của custom MBean. `company.actuator` là domain mong muốn cho Actuator JMX endpoint qua property.

Domain chỉ là một phần của ObjectName; không phải một `MBeanServer` riêng. Cả hai có thể cùng đăng ký trong platform MBeanServer, nếu cấu hình Boot/exporter sử dụng server đó.

## 9. Khởi chạy ứng dụng

Với Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Hoặc build và chạy jar với đúng tên output:

```bash
./mvnw package
java -jar target/actuator-jmx-lab-0.0.1-SNAPSHOT.jar
```

Giữ process chạy để thực hành JConsole. Nếu chạy từ IDE hoặc Maven, có thể có nhiều Java process. Hãy chọn process chạy `ActuatorJmxApplication` chứ không chọn nhầm launcher.

Có thể kiểm tra HTTP:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/info
```

Kết quả có thể thay đổi theo `HealthIndicator`, `InfoContributor`, cấu hình security và dữ liệu ứng dụng. Một response HTTP thành công không tự chứng minh Actuator JMX đã được export; bước tiếp theo mới xác nhận điều đó.

## 10. Dùng JConsole quan sát custom MBean

Mở terminal khác:

```bash
jconsole
```

Trong giao diện:

1. Chọn Java process local của `ActuatorJmxApplication`.
2. Kết nối và mở tab **MBeans**.
3. Tìm domain **`company.demo`**.
4. Mở MBean tương ứng `type=TaskManagement,name=primary`.
5. Trong **Attributes**, xem `CompletedTasks`, `ActiveTasks`, `WarningThreshold`.
6. Trong **Operations**, tìm `resetCounters`.

Đầu tiên chỉ đọc attribute. Đừng gọi `resetCounters` khi đang dùng state quan trọng; bài lab có counter giả nên có thể gọi sau khi hiểu side effect.

Nếu không thấy MBean, kiểm tra process, property `spring.jmx.enabled`, component scan, hạ tầng exporter và `ObjectName`. Nếu thấy domain nhưng không có attribute mong muốn, kiểm tra annotation metadata và `MBeanInfo`.

## 11. Dùng JConsole quan sát Actuator MBeans

Trong cùng tab **MBeans**, tìm domain `company.actuator`. Dưới domain đó, các endpoint đã enable và expose qua JMX có thể xuất hiện dưới dạng MBean.

Với những endpoint thường dùng:

| Endpoint | Mục đích | Kiểu thao tác |
|---|---|---|
| Health | Xem trạng thái ứng dụng/dependencies | Read operation |
| Info | Thông tin mô tả về ứng dụng | Read operation |
| Metrics | Danh sách/từng metric được instrument | Read operations có thể có tham số |

Tên operation, chữ ký và cấu trúc output cần được xác nhận bằng JConsole hoặc `MBeanInfo`; chúng phụ thuộc hạ tầng export và phiên bản Boot. **Không giả định Health luôn là một JMX attribute tên `Status` hoặc operation `health()`**.

Actuator endpoint thường được thiết kế dưới dạng read/write/delete operations ở cấp endpoint, không nhất thiết theo JavaBeans getter conventions giống custom `@ManagedAttribute` của `TaskManagement`.

### 11.1. HTTP và JMX exposure là hai tập riêng

Đổi:

```properties
management.endpoints.web.exposure.include=health
management.endpoints.jmx.exposure.include=health,info,metrics
```

HTTP lúc này chỉ expose Health trong nhóm minh họa, còn JMX có thể expose thêm Info và Metrics nếu endpoint có sẵn và được enable.

Ngược lại, nếu HTTP expose Metrics nhưng JMX không expose nó, JConsole sẽ không tự thấy Metrics endpoint chỉ vì `/actuator/metrics` hoạt động.

## 12. Tạo request để thay đổi state quan sát

Để tạo dữ liệu quan sát, có thể thêm một controller đơn giản:

```java
package example.actuatorjmx;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping("/demo/tasks/start")
    public String start() {
        service.startTask();
        return "started";
    }

    @PostMapping("/demo/tasks/complete")
    public String complete() {
        service.completeTask();
        return "completed";
    }

    @GetMapping("/demo/tasks/summary")
    public String summary() {
        return "active=" + service.activeCount()
            + ", completed=" + service.completedCount();
    }
}
```

Các POST endpoints này **chỉ dành cho môi trường lab**. Trong production, không công bố thao tác thay đổi state mà không có authentication, authorization, validation và các kiểm soát khác. Mẫu code không thêm security chỉ để giữ ví dụ tập trung vào JMX/Actuator.

Chạy:

```bash
curl -X POST http://localhost:8080/demo/tasks/start
curl -X POST http://localhost:8080/demo/tasks/complete
curl http://localhost:8080/demo/tasks/summary
```

Sau đó quay lại JConsole và đọc `ActiveTasks`/`CompletedTasks`. Các số liệu thay đổi theo `TaskService`, chứng minh custom MBean đang phản ánh đúng state trong ứng dụng.

## 13. Kiểm tra bằng Java MBeanServer API

Nếu JConsole không phù hợp với môi trường headless, tạo một bean chẩn đoán chạy sau khởi động:

```java
package example.actuatorjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxInspectionConfiguration {

    @Bean
    ApplicationRunner inspectMBeans() {
        return args -> {
            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            for (ObjectName name : server.queryNames(
                    new ObjectName("company.*:*"), null)) {
                System.out.println("MBean: " + name);

                MBeanInfo info = server.getMBeanInfo(name);
                System.out.println(
                    "  attributes=" + info.getAttributes().length
                    + ", operations=" + info.getOperations().length
                );
            }
        };
    }
}
```

Đoạn code chỉ đọc metadata, không gọi operation có tác dụng phụ. Nó dùng platform MBeanServer trong JVM hiện tại. Nếu ứng dụng được cấu hình để export vào MBeanServer khác, cần inject và truy vấn đúng server thay vì cố dùng platform server.

Không nên log tất cả attribute values để debug, bởi getter có thể trả dữ liệu nhạy cảm hoặc thực hiện tác vụ tốn tài nguyên.

### 13.1. Kiểm tra ObjectName cụ thể

```java
ObjectName taskName = new ObjectName(
    "company.demo:type=TaskManagement,name=primary"
);

boolean registered = server.isRegistered(taskName);
System.out.println("Custom MBean registered=" + registered);

if (registered) {
    System.out.println(
        "ActiveTasks=" +
        server.getAttribute(taskName, "ActiveTasks")
    );
}
```

Đây là phép kiểm tra mạnh hơn việc chỉ thấy bean `TaskManagement` trong Spring context: nó xác minh JMX registry và đường đọc attribute thực sự hoạt động.

## 14. Thêm Micrometer Counter để quan sát qua Actuator Metrics

Trong ví dụ cơ bản, các giá trị `TaskService` chỉ được xuất qua custom JMX MBean. Nếu muốn Actuator Metrics biết số task đã hoàn tất, cần instrument chúng vào `MeterRegistry`.

Thêm vào `TaskService`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

@Service
public class TaskService {
    private final Counter completedMeter;
    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();

    public TaskService(MeterRegistry registry) {
        this.completedMeter = registry.counter(
            "demo.tasks.completed",
            "component", "task-service"
        );
    }

    public void completeTask() {
        active.updateAndGet(n -> Math.max(0, n - 1));
        completed.incrementAndGet();
        completedMeter.increment();
    }

    // Các method còn lại tương tự phần trước.
}
```

Đoạn code là phần thay đổi vào class `TaskService`, **không phải một class thứ hai để copy nguyên song song**. Khi áp dụng, giữ các field và method cũ, bổ sung constructor nhận `MeterRegistry`, `Counter` và cập nhật `completeTask`.

Vì `spring-boot-starter-actuator` thường mang hạ tầng Micrometer trong các phiên bản Boot hiện đại, một `MeterRegistry` có thể được auto-configure. Nếu ứng dụng có nhiều registry hoặc auto-configuration bị tùy chỉnh, injection phải phù hợp với cấu hình thực tế.

Sau khi có event, thử:

```bash
curl http://localhost:8080/actuator/metrics/demo.tasks.completed
```

Response phụ thuộc metric name/tags, exposure web và security. Có thể dùng Actuator Metrics MBean trong JConsole để khám phá cùng metric nếu endpoint được expose qua JMX.

### 14.1. Tránh hiểu nhầm JMX attribute thành Micrometer meter

`getCompletedTasks()` xuất qua custom MBean **không tự tạo** một meter tên `demo.tasks.completed` trong Micrometer. Vì vậy chỉ có `@ManagedAttribute` chưa đủ để `/actuator/metrics/demo.tasks.completed` trả dữ liệu.

Trong lab này, counter được tạo bởi `registry.counter(...)`, còn JMX attribute được tạo bởi `@ManagedAttribute`. Hai đường cùng phản ánh sự kiện nhưng có cơ chế export khác nhau.

Nếu dùng JMX collector bên ngoài để scrape `CompletedTasks` và đồng thời xuất Counter Micrometer, cần tránh tạo hai metric trùng semantics rồi cộng chúng trong dashboard.

## 15. Thực hành custom Actuator endpoint

Ngoài custom Spring JMX MBean, có thể tạo Actuator endpoint tùy chỉnh:

```java
package example.actuatorjmx;

import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "taskSummary")
public class TaskSummaryEndpoint {
    private final TaskService service;

    public TaskSummaryEndpoint(TaskService service) {
        this.service = service;
    }

    @ReadOperation
    public Map<String, Object> summary() {
        return Map.of(
            "active", service.activeCount(),
            "completed", service.completedCount()
        );
    }
}
```

Thêm `taskSummary` vào exposure:

```properties
management.endpoints.web.exposure.include=health,info,metrics,taskSummary
management.endpoints.jmx.exposure.include=health,info,metrics,taskSummary
```

Khi endpoint đã được nhận diện và enable theo cơ chế Actuator của phiên bản Boot đang dùng, có thể thử HTTP endpoint tương ứng và tìm Actuator JMX MBean của `taskSummary`.

Một số phiên bản Actuator chuẩn hóa endpoint ID và path theo quy tắc riêng; hãy xác minh endpoint ID/path thực tế từ ứng dụng, không suy đoán chữ hoa/thường.

### 15.1. So sánh ba kênh quan sát

Cùng state `TaskService` có thể xuất hiện theo ba cách:

```text
TaskService.completedCount()
   |
   +--> @ManagedAttribute -> custom MBean "CompletedTasks"
   |
   +--> @ReadOperation    -> Actuator endpoint "taskSummary"
   |
   +--> MeterRegistry    -> "demo.tasks.completed" Counter
```

Kết quả trong test nên phản ánh cùng sự kiện, nhưng hình dạng dữ liệu và thời điểm đọc có thể khác nhau. Counter là cumulative metric, custom MBean trả số tức thời, Actuator endpoint trả object/read operation. Không giả định các client luôn lấy snapshot đồng thời.

## 16. Kiểm tra JMX exposure bằng MBeanInfo

Khi thấy custom hoặc Actuator MBean, có thể đọc metadata:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(taskName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTR %s readable=%s writable=%s type=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP " + operation.getName());
}
```

Với custom `TaskManagement`, kỳ vọng metadata có các attribute `CompletedTasks`, `ActiveTasks`, `WarningThreshold` và operation `resetCounters` khi exporter annotation hoạt động đúng.

Với Actuator endpoint, metadata có thể chủ yếu thể hiện operations ứng với endpoint read/write operations; không suy đoán tất cả property đều xuất thành JMX attribute theo JavaBeans convention.

Kiểm tra metadata không gọi operation nên là bước đầu phù hợp khi làm việc trên process thật.

## 17. Kiểm thử integration cho custom MBean

Một test có thể dùng `@SpringBootTest` để khởi chạy context ở môi trường test, bật JMX và assert ObjectName.

```java
package example.actuatorjmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    properties = {
        "spring.jmx.enabled=true",
        "management.endpoints.jmx.exposure.include=health,info"
    }
)
class TaskManagementJmxTest {

    @Autowired
    MBeanServer mbeanServer;

    @Test
    void customMBeanIsRegistered() throws Exception {
        ObjectName name = new ObjectName(
            "company.demo:type=TaskManagement,name=primary"
        );

        assertTrue(mbeanServer.isRegistered(name));
        assertNotNull(
            mbeanServer.getMBeanInfo(name)
        );
    }
}
```

Trong test project, cần đảm bảo có một bean `MBeanServer` được inject đúng với exporter thực tế; nếu không có bean theo cấu hình Boot đang dùng, có thể dùng `ManagementFactory.getPlatformMBeanServer()` trong test hoặc tự cấu hình server. Không mặc định `@Autowired MBeanServer` sẽ hoạt động ở mọi phiên bản/cấu hình.

Spring Test Context có thể cache context; nếu các test cùng dùng platform MBeanServer và ObjectName giống nhau, cần xem xét xung đột khi chạy song song. Với test metadata cô lập, một `MBeanServerFactory.createMBeanServer(...)` riêng thường cho kết quả dễ kiểm soát hơn.

## 18. Actuator Health và JMX Health có cùng ngữ nghĩa không?

Actuator Health phản ánh tập `HealthIndicator` và chính sách tổng hợp/hiển thị health đang được cấu hình. Cùng một endpoint logic có thể được truy cập qua HTTP hoặc JMX, nhưng cấu trúc output, mức chi tiết và quyền truy cập có thể phụ thuộc transport/security/version.

Không dùng một custom MBean `getState() == "READY"` làm thay thế hoàn toàn cho Actuator Health nếu health còn cần kiểm tra database, disk, broker hoặc hệ thống ngoài.

Ngược lại, nếu cần một trạng thái domain-specific nhỏ như `TaskServicePaused`, custom MBean/Actuator custom endpoint có thể phù hợp hơn việc đặt mọi trạng thái vào global health.

Một thiết kế rõ ràng:

- Health: ứng dụng sẵn sàng/liveness hoặc trạng thái dependency phù hợp.
- Metrics: dữ liệu đo đạc theo thời gian.
- Custom MBean: thuộc tính/operation quản trị được giới hạn.
- Custom Actuator endpoint: API vận hành có contract rõ qua transport đã cấu hình.

## 19. Bảo mật: không coi local lab là cấu hình production

Lab này có operation `resetCounters()` và POST endpoints mô phỏng, nên chỉ được dùng trong môi trường thử nghiệm cô lập.

Trong production:

1. Chỉ expose Actuator endpoints cần thiết qua HTTP/JMX.
2. Không dùng wildcard `management.endpoints.*.exposure.include=*` mà không có review.
3. Bảo vệ HTTP management endpoints bằng authentication, authorization và network policy.
4. Với remote JMX, cần authentication, TLS hoặc kênh bảo vệ, firewall và quyền hạn.
5. Không export API key, password, token, raw configuration hoặc dữ liệu người dùng qua MBean/Actuator.
6. Giới hạn writable attributes và operations có side effect.
7. Ghi audit cho thao tác quản trị quan trọng.
8. Hạn chế quyền của tài khoản monitoring; read-only metrics không cần quyền reset/restart.
9. Không mở RMI/JMX port ra public Internet.
10. Kiểm tra metadata và exposure sau mỗi dependency/Boot upgrade.

**Spring Security HTTP không tự đồng nghĩa JMX connector đã có cùng access policy.** Hai kênh truy cập cần được bảo vệ riêng.

## 20. Chẩn đoán khi không thấy custom MBean

### 20.1. spring.jmx.enabled chưa có hiệu lực

Kiểm tra property theo profile, environment, command-line argument và version Spring Boot. Một file `application.properties` đúng không bảo đảm nó không bị nguồn cấu hình ưu tiên cao hơn override.

### 20.2. TaskManagement không phải Spring bean

Nếu class nằm ngoài component scan hoặc thiếu `@Component`/`@Bean`, annotation JMX không có tác dụng trong context mong muốn.

### 20.3. Không có exporter metadata phù hợp

Cần `AnnotationMBeanExporter` hoặc hạ tầng tương đương để xử lý `@ManagedResource`. Kiểm tra exporter beans đã khởi tạo thay vì chỉ thấy annotation trong source.

### 20.4. ObjectName không như dự đoán

Dùng `queryNames(new ObjectName("company.demo:*"), null)` để lấy tên thật. Naming strategy hoặc explicit mapping có thể khác annotation mong muốn.

### 20.5. Duplicate ObjectName

Hai exporter/context cùng đăng ký một tên có thể gây collision. Không khắc phục bằng cách tự động `REPLACE_EXISTING` nếu chưa xác định ownership.

### 20.6. JConsole kết nối nhầm JVM

Maven, IDE và ứng dụng có thể cùng chạy nhiều Java process. Đối chiếu PID/main class và chọn đúng JVM.

### 20.7. JConsole đang xem MBeanServer khác

Platform server là lựa chọn phổ biến cho JConsole local. Nếu ứng dụng tạo MBeanServer riêng, custom MBean có thể không nằm trong registry mà JConsole hiển thị.

## 21. Chẩn đoán khi Actuator MBean không xuất hiện

Các nguyên nhân khác với custom MBean:

- Chưa thêm `spring-boot-starter-actuator`.
- Endpoint chưa được enable hoặc không được tạo theo classpath/conditions.
- `management.endpoints.jmx.exposure.include` không chứa endpoint tương ứng.
- Có `management.endpoints.jmx.exposure.exclude` loại endpoint.
- `spring.jmx.enabled` chưa bật/không hiệu lực.
- Domain JMX khác cấu hình dự kiến.
- MBeanServer hoặc exporter khác với dự kiến.
- Actuator version có thay đổi về endpoint availability/naming.

Nếu `/actuator/health` chạy nhưng JConsole không thấy Health, đừng kết luận Actuator bị lỗi. Hãy xác nhận exposure JMX độc lập, đúng MBeanServer và metadata thực tế.

## 22. Chẩn đoán khi Actuator Metrics không thấy custom counter

`@ManagedAttribute` trên `TaskManagement` không tự tạo Micrometer meter. Chỉ khi có code instrument qua `MeterRegistry` hoặc collector chuyên đọc JMX, metrics backend mới nhận dữ liệu tương ứng.

Kiểm tra:

1. Có `MeterRegistry` phù hợp trong context không?
2. Code có gọi `registry.counter("demo.tasks.completed", ...)` không?
3. Có sự kiện làm counter tăng chưa?
4. Endpoint Metrics được enable và expose qua HTTP/JMX chưa?
5. Metric name và tags đã nhập đúng chưa?
6. Nếu dùng Prometheus, có registry dependency và endpoint scrape chưa?
7. Có duplicate metric do JMX collector và Micrometer cùng đo không?

MBean metadata, Actuator endpoint và Micrometer registry cần được kiểm tra như ba lớp bổ sung, không coi một lớp tự chứng minh lớp còn lại hoạt động.

## 23. Bài thực hành mở rộng

### Bài 1 — Đọc custom attribute từ JConsole

Tạo hai task start và một task complete. Đọc `ActiveTasks`, `CompletedTasks` trong JConsole và đối chiếu với `/demo/tasks/summary`.

### Bài 2 — Đổi writable attribute

Trong môi trường lab, đặt `WarningThreshold=25` qua JConsole. Sau đó dùng Java JMX API hoặc bean getter để xác nhận giá trị. Thử số ngoài phạm vi và quan sát validation error.

### Bài 3 — Gọi operation có side effect

Đọc counters trước, gọi `resetCounters()` trong JConsole và đọc lại. Giải thích vì sao operation này không nên được trao quyền cho mọi monitoring client.

### Bài 4 — Web/JMX exposure khác nhau

Cấu hình HTTP chỉ expose `health`, JMX expose `health,info,metrics`. So sánh `curl` và JConsole để chứng minh hai transport độc lập.

### Bài 5 — Custom Actuator endpoint

Tạo `TaskSummaryEndpoint` với `@ReadOperation`. Expose qua HTTP/JMX và so sánh output với custom MBean `TaskManagement`.

### Bài 6 — Custom metric

Đăng ký `demo.tasks.completed` trong Micrometer, thực hiện tác vụ rồi tra cứu `/actuator/metrics/demo.tasks.completed` và JMX Metrics endpoint nếu có.

### Bài 7 — Exporter trùng

Trong test riêng, tạo hai exporter muốn đăng ký `company.demo:type=TaskManagement,name=primary`. Quan sát lỗi collision và giải thích vai trò của `RegistrationPolicy`.

### Bài 8 — Cấu hình nhiều context

Tạo root và child contexts với các exporter khác nhau. Xác định MBeanServer chung, ObjectName được đăng ký và tránh trùng registration.

### Bài 9 — Quan sát khi chạy headless

Không dùng JConsole GUI, thay bằng `ApplicationRunner` gọi `queryNames` và `getMBeanInfo`. Chỉ in metadata an toàn.

### Bài 10 — Security review

Liệt kê Actuator endpoints được expose, custom MBean attributes và operations. Xác định thành phần nào read-only, thành phần nào cần quyền quản trị và cách bảo vệ từng transport.

## 24. Checklist hoàn thành lab

- [ ] Ứng dụng Spring Boot đã khởi chạy.
- [ ] Có dependency Actuator.
- [ ] `spring.jmx.enabled` hiệu lực đúng.
- [ ] Custom bean `TaskManagement` nằm trong ApplicationContext.
- [ ] Custom MBean được đăng ký với ObjectName dự kiến.
- [ ] JConsole kết nối đúng JVM.
- [ ] Các attribute của custom MBean đọc được.
- [ ] Actuator Health/Info/Metrics MBeans xuất hiện nếu được enable và expose.
- [ ] HTTP exposure khác JMX exposure theo cấu hình đã thử.
- [ ] Custom Micrometer counter xuất hiện sau instrumentation.
- [ ] Không cần remote JMX không an toàn.
- [ ] Không để operation có side effect được công bố ngoài phạm vi lab.

Đây là danh sách hoạt động dành cho người học, không phải trạng thái kiểm định đã được thực hiện cho một môi trường cụ thể.

## 25. Câu hỏi tự kiểm tra

1. `@ManagedResource` và `@Endpoint` khác nhau thế nào?
2. `spring.jmx.enabled` có tự đồng nghĩa với expose mọi Actuator endpoint không?
3. Vì sao phải dùng `management.endpoints.jmx.exposure.include` riêng?
4. `TaskManagement` cần những điều kiện nào để được đăng ký như custom MBean?
5. JConsole nhìn thấy MBean từ đâu?
6. Vì sao `/actuator/health` hoạt động không bảo đảm Health xuất hiện qua JMX?
7. `@ManagedAttribute` có tự tạo Micrometer counter không?
8. `MBeanInfo` giúp xác nhận metadata nào?
9. Tại sao hai exporter có thể xung đột ObjectName?
10. Khi nào nên dùng custom Actuator endpoint thay vì custom MBean?
11. Những security controls nào cần có nếu bật remote JMX?
12. Làm sao kiểm tra tích hợp trong môi trường headless?

## 26. Tổng kết

**Kết hợp JMX với Spring Boot Actuator cho phép ứng dụng có cả custom management MBeans và những endpoint quan sát chuẩn của Actuator trong cùng JVM.** Các thành phần có thể dùng chung MBeanServer nhưng có cơ chế khai báo, exposure và metadata khác nhau.

Trong bài thực hành, hãy cấu hình `spring.jmx.enabled` rõ ràng, chọn Actuator JMX exposure theo allowlist, tạo `@ManagedResource` bean an toàn, dùng JConsole hoặc `MBeanServer` để xác minh đăng ký thực tế và so sánh với HTTP Actuator. Khi thêm Micrometer, instrument meter riêng thay vì giả định custom MBean tự sinh metric.

Trong môi trường vận hành, giữ hai nguyên tắc: **chỉ export dữ liệu và operation cần thiết**, và **bảo vệ từng đường truy cập HTTP/JMX theo mô hình quyền phù hợp**.
