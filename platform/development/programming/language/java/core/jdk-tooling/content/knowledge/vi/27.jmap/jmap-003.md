# Heap dump trong Java: thu thập và phân tích Java heap

## Mục tiêu

Sau bài này, bạn có thể giải thích heap dump là gì và nó lưu dữ liệu nào; phân biệt heap dump với heap histogram, thread dump và core dump; tạo heap dump từ JVM đang chạy bằng jmap và jcmd; hiểu khác biệt giữa dump object còn reachable và toàn bộ object; cấu hình tự động dump khi xảy ra OutOfMemoryError; phân tích file HPROF bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích; tìm retained heap, dominator và đường dẫn tới GC roots; so sánh nhiều snapshot để tìm memory leak; và thu thập dữ liệu an toàn trên môi trường production.

## 1. Heap dump là gì?

**Heap dump** là ảnh chụp dữ liệu của Java heap tại một thời điểm. Java heap là vùng bộ nhớ JVM dùng để cấp phát object và array. Heap dump ghi lại các object, class liên quan, giá trị field và quan hệ tham chiếu cần thiết để phân tích cấu trúc object graph.

Heap dump giúp trả lời các câu hỏi:

- Class nào đang có nhiều instance?
- Những object nào chiếm nhiều heap?
- Object nào giữ tham chiếu khiến một nhóm object không thể được garbage collector thu hồi?
- Collection, cache, listener hoặc session nào đang tăng không kiểm soát?
- Vì sao heap vẫn đầy dù ứng dụng đã xử lý xong request?
- Đường dẫn tham chiếu nào từ GC root tới object bị nghi ngờ giữ lại?

Heap dump thường được lưu ở định dạng nhị phân HPROF. File có thể được mở bằng Eclipse Memory Analyzer (MAT), JDK Mission Control hoặc một công cụ phân tích hỗ trợ đúng biến thể HPROF.

Heap dump là dữ liệu chẩn đoán có giá trị cao nhưng có thể rất lớn. Nó cũng có thể chứa dữ liệu nhạy cảm mà ứng dụng đang giữ trong bộ nhớ như access token, password, nội dung request, thông tin khách hàng hoặc dữ liệu nghiệp vụ.

## 2. Heap dump khác gì các loại dump khác?

| Loại dữ liệu | Nội dung chính | Câu hỏi thường trả lời |
|---|---|---|
| Heap dump | Object, array, field và reference trong Java heap | Object nào chiếm/giữ heap? |
| Heap histogram | Số instance và tổng byte theo class | Class nào đang chiếm nhiều heap? |
| Thread dump | Thread, trạng thái và stack trace | Thread đang chờ hoặc thực thi ở đâu? |
| Core dump | Snapshot bộ nhớ process ở cấp hệ điều hành | Process/JVM đang ở trạng thái nào khi crash? |
| JFR recording | Event runtime theo thời gian | Allocation, GC, latency và hoạt động JVM diễn ra thế nào? |

Histogram nhỏ và dễ thu thập hơn heap dump, phù hợp để sàng lọc ban đầu. Heap dump giữ thêm quan hệ tham chiếu, nhờ đó công cụ phân tích có thể tìm object giữ lại những object khác.

Core dump chứa thông tin rộng hơn về process, bao gồm cả native memory và trạng thái ở mức hệ điều hành. Heap dump tập trung vào Java heap, không thay thế core dump khi điều tra native crash hoặc lỗi thư viện JNI.

## 3. Khi nào nên tạo heap dump?

### Điều tra OutOfMemoryError

Khi JVM báo java.lang.OutOfMemoryError: Java heap space, heap dump có thể cho biết class hoặc object graph nào đang chiếm heap. Cần kết hợp exception, GC log, metrics và thời điểm sự cố để xác định nguyên nhân.

### Điều tra memory leak

Memory leak trong Java thường xảy ra khi object không còn cần thiết về mặt nghiệp vụ nhưng vẫn được giữ bởi một reference còn reachable từ GC root. Ví dụ:

- Static collection giữ object của request/session cũ.
- Cache không có giới hạn hoặc eviction policy.
- Listener đăng ký nhưng không được unregister.
- Thread-local giữ object sau khi tác vụ kết thúc.
- ClassLoader cũ bị giữ sau khi redeploy.
- Queue hoặc map tăng liên tục vì consumer không theo kịp producer.

### Kiểm tra heap sau deploy hoặc thay đổi tải

