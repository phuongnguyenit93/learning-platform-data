# Lệnh jmap

**jmap** là công cụ chẩn đoán của JDK dùng để xem một số thông tin bộ nhớ của Java HotSpot VM đang chạy. Các tác vụ thường dùng gồm tạo heap histogram, xuất heap dump, xem thống kê class loader và liệt kê đối tượng đang chờ finalization.

jmap hữu ích khi điều tra nghi ngờ rò rỉ bộ nhớ, tăng heap bất thường hoặc cần thu thập dữ liệu để phân tích offline. Tuy nhiên, đây là công cụ **experimental và unsupported** trong tài liệu JDK; Oracle khuyến nghị dùng **jcmd** cho chẩn đoán hiện đại vì có nhiều lệnh hơn và giảm overhead so với các tiện ích cũ như jmap.

Một heap dump hoặc histogram có thể tạo pause, kích hoạt garbage collection, sử dụng nhiều CPU/I/O và chứa dữ liệu nhạy cảm trong object graph. Vì vậy, cần xác minh đúng JVM, chọn đúng loại dữ liệu, chuẩn bị dung lượng đĩa và bảo vệ file đầu ra trước khi chạy trên production.

## 1. jmap dùng để làm gì?

jmap kết nối đến một Java process và đọc thông tin liên quan đến heap hoặc class loader. Các lệnh thường gặp trong JDK 24:

| Lệnh | Mục đích |
|---|---|
| -histo | In histogram số lượng object và bytes theo class |
| -dump | Xuất heap thành file HPROF binary |
| -clstats | In thống kê class loader trong heap |
| -finalizerinfo | Xem thông tin về object đang chờ finalization |
| --help | In cú pháp và tùy chọn được hỗ trợ |

Các thao tác này giúp trả lời những câu hỏi khác nhau:

- Class nào đang có nhiều instance nhất?
- Class nào chiếm nhiều shallow heap bytes?
- Có thể thu thập snapshot heap để tìm object giữ tham chiếu lâu dài không?
- Class loader nào đang nạp nhiều class?
- Có nhiều object đang chờ finalization hay không?

jmap không tự kết luận ứng dụng có memory leak. Nó cung cấp snapshot để kỹ sư phân tích cùng GC logs, JFR, metrics và hành vi ứng dụng.

### jmap không phải công cụ monitoring liên tục

jmap thực hiện một lần chụp hoặc truy vấn tại thời điểm chạy. Nó không thay thế metrics theo thời gian, heap occupancy chart, GC pause monitoring hay production profiling.

Nếu cần quan sát xu hướng heap theo thời gian, dùng Java Flight Recorder (JFR), JDK Mission Control (JMC), JMX hoặc hệ thống monitoring được bảo vệ. Histogram lặp lại theo chu kỳ có thể hữu ích, nhưng không nên tạo heap dump liên tục trên production chỉ để theo dõi xu hướng.

## 2. Trạng thái hỗ trợ và phiên bản JDK

Oracle JDK 24 Troubleshooting Guide phân loại jmap là công cụ experimental. Tài liệu cũng khuyến nghị dùng jcmd thay cho các tiện ích cũ như jmap, jinfo và jstack để có chẩn đoán tốt hơn và giảm overhead.

Điều đó có nghĩa:

- jmap có thể thay đổi tùy chọn hoặc output giữa các phiên bản.
- Công cụ có thể không còn được cung cấp trong một bản JDK tương lai.
- Khả năng hoạt động phụ thuộc JVM implementation, hệ điều hành và quyền attach.
- Không nên xây dựng automation dài hạn dựa trên output jmap.
- Nên kiểm tra help của đúng JDK đang chạy ứng dụng.

Xem cú pháp:

~~~bash
jmap --help
~~~

Trên OpenJDK 24.0.2 trong môi trường kiểm tra, help liệt kê các lệnh -clstats, -finalizerinfo, -histo và -dump. Các tùy chọn heap summary cũ như -heap không xuất hiện trong help của bản này. Không sao chép cú pháp từ tài liệu JDK cũ mà không kiểm tra toolchain hiện tại.

