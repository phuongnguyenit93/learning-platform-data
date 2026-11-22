# 17.8 ClassLoadingMXBean, VM.classloader_stats và log class load hoặc unload

## Mục tiêu học tập

Trong Java, **nạp lớp (class loading)** diễn ra khi JVM cần định nghĩa một lớp. Với ứng dụng lâu sống, lượng lớp đang được nạp, số class loader và khả năng **dỡ lớp (class unloading)** có thể liên quan trực tiếp đến tốc độ khởi động, cơ chế plugin/hot reload, việc sinh proxy/lambda động và sử dụng **Metaspace**. Nhưng “số lớp tăng” **không tự động có nghĩa memory leak**.

Bài học này cung cấp một quy trình chẩn đoán thống nhất bằng ba loại bằng chứng:

1. **`ClassLoadingMXBean`**: bộ đếm mức JVM — bao nhiêu lớp đang loaded, tổng lượt loaded và tổng lượt unloaded từ lúc khởi động.
2. **`jcmd <pid> VM.classloader_stats`**: ảnh chụp chi tiết theo class loader và ClassLoaderData, bao gồm số lớp và thông tin các metaspace chunks/blocks.
3. **Unified logging `class+load` / `class+unload`**: dòng thời gian sự kiện — lớp nào được nạp hoặc dỡ, vào lúc nào và đôi khi từ nguồn nào.

Hoàn thành bài, bạn có thể đọc đúng ý nghĩa của các số đo, bật logging ở mức phù hợp, chạy thí nghiệm Java 17+ với nhiều `URLClassLoader`, phát hiện xu hướng class loader retention và phân biệt class-loading churn hợp lệ với khả năng leak.

**Phạm vi:** API `ClassLoadingMXBean` thuộc Java SE (module `java.management`). Các lệnh `VM.classloader_stats`, `VM.log` và cờ `-Xlog` được minh họa trên **HotSpot/OpenJDK 17+**; kết quả, tên cột và khả năng dùng lệnh phụ thuộc JDK và môi trường. Ví dụ đã được biên dịch với `javac --release 17` và chạy trên HotSpot JDK 24. Không suy diễn rằng mọi JVM đều có cùng lệnh HotSpot.

## 1. Bản chất của class loading và class unloading

### 1.1 Tên lớp không đủ để xác định một runtime class

Trong JVM, định danh của một lớp về bản chất gắn với **tên nhị phân** và **class loader định nghĩa nó**. Hai class loader khác nhau có thể định nghĩa hai lớp cùng tên `lab.PluginThing` nhưng chúng là **hai runtime classes khác nhau**, có metadata riêng và không hoán đổi kiểu với nhau chỉ vì tên giống.

Một ứng dụng có thể sử dụng:

- **Bootstrap class loader** để nạp lớp nền của Java runtime.
- **Platform class loader** cho các module nền tảng thích hợp.
- **Application class loader** cho class path hoặc module path thông thường.
- **Custom class loader** như `URLClassLoader`, loader của application server, plugin system, framework code generation hoặc môi trường hot reload.

Thông thường loader tuân theo cơ chế delegation đến parent; cũng có loader sử dụng chiến lược riêng. Khi phân tích, cần phân biệt **loại loader** (`URLClassLoader`, `AppClassLoader`, …), **từng instance loader** và các lớp do loader đó định nghĩa. “Nạp cùng tên một lần nữa” có thể hợp lệ nếu loader khác, nhưng đáng điều tra nếu cứ tạo thêm loader mà không giải phóng được.

### 1.2 Các bước khác nhau, không nên dùng từ “load” cho tất cả

Một cách nhìn khái quát:

~~~text
Class loader được JVM yêu cầu định nghĩa lớp
                   |
                 Loading
                   |
           Linking (verify,
         prepare, resolve nếu cần)
                   |
          Initialization khi
             điều kiện yêu cầu
                   |
         Được dùng trong runtime
                   |
   Loader và các lớp của nó không còn
      bị giữ sống theo điều kiện GC
                   |
       Có thể class unloading khi
         JVM/GC hỗ trợ và chọn dỡ
~~~

- **Loading**: tìm/đọc biểu diễn class và tạo định nghĩa trong JVM.
- **Linking**: gồm verification, preparation và resolution (thời điểm resolution có thể khác).
- **Initialization**: chạy logic khởi tạo tĩnh nếu cần; **không phải** cứ class loading là static initializer lập tức chạy trong cùng ngữ cảnh.
- **Unloading**: thu hồi metadata của lớp khi các điều kiện về reachability và chính sách JVM/GC cho phép; không xảy ra ngay khi một biến trỏ tới loader ra khỏi scope.

`Class.forName("pkg.Name", true, loader)` có thể yêu cầu class initialization. `ClassLoader.loadClass(...)` thông thường không nhất thiết chủ động initialization. Đừng kết luận từ một dòng log `class,load` rằng static initializer đã chạy hoặc rằng class đó còn sống mãi.

### 1.3 Liên hệ đến Metaspace và heap

Metadata lớp của HotSpot được lưu trong các cấu trúc native, đặc biệt là Metaspace (và compressed class space tùy cấu hình). Trong khi đó, object `ClassLoader`, đối tượng `java.lang.Class` và nhiều cấu trúc tham chiếu từ ứng dụng là đối tượng Java/heap. Một loader bị giữ sống có thể gián tiếp giữ metadata của rất nhiều lớp.

**Nhưng:** `ClassLoadingMXBean.getLoadedClassCount()` không cho biết dung lượng Metaspace bằng byte, còn `VM.classloader_stats` không trực tiếp đo retained heap của mọi object thuộc loader. Khi cần chứng minh leak, phải ghép bằng chứng class loader + bộ nhớ + tham chiếu giữ sống.

## 2. Chọn công cụ theo câu hỏi chẩn đoán

