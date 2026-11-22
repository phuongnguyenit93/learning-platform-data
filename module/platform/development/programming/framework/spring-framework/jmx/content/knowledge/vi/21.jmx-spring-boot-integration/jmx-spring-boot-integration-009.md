# Kết hợp MBean tự định nghĩa với endpoint framework trong Spring Boot

## 1. Mục tiêu và bối cảnh

Spring Boot có nhiều cơ chế quản trị ứng dụng: các **MBean JMX tự định nghĩa** do application team tạo, các MBean có sẵn của JVM/framework và **Spring Boot Actuator endpoints** có thể được công bố qua HTTP hoặc JMX. Khi phối hợp, mục tiêu là có một hệ thống quản trị rõ ràng, không trùng ObjectName, không công bố chức năng nguy hiểm ngoài ý muốn và không nhầm lẫn giữa metric, endpoint và thao tác vận hành.

Bài học tập trung vào việc:

- Phân biệt custom MBean, JVM MBean và Actuator endpoint được expose qua JMX.
- Hiểu cấu hình Spring Boot bật JMX và exposure của Actuator.
- Tạo một MBean quản trị riêng bằng annotation Spring và quan sát song song với framework endpoint.
- Thiết kế namespace/ObjectName không xung đột, nhận diện đúng MBeanServer và quyền sở hữu exporter.
- Lựa chọn nên dùng custom JMX hay Actuator endpoint tùy nhu cầu.
- Kiểm tra bảo mật, lifecycle và khả năng quan sát cả hai lớp.

**Phạm vi phiên bản:** Các ví dụ minh họa sử dụng khái niệm Spring Framework JMX và Spring Boot Actuator phổ biến. Chi tiết auto-configuration, danh sách endpoint và property có thể thay đổi theo phiên bản Spring Boot; cần đối chiếu dependency và tài liệu đúng phiên bản của dự án.

## 2. Ba nguồn dữ liệu quản trị trong một JVM

Một ứng dụng Spring Boot có thể có:

~~~text
Spring Boot application / JVM
    |
    +-- Platform MBeanServer
           |
           +-- java.lang
           |     +-- Memory
           |     +-- Threading
           |     +-- Runtime
           |
           +-- com.example.shop
           |     +-- InventoryCache MBean
           |     +-- BackgroundJobs MBean
           |
           +-- org.springframework.boot
                 +-- Actuator endpoint MBeans (nếu bật/expose)
~~~

Các nhánh trên chỉ là sơ đồ khái niệm; domain và cách hiển thị có thể khác giữa các phiên bản, naming strategy và JMX client.

### JVM/platform MXBeans

Được JDK cung cấp, ví dụ Memory, Threading, ClassLoading, Runtime, GarbageCollector. Chúng thường xuất hiện dưới domain như `java.lang`.

### Custom application MBeans

Do ứng dụng định nghĩa để đo đạc hoặc điều khiển tài nguyên cụ thể: cache, worker, queue, trạng thái đồng bộ, thống kê xử lý. Có thể dùng Standard MBean, MXBean, Dynamic/Model MBean hoặc Spring `@ManagedResource`.

### Spring Boot Actuator endpoints

Actuator cung cấp mô hình endpoint quản trị thống nhất. Khi thích hợp và được expose, endpoint có thể được truy cập qua HTTP hoặc JMX, chẳng hạn health, info, metrics hoặc những endpoint khác tùy dependency, phiên bản và cấu hình.

**Một Actuator endpoint không mặc nhiên là một custom MBean.** Endpoint là abstraction của Actuator; lớp exposure JMX có thể trình bày endpoint đó thành MBean để JMX client sử dụng.

## 3. Phân biệt MBean và Actuator endpoint

