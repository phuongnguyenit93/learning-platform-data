# Thông lượng, độ trễ và dung lượng bộ nhớ

Khi đánh giá một ứng dụng Java, chỉ đo thời gian chạy của một thao tác là chưa đủ. Một dịch vụ có thể xử lý nhiều request mỗi giây nhưng phản hồi chậm với một số người dùng; một ứng dụng có latency thấp khi ít tải nhưng nhanh chóng nghẽn khi nhiều request đồng thời; hoặc throughput tốt nhưng tiêu thụ quá nhiều bộ nhớ để chạy ổn định trong container.

Ba nhóm chỉ số cần xem cùng nhau là:

- **Thông lượng (throughput):** lượng công việc hoàn thành trong một đơn vị thời gian, thường là request/giây hoặc operation/giây.
- **Độ trễ (latency):** thời gian từ lúc một thao tác được gửi đến lúc có kết quả, thường đo bằng mili giây và phân tích theo phân vị.
- **Dung lượng bộ nhớ (memory footprint):** lượng bộ nhớ mà ứng dụng sử dụng, gồm heap, vùng ngoài heap và bộ nhớ native của tiến trình.

Trong Java 17, có thể quan sát các chỉ số này bằng Java Flight Recorder (JFR), công cụ jcmd, unified GC logging, Java Management APIs và công cụ benchmark như JMH. Cần đo trên workload đại diện, vì kết quả của một microbenchmark nhỏ không tự dự đoán được hiệu năng của toàn dịch vụ.

## 1. Thông lượng (throughput)

Throughput biểu thị số lượng công việc hoàn thành trong một khoảng thời gian. Tùy ứng dụng, đơn vị có thể là:

- HTTP requests/second (RPS).
- Messages/second.
- Database transactions/second.
- Operations/second.
- Records/second trong một pipeline xử lý dữ liệu.

Nếu hệ thống hoàn thành 12.000 request trong 60 giây, throughput trung bình trong khoảng đó là:

\[
\text{throughput} = \frac{12\,000}{60} = 200 \text{ requests/second}
\]

Cần phân biệt **offered load** (lượng request client đưa vào) với **achieved throughput** (lượng request hệ thống thực sự hoàn tất). Khi hệ thống quá tải, client có thể gửi 500 request/giây nhưng server chỉ hoàn tất 350 request/giây; phần còn lại có thể đang chờ, bị từ chối hoặc timeout.

### 1.1. Throughput không đồng nghĩa với tốc độ của một request

Một request chạy nhanh không bảo đảm hệ thống có throughput cao. Nếu mỗi request cần một kết nối độc quyền, một lock toàn cục hoặc một thao tác I/O tuần tự, các request khác có thể phải chờ.

Ngược lại, hệ thống có thể xử lý nhiều request song song nên throughput cao dù mỗi request mất vài chục mili giây.

Ví dụ:

| Hệ thống | Throughput | Latency trung bình |
| --- | ---: | ---: |
| A | 100 request/s | 5 ms |
| B | 1.000 request/s | 40 ms |

B hoàn thành nhiều request hơn trong một giây, nhưng mỗi request của B mất thời gian lâu hơn. Không thể kết luận B tốt hơn A nếu chưa biết mục tiêu nghiệp vụ, phân vị latency, tỷ lệ lỗi và tài nguyên tiêu thụ.

### 1.2. Throughput có thể bão hòa

Khi tăng số request đồng thời, throughput thường tăng lúc đầu vì CPU, worker và kết nối được sử dụng hiệu quả hơn. Đến một điểm, tài nguyên trở thành nút thắt:

- CPU gần bão hòa.
- Thread pool hết worker.
- Connection pool hết kết nối.
- Lock hoặc hàng đợi gây tranh chấp.
- GC tiêu thụ nhiều CPU.
- Database hoặc dịch vụ phụ thuộc không đáp ứng đủ nhanh.

Sau điểm bão hòa, tăng concurrency có thể chỉ làm hàng đợi dài hơn và latency tăng, trong khi throughput gần như không tăng hoặc giảm.

## 2. Độ trễ (latency)

Latency là thời gian từ lúc bắt đầu một thao tác đến khi thao tác đó hoàn tất theo góc nhìn được đo. Với HTTP, có thể đo từ lúc client gửi request đến lúc nhận đủ response; ở phía server, có thể đo thời gian xử lý từ lúc request vào đến lúc response sẵn sàng.

Cần xác định rõ điểm bắt đầu và kết thúc. Latency của một method trong JVM không giống latency end-to-end của request đi qua mạng, proxy, ứng dụng, database và dịch vụ phụ thuộc.

### 2.1. Vì sao không chỉ xem giá trị trung bình?

Latency thường không phân bố đều. Phần lớn request có thể nhanh, nhưng một nhóm nhỏ rất chậm do GC pause, lock contention, I/O, queueing hoặc hoạt động nền.

