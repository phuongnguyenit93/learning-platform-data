# Đảm bảo tên JMX nhất quán giữa local và remote

## 1. Vấn đề và mục tiêu

Trong Spring Framework JMX, mỗi MBean được đăng ký trong **MBeanServer** bằng một **ObjectName**. Client tại chỗ hoặc từ xa muốn truy cập đúng MBean đều cần biết ObjectName đó. Một thay đổi nhỏ trong domain, key property hoặc quy tắc đặt tên có thể làm JConsole, script, dashboard và công cụ vận hành không tìm thấy tài nguyên.

Ví dụ ứng dụng xuất một MBean:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

Ở máy phát triển, một công cụ local đọc được MBean này. Khi triển khai lên máy chủ khác, client từ xa lại truy vấn:

```text
com.example.orders:type=Queue,name=payments
```

Hai chuỗi trên **không cùng ObjectName**, vì chuỗi thứ nhất có thêm key `application=checkout`. Việc client kết nối đúng JVM không làm hai tên khác nhau trở thành tương đương.

Bài học này trình bày cách thiết kế **naming strategy ổn định** để ứng dụng Spring và mọi client JMX dùng cùng hợp đồng tên, đồng thời tách phần định danh MBean khỏi thông tin kết nối của từng môi trường.

## 2. Local và remote dùng cùng mô hình định danh JMX

Kiến trúc tổng quát:

```text
Spring application / JVM
       |
       +-- Bean: PaymentQueueManagement
       |
       +-- MBeanExporter
               |
               +-- ObjectNamingStrategy
               |       |
               |       v
               |   ObjectName
               |
               v
           MBeanServer
             ^      ^
             |      |
       local client remote JMX connector
             |      |
          JConsole   remote script/dashboard
```

MBeanServer dùng cùng ObjectName để tra cứu MBean, bất kể lời gọi đến từ client trong JVM hay qua connector từ xa. Sự khác biệt giữa local và remote chủ yếu nằm ở **cách lấy kết nối đến MBeanServer**:

- **Local/in-process:** ứng dụng có thể dùng `MBeanServer` trực tiếp.
- **Remote:** client dùng `JMXConnector` và `MBeanServerConnection`.
- **MBean identity:** vẫn là ObjectName được đăng ký trong MBeanServer đích.

Không phải cứ ở máy khác thì phải thay domain hoặc thêm host vào ObjectName. Phần host, port, authentication và TLS thuộc **connection configuration**. Phần tên tài nguyên thuộc **management identity**.

## 3. ObjectName gồm những gì?

Cú pháp tổng quát:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

| Thành phần | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| Domain | `com.example.orders` | Namespace nhóm các MBean |
| `type` | `Queue` | Loại tài nguyên |
| `application` | `checkout` | Dịch vụ hoặc ứng dụng sở hữu |
| `name` | `payments` | Định danh logical resource |

**Quy tắc danh tính:** domain và tập key property quyết định ObjectName. Thứ tự key property không quyết định sự bằng nhau.

Hai chuỗi sau biểu diễn cùng một tên:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:name=payments,type=Queue,application=checkout
```

Nhưng các chuỗi sau là những tên khác:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=inventory,name=payments
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
```

Khi debug, nên ghi log `ObjectName.getCanonicalName()` để chuẩn hóa thứ tự key, tránh so sánh chuỗi thô chỉ khác thứ tự.

## 4. Thống nhất hợp đồng tên trước khi cấu hình kết nối

Một naming contract phù hợp cho nhiều ứng dụng có thể là:

```text
domain = com.example.<subsystem>

type        = logical resource type
application = stable application identifier
name        = stable resource identifier
```

Ví dụ:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
com.example.orders:type=Scheduler,application=checkout,name=background
com.example.inventory:type=Cache,application=inventory,name=products
```

Quy ước này nên được dùng thống nhất bởi:

1. Bean exporter tạo ObjectName.
2. Client Java dùng `ObjectName` để đọc attribute/gọi operation.
3. Script vận hành và các dashboard cần query chính xác.
4. Kiểm thử integration xác nhận registry.
5. Tài liệu và runbook vận hành.

**Không nhân bản logic đặt tên bằng các chuỗi viết tay ở nhiều nơi** nếu có thể chia sẻ một schema hoặc helper. Nếu các client ở ngôn ngữ khác nhau, công bố schema ObjectName như một hợp đồng tài liệu/kiểm thử.

### Những trường không nên đưa vào tên khi không cần

- Hostname hoặc IP thay đổi theo deployment.
- Port JMX remote.
- Random UUID sinh mới mỗi lần khởi động.
- Container ID ngắn hạn.
- Request ID hoặc user ID tạo ra nhiều MBean biến động.
- Tên lớp proxy do Spring AOP sinh.
- Thời gian khởi động hoặc build timestamp.

Những giá trị này làm ObjectName khó ổn định, dễ phá vỡ query và dashboard. Nếu hai instance ở **hai JVM khác nhau**, chúng thường có MBeanServer riêng và có thể sử dụng cùng ObjectName. Việc phân biệt instance được thực hiện tại tầng **monitoring target**.

## 5. Phân biệt ObjectName với định danh JVM/instance

Giả sử một service chạy trên ba node:

```text
node-a:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
node-b:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
node-c:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
```

Đây là một thiết kế hợp lệ khi ba JVM có MBeanServer riêng. Để nhận diện dữ liệu trong hệ thống giám sát:

```text
target=node-a, ObjectName=...name=payments
target=node-b, ObjectName=...name=payments
target=node-c, ObjectName=...name=payments
```

Nếu collector gộp dữ liệu mà không giữ nhãn target, số liệu giữa các replica có thể bị trộn. Đây là lỗi **định danh nguồn thu thập**, không phải xung đột ObjectName trong MBeanServer.

Chỉ thêm `instance` vào ObjectName khi thực sự cần phân biệt nhiều logical instances **trong cùng một MBeanServer** hoặc schema quản trị đã chủ động quy định như vậy. Khi thêm, giá trị instance nên có tính ổn định theo vòng đời và vai trò của tài nguyên.

### Hai lớp định danh

```text
Management target:
  cluster / environment / host / process / connector URL

Management resource:
  JMX ObjectName trong MBeanServer được kết nối
```

Đừng dùng host/port để xác định loại tài nguyên, cũng đừng kỳ vọng ObjectName tự mang thông tin định tuyến mạng.

## 6. Spring ObjectNamingStrategy hoạt động như thế nào?

Spring Framework có interface **`ObjectNamingStrategy`** dùng để tạo ObjectName cho các bean được xuất qua `MBeanExporter`.

Các cơ chế liên quan có thể gồm:

- **`MetadataNamingStrategy`**: sử dụng metadata JMX và fallback naming để tạo ObjectName.
- **`KeyNamingStrategy`**: dùng cách ánh xạ tên dựa trên bean key/configuration.
- **Custom `ObjectNamingStrategy`**: ứng dụng tự áp dụng hợp đồng đặt tên.

Một vấn đề quan trọng là annotation có thể khai báo ObjectName cố định:

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueManagement {
}
```

Nếu mục tiêu schema mới yêu cầu `application=checkout`, những bean vẫn dùng annotation tên cũ sẽ bị lệch hợp đồng. Khi chuyển sang chiến lược dùng chung, cần xác định nguồn ưu tiên đặt tên: annotation, explicit mapping hay naming strategy, theo exporter thực tế.

Không nên cho hai cơ chế tạo tên khác nhau một cách tùy ý trong cùng một ứng dụng.

## 7. Ví dụ: xây ObjectName từ các định danh logical ổn định

Một helper Java giúp chuẩn hóa cách tạo tên:

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import java.util.Hashtable;

public final class ManagementNames {

    private ManagementNames() {
    }

    public static ObjectName queue(
            String application,
            String resourceName
    ) throws MalformedObjectNameException {
        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Queue");
        properties.put("application", application);
        properties.put("name", resourceName);

        return new ObjectName("com.example.orders", properties);
    }
}
```

Caller dùng:

```java
ObjectName payments = ManagementNames.queue(
        "checkout",
        "payments"
);

System.out.println(payments.getCanonicalName());
```

Hàm có ưu điểm là giữ cố định domain và key names, giúp tránh lỗi thiếu `application` hoặc đổi `type` giữa các đoạn code.

**Lưu ý với dữ liệu đầu vào:** ObjectName có cú pháp đặc biệt cho dấu phẩy, dấu bằng, dấu sao, dấu hỏi và dấu ngoặc kép. Trong hệ thống thật, nên dùng định danh logical được validate theo một tập ký tự ổn định hoặc xây dựng tên với thao tác quote/escape theo quy tắc JMX. Không nối trực tiếp chuỗi dữ liệu tùy ý vào biểu thức ObjectName.

Nếu một property value chứa ký tự đặc biệt, cần kiểm tra cả `ObjectName.quote(value)` và hành vi của constructor đang dùng; tránh double quoting hoặc tạo pattern ngoài dự kiến.

## 8. Ví dụ custom ObjectNamingStrategy trong Spring

Giả sử ứng dụng muốn xác định tên bằng `applicationId` và `beanKey`:

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class StableObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String applicationId;

    public StableObjectNamingStrategy(String applicationId) {
        this.applicationId = applicationId;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.management"
              + ":type=Component"
              + ",application=" + ObjectName.quote(applicationId)
              + ",name=" + ObjectName.quote(beanKey)
        );
    }
}
```

Đây là ví dụ khái niệm: `type=Component` là một lựa chọn đơn giản; trong ứng dụng thực, type nên phản ánh **loại resource nghiệp vụ ổn định**, không dùng tên lớp proxy.

Có thể áp dụng vào `MBeanExporter`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class ManagementExportConfiguration {

    @Bean
    StableObjectNamingStrategy stableNamingStrategy() {
        return new StableObjectNamingStrategy("checkout");
    }

    @Bean
    MBeanExporter queueMBeanExporter(
            PaymentQueueManagement paymentQueueManagement,
            StableObjectNamingStrategy strategy
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "payments",
                paymentQueueManagement
        ));
        exporter.setNamingStrategy(strategy);
        return exporter;
    }
}
```

`PaymentQueueManagement` là class minh họa. Trong ví dụ này, `payments` là bean key mà exporter cung cấp cho naming strategy. Nếu ứng dụng có nhiều loại resource, chiến lược thực tế nên nhận metadata resource type riêng để tránh mọi bean có cùng `type=Component`.

**Điểm cần kiểm tra:** Tùy cách exporter xử lý explicit names và metadata, một key có dạng ObjectName đầy đủ có thể được dùng trực tiếp. Do đó, khi muốn naming strategy làm chủ, hãy dùng key theo hợp đồng và xác nhận ObjectName đăng ký thực tế bằng MBeanServer.

## 9. Dùng cấu hình thay vì hard-code thông tin môi trường vào ObjectName

Một cấu hình ứng dụng có thể có:

```properties
management.jmx.application-id=checkout
management.jmx.domain=com.example.orders

management.jmx.remote.host=127.0.0.1
management.jmx.remote.port=9010
```

Hai nhóm thuộc tính có vai trò khác nhau:

- `management.jmx.application-id` và `management.jmx.domain`: quyết định management identity.
- `management.jmx.remote.host` và `management.jmx.remote.port`: thông tin để client tìm endpoint, không phải thành phần của ObjectName.

Các tên property trên là **ví dụ do ứng dụng tự định nghĩa**, không phải mọi property đều là cấu hình chuẩn của Spring Boot hoặc Java JMX. Cần tự khai báo/bind chúng nếu dùng trong code.

Nếu muốn ObjectName giống nhau ở local/staging/production, giữ domain, type và logical name theo cùng schema. Tầng dashboard hoặc collector có thể thêm nhãn `environment`, `cluster`, `instance` khi thu thập.

### Cấu hình Spring Boot

Spring Boot có thể điều khiển khả năng export JMX qua các thuộc tính như `spring.jmx.enabled` tùy phiên bản. Nhưng việc bật JMX và lựa chọn domain/bean name phải được đối chiếu với cấu hình thực tế, đặc biệt nếu ứng dụng có Actuator hoặc nhiều exporter.

Không nên suy ra rằng bật `spring.jmx.enabled` sẽ tự áp dụng naming strategy tùy chỉnh nêu trên.

## 10. Local JMX: kiểm chứng tên đã đăng ký

Tại JVM ứng dụng, có thể query MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

System.out.println(server.isRegistered(expected));
```

Nếu `true`, có một MBean đang đăng ký đúng tên trong server đó. Nếu `false`, cần kiểm tra:

- MBeanExporter có chạy không?
- Bean được chọn để export chưa?
- ObjectName thực tế có khác schema không?
- Exporter đang dùng platform MBeanServer hay một MBeanServer khác?
- Có lỗi đăng ký hoặc trùng tên ở startup không?

### Liệt kê domain

```java
for (ObjectName name : server.queryNames(
        new ObjectName("com.example.orders:*"),
        null)) {
    System.out.println(name.getCanonicalName());
}
```

Đây là cách quan sát registry thực tế. Nên dùng canonical names khi chẩn đoán để tránh nhầm vì thứ tự key property.

## 11. Remote JMX: kết nối thay đổi, ObjectName giữ nguyên

Một client Java từ xa dùng `JMXConnectorFactory`:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteQueueInspector {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );

        try (JMXConnector connector =
                     JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example.orders:type=Queue,"
                    + "application=checkout,name=payments"
            );

            System.out.println(
                    "Registered: " + connection.isRegistered(name)
            );
            System.out.println(
                    "PendingCount: "
                    + connection.getAttribute(name, "PendingCount")
            );
        }
    }
}
```

URL chỉ là ví dụ nếu server thật đã bật và bảo vệ JMX RMI trên endpoint đó. Java không mặc định bật một JMX remote port nhất định.

**Lưu ý:** `JMXConnector` hỗ trợ đóng qua `close()` và được dùng với try-with-resources trong môi trường API phù hợp. Nếu phiên bản hoặc connector cụ thể không hỗ trợ điều kiện `AutoCloseable` mong muốn, có thể gọi `close()` trong `finally`.

Đối với remote JMX:

- Host/port, RMI endpoint, firewall và NAT ảnh hưởng kết nối.
- Authentication và TLS bảo vệ truy cập.
- Quyền đọc attribute hoặc gọi operation có thể khác nhau theo client.
- ObjectName chỉ được tra cứu **sau khi** kết nối đúng MBeanServer đích.

Đừng đổi `ObjectName` để chữa lỗi network; trước hết phân biệt lỗi kết nối với lỗi không tìm thấy MBean.

## 12. So sánh tên local và remote theo chuẩn hóa

Nếu hai công cụ cần đối chiếu danh tính, sử dụng:

```java
ObjectName local = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

ObjectName remote = new ObjectName(
    "com.example.orders:name=payments,application=checkout,type=Queue"
);

System.out.println(local.equals(remote)); // true
```

Cách so sánh đúng là dùng `ObjectName.equals` hoặc canonical name. Tránh so sánh chuỗi nhập nguyên dạng vì thứ tự key có thể khác.

### Khi hai JVM có cùng tên

Nếu local và remote đều dùng:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

đó là dấu hiệu schema nhất quán, nhưng không có nghĩa hai MBean chia sẻ trạng thái. Mỗi JVM có resource riêng. Để so sánh dữ liệu, luôn giữ thông tin về JVM/target.

### Khi local và remote khác domain

Ví dụ:

```text
Local:  com.example.dev:type=Queue,name=payments
Remote: com.example.prod:type=Queue,name=payments
```

Đây có thể là chính sách cố ý tách environment, nhưng script dùng một ObjectName cố định sẽ cần logic riêng theo môi trường.

Thông thường dễ duy trì hơn khi giữ domain nghiệp vụ ổn định và gắn environment ở tầng monitoring. Tuy nhiên, nếu nhiều môi trường nằm trong cùng JVM/MBeanServer hoặc có yêu cầu namespace cụ thể, có thể đưa environment vào tên với quy tắc được tài liệu hóa đầy đủ.

## 13. Bản chất của xung đột tên

**ObjectName chỉ cần duy nhất trong một MBeanServer.**

Hai Spring bean cùng MBeanServer không thể đăng ký cùng tên:

```text
com.example.orders:type=Queue,name=primary
```

Với nhiều bean, cần key phân biệt:

```text
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,name=shipping
```

Nhiều Spring `ApplicationContext` trong cùng JVM có thể dùng chung platform MBeanServer, vì vậy naming contract cần xét cả context hoặc application nếu cần.

`MBeanExporter` có chính sách registration như fail, ignore hoặc replace; dùng `REPLACE_EXISTING` để che lỗi xung đột có thể ghi đè MBean của component khác. Nên xác định ownership và đặt tên duy nhất trước.

### Không tạo tên ngẫu nhiên để tránh va chạm

```text
com.example.orders:type=Queue,name=payments-<random-uuid>
```

Tên này tránh trùng trong một lần chạy nhưng làm dashboard và script khó tìm, đồng thời có thể che lỗi lifecycle hoặc MBean bị bỏ lại sau reload. Chọn logical resource identity ổn định thay cho suffix tùy ý.

## 14. Spring proxy và tên class không ổn định

Trong Spring, bean có thể được bọc bằng proxy do transaction, security hoặc AOP. Nếu naming strategy dùng:

```java
managedBean.getClass().getName()
```

thì ObjectName có thể chứa tên proxy thay đổi theo cấu hình hoặc phiên bản.

Ví dụ tên không nên coi là management identity lâu dài:

```text
com.example.orders:type=PaymentQueueManagement$$SpringCGLIB$$0
```

Thay vào đó, sử dụng định danh do ứng dụng định nghĩa:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

Resource type và logical name nên được lấy từ metadata/bean key có hợp đồng ổn định, không từ runtime implementation detail.

## 15. Dùng wildcard query nhưng giữ schema nhất quán

Client không phải lúc nào cũng biết tên từng MBean. JMX hỗ trợ ObjectName pattern:

```text
com.example.orders:type=Queue,*
```

Java:

```java
Set<ObjectName> queues = connection.queryNames(
        new ObjectName("com.example.orders:type=Queue,*"),
        null
);
```

Pattern này tìm các MBean có domain và type phù hợp, cùng các key property khác.

Nếu schema local và remote khác nhau:

```text
Local:  com.example.orders:type=Queue,name=payments
Remote: com.example.orders:type=Queue,application=checkout,name=payments
```

pattern `com.example.orders:type=Queue,*` có thể vẫn tìm được cả hai. Nhưng client cần giá trị `application` để gắn nhãn hoặc truy vấn chính xác có thể bị lỗi khi local thiếu key.

**Wildcard giúp khám phá tài nguyên; nó không thay thế việc giữ naming schema đồng nhất.** Nếu client cần một tập key cố định, mọi exporter phải cung cấp đủ key đó.

## 16. Kiểm thử tính nhất quán của naming strategy

Một bài kiểm thử nên xác nhận cùng dữ liệu đầu vào sinh cùng ObjectName bất kể môi trường.

Ví dụ:

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

ObjectName actual = ManagementNames.queue(
    "checkout",
    "payments"
);

if (!expected.equals(actual)) {
    throw new AssertionError(
        "Unexpected JMX ObjectName: " + actual
    );
}
```

Có thể mở rộng kiểm thử theo các nhóm:

| Kiểm tra | Mục tiêu |
| --- | --- |
| Cùng logical resource | Tên ổn định qua nhiều lần chạy |
| Thứ tự key khác | Vẫn là cùng ObjectName |
| Hai resource khác tên | Không xung đột |
| Hai application trong một server | Có key phân biệt |
| Proxy class khác | ObjectName không thay đổi |
| Đầu vào có ký tự đặc biệt | Không tạo ObjectName sai cú pháp |
| Local và remote | Cùng name schema, chỉ khác connection |
| Application context đóng | MBean được hủy đăng ký đúng lifecycle |

### Kiểm thử registry

Chỉ kiểm thử helper tạo chuỗi chưa đủ. Exporter có thể dùng annotation hoặc explicit mapping thay vì naming strategy dự kiến.

Trong integration test, hãy xác nhận:

```java
ObjectName expected = ManagementNames.queue(
    "checkout",
    "payments"
);

if (!mbeanServer.isRegistered(expected)) {
    throw new AssertionError("Expected MBean not registered");
}
```

`mbeanServer` là MBeanServer đã được cấu hình cho test. Cần kiểm tra không có tên ngoài mong đợi trong domain/phạm vi của ứng dụng.

## 17. Một quy trình chẩn đoán khi local chạy nhưng remote không tìm thấy

Giả sử client remote ném `InstanceNotFoundException` khi đọc:

```text
com.example.orders:type=Queue,name=payments
```

Quy trình điều tra:

1. **Xác nhận kết nối:** Remote client có kết nối tới JVM chính xác không?
2. **Xác nhận target:** Cluster, host, PID và JMX connector có trỏ tới đúng instance không?
3. **Liệt kê domain:** Query `com.example.orders:*` để xem các ObjectName thực tế.
4. **So sánh canonical names:** Kiểm tra key `application`, `name`, `type` và domain.
5. **Kiểm tra exporter:** Spring đang dùng metadata naming, key naming hay custom strategy?
6. **Kiểm tra cấu hình:** Có biến môi trường/properties nào làm thay đổi domain hoặc logical name không?
7. **Kiểm tra lifecycle:** Bean có đăng ký thành công hay đã bị unregister?
8. **Kiểm tra quyền:** Remote client có quyền query/read MBean đó không?
9. **Sửa tại nguồn:** Đồng bộ schema naming và hợp đồng client, không tự động fallback sang một MBean gần giống có thể thuộc tài nguyên khác.

Nếu remote không kết nối được ngay từ đầu, lỗi nằm ở transport/security; đừng nhầm với lỗi tên JMX.

## 18. Spring Boot, Actuator và namespace quản trị

Spring Boot có thể expose MBean của ứng dụng và Actuator qua JMX tùy cấu hình và dependency. Các endpoint quản trị có thể dùng domain và naming convention riêng.

Khi kết hợp:

- Không tự ý đặt custom MBean trùng ObjectName của framework/Actuator.
- Xác định rõ domain của MBean ứng dụng.
- Kiểm tra domain thực tế trong `MBeanServer`.
- Phân biệt setting bật JMX với setting đặt tên MBean.
- Nếu dùng một namespace chung, định nghĩa quy ước phân biệt `type`, `application` và `name`.

Không nên giả định naming strategy của `MBeanExporter` tùy chỉnh tự áp dụng cho mọi MBean do Boot, JVM hoặc thư viện khác tạo.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Local tìm thấy, remote báo `InstanceNotFoundException` | ObjectName khác hoặc sai JVM | Query domain và so canonical names |
| Remote không kết nối được | JMX RMI host/port, firewall, authentication/TLS | Kiểm tra transport trước |
| Dashboard mất metric sau release | Đổi domain, type, application hoặc name | Giữ naming contract ổn định |
| Có nhiều MBean cùng loại | Chỉ dùng `type` làm key | Thêm logical `name` |
| MBean bị đăng ký trùng | Nhiều bean/context dùng cùng ObjectName | Tách ownership và key định danh |
| Tên chứa proxy class | Naming theo runtime class | Dùng resource type ổn định |
| Local có ít key hơn production | Config môi trường tạo các schema khác nhau | Chuẩn hóa các key bắt buộc |
| Query wildcard được nhưng exact lookup lỗi | Schema không đồng nhất | Đối chiếu full ObjectName |
| Client remote đọc nhầm instance | Không gắn target label | Tách target identity khỏi MBean identity |
| ObjectName có ký tự lạ | Ghép trực tiếp dữ liệu không escape | Validate/quote property values |

## 20. Những nguyên tắc thiết kế thực tế

### 20.1. Định nghĩa schema chung cho mọi exporter

Nếu các module dùng `type`, `application`, `name`, hãy dùng cùng cách viết hoa key, ý nghĩa và quy tắc value. Domain phân theo tổ chức và subsystem cần được tài liệu hóa.

### 20.2. Giữ logical name ổn định

Một cache `products` nên vẫn có tên `products` dù chuyển từ Java class A sang class B, thay proxy hay đổi cấu hình deployment. Client giám sát thường quan tâm logical resource, không quan tâm tên class.

### 20.3. Bảo đảm ownership trong mỗi JVM

Nếu nhiều Spring context cùng dùng platform MBeanServer, cần định rõ exporter/context nào đăng ký MBean nào. Nếu thực sự cần export nhiều instance giống nhau, bổ sung key phân biệt có ý nghĩa.

### 20.4. Tách định tuyến kết nối khỏi naming

`JMXServiceURL`, host và port cho biết **kết nối tới đâu**. ObjectName cho biết **truy cập đối tượng nào trong server đó**. Hai khái niệm không nên trộn lẫn.

### 20.5. Đối chiếu registry, không chỉ cấu hình

Một naming strategy có thể đúng nhưng exporter không gọi tới nó do explicit name, annotation hoặc bean không được export. Luôn xác nhận ObjectName thực tế bằng `queryNames` hoặc JConsole.

