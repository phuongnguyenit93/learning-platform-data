# 14.5 Chọn default.jfc, profile.jfc hoặc cấu hình sự kiện riêng theo câu hỏi

## Mục tiêu học tập

**Java Flight Recorder (JFR)** là công cụ ghi sự kiện có dấu thời gian của JVM và ứng dụng Java. Chọn cấu hình ghi đúng sẽ quyết định bạn có dữ liệu để trả lời câu hỏi chẩn đoán hay không, đồng thời ảnh hưởng đến CPU, kích thước tệp và mức độ can thiệp vào hệ thống.

Bài này tập trung vào ba lựa chọn: **`default.jfc`**, **`profile.jfc`** và **cấu hình `.jfc` tự tạo**, trong bối cảnh thu bản ghi JFR trên HotSpot JDK 17 trở lên. Sau bài này, bạn có thể:

- Ghép **câu hỏi cần giải đáp** với nhóm sự kiện và mức thu thập hợp lý, thay vì bật hết các sự kiện.
- Giải thích vì sao `default.jfc` thường thích hợp cho quan sát dài hạn, `profile.jfc` thích hợp cho một cửa sổ profiling có giới hạn, và khi nào cần tạo `.jfc` riêng.
- Điều chỉnh các event settings như `enabled`, `threshold`, `period`, `stackTrace` mà vẫn kiểm soát chi phí đo.
- Tạo cấu hình bằng `jfr configure` hoặc JDK Mission Control (JMC), chạy bằng `-XX:StartFlightRecording` hay `jcmd JFR.start`, rồi kiểm tra tệp `.jfr`.
- Tránh những kết luận sai khi event không xuất hiện, có quá ít mẫu, hoặc cấu hình đo làm thay đổi đặc điểm ứng dụng.

> Không có template nào luôn đúng cho mọi ứng dụng. **Câu hỏi, thời gian cần quan sát, tần suất sự kiện, workload và ngân sách overhead** quyết định lựa chọn. Các event được bật theo preset và các tùy chọn hỗ trợ có thể khác nhau giữa các bản JDK; hãy xác minh phiên bản đang chạy.

## 1. Hai loại tệp khác nhau: `.jfc` và `.jfr`

- **`.jfc` (JFR Configuration)**: tệp cấu hình dạng XML mô tả event nào được thu, threshold/period/stack trace và một số điều khiển (controls) do template hỗ trợ. JDK thường cung cấp `default.jfc` và `profile.jfc` tại `<JAVA_HOME>/lib/jfr/`.
- **`.jfr` (Flight Recording)**: tệp bản ghi nhị phân do JFR tạo ra, chứa sự kiện thực tế, metadata và những thông tin cần để phân tích. Dùng `jfr summary`, `jfr print`, hoặc mở trong **Java Mission Control**.

Đường đi tư duy:

~~~text
Câu hỏi chẩn đoán
       |
       v
Chọn sự kiện + mức lấy mẫu + threshold + thời lượng
       |
       v
Chọn default.jfc / profile.jfc / custom.jfc
       |
       v
Khởi chạy JFR -> ghi file .jfr -> xác minh event -> phân tích
       |
       v
Kết luận có bằng chứng hoặc chỉnh cấu hình và đo lại
~~~

`settings=default` và `settings=profile` trong một số lệnh JFR là tên rút gọn cho preset đi kèm JDK. Với template tự tạo, sử dụng đường dẫn `settings=locks.jfc` hoặc đường dẫn tuyệt đối tới tệp mà **JVM đích** truy cập được. Đừng nhầm tên cấu hình với tên recording.

## 2. Quy tắc quyết định nhanh

