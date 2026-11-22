# Phân tích CPU, cấp phát, GC, I/O và khóa trong JFR — Java 17

Java Flight Recorder (JFR) là công cụ ghi nhận sự kiện runtime của JVM để điều tra hiệu năng và hành vi ứng dụng. Trên Java 17, JFR được tích hợp trong JDK, có thể ghi lại các mẫu thực thi CPU, hoạt động cấp phát object, chu kỳ Garbage Collection, thao tác file/socket và sự kiện chờ khóa. Dữ liệu được lưu thành file recording để phân tích bằng Java Mission Control (JMC) hoặc công cụ dòng lệnh `jfr`.

JFR hữu ích khi ứng dụng chậm, CPU tăng cao, GC xảy ra thường xuyên, I/O bị chậm hoặc nhiều thread phải chờ nhau. Thay vì chỉ nhìn một chỉ số tổng hợp, recording giúp liên kết sự kiện với thời điểm, thread và stack trace để tìm khu vực code liên quan.

Bài học tập trung vào cách ghi recording trên Java 17 và cách đọc năm nhóm vấn đề:

- **CPU:** thread nào đang thực thi và stack nào xuất hiện thường xuyên.
- **Cấp phát:** code nào tạo nhiều object và tạo áp lực lên heap.
- **GC:** khi nào thu gom, pause kéo dài bao lâu và heap thay đổi thế nào.
- **I/O:** thao tác file hoặc socket nào mất nhiều thời gian.
- **Khóa:** thread nào bị chặn khi vào monitor hoặc đang park để chờ đồng bộ.

JFR là công cụ quan sát có chi phí thấp trong nhiều cấu hình, nhưng không phải profiler có thể bật mọi event ở mức chi tiết tối đa mà không có ảnh hưởng. Hãy chọn cấu hình phù hợp, ghi trong khoảng thời gian có workload đại diện và đọc kết quả trong ngữ cảnh của ứng dụng.

## 1. JFR cung cấp dữ liệu gì?

JFR ghi lại các **event** xảy ra trong JVM. Mỗi event có thể chứa timestamp, duration, thread, stack trace và các trường riêng theo loại sự kiện. Không phải event nào cũng có đầy đủ tất cả các trường này.

Một số nhóm event quan trọng:

