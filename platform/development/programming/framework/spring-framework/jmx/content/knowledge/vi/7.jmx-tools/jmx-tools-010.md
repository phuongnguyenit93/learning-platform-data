# Thực hành quan sát một ứng dụng Java nhỏ bằng công cụ JMX

## 1. Mục tiêu của bài thực hành

JMX (Java Management Extensions) cho phép quan sát và quản trị một ứng dụng Java đang chạy mà không cần bổ sung một HTTP endpoint cho từng giá trị nội bộ. Trong bài thực hành này, bạn sẽ tạo một ứng dụng Java rất nhỏ, đăng ký một **Standard MBean** tự viết, rồi sử dụng **JConsole** để khám phá JVM và tương tác với MBean.

Sau bài này, bạn có thể:

1. Khởi chạy một Java process tồn tại đủ lâu để kết nối bằng công cụ JMX.
2. Phân biệt các chỉ số JVM có sẵn với các giá trị quản trị do ứng dụng tự công bố.
3. Kết nối JConsole tới JVM local và tìm các tab quan sát `Memory`, `Threads`, `Classes` và `MBeans`.
4. Đọc một attribute chỉ đọc, thay đổi một attribute đọc–ghi và gọi một operation của MBean.
5. Hiểu tác dụng của sampling: các thông số là ảnh chụp theo thời điểm và có thể biến đổi giữa hai lần quan sát.
6. Nhận diện rủi ro của các thao tác điều khiển runtime và những giới hạn của quan sát qua JMX.

Bài sử dụng Java SE để thấy cơ chế JMX gốc. Khi chuyển sang ứng dụng Spring Framework hoặc Spring Boot, nền tảng `MBeanServer`, `ObjectName` và các khái niệm attribute/operation vẫn giữ nguyên; Spring chủ yếu hỗ trợ export, cấu hình và vòng đời bean.

## 2. Mô hình của thí nghiệm

Ứng dụng mô phỏng xử lý một request nhỏ theo chu kỳ. Mỗi lần xử lý, bộ đếm tăng và có thể tạo một đối tượng nhỏ để gây biến động bộ nhớ. Một MBean `DemoMonitor` công bố một số trạng thái.

```text
                  Console / terminal
                         |
                 java DemoApplication
                         |
             +-----------+------------+
             |                        |
         Worker thread             MBeanServer
             |                        |
       simulated request        JVM platform MXBeans
             |                        |
       DemoMonitor MBean -------------+
             |                        |
        attribute / operation          |
             +-----------+------------+
                         |
               JConsole (local)
                         |
        Memory / Threads / Classes / MBeans
```

Điểm khác nhau giữa hai nhóm dữ liệu:

- **JVM platform MXBeans** do JDK cung cấp, ví dụ memory usage, thread count, class loading và garbage collector statistics. Bạn không cần viết code để công bố những thông tin nền tảng này.
- **Application MBean** do bạn tạo, ví dụ tổng số tác vụ, ngưỡng cảnh báo và chế độ mô phỏng. Chúng thể hiện nhu cầu quản trị riêng của ứng dụng.

JConsole là một **JMX client**. Nó đọc dữ liệu qua MBeanServer và cung cấp một giao diện đồ họa. JConsole không phải một phần của Spring Framework và bản thân nó không lưu trữ lịch sử dài hạn như hệ thống metrics chuyên dụng.

## 3. Chuẩn bị môi trường

Sử dụng một JDK có công cụ `java`, `javac` và `jconsole`, chẳng hạn JDK 21. Bài không yêu cầu Maven, Gradle, Spring Boot, database hay Docker.

Kiểm tra trong terminal:

```bash
java -version
javac -version
jconsole
```

Lệnh `jconsole` thường mở cửa sổ đồ họa. Nếu hệ điều hành báo không tìm thấy lệnh, hãy kiểm tra bạn đang sử dụng **JDK đầy đủ** và `JAVA_HOME/bin` hoặc thư mục `bin` của JDK có trên `PATH`. Trong môi trường headless, container không có desktop hoặc phiên SSH không có giao diện, JConsole có thể không mở được; khi đó dùng desktop ở máy phù hợp hoặc viết client JMX local theo phần thay thế ở cuối bài.

**Bảo mật:** bài tập này dùng kết nối local tới tiến trình do bạn tự khởi chạy. Không cần bật remote JMX, không đặt `com.sun.management.jmxremote.authenticate=false` hoặc `...ssl=false`, không mở cổng mạng công khai. Nếu JConsole yêu cầu quyền truy cập local process, hãy chạy công cụ trong cùng ngữ cảnh người dùng hệ điều hành khi phù hợp.

