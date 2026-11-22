# 6.1 ManagementFactory, platform MXBean và ranh giới giữa API chuẩn với phần mở rộng HotSpot

> **Java Advance – runtime-diagnostics** · **6. MXBeans**

## 1. Bài toán: Java runtime đang cho ta quan sát những gì?

Khi một API Java chậm bất thường, người vận hành thường hỏi: heap hiện dùng bao nhiêu, JVM có bao nhiêu thread, GC đã chạy mấy lần, process đã tiêu thụ bao nhiêu CPU time, hay hệ điều hành có đang quá tải không? Không phải câu hỏi nào cũng cần profiler, heap dump hay agent. Nhiều số đo nền tảng được JVM cung cấp qua **platform MXBeans**, truy cập trực tiếp từ code hoặc qua **JMX (Java Management Extensions)**.

Trong Java, **ManagementFactory** là điểm vào thuận tiện nhất cho những MXBean này. Tuy nhiên, cần phân biệt hai tầng:

- **API quản lý chuẩn của Java SE**, chủ yếu nằm trong module **java.management** và package **java.lang.management**. Đây là hợp đồng liên nền tảng, có tài liệu quy định loại bean, phương thức và trường hợp không hỗ trợ.
- **Các phần mở rộng của JDK/HotSpot**, nổi bật là module **jdk.management**, package **com.sun.management**. Chúng có thể cung cấp process CPU time, allocated bytes theo thread, thông tin GC chuyên sâu hoặc chẩn đoán HotSpot; không nên xem đó là hợp đồng bắt buộc trên mọi bản Java SE và mọi JVM implementation.

Bài này đi từ đối tượng API đến giá trị đo, ranh giới tương thích, cách viết ứng dụng chịu được khác biệt runtime và giới hạn khi sử dụng trong sự cố production.

### Sau bài này, bạn cần làm được

1. Giải thích mối quan hệ **ManagementFactory → platform MXBean → platform MBeanServer → JMX client/proxy**.
2. Chọn được bean chuẩn cho memory, threads, runtime, class loading, operating system, garbage collector và memory pool.
3. Phân biệt kiểu **một MXBean (singleton)** với **danh sách MXBeans**; tránh gọi API singleton cho một loại có nhiều thực thể.
4. Hiểu ObjectName, JMX OpenType và vì sao getter trong code có thể trả đối tượng Java còn JMX attribute dùng CompositeData.
5. Dùng Java 17+ truy vấn MXBean chuẩn, nhận diện **giá trị động**, **-1/không hỗ trợ**, **null** và các metric là counter/gauge.
6. Nhận biết và kiểm tra an toàn phần mở rộng **com.sun.management**, đặc biệt OperatingSystemMXBean và HotSpotDiagnosticMXBean.
7. Không lẫn khả năng *quan sát* với quyền *thay đổi trạng thái*; không biến một API JMX thành endpoint công khai không bảo vệ.

## 2. Mô hình kiến trúc: có thể truy cập trực tiếp hoặc qua JMX

~~~text
                         +-------------------------------+
                         | JVM đang chạy                 |
                         |                               |
  Java code cùng process  |  ManagementFactory            |
  ----------------------->|       |                       |
                         |       v                       |
                         |  Platform MXBeans             |
                         |  Memory, Thread, Runtime ...  |
                         |       |                       |
                         |       v                       |
                         |  Platform MBeanServer         |
                         |  ObjectName + JMX attributes  |
                         +---------------+---------------+
                                         |
                      MBeanServerConnection / JMX connector
                                         |
                                         v
                          JMX client / dashboard / tool
~~~

Có **hai đường lấy số đo** khác nhau:

**Đường A – gọi trực tiếp trong chính JVM:**

~~~java
// Minh họa nằm trong một phương thức Java; đây không phải cả chương trình.
java.lang.management.MemoryMXBean bean =
        java.lang.management.ManagementFactory.getMemoryMXBean();
long heapUsedBytes = bean.getHeapMemoryUsage().getUsed();
~~~

Đường này không cần khởi động một JMX server mạng chỉ để đọc nội bộ. Chương trình gọi interface Java tương ứng trên chính process đang chạy.

**Đường B – đi qua MBeanServer/JMX:**

~~~text
JMX client -> MBeanServerConnection -> ObjectName/attribute/operation
                                   -> platform MXBean
~~~

JMX cung cấp cách truy cập quản lý từ các công cụ hoặc ứng dụng khác nếu có kết nối phù hợp. **Việc gọi ManagementFactory.getPlatformMBeanServer() không tự động mở một cổng JMX công khai**; xuất bản endpoint từ xa cần cấu hình connector và kiểm soát bảo mật riêng. Mở cổng quản lý không xác thực là rủi ro nghiêm trọng vì nhiều bean và operation có thể lộ dữ liệu nhạy cảm hoặc thay đổi trạng thái JVM.

### MXBean khác MBean như thế nào?

**MBean** là khái niệm rộng của JMX: một managed object phơi bày attributes và operations. **MXBean** là dạng MBean có quy tắc ánh xạ kiểu dữ liệu Java sang **JMX OpenTypes** (ví dụ dữ liệu đơn giản, CompositeData, TabularData). Nhờ vậy client JMX không nhất thiết phải có đúng class Java cụ thể của object trả về để đọc dữ liệu.

Một đối tượng gọi trực tiếp:

~~~text
MemoryMXBean.getHeapMemoryUsage() -> MemoryUsage
~~~

Khi đọc attribute tương ứng qua MBeanServer:

~~~text
MBeanServer.getAttribute(ObjectName, "HeapMemoryUsage")
    -> một giá trị OpenType, thường là CompositeData
~~~

Đây không phải hai metric khác nhau; đó là **hai cách biểu diễn** cùng thông tin theo hợp đồng JMX. Đừng cast giá trị từ MBeanServer sang MemoryUsage mà không xem phép ánh xạ MXBean. Ví dụ chạy được ở phần thực hành sẽ chứng minh điểm này.

## 3. ManagementFactory: cổng vào nhất quán cho platform MXBeans

Class **java.lang.management.ManagementFactory** có các phương thức static trả về bean đã được platform cung cấp. Không cần tự tạo MemoryMXBean hay ThreadMXBean bằng constructor.

### 3.1 Những factory method nên nhớ

| Factory method | Kiểu trả về chuẩn | Câu hỏi chẩn đoán |
| --- | --- | --- |
| getRuntimeMXBean() | RuntimeMXBean | VM name/version, uptime, start time, input arguments |
| getMemoryMXBean() | MemoryMXBean | Heap/non-heap used/committed/max, số pending finalization nếu được cung cấp |
| getThreadMXBean() | ThreadMXBean | Số thread live/daemon/peak, thread CPU time, deadlock và ThreadInfo khi được hỗ trợ |
| getOperatingSystemMXBean() | OperatingSystemMXBean | OS name/architecture, processors available, system load average |
| getClassLoadingMXBean() | ClassLoadingMXBean | Lớp đang được load, tổng loaded/unloaded |
| getGarbageCollectorMXBeans() | List<GarbageCollectorMXBean> | Các GC manager hiện có, tổng collection count/time |
| getMemoryPoolMXBeans() | List<MemoryPoolMXBean> | Eden/Old/Metaspace hoặc pool do VM định nghĩa, usage/peak/threshold |
| getMemoryManagerMXBeans() | List<MemoryManagerMXBean> | Các memory managers và pools liên quan |
| getCompilationMXBean() | CompilationMXBean hoặc null | Thông tin hệ biên dịch/JIT khi có |
| getPlatformMXBean(Class<T>) | T hoặc null | Lấy platform management interface có **tối đa một** thực thể |
| getPlatformMXBeans(Class<T>) | List<T> | Lấy **từ 0 đến nhiều** bean cùng interface |
| getPlatformManagementInterfaces() | Set<Class<? extends PlatformManagedObject>> | Các management interfaces platform hỗ trợ, gồm cả phần mở rộng implementation |
| getPlatformMBeanServer() | MBeanServer | Cổng JMX chuẩn trong process |

