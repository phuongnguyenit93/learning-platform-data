# Bốn năng lực chính của Spring Framework JMX: đăng ký MBean, kiểm soát giao diện, truy cập từ xa và tạo proxy

## 1. Bức tranh tổng thể

Java Management Extensions (JMX) là chuẩn quản trị và giám sát ứng dụng Java. JMX cho phép công cụ quản trị đọc thuộc tính, gọi thao tác và nhận thông báo từ các đối tượng quản lý (MBean). Trong Spring Framework, các tiện ích JMX giúp kết nối bean ứng dụng với hạ tầng quản trị Java mà không buộc mã nghiệp vụ phải tự thao tác với mọi API JMX cấp thấp.

Có thể hình dung hệ thống qua bốn câu hỏi liên tiếp:

1. **Đăng ký MBean:** Làm thế nào biến đối tượng Spring thành đối tượng được MBeanServer quản lý?
2. **Kiểm soát giao diện:** Những thuộc tính và thao tác nào thực sự được công khai cho người quản trị?
3. **Truy cập từ xa:** Làm thế nào công cụ ở JVM hoặc máy khác kết nối tới MBeanServer?
4. **Tạo proxy:** Làm thế nào một thành phần Java/Spring gọi MBean như gọi một giao diện Java thông thường?

Bốn năng lực này tạo thành đường đi từ **đối tượng ứng dụng → MBeanServer → công cụ hoặc ứng dụng quản trị**. Chúng giải quyết những bài toán khác nhau; dùng đủ hay một phần tùy theo yêu cầu vận hành.

```text
Ứng dụng Spring
  └── Bean nghiệp vụ / quản trị
        │ (1) MBeanExporter
        ▼
      MBeanServer
        │ (2) Metadata/assembler quyết định thuộc tính, operation, notification
        ├── Kết nối JMX nội bộ: JConsole/JMX client trong cùng JVM
        ├── (3) JMXConnectorServer → JMX client từ xa
        └── (4) MBeanServerConnection → MBeanProxyFactoryBean
                                            └── Giao diện Java phía client
```

> **Phân biệt cốt lõi:** MBeanServer là nơi chứa và phục vụ MBean; MBeanExporter đưa bean vào đó; assembler/annotation xác định giao diện quản trị; connector phụ trách đường truyền; proxy thích nghi lời gọi Java sang thao tác JMX.

## 2. Năng lực 1 — Đăng ký MBean

### 2.1. Tại sao phải đăng ký?

Một Spring bean chỉ sống trong Spring `ApplicationContext` chưa tự động trở thành MBean. Để JMX client tìm thấy nó, bean cần được **đăng ký với MBeanServer dưới một ObjectName**. ObjectName gồm domain và các cặp khóa, ví dụ:

```text
com.example.monitoring:type=CacheMonitor,name=PrimaryCache
```

Tên này là định danh JMX, không phải bean name của Spring. ObjectName phải hợp lệ theo JMX và duy nhất trong MBeanServer đang sử dụng. Việc đăng ký trùng tên có thể phát sinh lỗi hoặc được xử lý theo chính sách đăng ký đã cấu hình.

### 2.2. MBeanExporter đóng vai trò gì?

`org.springframework.jmx.export.MBeanExporter` là cầu nối đăng ký bean vào MBeanServer. Khi Spring khởi tạo exporter, nó chọn các bean được chỉ định, xây dựng mô hình quản trị phù hợp và đăng ký chúng. Khi ngữ cảnh đóng, exporter thường hủy đăng ký những MBean do chính nó quản lý.