| Nhóm | Event tiêu biểu trong JDK 17 | Dùng để điều tra |
| --- | --- | --- |
| CPU và thực thi | `jdk.ExecutionSample`, `jdk.NativeMethodSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Stack thực thi, CPU load của process/máy và thread. |
| Cấp phát object | `jdk.ObjectAllocationSample`, `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB` | Vị trí cấp phát và áp lực tạo object. |
| Garbage Collection | `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.GCHeapSummary` | Thời gian GC, pause và trạng thái heap trước/sau thu gom. |
| File I/O | `jdk.FileRead`, `jdk.FileWrite` | Thời gian đọc/ghi file, số byte và đường dẫn liên quan. |
| Socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` | Thời gian đọc/ghi socket, host/port và lượng dữ liệu. |
| Monitor và chờ khóa | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` | Tranh chấp monitor, wait/notify và thread park. |

Tên event và mức chi tiết phụ thuộc JDK, cấu hình recording và việc event có được bật hay không. Nếu không thấy event trong file, chưa thể kết luận rằng vấn đề không xảy ra; event có thể chưa được bật hoặc ngưỡng duration đang lọc các sự kiện ngắn.

JFR không chỉ ghi log văn bản. Recording lưu dữ liệu có cấu trúc, có thể lọc theo event, thời gian, thread và stack trace. Điều này giúp phân tích các mối liên hệ như: một method cấp phát nhiều object, dẫn đến young GC thường xuyên, trong lúc request latency tăng.

## 2. Bắt đầu một recording trên Java 17

Trước khi phân tích, cần tạo file recording trong thời gian ứng dụng đang chạy workload cần điều tra.

### 2.1. Ghi recording khi khởi động JVM

Có thể yêu cầu JVM tự bắt đầu recording bằng option:

```bash
java -XX:StartFlightRecording:filename=app.jfr,settings=profile,duration=120s -jar app.jar
```

Trong ví dụ:

- `filename=app.jfr` là file recording đầu ra.
- `settings=profile` chọn cấu hình có nhiều dữ liệu profiling hơn cấu hình mặc định.
- `duration=120s` giới hạn thời gian ghi khoảng hai phút.

Có thể chọn `settings=default` cho recording liên tục hoặc khi cần mức overhead thấp hơn. Cấu hình `profile` thường thu thập thêm dữ liệu hữu ích cho điều tra, nhưng có thể tạo nhiều event và overhead hơn. Hãy thử trên môi trường đại diện trước khi bật thời gian dài trong production.

### 2.2. Bắt đầu recording cho tiến trình đang chạy bằng jcmd

JDK 17 đi kèm công cụ `jcmd`. Tìm PID của tiến trình Java, sau đó bắt đầu recording:

```bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=2m filename=diagnostic.jfr
```

Thay `<pid>` bằng process ID thật. Lệnh yêu cầu JVM bắt đầu recording tên `diagnostic`, dùng cấu hình `profile` và ghi file khi hoàn tất thời lượng.

Kiểm tra recording đang chạy:

```bash
jcmd <pid> JFR.check
```

Nếu cần lấy snapshot trước khi recording tự kết thúc:

```bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
```

Dừng recording theo tên:

```bash
jcmd <pid> JFR.stop name=diagnostic
```

Các lệnh `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop` cần chạy với quyền và user phù hợp để attach vào JVM mục tiêu. Trong môi trường container, cần chạy `jcmd` ở đúng container hoặc trong môi trường có thể attach tới process đó.

### 2.3. Recording liên tục

Với dịch vụ chạy lâu, có thể dùng recording liên tục với cấu hình mặc định và giới hạn dung lượng/thời gian:

```bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=1h maxsize=256m
```

Khi cần điều tra, dump một bản recording:

```bash
jcmd <pid> JFR.dump name=continuous filename=incident.jfr
```

Sau khi không còn cần recording:

```bash
jcmd <pid> JFR.stop name=continuous
```

Giới hạn `maxage` và `maxsize` giúp kiểm soát dữ liệu lưu giữ. Recording liên tục có thể hữu ích khi lỗi chỉ xuất hiện không thường xuyên; tuy nhiên vẫn cần cân nhắc dung lượng, chính sách lưu trữ và quyền truy cập file.

## 3. Đọc recording bằng công cụ JFR

JDK 17 cung cấp command-line tool `jfr` để xem tổng quan và in event từ file recording.

Xem thống kê tổng quát:

```bash
jfr summary diagnostic.jfr
```

Lệnh này cho biết thời gian recording, phiên bản JDK, cấu hình và số lượng event theo loại. Hãy dùng summary trước để biết file có ghi được nhóm event đang cần điều tra hay không.

In các event cụ thể:

```bash
jfr print --events jdk.ExecutionSample diagnostic.jfr
jfr print --events jdk.ObjectAllocationSample diagnostic.jfr
jfr print --events jdk.GarbageCollection diagnostic.jfr
jfr print --events jdk.FileRead diagnostic.jfr
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
```

Đầu ra có thể dài. Với recording lớn, lọc theo event hoặc thời gian, hoặc mở file bằng JMC để xem bảng và biểu đồ trực quan.

### Dùng Java Mission Control

Java Mission Control (JMC) có thể mở file `.jfr` và cung cấp các trang phân tích như:

- **Overview:** tổng quan recording, JVM, heap và các chỉ số chính.
- **Threads:** trạng thái thread và hoạt động theo thời gian.
- **Method Profiling:** stack sample và các method xuất hiện thường xuyên.
- **Memory:** allocation và thông tin heap/GC.
- **Garbage Collections:** các chu kỳ GC, pause và heap summary.
- **I/O:** file/socket event cùng duration.
- **Locks:** monitor contention và thread park.

JMC là công cụ phân tích recording; JFR là cơ chế ghi event trong JVM. Có thể ghi bằng JFR trên máy chủ rồi chuyển file recording đến máy có JMC để phân tích, theo đúng chính sách bảo mật dữ liệu của tổ chức.

## 4. Phân tích CPU bằng ExecutionSample

CPU cao có thể do một vòng lặp tính toán nặng, xử lý dữ liệu lớn, serialize/parse nhiều object, mã native hoặc nhiều thread cạnh tranh CPU. JFR giúp tìm các stack thực thi xuất hiện thường xuyên trong recording.

### 4.1. Event ExecutionSample

`jdk.ExecutionSample` là event lấy mẫu stack của thread đang thực thi. Thay vì ghi lại mọi lời gọi method, JFR lấy mẫu theo thời gian để quan sát code đang chạy.

Ví dụ xem event:

```bash
jfr print --events jdk.ExecutionSample diagnostic.jfr
```

Một sample thường cho biết thread và stack trace tại thời điểm lấy mẫu. Khi nhiều sample có cùng method hoặc cùng nhánh stack, đó là tín hiệu để điều tra khu vực code đó.

**Sampling là phép ước lượng thống kê.** Một method xuất hiện trong nhiều sample có thể đang tiêu thụ nhiều thời gian thực thi, nhưng số sample không phải phép đo chính xác tuyệt đối số lần gọi hoặc thời gian CPU của từng lời gọi.

### 4.2. Đọc stack trace và flame graph

Giả sử recording có nhiều sample với stack:

```text
com.example.ReportService.generate
  com.example.ReportService.aggregate
    com.example.ReportService.normalize
      java.text...
