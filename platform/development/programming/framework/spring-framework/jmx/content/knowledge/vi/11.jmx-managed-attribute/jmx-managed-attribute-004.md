# Description, default descriptor và metadata của @ManagedAttribute trong Spring Framework JMX

## 1. Bối cảnh và mục tiêu

Khi một Spring bean được xuất sang JMX, các công cụ quản trị như JConsole hoặc client viết bằng Java có thể xem thuộc tính (attribute) của MBean. Ngoài giá trị của thuộc tính, JMX còn cung cấp **metadata**: thuộc tính tên gì, thuộc kiểu dữ liệu nào, có đọc/ghi được không, và mô tả dành cho người vận hành là gì.

Trong Spring Framework, annotation `@ManagedAttribute` cho phép mô tả một getter hoặc setter của bean như một thuộc tính quản trị. Bài học này tập trung vào **description, giá trị default và descriptor/metadata**, thay vì chỉ dừng ở cách thêm annotation. Những khái niệm này liên quan nhưng không đồng nhất:

- **Description** là văn bản giải thích ý nghĩa của thuộc tính.
- **Default value** là một thông tin mô tả giá trị mặc định trong metadata; nó không tự động gán giá trị thực tế cho bean.
- **Descriptor** là cấu trúc metadata mở rộng trong JMX, chứa các field được đặt tên và các giá trị của chúng.
- **MBeanAttributeInfo** cung cấp thông tin chuẩn của attribute như name, type, description, readable, writable.
- **MetadataMBeanInfoAssembler** là thành phần Spring chuyển thông tin từ annotation thành mô hình metadata quản trị.

Sau khi học, bạn có thể dùng `@ManagedAttribute(description = "...")`, hiểu `defaultValue`, khám phá metadata qua `MBeanServer.getMBeanInfo(...)`, đọc descriptor và phân biệt metadata với trạng thái runtime thật.

## 2. Mô hình: từ annotation đến JMX metadata

```text
Spring bean
  @ManagedResource
  @ManagedAttribute
       |
       v
AnnotationJmxAttributeSource
       |
       v
MetadataMBeanInfoAssembler
       |
       v
MBeanExporter
       |
       v
MBeanServer
       |
       +---- getAttribute(ObjectName, "Enabled")
       |         -> Trạng thái hiện tại
       |
       +---- getMBeanInfo(ObjectName)
                 -> MBeanAttributeInfo
                    name/type/description/readable/writable
                    descriptor fields (nếu có)
```

Điểm quan trọng: `getAttribute` trả giá trị tại thời điểm đọc; `getMBeanInfo` trả metadata về giao diện quản trị. Nếu metadata ghi một default value nào đó, client không được kết luận giá trị hiện tại chắc chắn bằng default ấy.

Trong JMX chuẩn, thông tin về attribute được biểu diễn bởi `javax.management.MBeanAttributeInfo`. Các MBean có thể dùng `ModelMBeanAttributeInfo`, hoặc loại metadata chuyên biệt khác, để mang thêm descriptor fields. Spring hỗ trợ tạo metadata dựa trên annotation trong quá trình export.

## 3. @ManagedAttribute mô tả điều gì?

