# 7.2 Truy cập MXBean trực tiếp, qua MBeanServerConnection hoặc proxy

> **Java Advance – runtime-diagnostics** · **7. JMX**

## 1. Một dữ liệu quản lý JVM, ba cách truy cập

Khi cần biết heap đang dùng bao nhiêu byte, có bao nhiêu thread, hoặc garbage collector đã chạy mấy lần, Java cung cấp **platform MXBeans**. Cùng một MXBean có thể được truy cập theo nhiều đường, tùy code đang ở **ngay JVM đích** hay ở **một công cụ quan sát khác**, và bạn muốn làm việc bằng **interface Java có kiểu rõ ràng** hay bằng **ObjectName/attributes/operations của JMX**.

Ba cách trung tâm:

1. **Trực tiếp (direct):** gọi getter của *ManagementFactory* trong chính process Java, nhận một interface như *MemoryMXBean*, rồi gọi *getHeapMemoryUsage()*.
2. **Qua MBeanServerConnection (raw JMX):** dùng *ObjectName* để đọc attribute, lấy thông tin MBean hoặc gọi operation. Nếu attribute có kiểu Java phức hợp, dữ liệu có thể đã được ánh xạ thành *CompositeData* hay *TabularData*.
3. **Qua MXBean proxy (typed JMX):** nhận một object triển khai interface *MemoryMXBean* nhưng thực chất **chuyển tiếp** lời gọi đến một *MBeanServerConnection*. Proxy thực hiện ánh xạ kiểu MXBean thuận tiện hơn raw JMX.

**Điểm mấu chốt:** *direct bean*, *MBeanServerConnection* và *typed proxy* là **những đường truy cập**, không phải ba bộ số đo khác nhau. Dữ liệu có thể phát sinh từ cùng một bean, nhưng **chi phí**, **khả năng kết nối từ xa**, **cách biểu diễn giá trị**, **lỗi** và **ranh giới bảo mật** khác nhau.

Kết thúc bài này, bạn có thể:

- Phân biệt gọi MXBean trực tiếp với truy cập thông qua JMX transport.
- Hiểu *MBeanServer*, *MBeanServerConnection*, *JMXConnector*, *ObjectName* và *MXBean proxy*.
- Lấy đúng attribute *HeapMemoryUsage* qua JMX và xử lý dạng *CompositeData*.
- Tạo typed proxy bằng *ManagementFactory.getPlatformMXBean(connection, ...)* hoặc *newPlatformMXBeanProxy(...)*.
- Xử lý platform beans **một thực thể** so với **nhiều thực thể**.
- Viết chương trình Java 17+ độc lập minh họa ba đường truy cập, với stdout xác minh được.
- Dùng JMX remote khi được cấp phép, xử lý lỗi kết nối và tránh cấu hình management endpoint nguy hiểm.

## 2. Sơ đồ kiến trúc: bean, server, connector và client

~~~text
                        PROCESS JVM ĐÍCH
+------------------------------------------------------------------+
|                                                                  |
|  Code chạy trong cùng JVM                                        |
|        |                                                         |
|        | A. Gọi trực tiếp                                        |
|        v                                                         |
|  ManagementFactory.getMemoryMXBean()                             |
|        |                                                         |
|        v                                                         |
|  MemoryMXBean (số liệu heap JVM)                                 |
|        ^                                                         |
|        | đăng ký/quản lý qua ObjectName                            |
|        v                                                         |
|  Platform MBeanServer                                            |
|        ^                                                         |
|        | B. MBeanServerConnection local                           |
|        | C. MXBean proxy dùng connection local                    |
|        |                                                         |
+--------|---------------------------------------------------------+
         |
         | JMX Connector server (chỉ khi có cấu hình/phát hành)
         | giao thức + xác thực + mã hóa + phân quyền
         v
+------------------------------------------------------------------+
|  JVM hoặc máy khác: JMX client                                   |
|      JMXConnector.getMBeanServerConnection()                     |
|        |                                                         |
|        +--> B. getAttribute(ObjectName, "HeapMemoryUsage")       |
|        |       -> CompositeData                                  |
|        |                                                         |
|        +--> C. ManagementFactory.getPlatformMXBean(              |
|                 connection, MemoryMXBean.class)                  |
|                  -> typed proxy -> MemoryUsage                    |
+------------------------------------------------------------------+
~~~

Các đường trong hình cần được đọc đúng:

- **Direct** luôn đọc **JVM chứa đoạn code**. Lấy *ManagementFactory.getMemoryMXBean()* trên laptop không thể tự lấy heap của một service chạy trên server.
- **MBeanServerConnection** là interface chung cho thao tác đọc/ghi/duyệt MBeans. Nó có thể là *MBeanServer* trong cùng process hoặc proxy tới MBeanServer **qua kết nối JMX từ xa**.
- **Proxy** vẫn cần connection làm kênh chuyển tiếp. Proxy không tự vượt firewall, không tự thiết lập authentication, không tự biết URL đích và không làm biến mất độ trễ mạng.
- **Platform MBeanServer tồn tại cục bộ** không đồng nghĩa đã bật remote JMX listener. Các bước cấu hình connector, bảo mật và routing mạng hoàn toàn riêng.

### Từ API tới số đo

| Câu hỏi | Đường trực tiếp | Raw MBeanServerConnection | Typed MXBean proxy |
| --- | --- | --- | --- |
| Bean nào? | Getter, ví dụ *getMemoryMXBean()* | *ObjectName("java.lang:type=Memory")* | Interface/đúng ObjectName |
| Thao tác đọc heap | *getHeapMemoryUsage()* | *getAttribute(name, "HeapMemoryUsage")* | *getHeapMemoryUsage()* |
| Giá trị trả về | *MemoryUsage* | *CompositeData* qua OpenType mapping | *MemoryUsage* qua proxy mapping |
| Trong cùng JVM? | Có | Có thể | Có thể |
| Đọc JVM khác? | Không qua getter trực tiếp | Có, nếu connection remote | Có, nếu proxy dùng connection remote |
| Loại lỗi chính | Trạng thái/sự hỗ trợ bean, quyền JVM | Tên/attribute, JMX access, I/O nếu remote | Tương thích interface, JMX I/O, mapping và runtime exceptions |
| Khi nào nên dùng? | Instrumentation nội bộ | Tool linh hoạt cần khám phá MBeans | Client muốn Java API typed, ít tự parse OpenTypes |

Đường truy cập không thay đổi **đơn vị** của chỉ số. Ví dụ *MemoryUsage.getUsed()* vẫn tính bằng **byte** dù dữ liệu đi qua direct hay proxy.

## 3. Nền tảng: MBean, MXBean, OpenType và ObjectName

### 3.1 MBean và MXBean không phải hai process khác nhau

Trong JMX, một **MBean** là đối tượng quản lý có **attributes**, **operations** và có thể phát **notifications**. **MXBean** là biến thể có quy tắc ánh xạ Java types sang hệ **JMX OpenTypes**: kiểu cơ bản, array, *CompositeData*, *TabularData* và các type phù hợp khác.

