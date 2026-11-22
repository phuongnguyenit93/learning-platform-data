# Kiểu tham số, kiểu trả về và tương thích JMX

> **Chủ đề:** Spring Framework JMX
> **Nhóm kiến thức:** ManagedOperation
> **Bài học:** Kiểu tham số, kiểu trả về và tương thích JMX

## 1. Mục tiêu

Bài này giải thích hợp đồng kiểu dữ liệu của một operation được Spring xuất bản qua Java Management Extensions (JMX). Sau khi học, bạn có thể:

- Đọc chính xác tên method, danh sách kiểu tham số và kiểu trả về của một JMX operation.
- Hiểu cách `@ManagedOperation` và `@ManagedOperationParameters` tạo bề mặt quản trị trên Spring bean.
- Phân biệt primitive với wrapper, kiểu Java dùng trong ứng dụng và kiểu dữ liệu có thể truyền qua JMX connector.
- Gọi `MBeanServer.invoke` bằng `ObjectName`, danh sách giá trị và chữ ký tham số đúng.
- Thiết kế operation dùng kiểu đơn giản hoặc Open Types, hạn chế phụ thuộc vào DTO nội bộ.
- Phân biệt Standard MBean, Spring ModelMBean và MXBean, đặc biệt khi kết nối từ xa.

## 2. Từ phương thức Java đến hợp đồng JMX

Một phương thức Java có thể có bất kỳ tham số và kiểu trả về phù hợp với ngôn ngữ. Khi công bố qua JMX, method trở thành một hợp đồng mà client quản trị cần hiểu, có tên, kiểu tham số theo thứ tự và kiểu trả về.

```text
Spring bean
    |
    | @ManagedResource + @ManagedOperation
    v
Spring AnnotationMBeanExporter / ModelMBean
    |
    | Operation name + parameter signature + return type
    v
MBeanServer
    |
    | invoke(ObjectName, operation, params, signature)
    v
JConsole / client Java / remote monitoring agent
```

Ví dụ một Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=WorkerControl,name=main"
)
public class WorkerControl {

    private volatile int workerLimit = 4;

    @ManagedOperation(description = "Set worker limit")
    public void resizeWorkers(int workers) {
        if (workers < 1 || workers > 128) {
            throw new IllegalArgumentException("workers must be 1..128");
        }
        workerLimit = workers;
    }

    @ManagedOperation(description = "Get worker limit")
    public int currentWorkerLimit() {
        return workerLimit;
    }
}
```

Với ứng dụng bật cấu hình export, ví dụ `@EnableMBeanExport`, metadata JMX công bố hai operation:

```text
resizeWorkers(int) -> void
currentWorkerLimit() -> int
```

Client JMX không dựa vào việc suy đoán kiểu từ tên method; nó phải gửi chữ ký phù hợp với metadata đã công bố.

## 3. Chữ ký trong MBeanServer.invoke

Phương thức trung tâm là:

```java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
);
```

| Đối số | Ý nghĩa | Ví dụ |
|---|---|---|
| `name` | Định danh chính xác của MBean | `learning.jmx:type=WorkerControl,name=main` |
| `operationName` | Tên operation đã công bố | `resizeWorkers` |
| `params` | Giá trị đối số theo thứ tự | `new Object[] { 8 }` |
| `signature` | Tên kiểu tham số khai báo theo thứ tự | `new String[] { "int" }` |
| Kết quả | Giá trị trả về dưới dạng Object | null cho `void`, Integer cho `int` |

Cách gọi:

```java
ObjectName name = new ObjectName(
    "learning.jmx:type=WorkerControl,name=main"
);

