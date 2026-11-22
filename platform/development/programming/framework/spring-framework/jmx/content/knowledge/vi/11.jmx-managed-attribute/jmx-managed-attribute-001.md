# Spring Framework JMX: @ManagedAttribute và cách phơi bày property

## 1. Mục tiêu bài học

Trong Spring Framework JMX, annotation \`@ManagedAttribute\` đánh dấu các phương thức truy cập property mà ứng dụng muốn công bố cho công cụ quản trị. Khi bean được Spring export thành MBean, JConsole hoặc Java JMX client có thể đọc hoặc ghi các **JMX attributes** tương ứng mà không cần lấy bean từ \`ApplicationContext\`.

Bài học làm rõ cách Spring ánh xạ Java getter/setter thành attribute, sự khác nhau giữa thuộc tính chỉ đọc và đọc/ghi, cách chọn chính xác dữ liệu được expose, cách khai báo metadata và những giới hạn khi dùng trong môi trường thực tế.

\`\`\`text
Spring-managed Java bean
  getMaxConnections()
  setMaxConnections(int)
  getActiveConnections()
  resetStatistics()
           |
           | @ManagedResource + @ManagedAttribute
           v
Spring MBeanExporter + metadata assembler
           |
           v
MBeanServer: com.example.app:type=ConnectionPool,name=primary
           |
           +-- MaxConnections: int  [read/write]
           +-- ActiveConnections: int [read-only]
           |
           +-- resetStatistics(): operation (chỉ nếu được export riêng)
           |
           v
JConsole / MBeanServerConnection
\`\`\`

**Điểm cốt lõi:** \`@ManagedAttribute\` là metadata của Spring dành cho property quản trị. Nó không tạo ra field mới, không tự động lưu cấu hình xuống đĩa, không bảo đảm tính thread-safe và không tự bật một JMX exporter. Những yếu tố này phải được thiết kế và cấu hình riêng.

## 2. JavaBean property và JMX attribute

Một property JavaBean thông thường được biểu diễn qua phương thức truy cập:

\`\`\`java
public int getMaxConnections();
public void setMaxConnections(int value);
\`\`\`

Theo quy ước JavaBeans, \`getMaxConnections()\` là getter cho property \`maxConnections\`, còn \`setMaxConnections(int)\` là setter cho property đó.

Khi được export qua Spring JMX, client thường nhìn thấy attribute có tên \`MaxConnections\` (định dạng tên được quyết định bởi metadata/exporter). Client không gọi trực tiếp method \`getMaxConnections\` theo cách Java thông thường; nó giao tiếp qua tên attribute:

\`\`\`java
Object current = server.getAttribute(objectName, "MaxConnections");
server.setAttribute(
    objectName,
    new Attribute("MaxConnections", 20)
);
\`\`\`

Trong MBean metadata, một attribute có những thông tin quan trọng:

| Thông tin | Ý nghĩa |
|---|---|
| \`name\` | Tên attribute dùng trong API JMX |
| \`type\` | Kiểu dữ liệu được công bố, ví dụ \`int\`, \`boolean\`, \`java.lang.String\` |
| \`description\` | Mô tả hành vi hoặc ý nghĩa quản trị |
| \`isReadable()\` | Client có quyền đọc theo hợp đồng attribute không |
| \`isWritable()\` | Client có thể thực hiện ghi theo hợp đồng attribute không |
| \`isIs()\` | Attribute boolean có getter dạng \`isXxx()\` hay không |

Hợp đồng JavaBeans cung cấp cách nhận diện getter và setter; annotation và assembler quyết định member nào thật sự được expose.

## 3. Khai báo @ManagedResource và @ManagedAttribute

Ví dụ một bean quản lý số lượng kết nối tối đa và số kết nối đang hoạt động.

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=ConnectionPool,name=primary",
    description = "Example runtime connection pool controls"
)
public class ConnectionPoolControl {

    private volatile int maxConnections = 16;
    private final AtomicInteger activeConnections = new AtomicInteger();

    @ManagedAttribute(
        description = "Maximum configured concurrent connections"
    )
    public int getMaxConnections() {
        return maxConnections;
    }

    @ManagedAttribute(
        description = "Changes the maximum connection limit"
    )
    public void setMaxConnections(int maxConnections) {
        if (maxConnections < 1 || maxConnections > 200) {
            throw new IllegalArgumentException(
                "maxConnections must be from 1 to 200"
            );
        }
        this.maxConnections = maxConnections;
    }

    @ManagedAttribute(
        description = "Currently active connections"
    )
    public int getActiveConnections() {
        return activeConnections.get();
    }

    // Chỉ dành cho logic nội bộ, không phải JMX attribute.
    public void recordConnectionOpened() {
        activeConnections.incrementAndGet();
    }

    public void recordConnectionClosed() {
        activeConnections.decrementAndGet();
    }
}
\`\`\`

Với metadata assembler đọc annotation của Spring, các thành viên quản trị dự kiến là:

\`\`\`text
MBean:
  com.example.app:type=ConnectionPool,name=primary

Attributes:
  MaxConnections
    type: int
    readable: true
    writable: true

  ActiveConnections
    type: int
    readable: true
    writable: false
\`\`\`

Ở đây \`MaxConnections\` có cả getter và setter được công bố. \`ActiveConnections\` chỉ có getter được công bố và vì vậy là read-only.

Phương thức \`recordConnectionOpened()\` và \`recordConnectionClosed()\` là public Java methods nhưng không có annotation JMX. Khi sử dụng annotation metadata assembler đúng cách, chúng không tự động trở thành JMX operations.

**Lưu ý ứng dụng thực:** thay đổi \`maxConnections\` trong field ví dụ chỉ đổi một giá trị cấu hình đang chạy. Nếu bean điều khiển connection pool thật, setter phải tích hợp logic resize hoặc cập nhật giới hạn của pool. Không nên để JMX báo đã cập nhật nhưng tài nguyên thực không đổi.

## 4. Annotation nên đặt ở đâu?

\`@ManagedAttribute\` dùng với các JavaBean accessor methods, thường là getter và setter. Không nên đặt nó trên field rồi kỳ vọng Spring tự suy ra đầy đủ cách đọc/ghi nếu cơ chế export của ứng dụng được xây để đọc metadata từ các phương thức.

Ví dụ đúng:

\`\`\`java
@ManagedAttribute
public int getTimeoutSeconds() {
    return timeoutSeconds;
}

@ManagedAttribute
public void setTimeoutSeconds(int value) {
    timeoutSeconds = value;
}
\`\`\`

Đối với property chỉ đọc:

\`\`\`java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
\`\`\`

Đối với property kiểu boolean, có thể dùng convention \`isXxx\`:

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

Một field đơn thuần như:

\`\`\`java
private volatile boolean paused;
\`\`\`

không phải là một thuộc tính có thể truy cập từ JMX nếu bạn chưa công bố accessor tương ứng trong hợp đồng quản trị.

## 5. Read-only, write-only và read/write

Khả năng truy cập attribute được xác định qua accessor được export và metadata mà MBeanServer cung cấp.

### 5.1. Chỉ đọc (read-only)

\`\`\`java
@ManagedAttribute(description = "Number of processed jobs")
public long getProcessedJobs() {
    return processedJobs.get();
}
\`\`\`

Client có thể đọc:

\`\`\`java
long count = (Long) server.getAttribute(
    objectName,
    "ProcessedJobs"
);
\`\`\`

Nếu không có setter được công bố, client không thể ghi attribute này. Cố ghi có thể dẫn tới \`AttributeNotFoundException\` hoặc exception tương ứng từ adapter.

Ví dụ những chỉ số nên để read-only: tổng request đã xử lý, số connection đang mở, thời điểm khởi động và trạng thái computed từ runtime.

### 5.2. Đọc và ghi (read/write)

\`\`\`java
@ManagedAttribute
public int getRefreshIntervalSeconds() {
    return refreshIntervalSeconds;
}

@ManagedAttribute
public void setRefreshIntervalSeconds(int value) {
    if (value < 5 || value > 3600) {
        throw new IllegalArgumentException("Expected 5..3600");
    }
    refreshIntervalSeconds = value;
}
\`\`\`

Đây là cấu hình runtime có thể quan sát và điều chỉnh. Client ghi rồi đọc lại:

\`\`\`java
server.setAttribute(
    objectName,
    new Attribute("RefreshIntervalSeconds", 60)
);

int observed = (Integer) server.getAttribute(
    objectName,
    "RefreshIntervalSeconds"
);
\`\`\`

Readback xác nhận giá trị bean đang công bố. Nó không nhất thiết chứng minh mọi worker hoặc scheduler phía sau đã áp dụng giá trị mới; điều đó phụ thuộc setter implementation.

### 5.3. Chỉ ghi (write-only)

Một property chỉ có setter được công bố về mặt lý thuyết có thể là write-only trong JMX metadata. Tuy vậy, write-only JMX attribute thường khó kiểm tra hậu trạng thái và có thể bị các công cụ quản trị xử lý khác nhau.

Nếu thao tác là thay đổi hành vi một lần, như \`clearCache()\`, hãy cân nhắc \`@ManagedOperation\` thay vì viết setter dạng \`setClearCache(true)\`. Nếu đây là cấu hình nhạy cảm không được trả ra cho client, cần thiết kế riêng và xác định rõ lý do write-only.

**Thực hành tốt:** chỉ mở quyền ghi khi có nhu cầu vận hành chính đáng và setter kiểm tra đầu vào.

## 6. @ManagedAttribute có đồng nghĩa với public setter không?

Không. Một setter tồn tại trong class không tự động làm property writable qua JMX nếu annotation assembler chỉ công bố getter đã annotate.

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getLimit() {
    return limit;
}

public void setLimit(int limit) {
    this.limit = limit;
}
\`\`\`

Trong cách export dựa trên annotation metadata, không nên mặc định setter không annotate sẽ được expose. Hãy kiểm tra \`MBeanInfo\` thực tế để biết \`Limit\` writable hay không.

Tương tự:

\`\`\`java
public int getLimit() {
    return limit;
}

@ManagedAttribute
public void setLimit(int limit) {
    this.limit = limit;
}
\`\`\`

Nếu getter chưa được đưa vào metadata, client không nên coi property có khả năng đọc. Hợp đồng JMX được xác nhận cuối cùng bằng \`MBeanAttributeInfo\`.

Điều này hữu ích khi bean chứa nhiều setter phục vụ application code nhưng chỉ một phần được phép gọi từ công cụ quản trị.

## 7. Cấu hình Spring để annotation có hiệu lực

Có annotation trong code chưa đủ. Bean phải được export vào \`MBeanServer\` bằng hạ tầng Spring JMX.

### 7.1. Cách ngắn gọn: @EnableMBeanExport

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    public ConnectionPoolControl connectionPoolControl() {
        return new ConnectionPoolControl();
    }
}
\`\`\`

Cấu hình annotation-driven tạo ra hạ tầng export phù hợp để Spring tìm bean \`@ManagedResource\` và expose các member được annotate.

Khi ứng dụng khởi động, exporter đăng ký bean dưới ObjectName đã khai báo nếu không gặp collision hoặc lỗi cấu hình.

### 7.2. Cấu hình tường minh: MBeanExporter + MetadataMBeanInfoAssembler

Ứng dụng có thể chủ động chọn bean và ObjectName:

\`\`\`java
package com.example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public AnnotationJmxAttributeSource annotationSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler metadataAssembler(
            AnnotationJmxAttributeSource annotationSource) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(annotationSource);
        return assembler;
    }

    @Bean
    public MBeanExporter exporter(
            ConnectionPoolControl control,
            MetadataMBeanInfoAssembler metadataAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(metadataAssembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=ConnectionPool,name=primary",
            control
        ));
        return exporter;
    }
}
\`\`\`

Khi dùng cách này, assembler lấy metadata từ \`@ManagedAttribute\`. Exporter quản lý mapping bean → ObjectName.

**Không cấu hình đồng thời hai exporter cùng đăng ký một bean** nếu không có kế hoạch ownership rõ ràng. Ví dụ bật \`@EnableMBeanExport\` rồi lại tạo một explicit exporter với cùng ObjectName có thể dẫn đến double-registration.

### 7.3. Cách kiểm tra hạ tầng

Khi MBean không xuất hiện, kiểm tra lần lượt:

1. Bean có thực sự được tạo trong \`ApplicationContext\`?
2. Class có \`@ManagedResource\` không?
3. Getter/setter mong muốn có \`@ManagedAttribute\` không?
4. Context có exporter phù hợp không?
5. ObjectName hợp lệ và duy nhất trong MBeanServer không?
6. Client có kết nối đúng MBeanServer mà exporter sử dụng không?
7. Startup log có exception liên quan registration hay metadata không?

Đối với Spring Boot, cấu hình JMX có thể được điều khiển bởi các property và auto-configuration của Boot. Cần kiểm tra \`spring.jmx.enabled\` cùng các exporter hiện hữu thay vì giả định việc auto-export giống nhau trong mọi runtime.

## 8. Đọc metadata để xác nhận attribute

API JMX chuẩn cho phép xác minh attribute sau khi export.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.app:type=ConnectionPool,name=primary"
);

if (!server.isRegistered(objectName)) {
    throw new IllegalStateException(
        "MBean not registered: " + objectName
    );
}

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

Đây là nguồn quan sát khách quan về hợp đồng JMX đã đăng ký. Nếu attribute không xuất hiện hoặc không writable như dự định, cần kiểm tra assembler, annotation, method signature và exporter configuration.

Trong hệ thống nhiều MBeanServer, thay \`ManagementFactory.getPlatformMBeanServer()\` bằng đúng server mà exporter đã đăng ký. Hai server trong cùng JVM có thể có registry khác nhau.

## 9. Giao tiếp với attribute qua MBeanServer

Giả sử \`ConnectionPoolControl\` đã được export như ví dụ.

### 9.1. Đọc

\`\`\`java
Object max = server.getAttribute(
    objectName,
    "MaxConnections"
);
System.out.println("Configured max = " + max);
\`\`\`

\`getAttribute\` trả \`Object\`; kiểu runtime thường là boxed type tương ứng với kiểu khai báo.

\`\`\`java
int configured = (Integer) server.getAttribute(
    objectName, "MaxConnections"
);

int active = (Integer) server.getAttribute(
    objectName, "ActiveConnections"
);
\`\`\`

Với attribute \`long\`, kết quả thường là \`Long\`. Ép \`Long\` sang \`Integer\` sẽ gây \`ClassCastException\` ở client, dù JMX đã đọc thành công.

### 9.2. Ghi

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    objectName,
    new Attribute("MaxConnections", 32)
);

int after = (Integer) server.getAttribute(
    objectName, "MaxConnections"
);

System.out.println("After = " + after);
\`\`\`

Với property \`int\`, giá trị được gửi qua JMX là Java \`Integer\` tương ứng. Chuỗi \`"32"\` không nhất thiết được tự động chuyển thành \`int\`.

### 9.3. Không thể ghi vào read-only attribute

\`\`\`java
server.setAttribute(
    objectName,
    new Attribute("ActiveConnections", 99)
);
\`\`\`

Do \`ActiveConnections\` chỉ công bố getter, thao tác ghi không hợp lệ theo metadata. Đây là lỗi quyền truy cập attribute, không phải cơ chế để trực tiếp sửa bộ đếm đo trạng thái runtime.

## 10. Description và metadata phục vụ người vận hành

Annotation hỗ trợ mô tả để người dùng công cụ JMX biết attribute thực sự có ý nghĩa gì:

\`\`\`java
@ManagedAttribute(
    description = "Idle timeout in seconds"
)
public int getIdleTimeoutSeconds() {
    return idleTimeoutSeconds;
}
\`\`\`

Mô tả hiệu quả nên trả lời:

- Attribute đo/cấu hình điều gì?
- Đơn vị là gì: giây, mili giây, byte, số lượng, phần trăm?
- Có thể sửa trực tiếp không? Nếu có, giá trị hợp lệ và tác dụng phụ là gì?
- Giá trị chỉ là cấu hình mong muốn hay trạng thái thực tế?
- Sau restart giá trị có được giữ lại không?

Ví dụ hai attribute có cùng kiểu \`int\` nhưng ý nghĩa khác nhau:

\`\`\`text
MaxConnections:
  Cấu hình giới hạn kết nối tối đa cho pool

ActiveConnections:
  Số kết nối đang sử dụng tại thời điểm đọc
\`\`\`

Nếu không làm rõ, người vận hành có thể nhầm số liệu đo với thông số cấu hình.

## 11. Khi nào dùng attribute và khi nào dùng operation?

\`@ManagedAttribute\` phù hợp với giá trị trạng thái hoặc cấu hình có thể biểu diễn như một property. \`@ManagedOperation\` phù hợp với hành động có chủ đích.

| Nhu cầu | Cách thể hiện gợi ý | Lý do |
|---|---|---|
| Đọc số request đã xử lý | \`@ManagedAttribute\` getter | Giá trị trạng thái, chỉ đọc |
| Chỉnh giới hạn worker | Getter/setter \`@ManagedAttribute\` | Một giá trị cấu hình runtime |
| Đọc worker đang paused không | Boolean \`@ManagedAttribute\` | Trạng thái hiện tại |
| Reset counters | \`@ManagedOperation\` | Hành động có tác dụng phụ |
| Xóa cache | \`@ManagedOperation\` | Hành động, không phải state |
| Reload cấu hình từ file | \`@ManagedOperation\` | Thực thi tác vụ có kết quả/thất bại |

Ví dụ operation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedOperation(description = "Reset connection statistics")
public void resetStatistics() {
    // ...
}
\`\`\`

Không nên thiết kế một writable attribute \`ClearCache\` rồi bắt client ghi \`true\` để ra lệnh xóa cache nếu bản chất đây là operation. Một property cần ngữ nghĩa đọc/ghi rõ ràng, còn operation có thể biểu diễn trạng thái thất bại và tham số nghiệp vụ tường minh.

## 12. Validation và an toàn của writable attribute

Khi expose setter, ứng dụng mở một đường thay đổi runtime. Client có thể là JConsole, script nội bộ hoặc remote JMX connector có quyền thao tác.

Một setter nên bảo đảm:

1. **Kiểu hợp lệ:** giá trị JMX đúng Java type.
2. **Miền giá trị hợp lệ:** ví dụ \`1 <= MaxConnections <= 200\`.
3. **Bất biến nghiệp vụ:** giới hạn mới không phá vỡ điều kiện mà service dựa vào.
4. **Áp dụng state nhất quán:** nếu thay đổi tài nguyên thật, cập nhật đúng các thành phần liên quan.
5. **Lỗi có nguyên nhân rõ:** ném exception thể hiện validation hoặc infrastructure failure.
6. **Có khả năng quan sát:** getter/metric/log phản ánh kết quả thay đổi.

Ví dụ:

\`\`\`java
@ManagedAttribute
public synchronized void setMaxConnections(int value) {
    if (value < 1 || value > 200) {
        throw new IllegalArgumentException(
            "Expected maxConnections between 1 and 200"
        );
    }

    // Trong ứng dụng thật: kiểm tra và cấu hình pool.
    maxConnections = value;
}
\`\`\`

\`synchronized\` trong ví dụ chỉ mô tả bảo vệ thao tác setter. Với tài nguyên thật, cần cân nhắc việc cập nhật nhiều state, race với worker và thời điểm bean công bố giá trị. \`volatile\` đảm bảo visibility cho một field, không biến thao tác đa bước thành transaction.

## 13. Lỗi thường gặp khi phơi bày property

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Không thấy MBean | Exporter chưa chạy, tên trùng hoặc bean không được tạo | Kiểm tra Spring context/exporter và registration log |
| MBean có nhưng thiếu attribute | Getter/setter thiếu annotation hoặc assembler không chọn | Đọc \`MBeanInfo\`, kiểm tra metadata |
| Attribute chỉ đọc dù có setter Java | Setter không được expose | Kiểm tra annotation trên setter và \`isWritable()\` |
| \`AttributeNotFoundException\` | Sai tên hoặc không có quyền đọc/ghi tương ứng | Kiểm tra tên chính xác và \`MBeanAttributeInfo\` |
| \`InvalidAttributeValueException\` | Giá trị truyền không hợp kiểu hoặc bị adapter từ chối | So \`getType()\` và kiểu Object trong \`Attribute\` |
| Setter ném lỗi | Validation, trạng thái hoặc logic backend thất bại | Xem target/cause exception và log ứng dụng |
| \`ClassCastException\` ở client | Client ép kiểu trả về sai | So loại attribute và boxed type |
| Đọc lại không đúng giá trị đã ghi | Setter chuẩn hóa giá trị hoặc có cập nhật đồng thời | Kiểm tra contract setter và concurrency |
| Thay đổi mất sau restart | Giá trị chỉ ở bộ nhớ | Thiết kế persist riêng nếu yêu cầu |
| Thấy attribute nhạy cảm | Expose getter không phù hợp | Thu hẹp giao diện quản trị và quyền truy cập |

\`AttributeNotFoundException\` không luôn có nghĩa chỉ sai chính tả; trong các tình huống read/write trái với metadata, client cũng có thể gặp lỗi này. Ngoài ra exception có thể được bọc bởi MBean adapter của Spring/JMX.

## 14. Các tình huống thiết kế thực tế

### 14.1. Property computed không nên ghi

\`\`\`java
@ManagedAttribute
public double getCpuLoad() {
    return cpuProbe.currentLoad();
}
\`\`\`

Giá trị đọc phản ánh trạng thái đo được. Không nên tạo setter giả \`setCpuLoad\` chỉ để dashboard có thể chỉnh số liệu.

### 14.2. Configuration property cần readback

\`\`\`java
@ManagedAttribute
public int getRetryLimit() {
    return retryLimit;
}

@ManagedAttribute
public void setRetryLimit(int retryLimit) {
    if (retryLimit < 0 || retryLimit > 10) {
        throw new IllegalArgumentException("retryLimit must be 0..10");
    }
    this.retryLimit = retryLimit;
}
\`\`\`

Công cụ vận hành có thể đọc trạng thái trước/sau. Nhưng nếu chương trình đọc lại file cấu hình vào thời điểm khác hoặc khởi động lại, giá trị có thể trở về mặc định.

### 14.3. Thuộc tính gắn với thông tin nhạy cảm

Không annotate các getter như:

\`\`\`java
public String getDatabasePassword() { /* ... */ return "..."; }
public String getAccessToken() { /* ... */ return "..."; }
\`\`\`

Ngay cả khi chỉ đọc, dữ liệu nhạy cảm có thể bị lộ qua JMX client, monitoring và log. Nếu thật sự cần quản trị credential, hãy dùng cơ chế secret management chuyên dụng, không biến giá trị bí mật thành attribute công khai.

### 14.4. Attribute có kiểu phức tạp

JMX client thường hỗ trợ các kiểu đơn giản dễ thao tác như \`String\`, \`int\`, \`long\`, \`boolean\` tốt hơn. Đối với dữ liệu phức tạp hoặc remote management, cần cân nhắc kiểu hợp lệ với JMX, MXBean open types hoặc cấu trúc \`CompositeData\`/tabular data.

Đừng mặc định một đối tượng domain tùy ý sẽ hiển thị đẹp hoặc được serialize an toàn qua remote JMX. Thiết kế DTO/metadata phù hợp nếu cần expose trạng thái phức tạp.

## 15. Bài thực hành

### Bài 1: Xác định read/write

Cho class:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=JobControl,name=main"
)
public class JobControl {

    @ManagedAttribute
    public int getMaxJobs() { return 8; }

    @ManagedAttribute
    public void setMaxJobs(int value) { /* ... */ }

    @ManagedAttribute
    public long getProcessedJobs() { return 100; }
}
\`\`\`

**Câu hỏi:** \`MaxJobs\` và \`ProcessedJobs\` có quyền đọc/ghi thế nào?

**Gợi ý:** \`MaxJobs\` có getter và setter được annotate, nên đọc/ghi. \`ProcessedJobs\` chỉ có getter, nên chỉ đọc.

### Bài 2: Chọn annotation phù hợp

Một lớp có phương thức \`clearCache()\`. Nên dùng \`@ManagedAttribute\` hay \`@ManagedOperation\`?

**Gợi ý:** \`clearCache()\` là hành động nên dùng \`@ManagedOperation\`.

### Bài 3: Phát hiện setter thiếu annotation

\`\`\`java
@ManagedAttribute
public int getThreshold() { return threshold; }

public void setThreshold(int threshold) {
    this.threshold = threshold;
}
\`\`\`

**Câu hỏi:** Có thể chắc chắn writable không?

**Gợi ý:** Không nên. Với annotation metadata assembler, cần đánh dấu setter và kiểm tra \`MBeanInfo\` sau khi export.

### Bài 4: Chẩn đoán sai kiểu

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxConnections", "32")
);
\`\`\`

**Câu hỏi:** Nếu property là \`int\`, tại sao có thể lỗi?

**Gợi ý:** Chuỗi \`"32"\` là \`String\`, không phải \`Integer\`.

### Bài 5: Đọc trạng thái sau khi ghi

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxConnections", 32)
);
int value = (Integer) server.getAttribute(
    name, "MaxConnections"
);
\`\`\`

**Câu hỏi:** \`value == 32\` có đủ chứng minh connection pool thật đã resize?

**Gợi ý:** Chưa đủ; còn phải quan sát tài nguyên thật hoặc metric tương ứng.

### Bài 6: Không thấy attribute dù annotation đúng

**Câu hỏi:** Điều gì cần kiểm tra trước khi sửa getter?

**Gợi ý:** Bean có export đúng MBeanServer và ObjectName không, exporter/assembler có được cấu hình chưa và có lỗi registration không.

## 16. Tổng kết

\`@ManagedAttribute\` giúp Spring Framework công bố **JavaBean properties** thành JMX attributes. Một getter được công bố tạo khả năng đọc; setter được công bố tạo khả năng ghi nếu metadata/hợp đồng cho phép. Attribute phản ánh trạng thái hoặc cấu hình runtime, còn hành động có chủ đích nên được mô hình hóa bằng \`@ManagedOperation\`.

Muốn khai báo có hiệu lực, bean cần được export thông qua hạ tầng Spring JMX thích hợp. Sau khi export, dùng \`MBeanInfo\` để xác minh tên, kiểu và quyền read/write. Với writable property, luôn kiểm soát validation, thread-safety, quyền truy cập, tác động thực tế và cách bảo toàn giá trị qua restart.