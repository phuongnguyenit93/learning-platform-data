# Chọn server JMX đã có hoặc tạo server riêng khi Exporting trong Spring

## 1. Vấn đề cần giải quyết

Khi dùng Spring Framework JMX để export một hoặc nhiều bean thành MBean, câu hỏi quan trọng không chỉ là “export bean nào?” mà còn là **“đăng ký MBean vào MBeanServer nào?”**. Một tiến trình Java có thể có platform MBeanServer, một MBeanServer do application server cung cấp, và những MBeanServer do ứng dụng tạo riêng. Nếu exporter đăng ký vào một server trong khi JMX client lại nhìn vào server khác, người vận hành sẽ thấy MBean “biến mất” dù quá trình đăng ký thành công.

Trong Java Management Extensions (JMX), `javax.management.MBeanServer` là registry và điểm truy cập quản trị của MBean. Mỗi MBean được định danh bằng `ObjectName` **trong phạm vi MBeanServer đó**. Hai MBeanServer có thể chứa ObjectName giống nhau mà vẫn là hai đăng ký độc lập.

Spring Framework hỗ trợ lựa chọn và tích hợp server thông qua `MBeanExporter`, `MBeanServerFactoryBean`, cùng những tiện ích tìm server hiện có. Bài học tập trung vào cách ra quyết định, cấu hình đúng server và tránh tạo ra các đảo quản trị tách rời.

Mục tiêu:

- Phân biệt **tái sử dụng MBeanServer có sẵn** với **tạo MBeanServer riêng**.
- Hiểu platform MBeanServer, server được đăng ký trong `MBeanServerFactory`, và server được tìm bởi Spring.
- Cấu hình `MBeanExporter.setServer(...)` để xác định rõ nơi đăng ký MBean.
- Biết khi nào nên dùng `MBeanServerFactoryBean` và điểm khác nhau giữa `createMBeanServer` với `newMBeanServer`.
- Kiểm tra ObjectName trên đúng server và hiểu hậu quả của nhiều server với JConsole, JMX Remote và monitoring.

## 2. Mô hình tư duy: exporter và server là hai vai trò khác nhau

```text
                  Spring ApplicationContext
                            |
                    Bean ứng dụng
                            |
                      MBeanExporter
                            |
                     setServer(...)
                            |
              +-------------+-------------+
              |                           |
      MBeanServer có sẵn           MBeanServer riêng
      (platform/container)        (do Spring tạo)
              |                           |
       ObjectName / MBean           ObjectName / MBean
              |                           |
      JMX client chọn đúng connection và server
```

`MBeanExporter` là thành phần Spring dùng để chuyển bean thành MBean và đăng ký. `MBeanServer` là nơi lưu registry và phục vụ truy cập. `MBeanExporter` **không đồng nghĩa** với `MBeanServer` và không tự buộc mọi JMX client trên máy nhìn thấy MBean ở một namespace chung.

Có thể hình dung:

- `MBeanExporter` là người đưa một đối tượng vào hệ thống quản trị.
- `MBeanServer` là sổ đăng ký và điểm nhận lệnh quản trị.
- `ObjectName` là địa chỉ của đối tượng **trong sổ đăng ký đó**.
- `MBeanServerConnection` là đường mà client dùng để làm việc với server.
- Remote connector là một khả năng kết nối mạng riêng, không tự sinh ra chỉ vì có exporter hoặc server.

Do đó lựa chọn server phải dựa trên **client nào cần truy cập MBean** và **server nào client đó thực sự kết nối**.

## 3. Ba nguồn MBeanServer thường gặp

### 3.1. Platform MBeanServer

JDK cung cấp một platform MBeanServer qua `java.lang.management.ManagementFactory`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platformServer =
    ManagementFactory.getPlatformMBeanServer();
