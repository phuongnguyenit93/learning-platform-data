# Phân tích Allocation bằng Java Flight Recorder (JFR)

Allocation là quá trình JVM cấp phát bộ nhớ cho object và array mới. Khi ứng dụng tạo nhiều object tạm thời, allocation rate tăng, garbage collector phải thu hồi chúng thường xuyên hơn và CPU có thể dành nhiều thời gian cho GC. Phân tích allocation bằng Java Flight Recorder (JFR) giúp tìm class, thread và stack trace tạo ra nhiều dữ liệu nhất, từ đó xác định nơi cần giảm cấp phát.

Bài này dùng JDK 17 trở lên và JDK Mission Control (JMC) để đọc recording. Trọng tâm là hiểu allocation sample, TLAB, các event JFR, cách ghi recording, cách tìm allocation hotspot và cách phân biệt allocation pressure với memory leak.

## 1. Allocation là gì?

Mỗi khi code tạo object hoặc array bằng new, gọi API tạo object, ghép chuỗi hoặc dùng thư viện tạo dữ liệu trung gian, JVM có thể phải cấp phát bộ nhớ trên Java heap.

Ví dụ:

~~~java
Customer customer = new Customer();
byte[] buffer = new byte[8192];
String message = "Order-" + orderId;
~~~

Các dòng trên tạo object hoặc array. Một request thực tế có thể tạo hàng trăm hoặc hàng nghìn object qua code ứng dụng, framework và thư viện.

Allocation analysis trả lời các câu hỏi:

- Class nào được tạo nhiều hoặc chiếm nhiều byte allocation?
- Method/stack trace nào là nguồn cấp phát chính?
- Thread nào tạo ra nhiều object nhất?
- Allocation diễn ra chủ yếu trong TLAB hay ngoài TLAB?
- Allocation rate tăng ở thời điểm nào trong recording?
- Những object đó là tạm thời hay được giữ lại lâu dài?

Allocation profile đặc biệt hữu ích khi ứng dụng có GC chạy thường xuyên, CPU tăng trong lúc xử lý request, throughput giảm hoặc latency tăng do áp lực cấp phát.

## 2. Phân biệt allocation với memory đang được giữ

Đây là điểm quan trọng nhất khi đọc dữ liệu allocation:

- **Allocated bytes:** tổng lượng bộ nhớ đã được cấp phát trong một khoảng thời gian.
- **Live/retained objects:** object vẫn còn được tham chiếu và chưa thể thu hồi tại thời điểm kiểm tra.
- **Heap used:** lượng heap đang được sử dụng tại một thời điểm.
- **Allocation rate:** lượng byte được cấp phát trong một đơn vị thời gian, thường tính bằng MB/s.

Một object có thể được cấp phát rồi trở nên unreachable ngay sau đó. Nó vẫn làm tăng allocation pressure nhưng có thể được GC thu hồi rất nhanh. Ngược lại, một object được cấp phát một lần nhưng bị cache hoặc static collection giữ lại lâu có thể làm heap tăng mà không tạo allocation rate cao.

Ví dụ:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    byte[] temporary = new byte[4096];
    process(temporary);
}
~~~

Vòng lặp có thể tạo gần một triệu array tạm thời. Nếu các array không bị giữ lại, chúng tạo allocation pressure nhưng không nhất thiết gây memory leak.

Ngược lại:

~~~java
static final List<byte[]> CACHE = new ArrayList<>();

void cache(byte[] data) {
    CACHE.add(data);
}
~~~

Nếu cache tăng liên tục và không loại bỏ phần tử, object có thể còn sống lâu sau GC. Đây là vấn đề retention/leak cần phân tích đường tham chiếu, không thể kết luận chỉ từ allocation sample.

Vì vậy, allocation profile dùng để tìm nơi tạo object; heap dump, old-object sampling và phân tích GC roots dùng để tìm object được giữ lại.

## 3. TLAB là gì?