Annotation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
```

được đặt trên phương thức getter/setter để khai báo thuộc tính quản trị theo cách export dựa trên metadata.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=WorkerConfig,name=Main",
    description = "Runtime configuration of the worker"
)
public class WorkerConfig {

    private volatile boolean enabled = true;

    @ManagedAttribute(
        description = "Whether the worker is accepting new jobs"
    )
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(
        description = "Enable or disable processing new jobs"
    )
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Nếu exporter và assembler được cấu hình để đọc metadata annotation, JMX công bố `Enabled` là một attribute có thể đọc và ghi. Client có thể xem tên, kiểu, quyền và mô tả trong `MBeanAttributeInfo`.

Trong mô hình quản trị, description trên getter/setter cần diễn giải cùng một ý nghĩa. Nếu chúng mâu thuẫn, công cụ quản trị có thể hiển thị metadata không như dự định, tùy cách assembler hợp nhất metadata. Hãy đặt mô tả nhất quán và rõ ràng, cho biết người vận hành cần hiểu giá trị như thế nào.

### 3.1. Attribute là hợp đồng quản trị

Không phải mọi field của lớp đều trở thành JMX attribute. Trong ví dụ, `enabled` là một field nội bộ. Các method `isEnabled()` và `setEnabled(...)` được assembler diễn giải thành attribute `Enabled`, nếu metadata source và exporter cho phép.

Một bean có thể có getter không được đánh dấu, ví dụ `getInternalToken()`; với assembler dựa trên annotation, getter ấy không nên được công bố chỉ vì nó public. Đây là lý do cần thiết kế interface quản trị có chủ ý.

### 3.2. Description không phải tên của attribute

```java
@ManagedAttribute(
    description = "Maximum number of tasks allowed in flight"
)
public int getMaxConcurrentTasks() {
    return maxConcurrentTasks;
}
```

Tên attribute được suy từ getter, thường là `MaxConcurrentTasks`. Description là câu tiếng Anh mô tả ý nghĩa cho con người. Client cần gọi:

```java
server.getAttribute(name, "MaxConcurrentTasks");
```

chứ không dùng chuỗi description để định tuyến. Description có thể thay đổi khi dịch thuật hoặc cập nhật tài liệu mà không cần đổi tên attribute đã công bố.

## 4. MBeanAttributeInfo: metadata chuẩn của JMX

API `MBeanServer.getMBeanInfo(ObjectName)` trả về `MBeanInfo`. Từ đó đọc danh sách attribute:

```java
import java.lang.management.ManagementFactory;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=WorkerConfig,name=Main"
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s type=%s readable=%s writable=%s description=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getDescription()
    );
}
```

Đoạn code giả định MBean đã được đăng ký trên platform MBeanServer. Nếu exporter dùng server khác, hãy gọi `getMBeanInfo` trên **đúng MBeanServer đó**.

| Phương thức | Vai trò |
| --- | --- |
| `getName()` | Tên attribute công bố |
| `getType()` | Tên kiểu Java của attribute |
| `getDescription()` | Văn bản mô tả |
| `isReadable()` | Cho phép client đọc |
| `isWritable()` | Cho phép client ghi |
| `isIs()` | Phản ánh getter dạng `isX()` cho boolean |
| `getDescriptor()` | Descriptor chứa metadata mở rộng nếu được cung cấp |

Ví dụ nếu JMX metadata cho `Enabled` chỉ ra `readable=true` và `writable=true`, client có thể gọi `getAttribute` và `setAttribute` đúng tên/kiểu. Tuy nhiên, quyền gọi thực tế vẫn còn chịu ảnh hưởng của bảo mật, policy và logic getter/setter.

## 5. Description: viết metadata để người vận hành hiểu đúng

Description nên trả lời câu hỏi “thuộc tính này biểu diễn điều gì?” và khi cần là “đơn vị, phạm vi và hậu quả khi thay đổi là gì?”.

### 5.1. Mô tả tốt và mô tả mơ hồ

| Mơ hồ | Dễ hiểu hơn |
| --- | --- |
| `"Count"` | `"Number of active jobs currently processing"` |
| `"Timeout"` | `"Maximum wait time for a job in milliseconds"` |
| `"Enabled"` | `"Whether new tasks can be accepted"` |
| `"Pool size"` | `"Maximum number of worker threads"` |

Với attribute có quyền ghi, description nên tránh hàm ý sai rằng thay đổi là tức thì nếu ứng dụng chỉ áp dụng sau khi reload. Ví dụ:

```java
@ManagedAttribute(
    description = "Requested worker count; applied on next scheduler cycle"
)
public void setRequestedWorkers(int workers) {
    this.requestedWorkers = workers;
}
```

Ở đây description giúp client hiểu setter thay đổi **requested configuration**, chưa chắc hệ thống đã chạy với số worker mới ngay lập tức.

### 5.2. Metadata cho hệ thống đa ngôn ngữ

Description là chuỗi metadata ở phía server. Nếu JMX client cần hiển thị bằng nhiều ngôn ngữ, ứng dụng UI có thể có cơ chế dịch riêng dựa trên tên attribute và loại MBean. Không nên đổi `ObjectName` hoặc tên attribute chỉ để dịch label.

Description không có vai trò định tuyến. Nó có thể được bổ sung hoặc cải thiện mà không thay đổi cách client gọi `getAttribute`.

### 5.3. Giữ mô tả bền vững

Description phù hợp cho ý nghĩa ổn định, không phải nơi ghi một giá trị đang thay đổi nhanh. Đừng đặt thông tin current state, timestamp runtime hoặc số lượng tác vụ hiện tại vào description nếu bạn mong muốn client liên tục cập nhật; các giá trị đó nên là attribute được đọc từ MBean.

## 6. Default value: metadata khác trạng thái thực

Spring `@ManagedAttribute` có thành phần `defaultValue` để mô tả giá trị mặc định của thuộc tính trong metadata quản trị. Ví dụ:

```java
@ManagedAttribute(
    description = "Maximum concurrent jobs",
    defaultValue = "8"
)
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}
```

**Điều cần hiểu:** `defaultValue = "8"` không thay thế việc khởi tạo biến `maxConcurrentJobs`, không tự gán giá trị 8 khi Spring tạo bean, và không tự xác thực setter.

Ví dụ khởi tạo runtime:

```java
public class JobConfig {
    private volatile int maxConcurrentJobs = 12;

