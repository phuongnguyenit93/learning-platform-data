# Kiểm thử bean có metadata JMX trong ApplicationContext

## 1. Mục tiêu: kiểm thử cấu hình JMX thực sự có hiệu lực

Trong Spring Framework, một bean có thể được gắn `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation` để tạo giao diện quản trị JMX. Tuy nhiên, chỉ kiểm tra annotation trong source code chưa chứng minh rằng:

- Bean đã được đăng ký trong `ApplicationContext`.
- Hạ tầng `MBeanExporter` hoặc `AnnotationMBeanExporter` đang hoạt động.
- MBean được đăng ký với đúng `ObjectName`.
- `MBeanInfo` phản ánh đúng các attribute và operation dự kiến.
- Getter/setter/operation thực sự chạy qua giao diện JMX.
- Các method nội bộ không bị xuất nhầm.
- Context đóng xong không để lại registration gây ảnh hưởng test tiếp theo.

Bài này hướng dẫn viết kiểm thử tự động cho **bean có metadata JMX trong Spring context**, tập trung vào hợp đồng quản trị đã được công bố và hành vi thực tế. Ta sẽ dùng một `ApplicationContext` nhỏ, MBeanServer cô lập, JUnit 5 và những JMX API tiêu chuẩn.

**Tư duy cốt lõi:** Kiểm thử bean tồn tại trong Spring và kiểm thử MBean tồn tại trong JMX là hai phép kiểm tra khác nhau. Cả hai cần được đối chiếu nếu mục tiêu là xác nhận cấu hình JMX hiệu lực.

## 2. Mô hình kiểm thử theo từng lớp

```text
            JUnit test
                |
       tạo Spring ApplicationContext
                |
        +-------+-------+
        |               |
     Managed bean   MBeanExporter
        |               |
        +-------+-------+
                |
           MBeanServer
                |
          ObjectName lookup
                |
              MBeanInfo
                |
       +--------+--------+
       |                 |
  Attribute access   Operation invoke
       |                 |
       +--------+--------+
                |
          Assertions
```

Một bộ test đầy đủ có thể có những tầng:

| Tầng | Điều cần xác minh | API gợi ý |
|---|---|---|
| Spring context | Bean quản trị có mặt | `containsBean`, `getBean` |
| Export infrastructure | Exporter được khởi tạo | `getBeansOfType(MBeanExporter.class)` |
| Registration | ObjectName tồn tại | `MBeanServer.isRegistered` |
| Metadata | Attribute/operation đúng hợp đồng | `getMBeanInfo` |
| Attribute behavior | Getter/setter chạy qua JMX | `getAttribute`, `setAttribute` |
| Operation behavior | Method quản trị hoạt động | `invoke` |
| Negative test | Method nội bộ không bị export | Kiểm tra danh sách `MBeanInfo` |
| Lifecycle | Không để MBean rác sau test | `context.close()`, `isRegistered` |

Không cần kiểm thử một lượt thật lớn trong một test method. Có thể tách các nhóm assertion nhưng dùng chung setup có lifecycle rõ ràng.

## 3. Phân biệt metadata ở source và metadata trong MBeanServer

Annotation là **ý định cấu hình**:

```java
@ManagedResource(objectName = "lab.test:type=JobMonitor")
public class JobMonitor {

    @ManagedAttribute
    public int getActiveJobs() {
        return 3;
    }

    @ManagedOperation
    public void reset() {
        // ...
    }
}
```

Nhưng JMX client không truy cập annotation trực tiếp. Nó nhìn thấy metadata từ `MBeanInfo` do exporter và MBeanServer cung cấp.

```text
Java annotation
      |
Spring metadata source / assembler
      |
MBeanExporter / ModelMBean
      |
MBeanServer
      |
MBeanInfo
      |
JMX client
```