TLAB là viết tắt của Thread-Local Allocation Buffer. JVM dành một vùng nhỏ trong heap cho từng thread để thread có thể cấp phát object nhanh bằng cách di chuyển con trỏ cấp phát trong vùng đó.

Quy trình đơn giản:

1. JVM cấp cho thread một TLAB.
2. Khi thread tạo object phù hợp, JVM cấp phát trong TLAB của thread đó.
3. Khi TLAB gần đầy hoặc không còn đủ chỗ, JVM cấp TLAB mới.
4. Object không được cấp phát trong TLAB có thể được cấp phát ngoài TLAB.

TLAB giảm tranh chấp giữa các thread khi nhiều thread cùng tạo object. Trong HotSpot, TLAB được bật mặc định trong các cấu hình thông thường; tùy chọn -XX:-UseTLAB có thể tắt nó.

### 3.1. Allocation trong TLAB

Object nhỏ và phù hợp với vùng còn trống thường được cấp phát trong TLAB. Đây là đường cấp phát phổ biến trong nhiều ứng dụng Java.

TLAB có kích thước hữu hạn. Khi cần TLAB mới, JVM phải xử lý việc cấp phát buffer và có thể phát sinh event liên quan đến việc cấp TLAB mới.

### 3.2. Allocation ngoài TLAB

Object lớn hoặc không phù hợp với TLAB có thể được cấp phát ngoài TLAB. Các allocation này có thể có chi phí khác với fast path trong TLAB.

Không nên kết luận object nào cũng phải đi ngoài TLAB chỉ vì nó có kích thước lớn hơn một ngưỡng cố định. Quyết định còn phụ thuộc TLAB còn bao nhiêu chỗ, cấu hình JVM và runtime.

### 3.3. Vì sao cần phân biệt hai loại?

JMC có thể phân tích allocation trong TLAB và ngoài TLAB. Điều này giúp xác định áp lực đến từ lượng lớn object nhỏ được tạo liên tục hay từ các object lớn.

Tuy nhiên, event count không đồng nghĩa với tổng số object của ứng dụng. Đặc biệt, event liên quan tới việc cấp TLAB mới không đại diện cho mọi object được cấp phát bên trong TLAB đó.

## 4. Các JFR event liên quan đến allocation

JFR thu thập dữ liệu dưới dạng event có timestamp và payload. Với JDK 17, các event thường gặp trong phân tích allocation gồm:

| Event | Ý nghĩa và dữ liệu chính |
|---|---|
| jdk.ObjectAllocationSample | Mẫu allocation có trọng số, thường gồm class, thread, stack trace và weight |
| jdk.ObjectAllocationInNewTLAB | Thông tin allocation gắn với việc cấp phát TLAB mới; có class, allocation size, TLAB size, thread và stack |
| jdk.ObjectAllocationOutsideTLAB | Thông tin object allocation ngoài TLAB; có class, allocation size, thread và stack |
| jdk.ThreadAllocationStatistics | Thống kê lượng allocation theo thread |

Tên event và các field khả dụng cần được xác nhận trong metadata của recording và phiên bản JDK đang chạy.

### 4.1. ObjectAllocationSample

jdk.ObjectAllocationSample là event lấy mẫu allocation. Nó được giới thiệu từ JDK 16 để hỗ trợ profiling allocation với overhead thấp hơn các event allocation chi tiết cũ.

Các field hữu ích:

- objectClass: class của object được sample.
- eventThread: thread liên quan tới sample.
- stackTrace: call stack tại vị trí allocation.
- weight: lượng byte ước lượng mà sample đại diện.

weight là trường quan trọng. Một sample có thể đại diện cho nhiều byte allocation; cộng weight theo class, thread hoặc stack trace cho ước lượng allocation pressure. Không đếm mỗi event như một object chính xác và không coi weight là kích thước chính xác của riêng object được sample.

Sampling là phương pháp thống kê. Kết quả phù hợp để xếp hạng hotspot và so sánh xu hướng; nó không phải bản kê đầy đủ từng object được tạo.

