# Giữ cấu hình quản trị tách khỏi nghiệp vụ trong Spring Framework JMX

## Mục tiêu học tập

Trong Spring Framework JMX, một ứng dụng có thể xuất trạng thái và thao tác quản trị thông qua `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` và `MBeanServer`. Tuy nhiên, nếu trộn trực tiếp cấu hình JMX, tên ObjectName, giao thức quản trị và logic nghiệp vụ trong cùng một class, hệ thống trở nên khó kiểm thử, khó tái sử dụng và dễ vô tình công bố các thao tác nhạy cảm.

Sau bài này, bạn có thể:

- Giải thích vì sao nên tách **business logic**, **management API**, **JMX adapter** và **Spring configuration**.
- Thiết kế một kiến trúc trong đó nghiệp vụ không cần biết JMX.
- Dùng Java `@Configuration`, `@Bean`, `MBeanExporter` và `ObjectName` để export adapter quản trị.
- Phân biệt cách dùng annotation trên domain bean với cách export một adapter riêng.
- Kiểm tra hiệu lực Spring AOP proxy, transaction, security và lifecycle.
- Viết unit test cho nghiệp vụ độc lập với JMX, integration test cho wiring quản trị.
- Nhận biết ranh giới truy cập và tác động vận hành của các operation được xuất.

## 1. Vấn đề khi gắn quản trị trực tiếp vào mã nghiệp vụ

Một class Spring có thể được viết như sau:

```java
@Service
@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main"
)
public class OrderProcessor {

    @ManagedAttribute
    public int getQueueDepth() {
        return 15;
    }

    @ManagedOperation
    public void retryFailedOrders() {
        // logic nghiệp vụ xử lý lại đơn hàng
    }

    public void placeOrder(Order order) {
        // logic nghiệp vụ
    }
}
```

Thiết kế này có thể phù hợp với ví dụ nhỏ, nhưng phát sinh vấn đề trong hệ thống lớn:

1. **Phụ thuộc kỹ thuật:** `OrderProcessor` phụ thuộc Spring JMX annotation dù bản chất nhiệm vụ là xử lý đơn hàng.
2. **Thay đổi bị liên kết:** thay ObjectName hay cấu trúc MBean có thể buộc sửa class nghiệp vụ.
3. **Bề mặt công bố dễ lan rộng:** một developer có thể vô tình đưa operation quá mạnh vào JMX.
4. **Khó tách quyền:** thao tác JMX và API nghiệp vụ thường có mô hình authorization khác nhau.
5. **Khó kiểm thử:** unit test logic thuần nghiệp vụ bị kéo theo metadata quản trị; integration test khó phân biệt lỗi business logic với lỗi JMX wiring.
6. **Proxy/AOP:** exporter có thể nhận target hoặc proxy không như dự định; nếu không kiểm soát đường gọi, các transaction/security advice có thể bị bỏ qua.
7. **Khó chuyển đổi giao thức:** nếu sau này thay JMX bằng REST management endpoint, class nghiệp vụ vẫn phải được sửa.

Điểm cần hướng đến không phải “cấm annotation”, mà là **mỗi lớp có một trách nhiệm rõ ràng**.

## 2. Nguyên tắc phân tách bốn tầng

Một kiến trúc thực tế:

```text
                    JConsole / JMC / Monitoring
                               |
                               v
                         MBeanServer
                               |
                               v
                       JMX Management Adapter
                        (API quản trị hẹp)
                               |
                               v
                      Business Service Interface
                               |
                               v
                        Spring Service Proxy
                    (transactions, security, AOP)
                               |
                               v
                         Business Logic

Spring @Configuration:
  - tạo / inject các bean
  - cấu hình ObjectName
  - cấu hình MBeanExporter
  - chọn MBeanServer
  - cấu hình registration policy
```

Phân vai:

| Lớp | Nhiệm vụ | Không nên chứa |
| --- | --- | --- |
| Business service | Nghiệp vụ, tính nhất quán dữ liệu, validation | ObjectName, JMX connection, metadata exporter |
| Business interface | Hợp đồng nghiệp vụ cần thiết | Tham số đặc thù của JConsole/JMC |
| Management adapter | Chuyển câu lệnh quản trị thành lời gọi nghiệp vụ, giới hạn quyền/tác động | Thuật toán lõi hoặc truy vấn database phức tạp không cần thiết |
| Spring JMX configuration | Wiring exporter, ObjectName, naming strategy, MBeanServer, policy | Business rules |

**Quy tắc:** nghiệp vụ có thể chạy khi JMX bị tắt; JMX là một cách quan sát/điều khiển nghiệp vụ, không phải nền tảng bắt buộc để nghiệp vụ hoạt động.

## 3. Business service không phụ thuộc JMX

Đầu tiên định nghĩa một interface nghiệp vụ:

```java
package com.example.orders.application;

public interface OrderProcessingService {
    int pendingOrderCount();
    boolean isIntakePaused();
    void pauseIntake();
    void resumeIntake();
}
```

Implementation:

```java
package com.example.orders.application;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    private final AtomicInteger pending = new AtomicInteger(18);
    private final AtomicBoolean paused = new AtomicBoolean(false);

    @Override
    public int pendingOrderCount() {
        return pending.get();
    }

    @Override
    public boolean isIntakePaused() {
        return paused.get();
    }

    @Override
    public void pauseIntake() {
        paused.set(true);
    }

    @Override
    public void resumeIntake() {
        paused.set(false);
    }
}
```

Ví dụ này chỉ mô phỏng trạng thái thread-safe; trong ứng dụng production, service có thể gọi repository, queue broker hoặc state manager.

Điểm đáng chú ý là **không import bất kỳ class nào từ `org.springframework.jmx` hay `javax.management`**. Service có thể được test bằng JUnit thuần, sử dụng qua REST/message listener hoặc tái sử dụng trong một module khác.

## 4. Management interface chuyên biệt

Định nghĩa một Standard MBean interface chỉ chứa các khả năng cho phép công bố:

```java
package com.example.orders.management;

public interface OrderProcessingAdminMBean {
    int getPendingOrderCount();
    boolean isIntakePaused();
    void pauseIntake();
    void resumeIntake();
}
```

Interface này khác với `OrderProcessingService`:

- `getPendingOrderCount()` theo quy ước Standard MBean xuất thành attribute `PendingOrderCount`.
- `isIntakePaused()` xuất thành boolean attribute `IntakePaused`.
- `pauseIntake()` và `resumeIntake()` được công bố là operations.
- Không chứa `submitOrder`, `refundOrder`, `deleteOrder` hoặc phương thức nhạy cảm không cần cho vận hành.

Hợp đồng quản trị là một API riêng. Khi MBean client cần thêm thông tin, cân nhắc mở rộng management interface và mô tả tác động, thay vì xuất toàn bộ public methods của service.

## 5. Tạo adapter quản trị

Adapter nhận **business service interface** qua constructor:

```java
package com.example.orders.management;

import com.example.orders.application.OrderProcessingService;

public final class OrderProcessingAdmin
        implements OrderProcessingAdminMBean {

    private final OrderProcessingService service;

    public OrderProcessingAdmin(OrderProcessingService service) {
        this.service = service;
    }

    @Override
    public int getPendingOrderCount() {
        return service.pendingOrderCount();
    }

    @Override
    public boolean isIntakePaused() {
        return service.isIntakePaused();
    }

    @Override
    public void pauseIntake() {
        service.pauseIntake();
    }

    @Override
    public void resumeIntake() {
        service.resumeIntake();
    }
}
```

Adapter không tự làm nghiệp vụ. Nó:

- Biến business method thành tên/kiểu phù hợp JMX.
- Chọn chính xác các operations được công bố.
- Có thể bổ sung mô tả metadata, input validation, rate limiting hoặc kiểm soát tác động nếu thật sự cần.
- Gọi qua **Spring service bean** được inject, do đó có thể giữ đường gọi thông qua transaction/security proxy.

Lưu ý rằng **interface JMX không tạo ra quyền truy cập**. Nếu client có quyền invoke MBean operation, adapter phải dựa vào chính sách quyền của JMX connector và business service hoặc thêm ranh giới authorization rõ ràng.

## 6. Đặt cấu hình JMX trong class @Configuration riêng

Tạo `OrderJmxConfiguration`:

```java
package com.example.orders.config;

import com.example.orders.application.OrderProcessingService;
import com.example.orders.management.OrderProcessingAdmin;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class OrderJmxConfiguration {

    @Bean
    public OrderProcessingAdmin orderProcessingAdmin(
            OrderProcessingService service) {
        return new OrderProcessingAdmin(service);
    }

    @Bean
    public MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter orderMBeanExporter(
            OrderProcessingAdmin admin,
            MBeanServer applicationMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(applicationMBeanServer);

        exporter.setBeans(Map.of(
            "com.example.orders:type=Processor,name=Main",
            admin
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
```

Mỗi phần rõ trách nhiệm:

1. Service được quản lý bởi Spring thông qua `@Service`.
2. Adapter được tạo từ service interface.
3. Exporter đăng ký **adapter**, không xuất trực tiếp business service.
4. ObjectName nằm ở một lớp cấu hình chuyên trách.
5. Registration policy cho phép phát hiện lỗi tên trùng một cách tường minh.
6. Khi application context đóng bình thường, exporter quản lý hủy đăng ký các MBean do mình sở hữu.

Trong dự án thực, có thể inject một `MBeanServer` đã tồn tại và dùng `@Qualifier` để tránh nhầm nếu có nhiều server beans.

## 7. Vị trí của @ManagedResource trong kiến trúc tách lớp

Nếu cần metadata mô tả nhiều hơn Standard MBean, bạn có thể dùng Spring annotation **trên adapter quản trị**:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main",
    description = "Observes the local order processor and controls intake"
)
public class AnnotatedOrderAdmin {

    private final OrderProcessingService service;