### Ưu tiên jcmd cho công việc mới

Oracle khuyến nghị dùng jcmd thay cho jmap trong các quy trình chẩn đoán hiện đại.

Các lệnh tương ứng thường dùng:

~~~bash
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump heap.hprof
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.finalizer_info
~~~

Tên diagnostic command và tùy chọn có thể khác theo JVM. Dùng lệnh sau để xem command được process mục tiêu hỗ trợ:

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_dump
jcmd <pid> help GC.class_histogram
~~~

Ngay cả khi dùng jcmd, heap histogram và heap dump vẫn có thể có tác động cao. Ưu tiên jcmd không có nghĩa thao tác thu thập heap trở thành miễn phí hoặc không gây pause.

## 3. Xác định đúng PID của JVM

jmap cần PID của Java process mục tiêu. Có thể dùng jps để tìm nhanh JVM trên máy local:

~~~bash
jps -l
~~~

Output minh họa:

~~~text
31840 com.example.ApiServer
32004 com.example.BatchWorker
~~~

Nếu ứng dụng là ApiServer, PID minh họa là 31840. Trước khi chạy jmap, xác minh process bằng công cụ hệ điều hành.

Linux/macOS:

~~~bash
ps -p 31840 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 31840" |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine
~~~

PID có thể được tái sử dụng sau khi process kết thúc. Không dùng PID cũ được lưu từ lần điều tra trước mà không xác minh lại process name, user, command line và thời điểm khởi chạy.

### Quyền truy cập và Attach API

jmap cần kết nối đến JVM mục tiêu. Thông thường, công cụ phải chạy trên cùng máy và với tài khoản có quyền attach phù hợp. Attach có thể thất bại nếu:

- Process không còn tồn tại hoặc PID đã thay đổi.
- User chạy jmap khác user khởi chạy JVM và không có quyền phù hợp.
- Attach mechanism bị vô hiệu hóa trong JVM.
- OS/container security policy chặn truy cập process.
- Runtime hoặc kiến trúc của tool không tương thích với process mục tiêu.
- JVM đang ở trạng thái không phản hồi hoặc bị treo.

Không tự động chạy bằng root/Administrator để vượt qua mọi lỗi attach. Xác định đúng owner và thực hiện theo quy trình vận hành.

### Container và PID namespace

Trong container, cùng một JVM có thể có PID khác nhau khi quan sát từ trong container và từ host. Ví dụ, process có thể là PID 1 bên trong container nhưng là PID 42000 trên host.

Chạy jmap trong đúng container hoặc dùng PID host đã được xác minh theo quy trình của container runtime. Không dùng PID trong namespace này cho lệnh chạy ở namespace khác.

## 4. Heap histogram với -histo

Heap histogram thống kê object theo class. Mỗi dòng thường có các cột:

~~~text
 num     #instances         #bytes  class name
------------------------------------------------
   1:         50000        4000000  com.example.Session
   2:         32000        2048000  byte[]
   3:         18000         576000  java.lang.String
~~~

Các số trong ví dụ chỉ minh họa.

- **num:** thứ hạng của class trong báo cáo.
- **#instances:** số instance thuộc class.
- **#bytes:** tổng shallow size của các instance thuộc class.
- **class name:** tên class; array class có thể hiển thị dạng như byte[] hoặc java.lang.Object[].

Shallow size là kích thước trực tiếp của object, không phải retained size. Nếu một HashMap giữ tham chiếu đến hàng nghìn object, histogram không tự cho biết HashMap đó là GC root hoặc object nào giữ toàn bộ graph sống.

### In histogram

~~~bash
jmap -histo <pid>
~~~

Ví dụ:

~~~bash
jmap -histo 31840
~~~