| Câu hỏi | Công cụ ưu tiên | Dữ liệu chính | Không trả lời trực tiếp |
| --- | --- | --- | --- |
| Tổng số lớp đang loaded có tăng theo thời gian không? | `ClassLoadingMXBean` | `loadedClassCount` | Loader nào giữ chúng, tổng byte |
| Tốc độ sinh lớp / unload có cao không? | `ClassLoadingMXBean` đọc định kỳ | Chênh lệch `totalLoaded` và `unloaded` theo thời gian | Từng tên lớp hay call site |
| Loader nào đang có nhiều lớp, số loader có tăng? | `VM.classloader_stats` | Loader, parent, CLD, classes, chunk/block stats | Toàn bộ GC roots của loader |
| Tên lớp nào được load, từ nguồn nào, vào lúc nào? | `-Xlog:class+load=info` | Timeline class load | Lý do ứng dụng yêu cầu lớp |
| Lớp nào thực sự bị dỡ? | `-Xlog:class+unload=info` | Timeline class unload đã xảy ra | Vì sao có/không có GC |
| Metaspace đang reserve/commit/used bao nhiêu? | `jcmd <pid> VM.metaspace` và metrics bộ nhớ | Số liệu Metaspace | Đầy đủ referent giữ loader sống |
| Vì sao loader vẫn reachable? | Heap dump, reference paths, thread/context loader, framework metrics | Đường tham chiếu mạnh | Không thể suy ra chỉ từ class-loading counters |

**Phương pháp:** đo **xu hướng tổng quan** bằng MXBean, tìm **phân bố loader** bằng `VM.classloader_stats`, nhìn **sự kiện cụ thể** qua logs. Chỉ chuyển sang heap dump/reference analysis khi có giả thuyết rõ về retention.

## 3. `ClassLoadingMXBean`: ba bộ đếm cốt lõi

### 3.1 Cách truy cập API chuẩn

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
int current = bean.getLoadedClassCount();
long total = bean.getTotalLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

Đây là **snippet** dùng trong phương thức Java, không phải một chương trình độc lập; ví dụ có thể chạy nằm ở phần 7. JVM có **một** instance MXBean quản lý class loading, có thể truy cập trong process bằng `ManagementFactory` hoặc qua JMX platform MBeanServer bằng ObjectName:

~~~text
java.lang:type=ClassLoading
~~~

Ba chỉ số có nghĩa chính xác:

| Phương thức | Kiểu | Diễn giải | Xu hướng thường gặp |
| --- | --- | --- | --- |
| `getLoadedClassCount()` | `int` | Số lớp đang loaded tại thời điểm đo | Tăng, giảm hoặc ổn định |
| `getTotalLoadedClassCount()` | `long` | Tổng số lớp từng loaded **từ lúc JVM khởi động** | Không giảm |
| `getUnloadedClassCount()` | `long` | Tổng số lớp đã unloaded **từ lúc JVM khởi động** | Không giảm |

**Không** đọc `getTotalLoadedClassCount()` như “số lớp đang chiếm bộ nhớ”. Nó là số tích lũy. Nếu ứng dụng tạo/dỡ 10.000 lớp trong ngày, total có thể tăng 10.000 nhưng số lớp đang sống cuối ngày hầu như không đổi.

Các giá trị có thể thay đổi trong lúc đọc từng getter. Ba lần gọi liên tiếp **không phải một ảnh chụp nguyên tử** cùng thời điểm; không đặt yêu cầu rằng một đẳng thức số học giữa ba giá trị phải luôn chính xác đến từng lớp khi hệ thống đang load/unload đồng thời.

### 3.2 Ví dụ cách đọc chênh lệch theo thời gian

Giả sử hai lần lấy mẫu trên **cùng JVM** cách nhau đúng 60 giây:

| Chỉ số | Tại `t0` | Tại `t1` | Delta |
| --- | ---: | ---: | ---: |
| `getLoadedClassCount()` | 8.200 | 8.280 | +80 |
| `getTotalLoadedClassCount()` | 12.000 | 12.500 | +500 |
| `getUnloadedClassCount()` | 3.800 | 4.220 | +420 |

Trong cửa sổ này, JVM đã load thêm khoảng **500 lớp**, unload **420 lớp** và số lớp đang loaded tăng **80**. Tốc độ load trung bình là khoảng **8,33 lớp/giây**; tốc độ unload trung bình **7 lớp/giây**. Đây là **số liệu giả định để luyện cách đọc**, không phải baseline chuẩn.

Một cách gần đúng:

~~~text
load_rate ≈ (totalLoaded(t1) - totalLoaded(t0)) / (t1 - t0)
unload_rate ≈ (unloaded(t1) - unloaded(t0)) / (t1 - t0)
net_loaded_change = loadedNow(t1) - loadedNow(t0)
~~~

Cần cùng process và biết khoảng thời gian thực, tốt nhất là monotonic clock của hệ thống đo. Không lấy chênh lệch giữa hai JVM khác PID/restart rồi coi là rate. Sau restart, các bộ đếm tích lũy bắt đầu lại.

**Cách phân loại ban đầu:**

- **Total tăng, unloaded tăng tương ứng, current khá ổn định:** có **class loading churn**. Có thể là công việc hợp lệ (plugin/test/job) hoặc tạo lớp động quá thường xuyên gây CPU/GC overhead; chưa chứng minh leak.
- **Total tăng, current tăng kéo dài, unloaded gần như không tăng:** nghi class loader/class definitions bị giữ hoặc chưa đến thời điểm GC thích hợp. Kiểm tra số loader, thời gian chạy và Metaspace; không vội kết luận leak.
- **Current tăng mạnh ở startup rồi dừng:** có thể do khởi động lười, JIT/framework warmup, nạp các lớp/cấu trúc dùng lâu dài; có thể hoàn toàn bình thường.
- **Unloaded tăng theo đợt sau GC:** có thể là class unloading theo chu kỳ GC; không mong đợi unloading liên tục từng giây.

### 3.3 `isVerbose()` và `setVerbose(boolean)`

`ClassLoadingMXBean` còn cung cấp:

~~~java
boolean enabled = bean.isVerbose();
bean.setVerbose(true);
~~~

