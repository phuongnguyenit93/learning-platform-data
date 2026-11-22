# Class tab trong JConsole

**Class tab** (tên hiển thị trong giao diện JConsole là **Classes**) dùng để theo dõi hoạt động nạp và gỡ nạp class của một Java Virtual Machine. Tab này trình bày số class đang được nạp, tổng số class đã từng được nạp kể từ khi JVM khởi chạy và tổng số class đã được unload.

Đây là màn hình giám sát tổng quan hữu ích khi ứng dụng dùng nhiều framework, proxy động, plugin, hot reload hoặc triển khai lại module trong cùng một JVM. Đường biểu diễn có thể giúp nhận ra class loading tăng liên tục hoặc class unloading không diễn ra như kỳ vọng. Tuy nhiên, số liệu chỉ là bộ đếm tổng hợp; nó không chỉ ra class cụ thể, class loader nào đang giữ class hay object nào ngăn class loader được thu hồi.

## 1. Class tab hiển thị gì?

Sau khi JConsole kết nối thành công với JVM, giao diện có các tab Overview, Memory, Threads, Classes, VM và MBeans. Chọn **Classes** để xem chi tiết class loading.

Tab có biểu đồ **Number of Loaded Classes** với hai đường:

| Đường biểu diễn | Màu trong JConsole | Ý nghĩa |
|---|---|---|
| Total Loaded | Đỏ | Tổng số class đã được nạp kể từ khi JVM khởi chạy, bao gồm cả class sau đó đã unload |
| Loaded | Xanh dương | Số class hiện đang được nạp trong JVM |

Phần **Details** bên dưới biểu đồ hiển thị ba chỉ số:

- **Current classes loaded:** số class hiện đang được nạp.
- **Total classes loaded:** tổng số class đã được nạp từ khi JVM khởi chạy, kể cả class đã unload.
- **Total classes unloaded:** tổng số class đã được gỡ khỏi JVM kể từ khi khởi chạy.

Đường đỏ là bộ đếm tích lũy: nó tăng khi có class mới được nạp và không giảm khi class unload. Đường xanh biểu diễn số class hiện tại nên có thể tăng hoặc giảm. Khi JVM không còn nạp class mới và cũng không unload class, hai đường có thể nằm ngang.

JConsole cũng có hộp chọn **Verbose Output** ở góc trên bên phải. Bật tùy chọn này sẽ bật verbose class-loading tracing trong JVM mục tiêu; đây là thay đổi trạng thái toàn JVM, không chỉ thay đổi cách vẽ biểu đồ.

## 2. Ba chỉ số được lấy từ đâu?

JConsole sử dụng JMX và platform MXBean của JVM. Class tab được hỗ trợ bởi interface **java.lang.management.ClassLoadingMXBean**.

MXBean này có một instance trong mỗi JVM và có thể lấy trong chương trình Java bằng:

~~~java
ManagementFactory.getClassLoadingMXBean()
~~~

Nó cũng được đăng ký trong platform MBean Server với ObjectName:

~~~text
java.lang:type=ClassLoading
~~~

Các phương thức chính:

| Phương thức | Giá trị trả về | Ý nghĩa |
|---|---|---|
| getLoadedClassCount() | int | Số class hiện đang được nạp |
| getTotalLoadedClassCount() | long | Tổng số class đã được nạp kể từ khi JVM chạy |
| getUnloadedClassCount() | long | Tổng số class đã unload kể từ khi JVM chạy |
| isVerbose() | boolean | Kiểm tra verbose class-loading tracing đang bật hay tắt |
| setVerbose(boolean) | void | Bật hoặc tắt verbose class-loading tracing |

Ba bộ đếm này có phạm vi toàn JVM. Chúng không chỉ đếm class của package ứng dụng; các class thư viện, framework và JDK cũng được tính.

Một class được định nghĩa bởi hai class loader khác nhau là hai class khác nhau trong JVM, dù chúng có cùng tên nhị phân. Vì vậy, ứng dụng plugin hoặc container có thể có nhiều bản định nghĩa của cùng một tên class.

### Phân biệt tổng số class và số class hiện tại

Ví dụ giả định:

| Thời điểm | Current loaded | Total loaded | Total unloaded |
|---|---:|---:|---:|
| Sau khởi động | 5.000 | 5.000 | 0 |
| Sau khi nạp plugin | 5.400 | 5.400 | 0 |
| Sau khi gỡ plugin và class loader được thu hồi | 5.050 | 5.400 | 350 |
| Sau khi nạp phiên bản plugin mới | 5.430 | 5.780 | 350 |

Các số trên chỉ minh họa cách đọc. Chúng không phải benchmark hoặc kết quả từ một ứng dụng thực tế.

Ở ví dụ này, tổng số class đã nạp tiếp tục tăng vì JVM đã nạp thêm class mới. Số class hiện tại giảm sau khi class loader cũ được thu hồi và các class của nó được unload. Khi plugin mới được nạp, cả current và total lại tăng.

## 3. Mở JConsole và kết nối với ứng dụng

JConsole nằm trong thư mục bin của JDK. Kiểm tra JDK trước:

~~~bash
java --version
jconsole -help
~~~

### Kết nối local

Mở cửa sổ chọn process:

~~~bash
jconsole
~~~

Chọn ứng dụng Java trong danh sách Local Process rồi nhấn Connect. Danh sách local thường chỉ hiển thị các JVM có thể quan sát bằng cùng user ID với JConsole.

Nếu đã biết PID của ứng dụng, có thể kết nối trực tiếp:

~~~bash
jconsole 12345
~~~

Thay 12345 bằng PID thực tế. Ứng dụng mục tiêu và JConsole phải chạy bằng cùng user ID. JVM phải hỗ trợ attach và cho phép management agent được bật; một process không attachable có thể không kết nối được.

Có thể tìm PID bằng:

~~~bash
jps -l
~~~

Hoặc dùng công cụ process của hệ điều hành. Luôn xác minh đúng process trước khi kết nối; PID có thể được tái sử dụng sau khi ứng dụng kết thúc.

### Kết nối remote

Để kết nối tới JMX agent trên máy khác:

~~~bash
jconsole app-host.example:7091
~~~

Host và port phải khớp JMX agent đã cấu hình khi JVM mục tiêu khởi chạy. Có thể kết nối bằng JMX service URL qua hộp thoại Remote Process.

Remote JMX cần được cấu hình và bảo vệ theo chính sách vận hành: bật authentication, dùng TLS khi phù hợp, giới hạn firewall và chỉ cho phép mạng quản trị truy cập. Không mở JMX endpoint không xác thực ra Internet hoặc mạng không tin cậy.

### Chọn chu kỳ cập nhật

Mặc định JConsole cập nhật dữ liệu theo chu kỳ 4 giây. Có thể thay đổi bằng tùy chọn:

~~~bash
jconsole -interval=2 12345
~~~

Lệnh trên yêu cầu cập nhật khoảng 2 giây một lần. Chu kỳ ngắn hơn giúp biểu đồ phản hồi nhanh hơn nhưng tăng số lần truy vấn và lượng dữ liệu quản trị. Nó vẫn là lấy mẫu định kỳ, không phải ghi lại mọi sự kiện class load/unload.

### Chọn tab Classes

Sau khi kết nối:

1. Chọn tab **Classes**.
2. Quan sát đường đỏ Total Loaded và đường xanh Loaded.
3. Đọc ba số Current classes loaded, Total classes loaded và Total classes unloaded trong Details.
4. Chọn Time Range phù hợp để xem khoảng thời gian cần điều tra.
5. Nếu cần lưu dữ liệu, nhấp chuột phải lên biểu đồ và chọn **Save data as...** để xuất CSV.

CSV có cột thời gian và các chuỗi dữ liệu của biểu đồ, có thể mở bằng spreadsheet để so sánh các khoảng thời gian.

## 4. Cách đọc xu hướng trên biểu đồ

Không nên đánh giá chỉ bằng một điểm dữ liệu. Hãy quan sát biểu đồ qua giai đoạn startup, warm-up, tải ổn định, redeploy hoặc thay đổi cấu hình.

### Trường hợp A: số class tăng lúc khởi động rồi ổn định

Đây thường là hành vi bình thường. JVM và framework nạp class khi ứng dụng khởi động, khởi tạo dependency hoặc xử lý request đầu tiên. Sau giai đoạn warm-up, số class hiện tại có thể ổn định.

Không cần cố làm cho đường đỏ và đường xanh nằm ngang ngay từ giây đầu tiên.