Tạo thư mục:

```text
jmx-observation-lab/
  DemoMonitorMBean.java
  DemoMonitor.java
  DemoApplication.java
```

Mỗi public class/interface nằm trong file riêng cùng tên. Có thể đặt ba file trong cùng thư mục và không khai báo `package` để đơn giản hóa quá trình biên dịch.

## 4. Xây dựng giao diện quản trị DemoMonitorMBean

Tạo file `DemoMonitorMBean.java`:

```java
public interface DemoMonitorMBean {

    // Thuộc tính chỉ đọc: dữ liệu do worker cập nhật.
    long getProcessedCount();

    // Thuộc tính chỉ đọc: snapshot tại thời điểm getter được gọi.
    int getLastBatchSize();

    // Thuộc tính đọc–ghi: người vận hành có thể thay đổi runtime.
    int getBatchSize();
    void setBatchSize(int batchSize);

    // Thuộc tính đọc–ghi: điều khiển việc mô phỏng.
    boolean isRunning();
    void setRunning(boolean running);

    // Operation: reset thống kê.
    void resetCounters();
}
```

Quy ước **Standard MBean** kết nối tên `DemoMonitor` với `DemoMonitorMBean`. Các method `getX()` và `isX()` tạo attribute có thể đọc; `setX(...)` tạo khả năng ghi. Getter và setter cùng thuộc tính `BatchSize` hoặc `Running` tạo một read-write attribute. Method `resetCounters()` là operation.

Một interface MBean là **hợp đồng công khai cho quản trị**. Những method chỉ có trong implementation nhưng không xuất hiện ở interface sẽ không mặc nhiên được export qua Standard MBean. Không nên công bố tất cả chi tiết nội bộ khi chỉ cần một số thuộc tính vận hành.

## 5. Triển khai MBean an toàn với nhiều thread

Tạo file `DemoMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class DemoMonitor implements DemoMonitorMBean {

    private final AtomicLong processedCount = new AtomicLong();
    private final AtomicInteger lastBatchSize = new AtomicInteger();

    private volatile int batchSize = 10;
    private volatile boolean running = true;

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public int getLastBatchSize() {
        return lastBatchSize.get();
    }

    @Override
    public int getBatchSize() {
        return batchSize;
    }

    @Override
    public void setBatchSize(int batchSize) {
        if (batchSize < 1 || batchSize > 1_000) {
            throw new IllegalArgumentException(
                "BatchSize must be between 1 and 1000"
            );
        }
        this.batchSize = batchSize;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public void setRunning(boolean running) {
        this.running = running;
    }

    @Override
    public void resetCounters() {
        processedCount.set(0L);
        lastBatchSize.set(0);
    }

    // Method nội bộ: không có trong MBean interface.
    public void recordBatch(int processed) {
        processedCount.addAndGet(processed);
        lastBatchSize.set(processed);
    }
}
```

Ở đây `AtomicLong` và `AtomicInteger` bảo vệ thao tác cập nhật các bộ đếm riêng lẻ trong môi trường có nhiều thread. `volatile` giúp các thay đổi `batchSize` và `running` được worker quan sát mà không cần đồng bộ phức tạp. Những cơ chế đó **không tạo một snapshot nguyên tử của nhiều thuộc tính**: nếu đọc `ProcessedCount` rồi `LastBatchSize`, worker có thể cập nhật giữa hai lần đọc.

Setter `setBatchSize` từ chối giá trị nằm ngoài phạm vi 1..1000. Đây là validation thuộc trách nhiệm của ứng dụng; một client JMX không tự biết các quy tắc nghiệp vụ trừ khi metadata và tài liệu mô tả chúng.

## 6. Tạo ứng dụng chạy và cập nhật trạng thái

Tạo file `DemoApplication.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class DemoApplication {

    public static void main(String[] args) throws Exception {

        DemoMonitor monitor = new DemoMonitor();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "lab.jmx:type=DemoMonitor,name=small-app"
        );

        server.registerMBean(monitor, name);

        System.out.println("JMX demo started");
        System.out.println("ObjectName: " + name);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Connect with JConsole and inspect MBeans");

        // Worker mô phỏng công việc và một chút allocation.
        // Không giữ object lâu, để JVM tự thu hồi khi thích hợp.
        List<byte[]> temporary = new ArrayList<>();

        while (!Thread.currentThread().isInterrupted()) {
            if (monitor.isRunning()) {
                int count = monitor.getBatchSize();

                temporary.clear();
                for (int i = 0; i < count; i++) {
                    temporary.add(new byte[4 * 1024]);
                }

                monitor.recordBatch(count);

                System.out.printf(
                    "ProcessedCount=%d, LastBatch=%d, BatchSize=%d%n",
                    monitor.getProcessedCount(),
                    monitor.getLastBatchSize(),
                    monitor.getBatchSize()
                );
            } else {
                System.out.println("Simulation paused");
            }

            TimeUnit.SECONDS.sleep(2);
        }
    }
}
```