| Tình huống/câu hỏi | Bắt đầu bằng | Vì sao | Dấu hiệu cần đổi cấu hình |
| --- | --- | --- | --- |
| Muốn giữ lịch sử để xem một sự cố hiếm xảy ra | `default.jfc`, recording liên tục với giới hạn dung lượng/tuổi dữ liệu | Chi phí thấp, có thông tin chung về JVM, GC, luồng, hệ thống | Không có đủ event hoặc stack để biết nguyên nhân |
| CPU cao, cần biết phương thức nào dùng thời gian CPU | `profile.jfc` trong cửa sổ đo đủ dài | Thông tin profiling/sampling phong phú hơn | Sample quá ít, không có stack hữu ích hoặc overhead quá lớn |
| Nghi tạo nhiều đối tượng tạm, cần tìm allocation hot spots | `profile.jfc` rồi kiểm tra allocation events | Có thêm dữ liệu phục vụ profiling | Sampling chưa đủ độ phân giải; cần bật/tinh chỉnh event cụ thể |
| Độ trễ lớn do chờ monitor/park | `default.jfc` để quan sát rộng, sau đó `custom.jfc` hạ threshold sự kiện liên quan | Chỉ thu thêm những lần chờ cần quan tâm | Threshold mặc định bỏ lỡ các chờ 5–20 ms |
| Một luồng chờ I/O tệp/socket quá lâu | `default.jfc` hoặc custom cho `jdk.FileRead`, `jdk.SocketRead`… | Phân biệt thời gian I/O với thời gian CPU | Event I/O bị tắt hoặc threshold quá cao |
| Điều tra exception phát sinh dày đặc | Custom **ngắn hạn**, giới hạn event exception phù hợp | Event cho *mỗi exception* có thể nhiều và đắt | File lớn, CPU tăng, stack không đủ thông tin |
| Cần footprint/GC cơ bản trong thời gian dài | `default.jfc` | Phù hợp điều tra xu hướng tổng thể | Thiếu sự kiện GC pha chi tiết hoặc các dữ liệu allocation cụ thể |

Các dòng trên là **điểm khởi đầu**, không bảo đảm mọi event đều được bật sẵn. Luôn mở preset của đúng JDK hoặc kiểm tra cấu hình hiệu lực; không suy luận rằng “profile” đồng nghĩa đã thu mọi allocation hay mọi Java method invocation.

### Ba điều cần ghi trước khi nhấn Start

1. **Câu hỏi có thể kiểm chứng:** “p99 tăng vì các thread chờ monitor `PaymentCache` hơn 10 ms” tốt hơn “ứng dụng bị chậm”.
2. **Khoảng thời gian và tải:** Có cần 10 phút lịch sử trước lỗi, hay đúng 60 giây tái hiện lỗi? Ghi RPS, concurrency, dữ liệu đầu vào và lúc xảy ra triệu chứng.
3. **Ngân sách chi phí đo:** CPU, file size, I/O, latency và retention của recording. Nếu hệ thống đang sát ngưỡng, một template giàu event có thể ảnh hưởng chính điều đang đo.

## 3. `default.jfc` — nền quan sát với overhead thấp

`default.jfc` thường được thiết kế để thu nhiều chỉ số và sự kiện có ích ở **mức overhead thấp**, phù hợp ghi dài hạn hoặc bật sẵn trong quá trình quan sát ứng dụng. Theo hướng dẫn Oracle, đây là lựa chọn mặc định cho continuous recording; overhead thường thấp (tham khảo mức dưới 1% trong cấu hình/điều kiện đã đo), **không phải cam kết cho mọi hệ thống**.

Dùng `default` khi muốn có timeline GC, diễn biến các luồng, CPU load và nhiều sự kiện JVM thông thường, đồng thời chưa biết nguyên nhân cụ thể. Một số event có threshold hoặc period nên các thao tác quá ngắn không được ghi. Một số event chi tiết (chẳng hạn các loại allocation có thể rất nhiều) có thể bị giảm hoặc tắt để giữ chi phí.

### 3.1 Thu liên tục cho tiến trình đang chạy

~~~sh
# Tìm PID của đúng JVM (cùng user/namespace có quyền attach):
jcmd -l

# Bắt đầu ghi liên tục; giới hạn kích thước và tuổi giữ dữ liệu.
jcmd <pid> JFR.start name=baseline settings=default disk=true maxage=1h maxsize=256m

# Kiểm tra recording còn hoạt động:
jcmd <pid> JFR.check

# Khi xảy ra sự cố, lấy 15 phút gần nhất (nếu đủ dữ liệu):
jcmd <pid> JFR.dump name=baseline filename=baseline-on-incident.jfr maxage=15m

# Dừng khi không cần thu tiếp:
jcmd <pid> JFR.stop name=baseline
~~~

Các giới hạn `maxage`, `maxsize` giữ lượng dữ liệu trong recording có giới hạn; bản dump chỉ chứa dữ liệu còn tồn tại trong vùng retention. **Chúng không bảo đảm có đủ 15 phút** nếu sự kiện quá nhiều và dữ liệu cũ đã bị loại trước. Tệp dump do JVM đích ghi: với container/remote JVM, `filename` là đường dẫn trong môi trường của JVM, không tự động xuất hiện trên máy gọi `jcmd`.

Đối với ứng dụng khởi động và dừng ngắn hạn, có thể bật ghi ngay khi tạo JVM:

~~~sh
java -XX:StartFlightRecording=settings=default,filename=startup.jfr,dumponexit=true -jar app.jar
~~~