Có thể đọc annotation bằng reflection trong unit test, nhưng đó không thay thế integration test qua MBeanServer. Những yếu tố như component scan, bean profiles, ObjectName, assembler, proxy và registration policy đều có thể làm metadata hiệu lực khác với dự đoán từ source.

Ngược lại, kiểm thử MBeanServer cũng không có nghĩa test tất cả logic nghiệp vụ. Ta chỉ cần xác nhận đường quản trị thực sự hoạt động và phạm vi công bố đúng.

## 4. Chuẩn bị dependency

Ví dụ dùng Maven với Spring Context và JUnit Jupiter. Phiên bản được quản lý bằng BOM hoặc dependency management của dự án.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu dự án không dùng parent/BOM quản lý version, hãy khai báo các phiên bản tương thích. Spring Framework 6+ sử dụng Jakarta annotations khi cần `@PostConstruct`, nhưng bài này không phụ thuộc `@PostConstruct`.

Với dự án Spring Boot, `spring-boot-starter-test` có thể cung cấp JUnit Jupiter và Spring testing utilities. Không bắt buộc khởi động toàn bộ web server chỉ để kiểm tra JMX metadata; một `AnnotationConfigApplicationContext` nhỏ thường đơn giản và nhanh hơn.

Không cần mở remote JMX hoặc khởi chạy JConsole trong automated tests. Kiểm tra tại MBeanServer local là đủ để xác nhận registration, metadata và hành vi JMX.

## 5. Xây dựng bean quản trị dùng cho test

Tạo `JobMonitor.java`:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "lab.test:type=JobMonitor,name=primary",
    description = "Job management test fixture"
)
public class JobMonitor {

    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();
    private volatile int warningThreshold = 10;

    @ManagedAttribute(description = "Completed jobs")
    public long getCompletedJobs() {
        return completed.get();
    }

    @ManagedAttribute(description = "Active jobs")
    public int getActiveJobs() {
        return active.get();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute(description = "Change warning threshold")
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException(
                "warningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = value;
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        completed.set(0);
        active.set(0);
    }

    // Nội bộ, không phải JMX operation.
    public void recordCompletedJob() {
        completed.incrementAndGet();
    }

    public void startJob() {
        active.incrementAndGet();
    }
}
```

Các method quản trị được chọn bằng annotation. `recordCompletedJob()` và `startJob()` không được đánh dấu; khi dùng annotation metadata assembler thích hợp, chúng không nên xuất hiện trong JMX operations.

Một class không cần `@Component` nếu test tạo nó bằng `@Bean`. Điều này giúp cấu hình fixture rõ ràng và tránh quét thêm bean ngoài phạm vi test.

## 6. Tạo MBeanServer riêng cho test

Platform MBeanServer là tài nguyên chung của JVM:

```java
ManagementFactory.getPlatformMBeanServer();
```

Nếu nhiều test dùng cùng ObjectName trên platform server, chúng có thể va chạm dù mỗi test tạo ApplicationContext mới. Đối với test metadata, nên dùng **MBeanServer cô lập**:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("jmx-test");
```

Sau test, đóng Spring context để exporter unregister những MBean nó sở hữu, và release server test khi không còn dùng:

```java
MBeanServerFactory.releaseMBeanServer(server);
```

Các import:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
```

Nếu một số test khác cần platform MXBeans, nên tạo JVM test riêng hoặc dùng ObjectName độc nhất với cleanup chắc chắn. Không tự động xóa những MBean có sẵn trên platform server của thư viện hoặc JDK.

**MBeanServer riêng không phải phiên bản mô phỏng giả:** nó vẫn tuân theo JMX API, có registration, metadata và lời gọi thực. Nó chỉ giúp cô lập registry khỏi các MBean khác trong cùng JVM.

## 7. Cấu hình ApplicationContext kiểm thử

Tạo `JmxTestConfiguration.java`:

```java
package example.jmx;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxTestConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer mbeanServer) {

        AnnotationMBeanExporter exporter =
            new AnnotationMBeanExporter();

        exporter.setServer(mbeanServer);
        return exporter;
    }
}
```

Test cung cấp `MBeanServer` được tạo riêng vào context trước `refresh()`, ví dụ bằng `registerBean`. Khi context được refresh, exporter sẽ phát hiện metadata `@ManagedResource` và đăng ký MBean tương ứng.

Vì ở đây chủ động khai báo `AnnotationMBeanExporter`, không bật thêm `@EnableMBeanExport` trong test fixture nếu nó tạo một exporter thứ hai có thể đụng ObjectName. Tương tự, không trộn cả Spring Boot auto-configuration vào một test hẹp mà không có mục đích.

Một cách tổ chức khác là tạo `MBeanExporter` với `MetadataMBeanInfoAssembler` được cấu hình tường minh. Mục tiêu vẫn là chạy chính cơ chế metadata mà ứng dụng sử dụng, không chỉ tạo bean thuần.

## 8. Thiết lập lifecycle trong JUnit 5

Ví dụ một test class:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JobMonitorJmxTest {

    private static final String JMX_NAME =
        "lab.test:type=JobMonitor,name=primary";

    private MBeanServer server;
    private AnnotationConfigApplicationContext context;
    private ObjectName objectName;

    @BeforeEach
    void startContext() throws Exception {
        server = MBeanServerFactory.createMBeanServer("jmx-test");
        objectName = new ObjectName(JMX_NAME);

        context = new AnnotationConfigApplicationContext();

        // Register singleton server để @Bean exporter inject đúng.
        context.getBeanFactory().registerSingleton(
            "testMBeanServer", server
        );
        context.register(JmxTestConfiguration.class);
        context.refresh();
    }

    @AfterEach
    void stopContext() {
        try {
            if (context != null) {
                context.close();
            }
        } finally {
            if (server != null) {
                MBeanServerFactory.releaseMBeanServer(server);
            }
        }
    }
}
```