Có thể chụp snapshot ở các giai đoạn tương đương để so sánh object count, retained heap và reference path. Hãy giữ điều kiện tải và thời gian warm-up gần giống nhau; nếu không, khác biệt có thể chỉ phản ánh workload khác nhau.

### Xác minh nghi vấn từ histogram hoặc JFR

Histogram cho thấy class nào có nhiều instance hoặc chiếm nhiều byte. JFR có thể chỉ ra allocation rate và thời điểm tăng trưởng. Khi đã xác định class hoặc giai đoạn đáng nghi, heap dump giúp truy tìm object nào đang giữ các instance đó.

Không cần tạo heap dump cho mọi sự cố. Nếu chỉ cần xem heap usage tổng quát, bắt đầu bằng jcmd PID GC.heap_info; nếu cần phân bố theo class, dùng jcmd PID GC.class_histogram.

## 4. HPROF và nội dung trong heap dump

HPROF là định dạng binary được các công cụ Java sử dụng để lưu thông tin profiling và heap. Heap dump HPROF có thể chứa:

- Mô tả class và thông tin liên quan.
- Object instance và array.
- Giá trị field có thể được ghi nhận trong dump.
- Quan hệ tham chiếu giữa object.
- Thông tin về GC roots và object graph cần cho việc phân tích reachability.
- Thông tin thread/root liên quan theo khả năng của JVM và định dạng dump.

Một heap dump không phải bản sao toàn bộ RAM của máy. Nó tập trung vào Java heap và các metadata cần thiết để phân tích object graph. Native allocation, memory của thư viện C/C++, file mapping và toàn bộ trạng thái CPU/register không được biểu diễn như một core dump.

### Reachable và unreachable object

Một object còn **reachable** nếu có đường tham chiếu từ một GC root theo quy tắc reachability của JVM. GC root có thể gồm thread stack/local reference, static reference và các root nội bộ khác.

Object không còn reachable có thể được garbage collector thu hồi. Vì vậy, hai heap dump được tạo theo hai cách khác nhau có thể cho kết quả khác nhau:

- Chỉ dump object còn sống sau khi GC xử lý: loại bỏ object unreachable tại thời điểm chụp.
- Dump toàn bộ object, kể cả object unreachable: giữ lại nhiều dữ liệu hơn để điều tra một số trường hợp đặc biệt.

Object unreachable không tự động là memory leak. Memory leak thường liên quan object không còn cần thiết nhưng vẫn reachable, vì thế GC không thể thu hồi.

## 5. jmap và trạng thái hỗ trợ

jmap là công cụ dòng lệnh trong JDK để in thông tin bộ nhớ của một Java process. Nó có các tùy chọn lấy heap dump, histogram và class loader statistics.

Tài liệu Java SE 26 xếp jmap vào nhóm công cụ experimental/unsupported. Công cụ có thể không còn trong một phiên bản JDK tương lai. Oracle khuyến nghị sử dụng jcmd thay cho jmap để có khả năng chẩn đoán tốt hơn và giảm performance overhead.

Vì vậy:

- Hiểu jmap để đọc hệ thống cũ, script vận hành và tài liệu legacy.
- Kiểm tra jmap -h trên đúng JDK trước khi sử dụng vì option có thể khác giữa phiên bản/vendor.
- Với quy trình mới, ưu tiên jcmd PID GC.heap_dump.
- Với core dump hoặc phân tích postmortem, xem jhsdb jmap và các cảnh báo an toàn của Serviceability Agent.

Không dùng binary jmap của một JDK khác để chẩn đoán JVM đích nếu chưa xác minh tính tương thích. Oracle cũng cảnh báo các công cụ serviceability của JDK không được hỗ trợ khi dùng công cụ từ một phiên bản JDK khác để chẩn đoán JVM.

## 6. Tìm PID của JVM đích

jmap cần PID của Java process.

### Dùng jcmd

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

PID trong ví dụ chỉ minh họa. Chọn đúng process theo main class và command line.

### Dùng jps hoặc công cụ hệ điều hành

~~~bash
jps -l
~~~

Trên Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Trong Docker/container, jps hoặc jcmd -l từ host có thể không liệt kê JVM trong PID namespace riêng. Hãy tìm PID trong đúng container hoặc namespace, rồi chạy công cụ ở môi trường có thể attach vào JVM đích.

