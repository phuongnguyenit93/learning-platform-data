# java.lang.management và mô hình Platform MXBean

## 1. Từ câu hỏi giám sát đến giao diện của JVM

Khi một ứng dụng Java chạy chậm hoặc dùng nhiều bộ nhớ, ta cần biết JVM đã chạy bao lâu, heap đang dùng bao nhiêu, số luồng có tăng liên tục không và bộ thu gom rác đang hoạt động thế nào. Đọc log nghiệp vụ không đủ trả lời mọi câu hỏi đó.

`java.lang.management` cung cấp các giao diện quản lý, giám sát JVM và những thành phần liên quan của môi trường chạy. Đây là API của Java SE, dùng được trong chương trình Java thông thường, không bắt buộc Spring Boot hay thư viện giám sát bên ngoài. API hỗ trợ cả truy cập trong JVM hiện tại và truy cập thông qua cơ sở hạ tầng JMX. [Tổng quan java.lang.management](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html).

Hãy hình dung JVM cung cấp các “bảng đồng hồ” chuẩn hóa. Mỗi bảng đồng hồ được biểu diễn bằng một giao diện, chẳng hạn `MemoryMXBean` cho hệ thống bộ nhớ. Ứng dụng hỏi giao diện đó để lấy thông tin, thay vì phụ thuộc vào lớp triển khai nội bộ của một JVM cụ thể.

Bài này tập trung vào mô hình và cách truy cập Platform MXBean; việc phân tích heap, luồng hay GC chuyên sâu là bước tiếp theo sau khi hiểu nguồn và ý nghĩa dữ liệu.

## 2. JMX, MBean và Platform MXBean liên hệ thế nào?

**JMX** (Java Management Extensions) là cơ sở hạ tầng để các thành phần công bố giao diện quản lý. **MBean** (managed bean) là đối tượng được quản lý thông qua giao diện đó. MBean có thể công bố thuộc tính, thao tác và thông báo; không nên hiểu mọi MBean chỉ là tập số liệu chỉ đọc.

**MXBean** bổ sung quy tắc ánh xạ kiểu Java sang các kiểu dữ liệu mở của JMX (open types). Nhờ đó, máy khách quản lý có thể đọc dữ liệu mà không cần mang theo mọi lớp mô hình riêng của bên cung cấp. MXBean vẫn có thể có thuộc tính ghi hoặc thao tác quản lý. [Đặc tả MXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html).

**Platform MXBean** là các MXBean của nền tảng Java, đại diện cho thành phần JVM hoặc môi trường chạy. Giao diện của chúng được nền tảng triển khai; ứng dụng lấy đối tượng có sẵn để sử dụng. Không tự `new MemoryMXBean()` hoặc tự triển khai một giao diện nền tảng để thay thế thông tin JVM. `PlatformManagedObject` là giao diện chung cung cấp `getObjectName()`; nó được thiết kế cho các giao diện quản lý nền tảng, không phải giao diện ứng dụng tự mở rộng. [PlatformManagedObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/PlatformManagedObject.html).

```text
Thành phần bên trong JVM
    -> triển khai giao diện Platform MXBean
        -> ứng dụng gọi trực tiếp qua giao diện Java
        -> hoặc đăng ký trong Platform MBeanServer
             -> đọc bằng ObjectName và tên thuộc tính
             -> hoặc dùng proxy có kiểu
```

Không phải mọi MXBean đều là Platform MXBean. Ứng dụng có thể tự công bố MXBean nghiệp vụ riêng, nhưng các bean đó có vòng đời và trách nhiệm do ứng dụng quản lý. Cũng không phải mọi đối tượng có tên kết thúc bằng “Bean” đều là MBean JMX.

## 3. ManagementFactory là điểm truy cập

`ManagementFactory` cung cấp các phương thức tĩnh để lấy Platform MXBean. Có phương thức lấy một đối tượng và có phương thức lấy danh sách. Cardinality — số đối tượng ứng với một giao diện — phụ thuộc loại thành phần:

| Nhóm | Giao diện thường dùng | Điểm truy cập |
| --- | --- | --- |
| Môi trường chạy | `RuntimeMXBean` | `getRuntimeMXBean()` |
| Bộ nhớ tổng thể | `MemoryMXBean` | `getMemoryMXBean()` |
| Luồng | `ThreadMXBean` | `getThreadMXBean()` |
| Nạp lớp | `ClassLoadingMXBean` | `getClassLoadingMXBean()` |
| Hệ điều hành | `OperatingSystemMXBean` | `getOperatingSystemMXBean()` |
| Biên dịch JIT nếu có | `CompilationMXBean` | `getCompilationMXBean()` |
| Các vùng bộ nhớ | `MemoryPoolMXBean` | `getMemoryPoolMXBeans()` |
| Các bộ thu gom rác | `GarbageCollectorMXBean` | `getGarbageCollectorMXBeans()` |
| Các bộ quản lý bộ nhớ | `MemoryManagerMXBean` | `getMemoryManagerMXBeans()` |

Các nhóm Runtime, Memory, Threading, ClassLoading và OperatingSystem có một đối tượng cho mỗi JVM. Compilation có thể không có nếu JVM không có hệ thống biên dịch; các nhóm pool, collector và memory manager có nhiều đối tượng. Không giả định “một JVM chỉ có một MXBean” hoặc “mỗi giao diện luôn trả đúng một bean”. [ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

Ngoài các phương thức chuyên biệt, có thể dùng `getPlatformMXBean(Class)` cho giao diện có nhiều nhất một đối tượng, hoặc `getPlatformMXBeans(Class)` cho danh sách. Cách lấy phải phù hợp mô hình của giao diện; đừng lấy một phần tử đầu tiên rồi coi nó là toàn bộ hệ thống.

## 4. ObjectName và Platform MBeanServer

`ObjectName` là định danh JMX của một bean trong một MBeanServer. Ví dụ:

| Bean | ObjectName chuẩn |
| --- | --- |
| Runtime | `java.lang:type=Runtime` |
| Bộ nhớ | `java.lang:type=Memory` |
| Luồng | `java.lang:type=Threading` |
| Nạp lớp | `java.lang:type=ClassLoading` |
| Hệ điều hành | `java.lang:type=OperatingSystem` |

Với các nhóm nhiều đối tượng, tên thường có thêm thuộc tính `name`, chẳng hạn mẫu `java.lang:type=MemoryPool,name=...`. Tên pool hoặc collector cụ thể phụ thuộc JVM và cấu hình. Lấy `bean.getObjectName()` giúp tránh tự ghép sai tên hoặc xử lý ký tự đặc biệt bằng tay. [PlatformManagedObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/PlatformManagedObject.html), [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

`ManagementFactory.getPlatformMBeanServer()` trả Platform MBeanServer dùng chung trong JVM. Lần gọi đầu tạo server này và đăng ký các Platform MXBean. Nó không đồng nghĩa với việc tự mở một cổng quản trị từ xa. Một MBeanServer tự tạo khác cũng không mặc nhiên có toàn bộ bean nền tảng. [Tổng quan java.lang.management](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html).

Khi đọc gián tiếp, tên thuộc tính không phải tên phương thức Java. `runtime.getUptime()` tương ứng thuộc tính `Uptime`; `memory.getHeapMemoryUsage()` tương ứng `HeapMemoryUsage`. Viết đúng chữ hoa/thường. Có thể dùng `getMBeanInfo()` để khám phá giao diện được công bố thay vì đoán tên. [MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html).

## 5. Ba cách truy cập cùng nguồn dữ liệu

### Gọi trực tiếp trong JVM

```java
RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
long uptimeMillis = runtime.getUptime();
```

Đây là đoạn minh họa cần import tương ứng. Đối tượng lấy từ factory thuộc JVM đang thực thi đoạn mã. Nó không giám sát một tiến trình Java khác chỉ vì tiến trình đó cũng ở cùng máy. `getUptime()` có đơn vị mili giây. [RuntimeMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html).

### Đọc thông qua MBeanServer

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
Object uptime = server.getAttribute(
        runtime.getObjectName(), "Uptime");
```

Cách này hữu ích khi công cụ cần khám phá nhiều loại bean bằng tên và metadata. Kết quả có kiểu Java tổng quát `Object`; giá trị nguyên thủy được đóng hộp, kiểu phức hợp được ánh xạ theo MXBean. Lỗi sai tên bean hoặc thuộc tính được báo qua ngoại lệ JMX; không biến lỗi đọc thành số 0 vì sẽ làm sai tín hiệu giám sát. [MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html).

### Dùng proxy có kiểu

```java
RuntimeMXBean proxy = ManagementFactory.getPlatformMXBean(
        server, RuntimeMXBean.class);
long uptimeMillis = proxy.getUptime();
```

Proxy chuyển lời gọi qua một `MBeanServerConnection`, nhưng vẫn cho mã Java sử dụng giao diện `RuntimeMXBean`. Kết nối có thể là cục bộ hoặc từ xa. Proxy không tạo JVM mới và không tự thiết lập kết nối mạng; phải có kết nối hợp lệ trước. Khi kết nối tới JVM khác, dữ liệu thuộc JVM đích. [ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

## 6. Vì sao MemoryUsage trở thành CompositeData?

Khi gọi trực tiếp:

```java
MemoryUsage usage = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage();
long usedBytes = usage.getUsed();
```

Bạn làm việc với lớp `MemoryUsage`. Nhưng khi đọc thuộc tính `HeapMemoryUsage` bằng `MBeanServer.getAttribute()`, kết quả là `CompositeData`, chứa các trường `init`, `used`, `committed`, `max`. Có thể gọi `MemoryUsage.from(compositeData)` để dựng lại đối tượng tương ứng. [MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

Đây là cơ chế ánh xạ kiểu, không phải hai phép đo khác nhau về bản chất. `CompositeData` cho phép công cụ JMX đọc cấu trúc dữ liệu bằng các kiểu mở; proxy có kiểu có thể thực hiện phần chuyển đổi cho người gọi. Không ép trực tiếp giá trị lấy từ MBeanServer thành `MemoryUsage`. [Đặc tả MXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html).

Các lần gọi riêng diễn ra tại những thời điểm khác nhau. Heap có thể thay đổi giữa lần đọc trực tiếp và lần đọc qua server, nên không kiểm tra sự đúng đắn bằng cách bắt hai số `used` phải bằng nhau. Một đối tượng `MemoryUsage` là một ảnh chụp các giá trị liên quan; nhiều lời gọi bean khác nhau không tạo thành giao dịch chụp toàn bộ JVM.

## 7. Chương trình Java chạy hoàn chỉnh

Ví dụ dùng Java 17+ và các API chuẩn, không yêu cầu bật quản trị từ xa. Nó đọc trực tiếp, đọc gián tiếp và đọc qua proxy trong **cùng JVM**.

Lưu thành `PlatformMxBeanDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.RuntimeMXBean;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public class PlatformMxBeanDemo {
    public static void main(String[] args) throws Exception {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage directUsage = memory.getHeapMemoryUsage();

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName runtimeName = runtime.getObjectName();
        ObjectName memoryName = memory.getObjectName();

        Object uptime = server.getAttribute(runtimeName, "Uptime");
        Object heapAttribute =
                server.getAttribute(memoryName, "HeapMemoryUsage");
        CompositeData heapData = (CompositeData) heapAttribute;
        MemoryUsage mappedUsage = MemoryUsage.from(heapData);

        RuntimeMXBean proxy = ManagementFactory.getPlatformMXBean(
                server, RuntimeMXBean.class);

        System.out.println("Runtime ObjectName=" + runtimeName);
        System.out.println("Memory ObjectName=" + memoryName);
        System.out.println("Runtime registered=" +
                server.isRegistered(runtimeName));
        System.out.println("Uptime attribute type=" +
                uptime.getClass().getName());
        System.out.println("HeapMemoryUsage uses CompositeData=" +
                (heapAttribute instanceof CompositeData));
        System.out.println("Heap used is nonnegative=" +
                (directUsage.getUsed() >= 0 && mappedUsage.getUsed() >= 0));
        System.out.println("Proxy uptime is nonnegative=" +
                (proxy.getUptime() >= 0));
    }
}
```

Biên dịch và chạy:

```shell
javac PlatformMxBeanDemo.java
java PlatformMxBeanDemo
```

Stdout:

```text
Runtime ObjectName=java.lang:type=Runtime
Memory ObjectName=java.lang:type=Memory
Runtime registered=true
Uptime attribute type=java.lang.Long
HeapMemoryUsage uses CompositeData=true
Heap used is nonnegative=true
Proxy uptime is nonnegative=true
```

Các dòng kiểm tra kiểu và miền giá trị giúp kết quả dễ đối chiếu mà không bịa số heap hoặc uptime cố định. Chương trình vẫn đọc số liệu thật của JVM; nó không in trực tiếp các giá trị thường thay đổi đó.

Để quan sát số liệu, có thể thêm dòng sau vào `main` sau khi có `directUsage`:

```java
System.out.println("Heap used bytes=" + directUsage.getUsed());
```

Số in ra phụ thuộc JVM, cấu hình bộ nhớ và thời điểm chạy. Nó không phải dung lượng bộ nhớ của toàn bộ tiến trình.

Với một ứng dụng dùng hệ thống module Java, thêm phụ thuộc tương ứng trong `module-info.java`:

```java
module monitoring.demo {
    requires java.management;
}
```

Các package `java.lang.management`, `javax.management` và `javax.management.openmbean` đều thuộc module `java.management`. Chạy ví dụ theo classpath như trên không cần tạo `module-info.java`. [Module java.management](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html).

## 8. Đọc số liệu theo đúng hợp đồng API

### Bộ nhớ là ảnh chụp theo phạm vi

`MemoryUsage` dùng đơn vị byte. `used` là phần đang dùng; `committed` là dung lượng đã được bảo đảm sẵn cho JVM sử dụng; `max` là giới hạn nếu xác định được. `init` hoặc `max` có thể bằng `-1` khi không xác định. Không tính phần trăm `used / max` trước khi kiểm tra mẫu số hợp lệ. [MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

Heap và non-heap là hai phạm vi được `MemoryMXBean` công bố. Không cộng chúng rồi gọi kết quả là toàn bộ bộ nhớ tiến trình: JVM còn có những vùng cấp phát và tài nguyên bản địa khác. Một lần thấy heap tăng không đủ chứng minh rò rỉ; cần theo dõi xu hướng trong bối cảnh tải và hoạt động thu gom. [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).

### Bộ đếm tích lũy khác giá trị tức thời

Số lần GC và thời gian GC là số tích lũy của từng collector. Muốn đánh giá một khoảng quan sát, lấy chênh lệch hai mẫu cùng collector, kiểm tra JVM có khởi động lại hay không và loại giá trị không xác định. `getCollectionCount()` hoặc `getCollectionTime()` có thể trả `-1`; thời gian thu gom là số gần đúng theo mili giây, không mặc nhiên là tổng thời gian dừng ứng dụng. [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).

### Có giao diện không có nghĩa mọi phép đo đều hỗ trợ

`CompilationMXBean` có thể không tồn tại. Nếu tồn tại, cần kiểm tra `isCompilationTimeMonitoringSupported()` trước khi đọc tổng thời gian biên dịch. Không dùng thời gian biên dịch tích lũy như điểm hiệu năng để so sánh các JVM. [CompilationMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/CompilationMXBean.html).

Một số phép đo của `ThreadMXBean` cũng cần kiểm tra hỗ trợ và trạng thái bật. Đo thời gian CPU theo luồng hoặc thu thập thông tin tranh chấp có thể có chi phí; không tự bật mọi tùy chọn trong một đường xử lý chỉ cần đọc số liệu cơ bản. Trên Java 21+, `ThreadMXBean` giám sát **luồng nền tảng (platform thread)**, không cung cấp bức tranh đầy đủ về **luồng ảo (virtual thread)**. Không diễn giải số luồng của bean này là tổng mọi tác vụ ảo. [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

`OperatingSystemMXBean` chuẩn cung cấp thông tin như tên hệ điều hành, kiến trúc, số bộ xử lý sẵn cho JVM và tải trung bình hệ thống nếu có. Tải trung bình không phải phần trăm CPU; giá trị âm báo không có dữ liệu. Các phép đo CPU/bộ nhớ mở rộng phụ thuộc giao diện triển khai, không tự giả định mọi JVM đều có cùng phần mở rộng. [OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html).

## 9. Giám sát khác thao tác quản trị

Platform MXBean không chỉ có getter. Ví dụ, `MemoryMXBean` có thao tác yêu cầu GC; các pool có thể có thao tác đặt ngưỡng hoặc đặt lại giá trị đỉnh. Việc một thao tác tồn tại không có nghĩa cần gọi nó trong mỗi lần thu thập số liệu. [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html), [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

Một tác vụ lấy mẫu thông thường nên đọc những gì cần thiết ở nhịp hợp lý, lưu thời điểm và danh tính JVM, xử lý lỗi rõ ràng. Đừng vô tình gọi GC hay đặt lại đỉnh bộ nhớ rồi làm thay đổi hệ thống mà mình đang quan sát.

Truy cập trong tiến trình không bắt buộc bật cổng JMX từ xa. Nếu triển khai truy cập từ xa, phần kết nối, xác thực, mã hóa và phân quyền phải được cấu hình riêng; việc tạo proxy không tự đáp ứng các yêu cầu đó. Không công bố endpoint quản trị chỉ để chạy ví dụ cục bộ này.

## 10. Lỗi thường gặp và cách tự kiểm tra

| Lỗi | Cách sửa |
| --- | --- |
| Import lớp triển khai nội bộ của JVM | Dùng giao diện chuẩn qua `ManagementFactory` |
| Gọi `getAttribute(name, "getUptime")` | Dùng tên thuộc tính `Uptime` |
| Ép `HeapMemoryUsage` thành `MemoryUsage` trực tiếp | Nhận `CompositeData` rồi chuyển đổi, hoặc dùng proxy có kiểu |
| Ghi cứng tên pool/collector | Lấy danh sách và `getObjectName()` của bean thực tế |
| Biến dữ liệu không xác định thành số 0 | Giữ trạng thái không có dữ liệu, xử lý theo hợp đồng API |
| Đòi hai mẫu heap liên tiếp phải giống nhau | Nhận biết thời điểm đo khác nhau |
| Gọi factory cục bộ để đo JVM khác | Tạo kết nối JMX tới JVM đích rồi dùng proxy hoặc đọc gián tiếp |

Tự trả lời ba câu hỏi:

1. **Tại sao cùng thuộc tính heap nhưng một đường trả `MemoryUsage`, đường kia trả `CompositeData`?** Do ánh xạ kiểu MXBean khi đi qua giao diện JMX tổng quát.
2. **Gọi `getPlatformMBeanServer()` có tự cho phép máy khác truy cập JVM không?** Không; server cục bộ và bộ kết nối từ xa là các phần riêng.
3. **Có thể coi một lần đọc bean là kết luận chẩn đoán cuối cùng không?** Không; đó là dữ liệu theo phạm vi và thời điểm, cần kết hợp xu hướng, tải và các bằng chứng khác.

Nắm được giao diện quản lý, ObjectName, MBeanServer và ánh xạ kiểu giúp bạn chọn đúng đường lấy dữ liệu. Sau đó mới có cơ sở đọc sâu các nhóm bộ nhớ, luồng và GC mà không nhầm phạm vi hoặc ý nghĩa phép đo.