Histogram giúp tìm class có nhiều instance hoặc chiếm nhiều shallow bytes. Nếu class ứng dụng như Session, CacheEntry hoặc byte[] đứng đầu, hãy điều tra allocation và reference graph trước khi kết luận đó là leak.

### Chỉ đếm object live

~~~bash
jmap -histo:live <pid>
~~~

Tùy chọn live chỉ đếm object còn sống sau quá trình xác định live objects. Thao tác này có thể yêu cầu garbage collection và gây pause đáng kể.

### Đếm tất cả object trong heap

~~~bash
jmap -histo:all <pid>
~~~

Tùy chọn all bao gồm cả object chưa còn reachable theo góc nhìn garbage collector. Trong JDK 24, help cho biết all là mặc định khi không chỉ định live hoặc all; nếu đồng thời có live và all thì live được ưu tiên.

Histogram all có thể cho thấy nhiều object đã trở thành garbage nhưng chưa được thu hồi. Vì vậy, số lượng object trong all không tương đương số object đang được ứng dụng giữ sống.

### Ghi histogram ra file

~~~bash
jmap -histo:live,file=histogram.txt <pid>
~~~

Tùy chọn file ghi histogram ra file thay vì chỉ hiển thị trên terminal. Tùy chọn parallel điều khiển số thread dùng để inspect heap:

~~~bash
jmap -histo:all,parallel=1,file=histogram-all.txt <pid>
~~~

- parallel=1 yêu cầu một thread để inspect.
- parallel=0 để JVM tự chọn số thread.
- Giá trị khác yêu cầu JVM cố gắng dùng số thread được chỉ định nhưng có thể dùng ít hơn.

Histogram có thể lớn. Đảm bảo thư mục output có đủ dung lượng và quyền ghi phù hợp.

## 5. Đọc histogram để điều tra memory leak

Một histogram đơn lẻ chỉ cho thấy snapshot. Để điều tra leak, cần so sánh qua thời gian và loại trừ garbage chưa được thu hồi.

Ví dụ hai lần chụp:

| Class | Histogram 1 | Histogram 2 | Nhận xét ban đầu |
|---|---:|---:|---|
| Session | 2.000 instance | 20.000 instance | Tăng mạnh, cần điều tra |
| byte[] | 8 MB | 60 MB | Có thể là payload hoặc buffer |
| String | 1 MB | 1,2 MB | Tăng nhẹ |
| RequestContext | 4.000 instance | 4.200 instance | Gần ổn định |

Đây chỉ là ví dụ giả định, không phải số đo thực tế.

### Quy trình đọc kết quả

1. Xác định histogram là live hay all.
2. So sánh cùng một loại snapshot giữa các lần thu thập.
3. Tìm class có instance count hoặc shallow bytes tăng liên tục.
4. Kiểm tra class đó có phải cache, session, queue, listener hoặc buffer hợp lệ không.
5. Dùng heap dump để tìm reference path và dominator.
6. Kiểm tra allocation stack hoặc JFR nếu cần biết object được tạo ở đâu.
7. Xác nhận bằng tải thực tế và regression test sau khi sửa.

### Histogram không cho biết nguyên nhân giữ object

Histogram không chỉ ra object nào đang giữ tham chiếu đến class có nhiều instance. Nó cũng không hiển thị retained heap trực tiếp.

Để tìm nguyên nhân, mở heap dump bằng Eclipse Memory Analyzer (MAT), JDK Mission Control hoặc công cụ phân tích HPROF phù hợp. Dùng dominator tree, paths to GC roots và retained size để xác định object graph nào đang giữ bộ nhớ.

Không kết luận memory leak chỉ vì một class có số lượng lớn. Một cache có giới hạn, pool hoặc queue có thể có nhiều object theo thiết kế.

## 6. Tạo heap dump với -dump

Heap dump là snapshot của Java heap được ghi thành file nhị phân HPROF. Nó chứa object, field, array và quan hệ tham chiếu tại thời điểm chụp.

Cú pháp:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Các tùy chọn trong JDK 24:

| Tùy chọn | Ý nghĩa |
|---|---|
| live | Chỉ dump object còn sống |
| all | Dump tất cả object trong heap |
| format=b | Định dạng HPROF binary |
| file=... | Đường dẫn file output |
| gz=n | Ghi HPROF gzip với mức n từ 1 đến 9 |

### Dump toàn bộ heap

~~~bash
jmap -dump:format=b,file=heap.hprof <pid>
~~~

Nếu không chỉ định live hoặc all, JDK 24 help mô tả mặc định là all. File HPROF có thể lớn gần bằng hoặc nhỏ hơn nhiều so với heap tùy số object, nội dung và cách lưu trữ.

### Chỉ dump object live

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

Tùy chọn live chỉ dump object được xác định là live. Quá trình này có thể yêu cầu garbage collection và gây pause.

### Dump rõ ràng tất cả object

~~~bash
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

Tùy chọn all giữ cả object chưa reachable. Dữ liệu này có thể hữu ích trong một số phân tích, nhưng file sẽ bao gồm nhiều object mà GC có thể thu hồi.

Nếu đồng thời chỉ định live và all, live được ưu tiên theo help của JDK 24.

### Nén heap dump

~~~bash
jmap -dump:live,format=b,gz=1,file=heap-live.hprof.gz <pid>
~~~

Mức nén:

- 1: nén nhanh hơn, tỷ lệ nén thấp hơn.
- 9: nén mạnh hơn, tốn CPU và thời gian hơn.
- Giá trị từ 1 đến 9.

Nén có thể giảm dung lượng file nhưng làm tăng CPU và thời gian thu thập. Chọn mức phù hợp với tình trạng service và giới hạn I/O.

### Đường dẫn output

Nên dùng đường dẫn tuyệt đối trong production để biết chính xác file được tạo ở đâu:

~~~bash
jmap -dump:live,format=b,file=/var/secure-diagnostics/app-live.hprof <pid>
~~~

Trên Windows, ví dụ:

~~~powershell
jmap -dump:live,format=b,file=C:\secure-diagnostics\app-live.hprof <pid>
~~~

Đảm bảo thư mục tồn tại, tài khoản chạy lệnh có quyền ghi và volume còn đủ dung lượng. Không ghi heap dump vào thư mục web root, thư mục public artifact hoặc thư mục tạm có quyền truy cập rộng.

## 7. Heap dump có thể ảnh hưởng production

Heap dump là thao tác nặng. Thời gian và tác động phụ thuộc kích thước heap, số object, GC algorithm, filesystem, CPU và cách JVM xử lý snapshot.

Các rủi ro chính:

- JVM có thể dừng ứng dụng trong một khoảng thời gian đáng kể.
- Full GC có thể được yêu cầu khi chỉ dump object live.
- Quá trình duyệt heap có thể dùng nhiều CPU và I/O.
- File có thể chiếm nhiều dung lượng đĩa.
- Disk đầy có thể ảnh hưởng các service khác cùng volume.
- JVM có thể bị timeout ở load balancer hoặc health check khi pause lâu.
- Heap dump có thể chứa dữ liệu nhạy cảm của người dùng.

### Lập kế hoạch trước khi dump

1. Xác định đúng PID và service.
2. Kiểm tra heap size và dung lượng volume.
3. Chọn live hoặc all theo câu hỏi cần trả lời.
4. Chọn thời điểm tải thấp hoặc maintenance window nếu phù hợp.
5. Chuẩn bị thư mục output được giới hạn quyền truy cập.
6. Xác nhận quy trình thu thập và chuyển file an toàn.
7. Theo dõi service health và disk usage.
8. Xóa hoặc lưu trữ file theo retention policy sau khi điều tra.

Không chạy heap dump lặp lại theo chu kỳ ngắn trên production mà không đánh giá overhead.

## 8. Bảo mật heap dump và histogram