```

Điều này gợi ý nhánh xử lý tạo báo cáo và hàm normalize cần được xem xét. Nếu cùng stack xuất hiện trong nhiều sample, hãy tìm xem có xử lý lặp lại, chuyển đổi dữ liệu hoặc tính toán tốn CPU không cần thiết hay không.

Trong flame graph:

- Trục ngang thể hiện tỷ lệ sample của các stack.
- Chiều dọc thể hiện call stack.
- Một khối rộng cho biết nhánh đó xuất hiện trong nhiều sample.
- Khối ở sâu trong stack có thể là method cụ thể tiêu thụ nhiều thời gian hoặc được gọi rất thường xuyên.

Không chỉ nhìn method có tên nổi bật. Cần phân biệt **self time** (thời gian trong chính method) với **inclusive time** (method cùng các hàm con). Một method ở trên cùng stack có thể xuất hiện nhiều vì nó gọi một hàm con rất tốn CPU.

### 4.3. Phân biệt CPU-bound và thread đang chờ

Execution sample chủ yếu giúp quan sát thread đang thực thi. Nếu thread đang blocked chờ lock, chờ I/O hoặc parked, vấn đề có thể không hiện lên như một hot CPU stack.

Để phân tích đầy đủ:

- Dùng `jdk.ExecutionSample` để tìm stack thực thi.
- Xem `jdk.CPULoad` để quan sát CPU load của JVM và máy.
- Xem `jdk.ThreadCPULoad` khi cần thông tin CPU theo thread và event được bật.
- Xem nhóm I/O và lock để xác định thread đang chờ thay vì thực thi.

Một ứng dụng có CPU thấp nhưng request chậm có thể bị chặn bởi I/O hoặc lock. Không nên cố tối ưu CPU chỉ vì ứng dụng có latency cao.

### 4.4. Cách điều tra CPU có hệ thống

1. Ghi JFR trong lúc CPU cao và workload thực tế đang chạy.
2. Mở trang Method Profiling hoặc lọc `jdk.ExecutionSample`.
3. Nhóm sample theo thread và stack.
4. Tìm nhánh stack có tỷ lệ sample cao.
5. Xem source code tương ứng và kiểm tra thuật toán, vòng lặp, xử lý chuỗi, collection hoặc serialization.
6. Sửa một nguyên nhân cụ thể rồi ghi recording mới để so sánh.

Nếu CPU cao do nhiều thread thực thi song song, hãy phân tích từng nhóm thread. Một method chỉ chiếm tỷ lệ nhỏ ở mỗi thread nhưng xuất hiện trên nhiều thread vẫn có thể là phần chi phí đáng kể của toàn process.

## 5. Phân tích cấp phát object

Nhiều object được tạo liên tục có thể làm tăng allocation rate, khiến young generation đầy nhanh và GC phải chạy thường xuyên. Một số allocation còn tạo áp lực lên CPU và cache dù object sống rất ngắn.

JFR có thể cho biết **object được cấp phát ở đâu** và loại object nào tạo ra áp lực.

### 5.1. ObjectAllocationSample

`jdk.ObjectAllocationSample` là event lấy mẫu allocation. Event có thể chứa class của object, thông tin về kích thước allocation và stack trace liên quan.

Xem event:

```bash
jfr print --events jdk.ObjectAllocationSample diagnostic.jfr
```

Đây là cách hữu ích để tìm allocation hot spot mà không cần ghi mọi lần cấp phát. Sampling có nghĩa recording không chứa một event cho mỗi object; hãy đọc các trường kích thước/weight và tổng hợp theo stack trong JMC, không đếm số event như thể đó là tổng số object được tạo.

### 5.2. TLAB và allocation ngoài TLAB

HotSpot thường cấp phát object nhỏ thông qua **Thread-Local Allocation Buffer (TLAB)**. Mỗi thread có một vùng cấp phát riêng, giúp thao tác cấp phát thông thường nhanh và ít cần đồng bộ.

JFR có thể ghi các event liên quan:

- `jdk.ObjectAllocationInNewTLAB`: allocation gắn với việc cấp phát một TLAB mới.
- `jdk.ObjectAllocationOutsideTLAB`: allocation diễn ra ngoài TLAB.

Các event này có thể giúp điều tra một số tình huống allocation cụ thể, nhưng không nên mặc định rằng chúng đại diện cho mọi object allocation. Với phân tích allocation tổng quát, `jdk.ObjectAllocationSample` thường là điểm bắt đầu phù hợp.

### 5.3. Tìm allocation hot spot

Giả sử stack sample cho thấy nhiều allocation đến từ:

```text
com.example.ApiMapper.toResponse
  java.util.ArrayList...
  java.lang.String...
