# MethodNameBasedMBeanInfoAssembler trong Spring Framework JMX

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vai trò của `MethodNameBasedMBeanInfoAssembler` trong việc tạo **management interface** cho Spring bean.
- Cấu hình danh sách tên method được xuất qua JMX bằng `managedMethods` và cơ chế cấu hình tương ứng.
- Phân biệt phương thức Java, JMX attribute và JMX operation khi assembler tạo `ModelMBeanInfo`.
- Kết hợp assembler với `MBeanExporter`, `ObjectName` và `MBeanServer`.
- Nhận biết giới hạn của lựa chọn theo **tên method** khi có overloaded methods, proxy, đổi tên API và nhiều bean.
- Kiểm tra hợp đồng quản trị thực tế bằng `MBeanInfo`, JConsole hoặc Java Mission Control.

## 2. Vị trí của assembler trong quá trình xuất MBean

Spring JMX có thể xuất một Spring bean thành MBean mà không bắt buộc bean phải tự định nghĩa interface `SomethingMBean` theo chuẩn Standard MBean. Với **Model MBean**, Spring dùng một `MBeanInfoAssembler` để quyết định những thành phần nào của bean sẽ được công bố.

Luồng khái niệm:

```text
Spring bean
  |
  v
MBeanExporter
  |
  +--> ObjectNamingStrategy --> ObjectName
  |
  +--> MBeanInfoAssembler --> metadata quản trị
  |                            (attributes, operations, descriptions)
  v
ModelMBean được đăng ký trong MBeanServer
  |
  v
JConsole / JMC / JMX client
```

`org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler` là một assembler cung cấp cách chọn các phương thức quản trị dựa vào **tên method**, thay vì phải gắn annotation cho từng method hay dùng một Java interface chỉ dành cho quản trị.

Đây là lựa chọn hữu ích khi bạn cần xuất một tập nhỏ các method của một class hiện có, đặc biệt khi class đó không muốn phụ thuộc vào Spring JMX annotation.

**Phân biệt ba yếu tố:**

| Thành phần | Chức năng |
| --- | --- |
| `MBeanExporter` | Nhận bean, tạo/đăng ký MBean vào `MBeanServer` và quản lý vòng đời |
| `MethodNameBasedMBeanInfoAssembler` | Chọn method tham gia hợp đồng quản trị theo danh sách tên |
| `ObjectName` | Tên định danh MBean trong `MBeanServer`, ví dụ `com.example.jobs:type=Worker,name=Billing` |

Assembler không phải JMX server và không tự mở kết nối JMX remote. Nó cung cấp **metadata** cho exporter.

## 3. Khi nào nên dùng MethodNameBasedMBeanInfoAssembler?

Giả sử một service Java có nhiều method:

```java
public class BillingWorker {
    private volatile boolean paused;
    private volatile int pendingJobs = 25;

    public int getPendingJobs() {
        return pendingJobs;
    }

    public boolean isPaused() {
        return paused;
    }

    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    public void retryFailedJobs(int limit) {
        // Gọi nghiệp vụ retry với giới hạn.
    }

    public void reconcileLedger() {
        // Nghiệp vụ nội bộ, không muốn lộ qua JMX.
    }
}
```

Bạn muốn người vận hành chỉ xem `PendingJobs` và `Paused`, đồng thời có thể yêu cầu `retryFailedJobs`, nhưng **không** được gọi `reconcileLedger`.

Thay vì xuất tất cả public methods, hãy tạo một allowlist gồm đúng tên cần quản trị:

```text
getPendingJobs
isPaused
setPaused
retryFailedJobs
```

Assembler chọn các method tương ứng. Trong JMX, getter/setter được nhận diện theo quy ước JavaBeans có thể trở thành attribute, còn thao tác nghiệp vụ được xuất như operation tùy logic tạo metadata của Spring.

**Tư duy an toàn:** danh sách method được quản trị là một phần hợp đồng public của ứng dụng. Hãy chọn có chủ đích và giữ hẹp, không coi `public` đồng nghĩa với `safe for remote management`.