server.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "int" }
);
```

Mảng `params` chứa **giá trị**, còn `signature` chứa **kiểu khai báo của method**. Chúng phải có cùng số phần tử và đúng thứ tự. Phần tử Java `8` được boxing thành `Integer` trong `Object[]`, nhưng signature vẫn phải là `int` vì method khai báo primitive `int`.

## 4. Primitive và wrapper là hai chữ ký khác nhau

Các kiểu primitive có tên như `int`, `long`, `boolean`, `double`. Wrapper là class như `java.lang.Integer`, `java.lang.Long`, `java.lang.Boolean`, `java.lang.Double`.

Giả sử có hai overload:

```java
public void setLimit(int value) { ... }

public void setLimit(Integer value) { ... }
```

Hai chữ ký khác nhau:

```text
setLimit(int)
setLimit(java.lang.Integer)
```

Cùng một object `Integer.valueOf(5)` có thể được dùng làm giá trị trong mảng `params`, nhưng `signature` chọn overload:

```java
server.invoke(
    name,
    "setLimit",
    new Object[] { Integer.valueOf(5) },
    new String[] { "int" }
);

server.invoke(
    name,
    "setLimit",
    new Object[] { Integer.valueOf(5) },
    new String[] { "java.lang.Integer" }
);
```

JMX không được coi là Java compiler có thể tự thử boxing, widening và overload resolution tùy ý. Nếu method nhận `long`, nên truyền `Long` và signature `long`. Nếu nhận `String`, signature là `java.lang.String`, không phải `String`.

Một số kiểu wrapper có thể nhận null, còn primitive không thể nhận null. Điều này ảnh hưởng validation và hành vi runtime.

## 5. Những kiểu phù hợp cho operation quản trị

| Kiểu | Ví dụ | Điểm cần lưu ý |
|---|---|---|
| `boolean` | `setEnabled(boolean)` | Đảm bảo chỉ cho phép thay đổi trạng thái đã được duyệt |
| `int` | `resize(int)` | Giới hạn giá trị và kiểm tra số âm |
| `long` | `setTimeoutMillis(long)` | Ghi rõ đơn vị để client không hiểu nhầm |
| `double` | `setThreshold(double)` | Kiểm tra NaN, infinity và khoảng giá trị |
| `String` | `refreshCache(String)` | Validate allowlist, độ dài và ký tự đầu vào |
| `Integer` hoặc `Boolean` | Tham số tùy chọn | Định nghĩa rõ ý nghĩa null |
| `String[]` | Danh sách tên | Client phải hỗ trợ xây dựng mảng đúng loại |
| `CompositeData` | Trạng thái có nhiều trường | Cần schema Open MBean rõ ràng |
| `TabularData` | Danh sách bản ghi | Cần type/index schema thống nhất |

Kiểu đơn giản thường tương thích với JConsole, script và client từ xa hơn. Tuy vậy, “dễ vận chuyển” không có nghĩa một operation tự động an toàn: `deleteEverything()` có chữ ký rỗng nhưng vẫn là thao tác nguy hiểm.

## 6. Không có tham số và nhiều tham số

Method không tham số:

```java
@ManagedOperation
public void resetCounters() {
    // Chỉ reset counters được phép.
}
```

Gọi với hai mảng rỗng:

```java
server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);
```

Không truyền `new Object[] { null }`, vì đó là **một** đối số null chứ không phải không có đối số.

Method ba tham số:

```java
@ManagedOperation
public String submit(
        String queue,
        int batchSize,
        boolean dryRun
) {
    return "accepted";
}
```

Client:

```java
Object result = server.invoke(
    name,
    "submit",
    new Object[] { "retry", 100, true },
    new String[] {
        "java.lang.String",
        "int",
        "boolean"
    }
);
```

Đổi thứ tự hai phần tử trong `signature` hoặc `params` có thể khiến server không tìm được operation hoặc không gọi được method. `params.length == signature.length` là điều kiện cần; từng kiểu và vị trí cũng phải đúng.

## 7. ManagedOperationParameters chỉ là metadata

Spring hỗ trợ mô tả tên và mục đích từng tham số:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Resize worker pool")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "workers",
        description = "Number of workers, from 1 to 128"
    )
})
public void resizeWorkers(int workers) {
    // ...
}
```

