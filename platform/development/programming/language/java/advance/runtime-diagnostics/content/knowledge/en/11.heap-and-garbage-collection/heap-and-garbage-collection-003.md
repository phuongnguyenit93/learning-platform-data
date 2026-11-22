# 11.3 Allocation rate, thời gian sống đối tượng và áp lực lên bộ thu gom

> Bối cảnh: Java 17+ trên HotSpot JVM. Phần luồng đối tượng dùng G1 GC làm ví dụ cụ thể; chính sách cấp phát, thế hệ và di chuyển đối tượng thay đổi theo collector, phiên bản JDK và cấu hình.

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Tính và diễn giải **allocation rate** (tốc độ cấp phát) mà không nhầm với lượng heap đang được sử dụng.
- Giải thích vì sao **thời gian sống / khả năng sống sót qua GC** làm thay đổi chi phí thu gom, promotion và áp lực lên old generation.
- Phân biệt **allocation churn** (tạo đối tượng ngắn hạn liên tục), **retention** hợp lệ và **memory leak** do tham chiếu tồn tại ngoài ý muốn.
- Dùng GC log, Java Flight Recorder (JFR), Java Mission Control (JMC) và phép đo có kiểm soát để tìm nguyên nhân trước khi tối ưu.

## 1. Ba đại lượng cần tách biệt

**Allocation rate** là tổng số byte mà chương trình cấp phát trong một khoảng thời gian, chia cho thời gian đo:

~~~text
allocation rate (MiB/s) ≈ allocated bytes / elapsed seconds / 1_048_576
~~~

Ví dụ một luồng xử lý tạo 600 MiB đối tượng trong 5 giây thì allocation rate trung bình là 120 MiB/s. Đây là **lưu lượng cấp phát**, không có nghĩa heap phải có thêm 600 MiB sau 5 giây. Phần lớn đối tượng có thể đã trở nên không còn truy cập được và được GC tái sử dụng không gian.

**Live set / retained heap** là lượng đối tượng vẫn còn *reachable* từ GC roots tại thời điểm quan sát. GC roots có thể gồm local/stack tham chiếu đang còn hiệu lực, trường static, luồng, JNI handles và các cấu trúc JVM. Heap usage trước GC bao gồm cả đối tượng đã chết nhưng chưa được thu hồi; heap usage sau một kỳ GC phù hợp thường gần với live set hơn, song vẫn phụ thuộc giai đoạn collector.

**Object lifetime** là thời gian từ lúc đối tượng được tạo cho đến khi nó không còn reachable. Thời điểm đối tượng được *thu hồi vật lý* có thể muộn hơn lúc nó chết về mặt reachability. **Object age** trong một GC có thế hệ thường tính bằng số kỳ thu gom trẻ mà đối tượng đã sống sót; nó không đồng nghĩa số mili-giây đối tượng tồn tại.

Ví dụ web service nhận 10.000 yêu cầu/giây và cấp phát trung bình 12 KiB/yêu cầu:

~~~text
10_000 × 12 KiB/s = 120_000 KiB/s ≈ 117,2 MiB/s
~~~

Nếu 99% lượng cấp phát nhanh chóng trở nên unreachable, chương trình vẫn có thể tạo áp lực GC do liên tục cần không gian cấp phát. Nếu 1% còn lại **tiếp tục được giữ vô thời hạn** trong một cache không giới hạn, riêng phần đó tăng khoảng 1,17 MiB/s, xấp xỉ 70 MiB/phút. Tỷ lệ giữ lại nhỏ vẫn nguy hiểm khi kéo dài và không có chính sách giải phóng.

## 2. Hành trình đối tượng trong heap và mối liên hệ với GC

Với cấu hình HotSpot G1 thông dụng, có thể hình dung luồng tổng quát:

1. Luồng Java thường cấp phát đối tượng nhỏ vào **Thread-Local Allocation Buffer (TLAB)** để tránh tranh chấp trên đường cấp phát nhanh. Khi TLAB hết chỗ, luồng xin vùng mới; một số cấp phát không đi qua TLAB.
2. Đa số đối tượng mới được đặt trong các vùng **Eden** của young generation. G1 chia heap thành các *region* và điều chỉnh số region trẻ theo mục tiêu của collector.
3. Young GC tìm đối tượng trẻ còn reachable rồi **evacuate/copy** các đối tượng sống sang Survivor hoặc Old; những đối tượng chết không cần sao chép từng cái. Một đối tượng có thể sống qua nhiều young GC trước khi được promotion; ngưỡng tuổi và quy tắc di chuyển do collector quyết định.
4. Khi nhiều đối tượng sống lâu, lượng dữ liệu phải sao chép, vùng Survivor và tốc độ đưa đối tượng sang Old cùng tăng. Old occupancy hoặc lượng công việc thu gom old tăng có thể dẫn đến mixed collection, concurrent marking hay những tình huống thu gom tốn kém khác.
5. Đối tượng rất lớn có thể đi theo đường cấp phát đặc biệt; G1 có khái niệm *humongous object* chiếm các region chuyên biệt. Vì vậy không suy diễn rằng **mọi** đối tượng đều đi tuần tự qua Eden → Survivor → Old.

Không phải collector nào cũng có cùng khái niệm generations/age: cơ chế và chi tiết log của G1, Parallel GC, ZGC, Shenandoah khác nhau; một số collector/phiên bản còn có chế độ generational riêng. Hãy xem collector thực tế được JVM sử dụng trước khi diễn giải promotion hoặc các vùng nhớ.

### Vì sao lifetime quan trọng?

| Nhóm đối tượng | Ví dụ | Hệ quả thường gặp |
| --- | --- | --- |
| Rất ngắn hạn | Chuỗi trung gian, wrapper, mảng tạm cho một thao tác | Allocation rate có thể cao nhưng tỷ lệ sống qua young GC thấp; young GC thường thu hồi được nhiều chỗ |
| Qua vài lần young GC | Request chờ hàng đợi, batch đang xử lý, đối tượng được chia sẻ ngắn hạn | Tăng chi phí sao chép Survivor và có thể được promotion |
| Sống lâu có chủ đích | Cấu hình, cache có giới hạn, index đang dùng | Đóng góp vào live set nền; cần sizing và giới hạn rõ ràng |
| Bị giữ ngoài ý muốn | Map static tăng mãi, listener không gỡ, queue không tiêu thụ, reference chain còn bám | Old/live set có thể tăng theo thời gian và cuối cùng làm cạn heap |

Sống lâu **không tự động là leak**: một cache ổn định có thể hợp lệ. Ngược lại, allocation rate thấp cũng không bảo đảm GC khỏe nếu live set quá lớn.

## 3. Tại sao allocation rate và lifetime tạo áp lực lên collector?

Có ít nhất bốn cơ chế liên quan:

**(1) Cạn không gian cấp phát nhanh.** Tạo đối tượng càng nhanh, Eden/TLAB càng phải nạp lại và young collection càng có cơ hội diễn ra thường xuyên. Xấp xỉ trực giác:

~~~text
khoảng cách giữa các young GC ≈ dung lượng cấp phát trẻ hữu dụng / tốc độ cấp phát vào vùng đó
~~~

Nếu giả sử vùng cấp phát trẻ hữu dụng là 192 MiB và luồng cấp phát vào đó 96 MiB/s, khoảng cách lý tưởng là khoảng 2 giây. Đây chỉ là mô hình đơn giản: TLAB waste, kích thước thế hệ trẻ thay đổi, cấp phát lớn, survivor và chính sách collector khiến số thật khác.

