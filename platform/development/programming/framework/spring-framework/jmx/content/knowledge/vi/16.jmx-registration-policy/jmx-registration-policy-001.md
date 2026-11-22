# Lỗi trùng ObjectName khi đăng ký mặc định trong Spring Framework JMX

## 1. Mục tiêu bài học

Khi Spring Framework export bean vào JMX, mỗi MBean được đăng ký trong một `MBeanServer` dưới một `ObjectName`. Trong cùng server, **không thể đồng thời đăng ký hai MBean khác nhau dưới cùng một ObjectName**. Nếu ObjectName đã tồn tại, thao tác đăng ký theo chính sách mặc định thường thất bại. Đây là chủ đề cốt lõi của **Registration policy** trong Spring Framework JMX.

Sau bài học, bạn sẽ có thể:

- Giải thích vì sao ObjectName trùng gây lỗi ngay lúc Spring khởi tạo exporter.
- Nhận diện `InstanceAlreadyExistsException` của JMX và các ngoại lệ do Spring bao bọc.
- Hiểu chính sách đăng ký mặc định của `MBeanExporter` và các lựa chọn `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING`.
- Chẩn đoán việc trùng tên do nhiều bean, nhiều exporter, Spring context, cấu hình tự động hoặc lifecycle.
- Thiết kế tên JMX ổn định, phân biệt instance và chọn registration policy phù hợp mà không ghi đè MBean của thành phần khác.
- Phân biệt lỗi trùng `ObjectName` với việc kết nối sai `MBeanServer` hoặc sai tên attribute/operation.

## 2. ObjectName phải duy nhất trong một MBeanServer

JMX dùng lớp `javax.management.ObjectName` để xác định một MBean. Cấu trúc:

```text
domain:key1=value1,key2=value2
```

Ví dụ:

```text
com.example.monitoring:type=JobWorker,name=Primary
```

Trong một `MBeanServer`, tên này ánh xạ tới **một** đăng ký MBean. Nếu đã đăng ký:

```java
server.registerMBean(firstWorker, objectName);
```

thì đăng ký tiếp:

```java
server.registerMBean(secondWorker, objectName);
```

sẽ không tạo hai mục có cùng tên. JMX phản hồi lỗi vì `ObjectName` đó đã được sử dụng.

Đặc tính duy nhất này có phạm vi **một MBeanServer**. Hai server riêng biệt có thể cùng tồn tại MBean với ObjectName giống nhau:

```text
Server A: com.example.monitoring:type=JobWorker,name=Primary
Server B: com.example.monitoring:type=JobWorker,name=Primary
```

Vì thế, khi chẩn đoán trùng tên, luôn xác định **exporter đang đăng ký vào server nào**. Một object name trùng giữa các JVM khác nhau không tự động dẫn tới lỗi trong mỗi JVM.

### 2.1. Thứ tự key property không giúp tránh trùng

Hai chuỗi sau biểu diễn cùng ObjectName:

```text
com.example.monitoring:type=JobWorker,name=Primary
com.example.monitoring:name=Primary,type=JobWorker
```

JMX chuẩn hóa ý nghĩa của key property. Bạn không thể tránh xung đột bằng cách đảo thứ tự key:

```java
ObjectName first = new ObjectName(
    "com.example.monitoring:type=JobWorker,name=Primary");

ObjectName second = new ObjectName(
    "com.example.monitoring:name=Primary,type=JobWorker");

System.out.println(first.equals(second)); // true
```

Nếu cần thêm instance, phải thay đổi giá trị hoặc thêm key property có ý nghĩa, chẳng hạn `instance=2`.

## 3. Điều gì xảy ra khi đăng ký theo mặc định?

API Java JMX định nghĩa ngoại lệ `javax.management.InstanceAlreadyExistsException` khi ObjectName được yêu cầu đã có MBean đăng ký. Ví dụ:

```java
import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=JobWorker,name=Primary");

server.registerMBean(firstWorker, name);

try {
    server.registerMBean(secondWorker, name);
} catch (InstanceAlreadyExistsException ex) {
    System.err.println(
        "MBean already registered: " + name.getCanonicalName());
}
```

Đoạn minh họa giả định `firstWorker` và `secondWorker` là những đối tượng JMX MBean hợp lệ, ví dụ các instance của lớp `JobWorker` implements `JobWorkerMBean`.

Với `MBeanExporter` của Spring, chính sách đăng ký mặc định là **`REGISTRATION_FAIL_ON_EXISTING`**: nếu một ObjectName đã tồn tại, exporter không tự động bỏ qua hay thay thế. Quá trình export có thể thất bại lúc ApplicationContext khởi tạo, và ngoại lệ JMX có thể xuất hiện dưới ngoại lệ Spring liên quan đến đăng ký MBean.

Cách mặc định này ưu tiên phát hiện cấu hình sai: nếu hai thành phần cùng nhận một tên quản trị, ứng dụng biết ngay rằng namespace có vấn đề thay vì âm thầm ghi đè MBean cũ.

### 3.1. Ví dụ lỗi lúc startup

```text
Spring context initializes
    |
    +-- Exporter A registers ObjectName X
    |      SUCCESS
    |
    +-- Exporter B registers ObjectName X
           FAILURE: InstanceAlreadyExistsException
```

Đó không nhất thiết là lỗi của bean nghiệp vụ. Một bean có thể hoạt động bình thường, nhưng cấu hình export của hai thành phần cùng ánh xạ nó hoặc hai bean khác nhau vào một tên JMX.

Ngoại lệ có thể được bao bọc trong `MBeanExportException`, `BeanCreationException` hoặc một chuỗi cause khác tùy cách exporter được khởi tạo. Khi đọc stack trace, nên đi tới root cause và ObjectName liên quan.

## 4. Các nguồn trùng ObjectName phổ biến

### 4.1. Hai bean có cùng tên tường minh

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=JobWorker,name=Primary")
public class FirstWorker {
    // ...
}
```

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=JobWorker,name=Primary")
public class SecondWorker {
    // ...
}
```

Nếu cả hai được exporter phát hiện và cố đăng ký trên cùng server, sẽ xung đột vì ObjectName bằng nhau.

### 4.2. Hai MBeanExporter cùng export một bean

Một ứng dụng có thể vừa bật cơ chế annotation-driven, vừa cấu hình thủ công một `MBeanExporter` cho cùng resource:

```java
@Configuration
@EnableMBeanExport
class AnnotationJmxConfig {
}
```

và đồng thời:

```java
@Bean
MBeanExporter customExporter(...) {
    // Cũng export cùng ObjectName.
}
```

Nếu cả hai đăng ký cùng tên, exporter khởi tạo sau thường gặp lỗi. Cách xử lý ưu tiên là **chọn một đường export rõ ràng**, không phải thay đổi registration policy để giấu trùng cấu hình.

### 4.3. Nhiều Spring ApplicationContext

Trong hệ thống có parent/child contexts hoặc khởi động nhiều context cùng JVM, mỗi context có thể tạo `MBeanExporter` riêng và cùng trỏ platform MBeanServer. Nếu cùng export một ObjectName, conflict xuất hiện dù bean thuộc những ApplicationContext khác nhau.

```text
Context A --------+
                  +--> Platform MBeanServer
Context B --------+      ObjectName X
```

Có thể giải quyết bằng cách phân quyền sở hữu MBean theo context, đặt namespace khác nhau hoặc tránh export cùng resource từ cả hai context.

### 4.4. Trùng do naming strategy

Một naming strategy có thể dùng tên lớp hoặc bean key để dựng ObjectName. Nếu hai instance có tên sinh giống nhau, chẳng hạn cả hai đều thành:

```text
com.example.app:type=Worker,name=Default
```