Mỗi test method được cấp một context và MBeanServer mới. Việc close context diễn ra trước khi release server để exporter có cơ hội unregister MBean do nó quản lý.

Nếu startup ném exception trong `@BeforeEach`, JUnit vẫn gọi `@AfterEach` theo lifecycle bình thường, nhưng vẫn nên thiết kế cleanup chịu được context chưa hoàn thành khởi tạo. Với hệ thống test phức tạp, có thể gói setup bằng `try/finally` trong helper để quản lý lỗi giữa chừng chắc chắn hơn.

## 9. Test 1: bean tồn tại trong ApplicationContext

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

@Test
void springContextContainsManagedBean() {
    assertTrue(context.containsBean("jobMonitor"));

    JobMonitor bean = context.getBean(JobMonitor.class);
    assertNotNull(bean);
}
```

Test này xác minh cấu hình Spring đã tạo bean. Nó **không chứng minh** MBean được đăng ký. Một ứng dụng có thể có `JobMonitor` trong context nhưng exporter thiếu hoặc hoạt động không đúng.

Nếu test không tìm được bean, kiểm tra `@Bean`, component scan, profile/conditional configuration và import. Không vội thay đổi JMX ObjectName vì vấn đề có thể nằm hoàn toàn ở Spring bean registration.

## 10. Test 2: exporter đã có trong context

```java
import org.springframework.jmx.export.MBeanExporter;

