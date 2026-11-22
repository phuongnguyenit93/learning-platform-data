# Lệnh jmap: cú pháp và thực hành

**jmap** là tiện ích dòng lệnh của JDK dùng để thu thập dữ liệu về heap của Java HotSpot VM đang chạy. Những thao tác thường dùng gồm in heap histogram, xuất heap dump HPROF, xem thống kê class loader và liệt kê object đang chờ finalization.

Bài này hướng dẫn cách chọn đúng JVM process, đọc cú pháp lệnh, chọn giữa histogram và heap dump, lưu kết quả ra file, phân tích dữ liệu và xử lý lỗi thường gặp. Một lab Java nhỏ ở phần sau giúp thực hành với một process do chính người học khởi chạy.

Trong Oracle JDK 24, jmap được phân loại là **experimental và unsupported**. Oracle khuyến nghị dùng **jcmd** cho chẩn đoán hiện đại vì có nhiều diagnostic command hơn và giảm overhead so với các tiện ích cũ. Hãy hiểu jmap để đọc runbook và xử lý hệ thống hiện có, đồng thời ưu tiên jcmd cho quy trình mới.

## 1. Cài đặt và kiểm tra jmap

jmap đi kèm JDK. Nếu máy chỉ cài runtime image tối giản, lệnh có thể không tồn tại.

Kiểm tra Java:

~~~bash
java --version
~~~

Kiểm tra jmap:

~~~bash
jmap --help
~~~

Trên OpenJDK 24.0.2, help liệt kê các lệnh:

- **-histo[:options]**: thống kê object theo class.
- **-dump:options**: ghi heap thành file.
- **-clstats**: thống kê class loader.
- **-finalizerinfo**: xem object đang chờ finalization.
- **-?**, **-h**, **--help**: in hướng dẫn.

Không giả định mọi JDK đều có cùng cú pháp. Các tùy chọn cũ có thể không còn trong bản mới; ví dụ help của OpenJDK 24.0.2 không liệt kê **-heap**. Hãy dùng help của đúng JDK chạy ứng dụng trước khi đưa lệnh vào script.

### jmap là công cụ chẩn đoán một lần

jmap không phải dashboard theo dõi heap liên tục. Mỗi lần gọi là một lần thu thập snapshot hoặc thống kê tại thời điểm đó. Nếu cần theo dõi xu hướng heap, GC pause và allocation theo thời gian, hãy dùng JFR, JDK Mission Control, JMX hoặc hệ thống metrics được tổ chức phê duyệt.

## 2. Cú pháp tổng quát

Cú pháp lệnh trong JDK 24:

~~~bash
jmap -clstats <pid>
jmap -finalizerinfo <pid>
jmap -histo[:<histo-options>] <pid>
jmap -dump:<dump-options> <pid>
~~~

<pid> là process identifier của JVM mục tiêu. Dấu ngoặc nhọn trong cú pháp chỉ biểu thị phần cần thay bằng giá trị thực tế; không gõ dấu này khi chạy lệnh.

Ví dụ:

~~~bash
jmap -histo 31840
~~~

31840 chỉ là PID minh họa. Không dùng PID ví dụ cho máy thật. Hãy tìm và xác minh PID của process mục tiêu trước khi chạy.

### Phân biệt hai nhóm tùy chọn

- Tùy chọn histogram bắt đầu bằng **-histo:** và có thể chọn **live**, **all**, **file** hoặc **parallel**.
- Tùy chọn heap dump bắt đầu bằng **-dump:** và có thể chọn **live**, **all**, **format=b**, **file** hoặc **gz**.

Các tùy chọn được nối với nhau bằng dấu phẩy. Không đặt dấu cách giữa các tùy chọn nằm trong cùng một nhóm.

## 3. Tìm và xác minh PID

Trên máy local, có thể dùng jps để tìm JVM:

~~~bash
jps -l
~~~

Output minh họa:

~~~text
31840 com.example.HeapLab
32004 com.example.ApiServer
~~~

Sau đó xác minh process bằng công cụ hệ điều hành.

Linux/macOS:

~~~bash
ps -p 31840 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 31840" |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine
~~~

Lưu ý:

- jps chỉ liệt kê các JVM HotSpot được instrument và có thể quan sát theo quyền hiện tại.
- LVMID do jps in ra thường là PID hệ điều hành nhưng không được bảo đảm luôn trùng.
- PID có thể được tái sử dụng sau khi process kết thúc.
- Container có thể dùng PID namespace, nên PID trong container khác PID nhìn từ host.
- jmap cần quyền attach phù hợp với process mục tiêu; thông thường công cụ chạy trên cùng máy và bằng tài khoản có quyền truy cập JVM.

Trước thao tác có tác động, xác nhận process name, user, command line và thời điểm khởi chạy. Không dùng PID cũ trong runbook mà chưa kiểm tra lại.

## 4. Heap histogram với -histo

Heap histogram cho biết số lượng object và tổng shallow bytes theo class. Đây thường là bước đầu để xem class nào đang chiếm nhiều object hoặc dung lượng.

Chạy histogram:

~~~bash
jmap -histo <pid>
~~~

Ví dụ:

~~~bash
jmap -histo 31840
~~~

Output có cấu trúc tương tự:

~~~text
 num     #instances         #bytes  class name
------------------------------------------------
   1:         12000         960000  com.example.Session
   2:          8000         512000  byte[]
   3:          6000         192000  java.lang.String
Total        26000        1664000
~~~

Các số ở trên chỉ để minh họa cấu trúc, không phải kết quả đo của một JVM thực tế.

Các cột:

- **num**: thứ hạng của class trong báo cáo.
- **#instances**: số object thuộc class.
- **#bytes**: tổng shallow size của các instance thuộc class.
- **class name**: tên class; array có thể hiển thị như byte[] hoặc java.lang.Object[].

### Shallow size không phải retained size

Shallow size là bộ nhớ trực tiếp của object. Nó không cộng toàn bộ object khác mà object đó tham chiếu.

Ví dụ, một HashMap có thể chỉ chiếm một lượng shallow bytes nhỏ nhưng giữ tham chiếu đến hàng triệu object. Histogram không tự cho biết map đó giữ bao nhiêu retained heap hoặc object nào đang giữ reference.

Muốn tìm nguyên nhân object còn sống, cần heap dump và công cụ phân tích reference graph, dominator tree hoặc paths to GC roots.

## 5. Chọn live hoặc all khi chạy histogram

### Chỉ thống kê object live

~~~bash
jmap -histo:live <pid>
~~~

live yêu cầu thống kê các object còn sống theo quá trình xác định reachability của JVM. Thao tác này có thể kích hoạt garbage collection và gây pause; mức ảnh hưởng phụ thuộc kích thước heap, GC và trạng thái ứng dụng.

Dùng live khi muốn giảm nhiễu từ object đã trở thành garbage nhưng chưa được thu hồi.

### Thống kê tất cả object

~~~bash
jmap -histo:all <pid>
~~~

all bao gồm cả object chưa reachable. Trong OpenJDK 24.0.2, help cho biết all là mặc định nếu không chỉ định live hoặc all. Nếu cả hai cùng xuất hiện, live được ưu tiên.

Dùng all khi cần xem cả object chưa được thu hồi tại thời điểm snapshot. Không so sánh histogram all với histogram live như thể chúng cùng một loại số liệu.

### Ghi histogram ra file

~~~bash
jmap -histo:live,file=histogram-live.txt <pid>
~~~

Ví dụ với tất cả object và một thread inspect:

~~~bash
jmap -histo:all,parallel=1,file=histogram-all.txt <pid>
~~~

parallel điều khiển số thread dùng để inspect heap:

- **parallel=0**: để JVM tự quyết định số thread.
- **parallel=1**: dùng một thread, tắt parallelism.
- Giá trị lớn hơn: JVM cố dùng số thread đó nhưng có thể dùng ít hơn.

Histogram có thể rất dài. Kiểm tra thư mục output, dung lượng đĩa và quyền truy cập trước khi chạy.

## 6. Heap dump với -dump

Heap dump là snapshot các object và quan hệ tham chiếu trong Java heap, được ghi ở định dạng HPROF binary.

Cú pháp:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Ví dụ dump toàn heap:

~~~bash
jmap -dump:format=b,file=heap.hprof <pid>
~~~

Các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| live | Chỉ dump object live |
| all | Dump tất cả object, gồm object unreachable |
| format=b | Định dạng HPROF binary |
| file=<path> | File đích |
| gz=<1..9> | Ghi file gzip với mức nén từ 1 đến 9 |

### Dump object live

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

