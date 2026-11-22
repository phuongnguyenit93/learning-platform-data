# 1.5 Từ triệu chứng đến giả thuyết, bằng chứng và nguyên nhân gốc

> **Module:** Java Advance – runtime-diagnostics · **Nhóm:** 1. Mô hình chẩn đoán

## 1. Mục tiêu và phạm vi

Khi ứng dụng Java chậm, treo, tăng CPU, hết bộ nhớ hoặc lỗi thất thường, thứ nhìn thấy đầu tiên thường chỉ là **triệu chứng**. Chẩn đoán tốt là quá trình biến triệu chứng thành một giả thuyết **có thể kiểm chứng và bác bỏ**, tìm bằng chứng từ JVM và các thành phần liên quan, rồi xác định cơ chế thực sự sinh ra sự cố. Mục tiêu không phải tìm một biểu đồ bất thường để đặt tên cho lỗi, mà là giải thích được **tại sao**, **trong điều kiện nào**, **bằng cơ chế nào** và **vì sao biện pháp khắc phục có hiệu quả**.

Sau bài này, người học có thể:

- Mô tả sự cố bằng các chỉ số, mốc thời gian và phạm vi ảnh hưởng thay cho cảm nhận như “hệ thống có vẻ chậm”.
- Phân biệt triệu chứng, tín hiệu quan sát, giả thuyết, bằng chứng, nguyên nhân trực tiếp, nguyên nhân gốc và yếu tố góp phần.
- Lập các giả thuyết cạnh tranh và dự đoán dấu vết quan sát được nếu từng giả thuyết đúng.
- Chọn phép đo JVM/ứng dụng/hệ điều hành phù hợp, diễn giải bằng chứng dương tính và âm tính, tránh nhầm tương quan với nhân quả.
- Kiểm chứng cơ chế bằng chuỗi chứng cứ, tái hiện có kiểm soát hoặc thay đổi có khả năng đảo ngược, rồi xác nhận kết quả sau sửa lỗi.

Phạm vi là **tư duy chẩn đoán Java runtime**. Các công cụ như thread dump, JFR, GC log, heap dump, metric và trace xuất hiện như nguồn chứng cứ; bài này không thay thế hướng dẫn chuyên sâu cho từng công cụ.

## 2. Sáu khái niệm cần tách bạch

| Khái niệm | Câu hỏi nó trả lời | Ví dụ trong Java |
| --- | --- | --- |
| **Triệu chứng (symptom)** | Người dùng/hệ thống đang gặp điều gì? | p99 độ trễ API tăng từ 250 ms lên 3 s, 5xx tăng. |
| **Tín hiệu (signal)** | Có số đo hoặc dấu vết gì? | 40 luồng BLOCKED; hàng đợi HTTP tăng; GC pause vẫn thấp. |
| **Giả thuyết (hypothesis)** | Cơ chế nào *có thể* tạo ra triệu chứng? | Một monitor đang bị giữ quá lâu khiến nhiều request phải chờ. |
| **Bằng chứng (evidence)** | Quan sát nào ủng hộ hoặc bác bỏ giả thuyết? | Nhiều thread dump ở các thời điểm khác nhau đều chỉ tới cùng monitor và luồng sở hữu. |
| **Nguyên nhân gốc (root cause)** | Điều kiện/cơ chế nào khiến sự cố phát sinh và có thể sửa để ngăn tái diễn? | Mã giữ khóa dùng chung trong khi gọi thao tác chậm; khi tải tăng, thời gian đợi khóa khuếch đại. |
| **Yếu tố góp phần (contributing factor)** | Điều gì làm sự cố dễ xảy ra hoặc nghiêm trọng hơn? | Retry đồng loạt, hàng đợi không giới hạn, thiếu cảnh báo về lock contention. |

**Nguyên nhân trực tiếp** khác nguyên nhân gốc. Ví dụ, timeout ở API là nguyên nhân trực tiếp của phản hồi lỗi; request bị chặn tại khóa có thể là cơ chế gần; thiết kế critical section bao cả lời gọi chậm mới là nguyên nhân gốc có thể sửa. Một sự cố có thể có **nhiều nguyên nhân gốc**, và “gốc” được xác định theo phạm vi hệ thống có thể kiểm soát, không phải một nhãn tuyệt đối.

**Biện pháp giảm thiểu (mitigation)** khác **sửa nguyên nhân (fix)**. Tăng số replica, tắt chức năng có lỗi hoặc rollback có thể giúp khôi phục dịch vụ nhanh, nhưng nếu thiết kế đồng bộ hóa sai vẫn tồn tại, sự cố có thể trở lại.