Đây chỉ là **snippet**. Theo API Java, verbose output và luồng xuất phụ thuộc implementation; thao tác `setVerbose` bật/tắt **toàn cục** trong JVM, có thể được nhiều thread gọi. Vì vậy **không dùng `setVerbose(true)` vô điều kiện trong production**, nhất là khi service load nhiều lớp.

Trên HotSpot hiện đại, **Unified Logging với `-Xlog`** thường phù hợp hơn vì lựa chọn được tag, level, output, decorator và file rotation. Dùng MXBean chủ yếu để **đọc số liệu** thay vì thay đổi trạng thái ghi log toàn cục. Nếu hệ thống đã có chính sách logging, không nên tùy ý gạt `setVerbose(false)` để “khôi phục”: có thể xung đột yêu cầu chẩn đoán từ component khác.

### 3.4 Đo qua JMX khi không muốn nhúng code

Tương tự các MXBean chuẩn khác, bean có thể được quan sát qua kênh JMX thích hợp, ví dụ công cụ JConsole/JMC hoặc hệ thống metrics bridge. ObjectName là `java.lang:type=ClassLoading` và các attribute tương ứng với getter. Điều kiện là cấu hình và quyền truy cập JMX đúng; **không mở JMX remote ra mạng công cộng chỉ để lấy class count**.

Khi xuất metrics sang dashboard, giữ PID/JVM start time trong nhãn hoặc metadata để phân biệt restart, và lấy rate từ các bộ đếm tích lũy thay vì vẽ `totalLoaded` như “currently loaded”.

## 4. `jcmd VM.classloader_stats`: đi từ tổng số lớp đến loader cụ thể

`VM.classloader_stats` là diagnostic command của HotSpot, in thống kê các class loader hiện có. Nó đặc biệt hữu ích khi `current` tăng bất thường và bạn nghi một framework tạo thêm class loader cho mỗi lần deploy/plugin/job.

### 4.1 Xác định PID và gọi lệnh

~~~sh
# Chạy cùng host/namespace và với quyền có thể attach JVM:
jcmd -l

# Thay <pid> bằng PID của process Java thực sự:
jcmd <pid> VM.classloader_stats

# Kiểm tra syntax/impact ngay trên JVM đích:
jcmd <pid> help VM.classloader_stats
~~~

`jcmd` thường đi kèm JDK. Nếu attach không được, kiểm tra user sở hữu process, namespace/container, đường dẫn JDK, việc `-XX:+DisableAttachMechanism` có được bật hay không và PID có còn tồn tại hay không. Không sử dụng PID của service khác chỉ vì tên gần giống.

Tài liệu Oracle liệt kê `VM.classloader_stats` là lệnh impact thấp, nhưng trong hệ thống có rất nhiều loader/classes và tải nhạy latency, vẫn nên thu thập có kiểm soát. Đây là **ảnh chụp**, không phải một stream events và không cho lịch sử của các loader đã bị dỡ.

### 4.2 Đọc ví dụ output thực tế

Trên HotSpot JDK 24, khi một Java demo giữ ba `URLClassLoader` sống, một phần report có dạng:

~~~text
ClassLoader         Parent              CLD*               Classes   ChunkSz   BlockSz  Type
0x...               0x...               0x...                    1      2048      1288  java.net.URLClassLoader
0x...               0x...               0x...                    1      6144      1288  java.net.URLClassLoader
0x...               0x...               0x...                    1      5120      1288  java.net.URLClassLoader
0x...               0x...               0x...                  852    ...       ...     <boot class loader>
...
Total = 6                                                   ...     ...       ...
ChunkSz: Total size of all allocated metaspace chunks
BlockSz: Total size of all allocated metaspace blocks (each chunk has several blocks)
~~~

Đây là **trích đoạn minh họa từ một lần đo**, đã rút gọn địa chỉ, một số dòng và số liệu; không phải kết quả cố định để so cho tất cả JDK. Số `Total = 6` trong ví dụ gốc đếm các mục class loader/data được report, không phải tổng số Java classes; tổng classes ở cột khác. Một report có thể có mục riêng cho hidden classes, bootstrap hoặc loader với `Classes=0`.

Đọc các cột:

| Cột | Ý nghĩa | Cần tránh |
| --- | --- | --- |
| `ClassLoader` | Địa chỉ/identifier mang tính nội bộ của loader theo bản HotSpot | Không dùng làm business ID hoặc lưu để so trực tiếp qua restart |
| `Parent` | Thông tin parent loader ở dạng nội bộ | Không khẳng định quan hệ ứng dụng chỉ từ một số hex |
| `CLD*` | Định danh ClassLoaderData native, dùng liên kết loader ↔ metadata | Không nhầm là địa chỉ `ClassLoader` object trên heap |
| `Classes` | Số classes được thống kê trong mục loader đó | Không phải số instance đối tượng Java |
| `ChunkSz` | Tổng size các **metaspace chunks** được cấp phát cho mục đó | Không phải bytes live của Java heap |
| `BlockSz` | Tổng size các **metaspace blocks** trong các chunks của mục đó | Không phải “số đối tượng”; chunk có thể chứa nhiều blocks |
| `Type` | Loại loader, ví dụ `java.net.URLClassLoader` | Nhiều instance có cùng tên Type |

Đơn vị và cách trình bày các size có thể khác giữa các JDK; đọc chú giải cuối report, **không mặc định KB hay MB**. Cột `Classes` có thể bao gồm các phân loại được JVM hiển thị riêng như hidden classes. Tổng các loader không nên bị đồng nhất máy móc với `ClassLoadingMXBean.getLoadedClassCount()` vì ngữ nghĩa/điểm lấy snapshot, cách tính hidden/array classes và việc class loading đang chạy có thể khác.

### 4.3 Tìm dấu hiệu đáng điều tra

Ở **hai mốc cùng tải và sau warmup**, bạn thấy số `java.net.URLClassLoader` hoặc loader tùy biến tăng từ 20 lên 200 trong khi ứng dụng chỉ có 20 plugin cố định. Đây là dấu hiệu mạnh để hỏi:

- Mỗi lần reload/deploy có tạo loader mới mà vẫn giữ loader cũ không?
- Còn thread/thread pool nào có `contextClassLoader` trỏ vào loader cũ?
- Có static cache, singleton, listener, service registry, timer, MBean, JDBC driver, thread local hoặc reflective method reference giữ class/loader không?
- Loader có còn các lớp do nó định nghĩa; metaspace dành cho chúng có tăng tương ứng?
- Sau khi ngừng churn và qua GC/class unloading, số loader có giảm không?

**Đừng suy từ một cột `ChunkSz` lớn ra nguyên nhân leak.** Chunks là tài nguyên quản lý Metaspace; size có thể cao do đã cấp phát cho loader hợp lệ, phân mảnh hay cấu trúc nội bộ. Cần xu hướng, thời gian sống và đường tham chiếu giữ loader.

### 4.4 Phối hợp với lệnh khác khi cần

~~~sh
# Tóm tắt Metaspace trên HotSpot hỗ trợ:
jcmd <pid> VM.metaspace basic

# Báo cáo chi tiết Metaspace và/hoặc phân bố theo loader:
jcmd <pid> VM.metaspace show-loaders

# Có thể xem cấu trúc loader trên các HotSpot hỗ trợ:
jcmd <pid> VM.classloaders
~~~

`VM.metaspace` xem bytes reserved/committed/used và các phần cấu trúc native; `VM.classloaders` nghiêng về cây/quan hệ loader. Những lệnh này **bổ sung** cho `VM.classloader_stats`; không tự tìm được GC root của loader. Trên bản JDK khác, kiểm tra `jcmd <pid> help VM.metaspace` hoặc `help VM.classloaders` trước khi dùng option.

Nếu cần so sánh footprint của VM trong phạm vi Native Memory Tracking, có thể dùng `VM.native_memory summary` **chỉ khi NMT đã bật khi JVM khởi động**. Không trộn `ClassLoadingMXBean` class count với bytes native mà không có metric riêng.

## 5. Unified Logging: quan sát class load và unload theo thời gian

Từ JDK 9, HotSpot hỗ trợ **Unified Logging `-Xlog`**. Đây là cách thuận tiện để ghi sự kiện load/unload có timestamp. Với JDK 17+:

~~~sh
# Thu class load và class unload ra một file:
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' -jar app.jar
~~~

`app.jar` là ứng dụng minh họa, thay bằng JAR thực tế. Trong shell hỗ trợ quote, toàn bộ `-Xlog:...` là **một JVM argument** và phải đứng **trước `-jar`**. Với Windows PowerShell, dùng single quote như trên; với Windows CMD, cần điều chỉnh cú pháp quote phù hợp. Nếu dùng Docker, file nằm trong filesystem của tiến trình JVM (có thể là trong container).

Hai tags quan trọng:

- **`class+load=info`:** log khi HotSpot load class, thường có tên lớp, source/module và timestamp theo decorator.
- **`class+unload=info`:** log khi class thực sự được unload. Nếu không có event, chưa có bằng chứng unload trong **khoảng log thu được**; không có nghĩa GC hoặc unloading “bị lỗi”.

Có thể giới hạn file log bằng rotation nếu hỗ trợ theo JDK:

~~~sh
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags:filecount=3,filesize=5M' -jar app.jar
~~~

Lệnh trên sử dụng **ba phần ngăn bằng dấu `:`** sau `-Xlog`: selection → output → decorators → output options (có filecount/filesize). Cú pháp đã được kiểm tra trên HotSpot JDK 24. File rolling có thể làm mất các class load events cũ; nếu điều tra sự cố hiếm, cần đồng bộ chiến lược retention với thời gian tái hiện.

### 5.1 Ví dụ log load

Trong thí nghiệm phần 7, sau khi chạy ba loader khác nhau, file có ba dòng dạng:

~~~text
[0.072s][info][class,load] lab.PluginThing source: file:/.../plugin/
[0.075s][info][class,load] lab.PluginThing source: file:/.../plugin/
[0.076s][info][class,load] lab.PluginThing source: file:/.../plugin/
~~~

Mốc thời gian, đường dẫn và mọi địa chỉ là **phụ thuộc máy/lần chạy**, còn điểm trọng tâm là **ba lần load cùng tên `lab.PluginThing`** do ba loader khác nhau định nghĩa. Nhìn thấy cùng tên xuất hiện ba lần chưa đủ chứng minh leak: chương trình thí nghiệm **cố ý** tạo ba loader.

Lưu ý: event `class+load` không nhất thiết in danh tính loader theo cách giúp phân biệt từng instance ở level `info`. Ghép với `VM.classloader_stats` và thời gian thu, hoặc dùng cấu hình logging chi tiết hơn khi cần và khi có thể chấp nhận overhead. `source: file:/...` là nguồn mã của lớp, **không phải GC root** hay bằng chứng loader sẽ tồn tại mãi.

### 5.2 Vì sao unload log có thể vắng mặt?

Unloading không phải lệnh đóng file, mà liên quan **class loader reachability** và cơ chế GC. Một số nguyên nhân:

1. Loader vẫn bị giữ từ static map/list, TCCL của thread, JMX/listener, scheduled task, callback hoặc object/class từ chính loader.
2. Workload vẫn đang sử dụng class hoặc loader, có stack/object tham chiếu còn sống.
3. Chưa diễn ra chu kỳ GC/class unloading phù hợp; GC có thể trì hoãn.
4. Tùy chọn JVM/collector hoặc chế độ VM đang không thực hiện class unloading.
5. Logging mới bật sau khi unload đã xảy ra, log bị rotate/truncated hoặc event filter chưa đúng.

**`URLClassLoader.close()` chỉ đóng các tài nguyên do loader mở; không ép JVM unload lớp.** Tương tự, gán biến thành `null` chỉ loại bỏ một cạnh tham chiếu, không chứng minh object không còn reachable. `System.gc()` hay `jcmd <pid> GC.run` là yêu cầu/biện pháp thử nghiệm có thể gây pause, **không bảo đảm** mọi lớp đủ điều kiện sẽ được unload đúng lúc.

### 5.3 Bật logging khi JVM đã chạy