**(2) Chi phí thu gom phụ thuộc *đối tượng còn sống*.** GC thường xử lý phần lớn dữ liệu sống để đánh dấu/sao chép/di chuyển. Một Eden đầy đối tượng đã chết có thể tương đối rẻ để thu hồi; Eden chứa nhiều đối tượng sống cần sao chép sẽ tốn CPU, băng thông bộ nhớ và có thể tăng pause.

**(3) Áp lực lên Old.** Khi đối tượng sống đủ lâu hoặc không còn chỗ Survivor, chúng có thể được đưa sang Old. Promotion cao kéo theo tăng old occupancy, nhiều việc cho concurrent marking/mixed GC và rủi ro thiếu không gian di chuyển. **Promotion rate không đồng nhất với allocation rate**, và mức tăng old occupancy cũng không đo trực tiếp số byte được giữ mới, vì GC đồng thời có thể thu hồi đối tượng cũ.

**(4) Cạnh tranh tài nguyên ứng dụng.** GC sử dụng CPU, cache, băng thông bộ nhớ và đôi khi có pha Stop-The-World (STW); việc duy trì collector cao có thể giảm throughput hoặc làm xấu tail latency. Phân biệt **GC CPU / tổng CPU**, **tổng pause time / thời gian chạy**, **p95/p99 pause** và **p95/p99 request latency**: chúng liên quan nhưng không phải một đại lượng.

Như vậy, áp lực GC không thể kết luận bằng một phép đo MiB/s. Phải xem đồng thời **allocation rate + phân bố lifetime/survival + live set + cấu hình heap/collector + mục tiêu latency/throughput**.

## 4. Allocation churn, retention và leak: phân biệt bằng dấu hiệu

- **Churn cao, live set ổn định:** Nhiều byte được cấp phát mỗi giây; GC chạy khá thường nhưng lượng heap còn sau GC gần như đi ngang. Khả năng cao là tạo đối tượng tạm liên tục. Tối ưu nếu chi phí GC/CPU hoặc latency thật sự vượt mục tiêu.
- **Promotion cao, heap sau GC tăng:** Nhiều đối tượng vượt qua các young GC hoặc có thêm tham chiếu sống lâu. Kiểm tra cache, queue, session và pipeline xử lý chậm. Đây là **nghi vấn retention**, chưa đủ để tuyên bố leak.
- **Live set lớn, allocation rate thấp:** Bộ nhớ đang cần cho trạng thái hợp lệ có thể lớn. Vấn đề lúc này thường là footprint/old GC/giới hạn heap chứ không hẳn tạo đối tượng quá nhanh.
- **Old occupancy tăng không có điểm dừng ở workload ổn định:** Kiểm tra thứ gì giữ đối tượng và liệu lưu lượng đầu vào có vượt khả năng tiêu thụ. Chỉ sau khi tìm được chuỗi tham chiếu không mong muốn mới kết luận memory leak.

Một đợt *spike* heap trước young GC là bình thường. Đừng suy ra leak từ đường răng cưa của biểu đồ used heap; cần quan sát nền dùng bộ nhớ qua nhiều chu kỳ GC tương đương và cùng mức tải.

## 5. Đo đạc thực tế: dùng công cụ cho đúng câu hỏi

### 5.1 GC unified logging: biết GC diễn ra lúc nào và tốn bao nhiêu

Trên HotSpot Java 17+, có thể chạy ứng dụng với GC log:

~~~sh
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*,gc+age=trace:file=gc.log:time,uptime,level,tags AllocationLifetimeDemo
~~~

Đây là ví dụ cấu hình để quan sát, **không phải** bộ cờ tối ưu mặc định cho hệ thống thực tế. Trong log, đối chiếu mốc thời gian, loại GC, pause duration, heap trước/sau GC, thay đổi vùng Eden/Survivor/Old và thông tin tuổi/survivor khi collector xuất ra. GC log không tự chỉ ra chính xác dòng Java nào sinh nhiều đối tượng.

