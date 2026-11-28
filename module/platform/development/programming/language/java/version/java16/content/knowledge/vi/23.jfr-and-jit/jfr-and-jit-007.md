# Đối chiếu allocation sample, GC log và thời gian phản hồi

Khi ứng dụng Java chậm, chỉ nhìn một loại dữ liệu thường chưa đủ để tìm nguyên nhân. Java Flight Recorder (JFR) có thể cho biết class và stack trace nào tạo nhiều object; GC log ghi lại thời điểm, nguyên nhân và thời lượng các hoạt động garbage collection; còn metric hoặc distributed trace của ứng dụng cho biết request mất bao lâu để hoàn thành.

Ba nguồn dữ liệu trả lời ba câu hỏi khác nhau. Allocation sample giúp tìm nơi tạo object, GC log giúp hiểu tác động của garbage collection, còn response time phản ánh trải nghiệm của người dùng. Khi căn chúng trên cùng một dòng thời gian, có thể kiểm tra giả thuyết rằng allocation pressure đang làm tăng GC và góp phần gây latency. Tuy nhiên, sự trùng thời điểm chưa tự chứng minh quan hệ nhân quả.

Bài học này hướng dẫn cách thu thập, căn thời gian và đối chiếu ba nguồn dữ liệu bằng công cụ JFR, unified JVM logging và metric ứng dụng đang được sử dụng trong Java hiện đại.

## 1. Ba nguồn dữ liệu và câu hỏi mỗi nguồn trả lời

| Nguồn | Dữ liệu chính | Câu hỏi trả lời tốt |
| --- | --- | --- |
| JFR allocation sample | Class, weight, thread, stack trace | Object nào được cấp phát và đường code nào tạo chúng? |
| GC log | Loại GC, nguyên nhân, heap trước/sau, pause và thời lượng | JVM thu gom lúc nào, pause bao lâu và heap thay đổi ra sao? |
| Response time metric/trace | Thời lượng request, percentile, route, status | Người dùng hoặc client phải chờ bao lâu? |

Không nguồn nào thay thế hoàn toàn hai nguồn còn lại:

- GC log không chỉ ra chính xác method ứng dụng đã tạo object.
- Allocation sample không cho biết request cụ thể đã chậm bao nhiêu mili giây.
- Response time metric không tự giải thích độ trễ đến từ GC, CPU, lock contention, I/O hay dịch vụ phụ thuộc.

Cần kết hợp chúng để xác định chuỗi sự kiện có khả năng giải thích vấn đề.

## 2. Đọc allocation sample để tìm nguồn cấp phát

JDK 16 bổ sung event JFR **jdk.ObjectAllocationSample**. Event lấy mẫu hoạt động cấp phát và cung cấp những trường quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| **objectClass** | Class của object được chọn làm mẫu |
| **weight** | Trọng số mẫu, dùng ước lượng lượng cấp phát được đại diện |
| **eventThread** | Thread thực hiện hoạt động cấp phát |
| **stackTrace** | Call stack tại vị trí mẫu được ghi nhận |
| **startTime** | Thời điểm event trong recording |

Trường **weight** không phải kích thước chính xác của object được chọn mẫu và số event không phải tổng số object được tạo. Khi tổng hợp weight theo class hoặc stack trace, có thể ước lượng allocation pressure trong khoảng recording.

Ví dụ, một recording có thể cho thấy weight đáng kể của **byte[]** với stack trace đi qua hàm đọc file, hoặc **String** với stack trace đi qua formatter. Đây là đầu mối để xem code nào đang tạo object lặp lại.

Có thể ghi JFR cùng lúc ứng dụng chạy:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile,duration=10m -jar app.jar
~~~

Sau recording, kiểm tra tổng quan và lọc allocation sample:

~~~bash
jfr summary app.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 32 app.jfr
~~~

Trong JDK Mission Control (JMC), dùng các trang Memory và Method Profiling để xem allocation theo class, method, thread và stack trace. Các góc nhìn này giúp tìm hot spot, nhưng cần xem weight và sample count đúng nghĩa của từng chỉ số.

## 3. Đọc GC log bằng unified logging

Từ Java 9, JVM dùng Unified JVM Logging để ghi GC và các thông tin runtime. Trong Java hiện đại, nên dùng tùy chọn **-Xlog**. Những cờ cũ như **-XX:+PrintGCDetails**, **-Xloggc** đã được thay thế hoặc deprecated; không nên dùng chúng cho cấu hình mới.

Ví dụ ghi GC và safepoint log ra file có timestamp, uptime và cơ chế xoay vòng:

~~~bash
java -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Ý nghĩa:

- **gc*** ghi các thông điệp thuộc nhóm GC, bao gồm các tag con.
- **safepoint** ghi thêm thông tin về safepoint.
- **file=logs/gc.log** đặt file đầu ra.
- **time** ghi thời gian thực.
- **uptime** ghi thời gian JVM đã chạy.
- **level,tags** bổ sung mức log và tag để hiểu loại thông điệp.
- **filecount=5,filesize=20M** giới hạn số file xoay vòng và kích thước mỗi file.

Hãy tạo thư mục **logs** trước khi khởi chạy. Nếu cần kiểm tra cú pháp hoặc các tag được hỗ trợ trên đúng runtime, dùng:

~~~bash
java -Xlog:help
~~~

Với ứng dụng đã chạy, không thể thêm tùy chọn khởi động này tùy ý vào JVM hiện tại; cần cấu hình từ lúc launch hoặc dùng cơ chế logging/diagnostic đã được hỗ trợ trong môi trường đó.

### Những trường cần đọc trong GC log

Một dòng GC log minh họa có thể có dạng:

~~~text
[2026-11-27T10:15:12.345+0700][123.456s][info][gc] GC(42) Pause Young (Normal) (G1 Evacuation Pause) 512M->180M(1024M) 12.345ms
~~~

Đây là dòng minh họa để giải thích cấu trúc, không phải output của một JVM thực tế.

- Timestamp cho biết thời điểm sự kiện.
- Uptime cho biết thời gian kể từ khi JVM khởi động.
- **GC(42)** là mã nhận diện chu kỳ GC trong log.
- **Pause Young** mô tả loại hoạt động GC.
- **512M->180M(1024M)** biểu thị heap được dùng trước và sau sự kiện cùng dung lượng heap tương ứng theo định dạng log.
- **12.345ms** là thời lượng pause trong ví dụ.

Khi phân tích, không chỉ đếm số lần GC. Hãy xem loại collection, nguyên nhân, pause time, heap trước/sau và khoảng cách giữa các lần GC. Với collector có các pha concurrent, tổng thời gian một chu kỳ GC không đồng nghĩa với thời gian ứng dụng bị dừng; cần tách các pha pause khỏi công việc concurrent.

## 4. Response time phải lấy từ metric hoặc trace của ứng dụng

JFR và GC log không tự cung cấp đầy đủ response time nghiệp vụ cho mọi ứng dụng. Hãy lấy số liệu từ metric hoặc tracing đang dùng trong service.

Các chỉ số thường cần:

- **Request count/throughput:** số request hoàn thành trong mỗi khoảng thời gian.
- **p50:** độ trễ trung vị.
- **p95:** 95% request hoàn thành không vượt quá giá trị này.
- **p99:** 99% request hoàn thành không vượt quá giá trị này.
- **Error rate:** tỷ lệ request lỗi.
- **Route hoặc operation:** phân biệt endpoint hay tác vụ nào bị ảnh hưởng.

Không chỉ dùng average latency. Trung bình có thể che khuất một nhóm request bị chậm nghiêm trọng; p95 và p99 giúp nhìn rõ phần đuôi phân phối.

Nếu ứng dụng chưa có metric response time, hãy bổ sung instrumentation ở tầng request hoặc dùng framework metrics/tracing hiện hành. Gắn nhãn bằng route template như **GET /orders/{id}**, tránh dùng URL đầy đủ hoặc ID người dùng làm label vì cardinality cao và có thể chứa dữ liệu nhạy cảm.

### Ghi thời lượng request bằng custom JFR event

JFR cho phép ứng dụng định nghĩa event riêng. Ví dụ sau ghi thời lượng xử lý request cùng route và status:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.Request")
@Label("Request")
@Category({"Application", "HTTP"})
class RequestEvent extends Event {
    @Label("Route")
    String route;

    @Label("Status")
    int status;
}
~~~

Ở ranh giới xử lý request:

~~~java
RequestEvent event = new RequestEvent();
event.route = "GET /orders/{id}";
event.begin();