Trên HotSpot hỗ trợ diagnostic command `VM.log`, có thể kiểm tra cấu hình hiện tại:

~~~sh
jcmd <pid> VM.log list
jcmd <pid> help VM.log
~~~

Một ví dụ kích hoạt log trên output console của JVM đích:

~~~sh
jcmd <pid> VM.log what=class+load=info,class+unload=info output=stdout decorators=uptime,level,tags
~~~

Lệnh được kiểm tra trên HotSpot JDK 24 và trả `Command executed successfully`. **Cẩn trọng:** nó thay đổi cấu hình logging của **JVM đích**, không phải chỉ in log vào terminal gọi `jcmd`. Trong container/server, `stdout` của JVM có thể đi vào hệ thống log khác; thao tác đổi output có thể tương tác với cấu hình logs sẵn có. Nên ghi lại trạng thái `VM.log list` trước thay đổi và lập phương án khôi phục chính xác, không gạt tắt các log hệ thống khác tùy tiện. Với điều tra tái hiện trong môi trường kiểm soát, bật `-Xlog` từ khởi động thường dễ lưu vết và kiểm soát hơn.

### 5.4 Level và chi phí vận hành

`info` thường đủ để biết tên và thời điểm lớp loaded/unloaded. `debug`/`trace` cho một số tag có thể tạo log rất lớn, tăng I/O và gây nhiễu. Không bật `-Xlog:class*=trace` trên production diện rộng khi chỉ cần xác nhận vài loader tăng. Sử dụng file rotation, khoảng thu hạn chế, kiểm tra dung lượng, và bảo vệ đường dẫn nếu tên module/class/source là thông tin nội bộ.

## 6. Phân biệt churn, retention và leak theo bằng chứng

### 6.1 Class loading churn (tạo/dỡ nhiều lớp)

Giả sử service liên tục xử lý rule expression hoặc sinh proxy động. `totalLoaded` tăng nhanh; sau các chu kỳ GC, `unloaded` cũng tăng; `current` dao động quanh một mức. Nhiều load/unload logs cùng tên lớp qua các loader khác nhau có thể đi kèm.

Tác động có thể bao gồm CPU cho verifier/linker/initializer, tạo metadata, GC class unloading, cache JIT mất hiệu lực khi loader biến mất. Đây có thể là **vấn đề hiệu năng**, ngay cả khi không có memory leak. Cần hỏi: có thể tái sử dụng loader/generated class/cache hợp lý không? Chi phí sinh class có đáng kể trong profile hay log startup không?

### 6.2 Class loader retention

Nếu một ứng dụng redeploy 10 lần và giữ 10 loader cũ, mỗi loader có thể duy trì nhiều định nghĩa lớp, static data và object gắn với chúng. Bộ đếm `current` tăng hoặc chững ở mức cao; `VM.classloader_stats` cho thấy các loader của phiên cũ còn sống; Metaspace có thể tăng và không thu hồi đủ.

Một số điểm giữ loader thường gặp:

~~~text
GC roots (static fields, live threads, native references...)
                       |
             App singleton / cache
                       |
             plugin Class<?> / instance
                       |
                ClassLoader
                       |
             Loaded classes / metadata
~~~

Hoặc:

~~~text
Live worker thread
        |
thread context class loader (TCCL)
        |
Old webapp/plugin class loader
        |
Metadata + classes belonging to old deployment
~~~

Đây là **mô hình minh họa**; đường tham chiếu thực phải được xác minh bằng heap dump/GC roots. Không cho rằng bất kỳ ThreadLocal hay singleton nào cũng giữ loader nếu đối tượng thực tế không còn liên quan. Cũng không kết luận leak chỉ vì loader của plugin đang cần được giữ để phục vụ tác vụ hợp lệ.

### 6.3 Class unloading bình thường

Nếu ứng dụng tắt plugin, hủy mọi tham chiếu tới loader/classes/instances rồi qua GC hỗ trợ unloading, log `class,unload` có thể xuất hiện; `unloaded` tăng và `current` có thể giảm. Nhưng:

- Không phải mọi lần GC đều unload classes.
- Metadata/Metaspace committed của JVM có thể không giảm ngay, ngay cả khi classes đã unload, do cơ chế chunk management hoặc retention.
- Một số classes được chia sẻ/loaded bởi loader nền tảng có vòng đời gần bằng JVM và không mong đợi unload trước khi process dừng.

Việc không thấy `class,unload` trong một khoảng đo ngắn **không đủ** để nói leak.

## 7. Bài thực hành Java 17+: ba class loader định nghĩa cùng một lớp

Thí nghiệm dùng hai file Java, biên dịch lớp plugin vào thư mục riêng, sau đó load `lab.PluginThing` bằng **ba instance `URLClassLoader`** với parent là platform loader. Chương trình giữ ba loader trong một list để bạn xem `VM.classloader_stats`, rồi cho phép bỏ tham chiếu. Mọi thành phần của bài thực hành dùng Java SE 17+; không phụ thuộc thư viện ngoài.

### 7.1 Tạo lớp plugin

Lưu file **PluginThing.java**:

~~~java
package lab;

public final class PluginThing {
    public static String ping() {
        return "OK";
    }
}
~~~

Biên dịch vào thư mục `plugin` (tạo các thư mục package nếu chưa có):

~~~sh
javac --release 17 -d plugin PluginThing.java
~~~

Sau lệnh này, tệp class nằm tại `plugin/lab/PluginThing.class`. Không thêm thư mục `plugin` vào class path mặc định của ứng dụng chính; trong ví dụ, **từng `URLClassLoader`** sẽ nạp lớp từ URL của thư mục đó.

### 7.2 Chương trình dùng MXBean và custom loaders

Lưu file đúng tên **LoaderDiagnosticsDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LoaderDiagnosticsDemo {
    private static final List<URLClassLoader> ACTIVE_LOADERS = new ArrayList<>();

    private static void metrics(String stage, ClassLoadingMXBean bean) {
        System.out.printf("%s current=%d total=%d unloaded=%d%n",
                stage, bean.getLoadedClassCount(),
                bean.getTotalLoadedClassCount(), bean.getUnloadedClassCount());
    }

    public static void main(String[] args) throws Exception {
        ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
        BufferedReader stdin = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        metrics("START", bean);
        System.out.println("READY_LOAD");
        stdin.readLine();

        URL classes = Path.of("plugin").toAbsolutePath().toUri().toURL();
        for (int i = 1; i <= 3; i++) {
            URLClassLoader loader = new URLClassLoader(
                    new URL[]{classes}, ClassLoader.getPlatformClassLoader());
            Class<?> type = Class.forName("lab.PluginThing", true, loader);
            String result = (String) type.getMethod("ping").invoke(null);
            ACTIVE_LOADERS.add(loader);
            System.out.println("LOADED_" + i + "=" + result);
        }
        metrics("AFTER_LOAD", bean);
        System.out.println("READY_RELEASE");
        stdin.readLine();

        for (URLClassLoader loader : ACTIVE_LOADERS) {
            loader.close();
        }
        ACTIVE_LOADERS.clear();
        System.out.println("REFERENCES_RELEASED");
        System.out.println("READY_EXIT");
        stdin.readLine();
    }
}
~~~

Giải thích những dòng thiết yếu:

- `ManagementFactory.getClassLoadingMXBean()` lấy số đếm lớp ở cấp JVM, **không chỉ những lớp của ba URLClassLoader**.
- `getPlatformClassLoader()` làm parent để nạp các lớp nền tảng; thư mục `plugin` không nằm trong application class path nên `lab.PluginThing` được ba custom loaders định nghĩa riêng.
- `Class.forName(..., true, loader)` yêu cầu nạp và khởi tạo lớp qua loader đó; `ping()` trả lại chuỗi xác nhận `OK`.
- `ACTIVE_LOADERS` giữ strong references để bạn chắc chắn thấy ba loader tại điểm đo.
- `loader.close()` đóng tài nguyên liên quan file/URL; `ACTIVE_LOADERS.clear()` bỏ đi những strong references mà list này nắm giữ. **Không bảo đảm unload ngay** vì có thể còn tham chiếu khác/stack liveness/GC chưa chạy.

### 7.3 Chạy bằng hai terminal và đo theo ba giai đoạn

**Terminal A**, trong thư mục chứa hai file source (đã biên dịch plugin ở trên):

~~~sh
javac --release 17 LoaderDiagnosticsDemo.java
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' LoaderDiagnosticsDemo
~~~

Chương trình in một dòng có số biến động, rồi dừng ở prompt:

~~~text
START current=<số tùy JVM> total=<số tùy JVM> unloaded=<số tùy JVM>
READY_LOAD
~~~

Dòng chứa dấu ngoặc nhọn là **mẫu mô tả output, không phải stdout cố định**; các counters là số thực của JVM ở thời điểm chạy. **Không gõ chữ mẫu trên**; chỉ nhấn Enter khi muốn chuyển bước.

**Terminal B**, khi Terminal A còn đang đợi:

~~~sh
jcmd -l
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace basic
~~~

Ghi lại số loader và các thông số. Trở lại **Terminal A**, nhấn **Enter lần thứ nhất**. Java sẽ in:

~~~text
LOADED_1=OK
LOADED_2=OK
LOADED_3=OK
AFTER_LOAD current=<số tùy JVM> total=<số tùy JVM> unloaded=<số tùy JVM>
READY_RELEASE
~~~

Vẫn ở **Terminal B**, lấy snapshot thứ hai:

~~~sh
jcmd <pid> VM.classloader_stats
~~~

Tìm ba mục `java.net.URLClassLoader` tương ứng các lớp vừa nạp. Trên HotSpot JDK 24 đã kiểm thử, báo cáo có **ba mục URLClassLoader, mỗi mục `Classes=1`**. Số loader nền tảng, số class khác, chunks và các địa chỉ thay đổi theo JVM. `ClassLoadingMXBean` cũng tăng nhiều hơn đúng ba trong thí nghiệm vì lần dùng MXBean/URL/reflective API có thể kéo theo các lớp JDK khác được nạp lười.

Trở lại **Terminal A**, nhấn **Enter lần thứ hai**. Chương trình in:

~~~text
REFERENCES_RELEASED
READY_EXIT
~~~

Lúc này danh sách `ACTIVE_LOADERS` đã được clear, các URLClassLoader đã đóng tài nguyên. Bạn có thể chụp thêm:

~~~sh
jcmd <pid> VM.classloader_stats
~~~

**Đừng mặc định các dòng URLClassLoader sẽ biến mất ngay.** Đã bỏ một nguồn strong reference, nhưng class unloading còn phụ thuộc reachability thực và GC. Trong bài lab (không phải production), nếu muốn thử tạo cơ hội GC, có thể chủ động gọi `jcmd <pid> GC.run` và đo lại; lệnh này có thể gây pause và **không bảo đảm** unload. Với production, tránh dùng `GC.run` chỉ để cho đẹp số liệu.

Khi hoàn tất, nhấn **Enter lần thứ ba** ở Terminal A để kết thúc.

### 7.4 Đọc class load log

Ở thư mục của Terminal A:

~~~sh
# Linux/macOS:
grep 'lab.PluginThing' class-events.log
~~~

Hoặc với PowerShell:

~~~powershell
Select-String -Path class-events.log -Pattern 'lab.PluginThing'
~~~

Trên HotSpot JDK 24 đã kiểm thử, ba dòng load `lab.PluginThing` xuất hiện và mô tả source trỏ tới thư mục `plugin`. Như đã nêu, thời điểm là biến động. Nếu có các dòng `[class,unload]` liên quan lớp này, nghĩa là unload đã thực sự diễn ra trong thời gian ghi; nếu không, không được kết luận loader bị leak từ một lần chạy ngắn.

### 7.5 Đối chiếu output đã kiểm thử

Trong thử nghiệm bằng cách cấp ba dòng Enter ngay để chương trình đi hết các giai đoạn, những dòng xác nhận **cố định** lần lượt là:

~~~text
READY_LOAD
LOADED_1=OK
LOADED_2=OK
LOADED_3=OK
READY_RELEASE
REFERENCES_RELEASED
READY_EXIT
~~~

Ngoài các dòng trên còn có hai dòng counter `START ...` và `AFTER_LOAD ...` với **giá trị phụ thuộc máy/JVM**. Trong một lần chạy thực tế, ví dụ `START current=789 total=789 unloaded=0` và `AFTER_LOAD current=983 total=983 unloaded=0`; đây chỉ là **số mẫu từ môi trường kiểm thử**, không phải kỳ vọng cố định. Thí nghiệm dùng `javac --release 17` và chạy thành công trên HotSpot JDK 24; cờ logging tới file cũng đã được kiểm tra.

## 8. Từ số liệu thành giả thuyết: ba kịch bản chẩn đoán

### Kịch bản A — startup tăng đột ngột rồi ổn định

Một service sau khởi động nạp thêm 2.000 lớp qua framework, cache serializer, HTTP clients và reflection. `current` tăng trong vài phút đầu rồi ổn định; `VM.classloader_stats` cho loader của framework tương ứng. `class+load` ghi nhiều lớp trong giai đoạn warmup, nhưng không thấy các loader tăng mãi.

**Đánh giá:** có thể là lazy class loading bình thường. Đặt baseline **sau warmup**, đo tiếp dưới lưu lượng tương tự; không báo “leak” chỉ vì `totalLoaded` tăng lúc đầu.

### Kịch bản B — class loading churn ở hệ thống rule động

Một service mỗi giây tạo thêm vài loại lớp proxy ngắn hạn với loader riêng. Sau GC, `getUnloadedClassCount()` tăng nhiều, `current` xấp xỉ ổn định và các URLClassLoader cũ dần biến mất. `class+load` và `class+unload` cùng dày đặc.

**Đánh giá:** có thể không leak, nhưng vẫn có **chi phí CPU/GC/Metaspace churn**. Điều tra nơi tạo class/loader, xem có thể cache/reuse hợp lý thay vì liên tục sinh class mới; đo hiệu quả tối ưu theo workload thực.

### Kịch bản C — class loader leak sau redeploy

Sau mỗi lần redeploy, có thêm một nhóm loader ứng dụng cũ. `current` tăng bậc thang, `unloaded` gần như không tăng sau nhiều chu kỳ GC phù hợp, `VM.classloader_stats` liên tục có loader thuộc những deployment cũ và `VM.metaspace` cho xu hướng footprint lớn dần. Heap dump xác định một thread sống dài giữ `contextClassLoader` trỏ tới loader cũ.

**Đánh giá:** có bằng chứng phù hợp **loader retention/leak**. Biện pháp có thể là ngừng thread trong lúc undeploy, khôi phục TCCL đúng scope, remove listener/ThreadLocal, giải phóng cache hoặc đóng plugin lifecycle. Phải kiểm chứng sau sửa bằng chính những số đo trên, không chỉ vì count giảm một lần.

## 9. Checklist điều tra trong môi trường thật

1. **Xác định đúng JVM:** lưu PID, JVM start time, JDK version/vendor, GC, tình trạng container và thời gian quan sát. Tách restart khỏi biến động bộ đếm.
2. **Lấy baseline:** đọc `ClassLoadingMXBean` hoặc JMX: current, total, unloaded. Ghi timestamp/load/concurrency và Metaspace used/committed.
3. **Đo cửa sổ:** lấy số ở mốc sau warmup và sau một workload lặp; tính `load_rate` và `unload_rate` từ counter tích lũy.
4. **Khoanh loader:** với cùng PID, chụp `VM.classloader_stats` vài lần. Xem loại loader, số lớp mỗi mục, số loader đang có, ChunkSz/BlockSz và xu hướng.
5. **Bật log theo giả thuyết:** nếu cần biết tên lớp hoặc lịch load/unload, sử dụng `class+load` và `class+unload` với output/rotation có giới hạn. Thu quanh giai đoạn xuất hiện vấn đề.
6. **Đặt giả thuyết cụ thể:** ví dụ “mỗi hot deploy giữ một URLClassLoader do thread pool không dừng” thay vì “Metaspace đang leak”.
7. **Kiểm tra root:** dùng heap dump/path-to-GC-roots, thread dump/TCCL, listener, cache, framework/plugin lifecycle. Với một đợt điều tra nhạy latency, cân nhắc tác động của từng diagnostic command.
8. **Thử sửa và đo lại:** so dưới cùng tải, cùng JVM config, cùng khoảng warmup, quan sát loader cũ biến mất khi đủ điều kiện GC/unloading, xu hướng `current` ổn định và memory footprint ngừng tăng.

**Không dùng một screenshot đơn lẻ của `VM.classloader_stats` để tuyên bố leak.** Một ứng dụng có 50.000 lớp hoàn toàn hợp lệ nếu đó là thiết kế runtime, trong khi một loader cũ giữ 100 lớp không còn dùng vẫn có thể là lỗi vòng đời.

## 10. Lỗi phổ biến cần tránh

