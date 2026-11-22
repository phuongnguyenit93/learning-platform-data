# Đăng ký assembler trong MBeanExporter

## Mục tiêu học tập

Trong Spring Framework JMX, `MBeanExporter` đưa các đối tượng quản lý vào `MBeanServer`, còn **MBeanInfoAssembler** quyết định giao diện quản lý (management interface) của những đối tượng không tự cung cấp một hợp đồng JMX chuẩn. Sau bài học, bạn sẽ:

- Hiểu vai trò riêng biệt của `MBeanExporter`, `MBeanInfoAssembler`, `MBeanServer` và `ObjectName`.
- Đăng ký một assembler với exporter qua `setAssembler(...)`.
- Dùng `MethodNameBasedMBeanInfoAssembler` để chọn rõ các method được công bố.
- Biết khi nào dùng `InterfaceBasedMBeanInfoAssembler` hoặc `MetadataMBeanInfoAssembler`.
- Kiểm tra attributes, operations và trạng thái đăng ký bằng `MBeanInfo`, không chỉ dựa vào việc ứng dụng khởi động thành công.
- Nhận biết phạm vi của autodetection và các nguy cơ công bố nhầm method quản trị.

## 1. Vì sao MBeanExporter cần assembler?

Một Spring bean bất kỳ có thể có nhiều method công khai nhưng chỉ một phần nhỏ trong đó nên được công bố qua JMX. Ví dụ, `CacheService` có `getEntryCount()`, `resetStatistics()`, `deleteAllCustomerData()` và nhiều method nghiệp vụ. Công cụ quản trị chỉ nên được phép quan sát số entry và reset bộ đếm, không được vô tình thấy các API nghiệp vụ nhạy cảm.

JMX có các loại MBean như Standard MBean với interface theo tên `ClassNameMBean`, MXBean và Dynamic MBean. Nếu một bean đã đáp ứng hợp đồng JMX chuẩn, `MBeanServer` có thể introspect hợp đồng đó. Đối với một POJO không implement interface JMX chuẩn, Spring có thể **adapt** đối tượng thành ModelMBean, và lúc này assembler cung cấp metadata quản lý.

Tách trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| `MBeanExporter` | Chọn bean cần export, ánh xạ tên, đăng ký và quản lý lifecycle |
| `MBeanInfoAssembler` | Xây dựng `ModelMBeanInfo` mô tả attributes, operations, constructors và notifications |
| `MBeanServer` | Registry JMX, thực thi get/set/invoke theo hợp đồng MBean đã đăng ký |
| `ObjectName` | Định danh duy nhất của MBean trong một server |
| JConsole/client | Đọc metadata, xem attributes và gọi operations được công bố |

Assembler không tự quét classpath hoặc đăng ký MBean vào server. Nó cần được exporter sử dụng cho các đối tượng thích hợp. Ngược lại, gắn assembler vào exporter cũng không tự khiến mọi bean trong `ApplicationContext` được export: vẫn phải có danh sách bean, chế độ autodetection hoặc cơ chế chọn bean cụ thể.

## 2. Hai quyết định: chọn bean và chọn management interface

Hãy phân biệt rõ hai câu hỏi:

1. **Bean nào được export?** Do cấu hình `MBeanExporter` quyết định, ví dụ `setBeans(Map.of(...))` hoặc autodetection.
2. **Method nào của bean đó được hiển thị?** Do giao diện JMX chuẩn hoặc assembler quyết định, tùy loại đối tượng và đường xuất.

Mô hình:

```text
ApplicationContext
    |
    +-- cacheService -----------------------+
    |                                      |
    +-- orderService                       |
    |                                      |
    +-- mBeanExporter                      |
            |                              |
            | setBeans: ObjectName -> bean |
            +------------------------------+
            |
            | setAssembler(...)
            v
       MBeanInfoAssembler
            |
            | Chọn getter / setter / operation
            | Tạo ModelMBeanInfo
            v
       ModelMBean adapter
            |
            | registerMBean(...)
            v
         MBeanServer
            |
            v
       JConsole / JMX client
```