Ví dụ một đối tượng quản trị độc lập:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheMonitor {
    private final AtomicInteger entryCount = new AtomicInteger();

    public int getEntryCount() {
        return entryCount.get();
    }

    public void clear() {
        entryCount.set(0);
    }

    public void recordEntry() {
        entryCount.incrementAndGet();
    }
}
```

Có thể đăng ký bằng Java configuration:

```java
package com.example.monitoring;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class JmxConfiguration {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            CacheMonitor cacheMonitor,
            MetadataMBeanInfoAssembler jmxAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=CacheMonitor,name=PrimaryCache",
                cacheMonitor));
        exporter.setAssembler(jmxAssembler);
        return exporter;
    }
}
```

Ở cấu hình trên, exporter dùng tên rõ ràng thay vì phụ thuộc cơ chế tự sinh tên. Bộ assembler metadata sẽ quyết định phần giao diện JMX công khai. Ví dụ cần bổ sung annotation ở phần tiếp theo để lộ thuộc tính/thao tác theo ý muốn.

### 2.3. MBeanServer và chính sách đăng ký

Spring có thể tìm MBeanServer đang tồn tại hoặc dùng MBeanServer được cấu hình/khởi tạo phù hợp. Khi hệ thống đã có MBeanServer do application server hoặc nền tảng vận hành quản lý, nên cố tình chọn đúng server để tránh công cụ nhìn vào một server khác.

Một số vấn đề cần xác định trước khi triển khai:

- **Naming:** đặt ObjectName ổn định, phản ánh module/instance; tránh tên dễ xung đột giữa nhiều bean.
- **Lifecycle:** Spring context restart cần đăng ký/hủy đăng ký có kiểm soát.
- **Ownership:** đối tượng được ứng dụng xuất ra nên do ứng dụng quản lý; tránh xóa nhầm MBean được hệ thống khác đăng ký.
- **Policy khi trùng tên:** lựa chọn hành vi fail, bỏ qua hoặc thay thế theo nhu cầu; thay thế MBean do thành phần khác sở hữu có thể nguy hiểm.
- **Phạm vi quản trị:** chỉ xuất các bean thực sự cần giám sát hoặc điều khiển.

**Dấu hiệu thành công:** trong JConsole hoặc một JMX client, ObjectName xuất hiện ở cây MBeans của đúng MBeanServer.

## 3. Năng lực 2 — Kiểm soát giao diện quản trị

### 3.1. Vì sao phải giới hạn bề mặt JMX?

Không nên đồng nhất mọi phương thức public của bean với API vận hành. Ví dụ `recordEntry()` trong `CacheMonitor` dành cho luồng nghiệp vụ, còn `getEntryCount()` và `clear()` có thể hữu ích cho quản trị. Giao diện JMX cần là một **hợp đồng được thiết kế chủ động**, giống một API quản trị độc lập.

JMX cung cấp ba nhóm dữ liệu chính:

| Thành phần | Công dụng | Ví dụ |
| --- | --- | --- |
| **Attribute** | Đọc hoặc ghi trạng thái | `EntryCount` (read-only), `Enabled` (read/write) |
| **Operation** | Thực thi hành động | `clear()`, `refreshConfiguration()` |
| **Notification** | Báo sự kiện tới listener | Thay đổi trạng thái dịch vụ hoặc vượt ngưỡng |

**Không nên** công khai thông tin nhạy cảm, token, chuỗi kết nối, thao tác hủy dữ liệu hay mutation nguy hiểm nếu không có chính sách vận hành và quyền truy cập phù hợp.

### 3.2. Annotation-based metadata

Spring hỗ trợ `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` và các annotation tham số, thông báo. Ví dụ bổ sung metadata ngay trên bean:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=PrimaryCache",
    description = "Cache operations monitoring")
public class CacheMonitor {
    private final AtomicInteger entryCount = new AtomicInteger();

    @ManagedAttribute(description = "Number of recorded cache entries")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation(description = "Reset the entry counter")
    public void clear() {
        entryCount.set(0);
    }

    public void recordEntry() {
        entryCount.incrementAndGet();
    }
}
```

Khi `MetadataMBeanInfoAssembler` lấy dữ liệu từ `AnnotationJmxAttributeSource`, `EntryCount` và `clear` trở thành thành phần quản trị. `recordEntry()` không được lộ qua giao diện metadata này vì không có annotation liên quan. Tên thuộc tính JMX được diễn giải theo quy ước getter/setter của JavaBean.