### 4.2. ObjectAllocationInNewTLAB

Event này ghi thông tin về allocation gắn với việc cấp một TLAB mới. Các field thường có:

- objectClass: class của object liên quan.
- allocationSize: kích thước allocation được ghi nhận.
- tlabSize: kích thước TLAB mới.
- eventThread và stackTrace: thread và call stack liên quan.

Đây không phải event được phát ra cho từng object nhỏ được cấp phát trong TLAB. Không lấy số event này làm tổng số object đã tạo trong TLAB.

### 4.3. ObjectAllocationOutsideTLAB

Event này ghi allocation xảy ra ngoài TLAB. Nó thường hữu ích khi điều tra object lớn hoặc allocation không thể đi qua fast path trong TLAB.

Field allocationSize giúp xem kích thước allocation được ghi nhận; objectClass, eventThread và stackTrace giúp lần về nguồn cấp phát.

### 4.4. ThreadAllocationStatistics

Event này cung cấp thống kê allocation theo thread. Nó hữu ích khi muốn biết thread nào tạo nhiều dữ liệu nhất, ví dụ request worker, scheduler, background consumer hoặc batch worker.

Số liệu theo thread cần được đọc cùng workload và thời lượng hoạt động. Một thread xử lý nhiều request hơn có thể có allocation cao đơn giản vì nó làm nhiều công việc hơn.

## 5. Chọn recording template phù hợp

JFR có hai cấu hình dựng sẵn trong thư mục <JAVA_HOME>/lib/jfr:

| Template | Mục đích |
|---|---|
| default.jfc | Bộ event cơ bản, overhead thấp, phù hợp recording liên tục |
| profile.jfc | Thu thập nhiều dữ liệu hơn để profiling trong khoảng thời gian giới hạn; overhead và dung lượng recording thường cao hơn |

Để tìm allocation hotspot, thường bắt đầu bằng recording ngắn dùng profile. Với recording liên tục trên production, hãy cân nhắc default và xác nhận event allocation cần thiết có được bật hay không.

Không phải mọi template, cấu hình JMC hoặc recording tùy chỉnh đều ghi cùng một tập event. Một recording có thể không chứa allocation data dù JVM hỗ trợ JFR. Luôn kiểm tra event thực tế trong recording trước khi kết luận không có allocation.

JDK 16 giới thiệu jdk.ObjectAllocationSample và ghi nhận event này được bật trong cấu hình default và profile chuẩn ở thời điểm đó. Các event TLAB chi tiết có overhead cao hơn và có thể bị tắt trong template tiêu chuẩn. Với recording cụ thể, hãy xem event settings và metadata thay vì dựa vào giả định.

## 6. Tạo JFR recording khi khởi chạy ứng dụng

Có thể bắt đầu recording ngay khi JVM khởi động bằng -XX:StartFlightRecording.

Cú pháp thực hành:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,duration=30s,filename=allocation.jfr AllocationDemo
~~~

Ý nghĩa:

- name=allocation: tên recording.
- settings=profile: dùng template profiling.
- duration=30s: ghi trong 30 giây.
- filename=allocation.jfr: file recording được tạo khi recording hoàn tất.

Có thể thêm delay=10s nếu muốn đợi ứng dụng khởi động và warm-up trước khi bắt đầu ghi:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,delay=10s,duration=30s,filename=allocation.jfr AllocationDemo
~~~

File .jfr là file nhị phân. Mở bằng JMC hoặc dùng công cụ jfr trong JDK để xem summary và event.

## 7. Bắt đầu recording cho JVM đang chạy

Nếu ứng dụng đã chạy, tìm PID:

~~~powershell
jcmd -l
~~~

Bắt đầu recording:

~~~powershell
jcmd <PID> JFR.start name=allocation settings=profile duration=30s filename=allocation.jfr
~~~

Kiểm tra recording:

~~~powershell
jcmd <PID> JFR.check
~~~