Các phân vị thường dùng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50 | 50% request hoàn tất trong thời gian này hoặc nhanh hơn; median |
| p90 | 90% request hoàn tất trong thời gian này hoặc nhanh hơn |
| p95 | 95% request hoàn tất trong thời gian này hoặc nhanh hơn |
| p99 | 99% request hoàn tất trong thời gian này hoặc nhanh hơn |
| p99.9 | 99,9% request hoàn tất trong thời gian này hoặc nhanh hơn |

Ví dụ:

| Chỉ số | Latency |
| --- | ---: |
| p50 | 18 ms |
| p95 | 75 ms |
| p99 | 420 ms |
| p99.9 | 1.800 ms |

Median 18 ms trông khá tốt, nhưng 1% request chậm nhất mất từ khoảng 420 ms trở lên. Với hệ thống có yêu cầu phản hồi nhanh, tail latency có thể quan trọng hơn trung bình.

Nên báo cáo histogram hoặc percentile cùng với số lượng mẫu. Không nên lấy trung bình của các percentile từ nhiều instance để suy ra percentile toàn hệ thống; hãy gộp histogram hoặc dữ liệu phân phối theo cách phù hợp.

### 2.2. Service time và queueing time

Một request có thể mất thời gian ở nhiều nơi:

~~~text
Client gửi
   |
   v
Network / Load balancer
   |
   v
Request queue
   |
   v
Application processing
   |
   +--> Database / remote service
   |
   v
Response serialization
   |
   v
Client nhận đủ response
~~~

Latency end-to-end gồm thời gian chờ và thời gian xử lý ở các thành phần liên quan. Một method Java chỉ chạy 2 ms nhưng request có thể mất 200 ms vì chờ worker hoặc database connection.

Khi tối ưu, hãy phân rã latency để xác định thời gian nằm ở CPU, queue, lock, I/O hay dịch vụ bên ngoài. Tối ưu một method vốn chỉ chiếm 1% tổng thời gian sẽ không cải thiện đáng kể latency end-to-end.

### 2.3. Tail latency và hiện tượng hàng đợi

Khi tải tiến gần khả năng phục vụ tối đa, một lượng nhỏ request chậm có thể tạo hiệu ứng dây chuyền:

1. Request xử lý lâu hơn giữ worker hoặc connection lâu hơn.
2. Request mới phải chờ trong queue.
3. Queueing time làm latency tăng.
4. Worker tiếp tục bị chiếm dụng, làm throughput khó tăng.
5. Timeout và retry có thể tạo thêm tải.

Retry không giới hạn có thể làm tình hình tệ hơn vì request mới được gửi khi hệ thống đang quá tải. Nên có timeout, giới hạn concurrency, backpressure và chính sách retry có kiểm soát.

## 3. Quan hệ giữa throughput, latency và concurrency

Một định luật hữu ích trong hệ thống ổn định là **Little's Law**:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số lượng request trung bình đang ở trong hệ thống (in-flight hoặc đang chờ).
- \(\lambda\): throughput trung bình, tính theo request/giây.
- \(W\): thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, nếu hệ thống hoàn tất trung bình 200 request/giây và mỗi request ở trong hệ thống trung bình 0,1 giây:

\[
L = 200 \times 0.1 = 20
\]

Trung bình có khoảng 20 request đang được xử lý hoặc chờ tại một thời điểm.

Little's Law mô tả quan hệ trung bình trong điều kiện hệ thống ổn định; nó không phải công thức để tự đặt concurrency tối ưu hoặc dự đoán percentile latency. Nếu queue tăng liên tục, hệ thống chưa ở trạng thái ổn định và việc diễn giải các giá trị trung bình cần thận trọng.

### 3.1. Tăng concurrency không luôn tăng throughput

Tăng số thread hoặc request đồng thời có thể giúp che độ trễ I/O và sử dụng CPU tốt hơn. Nhưng khi vượt quá mức phù hợp:

- Thread tranh chấp CPU và context switch tăng.
- Heap cần giữ nhiều request/object cùng lúc hơn.
- Queue dài làm latency tăng.
- Connection pool hoặc database trở thành nút thắt.
- GC phải xử lý nhiều object đang sống và allocation đồng thời.

Concurrency nên được điều chỉnh theo năng lực thực tế của CPU, bộ nhớ, database và dịch vụ phụ thuộc. Không có một con số thread phù hợp cho mọi ứng dụng.

## 4. Dung lượng bộ nhớ của ứng dụng Java

Một ứng dụng Java không chỉ dùng heap. Bộ nhớ của tiến trình thường gồm nhiều vùng:

~~~text
Tiến trình Java
|
+-- Java Heap
|   +-- Objects
|   +-- Arrays
|   +-- Collections
|
+-- Non-heap / JVM-managed
|   +-- Metaspace (class metadata)
|   +-- Code Cache (JIT compiled code)
|
+-- Native memory
|   +-- Thread stacks
|   +-- Direct buffers
|   +-- GC / JVM internal structures
|   +-- JNI / native libraries
|
+-- Memory-mapped files và vùng do hệ điều hành quản lý
~~~

Cách phân loại chi tiết phụ thuộc JVM implementation và hệ điều hành. Điều cần nhớ là **-Xmx chỉ giới hạn Java heap**, không phải tổng dung lượng RAM mà tiến trình có thể sử dụng.

### 4.1. Heap

Heap là vùng bộ nhớ JVM dùng để cấp phát phần lớn object và array. **-Xmx** đặt giới hạn heap tối đa; **-Xms** đặt kích thước heap ban đầu/tối thiểu theo cấu hình JVM.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar application.jar
~~~

Ở đây heap ban đầu là 512 MiB và giới hạn tối đa là 2 GiB. Đây chỉ là ví dụ cấu hình, không phải khuyến nghị chung cho mọi container hoặc máy chủ.

Heap được quản lý bởi garbage collector. **used** là lượng heap đang được sử dụng tại thời điểm quan sát; nó có thể gồm cả object sẽ được thu hồi ở lần GC sau. **committed** là dung lượng heap JVM đã cam kết có thể sử dụng; **max** là giới hạn tối đa được báo cáo, có thể không xác định trong một số môi trường.

### 4.2. Live set và retained memory

Sau khi GC thu hồi object không còn reachable, phần object còn sống được gọi gần đúng là live set. Đây là chỉ số quan trọng khi xác định heap thực sự cần thiết.

Nếu heap used tăng trước GC rồi giảm đáng kể sau GC, có thể ứng dụng đang tạo nhiều object ngắn hạn. Nếu lượng heap sau các chu kỳ GC tiếp tục tăng qua thời gian với cùng workload, có thể có object được giữ tham chiếu lâu hơn dự kiến hoặc cache/queue không có giới hạn.

Không nên kết luận có memory leak chỉ từ một lần heap tăng. Cần quan sát xu hướng qua nhiều chu kỳ, workload tương đương và heap dump/JFR khi cần điều tra.

### 4.3. Metaspace

Metaspace chứa metadata của class và được quản lý trong native memory. Việc nạp nhiều class, tạo class động hoặc giữ class loader lâu có thể làm vùng này tăng.

Ứng dụng có plugin, framework sinh proxy hoặc hot reload có thể cần chú ý vòng đời class loader. Nếu class loader không thể được thu hồi vì còn tham chiếu, metadata của class thuộc loader đó cũng có thể còn được giữ.

Metaspace không nằm trong heap nên tăng **-Xmx** không trực tiếp giải quyết việc metaspace tăng không kiểm soát.

### 4.4. Code Cache

JIT compiler có thể biên dịch bytecode thành mã máy và lưu trong Code Cache. Đây là vùng bộ nhớ do JVM quản lý, khác với Java heap.

Code Cache có thể thay đổi theo số lượng method được biên dịch và hoạt động tối ưu hóa. Không nên cộng nó vào heap used hoặc cho rằng **-Xmx** kiểm soát vùng này.

### 4.5. Direct buffer và native memory

**ByteBuffer.allocateDirect(...)** cấp phát vùng nhớ ngoài heap để phục vụ một số thao tác I/O hoặc xử lý dữ liệu nhị phân:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
~~~

Dung lượng direct buffer không được tính như object byte array thông thường trong heap. Tuy vậy, nó vẫn tiêu thụ bộ nhớ của tiến trình và có giới hạn/chi phí quản lý riêng.

Ngoài ra, JNI, thư viện native, thread stack, cấu trúc nội bộ GC và memory mapping cũng có thể làm process memory cao hơn heap committed.

### 4.6. Thread stack

Mỗi thread nền tảng (platform thread) có stack riêng. Nhiều thread đồng thời có thể làm native memory tăng đáng kể ngay cả khi heap không tăng tương ứng.

Stack size có thể được cấu hình bằng **-Xss**, nhưng giảm quá thấp có thể dẫn đến **StackOverflowError** trong code có call depth lớn. Tăng số thread cũng tăng tổng nhu cầu stack và chi phí lập lịch.

## 5. Phân biệt heap, process RSS và giới hạn container

Ba con số thường bị nhầm lẫn:

| Chỉ số | Đo điều gì? | Điều không thể suy ra trực tiếp |
| --- | --- | --- |
| Heap used | Object/array đang chiếm trong heap tại thời điểm đo | Tổng RAM tiến trình |
| Heap committed | Heap JVM đã cam kết sử dụng | Toàn bộ native memory |
| Process RSS | Các trang bộ nhớ của tiến trình hiện đang resident trong RAM theo hệ điều hành | Chỉ riêng heap hoặc lượng object sống |
| Container memory usage | Mức sử dụng bộ nhớ được cgroup/container runtime ghi nhận | Heap used đơn thuần |

