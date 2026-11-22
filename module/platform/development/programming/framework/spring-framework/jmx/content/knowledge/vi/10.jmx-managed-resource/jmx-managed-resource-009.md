# Kiểm thử scan annotation trong ApplicationContext

## Mục tiêu học tập

Trong Spring Framework JMX, việc thêm \`@ManagedResource\` vào một lớp chưa chứng minh rằng lớp đó đã được đăng ký làm MBean. Sau bài này, bạn có thể viết một bài kiểm thử tích hợp tạo \`ApplicationContext\` thật, kích hoạt cơ chế xuất JMX qua annotation, đối chiếu \`ObjectName\` trong \`MBeanServer\`, kiểm tra attribute và operation được công bố, đồng thời xác nhận những bean không có annotation quản lý không bị xuất ngoài ý muốn.

Bạn cũng sẽ hiểu các khác biệt giữa **component scanning**, **JMX autodetection**, **metadata assembly** và **đăng ký MBean**; biết cách cô lập JMX server để bài kiểm thử không phụ thuộc trạng thái của JVM hoặc các test khác.

## 1. “Scan annotation” thực sự bao gồm những bước nào?

Có hai loại phát hiện trong một ứng dụng dùng Spring JMX:

1. **Spring component scan** tìm các lớp được chú thích \`@Component\`, \`@Service\`, \`@Repository\` hoặc \`@Controller\`, từ đó tạo bean definition và Spring bean.
2. **JMX annotation autodetection** tìm các bean phù hợp trong \`ApplicationContext\` (đặc biệt những bean mang \`@ManagedResource\`), sau đó \`AnnotationMBeanExporter\` hoặc cấu hình tương đương xây dựng metadata quản lý và đăng ký chúng vào \`MBeanServer\`.

Đây là hai giai đoạn khác nhau. Ví dụ \`@ManagedResource\` của Spring JMX không tự động thay thế \`@Component\` để đăng ký bean trong container.

Chuỗi thao tác mong đợi:

\`\`\`text
Class trên classpath
       |
       | @ComponentScan tìm @Component
       v
Spring bean trong ApplicationContext
       |
       | @EnableMBeanExport / AnnotationMBeanExporter
       | phát hiện @ManagedResource
       v
Metadata JMX từ @ManagedAttribute / @ManagedOperation
       |
       | đăng ký với MBeanServer
       v
ObjectName xuất hiện trong registry
       |
       | MBeanServer.isRegistered/getMBeanInfo/getAttribute/invoke
       v
Bằng chứng kiểm thử tích hợp
\`\`\`

Một bài test chỉ dùng \`context.containsBean("orderMetrics")\` kiểm tra giai đoạn tạo Spring bean, **chưa chứng minh JMX export**. Một bài test chỉ dùng reflection xem annotation cũng chưa chứng minh MBean server đã đăng ký đối tượng.

## 2. Phạm vi và các kết quả cần chứng minh

Xét ứng dụng có \`OrderMetrics\`, được đánh dấu \`@ManagedResource\`, với một thuộc tính và một operation. Bài kiểm thử cần chứng minh ba việc:

- **Positive case:** Spring tạo bean, exporter tìm thấy bean và JMX registry có \`ObjectName\` đúng.
- **Metadata case:** MBean công bố đúng attribute \`CompletedCount\` và operation \`resetStatistics\`; các method nghiệp vụ không được phơi bày.
- **Negative case:** bean thông thường không có \`@ManagedResource\` không tự xuất vào JMX chỉ vì nó nằm trong \`ApplicationContext\`.

Ngoài ra, cần kiểm thử vòng đời: một MBean do context/exporter tạo ra được gỡ sau khi context đóng, miễn là không có bên thứ ba dùng cùng tên hoặc chính sách thay thế khác làm thay đổi ownership.

Bài thực hành dùng **Spring Framework thuần** và JUnit Jupiter, không đòi hỏi Spring Boot. Phần mềm chạy Java 17+; ví dụ phù hợp với Spring Framework 6.x và JDK 21.

## 3. Tạo lớp có @ManagedResource

**OrderMetrics.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.jmx:type=OrderMetrics,name=primary",
        description = "Order processing counters")
public class OrderMetrics {

    private final AtomicLong completed = new AtomicLong();

    public void recordCompleted() {
        completed.incrementAndGet();
    }

    @ManagedAttribute(description = "Number of completed orders")
    public long getCompletedCount() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset completed counter")
    public void resetStatistics() {
        completed.set(0);
    }
}
\`\`\`

Vai trò của các annotation:

| Annotation | Tác dụng |
| --- | --- |
| \`@Component\` | Cho phép \`@ComponentScan\` đăng ký \`OrderMetrics\` thành Spring bean |
| \`@ManagedResource\` | Đánh dấu lớp là đối tượng quản lý cho cơ chế JMX annotation exporter |
| \`@ManagedAttribute\` | Công bố \`getCompletedCount()\` thành attribute \`CompletedCount\` |
| \`@ManagedOperation\` | Công bố \`resetStatistics()\` thành operation |
| Không đánh dấu \`recordCompleted()\` | Method phục vụ nghiệp vụ không được annotation assembler mặc định xuất ra như operation |

Bên trong Spring, class này có thể được inject vào service nghiệp vụ để ghi nhận số liệu. JMX sẽ quan sát **cùng instance** nếu exporter xuất bean mà Spring quản lý.

## 4. Tạo bean không nên được JMX autodetect

**InternalService.java**

\`\`\`java
package com.example.jmx;

import org.springframework.stereotype.Component;

@Component
public class InternalService {

    public String internalStatus() {
        return "internal-only";
    }

    public void clearInternalState() {
        // Logic nội bộ, không intended for JMX.
    }
}
\`\`\`

Class này có \`@Component\` nên sẽ được đăng ký trong \`ApplicationContext\`. Nhưng nó không có \`@ManagedResource\` hoặc hợp đồng MBean JMX. Khi dùng annotation exporter theo mặc định phù hợp, \`InternalService\` không phải managed resource được chọn để công bố.

Một trường hợp âm tính như vậy giúp tránh nhầm lẫn rằng “Spring đã scan được bean” đồng nghĩa “JMX đã export mọi public method”.

## 5. Tạo cấu hình ApplicationContext để test

Để tránh phụ thuộc vào platform \`MBeanServer\` của JVM và các bài test khác, có thể tạo MBean server riêng cho context thử nghiệm.

**JmxTestConfiguration.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
@ComponentScan(basePackageClasses = {
        OrderMetrics.class,
        InternalService.class
})
@EnableMBeanExport(server = "testMBeanServer")
public class JmxTestConfiguration {

    @Bean
    public MBeanServer testMBeanServer() throws Exception {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("test.spring.jmx");
        factory.afterPropertiesSet();
        return factory.getObject();
    }
}
\`\`\`

\`@ComponentScan\` quét các class trong package, \`@EnableMBeanExport\` bật việc export MBean được chú thích và \`server = "testMBeanServer"\` chọn rõ JMX server để exporter sử dụng.

**Lưu ý về vòng đời server thử nghiệm:** \`MBeanServerFactoryBean\` tự quản lý hành vi tạo và giải phóng server. Với test đơn giản, thay vì tạo \`MBeanServerFactoryBean\` bên trong factory method rồi bỏ tham chiếu, có thể định nghĩa factory bean do Spring quản lý trực tiếp:

\`\`\`java
@Bean(name = "testMBeanServer")
public MBeanServerFactoryBean testMBeanServerFactory() {
    MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
    factory.setDefaultDomain("test.spring.jmx");
    factory.setLocateExistingServerIfPossible(false);
    return factory;
}
\`\`\`

Trong cách này, Spring gọi lifecycle của \`MBeanServerFactoryBean\` và inject sản phẩm \`MBeanServer\` của nó vào exporter. Đây là lựa chọn nên dùng trong bài test. Hãy **chọn một trong hai cách** khai báo bean \`testMBeanServer\`; không để cả hai method cùng tên trong một configuration.

Để giữ ví dụ dễ áp dụng, phần JUnit dưới đây dùng cấu hình \`@Bean\` trả về \`MBeanServerFactoryBean\` — Spring container quản lý vòng đời trực tiếp.

**Cấu hình hoàn chỉnh dùng cho bài test:**

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
@ComponentScan(basePackageClasses = {
        OrderMetrics.class,
        InternalService.class
})
@EnableMBeanExport(server = "testMBeanServer")
public class JmxTestConfiguration {

    @Bean(name = "testMBeanServer")
    public MBeanServerFactoryBean testMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("test.spring.jmx");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
\`\`\`

Cấu hình kiểm thử nên thuộc package chỉ chứa các component minh họa. Trong project thực, có thể dùng package test riêng hoặc một \`@ComponentScan\` có bộ lọc chỉ chọn class cần kiểm tra để tránh quét những bean không liên quan.

## 6. Viết JUnit test kiểm tra registry thật

Thay vì mock \`MBeanServer\`, bài test tích hợp nên tạo \`AnnotationConfigApplicationContext\` và đọc registry JMX thật.

**JmxAnnotationScanTest.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxAnnotationScanTest {

    private static final String METRICS_NAME =
            "com.example.jmx:type=OrderMetrics,name=primary";

    @Test
    void annotatedBeanIsExportedWithExpectedMetadata() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

            assertNotNull(context.getBean(OrderMetrics.class));
            assertNotNull(context.getBean(InternalService.class));

            MBeanServer server = context.getBean(
                    "testMBeanServer", MBeanServer.class);
            ObjectName metricsName = new ObjectName(METRICS_NAME);

            assertTrue(server.isRegistered(metricsName),
                    "Annotated OrderMetrics must be registered");

            MBeanInfo info = server.getMBeanInfo(metricsName);

            assertTrue(
                    java.util.Arrays.stream(info.getAttributes())
                            .anyMatch(a -> "CompletedCount".equals(a.getName())),
                    "Expected CompletedCount attribute");

            assertTrue(
                    java.util.Arrays.stream(info.getOperations())
                            .anyMatch(o -> "resetStatistics".equals(o.getName())),
                    "Expected resetStatistics operation");

            assertFalse(
                    java.util.Arrays.stream(info.getOperations())
                            .anyMatch(o -> "recordCompleted".equals(o.getName())),
                    "Unannotated method must not be exported");

            OrderMetrics metrics = context.getBean(OrderMetrics.class);
            metrics.recordCompleted();

            assertEquals(1L,
                    server.getAttribute(metricsName, "CompletedCount"));

            server.invoke(
                    metricsName, "resetStatistics",
                    new Object[0], new String[0]);

            assertEquals(0L,
                    server.getAttribute(metricsName, "CompletedCount"));
        }
    }
}
\`\`\`

Bài test kiểm tra từ nhiều phía:

- Bean đã tồn tại trong Spring context.
- \`MBeanServer\` có tên đăng ký mong đợi.
- MBean metadata phản ánh các annotation của Spring.
- Giá trị đọc qua JMX phản ánh **chính bean** mà ứng dụng cập nhật.
- Operation được công bố có thể gọi qua JMX và tác động lên instance đó.
- Method công khai nhưng không đánh dấu JMX không bị export như operation.

Đây là kiểm thử tích hợp của đường đi “scan → exporter → MBeanServer”, thay vì chỉ kiểm tra reflection annotation.

## 7. Kiểm thử negative case: bean bình thường không bị xuất

Một assertion nên kiểm tra registry không chứa tên đại diện cho \`InternalService\`:

\`\`\`java
@Test
void ordinarySpringBeanIsNotExported() throws Exception {
    try (var context = new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(
                "testMBeanServer", MBeanServer.class);

        ObjectName hypotheticalName = new ObjectName(
                "com.example.jmx:type=InternalService,name=primary");

        assertFalse(server.isRegistered(hypotheticalName));

        assertNotNull(context.getBean(InternalService.class));
    }
}
\`\`\`

Assertion một \`ObjectName\` không tồn tại chỉ đủ cho tên cụ thể đó. Nếu muốn kiểm tra chặt hơn rằng \`InternalService\` không bị xuất dưới **bất kỳ tên nào do exporter chọn**, cần chủ động kiểm soát naming strategy hoặc liệt kê MBeans trong domain test, rồi đối chiếu danh sách tên dự kiến.

Ví dụ kiểm tra namespace thuộc ứng dụng:

\`\`\`java
var names = server.queryNames(
        new ObjectName("com.example.jmx:*"), null);

assertEquals(
        java.util.Set.of(new ObjectName(METRICS_NAME)),
        names);
\`\`\`

Khi domain \`com.example.jmx\` chỉ dùng cho test fixture này, assertion tập tên chính xác giúp kiểm tra rằng không có export ngoài dự kiến. Nếu test có MBean phụ trợ thuộc cùng domain thì phải tính vào tập dự kiến hoặc chọn namespace riêng của fixture.

## 8. Kiểm thử vòng đời ApplicationContext

Exporter được Spring quản lý có nhiệm vụ đăng ký và dọn các MBean thuộc vòng đời của nó. Một test có thể giữ tham chiếu tới server để kiểm tra sau khi context đóng:

\`\`\`java
@Test
void exportedMBeanIsUnregisteredWhenContextCloses() throws Exception {
    var context = new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class);

    MBeanServer server = context.getBean(
            "testMBeanServer", MBeanServer.class);
    ObjectName name = new ObjectName(METRICS_NAME);

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name),
            "MBean should be unregistered with exporter lifecycle");
}
\`\`\`

Với \`MBeanServerFactoryBean\` do Spring quản lý, việc đóng context còn có thể giải phóng server. Do đó, nếu kiểm tra \`isRegistered\` sau khi server đã bị giải phóng, tham chiếu \`server\` có thể không còn nằm trong danh sách server của JVM dù vẫn là object Java được giữ bởi test. Để tập trung kiểm tra unregister theo exporter, có thể dùng một server được tạo và giải phóng tường minh bên ngoài context, rồi đưa vào test context như dependency, thay vì để cùng context quản lý cả server và exporter.

Một fixture ổn định cho trường hợp này:

\`\`\`java
MBeanServer server = javax.management.MBeanServerFactory.createMBeanServer(
        "isolated-test");
try {
    // Tạo context có @Bean MBeanServer trả chính server này.
    // Kiểm tra registered, đóng context rồi kiểm tra unregistered.
} finally {
    javax.management.MBeanServerFactory.releaseMBeanServer(server);
}
\`\`\`

Bài test nên tránh chia sẻ một platform server giữa nhiều test chạy song song cùng \`ObjectName\`; điều đó dễ tạo lỗi đăng ký trùng do test khác, không liên quan chức năng đang kiểm tra.

## 9. Kiểm tra annotation bằng metadata chứ không chỉ theo tên

Một bean đã xuất hiện trong registry có thể là Standard MBean được đăng ký bằng một cơ chế khác, hoặc được export tường minh bằng map. Vì vậy, khi cần chứng minh đúng **annotation-based export**, hãy kiểm tra:

1. Test configuration tạo annotation exporter qua \`@EnableMBeanExport\`.
2. \`OrderMetrics\` có \`@ManagedResource\`.
3. Registry có \`ObjectName\` từ annotation.
4. \`MBeanInfo\` công bố đúng attribute và operation do \`@ManagedAttribute\` và \`@ManagedOperation\` đánh dấu.
5. Method không đánh dấu không xuất hiện ngoài ý muốn.

Có thể mở rộng bằng cách đọc metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(metricsName);

for (var attribute : info.getAttributes()) {
    System.out.printf(
            "%s: type=%s, readable=%s, writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable());
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Nếu yêu cầu bài học chỉ là xác nhận đăng ký, \`isRegistered\` đã cung cấp tín hiệu quan trọng. Nếu muốn chứng minh phạm vi phơi bày chính xác, \`getMBeanInfo\` là bước cần thiết.

## 10. Phân biệt @ManagedResource và Standard MBean convention

Có hai con đường để một class thành JMX MBean:

**Standard MBean convention**:

\`\`\`java
public interface JobMonitorMBean {
    int getProcessedCount();
}

public class JobMonitor implements JobMonitorMBean {
    public int getProcessedCount() { return 0; }
}
\`\`\`

Khi đăng ký theo convention, JMX sử dụng giao diện \`ClassNameMBean\` để xác định hợp đồng quản lý. Không cần dùng Spring \`@ManagedResource\`.

**Spring annotation model**:

\`\`\`java
@ManagedResource(objectName = "com.example:type=JobMonitor")
public class JobMonitor {
    @ManagedAttribute
    public int getProcessedCount() { return 0; }
}
\`\`\`

Ở đây, Spring exporter/assembler dùng annotation để dựng metadata. Class không bắt buộc implement interface \`JobMonitorMBean\`.

Khi viết test cho **scan annotation**, dùng một class không triển khai \`*MBean\` sẽ giúp bằng chứng rõ ràng: MBean được đăng ký do cơ chế Spring annotation exporter thay vì nhờ Standard MBean convention.

## 11. Cấu hình khác: tạo AnnotationMBeanExporter trực tiếp

Nếu không dùng \`@EnableMBeanExport\`, có thể khai báo exporter tường minh:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ExplicitExporterConfiguration {

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer testMBeanServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(testMBeanServer);
        return exporter;
    }
}
\`\`\`

Đoạn này giả định context đã có \`MBeanServer\` bean phù hợp. \`AnnotationMBeanExporter\` được thiết kế để sử dụng metadata Spring JMX và tự động phát hiện các bean được đánh dấu. Không khai báo đồng thời \`@EnableMBeanExport\` và một exporter thứ hai trùng trách nhiệm mà không có chủ đích, vì có thể khiến hai exporter cùng đăng ký một \`ObjectName\`.

Một kiểm thử tốt nên chọn **một con đường cấu hình** cho mỗi fixture, và kiểm tra chính xác kết quả của con đường đó.

## 12. Phạm vi scan, context cha/con và bean proxy

### ComponentScan không quét toàn bộ classpath

\`@ComponentScan\` chỉ xét các package, include/exclude filter và điều kiện được cấu hình. Nếu \`OrderMetrics\` nằm ngoài package scan, \`@ManagedResource\` không tự làm nó xuất hiện trong context.

### ApplicationContext khác nhau có thể thấy tập bean khác nhau

Với context cha/con, bean trong context cha và bean trong context con có phạm vi truy cập khác nhau; exporter ở mỗi context có thể nhìn tập bean khác nhau theo cấu hình. Đồng thời, cả hai có thể dùng chung platform \`MBeanServer\`, dẫn tới trùng \`ObjectName\` nếu cùng cố xuất một managed resource.

### AOP proxy và class metadata

Khi một bean được Spring AOP proxy, lớp runtime có thể khác class gốc chứa \`@ManagedResource\`. Cách exporter lấy annotation, metadata và target bean type phụ thuộc cơ chế introspection và version Spring. Nếu một managed resource biến mất sau khi thêm \`@Transactional\` hoặc một aspect, nên kiểm tra loại proxy, annotation trên target/interface và log exporter.

### Lazy beans và FactoryBean

Một bean lazy hoặc sản phẩm của \`FactoryBean\` có thể chịu ảnh hưởng bởi thời điểm exporter kiểm tra, kiểu bean có thể xác định và việc khởi tạo. Không nên cho rằng tất cả instance tạo sau khi exporter hoàn tất scanning sẽ tự được export; nếu cần đăng ký runtime, dùng cơ chế đăng ký rõ ràng.

Trong test fixture đầu tiên, ưu tiên các bean singleton được tạo thông thường để kiểm tra nguyên lý cơ bản; sau đó mới mở rộng sang proxy, lazy và nhiều context.

## 13. Xử lý các lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| \`OrderMetrics\` không tồn tại trong context | \`@ComponentScan\` sai package hoặc class không có \`@Component\` | \`getBeanNamesForType\`, kiểm tra configuration |
| Có Spring bean nhưng thiếu JMX MBean | Thiếu \`@EnableMBeanExport\`, \`@ManagedResource\` hoặc exporter sai server | \`isRegistered\`, danh sách exporter beans và server thực |
| MBean đăng ký nhưng attribute trống | Thiếu \`@ManagedAttribute\` hoặc assembler không đọc metadata mong đợi | \`getMBeanInfo\`, annotation trên getter |
| \`InstanceAlreadyExistsException\` | Trùng \`ObjectName\` trong cùng server | Dùng server riêng, domain test và tên khác nhau |
| Test chạy riêng pass, chạy suite fail | Test chia sẻ registry hoặc context, không đóng context | Dùng server riêng và try-with-resources |
| Test qua JConsole thấy MBean nhưng JUnit không thấy | JConsole nối JVM khác, test đọc \`MBeanServer\` khác | Đối chiếu PID, server được inject, full \`ObjectName\` |
| MBean có operation ngoài mong đợi | Exporter/assembler hoặc Standard MBean interface khác cấu hình | Đọc \`MBeanInfo\`, xác định cơ chế export |
| Context khởi tạo lỗi vì MBean không hợp lệ | Metadata quản lý/kiểu dữ liệu hoặc ObjectName sai | Đọc root cause trong log startup |
| Lỗi khi đóng context | Ownership MBean/server hoặc exporter lifecycle xung đột | Cô lập server và xác định ai unregister |

Nếu \`isRegistered\` trả false, đừng ngay lập tức sửa annotation. Trước hết kiểm tra bean có trong context, exporter có tồn tại, server nào được dùng và tên JMX kỳ vọng có chính xác không.

## 14. Cấu hình build tối thiểu và cách chạy test

Nếu project Gradle Java đã dùng Spring Framework và JUnit Jupiter, cần dependency Spring context/JMX và JUnit Jupiter. Ví dụ Groovy DSL:

\`\`\`groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
\`\`\`

Các version trên chỉ minh họa một bộ dependency có dạng hợp lệ; với repository thực tế, nên lấy version từ BOM, dependency management hoặc catalog đang dùng để tránh xung đột. \`spring-context\` cung cấp các thành phần IoC và JMX annotation exporter trong ví dụ. JUnit Jupiter cung cấp assertions và \`@Test\`.

Chạy:

\`\`\`bash
./gradlew test --tests 'com.example.jmx.JmxAnnotationScanTest'
\`\`\`

Trên Windows, dùng \`gradlew.bat test --tests com.example.jmx.JmxAnnotationScanTest\` hoặc lệnh wrapper phù hợp với project. Bài test không cần bật remote JMX hay mở JConsole; nó truy cập trực tiếp một \`MBeanServer\` trong JVM test.

Nếu project đã dùng Spring Boot test starter, có thể dùng \`@SpringBootTest\` hoặc \`ApplicationContextRunner\`, nhưng cần xác định Boot auto-configuration có tự tạo exporter/server hay không. Với mục đích học rõ Spring Framework annotation scan, fixture \`AnnotationConfigApplicationContext\` riêng giảm các phụ thuộc ngoài đề bài.

## 15. Bài tập mở rộng

**Bài 1 — Phát hiện bean đúng phạm vi.** Thêm \`CacheMetrics\` có \`@Component\`, \`@ManagedResource\` và \`getCacheHits()\` có \`@ManagedAttribute\`. Chứng minh registry có cả \`OrderMetrics\` và \`CacheMetrics\`, còn \`InternalService\` không được export.

**Bài 2 — Annotation thiếu ở class.** Bỏ \`@ManagedResource\` khỏi \`OrderMetrics\` nhưng giữ \`@ManagedAttribute\`; chạy test và giải thích khác biệt giữa bean vẫn tồn tại trong context và JMX autodetection không chọn nó.

**Bài 3 — Method bị phơi bày.** Tạo method \`resetStatistics()\` rồi thử có/không có \`@ManagedOperation\`. Đối chiếu \`getMBeanInfo\` thay vì chỉ dựa trên việc compile thành công.

**Bài 4 — Sai server.** Cố tình cấu hình exporter với một \`MBeanServer\` riêng nhưng test đọc platform server. Quan sát \`isRegistered=false\` ở server sai và \`true\` ở server đúng. Sau đó sửa test để inject server từ context.

**Bài 5 — Trùng ObjectName.** Tạo hai managed resources cùng dùng một \`objectName\` và quan sát lỗi đăng ký trong môi trường test. Đặt lại tên khác nhau, xác nhận cả hai xuất hiện.

**Bài 6 — Vòng đời.** Thử đóng context rồi kiểm tra MBean không còn đăng ký trên một server do test quản lý bên ngoài context. Giải thích vai trò của exporter trong cleanup.

## Kết luận

Kiểm thử scan annotation JMX trong Spring Framework cần chứng minh cả đường đi **Spring component scan → managed bean → annotation exporter → MBeanServer registry → metadata/giá trị JMX**. \`@ManagedResource\` xác định đối tượng quản lý; \`@ManagedAttribute\` và \`@ManagedOperation\` xác định API được phơi bày; \`@EnableMBeanExport\` hoặc \`AnnotationMBeanExporter\` kích hoạt việc phát hiện và đăng ký. Một bài test tích hợp với \`ApplicationContext\` và \`MBeanServer\` riêng giúp kiểm tra chính xác các điều kiện trên và giảm xung đột giữa các test.
