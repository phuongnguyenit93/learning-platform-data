# Bean prototype, singleton và tính phù hợp để quản trị qua Spring JMX

## 1. Mục tiêu

Khi đưa một Spring bean ra JMX bằng \`@ManagedResource\` và \`MBeanExporter\`, cần hiểu rõ **vòng đời Spring bean** và **vòng đời MBean đã đăng ký trong MBeanServer**. Hai vòng đời này có liên hệ nhưng không hoàn toàn trùng nhau.

Câu hỏi trọng tâm: nên dùng **singleton** hay **prototype** khi một bean được quản trị qua JMX?

Câu trả lời thường gặp là: **singleton hoặc một management adapter singleton có vòng đời rõ ràng thích hợp hơn cho MBean quản trị ổn định**. Prototype có thể được dùng trong hệ thống, nhưng không nên giả định mỗi instance prototype tự động có một MBean hoặc JMX client có thể tìm đến đúng prototype được tạo ra ở bất kỳ thời điểm nào.

Spring JMX công bố một **đối tượng được đăng ký dưới ObjectName cụ thể**, còn Spring bean scope quyết định container tạo và quản lý các instance như thế nào. Cần xét cả hai yếu tố để tránh sai lệch trong trạng thái quan sát, xung đột ObjectName và rò rỉ tài nguyên.

## 2. Ôn lại singleton và prototype trong Spring

### Singleton scope

Trong một Spring \`ApplicationContext\`, bean có scope singleton mặc định được tạo tối đa một instance cho mỗi bean definition. Mọi lần tra cứu bean definition đó trong cùng context trả về instance được quản lý chung.

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class QueueMonitor {
    public int getQueueDepth() {
        return 42;
    }
}
\`\`\`

\`QueueMonitor\` không khai báo \`@Scope\`, nên mặc định là singleton. Nếu ứng dụng có một queue manager ở cấp application, một monitor chung thường phản ánh trạng thái dễ hiểu cho JMX client.

**Singleton không có nghĩa JVM-wide singleton.** Hai ApplicationContext khác nhau có thể sở hữu các instance singleton riêng; một context cũng có thể định nghĩa nhiều bean singleton cùng kiểu class. Nếu tất cả các instance này cùng export một ObjectName vào một MBeanServer, sẽ xảy ra xung đột tên.

### Prototype scope

Với prototype, Spring tạo một instance mới mỗi khi container được yêu cầu cung cấp bean:

\`\`\`java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class JobWorker {
    private final long createdAtNanos = System.nanoTime();

    public long getCreatedAtNanos() {
        return createdAtNanos;
    }
}
\`\`\`

Ví dụ:

\`\`\`java
JobWorker first = context.getBean(JobWorker.class);
JobWorker second = context.getBean(JobWorker.class);

System.out.println(first == second); // false
\`\`\`

Một điểm thường bị hiểu sai: **inject prototype vào singleton theo dependency injection thông thường chỉ giải quyết dependency một lần khi singleton được tạo**. Singleton sau đó giữ một reference tới một instance prototype đã được inject; nó không tự nhận instance mới ở mọi lần gọi method.

Muốn lấy prototype mới theo nhu cầu, có thể dùng \`ObjectProvider<JobWorker>\`, \`Provider<JobWorker>\` hoặc lookup method injection. Nhưng cơ chế này không làm những instance mới tự xuất hiện dưới các ObjectName JMX riêng biệt.

## 3. JMX quản trị MBean theo ObjectName chứ không theo bean scope

JMX registry có dạng:

\`\`\`text
MBeanServer
  |
  +-- com.example.jobs:type=QueueMonitor,name=Primary
  |       |
  |       +-- MBean instance hoặc adapter đang được đăng ký
  |
  +-- com.example.jobs:type=WorkerPool,name=Main
          |
          +-- MBean instance hoặc adapter đang được đăng ký
\`\`\`

Sau khi MBean được đăng ký, client sử dụng **ObjectName** để tìm nó. JMX không có khái niệm “lấy prototype mới” chỉ vì Spring bean có scope prototype.

Ví dụ một bean \`@ManagedResource\`:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {
    @ManagedAttribute
    public int getQueueDepth() {
        return 42;
    }
}
\`\`\`

Khi exporter đăng ký bean này, JMX client truy cập một MBean dưới ObjectName đã chọn. Việc exporter phát hiện hoặc lấy bean lúc nào phụ thuộc vào cấu hình exporter, bean definition và Spring context; không nên suy diễn rằng annotation làm đổi scope của bean.

\`\`\`text
Spring container                JMX registry
-------------------------       -----------------------------
singleton QueueMonitor --export-> ObjectName QueueMonitor
prototype JobWorker #1
prototype JobWorker #2          (không tự có ObjectName)
prototype JobWorker #3
\`\`\`

Spring quản lý việc tạo bean; \`MBeanExporter\` quản lý việc công bố MBean. Hai hệ thống có mối liên kết khi đăng ký nhưng không có quy tắc mặc định biến mọi prototype thành một management endpoint tự động.

## 4. Vì sao singleton phù hợp với MBean quản trị thông thường?

### 4.1. Danh tính ổn định

Một JMX client, dashboard hoặc script thường lưu ObjectName để đọc đi đọc lại:

\`\`\`text
com.example.jobs:type=QueueMonitor,name=Primary
\`\`\`

Nếu mỗi truy cập tương ứng một instance khác nhau, client có thể thấy thông tin không liên tục. Singleton hoặc adapter singleton duy trì một endpoint ổn định, còn implementation bên dưới có thể thay đổi mà không buộc client tìm ObjectName mới.

### 4.2. Trạng thái quan sát nhất quán

Các thuộc tính như \`ActiveWorkers\`, \`QueueDepth\`, \`FailedJobs\` thường là dữ liệu toàn hệ thống hoặc toàn component. Một monitor singleton tổng hợp từ service dùng chung tránh việc mỗi MBean tình cờ phản ánh một instance prototype cục bộ, dẫn tới số liệu khó hiểu.

### 4.3. Vòng đời rõ ràng

Exporter có thể đăng ký MBean khi context hoạt động và unregister khi exporter bị hủy. Một singleton do context quản lý thường có vòng đời sát với exporter, nên dễ dự đoán lúc nào ObjectName tồn tại.

### 4.4. Giảm xung đột ObjectName

ObjectName là duy nhất trong một MBeanServer ở một thời điểm. Nếu nhiều prototype cùng muốn đăng ký:

\`\`\`text
com.example.jobs:type=JobWorker,name=Current
\`\`\`

chỉ có thể có một MBean dưới tên đó, trừ khi có cơ chế thay thế hoặc bỏ qua đối tượng hiện hữu. \`RegistrationPolicy.REPLACE_EXISTING\` không phải giải pháp tự động phù hợp cho việc quản trị nhiều prototype: client có thể thấy một ObjectName bất ngờ chuyển sang instance khác.

### 4.5. Giới hạn chi phí quản lý

Mỗi MBean có thể phát sinh metadata, listener, tham chiếu tới object, vòng đời unregister và dữ liệu quan sát. Đăng ký một MBean cho hàng nghìn object ngắn hạn gây tăng kích thước registry, chi phí query và nguy cơ để lại tham chiếu tới object đã không còn hữu ích.

## 5. Ví dụ thiết kế ưu tiên: management adapter singleton

Giả sử ứng dụng có nhiều worker theo scope prototype, được cấp phát để chạy các job ngắn hạn. Thay vì export từng worker, tạo một **singleton management adapter** để giám sát service quản lý worker.

\`\`\`java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Giám sát và điều khiển nhóm worker"
)
public class WorkerPoolManagement {
    private final WorkerPoolService poolService;

    public WorkerPoolManagement(WorkerPoolService poolService) {
        this.poolService = poolService;
    }

    @ManagedAttribute(description = "Số worker đang hoạt động")
    public int getActiveWorkers() {
        return poolService.getActiveWorkerCount();
    }

    @ManagedAttribute(description = "Số job đang chờ")
    public long getPendingJobs() {
        return poolService.getPendingJobCount();
    }

    @ManagedOperation(description = "Yêu cầu refresh cấu hình worker")
    public void requestRefresh() {
        poolService.requestConfigurationRefresh();
    }
}
\`\`\`

\`WorkerPoolService\` ở đây là service nghiệp vụ do ứng dụng cung cấp, có các method đã minh họa; mục đích là thể hiện cách adapter delegate. WorkerPoolManagement dùng singleton scope mặc định, còn các worker nội bộ có thể là prototype, được tạo và giải phóng theo nhu cầu.

Cấu hình export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Kết quả là một điểm quản trị ổn định:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main
  Attributes:
    ActiveWorkers
    PendingJobs
  Operation:
    requestRefresh()
\`\`\`

Client không cần biết pool hiện có bao nhiêu prototype hay chúng được tạo bởi \`ObjectProvider\`, factory, scheduler hay thread pool.

## 6. Prototype không nhất thiết bị cấm export

Có những trường hợp cần quản trị **một instance cụ thể** thay vì một nhóm, chẳng hạn:

- Một session xử lý tồn tại đủ lâu và có nhu cầu thao tác riêng.
- Một connector động có trạng thái riêng, được đăng ký/hủy đăng ký có kiểm soát.
- Một resource tạo lúc runtime, có ID duy nhất và lifecycle do ứng dụng quản lý.

Trong các trường hợp này, phải giải quyết rõ:

1. Ai tạo instance?
2. Ai quyết định instance nào được export?
3. ObjectName nào duy nhất, ổn định cho toàn thời gian tồn tại instance?
4. Khi instance kết thúc, ai unregister MBean?
5. JMX client xử lý ra sao khi MBean biến mất giữa hai lời gọi?
6. Registry có giới hạn tổng số MBean không?
7. MBean có giữ reference làm ngăn garbage collection không?

Đừng hiểu \`@Scope("prototype")\` + \`@ManagedResource\` là công thức “mỗi lần getBean sẽ có thêm một MBean”. Để quản lý dynamic instance thực sự, cần một thành phần sở hữu đăng ký động và cleanup.

## 7. Đăng ký MBean động cho một resource riêng biệt

Khi cần export một resource động, JMX chuẩn cho phép đăng ký theo ObjectName khác nhau. Ví dụ sau dùng một Standard MBean rõ ràng.

**Giao diện quản trị:**

\`\`\`java
package com.example.management;

public interface WorkerViewMBean {
    String getState();
    long getCompletedTasks();
}
\`\`\`

**Implementation:**

\`\`\`java
package com.example.management;

public class WorkerView implements WorkerViewMBean {
    private final WorkerSnapshotProvider provider;

    public WorkerView(WorkerSnapshotProvider provider) {
        this.provider = provider;
    }

    @Override
    public String getState() {
        return provider.state();
    }

    @Override
    public long getCompletedTasks() {
        return provider.completedTasks();
    }
}
\`\`\`

\`WorkerSnapshotProvider\` là interface/service của ứng dụng, có method trả dữ liệu cho đúng một worker. Đăng ký động có thể thực hiện qua \`MBeanServer\`:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerMBeanRegistration {
    private final MBeanServer server;

    public WorkerMBeanRegistration(MBeanServer server) {
        this.server = server;
    }

    public ObjectName register(
            String workerId, WorkerViewMBean mbean) throws Exception {
        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,id=" +
            ObjectName.quote(workerId)
        );
        server.registerMBean(mbean, name);
        return name;
    }

    public void unregister(ObjectName name) throws Exception {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Với Standard MBean, implementation phải đúng quy ước \`WorkerView\` / \`WorkerViewMBean\`; type của tham số \`mbean\` ở runtime phải là instance thích hợp. Khi bọc một implementation bất kỳ, có thể sử dụng \`StandardMBean\` để xác định management interface rõ ràng.

Nên ghi nhận ObjectName đã đăng ký và chỉ hủy đăng ký **MBean mà thành phần này thực sự sở hữu**, tránh race khi tên được dùng lại. \`isRegistered\` trước \`unregisterMBean\` chỉ là kiểm tra tại một thời điểm, không loại bỏ race condition. Một registry/tracker được đồng bộ theo ID và cleanup trong \`finally\` hoặc lifecycle callback sẽ phù hợp hơn trong code thật.

Mỗi MBean instance động có thể mang \`id\` riêng; tuy vậy ID nên là giá trị kỹ thuật an toàn, không chứa secrets hoặc dữ liệu cá nhân.

## 8. Prototype, dependency injection và tính nhất quán dữ liệu

Một management bean singleton có thể phụ thuộc một prototype:

\`\`\`java
@Component
public class WorkerManagement {
    private final JobWorker worker;

    public WorkerManagement(JobWorker worker) {
        this.worker = worker;
    }
}
\`\`\`

Nếu \`JobWorker\` là prototype, Spring inject **một instance tại thời điểm tạo \`WorkerManagement\`**. Sau đó MBean singleton sẽ đọc đúng instance ấy, không đại diện cho các worker khác.

Nếu muốn lấy worker prototype mới mỗi lần:

\`\`\`java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

@Component
public class WorkerFactoryClient {
    private final ObjectProvider<JobWorker> workerProvider;

    public WorkerFactoryClient(ObjectProvider<JobWorker> workerProvider) {
        this.workerProvider = workerProvider;
    }

    public void runWork() {
        JobWorker worker = workerProvider.getObject();
        // Sử dụng worker mới và quản lý tài nguyên nếu cần.
    }
}
\`\`\`

Nhưng management attribute không nên dùng \`workerProvider.getObject()\` chỉ để đọc “trạng thái hiện tại” vì mỗi lần polling lại tạo một instance mới, số liệu không có ý nghĩa. Thay vào đó đọc từ \`WorkerRegistry\`, \`WorkerPoolService\` hoặc snapshot aggregator nắm thông tin toàn nhóm.

### Ví dụ anti-pattern

\`\`\`java
@ManagedAttribute
public String getWorkerState() {
    return workerProvider.getObject().getState();
}
\`\`\`

Mỗi lần JConsole đọc attribute có thể tạo một worker mới, và nếu worker có constructor tốn tài nguyên hoặc mở kết nối, việc monitoring tự gây tác động lên ứng dụng. Cách đúng thường là đọc state từ đối tượng đang được quản lý thực sự hoặc aggregate.

## 9. Scope không quyết định thread safety

Singleton dùng chung giữa nhiều thread; JMX client cũng có thể gọi attribute/operation đồng thời. Vì vậy singleton management bean cần thiết kế thread-safe, nhất là khi vừa đọc vừa thay đổi trạng thái.

Ví dụ counter:

\`\`\`java
private final java.util.concurrent.atomic.AtomicLong completed =
    new java.util.concurrent.atomic.AtomicLong();

@ManagedAttribute
public long getCompletedCount() {
    return completed.get();
}
\`\`\`

Hoặc nên delegate sang service cung cấp snapshot đồng bộ. Một vài điểm:

- Dùng \`volatile\`, atomic type hoặc lock khi state cần visibility/consistency.
- Không giữ lock trong thời gian gọi operation bên ngoài hoặc notification callback nếu có nguy cơ chặn hệ thống.
- Các getter phục vụ monitoring nên nhanh, không side effect và không làm việc nặng.
- Nếu trả nhiều metric có liên hệ, dùng snapshot nhất quán thay vì đọc nhiều biến không đồng bộ theo thứ tự tùy ý.
- Prototype không tự động thread-safe: cùng một instance prototype có thể được chia sẻ cho nhiều thread nếu ứng dụng giữ reference và dùng đồng thời.

**Bean scope và concurrency là hai trục khác nhau.** Singleton quyết định reuse instance, còn thread safety đến từ thiết kế state và cách truy cập.

## 10. Spring lifecycle: ai chịu trách nhiệm giải phóng?

### Singleton

Với singleton do Spring container tạo và sở hữu, Spring thường quản lý initialization và destruction callbacks khi context đóng. \`MBeanExporter\` có vòng đời liên kết với context để hủy đăng ký MBean mà nó đã export.

Điều đó khiến singleton phù hợp cho dashboard luôn kết nối tới ObjectName cố định trong thời gian ứng dụng chạy.

### Prototype

Spring khởi tạo và cấu hình prototype khi yêu cầu, nhưng **không tự quản lý toàn bộ vòng đời hủy của mọi prototype sau khi cấp instance** như với singleton. Ứng dụng nhận prototype thường chịu trách nhiệm cleanup resource và destruction callbacks khi instance không còn sử dụng.

Nếu prototype được export thành MBean, MBeanServer có thể giữ reference tới đối tượng hoặc adapter, khiến garbage collection không giải phóng instance theo kỳ vọng. Vì vậy việc unregister đúng lúc là thiết yếu. Đừng coi “prototype được Spring tạo” là bằng chứng Spring sẽ tự unregister mỗi instance đó khi nghiệp vụ kết thúc.

Đối với resource ngắn hạn, một monitor singleton tổng hợp thường hiệu quả hơn. Nếu thực sự cần MBean per-resource, tạo lifecycle manager sở hữu cả resource và việc đăng ký/hủy đăng ký.

## 11. Trùng ObjectName giữa nhiều context hoặc instance

Ví dụ hai Spring context cùng export:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main
\`\`\`

vào cùng platform MBeanServer. Vì ObjectName phải duy nhất trong một server, exporter thứ hai có thể gặp \`InstanceAlreadyExistsException\` hoặc xử lý theo \`RegistrationPolicy\`.

Các lựa chọn chính:

- \`FAIL_ON_EXISTING\`: báo lỗi khi trùng; phù hợp để phát hiện cấu hình bất ngờ.
- \`IGNORE_EXISTING\`: bỏ qua MBean mới nếu đã có cùng tên.
- \`REPLACE_EXISTING\`: thay MBean cũ; cần cực kỳ hiểu rõ ownership và cleanup.

Không nên dùng \`REPLACE_EXISTING\` để luân phiên expose nhiều prototype cùng tên. Dashboard sẽ không có định danh ổn định cho từng instance, và việc shutdown context có thể làm phát sinh vấn đề ownership.

Nếu thật sự có nhiều instance quản trị riêng trong cùng MBeanServer, thêm key định danh:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main,instance=alpha
com.example.jobs:type=WorkerPool,name=Main,instance=beta
\`\`\`

Nếu mỗi instance chạy ở JVM/MBeanServer khác nhau, chúng có thể dùng cùng ObjectName; client phân biệt theo kết nối server. Không nhất thiết thêm instance key chỉ vì ứng dụng chạy nhiều JVM, trừ khi tổ chức monitoring yêu cầu.

## 12. Lựa chọn thiết kế cho từng tình huống

| Tình huống | Scope nghiệp vụ | Management endpoint khuyến nghị | Lý do |
| --- | --- | --- | --- |
| Trạng thái connection pool của ứng dụng | Singleton/pool | Singleton monitor | Định danh và dữ liệu toàn pool ổn định |
| Worker tạo theo từng job | Prototype/short-lived | Singleton aggregator | Tránh một MBean cho mỗi job |
| Một scheduler toàn ứng dụng | Singleton | Singleton MBean hoặc adapter | Thao tác và số liệu nhất quán |
| Nhiều resource dài hạn độc lập | Dynamic instances | MBean riêng có ObjectName duy nhất và lifecycle manager | Cần quan sát/điều khiển từng resource |
| Request-scoped object | Request | Aggregate metrics ở singleton | Không có một request instance ổn định để quản trị qua JMX |
| Một Spring bean singleton giữ prototype injected | Singleton + prototype | Quan sát đúng dependency đã inject hoặc aggregate | Prototype không tự refresh sau mỗi JMX call |
| Nhiều ApplicationContext cùng JVM | Nhiều singleton | Naming policy và exporter ownership rõ ràng | Tránh trùng MBean |

Cách chọn dựa trên **đơn vị quản trị mà client cần nhìn thấy**, không chỉ scope được khai báo trên class.

## 13. Chi phí, bảo mật và hiệu ứng phụ

Khi export MBean từ bean có scope bất kỳ, cần xác định:

**Exposure:** Chỉ công bố \`@ManagedAttribute\` và \`@ManagedOperation\` thật sự phục vụ vận hành. Một prototype dùng nội bộ có thể chứa data cá nhân hoặc trạng thái nghiệp vụ nhạy cảm; không vì tiện debug mà expose mọi field.

**Operation effects:** Nếu một MBean quản trị có \`reset()\` hoặc \`stop()\`, cần biết đối tượng nào nhận lệnh và hậu quả của việc gọi lặp. Một proxy thay đổi target bất ngờ có thể khiến operation tác động sai resource.

**Performance:** JConsole hoặc hệ thống monitoring có thể polling thường xuyên. Getter không được tạo prototype tốn tài nguyên, query dữ liệu lớn hoặc giữ lock lâu chỉ để trả trạng thái.

**Registry growth:** Mỗi MBean per-instance làm tăng quy mô registry và metadata. Với resource ngắn hạn, việc thường xuyên register/unregister có thể gây overhead và race với client đang query.

**Security:** Annotation \`@ManagedResource\` không tự cấu hình quyền remote JMX connector. Bảo vệ network, xác thực/phân quyền và validation các operation có tác động như với những MBean khác.

## 14. Mô hình tư duy cần nhớ

\`\`\`text
Spring Scope
  |
  +-- Singleton: một bean instance / bean definition / ApplicationContext
  |      |
  |      +--> phù hợp MBean ổn định, ObjectName cố định
  |
  +-- Prototype: tạo mới khi container được yêu cầu
         |
         +--> không tự động có một MBean cho mỗi instance
         |
         +--> nếu cần per-instance MBean:
                  lifecycle manager + ObjectName duy nhất
                  + unregister khi resource kết thúc

JMX side:
  MBeanServer
     |
     +-- ObjectName -> một MBean đang đăng ký
     +-- ObjectName -> một MBean đang đăng ký
\`\`\`

**Kết luận:** Đối với Spring Framework JMX, singleton hoặc một singleton management adapter là lựa chọn thường phù hợp để cung cấp endpoint quản trị ổn định, có số liệu nhất quán và lifecycle rõ ràng. Prototype phục vụ việc tạo instance theo nhu cầu; nó không tự mang ý nghĩa “mỗi instance là một MBean”. Khi cần quản trị từng instance động, hãy thiết kế đăng ký, naming, ownership, cleanup và giới hạn quy mô một cách chủ động.