@Test
void contextContainsMBeanExporter() {
    var exporters =
        context.getBeansOfType(MBeanExporter.class);

    assertFalse(exporters.isEmpty());
}
```

Vì `AnnotationMBeanExporter` kế thừa `MBeanExporter`, phép tìm type này có thể tìm thấy exporter annotation đang được sử dụng.

Nếu test yêu cầu **đúng một exporter**, có thể assert count bằng một. Nhưng phải hiểu phạm vi test: trong ứng dụng thật có thể có nhiều exporter hợp lệ cho các nhóm MBean khác nhau. Đừng biến giả định đơn giản của fixture thành quy tắc tuyệt đối cho mọi ứng dụng.

Kiểm thử integration trên cấu hình production-like có thể cần kiểm kê thêm exporter của parent/child ApplicationContext hoặc auto-configuration. Một `getBeansOfType` trong một context không tự động tìm mọi exporter của context độc lập khác trong JVM.

## 11. Test 3: MBean đã đăng ký đúng ObjectName

```java
@Test
void mbeanIsRegistered() {
    assertTrue(server.isRegistered(objectName));
}
```

Đây là bước nối giữa Spring và JMX. Nó xác minh ObjectName tồn tại trong **MBeanServer đang được test sử dụng**.

Nhưng một registration đã tồn tại cũng chưa chứng minh toàn bộ attribute/operation đúng. Khi có nhiều exporter dùng chung MBeanServer, một MBean khác có thể chiếm tên; test cô lập bằng server riêng giúp giảm nguy cơ này.

Có thể kiểm tra thêm:

```java
Set<ObjectName> names = server.queryNames(
    new ObjectName("lab.test:*"), null
);
assertTrue(names.contains(objectName));
```

Danh sách từ `queryNames` không có thứ tự bảo đảm. Nếu cần so sánh số lượng hoặc tập tên, dùng `Set`.

## 12. Test 4: metadata attribute đúng quyền đọc/ghi

Đọc `MBeanInfo`:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

@Test
void expectedAttributesAreExposed() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    Map<String, MBeanAttributeInfo> attributes =
        java.util.Arrays.stream(info.getAttributes())
            .collect(java.util.stream.Collectors.toMap(
                MBeanAttributeInfo::getName,
                attribute -> attribute
            ));

    MBeanAttributeInfo completed = attributes.get("CompletedJobs");
    assertNotNull(completed);
    assertTrue(completed.isReadable());
    assertFalse(completed.isWritable());

    MBeanAttributeInfo warning = attributes.get("WarningThreshold");
    assertNotNull(warning);
    assertTrue(warning.isReadable());
    assertTrue(warning.isWritable());

    assertEquals("int", warning.getType());
}
```

Bài kiểm tra này xem hợp đồng mà JMX client thấy:

- `CompletedJobs`: chỉ đọc vì không có setter được export.
- `WarningThreshold`: đọc–ghi vì có getter và setter phù hợp.
- Type của `WarningThreshold` là kiểu primitive `int` trong metadata của hợp đồng này.

Nếu `getWarningThreshold()` có annotation nhưng `setWarningThreshold(...)` không được export theo cấu hình, thuộc tính có thể không writable như mong đợi. Đó là lý do phải kiểm tra metadata thực tế.

Đừng dùng kết quả `server.getAttribute(...)` một lần để suy ra quyền ghi; cần đọc `MBeanAttributeInfo.isWritable()`.

## 13. Test 5: operation quản trị được công bố

```java
import javax.management.MBeanOperationInfo;

@Test
void resetOperationIsExposed() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    boolean found =
        java.util.Arrays.stream(info.getOperations())
            .map(MBeanOperationInfo::getName)
            .anyMatch("resetCounters"::equals);

    assertTrue(found);
}
```

Một operation được export không có nghĩa nên gọi nó trong production. Trong test fixture riêng, `resetCounters()` là hành động có tác dụng phụ nhưng đã được kiểm soát.

Khi method có tham số, metadata `MBeanOperationInfo.getSignature()` cung cấp kiểu tham số. Kiểm tra cả signature, không chỉ tên nếu có overloaded methods. Nếu target dùng ModelMBean hoặc MXBean mapping, contract có thể khác biệt; hãy viết assertion theo metadata dự kiến của cơ chế export đang dùng.

## 14. Test 6: method nội bộ không bị export

Một mục tiêu bảo mật quan trọng là chứng minh các method ngoài management contract không thể gọi qua JMX:

```java
@Test
void internalMethodsAreNotJmxOperations() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    Set<String> operations =
        java.util.Arrays.stream(info.getOperations())
            .map(MBeanOperationInfo::getName)
            .collect(java.util.stream.Collectors.toSet());

    assertFalse(operations.contains("recordCompletedJob"));
    assertFalse(operations.contains("startJob"));
}
```

Đây là kiểm tra **negative contract**. Khi một developer bổ sung method public vào implementation, nó không nên tự thành một JMX operation chỉ vì exporter dùng reflective assembler quá rộng.

Với một môi trường có nhu cầu kiểm soát mạnh, có thể assert toàn bộ tập operation được phép, không chỉ vài method bị cấm. Ví dụ, chỉ `resetCounters` được phơi bày trong fixture. Tuy nhiên, cần hiểu MBeanInfo có thể trình bày accessor theo convention riêng của assembler; tập assertion phải phản ánh contract thực sự của phiên bản Spring sử dụng.

## 15. Test 7: đọc attribute qua JMX

Sau khi xác nhận metadata, thực hiện một lời gọi thực:

```java
@Test
void canReadAttributeThroughJmx() throws Exception {
    JobMonitor target = context.getBean(JobMonitor.class);

    target.recordCompletedJob();
    target.recordCompletedJob();

    Object count = server.getAttribute(
        objectName, "CompletedJobs"
    );

    assertEquals(2L, count);
}
```

Test này khác với `target.getCompletedJobs()`: nó đi qua `MBeanServer` và ObjectName, chứng minh đường truy cập JMX hoạt động.

Cần tránh đọc mọi attribute theo danh sách tự động trong môi trường production. Getter có thể có side effect, có thể thực hiện thao tác network hoặc trả dữ liệu nhạy cảm. Trong test fixture, ta chọn attribute số đếm đơn giản và an toàn.

## 16. Test 8: ghi attribute hợp lệ và không hợp lệ

```java
import javax.management.Attribute;

@Test
void writableAttributeDelegatesToBean() throws Exception {
    server.setAttribute(
        objectName,
        new Attribute("WarningThreshold", 20)
    );

    JobMonitor target = context.getBean(JobMonitor.class);

    assertEquals(20, target.getWarningThreshold());
    assertEquals(
        20,
        server.getAttribute(objectName, "WarningThreshold")
    );
}
```

Setter phải được export và metadata phải writable.

Kiểm thử validation:

```java
@Test
void invalidThresholdIsRejected() {
    assertThrows(Exception.class, () ->
        server.setAttribute(
            objectName,
            new Attribute("WarningThreshold", -1)
        )
    );
}
```

Ví dụ dùng `Exception.class` để minh họa rằng JMX có thể bọc exception từ setter trong một exception khác. Khi cần test chính xác, hãy kiểm tra loại exception thực tế của Spring/JMX version dùng trong dự án, `cause` và message liên quan; tránh assert một loại wrapper chưa được xác minh.

Quan trọng: việc setter từ chối input không nên làm thay đổi giá trị cấu hình đã có. Có thể assert `WarningThreshold` giữ nguyên sau test invalid.

## 17. Test 9: gọi operation qua MBeanServer

```java
@Test
void operationIsInvokable() throws Exception {
    JobMonitor target = context.getBean(JobMonitor.class);
    target.recordCompletedJob();

    Object result = server.invoke(
        objectName,
        "resetCounters",
        new Object[0],
        new String[0]
    );

    assertEquals(0L, target.getCompletedJobs());
}
```

Vì `resetCounters()` trả `void`, kết quả `invoke` có thể là `null`; điều quan trọng là side effect đã xảy ra.

Nếu một operation có tham số:

```java
server.invoke(
    objectName,
    "setMode",
    new Object[]{"PAUSED"},
    new String[]{String.class.getName()}
);
```

thì `setMode` phải được export như operation có chữ ký phù hợp. Không coi mọi Java setter là operation có thể invoke tùy ý; property setter thường được gọi qua `setAttribute`.

Trong production, không gọi operation nguy hiểm chỉ để kiểm tra JMX configuration. Dùng môi trường test với dữ liệu giả.

## 18. Test lifecycle: context close và unregister

Sau khi `ApplicationContext` đóng, exporter chịu trách nhiệm gỡ những MBean mà nó quản lý. Một kiểm thử vòng đời có thể tạo context trong `try/finally`:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("lifecycle-test");

AnnotationConfigApplicationContext context =
    createJmxContext(server);

ObjectName name = new ObjectName(
    "lab.test:type=JobMonitor,name=primary"
);

try {
    assertTrue(server.isRegistered(name));
} finally {
    context.close();
}

assertFalse(server.isRegistered(name));

MBeanServerFactory.releaseMBeanServer(server);
```

`createJmxContext(server)` ở đây là helper tạo context và cấu hình exporter giống phần setup đầu bài; cần tự định nghĩa trong test project. Một implementation có thể dùng `registerSingleton` rồi `context.register(JmxTestConfiguration.class)` và `context.refresh()`.

Lưu ý chỉ kiểm tra MBean do exporter trong test tạo. Không unregister toàn bộ platform MBeans hoặc những MBean khác mà test không sở hữu.

Với registration policy `IGNORE_EXISTING` hoặc `REPLACE_EXISTING`, ownership và cleanup có thể có trường hợp cần kiểm thử riêng. Tốt nhất dùng server cô lập và ObjectName không trùng để xác minh lifecycle cơ bản trước.

## 19. Unit test metadata source và integration test runtime

Có hai mức kiểm thử bổ sung:

### 19.1. Unit test annotation bằng reflection

```java
ManagedResource annotation =
    JobMonitor.class.getAnnotation(ManagedResource.class);