```

Đây là nơi JDK đăng ký nhiều platform MXBean phục vụ quản trị JVM, chẳng hạn bộ nhớ, thread và garbage collection. Nó thường là lựa chọn thuận tiện cho ứng dụng độc lập muốn để MBean ứng dụng xuất hiện cùng những đối tượng quản trị JVM đã quen thuộc.

Lợi ích:

- Dễ tích hợp với công cụ quen thuộc như JConsole hoặc VisualVM khi chúng kết nối tới platform management agent.
- Không cần tạo thêm một MBeanServer cho cùng tiến trình.
- Có thể đặt ObjectName thuộc domain riêng để tránh va chạm với MBean nền tảng.
- Có vòng đời gắn với JVM và có thể được nhiều thành phần trong tiến trình tái sử dụng.

Tuy nhiên, platform MBeanServer và JMX Remote là hai khái niệm khác nhau. Việc có platform server **không tự động bảo đảm** mạng bên ngoài truy cập được; cần connector và chính sách bảo mật phù hợp.

### 3.2. MBeanServer do container hoặc thành phần khác tạo

Trong môi trường application server, có thể có MBeanServer do container quản lý. Container có thể định nghĩa convention về tên, classloader, vòng đời hoặc việc expose JMX connector.

Trong môi trường này nên cân nhắc **tái sử dụng server thực sự được quản trị** thay vì tạo thêm server và kỳ vọng công cụ của container sẽ tự khám phá nó. Khi xác định server, có thể dùng lookup theo agent ID hoặc inject MBeanServer đã chọn sẵn.

Cần tránh suy luận rằng một tiến trình chỉ có một MBeanServer: JMX API cho phép nhiều server, và danh sách các server được tạo/đăng ký qua factory có thể khác với platform server mong đợi.

### 3.3. MBeanServer do ứng dụng tạo riêng

Một số trường hợp cần tách miền quản trị để kiểm soát rõ namespace, vòng đời, chính sách kết nối hoặc thành phần được phép đăng ký. JMX cung cấp:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer privateServer =
    MBeanServerFactory.newMBeanServer("com.example.private");
```

MBeanServer này là một registry quản trị riêng. Nếu client chỉ kết nối platform server, nó **không nhìn thấy** MBean được đăng ký trong `privateServer` trừ khi có một đường truy cập phù hợp tới server riêng.

Tạo riêng cần chủ động quản lý đăng ký, kết nối, vòng đời và quan sát. Nó hữu ích khi có nhu cầu tách biệt thực sự; việc tạo thêm chỉ để tránh cấu hình server thường khiến vận hành phức tạp hơn.

## 4. Tìm MBeanServer hiện có

### 4.1. MBeanServerFactory.findMBeanServer

API JMX có:

```java
import java.util.List;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

List<MBeanServer> servers =
    MBeanServerFactory.findMBeanServer(null);
```

Lời gọi với `null` trả về các MBeanServer đã được đăng ký trong danh sách của `MBeanServerFactory`, theo khả năng nhìn thấy của môi trường thực thi. Không nên suy luận rằng kết quả sẽ chỉ có một hoặc bao gồm mọi MBeanServer được tạo bằng bất cứ cơ chế nào.

Để tìm theo agent ID cụ thể:

```java
List<MBeanServer> matches =
    MBeanServerFactory.findMBeanServer("my-agent-id");
```

Chỉ dùng ID được cấu hình/biết chắc, không đoán agent ID từ tên domain hoặc ObjectName. Server được tạo bằng `newMBeanServer` có thể không được đăng ký trong danh sách factory, vì vậy cơ chế tìm này không thay thế dependency injection cho server riêng.

### 4.2. Lợi ích của dependency injection

Một khi đã chọn được server đúng, cách ít mơ hồ nhất trong Spring là khai báo nó thành bean và inject vào exporter. Điều đó giúp:

- Chỉ ra một nơi chịu trách nhiệm chọn server.
- Cho các exporter trong cùng ứng dụng dùng nhất quán cùng server.
- Đọc cấu hình dễ dàng: từ exporter lần theo `MBeanServer` được inject.
- Dễ thay đổi lựa chọn giữa platform và server riêng qua configuration.
- Tránh mỗi thành phần tự gọi API tìm server rồi chọn nhầm instance.

Ví dụ:

```java
@Bean
public MBeanServer jmxServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

Khi ứng dụng có nhiều bean kiểu `MBeanServer`, cần dùng tên hoặc `@Qualifier` để tránh injection mơ hồ.

## 5. Export bean vào platform MBeanServer

Ví dụ Spring Java Configuration có thể chạy trong một ứng dụng Spring Framework:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class PlatformJmxConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter cacheExporter(
            CacheMonitor monitor,
            MBeanServer jmxServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=CacheMonitor,name=Main",
            monitor
        ));
        return exporter;
    }
}
```

Với đối tượng MBean đi kèm:

```java
package com.example.monitoring;

public interface CacheMonitorMBean {
    int getEntryCount();
    void reset();
}
```

```java
package com.example.monitoring;

public class CacheMonitor implements CacheMonitorMBean {

    private int entryCount;

    @Override
    public synchronized int getEntryCount() {
        return entryCount;
    }

    @Override
    public synchronized void reset() {
        entryCount = 0;
    }

    public synchronized void recordEntry() {
        entryCount++;
    }
}
```

`CacheMonitor` là Standard MBean vì tên interface phù hợp. `MBeanExporter` có thể xác định MBean và đăng ký bean dưới ObjectName được cấu hình.

Trong ví dụ, `MBeanServer` được inject rõ ràng và sử dụng `setServer(...)`. Vì vậy exporter không phải tự tìm server vào lúc khởi tạo, và mọi client muốn truy cập MBean này cần kết nối đúng platform server.

Lưu ý: `reset()` là thao tác quản trị có side effect. Chỉ expose operation cần thiết, và nếu bật remote access phải áp dụng xác thực/ủy quyền bảo vệ môi trường.

## 6. Tạo MBeanServer riêng bằng Spring MBeanServerFactoryBean

Spring cung cấp `org.springframework.jmx.support.MBeanServerFactoryBean` để làm việc với MBeanServer trong bean lifecycle. Có thể cấu hình tạo server mới và đưa nó vào `MBeanExporter`.

```java
package com.example.monitoring;

import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class PrivateJmxConfig {

    @Bean
    public MBeanServerFactoryBean privateJmxServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.private");
        factory.setLocateExistingServerIfPossible(false);
        factory.setRegisterWithFactory(false);
        return factory;
    }

    @Bean
    public MBeanExporter privateExporter(
            CacheMonitor monitor,
            MBeanServer privateJmxServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(privateJmxServer);
        exporter.setBeans(Map.of(
            "com.example.private:type=CacheMonitor,name=Main",
            monitor
        ));
        return exporter;
    }
}
```

`MBeanServerFactoryBean` là `FactoryBean<MBeanServer>`, do đó thông thường dependency injection theo kiểu `MBeanServer` nhận đối tượng server do factory tạo ra. Tên bean factory và tên sản phẩm có quan hệ riêng theo cơ chế `FactoryBean` của Spring. Nếu cần truy cập chính factory, Spring dùng cú pháp bean name bắt đầu bằng `&`.

Cấu hình trên chủ động yêu cầu tạo mới, không định tìm server sẵn, đồng thời không đăng ký server vào danh sách `MBeanServerFactory`. Vì vậy server mới được tách riêng; client phải được cung cấp chính server hoặc một connector trỏ vào nó. Default domain chỉ là miền mặc định của server; nó **không bắt buộc** mọi ObjectName đăng ký phải dùng domain đó.

Trong ứng dụng thực tế, hãy đảm bảo cùng một `CacheMonitor` không bị xuất đồng thời bởi các configuration khác với ObjectName xung đột, hoặc tự thiết kế việc export vào nhiều server nếu thật sự cần.

### 6.1. createMBeanServer và newMBeanServer

JMX API phân biệt:

```java
MBeanServer a =
    MBeanServerFactory.createMBeanServer("com.example.a");

MBeanServer b =
    MBeanServerFactory.newMBeanServer("com.example.b");
```

Cả hai tạo một server mới, nhưng `createMBeanServer` đăng ký server vào danh sách của factory để có thể tìm bằng `findMBeanServer`, còn `newMBeanServer` không đăng ký như vậy. Đây là khác biệt **về khả năng tra cứu của factory**, không phải về việc server tự mở cổng mạng.