jcmd yêu cầu chạy trên cùng máy với JVM và có cùng effective user ID/group ID đã dùng để khởi chạy JVM. Các hạn chế attach, container, quyền hệ điều hành và -XX:+DisableAttachMechanism cũng có thể ảnh hưởng khả năng chẩn đoán. Không tự ý tăng quyền rộng chỉ để chạy dump.

## 7. Tạo heap dump bằng jmap

Cú pháp heap dump HPROF được tài liệu JDK mô tả:

~~~bash
jmap -dump:format=b,file=heap.hprof <PID>
~~~

Ví dụ tạo dump cho process PID 4128:

~~~bash
jmap -dump:format=b,file=order-service.hprof 4128
~~~

Giải thích:

- -dump: yêu cầu dump Java heap.
- format=b: ghi dump ở dạng binary HPROF.
- file=order-service.hprof: chỉ định đường dẫn file đích.
- 4128: PID của JVM cần thu thập.

JDK 26 Troubleshooting Guide dùng cú pháp jmap -dump:format=b,file=snapshot.jmap PID để minh họa heap dump từ process đang chạy. Phần mở rộng .hprof thường dễ nhận biết; tên file không làm thay đổi định dạng binary được ghi.

### Chỉ lấy object còn sống

Một số phiên bản jmap hỗ trợ suboption live:

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof <PID>
~~~

live yêu cầu chỉ dump object còn sống. Cú pháp và tùy chọn có thể khác theo phiên bản; kiểm tra jmap -h của đúng JDK trước khi dùng.

Không mặc định rằng mọi phiên bản jmap có cùng semantics với jcmd GC.heap_dump. Đặc biệt, mặc định của jmap và tùy chọn -all của jcmd không giống nhau.

### Histogram để sàng lọc trước khi dump

~~~bash
jmap -histo <PID>
~~~

Một số phiên bản hỗ trợ chỉ histogram object còn sống:

~~~bash
jmap -histo:live <PID>
~~~

Histogram hiển thị số instance, tổng dung lượng theo byte và tên class. Nó không chứa toàn bộ quan hệ tham chiếu để phân tích retained heap như heap dump.

### Các thông tin liên quan khác

~~~bash
jmap -clstats <PID>
~~~

In thống kê class loader của heap. Có ích khi nghi ngờ class loader hoặc metaspace tăng bất thường.

Tùy phiên bản, jmap -heap có thể hiển thị cấu hình và usage của heap. Với JDK mới, hãy kiểm tra option được hỗ trợ và ưu tiên command tương ứng trong jcmd.

## 8. Tạo heap dump bằng jcmd — cách được khuyến nghị

JDK 26 khuyến nghị dùng jcmd thay cho jmap để tạo heap dump.

Cú pháp:

~~~bash
jcmd <PID> GC.heap_dump heap.hprof
~~~

Ví dụ:

~~~bash
jcmd 4128 GC.heap_dump order-service.hprof
~~~

GC.heap_dump tạo file HPROF. Theo tài liệu JDK 26, command có impact cao, phụ thuộc kích thước và nội dung heap. Mặc định command yêu cầu full GC, trừ khi dùng option -all.

### Dump cả object unreachable

~~~bash
jcmd <PID> GC.heap_dump -all heap-all-objects.hprof
~~~

-all yêu cầu dump tất cả object, bao gồm object unreachable. Vì option này không yêu cầu full GC theo hành vi mặc định của command, dump có thể chứa object mà một lần GC bình thường sẽ thu hồi.

### Nén file dump

~~~bash
jcmd <PID> GC.heap_dump -gz=1 heap.hprof.gz
~~~

-gz nhận mức nén từ 1 đến 9:

- 1: nén nhanh, thường được khuyến nghị.
- 9: nén mạnh hơn, thường tốn thêm CPU và thời gian.

Nén có thể giảm dung lượng file nhưng không loại bỏ overhead của việc duyệt heap và tạo dump.

### Cho phép ghi đè file

~~~bash
jcmd <PID> GC.heap_dump -overwrite heap.hprof
~~~

Chỉ dùng -overwrite khi đã xác nhận file đích được phép thay thế. Mặc định command không ghi đè file có sẵn.

### Điều chỉnh số thread dump song song

~~~bash
jcmd <PID> GC.heap_dump -parallel=2 heap.hprof
~~~

-parallel yêu cầu số thread dùng cho thao tác heap dump. JVM có thể dùng ít thread hơn số được yêu cầu. Tùy chọn này không đảm bảo thời gian dump giảm theo tỷ lệ số thread.

### Xem option của JVM đích