## 3. Khởi đầu bằng một phát biểu sự cố có thể đo được

Trước khi dùng profiler hoặc nhìn mã nguồn, hãy viết một “problem statement” gồm:

1. **Ảnh hưởng:** luồng người dùng/API nào, tỷ lệ lỗi, SLO nào bị vi phạm, số lượng instance và khách hàng liên quan.
2. **Chênh lệch so với baseline:** p50/p95/p99, throughput, CPU, heap, GC, queue hoặc error rate trước và sau; ghi rõ đơn vị, cửa sổ lấy mẫu và số mẫu.
3. **Thời gian:** lần cuối bình thường, thời điểm bắt đầu bất thường, thời gian phục hồi; đồng bộ timezone và đồng hồ giữa các nguồn.
4. **Điều kiện xuất hiện:** chỉ ở một phiên bản, node, tenant, route, tải, cỡ payload hay khoảng giờ nào.
5. **Thay đổi gần thời điểm lỗi:** triển khai, flag, traffic, cấu hình JVM, schema/index, dependency, certificate, cron, cache hoặc giới hạn tài nguyên.
6. **Những điều *chưa biết*:** dữ liệu thiếu hoặc có nguy cơ sai, để không biến giả định thành sự thật.

Ví dụ giả định: “Từ 14:05–14:18 UTC, p99 của POST /orders tăng 240 ms → 2.8 s ở 3/4 instance của bản v2.7; throughput gần như không đổi, tỷ lệ timeout tăng 0.1% → 7%; CPU JVM khoảng 30%, GC pause p99 dưới 20 ms; vừa bật cờ gọi dịch vụ đối soát.” Phát biểu này gợi hướng điều tra rõ hơn nhiều so với “Java chậm sau deploy”, nhưng **chưa chứng minh** cờ mới là nguyên nhân.

Tránh so sánh p99 giữa các cửa sổ có lưu lượng và số mẫu quá khác nhau mà không ghi chú. p99 của tập ít mẫu có thể dao động mạnh; trung bình có thể che đuôi phân phối. Thống nhất metric ở cấp request hay ở cấp từng dependency, tránh đánh đồng hai loại.

## 4. Chuỗi chẩn đoán: từ quan sát tới cơ chế nhân quả

Dùng vòng lặp sau, quay lại bước trước bất cứ lúc nào bằng chứng bác bỏ giả định:

**Triệu chứng → định lượng/timeline → giả thuyết cạnh tranh → dự đoán dấu vết → thu bằng chứng → thử bác bỏ/kiểm chứng → nguyên nhân gốc → hành động → xác nhận.**

### Bước 1 — Khoanh vùng ảnh hưởng và lập timeline

Lấy các mốc phát hiện, phát sinh, deploy/flag, thay đổi tải, bắt đầu retry, rollback và phục hồi. So sánh instance **bị ảnh hưởng** với instance **không bị ảnh hưởng** trong cùng thời gian; đây thường là đối chứng tốt hơn việc nhìn một biểu đồ đơn lẻ.

Cần hỏi: lỗi có xảy ra trước lần triển khai đáng nghi không? Tải tăng trước hay sau độ trễ? Thread pool đầy là nguyên nhân ban đầu hay hậu quả của request chạy lâu? Một thứ xuất hiện **sau** triệu chứng khó là tác nhân khởi phát, nhưng vẫn có thể khuếch đại sự cố.

### Bước 2 — Lập nhiều giả thuyết có thể bác bỏ

Mỗi giả thuyết phải nói rõ cơ chế và **dấu vết dự đoán**. Ví dụ cùng một triệu chứng “p99 tăng, CPU thấp” có thể do:

| Giả thuyết | Nếu đúng, kỳ vọng thấy | Bằng chứng có thể làm yếu/bác bỏ |
| --- | --- | --- |
| H1: lock contention | Nhiều luồng BLOCKED hoặc park chờ cùng tài nguyên qua nhiều mẫu; thời gian chờ tăng theo tải | Luồng đang xử lý request không đợi lock; không thấy điểm tranh chấp trong khoảng lỗi |
| H2: database pool cạn | Thời gian acquire connection và số request chờ pool tăng; active connection chạm giới hạn | Acquire time thấp, pool còn nhiều connection rảnh ở đúng thời điểm |
| H3: dependency chậm | Client span/timeout đến cùng endpoint tăng, pool hoặc socket wait trùng khoảng lỗi | Dependency span ổn định, phần chậm nằm trước/sau lời gọi |
| H4: GC pause kéo dài | Thời điểm pause trong GC log/JFR trùng khoảng request bị trì hoãn | Tổng thời gian pause rất nhỏ so với sự cố; nhiều request chậm khi JVM vẫn chạy |
| H5: CPU quota/throttling | Container CPU bị throttle, run queue tăng, request chậm khi quota chạm mức | Không thấy throttling và không có tiến trình/luồng tiêu CPU liên quan |