try {
    handleRequest();
    event.status = 200;
} catch (RuntimeException exception) {
    event.status = 500;
    throw exception;
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

Event có duration từ lúc gọi **begin()** tới **end()**. Khi recording bật event tương ứng, JFR lưu thời lượng và các field để có thể xem cùng GC và allocation trên cùng timeline.

Trong ứng dụng thật, cần đặt instrumentation tại ranh giới request phù hợp với cách framework xử lý exception và status. Có thể bổ sung event outcome, nhưng không ghi raw payload, token, thông tin cá nhân hoặc ID có độ cardinality cao. Nếu đã có metrics/tracing chuẩn của framework, hãy tiếp tục dùng chúng làm nguồn response time chính; custom JFR event là lựa chọn bổ sung khi cần đối chiếu trực tiếp trong recording.

## 5. Thu thập ba nguồn trong cùng khoảng thời gian

Để so sánh có ý nghĩa, hãy ghi JFR, bật GC logging và thu metric response time trong cùng một cửa sổ workload.

Ví dụ khởi động JVM:

~~~bash
java -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M -XX:StartFlightRecording=filename=logs/app.jfr,settings=profile,duration=10m -jar app.jar
~~~

Trước khi chạy:

1. Tạo thư mục **logs**.
2. Bảo đảm metric/tracing của service đang hoạt động.
3. Ghi lại phiên bản JDK, GC đang dùng, heap size, CPU/memory limit và cấu hình workload.
4. Chạy workload đại diện trong suốt hoặc trong phần lớn thời gian recording.
5. Ghi lại mốc thời gian bắt đầu/kết thúc và số request hoàn thành.

**profile** thu thập nhiều dữ liệu hơn **default** và phù hợp với phiên điều tra có giới hạn. Nếu cần recording dài hạn, cân nhắc cấu hình **default** và đo overhead trong môi trường triển khai. Không bật thêm event chi tiết nếu chưa có câu hỏi cụ thể cần trả lời.

## 6. Căn thời gian giữa JFR, GC log và response time

Đây là bước quan trọng để tránh gán nhầm nguyên nhân.

### Dùng timestamp và uptime

Trong ví dụ GC logging, **time** ghi thời gian thực còn **uptime** ghi thời gian JVM đã chạy. JFR recording có timestamp của event và thời lượng đối với duration event. Metric/tracing cũng cần có timestamp hoặc bucket thời gian.

Có thể căn theo:

- Cùng máy và cùng JVM: dùng timestamp thực cùng uptime để kiểm tra thứ tự sự kiện.
- Nhiều service hoặc nhiều máy: đồng bộ clock bằng cơ chế thời gian của hạ tầng và kiểm tra timezone.
- Metric tổng hợp theo phút: chuyển event JFR/GC về cùng bucket một phút, hoặc dùng bucket ngắn hơn nếu hệ thống đủ traffic.
- Trace theo request: dùng trace ID ở hệ thống tracing để xác định request cụ thể; không giả định trace ID tự xuất hiện trong JFR nếu chưa instrument để ghi nó.

Không so sánh một p99 của cả mười phút với một GC pause đơn lẻ rồi kết luận pause đó gây ra p99. Hãy thu hẹp khoảng thời gian và route tương ứng.

### Xây dựng timeline chung

Ví dụ minh họa:

| Thời gian | Allocation sample | GC log | Response time |
| --- | --- | --- | --- |
| 10:00–10:01 | Weight ổn định | Young GC ngắn, đều | p95 ổn định |
| 10:01–10:02 | Weight byte[] tăng mạnh ở một stack trace | Young GC dày hơn, pause tăng | p95 bắt đầu tăng |
| 10:02–10:03 | Allocation vẫn cao | Có pause dài trùng thời điểm | p95/p99 tăng rõ |
| 10:03–10:04 | Allocation giảm | GC trở lại nhịp cũ | p95 giảm dần |

Bảng chỉ minh họa một kiểu tương quan có thể quan sát; không phải dữ liệu đo thực tế. Cần kiểm tra thêm workload, throughput, CPU, thread contention và I/O trước khi kết luận.

## 7. Phân tích tương quan và xác định giả thuyết

Có thể bắt đầu bằng ma trận dấu hiệu sau:

| Dấu hiệu quan sát | Giả thuyết cần kiểm tra |
| --- | --- |
| Allocation weight tăng, young GC dày hơn, p95 tăng cùng khoảng thời gian | Allocation pressure có thể làm tăng công việc GC và góp phần gây latency |
| Allocation weight cao nhưng p95 ổn định, GC pause ngắn | Allocation có thể được thu gom hiệu quả; chưa có bằng chứng nó gây latency |
| GC pause dài trùng với request latency spike | Request đang chạy có thể bị ảnh hưởng bởi stop-the-world pause |
| GC pause thấp nhưng p99 tăng | Kiểm tra CPU saturation, lock contention, I/O, thread pool và downstream |
| Heap sau GC tăng dần qua nhiều chu kỳ | Kiểm tra object retention, cache tăng trưởng hoặc memory leak |
| GC hoạt động concurrent lâu nhưng pause ngắn | Phân biệt thời gian GC concurrent với thời gian ứng dụng bị dừng; kiểm tra CPU contention |

### Allocation cao không đồng nghĩa memory leak

Allocation sample chỉ ra nơi object được tạo và lượng cấp phát được ước lượng. Nhiều object ngắn hạn có thể được thu gom bình thường mà không gây leak.

Memory leak liên quan tới object không còn cần thiết nhưng vẫn được giữ tham chiếu. Khi nghi ngờ retention, cần xem heap sau GC, live object, GC root hoặc heap dump. JFR có các event và phân tích khác hỗ trợ điều tra object sống lâu; allocation sample đơn lẻ không đủ chứng minh leak.

### GC pause không giải thích mọi latency spike

Một request có thể chậm do chờ database, gọi HTTP downstream, lock, queue, CPU scheduling hoặc thread pool cạn. Ngoài ra, một số collector thực hiện phần lớn công việc concurrent nên tổng thời gian GC không bằng thời gian dừng ứng dụng.

Hãy kiểm tra xem pause có thực sự chồng lên thời gian xử lý request hay không, và so sánh độ dài pause với mức tăng latency quan sát được. Nếu latency tăng lớn hơn nhiều so với pause, có thể tồn tại thêm nguyên nhân khác.

## 8. Phân tích recording trong JDK Mission Control

Mở file **app.jfr** bằng JDK Mission Control (JMC). Các khu vực thường hữu ích:

- **Memory:** xem heap, allocation, GC event và pause.
- **Method Profiling:** xem method và stack trace liên quan tới allocation hoặc CPU.
- **Threads:** xem hoạt động, trạng thái và stack trace của thread.
- **I/O:** xem các hoạt động I/O có thể làm request chờ.
- **Automated Analysis:** xem các cảnh báo và dấu hiệu cần điều tra.

Chọn cùng khoảng thời gian với GC log và metric response time. Drill down từ một khoảng có p95 tăng tới GC event, allocation site hoặc thread có liên quan.

JMC hỗ trợ xem allocation sites, GC pause và các view về latency thông qua I/O và Threads. Tên tab và cách trình bày có thể thay đổi theo phiên bản JMC. Dùng JFR recording làm nguồn dữ liệu chung, rồi xác minh các event bằng **jfr summary** và **jfr print** khi cần.

## 9. Ví dụ điều tra một endpoint chậm

Giả sử endpoint tạo báo cáo có p95 tăng từ 180 ms lên 900 ms trong một phút.

**Bước 1 — Kiểm tra response time**

Metric cho thấy chỉ route **GET /reports/{id}** tăng p95; các endpoint khác gần như ổn định. Throughput không tăng đáng kể.

**Bước 2 — Kiểm tra GC log**

Trong cùng phút, log cho thấy nhiều young GC hơn và một số pause dài hơn baseline. Heap sau GC vẫn giảm về mức gần cũ, chưa có dấu hiệu rõ ràng về heap retention tăng liên tục.

**Bước 3 — Kiểm tra allocation sample**

JFR cho thấy weight của **byte[]** tăng mạnh. Stack trace thường đi qua hàm serialize report và tạo buffer trung gian.

**Bước 4 — Đặt giả thuyết**

Việc serialize tạo nhiều buffer tạm thời, làm allocation pressure tăng. GC có thể góp phần kéo dài request trong những khoảng pause trùng thời điểm. Tuy nhiên, cần kiểm tra CPU và I/O để loại trừ các nguyên nhân khác.

**Bước 5 — Kiểm tra code và tối ưu có mục tiêu**

Xem serializer có tạo buffer mới ở mỗi phần tử hoặc sao chép dữ liệu nhiều lần không. Thay đổi cách cấp phát hoặc tái sử dụng buffer chỉ khi vòng đời và quyền sở hữu dữ liệu cho phép.

**Bước 6 — Đo lại**

Chạy cùng workload, cùng cấu hình JFR và GC logging. So sánh:

- Allocation weight theo request hoặc theo số request hoàn thành.
- Tần suất GC và pause time.
- p50, p95, p99 của endpoint.
- Throughput, CPU và error rate.

Nếu allocation giảm nhưng p95 không thay đổi, cần tiếp tục điều tra các nguồn latency khác. Nếu cả allocation, GC pause và p95 cùng cải thiện, giả thuyết được củng cố nhưng vẫn nên xác nhận qua nhiều lần chạy.

## 10. Chuẩn hóa dữ liệu khi so sánh trước và sau

Không so sánh tổng weight của hai recording nếu số request hoặc thời lượng workload khác nhau đáng kể.

Có thể chuẩn hóa weight theo số request hoàn thành:

\[
\text{Estimated allocation per request}
=
\frac{\text{Total allocation sample weight}}
{\text{Completed requests}}
\]

Đây là ước lượng từ sampling, không phải phép đo chính xác số byte của từng request. So sánh chỉ có ý nghĩa khi recording settings, workload và môi trường tương đương.

Với GC log, có thể tổng hợp trong cùng bucket thời gian:

- Số lần GC theo loại.
- Tổng pause time trong bucket.
- Pause dài nhất.
- Heap trước/sau các chu kỳ liên quan.
- Thời gian concurrent nếu collector ghi nhận.

Với response time:

- So sánh p50, p95 và p99 theo route.
- Dùng cùng bucket thời gian và cùng đơn vị.
- Ghi request count để biết percentile có đủ mẫu.
- Tách status code hoặc loại request nếu workload khác nhau.

Không dùng một p99 có rất ít request để kết luận xu hướng ổn định. Cần đủ số mẫu và lặp lại thử nghiệm.

## 11. Những lỗi phân tích thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Xem weight như kích thước object chính xác | Weight là trọng số sampling | Tổng hợp theo class/stack và xem là ước lượng |
| Dùng số event sample làm tổng object | JFR không ghi event cho mọi allocation | Dùng weight và JMH/metric phù hợp khi cần đo định lượng |
| Kết luận mọi GC đều làm request dừng | Có pha GC concurrent và pause riêng | Đọc pause event/log cụ thể và căn với request |
| Dùng average latency duy nhất | Có thể che p95/p99 spike | Theo dõi percentile và request count |
| So sánh recording có workload khác nhau | Allocation và latency thay đổi theo input | Chuẩn hóa theo request và chạy workload tương đương |
| Kết luận memory leak từ allocation cao | Allocation không cho biết object có bị giữ lại | Kiểm tra live set, GC root và heap dump |
| Dùng cờ GC logging cũ | Cấu hình mới dựa trên unified logging | Dùng **-Xlog** và cú pháp đúng JDK |
| Coi tương quan là nguyên nhân | Nhiều yếu tố có thể cùng thay đổi | Kiểm tra stack, pause overlap, CPU, lock và I/O |

## 12. Quy trình thực hành

Khi điều tra một đợt tăng latency, có thể thực hiện theo trình tự:

1. Xác định route hoặc operation có p95/p99 tăng và ghi nhận số request.
2. Bật GC unified logging với timestamp và uptime.
3. Ghi JFR với cấu hình phù hợp, bao gồm allocation sample và các event GC/thread cần thiết.
4. Chạy workload đại diện và lưu mốc thời gian.
5. Xếp hạng allocation theo class, weight và stack trace.
6. Đối chiếu GC pause, loại GC, heap trước/sau và thời điểm latency spike.
7. Kiểm tra CPU, lock contention, I/O và downstream nếu GC không giải thích được toàn bộ độ trễ.
8. Đưa ra một giả thuyết cụ thể và thay đổi có mục tiêu.
9. Chạy lại cùng workload, chuẩn hóa allocation theo request và so sánh p50/p95/p99, GC pause, throughput và CPU.
10. Chỉ kết luận khi xu hướng lặp lại và các nguồn dữ liệu cùng hỗ trợ giả thuyết.

## 13. Kết luận

Allocation sample, GC log và response time bổ sung cho nhau. JFR chỉ ra loại object và stack trace tạo allocation; GC log cho biết hoạt động thu gom và pause; metric hoặc trace của ứng dụng cho biết request thực sự chậm đến đâu.

Hãy căn ba nguồn trên cùng timeline, xem percentile theo route, phân biệt GC pause với concurrent work và chuẩn hóa allocation weight theo số request. Allocation tăng, GC dày hơn và p95 tăng cùng lúc là một giả thuyết đáng điều tra, chưa phải bằng chứng cuối cùng. Xác minh thêm CPU, lock, I/O, heap retention và lặp lại workload trước khi kết luận nguyên nhân hoặc đánh giá một thay đổi tối ưu.

## Tài liệu tham khảo

- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [JDK Mission Control 9 User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Unified JVM Logging — OpenJDK Java Launcher Documentation](https://dev.java/learn/jvm/tools/core/java/)
- [Event — Java SE 16 JFR API](https://docs.oracle.com/en/java/javase/16/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Java Flight Recorder API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [JEP 328: Flight Recorder](https://openjdk.org/jeps/328)