~~~bash
jcmd <PID> help GC.heap_dump
~~~

Command help của JVM đích là nguồn xác nhận tốt nhất về option, kiểu giá trị và mặc định trên runtime đang chạy.

### So sánh cách lấy object

| Command | Ý nghĩa |
|---|---|
| jmap -dump:format=b,file=heap.hprof PID | Dump HPROF theo cú pháp jmap; kiểm tra mặc định của phiên bản đang dùng |
| jmap -dump:live,format=b,file=heap-live.hprof PID | Trên phiên bản hỗ trợ live, chỉ dump object còn sống |
| jcmd PID GC.heap_dump heap.hprof | Dump HPROF; mặc định yêu cầu full GC |
| jcmd PID GC.heap_dump -all heap-all.hprof | Bao gồm object unreachable và không yêu cầu full GC theo mặc định của command |

Đừng chuyển option từ jmap sang jcmd theo kiểu thay tên công cụ. Hai lệnh có cú pháp và quy tắc chọn object khác nhau.

## 9. Chọn đường dẫn, dung lượng và định dạng file

Heap dump có thể gần bằng dung lượng object đang được lưu trong heap, và file có thể lớn hơn dự kiến tùy nội dung, metadata, định dạng và cách dump.

Trước khi chạy:

1. Chọn filesystem có đủ dung lượng trống.
2. Chọn thư mục có quyền ghi cho user chạy JVM/diagnostic tool.
3. Xác nhận quota, giới hạn container và chính sách lưu trữ.
4. Tránh ghi dump vào filesystem đang gần đầy hoặc volume chứa dữ liệu vận hành thiết yếu.
5. Chọn tên file có PID và timestamp để tránh nhầm giữa nhiều snapshot.
6. Bảo vệ thư mục vì heap dump có thể chứa dữ liệu nhạy cảm.

Ví dụ trên Linux:

~~~bash
mkdir -p /var/tmp/java-dumps
jcmd <PID> GC.heap_dump /var/tmp/java-dumps/app-heap.hprof
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force C:\java-dumps
jcmd <PID> GC.heap_dump C:\java-dumps\app-heap.hprof
~~~

Nếu dump thất bại vì hết dung lượng, không tiếp tục chạy nhiều lần trên cùng filesystem. Kiểm tra file dở dang, dung lượng và log trước khi chọn vị trí mới.

## 10. Tự động tạo heap dump khi xảy ra OutOfMemoryError

Có thể cấu hình JVM tạo heap dump tự động khi xảy ra Java heap exhaustion:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/java-dumps/heap-%p.hprof -jar service.jar
~~~

Trong đó:

- -XX:+HeapDumpOnOutOfMemoryError: bật tự động tạo heap dump khi JVM ném OutOfMemoryError do Java heap exhaustion.
- -XX:HeapDumpPath: chỉ định đường dẫn và tên file.
- %p: được thay bằng PID của process.

Nếu không chỉ định HeapDumpPath, file mặc định thường có dạng java_pid<PID>.hprof trong working directory.

Lưu ý: tùy chọn này áp dụng cho OutOfMemoryError do Java heap exhaustion. Nó không bao phủ mọi trường hợp OutOfMemoryError, ví dụ lỗi tạo native thread hoặc exception được ứng dụng ném trực tiếp.

Đặt thư mục dump trước khi chạy ứng dụng, bảo đảm filesystem đủ dung lượng và có quyền ghi. Tùy chọn startup này không cần đợi người vận hành attach bằng jmap/jcmd khi sự cố xảy ra.

## 11. Phân tích heap dump bằng Eclipse Memory Analyzer (MAT)

Sau khi tạo file HPROF, mở bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích.

Một quy trình phân tích thường gồm:

1. Mở file .hprof trong MAT.
2. Chờ công cụ parse index và tính toán dữ liệu.
3. Xem Overview để nắm kích thước dump, số object và thống kê ban đầu.
4. Chạy Leak Suspects Report để tìm nhóm object đáng nghi.
5. Mở Histogram để xem số instance và shallow heap theo class.
6. Dùng Dominator Tree để xác định object đang giữ lượng retained heap lớn.
7. Xem Path to GC Roots để tìm chuỗi reference giữ object.
8. Đối chiếu kết quả với source code, cache policy, lifecycle và log ứng dụng.

MAT có thể cần thêm RAM ngoài kích thước heap dump để xây dựng index và phân tích. Hãy mở dump trên máy phân tích có đủ bộ nhớ và không nhất thiết phải mở ngay trên production server.