Heap dump không chỉ chứa thông tin kỹ thuật. Nó có thể chứa:

- Password, access token, API key hoặc session cookie đang nằm trong object.
- Connection string và credential của database.
- Nội dung request/response và dữ liệu cá nhân.
- Email, số điện thoại hoặc thông tin định danh.
- Dữ liệu giao dịch, cache và payload chưa được xóa.
- Private key hoặc secret nếu ứng dụng giữ chúng trong memory.

Vì vậy, heap dump phải được xử lý như dữ liệu nhạy cảm.

### Quy tắc bảo vệ file

- Chỉ người điều tra được phê duyệt mới được đọc file.
- Dùng volume mã hóa hoặc cơ chế mã hóa file theo chính sách.
- Không tải heap dump lên dịch vụ chia sẻ công khai.
- Không gửi file qua email/chat không được phê duyệt.
- Không commit file vào Git hoặc đưa vào build artifact.
- Ghi lại người thu thập, thời điểm, PID, host, JDK và lý do thu thập.
- Giới hạn retention và xóa an toàn sau khi hết nhu cầu.
- Khi cần chia sẻ báo cáo, ưu tiên histogram đã redaction hoặc kết quả phân tích không chứa dữ liệu object thô.

Tên file heap dump cũng không nên chứa thông tin người dùng hoặc secret.

## 9. Thống kê class loader với -clstats

Class loader nạp class vào JVM. Một ứng dụng dùng plugin, hot reload, application server hoặc nhiều deployment có thể tạo nhiều class loader.

Dùng:

~~~bash
jmap -clstats <pid>
~~~

Báo cáo class loader statistics giúp xem:

- Class loader nào đang tồn tại trong heap.
- Parent class loader.
- Số lượng class được loader nạp.
- Thông tin về mức độ hoạt động và kích thước class metadata mà tool có thể thu thập.

Dữ liệu này hữu ích khi điều tra class loader leak. Ví dụ, ứng dụng redeploy nhiều lần nhưng class loader cũ vẫn được giữ bởi ThreadLocal, static reference, thread hoặc library cache.

### Dấu hiệu cần điều tra

- Số class loader tăng qua mỗi lần redeploy.
- Class loader của ứng dụng cũ vẫn còn sau khi undeploy.
- Một class loader giữ nhiều class không còn cần thiết.
- Thread hoặc static cache giữ tham chiếu đến class loader cũ.

jmap -clstats không tự xác định reference path gây leak. Dùng heap dump và phân tích GC roots để tìm object giữ class loader.

### Lệnh thay thế bằng jcmd

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Trên JDK 21.0.9 trong môi trường kiểm tra, diagnostic command VM.classloader_stats được hỗ trợ và có impact thấp. Danh sách command cụ thể phụ thuộc JVM; hãy dùng jcmd PID help trước khi chạy.

## 10. Thông tin object chờ finalization với -finalizerinfo

jmap có tùy chọn:

~~~bash
jmap -finalizerinfo <pid>
~~~

Lệnh in thông tin về object đang chờ finalization. Đây là dữ liệu hữu ích khi ứng dụng còn dùng cơ chế finalization cũ hoặc hàng đợi finalizer tăng bất thường.

Finalization không phải cách quản lý tài nguyên đáng tin cậy. Không dựa vào finalize() để đóng file, socket hoặc resource quan trọng. Dùng try-with-resources, AutoCloseable hoặc cơ chế quản lý vòng đời tường minh.

Lệnh tương ứng trên jcmd có thể là:

~~~bash
jcmd <pid> GC.finalizer_info
~~~

Tên và mức độ tác động của diagnostic command cần được xác nhận bằng help của JVM mục tiêu.

## 11. Dùng jcmd thay cho jmap

jcmd là công cụ diagnostic hiện đại được Oracle khuyến nghị. Nó gửi diagnostic command trực tiếp đến JVM và có thể cung cấp heap dump, histogram, class loader statistics, thread dump, JFR và nhiều dữ liệu khác.