**Hai con đường đặt ObjectName:** cấu hình tường minh trong `MBeanExporter.setBeans(...)` hoặc metadata `@ManagedResource(objectName=...)` kết hợp naming strategy thích hợp. Ví dụ ở đây đã chỉ định tường minh trong exporter; annotation cũng mô tả cùng tên để giữ thống nhất.

### 3.3. Các lựa chọn assembler khác

Spring JMX còn có các cơ chế như `MethodNameBasedMBeanInfoAssembler` để liệt kê phương thức bằng tên, `InterfaceBasedMBeanInfoAssembler` để giới hạn theo interface, và assembler dựa trên metadata. Sự khác biệt là nguồn quyết định giao diện xuất ra:

- **Annotation metadata:** mô tả gần nơi khai báo code, thích hợp với API vận hành rõ ràng.
- **Interface-based:** dùng contract Java, hữu ích khi cần tách quản trị khỏi interface nghiệp vụ.
- **Method-name based:** lựa chọn tên phương thức qua configuration, hữu ích với bean không thể chỉnh sửa source.

Chọn một cơ chế nhất quán với chính sách API và khả năng kiểm soát code. Thay đổi chữ ký method hoặc tên thuộc tính công khai là thay đổi hợp đồng quản trị; cần xem xét tác động tới dashboard/script vận hành.

### 3.4. Hiểu quyền đọc/ghi thuộc tính

Nếu chỉ khai báo getter `@ManagedAttribute`, thuộc tính thường chỉ đọc; nếu muốn ghi, cần setter phù hợp được khai báo cho JMX. Đừng tạo setter chỉ để tiện thao tác nếu việc thay đổi runtime có thể phá invariant ứng dụng. Với các hành động có hậu quả, operation tên rõ nghĩa và có xác thực/kiểm soát là lựa chọn dễ quản lý hơn.

## 4. Năng lực 3 — Truy cập JMX từ xa

### 4.1. MBeanServer không đồng nghĩa với kênh mạng

MBean đã đăng ký có thể được sử dụng trong JVM qua `MBeanServer` hoặc `MBeanServerConnection`. Để client ở JVM khác truy cập, cần hạ tầng kết nối, chẳng hạn **JMX Remote connector**. `JMXConnectorServer` mở điểm phục vụ; phía client tạo `JMXConnector` và lấy `MBeanServerConnection`.

```text
JVM ứng dụng                               JVM công cụ
MBean → MBeanServer                       JMX client
          │                                    │
          └── JMXConnectorServer  ⇄  JMXConnector
                       giao thức/kết nối
```

Spring hỗ trợ cấu hình connector server thông qua các thành phần trong `org.springframework.jmx.support` hoặc cơ chế JMX Remote chuẩn của JDK. Việc export MBean và việc bật kết nối mạng là **hai quyết định độc lập**.

### 4.2. Ví dụ client kết nối qua JMXServiceURL

Ví dụ Java client minh họa kết nối rồi đọc attribute. URL chỉ là ví dụ cho môi trường được cấu hình JMX/RMI tương ứng:

```java
package com.example.client;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxReader {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi");

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example.monitoring:type=CacheMonitor,name=PrimaryCache");

            Object count = connection.getAttribute(name, "EntryCount");
            System.out.println("Entries = " + count);
        }
    }
}
```

Đoạn code giả định server, registry, service URL và quyền truy cập đã được cấu hình. Nó không tự bật JMX Remote ở phía ứng dụng. Kết nối thực tế có thể yêu cầu cấu hình hostname, nhiều cổng RMI, firewall, TLS, credentials và các thuộc tính môi trường gửi vào `JMXConnectorFactory.connect(url, environment)`.

### 4.3. Bảo mật và vận hành

Một JMX operation có thể thay đổi trạng thái tiến trình thực. Do đó JMX Remote phải được đối xử như một cổng quản trị nhạy cảm.

- Chỉ bật remote connector khi thực sự cần; ưu tiên mạng quản trị riêng, tunnel được bảo vệ hoặc truy cập qua hệ thống giám sát đáng tin cậy.
- Bật xác thực, phân quyền, mã hóa kênh theo môi trường và giao thức; không đặt endpoint quản trị công khai trên Internet.
- Giới hạn operation có thể tạo tác động mạnh, kiểm soát tài khoản thao tác, ghi audit ở lớp phù hợp.
- Với RMI, kiểm tra cả cổng registry và cổng remote object; NAT/container có thể khiến client kết nối registry được nhưng không hoàn thành lời gọi.
- Lên kế hoạch timeout, độ sẵn sàng, credential rotation và kiểm thử kết nối từ đúng mạng của client.

**Dấu hiệu thành công:** client từ xa truy vấn đúng ObjectName và nhận được `EntryCount`; đồng thời trường hợp thiếu quyền bị chặn như thiết kế.

## 5. Năng lực 4 — Tạo proxy để gọi MBean như interface Java

### 5.1. Vấn đề của JMX client cấp thấp

Client dùng `MBeanServerConnection` thường phải xây ObjectName và gọi `getAttribute`, `setAttribute`, `invoke` với tên String, mảng tham số và chữ ký kiểu. Spring `MBeanProxyFactoryBean` cho phép khai báo một **interface phía client** và tạo proxy thực hiện lời gọi JMX.

Proxy là phía tiêu thụ của hợp đồng MBean. Nó không thay thế việc đăng ký MBean và không tự cung cấp transport. Client vẫn cần `MBeanServerConnection` đến đúng server (nội bộ hoặc từ xa).

### 5.2. Ví dụ hợp đồng và cấu hình proxy

Interface phía client:

```java
package com.example.client;

public interface CacheMonitorOperations {
    int getEntryCount();
    void clear();
}
```

Bean configuration (giả định `MBeanServerConnection` đã được cấu hình và có thể truy cập ObjectName):

```java
package com.example.client;

import javax.management.MBeanServerConnection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class JmxClientConfiguration {

    @Bean
    public MBeanProxyFactoryBean cacheMonitorProxy(
            MBeanServerConnection connection) {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(connection);
        proxy.setObjectName(
            "com.example.monitoring:type=CacheMonitor,name=PrimaryCache");
        proxy.setProxyInterface(CacheMonitorOperations.class);
        return proxy;
    }
}
```

Thành phần client gọi qua interface:

```java
package com.example.client;

public class CacheAdministration {
    private final CacheMonitorOperations cache;

    public CacheAdministration(CacheMonitorOperations cache) {
        this.cache = cache;
    }

    public int readCount() {
        return cache.getEntryCount();
    }

    public void resetCount() {
        cache.clear();
    }
}
```

Với Spring, tên bean `cacheMonitorProxy` có thể được inject theo kiểu interface mà FactoryBean tạo ra. Kết nối vẫn có thể phát sinh lỗi mạng hoặc lỗi JMX khi chạy; cú pháp interface không biến lời gọi từ xa thành lời gọi nội bộ về mặt độ tin cậy.

### 5.3. Chú ý khi thiết kế proxy

- Phương thức interface phải tương thích với thuộc tính/operation được xuất ở phía MBean, gồm tên và kiểu Java.
- Thuộc tính theo chuẩn getter/setter cần khớp metadata JMX của phía server.
- Proxy là client kỹ thuật; chính sách retry, timeout và xử lý ngoại lệ phải tính đến side effect. Không retry mù operation không idempotent.
- Một số kiểu dữ liệu phức tạp cần tuân theo khả năng biểu diễn của JMX, đặc biệt khi hai JVM khác phiên bản class.
- Đối với hệ thống phân tán quy mô lớn, cân nhắc khi nào JMX phù hợp với quản trị/giám sát và khi nào HTTP management endpoint hoặc metrics pipeline là lựa chọn tốt hơn.

## 6. Ghép bốn năng lực thành một kịch bản thực tế

Giả sử dịch vụ có bộ đệm và đội vận hành cần đọc số lượng entry, có quyền xóa trạng thái theo quy trình được phê duyệt.

| Bước | Thành phần | Kết quả |
| --- | --- | --- |
| 1. Định nghĩa bean | `CacheMonitor` | Có phương thức đọc trạng thái và thao tác quản trị |
| 2. Giới hạn giao diện | `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, assembler | Chỉ những thành phần được chọn hiển thị qua JMX |
| 3. Đăng ký | `MBeanExporter` + `MBeanServer` | ObjectName có thể được tìm và truy vấn |
| 4. Mở đường truy cập (nếu cần) | `JMXConnectorServer` và cấu hình bảo mật | Client từ JVM khác lấy được `MBeanServerConnection` |
| 5. Tiêu thụ | JConsole hoặc `MBeanProxyFactoryBean` | Người vận hành quan sát; ứng dụng client gọi qua interface |

Một ứng dụng chỉ cần JConsole tại máy chủ có thể dừng ở bước 3. Client Java chạy trong cùng JVM có thể dùng `MBeanServerConnection` nội bộ để tạo proxy và bỏ qua remote connector. Chỉ khi cần kết nối giữa JVM/máy khác mới cần bước 4.

## 7. Những nhầm lẫn thường gặp

**“Thêm `@ManagedResource` là đã mở JMX Remote.”** Sai: annotation mô tả managed resource; đăng ký và transport là các bước khác.

**“Mọi public method của bean đều nên là JMX operation.”** Sai: JMX là bề mặt quản trị, cần chọn đúng method/attribute và quyền sử dụng.

**“ObjectName chính là Spring bean name.”** Sai: chúng thuộc hai hệ thống định danh khác nhau. Exporter có thể ánh xạ bean sang ObjectName cụ thể.

**“Proxy là MBean.”** Sai: proxy là adapter ở phía client, chuyển lời gọi interface thành tương tác với MBean đã đăng ký.

**“Gọi qua proxy sẽ không có lỗi mạng.”** Sai: nếu connection ở xa, lỗi timeout, mất kết nối và authorization vẫn có thể xảy ra.

**“Đọc được MBean nghĩa là nên cho phép mọi operation.”** Sai: quyền đọc, quyền gọi thao tác và nguy cơ side effect phải được đánh giá độc lập.

## 8. Tự kiểm tra hiểu biết

1. Nếu một bean đã được tạo trong `ApplicationContext` nhưng không thấy trong JConsole, cần xem lại thành phần nào đầu tiên? **MBeanExporter, ObjectName và MBeanServer được sử dụng.**
2. Nếu chỉ muốn công khai `getEntryCount()`, còn `recordEntry()` phải ẩn, cần thiết kế ở lớp nào? **Assembler/metadata hoặc interface quản trị.**
3. Nếu client ở máy khác không thể gọi MBean mặc dù local JConsole thấy nó, nên kiểm tra gì? **Connector server, service URL, mạng/cổng, RMI hostname, TLS/authentication và quyền truy cập.**
4. Nếu muốn code client sử dụng `cache.getEntryCount()` thay vì `connection.getAttribute(...)`, dùng gì? **MBeanProxyFactoryBean với proxy interface tương thích.**
5. Có bắt buộc phải bật remote connector để tạo proxy không? **Không; proxy có thể dùng kết nối MBeanServer nội bộ.**

## 9. Ghi nhớ

- **Exporter** trả lời *đối tượng nào được đăng ký và dưới tên gì*.
- **Metadata/assembler** trả lời *client được nhìn thấy và được thao tác những gì*.
- **Connector** trả lời *client ở đâu và kết nối tới server bằng cách nào*.
- **Proxy** trả lời *code phía client muốn gọi MBean qua interface Java ra sao*.

Đây là bốn năng lực bổ sung cho nhau của Spring Framework JMX. Hãy thiết kế giao diện quản trị tối thiểu, đặt tên MBean ổn định, bảo vệ kết nối từ xa và coi các lời gọi proxy qua mạng là hoạt động có thể thất bại.