Ứng dụng đăng ký MBean vào platform MBeanServer qua `ManagementFactory.getPlatformMBeanServer()`. `ObjectName` là định danh tìm kiếm MBean, gồm domain `lab.jmx` và các key property `type`, `name`. Các key đó thuộc phần định danh; chúng không có quan hệ trực tiếp với tên class Java hay đường dẫn file.

Worker tạo các mảng `byte[]` nhỏ theo mỗi batch, lưu tạm trong danh sách rồi thay thế ở vòng sau. Đây chỉ là **allocation minh họa**, không phải benchmark bộ nhớ hay mô hình tải production. Số lần garbage collection, độ lớn heap và đồ thị memory phụ thuộc JDK, collector, kích thước heap và các yếu tố khác; không mong chờ một đường cong cố định.

Vòng lặp trên chạy đến khi process bị dừng, thường bằng `Ctrl+C` trong terminal. Khi JVM kết thúc, MBean không còn tồn tại. Một ứng dụng production có thể gỡ MBean chủ động trong lifecycle shutdown; đối với lab ngắn này, JVM shutdown tự kết thúc MBeanServer trong tiến trình.

## 7. Biên dịch và chạy

Trong thư mục `jmx-observation-lab`, chạy:

```bash
javac DemoMonitorMBean.java DemoMonitor.java DemoApplication.java
java DemoApplication
```

Bạn sẽ thấy log tương tự:

```text
JMX demo started
ObjectName: lab.jmx:type=DemoMonitor,name=small-app
PID: 12345
Connect with JConsole and inspect MBeans
ProcessedCount=10, LastBatch=10, BatchSize=10
ProcessedCount=20, LastBatch=10, BatchSize=10
ProcessedCount=30, LastBatch=10, BatchSize=10
...
```

PID chỉ là ví dụ; mỗi lần chạy và mỗi máy sẽ có PID khác. Khi `Running=true`, `ProcessedCount` tăng theo batch size cứ khoảng hai giây. Nếu máy bận hoặc hệ điều hành scheduling khác, khoảng thời gian thực tế có thể lệch một chút.

Giữ terminal này chạy. Mở terminal thứ hai để khởi động `jconsole`. Nếu đóng terminal đang chạy Java, dừng process hoặc JVM thoát, JConsole không thể tiếp tục quan sát MBean cũ.

### 7.1. Cấu trúc file sau biên dịch

```text
jmx-observation-lab/
  DemoMonitorMBean.java
  DemoMonitor.java
  DemoApplication.java
  DemoMonitorMBean.class
  DemoMonitor.class
  DemoApplication.class
```

JDK có thể tạo thêm file class nếu code có nested classes; với ba file ở trên, ba class file chính là đủ. Không cần thêm `module-info.java` hay dependency quản lý bằng build tool cho thí nghiệm tối giản này.

## 8. Mở JConsole và chọn đúng JVM

Trong một terminal khác, chạy:

```bash
jconsole
```

JConsole thường hiển thị danh sách các process Java local mà nó có thể quan sát. Chọn process có main class `DemoApplication` hoặc PID đã in từ terminal.

Nếu danh sách có nhiều Java process, **đừng đoán theo thứ tự**. Đối chiếu PID và main class; có thể có IDE, Gradle daemon, server khác cũng đang chạy. Khi công cụ yêu cầu xác nhận kết nối local hoặc hiển thị cảnh báo, đọc rõ JVM nào đang được chọn.

Sau khi kết nối, giao diện thường có các tab:

- `Overview`: tổng quan usage và biểu đồ.
- `Memory`: heap/non-heap và hoạt động GC ở mức phù hợp.
- `Threads`: thread count, thông tin thread, khả năng phát hiện deadlock tùy công cụ/JVM.
- `Classes`: số class loaded/unloaded.
- `VM Summary`: thông tin VM, runtime, arguments, properties.
- `MBeans`: cây MBean của JVM và ứng dụng.