Trong `MBeanServerFactoryBean`, thuộc tính `registerWithFactory` điều khiển lựa chọn này khi tạo server:

- `true`: đăng ký server vào danh sách của MBeanServerFactory.
- `false`: tạo server mà không đưa vào danh sách đó.

Một server “được register với factory” vẫn chưa đồng nghĩa có remote connector. Muốn truy cập từ JVM khác, cần thêm cơ chế truy cập thích hợp.

## 7. Tái sử dụng server có sẵn với MBeanServerFactoryBean

`MBeanServerFactoryBean` có thể được cấu hình để cố tìm một MBeanServer đã tồn tại:

```java
@Bean
public MBeanServerFactoryBean existingJmxServer() {
    MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
    factory.setLocateExistingServerIfPossible(true);
    return factory;
}
```

Ý tưởng của lựa chọn này là cho phép factory tìm server đang có trước, rồi xử lý trường hợp không tìm được theo cấu hình của factory. Tuy nhiên, nếu hệ thống có nhiều server, **tự động tìm** có thể trở nên mơ hồ. Cần hiểu rõ server nào được chọn, đặc biệt khi ứng dụng chạy trong container hoặc có các framework hỗ trợ JMX khác.

Khi biết chính xác platform server cần sử dụng, gọi trực tiếp `ManagementFactory.getPlatformMBeanServer()` và inject như phần 5 thường dễ hiểu hơn.

Trong hệ thống có yêu cầu chọn server bằng agent ID, có thể dùng các tiện ích Spring tìm server như `MBeanServerFactoryBean.setAgentId(...)` và những thành phần lookup tương ứng. Agent ID là thông tin phục vụ nhận diện server trong môi trường JMX; nó không phải ObjectName của một MBean.

**Quy tắc thiết kế:** xác định rõ tiêu chí chọn server, xác minh server được trả về, rồi inject cùng server đó vào exporter và các thành phần quản trị nội bộ. Đừng để hai exporter quan trọng tự động chọn hai server khác nhau mà không có chủ đích.

## 8. Khi nào tái sử dụng, khi nào tạo riêng?

| Tiêu chí | Dùng MBeanServer đã có | Tạo MBeanServer riêng |
| --- | --- | --- |
| Công cụ giám sát hiện tại | Dễ dùng nếu công cụ đã kết nối server đó | Phải tạo đường kết nối tương ứng |
| Tích hợp platform MXBeans | Có thể truy cập cùng server | Không tự xuất hiện trong server riêng |
| Tách biệt registry | Chia sẻ namespace và chính sách của server | Có registry và namespace độc lập |
| Vòng đời | Thường do JDK/container quản lý | Ứng dụng/factory chịu trách nhiệm |
| Cấu hình | Ít thành phần mới | Cần quản lý server, connector và listener |
| Trùng ObjectName | Xung đột nếu cùng server | Có thể trùng ObjectName giữa hai server |
| Phù hợp | Ứng dụng thông thường, tích hợp vận hành sẵn có | Nhu cầu phân tách quản trị rõ ràng |

Các ví dụ cần suy nghĩ:

**Dịch vụ Spring Boot độc lập:** Thường chọn platform server nếu các công cụ vận hành của JVM đã dựa vào platform management agent. Cần xác nhận cấu hình quản trị thực tế thay vì suy ra mọi JConsole đều hiển thị mọi server.

**Ứng dụng trong application server:** Nên tìm hiểu server do container cung cấp. Việc dùng server của container có thể giúp thống nhất với console quản trị và chính sách sẵn có.

**Thành phần nhúng chạy nhiều instance trong một JVM:** Nếu cần tách vùng MBean theo tenant hoặc thành phần, có thể dùng ObjectName có key rõ ràng trong một server; chỉ tạo server riêng khi sự tách biệt ở cấp registry thực sự cần thiết.

**Thử nghiệm tích hợp:** Server riêng hữu ích để giảm phụ thuộc trạng thái global của platform MBeanServer và tránh va chạm ObjectName giữa các test chạy cùng JVM. Nhưng cần dọn đăng ký và tài nguyên khi test kết thúc.

