# Tạo attribute đọc–ghi bằng @ManagedAttribute trong Spring Framework JMX

## 1. Mục tiêu thực hành

Trong bài này, bạn sẽ tạo một **JMX attribute vừa đọc vừa ghi** bằng \`@ManagedAttribute\` trong Spring Framework. Ví dụ chính là thuộc tính \`MaxConcurrentJobs\`, biểu diễn giới hạn số công việc được xử lý đồng thời trong một worker pool.

Kết thúc bài, bạn có thể:

- Sử dụng \`@ManagedResource\` để đánh dấu Spring bean làm tài nguyên quản trị JMX.
- Gắn \`@ManagedAttribute\` vào getter và setter để JMX công bố attribute có quyền đọc/ghi.
- Hiểu quy tắc ánh xạ \`getMaxConcurrentJobs()\` và \`setMaxConcurrentJobs(int)\` thành cùng một attribute \`MaxConcurrentJobs\`.
- Cấu hình exporter hoặc cơ chế annotation-driven export trong Spring mà không tạo nhiều MBean registration owners.
- Dùng \`MBeanServer.getMBeanInfo()\`, \`getAttribute()\` và \`setAttribute()\` kiểm tra sự tồn tại, kiểu dữ liệu, quyền đọc/ghi và giá trị thực.
- Xử lý validation, đồng bộ trạng thái, lỗi khi setter bị từ chối và tác động của thay đổi cấu hình lúc runtime.
- Phân biệt JMX write permission với authentication/authorization của remote connector.
- Tạo integration test bảo đảm attribute writable đúng contract nhưng những operations không mong muốn không bị lộ.

## 2. Bài toán thực tế

Một ứng dụng xử lý hàng đợi có giới hạn số jobs chạy đồng thời. Ban đầu cấu hình trong application:

~~~text
maxConcurrentJobs = 8
~~~

Khi tải thay đổi, operator muốn:

1. Đọc giá trị hiện tại qua JConsole.
2. Điều chỉnh giới hạn thành 12 mà không restart ứng dụng.
3. Nhận lỗi rõ ràng nếu giá trị không hợp lệ, ví dụ 0 hoặc 100000.
4. Biết chắc hệ thống đang sử dụng giới hạn mới, thay vì chỉ thay một biến hiển thị không tác động tới worker pool.

JMX phù hợp cho một số cấu hình quản trị động nhỏ, nhưng cần **management contract** và **giới hạn quyền** rõ ràng. Không nên biến mọi application property thành writable attribute.

Mô hình:

~~~text
JConsole / JMX client
        |
        v
MBeanServer
        |
        v
Spring JMX management bean
    getMaxConcurrentJobs()
    setMaxConcurrentJobs(int)
        |
        v
WorkerConcurrencySettings (Spring bean)
        |
        v
Worker pool / scheduler
~~~

Management adapter là cửa sổ quản trị; business component vẫn là nơi duy nhất sở hữu cấu hình được áp dụng.

## 3. Chuẩn bị môi trường

Ví dụ hướng đến ứng dụng Java sử dụng Spring Framework JMX và Java 17+; có thể áp dụng với các phiên bản Spring phù hợp sau khi kiểm tra API/version.

Các thành phần cần có:

- Java JDK có module \`java.management\` và công cụ JConsole hoặc JMX client thích hợp.
- Spring Context và hỗ trợ JMX export.
- Một \`MBeanServer\`, thông thường có thể là platform MBeanServer.
- Một Spring bean đại diện cho worker settings.
- Một Spring management bean có JMX annotations.
- Cơ chế export annotation-aware, thông qua cấu hình Spring phù hợp.

Nếu sử dụng Spring Boot, cần xác định Boot version và exporter auto-configuration trước khi thêm exporter thủ công. Việc có \`@ManagedResource\` trên class không tự đảm bảo bean đã xuất hiện trong \`MBeanServer\`.

Để kiểm tra JMX **local**, không cần mở remote JMX connector. Đọc cùng MBeanServer trong JVM hoặc dùng công cụ được quyền kết nối local. Không đặt \`authenticate=false\` và \`ssl=false\` lên remote connector chỉ vì muốn thử nghiệm thuận tiện.

## 4. Hiểu attribute đọc–ghi của JMX

Trong JMX, một attribute có các thuộc tính metadata quan trọng:

| Metadata | Ý nghĩa |
|---|---|
| Name | Tên attribute client sử dụng |
| Type | Kiểu Java/JMX được công bố |
| Readable | Client có thể gọi \`getAttribute\` không |
| Writable | Client có thể gọi \`setAttribute\` không |
| Is | Có phải boolean getter theo quy ước \`isXxx\` không |
| Description | Mô tả cho người vận hành |

Trong Spring annotation-driven JMX, ví dụ:

~~~java
@ManagedAttribute
public int getMaxConcurrentJobs() {
    return 8;
}

@ManagedAttribute
public void setMaxConcurrentJobs(int value) {
    // Áp dụng giá trị mới.
}
~~~

Hai methods tương ứng với một JMX attribute tên \`MaxConcurrentJobs\` nếu assembler nhận diện theo JavaBean property convention.

Phía client đọc:

~~~java
Object value = server.getAttribute(name, "MaxConcurrentJobs");
~~~

Phía client ghi:

~~~java
server.setAttribute(name, new Attribute("MaxConcurrentJobs", 12));
~~~

**Chú ý:** JMX attribute setter có thể được gọi từ công cụ quản trị được cấp quyền. Setter không chỉ đổi một field để JConsole hiển thị; nó nên có semantics rõ và đảm bảo hiệu lực với component thực tế.

## 5. Bước 1 — Tạo lớp settings quản lý trạng thái

Đầu tiên tách state nghiệp vụ khỏi JMX adapter:

~~~java
package com.example.shop.jobs;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class WorkerConcurrencySettings {

    public static final int MIN_CONCURRENCY = 1;
    public static final int MAX_CONCURRENCY = 64;

    private final AtomicInteger maxConcurrentJobs =
            new AtomicInteger(8);

    public int currentLimit() {
        return maxConcurrentJobs.get();
    }

    public void updateLimit(int newLimit) {
        if (newLimit < MIN_CONCURRENCY
                || newLimit > MAX_CONCURRENCY) {
            throw new IllegalArgumentException(
                    "MaxConcurrentJobs must be between 1 and 64");
        }

        maxConcurrentJobs.set(newLimit);
    }
}
~~~

Thiết kế này thể hiện:

- Một nguồn chân lý duy nhất cho \`maxConcurrentJobs\`.
- Giá trị default là 8.
- Phạm vi hợp lệ là 1..64.
- \`AtomicInteger\` cung cấp khả năng đọc/ghi giá trị nguyên tử và visibility giữa threads.
- Validation được thực hiện trong component sở hữu cấu hình, không chỉ ở JMX adapter.

**Giới hạn của ví dụ:** \`AtomicInteger.set()\` chỉ đổi giá trị trong bộ nhớ. Worker pool chỉ thật sự thay đổi concurrency nếu scheduler/worker logic đọc giá trị này hoặc một adapter khác áp dụng thay đổi vào cơ chế điều phối thực. Nếu đang dùng \`ThreadPoolExecutor\`, các giới hạn như \`corePoolSize\` và \`maximumPoolSize\` cần được cập nhật theo API và thứ tự hợp lệ; không thay đổi ngẫu nhiên hai con số vì có thể gây \`IllegalArgumentException\` hoặc hành vi không mong muốn.

Đối với bài học, ta mô hình hóa worker pool thông qua một settings component để tập trung vào JMX read/write contract.

## 6. Bước 2 — Tạo Spring management bean

Bean quản trị dùng \`@ManagedResource\` và \`@ManagedAttribute\`:

~~~java
package com.example.shop.jobs;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.shop.jobs:type=WorkerSettings,name=primary",
        description = "Runtime worker concurrency settings")
public class WorkerSettingsManagement {

    private final WorkerConcurrencySettings settings;

    public WorkerSettingsManagement(
            WorkerConcurrencySettings settings) {
        this.settings = settings;
    }

    @ManagedAttribute(
            description = "Current maximum concurrent jobs")
    public int getMaxConcurrentJobs() {
        return settings.currentLimit();
    }

    @ManagedAttribute(
            description = "Maximum concurrent jobs, allowed range 1..64")
    public void setMaxConcurrentJobs(int maxConcurrentJobs) {
        settings.updateLimit(maxConcurrentJobs);
    }
}
~~~

Tại đây:

1. \`@Component\`: tạo Spring bean qua component scanning.
2. \`@ManagedResource\`: cung cấp resource metadata và ObjectName mong muốn.
3. \`getMaxConcurrentJobs()\`: JMX getter, đọc trạng thái hiện hành.
4. \`setMaxConcurrentJobs(int)\`: JMX setter, gọi cùng một settings service để ghi.
5. \`@ManagedAttribute\` ở cả hai method: khai báo cả read và write metadata theo annotation assembler.
6. Domain \`com.example.shop.jobs\`: namespace JMX tùy chỉnh của ứng dụng.
7. \`type=WorkerSettings,name=primary\`: định danh của MBean trong một MBeanServer.

Không thêm \`@ManagedOperation\` lên setter chỉ để ghi attribute. Setter là một **write attribute accessor**, không nhất thiết là một JMX operation riêng. Nên dùng cách công bố đúng ngữ nghĩa.

## 7. Bước 3 — Đảm bảo component scanning

Nếu dùng Spring Boot:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với package \`com.example.shop\` ở root, các classes \`com.example.shop.jobs.*\` thường nằm trong phạm vi component scanning mặc định.

Nếu ứng dụng đặt \`@SpringBootApplication(scanBasePackages=...)\`, hãy bảo đảm package management và settings được bao gồm.

Với Spring Framework thuần, có thể dùng:

~~~java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.shop.jobs")
public class ApplicationConfiguration {
}
~~~

Nếu bean chưa nằm trong ApplicationContext, exporter không thể autodetect nó. Đó là lỗi bean registration trong Spring, khác với JMX registration.

## 8. Bước 4 — Cấu hình annotation-aware MBeanExporter

Một cấu hình minh họa không phụ thuộc vào Spring Boot auto-configuration:

~~~java
package com.example.shop.jobs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
~~~

Vai trò:

- \`AnnotationJmxAttributeSource\` đọc \`@ManagedResource\` và \`@ManagedAttribute\`.
- \`MetadataMBeanInfoAssembler\` tạo metadata JMX từ annotation data.
- \`MetadataNamingStrategy\` dùng managed resource metadata để tạo ObjectName.
- \`AUTODETECT_ASSEMBLER\` giúp exporter lựa chọn những beans đáp ứng tiêu chí assembler.
- \`MBeanExporter\` thực hiện registration vào MBeanServer.

**Không thêm nguyên cấu hình này khi ứng dụng đã có exporter từ Spring Boot hoặc từ cấu hình khác.** Hai exporter cùng đăng ký \`com.example.shop.jobs:type=WorkerSettings,name=primary\` có thể gây xung đột. Trước khi tạo exporter mới, xác định owner hiện tại.

Một lựa chọn khác là dùng \`AnnotationMBeanExporter\` hoặc \`@EnableMBeanExport\` theo cấu hình Spring/version phù hợp. Mục tiêu là **một** đường export annotation-driven rõ ràng.

## 9. Bước 5 — Chỉ định MBeanServer phù hợp

Một Spring exporter có thể dùng server được tìm thấy hoặc server được cấu hình rõ:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
~~~

Khi cần thiết, inject server vào exporter:

~~~java
@Bean
MBeanExporter jmxExporter(
        MBeanServer server,
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy naming) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(naming);
    exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
    return exporter;
}
~~~

Đây là **biến thể thay thế** cho \`jmxExporter\` ở mục trước, không phải bean thứ hai nên thêm đồng thời với cùng tên. Trong một ứng dụng thực tế chỉ chọn một cấu hình exporter.

Đặt đúng MBeanServer giúp các JMX clients và test đọc cùng registry. Nếu application dùng custom MBeanServer, \`ManagementFactory.getPlatformMBeanServer()\` có thể không chứa custom MBean.

## 10. Bước 6 — Xác minh MBean đã đăng ký

Trước khi mở JConsole, có thể kiểm tra bằng Java API:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationCheck {
    public static void verify(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "WorkerSettings MBean not registered");
        }

        System.out.println("Registered: " + name);
    }

    public static void main(String[] args) throws Exception {
        verify(ManagementFactory.getPlatformMBeanServer());
    }
}
~~~

Chú ý: đoạn \`main\` chạy trong một JVM độc lập sẽ kiểm tra MBeanServer của **chính JVM đó**, không tự đọc MBeanServer của một Spring Boot process khác. Để kiểm tra registration đúng, chạy logic trong application JVM/test context hoặc kết nối remote bằng connector đã được cấp quyền.

MBean được đăng ký là điều kiện cần, nhưng chưa đủ chứng minh attribute writable. Bước kế tiếp cần đọc metadata.

## 11. Bước 7 — Kiểm tra MBeanInfo và quyền đọc/ghi

Để biết JMX client thực sự nhìn thấy thuộc tính nào:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class AttributeMetadataCheck {

    public static void verify(MBeanServer server)
            throws Exception {

        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo target = null;
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            if ("MaxConcurrentJobs".equals(attribute.getName())) {
                target = attribute;
                break;
            }
        }

        if (target == null) {
            throw new AssertionError(
                "Missing JMX attribute MaxConcurrentJobs");
        }
        if (!target.isReadable()) {
            throw new AssertionError("Attribute not readable");
        }
        if (!target.isWritable()) {
            throw new AssertionError("Attribute not writable");
        }
        if (!"int".equals(target.getType())) {
            throw new AssertionError(
                "Unexpected type: " + target.getType());
        }

        System.out.println("Attribute is readable and writable");
    }
}
~~~

Trên JMX \`MBeanInfo\`, tên attribute là \`MaxConcurrentJobs\` theo JavaBean property naming. Kiểu primitive \`int\` thường hiện là \`int\`, còn giá trị trả qua JMX client API được boxing thành \`Integer\`.

Nếu \`isWritable()\` là \`false\`, hãy kiểm tra:

- Setter có tồn tại và public không?
- Setter có đúng signature \`setMaxConcurrentJobs(int)\` không?
- Có \`@ManagedAttribute\` ở setter không?
- Exporter/assembler thực sự dùng metadata annotation hay Standard MBean interface khác?
- AOP proxy có expose setter không?
- Có vấn đề getter/setter type mismatch không?
- Có MBean khác chiếm cùng ObjectName do registration policy không?

Đừng nhầm \`isWritable()\` với permission của JMX remote principal. \`isWritable()\` chỉ nói contract cho phép set, còn client cụ thể có quyền ghi hay không phụ thuộc tầng security.

## 12. Bước 8 — Ghi attribute bằng MBeanServer

JMX API thao tác:

~~~java
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class UpdateWorkerConcurrency {

    public static void update(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        Object before = server.getAttribute(name, "MaxConcurrentJobs");
        System.out.println("Before: " + before);

        server.setAttribute(
            name,
            new Attribute("MaxConcurrentJobs", 12));

        Object after = server.getAttribute(name, "MaxConcurrentJobs");
        System.out.println("After: " + after);
    }
}
~~~

Phép ghi thành công có nghĩa setter được JMX invocation xử lý mà không báo lỗi. Kiểm tra readback giúp xác nhận settings component đang báo giá trị mới.

Nhưng **readback giá trị 12 không đủ để chứng minh worker pool đã thực sự áp dụng giới hạn 12** nếu settings component không tích hợp với scheduler. Trong triển khai thực tế, cần test behavior hoặc đọc metrics như \`ConfiguredLimit\`, \`EffectiveLimit\`, \`ActiveWorkers\` để tránh tình trạng cấu hình mới chỉ thay đổi trên bề mặt.

## 13. Bước 9 — Thử ghi giá trị không hợp lệ

Setter đã có validation 1..64. Hãy thử giá trị 0 trong môi trường development/test:

~~~java
try {
    server.setAttribute(
        name, new Attribute("MaxConcurrentJobs", 0));
    throw new AssertionError("Expected validation failure");
} catch (Exception expected) {
    System.out.println(
        "Invalid value rejected: " +
        expected.getClass().getSimpleName());
}
~~~

Đây là minh họa ngắn. Trong test thực tế, không nên bắt mọi \`Exception\` rồi coi là đúng: phải xác nhận **lỗi đến từ validation mong đợi** thông qua exception/cause phù hợp của JMX/Spring version. Sau lỗi, đọc \`MaxConcurrentJobs\` và xác nhận giá trị cũ không bị thay đổi.

Các exception có thể liên quan:
- \`InvalidAttributeValueException\` trong các đường gọi JMX phù hợp.
- \`MBeanException\` hoặc một ngoại lệ được framework bọc lại từ setter.
- \`AttributeNotFoundException\` nếu tên sai hoặc không có quyền ghi ở contract.
- \`ReflectionException\` khi invocation/signature không đúng.
- \`SecurityException\` hoặc access denied do security policy.

Đừng “sửa” test validation thất bại bằng cách bỏ validation để JConsole có thể set mọi giá trị.

## 14. Spring JMX metadata và cơ chế setter

Trong JavaBeans, getter và setter thường ghép thành một property khi cùng tên và kiểu tương thích:

~~~text
getMaxConcurrentJobs()      -> property MaxConcurrentJobs (read)
setMaxConcurrentJobs(int)   -> property MaxConcurrentJobs (write)
~~~

Đối với boolean có thể dùng:

~~~java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}

@ManagedAttribute
public void setPaused(boolean paused) {
    this.paused = paused;
}
~~~

Tuy nhiên đừng nhầm \`@ManagedAttribute\` với \`@Value\` hay \`@ConfigurationProperties\`. Spring JMX setter có thể thay giá trị **runtime**, nhưng nó không tự ghi ngược \`application.yml\`, environment variables hoặc config server.

Khi JVM restart, cấu hình có thể trở về giá trị từ property source. Nếu cần duy trì thay đổi qua restart, phải thiết kế persistence/cấu hình động riêng với authentication, audit và rollback.

## 15. Quyền đọc/ghi trên MBean khác quyền người dùng

MBeanInfo có thể nói attribute writable, nhưng remote JMX connector vẫn có thể giới hạn client cụ thể.

Phân biệt:

| Cấp | Ý nghĩa |
|---|---|
| Attribute metadata \`isWritable()\` | Contract MBean có setter |
| JMX connector authentication | Client là ai |
| JMX connector authorization | Client được làm gì |
| Firewall/network policies | Client có thể kết nối từ đâu |
| TLS/encryption | Bảo vệ lưu lượng |
| Application-level validation | Giá trị hợp lệ và tác động an toàn |
| Audit | Ai đã thay cấu hình, khi nào |

Một MBean writable không tự động được bảo vệ bằng Spring Security HTTP rules. JMX remote thường có security configuration riêng. Để production an toàn:
- Không mở remote JMX không xác thực.
- Không chia sẻ quyền quản trị với collector chỉ cần đọc metrics.
- Giới hạn network và credentials.
- Review setters ảnh hưởng availability.
- Ghi audit cho thay đổi có tác động vận hành.
- Có cách khôi phục cấu hình trước đó.

## 16. Thiết kế setter tránh side effects nguy hiểm

Không phải attribute nào cũng nên writable.

Những giá trị nên cẩn trọng:
- Thread pool concurrency limit.
- Cache capacity.
- Batch size.
- Retry interval.
- Queue draining switch.
- Traffic control.
- Feature flag ảnh hưởng xử lý đơn hàng.

Rủi ro khi setter thay đổi giá trị:
1. Tăng concurrency quá cao gây quá tải CPU/DB.
2. Giảm concurrency đột ngột khiến throughput thấp.
3. Vi phạm invariant khác như min/max pool sizes.
4. Ghi cấu hình một phần nhưng không áp dụng hết.
5. Nhiều operators thay liên tiếp gây race.
6. Thay đổi runtime bị mất sau restart.
7. Monitoring đọc giá trị đã set nhưng worker pool chưa áp dụng.
8. Không có audit để điều tra thay đổi.

Một setter tốt cần có:
- Validation ở domain boundary.
- Đồng bộ cập nhật và trạng thái hiệu lực.
- Semantics rõ (áp dụng ngay, deferred, hay cần restart).
- Error reporting cụ thể.
- Khả năng quan sát current/effective state.
- Phân quyền và audit theo độ nhạy.

## 17. Khi cập nhật nhiều cấu hình liên quan

\`@ManagedAttribute\` trên hai setters độc lập không tạo transaction:

~~~java
setCorePoolSize(int core);
setMaximumPoolSize(int max);
~~~

Nếu client gọi hai setter liên tiếp, hệ thống có thể nhìn thấy trạng thái trung gian không hợp lệ. Ví dụ giảm max trước core khiến \`ThreadPoolExecutor\` từ chối cấu hình.

Khi cần thay nhiều tham số như một thay đổi nguyên tử, cân nhắc:
- Một management operation \`updatePoolSettings(core, max)\` có validation tổng hợp.
- Một immutable settings object được publish nguyên tử.
- Lock hoặc state machine nhất quán.
- Một version/generation giúp phát hiện cập nhật cạnh tranh.
- Một quy trình staged apply và rollback nếu API không atomic.

Không bắt buộc mọi thay đổi phải là JMX attribute setter. Operations có chủ đích có thể phù hợp hơn cho hành động đa bước hoặc chứa side effects.

## 18. Hỗ trợ concurrent updates

\`AtomicInteger\` đảm bảo read/write đơn giản không bị xé giá trị (torn primitive update). Tuy nhiên nó không tự xử lý **lost update** ở những thao tác kiểu đọc rồi ghi:

~~~java
int current = settings.currentLimit();
settings.updateLimit(current + 1);
~~~

Nếu hai client cùng chạy đoạn này, cả hai có thể đọc 8 và cùng set 9, thay vì đạt 10. Nếu ứng dụng chỉ cần “set absolute target”, \`set(9)\` có thể là semantics phù hợp; nhưng nếu muốn “increment” nguyên tử, phải dùng CAS hoặc operation chuyên biệt.

Có thể công bố:
- \`MaxConcurrentJobs\` (giá trị target).
- \`ConfigurationGeneration\` (số phiên bản tăng mỗi lần thay đổi).
- \`LastChangedEpochMillis\`.
- \`EffectiveConcurrency\` nếu worker pool áp dụng async.

Một client có thể đối chiếu generation trước/sau, nhưng việc có generation không tự tạo optimistic transaction nếu setter không kiểm tra generation.

## 19. Không thay đổi cấu hình bền vững nếu chỉ cần thử nghiệm

Khi setter chỉ thay state RAM:
- Restart JVM khôi phục giá trị mặc định hoặc external config.
- Các replicas không tự đồng bộ, mỗi JVM có MBeanServer và settings riêng.
- Một JConsole client thay đổi pod A không nhất thiết thay đổi pod B.
- Config rollout có thể ghi đè thay đổi runtime.

Nếu cần thay đổi cluster-wide, nên dùng hệ thống cấu hình/rollout có kiểm soát thay vì gửi \`setAttribute()\` riêng đến từng pod mà không có orchestration.

Đối với thử nghiệm, công bố rõ:
~~~text
Runtime-only override: yes
Applies to: current JVM
Persists across restart: no
Effective immediately: depends on worker integration
~~~

Những thông tin này quan trọng để operator không hiểu sai phạm vi thay đổi.

## 20. Dùng JConsole để thực hành

Các bước ở JVM mà bạn có quyền quản trị:

1. Khởi chạy ứng dụng với management bean và annotation-aware exporter đã cấu hình.
2. Mở JConsole/JMC và kết nối đúng JVM.
3. Chọn tab **MBeans**.
4. Tìm domain \`com.example.shop.jobs\`.
5. Mở \`type=WorkerSettings,name=primary\`.
6. Chọn attribute \`MaxConcurrentJobs\`.
7. Xem giá trị hiện tại (8).
8. Thử ghi 12 theo UI hỗ trợ chỉnh sửa.
9. Refresh và xác nhận giá trị mới.
10. Trong test, thử 0 để xem validation error.
11. Khôi phục giá trị 8 nếu cần.
12. Quan sát worker pool có áp dụng thay đổi như contract thiết kế hay không.

UI của JConsole thay đổi theo JDK và khả năng truy cập. Nếu attribute không cho chỉnh sửa, đọc metadata để xác nhận \`isWritable\`. Nếu JConsole không thấy MBean, kiểm tra ObjectName, exporter và MBeanServer, không vội sửa setter.

## 21. Tự kiểm tra JMX metadata bằng Java

Một helper có thể in tất cả attributes:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxAttributeInspector {

    public static void print(MBeanServer server, ObjectName name)
            throws Exception {

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf(
                "%s type=%s readable=%s writable=%s%n",
                a.getName(),
                a.getType(),
                a.isReadable(),
                a.isWritable());
        }
    }
}
~~~

Kết quả mong đợi đối với bài học:

~~~text
MaxConcurrentJobs type=int readable=true writable=true
~~~

Nếu kết quả khác, xem đúng exporter/assembler và MBean mà client đang đọc. Chỉ có \`@ManagedAttribute\` trên getter sẽ thường dẫn tới read-only nếu setter không được công bố.

## 22. Integration test với Spring Test

Một integration test tốt nên dựng ApplicationContext có:
- \`WorkerConcurrencySettings\`.
- \`WorkerSettingsManagement\`.
- Một exporter annotation-aware.
- MBeanServer test riêng.
- Chính sách registration rõ.

Các assertions cần:

1. MBean được đăng ký đúng ObjectName.
2. Attribute \`MaxConcurrentJobs\` tồn tại.
3. \`isReadable\` và \`isWritable\` đều true.
4. \`getType()\` là \`int\`.
5. Giá trị ban đầu 8.
6. \`setAttribute(...,12)\` thành công.
7. Đọc lại trả 12.
8. Settings service đọc 12, không chỉ lớp JMX.
9. Giá trị 0 bị từ chối và giá trị cũ còn nguyên.
10. Bean khác không bị export ngoài ý muốn.
11. Khi context đóng, exporter unregister đúng registrations.

Test nên dùng JUnit/Spring Test với configuration thực tế và một test MBeanServer riêng thay vì sử dụng platform MBeanServer chung của cả test suite.

### Pseudocode kiểm chứng

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.jobs:type=WorkerSettings,name=primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo attr = java.util.Arrays
        .stream(info.getAttributes())
        .filter(a -> "MaxConcurrentJobs".equals(a.getName()))
        .findFirst()
        .orElseThrow();

assertTrue(attr.isReadable());
assertTrue(attr.isWritable());
assertEquals("int", attr.getType());

assertEquals(8, server.getAttribute(name, "MaxConcurrentJobs"));

server.setAttribute(
    name,
    new javax.management.Attribute("MaxConcurrentJobs", 12));

assertEquals(12, server.getAttribute(name, "MaxConcurrentJobs"));
assertEquals(12, settings.currentLimit());
~~~

Đoạn trên là phần assertions, không phải một test standalone đầy đủ. Cần import JUnit assertions, khởi động context và inject đúng MBeanServer/settings.

## 23. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| MBean không xuất hiện | Bean chưa nằm trong context hoặc exporter chưa bật | Kiểm tra component scanning/exporter |
| Attribute chỉ đọc | Setter thiếu annotation hoặc không được metadata nhận diện | Kiểm tra getter/setter, MBeanInfo |
| Attribute không tồn tại | Tên JavaBean property sai hoặc export path khác | Đọc \`MBeanInfo\` |
| \`AttributeNotFoundException\` | Sai tên hoặc không writable | Xác minh \`MaxConcurrentJobs\` |
| \`InvalidAttributeValueException\` | Kiểu hoặc giá trị không hợp lệ | Kiểm tra \`int\`, validation |
| \`MBeanException\` | Setter ném lỗi nghiệp vụ | Đọc cause và log |
| \`ReflectionException\` | Accessor signature/metadata không phù hợp | So sánh setter/getter |
| \`InstanceAlreadyExistsException\` | Hai exporters trùng ObjectName | Một registration owner |
| Ghi 12 nhưng worker vẫn chạy tối đa 8 | Settings không được worker pool áp dụng | Kết nối effective configuration |
| Thay đổi mất sau restart | Runtime-only state | Thiết kế persistence nếu cần |
| Chỉ một pod thay đổi | MBeanServer thuộc một JVM | Có cluster configuration control |
| Setter hoạt động trên local, remote bị chặn | Connector authorization | Kiểm tra JMX permissions |
| Proxy làm annotation không được nhận diện | Spring AOP interface/target resolution | Test annotation assembler với proxy |
| Setter gây quá tải | Giá trị quá lớn hoặc thiếu giới hạn | Validation và guardrails |

## 24. Câu hỏi tự kiểm tra

**1. Vì sao cần cả getter và setter để có attribute đọc–ghi?**  
Vì client cần đường đọc và đường ghi cho cùng JavaBean property; assembler phải công bố cả hai.

**2. Vì sao \`@ManagedAttribute\` không đồng nghĩa với \`@ManagedOperation\`?**  
Vì attribute thể hiện property có getter/setter, còn operation là một action được invoke theo tên và signature.

**3. \`isWritable()\` có đảm bảo mọi client remote được ghi không?**  
Không. Đó là metadata MBean, không phải authorization policy của connector.

**4. Dùng \`AtomicInteger\` đã đủ để thay đổi thread pool concurrency an toàn chưa?**  
Chưa. Nó bảo vệ giá trị cấu hình nhưng phải có cách áp dụng vào executor/worker scheduler, validation và policy khi runtime thay đổi.

**5. Khi set xong đọc lại được 12 nhưng worker vẫn giới hạn 8, sai ở đâu?**  
Management state chưa được phản ánh vào effective worker pool behavior.

**6. JMX setter có tự ghi lại \`application.yml\` không?**  
Không. Mặc định chỉ thay state mà implementation của setter quản lý.

**7. Hai JVM có cùng ObjectName thì một lần ghi có áp dụng cho cả hai không?**  
Không. ObjectName được định danh trong từng MBeanServer; cần cơ chế đồng bộ/rollout riêng.

**8. Có nên expose setter thay đổi cấu hình nhạy cảm trên public remote JMX không?**  
Không. Chỉ expose qua đường quản trị an toàn với authentication, authorization, encryption và network controls phù hợp.

## 25. Bài tập mở rộng

### Bài A — Tạo boolean attribute đọc–ghi

Thêm vào management bean:

~~~java
private final java.util.concurrent.atomic.AtomicBoolean paused =
        new java.util.concurrent.atomic.AtomicBoolean();

@ManagedAttribute
public boolean isPaused() {
    return paused.get();
}

@ManagedAttribute
public void setPaused(boolean value) {
    paused.set(value);
}
~~~

Dùng MBeanInfo kiểm tra \`Paused\` có type \`boolean\`, readable/writable. Thảo luận rằng chỉ đổi flag không tự pause worker nếu worker không đọc flag.

### Bài B — Thêm giới hạn min/max thành read-only

Công bố:

~~~java
@ManagedAttribute
public int getMinimumConcurrency() {
    return WorkerConcurrencySettings.MIN_CONCURRENCY;
}

@ManagedAttribute
public int getMaximumConcurrency() {
    return WorkerConcurrencySettings.MAX_CONCURRENCY;
}
~~~

Hai attributes này nên read-only, giúp người dùng JConsole biết giới hạn áp dụng trước khi ghi.

### Bài C — Trạng thái mong muốn và trạng thái hiệu lực

Thiết kế \`RequestedLimit\` writable và \`EffectiveLimit\` read-only. Khi worker pool mất một khoảng ngắn để áp dụng, operator thấy được cả target và trạng thái đã thực thi. Thêm \`LastAppliedEpochMillis\` và \`LastApplyError\` nếu cần.

### Bài D — Test validation

Thử ghi -1, 0, 65 và giá trị hợp lệ 1, 32, 64. Mỗi lần thử, kiểm tra:
- Exception/cause đúng loại.
- State không đổi sau giá trị sai.
- Giá trị hợp lệ được ghi và đọc lại.
- Worker component được thông báo hoặc áp dụng đúng.

### Bài E — Hai setters phụ thuộc lẫn nhau

Thiết kế \`MinWorkers\` và \`MaxWorkers\`. Giải thích tại sao hai setter độc lập không transactional; đề xuất một operation \`updateLimits(min,max)\` với validation tổng hợp, hoặc immutable settings snapshot được publish atomically.

### Bài F — Kiểm thử permission

Dùng môi trường kiểm thử đã cấu hình hai JMX principals: read-only và readwrite. Xác nhận reader có thể getAttribute nhưng không thể setAttribute, còn operator đủ quyền có thể ghi giá trị hợp lệ. Không làm thử nghiệm bằng cách mở remote connector không xác thực.

## 26. Ghi nhớ

- \`@ManagedResource\` đánh dấu resource; \`@ManagedAttribute\` trên getter/setter giúp công bố cùng một JMX property có quyền đọc/ghi.
- Tên \`getMaxConcurrentJobs\` / \`setMaxConcurrentJobs\` được ánh xạ thành attribute \`MaxConcurrentJobs\`.
- Spring bean phải tồn tại trong context và được exporter/assembler phù hợp xử lý.
- Kiểm tra \`MBeanInfo\` để biết client thật sự thấy \`readable=true\` và \`writable=true\`.
- Dùng \`getAttribute()\` và \`setAttribute()\` để xác minh end-to-end.
- Setter nên có validation, concurrency semantics và chỉ thay đổi cấu hình với tác động rõ.
- JMX writeability khác authorization của JMX connector.
- Runtime JMX changes thường thuộc một JVM và không tự persistence/replicate.
- Không tạo nhiều MBean exporters cùng đăng ký một ObjectName.
- Với các cấu hình nhiều fields phụ thuộc nhau, dùng một operation hoặc atomic configuration update thay vì nhiều setter rời rạc.

## 27. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