### Trường hợp B: Total Loaded tăng nhưng Current Loaded gần như ổn định

Điều này cho thấy JVM tiếp tục nạp class mới trong khi một số class cũ được unload, hoặc số class hiện tại thay đổi ít vì hai xu hướng bù trừ nhau.

Các nguyên nhân có thể gồm:

- Proxy hoặc class được tạo động.
- Framework nạp implementation theo yêu cầu.
- Plugin được nạp và gỡ theo vòng đời.
- Hot reload hoặc redeploy module.
- Nhiều class loader định nghĩa các class cùng tên.

Đây không tự động là lỗi. Cần xác định việc nạp class mới có phù hợp với hoạt động nghiệp vụ hay không.

### Trường hợp C: Current Loaded tăng liên tục và không giảm

Đây là dấu hiệu nên điều tra nếu xu hướng kéo dài sau giai đoạn warm-up hoặc lặp lại sau mỗi lần redeploy.

Nguyên nhân có thể là:

- Ứng dụng tạo class hoặc proxy mới không giới hạn.
- Plugin được nạp nhiều lần nhưng class loader cũ vẫn còn được giữ.
- Thread, ThreadLocal hoặc static registry giữ tham chiếu tới class loader.
- Framework tạo class loader mới cho mỗi lần reload nhưng không giải phóng loader cũ.
- Một cache hoặc registry giữ đối tượng có tham chiếu ngược đến class loader.

Class tab chỉ cho biết số lượng class hiện tại tăng. Nó không chứng minh nguyên nhân là class loader leak.

### Trường hợp D: Total Unloaded tăng và Current Loaded giảm

Điều này cho thấy JVM đã unload class. Với class do ứng dụng hoặc plugin định nghĩa, việc unload thường chỉ có thể xảy ra khi class loader định nghĩa chúng không còn được giữ sống và JVM thực hiện quá trình thu hồi phù hợp.

Việc class loader trở nên không còn reachable không đồng nghĩa class được unload ngay lập tức. Thời điểm thu hồi phụ thuộc garbage collector, cấu hình và implementation JVM. Gọi System.gc() cũng không bảo đảm class sẽ được unload.

### Trường hợp E: số class đột ngột tăng mạnh

Có thể là:

- Một module lớn được khởi tạo lần đầu.
- Một plugin hoặc framework mới được nạp.
- Một lần redeploy hoặc reload.
- Một tính năng tạo nhiều proxy/generated class.
- JConsole attach vào JVM và bật management agent, làm JVM nạp thêm một số class phục vụ quản lý.

Hãy đối chiếu với thời điểm deploy, log ứng dụng, hoạt động plugin và thay đổi cấu hình trước khi kết luận có sự cố.

## 5. Class loading và class unloading diễn ra như thế nào?

JVM nạp class thông qua class loader. Khi ứng dụng tham chiếu đến class lần đầu hoặc framework chủ động nạp class, JVM có thể định nghĩa class trong class loader tương ứng.

Một class có danh tính được xác định bởi tên nhị phân và defining class loader. Do đó, hai class cùng tên nhưng do hai class loader khác nhau định nghĩa không phải cùng một class theo quy tắc định danh của JVM.

### Class unloading phụ thuộc vòng đời class loader

Trong Java, class không được ứng dụng yêu cầu unload trực tiếp bằng một lệnh API thông thường. JVM có thể unload các class khi class loader định nghĩa chúng đủ điều kiện được thu hồi.

Ví dụ, một plugin được nạp bằng URLClassLoader riêng. Khi gỡ plugin, ứng dụng phải đóng loader nếu cần, xóa các tham chiếu đến loader, dừng thread thuộc plugin và giải phóng registry/cache. Nếu một đối tượng bên ngoài vẫn giữ tham chiếu đến class loader, loader có thể tiếp tục reachable và các class của nó không được unload.

### Những tham chiếu thường giữ class loader ngoài ý muốn

- Static field trong class được nạp bởi class loader sống lâu hơn.
- Thread hoặc ThreadLocal còn giữ class/instance của plugin.
- Executor, timer hoặc scheduler vẫn chạy task của plugin.
- Context ClassLoader của thread chưa được khôi phục.
- JDBC driver hoặc logging provider được đăng ký nhưng không deregister.
- MBean, listener, callback hoặc shutdown hook còn đăng ký.
- Cache, reflection metadata hoặc framework registry giữ class/loader.