“Có thể lỗi ở JVM” chưa đủ là giả thuyết. Viết theo mẫu: **Nếu [cơ chế X] gây [triệu chứng Y], tôi kỳ vọng [quan sát A/B] trong [khoảng thời gian/phạm vi]; nếu quan sát [C], giả thuyết suy yếu.** Chọn giả thuyết theo mức giải thích, độ kiểm chứng, mức ảnh hưởng và chi phí đo; tránh chỉ ưu tiên cái dễ sửa.

### Bước 3 — Thu bằng chứng từ ít xâm lấn đến chuyên sâu

Bắt đầu bằng log có correlation ID, request metrics, trace hiện có, dashboard JVM/OS và thông tin thay đổi. Khi chưa đủ, mới lấy thread dump, JFR, GC log hoặc heap dump có chủ đích. Ghi rõ **thời điểm**, phiên bản, process ID, instance, kích thước mẫu và điều kiện thu.

Một snapshot chỉ thể hiện trạng thái tại một khoảnh khắc. Thread dump lặp lại khi lỗi đang diễn ra giúp phân biệt điểm chờ thoáng qua với chờ kéo dài; JFR giúp khảo sát sự kiện theo thời gian. Thu ngay gần thời điểm có triệu chứng, vì dump sau khi đã phục hồi thường không còn dấu vết.

### Bước 4 — Đối chiếu và chủ động tìm dữ liệu phủ định

Tìm ít nhất hai nguồn bằng chứng bổ sung, ví dụ **trace request chậm → thread dump chờ monitor → metric contention tăng**. Tuy vậy, hai biểu đồ lấy từ cùng một nguồn không hẳn độc lập. Xem các trường hợp không lỗi, khoảng thời gian trước lỗi, instance đối chứng và lần lỗi không khớp mẫu.

Phân biệt:
- **Đồng xuất hiện:** CPU và p99 cùng tăng.
- **Thứ tự thời gian:** CPU tăng trước p99.
- **Cơ chế:** stack/profile chứng minh luồng tiêu CPU làm công việc nào, gây chậm đoạn nào.
- **Kiểm chứng tác động:** loại bỏ hoặc cô lập tác nhân thì độ trễ cải thiện trong điều kiện tương đương.

Chỉ khi nối được các mắt xích này mới nên tăng mức tin cậy về quan hệ nhân quả. Correlation ID giúp nối sự kiện nhưng **không tự chứng minh nguyên nhân**.

### Bước 5 — Kiểm chứng có kiểm soát

Ưu tiên thử trên môi trường staging với cùng cấu hình, cỡ tải, tập dữ liệu và phiên bản tương đương. Thay **một biến có ý nghĩa** mỗi lượt: ví dụ thu nhỏ critical section hoặc bỏ lời gọi remote ra ngoài lock; giữ nguyên traffic và thread-pool limit. Nếu cần kiểm chứng trực tiếp trên production, dùng canary/flag có giới hạn và kế hoạch rollback.

Một kiểm chứng mạnh trả lời được ba câu: (1) hiện tượng có tái hiện khi điều kiện gây lỗi xuất hiện không, (2) thay đổi nhắm vào cơ chế có làm biến mất dấu vết dự đoán không, (3) metric người dùng và tác dụng phụ có cải thiện bền vững không. Không ép production tái hiện OOM/deadlock chỉ để “chứng minh”.

### Bước 6 — Chốt nguyên nhân gốc và xác nhận sau sửa

Mô tả **trigger + cơ chế + tác động + điều kiện khuếch đại**. Phân tách hành động chữa cháy, sửa mã/cấu hình, và guardrail như giới hạn queue, circuit breaker, dashboard, cảnh báo hoặc regression test. So sánh trước/sau ở traffic tương tự, xác minh không chuyển lỗi sang hệ khác hoặc làm tăng chi phí vô hình.

Cần ghi “chưa xác định” nếu bằng chứng chỉ đủ để khoanh vùng. Mức tin cậy là một kết luận có điều kiện, không phải yêu cầu phải chọn một thủ phạm.

## 5. Đọc tín hiệu Java runtime đúng ngữ cảnh