### Heap histogram

~~~bash
jcmd <pid> GC.class_histogram
~~~

Để bao gồm cả object chưa reachable:

~~~bash
jcmd <pid> GC.class_histogram -all
~~~

Trên JDK 21.0.9 đã kiểm tra, GC.class_histogram có impact High. Mức tác động phụ thuộc kích thước heap và nội dung.

### Heap dump

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Lệnh này tạo HPROF dump. Theo help của JVM được kiểm tra, thao tác có impact High và yêu cầu full GC trừ khi chỉ định -all.

Để dump cả object unreachable:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

Có thể nén bằng tùy chọn -gz theo mức được help của JVM hỗ trợ:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

Nếu file đã tồn tại, kiểm tra tùy chọn overwrite trong help trước khi ghi đè.

### Class loader statistics

~~~bash
jcmd <pid> VM.classloader_stats
~~~

### Finalization queue

~~~bash
jcmd <pid> GC.finalizer_info
~~~

### Xem mức tác động trước khi chạy

~~~bash
jcmd <pid> help GC.heap_dump
jcmd <pid> help GC.class_histogram
~~~

Diagnostic command có thể có impact Low, Medium hoặc High. Đọc mô tả của đúng JVM mục tiêu trước khi chạy trên production.

### Bảng đối chiếu

| Nhu cầu | jmap | jcmd khuyến nghị |
|---|---|---|
| Heap histogram | -histo[:live] | GC.class_histogram |
| Heap dump | -dump:... | GC.heap_dump |
| Class loader statistics | -clstats | VM.classloader_stats |
| Finalization queue | -finalizerinfo | GC.finalizer_info |
| Heap summary | Tùy chọn thay đổi theo JDK | GC.heap_info |

jcmd có thể cung cấp command khác tùy JDK. Không giả định mọi JVM đều hỗ trợ chính xác cùng tập diagnostic commands.

## 12. Phân tích core dump bằng jhsdb jmap

Nếu JVM đã crash và có core dump, không dùng cú pháp jmap PID. Dùng Serviceability Agent qua jhsdb.

Xem help:

~~~bash
jhsdb jmap --help
~~~

Đọc heap summary từ core file:

~~~bash
jhsdb jmap --heap --core core.1234 --exe /path/to/java
~~~

Tạo histogram:

~~~bash
jhsdb jmap --histo --core core.1234 --exe /path/to/java
~~~

Xuất heap dump:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --core core.1234 --exe /path/to/java
~~~

Các điểm cần nhớ:

- --core và --exe phải được chỉ định cùng nhau.
- --exe phải là executable phù hợp với JVM đã tạo core.
- Core file có thể rất lớn và chứa dữ liệu nhạy cảm.
- Phân tích core yêu cầu đúng quyền truy cập và binary tương thích.
- Tên và cú pháp tùy chọn phải được kiểm tra theo JDK hiện tại.

### Cảnh báo khi attach jhsdb vào JVM đang chạy

jhsdb là công cụ Serviceability Agent và có trạng thái experimental/unsupported. Oracle cảnh báo attach jhsdb vào live process có thể làm process bị treo và nhiều khả năng crash khi debugger detach.

Vì vậy, ưu tiên dùng jhsdb với core dump để phân tích hậu sự cố. Không thử jhsdb --pid trên production chỉ để lấy histogram hoặc heap dump nếu chưa đánh giá và phê duyệt rủi ro dừng/crash service.

## 13. Từ heap dump đến phân tích object graph

Sau khi tạo file HPROF, mở bằng công cụ phân tích như Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích HPROF.

Các bước thường thực hiện:

1. Mở file heap dump.
2. Tạo histogram để xem class theo instance count và shallow bytes.
3. Xem dominator tree để tìm object giữ nhiều retained heap.
4. Tìm paths to GC roots để biết vì sao object còn reachable.
5. Kiểm tra static field, ThreadLocal, listener, cache và collection.
6. So sánh snapshot trước/sau khi tải hoặc sau khi kết thúc session.
7. Đối chiếu với source code và allocation profile.