Tên tab, layout và chi tiết hiển thị có thể thay đổi theo phiên bản JDK hoặc hệ điều hành. Mục tiêu là nhận biết dữ liệu và chức năng, không phụ thuộc pixel hay thứ tự tab.

## 9. Quan sát JVM: Memory, Threads và Classes

### 9.1. Memory

Chọn tab `Memory` và xem các thông số như heap usage, non-heap usage và biểu đồ sử dụng bộ nhớ theo thời gian.

Điểm cần phân biệt:

| Chỉ số | Ý nghĩa |
|---|---|
| Used | Bộ nhớ đang được JVM báo là sử dụng |
| Committed | Dung lượng JVM đã cam kết có thể sử dụng |
| Max | Giới hạn tối đa được báo nếu xác định được |
| Heap | Vùng lưu trữ phần lớn object Java |
| Non-heap | Các vùng bộ nhớ quản lý runtime khác ngoài heap |

`used` không đồng nghĩa `committed` và cũng không nhất thiết bằng `max`. Một lần nhìn thấy heap tăng là bình thường nếu worker đang tạo object. Java garbage collector có thể thu hồi object không còn reachable khi cần; heap used có thể tăng rồi giảm hoặc thay đổi theo mô hình khác tùy collector.

Một số bản JConsole có nút yêu cầu GC. Thao tác này chỉ phục vụ thử nghiệm và có thể ảnh hưởng tiến trình. Không dùng nút đó để kết luận “ứng dụng có memory leak” hoặc “không có memory leak”. Garbage collection được yêu cầu không đảm bảo heap sẽ giảm ngay theo một mức cụ thể.

### 9.2. Threads

Chọn tab `Threads`, xem số thread hiện tại và danh sách các thread. Ứng dụng chỉ có một main worker do bạn viết, nhưng JVM, JMX agent và các runtime thread khác có thể cùng tồn tại. Vì vậy **thread count không bằng số thread nghiệp vụ bạn chủ động tạo**.

Có thể quan sát trạng thái thread khác nhau (`RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`) tùy thời điểm. Ví dụ `TimeUnit.SECONDS.sleep(2)` làm main thread thường rơi vào `TIMED_WAITING` trong lúc ngủ.

Số thread cao không tự chứng minh deadlock. Nếu JConsole có chức năng `Detect Deadlock`, đó là một phép kiểm tra cụ thể và vẫn cần phân tích thread dump khi gặp sự cố thực.

### 9.3. Classes

Tab `Classes` cho biết số class đã được load/unload. Thí nghiệm không chủ động tạo class mới liên tục, nên biểu đồ có thể khá ổn định sau giai đoạn khởi động. JConsole/JMX có thể khiến một số class bổ sung được load vào quá trình quan sát. Không mặc định số class tăng là classloader leak.

### 9.4. VM Summary

Đọc tên JVM, Java version, VM arguments và thông tin runtime khác. Đối chiếu version với `java -version` bạn đã dùng. Nếu chạy trong IDE hoặc một môi trường có nhiều JDK, việc đối chiếu này giúp phát hiện kết nối nhầm process hoặc classpath bất ngờ.

## 10. Tìm MBean tự tạo trong cây MBeans

Chọn tab `MBeans` rồi mở domain:

```text
lab.jmx
  type=DemoMonitor,name=small-app
```

Cây và thứ tự hiển thị key có thể khác giữa các công cụ, nhưng ObjectName vẫn định danh cùng MBean. Chọn MBean và xem phần `Attributes`, `Operations` và metadata nếu JConsole hỗ trợ.

Các thuộc tính dự kiến:

| Attribute | Kiểu | Quyền | Diễn giải |
|---|---|---|---|
| `ProcessedCount` | `long` | Read-only | Số phần tử mô phỏng đã xử lý từ lần reset |
| `LastBatchSize` | `int` | Read-only | Kích thước batch cuối cùng |
| `BatchSize` | `int` | Read-write | Số object được tạo và số đếm tăng mỗi vòng |
| `Running` | `boolean` | Read-write | Bật/tạm dừng vòng mô phỏng |

Operation:

```text
resetCounters()
```

Các attribute được JMX nhận dạng thông qua interface `DemoMonitorMBean`. Method `recordBatch(int)` là chi tiết nội bộ và **không xuất hiện** như JMX operation, vì nó không có trong interface.

Nếu không thấy domain `lab.jmx`, kiểm tra Java process còn chạy, JConsole kết nối đúng PID và log khởi động có báo MBean được đăng ký thành công. Nếu `server.registerMBean` ném exception, chương trình sẽ thoát trước khi bạn kết nối; cần đọc lỗi từ terminal.