Lưu ý rằng việc có `dumponexit=true` yêu cầu JVM thoát để hoàn tất bản dump ở ví dụ này; với server chạy dài, dùng `jcmd JFR.dump` khi cần snapshot mà không dừng ứng dụng.

### 3.2 Khi nào default là chưa đủ?

Ví dụ, ứng dụng có p99 tăng do rất nhiều lượt chờ lock **khoảng 5–15 ms**, nhưng template hiện tại đặt `jdk.JavaMonitorEnter#threshold=20ms`. Không thấy sự kiện lock 5–15 ms là điều hoàn toàn có thể xảy ra; kết luận “không có lock contention” sẽ sai. Hãy hạ đúng threshold trong **cửa sổ đo có kiểm soát**, thu lại và xem thay đổi số event/overhead.

## 4. `profile.jfc` — chi tiết hơn trong cửa sổ ngắn

`profile.jfc` thường bật hoặc tăng tần suất các dữ liệu phục vụ profiling như sampling thực thi và allocation, đổi lại chi phí và lưu lượng bản ghi cao hơn `default`. Nó thích hợp cho điều tra CPU hot spots, allocation hot spots và một số bottleneck khi đã có cửa sổ tái hiện rõ ràng.

~~~sh
# Profiling trong 60 giây rồi ghi ra file:
jcmd <pid> JFR.start name=cpu-investigation settings=profile duration=60s filename=cpu-profile.jfr
~~~

Sau khi đủ thời lượng, kiểm tra tệp và event thực tế:

~~~sh
jfr summary cpu-profile.jfr
jfr print --events jdk.ExecutionSample --stack-depth 20 cpu-profile.jfr
~~~

**Không** đọc số `jdk.ExecutionSample` như “số lần method thực thi”, “CPU percent” hay một call graph đầy đủ. Đây là **mẫu**, không phải trace cho từng invocation. Ít sample có thể phản ánh thời gian đo ngắn, số thread không chạy CPU thường xuyên, period quá lớn hoặc sampling chưa bật; phần phân tích phải bám sự kiện thật và bối cảnh.

Đối với allocation, hãy kiểm tra `jdk.ObjectAllocationSample`. Event này lấy mẫu và thường có trọng số ước tính; đếm event thô không bằng tổng số đối tượng/byte được cấp phát. Với bài toán nhỏ, dùng JMH `-prof gc` hoặc profiler allocation phù hợp để đối chiếu B/op.

### 4.1 Đo đúng cửa sổ

- Chụp lúc ứng dụng đang **chịu tải gây ra vấn đề**, không chỉ khi idle.
- Ghi đủ dài để mẫu có ý nghĩa; một recording vài mili-giây có thể không có event bạn cần.
- Tránh đem profile và default từ **hai workload khác nhau** ra kết luận cách tối ưu/GC đã thay đổi.
- Dùng cùng JDK/collector/config khi cần so A/B, đồng thời ghi lại event settings; tên `profile` không bảo đảm template không thay đổi giữa các bản JDK.

## 5. Custom `.jfc` — chỉ thu những gì trả lời được câu hỏi

Custom phù hợp khi cả hai preset đều không đúng nhu cầu: cần một event bị tắt, một ngưỡng khác, chu kỳ sampling khác, thêm stack trace hoặc cắt bớt một nhóm event quá ồn. **Đừng mặc định rằng bật nhiều event hơn cho ra chẩn đoán tốt hơn**: hàng triệu event không liên quan có thể gây áp lực file/I/O và làm mờ tín hiệu.

### 5.1 Bốn settings nền tảng

| Setting | Ví dụ | Ý nghĩa và trade-off |
| --- | --- | --- |
| `enabled` | `jdk.JavaMonitorEnter#enabled=true` | Cho phép event được ghi nếu điều kiện phát sinh thỏa; tắt event để giảm dữ liệu |
| `threshold` | `jdk.JavaMonitorEnter#threshold=5ms` | Chỉ ghi sự kiện duration **đạt/vượt** ngưỡng; hạ threshold làm tăng số event và dữ liệu |
| `period` | `jdk.ExecutionSample#period=20ms` | Với event định kỳ/sampling hỗ trợ period, khoảng lấy mẫu; period ngắn hơn tăng độ phân giải và chi phí |
| `stackTrace` | `jdk.JavaMonitorEnter#stackTrace=true` | Thu call stack nếu event hỗ trợ; giúp xác định call site nhưng thêm dữ liệu/chi phí |