### Shallow size và retained size

- **Shallow size:** kích thước trực tiếp của một object, không tính object khác mà nó tham chiếu.
- **Retained size:** tổng bộ nhớ có thể được giải phóng nếu object đó cùng các object chỉ được giữ bởi nó trở nên unreachable.

Histogram chủ yếu giúp nhìn shallow size theo class. Dominator tree và reference graph mới giúp tìm retained memory và object giữ reference.

### Ví dụ tình huống

Một service có class SessionCache tăng từ vài nghìn lên hàng trăm nghìn instance sau mỗi đợt traffic.

Histogram cho thấy SessionCache và byte[] tăng. Tuy nhiên, histogram không nói cache có giới hạn hay không. Trong MAT, dominator tree cho thấy một static ConcurrentHashMap giữ tất cả Session object. Paths to GC roots chỉ ra static field của SessionRegistry giữ map đó.

Hướng sửa có thể là đặt TTL, giới hạn kích thước, loại bỏ entry khi session kết thúc hoặc sửa lifecycle. Cần test tải và xác nhận retained heap giảm sau khi sửa.

Đây là ví dụ minh họa phương pháp phân tích, không phải kết quả đo của một ứng dụng cụ thể.

## 14. Lỗi thường gặp khi chạy jmap

### Not enough permissions hoặc attach failed

Kiểm tra user sở hữu JVM, quyền attach, OS policy và đúng PID. Dùng cùng tài khoản service theo quy trình được phép. Không tự ý nâng quyền.

### Process không tồn tại

PID có thể sai, process đã kết thúc hoặc PID được tái sử dụng. Xác minh lại bằng jps và OS process tool.

### jmap không tương thích với JVM

Dùng JDK tool cùng major version/vendor với JVM mục tiêu nếu có thể. Kiểm tra kiến trúc 32/64-bit, executable và runtime provider.

### jmap không phản hồi

Process có thể bị treo hoặc không tới safepoint. Oracle hướng dẫn dùng jhsdb trong một số tình huống process hung, nhưng cần lưu ý jhsdb attach live process có thể làm process treo và crash khi detach. Ưu tiên thu thập core theo quy trình postmortem hoặc dùng diagnostic workflow được hỗ trợ.

### Heap dump không tạo được

Kiểm tra:

- Đường dẫn file có hợp lệ không.
- Thư mục có tồn tại và có quyền ghi không.
- Dung lượng volume còn đủ không.
- File có đang tồn tại hoặc bị khóa không.
- JVM có còn phản hồi không.
- Quyền attach và security policy có cho phép không.

Không ghi đè heap dump cũ nếu chưa xác nhận nội dung đó đã được lưu trữ an toàn.

### File dump quá lớn

Dùng live dump nếu câu hỏi chỉ cần object còn sống, nén nếu phù hợp và chuẩn bị volume đủ dung lượng. Không loại bỏ object unreachable nếu mục tiêu điều tra là xem trạng thái toàn heap tại thời điểm chụp.

### Histogram thay đổi mạnh giữa hai lần chạy

Xác định cả hai lần dùng live hay all, tải ứng dụng, GC state và thời gian chụp. So sánh các snapshot cùng điều kiện trước khi kết luận có leak.

### Không tìm thấy file output

Đường dẫn tương đối được tính từ working directory của shell đang chạy lệnh. Dùng đường dẫn tuyệt đối và kiểm tra quyền truy cập của user chạy tool.

## 15. Quy trình thu thập heap evidence an toàn