Với ví dụ này, exporter đăng ký `cacheService`; assembler chỉ công bố những method được cấu hình. `orderService` vẫn có thể là một Spring bean hợp lệ nhưng không phải đối tượng được export.

## 3. Chuẩn bị managed object dưới dạng POJO

Tạo class không implement interface `*MBean`, để phần management interface do assembler xác định.

**CacheService.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheService {
    private final AtomicInteger entryCount = new AtomicInteger(3);
    private final AtomicInteger resetCount = new AtomicInteger();

    public int getEntryCount() {
        return entryCount.get();
    }

    public int getResetCount() {
        return resetCount.get();
    }

    public void resetStatistics() {
        resetCount.incrementAndGet();
    }

    public void deleteAllCustomerData() {
        throw new UnsupportedOperationException(
                "Sensitive business operation must not be exposed via JMX");
    }
}
```

Class chứa nhiều public methods nhưng chỉ một số được chọn làm management interface. Phần `deleteAllCustomerData()` là method minh họa để cho thấy hậu quả nếu dùng assembler quá rộng. Trong ứng dụng thực tế, logic nghiệp vụ nhạy cảm cần được bảo vệ theo kiến trúc và quyền truy cập riêng; không nên dựa vào tên method để bảo vệ.

## 4. Đăng ký MethodNameBasedMBeanInfoAssembler trong MBeanExporter

`MethodNameBasedMBeanInfoAssembler` thuộc package `org.springframework.jmx.export.assembler`. Nó cho phép chỉ định các method cần được đưa vào metadata quản lý.

Ví dụ Java configuration:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class CacheJmxConfiguration {

    @Bean
    public CacheService cacheService() {
        return new CacheService();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler cacheAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
                new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
                "getEntryCount",
                "getResetCount",
                "resetStatistics"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter cacheExporter(
            CacheService cacheService,
            MBeanServer platformMBeanServer,
            MethodNameBasedMBeanInfoAssembler cacheAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setAssembler(cacheAssembler);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=CacheService,name=primary",
                cacheService
        ));
        return exporter;
    }
}
```

Các điểm cần hiểu:

- `cacheService()` tạo object đang được quản lý, dùng cùng instance với các Spring component khác nếu chúng inject bean này.
- `platformMBeanServer()` chọn server JMX của JVM hiện tại.
- `cacheAssembler()` chỉ ra ba method được đưa vào `ModelMBeanInfo`.
- `cacheExporter()` gắn assembler bằng `setAssembler(cacheAssembler)` và đăng ký `cacheService` dưới một `ObjectName`.
- `deleteAllCustomerData()` không nằm trong danh sách nên không được assembler này công bố.
- Method getter có thể được mô hình hóa thành JMX attribute, còn `resetStatistics()` có thể xuất hiện trong operations.

Lưu ý về `setManagedMethods`: API Spring nhận danh sách tên method, không định danh từng overload theo kiểu tham số. Nếu class có nhiều method cùng tên nhưng signature khác nhau, hãy kiểm tra metadata thực tế hoặc ưu tiên tên quản trị không overload để tránh nhầm lẫn.

### Điều gì xảy ra khi không gọi setAssembler?

`MBeanExporter` có thể dùng assembler mặc định cho các POJO thích hợp. Tùy cấu hình/phiên bản, cách assemble mặc định có thể công bố rộng hơn danh sách method mà bạn mong muốn. Vì vậy, với bean chứa nhiều public method nghiệp vụ, nên chọn assembler hoặc management interface tường minh, rồi xác minh danh sách attributes/operations bằng `MBeanInfo`.