```

Các câu hỏi cần đặt ra:

- Có tạo collection trung gian cho mỗi request không?
- Có chuyển đổi cùng một dữ liệu nhiều lần không?
- Có tạo nhiều chuỗi tạm trong vòng lặp không?
- Có parse/serialize object lặp lại không?
- Có thể dùng cấu trúc dữ liệu phù hợp hơn hoặc tránh tạo object không cần thiết không?

Không phải allocation nào cũng xấu. Object nhỏ, sống ngắn và được cấp phát hiệu quả là mô hình bình thường của Java. Mục tiêu không phải xóa mọi allocation mà là giảm allocation không cần thiết khi nó tạo áp lực đáng kể.

### 5.4. Allocation khác với retained heap

JFR allocation event giúp tìm nơi **tạo** object. Nó không tự trả lời object nào đang được giữ lại lâu dài và vì sao object đó không được thu hồi.

Phân biệt:

- **Allocation pressure:** nhiều object được tạo trong một đơn vị thời gian.
- **Retained heap:** bộ nhớ của object còn được giữ bởi các tham chiếu sống.
- **Memory leak:** object không còn cần cho nghiệp vụ nhưng vẫn được giữ tham chiếu, khiến live set tăng.

Nếu allocation cao nhưng object sống ngắn, young GC có thể thường xuyên xảy ra mà heap sau GC vẫn ổn định. Nếu heap sau các chu kỳ thu gom tiếp tục tăng, hãy xem thêm heap dump, dominator tree và đường dẫn giữ tham chiếu. Đổi GC không sửa được logic giữ object ngoài ý muốn.

## 6. Phân tích Garbage Collection

GC event giúp xác định tần suất thu gom, thời gian pause, nguyên nhân kích hoạt và biến động heap.

### 6.1. Các event quan trọng

| Event | Thông tin chính |
| --- | --- |
| `jdk.GarbageCollection` | Một chu kỳ GC, duration, tên collector và nguyên nhân liên quan. |
| `jdk.GCPhasePause` | Các pha pause trong quá trình GC. |
| `jdk.GCHeapSummary` | Tóm tắt heap trước hoặc sau một số giai đoạn GC. |
| `jdk.GCPhaseConcurrent` | Pha GC chạy concurrent nếu collector phát ra event tương ứng. |
| `jdk.GCReferenceStatistics` | Thống kê xử lý các loại reference trong GC. |

Tên và số lượng event được ghi phụ thuộc collector và cấu hình JFR. Một collector không có cùng chuỗi pha với collector khác; đừng so sánh tên phase như thể chúng có ý nghĩa giống hệt nhau.

Xem GC event:

```bash
jfr print --events jdk.GarbageCollection diagnostic.jfr
jfr print --events jdk.GCPhasePause diagnostic.jfr
jfr print --events jdk.GCHeapSummary diagnostic.jfr
```

### 6.2. Đọc duration và pause

Với mỗi GC event, hãy xem:

- Thời điểm bắt đầu và duration.
- Tên collector hoặc loại collection.
- Nguyên nhân kích hoạt nếu event cung cấp.
- Pause duration và các pha pause.
- Heap trước và sau GC.

Một GC event có duration dài không nhất thiết toàn bộ thời gian đó là stop-the-world. Một số collector có cả pha concurrent. Khi điều tra request latency, cần xem pause event cụ thể thay vì chỉ lấy duration của toàn chu kỳ.

### 6.3. Phân biệt allocation rate cao và memory leak

Ví dụ A: allocation rate cao

- Young GC xuất hiện thường xuyên.
- Heap giảm đáng kể sau young collection.
- Live set sau GC tương đối ổn định.
- Allocation sample tập trung ở một số method tạo object tạm.

Hướng xử lý: kiểm tra allocation hot spot, object trung gian, chuyển đổi dữ liệu và batch size.

Ví dụ B: live set tăng liên tục

- Heap sau các chu kỳ GC tăng dần.
- Old generation hoặc vùng object sống lâu tăng.
- GC thu hồi ngày càng ít so với lượng heap đang chiếm.
- Ứng dụng có thể giữ cache, collection hoặc listener không được giải phóng.

Hướng xử lý: xem heap dump, dominator tree, reference chain và vòng đời object. JFR giúp xác định thời điểm và xu hướng; heap dump thường cần thiết để tìm object nào giữ tham chiếu.

### 6.4. Tương quan GC với latency

Nếu request latency tăng cùng thời điểm GC pause, hãy kiểm tra:

1. Pause có trùng với spike latency không?
2. Pause xuất hiện thường xuyên hay chỉ một lần bất thường?
3. Heap có đủ headroom trước collection không?
4. Allocation rate có tăng trước khi GC xảy ra không?
5. CPU của GC có cạnh tranh với thread ứng dụng không?
6. Các request bị chậm có nằm trên cùng JVM hoặc cùng instance xảy ra pause không?

Một pause xảy ra cùng thời điểm latency tăng chưa đủ chứng minh GC là nguyên nhân duy nhất. Cần đối chiếu timestamp, request metrics và các sự kiện I/O/lock khác.

## 7. Phân tích File I/O

Các thao tác file có thể chậm do file lớn, storage latency, filesystem, antivirus/scanner, network filesystem hoặc thread pool bị nghẽn.

JFR có thể ghi các event:

- `jdk.FileRead`: đọc dữ liệu từ file.
- `jdk.FileWrite`: ghi dữ liệu ra file.

Xem event:

```bash
jfr print --events jdk.FileRead diagnostic.jfr
jfr print --events jdk.FileWrite diagnostic.jfr
```

Tùy event và cấu hình, thông tin có thể bao gồm path, số byte, duration, thread và stack trace.

### 7.1. Tìm thao tác file chậm

Khi xem event, tập trung vào:

- Duration lớn.
- Đường dẫn file lặp lại.
- Số byte đọc/ghi.
- Thread thực hiện I/O.
- Stack trace gọi tới API file.

Ví dụ stack:

```text
com.example.ExportService.export
  java.nio.file.Files.write
  ...
