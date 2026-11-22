# ManagementFactory và truy cập các MXBean nền tảng

## 1. Từ câu hỏi vận hành đến giao diện giám sát JVM

Khi một ứng dụng Java chạy lâu, ta cần trả lời những câu hỏi như: JVM đã chạy bao lâu, heap đang dùng bao nhiêu, có bao nhiêu luồng đang hoạt động, bộ thu gom rác đã thực hiện bao nhiêu lượt?

`ManagementFactory`, thuộc gói `java.lang.management`, là điểm truy cập chuẩn để lấy các **MXBean nền tảng (platform MXBean)**. Mỗi MXBean cung cấp giao diện quản lý một thành phần của JVM. Ta gọi phương thức Java trên giao diện đó để đọc thông tin, thay vì đọc chuỗi từ một lệnh hệ điều hành hoặc phụ thuộc vào lớp triển khai nội bộ.

Ví dụ nhập môn:

~~~java
long uptimeMillis = ManagementFactory.getRuntimeMXBean().getUptime();
~~~

Đây là một câu lệnh minh họa, cần import `java.lang.management.ManagementFactory` và đặt trong phương thức. Nó đọc thời gian hoạt động của **JVM đang thực thi câu lệnh**, không phải thời gian sống riêng của một đối tượng hay thời gian máy tính đã bật.

Ba thành phần cần phân biệt:

- **ManagementFactory**: lấy các đối tượng quản lý hoặc truy cập MBeanServer nền tảng.
- **MXBean**: giao diện có kiểu dữ liệu rõ ràng, chẳng hạn `MemoryMXBean` hoặc `RuntimeMXBean`.
- **MBeanServer**: nơi các managed bean được đăng ký và được truy cập qua JMX, dùng tên `ObjectName`.

MXBean có quy tắc ánh xạ dữ liệu sang các kiểu mở của JMX, giúp công cụ quản lý trao đổi dữ liệu mà không cần biết lớp triển khai riêng của JVM. [ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html)

## 2. Các nhóm MXBean nên biết trước khi viết bộ thu thập số liệu

| Thành phần cần quan sát | Giao diện | Cách lấy thường dùng |
|---|---|---|
| Phiên chạy JVM | `RuntimeMXBean` | `getRuntimeMXBean()` |
| Heap và non-heap | `MemoryMXBean` | `getMemoryMXBean()` |
| Luồng nền tảng | `ThreadMXBean` | `getThreadMXBean()` |
| Nạp lớp | `ClassLoadingMXBean` | `getClassLoadingMXBean()` |
| Hệ điều hành nhìn từ JVM | `OperatingSystemMXBean` | `getOperatingSystemMXBean()` |
| Trình biên dịch JIT | `CompilationMXBean` | `getCompilationMXBean()` |
| Các bộ thu gom rác | `GarbageCollectorMXBean` | `getGarbageCollectorMXBeans()` |
| Các vùng bộ nhớ | `MemoryPoolMXBean` | `getMemoryPoolMXBeans()` |
| Các bộ quản lý bộ nhớ | `MemoryManagerMXBean` | `getMemoryManagerMXBeans()` |
| Các vùng buffer như direct/mapped | `BufferPoolMXBean` | `getPlatformMXBeans(BufferPoolMXBean.class)` |

Các phương thức trong cột cuối thuộc `ManagementFactory`. Bảng là bản đồ chọn giao diện, không có nghĩa mọi mục đều có đúng một đối tượng.

Heap có thể được chia thành nhiều pool; một JVM có thể cung cấp nhiều GC bean. Không chọn phần tử đầu tiên rồi coi đó là toàn bộ hệ thống bộ nhớ. Nếu cần quan sát toàn cảnh, duyệt các bean và giữ danh tính riêng của chúng.

## 3. Ba cách lấy bean có kiểu rõ ràng

### 3.1. Getter chuyên biệt

Cách dễ đọc nhất khi đã biết thành phần:

~~~java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
~~~

Các dòng trên cần import các giao diện tương ứng trong `java.lang.management`. Đây là tham chiếu đến thành phần quản lý của JVM hiện tại, không phải ảnh chụp cố định: gọi getter số liệu vào thời điểm khác có thể nhận giá trị khác.

### 3.2. Getter tổng quát cho một bean

~~~java
MemoryMXBean memory =
        ManagementFactory.getPlatformMXBean(MemoryMXBean.class);