Không nên giả định rằng một public method nhạy cảm được bảo vệ chỉ vì bạn chưa gắn annotation `@ManagedOperation`: với một assembler theo method naming, mức phơi bày phụ thuộc cấu hình assembler, không phụ thuộc annotation.

## 5. Chạy trong ApplicationContext

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            CacheService cache = context.getBean(CacheService.class);
            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName objectName = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            System.out.println("Registered: "
                    + server.isRegistered(objectName));
            System.out.println("Entries: "
                    + server.getAttribute(objectName, "EntryCount"));

            cache.resetStatistics();
            System.out.println("Resets: "
                    + server.getAttribute(objectName, "ResetCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read();
        }
    }
}
```

Spring khởi tạo exporter cùng context. Sau khi đăng ký thành công, JMX client kết nối đúng JVM sẽ thấy `ObjectName` và metadata do assembler cung cấp. Đóng context bình thường kích hoạt lifecycle cleanup của exporter đối với các đăng ký do nó quản lý.

Với ví dụ tạo platform server, không cần khởi động remote JMX để gọi API trong cùng JVM. Kết nối từ máy khác có yêu cầu cấu hình JMX remote và bảo mật riêng.

## 6. Kiểm tra chính xác management interface bằng MBeanInfo

Để biết một method có bị lộ ra JMX hay không, hãy đọc metadata từ server, không suy đoán từ class Java:

```java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InspectJmx {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            MBeanInfo info = server.getMBeanInfo(name);

            System.out.println("Attributes:");
            for (var attribute : info.getAttributes()) {
                System.out.printf(
                        "  %s: %s, readable=%s writable=%s%n",
                        attribute.getName(),
                        attribute.getType(),
                        attribute.isReadable(),
                        attribute.isWritable());
            }

            System.out.println("Operations:");
            for (var operation : info.getOperations()) {
                System.out.println(
                        "  " + operation.getName());
            }
        }
    }
}
```

Với cấu hình assembler chỉ chọn ba method, ta kỳ vọng thấy thuộc tính `EntryCount`, `ResetCount` và operation `resetStatistics` theo metadata ModelMBean đã assemble. Phần biểu diễn cụ thể getter thành attribute/operation có thể tùy chiến lược assembler và JMX ModelMBean; vì vậy assertion thực tế phải dựa vào `MBeanInfo` trả về.

Điều quan trọng nhất: `deleteAllCustomerData` không được công bố dưới dạng operation có thể gọi từ JMX. Đây là một kiểm tra cần thực hiện khi thiết kế management interface theo cơ chế assembler.

## 7. Kiểm thử tích hợp sự phơi bày có kiểm soát

Ví dụ JUnit Jupiter:

```java
package com.example.jmx;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CacheAssemblerTest {

    @Test
    void onlySelectedMethodsAreExposed() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "EntryCount".equals(a.getName())));

            assertTrue(Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "ResetCount".equals(a.getName())));

            assertTrue(Arrays.stream(info.getOperations())
                    .anyMatch(o -> "resetStatistics".equals(o.getName())));

            assertFalse(Arrays.stream(info.getOperations())
                    .anyMatch(o ->
                            "deleteAllCustomerData".equals(o.getName())));
        }
    }
}
```

Đây là test minh họa cách xác minh registry/metadata. Nếu dự án có nhiều test JMX song song dùng cùng platform server và `ObjectName`, chúng có thể xung đột. Trong suite lớn, nên dùng server test riêng, tên domain riêng hoặc cấu hình cô lập context để đảm bảo độc lập.

Không cần gọi một operation nhạy cảm để chứng minh nó bị ẩn; đọc `MBeanInfo` là cách an toàn hơn để kiểm tra nó không xuất hiện trong hợp đồng quản lý.

## 8. InterfaceBasedMBeanInfoAssembler: chọn method bằng interface riêng

Thay vì liệt kê tên method, bạn có thể định nghĩa một interface chỉ chứa API quản trị:

```java
package com.example.jmx;