```

Nếu nhiều event ghi file kéo dài từ cùng một đường dẫn và stack, hãy xem cách export, kích thước dữ liệu, batching và vị trí lưu trữ.

### 7.2. Phân biệt thời gian I/O với thời gian xử lý

Một request có thể mất nhiều thời gian vì:

- Đọc file chậm.
- Parse nội dung sau khi đọc.
- Chờ lock trước khi bắt đầu đọc.
- Ghi kết quả ra file.
- Chờ một dịch vụ khác.

JFR event `FileRead` cho biết hoạt động file được ghi nhận; stack trace cho biết code liên quan. Để hiểu toàn bộ request, cần ghép thời điểm event với các span/log/metrics của ứng dụng nếu có.

### 7.3. Event threshold

Các event I/O thường được cấu hình với ngưỡng duration để tránh ghi quá nhiều thao tác ngắn. Vì vậy, recording có thể chỉ chứa những thao tác vượt threshold.

Nếu không thấy một lần đọc file mà bạn biết đã xảy ra, hãy kiểm tra cấu hình event, threshold và stack trace setting. Không được kết luận file I/O không có vấn đề chỉ từ việc recording không chứa event.

## 8. Phân tích Socket I/O

Một request HTTP chậm có thể do server từ xa, mạng, DNS, proxy, kết nối hoặc ứng dụng đọc/ghi socket. JFR có các event:

- `jdk.SocketRead`: thao tác đọc từ socket.
- `jdk.SocketWrite`: thao tác ghi ra socket.

Xem event:

```bash
jfr print --events jdk.SocketRead diagnostic.jfr
jfr print --events jdk.SocketWrite diagnostic.jfr
```

Thông tin có thể bao gồm host, địa chỉ, port, số byte, timeout, end-of-stream, duration, thread và stack trace tùy event.

### 8.1. Đọc SocketRead

Nếu `SocketRead` có duration dài, thread có thể đã chờ dữ liệu từ peer hoặc network stack. Kiểm tra:

- Host và port đích.
- Số byte nhận được.
- Thread thực hiện read.
- Stack trace gọi tới socket/client API.
- Request có timeout hay không.
- Event có xảy ra cùng thời điểm server từ xa chậm không.

Một read kéo dài không tự chứng minh mạng bị lỗi. Server có thể chưa gửi dữ liệu, ứng dụng có thể đang chờ response, hoặc giao thức có thể yêu cầu đọc tiếp.

### 8.2. Đọc SocketWrite

Nếu `SocketWrite` kéo dài, có thể thread đang chờ khả năng ghi dữ liệu, socket buffer hoặc peer đọc chậm. Hãy kiểm tra kích thước payload, tốc độ gửi, backpressure và trạng thái dịch vụ đích.

### 8.3. Kết hợp với HTTP client metrics

Với ứng dụng dùng HTTP Client hoặc thư viện networking, JFR socket event nên được đối chiếu với:

- Thời gian tổng request.
- Thời gian chờ connection pool.
- DNS lookup và TLS handshake nếu có metrics/event phù hợp.
- Server response time.
- Số byte gửi và nhận.
- Retry, timeout và error rate.

JFR socket event không thay thế distributed tracing. Nếu cần theo dõi một request qua nhiều service, hãy dùng trace/span ID và ghép với thời gian JFR trên từng JVM.

## 9. Phân tích khóa và thread contention

Nhiều thread có thể cùng cần truy cập một tài nguyên được bảo vệ. Nếu một thread giữ lock quá lâu, các thread khác phải chờ, khiến throughput giảm dù CPU không cao.

JFR có một số event quan trọng:

| Event | Dùng để quan sát |
| --- | --- |
| `jdk.JavaMonitorEnter` | Thread bị block khi cố vào synchronized monitor do monitor đang bị thread khác giữ. |
| `jdk.JavaMonitorWait` | Thread gọi `Object.wait()` và chờ notification hoặc điều kiện timeout. |
| `jdk.ThreadPark` | Thread park thông qua cơ chế như `LockSupport.park()`; thường gặp trong synchronizer và concurrent utilities. |

Xem event:

```bash
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
jfr print --events jdk.JavaMonitorWait diagnostic.jfr
jfr print --events jdk.ThreadPark diagnostic.jfr
```

### 9.1. JavaMonitorEnter: tranh chấp synchronized

Khi thread muốn vào khối `synchronized` nhưng monitor đang được thread khác giữ, thread đó phải chờ. `jdk.JavaMonitorEnter` có thể ghi lại sự kiện contention với duration và thông tin monitor/thread liên quan.

Ví dụ code có khả năng gây tranh chấp:

```java
public class SharedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
```

Nếu nhiều thread gọi `increment()` liên tục trên cùng một instance, chúng phải lần lượt vào monitor. Nếu critical section dài hoặc lock được dùng quá rộng, contention có thể tăng.

Khi đọc event, xem:

- Thread nào bị block.
- Duration chờ monitor.
- Stack trace nơi thread cố vào synchronized.
- Loại monitor và thông tin liên quan nếu event cung cấp.
- Thread nào có thể đang giữ monitor lâu; cần đối chiếu thread activity và stack.

Event cho biết thread chờ monitor; để xác định code giữ lock lâu, hãy xem hoạt động của thread sở hữu monitor quanh cùng thời điểm.

### 9.2. JavaMonitorWait: Object.wait không đồng nghĩa lock contention

`Object.wait()` đưa thread vào trạng thái chờ trên monitor. Thread phải sở hữu monitor khi gọi `wait()`; khi wait, nó nhả monitor và chờ được notify/notifyAll hoặc timeout.

`jdk.JavaMonitorWait` giúp quan sát thời gian chờ này. Tuy nhiên, thời gian wait dài không tự động là lỗi contention: đó có thể là hành vi đúng của producer-consumer hoặc một điều kiện nghiệp vụ chưa xảy ra.

Hãy kiểm tra:

- Thread chờ trong method nào.
- Wait có timeout hay không.
- Có thread nào thực hiện notify/notifyAll không.
- Điều kiện vòng lặp quanh wait có đúng không.
- Thời gian chờ có phù hợp với SLA hay không.

### 9.3. ThreadPark: ReentrantLock và các synchronizer

`jdk.ThreadPark` ghi nhận thread park qua cơ chế `LockSupport`. Các cấu trúc như `ReentrantLock`, `Semaphore`, `BlockingQueue` và một số executor có thể sử dụng cơ chế này.

Ví dụ:

```java
import java.util.concurrent.locks.ReentrantLock;

public class LockExample {
    private final ReentrantLock lock = new ReentrantLock();

    public void update() {
        lock.lock();
        try {
            // Critical section
        } finally {
            lock.unlock();
        }
    }
}
```

Nếu nhiều thread tranh chấp `lock`, một số thread có thể park trong lúc chờ. Nhưng `ThreadPark` không đồng nghĩa mọi event đều là lock contention. Thread cũng có thể park có chủ đích để chờ queue, condition, scheduler hoặc một tín hiệu khác.

Cần xem stack trace, blocker/parked class nếu có, thread state và hoạt động của thread khác để hiểu nguyên nhân.

## 10. Phân biệt CPU cao, I/O chậm và lock contention

Ba tình huống có thể khiến request chậm nhưng biểu hiện khác nhau:

| Triệu chứng | Dữ liệu JFR nên xem | Dấu hiệu thường gặp |
| --- | --- | --- |
| CPU-bound | `ExecutionSample`, `CPULoad`, `ThreadCPULoad` | Nhiều sample tập trung ở một số method; CPU process cao. |
| I/O-bound | `FileRead`, `FileWrite`, `SocketRead`, `SocketWrite` | Event I/O duration dài; thread chờ dữ liệu hoặc ghi. |
| Lock contention | `JavaMonitorEnter`, `JavaMonitorWait`, `ThreadPark` | Nhiều thread chờ cùng monitor/synchronizer; CPU có thể thấp. |
| Allocation pressure | `ObjectAllocationSample` và GC events | Allocation sample tập trung ở stack cụ thể; young GC thường xuyên. |
| GC pause | `GarbageCollection`, `GCPhasePause`, `GCHeapSummary` | Pause trùng thời điểm latency tăng; heap thay đổi sau collection. |

Đây là các tín hiệu điều tra, không phải chẩn đoán tự động. Một request có thể đồng thời chịu ảnh hưởng của nhiều nguyên nhân: tạo quá nhiều object, gây GC thường xuyên, rồi chờ I/O hoặc lock.

## 11. Phân tích theo timeline thay vì từng event riêng lẻ

JFR hữu ích nhất khi đặt event vào cùng một dòng thời gian.

Ví dụ một API có latency tăng:

```text
Thời gian  ──────────────────────────────────────────────────────────>

Request bắt đầu
    |
    +-- Allocation tăng trong Mapper
    |
    +-- Young GC pause
    |
    +-- Thread chờ SocketRead
    |
    +-- Response hoàn tất
```

Khi điều tra, hãy hỏi:

1. Event nào bắt đầu trước khi latency tăng?
2. Thread xử lý request có bị pause, block hoặc park không?
3. Có GC pause trùng thời điểm không?
4. Có một stack allocation hoặc CPU hot spot xuất hiện liên tục không?
5. I/O có kéo dài hơn bình thường không?
6. Có nhiều request/thread cùng chờ một monitor không?

Dùng timestamp, thread name/ID và stack trace để liên kết các event. Nếu ứng dụng có distributed tracing, hãy đối chiếu JFR timeline với trace và log có correlation ID.

Đừng chỉ chọn event có duration lớn nhất rồi kết luận đó là nguyên nhân. Hãy xác định event có nằm trên đường xử lý của request chậm hay không.

## 12. Chọn recording settings và threshold

JFR có các cấu hình recording dựng sẵn như `default` và `profile`:

- `default` hướng đến việc ghi liên tục với mức chi phí thấp hơn.
- `profile` thu thập nhiều dữ liệu chi tiết hơn để điều tra hiệu năng trong một khoảng thời gian.

Có thể dùng `jfr configure` để tạo cấu hình tùy chỉnh hoặc dùng JMC để chỉnh event settings. Trong file JFC, mỗi event có thể cấu hình `enabled`, `stackTrace` và `threshold` cùng các thiết lập phù hợp.

Ví dụ một đoạn cấu hình minh họa để bật socket read và chỉ ghi event có duration đủ dài:

```xml
<event name="jdk.SocketRead">
    <setting name="enabled">true</setting>
    <setting name="stackTrace">true</setting>
    <setting name="threshold">10 ms</setting>