Class tab không thể chỉ ra các tham chiếu này. Cần dùng class loader statistics, heap dump, JFR hoặc phân tích GC roots để tìm nguyên nhân.

## 6. Dùng Verbose Output đúng cách

Hộp chọn **Verbose Output** trên Classes tab bật verbose class-loading tracing cho JVM mục tiêu.

Trong Java API, chức năng tương ứng là:

~~~java
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

bean.setVerbose(true);
~~~

Kiểm tra trạng thái:

~~~java
boolean enabled = bean.isVerbose();
~~~

Tắt lại:

~~~java
bean.setVerbose(false);
~~~

Khi bật, JVM thường phát thông báo mỗi khi class được nạp. Nội dung và output stream phụ thuộc implementation; thông thường thông tin được ghi vào output của JVM.

### Vì sao không nên bật liên tục trên production?

- Một ứng dụng lớn có thể nạp rất nhiều class.
- Log có thể tăng nhanh và gây tốn dung lượng.
- Ghi log dày có thể tăng I/O và overhead.
- Log class loading có thể làm lộ package, đường dẫn hoặc cấu trúc nội bộ.
- Verbose tracing là thay đổi toàn JVM, ảnh hưởng mọi thành phần trong process.

Chỉ bật trong khoảng thời gian điều tra cần thiết, xác định nơi output được ghi, giới hạn dung lượng và tắt lại sau khi thu thập đủ bằng chứng.

Một cách khác là bật unified logging ngay khi khởi chạy JVM:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Để theo dõi class unloading:

~~~bash
java -Xlog:class+unload=info -jar app.jar
~~~

Các lệnh này ghi sự kiện class load hoặc unload vào output logging đã cấu hình. Nếu ghi ra file, nên cấu hình rotation và retention phù hợp. Chỉ bật mức log cần thiết vì output có thể rất lớn.

## 7. Đọc ClassLoadingMXBean bằng Java

JConsole dùng cùng các chỉ số mà chương trình Java có thể truy cập qua JMX. Ví dụ Java 17+ sau đây in số class hiện tại, tổng số class đã nạp và số class đã unload mỗi 5 giây.