### Histogram

Histogram nhóm object theo class, thường hiển thị class name, number of instances, shallow heap và retained heap nếu công cụ đã tính. Histogram trả lời class nào có nhiều instance hoặc dùng nhiều memory, nhưng chưa giải thích vì sao object vẫn còn sống.

### Shallow heap và retained heap

**Shallow heap** là dung lượng object trực tiếp chiếm, không tính object khác mà nó tham chiếu.

**Retained heap** là dung lượng có thể được giải phóng nếu object hoặc nhóm object được loại khỏi object graph, theo phân tích dominator của công cụ.

Một object wrapper nhỏ có thể giữ một graph rất lớn. Ví dụ một static map chỉ chiếm vài MB shallow heap nhưng giữ hàng triệu object phía sau; retained heap của map hoặc entry có thể lớn hơn rất nhiều.

### Dominator Tree

Dominator Tree giúp tìm object hoặc nhóm object chi phối khả năng reachability của các object khác.

Nếu object A dominate object B, mọi đường đi từ GC root tới B đều đi qua A. Khi A không còn được giữ, B có thể trở thành unreachable cùng với các object chỉ được giữ qua nó.

Dominator lớn là điểm điều tra tốt, nhưng chưa tự động chứng minh leak. Một cache lớn có thể là hành vi thiết kế có chủ ý; cần so sánh với giới hạn cache và nhu cầu nghiệp vụ.

### Path to GC Roots

Path to GC Roots cho biết reference chain từ một GC root đến object đang phân tích. Ví dụ:

~~~text
GC Root
  -> ApplicationClass.staticCache
      -> HashMap.table
          -> CacheEntry
              -> CustomerSession
                  -> LargePayload
~~~

Đường dẫn này gợi ý staticCache đang giữ CustomerSession và LargePayload. Cần kiểm tra cache có eviction/expiration, session có được remove khi logout và reference có được release sau request hay không.

Khi xem path, có thể loại trừ một số weak/soft/phantom reference theo tùy chọn của công cụ để tập trung vào đường giữ object thực sự. Đọc rõ loại GC root và reference type trước khi kết luận.

## 12. Đọc histogram và so sánh nhiều snapshot

Một histogram ví dụ:

~~~text
 num      #instances       #bytes       class name
---------------------------------------------------
   1:         50000      8000000       com.example.Session
   2:         25000      4000000       byte[]
   3:         10000      1200000       java.lang.String
   4:          8000       640000       java.util.HashMap$Node
---------------------------------------------------
 Total:       93000     13840000
~~~

Các số trên chỉ minh họa định dạng, không phải kết quả của một ứng dụng thật.

Nếu com.example.Session tăng liên tục qua các snapshot, đó là tín hiệu cần điều tra. Hãy xác nhận:

- Số instance tăng theo thời gian hay chỉ tăng khi tải tăng?
- Heap usage có giảm sau khi workload kết thúc và GC có cơ hội chạy không?
- Instance có được giữ bởi cache, static field, listener hay thread-local không?
- Retained heap tăng cùng instance count hay chỉ tăng do object graph thay đổi?
- Các snapshot có được chụp sau cùng thời gian warm-up và workload tương đương không?

Một snapshot đơn lẻ thường không đủ chứng minh memory leak. So sánh ít nhất hai hoặc ba thời điểm dưới tải tương đương sẽ giúp thấy xu hướng.

## 13. Ví dụ thực hành: tạo heap dump cho một JVM mẫu

Ví dụ này tạo 16 byte array, mỗi array 1 MiB, rồi giữ chúng trong static list để chúng vẫn reachable trong lúc thu thập heap dump.

Tạo file HeapDumpTarget.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapDumpTarget {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 16; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        System.out.println("heap-dump-target-ready");
        System.out.println("retainedMiB=" + retained.size());

        while (true) {
            Thread.sleep(60_000);
        }
    }
}
~~~

### Biên dịch

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 HeapDumpTarget.java
~~~

### Khởi chạy JVM đích

Terminal A:

~~~bash
java HeapDumpTarget
~~~

Output chính xác:

~~~text
heap-dump-target-ready
retainedMiB=16
~~~

Giữ process chạy để có thể attach từ terminal khác.

### Tìm PID

Terminal B:

~~~bash
jcmd -l
~~~

Tìm process HeapDumpTarget và ghi lại PID.

### Tạo heap dump bằng jcmd

