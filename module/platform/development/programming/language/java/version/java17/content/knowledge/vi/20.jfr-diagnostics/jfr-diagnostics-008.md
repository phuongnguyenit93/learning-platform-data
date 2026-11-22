# Đọc dữ liệu ghi bằng công cụ jfr và JDK Mission Control

> **Chủ đề:** Java 17  
> **Chương:** Chẩn đoán và JFR  
> **Mục tiêu:** Ghi lại hoạt động của JVM bằng Java Flight Recorder (JFR), đọc nhanh file recording với lệnh `jfr` và phân tích timeline, event, thread, GC, allocation cùng các vấn đề hiệu năng bằng JDK Mission Control (JMC).

## 1. JFR và JDK Mission Control là gì?

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện của JVM. Nó thu thập dữ liệu về hoạt động của ứng dụng và runtime theo thời gian, ví dụ:

- CPU load và thời gian thực thi của thread.
- Garbage collection, allocation và áp lực bộ nhớ.
- Lock contention và thread bị chặn.
- I/O, file, socket và các hoạt động hệ thống được bật trong cấu hình recording.
- Exception, class loading, JIT compilation và các sự kiện JVM khác.

JFR lưu dữ liệu thành recording, thường có phần mở rộng `.jfr`. File này chứa các event có timestamp, thông tin thread, stack trace và những trường dữ liệu phù hợp với từng loại event.

**JDK Mission Control (JMC)** là công cụ phân tích recording JFR bằng giao diện đồ họa. JMC giúp:

- Xem tổng quan recording và khoảng thời gian được ghi.
- Tìm các khoảng CPU cao, GC pause, allocation và lock contention.
- Xem event theo timeline, thread hoặc loại sự kiện.
- Đi từ một event đến stack trace và vùng code liên quan.
- Chạy các quy tắc phân tích để tìm dấu hiệu cần điều tra.

Trong Java 17, lệnh `jfr` được cung cấp cùng JDK. JMC là công cụ riêng có thể cài từ bản phân phối JDK Mission Control; không nên giả định mọi bản cài JDK 17 đều có sẵn ứng dụng JMC.

### 1.1. JFR khác gì log ứng dụng?

Log ứng dụng ghi những thông điệp mà code chủ động phát ra. JFR ghi các sự kiện từ JVM, runtime và những thành phần instrumented khác. Hai nguồn dữ liệu bổ sung cho nhau:

| Nguồn | Trả lời tốt câu hỏi |
|---|---|
| Application log | Request nào lỗi? User nào gọi? Nghiệp vụ đã xảy ra điều gì? |
| Metrics | CPU, memory, latency, throughput thay đổi ra sao theo thời gian? |
| JFR recording | Trong JVM, thread nào chạy, chờ lock, cấp phát object hoặc trải qua GC vào thời điểm nào? |
| Thread dump | Tại thời điểm lấy dump, thread đang ở stack frame nào và trạng thái gì? |
| Heap dump | Object nào đang giữ heap và quan hệ tham chiếu ra sao? |

JFR không thay thế log hoặc metrics. Ví dụ, JFR có thể cho thấy thread xử lý request bị chờ monitor trong một khoảng thời gian, còn application log giúp liên hệ khoảng đó với request ID hoặc thao tác nghiệp vụ.

### 1.2. JFR có dùng được trong môi trường production không?

JFR được thiết kế để ghi sự kiện với overhead thấp khi dùng cấu hình phù hợp. Nó thường được dùng để quan sát JVM trong môi trường chạy thật, kể cả recording liên tục hoặc recording theo khoảng thời gian.

Tuy vậy, không có mức overhead bằng không. Cấu hình nhiều event chi tiết, stack trace sâu, event có tần suất cao hoặc thời gian ghi dài có thể làm tăng CPU, dung lượng recording và I/O. Hãy bắt đầu bằng cấu hình phù hợp, thử nghiệm trên workload đại diện và theo dõi tác động trước khi áp dụng rộng.

## 2. Chuẩn bị môi trường Java 17

Cần có:

- JDK 17 đang chạy ứng dụng hoặc tương thích với tiến trình cần chẩn đoán.
- Lệnh `jfr` và `jcmd` từ thư mục `bin` của JDK.
- JDK Mission Control có phiên bản hỗ trợ đọc recording của Java 17.
- Quyền truy cập tiến trình JVM và thư mục lưu file recording.

Kiểm tra công cụ:

```bash
java -version
jfr --version
jcmd -h
```

Nếu shell không tìm thấy `jfr` hoặc `jcmd`, hãy gọi bằng đường dẫn đầy đủ đến thư mục `JAVA_HOME/bin` hoặc bổ sung JDK `bin` vào PATH.

### 2.1. Xác định đúng JVM process

Lệnh:

```bash
jcmd -l
```

liệt kê các tiến trình JVM mà người dùng hiện tại có thể quan sát. Kết quả thường gồm PID và tên class/module khởi chạy.

Ví dụ:

```text
18420 com.acme.orders.Main
19108 org.springframework.boot.loader.launch.JarLauncher
```

Trong các ví dụ tiếp theo, `<pid>` là PID thực tế của tiến trình cần ghi. Không dùng PID minh họa trên máy của bạn.

Nếu ứng dụng chạy trong container, hãy chạy công cụ trong đúng container hoặc môi trường process namespace phù hợp. PID nhìn từ host có thể khác PID trong container.

## 3. Tạo recording JFR

Có hai cách thường dùng: bật recording khi JVM khởi động hoặc attach vào JVM đang chạy bằng `jcmd`.

### 3.1. Bật recording khi khởi động ứng dụng

Ví dụ ghi một khoảng thời gian 2 phút bằng cấu hình `profile`:

```bash
java -XX:StartFlightRecording:filename=orders-profile.jfr,settings=profile,duration=2m \
     -jar orders-service.jar
```

Các tham số:

- `filename`: file recording được ghi ra.
- `settings=profile`: dùng cấu hình thu thập chi tiết hơn để điều tra hiệu năng trong một khoảng thời gian.
- `duration=2m`: dừng recording sau 2 phút.

Nếu muốn recording tiếp tục trong suốt vòng đời tiến trình, có thể bỏ `duration` và dùng `dumponexit=true` để dump khi JVM kết thúc:

```bash
java -XX:StartFlightRecording:filename=orders-runtime.jfr,settings=default,dumponexit=true \
     -jar orders-service.jar
```

Recording dài hạn thường nên dùng cấu hình `default` và giới hạn dung lượng/thời gian lưu phù hợp. Kiểm tra dung lượng đĩa và chính sách lưu trữ của môi trường chạy.

### 3.2. Bắt đầu recording trên JVM đang chạy bằng jcmd

Đây là cách tiện lợi khi cần chẩn đoán một ứng dụng đã khởi động mà không muốn restart:

```bash
jcmd <pid> JFR.start name=orders-profile settings=profile duration=2m filename=orders-profile.jfr
```

Nếu lệnh thành công, JVM trả về thông tin recording đã bắt đầu và ID của recording. File được ghi tại đường dẫn mà tiến trình có quyền tạo.

Một recording mặc định có thể được bắt đầu bằng:

```bash
jcmd <pid> JFR.start name=orders-default settings=default duration=5m filename=orders-default.jfr
```

`default` phù hợp cho quan sát tổng quát và thời gian dài hơn; `profile` thường ghi nhiều dữ liệu chi tiết hơn để điều tra một khoảng thời gian ngắn. Cấu hình cụ thể quyết định event nào được bật, ngưỡng, chu kỳ và stack trace.

### 3.3. Bắt đầu recording liên tục và dump khi cần

Có thể để JVM duy trì recording trên đĩa, rồi dump ra file khi phát hiện vấn đề:

```bash
jcmd <pid> JFR.start name=orders-continuous settings=default disk=true maxage=1h maxsize=250m
```

Khi cần lấy dữ liệu:

```bash
jcmd <pid> JFR.dump name=orders-continuous filename=orders-incident.jfr
```

Recording liên tục cho phép giữ một cửa sổ dữ liệu gần thời điểm sự cố. Các tùy chọn:

- `disk=true`: ghi recording ra đĩa theo cơ chế repository của JFR.
- `maxage=1h`: giới hạn tuổi dữ liệu được giữ.
- `maxsize=250m`: giới hạn dung lượng recording được giữ.

Các giới hạn này là ví dụ; hãy chọn theo tốc độ phát sinh event và dung lượng đĩa. Nếu recording không dùng disk, dữ liệu được giữ trong bộ nhớ và có giới hạn tài nguyên khác.

### 3.4. Kiểm tra, dump và dừng recording

Xem các recording hiện có:

```bash
jcmd <pid> JFR.check
```

Dump recording đang chạy:

```bash
jcmd <pid> JFR.dump name=orders-continuous filename=orders-snapshot.jfr
```

Dừng recording:

```bash
jcmd <pid> JFR.stop name=orders-continuous
```

Dump và stop là hai thao tác khác nhau. `JFR.dump` tạo file snapshot của dữ liệu recording hiện tại; `JFR.stop` kết thúc recording được chỉ định. Khi điều tra, hãy dump trước nếu muốn giữ dữ liệu rồi mới dừng recording.

### 3.5. Tự động dump khi JVM thoát

Với recording tạo bằng `jcmd`, có thể dùng tùy chọn `dumponexit=true` khi bắt đầu:

```bash
jcmd <pid> JFR.start name=orders-exit settings=default disk=true dumponexit=true
```

Điều này yêu cầu JVM ghi recording khi tiến trình kết thúc bình thường theo cơ chế JFR. Với sự cố kill cưỡng bức hoặc máy bị mất điện, không nên giả định dữ liệu cuối cùng sẽ luôn được dump đầy đủ.

### 3.6. Xem trợ giúp lệnh JFR

Tên và các tùy chọn khả dụng có thể phụ thuộc bản JDK cụ thể. Hãy xem trợ giúp ngay trên JDK đang sử dụng:

```bash
jcmd <pid> help JFR.start
jcmd <pid> help JFR.dump
jcmd <pid> help JFR.stop
```

Và xem trợ giúp CLI:

```bash
jfr help
jfr help summary
jfr help print
jfr help configure
```

Đây là cách xác nhận cú pháp thực tế thay vì sao chép một câu lệnh từ bản JDK khác.

## 4. Đọc recording bằng lệnh jfr

JDK 17 cung cấp CLI `jfr` để xem metadata, thống kê và nội dung event trong file recording mà không cần mở JMC.

### 4.1. Xem tóm tắt recording

```bash
jfr summary orders-profile.jfr
```

Summary thường cho biết:

- Thời điểm bắt đầu và kết thúc recording.
- Thời lượng.
- Phiên bản JFR/JVM và thông tin môi trường được ghi.
- Danh sách event type.
- Số lượng event và kích thước dữ liệu tương ứng.

Hãy bắt đầu bằng summary để biết recording có đúng khoảng thời gian cần điều tra và có những loại event nào. Nếu event quan trọng không xuất hiện, kiểm tra cấu hình recording trước khi phân tích sâu.

### 4.2. In nội dung event

In recording ra dạng text:

```bash
jfr print orders-profile.jfr
```

File lớn có thể tạo đầu ra rất dài. Thường nên lọc theo event type:

```bash
jfr print --events jdk.ExecutionSample orders-profile.jfr
jfr print --events jdk.GarbageCollection orders-profile.jfr
jfr print --events jdk.JavaMonitorEnter orders-profile.jfr
```

Có thể yêu cầu stack trace sâu hơn:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 orders-profile.jfr
```

Tên event phải tồn tại trong metadata của recording và được bật trong cấu hình. Nếu không thấy dữ liệu, hãy kiểm tra tên event bằng `jfr metadata` hoặc xem danh sách event trong JMC.

### 4.3. Xem metadata của event

```bash
jfr metadata orders-profile.jfr
```

Metadata mô tả event type và các trường dữ liệu được định nghĩa. Nó hữu ích khi cần biết:

- Tên chính xác của event.
- Event có những field nào.
- Kiểu dữ liệu và ý nghĩa của field.
- Event được định nghĩa bởi JVM hay một thành phần khác.

JFR recording không nhất thiết chứa mọi event mà JVM biết. Metadata giúp hiểu event type; summary giúp biết event nào thực sự có trong recording.

### 4.4. Chuyển đầu ra sang JSON hoặc XML

Để dùng công cụ xử lý dữ liệu khác, có thể in event theo định dạng có cấu trúc:

```bash
jfr print --json --events jdk.GarbageCollection orders-profile.jfr
```

Hoặc:

```bash
jfr print --xml --events jdk.GarbageCollection orders-profile.jfr
```

Đầu ra có thể lớn, đặc biệt với event tần suất cao. Hãy lọc event trước khi chuyển đổi và tránh lưu dữ liệu nhạy cảm ở nơi không được kiểm soát.

### 4.5. Lọc theo event và thời gian

CLI `jfr print` hỗ trợ lọc theo event type và một số điều kiện thời gian tùy phiên bản JDK. Với Java 17, xem chính xác các tùy chọn:

```bash
jfr help print
```

Khi cần phân tích nhiều event liên hệ theo timeline, JMC thường thuận tiện hơn vì có thể lọc và điều hướng trực quan. CLI phù hợp cho kiểm tra nhanh, trích xuất một nhóm event hoặc tích hợp vào script phân tích.

### 4.6. Ví dụ quy trình CLI tối thiểu

Giả sử đã có file `orders-incident.jfr`:

```bash
jfr summary orders-incident.jfr
jfr print --events jdk.GarbageCollection orders-incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 orders-incident.jfr
```

Đọc summary trước, sau đó chọn event phù hợp với giả thuyết điều tra. Nếu GC pause cao, xem GC events; nếu CPU cao, xem execution samples và stack trace. Tránh in toàn bộ recording khi chỉ cần một nhóm sự kiện.

## 5. Phân tích file JFR bằng JDK Mission Control

JMC cung cấp giao diện đồ họa để xem recording và kết nối các event theo thời gian. Tên tab hoặc cách sắp xếp có thể khác giữa các phiên bản JMC, nhưng quy trình phân tích cơ bản tương tự.

### 5.1. Mở file recording

1. Cài phiên bản JDK Mission Control tương thích với JFR của Java 17.
2. Khởi động ứng dụng JMC.
3. Mở file recording bằng chức năng mở file hoặc kéo file `.jfr` vào cửa sổ JMC.
4. Chờ JMC đọc và lập chỉ mục dữ liệu.
5. Mở trang tổng quan/Overview để xem thời gian, JVM và các chỉ số chính.

JMC là ứng dụng riêng; cài JDK 17 không đồng nghĩa máy đã có JMC. Nếu file được tạo bằng JDK mới hơn, hãy dùng phiên bản JMC hỗ trợ format/event tương ứng. Không nên giả định mọi bản JMC cũ đều hiểu đầy đủ event mới.

### 5.2. Bắt đầu từ trang tổng quan

Trang tổng quan giúp xác định recording có đủ dữ liệu để điều tra:

- Recording bắt đầu/kết thúc lúc nào?
- JVM nào đã tạo file, phiên bản Java và hệ điều hành nào?
- Thời gian recording có trùng khoảng xảy ra sự cố?
- CPU load và heap usage thay đổi ra sao?
- Có GC pause đáng chú ý không?
- Thread count có tăng bất thường không?
- Các nhóm event nào xuất hiện nhiều?

Nếu sự cố xảy ra lúc 10:05 nhưng recording chỉ bắt đầu lúc 10:10, recording có thể không chứa nguyên nhân ban đầu. Hãy xác định chính xác cửa sổ thời gian trước khi đưa ra kết luận.

### 5.3. Dùng Automated Analysis

JMC có các quy tắc phân tích tự động (automated analysis/rules) để tìm dấu hiệu đáng chú ý trong recording, ví dụ:

- CPU load cao hoặc thread dành nhiều thời gian ở một số stack.
- GC pause hoặc allocation pressure đáng xem xét.
- Lock contention.
- I/O chậm.
- Một số cấu hình JVM hoặc hành vi runtime cần kiểm tra.

Kết quả rule là **gợi ý điều tra**, không phải chẩn đoán chắc chắn. Một cảnh báo có thể phù hợp với workload bình thường; một rule không cảnh báo cũng không chứng minh ứng dụng không có vấn đề. Mở chi tiết rule, xem event và đối chiếu với thời điểm lỗi cùng metrics/log của ứng dụng.

### 5.4. Dùng Event Browser và timeline

Event Browser cho phép xem các event đã ghi, thường có thể lọc theo:

- Event type.
- Khoảng thời gian.
- Thread.
- Stack trace.
- Giá trị field như duration hoặc size, nếu event có trường đó.

Timeline giúp quan sát event nào xuất hiện trước, trong và sau một khoảng bất thường. Ví dụ, CPU tăng có thể trùng với nhiều execution samples trong một nhóm method; một thread chờ lâu có thể trùng với monitor contention hoặc socket read.

Hãy giữ ngữ cảnh thời gian khi lọc. Nếu lọc chỉ còn một event mà không xem các event lân cận, có thể bỏ qua quan hệ nhân quả quan trọng.

## 6. Đọc các nhóm event quan trọng

JFR có nhiều event type. Tên chính xác và việc event có xuất hiện hay không phụ thuộc cấu hình recording, phiên bản JVM và workload. Những nhóm dưới đây thường hữu ích khi điều tra ứng dụng Java.

### 6.1. CPU và execution samples

Các event như `jdk.ExecutionSample` ghi lại mẫu stack của thread đang thực thi tại các thời điểm lấy mẫu. Trong JMC, xem các stack thường được quan sát nhiều để tìm vùng code tiêu tốn thời gian CPU.

Quy trình:

1. Mở trang CPU/Method Profiling hoặc nhóm phân tích tương ứng.
2. Chọn khoảng thời gian CPU cao.
3. Xem top methods hoặc call tree theo số mẫu.
4. Mở stack trace để xác định caller và callee.
5. Liên hệ method với request, batch hoặc workload cụ thể bằng log/metrics.

**Execution sample là dữ liệu lấy mẫu thống kê.** Nếu một method xuất hiện nhiều mẫu, nó thường chiếm phần đáng kể thời gian thực thi trong khoảng được lấy mẫu; số mẫu không phải phép đếm chính xác số lần gọi method hoặc thời gian CPU tuyệt đối của từng invocation.

Các câu hỏi nên đặt:

- Method nào xuất hiện nhiều trong các sample?
- CPU tập trung ở code ứng dụng, framework hay thư viện?
- Có vòng lặp nóng hoặc xử lý dữ liệu lặp lại không?
- CPU tăng do một thread hay nhiều thread?
- Stack trace có thay đổi giữa lúc bình thường và lúc tải cao không?

Đừng tối ưu method chỉ vì nó có tên ở top list. Hãy xem tỷ lệ mẫu, workload, số thread và tác động đến latency.

### 6.2. Garbage collection và heap

Những event như `jdk.GarbageCollection`, `jdk.GCPhasePause` và các event GC liên quan mô tả hoạt động thu gom rác.

Trong JMC, xem:

- Thời điểm bắt đầu/kết thúc các lần GC.
- Pause duration và các pha pause.
- Loại collector và loại chu kỳ GC.
- Heap occupancy trước/sau GC khi event cung cấp dữ liệu.
- Các khoảng thời gian allocation tăng.
- Tần suất GC và ảnh hưởng đến throughput/latency.

Một vài cách diễn giải:

| Dấu hiệu | Hướng điều tra |
|---|---|
| Pause dài trùng với latency spike | Xem GC phase, heap occupancy, allocation pressure và thời điểm request chậm |
| GC xảy ra dày đặc | Kiểm tra allocation rate, object lifetime, heap size và workload |
| Heap sau GC tăng qua nhiều chu kỳ | Kiểm tra live set, cache, collection và tham chiếu giữ object |
| Nhiều allocation sample từ một stack | Tìm code tạo nhiều object; xem có thể giảm allocation hoặc tái sử dụng hợp lý không |

Không phải mọi GC pause đều là lỗi. GC là hoạt động bình thường của JVM; cần so sánh thời lượng, tần suất, mục tiêu latency và mức tải.

### 6.3. Allocation và object pressure

Các event như `jdk.ObjectAllocationSample` cung cấp mẫu về nơi object được cấp phát. Trong JMC, stack trace có thể giúp xác định method tạo ra nhiều allocation.

Ví dụ, một API chuyển đổi hàng nghìn bản ghi có thể tạo nhiều object tạm:

```java
List<String> labels = records.stream()
        .map(record -> record.getName() + ":" + record.getId())
        .toList();
```

Nếu recording cho thấy allocation sample tập trung ở pipeline này, có thể xem xét:

- Có tạo chuỗi trung gian không cần thiết không?
- Có xử lý lại cùng dữ liệu nhiều lần không?
- Có thể giảm số object tạm mà vẫn giữ code rõ ràng không?
- Có cache không giới hạn khiến object sống lâu hơn không?

Lưu ý: `ObjectAllocationSample` là event lấy mẫu, không phải bản kê đầy đủ từng object được cấp phát. Không dùng số sample như tổng số object hoặc tổng byte cấp phát chính xác nếu chưa hiểu cách event được cấu hình và lấy mẫu.

### 6.4. Lock contention và thread waiting

Các event như `jdk.JavaMonitorEnter` có thể ghi nhận thời gian thread chờ monitor; `jdk.ThreadPark` có thể giúp quan sát thread bị park trong các cơ chế đồng bộ.

Trong JMC:

1. Mở phần Threads hoặc Lock Instances/Lock Profiling tùy phiên bản.
2. Tìm các khoảng chờ dài hoặc lặp lại.
3. Xác định thread đang chờ và stack trace tại thời điểm chờ.
4. Tìm thread giữ lock hoặc vùng code liên quan nếu recording có dữ liệu.
5. Kiểm tra lock có được giữ trong lúc thực hiện I/O, gọi dịch vụ hoặc xử lý lâu không.

Ví dụ:

```java
public synchronized void updateInventory() {
    // Nếu giữ monitor trong lúc gọi dịch vụ từ xa,
    // các thread khác có thể phải chờ lâu.
    remoteService.refresh();
    updateLocalState();
}
```

Một hướng cải thiện có thể là rút ngắn vùng giữ lock và tách thao tác I/O khỏi critical section, nhưng phải bảo toàn tính nhất quán dữ liệu. JFR chỉ cho thấy dấu hiệu contention; quyết định sửa code cần hiểu invariant của nghiệp vụ.

### 6.5. File I/O và socket I/O

Các event như `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead` và `jdk.SocketWrite` có thể cho biết hoạt động I/O cùng duration/size/endpoint tùy event và cấu hình.

Khi điều tra:

- Xem operation nào có duration dài.
- Phân biệt thread đang chờ I/O với thread đang dùng CPU.
- Kiểm tra kích thước dữ liệu và số lần gọi.
- Tìm stack trace dẫn đến file/client/network library.
- Đối chiếu với log phía server hoặc dịch vụ phụ thuộc.

Không phải mọi event I/O đều được ghi trong mọi recording. Cấu hình có thể đặt threshold để chỉ ghi operation đủ lâu. Vì vậy, không thấy event chậm không có nghĩa không có I/O; có thể event chưa được bật hoặc ngưỡng quá cao.

### 6.6. Exception và class loading

Các event như `jdk.JavaExceptionThrow`, `jdk.ExceptionStatistics` và event class loading có thể giúp xác định:

- Exception có xuất hiện dày trong một khoảng thời gian không?
- Exception có cùng stack trace lặp đi lặp lại không?
- Ứng dụng có nạp class bất thường trong thời gian chạy không?
- Một framework hoặc plugin có làm class loading tăng đột biến không?

Exception không nhất thiết là nguyên nhân của vấn đề hiệu năng. Một số ứng dụng dùng exception cho luồng điều khiển, nhưng exception phát sinh quá nhiều có thể làm tăng chi phí CPU và log. Hãy xem loại exception, tần suất, stack trace và ngữ cảnh.

## 7. Chọn cấu hình recording phù hợp

JFR dùng file cấu hình `.jfc` để quyết định event nào được ghi, ngưỡng duration, chu kỳ lấy mẫu, stack trace và các tham số khác.

### 7.1. default và profile

JDK cung cấp hai cấu hình thường gặp:

| Cấu hình | Mục đích | Cách dùng điển hình |
|---|---|---|
| `default` | Theo dõi tổng quát với lượng dữ liệu và overhead thấp | Recording liên tục hoặc thời gian dài |
| `profile` | Thu thập nhiều dữ liệu chi tiết hơn cho điều tra hiệu năng | Recording ngắn trong khoảng tái hiện vấn đề |

`profile` không phải lúc nào cũng là lựa chọn tốt nhất. Nó có thể ghi thêm event và stack trace, tạo file lớn hơn hoặc overhead cao hơn tùy workload. Với dịch vụ chạy liên tục, có thể giữ recording `default` làm nền và tạo recording `profile` ngắn khi cần điều tra cụ thể.

### 7.2. Vị trí file cấu hình JFC

Trong JDK 17, các cấu hình đi kèm thường nằm dưới:

```text
JAVA_HOME/lib/jfr/
    default.jfc
    profile.jfc
```

Có thể xem file cấu hình để biết event nào được bật và threshold hiện tại. Không nên chỉnh trực tiếp file cấu hình mặc định của JDK dùng chung cho nhiều ứng dụng; hãy tạo một file cấu hình riêng cho ứng dụng hoặc môi trường.

### 7.3. Tạo cấu hình riêng bằng jfr configure

Ví dụ bắt đầu từ profile và điều chỉnh threshold của event monitor contention:

```bash
jfr configure --input profile.jfc --output orders-diagnostic.jfc \
    jdk.JavaMonitorEnter#threshold=10ms
```

Sau đó sử dụng file cấu hình riêng:

```bash
jcmd <pid> JFR.start name=orders-locks settings=orders-diagnostic.jfc duration=3m filename=orders-locks.jfr
```

Ví dụ trên chỉ minh họa cách truyền một tùy chọn cấu hình. Hãy kiểm tra event và tùy chọn hợp lệ bằng `jfr help configure` cùng metadata của JDK đang chạy.

### 7.4. Bật event và điều chỉnh threshold có chủ đích

Một số event chỉ ghi khi duration vượt threshold. Hạ threshold có thể giúp bắt được operation ngắn hơn nhưng cũng làm tăng số lượng event và dung lượng file.

Khi chỉnh cấu hình:

1. Xác định giả thuyết: CPU, allocation, lock, I/O hay GC?
2. Chỉ bật event cần thiết.
3. Đặt threshold dựa trên latency mục tiêu và workload.
4. Chạy thử với dữ liệu đại diện.
5. Đo overhead, dung lượng recording và mức độ hữu ích của dữ liệu.
6. Lưu file JFC cùng tài liệu triển khai để có thể tái hiện cấu hình.

Không hạ mọi threshold về zero hoặc bật mọi event một cách tùy tiện. Recording quá chi tiết có thể làm tăng overhead, tạo file lớn và khiến việc tìm tín hiệu quan trọng khó hơn.

### 7.5. Stack trace và sampling

Stack trace giúp nối event với đường gọi trong ứng dụng, nhưng không phải event nào cũng có stack trace và không phải mọi event đều được ghi ở cùng tần suất.

- Execution samples được lấy theo chu kỳ, nên là thống kê.
- Allocation sample là dữ liệu mẫu về nơi cấp phát.
- I/O hoặc lock events có thể được ghi khi vượt threshold.
- Một số event có thể chỉ được ghi khi bật rõ ràng trong JFC.

Khi so sánh hai recording, hãy dùng cấu hình tương đương. Nếu một recording có stack trace và event chi tiết còn recording kia không có, số liệu không thể so sánh trực tiếp.

## 8. Quy trình điều tra hiệu năng bằng JMC

Một recording có nhiều dữ liệu chỉ hữu ích khi câu hỏi điều tra rõ ràng. Có thể đi theo quy trình sau:

### Bước 1 — Xác định khoảng thời gian sự cố

Đối chiếu timestamp của JFR với:

- Alert/metrics báo CPU, latency hoặc error rate tăng.
- Application log và request ID.
- Thời điểm deploy hoặc thay đổi cấu hình.
- Thời điểm workload tăng hoặc batch job bắt đầu.

Xác định recording có bao phủ cả thời điểm ngay trước sự cố hay không.

### Bước 2 — Xem Overview và automated analysis

Ghi nhận CPU, heap, GC, thread count và các cảnh báo. Chọn một hoặc hai tín hiệu nổi bật để đào sâu. Tránh mở đồng thời mọi event rồi cố tìm nguyên nhân trong lượng dữ liệu lớn.

### Bước 3 — Chọn nhóm event theo triệu chứng

| Triệu chứng | Event/nhóm dữ liệu nên xem |
|---|---|
| CPU cao | Execution samples, thread CPU load, method profiling |
| Latency tăng cùng GC | Garbage collection, GC phase/pause, heap usage |
| Allocation tăng | Object allocation samples, allocation stack traces |
| Thread chờ lâu | Java monitor enter, thread park, thread state |
| I/O chậm | File read/write, socket read/write |
| Exception tăng | Java exception throw, exception statistics |
| Class loading tăng | Class load/unload và class loader events |

Tên event có thể thay đổi hoặc không có trong recording; hãy dựa vào event thực tế đã ghi.

### Bước 4 — Tìm stack trace và đường gọi

Khi thấy event bất thường:

1. Chọn event hoặc nhóm event.
2. Mở stack trace.
3. Xác định frame đầu tiên thuộc code ứng dụng.
4. Xem caller để hiểu vì sao đoạn code được gọi.
5. Kiểm tra thread, thời gian và các event lân cận.

Đừng dừng ở một method của framework nếu chưa biết code ứng dụng nào đã kích hoạt nó.

### Bước 5 — Đặt giả thuyết và kiểm chứng

Ví dụ:

- Giả thuyết: latency tăng vì một lock dùng chung.
- Bằng chứng: nhiều thread chờ cùng monitor trong khoảng spike; stack trace chỉ về cùng critical section.
- Kiểm chứng: đối chiếu với metrics latency và log; tạo recording sau khi thay đổi để so sánh.

JFR giúp hình thành giả thuyết và chỉ ra vị trí cần xem. Muốn khẳng định nguyên nhân, cần kết hợp log, metrics, code và thử nghiệm có kiểm soát.

### Bước 6 — So sánh baseline và recording sau thay đổi

Khi đánh giá một bản sửa:

- Dùng workload và thời lượng tương tự.
- Dùng cùng cấu hình JFR.
- So sánh CPU samples, allocation, GC pause, lock wait và I/O duration.
- Xem latency/throughput từ metrics ứng dụng.
- Kiểm tra thay đổi có chuyển chi phí sang một vùng khác không.

Một chỉ số giảm chưa chắc toàn hệ thống tốt hơn. Ví dụ, giảm allocation bằng cache có thể làm heap live set tăng; hãy xem cả hai phía.

## 9. Ví dụ thực hành: điều tra CPU tăng cao

Giả sử metrics cho thấy CPU của dịch vụ tăng mạnh trong vài phút, nhưng error rate không tăng tương ứng.

### 9.1. Ghi recording

Nếu tiến trình đã chạy, bắt đầu recording ngắn:

```bash
jcmd <pid> JFR.start name=cpu-incident settings=profile duration=3m filename=cpu-incident.jfr
```

Trong lúc recording chạy, tái hiện hoặc chờ workload có vấn đề. Sau khi recording kết thúc, kiểm tra file:

```bash
jfr summary cpu-incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 cpu-incident.jfr
```

### 9.2. Phân tích trong JMC

1. Mở `cpu-incident.jfr` trong JMC.
2. Kiểm tra recording có bao phủ khoảng CPU tăng hay không.
3. Mở trang CPU/Method Profiling và chọn đúng khoảng thời gian.
4. Xem method/call tree có nhiều execution samples.
5. Mở stack trace để tìm code ứng dụng xuất hiện thường xuyên.
6. Đối chiếu thread, GC và I/O để biết CPU tăng do tính toán, GC hay hoạt động khác.

Ví dụ, nếu nhiều sample tập trung ở hàm xử lý JSON, hãy kiểm tra số lần parse, kích thước payload, việc tạo object trung gian và caller. Nếu sample tập trung trong GC, hãy chuyển sang phân tích allocation và GC events.

### 9.3. Kiểm chứng sau khi sửa

Sau khi tối ưu, ghi một recording mới với cấu hình và workload tương tự. So sánh:

- Tỷ lệ execution samples ở method đã sửa.
- CPU load và số thread hoạt động.
- Allocation samples và GC pause.
- Latency/throughput từ metrics.

Không dùng riêng số lượng sample của hai recording có thời lượng, cấu hình hoặc tải khác nhau để kết luận hiệu năng đã cải thiện.

## 10. Ví dụ thực hành: điều tra thread chờ lock

Giả sử latency tăng khi nhiều request cập nhật cùng một cấu trúc dữ liệu.

### 10.1. Ghi recording

```bash
jcmd <pid> JFR.start name=lock-incident settings=profile duration=5m filename=lock-incident.jfr
```

Nếu profile hiện tại không ghi đủ monitor event cho nhu cầu, tạo JFC riêng với threshold phù hợp rồi chạy lại recording.

### 10.2. Tìm contention

Trong JMC:

1. Mở phần Threads hoặc Lock Instances/Lock Profiling.
2. Lọc khoảng latency tăng.
3. Tìm monitor enter hoặc park có duration đáng kể.
4. Mở stack trace của thread chờ.
5. Xác định critical section và luồng code giữ lock nếu recording cung cấp thông tin.
6. Đối chiếu với số request đồng thời và metrics latency.

Nếu thấy nhiều thread cùng chờ một monitor, đó là bằng chứng về contention. Cần xem code để xác định lock được giữ quá lâu, phạm vi lock quá rộng hay một thread giữ lock bị chậm do I/O.

## 11. Ví dụ thực hành: điều tra allocation và GC

Giả sử heap occupancy và GC activity tăng trong giờ cao điểm.

1. Ghi JFR bằng `profile` trong khoảng tải đại diện.
2. Trong JMC, xem GC timeline và pause duration.
3. Xem allocation page/stack để tìm nguồn allocation nổi bật.
4. Tìm method tạo nhiều object tạm hoặc collection tăng liên tục.
5. Đối chiếu heap dump nếu cần biết object nào đang sống và ai giữ tham chiếu.

JFR và heap dump trả lời các câu hỏi khác nhau:

| Công cụ | Câu hỏi |
|---|---|
| JFR allocation events | Object được cấp phát từ stack nào, trong khoảng thời gian nào? |
| JFR GC events | Khi nào GC chạy, pause và các pha GC ra sao? |
| Heap dump | Tại thời điểm dump, object nào còn sống, chiếm bao nhiêu heap và được giữ bởi đường tham chiếu nào? |

Nếu nghi ngờ memory leak, JFR giúp tìm thời điểm allocation hoặc GC bất thường; heap dump và phân tích dominator/reference chain thường cần thiết để xác định object còn reachable vì lý do gì.

## 12. Lưu trữ, chia sẻ và bảo vệ file JFR

Recording là dữ liệu chẩn đoán của ứng dụng và môi trường chạy. Tùy event được bật, file có thể chứa:

- Tên class, method, package và stack trace.
- Tên thread, tên tiến trình và thông tin runtime.
- Đường dẫn file, host hoặc endpoint I/O.
- System properties và dữ liệu từ custom event nếu ứng dụng tự ghi.
- Thông tin triển khai hoặc cấu hình có thể tiết lộ cấu trúc nội bộ.

Vì vậy:

- Lưu recording trong thư mục có quyền truy cập hạn chế.
- Không tải file lên dịch vụ công cộng hoặc đính kèm vào ticket bên ngoài khi chưa xem xét dữ liệu.
- Áp dụng thời hạn lưu và xóa file theo chính sách của tổ chức.
- Chỉ chia sẻ phần dữ liệu cần thiết; có thể trích event đã lọc thay vì gửi toàn recording.
- Kiểm tra dung lượng đĩa khi bật recording liên tục.

Nếu dùng `maxage` và `maxsize`, hãy hiểu rằng đây là giới hạn cho recording repository; chúng không thay thế chính sách backup, retention và kiểm soát quyền truy cập ở tầng lưu trữ.

## 13. Các lỗi thường gặp khi đọc JFR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy file recording | JVM chưa dump, đường dẫn không hợp lệ hoặc tiến trình không có quyền ghi | Kiểm tra output của `JFR.start`, quyền thư mục và trạng thái recording |
| File nhỏ hoặc không có event mong muốn | Event chưa bật, recording quá ngắn hoặc threshold quá cao | Xem `jfr summary`, metadata và file JFC |
| JMC không mở được file | File hỏng, chưa dump hoàn chỉnh hoặc JMC quá cũ | Kiểm tra file, dùng JMC hỗ trợ Java 17 và thử `jfr summary` |
| Không thấy event CPU | Execution sampling chưa bật hoặc khoảng recording không có workload | Kiểm tra event settings và ghi lại trong lúc tái hiện |
| Không thấy I/O ngắn | Threshold event I/O cao hơn duration operation | Điều chỉnh threshold có chủ đích trong JFC |
| Recording quá lớn | Nhiều event, stack trace chi tiết hoặc thời gian ghi dài | Dùng `default`, giới hạn thời gian/dung lượng và lọc event cần thiết |
| CPU tăng sau khi bật recording | Cấu hình quá chi tiết hoặc workload nhạy với instrumentation | Đo overhead, giảm event/stack depth, dùng recording ngắn hơn |
| Hai recording cho kết quả khác khó giải thích | Khác workload, duration, JFC, JDK hoặc mức tải | Chuẩn hóa điều kiện trước khi so sánh |
| Không thấy nguyên nhân dù có recording | Sự cố xảy ra ngoài cửa sổ ghi hoặc event cần thiết không được bật | Mở rộng cửa sổ recording hoặc tạo JFC phù hợp |
| JMC báo cảnh báo nhưng ứng dụng vẫn bình thường | Rule chỉ ra một dấu hiệu, không phải kết luận | Xem event gốc, workload và SLO trước khi thay đổi code |

## 14. Những giới hạn khi diễn giải dữ liệu JFR

### 14.1. Event không phải lúc nào cũng được ghi đầy đủ

JFR dùng cấu hình để cân bằng giữa chi tiết và overhead. Một số event được lấy mẫu, một số chỉ được ghi khi vượt threshold, một số phải bật rõ ràng. Không thấy event trong recording không chứng minh hoạt động đó không xảy ra.

### 14.2. Sample không phải phép đo tuyệt đối

Execution sample và allocation sample hữu ích để tìm xu hướng và điểm nóng. Nhưng chúng không tương đương với việc đếm chính xác mọi method invocation hoặc mọi object allocation. Hãy dùng metrics/benchmark hoặc công cụ chuyên biệt khi cần số liệu chính xác cho một phép đo cụ thể.

### 14.3. JFR không thay heap dump

JFR có thể ghi allocation và GC activity theo thời gian. Nó không cung cấp đầy đủ toàn bộ object graph sống tại một thời điểm như heap dump. Nếu cần tìm object nào giữ tham chiếu tới một object lớn, hãy lấy heap dump và dùng công cụ phân tích heap phù hợp.

### 14.4. JFR không thay thread dump

JFR cho timeline và lịch sử event trong khoảng thời gian recording. Thread dump là snapshot tại một thời điểm, thường hữu ích để xem tất cả thread đang ở đâu. Khi điều tra deadlock hoặc trạng thái tức thời, có thể cần thread dump cùng JFR.

### 14.5. Recording không tự xác định quan hệ nhân quả

Hai event xuất hiện gần nhau không có nghĩa event đầu tiên gây ra event thứ hai. Hãy dùng stack trace, thread identity, timestamp, log, metrics và thử nghiệm để kiểm chứng giả thuyết.

## 15. Các nguyên tắc sử dụng JFR và JMC trong Java 17

- Bắt đầu bằng `default` cho quan sát tổng quát hoặc recording dài hạn.
- Dùng `profile` cho khoảng điều tra ngắn khi cần nhiều event chi tiết hơn.
- Ghi rõ JDK version, cấu hình JFC, thời gian và workload của recording.
- Dùng `jfr summary` trước khi đọc event để xác nhận file và event có sẵn.
- Dùng `jfr print` khi cần kiểm tra nhanh hoặc trích một nhóm event; dùng JMC để xem timeline và stack trace.
- Phân biệt event được lấy mẫu với event được ghi theo threshold.
- Đối chiếu JFR với application logs, metrics và thread/heap dump.
- Không kết luận từ automated analysis mà chưa mở event gốc.
- Giới hạn dung lượng và thời gian lưu recording.
- Bảo vệ file JFR như dữ liệu nội bộ có thể chứa thông tin nhạy cảm.

## 16. Bài tập thực hành

### Bài 1 — Ghi recording trong 60 giây

Khởi động một ứng dụng Java 17 với:

```bash
java -XX:StartFlightRecording:filename=app.jfr,settings=profile,duration=60s \
     -jar app.jar
```

Sau khi ứng dụng chạy xong recording, dùng `jfr summary app.jfr` để xác nhận thời lượng và danh sách event. Ghi lại những event xuất hiện.

### Bài 2 — Attach vào JVM đang chạy

1. Dùng `jcmd -l` để tìm PID.
2. Bắt đầu recording bằng `JFR.start` với tên dễ nhận biết.
3. Kiểm tra bằng `JFR.check`.
4. Dump recording bằng `JFR.dump`.
5. Dừng recording bằng `JFR.stop`.
6. Mở file trong JMC.

Giải thích sự khác nhau giữa dump và stop.

### Bài 3 — Đọc execution samples

Chạy một workload có xử lý CPU. Ghi recording với `profile`, rồi:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 app.jfr
```

Tìm một stack trace xuất hiện nhiều lần. Giải thích vì sao sample count không phải số lần gọi method chính xác.

### Bài 4 — Tìm lock contention

Tạo một workload có nhiều thread cạnh tranh trên cùng một monitor. Ghi JFR, mở JMC và tìm event `jdk.JavaMonitorEnter` hoặc event liên quan đến thread waiting. Xác định stack trace của thread chờ và critical section liên quan.

### Bài 5 — So sánh default và profile

Chạy cùng workload hai lần, một lần với `settings=default` và một lần với `settings=profile`. So sánh:

- Số lượng event.
- Dung lượng file.
- Các event có stack trace.
- Khả năng tìm ra method CPU hoặc allocation nổi bật.

Ghi nhận sự đánh đổi giữa chi tiết dữ liệu và overhead.

### Bài 6 — Phân tích một recording có GC bất thường

Mở recording có nhiều GC pause. Xem timeline GC, heap occupancy, allocation và stack trace allocation sample. Nêu một giả thuyết nguyên nhân và những dữ liệu bổ sung cần có để kiểm chứng.

## 17. Tài liệu chính thức

- [Java 17 jfr command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): cú pháp CLI để xem summary, metadata, in event và cấu hình recording.
- [Java 17 jcmd command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): chẩn đoán tiến trình JVM và các lệnh JFR.
- [Java 17 java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn khởi động recording bằng `-XX:StartFlightRecording`.
- [Java SE 17 API — jdk.jfr](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): API và mô hình event của Java Flight Recorder.
- [JDK Mission Control — Oracle](https://www.oracle.com/java/technologies/jdk-mission-control.html): thông tin về JDK Mission Control.
- [OpenJDK JDK Mission Control](https://github.com/openjdk/jmc): mã nguồn và tài liệu dự án JMC.
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): đưa Flight Recorder thành công nghệ mở trong OpenJDK.

**Ghi nhớ:** JFR ghi lại event của JVM và ứng dụng trong một khoảng thời gian; lệnh `jfr` giúp xem summary, metadata và trích event; JDK Mission Control giúp phân tích timeline, stack trace, CPU, GC, allocation, lock và I/O. Hãy chọn cấu hình recording phù hợp, hiểu giới hạn của sampling/threshold, đối chiếu với log và metrics, đồng thời bảo vệ file recording như dữ liệu chẩn đoán nội bộ.