Tạo file **ClassTabDemo.java**:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class ClassTabDemo {
    public static void main(String[] args) throws InterruptedException {
        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("READY");

        while (true) {
            System.out.printf(
                    "current=%d total=%d unloaded=%d%n",
                    bean.getLoadedClassCount(),
                    bean.getTotalLoadedClassCount(),
                    bean.getUnloadedClassCount()
            );

            Thread.sleep(5_000);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 ClassTabDemo.java
~~~

Chạy:

~~~bash
java ClassTabDemo
~~~

Output có dạng:

~~~text
READY
current=... total=... unloaded=...
current=... total=... unloaded=...
~~~

Các giá trị số thay đổi theo JDK, thời điểm khởi chạy và class đã được nạp. Dấu ba chấm trong output trên biểu thị giá trị runtime, không phải ký tự chương trình in ra.

Trong khi chương trình còn chạy, mở terminal khác:

~~~bash
jps -l
~~~

Tìm PID của ClassTabDemo rồi mở JConsole:

~~~bash
jconsole <pid>
~~~

Chọn tab **Classes** để xem biểu đồ. So sánh các chỉ số trên JConsole với dòng output của chương trình. Sau khi hoàn tất, nhấn Ctrl+C ở terminal chạy ClassTabDemo để dừng lab.

### Tại sao số liệu trong lab không cố định?

JVM nạp các class khác nhau theo version, startup path và runtime environment. Khi JConsole kết nối, management agent cũng có thể được bật động nếu JVM hỗ trợ attach; thao tác này có thể khiến một số class quản lý được nạp thêm. Vì vậy, không dùng một con số cố định làm expected output cho mọi máy.

## 8. Xem ClassLoadingMXBean trong MBeans tab

Ngoài Classes tab, có thể xem cùng các thuộc tính trong MBeans tab:

1. Chọn **MBeans**.
2. Mở domain **java.lang**.
3. Chọn type **ClassLoading**.
4. Xem các thuộc tính LoadedClassCount, TotalLoadedClassCount, UnloadedClassCount và Verbose.

Các thuộc tính này tương ứng với những phương thức của ClassLoadingMXBean. Verbose là thuộc tính có thể thay đổi; khi sửa nó, JConsole gọi cơ chế bật/tắt verbose class-loading tracing trên JVM mục tiêu.

MBeans tab cung cấp quyền truy cập rộng hơn vào platform MXBeans và application MBeans. Chỉ thay đổi thuộc tính khi hiểu rõ tác động; không dùng JConsole như công cụ thử nghiệm tùy tiện trên production.

## 9. Giới hạn của Class tab

Class tab là màn hình quan sát số lượng class, không phải trình phân tích class loader hoặc profiler.

Nó không hiển thị trực tiếp:

- Tên từng class đang được nạp.
- Class loader định nghĩa từng class.
- Quan hệ parent/child giữa các class loader.
- Nguồn JAR hoặc module của từng class.
- Số byte metadata của từng class.
- Retained memory do class loader giữ.
- Object hoặc reference đang ngăn class loader được thu hồi.
- Stack trace tại thời điểm class được nạp.
- Nguyên nhân cụ thể khiến class unload hoặc không unload.

Class tab cũng không đo trực tiếp Metaspace usage. Muốn xem memory pool, chuyển sang Memory tab; muốn tìm class loader và class cụ thể, dùng diagnostic tools khác.

### Dữ liệu được lấy mẫu

Biểu đồ cập nhật theo chu kỳ JConsole. Một đợt load/unload rất ngắn có thể xảy ra giữa hai lần lấy mẫu. Đường biểu diễn cho thấy xu hướng, không phải timeline chính xác của từng sự kiện.

Muốn có sự kiện chi tiết, dùng unified logging hoặc JFR. Không dùng đường biểu diễn 4 giây một lần để suy ra chính xác thời điểm class được nạp.

### Không thể kết luận memory leak từ một biểu đồ

Current Loaded tăng có thể do startup, warm-up hoặc framework hợp lệ. Total Loaded tăng là điều bình thường khi ứng dụng tiếp tục nạp class động. Class loader leak chỉ là một giả thuyết khi số class hiện tại tăng dai dẳng trong cùng workload và không giảm sau các vòng đời unload/redeploy.

Cần kết hợp số liệu với class loader statistics, heap dump, GC roots, JFR và lifecycle của ứng dụng.

## 10. Chẩn đoán class loader bằng jcmd

Khi Class tab cho thấy xu hướng bất thường, dùng jcmd để xem sâu hơn.

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Xem thống kê tất cả class loader:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Lệnh này cho biết thống kê class loader của JVM, hữu ích khi nghi ngờ số lượng loader tăng hoặc loader cũ còn tồn tại.

Xem cây class hierarchy:

~~~bash
jcmd <pid> VM.class_hierarchy
~~~

Lệnh này in danh sách class đã nạp theo cấu trúc hierarchy và thông tin class loader tương ứng. Output có thể lớn khi ứng dụng nạp nhiều class; hãy kiểm tra help và tác động của command trước khi chạy trên production.

Xem help của JVM mục tiêu:

~~~bash
jcmd <pid> help VM.classloader_stats
jcmd <pid> help VM.class_hierarchy
~~~

Trong OpenJDK 24.0.2 đã kiểm tra, VM.classloader_stats có impact Low; VM.class_hierarchy có impact Medium tùy số class được nạp. Mức tác động có thể khác theo runtime.

## 11. Dùng JFR khi cần lịch sử class loading chi tiết

Java Flight Recorder có thể thu thập event về class loading, class unloading, class loader statistics và class loading statistics.

Bắt đầu recording có thời hạn:

~~~bash
jcmd <pid> JFR.start name=class-audit settings=profile class-loading=true duration=60s filename=class-audit.jfr
~~~

Lệnh yêu cầu ghi trong 60 giây và lưu file class-audit.jfr. Profile recording có thể có overhead cao hơn default; chỉ dùng trong khoảng thời gian cần thiết và đánh giá tác động trước khi chạy production.

Đọc các event liên quan:

~~~bash
jfr print --events jdk.ClassLoad,jdk.ClassUnload,jdk.ClassLoaderStatistics,jdk.ClassLoadingStatistics class-audit.jfr
~~~

Tên event có thể kiểm tra trong metadata của JDK:

~~~bash
jfr metadata
~~~

JFR cung cấp timestamp và event detail hữu ích hơn bộ đếm tổng hợp trên Class tab. Tuy nhiên, tập event được ghi phụ thuộc recording settings; nếu event không được bật, file sẽ không có dữ liệu tương ứng.

## 12. Kết hợp Class tab với các tab JConsole khác

Class loading thường liên quan đến memory, thread và hoạt động ứng dụng. Hãy dùng các tab khác để kiểm tra giả thuyết:

| Tab | Dữ liệu | Cách kết hợp với Classes |
|---|---|---|
| Overview | CPU, memory, thread và class summary | Xem thời điểm class count tăng có trùng với CPU/memory spike không |
| Memory | Heap, nonheap và memory pools | Kiểm tra Metaspace cùng thời điểm class count tăng |
| Threads | Thread count và stack trace | Tìm thread/plugin task còn chạy sau khi redeploy |
| Classes | Current/total/unloaded class count | Xác định xu hướng class loading |
| VM | JVM version, arguments, uptime và summary | Đối chiếu runtime, flags và thời gian chạy |
| MBeans | Platform/application MXBeans | Đọc thuộc tính và thao tác quản trị sâu hơn |

Ví dụ, nếu current loaded tăng sau mỗi lần redeploy, đồng thời Metaspace tăng và class loader statistics cho thấy nhiều loader cũ, cần điều tra vòng đời plugin, thread, ThreadLocal và registry.

Nếu current loaded tăng nhưng Metaspace ổn định và xu hướng dừng sau warm-up, đó có thể chỉ là hoạt động nạp class bình thường. Không kết luận chỉ dựa vào một metric.

## 13. Bảo mật và tác động vận hành

JConsole có thể kết nối và quản lý JVM, không chỉ đọc biểu đồ. Một số thao tác qua MBeans có thể thay đổi thuộc tính hoặc gọi operation của JVM/application.

Các nguyên tắc:

- Chỉ cấp quyền JMX cho tài khoản vận hành được phê duyệt.
- Với remote JMX, bật authentication và TLS theo chính sách.
- Giới hạn port bằng firewall và network segmentation.
- Không để management endpoint không xác thực trên mạng công khai.
- Hạn chế bật verbose class loading trên production.
- Lưu CSV và log ở nơi có quyền truy cập phù hợp.
- Không đưa command line, path hoặc thông tin nhạy cảm vào báo cáo công khai.
- Đóng kết nối JConsole khi hoàn tất.
- Ưu tiên chạy JConsole trên máy quản trị riêng khi giám sát production.

Oracle lưu ý JConsole tiêu thụ tài nguyên đáng kể; local monitoring hữu ích cho development/prototype nhưng không được khuyến nghị cho production. Remote monitoring giúp tách tải của giao diện JConsole khỏi máy đang chạy ứng dụng.

## 14. Lỗi thường gặp

### Không thấy process trong Local Process

Kiểm tra JConsole và JVM mục tiêu có cùng user ID không. Xác nhận process còn chạy, JVM có hỗ trợ attach và management agent có thể được bật. Nếu process không attachable và agent chưa được bật từ lúc khởi chạy, JConsole có thể không kết nối được.

### Classes tab không có dữ liệu hoặc không cập nhật

Kiểm tra kết nối JMX còn hoạt động, JVM chưa kết thúc và management agent không bị ngắt. Chờ ít nhất một vài chu kỳ cập nhật. Kiểm tra MBeans tab có domain java.lang và type ClassLoading hay không.

### Current Loaded tăng nhưng không thấy unload

Có thể ứng dụng chưa unload class, class loader vẫn reachable hoặc JVM chưa thực hiện quá trình thu hồi. Kiểm tra class loader statistics, JFR và lifecycle plugin. Không ép System.gc() rồi kết luận nếu class count không giảm ngay.

### Total Loaded tăng nhưng Current Loaded không đổi

Đây có thể là class churn: JVM nạp class mới trong khi unload class cũ. Kiểm tra plugin, proxy, redeploy và framework dynamic loading.

### Verbose Output không hiện trong JConsole

Checkbox bật tracing trên JVM; output stream phụ thuộc implementation và thường được ghi vào output/log của process mục tiêu. Kiểm tra log của ứng dụng và bảo đảm user có quyền đọc. Tắt verbose khi không còn cần.

### Remote connection thất bại

Kiểm tra host, port, JMX agent, firewall, DNS, authentication và TLS. Không tắt authentication hoặc mở port công khai chỉ để xử lý nhanh lỗi kết nối.

### JConsole làm ứng dụng chậm

JConsole có overhead riêng và việc attach có thể bật management agent hoặc nạp thêm class. Giảm tần suất cập nhật, giới hạn thời gian quan sát và chuyển sang JFR/JMX monitoring phù hợp nếu cần thu thập dài hạn.

## 15. Quy trình điều tra class loading đề xuất

1. Ghi nhận JDK vendor/version, JVM uptime, PID và thời điểm bắt đầu quan sát.
2. Kết nối JConsole bằng tài khoản có quyền phù hợp.
3. Chọn Classes và quan sát cả Total Loaded, Current Loaded và Total Unloaded.
4. Lưu CSV nếu cần so sánh các khoảng thời gian.
5. Đối chiếu thời điểm tăng class với startup, warm-up, redeploy và plugin activity.
6. Nếu Current Loaded tăng dai dẳng, kiểm tra Memory tab và Metaspace.
7. Chạy jcmd VM.classloader_stats để tìm loader bất thường.
8. Dùng VM.class_hierarchy hoặc JFR nếu cần thêm chi tiết.
9. Kiểm tra thread, ThreadLocal, static registry, listener, MBean và cache có thể giữ class loader.
10. Sửa lifecycle/cleanup và lặp lại cùng quy trình để xác nhận xu hướng đã cải thiện.
11. Tắt verbose tracing, đóng JConsole và lưu bằng chứng theo retention policy.

## 16. Checklist khi sử dụng Class tab

- Kết nối đúng JVM và đúng môi trường.
- Hiểu đường đỏ là tổng số class đã nạp, kể cả class đã unload.
- Hiểu đường xanh là số class hiện đang nạp.
- Ghi lại Current, Total Loaded và Total Unloaded.
- Xem xu hướng qua startup, warm-up và redeploy.
- Không kết luận memory leak từ một snapshot.
- Nhớ cùng tên class do hai loader định nghĩa là hai class khác nhau.
- Dùng Verbose Output có giới hạn thời gian.
- Dùng CSV khi cần so sánh dữ liệu.
- Kiểm tra Metaspace ở Memory tab.
- Dùng jcmd VM.classloader_stats khi cần phân tích loader.
- Dùng JFR hoặc class load/unload logging khi cần event detail.
- Bảo vệ remote JMX bằng authentication, TLS và firewall.
- Đóng kết nối và tắt tracing khi kết thúc.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Class loading | Quá trình JVM nạp và định nghĩa class |
| Class unloading | Quá trình JVM gỡ class khi class loader đủ điều kiện được thu hồi |
| Current classes loaded | Số class hiện đang được nạp |
| Total classes loaded | Tổng số class đã nạp kể từ khi JVM chạy |
| Total classes unloaded | Tổng số class đã unload kể từ khi JVM chạy |
| ClassLoadingMXBean | Platform MXBean cung cấp bộ đếm class loading |
| JConsole | Công cụ GUI giám sát và quản lý Java qua JMX |
| JMX | Java Management Extensions |
| MBean | Đối tượng quản lý được đăng ký trong MBean Server |
| Class loader | Thành phần nạp và định nghĩa class |
| Class loader leak | Class loader cũ không được thu hồi do còn tham chiếu |
| Metaspace | Native memory chứa metadata class trong HotSpot hiện đại |
| Verbose class loading | Chế độ ghi thông tin khi class được nạp |
| JFR | Java Flight Recorder, công cụ ghi runtime events |
| Class churn | Hiện tượng class được nạp và unload liên tục |
| PID | Process ID của JVM process |

Class tab trong JConsole là công cụ quan sát nhanh xu hướng class loading. Hãy đọc đồng thời tổng số class đã nạp, số class hiện tại và số class đã unload; khi thấy xu hướng bất thường, kết hợp ClassLoadingMXBean, jcmd, JFR và phân tích class loader để tìm nguyên nhân.

## Tài liệu tham khảo

- Oracle JDK 24 — [Using JConsole](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- Oracle JDK 24 — [The jconsole Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html)
- Oracle Java SE 24 API — [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle JDK 24 — [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)