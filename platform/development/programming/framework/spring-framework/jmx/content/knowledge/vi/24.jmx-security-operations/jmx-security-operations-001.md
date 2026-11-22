# Rủi ro của JMX remote không xác thực

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích JMX remote là gì và vì sao nó khác với JMX local qua `MBeanServer` trong cùng JVM.
- Nhận diện hậu quả khi mở Java Management Extensions (JMX) remote mà không yêu cầu xác thực hoặc không giới hạn nguồn kết nối.
- Phân biệt **authentication**, **authorization**, **encryption**, **network isolation** và **audit**: mỗi tầng giải quyết một nhóm rủi ro khác nhau.
- Hiểu MBeans có thể công bố **attributes**, **operations** và **notifications**; một số operation có thể thay đổi trạng thái ứng dụng.
- Đánh giá bề mặt tấn công của JMX/RMI, bao gồm cổng registry, cổng RMI server, host được công bố, firewall và container networking.
- Lập cấu hình vận hành an toàn theo nguyên tắc mặc định không mở remote, chỉ bật khi có nhu cầu, bắt buộc kiểm soát quyền truy cập và bảo vệ transport.
- Thực hiện kiểm tra cấu hình và kết nối trong môi trường được cấp phép, không quét hoặc khai thác hệ thống không thuộc quyền quản lý.
- Phân tích sự khác biệt giữa Spring custom MBeans, Actuator JMX endpoints và JVM platform MBeans.

## 2. Bối cảnh: JMX dùng để quản lý, không chỉ để đọc số liệu

Một ứng dụng Java thường có `MBeanServer` để cung cấp thông tin về JVM và những MBeans do ứng dụng/thư viện đăng ký.

Ví dụ:

```text
java.lang:type=Memory
java.lang:type=Threading
com.example.shop.orders:type=QueueMonitor,name=outbox
```

Các MBeans có thể cung cấp:

- **Attributes**: số thread, heap usage, queue depth, trạng thái cache, cấu hình.
- **Operations**: reset counters, thay đổi log level, clear cache, pause/resume worker, chạy tác vụ quản trị.
- **Notifications**: thông báo sự kiện như threshold exceeded hoặc thay đổi trạng thái.

Trong cùng JVM, code có thể gọi `ManagementFactory.getPlatformMBeanServer()`. Đó là JMX local. Khi bật **JMX remote**, client từ process/máy khác có thể truy cập qua connector (thường JMX/RMI). Lúc này MBeanServer trở thành một **management interface qua mạng**.

Ví dụ kiến trúc:

```text
                 JVM ứng dụng
          +--------------------------+
          |  MBeanServer             |
          |    |                     |
          |    +-- Platform MBeans   |
          |    +-- Library MBeans    |
          |    +-- Custom MBeans     |
          +-----------+--------------+
                      |
                JMX remote connector
                      |
                 Network boundary
                      |
               JConsole / client
```

Nếu client bên ngoài có thể kết nối mà **không chứng minh danh tính**, ứng dụng đã trao quyền quan sát và có thể cả quyền điều khiển cho bất kỳ bên nào tiếp cận được connector theo chính sách hiện hành.

**Thông điệp chính:** JMX remote là một bề mặt **quản trị đặc quyền**, không nên được đối xử như endpoint metrics công khai chỉ đọc.

## 3. “Không xác thực” nghĩa là gì?

Một cấu hình JMX remote **không xác thực** cho phép client kết nối mà không phải cung cấp danh tính/credentials được server xác minh.

Ví dụ cấu hình JVM thường được dùng trong demo nhưng nguy hiểm nếu đưa vào môi trường có mạng không tin cậy:

```properties
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

Các dòng trên chỉ nhằm minh họa **cấu hình không nên dùng cho remote production**. Không áp dụng chúng lên máy thật. Việc không xác thực và không dùng TLS đồng thời làm tăng rủi ro từ truy cập trái phép và nghe lén/thao túng lưu lượng.

Mức độ phơi lộ thực tế còn phụ thuộc:

- Connector đang bind vào địa chỉ nào.
- Cổng có được firewall/network policy cho phép không.
- Có reverse tunnel hoặc VPN giới hạn khách truy cập hay không.
- RMI stub công bố host/port nào.
- Container/orchestrator có publish port ra ngoài hay không.
- Hệ thống có MBeans nào và operations nào được expose.

Không nên suy luận rằng chỉ vì một JVM có JMX thì nó tự mở Internet. Rủi ro trọng tâm là **remote connector được mở và có thể truy cập mà thiếu kiểm soát tương ứng**.

## 4. Rủi ro 1: đọc thông tin vận hành nhạy cảm

Một số MBeans công bố trạng thái hữu ích để debug nhưng cũng hữu ích cho người truy cập không được phép:

- JVM version và runtime properties.
- Thông tin về class loading, thread counts, heap/GC.
- Một số system properties hoặc environment-derived values, tùy MBean.
- Tên dịch vụ, module, pool, datasource hoặc dependency.
- ObjectName và cấu trúc nội bộ của thành phần.
- Thông tin cấu hình được custom MBeans công bố.

Một custom MBean thiết kế kém có thể để lộ access token, password, API key, full database URL kèm credentials, session identifiers hoặc dữ liệu khách hàng.

Ví dụ **không nên làm**:

```java
@ManagedAttribute
public String getDatabasePassword() {
    return credentials.password();
}
```

JMX annotations không tự áp dụng bộ lọc bảo mật cho mọi thuộc tính. Nếu một client được phép đọc, các attributes có thể xuất hiện qua JConsole/SDK và có thể bị thu thập ngoài dự kiến.

Cách thiết kế tốt hơn là chỉ công bố những thông tin cần cho vận hành:

```java
@ManagedAttribute
public boolean isDatabaseConnected() {
    return connectionHealthSnapshot.isConnected();
}
```

Vẫn cần đánh giá getter có gây I/O hay tiết lộ chi tiết không cần thiết; một status flag ngắn thường phù hợp hơn raw secrets.

## 5. Rủi ro 2: gọi operations gây thay đổi trạng thái

Không phải mọi MBean đều chỉ đọc. JMX operations có thể thực hiện những hành động quản trị được ứng dụng hoặc thư viện cung cấp.

Ví dụ custom MBean:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=QueueControl,name=outbox")
public class QueueControlManagement {

    @ManagedOperation
    public void pauseConsumers() {
        // Dừng việc nhận thêm jobs.
    }

    @ManagedOperation
    public void clearInMemoryCache() {
        // Xóa cache dùng cho hiệu năng.
    }
}
```

Một người có quyền gọi operation có thể gây:

- Ngừng xử lý hàng đợi hoặc giảm throughput.
- Xóa cache và tạo tải database đột ngột.
- Reset diagnostic counters, làm gián đoạn monitoring.
- Thay đổi cấu hình động hoặc logging settings.
- Kích hoạt thao tác nghiệp vụ không được thiết kế như API công khai.

Ở một số môi trường, các MBeans khác còn có operations nhạy cảm hơn. Không giả định remote JMX là read-only chỉ vì client thông thường chỉ dùng nó để xem metrics.

**Bài học:** Đánh giá operation surface và quyền từng operation, không chỉ đánh giá cổng đã mở.

## 6. Rủi ro 3: tăng khả năng gián đoạn dịch vụ

Ngay cả khi client chỉ đọc, truy cập JMX cũng có thể tiêu tốn tài nguyên:

- Getter thực hiện SQL hoặc HTTP call mỗi lần đọc.
- Getter duyệt collection lớn, tạo allocations hoặc lock contention.
- Query hàng loạt MBeans gây CPU/memory overhead.
- Client gọi operation quản trị liên tục.
- Nhiều kết nối hoặc listeners gây tải lên connector và application.
- Notification quá nhiều dẫn đến backlog hoặc event storm.

Ví dụ getter đắt đỏ:

```java
@ManagedAttribute
public long getPendingOrders() {
    return repository.countPendingOrders();
}
```

Nếu nhiều client không được xác thực có thể polling method đó, chúng có thể làm tăng tần suất truy vấn DB. Trong sự cố, chính lớp quan sát có thể làm tình trạng nghẽn nặng hơn.

Thiết kế getter nên ưu tiên snapshot hoặc counter in-memory:

```java
@ManagedAttribute
public long getPendingOrders() {
    return pendingSnapshot.get();
}
```

Đồng thời áp dụng network access controls, giới hạn quyền thao tác và giám sát chính connector để giảm abuse.

## 7. Rủi ro 4: thông tin và dữ liệu truyền không được bảo vệ

Authentication trả lời câu hỏi **ai đang kết nối?** Encryption trả lời câu hỏi **dữ liệu có bị quan sát/chỉnh sửa trên đường truyền không?**

Một kết nối JMX/RMI không có TLS có thể có nguy cơ bị nghe lén hoặc can thiệp trên mạng không tin cậy, kể cả khi có mật khẩu ở một cơ chế authentication. Do đó **bật authentication không thay thế TLS**.