Nếu muốn ghi liên tục và chủ động dump file khi đã thu đủ dữ liệu:

~~~powershell
jcmd <PID> JFR.start name=allocation settings=profile
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=allocation filename=allocation.jfr
jcmd <PID> JFR.stop name=allocation
~~~

JFR.dump ghi dữ liệu hiện có ra file và recording vẫn tiếp tục chạy. JFR.stop dừng recording. Dùng đúng PID, chạy trên cùng máy và cùng effective user/group với tiến trình JVM đích.

Với production, chọn khoảng thời gian ghi phù hợp với workload cần quan sát. Không bật event chi tiết có overhead cao trong thời gian dài nếu chưa đánh giá tác động.

## 8. Mở recording trong JDK Mission Control

JDK Mission Control (JMC) là công cụ riêng để xem và phân tích file .jfr; nó không nhất thiết được cài cùng mọi bản JDK.

Quy trình:

1. Mở JMC.
2. Chọn File → Open File... và chọn allocation.jfr.
3. Mở recording trong Flight Recorder.
4. Xem Automated Analysis Results để tìm cảnh báo và khu vực cần điều tra.
5. Mở trang TLAB Allocations hoặc trang Allocation tương ứng với phiên bản JMC.
6. Chọn khoảng thời gian có workload cần phân tích.
7. So sánh allocation theo class, thread và stack trace.

Trang TLAB Allocations trong JMC có thể cung cấp các góc nhìn:

- **Allocation by Class:** class nào tạo nhiều allocation nhất.
- **Allocation by Thread:** thread nào tạo nhiều allocation nhất.
- **Allocation Profile:** cây stack trace tổng hợp các vị trí cấp phát.
- **By Top Methods:** một số phiên bản JMC có thêm góc nhìn theo method.

Tên tab và cách bố trí có thể khác theo phiên bản JMC. Nếu không thấy trang Allocation/TLAB Allocations, kiểm tra recording có chứa event allocation và JMC có hỗ trợ event đó hay không.

## 9. Đọc Allocation by Class

Bắt đầu với danh sách class được sắp theo lượng allocation. Tìm class có tổng byte ước lượng lớn hoặc tỷ trọng cao trong recording.

Ví dụ minh họa:

| Class | Allocation ước lượng | Diễn giải ban đầu |
|---|---:|---|
| byte[] | 420 MB | Buffer hoặc payload được tạo nhiều |
| java.lang.String | 180 MB | Ghép chuỗi, parse, format hoặc tạo key |
| char[] | 95 MB | Xử lý text hoặc chuyển đổi dữ liệu |
| java.util.HashMap$Node | 72 MB | Entry mới khi map tăng hoặc được tạo liên tục |
| com.example.OrderDto | 48 MB | DTO được tạo trong luồng xử lý order |

Đây là dữ liệu giả định để minh họa cách đọc. Một class đứng đầu không tự động là lỗi. byte[] có thể chiếm nhiều byte vì buffer lớn; String có thể chiếm nhiều allocation vì ứng dụng xử lý nhiều text.

Sau khi chọn class:

1. Xem stack trace để tìm method tạo object.
2. Xác định component hoặc request path gọi method đó.
3. Xem allocation có xảy ra trong startup, batch hay request bình thường.
4. Đối chiếu số byte với số lượng request và thời gian recording.
5. Kiểm tra object có được giữ lại hay chỉ tồn tại ngắn hạn.

Nếu nhiều class có chung stack trace, nguyên nhân có thể nằm ở một method tạo object trung gian cho nhiều loại dữ liệu.

## 10. Đọc Allocation by Thread

Góc nhìn theo thread giúp xác định nhóm công việc tạo nhiều allocation nhất.

Ví dụ:

- http-nio-8080-exec-* có thể là thread xử lý HTTP request.
- pool-2-thread-* có thể là worker của executor.
- scheduler-* có thể là thread chạy tác vụ định kỳ.
- kafka-consumer-* có thể là thread nhận và xử lý message.
- batch-worker-* có thể là worker của tác vụ batch.

Nếu một thread tạo nhiều allocation, hãy kiểm tra lượng công việc thread đó thực hiện. Không so sánh hai thread chỉ bằng tổng byte nếu một thread xử lý gấp nhiều lần số request.

Cách phân tích:

1. Chọn thread có allocation cao.
2. Mở stack profile của thread.
3. Tìm method ứng dụng đứng đầu các nhánh allocation.
4. Đối chiếu với request rate, batch size hoặc số message.
5. So sánh allocation trên mỗi đơn vị công việc, chẳng hạn byte/request hoặc byte/message.

Nếu tất cả worker cùng có allocation cao tại một method, vấn đề có thể nằm trong logic chung. Nếu chỉ một thread nổi bật, kiểm tra workload lệch, dữ liệu đầu vào lớn hoặc một job đặc biệt.

## 11. Đọc Allocation Profile và stack trace

Allocation Profile tổng hợp các event theo cây call stack. Đây thường là nơi hữu ích nhất để lần từ class được tạo về method yêu cầu cấp phát.

Ví dụ minh họa:

~~~text
com.example.OrderController.submit()
  com.example.OrderService.createOrder()
    com.example.OrderMapper.toDto()
      java.util.ArrayList.<init>()
      java.lang.StringBuilder.<init>()
      java.lang.String.substring()
~~~

Cây này gợi ý OrderMapper.toDto() đang tạo list và chuỗi trung gian. Hãy mở source code để kiểm tra số lần method được gọi, kích thước collection và cách chuyển đổi text.

Đọc stack trace từ method cấp phát lên các caller:

- Frame gần allocation cho biết API/class tạo object.
- Frame tiếp theo chỉ ra method ứng dụng gọi API đó.
- Các frame cao hơn cho biết request, batch hoặc message flow dẫn tới allocation.

Một class có thể được tạo từ nhiều stack trace. Hãy xử lý từng nguồn cấp phát theo tỷ trọng và tác động thực tế, không chỉ sửa class có tổng số byte lớn nhất.

## 12. Hiểu weight và ước lượng allocation rate

Với jdk.ObjectAllocationSample, weight là lượng byte ước lượng mà sample đại diện. Khi tổng hợp các sample trong recording, có thể ước lượng allocation pressure theo class, thread hoặc stack trace.

Công thức đơn giản:

\[
\text{Allocation rate} \approx
\frac{\text{Tổng sample weight (bytes)}}{\text{Thời gian recording (seconds)}}
\]

Ví dụ: nếu tổng weight của một stack trace là 600 MiB trong 60 giây:

\[
600 \div 60 = 10\ \text{MiB/s}
\]

Đây là allocation rate ước lượng cho stack trace đó trong khoảng quan sát. Khi dùng dữ liệu sample, không coi kết quả là phép đếm chính xác từng object.

Nên xem đồng thời:

- Tổng byte allocation.
- Số sample/event.
- Class và stack trace.
- Thread tạo allocation.
- Khoảng thời gian recording.
- Workload trong cùng khoảng thời gian.

Không dùng số event để tính object count nếu event là sampling event. Không so sánh hai recording có template, thời lượng hoặc workload khác nhau mà không ghi rõ các khác biệt.

## 13. Dùng jfr để đọc allocation event từ terminal

Trước tiên xem tổng quan recording:

~~~powershell
jfr summary allocation.jfr
~~~

Lọc event allocation sample:

~~~powershell
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr
~~~

Lọc các event TLAB:

~~~powershell
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB --stack-depth 12 allocation.jfr
~~~

Xem metadata và field của event:

~~~powershell
jfr metadata allocation.jfr
~~~

Có thể redirect output ra file để tìm class, thread hoặc stack trace:

~~~powershell
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr > allocation-events.txt
~~~

jfr summary cho biết recording có những event nào và số lượng event đã ghi. jfr print hiển thị event chi tiết; --events giúp lọc và --stack-depth điều chỉnh độ sâu stack trace.

Nếu không có jdk.ObjectAllocationSample trong summary, hãy kiểm tra template, event settings và JDK version. Recording không chứa event thì jfr print không thể khôi phục allocation đã không được ghi.

## 14. Ví dụ thực hành: tạo allocation workload

Tạo file AllocationDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class AllocationDemo {
    private static volatile byte[] lastPayload;
    private static volatile String lastLabel;
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 1_000_000; i++) {
            byte[] payload = new byte[256 + (i & 2047)];
            payload[0] = (byte) i;
            lastPayload = payload;

            String label = "order-" + i + "-" + (i % 17);
            lastLabel = label;

            if (i % 5_000 == 0) {
                RETAINED.add(new byte[16 * 1024]);
            }
        }

        System.out.println("Allocation workload finished.");
        System.out.println("Retained arrays: " + RETAINED.size());

        // Giữ JVM sống để recording hoàn tất.
        Thread.sleep(35_000);
    }
}
~~~

Chương trình cố ý tạo nhiều array và String tạm thời. Các biến volatile giữ tham chiếu cuối cùng để allocation có thể quan sát được; danh sách RETAINED giữ lại một số array để minh họa object còn sống.

Biên dịch:

~~~powershell
javac AllocationDemo.java
~~~

Chạy và ghi JFR trong 30 giây:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,duration=30s,filename=allocation.jfr AllocationDemo
~~~

Stdout do chương trình in:

~~~text
Allocation workload finished.
Retained arrays: 200
~~~

JFR có thể in thêm thông báo lúc khởi tạo recording tùy JDK. Hai dòng trên là output của ứng dụng sau workload; số event và sample weight trong recording phụ thuộc runtime.

Sau khi file được tạo:

~~~powershell
jfr summary allocation.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr
~~~

Mở allocation.jfr trong JMC và so sánh class byte[], java.lang.String, thread main và stack trace của AllocationDemo.main().

Ví dụ này tạo cả object ngắn hạn lẫn object được giữ lại. Vì vậy, khi đọc recording, hãy phân biệt allocation pressure của vòng lặp với khoảng 200 array được giữ trong danh sách.

## 15. Từ allocation hotspot đến cải thiện code

Sau khi tìm được method cấp phát nhiều, cần xác định vì sao nó tạo object và liệu có thể giảm allocation mà vẫn giữ đúng hành vi.

### 15.1. Giảm object trung gian

Kiểm tra các bước chuyển đổi dữ liệu tạo collection, wrapper, DTO hoặc object tạm thời không cần thiết. Nếu nhiều bước tạo bản sao của cùng dữ liệu, cân nhắc truyền dữ liệu theo dạng phù hợp hơn hoặc giảm số lần chuyển đổi.

### 15.2. Kiểm soát String allocation

Các thao tác nối chuỗi, format, parse và tạo key trong vòng lặp có thể tạo nhiều String và backing array. Kiểm tra stack trace để biết allocation xuất phát từ đâu.

Dùng StringBuilder khi cần xây dựng chuỗi trong nhiều bước. Tránh tạo chuỗi trung gian nếu API có thể nhận dữ liệu dạng buffer hoặc stream. Không thay mọi phép nối chuỗi bằng StringBuilder một cách máy móc; compiler có thể tối ưu một số phép nối đơn giản.

### 15.3. Đặt capacity collection hợp lý

Nếu biết trước kích thước gần đúng, khởi tạo ArrayList hoặc HashMap với capacity phù hợp có thể giảm việc mở rộng và tạo array backing mới.

Không đặt capacity quá lớn cho mọi collection. Cân bằng giữa số lần resize và lượng bộ nhớ bị giữ không cần thiết.

### 15.4. Giảm copy buffer

Nếu stack trace cho thấy nhiều byte[] hoặc char[], tìm các bước copy, encode/decode, serialization hoặc buffering lặp lại. Có thể giảm số lần copy, xử lý theo chunk hoặc tái sử dụng buffer có vòng đời rõ ràng.