public interface CacheManagement {
    int getEntryCount();
    int getResetCount();
    void resetStatistics();
}
```

Class nghiệp vụ implement interface này:

```java
public class CacheService implements CacheManagement {
    // Triển khai các method của CacheManagement.
    // Các method nghiệp vụ khác không nằm trong interface quản trị.
}
```

Sau đó dùng `InterfaceBasedMBeanInfoAssembler`:

```java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
public InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();

    assembler.setManagedInterfaces(CacheManagement.class);
    return assembler;
}
```

Trong exporter:

```java
exporter.setAssembler(interfaceAssembler);
```

Lợi ích là hợp đồng quản trị được mô tả bằng một Java interface rõ ràng, compiler hỗ trợ kiểm tra signature. Đây là **management interface do Spring assembler sử dụng**, không nhất thiết là Standard MBean interface theo quy ước `ClassNameMBean`.

So sánh:

| Assembler | Cách chọn method | Phù hợp khi |
| --- | --- | --- |
| `MethodNameBasedMBeanInfoAssembler` | Chọn tên method cụ thể | Số method quản trị ít, dễ chỉ định |
| `InterfaceBasedMBeanInfoAssembler` | Chọn các method được khai báo qua interface quản lý | Muốn API quản trị tường minh, có kiểm tra compile-time |
| `MetadataMBeanInfoAssembler` | Đọc metadata từ nguồn phù hợp, thường Spring JMX annotation | Muốn mô tả attribute/operation qua annotation |

Tên `CacheManagement` không có hậu tố `MBean` vẫn hợp lệ cho interface-based assembler: assembler sử dụng interface như cấu hình để dựng `ModelMBeanInfo`. Đừng nhầm cách này với trực tiếp đăng ký một Standard MBean trong JMX, nơi quy ước tên interface có vai trò riêng.

## 9. MetadataMBeanInfoAssembler và annotation JMX

Nếu muốn điều khiển management interface bằng Spring annotations, có thể dùng `MetadataMBeanInfoAssembler` kết hợp `AnnotationJmxAttributeSource`:

```java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
public AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
public MetadataMBeanInfoAssembler metadataAssembler(
        AnnotationJmxAttributeSource jmxAttributeSource) {
    MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(jmxAttributeSource);
    return assembler;
}
```

Một managed object được đánh dấu:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jmx:type=CacheAdmin,name=primary")
public class CacheAdmin {

    @ManagedAttribute(description = "Current entry count")
    public int getEntryCount() {
        return 3;
    }

    @ManagedOperation(description = "Reset cache statistics")
    public void resetStatistics() {
        // ...
    }
}
```

Trong cấu hình đầy đủ, exporter phải được thiết lập đúng naming strategy và assembler/attribute source khi cần; chỉ gọi `setAssembler(metadataAssembler)` không tự bảo đảm tên `ObjectName` sẽ được suy ra từ `@ManagedResource` nếu naming strategy không đọc annotation. Nếu muốn tiện ích tích hợp sẵn, `AnnotationMBeanExporter` hoặc `@EnableMBeanExport` thường giúp đồng bộ bộ đọc annotation, assembler và naming.

Khi dùng `MetadataMBeanInfoAssembler`, bean được chọn để export vẫn là một quyết định riêng. Không nên hiểu “có assembler đọc annotation” là “Spring tự quét và đăng ký mọi class có annotation” nếu chưa bật chiến lược autodetection phù hợp.

## 10. Chọn bean tường minh và autodetection

Một exporter có thể dùng `setBeans(...)` để chọn đích:

```java
exporter.setBeans(Map.of(
        "com.example.jmx:type=CacheService,name=primary",
        cacheService
));
```

Hoặc cấu hình một chế độ autodetect để tìm bean theo các cơ chế mà Spring hỗ trợ. Những hằng mode có thể gặp gồm `AUTODETECT_NONE`, `AUTODETECT_MBEAN`, `AUTODETECT_ASSEMBLER`, `AUTODETECT_ALL`.