Chọn lệnh này khi muốn phân tích object còn sống và các đường tham chiếu giữ chúng. Việc xác định live objects có thể yêu cầu garbage collection và làm JVM pause.

### Dump tất cả object

~~~bash
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

Lệnh này giữ cả object chưa reachable. Dữ liệu có thể hữu ích khi điều tra trạng thái heap rộng hơn, nhưng file thường chứa nhiều object mà GC có thể thu hồi.

Trong help của JDK 24, nếu không chỉ định live hoặc all thì mặc định là all; nếu cùng chỉ định cả hai, live được ưu tiên.

### Nén heap dump

~~~bash
jmap -dump:live,format=b,gz=1,file=heap-live.hprof.gz <pid>
~~~

Mức nén:

- **gz=1**: ưu tiên tốc độ nén.
- **gz=9**: nén mạnh hơn, thường tốn CPU và thời gian hơn.
- Chỉ dùng giá trị từ 1 đến 9.

Nén giúp giảm dung lượng lưu trữ nhưng không loại bỏ chi phí đọc heap và ghi file. Hãy chọn mức nén theo tải ứng dụng và dung lượng volume.

### Dùng đường dẫn tuyệt đối

Linux/macOS:

~~~bash
jmap -dump:live,format=b,file=/var/secure-diagnostics/heap-live.hprof <pid>
~~~

Windows PowerShell:

~~~powershell
jmap -dump:live,format=b,file=C:\secure-diagnostics\heap-live.hprof <pid>
~~~

Thư mục phải tồn tại và user chạy jmap phải có quyền ghi. Tránh ghi vào web root, thư mục public, thư mục upload hoặc volume có quyền truy cập rộng.

## 7. Lab: tạo một JVM có object để quan sát

Lab này tạo một chương trình giữ lại một số byte array trong static list. Các array vẫn được tham chiếu trong suốt thời gian chương trình chờ, vì vậy có thể tìm thấy chúng trong live histogram và heap dump.