    @ManagedAttribute(
        description = "Maximum concurrent jobs",
        defaultValue = "8"
    )
    public int getMaxConcurrentJobs() {
        return maxConcurrentJobs;
    }
}
```

Nếu MBean được xuất đúng, đọc attribute `MaxConcurrentJobs` có thể trả `12` vì đó là trạng thái của bean, dù metadata mô tả default `8`. Dữ liệu metadata và dữ liệu runtime phục vụ hai mục đích khác nhau.

### 6.1. Default trong metadata có tác dụng gì?

Default có thể hữu ích cho công cụ quản trị muốn hiển thị cấu hình mặc định, hoặc cho lớp quản lý hỗ trợ các descriptor liên quan. Mức độ sử dụng phụ thuộc vào kiểu MBean, assembler và client. Không phải mọi client JMX đều hiển thị hoặc diễn giải default như nhau.

Một số công cụ chỉ dùng name/type/readable/writable/description. Vì vậy không nên thiết kế luồng nghiệp vụ dựa trên giả định rằng client sẽ tự áp dụng `defaultValue`.

### 6.2. Dùng defaultValue cho kiểu số và boolean

Annotation khai báo default qua chuỗi. Khi ghi metadata, nó phải được diễn giải theo hợp đồng metadata của Spring/JMX và kiểu dữ liệu attribute được công bố. Nếu giá trị default phức tạp hoặc không tương thích, người dùng có thể hiểu sai hoặc công cụ quản trị có thể không sử dụng được.

Nên chọn default thể hiện đúng cấu hình thực tế và nhất quán với tài liệu. Nhưng nếu runtime default đến từ properties, environment hoặc database, hãy cập nhật quy tắc mô tả phù hợp thay vì để metadata cố định sai lệch.

### 6.3. Không nhầm với @Value hoặc cấu hình Spring Boot

```java
@Value("${worker.max-concurrent:8}")
private int maxConcurrentJobs;
```

`@Value` trong Spring có thể inject giá trị cấu hình theo property resolution. `@ManagedAttribute(defaultValue = "8")` mô tả metadata JMX. Hai annotation giải quyết hai bài toán độc lập. Nếu cần biết giá trị hiện tại, phải đọc bean hoặc JMX attribute, không dựa vào default metadata.

## 7. Descriptor là gì?

JMX cung cấp interface `javax.management.Descriptor`. Có thể hiểu descriptor là **tập hợp các field có tên**, dùng để gắn metadata mở rộng vào các đối tượng quản trị.

Ví dụ về hình dạng logic:

```text
Descriptor:
  name = MaxConcurrentJobs
  descriptorType = attribute
  default = 8
  currencyTimeLimit = 10