~~~

Dùng cho giao diện được quy định là có một thực thể nếu được triển khai. Với một giao diện tùy chọn, kết quả có thể là `null`. Không dùng biến thể số ít cho loại có nhiều thực thể như `MemoryPoolMXBean`: API có thể ném `IllegalArgumentException`.

### 3.3. Getter tổng quát trả danh sách

~~~java
List<BufferPoolMXBean> pools =
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
~~~

Đoạn này cần import `java.util.List`, `BufferPoolMXBean` và `ManagementFactory`. Danh sách có thể có không, một hoặc nhiều phần tử tùy hợp đồng giao diện. **Không có bảo đảm thứ tự danh sách ổn định** giữa các lần gọi; dùng `getObjectName()` hoặc tên phù hợp để nhận diện bean, không dùng chỉ số danh sách làm danh tính. [Hợp đồng getPlatformMXBean/getPlatformMXBeans](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html#getPlatformMXBeans(java.lang.Class))

`getPlatformManagementInterfaces()` còn cho biết các giao diện quản lý mà JVM hỗ trợ. Nó hữu ích khi xây công cụ khám phá khả năng; một ứng dụng chỉ cần vài số liệu thường nên gọi trực tiếp các getter liên quan.

## 4. Xử lý khả năng tùy chọn và các giá trị đặc biệt

### Trình biên dịch có thể không tồn tại hoặc không cung cấp thống kê thời gian

`getCompilationMXBean()` có thể trả `null` khi JVM không có hệ thống biên dịch. Có bean cũng chưa đủ để gọi mọi phép đo; kiểm tra `isCompilationTimeMonitoringSupported()` trước `getTotalCompilationTime()`.

Thời gian này là thời gian biên dịch tích lũy gần đúng, tính bằng mili giây. Nó không phải thời gian CPU của toàn ứng dụng, và không phải thước đo để kết luận JVM của hãng nào nhanh hơn. [CompilationMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/CompilationMXBean.html)

### Giá trị âm thường biểu thị số liệu không sẵn có

Không tự chuyển mọi giá trị âm thành 0:

- `MemoryUsage.getMax()` hoặc `getInit()` có thể là `-1` khi chưa xác định.
- `GarbageCollectorMXBean.getCollectionCount()` và `getCollectionTime()` có thể là `-1` khi số liệu không xác định.
- Một số chỉ số khác có quy ước riêng; đọc hợp đồng của đúng phương thức.

Số 0 biểu thị một giá trị đo được bằng 0; “không sẵn có” biểu thị không có dữ liệu hợp lệ để kết luận. Hai trường hợp này cần đi qua hai nhánh khác nhau trong báo cáo hoặc biểu đồ.

## 5. Đọc số liệu bộ nhớ đúng nghĩa

`MemoryMXBean.getHeapMemoryUsage()` trả `MemoryUsage` với bốn đại lượng tính bằng byte:

| Thuộc tính | Ý nghĩa |
|---|---|
| `init` | Lượng bộ nhớ yêu cầu lúc khởi tạo; có thể chưa xác định |
| `used` | Lượng đang được ghi nhận là sử dụng |
| `committed` | Lượng được bảo đảm sẵn có để JVM sử dụng cho vùng đang đo |
| `max` | Giới hạn tối đa nếu được xác định |

Trong cùng một `MemoryUsage`, `used <= committed`; nếu `max` xác định thì `committed <= max`. Không tính phần trăm `used / max` khi `max <= 0`. `committed - used` là phần chưa dùng bên trong lượng đã cam kết, không phải tổng RAM còn trống của máy. [MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html)

Một ảnh chụp heap không đại diện cho toàn bộ bộ nhớ tiến trình. Còn có non-heap, stack luồng, buffer ngoài heap và các khoản cấp phát native khác. Tăng heap không tự giải quyết mọi vấn đề thiếu bộ nhớ.

`BufferPoolMXBean` bổ sung góc nhìn cho các pool như direct/mapped. `getMemoryUsed()` là ước lượng, có thể khác `getTotalCapacity()` vì cách căn chỉnh và cấp phát; không cộng các chỉ số khác nghĩa rồi gọi đó là tổng bộ nhớ chính xác. [BufferPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)

## 6. Ví dụ độc lập: đọc một lần và đối chiếu truy cập JMX

Chương trình sau dùng API chuẩn, không cần thư viện ngoài hay kết nối JMX từ xa. Nó minh họa getter chuyên biệt, getter danh sách tổng quát, kiểm tra khả năng tùy chọn và truy cập qua MBeanServer.

Lưu thành `PlatformSnapshot.java`:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.CompilationMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.OperatingSystemMXBean;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class PlatformSnapshot {
    private static String known(long value) {
        return value < 0 ? "unavailable" : Long.toString(value);
    }

    public static void main(String[] args) throws Exception {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();
        OperatingSystemMXBean os =
                ManagementFactory.getOperatingSystemMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        System.out.println("vm.name=" + runtime.getVmName());
        System.out.println("uptime.ms=" + runtime.getUptime());
        System.out.println("heap.used.bytes=" + heap.getUsed());
        System.out.println("heap.committed.bytes=" + heap.getCommitted());
        System.out.println("heap.max.bytes=" + known(heap.getMax()));
        System.out.println("platform.threads.live="
                + threads.getThreadCount());
        System.out.println("classes.loaded=" + classes.getLoadedClassCount());
        System.out.println("processors.available="
                + os.getAvailableProcessors());

        CompilationMXBean compilation =
                ManagementFactory.getCompilationMXBean();
        if (compilation == null) {
            System.out.println("jit=unavailable");
        } else {
            System.out.println("jit=" + compilation.getName());
            if (compilation.isCompilationTimeMonitoringSupported()) {
                System.out.println("jit.total.ms="
                        + compilation.getTotalCompilationTime());
            } else {
                System.out.println("jit.total.ms=unavailable");
            }
        }

        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("gc[" + gc.getName() + "].count="
                    + known(gc.getCollectionCount()));
            System.out.println("gc[" + gc.getName() + "].time.ms="
                    + known(gc.getCollectionTime()));
        }

        for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(
                BufferPoolMXBean.class)) {
            System.out.println("buffer[" + pool.getName() + "].used.bytes="
                    + known(pool.getMemoryUsed()));
        }

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
                new ObjectName(ManagementFactory.RUNTIME_MXBEAN_NAME);
        Object vmName = server.getAttribute(name, "VmName");
        System.out.println("jmx.vm.name.same="
                + runtime.getVmName().equals(vmName));
    }
}
~~~

