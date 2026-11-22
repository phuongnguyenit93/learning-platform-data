# Cách đọc VM Summary trong JConsole

VM Summary là màn hình tổng hợp thông tin của Java Virtual Machine (JVM) trong JConsole. Nó gom các chỉ số về thời gian chạy, CPU, JIT compilation, thread, class loading, heap, garbage collection, hệ điều hành và cấu hình khởi chạy vào một nơi. Khi ứng dụng chậm, tăng bộ nhớ, tạo quá nhiều thread hoặc chạy khác môi trường dự kiến, màn hình này giúp bạn xác định nhóm tài nguyên cần điều tra tiếp.

Bài này sử dụng JDK 17 trở lên. Trọng tâm là ý nghĩa từng trường trong VM Summary, cách đọc số liệu theo thời gian, phân biệt bộ đếm tích lũy với giá trị hiện tại, cách kết nối JConsole vào JVM local/remote và cách đối chiếu với các MXBean hoặc công cụ dòng lệnh.

## 1. JConsole và VM Summary là gì?

JConsole là công cụ giao diện đồ họa dùng Java Management Extensions (JMX) để giám sát và quản lý JVM. JVM cung cấp instrumentation và các platform MXBean; JConsole đọc dữ liệu đó thông qua management agent.

Sau khi kết nối với một tiến trình Java, giao diện JConsole thường có các tab:

| Tab | Mục đích |
|---|---|
| Overview | Xem nhanh biểu đồ CPU, memory, thread và class loading |
| Memory | Theo dõi heap, non-heap, memory pool và GC |
| Threads | Xem thread đang sống, trạng thái, stack trace và deadlock |
| Classes | Theo dõi class hiện đang được nạp, tổng số đã nạp và đã unload |
| VM Summary | Xem thông tin tổng hợp về JVM, thread, class, memory, GC, OS và tham số khởi chạy |
| MBeans | Đọc attribute, gọi operation và quản lý các MBean được đăng ký |

Tên hoặc cách bố trí tab có thể thay đổi đôi chút theo bản JDK và nền tảng. Trong tài liệu JDK 17, màn hình tổng hợp này được gọi là **VM Summary**.

VM Summary trả lời các câu hỏi ban đầu như:

- JVM đã chạy được bao lâu?
- Tiến trình đã tiêu thụ bao nhiêu CPU time?
- JIT compiler đã dành bao nhiêu thời gian để biên dịch?
- Hiện có bao nhiêu thread và class?
- Heap đang dùng, đã commit và có thể tăng tối đa bao nhiêu?
- Các garbage collector đã chạy bao nhiêu lần và mất bao nhiêu thời gian?
- JVM chạy trên hệ điều hành nào và được khởi chạy với tham số/classpath nào?

VM Summary là điểm bắt đầu để định hướng chẩn đoán. Khi tìm thấy dấu hiệu bất thường, hãy chuyển sang tab chuyên biệt hoặc công cụ phù hợp để xác minh nguyên nhân.

## 2. Khởi chạy JConsole

Tệp thực thi `jconsole` nằm trong thư mục `bin` của JDK.

Nếu JDK đã nằm trong PATH:

~~~powershell
jconsole
~~~

Có thể mở JConsole và kết nối trực tiếp tới PID:

~~~powershell
jconsole 8120
~~~

PID `8120` chỉ là ví dụ. Tìm PID bằng:

~~~powershell
jps -l
~~~

Hoặc dùng Task Manager trên Windows, `ps` trên Linux/macOS.

Khi chạy `jconsole` không kèm PID, cửa sổ New Connection cho phép chọn tiến trình local hoặc nhập thông tin kết nối remote. Chọn đúng ứng dụng rồi nhấn Connect. Sau khi kết nối, mở tab **VM Summary**.

### 2.1. Điều kiện kết nối local

Với JVM hỗ trợ Attach API, JDK hiện đại có thể tự bật management agent khi JConsole attach; thường không cần thêm `-Dcom.sun.management.jmxremote` cho giám sát local.

Các điều kiện thường gặp:

- JConsole và ứng dụng chạy trên cùng máy.
- JConsole và JVM đích chạy dưới cùng tài khoản hệ điều hành.
- JVM đích hỗ trợ attach và không bị cấu hình bảo mật chặn.
- PID được chọn là PID của JVM cần giám sát.
- Trên Windows, thư mục temporary mặc định cần nằm trên filesystem hỗ trợ quyền truy cập file/thư mục phù hợp, chẳng hạn NTFS.

Nếu không thấy tiến trình hoặc không kết nối được, kiểm tra PID, user, JDK và môi trường container trước khi thay đổi cấu hình JVM.

### 2.2. Kết nối remote

Để giám sát JVM ở máy khác, JVM đích phải bật JMX remote agent. JConsole có thể mở bằng cú pháp:

~~~powershell
jconsole app-server.example.com:9010
~~~

Hoặc nhập hostname và port trong cửa sổ New Connection. Nếu agent yêu cầu xác thực, cung cấp username/password theo cấu hình được quản trị viên cấp.

JMX remote có quyền đọc thông tin runtime và có thể cho phép gọi operation hoặc thay đổi attribute MBean. Vì vậy:

- Bật authentication và TLS theo hướng dẫn JDK.
- Giới hạn port bằng firewall và network policy.
- Cấp tài khoản chỉ có quyền cần thiết; dùng read-only access khi chỉ giám sát.
- Bảo vệ password/access file bằng quyền file hạn chế.
- Không mở JMX không xác thực ra Internet hoặc mạng không tin cậy.
- Không đặt credential thật trong shell history, script hoặc log.

Oracle mô tả đầy đủ các thuộc tính JMX remote, password/access file và TLS trong Java SE 17 Monitoring and Management Guide. Không dùng cấu hình tắt xác thực hoặc SSL như một cách khắc phục kết nối trong production.

## 3. Cấu trúc các nhóm thông tin trong VM Summary

Các trường thường được nhóm như sau:

1. **Summary:** thông tin nhận diện JVM, uptime, process CPU time và JIT compile time.
2. **Threads:** số thread đang sống, peak, daemon và tổng số thread đã khởi chạy.
3. **Classes:** số class hiện tại, tổng số class đã nạp và số class đã unload.
4. **Memory:** heap hiện tại, heap tối đa, committed memory, object pending finalization và thống kê GC.
5. **Operating System:** hệ điều hành, kiến trúc, processor và một số số liệu RAM/virtual memory/swap tùy nền tảng.
6. **Other Information:** VM arguments, class path, library path và thông tin boot class path nếu runtime cung cấp.

Một số trường có thể không xuất hiện hoặc có giá trị unavailable tùy JVM, hệ điều hành, garbage collector và JDK vendor. Không nên giả định mọi JVM sẽ hiển thị cùng một danh sách.

## 4. Summary: uptime, CPU time và JIT compile time

### 4.1. Uptime

`Uptime` là tổng thời gian JVM đã chạy kể từ lúc khởi động.

Ví dụ: nếu uptime hiển thị `02:15:30`, JVM đã chạy khoảng 2 giờ 15 phút 30 giây. Đây không phải thời gian người dùng mở ứng dụng và cũng không nhất thiết bằng thời gian máy chủ bật.

Uptime hữu ích để:

- Xác định ứng dụng vừa restart hay đã chạy lâu.
- Đặt các counter tích lũy vào đúng khoảng thời gian.
- So sánh hai lần chụp số liệu.
- Nhận biết việc restart làm bộ đếm runtime bắt đầu lại.

Nếu một bộ đếm như total threads started hoặc total classes loaded tăng, hãy xét cùng uptime. Một giá trị lớn trên JVM đã chạy nhiều ngày có thể bình thường; tốc độ tăng mới là thông tin có ý nghĩa.

### 4.2. Process CPU Time

`Process CPU Time` là tổng thời gian CPU mà tiến trình JVM đã sử dụng kể từ khi khởi động. Đây là CPU time tích lũy, không phải phần trăm CPU tức thời.

Ví dụ, sau một phút theo đồng hồ, process CPU time tăng thêm 20 giây cho thấy tiến trình đã dùng tổng cộng khoảng 20 giây CPU trong khoảng đó. Trên máy nhiều lõi, CPU time có thể tăng nhanh hơn thời gian thực vì nhiều thread có thể chạy song song.

Để xem xu hướng, ghi nhận hai mẫu:

| Mẫu | Uptime | Process CPU Time |
|---|---:|---:|
| A | 10 phút | 45 giây |
| B | 11 phút | 78 giây |

Trong một phút giữa hai mẫu, CPU time tăng 33 giây. Đây là mức tiêu thụ CPU tích lũy của cả tiến trình trong khoảng đó. Cần đối chiếu với số lõi, tải hệ thống và metrics của hệ điều hành trước khi kết luận CPU cao.

Nếu Process CPU Time không có giá trị hoặc không được hỗ trợ, dùng công cụ hệ điều hành, JFR hoặc APM để lấy số liệu thay thế.

### 4.3. Total Compile Time

`Total Compile Time` là tổng thời gian JVM dành cho JIT compilation kể từ khi khởi động. JIT compiler biên dịch một số method bytecode thành mã máy khi runtime xác định chúng có lợi ích hiệu năng.

Cần phân biệt:

- Đây là thời gian tích lũy cho hoạt động biên dịch.
- Không phải thời gian ứng dụng xử lý request.
- Không phải CPU time của toàn tiến trình.
- Không cho biết riêng method nào đang chậm.
- Không có nghĩa mọi method đều đã được biên dịch.

Trong giai đoạn startup hoặc warm-up, compile time có thể tăng nhanh khi JVM biên dịch các method nóng. Khi ứng dụng ổn định, tốc độ tăng có thể giảm. Nếu cần xem compilation chi tiết, dùng tab MBeans/Compilation MXBean, JFR hoặc công cụ profiling.

## 5. Threads: đọc số lượng và xu hướng thread

VM Summary hiển thị bốn chỉ số thread chính.

| Trường | Ý nghĩa |
|---|---|
| Live threads | Số thread daemon và non-daemon hiện đang sống |
| Peak | Số thread sống cao nhất kể từ khi JVM khởi động |
| Daemon threads | Số thread daemon hiện đang sống |
| Total threads started | Tổng số thread đã được start kể từ khi JVM khởi động, bao gồm cả thread đã kết thúc |

### 5.1. Live threads

Live threads là số thread đang tồn tại tại thời điểm cập nhật. Số này có thể thay đổi khi request đến, worker được tạo, task hoàn thành hoặc thread pool mở rộng/thu hẹp.

Một giá trị lớn không tự động là lỗi. Web server có thể có nhiều worker thread để phục vụ request đồng thời. Hãy so sánh với baseline và cấu hình thread pool.

### 5.2. Peak

Peak là số thread sống cao nhất đã quan sát từ khi JVM khởi động. Nó giúp nhận biết ứng dụng từng đạt đỉnh bao nhiêu thread, kể cả khi số thread hiện tại đã giảm.

Peak thường giữ giá trị cao nhất. Nếu live thread giảm nhưng peak vẫn cao, điều đó không có nghĩa thread cũ vẫn còn sống.

### 5.3. Daemon threads

Daemon threads là các thread nền mà JVM không chờ riêng chúng để giữ tiến trình tiếp tục sống khi không còn non-daemon thread. Một số thread runtime, scheduler và worker nền có thể là daemon.

Số daemon cần được xem cùng Live threads. Nếu daemon tăng liên tục, hãy tìm executor hoặc thành phần tạo thread nền có vòng đời chưa được kiểm soát.

### 5.4. Total threads started

Đây là bộ đếm tích lũy gồm cả thread đã kết thúc. Nếu Total threads started tăng nhanh nhưng Live threads gần như ổn định, ứng dụng có thể đang tạo và kết thúc nhiều thread liên tục.

Đây có thể là dấu hiệu thread churn, ví dụ code tạo thread mới cho mỗi request thay vì tái sử dụng executor. Nếu cả Live threads và Peak tăng qua thời gian, hãy điều tra khả năng thread leak hoặc pool không giới hạn.

Khi phát hiện bất thường, mở tab Threads để xem tên, trạng thái và stack trace. Dùng nút Detect Deadlock nếu cần kiểm tra deadlock; với phân tích sâu hơn, lấy thread dump bằng `jcmd PID Thread.print -l`.

## 6. Classes: phân biệt số hiện tại và bộ đếm tích lũy

VM Summary hiển thị:

| Trường | Ý nghĩa |
|---|---|
| Current classes loaded | Số class hiện đang được nạp trong JVM |
| Total classes loaded | Tổng số class đã được nạp kể từ khi JVM khởi động, kể cả class sau đó đã unload |
| Total classes unloaded | Tổng số class đã unload kể từ khi JVM khởi động |

Ví dụ:

~~~text
Current classes loaded: 8,400
Total classes loaded: 9,100
Total classes unloaded: 700
~~~

Trong ví dụ, JVM đã nạp tổng cộng 9.100 class; 700 class đã unload và hiện còn 8.400 class. Đây là bộ đếm minh họa, không phải output cố định.

Cách đọc xu hướng:

- Total loaded tăng trong startup/warm-up là bình thường.
- Current loaded ổn định sau warm-up thường là dấu hiệu hệ thống đã ổn định về class loading.
- Total loaded tăng liên tục trong khi current loaded tăng dần có thể phản ánh nạp class động.
- Total unloaded tăng cho biết JVM đã unload class; không tự động có nghĩa memory leak đã được xử lý hoàn toàn.

Nếu nghi ngờ class loader leak, kết hợp tab Classes với Metaspace metrics, `jcmd PID VM.classloader_stats` và heap dump. Không kết luận leak chỉ từ tổng số class tăng.

## 7. Memory: heap, committed và maximum

VM Summary hiển thị các trường memory chính. Cần hiểu rõ sự khác nhau giữa memory đã dùng, memory đã commit và giới hạn tối đa.

| Trường | Ý nghĩa |
|---|---|
| Current heap size | Dung lượng heap hiện đang được sử dụng theo cách hiển thị của VM Summary |
| Committed memory | Dung lượng heap đã được JVM commit và bảo đảm sẵn sàng sử dụng |
| Maximum heap size | Giới hạn heap tối đa mà JVM có thể dùng, nếu runtime xác định được |
| Objects pending for finalization | Số object đang chờ quá trình finalization |

Các giá trị này thường được hiển thị theo KB hoặc đơn vị dễ đọc như MB. Kiểm tra đơn vị trên giao diện trước khi quy đổi.

### 7.1. Used, committed và max khác nhau thế nào?

- **Used:** phần bộ nhớ hiện đang được sử dụng. Heap used có thể bao gồm object chưa được GC thu hồi tại thời điểm lấy mẫu.
- **Committed:** phần bộ nhớ JVM đã commit và bảo đảm sẵn sàng cho JVM dùng. Committed thường lớn hơn hoặc bằng used.
- **Max:** mức tối đa mà vùng quản lý bộ nhớ có thể đạt tới. Tùy runtime, giá trị này có thể không xác định hoặc có thể thay đổi.

Ví dụ:

~~~text
Current heap size: 420 MB
Committed memory: 768 MB
Maximum heap size: 2048 MB
~~~

Ví dụ này cho biết khoảng 420 MB heap đang được dùng, 768 MB đã commit và heap có thể tăng tới khoảng 2 GB nếu JVM và môi trường cho phép. Nó không có nghĩa tiến trình đang dùng tổng cộng 420 MB RAM; JVM còn có non-heap và native memory.

Không kết luận memory leak từ một mẫu used cao. Hãy theo dõi sau nhiều chu kỳ GC và trong cùng workload. Nếu heap used sau GC liên tục tăng qua nhiều chu kỳ, cần kiểm tra object retention bằng heap dump/profiler.

### 7.2. Objects pending for finalization

Trường này đếm số object đang chờ finalization. Finalization là cơ chế cũ, có chi phí và đã bị deprecated trong Java hiện đại. Không dùng trường này làm thước đo tổng quát cho toàn bộ object chờ GC hoặc toàn bộ backlog của ứng dụng.

Nếu số pending finalization tăng, hãy xem lại code dùng `finalize()` và ưu tiên cơ chế quản lý tài nguyên tường minh như try-with-resources, `AutoCloseable` hoặc cleaner phù hợp.

## 8. Garbage collector: số lần collection và thời gian GC

VM Summary có thể liệt kê từng garbage collector với các thông tin:

- Tên collector.
- Số lần collection đã thực hiện.
- Tổng thời gian đã dành cho collection.

Ví dụ minh họa:

~~~text
Garbage collector:
  Name = G1 Young Generation
  Collections = 120
  Total time spent = 2.40 seconds

Garbage collector:
  Name = G1 Old Generation
  Collections = 3
  Total time spent = 1.15 seconds
~~~

Tên collector và cách chia young/old phụ thuộc JVM và GC được chọn. Một số collector có thể hiển thị nhiều MXBean; số liệu cụ thể khác nhau theo JDK và cấu hình.

### 8.1. Collections

Collections là bộ đếm tích lũy số lần collector chạy kể từ khi JVM khởi động. Hãy so sánh chênh lệch giữa hai lần đọc, không chỉ nhìn tổng số.

Nếu số lần young collection tăng nhanh, có thể ứng dụng đang tạo nhiều object ngắn hạn. Nếu old/full collection thường xuyên xuất hiện, cần xem heap pressure, object sống lâu và cấu hình GC.

### 8.2. Total time spent

Đây là tổng thời gian tích lũy collector báo cáo đã dùng cho GC. So sánh delta trong một khoảng thời gian với độ dài khoảng quan sát để đánh giá mức ảnh hưởng.

Ví dụ: GC time tăng 0,8 giây trong một phút cho thấy collector đã dành tổng cộng 0,8 giây cho hoạt động GC trong khoảng đó. Hãy đối chiếu với pause time thực tế, throughput, latency và log GC; tổng thời gian collector không thay thế phân tích từng pause.

### 8.3. Khi nào cần mở tab Memory?

Chuyển sang tab Memory khi cần:

- Xem heap/non-heap theo thời gian.
- Chọn memory pool cụ thể.
- Theo dõi Eden, Survivor, Old/tenured hoặc Metaspace tùy GC/JVM.
- So sánh used, committed và max.
- Đối chiếu GC time và số lần collection.
- Kiểm tra xu hướng bộ nhớ trước và sau collection.

Nút Perform GC có thể yêu cầu JVM chạy garbage collection. Đây là thao tác tác động tới tiến trình đang chạy và không nên bấm tùy tiện trên production chỉ để “thử xem memory có giảm không”.

## 9. Operating System: đọc thông tin máy chủ

Nhóm Operating System có thể hiển thị:

| Trường | Ý nghĩa |
|---|---|
| Operating System | Tên và phiên bản hệ điều hành |
| Architecture | Kiến trúc hệ thống |
| Number of processors | Số processor mà runtime báo cáo |
| Total physical memory | Tổng RAM vật lý |
| Free physical memory | RAM vật lý còn trống |
| Committed virtual memory | Lượng virtual memory được bảo đảm sẵn sàng cho tiến trình |
| Total swap space | Tổng dung lượng swap, nếu được hỗ trợ |
| Free swap space | Dung lượng swap còn trống, nếu được hỗ trợ |

Các trường cụ thể phụ thuộc OS, JDK vendor và phiên bản. Một số thông tin là phần mở rộng của `OperatingSystemMXBean`, không phải mọi nền tảng đều hỗ trợ.

### 9.1. Phân biệt memory của JVM và memory của hệ điều hành

Heap committed là bộ nhớ JVM commit cho heap. Committed virtual memory là số liệu ở cấp tiến trình/hệ điều hành. Hai số liệu này không cùng phạm vi.

Tiến trình Java còn sử dụng:

- Metaspace và compressed class space.
- JIT code cache.
- Thread stack.
- Direct byte buffers.
- Native library và JNI allocations.
- Các vùng native/internal khác của JVM.

Vì vậy, heap max 2 GB không có nghĩa tiến trình chỉ có thể dùng tối đa 2 GB RAM.

Trong container, số liệu OS có thể phản ánh host hoặc giá trị đã được container-aware JVM điều chỉnh, tùy JDK và nền tảng. Hãy đối chiếu với cgroup/container metrics hoặc công cụ vận hành của nền tảng thay vì giả định giá trị trong JConsole luôn là giới hạn container.

## 10. Other Information: VM arguments và đường dẫn

Phần cuối VM Summary cung cấp thông tin khởi chạy và tìm kiếm class/native library.

| Trường | Ý nghĩa |
|---|---|
| VM arguments | Các đối số truyền cho JVM khi khởi chạy, không bao gồm đối số truyền vào `main(String[] args)` |
| Class path | Classpath mà system class loader sử dụng để tìm class |
| Library path | Danh sách đường dẫn được tìm kiếm khi nạp native library |
| Boot class path | Đường dẫn dùng bởi bootstrap class loader khi runtime cung cấp trường này |

Ví dụ VM arguments:

~~~text
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Dapp.profile=production
~~~

Các tham số này giúp xác minh JVM thực sự chạy với heap, GC và profile nào. Nếu cấu hình trong deployment script khác với điều đang thấy trên VM Summary, hãy điều tra service wrapper, container entrypoint hoặc cách triển khai.

### 10.1. VM arguments không phải application arguments

Hai loại tham số này khác nhau:

~~~powershell
java -Xmx2g -Dapp.profile=prod -jar app.jar --mode=batch
~~~

- `-Xmx2g` và `-Dapp.profile=prod` là tham số của JVM.
- `--mode=batch` là tham số ứng dụng được chuyển vào `main(String[] args)` hoặc framework xử lý command line.

VM Summary hiển thị VM arguments; nó không phải màn hình liệt kê đầy đủ mọi đối số nghiệp vụ của ứng dụng.

### 10.2. Cẩn trọng với thông tin nhạy cảm

VM arguments có thể chứa password/token nếu ứng dụng đã cấu hình sai bằng cách đưa secret vào command line hoặc `-D`. Class path và library path có thể tiết lộ cấu trúc thư mục, tên dịch vụ và artifact nội bộ.

Trước khi chia sẻ screenshot hoặc output:

- Che credential và token nếu xuất hiện.
- Che hostname, username, đường dẫn nội bộ khi chính sách yêu cầu.
- Không gửi toàn bộ VM arguments vào ticket công khai.
- Chỉ trích xuất trường cần thiết cho chẩn đoán.

## 11. Đọc VM Summary theo tình huống thực tế

### 11.1. Ứng dụng vừa khởi động

Dấu hiệu có thể thấy:

- Uptime thấp.
- Process CPU Time và Total Compile Time đang tăng khi JVM warm-up.
- Total threads started tăng trong lúc framework tạo worker.
- Total classes loaded tăng nhanh.
- Heap used/committed thay đổi khi ứng dụng khởi tạo.

Đây có thể là hoạt động bình thường. Hãy lấy một baseline sau khi ứng dụng warm-up xong để so sánh các lần sau.

### 11.2. CPU tăng cao

Kiểm tra Process CPU Time ở hai thời điểm. Nếu delta tăng nhanh so với khoảng thời gian thực, tiến trình đang tiêu thụ nhiều CPU hơn.

Sau đó:

1. Kiểm tra Overview để xem CPU trend.
2. Mở Threads và tìm thread có stack liên quan.
3. Lấy thread dump nhiều lần để xem thread RUNNABLE có lặp lại cùng stack không.
4. Dùng JFR hoặc profiler để tìm method nóng.

Process CPU Time chỉ là số tổng của tiến trình; VM Summary không chỉ ra thread hoặc method cụ thể gây tải.

### 11.3. Số thread tăng dần

So sánh Live threads, Peak và Total threads started:

- Live tăng và không giảm sau khi tải kết thúc: kiểm tra thread leak hoặc executor không giới hạn.
- Total started tăng nhanh nhưng Live ổn định: có thể tạo thread ngắn hạn quá thường xuyên.
- Peak cao nhưng Live hiện tại thấp: có thể ứng dụng từng có đỉnh tải lớn rồi đã giảm.

Mở Threads để xem tên thread và stack; nhóm các thread theo prefix để tìm component tạo chúng.

### 11.4. Heap used tăng

Theo dõi Current heap size, Committed và Maximum. Nếu used tăng trong lúc workload chạy, điều đó có thể là bình thường. Nếu used sau GC không giảm và tăng qua nhiều chu kỳ, kiểm tra object retention.

Chuyển sang tab Memory để xem heap pool và GC. Nếu cần tìm object giữ bộ nhớ, lấy heap dump bằng quy trình phù hợp và phân tích bằng heap analyzer.

### 11.5. Class count tăng liên tục

Nếu Total classes loaded tăng, hãy xem Current classes loaded và Total classes unloaded:

- Current ổn định, total tăng: có class mới được nạp và có thể một số class cũ đã unload.
- Current tăng đều, unloaded không tăng: có thể nạp class động hoặc class loader cũ vẫn được giữ.
- Total unloaded tăng: JVM đã unload class; vẫn cần kiểm tra Metaspace nếu nghi ngờ memory leak.

Dùng tab Classes, `jstat -class` và `jcmd PID VM.classloader_stats` để điều tra sâu hơn.

### 11.6. GC time tăng

So sánh số collection và total GC time qua các khoảng thời gian. Nếu GC time tăng nhanh cùng heap pressure và latency, cần phân tích GC log/JFR và workload allocation. Không thay đổi GC flags chỉ dựa trên một ảnh chụp VM Summary.

## 12. Đối chiếu VM Summary với Java Management API

VM Summary hiển thị các dữ liệu lấy từ platform MXBeans và các thông tin runtime/OS. Ứng dụng cũng có thể đọc nhiều chỉ số này bằng `ManagementFactory`.

| Nhóm trong VM Summary | API/MXBean thường dùng |
|---|---|
| Uptime, VM arguments, class path | `RuntimeMXBean` |
| Process CPU và thông tin OS | `OperatingSystemMXBean` hoặc extension của vendor |
| Thread count, peak, daemon, total started | `ThreadMXBean` |
| Current/total/unloaded classes | `ClassLoadingMXBean` |
| Heap usage và pending finalization | `MemoryMXBean` |
| GC count và collection time | `GarbageCollectorMXBean` |
| Total compile time | `CompilationMXBean` |

Ví dụ đọc một số giá trị bằng Java:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;

public class VmSummaryMetrics {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();
        CompilationMXBean compilation =
                ManagementFactory.getCompilationMXBean();

        System.out.println("Uptime ms: " + runtime.getUptime());
        System.out.println("Live threads: " + threads.getThreadCount());
        System.out.println("Peak threads: " + threads.getPeakThreadCount());
        System.out.println("Daemon threads: " + threads.getDaemonThreadCount());
        System.out.println("Total started threads: "
                + threads.getTotalStartedThreadCount());
        System.out.println("Current loaded classes: "
                + classes.getLoadedClassCount());
        System.out.println("Total loaded classes: "
                + classes.getTotalLoadedClassCount());
        System.out.println("Total unloaded classes: "
                + classes.getUnloadedClassCount());

        if (compilation != null && compilation.isCompilationTimeMonitoringSupported()) {
            System.out.println("Total compile time ms: "
                    + compilation.getTotalCompilationTime());
        } else {
            System.out.println("Compilation time monitoring is unavailable.");
        }
    }
}
~~~

Biên dịch và chạy:

~~~powershell
javac VmSummaryMetrics.java
java VmSummaryMetrics
~~~

Các số thread, class và uptime thay đổi theo runtime nên stdout không có giá trị cố định. Chương trình in các metric cùng ý nghĩa với một phần VM Summary; process CPU time và một số trường OS có thể cần API extension theo vendor.

## 13. VM Summary khác gì các tab còn lại?

VM Summary cung cấp bức tranh tổng quan. Các tab khác cho dữ liệu chi tiết hơn:

| Khi cần... | Mở tab |
|---|---|
| Xem xu hướng CPU, heap, threads, classes cùng lúc | Overview |
| Xem memory pool, heap/non-heap và GC | Memory |
| Xem tên thread, state, stack trace và deadlock | Threads |
| Xem số class hiện tại, tổng nạp và unload | Classes |
| Xem uptime, CPU time, compile time, thread/class/memory/OS và VM args | VM Summary |
| Xem platform MXBean, application MBean, attribute và operation | MBeans |

Ví dụ, VM Summary báo Live threads tăng bất thường. Tab Threads giúp xác định thread nào đang sống và stack trace của chúng. VM Summary báo heap tăng; tab Memory cho biết pool nào tăng. VM Summary báo total classes tăng; tab Classes cho biết current/total/unloaded theo thời gian.

## 14. Lưu biểu đồ và so sánh theo thời gian

JConsole cho phép lưu dữ liệu của biểu đồ ra CSV:

1. Mở tab có chart cần lưu, ví dụ Overview, Memory, Threads hoặc Classes.
2. Nhấp chuột phải lên biểu đồ.
3. Chọn **Save data as...**.
4. Chọn đường dẫn và tên file CSV.
5. Mở CSV bằng spreadsheet hoặc công cụ phân tích.

CSV thường có cột timestamp và các giá trị đo. Khi import vào spreadsheet, kiểm tra định dạng timestamp và đơn vị của các cột trước khi vẽ lại.

VM Summary chứa nhiều counter tích lũy; để phân tích trend, ghi lại snapshot định kỳ hoặc xuất chart từ tab chuyên biệt. So sánh delta trong khoảng thời gian, thay vì chỉ so sánh tổng giá trị từ lúc JVM khởi động.

## 15. Lỗi thường gặp khi dùng VM Summary

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jconsole is not recognized` | JDK `bin` chưa nằm trong PATH | Dùng đường dẫn đầy đủ tới `jconsole` hoặc cập nhật PATH |
| Không thấy tiến trình local | Khác user, PID namespace/container hoặc tiến trình không hỗ trợ attach | Chạy cùng user và trong đúng môi trường; xác minh PID bằng `jps -l` |
| Tiến trình bị mờ/không thể Connect | Management agent không bật và JVM không hỗ trợ dynamic attach | Kiểm tra runtime, Attach API và cấu hình agent |
| Kết nối local thất bại trên Windows | Temporary directory không hỗ trợ ACL cần thiết | Dùng filesystem hỗ trợ permission như NTFS và kiểm tra quyền thư mục |
| Remote connection refused | Sai host/port, firewall hoặc JMX agent chưa bật | Kiểm tra agent, port, RMI và network policy |
| Remote connection bị từ chối xác thực | Username/password hoặc access file không đúng | Xác minh credential và quyền read-only/read-write |
| Một số metric không có giá trị | JVM/OS không hỗ trợ MXBean hoặc extension tương ứng | Đối chiếu tài liệu vendor và công cụ hệ điều hành |
| Heap used cao nhưng không biết object nào giữ | VM Summary chỉ là dữ liệu tổng hợp | Dùng Memory tab, heap dump và heap analyzer |
| CPU time tăng nhưng không biết thread nào gây tải | Process CPU time là số tổng của JVM | Dùng Threads, thread dump, JFR hoặc profiler |
| Số thread total tăng nhưng live ổn định | Thread được tạo rồi kết thúc thường xuyên | Kiểm tra thread churn và cách dùng executor |

## 16. Giới hạn và lưu ý vận hành

- VM Summary là ảnh chụp số liệu tại thời điểm giao diện cập nhật; không thay thế monitoring history dài hạn.
- Các counter như uptime, total threads started, total classes loaded, GC count và GC time thường tích lũy từ lúc JVM khởi động.
- Peak threads là giá trị đỉnh, không phải số thread đang sống.
- Process CPU time là CPU time tích lũy, không phải CPU percentage.
- Total compile time là thời gian JIT tích lũy, không phải request latency.
- Heap committed và process committed virtual memory thuộc hai phạm vi khác nhau.
- Trường OS phụ thuộc nền tảng và có thể không phản ánh chính xác quota container nếu runtime không expose giá trị container-aware.
- JConsole local tiêu thụ tài nguyên; Oracle không khuyến nghị chạy local JConsole trên production vì có thể ảnh hưởng tiến trình được giám sát. Nên đặt công cụ giám sát trên máy khác khi phù hợp.
- MBeans tab có thể thay đổi writable attribute hoặc gọi operation; xác minh tác động trước khi thực hiện.
- VM arguments và classpath có thể chứa thông tin nhạy cảm; redact trước khi chia sẻ.

Với production, nên dùng monitoring system/JMX exporter/APM/JFR để lưu lịch sử và cảnh báo. JConsole phù hợp cho kiểm tra trực tiếp, học tập và chẩn đoán tương tác.

## 17. Checklist đọc VM Summary

- [ ] Đã xác định đúng JVM/PID và xác nhận kết nối tới đúng ứng dụng.
- [ ] Đã ghi nhận VM name, vendor, version và uptime.
- [ ] Đã hiểu Process CPU Time là CPU time tích lũy.
- [ ] Đã hiểu Total Compile Time là JIT compile time tích lũy.
- [ ] Đã phân biệt Live, Peak, Daemon và Total threads started.
- [ ] Đã phân biệt Current classes loaded với Total classes loaded và Total classes unloaded.
- [ ] Đã phân biệt heap used/current, committed và maximum.
- [ ] Đã đọc số lần collection và total GC time theo từng collector.
- [ ] Đã phân biệt số liệu heap với số liệu memory ở cấp OS/process.
- [ ] Đã kiểm tra VM arguments, class path và library path khi cần.
- [ ] Đã đối chiếu chỉ số bất thường bằng tab chuyên biệt hoặc JMX/CLI.
- [ ] Đã xem xét quyền và bảo mật khi dùng remote JMX.
- [ ] Đã redact credential, hostname và đường dẫn nhạy cảm trước khi chia sẻ.

VM Summary là màn hình tổng hợp để đọc nhanh tình trạng JVM: thời gian chạy, CPU/JIT, thread, class, heap/GC, hệ điều hành và cấu hình khởi chạy. Hãy phân biệt giá trị hiện tại với bộ đếm tích lũy, so sánh delta qua các lần chụp và chuyển sang tab chuyên biệt khi cần tìm nguyên nhân. Khi giám sát production, bảo vệ JMX remote, giới hạn quyền truy cập và dùng hệ thống monitoring có lịch sử để xác nhận xu hướng.

## Tài liệu tham khảo

- Oracle, Java SE 17 Monitoring and Management Guide — Using JConsole: https://docs.oracle.com/en/java/javase/17/management/using-jconsole.html
- Oracle, Java SE 17 Monitoring and Management Guide — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html
- Oracle, Java SE 17 API — RuntimeMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html
- Oracle, Java SE 17 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle, Java SE 17 API — ClassLoadingMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle, Java SE 17 API — MemoryMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