~~~bash
jcmd <PID> GC.heap_dump heap-dump-target.hprof
~~~

Lệnh mặc định yêu cầu full GC trước khi dump, nên object không còn reachable có thể được thu hồi trước khi snapshot được ghi.

Nếu muốn bao gồm cả object unreachable:

~~~bash
jcmd <PID> GC.heap_dump -all heap-dump-target-all.hprof
~~~

### Tạo heap dump bằng jmap

Trên JDK có hỗ trợ cú pháp jmap tương ứng:

~~~bash
jmap -dump:format=b,file=heap-dump-target-jmap.hprof <PID>
~~~

Nếu phiên bản hỗ trợ live và muốn chỉ lấy object còn sống:

~~~bash
jmap -dump:live,format=b,file=heap-dump-target-live.hprof <PID>
~~~

### Xác minh file

Linux:

~~~bash
ls -lh heap-dump-target*.hprof
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem heap-dump-target*.hprof |
    Select-Object Name, Length, LastWriteTime
~~~

Mở một file HPROF bằng MAT để kiểm tra class HeapDumpTarget và các byte[] được giữ trong static list.

### Dừng JVM mẫu

Quay lại terminal A và nhấn Ctrl+C. Không cần tạo OutOfMemoryError trong bài thực hành.

## 14. Tạo heap dump từ core file bằng jhsdb

Nếu JVM đã crash và hệ điều hành đã tạo core dump, có thể dùng Serviceability Agent qua jhsdb jmap để phân tích sau sự cố.

Ví dụ lấy histogram từ core file:

~~~bash
jhsdb jmap --histo --exe /path/to/java --core core-file
~~~

Tạo heap dump HPROF từ core file:

~~~bash
jhsdb jmap --binaryheap --dumpfile heap-from-core.hprof --exe /path/to/java --core core-file
~~~

In heap summary:

~~~bash
jhsdb jmap --heap --exe /path/to/java --core core-file
~~~

Trong đó:

- --exe: đường dẫn executable Java tương ứng với core file.
- --core: đường dẫn core dump.
- --histo: in histogram.
- --binaryheap: ghi heap thành HPROF binary.
- --dumpfile: tên file dump.
- --heap: in heap summary.

Nếu VM được tạo bằng JNI Invocation API, binary executable có thể không mang tên java; cần cung cấp đúng executable đã tạo core file.

**Cảnh báo:** jhsdb là công cụ experimental/unsupported. Attach jhsdb vào live process sẽ làm process bị treo và có khả năng crash khi debugger detach. Ưu tiên phân tích core file đã có; không dùng jhsdb attach live như cách tạo heap dump thông thường trên production.

Nếu jmap PID không phản hồi do process bị treo, Oracle hướng dẫn dùng jhsdb jmap để chạy Serviceability Agent. Hãy đánh giá tác động và thu thập core file theo quy trình vận hành trước khi dùng công cụ postmortem.

## 15. Kết hợp heap dump với các công cụ chẩn đoán khác

Heap dump thường hiệu quả nhất khi kết hợp với dữ liệu khác:

| Dữ liệu | Vai trò |
|---|---|
| GC log (-Xlog:gc*) | Cho biết heap tăng/giảm và thời điểm GC |
| jcmd GC.heap_info | Snapshot usage tổng quát |
| jcmd GC.class_histogram | Sàng lọc class chiếm nhiều heap |
| JFR | Allocation rate, GC pause, thread và event theo thời gian |
| Thread dump | Trạng thái thread, lock và stack |
| NMT | Memory nội bộ HotSpot nếu đã bật từ startup |
| Heap dump | Object graph và reference giữ object |

Ví dụ quy trình:

1. Metrics cảnh báo heap occupancy tăng liên tục.
2. Xem GC log để xác nhận old-generation occupancy không giảm sau các chu kỳ GC.
3. Lấy histogram để tìm class tăng instance.
4. Thu JFR để xác định allocation site và thời điểm tạo object.
5. Tạo heap dump để xem object graph, dominator và path to GC roots.
6. Đối chiếu source code và sửa lifecycle/cache/reference.
7. Chụp snapshot sau khi sửa để xác nhận retained heap ổn định.

Heap dump tập trung vào Java heap. Nếu RSS của process tăng nhưng heap ổn định, cần điều tra direct buffer, native library, thread stack, memory mapping và native allocation bằng NMT hoặc công cụ OS.

## 16. Tác động đến ứng dụng và an toàn production

