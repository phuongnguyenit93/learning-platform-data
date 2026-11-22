# jfr view và các bảng tổng hợp sự kiện hữu ích

Java Flight Recorder (JFR) ghi lại các sự kiện của JVM và ứng dụng trong một file `.jfr`. Trên Java 21, lệnh `jfr view` có thể tổng hợp dữ liệu sự kiện thành các bảng ngay trên command line. Nhờ đó, có thể nhanh chóng xem phương thức tiêu thụ CPU nhiều, vị trí cấp phát object, thời gian GC pause, monitor contention hoặc virtual thread bị pin mà chưa cần mở công cụ phân tích đồ họa.

`jfr view` không thay thế dữ liệu sự kiện gốc. Mỗi bảng là một góc nhìn tổng hợp được xây dựng từ những event có trong recording. Nếu recording không bật một event cần thiết, bảng có thể thiếu dữ liệu hoặc không đủ căn cứ để kết luận. Quy trình hiệu quả là bắt đầu bằng summary, chọn view theo giả thuyết, sau đó kiểm tra event và stack trace chi tiết bằng `jfr print` hoặc JDK Mission Control.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Tạo và kiểm tra một JFR recording trên Java 21.
- Phân biệt `jfr summary`, `jfr view` và `jfr print`.
- Liệt kê các view và event type có trong recording.
- Chọn bảng tổng hợp phù hợp để điều tra CPU, allocation, GC, thread, lock và I/O.
- Đọc số liệu dạng count, sample, duration và percentage mà không diễn giải quá mức.
- Dùng `--verbose`, `--width`, `--truncate` và `--cell-height` để hiểu và định dạng kết quả.
- Xác minh kết quả tổng hợp bằng event chi tiết, stack trace và bối cảnh tải.

## 1. `jfr view` có sẵn trong Java 21

JFR View là một tính năng của JDK 21. Có thể dùng nó với file recording thông qua công cụ `jfr`, hoặc xem dữ liệu gần thời gian thực của một JVM đang chạy thông qua `jcmd`.

Với file recording:

```bash
jfr view gc-pauses recording.jfr
```

Với JVM đang chạy:

```bash
jcmd <pid> JFR.view gc-pauses
```

Thay `<pid>` bằng process ID của JVM cần quan sát. Cần có quyền attach phù hợp và JVM phải cho phép công cụ chẩn đoán kết nối. Với phân tích sau sự cố, file `.jfr` giúp giữ lại dữ liệu để chia sẻ và kiểm tra lại.

`jfr view` trình bày dữ liệu đã được tổng hợp theo view. Một view có thể nhóm nhiều event thành các hàng theo phương thức, class, thread, loại sự kiện hoặc khoảng thời gian. Tên và các cột cụ thể phụ thuộc view và phiên bản JDK.

## 2. Phân biệt summary, view và print

Ba lệnh thường được dùng liên tiếp nhưng phục vụ các câu hỏi khác nhau:

| Lệnh | Mục đích | Khi nào dùng |
|---|---|---|
| `jfr summary recording.jfr` | Thống kê recording, số event theo loại và kích thước dữ liệu | Kiểm tra recording có dữ liệu gì và event nào chiếm nhiều |
| `jfr view <view> recording.jfr` | Tổng hợp event thành bảng có ý nghĩa chẩn đoán | Tìm nhóm phương thức, class, thread hoặc event đáng chú ý |
| `jfr print ... recording.jfr` | In các event riêng lẻ cùng field và stack trace | Xác minh một hàng tổng hợp bằng các event gốc |

Ví dụ:

```bash
jfr summary recording.jfr
jfr view hot-methods recording.jfr
jfr print --events jdk.ExecutionSample --stack-depth 20 recording.jfr
```

Không nên đọc toàn bộ file bằng `jfr print` ngay từ đầu nếu recording lớn. Hãy dùng `summary` để hiểu phạm vi, `view` để thu hẹp vấn đề, rồi `print` với filter để kiểm tra chi tiết.