## 11. Thí nghiệm 1: đọc attribute chỉ đọc

Quan sát `ProcessedCount` ở `MBeans -> Attributes`. Khi worker đang chạy, giá trị tăng sau mỗi vòng.

Thực hiện:

1. Ghi lại giá trị đầu tiên, ví dụ `40`.
2. Sau khoảng vài giây, yêu cầu công cụ đọc lại.
3. Ghi giá trị mới, ví dụ `70`, tùy số chu kỳ đã chạy.
4. Mở terminal chạy Java và so sánh với log đã in.

JConsole có thể tự refresh hoặc chỉ refresh khi bạn thao tác, tùy phiên bản/cấu hình. Dữ liệu được đọc tại hai thời điểm khác nhau không nhất thiết trùng chính xác vì worker tiếp tục chạy giữa các lần quan sát.

Thử kiểm tra metadata: `ProcessedCount` đọc được nhưng không ghi được. Một client gọi `setAttribute("ProcessedCount", ...)` phải bị từ chối theo hợp đồng Standard MBean. Đừng cố “sửa số đếm” bằng việc sửa source hoặc reflection trong bài này; ta đang học giới hạn do giao diện quản trị công bố.

**Điều học được:** read-only là giới hạn khả năng ghi qua JMX, không có nghĩa giá trị không thể thay đổi bởi thread nội bộ.

## 12. Thí nghiệm 2: thay đổi attribute đọc–ghi

Trong `Attributes`, tìm `BatchSize`. Giá trị mặc định là `10`. Thay đổi thành `50` nếu JConsole cho phép sửa attribute tương ứng, rồi xác nhận.

Quan sát terminal:

```text
ProcessedCount=..., LastBatch=10, BatchSize=10
ProcessedCount=..., LastBatch=50, BatchSize=50
ProcessedCount=..., LastBatch=50, BatchSize=50
```

Giá trị `ProcessedCount` tăng nhanh hơn theo mỗi vòng vì chương trình sử dụng `monitor.getBatchSize()` làm số phần tử xử lý. `LastBatchSize` phản ánh batch cuối cùng và có thể chưa đổi ngay nếu bạn đọc trước khi worker bắt đầu vòng mới.

Thử nhập giá trị `0` hoặc `1001`. Setter được thiết kế để từ chối chúng. UI JConsole có thể hiển thị lỗi ghi attribute, còn runtime thường bọc exception từ setter thành một exception JMX. Mục tiêu là thấy **writable không có nghĩa chấp nhận mọi giá trị**.

Sau đó đặt `BatchSize=10` để trở lại nhịp bình thường.

## 13. Thí nghiệm 3: tạm dừng và tiếp tục

Tìm `Running` và đổi từ `true` thành `false`. Terminal sẽ in `Simulation paused` và `ProcessedCount` ngừng tăng sau khi worker quan sát được thay đổi.

Tại thời điểm chuyển chế độ, một vòng đang chạy có thể hoàn thành trước khi `Running=false` có hiệu lực. Đây là đặc tính concurrency của một cờ được worker kiểm tra theo chu kỳ, không phải lỗi JMX.

Đổi lại `Running=true`. Counter sẽ tiếp tục tăng. Hãy tự trả lời:

- Vì sao `Running` là read-write, không phải operation `pause()` và `resume()`?
- Một hệ thống production cần thêm điều kiện an toàn gì trước khi tạm dừng worker thực?
- Một thuộc tính read-write có đủ để thực hiện workflow dừng có trạng thái chuyển tiếp như `STOPPING` hoặc `DRAINING` không?

Trong hệ thống phức tạp, operation rõ ràng như `pauseConsumer()`, `resumeConsumer()` có thể diễn đạt ý định và validation tốt hơn. Bài tập chỉ dùng boolean để minh họa cơ chế JMX.

## 14. Thí nghiệm 4: gọi operation resetCounters()

Chọn mục `Operations`, tìm `resetCounters` và gọi một lần. Sau đó đọc lại `ProcessedCount` và `LastBatchSize`.

Nếu `Running=true`, worker có thể tăng lại counter ngay sau khi reset. Vì vậy `ProcessedCount` không nhất thiết vẫn là `0` khi JConsole đọc lại.

Để dễ quan sát:

1. Đặt `Running=false`.
2. Chờ terminal cho thấy worker đã tạm dừng.
3. Gọi `resetCounters()`.
4. Đọc lại `ProcessedCount` và `LastBatchSize`, lúc này thường là `0`.
5. Đặt `Running=true` để tiếp tục.

