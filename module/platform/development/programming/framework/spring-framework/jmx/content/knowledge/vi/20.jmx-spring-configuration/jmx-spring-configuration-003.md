# @EnableMBeanExport trong nhiều profile: quản lý Spring JMX theo môi trường

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích chức năng của **\`@EnableMBeanExport\`** trong Spring Framework và mối quan hệ với **\`MBeanExporter\`**, **\`MBeanServer\`**, **\`@ManagedResource\`** và các annotation JMX khác.
- Sử dụng Spring **\`@Profile\`** để quyết định cấu hình xuất MBean nào được kích hoạt trong các môi trường \`dev\`, \`test\`, \`staging\` và \`prod\`.
- Phân biệt **bật JMX export trong ứng dụng** với **mở remote JMX connector của JVM**; việc sử dụng profile không tự động bảo vệ một cổng quản trị.
- Thiết kế profile, quy ước \`ObjectName\` và ownership tránh tạo nhiều exporter hoặc nhiều MBean cùng tên.
- Dùng cấu hình Spring Java thuần hoặc Spring Boot mà không nhầm \`@EnableMBeanExport\` với \`spring.jmx.enabled\`.
- Kiểm tra \`Environment.getActiveProfiles()\`, \`MBeanServer.isRegistered(...)\` và \`MBeanInfo\` để xác nhận những gì thực sự được export.
- Viết integration tests chứng minh MBean chỉ xuất hiện trong profile được cho phép, và được unregister khi context đóng.
- Nhận diện các rủi ro do profile chồng chéo, default profile, AOP proxy, auto-configuration, context cha/con và remote management.

## 2. Bối cảnh: tại sao JMX export cần cấu hình theo profile?

Một ứng dụng Spring có thể triển khai trên nhiều môi trường với yêu cầu quản trị khác nhau:

| Môi trường | Nhu cầu JMX thường gặp |
| --- | --- |
| \`dev\` | Cần quan sát chi tiết cache, queue, worker và thử operation quản trị trong môi trường cô lập. |
| \`test\` | Cần test hợp đồng MBean hoặc kiểm tra integration, nhưng không muốn MBean làm các test va chạm. |
| \`staging\` | Cần gần với production để kiểm thử monitoring, quyền truy cập và lifecycle. |
| \`prod\` | Chỉ xuất MBean thật sự cần thiết, kiểm soát nội dung và quyền chặt chẽ. |

Không phải tất cả ứng dụng đều cần remote JMX. Nhiều hệ thống chỉ sử dụng platform MBeanServer cục bộ để đọc tình trạng JVM hoặc xuất metrics qua một adapter khác. Tuy nhiên khi đã công bố một operation điều khiển như \`clearCache()\`, \`pauseConsumers()\` hoặc \`reloadConfiguration()\`, việc giới hạn nơi operation đó xuất hiện có thể giảm bề mặt vận hành.

**Spring profile** giúp quyết định *bean cấu hình nào tồn tại trong ApplicationContext*. Khi cấu hình \`@EnableMBeanExport\` nằm trong một \`@Configuration\` chỉ có hiệu lực với profile nhất định, exporter do annotation kích hoạt có thể chỉ được tạo trong các context phù hợp.

\`\`\`text
Active profiles
   dev,local          prod          test
      |                |             |
      v                v             v
@Profile matching?
      |                |             |
      v                v             v
JMX configuration được kích hoạt?
      |                |             |
      v                v             v
MBeanExporter được tạo / cấu hình
      |
      v
MBeanServer đăng ký những MBean được chọn
      |
      v
JConsole / JMX client nhìn thấy hợp đồng runtime
\`\`\`

**Lưu ý:** profile chỉ là một cơ chế chọn cấu hình Spring. Nó không tự động giới hạn quyền JMX, mã hóa đường truyền hoặc phân biệt read-only/readwrite.

## 3. @EnableMBeanExport có nhiệm vụ gì?

Trong Spring Framework, annotation:

\`\`\`java
import org.springframework.context.annotation.EnableMBeanExport;
\`\`\`

dùng để kích hoạt hỗ trợ export JMX trên một \`@Configuration\` class. Cơ chế nhập cấu hình nội bộ tạo/cấu hình infrastructure exporter tương ứng, cho phép Spring quản lý các bean đủ điều kiện theo cấu hình JMX.

Ví dụ cơ bản:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Các bean có metadata như \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` có thể được đăng ký thành MBean theo cách exporter phát hiện chúng.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class OrderQueueManagement {

    @ManagedAttribute(description = "Current queued messages")
    public long getQueueDepth() {
        return 42L; // Chỉ là dữ liệu minh họa.
    }
}
\`\`\`

Nếu exporter không được kích hoạt hoặc bean không thuộc ApplicationContext hiện tại, annotation trên class một mình không bảo đảm MBean sẽ xuất hiện. Ngược lại, nếu bean được đăng ký thủ công qua \`MBeanServer.registerMBean\`, nó có thể vẫn tồn tại dù không sử dụng \`@EnableMBeanExport\`.

### 3.1. @EnableMBeanExport không làm gì?

Nó không:

- Tự bật cổng remote JMX/RMI.
- Cấp quyền JMX hoặc tạo tài khoản người vận hành.
- Thay thế TLS, firewall hoặc VPN.
- Bảo đảm tất cả bean Spring đều được export.
- Chuyển mọi public method thành operation quản trị.
- Tự kiểm tra nội dung dữ liệu nhạy cảm của getter.
- Tự chuyển metrics thành Prometheus/OpenTelemetry.
- Quản lý database persistence cho trạng thái MBean.

Đây là ranh giới quan trọng để không nhầm Spring bean exporting với các lớp quản trị bên ngoài JVM.

## 4. Cơ chế Spring @Profile

Annotation \`@Profile\` đặt điều kiện dựa trên **active profiles** của Spring \`Environment\`:

\`\`\`java
import org.springframework.context.annotation.Profile;
\`\`\`

Ví dụ:

\`\`\`java
@Configuration
@Profile("dev")
public class DevelopmentOnlyConfiguration {
    // Bean trong configuration này chỉ được đăng ký
    // khi profile dev đang active.
}
\`\`\`

Nếu cấu hình chứa \`@EnableMBeanExport\` nằm trên class \`@Configuration\` cùng \`@Profile\`, việc nhập cấu hình export phụ thuộc điều kiện profile:

\`\`\`java
@Configuration
@Profile("dev")
@EnableMBeanExport
public class DevelopmentJmxConfiguration {
}
\`\`\`

Khi \`dev\` không active, class cấu hình bị loại khỏi quá trình xử lý phù hợp, vì thế đường cấu hình này không kích hoạt exporter. Điều đó **không có nghĩa không còn exporter khác**: Spring Boot auto-configuration hoặc một \`@Configuration\` khác vẫn có thể tạo exporter riêng.

### 4.1. Profile expression

Spring hỗ trợ biểu thức profile như:

\`\`\`java
@Profile({"dev", "staging"})
\`\`\`

Trong trường hợp này, điều kiện theo các tên profile thường hoạt động theo nghĩa *bất kỳ profile nào trong danh sách là active*. Biểu thức logic có thể dùng dạng:

\`\`\`java
@Profile("dev | staging")
\`\`\`

hoặc:

\`\`\`java
@Profile("!prod")
\`\`\`

Nhưng \`!prod\` có thể rộng hơn dự định: khi không có profile \`prod\`, cấu hình có thể được bật cả ở môi trường chưa phân loại. Với bề mặt quản trị, nên ưu tiên **allowlist profile rõ ràng** thay vì cấu hình phủ định quá rộng.

## 5. Ví dụ 1: chỉ bật JMX export ở dev và staging

### 5.1. Config theo profile

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile({"dev", "staging"})
@EnableMBeanExport
public class ManagementExportConfiguration {
}
\`\`\`

### 5.2. Managed bean

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class ImportWorkerManagement {

    @ManagedAttribute(description = "Whether the worker is running")
    public boolean isRunning() {
        return true;
    }

    @ManagedAttribute(description = "Number of processed items")
    public long getProcessedCount() {
        return 100L;
    }

    @ManagedOperation(description = "Request a graceful worker pause")
    public void requestPause() {
        // Gọi service để yêu cầu tạm dừng an toàn.
    }
}
\`\`\`

Đối với một ApplicationContext Spring Framework thuần, nếu không có exporter khác và cơ chế export annotation được cấu hình phù hợp, khi active \`dev\` hoặc \`staging\`, MBean có thể được đăng ký tại:

\`\`\`text
com.example:type=Worker,name=Importer
\`\`\`

Khi profile không khớp, \`ManagementExportConfiguration\` không kích hoạt cơ chế export từ annotation này. Nhưng bean \`ImportWorkerManagement\` vẫn có thể tồn tại như Spring \`@Component\`; điều kiện profile ở **configuration export** không tự động loại bỏ bean nghiệp vụ.

### 5.3. Kích hoạt profile

Trong Spring Boot:

\`\`\`bash
java -jar app.jar --spring.profiles.active=dev
\`\`\`

Trong \`application.properties\` (khi phù hợp với cách triển khai):

\`\`\`properties
spring.profiles.active=staging
\`\`\`

Hoặc dùng environment variable:

\`\`\`text
SPRING_PROFILES_ACTIVE=dev
\`\`\`

Lựa chọn kích hoạt profile phụ thuộc hạ tầng triển khai. Với production nên dùng hệ thống quản lý cấu hình và quy trình release, tránh ghi cứng profile chỉ phục vụ dev vào mã nguồn chung.

## 6. Ví dụ 2: profile cho từng nhóm quản trị khác nhau

Một ứng dụng có thể cần MBean *monitoring* ở production nhưng chỉ cho phép các operation chuyên biệt ở lab.

Có hai cách thường gặp:

1. **Chọn cấu hình export:** profile nào tạo exporter và MBean nào được xuất.
2. **Tách managed resources:** luôn có MBean read-only, nhưng chỉ đăng ký MBean chứa operation điều khiển ở môi trường được phép.

### 6.1. Management adapter chỉ đọc

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=ImporterStatus"
)
public class ImporterStatusManagement {

    @ManagedAttribute
    public boolean isHealthy() {
        return true;
    }

    @ManagedAttribute
    public long getBacklog() {
        return 25L;
    }
}
\`\`\`

### 6.2. Management adapter điều khiển

\`\`\`java
import org.springframework.context.annotation.Profile;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@Profile({"dev", "staging"})
@ManagedResource(
    objectName = "com.example:type=Worker,name=ImporterControl"
)
public class ImporterControlManagement {

    @ManagedOperation(
        description = "Request graceful pause of importer"
    )
    public void requestPause() {
        // Chuyển yêu cầu tới service có validation.
    }
}
\`\`\`

Lúc này bean điều khiển chỉ được tạo khi profile hợp lệ. Nếu exporter toàn cục quét ApplicationContext, nó không thể xuất bean này trong production vì bean không tồn tại ở đó.

**Đây là cách bảo vệ rõ ràng hơn so với chỉ thay description**, nhưng không thay thế authorization của connector. Nếu một operation có ý nghĩa quản trị quan trọng ở production, cần triển khai phân quyền và audit thật thay vì chỉ dựa vào profile.

### 6.3. Khi có nhiều loại exporter

Trong một dự án lớn, một exporter có thể dùng danh sách bean tường minh để kiểm soát bề mặt quản trị. Đặt mọi thứ trong một exporter duy nhất dễ quản lý ownership hơn khi có nhiều module.

Một cấu hình *không nên* tạo ra hai exporter riêng cùng quét cùng một tập bean và cùng dùng platform MBeanServer, trừ khi đã kiểm soát việc trùng \`ObjectName\` và lifecycle. Nếu cần nhiều nhóm MBean, có thể gộp danh sách bean được chọn hoặc phân vùng rõ.

## 7. Ví dụ 3: Spring Boot và spring.jmx.enabled

Spring Boot có cấu hình JMX auto-configuration. Trong nhiều phiên bản Spring Boot, thuộc tính:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

cho phép auto-configure việc xuất MBean của Spring theo các điều kiện áp dụng.

Ví dụ \`application-dev.properties\`:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Ví dụ \`application-prod.properties\`:

\`\`\`properties
spring.jmx.enabled=false
\`\`\`

**Điểm cần hiểu:**

- \`spring.jmx.enabled\` điều khiển cơ chế **JMX auto-configuration của Spring Boot** theo phiên bản và các điều kiện cụ thể.
- \`@EnableMBeanExport\` trực tiếp trên một \`@Configuration\` là đường cấu hình **Spring Framework**.
- Nếu bạn **tự đặt \`@EnableMBeanExport\`**, việc tắt auto-configuration bằng \`spring.jmx.enabled=false\` không nên được mặc định hiểu là tắt luôn exporter thủ công đó.
- Trong ứng dụng có cả hai cơ chế, cần kiểm tra số exporter thực tế và tên MBean được đăng ký; tránh nghĩ rằng profile là một “công tắc duy nhất” cho toàn bộ JMX.

Một chiến lược đơn giản trong Spring Boot là sử dụng **một đường cấu hình JMX được lựa chọn có chủ đích**. Nếu dùng Boot auto-configuration thì quản lý \`spring.jmx.enabled\` theo profile và tránh \`@EnableMBeanExport\` trùng. Nếu muốn kiểm soát sâu bằng Framework config, chủ động quản lý exporter và các bean liên quan.

### 7.1. application.yml theo profile

Một ví dụ cách tổ chức tài liệu cấu hình Spring Boot:

\`\`\`yaml
spring:
  application:
    name: import-service
---
spring:
  config:
    activate:
      on-profile: dev
  jmx:
    enabled: true
---
spring:
  config:
    activate:
      on-profile: prod
  jmx:
    enabled: false
\`\`\`

Các YAML documents được áp dụng tùy profile theo cơ chế Spring Boot Config Data của phiên bản đang dùng. Với những profile khác, hãy đặt giá trị mặc định rõ ràng hoặc định nghĩa file cấu hình riêng, tránh trạng thái không dự đoán.

Cấu hình này chỉ minh họa Boot JMX auto-configuration. Nếu dự án có \`@EnableMBeanExport\` ở nơi khác, quy tắc profile phải xét thêm lớp đó.

## 8. Profile trùng và nhiều profile đang active

Trong thực tế, có thể active nhiều profile cùng lúc:

\`\`\`text
spring.profiles.active=prod,debug
\`\`\`

Hoặc:

\`\`\`text
spring.profiles.active=staging,observability
\`\`\`

Các biểu thức \`@Profile\` hoạt động dựa trên tập profile. Nếu annotation viết:

\`\`\`java
@Profile("!prod")
\`\`\`

thì với \`prod,debug\`, nó thường không khớp vì \`prod\` đang active. Nhưng với một environment chưa khai báo \`prod\`, điều kiện phủ định có thể khớp ngoài ý muốn.

Một nguy cơ khác:

\`\`\`java
@Configuration
@Profile("dev")
@EnableMBeanExport
class DevJmxExportConfig {}

@Configuration
@Profile("observability")
@EnableMBeanExport
class ObservabilityJmxExportConfig {}
\`\`\`

Nếu \`dev\` và \`observability\` đều active, cả hai configuration có thể cùng tham gia import cơ chế JMX. Đừng suy đoán có “hai exporter” chỉ vì có hai annotation; cách Spring nhập bean definition và xử lý tên infrastructure phụ thuộc phiên bản/configuration. Nhưng thiết kế như vậy tạo **độ mơ hồ về ownership** và cần được tránh bằng cách gom điều kiện.

Nên ưu tiên một configuration duy nhất:

\`\`\`java
@Configuration
@Profile("dev | observability")
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

Hoặc nếu cần kiểm soát chính xác hơn, dùng conditional configuration và một danh sách environment được tổ chức rõ trong hệ thống triển khai.

## 9. Default profile và bẫy “không có profile nào”

Spring có **default profile**, thường mang tên \`default\`, được sử dụng khi không có active profile tường minh. Vì thế:

\`\`\`java
@Profile("default")
\`\`\`

có thể khớp trong môi trường local không cấu hình profile.

Nếu dùng:

\`\`\`java
@Profile("!prod")
\`\`\`

thì những JVM khởi động thiếu profile production có thể bật JMX export ngoài mong muốn. Với môi trường quan trọng, nên có cấu hình mặc định **hạn chế**, chỉ bật các MBean nâng cao qua allowlist.

Một cách đặt câu hỏi:

- Khi không có profile, JMX export có được bật không?
- Khi active đồng thời \`prod\` và một profile hỗ trợ debug, điều gì xảy ra?
- Ai có quyền đặt \`SPRING_PROFILES_ACTIVE\`?
- Có config bên ngoài, command-line hay environment variable ghi đè property không?
- Có Spring Boot auto-configuration khác tạo exporter khi class \`@Profile\` bị loại bỏ không?

Các câu hỏi này quyết định bề mặt quản trị thực tế hơn là chỉ nhìn một annotation.

## 10. Đặt tên ObjectName và tránh xung đột khi chuyển profile

Tên JMX thường có cấu trúc:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
com.example.import:type=Worker,name=Daily
com.example.import:type=Queue,name=Retries
\`\`\`

Nhiều profile khác nhau thường chạy ở **những JVM khác nhau**, nên trùng \`ObjectName\` giữa hai môi trường độc lập không phải xung đột trên cùng MBeanServer. Xung đột xảy ra **trong cùng một server** khi hai chủ thể đăng ký cùng tên.

Các trường hợp cần chú ý:

1. Hai exporter trong một ApplicationContext cùng xuất một bean.
2. Spring parent context và child context chia sẻ platform MBeanServer.
3. Một MBean do code thủ công đăng ký trước.
4. Hai module sử dụng cùng domain/type/name.
5. Một context test chưa đóng, để MBean cũ trong platform server.
6. Có nhiều exporter với registration policy khác nhau cùng tranh tên.

Nếu cần một tên duy nhất theo instance trong cùng JVM, dùng naming strategy hoặc key property bổ sung không chứa dữ liệu nhạy cảm. Không thêm profile vào \`ObjectName\` chỉ để che lỗi hai exporter trùng; cần xác định đúng ownership.

## 11. RegistrationPolicy trong môi trường nhiều profile

Spring hỗ trợ các chính sách khi ObjectName đã tồn tại:

- \`FAIL_ON_EXISTING\`: lỗi nếu ObjectName đã được đăng ký.
- \`IGNORE_EXISTING\`: bỏ qua đăng ký mới nếu tên tồn tại.
- \`REPLACE_EXISTING\`: thay MBean đang tồn tại theo chính sách exporter.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Với nhiều profile và nhiều exporter, \`FAIL_ON_EXISTING\` thường giúp phát hiện xung đột cấu hình sớm. \`IGNORE_EXISTING\` có thể khiến ứng dụng tiếp tục chạy với MBean cũ hoặc MBean của module khác, làm người vận hành hiểu sai trạng thái. \`REPLACE_EXISTING\` có thể thay đối tượng không thuộc quyền quản lý của exporter, cần cân nhắc cẩn thận.

**Registration policy không phải cơ chế bật/tắt theo profile.** Nó chỉ xử lý xung đột tên khi đã có thao tác đăng ký.

## 12. Đúng MBeanServer và đúng JVM

Spring exporter có thể sử dụng **platform MBeanServer** hoặc custom \`MBeanServer\`, tùy cấu hình. Khi kiểm tra:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

chỉ đúng nếu exporter thực sự đăng ký vào server này.

Với custom server, cần inject hoặc truy xuất đúng MBeanServer đã cấu hình. Remote client có thể kết nối tới JVM khác hoặc connector trỏ tới server riêng. Vì vậy khi \`isRegistered(name)\` là \`false\`, chưa đủ để khẳng định class \`@EnableMBeanExport\` không hoạt động.

## 13. Kiểm tra profile active tại runtime

Có thể lấy \`Environment\` trong Spring:

\`\`\`java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileReporter {
    private final Environment environment;

    public ActiveProfileReporter(Environment environment) {
        this.environment = environment;
    }

    public void reportProfiles() {
        System.out.println(
            "Active profiles: "
                + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
\`\`\`

Nếu không có active profiles tường minh, \`getActiveProfiles()\` có thể trả mảng rỗng trong khi default profiles vẫn có hiệu lực. Nếu cần biết default profiles, dùng \`getDefaultProfiles()\`.

Nên kết hợp dữ liệu profile với trạng thái MBean thực tế, không chỉ log \`Active profiles: [dev]\` rồi kết luận exporter đã đăng ký thành công.

### 13.1. Xác minh MBean được đăng ký

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

boolean registered = server.isRegistered(name);
System.out.println("Registered = " + registered);
\`\`\`

Với ví dụ \`@Profile({"dev", "staging"})\`, kỳ vọng trong một Spring Framework context không có exporter khác:

| Profile active | MBean mục tiêu dự kiến |
| --- | --- |
| \`dev\` | Được đăng ký |
| \`staging\` | Được đăng ký |
| \`prod\` | Không đăng ký qua cấu hình này |
| \`test\` | Không đăng ký qua cấu hình này |
| Không có profile tường minh | Không đăng ký qua cấu hình này, nếu default không khớp |

Đây là kết quả theo ví dụ và các giả định. Trong ứng dụng thực tế, các cơ chế exporter khác có thể thay đổi kết quả.

## 14. Đọc MBeanInfo để xác nhận giao diện được công bố

\`isRegistered=true\` chỉ xác nhận có một MBean ở tên đó. Để xác minh giao diện thực tế:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("MBean class = " + info.getClassName());

    for (var attribute : info.getAttributes()) {
        System.out.println(
            "Attribute: " + attribute.getName()
                + ", writable=" + attribute.isWritable()
        );
    }

    for (MBeanOperationInfo operation : info.getOperations()) {
        System.out.println(
            "Operation: " + operation.getName()
        );
    }
}
\`\`\`

Khi production chỉ cho phép đọc trạng thái, hãy kiểm tra những operation điều khiển không bị xuất nhầm. Một \`@ManagedOperation\` tồn tại trong class chưa chắc bị loại chỉ vì profile \`prod\` có security policy khác; điều cần kiểm tra là resource chứa operation đó có được export hay không.

## 15. Integration test cho profile

Để tránh cấu hình thay đổi âm thầm sau refactor, tạo các test khởi chạy Spring context với profile tương ứng.

### 15.1. Mẫu test thuần Spring

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class JmxProfileCheck {

    private static final ObjectName NAME;

    static {
        try {
            NAME = new ObjectName(
                "com.example:type=Worker,name=Importer"
            );
        } catch (Exception e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    static void runForProfile(
            String profile, boolean expected) {

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.getEnvironment()
                .setActiveProfiles(profile);

            context.register(ManagementExportConfiguration.class);
            context.register(ImportWorkerManagement.class);
            context.refresh();

            boolean actual = server.isRegistered(NAME);

            if (actual != expected) {
                throw new AssertionError(
                    "Profile=" + profile
                        + ", expected=" + expected
                        + ", actual=" + actual
                );
            }
        }
    }

    public static void main(String[] args) {
        runForProfile("dev", true);
        runForProfile("staging", true);
        runForProfile("prod", false);
        runForProfile("test", false);
    }
}
\`\`\`

Bài test trên minh họa profile và registration trong một process. Cần đảm bảo \`ImportWorkerManagement\` là bean hợp lệ và JMX exporter được kích hoạt theo cấu hình Spring Framework thực tế. Nếu Spring context hoặc custom MBeanServer sử dụng cơ chế khác, điều chỉnh test theo implementation.

### 15.2. Test cleanup giữa các profile

Nhiều integration tests chạy trong cùng JVM có thể chia sẻ platform MBeanServer. Nếu test \`dev\` không đóng context, MBean vẫn còn và test \`prod\` có thể thấy \`isRegistered=true\` dù profile prod không tạo exporter.

Vì thế:

- Dùng \`try-with-resources\` để close context.
- Khi test kết thúc, xác nhận exporter đã unregister MBean do nó sở hữu.
- Dùng \`ObjectName\` duy nhất khi test chạy song song.
- Không tự unregister MBean của test khác hoặc của ứng dụng đang chạy.
- Không dùng \`REPLACE_EXISTING\` để che isolation lỗi.

Trong JUnit/Spring Test có thể dùng \`@ActiveProfiles\`, nhưng cần quan tâm context caching: các profile khác nhau thường tạo context cấu hình khác, còn platform MBeanServer vẫn có thể dùng chung trong một JVM test.

## 16. Dùng @ActiveProfiles trong Spring Test

Trong Spring Test, \`@ActiveProfiles\` được dùng để thiết lập profiles cho test context:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
    ManagementExportConfiguration.class,
    ImportWorkerManagement.class
})
@ActiveProfiles("dev")
class DevelopmentJmxExportTest {

    @Test
    void exportsManagementMBean() {
        // Inject MBeanServer hoặc dùng platform server,
        // rồi assert isRegistered(name).
    }
}
\`\`\`

Đây là ví dụ định hướng test; cần dependency Spring Test và JUnit Jupiter phù hợp. Khi tạo test production-ready, assert trạng thái thực tế thay vì để trống body test.

Một test cho profile \`prod\` nên bảo đảm app không có exporter khác được bật bởi auto-configuration. Nếu dùng Spring Boot test, có thể đưa property \`spring.jmx.enabled=false\` vào cấu hình môi trường test để kiểm soát auto-export khi phù hợp với mục tiêu.

## 17. Nhiều ApplicationContext và context hierarchy

Trong web application hoặc hệ thống module lớn có thể có:

\`\`\`text
Root ApplicationContext
        |
        +-- MBeanExporter A
        |
        +-- Child ApplicationContext
                   |
                   +-- MBeanExporter B
\`\`\`

Nếu cả A và B đăng ký vào cùng platform MBeanServer và cùng dùng \`ObjectName\`, việc hai contexts có profile khác nhau không ngăn được xung đột. Mỗi context có \`Environment\` và bean definitions riêng; các profile có thể kế thừa hoặc được cấu hình khác nhau.

Để tránh sự cố:

1. Xác định context nào sở hữu JMX exporter.
2. Xác định bean nào nằm trong phạm vi quét của mỗi exporter.
3. Sử dụng một exporter cho từng tập MBean hoặc chia namespace rõ ràng.
4. Không để cùng một MBean được đăng ký ở parent và child ngoài chủ đích.
5. Kiểm tra lifecycle shutdown và unregistration khi một child context đóng trước root context.

Trong multi-tenant/multi-module, không đưa tenant ID hoặc thông tin nhạy cảm trực tiếp vào ObjectName nếu không có chính sách rõ.

## 18. JMX export theo profile không đồng nghĩa remote JMX theo profile

Phân biệt hai lớp cấu hình:

\`\`\`text
Layer 1 — Spring JMX exporting:
    @EnableMBeanExport
    @ManagedResource
    MBeanExporter
    spring.jmx.enabled (Boot auto-configuration)

Layer 2 — JVM remote connector:
    -Dcom.sun.management.jmxremote
    -Dcom.sun.management.jmxremote.port=...
    -Dcom.sun.management.jmxremote.authenticate=...
    -Dcom.sun.management.jmxremote.ssl=...
\`\`\`

Một cấu hình \`@Profile("dev")\` có thể khiến MBean nghiệp vụ chỉ được export trong dev, nhưng nếu JVM prod vẫn bật remote JMX, client remote vẫn có thể thấy những MBean hệ thống của JVM hoặc các MBean đăng ký bởi thành phần khác.

Ngược lại, Spring có thể export một MBean trong production ngay cả khi remote JMX connector không mở; MBean vẫn nằm trong local MBeanServer.

**Không dùng profile như biện pháp bảo mật duy nhất.** Với remote JMX, cần xác thực, TLS, network restriction và phân quyền phù hợp, đồng thời kiểm soát API được MBean công bố.

## 19. Phân biệt với Spring Boot Actuator

Spring Boot Actuator cung cấp các endpoint quản trị qua các kênh như HTTP và JMX theo dependency và cấu hình exposure. Một số endpoint có thể được xuất dưới dạng MBean khi cơ chế JMX của Boot/Actuator được bật.

Điều đó tạo thêm những câu hỏi:

- Profile \`prod\` có bật JMX exporter của Boot không?
- Actuator JMX exposure có danh sách endpoint được cho phép nào?
- Có \`@EnableMBeanExport\` thủ công bên cạnh auto-configuration không?
- Có custom MBeans được xuất từ ứng dụng không?
- Endpoint HTTP và JMX có phạm vi exposure khác nhau không?
- Có phân quyền riêng cho connector JMX không?

Ví dụ cấu hình cần kiểm tra trong dự án Spring Boot:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Đây là ví dụ để minh họa cấu hình kênh JMX trong Spring Boot/Actuator ở những phiên bản hỗ trợ property tương ứng. Khi nâng cấp Boot, cần kiểm tra tài liệu version cụ thể để biết endpoint exposure mặc định và cú pháp chính xác.

Không giả định cấu hình \`management.endpoints.web.exposure.include\` tự động áp dụng y hệt cho JMX.

## 20. Chẩn đoán vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| \`@EnableMBeanExport\` trong dev nhưng MBean không có | Dev profile chưa active, bean không được chọn hoặc exporter không chạy. | Xem active profiles, exporter, ObjectName và MBeanServer. |
| MBean vẫn tồn tại trong prod | Exporter khác, Spring Boot auto-configuration, manual registration hoặc context cũ. | Kiểm tra owner, \`MBeanInfo\`, \`spring.jmx.enabled\`. |
| Hai exporter trùng ObjectName | Profile chồng chéo, nhiều contexts hoặc auto-config + manual config. | Chỉ định một owner, kiểm tra registration policy. |
| \`InstanceAlreadyExistsException\` | Cùng tên đã đăng ký trong MBeanServer. | Xác định exporter/bean đang giữ tên. |
| Kích hoạt \`prod,debug\` làm xuất MBean không mong muốn | Điều kiện profile quá rộng hoặc cấu hình debug có exporter khác. | Dùng allowlist và kiểm tra runtime. |
| Test prod vẫn thấy MBean dev | Test trước chưa cleanup hoặc dùng platform server chung. | Close context, ObjectName test duy nhất. |
| JConsole không kết nối remote | Connector, port, TLS, hostname/RMI, firewall. | Phân biệt lỗi kết nối với export. |
| Có MBean nhưng operation không đúng | Assembler/interface/annotation thay đổi. | Đọc \`MBeanInfo\`, so sánh hợp đồng. |
| Cấu hình \`spring.jmx.enabled=false\` nhưng vẫn có MBean | Manual exporter hoặc JDK/platform MBeans. | Kiểm tra chủ thể đăng ký, không nhầm property Boot với mọi JMX. |
| Bean không biến mất khi profile thay đổi runtime | Profile thường quyết định bean definitions khi context tạo, không phải công tắc live. | Khởi tạo lại context/deploy theo quy trình và xác minh lifecycle. |

## 21. Đổi profile khi ứng dụng đang chạy có làm MBean tự biến mất không?

Thông thường **không**. Spring profile chủ yếu được dùng khi tạo và refresh ApplicationContext để quyết định bean definition có được nạp. Việc chỉnh environment variable ở hệ điều hành sau khi JVM đã khởi động không tự làm những bean trong context hiện tại biến mất hoặc đăng ký lại.

Muốn thay đổi profile theo chính sách triển khai, thông thường cần **restart/redeploy** hoặc xây dựng một cơ chế runtime reconfiguration riêng.

Ví dụ:

\`\`\`text
Khởi động:
    spring.profiles.active=dev
    -> Exporter được tạo
    -> MBean được đăng ký

Đổi biến môi trường trên host:
    SPRING_PROFILES_ACTIVE=prod
    -> JVM đang chạy không tự rebuild context
    -> MBean chưa chắc bị hủy

Restart ứng dụng với prod:
    -> Spring tạo context mới theo prod
    -> Config chỉ cho dev không được nạp
\`\`\`

Nếu thay đổi profile trong hệ thống có nhiều instance, cần đảm bảo mỗi instance được restart theo đúng kế hoạch và trạng thái JMX được quan sát sau deploy.

## 22. Thiết kế profile an toàn cho thực tế

Một mẫu quyết định:

- **dev/local:** có thể bật thêm MBean để chẩn đoán và thao tác trong môi trường cô lập.
- **test:** chỉ bật JMX khi test cần; giữ ObjectName riêng và cleanup chặt.
- **staging:** bật những MBean cần kiểm thử monitoring và auth, dùng cấu hình gần production.
- **prod:** xuất tập MBean nhỏ, ưu tiên read-only metrics/status, điều khiển qua operation được kiểm soát rõ.
- **default/unknown:** chỉ bật khi có quy tắc cho phép minh bạch; tránh vô tình bật chức năng quản trị nhạy cảm.

Mẫu design:

\`\`\`text
Profile selection
    |
    +-- Monitoring adapter: always available where needed
    |
    +-- Debug/control adapter: dev/staging only
    |
    +-- JMX exporter: one owner, explicit policy
    |
    +-- Remote connector: separately secured and configured
\`\`\`

Nếu dự án bắt buộc có JMX production, nên có tests xác minh việc xuất MBean đúng hợp đồng và không vô tình lộ debug operation.

## 23. Bài tập thực hành

### Bài tập 1 — Profile dev/staging

Tạo \`ManagementExportConfiguration\` dùng \`@Profile({"dev", "staging"})\` và \`@EnableMBeanExport\`. Tạo \`@ManagedResource\` với một attribute read-only. Chạy cùng \`dev\`, \`staging\`, \`prod\`.

**Mục tiêu:** chứng minh profile quyết định configuration có được nạp.

### Bài tập 2 — Spring Boot property

Tạo \`application-dev.properties\` với \`spring.jmx.enabled=true\` và \`application-prod.properties\` với \`spring.jmx.enabled=false\`. Khởi động theo từng profile, kiểm tra danh sách MBean ứng dụng và xác định exporter thực tế.

**Mục tiêu:** phân biệt property Boot với annotation Framework.

### Bài tập 3 — Nhiều profile cùng active

Chạy \`spring.profiles.active=prod,debug\`. Thử một configuration dùng \`@Profile("!prod")\` và một configuration dùng \`@Profile({"dev", "staging"})\`.

**Mục tiêu:** hiểu logic điều kiện profile và nguy cơ profile phủ định.

### Bài tập 4 — Xung đột ObjectName

Trong hai context thử nghiệm dùng cùng platform server, cố export cùng ObjectName. Quan sát \`InstanceAlreadyExistsException\` với \`FAIL_ON_EXISTING\`, rồi điều chỉnh ownership và tên.

**Mục tiêu:** thấy rằng khác profile/context không tự động bảo đảm tên JMX không xung đột.

### Bài tập 5 — Kiểm tra MBeanInfo

Với production monitoring adapter, xác minh chỉ có \`Healthy\` và \`Backlog\` read-only; operation \`requestPause()\` không có trong MBeanInfo khi control adapter bị loại bởi profile.

**Mục tiêu:** bảo vệ bề mặt công bố thay vì chỉ kiểm tra exporter tồn tại.

### Bài tập 6 — Startup/shutdown

Tạo integration test chạy cùng profile \`dev\`, xác nhận MBean đăng ký; đóng context, xác nhận unregister. Lặp lại trong JVM test cô lập với \`prod\`.

**Mục tiêu:** không để MBean của profile trước ảnh hưởng test profile tiếp theo.

## 24. Câu hỏi ôn tập

**1. \`@EnableMBeanExport\` dùng để làm gì?** Kích hoạt hỗ trợ Spring JMX exporting trên configuration phù hợp.

**2. \`@Profile\` tác động đến \`@EnableMBeanExport\` thế nào?** Nó quyết định configuration class chứa annotation có được đưa vào context khi các profile khớp hay không.

**3. Nếu \`spring.jmx.enabled=false\`, một exporter cấu hình thủ công có chắc bị tắt không?** Không. Property Boot chủ yếu điều khiển auto-configuration của Boot, không nhất thiết triệt tiêu bean tự khai báo.

**4. \`@EnableMBeanExport\` có tự mở cổng remote JMX không?** Không. Remote connector là cấu hình riêng của JVM/agent.

**5. Vì sao \`@Profile("!prod")\` có thể nguy hiểm?** Vì các môi trường không có profile prod đều có thể khớp, kể cả môi trường chưa được nhận diện.

**6. Khi đổi biến môi trường về profile khác, MBean có lập tức unregister không?** Thông thường không; profile được xét khi tạo/refresh context.

**7. Khi nào ObjectName bị trùng?** Khi hai MBean được đăng ký cùng tên trong cùng một MBeanServer.

**8. Có thể dùng profile thay authentication/TLS JMX không?** Không. Profile chỉ chọn cấu hình, không tạo bảo mật connector.

**9. Cách nào xác nhận MBean thực sự được xuất?** Kiểm tra đúng \`MBeanServer.isRegistered(name)\` và \`MBeanInfo\`.

**10. Nếu production vẫn thấy MBean dù configuration dev bị loại, nên xem gì?** Exporter khác, Boot auto-configuration, manual register, context hierarchy hoặc JDK platform MBeans.

## 25. Tổng kết

Kết hợp **\`@EnableMBeanExport\`** và **\`@Profile\`** giúp Spring Framework chọn những cấu hình JMX exporting phù hợp với từng môi trường. Cách này hữu ích khi cần thêm quản trị ở dev/staging nhưng giữ bề mặt production tối giản.

Tuy nhiên, trong ứng dụng có nhiều profile, Spring Boot auto-configuration hoặc nhiều ApplicationContext, không nên mặc định một profile sẽ kiểm soát mọi MBean. Hãy thiết kế **một owner rõ ràng cho exporter**, kiểm tra ObjectName và MBeanInfo runtime, quản lý cleanup giữa các context và bảo vệ remote JMX connector bằng cơ chế riêng.

## Tài liệu tham khảo

- Spring Framework Javadoc — \`EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Spring Framework Javadoc — \`Profile\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Bean definition profiles: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html