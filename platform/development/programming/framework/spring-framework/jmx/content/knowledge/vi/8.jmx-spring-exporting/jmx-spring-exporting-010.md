# Đọc lỗi MBeanExporter trong giai đoạn khởi động Spring

## 1. Mục tiêu

Khi ứng dụng Spring khởi động, \`MBeanExporter\` có thể đăng ký các bean lên một \`MBeanServer\` để công cụ JMX đọc thuộc tính và gọi thao tác quản trị. Nếu một bean không thể được export, lỗi thường xuất hiện trong lúc tạo \`ApplicationContext\`, trước khi ứng dụng sẵn sàng phục vụ request. Stack trace đôi khi dài vì lỗi gốc được bọc qua nhiều lớp Spring.

Bài này hướng dẫn đọc một startup failure theo **nguyên nhân gốc và giai đoạn thất bại**, từ đó quyết định sửa tên MBean, cấu hình exporter, bean metadata, interface JMX hay vòng đời đăng ký.

Các câu hỏi phải trả lời từ log:

1. **Bean hoặc ObjectName nào** đang được đăng ký?
2. **MBeanServer nào** nhận đăng ký?
3. Lỗi xảy ra **trước khi tạo MBean**, **khi chuyển bean thành MBean**, hay **khi gọi registerMBean**?
4. **Exception cụ thể ở tầng sâu nhất** là gì?
5. Đây là lỗi khiến context không lên, hay exporter đã được cấu hình cho phép bỏ qua một số bean lỗi?

## 2. Đường đi của exporter lúc startup

\`\`\`text
Spring tạo ApplicationContext
    |
    +-- Component scan / @Bean / auto-configuration
    |        |
    |        v
    |    Tạo bean ứng dụng
    |        |
    |        v
    +-- MBeanExporter được tạo và cấu hình
             |
             +-- Chọn MBeanServer
             +-- Chọn candidate bean
             +-- Tạo ObjectName (naming strategy)
             +-- Tạo MBean metadata (assembler/model)
             +-- registerMBean(...)
                      |
                      +-- Thành công: MBean có trong registry
                      |
                      +-- Thất bại: exception/log/startup failure
\`\`\`

Spring có thể tự động phát hiện bean, nhận map các bean cần export, hoặc xử lý \`@ManagedResource\` qua metadata assembler. Những nhánh này có cùng kết quả là đăng ký một MBean, nhưng điểm cấu hình và kiểu exception khác nhau.

**Không chỉ đọc dòng cuối “Application run failed”.** Hãy tìm \`Caused by:\` sâu nhất có ý nghĩa, thông tin ObjectName và phần stack trace bắt đầu tại \`org.springframework.jmx.export\` hoặc \`javax.management\`.

## 3. Ví dụ cấu hình Spring JMX có thể báo lỗi

Một bean quản trị:

\`\`\`java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.app:type=Cache,name=Primary",
    description = "Cache management"
)
public class CacheMonitor {
    @ManagedAttribute(description = "Number of entries")
    public int getSize() {
        return 42;
    }
}
\`\`\`

Để Spring Framework xử lý metadata annotation, exporter cần cấu hình phù hợp (ví dụ metadata assembler và naming strategy). Trong Spring Boot, thuộc tính \`spring.jmx.enabled=true\` có thể kích hoạt cấu hình JMX theo phiên bản đang dùng:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Đây là hai bối cảnh khác nhau. Nếu ứng dụng vừa dùng Boot auto-configuration vừa khai báo một exporter riêng, phải xác định exporter nào đăng ký \`CacheMonitor\`, có cùng server và tên không, và có vô tình đăng ký hai lần hay không.

## 4. Đọc cấu trúc exception được Spring bọc

Một log minh họa:

\`\`\`text
org.springframework.beans.factory.BeanCreationException:
 Error creating bean with name 'mbeanExporter':
 Failed to register bean with key 'cacheMonitor' as MBean
Caused by: org.springframework.jmx.export.UnableToRegisterMBeanException:
 Unable to register MBean [cacheMonitor] with key 'cacheMonitor'
Caused by: javax.management.InstanceAlreadyExistsException:
 com.example.app:type=Cache,name=Primary
\`\`\`

Trong chuỗi này:

- \`BeanCreationException\` cho biết context không hoàn tất quá trình khởi tạo bean \`mbeanExporter\`.
- \`UnableToRegisterMBeanException\` gắn lỗi với thao tác export và có thể chứa tên hoặc bean key.
- \`InstanceAlreadyExistsException\` nói rằng **ObjectName đã tồn tại trong cùng MBeanServer**. Đây là thông tin giúp xử lý nguyên nhân trực tiếp.

Những lớp wrapper có ích để xác định **ngữ cảnh lỗi**; exception sâu hơn thường quyết định cách sửa. Dù vậy, không bỏ qua mọi exception ở trên: nhiều startup failures có hơn một nhánh \`Caused by\` hoặc lỗi xảy ra ở khâu cấu hình trước khi gọi register.

### Quy trình tìm đúng dòng trong log

1. Tìm \`Application run failed\`, \`BeanCreationException\` hoặc \`UnableToRegisterMBeanException\`.
2. Ghi lại **tên bean** và **bean key/ObjectName** xuất hiện gần đầu stack trace.
3. Theo các dòng \`Caused by\` tới exception sâu nhất còn liên quan.
4. Phân loại: trùng tên, tên không hợp lệ, MBean không compliant, mapping lỗi, server không có hoặc lỗi từ lifecycle bean.
5. Dùng một probe hoặc test có giới hạn để xác nhận giả thuyết; sau đó sửa cấu hình/implementation đúng chỗ.

## 5. InstanceAlreadyExistsException: đăng ký trùng ObjectName

Ví dụ:

\`\`\`text
javax.management.InstanceAlreadyExistsException:
 com.example.app:type=Cache,name=Primary
\`\`\`

Một \`MBeanServer\` không thể chứa hai registration cùng \`ObjectName\`. Những nguyên nhân thường gặp:

- Hai bean khác nhau sử dụng \`@ManagedResource(objectName=...)\` giống nhau.
- Một MBean đã được \`registerMBean\` thủ công, sau đó Spring exporter đăng ký tiếp.
- Hai \`MBeanExporter\` cùng quản lý bean hoặc cùng tạo tên.
- Hai \`ApplicationContext\` trong cùng JVM cùng export tên giống nhau vào platform server.
- Redeploy/hot reload không dọn MBean cũ như mong đợi.

Probe trong chính JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=Cache,name=Primary"
);

System.out.println(server.isRegistered(name));
\`\`\`

Probe chỉ phản ánh platform server, vì vậy nếu exporter trỏ đến server do ứng dụng tạo, hãy dùng đúng instance đã inject vào exporter.

**Cách sửa ưu tiên:** xác định chủ sở hữu registration; gỡ đăng ký thừa, chọn một exporter hoặc cấp \`ObjectName\` riêng cho từng thành phần. Một hệ thống nhiều instance cùng JVM có thể thêm key như \`instance\` hoặc \`context\`, được chuẩn hóa an toàn.

\`MBeanExporter\` có chính sách registration behavior cho tình huống đã tồn tại (ví dụ bỏ qua hoặc thay thế tùy phiên bản/cấu hình). Đây là quyết định thiết kế, không phải giải pháp mặc định: chọn thay thế có thể làm một thành phần chiếm MBean của thành phần khác.

## 6. MalformedObjectNameException: chuỗi tên sai cú pháp

Ví dụ:

\`\`\`text
javax.management.MalformedObjectNameException:
 Invalid character ',' in value
\`\`\`

JMX \`ObjectName\` có dạng:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Nếu một giá trị động chứa dấu phẩy, dấu bằng, dấu nháy kép, newline hoặc wildcard, ghép chuỗi trực tiếp có thể tạo tên lỗi hoặc pattern.

Ví dụ nguy hiểm:

\`\`\`java
String queue = "critical,eu";
ObjectName name = new ObjectName(
    "com.example:type=Queue,name=" + queue
);
\`\`\`

Dùng API quote phần **value**:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example:type=Queue,name=" +
    ObjectName.quote(queue)
);
\`\`\`

Nếu domain hoặc key động, cần validate chúng riêng; \`ObjectName.quote\` dành cho value, không tự biến key bất hợp lệ thành hợp lệ.

Khi stack trace chứa \`MalformedObjectNameException\`, xác định tên được tạo ở annotation, naming strategy hay cấu hình exporter. Tránh sửa bằng cách thay ký tự trên toàn bộ chuỗi \`ObjectName\`, vì có thể phá dấu phân cách hợp lệ.

## 7. NotCompliantMBeanException: bean không có giao diện quản trị hợp lệ

Ví dụ:

\`\`\`text
javax.management.NotCompliantMBeanException:
 MBean class ... does not implement DynamicMBean,
 and neither follows Standard MBean conventions nor MXBean conventions
\`\`\`

Nếu gọi API JMX chuẩn trực tiếp:

\`\`\`java
server.registerMBean(new CacheMonitor(), name);
\`\`\`

một POJO bất kỳ không tự động là Standard MBean. Standard MBean thường tuân theo quy ước:

\`\`\`java
public interface CacheMonitorMBean {
    int getSize();
    void clear();
}

public class CacheMonitor implements CacheMonitorMBean {
    public int getSize() { return 42; }
    public void clear() {}
}
\`\`\`

Hoặc dùng \`StandardMBean\` để chỉ rõ interface:

\`\`\`java
javax.management.StandardMBean wrapper =
    new javax.management.StandardMBean(
        monitor,
        CacheMonitorMBean.class
    );
server.registerMBean(wrapper, name);
\`\`\`

Với annotation-driven Spring JMX, metadata assembler có thể xuất bean mà không cần interface theo quy ước Standard MBean. Vì vậy nếu gặp \`NotCompliantMBeanException\`, cần xem bean đã đi qua assembler đúng cách chưa, hay bị đăng ký thủ công/qua một exporter không được cấu hình.

Các trường hợp khác: interface quản trị không public, tên interface không khớp, MXBean trả kiểu không ánh xạ được, hoặc proxy che khuất contract dự kiến. \`MBeanInfo\` và loại bean thực tế giúp phân biệt.

## 8. InvalidInvocationException, reflection và lỗi từ getter/method

Một số lỗi không xuất hiện khi đăng ký mà khi exporter đọc metadata hoặc khi framework gọi method để xây dựng/describer MBean. Stack trace có thể chứa:

\`\`\`text
java.lang.IllegalArgumentException
java.lang.reflect.InvocationTargetException
org.springframework.beans.factory.BeanCreationException
\`\`\`

Đọc method gây lỗi, không mặc định quy mọi \`BeanCreationException\` về JMX. Ví dụ getter dùng để tính attribute có side effect hoặc truy cập dependency chưa sẵn sàng; việc đăng ký MBean có thể thành công nhưng client đọc attribute sau đó mới gặp lỗi.

Phân loại rõ:

- **Registration-time:** lỗi ném ra trong khâu tạo/register MBean, khiến exporter thất bại.
- **Invocation-time:** lỗi khi client gọi getter/operation; có thể không ngăn context khởi động.
- **Bean initialization-time:** dependency/cấu hình ứng dụng chưa tạo được bean quản trị, exporter chưa có cơ hội đăng ký.

Không chuyển logic nặng hoặc truy cập mạng bắt buộc vào getter quản trị. Một getter nên trả snapshot trạng thái có sẵn, tránh làm startup và client thao tác bị ảnh hưởng bởi hệ thống ngoài.

## 9. Lỗi không tìm thấy MBeanServer

Nếu exporter không có server phù hợp, startup có thể báo lỗi liên quan lookup \`MBeanServer\`, factory bean hoặc inject dependency. Kiểm tra:

1. Có bean \`MBeanServer\` nào trong Spring context không?
2. Exporter tự động tìm server hay được \`setServer(...)\`?
3. Ứng dụng có tạo server riêng trong context khác không?
4. Server đã được khởi tạo đúng thứ tự chưa?
5. Một connector đang trỏ platform server trong khi exporter đăng ký custom server không?

Ví dụ chỉ định platform server tường minh:

\`\`\`java
@Bean
MBeanExporter mbeanExporter() {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(
        java.lang.management.ManagementFactory
            .getPlatformMBeanServer()
    );
    return exporter;
}
\`\`\`

Cấu hình đầy đủ cần thêm mapping beans hoặc autodetect/assembler phù hợp. Nếu Boot đã có exporter, đừng tạo bean mới chỉ để đặt server mà không xem cấu hình đang tồn tại.

## 10. Lỗi annotation hoặc metadata assembler

Một annotation như \`@ManagedResource\` mô tả tên MBean, còn \`@ManagedAttribute\` và \`@ManagedOperation\` mô tả bề mặt quản trị. Nhưng exporter phải có \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\` hoặc cơ chế tương đương.

Ví dụ cấu hình Spring Framework:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxConfig {
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

        var exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
\`\`\`

Một lỗi thường gặp là dùng annotation nhưng exporter mặc định không tìm bean như mong muốn. Điều này có thể biểu hiện bằng “không có MBean” chứ không nhất thiết là startup failure. Kiểm tra cơ chế autodetect, map bean explicit, \`@EnableMBeanExport\` khi phù hợp với cấu hình dự án, và cách Boot auto-configure JMX.

## 11. Startup failure khi bật Spring AOP/proxy

Bean quản trị có thể được bọc trong JDK dynamic proxy hoặc CGLIB proxy do \`@Transactional\`, caching, security hoặc các advice khác. Khi đó:

- Loại runtime có thể là proxy thay vì implementation.
- Interface Standard MBean có thể không được nhìn thấy theo cách dự kiến.
- Annotation được đặt trên implementation nhưng metadata resolver không nhận theo cấu hình thực.
- Một bean name được export nhưng instance/contract sau proxy không hợp lệ với MBean server.

Hướng kiểm tra:

\`\`\`java
Object bean = context.getBean("cacheMonitor");
System.out.println(bean.getClass());
System.out.println(
    org.springframework.aop.support.AopUtils.getTargetClass(bean)
);
\`\`\`

Đừng tháo AOP chỉ để MBean xuất hiện. Có thể tạo **adapter quản trị riêng** không bị proxy nghiệp vụ, inject một application port và export adapter đó. Phương án này còn giúp interface quản trị độc lập business interface.

## 12. Lỗi JMX và lỗi Spring Boot khác nhau thế nào?

Trong Spring Boot, log có thể bắt đầu bằng:

\`\`\`text
APPLICATION FAILED TO START
Description:
...
Action:
...
\`\`\`

Thông báo FailureAnalyzer là gợi ý hữu ích nhưng không luôn hiển thị đầy đủ nguyên nhân JMX. Cần kết hợp:

- **Bean name:** bean nào không khởi tạo được?
- **Condition evaluation:** JMX auto-configuration có áp dụng không?
- **External configuration:** profile hay biến môi trường nào đặt \`spring.jmx.enabled\`?
- **Exporter count:** có bean exporter do người dùng khai báo và bean auto-configured cùng lúc không?
- **Nested exceptions:** lỗi JMX sâu nhất là gì?

Không kết luận “Spring Boot không hỗ trợ JMX” chỉ vì một cấu hình bị vô hiệu hoặc chưa đăng ký bean. Phân biệt **không bật export** với **export thất bại** và **export thành công nhưng connector/UI không thấy**.

## 13. Kiểm tra lỗi bằng MBeanServer probe

Nếu startup có thể tiếp tục hoặc bạn đang chạy integration test, một probe cho biết registration thực tế:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class RegistrationProbe {
    public static void inspect() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName expected = new ObjectName(
            "com.example.app:type=Cache,name=Primary"
        );

        System.out.println("Registered: " +
                server.isRegistered(expected));

        for (ObjectName name : server.queryNames(
                new ObjectName("com.example.app:*"), null)) {
            System.out.println(name.getCanonicalName());
        }
    }
}
\`\`\`

Probe phải chạy trong **cùng JVM** và trên **đúng \`MBeanServer\`**. Một process test khác có platform server riêng, do đó không thể chứng minh registration của ứng dụng production.

Nếu exporter đã ném exception khiến context bị hủy, MBean có thể đã được unregister trong cleanup; \`false\` sau failure không chứng minh rằng bean chưa từng đăng ký. Startup stack trace và thứ tự lifecycle vẫn là bằng chứng quan trọng.

## 14. Dùng integration test để tái hiện lỗi exporter

Một test context có thể xác nhận đối tượng được đăng ký:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;

void assertCacheMBeanRegistered(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.app:type=Cache,name=Primary"
    );
    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);
    assertTrue(
        java.util.Arrays.stream(info.getAttributes())
            .anyMatch(a -> "Size".equals(a.getName()))
    );
}
\`\`\`

Các tình huống test nên phản ánh lỗi thực tế:

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai bean export cùng ObjectName | Ném lỗi duplicate hoặc xử lý theo policy rõ |
| ObjectName chứa value đặc biệt không quote | Phát hiện tên sai hoặc pattern ngoài ý muốn |
| Export một POJO không compliant qua JMX chuẩn | \`NotCompliantMBeanException\` |
| Adapter annotated với exporter cấu hình đúng | MBean đăng ký và metadata xuất hiện |
| Đóng context | MBean do exporter sở hữu được unregister |
| Hai context trong một JVM | Mỗi context dùng tên khác nhau hoặc chính sách sở hữu rõ |

Trong test, dùng ObjectName riêng để tránh xung đột khi chạy song song. Đóng context và dọn MBean đúng vòng đời; không xóa registration của component khác.

## 15. Bật log để khoanh vùng, không làm thay đổi hành vi

Khi cần thêm bằng chứng, có thể điều chỉnh mức log cho nhóm Spring JMX/exporter theo hệ thống logging đang dùng:

\`\`\`properties
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.jmx.export=TRACE
\`\`\`

Trong dự án Spring Boot, đây là ví dụ cấu hình mức log; trong Spring Framework thuần có thể thiết lập tương đương bằng Logback, Log4j2 hoặc hệ thống log đang dùng.

Chỉ bật TRACE trong phạm vi chẩn đoán cần thiết vì có thể tạo log lớn. Không ghi credentials của JMX connector hoặc userData nhạy cảm vào log debug. Sau khi xác định lỗi, quay lại mức log vận hành thông thường theo quy trình triển khai.

## 16. Cách xử lý theo exception gốc

| Exception/triệu chứng | Ý nghĩa chính | Hướng sửa |
| --- | --- | --- |
| \`InstanceAlreadyExistsException\` | Trùng ObjectName trong cùng server | Chọn chủ sở hữu, gỡ registration thừa, đặt tên duy nhất |
| \`MalformedObjectNameException\` | Tên JMX không đúng cú pháp | Validate domain/key, \`ObjectName.quote\` value động |
| \`NotCompliantMBeanException\` | Bean không theo contract Standard MBean/MXBean/DynamicMBean | Sửa interface hoặc cấu hình Spring assembler |
| \`UnableToRegisterMBeanException\` | Wrapper cho lỗi đăng ký | Đọc nested cause và bean key |
| \`BeanCreationException\` | Context không tạo được bean/exporter | Tìm cause sâu hơn, dependency và cấu hình |
| \`JMException\` trong registration | Lỗi từ tầng JMX | Xem subclass, ObjectName và server |
| Không có exception nhưng không thấy MBean | Có thể exporter không nhận bean hoặc client sai server | Kiểm tra autodetect, \`isRegistered\`, \`queryNames\` |
| Có MBean nhưng getter lỗi | Lỗi khi invocation | Kiểm tra MBeanInfo, getter, mapping và quyền |

Một lỗi không nhất thiết trùng đúng class exception trong bảng vì Spring có thể bọc lỗi tùy phiên bản và đường đăng ký. Xác định nguyên nhân bằng nội dung nested cause và nơi exception phát sinh.

## 17. Quy trình chẩn đoán 10 phút khi startup thất bại

1. Lấy **stack trace đầy đủ** của lần khởi động thất bại.
2. Ghi tên Spring bean gây lỗi và \`ObjectName\` hoặc exporter key.
3. Đọc các tầng \`Caused by\` để tìm exception JMX cụ thể.
4. Xác định bean được export qua Standard MBean, MXBean, Spring metadata hay đường thủ công.
5. Kiểm tra server mà exporter đã chọn.
6. Nếu trùng tên, tìm những nơi cùng đăng ký; nếu tên sai, kiểm tra thành phần động; nếu không compliant, kiểm tra interface/mapping.
7. Sửa ở nguồn registration; không bật chế độ overwrite mù.
8. Khởi động lại trong môi trường kiểm thử, xác nhận context lên.
9. Dùng \`isRegistered\`, \`queryNames\` và \`getMBeanInfo\` để xác nhận kết quả.
10. Nếu MBean có trong server nhưng UI không thấy, chuyển sang chẩn đoán connector/JMX client thay vì tiếp tục sửa exporter.

\`\`\`text
Startup failed?
  |
  +-- Có "Caused by: InstanceAlreadyExistsException"?
  |       +-- Kiểm tra duplicate ObjectName/exporter/context
  |
  +-- Có "MalformedObjectNameException"?
  |       +-- Kiểm tra domain/key/value, quote dynamic value
  |
  +-- Có "NotCompliantMBeanException"?
  |       +-- Kiểm tra Standard MBean/MXBean/assembler
  |
  +-- BeanCreationException nhưng không có lỗi JMX?
  |       +-- Kiểm tra bean dependencies và init lifecycle
  |
  +-- Không có exception và app chạy?
          +-- Kiểm tra MBeanExporter configuration/registry
\`\`\`

## 18. Ghi nhớ

\`MBeanExporter\` là mắt xích đưa bean Spring vào registry JMX trong giai đoạn khởi động. Khi lỗi, **đọc từ wrapper Spring tới nested cause JMX**, đồng thời ghi lại bean name, ObjectName và MBeanServer thực tế. \`InstanceAlreadyExistsException\` chỉ tới trùng tên; \`MalformedObjectNameException\` chỉ tới cú pháp tên; \`NotCompliantMBeanException\` chỉ tới contract hoặc mapping; còn \`BeanCreationException\` là lớp bọc cần được đào sâu. Sửa đúng giai đoạn thất bại sẽ nhanh và an toàn hơn thay đổi ngẫu nhiên toàn bộ cấu hình JMX.