**Operation khác attribute:** `resetCounters()` là hành động có tác dụng phụ. `ProcessedCount` vẫn là read-only vì JMX không công bố setter cho nó, dù operation được phép thay đổi giá trị.

Trong production, operation có thể gây ảnh hưởng đáng kể. Chỉ gọi thao tác mà bạn hiểu hậu quả và có quyền thực hiện.

## 15. Quan sát bằng Java client, không cần JConsole

Để minh họa rằng JConsole chỉ là một client, bạn có thể viết một Java class khác đọc cùng MBean qua API JMX. Ví dụ client **trong cùng JVM**, thêm đoạn sau vào `DemoApplication` sau khi đăng ký MBean:

```java
Object value = server.getAttribute(name, "ProcessedCount");
System.out.println("Initial ProcessedCount = " + value);

Object threshold = server.getAttribute(name, "BatchSize");
System.out.println("Initial BatchSize = " + threshold);
```

Hoặc đọc MXBean nền tảng:

```java
import java.lang.management.MemoryMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memoryBean.getHeapMemoryUsage();

System.out.println("Heap used bytes: " + heap.getUsed());
System.out.println("Heap committed bytes: " + heap.getCommitted());
```

Những lệnh này dùng API Java Management mà JDK hỗ trợ. Khi một JMX client thật kết nối từ tiến trình khác, nó vẫn có thể dùng `MBeanServerConnection` để truy vấn cùng các ObjectName, với điều kiện connector được thiết lập và truy cập phù hợp.

### 15.1. Kiểm tra metadata programmatically

Sau đăng ký MBean:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, read=%s, write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

Kết quả giúp bạn xác nhận hợp đồng JMX do MBeanServer nhìn thấy. Đọc metadata đáng tin cậy hơn việc suy đoán dựa vào hình thức UI. Nó cũng phân biệt attribute chỉ đọc với attribute đọc–ghi.

## 16. Thay thế nếu không có giao diện đồ họa

Trong môi trường headless, bạn có thể vẫn kiểm tra MBean bằng API ngay trong JVM. Tạo một tác vụ nhỏ đọc định kỳ qua `MBeanServer`, hoặc bổ sung log metadata và một số giá trị sau mỗi vòng xử lý.

Một ví dụ đơn giản để in mọi ObjectName trong domain lab:

```java
for (ObjectName objectName : server.queryNames(
        new ObjectName("lab.jmx:*"), null)) {
    System.out.println("Found MBean: " + objectName);
}
```

Bạn cũng có thể đọc những platform MBean thông dụng:

```java
var threadingBean = ManagementFactory.getThreadMXBean();
System.out.println("Threads: " + threadingBean.getThreadCount());

var classBean = ManagementFactory.getClassLoadingMXBean();
System.out.println("Loaded classes: " +
    classBean.getLoadedClassCount());
```

Các ví dụ này minh họa quan sát local, **không chứng minh rằng remote JMX đã cấu hình đúng**. Nếu mục tiêu là kiểm tra connector từ xa, cần một thí nghiệm riêng có thiết kế bảo mật, không sử dụng các tùy chọn vô hiệu hóa xác thực/TLS chỉ để truy cập nhanh.

## 17. Mở rộng: áp dụng vào Spring Framework

Khi ứng dụng chuyển sang Spring, cơ chế JMX nền tảng vẫn như vậy:

```text
Spring-managed bean
       |
MBeanExporter / annotation export / explicit registration
       |
MBeanServer
       |
JConsole / Java client
```

Có thể tạo một Spring bean quản lý trạng thái, dùng annotation `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation` để công bố getter, setter và operation. Spring cung cấp tiện ích đăng ký/metadata, còn client vẫn làm việc với `ObjectName`, `MBeanInfo` và JMX API.

Ví dụ lớp bean:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "lab.spring:type=TaskMonitor")
public class TaskMonitor {
    private final AtomicLong count = new AtomicLong();
    private volatile int batchSize = 10;

    public void recordBatch(int size) {
        count.addAndGet(size);
    }

    @ManagedAttribute
    public long getCount() {
        return count.get();
    }

    @ManagedAttribute
    public int getBatchSize() {
        return batchSize;
    }