Một tiến trình có **-Xmx=2g** vẫn có thể sử dụng nhiều hơn 2 GiB RAM vì còn metaspace, code cache, stacks, direct buffers và native allocations. Trong container, cần chừa headroom cho những vùng này và cho tiến trình phụ trợ nếu có.

Java 17 HotSpot có khả năng nhận biết giới hạn container trong các môi trường được hỗ trợ. **-XX:MaxRAMPercentage** có thể điều khiển tỷ lệ RAM được dùng để tính heap tối đa, nhưng tỷ lệ đó vẫn là ngân sách heap, không phải giới hạn tổng process memory.

Ví dụ:

~~~bash
java -XX:MaxRAMPercentage=60 -jar application.jar
~~~

Tỷ lệ 60% chỉ minh họa cú pháp. Cần chọn tỷ lệ dựa trên container memory limit, native memory, số thread, direct buffers, workload và headroom vận hành. Nếu đặt **-Xmx** tường minh, cấu hình đó sẽ chi phối heap max thay vì để tỷ lệ tự tính theo cách mặc định.

## 6. Allocation rate và garbage collection

**Allocation rate** là tốc độ ứng dụng tạo object mới, thường đo bằng bytes/second. Nó khác với live set:

- Allocation rate cao có thể đến từ nhiều object ngắn hạn.
- Live set cao nghĩa là nhiều object còn reachable sau khi GC.
- Một ứng dụng có thể allocation rate cao nhưng live set nhỏ.
- Một ứng dụng có allocation rate thấp vẫn có thể giữ một cache lớn trong heap.

Ví dụ:

~~~java
public static long countWords(String[] words) {
    long total = 0;

    for (String word : words) {
        String normalized = word.trim().toLowerCase();
        total += normalized.length();
    }

    return total;
}
~~~

Tùy dữ liệu và tối ưu hóa JIT, các thao tác trên có thể tạo object tạm. Nếu method được gọi với tần suất rất cao, allocation rate có thể tăng. Nhưng không nên chỉ nhìn source code rồi kết luận object chắc chắn được cấp phát; JIT có thể tối ưu một số trường hợp bằng escape analysis hoặc scalar replacement.

### 6.1. GC ảnh hưởng tới throughput và latency

GC cần CPU và có thể có các pha dừng ứng dụng (stop-the-world). Tác động tùy collector, heap, allocation pattern, object lifetime và cấu hình:

- GC tiêu thụ CPU có thể làm giảm CPU dành cho xử lý nghiệp vụ.
- Pause có thể làm tăng latency, đặc biệt ở tail.
- Heap quá nhỏ có thể dẫn đến GC thường xuyên.
- Heap lớn hơn có thể giảm áp lực GC trong một số workload nhưng tăng footprint và không đảm bảo pause thấp hơn.
- Object sống lâu làm tăng công việc quản lý vùng old/live set.

Không có một collector hay heap size tối ưu cho mọi ứng dụng. Phải đo với workload đại diện và mục tiêu latency/throughput cụ thể.

### 6.2. Không dùng System.gc() như chiến lược quản lý bộ nhớ

Gọi **System.gc()** chỉ đưa ra yêu cầu gợi ý cho JVM; không phải lệnh đảm bảo mọi object không dùng được sẽ được thu hồi ngay. Gọi thường xuyên có thể làm gián đoạn ứng dụng và làm kết quả đo không đại diện.

Tập trung vào vòng đời tham chiếu, giới hạn cache/queue, allocation pattern và cấu hình GC. Chỉ dùng các cơ chế explicit GC khi có lý do vận hành cụ thể và đã đo tác động.

## 7. Đo heap và non-heap bằng Java Management APIs

Java cung cấp **MemoryMXBean** để đọc mức sử dụng heap và non-heap. Đây là API chuẩn trong package **java.lang.management**.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class MemoryUsageDemo {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        print("heap", memory.getHeapMemoryUsage());
        print("non-heap", memory.getNonHeapMemoryUsage());
    }

    private static void print(String name, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%d MiB, committed=%d MiB, max=%d MiB%n",
                name,
                toMiB(usage.getUsed()),
                toMiB(usage.getCommitted()),
                toMiB(usage.getMax())
        );
    }

    private static long toMiB(long bytes) {
        return bytes < 0 ? bytes : bytes / (1024 * 1024);
    }
}
~~~

**MemoryUsage.getMax()** có thể là giá trị âm nếu không xác định. Ví dụ trên giữ giá trị âm thay vì hiển thị nó như một dung lượng thực tế.