Tạo file HeapLab.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class HeapLab {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        int count = args.length == 0 ? 32 : Integer.parseInt(args[0]);

        for (int i = 0; i < count; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        System.out.println("READY retained=" + retained.size());
        Thread.sleep(10 * 60 * 1000L);
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~bash
javac --release 17 HeapLab.java
~~~

Mở terminal thứ nhất và chạy:

~~~bash
java -Xms64m -Xmx256m HeapLab 32
~~~

Stdout chính xác:

~~~text
READY retained=32
~~~

Chương trình giữ 32 array, mỗi array có payload 1 MiB, và chờ tối đa 10 phút. Shallow bytes thực tế có thêm object header/alignment và có thể khác đôi chút theo JVM.

Mở terminal thứ hai, tìm PID:

~~~bash
jps -l
~~~

Tìm dòng HeapLab, rồi xác minh PID bằng ps hoặc PowerShell như phần trước.

Chạy histogram live:

~~~bash
jmap -histo:live <pid>
~~~

Tìm dòng byte[]. Số instance có thể lớn hơn 32 vì JVM và chương trình còn tạo các array khác.

Tạo heap dump live:

~~~bash
jmap -dump:live,format=b,file=heaplab-live.hprof <pid>
~~~

Mở heaplab-live.hprof bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích HPROF. Tìm HeapLab.retained và các byte[] để xem reference path.

Khi hoàn tất, quay lại terminal thứ nhất và nhấn Ctrl+C để kết thúc chương trình. Không dùng PID của lab cho service khác.

## 8. Thống kê class loader bằng -clstats

Class loader chịu trách nhiệm nạp class. Ứng dụng có plugin, application server, hot reload hoặc redeploy nhiều lần có thể có nhiều class loader.

Chạy:

~~~bash
jmap -clstats <pid>
~~~

Thông tin thống kê class loader giúp điều tra:

- Số class được nạp bởi từng loader.
- Quan hệ parent loader.
- Loader nào còn tồn tại trong heap.
- Dấu hiệu loader cũ chưa được giải phóng sau redeploy.

Một class loader cũ còn tồn tại có thể do ThreadLocal, thread, static field, listener hoặc cache giữ tham chiếu. jmap -clstats không chỉ ra đầy đủ reference path gây ra vấn đề; dùng heap dump và phân tích GC roots để tìm object giữ loader.

Lệnh tương ứng được khuyến nghị trên jcmd:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Trong JDK 24, VM.classloader_stats là diagnostic command có impact thấp theo tài liệu jcmd.

## 9. Thông tin object chờ finalization

Chạy:

~~~bash
jmap -finalizerinfo <pid>
~~~

Lệnh hiển thị thông tin về object đang chờ finalization. Đây là dữ liệu hữu ích khi điều tra code cũ còn dùng finalize().

Finalization không phải cơ chế quản lý resource đáng tin cậy. Không dựa vào finalize để đóng file, socket, database connection hoặc resource quan trọng. Hãy dùng try-with-resources, AutoCloseable hoặc lifecycle API tường minh.

Lệnh tương ứng trong jcmd:

~~~bash
jcmd <pid> GC.finalizer_info
~~~

Theo tài liệu jcmd JDK 24, GC.finalizer_info có impact Medium. Luôn kiểm tra help của JVM mục tiêu vì tập diagnostic commands phụ thuộc runtime.

## 10. jcmd là lựa chọn ưu tiên cho chẩn đoán mới

Oracle khuyến nghị dùng jcmd thay cho jmap. jcmd cung cấp các diagnostic command có mô tả impact và có thể hỗ trợ nhiều loại thông tin JVM hơn.

Liệt kê process:

~~~bash
jcmd -l
~~~

Xem command được JVM hỗ trợ:

~~~bash
jcmd <pid> help
~~~

Xem help của heap dump:

~~~bash
jcmd <pid> help GC.heap_dump
~~~

Xem help của histogram:

~~~bash
jcmd <pid> help GC.class_histogram
~~~

### Histogram bằng jcmd

~~~bash
jcmd <pid> GC.class_histogram
~~~

Bao gồm object unreachable:

~~~bash
jcmd <pid> GC.class_histogram -all
~~~

### Heap dump bằng jcmd

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Bao gồm object unreachable:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

Nén dump theo cú pháp được jcmd JDK 24 hỗ trợ:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

Có thể chỉ định -overwrite nếu cần ghi đè file đã tồn tại; không dùng tùy chọn này nếu chưa xác minh file cũ không còn cần thiết.

Theo tài liệu Oracle JDK 24, GC.heap_dump có impact High và yêu cầu full GC trừ khi dùng -all. GC.class_histogram cũng có impact High. Kiểm tra impact trong help trước khi thực hiện trên production.

### So sánh jmap và jcmd

| Mục tiêu | jmap | jcmd |
|---|---|---|
| Heap histogram | -histo[:options] | GC.class_histogram |
| Heap dump | -dump:options | GC.heap_dump |
| Class loader statistics | -clstats | VM.classloader_stats |
| Finalization queue | -finalizerinfo | GC.finalizer_info |
| Heap summary | Tùy phiên bản jmap | GC.heap_info |

Tên command và option có thể khác giữa JVM. Không giả định mọi JVM hỗ trợ cùng một tập diagnostic commands.

## 11. Phân tích core dump bằng jhsdb jmap

Khi JVM crash và tạo core dump, có thể dùng Serviceability Agent để phân tích offline.

Xem cú pháp:

~~~bash
jhsdb jmap --help
~~~

Tạo histogram từ core:

~~~bash
jhsdb jmap --histo --core core.1234 --exe /path/to/java
~~~

Xem heap summary:

~~~bash
jhsdb jmap --heap --core core.1234 --exe /path/to/java
~~~

Xuất HPROF từ core:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --core core.1234 --exe /path/to/java
~~~

--core và --exe phải được cung cấp cùng nhau. Executable phải phù hợp với JVM đã tạo core. Tùy chọn --pid dùng cho live process, nhưng Oracle cảnh báo attach jhsdb vào process đang chạy có thể làm process treo và có khả năng crash khi debugger detach. Không dùng live attach trên production chỉ để thử nghiệm.

Tài liệu JDK cũng ghi nhận remote --connect của jhsdb/debugd đã deprecated. Ưu tiên phân tích core dump offline hoặc diagnostic workflow được hỗ trợ.

## 12. Đọc heap dump bằng công cụ phân tích

jmap tạo file HPROF, nhưng không tự phân tích nguyên nhân memory leak. Dùng Eclipse Memory Analyzer (MAT), JDK Mission Control hoặc công cụ tương thích HPROF để xem object graph.

Các bước phổ biến:

1. Mở file HPROF.
2. Xem histogram theo class.
3. Mở dominator tree để tìm object giữ retained heap lớn.
4. Dùng paths to GC roots để tìm lý do object còn reachable.
5. Kiểm tra static field, collection, cache, ThreadLocal, listener và thread.
6. So sánh nhiều snapshot nếu cần xác định xu hướng.
7. Đối chiếu reference path với source code và lifecycle nghiệp vụ.

### Shallow size và retained size

- **Shallow size:** kích thước trực tiếp của object.
- **Retained size:** lượng heap có thể được giải phóng nếu object đó và những object chỉ được giữ bởi nó trở nên unreachable.
- Histogram giúp tìm class có nhiều instance hoặc shallow bytes.
- Dominator tree và reference graph giúp tìm object đang giữ retained heap.

Một class có nhiều instance không tự động là memory leak. Có thể đó là cache, pool hoặc queue có giới hạn hợp lệ. Cần đối chiếu với tải ứng dụng, giới hạn cấu hình và xu hướng theo thời gian.

## 13. Tác động và an toàn khi chạy trên production

Heap inspection có thể tốn nhiều tài nguyên. Trước khi chạy:

- Xác minh PID và đúng service.
- Ước lượng heap size và dung lượng volume.
- Chọn live/all theo câu hỏi cần trả lời.
- Xem impact của diagnostic command.
- Chọn thời điểm tải thấp hoặc maintenance window nếu phù hợp.
- Chuẩn bị thư mục output có quyền truy cập tối thiểu.
- Theo dõi latency, health check, CPU và disk I/O.
- Không chạy lặp lại liên tục nếu chưa đánh giá overhead.

### Heap dump là dữ liệu nhạy cảm

Heap dump có thể chứa password, token, session cookie, database credentials, request payload, dữ liệu cá nhân hoặc private material mà ứng dụng giữ trong memory.

Vì vậy:

- Lưu dump trong volume mã hóa hoặc vùng bảo vệ theo chính sách.
- Giới hạn người có quyền đọc file.
- Không gửi qua email/chat hoặc dịch vụ chia sẻ công khai.
- Không commit vào Git hoặc đưa vào build artifact.
- Redact báo cáo trước khi chia sẻ.
- Ghi nhận người thu thập, thời điểm, host, PID, JDK và lý do.
- Áp dụng retention và xóa an toàn sau khi hoàn tất điều tra.

Histogram thường ít nhạy cảm hơn heap dump nhưng vẫn có thể tiết lộ tên class, package và cấu trúc nội bộ. Cũng cần kiểm soát quyền truy cập.

## 14. Lỗi thường gặp và cách xử lý

### Attach failed hoặc not enough permissions

Kiểm tra process owner, quyền attach, OS policy và đúng PID. Thông thường công cụ cần chạy trên cùng host và bằng user/group có quyền phù hợp. Không tự động nâng quyền để bỏ qua kiểm soát bảo mật.

### Process không tồn tại

PID có thể sai, process đã kết thúc hoặc PID được tái sử dụng. Tìm lại bằng jps, xác minh bằng OS tool và chạy lệnh trong đúng host/container.

### Không ghi được file heap dump

Kiểm tra:

- Đường dẫn có hợp lệ không.
- Thư mục đã tồn tại chưa.
- User chạy lệnh có quyền ghi không.
- Volume còn đủ dung lượng không.
- File đích đã tồn tại hoặc bị khóa không.
- Có chính sách bảo vệ filesystem/container ngăn ghi không.

Ưu tiên đường dẫn tuyệt đối và không ghi đè file cũ khi chưa kiểm tra.

### JVM pause quá lâu

Heap lớn, nhiều object, live-object traversal hoặc full GC có thể làm thao tác kéo dài. Theo dõi service health, dừng các thao tác chẩn đoán tiếp theo và tuân thủ runbook incident. Lần sau, cân nhắc histogram hoặc JFR trước heap dump nếu mục tiêu chưa cần object graph đầy đủ.

### Histogram không giống nhau giữa các lần

Kiểm tra cả hai lần có cùng dùng live/all không, thời điểm chụp, tải ứng dụng và trạng thái GC. So sánh snapshot cùng điều kiện trước khi kết luận có leak.

### Heap dump mở không được

Kiểm tra file có hoàn tất hay bị cắt do hết dung lượng, phiên bản HPROF có được công cụ phân tích hỗ trợ và file có bị hỏng trong quá trình truyền không. Tính checksum trước/sau khi chuyển file để xác nhận bytes không đổi.

### jmap không có trên JDK

Một số runtime image tối giản không đóng gói jmap. Dùng JDK đầy đủ phù hợp với runtime mục tiêu hoặc dùng jcmd nếu có. Với quy trình mới, ưu tiên jcmd theo khuyến nghị của Oracle.

## 15. Quy trình chẩn đoán bộ nhớ đề xuất

1. Xác định service, host/container và PID hiện tại.
2. Xác minh user, command line, JDK vendor/version và heap flags.
3. Bắt đầu bằng metrics, GC logs hoặc JFR để hiểu xu hướng.
4. Nếu cần snapshot nhanh, chạy histogram và chọn live/all đúng mục tiêu.
5. So sánh histogram theo thời gian trong điều kiện tương đương.
6. Nếu cần tìm reference path, tạo heap dump ở thời điểm phù hợp.
7. Phân tích HPROF bằng MAT hoặc công cụ tương thích.
8. Tìm dominator, retained heap và GC roots.
9. Đối chiếu với source code, cache policy, listener và lifecycle.
10. Sửa nguyên nhân, chạy regression/load test.
11. Thu thập snapshot sau sửa để xác nhận retained heap và xu hướng đã cải thiện.
12. Bảo vệ và xóa file dump theo retention policy.

Không dùng một histogram hoặc heap dump đơn lẻ để kết luận memory leak nếu chưa hiểu workload và lifecycle của object.

## 16. Checklist trước khi chạy lệnh jmap

- Kiểm tra jmap --help của đúng JDK.
- Xác nhận đúng host, container, PID và user.
- Kiểm tra quyền attach.
- Chọn -histo hay -dump theo mục tiêu.
- Chọn live hay all có chủ đích.
- Hiểu tác động GC và pause.
- Chuẩn bị thư mục output, quyền ghi và dung lượng đĩa.
- Dùng đường dẫn tuyệt đối khi thu thập production.
- Bảo vệ HPROF như dữ liệu nhạy cảm.
- Ưu tiên jcmd cho diagnostic workflow mới.
- Đọc impact của GC.heap_dump và GC.class_histogram.
- Không dùng jhsdb live attach trên production nếu chưa đánh giá rủi ro.
- Dùng công cụ phân tích HPROF để tìm retained heap và GC roots.
- Lưu metadata của lần thu thập và checksum file.
- Xóa dump theo retention policy sau khi điều tra.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jmap | Công cụ JDK thu thập thông tin heap/class loader |
| PID | Process ID của JVM ở cấp hệ điều hành |
| Heap | Vùng bộ nhớ chứa object Java |
| Histogram | Thống kê số instance và shallow bytes theo class |
| Heap dump | Snapshot object graph ở định dạng HPROF |
| HPROF | Định dạng file nhị phân chứa dữ liệu heap |
| Live object | Object còn reachable theo quá trình xác định liveness |
| Unreachable object | Object không còn reachable và có thể được GC thu hồi |
| Shallow size | Kích thước trực tiếp của object |
| Retained size | Heap có thể được giải phóng khi object và phần chỉ nó giữ trở nên unreachable |
| Class loader | Thành phần nạp class vào JVM |
| Finalization | Cơ chế cũ xử lý object trước khi thu hồi; không nên dùng để quản lý resource |
| jcmd | Công cụ gửi diagnostic command đến JVM |
| jhsdb | Serviceability Agent dùng phân tích JVM hoặc core dump |
| MAT | Eclipse Memory Analyzer dùng phân tích heap dump |
| GC root | Điểm bắt đầu của đường tham chiếu giữ object sống |
| Dominator tree | Cấu trúc giúp tìm object giữ retained heap lớn |
| JFR | Java Flight Recorder dùng thu thập sự kiện runtime |

jmap cung cấp histogram, heap dump, class loader statistics và finalization information để hỗ trợ điều tra bộ nhớ. Hãy xác minh đúng process, hiểu tác động của live/all và garbage collection, bảo vệ file HPROF, rồi phân tích reference graph bằng công cụ phù hợp. Với quy trình chẩn đoán mới, ưu tiên jcmd theo khuyến nghị của Oracle.

## Tài liệu tham khảo

- Oracle JDK 24 — The jmap Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 24 — Troubleshooting Guide: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf