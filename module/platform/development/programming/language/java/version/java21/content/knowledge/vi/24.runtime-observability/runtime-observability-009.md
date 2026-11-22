# Phân tích JFR bằng công cụ tương thích với JDK 21

Java Flight Recorder (JFR) là hệ thống ghi nhận sự kiện và dữ liệu profiling được tích hợp trong JDK. Với ứng dụng chạy trên JDK 21, có thể thu thập recording ngay trong JVM bằng jcmd hoặc tùy chọn lúc khởi động, sau đó phân tích file .jfr bằng JDK Mission Control (JMC) hoặc công cụ dòng lệnh jfr đi kèm JDK.

Quy trình hiệu quả không bắt đầu bằng việc bật mọi event. Hãy xác định vấn đề cần tìm, chọn recording template phù hợp, ghi lại khoảng thời gian có tải đại diện, rồi dùng JMC hoặc jfr để tìm dấu hiệu liên quan đến CPU, allocation, garbage collection, lock contention, thread và I/O.

## 1. JFR, JMC và jfr là ba thành phần khác nhau

Các công cụ có vai trò bổ sung cho nhau:

| Thành phần | Vai trò | Nằm ở đâu? |
|---|---|---|
| Java Flight Recorder (JFR) | Thu thập event có timestamp từ JVM và ứng dụng | Tích hợp trong JDK 21 |
| jcmd | Gửi lệnh chẩn đoán tới JVM đang chạy, bao gồm điều khiển recording | <JAVA_HOME>/bin |
| jfr | Tóm tắt, lọc, in và thao tác file .jfr | <JAVA_HOME>/bin |
| JDK Mission Control (JMC) | Giao diện đồ họa để xem biểu đồ, event, stack trace và kết quả phân tích | Cài đặt riêng, không nằm trong JDK thông thường |

JFR ghi dữ liệu dưới dạng event. Một số event diễn tả khoảng thời gian, ví dụ thời gian chờ monitor hoặc đọc socket; một số event ghi nhận một thời điểm, ví dụ một exception được ném ra; một số event được lấy mẫu định kỳ, ví dụ thông tin CPU hoặc stack của thread.

File .jfr là dữ liệu nhị phân. JMC trình bày dữ liệu bằng bảng và biểu đồ; jfr cho phép kiểm tra nhanh từ terminal hoặc xuất dữ liệu có cấu trúc để xử lý tiếp.

## 2. Chọn công cụ tương thích với JDK 21

Để tránh nhầm phiên bản công cụ và JVM, trước tiên xác định JDK đang chạy ứng dụng:

~~~shell
java --version
jcmd -l
jfr --version
~~~

jcmd -l liệt kê các tiến trình JVM mà công cụ có thể phát hiện. Sau khi xác định PID ứng dụng, có thể hỏi trực tiếp JVM:

~~~shell
jcmd <pid> VM.version
jcmd <pid> VM.command_line
~~~

jcmd cần chạy trên cùng máy với JVM và bằng user có quyền phù hợp với user đã khởi chạy tiến trình. Trong môi trường container, PID hiển thị từ host có thể không phải PID mà công cụ nhìn thấy bên trong container.

Đối với quy trình phân tích JDK 21:

- Dùng jcmd và jfr từ JDK 21 để có bộ lệnh và cách diễn giải khớp với tài liệu của runtime mục tiêu.
- Dùng bản JMC có hỗ trợ đọc JFR recording từ JDK 21. JMC là ứng dụng riêng; phiên bản JMC dùng để mở file không nhất thiết phải được cài trong cùng thư mục JDK đang chạy ứng dụng.
- Nếu mở recording bằng JMC cũ hoặc bằng một công cụ không hiểu event metadata của runtime, một số event hoặc field có thể không hiển thị đúng. Khi đó hãy cập nhật JMC và thử lại bằng jfr của JDK 21 để kiểm tra dữ liệu gốc.
- Không suy ra phiên bản JDK của ứng dụng chỉ từ phiên bản JMC hoặc phiên bản jfr được tìm thấy đầu tiên trên PATH.

JDK 21 đã tích hợp JFR; không cần bật các cờ thương mại cũ hoặc cài agent profiling riêng chỉ để bắt đầu một recording thông thường.

## 3. Chọn recording template: default hay profile?

JDK 21 cung cấp hai cấu hình JFR dựng sẵn trong thư mục <JAVA_HOME>/lib/jfr:

| Template | Mục đích | Khi nên dùng |
|---|---|---|
| default.jfc | Thu thập tập event hữu ích với overhead thấp | Recording liên tục hoặc theo dõi trong thời gian dài |
| profile.jfc | Thu thập nhiều dữ liệu profiling hơn, thường có overhead cao hơn | Điều tra có mục tiêu trong khoảng thời gian ngắn |

default.jfc phù hợp khi cần giữ một cửa sổ dữ liệu để xem lại sau sự cố. profile.jfc phù hợp khi đã biết khoảng thời gian hoặc workload cần phân tích và cần thêm thông tin về method, allocation hoặc thread.

Không nên bật mọi event ở mức chi tiết cao trong thời gian dài. Số lượng event, stack trace và ngưỡng ghi event ảnh hưởng đến dung lượng recording và chi phí thu thập. Hãy bắt đầu với template phù hợp, sau đó chỉ bật thêm event khi câu hỏi điều tra yêu cầu.

## 4. Tạo recording ngay khi khởi động ứng dụng

Có thể bật recording trong lệnh chạy Java bằng tùy chọn -XX:StartFlightRecording:

~~~shell
java -XX:StartFlightRecording=filename=app-profile.jfr,settings=profile,duration=5m -jar app.jar
~~~

Ý nghĩa:

- filename=app-profile.jfr: đường dẫn file recording được ghi khi recording kết thúc.
- settings=profile: dùng cấu hình profiling của JDK.
- duration=5m: tự dừng recording sau năm phút.

Với theo dõi liên tục, có thể dùng default và giới hạn dung lượng/thời gian lưu:

~~~shell
java -XX:StartFlightRecording=filename=app-continuous.jfr,settings=default,maxage=6h,maxsize=512m,dumponexit=true -jar app.jar
~~~

maxage và maxsize giới hạn dữ liệu giữ trên disk cho recording dạng disk. dumponexit=true yêu cầu ghi recording khi JVM shutdown. Giá trị trong ví dụ chỉ minh họa; cần đặt giới hạn phù hợp với dung lượng lưu trữ và chính sách vận hành.

## 5. Bắt đầu recording trên JVM đang chạy bằng jcmd

Khi không thể khởi động lại ứng dụng để thêm JVM option, có thể yêu cầu JVM đang chạy bắt đầu recording:

~~~shell
jcmd <pid> JFR.start name=incident settings=profile duration=5m filename=incident.jfr
~~~

Lệnh này tạo recording tên incident, dùng profile, chạy năm phút và ghi ra incident.jfr. JDK 21 cũng cho phép dùng settings=default cho recording ít chi tiết hơn hoặc recording dài hạn.

Kiểm tra recording đang chạy:

~~~shell
jcmd <pid> JFR.check
jcmd <pid> JFR.check name=incident verbose=true
~~~

Một recording liên tục có thể được dump ra file mà vẫn tiếp tục chạy:

~~~shell
jcmd <pid> JFR.dump name=continuous filename=incident-window.jfr begin=-30m
~~~

begin=-30m chọn dữ liệu trong 30 phút gần nhất. JFR.dump không dừng recording; nó chỉ ghi một bản dump của khoảng dữ liệu được chọn.

Khi muốn dừng recording và ghi file:

~~~shell
jcmd <pid> JFR.stop name=incident filename=incident-final.jfr
~~~

Nếu gọi JFR.stop mà không cung cấp filename, dữ liệu recording có thể bị loại bỏ thay vì được lưu thành file. Hãy chỉ định đường dẫn file khi cần giữ kết quả.

## 6. Kiểm tra file bằng jfr trước khi mở JMC

Sau khi có file recording, hãy kiểm tra nhanh file và thống kê event:

~~~shell
jfr summary incident.jfr
~~~

Summary cho biết thời lượng recording, số lượng event và dung lượng dữ liệu theo event. Đây là bước hữu ích để xác nhận file có dữ liệu, xem template đã ghi những event nào và nhận biết recording có quá ít dữ liệu cho câu hỏi điều tra hay không.

Liệt kê các view và event có trong file:

~~~shell
jfr view all-views incident.jfr
jfr view all-events incident.jfr
jfr view types incident.jfr
~~~

jfr view có thể hiển thị dữ liệu đã tổng hợp theo view hoặc theo event type. Danh sách view và event phụ thuộc vào dữ liệu có trong recording và phiên bản JDK đã ghi nó.

In một nhóm event cụ thể:

~~~shell
jfr print --events jdk.GCPhasePause,jdk.JavaMonitorEnter,jdk.SocketRead incident.jfr
~~~

Hoặc lọc theo category:

~~~shell
jfr print --categories GC incident.jfr
~~~

Có thể xuất JSON để xử lý tiếp:

~~~shell
jfr print --json --events jdk.JavaMonitorEnter incident.jfr
~~~

jfr print mặc định hiển thị nội dung dễ đọc; --events lọc theo tên event, --categories lọc theo category và --stack-depth điều chỉnh độ sâu stack trace. Nếu không lọc, công cụ có thể in lượng dữ liệu rất lớn.

## 7. Phân tích file trong JDK Mission Control

JMC phù hợp khi cần xem quan hệ thời gian và điều hướng qua nhiều nhóm event. Có thể mở file .jfr bằng cách mở JMC rồi chọn file recording, hoặc mở file trực tiếp từ hệ điều hành.

Một quy trình phân tích thường dùng:

1. Mở recording và kiểm tra trang Automated Analysis Results để xem cảnh báo hoặc gợi ý ban đầu.
2. Chọn khoảng thời gian có vấn đề bằng time range navigator. So sánh giai đoạn latency cao với một khoảng bình thường.
3. Mở các trang liên quan như Code, Memory, Garbage Collections, Threads, Locks và I/O.
4. Từ biểu đồ tổng quan, mở event hoặc stack trace cụ thể để tìm method, thread, class hoặc resource liên quan.
5. Đối chiếu thời điểm event với metric bên ngoài như request latency, throughput, CPU, số kết nối và log ứng dụng.

Automated Analysis Results là điểm bắt đầu để phát hiện dấu hiệu, không phải kết luận cuối cùng. Một cảnh báo cần được kiểm tra trong event và stack trace gốc, sau đó xác nhận bằng workload hoặc metric phù hợp.

## 8. Phân tích CPU và method execution

Khi CPU cao hoặc throughput thấp dù không có nhiều thời gian chờ I/O, hãy bắt đầu từ trang Code và các execution sample:

- Xem method nào xuất hiện thường xuyên trong các sample.
- Kiểm tra stack trace để tìm đường gọi dẫn đến method nóng.
- Phân biệt thời gian thực thi CPU với thời gian thread chờ lock, socket, file hoặc park.
- So sánh theo thread để tìm worker hoặc request path tiêu tốn CPU bất thường.

Execution sample là mẫu tại các thời điểm, không phải bộ đếm chính xác mọi lần gọi method. Một method xuất hiện nhiều trong sample là dấu hiệu đáng điều tra; cần xác nhận bằng profile khác hoặc benchmark trước khi tối ưu.

Nếu thread có nhiều khoảng thời gian không xuất hiện event chờ và CPU process cao, phần thời gian đó có thể là thời gian chạy code hoặc CPU-bound. Nếu process CPU thấp nhưng request chậm, hãy kiểm tra thread stalling, I/O, lock và downstream dependency.

## 9. Phân tích allocation và garbage collection

Khi nghi ngờ áp lực bộ nhớ hoặc GC, mở các trang Memory và Garbage Collections:

- Xem allocation theo class, thread và stack trace để tìm nơi tạo nhiều object.
- Phân biệt allocation rate cao với live set cao; tạo nhiều object tạm không đồng nghĩa với giữ nhiều object lâu dài.
- Xem tần suất collection, thời lượng pause và tổng thời gian ứng dụng bị pause.
- Kiểm tra allocation spike có trùng thời điểm latency tăng hay không.
- Nếu nghi ngờ object bị giữ lại, cần điều tra đường tham chiếu và live set thay vì chỉ tăng heap.

Một số event JFR hữu ích trong JDK 21:

| Event | Dùng để xem |
|---|---|
| jdk.GCPhasePause | Các pha pause của GC |
| jdk.ObjectAllocationInNewTLAB | Allocation trong TLAB |
| jdk.ObjectAllocationOutsideTLAB | Allocation ngoài TLAB |
| jdk.ThreadAllocationStatistics | Thống kê allocation theo thread |

Khi đo latency, không bật Heap Statistics một cách tùy tiện. Tính năng này có thể kích hoạt old/full GC ở đầu và cuối recording, làm thay đổi hành vi pause mà bạn đang muốn đo. Chỉ bật khi câu hỏi điều tra thực sự cần heap statistics hoặc live set và chấp nhận chi phí đó.

## 10. Phân tích lock, thread và I/O

JFR có thể ghi các event mô tả thời gian thread bị chặn hoặc chờ:

| Event | Câu hỏi cần trả lời |
|---|---|
| jdk.JavaMonitorEnter | Thread chờ bao lâu để lấy intrinsic monitor? |
| jdk.JavaMonitorWait | Thread chờ trên monitor trong bao lâu? |
| jdk.ThreadPark | Thread bị park trong thời gian nào và stack trace nào? |
| jdk.ThreadSleep | Thread đang sleep trong khoảng thời gian nào? |
| jdk.SocketRead / jdk.SocketWrite | Thread chờ đọc/ghi socket bao lâu? |
| jdk.FileRead / jdk.FileWrite | Thao tác file chiếm bao nhiêu thời gian? |

Nếu JavaMonitorEnter có thời lượng lớn trên đường xử lý quan trọng, kiểm tra lock instance và stack trace của thread đang chờ. Nếu SocketRead hoặc SocketWrite chiếm nhiều thời gian, xác định host, port, lượng dữ liệu và dependency từ xa liên quan. Nếu nhiều thread park, hãy xác định chúng đang chờ queue, semaphore, future hay một cơ chế đồng bộ khác.

JFR chỉ ghi event thỏa điều kiện cấu hình và ngưỡng thời lượng. Trong cấu hình thông thường, nhiều event ngắn có thể không được ghi. Vì vậy, không thấy event không chứng minh rằng thao tác đó chưa từng xảy ra. Nếu cần bắt các lần chờ ngắn hơn, hãy điều chỉnh threshold trong recording template và đánh giá overhead trước khi triển khai rộng.

## 11. Quy trình phân tích theo một câu hỏi cụ thể

Thay vì xem toàn bộ recording không có mục tiêu, hãy bắt đầu bằng một giả thuyết:

| Triệu chứng | Nơi nên xem trước | Dấu hiệu cần tìm |
|---|---|---|
| CPU cao, throughput giảm | Code, Threads | Execution sample tập trung ở một số method hoặc thread |
| Latency tăng, CPU thấp | Threads, I/O, Locks | Thread chờ socket, file, monitor, park hoặc downstream |
| GC pause hoặc allocation pressure | Memory, Garbage Collections | Pause dài, tổng pause tăng, allocation site lớn |
| Thread bị block nhiều | Threads, Locks | Monitor contention, stack trace và lock instance |
| Socket call chậm | I/O | Socket read/write duration, host/port và lượng dữ liệu |
| Bộ nhớ tăng theo thời gian | Memory | Live set, class tăng trưởng và đường giữ tham chiếu |

Quy trình lặp lại:

1. Ghi nhận thời điểm bắt đầu triệu chứng và metric bị ảnh hưởng.
2. Tạo recording bao phủ cả khoảng trước, trong và sau triệu chứng.
3. Dùng Automated Analysis để tìm vùng đáng chú ý.
4. Khoanh vùng event, thread và stack trace trong đúng khoảng thời gian.
5. Đưa ra giả thuyết nguyên nhân và kiểm tra bằng metric hoặc recording thứ hai.
6. Sau khi thay đổi code/cấu hình, ghi recording mới dưới workload tương đương để so sánh.

Không kết luận một event có thời lượng cao là nguyên nhân gốc nếu chưa xác định nó ảnh hưởng đến request hoặc thread quan trọng như thế nào.

## 12. Tạo recording settings riêng khi cần event chi tiết

Nếu template default hoặc profile chưa bật event cần thiết, có thể tạo file .jfc tùy chỉnh. Không sửa trực tiếp các file cấu hình mặc định trong JDK; hãy tạo file mới dựa trên cấu hình có sẵn:

~~~shell
jfr configure --input /path/to/jdk/lib/jfr/profile.jfc --output app-diagnostics.jfc
~~~

Thay đường dẫn ví dụ bằng file profile.jfc trong thư mục lib/jfr của JDK 21 đang dùng.

Có thể xem cú pháp và event setting:

~~~shell
jfr help configure
jfr metadata --events jdk.JavaMonitorEnter incident.jfr
~~~

Khi đã có file cấu hình, dùng nó lúc bắt đầu recording:

~~~shell
jcmd <pid> JFR.start name=locks settings=./app-diagnostics.jfc duration=3m filename=locks.jfr
~~~