Bảng phân biệt:

| Biện pháp | Giải quyết | Không tự giải quyết |
|---|---|---|
| Authentication | Xác minh danh tính client | Không mã hóa traffic |
| Authorization | Giới hạn actions theo danh tính/quyền | Không tự mã hóa traffic |
| TLS | Bảo mật kênh truyền và hỗ trợ xác thực peer khi cấu hình | Không quyết định operations được phép |
| Firewall/network policy | Giới hạn nguồn có thể kết nối | Không xác minh danh tính ở cấp ứng dụng |
| VPN/tunnel | Tạo đường truy cập có kiểm soát | Không thay thế policy quyền trên MBean |
| Audit | Ghi nhận hành vi quản trị | Không tự ngăn truy cập trái phép |

Một hệ thống có thể có network private nhưng vẫn không nên coi private network là tuyệt đối đáng tin. Misconfiguration, compromised workloads và lateral movement là những rủi ro cần tính đến.

## 8. Rủi ro 5: bề mặt Java serialization và RMI

JMX remote thường chạy qua JMX/RMI. Một số giao thức Java remote sử dụng serialization để trao đổi đối tượng hoặc thông tin lời gọi. Đây là bề mặt cần quản lý cẩn thận:

- Sử dụng JDK được vá và cập nhật.
- Giới hạn nguồn có thể kết nối.
- Kiểm soát authentication/authorization.
- Dùng TLS hoặc transport được bảo vệ theo yêu cầu deployment.
- Tránh đưa custom DTO/class graph lớn không cần thiết qua remote JMX.
- Cân nhắc serialization filtering/allowlisting thích hợp theo JDK và connector.
- Hạn chế mở remote connector trên môi trường không tin cậy.

Rủi ro không chỉ đến từ một method cụ thể. Các phiên bản Java/JMX implementations, classpath và cấu hình bảo mật khác nhau có các đặc tính và giới hạn khác nhau. Vì vậy phải tham khảo hướng dẫn security của JDK/version đang dùng thay vì áp dụng một checklist tùy ý cho mọi phiên bản.

**Không nên** dùng Java serialization hoặc remote MBeans để công bố tùy tiện JPA entities, full object graphs hoặc thông tin bí mật.

## 9. JMX/RMI có thể dùng nhiều cổng

Một sai lầm vận hành thường gặp là nghĩ rằng đặt:

```properties
-Dcom.sun.management.jmxremote.port=9010
```

thì firewall chỉ cần xử lý đúng một kết nối TCP duy nhất trong mọi cấu hình.

Trong JMX/RMI, có thể có:

1. Cổng RMI registry/connector discovery.
2. Cổng RMI server phục vụ lời gọi thực tế.
3. Host/IP được công bố trong RMI stub mà client sử dụng để kết nối.

Nếu RMI server chọn cổng động, connection có thể thất bại qua firewall/NAT hoặc container dù cổng registry mở.

Ví dụ các thuộc tính JVM liên quan đến deployment:

```properties
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.internal.example
```

Đây là **minh họa thiết kế networking**, không phải cấu hình production hoàn chỉnh. Các cổng/host phải được gán theo policy nội bộ, và cần kiểm soát xác thực/TLS/network. Chỉ cấu hình cổng cố định không làm kết nối an toàn hơn nếu chúng vẫn được public không xác thực.

Một điểm đặc biệt của container: `java.rmi.server.hostname` cần phù hợp với địa chỉ mà client thực sự định tuyến được. Bind address, advertised hostname, Kubernetes Service/NAT và firewall có thể cần xử lý riêng.

## 10. Tại sao expose cổng trong Docker/Kubernetes cần thận trọng?

Trong container, có các ranh giới:

```text
JVM inside container
        |
        v
Container network interface
        |
        v
Pod / Docker networking
        |
        v
Kubernetes Service / published port
        |
        v
Cluster network / external network
```

Chỉ vì JVM lắng nghe trong container không nhất thiết có nghĩa Internet truy cập được. Nhưng nếu dùng:

- Docker `-p` publish ra host interface rộng.
- Kubernetes `NodePort` hoặc `LoadBalancer`.
- Network policy cho phép traffic rộng.
- Security group cho phép nhiều nguồn.
- Port forwarding không có kiểm soát.

thì remote JMX có thể trở thành bề mặt truy cập vượt dự kiến.

**Nguyên tắc:** Không publish JMX remote trực tiếp ra Internet. Nếu cần truy cập tạm thời cho debugging, dùng đường quản trị đã được xác thực/ủy quyền, giới hạn nguồn và thời gian, đồng thời vẫn đánh giá security của connector.