    public AnnotatedOrderAdmin(OrderProcessingService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of pending orders in this JVM")
    public int getPendingOrderCount() {
        return service.pendingOrderCount();
    }

    @ManagedOperation(
        description = "Stops accepting new orders on this processor"
    )
    public void pauseIntake() {
        service.pauseIntake();
    }
}
```

Khi chọn cách annotation-driven, bật `@EnableMBeanExport` hoặc `<context:mbean-export/>` và đảm bảo đúng metadata assembler/exporter. **Không đồng thời tự động export và explicit map cùng một adapter dưới một ObjectName** nếu không có chiến lược đăng ký chủ đích.

Cách tiếp cận vẫn giữ nguyên nguyên tắc: annotation JMX nằm ở **management adapter**; business service không phải biết về JMX.

## 8. So sánh hai thiết kế

### A. Đưa annotation trực tiếp vào service

```text
OrderProcessingService
  @Service
  @ManagedResource
  @ManagedOperation
  business logic + JMX metadata
```

Ưu điểm: ít class, nhanh cho demo, thuận tiện khi component rất nhỏ.

Nhược điểm: service mang phụ thuộc quản trị; dễ mở rộng bề mặt MBean thiếu kiểm soát; thay đổi interface quản trị có thể chạm logic nghiệp vụ.

### B. Tách adapter và cấu hình

```text
OrderProcessingService
  business logic
        ^
        |
OrderProcessingAdmin
  management interface
        ^
        |
OrderJmxConfiguration
  ObjectName + MBeanExporter + MBeanServer
```

Ưu điểm: hợp đồng JMX hẹp, kiểm thử từng lớp dễ, đổi naming/exporter ít ảnh hưởng business code, AOP proxy rõ ràng hơn.

Nhược điểm: thêm adapter/configuration class và cần quản lý mapping giữa hai interface.

Với ứng dụng vận hành lâu dài, đặc biệt có operations tác động nghiệp vụ, **thiết kế tách lớp thường dễ duy trì và kiểm soát hơn**.

## 9. Tránh trộn bean name với ObjectName

Tên Spring bean và tên JMX không nhất thiết giống nhau.

```text
Spring bean name:
  orderProcessingAdmin

JMX ObjectName:
  com.example.orders:type=Processor,name=Main
```

Spring bean name dùng để inject và quản lý object trong container. ObjectName dùng để JMX client nhận diện MBean trong `MBeanServer`.

Nếu đổi `orderProcessingAdmin` thành `ordersManagementAdapter`, bạn có thể giữ nguyên ObjectName. Nhờ đó dashboard và runbook không cần đổi theo refactor nội bộ.

Domain `com.example.orders`, `type=Processor`, `name=Main` nên là một quy ước quản trị **ổn định**. Không dùng ID ngẫu nhiên sinh mỗi lần start chỉ để tránh xung đột do exporter bị cấu hình trùng.

## 10. Tách MBeanServer và remote connector khỏi nghiệp vụ

`MBeanServer` không phải trách nhiệm của `OrderProcessingService`. Một ứng dụng có thể dùng platform server:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

hoặc một server tùy biến. Tuy nhiên, việc chọn server thuộc lớp configuration/infrastructure.

Tương tự, remote JMX connector, authentication, TLS, RMI port, hostname và firewall là vấn đề deployment/operations. Không đặt các tham số này trong business service:

```java
// Không nên trong nghiệp vụ:
System.setProperty(
    "com.sun.management.jmxremote.port",
    "9010"
);
```

Cấu hình remote connector nên được quản lý ở JVM startup hoặc hạ tầng chuyên trách, với bảo mật rõ ràng và không hardcode credentials trong source code.

Một MBean được export thành công **không đồng nghĩa** remote client đã kết nối được. Hai lớp cần được test riêng.

## 11. Phân tách cấu hình theo profile và environment

Không phải mọi môi trường đều cần cùng bề mặt quản trị.

Ví dụ bật JMX management configuration có điều kiện:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("management-jmx")
public class OrderJmxConfiguration {
    // Các @Bean MBeanServer / adapter / exporter...
}
```

Sau đó chỉ kích hoạt profile `management-jmx` ở môi trường đã được phê duyệt.

Phân tách không chỉ giúp giảm bề mặt vận hành mà còn giữ business service hoạt động độc lập nếu cấu hình quản trị bị tắt.

Một số tình huống cần cân nhắc:

- Local development bật JMX để debug.
- Test unit không bật JMX để chạy nhanh.
- Integration test dùng MBeanServer test riêng.
- Production chỉ bật JMX qua endpoint được bảo vệ, có chính sách truy cập cụ thể.

**Lưu ý:** `@Profile` điều khiển việc đăng ký configuration bean, không tự cấu hình authentication hoặc TLS. Nếu JMX remote endpoint mở ra ngoài, phải đảm bảo chính sách bảo mật độc lập.

## 12. Quản lý quyền với management operations

Operation như `pauseIntake`, `resumeIntake`, `clearCache`, `rebuildIndex` có thể gây side effect. Tách adapter giúp đặt một ranh giới rõ, nhưng không thay thế authorization.

Các câu hỏi cần trả lời trước khi export:

- Client nào được kết nối tới MBeanServer?
- Client chỉ đọc attribute hay được invoke operation?
- Operation tác động một JVM, một instance service hay toàn cluster?
- Có audit việc gọi action quan trọng không?
- Nếu một operation bị gọi lặp, có gây sai dữ liệu không?
- Có validation cho tham số và giới hạn công việc không?
- Có cần phê duyệt hoặc một API khác thay JMX cho action nguy hiểm không?

Ví dụ adapter kiểm tra giới hạn:

```java
public int retryFailed(int maxCount) {
    if (maxCount < 1 || maxCount > 100) {
        throw new IllegalArgumentException(
            "maxCount must be between 1 and 100"
        );
    }
    return service.retryFailed(maxCount);
}
```

Ở đây, business interface phải cung cấp `retryFailed(int)` nếu adapter muốn gọi; ví dụ là một mở rộng có chủ đích của hợp đồng nghiệp vụ.

Đối với các thao tác nhạy cảm, đừng nghĩ rằng một `@ManagedOperation(description = "...")` tạo ra quyền. Metadata chỉ mô tả, không cấp hoặc từ chối quyền.

## 13. Spring AOP proxy và vì sao adapter có lợi

Nghiệp vụ thường có Spring AOP advice:

```java
@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    @Transactional
    public void performBusinessAction() {
        // ...
    }
}
```

Nếu exporter nhận target object thay vì Spring proxy, lời gọi từ JMX có nguy cơ bỏ qua transaction/security advice.

Với kiến trúc tách lớp:

```text
JMX
 -> OrderProcessingAdmin
 -> OrderProcessingService bean (Spring proxy)
 -> DefaultOrderProcessingService target
```

Adapter gọi qua interface được inject. Nếu interface thực sự do Spring proxy triển khai và advice đã được áp dụng, giao dịch/bảo mật có thể tiếp tục hoạt động theo đường gọi thông thường.

Cần nhớ giới hạn của Spring AOP: **self-invocation** bên trong target thường không đi qua proxy. Nếu adapter gọi `service.pauseIntake()`, nhưng `pauseIntake()` lại tự gọi một method khác cùng object có `@Transactional`, advice ở method nội bộ đó có thể không được áp dụng theo proxy-based AOP.

Vì vậy, thiết kế service/proxy cần được xem xét độc lập; adapter chỉ giúp đường gọi rõ hơn, không “sửa” tự động mọi giới hạn AOP.

## 14. Unit test nghiệp vụ không cần JMX

Một ưu điểm lớn của tách lớp là business service có thể test riêng:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DefaultOrderProcessingServiceTest {

    @Test
    void pausesAndResumesIntake() {
        OrderProcessingService service =
            new DefaultOrderProcessingService();

        assertFalse(service.isIntakePaused());

        service.pauseIntake();
        assertTrue(service.isIntakePaused());

        service.resumeIntake();
        assertFalse(service.isIntakePaused());
    }
}
```

Test này:

- Không cần `MBeanServer`.
- Không phụ thuộc `ObjectName`.
- Không mở connector hay JVM management agent.
- Chạy nhanh và chỉ xác minh business behavior.

Nếu unit test nghiệp vụ bắt buộc khởi tạo JMX exporter, đó có thể là dấu hiệu logic và infrastructure chưa được tách đúng.

## 15. Unit test adapter bằng fake service

Adapter cũng có thể test mà không khởi tạo JMX:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderProcessingAdminTest {

    @Test
    void delegatesPauseAndResume() {
        OrderProcessingService fake = new OrderProcessingService() {
            private boolean paused;

            @Override
            public int pendingOrderCount() {
                return 3;
            }

            @Override
            public boolean isIntakePaused() {
                return paused;
            }

            @Override
            public void pauseIntake() {
                paused = true;
            }

            @Override
            public void resumeIntake() {
                paused = false;
            }
        };

        OrderProcessingAdmin adapter = new OrderProcessingAdmin(fake);

        assertEquals(3, adapter.getPendingOrderCount());

        adapter.pauseIntake();
        assertTrue(adapter.isIntakePaused());

        adapter.resumeIntake();
        assertFalse(adapter.isIntakePaused());
    }
}
```

Test chứng minh adapter ủy quyền đúng service interface. Tuy nhiên, nó **chưa** chứng minh các method thực sự được MBeanServer công bố. Việc đó thuộc integration test sau.

## 16. Integration test exporter với MBeanServer thật

Có thể tạo một test `MBeanServer` cách ly:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("test.management");
```

Ví dụ JUnit 5 không cần remote connector:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.MBeanExporter;

class OrderJmxExporterTest {

    @Test
    void exportsOnlyManagementInterface() throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("test.management");

        OrderProcessingService service =
            new DefaultOrderProcessingService();
        OrderProcessingAdmin adapter =
            new OrderProcessingAdmin(service);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(java.util.Map.of(
            "com.example.orders:type=Processor,name=Main",
            adapter
        ));

        exporter.afterPropertiesSet();
        exporter.afterSingletonsInstantiated();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Processor,name=Main"
        );

        try {
            assertTrue(server.isRegistered(name));

            assertEquals(
                18,
                server.getAttribute(name, "PendingOrderCount")
            );

            server.invoke(
                name, "pauseIntake",
                new Object[0], new String[0]
            );

            assertTrue(adapter.isIntakePaused());
        } finally {
            exporter.destroy();
        }

        assertFalse(server.isRegistered(name));
    }
}
```

Ví dụ này thể hiện ý tưởng kiểm tra MBean được export và không đưa service public API khác vào JMX. Với việc tự quản lý lifecycle exporter, cần tuân theo interface Spring và phiên bản cụ thể; trong project thực tế có thể đơn giản hơn bằng cách tạo `AnnotationConfigApplicationContext` với cấu hình test và đóng context sau test.

`MBeanInfo` cho biết chính xác operation/attribute được công bố:

```java
var info = server.getMBeanInfo(name);

for (var op : info.getOperations()) {
    System.out.println(op.getName());
}
```

Đối với cấu hình dùng Standard MBean adapter, kiểm thử nên xác minh chỉ những operation được định nghĩa trong `OrderProcessingAdminMBean` xuất hiện.

## 17. Không để lỗi JMX ngăn nghiệp vụ một cách khó hiểu

Một nguyên tắc kiến trúc là business service độc lập về mặt source code và dependency. Tuy nhiên, nếu `MBeanExporter` là Spring bean khởi tạo trong cùng ApplicationContext, lỗi như `InstanceAlreadyExistsException` vẫn có thể khiến toàn bộ context startup thất bại theo chính sách đăng ký.

Vì vậy có **hai cấp độc lập**:

1. **Độc lập mã nguồn:** business service không biết JMX và vẫn có thể dùng khi không bật JMX.
2. **Độc lập runtime:** việc không thể đăng ký JMX có làm ứng dụng thất bại hay không tùy chính sách cấu hình và deployment.

Đừng nhầm tách class với đảm bảo “JMX lỗi thì ứng dụng vẫn chạy”. Nếu yêu cầu nghiệp vụ vẫn sẵn sàng khi quản trị thất bại, cần thiết kế deployment và chiến lược fallback có chủ đích, không đơn thuần đổi annotation.

Tương tự, `RegistrationPolicy.IGNORE_EXISTING` không phải giải pháp tự động an toàn: nó có thể bỏ qua MBean mới trong khi client vẫn nhìn thấy một MBean cũ khác.

## 18. Tổ chức package và module

Một cấu trúc thư mục tham khảo:

```text
src/main/java/com/example/orders/
  domain/
    Order.java
  application/
    OrderProcessingService.java
    DefaultOrderProcessingService.java
  management/
    OrderProcessingAdminMBean.java
    OrderProcessingAdmin.java
  config/
    OrderJmxConfiguration.java
```

Nếu hệ thống lớn, có thể tách thành module:

```text
orders-core
  -> business interfaces / implementations

orders-management-jmx
  -> depends on orders-core
  -> adapter + Spring JMX configuration

orders-app
  -> wires business and optional management module
```

Hướng phụ thuộc nên là:

```text
management-jmx --> business-core
business-core  -X-> management-jmx
```

Tách module giúp ứng dụng không cần JMX có thể tái sử dụng business-core mà không kéo thêm hạ tầng quản trị.

## 19. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `InstanceAlreadyExistsException` | Adapter được export qua cả manual và annotation-driven exporter | Chọn một owner cho ObjectName |
| MBean không xuất hiện | Config/profile không active, exporter dùng server khác | Kiểm tra context, profile, `setServer`, `isRegistered` |
| JMX thấy service methods không mong muốn | Export trực tiếp bean và assembler phản chiếu rộng | Dùng adapter/management interface hẹp |
| Operation không đi qua transaction | Export target hoặc tự gọi method nội bộ | Inject và gọi Spring proxy qua interface đúng |
| Test business cần JMX | Logic phụ thuộc hạ tầng management | Chuyển ObjectName/exporter vào configuration |
| MBean có nhưng thiếu methods | Interface Standard MBean hoặc metadata assembler không khớp | Kiểm tra `MBeanInfo` |
| Thay tên bean làm đứt monitoring | ObjectName được sinh thiếu ổn định từ bean key | Đặt ObjectName logic rõ ràng |
| Gọi operation không được bảo vệ | Authorization chỉ nằm ở connector hoặc target chưa áp dụng advice | Thiết kế security trên ranh giới JMX và business |
| JConsole/JMC không thấy MBean | Client kết nối platform server nhưng exporter dùng custom server | Kiểm tra connector và server selection |

## 20. Checklist khi triển khai thực tế

Trước khi đưa một management MBean vào vận hành:

1. Business service có import JMX class không? Nếu có, việc phụ thuộc đó có thực sự cần thiết?
2. Management interface chỉ expose khả năng cần cho operations không?
3. ObjectName được đặt tập trung, có domain/type/name rõ ràng và ổn định không?
4. Exporter đăng ký adapter vào đúng MBeanServer không?
5. Có nhiều exporter tự động/thủ công cùng export một resource không?
6. Method JMX có side effect được giới hạn, validate và kiểm soát quyền không?
7. Adapter có gọi qua Spring service proxy để không bỏ qua advice quan trọng không?
8. Unit tests của nghiệp vụ có chạy độc lập với JMX không?
9. Integration tests có xác minh `isRegistered`, `MBeanInfo`, invocation và cleanup không?
10. Remote connector có authentication/TLS/network controls phù hợp môi trường không?

## 21. Bài tập thực hành

1. Viết một `InventoryService` thuần nghiệp vụ với `getStockSyncQueueDepth()` và `pauseStockSync()`.
2. Tạo `InventoryAdminMBean` chỉ gồm thuộc tính queue depth và operation pause.
3. Cài đặt `InventoryAdmin` delegate qua `InventoryService`; không import `javax.management` trong service.
4. Viết `InventoryJmxConfiguration` tạo adapter, exporter, ObjectName `com.example.inventory:type=Sync,name=Stock`.
5. Dùng MBeanServer thật trong test xác minh đọc attribute và gọi operation; đóng exporter/context và xác minh MBean được unregister.
6. Thử thêm một method nội bộ `deleteAllStockHistory()` vào service. Xác nhận method đó không xuất hiện trong `MBeanInfo` của adapter.
7. Tạo profile tắt JMX configuration và kiểm tra service nghiệp vụ vẫn hoạt động.
8. Bật transaction/security proxy quanh một service operation trong ứng dụng test và xác minh đường gọi từ adapter đi qua proxy.

## 22. Câu hỏi tự kiểm tra

- Vì sao class nghiệp vụ không nên trực tiếp chịu trách nhiệm đặt `ObjectName`?
- Management adapter khác business service interface ở điểm nào?
- Việc tách JMX adapter có tự tạo authentication hoặc authorization không?
- Khi Spring exporter lỗi startup, nghiệp vụ có luôn tiếp tục chạy không?
- Vì sao nên export adapter thay vì toàn bộ public methods của service?
- Phân biệt cách kiểm thử business service, management adapter và MBeanExporter.
- Nếu một JMX operation không đi qua transaction advice, cần kiểm tra đường proxy nào?
- Trong cấu trúc nhiều module, hướng phụ thuộc nên đi từ management sang core hay ngược lại?

**Ghi nhớ:** Giữ cấu hình quản trị tách khỏi nghiệp vụ nghĩa là business service tập trung xử lý nghiệp vụ, management adapter cung cấp hợp đồng quản trị hẹp, còn Spring `@Configuration` quyết định `MBeanServer`, `ObjectName`, `MBeanExporter` và policy. Phân tách rõ trách nhiệm giúp hạn chế việc vô tình phơi bày API, dễ kiểm thử và thay đổi hạ tầng quản trị mà ít ảnh hưởng đến code nghiệp vụ.