Khi đánh giá một dịch vụ, nên so cùng khoảng thời gian với request rate, throughput, tail latency và CPU. Nếu thay đổi collector hoặc phiên bản JDK, tên sự kiện và ý nghĩa một số bộ đếm có thể khác.

### 5.2 JFR + Java Mission Control: tìm call stack cấp phát

JFR ghi thông tin chẩn đoán từ JVM với mức overhead phụ thuộc cấu hình. Đối với một tiến trình Java đang chạy, dùng PID thật:

~~~sh
jcmd <pid> JFR.start name=allocation-study settings=profile duration=60s filename=allocation.jfr
jfr summary allocation.jfr
jfr print --events jdk.ObjectAllocationSample allocation.jfr
~~~

Lệnh `jfr summary` và `jfr print` chạy **sau khi** bản ghi đã được ghi thành file. Có thể mở file trong **Java Mission Control** để xem các allocation hot spots, loại đối tượng, thread, stack trace và tương quan với GC/CPU. Trong một bản ghi quá ngắn, có thể không đủ mẫu hữu ích.

Sự kiện **jdk.ObjectAllocationSample** được lấy mẫu và có trọng số ước tính (*sample weight*); **không cộng số event như thể đó là số đối tượng được cấp phát toàn phần**. Các sự kiện liên quan TLAB và allocation ngoài TLAB có cơ chế thu thập/chi phí khác; phải kiểm tra event thực tế được bật trong file JFR trước khi phân tích. Đừng dùng một stack mẫu duy nhất làm kết luận nguyên nhân của toàn bộ workload.

JFR cũng có nhóm sự kiện hỗ trợ phân tích đối tượng sống lâu (ví dụ Old Object Sample khi được cấu hình phù hợp), nhưng đó **không phải** bản ghi đầy đủ thời gian sống của mọi đối tượng. Chụp heap dump / truy GC roots là kỹ thuật kiểm tra retention khi có nghi vấn cụ thể, có chi phí pause và dung lượng file đáng kể.

### 5.3 JMH: so chi phí cấp phát của một đoạn code nhỏ

Với benchmark đã được xây bằng JMH, tùy chọn `-prof gc` có thể hiển thị các chỉ số như `gc.alloc.rate` (MB/s) và `gc.alloc.rate.norm` (B/op), cùng các chỉ số GC được hỗ trợ. **B/op** tiện để so hai cách xử lý cùng một đơn vị công việc; **MiB/s** phản ánh lượng byte trên thời gian và còn phụ thuộc số thao tác/giây.

Phải có warmup, đủ iteration/fork và tiêu thụ kết quả đúng cách. JIT có thể loại bỏ allocation bằng escape analysis/scalar replacement hoặc dead-code elimination; benchmark quá đơn giản có thể đo **code đã được JVM tối ưu khác xa code tác giả hình dung**. JMH là công cụ đo vi mô, không thay thế phép đo toàn hệ thống dưới tải đại diện.

### 5.4 Điều nên và không nên đọc từ các công cụ khác

- `jcmd <pid> GC.class_histogram` hoặc heap dump giúp nhận diện loại đối tượng có mặt trong heap, **không trực tiếp cho biết allocation rate theo call site**; một số thao tác có thể gây pause. Dùng có chủ đích, đặc biệt ở production.
- `GarbageCollectorMXBean` cung cấp số lần/thời gian GC theo collector; các bộ đếm tích lũy cần lấy hiệu giữa hai thời điểm, và không chứng minh nguyên nhân allocation.
- Used heap, committed heap, max heap và RSS của tiến trình là các thước đo khác nhau. Off-heap/direct buffers, metaspace, stack và native allocations không được phép quy tất cả về Java heap allocation.

## 6. Ví dụ Java 17+ chạy được: sống ngắn so với bị giữ lại