Tái sử dụng buffer cần chú ý thread safety, dữ liệu cũ và việc giữ buffer quá lớn sau khi tải giảm. Không dùng object pool chỉ vì allocation profile có nhiều object nhỏ; pool có thể tăng retention, đồng bộ và độ phức tạp.

### 15.5. Đánh giá theo workload thật

Sau khi sửa:

1. Chạy cùng workload và cùng thời lượng.
2. Dùng cùng JDK, GC và recording template.
3. So sánh allocation rate, class/stack hotspot và GC activity.
4. Kiểm tra throughput và latency.
5. Kiểm tra heap sau GC để đảm bảo retention không tăng.

Một thay đổi làm giảm allocation nhưng tăng CPU hoặc latency có thể không phải cải thiện tổng thể.

## 16. Phân biệt allocation pressure, GC pressure và memory leak

| Dấu hiệu | Khả năng | Bằng chứng cần xem |
|---|---|---|
| Allocation rate cao, heap sau GC ổn định | Nhiều object tạm thời được tạo rồi thu hồi | Allocation Profile, GC frequency và pause |
| Allocation rate cao, GC chạy thường xuyên | Allocation pressure gây thêm công việc GC | Allocation rate cùng GC event/pause |
| Heap sau GC tăng qua nhiều chu kỳ | Object sống lâu hoặc retention tăng | Heap dump, old-object sample, GC roots |
| Một class chiếm allocation lớn nhưng không còn sống sau GC | Object tạm thời, không nhất thiết là leak | Allocation stack và live set |
| Một loader/cache/collection giữ object tăng dần | Có thể có retention hoặc leak | Heap dump và đường tham chiếu |

JFR allocation sample không chứng minh memory leak. Để tìm object tồn tại lâu, dùng JFR jdk.OldObjectSample nếu recording được cấu hình phù hợp, hoặc lấy heap dump rồi phân tích đường tham chiếu từ GC roots.

Trong JDK 17, JFR có thể ghi thêm thông tin về old object và đường dẫn GC roots. Thu thập path-to-GC-roots có thể làm ứng dụng pause trong một khoảng thời gian; chỉ bật khi nghi ngờ leak và đã cân nhắc tác động.

## 17. Lỗi thường gặp khi phân tích Allocation

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy TLAB Allocations trong JMC | Recording không bật event allocation hoặc JMC không hỗ trợ event | Kiểm tra jfr summary, event settings và phiên bản JMC |
| Không có jdk.ObjectAllocationSample | Template tùy chỉnh hoặc event bị tắt | Tạo recording dùng template phù hợp hoặc bật event trong bản sao template |
| Sample weight nhỏ hoặc số sample ít | Workload ngắn, allocation thấp hoặc sampling không đủ | Ghi lâu hơn trong workload đại diện và xem lại event settings |
| Stack trace không đầy đủ | Stack trace bị tắt hoặc độ sâu quá ngắn | Bật stack trace cho event và tăng stack depth khi cần |
| Allocation by Class khác số byte heap | Allocation là tổng cấp phát theo thời gian, heap là trạng thái đang giữ | So sánh với GC và live set, không dùng hai số thay thế nhau |
| Nhiều event TLAB nhưng không biết số object | Event TLAB không ghi từng object trong TLAB | Dùng ObjectAllocationSample và hiểu weight |
| Recording quá lớn | Bật quá nhiều event hoặc dùng template profiling quá lâu | Giảm thời lượng, chọn event cần thiết, dùng default cho continuous |
| Kết quả hai recording khác nhau | Workload, thời lượng, template hoặc JDK khác nhau | Chuẩn hóa điều kiện đo và so sánh allocation rate |
| Không tìm thấy method ứng dụng | Stack bị cắt hoặc allocation xảy ra trong thư viện | Tăng stack depth và lần ngược caller trong profile |

## 18. Overhead và bảo vệ recording