Dùng JDK 17 trở lên, chạy tại thư mục chứa tệp:

~~~shell
javac PlatformSnapshot.java
java PlatformSnapshot
~~~

Trong một lần chạy thật với OpenJDK 24, stdout là:

~~~text
vm.name=OpenJDK 64-Bit Server VM
uptime.ms=48
heap.used.bytes=0
heap.committed.bytes=2147483648
heap.max.bytes=31675383808
platform.threads.live=7
classes.loaded=801
processors.available=28
jit=HotSpot 64-Bit Tiered Compilers
jit.total.ms=7
gc[G1 Young Generation].count=0
gc[G1 Young Generation].time.ms=0
gc[G1 Concurrent GC].count=0
gc[G1 Concurrent GC].time.ms=0
gc[G1 Old Generation].count=0
gc[G1 Old Generation].time.ms=0
buffer[mapped].used.bytes=0
buffer[direct].used.bytes=0
buffer[mapped - 'non-volatile memory'].used.bytes=0
jmx.vm.name.same=true
~~~

Đây là **một lần quan sát**, không phải tập giá trị cố định cho mọi JVM. Tên GC, danh sách buffer, số lớp, bộ nhớ và thời gian có thể khác theo phiên bản, cấu hình và thời điểm lấy mẫu. Thứ tự danh sách cũng có thể khác.

Trong lần chạy ngắn này, heap được báo là 0 byte đã dùng ở thời điểm lấy mẫu. Không suy diễn rằng chương trình không tạo đối tượng; mức cập nhật và cách hạch toán của JVM có thể làm số liệu quan sát lúc khởi động khác trực giác về các đối tượng vừa tạo.

Dòng `jmx.vm.name.same=true` đối chiếu cùng thuộc tính tên triển khai JVM qua hai đường. Phép đối chiếu này có ý nghĩa vì tên triển khai không biến động như lượng bộ nhớ đang dùng. Không đòi hỏi hai lần đọc số liệu động liên tiếp phải bằng nhau.

Các điểm trong chương trình cần hiểu:

- `known` chuyển quy ước âm thành chữ `unavailable` ở **những chỉ số đang được in**, không thay đổi dữ liệu gốc.
- Thời gian hoạt động, thời gian JIT và thời gian GC được in bằng mili giây; bộ nhớ bằng byte.
- Lấy `MemoryUsage heap` một lần giúp các trường heap trong báo cáo thuộc cùng đối tượng ảnh chụp.
- Các bean khác được gọi tuần tự; toàn bộ bản in không phải ảnh chụp nguyên tử của JVM tại đúng một thời điểm.
- `main throws Exception` giữ ví dụ ngắn cho các ngoại lệ JMX. Trong bộ thu thập thực tế, cần ghi nhận lỗi của nguồn số liệu phù hợp thay vì làm dừng ứng dụng.
- Chương trình chỉ đọc; không gọi `gc()`, không bật tính năng giám sát đắt tiền và không thay đổi cấu hình runtime.

## 7. Truy cập qua MBeanServer: vẫn cùng thành phần, khác đường gọi

Mỗi MXBean nền tảng có `ObjectName` để đăng ký với MBeanServer. Ví dụ runtime dùng tên trong `ManagementFactory.RUNTIME_MXBEAN_NAME`, tức `java.lang:type=Runtime`.

Trong chương trình:

~~~java
Object vmName = server.getAttribute(name, "VmName");
~~~

Tên thuộc tính JMX là `VmName`, không phải chuỗi `getVmName()`. Đường gọi JMX có các lỗi như tên không hợp lệ, bean không tồn tại hoặc thuộc tính không tồn tại; truy cập trực tiếp qua giao diện Java giúp tránh nhiều lỗi tên chuỗi và có kiểu trả về rõ ràng hơn.

Với dữ liệu cấu trúc, kiểu trên đường JMX cũng có thể khác kiểu Java trực tiếp. Chẳng hạn `MemoryUsage` được ánh xạ sang `CompositeData`. Không ép kiểu kết quả `getAttribute(..., "HeapMemoryUsage")` thẳng thành `MemoryUsage`; nếu cần, dùng ánh xạ `MemoryUsage.from(...)` đúng kiểu đầu vào.

`getPlatformMBeanServer()` trả máy chủ quản lý dùng chung của JVM và đăng ký các MXBean nền tảng. **Lời gọi này không tự mở cổng quản lý từ xa**. Không cần cấu hình JMX remote để chương trình tự đọc bean của chính nó.

Khi đã có `MBeanServerConnection` đến một JVM khác, có thể tạo proxy có kiểu bằng `getPlatformMXBean(connection, RuntimeMXBean.class)`, hoặc lấy danh sách bằng biến thể số nhiều. Lúc đó lời gọi đi đến JVM đích; kết nối, xác thực, bảo vệ đường truyền và lỗi mạng là các phần phải quản lý riêng. Bài này không thiết lập máy chủ JMX từ xa.

## 8. Những giới hạn quan trọng trên Java hiện hành

### ThreadMXBean không phải bộ đếm mọi loại luồng

`ThreadMXBean` quản lý và giám sát **luồng nền tảng (platform thread)**. Trên Java có luồng ảo (virtual thread), không lấy `getThreadCount()` làm tổng số virtual thread đang chạy.