**Số lượng có ý nghĩa.** MemoryMXBean và ThreadMXBean là singleton tiêu biểu. GarbageCollectorMXBean, MemoryManagerMXBean, MemoryPoolMXBean và BufferPoolMXBean là nhóm có thể có nhiều bean; số lượng/tên/thứ tự phụ thuộc VM, GC và cấu hình. CompilationMXBean có thể **không tồn tại** và method trả null.

Do đó, **không** gọi getPlatformMXBean(GarbageCollectorMXBean.class) rồi cho rằng có một collector duy nhất: API singleton có thể ném IllegalArgumentException vì loại interface này không phải singleton. Hãy dùng:

~~~java
// Mảnh mã minh họa, đặt trong phương thức bất kỳ.
var collectors = java.lang.management.ManagementFactory
        .getPlatformMXBeans(java.lang.management.GarbageCollectorMXBean.class);
for (var gc : collectors) {
    System.out.println(gc.getName() + ": " + gc.getCollectionCount());
}
~~~

Vòng lặp trên không có stdout cố định: tên GC, số bean và counter thay đổi theo JVM, cấu hình collector và thời điểm quan sát.

### 3.2 getPlatformMXBean có thể null, list có thể rỗng

Với interface singleton được platform biết đến nhưng không triển khai, **getPlatformMXBean(Class<T>) có thể trả null**. Với interface quản lý không được công nhận là platform interface hoặc sử dụng singleton API cho loại nhiều instance, **IllegalArgumentException** là kết quả hợp lệ của API. Với phiên bản JDK/vendor khác, đừng mặc định mọi extension đều có mặt.

Với getPlatformMXBeans(Class<T>), kết quả có thể là danh sách rỗng, một hoặc nhiều bean; **thứ tự không được cam kết ổn định**. Không viết code “phần tử 0 luôn là Old GC” hoặc “tên pool luôn là G1 Old Gen”. Nếu cần phân biệt loại pool, đọc *getName()*, *getType()*, *getMemoryManagerNames()* và metadata thực tế, đồng thời chấp nhận tên có thể đổi giữa collector/version.

### 3.3 getPlatformManagementInterfaces là danh mục khả năng, không phải bảo đảm mã của bạn sẽ portable

Method này trả tập các interface do platform hiện tại cung cấp; trong OpenJDK/HotSpot có thể bao gồm **interface JDK extension**, không chỉ chuẩn Java SE. Việc một extension xuất hiện ở build đang thử chỉ chứng minh **build đó** hỗ trợ, không chứng minh JVM khác bắt buộc phải làm vậy.

Một thiết kế portable phải dựa trên interface Java SE khi số đo chuẩn đủ dùng; chỉ mở rộng khi có **nhu cầu chẩn đoán rõ ràng**, có kiểm tra khả năng runtime và fallback.

## 4. Ranh giới mô-đun và khả năng tương thích

| Nhóm | Module và package | Hợp đồng | Ví dụ |
| --- | --- | --- | --- |
| Chuẩn Java SE | java.management / java.lang.management | API nền tảng được đặc tả trong Java SE | ManagementFactory, MemoryMXBean, ThreadMXBean, RuntimeMXBean, OperatingSystemMXBean |
| Chuẩn JMX | java.management / javax.management và javax.management.openmbean | Kết nối và truy cập attributes/operations, OpenTypes | MBeanServer, MBeanServerConnection, ObjectName, CompositeData |
| Phần mở rộng JDK | jdk.management / com.sun.management | API có tài liệu trong JDK, không thuộc hợp đồng Java SE cốt lõi | OperatingSystemMXBean mở rộng, ThreadMXBean mở rộng, HotSpotDiagnosticMXBean, GcInfo |
| Cơ chế HotSpot/chẩn đoán khác | Công cụ, JFR, diagnostic commands, JDK-specific APIs | Phụ thuộc VM và tool, không thể thay thế bằng lời gọi Java SE nếu chưa có interface chuẩn | jcmd VM.*, heap dump, chi tiết GC |

**Hai package cùng có tên OperatingSystemMXBean**:

- **java.lang.management.OperatingSystemMXBean** chỉ có các thuộc tính cơ bản như OS name, architecture, available processors và load average.
- **com.sun.management.OperatingSystemMXBean** extends interface chuẩn, thêm thông tin process CPU time/load, memory/cpu environment. Với JDK 17, những method thường gặp gồm *getProcessCpuTime()*, *getProcessCpuLoad()*, *getCpuLoad()*, *getTotalMemorySize()* và *getFreeMemorySize()*.

Đừng viết import wildcard cho hai package cùng lúc rồi dùng tên *OperatingSystemMXBean* không rõ nghĩa. Trong ví dụ extension, chúng ta cố ý viết tên interface mở rộng đầy đủ để phân biệt.

Trong **ứng dụng có module-info.java**:

~~~java
module diagnostics.app {
    requires java.management;
}
~~~

Đó là module descriptor đủ cho phần dùng API chuẩn của bài (nếu app không có dependency/module khác). Chỉ khi code **tham chiếu trực tiếp** com.sun.management và JDK thực tế có module đó, mới cần:

~~~java
module diagnostics.app {
    requires java.management;
    requires jdk.management;
}
~~~

Đây là hai ví dụ descriptor **thay thế nhau**, không đặt cùng một file. Không tự động thêm requires jdk.management vào mọi service chỉ để đọc heap used chuẩn. Module jdk.management có thể không được đóng gói vào custom runtime image nếu jlink không bao gồm, nên tham chiếu tới nó có thể khiến deployment fail ngay cả khi build tại máy phát triển thành công.

**Ghi nhớ:** “com.sun.management có tài liệu công khai trong JDK” khác “com.sun.management là API chuẩn bắt buộc của Java SE”; cũng khác “mọi lớp bắt đầu bằng sun.* đều được hỗ trợ”. Cách ra quyết định là theo **module/package và hợp đồng cụ thể**, không chỉ nhìn tiền tố tên package.

## 5. PlatformManagedObject và ObjectName

Mỗi platform MXBean triển khai **PlatformManagedObject**, có method *getObjectName()* dùng nhận diện object trong platform MBeanServer. Một số ObjectName ổn định trong API Java SE:

| Interface | ObjectName chuẩn |
| --- | --- |
| MemoryMXBean | java.lang:type=Memory |
| ThreadMXBean | java.lang:type=Threading |
| RuntimeMXBean | java.lang:type=Runtime |
| OperatingSystemMXBean | java.lang:type=OperatingSystem |
| ClassLoadingMXBean | java.lang:type=ClassLoading |
| CompilationMXBean (nếu tồn tại) | java.lang:type=Compilation |
| GarbageCollectorMXBean | java.lang:type=GarbageCollector,name=<tên collector> |
| MemoryPoolMXBean | java.lang:type=MemoryPool,name=<tên pool> |

