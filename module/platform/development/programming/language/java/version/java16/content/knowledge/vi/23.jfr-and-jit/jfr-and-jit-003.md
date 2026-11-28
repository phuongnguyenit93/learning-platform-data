# Tạo bản ghi JFR bằng StartFlightRecording hoặc jcmd JFR.start

Java Flight Recorder (JFR) là công cụ ghi lại các sự kiện trong JVM và ứng dụng Java để phục vụ giám sát, phân tích hiệu năng và điều tra sự cố. Có thể tạo bản ghi ngay khi khởi động ứng dụng bằng tùy chọn **-XX:StartFlightRecording**, hoặc bắt đầu ghi trên một JVM đang chạy bằng lệnh **jcmd JFR.start**.

Cả hai cách đều sử dụng cùng cơ chế JFR. Khác biệt chính nằm ở thời điểm bắt đầu: tùy chọn khởi động phù hợp khi cần ghi từ những giây đầu tiên của ứng dụng; **jcmd** phù hợp khi ứng dụng đã chạy và cần thu thập dữ liệu để điều tra một vấn đề vừa xuất hiện. Bài học này hướng dẫn cách tạo, kiểm tra, dump và dừng recording bằng các lệnh vẫn được hỗ trợ trong Java hiện đại.

## 1. Khi nào cần tạo JFR recording?

JFR thu thập các event có dấu thời gian, phản ánh hoạt động của JVM và ứng dụng. Tùy cấu hình, recording có thể chứa thông tin về:

- CPU và các mẫu thực thi của thread.
- Garbage collection, heap và allocation.
- Thread bị block, contention và đồng bộ hóa.
- I/O, socket, file và hoạt động của hệ thống.
- Exception, class loading và các sự kiện runtime khác.

Một file recording có phần mở rộng **.jfr** lưu dữ liệu để phân tích sau. Có thể mở file bằng JDK Mission Control (JMC) hoặc dùng công cụ dòng lệnh **jfr** đi kèm JDK.

Các tình huống thường cần recording:

- Ứng dụng khởi động chậm và cần quan sát từ giai đoạn startup.
- Độ trễ tăng bất thường trong một khoảng thời gian.
- CPU hoặc GC tăng cao khi ứng dụng đang phục vụ request.
- Cần giữ lại dữ liệu runtime để phân tích sau khi sự cố đã kết thúc.
- Cần recording liên tục để có dữ liệu trước khi sự cố xảy ra.

JFR có thể chạy trong môi trường production với overhead thấp khi chọn cấu hình phù hợp. Tuy nhiên, overhead thực tế phụ thuộc vào event và mức chi tiết được bật.

## 2. Chọn cấu hình recording

JDK cung cấp hai cấu hình JFR tiêu chuẩn trong thư mục **JAVA_HOME/lib/jfr**:

| Cấu hình | Mục đích | Cách sử dụng |
| --- | --- | --- |
| **default.jfc** | Thu thập nhóm sự kiện nền tảng với overhead thấp | Recording liên tục hoặc giám sát dài hạn |
| **profile.jfc** | Thu thập nhiều sự kiện và dữ liệu chi tiết hơn | Profiling trong khoảng thời gian ngắn |

Nếu không chỉ định **settings**, JFR sử dụng cấu hình mặc định **default.jfc**. Cấu hình **profile.jfc** hữu ích khi cần điều tra sâu hơn, nhưng có thể ảnh hưởng hiệu năng nhiều hơn.

Có thể tạo cấu hình JFC riêng khi cần bật hoặc thay đổi một số event. Hãy sao chép cấu hình hiện có rồi chỉnh file riêng, không sửa trực tiếp **default.jfc** hoặc **profile.jfc** trong thư mục JDK. Khi truyền file tùy chỉnh qua **settings**, cung cấp đường dẫn nếu file không nằm trong **JAVA_HOME/lib/jfr**.

Nguyên tắc chọn cấu hình:

- Bắt đầu với **default** khi cần dữ liệu nền hoặc recording dài hạn.
- Chọn **profile** khi đã có câu hỏi điều tra cụ thể và cần thêm chi tiết.
- Chỉ bật event bổ sung khi dữ liệu hiện tại chưa trả lời được câu hỏi.
- Kiểm tra dung lượng file và overhead trước khi duy trì recording lâu dài.

## 3. Tạo recording ngay khi khởi động bằng StartFlightRecording

Tùy chọn **-XX:StartFlightRecording** yêu cầu JVM bắt đầu JFR recording khi ứng dụng khởi chạy. Đây là cách phù hợp khi muốn thu thập dữ liệu từ giai đoạn startup hoặc bảo đảm recording đã hoạt động trước khi tải ứng dụng bắt đầu.

Ví dụ tạo recording profiling trong hai phút:

~~~bash
java -XX:StartFlightRecording=name=StartupProfile,settings=profile,duration=2m,filename=recordings/startup.jfr,dumponexit=true -jar app.jar
~~~

Trong ví dụ:

| Tham số | Ý nghĩa |
| --- | --- |
| **name=StartupProfile** | Đặt tên recording để dễ nhận diện |
| **settings=profile** | Dùng cấu hình profiling có nhiều dữ liệu hơn |
| **duration=2m** | Tự kết thúc recording sau hai phút |
| **filename=recordings/startup.jfr** | Ghi file JFR vào đường dẫn chỉ định khi recording được lưu |
| **dumponexit=true** | Yêu cầu dump recording khi JVM tắt |

Hãy tạo thư mục **recordings** trước khi chạy lệnh. Có thể thay đường dẫn tương đối bằng đường dẫn tuyệt đối để xác định rõ vị trí file trên máy hoặc trong container.

Nếu ứng dụng chỉ cần ghi trong một khoảng thời gian cố định, **duration** giúp recording tự kết thúc. Nếu muốn ghi cho tới khi ứng dụng dừng, có thể bỏ **duration** và bật **dumponexit=true** để lưu dữ liệu khi JVM shutdown.

Ví dụ recording nền với cấu hình nhẹ:

~~~bash
java -XX:StartFlightRecording=name=StartupBaseline,settings=default,duration=5m,filename=recordings/baseline.jfr -jar app.jar
~~~

### Các tham số thường dùng

- **name:** tên recording.
- **settings:** cấu hình JFC, thường là **default** hoặc **profile**.
- **filename:** đường dẫn file sẽ nhận dữ liệu khi recording được dump.
- **duration:** thời lượng recording, dùng hậu tố **s**, **m**, **h** hoặc **d**.
- **delay:** thời gian chờ sau khi JVM khởi chạy trước khi bắt đầu ghi.
- **dumponexit:** dump recording khi JVM shutdown.
- **maxage** và **maxsize:** giới hạn lượng dữ liệu giữ trên đĩa khi **disk=true**.

Với **jcmd**, có thể xem danh sách tùy chọn mà JVM đích hỗ trợ bằng **jcmd <pid> help JFR.start**. Trên JDK 16, đây là cách trực tiếp để kiểm tra cú pháp lệnh runtime; đồng thời có thể đối chiếu với trang hướng dẫn **java** của đúng phiên bản JDK. Cú pháp và tùy chọn chi tiết có thể thay đổi theo phiên bản hoặc bản phân phối.

## 4. Ghi liên tục và giới hạn dung lượng

Đối với ứng dụng chạy lâu dài, có thể bật continuous recording với cấu hình **default** và giới hạn lượng dữ liệu được giữ lại.

~~~bash
java -XX:StartFlightRecording=name=AlwaysOn,settings=default,disk=true,maxage=6h,maxsize=1g,dumponexit=true,filename=recordings/always-on.jfr -jar app.jar
~~~

Các tham số quan trọng:

- **disk=true:** ghi dữ liệu recording ra đĩa trong khi chạy.
- **maxage=6h:** giới hạn tuổi dữ liệu được giữ lại ở mức sáu giờ.
- **maxsize=1g:** giới hạn dung lượng dữ liệu recording ở mức một gigabyte.
- **dumponexit=true:** dump dữ liệu còn lại khi JVM dừng.
- **filename:** xác định file recording đầu ra.

**maxage** và **maxsize** chỉ có ý nghĩa khi recording ghi dữ liệu ra đĩa. Hai giới hạn này giúp kiểm soát dung lượng và thời gian lưu dữ liệu trong recording liên tục. Khi giới hạn được chạm tới, dữ liệu cũ được loại bỏ để giữ dữ liệu gần thời điểm hiện tại.

Continuous recording hữu ích khi chưa biết chính xác sự cố xảy ra lúc nào. Khi sự cố xuất hiện, có thể dump phần dữ liệu đang được lưu để phân tích lại diễn biến trước đó.

Không nên dùng **profile** làm cấu hình luôn bật nếu chưa đánh giá overhead. Cấu hình **default** thường là điểm bắt đầu phù hợp hơn cho recording dài hạn.

## 5. Tạo recording trên JVM đang chạy bằng jcmd JFR.start

Nếu ứng dụng đã khởi động mà chưa có recording, có thể dùng **jcmd** để gửi lệnh chẩn đoán trực tiếp tới JVM. Cách này không cần khởi động lại ứng dụng.

Trước tiên, liệt kê các tiến trình Java:

~~~bash
jcmd -l
~~~

Kết quả hiển thị process ID và main class của các JVM mà công cụ có thể nhìn thấy. Chọn đúng PID của ứng dụng cần ghi.

Ví dụ bắt đầu recording có tên **Incident**:

~~~bash
jcmd 12345 JFR.start name=Incident settings=profile
~~~

Thay **12345** bằng PID thực tế. Nếu không chỉ định **duration**, recording tiếp tục chạy cho đến khi được dừng hoặc JVM kết thúc. Cấu hình mặc định cho **JFR.start** là **default.jfc**; ở đây chỉ định **profile** để thu thập thêm dữ liệu trong phiên điều tra.

Có thể tạo recording có thời lượng giới hạn ngay khi bắt đầu:

~~~bash
jcmd 12345 JFR.start name=IncidentProfile settings=profile duration=2m filename=recordings/incident-profile.jfr
~~~

Recording sẽ tự kết thúc sau hai phút và lưu dữ liệu vào file đã chỉ định.

### Điều kiện để jcmd kết nối được tới JVM

**jcmd** có một số yêu cầu quan trọng:

- Công cụ phải chạy trên cùng máy với JVM đích.
- Người chạy **jcmd** cần có cùng effective user và group ID với người khởi chạy JVM.
- Cần dùng PID thuộc đúng môi trường process namespace.
- Attach mechanism của JVM phải được cho phép; nếu JVM khởi chạy với **-XX:+DisableAttachMechanism**, các công cụ attach như **jcmd** không thể kết nối theo cách thông thường.

Trong môi trường container, **jcmd -l** có thể không hiển thị tiến trình chạy trong Docker process riêng. Khi đó, chạy công cụ bên trong container hoặc xác định PID trong đúng PID namespace.

Nếu không kết nối được, hãy kiểm tra PID, tài khoản thực thi, quyền truy cập, container và tùy chọn attach của JVM trước khi thử lại.

## 6. Kiểm tra recording đang chạy bằng JFR.check

Sau khi bắt đầu recording, dùng **JFR.check** để xem trạng thái:

~~~bash
jcmd 12345 JFR.check
~~~

Có thể lọc theo tên:

~~~bash
jcmd 12345 JFR.check name=Incident
~~~

Lệnh này giúp xác nhận recording có đang hoạt động hay không và xem thông tin nhận diện recording. Có thể yêu cầu hiển thị chi tiết event settings:

~~~bash
jcmd 12345 JFR.check name=Incident verbose=true
~~~

Nếu không nhớ cú pháp của một lệnh JFR trên phiên bản JDK đang chạy, yêu cầu trợ giúp trực tiếp từ JVM:

~~~bash
jcmd 12345 help JFR.start
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
~~~

Đây là cách kiểm tra phù hợp khi làm việc với nhiều phiên bản JDK hoặc bản phân phối khác nhau.

## 7. Dump recording mà không dừng nó bằng JFR.dump

Trong một số tình huống, cần lưu dữ liệu hiện có để phân tích nhưng vẫn muốn tiếp tục recording. **JFR.dump** tạo file snapshot từ dữ liệu đã thu thập tới thời điểm gọi lệnh; recording tiếp tục chạy sau khi dump.

~~~bash
jcmd 12345 JFR.dump name=Incident filename=recordings/incident-snapshot.jfr
~~~

Có thể dump một khoảng thời gian cụ thể nếu cần:

~~~bash
jcmd 12345 JFR.dump name=Incident begin=-10m filename=recordings/incident-last-10m.jfr
~~~

Ví dụ thứ hai lưu dữ liệu từ mười phút trước thời điểm dump tới hiện tại. Tùy chọn thời gian cần được hỗ trợ bởi phiên bản JDK đang dùng; kiểm tra **help JFR.dump** trước khi sử dụng trong script tự động.

**JFR.dump** không dừng recording. Có thể tiếp tục quan sát ứng dụng và dump thêm một snapshot khác nếu sự cố kéo dài hoặc cần so sánh các giai đoạn.

## 8. Dừng recording và lưu file bằng JFR.stop

Khi đã thu thập đủ dữ liệu, dùng **JFR.stop** để kết thúc recording.

~~~bash
jcmd 12345 JFR.stop name=Incident filename=recordings/incident-final.jfr
~~~

Lệnh này dừng recording có tên **Incident** và lưu dữ liệu vào file **incident-final.jfr**.

Cần chú ý: nếu dừng recording mà không chỉ định **filename** trong lệnh **JFR.stop**, dữ liệu có thể bị loại bỏ thay vì được lưu thành file. Hãy luôn chỉ định file đầu ra khi cần giữ recording.

Nếu recording đã được tạo với **duration**, JVM sẽ tự kết thúc nó khi hết thời lượng và ghi file theo cấu hình đã cung cấp lúc bắt đầu. Không cần gọi **JFR.stop** sau khi recording đã tự kết thúc.

### Phân biệt ba lệnh quản lý recording

| Lệnh | Tác dụng | Recording sau lệnh |
| --- | --- | --- |
| **JFR.check** | Xem recording đang chạy | Tiếp tục chạy |
| **JFR.dump** | Ghi snapshot dữ liệu hiện có ra file | Tiếp tục chạy |
| **JFR.stop** | Dừng recording và có thể lưu file | Đã dừng |

Nếu cần lưu snapshot trước khi dừng, có thể gọi **JFR.dump**, sau đó gọi **JFR.stop** để kết thúc và lưu bản cuối cùng.

## 9. Quy trình thực hành từ lúc bắt đầu đến khi phân tích

Có thể thực hiện một phiên profiling trên ứng dụng đang chạy theo quy trình sau.

**Bước 1 — Xác định JVM**

~~~bash
jcmd -l
~~~

Ghi lại PID của ứng dụng. Kiểm tra đúng tiến trình và môi trường đang chạy.

**Bước 2 — Bắt đầu recording**

~~~bash
jcmd 12345 JFR.start name=ApiLatency settings=profile duration=3m filename=recordings/api-latency.jfr
~~~

**Bước 3 — Tạo workload cần quan sát**

Gửi request hoặc chạy tác vụ làm xuất hiện độ trễ cần điều tra. Cố gắng ghi lại thời điểm và loại workload để đối chiếu với timestamp trong recording.

**Bước 4 — Kiểm tra recording**

~~~bash
jcmd 12345 JFR.check name=ApiLatency
~~~