thì chúng xung đột. Đừng chỉ kiểm tra `@ManagedResource`; phải kiểm tra **ObjectName cuối cùng** mà naming strategy trả về.

### 4.5. MBean được đăng ký thủ công trước đó

Có thể một thư viện, application server hoặc đoạn code khác đã gọi:

```java
server.registerMBean(existing, name);
```

Sau đó `MBeanExporter` cố đăng ký một bean khác với cùng `name`. Trong tình huống này, không được vội chọn REPLACE vì MBean cũ có thể do framework/container sở hữu.

### 4.6. Test không dọn đăng ký

Test tích hợp dùng platform MBeanServer (thường có vòng đời dài trong JVM test) có thể để lại MBean sau khi kết thúc. Test kế tiếp đăng ký cùng tên và nhận lỗi. Việc dùng một ObjectName riêng cho mỗi test, server riêng hoặc đóng Spring context đúng lifecycle giúp giảm xung đột.

## 5. Các registration policy trong Spring

Spring Framework cung cấp các giá trị chính sách trên `MBeanRegistrationSupport`, thường được `MBeanExporter` sử dụng:

| Chính sách | Ý nghĩa khi ObjectName đã tồn tại |
| --- | --- |
| `REGISTRATION_FAIL_ON_EXISTING` | Báo lỗi đăng ký; mặc định và an toàn khi cần phát hiện xung đột |
| `REGISTRATION_IGNORE_EXISTING` | Bỏ qua đăng ký mới, giữ MBean hiện có |
| `REGISTRATION_REPLACE_EXISTING` | Gỡ đăng ký cũ rồi đăng ký MBean mới theo chính sách Spring |

Các chính sách này điều khiển **xử lý xung đột đăng ký**, không phải chính sách bảo mật. Chúng không quyết định một client có quyền gọi operation hay ghi attribute hay không.

### 5.1. FAIL_ON_EXISTING: phát hiện lỗi sớm

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanRegistrationSupport;

MBeanExporter exporter = new MBeanExporter();

exporter.setRegistrationPolicy(
    MBeanRegistrationSupport.REGISTRATION_FAIL_ON_EXISTING);
```

Khi tên đã tồn tại, Spring báo lỗi. Đây là lựa chọn phù hợp cho phần lớn ứng dụng vì tránh việc vô tình chiếm quyền sở hữu một MBean khác.

### 5.2. IGNORE_EXISTING: giữ đăng ký cũ

```java
exporter.setRegistrationPolicy(
    MBeanRegistrationSupport.REGISTRATION_IGNORE_EXISTING);
```

Nếu ObjectName đã có, exporter bỏ qua đăng ký bean mới. Điều này có thể hữu ích trong môi trường biết chắc rằng một MBean do thành phần khác đăng ký là đích mong muốn. Nhưng nó tạo ra rủi ro hiểu sai: application context có bean mới, trong khi JMX client vẫn nhìn thấy **MBean cũ**.

```text
Exporter A registers X -> firstWorker
Exporter B tries X -> secondWorker
Policy IGNORE_EXISTING
Result: JMX X still points to firstWorker
```

Không nên dùng IGNORE để che lỗi duplicate exporter. Sau khi chọn policy này, cần biết chính xác ObjectName nào bị bỏ qua và ai sở hữu MBean hiện tại.

### 5.3. REPLACE_EXISTING: thay MBean cũ

```java
exporter.setRegistrationPolicy(
    MBeanRegistrationSupport.REGISTRATION_REPLACE_EXISTING);
```

Khi ObjectName đã tồn tại, Spring có thể unregister MBean trước đó và đăng ký MBean mới. Điều này làm thay đổi đối tượng được client JMX truy cập. Những listener, proxy, thông tin quản trị hoặc trạng thái đang phụ thuộc MBean cũ có thể bị ảnh hưởng.

REPLACE có thể được cân nhắc nếu **ứng dụng kiểm soát toàn bộ vòng đời và quyền sở hữu đăng ký**, chẳng hạn một luồng thay thế MBean được thiết kế có chủ đích. Không nên bật rộng cho mọi exporter trong môi trường chia sẻ MBeanServer.

### 5.4. Chọn chính sách như thế nào?

Một quy tắc thực dụng:

1. Mặc định **FAIL** để nhìn thấy cấu hình sai.
2. Nếu xung đột do nhiều bean/exporter, sửa thiết kế tên hoặc giảm số exporter.
3. Chỉ dùng **IGNORE** khi có yêu cầu rõ ràng để bảo toàn MBean hiện có.
4. Chỉ dùng **REPLACE** khi có quy trình sở hữu và thay thế MBean được xác định.
5. Kiểm tra kết quả thực tế trên MBeanServer sau khi exporter khởi tạo.

Không tự chuyển FAIL sang IGNORE/REPLACE chỉ để ứng dụng startup được. Làm vậy có thể khiến giám sát trỏ sai instance hoặc thay thế resource không thuộc ứng dụng.

## 6. Ví dụ tối giản có hai instance trùng tên

Định nghĩa Standard MBean:

```java
package com.example.monitoring;

public interface WorkerStatusMBean {
    String getName();
}
```

```java
package com.example.monitoring;

public class WorkerStatus implements WorkerStatusMBean {
    private final String name;

    public WorkerStatus(String name) {
        this.name = name;
    }

    @Override
    public String getName() {
        return name;
    }
}
```

Đăng ký hai instance cùng ObjectName:

```java
import java.lang.management.ManagementFactory;

import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=WorkerStatus,name=Primary");

WorkerStatus first = new WorkerStatus("first");
WorkerStatus second = new WorkerStatus("second");