Ví dụ ý nghĩa:

- `AUTODETECT_NONE`: chỉ xuất các bean được cấu hình tường minh.
- `AUTODETECT_MBEAN`: xét các bean tuân thủ MBean convention.
- `AUTODETECT_ASSEMBLER`: xét các bean có thể được assembler nhận diện theo metadata.
- `AUTODETECT_ALL`: kết hợp các nguồn phát hiện theo cấu hình.

Với mục tiêu học về cách **đăng ký assembler**, `setBeans` giúp tách lựa chọn bean khỏi lựa chọn method. Khi đưa vào hệ thống nhiều bean, cân nhắc rõ chiến lược autodetection để tránh mở rộng bề mặt quản trị vô tình.

Một assembler chỉ chọn được method cho object mà exporter thực sự đưa vào quá trình assemble. Nếu object không nằm trong danh sách bean được export, nó sẽ không xuất hiện trong registry dù assembler được cấu hình chính xác.

## 11. Ví dụ XML configuration

Spring Framework cũng hỗ trợ XML bean definitions:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="cacheService" class="com.example.jmx.CacheService"/>

    <bean id="cacheAssembler"
          class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
        <property name="managedMethods">
            <list>
                <value>getEntryCount</value>
                <value>getResetCount</value>
                <value>resetStatistics</value>
            </list>
        </property>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="assembler" ref="cacheAssembler"/>
        <property name="beans">
            <map>
                <entry
                    key="com.example.jmx:type=CacheService,name=primary"
                    value-ref="cacheService"/>
            </map>
        </property>
    </bean>