1. Xác định service, host/container và PID hiện tại.
2. Xác minh process name, user và runtime version.
3. Xác định câu hỏi điều tra: histogram, heap dump, class loader hay finalizer queue.
4. Đọc help và impact của lệnh; ưu tiên jcmd cho diagnostic mới.
5. Ước lượng pause, CPU, I/O và dung lượng file.
6. Chọn live/all đúng mục tiêu.
7. Dùng thư mục output bảo vệ và có đủ dung lượng.
8. Thu thập tại thời điểm phù hợp và theo dõi service health.
9. Ghi metadata: host, PID, JDK, timestamp, lệnh, lý do và người thực hiện.
10. Phân tích HPROF trong môi trường được kiểm soát.
11. Redact dữ liệu nhạy cảm trước khi chia sẻ báo cáo.
12. Xóa file dump theo retention policy sau khi hoàn tất.

Nếu heap dump được tạo tự động khi OutOfMemoryError, cần bảo vệ cả file dump lẫn đường dẫn ghi. Có thể cấu hình JVM:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
~~~

Đây là tùy chọn JVM khi khởi động ứng dụng, không phải lệnh jmap. Kiểm tra dung lượng và quyền thư mục trước khi bật trong production.

## 16. Checklist sử dụng jmap

- Kiểm tra JDK version và jmap --help.
- Nhớ jmap là experimental/unsupported và ưu tiên jcmd.
- Xác minh đúng PID, host, container và user.
- Kiểm tra quyền attach trước khi chạy.
- Chọn histogram hoặc heap dump theo câu hỏi cần trả lời.
- Hiểu khác biệt giữa live và all.
- Nhớ histogram báo shallow bytes, không phải retained heap.
- Đánh giá pause/GC/CPU/I/O trước khi dump.
- Chuẩn bị dung lượng đĩa và đường dẫn tuyệt đối.
- Bảo vệ HPROF vì file có thể chứa password, token và dữ liệu người dùng.
- Dùng MAT hoặc công cụ tương thích để xem dominator tree và GC roots.
- Dùng jcmd GC.class_histogram và GC.heap_dump cho quy trình mới.
- Dùng jhsdb jmap với core file; thận trọng với live attach.
- Không xem một histogram đơn lẻ là bằng chứng đủ của memory leak.
- Lưu metadata và xóa dump theo retention policy.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jmap | Công cụ JDK chẩn đoán heap và class loader của JVM |
| Heap | Vùng bộ nhớ chứa object Java |
| Heap histogram | Thống kê instance count và shallow bytes theo class |
| Heap dump | Snapshot object graph ở định dạng HPROF |
| HPROF | Định dạng binary dùng lưu heap snapshot |
| Live object | Object còn reachable theo quá trình xác định live objects |
| Unreachable object | Object không còn reachable và có thể được GC thu hồi |
| Shallow size | Kích thước trực tiếp của object |
| Retained size | Bộ nhớ có thể được giải phóng khi object và các object chỉ nó giữ trở nên unreachable |
| Class loader | Thành phần nạp class vào JVM |
| Finalization queue | Các object đang chờ xử lý finalization |
| jcmd | Công cụ gửi diagnostic command đến JVM |
| jhsdb | Serviceability Agent dùng phân tích JVM hoặc core dump |
| MAT | Eclipse Memory Analyzer, công cụ phân tích heap dump |
| GC root | Điểm bắt đầu của đường tham chiếu giữ object reachable |
| Dominator tree | Cấu trúc giúp tìm object giữ retained heap lớn |
| JFR | Java Flight Recorder dùng thu thập sự kiện runtime |

jmap có thể giúp thu thập histogram và heap dump để điều tra bộ nhớ, nhưng đây là công cụ experimental/unsupported và thao tác có thể gây pause, GC, I/O lớn hoặc lộ dữ liệu nhạy cảm. Ưu tiên jcmd cho chẩn đoán mới, dùng công cụ phân tích HPROF để tìm reference path và retained heap, đồng thời bảo vệ mọi file dump như dữ liệu production nhạy cảm.

## Tài liệu tham khảo

- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle JDK 24 — [Troubleshooting Guide: Diagnosing Java Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jhsdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html)
- Oracle Java SE 24 — [Java HotSpot VM Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/)