Đừng coi `localhost` trong container là `localhost` trên máy người vận hành. Network namespace khiến cách kết nối phải được thiết kế rõ.

## 11. JMX local không đồng nghĩa với remote JMX đã bật

Ứng dụng Spring hoặc Java có thể đăng ký MBeans vào:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

Điều đó chưa chứng minh một remote connector đã được mở.

Tương tự:

```yaml
spring:
  jmx:
    enabled: true
```

thường liên quan đến Spring JMX integration/export tùy phiên bản Spring Boot, nhưng **không tự là cấu hình mở remote RMI port** với authentication, TLS và mạng.

Tách ba trạng thái:

1. MBean đã được đăng ký trong JVM.
2. Một connector có thể cung cấp MBeanServer ra process khác.
3. Connector có thể được tiếp cận qua network và có chính sách bảo mật cụ thể.

Nhầm lẫn ba trạng thái có thể gây cả false alarm (“JMX local đang bật nên Internet nguy hiểm”) lẫn false security (“Chỉ bật spring.jmx.enabled, chắc chưa có đường remote nào”).

## 12. Actuator JMX exposure khác custom MBeans

Trong Spring Boot, Actuator endpoints có thể được expose qua JMX theo cấu hình như:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

Cấu hình này liên quan **Actuator endpoints qua JMX**. Nó không phải là ACL áp dụng cho toàn bộ JVM platform MBeans hoặc custom Spring `@ManagedResource` beans.

Những nguồn MBean có thể cùng tồn tại:

| Nguồn | Ví dụ | Ai kiểm soát registration/exposure? |
|---|---|---|
| JVM platform | `java.lang:type=Memory` | Java runtime/JMX facilities |
| Custom Spring MBean | `com.example.shop:type=Cache,name=products` | Spring `MBeanExporter`/annotation config |
| Library MBean | Connection pool, scheduler MBean | Thư viện/component |
| Actuator JMX endpoint | Health/metrics JMX endpoint | Spring Boot Actuator JMX infrastructure |

Nếu mở JMX remote connector tới một MBeanServer, những MBeans có trong server đó có thể trở thành management surface cho client tùy quyền. Đừng nghĩ rằng `management.endpoints.jmx.exposure.include=health` làm mọi MBean còn lại biến mất.

## 13. Các nguyên tắc an toàn khi thiết kế remote JMX

Có thể sắp xếp biện pháp theo mức ưu tiên:

### 13.1. Mặc định không mở remote

Chỉ bật remote JMX nếu có use case thực sự: kiểm tra JVM bằng JConsole/JMC, thu thập metric qua JMX, điều tra sự cố cần MBean metadata hoặc operation.

Nếu metrics đã được thu thập qua Micrometer/Prometheus endpoint có authentication/network controls, không nhất thiết phải mở remote JMX cho mọi instance.

### 13.2. Giới hạn network reachability

Giới hạn nguồn kết nối bằng firewall, security group, Kubernetes NetworkPolicy, private subnet hoặc đường quản trị tương đương. Tránh expose trực tiếp ra public Internet.

### 13.3. Bật authentication phù hợp

Dùng JMX authentication hoặc cơ chế xác thực được tổ chức hỗ trợ. Credentials phải được quản lý như secrets, có rotation và không hardcode trong repository hoặc command output không được bảo vệ.

### 13.4. Bảo vệ transport

Dùng TLS hoặc một đường truyền quản trị được mã hóa theo threat model. Không tắt TLS chỉ vì “chạy trong VPC”.

### 13.5. Authorization/least privilege

Giới hạn người dùng nào có quyền gọi operations. Với môi trường cần read-only monitoring, ưu tiên quyền chỉ đọc hoặc công cụ exporter được thiết kế để thu thập những attributes cần thiết, thay vì cho mọi collector quyền quản trị toàn MBeanServer.

### 13.6. Thu hẹp management surface

Không export operations gây side effect nếu không thật sự cần. Không công bố secrets hoặc thông tin nhạy cảm qua attributes.

### 13.7. Audit và phát hiện truy cập bất thường

Theo dõi kết nối quản trị, thay đổi cấu hình, operations quan trọng và thay đổi registration. Mức độ audit thực tế phụ thuộc connector, platform và cơ chế proxy trung gian; không giả định JMX tự ghi mọi `invoke()` vào audit log.

## 14. Ví dụ cấu hình được bảo vệ: cách tư duy