Bảng trên minh họa quy ước đăng ký của bean chuẩn. Dòng có *name* có thể thay đổi giá trị giữa VM/collector và cần được **encode đúng theo ObjectName syntax** khi dùng JMX API. Tốt nhất **lấy trực tiếp bean.getObjectName()** khi đã có bean, thay vì tự ghép chuỗi tên. ObjectName không phải Java class name và cũng không phải PID.

Platform MBeanServer được lấy bằng:

~~~java
// Mảnh mã minh họa.
javax.management.MBeanServer server =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
~~~

Lần lấy đầu tiên có thể khởi tạo server và đăng ký các platform MXBeans hiện hữu; những platform beans có lifecycle động có thể được đăng ký/hủy đăng ký tương ứng. Có server local **không chứng minh** có remote JMX listener mở cổng.

### Ba cách truy cập cùng platform MXBean

1. **Direct Java interface:** getMemoryMXBean().getHeapMemoryUsage(), thuận tiện khi chạy trong cùng JVM.
2. **MBeanServer/MBeanServerConnection:** lấy attribute bằng ObjectName, ví dụ *getAttribute(name, "HeapMemoryUsage")*, phù hợp công cụ quản lý/JMX.
3. **Typed proxy:** *ManagementFactory.getPlatformMXBean(connection, MemoryMXBean.class)* hoặc *newPlatformMXBeanProxy(connection, name, MemoryMXBean.class)*, chuyển các lời gọi method qua MBeanServerConnection.

Proxy dễ viết mã typed hơn so với ObjectName attribute thô, nhưng còn phụ thuộc kết nối và chuyển đổi OpenType. Một lời gọi proxy có thể phát sinh lỗi I/O (thậm chí được gói trong exception của dynamic proxy), phải xử lý disconnect, timeout và mismatch phiên bản. Truy cập local trực tiếp không gặp vấn đề kết nối mạng ấy.

**Không dùng cùng ngữ nghĩa** cho “local bean được giữ trong một biến của JVM ứng dụng” và “remote proxy qua JMX connector”. Hai thứ có thể cùng interface nhưng khác timeout, concurrency và biên an toàn.

## 6. Ví dụ Java 17+ dùng API chuẩn và OpenType: chạy độc lập

Mục tiêu của ví dụ:

- Truy cập MemoryMXBean, RuntimeMXBean, ThreadMXBean và OperatingSystemMXBean qua **ManagementFactory chuẩn**.
- Đọc các giá trị heap/thread/uptime động nhưng **không in số tuyệt đối** vì chúng khác giữa các máy.
- Truy cập platform MBeanServer và chứng minh thuộc tính Java *MemoryUsage* được chuyển thành **CompositeData** qua JMX.
- In các mệnh đề kiểm tra có **stdout ổn định** trên Java 17+ có platform MXBeans chuẩn.

Tạo file **StandardMxBeanDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.OperatingSystemMXBean;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import javax.management.MBeanServer;
import javax.management.openmbean.CompositeData;

public final class StandardMxBeanDemo {
    public static void main(String[] args) throws Exception {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        System.out.println("memoryObjectName=" + memory.getObjectName());
        System.out.println("runtimeObjectName=" + runtime.getObjectName());
        System.out.println("memoryRegistered=" + server.isRegistered(memory.getObjectName()));
        System.out.println("heapAttributeIsOpenData="
                + (server.getAttribute(memory.getObjectName(), "HeapMemoryUsage")
                   instanceof CompositeData));
        System.out.println("heapUsedNonnegative=" + (heap.getUsed() >= 0));
        System.out.println("heapCommittedNonnegative=" + (heap.getCommitted() >= 0));
        System.out.println("threadCountPositive=" + (threads.getThreadCount() > 0));
        System.out.println("uptimeNonnegative=" + (runtime.getUptime() >= 0));
        System.out.println("processorsPositive=" + (os.getAvailableProcessors() > 0));
        System.out.println("memoryInterfaceListed=" + ManagementFactory
                .getPlatformManagementInterfaces().contains(MemoryMXBean.class));
    }
}
~~~

Trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 StandardMxBeanDemo.java
java StandardMxBeanDemo
~~~

**Stdout chính xác của phép thử này trên môi trường Java 17+ thông thường:**

~~~text
memoryObjectName=java.lang:type=Memory
runtimeObjectName=java.lang:type=Runtime
memoryRegistered=true
heapAttributeIsOpenData=true
heapUsedNonnegative=true
heapCommittedNonnegative=true
threadCountPositive=true
uptimeNonnegative=true
processorsPositive=true
memoryInterfaceListed=true
~~~

Vì chương trình in **kiểm tra điều kiện**, không in số liệu heap/uptime tuyệt đối, đầu ra có thể so khớp khi học. Đã thử biên dịch/chạy chương trình độc lập trên JDK thực tế và thu các dòng trên.

**Diễn giải:**

- *memory.getObjectName()* là định danh platform bean, không phụ thuộc PID hay tên lớp implement.
- *getHeapMemoryUsage()* trả một **MemoryUsage snapshot** có số byte tại thời điểm đo; method *getUsed()* khác phép đo RSS của process.
- *getAttribute(..., "HeapMemoryUsage")* trả một **MXBean OpenType**, ở đây là CompositeData. Không phải phải cài cùng MemoryUsage class lên một JMX client khác mới đọc được các thành phần dữ liệu.
- *getThreadCount()* phản ánh thread count tại thời điểm đọc, không phải số request/s; *getUptime()* tính mili giây từ khi JVM khởi động, không phải timestamp hiện tại.
- *getPlatformManagementInterfaces()* cho biết interface MemoryMXBean nằm trong tập hỗ trợ; tập có thể chứa các interface extension của JDK đang chạy.

**Giới hạn của ví dụ:** kiểm tra trên không chứng minh kết quả của tất cả JVM version/vendor. Mỗi snapshot có thể được lấy ở thời điểm khác nhau; không có thao tác chụp đồng thời nguyên tử cho toàn bộ CPU/heap/threads. Trước khi dùng làm alert, cần biết semantics, đơn vị và chính sách “không hỗ trợ”.

## 7. Cách đọc đúng các metric chuẩn: gauge, counter, sentinel

Platform MXBeans tiện vì ít cấu hình, nhưng bản thân dữ liệu rất dễ bị suy diễn sai.

| Method | Kiểu dữ liệu/đơn vị | Kiểu metric | Bẫy thường gặp |
| --- | --- | --- | --- |
| MemoryMXBean.getHeapMemoryUsage().getUsed() | byte | Gauge/snapshot | Không phải RSS, không phải tổng đã allocate |
| MemoryUsage.getCommitted() | byte | Gauge/snapshot | JVM đã cam kết vùng nhớ, không phải byte còn sống |
| MemoryUsage.getMax() | byte hoặc -1 | Giới hạn nếu xác định | -1 nghĩa là max không xác định |
| RuntimeMXBean.getUptime() | mili giây | Thời gian từ khi JVM chạy | Reset về gần 0 sau restart; không phải thời gian lịch |
| ThreadMXBean.getThreadCount() | thread | Gauge | Không phải thông lượng xử lý request |
| ThreadMXBean.getPeakThreadCount() | thread | High-water mark | Không phải số thread hiện tại; có thể reset qua operation |
| ClassLoadingMXBean.getTotalLoadedClassCount() | tổng số class | Counter tích lũy | Khác getLoadedClassCount() là số hiện đang loaded |
| ClassLoadingMXBean.getUnloadedClassCount() | tổng số class | Counter tích lũy | Không phải số class unload/s nếu chưa lấy delta |
| GarbageCollectorMXBean.getCollectionCount() | số lần hoặc -1 | Counter nếu được hỗ trợ | Không bằng số GC pause ở mọi collector/VM |
| GarbageCollectorMXBean.getCollectionTime() | mili giây hoặc -1 | Thời lượng tích lũy nếu được hỗ trợ | Không phải độ trễ một GC cụ thể/p99 pause |
| OperatingSystemMXBean.getAvailableProcessors() | số processor | Trạng thái/capacity | Có thể thay đổi do quota/affinity/runtime |
| OperatingSystemMXBean.getSystemLoadAverage() | load average hoặc âm | Chỉ báo tải hệ điều hành | Không phải CPU percentage; có thể không hỗ trợ |