</event>
```

Cấu hình này minh họa cách điều chỉnh một event; hãy tích hợp vào file JFC hoàn chỉnh phù hợp với recording. Ngưỡng 10 ms chỉ là ví dụ, không phải giá trị chuẩn cho mọi hệ thống.

Nếu threshold quá cao, các event chậm vừa phải có thể không được ghi. Nếu threshold quá thấp và event xảy ra rất thường xuyên, recording có thể lớn hơn và tạo overhead đáng kể.

### Chọn settings theo câu hỏi điều tra

| Câu hỏi | Event/setting nên chú ý |
| --- | --- |
| Method nào đang tiêu thụ CPU? | Execution sampling và stack traces. |
| Code nào tạo nhiều object? | Allocation sampling và stack traces. |
| GC pause nào làm chậm ứng dụng? | Garbage collection, pause phase và heap summary. |
| File/socket nào có thao tác lâu? | FileRead/FileWrite/SocketRead/SocketWrite, threshold và stack traces. |
| Thread nào chờ synchronized monitor? | JavaMonitorEnter và stack traces. |
| Thread nào đang park? | ThreadPark và thông tin thread/stack liên quan. |

Không cần bật mọi event ở mức chi tiết tối đa cho mọi recording. Bắt đầu với cấu hình phù hợp, sau đó tạo recording tập trung nếu cần điều tra sâu hơn.

## 13. Quy trình điều tra một sự cố hiệu năng

Một quy trình có thể lặp lại:

### Bước 1: xác định triệu chứng

Thu thập số liệu ứng dụng trước khi bật recording:

- CPU process hoặc container.
- Request latency p50/p95/p99.
- Throughput và error rate.
- Heap usage và GC count.
- I/O latency và queue depth.
- Thread count và trạng thái thread nếu có.

### Bước 2: ghi JFR đúng thời điểm

Bắt đầu recording trong lúc workload thể hiện triệu chứng. Chọn `profile` cho một khoảng điều tra ngắn hoặc `default` cho ghi liên tục.

### Bước 3: kiểm tra recording có đủ event

Chạy `jfr summary` để xem event counts và thời gian. Nếu nhóm event cần thiết không xuất hiện, kiểm tra settings, threshold và thời điểm ghi.

### Bước 4: chọn nhóm event theo triệu chứng

- CPU cao: xem ExecutionSample và CPU load.
- Heap/GC bất thường: xem allocation sample, GarbageCollection và heap summary.
- I/O chậm: xem FileRead/Write và SocketRead/Write.
- Thread chờ: xem JavaMonitorEnter, JavaMonitorWait và ThreadPark.

### Bước 5: xác định stack và thread liên quan

Nhóm event theo stack, thread, class, host/path và duration. Tìm một số điểm nóng lặp lại, không chỉ một event đơn lẻ.

### Bước 6: đối chiếu với code và metrics

Mở source code của stack liên quan. So sánh thời điểm event với request metrics, application log và distributed trace.

### Bước 7: thay đổi có mục tiêu và ghi lại

Sửa nguyên nhân có bằng chứng, chạy lại workload tương đương và ghi recording mới. So sánh cùng chỉ số và cùng điều kiện.

## 14. Những giới hạn cần nhớ khi đọc JFR

- **Sampling không phải trace đầy đủ:** ExecutionSample và ObjectAllocationSample là các phép lấy mẫu, không phải bản ghi mọi method call hoặc mọi allocation.
- **Event có thể bị threshold lọc:** không thấy event không chứng minh hoạt động đó không xảy ra.
- **Recording có thể không đại diện:** nếu ghi lúc ứng dụng idle hoặc chỉ trong startup, dữ liệu không phản ánh workload production.
- **Stack trace có chi phí:** bật stack trace cho nhiều event tần suất cao có thể làm recording lớn hơn và tăng overhead.
- **CPU sample không đo trực tiếp latency request:** cần đối chiếu với metrics và tracing.
- **Allocation không phải retained heap:** muốn tìm object còn sống và đường dẫn giữ tham chiếu, có thể cần heap dump.
- **Socket event không giải thích toàn bộ network path:** DNS, TLS, connection pool và server processing có thể cần thêm metrics hoặc trace.
- **ThreadPark không luôn là lỗi:** có thể là cơ chế chờ bình thường.
- **GC event không tự chứng minh memory leak:** cần xem live set, heap dump và vòng đời object.
- **JFR không thay thế observability của ứng dụng:** metrics, logs và distributed tracing vẫn cần thiết.

## 15. Bảo vệ recording và dữ liệu nhạy cảm

File JFR có thể chứa thông tin nội bộ như tên class, method, đường dẫn file, host/port, tên thread, stack trace và một số giá trị sự kiện. Không giả định recording là dữ liệu vô hại chỉ vì nó không phải log nghiệp vụ.

Khi chia sẻ recording:

- Lưu file ở vị trí có quyền truy cập phù hợp.
- Không đưa recording lên dịch vụ công cộng nếu chưa được phép.
- Kiểm tra thông tin nhạy cảm trước khi gửi cho bên khác.
- Giới hạn thời gian và dung lượng recording.
- Tuân thủ chính sách lưu giữ dữ liệu của tổ chức.
- Dùng bản recording đã được lọc hoặc làm sạch khi cần chia sẻ.

Công cụ `jfr scrub` có thể hỗ trợ loại bỏ một số thông tin trong recording theo cấu hình phù hợp; hãy kiểm tra nội dung đầu ra trước khi chia sẻ và không xem thao tác scrub là bảo đảm ẩn danh tuyệt đối.

## 16. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| JFR ghi mọi method call. | ExecutionSample chủ yếu lấy mẫu stack; nó không phải trace đầy đủ từng lời gọi. |
| Không có ObjectAllocationSample nghĩa là không có allocation. | Event có thể chưa bật hoặc recording không lấy được sample trong khoảng ghi. |
| Allocation sample cho biết object nào bị leak. | Nó cho biết nơi tạo object; retained heap và đường dẫn giữ tham chiếu cần phân tích riêng. |
| GC event duration chính là pause time. | Chu kỳ GC có thể chứa pha concurrent; cần xem pause event cụ thể. |
| SocketRead lâu chứng minh mạng có lỗi. | Thread có thể đang chờ peer gửi dữ liệu; cần đối chiếu server, timeout và trace. |
| ThreadPark luôn là lock contention. | Park có thể là cơ chế chờ bình thường trong nhiều synchronizer. |
| Không có JavaMonitorEnter nghĩa là không có tranh chấp lock. | Có thể đang dùng synchronizer dựa trên park, event bị threshold lọc hoặc settings chưa bật. |
| Recording profile không có overhead. | JFR thường có overhead thấp nhưng không bằng không; mức ảnh hưởng phụ thuộc event và workload. |
| Một recording ngắn lúc idle đủ để tìm bottleneck production. | Cần ghi trong workload đại diện và đúng thời điểm có triệu chứng. |
| JFR thay thế metrics, logs và tracing. | JFR bổ sung dữ liệu JVM chi tiết; cần kết hợp observability ở cấp ứng dụng và hệ thống. |

## 17. Bài thực hành

### Bài 1 — ghi recording và đọc summary

Chạy ứng dụng Java 17 có workload trong khoảng hai phút. Dùng `jcmd` bắt đầu recording với `settings=profile`, sau đó chạy `jfr summary`. Ghi lại event nào xuất hiện nhiều nhất.

### Bài 2 — tìm CPU hot spot

Tạo một method có vòng lặp tính toán đủ lâu để xuất hiện trong recording. Xem `jdk.ExecutionSample` và stack trace. Xác định method nào có nhiều sample và giải thích vì sao sample không phải số lần gọi chính xác.

### Bài 3 — quan sát allocation

Tạo workload tạo nhiều object tạm trong vòng lặp. Bật allocation sampling, xem `jdk.ObjectAllocationSample` và nhóm theo stack/class. Thử giảm object trung gian rồi ghi recording mới để so sánh.

### Bài 4 — liên hệ GC với allocation

Tạo workload cấp phát object với tốc độ cao. Xem allocation sample, `jdk.GarbageCollection` và `jdk.GCPhasePause`. So sánh allocation hot spot với tần suất young GC và pause.

### Bài 5 — quan sát File I/O

Tạo chương trình đọc và ghi file có kích thước đủ lớn. Ghi JFR, xem `jdk.FileRead` và `jdk.FileWrite`. So sánh duration, bytes và stack trace.

### Bài 6 — quan sát Socket I/O

Gọi một endpoint thử nghiệm có độ trễ có kiểm soát. Xem `jdk.SocketRead` và `jdk.SocketWrite`. Xác định thread, host/port và duration của thao tác socket.

### Bài 7 — quan sát monitor contention

Tạo nhiều thread cùng gọi một method `synchronized` có thời gian giữ monitor đủ dài. Ghi JFR và xem `jdk.JavaMonitorEnter`. Tìm thread bị chờ và stack trace nơi nó cố vào monitor.

### Bài 8 — phân biệt wait và park

Tạo một ví dụ dùng `Object.wait()` và một ví dụ dùng `ReentrantLock`. Quan sát `jdk.JavaMonitorWait` và `jdk.ThreadPark`. Giải thích vì sao hai event thể hiện các cơ chế chờ khác nhau.

### Bài 9 — phân tích một sự cố tổng hợp

Tạo workload vừa cấp phát object, vừa đọc file và vừa đồng bộ qua lock. Ghi JFR trong lúc tải cao. Dùng timeline để tìm xem CPU, allocation, GC, I/O hay lock là nguyên nhân nổi bật nhất của latency.

## 18. Ghi nhớ nhanh

| Mục tiêu | Event / công cụ |
| --- | --- |
| Ghi recording đang chạy | `jcmd <pid> JFR.start ...` |
| Kiểm tra recording | `jcmd <pid> JFR.check` |
| Dump recording | `jcmd <pid> JFR.dump ...` |
| Dừng recording | `jcmd <pid> JFR.stop ...` |
| Xem tổng quan file | `jfr summary recording.jfr` |
| Xem CPU stack samples | `jdk.ExecutionSample` |
| Xem allocation samples | `jdk.ObjectAllocationSample` |
| Xem chu kỳ GC | `jdk.GarbageCollection` |
| Xem GC pause phases | `jdk.GCPhasePause` |
| Xem heap summary | `jdk.GCHeapSummary` |
| Xem file I/O | `jdk.FileRead`, `jdk.FileWrite` |
| Xem socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` |
| Xem synchronized contention | `jdk.JavaMonitorEnter` |
| Xem Object.wait | `jdk.JavaMonitorWait` |
| Xem thread park | `jdk.ThreadPark` |
| Phân tích trực quan | Java Mission Control (JMC) |

**Nguyên tắc cốt lõi:** Dùng JFR để liên kết event, thread, thời gian và stack trace. ExecutionSample giúp tìm hot stack CPU; allocation sample tìm nơi tạo object; GC event cho biết pause và biến động heap; File/Socket event giúp điều tra I/O; JavaMonitorEnter, JavaMonitorWait và ThreadPark cho thấy các cơ chế chờ. Ghi trong workload đại diện, kiểm tra settings/threshold và kết hợp JFR với metrics, logs cùng tracing trước khi kết luận nguyên nhân.
