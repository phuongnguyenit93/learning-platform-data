# Đọc log exporter, MBeanServer và connector để khoanh vùng sự cố Spring Framework JMX

## Mục tiêu học tập

Trong một ứng dụng Spring Framework JMX, việc JConsole không thấy MBean hoặc client remote không gọi được operation có thể xuất phát từ nhiều lớp: Spring bean chưa được tạo, \`MBeanExporter\` không đăng ký, \`ObjectName\` sai, \`MBeanServer\` không đúng, MBean thiếu metadata, hoặc remote \`JMXConnectorServer\` chưa hoạt động. Nếu chỉ nhìn một exception cuối cùng rồi thay đổi cấu hình ngẫu nhiên, việc chẩn đoán dễ kéo dài và có thể tạo lỗi mới.

Bài này thuộc phần **Chẩn đoán sự cố** của Spring Framework JMX. Sau bài học, bạn có thể:

- Tách lỗi theo các tầng **Spring context → exporter → MBeanServer → connector → JMX client**.
- Bật và đọc logging phù hợp của Spring JMX exporter, Spring container, JDK JMX/RMI và thành phần ứng dụng.
- Dùng dấu hiệu \`ObjectName\`, server identity, PID, endpoint, thời điểm và correlation ID để liên kết log.
- Hiểu các exception phổ biến: \`InstanceAlreadyExistsException\`, \`NotCompliantMBeanException\`, \`InstanceNotFoundException\`, \`AttributeNotFoundException\`, \`ReflectionException\`, lỗi RMI kết nối và lỗi xác thực.
- Kiểm chứng các nhận định từ log bằng API \`MBeanServer\`, không phụ thuộc hoàn toàn vào JConsole.
- Viết một quy trình điều tra an toàn, dễ tái lập, có thời gian khoanh vùng và kết luận nguyên nhân gốc.

## 1. Bản đồ các tầng cần quan sát

\`\`\`text
Spring ApplicationContext
    |
    | Bean creation / dependency injection
    v
Managed Spring bean
    |
    | MBeanExporter, assembler, naming strategy
    v
MBean registration
    |
    | ObjectName -> MBean
    v
MBeanServer
    |
    +-- Local client: MBeanServerConnection
    |
    +-- JMXConnectorServer
            |
            | RMI / transport / authentication
            v
       Remote JMX client (JConsole, custom client)
\`\`\`

Mỗi tầng có dấu hiệu khác nhau:

| Tầng | Câu hỏi | Nguồn bằng chứng |
| --- | --- | --- |
| Context | Spring bean có được tạo và context còn chạy? | Startup logs, bean definitions, dependency failures |
| Exporter | Có exporter hoạt động và bean nằm trong export mapping? | Spring JMX exporter logs, cấu hình |
| Naming | \`ObjectName\` cuối cùng là gì? | Log naming strategy, \`queryNames\` |
| Registry | MBean đã tồn tại trong đúng server? | \`isRegistered\`, \`getMBeanInfo\` |
| JMX contract | Attribute/operation có được công bố? | \`MBeanInfo\`, exceptions |
| Connector | Remote endpoint đã start, bind đúng host/port? | Connector startup logs, socket diagnostics |
| Client | Client kết nối đúng JVM, credentials và URL? | Client logs, PID, JMX service URL |
| Runtime | Operation có thực thi và phản hồi đúng? | App logs, result/exception, metrics |

**Nguyên tắc chẩn đoán:** luôn bắt đầu bằng việc chứng minh trạng thái ở tầng gần nguồn lỗi nhất. Nếu \`server.isRegistered(name)\` là \`false\` trên server mà exporter dùng, sửa RMI connector sẽ không làm MBean xuất hiện trong registry. Nếu local API đọc MBean thành công nhưng remote client thất bại, tập trung vào connector/transport/security thay vì sửa metadata exporter.

## 2. Ba kiểu lỗi quan trọng cần phân biệt

### 2.1. Lỗi đăng ký

Ví dụ Spring context khởi tạo nhưng MBean không được đăng ký do trùng tên hoặc implementation không hợp lệ.

\`\`\`text
ApplicationContext -> MBeanExporter -> MBeanServer
                                    X registerMBean
\`\`\`

Dấu hiệu: exception ở startup hoặc log của exporter, \`isRegistered\` không đúng kỳ vọng.

### 2.2. Lỗi hợp đồng quản lý

MBean có trong registry nhưng thiếu attribute hoặc operation. Chẳng hạn \`getPendingCount()\` không nằm trong management interface, assembler loại bỏ method, hoặc client truyền sai operation signature.

\`\`\`text
MBeanServer: ObjectName có thật
    |
    +-- getMBeanInfo thành công
    +-- getAttribute/invoke thất bại
\`\`\`

Dấu hiệu: \`AttributeNotFoundException\`, \`ReflectionException\`, hoặc metadata không như mong đợi.

### 2.3. Lỗi kết nối remote

MBean đã đăng ký và local API hoạt động, nhưng client từ xa không kết nối được.

\`\`\`text
Local MBeanServer: OK
Remote JMX connector: X
Remote client: timeout / connection refused
\`\`\`

Dấu hiệu: \`IOException\`, \`ConnectException\`, lỗi RMI lookup, SSL handshake hoặc authentication. Đây là vùng điều tra khác với exporter.

## 3. Bật log cho Spring JMX exporter

Khi cần điều tra, bật logger cụ thể thay vì bật DEBUG/TRACE toàn ứng dụng. Các package/class liên quan thường gồm:

- \`org.springframework.jmx.export\`: \`MBeanExporter\` và các thành phần export.
- \`org.springframework.jmx.export.annotation\`: annotation metadata và annotation-based exporting.
- \`org.springframework.jmx.export.assembler\`: assembler tạo management interface.
- \`org.springframework.jmx.export.naming\`: naming strategy.
- \`org.springframework.jmx.support\`: hỗ trợ MBeanServer/registration.
- \`org.springframework.beans.factory\`: quá trình tạo bean, dependency wiring.
- \`org.springframework.context\`: refresh, close và lifecycle của ApplicationContext.

Ví dụ cấu hình Spring Boot \`application.properties\`:

\`\`\`properties
logging.level.org.springframework.jmx.export=DEBUG
logging.level.org.springframework.jmx.export.annotation=DEBUG
logging.level.org.springframework.jmx.export.assembler=DEBUG
logging.level.org.springframework.jmx.export.naming=DEBUG
logging.level.org.springframework.jmx.support=DEBUG
logging.level.org.springframework.beans.factory=INFO
\`\`\`

Với Logback:

\`\`\`xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} [%thread] %-5level %logger{48} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.springframework.jmx.export" level="DEBUG"/>
    <logger name="org.springframework.jmx.support" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
\`\`\`

Các câu log thực tế thay đổi theo Spring Framework version, logger implementation và đường code được thực thi. Không phụ thuộc vào một câu log nguyên văn duy nhất. Mục tiêu là lấy bằng chứng: exporter được khởi tạo, bean nào được xét, tên JMX nào được dùng và có lỗi registration hay không.

**Lưu ý:** DEBUG/TRACE có thể tăng lượng log và làm lộ thông tin cấu hình. Chỉ bật trong khoảng cần thiết, không in credentials, secrets hoặc dữ liệu khách hàng.

## 4. Log cần có những thông tin gì?

Một dòng log phục vụ chẩn đoán thường hữu ích khi có:

\`\`\`text
timestamp | level | logger | thread | JVM/PID | context |
ObjectName | server identity | phase | outcome | error cause
\`\`\`

Ví dụ log minh họa:

\`\`\`text
2026-11-11T09:10:15.230Z INFO  app.jmx
pid=2145 context=orders-main phase=register
objectName=com.example.orders:type=QueueMonitor,name=primary
server=platform outcome=SUCCESS
\`\`\`

Ví dụ lỗi:

\`\`\`text
2026-11-11T09:10:16.099Z ERROR app.jmx
pid=2145 context=orders-child phase=register
objectName=com.example.orders:type=QueueMonitor,name=primary
error=InstanceAlreadyExistsException
\`\`\`

Các dòng trên là **mẫu minh họa logging của ứng dụng**, không phải một cam kết rằng Spring sẽ phát ra đúng định dạng. Khi ghi log thực, hãy dùng formatter/logger thống nhất và tránh chép toàn bộ exception message nếu chứa dữ liệu nhạy cảm.

Các trường đặc biệt có giá trị:

- **Timestamp**: liên kết sự kiện startup, connector và client.
- **PID/JVM identity**: tránh phân tích nhầm log từ một tiến trình khác.
- **Context ID**: phân biệt root/child contexts hoặc context khởi động lại.
- **\`ObjectName\`**: xác định registration cụ thể.
- **Server identity**: platform MBeanServer hay custom server.
- **Thread name**: phân biệt startup, background worker hoặc JMX request thread.
- **Root cause**: loại exception và stack trace phù hợp.
- **Correlation/request ID**: truy vết operation có tác dụng phụ, nếu ứng dụng cung cấp.

## 5. Đọc stack trace: tìm nguyên nhân gốc thay vì chỉ nhìn wrapper

Spring có thể bọc lỗi trong các exception như \`BeanCreationException\`, \`MBeanExportException\` hoặc một exception khác ở tầng lifecycle. Ví dụ:

\`\`\`text
BeanCreationException: Error creating bean 'mBeanExporter'
  caused by MBeanExportException: Could not register MBean
    caused by InstanceAlreadyExistsException:
      com.example.orders:type=QueueMonitor,name=primary
\`\`\`

Trong trường hợp này, \`BeanCreationException\` mô tả tác động lên context. **Nguyên nhân gốc** là registry đã có tên JMX đó.

Một stack trace khác:

\`\`\`text
MBeanExportException: Unable to register bean
  caused by NotCompliantMBeanException:
    MBean class does not implement a valid management interface
\`\`\`

Lúc này vấn đề là hợp đồng MBean/type/metadata, không phải mạng. Bật thêm TRACE của RMI connector không giúp giải quyết lỗi compliance.

Cách đọc:

1. Xác định phase: startup, registration, connection, invocation hay shutdown.
2. Tìm exception type đầu tiên có ý nghĩa domain.
3. Đọc \`Caused by\` đến root cause.
4. Liên kết exception với \`ObjectName\`, server và bean.
5. Kiểm chứng bằng API registry hoặc test nhỏ.
6. Chỉ sau đó thay đổi cấu hình/code.

Không mọi stack trace đều có \`Caused by\` đầy đủ nếu logging bị cắt. Khi log thiếu, cấu hình logging/error reporting cho đúng exception object và stack trace thay vì chỉ ghi \`ex.getMessage()\`.

## 6. Lỗi InstanceAlreadyExistsException

\`InstanceAlreadyExistsException\` xảy ra khi \`MBeanServer\` đã có registration dưới \`ObjectName\` mà exporter muốn sử dụng.

Nguyên nhân thường gặp:

- Hai \`MBeanExporter\` cùng đăng ký một tên.
- Spring XML exporter và Java Config exporter cùng active.
- Root context và child context dùng chung platform server.
- Test trước không đóng context/unregister.
- Naming strategy tạo cùng tên cho nhiều instances.
- Auto-configuration cùng với exporter thủ công dẫn tới chồng chéo.

Cách xác minh:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

System.out.println(server.isRegistered(name));
System.out.println(server.getMBeanInfo(name).getClassName());
\`\`\`

Đoạn này chỉ đúng khi exporter đang dùng **platform server**. Nếu exporter dùng custom server, phải lấy chính server đó để kiểm tra.

Khi tên đã tồn tại, tìm owner của registration trước khi dùng \`REPLACE_EXISTING\`. Nếu thật sự cần hai instances, hãy đặt \`ObjectName\` khác nhau. \`IGNORE_EXISTING\` có thể khiến startup qua nhưng client tiếp tục đọc MBean cũ; nó không phải giải pháp tổng quát.

## 7. Lỗi NotCompliantMBeanException và metadata không hợp lệ

\`NotCompliantMBeanException\` thường liên quan đối tượng không đáp ứng quy tắc MBean mà JMX server yêu cầu, hoặc metadata được dựng không hợp lệ.

Ví dụ Standard MBean:

\`\`\`java
public interface QueueMonitorMBean {
    int getQueueDepth();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getQueueDepth() {
        return 5;
    }
}
\`\`\`

Nếu class không implement interface Standard MBean đúng convention hoặc sử dụng method/type không phù hợp, việc đăng ký có thể thất bại.

Spring cũng có thể adapt POJO thành ModelMBean qua assembler. Khi đó cần kiểm tra:

- \`MBeanInfoAssembler\` nào đang được gắn?
- Có đang dùng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` đúng mục tiêu?
- Bean có bị Spring AOP JDK proxy che implementation method?
- Có method signature/type không phù hợp JMX?
- Exporter có đang nhận cùng object mà bạn tưởng?