### 7.1 MemoryUsage có bốn thành phần

Một snapshot **MemoryUsage** chứa *init*, *used*, *committed*, *max*:

- *init*: bộ nhớ ban đầu JVM yêu cầu hệ điều hành, có thể không xác định.
- *used*: lượng bộ nhớ được dùng theo phạm vi quản lý của bean/pool tại snapshot.
- *committed*: bộ nhớ đã cam kết, JVM được đảm bảo có thể sử dụng theo mô hình JVM.
- *max*: ngưỡng tối đa có thể sử dụng nếu xác định; giá trị **-1** nghĩa là không xác định.

Trong điều kiện hợp lệ, *used ≤ committed*; *committed* và *max* không phải cùng một chỉ số. **Không lấy used/max thành phần trăm khi max = -1**, vì biểu thức không có ý nghĩa. Và đừng coi heap max là toàn bộ hạn mức memory của container: process còn có metaspace, code cache, thread stacks, native allocations, direct buffers và nhiều vùng khác.

**MemoryMXBean.getNonHeapMemoryUsage()** không tương đương toàn bộ RAM ngoài heap. Những phân bổ native khác nhau có thể không nằm trong cách hạch toán của non-heap MXBean; để biết RSS/native footprint cần số liệu OS/container hoặc công cụ chẩn đoán phù hợp.

### 7.2 GC count/time là counter, không phải histogram latency

Ví dụ đọc hai snapshot của một collector, cách nhau \(\Delta t\):

\[
\text{GC collections/s} = \frac{C_2-C_1}{\Delta t},
\qquad
\text{GC time ratio} = \frac{T_2-T_1}{1000\Delta t}
\]

Với \(T\) tính bằng **mili giây**, \(\Delta t\) tính bằng **giây**. Nhưng công thức này chỉ có ý nghĩa khi:
- Hai snapshot thuộc **cùng JVM/collector** và counter không bị reset.
- Cả count/time **khác -1** (được hỗ trợ).
- Chúng có cùng phạm vi định nghĩa; hiểu cách GC vendor/collector tính thời gian.
- Không dùng delta âm sau process restart.

Một tổng GC collection time tăng 300 ms trong 60 s **không** đủ để biết p99 pause: cần phân bố từng pause từ JFR/GC logs/histogram phù hợp. Collection time theo bean có thể phụ thuộc cách implementation định nghĩa thời gian; đừng đánh đồng máy móc với “số mili giây tất cả thread ứng dụng bị stop-the-world”.

### 7.3 ThreadMXBean: kiểm tra support trước khi đo

Một số chức năng có điều kiện:

- *isThreadCpuTimeSupported()* và *isCurrentThreadCpuTimeSupported()* kiểm tra khả năng đo CPU time.
- *isThreadCpuTimeEnabled()* kiểm tra trạng thái bật/tắt hiện tại; máy ảo có thể hỗ trợ nhưng đang tắt.
- *getThreadCpuTime(threadId)* có thể trả **-1** nếu không hỗ trợ, không bật hoặc thread không hợp lệ/đã kết thúc theo hợp đồng.
- *isThreadContentionMonitoringSupported()* kiểm tra hỗ trợ contention timings; bật đo có thể tạo overhead.
- *findDeadlockedThreads()* và *dumpAllThreads(...)* có thể giúp điều tra lock, nhưng mức dữ liệu và tác động tăng theo số thread.

Không gọi *setThreadCpuTimeEnabled(true)* hoặc *setThreadContentionMonitoringEnabled(true)* như một bước “chỉ đọc” trong production. Đây là **thao tác thay đổi trạng thái đo**, có chi phí và quyền truy cập riêng. Kiểm tra khả năng, policy và cần thiết trước khi bật.

### 7.4 Số -1 và null không đồng nghĩa với 0

Trong tài liệu quản lý Java, **-1** thường là sentinel “không hỗ trợ/không xác định” của method cụ thể. Nhưng không phải mọi method dùng cùng sentinel. *getCompilationMXBean()* có thể trả null nếu JVM không có compilation system; *MemoryPoolMXBean.getUsage()* có thể không khả dụng trong một số tình huống; *OperatingSystemMXBean.getSystemLoadAverage()* trả giá trị âm nếu không được cung cấp.

**Sai:** “System load = -1 nên máy đang thiếu tải và có thể bỏ qua.”

**Đúng:** “System load average không khả dụng trên JVM/OS này; dùng metric OS khác.” Không đưa giá trị -1 vào biểu đồ CPU load như một số đo thực.

Nếu bean method trả *UnsupportedOperationException*, hãy phân biệt tính năng được hỗ trợ với quyền truy cập và cấu hình runtime. Không catch mọi exception rồi giả vờ số đo bằng 0, vì dashboard sẽ dễ đưa ra kết luận sai.

## 8. Phần mở rộng JDK/HotSpot: com.sun.management

Package **com.sun.management** nằm trong module **jdk.management** (JDK 17) và có tài liệu chính thức. Nó là **extension của JDK**, không phải interface cốt lõi được quy định bắt buộc trong mọi Java SE runtime.

### 8.1 Các interface mở rộng thường gặp

| Interface JDK extension | Liên hệ với API chuẩn | Khả năng bổ sung điển hình |
| --- | --- | --- |
| com.sun.management.OperatingSystemMXBean | extends java.lang.management.OperatingSystemMXBean | Process CPU time/load, CPU load của environment, physical/container memory metrics |
| com.sun.management.UnixOperatingSystemMXBean | extends OS bean mở rộng | Thông tin file descriptor trên môi trường Unix khi có |
| com.sun.management.ThreadMXBean | extends java.lang.management.ThreadMXBean | Số byte đã được thread cấp phát và phương thức kiểm tra hỗ trợ |
| com.sun.management.GarbageCollectorMXBean | extends bean GC chuẩn | Thông tin về lần GC gần nhất (GcInfo) khi collector hỗ trợ |
| com.sun.management.HotSpotDiagnosticMXBean | PlatformManagedObject riêng | VM options và các thao tác HotSpot như heap dump |
| com.sun.management.DiagnosticCommandMBean | MBean cho diagnostic commands HotSpot | Bộ operations riêng của VM, không phải API nghiệp vụ chuẩn |

Một interface xuất hiện trong package không bảo đảm mọi method **hoạt động trên tất cả cấu hình/OS**, đặc biệt với CPU time, allocation-by-thread hoặc thông tin GC chuyên sâu.

### 8.2 OperatingSystemMXBean: tiêu biểu cho ranh giới chuẩn/mở rộng

Đoạn sau **không tồn tại** trên interface chuẩn:

~~~text
com.sun.management.OperatingSystemMXBean.getProcessCpuTime()
com.sun.management.OperatingSystemMXBean.getProcessCpuLoad()
com.sun.management.OperatingSystemMXBean.getTotalMemorySize()
com.sun.management.OperatingSystemMXBean.getFreeMemorySize()
~~~

Vì vậy mã chỉ dùng import *java.lang.management.OperatingSystemMXBean* mà gọi *getProcessCpuTime()* sẽ **không biên dịch**: không phải do JVM “thiếu CPU”, mà do **interface chuẩn không khai báo method đó**.

Để thấy process CPU time từ JDK extension trên một JVM hỗ trợ, cần truy cập interface mở rộng **có kiểm tra runtime**. Ví dụ độc lập dưới đây dùng pattern matching *instanceof* của Java 17, và cố ý phân biệt biến chuẩn với biến mở rộng.

Tạo file **JdkManagementExtensionDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public final class JdkManagementExtensionDemo {
    public static void main(String[] args) {
        OperatingSystemMXBean standard = ManagementFactory.getOperatingSystemMXBean();
        if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
            System.out.println("jdkExtensionAvailable=true");
            long processCpuNanos = extended.getProcessCpuTime();
            if (processCpuNanos < 0) {
                System.out.println("processCpuTime=unsupported");
            } else {
                System.out.println("processCpuTime=nonnegative");
            }
        } else {
            System.out.println("jdkExtensionAvailable=false");
        }
    }
}
~~~

Trong JDK 17+ có module **jdk.management** và implementation phù hợp:

~~~bash
javac -encoding UTF-8 JdkManagementExtensionDemo.java
java JdkManagementExtensionDemo
~~~

Kết quả đã quan sát được trên một JDK HotSpot hỗ trợ CPU-time:

~~~text
jdkExtensionAvailable=true
processCpuTime=nonnegative
~~~

**Đây là đầu ra của môi trường kiểm thử, không phải lời cam kết cho mọi VM.** Nếu runtime có class extension nhưng implementation không cung cấp bean, nhánh “unavailable” được dùng; nếu CPU time không được hỗ trợ, in dòng “unsupported”. Nếu JDK/runtime image **không chứa jdk.management**, mã có liên kết trực tiếp tới com.sun.management có thể **không biên dịch hoặc không khởi động được**; ở môi trường đó phải chọn bản xây dựng khác hoặc tách module/tùy chọn extension.

Tại sao code dùng *instanceof*? Interface chuẩn là hợp đồng bạn có thể luôn làm việc với khi dùng Java SE có MXBean tương ứng. *instanceof* chỉ đi vào nhánh phụ thuộc JDK khi implementation thực sự thỏa interface; tránh ép kiểu không kiểm tra gây ClassCastException. Tuy nhiên guard runtime **không thay thế** việc kiểm tra sự có mặt của module trong quá trình build/deploy.

### 8.3 CPU time và CPU load không phải cùng đại lượng

Phương thức *getProcessCpuTime()* của extension trả **CPU time tích lũy theo nanosecond** hoặc **-1** nếu không được hỗ trợ. Nếu muốn mức tiêu thụ CPU trung bình giữa hai snapshot, cần lấy:

\[
\frac{\Delta \text{processCpuNanos}}{\Delta \text{wallNanos}}
\]

Kết quả có thể lớn hơn 1 nếu process dùng nhiều CPU core đồng thời. Để chuyển sang tỷ lệ công suất, phải chọn cách chuẩn hóa theo **available processors/quota** và hiểu hợp đồng metric của runtime; không tùy tiện gọi nó là 100% khi có nhiều core.

Các method như *getProcessCpuLoad()* trả số đo về **recent CPU usage**, có thể trả giá trị âm khi không hỗ trợ. Không suy ra “process đang dùng 0% CPU” chỉ vì một lời gọi trả -1. CPU load gần thời điểm hiện tại khác CPU time tích lũy, và chúng có thể phản ứng khác nhau với sampling/containers.

Các method bộ nhớ môi trường như *getTotalMemorySize()* và *getFreeMemorySize()* thuộc extension, không nằm trong API chuẩn OS bean; việc chúng diễn giải container limit hay host capacity còn phụ thuộc môi trường và triển khai. Đừng lấy total memory trên một bản build rồi tuyên bố là memory heap max hoặc cgroup hard limit trên mọi JVM.

### 8.4 HotSpotDiagnosticMXBean: vượt khỏi việc đọc số đo

**HotSpotDiagnosticMXBean** có ObjectName theo JDK implementation, thường là:

~~~text
com.sun.management:type=HotSpotDiagnostic
~~~

Nó hỗ trợ các operation điển hình:

- *getDiagnosticOptions()*: các VM options có thể chẩn đoán/thay đổi theo khả năng.
- *getVMOption(name)*: đọc trạng thái option được chỉ định.
- *setVMOption(name, value)*: **thay đổi** một VM option hỗ trợ thay đổi động; không phải tất cả option đều writable.
- *dumpHeap(path, live)*: tạo heap dump (file *.hprof*) trong filesystem mà JVM nhìn thấy.

**Cảnh báo:** heap dump có thể rất lớn, tạo áp lực CPU/I/O/disk, ảnh hưởng độ trễ và chứa đối tượng/secret của ứng dụng. Dù bean tồn tại, việc gọi dumpHeap **không phải thao tác đọc nhẹ**. Tương tự, setVMOption là thao tác điều khiển runtime, cần quyền và kế hoạch vận hành. Tài liệu JDK nêu lỗi cho file đã tồn tại, path không hợp lệ, không được ghi hoặc operation không hỗ trợ.

Nếu chỉ cần kiểm tra ban đầu, hãy ưu tiên các API chuẩn ít xâm lấn như heap usage, thread count và runtime uptime; đừng thử dumpHeap để “test xem extension dùng được không”.

## 9. Chiến lược thiết kế code: standard-first, kiểm tra capability, fallback

Một thư viện observability thường được tái sử dụng ở nhiều service. Nếu lớp core import com.sun.management ở mọi nơi, một runtime image tối giản hoặc implementation JVM khác có thể không chạy được, dù chức năng chuẩn vẫn có.

Thiết kế đề xuất:

~~~text
DiagnosticsFacade
    |
    +-- StandardJmxReader (java.management)
    |     +-- memory, threads, runtime, OS basics, GC
    |
    +-- OptionalJdkReader (jdk.management) [nếu có]
    |     +-- process CPU, thread allocation, HotSpot-specific
    |
    +-- Metrics exporter / structured result
          +-- giá trị
          +-- đơn vị
          +-- nguồn
          +-- phạm vi instance
          +-- availability: supported / unavailable / error
~~~

**Các nguyên tắc cụ thể:**

1. **Dùng chuẩn trước:** nếu muốn heap used, dùng MemoryMXBean thay vì HotSpotDiagnosticMXBean.
2. **Phân tách dependency:** extension trong adapter/module riêng; core không luôn phải load code extension.
3. **Capability detection:** kiểm tra interface/module và các *isXxxSupported()*, null/-1 theo contract. Không lấy tên JVM chứa chuỗi “HotSpot” làm phép kiểm duy nhất.
4. **Định nghĩa kết quả vắng mặt:** biểu diễn *unsupported* hoặc *not available*, không làm giả số đo 0.
5. **Ghi đơn vị và xuất xứ:** “CPU time từ JDK extension, nanosecond” khác “system load average từ Java SE, dimensionless”.
6. **Không giả định tên bean cố định ở các loại nhiều instance:** collector/pool có thể biến đổi sau đổi GC hoặc version.
7. **Tách read-only metrics và control operations:** một endpoint cung cấp số đo không nên ngầm kích hoạt dumpHeap hoặc setVMOption.
8. **Thử nhiều môi trường:** ít nhất các JDK/GC/OS/container mà sản phẩm thực sự hỗ trợ; nêu phạm vi được kiểm thử.

Ví dụ trả dữ liệu ra JSON từ một exporter: một trường “processCpuTimeNs = null; availability=unsupported; source=jdk.management” tốt hơn “processCpuTimeNs = 0”, vì số 0 có thể khiến alert suy ra process nhàn rỗi trong khi thực tế không đo được.

## 10. JMX client và MXBean proxy: portability ở tầng dữ liệu

Khi cần đọc từ một process khác, người dùng có thể truy vấn MBeanServerConnection. **JMX connector được bảo vệ** cung cấp đường từ client tới server; ManagementFactory hỗ trợ tạo proxy typed tương ứng với MXBean trên connection đó.

Ví dụ **mảnh mã, không độc lập** — giả sử biến *connection* là MBeanServerConnection đã kết nối an toàn:

~~~java
java.lang.management.MemoryMXBean remoteMemory =
        java.lang.management.ManagementFactory.getPlatformMXBean(
                connection, java.lang.management.MemoryMXBean.class);
if (remoteMemory != null) {
    long bytes = remoteMemory.getHeapMemoryUsage().getUsed();
    // Xuất bytes cùng timestamp và danh tính JVM đích.
}
~~~

Đây là cùng interface chuẩn nhưng **truy cập remote**. Kết nối có thể mất, JVM target restart hoặc JMX client dùng version khác. Cần xử lý thời gian chờ, lỗi giao tiếp, object biến mất và các vấn đề ánh xạ OpenTypes.

Một cách không dùng proxy là:

~~~java
// Mảnh mã, đòi hỏi MBeanServerConnection connection có sẵn.
javax.management.ObjectName name =
        new javax.management.ObjectName("java.lang:type=Memory");
Object value = connection.getAttribute(name, "HeapMemoryUsage");
// value được ánh xạ qua OpenType/CompositeData, không cast thẳng MemoryUsage.
~~~

**Không có ObjectName bí mật:** các tên chuẩn có thể biết được, nhưng điều đó không phải lý do để mở JMX ra mạng công cộng. **Authentication, TLS, network access control và quyền thao tác** là những điều cần thiết khi một JMX connector được bật từ xa, đặc biệt đối với MBeans có operations điều khiển.

JMX proxy được thiết kế cho sự tương tác liên phiên bản nhờ OpenTypes, nhưng không đảm bảo mỗi method mới/cũ trên interface có cùng ý nghĩa hay luôn tồn tại. Client nên dùng hợp đồng phiên bản phù hợp, xử lý unsupported/unknown attribute và có quy tắc fallback.

## 11. ManagementFactory không phải công cụ chẩn đoán mọi vấn đề

**Khi dùng MXBeans là hợp lý:**

- Poll heap used/committed, thread count, class loading, GC count/time.
- Kiểm tra runtime uptime/start time để nhận diện restart.
- Đọc OS available processors/load average theo API chuẩn.
- Xác định số lượng và tên pool/collector do JVM thực tế cung cấp.
- Triển khai exporter nội bộ có chi phí thấp, kiểm tra tình trạng cơ bản thường xuyên.

**Khi cần dữ liệu khác MXBeans:**

- **p95/p99 GC pause chính xác:** GC logs, JFR hoặc histogram có ghi từng sự kiện; tổng collection time không cho distribution.
- **Nghi object retention hoặc memory leak:** heap dump/JFR allocation profiling/công cụ phân tích; heap used một thời điểm không chứng minh leak.
- **Deadlock hoặc lock contention chi tiết:** ThreadMXBean có khả năng hỗ trợ, nhưng cần ThreadInfo/stack/JFR và đối chiếu trạng thái trong thời gian.
- **Native memory/RSS:** OS metrics, container metrics hoặc Native Memory Tracking/công cụ phù hợp; heap + nonheap không bằng toàn bộ RSS.
- **Request latency và business errors:** application metrics/log/tracing; MXBean không mặc định biết route/requestId.
- **Per-thread allocation hoặc process CPU:** có thể cần extension và kiểm tra support.

### Minh họa: vì sao chỉ nhìn một bean dẫn tới kết luận sai?

Một JVM chạy với throughput tăng mạnh, heap used dao động quanh 500 MiB. Nếu chỉ nhìn *getHeapMemoryUsage().getUsed()*, có thể kết luận “memory ổn, không có vấn đề”. Nhưng application có thể đang cấp phát object với tốc độ rất cao rồi GC liên tục; heap used không nhất thiết tăng nếu collector vẫn thu hồi kịp. Cần đọc **GC count/time qua nhiều snapshot**, allocation metrics/JFR và request latency, thay vì nhìn gauge đơn lẻ.

Ngược lại, heap used tăng trong giai đoạn warming rồi ổn định không đủ chứng minh leak; cần baseline, retained heap, collector behavior và tải tương đương.

## 12. Diagnostic walkthrough: đọc đúng tín hiệu cho bốn triệu chứng

### 12.1 Heap tăng dần sau mỗi đợt tải

**Nguồn chuẩn:** MemoryMXBean.getHeapMemoryUsage(), MemoryPoolMXBeans theo pool.

**Câu hỏi:** heap used tăng trong mọi thời điểm hay chỉ trước GC? Giá trị sau GC có tăng qua nhiều chu kỳ? Committed/max thay đổi do ergonomic sizing không?

**Phép đo bổ sung:** GC logs/JFR, memory pool usage, native/container memory; chỉ tiến tới heap dump khi có quyền và lợi ích điều tra rõ.

**Giới hạn:** HeapMemoryUsage không cho object graph hay ai giữ tham chiếu. DumpHeap qua extension có thể giúp nhưng là operation tác động mạnh.

### 12.2 Thread count tăng, API throughput lại giảm

**Nguồn chuẩn:** ThreadMXBean.getThreadCount(), getPeakThreadCount(), getAllThreadIds()/getThreadInfo() tùy nhu cầu và support.

**Câu hỏi:** live threads tăng do pool mở rộng, blocked/waiting, deadlock hay thread leak? Có bao nhiêu request in flight, queue depth và timeout?

**Phép đo bổ sung:** thread dump/JFR/stack, thread-pool gauges, dependency latency. Không kết luận “CPU cạn” chỉ từ số thread; thread đang WAITING có thể tiêu thụ rất ít CPU.

**Giới hạn:** Một số thread CPU times/lock contention cần đo được hỗ trợ và bật; bật khi đang sự cố có chi phí. Số thread cũng không đồng nhất với số virtual threads ở các JVM đời mới; cần đọc tài liệu đúng release nếu ứng dụng dùng virtual threads.

### 12.3 GC count tăng, p99 xấu đi

**Nguồn chuẩn:** List<GarbageCollectorMXBean>; đọc collection count/time ở hai hoặc nhiều thời điểm.