try {
    server.registerMBean(first, name);

    try {
        server.registerMBean(second, name);
        throw new AssertionError("Expected duplicate registration failure");
    } catch (InstanceAlreadyExistsException expected) {
        System.out.println("Duplicate ObjectName rejected: " + name);
    }
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
```

Ví dụ này thể hiện cơ chế JMX độc lập với Spring. Dùng ObjectName riêng cho test để tránh unregister một MBean đang tồn tại do thành phần khác sở hữu. Trong bài thực hành, nên chạy JVM mới hoặc dùng `MBeanServerFactory.newMBeanServer(...)` để cô lập registry test.

## 7. Cấu hình MBeanExporter và registration policy

Ví dụ một cấu hình có hai bean giống loại nhưng ObjectName khác nhau:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanRegistrationSupport;

@Configuration
public class WorkerJmxConfig {

    @Bean
    public WorkerStatus primaryWorker() {
        return new WorkerStatus("primary");
    }

    @Bean
    public WorkerStatus backupWorker() {
        return new WorkerStatus("backup");
    }

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter workerExporter(
            WorkerStatus primaryWorker,
            WorkerStatus backupWorker,
            MBeanServer jmxServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setRegistrationPolicy(
            MBeanRegistrationSupport.REGISTRATION_FAIL_ON_EXISTING);

        exporter.setBeans(Map.of(
            "com.example.monitoring:type=WorkerStatus,name=Primary",
            primaryWorker,
            "com.example.monitoring:type=WorkerStatus,name=Backup",
            backupWorker
        ));
        return exporter;
    }
}
```

Cả hai MBean dùng domain `com.example.monitoring` và type `WorkerStatus`, nhưng key `name` khác nhau. Cách này giữ naming nhất quán, cho phép client truy vấn theo pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.monitoring:type=WorkerStatus,*");

for (ObjectName found : jmxServer.queryNames(pattern, null)) {
    System.out.println(found.getCanonicalName());
}
```

Nếu hai entry được ánh xạ tới cùng chuỗi ObjectName, xung đột xuất hiện. Khi dùng `Map`, hai key chuỗi giống nhau còn có thể bị gộp/ghi đè ở mức Java collection trước cả khi exporter đăng ký; vì vậy cần phân biệt lỗi cấu hình map với lỗi do `MBeanServer.registerMBean` từ hai exporter hoặc hai lần đăng ký riêng.

## 8. Lỗi trong Spring ApplicationContext nhìn như thế nào?

Khi `MBeanExporter` khởi tạo, nó có thể đăng ký bean theo cấu hình. Nếu xung đột, khởi tạo context có thể thất bại.

Một dạng stack trace minh họa:

```text
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'workerExporter'
  ...
Caused by: org.springframework.jmx.export.MBeanExportException:
  Unable to register MBean ...
Caused by: javax.management.InstanceAlreadyExistsException:
  com.example.monitoring:type=WorkerStatus,name=Primary
```

Không nên phụ thuộc vào một dạng thông điệp hoặc chuỗi class chính xác cho mọi phiên bản Spring. Điều quan trọng là:

- Tìm **root cause** của quá trình đăng ký.
- Xác định ObjectName trong thông báo lỗi.
- Xác định `MBeanServer` mà exporter dùng.
- Xác định bean/exporter nào đã đăng ký trước.
- Chỉ sau đó quyết định sửa naming hay thay policy.

Nếu thấy `InstanceNotFoundException`, đó là nhóm vấn đề khác: client gọi tới tên không tồn tại hoặc MBean đã bị unregister. `InstanceAlreadyExistsException` là lỗi đăng ký với tên **đã tồn tại**, không phải lỗi đọc attribute.

## 9. Chẩn đoán xung đột theo từng bước

### Bước 1: Ghi lại ObjectName chính xác

Ví dụ:

```text
com.example.monitoring:type=WorkerStatus,name=Primary
```

Chú ý domain, mọi key property, quoting và thứ tự canonical. Không nhầm tên Spring bean `primaryWorker` với ObjectName.

### Bước 2: Xác định MBeanServer

Spring exporter có thể sử dụng platform server hoặc server riêng, được cấu hình qua `setServer(...)` hoặc cơ chế lookup. Nếu client kiểm tra platform server trong khi exporter đăng ký vào server riêng, thông tin thu được có thể gây hiểu nhầm.

### Bước 3: Kiểm tra đăng ký đã tồn tại

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=WorkerStatus,name=Primary");

boolean exists = server.isRegistered(name);
System.out.println("Already registered? " + exists);
```

Nếu true, có một MBean ở tên đó **tại thời điểm kiểm tra**. Tuy nhiên, `isRegistered` chỉ là snapshot. MBean khác có thể đăng ký hoặc unregister ngay sau khi kiểm tra; không được dùng pre-check này làm cơ chế đảm bảo atomic thay cho phản hồi từ `registerMBean`.

### Bước 4: Khám phá metadata của MBean hiện có

```java
if (server.isRegistered(name)) {
    var info = server.getMBeanInfo(name);

    System.out.println("Class: " + info.getClassName());
    System.out.println("Description: " + info.getDescription());
}
```

Metadata giúp nhận diện loại MBean, nhưng có thể không đủ để kết luận chắc chắn **thành phần nào sở hữu** đăng ký. Có thể kết hợp logging, cấu hình exporter và thông tin lifecycle.

### Bước 5: Kiểm tra cấu hình export

Tìm những nơi cùng khai báo ObjectName:

- `@ManagedResource(objectName = "...")`.
- `MBeanExporter.setBeans(...)`.
- `MetadataNamingStrategy` hoặc custom `ObjectNamingStrategy`.
- `@EnableMBeanExport` hoặc JMX auto-configuration.
- Lệnh `registerMBean(...)` thủ công.
- Spring parent/child contexts và test context.
- Thư viện/container cũng đăng ký MBean.

Nếu MBean đã tồn tại hợp lệ, xác định liệu có nên dùng lại resource hiện có thay vì tạo một đăng ký khác.

### Bước 6: Sửa gốc vấn đề

Nếu trùng do thiếu key instance:

```text
com.example.monitoring:type=WorkerStatus,name=Primary
com.example.monitoring:type=WorkerStatus,name=Backup
```

Nếu trùng do exporter kép: giữ một exporter hoặc chia phạm vi bean rõ ràng. Nếu trùng do test: dùng server riêng hoặc đảm bảo cleanup. Nếu trùng do container sở hữu: không đè MBean đó khi chưa có thỏa thuận về quyền sở hữu.

## 10. Tính đúng đắn của ObjectName và naming strategy

Một số lỗi cấu hình không gây `InstanceAlreadyExistsException` trực tiếp nhưng có thể dẫn đến xung đột sau đó.

### 10.1. Dùng class name mà thiếu instance

Một custom naming strategy có thể đặt:

```text
com.example.monitoring:type=WorkerStatus
```

cho mọi instance của lớp `WorkerStatus`. Điều đó phù hợp nếu chỉ có một instance, nhưng không đủ nếu có nhiều worker. Thêm key `name` hoặc `instance` theo định danh ổn định.

### 10.2. Dùng display label làm identity

Nhãn “Primary Worker” dành cho UI có thể thay đổi theo ngôn ngữ. ObjectName nên dựa trên định danh ổn định như `name=Primary`; không nên tự động đổi domain hoặc key khi có người sửa label.

### 10.3. Định dạng value phức tạp

Nếu một key property value chứa dấu phẩy hoặc ký tự đặc biệt, dùng `ObjectName.quote(...)` khi cần thiết. Đừng tự ghép chuỗi không kiểm soát:

```java
String instance = "Primary, East";

ObjectName safeName = new ObjectName(
    "com.example.monitoring:type=WorkerStatus,name="
        + ObjectName.quote(instance));
```

Tên hợp lệ về cú pháp vẫn phải duy nhất theo ngữ nghĩa. Việc quote không giải quyết được hai instance cùng dùng một ID.

## 11. Lifecycle: khởi tạo, thay thế và dọn dẹp

Một MBean có vòng đời đăng ký:

```text
Spring context starts
      |
      v
MBeanExporter registers ObjectName
      |
      v
MBean available to JMX clients
      |
      v
Spring context closes
      |
      v
Exporter unregisters its managed registrations
```

Khi nhiều context cùng tồn tại, cần tránh một context sở hữu/ghi đè đăng ký mà context khác đang sử dụng. `MBeanExporter` có cơ chế quản lý đăng ký trong lifecycle của nó, nhưng không nên dựa vào hành vi cleanup để xử lý an toàn mọi tình huống chia sẻ quyền sở hữu.

Ví dụ rủi ro của `REPLACE_EXISTING`:

1. Context A đăng ký `X -> A`.
2. Context B dùng REPLACE, thay thành `X -> B`.
3. Context A đóng, có thể phát sinh tương tác lifecycle không mong đợi nếu ứng dụng không kiểm soát ownership chặt chẽ.
4. Client JMX đang giữ reference hoặc listener của MBean A phải thích nghi với việc A bị unregister.

Một chiến lược tốt thường là: **mỗi ObjectName có một thành phần chịu trách nhiệm đăng ký/hủy đăng ký**, và việc thay thế có quy trình rõ ràng.

## 12. Spring Boot và môi trường có tự động cấu hình JMX

Trong ứng dụng Spring Boot, khả năng export JMX có thể phụ thuộc cấu hình của Boot, management endpoints, dependency và phiên bản. Một ứng dụng có thể vô tình bật thêm hạ tầng exporter trong lúc cũng cấu hình `@EnableMBeanExport` hoặc `MBeanExporter` bằng tay.

Không nên suy luận rằng mọi lỗi trùng ObjectName đều do Boot. Hãy kiểm tra danh sách exporter, ObjectName thực tế và nguồn tạo bean trong cấu hình ứng dụng.

Một số lưu ý:

- Spring Framework JMX và Spring Boot Actuator JMX endpoints là các lớp tích hợp có thể liên quan nhưng không đồng nhất.
- Nếu cùng server có MBean của Spring, thư viện và application server, namespace cần được quản lý rõ.
- Đừng đổi domain tùy tiện để “né” lỗi nếu monitoring scripts vẫn trông đợi ObjectName cũ.
- Đừng mở remote JMX chỉ để debug registration conflict; có thể kiểm tra trực tiếp qua local MBeanServer và log của exporter.

## 13. Xử lý lỗi trong ứng dụng và trong test

### 13.1. Ứng dụng production

Nếu đăng ký quản trị thất bại, cần biết yêu cầu vận hành: ứng dụng có nên startup thất bại không, hay có thể tiếp tục mà không có MBean? Chính sách đăng ký mặc định giúp lộ xung đột, nhưng quyết định bỏ qua lỗi phải dựa trên yêu cầu observability và quản trị của hệ thống.

Tránh nuốt lỗi và ghi log “JMX optional” khi các hệ thống tự động dựa vào MBean để thực hiện điều khiển hoặc theo dõi quan trọng.

### 13.2. Test tích hợp

Nên dùng `MBeanServerFactory.newMBeanServer(...)` để tạo server không đăng ký trong danh sách factory, rồi inject vào exporter nếu muốn test namespace cô lập:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("com.example.test");
```

Nếu test tự đăng ký MBean, dùng `try/finally` để unregister chính MBean do test tạo. Không nên quét và unregister mọi MBean trong platform server, vì có thể làm hỏng các thành phần khác cùng JVM.

### 13.3. Phép thử cho registration policy

Bạn có thể viết bài test gồm:

1. Tạo isolated MBeanServer.
2. Đăng ký MBean A dưới ObjectName X.
3. Khởi tạo exporter B có cùng ObjectName X.
4. Với FAIL, mong đợi lỗi.
5. Với IGNORE, xác minh MBean X vẫn là A.
6. Với REPLACE, xác minh MBean X là B.
7. Dọn đúng đăng ký do test quản lý.

Để phân biệt A và B, cho mỗi MBean công bố attribute `InstanceLabel` với giá trị khác nhau. Sau khi export, gọi `getAttribute(X, "InstanceLabel")` thay vì chỉ kiểm tra `isRegistered(X)`; vì cả ba chính sách có thể để lại trạng thái tồn tại ở một số trường hợp, nhưng đối tượng đích khác nhau.

## 14. Bảo mật và ownership của MBean

Registration policy không phải cơ chế authorization. Nếu một exporter có quyền REPLACE trên MBeanServer, việc thay một ObjectName có thể ảnh hưởng đến người vận hành, notification listener, automation và runtime state.

Bởi vậy:

- Không cho mã ứng dụng không đáng tin có quyền ghi/đăng ký MBean tùy ý.
- Giới hạn remote JMX và phân quyền theo môi trường.
- Đặt domain và key property riêng cho ứng dụng, tránh namespace JDK/container.
- Không bật REPLACE rộng rãi để giải quyết mọi xung đột.
- Ghi nhận ai cấu hình exporter và ai sở hữu ObjectName.
- Kiểm tra audit/log cho lần đăng ký, skip hoặc replace mà không ghi secret.

Đặc biệt, **`java.lang` và các domain của platform MXBeans** thuộc các thành phần quản trị nền tảng; không nên dùng chúng làm namespace tùy ý cho MBean ứng dụng.

## 15. Bài tập thực hành

Tạo một bài tập theo hai bước: trước tiên tái hiện lỗi mặc định, sau đó sửa đúng cách.

### Phần A — tái hiện lỗi

1. Tạo `WorkerStatus` implements `WorkerStatusMBean`.
2. Tạo isolated MBeanServer.
3. Đăng ký worker A dưới ObjectName `com.example.demo:type=WorkerStatus,name=Main`.
4. Cố đăng ký worker B dưới cùng ObjectName.
5. Ghi nhận `InstanceAlreadyExistsException` và xác nhận MBean A vẫn đọc được.

### Phần B — sửa bằng naming

1. Giữ nguyên worker A dưới `name=Main`.
2. Đăng ký worker B dưới `name=Secondary`.
3. Dùng `queryNames("com.example.demo:type=WorkerStatus,*")` để liệt kê.
4. Đọc attribute `Name` của hai MBean.
5. Giải thích vì sao hai tên mới khác nhau là một giải pháp tốt hơn việc bật REPLACE.

### Phần C — thử policy Spring

1. Tạo `MBeanExporter` riêng với `setServer(isolated)`.
2. Cấu hình `setBeans(...)` trỏ tới ObjectName đã tồn tại.
3. Thử `REGISTRATION_FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING` ở các lần test độc lập.
4. Sau mỗi thử nghiệm, đọc lại `Name` để xác nhận instance được giữ.
5. Đóng context và dọn resource theo ownership.

Bản ghi kết quả nên phân biệt “có MBean dưới ObjectName” với “MBean nào đang được gắn dưới ObjectName”.

## 16. Câu hỏi tự kiểm tra

**1. Khi trùng ObjectName trong cùng MBeanServer, JMX báo lỗi gì?** `InstanceAlreadyExistsException`.

**2. Chính sách mặc định của Spring MBeanExporter là gì?** `REGISTRATION_FAIL_ON_EXISTING`.

**3. IGNORE_EXISTING có thay thế MBean cũ không?** Không, nó giữ đăng ký cũ và bỏ qua đăng ký mới khi có xung đột.

**4. REPLACE_EXISTING có nguy cơ gì?** Thay resource mà client hoặc thành phần khác đang dùng, gây thay đổi ownership/lifecycle và gián đoạn quản trị.

**5. Hai MBeanServer có thể có cùng ObjectName không?** Có, ObjectName chỉ duy nhất trong từng server.

**6. Đảo thứ tự key property có tránh trùng không?** Không, hai ObjectName với cùng domain và các key/value tương đương vẫn bằng nhau.

**7. Nếu `isRegistered(name)` trả true, có chắc MBean đó thuộc exporter của bạn không?** Không. Cần xác định nguồn đăng ký và quyền sở hữu.

**8. Vì sao không đổi policy ngay khi gặp xung đột?** Vì có thể che lỗi duplicate exporter hoặc thay thế MBean của thành phần khác.

**9. Cách đơn giản để phân biệt hai worker cùng type?** Thêm key property `name` hoặc `instance` ổn định và khác nhau.

**10. Có nên gọi unregister cho mọi ObjectName trùng để startup được không?** Không. Chỉ hủy đăng ký khi bạn sở hữu resource hoặc có quy trình thay thế được cho phép.

## 17. Ghi nhớ

- **Một ObjectName chỉ ánh xạ tới một MBean trong mỗi MBeanServer.**
- **`InstanceAlreadyExistsException`** là dấu hiệu đăng ký trùng tên.
- **Spring MBeanExporter mặc định fail khi tên đã tồn tại**, giúp phát hiện cấu hình sai sớm.
- **IGNORE** giữ MBean cũ; **REPLACE** thay MBean cũ, cả hai cần quyết định có chủ đích.
- Phải kiểm tra **MBeanServer, ObjectName, exporter và lifecycle**, không chỉ nhìn stack trace.
- Trùng do nhiều bean, exporter kép hoặc test cleanup thường nên sửa từ cấu hình gốc.
- Naming strategy cần có đủ key phân biệt instance và namespace ổn định.
- Registration policy không cấp quyền bảo mật và không thay thế việc quản lý ownership.

Hiểu rõ lỗi trùng ObjectName giúp bạn giữ một registry JMX nhất quán, tránh âm thầm xuất nhầm MBean và lựa chọn registration policy an toàn cho từng môi trường Spring Framework.