Chương trình tạo hai kiểu vòng đời. Trong lượt đầu, một mảng 1 KiB được đưa qua trường `volatile` và thường nhanh chóng mất tham chiếu khi mảng mới thay thế nó; trong lượt sau, 4.000 mảng được lưu trong danh sách static nên còn reachable. Không gọi `System.gc()` để ép GC: khi nào thu gom là do JVM.

Lưu tệp **AllocationLifetimeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class AllocationLifetimeDemo {
    private static final List<byte[]> HELD = new ArrayList<>();
    private static volatile byte[] visible;

    private static void allocate(int count, boolean hold) {
        for (int i = 0; i < count; i++) {
            byte[] data = new byte[1_024];
            data[0] = (byte) i;
            visible = data; // Cho đối tượng escape; hạn chế bị tối ưu loại bỏ.
            if (hold) {
                HELD.add(data);
            }
        }
    }

    public static void main(String[] args) {
        allocate(100_000, false);
        System.out.println("after ephemeral: " + HELD.size());

        allocate(4_000, true);
        System.out.println("after retained: " + HELD.size());

        HELD.clear();
        visible = null;
        System.out.println("after release: " + HELD.size());
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --release 17 AllocationLifetimeDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC AllocationLifetimeDemo
~~~

Stdout từ chương trình (không bật log GC):

~~~text
after ephemeral: 0
after retained: 4000
after release: 0
~~~

**Diễn giải đúng:** 100.000 mảng đầu có tổng *payload được yêu cầu* là 102.400.000 byte (khoảng 97,7 MiB) cộng chi phí object header/alignment. Chúng **không cùng tồn tại trong danh sách**; JVM có thể tái sử dụng không gian của những mảng đã chết. 4.000 mảng ở lượt sau có payload khoảng 3,9 MiB và vẫn reachable qua `HELD` cho đến `clear()`. Kết quả `HELD.size() == 0` chỉ cho thấy danh sách đã bỏ tham chiếu: **không chứng minh GC vừa chạy, heap used đã giảm hay RSS của tiến trình đã trả lại hệ điều hành**.

Trường `visible` là một cách cho mảng có đường escape để quan sát cấp phát; đây là ví dụ giáo dục, không phải kỹ thuật nên đưa vào code ứng dụng. Các con số GC cụ thể sẽ thay đổi theo JDK, heap, collector, thời gian chạy và hệ thống. Để có JFR với chương trình ngắn này, có thể khởi động bản ghi ngay từ đầu:

~~~sh
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:StartFlightRecording=settings=profile,filename=allocation.jfr,dumponexit=true AllocationLifetimeDemo
jfr summary allocation.jfr
~~~

Ở lần chạy rất ngắn, JFR vẫn có thể thiếu mẫu allocation; trên một service dài hạn, hãy ghi trong cửa sổ có workload đủ đại diện. Khi bật `-Xlog:gc*`, stdout có thêm log JVM ngoài ba dòng do chương trình in ra.

## 7. Quy trình chẩn đoán có thể lặp lại

1. **Xác lập vấn đề và SLO:** Ví dụ CPU GC tăng từ 3% lên 20%, request p99 vượt ngưỡng hoặc old occupancy tiến sát giới hạn. Ghi rõ khoảng thời gian và phiên bản JDK, collector, `-Xms/-Xmx`, CPU/memory limit của container.
2. **Cố định workload so sánh:** RPS, kích thước request/response, cache warmup, tỷ lệ lỗi, kiểu dữ liệu, concurrency và thời gian chạy. Đừng so hai profile có lưu lượng khác nhau mà chỉ nhìn MiB/s.
3. **Đo ba lớp:** (a) allocation rate và top call stacks từ JFR/JMH khi phù hợp; (b) tần suất/pause và young/survivor/old từ GC logs; (c) live set và đồ thị post-GC occupancy qua thời gian. Đồng bộ timestamp với CPU và latency.
4. **Đặt giả thuyết cụ thể:** “Mỗi request tạo nhiều bản sao `byte[]` vì chuyển đổi định dạng hai lần” hoặc “Queue có tốc độ thêm > tốc độ xử lý nên các request sống lâu”. Dự đoán chỉ số nào phải thay đổi nếu giả thuyết đúng.
5. **Thay đổi một nguyên nhân:** Loại bỏ copy dư thừa, giới hạn queue, sửa cache eviction, cải thiện streaming/batching... Sau đó đo lại cùng loại workload. Theo dõi cả allocation B/op, throughput, CPU GC, p99 và bộ nhớ còn sau GC.
6. **Kiểm tra trade-off:** Một kỹ thuật giảm số đối tượng nhưng giữ buffer lâu hơn có thể làm tăng live set hoặc contention. Ưu tiên kết quả đo được và tính đúng đắn, không tối ưu chỉ vì biểu đồ allocation giảm.

## 8. Ba tình huống đọc số liệu

| Quan sát dưới tải tương đương | Giả thuyết đầu tiên | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Allocation 300 MiB/s, young GC thường xuyên, sau GC heap ổn định, CPU GC cao | Churn đối tượng ngắn hạn | JFR allocation top stacks và B/op; so p99 trước/sau giảm copy |
| Allocation 70 MiB/s, old occupancy sau GC tăng liên tục, queue/cache cũng tăng | Dữ liệu bị giữ lại lâu hoặc consumer xử lý không kịp | Heap histogram, đường tham chiếu GC roots, kích thước queue/cache và eviction policy |
| Allocation 15 MiB/s, post-GC live set sát `-Xmx`, pause xấu | Tập dữ liệu sống lớn so với heap, có thể kèm fragmentation hoặc chính sách GC không hợp | Object histogram, live set ổn định hay tăng, heap/headroom, log collector thực tế |

Các con số trên là tình huống minh họa, **không phải ngưỡng cố định** để chẩn đoán mọi JVM. “Allocation rate cao” chỉ có ý nghĩa khi đặt cạnh ngân sách CPU, pause SLO, workload và mức heap.

## 9. Hướng tối ưu theo nguồn áp lực

**Khi churn tạo CPU GC lớn:** Trước tiên xác định hot stack. Cân nhắc bỏ conversion/copy trung gian, tránh boxing và chuỗi tạm trong vòng lặp nóng, chuyển sang streaming khi không cần giữ toàn bộ dữ liệu, hoặc batch các tác vụ nhỏ có chi phí tạo wrapper cao. So **B/op** và thời gian xử lý; một chuỗi API gọn hơn không mặc định tạo ít đối tượng hơn. Đừng triển khai object pool cho đối tượng nhỏ chỉ theo trực giác: pool giữ chúng sống lâu, thêm đồng bộ và có thể kém hơn cơ chế cấp phát nhanh của JVM.

**Khi retention/promotion lớn:** Rà soát phạm vi tham chiếu; giới hạn cache theo kích thước/TTL, gỡ listener khi hết vòng đời, bảo đảm hàng đợi có backpressure hoặc giới hạn, kết thúc batch và đóng tài nguyên đúng thời điểm. Cắt bớt lượng tham chiếu sống lâu có thể hiệu quả hơn giảm vài byte của đối tượng tạm.

**Khi live set lớn nhưng hợp lệ:** Đánh giá heap headroom, cấu trúc dữ liệu (đặc biệt độ dư/bộ nhớ kèm theo của map/list), nhu cầu giữ dữ liệu, phân vùng/batching và collector thích hợp với mục tiêu latency/throughput. Tuning heap hay collector sau khi có baseline; tăng `-Xmx` có thể giảm tần suất GC nhưng cũng đổi footprint và đặc điểm pause. Không giải quyết leak bằng cách cứ tăng heap.

**Khi có nhiều đối tượng kích thước lớn:** Xem luồng copy mảng/buffer, đường cấp phát đặc biệt, giới hạn kích thước batch và áp lực lên region/fragmentation theo collector. Đừng đồng nhất cấp phát native/direct memory với Java heap allocation.

## 10. Những kết luận sai hay gặp

1. **“Heap tăng trước GC nghĩa là leak.”** Không: trước GC có thể chứa lượng lớn đối tượng đã chết; xem sau GC và các GC roots.
2. **“Allocation 1 GiB/s buộc heap lớn hơn 1 GiB.”** Không: đó là lưu lượng byte/giây; tốc độ thu hồi và live set quyết định khả năng vận hành.
3. **“Ít GC nhất là tốt nhất.”** Không: pause dài hoặc live set lớn có thể tệ hơn các young GC ngắn; xem SLO tổng thể.
4. **“Đối tượng vào Old là leak.”** Không: nhiều cấu trúc sống lâu hợp lệ; promotion chỉ là cơ chế quản lý.
5. **“Sau `clear()` bộ nhớ hệ điều hành phải giảm.”** Không: GC không nhất thiết chạy ngay, heap đã commit có thể vẫn được JVM giữ.
6. **“Một JFR allocation event tương đương một allocation thật.”** Không: sampling, event configuration, weight và stack context quyết định cách diễn giải.
7. **“Giảm số `new` trong source chắc chắn giảm byte cấp phát.”** Không: JIT tối ưu có thể loại bỏ allocation; ngược lại một object pool giữ byte sống lâu có thể tăng áp lực GC.
8. **“GC pause là nguyên nhân mọi request chậm.”** Không: phải đối chiếu timestamp với CPU, I/O, lock contention, network và thời gian queue.

## 11. Tự kiểm tra khả năng suy luận

**Bài toán A.** Nếu luồng thực sự cấp phát 120 MiB/s và khoảng dung lượng trẻ hữu dụng giả định là 240 MiB, nhịp lấp đầy đơn giản là bao lâu? **Đáp án:** khoảng 2 giây. Đó không phải lịch GC được bảo đảm vì young size và survival thay đổi.

**Bài toán B.** Hai bản chạy cùng 100 MiB/s. Bản 1 có post-GC live set ổn định 300 MiB; bản 2 tăng từ 300 lên 800 MiB qua nhiều phút ở cùng tải. Bản nào cần điều tra retention trước? **Đáp án:** bản 2. Cần đối chiếu cache/queue/reference chain, không lập tức khẳng định leak.

**Bài toán C.** Bạn giảm từ 200 xuống 90 B/op nhưng p99 tăng và old occupancy tăng. Đã tối ưu thành công chưa? **Đáp án:** chưa thể kết luận. Có thể đã đổi allocation ngắn hạn thành giữ buffer lâu, tăng contention hoặc thêm chi phí khác; phải đánh giá throughput, p99, CPU GC và live set cùng nhau.

## Ghi nhớ để áp dụng

- **Allocation rate** trả lời “chương trình tạo bao nhiêu byte mỗi giây?”; **live set** trả lời “bao nhiêu byte vẫn cần giữ?”; **lifetime/survival** nối hai đại lượng đó với chi phí GC.
- **High churn** và **high retention** đòi hỏi chiến lược khác nhau. Quan sát GC logs để biết *khi nào/chi phí thu gom*; dùng JFR/JMC để biết *ai cấp phát*; dùng reference analysis khi nghi *ai giữ lại*.
- Một thay đổi tốt được xác minh bằng workload đại diện và mục tiêu ứng dụng, không chỉ bằng việc giảm số lần gọi `new` hay số lần GC.

### Tài liệu tham khảo

- Oracle, *Java 21 GC Tuning Guide*: https://docs.oracle.com/en/java/javase/21/gctuning/
- Oracle, *Java 21 Diagnostic Tools* (JFR, `jcmd`, heap histogram): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Dev.java, *Configuring the JDK Flight Recorder*: https://dev.java/learn/jvm/jfr/configure/