| Tiêu chí | Custom MBean | Actuator endpoint |
| --- | --- | --- |
| Mô hình API | Attributes, operations, notifications JMX | Endpoint, operations và technologies exposure |
| Định danh | `ObjectName` | Endpoint ID, cộng quy tắc ObjectName khi qua JMX |
| Tạo bằng | Standard MBean/MXBean hoặc Spring JMX annotations | Actuator built-in endpoint hoặc custom `@Endpoint` |
| Truy cập | JMX client | HTTP/JMX tùy exposure |
| Tính đặc thù JMX | Cao | Endpoint model độc lập hơn với transport |
| Use case tiêu biểu | Điều khiển một component cụ thể, typed MBean contract | Health/info/metrics, quản trị ứng dụng theo convention |
| Bảo mật | JMX connector access + business controls | Bảo mật tương ứng technology: HTTP hoặc JMX |
| Naming | Do ứng dụng/exporter quy định | Do Actuator JMX exposure/naming quy định |

Nếu cần một **management API chỉ phục vụ Java/JMX client**, custom MBean là lựa chọn tự nhiên. Nếu cần cùng một khái niệm quản trị có thể được expose qua nhiều technology, custom Actuator endpoint có thể phù hợp hơn.

Không có lựa chọn nào tự động an toàn hơn. Các thao tác ghi và operation cần giới hạn quyền, validation và audit tương ứng.

## 4. Dependencies và bật JMX trong Spring Boot

Trong một ứng dụng Maven có Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot có hỗ trợ JMX và một property thường dùng:

~~~properties
spring.jmx.enabled=true
~~~

Thuộc tính này điều khiển tính năng JMX trong cấu hình Boot phù hợp. Trong dự án thực tế, cần xác minh:

- Spring Boot đang dùng phiên bản nào.
- Có dependency Actuator không.
- JMX auto-configuration có hiệu lực không.
- `MBeanExporter` nào thực sự được tạo.
- Có custom exporter nào đang đăng ký cùng MBean hoặc cùng ObjectName không.
- Actuator endpoint nào được phép expose qua JMX.

**Bật Spring JMX không đồng nghĩa bật remote JMX connector.** Các MBean có thể tồn tại trong platform MBeanServer và được JConsole local nhìn thấy, trong khi kết nối từ xa vẫn chưa được cấu hình.

### Exposure của Actuator qua JMX

Ví dụ property:

~~~properties
management.endpoints.jmx.exposure.include=health,info,metrics
~~~

Property này minh họa việc lựa chọn Actuator endpoint được expose qua JMX. Một số endpoint có thể không tồn tại nếu thiếu dependency hoặc không được kích hoạt; danh sách include không tự tạo những endpoint chưa có.

Có thể dùng include/exclude theo quy tắc của Spring Boot phiên bản dự án. Đừng mở toàn bộ endpoint chỉ để “thấy hết” nếu nhu cầu thực tế chỉ cần một số endpoint.

### HTTP exposure là chính sách riêng

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info,metrics
~~~

Hai cấu hình lựa chọn các endpoint theo hai technology khác nhau. Việc endpoint có thể truy cập qua JMX không có nghĩa nó tự xuất hiện trên HTTP, và ngược lại.

## 5. Tạo custom MBean với Spring annotations

Ví dụ theo dõi một cache của ứng dụng:

~~~java
package com.example.shop.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop:type=Cache,name=products",
    description = "Product cache management"
)
public class ProductCacheManagement {

    private final AtomicLong hitCount = new AtomicLong();
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Number of cache hits")
    public long getHitCount() {
        return hitCount.get();
    }

    @ManagedAttribute(description = "Whether cache is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Reset cache hit statistics")
    public void resetStatistics() {
        hitCount.set(0);
    }

    public void onCacheHit() {
        hitCount.incrementAndGet();
    }
}
~~~

Class này minh họa tập attribute/operation được công bố:

~~~text
com.example.shop:type=Cache,name=products

Attributes:
  HitCount : long [read-only]
  Enabled  : boolean [read/write]

Operations:
  resetStatistics()
~~~

Chỉ method được công bố trong metadata JMX mới thuộc management contract. Method `onCacheHit()` không được gắn annotation quản trị nên không được chủ động công bố như operation theo annotation assembler.

Ví dụ chỉ giữ trạng thái trong bean. Production nên ủy quyền cho cache/service thật; nếu chỉ đổi cờ mà cache không áp dụng cờ đó, JMX sẽ báo trạng thái không phản ánh hành vi thực tế.