**Bước 5 — Chờ recording kết thúc hoặc dump snapshot**

Nếu recording vẫn đang chạy và cần lưu dữ liệu hiện tại:

~~~bash
jcmd 12345 JFR.dump name=ApiLatency filename=recordings/api-latency-snapshot.jfr
~~~

**Bước 6 — Xác nhận file và xem tổng quan**

~~~bash
jfr summary recordings/api-latency.jfr
~~~

Có thể in một số event cần kiểm tra:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample recordings/api-latency.jfr
~~~

Sau đó mở file bằng JDK Mission Control để phân tích theo thời gian, thread, GC, CPU và các event liên quan tới vấn đề đang điều tra.

Trong thực tế, hãy điều chỉnh tên event theo câu hỏi cần trả lời và danh sách event có trong recording. Không phải mọi event đều được bật trong mọi cấu hình.

## 10. Những lỗi thường gặp khi tạo recording

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy PID | JVM không nằm trong namespace mà **jcmd -l** đang quan sát | Chạy **jcmd** trong đúng máy hoặc container, xác định PID ở đúng namespace |
| Attach thất bại | Sai user/group, thiếu quyền hoặc attach mechanism bị tắt | Dùng cùng tài khoản chạy JVM và kiểm tra **-XX:+DisableAttachMechanism** |
| Không có file sau khi dừng | Dừng recording mà không chỉ định file lưu | Dùng **JFR.stop filename=...** hoặc thiết lập filename từ lúc bắt đầu |
| File quá lớn | Recording kéo dài hoặc cấu hình ghi nhiều event | Chọn **default**, đặt **maxage/maxsize** hoặc giới hạn **duration** |
| Không thấy event mong muốn | Event chưa bật trong JFC settings | Kiểm tra cấu hình bằng **JFR.check verbose=true**, tạo JFC riêng nếu cần |
| Recording có overhead cao | Dùng profile hoặc bật nhiều event chi tiết trong thời gian dài | Bắt đầu bằng **default**, chỉ dùng profile trong khoảng điều tra |
| File không đại diện cho sự cố | Recording bắt đầu sau khi sự cố đã xảy ra hoặc workload không xuất hiện trong khoảng ghi | Dùng continuous recording hoặc điều chỉnh thời điểm và thời lượng ghi |

File **.jfr** có thể chứa thông tin runtime, tên thread, đường dẫn, tham số và một số dữ liệu ứng dụng. Hãy lưu file ở vị trí có quyền truy cập phù hợp và kiểm tra dữ liệu trước khi chia sẻ ra ngoài môi trường dự án.

## 11. Kết luận

Có hai cách phổ biến để tạo JFR recording:

- Dùng **-XX:StartFlightRecording** khi cần bắt đầu ghi cùng lúc JVM khởi chạy, đặc biệt hữu ích cho startup profiling và continuous recording.
- Dùng **jcmd JFR.start** khi ứng dụng đã chạy và cần bắt đầu thu thập dữ liệu ngay trong lúc điều tra.

Sau khi bắt đầu, dùng **JFR.check** để kiểm tra, **JFR.dump** để lưu snapshot mà không dừng recording, và **JFR.stop** để kết thúc đồng thời lưu file. Chọn **default.jfc** cho recording dài hạn, **profile.jfc** cho phiên profiling ngắn, đồng thời đặt giới hạn dung lượng khi cần ghi liên tục.

Nắm vững vòng đời recording giúp thu thập dữ liệu đúng thời điểm, tránh mất file và có đủ bằng chứng để phân tích hành vi JVM trong Java hiện đại.

## Tài liệu tham khảo

- [The java Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [The jcmd Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jcmd.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [The jcmd Command — Java SE 27](https://download.java.net/java/early_access/jdk27/docs/specs/man/jcmd.html)
- [Diagnostic Tools: Flight Recorder — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [Flight Recorder Configurations — Java SE 26](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-configurations.html)
- [JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)