Một số event có setting riêng như sampling throttle; **không phải event nào cũng hỗ trợ mọi setting**. `threshold` chỉ có nghĩa với event kiểu duration phù hợp; nó không phải “ngưỡng số lần/giây”. `period` của sampling không bảo đảm mỗi thread được lấy đúng một mẫu mỗi 20 ms. Chỉ dùng setting được event hỗ trợ và kiểm tra template đầu ra.

Trong tệp `.jfc`, mỗi event có tên đầy đủ và tập `<setting name="...">...`. Template cũng có thể có control hỗ trợ các preset. Sửa event setting trong JFR là cấu hình **recording**, không thay đổi logic lock, GC hay tốc độ thực thi của chương trình ngoài overhead của công cụ đo.

### 5.2 Tạo template theo câu hỏi về lock contention

Giả thiết: p99 tăng và cần tìm các lượt chờ monitor ít nhất 5 ms cùng vị trí gọi Java. Với `jfr configure` của JDK hỗ trợ (JDK 17+ có thể kiểm tra bằng `jfr help configure`), tạo template mới **dựa trên default**:

~~~sh
jfr configure --input default.jfc --output locks.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms' 'jdk.JavaMonitorEnter#stackTrace=true'
~~~

Lệnh giữ nguyên các setting còn lại của `default.jfc` rồi thay ba setting của event đã nêu, không sửa template mặc định. Trên một JDK, các biểu thức event setting có dạng `<event-name>#<setting-name>=<value>`; shell cần quote biểu thức có `#` khi môi trường yêu cầu. Kiểm tra:

~~~sh
jfr help configure
~~~

Có thể mở `locks.jfc` để xem event `jdk.JavaMonitorEnter` thật sự có `enabled=true`, `threshold=5 ms` và `stackTrace=true`. **Không giả định file tạo thành công chỉ vì câu lệnh không báo lỗi** nếu đang dùng một phiên bản JDK khác hoặc event đã đổi tên.

Bắt đầu recording với custom template:

~~~sh
# Trong cùng thư mục có locks.jfc, hoặc dùng đường dẫn đầy đủ tới .jfc:
jcmd <pid> JFR.start name=lock-study settings=locks.jfc duration=60s filename=locks.jfr

# Sau 60 giây:
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter --stack-depth 30 locks.jfr
~~~

Ví dụ này thu thêm các lượt monitor contention có duration từ khoảng 5 ms; nếu workload có hàng nghìn lượt chờ/giây, file và overhead có thể tăng mạnh. Khi nhiều sự kiện quá, chọn threshold cao hơn hoặc khoảng đo ngắn hơn. Tập trung vào **duration, monitorClass, thread, previousOwner, stackTrace và mốc thời gian**, không kết luận từ count đơn lẻ.

### 5.3 Custom để tìm allocation hot spots

Khi profile hiện tại không cho đủ mẫu allocation, bạn có thể tùy chỉnh event lấy mẫu (nếu được hỗ trợ trên JDK đích):

~~~sh
jfr configure --input profile.jfc --output allocations.jfc 'jdk.ObjectAllocationSample#enabled=true' 'jdk.ObjectAllocationSample#stackTrace=true'
jcmd <pid> JFR.start name=alloc-study settings=allocations.jfc duration=90s filename=allocations.jfr
~~~

Đọc:

~~~sh
jfr summary allocations.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 30 allocations.jfr
~~~

Event `jdk.ObjectAllocationSample` chỉ lấy mẫu; phần mềm phân tích có thể dựa vào trọng số mẫu và event metadata để ước lượng byte theo stack. Nếu cần số byte trên từng đơn vị công việc, kết hợp benchmark JMH hoặc các số liệu allocation khác. Những event mức TLAB (`jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB`) có đặc điểm thu thập và chi phí riêng, không nên bật hàng loạt cho recording dài mà chưa đánh giá tác động.

### 5.4 Custom cho I/O hoặc exception

Với độ trễ socket/file, có thể lựa chọn `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` và đặt `threshold`/`stackTrace` ở ngưỡng phù hợp. Phải phân biệt **thread đang chờ I/O** với CPU nóng; CPU sampler không giải thích hết thời gian chờ.

Với exception dày đặc, `jdk.JavaExceptionThrow` có thể ghi nhiều event và stack, gây overhead đáng kể. Thử bằng cửa sổ ngắn, xác định loại exception, cân nhắc lấy số tổng hợp trước, sau đó mới mở event chi tiết nếu có lý do. Đừng cấu hình threshold của lock cho event exception: mỗi event có các setting hợp lệ khác nhau.