</beans>
```

Ở ví dụ XML này, exporter chưa chỉ định `server` nên sẽ sử dụng cơ chế tìm server theo Spring configuration thực tế. Nếu muốn chắc chắn nó đăng ký vào platform `MBeanServer`, thêm một bean `MBeanServer` hoặc `MBeanServerFactoryBean` phù hợp rồi inject qua thuộc tính `server`.

Cách khai báo XML và Java config khác cú pháp nhưng cùng mô hình: bean exporter tham chiếu assembler, bean được quản lý và server.

## 12. Vòng đời và lỗi cấu hình

Khi `ApplicationContext` khởi tạo:

1. Spring tạo các bean phụ thuộc, bao gồm object cần xuất và assembler.
2. `MBeanExporter` nhận server, assembler, mapping bean → `ObjectName`.
3. Exporter dựng metadata hoặc dùng hợp đồng MBean sẵn có tùy loại bean.
4. Exporter đăng ký MBean với `MBeanServer`.
5. Client JMX có thể truy vấn metadata và gọi operation theo quyền.

Khi context đóng bình thường, exporter có thể hủy đăng ký các MBean mà nó quản lý. Trong ứng dụng có nhiều exporters hoặc contexts dùng chung platform server, cần tránh cùng `ObjectName` và xác định ownership.

Một số lỗi cần nhận biết:

| Triệu chứng | Nguyên nhân cần xem | Hướng xử lý |
| --- | --- | --- |
| MBean không xuất hiện | Exporter không được khai báo thành bean, bean không nằm trong mapping, sai server | Kiểm tra context, `setBeans`, server và `isRegistered` |
| Attribute/operation quá nhiều | Assembler quá rộng hoặc không được gắn đúng | Kiểm tra `setAssembler` và `MBeanInfo` |
| Method mong đợi không có | Sai tên method, getter/setter không hợp lệ, assembler không chọn | So sánh method khai báo và metadata |
| `InstanceAlreadyExistsException` | Trùng `ObjectName` trong cùng server | Chọn tên duy nhất, kiểm tra lifecycle |
| `NotCompliantMBeanException` / lỗi metadata | Kiểu MBean/metadata không hợp lệ | Kiểm tra class, assembler, method signature |
| JConsole không thấy MBean | Sai JVM/PID hoặc context đã đóng | Xác nhận `ObjectName`, server và tiến trình |
| Method nhạy cảm xuất hiện | Sai cơ chế assembler hoặc cấu hình chọn method | Thu hẹp management interface và kiểm tra lại |
| Đổi assembler nhưng client vẫn thấy metadata cũ | MBean cũ còn đăng ký, context chưa khởi tạo lại | Kiểm tra registration policy và đúng instance |

## 13. Bảo mật và phạm vi phơi bày

`MBeanInfoAssembler` là công cụ thiết kế management interface; nó không phải hệ thống xác thực. Ngay cả khi assembler chỉ công bố vài method, một JMX client có quyền truy cập vẫn có thể gọi các operation đó. Vì vậy:

- Chỉ đưa các phương thức cần thiết cho vận hành vào assembler.
- Không công bố khóa bí mật, token hoặc dữ liệu khách hàng thông qua attributes.
- Giữ operation có side effect như `clearCache`, `reloadRules`, `shutdown` trong phạm vi đã được duyệt và kiểm soát.
- Thiết kế validation và precondition ngay trong implementation khi phù hợp.
- Với remote JMX, cấu hình xác thực, quyền và giới hạn network phù hợp.
- Kiểm tra `MBeanInfo` sau khi xuất thay vì suy luận dựa trên tên Java.

Nếu business service có nhiều method không an toàn cho quản trị, tạo một **management facade/adapter** riêng thường giúp giới hạn bề mặt JMX rõ ràng hơn. Sau đó assembler có thể chọn method trên facade với số lượng nhỏ và ý nghĩa ổn định.

## 14. Bài tập thực hành

**Bài 1 — Chọn method bằng tên.** Tạo class `QueueService` có `getQueueDepth()`, `getProcessedCount()`, `resetCounters()`, `deleteAllPendingJobs()`. Dùng `MethodNameBasedMBeanInfoAssembler` chỉ export ba method đầu; kiểm tra `MBeanInfo` không có `deleteAllPendingJobs`.

**Bài 2 — Thay management interface.** Tạo `QueueManagement` interface chỉ có `getQueueDepth()` và `resetCounters()`, rồi đổi sang `InterfaceBasedMBeanInfoAssembler`. So sánh metadata của hai cách cấu hình.

**Bài 3 — Annotation metadata.** Gắn `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` lên class test và cấu hình `MetadataMBeanInfoAssembler` cùng `AnnotationJmxAttributeSource`. Kiểm tra `ObjectName` và metadata; giải thích vì sao naming strategy phải phù hợp với annotation.

**Bài 4 — Test cùng instance.** Inject cùng bean `QueueService` vào business service và exporter. Thay đổi số đếm từ business service rồi đọc qua JMX để xác minh không có một instance quản trị riêng biệt.

**Bài 5 — Autodetection.** So sánh `setBeans` với một mode autodetection phù hợp. Kiểm tra có bao nhiêu MBean xuất hiện và operation nào được công bố, sau đó giải thích vì sao hai quyết định này độc lập.

## Kết luận

Đăng ký assembler trong `MBeanExporter` nghĩa là cung cấp một `MBeanInfoAssembler` để Spring xây dựng management interface cho bean được xuất. **Exporter chọn đối tượng và đăng ký nó; assembler quyết định metadata quản lý của đối tượng thích hợp.** Có thể dùng `MethodNameBasedMBeanInfoAssembler` cho danh sách method, `InterfaceBasedMBeanInfoAssembler` cho hợp đồng Java interface và `MetadataMBeanInfoAssembler` cho metadata kiểu annotation. Để xác nhận cấu hình đúng, hãy kiểm tra `ObjectName`, attributes và operations từ `MBeanServer`, đặc biệt bảo đảm không phơi bày những method nghiệp vụ không được dự định cho quản trị.