### 2.1. Đọc `jfr summary`

`jfr summary` thường hiển thị thông tin tổng quan như khoảng thời gian recording, dung lượng file và bảng số lượng event theo loại. Ví dụ minh họa:

| Event type | Count | Ý nghĩa khi xem summary |
|---|---:|---|
| `jdk.ExecutionSample` | 12.400 | Có các mẫu stack của thread đang thực thi |
| `jdk.ObjectAllocationSample` | 1.850 | Có mẫu cấp phát object |
| `jdk.GCPhasePause` | 24 | Có dữ liệu các pha pause của GC |
| `jdk.JavaMonitorEnter` | 310 | Có event về việc chờ vào intrinsic monitor |

Các số trong bảng chỉ minh họa cách đọc, không phải kết quả của một recording thật. Count là số event được ghi nhận, không phải lúc nào cũng bằng số lần thao tác nghiệp vụ. Ví dụ, `ExecutionSample` là sampling; một sample không tương đương một lần gọi phương thức.

Nếu event cần phân tích không xuất hiện trong summary, hãy kiểm tra settings và thời điểm recording trước khi kết luận ứng dụng không có hiện tượng đó.

## 3. Khám phá view và event type

JDK 21 cung cấp nhiều view dựng sẵn. Danh sách có thể xem theo recording:

```bash
# Liệt kê các view có thể dùng
jfr view all-views recording.jfr

# Liệt kê event type trong recording
jfr view types recording.jfr

# Liệt kê tất cả event được ghi
jfr view all-events recording.jfr
```

Tên view khả dụng có thể thay đổi theo JDK vendor, phiên bản và event metadata. Một số view chỉ có ý nghĩa khi recording chứa các event tương ứng. Nếu chưa biết view nào phù hợp, dùng:

```bash
jfr --help view
jfr view all-views recording.jfr
```

`jfr view types` giúp kiểm tra tên event type để dùng làm đối số view hoặc filter của `jfr print`. `jfr view all-events` hiển thị dữ liệu event đã ghi; với recording lớn, output có thể rất dài.

## 4. Các view hữu ích để điều tra CPU và phương thức nóng

### 4.1. `hot-methods`

`hot-methods` tổng hợp các method xuất hiện nhiều trong execution samples. Đây là điểm bắt đầu hữu ích khi nghi ngờ CPU bị tiêu thụ bởi một số call path.

```bash
jfr view hot-methods recording.jfr
```

Bảng thường cho biết method, số sample và tỷ lệ sample. Ví dụ minh họa:

| Method | Samples | Percent |
|---|---:|---:|
| `com.example.JsonParser.parse` | 4.200 | 35% |
| `com.example.OrderService.calculate` | 2.160 | 18% |
| `java.util.HashMap.getNode` | 960 | 8% |

Tỷ lệ trong bảng là tỷ lệ trên các sample được ghi nhận theo cách view định nghĩa; không được hiểu máy móc là phần trăm CPU tuyệt đối của toàn máy hoặc thời gian chạy chính xác của method. Hãy kiểm tra stack trace, thread và CPU load cùng khoảng thời gian để xác định call path có thực sự là bottleneck.

Nếu method xuất hiện nhiều trong `hot-methods`, bước tiếp theo có thể là:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 30 recording.jfr
```

Lọc thêm theo thời gian hoặc thread bằng công cụ phù hợp nếu recording chứa nhiều dữ liệu. JDK Mission Control có thể giúp chọn khoảng thời gian và xem stack theo cách trực quan hơn.

### 4.2. `cpu-load` và `cpu-load-samples`

Các view CPU giúp đặt execution samples vào bối cảnh tải CPU. `cpu-load` và `cpu-load-samples` có thể cung cấp góc nhìn về tải CPU mà recording thu thập được.

```bash
jfr view cpu-load recording.jfr
jfr view cpu-load-samples recording.jfr
```

CPU load thấp cùng latency cao thường gợi ý ứng dụng đang chờ I/O, lock hoặc tài nguyên bên ngoài. CPU load cao cùng nhiều execution sample tập trung ở một số call path có thể gợi ý CPU-bound workload. Đây chỉ là hướng điều tra; cần đối chiếu request rate, container throttling và dữ liệu thread để xác nhận.

## 5. Các view hữu ích để phân tích allocation và object

### 5.1. `allocation-by-site`

`allocation-by-site` nhóm các mẫu cấp phát theo nơi phát sinh, thường dựa trên class và stack trace. Dùng khi nghi ngờ một call path tạo quá nhiều object.

```bash
jfr view allocation-by-site recording.jfr
```

Hãy tìm các site có tổng lượng cấp phát hoặc tỷ lệ sample lớn. Sau đó kiểm tra:

- Call site có nằm trong vòng lặp nóng không?
- Object có thực sự cần được tạo ở mỗi lần gọi không?
- Allocation có tương ứng với request rate hay tăng bất thường?
- Object chỉ sống ngắn hay được giữ lại trong cache, queue hoặc collection?

Allocation view thường dựa trên event lấy mẫu như `jdk.ObjectAllocationSample`, vì vậy không phải phép đếm chính xác mọi object được tạo. Dùng nó để tìm nơi đáng chú ý, không dùng sample count làm tổng allocation chính xác nếu view không công bố rõ cách ước lượng.

### 5.2. `allocation-by-class` và `allocation-by-thread`

Hai view này giúp đổi góc nhìn:

```bash
jfr view allocation-by-class recording.jfr
jfr view allocation-by-thread recording.jfr
```

- `allocation-by-class` giúp nhận diện loại object được cấp phát nhiều theo dữ liệu ghi nhận.
- `allocation-by-thread` giúp tìm thread hoặc nhóm công việc tạo ra nhiều allocation.

Nếu một class chiếm tỷ trọng cao, không có nghĩa class đó là lỗi. Ví dụ `byte[]`, `char[]` hoặc buffer có thể tăng theo lưu lượng request bình thường. Hãy so sánh với throughput, kích thước payload và thời gian sống của object.

### 5.3. `object-statistics` và memory leak views

```bash
jfr view object-statistics recording.jfr
jfr view memory-leaks-by-class recording.jfr
jfr view memory-leaks-by-site recording.jfr
```

Các view liên quan object statistics hoặc memory leak chỉ có thể đưa ra kết quả hữu ích nếu recording có đủ event và cấu hình phù hợp. Chúng giúp tìm class hoặc allocation site có object bị giữ lâu đáng chú ý; không tự chứng minh có memory leak.

Để xác minh retention, cần xem object có còn reachable sau các chu kỳ GC, ai đang giữ tham chiếu và liệu việc giữ đó có đúng yêu cầu nghiệp vụ hay không. Có thể cần heap dump, dominator tree và path to GC roots. Thu thập dữ liệu đường dẫn GC root có thể làm tăng chi phí recording hoặc tạo pause, vì vậy chỉ bật khi có giả thuyết memory leak cần điều tra.

## 6. Các view hữu ích để phân tích Garbage Collection

### 6.1. `gc-pauses`

`gc-pauses` tổng hợp các pause liên quan GC:

```bash
jfr view gc-pauses recording.jfr
```

Hãy xem thời điểm, duration và loại/pha pause theo các cột mà view cung cấp. Dùng bảng này để tìm pause dài bất thường hoặc các khoảng pause trùng với latency spike.

Không chỉ nhìn pause lớn nhất. Cần phân tích phân bố và tần suất: nhiều pause ngắn lặp lại có thể ảnh hưởng latency tail khác với một pause dài hiếm gặp.

### 6.2. `gc`, `gc-concurrent-phases` và `gc-pause-phases`

```bash
jfr view gc recording.jfr
jfr view gc-concurrent-phases recording.jfr
jfr view gc-pause-phases recording.jfr
```

Các view này bổ sung bối cảnh về chu kỳ GC, các pha concurrent và các pha pause. Với collector concurrent như ZGC, thời gian làm việc concurrent có thể đáng kể dù pause ngắn. Vì vậy, hãy xem thêm CPU load, allocation rate và heap occupancy thay vì kết luận collector tốt chỉ dựa trên pause.

Với Generational ZGC trên Java 21, có thể đối chiếu dữ liệu JFR với GC log để hiểu hoạt động young/old collection. View không nhất thiết hiển thị mọi chỉ số promotion hoặc live set mà bài toán cần; khi thiếu, dùng GC log và các công cụ phân tích heap phù hợp.

### 6.3. `gc-references`

`gc-references` có thể giúp xem dữ liệu liên quan reference processing. Khi điều tra chi phí xử lý soft, weak, phantom reference hoặc reference queue, cần đọc các event tương ứng và hiểu ứng dụng đang sử dụng loại reference nào.

Không suy luận rằng mọi reference processing đều là leak. Hãy xác định loại reference, số lượng và thời gian xử lý, sau đó kiểm tra logic cache hoặc cleanup có liên quan.

## 7. Các view hữu ích để phân tích thread và virtual thread

### 7.1. `thread-count` và `thread-start`

```bash
jfr view thread-count recording.jfr
jfr view thread-start recording.jfr
```

`thread-count` giúp theo dõi số thread và đỉnh thread count trong recording. `thread-start` giúp xem hoạt động tạo thread. Số lượng thread tăng liên tục có thể liên quan đến thread leak, executor tạo thread không giới hạn hoặc workload thay đổi.

Đối với virtual thread, số lượng thread Java có thể rất lớn và không đồng nghĩa với số lượng OS thread/carrier. Hãy phân biệt platform thread, virtual thread và carrier thread khi diễn giải số liệu.

### 7.2. `thread-cpu-load` và `thread-allocation`

```bash
jfr view thread-cpu-load recording.jfr
jfr view thread-allocation recording.jfr
```

Các view này giúp xác định thread nào có hoạt động CPU hoặc allocation đáng chú ý. Đối chiếu với tên thread, executor và loại request để nhận diện worker gây tải.

Tên thread chỉ là nhãn chẩn đoán. Một worker pool có thể tái sử dụng cùng thread cho nhiều task, vì vậy cần thêm request ID hoặc trace ID để nối dữ liệu thread với một giao dịch cụ thể.

### 7.3. `pinned-threads`

Với ứng dụng Java 21 dùng virtual thread, view `pinned-threads` giúp điều tra các lần virtual thread bị pin vào carrier trong lúc thực hiện blocking:

```bash
jfr view pinned-threads recording.jfr
```

Khi thấy pinning, xem duration, thread và stack trace để tìm vùng code liên quan. Trong Java 21, pinning có thể xảy ra khi virtual thread blocking trong một số vùng `synchronized` hoặc native/foreign call. Không dùng pinning như cơ chế giữ virtual thread trên cùng carrier; đó không phải hợp đồng thread affinity.

Nếu recording không chứa event `jdk.VirtualThreadPinned` hoặc event chưa được bật/được ghi nhận, view có thể trống. Hãy kiểm tra event type và JFR settings trước khi kết luận không có pinning.

## 8. Các view hữu ích để phân tích lock và contention

Các view như `contention-by-class`, `contention-by-site`, `contention-by-thread` và `contention-by-address` giúp nhóm sự kiện tranh chấp monitor:

```bash
jfr view contention-by-class recording.jfr
jfr view contention-by-site recording.jfr
jfr view contention-by-thread recording.jfr
```

Khi đọc bảng, tìm class, call site hoặc thread có thời gian chờ/tần suất contention nổi bật. Một số điểm cần phân biệt:

- Nhiều lần contention ngắn có thể gây overhead tích lũy.
- Một lần chờ rất dài có thể làm tăng latency của một request.
- Contention trên cùng một lock có thể tuần tự hóa nhiều worker.
- Monitor contention không bao gồm mọi loại chờ như chờ connection pool, semaphore, I/O hoặc lock của thư viện native.

Nếu cần xác minh, xem event `jdk.JavaMonitorEnter` và stack trace. Không thay `synchronized` bằng một cơ chế khác chỉ vì thấy contention; trước hết cần xác định invariant được bảo vệ và phạm vi critical section.

## 9. Các view hữu ích để phân tích exception và I/O

### 9.1. Exception

```bash
jfr view exception-count recording.jfr
jfr view exception-by-message recording.jfr
jfr view exception-by-site recording.jfr
```

Các view này giúp tìm loại exception, message hoặc call site xuất hiện thường xuyên. Exception có thể là một phần của luồng điều khiển bình thường trong một số ứng dụng, nhưng số lượng lớn hoặc stack lặp lại có thể chỉ ra lỗi đầu vào, retry loop hoặc đường code thất bại liên tục.

Không chỉ đếm exception. Hãy xem loại exception, nơi phát sinh, tần suất theo request và liệu exception có được bắt rồi retry hay không.

### 9.2. File và socket I/O

```bash
jfr view file-reads-by-path recording.jfr
jfr view file-writes-by-path recording.jfr
jfr view socket-reads-by-host recording.jfr
jfr view socket-writes-by-host recording.jfr
```

Các view I/O giúp xác định đường dẫn file hoặc host có hoạt động đọc/ghi đáng chú ý. Chúng hữu ích khi ứng dụng có latency cao nhưng CPU thấp, hoặc khi nghi ngờ một dịch vụ bên ngoài chậm.

Event I/O có thể dùng threshold để tránh ghi quá nhiều sự kiện nhỏ. Vì vậy, không thấy một lần đọc/ghi trong bảng không chứng minh thao tác đó không xảy ra. Kiểm tra JFR settings, threshold và event type trước khi kết luận.

## 10. View môi trường và cấu hình JVM

JFR còn cung cấp các view về môi trường, hữu ích để giải thích vì sao cùng một ứng dụng lại có hiệu năng khác nhau giữa các máy hoặc container:

```bash
jfr view cpu-information recording.jfr
jfr view container-configuration recording.jfr
jfr view container-cpu-usage recording.jfr
jfr view container-cpu-throttling recording.jfr
jfr view container-memory-usage recording.jfr
jfr view jvm-flags recording.jfr
jfr view system-properties recording.jfr
```

Những thông tin này có thể giúp kiểm tra CPU khả dụng, giới hạn container, mức throttling, memory limit và cờ JVM. Một ứng dụng có thể có CPU load thấp vì đang bị giới hạn hoặc chờ I/O; ngược lại, CPU throttling có thể làm GC và application thread đều chậm hơn.

Các view môi trường có thể chứa thông tin nhạy cảm như environment variable, system property, đường dẫn file hoặc tên host. Trước khi chia sẻ recording hoặc output, hãy kiểm tra và loại bỏ dữ liệu bí mật.

## 11. Tùy chỉnh cách hiển thị bảng

`jfr view` hỗ trợ các tùy chọn định dạng. Các tùy chọn phải đặt trước tên view:

```bash
jfr view --width 140 --cell-height 12 hot-methods recording.jfr
```

Các tùy chọn chính:

| Tùy chọn | Tác dụng |
|---|---|
| `--verbose` | Hiển thị query tạo nên view, hữu ích để hiểu event và phép tổng hợp |
| `--width <n>` | Đặt độ rộng bảng theo số ký tự |
| `--truncate beginning` | Cắt nội dung dài ở đầu ô thay vì cuối ô |
| `--truncate end` | Cắt nội dung dài ở cuối ô; đây là mặc định |
| `--cell-height <n>` | Giới hạn số dòng hiển thị trong một ô bảng |

Ví dụ xem query đằng sau view:

```bash
jfr view --verbose allocation-by-site recording.jfr
```

`--verbose` hữu ích khi cần biết view đang nhóm theo field nào, lọc event ra sao hoặc tính tổng hợp theo phép đo nào. Đây là cách kiểm tra ngữ nghĩa của bảng thay vì đoán dựa trên tên view.

Nếu tên method hoặc stack trace bị cắt, tăng `--width` hoặc chọn `--truncate beginning` để giữ phần cuối của tên package/method. Không nên tăng width quá lớn khi terminal hoặc log collector không hỗ trợ dòng dài.

## 12. Kết hợp view với jfr print

Sau khi view chỉ ra một nhóm đáng chú ý, dùng `jfr print` để xem event gốc. Ví dụ, nếu `gc-pauses` có một pause dài:

```bash
jfr print --events jdk.GCPhasePause recording.jfr
```

Nếu `hot-methods` chỉ ra method nóng:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 30 recording.jfr
```

Nếu `pinned-threads` cho thấy virtual thread bị pin:

```bash
jfr print --events jdk.VirtualThreadPinned --stack-depth 30 recording.jfr
```

Nếu `allocation-by-site` chỉ ra allocation hotspot:

```bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 30 recording.jfr
```

Tên event có thể khác tùy loại view và metadata của recording. Dùng `jfr view types recording.jfr` hoặc `jfr metadata --events ... recording.jfr` để kiểm tra event name và field có thật trong file trước khi filter.

## 13. Quy trình thực hành từ recording đến bảng tổng hợp

### 13.1. Ghi một profile ngắn

Có thể khởi chạy ứng dụng với recording có thời hạn:

```bash
java \
  -XX:StartFlightRecording=name=diagnostic,settings=profile,duration=3m,filename=diagnostic.jfr \
  -jar application.jar
```

`profile` thu thập nhiều dữ liệu hơn `default` và thường phù hợp với phiên profiling ngắn. `default` có overhead thấp hơn, thường phù hợp cho recording liên tục. Chọn settings theo mục tiêu và đo overhead trên workload thực tế.

Hoặc attach vào JVM đang chạy:

```bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=3m filename=diagnostic.jfr
jcmd <pid> JFR.check
```

Sau khi có recording:

```bash
jfr summary diagnostic.jfr
jfr view all-views diagnostic.jfr
jfr view hot-methods diagnostic.jfr
jfr view allocation-by-site diagnostic.jfr
jfr view gc-pauses diagnostic.jfr
```

Không cần chạy mọi view trong mọi sự cố. Chọn view theo giả thuyết: CPU-bound, allocation churn, GC pause, contention, I/O hoặc thread pinning.

### 13.2. Điều tra một sự cố theo câu hỏi

| Triệu chứng | View bắt đầu | Dữ liệu cần đối chiếu |
|---|---|---|
| CPU cao | `hot-methods`, `cpu-load` | Execution samples, CPU/container throttling, request throughput |
| Heap/GC pressure | `allocation-by-site`, `allocation-by-class`, `gc` | Allocation sample, GC log, heap live set |
| Pause GC ảnh hưởng latency | `gc-pauses`, `gc-pause-phases` | Pause duration, request latency cùng timestamp |
| Virtual thread bị pin | `pinned-threads` | `jdk.VirtualThreadPinned`, stack trace, JDK version |
| Lock contention | `contention-by-class`, `contention-by-site` | `jdk.JavaMonitorEnter`, lock owner và critical section |
| Nhiều exception | `exception-count`, `exception-by-site` | Event exception, message, retry behavior |
| I/O chậm | `socket-reads-by-host`, `file-reads-by-path` | I/O duration/bytes, network metrics, dependency latency |
| Thread tăng liên tục | `thread-count`, `thread-start` | Thread lifecycle, executor configuration, thread dump |

### 13.3. Một chuỗi lệnh mẫu

```bash
# 1. Kiểm tra loại event và số lượng
jfr summary diagnostic.jfr

# 2. Xem view phù hợp với giả thuyết CPU
jfr view hot-methods diagnostic.jfr

# 3. Xem query và cách tổng hợp của view
jfr view --verbose hot-methods diagnostic.jfr

# 4. Kiểm tra event gốc và stack trace
jfr print --events jdk.ExecutionSample --stack-depth 30 diagnostic.jfr
```

Kết quả cuối cùng nên được đối chiếu với log ứng dụng, metric hệ thống và trace request. JFR cho biết điều gì xảy ra bên trong JVM; nó không tự giải thích toàn bộ bối cảnh nghiệp vụ hoặc tình trạng của database, network và hệ điều hành.

## 14. Giới hạn và cách diễn giải đúng

- **Recording chỉ chứa event đã bật:** view không thể tổng hợp dữ liệu chưa được ghi.
- **Sampling không phải đếm tuyệt đối:** execution sample và allocation sample là dữ liệu lấy mẫu; dùng để nhận diện hotspot, không mặc định coi là số lần thực thi/cấp phát chính xác.
- **Threshold có thể bỏ qua event ngắn:** I/O hoặc contention rất ngắn có thể không xuất hiện tùy settings.
- **Khoảng thời gian quan trọng:** recording không bao phủ thời điểm sự cố thì view không thể giải thích sự cố đó.
- **Một bảng không phải kết luận:** cần xác minh bằng event gốc, stack trace, log, metric và workload.
- **Overhead phụ thuộc settings:** `profile` thu nhiều dữ liệu hơn `default`; cấu hình custom có thể thay đổi chi phí và event được ghi.
- **Dữ liệu nhạy cảm:** recording có thể chứa tên thread, host, đường dẫn, system properties hoặc stack trace nội bộ. Kiểm tra trước khi chia sẻ.
- **Khác biệt JDK/vendor:** danh sách view, field và cách trình bày có thể thay đổi; luôn xem `jfr --help view` và `jfr view all-views` trên runtime đang dùng.

## 15. Nguyên tắc sử dụng

- Bắt đầu bằng `jfr summary` để biết recording có event nào.
- Dùng `jfr view` để tổng hợp dữ liệu theo câu hỏi chẩn đoán.
- Dùng `jfr view all-views` và `jfr view types` để khám phá view/event khả dụng.
- Chọn `hot-methods`, allocation, GC, contention, thread hoặc I/O view theo triệu chứng.
- Dùng `--verbose` để hiểu query và field đằng sau bảng.
- Dùng `jfr print` để xác minh hàng tổng hợp bằng event và stack trace gốc.
- Đọc sample, count, duration và percentage theo đúng ngữ nghĩa; không suy diễn thành số liệu tuyệt đối khi view không bảo đảm.
- Ghi recording đúng thời điểm, đúng settings và đủ dài để bao phủ workload cần phân tích.
- Kết hợp JFR với GC log, application metrics, tracing và dữ liệu hệ thống.
- Kiểm tra dữ liệu nhạy cảm trước khi chia sẻ file recording.

`jfr view` giúp chuyển recording JFR thành các bảng tổng hợp dễ đọc ngay trên command line. Khi dùng summary để kiểm tra dữ liệu, chọn view theo giả thuyết và quay lại event gốc để xác minh, quá trình điều tra CPU, memory, GC, lock, I/O và virtual thread sẽ nhanh hơn mà vẫn giữ được độ chính xác trong diễn giải.

## Tài liệu tham khảo

- [Java SE 21 — The `jfr` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): cú pháp `jfr view`, `summary`, `print`, các tùy chọn và cách liệt kê view/event.
- [JDK 21 Release Notes — New JFR View Command](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): xác nhận JFR View được bổ sung trong JDK 21 và các view dựng sẵn.
- [Inside.java — JFR View Command](https://inside.java/2023/09/26/sip082/): nhóm view JVM, environment, application và ví dụ định dạng bảng.
- [Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): ghi JFR, các cách phân tích recording và sử dụng JDK Mission Control.
- [Java SE 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): các lệnh chẩn đoán JVM và quản lý recording JFR.
- [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): settings `default`/`profile`, event settings và cách cấu hình recording.