Không giải quyết bằng cách đổi \`ObjectName\` ngẫu nhiên nếu lỗi xuất phát từ management interface.

## 8. Lỗi InstanceNotFoundException

Khi client gọi:

\`\`\`java
connection.getAttribute(name, "QueueDepth");
\`\`\`

mà tên không có trong server đích, JMX có thể ném \`InstanceNotFoundException\`.

Những nguyên nhân cần loại trừ:

1. MBean chưa được exporter đăng ký.
2. \`ObjectName\` bị sai domain hoặc key.
3. Client đang kết nối tới \`MBeanServer\` khác.
4. Client đang kết nối tới JVM khác.
5. MBean đã bị unregister khi \`ApplicationContext\` đóng.
6. Naming strategy tạo tên khác dự kiến.
7. Exporter dùng \`IGNORE_EXISTING\`, giữ MBean khác rồi owner cũ đóng làm tên biến mất.

Dùng query:

\`\`\`java
Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.orders:*"), null);

for (ObjectName n : names) {
    System.out.println(n.getCanonicalName());
}
\`\`\`

Không đoán tên JMX chỉ từ Spring bean name. Hãy đọc registry cuối cùng.

## 9. Lỗi AttributeNotFoundException và ReflectionException

Nếu \`ObjectName\` tồn tại nhưng một attribute không có:

\`\`\`text
AttributeNotFoundException: QueueDepth
\`\`\`

có thể là do:

- Getter không thuộc management interface.
- Assembler không chọn method đó.
- Annotation \`@ManagedAttribute\` không được phát hiện.
- Tên attribute có phân biệt chữ hoa/thường.
- Client dùng sai MBean hoặc metadata thay đổi.

Tương tự, \`ReflectionException\` hoặc lỗi invocation có thể phát sinh khi method name/signature không khớp.

Kiểm tra metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.println(
            attr.getName() + " " + attr.getType());
}

for (var operation : info.getOperations()) {
    System.out.println(
            operation.getName() + " "
            + java.util.Arrays.toString(operation.getSignature()));
}
\`\`\`

Ví dụ gọi operation có tham số:

\`\`\`java
server.invoke(
        name,
        "resizePool",
        new Object[]{8},
        new String[]{"int"});
\`\`\`

Với method \`resizePool(int)\`, signature JMX là \`"int"\`; không tự thay thành \`"java.lang.Integer"\` nếu metadata mô tả primitive. Đọc \`MBeanOperationInfo.getSignature()\` để xác định.

## 10. Lỗi permission và security

Remote JMX connector có thể từ chối kết nối hoặc invocation do authentication, authorization hoặc TLS.

Các biểu hiện:

\`\`\`text
SecurityException
Authentication failed
SSLHandshakeException
Access denied
\`\`\`

Phân biệt:

- **Authentication failure**: credentials không hợp lệ hoặc thiếu.
- **Authorization failure**: client đã xác thực nhưng không có quyền thao tác.
- **TLS handshake failure**: truststore/keystore/protocol không khớp.
- **Network failure**: client không tới được endpoint.
- **MBean operation failure**: kết nối và quyền đã qua nhưng logic operation thất bại.

Không in username/password, token, private key hoặc toàn bộ environment map của \`JMXConnectorFactory.connect\` vào log. Với các lỗi bảo mật, ghi error category, correlation ID và endpoint không nhạy cảm là đủ để điều tra bước đầu.

## 11. Lỗi connector: Connection refused, timeout và RMI

Một cấu hình JMX over RMI phổ biến dùng URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://host.example:9010/jmxrmi
\`\`\`

Trong đó RMI registry có thể nằm ở một port, còn exported RMI remote object có thể dùng một port khác. Client cần đi qua cả lookup và invocation. Vì vậy có trường hợp **registry lookup thành công nhưng remote invoke thất bại**.

Các lỗi thường gặp:

| Biểu hiện | Nguyên nhân khả dĩ | Hành động kiểm tra |
| --- | --- | --- |
| \`ConnectException: Connection refused\` | Port sai, server chưa start, bind sai interface | Kiểm tra connector lifecycle và listening socket |
| \`ConnectException: Connection timed out\` | Firewall, route, host không tới được | Kiểm tra network path và advertised host |
| \`NameNotFoundException: jmxrmi\` | Registry không có binding \`jmxrmi\` | Kiểm tra RMI naming và URL |
| Lookup được nhưng invoke thất bại | RMI stub quảng bá host/port không reachable | Kiểm tra \`java.rmi.server.hostname\` và connector endpoint |
| \`SSLHandshakeException\` | Trust/keystore/protocol mismatch | Kiểm tra TLS fixture và chứng chỉ |
| \`IOException\` khi remote call | Kết nối bị đóng, server restart hoặc transport lỗi | Liên kết logs client/server theo thời điểm |
| Client thao tác nhầm server | Cùng domain/name trên một JVM khác | Xác minh JVM identity, PID và endpoint |

**Quan trọng:** \`java.rmi.server.hostname\` là property JVM ảnh hưởng thông tin host mà RMI object quảng bá. Nó không tự mở cổng, không thay firewall rules và không bảo đảm đúng địa chỉ khi ứng dụng chạy trong container.

Trong Kubernetes/Docker, \`127.0.0.1\` trong container client khác với \`127.0.0.1\` ở container server. Cần thiết kế network riêng và advertised endpoint phù hợp nếu kiểm thử cross-container.

## 12. Bật logging JMX/RMI của JDK

Không phải mọi JMX/RMI log đều đi qua SLF4J/Logback logger của Spring. Với JDK, thông tin chẩn đoán có thể dùng \`java.util.logging\` (JUL), Java Flight Recorder, JVM management logs hoặc cơ chế provider-specific.

Một cấu hình JUL test minh họa:

\`\`\`properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

javax.management.level=FINE
javax.management.remote.level=FINE
sun.rmi.level=FINE
\`\`\`

Khởi chạy JVM với:

\`\`\`bash
java -Djava.util.logging.config.file=jmx-logging.properties \
     -cp target/classes com.example.Main
\`\`\`

Tên logger cụ thể của JDK/provider và lượng sự kiện được ghi **có thể thay đổi theo JDK version**. Một số cấu hình JMX nội bộ có thể dùng logger khác, và log chi tiết của RMI phụ thuộc implementation. Vì vậy xem JUL như nguồn bổ sung, không phải bằng chứng chắc chắn mọi sự kiện kết nối sẽ xuất hiện trong một logger cụ thể.

Khi debug production, ưu tiên bật trong môi trường tái hiện hoặc trong khoảng ngắn, vì logging transport chi tiết có thể tăng chi phí và chứa thông tin hạ tầng.

## 13. Log connector startup và shutdown trong ứng dụng

Với connector tự tạo, nên ghi các sự kiện lifecycle rõ:

\`\`\`java
JMXConnectorServer connector =
        JMXConnectorServerFactory.newJMXConnectorServer(
                serviceUrl, environment, mBeanServer);

try {
    connector.start();
    logger.info("JMX connector started: {}", connector.getAddress());
} catch (IOException e) {
    logger.error("JMX connector start failed", e);
    throw e;
}
\`\`\`

Trong shutdown:

\`\`\`java
try {
    connector.stop();
    logger.info("JMX connector stopped");
} catch (IOException e) {
    logger.error("Failed to stop JMX connector", e);
}
\`\`\`

Chỉ ghi service URL khi không chứa credential hoặc thông tin nhạy cảm. Một số môi trường dùng query parameters hoặc service discovery chứa dữ liệu cần ẩn; cần áp dụng logging policy phù hợp.

Trong Spring, một \`JMXConnectorServer\` có thể được khai báo bean với \`destroyMethod="stop"\` hoặc bọc bằng \`SmartLifecycle\` để kiểm soát thời điểm start/stop. Nếu connector khởi động trước exporter, client có thể kết nối thành công nhưng MBean chưa được đăng ký. Đây là một lỗi timing/lifecycle, không phải lỗi transport.

## 14. Chứng minh đúng MBeanServer

Một lỗi phổ biến là kiểm tra platform server trong khi exporter đăng ký vào custom server khác:

\`\`\`java
MBeanServer platform =
        ManagementFactory.getPlatformMBeanServer();

System.out.println(platform.isRegistered(name));
\`\`\`

Nếu exporter dùng \`MBeanServerFactoryBean\` custom, kết quả \`false\` trên platform không có nghĩa exporter thất bại.

Cách đúng là lấy **chính server mà exporter được inject**:

\`\`\`java
MBeanServer server = context.getBean(
        "applicationMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

System.out.println(server.isRegistered(name));
\`\`\`

Nếu có nhiều \`MBeanServer\` beans, dùng qualifier/tên bean rõ ràng. Tên \`ObjectName\` chỉ duy nhất trong **một server**, không duy nhất trên mọi JVM/server. Hai server có thể chứa cùng tên nhưng trỏ tới hai MBeans khác nhau.

Khi client remote đang xem một connector, cần xác nhận connector đó gắn với server nào. Chỉ biết PID không đủ nếu một JVM tạo nhiều servers.

## 15. Một probe chẩn đoán có cấu trúc

Có thể viết một lệnh nhỏ chạy trong JVM để xuất dữ liệu cần thiết mà không cần thao tác trên JConsole:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class JmxDiagnosticProbe {

    public static void inspect(
            MBeanServer server,
            ObjectName expected,
            String domainPattern) throws Exception {

        System.out.println("defaultDomain="
                + server.getDefaultDomain());

        System.out.println("registered="
                + server.isRegistered(expected));

        Set<ObjectName> matches =
                server.queryNames(
                        new ObjectName(domainPattern), null);

        for (ObjectName name : matches) {
            System.out.println(
                    "objectName=" + name.getCanonicalName());
        }

        if (!server.isRegistered(expected)) {
            return;
        }

        MBeanInfo info = server.getMBeanInfo(expected);

        System.out.println("class=" + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.println(
                    "attribute=" + attribute.getName()
                    + ",type=" + attribute.getType()
                    + ",readable=" + attribute.isReadable());
        }

        for (var operation : info.getOperations()) {
            System.out.println(
                    "operation=" + operation.getName());
        }
    }
}
\`\`\`

Cách gọi:

\`\`\`java
JmxDiagnosticProbe.inspect(
        server,
        new ObjectName(
                "com.example.orders:type=QueueMonitor,name=primary"),
        "com.example.orders:*");
\`\`\`

Probe cho biết: server đang kiểm tra có entry nào, tên đúng là gì và management interface cuối cùng có những gì.

**Không gọi operation có side effect chỉ để thử connectivity** khi chưa hiểu hành vi. Đọc \`isRegistered\`, \`getMBeanInfo\` và các read-only attributes trước.

## 16. Phân biệt logs của exporter, MBeanServer và connector

| Nguồn log | Tập trung vào | Không thể kết luận một mình |
| --- | --- | --- |
| Spring exporter | Bean selection, assembler, naming, registration | Connector từ xa có reachable hay không |
| MBeanServer/registry probe | Tên đã đăng ký, metadata, attributes | Remote client có đi qua firewall/TLS được hay không |
| Connector startup logs | Endpoint, port, lifecycle, transport errors | MBean cụ thể có xuất đúng management contract hay không |
| Client logs | URL, connect, auth, query, invoke outcome | Server-side operation có hoàn thành sau client timeout không |
| Application service logs | Operation logic, database/network dependencies | JMX transport đã kết nối chính xác hay không |

Một quy trình hiệu quả kết hợp các nguồn này theo cùng một thời điểm, không dùng một dòng log duy nhất để kết luận hệ thống hoạt động end-to-end.

## 17. Quy trình khoanh vùng theo bước

### Bước 1 — Xác nhận JVM và ApplicationContext

Thu thập PID, application name, context ID, environment/profile và thời điểm khởi động. Đọc startup logs xem context có hoàn tất refresh hay bị \`BeanCreationException\`.

Nếu context không khởi tạo thành công, tiếp tục đọc root cause trước khi đi sâu remote connector.

### Bước 2 — Kiểm tra exporter

Xác định \`MBeanExporter\` có được khai báo hoặc annotation-driven exporter có được bật không. Kiểm tra mapping \`beans\`, autodetection, assembler, naming strategy và registration policy.

Đối với Spring Boot, kiểm tra auto-configuration JMX để tránh hai exporters cùng đăng ký.

### Bước 3 — Xác nhận server và ObjectName

Dùng \`server.isRegistered(name)\`, \`queryNames\`, và \`getMBeanInfo\` trên đúng server mà exporter dùng. Nếu object không có, tập trung vào registration. Nếu có nhưng thiếu method, tập trung vào management metadata.

### Bước 4 — Kiểm tra connector

Xác định \`JMXConnectorServer\` đã start, bind đúng interface, URL có thể dùng, RMI registry/remote object host-port không sai và credentials/TLS được cấu hình.

### Bước 5 — Kiểm tra client

Dùng một JMX client có địa chỉ/credentials đúng, gọi một read-only attribute hoặc \`getMBeanInfo\`. Nếu client kết nối được nhưng operation không chạy, xem signature/authorization/exception từ target.

### Bước 6 — Liên kết server-side và client-side log

Đối chiếu timestamp, operation name, request ID hoặc job ID. Nếu client timeout, không tự kết luận server không chạy. Kiểm tra trạng thái nghiệp vụ hoặc terminal outcome.

### Bước 7 — Ghi nhận nguyên nhân gốc

Mỗi kết luận cần bằng chứng như:

\`\`\`text
Symptom:
  JConsole connects, QueueDepth is missing.

Evidence:
  isRegistered(ObjectName) = true.
  MBeanInfo contains PendingCount, not QueueDepth.
  Exporter uses InterfaceBasedMBeanInfoAssembler.

Root cause:
  Management interface does not expose getQueueDepth().

Fix:
  Update the management contract deliberately; test metadata.

Verification:
  MBeanInfo now exposes QueueDepth; read-only query succeeds.
\`\`\`

Không nên chỉ ghi “JMX lỗi” hoặc “đã restart nên hết lỗi” vì không giúp ngăn tái diễn.

## 18. Khi nhiều ApplicationContext hoặc exporter cùng chạy

Một JVM có thể có root context, child context hoặc nhiều plugin modules, tất cả sử dụng platform \`MBeanServer\`.

Các lỗi:

- Hai exporters cùng một \`ObjectName\`.
- Context cũ chưa đóng, registration chưa unregister.
- \`IGNORE_EXISTING\` khiến MBean mới không được đăng ký.
- \`REPLACE_EXISTING\` thay target và gây ảnh hưởng khi owner cũ đóng.
- Custom server được release khi context khác vẫn dùng.

Để chẩn đoán, log context ID/owner với mỗi registration do ứng dụng tạo. Khi có xung đột, xác định exporter nào đã đăng ký trước, policy được áp dụng và target instance hiện đang ở registry.

Không dùng \`unregisterMBean(name)\` tùy tiện trong production chỉ để “làm sạch” khi chưa xác định owner. Có thể xóa MBean của một component khác.

## 19. Ví dụ Spring Java Config có log rõ

\`\`\`java
@Configuration
public class DiagnosticJmxConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticJmxConfiguration.class);

    @Bean
    public MBeanServer platformMBeanServer() {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        log.info("Using JMX server defaultDomain={}",
                server.getDefaultDomain());
        return server;
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter exporter(
            QueueMonitor queueMonitor,
            MBeanServer platformMBeanServer) {

        String objectName =
                "com.example.orders:type=QueueMonitor,name=primary";

        log.info("Preparing MBean export objectName={}", objectName);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(
                java.util.Map.of(objectName, queueMonitor));
        return exporter;
    }
}
\`\`\`

Trong ví dụ này, log trong \`@Bean\` chỉ nói exporter đã **được cấu hình**, chưa chứng minh đăng ký thành công. Registration thường diễn ra sau đó trong lifecycle của exporter. Để ghi \`REGISTERED\` một cách chính xác, cần quan sát callback/lifecycle hoặc kiểm tra \`server.isRegistered(name)\` sau khi exporter hoàn tất khởi tạo.

Trong project thật, imports tương ứng đến từ Spring context, JMX, SLF4J và \`ManagementFactory\`; \`QueueMonitor\` là một MBean fixture phù hợp với hợp đồng JMX mà bạn tự định nghĩa.

## 20. Kiểm thử tự động cho sự cố từng tầng

Một suite test tốt cần chia theo tầng:

**Test 1 — Registration:** khởi tạo Spring context với exporter và server test, assert \`isRegistered\`.

**Test 2 — Metadata:** assert attributes/operations mong đợi trong \`MBeanInfo\`.

**Test 3 — Conflict:** cố tạo hai registrations trùng tên trong server test cô lập, xác nhận policy mong muốn.

**Test 4 — Local invocation:** gọi một read-only attribute và một operation an toàn qua \`MBeanServer\`.

**Test 5 — Remote connector:** tạo \`JMXConnectorServer\` loopback trong fixture, kết nối bằng \`JMXConnectorFactory.connect\` và đọc attribute qua \`MBeanServerConnection\`.

**Test 6 — Security:** với một fixture có authentication/TLS thực sự, kiểm tra credentials sai/đúng và quyền operation.

**Test 7 — Shutdown:** đóng context, xác minh exporter unregister đúng MBeans và connector stop theo owner.

Các test này giúp phân biệt “registration hỏng” với “connector hỏng” mà không phải mở production endpoint để thử.

## 21. Ghi log trong môi trường container và distributed deployment

Khi ứng dụng Spring chạy trong Docker hoặc Kubernetes, nên log:

- Pod/container identity và process PID.
- Application context/profile/instance ID.
- JMX domain/\`ObjectName\`.
- Connector bind address và advertised host không nhạy cảm.
- Registry port và remote object port khi dùng RMI.
- Thời điểm start/stop connector.
- Error category và root cause.
- Correlation/job ID cho operation có side effect.

Không giả định rằng \`127.0.0.1\` trong client container là loopback của server container. Nếu client kết nối tới hostname container/pod khác, RMI stub cũng phải quảng bá host và port mà client truy cập được.

Nếu endpoint dùng \`kubectl port-forward\`, cần hiểu rằng RMI có thể sử dụng port thứ hai, nên chỉ forward registry port đôi khi không đủ. Cần cấu hình connector/server port phù hợp với đường truy cập và kiểm tra thực tế.

## 22. Log và bảo mật: không tạo lỗ hổng khi debug

Trong quá trình điều tra, dễ bị cám dỗ bật TRACE toàn hệ thống hoặc in toàn bộ environment của connector. Điều này có thể làm lộ:

- Credentials JMX.
- Mật khẩu keystore/truststore.
- Authentication tokens.
- Địa chỉ nội bộ nhạy cảm.
- Stack trace chứa dữ liệu request.
- Nội dung của attributes hoặc operation parameters.

Nguyên tắc:

1. Chỉ tăng logging ở package cần thiết.
2. Giới hạn thời gian bật DEBUG/TRACE.
3. Redact secrets và thông tin cá nhân.
4. Không gọi operation nguy hiểm để kiểm tra kết nối.
5. Dùng môi trường test/cô lập khi cần tái hiện.
6. Lưu bằng chứng đủ phục vụ phân tích nhưng không đăng tải log raw lên nơi công khai.

Nếu nghi ngờ lỗi authentication, đừng khắc phục bằng cách vô hiệu hóa toàn bộ xác thực trên endpoint production. Dùng fixture test riêng để phân biệt lỗi mật khẩu, TLS và network.

## 23. Các câu hỏi chẩn đoán nhanh

| Câu hỏi | Nếu câu trả lời là “không” | Điều tra tiếp |
| --- | --- | --- |
| Spring context đã khởi tạo thành công? | Có thể thiếu bean/exporter | Startup và bean logs |
| Exporter được tạo? | Không có registration pipeline | Cấu hình IoC, annotation enable |
| Managed bean được chọn? | Không được export | \`setBeans\`/autodetection |
| \`ObjectName\` có trong đúng server? | Registration/naming lỗi | Exporter và MBeanServer |
| \`MBeanInfo\` đúng? | Interface/assembler lỗi | Metadata, annotations |
| Local getAttribute thành công? | Contract hoặc target lỗi | Attribute name, exception |
| Connector đã start? | Remote endpoint chưa hoạt động | Connector lifecycle logs |
| Client connect thành công? | Network, RMI, auth, TLS | Client/transport logs |
| Remote read thành công? | ObjectName/server mismatch | Client target, metadata |
| Operation có outcome rõ? | Logic bị block/fail | App logs, timeout, job status |

## 24. Bài tập thực hành

**Bài 1 — Trùng ObjectName:** tạo hai exporters dùng chung platform server, cùng tên \`com.example:type=Monitor,name=primary\`. Ghi nhận root cause và sửa naming.

**Bài 2 — Sai server:** exporter đăng ký vào custom \`MBeanServer\` nhưng diagnostic code đọc platform server. So sánh kết quả \`isRegistered\` và giải thích vì sao JConsole có thể không thấy custom server.

**Bài 3 — Thiếu attribute:** tạo một MBean chỉ công bố \`QueueDepth\`, sau đó gọi \`getAttribute(name, "PendingCount")\`. Đọc \`MBeanInfo\` và xác định lỗi nằm ở metadata/client, không phải transport.

**Bài 4 — Connector RMI:** tạo fixture local loopback, khởi động \`JMXConnectorServer\`, kết nối bằng remote client. Cố tình cấu hình sai hostname quảng bá trong môi trường test để quan sát lỗi lookup/invoke.

**Bài 5 — Context shutdown:** đăng ký MBean, đóng \`ApplicationContext\`, rồi đọc registry. Liên hệ với log exporter unregister và phân biệt server vẫn sống với MBean đã bị gỡ.

**Bài 6 — Timeline:** thu thập logs từ Spring context, exporter, connector và client; sắp xếp theo timestamp và viết báo cáo \`symptom → evidence → root cause → fix → verification\`.

## Kết luận

**Đọc log exporter, MBeanServer và connector để khoanh vùng** là kỹ năng cốt lõi khi chẩn đoán Spring Framework JMX. Hãy chia đường đi thành những tầng cụ thể: Spring context tạo bean, exporter chọn/đăng ký MBean, server lưu \`ObjectName\` và metadata, connector mở remote endpoint, client kết nối rồi thực hiện lời gọi. Kết hợp logs với \`isRegistered\`, \`queryNames\`, \`getMBeanInfo\` và các phép đọc an toàn để xác định lỗi thuộc tầng nào. Một kết luận có giá trị luôn gắn với bằng chứng về **JVM, server, ObjectName, phase, exception và outcome**, thay vì chỉ dựa vào một thông báo cuối cùng.
