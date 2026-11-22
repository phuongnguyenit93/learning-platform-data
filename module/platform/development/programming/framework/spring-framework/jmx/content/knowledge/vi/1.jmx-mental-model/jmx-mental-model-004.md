# Luồng từ bean Spring đến MBeanServer và công cụ quản trị

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Mô hình tư duy  
> **Mục tiêu:** Hình dung trọn vẹn hành trình một Spring bean được xuất bản dưới dạng MBean, được đăng ký với \`MBeanServer\`, rồi được quan sát hoặc điều khiển bằng công cụ JMX. Phân biệt rõ bean nghiệp vụ, lớp quản lý JMX, tên định danh và kết nối từ xa.

## 1. Bức tranh tổng thể

Trong ứng dụng Spring, một đối tượng do IoC container quản lý có thể chứa trạng thái và hành vi nghiệp vụ. **JMX (Java Management Extensions)** cung cấp một mô hình quản trị cho JVM: các tài nguyên được biểu diễn thành **MBean (Managed Bean)** và đăng ký trong một **MBeanServer**. Công cụ như JConsole, VisualVM với plugin phù hợp hoặc một JMX client có thể kết nối tới MBeanServer để đọc thuộc tính, gọi thao tác và nhận thông báo.

Spring hỗ trợ một cầu nối: thay vì tự đăng ký từng đối tượng qua API JMX thuần, ứng dụng cấu hình \`MBeanExporter\` để phát hiện hoặc nhận danh sách bean cần xuất bản, chọn cách biểu diễn chúng và đăng ký vào MBeanServer.

\`\`\`text
                Spring ApplicationContext
                         |
            tạo bean, inject dependencies,
                 chạy lifecycle
                         |
       +-----------------+----------------+
       |                                  |
  Business Bean A                    Business Bean B
  (trạng thái/hành vi)                (trạng thái/hành vi)
       |                                  |
       +------------ MBeanExporter -------+
                         |
               chọn bean được export
             ánh xạ ObjectName, metadata,
                thuộc tính và operation
                         |
                  MBeanServer
            (JMX registry trong JVM)
                         |
              MBean ObjectName:
         app.monitoring:type=Cache,name=main
                         |
             JMX connector / RMI
             (khi bật remote JMX)
                         |
             JConsole / JMX Client
       đọc attributes | invoke operations
          listen notifications
\`\`\`

Đây là **luồng quản trị**, không phải đường đi của mọi request nghiệp vụ. Bean tiếp tục phục vụ luồng nghiệp vụ bình thường; khi được export, nó có thêm một giao diện quan sát/điều khiển thông qua JMX.

## 2. Vai trò của từng thành phần

| Thành phần | Trách nhiệm | Cần nhớ |
|---|---|---|
| **Spring bean** | Chứa logic, trạng thái, dependency và vòng đời do ApplicationContext quản lý. | Không phải bean nào cũng tự động là MBean. |
| **\`MBeanExporter\`** | Chọn bean, tạo/nhận mô hình quản trị và đăng ký lên MBeanServer. | Đây là cầu nối chủ đạo từ Spring sang JMX. |
| **Assembler / metadata** | Quyết định method nào thành attribute getter/setter hoặc operation. | Bề mặt quản trị nên nhỏ và có chủ ý. |
| **\`ObjectName\`** | Tên duy nhất của một MBean trong MBeanServer, dạng domain:key=value. | Công cụ quản trị tra cứu theo ObjectName. |
| **\`MBeanServer\`** | Registry và điểm thực thi các lời gọi JMX; hỗ trợ tra cứu, lấy thuộc tính, gọi operation và notification. | Nó nằm phía server, trong tiến trình JVM. |
| **JMX connector** | Đưa giao diện JMX ra client khác tiến trình/máy. | Chỉ cần nếu muốn truy cập từ xa. |
| **JConsole / client JMX** | Duyệt MBean, hiển thị attribute, gọi operation, theo dõi notification. | Client không phải Spring ApplicationContext. |

Một \`ObjectName\` ví dụ là \`learning.jmx:type=CacheMonitor,name=main\`. Phần \`learning.jmx\` là *domain*, các cặp \`type\` và \`name\` là *key properties*. Tránh dùng \`ObjectName\` dễ trùng giữa các bean trong cùng một MBeanServer.

## 3. Chuỗi sự kiện lúc khởi động

1. **Spring tạo và cấu hình bean.** ApplicationContext khởi tạo bean theo cấu hình và hoàn tất giai đoạn cần thiết của lifecycle.
2. **\`MBeanExporter\` xác định đối tượng cần export.** Nó có thể nhận \`beans\` map khai báo rõ, hoặc sử dụng cơ chế phát hiện theo annotation khi được cấu hình.
3. **Chọn mô hình MBean.** Nếu bean đã tuân theo hợp đồng JMX (ví dụ Standard MBean phù hợp), nó có thể được đăng ký theo mô hình đó. Với bean Spring thông thường, Spring có thể sử dụng một \`ModelMBean\` và metadata để xác định các thuộc tính/operation có thể quản trị.
4. **Gán \`ObjectName\`.** Có thể khai báo tên cố định, dùng \`ObjectNamingStrategy\`, hoặc dùng annotation \`@ManagedResource\` cùng cơ chế phát hiện tương ứng.
5. **Đăng ký với \`MBeanServer\`.** Exporter dùng MBeanServer đã được cấp hoặc tìm/khởi tạo server theo cấu hình. Sau đăng ký, MBean tồn tại dưới ObjectName tương ứng.
6. **Client tìm và sử dụng MBean.** Một JMX client truy vấn danh sách tên, gọi \`getAttribute\`, \`setAttribute\`, \`invoke\`, hoặc đăng ký nhận notification.
7. **Khi ứng dụng dừng**, exporter quản lý việc hủy đăng ký các MBean do nó đăng ký theo lifecycle thích hợp.

Lưu ý rằng bước 5 tạo ra **giao diện JMX ở phía JVM**. Nó không tự động mở cổng mạng. Muốn kết nối từ xa phải cấu hình JMX connector hoặc cơ chế remote JMX tương ứng.

## 4. Ví dụ: Spring bean được export thành MBean

Ví dụ nhỏ sau dùng Spring Framework với cấu hình annotation và JMX. Bean ứng dụng giữ số lần xóa cache; giao diện JMX cho phép quan sát và gọi thao tác reset.

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main",
    description = "Cache monitoring and maintenance"
)
public class CacheMonitor {

    private final AtomicLong evictionCount = new AtomicLong();

    // Được gọi bởi luồng nghiệp vụ khi thực sự xóa cache.
    public void recordEviction() {
        evictionCount.incrementAndGet();
    }

    @ManagedAttribute(description = "Total cache evictions")
    public long getEvictionCount() {
        return evictionCount.get();
    }

    @ManagedOperation(description = "Reset the counter")
    public void resetCounter() {
        evictionCount.set(0);
    }
}
\`\`\`

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheMonitor.class)
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Trong cấu hình này:

- \`@Component\` đưa \`CacheMonitor\` vào Spring container.
- \`@EnableMBeanExport\` kích hoạt cấu hình xuất bản MBean và cơ chế xử lý các annotation JMX liên quan.
- \`@ManagedResource\` khai báo tài nguyên quản trị và \`ObjectName\`.
- \`@ManagedAttribute\` cho phép client đọc \`EvictionCount\` như một attribute.
- \`@ManagedOperation\` công bố \`resetCounter\` như một operation.

Tên thuộc tính JavaBean \`getEvictionCount()\` được bộc lộ tới JMX là \`EvictionCount\`. \`recordEviction()\` không có annotation quản trị trong ví dụ này nên không nằm trong giao diện JMX được export bởi metadata annotation.

**Đường đi thực tế của một thao tác đọc:**

\`\`\`text
JConsole
  -> tìm "learning.jmx:type=CacheMonitor,name=main"
  -> MBeanServer.getAttribute(objectName, "EvictionCount")
  -> ModelMBean / lớp ánh xạ do Spring tạo
  -> CacheMonitor.getEvictionCount()
  -> AtomicLong.get()
  -> giá trị long trở lại JConsole
\`\`\`

**Đường đi thực tế khi gọi operation:**

\`\`\`text
JConsole -> MBeanServer.invoke(objectName, "resetCounter", ...)
         -> ModelMBean/Spring adapter
         -> CacheMonitor.resetCounter()
         -> bộ đếm được đặt về 0
\`\`\`

Đây là lời gọi đồng bộ thông qua JMX trên **cùng đối tượng bean được quản lý**, không phải tạo một bản sao độc lập của \`CacheMonitor\` cho JConsole.

## 5. Cách quan sát bằng công cụ JMX

Với một ứng dụng đang chạy có MBean được export và quyền kết nối phù hợp:

1. Khởi chạy ứng dụng Spring, bảo đảm cấu hình JMX export được bật.
2. Mở **JConsole** từ JDK, kết nối tới local JVM tương ứng. Tùy môi trường có thể cần quyền người dùng hoặc cấu hình phù hợp để attach.
3. Vào tab **MBeans**, tìm domain \`learning.jmx\`, tiếp theo \`type=CacheMonitor,name=main\`.
4. Ở **Attributes**, đọc \`EvictionCount\`; tạo thêm các lần xóa cache trong ứng dụng để thấy giá trị thay đổi khi đọc lại.
5. Ở **Operations**, gọi \`resetCounter\`; đọc lại attribute và thấy giá trị trở về \`0\`.

Trạng thái thể hiện trong UI được client truy vấn qua JMX. Nó không nhất thiết là luồng cập nhật liên tục. Việc “refresh”, polling và notification phụ thuộc vào client và tính năng MBean.

### Kiểm chứng bằng JMX API

Thay cho giao diện đồ họa, code chạy trong cùng JVM có thể truy cập MBeanServer phù hợp:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name =
    new ObjectName("learning.jmx:type=CacheMonitor,name=main");

Object value = server.getAttribute(name, "EvictionCount");
System.out.println("Evictions = " + value);

server.invoke(name, "resetCounter", new Object[0], new String[0]);
\`\`\`

Đoạn này giả định exporter đăng ký bean trên **platform MBeanServer**. Nếu ứng dụng dùng MBeanServer khác, lấy đúng server được exporter dùng; \`getPlatformMBeanServer()\` không tự động nhìn thấy registry ở server riêng.

## 6. Ba đường cấu hình cần phân biệt

### A. Export theo annotation

Thích hợp khi muốn đặt metadata gần code và chỉ rõ các thao tác quản trị:

\`\`\`text
@Component + @ManagedResource
             |
@EnableMBeanExport + AnnotationMBeanExporter
             |
       MBeanServer
\`\`\`

Các annotation \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@ManagedNotification\` hoặc tham số liên quan mô tả bề mặt quản trị.

### B. Export theo danh sách bean

Có thể khai báo \`MBeanExporter\` với một map tên → bean, ví dụ khi không muốn annotation nằm trong lớp nghiệp vụ:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
class ManualJmxConfig {

    @Bean
    MBeanExporter mbeanExporter(CacheMonitor cacheMonitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "learning.jmx:type=CacheMonitor,name=manual", cacheMonitor
        ));
        return exporter;
    }
}
\`\`\`

Với bean Java thông thường, khả năng nhìn thấy attribute và operation phụ thuộc vào assembler và cấu hình export. Khai báo map tên → bean **không đồng nghĩa** mọi public method đều nên hay sẽ được công bố. Đặc biệt cần xác định cơ chế ánh xạ và tránh cấu hình hai exporter vô tình cùng đăng ký một ObjectName.

### C. Tự triển khai giao diện MBean chuẩn

Theo quy tắc Standard MBean của JMX, một lớp \`CacheStats\` có thể implement \`CacheStatsMBean\` và expose hợp đồng quản trị ở interface này. Spring có thể đăng ký MBean tuân thủ hợp đồng JMX; lúc đó tên và phương thức expose được xác định bởi quy tắc của JMX. Phương án này phù hợp khi hợp đồng quản trị phải rõ ràng và không muốn gắn annotation của Spring lên domain object.

Ba hướng trên phục vụ cùng mô hình: **đối tượng quản trị → ObjectName → MBeanServer → client**. Điều khác nhau là cách mô tả và chọn bề mặt MBean.

## 7. Phân biệt quản trị nội bộ và từ xa

\`\`\`text
[Local, cùng JVM]
Spring bean -> MBeanExporter -> MBeanServer
                                    |
                              local JMX client
                              hoặc JMX API

[Remote, có connector]
Spring bean -> MBeanExporter -> MBeanServer
                                    |
                             JMXConnectorServer
                                    |
                              network/RMI
                                    |
                              Remote client
\`\`\`

\`MBeanServer\` là nơi MBean được đăng ký và truy cập. \`JMXConnectorServer\` (hoặc agent quản trị JMX của JVM) là thành phần cung cấp kết nối remote. Chỉ bật \`@EnableMBeanExport\` **không đồng nghĩa** đã mở kết nối remote.

Khi có truy cập từ xa, cần kiểm soát xác thực, phân quyền, cấu hình TLS, địa chỉ bind, firewall và cổng RMI phù hợp. Các operation có khả năng thay đổi trạng thái (như reset, reload, purge) nên được xem là API quản trị nhạy cảm; tránh công bố đại trà và không mở endpoint JMX công khai lên Internet.

## 8. Các ngộ nhận thường gặp

| Ngộ nhận | Mô hình đúng |
|---|---|
| “Spring bean là MBean sẵn.” | Bean chỉ thành tài nguyên JMX khi được đăng ký/export bằng cơ chế phù hợp. |
| “JConsole gọi trực tiếp ApplicationContext.” | JConsole tương tác với MBeanServer qua JMX; Spring chỉ tạo cầu nối tới bean. |
| “Export MBean là bật port JMX.” | Export là đăng ký MBean; networking thuộc connector/agent remote. |
| “ObjectName là tên class.” | ObjectName là khóa định danh JMX, không bắt buộc trùng tên class. |
| “Tất cả method public sẽ xuất hiện.” | Phụ thuộc Standard MBean interface hoặc Spring assembler/metadata. |
| “Có hai bean cùng ObjectName vẫn ổn.” | ObjectName phải duy nhất trong một MBeanServer; đăng ký trùng cần chính sách xử lý rõ. |
| “MBean luôn là một object khác.” | Có thể là đối tượng MBean trực tiếp hoặc adapter/ModelMBean ủy quyền tới bean gốc. |
| “Gọi JMX là một sự kiện async.” | Đọc attribute và invoke operation là lời gọi yêu cầu/đáp ứng thông thường; notification là cơ chế khác. |

## 9. Sự cố và cách định vị theo từng mắt xích

**Không thấy domain/MBean trong JConsole:** kiểm tra ứng dụng có chạy, \`@EnableMBeanExport\` hoặc \`MBeanExporter\` đã được tạo, bean thực sự nằm trong ApplicationContext, \`ObjectName\` đúng, và client đang nối tới **đúng JVM/MBeanServer**. Nếu exporter dùng server riêng, client gắn vào platform server có thể không thấy MBean đó.

**MBean có tên nhưng thiếu attribute/operation:** xem annotation, tên getter/setter theo JavaBean conventions, interface MBean, assembler đang dùng và mô hình expose được chọn. Một method chỉ tồn tại trong class không bảo đảm nó đã được công bố qua JMX.

**Lỗi đăng ký ObjectName:** kiểm tra cú pháp JMX ObjectName, ký tự cần quote, tên trùng và chính sách xử lý existing registrations của exporter. Không giải quyết xung đột bằng cách xóa tùy tiện MBean khác.

**Công cụ kết nối được nhưng thao tác thất bại:** kiểm tra chữ ký operation, kiểu tham số, quyền truy cập, exception từ bean nghiệp vụ và log server. Một exception trong code được gọi có thể lan lên dạng lỗi JMX.

**Remote kết nối không ổn định:** kiểm tra connector/agent, hostname RMI được quảng bá, cổng registry và cổng RMI, NAT/firewall, TLS và authentication. JMX remote qua RMI thường cần lưu ý hơn một địa chỉ/cổng.

**Thay đổi giá trị nhưng UI chưa cập nhật:** xác minh thao tác đọc lại attribute, caching/polling của client và việc trạng thái của bean có thay đổi thật hay không. Notification không phát sinh tự động chỉ vì một field thay đổi.

## 10. Khi nào nên dùng JMX?

JMX hữu ích với **trạng thái quản trị trong JVM**: số lượng hàng đợi, kích thước pool, counters, trạng thái cache, hoặc một operation bảo trì được kiểm soát. Nó cũng dùng để quan sát thành phần JVM và thư viện vốn đã có MBean.

JMX không thay thế API phục vụ nghiệp vụ hoặc một hệ thống metrics time-series hoàn chỉnh. Nếu cần dashboard, alert dài hạn và phân tích thống kê, có thể xuất metrics sang hệ quan sát phù hợp, trong khi JMX vẫn làm kênh kiểm tra và quản trị trực tiếp. Hãy lựa chọn thông tin expose dựa trên nhu cầu vận hành và mức độ an toàn của từng operation.

## 11. Bài tập tư duy

**Tình huống:** ứng dụng có bean \`OrderQueue\`, cần xem số tác vụ đang chờ và có nút tạm dừng việc tiêu thụ tác vụ trong môi trường vận hành.

- Nêu rõ bean nào chứa trạng thái thật và bean nào chỉ là metadata hoặc adapter.
- Chọn một ObjectName, ví dụ \`learning.jmx:type=OrderQueue,name=primary\`, và giải thích vì sao phải duy nhất.
- Định nghĩa một attribute read-only \`PendingCount\`, một operation \`pauseConsumption()\`; cân nhắc liệu nên cung cấp operation đảo ngược \`resumeConsumption()\`.
- Vẽ đường đi của \`getAttribute\` và \`invoke\` từ công cụ JMX xuống bean.
- Mô tả cách operator kiểm tra đã kết nối đúng JVM và cách giới hạn quyền gọi operation thay đổi trạng thái.

**Câu trả lời mong đợi:** trạng thái thuộc bean nghiệp vụ; exporter/adapter chỉ làm cầu nối. Công cụ JMX gửi yêu cầu tới MBeanServer theo ObjectName, server chuyển tới implementation hoặc adapter, rồi đến logic bean. Kết nối remote và quyền thao tác phải được cấu hình riêng.

## 12. Ghi nhớ mô hình

\`\`\`text
Bean Spring được quản lý bởi ApplicationContext
  -> MBeanExporter chọn bean và mô tả giao diện quản trị
  -> ObjectName định danh MBean
  -> MBeanServer đăng ký và thực thi lời gọi
  -> JMX connector (nếu cần remote)
  -> JConsole / JMX client đọc attribute, gọi operation, nhận notification
\`\`\`

Câu hỏi kiểm tra cuối cùng: **“Ai sở hữu trạng thái thật, ai đăng ký đối tượng, ai định tuyến lời gọi, và ai chỉ là công cụ quan sát?”** Khi phân biệt được bốn vai trò đó, luồng Spring bean → MBeanServer → công cụ quản trị sẽ rõ ràng.