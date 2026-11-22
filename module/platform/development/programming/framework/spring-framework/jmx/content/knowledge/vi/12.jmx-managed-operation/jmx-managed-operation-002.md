# Description và metadata cho operation với @ManagedOperation trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích operation là gì trong JMX và phân biệt operation với attribute.
- Sử dụng \`@ManagedOperation\` để công bố một phương thức Java như một operation quản trị có chủ đích.
- Viết **description** rõ ràng cho operation, mô tả đúng tác dụng và rủi ro khi người vận hành gọi nó.
- Sử dụng \`@ManagedOperationParameter\` và \`@ManagedOperationParameters\` để gắn tên và mô tả cho các tham số.
- Hiểu metadata mà JMX cung cấp qua \`MBeanOperationInfo\`, \`MBeanParameterInfo\`, \`MBeanInfo\` và \`Descriptor\`.
- Xác minh metadata thực tế trên \`MBeanServer\`, thay vì chỉ suy luận từ annotation trong source code.
- Phân biệt các thiết lập \`impact\`, \`currencyTimeLimit\` và các thuộc tính descriptor có phụ thuộc Model MBean với kiểm soát nghiệp vụ và quyền truy cập.
- Thiết kế hợp đồng operation có tên, tham số, kiểu trả về, cách xử lý lỗi và mô tả đủ rõ cho JConsole và client JMX.

## 2. Operation trong mô hình JMX

Một MBean có thể công bố **attributes** để đọc hoặc ghi trạng thái và **operations** để thực hiện hành động quản trị. Ví dụ:

\`\`\`text
ObjectName:
  com.example.orders:type=ImportJob,name=Daily

Attributes:
  Running          Boolean  read-only
  ProcessedCount   Long     read-only

Operations:
  requestPause()                  void
  retryFailedTasks(int maxTasks)  int
\`\`\`

Ở góc nhìn JMX client, operation gồm **tên**, **danh sách tham số**, **kiểu trả về**, **mức tác động (impact)** và **mô tả (description)**. Những thông tin này xuất hiện trong \`MBeanOperationInfo\`.

Trong Spring Framework, \`@ManagedOperation\` là metadata để Spring JMX exporter xác định phương thức nào cần công bố. Để annotation được áp dụng, ứng dụng phải sử dụng exporter/assembler hiểu metadata annotation, chẳng hạn \`MBeanExporter\` với \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\`.

Không phải mọi phương thức \`public\` của Spring bean đều được xuất qua JMX nếu bạn sử dụng cấu hình metadata chọn lọc đúng cách.

## 3. Vì sao description quan trọng?

Description là phần mô tả giúp người vận hành biết operation **làm gì** trước khi gọi. Điều này quan trọng vì không ít operation JMX có tác dụng phụ thực tế:

- Làm mới cache khiến hệ thống truy cập nguồn dữ liệu.
- Tạm dừng một consumer khiến thông điệp tồn đọng.
- Kích hoạt retry tạo thêm tải lên downstream.
- Reset statistics có thể làm mất số liệu tính từ lần reset trước.
- Reload configuration có thể thay đổi cách ứng dụng vận hành.

Ví dụ mô tả còn mơ hồ:

\`\`\`java
@ManagedOperation(description = "Refresh")
public void refresh() { /* ... */ }
\`\`\`

Mô tả có ngữ nghĩa hơn:

\`\`\`java
@ManagedOperation(
    description = "Reload the product cache from the current database snapshot"
)
public void refreshProductCache() {
    // Chỉ minh họa: ứng dụng triển khai hành động thật.
}
\`\`\`

Một description tốt giúp client hiểu hành động, nhưng **không phải cơ chế cấp quyền hoặc xác nhận an toàn**. Nếu operation nguy hiểm được công bố, người có quyền gọi JMX vẫn có thể thực thi nó; phần mô tả không ngăn được lời gọi.

### 3.1. Nội dung nên có trong description

Tùy mức độ quan trọng, description nên cho biết:

1. **Hành động:** operation thay đổi cái gì?
2. **Phạm vi:** cache nào, worker nào, tài nguyên nào?
3. **Tác dụng phụ:** có reset bộ đếm, gây tải, tạm dừng tác vụ không?
4. **Điều kiện:** chỉ hợp lệ khi nào? Có idempotent không?
5. **Kết quả:** giá trị trả về hoặc trạng thái nào xác nhận hành động?
6. **Độ trễ:** gọi đồng bộ hay chỉ gửi yêu cầu bất đồng bộ?

Ví dụ:

\`\`\`java
@ManagedOperation(
    description = "Request graceful pause of the import worker; " +
                  "returns before in-flight tasks finish"
)
public void requestPause() {
    // ...
}
\`\`\`

Chuỗi mô tả có thể dài hơn một câu nhưng nên vẫn ngắn gọn, rõ để hiển thị trong công cụ quản trị. Nếu có yêu cầu vận hành phức tạp, nên lưu quy trình chi tiết trong tài liệu riêng và chỉ đưa mô tả ngắn tới JMX metadata.

## 4. @ManagedOperation: khai báo cơ bản

Annotation nằm trong package:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

Ví dụ với bean quản trị:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class ImportWorkerAdmin {

    @ManagedOperation(
        description = "Request a graceful stop of the import worker"
    )
    public void requestStop() {
        // Chuyển yêu cầu tới service thực tế.
    }
}
\`\`\`

Trong cấu hình exporter dùng annotation-based metadata, \`requestStop\` sẽ được mô tả là một operation. Thông thường \`getMBeanInfo\` cho biết:

\`\`\`text
operation.name        = requestStop
operation.description = Request a graceful stop of the import worker
operation.signature   = []
operation.returnType  = void
\`\`\`

Việc gọi \`requestStop\` qua JMX có thể kích hoạt logic ứng dụng. Vì thế chỉ xuất operation với hành vi được xác định trước; tránh đưa method tùy ý như \`executeCommand(String)\` hoặc \`deleteEverything()\` ra bề mặt quản trị.

## 5. Description thuộc metadata nào?

JMX chuẩn định nghĩa \`MBeanOperationInfo\` với các thông tin chính:

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| Tên operation | \`getName()\` | Tên dùng để client gọi operation. |
| Description | \`getDescription()\` | Nội dung mô tả vận hành. |
| Kiểu trả về | \`getReturnType()\` | Tên kiểu Java mà JMX công bố. |
| Tham số | \`getSignature()\` | Mảng \`MBeanParameterInfo\` theo thứ tự tham số. |
| Impact | \`getImpact()\` | Phân loại hành động theo JMX metadata. |
| Descriptor | \`getDescriptor()\` | Các field metadata bổ sung khi được cung cấp. |

Client có thể dùng các thông tin này để tạo giao diện. Ví dụ, JConsole có thể hiển thị operation với vùng nhập tham số và nút gọi; custom client có thể kiểm tra signature để truyền đúng kiểu.

Description không đổi logic của Java method. Nó giúp người đọc và công cụ hiểu ý nghĩa quản trị.

## 6. Metadata cho tham số operation

Chỉ công bố description của operation đôi khi không đủ. Với một operation nhiều tham số, client cần biết mỗi tham số biểu diễn điều gì.

Ví dụ phương thức:

\`\`\`java
public int retryFailedTasks(int maxTasks, boolean dryRun) { /* ... */ }
\`\`\`

Nếu tên tham số Java bị loại khỏi bytecode hoặc introspection không giữ đủ metadata, JMX client có thể chỉ thấy kiểu hoặc tên chung chung. Spring cung cấp \`@ManagedOperationParameter\` để mô tả từng tham số.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(
    description = "Retry up to maxTasks failed items; dryRun counts without retrying"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "maxTasks",
        description = "Maximum number of failed items to examine"
    ),
    @ManagedOperationParameter(
        name = "dryRun",
        description = "When true, return candidate count without retry"
    )
})
public int retryFailedTasks(int maxTasks, boolean dryRun) {
    return 0; // Triển khai thật gọi service có kiểm soát.
}
\`\`\`

Với metadata assembler hỗ trợ annotations, \`MBeanOperationInfo.getSignature()\` sẽ cung cấp metadata cho hai tham số theo thứ tự:

\`\`\`text
Parameter 0:
    name = maxTasks
    type = int
    description = Maximum number of failed items to examine

Parameter 1:
    name = dryRun
    type = boolean
    description = When true, return candidate count without retry
\`\`\`

**Quan trọng:** annotation mô tả tham số không tự áp đặt validation như \`maxTasks > 0\`. Code nghiệp vụ vẫn phải kiểm tra giới hạn và từ chối giá trị không hợp lệ.

## 7. Quy ước viết description cho parameter

Mỗi parameter description nên:

- Xác định ý nghĩa nghiệp vụ, không chỉ lặp lại tên.
- Nêu đơn vị: giây, milliseconds, bytes, số phần tử.
- Nêu phạm vi hợp lệ nếu có, ví dụ \`1..100\`.
- Nêu hiệu ứng của giá trị đặc biệt như \`0\` hoặc \`-1\`.
- Làm rõ trường hợp \`null\` hoặc chuỗi rỗng.
- Tránh mô tả mơ hồ như “parameter”, “value”, “the argument”.

Ví dụ tốt:

\`\`\`java
@ManagedOperationParameter(
    name = "timeoutMillis",
    description = "Maximum time to wait in milliseconds (100..10000)"
)
\`\`\`

Nhưng mô tả \`100..10000\` chỉ là hợp đồng tài liệu. Implementation phải thực thi:

\`\`\`java
if (timeoutMillis < 100 || timeoutMillis > 10_000) {
    throw new IllegalArgumentException(
        "timeoutMillis must be between 100 and 10000"
    );
}
\`\`\`

Khi thay đổi validation, cần cập nhật description tương ứng để tránh công cụ vận hành dùng giá trị không còn hợp lệ.

## 8. Metadata impact: ACTION, INFO và ACTION_INFO

JMX \`MBeanOperationInfo\` có các giá trị impact phổ biến:

| Impact | Ý nghĩa mô tả | Ví dụ |
| --- | --- | --- |
| \`INFO\` | Operation nhằm cung cấp thông tin. | Tính snapshot hoặc đọc trạng thái. |
| \`ACTION\` | Operation thực hiện hành động. | Reset counters, request pause. |
| \`ACTION_INFO\` | Operation vừa thực hiện hành động vừa trả thông tin. | Start retry và trả số task đã nhận. |
| \`UNKNOWN\` | Không xác định rõ phân loại. | Operation chưa có metadata thích hợp. |

Trường impact giúp mô tả tính chất của operation cho client. **Nó không phải authorization rule**: một operation được đánh dấu \`INFO\` vẫn có thể chứa side effect nếu implementation viết sai; một operation \`ACTION\` không tự động bị chặn với role chỉ đọc nếu cơ chế authorization không kiểm tra phù hợp.

Trong Spring JMX, metadata annotation và assembler xác định impact được công bố. Khi cần kiểm soát hoặc đánh giá impact thực tế, đọc \`MBeanOperationInfo.getImpact()\` từ MBeanServer đang chạy.

### 8.1. Ví dụ metadata tác động

Giả sử:

\`\`\`java
public int retryFailedTasks(int maxTasks, boolean dryRun);
\`\`\`

Một operation này có thể trả số lượng task xử lý (thông tin) và đồng thời kích hoạt retry (hành động), nên về ngữ nghĩa phù hợp với \`ACTION_INFO\`. Tuy nhiên không nên giả định Spring tự suy ra điều đó từ kiểu trả về hoặc tên method. Cần kiểm tra runtime metadata và dùng assembler/metadata strategy phù hợp nếu dự án yêu cầu phân loại chính xác.

## 9. currencyTimeLimit và descriptor cho operation

Spring JMX hỗ trợ một số metadata có nguồn gốc từ JMX Model MBean descriptors. Trong mô hình đó, \`currencyTimeLimit\` có thể liên quan tới chính sách cache giá trị trả về của operation trong những tình huống cụ thể.

Cần phân biệt ba thứ:

1. **Description:** mô tả operation.
2. **Descriptor field:** metadata bổ sung, có thể được Model MBean implementation diễn giải.
3. **Business behavior:** code của operation thực thi và kiểm soát side effect.

Nếu thấy \`currencyTimeLimit\` trong metadata operation, không nên hiểu nó là timeout cho lời gọi, SLA hoặc một scheduler. Nó thuộc ngữ cảnh Model MBean caching, nếu implementation hỗ trợ và áp dụng.

Ví dụ cấu trúc descriptor:

\`\`\`text
name              = calculateStatus
descriptorType    = operation
currencyTimeLimit = 5
\`\`\`

Trường này có thể chỉ dẫn Model MBean dùng kết quả đã cache theo semantics của implementation. Với operation có side effect, việc cache kết quả có thể thay đổi số lần logic thực tế được gọi. Vì vậy không nên tùy tiện thiết lập cache trên operation thay đổi trạng thái.

Nếu cần timeout thực, hãy triển khai timeout trong code service, connector hoặc tác vụ bất đồng bộ theo kiến trúc cụ thể; đừng dùng \`currencyTimeLimit\` như công cụ ngắt lời gọi.

## 10. Cách Spring tạo metadata operation

Một đường xử lý thường gặp:

\`\`\`text
Spring bean
  @ManagedResource
  @ManagedOperation
  @ManagedOperationParameters
             |
             v
AnnotationJmxAttributeSource
             |
             v
MetadataMBeanInfoAssembler
             |
             v
ModelMBeanInfo / MBeanOperationInfo
             |
             v
MBeanExporter
             |
             v
MBeanServer
             |
             v
JConsole / JMX client
\`\`\`

\`AnnotationJmxAttributeSource\` đọc annotation trên class và methods. \`MetadataMBeanInfoAssembler\` chuyển metadata thành \`MBeanInfo\` và descriptors phù hợp để exporter cung cấp tới MBeanServer.

Nếu ứng dụng dùng \`InterfaceBasedMBeanInfoAssembler\` hoặc một strategy khác, metadata annotation có thể không được áp dụng theo cách mong đợi. Luôn kiểm tra cấu hình assembler thực tế.

### 10.1. Ví dụ cấu hình tường minh

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanExporter mBeanExporter(ImportJobAdmin admin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("importJobAdmin", admin));

        return exporter;
    }
}
\`\`\`

Đây là mẫu Spring Framework thuần, chỉ nhằm làm rõ con đường metadata. Trong Spring Boot, có thể có auto-configuration JMX đã tồn tại; cần tránh exporter trùng đăng ký cùng \`ObjectName\`.

### 10.2. Ví dụ bean được công bố

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=ImportJob,name=Daily",
    description = "Import job management"
)
public class ImportJobAdmin {

    @ManagedOperation(
        description = "Request a graceful pause; in-flight items continue"
    )
    public void requestPause() {
        // Gọi service yêu cầu pause.
    }

    @ManagedOperation(
        description = "Retry up to maxTasks failed tasks; returns accepted count"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxTasks",
            description = "Maximum tasks to retry (1..100)"
        )
    })
    public int retryFailedTasks(int maxTasks) {
        if (maxTasks < 1 || maxTasks > 100) {
            throw new IllegalArgumentException(
                "maxTasks must be between 1 and 100"
            );
        }
        return 0; // Kết quả placeholder minh họa.
    }

    // Method public nhưng không có annotation operation:
    public void internalRebuildAllIndexes() {
        // Không công bố qua assembler dựa trên annotation.
    }
}
\`\`\`

Mẫu này giữ một bề mặt quản trị nhỏ. Không đưa method khôi phục toàn bộ dữ liệu hoặc thực thi lệnh tùy ý ra JMX nếu không có nhu cầu vận hành và kiểm soát quyền rõ ràng.

## 11. Ví dụ gọi operation qua MBeanServer

Giả sử bean đã được exporter đăng ký thành công:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

// Operation không có tham số:
server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

// Operation nhận int:
Object result = server.invoke(
    name,
    "retryFailedTasks",
    new Object[] { 10 },
    new String[] { "int" }
);

System.out.println("Accepted count: " + result);
\`\`\`

Signature \`new String[] { "int" }\` sử dụng tên kiểu primitive \`int\` tương ứng với khai báo Java method. Với kiểu reference, dùng tên class Java tương ứng. JMX dùng signature để xác định operation phù hợp, nhất là khi có overload.

Cần đảm bảo operation được đăng ký trên platform MBeanServer đang truy cập. Nếu exporter dùng MBeanServer khác, phải lấy đúng server tương ứng.

## 12. Đọc metadata thực tế

Không nên kết luận rằng annotation đã được áp dụng chỉ vì code biên dịch. Dùng JMX API để kiểm tra:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s%nDescription: %s%n" +
        "Return type: %s%nImpact: %d%n",
        operation.getName(),
        operation.getDescription(),
        operation.getReturnType(),
        operation.getImpact()
    );

    for (MBeanParameterInfo parameter
            : operation.getSignature()) {
        System.out.printf(
            "  Parameter: %s (%s) - %s%n",
            parameter.getName(),
            parameter.getType(),
            parameter.getDescription()
        );
    }
}
\`\`\`

Kết quả mong đợi ở mức ý nghĩa:

\`\`\`text
Operation: requestPause
Description: Request a graceful pause; in-flight items continue
Return type: void

Operation: retryFailedTasks
Description: Retry up to maxTasks failed tasks; returns accepted count
Return type: int
  Parameter: maxTasks (int) - Maximum tasks to retry (1..100)
\`\`\`

Con số \`Impact\` tương ứng với hằng số của \`MBeanOperationInfo\`; client có thể chuyển thành tên \`INFO\`, \`ACTION\`, \`ACTION_INFO\` hoặc \`UNKNOWN\`.

### 12.1. Đọc descriptor của operation

\`\`\`java
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " => "
            + operation.getDescriptor()
    );
}
\`\`\`

Descriptor có thể chứa các field như \`name\`, \`descriptorType\`, \`role\`, \`currencyTimeLimit\` hoặc metadata khác tùy Model MBean implementation. Field nào không có thì không nên tự giả định giá trị đã được áp dụng.

### 12.2. Metadata là hợp đồng runtime

Khi thiết kế một client tự động, có thể kiểm tra metadata trước khi invoke:

\`\`\`java
boolean available = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("retryFailedTasks".equals(operation.getName())
            && operation.getSignature().length == 1
            && "int".equals(
                operation.getSignature()[0].getType())) {
        available = true;
    }
}

if (!available) {
    throw new IllegalStateException(
        "Expected JMX operation is not available"
    );
}
\`\`\`

Điều này giúp phát hiện tên/signature đã đổi giữa các phiên bản. Tuy nhiên vẫn cần xử lý trường hợp MBean bị hủy đăng ký sau khi kiểm tra (time-of-check/time-of-use).

## 13. Operation metadata và JConsole

Trong JConsole, vào **MBeans → domain → MBean → Operations**. Với MBean công bố operation, bạn thường có thể xem:

- Tên operation.
- Tham số mà người dùng cần nhập.
- Kiểu trả về.
- Mô tả operation và tham số, tùy cách JConsole hiển thị metadata.
- Nút thực thi operation.

Không nên giả định mọi phiên bản JConsole hoặc mọi JMX client hiển thị tất cả descriptor field. Description/metadata vẫn có thể đọc qua JMX API ngay cả khi GUI rút gọn.

**Nhấn nút invoke là thao tác thật.** Với operation có side effect, xác nhận đúng JVM, đúng môi trường và đúng MBean trước khi gọi. Một operation \`requestPause\` có thể làm dừng xử lý nghiệp vụ, không chỉ thay đổi giao diện.

### 13.1. Vì sao mô tả tốt giúp vận hành?

Hai operation:

\`\`\`text
reset()
reload()
\`\`\`

không đủ để người dùng hiểu hệ quả. Nếu metadata ghi:

\`\`\`text
reset()  - Reset request counters to zero; no business data is changed
reload() - Reload validated runtime configuration; active requests are unaffected
\`\`\`

người vận hành có thể phân biệt tác dụng. Nhưng mô tả phải khớp implementation. Không viết “active requests are unaffected” nếu code có thể hủy request đang chạy.

## 14. Phân biệt operation và attribute

Trong Spring JMX, getter như \`getStatus()\` thường phù hợp với \`@ManagedAttribute\`; lệnh như \`restart()\` phù hợp với \`@ManagedOperation\`.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedAttribute(description = "Current worker status")
public String getStatus() {
    return "RUNNING";
}

@ManagedOperation(
    description = "Request the worker to restart gracefully"
)
public void requestRestart() {
    // ...
}
\`\`\`

Một method chỉ đọc vẫn có thể được xuất như operation nếu có nhu cầu tính toán hoặc nhận tham số, nhưng cần lý do rõ ràng. Đối với số liệu được polling thường xuyên, getter attribute đơn giản dễ tích hợp với nhiều công cụ quản trị hơn.

Không dùng operation chỉ để phơi bày Java API rộng hơn cần thiết; JMX là bề mặt vận hành, không phải cơ chế tự động xuất toàn bộ service methods.

## 15. Validation, lỗi và semantics của operation

Metadata mô tả input nhưng **không tự validate tất cả ràng buộc nghiệp vụ**. Ví dụ \`retryFailedTasks(1000000)\` có thể gây tải lớn nếu implementation không kiểm tra.

Cần xử lý:

1. **Range validation:** giới hạn số lượng, thời gian và kích thước chuỗi.
2. **State validation:** operation chỉ hợp lệ trong những trạng thái nào.
3. **Concurrency:** hai người quản trị gọi đồng thời có gây xung đột không.
4. **Idempotency:** nếu client retry do timeout, operation có chạy lặp gây hậu quả không.
5. **Error reporting:** exception hoặc mã trạng thái cho phép chẩn đoán mà không lộ dữ liệu nhạy cảm.
6. **Authorization:** ai được gọi operation, bằng cơ chế bảo mật JMX/connector và lớp ứng dụng khi cần.
7. **Observability:** ghi nhận thời điểm và kết quả của thao tác có tác động lớn.

Một pattern thường an toàn hơn là **request-style operation**:

\`\`\`java
@ManagedOperation(
    description = "Request a cache rebuild; returns a request ID"
)
public String requestCacheRebuild() {
    // Gửi yêu cầu đến executor/queue nội bộ.
    return "request-example";
}
\`\`\`

Như vậy lời gọi không nhất thiết chặn JConsole cho đến khi rebuild hoàn tất. Tuy nhiên cần cung cấp đường xem trạng thái yêu cầu và cơ chế xử lý lặp theo định danh thật khi triển khai.

## 16. Tránh nhầm description với authorization

Description là tài liệu, không ngăn người dùng bấm invoke. Cũng vậy:

- **Impact** chỉ là metadata phân loại.
- **Parameter description** không tự chặn input sai.
- **CurrencyTimeLimit** không phải timeout bảo mật.
- **ObjectName** không phải quyền truy cập.
- **Ẩn operation khỏi tài liệu** không có nghĩa method không thể bị gọi nếu implementation dynamic vẫn xử lý nó.

Hãy kiểm soát an toàn bằng thiết kế bề mặt MBean tối thiểu, validation, quyền connector, xác thực/TLS và kiểm soát hành động có tác dụng phụ.

Một client chỉ đọc nên có chính sách không cho phép gọi operation thay đổi trạng thái nếu hệ thống hỗ trợ phân quyền như vậy. Nếu cần mức quyền chi tiết theo operation, phải sử dụng cơ chế authorization phù hợp, không chỉ dựa trên một chuỗi description.

## 17. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Operation không xuất hiện | Chưa export bean, annotation không được assembler đọc, sai ObjectName. | Kiểm tra \`MBeanExporter\`, assembler, \`getMBeanInfo\`. |
| Description không hiển thị | Client GUI rút gọn metadata hoặc assembler không chuyển annotation. | Đọc \`getDescription()\` qua JMX API. |
| Parameter chỉ có tên chung | Chưa khai báo metadata parameter hoặc annotation không áp dụng. | Dùng \`@ManagedOperationParameters\`, xác minh \`getSignature()\`. |
| Gọi operation báo signature sai | Tên kiểu hoặc thứ tự tham số không khớp. | Đọc signature của \`MBeanOperationInfo\`. |
| Gọi được nhưng kết quả sai | Logic service chưa đúng, không kiểm tra input/trạng thái. | Sửa validation và business logic, không chỉ description. |
| Operation gây tải lớn | Không giới hạn tham số, chạy đồng bộ lâu. | Thêm giới hạn, điều phối bất đồng bộ và trạng thái tiến độ. |
| Tên operation trùng | Có overload và client chọn sai signature. | Công bố signature rõ ràng, cân nhắc tên quản trị dễ phân biệt. |
| Impact không phù hợp | Metadata mặc định hoặc cấu hình assembler. | Kiểm tra JMX runtime, điều chỉnh strategy nếu cần. |
| Thay mô tả nhưng JConsole vẫn cũ | MBean chưa đăng ký lại hoặc kết nối chưa refresh. | Kiểm tra lifecycle MBean và reconnect/refresh client. |

## 18. Hướng dẫn thiết kế API quản trị có thể duy trì

Ví dụ một hợp đồng:

\`\`\`text
MBean:
  com.example.orders:type=Scheduler,name=Reconciliation

Attributes:
  State                String  read-only
  LastRunEpochMillis   Long    read-only

Operations:
  requestRunOnce()
    description: Queue one reconciliation run; returns immediately.
    returnType: String requestId

  cancelPendingRun(String requestId)
    description: Cancel a queued run if it has not started.
    parameter:
      requestId: ID returned by requestRunOnce
    returnType: boolean
\`\`\`

Các nguyên tắc:

- **Tên ổn định:** tránh đổi tên/signature liên tục vì custom client có thể phụ thuộc vào chúng.
- **Description chính xác:** nêu rõ hành vi đồng bộ/bất đồng bộ và giá trị trả về.
- **Tham số tối thiểu:** không chấp nhận path, SQL, shell command hoặc tùy chọn nguy hiểm nếu không cần.
- **Kiểu đơn giản:** ưu tiên kiểu JMX dễ nhập và quan sát; cân nhắc MXBean/OpenType cho dữ liệu phức tạp.
- **Side effect có kiểm soát:** validation, giới hạn tải và trạng thái thao tác.
- **Không rò dữ liệu:** description, parameter name, exception và return value đều là nội dung có thể thấy bởi client.

## 19. Bài tập thực hành

### Bài tập 1 — Operation đơn giản

Tạo bean \`@ManagedResource\` có \`@ManagedOperation(description = "Reset request counters")\` trên method \`resetCounters()\`. Export bean rồi đọc description qua \`MBeanServer.getMBeanInfo\`.

**Mục tiêu:** hiểu cách description đi từ annotation tới metadata runtime.

### Bài tập 2 — Metadata tham số

Tạo operation \`reconfigurePool(int minSize, int maxSize)\`. Dùng \`@ManagedOperationParameters\` để mô tả hai tham số, đơn vị và giới hạn hợp lệ. Đọc \`getSignature()\` để kiểm tra tên, type, description.

**Mục tiêu:** biết quản lý metadata tham số thay vì phụ thuộc vào tên biến Java.

### Bài tập 3 — Signature và invoke

Đăng ký \`retryFailedTasks(int maxTasks)\`, dùng MBeanServer.invoke với signature \`"int"\`. Thử signature \`"java.lang.Integer"\` rồi quan sát hành vi với JMX exporter đang dùng.

**Mục tiêu:** hiểu tham số signature được định danh bằng kiểu theo metadata JMX.

### Bài tập 4 — Operation có tác dụng phụ

Thiết kế operation \`clearCache()\` với description nêu rõ ảnh hưởng lên cache và tải database sau khi clear. Thêm authorization và validation theo kiến trúc ứng dụng.

**Mục tiêu:** hiểu metadata tốt giúp vận hành nhưng không thay thế cơ chế bảo vệ.

### Bài tập 5 — So sánh các assembler

Trong lab, xuất cùng bean bằng annotation-based assembler và một strategy khác phù hợp. So sánh \`MBeanInfo\`: operation nào xuất hiện, description nào được giữ, tham số nào có metadata.

**Mục tiêu:** thấy rằng annotation chỉ có hiệu lực khi exporter/assembler dùng đúng cách.

### Bài tập 6 — Client tự kiểm tra metadata

Viết Java client đọc operation list, tìm \`retryFailedTasks\` có một tham số \`int\`, rồi mới invoke. Nếu operation thiếu hoặc signature khác, báo lỗi rõ.

**Mục tiêu:** tạo client quản trị ít phụ thuộc vào implementation hơn.

## 20. Câu hỏi ôn tập

**1. \`@ManagedOperation\` dùng để làm gì?** Mô tả một phương thức được xuất làm JMX operation khi exporter/assembler phù hợp xử lý annotation.

**2. \`description\` có tác động gì?** Cung cấp tài liệu giúp client/người vận hành hiểu ý nghĩa operation; không tự thay đổi Java method.

**3. Metadata operation đọc ở đâu?** \`MBeanInfo.getOperations()\` và từng \`MBeanOperationInfo\`.

**4. Vì sao cần \`@ManagedOperationParameter\`?** Để cung cấp tên và mô tả tham số quản trị thay vì chỉ có kiểu hoặc tên chung chung.

**5. Impact có phải phân quyền không?** Không. Nó là metadata mô tả tính chất operation.

**6. Description có validate input không?** Không. Implementation phải kiểm tra dữ liệu đầu vào.

**7. Vì sao signature quan trọng?** Nó giúp client chọn operation chính xác, nhất là khi có overload hoặc kiểu tham số khác nhau.

**8. Spring Boot bật JMX có tự động làm tất cả method public thành operation?** Không. Những gì được công bố phụ thuộc exporter, assembler và cấu hình cụ thể.

**9. Tại sao không đặt currencyTimeLimit trên operation thay đổi trạng thái tùy tiện?** Vì cache kết quả có thể ảnh hưởng số lần method thực thi khi Model MBean diễn giải descriptor.

**10. Nên đưa gì vào description của operation rủi ro cao?** Hành động, phạm vi, điều kiện gọi, side effect, kết quả và các giới hạn quan trọng, đồng thời thực thi các kiểm soát thật trong code/quyền.

## 21. Tổng kết

**Operation metadata** là hợp đồng giúp JMX client khám phá, hiển thị và gọi các thao tác quản trị. Trong Spring Framework, \`@ManagedOperation\` mô tả operation và description; \`@ManagedOperationParameters\` cùng \`@ManagedOperationParameter\` giúp đặt tên và giải thích các tham số.

Metadata runtime được thể hiện qua \`MBeanOperationInfo\` và \`MBeanParameterInfo\`; cần kiểm tra trực tiếp từ MBeanServer để xác nhận exporter đã công bố đúng. Description, impact và descriptor giúp giải thích khả năng quản trị nhưng không thay thế validation, authorization hoặc thiết kế hành động an toàn.

## Tài liệu tham khảo

- Spring Framework Javadoc — \`ManagedOperation\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework Javadoc — \`ManagedOperationParameter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperationParameter.html
- Spring Framework Javadoc — \`ManagedOperationParameters\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperationParameters.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanParameterInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanParameterInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html