**Câu hỏi:** collection rate/tổng collection time tăng bao nhiêu? Có restart/counter reset không? Bộ đếm có trả -1 không? Dữ liệu theo collector nào?

**Phép đo bổ sung:** GC logging/JFR pause duration và timestamp, allocation rate, heap pools, CPU. “GC count tăng” chỉ là tương quan; phải xác nhận pause có đủ độ lớn và trùng request chậm.

### 12.4 CPU cao trong container

**Nguồn chuẩn:** OperatingSystemMXBean.getAvailableProcessors()/getSystemLoadAverage().

**Nguồn có thể thêm từ JDK extension:** process CPU time/load, CPU load environment. Các số đo trên có thể phụ thuộc JDK, cgroup, quota và host/container isolation.

**Phép đo bổ sung:** OS/container metrics về CPU throttling/quota, process CPU, thread CPU time khi hỗ trợ, JFR CPU/profile. Không lấy system load average làm phần trăm CPU và không suy ra process CPU% từ snapshot đơn lẻ của CPU time tích lũy.

## 13. Những điều phải đặc biệt cẩn trọng trong production

### 13.1 Những method chỉ đọc và những operation điều khiển

| Nhóm | Ví dụ | Mức tác động |
| --- | --- | --- |
| Đọc snapshot | getHeapMemoryUsage(), getThreadCount(), getUptime() | Thường thích hợp cho monitoring, nhưng vẫn có overhead khi thu liên tục quá dày |
| Đọc danh sách runtime | getMemoryPoolMXBeans(), getGarbageCollectorMXBeans() | Phải xử lý danh sách thay đổi; không nên poll quá mức |
| Thu stack/chi tiết khóa | ThreadInfo, dumpAllThreads() | Có thể tốn CPU/bộ nhớ, trả dữ liệu lớn |
| Bật/tắt đo thêm | setThreadCpuTimeEnabled(), setThreadContentionMonitoringEnabled() | **Thay đổi trạng thái**, cần cân nhắc chi phí và quyền |
| Yêu cầu GC | MemoryMXBean.gc() | **Không chỉ đọc**; yêu cầu chạy GC, không bảo đảm kết quả/thời điểm, có thể ảnh hưởng latency |
| Dump bộ nhớ | HotSpotDiagnosticMXBean.dumpHeap() | **Tác động cao**, tốn disk/I/O, nguy cơ dữ liệu nhạy cảm |
| Đổi VM option | HotSpotDiagnosticMXBean.setVMOption() | **Thay đổi runtime**, có thể không được hỗ trợ hoặc option không writable |

Một exporter “read-only” nên tránh expose operations điều khiển một cách không kiểm soát. Nếu phải cho phép thao tác mạnh, tách endpoint, authentication, authorization, audit, rate limit và approval riêng.

### 13.2 Sampling và overhead

Một bean trả số liệu tại thời điểm đọc. Lấy heap usage, GC count và thread count qua ba lời gọi không tạo **global atomic snapshot**; nếu JVM thay đổi nhanh, ba giá trị có thể phản ánh ba thời điểm khác nhau. Gắn timestamp riêng hoặc cửa sổ sampling thích hợp, và tránh việc dùng chênh lệch bất nhất làm bằng chứng chắc chắn của causal chain.

Poll mỗi vài chục mili giây có thể tăng overhead mà không cải thiện chất lượng kết luận. Ngược lại, poll mỗi 5 phút có thể bỏ qua spike ngắn. Chọn tần suất theo triệu chứng và kết hợp metrics theo lịch, event traces/JFR khi điều tra sâu.

### 13.3 Counter reset, đổi GC và đổi JVM instance

Nếu service restart, RuntimeMXBean uptime giảm và các counter GC/class loading bắt đầu chu kỳ mới. Khi autoscale, một instance mới có counters gần 0, instance cũ có thể biến mất. Tính **rate/increase theo instance trước khi aggregate**, không lấy hiệu raw total của fleet khi số instance thay đổi.

Không cache tên GarbageCollectorMXBean, MemoryPoolMXBean hoặc index trong list như một hợp đồng bất biến xuyên version. Hãy ghi VM version, collector và ObjectName trong metadata quan sát.

### 13.4 Quyền xem và dữ liệu nhạy cảm

RuntimeMXBean.getInputArguments() có thể chứa JVM options, đường dẫn hoặc tham số nhạy cảm. JMX management interface có thể bộc lộ thông tin cấu hình hệ thống. Heap dumps có thể chứa credentials, dữ liệu khách hàng, session state. Bảo vệ quyền xem, lưu trữ, đường xuất file, thời gian retention và redaction.

Từ xa, **JMX chưa được cấu hình bảo mật là một attack surface**. Không đưa một connector JMX/RMI ra Internet hoặc toàn cluster không hạn chế vì “chỉ để đọc CPU”. Một số operations thực sự có quyền điều khiển, và dữ liệu read-only cũng có thể nhạy cảm.

## 14. Các hiểu nhầm và lỗi phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “ManagementFactory chỉ có interface HotSpot” | Core API nằm trong Java SE java.management | Dùng java.lang.management trước |
| “com.sun.management là API Java SE chuẩn” | Đây là JDK extension trong jdk.management | Thiết kế fallback và kiểm tra module/vendor |
| “Tên method OperatingSystemMXBean giống nhau nên import nào cũng được” | Interface chuẩn và extension có bộ method khác nhau | Dùng fully qualified type hoặc import rõ ràng |
| “getPlatformMXBean cho GC collector trả singleton” | GC bean là multi-instance | Dùng getPlatformMXBeans/list |
| “getPlatformMXBean luôn trả bean” | Có singleton platform bean tùy chọn không được hỗ trợ | Xử lý null/IllegalArgumentException đúng contract |
| “Danh sách GC/pool có thứ tự cố định” | JVM có thể thay đổi số lượng/tên/thứ tự | Nhận dạng theo bean metadata, không theo index |
| “getHeapMemoryUsage.used = RSS” | Heap chỉ là một phần footprint | Dùng OS/container/native memory metrics khi cần |
| “MemoryUsage.max = -1 là không được cấp phát memory” | -1 nghĩa không xác định | Gắn trạng thái unavailable, không chia cho -1 |
| “GC collection time là p99 pause” | Tổng thời gian tích lũy không phải phân bố | Xem GC logs/JFR/histogram |
| “Thread count = request throughput” | Thread count là gauge | Xem request counter/rate và in-flight |
| “ProcessCpuTime = process CPU%” | Là CPU nanoseconds tích lũy | Lấy delta theo thời gian, chuẩn hóa cẩn thận |
| “Có platform MBeanServer là đã có JMX port” | MBeanServer local khác remote connector | Kiểm tra connector và bảo mật |
| “MBeanServer.getAttribute trả MemoryUsage” | MXBean qua JMX dùng OpenType mapping | Xử lý CompositeData hoặc dùng typed proxy |
| “Bật thread CPU time luôn miễn phí” | Có thể tạo overhead và thay đổi trạng thái đo | Kiểm tra support/permission/trước-sau |
| “DumpHeap chỉ là getter vô hại” | Có thể tốn tài nguyên, lộ dữ liệu | Approval/đánh giá impact |
| “JVM khác vendor chắc chắn có getProcessCpuLoad()” | Đây là extension, có thể thiếu/unsupported | Capability detection và fallback |
| “Đổi module JDK không ảnh hưởng deploy” | Custom runtime image có thể thiếu jdk.management | Kiểm tra jlink/module graph khi build |