Tạo heap dump có thể ảnh hưởng đáng kể đến JVM đang chạy.

Các rủi ro chính:

- JVM có thể pause trong quá trình duyệt và ghi heap.
- Dump mặc định qua jcmd yêu cầu full GC, có thể làm latency tăng.
- Thời gian dump phụ thuộc heap size, object count, collector, I/O và tốc độ disk.
- File dump có thể chiếm nhiều dung lượng.
- Heap dump có thể chứa secret, dữ liệu cá nhân, request body và nội dung nghiệp vụ.
- Ghi dump vào filesystem đầy có thể làm hỏng dịch vụ hoặc không tạo được artifact hoàn chỉnh.

Quy trình production:

1. Xác nhận PID và đúng JVM.
2. Xác nhận cần heap dump thay vì chỉ histogram/JFR.
3. Kiểm tra disk space, quota và quyền ghi.
4. Chọn volume riêng có đủ dung lượng.
5. Đánh giá thời điểm thu thập và tải hệ thống.
6. Bảo vệ file bằng quyền truy cập hạn chế và encryption at rest theo chính sách.
7. Ghi lại PID, JDK version, thời gian, command và lý do thu thập.
8. Xác minh file có kích thước hợp lý và mở được bằng công cụ phân tích.
9. Chia sẻ file qua kênh được phê duyệt.
10. Xóa hoặc lưu trữ theo retention policy.

Không upload heap dump lên dịch vụ công khai hoặc gửi vào ticket không được bảo vệ. Trước khi chia sẻ cho bên thứ ba, cần đánh giá dữ liệu nhạy cảm và chính sách bảo mật của tổ chức.

## 17. Lỗi thường gặp và cách xử lý

### Attach không được vào JVM

**Dấu hiệu:** jmap hoặc jcmd báo attach failed, permission denied hoặc không tìm thấy process.

**Nguyên nhân:** PID sai, JVM đã thoát, khác user/group, sai PID namespace/container hoặc attach mechanism bị vô hiệu hóa.

**Cách xử lý:** xác nhận PID trong đúng môi trường; chạy công cụ với effective user/group phù hợp; kiểm tra startup option -XX:+DisableAttachMechanism; xác nhận dùng tool tương thích với JDK đích.

### jmap không có hoặc không hỗ trợ option

**Dấu hiệu:** command not found hoặc báo option không hợp lệ.

**Nguyên nhân:** JDK distribution không đóng gói jmap, tool experimental đã bị loại bỏ hoặc cú pháp khác theo phiên bản.

**Cách xử lý:** ưu tiên jcmd <PID> GC.heap_dump; dùng jcmd <PID> help GC.heap_dump để xác nhận option; không tải binary jmap không rõ nguồn.

### Không đủ dung lượng disk

**Dấu hiệu:** dump bị lỗi giữa chừng, file nhỏ bất thường hoặc không thể hoàn tất.

**Nguyên nhân:** filesystem đầy, quota container hoặc dung lượng dự kiến không đủ.

**Cách xử lý:** kiểm tra dung lượng và file dở dang; chọn volume có đủ dung lượng; cân nhắc -gz=1 của jcmd; không lặp lại dump trên filesystem đang đầy.

### File dump đã tồn tại

**Dấu hiệu:** jcmd từ chối ghi file đích.

**Nguyên nhân:** file cùng tên đã tồn tại và -overwrite chưa được chỉ định.

**Cách xử lý:** chọn tên mới hoặc dùng -overwrite sau khi xác nhận có thể thay thế file cũ.

### Heap dump mất quá nhiều thời gian

**Dấu hiệu:** ứng dụng pause hoặc latency tăng mạnh trong khi dump.

**Nguyên nhân:** heap lớn, nhiều object, full GC, disk chậm hoặc I/O bị giới hạn.

**Cách xử lý:** đánh giá thời điểm thu thập, dùng histogram trước, kiểm tra disk throughput và cân nhắc nén; không chạy lặp lại liên tục khi chưa biết trạng thái lần trước.

### MAT không mở được file

**Dấu hiệu:** công cụ báo file hỏng, không nhận dạng HPROF hoặc hết memory khi indexing.

**Nguyên nhân:** dump chưa hoàn chỉnh, file bị truncate, biến thể format không tương thích hoặc máy phân tích thiếu RAM/disk.

**Cách xử lý:** xác minh command hoàn tất và kích thước file; tạo dump lại vào volume đủ dung lượng; dùng phiên bản MAT tương thích và tăng heap cho chính MAT nếu cần.