Ví dụ dưới minh họa **các thành phần cần kiểm soát**, không phải chỉ dẫn copy-paste một remote configuration hoàn chỉnh:

```text
JMX remote enabled:         Chỉ khi có nhu cầu
Network binding:            Private management interface
Firewall allowlist:         Chỉ monitoring/bastion
Authentication:             Enabled
Authorization:              Least privilege
Transport:                  TLS / approved encrypted tunnel
Credentials:                Secret manager / protected deployment
RMI ports/hostname:         Deterministic, reachable only by approved clients
Audit:                      Record privileged operations where feasible
```

Trong một triển khai dùng JVM built-in management agent, các system properties liên quan có thể bao gồm:

```properties
-Dcom.sun.management.jmxremote.port=<management-port>
-Dcom.sun.management.jmxremote.rmi.port=<rmi-port>
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
```

Các placeholder cần được thay bằng cấu hình hợp lệ nếu thực sự triển khai. Bật `authenticate=true` và `ssl=true` **chưa đủ**: cần cung cấp password/access files hoặc security realm tương ứng, key/trust material cho TLS nếu yêu cầu, file permissions chính xác và client configuration. Các chi tiết phụ thuộc JDK/connector.

Không khuyến nghị ghi secrets thật vào ví dụ hoặc đưa cấu hình chưa được kiểm tra trực tiếp lên production.

## 15. Quản lý file mật khẩu và access control

JDK built-in JMX remote agent có thể hỗ trợ file password và access control với các cấu hình tương ứng (tùy JDK).

Các ý cần lưu ý:

- Password file chứa thông tin bí mật và phải được bảo vệ bằng filesystem permissions nghiêm ngặt.
- Không commit file credentials thật vào Git.
- Không in password vào startup logs hoặc process arguments nếu có cách tránh.
- Rotate credentials định kỳ và khi nghi ngờ lộ.
- Phân biệt role chỉ đọc và role có quyền ghi/execute operations theo khả năng access model.
- Kiểm tra security policy khi container image hoặc OS thay đổi.
- Dùng secret management của deployment platform thay vì copy thủ công khó kiểm soát.

Một file permission quá rộng có thể khiến JVM từ chối khởi động remote agent hoặc tạo rủi ro lộ credentials, tùy implementation. Vì vậy cần theo dõi startup logs và chạy phép kiểm tra kết nối sau deployment.

## 16. Authorization: vì sao chỉ xác thực chưa đủ?

Giả sử có hai đối tượng:

1. Monitoring collector chỉ cần đọc `ThreadCount`, `HeapMemoryUsage`, `PendingCount`.
2. Operator có nhiệm vụ thay đổi log level hoặc chạy một maintenance operation.

Nếu cả hai dùng chung credentials có quyền quản trị toàn bộ MBeans, monitoring collector bị compromise có thể trở thành đường điều khiển ứng dụng.

Thiết kế tốt hơn:

- Monitoring principal: read-only khi connector/authorization hỗ trợ.
- Operator principal: quyền cao hơn có kiểm soát, audit và quy trình chấp thuận.
- Không chia sẻ credentials giữa các ứng dụng/team.
- Không dùng quyền admin cho script chỉ đọc metric.
- Kiểm tra custom MBeans có tự triển khai thêm bảo vệ operation quan trọng hay không.

Không nên nhầm **JMX access file readwrite** với một hệ thống RBAC chi tiết tự động áp dụng tới từng method theo business roles. Nếu cần chính sách phân quyền phức tạp, phải thiết kế ở tầng thích hợp, không chỉ dựa vào role name.

## 17. Đánh giá custom MBeans trước khi cho phép remote

Khi một class có:

```java
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class QueueManagement {
    @ManagedAttribute
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedOperation
    public void pauseConsumers() {
        consumerControl.pause();
    }
}
```

hãy tự hỏi:

1. `PendingCount` có phải thông tin an toàn để công bố tới monitoring principal không?
2. Getter có nhẹ và không gây truy vấn/side effect không?
3. `pauseConsumers()` có làm gián đoạn quy trình xử lý đơn hàng không?
4. Có cần operation đó trong production không?
5. Ai được quyền thực hiện, và hành động có được audit không?
6. Có cơ chế khôi phục khi operation thất bại giữa chừng không?
7. Nếu nhiều replicas, thao tác này chỉ áp dụng JVM local hay toàn cluster?
8. ObjectName có vô tình chứa dữ liệu nhạy cảm không?