Tại sao cần mapping? Client có thể chạy trên classpath hoặc JDK version khác với server. Nếu attribute trả một đối tượng Java tùy ý thuộc class của server, client có thể thiếu class để giải mã. OpenTypes cho phép trao đổi cấu trúc dữ liệu không phụ thuộc hoàn toàn vào class implementation riêng.

Với platform memory bean:

~~~text
Direct:
MemoryMXBean.getHeapMemoryUsage()
    -> java.lang.management.MemoryUsage

Raw JMX:
connection.getAttribute(
    ObjectName("java.lang:type=Memory"),
    "HeapMemoryUsage")
    -> javax.management.openmbean.CompositeData

Typed MXBean proxy:
proxy.getHeapMemoryUsage()
    -> java.lang.management.MemoryUsage
       (proxy ánh xạ CompositeData về kiểu Java)
~~~

**Không được cast** một *CompositeData* lấy từ raw JMX thẳng sang *MemoryUsage*. Nếu muốn tái tạo kiểu Java và đúng CompositeData mapping, dùng phương thức *MemoryUsage.from(CompositeData)* hoặc typed MXBean proxy. Nếu chỉ cần field *used*, *CompositeData.get("used")* cũng có thể trả *Long* để lấy byte.

### 3.2 ObjectName: địa chỉ logic của MBean trong server

Một MBean được nhận diện bằng **ObjectName** trong phạm vi một MBeanServer. Với MemoryMXBean chuẩn, định danh thường dùng và được đặc tả là:

~~~text
java.lang:type=Memory
~~~

Đây là **domain** *java.lang* và key property *type=Memory*; không phải Java package của bean, PID hay hostname. Hai JVM có thể đồng thời có bean cùng ObjectName vì chúng thuộc **hai MBeanServers/process khác nhau**.

Các ví dụ platform ObjectName thường gặp:

| Bean | ObjectName |
| --- | --- |
| MemoryMXBean | *java.lang:type=Memory* |
| RuntimeMXBean | *java.lang:type=Runtime* |
| ThreadMXBean | *java.lang:type=Threading* |
| ClassLoadingMXBean | *java.lang:type=ClassLoading* |
| OperatingSystemMXBean | *java.lang:type=OperatingSystem* |
| MemoryPoolMXBean | *java.lang:type=MemoryPool,name=<tên pool>* |
| GarbageCollectorMXBean | *java.lang:type=GarbageCollector,name=<tên collector>* |

Các tên có *name* là **phần thay đổi theo collector, pool và JVM**. Khi đã có bean, **ưu tiên bean.getObjectName()** thay vì tự ghép chuỗi có thể sai escaping/quoting. Với JMX discovery, có thể dùng một *ObjectName pattern* hợp lệ để tìm các bean hiện có.

*ObjectName* là danh tính của bean **trong server**; trong báo cáo chẩn đoán vẫn cần **host/pod/JVM instance/PID và timestamp** để xác định server nguồn. Không thể suy ra hai dòng thuộc cùng JVM chỉ vì đều có ObjectName *java.lang:type=Memory*.

### 3.3 Attribute và method không có cùng cú pháp tên

Từ getter Java *getHeapMemoryUsage()* của MemoryMXBean, JMX attribute tương ứng tên:

~~~text
HeapMemoryUsage
~~~

Do vậy:

~~~java
// Mảnh mã minh họa: giả định đã có connection và memoryName.
Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
~~~

Đúng hơn là gọi *getAttribute* với chuỗi *getHeapMemoryUsage()* hoặc *heapUsed*. Tên attribute **phân biệt hoa thường** và được mô tả trong MBeanInfo. Với boolean getter, properties và operation signatures, cần đọc hợp đồng JMX thay vì đoán mọi tên bằng cách bỏ tiền tố get.

Đọc danh sách attribute/operation được công bố bằng:

~~~java
// Mảnh mã minh họa: giả định connection và memoryName đã có.
javax.management.MBeanInfo info = connection.getMBeanInfo(memoryName);
// info.getAttributes(), info.getOperations() để khám phá metadata.
~~~

Không phải mọi Java method trên một class implementation đều là attribute JMX. MBeanServer chỉ công bố những thành viên theo hợp đồng quản lý của bean đã đăng ký.

## 4. Đường A: truy cập MXBean trực tiếp trong process

### 4.1 Cách đọc trong code Java

Trong chính JVM cần đo, bạn có thể viết:

~~~java
// Mảnh mã đặt trong một phương thức, không phải chương trình độc lập.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.getMemoryMXBean();

java.lang.management.MemoryUsage usage = memory.getHeapMemoryUsage();
long usedBytes = usage.getUsed();
~~~

Không cần URL, username, port JMX hay *JMXConnector*. Đây là cách thuận tiện cho:

- Health/diagnostic endpoints **nội bộ** có kiểm soát.
- Metrics exporter chạy **trong service**.
- Log định kỳ một số gauge/counter quản lý runtime.
- Đo trong unit/integration tests của Java process hiện tại.

**Cẩn thận:** nếu đoạn code chạy trong ứng dụng kiểm thử chứ không chạy trong JVM production, direct getter đọc JVM kiểm thử. Biến *memory* không chứa danh tính máy remote.

### 4.2 Các getter từ ManagementFactory

| API chuẩn | Giá trị phổ biến |
| --- | --- |
| *getMemoryMXBean()* | Heap, non-heap usage |
| *getThreadMXBean()* | Live/peak thread count, ThreadInfo và tính năng CPU time có điều kiện |
| *getRuntimeMXBean()* | Start time, uptime, input arguments, VM name |
| *getClassLoadingMXBean()* | Loaded/unloaded class counters |
| *getOperatingSystemMXBean()* | Processor count, OS name, load average nếu hỗ trợ |
| *getGarbageCollectorMXBeans()* | Danh sách collector, count/time theo collector |
| *getMemoryPoolMXBeans()* | Danh sách memory pools và usage |
| *getPlatformMBeanServer()* | Local MBeanServer; **không mở remote JMX port** |

Gọi bean trực tiếp là API có type-safe compile-time, nhưng **không đảm bảo mọi số đo luôn tồn tại**. Ví dụ *getSystemLoadAverage()* có thể cho giá trị âm báo unsupported; GC collection count/time có thể trả -1; MemoryUsage.getMax() có thể trả -1. Không biến sentinel thành 0 trên dashboard.

### 4.3 Các loại một instance và nhiều instance

**Singleton platform MXBeans:** MemoryMXBean, RuntimeMXBean, ThreadMXBean thường dùng *getPlatformMXBean(MemoryMXBean.class)* hoặc các getter riêng.

**Multi-instance platform MXBeans:** GarbageCollectorMXBean và MemoryPoolMXBean cần *getPlatformMXBeans(...)* (danh sách từ 0 đến nhiều phần tử).

~~~java
// Mảnh mã minh họa: chạy trong một phương thức.
var localPools = java.lang.management.ManagementFactory
        .getPlatformMXBeans(java.lang.management.MemoryPoolMXBean.class);
for (var pool : localPools) {
    System.out.println(pool.getObjectName());
}
~~~