Event setting có thể cấu hình bật/tắt, threshold và stack trace tùy loại event. Chỉ bật thêm những event phục vụ câu hỏi điều tra. Ghi càng nhiều event và stack trace càng chi tiết có thể làm recording lớn hơn và tăng overhead.

## 13. Bảo vệ và chia sẻ file recording

Recording có thể chứa tên thread, tên class, stack trace, thông tin môi trường, URI hoặc dữ liệu ứng dụng tùy event được bật. Hãy xem .jfr như dữ liệu chẩn đoán nội bộ:

- Lưu file ở vị trí có quyền truy cập phù hợp.
- Không gửi recording ra ngoài khi chưa kiểm tra dữ liệu nhạy cảm.
- Chỉ thu thập event cần thiết và giới hạn thời gian/dung lượng recording.
- Nếu cần loại bỏ event hoặc thread trước khi chia sẻ, có thể tạo bản đã lọc bằng jfr scrub:

~~~shell
jfr scrub --exclude-threads "worker-secret-*" incident.jfr incident-scrubbed.jfr
~~~

jfr scrub lọc event theo event name, category hoặc thread. Đây không phải công cụ bảo đảm ẩn danh mọi chuỗi nhạy cảm; cần mở và kiểm tra file đầu ra trước khi chia sẻ.

## 14. Các lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| jcmd không thấy process | Khác user, PID ở container khác hoặc JVM không cùng máy | Chạy bằng user phù hợp, xác định PID trong đúng môi trường |
| Không thấy event cần tìm | Template không bật event hoặc threshold quá cao | Kiểm tra jfr summary, jfr metadata và cấu hình recording |
| File .jfr quá lớn | Recording quá dài hoặc profile bật nhiều event | Dùng duration, maxage/maxsize và template phù hợp |
| JMC không hiển thị event như mong đợi | JMC cũ hoặc không tương thích metadata/event schema | Dùng bản JMC hỗ trợ JDK 21; đối chiếu bằng jfr cùng JDK |
| Kết quả không tái hiện vấn đề | Recording không bao phủ đúng thời điểm hoặc tải khác biệt | Ghi lại trong workload và khoảng thời gian đại diện |
| Phân tích latency nhưng số pause bất thường | Heap Statistics kích hoạt old GC | Tắt Heap Statistics nếu không điều tra live set |
| Không thể chia sẻ file recording | File chứa thông tin nội bộ | Dùng jfr scrub, kiểm tra lại file và tuân thủ chính sách dữ liệu |

## 15. Checklist phân tích JFR trên JDK 21

- [ ] Xác định phiên bản JVM mục tiêu và dùng jcmd/jfr từ JDK 21.
- [ ] Dùng JMC có hỗ trợ recording của JDK 21 nếu cần giao diện đồ họa.
- [ ] Chọn default.jfc cho theo dõi dài hạn hoặc profile.jfc cho profiling ngắn hạn.
- [ ] Ghi recording bao phủ đúng thời gian và workload có vấn đề.
- [ ] Kiểm tra file bằng jfr summary trước khi phân tích sâu.
- [ ] Dùng jfr view, jfr print và bộ lọc event để khoanh vùng dữ liệu.
- [ ] Trong JMC, bắt đầu từ Automated Analysis Results rồi đi sâu vào Code, Memory, GC, Threads, Locks và I/O.
- [ ] Phân biệt CPU execution với thời gian chờ I/O, lock hoặc park.
- [ ] Không bật Heap Statistics khi đo latency nếu không cần điều tra live set.
- [ ] Điều chỉnh event threshold khi cần bắt các thao tác ngắn và đánh giá overhead.
- [ ] Bảo vệ file .jfr và kiểm tra bản đã scrub trước khi chia sẻ.
- [ ] So sánh recording trước/sau thay đổi dưới workload tương đương.

JFR cung cấp bằng chứng về điều JVM và ứng dụng đã làm trong một khoảng thời gian. jcmd giúp thu thập dữ liệu từ tiến trình đang chạy, jfr giúp lọc và kiểm tra recording, còn JMC giúp nhìn thấy mối liên hệ giữa event, thread, code, memory và I/O. Dùng đúng phiên bản công cụ, đúng template và một câu hỏi điều tra rõ ràng sẽ giúp phân tích runtime trên JDK 21 có thể lặp lại và đưa ra quyết định dựa trên dữ liệu.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java SE 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle Java SE 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 21 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [Oracle JDK Mission Control 9 — User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)