Nếu client chỉ cần metric, có thể tách `QueueMetricsMBean` chỉ đọc và `QueueControlMBean` dành cho vận hành, nhưng vẫn cần access controls trên cùng connector/server; chỉ tách tên MBean không tự chặn caller không được phép.

## 18. Kiểm tra exposure trong JVM được cấp phép

Các bước chẩn đoán hợp lệ trên ứng dụng mà bạn quản lý:

### 18.1. Xem cấu hình JVM và deployment

Kiểm tra runtime flags và deployment manifests để xác định remote agent có được bật hay không. Không nên chỉ dựa vào source `application.yml`, vì JMX remote có thể được bật qua JVM options hoặc platform scripts.

### 18.2. Xem process đang lắng nghe

Dùng công cụ OS/platform approved để biết các cổng quản trị có được bind trên interface dự kiến. Kiểm tra cả RMI registry và RMI server port, nếu cấu hình dùng hai cổng.

### 18.3. Thử kết nối từ vị trí quản trị được ủy quyền

Sử dụng JConsole/JMC với credentials hợp lệ, kênh mã hóa phù hợp và network allowlist. Xác nhận các client không được cấp quyền bị từ chối.

### 18.4. Kiểm tra MBeanInfo và operation surface

Kết nối bằng principal phù hợp và liệt kê metadata MBean mà client được phép truy cập. Không gọi operation có side effect chỉ để kiểm tra security trên production; dùng test MBean hoặc môi trường staging.

### 18.5. Theo dõi logs và monitoring

Xác nhận sự kiện authentication failure hoặc cảnh báo network có thể được quan sát theo cơ chế platform. Không mặc định mọi JMX access đều có audit event chi tiết nếu chưa triển khai.

## 19. Ví dụ kiểm tra MBeans local mà không mở remote connector

Nếu chỉ cần debug trong cùng JVM, có thể đọc platform MBeanServer trực tiếp:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalJmxInspection {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "java.lang:type=Threading");

        Object count = server.getAttribute(
                name,
                "ThreadCount");

        System.out.println("ThreadCount: " + count);
    }
}
```

Đoạn code này chạy trong cùng JVM và không yêu cầu cấu hình `com.sun.management.jmxremote.port`. Nó chứng minh rằng **JMX local access** và **network JMX remote access** là hai khả năng khác nhau.

Nếu có thể đạt mục tiêu bằng JMX local, in-process diagnostics hoặc một metrics exporter đã được bảo vệ, hãy cân nhắc không mở thêm bề mặt remote JMX.

## 20. Remote JMX có giống HTTP Actuator không?

Không. Spring Boot Actuator có thể expose endpoints qua HTTP và JMX, nhưng hai technology khác nhau:

| Khía cạnh | HTTP Actuator | JMX remote |
|---|---|---|
| Địa chỉ | HTTP URL/path và management port | JMX service URL/RMI connector |
| Danh tính | HTTP authentication/security chain | JMX connector authentication/authorization |
| Transport | HTTP hoặc HTTPS | JMX/RMI hoặc connector khác |
| Content | Actuator web endpoints | MBeans trên MBeanServer theo quyền |
| Network | Web server/proxy | JMX remote ports/hostname |
| Nguy cơ | Lộ diagnostics/config/operations qua HTTP | Lộ JVM/MBeans và operations qua JMX |
| Kiểm soát exposure | `management.endpoints.web.exposure.*` | JMX endpoint config + remote connector controls |

`management.endpoints.jmx.exposure.include` chỉ chọn **Actuator endpoints qua JMX**, không phải firewall cho toàn bộ MBeanServer. Việc `/actuator/health` được bảo vệ bằng Spring Security không tự bảo vệ JMX remote RMI connector.

Đừng trộn auth của HTTP với auth của JMX: chúng thường đi qua các hạ tầng khác nhau.

## 21. Kịch bản rủi ro minh họa

### Kịch bản A: thử nghiệm local được đưa nguyên lên production

Developer cấu hình remote JMX không authentication và TLS để JConsole kết nối tiện. Deployment sau đó publish cùng port trên network cho nhiều workloads.

**Rủi ro:** Người không được phép truy cập network có thể quan sát MBeans và có khả năng gọi operations.

**Giải pháp:** Tắt remote khi không cần; nếu cần thì dùng auth, transport protection và allowlist; kiểm tra đường public exposure trong pipeline deployment.

### Kịch bản B: metrics collector được cấp admin credential

Collector chỉ đọc số liệu, nhưng dùng credentials quyền readwrite.

**Rủi ro:** Nếu collector bị compromise, credentials có thể được dùng để gọi operations.

**Giải pháp:** Principal chỉ đọc, secret scoping và rotate; không dùng chung credentials vận hành.

### Kịch bản C: custom MBean trả về thông tin cấu hình nhạy cảm

Ứng dụng expose `getConfiguration()` trả nguyên Map có secrets.

**Rủi ro:** Dữ liệu nhạy cảm có thể được đọc bởi principal có quyền JMX hoặc client remote không xác thực.

**Giải pháp:** Thiết kế getter trả trạng thái tổng hợp đã loại bỏ secrets, hạn chế role và kiểm tra metadata.

### Kịch bản D: JMX/RMI không kết nối qua firewall

Cổng registry mở nhưng RMI server cổng động bị chặn, nên team tạm mở dải cổng rất rộng.

**Rủi ro:** Mở rộng network attack surface ngoài nhu cầu.

**Giải pháp:** Cấu hình cổng server xác định, advertised hostname hợp lệ và firewall allowlist hẹp; vẫn bật authentication/TLS.

### Kịch bản E: operation reset không được audit

JMX client có quyền gọi `resetStatistics()`, khiến dashboard mất dữ liệu nhưng không ai biết caller.

**Rủi ro:** Sự cố khó truy vết và khó phân định trách nhiệm.

**Giải pháp:** Có audit ở management adapter hoặc gateway/connector theo thiết kế, identity riêng và policy vận hành rõ.

## 22. Checklist triển khai an toàn

### Trước khi bật remote

- [ ] Có use case cần remote JMX được mô tả rõ.
- [ ] Đã xác định đúng JVM và các MBeanServer liên quan.
- [ ] ObjectNames và operations được review theo quyền.
- [ ] Không có getter tiết lộ secrets hoặc dữ liệu khách hàng.
- [ ] Remote bind vào interface quản trị được phép.
- [ ] Firewall/network policy chỉ cho các nguồn được duyệt.
- [ ] Authentication được bật và credentials được bảo vệ.
- [ ] Encryption/TLS hoặc đường truyền bảo vệ phù hợp đã được cấu hình.
- [ ] RMI registry/server ports và advertised hostname được kiểm soát.
- [ ] JDK/connector được cập nhật và xem xét serialization security.
- [ ] Monitoring principal không có quyền ghi nếu chỉ cần đọc.
- [ ] Có logging/audit phù hợp cho privileged operations.
- [ ] Đã thử kết nối hợp lệ và từ chối kết nối không hợp lệ trên môi trường kiểm thử.
- [ ] Có quy trình tắt remote JMX khi không còn nhu cầu.

### Sau khi bật

- [ ] Kiểm tra lại trạng thái port exposure từ network boundary dự kiến.
- [ ] Theo dõi connector health và authentication failures nếu hỗ trợ.
- [ ] Đánh giá tác động của JMX polling lên CPU, DB và application threads.
- [ ] Kiểm tra credentials expiry/rotation.
- [ ] Định kỳ soát lại MBeans và operations mới sau deploy.
- [ ] Không mở rộng network access tạm thời thành cấu hình thường trực.

## 23. Những lỗi nhận thức thường gặp

| Nhận định | Thực tế |
|---|---|
| “JMX chỉ có metrics, nên không nguy hiểm.” | JMX còn có operations và dữ liệu cấu hình |
| “Không có password nhưng chạy trong VPC nên an toàn.” | Private network không thay thế authentication |
| “Bật authentication là không cần TLS.” | Credentials/dữ liệu vẫn cần bảo vệ transport |
| “Spring Security HTTP bảo vệ cả JMX RMI.” | JMX connector có security boundary riêng |
| “`spring.jmx.enabled=true` mở remote JMX.” | JMX export khác remote connector |
| “JMX không có remote port thì không có MBeans.” | Local MBeanServer vẫn có thể hoạt động |
| “Chỉ mở registry port là đủ.” | RMI server/advertised hostname có thể cần cấu hình riêng |
| “`management.endpoints.jmx.exposure` lọc tất cả MBeans.” | Nó chủ yếu điều khiển Actuator JMX endpoints |
| “JMX role readwrite là quyền nhỏ.” | Quyền đó có thể cho phép operations trên nhiều MBeans |
| “Chỉ cần kiểm tra port một lần.” | Deployment/config changes có thể thay đổi exposure |

## 24. Bài tập thực hành

### Bài tập 1 — Đánh giá cấu hình không an toàn

Cho JVM options:

```properties
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

Hãy liệt kê các lớp bảo vệ còn thiếu và mô tả một hướng khắc phục không yêu cầu mở public management port.