**Yêu cầu isolation chuyên biệt:** Server riêng tạo một namespace/registry khác; nó không tự cung cấp ranh giới bảo mật tuyệt đối, sandbox hoặc quyền truy cập biệt lập nếu connector và lớp authorization chưa được thiết kế phù hợp.

## 9. Kiểm tra exporter đã dùng đúng server

### 9.1. isRegistered trên server cụ thể

Sau khi Spring context đã khởi tạo exporter, kiểm tra:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=CacheMonitor,name=Main"
);

boolean found = jmxServer.isRegistered(name);
System.out.println("Found on selected server: " + found);
```

Nếu `found` là `false`, cần kiểm tra:

1. Exporter có được Spring khởi tạo không?
2. Exporter có trỏ tới đúng MBeanServer không?
3. ObjectName dùng kiểm tra có khớp tên đã đăng ký không?
4. MBean có đăng ký thành công hay bị xung đột ObjectName không?
5. Thời điểm kiểm tra có diễn ra sau khởi tạo exporter hay không?
6. Có bean/controller/configuration khác đang quản lý vòng đời MBean hay không?

Việc một `ObjectName` có mặt trong một server khác không có nghĩa nó có mặt trong server mà client đang kết nối.

### 9.2. Đọc attribute để xác nhận

```java
Object value = jmxServer.getAttribute(
    name, "EntryCount"
);

System.out.println("EntryCount = " + value);
```

Với Standard MBean trong phần 5, `EntryCount` được công bố nhờ `getEntryCount()`. Đọc thành công cho thấy MBean và attribute thực sự có thể truy cập trên **server đã chọn**.

Đừng kiểm tra bằng cách chỉ gọi `ManagementFactory.getPlatformMBeanServer()` nếu exporter đã được cấu hình vào private server: kết quả âm tính khi đó có thể hoàn toàn đúng.

### 9.3. Khi thấy MBean trong JConsole

JConsole thường kết nối qua management agent của JVM hoặc JMX Remote endpoint. Nó không mặc định duyệt tất cả các MBeanServer bất kỳ được tạo bên trong tiến trình.

Nếu exporter dùng server riêng, cần cung cấp connector hoặc công cụ kết nối đúng server đó. Nếu JConsole kết nối platform server, nó có thể thấy platform MXBeans và các MBean được xuất vào đó, nhưng không nhất thiết thấy private server.

Do đó khi debug câu hỏi “MBean đã export thành công nhưng không thấy trong JConsole”, hãy xác minh **đường kết nối client → MBeanServer** trước khi sửa ObjectName hoặc cấu hình annotation.

## 10. Kết nối mạng và bảo mật là quyết định độc lập

Một số lập trình viên nhầm rằng `MBeanServerFactoryBean` tạo server riêng đồng nghĩa đã tạo endpoint JMX Remote. Thực tế, việc tạo MBeanServer chỉ tạo registry JMX; client từ xa cần connector trỏ vào server.

```text
JVM ứng dụng                         JVM quản trị
  MBeanExporter
       |
  MBeanServer
       |
  JMXConnectorServer  <---------->  JMXConnector
                                     |
                              MBeanServerConnection