1. **Nhầm `totalLoaded` với `current`.** `totalLoaded` tăng không có nghĩa số lớp còn sống tăng.
2. **Diễn giải `unloaded=0` trong vài giây như bug GC.** Unloading chỉ xảy ra khi đáp ứng điều kiện và ở thời điểm phù hợp.
3. **Nhầm số `Classes` trong `VM.classloader_stats` với số instance object của lớp đó.** Đây là số định nghĩa class theo loader/CLD, không phải object histogram.
4. **Đọc `ChunkSz` như Java heap used hoặc tổng metaspace live chính xác.** Cần đối chiếu `VM.metaspace` và cách cấp phát chunk/block của HotSpot.
5. **Thấy cùng tên class load ba lần rồi kết luận trùng lặp vô ích.** Có thể mỗi bản là class khác do loader khác định nghĩa.
6. **Cho rằng `URLClassLoader.close()` hoặc gán `null` là unload.** Close giải phóng tài nguyên của loader; unload cần reachability/GC.
7. **Bật `setVerbose(true)` và quên nó là thay đổi toàn cục.** Log có thể tăng mạnh và output phụ thuộc implementation.
8. **Dùng flags cũ `-XX:+TraceClassLoading` của các JDK xưa cho JDK 17+.** HotSpot hiện đại dùng `-Xlog:class+load=info` và `class+unload=info`.
9. **Quên class source logging được bật quá muộn.** `-Xlog` từ startup chỉ ghi thời gian sau khi khởi động với flag; bật động qua `VM.log` không hồi cứu những lần load đã qua.
10. **Quên log rotation.** Khi file đã xoay vòng, không thấy event cũ không có nghĩa nó chưa xảy ra.
11. **So counters giữa PID/JVM khác nhau.** Restart reset bộ đếm; phải tách series theo process.
12. **Kết luận mọi lần current tăng là leak.** Lazy loading, proxy, generated classes, plugin mới, warmup có thể hợp lệ.
13. **Bỏ qua thread context class loader.** Thread lâu sống có thể giữ loader cũ dù không còn request/plugin sử dụng.
14. **Chạy `GC.run` trên production để “ép unload” liên tục.** Có thể gây pause và không bảo đảm; hãy quan sát chu kỳ GC tự nhiên trước.
15. **Dùng quá nhiều log và diagnostic commands làm méo latency.** Cấu hình mức chi tiết thấp đủ trả lời câu hỏi, giữ giới hạn file và thời gian đo.

## 11. Bài tập có lời giải

**Bài 1.** `totalLoaded` tăng thêm 4.000 sau 1 giờ, `unloaded` tăng 3.900 và `current` chỉ tăng 100. Đây là memory leak?

**Giải:** Chưa có bằng chứng. Dữ liệu phù hợp với churn khoảng 4.000 lượt load/3.900 unload; lớp còn loaded ròng tăng khoảng 100. Cần theo dõi tốc độ và chi phí, đồng thời kiểm tra nhóm loader nếu xu hướng current tiếp tục tăng.

**Bài 2.** `VM.classloader_stats` liệt kê 40 `URLClassLoader`, mỗi loader có 10 classes. Công cụ này đã chứng minh 400 đối tượng Java đang nằm trên heap chưa?

**Giải:** Không. `Classes` là số class definitions theo các loader/CLD ở ảnh chụp, không phải instance count. Để đếm/định vị object, dùng profiler hoặc heap dump/histogram, đồng thời lưu ý một loader có thể chứa metadata nhiều lớp khác nhau.

**Bài 3.** Bạn chạy `URLClassLoader.close()` rồi không thấy `[class,unload]` trong 3 giây. Kết luận?

**Giải:** Chỉ biết chưa quan sát được unload trong ba giây log đó. Có thể còn tham chiếu mạnh, class loader chưa unreachable hoặc chưa có GC/unloading thích hợp. Không nên suy ra ngay leak hay lỗi JDK.

**Bài 4.** Log `class,load` xuất hiện lặp `lab.PluginThing` ba lần, nhưng application không có ba loại plugin khác nhau. Có gì đáng kiểm tra?

**Giải:** Hãy kiểm tra loader định nghĩa từng lớp. Có thể ba instance loader độc lập nạp cùng tên, như demo; nếu ứng dụng chỉ cần một instance, đó có thể là churn không cần thiết. Dùng `VM.classloader_stats`/loader identity để phân biệt, rồi kiểm vòng đời.

**Bài 5.** Service đang chạy 30 ngày, cần xác định khi nào `com.acme.DynamicRule` được load lần đầu. Hiện tại chưa bật logging. Có thể lấy lịch sử chính xác từ `VM.classloader_stats`?

**Giải:** Không. `VM.classloader_stats` chỉ cung cấp snapshot hiện tại; `ClassLoadingMXBean` chỉ cho tổng counters. Phải có log/JFR/trace đã ghi đúng cửa sổ trước đó để biết timestamp lịch sử. Bật log bây giờ không tái tạo event đã xảy ra.

**Bài 6.** Sau redeploy, số lớp hiện loaded tăng đều, `VM.classloader_stats` có nhiều loader của deployment cũ và Metaspace tăng. Bước xác minh tiếp theo?

**Giải:** Tìm **đường tham chiếu giữ class loader sống** bằng heap dump và GC roots, kiểm các thread/TCCL, static registries, listener, timer, JDBC driver, ThreadLocal hoặc framework resources; xác nhận những loader đó đáng ra phải được dỡ. Sau sửa, lặp đo ở cùng tải qua các chu kỳ GC phù hợp.

## 12. Bảng lệnh ghi nhớ

~~~sh
# 1. Lấy số current/total/unloaded bằng ClassLoadingMXBean
#    (sử dụng Java/JMX metrics, xem code phần 7)

# 2. Xác định PID và lấy snapshot loader:
jcmd -l
jcmd <pid> VM.classloader_stats

# 3. Khi cần chi tiết memory:
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.metaspace show-loaders

# 4. Ghi class load/unload từ JVM startup:
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' -jar app.jar

# 5. Nếu cần thay logging khi JVM đang chạy (thao tác có kiểm soát):
jcmd <pid> VM.log list
jcmd <pid> help VM.log
~~~

**Điểm mấu chốt:** `ClassLoadingMXBean` cho **xu hướng**, `VM.classloader_stats` cho **phân bố theo loader**, `class+load`/`class+unload` cho **timeline sự kiện**. Kết hợp thêm Metaspace và GC roots mới giúp trả lời câu hỏi **vì sao loader còn sống**. Phân biệt “load nhiều”, “đang loaded nhiều” và “unload chưa xảy ra” trước khi gán nhãn leak.

### Tài liệu tham khảo chính thức

- Oracle Java 21 API, `ClassLoadingMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle Java 21, `The jcmd Command` (gồm `VM.classloader_stats`, `VM.metaspace`, `VM.log`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 17, `The java Command` / Unified Logging / chuyển cờ `TraceClassLoading` sang `-Xlog`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 22, `Troubleshooting Memory Leaks` (class loader statistics): https://docs.oracle.com/en/java/javase/22/troubleshoot/troubleshooting-memory-leaks.html
- Oracle Java 21 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