    @ManagedAttribute
    public void setBatchSize(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("Invalid batch size");
        }
        batchSize = value;
    }

    @ManagedOperation
    public void reset() {
        count.set(0L);
    }
}
```

Để annotation có hiệu lực, ứng dụng phải cấu hình JMX exporter phù hợp. Trong Spring Framework thuần, có thể dùng `@EnableMBeanExport`; trong Spring Boot, khả năng export thường phụ thuộc cấu hình JMX của Boot, ví dụ `spring.jmx.enabled` trong phiên bản sử dụng. Chỉ có `@Component` không đảm bảo bean đã xuất hiện trong JConsole.

Không đặt cả `DemoMonitor` và `TaskMonitor` dưới cùng một ObjectName trong cùng MBeanServer. ObjectName phải duy nhất, nếu không quá trình đăng ký có thể báo lỗi instance đã tồn tại.

## 18. Các lỗi thường gặp khi thực hành

### 18.1. JConsole không tìm thấy Java process

Kiểm tra JVM còn đang chạy, JConsole thuộc JDK phù hợp và tiến trình có thể được attach trong ngữ cảnh người dùng/OS. Trong container hoặc máy bị hạn chế quyền attach, discovery local có thể không hoạt động. Không suy đoán rằng ứng dụng chết chỉ vì JConsole không liệt kê được process.

### 18.2. Kết nối tới JVM sai

Nhiều Java process có tên gần giống nhau. Đối chiếu PID do ứng dụng in hoặc dùng công cụ liệt kê Java process thích hợp. Sau khi kết nối, kiểm tra domain `lab.jmx` để chắc chắn đúng đối tượng.

### 18.3. Không thấy MBean tự tạo

Kiểm tra `server.registerMBean(monitor, name)` đã chạy mà không lỗi, tên interface đúng `DemoMonitorMBean`, class implement interface và ObjectName hợp lệ. Một MBean chưa đăng ký sẽ không tự xuất hiện.

### 18.4. Ghi attribute bị từ chối

`ProcessedCount` là read-only; JMX không cho phép ghi qua `setAttribute`. Với `BatchSize`, giá trị ngoài 1..1000 cũng bị setter từ chối. Đọc metadata và lỗi thực tế để phân biệt quyền ghi với validation.

### 18.5. Gọi reset nhưng vẫn thấy counter tăng

Worker đang chạy và cập nhật sau reset. Tạm dừng bằng `Running=false` rồi reset nếu cần quan sát số `0` rõ ràng.

### 18.6. Biểu đồ memory không thay đổi như dự đoán

Object allocation ít, heap được JVM cấp phát trước, GC chưa chạy hoặc công cụ lấy mẫu chậm. Không tăng bộ nhớ vô giới hạn để ép biểu đồ; nếu muốn thấy rõ hơn, thử điều chỉnh `BatchSize` trong phạm vi an toàn, quan sát trong thời gian đủ dài và đọc các chỉ số theo ngữ nghĩa.

### 18.7. JConsole báo lỗi bảo mật/kết nối

Bài này chỉ hướng dẫn local JMX. Kiểm tra quyền local attach và trạng thái tiến trình. Không nên giải quyết bằng cách mở remote port hoặc vô hiệu hóa xác thực trên môi trường mạng.

### 18.8. Process chiếm CPU hoặc in quá nhiều log

Vòng lặp ngủ hai giây nhưng vẫn liên tục in log. Dừng bằng `Ctrl+C` sau khi hoàn tất quan sát. Khi dùng ứng dụng dài hạn, thay `System.out.println` bằng logging có mức độ phù hợp, điều chỉnh nhịp và hạn chế allocation để tránh ảnh hưởng vận hành.

## 19. Ghi chép kết quả và giải thích

Có thể lập bảng quan sát như sau:

| Thao tác | Kỳ vọng | Dữ liệu cần ghi |
|---|---|---|
| Kết nối JConsole | Thấy Java process đúng PID | PID, JVM version |
| Mở Memory | Có chỉ số heap và non-heap | Used/Committed/Max tại một thời điểm |
| Mở Threads | Có số thread và các trạng thái | Thread count, một ví dụ state |
| Mở Classes | Có số class loaded | Loaded class count |
| Đọc `ProcessedCount` hai lần | Giá trị tăng khi Running=true | Giá trị và thời điểm hai lần đọc |
| Đặt `BatchSize=50` | LastBatch và tốc độ tăng đổi | Trước/sau, log terminal |
| Đặt `Running=false` | Counter ngừng tăng sau một vòng đang chạy | Thời điểm và hai lần đọc |
| Gọi `resetCounters()` lúc paused | Counters về 0 | Giá trị sau operation |
| Đặt `BatchSize=0` | Setter từ chối | Thông báo lỗi quan sát được |

Bảng này là **mẫu ghi nhận dự kiến**, không phải kết quả có sẵn. Hãy điền số thực tế từ máy đang chạy để phân biệt hành vi có thể kiểm chứng và dữ liệu chỉ mang tính minh họa.

Khi giải thích phát hiện, tránh suy diễn quá mức. Ví dụ: một `Heap Used` tăng trong vài lần lấy mẫu chưa chứng minh memory leak; thread count tăng cũng không tự chứng minh deadlock. Cần kết hợp nhiều nguồn dữ liệu và quan sát theo thời gian.

## 20. Bài tập mở rộng

### Bài tập A — Thêm read-only attribute cho uptime

Bổ sung thời điểm khởi tạo vào implementation:

```java
private final long startedAt = System.currentTimeMillis();