| Nguồn tín hiệu | Dùng để kiểm tra | Bẫy diễn giải |
| --- | --- | --- |
| Request metric + distributed trace | Thành phần chiếm latency, retry, error, queue, dependency | Span thiếu sampling hoặc thời gian chờ trước span khiến kết luận lệch |
| Application log có request ID | Exception, quyết định nhánh xử lý, timeout, causal timeline | Log lúc lỗi lớn có thể bị drop, bất đồng bộ hoặc có clock skew |
| Thread dump | Trạng thái luồng, stack, monitor sở hữu/chờ, deadlock, executor | RUNNABLE không luôn bằng đang sử dụng CPU; một dump không nói được tần suất |
| JFR (Java Flight Recorder) | CPU samples, allocations, lock contention, I/O, GC, latency event theo thời gian | Recording cần đúng khoảng lỗi; sampling không phải đo tuyệt đối mọi lệnh |
| GC log / GC metrics | Pause, heap usage trước-sau GC, allocation pressure, collector behavior | GC xuất hiện đồng thời có thể là hệ quả của traffic/allocation, không phải nguyên nhân gốc |
| Heap dump / class histogram | Kiểu object, retained graph, nghi vấn retention | Dump lớn, nhạy cảm và có chi phí; object nhiều không tự chứng minh leak |
| OS/container metrics | CPU throttling, RSS, page fault, I/O, network, file descriptors | RSS khác Java heap; CPU % phải xét số core và quota |
| Downstream/pool metrics | Connection acquire, hàng chờ, timeout, giới hạn tài nguyên | Pool đầy có thể do downstream chậm, không phải pool size đặt sai |

**Trạng thái thread cần đọc kỹ:** BLOCKED thường là đang chờ vào monitor Java; WAITING/TIMED_WAITING có thể là chờ điều kiện, park, sleep hoặc công việc nhàn rỗi. Một thread đang ngủ nhưng **giữ monitor** vẫn có thể làm thread khác BLOCKED. Thread pool có nhiều WAITING khi rảnh là bình thường. RUNNABLE theo JVM không bảo đảm thread đang chạy trên CPU ở mọi thời điểm.

**Bộ nhớ:** heap used tăng chưa chắc leak; xem xu hướng object còn được giữ qua chu kỳ thu gom, tốc độ cấp phát, giới hạn heap và container RSS. Direct buffer, metaspace, stack native và mmap đóng góp vào RSS ngoài heap. Không chạy Full GC cưỡng bức trên production chỉ để có đường cơ sở nếu chưa đánh giá tác động.

**CPU và GC:** CPU JVM cao có thể do mã ứng dụng, JIT compilation, allocation/GC, vòng lặp retry hoặc spin lock. Nếu GC pause ngắn, cần tìm CPU samples/OS throttling trước khi gán lỗi cho GC. Nếu CPU thấp nhưng p99 cao, ưu tiên thời gian chờ I/O, locks, queue, semaphore, pool và remote calls.

## 6. Các lệnh lấy bằng chứng tối thiểu trên JDK 17+

Chạy trên đúng máy/container và trong namespace có thể thấy JVM đích; cần quyền phù hợp. Ghi **PID, timestamp, instance và phiên bản ứng dụng** cùng dữ liệu thu. Các lệnh dưới đây là ví dụ thao tác, không nên chạy dồn dập vô hạn trên production.

~~~bash
# Liệt kê JVM Java mà tài khoản hiện tại có thể thấy.
jcmd -l

# Thay <PID> bằng PID Java đích đã xác minh.
jcmd <PID> VM.command_line
jcmd <PID> Thread.print -l
jcmd <PID> GC.heap_info

# Bắt đầu recording 60 giây; file được ghi khi recording hoàn tất.
jcmd <PID> JFR.start name=diagnosis settings=profile duration=60s filename=incident.jfr

# Sau khi có file JFR, xem tóm tắt bằng JDK tool.
jfr summary incident.jfr
~~~

Lưu ý khi diễn giải:

- **VM.command_line** chứng minh JVM flags và entrypoint thực tế; cần đối chiếu cấu hình container và launch script, không suy đoán từ file cấu hình nguồn.
- **Thread.print -l** hữu ích khi nghi chờ monitor/deadlock; lưu vài bản cách nhau vài giây đúng khoảng lỗi để so stack và lock owner. Không coi mỗi thread ở trạng thái WAITING là thread “kẹt”.
- **GC.heap_info** cho ảnh chụp heap; không đủ riêng lẻ để kết luận leak.
- **JFR.start** thu sự kiện theo thời gian. Profiling/recording vẫn có overhead, dữ liệu có thể chứa tên lớp, đường dẫn, stack hoặc thông tin nhạy cảm; chọn cấu hình, thời lượng, nơi lưu và quyền truy cập phù hợp. Với JDK/cấu hình không hỗ trợ thao tác, dựa vào log/metric sẵn có và ghi rõ hạn chế.
- **VM.native_memory summary** chỉ hữu ích nếu Native Memory Tracking đã được kích hoạt khi khởi động JVM, chẳng hạn tùy chọn -XX:NativeMemoryTracking=summary; không mặc định có dữ liệu.
- Heap dump có thể lớn và gây tác động lớn hơn nhiều so với các lệnh trên. Chỉ thu khi có mục đích rõ, đủ dung lượng, quyền truy cập và đánh giá ảnh hưởng.

Thread dump được tạo bằng tín hiệu hoặc công cụ khác có thể có định dạng/cơ chế khác nhau tùy JDK. Trước khi so sánh, bảo đảm các mẫu đến từ cùng PID và khoảng thời gian sự cố. Đừng dán stack trace có token, URL chứa bí mật hoặc dữ liệu khách hàng vào công cụ chia sẻ công khai.

## 7. Tình huống phân tích đầy đủ: p99 tăng vì giữ monitor quá lâu

*Tình huống giả định dùng để luyện phương pháp; các số đo sau đây minh họa, không phải kết quả benchmark.*

Một API Java có p99 tăng từ 180 ms lên 2.4 s khi traffic tăng 40%. CPU process ổn định 28–35%, GC pause p99 dưới 15 ms. Các request bị chậm tập trung ở endpoint ghi trạng thái đơn hàng. Ban đầu có ba giả thuyết:

- **H1:** luồng xử lý cập nhật giữ một monitor dùng chung trong khi làm thao tác chậm, khiến các request khác nối hàng.
- **H2:** pool kết nối DB cạn gây chờ ở bước acquire.
- **H3:** GC stop-the-world làm các request đồng thời bị trì hoãn.

**Dự đoán cần kiểm:** H1 cho nhiều thread cùng chờ một monitor trong các thread dump và một luồng đang giữ monitor thực hiện công việc chậm. H2 cho acquire time của DB pool tăng, số connection active chạm max, nhiều stack chờ acquire. H3 cho các mốc pause dài trong log/JFR trùng request bị chậm.

**Chuỗi bằng chứng:** Trace cho thấy phần chậm nằm ở đoạn cập nhật trạng thái nội bộ; connection acquire time thấp. Ba thread dump trong cửa sổ lỗi cho thấy nhiều request BLOCKED chờ cùng monitor, một luồng sở hữu monitor đang ngủ/chờ thao tác chậm. GC pause vẫn quá nhỏ để giải thích độ trễ 2.4 s. Điều đó **ủng hộ mạnh H1**, làm yếu H2/H3 trong cửa sổ quan sát. Để tránh đánh đồng “chờ monitor” với nguyên nhân gốc, cần tiếp tục xác minh **vì sao monitor bị giữ lâu**, đường gọi nào nằm trong critical section, và tải nào kích hoạt hiện tượng.

### 7.1 Ví dụ Java 17+ tái hiện riêng cơ chế chờ monitor

Ví dụ tối giản này **cố ý** giữ một monitor trong lúc sleep để tạo dấu vết dễ quan sát. Đây là mô hình về lock contention, **không phải** mã xử lý HTTP hay bằng chứng ứng dụng thực sự ngủ trong critical section.

Lưu tệp thành **LockContentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LockContentionDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch acquired = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                acquired.countDown();
                try {
                    Thread.sleep(20_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-holder");

        Thread waiter = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("waiter acquired lock");
            }
        }, "lock-waiter");

        holder.start();
        acquired.await();  // Bảo đảm holder đã vào synchronized.
        waiter.start();     // Waiter phải đợi holder nhả LOCK.
        waiter.join();
        holder.join();
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac LockContentionDemo.java
java LockContentionDemo
~~~

Trong khoảng 20 giây đầu, mở terminal khác:

~~~bash
jcmd -l
jcmd <PID_CUA_DEMO> Thread.print -l
~~~

Chọn PID theo lớp **LockContentionDemo**, không lấy nhầm JVM khác. Khi bắt đúng thời điểm, thread **lock-holder** thường ở TIMED_WAITING vì Thread.sleep nhưng **vẫn sở hữu monitor**, còn **lock-waiter** ở BLOCKED chờ monitor đó. Sau khoảng 20 giây, chương trình kết thúc và stdout từ chương trình là:

~~~text
waiter acquired lock
~~~

Không khẳng định chính xác vị trí stack, địa chỉ monitor hay PID vì chúng thay đổi theo JDK và lần chạy. CountDownLatch ở đây chỉ giúp bảo đảm luồng holder chiếm monitor **trước khi** luồng waiter bắt đầu; không phải đối tượng tranh chấp đang điều tra.

### 7.2 Chuyển bằng chứng thành giả thuyết nguyên nhân gốc

Giả sử mã ứng dụng có cấu trúc “đọc trạng thái → khóa toàn cục → gọi remote API → cập nhật trạng thái → nhả khóa”. Khi remote API đôi lúc chậm, thời gian giữ khóa tăng; mỗi request mới buộc phải xếp hàng. **Thời gian chờ trong hàng đợi** tăng nhanh theo mức tranh chấp và có thể khiến p99 cao dù CPU và GC vẫn bình thường.

Giả thuyết nguyên nhân gốc: “Critical section giữ monitor chia sẻ bao trùm một lời gọi I/O chậm; độ trễ của dependency kéo dài thời gian giữ khóa, làm nhiều request BLOCKED và đẩy p99 tăng khi concurrency tăng.”

Cách kiểm chứng:
1. Đối chiếu mã đang triển khai với thread dump để xác nhận monitor, lock owner và vị trí gọi I/O thực tế; xác nhận trace/metric của cùng thời điểm.
2. Trên môi trường kiểm thử, phát tải tương tự và cố ý tăng latency dependency trong phạm vi kiểm soát; quan sát số luồng chờ và p99.
3. Thiết kế lại để giảm thời gian giữ khóa, ví dụ thực hiện I/O ngoài critical section **nếu** bất biến dữ liệu và thứ tự cập nhật vẫn đúng; có thể thay monitor toàn cục bằng đồng bộ hóa chi tiết hơn, hàng đợi có giới hạn hoặc điều phối độc lập theo key.
4. Lặp lại với cùng điều kiện, so p50/p95/p99, throughput, trạng thái thread, lỗi dữ liệu và retry. Sửa lock contention mà làm hỏng tính nhất quán không phải sửa thành công.

Nếu bỏ lời gọi chậm khỏi critical section làm số thread BLOCKED giảm và p99 trở về baseline trong tải tương tự, niềm tin về cơ chế tăng đáng kể. Nếu triệu chứng vẫn tồn tại, phải mở lại H2/H3 hoặc giả thuyết mới; không chỉnh sửa báo cáo để ép khớp chẩn đoán ban đầu.

## 8. Tình huống đối chứng: đừng nhầm GC hoặc bộ nhớ với nguyên nhân gốc

Giả sử sau deploy, **heap used**, số lần GC và p99 cùng tăng. Cách kết luận vội là “GC gây chậm, hãy tăng -Xmx”. Một đường nhân quả khác có thể là: thay đổi mã tạo nhiều object tạm → allocation rate tăng → GC hoạt động nhiều → CPU cạnh tranh và tail latency tăng. Trong trường hợp này, **phần cấp phát bất thường trong mã** là điều cần sửa, còn GC là phản ứng của runtime.

Cũng có thể dependency chậm làm request sống lâu hơn, giữ nhiều object/request context trong heap, dẫn đến heap used tăng **sau khi** latency tăng. Dữ liệu cần phân biệt:

| Câu hỏi | Dữ liệu cần |
| --- | --- |
| Pause GC có đủ dài và trùng các request chậm không? | GC log/JFR với timestamp so với request trace |
| Allocation rate tăng trước hay sau lỗi? | JFR allocation samples, throughput, deploy timeline |
| Object được giữ lâu hay chỉ tạo nhiều rồi thu gom? | Heap trend sau chu kỳ GC tự nhiên, class histogram/retained graph khi cần |
| Bộ nhớ tăng nằm ở heap hay ngoài heap? | Heap committed/used so với container RSS, direct/native metrics |
| Tăng heap có thật sự xử lý cơ chế không? | So sánh có kiểm soát và tác dụng phụ: pause, RSS limit, OOMKilled |

Giải pháp có thể là loại bỏ allocation dư, sửa cache không giới hạn, giới hạn concurrency hoặc tối ưu payload. Tăng heap có lúc là điều chỉnh hợp lệ nhưng không tự là bằng chứng về nguyên nhân; còn OOMKilled do container RSS có thể xảy ra khi Java heap chưa chạm -Xmx. Với lỗi rò rỉ, cần chứng cứ **retention tăng qua thời gian trong điều kiện tương đương**, không chỉ một ảnh chụp heap lớn.