```

Trong môi trường remote, phải giải quyết đúng URL, hostname, cổng, firewall, RMI registry/remote port nếu dùng RMI, cùng authentication và TLS. Không đưa endpoint quản trị nhạy cảm trực tiếp lên Internet.

Việc đăng ký MBean vào platform server không đồng nghĩa mọi tác vụ được bảo vệ. Attribute/operation có thể chứa hoặc thay đổi trạng thái quan trọng. Cần công khai giao diện quản trị tối thiểu, kiểm soát quyền và tránh xuất secrets.

Tạo server riêng có thể hỗ trợ phân chia diện quản trị theo kết nối, nhưng **không thể thay thế** xác thực và phân quyền. Nếu connector cho phép truy cập rộng, toàn bộ MBean trong server đó vẫn cần được xem là bề mặt quản trị nhạy cảm.

## 11. Vòng đời và xử lý xung đột

### 11.1. Ai chịu trách nhiệm hủy đăng ký?

Nếu `MBeanExporter` đăng ký MBean khi Spring context khởi tạo, hãy để exporter quản lý việc hủy đăng ký tương ứng khi context đóng. Đừng tự ý hủy đăng ký ObjectName do container, JVM hoặc thư viện khác sở hữu.

Ngược lại, nếu dùng `registerMBean(...)` thủ công, code tạo đăng ký phải có kế hoạch unregister và dọn tài nguyên. Trong test, dùng ObjectName riêng hoặc server riêng để giảm ảnh hưởng qua lại.

### 11.2. Xử lý trùng ObjectName

JMX ObjectName phải duy nhất trong một MBeanServer. Nếu hai exporter đăng ký cùng một ObjectName vào cùng server, hành vi phụ thuộc chính sách đăng ký và có thể lỗi. Spring có các chính sách registration để xử lý trùng tên, nhưng việc bỏ qua hoặc thay thế MBean khác cần có chủ đích.

Khi cần nhiều instance:

```text
com.example.monitoring:type=CacheMonitor,name=Main,instance=1
com.example.monitoring:type=CacheMonitor,name=Main,instance=2
```

Hãy đặt key property rõ ràng thay vì ngẫu nhiên thay đổi tên hoặc tạo thêm server chỉ để tránh collision.

### 11.3. Default domain không thay thế định danh

Tạo server với default domain `com.example.private` không bắt buộc mọi MBean đăng ký vào domain đó. ObjectName vẫn có thể có domain tường minh, ví dụ:

```text
com.example.other:type=CacheMonitor,name=Main
```

Khi dựng ObjectName, cân nhắc domain của ứng dụng/module rõ ràng. Đừng phụ thuộc vào default domain nếu cần tên ổn định qua nhiều cấu hình.

## 12. Lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Export thành công, JConsole không thấy | Client kết nối server khác | Xác định exporter server và connector của client |
| `InstanceNotFoundException` | Sai server hoặc ObjectName, MBean đã unregister | `isRegistered(name)` trên chính server đó |
| `InstanceAlreadyExistsException` | ObjectName đã đăng ký trên server | Kiểm tra namespace và registration policy |
| MBean thấy trong test khác nhưng không phải test này | Dùng chung platform server và rò rỉ đăng ký | Cô lập test, dọn lifecycle |
| Tạo private server nhưng remote client không vào được | Chưa cấu hình connector hoặc sai endpoint | Kiểm tra connector, URL, port và mạng |
| Không tìm thấy server bằng `findMBeanServer` | Server không đăng ký trong factory, sai agent ID | Kiểm tra nguồn tạo server và cấu hình lookup |
| Nhiều MBeanServer gây kết quả không nhất quán | Các exporter/client tự chọn server khác nhau | Inject một server tường minh hoặc ghi rõ mapping |
| Server riêng dường như rỗng | MBeanExporter chưa khởi tạo hoặc đang dùng server khác | Kiểm tra lifecycle và `setServer` |

Thêm logging có ngữ cảnh cho lúc đăng ký MBean, ObjectName và server được chọn sẽ giúp chẩn đoán, nhưng không nên ghi dữ liệu nhạy cảm của thuộc tính quản trị.

## 13. Bài thực hành: so sánh platform và private server

Bài thực hành giúp thấy rõ một ObjectName có thể tồn tại ở một server nhưng không tồn tại ở server khác.

```java
import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("com.example.isolated");

ObjectName platformName = new ObjectName(
    "com.example.demo:type=CacheMonitor,name=Platform"
);

ObjectName privateName = new ObjectName(
    "com.example.demo:type=CacheMonitor,name=Private"
);

platform.registerMBean(new CacheMonitor(), platformName);
isolated.registerMBean(new CacheMonitor(), privateName);

System.out.println(platform.isRegistered(platformName)); // true
System.out.println(platform.isRegistered(privateName));  // false
System.out.println(isolated.isRegistered(platformName));  // false
System.out.println(isolated.isRegistered(privateName));   // true

platform.unregisterMBean(platformName);
isolated.unregisterMBean(privateName);
```

Đây là minh họa JMX thuần để quan sát hai registry riêng biệt. Khi viết test thực tế, dùng `try/finally` để bảo đảm unregister kể cả khi assertion thất bại. Mỗi ObjectName là địa chỉ có ý nghĩa **trong server tương ứng**.

Bạn có thể thử thêm:

1. Đăng ký cùng `ObjectName` vào cả hai server với hai instance MBean khác nhau, rồi xác nhận cả hai có thể tồn tại.
2. Thử đăng ký trùng cùng `ObjectName` hai lần vào **một** server, quan sát lỗi hoặc xử lý trùng tên.
3. Kiểm tra `MBeanServerFactory.findMBeanServer(null)` để so sánh server được factory đăng ký với server tạo bằng `newMBeanServer`.
4. Đổi cấu hình `MBeanExporter` từ platform sang private server và kiểm tra lại bằng `isRegistered`.
5. Kết nối JConsole tới management agent, giải thích vì sao không đương nhiên nhìn thấy private server.

## 14. Câu hỏi tự kiểm tra

**1. MBeanExporter và MBeanServer khác nhau thế nào?** Exporter đưa bean vào hệ thống quản trị; MBeanServer chứa registry và phục vụ lời gọi quản trị.

**2. Khi nào tái sử dụng platform server?** Khi cần tích hợp với công cụ vận hành JVM và không có lý do tách registry riêng.

**3. Tạo server riêng có tự bật JMX Remote không?** Không; connector và bảo mật là bước riêng.

**4. `createMBeanServer` khác `newMBeanServer` ở đâu?** Cả hai tạo server mới; `createMBeanServer` đăng ký server vào danh sách factory, còn `newMBeanServer` không.

**5. Hai MBeanServer có thể có cùng ObjectName không?** Có, vì ObjectName chỉ duy nhất trong mỗi server.

**6. Vì sao `setServer(...)` quan trọng?** Nó xác định rõ nơi exporter đăng ký MBean và giúp tránh chọn nhầm server.

**7. Nếu JConsole không thấy MBean dù exporter không báo lỗi, cần kiểm tra gì trước?** Connector của JConsole kết nối server nào, và exporter đã đăng ký vào server nào.

**8. Default domain của server có ép mọi ObjectName sử dụng domain đó không?** Không, ObjectName có thể khai báo domain tường minh.

**9. Khi có nhiều bean `MBeanServer` trong Spring context, nên làm gì?** Dùng qualifier hoặc tên để inject server mong muốn một cách tường minh.

**10. Server riêng có tự tạo ranh giới bảo mật đầy đủ không?** Không; vẫn phải thiết kế connector, xác thực, phân quyền và network isolation.

## 15. Ghi nhớ

- Trước khi export MBean, hãy xác định **client sẽ kết nối MBeanServer nào**.
- **Tái sử dụng server hiện có** phù hợp khi muốn thống nhất với platform/container và công cụ giám sát.
- **Tạo server riêng** phù hợp khi thật sự cần registry độc lập và sẵn sàng quản lý connector/lifecycle.
- **`MBeanExporter.setServer(...)`** giúp gắn exporter với đúng server.
- **`MBeanServerFactoryBean`** tích hợp việc tạo/tìm server vào Spring; `registerWithFactory` điều khiển việc đăng ký server mới với danh sách factory.
- **ObjectName chỉ duy nhất trong một MBeanServer**, vì vậy cùng tên ở hai server là hai đích quản trị khác nhau.
- **MBeanServer không tự đồng nghĩa với JMX Remote**; kết nối, xác thực và bảo mật cần được cấu hình riêng.
- Xác nhận bằng **`isRegistered` và đọc attribute trên đúng server**, rồi mới kết luận exporter hoặc client có vấn đề.

Lựa chọn MBeanServer đúng ngay từ đầu giúp Spring JMX có đường quản trị rõ ràng, tránh xung đột hoặc “mất” MBean khi công cụ kết nối nhầm registry, và giảm sự phức tạp của vận hành lâu dài.