**getNonHeapMemoryUsage()** cung cấp số liệu non-heap theo định nghĩa của JVM; nó không bao gồm mọi loại native allocation như direct buffers hoặc mọi vùng do thư viện native cấp phát. Vì vậy, không dùng riêng API này để suy ra tổng process memory.

### 7.1. Theo dõi số lần và thời gian GC

Có thể đọc thông tin collector qua **GarbageCollectorMXBean**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {

    System.out.printf(
            "%s: collections=%d, collectionTime=%d ms%n",
            gc.getName(),
            gc.getCollectionCount(),
            gc.getCollectionTime()
    );
}
~~~

Một số giá trị có thể là **-1** nếu implementation không cung cấp thông tin. **collectionTime** là số liệu tích lũy theo MXBean và độ chính xác phụ thuộc JVM; không nên coi nó là phép đo chính xác từng pause. Dùng JFR và GC logs khi cần phân tích chi tiết.

## 8. Quan sát GC bằng unified logging trong Java 17

Java 17 sử dụng unified JVM logging. Có thể bật log GC khi khởi chạy:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

Log giúp quan sát:

- Các lần GC bắt đầu và kết thúc.
- Heap trước/sau GC.
- Thời gian pause được ghi nhận.
- Các pha và hoạt động của collector.
- Safepoint liên quan đến việc dừng thread ứng dụng.

Cấu hình log nên phù hợp môi trường triển khai: ghi ra file có rotation/retention phù hợp, tránh để log tăng không giới hạn hoặc ghi vào filesystem có dung lượng nhỏ.

### 8.1. Đọc log cùng với latency

Nếu p99 tăng đúng vào các khoảng GC pause dài, GC có thể là một nguyên nhân. Nhưng tương quan thời gian chưa đủ để kết luận. Cần đối chiếu với CPU, thread scheduling, lock, I/O và queue.

Nếu GC logs cho thấy nhiều lần young collection nhưng pause ngắn, vấn đề có thể nằm ở nơi khác. Nếu old-generation occupancy tăng liên tục, hãy điều tra live set và retention. Nếu GC CPU cao, hãy xem allocation rate và thời gian sống của object.

## 9. Dùng Java Flight Recorder để tìm nguyên nhân

Java Flight Recorder (JFR) được tích hợp trong JDK và có thể ghi nhận nhiều loại sự kiện runtime với overhead thường thấp khi dùng cấu hình phù hợp. Nó hỗ trợ phân tích CPU, allocation, GC, lock contention, thread, I/O và nhiều sự kiện JVM khác.

Bắt đầu một recording trong 60 giây:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=60s filename=performance.jfr
~~~

**<pid>** là process ID của ứng dụng Java. Sau khi recording hoàn tất, xem tóm tắt:

~~~bash
jfr summary performance.jfr
~~~

Có thể mở file **.jfr** bằng Java Mission Control để xem:

- Method nào tiêu thụ CPU.
- Allocation nhiều ở class/method nào.
- GC event và pause.
- Thread bị block hoặc chờ lock.
- Socket/file I/O kéo dài.
- Thread state và hoạt động của JVM.

### 9.1. JFR và heap dump giải quyết câu hỏi khác nhau

JFR hữu ích để quan sát hành vi trong một khoảng thời gian: allocation xảy ra ở đâu, thread chờ gì, GC hoạt động ra sao.

Heap dump là ảnh chụp object graph tại một thời điểm, hữu ích để tìm object đang được giữ tham chiếu và đường dẫn đến GC root. Tạo heap dump có thể tốn thời gian và dung lượng lớn, thậm chí làm ảnh hưởng ứng dụng; cần thực hiện theo quy trình vận hành phù hợp.

Không phải mọi vấn đề memory đều cần heap dump. Bắt đầu bằng metrics, GC log và JFR; chỉ tạo heap dump khi cần phân tích retained object cụ thể.

## 10. Native Memory Tracking và bộ nhớ ngoài heap

Khi process RSS cao hơn nhiều so với heap committed, cần xem xét native memory. HotSpot có **Native Memory Tracking (NMT)** để thống kê một số nhóm cấp phát nội bộ của JVM.

NMT phải được bật khi JVM khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Hoặc chọn mức chi tiết hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Sau đó có thể dùng jcmd:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Lệnh **baseline** ghi nhận mốc để so sánh; **summary.diff** hiển thị thay đổi từ mốc đó. NMT có overhead và không theo dõi mọi allocation của mọi thư viện native hoặc toàn bộ cách hệ điều hành tính RSS. Hãy dùng kết quả như một nguồn chẩn đoán, không coi nó là phép đo toàn diện duy nhất.

### 10.1. Điều tra direct buffer

**BufferPoolMXBean** cung cấp số liệu về các buffer pool, bao gồm direct buffer pool trong những JVM hỗ trợ:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {

    System.out.printf(
            "%s: count=%d, used=%d MiB, capacity=%d MiB%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed() / (1024 * 1024),
            pool.getTotalCapacity() / (1024 * 1024)
    );
}
~~~