Các tính năng như thời gian CPU của luồng hay theo dõi tranh chấp có thể phụ thuộc khả năng và trạng thái bật/tắt. Trước khi dùng, kiểm tra phương thức `is...Supported()` và trạng thái liên quan; không bật mọi tính năng chỉ vì bean có phương thức tương ứng. [ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

### Thông tin hệ điều hành không đồng nghĩa phần trăm CPU của tiến trình

`OperatingSystemMXBean.getAvailableProcessors()` là số bộ xử lý sẵn có cho JVM, có thể thay đổi. Không tự kết luận đó là số nhân vật lý của cả máy.

`getSystemLoadAverage()` là tải trung bình hệ thống trong một phút và có thể âm khi không sẵn có; nó không phải phần trăm CPU của tiến trình Java. Các phần mở rộng theo JDK có thể cung cấp số liệu khác nhưng cần kiểm tra khả năng, không ép kiểu mù vào lớp nội bộ. [OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html)

### Số liệu GC là tích lũy gần đúng, không phải từng lần dừng ứng dụng

`getCollectionTime()` là thời gian thu gom tích lũy gần đúng. Hiệu hai mẫu chỉ biểu thị thay đổi của số đo đó trong khoảng lấy mẫu, không trực tiếp cho biết phân vị độ trễ hay thời gian dừng dài nhất. Từng bộ thu gom còn có cách báo cáo riêng; không cộng mọi giá trị rồi coi là phần trăm thời gian ứng dụng bị dừng. [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)

## 9. Đưa vào ứng dụng: thu thập có ngữ cảnh

Một bộ thu thập nhỏ có thể giữ tham chiếu các bean cần đọc, lấy mẫu định kỳ và lưu cùng dấu thời gian. Mục tiêu là tạo chuỗi quan sát đủ để giải thích xu hướng, không phải gọi getter liên tục trong mỗi yêu cầu nghiệp vụ.

Phân biệt hai kiểu dữ liệu:

- **Giá trị tại thời điểm đo**: heap đang dùng, số luồng sống, số lớp đang được nạp.
- **Bộ đếm tích lũy**: tổng lượt GC, tổng thời gian GC, tổng số lớp đã nạp.

Với bộ đếm, tính hiệu giữa hai mẫu thuộc cùng phiên JVM và cùng bean. Nếu tiến trình khởi động lại, bean thay đổi hoặc giá trị không còn hợp lệ, bắt đầu đường cơ sở mới. Không xuất tốc độ âm từ hai phiên khác nhau; cũng không coi `-1` là một mẫu số liệu bình thường.

Số liệu runtime như tham số khởi động hoặc system properties có thể chứa cấu hình nhạy cảm. Khi chọn thuộc tính để xuất ra endpoint hay log, chỉ xuất những trường cần thiết cho mục đích giám sát.

Ứng dụng dùng Java Module System cần khai báo:

~~~java
module example.monitoring {
    requires java.management;
}
~~~

Đây là nội dung minh họa cho `module-info.java` của một ứng dụng có module, không phải tệp thứ hai bắt buộc cho ví dụ classpath ở trên. Với runtime image rút gọn, cần bảo đảm module quản lý cần thiết có mặt.

## 10. Lỗi thường gặp và bài tập kiểm chứng

| Cách làm | Điều cần sửa |
|---|---|
| Cố định một số lượng hoặc tên GC cho mọi JVM | Khám phá danh sách từ JVM đang chạy |
| Chọn bean bằng vị trí 0 rồi gắn danh tính lâu dài | Dùng tên/ObjectName, không dựa vào thứ tự |
| Gọi getter số ít với `MemoryPoolMXBean.class` | Dùng danh sách cho loại có nhiều thực thể |
| Gọi phương thức trên `CompilationMXBean` không kiểm tra null | Xử lý JVM không có bean biên dịch |
| Tính phần trăm heap với max bằng -1 | Đánh dấu chưa xác định hoặc chọn phép đo khác có ý nghĩa |
| Dùng heap làm tổng RAM tiến trình | Phân biệt heap, non-heap và cấp phát native |
| Đếm virtual thread bằng `ThreadMXBean` | Tôn trọng phạm vi platform thread của giao diện |
| Gọi `getPlatformMBeanServer()` rồi cho rằng đã có JMX remote | Phân biệt đăng ký cục bộ và cấu hình connector từ xa |
| Kết luận rò rỉ bộ nhớ từ một lần đọc | Theo dõi xu hướng cùng tải và chu kỳ GC |

Để kiểm chứng hiểu bài, hãy mở rộng chương trình theo ba bước:

1. In thêm non-heap qua `getNonHeapMemoryUsage()`, vẫn xử lý `max` không xác định.
2. Duyệt `getMemoryPoolMXBeans()` và in tên, kiểu vùng nhớ, `getUsage()`; xử lý trường hợp usage là `null` nếu pool không còn hợp lệ.
3. Lấy hai mẫu cách nhau một khoảng thời gian, lưu mốc lấy mẫu và so sánh chỉ những bộ đếm hợp lệ của cùng GC bean.

Sau mỗi bước, giải thích **số liệu đang đo thành phần nào, dùng đơn vị gì, có thể thiếu khi nào và không cho phép kết luận điều gì**. Đó là nền tảng để dùng ManagementFactory hữu ích trong giám sát JVM, thay vì chỉ in ra nhiều con số.