`@ManagedOperationParameters` không tự ép kiểu, không biến `int` thành `String` và không thay đổi thứ tự tham số. Nó hỗ trợ công cụ JMX hiển thị tên và mô tả. Nếu input không hợp lệ, method vẫn phải tự xác thực hoặc chuyển cho service chịu trách nhiệm xác thực.

## 8. Kiểu trả về

Đối với `void`, `MBeanServer.invoke` thường trả `null`. Với primitive, kết quả được boxing, ví dụ `int` trả về `Integer`. Với `String`, client thường nhận `String`.

```java
Object result = server.invoke(
    name,
    "currentWorkerLimit",
    new Object[0],
    new String[0]
);

Integer limit = (Integer) result;
```

Client chỉ ép kiểu khi hợp đồng MBean thực sự trả về kiểu đó. Có thể xác nhận qua `MBeanOperationInfo.getReturnType()`.

Operation có kiểu trả về `void` nhưng khởi chạy công việc bất đồng bộ không có nghĩa công việc đã hoàn thành:

```java
@ManagedOperation
public void requestRefresh() {
    executor.submit(this::refreshInternal);
}
```

Trong trường hợp này, thành công của lời gọi chỉ xác nhận phương thức yêu cầu hoàn tất việc submit. Thiết kế dễ giám sát hơn có thể trả về job ID:

```java
@ManagedOperation
public String requestRefresh(String cacheName) {
    return scheduleRefresh(cacheName);
}

@ManagedOperation
public String refreshStatus(String jobId) {
    return lookupRefreshStatus(jobId);
}
```

`scheduleRefresh` và `lookupRefreshStatus` là thành phần nghiệp vụ minh họa, cần triển khai thật khi sử dụng.

## 9. Đối tượng Java phức tạp

Một operation:

```java
@ManagedOperation
public JobResult submit(JobRequest request) {
    // ...
}
```

có thể hợp lệ theo Java nhưng khó dùng qua JMX vì:

- JConsole có thể không tạo được instance của `JobRequest` từ giao diện.
- Client Java bên ngoài phải biết class và phiên bản tương thích.
- Remote connector có thể cần serialization và classpath phù hợp.
- Đổi package, field hoặc cấu trúc DTO có thể làm client cũ lỗi.
- Dữ liệu trả về có thể làm lộ chi tiết nội bộ hoặc tạo payload lớn.

JMX không cấm mọi object tùy biến, nhưng một contract dùng class nội bộ khiến client phụ thuộc nhiều vào implementation.

Thay vì expose toàn bộ DTO, có thể cung cấp management facade:

```java
@ManagedOperation(
    description = "Submit a predefined job configuration"
)
public String submitPredefinedJob(String definitionId) {
    JobRequest request = lookupDefinition(definitionId);
    JobResult result = jobService.submit(request);
    return result.id();
}
```

Client chỉ cần `String` để chỉ định một cấu hình đã được allowlist và nhận job ID; còn `JobRequest`/`JobResult` vẫn thuộc tầng nghiệp vụ. Các method phụ trợ và class trong ví dụ là code ứng dụng giả định, không phải Spring API có sẵn.

## 10. Enum và array

Enum:

```java
enum Mode {
    NORMAL, MAINTENANCE
}

@ManagedOperation
public void setMode(Mode mode) {
    // ...
}
```

Chữ ký JMX của tham số là tên class enum đầy đủ, chẳng hạn `example.jmx.Mode`. Client remote phải có kiểu tương thích để xây dựng giá trị; JConsole có thể không nhập trực tiếp được.

Một lựa chọn dễ dùng là `String` có validation:

```java
@ManagedOperation
public void setMode(String rawMode) {
    Mode selected = Mode.valueOf(rawMode);
    // Kiểm tra quyền và thực thi chuyển đổi.
}
```