**Gợi ý:** Authentication, authorization, TLS/encrypted management path, network allowlist, audit.

### Bài tập 2 — Phân biệt local và remote

Một ứng dụng đọc được `java.lang:type=Memory` qua `ManagementFactory.getPlatformMBeanServer()` nhưng JConsole từ một máy khác không kết nối được.

Hãy giải thích vì sao đây không nhất thiết là lỗi MBean, và những điều kiện nào mới cần có để remote client kết nối được một cách an toàn.

### Bài tập 3 — Chọn least privilege

Một monitoring service chỉ cần đọc `ThreadCount` và `HeapMemoryUsage`; một operator đôi khi cần đổi log level.

Thiết kế hai principal hoặc hai đường truy cập có quyền khác nhau, nêu cách xử lý credentials/audit.

### Bài tập 4 — Kiểm tra custom MBean

Một bean export:

```java
@ManagedAttribute
public String getJwtSigningSecret() { ... }

@ManagedOperation
public void purgePendingOrders() { ... }
```

Hãy đề xuất cách loại bỏ secret getter khỏi management API và kiểm soát operation destructive. Không chạy method trên production chỉ để kiểm thử.

### Bài tập 5 — RMI networking

Một pod có JMX registry port nhưng remote client vẫn không thể kết nối. Hãy chỉ ra cần kiểm tra RMI server port, advertised hostname, network policies và TLS/auth configuration. Vì sao mở toàn bộ port range là giải pháp không phù hợp?

### Bài tập 6 — Threat model cho production

Lập bảng cho một ứng dụng có remote JMX với các cột:

```text
Asset | Entry point | Unauthorized action | Impact | Control | Evidence
```

Ví dụ asset: JVM management data, cache controls, worker lifecycle, runtime properties. Chọn các controls thực tế và cách xác minh được chúng đang áp dụng.

## 25. Câu hỏi tự kiểm tra

**1. Vì sao remote JMX không xác thực nguy hiểm hơn một endpoint metric chỉ đọc?**

Vì JMX có thể công bố nhiều MBeans cùng operations quản trị, và một client không được xác thực có thể vượt khỏi nhu cầu đọc metric.

**2. Không bật JMX remote có đồng nghĩa không có MBeanServer không?**

Không. JVM và Spring vẫn có thể có local MBeanServer.

**3. TLS có thay thế authentication/authorization không?**

Không. TLS bảo vệ transport; quyền truy cập và quyền hành động cần cơ chế riêng.

**4. Private VPC có phải bảo vệ đủ cho JMX không xác thực?**

Không nên xem là đủ. Network segmentation là một lớp bảo vệ, không thay cho identity và least privilege.

**5. Spring Boot HTTP security có tự bảo vệ JMX remote connector không?**

Không. Hai đường truy cập thường sử dụng cơ chế security riêng.

**6. Vì sao phải kiểm tra custom MBean operations khi cho phép remote?**

Vì một số operations có tác động thật như pause worker, clear cache hoặc đổi cấu hình.

**7. `management.endpoints.jmx.exposure.include` có xóa JVM platform MBeans không?**

Không. Nó điều khiển Actuator JMX endpoints, không phải toàn bộ MBeanServer.

## 26. Ghi nhớ

- JMX remote biến management interface JVM thành bề mặt qua mạng.
- Remote không xác thực có thể dẫn đến đọc dữ liệu nhạy cảm, gọi operations quản trị hoặc gây tải hệ thống.
- Authentication, authorization, TLS, network isolation và audit là **các lớp bảo vệ bổ sung**, không thay thế nhau.
- JMX/RMI cần kiểm soát registry/server ports và advertised hostname; tránh giải quyết lỗi kết nối bằng cách mở mạng quá rộng.
- `spring.jmx.enabled` và Actuator JMX exposure khác với việc cấu hình một remote connector.
- Custom MBeans, library MBeans và JVM platform MBeans cũng phải được đưa vào threat model.
- Mặc định không mở remote khi không có nhu cầu. Khi cần, giới hạn nguồn, danh tính và operations theo least privilege.
- Không trả secrets qua managed attributes và không để destructive operations truy cập tùy tiện.
- Xác minh cấu hình bằng kiểm tra deployment, network, metadata và kết nối **trên hệ thống được cấp quyền**.
- Lập kế hoạch audit/rotation/đóng cổng cùng với chính sách vận hành.

## 27. Tài liệu tham khảo

- Oracle Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/tutorial/jmx/
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `JMXConnectorServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorServer.html
- Java SE 21 — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