assertNotNull(annotation);
assertEquals(
    "lab.test:type=JobMonitor,name=primary",
    annotation.objectName()
);
```

Với getter:

```java
Method getter = JobMonitor.class.getMethod("getCompletedJobs");
assertNotNull(getter.getAnnotation(ManagedAttribute.class));
```

Những test này nhanh và chỉ xem source metadata, không cần Spring context. Chúng phù hợp khi muốn ràng buộc một annotation cụ thể không bị xóa nhầm.

### 19.2. Integration test với MBeanServer

Kiểm tra `MBeanInfo`, registration và JMX calls như phần trước. Đây là tầng phát hiện các lỗi:

- Exporter không có trong context.
- Bean không được scan/import.
- ObjectName sai hoặc trùng.
- Assembler không chọn đúng metadata.
- Một proxy làm thay đổi bean được export.
- Registration policy bỏ qua MBean mới.
- MBeanServer bị cấu hình khác dự kiến.

Khi mục tiêu là **kiểm thử bean có metadata JMX trong context**, integration test có giá trị quyết định vì nó kiểm tra hợp đồng thực sự được công bố.

## 20. Tách test config khỏi production config

Không nên dùng toàn bộ cấu hình production cho một unit test metadata đơn giản nếu nó:

- Kết nối database, broker hoặc remote service.
- Khởi động scheduler/worker nền.
- Bật HTTP server hoặc remote JMX connector.
- Export hàng chục MBean ngoài phạm vi test.
- Dùng chung platform MBeanServer giữa các test song song.

Thay vào đó, tạo context nhỏ với fixture và exporter đủ để tái tạo cơ chế export. Nếu cần xác minh auto-configuration của Spring Boot, viết một **integration test cấp ứng dụng** riêng, chẳng hạn dùng Spring Boot test context và kiểm tra exporter trong môi trường test có property phù hợp.

Hai loại test có mục tiêu khác:

| Loại test | Mục tiêu |
|---|---|
| Context nhỏ, tự cấu hình | Kiểm tra contract của MBean/metadata |
| Boot integration test | Kiểm tra JMX auto-configuration và exposure của ứng dụng |
| Remote JMX integration test | Kiểm tra connector, authentication, TLS, network topology |
| Manual JConsole test | Quan sát trực quan, hỗ trợ chẩn đoán |

Không biến mọi test metadata thành remote JMX test. Phần lớn kiểm chứng về `MBeanInfo` có thể chạy hoàn toàn local và deterministically khi cô lập đúng server.

## 21. Vấn đề thường gặp khi chạy test song song

Hai test tạo context riêng nhưng cùng sử dụng:

```text
lab.test:type=JobMonitor,name=primary
```

trên platform server có thể gây `InstanceAlreadyExistsException`. Kết quả test sẽ phụ thuộc thứ tự chạy.

Biện pháp:

1. Tạo MBeanServer riêng cho từng test hoặc test suite.
2. Dùng ObjectName riêng nếu phải dùng chung server.
3. Đóng context trong `@AfterEach`.
4. Chỉ unregister MBean do test sở hữu.
5. Không dùng `REPLACE_EXISTING` để che collision do test isolation lỗi.
6. Tách những test yêu cầu platform server vào JVM fork riêng nếu cần.

Test dùng `@SpringBootTest` cũng có thể cache context giữa test classes. Nếu test tự thay đổi state MBean, cần reset fixture và hiểu lifecycle của context cache; không assume mỗi test method luôn tạo context mới khi dùng Spring Test Context framework.

## 22. Các sai lầm cần tránh

### 22.1. Chỉ assert annotation tồn tại

`@ManagedResource` có thể tồn tại nhưng không có exporter. Cần assert registry thực tế.

### 22.2. Chỉ assert bean tồn tại trong context

Spring bean không tương đương JMX MBean. Cần dùng `MBeanServer.isRegistered`.

### 22.3. Test dùng platform server chung mà không cleanup

Dễ gây lỗi không ổn định hoặc đọc nhầm MBean của test trước. Dùng server cô lập.

### 22.4. Đọc đúng ObjectName nhưng không kiểm tra MBeanInfo

Có thể một exporter khác chiếm tên. Kiểm tra attribute và operation thực sự được công bố.

### 22.5. Chỉ kiểm tra positive contract

Nếu một getter nhạy cảm vô tình được export, test positive vẫn pass. Kiểm tra cả method **không được công bố**.

### 22.6. Gọi mọi operation để xác nhận

Operation có thể thay đổi dữ liệu, xóa cache, restart worker. Chỉ gọi operation an toàn trong test fixture.

### 22.7. Dùng setAttribute cho một read-only property

Sẽ bị từ chối theo JMX contract. Test quyền read/write theo `MBeanAttributeInfo`, không dựa vào tên method trong implementation.

### 22.8. Không quan tâm exception wrapper

JMX và Spring ModelMBean có thể chuyển hoặc bọc exception. Test hành vi từ chối và trạng thái giữ nguyên thay vì chỉ assert class exception tùy đoán.

### 22.9. Lẫn metadata Spring JMX với Actuator

`@ManagedResource` thuộc annotation-based Spring JMX; `@Endpoint` và `@ReadOperation` thuộc Spring Boot Actuator endpoint model. Hai cơ chế export khác nhau, nên setup test phải phù hợp với loại endpoint.

## 23. Mẫu checklist kỹ thuật cho bài test

Một checklist gọn:

- [ ] Test dùng context và MBeanServer đúng phạm vi.
- [ ] Bean quản trị tồn tại trong context.
- [ ] Exporter được cấu hình đúng.
- [ ] MBean được đăng ký tại ObjectName mong đợi.
- [ ] MBeanInfo chứa attribute với type/quyền phù hợp.
- [ ] MBeanInfo chứa operation với signature phù hợp.
- [ ] Method nội bộ ngoài hợp đồng không bị export.
- [ ] Getter và setter hoạt động qua JMX.
- [ ] Operation an toàn thực hiện đúng side effect.
- [ ] Input không hợp lệ bị từ chối và không làm hỏng state.
- [ ] Test cleanup context và MBeanServer.
- [ ] Không gọi remote connector hoặc làm rò dữ liệu nhạy cảm.

Checklist này áp dụng cho thiết kế bộ kiểm thử của dự án, không phải một trạng thái nghiệm thu tự động của bài viết.

## 24. Bài tập thực hành

**Bài 1 — Kiểm thử registration.** Tạo `@ManagedResource` bean có hai getter quản trị, dùng `AnnotationMBeanExporter` và một MBeanServer test riêng. Assert ObjectName tồn tại.

**Bài 2 — Kiểm thử read/write metadata.** Tạo `getLimit()`, `setLimit(int)` và `getCount()`. Xác minh `Limit` là read-write, `Count` chỉ đọc.

**Bài 3 — Kiểm thử negative contract.** Thêm `getInternalToken()` không annotate và assert nó không là attribute JMX. Thêm `deleteAllData()` không annotate và assert không là operation.

**Bài 4 — Kiểm thử operation.** Thêm `resetCounters()` được annotate; gọi qua `MBeanServer.invoke` trong môi trường test và kiểm tra counter.

**Bài 5 — Kiểm thử collision.** Tạo hai exporter cùng ObjectName trên server test. Quan sát `FAIL_ON_EXISTING` trong một test riêng; không dùng `REPLACE_EXISTING` để giấu lỗi.

**Bài 6 — Kiểm thử shutdown.** Đóng context sau khi register MBean và xác nhận ObjectName được unregister trước khi release MBeanServer.

**Bài 7 — Spring Boot integration.** Trong một Boot test, bật `spring.jmx.enabled` theo phiên bản đang dùng, kiểm tra custom MBean và phân biệt với Actuator endpoint JMX export.

**Bài 8 — Kiểm thử interface-based export.** Thay annotation assembler bằng `InterfaceBasedMBeanInfoAssembler`, tạo management interface allowlist và assert MBeanInfo không mở rộng khi implementation thêm method mới.

## 25. Câu hỏi tự kiểm tra

1. Vì sao đọc annotation bằng reflection chưa đủ để chứng minh MBean đã export?
2. `ApplicationContext` và `MBeanServer` giải quyết hai vấn đề gì khác nhau?
3. `MBeanInfo` có thể xác nhận read-only và read-write bằng cách nào?
4. Tại sao cần kiểm tra cả method không được export?
5. Vì sao test dùng platform MBeanServer chung dễ gặp collision?
6. `AnnotationMBeanExporter` có trách nhiệm gì trong bài test?
7. Khi `setAttribute` thất bại, tại sao exception có thể được bọc?
8. `getAttribute` khác với gọi trực tiếp getter trên Spring bean như thế nào?
9. Cleanup context và release MBeanServer giúp tránh vấn đề gì?
10. Khi nào cần Spring Boot integration test thay cho context test nhỏ?
11. Nếu cùng ObjectName nhưng metadata khác dự kiến, bạn kiểm tra những lớp nào?
12. Vì sao không nên bật remote JMX trong mỗi test metadata?

## 26. Ghi nhớ

**Kiểm thử metadata JMX trong Spring phải xác minh hợp đồng tại MBeanServer, không chỉ annotation trong source hoặc bean có mặt trong context.** Hãy tạo context nhỏ, MBeanServer cô lập, exporter phù hợp, rồi assert ObjectName, MBeanInfo, attribute, operation và sự vắng mặt của các method ngoài hợp đồng. Sau đó kiểm tra một số lời gọi JMX thực và cleanup lifecycle.

Thiết kế test này giúp phát hiện cấu hình thiếu exporter, naming sai, method bị export thừa, quyền read/write không đúng và lỗi đăng ký giữa nhiều context. Nó cũng tạo một ranh giới bảo mật thực tế: chỉ những khả năng quản trị đã được phê duyệt mới xuất hiện trong bề mặt JMX của ứng dụng.