JFR được thiết kế cho profiling và chẩn đoán runtime với overhead thấp, nhưng overhead thực tế phụ thuộc ứng dụng, event settings, thời lượng và lượng dữ liệu ghi. Template profile thu thập nhiều dữ liệu hơn và có thể tạo overhead/dung lượng file lớn hơn default.

Các lưu ý:

- Bắt đầu bằng recording ngắn và workload đại diện.
- Chỉ bật event chi tiết khi sample không đủ để tìm hotspot.
- Không ghi quá nhiều event trong thời gian dài nếu chưa đánh giá overhead.
- Theo dõi kích thước file và giới hạn tuổi/dung lượng recording liên tục.
- Không bật Heap Statistics chỉ để tìm allocation hotspot; tính năng này có thể kích hoạt old GC và làm thay đổi pause.
- Ghi lại JDK, GC, template, thời lượng và workload cùng file recording.

File .jfr có thể chứa tên class, package, method, stack trace, thread name, đường dẫn và dữ liệu từ custom event. Giới hạn quyền truy cập file, không đăng recording công khai khi chưa rà soát, và redact hoặc tạo bản chia sẻ đã xử lý nếu cần.

## 19. Quy trình phân tích Allocation trong một sự cố

1. Xác định triệu chứng: GC thường xuyên, CPU tăng, latency cao hay heap tăng.
2. Chọn workload và khoảng thời gian có triệu chứng.
3. Tạo JFR recording với profile trong thời gian giới hạn.
4. Kiểm tra jfr summary để xác nhận event allocation đã được ghi.
5. Mở file trong JMC và xem TLAB Allocations/Allocation Profile.
6. Xếp hạng theo class, thread và stack trace.
7. Tính allocation rate ước lượng bằng sample weight chia cho thời lượng.
8. Mở source code tại method đứng đầu và xác định object trung gian.
9. Đối chiếu GC pause và heap sau GC để phân biệt temporary allocation với retention.
10. Thực hiện thay đổi nhỏ, đo lại trên cùng workload và so sánh kết quả.

## 20. Checklist đọc Allocation

- [ ] Đã chọn đúng JVM, JDK và khoảng thời gian có workload.
- [ ] Recording có event allocation cần phân tích.
- [ ] Đã hiểu jdk.ObjectAllocationSample là sampling event và weight là byte ước lượng.
- [ ] Không dùng số sample làm số object chính xác.
- [ ] Đã phân biệt allocation trong TLAB và ngoài TLAB.
- [ ] Không xem event cấp TLAB mới là mọi object được tạo trong TLAB.
- [ ] Đã xem Allocation by Class, Allocation by Thread và Allocation Profile.
- [ ] Đã tìm stack trace đầu tiên thuộc code ứng dụng.
- [ ] Đã xem allocation rate theo thời gian và workload.
- [ ] Đã phân biệt allocated bytes với heap đang giữ và object sống sau GC.
- [ ] Đã đối chiếu GC activity và heap/live set khi cần.
- [ ] Đã đo lại bằng cùng workload/template sau khi tối ưu.
- [ ] Đã bảo vệ và redact file .jfr trước khi chia sẻ.

Allocation analysis bằng JFR giúp tìm class, thread và stack trace tạo ra nhiều object nhất. Hãy dùng jdk.ObjectAllocationSample để ước lượng allocation pressure, event TLAB để hiểu đường cấp phát và JMC để lần từ class về method. Sau đó đối chiếu với GC và live heap: giảm allocation có thể giảm GC pressure, còn memory leak cần bằng chứng object vẫn được giữ sau collection.

## Tài liệu tham khảo

- Oracle, Java SE 17 Troubleshooting Guide — Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — The jfr Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle, Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle, Java SE 17 — Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle, JDK Mission Control 9 User Guide — Flight Recorder: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html
- Oracle, JDK 16 Release Notes — New jdk.ObjectAllocationSample Event Enabled by Default: https://www.oracle.com/java/technologies/javase/16-relnote-issues.html
