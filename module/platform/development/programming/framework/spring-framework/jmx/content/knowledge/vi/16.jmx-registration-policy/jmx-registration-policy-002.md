# RegistrationPolicy.FAIL_ON_EXISTING trong Spring Framework JMX

## Mục tiêu

Sau bài học, bạn có thể giải thích chính xác ý nghĩa của `RegistrationPolicy.FAIL_ON_EXISTING` khi Spring xuất MBean qua JMX, biết khi nào nó được áp dụng, cách cấu hình trong `MBeanExporter`, cách phân biệt với `IGNORE_EXISTING` và `REPLACE_EXISTING`, và cách viết kiểm thử chứng minh trường hợp trùng `ObjectName` không âm thầm ghi đè MBean đã có.

Bài học nằm trong chủ đề **Spring Framework JMX → Registration policy**. Trọng tâm là chính sách đăng ký, không phải việc chọn interface hay thiết lập remote JMX connector.

## 1. Vấn đề: một ObjectName chỉ được đăng ký một lần trong MBeanServer

JMX định danh mỗi MBean bằng `javax.management.ObjectName`, ví dụ:

```text
com.example.payment:type=Queue,name=Primary
```

Trong **một `MBeanServer`**, không thể có hai MBean được đăng ký đồng thời dưới cùng một `ObjectName`.

Một ứng dụng Spring có thể xuất MBean theo nhiều cách: khai báo map `beans` trên `MBeanExporter`, bật annotation-driven export bằng `@EnableMBeanExport`, hoặc sử dụng `<context:mbean-export/>` trong XML. Nếu hai exporter cùng đăng ký một tên, hoặc một exporter cố đăng ký tên đã được component khác sử dụng, xung đột xuất hiện.

```text
MBeanServer
  |
  |-- com.example.payment:type=Queue,name=Primary
  |          ^
  |          | đã được đăng ký
  |
Exporter B
  |
  +-- cố đăng ký cùng ObjectName
             |
             v
      Chính sách registration quyết định cách xử lý
```

Trong JMX thuần Java, một lời gọi đăng ký trùng thông thường sinh `InstanceAlreadyExistsException`. Spring đưa ra `RegistrationPolicy` để người viết cấu hình chọn hành vi khi gặp trường hợp này.

## 2. FAIL_ON_EXISTING nghĩa là gì?

`org.springframework.jmx.support.RegistrationPolicy.FAIL_ON_EXISTING` có nghĩa:

> Khi Spring định đăng ký một MBean dưới `ObjectName` đã tồn tại trong `MBeanServer` đích, **không bỏ qua và không thay thế MBean cũ**; thay vào đó báo lỗi đăng ký.

Đây là hành vi **fail-fast**: xung đột được đưa ra rõ ràng tại thời điểm export thay vì lặng lẽ che giấu cấu hình trùng.

Ví dụ kỳ vọng:

```text
Tại thời điểm bắt đầu:
  MBeanServer có "com.example.payment:type=Queue,name=Primary"

Spring MBeanExporter:
  muốn đăng ký một bean khác với cùng tên
  registrationPolicy = FAIL_ON_EXISTING

Kết quả:
  Đăng ký thứ hai thất bại
  MBean đã tồn tại vẫn giữ nguyên
  Spring báo lỗi; quá trình khởi tạo context có thể thất bại
```

Lưu ý: `FAIL_ON_EXISTING` xử lý **trùng tên tại MBeanServer**. Nó không tự kiểm tra logic nghiệp vụ, quyền truy cập, chất lượng metadata hoặc tính duy nhất giữa các JVM khác nhau.

## 3. API và các lựa chọn chính sách

Enum `RegistrationPolicy` trong Spring JMX có ba lựa chọn thường gặp:

| Chính sách | Khi ObjectName đã tồn tại | Hậu quả chính |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Báo lỗi | Phát hiện xung đột ngay, không cố thay thế MBean hiện có |
| `IGNORE_EXISTING` | Bỏ qua đăng ký mới | MBean cũ tiếp tục phục vụ; bean mới có thể không được xuất |
| `REPLACE_EXISTING` | Thay thế MBean cũ theo cơ chế đăng ký của Spring | Cần hiểu ownership; có thể ảnh hưởng component khác |

Ví dụ cấu hình:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Đối với `MBeanExporter` thông thường, chính sách fail khi tên đã tồn tại là hành vi mặc định; việc khai báo tường minh giúp người bảo trì hiểu chủ đích và không bị bất ngờ khi các cấu hình khác thay đổi.

Không nên chọn `IGNORE_EXISTING` hay `REPLACE_EXISTING` chỉ để “làm ứng dụng khởi động được” trước khi xác định vì sao hai bên dùng chung ObjectName.

## 4. Ví dụ Standard MBean để thực hành

Tạo interface JMX theo quy ước Standard MBean:

```java
package com.example.payment.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
}
```

Implementation:

```java
package com.example.payment.jmx;

public final class PaymentQueueMonitor
        implements PaymentQueueMonitorMBean {

    private final int pendingCount;
    private final boolean paused;

    public PaymentQueueMonitor(int pendingCount, boolean paused) {
        this.pendingCount = pendingCount;
        this.paused = paused;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }
}
```

Một `PaymentQueueMonitor` hợp lệ có thể được đăng ký như Standard MBean dưới tên:

```text
com.example.payment:type=Queue,name=Primary
```

Nếu tạo một instance thứ hai và cố đăng ký dưới đúng tên trên, JMX server sẽ phát hiện trùng bất kể hai object có cùng class hay cùng giá trị attribute.

**Tính duy nhất phụ thuộc ObjectName, không phụ thuộc object identity hay class.**

## 5. Cấu hình MBeanExporter dùng FAIL_ON_EXISTING

Ví dụ Java configuration cho Spring Framework:

```java
package com.example.payment.config;

import com.example.payment.jmx.PaymentQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class PaymentJmxConfig {

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor(15, false);
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter paymentMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.payment:type=Queue,name=Primary",
            paymentQueueMonitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
```

Các phần quan trọng:

1. `setServer`: chọn MBeanServer cần đăng ký.
2. `setBeans`: chỉ định bean và tên JMX.
3. `setRegistrationPolicy`: xác định cách phản ứng khi tên đã tồn tại.
4. Khi ApplicationContext khởi tạo, `MBeanExporter` đăng ký MBean theo vòng đời Spring.
5. Nếu ObjectName đã tồn tại, lỗi có thể được Spring bọc trong ngoại lệ khởi tạo context; nguyên nhân gốc thường liên quan đến `InstanceAlreadyExistsException`.

Nếu ứng dụng đã có `MBeanServer` được cấu hình nơi khác, hãy dùng server đó thay vì tạo thêm một server tùy ý. Cũng không được mặc định mọi Spring bean có thể đăng ký như Standard MBean nếu không có interface hoặc assembler phù hợp.

## 6. Cấu hình XML

Với các ứng dụng Spring Framework dùng XML:

```xml
<bean id="paymentQueueMonitor"
      class="com.example.payment.jmx.PaymentQueueMonitor">
    <constructor-arg value="15"/>
    <constructor-arg value="false"/>
</bean>

<bean id="paymentExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.payment:type=Queue,name=Primary"
                   value-ref="paymentQueueMonitor"/>
        </map>
    </property>
    <property name="registrationPolicy" value="FAIL_ON_EXISTING"/>
</bean>
```

Thuộc tính `registrationPolicy` dùng enum Spring. Cần dùng XML schema/version Spring phù hợp với dự án; ví dụ trên mô tả cách cấu hình trực tiếp bean `MBeanExporter`.

Nếu ứng dụng dùng:

```xml
<context:mbean-export/>
```

thì đây là cơ chế annotation-driven export khác với việc cấu hình thủ công một exporter. Có thể có các lựa chọn chính sách đăng ký ở phần tử XML namespace tùy phiên bản schema; phải kiểm tra cách cấu hình thực tế và tránh khởi tạo nhiều exporter đăng ký cùng tên.

**Không bật hai đường export chỉ vì cả hai cùng có sẵn trong codebase.** Mỗi ObjectName nên có owner rõ ràng.

## 7. FAIL_ON_EXISTING khác gì với lỗi Java thông thường?

Java JMX định nghĩa quy tắc: một `ObjectName` đang được sử dụng không thể đăng ký thêm object thứ hai mà không có bước hủy đăng ký thích hợp. Với `MBeanServer.registerMBean`, dấu hiệu điển hình là:

```text
javax.management.InstanceAlreadyExistsException
```

Trong Spring, lỗi có thể được bọc qua `MBeanExportException`, `BeanCreationException` hoặc các lớp ngoại lệ khác tùy thời điểm khởi tạo và cách exporter được cấu hình.

Do đó khi phân tích log:

- Đọc **root cause** thay vì chỉ dòng ngoại lệ ngoài cùng.
- Tìm `ObjectName` cụ thể đang bị trùng.
- Xác định MBean nào đã đăng ký trước.
- Kiểm tra exporter nào đã thực hiện đăng ký lần thứ hai.
- Xem lifecycle: bean cũ có còn tồn tại do context cũ chưa đóng không?

Một lỗi do trùng ObjectName khác với `MalformedObjectNameException` (chuỗi tên sai cú pháp) hay `NotCompliantMBeanException` (object không phải MBean hợp lệ).

## 8. Kiểm thử trùng tên bằng MBeanServer thuần Java

Trước khi kiểm tra Spring policy, có thể kiểm chứng hành vi nền tảng JMX với MBeanServer riêng:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class DuplicateObjectNameTest {

    @Test
    void rejectsSecondRegistration() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try {
            server.registerMBean(
                new PaymentQueueMonitor(10, false), name
            );

            assertTrue(server.isRegistered(name));

            assertThrows(
                InstanceAlreadyExistsException.class,
                () -> server.registerMBean(
                    new PaymentQueueMonitor(99, true), name
                )
            );

            // Đăng ký trùng không thay thế giá trị MBean ban đầu.
            assertEquals(
                10,
                server.getAttribute(name, "PendingCount")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Test này xác minh luật JMX cốt lõi: tên đã tồn tại khiến lần đăng ký mới thất bại và object cũ không bị thay thế.

Tuy nhiên, **đây chưa phải integration test của chính sách Spring**. Muốn chứng minh `RegistrationPolicy.FAIL_ON_EXISTING`, phải chạy một `MBeanExporter` của Spring với policy đó khi server đã có MBean cùng tên.

## 9. Integration test chứng minh FAIL_ON_EXISTING

Sử dụng server test riêng và đăng ký trước một MBean. Sau đó tạo Spring context có exporter cố đăng ký MBean thứ hai cùng tên.

Một mẫu test mang tính minh họa:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

class FailOnExistingExporterTest {
    @Test
    void rejectsNameOwnedByAnotherComponent() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");
        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try {
            // Component A đăng ký trước.
            server.registerMBean(
                new PaymentQueueMonitor(10, false), name
            );

            GenericApplicationContext context =
                    new GenericApplicationContext();

            context.registerBean("exporter", MBeanExporter.class, () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(
                    RegistrationPolicy.FAIL_ON_EXISTING
                );
                exporter.setBeans(Map.of(
                    name.toString(),
                    new PaymentQueueMonitor(99, true)
                ));
                return exporter;
            });

            try {
                // Lỗi xung đột phát sinh trong quá trình refresh/export.
                assertThrows(
                    RuntimeException.class,
                    context::refresh
                );

                // Object đăng ký đầu vẫn là owner của tên.
                assertTrue(server.isRegistered(name));
                assertEquals(
                    10,
                    server.getAttribute(name, "PendingCount")
                );
            } finally {
                context.close();
            }
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Trong dự án thực tế, nên kiểm tra root cause của exception để xác nhận lỗi là do trùng tên, không phải lỗi unrelated trong `ApplicationContext`. Kiểm thử không nên dựa vào message chính xác vì wrapper exception và wording có thể thay đổi theo phiên bản Spring.

Ngoài ra, test trên dùng `MBeanServer` riêng để không tác động vào MBean hệ thống hoặc các test khác trong cùng JVM.

## 10. Khi nào nên chọn FAIL_ON_EXISTING?

**Phù hợp khi:**

1. Mỗi JMX ObjectName có một chủ sở hữu rõ.
2. Trùng tên là dấu hiệu cấu hình sai cần sửa ngay.
3. Bạn muốn tránh việc một exporter vô tình chiếm quyền quản lý MBean của component khác.
4. Monitoring phụ thuộc vào hợp đồng ObjectName ổn định và không chấp nhận âm thầm giữ nhầm object.
5. Hệ thống khởi tạo theo quy trình có thể phát hiện và xử lý lỗi cấu hình trước khi phục vụ lưu lượng.

Ví dụ service `PaymentService` có đúng một MBean `type=Queue,name=Primary` trong JVM. Nếu tồn tại hai exporter xuất cùng tên, đó thường là lỗi wiring. Fail-fast giúp phát hiện vấn đề.

**Cân nhắc kỹ khi:**

- Nhiều application context chia sẻ platform MBeanServer một cách có chủ đích.
- Ứng dụng redeploy trong một JVM nhưng context cũ chưa teardown.
- Có framework/instrumentation khác đã sở hữu tên và bạn chỉ muốn dùng lại dữ liệu của nó.
- Bạn cần hot-swap một MBean và có cơ chế ownership/chuyển giao được thiết kế rõ.

Trong các tình huống đó, cần phân tích vòng đời và quyền sở hữu trước khi chọn ignore/replace.

## 11. Phân biệt IGNORE_EXISTING và REPLACE_EXISTING

### IGNORE_EXISTING

Nếu server đã có:

```text
com.example.payment:type=Queue,name=Primary -> monitor A
```

và exporter muốn đăng ký monitor B cùng tên, `IGNORE_EXISTING` bỏ qua việc đăng ký B. JMX client vẫn thấy A.

Rủi ro: ứng dụng có thể khởi động mà người vận hành tưởng mình đang đọc B. Nếu MBean A thuộc context cũ, dữ liệu có thể stale hoặc không phản ánh trạng thái ứng dụng hiện tại.

### REPLACE_EXISTING

Exporter cố thay MBean hiện có bằng MBean mới. Điều này có thể phù hợp khi một thành phần thật sự quản lý lifecycle thay thế, nhưng có rủi ro:

- MBean cũ có thể thuộc subsystem khác.
- Listener của client có thể chịu ảnh hưởng bởi unregister/register.
- Trong thời gian thay thế, client có thể gặp gián đoạn.
- Khi context mới đóng, cần hiểu MBean nào sẽ được unregister.

`FAIL_ON_EXISTING` tránh các hành vi này bằng cách báo xung đột và để người quản trị quyết định đường sửa thực sự.

## 12. Nguyên nhân gây xung đột phổ biến trong Spring

### Hai MBeanExporter độc lập

Một config Java khai báo `MBeanExporter` thủ công, trong khi cấu hình annotation bật thêm exporter khác. Nếu cùng xuất một bean dưới cùng ObjectName, khả năng trùng cao.

### Parent/child ApplicationContext

Trong ứng dụng web hoặc modular application, parent và child context có thể cùng sử dụng platform MBeanServer. Nếu cả hai export cùng tên, xung đột phát sinh dù bean có thể thuộc các context khác nhau.

### Duplicate explicit mapping

Hai module cùng dùng:

```text
com.example.payment:type=Queue,name=Primary
```

vì copy cấu hình hoặc thiếu naming convention. Cần chỉnh tên logic hoặc chọn một owner.

### Tên thay đổi/không chuẩn hóa

Các chuỗi:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:name=Primary,type=Queue
```

là cùng ObjectName dù thứ tự key khác nhau. Vì vậy, một kiểm tra string đơn giản có thể bỏ sót xung đột; nên dùng `ObjectName.equals()` hoặc `getCanonicalName()`.

### Context cũ chưa unregister

Một context không được đóng đúng cách có thể để lại MBean. Khi context mới đăng ký lại tên, `FAIL_ON_EXISTING` sẽ phát hiện. Sửa lifecycle/cleanup thay vì nối UUID ngẫu nhiên vào ObjectName.

## 13. Chẩn đoán xung đột bằng MBeanServer

Nếu log báo trùng, kiểm tra tên đã được đăng ký:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("MBean class: " + info.getClassName());
    System.out.println("ObjectName: " + name.getCanonicalName());
}
```

Lưu ý `MBeanInfo.getClassName()` cho biết class/metadata mà JMX công bố, **không phải bằng chứng đầy đủ về Spring ApplicationContext hoặc exporter nào đã đăng ký**. Để xác định owner, cần kết hợp log startup, bean definitions, naming configuration và lifecycle của từng module.

Nếu exporter dùng MBeanServer tùy chỉnh, phải truy vấn đúng server thay vì mặc định platform server.

## 14. Kiểm tra vòng đời unregister

Một exporter sở hữu MBean thường sẽ unregister các MBean do nó quản lý khi ApplicationContext đóng bình thường.

Trong test:

```java
ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

try (var context = new AnnotationConfigApplicationContext(
        PaymentJmxConfig.class)) {
    assertTrue(
        ManagementFactory.getPlatformMBeanServer()
            .isRegistered(name)
    );
}

assertFalse(
    ManagementFactory.getPlatformMBeanServer()
        .isRegistered(name)
);
```

Đây là mẫu ý tưởng: test phải chạy trong môi trường không có owner khác đang dùng tên. Nếu test dùng một platform MBeanServer chung, không tự unregister MBean mà ứng dụng khác sở hữu.

Với `FAIL_ON_EXISTING`, đăng ký của exporter mới **không thành công** nếu tên đã tồn tại, nên nó không nên coi MBean cũ là đối tượng do nó sở hữu. Việc cleanup cần tuân theo owner thực tế, không được tự xóa MBean của component khác để test tiếp tục.

## 15. Quy tắc đặt tên giúp tránh FAIL_ON_EXISTING

ObjectName nên vừa duy nhất vừa có nghĩa:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
com.example.payment:type=WorkerPool,name=Retry
```

Thiết kế key property theo tài nguyên:

- `domain`: namespace module/service.
- `type`: loại thành phần, ví dụ `Queue`, `Cache`, `WorkerPool`.
- `name`: tên logic của instance/tài nguyên trong JVM.
- `component`, `tenant` hoặc `region`: chỉ thêm khi cần phân biệt hợp lệ.

Không cần đưa PID hoặc UUID mỗi lần restart vào ObjectName nếu resource logic không đổi. Sự ổn định giúp script vận hành và dashboard tìm đúng MBean.

Nếu nhiều replica chạy trên JVM riêng, chúng **có thể dùng cùng ObjectName** vì mỗi JVM có MBeanServer riêng. Xung đột mà `FAIL_ON_EXISTING` kiểm soát chỉ diễn ra trong server đích của lần đăng ký.

## 16. Cấu hình xử lý xung đột trong môi trường production

Một quy trình xử lý an toàn:

1. Ghi lại ObjectName và MBeanServer đích từ lỗi.
2. Xác định component đăng ký trước và exporter đang bị lỗi.
3. Kiểm tra xem hai đăng ký có đại diện cho **cùng tài nguyên** hay **hai tài nguyên khác nhau**.
4. Nếu cùng tài nguyên: giữ một exporter/owner, loại đường đăng ký trùng.
5. Nếu khác tài nguyên: chọn ObjectName khác nhau theo quy ước logic.
6. Nếu context cũ còn sống: sửa teardown/lifecycle, không xóa MBean tùy tiện.
7. Nếu cần replace có chủ đích: thiết kế lại ownership và quy trình chuyển giao, cân nhắc `REPLACE_EXISTING`.
8. Xác minh lại `isRegistered`, `getMBeanInfo` và attribute từ JMX client sau thay đổi.

Không dùng `server.unregisterMBean(name)` trong application startup như một “cách giải quyết chung” cho lỗi trùng tên: lệnh này có thể xóa MBean đang phục vụ client của module khác.

## 17. Bài tập thực hành

1. Tạo `PaymentQueueMonitorMBean` và hai instance với các giá trị `PendingCount` khác nhau. Đăng ký dưới cùng ObjectName vào một MBeanServer riêng, kiểm tra exception.
2. Cấu hình Spring `MBeanExporter` với `FAIL_ON_EXISTING`, tạo trước MBean cùng tên trong server rồi xác nhận context mới không export được.
3. Thử `IGNORE_EXISTING` trong môi trường test và so sánh attribute mà client nhìn thấy.
4. Thử `REPLACE_EXISTING` trong môi trường test để thấy tác động đến object đã đăng ký; không dùng trên server chia sẻ nếu không có quyền sở hữu.
5. Tạo hai ObjectName chỉ khác thứ tự key property. So sánh `equals()` và quan sát xung đột đăng ký.
6. Chia cấu hình thành hai Spring context dùng cùng platform server và tên cố định. Chẩn đoán exporter nào gây xung đột.
7. Viết integration test kiểm tra thông báo lỗi do trùng `ObjectName` và khẳng định MBean cũ không bị thay thế.

## 18. Câu hỏi tự kiểm tra

- `FAIL_ON_EXISTING` thực hiện điều gì khi ObjectName đã tồn tại?
- Chính sách này khác `IGNORE_EXISTING` và `REPLACE_EXISTING` ra sao?
- Trong JMX, ObjectName có duy nhất trên toàn bộ cluster hay trong mỗi MBeanServer?
- Vì sao `MBeanInfo.getClassName()` không đủ để xác định chính xác exporter sở hữu MBean?
- Khi hai bean thực sự là hai tài nguyên khác nhau, nên sửa naming strategy thế nào?
- Vì sao không nên thêm UUID ngẫu nhiên chỉ để né lỗi trùng tên?
- Điều gì cần kiểm tra nếu ứng dụng có cả `@EnableMBeanExport` và `MBeanExporter` khai báo thủ công?
- Làm sao chứng minh policy không thay thế MBean cũ trong integration test?

**Ghi nhớ:** `RegistrationPolicy.FAIL_ON_EXISTING` bảo vệ tính rõ ràng của đăng ký MBean: **đã có ObjectName thì đăng ký mới thất bại**, thay vì bị bỏ qua hoặc thay thế âm thầm. Đây thường là lựa chọn an toàn khi trùng tên biểu hiện lỗi cấu hình. Hãy quản lý ObjectName ổn định, xác định owner của mỗi MBean và kiểm thử hành vi xung đột trên một MBeanServer được cách ly.