@Override
public long getUptimeMillis() {
    return System.currentTimeMillis() - startedAt;
}
```

Thêm `long getUptimeMillis();` vào `DemoMonitorMBean`, biên dịch lại và khởi động ứng dụng. Trong JConsole, kiểm tra attribute `UptimeMillis` chỉ đọc và tăng theo thời gian.

### Bài tập B — Tạo operation thay đổi chế độ

Thay cặp setter `Running` bằng hai operation `pause()`/`resume()` và một getter `isRunning()`. So sánh biểu diễn trên tab `MBeans` và cách API diễn đạt ý định. Khi nào boolean read-write thuận tiện, khi nào operation rõ nghĩa hơn?

### Bài tập C — Thêm notification

Cho MBean kế thừa `NotificationBroadcasterSupport` và phát một JMX `Notification` khi `ProcessedCount` vượt ngưỡng định sẵn. Đăng ký `NotificationListener`, lọc theo `type` và ghi nhận `sequenceNumber`. Chú ý nếu counter tiếp tục vượt ngưỡng, cần quyết định phát mỗi lần hay chỉ phát khi chuyển trạng thái.

### Bài tập D — So sánh attribute JVM và ứng dụng

Dùng `MemoryMXBean` để đọc `HeapMemoryUsage`, rồi dùng `MBeanServer` đọc `ProcessedCount`. Xác định chỉ số nào do JVM định nghĩa và chỉ số nào do ứng dụng định nghĩa. Tại sao công cụ JMX có thể quan sát cả hai qua một giao diện?

### Bài tập E — Kiểm tra tính nhất quán

Bật worker, đọc liên tiếp `LastBatchSize` và `ProcessedCount`. Có thể xảy ra trường hợp các giá trị được lấy ở hai thời điểm khác nhau không? Hãy đề xuất một attribute snapshot tổng hợp nếu cần một bộ số liệu nhất quán hơn.

## 21. Tự kiểm tra kiến thức

1. Vì sao không cần tạo MBean riêng chỉ để biết heap memory usage của JVM?
2. ObjectName `lab.jmx:type=DemoMonitor,name=small-app` dùng để làm gì?
3. JConsole cần biết class implementation `DemoMonitor` mới đọc được attribute không?
4. Vì sao `recordBatch(int)` không hiển thị như operation của Standard MBean?
5. `ProcessedCount` là read-only nhưng vẫn tăng: điều đó có mâu thuẫn không?
6. Vì sao thao tác ghi `BatchSize=0` thất bại mặc dù `BatchSize` là read-write?
7. Một lần bấm `resetCounters()` có bảo đảm JConsole luôn thấy `ProcessedCount=0` khi worker chưa tạm dừng không?
8. JConsole và MBeanServer có vai trò khác nhau như thế nào?
9. Tại sao không thể kết luận memory leak từ một lần nhìn thấy heap used cao?
10. Khi áp dụng lab vào Spring, những phần nào do Spring hỗ trợ và những phần nào vẫn là JMX chuẩn?

## 22. Kết luận

Qua một ứng dụng Java ba file, bạn đã tạo một **giao diện quản trị có thể quan sát trực tiếp**: `DemoMonitorMBean` xác định hợp đồng, `DemoMonitor` quản lý trạng thái, `MBeanServer` đăng ký đối tượng bằng ObjectName, còn JConsole đóng vai trò client đọc attribute và gọi operation. Cùng lúc, các platform MXBean cho thấy JVM đã cung cấp sẵn dữ liệu về memory, threads và classes.

Mỗi lần quan sát là một phép đọc tại thời điểm nhất định; các giá trị thay đổi khi worker hoạt động. Hiểu được nguồn dữ liệu, quyền đọc/ghi, hiệu ứng của operation và giới hạn của số liệu là nền tảng để sử dụng JMX trong ứng dụng Spring và các môi trường vận hành thực tế.
