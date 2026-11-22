# Migration từ XML exporter sang Java Config trong Spring Framework JMX

## Mục tiêu học tập

Bài học thuộc phần **Spring configuration** của Spring Framework JMX. Sau khi hoàn thành, bạn có thể:

- Chuyển cấu hình JMX bằng XML sang Java Config với \`@Configuration\` và \`@Bean\` mà không thay đổi ý nghĩa của các MBean đã công bố.
- Nhận diện các thành phần XML như \`MBeanExporter\`, \`MBeanServer\`, \`assembler\`, \`namingStrategy\`, \`registrationPolicy\`, bản đồ \`beans\` và cấu hình annotation-based exporting.
- Bảo toàn \`ObjectName\`, management interface, attributes/operations, hành vi xử lý trùng tên và vòng đời container.
- Phân biệt \`MBeanExporter\` tường minh với \`@EnableMBeanExport\` và \`AnnotationMBeanExporter\`.
- Kiểm tra migration bằng \`MBeanServer\`, \`MBeanInfo\`, JConsole và integration test.
- Lập kế hoạch chuyển đổi có khả năng rollback, tránh hai exporters cùng đăng ký một \`ObjectName\`.

## 1. Vì sao cần migration?

Nhiều dự án Spring Framework cũ dùng \`applicationContext.xml\` hoặc \`spring-jmx.xml\` để khai báo các bean quản trị JMX. Khi codebase chuyển dần sang Java Config, các XML bean definitions có thể được thay bằng các factory method \`@Bean\`, cho phép quản lý dependency bằng kiểu Java, IDE navigation và cấu hình gần với implementation hơn.

Ví dụ cấu hình cũ:

\`\`\`xml
<bean id="mBeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.jobs:type=JobMonitor,name=primary"
                   value-ref="jobMonitor"/>
        </map>
    </property>
</bean>
\`\`\`

Một cấu hình Java Config tương đương về mục tiêu:

\`\`\`java
@Bean
public MBeanExporter mBeanExporter(JobMonitor jobMonitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            jobMonitor));
    return exporter;
}
\`\`\`

Điểm chính của migration là **giữ nguyên hợp đồng quản trị runtime**, không phải chỉ viết lại cú pháp từ XML thành Java. Những công cụ giám sát phụ thuộc \`ObjectName\`, tên attribute, chữ ký operation và endpoint/server JMX. Thay đổi vô ý một trong các yếu tố này có thể khiến dashboard hoặc thao tác quản trị không còn hoạt động.

## 2. Kiến trúc trước và sau migration

\`\`\`text
Trước:
  XML BeanDefinitions
      |
      +-- jobMonitor
      +-- mBeanServer
      +-- mBeanExporter
             |
             +-- ObjectName -> jobMonitor
             v
          MBeanServer

Sau:
  @Configuration class
      |
      +-- @Bean JobMonitor
      +-- @Bean MBeanServer
      +-- @Bean MBeanExporter
             |
             +-- ObjectName -> jobMonitor
             v
          MBeanServer
\`\`\`

Cả hai đường cuối cùng đều cấu hình các Spring beans. Java Config không loại bỏ \`MBeanExporter\` hay \`MBeanServer\`; nó chỉ thay cách khai báo và liên kết chúng.

Cũng không nhất thiết phải migrate tất cả XML trong một lần. Spring có thể kết hợp Java Config với XML thông qua \`@ImportResource\`, nhưng khi chuyển phần JMX cần xác định chính xác **exporter nào đang hoạt động** để tránh trùng tên đăng ký.

## 3. Những phần cấu hình cần kiểm kê trước khi chuyển

Một sơ đồ đối chiếu quan trọng:

| Trong XML | Trong Java Config | Điều cần giữ nguyên |
| --- | --- | --- |
| \`<bean id="jobMonitor" class="..."/>\` | \`@Bean JobMonitor jobMonitor()\` | Cùng managed object/lifecycle |
| \`<bean ... MBeanExporter>\` | \`@Bean MBeanExporter mBeanExporter(...)\` | Có một exporter phù hợp |
| \`<property name="beans"><map>...\` | \`exporter.setBeans(Map.of(...))\` | Chính xác từng \`ObjectName\` |
| \`<property name="server" ref="..."/>\` | \`exporter.setServer(server)\` | Cùng \`MBeanServer\` |
| \`<property name="assembler" ref="..."/>\` | \`exporter.setAssembler(assembler)\` | Cùng attributes/operations |
| \`<property name="namingStrategy" ref="..."/>\` | \`exporter.setNamingStrategy(strategy)\` | Tên JMX cuối cùng |
| \`<property name="registrationPolicy" .../>\` | \`setRegistrationPolicy(...)\` | Cách xử lý tên trùng |
| \`<context:mbean-export/>\` | \`@EnableMBeanExport\` | Chế độ phát hiện annotation phù hợp |
| \`<context:component-scan .../>\` | \`@ComponentScan\` hoặc \`@Bean\` | Bean cần xuất vẫn nằm trong context |

Không giả định hai cách cấu hình tự động tương đương nếu XML đang dùng assembler, naming strategy hoặc autodetection tùy chỉnh. Khi đó, migration phải chuyển **toàn bộ cấu hình liên quan**, không chỉ phần \`beans\`.

## 4. Ví dụ Standard MBean cho migration

Giả sử hệ thống đang công bố một \`JobMonitor\` để các công cụ JMX đọc số công việc đã xử lý.

**JobMonitorMBean.java**

\`\`\`java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
\`\`\`

**JobMonitor.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void reset() {
        processed.set(0);
    }
}
\`\`\`

Đây là Standard MBean: interface \`JobMonitorMBean\` có hậu tố phù hợp với implementation \`JobMonitor\`. Khi export, JMX công bố attribute \`ProcessedCount\`, attribute \`Enabled\` đọc/ghi và operation \`reset\`.

Method \`recordProcessedJob()\` không nằm trong interface Standard MBean nên không được tự động công bố qua interface đó. Điều này giúp management API ổn định khi chuyển cách cấu hình.

## 5. Cấu hình XML đầy đủ trước migration

Một ví dụ cũ có tường minh platform server và exporter:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="jobMonitor"
          class="com.example.jmx.JobMonitor"/>

    <bean id="platformMBeanServer"
          class="org.springframework.jmx.support.MBeanServerFactoryBean">
        <property name="locateExistingServerIfPossible" value="true"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="server" ref="platformMBeanServer"/>

        <property name="beans">
            <map>
                <entry
                    key="com.example.jobs:type=JobMonitor,name=primary"
                    value-ref="jobMonitor"/>
            </map>
        </property>
    </bean>
</beans>
\`\`\`

Cấu hình này chỉ minh họa cách XML khai báo server và exporter. \`MBeanServerFactoryBean\` với chế độ tìm existing server có thể tìm một server phù hợp hoặc tạo server mới nếu không có; nó **không bảo đảm trong mọi môi trường** sẽ chọn đúng platform \`MBeanServer\`. Muốn giữ đúng server khi migrate, cần xác minh server thực tế trước đó.

Nếu XML cũ đã có một \`MBeanServer\` bean khác hoặc ứng dụng chạy trong application server cung cấp JMX registry, hãy dùng cùng server dự kiến thay vì máy móc thay thành platform server.

## 6. Cấu hình Java Config tương ứng

**JmxConfiguration.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            JobMonitor jobMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jobs:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }
}
\`\`\`

So với XML, mọi dependency được inject qua tham số factory method. Spring biết \`mBeanExporter\` phụ thuộc vào \`jobMonitor\` và \`platformMBeanServer\`, giúp container quản lý lifecycle có chủ đích.

**Điểm khác cần kiểm soát:** Java Config này chọn platform server **tường minh**. Nếu XML cũ đang sử dụng server khác được tìm tự động, đây là một thay đổi hành vi. Khi migration yêu cầu tương đương tuyệt đối, nên inject đúng \`MBeanServer\` mà ứng dụng đang dùng, không đơn giản thay vì tiện cho JConsole.

## 7. Chạy ApplicationContext Java Config và xác minh MBean

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxMigrationDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor jobMonitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            jobMonitor.recordProcessedJob();
            jobMonitor.recordProcessedJob();

            System.out.println(
                    "ProcessedCount via JMX: "
                    + server.getAttribute(name, "ProcessedCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read(); // Giữ demo chạy để kiểm tra JConsole.
        }
    }
}
\`\`\`

Dấu hiệu kỳ vọng là \`Registered: true\` và \`ProcessedCount via JMX: 2\`. Đọc \`ProcessedCount\` qua \`MBeanServer\` giúp chứng minh MBean thực sự được export và phản ánh cùng Spring bean.

JConsole có thể kết nối đến PID ứng dụng, mở tab **MBeans** rồi tìm domain \`com.example.jobs\`. Các công cụ quản trị hiện tại chỉ cần giữ nguyên \`ObjectName\` và management interface là có thể sử dụng cùng tên và metadata, nếu endpoint JMX không đổi.

## 8. Không chạy XML exporter và Java Config exporter đồng thời

Đây là lỗi migration dễ gặp nhất. Một hệ thống có thể import XML cũ trong khi Java Config mới cũng được load:

\`\`\`java
@Configuration
@ImportResource("classpath:spring-jmx.xml")
public class AppConfiguration {
    // Nếu còn khai báo @Bean MBeanExporter cho cùng ObjectName,
    // cả hai exporter có thể cố đăng ký trùng.
}
\`\`\`

Nếu hai exporters đăng ký cùng \`ObjectName\` trong một \`MBeanServer\`, registration mới có thể thất bại với \`InstanceAlreadyExistsException\`. Nếu chính sách \`IGNORE_EXISTING\` được bật, startup có thể qua nhưng exporter mới bị bỏ qua, khiến JMX client vẫn đọc instance cũ. Nếu \`REPLACE_EXISTING\`, có thể thay đối tượng mà công cụ giám sát đang sử dụng.

Quy trình migration thích hợp:

1. Xác định exporter cũ trong XML và các tên mà nó đăng ký.
2. Tạo Java Config tương ứng nhưng **không bật song song cùng đăng ký** ở runtime.
3. Trong một môi trường thử nghiệm tách biệt, thay XML exporter bằng Java Config exporter.
4. Kiểm tra \`ObjectName\`, \`MBeanInfo\`, attribute/operation và lifecycle.
5. Khi kết quả ổn định, gỡ hoặc ngừng import định nghĩa exporter cũ.

Nếu cần giữ các XML bean definitions khác, có thể tách riêng \`spring-jmx.xml\` để ngừng import phần export trước, không cần viết lại toàn bộ cấu hình hệ thống trong cùng đợt.

## 9. Chuyển registrationPolicy

Trong XML, có thể cấu hình:

\`\`\`xml
<property name="registrationPolicy" value="FAIL_ON_EXISTING"/>
\`\`\`

Trong Java Config:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
\`\`\`

Các policy cần biết:

| Policy | Nếu \`ObjectName\` đã tồn tại | Ý nghĩa migration |
| --- | --- | --- |
| \`FAIL_ON_EXISTING\` | Dừng với lỗi đăng ký | Phát hiện cấu hình XML/Java còn trùng |
| \`IGNORE_EXISTING\` | Giữ MBean đã có | Có thể che việc exporter mới chưa hoạt động |
| \`REPLACE_EXISTING\` | Thay MBean cũ | Có thể gây thay đổi owner bất ngờ |

Với migration, \`FAIL_ON_EXISTING\` thường hữu ích trong giai đoạn kiểm chứng vì lỗi trùng không bị che. Tuy nhiên, nếu XML cũ cố tình dùng policy khác theo thiết kế, migration tương đương phải giữ hành vi đó hoặc thay đổi có chủ đích kèm đánh giá tác động.

Spring Framework phiên bản cũ có thể dùng hằng integer \`REGISTRATION_FAIL_ON_EXISTING\` hoặc setter khác. Cần kiểm tra API của phiên bản dự án trước khi chuyển nguyên văn.

## 10. Chuyển MBeanInfoAssembler và management interface

Một số XML exporters không export Standard MBean mà export POJO qua \`MBeanInfoAssembler\`. Trong trường hợp đó, chỉ chuyển \`setBeans\` là chưa đủ: nếu bỏ assembler, tập attributes/operations có thể thay đổi.

Ví dụ XML cũ dùng \`MethodNameBasedMBeanInfoAssembler\`:

\`\`\`xml
<bean id="jobAssembler"
      class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
    <property name="managedMethods">
        <list>
            <value>getProcessedCount</value>
            <value>reset</value>
        </list>
    </property>
</bean>

<bean id="mBeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="assembler" ref="jobAssembler"/>
    <property name="beans">
        <map>
            <entry key="com.example.jobs:type=JobAdmin,name=primary"
                   value-ref="jobAdmin"/>
        </map>
    </property>
</bean>
\`\`\`

Java Config tương ứng:

\`\`\`java
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Bean
public MethodNameBasedMBeanInfoAssembler jobAssembler() {
    MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
    assembler.setManagedMethods("getProcessedCount", "reset");
    return assembler;
}

@Bean
public MBeanExporter mBeanExporter(
        JobAdmin jobAdmin,
        MBeanServer platformMBeanServer,
        MethodNameBasedMBeanInfoAssembler jobAssembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setAssembler(jobAssembler);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobAdmin,name=primary",
            jobAdmin));
    return exporter;
}
\`\`\`

Đây là **một cấu hình thay thế** cho exporter Standard MBean ở mục 6, không nên khai báo đồng thời hai \`@Bean\` methods cùng tên \`mBeanExporter\` trong một configuration. Ví dụ cũng giả định \`JobAdmin\` là class POJO ứng dụng đã có và có hai method được liệt kê.

Nếu XML dùng \`InterfaceBasedMBeanInfoAssembler\` hoặc \`MetadataMBeanInfoAssembler\`, cần chuyển đúng interface metadata hoặc attribute source và naming strategy tương ứng. Sau đó đọc \`MBeanInfo\` để xác minh hợp đồng không bị mở rộng hoặc thu hẹp ngoài ý muốn.

## 11. Chuyển namingStrategy

Trong XML có thể có:

\`\`\`xml
<property name="namingStrategy" ref="jmxNamingStrategy"/>
\`\`\`

Java Config tương ứng truyền strategy qua constructor/factory method \`@Bean\` rồi gọi:

\`\`\`java
exporter.setNamingStrategy(jmxNamingStrategy);
\`\`\`

Các strategy thường gặp:

- \`KeyNamingStrategy\`: xử lý tên qua key/mapping cấu hình.
- \`MetadataNamingStrategy\`: đọc \`ObjectName\` từ metadata như \`@ManagedResource\`.
- \`IdentityNamingStrategy\`: giúp phân biệt các instance bằng identity runtime.

Để không thay đổi dashboard hiện tại, hãy giữ nguyên full \`ObjectName\` bao gồm domain và key properties. Một migration vô tình thay \`name=primary\` thành tên dựa trên class hoặc bean name có thể khiến monitoring không tìm thấy mục tiêu cũ.

Các key như \`type\`, \`name\`, \`pool\`, \`tenant\` do dự án quy ước, không phải bắt buộc của Java. Nếu dùng thuộc tính có ký tự đặc biệt, tạo \`ObjectName\` hợp lệ và quote/escape đúng.

## 12. Chuyển XML annotation exporter sang @EnableMBeanExport

Nếu XML cũ bật annotation exporting:

\`\`\`xml
<context:mbean-export
    xmlns:context="http://www.springframework.org/schema/context"
    default-domain="com.example.management"/>
\`\`\`

thì hướng Java Config thường là:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(defaultDomain = "com.example.management")
public class JmxAnnotationConfiguration {
}
\`\`\`

Một managed bean có thể được chú thích:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.management:type=CacheAdmin,name=primary")
public class CacheAdmin {

    @ManagedAttribute
    public int getCacheSize() {
        return 10;
    }

    @ManagedOperation
    public void resetCacheStatistics() {
        // Logic quản trị...
    }
}
\`\`\`

Để Spring JMX autodetection thấy class, object cần được đăng ký thành bean của \`ApplicationContext\` qua \`@Bean\`, \`@Component\` + component scan hoặc cơ chế phù hợp. \`@ManagedResource\` không tự thay thế \`@Component\`.

Một cấu hình đầy đủ:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(defaultDomain = "com.example.management")
public class JmxAnnotationConfiguration {

    @Bean
    public CacheAdmin cacheAdmin() {
        return new CacheAdmin();
    }
}
\`\`\`

Nếu XML đang dùng \`<context:mbean-export/>\` cùng assembler/naming options riêng, cần xác minh thuộc tính Java annotation support tương đương trong Spring version thực tế; không tự suy luận mọi XML attribute đều có cùng Java annotation attribute.

**Quan trọng:** Không chuyển một exporter tường minh sang \`@EnableMBeanExport\` mà chưa kiểm tra tập bean được phát hiện. Annotation mode và explicit \`setBeans\` có thể xuất các đối tượng khác nhau.

## 13. Chuyển MBeanServer và quyền sở hữu server

XML thường tham chiếu một \`MBeanServerFactoryBean\` hoặc server được tạo bên ngoài Spring:

\`\`\`xml
<bean id="applicationMBeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean">
    <property name="defaultDomain" value="com.example.management"/>
    <property name="locateExistingServerIfPossible" value="false"/>
</bean>
\`\`\`

Java Config:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
\`\`\`

\`MBeanServerFactoryBean\` là Spring \`FactoryBean\`; các bean khác inject một \`MBeanServer\` được factory cung cấp. Khi factory tạo server riêng, Spring quản lý lifecycle của factory để release server theo trách nhiệm. Nếu server được mượn từ JVM hoặc container khác, việc đóng Spring context không có nghĩa Spring có quyền giải phóng server đó.

Khi chuyển đổi, bảo toàn lựa chọn giữa **server được mượn** và **server do ứng dụng tạo**. Một thay đổi từ custom server sang platform server có thể đổi phạm vi registry và cách JConsole/JMX connector truy cập, dù \`ObjectName\` không đổi.

## 14. Cách migrate từng phần khi còn XML khác

Với dự án lớn, migration có thể theo giai đoạn:

**Giai đoạn 1 — Giữ XML nghiệp vụ, thay JMX config.** Tạo \`JmxConfiguration\` có exporter mới; loại bỏ chỉ bean exporter cũ khỏi XML, giữ các XML bean definitions còn cần.

**Giai đoạn 2 — Thống nhất bean references.** Nếu \`JobMonitor\` đã nằm trong XML, Java Config có thể inject bean đó mà không tạo \`@Bean JobMonitor\` lần thứ hai:

\`\`\`java
@Bean
public MBeanExporter mBeanExporter(
        JobMonitor existingMonitor,
        MBeanServer existingServer) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(existingServer);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            existingMonitor));
    return exporter;
}
\`\`\`

Cách này tránh tình huống JMX quản lý instance mới trong khi nghiệp vụ vẫn dùng instance cũ từ XML.

**Giai đoạn 3 — Chuyển bean definitions còn lại.** Thay \`<bean>\` bằng \`@Bean\` hoặc component scanning, đồng thời giữ \`@Qualifier\`, scope, init/destroy callbacks và dependency injection nếu các cấu hình đó ảnh hưởng runtime.

**Giai đoạn 4 — Gỡ XML JMX cũ.** Khi không còn phần config JMX nào được dùng, ngừng import file cũ. Kiểm tra rằng không có bean exporter ẩn từ một auto-configuration khác.

Không cần chuyển cả hệ thống ngay để đổi cách khai báo JMX, nhưng cần có **một owner duy nhất cho mỗi registration**.

## 15. Spring Boot: tránh đè auto-configuration

Khi dự án Spring Boot được cấu hình để bật JMX, Boot có thể tạo cơ sở hạ tầng export theo dependency và thuộc tính như \`spring.jmx.enabled\`, với hành vi phụ thuộc phiên bản. Nếu bạn tự thêm \`MBeanExporter\` bằng \`@Configuration\`, có thể vô tình thêm một exporter thứ hai.

Trước khi migration trong Spring Boot:

1. Xác định version Boot và trạng thái JMX auto-configuration.
2. Xác định exporter đang hoạt động và các bean được export.
3. Kiểm tra những \`ObjectName\` cần bảo toàn.
4. Quyết định dùng auto-config/annotation hoặc exporter thủ công, không chồng chéo cùng tên.
5. Kiểm tra integration test với đúng profile và môi trường của ứng dụng.

Không giả định rằng thêm \`@EnableMBeanExport\` là bước bắt buộc trong mọi Spring Boot application. Với Spring Framework thuần, annotation đó là cách kích hoạt annotation-driven exporting, nhưng trong Boot cần xét cấu hình sẵn có.

## 16. Integration test kiểm chứng tương đương XML và Java Config

Một migration đáng tin cậy cần kiểm chứng hành vi cuối cùng, không chỉ nhìn vào cấu trúc bean declarations.

Ví dụ test Java Config:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxMigrationTest {

    @Test
    void javaConfigExportsExpectedMBeanContract() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            JobMonitor monitor = context.getBean(JobMonitor.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(java.util.Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "ProcessedCount".equals(a.getName())));

            assertTrue(java.util.Arrays.stream(info.getOperations())
                    .anyMatch(o -> "reset".equals(o.getName())));

            monitor.recordProcessedJob();

            assertEquals(
                    1, server.getAttribute(name, "ProcessedCount"));

            server.invoke(name, "reset",
                    new Object[0], new String[0]);

            assertEquals(
                    0, server.getAttribute(name, "ProcessedCount"));
        }
    }
}
\`\`\`

Test chứng minh registration, attribute và operation theo cấu hình mới. Để xác minh **tương đương với XML**, chạy cấu hình cũ và mới trong hai test fixtures tách biệt, lấy \`MBeanInfo\` và so sánh danh sách name/type/access của attributes, operation signatures, cùng toàn bộ \`ObjectName\` mà ứng dụng muốn công bố.

Tránh khởi tạo XML và Java exporters cùng tên trong cùng platform \`MBeanServer\` khi test chạy song song. Có thể dùng hai MBean servers cô lập hoặc chạy lần lượt với cleanup đầy đủ. Khi dữ liệu runtime khác nhau, so sánh contract và một số hành vi đã định nghĩa thay vì buộc mọi metric có cùng giá trị.

## 17. Checklist migration theo hành vi

| Hạng mục | Kiểm tra trước/sau migration |
| --- | --- |
| Danh sách MBean | Tất cả \`ObjectName\` dự kiến vẫn có |
| JMX server | Exporter vẫn dùng đúng server/connector |
| Metadata | Attributes, operations, types và signatures tương đương |
| Naming | Domain và key properties không thay đổi ngoài chủ đích |
| Assembler | Không công bố thêm method nhạy cảm, không mất method cần thiết |
| Registration policy | Giữ hành vi xử lý trùng tên mong muốn |
| Managed instance | MBean tham chiếu đúng Spring bean đang dùng trong nghiệp vụ |
| Lifecycle | Khởi tạo, unregister và shutdown phù hợp |
| Autodetection | Không xuất thêm bean hoặc bỏ sót bean ngoài ý muốn |
| Client | JConsole/dashboard/automation vẫn nhìn đúng MBean |
| Cấu hình kép | Không còn hai exporters cùng sở hữu một \`ObjectName\` |
| Rollback | Có thể quay lại XML config độc lập, không đăng ký hai lần |

## 18. Lỗi migration thường gặp

### Context khởi tạo lỗi vì tên trùng

**Nguyên nhân:** XML exporter vẫn được load cùng Java exporter mới.

**Cách xử lý:** tắt định nghĩa cũ trong deployment mới, không chỉ đổi registration policy để che vấn đề. Xác định một owner cho từng \`ObjectName\`.

### JConsole vẫn thấy MBean nhưng dữ liệu khác

**Nguyên nhân:** Java Config tạo một bean instance mới, exporter dùng server khác hoặc naming strategy thay đổi.

**Cách xử lý:** đối chiếu Spring bean được inject, server và identity của MBean trong registry. Một tên JMX hợp lệ không bảo đảm target instance chính xác.

### Mất một số attributes/operations

**Nguyên nhân:** migration bỏ mất assembler hoặc annotation export, hoặc interface quản lý khác.

**Cách xử lý:** đọc \`MBeanInfo\` ở cấu hình cũ/mới; chuyển đúng \`MBeanInfoAssembler\`, interface hoặc metadata configuration.

### Không thấy MBean ở client

**Nguyên nhân:** exporter dùng custom server, trong khi client đang xem platform server, hoặc tên JMX khác.

**Cách xử lý:** đọc \`isRegistered\` trên server được inject vào exporter; đối chiếu connector/endpoint rồi mới sửa config.

### Context cũ đóng làm MBean mới biến mất

**Nguyên nhân:** ownership không rõ, replacement policy hoặc hai exporters dùng cùng tên.

**Cách xử lý:** tránh chồng lấn registration, xác định lifecycle, tạo context/server test độc lập và kiểm tra hành vi unregister.

### Test qua nhưng production thất bại

**Nguyên nhân:** môi trường runtime có application server JMX, proxy/AOP, nhiều contexts hoặc Boot auto-configuration khác test.

**Cách xử lý:** chạy integration test theo profile production gần thực tế; kiểm tra danh sách exporters và server trước deployment.

## 19. Bảo mật và vận hành khi migration

Một migration JMX có thể khiến method mới xuất hiện nếu assembler hoặc annotation autodetection thay đổi. Đây là thay đổi bề mặt quản trị, không chỉ thay file cấu hình.

- Không công bố bí mật, dữ liệu khách hàng hoặc phương thức nghiệp vụ nhạy cảm qua JMX.
- Với operation như \`reset\`, \`clearCache\`, \`reload\` hoặc \`shutdown\`, kiểm tra điều kiện sử dụng, khả năng gọi lặp và tác động runtime.
- Nếu thay \`MBeanServer\` hoặc connector, giữ nguyên hoặc tăng cường xác thực, mã hóa và giới hạn network cho remote JMX.
- Cần ghi nhận thời điểm migration và \`ObjectName\` thay đổi có chủ đích để cập nhật dashboard/alert.
- Với nhiều instances/JVM, \`ObjectName\` chỉ duy nhất trong từng server; monitoring cần nhận diện cả JVM/endpoint.
- Dùng integration tests để kiểm tra **không có method dư** chứ không chỉ kiểm tra đã đăng ký MBean.

## 20. Bài tập thực hành

**Bài 1 — Migration cơ bản.** Tạo \`spring-jmx.xml\` với \`JobMonitor\` và \`MBeanExporter\`, xác minh \`ProcessedCount\` qua JMX. Sau đó chuyển sang \`JmxConfiguration\` và giữ nguyên \`ObjectName\`.

**Bài 2 — Migration từng phần.** Giữ \`JobMonitor\` dưới dạng XML bean nhưng khai báo exporter bằng Java Config. Inject cùng bean đã có; chứng minh JMX đọc chính instance nghiệp vụ.

**Bài 3 — Assembler.** Tạo một POJO chứa \`getCount()\`, \`reset()\` và \`deleteAll()\`. Cấu hình \`MethodNameBasedMBeanInfoAssembler\` trong XML, sau đó chuyển assembler sang \`@Bean\`. So sánh metadata và xác nhận \`deleteAll()\` không bị công bố.

**Bài 4 — Cấu hình kép.** Chủ động chạy hai exporters cùng \`ObjectName\` trong một test cô lập, quan sát lỗi, rồi sửa bằng cách chỉ bật một exporter. Giải thích tại sao \`IGNORE_EXISTING\` không phải lời giải cho migration đúng nghĩa.

**Bài 5 — Annotation mode.** Thay \`<context:mbean-export/>\` bằng \`@EnableMBeanExport\`, giữ bean \`@ManagedResource\`. Kiểm tra chính xác những beans nào được autodetect và những methods nào được công bố.

**Bài 6 — Rollback.** Thiết kế hai cấu hình triển khai chỉ khác cơ chế Java/XML, không cùng active. Kiểm tra có thể chuyển ngược mà không đổi full \`ObjectName\` hoặc contract quản trị.

## Kết luận

**Migration từ XML exporter sang Java Config** trong Spring Framework JMX không chỉ là thay \`<bean>\` bằng \`@Bean\`. Mục tiêu là bảo toàn đường đi **Spring-managed object → MBeanExporter → MBeanServer → JMX ObjectName** và hợp đồng mà client hiện tại đang sử dụng. Khi chuyển đổi, hãy giữ đúng managed instance, server, naming strategy, assembler, registration policy và lifecycle; tránh hai exporters cùng đăng ký một tên. Xác minh migration bằng registry và \`MBeanInfo\`, không chỉ bằng việc application context khởi động thành công.