## 15. Bài tập thực hành và đáp án

### Bài A – Chọn bean chuẩn

**Câu hỏi:** Bạn cần biết heap used, số thread live, uptime và available processors của một JVM Java 17. Có cần com.sun.management không?

**Đáp án:** Không. Dùng MemoryMXBean, ThreadMXBean, RuntimeMXBean và java.lang.management.OperatingSystemMXBean qua ManagementFactory. Đây là các interface chuẩn, đủ để đọc bốn số đo trên.

### Bài B – Một hay nhiều bean?

**Câu hỏi:** Vì sao gọi getPlatformMXBean(GarbageCollectorMXBean.class) không phù hợp, trong khi getPlatformMXBean(MemoryMXBean.class) hợp lý?

**Đáp án:** MemoryMXBean là singleton platform MXBean; GarbageCollectorMXBean là loại có thể có nhiều thực thể. Dùng getPlatformMXBeans(GarbageCollectorMXBean.class) hoặc getGarbageCollectorMXBeans().

### Bài C – Ranh giới API

**Câu hỏi:** Java code chỉ import java.lang.management.OperatingSystemMXBean nhưng gọi getProcessCpuTime(). Vì sao javac báo không có method?

**Đáp án:** Method thuộc interface com.sun.management.OperatingSystemMXBean trong module jdk.management, không nằm trong interface OS bean chuẩn. Cần JDK extension, module phù hợp, check implementation và xử lý -1 khi unsupported.

### Bài D – JMX OpenType

**Câu hỏi:** Trong cùng JVM, getHeapMemoryUsage() trả MemoryUsage nhưng MBeanServer.getAttribute("java.lang:type=Memory","HeapMemoryUsage") có thể trả CompositeData. Có phải lệch dữ liệu không?

**Đáp án:** Không. MXBean mapping chuyển type Java phức hợp sang JMX OpenType cho client; có thể dùng typed proxy để mapping thuận tiện.

### Bài E – Sentinel và phép toán

**Câu hỏi:** MemoryUsage.getMax() trả -1. Tính 100 × used/max để báo percent heap có hợp lệ không?

**Đáp án:** Không. Max chưa xác định, tỷ lệ không có ý nghĩa. Dùng metric khác hoặc biểu diễn “unknown” rõ ràng.

### Bài F – Delta GC

**Câu hỏi:** Collector A có collectionCount từ 120 lên 132 trong 60 giây không reset. Rate theo collector là bao nhiêu?

**Đáp án:** 12/60 = 0,2 collection/s. Kết quả không cho biết p95/p99 GC pause. Nếu một trong hai snapshot trả -1, không thể dùng công thức.

### Bài G – Tương thích runtime image

**Câu hỏi:** Dự án dùng module java.management, nhưng sau khi thêm import com.sun.management và đóng gói jlink image tối giản, service không khởi động. Khả năng nào cần kiểm tra?

**Đáp án:** Image có thể không chứa jdk.management; phải kiểm tra module graph và bản JVM, sau đó chọn đóng gói extension đúng cách hoặc tách adapter optional. Không coi lỗi module là JVM không có CPU metrics chuẩn.

### Bài H – Gỡ lỗi ở production

**Câu hỏi:** Một dashboard muốn lấy heap dump định kỳ mỗi 10 giây để “đo memory”. Có hợp lý không?

**Đáp án:** Không. Heap dump nặng và chứa dữ liệu nhạy cảm; dùng MemoryMXBean/MemoryPoolMXBean cho monitoring, chỉ dump có kiểm soát khi cần phân tích object retention.

### Bài I – JMX remote

**Câu hỏi:** Code gọi getPlatformMBeanServer() rồi không thấy cổng 9010 mở. Có phải bug?

**Đáp án:** Không. Lấy local MBeanServer không tự tạo remote JMX connector; muốn kết nối remote cần cấu hình connector an toàn theo chính sách môi trường.

### Bài J – CPU time và CPU load

**Câu hỏi:** ProcessCpuTime tăng 120 tỷ nanosecond trong 60 giây wall-clock. Giá trị 120 tỷ có phải “120% CPU” không?

**Đáp án:** Không. Tỷ lệ CPU-time/wall-time = \(120\,s / 60\,s = 2\) CPU-seconds/second trung bình; có thể là khoảng hai core dùng hết trong thời gian đó. Muốn biểu thị % phải định nghĩa denominator là một core, available processors hay quota, và xét cách runtime/OS đo.

## 16. Checklist lựa chọn API khi làm runtime diagnostics

Trước khi thêm một dòng đo MXBean vào service, hãy tự trả lời:

1. **Câu hỏi:** tôi cần gauge, counter, rate hay một phân bố?
2. **Chuẩn hay mở rộng:** có Java SE API trong java.lang.management trả lời đủ chưa?
3. **Module:** dự án có java.management; nếu dùng JDK extension có jdk.management trong runtime image không?
4. **Số lượng:** interface này singleton hay multi-instance? Có thể null/empty không?
5. **Đơn vị:** byte, millisecond, nanosecond, class, thread, load average hay tỷ lệ?
6. **Sentinel:** method có thể trả -1, null hoặc UnsupportedOperationException không?
7. **Thời gian:** snapshot của JVM nào, lúc nào, có process restart hoặc đổi GC không?
8. **Cost:** getter nhẹ hay operation thu stack/dumpHeap/thay đổi state?
9. **Bảo mật:** dữ liệu có thể nhạy cảm, JMX server có được bảo vệ, operation có phân quyền?
10. **Fallback:** khi extension không tồn tại, ta báo unavailable hay sử dụng metric khác?
11. **QA:** đã thử trên JDK/vendor/GC/container thực tế và so với log/JFR/OS metrics chưa?

Một báo cáo tốt không ghi “CPU=0 vì MXBean không hỗ trợ”; hãy ghi “process CPU metric unavailable” và tìm nguồn khác. Không ghi “GC time cao gây latency” nếu chưa có dữ liệu thời điểm, pause distribution và trace đối chứng.

## 17. Tài liệu tham khảo chính thức

- Java SE 17 – ManagementFactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 17 – OperatingSystemMXBean chuẩn: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- Java SE 17 – ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17 – MemoryUsage: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- Java SE 17 – GarbageCollectorMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html
- JDK 17 – package com.sun.management: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/package-summary.html
- JDK 17 – OperatingSystemMXBean extension: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- JDK 17 – HotSpotDiagnosticMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html

Đọc Javadoc đúng **version và implementation** của JVM đang chạy. Các loại bean, method và default behavior có thể tiến hóa theo JDK/VM.

## Ghi nhớ

**ManagementFactory** là cổng vào platform MXBeans. **java.management / java.lang.management** là nền tảng chuẩn để đọc memory, thread, runtime, operating system, class loading và GC. **jdk.management / com.sun.management** mở rộng thông tin chẩn đoán của JDK/HotSpot, có ích nhưng **không được mặc định portable**. Chọn interface chuẩn trước, kiểm tra capability và sentinel, phân biệt singleton/list, biết OpenType khi đi qua JMX, rồi tách các operation thay đổi trạng thái khỏi hoạt động giám sát. Chính sự rõ ràng về hợp đồng API, đơn vị và phạm vi runtime mới khiến số liệu MXBean trở thành bằng chứng đáng tin trong chẩn đoán Java.