## 4. Cấu hình Java với MBeanExporter

Ví dụ sau cấu hình assembler và exporter bằng Spring Java configuration:

```java
package com.example.billing.config;

import com.example.billing.BillingWorker;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class BillingJmxConfig {

    @Bean
    public BillingWorker billingWorker() {
        return new BillingWorker();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler billingAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
                new MethodNameBasedMBeanInfoAssembler();

        assembler.setManagedMethods(
                "getPendingJobs",
                "isPaused",
                "setPaused",
                "retryFailedJobs"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter billingExporter(
            BillingWorker billingWorker,
            MethodNameBasedMBeanInfoAssembler billingAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(billingAssembler);
        exporter.setBeans(Map.of(
            "com.example.billing:type=Worker,name=Billing",
            billingWorker
        ));
        return exporter;
    }
}
```

Ở đây:

1. `billingWorker` là bean thực thi logic.
2. `billingAssembler` xác định các method được công bố.
3. `setBeans` ánh xạ một `ObjectName` tới bean cụ thể.
4. Exporter dùng assembler tạo metadata cho Model MBean.
5. MBeanServer lưu MBean để JMX client truy xuất.

Cần import class `BillingWorker` trong ví dụ dự án thực tế. Cấu hình này giả định không có exporter khác đã đăng ký cùng `ObjectName`.

### Trường hợp cấu hình mảng rõ ràng

Trong một số phong cách Java, bạn có thể xây mảng:

```java
String[] allowed = {
    "getPendingJobs",
    "isPaused",
    "setPaused",
    "retryFailedJobs"
};
assembler.setManagedMethods(allowed);
```

Danh sách này có ý nghĩa **allowlist**. Nếu muốn thêm một operation, hãy bổ sung tên method và xem đó là thay đổi hợp đồng JMX cần được kiểm soát.

## 5. Cấu hình XML tương đương

Dự án dùng XML có thể khai báo bean assembler rồi gắn vào exporter:

```xml
<bean id="billingWorker" class="com.example.billing.BillingWorker"/>

<bean id="billingAssembler"
      class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
    <property name="managedMethods">
        <list>
            <value>getPendingJobs</value>
            <value>isPaused</value>
            <value>setPaused</value>
            <value>retryFailedJobs</value>
        </list>
    </property>
</bean>

<bean id="billingExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="assembler" ref="billingAssembler"/>
    <property name="beans">
        <map>
            <entry key="com.example.billing:type=Worker,name=Billing"
                   value-ref="billingWorker"/>
        </map>
    </property>
</bean>
```

Trong XML, property `managedMethods` nhận danh sách string thể hiện tên method. Exporter chỉ sử dụng assembler đã cấu hình nếu property `assembler` được liên kết đúng.

Phân biệt với:

```xml
<context:mbean-export/>
```

Phần tử `context:mbean-export` thường dùng để bật export dựa trên annotation (như `@ManagedResource` và `@ManagedOperation`). Nó **không tự dùng** bean `MethodNameBasedMBeanInfoAssembler` mà bạn vừa khai báo cho mọi exporter khác. Muốn chọn method theo tên, hãy cấu hình assembler cụ thể trên exporter có trách nhiệm đăng ký bean.

Khi hai cơ chế cùng hoạt động, cần tránh trùng `ObjectName`.

## 6. Cơ chế chọn method theo tên

`MethodNameBasedMBeanInfoAssembler` thuộc nhóm assembler dựa trên tên và so khớp tên Java method được xét để công bố quản trị.

Về mặt thiết kế, điều này có nghĩa:

- `getPendingJobs()` có tên trong allowlist thì được xét để export.
- `retryFailedJobs(int)` có tên trong allowlist thì được xét để export.
- `reconcileLedger()` không có tên trong danh sách nên không được đưa vào metadata theo allowlist.
- Nếu class có nhiều method overload cùng tên, cách cấu hình **chỉ bằng tên** không phải là cơ chế chọn riêng một overload dựa trên chữ ký tham số.

Ví dụ:

```java
public void retryFailedJobs(int limit) { /* ... */ }

public void retryFailedJobs(String jobId) { /* ... */ }
```

Nếu allowlist chứa `retryFailedJobs`, đừng mặc định rằng chỉ overload nhận `int` được công bố. Cần kiểm tra `MBeanInfo.getOperations()` hoặc thiết kế tên khác nhau, chẳng hạn:

```java
public void retryUpTo(int limit) { /* ... */ }

public void retryById(String jobId) { /* ... */ }
```

Khi yêu cầu hợp đồng JMX rất chặt về chữ ký, cân nhắc interface Standard MBean/MXBean rõ ràng, adapter quản trị hoặc assembler/metadata khác phù hợp hơn.

## 7. Getter, setter và JMX attribute

Một tình huống quan trọng là sự khác nhau giữa **tên method Java** và **tên attribute trong JMX**.

Java method:

```java
public int getPendingJobs();
public boolean isPaused();
public void setPaused(boolean paused);
```

Metadata quản trị có thể biểu diễn thành:

```text
Attributes:
  PendingJobs    int      read-only
  Paused         boolean  read-write
```

Đó là cách JavaBeans naming thường được Spring phân tích khi xây MBean metadata. Chọn một getter để đọc; thêm setter khi thực sự muốn cho phép thay đổi trạng thái qua JMX.

Nếu chỉ đưa `getPendingJobs` vào allowlist thì client không thể mặc nhiên thay đổi `PendingJobs`. Nếu có `setPaused` trong allowlist, người dùng có quyền ghi `Paused` có thể thay đổi trạng thái ứng dụng.

**Không coi setter là vô hại.** Xuất `setEnabled`, `setTimeout` hoặc `setPaused` cũng là công bố một điểm điều khiển quản trị tương tự operation.

Một phương thức không tuân theo getter/setter conventions, chẳng hạn `pendingJobs()`, thường sẽ được xem là operation nếu được công bố chứ không tự động thành `PendingJobs` attribute.

## 8. MethodNameBasedMBeanInfoAssembler có phải interface Java mới không?

Không. Assembler cung cấp một **management interface ở mức metadata JMX**, không tạo source file Java interface mới có tên `BillingWorkerMBean`.

Hai mô hình có thể cho ra trải nghiệm JMX tương tự nhưng cách xác định hợp đồng khác nhau:

**Standard MBean:**

```java
public interface BillingWorkerMBean {
    int getPendingJobs();
    void retryFailedJobs(int limit);
}
```

```java
public class BillingWorker implements BillingWorkerMBean {
    // ...
}
```

**Spring Model MBean với name-based assembler:**

```text
BillingWorker (class Java hiện có)
    +
MethodNameBasedMBeanInfoAssembler
    +
MBeanExporter
    =
MBean với management metadata được chọn theo tên method
```

Lợi ích của cách thứ hai là giảm phụ thuộc của service class vào JMX interface chuyên dụng. Nhưng đổi lại, hợp đồng phụ thuộc vào string trong cấu hình và quy tắc introspection, cần test sau khi refactor.

## 9. So sánh các assembler thường gặp

| Loại assembler | Phương thức lựa chọn | Khi nào thích hợp |
| --- | --- | --- |
| `SimpleReflectiveMBeanInfoAssembler` | Dựa trên phản chiếu các method đủ điều kiện | Demo/khai phá; cẩn thận vì bề mặt expose rộng |
| `MethodNameBasedMBeanInfoAssembler` | Danh sách tên method được quản lý | Cần allowlist đơn giản, không muốn sửa class |
| `MethodExclusionMBeanInfoAssembler` | Danh sách tên bị loại trừ | Cần loại một số method trong API lớn; phải quản lý rủi ro phát sinh method mới |
| `InterfaceBasedMBeanInfoAssembler` | Các interface Java được chỉ định | Cần hợp đồng interface rõ ràng |
| `MetadataMBeanInfoAssembler` | Annotation/metadata qua `JmxAttributeSource` | Cần mô tả chi tiết trên code bằng `@Managed*` |

Một quy tắc lựa chọn hữu ích:

- Muốn expose ít method từ class có sẵn: **MethodNameBased**.
- Muốn hợp đồng quản trị ổn định, có kiểu rõ ràng: **InterfaceBased** hoặc adapter Standard MBean.
- Muốn method, attribute, description và tham số có tài liệu sát code: **MetadataMBeanInfoAssembler** và annotation phù hợp.

Không có lựa chọn nào tự giải quyết toàn bộ bảo mật; mỗi cơ chế đều cần xem xét phạm vi method được công bố.

## 10. Kiểm tra kết quả bằng MBeanInfo

Sau khi Spring context khởi động và exporter đăng ký thành công, dùng JMX API đọc metadata.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.billing:type=Worker,name=Billing"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("Billing worker MBean was not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, read=%s, write=%s%n",
        attr.getName(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "Operation: %s, return=%s%n",
        op.getName(),
        op.getReturnType()
    );
}
```

Ví dụ trên chỉ đúng nếu exporter đăng ký vào **platform `MBeanServer`**. Với MBeanServer tùy chỉnh, phải dùng reference tới đúng server đó.

Để xem kết quả sử dụng:

```java
Object count = server.getAttribute(name, "PendingJobs");
System.out.println("Pending: " + count);
```

Và gọi operation:

```java
server.invoke(
    name,
    "retryFailedJobs",
    new Object[] { 5 },
    new String[] { "int" }
);
```

Nếu `MBeanInfo` không có operation hoặc attribute như kỳ vọng, hãy kiểm tra xem tên method trong `managedMethods` có chính xác và được exporter xét trên class thực sự hay không.

## 11. Khác biệt giữa tên method và signature khi gọi JMX

`managedMethods` hoạt động ở lớp **chọn method để tạo metadata**; còn `MBeanServer.invoke` hoạt động ở lớp **gọi operation đã được công bố**.

Ví dụ cấu hình:

```java
assembler.setManagedMethods("retryFailedJobs");
```

Khi gọi JMX operation, vẫn cần đúng signature:

```java
server.invoke(
    name,
    "retryFailedJobs",
    new Object[] { Integer.valueOf(5) },
    new String[] { "int" }
);
```

Nếu khai báo parameter type trong JMX metadata là `int`, phải dùng `"int"`. Truyền signature `"java.lang.Integer"` không tương đương. Nếu overload khác nhau, việc gọi đúng signature là bắt buộc.

Tốt nhất lấy `MBeanOperationInfo.getSignature()` để biết tên và kiểu từng tham số thay vì đoán từ source method.

## 12. Spring AOP proxy và lựa chọn phương thức

Một Spring bean có thể được bọc bằng JDK proxy hoặc CGLIB do `@Transactional`, `@Async`, security hoặc custom advice.

Nếu exporter nhận proxy thay cho target, tập method và metadata thực tế có thể khác class đích:

```text
MBeanExporter
    |
    v
Spring AOP proxy
    |
    v
BillingWorker target
```

Đặc biệt với JDK dynamic proxy:

- Proxy chỉ triển khai các interface được chỉ định.
- Một method public chỉ có trên target class nhưng không thuộc interface có thể không gọi được qua proxy.
- Cấu hình theo tên không tự làm proxy expose thêm method.

Với CGLIB/class-based proxy, class proxy kế thừa target class nhưng vẫn cần kiểm tra phương thức thực sự được intercept và public signature mà exporter dùng.

Giải pháp khi đường gọi cần rõ ràng là **JMX adapter**:

```java
public interface BillingControlService {
    int pendingJobs();
    void retryFailedJobs(int maxCount);
}

public final class BillingJmxAdapter {
    private final BillingControlService delegate;

    public BillingJmxAdapter(BillingControlService delegate) {
        this.delegate = delegate;
    }

    public int getPendingJobs() {
        return delegate.pendingJobs();
    }