Số liệu này hữu ích khi ứng dụng dùng NIO hoặc thư viện dựa trên direct buffer. Nó không đại diện cho toàn bộ native memory.

## 11. Đo microbenchmark bằng JMH

Khi cần so sánh hai cách triển khai một thao tác nhỏ, nên dùng **JMH (Java Microbenchmark Harness)** thay vì tự viết vòng lặp với **System.currentTimeMillis()**.

JVM có JIT compilation, warmup, dead-code elimination, escape analysis và các tối ưu hóa phụ thuộc workload. Benchmark tự viết có thể đo nhầm chi phí khởi động, bị tối ưu bỏ kết quả hoặc tạo ra điều kiện khác xa ứng dụng thật.

Ví dụ một benchmark JMH:

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringBenchmark {
    private String input;

    @Setup(Level.Trial)
    public void setup() {
        input = "  Java 17 performance  ";
    }

    @Benchmark
    public int normalizedLength() {
        return input.strip().toLowerCase().length();
    }
}
~~~

JMH là thư viện benchmark riêng, không nằm trong JDK. Khi chạy benchmark, nên:

- Có warmup đủ để JVM đạt trạng thái ổn định.
- Dùng nhiều fork để giảm ảnh hưởng trạng thái JVM từ lần chạy trước.
- Chọn số vòng measurement và thời lượng đủ đại diện.
- Trả kết quả hoặc dùng **Blackhole** để tránh dead-code elimination.
- Giữ input và môi trường tương đương khi so sánh.
- Kiểm tra allocation rate nếu mục tiêu là giảm áp lực GC.

Một lệnh chạy thường gặp sau khi đóng gói benchmark:

~~~bash
java -jar target/benchmarks.jar -f 3 -wi 5 -i 10
~~~

JMH phù hợp để đo một thao tác cô lập. Nó không thay thế load test end-to-end khi cần đánh giá throughput và tail latency của dịch vụ có mạng, database, queue và nhiều thread.

## 12. Load test để đánh giá cả hệ thống

Để đo một service, cần phát workload gần với cách người dùng hoặc hệ thống khác thực sự sử dụng:

- Tỷ lệ request theo endpoint.
- Kích thước payload và phân bố dữ liệu.
- Số client đồng thời.
- Tốc độ gửi request (offered load).
- Tỷ lệ lỗi và timeout.
- Thời gian chạy đủ dài để thấy GC, cache và hoạt động nền.

Nên tăng tải theo từng mức để tìm điểm throughput bão hòa và xem latency bắt đầu tăng ở đâu. Không chỉ đo một mức tải thấp rồi kết luận ứng dụng có khả năng mở rộng.

### 12.1. Closed-loop và open-loop load

Trong closed-loop test, client thường đợi request trước hoàn tất rồi mới gửi request tiếp theo. Khi server chậm, tốc độ gửi của client cũng tự giảm; điều này có thể che giấu latency xấu dưới tải cao.

Trong open-loop test, tốc độ request được đưa vào độc lập hơn với thời gian phản hồi. Cách này giúp kiểm tra hệ thống dưới một offered load xác định, nhưng phải có giới hạn queue và chính sách khi hệ thống không theo kịp.

Một số công cụ load test có chế độ coordinated-omission correction để giảm sai lệch khi request bị gửi trễ do client chờ response trước. Khi đánh giá tail latency, hãy hiểu mô hình phát tải của công cụ.

### 12.2. Ma trận quan sát

Ở mỗi mức tải, ghi nhận ít nhất:

| Nhóm | Chỉ số |
| --- | --- |
| Workload | Offered RPS, achieved throughput, số request đồng thời |
| Latency | p50, p95, p99, p99.9 nếu đủ mẫu |
| Reliability | Error rate, timeout, retry, rejected request |
| CPU | Process CPU, CPU theo thread nếu cần, GC CPU |
| Heap | Used/committed/max, occupancy sau GC |
| GC | Tần suất, pause duration, allocation rate |
| Native memory | RSS, direct buffer, metaspace, NMT nếu bật |
| Runtime | Thread count, queue length, connection pool usage |

Đo cùng khoảng thời gian để có thể liên hệ các thay đổi. Một p99 tăng cùng lúc với queue length, thread count và GC activity có thể chỉ ra nhiều nguyên nhân phối hợp.

## 13. Tối ưu throughput, latency và memory theo thứ tự

Không nên tối ưu ba mục tiêu bằng các thay đổi rời rạc mà không biết bottleneck. Quy trình thực tế:

1. **Xác định mục tiêu:** ví dụ p99 dưới 200 ms ở 500 RPS, error rate dưới ngưỡng và memory dưới container limit.
2. **Lập baseline:** đo workload, cấu hình JVM, CPU, heap, native memory và latency distribution.
3. **Tìm bottleneck:** dùng JFR, GC logs, thread/queue metrics và profiling để xác định phần chiếm chi phí.
4. **Thay đổi một nhóm yếu tố:** chẳng hạn giảm allocation, điều chỉnh pool, cải thiện query hoặc giảm lock contention.
5. **Đo lại cùng workload:** so sánh throughput, p95/p99, error rate và memory.
6. **Kiểm tra soak test:** chạy đủ lâu để thấy memory retention, cache growth và hoạt động GC dài hạn.
7. **Giữ headroom:** bảo đảm ứng dụng vẫn ổn định khi tải tăng hoặc có burst.

### 13.1. Giảm allocation khi allocation rate là bottleneck

Nếu JFR cho thấy allocation cao và GC chiếm nhiều CPU, có thể xem xét:

- Tránh tạo object tạm không cần thiết trong vòng lặp nóng.
- Dùng buffer có vòng đời rõ ràng khi xử lý dữ liệu lớn.
- Tránh sao chép mảng/chuỗi lặp lại nếu có cách xử lý trực tiếp an toàn.
- Giới hạn cache và queue.
- Chọn cấu trúc dữ liệu phù hợp với workload.
- Tránh tối ưu thủ công trước khi profiler chỉ ra allocation thực tế.

Không nên tái sử dụng mutable object một cách tùy tiện nếu nó làm code khó an toàn luồng hoặc gây lỗi dữ liệu. Giảm allocation chỉ có ích khi không làm sai semantics và đã được đo.

### 13.2. Giảm retained heap

Nếu live set tăng theo thời gian, điều tra các cấu trúc giữ tham chiếu:

- Static collection hoặc singleton cache.
- Map không có eviction.
- Queue không giới hạn.
- Listener/callback không được gỡ bỏ.
- ThreadLocal giữ object lâu hơn vòng đời request.
- Class loader hoặc plugin bị giữ tham chiếu.
- Task/CompletableFuture bị lưu lại ngoài ý muốn.

Đặt giới hạn kích thước và chính sách eviction cho cache/queue. Nếu object vẫn reachable, GC không thể thu hồi nó chỉ vì ứng dụng không còn dùng về mặt logic.

### 13.3. Điều chỉnh heap và collector

Tăng **-Xmx** có thể giúp nếu heap thực sự quá nhỏ so với live set và allocation pattern. Nhưng tăng heap không sửa memory leak, không giới hạn native memory và có thể làm tổng footprint vượt container limit.

Thay collector hoặc cấu hình GC có thể cải thiện một mục tiêu nhưng làm mục tiêu khác xấu đi. Đánh giá đồng thời throughput, pause distribution, CPU và memory. Xác nhận collector đang dùng bằng GC log hoặc công cụ runtime thay vì giả định từ cấu hình mặc định.

## 14. Ví dụ tính toán ngân sách bộ nhớ cho container

Giả sử container có giới hạn 4 GiB. Không nên tự đặt heap max bằng toàn bộ 4 GiB vì process còn cần native memory và vùng dự phòng.

Một ngân sách minh họa có thể gồm:

| Thành phần | Ngân sách minh họa |
| --- | ---: |
| Java heap max | 2,5 GiB |
| Metaspace và Code Cache | 250 MiB |
| Thread stacks | 300 MiB |
| Direct buffers / native libraries / JVM native | 450 MiB |
| Headroom cho biến động và hệ điều hành | 500 MiB |
| **Tổng** | **4 GiB** |

Đây không phải công thức phân bổ cố định. Số thực tế phải được đo trên workload và runtime của ứng dụng. Nếu direct buffer tăng, số thread lớn hoặc thư viện native tiêu thụ nhiều, cần thay đổi ngân sách heap hoặc giới hạn các vùng đó.

