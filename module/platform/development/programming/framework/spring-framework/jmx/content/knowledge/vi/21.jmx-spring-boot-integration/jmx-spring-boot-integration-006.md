# JMX trong ứng dụng Spring Boot chạy embedded server

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của **embedded web server** trong Spring Boot và mối quan hệ giữa **JVM**, **Spring ApplicationContext**, **MBeanServer** và máy chủ web nhúng.
- Phân biệt MBean **JVM mặc định**, **Spring JMX**, **Spring Boot Actuator**, và MBean do **Tomcat/Jetty/Undertow** công bố khi thực sự được bật.
- Hiểu rằng mở HTTP port của embedded server không đồng nghĩa mở JMX port, và bật \`spring.jmx.enabled\` không tự bật remote JMX/RMI.
- Cấu hình export MBean cho ứng dụng Spring Boot chạy dạng executable JAR, có hoặc không có Actuator.
- Kiểm tra MBean thực tế bằng \`ManagementFactory.getPlatformMBeanServer()\`, \`ObjectName\`, \`MBeanInfo\` và JConsole.
- Nhận diện khác biệt của việc công bố MBean từ embedded Tomcat so với JMX endpoints của ứng dụng.
- Cân nhắc vận hành trong Docker/Kubernetes: port, RMI hostname, lifecycle, health/readiness và quyền truy cập.
- Xây dựng quy trình kiểm tra, hạn chế xung đột ObjectName và bảo vệ bề mặt quản trị của server nhúng.

## 2. Embedded server trong Spring Boot là gì?

Ứng dụng Spring Boot dạng web thường dùng một server nhúng để chạy HTTP trực tiếp trong JVM, thay vì đóng gói WAR và triển khai thủ công lên một ứng dụng server bên ngoài.

Ví dụ cấu trúc khi khởi chạy:

\`\`\`text
java -jar order-service.jar
          |
          v
   JVM process / PID
          |
          +-- Spring ApplicationContext
          |      |
          |      +-- Controllers, Services, Repositories
          |      +-- Application MBeans (nếu export)
          |      +-- Spring Boot Actuator (nếu có)
          |
          +-- Embedded Web Server
          |      +-- Tomcat hoặc Jetty hoặc Undertow
          |      +-- HTTP connectors, threads, sessions...
          |
          +-- Platform MBeanServer
                 +-- JVM built-in MBeans
                 +-- Spring-exported MBeans
                 +-- Server-specific MBeans (nếu đăng ký)
\`\`\`

Các thành phần cùng tồn tại trong **một JVM**, nhưng có trách nhiệm khác nhau. Một web server được nhúng không tự động biến mọi internal object của nó thành MBean có thể quản trị. Việc các MBean của container xuất hiện còn phụ thuộc server implementation, phiên bản và cách cấu hình.

### 2.1. Các server nhúng thường gặp

| Server | Vai trò | Điểm cần chú ý về JMX |
| --- | --- | --- |
| Embedded Tomcat | Servlet web server thường dùng trong Spring Boot | Có cơ chế JMX MBean registry; mức bật/đăng ký có thể khác khi chạy embedded so với standalone. |
| Embedded Jetty | Servlet web server có mô-đun quản trị riêng | Các MBean hoặc module JMX không nhất thiết được bật tự động trong mọi cấu hình nhúng. |
| Embedded Undertow | Web server hỗ trợ Servlet và I/O hiệu năng cao | Khả năng công bố JMX cần xác nhận theo phiên bản và tích hợp sử dụng, không suy ra từ Tomcat. |
| Reactor Netty | Web server reactive của Spring WebFlux | Không phải servlet embedded container; metrics/observability và JMX exposure đi theo cơ chế khác. |

Ứng dụng có thể sử dụng server không nằm trong danh sách này. Vì vậy, khi thiết kế kiểm tra JMX, bắt đầu bằng **server factory/dependency đang chạy**, không chỉ bởi tên starter Maven.

## 3. JMX có những lớp nào trong một ứng dụng embedded?

### 3.1. JVM platform MBeans

JDK thông thường công bố các MBean quản lý runtime như:

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
java.lang:type=OperatingSystem
java.lang:type=GarbageCollector,name=...
\`\`\`

JConsole hoặc JMX client kết nối đúng JVM có thể quan sát memory, threads, class loading và GC. Những MBean này không đòi hỏi bạn tự viết \`@ManagedResource\`.

Một ứng dụng không bật \`spring.jmx.enabled\` vẫn có thể có các MBean do JVM tạo.

### 3.2. Spring-exported MBeans

Spring Framework sử dụng \`MBeanExporter\` để công bố các bean quản trị đã chọn. Annotation thường gặp:

- \`@ManagedResource\`: xác định resource JMX.
- \`@ManagedAttribute\`: công bố getter/setter.
- \`@ManagedOperation\`: công bố hành động.
- \`@ManagedOperationParameter\`: mô tả tham số operation.

Ví dụ một bean nghiệp vụ có thể công bố \`QueueDepth\` hoặc \`requestPause()\` mà không phụ thuộc máy chủ web đang dùng.

### 3.3. Spring Boot Actuator JMX endpoints

Nếu có Spring Boot Actuator và cấu hình exposure phù hợp, một số endpoint như health/info/metrics có thể được công bố qua JMX. Đây là hệ thống **endpoint management** của Boot, không phải toàn bộ API Tomcat.

Các endpoint Actuator cần kiểm tra theo phiên bản Spring Boot: tên JMX MBean, exposure mặc định, cấu hình security và dữ liệu có thể khác nhau.

### 3.4. Web server MBeans

Embedded Tomcat/Jetty có thể đăng ký MBean liên quan connector, thread pool, session, web application hoặc tài nguyên khác, nhưng chỉ khi các cơ chế JMX tương ứng được sử dụng. Việc mở cổng \`server.port=8080\` không xác nhận các MBean đó đã được đăng ký.

**Bài học quan trọng:** bốn lớp MBean có thể cùng nằm trong một \`MBeanServer\` nhưng hoàn toàn không đồng nhất.

## 4. Phân biệt HTTP port và JMX connector

Khi Spring Boot khởi chạy:

\`\`\`properties
server.port=8080
\`\`\`

ứng dụng sẽ cấu hình HTTP listener trên port 8080 theo server factory. Điều đó **không** mở JMX/RMI port.

Cũng vậy:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

chủ yếu liên quan đến cơ chế JMX auto-configuration và export của Spring Boot khi điều kiện tương ứng thỏa mãn. Nó không tương đương:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
\`\`\`

Hai đường kết nối:

\`\`\`text
HTTP client
    |
    | HTTP/HTTPS :8080
    v
Embedded Tomcat/Jetty/Undertow
    |
    v
Spring MVC / WebFlux application

JMX client (JConsole, JMX exporter)
    |
    | Local attach hoặc JMX connector/RMI :9010
    v
MBeanServer
    |
    +-- JVM MBeans
    +-- Spring MBeans
    +-- Container-specific MBeans
\`\`\`

Không vì thấy ứng dụng HTTP hoạt động mà kết luận JMX remote đã sẵn sàng. Ngược lại, JMX local vẫn có thể hoạt động khi HTTP server chưa bắt đầu nhận traffic, tùy lifecycle.

## 5. Cấu hình Spring Boot JMX cơ bản

Đối với ứng dụng Spring Boot dùng JMX auto-configuration, thuộc tính thường gặp:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Một resource được đánh dấu:

\`\`\`java
package example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Primary",
    description = "Order queue monitoring"
)
public class QueueManagement {

    @ManagedAttribute(description = "Current pending messages")
    public long getPendingMessages() {
        return 42L;
    }
}
\`\`\`

Khi JMX exporter được kích hoạt và metadata annotations được xử lý, bean có thể xuất hiện ở:

\`\`\`text
com.example.orders:type=Queue,name=Primary
\`\`\`

Sau khi khởi động ứng dụng, đọc lại MBeanServer để xác minh. Không mặc định rằng \`@Component\` hoặc annotation trên class tự bảo đảm exporter đã đăng ký thành công.

### 5.1. Tránh exporter trùng

Trong ứng dụng Boot, nên xác định rõ có dùng **Boot-managed exporter** hay tạo **\`MBeanExporter\` thủ công**. Nếu cả hai cùng chọn một bean/ObjectName, có thể xảy ra \`InstanceAlreadyExistsException\` hoặc một cấu hình bỏ qua/thay thế MBean ngoài mong muốn.

Đừng giải quyết bằng cách tự động chuyển sang \`REPLACE_EXISTING\` mà chưa xác định owner của tên MBean.

## 6. Actuator có bắt buộc để dùng JMX không?

**Không.** Spring JMX và JVM platform MBeans không bắt buộc phải có Spring Boot Actuator.

Ví dụ dependency Actuator nếu dự án muốn endpoints:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

Điều này bổ sung cơ chế Actuator endpoints. Ứng dụng vẫn cần cấu hình exposure thích hợp để endpoint nào đó được công bố qua JMX.

Ví dụ property:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Đây là ví dụ về ý định expose endpoint. Tên và danh sách endpoint thực tế phụ thuộc dependencies, enablement và phiên bản Boot. Trong Spring Boot hiện đại, hãy kiểm tra tài liệu của phiên bản đang dùng để xác định default exposure, cấu hình include/exclude và endpoint-specific behavior.

### 6.1. Actuator web exposure khác JMX exposure

Các property như:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info
\`\`\`

điều khiển **hai kênh exposure khác nhau**. Đặt chỉ web exposure không đồng nghĩa JMX có danh sách y hệt.

Tương tự, các thiết lập HTTP security không nhất thiết bảo vệ remote JMX connector. Việc định tuyến, TLS, xác thực và quyền của JMX phải được thiết kế riêng.

## 7. Embedded Tomcat và MBean container

Tomcat cung cấp hạ tầng JMX riêng để quản trị các đối tượng như connectors và thread pools. Trong trường hợp Tomcat chạy như ứng dụng server độc lập, bộ MBeans có thể khác với Tomcat được nhúng trong Spring Boot.

Một số tên quản trị Tomcat có dạng:

\`\`\`text
Catalina:type=ThreadPool,name="http-nio-8080"
Catalina:type=GlobalRequestProcessor,name="http-nio-8080"
Catalina:type=Connector,port=8080
\`\`\`

Các tên trên **chỉ là ví dụ minh họa**: domain, protocol, connector name, key properties và sự hiện diện thực tế phụ thuộc Tomcat version, connector và việc bật cơ chế JMX.

**Không coi việc không thấy domain \`Catalina\` là lỗi nếu embedded Tomcat chưa bật đăng ký container MBean.** Cũng không khẳng định mọi Tomcat embedded luôn đăng ký đầy đủ như standalone.

### 7.1. Cấu hình registry trong embedded Tomcat

Với một số phiên bản Spring Boot/Tomcat, có thể cần bật JMX registration cho embedded Tomcat thông qua cách cấu hình container cụ thể. Ví dụ ý tưởng tùy biến:

\`\`\`java
import org.apache.catalina.core.StandardService;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.context.annotation.Bean;

// Đây là khung tham khảo: các API cần kiểm tra
// theo Spring Boot/Tomcat version cụ thể.
\`\`\`

Các API bật registry của Tomcat có thể thay đổi giữa phiên bản và không được xem là public stable contract cho mọi Boot release. Thay vì sao chép một cấu hình cũ bất kỳ, cần xác nhận tài liệu Tomcat/Boot đúng phiên bản và kiểm tra \`queryNames\` để biết hiệu lực thực tế.

Một số hạ tầng cài đặt Tomcat có registry riêng và cơ chế \`LifecycleMBeanBase\`. Khi chạy embedded, Spring Boot quản lý vòng đời Tomcat, nên việc đăng ký/hủy đăng ký MBean container diễn ra theo chính sách của factory/server tương ứng.

## 8. Kiểm tra MBean của JVM, Spring và embedded server

Ví dụ đọc các domain và MBean names từ platform server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

for (String domain : server.getDomains()) {
    System.out.println("Domain: " + domain);
}

for (ObjectName name : server.queryNames(null, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Đoạn trên có thể dùng trong **lab** để khảo sát. Trong production, liệt kê toàn bộ tên có thể tạo log lớn và lộ topology. Nên thu hẹp theo domain hoặc prefix đã biết:

\`\`\`java
for (ObjectName name :
        server.queryNames(
            new ObjectName("com.example.orders:*"),
            null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Đối với Tomcat, khi domain có mặt và bạn được phép chẩn đoán:

\`\`\`java
for (ObjectName name :
        server.queryNames(
            new ObjectName("Catalina:*"),
            null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Nếu kết quả rỗng, chưa thể kết luận embedded server không hoạt động. Cần kiểm tra \`server.port\`, lifecycle, phiên bản và cách server đăng ký JMX.

### 8.1. Kiểm tra một ObjectName cụ thể

\`\`\`java
ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,name=Primary"
);

boolean registered = server.isRegistered(expected);

System.out.println("Registered = " + registered);
\`\`\`

\`true\` chỉ xác nhận tên đang tồn tại; để biết giao diện nào được công bố, đọc thêm \`getMBeanInfo\`.

## 9. Đọc MBeanInfo runtime

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, read=%s, write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, impact=%d%n",
        operation.getName(),
        operation.getImpact()
    );
}
\`\`\`

Cần đọc metadata thực tế sau export, nhất là khi một operation có thể làm thay đổi trạng thái server hoặc ứng dụng.

Một MBean container có thể expose thêm operation đặc thù như quản lý connector. Nếu remote JMX mở với quyền cao, các operation đó trở thành bề mặt quản trị cần bảo vệ.

### 9.1. MBeanInfo không phải dữ liệu runtime value

\`MBeanInfo\` mô tả tên, kiểu, quyền đọc/ghi và operation. Giá trị thực tế được đọc bằng \`getAttribute\`, có thể kích hoạt getter tương ứng. Getter JMX từ thư viện/container không nên bị gọi polling ở tần suất quá cao nếu chi phí chưa được đánh giá.

## 10. Xem qua JConsole

Các bước:

1. Khởi chạy ứng dụng Spring Boot dạng JAR với embedded server.
2. Mở \`jconsole\` từ JDK.
3. Chọn đúng Java process trong danh sách **Local Process** nếu chạy cùng host.
4. Mở tab **MBeans**.
5. Quan sát domain \`java.lang\`, domain ứng dụng (\`com.example.orders\`) và các domain server-specific nếu có.
6. Chọn một MBean, xem **Attributes**, **Operations** và metadata được công cụ hỗ trợ.
7. Không invoke những operation có side effect trong production chỉ để thử.

Khi JConsole không tìm thấy app trong Local Process, kiểm tra PID, user/attach permission, container namespace và JDK đang dùng. Không cần bật remote JMX chỉ để xem local khi attach được hỗ trợ.

### 10.1. Đừng nhầm hai loại port trong JConsole

Khi chọn **Remote Process** và nhập \`host:port\`, đó phải là endpoint JMX connector của JVM, **không** phải HTTP port của embedded server.

Ví dụ:

\`\`\`text
HTTP:
  localhost:8080

Remote JMX (nếu đã cấu hình riêng):
  localhost:9010
\`\`\`

Việc nhập \`localhost:8080\` vào trường Remote Process sẽ không làm JConsole tự dùng Actuator HTTP.

## 11. Bật remote JMX cho lab

Để quan sát từ một máy client khác, JVM cần remote JMX connector hoặc cơ chế kết nối phù hợp. Với JMX/RMI management agent của HotSpot/OpenJDK, cấu hình lab cô lập trên loopback có thể là:

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -jar order-service.jar
\`\`\`

**Cảnh báo:** cấu hình \`authenticate=false\` và \`ssl=false\` chỉ phù hợp với môi trường lab cô lập có kiểm soát. Không mở endpoint này ra internet hoặc mạng không tin cậy.

Giải thích:

- \`jmxremote.port\`: cổng ban đầu của JMX/RMI connector.
- \`jmxremote.rmi.port\`: cố định cổng RMI server để tránh cổng động khó đi qua firewall/NAT.
- \`java.rmi.server.hostname\`: địa chỉ mà RMI stub quảng bá cho client; \`127.0.0.1\` phù hợp khi client cùng host hoặc tunnel tương thích.
- \`authenticate\` và \`ssl\`: các cài đặt bảo mật connector, cần cấu hình đúng với production.

Với kết nối từ host khác, hostname phải được quảng bá theo đường mạng thực sự có thể truy cập; không chỉ mở registry port là đủ.

### 11.1. Bảo vệ remote JMX production

Một hướng vận hành phù hợp thường gồm:

- Mạng quản trị riêng hoặc VPN/tunnel.
- Authentication và authorization cho JMX connector.
- TLS với truststore/certificate đúng cấu hình.
- Cổng được cố định và firewall chỉ cho phép nguồn đáng tin.
- Không expose internet trực tiếp.
- Không đưa password vào command line hoặc repository.
- Ghi log/audit các thao tác quản trị quan trọng.
- Thực hiện kiểm tra quyền cho operation thay đổi trạng thái.

Nếu phải dùng SSH tunnel, hãy đảm bảo cả RMI registry endpoint và địa chỉ/cổng trong RMI stub tương thích với tunnel. Một tunnel duy nhất tới registry port không giải quyết được endpoint thứ hai khi còn dùng cổng động.

## 12. Embedded server chạy trong Docker

Docker tạo network namespace riêng. Những điểm cần nhớ:

1. Container có HTTP listener bên trong, ví dụ \`8080\`.
2. Port mapping \`-p 8080:8080\` cho phép bên ngoài truy cập HTTP, **không** chuyển tiếp JMX.
3. Nếu JVM bật JMX trên \`9010\`, phải quyết định có cần port mapping/tunnel riêng không.
4. RMI stub có thể quảng bá \`127.0.0.1\` **bên trong** container hoặc một hostname không truy cập được từ host client.
5. Chỉ map một port JMX khi RMI endpoint phù hợp với port đã được map.
6. Không nên publish JMX port ra mạng công khai chỉ vì cần chẩn đoán nhanh.

Ví dụ một container lab có thể cấu hình JVM JMX cùng cổng registry/RMI và kết nối qua đường chuyển tiếp bảo vệ. Nhưng thiết lập chính xác phụ thuộc Docker network mode, host OS, JDK và địa chỉ RMI được quảng bá.

### 12.1. HTTP health còn tốt nhưng JMX không hoạt động?

Điều đó hoàn toàn có thể xảy ra. HTTP server và JMX connector là hai subsystem. \`GET /actuator/health\` có thể trả kết quả trong khi JMX remote port đóng hoặc MBean exporter không được bật.

Ngược lại, JVM còn chạy và JMX local có thể phản hồi khi HTTP server đang lỗi startup hoặc không bind được port.

## 13. Kubernetes và port-forward

Trong Kubernetes, ứng dụng Spring Boot thường nằm trong Pod với network namespace riêng. Các trường hợp phổ biến:

- HTTP Service/Ingress định tuyến traffic tới embedded server.
- JMX chỉ dùng nội bộ hoặc qua port-forward.
- MBeanServer nằm trong JVM của container, không phải trong Kubernetes control plane.
- Cổng JMX không tự tạo Kubernetes Service; phải cấu hình khi cần.
- \`kubectl port-forward\` chuyển tiếp port đã chọn, nhưng RMI stub vẫn phải trỏ đến địa chỉ/cổng mà client có thể truy cập.

Một kết nối lab có thể dùng:

\`\`\`bash
kubectl port-forward pod/order-service-abc123 9010:9010
\`\`\`

Sau đó JConsole thử kết nối \`localhost:9010\` **nếu** JVM JMX/RMI được cấu hình tương thích với port-forward và RMI advertised host/port. Pod name chỉ minh họa.

**Không** xem port-forward là cơ chế tự động xử lý mọi vấn đề của JMX/RMI. Với môi trường production, việc access Pod và port-forward cần RBAC/Kubernetes audit phù hợp.

## 14. Lifecycle của embedded server và MBean

Trong Spring Boot, web server được quản lý theo vòng đời của ApplicationContext. Điều này liên quan tới JMX ở các điểm:

- Khi context khởi tạo, các Spring beans và exporter có thể được đăng ký trước hoặc sau một số thành phần web server tùy lifecycle.
- Embedded server có thể chỉ đăng ký MBean riêng sau khi container khởi động hoặc registry được bật.
- Khi ApplicationContext đóng bình thường, các thành phần liên quan có thể unregister MBean và cleanup.
- Nếu JVM bị kill cứng, không có bảo đảm callback unregister hoặc cleanup Java code được chạy.
- Khi ứng dụng restart, JMX client cũ cần kết nối lại với JVM process/endpoint mới.

### 14.1. Không truy vấn quá sớm

Ví dụ một bean \`@PostConstruct\` muốn thấy ngay MBean của Tomcat có thể truy vấn khi container chưa hoàn tất khởi động. Khi đó \`queryNames\` có thể rỗng dù MBean sau này xuất hiện.

Một lựa chọn tốt hơn là kiểm tra sau khi Spring Boot đã phát \`ApplicationReadyEvent\`, hoặc sau một điểm lifecycle được dự án xác định phù hợp. Tuy nhiên cũng cần kiểm tra khả năng container MBean chưa được bật: chờ lâu hơn không tạo ra MBean nếu registry bị tắt.

## 15. Ví dụ kiểm tra sau ApplicationReadyEvent

\`\`\`java
package example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class JmxStartupInspector {

    @EventListener(ApplicationReadyEvent.class)
    public void inspectAfterStartup() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName application = new ObjectName(
            "com.example.orders:type=Queue,name=Primary"
        );

        System.out.println(
            "Application MBean registered: "
                + server.isRegistered(application)
        );

        ObjectName tomcatPattern =
            new ObjectName("Catalina:*");

        int tomcatMBeans =
            server.queryNames(tomcatPattern, null).size();

        System.out.println(
            "Tomcat domain MBeans (if configured): "
                + tomcatMBeans
        );
    }
}
\`\`\`

Ví dụ này in số MBean trong domain \`Catalina\` như một quan sát, **không coi giá trị 0 là lỗi startup**. Nếu ứng dụng dùng Jetty, Undertow hoặc Reactor Netty, domain Tomcat không có ý nghĩa và cần thay bằng phương pháp phù hợp.

Trong production, tránh log toàn bộ danh sách MBean names vào mỗi lần khởi động nếu chứa thông tin nhạy cảm hoặc tạo log ồn.

## 16. Embedded server metrics và JMX

Một số dữ liệu hiệu năng web server có thể có ở dạng JMX MBean:

- Thread pool size, busy threads, số connection.
- Request count, bytes sent/received, thời gian xử lý.
- Session count và các thông số container.
- Connector status và lifecycle.

Tuy nhiên nguồn dữ liệu này khác nhau theo server và phiên bản. Spring Boot Actuator/Micrometer có thể cung cấp metrics theo cách chuẩn hóa hơn cho dashboard và hệ thống time-series.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Debug trực tiếp JVM | JConsole + platform MBeans |
| Quan sát một MBean cụ thể của server | JMX metadata và server-specific MBean |
| Metrics dài hạn qua Prometheus/Grafana | Micrometer/Actuator hoặc exporter tương thích |
| Theo dõi health/readiness | Actuator health/readiness probes hoặc hệ health phù hợp |
| Điều khiển MBean của ứng dụng | Spring JMX exporter với operation được bảo vệ |
| Kiểm tra hợp đồng JMX | Integration tests đọc \`MBeanInfo\` |

Không nên sử dụng JMX như nguồn metrics duy nhất nếu hệ thống cần retention, alerting, aggregation và multi-instance visibility.

## 17. Spring Boot Actuator và management port

Trong Spring Boot, các HTTP management endpoints có thể dùng cùng port với ứng dụng hoặc port riêng:

\`\`\`properties
server.port=8080
management.server.port=8081
\`\`\`

\`management.server.port=8081\` liên quan **HTTP management web server/context**, không phải remote JMX/RMI port. JMX registry và connector vẫn là một subsystem khác.

Một cấu hình đồng thời có thể là:

\`\`\`text
Main HTTP port:         8080
Actuator HTTP port:     8081
JMX remote port:        9010 (nếu tự cấu hình)
\`\`\`

Từ đó tránh lỗi “đổi \`management.server.port\` mà JConsole vẫn không kết nối”. JConsole dùng JMX connector, không dùng Actuator HTTP.

## 18. Bảo mật bề mặt quản trị

Embedded server và JMX có thể cùng chạy trong một JVM với quyền của service process. Những thao tác như tắt connector, thay đổi thread pool hoặc stop worker có thể gây ảnh hưởng lớn. Do đó cần:

1. **Tối thiểu hóa MBean/operation được công bố.** Không export mọi service method theo reflection một cách vô kiểm soát.
2. **Đặt quyền truy cập đúng.** Remote JMX cần authentication, TLS và giới hạn nguồn.
3. **Phân quyền thao tác.** Tách vai trò đọc metrics với vai trò gọi operation thay đổi trạng thái.
4. **Tránh lộ secrets.** Getter và ObjectName không nên chứa password, token, PII.
5. **Xác nhận môi trường trước invoke.** Có thể nhầm JVM staging với production nếu dùng cùng tên ObjectName.
6. **Thiết kế operation an toàn.** Có validation, concurrency control và idempotency khi phù hợp.
7. **Không retry mù.** Nếu invoke timeout, operation có thể đã chạy ở server.
8. **Có audit phù hợp.** Với thao tác quản trị có tác động, ghi lại actor, thời điểm và kết quả mà không lộ credential.

Dù Spring Boot chỉ chạy HTTP trên loopback hoặc trong container private, remote JMX exposed sai có thể trở thành đường truy cập mạnh vào JVM.

## 19. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JConsole thấy JVM nhưng không thấy MBean ứng dụng | \`spring.jmx.enabled\` chưa bật, bean không export, sai ObjectName. | Kiểm tra exporter, annotation và \`isRegistered\`. |
| Không có domain Tomcat | Registry/container MBeans chưa bật hoặc dùng server khác. | Xác định server implementation, phiên bản và cấu hình JMX container. |
| HTTP phục vụ bình thường, JMX remote connection refused | JMX remote agent chưa chạy, sai port. | Kiểm tra JVM flags và listener. |
| Port JMX mở nhưng client timeout | RMI advertised hostname/port sai hoặc firewall/NAT. | Kiểm tra \`java.rmi.server.hostname\`, \`jmxremote.rmi.port\`. |
| Cấu hình \`spring.jmx.enabled=true\` nhưng không thấy Actuator MBean | Chưa có Actuator hoặc JMX exposure/enablement không khớp. | Kiểm tra dependency và management properties theo phiên bản. |
| Trùng \`ObjectName\` | Nhiều exporter hoặc manual registration. | Kiểm tra registration policy và ownership. |
| Container đổi Pod nhưng JConsole giữ kết nối cũ | JVM đã restart/connector mới. | Reconnect đúng Pod/endpoint. |
| \`queryNames\` rỗng trong \`@PostConstruct\` | Container chưa xong lifecycle hoặc registry chưa bật. | Kiểm tra sau điểm ready và cấu hình thực tế. |
| Có MBean nhưng operation thiếu | Metadata assembler/management interface không khớp. | Đọc \`MBeanInfo\`. |
| Metrics không có nhãn/chuỗi thời gian | JMX chỉ là management API, không phải metrics storage. | Dùng collector/Micrometer/Actuator phù hợp. |

## 20. Integration test cho ứng dụng embedded server

Một integration test nên xác nhận cả web application và hợp đồng JMX, không phụ thuộc vào domain server-specific trừ khi dự án đã cấu hình có chủ đích.

Ví dụ ý tưởng với Spring Boot Test:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.jmx.enabled=true"
)
class EmbeddedJmxIntegrationTest {

    @Autowired
    Environment environment;

    @Test
    void expectedApplicationMBeanIsExported() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Primary"
        );

        assertTrue(
            server.isRegistered(name),
            "Expected application MBean is missing"
        );

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getAttributes())
                .anyMatch(a ->
                    "PendingMessages".equals(a.getName())
                    && a.isReadable()
                    && !a.isWritable()
                )
        );
    }
}
\`\`\`

Ví dụ yêu cầu \`QueueManagement\` được tạo trong test ApplicationContext và exporter đang đăng ký vào platform MBeanServer. Với các test chạy song song hoặc chia sẻ context, cần có ObjectName unique và cleanup để tránh xung đột.

Không nên đặt assert “\`Catalina:*\` luôn có MBean” trong một test dùng chung cho Tomcat, Jetty và Undertow. Chỉ kiểm tra server-specific MBeans khi đó là tính năng cấu hình rõ ràng của ứng dụng.

### 20.1. Kiểm tra dừng và restart

Một test lifecycle riêng có thể:

1. Khởi động context có embedded server.
2. Xác nhận HTTP port sẵn sàng và MBean ứng dụng được đăng ký.
3. Đóng context.
4. Xác nhận MBean do exporter sở hữu được unregister.
5. Khởi động lại context với \`ObjectName\` giống nhau trong môi trường cô lập, xác nhận không có lỗi \`InstanceAlreadyExistsException\`.

Đừng thực hiện test này trên ứng dụng production thực, vì đóng context sẽ dừng server đang phục vụ traffic.

## 21. Theo dõi nhiều instance

Nếu có nhiều instance Spring Boot cùng chạy:

\`\`\`text
instance A: order-service-1, PID 101
instance B: order-service-2, PID 102
instance C: order-service-3, PID 103
\`\`\`

mỗi JVM có MBeanServer riêng. Cùng ObjectName có thể tồn tại ở tất cả JVM mà không xung đột, vì registry tách biệt.

Để kết nối JConsole cần chọn **đúng instance/PID/JMX endpoint**. Metrics tập trung cần thêm nhãn instance/pod/host do collector cung cấp; \`ObjectName\` không tự định danh toàn bộ topology cluster.

Nếu một proxy JMX local trong instance A gọi MBean cùng tên, nó gọi registry của JVM A; không tự chuyển đến MBean instance B.

## 22. Phân biệt embedded và external servlet container

| Khía cạnh | Spring Boot embedded server | WAR chạy trong external container |
| --- | --- | --- |
| Quản lý lifecycle web server | Do Spring Boot/server factory điều phối trong JVM ứng dụng. | Container bên ngoài quản lý web server, WAR chỉ là một ứng dụng được triển khai. |
| Nguồn MBean container | Phụ thuộc embedded server và cơ chế bật JMX. | Có thể có registry/management cấu hình từ container độc lập. |
| JMX JVM process | JVM khởi chạy executable JAR. | JVM khởi chạy application server chứa một hoặc nhiều WAR. |
| Ranh giới quản trị | Thường gắn với một Spring Boot app/JVM. | Có thể chứa nhiều ứng dụng trong cùng JVM. |
| Port HTTP | Thường qua \`server.port\`. | Thường do external container cấu hình. |
| JMX connector | Cấu hình ở JVM/connector riêng. | Có thể do container/operator cung cấp. |

Khi chuyển một ứng dụng từ external Tomcat sang embedded Tomcat, **không bảo đảm giữ nguyên toàn bộ MBean container**. Cần kiểm tra lại domain/name, server registry và các công cụ monitoring đang phụ thuộc vào MBean cũ.

## 23. Bài tập thực hành

### Bài tập 1 — Phân biệt các lớp JMX

Tạo ứng dụng Spring Boot web có embedded Tomcat, một \`@ManagedResource\` đơn giản và bật \`spring.jmx.enabled=true\`. Chạy JConsole local, tìm \`java.lang\`, domain ứng dụng và domain Tomcat nếu có.

**Mục tiêu:** phân biệt JVM MBeans, Spring MBeans và container MBeans.

### Bài tập 2 — HTTP port không phải JMX

Đặt \`server.port=8090\`. Dùng browser gọi HTTP API; mở JConsole Remote Process thử \`localhost:8090\` trong môi trường lab và ghi nhận đây không phải JMX connector. Sau đó kết nối JConsole theo Local Process đúng JVM.

**Mục tiêu:** không nhầm HTTP listener với JMX endpoint.

### Bài tập 3 — Actuator JMX exposure

Thêm dependency Actuator, bật các endpoint JMX được phép, kiểm tra domain/operation mà runtime thực sự xuất. So sánh với danh sách web endpoints.

**Mục tiêu:** hiểu exposure theo kênh HTTP/JMX.

### Bài tập 4 — Embedded server khác nhau

Chạy cùng ứng dụng với Tomcat rồi Jetty trong hai môi trường test cô lập. So sánh những domain server-specific được đăng ký, nhưng không mặc định một domain luôn phải xuất hiện.

**Mục tiêu:** hiểu implementation-specific behavior.

### Bài tập 5 — Container network

Trong môi trường lab có thể kiểm soát, cấu hình remote JMX cố định port, sử dụng Docker port mapping hoặc Kubernetes port-forward; xác minh địa chỉ/cổng được RMI stub quảng bá tương thích đường kết nối.

**Mục tiêu:** hiểu vì sao mở port registry chưa chắc làm JConsole kết nối thành công.

### Bài tập 6 — Security checklist

Liệt kê các operation được công bố qua \`MBeanInfo\`, xác định operation có side effect và đề xuất quyền đọc/điều khiển, TLS, audit.

**Mục tiêu:** tránh tạo endpoint quản trị nguy hiểm trong production.

### Bài tập 7 — Restart lifecycle

Khởi động rồi dừng context trong integration test, xác minh MBean ứng dụng được unregister và đăng ký lại sạch khi restart.

**Mục tiêu:** ngăn xung đột ObjectName và leak registry.

## 24. Câu hỏi ôn tập

**1. Embedded server là gì?** Web server chạy trong cùng JVM và được ứng dụng Spring Boot điều phối, thường khi chạy executable JAR.

**2. Bật \`server.port\` có mở JMX port không?** Không. Nó cấu hình HTTP listener của web server.

**3. Bật \`spring.jmx.enabled=true\` có tự mở remote JMX/RMI không?** Không. Remote connector phải được cấu hình riêng.

**4. Có cần Actuator mới dùng Spring JMX không?** Không. Spring JMX và JVM platform MBeans có thể hoạt động độc lập.

**5. Vì sao MBean Tomcat có thể không xuất hiện khi chạy embedded?** Việc container tự đăng ký MBean có thể không được bật hoặc khác so với standalone; cần kiểm tra cấu hình/version.

**6. MBean JVM nào có thể kiểm tra dù không có application exporter?** Ví dụ \`java.lang:type=Memory\`, \`java.lang:type=Threading\` hoặc \`java.lang:type=Runtime\`.

**7. \`management.server.port\` là JMX port phải không?** Không. Nó liên quan HTTP management server của Boot khi được sử dụng.

**8. Nếu nhiều instance cùng có \`ObjectName\`, có xung đột không?** Không nếu nằm trong các MBeanServer/JVM khác nhau.

**9. Làm sao kiểm tra MBean thực sự được đăng ký?** Dùng đúng MBeanServer rồi gọi \`isRegistered\`, \`queryNames\` và \`getMBeanInfo\`.

**10. JMX có thay thế metrics collector và time-series database không?** Không. JMX là API quản trị/quan sát; monitoring dài hạn cần pipeline phù hợp.

## 25. Tổng kết

Ứng dụng Spring Boot chạy **embedded server** là một JVM chứa cả business application, server HTTP và các thành phần quản trị. JMX có thể công bố đồng thời MBeans của JVM, của Spring, của Actuator và của web server nhúng — nhưng mức độ công bố phụ thuộc cấu hình và implementation, không phải chỉ vì ứng dụng mở HTTP port.

Muốn khai thác JMX đúng, hãy phân biệt **\`spring.jmx.enabled\`**, **Actuator JMX exposure**, **container-specific MBeans** và **remote JMX connector**. Sau khi khởi động, kiểm tra \`MBeanInfo\` thực tế trên đúng JVM; khi triển khai container/Kubernetes, xét cả RMI advertised host/port, lifecycle và quyền truy cập. Với production, chỉ công bố bề mặt quản trị cần thiết và bảo vệ kết nối JMX tách biệt với HTTP.

## Tài liệu tham khảo

- Spring Boot Reference — Embedded Web Servers: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Apache Tomcat Documentation — Monitoring and Management: https://tomcat.apache.org/tomcat-10.1-doc/monitoring.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html