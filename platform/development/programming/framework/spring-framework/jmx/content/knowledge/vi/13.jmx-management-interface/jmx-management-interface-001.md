# Management interface mặc định và mức độ phơi bày public trong Spring JMX

## 1. Vì sao management interface cần được kiểm soát?

Khi xuất một Spring bean qua JMX, câu hỏi quan trọng không chỉ là **MBean có được đăng ký hay không**, mà còn là **client được xem và gọi những gì**. Một lớp Java có thể chứa nhiều public method phục vụ nghiệp vụ hoặc hạ tầng. Nếu giao diện quản trị mặc định vô tình đưa tất cả những method đó ra ngoài, người vận hành hoặc người có quyền kết nối JMX có thể nhìn thấy hành vi mà ứng dụng không chủ ý coi là thao tác quản trị.

Spring Framework cung cấp \`MBeanExporter\` để đăng ký bean với \`MBeanServer\`. Tùy cấu hình, exporter có thể dùng interface JMX chuẩn hoặc tạo mô hình quản trị cho POJO qua \`MBeanInfoAssembler\`. **Quy tắc public method nào được phơi bày phụ thuộc cách exporter xây dựng MBeanInfo**, không thể suy ra chỉ từ việc một method là \`public\`.

Bài này tập trung vào:

- Management interface theo quy ước **Standard MBean** và **MXBean**.
- Management interface do Spring tự tạo từ bean qua assembler mặc định.
- Khác biệt giữa Java \`public\` và “được export qua JMX”.
- Cách giới hạn bề mặt bằng interface, annotation hoặc assembler có chọn lọc.
- Cách kiểm tra bề mặt thực sự qua \`MBeanServer.getMBeanInfo()\`.
- Ảnh hưởng của proxy, quyền truy cập và thay đổi API qua các phiên bản.

## 2. Hai ý nghĩa thường gặp của “management interface”

Trong tài liệu và dự án, cụm “management interface” có thể đề cập đến hai cơ chế:

1. **JMX management interface chuẩn**: Java interface như \`CacheManagerMBean\` mà một class triển khai theo quy tắc Standard MBean, hoặc interface \`CacheManagerMXBean\` theo quy ước MXBean. Interface ấy quy định những thuộc tính và operation có thể được JMX nhìn thấy.
2. **Bề mặt management mà Spring exporter sinh ra**: tập attribute/operation được mô tả bằng \`MBeanInfo\` sau khi exporter dùng assembler, annotation và chính sách include/exclude method.

Ví dụ Standard MBean:

\`\`\`java
public interface CacheAdminMBean {
    int getEntryCount();
    void clearExpired();
}

public class CacheAdmin implements CacheAdminMBean {
    @Override
    public int getEntryCount() {
        return 42;
    }

    @Override
    public void clearExpired() {
        // Thao tác quản trị có kiểm soát.
    }

    public void deleteAllCustomerData() {
        // Public Java method, nhưng không nằm trong CacheAdminMBean.
    }
}
\`\`\`

Khi được đăng ký dưới dạng Standard MBean, \`getEntryCount\` và \`clearExpired\` thuộc management interface. \`deleteAllCustomerData\` là public trong Java nhưng không tự động xuất hiện chỉ vì public.

Ngược lại, nếu Spring được cấu hình để tự expose các public method qua một assembler rộng, \`deleteAllCustomerData\` có thể trở thành operation JMX ngoài ý muốn. Vì thế phải xác định chính xác **đường export đang dùng**.

## 3. Cách Spring MBeanExporter quyết định bề mặt public

\`MBeanExporter\` chịu trách nhiệm chọn các bean, đặt \`ObjectName\`, dựng MBean adapter nếu cần và đăng ký với \`MBeanServer\`.

Đối với một Java object đã là MBean hợp lệ (Standard MBean, MXBean hoặc \`DynamicMBean\`), exporter có thể sử dụng thông tin quản trị do cơ chế JMX chuẩn quy định. Đối với POJO thông thường, Spring có khả năng tạo \`ModelMBean\` bằng các assembler như:

- \`SimpleReflectiveMBeanInfoAssembler\`: khám phá public properties và public methods theo reflection, vì vậy có thể tạo bề mặt rộng.
- \`MethodNameBasedMBeanInfoAssembler\`: chọn các method theo tên cấu hình.
- \`MethodExclusionMBeanInfoAssembler\`: cho phép loại một số method khỏi tập được phơi bày.
- \`InterfaceBasedMBeanInfoAssembler\`: dựa vào một hoặc nhiều interface được chỉ định.
- \`MetadataMBeanInfoAssembler\`: dùng metadata như \`@ManagedAttribute\` và \`@ManagedOperation\`.

Các tên và hành vi cụ thể cần đối chiếu với phiên bản Spring đang sử dụng. Trong cấu hình mặc định phổ biến cho POJO, nếu không cung cấp assembler chọn lọc, việc dựa vào reflection có thể khiến bề mặt quản trị rộng hơn mong đợi.

**Điểm mấu chốt:** \`public\` là điều kiện về khả năng truy cập trong Java. Nó không phải chính sách bảo mật cũng không phải tuyên bố rằng method thích hợp cho JMX. Bề mặt thực tế phải kiểm tra từ MBeanInfo.

## 4. Ví dụ nguy cơ khi export POJO quá rộng

Giả sử một service có nhiều public method:

\`\`\`java
public class ReportService {
    public int getActiveJobs() {
        return 8;
    }

    public void retryFailedJobs() {
        // Lệnh vận hành cần chính sách cho phép.
    }

    public void generateCustomerReport(String customerId) {
        // Use case nghiệp vụ.
    }

    public void purgeHistoricalRecords() {
        // Thao tác có ảnh hưởng lớn.
    }
}
\`\`\`

Nếu một exporter tạo ModelMBean và expose tất cả public methods, client JMX có thể thấy cả \`generateCustomerReport\` và \`purgeHistoricalRecords\`. Điều này tạo ra các rủi ro:

- API quản trị không được thiết kế với ngữ cảnh phân quyền tương đương HTTP.
- Method có thể thiếu validation, audit hoặc guard cho lời gọi từ JMX thread.
- Một operation có thể chạy lâu và chiếm tài nguyên ứng dụng.
- Thay đổi API Java công khai vô tình đổi luôn API quản trị.
- Tool quản trị hoặc automation có thể gọi nhầm method nhạy cảm.

**Không dùng export-all cho service nghiệp vụ lớn** nếu chưa có lý do và kiểm soát chặt chẽ. Lựa chọn an toàn hơn là tạo một adapter hoặc chọn những method cụ thể được quản lý.

## 5. Standard MBean interface: danh sách trắng rõ ràng

Ví dụ tách giao diện quản trị khỏi service:

\`\`\`java
package com.example.reports.jmx;

public interface ReportMonitorMBean {
    int getActiveJobs();
    long getCompletedTotal();
    void requestRetry();
}
\`\`\`

\`\`\`java
package com.example.reports.jmx;

public final class ReportMonitor implements ReportMonitorMBean {
    private final ReportManagement management;

    public ReportMonitor(ReportManagement management) {
        this.management = management;
    }

    @Override
    public int getActiveJobs() {
        return management.snapshot().activeJobs();
    }

    @Override
    public long getCompletedTotal() {
        return management.snapshot().completedTotal();
    }

    @Override
    public void requestRetry() {
        management.requestRetry();
    }
}
\`\`\`

\`ReportManagement\` là interface ứng dụng chứa truy vấn và lệnh quản trị độc lập JMX:

\`\`\`java
public interface ReportManagement {
    ReportSnapshot snapshot();
    void requestRetry();
}

public record ReportSnapshot(
    int activeJobs,
    long completedTotal
) {}
\`\`\`

Trong Standard MBean, interface \`ReportMonitorMBean\` chính là hợp đồng JMX. Những method public khác trên \`ReportMonitor\` không thuộc giao diện này sẽ không tự động trở thành operation JMX.

Khi đăng ký trực tiếp:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.reports:type=Monitor,name=Primary"
);

server.registerMBean(new ReportMonitor(management), name);
\`\`\`

Biến \`management\` là dependency đã được cung cấp bởi ứng dụng. Trong Spring, bạn cũng có thể inject nó vào bean adapter và để exporter quản lý registration/lifecycle.

## 6. Spring annotation: chỉ chọn attribute và operation có chủ đích

Một cách khác là xây adapter với annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.reports:type=Monitor,name=Primary",
    description = "Safe report management API"
)
public final class ReportJmxAdapter {
    private final ReportManagement management;

    public ReportJmxAdapter(ReportManagement management) {
        this.management = management;
    }

    @ManagedAttribute(description = "Currently active reports")
    public int getActiveJobs() {
        return management.snapshot().activeJobs();
    }

    @ManagedAttribute(description = "Completed reports since startup")
    public long getCompletedTotal() {
        return management.snapshot().completedTotal();
    }

    @ManagedOperation(description = "Request retry of failed reports")
    public void retryFailed() {
        management.requestRetry();
    }

    public void internalHelper() {
        // Public method nhưng không được đánh dấu quản trị.
    }
}
\`\`\`

Nếu exporter dùng \`MetadataMBeanInfoAssembler\` với metadata source phù hợp, chỉ những getter/operation được quản trị theo annotation và các quy tắc metadata mới trở thành bề mặt JMX. \`@ManagedResource\` định nghĩa bean quản trị; nó không tự động biến mọi public method thành operation.

Chú ý rằng \`@ManagedOperation\` cũng không tự tạo authentication hoặc authorization. Những lệnh quản trị có tác động vẫn cần kiểm soát ở connector và tầng ứng dụng.

## 7. Cấu hình exporter dùng metadata annotation

Với Spring Framework cấu hình Java thuần:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {
    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
            AnnotationJmxAttributeSource source) {
        var assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        var naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
\`\`\`

Trong dự án Spring Boot, JMX auto-configuration có thể tạo exporter khi bật \`spring.jmx.enabled=true\`. Kiểm tra exporter thực tế và phiên bản Spring/Boot trước khi thêm một exporter thủ công, tránh trùng \`ObjectName\` hoặc đăng ký cùng bean nhiều lần.

\`AnnotationJmxAttributeSource\` đọc metadata; \`MetadataMBeanInfoAssembler\` chọn các attribute/operation; \`MetadataNamingStrategy\` giải quyết tên MBean. Chúng phục vụ các trách nhiệm khác nhau, vì thế một annotation xuất hiện trên class không bảo đảm toàn bộ cấu hình đã hoạt động.

## 8. InterfaceBasedMBeanInfoAssembler: chọn phương thức theo interface

Khi không muốn đưa annotation JMX vào service, có thể cấu hình Spring assembler dựa trên interface. Ví dụ:

\`\`\`java
public interface ReportManagementView {
    int getActiveJobs();
    long getCompletedTotal();
}
\`\`\`

Implementation có nhiều public method khác, nhưng giao diện quan sát chỉ có hai getter. Một cấu hình mẫu:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

InterfaceBasedMBeanInfoAssembler assembler =
    new InterfaceBasedMBeanInfoAssembler();

assembler.setManagedInterfaces(
    new Class<?>[] { ReportManagementView.class }
);

MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
exporter.setBeans(
    java.util.Map.of(
        "com.example.reports:type=View,name=Primary",
        reportService
    )
);
\`\`\`

Đoạn trên minh họa một exporter riêng; cần đặt vào cấu hình Spring hợp lệ với bean \`reportService\` do container cung cấp. Interface được chọn mô tả các method đủ điều kiện xuất theo assembler, không nhất thiết là một Standard MBean interface có hậu tố \`MBean\`.

Khi dự án đã có management interface ứng dụng riêng, dùng interface-based assembler giúp giới hạn bề mặt mà không cần bổ sung annotation vào nhiều method. Nếu interface đó chứa lệnh nhạy cảm, vẫn cần tách hoặc giới hạn tiếp.

## 9. Chọn method theo tên và loại trừ method

Với một codebase cũ chưa thể tách adapter ngay, Spring có những assembler chọn theo tên hoặc loại trừ theo tên:

\`\`\`java
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

MethodNameBasedMBeanInfoAssembler assembler =
    new MethodNameBasedMBeanInfoAssembler();

assembler.setManagedMethods(
    "getActiveJobs",
    "getCompletedTotal",
    "requestRetry"
);
\`\`\`

Đây là cách tạo danh sách cho phép (allowlist) theo method name. Khi có overload, cần hiểu cách assembler xử lý phương thức cùng tên. Không nên coi tên method đơn lẻ là một quyền truy cập đầy đủ; các signature, kiểu tham số và vai trò method phải được kiểm tra thực tế từ \`MBeanInfo\`.

Một cách loại trừ:

\`\`\`java
import org.springframework.jmx.export.assembler.MethodExclusionMBeanInfoAssembler;

MethodExclusionMBeanInfoAssembler assembler =
    new MethodExclusionMBeanInfoAssembler();

assembler.setIgnoredMethods(
    "purgeHistoricalRecords",
    "generateCustomerReport"
);
\`\`\`

Danh sách loại trừ là phương án chuyển tiếp khi cần duy trì bề mặt rộng của một hệ thống cũ. Với hệ thống có yêu cầu an toàn và ổn định cao, allowlist hoặc adapter riêng thường dễ quản lý hơn vì method public mới sẽ không tự được expose.

## 10. Public Java method khác JMX operation

Xét:

\`\`\`java
public class Example {
    public int getCount() { return 10; }
    public boolean isRunning() { return true; }
    public void setThreshold(int value) { }
    public void reset() { }
    public String debugDump() { return "internal"; }
}
\`\`\`

Một assembler phản chiếu có thể diễn giải:

- \`getCount()\` thành readable attribute \`Count\`.
- \`isRunning()\` thành boolean attribute \`Running\`.
- \`setThreshold(int)\` thành writable attribute \`Threshold\` nếu được chọn.
- \`reset()\` thành operation.
- \`debugDump()\` thành operation hoặc một method được xét theo quy tắc assembler.

Nhưng các mapping thực tế phụ thuộc assembler, bean type và hợp đồng JMX. Một getter Java không nhất thiết được đọc qua JMX nếu không thuộc management interface.

**Đặc biệt chú ý setter:** public setter có thể cho phép sửa trạng thái mà API nghiệp vụ dự kiến chỉ nội bộ được phép sửa. Không đưa writable attribute ra JMX trừ khi đã định nghĩa range hợp lệ, authorization, audit và tác động tới concurrency/lifecycle.

## 11. Không xuất DTO lớn và method có chi phí cao

Giới hạn danh sách public method là một phần của thiết kế quản trị. Một operation có thể bị gọi từ console người vận hành, script hoặc dashboard, với đặc điểm khác luồng ứng dụng bình thường:

- \`getAllUsers()\`: trả dữ liệu nhạy cảm, khối lượng lớn.
- \`getEntireCache()\`: serialization tốn bộ nhớ.
- \`rebuildIndex()\`: chạy lâu, tạo áp lực CPU/IO.
- \`changeDatabaseUrl(...)\`: thay đổi cấu hình quan trọng.
- \`deleteAll()\`: thao tác phá hủy dữ liệu.

Kể cả khi những method này public để phục vụ integration test hoặc ứng dụng nội bộ, chúng không vì thế trở thành API quản trị phù hợp. Bề mặt JMX tốt thường thiên về **snapshot đọc nhanh** và **lệnh rõ ý nghĩa, có giới hạn**.

Với dữ liệu quản trị phức tạp, chuyển thành scalar hoặc Open MBean types được mapping rõ; hạn chế payload và không trả reference mutable của domain object.

## 12. Ảnh hưởng của JDK proxy và CGLIB proxy

Spring AOP có thể thay object runtime bằng JDK dynamic proxy hoặc CGLIB proxy:

- JDK proxy thường expose các method thuộc interface mà proxy thực hiện.
- CGLIB proxy là subclass của target nhưng không thể override một số method như \`final\`.
- Metadata annotation có thể nằm trên target class trong khi exporter nhận một proxy.
- Nếu management interface chọn method không khả dụng qua proxy, \`MBeanInfo\` và invocation có thể không khớp.

Ví dụ kiểm tra:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("reportService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

\`context\` là \`ApplicationContext\` đã được inject, không phải biến có sẵn toàn cục. Khi có proxy, một adapter JMX riêng inject business/management port qua interface thường ổn định hơn xuất trực tiếp class nghiệp vụ.

Không giả định rằng đổi \`proxyTargetClass=true\` tự giải quyết được mọi lỗi JMX. Nó có thể ảnh hưởng nhiều bean AOP khác và không sửa được exporter đang chọn nhầm assembler hoặc ObjectName.

## 13. Kiểm tra chính xác những gì đã xuất bằng MBeanInfo

Cách kiểm chứng đáng tin cậy là hỏi \`MBeanServer\` sau khi đăng ký:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.reports:type=Monitor,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered: " + name);
}

MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s readable=%s writable=%s%n",
        attr.getName(), attr.isReadable(), attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("Operation=" + operation.getName());
}
\`\`\`

Probe này phải dùng đúng \`MBeanServer\` mà exporter đăng ký; nếu ứng dụng dùng server riêng, thay platform server bằng instance được inject. Đọc MBeanInfo giúp biết mặt JMX thực tế được xuất, không chỉ những gì developer dự kiến từ annotation hoặc interface.

Cũng nên so sánh **operation signature** và **impact** theo \`MBeanOperationInfo\`, đặc biệt khi có overload hoặc method nhận tham số phức tạp.

## 14. Kiểm thử bề mặt public bằng danh sách cho phép

Một integration test có thể assert những operation được expose:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;

class JmxSurfaceAssertions {
    static void assertSafeSurface(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.reports:type=Monitor,name=Primary"
        );

        var info = server.getMBeanInfo(name);

        Set<String> operations = Arrays.stream(info.getOperations())
            .map(op -> op.getName())
            .collect(Collectors.toSet());

        assertTrue(operations.contains("retryFailed"));
        assertFalse(operations.contains("deleteAllCustomerData"));
        assertFalse(operations.contains("purgeHistoricalRecords"));
    }
}
\`\`\`

Với contract nghiêm ngặt, test một danh sách chính xác cả **attribute name, read/write flags, operation name, signature** và loại dữ liệu. Cách này phát hiện regressions khi ai đó thêm method public mới hoặc thay cấu hình assembler.

Không test bằng việc quét tất cả public method của Java class rồi tự dự đoán mapping. \`MBeanInfo\` là thứ JMX client thực sự nhìn thấy.

## 15. Ranh giới bảo mật của management interface

Không nên xem “chỉ public method” là biện pháp bảo mật. Truy cập JMX có thể có quyền quan sát và thực thi operation, tùy connector, authentication, TLS và cơ chế authorization được cấu hình. Một API quản trị được giới hạn tốt vẫn cần:

1. **Giới hạn exposure** bằng interface/annotation/assembler chọn lọc.
2. **Giới hạn truy cập network** tới JMX connector, không công khai cổng quản trị không cần thiết.
3. **Xác thực và phân quyền** cho client và operation có tác động.
4. **Kiểm tra điều kiện ở application layer** khi thực thi lệnh quản trị.
5. **Audit** đối với thay đổi trạng thái quan trọng.
6. **Giới hạn chi phí** của getter và operation để client không thể gây quá tải do polling hoặc gọi lặp.

Một management interface chỉ có read-only attributes có thể được vận hành an toàn hơn, nhưng vẫn có thể làm lộ số liệu nhạy cảm như tenant ID, đường dẫn hệ thống hoặc dữ liệu khách hàng. Hãy xem cả danh tính MBean (\`ObjectName\`) và payload của attribute.

## 16. Lựa chọn chiến lược theo quy mô dự án

| Chiến lược | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Standard MBean interface | Ranh giới rõ, Java/JMX chuẩn | Cần duy trì interface JMX |
| Spring annotation + Metadata assembler | Chọn attribute/operation gần adapter | Phụ thuộc cấu hình Spring exporter |
| InterfaceBased assembler | Tách hợp đồng bằng interface | Cần quản lý mapping/proxy |
| MethodNameBased assembler | Thích hợp codebase cũ, allowlist nhanh | String method names dễ lệch khi refactor |
| MethodExclusion assembler | Có thể giữ contract cũ khi cần loại vài method | Public method mới có thể vô tình được phơi bày |
| Reflective export rộng | Cấu hình nhanh để demo nội bộ | Khó kiểm soát bề mặt và thay đổi API |

Với một ứng dụng đang phát triển, ưu tiên **adapter quản trị riêng + danh sách method được phép**. Khi thực sự cần export một bean theo giao diện mặc định rộng, hãy có integration test xác minh chính xác \`MBeanInfo\`.

## 17. Quy trình thực hành

Khi thiết kế hoặc rà soát một MBean:

1. Ghi lại \`ObjectName\`, bean owner và exporter đang sử dụng.
2. Xác định Standard MBean/MXBean hay POJO được Spring ModelMBean export.
3. Xác định assembler và naming strategy thực tế.
4. Liệt kê những attribute và operation **được phép**, bao gồm read/write semantics.
5. Loại bỏ public method nghiệp vụ, debug và maintenance không thuộc quản trị.
6. Kiểm tra proxy/interface nếu AOP đang áp dụng.
7. Khởi động context test và đọc \`MBeanInfo\` trên đúng server.
8. Test rằng method mới không vô tình xuất hiện trên JMX.
9. Kiểm tra authentication, authorization và audit cho các lệnh có tác động.
10. Duy trì management interface như một hợp đồng công khai có versioning và kiểm soát thay đổi.

## 18. Ghi nhớ

**Java \`public\` không đồng nghĩa được phép export qua JMX.** Standard MBean/MXBean dùng giao diện quản trị được định nghĩa rõ, còn Spring có thể tạo bề mặt từ POJO theo assembler. Một assembler mặc định dựa trên reflection có thể xuất nhiều public method hơn dự kiến. Để giữ API quản trị nhỏ và an toàn, hãy chọn interface/annotation/allowlist có chủ đích và dùng \`MBeanServer.getMBeanInfo()\` để xác minh chính xác những gì client thực sự nhìn thấy.