Số lượng, thứ tự và tên memory pools phụ thuộc JVM/GC; **không có stdout cố định**. Không gọi *getPlatformMXBean(GarbageCollectorMXBean.class)* như thể GC có một bean duy nhất; API singleton chỉ dành cho những interface được đặc tả có tối đa một thực thể.

### 4.4 Đường direct cũng có chi phí

Đọc một số snapshot heap hoặc uptime thường nhẹ; nhưng một số method của ThreadMXBean có thể thu nhiều ThreadInfo/stack, khả năng đo contention cần bật hoặc có chi phí đáng kể. Không đặt *dumpAllThreads()* trong một HTTP request path cho hàng chục nghìn request/s chỉ vì đó là một method Java bình thường.

Quy tắc: chọn **mức đo phù hợp**, tần suất polling phù hợp và kiểm tra method có thao tác **thay đổi trạng thái** (ví dụ bật contention monitoring hoặc yêu cầu GC) trước khi gọi.

## 5. Đường B: MBeanServerConnection và cách truy cập thô

### 5.1 MBeanServerConnection là interface, không đồng nghĩa kết nối mạng

*javax.management.MBeanServerConnection* mô tả các thao tác như:

- *getAttribute(ObjectName, attributeName)*, *getAttributes(...)*: đọc attributes.
- *getMBeanInfo(ObjectName)*: hỏi metadata của MBean.
- *queryNames(ObjectName pattern, QueryExp query)*: khám phá danh sách ObjectNames.
- *isRegistered(ObjectName)*: kiểm tra MBean đang được đăng ký.
- *invoke(ObjectName, operation, arguments, signature)*: gọi operation.
- *setAttribute(...)* và một số method khác: **thay đổi trạng thái nếu quyền và MBean cho phép**.

**MBeanServerConnection không phải giao diện chỉ đọc.** Client nào có quyền phù hợp có thể gọi cả operation mang tác động; không để lộ một endpoint quản lý như thể nó chỉ cung cấp metrics.

Để lấy connection **local**:

~~~java
// Mảnh mã minh họa.
javax.management.MBeanServerConnection local =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
~~~

Điều này hợp lệ vì **MBeanServer triển khai MBeanServerConnection**. Các thao tác qua biến local vẫn đi qua JMX abstraction và OpenType conversion, nhưng không đi qua network. Cần phân biệt:

~~~text
ManagementFactory.getPlatformMBeanServer()
    -> local platform server, trong chính JVM.

connector.getMBeanServerConnection()
    -> connection đại diện cho server mà JMXConnector đang nối đến,
       có thể nằm trong JVM/process khác.
~~~

Tên interface giống nhau để code client có thể dùng được với cả hai, nhưng **failure mode và latency không giống nhau**.

### 5.2 Đọc MemoryMXBean theo ObjectName

~~~java
// Mảnh mã minh họa, cần hai biến đã khởi tạo.
javax.management.ObjectName memoryName =
        new javax.management.ObjectName("java.lang:type=Memory");

Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
javax.management.openmbean.CompositeData data =
        (javax.management.openmbean.CompositeData) raw;
long usedBytes = (Long) data.get("used");
~~~

Dòng *connection* có thể là local MBeanServerConnection hoặc remote. Nếu remote, việc đọc attribute là **một lượt truy cập tới JVM đích**; nếu connection mất, kết quả không thể được thay bằng 0 một cách an toàn.

Với *CompositeData*, các keys của *MemoryUsage* gồm *init*, *used*, *committed*, *max*. Phần tử có kiểu tương ứng OpenType; dùng *data.get("used")* để đọc byte.

Nếu muốn chuyển lại type Java chuẩn và mapping khớp hợp đồng:

~~~java
// Mảnh mã minh họa.
java.lang.management.MemoryUsage mapped =
        java.lang.management.MemoryUsage.from(data);
long used = mapped.getUsed();
~~~

Khi code chỉ cần một attribute đơn giản, raw JMX hữu ích. Khi phải đọc hàng loạt attributes có kiểu phức tạp, tự xử lý OpenTypes có thể phức tạp; một typed proxy thường giúp giảm lỗi mapping.

### 5.3 Khi nào cần queryNames?

Nếu không biết exact ObjectName — ví dụ một JVM có nhiều GarbageCollectorMXBeans — hãy **khám phá đối tượng đang đăng ký**:

~~~java
// Mảnh mã minh họa, có thể ném checked exceptions.
javax.management.ObjectName pattern =
        new javax.management.ObjectName("java.lang:type=GarbageCollector,*");
var names = connection.queryNames(pattern, null);
for (var objectName : names) {
    System.out.println(objectName.getCanonicalName());
}
~~~

Kết quả là tập ObjectNames trong MBeanServer được truy vấn; tên/order có thể khác giữa JVM. Đừng dựa vào thứ tự xuất ra để suy ra collector chính. **Một query thành công cũng chỉ nói về server của connection đó**, không nói về mọi JVM trên host.

Nếu client cần đọc *CollectionCount* của từng collector, có thể dùng *getAttribute* theo từng ObjectName. Nhưng với platform bean quen thuộc, typed API *ManagementFactory.getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* thường đơn giản hơn và ít phải tự xử lý ObjectName.

### 5.4 Exception khi truy vấn raw JMX

Những lỗi quan trọng:

| Lỗi/nhóm lỗi | Ý nghĩa có thể | Kiểm tra |
| --- | --- | --- |
| *MalformedObjectNameException* | Cú pháp tên không hợp lệ khi tạo ObjectName | Kiểm tra domain, key/value, escaping |
| *InstanceNotFoundException* | Không có bean theo ObjectName tại thời điểm truy vấn | Query names, kiểm tra đúng target |
| *AttributeNotFoundException* | Tên attribute sai hoặc bean không công bố | MBeanInfo, tên phân biệt hoa thường |
| *ReflectionException/MBeanException* | Vấn đề khi dispatch/thi hành operation hoặc method bean | Nội dung exception và contract của bean |
| *IOException* | Kết nối remote bị lỗi, server không đáp ứng hoặc transport có vấn đề | Endpoint, network, connector, TLS/auth, retry policy |
| *SecurityException/authorization failure* | Chính sách không cho phép truy vấn hoặc operation | Principal/permissions; không tắt bảo mật để thử |
| *ClassCastException* | Giả định sai kiểu raw OpenType | Inspect *CompositeType*/OpenData, dùng MXBean mapping đúng |

Một số method có checked exceptions đặc thù; đừng gom tất cả vào một catch rồi mặc định JVM đã chết. **Bean không tồn tại**, **connection hỏng** và **attribute không có** là ba tình huống khác nhau.

## 6. Đường C: typed MXBean proxy qua một connection

### 6.1 Factory proxy cho platform MXBeans

Khi có *MBeanServerConnection*, *ManagementFactory* cung cấp typed proxy:

~~~java
// Mảnh mã minh họa, cần connection đã có.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.getPlatformMXBean(
                connection, java.lang.management.MemoryMXBean.class);

if (memory != null) {
    long heapUsed = memory.getHeapMemoryUsage().getUsed();
}
~~~