## 9. Đánh giá chất lượng bằng chứng

Một “bằng chứng tốt” không phải bằng chứng ủng hộ câu chuyện hấp dẫn nhất. Đánh giá theo sáu trục:

1. **Đúng phạm vi:** Có đến từ instance/PID/version/endpoint chịu tác động hay không?
2. **Đúng thời điểm:** Có thu trong lúc triệu chứng còn xảy ra, với timestamp đồng bộ hay không?
3. **Có đối chứng:** Có so với thời kỳ bình thường, nhóm không lỗi, hoặc tải tương đương?
4. **Có tính độc lập:** Trace, runtime event và pool metric có cung cấp các góc quan sát khác nhau?
5. **Có khả năng bác bỏ:** Quan sát nào sẽ khiến ta bỏ giả thuyết, và đã chủ động tìm nó chưa?
6. **Có liên hệ nhân quả:** Bằng chứng có giải thích được toàn bộ đường đi từ trigger tới tác động, và có kiểm chứng can thiệp khi an toàn?

Xếp mức tin cậy theo cách nói có căn cứ:

- **Thấp:** mới có tương quan hoặc một snapshot; nhiều giả thuyết còn phù hợp.
- **Trung bình:** nhiều mẫu trong đúng khoảng lỗi nhất quán với một cơ chế; đối chứng và bằng chứng phủ định đã xét nhưng chưa thử can thiệp.
- **Cao:** quan sát đa nguồn, cơ chế được chứng minh, thử tái hiện/biện pháp sửa làm thay đổi dấu vết và kết quả theo đúng dự đoán.

Không biến “không thấy log lỗi” thành “không có lỗi”. Logging có thể thiếu, bị lọc, không giữ đủ thời gian hoặc không bao phủ phần chờ. Nếu profiling chỉ lấy mẫu, mẫu không xuất hiện cũng không bảo đảm code path đó không chạy.

## 10. Những sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Chọn nguyên nhân ngay từ tên exception | Chỉ chữa symptom hoặc bỏ qua nguyên nhân phía upstream | Lập timeline và hỏi exception được phát sinh sau cơ chế nào |
| Một biểu đồ tăng cùng lúc ⇒ quan hệ nhân quả | Nhầm hậu quả/thành phần khuếch đại với trigger | So thời gian, stack/trace, đối chứng, thử thay đổi từng biến |
| Chỉ tìm bằng chứng xác nhận giả thuyết thích nhất | Confirmation bias | Ghi trước dự đoán bác bỏ, giữ giả thuyết cạnh tranh |
| Một thread dump ⇒ ứng dụng deadlock | Nhầm chờ hợp lệ hoặc contention với vòng khóa chết | Lấy nhiều mẫu, kiểm tra owner/wait graph, khả năng tiến triển |
| Thấy RUNNABLE ⇒ JVM tiêu CPU tại code đó | Nhầm trạng thái JVM với scheduler CPU | Kết hợp CPU samples, OS metrics, quota và thời lượng |
| Thấy heap tăng ⇒ memory leak | Nhầm allocation/tải tăng với retention | Xem xu hướng, GC, heap/RSS, chuỗi object giữ lại |
| Tăng thread pool/heap hoặc timeout vô điều kiện | Che triệu chứng, thêm hàng đợi và áp lực downstream | Tìm giới hạn thực tế, queueing, resource budget; đo trước/sau |
| Chụp heap dump trên production không chuẩn bị | Pause, tốn disk, rò dữ liệu nhạy cảm | Đánh giá mục đích/chi phí/quyền, ưu tiên tín hiệu nhẹ trước |
| Đo sau rollback rồi kết luận về lúc lỗi | Mất bằng chứng quan trọng | Lưu bằng chứng có timestamp trước thay đổi nếu an toàn |
| “Hết lỗi sau deploy” ⇒ sửa đúng root cause | Có thể chỉ khác tải hoặc thời điểm | Đối chiếu điều kiện, kiểm tra cơ chế dự đoán và regression |

Một phép thử có thể **làm sai giả thuyết nhưng vẫn có ích**: loại trừ được H3 giúp tập trung vào H1/H2. Không sửa code chỉ để chứng minh điều đã tin; để dữ liệu dẫn tới quyết định.

## 11. Mẫu báo cáo sự cố có thể tái sử dụng

~~~text
SỰ CỐ / ẢNH HƯỞNG
- Dịch vụ, phiên bản, instance, người dùng/API bị tác động:
- Mốc bắt đầu/kết thúc, timezone, SLO/error/latency/throughput:
- Baseline và cách lấy mẫu:

QUAN SÁT ĐÃ XÁC MINH
- Triệu chứng:
- Metric/log/trace/JFR/thread dump/GC log (PID, timestamp, nguồn):
- Điều kiện xuất hiện và đối chứng:
- Dữ liệu thiếu/hạn chế đo:

GIẢ THUYẾT
- H1: cơ chế → dấu vết dự đoán → quan sát ủng hộ/bác bỏ
- H2: cơ chế → dấu vết dự đoán → quan sát ủng hộ/bác bỏ
- Những giả thuyết chưa loại trừ:

KẾT LUẬN NHÂN QUẢ
- Trigger:
- Cơ chế gần:
- Nguyên nhân gốc (nếu đủ chứng cứ):
- Yếu tố góp phần:
- Mức tin cậy và căn cứ; điều vẫn chưa chắc chắn:

HÀNH ĐỘNG / KIỂM CHỨNG
- Mitigation và khả năng rollback:
- Sửa nguyên nhân, guardrail, regression test:
- Chỉ số trước/sau trong điều kiện tương đương:
- Kết quả xác nhận; người phụ trách theo dõi:
~~~

Báo cáo trên phải chỉ ra **liên kết giữa từng kết luận và chứng cứ thực sự**, không chỉ liệt kê công cụ đã chạy. Với ảnh chụp, JFR hoặc heap dump có dữ liệu nhạy cảm, lưu ở nơi được kiểm soát, trích dẫn mã tham chiếu phù hợp và tuân thủ chính sách lưu giữ của hệ thống.

## 12. Bài tập tự kiểm tra

**Bài tập A.** Một API có p99 tăng, CPU thấp, nhiều thread ở TIMED_WAITING. Có đủ kết luận là deadlock không? **Không.** Cần xem stack, chờ cái gì, có giữ monitor không, request có tiếp tục tiến triển không, nhiều mẫu thời gian và dấu vết liên quan. TIMED_WAITING có thể chỉ là thread ngủ hợp lệ.

**Bài tập B.** Sau một thay đổi mã, allocation rate tăng 3 lần và GC frequency tăng, nhưng GC pause mỗi lần rất ngắn. Gọi “GC là nguyên nhân gốc” có hợp lý? **Chưa.** Hãy kiểm tra nguồn allocation, CPU mà GC tiêu thụ, latency correlation và code path mới. Cấp phát tăng có thể là cơ chế cần xử lý.

**Bài tập C.** Database pool active chạm max, acquire time tăng, downstream latency cũng tăng trước đó. Chỉ tăng pool size có giải quyết root cause? **Không thể kết luận.** Pool cạn có thể do connection bị giữ lâu vì downstream chậm; tăng pool còn có thể khuếch đại áp lực. Cần nối trace, pool wait, query latency, retry và giới hạn DB.

**Bài tập D.** Một bản canary bỏ I/O khỏi critical section, số thread BLOCKED giảm đáng kể nhưng p99 toàn dịch vụ vẫn cao. Kết luận nào phù hợp? **Một cơ chế contention được cải thiện nhưng chưa giải thích hết triệu chứng.** Kiểm tra route, tỷ lệ traffic canary, yếu tố còn lại và các giả thuyết cạnh tranh.

**Tiêu chí hoàn thành bài:** Với một sự cố thực hoặc mô phỏng, hãy viết được phát biểu có baseline và thời gian, ít nhất hai giả thuyết bác bỏ được, dự đoán dấu vết và phép đo tương ứng, bảng bằng chứng dương/âm, chuỗi cơ chế nhân quả và một cách kiểm chứng sửa lỗi. Một kết luận “chưa đủ dữ liệu” có lập luận rõ còn tốt hơn một nguyên nhân gốc suy đoán.

## Ghi nhớ

- **Triệu chứng** là điểm khởi đầu, **giả thuyết** là cơ chế có thể kiểm chứng, **bằng chứng** là dữ liệu đúng phạm vi và thời gian, còn **nguyên nhân gốc** phải giải thích được chuỗi nhân quả và gợi ra biện pháp ngăn tái diễn.
- Luôn tìm bằng chứng **bác bỏ**, theo dõi những giả thuyết còn sống và đối chiếu ứng dụng–JVM–OS–dependency. Không có một metric đơn lẻ đủ để chẩn đoán mọi vấn đề runtime Java.
- Kết luận chất lượng cao gồm **trigger → cơ chế → triệu chứng → kiểm chứng → hiệu quả sau sửa**; ghi nhận mức tin cậy và điều chưa biết.