## 6. Đảm bảo annotation MBean thực sự được export

`@ManagedResource` chỉ cung cấp metadata; bean cần được exporter phát hiện và đăng ký thành MBean.

Trong ứng dụng Spring Framework thuần có thể khai báo `AnnotationMBeanExporter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
~~~

Tuy nhiên, trong Spring Boot đã có JMX auto-configuration, tạo exporter thủ công có thể gây đăng ký trùng. **Không nên sao chép cấu hình trên một cách máy móc** khi Boot đã tạo exporter.

Cách xác minh trong ứng dụng:

1. Kiểm tra property JMX đang có hiệu lực.
2. Xác định bean exporter hiện có.
3. Đọc log startup để phát hiện lỗi registration.
4. Truy vấn MBeanServer để xác nhận ObjectName của custom bean.
5. Quan sát trong JConsole, kiểm tra attributes và operations thực tế.

Nếu custom bean không xuất hiện, kiểm tra component scan, active profile, conditional registration, exporter và naming. Nếu Actuator vẫn hiện mà custom bean không hiện, điều đó chưa chứng minh custom bean được exporter lựa chọn.

## 7. Tránh xung đột ObjectName với framework endpoints

Mỗi MBean được định danh duy nhất trong một MBeanServer. Hai bean không thể cùng đăng ký dưới một ObjectName.

Ví dụ một custom MBean nên dùng namespace riêng:

~~~text
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=payments
com.example.shop:type=Scheduler,name=background
~~~

Với Actuator, để framework quản lý domain và naming theo cơ chế của nó thay vì đặt custom MBean vào cùng domain/key convention khi không có lý do.

### Các lỗi dễ gặp

- Custom MBean hard-code tên giống một endpoint framework.
- Hai exporter dùng cùng domain/type/name.
- Hai `ApplicationContext` trong một JVM dùng chung MBeanServer và đăng ký tên trùng.
- Naming strategy dựa vào runtime proxy class thay vì logical resource.
- Đổi domain khi deploy khiến dashboard hoặc client không tìm thấy MBean.

### Quy tắc khuyến nghị

Dành một domain ổn định cho application MBean, chẳng hạn `com.example.shop`, với các key property có nghĩa nghiệp vụ. Tránh đặt tên theo một Java class tạm thời hoặc hostname/port thay đổi. Trong mỗi JVM, mỗi logical resource được export phải có ObjectName duy nhất.

Nếu nhiều JVM có MBeanServer riêng, cùng ObjectName không phải xung đột; hệ thống giám sát cần phân biệt instance ở tầng target.

## 8. Đọc MBean trong JConsole

Sau khi chạy ứng dụng:

1. Mở `jconsole` và chọn đúng JVM.
2. Chọn tab **MBeans**.
3. Mở domain `java.lang` để xem các platform MXBeans.
4. Mở domain của ứng dụng như `com.example.shop` để xem custom MBean.
5. Tìm domain của Spring Boot Actuator theo cách đặt tên hiện hành của phiên bản chạy.
6. Đọc attributes, operations và descriptions để xác định đúng resource.

Một cây minh họa:

~~~text
MBeans
├── java.lang
│   ├── Memory
│   ├── Runtime
│   └── Threading
├── com.example.shop
│   ├── Cache
│   │   └── products
│   └── Queue
│       └── payments
└── org.springframework.boot
    ├── health
    ├── info
    └── metrics
~~~

Cấu trúc node là minh họa, không phải cam kết tên hiển thị chính xác trên mọi phiên bản. JConsole có thể nhóm key properties khác nhau và Actuator JMX naming có thể khác.

### Kiểm tra bằng ObjectName thay vì chỉ nhìn nhánh

Nếu JConsole hiển thị MBean dưới node khác kỳ vọng, đối chiếu **ObjectName đầy đủ**. Domain trong ObjectName là namespace JMX, không nhất thiết là Java package của class.

## 9. Truy vấn custom MBean và framework MBean bằng Java

MBeanServer cho phép query domain:

~~~java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ListJmxMBeans {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        Set<ObjectName> customNames =
            server.queryNames(
                new ObjectName("com.example.shop:*"),
                null
            );

        for (ObjectName name : customNames) {
            System.out.println(name.getCanonicalName());
        }
    }
}
~~~

Chạy đoạn code trong **JVM đang chứa MBeans**. Nếu chạy ở một tiến trình Java khác thì `getPlatformMBeanServer()` tham chiếu platform server của tiến trình đó, không tự kết nối tới ứng dụng Spring Boot bên ngoài.

Nếu dùng một `MBeanServer` riêng thay vì platform server, cần inject hoặc lấy đúng server mà exporter thực sự sử dụng.

### Kiểm tra chính xác custom MBean

~~~java
ObjectName name = new ObjectName(
    "com.example.shop:type=Cache,name=products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Custom cache MBean is not registered"
    );
}

Object hits = server.getAttribute(name, "HitCount");
System.out.println("HitCount = " + hits);
~~~

Truy vấn này xác nhận MBean đã đăng ký và attribute có thể đọc. Nếu permission hoặc metadata không hợp lệ, phương thức vẫn có thể ném lỗi runtime.

## 10. Custom Actuator endpoint là lựa chọn khác với custom MBean

Khi muốn một management concept được truy cập qua nhiều technology, có thể tạo **custom Actuator endpoint**:

~~~java
package com.example.shop.management;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "inventorySummary")
public class InventorySummaryEndpoint {

    private final InventoryService inventoryService;

    public InventorySummaryEndpoint(
            InventoryService inventoryService
    ) {
        this.inventoryService = inventoryService;
    }

    @ReadOperation
    public InventorySummary summary() {
        return inventoryService.currentSummary();
    }
}
~~~

`InventoryService` và `InventorySummary` là các kiểu minh họa, cần được định nghĩa trong ứng dụng. Cách Actuator chuyển đổi kiểu dữ liệu và tính tương thích của kiểu kết quả khi expose JMX/HTTP phải được đánh giá theo yêu cầu endpoint và phiên bản framework.

Endpoint ID nên tuân theo quy tắc định danh của Spring Boot phiên bản đang sử dụng. Các endpoint built-in cũng có ID riêng như `health`, `info`, `metrics`.

### Khi nào không nên tự tạo Actuator endpoint?

Nếu chỉ cần một Standard MBean với Java interface typed đã dùng lâu dài, việc chuyển sang Actuator endpoint có thể phá hợp đồng ObjectName/attributes/operations của các client cũ.

Nếu thao tác có nhiều overload, JMX notification, yêu cầu MXBean Open Types đặc thù hoặc client chỉ dùng JMX, custom MBean thường phù hợp hơn.

## 11. Không export hai giao diện cho cùng một tài nguyên mà thiếu chính sách

Có thể một resource được quản lý đồng thời bởi:

~~~text
ProductCacheService
      |
      +-- Custom MBean: resetStatistics()
      |
      +-- Actuator endpoint: clearCache()
~~~

Đây không mặc nhiên sai. Tuy nhiên, cần trả lời:

- Hai giao diện có đọc cùng một trạng thái không?
- Operation có tên khác nhưng tác dụng chồng lấn không?
- Có thể có hai client gọi đồng thời và gây race condition không?
- Quyền truy cập HTTP và JMX có nhất quán không?
- Có một service chung bảo đảm validation và concurrency không?
- Khi action thành công, metric/health phản ánh ngay hay có độ trễ?

### Thiết kế đề xuất: service quản trị chung

~~~text
                ProductCacheService
                   /          \
                  /            \
          JMX adapter       Actuator endpoint
             |                   |
        JMX connector       HTTP / JMX exposure
~~~

Hai adapter nên gọi một service trung tâm có state machine và policy rõ ràng. Đừng tự nhân bản logic pause/reset/clear ở hai lớp khác nhau khiến kết quả không nhất quán.

## 12. Phân biệt Actuator metrics với custom JMX attribute

Ví dụ ứng dụng muốn báo số cache hit. Có ít nhất hai cách:

**Custom MBean attribute:**

~~~text
com.example.shop:type=Cache,name=products
    HitCount = 12450
~~~

**Actuator metrics endpoint:** cung cấp metric từ hệ thống metrics như Micrometer theo mô hình meter/tag phù hợp.

Cả hai có thể cùng tồn tại, nhưng sẽ khó hiểu nếu:

- Một bên đếm số hit từ lúc JVM start, bên kia dùng time window.
- Một bên reset thủ công, bên kia là cumulative counter không reset cùng lúc.
- Metric name/unit khác nhau.
- Tag của metric và ObjectName key mang nghĩa khác nhau.
- Client bỏ qua nhãn instance khiến số liệu giữa các replica bị trộn.

Muốn đồng bộ, cần thống nhất định nghĩa metric: đơn vị, ranh giới thời gian, nguồn số liệu và scope resource. Không nên kỳ vọng custom attribute tự xuất hiện trong Actuator metrics; thường cần meter riêng hoặc adapter phù hợp.

## 13. Endpoint exposure và access control

Cần phân biệt **availability** và **authorization**.

- Endpoint **enabled**: bean/endpoint có thể tồn tại trong application context.
- Endpoint **exposed qua JMX**: có thể được đăng ký thành JMX MBean theo cấu hình.
- Endpoint **exposed qua HTTP**: có đường truy cập web theo cấu hình.
- Endpoint **được phép truy cập**: client còn phải vượt qua các lớp security tương ứng.

Ví dụ:

~~~properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.web.exposure.include=health,info
~~~

Không nên suy ra mọi endpoint liệt kê đều đã sẵn sàng trong mọi ứng dụng. Kiểm tra runtime registry và danh sách endpoint thực tế.

### Bảo mật JMX không phải bảo mật HTTP

JMX remote connector có authentication/TLS/authorization riêng. Spring Security cho HTTP endpoints không tự thay thế chính sách của JMX connector.

Nếu một operation quản trị được expose qua hai transport, cần xem xét quyền truy cập **trên cả hai đường**. Một endpoint chỉ được bảo vệ bằng HTTP security vẫn có thể cần kiểm soát JMX riêng khi JMX exposure bật.

Không mở remote JMX rộng chỉ để dùng Actuator metrics. Nếu chỉ cần dữ liệu giám sát, một metric endpoint read-only với mô hình bảo mật phù hợp có thể giảm quyền quản trị phải cấp cho collector.

## 14. Naming và tương thích client

ObjectName của custom MBean là một phần management contract:

~~~text
com.example.shop:type=Cache,name=products
~~~

Các script như:

~~~java
connection.getAttribute(
    new ObjectName(
        "com.example.shop:type=Cache,name=products"
    ),
    "HitCount"
);
~~~

phụ thuộc vào tên và kiểu attribute đó. Thay ObjectName hoặc đổi `HitCount` thành `Hits` có thể phá client.

Đối với Actuator endpoint, endpoint ID và cách framework chuyển nó sang ObjectName có thể khác với custom MBean. Khi chuyển đổi giữa hai cơ chế, không được mặc định giữ nguyên hợp đồng JMX.

Nếu có legacy client, có thể duy trì adapter custom MBean để tương thích trong khi triển khai endpoint mới. Nhưng nên kiểm soát kỹ ownership và concurrency nếu cả hai giao diện cùng điều khiển một resource.

## 15. Lifecycle và nhiều ApplicationContext

Một ứng dụng Spring Boot có thể có:

- ApplicationContext chính.
- Management context riêng trong một số cấu hình.
- Bean quản trị từ thư viện hoặc module được import.
- Framework exporter và exporter do ứng dụng khai báo.

Nếu nhiều exporter cùng dùng một MBeanServer, cần tránh đăng ký trùng ObjectName.

Một số vấn đề:

1. Custom MBean được đăng ký hai lần vì hai exporter.
2. Bean tồn tại trong child context nhưng exporter nhìn thấy phạm vi khác dự kiến.
3. Context đóng nhưng MBean cũ không được unregister như mong đợi.
4. Policy `REPLACE_EXISTING` che mất xung đột owner.
5. JConsole đang kết nối tới JVM khác với ứng dụng đang kiểm tra.

**Chính sách đăng ký không thay thế thiết kế ownership.** Mỗi MBean nên có owner rõ chịu trách nhiệm register/unregister; nếu hai context cần cùng dữ liệu, hãy cân nhắc dùng service chung hoặc client/proxy thay vì xuất trùng một ObjectName.

## 16. Tích hợp kiểm thử: xác nhận cả hai nhóm MBean

Một integration test hữu ích nên xác nhận:

- Custom MBean có ObjectName chính xác.
- Attribute/operation cần thiết được công bố đúng.
- Các Actuator endpoint dự kiến xuất hiện dưới JMX khi cấu hình phù hợp.
- Không có xung đột tên trong registry.
- Các operation nhạy cảm không bị xuất ngoài dự kiến.
- Context shutdown dọn dẹp registration thuộc quyền quản lý.

Ví dụ kiểm tra custom MBean:

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class CustomMBeanContractCheck {
    public static void verify(MBeanServer server) throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop:type=Cache,name=products"
        );

        if (!server.isRegistered(name)) {
            throw new AssertionError(
                "Expected custom MBean is not registered"
            );
        }

        Object hitCount = server.getAttribute(name, "HitCount");
        if (!(hitCount instanceof Long)) {
            throw new AssertionError("Wrong HitCount type");
        }
    }
}
~~~

Ví dụ này giả định test inject đúng MBeanServer mà exporter dùng. Nó chỉ kiểm tra custom MBean; Actuator contract cần kiểm thử riêng theo endpoint ID và naming thực tế của phiên bản framework.

### Không hard-code domain Actuator không được xác minh

Thay vì đoán ObjectName cho health/info, trong integration test có thể query toàn bộ registry, tìm MBean thuộc domain Actuator thực tế và đối chiếu naming quy định bởi version đang chạy. Sau đó ghi nhận tên kỳ vọng trong test fixture.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JVM MBeans xuất hiện nhưng custom MBean không có | Exporter không bật hoặc bean chưa được chọn | `spring.jmx.enabled`, component scan, metadata |
| Custom MBean có nhưng Actuator endpoint không có | Thiếu Actuator hoặc JMX exposure không cho phép | Dependency, endpoint availability, properties |
| HTTP endpoint có nhưng JMX endpoint không có | Hai exposure policy khác nhau | `management.endpoints.jmx.exposure.*` |
| Hai exporter báo trùng tên | Cùng ObjectName trong một MBeanServer | Naming, exporter ownership |
| Endpoint hiển thị dưới domain lạ | Framework naming khác dự kiến | MBeanServer query/canonical ObjectName |
| Client remote không truy cập được | Connector chưa bật hoặc network/TLS/auth lỗi | JMX transport và security |
| Attribute/operation thiếu | Metadata hoặc interface không khớp | `MBeanInfo` |
| Metrics hai nguồn khác nhau | Khác scope, unit, reset hoặc aggregation | Tài liệu định nghĩa metric |
| Context shutdown ảnh hưởng MBean khác | Ownership/registration lifecycle không rõ | Exporter và MBeanServer |
| Gọi operation qua HTTP thành công nhưng JMX bị từ chối | Chính sách access khác nhau | HTTP/JMX authorization riêng |

## 18. Khi nào chọn custom MBean, khi nào chọn Actuator?

| Yêu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Cần Standard MBean/MXBean interface cho Java JMX client | Custom MBean |
| Cần JMX notification theo hợp đồng cụ thể | Custom MBean |
| Cần thuộc tính có getter/setter và operation JMX đặc thù | Custom MBean |
| Cần health, info, metrics chuẩn của Boot | Actuator |
| Muốn cùng một endpoint có thể expose qua HTTP/JMX | Actuator custom endpoint |
| Phải giữ ObjectName cũ cho script vận hành | Giữ adapter custom MBean |
| Chỉ cần metrics để monitoring collector | Micrometer/Actuator metrics thường phù hợp |
| Cần thao tác nguy hiểm có workflow bảo mật sâu | Đánh giá API quản trị chuyên biệt và audit |

Có thể sử dụng cả hai nếu trách nhiệm không chồng lấn hoặc có service trung tâm kiểm soát trạng thái. Không nên chọn theo số dòng code đơn thuần.

## 19. Bài tập thực hành

**Mục tiêu:** chạy một ứng dụng Spring Boot có custom MBean cho cache và Actuator endpoint `health`/`info` được expose qua JMX.

Thực hiện:

1. Thêm dependency Actuator.
2. Bật JMX theo cấu hình dự án.
3. Tạo `ProductCacheManagement` với `@Component`, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
4. Cấu hình Actuator JMX exposure chỉ gồm những endpoint cần dùng.
5. Chạy ứng dụng và mở JConsole đúng JVM.
6. Tìm `com.example.shop:type=Cache,name=products`.
7. Đọc `HitCount`, `Enabled`; thử `resetStatistics()` trên môi trường test.
8. Tìm các MBean Actuator thực sự xuất hiện và ghi nhận ObjectName của chúng.
9. Query `MBeanServer` để xác nhận không có ObjectName ngoài ý muốn trong domain ứng dụng.
10. Phân biệt quyền truy cập HTTP endpoints và JMX remote nếu có bật remote.
11. Tắt ứng dụng và xác nhận exporter dọn dẹp MBean thuộc lifecycle của context.

**Kết quả mong đợi:** custom resource và Actuator endpoints có thể tồn tại cùng MBeanServer, dùng naming khác nhau và phục vụ những nhu cầu quản trị riêng.

## 20. Câu hỏi tự kiểm tra

**1. Bật `spring.jmx.enabled=true` có tự bật remote JMX không?** Không. Remote connector cần cấu hình bảo mật và transport riêng.

**2. `@ManagedResource` có đồng nghĩa Actuator endpoint?** Không. Nó khai báo metadata cho Spring JMX export.

**3. Vì sao JConsole có thể thấy JVM Memory nhưng không thấy custom MBean?** Platform MXBean có sẵn; custom bean còn cần được Spring tạo và exporter đăng ký thành công.

**4. HTTP exposure và JMX exposure của Actuator có giống nhau không?** Không. Chúng có thể có chính sách exposure và bảo mật riêng.

**5. Cùng ObjectName trong hai JVM khác nhau có xung đột không?** Thông thường không; uniqueness áp dụng trong từng MBeanServer.

**6. Vì sao hai lớp quản trị cùng gọi một resource dễ gây lỗi?** Chúng có thể tạo side effect trùng hoặc race condition nếu không dùng service/state machine chung.

**7. Có nên đặt custom MBean vào domain Actuator?** Không nên nếu không có lý do rõ và chưa kiểm tra naming/ownership của framework.

**8. Khi nào cần custom Actuator endpoint?** Khi muốn mô hình endpoint quản trị độc lập với JMX và có thể expose qua technology khác tùy cấu hình.

## 21. Tổng kết

Spring Boot cho phép sử dụng **custom MBeans**, **platform MXBeans** và **Actuator endpoints** trong cùng một môi trường quản trị. Cách phối hợp bền vững là:

- Sử dụng custom MBean cho hợp đồng JMX đặc thù, đặt ObjectName trong domain riêng.
- Sử dụng Actuator cho các endpoint quản trị theo convention của Boot.
- Chỉ expose những endpoint và operation cần thiết.
- Tách security của JMX connector khỏi security của HTTP endpoint.
- Giữ một nguồn logic nghiệp vụ chung nếu custom MBean và Actuator cùng điều khiển tài nguyên.
- Xác minh registry JMX và metadata thực tế thay vì đoán naming của framework.

**Kết hợp đúng không phải là xuất càng nhiều càng tốt, mà là công bố đúng thông tin và đúng thao tác qua từng giao diện quản trị, với ownership, naming và quyền truy cập nhất quán.**

### Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
