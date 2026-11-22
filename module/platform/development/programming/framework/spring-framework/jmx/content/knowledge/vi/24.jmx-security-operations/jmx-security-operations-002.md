# Phân quyền đọc attribute và gọi operation trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **xác thực (authentication)**, **phân quyền (authorization)** và **bảo mật đường truyền** trong JMX.
- Hiểu sự khác nhau giữa quyền đọc attribute, quyền ghi attribute và quyền gọi operation đối với một MBean.
- Biết giới hạn và khả năng của cơ chế quyền **readonly/readwrite** trong JDK remote JMX access file; không nhầm các mức quyền đó với RBAC chi tiết theo từng method.
- Thiết kế MBean quản trị có bề mặt nhỏ, tách operation tác động cao khỏi các thông số quan sát.
- Hiểu rằng **\`@ManagedAttribute\`**, **\`@ManagedOperation\`** và Spring \`MBeanExporter\` chỉ mô tả/export khả năng quản trị, không tự động thiết lập quyền theo người dùng.
- Tìm hiểu các điểm kiểm soát quyền ở **remote connector**, **MBeanServer layer**, **application/service layer** và hệ thống mạng.
- Biết cách viết kiểm tra tích hợp để xác nhận tài khoản chỉ đọc không thể thực hiện thao tác thay đổi trạng thái.
- Xử lý tình huống nhiều người dùng, local JMX, proxy nội bộ, Actuator và JVM/container security một cách có chủ đích.

## 2. Bức tranh tổng thể: bảo vệ một MBean

JMX (Java Management Extensions) cung cấp giao diện để quan sát và điều khiển JVM hoặc ứng dụng qua các **MBeans**. Một MBean có thể công bố:

- **Attributes**: tên, kiểu, cờ readable/writable; ví dụ \`QueueDepth\`, \`Running\`, \`MaxWorkers\`.
- **Operations**: tên, signature, kiểu trả về và metadata; ví dụ \`requestPause()\`, \`clearCache()\`, \`reloadConfiguration()\`.
- **Notifications**: các sự kiện mà client có thể subscribe, nếu implementation hỗ trợ.
- **Descriptors**: metadata bổ sung.

Về mặt rủi ro, không phải mọi quyền đều như nhau:

\`\`\`text
JMX client / operator
          |
          v
Authentication: ai đang kết nối?
          |
          v
Authorization: được làm gì?
          |
          +--> Query MBean metadata
          +--> Read attribute
          +--> Write attribute
          +--> Invoke operation
          +--> Register / unregister MBean
          +--> Subscribe notification
          |
          v
MBeanServer / target MBean
          |
          v
Java application / JVM state
\`\`\`

Một người được phép xem \`QueueDepth\` chưa chắc nên được phép gọi \`clearQueue()\`. Một người được phép chỉnh \`MaxWorkers\` cũng không nhất thiết nên được phép \`shutdown()\`.

Định nghĩa **read-only** và **read-write** cần gắn với **cơ chế kiểm soát đang sử dụng**. JMX không tự suy ra vai trò nghiệp vụ từ tên operation hay từ \`MBeanOperationInfo.getImpact()\`.

## 3. Những lớp bảo mật cần phân biệt

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| Network boundary | Giảm phạm vi máy có thể kết nối | Firewall, VPN, private network, tunnel |
| Transport security | Chống nghe lén/chỉnh sửa trên đường truyền | TLS cho JMX connector |
| Authentication | Xác minh danh tính của client | Password file, JAAS hoặc connector tùy chỉnh |
| Connector authorization | Quy định nhóm thao tác được phép | JDK access file \`readonly\`/\`readwrite\` |
| MBeanServer authorization | Kiểm soát lệnh ở tầng server | \`MBeanServerForwarder\` hoặc custom interceptor |
| Business authorization | Kiểm tra quyền nghiệp vụ khi thực thi | Permission check trong service |
| Audit | Truy vết thao tác quản trị | Log actor, ObjectName, action, result |

Những lớp này bổ sung cho nhau, không thay thế nhau.

Ví dụ, TLS bảo vệ dữ liệu trên đường truyền nhưng không quyết định một user có được phép xóa cache hay không. Một password file xác thực user nhưng không mặc định triển khai policy phức tạp cho từng \`ObjectName\`.

## 4. Read attribute, write attribute và invoke operation

### 4.1. Đọc attribute

\`\`\`java
Object value = connection.getAttribute(
    objectName,
    "QueueDepth"
);
\`\`\`

Phép gọi này thường đọc thông tin. Nhưng getter là code Java thật; nếu viết getter có side effect hoặc gây tải lớn, một thao tác “đọc” vẫn có thể ảnh hưởng hệ thống.

Vì vậy phải thiết kế getter JMX:

- Không cập nhật business state ngoài ý định.
- Không tiết lộ secret hoặc dữ liệu cá nhân.
- Không thực hiện truy vấn tốn tài nguyên trên mỗi lần polling nếu không cần.
- Có semantics rõ về freshness/cache.

### 4.2. Ghi attribute

\`\`\`java
import javax.management.Attribute;

connection.setAttribute(
    objectName,
    new Attribute("MaxWorkers", 8)
);
\`\`\`

Phép gọi này thay đổi cấu hình hoặc trạng thái khi MBean cho phép writable attribute.

Ngay cả khi quyền connector là readwrite, ứng dụng vẫn cần validate giá trị: \`MaxWorkers=1000000\` có thể làm cạn tài nguyên. Quyền thao tác và validation là hai trách nhiệm khác nhau.

### 4.3. Gọi operation

\`\`\`java
connection.invoke(
    objectName,
    "requestPause",
    new Object[0],
    new String[0]
);
\`\`\`

Operation có thể chỉ trả dữ liệu, hoặc có thể thực hiện hành động nghiêm trọng. **Không được suy ra operation \`INFO\` là hoàn toàn an toàn, hoặc operation \`ACTION\` được tự động bảo vệ**. Impact là metadata, không phải rule phân quyền.

### 4.4. Những hành động khác

Client có quyền cao có thể thực hiện một số thao tác như \`createMBean\`, \`registerMBean\`, \`unregisterMBean\` hoặc subscribe notifications tùy implementation và policy. Vì vậy cần kiểm soát hơn là chỉ giới hạn hai method \`getAttribute\` và \`invoke\`.

## 5. Spring @ManagedAttribute và @ManagedOperation không phải authorization

Ví dụ Spring:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Primary",
    description = "Queue administration"
)
public class QueueManagement {

    private volatile int maxWorkers = 8;

    @ManagedAttribute(description = "Current worker limit")
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(description = "Update worker limit")
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 64) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 64"
            );
        }
        this.maxWorkers = maxWorkers;
    }

    @ManagedOperation(description = "Request a graceful queue pause")
    public void requestPause() {
        // Delegates to an application service.
    }
}
\`\`\`

Nếu Spring JMX exporter được cấu hình đúng, client có thể thấy attribute \`MaxWorkers\` readable/writable và operation \`requestPause\`.

Nhưng:

- \`@ManagedAttribute\` không gắn role \`ROLE_VIEWER\`.
- \`@ManagedOperation\` không gắn role \`ROLE_OPERATOR\`.
- Description không tạo yêu cầu xác nhận khi invoke.
- \`setMaxWorkers\` validation giới hạn input, không biết ai đang gọi.
- Bật \`spring.jmx.enabled=true\` không tự tạo phân quyền theo user.

Muốn phân quyền, cần một security boundary thực sự ở connector/server/service.

## 6. Xác thực và authorization của JDK remote JMX

HotSpot/OpenJDK management agent hỗ trợ remote JMX với password file và access file trong những cấu hình được hỗ trợ.

Các property thường gặp:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access
\`\`\`

Đây là ví dụ định hướng property, không phải một cấu hình TLS hoàn chỉnh. Khi triển khai cần cấu hình certificate/keystore/truststore và RMI advertised hostname theo hạ tầng cụ thể.

### 6.1. Password file

Một password file của JMX agent thường chứa định danh và mật khẩu theo định dạng được JDK hỗ trợ:

\`\`\`text
monitorRole CHANGE_ME_FROM_SECRET_STORE
controlRole CHANGE_ME_FROM_SECRET_STORE
\`\`\`

Các chuỗi trên chỉ minh họa; không sử dụng literal này làm credential thực. Trong production, lấy secret từ nguồn được bảo vệ và giới hạn quyền filesystem theo JDK/OS.

Trên một số nền tảng/JDK, file mật khẩu có yêu cầu nghiêm ngặt về permission. Nếu file đọc được bởi user khác, agent có thể từ chối khởi động. Không khắc phục bằng cách nới quyền file.

### 6.2. Access file: readonly và readwrite

Ví dụ access file:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

Ý định:

- **monitorRole** có quyền đọc/quan sát trong phạm vi cơ chế JDK agent cho phép.
- **controlRole** có quyền thực hiện các thao tác thay đổi, bao gồm invoke operation trong phạm vi được phép.

Đây là **phân quyền coarse-grained**, không phải ma trận tùy chỉnh “role A chỉ được gọi \`refreshCache\`, role B chỉ được gọi \`pauseWorker\`”.

Khi cần role-specific per-operation authorization, hãy cân nhắc server forwarder hoặc security design khác.

### 6.3. Hạn chế của readwrite

Một user \`readwrite\` không tự động bị giới hạn chỉ một số method do ứng dụng gắn \`@ManagedOperation\`. Nếu client được quyền invoke operations của MBean và policy không cấm, operation có thể chạy.

Một số JDK access file syntax hỗ trợ tùy chọn giới hạn như \`create\` hoặc \`unregister\` đối với thao tác MBean management, tùy JDK/version. Điều đó vẫn không phải một hệ RBAC chi tiết cho mọi method; cần đọc tài liệu JDK tương ứng.

**Không dùng một tài khoản readwrite chung cho tất cả dashboards hoặc monitoring collectors** nếu các hệ đó chỉ cần đọc metrics.

## 7. Readonly có cho gọi operation chỉ đọc không?

Đây là một câu hỏi dễ nhầm.

Trong cơ chế access control của JDK management agent, **\`readonly\` không nên được hiểu là được phép gọi mọi operation có tên \`getSomething\` hoặc có impact \`INFO\`**. Quyền invoke thường được đối xử như một thao tác quản trị được kiểm soát riêng, không phân loại theo logic nghiệp vụ của operation.

Vì vậy khi thiết kế API cho monitoring client chỉ đọc:

- Ưu tiên **attributes** readable để lấy trạng thái.
- Không yêu cầu monitoring collector gọi custom operation chỉ để lấy một số liệu đơn giản.
- Nếu cần truy vấn dữ liệu có tham số, xác định connector policy có cho phép invoke hay không; không giả định có quyền từ \`INFO\`.
- Kiểm thử thực tế với tài khoản readonly của connector/JDK đang dùng.

Một MBean có \`calculateSummary()\` chỉ đọc về mặt nghiệp vụ vẫn có thể không gọi được bằng một account readonly nếu policy cấm invoke. Điều đó là hành vi security boundary, không phải lỗi của Spring exporter.

## 8. Tại sao MBeanInfo.isWritable không phải quyền người dùng?

\`MBeanAttributeInfo.isWritable()\` trả về thông tin **cấu trúc MBean**: attribute có setter hoặc được định nghĩa writable trong hợp đồng.

Ví dụ:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (var a : info.getAttributes()) {
    System.out.printf(
        "%s readable=%s writable=%s%n",
        a.getName(),
        a.isReadable(),
        a.isWritable()
    );
}
\`\`\`

Nếu \`isWritable=true\`, chỉ có thể kết luận attribute được MBean **công bố khả năng ghi**. Không có nghĩa caller hiện tại đủ quyền \`setAttribute\`.

Tương tự, \`MBeanInfo.getOperations()\` liệt kê operation được công bố, không phải danh sách operation mà user cụ thể được phép gọi.

Đây là hai lớp kiểm tra độc lập:

\`\`\`text
MBeanInfo: operation có tồn tại không?
    |
    v
Authorization policy: caller có được gọi không?
    |
    v
Business validation: giá trị/trạng thái có hợp lệ không?
    |
    v
Operation thực sự chạy
\`\`\`

Không sử dụng MBeanInfo thay thế authorization test.

## 9. Spring Boot và security của JMX

Trong Spring Boot, các property quản trị như:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

liên quan tới export MBean hoặc exposure của Actuator JMX endpoints, không phải một hệ role-based authorization đầy đủ cho mọi operation.

Đặc biệt cần phân biệt:

- **Spring Security web filters** bảo vệ HTTP requests.
- **JMX/RMI connector** tiếp nhận JMX clients theo giao thức quản trị.
- **MBeanServer** dispatch các API JMX.
- **Spring JMX exporter** công bố MBean từ các bean đã chọn.

**HTTP security configuration không tự bảo vệ JMX connector.** Ví dụ yêu cầu \`/actuator/**\` qua HTTP có authentication không có nghĩa JConsole cũng sẽ dùng cùng chain Spring Security.

Nếu một JMX operation cần biết user đã xác thực, hãy thiết kế cơ chế truyền identity có bảo đảm từ connector tới authorization layer. Không tự giả định SecurityContext của HTTP request hiện diện trong thread JMX.

## 10. Local JMX và remote JMX có mô hình tin cậy khác nhau

### 10.1. Local MBeanServer

Code trong cùng JVM có thể lấy platform MBeanServer:

\`\`\`java
MBeanServer server =
    java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
\`\`\`

Sau đó gọi:

\`\`\`java
server.invoke(name, "requestPause",
    new Object[0], new String[0]);
\`\`\`

Một call local không đi qua authentication password/access file của **remote connector**. Nếu code trong ứng dụng giữ tham chiếu đến \`MBeanServer\`, connector policy không phải rào chắn cho code đó.

Vì vậy không nên xem file \`jmxremote.access\` là cách bảo vệ mọi caller Java bên trong tiến trình.

### 10.2. Local attach với JConsole

JConsole local attach cũng có các điều kiện về user, OS permissions và attach mechanism. Nó không đơn giản đồng nhất với remote JMX agent có password file.

Trong môi trường nhiều người dùng, phải kiểm soát OS permissions, tài khoản chạy ứng dụng, khả năng attach/debug process và chính sách truy cập host/container.

### 10.3. Remote JMX

Remote connector có thêm:

- Authentication.
- TLS/network encryption.
- Authorization layer.
- Firewall/network restrictions.
- Audit và lifecycle kết nối.

Cần thiết kế các lớp này đồng thời, không chỉ dựa vào việc các MBean có annotation “read-only” hay không.

## 11. Thiết kế MBean riêng cho monitoring và control

Một kiến trúc dễ kiểm soát là tách phần quan sát và phần điều khiển.

\`\`\`text
com.example.orders:type=Queue,name=PrimaryStatus
  Attributes:
    PendingMessages    long (read-only)
    Running            boolean (read-only)
    LastFailureTime    String (read-only)

com.example.orders:type=Queue,name=PrimaryControl
  Operations:
    requestPause()     void
    requestResume()    void
    clearRetryQueue()  int
\`\`\`

Lợi ích:

- Monitoring collectors chỉ cần các attribute của status MBean.
- Các operation có side effect tập trung trong control MBean.
- Dễ lập allowlist/denylist theo \`ObjectName\`.
- Dễ log/audit các hành động điều khiển.
- Có thể chỉ export control MBean ở môi trường hoặc context được phép.

Tuy nhiên tách MBean **không tự tạo quyền** nếu connector vẫn cấp readwrite trên toàn MBeanServer. Muốn chặn role cụ thể, cần policy bảo đảm như custom forwarder, tách connector với quyền khác, hoặc authorization tại service.

### 11.1. Ví dụ status MBean

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PrimaryStatus"
)
public class QueueStatusMBeanAdapter {

    @ManagedAttribute(description = "Current pending message count")
    public long getPendingMessages() {
        return 12L;
    }

    @ManagedAttribute(description = "Whether worker is running")
    public boolean isRunning() {
        return true;
    }
}
\`\`\`

### 11.2. Ví dụ control MBean

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PrimaryControl"
)
public class QueueControlMBeanAdapter {

    private final QueueControlService control;

    public QueueControlMBeanAdapter(QueueControlService control) {
        this.control = control;
    }

    @ManagedOperation(
        description = "Request graceful pause of queue consumers"
    )
    public void requestPause() {
        control.requestPause();
    }
}
\`\`\`

\`QueueControlService\` là service do ứng dụng định nghĩa. Nó phải thực thi authorization và validation khi cần; ví dụ trên chỉ minh họa cách tách surface.

## 12. Fine-grained authorization qua MBeanServerForwarder

JMX remote API có interface **\`MBeanServerForwarder\`** trong \`javax.management.remote\`. Nó cho phép đặt một lớp forwarder trước \`MBeanServer\` để kiểm soát/ủy quyền các lời gọi từ connector.

Ý tưởng:

\`\`\`text
JMX client
    |
    v
JMXConnectorServer
    |
    v
MBeanServerForwarder
    |   \
    |    +--> Xác định caller/subject
    |    +--> Kiểm tra action + ObjectName
    |    +--> Cho phép / từ chối
    v
MBeanServer
    |
    v
Target MBean
\`\`\`

Một policy minh họa:

\`\`\`text
role=viewer:
    allow getMBeanInfo
    allow queryNames
    allow getAttribute on com.example.orders:type=Queue,name=PrimaryStatus
    deny  setAttribute
    deny  invoke

role=operator:
    allow getAttribute on status MBean
    allow invoke requestPause on PrimaryControl
    deny  invoke clearRetryQueue
    deny  unregisterMBean

role=administrator:
    allow selected management operations
    apply stronger authentication/audit
\`\`\`

Đây là pseudo-policy để mô tả logic, **không phải cú pháp file cấu hình chuẩn của JDK**.

### 12.1. Điều gì cần bảo vệ khi tự viết forwarder?

Nếu triển khai authorization tại tầng \`MBeanServerForwarder\`, không chỉ chặn \`invoke\`:

- \`getAttribute\` và \`getAttributes\`.
- \`setAttribute\` và \`setAttributes\`.
- \`invoke\`.
- \`queryNames\`, \`queryMBeans\`, \`getMBeanInfo\` nếu metadata nhạy cảm.
- \`createMBean\`, \`registerMBean\`, \`unregisterMBean\`.
- \`addNotificationListener\`, \`removeNotificationListener\`.
- Những operation có thể đạt cùng hiệu ứng qua đường API khác.

Cần chú ý **bulk operations**: một policy chỉ bảo vệ \`getAttribute\` nhưng bỏ sót \`getAttributes\` có thể tạo đường vòng. Tương tự, nếu chỉ chặn một operation nhưng attribute writable cho cùng hành vi, client vẫn có thể thay đổi trạng thái.

Forwarder cần fail-closed, kiểm tra policy trên đúng caller identity, không cache quyền sai ngữ cảnh và không log thông tin mật.

### 12.2. Caller identity và Subject

Remote JMX có thể gắn \`Subject\` của phiên xác thực với invocation qua cơ chế của connector/JDK. Cách lấy và sử dụng danh tính tùy cấu hình auth, Java version và API bảo mật tương ứng.

Không nên viết:

\`\`\`java
String user = "admin";
\`\`\`

hoặc tin thông tin caller tự gửi trong operation argument làm danh tính đáng tin cậy.

Ở các phiên bản JDK hiện đại, nhiều API security và SecurityManager đã thay đổi hoặc bị loại bỏ; khi triển khai custom authorization cần dùng tài liệu của JDK phiên bản cụ thể và test với connector thực tế, không dựa vào ví dụ cũ không còn hợp lệ.

## 13. Kiểm soát quyền ngay tại service layer

Nếu operation quản trị có tác động quan trọng, chỉ dựa vào connector role có thể chưa đủ. Ví dụ cùng một service method được gọi từ:

- JMX remote.
- Local Java code.
- HTTP admin API.
- Message consumer.
- Scheduled job.

Nếu business authorization chỉ tồn tại trong connector forwarder, đường gọi khác có thể bỏ qua nó. Có thể đặt kiểm tra quyền tại service boundary hoặc ở một application authorization component dùng chung.

Ví dụ ý tưởng:

\`\`\`java
public interface ManagementAuthorization {
    void requirePermission(String permission);
}
\`\`\`

Service:

\`\`\`java
public void clearRetryQueue() {
    authorization.requirePermission(
        "queue.retry.clear"
    );
    // Thực thi hành động đã được kiểm soát.
}
\`\`\`

Tuy nhiên implementation \`ManagementAuthorization\` phải xác định caller đáng tin cậy. Nếu operation JMX không có identity được truyền từ connector tới service, service không thể tự đoán ai đang gọi; có thể cần connector-specific principal mapping, command gateway hoặc tách API quản trị.

**Không truyền password hoặc token quản trị dưới dạng một tham số JMX operation thông thường** nếu chưa đánh giá đầy đủ vấn đề logging, transport, storage và truy cập.

## 14. Metadata impact và bẫy phân quyền theo tên

JMX operation có \`impact\`:

- \`INFO\`
- \`ACTION\`
- \`ACTION_INFO\`
- \`UNKNOWN\`

Ví dụ:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + ": " + operation.getImpact()
    );
}
\`\`\`

Một công cụ quản trị có thể dùng metadata impact để hiển thị khác nhau. Nhưng impact không phải bảo đảm phương thức không thay đổi trạng thái.

Ví dụ operation \`getAndResetCounter()\` có thể được gắn nhầm \`INFO\` dù làm reset counter. Nếu authorization dựa hoàn toàn vào \`INFO\`, người dùng chỉ đọc có thể thực hiện side effect ngoài dự định.

Do đó policy bảo mật nên dựa trên **allowlist action + ObjectName + signature** được review, chứ không dựa vào tên \`get*\`, description hoặc impact.

## 15. Đọc và ghi attribute có thể là những quyền riêng

Cùng một attribute \`MaxWorkers\` có thể readable/writable:

\`\`\`text
Attribute MaxWorkers:
  type = int
  readable = true
  writable = true
\`\`\`

Policy nghiệp vụ có thể muốn:

- Viewer: được đọc \`MaxWorkers\`.
- Operator: được đọc và ghi trong phạm vi được phép.
- Admin: được thay đổi cả settings nâng cao.

Nếu connector chỉ có hai mức readonly/readwrite trên toàn registry, nó không tự đáp ứng đầy đủ phân quyền per-attribute/per-value. Cần custom authorization hoặc tách các bề mặt JMX theo miền quyền phù hợp.

Ngay khi một operator được cấp quyền ghi, setter vẫn cần kiểm tra:

\`\`\`java
if (maxWorkers < 1 || maxWorkers > 64) {
    throw new IllegalArgumentException(
        "maxWorkers must be between 1 and 64"
    );
}
\`\`\`

Một access check không thể thay thế validation, concurrency control hoặc transaction semantics.

## 16. Remote JMX TLS và firewall

Phân quyền chỉ đáng tin khi endpoint quản trị được bảo vệ đúng đường truyền và kết nối:

\`\`\`text
Monitoring host
   |
   | authenticated + encrypted
   v
Private management network / VPN / tunnel
   |
   v
JMX connector
   |
   v
Authorization
   |
   v
MBeanServer
\`\`\`

Khi sử dụng JMX/RMI, có thể cần cổng registry và cổng RMI server. Nếu cấu hình remote JMX dùng cổng động hoặc quảng bá hostname không truy cập được, client có thể lỗi dù authentication đúng.

Đặc biệt trong Docker/Kubernetes:

- Chỉ publish JMX port khi thật sự cần.
- Tách khỏi ingress HTTP công khai.
- Xác định RMI advertised host/port chính xác.
- Bảo vệ quyền port-forward và Kubernetes RBAC.
- Không để credential trong container image hoặc version control.
- Thường xuyên kiểm tra phiên bản JDK và security policy.

Không nên cấu hình \`authenticate=false\`, \`ssl=false\` trên endpoint mở ra production để “khắc phục nhanh” lỗi kết nối.

## 17. Test quyền bằng hai tài khoản

Giả sử lab có hai role:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

Và MBean:

\`\`\`text
com.example.orders:type=Queue,name=PrimaryControl
\`\`\`

Một phép kiểm tra authorization phải dùng **remote JMX connector thật** với mỗi credential, không chỉ gọi \`ManagementFactory.getPlatformMBeanServer()\` local.

### 17.1. Kết nối JMX có credentials

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
\`\`\`

Với JMX API, khóa môi trường chuẩn dùng để truyền credentials là \`JMXConnector.CREDENTIALS\` (một constant), tương ứng \`String[]\` chứa username và password.

Ví dụ code:

\`\`\`java
Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, env)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    // Chạy các assertions tương ứng với role.
}
\`\`\`

\`username\` và \`password\` phải lấy từ secret/test fixture an toàn. Không log giá trị credential.

### 17.2. Test read-only

Với account readonly:

1. \`getMBeanInfo\` và \`getAttribute\` cho MBean được phép.
2. Thử \`setAttribute\` trên attribute writable.
3. Thử \`invoke\` một operation an toàn trong môi trường test.
4. Assert thao tác thay đổi bị từ chối theo security configuration thực tế.
5. Sau khi bị từ chối, kiểm tra state vẫn giữ nguyên.

Dùng một operation test có side effect nhỏ và được cô lập, ví dụ \`incrementTestCounter()\`, để có thể chứng minh nó **không chạy** khi client không có quyền. Không dùng \`clearProductionQueue()\` hoặc \`shutdown()\` cho test.

### 17.3. Test readwrite

Với account readwrite:

1. Kiểm tra có thể đọc attribute.
2. Ghi một attribute được phép trong lab, sau đó đọc lại.
3. Gọi operation kiểm thử đã được cho phép, assert state thay đổi đúng.
4. Nếu có custom forwarder, thử operation bị policy cấm dù account ở nhóm operator.
5. Xác nhận audit event ghi đúng actor/action/result.

**Điểm cần hiểu:** JDK access file có thể cho một nhóm readwrite thao tác rộng. Bài test readwrite không chứng minh có per-operation RBAC nếu chưa triển khai policy riêng.

## 18. Integration test không nên chỉ bắt exception

Giả sử một client readonly thử gọi:

\`\`\`java
connection.invoke(
    objectName,
    "incrementTestCounter",
    new Object[0],
    new String[0]
);
\`\`\`

Một test chỉ kiểm tra “lời gọi ném exception” là chưa đủ. Có thể exception đến từ \`InstanceNotFoundException\`, signature sai hoặc lỗi nghiệp vụ, không phải authorization.

Test tốt nên:

- Xác nhận MBean tồn tại và operation signature đúng bằng admin/fixture có quyền.
- Dùng đúng readonly credential.
- Phân loại exception phát sinh do chính sách quyền.
- Kiểm tra counter không tăng sau lời gọi bị từ chối.
- Chạy cùng operation với credential được cho phép để chứng minh test fixture hoạt động.

Cơ chế JDK connector có thể wrap lỗi thành \`SecurityException\`, \`IOException\` hoặc exception đặc thù tùy giao thức/version. Không hardcode một error message cố định nếu cần hỗ trợ nhiều phiên bản.

## 19. Local test khác remote test

Một test local:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PrimaryControl"
);

server.invoke(
    name,
    "incrementTestCounter",
    new Object[0],
    new String[0]
);
\`\`\`

chứng minh operation thực hiện được trong registry local. Nhưng nó không đi qua remote authentication/access file. Nó **không chứng minh** tài khoản readonly của JMX connector bị chặn.

Bộ test tốt nên có hai lớp:

1. **Contract test local:** MBeanInfo, attribute read/write metadata, method signature, business validation.
2. **Security integration test remote:** authentication, role permissions, TLS và denial thực tế.

Với custom forwarder, test cả các đường API bulk và các operation có hiệu ứng tương đương.

## 20. Audit và log thao tác quản trị

Những operation có side effect cần audit phù hợp:

\`\`\`text
timestamp=2026-11-11T10:00:00Z
actor=operator-123
source=jmx
objectName=com.example.orders:type=Queue,name=PrimaryControl
operation=requestPause
result=accepted
requestId=abc123
\`\`\`

Đây là định dạng minh họa, không phải chuẩn tự động của Spring/JMX. Actor phải đến từ danh tính đã xác thực hoặc một cơ chế tin cậy, không phải tham số tùy ý người dùng truyền.

Không log:

- Mật khẩu JMX.
- Access token.
- Giá trị attribute chứa secret.
- Toàn bộ tham số nhạy cảm.
- Đường dẫn credentials/keystore chi tiết trong log không được bảo vệ.
- Stack trace chứa dữ liệu bí mật chưa sanitize.

Một audit event nên phân biệt:

- **Request accepted**: thao tác được chấp nhận.
- **Operation completed**: tác vụ đã hoàn tất.
- **Operation rejected**: từ chối bởi authorization hoặc validation.
- **Operation failed**: có lỗi trong execution.

Đối với operation async, \`invoke\` trả thành công không đồng nghĩa job đã hoàn tất. Cần trạng thái task và audit tương ứng.

## 21. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Readonly vẫn thấy operation trên JConsole | MBeanInfo mô tả operation, không phải danh sách quyền user. | Kiểm tra policy khi invoke, không dùng metadata làm authorization. |
| Readonly gọi được operation nguy hiểm | Connector đang không bật auth/authorization hoặc dùng quyền khác kỳ vọng. | Xác minh endpoint, credential, access file, custom connector. |
| \`spring.jmx.enabled=false\` mà vẫn thấy JVM MBeans | Platform MBeans của JVM độc lập với Spring exporter. | Phân biệt nguồn đăng ký. |
| Spring Security HTTP đã bật nhưng JConsole vẫn truy cập | Remote JMX không qua HTTP filter chain. | Cấu hình JMX authentication/TLS/policy riêng. |
| \`isWritable=true\` nhưng set bị từ chối | Metadata writable, caller không có quyền. | Kiểm tra connector authorization. |
| Readwrite có thể gọi operation ngoài phạm vi mong muốn | JDK role coarse-grained, thiếu fine-grained policy. | Tách API hoặc triển khai forwarder/gateway kiểm soát. |
| Security test local pass nhưng remote fail | Local bypass connector auth hoặc remote identity khác. | Test bằng kết nối remote thật. |
| Authentication fail do file permissions | JDK agent yêu cầu file password an toàn. | Thiết lập owner/permission đúng, không nới quyền. |
| JConsole kết nối timeout | RMI hostname/port, firewall hoặc TLS. | Kiểm tra network và connector trước khi kết luận quyền. |
| Test bị từ chối nhưng state vẫn đổi | Authorization xảy ra sau side effect, hoặc test không cô lập. | Chặn trước dispatch, kiểm tra race và audit. |
| QueryNames lộ topology | Metadata discovery chưa được kiểm soát. | Đánh giá quyền metadata, network boundary. |
| Notification tiết lộ dữ liệu | Policy không kiểm tra subscribe/notification payload. | Bảo vệ listener registration và nội dung event. |

## 22. Quy trình thiết kế chính sách phân quyền

### Bước 1 — Kiểm kê MBean

Liệt kê domain, ObjectName và những attributes/operations thực tế đã export bằng \`MBeanInfo\`. Không dựa chỉ vào annotation source.

### Bước 2 — Phân loại dữ liệu và hành động

Ví dụ:

\`\`\`text
QueueDepth       read-only telemetry
MaxWorkers       configurable operational setting
requestPause     operational command
clearRetryQueue  destructive command
\`\`\`

Đánh giá side effect thực, không chỉ tên hoặc \`impact\`.

### Bước 3 — Định nghĩa role

Một mô hình:

\`\`\`text
viewer    -> đọc status
operator  -> đọc status + điều khiển chọn lọc
admin     -> quản trị nâng cao trong phạm vi được duyệt
\`\`\`

### Bước 4 — Chọn enforcement mechanism

- Nếu hai cấp readonly/readwrite đủ, JDK agent access file có thể phù hợp.
- Nếu cần per-MBean/per-operation, dùng custom forwarder hoặc gateway có policy.
- Nếu operation có tác động nghiệp vụ lớn, thêm service-layer authorization.
- Nếu có nhiều đường gọi cùng service, đảm bảo authorization không chỉ nằm tại một transport.

### Bước 5 — Kiểm thử denial

Với mỗi role, thử những thao tác bị cấm và xác nhận state không thay đổi. Kiểm tra cả bulk operations, overload và đường API thay thế.

### Bước 6 — Triển khai bảo mật kết nối

TLS, authentication, firewall, secrets management, log retention và quyền hạ tầng cần phù hợp với mức độ nhạy cảm của JVM.

### Bước 7 — Giám sát và duy trì

Khi thêm một \`@ManagedOperation\` mới, cập nhật security allowlist và tests trước deploy. Audit các hành động nhạy cảm; không cấp quyền rộng chỉ để xử lý nhanh lỗi phân quyền.

## 23. Bài tập thực hành

### Bài tập 1 — Hai tài khoản JMX

Trong một lab cô lập, cấu hình \`monitorRole readonly\` và \`controlRole readwrite\`. Kết nối bằng hai account, kiểm tra việc đọc \`QueueDepth\`, ghi \`MaxWorkers\` và gọi \`incrementTestCounter\`.

**Mục tiêu:** chứng minh quyền read/write thực tế của connector.

### Bài tập 2 — Metadata không phải quyền

Đọc \`MBeanInfo\` với account readonly, ghi nhận operation \`incrementTestCounter\` xuất hiện. Thử invoke và xác nhận bị từ chối.

**Mục tiêu:** hiểu \`getOperations()\` không là authorization allowlist.

### Bài tập 3 — Operation chỉ đọc

Tạo operation \`calculateSummary()\` chỉ trả thông tin và khai báo impact INFO phù hợp. Kiểm tra account readonly có được invoke theo JMX access policy hay không.

**Mục tiêu:** không suy luận quyền từ impact hoặc tên.

### Bài tập 4 — Tách status/control

Tạo hai MBeans: \`QueueStatus\` có attribute read-only và \`QueueControl\` có operation thay đổi trạng thái. Thiết kế policy để monitoring role chỉ đọc status.

**Mục tiêu:** giảm bề mặt quản trị và đơn giản hóa authorization.

### Bài tập 5 — Fine-grained policy

Thiết kế policy giả lập cho \`MBeanServerForwarder\` chặn mọi operation trừ \`requestPause\` đối với role operator. Viết test chặn \`clearRetryQueue\` và xác nhận không có side effect.

**Mục tiêu:** hiểu quyền per-operation phải được thực thi bởi cơ chế riêng.

### Bài tập 6 — Kiểm tra local và remote

Dùng local MBeanServer invoke thành công, sau đó kết nối JMX remote với readonly credential và chứng minh thao tác thay đổi bị từ chối.

**Mục tiêu:** nhận ra connector authorization không áp dụng tự động cho Java code local.

### Bài tập 7 — Security review

Kiểm kê 10 MBeans hiện có, phân loại attributes/operations và đề xuất nhóm quyền. Đánh giá thêm metadata discovery và notifications.

**Mục tiêu:** bảo vệ toàn bộ bề mặt JMX thay vì chỉ vài operation nổi bật.

## 24. Câu hỏi ôn tập

**1. \`@ManagedOperation\` có tự thiết lập role được gọi không?** Không. Nó mô tả một operation được export; authorization do tầng bảo mật khác đảm nhận.

**2. \`MBeanAttributeInfo.isWritable()\` trả lời câu hỏi gì?** Attribute có khả năng được ghi theo hợp đồng MBean, không phải caller hiện tại có đủ quyền.

**3. \`readonly\` trong JDK JMX access file có nghĩa user được invoke mọi operation INFO không?** Không. Không nên suy ra quyền invoke từ metadata impact.

**4. Tài khoản \`readwrite\` có sẵn phân quyền theo ObjectName hay không?** Không nên coi readonly/readwrite là RBAC chi tiết; cần policy riêng khi muốn quyền theo MBean hoặc operation.

**5. Tại sao Spring Security HTTP không tự bảo vệ remote JMX?** Vì JMX connector không đi qua HTTP filter chain của Spring Security.

**6. Local MBeanServer có dùng password file của remote JMX agent không?** Không; lời gọi Java local không phải kết nối qua remote connector đó.

**7. Khi nào cần \`MBeanServerForwarder\`?** Khi muốn chặn/ủy quyền các thao tác JMX ở tầng connector/server theo policy riêng.

**8. Vì sao authorization test phải kiểm tra state?** Để chắc chắn lời gọi bị từ chối trước khi có side effect, không chỉ có exception.

**9. Nếu operation thay đổi trạng thái cần quyền riêng, nên làm gì?** Tách bề mặt status/control, dùng allowlist và enforcement đáng tin ở connector/server/service.

**10. Những lớp nào cần có khi mở remote JMX production?** Network restriction, TLS, authentication, authorization, audit và secret management phù hợp.

## 25. Tổng kết

**Phân quyền đọc attribute và gọi operation trong Spring JMX** không nằm trong bản thân annotation \`@ManagedAttribute\` hay \`@ManagedOperation\`. Spring exporter quyết định **những gì được công bố**, còn security infrastructure quyết định **ai được phép làm gì**.

JDK remote JMX access file có thể dùng các role coarse-grained như \`readonly\` và \`readwrite\`. Khi cần quyền chi tiết theo MBean/attribute/operation, phải bổ sung enforcement như \`MBeanServerForwarder\` hoặc business authorization. Mọi quyền phải được kiểm chứng bằng remote security integration tests, gồm cả trường hợp denial và trạng thái không đổi. Trong production, tách monitoring khỏi control, bảo vệ connector bằng TLS/network policy và không dựa vào metadata impact để ra quyết định bảo mật.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Oracle JDK Monitoring and Management Guide — Using JMX Technology: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanServerForwarder\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/MBeanServerForwarder.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html