Với array, JMX metadata có thể dùng biểu diễn descriptor kiểu JVM như `[Ljava.lang.String;`, tùy loại operation và mô hình đăng ký. Đừng tự suy ra rằng `String[]` là chuỗi signature chính xác; đọc `MBeanParameterInfo.getType()`.

## 11. Standard MBean, ModelMBean và MXBean

**Standard MBean** dùng interface quản trị theo quy ước, ví dụ `CacheControlMBean`. Operation lấy từ các method trong interface.

**Spring annotation ModelMBean** dùng metadata từ `@ManagedResource`, `@ManagedOperation` và các annotation liên quan để mô tả management interface của bean. Annotation không tự chuyển tất cả DTO nghiệp vụ thành kiểu trung lập.

**MXBean** dùng các quy tắc ánh xạ giữa kiểu Java và JMX Open Types. Một số kiểu composite, collection hoặc map phù hợp có thể được biểu diễn bằng `CompositeData` hoặc `TabularData`, giúp giảm phụ thuộc vào class implementation ở client.

```text
Standard MBean:
  Java interface -> JMX operation

Spring ModelMBean:
  Annotation metadata -> JMX operation

MXBean:
  Java management interface -> MXBean type mapping
                             -> JMX Open Types
```

Không coi việc thêm `@ManagedOperation` là đã tạo MXBean. Khi muốn Open Type mapping, cần dùng mô hình MXBean hoặc Open MBean đúng hợp đồng.

## 12. CompositeData và TabularData

Open MBean cung cấp những biểu diễn dữ liệu có schema được mô tả công khai:

- `SimpleType`: các giá trị chuẩn như `String`, `Integer`, `Long` và `Boolean`.
- `ArrayType`: mảng có phần tử thuộc Open Type hợp lệ.
- `CompositeType` và `CompositeData`: bản ghi có các field định danh và kiểu cụ thể.
- `TabularType` và `TabularData`: tập bản ghi theo cấu trúc bảng, có khóa chỉ mục.

Ví dụ tạo một bản ghi trạng thái:

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

String[] keys = { "active", "maximum", "healthy" };

CompositeType type = new CompositeType(
    "WorkerStatus",
    "Worker pool status",
    keys,
    new String[] {
        "Active workers",
        "Maximum workers",
        "Healthy"
    },
    new OpenType<?>[] {
        SimpleType.INTEGER,
        SimpleType.INTEGER,
        SimpleType.BOOLEAN
    }
);

CompositeData data = new CompositeDataSupport(
    type,
    keys,
    new Object[] { 3, 16, true }
);
```

Để trả dữ liệu này từ một operation, phải expose method thích hợp qua MBean/MXBean. `CompositeData` giúp client đọc cấu trúc mà không cần class DTO nội bộ, nhưng schema vẫn phải được duy trì ổn định.

## 13. Đọc chữ ký thật bằng MBeanInfo

Dùng `MBeanServerConnection.getMBeanInfo` để xem management contract sau khi exporter đã đăng ký:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] parameters = op.getSignature();

    for (int i = 0; i < parameters.length; i++) {
        if (i > 0) System.out.print(", ");
        System.out.print(parameters[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
```

Ví dụ kết quả:

```text
resizeWorkers(int) -> void
currentWorkerLimit() -> int
```

Các tên kiểu trong metadata mới là cơ sở để client xây `signature`, đặc biệt khi có overload, array hoặc kiểu không đơn giản.

Khi có nhiều method cùng tên, phải so khớp toàn bộ tên và dãy kiểu; không chọn tùy tiện overload đầu tiên.

## 14. Kiểm tra operation theo metadata

Một client hoặc integration test có thể xác nhận hợp đồng trước khi invoke:

```java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

MBeanOperationInfo op = Arrays.stream(
    connection.getMBeanInfo(name).getOperations()
)
    .filter(candidate ->
        candidate.getName().equals("resizeWorkers"))
    .filter(candidate ->
        candidate.getSignature().length == 1)
    .filter(candidate ->
        "int".equals(candidate.getSignature()[0].getType()))
    .findFirst()
    .orElseThrow();

if (!"void".equals(op.getReturnType())) {
    throw new IllegalStateException("Unexpected return type");
}
```

Đây là đoạn minh họa dùng trong method có `connection` và `name` đã được khởi tạo. Có thể dùng `MBeanInfo` để kiểm tra hợp đồng khi phát hành, tránh vô tình đổi kiểu của operation được các client giám sát sử dụng.

## 15. Sai chữ ký và exception

Các lỗi liên quan thường gặp:

| Vấn đề | Biểu hiện | Cách xử lý |
|---|---|---|
| Sai ObjectName | `InstanceNotFoundException` | Kiểm tra đăng ký và MBeanServer kết nối |
| Sai tên/chữ ký | `ReflectionException` hoặc lỗi định tuyến | Đọc `MBeanInfo` và so khớp kiểu theo thứ tự |
| Method ném checked exception | `MBeanException` | Đọc exception gốc |
| Method ném runtime exception | `RuntimeMBeanException` | Kiểm tra validation và logic operation |
| Remote connector lỗi | `IOException`, lỗi RMI/serialization | Kiểm tra connection và kiểu dữ liệu |
| Sai kỳ vọng kiểu trả về | `ClassCastException` phía client | Đọc `getReturnType()` |
| Thiếu quyền | `SecurityException` | Kiểm tra cấu hình truy cập JMX |

Ví dụ chữ ký sai:

```java
// resizeWorkers(int) nhưng client gửi wrapper type.
connection.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "java.lang.Integer" }
);
```

Sửa thành `new String[] { "int" }`. Nếu `ReflectionException` xuất hiện, đây chỉ là một hướng điều tra; lỗi reflection có thể có nguyên nhân khác, cần đọc cause.

## 16. Khả năng tương thích với công cụ JMX

Trong JConsole, bạn có thể:

1. Mở tab MBeans và tìm đúng `ObjectName`.
2. Xem Operations để biết tên operation và các tham số.
3. Gọi method không tham số hoặc dùng những kiểu được UI hỗ trợ.
4. Kiểm tra kết quả hiển thị, sau đó đọc attribute liên quan.
5. Nếu method nhận DTO phức tạp, dùng client Java tương thích hoặc thiết kế lại management contract.

Một operation hợp lệ nhưng GUI không thể nhập tham số không nhất thiết là operation bị đăng ký sai. Tuy nhiên, nếu mục tiêu là vận hành từ JConsole, những kiểu khó nhập sẽ làm API quản trị kém hữu dụng.

Local và remote JMX đều định tuyến qua `ObjectName` và chữ ký operation. Với remote, truyền đối tượng có thể phát sinh thêm yêu cầu serialization và class compatibility. `@EnableMBeanExport` chỉ bật export MBean, không tự mở remote JMX connector.

## 17. Thiết kế operation ổn định

Khi viết `@ManagedOperation`, ưu tiên:

- Tên method diễn đạt hành động cụ thể, chẳng hạn `resizeWorkers`, `refreshCache`.
- Đơn vị rõ ràng: `setTimeoutMillis(long)` tốt hơn một tên mơ hồ như `setTimeout(long)`.
- Input nhỏ, kiểu thông dụng và được kiểm tra giới hạn.
- Giá trị trả về dễ diễn giải, không chứa secret hoặc toàn bộ object graph.
- Không phụ thuộc vào class nội bộ nếu client vận hành độc lập.
- Không overload phức tạp nếu client chính là GUI.
- Không dùng exception message làm kênh tiết lộ cấu hình nhạy cảm.
- Với tác vụ dài, trả job ID và cung cấp trạng thái thay vì giữ lời gọi chờ không giới hạn.

Ví dụ:

```java
@ManagedOperation(description = "Set timeout in milliseconds")
public void setTimeoutMillis(long value) {
    if (value < 100L || value > 60_000L) {
        throw new IllegalArgumentException(
            "timeout must be 100..60000 ms"
        );
    }
    // Áp dụng cấu hình thực tế.
}
```

Khi có kết nối remote, xác thực, phân quyền, TLS và network restrictions cần được cấu hình ở tầng kết nối quản trị; annotation không cung cấp sẵn chính sách đó.

## 18. Bài tập thực hành

Một service có API:

```java
JobResult submit(JobRequest request);
void resize(int workers);
Map<String, JobStatus> listJobs();
```

Hãy thiết kế JMX facade sao cho operator không cần class `JobRequest`, `JobResult` hoặc `JobStatus`.

Gợi ý:

```java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=SchedulerControl,name=main"
)
public class SchedulerControl {

    private final SchedulerService service;

    public SchedulerControl(SchedulerService service) {
        this.service = service;
    }

    @ManagedOperation
    public void resizeWorkers(int workers) {
        if (workers < 1 || workers > 64) {
            throw new IllegalArgumentException("workers must be 1..64");
        }
        service.resize(workers);
    }

    @ManagedOperation
    public String submitPredefinedJob(String definitionId) {
        JobRequest request = lookupDefinition(definitionId);
        JobResult result = service.submit(request);
        return result.id();
    }
}
```

Các class `SchedulerService`, `JobRequest`, `JobResult` và helper `lookupDefinition` là thành phần giả định của ứng dụng. Trong hệ thống thật, facade nên dùng allowlist cho `definitionId`, kiểm tra quyền, giới hạn tác dụng phụ và ghi nhận thao tác quản trị cần audit.

Một client JMX gọi:

```java
connection.invoke(
    name,
    "resizeWorkers",
    new Object[] { 12 },
    new String[] { "int" }
);
```

Operation này dễ kiểm thử và không buộc client có dependency tới DTO nghiệp vụ.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `@ManagedOperation` trên method Java không bảo đảm JConsole nhập được mọi tham số?
2. Vì sao `int` và `java.lang.Integer` là hai chữ ký JMX khác nhau?
3. `@ManagedOperationParameters` thay đổi kiểu tham số hay chỉ mô tả metadata?
4. Tại sao `MBeanInfo` cần được đọc trước khi xây một client JMX tổng quát?
5. Kiểu trả về `void` có ý nghĩa gì với một operation khởi chạy job bất đồng bộ?
6. Những rủi ro nào xuất hiện khi expose `JobRequest` và `JobResult` trực tiếp?
7. MXBean khác Spring ModelMBean ở điểm nào về ánh xạ kiểu?
8. Khi nào dùng `CompositeData` và `TabularData`?
9. Thay `resize(int)` bằng `resize(long)` có thể ảnh hưởng client cũ như thế nào?
10. Vì sao kiểu dữ liệu đơn giản vẫn cần validation và phân quyền?

## 20. Ghi nhớ

```text
@ManagedOperation
     |
     v
MBeanOperationInfo
  - name
  - parameter types
  - return type
     |
     v
MBeanServer.invoke(
  ObjectName,
  operationName,
  Object[] values,
  String[] declaredTypes
)
     |
     v
Method được gọi và kết quả trả về
```

**Nguyên tắc cốt lõi:** `@ManagedOperation` quyết định method nào được công bố. `MBeanInfo` cho biết kiểu và chữ ký thực sự. Client phải dùng đúng chữ ký, còn khả năng vận chuyển dữ liệu và khả năng nhập liệu của công cụ quyết định mức độ tương thích. Giữ hợp đồng JMX nhỏ, ổn định và ưu tiên kiểu đơn giản hoặc Open Types khi cần.