    public void retryFailedJobs(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }
        delegate.retryFailedJobs(maxCount);
    }
}
```

Exporter đăng ký adapter, assembler chọn `getPendingJobs` và `retryFailedJobs`. Delegate có thể là Spring proxy để tiếp tục áp dụng transaction/security advice trên service.

Một adapter còn giúp tránh công bố các method nghiệp vụ nhạy cảm khi service thêm chức năng mới.

## 13. Rủi ro khi đổi tên method hoặc refactor

Allowlist bằng chuỗi là cấu hình **không được compiler bảo đảm** giống một method call trực tiếp.

Giả sử đổi:

```java
getPendingJobs()  -> getQueueDepth()
```

nhưng quên đổi:

```java
assembler.setManagedMethods("getPendingJobs");
```

Khi Spring tạo MBean metadata, method cũ không còn tồn tại và attribute mong đợi có thể biến mất. Phần còn lại của ứng dụng vẫn có thể compile và chạy, khiến lỗi chỉ xuất hiện ở công cụ quản trị.

Các biện pháp hữu ích:

1. Tập trung danh sách managed method tại một cấu hình duy nhất.
2. Viết integration test kiểm tra `MBeanInfo` sau khi context khởi động.
3. Ghi nhận `ObjectName` và thuộc tính/operation ổn định như một API contract.
4. Khi rename, cập nhật dashboard, alert và script trước khi loại bỏ tên cũ.
5. Không dùng pattern tên mơ hồ hoặc broad exposure chỉ để bù thiếu method sau refactor.

Nếu cần yêu cầu contract chặt chẽ và khó thay đổi, interface-based hoặc annotation metadata có kiểm soát có thể phù hợp hơn.

## 14. Bảo mật: không lộ quá nhiều method

`MethodNameBasedMBeanInfoAssembler` giúp giảm số method được công bố, nhưng danh sách method **không phải hệ thống phân quyền**.

Nếu `retryFailedJobs` nằm trong allowlist, client có khả năng invoke có thể gọi method đó theo quyền JMX của nó. Một operation có thể thay đổi trạng thái, kích hoạt retry, xóa cache hoặc làm gián đoạn dịch vụ.

Hãy kết hợp:

- Chỉ expose method có mục đích quản trị rõ ràng.
- Validate tham số và giới hạn tần suất/cường độ operation.
- Không export method trả secret, token hoặc dữ liệu cá nhân.
- Cấu hình authentication, authorization và TLS cho remote JMX theo chính sách.
- Giới hạn network access tới cổng JMX.
- Ghi log/audit action quan trọng nếu hệ thống cần truy vết.
- Kiểm tra các aspect bảo mật có được thực thi khi JMX gọi vào bean hay không.

Không dựa vào việc JConsole hiển thị một operation như “read-only” hay description thân thiện để kết luận nó an toàn.

## 15. Vòng đời và các lỗi hay gặp

`MBeanExporter` đăng ký MBean khi Spring context khởi tạo và hủy đăng ký các MBean do nó quản lý khi context đóng bình thường.

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| MBean không xuất hiện | Exporter chưa khởi tạo, bean chưa được map, server khác | Kiểm tra context, `setBeans`, `MBeanServer` |
| `InstanceAlreadyExistsException` | Trùng ObjectName do nhiều exporter/context | Chọn một owner cho registration |
| `NotCompliantMBeanException` | Bean không phù hợp cách export hoặc proxy/hợp đồng không hợp lệ | Kiểm tra assembler, kiểu bean, JMX contract |
| Chỉ thấy vài attributes | Thiếu tên getter/setter trong `managedMethods` | So sánh allowlist với method runtime |
| Không thấy operation mong đợi | Sai chính tả tên hoặc đã đổi tên method | Kiểm tra `MBeanInfo`, refactor |
| `ReflectionException` khi invoke | Tên operation hoặc signature không trùng metadata | Xem `MBeanOperationInfo.getSignature()` |
| Operation chạy nhưng không qua Spring advice | Đăng ký target thay proxy | Dùng adapter hoặc delegate proxy đúng cách |
| Client từ xa không đọc được dữ liệu | Remote JMX/serialization hoặc quyền truy cập | Kiểm tra connector, TLS, authentication, kiểu dữ liệu |

Để chẩn đoán, bắt đầu từ ba câu hỏi: **MBean đã được đăng ký chưa? `MBeanInfo` có tên mong đợi không? Chữ ký invocation có khớp không?**

## 16. Thực hành với nhiều bean và lựa chọn cấu hình phù hợp

Giả sử ứng dụng có hai worker:

```text
com.example.billing:type=Worker,name=Invoicing
com.example.billing:type=Worker,name=Reconciliation
```

Nếu cả hai có cùng cấu trúc method, chúng có thể dùng cùng một assembler allowlist:

```java
exporter.setBeans(Map.of(
    "com.example.billing:type=Worker,name=Invoicing", invoicingWorker,
    "com.example.billing:type=Worker,name=Reconciliation", reconciliationWorker
));
exporter.setAssembler(billingAssembler);
```

Khi hai bean cần các tập method khác nhau, một allowlist chung có thể không đúng: operation hợp lệ cho worker này nhưng không phù hợp worker kia. Khi đó cân nhắc tạo các exporter hoặc assembler cấu hình riêng có ownership rõ, hoặc sử dụng assembler hỗ trợ phân biệt theo bean key / management interface riêng.

**Không lạm dụng việc tạo exporter mới** nếu nó gây trùng đăng ký hay khó quản lý lifecycle. Mỗi ObjectName chỉ nên có một chủ sở hữu đăng ký trong cùng MBeanServer.

## 17. Bài tập thực hành

1. Tạo class `BillingWorker` với `getPendingJobs`, `isPaused`, `setPaused`, `retryFailedJobs` và `reconcileLedger`. Cấu hình `MethodNameBasedMBeanInfoAssembler` chỉ công bố bốn method đầu.
2. Mở JConsole hoặc JMC, xác nhận `PendingJobs`, `Paused` và `retryFailedJobs` xuất hiện; `reconcileLedger` không nằm trong hợp đồng.
3. Loại `setPaused` khỏi allowlist, khởi tạo lại context và xem `Paused` còn writable không.
4. Tạo hai overload `retryFailedJobs(int)` và `retryFailedJobs(String)`. Xem `MBeanInfo` để hiểu hạn chế của việc chọn bằng tên.
5. Đổi tên `getPendingJobs` thành `getQueueDepth` nhưng giữ cấu hình cũ; quan sát tác động tới metadata và sửa allowlist.
6. Viết integration test xác minh ObjectName, attribute/operation mong đợi và cleanup khi đóng context.
7. Thử thay bean trực tiếp bằng adapter gọi qua Spring proxy; kiểm tra advice có còn được thực thi khi gọi JMX không.

## 18. Câu hỏi tự kiểm tra

- `MethodNameBasedMBeanInfoAssembler` quyết định điều gì trong quá trình export MBean?
- Vì sao cấu hình `managedMethods` là một allowlist chứ không phải hệ thống phân quyền?
- Một getter `getPendingJobs` được chọn có thể được thể hiện dưới dạng gì trong JMX?
- Vì sao overload là trường hợp cần chú ý khi lựa chọn theo tên method?
- Nếu đổi tên Java method mà quên sửa XML, lỗi có nhất thiết được compiler phát hiện không?
- `MethodNameBasedMBeanInfoAssembler` khác `MetadataMBeanInfoAssembler` và `InterfaceBasedMBeanInfoAssembler` như thế nào?
- Khi Spring AOP proxy không expose một method, danh sách `managedMethods` có tự sửa được tình huống đó không?
- Cách xác minh chính xác một operation đã được xuất là gì?

**Ghi nhớ:** `MethodNameBasedMBeanInfoAssembler` là công cụ Spring JMX để xác định bề mặt quản trị dựa trên **danh sách tên phương thức**. Nó cho phép chọn một tập nhỏ các method từ Spring bean mà không cần sửa class để gắn annotation. Hãy cấu hình allowlist chính xác, kết nối assembler với đúng `MBeanExporter`, kiểm tra `MBeanInfo` sau khi đăng ký và bảo vệ các operation có side effect bằng cơ chế quyền và validation phù hợp.