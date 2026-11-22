# RegistrationPolicy.IGNORE_EXISTING trong Spring Framework JMX

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích ý nghĩa của \`RegistrationPolicy.IGNORE_EXISTING\` khi Spring Framework xuất MBean qua \`MBeanExporter\`, xác định điều gì xảy ra khi một \`ObjectName\` đã có trong \`MBeanServer\`, phân biệt chế độ bỏ qua với báo lỗi và thay thế, cấu hình policy bằng Java hoặc XML, kiểm tra instance thực sự đang được quản lý, đồng thời thiết kế vòng đời đăng ký để tránh xung đột giữa các Spring \`ApplicationContext\`.

## 1. Bối cảnh: mỗi ObjectName chỉ có một registration

JMX (Java Management Extensions) quản lý các MBean đã được đăng ký trong một \`MBeanServer\`. Mỗi registration có một \`javax.management.ObjectName\`, ví dụ:

\`\`\`text
com.example.monitoring:type=CacheMonitor,name=primary
\`\`\`

Trong **một MBean server**, hai MBean không thể cùng tồn tại với chính xác một \`ObjectName\`. Nếu một component cố đăng ký object mới dưới tên đã có, API JMX \`registerMBean\` thông thường ném \`InstanceAlreadyExistsException\`.

Spring Framework cung cấp \`MBeanExporter\` để đưa Spring beans vào JMX registry. Khi exporter gặp tên đã đăng ký trước đó, **registration policy** quyết định cách xử lý xung đột:

| Policy | Kết quả khi tên đã tồn tại | Hệ quả |
| --- | --- | --- |
| \`RegistrationPolicy.FAIL_ON_EXISTING\` | Báo lỗi | Dễ phát hiện cấu hình trùng tên |
| \`RegistrationPolicy.IGNORE_EXISTING\` | Bỏ qua registration mới | MBean cũ vẫn giữ nguyên |
| \`RegistrationPolicy.REPLACE_EXISTING\` | Thay registration cũ bằng đối tượng mới | Cần hiểu rõ quyền sở hữu và tác động lên client |

Trong các phiên bản Spring Framework dùng enum \`RegistrationPolicy\`, nó thuộc package \`org.springframework.jmx.support\`. Các hằng số \`REGISTRATION_FAIL_ON_EXISTING\`, \`REGISTRATION_IGNORE_EXISTING\`, \`REGISTRATION_REPLACE_EXISTING\` là dạng integer constants xuất hiện trong API/cấu hình cũ. Khi viết code mới, nên dùng enum nếu API của phiên bản Spring đang dùng hỗ trợ.

## 2. Ý nghĩa chính xác của IGNORE_EXISTING

\`RegistrationPolicy.IGNORE_EXISTING\` cho biết exporter:

> Nếu có một MBean đang đăng ký dưới \`ObjectName\` mong muốn, không thay thế nó bằng MBean của exporter hiện tại và tiếp tục theo policy.

Điểm cần nhớ:

1. **MBean đang có vẫn là instance cũ.** Client đọc attribute hoặc invoke operation theo tên đó sẽ tiếp tục tương tác với object đang được đăng ký trước đó.
2. **Bean Spring mới vẫn có thể tồn tại trong \`ApplicationContext\`.** Việc bỏ qua JMX registration không hủy hoặc vô hiệu hóa Spring bean.
3. **Không tạo hai MBean trùng tên.** Registry vẫn chứa một entry duy nhất cho \`ObjectName\` đó.
4. **Không đồng bộ trạng thái giữa hai bean.** MBean cũ không tự chuyển sang dữ liệu của bean mới, và exporter không tạo proxy hợp nhất.
5. **Không tự giải quyết sai naming strategy.** Nếu cần quản trị riêng hai instance, phải đặt \`ObjectName\` khác nhau cho mỗi instance.

Ví dụ:

\`\`\`text
Exporter A -> cacheMonitorA -> com.example:type=CacheMonitor,name=primary
Exporter B -> cacheMonitorB -> com.example:type=CacheMonitor,name=primary
\`\`\`

Nếu A đăng ký trước, B dùng \`IGNORE_EXISTING\`, JMX client vẫn nhìn thấy \`cacheMonitorA\`; \`cacheMonitorB\` không được xuất dưới tên này. Điều đó có thể khiến dashboard hiển thị số liệu cũ hoặc số liệu của context khác nếu người vận hành tưởng B đã thay thế A.

## 3. Ví dụ một Standard MBean

Tạo interface JMX chuẩn và implementation để quan sát rõ trạng thái của từng instance.

**CacheMonitorMBean.java**

\`\`\`java
package com.example.jmx;

public interface CacheMonitorMBean {
    String getInstanceId();
    long getHitCount();
    void incrementHits();
}
\`\`\`

**CacheMonitor.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {
    private final String instanceId;
    private final AtomicLong hitCount = new AtomicLong();

    public CacheMonitor(String instanceId) {
        this.instanceId = instanceId;
    }

    @Override
    public String getInstanceId() {
        return instanceId;
    }

    @Override
    public long getHitCount() {
        return hitCount.get();
    }

    @Override
    public void incrementHits() {
        hitCount.incrementAndGet();
    }
}
\`\`\`

Đây là Standard MBean theo convention \`CacheMonitor\` → \`CacheMonitorMBean\`. JMX công bố hai attributes \`InstanceId\`, \`HitCount\`, và operation \`incrementHits\`. Operation tăng bộ đếm có side effect, vì vậy chỉ gọi trong môi trường thử nghiệm hoặc khi đã hiểu ảnh hưởng.

Tạo hai instance để phân biệt dữ liệu:

\`\`\`java
CacheMonitor first = new CacheMonitor("context-A");
CacheMonitor second = new CacheMonitor("context-B");

first.incrementHits();
first.incrementHits();
second.incrementHits();
\`\`\`

Lúc này \`first\` có 2 hits còn \`second\` có 1. Nếu JMX registry vẫn chứa \`first\`, attribute \`InstanceId\` sẽ trả \`context-A\`, bất kể context chứa \`second\` có khởi tạo thành công hay không.

## 4. Cấu hình RegistrationPolicy.IGNORE_EXISTING trong MBeanExporter

Ví dụ Java configuration với Spring Framework:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxIgnoreExistingConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor("spring-context-B");
    }

    @Bean
    public MBeanExporter mBeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setRegistrationPolicy(
                RegistrationPolicy.IGNORE_EXISTING);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=CacheMonitor,name=primary",
                cacheMonitor
        ));
        return exporter;
    }
}
\`\`\`

Cấu hình này nói rằng: exporter muốn đưa \`cacheMonitor\` ra JMX với tên đã chỉ định; nếu tên đã có trong server, exporter bỏ qua việc đăng ký đối tượng này.

**Nếu tên chưa tồn tại**, exporter vẫn đăng ký bean mới bình thường. \`IGNORE_EXISTING\` không có nghĩa là bỏ qua tất cả bean; nó chỉ thay đổi hành vi khi xảy ra xung đột.

**Nếu tên đã tồn tại**, đối tượng đang đăng ký được giữ lại. Mặc dù \`ApplicationContext\` vẫn chứa \`cacheMonitor\` của cấu hình mới, giá trị mà JMX client đọc dưới tên đó thuộc về MBean cũ.

## 5. Mô phỏng xung đột với MBeanServer trong cùng JVM

Để có ví dụ thực hành có thể quan sát, đăng ký trước một MBean vào platform server rồi tạo Spring context dùng policy IGNORE.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class IgnoreExistingDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=CacheMonitor,name=primary");

        CacheMonitor existing = new CacheMonitor("existing-owner");
        existing.incrementHits();
        existing.incrementHits();

        server.registerMBean(existing, name);

        try {
            try (var context = new AnnotationConfigApplicationContext(
                    JmxIgnoreExistingConfiguration.class)) {

                CacheMonitor candidate = context.getBean(CacheMonitor.class);
                candidate.incrementHits();

                System.out.println("Spring instance: "
                        + candidate.getInstanceId());

                System.out.println("JMX registered: "
                        + server.isRegistered(name));

                System.out.println("JMX instance: "
                        + server.getAttribute(name, "InstanceId"));

                System.out.println("JMX hits: "
                        + server.getAttribute(name, "HitCount"));
            }

            System.out.println("After Spring context closes: "
                    + server.isRegistered(name));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
    }
}
\`\`\`

Kết quả dự kiến:

\`\`\`text
Spring instance: spring-context-B
JMX registered: true
JMX instance: existing-owner
JMX hits: 2
After Spring context closes: true
\`\`\`

Điều quan trọng là kết quả JMX thuộc MBean đăng ký trước. Trong cấu hình thông thường, exporter bỏ qua một registration đã tồn tại không nên coi nó là MBean do exporter tự tạo và tự gỡ khi đóng context. Việc ghi nhận cleanup rõ ràng trong demo giúp tránh để MBean thử nghiệm tồn tại sau khi hoàn thành.

Ví dụ trên phù hợp cho môi trường thử nghiệm cô lập. Nếu tên đó đã được một ứng dụng khác trong cùng JVM dùng, lời gọi \`registerMBean\` đầu tiên sẽ báo trùng; không dùng đoạn cleanup để xóa registration không thuộc bài thử.

## 6. Phân biệt IGNORE_EXISTING với FAIL_ON_EXISTING và REPLACE_EXISTING

Đặt ba chiến lược cạnh nhau:

### FAIL_ON_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
\`\`\`

Khi tên đã có, exporter báo lỗi đăng ký. Điều này thường hữu ích trong môi trường yêu cầu cấu hình chính xác: xung đột được phát hiện sớm thay vì âm thầm dùng một instance khác.

### IGNORE_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.IGNORE_EXISTING);
\`\`\`

Khi tên đã có, exporter bỏ qua bean mới tại tên đó và tiếp tục. Chiến lược này hữu ích khi nhiều context hoặc module có thể cùng cung cấp một MBean bổ sung, nhưng sự tồn tại của một registration trước đó được xem là chấp nhận được.

### REPLACE_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.REPLACE_EXISTING);
\`\`\`

Khi tên đã có, exporter thay thế MBean cũ bằng MBean mới. Điều này có thể thay đổi đối tượng mà các công cụ quản trị đang theo dõi, khiến số liệu/operation chuyển sang instance khác. Cần biết rõ ai sở hữu registration và chuyện gì xảy ra khi context cũ hoặc mới đóng.

| Câu hỏi | FAIL | IGNORE | REPLACE |
| --- | --- | --- | --- |
| Có phát hiện xung đột rõ ràng? | Có, bằng lỗi | Có thể ghi nhận trong log, nhưng không buộc dừng | Có thể thay đổi registration |
| Instance cũ có tiếp tục làm MBean? | Có cho đến khi chủ cũ gỡ | Có | Không, sau khi thay thế thành công |
| Instance mới có được đăng ký ở tên trùng? | Không | Không | Có |
| Phù hợp để giữ đồng thời hai instance? | Không | Không | Không |

Nếu bài toán yêu cầu theo dõi hai instance riêng, hãy tạo hai \`ObjectName\` khác nhau. Registration policy không thay thế được naming strategy.

## 7. Tình huống dùng IGNORE_EXISTING

### 7.1. Nhiều ApplicationContext cùng chia sẻ một JVM

Một ứng dụng có thể có root context và child context. Cả hai sử dụng cùng platform \`MBeanServer\`, và cấu hình chung vô tình export cùng \`ObjectName\`.

Dùng \`IGNORE_EXISTING\` ở context thứ hai có thể tránh lỗi khởi tạo, nhưng không giúp bean của context đó xuất hiện qua tên trùng. Điều này chỉ phù hợp nếu thực sự muốn giữ MBean đã có.

### 7.2. Module tùy chọn cung cấp MBean dự phòng

Một module phụ có thể muốn đăng ký MBean quản lý khi module chính chưa có. Nếu MBean chính đã tồn tại, module phụ không cần thay thế. \`IGNORE_EXISTING\` có thể thể hiện ý định này.

Phải bảo đảm hợp đồng quản lý của MBean hiện có phù hợp với cách công cụ giám sát sử dụng tên đó. Chỉ cùng \`ObjectName\` không có nghĩa hai implementation cung cấp cùng attributes hoặc operations.

### 7.3. Môi trường test hoặc application context được khởi tạo nhiều lần

Trong integration tests, việc nhiều context dùng chung platform server có thể tạo xung đột. \`IGNORE_EXISTING\` làm test dễ khởi tạo hơn, nhưng có nguy cơ khiến test đọc MBean còn sót từ lần chạy trước.

Trong test cần chứng minh đúng bean được export, nên dùng MBean server riêng, tên thử nghiệm riêng và cleanup chính xác thay vì dựa vào policy IGNORE để che xung đột.

### 7.4. Rolling context replacement trong cùng tiến trình

Khi context mới được dựng trước khi context cũ đóng, hai exporter có thể cùng chọn một \`ObjectName\`. Dùng IGNORE khiến context mới không thay thế MBean cũ trong giai đoạn chồng lấn. Sau khi context cũ gỡ MBean, không nên giả định exporter mới sẽ tự động đăng ký lại object đã bị bỏ qua.

Vì vậy, IGNORE thường không phù hợp nếu mục tiêu là chuyển giao ownership MBean sang context mới một cách chắc chắn. Cần có quy trình chuyển giao, tên mới hoặc cơ chế đăng ký lại rõ ràng.

## 8. Vòng đời và quyền sở hữu MBean

Đây là phần quan trọng nhất khi sử dụng IGNORE. Một exporter chỉ nên quản lý vòng đời những registration mà nó thực sự tạo hoặc thay thế theo chính sách của nó. Nếu nó bỏ qua một tên đã có, registration đó thuộc về thành phần đăng ký ban đầu.

Mô hình:

\`\`\`text
Thời điểm T1:
  Context A / Exporter A
    register ObjectName X -> MBean A

Thời điểm T2:
  Context B / Exporter B (IGNORE_EXISTING)
    register ObjectName X -> phát hiện đã tồn tại
    bỏ qua đăng ký MBean B

Registry tại T2:
  X -> MBean A

Thời điểm T3:
  Context B đóng
    không có registration X mới của B để gỡ

Thời điểm T4:
  Context A đóng
    MBean A được unregister bởi owner A

Registry tại T4:
  X không còn, MBean B không tự xuất hiện
\`\`\`

Hệ quả vận hành là “khởi tạo context B thành công” không đồng nghĩa “JMX đã chuyển sang quản lý bean B”. Nếu một automation theo dõi JMX name X, nó có thể tiếp tục đọc MBean A cho đến khi A đóng, sau đó tên X biến mất.

Khi chọn IGNORE, phải trả lời rõ: MBean nào được phép giữ tên? Ai có trách nhiệm unregister? Có cần một bước đăng ký lại sau khi owner cũ dừng không?

## 9. Đọc MBean thực tế để tránh nhầm instance

Đừng chỉ kiểm tra \`server.isRegistered(name)\`. Lời gọi đó trả \`true\` dù exporter mới đã bỏ qua registration. Để biết đúng đối tượng đang được quản lý, công bố một attribute nhận diện instance hoặc đọc thông tin metadata thích hợp.

Ví dụ:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.jmx:type=CacheMonitor,name=primary");

if (server.isRegistered(name)) {
    Object instanceId = server.getAttribute(name, "InstanceId");
    System.out.println("Registry owner instance = " + instanceId);
}
\`\`\`

Đối chiếu \`InstanceId\` với danh tính logic mong đợi, chẳng hạn tên context, shard hoặc pool. Không dùng thông tin bí mật hoặc dữ liệu cá nhân để làm định danh hiển thị.

Có thể xem metadata:

\`\`\`java
var info = server.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.println(attribute.getName());
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Metadata giúp kiểm tra MBean hiện có có hợp đồng phù hợp hay không. Nhưng cùng class và interface vẫn chưa đủ chứng minh instance đúng. Khi cần phân biệt nhiều object cùng kiểu, attribute nhận diện logic và \`ObjectName\` ổn định rất hữu ích.

## 10. Cấu hình XML với registrationPolicy

Dự án Spring dùng XML có thể cấu hình registration policy trên bean exporter. Ví dụ:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="cacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="xml-context"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="registrationPolicy" value="IGNORE_EXISTING"/>

        <property name="beans">
            <map>
                <entry
                    key="com.example.jmx:type=CacheMonitor,name=primary"
                    value-ref="cacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
\`\`\`

Ví dụ không chỉ định \`server\`; exporter sử dụng cơ chế tìm \`MBeanServer\` trong Spring/runtime. Nếu muốn chắc chắn dùng một server cụ thể, khai báo bean \`MBeanServer\` và inject vào thuộc tính \`server\`.

Với cấu hình dùng enum \`RegistrationPolicy\`, Spring có thể chuyển chuỗi \`IGNORE_EXISTING\` sang enum khi bind property. Cần kiểm tra phiên bản Spring Framework hiện có và API thực tế khi triển khai.

## 11. IGNORE_EXISTING và MBeanExporterListener

\`MBeanExporter\` hỗ trợ các cơ chế callback/lifecycle liên quan registration. Nếu ứng dụng cần kiểm kê registration nào đã được tạo và tên nào bị bỏ qua, nên quan sát log và các callback phù hợp của exporter hoặc ghi trạng thái từ một thành phần orchestration riêng.

Tuy nhiên, đừng giả định một listener registration được gọi cho cả trường hợp **bỏ qua** nếu thực tế không có registration mới. Để xác minh kết quả cuối cùng, đọc \`MBeanServer\` sau khi exporter khởi tạo, rồi kiểm tra thông tin nhận diện của MBean đã tồn tại.

Nếu muốn cảnh báo khi xung đột bị bỏ qua, có thể thiết kế health check hoặc kiểm tra startup so sánh identity mong đợi với identity trong JMX. \`IGNORE_EXISTING\` chỉ là chính sách xử lý xung đột ở tầng registration, không phải hệ thống audit ownership.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Spring context khởi tạo thành công nhưng JMX hiển thị số liệu cũ | IGNORE giữ MBean có trước | Kiểm tra \`InstanceId\`, owner và \`ObjectName\` |
| \`isRegistered(name)=true\` nhưng không thấy bean mới | Tên đã tồn tại và exporter bỏ qua | Đọc attribute nhận diện; không dựa riêng vào \`isRegistered\` |
| MBean biến mất sau khi context cũ đóng | Context mới đã bỏ qua, không đăng ký lại | Thiết kế chuyển giao hoặc tên khác |
| Hai instance cần cùng được theo dõi | Đang dùng cùng \`ObjectName\` | Thêm \`name\`, \`pool\`, \`tenant\` hoặc key nhận diện khác |
| Không thấy lỗi trùng tên nên tưởng đã thay thế | IGNORE không báo lỗi đăng ký như FAIL | Kiểm tra registry và instance thực |
| Test suite bị nhiễm trạng thái | Các test dùng chung platform \`MBeanServer\` | Cô lập server hoặc dùng tên test riêng |
| Đổi policy nhưng chưa thấy khác biệt | Context cũ vẫn hoạt động, registration cũ còn tồn tại | Kiểm tra lifecycle và registry hiện tại |
| Client không thấy đúng operation | MBean cũ có contract khác | Đọc \`MBeanInfo\`, xác định owner |
| Có nhiều JVM cùng tên JMX | Uniqueness chỉ trong từng MBean server | Đối chiếu JVM/PID và endpoint kết nối |

Khi gặp sự cố, thứ tự điều tra phù hợp là: xác nhận đúng JVM/server, đọc full \`ObjectName\`, kiểm tra policy exporter, xác định registration đã có trước hay chưa, rồi đối chiếu instance thực tế.

## 13. Quy trình kiểm thử IGNORE_EXISTING

Trong bài test tích hợp, nên dùng một \`MBeanServer\` riêng để tránh đụng vào platform registry của các test khác:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test-jmx");

try {
    // 1. Đăng ký MBean A dưới ObjectName X.
    // 2. Tạo Spring context/exporter B dùng cùng testServer.
    // 3. Đặt RegistrationPolicy.IGNORE_EXISTING.
    // 4. Đảm bảo context B khởi tạo thành công.
    // 5. Đọc attribute nhận diện và xác minh registry vẫn trỏ tới A.
    // 6. Đóng context B, xác minh A vẫn đăng ký.
    // 7. Gỡ A trong cleanup được kiểm soát.
} finally {
    MBeanServerFactory.releaseMBeanServer(testServer);
}
\`\`\`

Các assertion quan trọng:

- Tên X đã được đăng ký trước khi exporter B chạy.
- Sau khi B khởi tạo, registry vẫn trả instance ID của A.
- Bean B vẫn tồn tại trong Spring \`ApplicationContext\`.
- Sau khi đóng B, registration A vẫn tồn tại.
- Sau khi owner A unregister, tên X không tự chuyển sang B.

Cấu hình fixture cần inject **chính \`testServer\`** vào exporter B. Nếu exporter B dùng platform server còn test kiểm tra \`testServer\`, kết quả sẽ không phản ánh policy đang thử.

### Kiểm tra sự khác biệt khi chưa có registration

Một test khác nên bắt đầu với server trống rồi khởi tạo exporter có \`IGNORE_EXISTING\`. Lúc này registry phải chứa MBean của exporter đó. Bài test giúp chứng minh “IGNORE_EXISTING chỉ bỏ qua tên đã có”, không làm exporter ngừng đăng ký mọi MBean.

## 14. Khi nào nên và không nên chọn IGNORE_EXISTING?

**Phù hợp khi:**

- Một MBean đã tồn tại được xem là nguồn quản trị hợp lệ và ưu tiên.
- Component mới chỉ cung cấp một registration dự phòng/tùy chọn.
- Mục tiêu là tránh trùng tên ở một điểm tích hợp đã được định nghĩa rõ ownership.
- Hợp đồng MBean của registration đang có được xác nhận phù hợp với client.

**Không phù hợp khi:**

- Hai instance cần được quản trị cùng lúc dưới hai danh tính khác nhau.
- Context mới phải thay thế context cũ trong một quy trình chuyển giao chính thức.
- Việc có MBean sai instance gây nguy cơ dashboard, automation hoặc operator đọc nhầm dữ liệu.
- Bạn cần phát hiện cấu hình trùng tên càng sớm càng tốt.
- Mục tiêu test là xác nhận bean mới đã được export nhưng policy có thể giữ một MBean từ test trước.

Trong các trường hợp đó, dùng \`FAIL_ON_EXISTING\`, tạo \`ObjectName\` duy nhất hoặc thiết kế quy trình thay thế/ownership rõ ràng tùy mục tiêu.

## 15. Bài tập thực hành

**Bài 1 — Hai exporters:** tạo hai \`MBeanExporter\` dùng chung server, cùng \`ObjectName\` nhưng khác \`CacheMonitor\` instance ID. Exporter A đăng ký trước; exporter B dùng \`IGNORE_EXISTING\`. Xác minh client vẫn đọc instance A.

**Bài 2 — So sánh policy:** chạy ba kịch bản độc lập với \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, \`REPLACE_EXISTING\`. Ghi nhận trạng thái registry, instance nhận lời gọi và kết quả startup.

**Bài 3 — Lifecycle:** đóng context B (đã ignore) rồi đóng context A. Kiểm tra tên JMX biến mất sau khi A unregister và B không tự thay thế.

**Bài 4 — Hai tên khác nhau:** sửa tên B thành \`com.example.jmx:type=CacheMonitor,name=secondary\`, giữ \`IGNORE_EXISTING\`. Xác nhận cả A và B cùng xuất hiện vì không còn xung đột tên.

**Bài 5 — Test Spring:** dùng JUnit Jupiter và \`AnnotationConfigApplicationContext\` với server test riêng. Assert bean B tồn tại trong context nhưng giá trị \`InstanceId\` qua JMX vẫn thuộc về A sau khi exporter B bỏ qua registration.

## Kết luận

\`RegistrationPolicy.IGNORE_EXISTING\` cho phép \`MBeanExporter\` tiếp tục khi một \`ObjectName\` đã được đăng ký, **giữ nguyên MBean đang tồn tại và bỏ qua bean mới tại tên đó**. Policy này hữu ích khi registration có trước được ưu tiên, nhưng không tạo thêm instance, không đồng bộ trạng thái và không tự chuyển ownership khi context cũ dừng. Khi triển khai Spring Framework JMX, hãy phân biệt thành công của \`ApplicationContext\` với việc MBean nào thực sự được công bố, đồng thời kiểm tra \`ObjectName\`, instance identity và vòng đời của từng exporter.