Đối tượng *memory* ở đây có **interface MemoryMXBean** nhưng các method của nó được proxy **chuyển tiếp qua connection**. Nó không nhất thiết là object bean thực tế trong JVM gọi; nếu connection remote, chính JVM **đích** trả số đo.

*getPlatformMXBean(connection, Class<T>)* dành cho **singleton platform MXBean interfaces**, có thể trả null nếu interface có một instance tùy chọn mà server không triển khai. Trong trường hợp interface không thuộc platform hoặc không phải singleton, API có thể ném *IllegalArgumentException*. Với connection remote, factory có thể báo *IOException* khi truy vấn server.

### 6.2 Proxy theo ObjectName cụ thể

Nếu đã biết tên bean (ví dụ *memoryName*), dùng:

~~~java
// Mảnh mã minh họa, cần memoryName và connection.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.newPlatformMXBeanProxy(
                connection,
                memoryName.getCanonicalName(),
                java.lang.management.MemoryMXBean.class);
~~~

Khác biệt:

- *getPlatformMXBean(connection, MemoryMXBean.class)* chọn singleton platform bean theo **interface**, không cần truyền ObjectName thủ công.
- *newPlatformMXBeanProxy(connection, name, interface)* tạo proxy theo **ObjectName đã xác định**, hữu ích khi muốn cụ thể hóa đích và kiểm tra metadata.
- Cả hai đều truy cập qua *connection* và dùng **MXBean mapping** cho kiểu phức tạp.

Đừng dùng *newPlatformMXBeanProxy* tùy tiện cho bất kỳ custom MBean không tuân theo interface platform MXBean. Với MXBean do ứng dụng tự định nghĩa, JMX API có *JMX.newMXBeanProxy(connection, objectName, CustomMXBean.class)*; đó là use case khác, có hợp đồng riêng.

### 6.3 Tạo danh sách proxy cho multi-instance MXBeans

~~~java
// Mảnh mã minh họa.
var collectors = java.lang.management.ManagementFactory
        .getPlatformMXBeans(
                connection,
                java.lang.management.GarbageCollectorMXBean.class);

for (var gc : collectors) {
    System.out.println(gc.getName() + ": " + gc.getCollectionCount());
}
~~~

Mỗi phần tử đại diện cho một collector bean. **Không giả định danh sách có một phần tử hoặc tên G1/CMS/Shenandoah giống nhau giữa JDK.** API cho phép 0, 1 hoặc nhiều kết quả tùy interface/JVM; không cam kết thứ tự ổn định.

Đọc thuộc tính lần lượt qua nhiều proxies có thể phát sinh **nhiều lượt network**. Nếu dùng dashboard, phải tính chi phí polling theo số bean × số metric × tần suất × số JVM, tránh query thừa khi một server chậm.

### 6.4 Proxy có typed return không có nghĩa lấy snapshot nguyên tử

Lời gọi *memory.getHeapMemoryUsage()* tại thời điểm T1 và *raw getAttribute* tại T2 có thể trả **used bytes khác nhau** do ứng dụng allocation/GC đang chạy. Đó không phải lỗi proxy.

Tương tự, gọi *getHeapMemoryUsage()* rồi *getNonHeapMemoryUsage()* là hai snapshot gần nhau, không phải transaction hay event stream. Không viết test bắt ba đường phải cho giá trị byte **bằng tuyệt đối**. Đúng hơn nên kiểm tra type, khả năng đọc và các invariant như used/committed không âm.

### 6.5 Lỗi proxy có thể biểu hiện khác raw JMX

Một method trên interface *MemoryMXBean* không nhất thiết khai báo checked *IOException*. Tuy nhiên proxy dùng *MBeanServerConnection* có thể gặp I/O trong quá trình forwarding. Tùy lời gọi, exception có thể được đóng gói trong runtime wrapper của dynamic proxy (ví dụ *UndeclaredThrowableException*). Vì vậy khi viết JMX client cần:

- Xử lý lỗi khi **tạo và sử dụng connection/proxy**, không chỉ lúc *connect()*.
- Lưu nguyên nhân gốc có kiểm soát, phân biệt endpoint không tới được với bean/attribute không có.
- Có timeout/retry/backoff/circuit breaker phù hợp, không retry vô hạn request chẩn đoán vào JVM đang yếu.
- Giữ code chính xác theo các exceptions mà Javadoc của phương thức cụ thể công bố.

Không nên catch mọi *RuntimeException* rồi gán giá trị metric 0; khi mất connectivity dashboard sẽ báo sai tình trạng.

## 7. Lab độc lập Java 17+: ba đường truy cập cùng JVM

Lab này chứng minh ba đường trên **trên local platform MBeanServer**, nên **không cần mở cổng JMX, không cần tài khoản và không cần thư viện bên ngoài**. Mục đích là kiểm chứng **dạng trả về và đường API**, không khẳng định việc kết nối từ xa cũng được bảo đảm.