### 20.6. Tương thích với client cũ

Đổi ObjectName có thể là breaking change cho dashboard và script. Nếu cần đổi schema, có thể hỗ trợ giai đoạn chuyển tiếp bằng cách cập nhật client và giám sát trước; tránh đăng ký hai MBean cùng điều khiển một resource nếu điều đó tạo nhầm lẫn hoặc thao tác trùng.

## 21. Bài tập thực hành

Tạo hai ứng dụng Spring hoặc hai JVM mô phỏng local và remote, cùng xuất một queue quản trị tên `payments`.

**Yêu cầu:**

1. Dùng domain `com.example.orders`.
2. Dùng key `type=Queue`, `application=checkout`, `name=payments`.
3. Bean business được quản lý trong Spring context.
4. Cấu hình exporter với naming strategy hoặc ObjectName tường minh phù hợp.
5. Dùng JConsole hoặc client JMX local đọc `PendingCount`.
6. Bật JMX remote trong môi trường thực hành được bảo vệ và kết nối tới JVM kia.
7. Dùng cùng ObjectName để đọc `PendingCount` ở JVM remote.
8. So sánh `getCanonicalName()` của hai ObjectName.
9. Thử đổi `application=inventory` ở client, quan sát exact lookup không còn trỏ tới MBean ban đầu.
10. Query theo pattern `com.example.orders:type=Queue,*` và kiểm tra key thực tế.

**Kỳ vọng:** các JVM có thể cùng ObjectName nhưng giá trị PendingCount có thể khác; client phân biệt giá trị bằng thông tin target/JVM.

## 22. Câu hỏi tự kiểm tra

**1. Cùng một ObjectName ở hai JVM có gây xung đột không?**

Thông thường không. ObjectName cần duy nhất trong từng MBeanServer. Hệ thống giám sát cần thêm target identity để phân biệt JVM.

**2. Host/port JMX remote có nên nằm trong ObjectName không?**

Thường không. Host/port thuộc connection configuration và có thể thay đổi theo deployment.

**3. Thứ tự key property có ảnh hưởng ObjectName equality không?**

Không. Dùng `ObjectName.equals` hoặc canonical name để so sánh.

**4. Vì sao naming theo class proxy không bền vững?**

Proxy class có thể thay đổi theo AOP/configuration; logical resource type giữ hợp đồng ổn định hơn.

**5. Cùng query wildcard có đủ bảo đảm naming nhất quán không?**

Không. Wildcard có thể tìm được các MBean thiếu key, nhưng client exact lookup hoặc schema validation vẫn thất bại.

**6. Khi remote client không thấy MBean, nên làm gì trước?**

Xác nhận kết nối đúng JVM, query registry thực tế rồi so ObjectName. Phân biệt lỗi transport với lỗi naming.

**7. Annotation objectName và custom naming strategy có thể mâu thuẫn không?**

Có thể, tùy exporter và nguồn metadata được ưu tiên. Cần thống nhất nguồn đặt tên và kiểm tra MBean đã đăng ký.

**8. Có cần `instance` key cho mọi replica không?**

Không bắt buộc nếu mỗi replica có MBeanServer riêng. Collector có thể gắn nhãn instance ở tầng thu thập.

## 23. Tổng kết

Để giữ tên MBean nhất quán giữa local và remote, cần định nghĩa **một hợp đồng ObjectName ổn định** gồm domain và key properties có ý nghĩa nghiệp vụ. Spring `ObjectNamingStrategy`, explicit exporter mapping hoặc annotation đều có thể tạo tên, nhưng phải được cấu hình theo cùng schema.

Hãy nhớ hai tầng:

```text
JMX connection: host / port / credentials / TLS / target JVM
JMX identity:   domain + key properties của ObjectName
```

Khi local và remote dùng cùng schema ObjectName, script và dashboard dễ tái sử dụng; khi cùng tên tồn tại ở nhiều JVM, hệ thống giám sát phân biệt bằng target identity. Cuối cùng, luôn xác nhận **canonical ObjectName thực tế từ MBeanServer**, vì đó là tên mà JMX client thật sự truy vấn.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `ObjectNamingStrategy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Java SE API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — `JMXConnectorFactory`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