Nếu điều tra GC, bắt đầu xem các sự kiện `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.GCHeapSummary`. Chỉ bật thêm các pha/vùng GC chi tiết khi timeline và pause hiện có không đủ trả lời câu hỏi. Không có một tập event chi tiết chung cho mọi collector và mọi JDK.

### 5.5 Cách tạo bằng Java Mission Control

Nếu cần UI để chọn template hoặc xem nhóm event:

1. Mở Java Mission Control (JMC) và tính năng quản lý JFR recording templates; tìm `default.jfc`/`profile.jfc` tương ứng JDK đang chạy.
2. **Sao chép** template gốc, sửa nhóm event, enabled/threshold/period/stack trace theo mục tiêu, rồi lưu thành tên `.jfc` riêng.
3. Đọc lại các setting đã sửa và giữ version của template cùng kết quả `.jfr` để có thể tái hiện thí nghiệm.

Tên menu JMC có thể thay đổi theo phiên bản. Để dễ review và tái sử dụng, có thể lưu `locks.jfc` có kiểm soát phiên bản trong dự án riêng; **không sửa trực tiếp** `default.jfc` hoặc `profile.jfc` trong thư mục JDK.

## 6. Thí nghiệm Java 17+ chạy được: thấy tác dụng của cấu hình lock

Chương trình dưới đây cố ý tạo một đoạn **monitor contention** được đồng bộ bằng `CountDownLatch`, rồi tạo đối tượng ngắn hạn. Mục tiêu là xem custom `locks.jfc` bắt được **event lock** và stack mà không dựa vào sự ngẫu nhiên của scheduler.

Lưu đúng tên **JfrSettingsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JfrSettingsDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch LOCK_HELD = new CountDownLatch(1);
    private static volatile byte[] last;

    public static void main(String[] args) throws Exception {
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                LOCK_HELD.countDown();
                try {
                    Thread.sleep(250);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "holder");

        holder.start();
        LOCK_HELD.await();
        synchronized (LOCK) {
            System.out.println("CONTENTION_FINISHED");
        }
        holder.join();

        for (int i = 0; i < 100_000; i++) {
            byte[] data = new byte[256];
            data[0] = (byte) i;
            last = data;
        }
        System.out.println("ALLOCATION_FINISHED");
        Thread.sleep(3_000);
        System.out.println("DONE");
    }
}
~~~

`CountDownLatch` bảo đảm thread `holder` đã lấy monitor trước khi main cố vào vùng synchronized. Trong lúc giữ lock, `holder` ngủ 250 ms, vì vậy thread main phải chờ monitor. Trường `volatile last` làm mảng thoát khỏi phạm vi local để tránh trường hợp JIT loại bỏ mọi allocation; điều đó không đồng nghĩa mọi mảng vẫn được giữ sống cho đến hết chương trình.

**Thao tác trên JDK hỗ trợ `jfr configure`:**

~~~sh
javac --release 17 JfrSettingsDemo.java
jfr configure --input default.jfc --output locks-demo.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms' 'jdk.JavaMonitorEnter#stackTrace=true'
java -XX:StartFlightRecording=settings=locks-demo.jfc,filename=locks-demo.jfr,dumponexit=true JfrSettingsDemo
jfr summary locks-demo.jfr
jfr print --events jdk.JavaMonitorEnter locks-demo.jfr
~~~

Stdout **do chương trình Java tự in** là:

~~~text
CONTENTION_FINISHED
ALLOCATION_FINISHED
DONE
~~~

JVM có thể in thêm các dòng `[info][jfr,startup]` khi khởi động recording. Một lần thực thi trên HotSpot JDK 24 đã ghi được event `jdk.JavaMonitorEnter` với duration khoảng 251 ms và stack tại `JfrSettingsDemo.main`; **con số thời gian, số lượng event và địa chỉ trong trace không cố định** theo máy/JVM. Tập trung xác minh trong file `.jfr` có event lock với thread main và stack đúng, đồng thời nhớ rằng các allocation samples nếu có cũng không phải full object trace.

Ví dụ này chạy trên JDK 17+ về mặt ngôn ngữ Java (đã kiểm tra với `javac --release 17`). Lệnh tạo custom template và kết quả JFR đã được kiểm tra trên JDK 24; nếu JDK của bạn không hỗ trợ `jfr configure` hoặc event khác tên, dùng JMC/cấu hình `.jfc` tương đương của JDK đó và kiểm tra danh sách event thực tế.

## 7. Xác minh recording **trước** khi phân tích

Một file `.jfr` đã tồn tại không chứng minh rằng dữ liệu cần thiết đã được ghi. Làm theo thứ tự sau:

~~~sh
# 1. Có dữ liệu, thời lượng và kích thước nào?
jfr summary locks-demo.jfr

# 2. Trong file có tên event/metadata nào?
jfr metadata locks-demo.jfr

# 3. Dữ liệu event mục tiêu có những gì?
jfr print --events jdk.JavaMonitorEnter --stack-depth 30 locks-demo.jfr

# 4. Kiểm tra các cài đặt thực tế được JFR ghi lại (khi có):
jfr print --events jdk.ActiveSetting locks-demo.jfr
~~~

`jfr summary` liệt kê số event được ghi trong file, không hiển thị trực tiếp toàn bộ cấu hình đã yêu cầu. `jdk.ActiveSetting` có thể giúp đối chiếu cấu hình hiệu lực tại thời điểm thu; dữ liệu này phụ thuộc recording thực tế. Xem chi tiết trong JMC để lọc timeline, group theo thread/stack/duration và đối chiếu các mốc latency.

**Nếu không thấy event cần tìm**, kiểm tra theo trật tự:

1. Có đúng tệp từ **đúng PID, đúng recording name, đúng cửa sổ thời gian** không? Tệp JFR có thể được ghi trong container chứ không phải host.
2. Event có được bật ở cấu hình hiệu lực không? Tên event có tồn tại trên JDK hiện tại không?
3. Mẫu thử có thực sự sinh ra tình huống đó chưa? Ví dụ `jdk.JavaMonitorEnter` chỉ ghi việc tranh chấp monitor; một thao tác vào monitor không bị tranh chấp không tạo event chờ tương ứng.
4. `threshold` quá cao, `period` quá thưa, recording quá ngắn hoặc sample chưa bắt trúng hay không?
5. Có quá nhiều event bị giới hạn bởi dung lượng/retention, hoặc bản dump chỉ giữ đoạn cuối không? Đối chiếu timestamp và điều kiện tải.

**Không có event trong file không đồng nghĩa sự kiện không từng xảy ra.** Đó chỉ là kết quả theo cấu hình, thời gian và điều kiện đo hiện có.

## 8. Hiểu sự đánh đổi của event settings

### 8.1 Threshold: độ nhạy so với số lượng sự kiện

Giả sử một dịch vụ mỗi giây có 10.000 lần chờ monitor với phân bố:

- 9.800 lần dưới 1 ms;
- 180 lần từ 1 đến dưới 5 ms;
- 19 lần từ 5 đến dưới 20 ms;
- 1 lần từ 20 ms trở lên.

Với `threshold=20ms`, có thể chỉ thấy **khoảng 1 event/s**; với `threshold=5ms`, có thể thấy **khoảng 20 event/s**; với `threshold=0ms`, file có thể ghi gần 10.000 event/s nếu không có giới hạn khác. Đây là tình huống giả định để minh họa; thời gian đo/collector/loại event khiến số thật khác. Việc giảm threshold không “tạo ra contention”, mà thay đổi phần contention bạn nhìn thấy và chi phí thu thập.

Đừng tự động chọn `threshold=0ms` với mọi event latency nếu nghi vấn chỉ liên quan các thao tác trên 10 ms.

### 8.2 Period: tốc độ lấy mẫu và khả năng nhận biết hot spot

Ví dụ `jdk.ExecutionSample#period=20ms` nhằm thu mẫu thường xuyên hơn `period=100ms` trong cùng điều kiện, nên có khả năng bắt được nhiều khung thực thi hơn nhưng cũng có thể tốn thêm overhead và dung lượng.

- **Sample stack nhiều** từ phương thức A gợi ý A xuất hiện thường xuyên trong thời gian được quan sát, cần diễn giải theo CPU state/chi phí sample tương ứng.
- **Không thấy phương thức B** không chứng minh B chưa từng chạy: B có thể quá ngắn, hiếm, bị inlining hoặc không được lấy mẫu đúng lúc.
- Không suy ra time spent từ số mẫu một cách tuyệt đối nếu cơ chế event, thời lượng hoặc bias lấy mẫu chưa được kiểm chứng.

Với vài nghìn mili-giây recording, số mẫu có thể ít hơn mong đợi. Hãy chọn period và duration sau khi xác định độ phân giải cần thiết, rồi xác minh trong file.

### 8.3 Stack trace: thông tin nguyên nhân đi kèm chi phí

`stackTrace=true` hỗ trợ trả lời “sự kiện xảy ra **ở đâu**?”, nhất là lock, I/O hoặc allocation. Nhưng sự kiện tần suất cao kèm stack có thể tăng kích thước tệp đáng kể. Nếu chỉ cần tần suất/độ trễ tổng quan, có thể giảm stack trace ở những event không cần call site.

### 8.4 Overhead có thể làm thay đổi vấn đề đang điều tra

Sampling, tracing exception, nhiều event ngắn và heap/object leak analysis có chi phí khác nhau. Một số chế độ thu thông tin đường tới GC roots hoặc heap statistics có thể gây pause đáng kể. Khi đo độ trễ rất nhỏ, luôn so overhead và chỉ số ứng dụng trong cùng workload. Dữ liệu thu được chính xác về mặt sự kiện vẫn có thể **không đại diện** nếu việc thu đã làm thay đổi workload, CPU contention hoặc tốc độ xử lý.

## 9. Quy trình chọn cấu hình thực tế theo vòng lặp

1. **Đặt câu hỏi:** “CPU user tăng?”, “thread chờ monitor bao lâu?”, “socket đọc chậm?”, “allocation B/op tăng?”, “GC pause gây p99?”.
2. **Chọn tín hiệu tối thiểu:** event name, field/stack cần có, metric hệ thống đối chiếu và mốc thời gian.
3. **Chọn baseline:** bắt đầu `default` nếu cần quan sát dài/rộng; `profile` nếu cần profiling trong cửa sổ hữu hạn; `custom` khi cần một event/threshold/period chưa có.
4. **Đặt ngân sách:** duration, maxsize/maxage, vị trí ghi file, giới hạn I/O và chi phí phù hợp. Với tình huống hiếm, giữ lịch sử bằng default; khi cần điều tra sâu, ghi một khoảng profile/custom riêng.
5. **Xác minh sớm:** kiểm tra `JFR.check` lúc recording chạy và `jfr summary`/`jfr metadata`/`jfr print` sau khi dump; đừng dành cả giờ đo rồi mới phát hiện event đang tắt.
6. **Phân tích theo câu hỏi ban đầu:** lọc event mục tiêu; đối chiếu timestamp với load/latency/GC/CPU, xem stack và duration. Viết giả thuyết có thể bác bỏ, không chỉ mô tả biểu đồ.
7. **Lặp một thay đổi mỗi lần:** nếu threshold cao, hạ đúng event; nếu sample ít, tăng duration hoặc chỉnh period; nếu overhead lớn, loại event không cần và tăng threshold. Ghi lại template phiên bản nào đã dùng để so được các lần đo.

### Ví dụ ba lần thu khác nhau cùng một sự cố

Một ứng dụng có request p99 tăng từ 200 lên 900 ms vài lần mỗi ngày:

- **Lần 1 — `default.jfc` liên tục:** giữ lịch sử 1 giờ, dump 15 phút quanh lần p99 tăng. Quan sát GC không có pause tương ứng nhưng có dấu hiệu nhiều thread đang chờ.
- **Lần 2 — `profile.jfc` 60 giây:** có CPU samples, nhưng phần lớn request đang chờ thay vì tiêu thụ CPU. Không nên kết luận phương thức có ít CPU samples là không liên quan.
- **Lần 3 — `locks.jfc` threshold 5 ms:** tìm được stack `OrderService.reserve()` liên tục chờ monitor do đoạn công việc tốn thời gian nằm trong synchronized. Sau khi thay đổi cách đồng bộ, p99 giảm trong tải so sánh; đó là bằng chứng mạnh hơn chỉ nhìn thấy nhiều lock events.

Tình huống trên là minh họa suy luận, không phải số liệu benchmark hay quy tắc bắt buộc ba lần đo. Khi cần, một lần recording custom đúng mục tiêu cũng có thể đủ.

## 10. Những sai lầm phổ biến