Tạo file **MxBeanThreePathsDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class MxBeanThreePathsDemo {
    public static void main(String[] args) throws Exception {
        MemoryMXBean direct = ManagementFactory.getMemoryMXBean();
        MBeanServerConnection connection = ManagementFactory.getPlatformMBeanServer();
        ObjectName memoryName = direct.getObjectName();

        Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
        CompositeData data = (CompositeData) raw;
        long rawUsed = (Long) data.get("used");

        MemoryMXBean typed = ManagementFactory.getPlatformMXBean(
                connection, MemoryMXBean.class);
        MemoryMXBean named = ManagementFactory.newPlatformMXBeanProxy(
                connection, memoryName.getCanonicalName(), MemoryMXBean.class);

        List<MemoryPoolMXBean> localPools = ManagementFactory.getMemoryPoolMXBeans();
        List<MemoryPoolMXBean> proxiedPools = ManagementFactory.getPlatformMXBeans(
                connection, MemoryPoolMXBean.class);

        System.out.println("objectName=" + memoryName);
        System.out.println("rawIsCompositeData=" + (raw instanceof CompositeData));
        System.out.println("rawUsedNonnegative=" + (rawUsed >= 0));
        System.out.println("directUsedNonnegative="
                + (direct.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("typedUsedNonnegative="
                + (typed.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("namedUsedNonnegative="
                + (named.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("typedNameMatches=" + typed.getObjectName().equals(memoryName));
        System.out.println("namedNameMatches=" + named.getObjectName().equals(memoryName));
        System.out.println("localPoolsAvailable=" + !localPools.isEmpty());
        System.out.println("proxiedPoolsAvailable=" + !proxiedPools.isEmpty());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 MxBeanThreePathsDemo.java
java MxBeanThreePathsDemo
~~~

**Stdout của chương trình trên JVM Java 17+ thông dụng:**

~~~text
objectName=java.lang:type=Memory
rawIsCompositeData=true
rawUsedNonnegative=true
directUsedNonnegative=true
typedUsedNonnegative=true
namedUsedNonnegative=true
typedNameMatches=true
namedNameMatches=true
localPoolsAvailable=true
proxiedPoolsAvailable=true
~~~

Đã biên dịch/chạy ví dụ trên JDK và xác nhận 10 dòng stdout như trên. Các kiểm tra boolean tránh phụ thuộc vào số byte của heap và số pool (luôn biến đổi theo tải/VM); nếu môi trường Java SE bất thường không có pool hoặc vi phạm giả định hỗ trợ, những kiểm tra cuối có thể khác. **Không nên coi chuỗi stdout là đặc tả bắt buộc trên mọi VM implementation.**

### Giải thích từng nhánh code

**Nhánh direct**

~~~java
MemoryMXBean direct = ManagementFactory.getMemoryMXBean();
~~~

Chính process Java đang chạy class demo là mục tiêu đo.

**Nhánh raw**

~~~java
Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
CompositeData data = (CompositeData) raw;
long rawUsed = (Long) data.get("used");
~~~

Lấy dữ liệu qua MBeanServerConnection và nhận **OpenType**. Thao tác chỉ đọc một attribute. Không có cast *MemoryUsage* trực tiếp từ raw.

**Nhánh typed (singleton interface)**

~~~java
MemoryMXBean typed = ManagementFactory.getPlatformMXBean(
        connection, MemoryMXBean.class);
~~~

Tạo interface/proxy typed cho platform memory bean thông qua connection. Trong chương trình, connection là local. Nếu thay bằng connection remote phù hợp, **logic typed proxy tương tự** nhưng lỗi/kết nối/quyền phải xử lý riêng.

**Nhánh named proxy**

~~~java
MemoryMXBean named = ManagementFactory.newPlatformMXBeanProxy(
        connection, memoryName.getCanonicalName(), MemoryMXBean.class);
~~~

Chọn bean theo **ObjectName cụ thể**, thay vì để factory chọn từ interface singleton.

**Nhánh danh sách**

~~~java
List<MemoryPoolMXBean> proxiedPools = ManagementFactory.getPlatformMXBeans(
        connection, MemoryPoolMXBean.class);
~~~

Chứng minh với những platform bean **multi-instance** bạn dùng danh sách typed proxies, không cố tìm một bean duy nhất.

### Các điều lab không chứng minh

- Không chứng minh JMX remote đã mở hoặc đã bảo mật. Code chỉ dùng local platform MBeanServer.
- Không chứng minh ba số *used* lấy cùng lúc; chúng được đọc nối tiếp.
- Không chứng minh mọi implementation có cùng GC/pool names/count.
- Không kiểm tra mọi operations trên MBeanServerConnection đều read-only.
- Không đánh giá overhead khi chạy trên hàng nghìn JVM; muốn benchmark cần thử dưới workload thực.

Lab đã đủ để thấy **khác biệt về API và kiểu dữ liệu**, sau đó mới nghiên cứu kết nối remote thực sự.

## 8. Truy cập một JVM khác: JMXConnector và MBeanServerConnection remote

### 8.1 Kết nối remote xuất hiện ở đâu?

Trong môi trường có remote JMX connector **được cấu hình hợp lệ và bảo vệ đầy đủ**, client có thể dùng:

~~~text
JMXServiceURL
     |
JMXConnectorFactory.connect(url, environment)
     |
JMXConnector
     |
getMBeanServerConnection()
     |
MBeanServerConnection (tới JVM đích)
     |
getAttribute(...) hoặc platform MXBean proxy
~~~

*JMXServiceURL* là địa chỉ **JMX connector**, không phải URL HTTP của endpoint ứng dụng. Một URL RMI có thể dùng scheme *service:jmx:rmi:///jndi/rmi://host:port/name*; địa chỉ cụ thể, port mapping, DNS, server endpoint và TLS/auth do hệ thống triển khai quyết định.

Đặc biệt với RMI, cần hiểu **RMI registry port** và **RMI server endpoint** có thể không trùng nhau. Trong Docker/Kubernetes/NAT, chỉ mở một port mà không cấu hình server hostname/port phù hợp có thể khiến client lấy được stub nhưng không kết nối tiếp được. Đừng “chữa” bằng cách tắt authentication hoặc TLS.

### 8.2 Minh họa client remote an toàn về cấu trúc

Phần code bên dưới là **mảnh mã, không phải chương trình độc lập**: nó giả định *url* là *JMXServiceURL* hợp lệ đến endpoint đã được đội vận hành cho phép, và *environment* là *Map<String, ?>* do lớp kết nối an toàn cấp (ví dụ thông tin xác thực/TLS/connector configuration thích hợp). Không chứa credential hardcode, không tự bật server hay vô hiệu bảo mật:

~~~java
// Mảnh mã nằm trong phương thức có checked exceptions.
// url: JMXServiceURL đến connector đã được quản lý.
// environment: Map<String, ?> cấu hình kết nối an toàn có sẵn.
try (javax.management.remote.JMXConnector connector =
        javax.management.remote.JMXConnectorFactory.connect(url, environment)) {
    javax.management.MBeanServerConnection remote =
            connector.getMBeanServerConnection();

    java.lang.management.MemoryMXBean memory =
            java.lang.management.ManagementFactory.getPlatformMXBean(
                    remote, java.lang.management.MemoryMXBean.class);

    if (memory != null) {
        long usedBytes = memory.getHeapMemoryUsage().getUsed();
        // Ghi nhận usedBytes cùng danh tính JVM đích và thời điểm.
    }
}
~~~

**Một số lưu ý bắt buộc:**

- Đây **không** phải ví dụ chạy standalone: chưa có endpoint, DNS, protocol, credential/TLS config. Mục đích là minh họa **cách dùng connection sau khi đã được cấp an toàn**.
- *JMXConnector* cần được đóng để giải phóng tài nguyên, ở đây dùng *try-with-resources*.
- Mở connection không bảo đảm mọi getter sau đó thành công; JVM target có thể restart, mạng rớt, quyền bị thu hồi hoặc server quá tải.
- Kết quả phải gắn với **identity của target** (host/pod/JVM start time) chứ không chỉ tên ObjectName.
- Không đưa password vào ví dụ command line hoặc log credential; không tắt SSL/authentication cho tiện thử trên production.

**Thiết kế bảo mật:** hạn chế network reachability, bật authentication và TLS đúng chính sách, cấp quyền tối thiểu, ghi audit. JMX remote có khả năng truy cập operations quản trị; một username chỉ dùng để “xem số đo” cần phân quyền chứ không được mặc định toàn quyền. Nếu cần chẩn đoán từ máy vận hành, ưu tiên kênh truy cập quản trị được phê duyệt thay vì expose JMX trên Internet.

### 8.3 Local JMX và remote JMX không phải cùng lỗi

| Tình trạng | Local connection | Remote connection |
| --- | --- | --- |
| Tạo connection | *getPlatformMBeanServer()* | Thường qua *JMXConnectorFactory.connect()* |
| Vấn đề mạng | Không cần network | DNS, firewall, NAT, RMI/TLS, timeout |
| Auth/authorization | Quyền process/JMX policy local | Connector authentication, TLS và quyền MBean |
| JVM restart | Mất process/dữ liệu local | Stale connection, reconnect có kiểm soát |
| Overhead | Tùy bean/mapping | Mapping + marshalling + network + round trips |
| Chỉ số động | Snapshot thay đổi | Snapshot thay đổi và có thêm network delay |
| Lỗi ObjectName/attribute | Có thể có | Có thể có, cộng thêm connection failures |

**Một phép thử local thành công không phải bằng chứng remote production sẽ thành công.** Cần kiểm tra server endpoint, user/role, TLS, routing mạng và version tương thích ở môi trường thực.

## 9. Chọn đường nào cho từng nhu cầu?

| Tình huống | Ưu tiên | Lý do |
| --- | --- | --- |
| Exporter chạy bên trong service đo heap/thread | Direct platform MXBean | Không phải quản lý connection, type-safe |
| Internal actuator/health có vài số đo JVM | Direct, nếu endpoint có policy phù hợp | Đơn giản, tránh overhead JMX transport |
| JMX client tổng quát cần list bean và metadata | Raw MBeanServerConnection | *queryNames*, *getMBeanInfo*, khám phá runtime |
| Dashboard Java biết rõ cần MemoryMXBean | Typed proxy | *getHeapMemoryUsage()* trả *MemoryUsage*, giảm tự parse OpenType |
| Muốn tham chiếu bean có ObjectName cụ thể | *newPlatformMXBeanProxy()* | Điều khiển identity của bean |
| Cần danh sách collectors/pools trên JVM remote | *getPlatformMXBeans(connection, Interface.class)* | Không đoán số lượng/tên, typed list |
| Custom MXBean do ứng dụng tự đăng ký | Raw JMX hoặc *JMX.newMXBeanProxy()* | Không nhất thiết là platform interface |
| JVM/OS/JDK vendor không hỗ trợ một bean extension | Chuẩn trước, capability check rồi fallback | Portable và tránh ClassNotFound/NoClassDefFoundError |
| Muốn heap dump, thay VM option hoặc trigger GC | Quy trình chẩn đoán riêng, có phê duyệt | Không coi là getter monitoring nhẹ |

Không có một cách “nhanh nhất” tuyệt đối. Với code chạy cùng JVM và vài getter, direct thường đơn giản nhất. Với công cụ generic, MBeanServerConnection là nền tảng; với client ứng dụng muốn kiểu mạnh, proxy tiện hơn. Nhưng chi phí remote phụ thuộc số method calls và network, không chỉ việc tạo proxy.

## 10. Những khác biệt dễ mắc lỗi khi lập trình

### 10.1 Lấy object typed từ connection không phải lấy bean local

Hai dòng có kiểu đều là *MemoryMXBean* nhưng khác nơi lấy dữ liệu:

~~~java
// Mảnh mã minh họa.
var local = java.lang.management.ManagementFactory.getMemoryMXBean();
var viaConnection = java.lang.management.ManagementFactory
        .getPlatformMXBean(connection, java.lang.management.MemoryMXBean.class);
~~~

Nếu connection remote, *viaConnection* đo JVM **đích**, còn *local* đo JVM **đang chạy client**. Đừng gộp hai kết quả làm một series mà không ghi instance. Đây là lỗi thường gặp khi thử code trong local IDE rồi port sang monitoring backend.

### 10.2 Raw getAttribute trả kiểu OpenType

Sai:

~~~java
// Mã sai: CompositeData không thể cast trực tiếp thành MemoryUsage.
java.lang.management.MemoryUsage usage =
        (java.lang.management.MemoryUsage)
        connection.getAttribute(memoryName, "HeapMemoryUsage");
~~~

Đúng:

~~~java
// Mảnh mã minh họa.
javax.management.openmbean.CompositeData data =
        (javax.management.openmbean.CompositeData)
        connection.getAttribute(memoryName, "HeapMemoryUsage");
java.lang.management.MemoryUsage usage =
        java.lang.management.MemoryUsage.from(data);
~~~

Hoặc dùng *MemoryMXBean* typed proxy để proxy xử lý mapping.

### 10.3 Không phải mọi bean là singleton

Sai: cố đọc *GarbageCollectorMXBean* qua singleton platform MXBean getter.

Đúng: gọi *ManagementFactory.getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* hoặc getter danh sách trong local JVM.

GC/MemoryPool names có thể thay đổi theo G1, Parallel, ZGC, Shenandoah, JDK version hoặc vendor; tuyệt đối không hardcode “collector thứ hai luôn là Old GC”.

### 10.4 ObjectName không phải URL process và không duy nhất giữa các JVM

*java.lang:type=Memory* chỉ định memory bean **trong một MBeanServer**. Nếu client giữ hai MBeanServerConnections tới hai JVM khác nhau, cùng ObjectName đó đại diện cho hai bean **ở hai nơi khác nhau**. Luôn gắn host/container/process start time khi lưu metrics.

### 10.5 Tạo proxy không đảm bảo bean tồn tại ở mọi lúc

Một số platform beans tùy chọn có thể vắng mặt, và multi-instance beans có thể thay đổi theo runtime. Trước khi lấy thuộc tính, kiểm tra null/empty như hợp đồng API quy định, hoặc *isRegistered* với ObjectName cụ thể khi cần. Nhưng **kiểm tra trước không loại bỏ race condition**: bean có thể biến mất sau *isRegistered*. Cần xử lý lỗi ở thao tác thực tế.

### 10.6 Thao tác JMX có thể thay đổi JVM

Các method *invoke*, *setAttribute* và một số MXBean operations có thể là control plane. Ví dụ yêu cầu GC, bật thread contention monitoring hoặc thao tác diagnostic HotSpot có thể gây overhead/rủi ro. Không trao cho một dashboard chỉ cần *getAttribute* quyền gọi mọi operation. Phân quyền JMX tùy connector/chính sách, không tự nhận interface là read-only.

### 10.7 JMX remote lỗi có thể nằm sâu trong dynamic proxy

Một typed proxy gọi method không khai báo checked IOException, nhưng bên dưới connection remote có I/O. Một số lỗi có thể được bọc bởi dynamic proxy wrapper. Ghi log nguyên nhân gốc có chọn lọc, lưu endpoint identifier, không gộp lỗi kết nối và sentinel metric.

### 10.8 Java SE API và phần mở rộng JDK không đồng nhất

MemoryMXBean thuộc *java.lang.management* là chuẩn; một số thông tin process CPU/GC chuyên sâu nằm trong *com.sun.management* (module *jdk.management*). Một interface JDK extension không được bảo đảm có trên mọi vendor/runtime image. Đừng suy ra chỉ cần *ManagementFactory* là mọi extension đều có mặt. Hãy thiết kế fallback, không ép kiểu không kiểm tra.

## 11. Đọc metrics đúng ý nghĩa, không chỉ lấy được giá trị

Có connection và code đúng vẫn chưa chắc metric có ý nghĩa.

### 11.1 Snapshot không đồng bộ

Trong lab, *direct*, *raw*, *typed*, *named* đọc heap used **theo thứ tự**. GC/allocation giữa các lượt có thể làm số byte đổi. Không assert bằng tuyệt đối, nhất là qua remote.

Nếu muốn biểu đồ theo thời gian, lấy timestamp cùng mỗi lần đo và giữ identity của JVM; không dùng timestamp collector làm timestamp event nếu cần phân tích pause rất ngắn.

### 11.2 Các loại số đo khác nhau

| MXBean method | Đơn vị/loại | Lưu ý |
| --- | --- | --- |
| *MemoryUsage.getUsed()* | byte / gauge | Heap/non-heap phạm vi bean, không phải process RSS |
| *MemoryUsage.getCommitted()* | byte / gauge | Bộ nhớ đã cam kết, khác used |
| *MemoryUsage.getMax()* | byte hoặc -1 | -1 nghĩa là giới hạn không xác định |
| *ThreadMXBean.getThreadCount()* | thread / gauge | Không phải request throughput |
| *RuntimeMXBean.getUptime()* | millisecond / elapsed time | Reset khi JVM restart |
| *GarbageCollectorMXBean.getCollectionCount()* | count hoặc -1 | Counter tích lũy nếu được hỗ trợ |
| *GarbageCollectorMXBean.getCollectionTime()* | millisecond hoặc -1 | Không bằng p99 GC pause |
| *ClassLoadingMXBean.getTotalLoadedClassCount()* | count | Counter tích lũy; khác số lớp hiện đang loaded |
| *OperatingSystemMXBean.getSystemLoadAverage()* | load average hoặc âm | Không phải CPU% và có thể unavailable |

Counter cần tính delta/rate trên **cùng instance** và xử lý restart. Không lấy delta của GC count trước restart và sau restart rồi gọi kết quả âm là “GC chạy âm lần”. Sentinel -1/null không được đưa vào dashboard như giá trị 0. Dữ liệu từ bean chuẩn vẫn cần diễn giải, sampling và metadata rõ ràng.

### 11.3 Chi phí remote và N+1 calls

Ví dụ một monitoring client poll 200 JVM, mỗi JVM đọc 15 attributes, cứ 5 giây. Trong mô hình thô, có thể phát sinh khoảng **3.000 attribute reads mỗi chu kỳ** chưa tính connect/metadata/retry. Không thể suy ra mỗi read là một kết nối TCP mới, nhưng số round trip và lượng serialized data có thể rất lớn.

Các hướng tối ưu:

- Chọn bộ metrics thật sự cần; tránh query mọi MBean để làm một gauge.
- Sử dụng *getAttributes* có kiểm tra kết quả nếu phù hợp để giảm overhead so với đọc lẻ quá nhiều attributes.
- Cache metadata/ObjectNames hợp lý nhưng refresh sau restart/reconfiguration; **không cache số đo** như thể không đổi.
- Batch theo server, giới hạn concurrency, đặt timeout/backoff và giám sát collector errors.
- Đọc histogram/GC logs/JFR cho những câu hỏi cần phân bố sự kiện; MXBean tổng tích lũy không thay thế chúng.
- Nếu hệ thống đã có Prometheus/OpenTelemetry exporter nội bộ phù hợp, không nhất thiết mở một cổng JMX remote mới.

## 12. Quy trình chẩn đoán khi ba đường cho kết quả khác nhau

Giả sử direct getter trong service báo heap used, còn dashboard JMX remote báo một số khác. **Đừng kết luận proxy sai ngay.**

### Bước 1 – Kiểm tra đúng JVM

- Direct code nằm ở JVM nào?
- URL remote trỏ đến pod/host/JVM nào?
- Process đã restart giữa hai snapshot không?
- Có load balancer, sidecar hoặc registry nhầm target không?

Hai bean cùng tên *java.lang:type=Memory* trên hai JVM khác nhau có thể cho số liệu hoàn toàn khác.

### Bước 2 – Kiểm tra cùng metric và đơn vị

- *HeapMemoryUsage* hay *NonHeapMemoryUsage*?
- *used*, *committed*, *init* hay *max*?
- Byte hay MiB? \(1\,\mathrm{MiB}=1{,}048{,}576\) byte.
- Thời điểm đọc có gần nhau? GC diễn ra giữa hai phép đo không?

### Bước 3 – Kiểm tra raw OpenType mapping

- Raw *getAttribute* có trả *CompositeData* như hợp đồng không?
- Field *used* có kiểu *Long* và đơn vị byte không?
- Code có cast sai *CompositeData → MemoryUsage* không?
- Proxy có tương thích client/server JDK version không?

### Bước 4 – Kiểm tra connectivity/authorization

- Có remote JMX connector thật không?
- Protocol/hostname/RMI endpoint/port/TLS/auth có đúng?
- Tài khoản có quyền đọc đúng MBean không?
- Remote server có còn sống? Lỗi chỉ xuất hiện khi JVM quá tải không?

### Bước 5 – Kiểm tra cách app xử lý lỗi

- Có đang đổi *IOException* thành 0 không?
- Có dùng cache dữ liệu cũ mà không đánh dấu stale không?
- Có retry liên tục khiến target tăng tải không?
- Có gộp nhiều JVM vào một series thiếu instance label không?

**Kết luận đúng:** Nếu raw và proxy dùng **cùng connection + ObjectName + thời điểm đủ gần**, chúng thường phải tuân cùng hợp đồng giá trị; sai khác nhỏ về số bytes có thể là snapshot timing. Nếu cùng thời điểm chỉ một đường bị lỗi, hãy xem mapping, access policy, hoặc exception cụ thể thay vì suy đoán.

## 13. Các bài tập thực hành có lời giải

### Bài 1 – Phân loại ba câu lệnh

**Cho:**

~~~java
// Mảnh mã minh họa.
var a = java.lang.management.ManagementFactory.getMemoryMXBean();
var b = connection.getAttribute(memoryName, "HeapMemoryUsage");
var c = java.lang.management.ManagementFactory.getPlatformMXBean(
        connection, java.lang.management.MemoryMXBean.class);
~~~

**Hỏi:** Dòng nào luôn đọc JVM chứa code? Dòng nào có thể đọc JVM remote?

**Đáp án:** *a* là direct bean của JVM hiện tại. *b* là raw JMX, *c* là typed MXBean proxy; cả *b* và *c* truy cập JVM mà **connection** trỏ tới, có thể local hoặc remote.

### Bài 2 – Nhận dạng kiểu dữ liệu

**Hỏi:** Tại sao một method khai báo trả *MemoryUsage* lại cho giá trị *CompositeData* khi đọc qua raw JMX?

**Đáp án:** MXBean chuyển Java value thành JMX OpenType khi dùng giao diện MBeanServer. Typed MXBean proxy chuyển về kiểu Java. Có thể parse *CompositeData* hoặc dùng *MemoryUsage.from()*.

### Bài 3 – Không thấy CPU từ OperatingSystemMXBean

**Hỏi:** Bạn gọi *java.lang.management.OperatingSystemMXBean* rồi muốn *getProcessCpuTime()* nhưng javac không tìm thấy method. Có phải do dùng proxy?

**Đáp án:** Không. *getProcessCpuTime()* thuộc interface mở rộng *com.sun.management.OperatingSystemMXBean* của JDK, không nằm trong interface Java SE chuẩn. Cần module/vendor tương thích và fallback; đổi direct sang proxy không tự thêm method vào interface chuẩn.

### Bài 4 – Đọc GarbageCollectorMXBean từ JVM remote

**Hỏi:** Vì sao không dùng *getPlatformMXBean(connection, GarbageCollectorMXBean.class)*?

**Đáp án:** GC collectors có thể nhiều bean; method singleton không phù hợp. Dùng *getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* và lặp qua list, không phụ thuộc index.

### Bài 5 – Local MBeanServer

**Hỏi:** Chương trình đã gọi *ManagementFactory.getPlatformMBeanServer()*. Có chắc JMX client máy khác kết nối tới được không?

**Đáp án:** Không. Nó chỉ cung cấp local server. Remote access đòi connector/service URL và cấu hình bảo mật/mạng riêng.

### Bài 6 – Cast sai

**Hỏi:** Phép cast trực tiếp *MemoryUsage usage=(MemoryUsage) connection.getAttribute(...)* thường gây lỗi gì?

**Đáp án:** Runtime *ClassCastException* khi raw attribute là *CompositeData*. Phải parse OpenType hoặc dùng typed proxy.

### Bài 7 – Lỗi từ remote proxy

**Hỏi:** *JMXConnectorFactory.connect()* thành công, nhưng vài phút sau *proxy.getHeapMemoryUsage()* lỗi. Tại sao?

**Đáp án:** Kết nối có thể mất sau khi tạo, JVM restart, firewall/NAT timeout, permission thay đổi hoặc server không đáp ứng. Proxy vẫn dùng remote connection mỗi lần gọi; cần xử lý lỗi runtime và reconnect/backoff có kiểm soát.

### Bài 8 – Hai số heap khác nhau

**Hỏi:** Direct đọc 120 MiB, raw đọc 116 MiB, proxy đọc 118 MiB. Có chứng minh một API sai?

**Đáp án:** Không. JVM allocation/GC có thể diễn ra giữa các snapshot. Cần xem timestamp, cùng instance và cùng trường *used*. Không viết test giả định ba lần đọc phải bằng nhau.

### Bài 9 – Tên ObjectName có phân biệt process?

**Hỏi:** Hai JVM đều có *java.lang:type=Memory*. Có phải cùng MXBean object trên một máy?

**Đáp án:** Không. ObjectName là tên trong phạm vi mỗi MBeanServer. Phải gắn endpoint/JVM identity để phân biệt.

### Bài 10 – Kiểm soát quyền

**Hỏi:** Dashboard chỉ cần heap used nhưng được cấp mọi JMX operation, kể cả yêu cầu GC và dump heap. Đây có phải “monitoring read-only” không?

**Đáp án:** Không. Quyền quản trị đang quá rộng; tách truy cập chỉ đọc, giới hạn operations và bảo vệ transport/authentication/TLS.

### Bài 11 – Tính tốc độ từ GC MXBean

**Hỏi:** Một collector có *CollectionCount* tăng từ 40 lên 70 trong 150 giây, không restart, hai snapshot đều hợp lệ. Tốc độ trung bình là bao nhiêu?

**Đáp án:** \((70-40)/150=0{,}2\) collection/s. Số này không cung cấp p99 pause; cần GC logs/JFR hoặc dữ liệu phân bố.

### Bài 12 – QueryNames trả nhiều MBeans

**Hỏi:** *queryNames("java.lang:type=MemoryPool,*")* cho 8 names. Có nên ghi “memoryPool1...memoryPool8” dựa trên thứ tự set?

**Đáp án:** Không. Thứ tự không có hợp đồng ổn định. Dùng ObjectName/canonical name, tên pool và loại memory để nhận dạng; dữ liệu có thể khác ở lần chạy sau.

## 14. Checklist thực tế trước khi triển khai JMX monitoring

**Tầng target**

- JVM thực tế là JVM nào? Đã biết host, PID hoặc pod/container và thời điểm khởi động?
- Bean/interface được Java SE bảo đảm hay là extension theo vendor/JDK?
- Singleton hay multi-instance? Đã xử lý null/empty/-1/unsupported?
- ObjectName/attribute có tồn tại theo *getMBeanInfo* hoặc hợp đồng standard?

**Tầng connection**

- Direct đang ở JVM cần đo hay đang chạy bên client?
- Connection là **local MBeanServer** hay **JMXConnector remote**?
- Khi remote, endpoint, RMI port mapping, firewall, TLS, authentication và authorization có đúng?
- Client có đóng connector và giới hạn concurrency/retry không?

**Tầng dữ liệu**

- Raw trả OpenType gì? Có parse CompositeData đúng schema không?
- Proxy có interface compatible và mapping đúng không?
- Giá trị dùng đơn vị nào, là gauge hay counter, có cần delta?
- Timestamp và instance labels có đủ để đối chiếu giữa các lần đo không?
- Có phân biệt metric unavailable với 0 và stale data với fresh data?

**Tầng vận hành và an toàn**

- Frequency, overhead và round trips có hợp lý dưới tải cao?
- Có log exception gốc nhưng không lộ credential/secret?
- Endpoint JMX remote không bị public/expose quá rộng?
- Dashboard chỉ cần getter có được phân quyền tránh state-changing operations?
- Có đường đối chứng bằng app metrics, GC logs, JFR hoặc OS metrics khi cần?

## 15. Tài liệu chính thức nên tra cứu theo JDK đang sử dụng

- **ManagementFactory — Java SE 17**, direct getters, local/remote platform MXBean proxy và multi-instance: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- **MemoryMXBean — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- **MemoryUsage — Java SE 17**, gồm *from(CompositeData)*: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- **MBeanServerConnection — Java SE 17**, getAttribute/queryNames/getMBeanInfo/invoke: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanServerConnection.html
- **JMX — Java SE 17**, mapping OpenTypes và typed MXBean proxies: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/JMX.html
- **CompositeData — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/openmbean/CompositeData.html
- **JMXConnectorFactory — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- **JMX remote API — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/package-summary.html
- **Oracle JMX Security — Java SE 17**: https://docs.oracle.com/en/java/javase/17/jmx/security.html

Khả năng và chính sách JMX remote phụ thuộc JDK version, vendor, runtime flags, connector và cấu hình bảo mật thực tế. Đối chiếu tài liệu với chính môi trường bạn cần chẩn đoán.

## Kết luận

**Direct MXBean** thích hợp khi code ở **cùng JVM** và muốn gọi getter với kiểu Java rõ ràng. **MBeanServerConnection** cung cấp cách truy cập tổng quát bằng *ObjectName, attribute và operation*; có thể local hoặc remote. **Typed MXBean proxy** nằm trên một connection và chuyển các lời gọi thành dạng interface Java thuận tiện, tự xử lý mapping MXBean nhưng **không loại bỏ** network I/O, authorization, timeout hay rủi ro vận hành.

Một phép đo đáng tin cần đủ **đúng JVM đích, đúng bean, đúng attribute/đơn vị, đúng thời điểm và đúng quyền**. Chọn đường truy cập theo vị trí code và nhu cầu khám phá/typing, không dựa chỉ vào việc lệnh biên dịch được.