# RegistrationPolicy.REPLACE_EXISTING trong Spring Framework JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Registration policy  
> **Bài học:** RegistrationPolicy.REPLACE_EXISTING

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu vì sao hai MBean không thể đồng thời đăng ký cùng một \`ObjectName\` trong cùng \`MBeanServer\`.
- Giải thích ý nghĩa \`RegistrationPolicy.REPLACE_EXISTING\` của Spring JMX exporter.
- Phân biệt \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\` và \`REPLACE_EXISTING\`.
- Biết điều gì diễn ra khi exporter gặp một MBean đã tồn tại dưới cùng \`ObjectName\`.
- Nhận diện rủi ro khi thay thế MBean thuộc thành phần khác, làm gián đoạn monitoring, notification listener hoặc client proxy.
- Cấu hình policy có chủ đích, kiểm tra kết quả bằng \`MBeanServer\` và lựa chọn chính sách phù hợp từng môi trường.

## 2. Bối cảnh: một ObjectName chỉ trỏ đến một MBean tại một thời điểm

Một \`MBeanServer\` là registry quản lý các MBean bằng \`javax.management.ObjectName\`.

\`\`\`text
MBeanServer
  |
  +-- app.monitoring:type=Cache,name=primary
  |      -> MBean hiện có
  |
  +-- app.monitoring:type=WorkerPool,name=main
         -> MBean khác
\`\`\`

Nếu một exporter thứ hai cố đăng ký một MBean mới với tên:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

thì sẽ có xung đột tên. Theo quy tắc JMX thông thường, \`MBeanServer.registerMBean\` ném \`InstanceAlreadyExistsException\` khi tên đó đã được sử dụng.

Spring cung cấp \`org.springframework.jmx.support.RegistrationPolicy\` để quyết định cách \`MBeanExporter\` xử lý xung đột tại thời điểm đăng ký.

\`\`\`text
Spring exporter muốn đăng ký bean mới
                 |
                 v
         ObjectName đã tồn tại?
             /         \
           Không         Có
            |            |
            v            v
       Register mới   Áp dụng RegistrationPolicy
                           |
                   +-------+--------+
                   |       |        |
                  FAIL   IGNORE   REPLACE
\`\`\`

**Quan trọng:** Registration policy điều chỉnh cách exporter xử lý **xung đột đăng ký MBean**. Nó không thay đổi quy tắc đặt ObjectName, không xác thực quyền client và không làm mọi MBean trở nên tương thích với nhau.

## 3. REPLACE_EXISTING nghĩa là gì?

\`RegistrationPolicy.REPLACE_EXISTING\` yêu cầu Spring exporter xử lý trường hợp tên đã có bằng cách **thay thế registration cũ bằng MBean mới**.

Mô hình:

\`\`\`text
Trước:
  MBeanServer
    app.monitoring:type=Cache,name=primary
        -> OldCacheMBean

Exporter mới:
    muốn đăng ký NewCacheMBean cùng ObjectName
    policy = REPLACE_EXISTING

Trong quá trình:
    unregister MBean cũ
    register MBean mới

Sau khi thành công:
  MBeanServer
    app.monitoring:type=Cache,name=primary
        -> NewCacheMBean
\`\`\`

Trong Spring, đây là hành vi xử lý khi tên trùng, **không phải hot swap nguyên tử** hay thay implementation trực tiếp bên trong cùng một instance MBean.

Một client có thể gặp khoảng thời gian MBean chưa tồn tại giữa thao tác hủy đăng ký và đăng ký mới. Do đó, client không nên xem việc thay thế là hoàn toàn trong suốt.

### Điểm cần phân biệt

- \`REPLACE_EXISTING\` không tạo hai MBean đồng thời dưới cùng một tên.
- Không bảo đảm MBean mới có metadata attribute/operation tương thích với MBean cũ.
- Không mặc định giữ listener đã gắn vào MBean cũ.
- Không bảo đảm trạng thái nội bộ của MBean cũ được chuyển sang MBean mới.
- Không biến thao tác unregister/register thành một transaction có rollback tự động.
- Không cho phép exporter vượt qua mọi lỗi permission, initialization hoặc lifecycle.

## 4. So sánh ba registration policy

| Policy | Khi ObjectName chưa tồn tại | Khi ObjectName đã tồn tại | Ý nghĩa vận hành |
|---|---|---|---|
| \`FAIL_ON_EXISTING\` | Đăng ký MBean mới | Báo lỗi xung đột | Phát hiện cấu hình trùng, không âm thầm can thiệp MBean khác |
| \`IGNORE_EXISTING\` | Đăng ký MBean mới | Giữ MBean cũ, bỏ qua registration mới | Phù hợp khi muốn tái sử dụng MBean hiện có mà không thay thế |
| \`REPLACE_EXISTING\` | Đăng ký MBean mới | Hủy đăng ký MBean cũ rồi đăng ký MBean mới | Cho phép exporter chiếm ObjectName đã dùng, nhưng có thể phá vỡ client hiện tại |

Các tên enum có thể được sử dụng qua:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

RegistrationPolicy policy =
    RegistrationPolicy.REPLACE_EXISTING;
\`\`\`

Giá trị mặc định và khả năng cấu hình còn phụ thuộc Spring exporter cụ thể và phiên bản thư viện. Khi đánh giá một ứng dụng hiện có, hãy kiểm tra cấu hình thực tế thay vì mặc định giả định \`REPLACE_EXISTING\` đang được sử dụng.

## 5. Cấu hình REPLACE_EXISTING trong Spring

Ví dụ cấu hình \`MBeanExporter\` tường minh:

\`\`\`java
package example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagementFacade cacheFacade
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "app.monitoring:type=Cache,name=primary",
            cacheFacade
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.REPLACE_EXISTING
        );

        return exporter;
    }
}
\`\`\`

Giả định \`CacheManagementFacade\` là một Spring bean phù hợp để xuất bản qua JMX, chẳng hạn class có metadata \`@ManagedResource\`/\`@ManagedAttribute\` hoặc implement một MBean interface theo quy tắc tương ứng.

Phương thức \`setRegistrationPolicy\` thuộc cơ chế export/registration mà \`MBeanExporter\` kế thừa từ lớp hỗ trợ Spring JMX. Nó quyết định cách xử lý tên đã tồn tại trên MBeanServer được exporter sử dụng.

### Đừng tạo exporter trùng ngoài ý muốn

Nếu ứng dụng đã có \`@EnableMBeanExport\` hoặc Spring Boot tự cấu hình JMX exporter, thêm một \`MBeanExporter\` khác có thể khiến cả hai cùng xử lý một bean/ObjectName.

\`\`\`text
AnnotationMBeanExporter  ----\
                               > cùng ObjectName -> conflict
MBeanExporter thủ công  ------/
\`\`\`

\`REPLACE_EXISTING\` không phải cách sửa tốt cho một cấu hình bị trùng exporter do sơ suất. Nên trước hết xác định bean nào thuộc exporter nào, rồi loại bỏ cấu hình trùng không cần thiết. Chỉ thay thế khi đó là yêu cầu lifecycle có chủ đích.

## 6. Ví dụ MBean và thử xung đột

Để quan sát hành vi registry, tạo một Standard MBean đơn giản.

### 6.1. Interface

\`\`\`java
package example.jmx;

public interface CounterMBean {
    int getCount();
    void increment();
}
\`\`\`

### 6.2. Implementation

\`\`\`java
package example.jmx;

public class Counter implements CounterMBean {

    private int count;

    public Counter(int initialValue) {
        this.count = initialValue;
    }

    @Override
    public synchronized int getCount() {
        return count;
    }

    @Override
    public synchronized void increment() {
        count++;
    }
}
\`\`\`

### 6.3. Tình huống xung đột qua JMX thuần

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=Counter,name=primary"
);

server.registerMBean(new Counter(3), name);

// Đăng ký cùng tên một lần nữa sẽ phát sinh
// InstanceAlreadyExistsException:
server.registerMBean(new Counter(100), name);
\`\`\`

Lệnh thứ hai minh họa nguyên nhân policy tồn tại. Không chạy đoạn này mà không có cleanup trong test thật; nếu tên đã được dùng trước đó, đăng ký đầu tiên cũng có thể thất bại.

**Spring REPLACE_EXISTING** thực hiện xử lý xung đột ở tầng exporter. JMX thuần không có tham số \`RegistrationPolicy\` trên \`registerMBean\`.

## 7. Chu trình thay thế và hệ quả không nguyên tử

Giả sử MBean cũ \`Counter(3)\` được đăng ký dưới:

\`\`\`text
learning.jmx:type=Counter,name=primary
\`\`\`

Exporter mới cấu hình \`REPLACE_EXISTING\` cho \`Counter(100)\` cùng tên.

Từ góc nhìn logic:

\`\`\`text
1. Đăng ký MBean mới với ObjectName.
2. Phát hiện InstanceAlreadyExistsException.
3. Policy yêu cầu xử lý thay thế.
4. Unregister MBean cũ.
5. Register MBean mới dưới cùng ObjectName.
6. Ghi nhận registration mới để quản lý lifecycle.
\`\`\`

Các bước thực tế và exception handling chi tiết là trách nhiệm của Spring exporter, nhưng **bản chất là thay đổi registry**, không phải thay các field trên object cũ.

Một client liên tục gọi:

\`\`\`java
connection.getAttribute(name, "Count");
\`\`\`

có thể quan sát:

\`\`\`text
Trước thay thế: Count = 3
Trong khoảng unregister/register: MBean không tìm thấy
Sau thay thế: Count = 100
\`\`\`

Đây là kịch bản minh họa. Khoảng thời gian thực tế phụ thuộc scheduling và cách client gọi; có thể không quan sát được lỗi trong một lần thử nhưng vẫn có race.

## 8. Rủi ro của REPLACE_EXISTING

### 8.1. Thay nhầm MBean không thuộc sở hữu

Một MBean có thể được đăng ký bởi:

- Một Spring ApplicationContext khác.
- Monitoring agent hoặc thư viện bên thứ ba.
- Mã Java trực tiếp qua \`registerMBean\`.
- Một phiên bản ứng dụng đang hoạt động.
- Infrastructure của JVM.

Nếu exporter sử dụng \`REPLACE_EXISTING\` với tên trùng, có nguy cơ unregister một MBean do thành phần khác sở hữu. Khi đó, tài nguyên quản trị gốc có thể bị mất khỏi registry.

Đừng dùng policy này trên domain rộng hoặc ObjectName suy đoán từ class nếu không kiểm soát quyền sở hữu registration.

### 8.2. Thay đổi attribute hoặc operation

MBean cũ có:

\`\`\`text
Attribute: PendingJobs (int)
Operation: pause()
\`\`\`

MBean mới có:

\`\`\`text
Attribute: QueueDepth (long)
Operation: suspend(boolean)
\`\`\`

Dù ObjectName giống nhau, client cũ gọi \`getAttribute("PendingJobs")\` có thể nhận \`AttributeNotFoundException\`, và \`invoke("pause")\` có thể lỗi vì operation không còn.

**Ổn định ObjectName không tự bảo đảm tương thích hợp đồng JMX.** Cần so sánh \`MBeanInfo\` khi thay phiên bản quản trị.

### 8.3. Listener notification có thể bị mất

Nếu client đã đăng ký \`NotificationListener\` trên MBean cũ, unregister MBean có thể làm mất registration gắn với broadcaster cũ. Sau đó MBean mới có cùng ObjectName không có nghĩa listener cũ tự chuyển sang instance mới.

Client cần theo dõi lifecycle và có khả năng đăng ký lại listener. Có thể quan sát các sự kiện đăng ký/hủy đăng ký qua \`MBeanServerDelegate\`.

### 8.4. State không được di chuyển

Nếu MBean cũ lưu counter bằng field và MBean mới khởi tạo counter khác, thay thế sẽ thay trạng thái quan sát được. \`REPLACE_EXISTING\` không tự sao chép object state hay dữ liệu business.

Khi cần state liên tục, dùng service/metrics repository ổn định hoặc thiết kế migration riêng thay vì dựa vào registration policy.

### 8.5. Thay thế không nhất thiết rollback khi đăng ký mới thất bại

Nếu MBean cũ đã unregister nhưng đăng ký MBean mới lỗi, không được tự giả định Spring/JMX sẽ phục hồi MBean cũ như một transaction. Cần đọc exception và thiết kế fallback/recovery phù hợp, đặc biệt khi đăng ký một MBean giữ chức năng giám sát quan trọng.

## 9. Lifecycle của Spring exporter

Spring exporter quản lý các MBean mà nó đăng ký theo lifecycle của Spring bean hoặc ApplicationContext, tùy cấu hình.

\`\`\`text
ApplicationContext start
        |
        v
MBeanExporter initialization
        |
        +--> đăng ký MBean
        |       |
        |       +--> nếu trùng:
        |             REPLACE_EXISTING
        |
        v
MBeanServer registry cập nhật
        |
        v
ApplicationContext shutdown
        |
        v
Exporter cleanup registrations thuộc phạm vi quản lý
\`\`\`

Một hệ quả quan trọng của việc thay thế: sau khi exporter mới chiếm ObjectName và sau đó đóng context, registry có thể không tự khôi phục MBean cũ đã bị unregister. Đừng coi \`REPLACE_EXISTING\` là override tạm thời có khả năng rollback.

Nếu nhiều ApplicationContext có lifecycle chồng lấn trong cùng JVM, hãy thiết kế ownership rõ ràng, tránh hai exporter tranh chấp cùng tên.

## 10. Kiểm tra trước và sau khi thay thế

Có thể quan sát trạng thái đăng ký:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "learning.jmx:type=Counter,name=primary"
);

System.out.println(
    "Registered: " + server.isRegistered(name)
);

if (server.isRegistered(name)) {
    Object count = server.getAttribute(name, "Count");
    System.out.println("Count = " + count);
}
\`\`\`

Một phép kiểm tra \`isRegistered\` và thao tác \`getAttribute\` là hai lời gọi riêng, vì vậy MBean có thể biến mất giữa chúng. Cần xử lý \`InstanceNotFoundException\` khi client hoạt động trong môi trường thay đổi registry.

Với JConsole:

1. Kết nối đúng JVM.
2. Mở tab **MBeans**.
3. Tìm ObjectName của MBean đang thử.
4. Quan sát attribute và operation trước khi exporter thay thế.
5. Kích hoạt chu trình ứng dụng có cấu hình \`REPLACE_EXISTING\` trong môi trường kiểm thử.
6. Refresh danh sách MBeans nếu cần.
7. Đọc lại attribute, operation và notification metadata.
8. Xác nhận MBean hiện tại thực sự thuộc implementation mong muốn.

Không nên thực hiện thử nghiệm thay thế MBean đang phục vụ monitoring sản xuất nếu không có phương án chuyển đổi và phục hồi.

## 11. Dùng MBeanInfo để kiểm tra hợp đồng sau thay thế

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(
    "MBean class: " + info.getClassName()
);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s type=%s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "Operation: " + op.getName()
            + " -> " + op.getReturnType()
    );
}
\`\`\`

Sau khi replacement thành công, kiểm tra:

- ObjectName có còn tồn tại không?
- Attribute client đang dùng có còn tên, kiểu và quyền đọc/ghi như trước không?
- Operation còn cùng chữ ký tham số và kiểu trả về không?
- Notification types có tương thích với các listener đang dùng không?
- Giá trị trạng thái có thay đổi hợp lý không?

Không chỉ dựa vào \`info.getClassName()\`, vì với Spring ModelMBean/adapter, tên class metadata có thể không phải class service nội bộ bạn muốn nhận diện.

## 12. Theo dõi registry bằng MBeanServerDelegate

JMX có MBean hệ thống \`JMImplementation:type=MBeanServerDelegate\`. Nó phát notification khi MBean được register hoặc unregister.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener listener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            System.out.println(
                event.getType() + " : " + event.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    listener,
    null,
    null
);

try {
    // Thực hiện bước khởi tạo exporter trong môi trường test.
} finally {
    server.removeNotificationListener(
        MBeanServerDelegate.DELEGATE_NAME,
        listener
    );
}
\`\`\`

Khi replacement diễn ra, listener theo dõi registry có thể quan sát sự kiện unregister rồi register lại dưới cùng một ObjectName.

Đây là một cách kiểm chứng rằng registry thực sự thay đổi. Tuy nhiên event listener cũng có vòng đời riêng; nếu đăng ký quá muộn, có thể không thấy sự kiện đã xảy ra. Đừng xem notification registry là một lịch sử bền vững.

## 13. MBean proxy và replacement

Một client có thể tạo proxy:

\`\`\`java
import javax.management.JMX;

CounterMBean proxy = JMX.newMBeanProxy(
    connection,
    name,
    CounterMBean.class
);
\`\`\`

Proxy thường giữ \`ObjectName\` và connection, không giữ trực tiếp tham chiếu tới implementation server-side.

Sau replacement, proxy có thể tiếp tục định tuyến các lời gọi đến MBean mới dưới cùng tên **nếu** operation/attribute vẫn tương thích. Nhưng proxy cũng có thể gặp:

- \`InstanceNotFoundException\` hoặc exception được proxy bao bọc trong khoảng unregister/register.
- Lỗi khi signature đổi.
- Lỗi kiểu trả về nếu interface cũ không còn tương thích.
- Logic bất ngờ nếu MBean mới có trạng thái khác.

Không xem proxy là bằng chứng bảo đảm replacement trong suốt. Với service quản trị quan trọng, cần lập kế hoạch tương thích và khả năng retry có giới hạn nếu appropriate; tránh retry operation có tác dụng phụ khi không biết lời gọi trước đã hoàn tất hay chưa.

## 14. REPLACE_EXISTING không phải cơ chế hot deployment

Các khái niệm có thể dễ bị lẫn:

| Cơ chế | Mục tiêu | Có chuyển state tự động? |
|---|---|---|
| Spring \`REPLACE_EXISTING\` | Giải quyết xung đột ObjectName bằng thay registration | Không |
| Hot reload bean/application | Thay code hoặc context trong quá trình phát triển | Không mặc nhiên |
| Rolling deployment | Chuyển phiên bản dịch vụ theo nhiều instance | Phụ thuộc hạ tầng |
| MBean facade ổn định | Giữ contract quản trị khi implementation đổi | Không tự chuyển state, nhưng có thể giữ cùng service phụ trợ |
| Stateful migration | Chuyển trạng thái dữ liệu từ phiên bản cũ sang mới | Cần thiết kế riêng |

Với sản phẩm có client JMX bên ngoài, cách tốt hơn thường là giữ MBean facade ổn định và thay dependency bên dưới, thay vì unregister/register MBean mỗi lần muốn đổi implementation.

## 15. Khi nào REPLACE_EXISTING có thể phù hợp?

Một số trường hợp có thể cân nhắc:

- Môi trường test cần đăng ký lại MBean đã được tạo bởi một vòng setup trước, với ownership được kiểm soát rõ.
- Chu trình restart/reload của một thành phần được thiết kế để thay registration của chính nó.
- Migration có phối hợp, biết chắc tên thuộc phạm vi ứng dụng và client có thể chịu gián đoạn ngắn.
- Một cấu hình quản lý MBean cũ/mới có kế hoạch cleanup rõ ràng.

Những điều kiện nên có trước khi dùng:

1. Xác nhận **ai sở hữu ObjectName hiện có**.
2. Xác nhận replacement là hành vi mong muốn, không phải dấu hiệu cấu hình hai exporter trùng.
3. Kiểm tra hợp đồng mới tương thích với client.
4. Có phương án subscription lại listener.
5. Có kế hoạch khi đăng ký MBean mới thất bại.
6. Có log/telemetry để truy vết việc thay registration.
7. Không dựa vào policy để “chiếm” MBean của thư viện hoặc JVM khác.

## 16. Khi nào không nên dùng?

Tránh \`REPLACE_EXISTING\` như phương án mặc định khi:

- Chưa biết lý do ObjectName trùng.
- Nhiều ApplicationContext hoặc module cùng tồn tại nhưng không có ownership rõ.
- MBean có listener hoặc client dài hạn và replacement gây gián đoạn.
- Có thể sửa naming strategy để mỗi MBean có tên riêng.
- Xung đột do Spring Boot auto-configuration và exporter tự tạo chồng nhau.
- MBean cũ chứa state quản trị không thể mất.
- MBean thuộc hệ thống hoặc thư viện bên ngoài không do ứng dụng quản lý.

Trong các trường hợp này, \`FAIL_ON_EXISTING\` giúp phát hiện cấu hình trùng sớm; \`IGNORE_EXISTING\` có thể phù hợp nếu chủ đích là giữ registration đã tồn tại, nhưng cũng phải kiểm tra contract và ownership.

## 17. Phân biệt IGNORE_EXISTING và REPLACE_EXISTING

Giả sử server đã có \`Counter(3)\` với tên \`learning.jmx:type=Counter,name=primary\`.

Exporter cố đăng ký \`Counter(100)\` cùng tên.

**IGNORE_EXISTING:**

\`\`\`text
MBeanServer vẫn trỏ tới Counter(3)
Count = 3
\`\`\`

**REPLACE_EXISTING:**

\`\`\`text
MBeanServer trỏ tới Counter(100)
Count = 100
\`\`\`

**FAIL_ON_EXISTING:**

\`\`\`text
Báo lỗi xung đột
MBean cũ không bị policy chủ đích thay thế
\`\`\`

Không nên đánh giá IGNORE là “không lỗi nên an toàn” trong mọi trường hợp. Nếu deployment mong đợi MBean mới, ignore có thể khiến công cụ tiếp tục nhìn thấy metadata hoặc trạng thái cũ. Cần kiểm tra kết quả thực tế.

## 18. Bảo vệ quyền truy cập và dữ liệu

\`REPLACE_EXISTING\` là chính sách đăng ký, không phải security policy. Nó không:

- Xác thực client JMX.
- Phân quyền gọi operation.
- Mã hóa remote connector.
- Kiểm tra dữ liệu đầu vào của operation.
- Chặn việc export secret qua attribute.
- Giới hạn tác dụng phụ của management operation.

Nếu một MBean mới expose thêm \`@ManagedOperation\` nguy hiểm, việc replacement có thể vô tình mở rộng bề mặt quản trị dưới một ObjectName mà client vốn đã biết.

Nên kiểm tra \`MBeanInfo\` và chính sách quyền khi thay phiên bản, đặc biệt ở môi trường có remote JMX connector.

## 19. Ví dụ kiểm thử kết quả trong một context có exporter

Một test tích hợp có thể tạo MBean cũ bằng API JMX thuần, sau đó khởi tạo Spring context chứa exporter mới có policy \`REPLACE_EXISTING\`. Cuối cùng đọc lại attribute để xác nhận MBean mới được đăng ký.

Phác thảo các bước:

\`\`\`text
1. Tạo MBeanServer riêng cho test.
2. Register Counter(3) dưới ObjectName X.
3. Khởi tạo Spring MBeanExporter được trỏ tới cùng server.
4. Cấu hình exporter với Counter(100) và REPLACE_EXISTING.
5. Khởi tạo exporter để đăng ký bean mới.
6. Assert MBeanServer.getAttribute(X, "Count") == 100.
7. Đóng exporter/context.
8. Kiểm tra cleanup và đóng server test nếu cần.
\`\`\`

Trong test thật, nên tạo một MBeanServer riêng để tránh ảnh hưởng platform MBeanServer đang được JVM/test runner khác sử dụng.

Đoạn cấu hình exporter tương ứng:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(testMBeanServer);
exporter.setBeans(Map.of(
    "learning.jmx:type=Counter,name=primary",
    new Counter(100)
));
exporter.setRegistrationPolicy(
    RegistrationPolicy.REPLACE_EXISTING
);
exporter.afterPropertiesSet();
exporter.afterSingletonsInstantiated();
\`\`\`

Đây là phác thảo kiểm thử exporter lifecycle; trong Spring context thật, Spring gọi các lifecycle callback thích hợp. Nếu tạo exporter thủ công, cần tuân thủ hợp đồng lifecycle của phiên bản Spring đang dùng và gọi cleanup thích hợp, không chỉ coi \`setBeans\` là đã đăng ký ngay lập tức.

## 20. Checklist trước khi bật REPLACE_EXISTING

- [ ] Đã xác minh ObjectName cần thay thế thuộc phạm vi quản lý của ứng dụng.
- [ ] Biết chính xác lý do registration xung đột.
- [ ] Đã loại trừ cấu hình exporter trùng không chủ đích.
- [ ] MBean mới công bố attribute/operation/notification tương thích với client.
- [ ] Không phụ thuộc vào việc giữ state bên trong MBean cũ.
- [ ] Client có khả năng chịu khoảng unregister/register.
- [ ] Listener dài hạn có chiến lược đăng ký lại.
- [ ] Có cách quan sát exception và kết quả registration.
- [ ] Có phương án xử lý nếu replacement thất bại giữa chừng.
- [ ] Đã đánh giá quyền truy cập JMX và bề mặt quản trị mới.
- [ ] Có kiểm thử trong MBeanServer riêng hoặc môi trường không ảnh hưởng sản xuất.
- [ ] Có kế hoạch dọn registration khi context đóng.

## 21. Câu hỏi tự kiểm tra

1. Vì sao MBeanServer không thể có hai MBean cùng ObjectName?
2. \`REPLACE_EXISTING\` làm gì khi tên chưa tồn tại?
3. Điểm khác nhau giữa \`REPLACE_EXISTING\` và \`IGNORE_EXISTING\` là gì?
4. Vì sao không nên dùng REPLACE để che giấu lỗi cấu hình hai exporter?
5. Listener đã đăng ký trên MBean cũ có tự chuyển sang MBean mới không?
6. Một proxy giữ cùng ObjectName có chắc hoạt động sau replacement không?
7. Vì sao thay registration có thể làm client gặp \`InstanceNotFoundException\` trong thời gian ngắn?
8. \`REPLACE_EXISTING\` có tự copy state hoặc rollback MBean cũ không?
9. Vì sao nên đọc \`MBeanInfo\` sau replacement?
10. Khi nào \`FAIL_ON_EXISTING\` là lựa chọn phù hợp hơn cho hệ thống sản xuất?

## 22. Ghi nhớ

\`\`\`text
MBeanExporter
    |
    v
register MBean với ObjectName X
    |
    +-- chưa có X -> đăng ký bình thường
    |
    +-- X đã tồn tại
          |
          +-- FAIL_ON_EXISTING
          |       -> báo lỗi
          |
          +-- IGNORE_EXISTING
          |       -> giữ MBean cũ
          |
          +-- REPLACE_EXISTING
                  -> unregister MBean cũ
                  -> register MBean mới
\`\`\`

**Điểm cốt lõi:** \`RegistrationPolicy.REPLACE_EXISTING\` là cơ chế xử lý **xung đột tên đăng ký** của Spring JMX. Nó không phải một bản nâng cấp không gián đoạn, không phải cơ chế chuyển state và không giải quyết tự động vấn đề ownership hay tương thích API. Chỉ dùng khi replacement là chủ đích đã được thiết kế và kiểm chứng.