1. **“`default.jfc` nhẹ nên không có thông tin hữu ích.”** Sai: với câu hỏi timeline, GC/threads và sự cố hiếm, nó thường là bước đầu rất tốt.
2. **“`profile.jfc` thu được mọi hoạt động của Java.”** Sai: nhiều event vẫn lấy mẫu hoặc có threshold; template không phải full instruction/method trace.
3. **“Custom tốt nhất là bật toàn bộ event với `threshold=0`.”** Sai: có thể tăng mạnh overhead và làm méo kết quả.
4. **“Hai tệp đều dùng `profile` nên so event count trực tiếp được.”** Sai: JDK version, duration, tải, cấu hình thực tế và retention có thể khác.
5. **“Không thấy event trong `jfr summary` chứng minh nó không xảy ra.”** Sai: event có thể bị tắt, lọc, ngưỡng cao, file ngắn hoặc không đúng cửa sổ.
6. **“`jdk.ExecutionSample` đếm chính xác lời gọi method.”** Sai: sample phản ánh quan sát trong các thời điểm lấy mẫu, không phải invocation counter.
7. **“Một `jdk.ObjectAllocationSample` bằng một object được tạo.”** Sai: sampling/weight cần được hiểu đúng.
8. **“`threshold=5ms` làm các lock nhanh hơn.”** Sai: chỉ thay cách ghi event; bản thân quan sát còn có overhead.
9. **“Tên `settings=locks.jfc` nghĩa là cả host và container đều đọc được file.”** Sai: JVM thực hiện recording phải truy cập được template và vị trí ghi file.
10. **“Thấy nhiều event là tìm được nguyên nhân.”** Sai: event count phải gắn với duration, stack, workload, chuỗi nguyên nhân và phép đo trước/sau.
11. **“Chỉnh file `default.jfc` trong JDK là cách duy nhất.”** Sai: tạo bản sao/custom riêng để giữ preset gốc và lưu provenance.
12. **“Chỉ cần mở file trong JMC là đủ xác minh.”** Sai: cần xác minh đúng PID/thời gian, event settings thực tế và điều kiện workload.

## 11. Câu hỏi tự kiểm tra

**Câu A.** Hệ thống production bị chậm 2 lần mỗi tuần. Bạn có thể giữ một recording nhỏ trong nhiều giờ. Chọn gì?

**Trả lời:** Bắt đầu `default.jfc` với retention và dung lượng được giới hạn, dump quanh mốc sự cố. Khi đã xác định nhóm event còn thiếu, lập recording profile/custom ngắn ở cửa sổ tái hiện. Không bật full allocation/exception tracing liên tục chỉ để “có đủ mọi thứ”.

**Câu B.** p99 tăng và monitor wait 8–12 ms nhưng recording không có `jdk.JavaMonitorEnter`. Có kết luận không bị contention được không?

**Trả lời:** Chưa. Xem event có bật không, threshold hiện tại bao nhiêu, stackTrace và cửa sổ đo có đúng không. Nếu threshold đang 20 ms, một custom `threshold=5ms` hợp lý cho thử nghiệm có kiểm soát.

**Câu C.** Hai recording `jdk.ExecutionSample` có lần lượt 800 và 2.000 event nhưng durations 20 giây và 120 giây. Lần sau CPU chắc chắn tăng?

**Trả lời:** Không. Số event tuyệt đối tăng có thể chỉ do thời gian dài hơn, period hoặc cấu hình khác. Cần chuẩn hóa thời lượng, settings, workload và cách diễn giải sampling.

**Câu D.** Khi phân tích allocation, `jdk.ObjectAllocationSample` xuất hiện 500 lần. Có nghĩa JVM đã cấp phát đúng 500 đối tượng?

**Trả lời:** Không. Đây là event lấy mẫu; cần hiểu trọng số và thuật toán sampling, dùng profiler/JMH/heap metrics phù hợp để kiểm chứng.

**Câu E.** Custom recording có rất nhiều event I/O, nhưng không thấy nguyên nhân p99. Nên làm gì?

**Trả lời:** Kiểm tra có đúng request thời điểm lỗi và stack liên quan không; xem event I/O chiếm thời gian bao lâu, event threshold và workload. Nếu không tương quan, điều tra lock/queue/GC hoặc nguồn chờ khác. Loại bớt các event không phục vụ giả thuyết, giữ chi phí đo phù hợp.

## Ghi nhớ

- **`default.jfc`**: bắt đầu khi cần lịch sử/timeline và overhead thấp, thường phù hợp ghi liên tục.
- **`profile.jfc`**: dành cho cửa sổ profiling có giới hạn, khi cần nhiều sample/hot spots hơn.
- **`custom.jfc`**: chọn khi câu hỏi yêu cầu một event, ngưỡng, period hoặc stack trace khác; tạo từ template gốc và xác minh settings hiệu lực.
- **Sự kiện nào, trong bao lâu, điều kiện gì, chi phí nào?** là bốn câu hỏi trước khi bật JFR. Sau khi thu, chứng minh rằng file có đúng dữ liệu cần dùng rồi mới kết luận.

### Tài liệu chính thức để đối chiếu theo JDK

- Oracle Java 21, *Flight Recorder Configurations*: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Oracle Java 21, *The jfr Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 21, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Dev.java, *Configuring the JDK Flight Recorder*: https://dev.java/learn/jvm/jfr/configure/
- Inside Java, *JFR Configuration Improvements*: https://inside.java/2022/06/13/sip055/