Điều quan trọng là tổng process/container memory phải được quan sát cùng heap metrics. Một ứng dụng có heap used thấp vẫn có thể bị container OOM vì native memory hoặc RSS tăng.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Throughput tăng nhưng p99 xấu đi | Queueing, concurrency quá cao hoặc tail request bị kéo dài | Xem latency histogram, queue length và điểm bão hòa |
| Average latency tốt nhưng người dùng vẫn thấy request chậm | Tail latency bị che bởi trung bình | Theo dõi p95/p99/p99.9 và số lượng mẫu |
| Tăng thread nhưng throughput không tăng | CPU, lock, DB hoặc connection pool đã bão hòa | Tìm bottleneck trước khi tăng concurrency |
| -Xmx 2 GiB nhưng process dùng hơn 2 GiB | Heap không bao gồm native/non-heap toàn bộ | Đo RSS, NMT, direct buffers, stacks và metaspace |
| Heap used tăng trước GC | Object tạm đang được cấp phát | Xem allocation rate và GC logs |
| Heap sau GC tăng liên tục | Retained object/cache/queue hoặc leak | Dùng JFR, heap dump và phân tích GC roots |
| GC pause ngắn nhưng latency vẫn cao | Bottleneck có thể ở queue, I/O, lock hoặc dịch vụ ngoài | Phân rã latency và dùng JFR |
| Microbenchmark nhanh nhưng production chậm | Workload, warmup, concurrency hoặc I/O khác nhau | Dùng JMH cho method và load test cho hệ thống |
| Benchmark tự viết cho kết quả bất ổn | JIT, dead-code elimination, timer và warmup | Dùng JMH với fork/warmup/measurement phù hợp |
| Container bị OOM dù heap chưa đầy | Native memory hoặc tổng footprint vượt limit | Chừa headroom, đo RSS/NMT và giới hạn vùng cấp phát |
| Giảm heap làm latency tăng | GC xảy ra thường xuyên hơn hoặc live set sát giới hạn | Đo GC/occupancy và điều chỉnh theo workload |
| Tăng heap nhưng không hết memory leak | Object vẫn reachable | Tìm đường dẫn giữ tham chiếu; sửa ownership/cache/queue |

## 16. Bài tập thực hành

### Bài 1 — Tính throughput và latency

Một test hoàn tất 30.000 request trong 120 giây. Tính throughput trung bình. Sau đó cho biết vì sao chỉ có throughput chưa đủ để kết luận hệ thống đáp ứng tốt.

### Bài 2 — Đọc percentile

Một báo cáo có p50 = 20 ms, p95 = 80 ms, p99 = 600 ms. Giải thích điều gì xảy ra với nhóm request chậm nhất và vì sao average không mô tả đủ trải nghiệm.

### Bài 3 — Áp dụng Little's Law

Một service hoàn tất 400 request/giây, thời gian trung bình trong hệ thống là 50 ms. Tính số request trung bình đang in-flight hoặc chờ. Nêu giả định hệ thống đang ổn định.

### Bài 4 — Quan sát heap và non-heap

Chạy **MemoryUsageDemo** trên JDK 17. Ghi nhận used, committed và max. Tạo thêm object trong một vòng đời kiểm soát rồi quan sát số liệu thay đổi.

### Bài 5 — Theo dõi GC

Khởi chạy ứng dụng với unified GC logging. Tạo workload cấp phát object ngắn hạn và quan sát tần suất GC, heap trước/sau GC và pause.

### Bài 6 — Ghi JFR

Dùng jcmd bắt một recording trong lúc ứng dụng chịu tải. Xem allocation, CPU, lock và GC events. Xác định một hotspot và giải thích bằng số liệu.

### Bài 7 — Phân biệt heap với process memory

So sánh heap committed với RSS của process. Giải thích vì sao hai số không bằng nhau. Nếu có direct buffer, kiểm tra **BufferPoolMXBean**.

### Bài 8 — Thiết kế load test

Tăng offered load theo nhiều mức. Ghi achieved throughput, p95/p99, error rate, CPU, GC và memory. Xác định mức bắt đầu bão hòa và nêu bottleneck có bằng chứng.

## 17. Nguyên tắc cần nhớ

- **Throughput** đo lượng công việc hoàn tất; **latency** đo thời gian một thao tác; **memory footprint** đo tài nguyên bộ nhớ mà tiến trình sử dụng.
- Theo dõi cả achieved throughput và offered load; throughput không tăng mãi khi tăng concurrency.
- Dùng p50/p95/p99 để thấy tail latency; average có thể che các request rất chậm.
- Little's Law liên hệ số request trung bình trong hệ thống, throughput và thời gian trung bình khi hệ thống ổn định.
- **-Xmx** giới hạn Java heap, không giới hạn toàn bộ RSS hoặc container memory.
- Phân biệt allocation rate, live set, heap committed, metaspace, code cache, direct buffers, thread stacks và native memory.
- Dùng JFR, unified GC logging, jcmd, Management APIs và NMT để tìm nguyên nhân; hiểu phạm vi và overhead của từng công cụ.
- Dùng JMH cho microbenchmark và load test đại diện cho throughput/latency end-to-end.
- Thay đổi một yếu tố, đo lại cùng workload và kiểm tra cả hiệu năng lẫn bộ nhớ.
- Giữ headroom cho native memory và biến động tải; không tối ưu một chỉ số bằng cách làm hệ thống mất ổn định ở chỉ số khác.

Trong Java 17, hiệu năng cần được đánh giá trên toàn bộ vòng đời request và toàn bộ bộ nhớ tiến trình. Khi đo throughput, latency distribution, allocation/retained heap và native footprint cùng nhau, nhóm phát triển có thể xác định bottleneck thực sự, chọn cách tối ưu phù hợp và giữ ứng dụng ổn định dưới tải thực tế.