### Histogram cho thấy class lớn nhưng chưa rõ nguyên nhân

**Dấu hiệu:** một class có nhiều instance nhưng chưa biết object nào giữ chúng.

**Nguyên nhân:** histogram không chứa đầy đủ đường tham chiếu để phân tích retained heap.

**Cách xử lý:** tạo heap dump và dùng Dominator Tree/Path to GC Roots để tìm reference chain.

### Heap dump có nhiều object nhưng không chứng minh leak

**Dấu hiệu:** snapshot cho thấy nhiều object nhưng ứng dụng vẫn hoạt động bình thường.

**Nguyên nhân:** dữ liệu phản ánh workload, cache hợp lệ hoặc thời điểm chụp trước khi GC.

**Cách xử lý:** so sánh nhiều snapshot dưới tải tương đương; đối chiếu GC log, JFR và cache policy; kiểm tra object còn reachable và retained heap trước khi kết luận.

### Process bị treo, jmap không phản hồi

**Dấu hiệu:** jmap PID không trả kết quả.

**Nguyên nhân:** JVM đang ở trạng thái hang hoặc attach request không hoàn tất.

**Cách xử lý:** thu thập dữ liệu incident; nếu đã có core file, dùng jhsdb jmap để phân tích postmortem. Không attach jhsdb vào live process nếu chưa chấp nhận khả năng process bị treo và crash khi debugger detach.

### Heap dump tự động không được tạo khi OOME

**Dấu hiệu:** ứng dụng báo OutOfMemoryError nhưng không có file HPROF.

**Nguyên nhân:** chưa bật -XX:+HeapDumpOnOutOfMemoryError, HeapDumpPath sai, thiếu quyền ghi, disk đầy hoặc lỗi không phải Java heap exhaustion.

**Cách xử lý:** kiểm tra startup flags, HeapDumpPath, quyền và disk; xác nhận loại OutOfMemoryError; kiểm thử cơ chế trong môi trường staging.

## 18. Checklist trước và sau khi tạo heap dump

### Trước khi dump

- [ ] Xác định đúng JVM PID và JDK version.
- [ ] Chọn jcmd cho quy trình mới; chỉ dùng jmap khi cần tương thích.
- [ ] Xác định cần object còn sống hay cả object unreachable.
- [ ] Đọc jcmd <PID> help GC.heap_dump để biết option của target.
- [ ] Kiểm tra disk space, quota và quyền ghi.
- [ ] Chọn đường dẫn và tên file duy nhất.
- [ ] Đánh giá impact và thời điểm thu thập.
- [ ] Xác định chính sách bảo vệ dữ liệu nhạy cảm.

### Sau khi dump

- [ ] Xác nhận command hoàn tất.
- [ ] Xác nhận file tồn tại và kích thước hợp lý.
- [ ] Kiểm tra file có mở được bằng MAT hoặc công cụ tương thích.
- [ ] Lưu JDK version, PID, timestamp và command đã dùng.
- [ ] Phân tích Histogram, Dominator Tree và Path to GC Roots.
- [ ] Đối chiếu với GC log, JFR và metrics.
- [ ] Không kết luận leak từ một snapshot duy nhất.
- [ ] Bảo vệ và lưu trữ file theo retention policy.
- [ ] Xóa file tạm khi đã hoàn thành phân tích và được phép.

## 19. Tài liệu tham khảo chính thức

- [The jmap Command — Java SE 26 Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html) — danh mục công cụ JDK và vị trí tài liệu jmap trong bản phát hành.
- [Java SE 26 Troubleshooting Guide — The jmap Utility](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — trạng thái jmap, heap dump, histogram, class loader statistics và khuyến nghị dùng jcmd.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — GC.heap_dump, -all, -gz, -overwrite, -parallel và mức impact.
- [The jhsdb Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html) — jhsdb jmap, heap dump từ core file và cảnh báo khi attach vào live process.
- [Troubleshoot Memory Leaks — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html) — histogram, heap dump, JFR và quy trình điều tra memory leak.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/) — công cụ phân tích HPROF, histogram, dominator tree và retained heap.

Heap dump cung cấp object graph tại một thời điểm để tìm object đang chiếm hoặc giữ Java heap. Hãy ưu tiên jcmd, chọn đúng chế độ dump, chuẩn bị đủ dung lượng, phân tích retained heap và GC roots, rồi đối chiếu nhiều snapshot trước khi kết luận memory leak.