```

Các field cụ thể và cách diễn giải phụ thuộc loại MBean/ModelMBean và thành phần tạo metadata. Không phải mọi `MBeanAttributeInfo` đều chứa đúng những field ví dụ trên, và không phải mọi công cụ JMX đều sử dụng chúng.

JMX phân biệt các khái niệm:

- `MBeanInfo`: metadata tổng thể về MBean.
- `MBeanAttributeInfo`: metadata chuẩn về một attribute.
- `Descriptor`: metadata mở rộng gắn với MBean hoặc từng thành phần.
- `ModelMBeanAttributeInfo`: dạng metadata dành cho Model MBean, có thể dùng descriptor với các field được quy định bởi mô hình ModelMBean.

Đặc điểm quan trọng của descriptor là **có cấu trúc**: thay vì nhét nhiều ý nghĩa vào một câu description, metadata có thể biểu diễn thành field có tên để client hoặc ModelMBean xử lý theo hợp đồng.

## 8. Đọc descriptor bằng Java

Sau khi `MBeanInfo` đã có, có thể lấy descriptor từ từng attribute:

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    Descriptor descriptor = attr.getDescriptor();

    System.out.println("Attribute: " + attr.getName());
    System.out.println("Description: " + attr.getDescription());

    for (String fieldName : descriptor.getFieldNames()) {
        System.out.printf(
            "  %s = %s%n",
            fieldName,
            descriptor.getFieldValue(fieldName)
        );
    }
}
```

Đây là cách quan sát các field mà MBean thực sự công bố. Danh sách có thể khác nhau tùy Spring metadata assembler, MBean type, server hoặc phiên bản thư viện. Không nên giả định rằng descriptor của mọi MBean đều có field `default`.

Để chỉ lấy một field:

```java
Object defaultMetadata =
    descriptor.getFieldValue("default");
```

Giá trị trả về có kiểu `Object`. Việc field không tồn tại có thể trả `null`; code client nên xử lý tình huống metadata thiếu. Không nên ép kiểu sang `String` nếu chưa biết emitter/assembler đã biểu diễn nó ra sao.

### 8.1. So sánh metadata và giá trị thực tế

```java
for (MBeanAttributeInfo attr : info.getAttributes()) {
    if (!attr.isReadable()) {
        continue;
    }

    Object current = server.getAttribute(name, attr.getName());
    Object declaredDefault =
        attr.getDescriptor().getFieldValue("default");

    System.out.printf(
        "%s: current=%s metadataDefault=%s%n",
        attr.getName(),
        current,
        declaredDefault
    );
}
```

Phép so sánh trên giúp thấy rõ sự khác biệt giữa **giá trị hiện tại** và **mô tả giá trị mặc định**. Nó không chứng minh rằng ứng dụng khởi động từ default đó, cũng không bảo đảm default có mặt trong metadata của mọi MBean.

## 9. Metadata assembly trong Spring

Để annotation được chuyển thành JMX metadata, Spring cần một nguồn metadata và assembler. Một cấu hình cơ bản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class JmxMetadataConfig {

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }
}
```

Trong một ứng dụng thực tế, cấu hình exporter cũng phải dùng assembler này; nếu chỉ khai báo assembler bean mà exporter không tham chiếu tới, metadata JMX có thể được xuất theo cơ chế khác.

Ví dụ:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanServer jmxServer() {
    return ManagementFactory.getPlatformMBeanServer();
}

@Bean
public MBeanExporter workerExporter(
        WorkerConfig workerConfig,
        MetadataMBeanInfoAssembler assembler,
        MBeanServer jmxServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(jmxServer);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.monitoring:type=WorkerConfig,name=Main",
        workerConfig
    ));
    return exporter;
}
```

Đoạn cấu hình thứ hai cần nằm trong một class `@Configuration` phù hợp và có bean `WorkerConfig` được tạo trong context. Sau khi exporter chạy, client có thể kiểm tra `MBeanInfo` để xem metadata được công bố.

Spring cũng có cấu hình annotation-driven, chẳng hạn `@EnableMBeanExport`, nhằm thiết lập hạ tầng tương ứng. Khi dùng cấu hình đó, tránh vô tình tạo exporter thủ công thứ hai cho cùng bean/ObjectName.

## 10. Ví dụ hoàn chỉnh: ManagedAttribute có description và default

Một resource với ngưỡng xử lý tác vụ:

```java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=JobSettings,name=Main",
    description = "Manage worker runtime limits"
)
public class JobSettings {

    private volatile int maxConcurrentJobs = 8;

    @ManagedAttribute(
        description = "Maximum number of concurrent jobs",
        defaultValue = "8"
    )
    public int getMaxConcurrentJobs() {
        return maxConcurrentJobs;
    }

    @ManagedAttribute(
        description = "Set the maximum concurrent jobs"
    )
    public void setMaxConcurrentJobs(int next) {
        if (next < 1 || next > 128) {
            throw new IllegalArgumentException(
                "maxConcurrentJobs must be between 1 and 128"
            );
        }
        maxConcurrentJobs = next;
    }
}
```

Ở ví dụ này:

- Runtime mặc định bằng 8 nhờ field initializer `= 8`.
- Annotation cũng mô tả default 8 trong metadata.
- Setter kiểm tra miền giá trị từ 1 đến 128, **không dựa vào description hoặc defaultValue để tự validation**.
- `MBeanExporter` cần đăng ký object và dùng metadata assembler phù hợp để attribute xuất hiện.
- Khi client ghi 16, `getAttribute(name, "MaxConcurrentJobs")` trả 16, trong khi mô tả default vẫn có thể là 8.

Đọc và ghi:

```java
import javax.management.Attribute;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=JobSettings,name=Main"
);

int before = (Integer) server.getAttribute(
    name, "MaxConcurrentJobs"
);

server.setAttribute(
    name,
    new Attribute("MaxConcurrentJobs", Integer.valueOf(16))
);

int after = (Integer) server.getAttribute(
    name, "MaxConcurrentJobs"
);

System.out.printf("Before=%d After=%d%n", before, after);
```

Nếu nhận `AttributeNotFoundException`, hãy kiểm tra metadata thực sự được xuất. Nếu nhận lỗi từ setter, kiểm tra giá trị truyền vào và logic validation. Có thể kiểm tra `isWritable()` trên `MBeanAttributeInfo` trước khi cho phép thao tác từ công cụ quản trị.

## 11. Metadata là hợp đồng, không phải cơ chế runtime

Một số nhầm lẫn dễ gặp:

| Nhầm lẫn | Thực tế |
| --- | --- |
| Có `description` thì UI tự có bản dịch | Description chỉ là chuỗi metadata; bản địa hóa do client quyết định |
| `defaultValue = "8"` tự gán 8 vào field | Phải khởi tạo cấu hình/field riêng |
| Descriptor chứa default nghĩa là current value bằng default | Current value phải đọc bằng `getAttribute` |
| Gắn `@ManagedAttribute` thì bean tự đăng ký | Phải có exporter và MBeanServer |
| Getter Java public luôn thành JMX attribute | Phụ thuộc MBean interface/assembler |
| Descriptor nào cũng có đủ tất cả field | Field phụ thuộc loại MBean và metadata được tạo |
| Description dùng làm tên attribute khi gọi API | Client dùng `MBeanAttributeInfo.getName()` |
| Metadata có writable=true nghĩa là client luôn có quyền sửa | Vẫn cần authorization và setter chấp nhận giá trị |

Metadata nên được hiểu như tài liệu máy đọc về bề mặt quản trị. Nó cho biết cách một JMX client có thể khám phá và tương tác với resource, nhưng không thay thế việc thi hành quy tắc nghiệp vụ và kiểm soát truy cập.

## 12. Các tình huống nên sử dụng description/default/descriptor

### 12.1. Giúp dashboard hiểu attribute

Dashboard giám sát hàng chục MBean có thể hiển thị `MBeanAttributeInfo.getDescription()` bên cạnh tên attribute. Ví dụ thay `MaxConcurrentJobs` bằng mô tả “Maximum number of concurrent jobs” giúp người vận hành hiểu rõ hơn.

Nếu cần hiển thị đơn vị, description có thể ghi rõ “milliseconds” hoặc “bytes”. Đây là thông tin có ích, nhưng khi ứng dụng/client dùng metadata có cấu trúc cho đơn vị và ràng buộc, nên duy trì một hợp đồng rõ ràng thay vì bắt người đọc phân tích chuỗi mô tả bằng regex.

### 12.2. Mô tả cấu hình mặc định

Default value trong metadata giúp công cụ quản trị biết giá trị đề xuất hoặc mặc định. Nhưng nếu ứng dụng có cấu hình override từ môi trường, mô tả mặc định vẫn có thể khác giá trị khởi động thực tế.

Để tránh hiểu sai, client có thể trình bày:

```text
Maximum concurrent jobs
Current value: 16
Declared default: 8
```

Thay vì chỉ hiển thị “Default: 8” khiến người dùng nghĩ runtime đang chạy với giá trị 8.

### 12.3. Công cụ quản trị tự khám phá

Một công cụ không biết trước tên attribute có thể:

1. Gọi `getMBeanInfo`.
2. Đọc `getAttributes()`.
3. Lấy name/type/readable/writable/description.
4. Kiểm tra descriptor fields nếu có.
5. Chỉ tạo control chỉnh sửa với attribute writable và kiểu dữ liệu được hỗ trợ.
6. Đọc current value bằng `getAttribute`.
7. Gửi `setAttribute` nếu người dùng được phép, rồi đọc lại để xác nhận.

Đây là lý do metadata nhất quán có giá trị: nó giúp công cụ hiển thị và xử lý những MBean không được hard-code từ trước.

## 13. Khám phá metadata mà không phụ thuộc cấu hình cụ thể

Một utility Java minh họa việc in metadata theo kiểu defensively:

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeMetadataPrinter {

    private AttributeMetadataPrinter() {}

    public static void print(
            MBeanServerConnection connection,
            ObjectName objectName) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(objectName);

        System.out.println("MBean: " + objectName);
        System.out.println("MBean description: "
            + info.getDescription());

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "%s: type=%s, readable=%s, writable=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable()
            );
            System.out.println("  " + attr.getDescription());

            Descriptor descriptor = attr.getDescriptor();
            for (String field : descriptor.getFieldNames()) {
                Object value = descriptor.getFieldValue(field);
                System.out.printf("  descriptor[%s]=%s%n",
                    field, value);
            }

            if (attr.isReadable()) {
                try {
                    Object current = connection.getAttribute(
                        objectName, attr.getName());
                    System.out.println("  current=" + current);
                } catch (Exception ex) {
                    System.out.println("  read failed: "
                        + ex.getClass().getSimpleName());
                }
            }
        }
    }
}
```

Dùng `MBeanServerConnection` cho phép utility làm việc qua server local hoặc remote. Vì metadata và trạng thái hiện tại có vòng đời khác nhau, thuộc tính có thể thay đổi hoặc MBean có thể bị unregister ngay sau khi `getMBeanInfo`; code client phải chấp nhận lỗi thực tế khi đọc.

Không nên log secret hoặc các attribute nhạy cảm ở môi trường production. Một utility khám phá tổng quát cần có danh sách loại trừ và policy quyền truy cập thích hợp.

## 14. Bài tập thực hành

Dùng `JobSettings` ở phần 10 và một `MBeanExporter` sử dụng metadata assembler:

1. Khởi tạo bean với `maxConcurrentJobs = 8`.
2. Export thành MBean với ObjectName `com.example.monitoring:type=JobSettings,name=Main`.
3. Gọi `MBeanServer.getMBeanInfo(name)`.
4. Tìm `MBeanAttributeInfo` có tên `MaxConcurrentJobs`.
5. In `getType()`, `isReadable()`, `isWritable()`, `getDescription()`.
6. In toàn bộ field từ `getDescriptor()` và quan sát có field default hay không.
7. Đọc current value qua `getAttribute` (dự kiến 8).
8. Ghi giá trị 16 và đọc lại (dự kiến 16).
9. Quan sát metadata default vẫn mô tả 8 nếu được exporter đưa vào descriptor.
10. Thử ghi 0; setter trong ví dụ sẽ từ chối giá trị ngoài miền cho phép.
11. Ghi lại 8 để đưa runtime về cấu hình ban đầu.

Phần khó của bài tập không phải ghi thuộc tính, mà là diễn giải đúng: **description/default/descriptor thuộc metadata; current value và validation thuộc runtime**.

## 15. Câu hỏi tự kiểm tra

**1. `@ManagedAttribute(description = "...")` có đổi tên attribute không?** Không; tên attribute được suy từ method hoặc cấu hình metadata tương ứng.

**2. `MBeanAttributeInfo.getDescription()` dùng để làm gì?** Đưa ra mô tả của thuộc tính cho client/công cụ quản trị.

**3. `defaultValue` trong `@ManagedAttribute` có tự gán state của bean không?** Không; đó là metadata.

**4. JMX API nào trả giá trị hiện tại của thuộc tính?** `getAttribute(ObjectName, String)`.

**5. API nào trả mô tả và quyền đọc/ghi của thuộc tính?** `getMBeanInfo(ObjectName)`, sau đó đọc `MBeanAttributeInfo`.

**6. Descriptor khác description như thế nào?** Description là chuỗi mô tả; descriptor là tập hợp field có tên dành cho metadata mở rộng.

**7. Có thể giả định descriptor luôn chứa `default` không?** Không; điều đó phụ thuộc loại MBean, assembler và metadata được công bố.

**8. Vì sao không dùng metadata để thay thế validation trong setter?** Metadata không tự thực thi quy tắc nghiệp vụ hoặc ràng buộc mọi lời gọi JMX.

**9. Khi metadata nói writable nhưng setAttribute lỗi, cần kiểm tra gì?** Quyền truy cập, kiểu giá trị, setter logic và lỗi từ MBean.

**10. Có thể đổi description mà giữ client hoạt động không?** Thường có, nếu tên attribute và hợp đồng quản trị không đổi; client không nên định tuyến bằng description.

## 16. Ghi nhớ

- **`@ManagedAttribute`** mô tả một getter/setter thành JMX attribute khi exporter/assembler hỗ trợ.
- **Description** giúp công cụ và người vận hành hiểu ý nghĩa attribute.
- **Default value** là thông tin mô tả; không tự gán giá trị cho field.
- **Descriptor** là metadata dạng field/value, không phải trạng thái runtime.
- **`MBeanAttributeInfo`** cung cấp name, type, description, readable/writable và descriptor.
- **`getMBeanInfo`** đọc metadata; **`getAttribute`** đọc giá trị hiện tại.
- **`AnnotationJmxAttributeSource` + `MetadataMBeanInfoAssembler` + `MBeanExporter`** là một đường tích hợp Spring JMX thường gặp.
- Không đánh đồng metadata với cơ chế validation, authorization hay trạng thái live.

Khi thiết kế attribute quản trị, hãy viết description rõ ràng, default phản ánh hợp đồng cấu hình, và chỉ dựa vào descriptor sau khi xem metadata thực tế của MBean. Sự phân biệt này giúp client JMX diễn giải đúng trạng thái và giảm nhầm lẫn giữa “giá trị mặc định” với “giá trị đang chạy”.