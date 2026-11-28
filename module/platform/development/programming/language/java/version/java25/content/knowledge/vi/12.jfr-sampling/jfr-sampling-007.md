# Đọc bản ghi bằng công cụ JFR và phiên bản JDK Mission Control tương thích

> **Chương:** Lấy mẫu JFR  
> **Phạm vi:** Java Flight Recorder (JFR) trên JDK 25 và phân tích bản ghi bằng JDK Mission Control (JMC).  
> **Kết quả:** Tạo được file `.jfr`, kiểm tra bằng công cụ dòng lệnh `jfr`, mở bằng JMC tương thích và lần theo dấu hiệu CPU, allocation, GC, lock hoặc I/O.

## 1. JFR và JDK Mission Control giải quyết hai phần của cùng một quy trình

Khi một dịch vụ Java bị tăng độ trễ, CPU cao hoặc bộ nhớ tăng bất thường, chỉ nhìn log ứng dụng thường chưa đủ. Ta cần biết JVM và ứng dụng đã làm gì trong khoảng thời gian xảy ra sự cố: thread nào đang chạy, phương thức nào xuất hiện nhiều trong mẫu CPU, GC có pause dài không, object được cấp phát ở đâu, thread có chờ monitor hay socket không.

**Java Flight Recorder (JFR)** là cơ chế ghi lại các sự kiện có timestamp ngay trong JVM. Nó lưu dữ liệu vào file nhị phân `.jfr` để có thể phân tích sau khi sự cố xảy ra.

**JDK Mission Control (JMC)** là ứng dụng phân tích và chẩn đoán. JMC đọc file JFR và trình bày dữ liệu thành timeline, bảng, biểu đồ, stack trace và các rule phân tích.

| Thành phần | Vai trò | Có trong JDK 25 không? |
|---|---|---|
| JFR runtime | Thu thập event từ JVM và ứng dụng | Có, tích hợp trong HotSpot |
| `jfr` CLI | Tóm tắt, lọc, in, xem và xử lý file `.jfr` | Có trong `JDK/bin` |
| `jcmd` | Điều khiển recording của JVM đang chạy | Có trong `JDK/bin` |
| JDK Mission Control | Phân tích trực quan file JFR, theo dõi JVM qua JMX | Cài riêng, không phải thành phần mặc định của JDK |
| JFR API | Tạo recording và event tùy chỉnh từ Java code | Có trong module `jdk.jfr` |

~~~mermaid
flowchart LR
    A["Java 25 JVM"] --> B["JFR events\nCPU / GC / allocation / locks"]
    B --> C["Recording .jfr"]
    C --> D["jfr CLI"]
    C --> E["JDK Mission Control"]
    D --> F["Summary / JSON / text"]
    E --> G["Timeline / charts / stack traces"]
    F --> H["Khoanh vùng nguyên nhân"]
    G --> H
~~~

JFR thu thập dữ liệu; JMC giúp đọc và phân tích dữ liệu đó. JMC không phải nơi bắt buộc để tạo recording: có thể tạo recording bằng JVM option hoặc `jcmd`, sau đó chuyển file `.jfr` sang máy phân tích.

## 2. Chọn JDK Mission Control tương thích với Java 25

JDK Mission Control có vòng đời phát hành riêng với JDK. Không nên mặc định phiên bản JMC đi kèm một JDK cũ là phù hợp để đọc mọi recording mới.

Tại thời điểm biên soạn, tài liệu Oracle đang mô tả **JDK Mission Control 9.1.2**. Theo hướng dẫn cài đặt chính thức:

- JMC 9.1.2 cần **Oracle JDK 21 hoặc mới hơn để chạy chính ứng dụng JMC**.
- JMC 9 hỗ trợ JMX monitoring và JFR profiling trên các JVM chạy JDK 7u40 trở lên, trên các nền tảng được hỗ trợ.
- Vì JDK 25 mới hơn JDK 21, có thể dùng JDK 25 để chạy JMC 9.1.2.
- JMC là sản phẩm cài riêng; cài JDK 25 không đồng nghĩa máy đã có JMC.

Tài liệu What's New của Oracle ghi JMC 9.1.2 là bản bảo trì thay thế 9.1.1. Khi cài đặt thực tế, kiểm tra trang download/release notes để chọn bản phát hành ổn định mới nhất mà nhà cung cấp công bố, thay vì tải một build snapshot hoặc bản thử nghiệm cho môi trường production.

### Chọn đúng hai phiên bản

| Việc cần làm | Phiên bản / điều kiện |
|---|---|
| Tạo recording | Dùng JDK 25 của ứng dụng |
| Chạy JMC | JMC 9.1.2; dùng JDK 21+ để khởi chạy JMC |
| Đọc recording JDK 25 | JMC 9 hỗ trợ JFR của JVM từ JDK 7u40 trở lên |
| Dùng `jfr` CLI | Ưu tiên `jfr` thuộc chính JDK 25 đang tạo recording |
| Đọc event mới hoặc event tùy chỉnh | Kiểm tra metadata của file và khả năng hiển thị của JMC; dùng CLI/JFR API nếu giao diện không có trang chuyên biệt |

JMC 9.1.2 có thể chạy bằng JDK 25. Nếu máy cài nhiều JDK, cấu hình launcher JMC để trỏ tới JDK 21+ hoặc JDK 25. Trong `jmc.ini`, đường dẫn `-vm` phải đứng trước `-vmargs`:

~~~text
-vm
C:\Program Files\Java\jdk-25\bin
-vmargs
~~~

Đường dẫn chỉ là ví dụ. Dùng thư mục JDK thực tế của máy, không trỏ tới JRE cũ hoặc một executable Java không xác định.

**Phân biệt:** JDK Mission Control là công cụ đọc/giám sát. JFR là hệ thống event recording trong JVM. Không cần cài một agent JMC vào ứng dụng chỉ để mở một file `.jfr` đã có sẵn.

## 3. Tạo recording từ lúc khởi động ứng dụng

Trước tiên kiểm tra JDK:

~~~bash
java --version
jfr --version
jcmd --version
~~~

Các công cụ `java`, `jfr` và `jcmd` nên đến từ cùng JDK 25 để tránh khác biệt về command options và event metadata.

### 3.1. Recording ngắn với profile.jfc

Ví dụ khởi chạy một service và ghi trong hai phút:

~~~bash
mkdir -p recordings

java \
  -XX:StartFlightRecording:filename=recordings/order-service-profile.jfr,duration=2m,settings=profile.jfc \
  -jar build/libs/order-service.jar
~~~

Các tham số:

- `filename`: file đích để lưu recording.
- `duration=2m`: thời lượng hai phút, sau đó recording dừng.
- `settings=profile.jfc`: cấu hình profile thu thập nhiều dữ liệu hơn cấu hình mặc định.

`profile.jfc` phù hợp cho phiên profiling ngắn khi cần thêm thông tin về CPU, allocation, lock và các event khác. Nó có thể tạo nhiều dữ liệu hơn và tác động hiệu năng cao hơn `default.jfc`; không nên bật một profile nặng liên tục nếu chưa đánh giá overhead.

### 3.2. Recording mặc định để quan sát dài hạn

Đối với recording liên tục, JDK cung cấp `default.jfc` với tập event có overhead thấp hơn:

~~~bash
java \
  -XX:StartFlightRecording:name=continuous,settings=default.jfc,disk=true,maxage=6h,maxsize=500m,dumponexit=true,filename=recordings/order-service-continuous.jfr \
  -jar build/libs/order-service.jar
~~~

`maxage` và `maxsize` giới hạn dữ liệu lưu khi `disk=true`. Cấu hình này hữu ích cho việc giữ lại một cửa sổ quan sát gần đây. Dữ liệu cũ có thể bị loại bỏ khi vượt giới hạn.

Recording mặc định thường phù hợp để quan sát liên tục. Nó không thu mọi loại allocation/heap statistics ở mức chi tiết như profile recording; khi cần điều tra sâu, tạo một recording ngắn hơn với `profile.jfc`.

### 3.3. Chạy workload có thể tái hiện

Không nên tạo recording rồi chỉ để ứng dụng idle. Trong khoảng thời gian ghi, gửi một workload đại diện:

- Một số request đọc dữ liệu.
- Một số request ghi/cập nhật.
- Một luồng tích hợp gọi dependency.
- Một tình huống tải cao có kiểm soát.
- Một kịch bản gây ra độ trễ hoặc allocation tăng.

Ghi lại thời điểm bắt đầu/kết thúc workload và mã request thử nghiệm. Khi phân tích JMC, ta có thể chọn đúng khoảng thời gian tương ứng với sự cố.

Không chạy benchmark nặng tùy tiện trên production chỉ để tạo recording. Hãy dùng môi trường staging hoặc một cửa sổ điều tra được kiểm soát.

## 4. Tạo recording khi JVM đã chạy bằng jcmd

JFR có thể bắt đầu sau khi ứng dụng đã khởi động. Đây là cách hữu ích khi sự cố xuất hiện bất ngờ và không thể restart service để thêm JVM option.

Liệt kê các JVM:

~~~bash
jcmd -l
~~~

Chọn PID của đúng tiến trình ứng dụng, sau đó xem các recording đang hoạt động:

~~~bash
jcmd <PID> JFR.check
~~~

Bắt đầu recording:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile.jfc duration=2m filename=recordings/incident.jfr
~~~

Thay `<PID>` bằng process ID thực tế. Sau hai phút, recording tự dừng và ghi file theo `filename`.

Có thể xem trợ giúp của đúng JVM trước khi chạy:

~~~bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
~~~

### Dump dữ liệu mà không dừng recording

Nếu recording đang chạy và cần lấy snapshot ngay:

~~~bash
jcmd <PID> JFR.dump name=continuous filename=recordings/incident-snapshot.jfr
~~~

Lệnh `JFR.dump` ghi dữ liệu hiện có ra file nhưng **recording tiếp tục chạy**. Điều này hữu ích khi cần lấy snapshot trước khi dữ liệu cũ bị ghi đè bởi giới hạn max age/max size.

### Dừng recording và ghi file

~~~bash
jcmd <PID> JFR.stop name=continuous filename=recordings/continuous-final.jfr
~~~

Nếu `JFR.stop` không có `filename`, dữ liệu của recording bị loại bỏ. Vì vậy, hãy cung cấp đường dẫn file khi muốn giữ lại kết quả.

### Điều kiện khi dùng jcmd

- Chạy trên cùng máy với JVM đích.
- Dùng cùng effective user/group ID đã khởi chạy JVM.
- Trong container riêng, PID có thể khác PID trên host; cần xác định PID trong đúng namespace.
- Nếu JVM không xuất hiện trong `jcmd -l`, kiểm tra quyền, user và môi trường container trước.

## 5. Kiểm tra file .jfr trước khi mở JMC

File `.jfr` là file nhị phân, không nên mở bằng text editor để đọc trực tiếp. Bắt đầu bằng công cụ `jfr` của JDK 25.

### 5.1. Kiểm tra file đã được tạo

~~~bash
ls -lh recordings/incident.jfr
~~~

Trên Windows PowerShell:

~~~powershell
Get-Item .\recordings\incident.jfr
~~~

File tồn tại và có kích thước lớn hơn 0 là điều kiện ban đầu, chưa chứng minh file đã đầy đủ hoặc có event cần tìm.

### 5.2. Đọc summary

~~~bash
jfr summary recordings/incident.jfr
~~~

Summary cho biết thông tin tổng quan của recording, bao gồm số lượng event theo loại và dung lượng dữ liệu. Dùng nó để trả lời:

- Recording có bao nhiêu event?
- Event nào chiếm số lượng lớn?
- File có vẻ ghi được dữ liệu trong khoảng thời gian mong đợi không?
- Event cần phân tích có xuất hiện hay không?

Nếu summary gần như không có event, kiểm tra lại thời lượng recording, settings và workload đã chạy trong khoảng thời gian ghi.

### 5.3. Xem danh sách event và metadata

~~~bash
jfr metadata recordings/incident.jfr
~~~

Lọc metadata của event CPU sample:

~~~bash
jfr metadata --events jdk.ExecutionSample recordings/incident.jfr
~~~

Metadata giúp xem event name, category và field layout được lưu trong file. Đây là bước hữu ích khi JMC không có trang chuyên biệt cho event tùy chỉnh hoặc event mới.

### 5.4. In event có chọn lọc

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 20 recordings/incident.jfr
~~~

Có thể in nhiều event:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad recordings/incident.jfr
~~~

Hoặc in theo category:

~~~bash
jfr print --categories GC recordings/incident.jfr
~~~

Nếu cần dữ liệu máy đọc được:

~~~bash
jfr print --json --events jdk.ExecutionSample recordings/incident.jfr
~~~

`jfr print` hỗ trợ lọc theo event/category và giới hạn stack depth. Không nên in toàn bộ event của recording lớn ra terminal; lọc theo loại cần điều tra để tránh output quá dài.

### 5.5. Xem dữ liệu đã tổng hợp

~~~bash
jfr view all-views recordings/incident.jfr
jfr view types recordings/incident.jfr
jfr view all-events recordings/incident.jfr
~~~

Sau khi xem danh sách, chọn view hoặc event phù hợp:

~~~bash
jfr view <view-name> recordings/incident.jfr
~~~

Tên view có thể thay đổi theo JDK release và nội dung file. Hãy lấy tên thực tế từ `all-views` hoặc `types`, không đoán tên view từ một bản JDK khác.

## 6. Mở file JFR bằng JDK Mission Control

Sau khi có file recording:

1. Cài JMC 9.1.2 hoặc bản ổn định mới hơn có hỗ trợ recording mục tiêu.
2. Khởi chạy JMC bằng JDK 21+ (có thể dùng JDK 25).
3. Trong JMC, chọn **File → Open File...**.
4. Chọn file `recordings/incident.jfr`.
5. Chờ JMC phân tích file và mở trang tổng quan Flight Recording.
6. Lưu bản phân tích hoặc ghi lại các mốc thời gian/stack trace quan trọng nếu cần chia sẻ với nhóm.

JMC cũng có thể mở file bằng cách kéo thả `.jfr` vào cửa sổ ứng dụng trên các nền tảng hỗ trợ. Nếu file lớn, quá trình parse có thể mất thời gian và cần bộ nhớ cho chính ứng dụng JMC.

### Các khu vực nên xem trước

| Khu vực trong JMC | Câu hỏi cần trả lời |
|---|---|
| Overview | Recording bắt đầu/kết thúc lúc nào? JVM, JDK và thời lượng nào được ghi? |
| Event Browser | Event nào có mặt, số lượng và field nào đáng chú ý? |
| Java Application | CPU, heap, GC và trạng thái ứng dụng thay đổi thế nào? |
| Threads | Thread nào chạy, chờ, block hoặc park trong khoảng sự cố? |
| Memory | Heap, allocation và object pressure có bất thường không? |
| Garbage Collections | GC có xảy ra dồn dập hoặc pause dài không? |
| Method Profiling / Code | Stack trace nào xuất hiện nhiều trong mẫu CPU hoặc allocation? |
| Lock Instances / Synchronization | Có contention hoặc thread chờ monitor kéo dài không? |

Tên và sự hiện diện của từng trang phụ thuộc JMC version, event settings và nội dung recording. Một trang trống không nhất thiết có nghĩa ứng dụng không gặp vấn đề; có thể event cần thiết chưa được bật hoặc recording không bao phủ khoảng thời gian đó.

## 7. Đọc dữ liệu sampling: mẫu CPU không phải số lần gọi method chính xác

JFR có nhiều loại event: event tức thời, event có duration, event định kỳ và event do ứng dụng tự định nghĩa. Sampling event lấy mẫu trạng thái tại các thời điểm nhất định để ước lượng hành vi trong một khoảng thời gian.

Ví dụ, `jdk.ExecutionSample` ghi nhận stack của thread đang thực thi tại thời điểm lấy mẫu. Nếu một method xuất hiện trong nhiều mẫu, đó là dấu hiệu method hoặc các frame con của nó chiếm nhiều thời gian CPU tương đối trong khoảng được ghi.

**Không diễn giải số mẫu như số lần gọi method.** Một method xuất hiện 500 lần trong event sampling không có nghĩa method đó được gọi chính xác 500 lần. Sampling có thể bỏ lỡ method ngắn hoặc thiên lệch theo cách lấy mẫu/safepoint.

### Cách đọc stack trace

Một stack trace có thể biểu diễn như:

~~~text
jdk.ExecutionSample
  com.example.orders.PricingService.calculate
  com.example.orders.OrderService.create
  com.example.orders.OrderController.submit
  ...
~~~

Đọc từ frame cụ thể lên các caller:

1. Tìm method xuất hiện nhiều trong các mẫu.
2. Xác định nó là code nghiệp vụ, thư viện hay framework.
3. Nhìn các frame phía trên để biết đường gọi đến method đó.
4. So sánh trong cùng khoảng thời gian với CPU load, GC và thread state.
5. Kiểm tra code thực tế trước khi kết luận cần tối ưu.

Nếu phần lớn mẫu tập trung trong một phép tính CPU-bound, tối ưu thuật toán có thể hữu ích. Nếu thread chủ yếu ở trạng thái chờ I/O hoặc monitor, tối ưu CPU của method không giải quyết nguyên nhân gốc.

## 8. Đọc các nhóm event thường dùng

| Nhóm cần điều tra | Event / dữ liệu thường xem | Dấu hiệu cần tìm |
|---|---|---|
| CPU sampling | `jdk.ExecutionSample` | Stack trace nào chiếm nhiều mẫu |
| CPU load | `jdk.CPULoad` | CPU JVM và máy có tăng cao không |
| Native execution sampling | `jdk.NativeMethodSample` nếu được ghi | Thời gian ở native method |
| Allocation sampling | `jdk.ObjectAllocationSample` | Loại object và stack trace cấp phát |
| Garbage collection | `jdk.GarbageCollection`, `jdk.GCPhasePause` | Tần suất, duration và pause |
| Monitor contention | `jdk.JavaMonitorEnter` | Thread chờ monitor và stack trace |
| Thread park | `jdk.ThreadPark` | Thread chờ lock/condition hoặc cơ chế đồng bộ |
| Socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` | Độ dài và thời gian thao tác socket |
| Thread lifecycle | `jdk.ThreadStart`, `jdk.ThreadEnd` | Tạo quá nhiều thread hoặc vòng đời bất thường |

Tên event và cấu hình ghi phụ thuộc JDK/provider. Dùng `jfr metadata` hoặc `jfr view types` trên file thật để xác minh event có được ghi và có field nào.

### CPU cao

- Tìm các stack trace xuất hiện nhiều trong Execution Samples.
- So sánh CPU load của JVM và CPU toàn máy.
- Xem có nhiều thread cùng chạy một đoạn code hay một thread đơn lẻ chiếm CPU.
- Kiểm tra các vòng lặp, serialization, regex, xử lý collection hoặc tính toán lặp.

### Allocation/GC tăng

- Tìm event allocation sample và stack trace cấp phát.
- Đối chiếu với heap/GC timeline.
- Kiểm tra object được tạo nhiều có thể tái sử dụng hoặc tránh boxing/copy không.
- Không kết luận memory leak chỉ từ một đỉnh allocation; cần xem xu hướng heap/live objects và các recording qua thời gian.

### Lock contention

- Xem monitor enter/park và thread state.
- Xác định lock nào có nhiều thread chờ.
- Tìm stack trace giữ lock và stack trace chờ lock.
- Kiểm tra vùng critical section có chứa I/O hoặc công việc lâu không.

### Độ trễ I/O

- Xem socket read/write duration và thread đang thực hiện.
- Đối chiếu timestamp với log ứng dụng và trace ID nếu ứng dụng tự ghi event tương ứng.
- JFR ghi dữ liệu JVM; nó không tự động cung cấp toàn bộ ngữ cảnh nghiệp vụ như mã đơn hàng hoặc user nếu ứng dụng không instrument.

## 9. So sánh default.jfc và profile.jfc

JDK 25 có hai cấu hình tiêu chuẩn nằm trong `$JAVA_HOME/lib/jfr`:

| Cấu hình | Mục đích | Đặc điểm |
|---|---|---|
| `default.jfc` | Recording liên tục | Thu tập event hữu ích với overhead thấp, phù hợp quan sát dài hạn |
| `profile.jfc` | Profiling trong thời gian ngắn | Thu nhiều dữ liệu hơn, có thể tăng overhead và ảnh hưởng hiệu năng |

Có thể xem file cấu hình đang dùng:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/default.jfc" --output custom.jfc
~~~

Để chỉnh event setting, dùng `jfr configure` với tên event và setting cụ thể:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output custom-profile.jfc jdk.ExecutionSample#enabled=true
~~~

Cú pháp event setting có dạng `<event-name>#<setting-name>=<value>`. Kiểm tra trợ giúp của đúng JDK:

Trên Windows PowerShell, dùng đường dẫn tương ứng như `"$env:JAVA_HOME\lib\jfr\profile.jfc"`. Nếu dùng JDK được cài ở vị trí khác, hãy thay đường dẫn theo thư mục JDK đang chạy.

~~~bash
jfr help configure
~~~

Không sửa trực tiếp các file `default.jfc` hoặc `profile.jfc` do JDK cung cấp. Hãy tạo file custom riêng, lưu cùng pipeline/configuration và ghi nhận phiên bản settings để có thể tái tạo recording.

## 10. Từ dữ liệu sang kết luận: quy trình phân tích có thể lặp lại

Một bản recording có thể chứa hàng nghìn hoặc hàng triệu event. Phân tích hiệu quả cần bắt đầu từ giả thuyết, không phải mở mọi bảng rồi tìm một con số nổi bật.

### Quy trình 7 bước

1. **Xác định thời điểm:** dùng log/metric để xác định khoảng thời gian độ trễ hoặc lỗi xuất hiện.
2. **Kiểm tra recording:** chạy `jfr summary` và xác nhận file bao phủ khoảng thời gian đó.
3. **Chọn event:** dùng `jfr metadata` hoặc Event Browser để xác nhận event cần điều tra đã được ghi.
4. **Chọn nhóm dữ liệu:** CPU, allocation, GC, locks, threads hoặc I/O.
5. **Lọc thời gian:** chọn khoảng bắt đầu trước khi sự cố xảy ra và kết thúc sau khi hệ thống phục hồi.
6. **Đọc stack/context:** tìm thread, stack trace và event liên quan.
7. **Đối chiếu giả thuyết:** so với log, metric, trace phân tán và thay đổi deploy trước khi kết luận.

~~~mermaid
flowchart TD
    A["Có sự cố latency / CPU / memory"] --> B["Xác định time window"]
    B --> C["jfr summary / metadata"]
    C --> D["Chọn event và trang JMC"]
    D --> E["Lọc timeline + stack traces"]
    E --> F["Đối chiếu logs / metrics / traces"]
    F --> G["Giả thuyết nguyên nhân"]
    G --> H["Tạo workload tái hiện và kiểm chứng"]
~~~

### Ví dụ: API create order tăng latency

Giả sử p95 latency tăng từ 120 ms lên 900 ms. JFR cho thấy:

- CPU load không tăng đáng kể.
- Nhiều thread có event `jdk.JavaMonitorEnter` kéo dài.
- Các stack trace chờ cùng một monitor nằm trong đoạn cập nhật cache.
- GC pause không thay đổi đáng kể.

Giả thuyết hợp lý là contention trên cache lock, không phải CPU thiếu hoặc GC. Bước tiếp theo là kiểm tra vùng critical section, giảm thời gian giữ lock hoặc thay cấu trúc đồng bộ; sau đó ghi JFR mới để so sánh cùng workload.

Ví dụ này minh họa cách suy luận, không phải kết luận có thể áp dụng cho mọi recording.

## 11. Làm sạch recording trước khi chia sẻ

JFR có thể chứa thông tin nhạy cảm tùy event settings và ứng dụng: đường dẫn file, tên thread, địa chỉ mạng, thông tin môi trường, chuỗi truy vấn hoặc dữ liệu do custom event ghi vào.

Trước khi gửi recording ra ngoài tổ chức:

1. Kiểm tra nội dung event và metadata.
2. Xác định trường nào không được chia sẻ.
3. Dùng `jfr scrub` để loại event/category/thread không cần thiết nếu phù hợp.
4. Mở lại file đã scrub bằng `jfr summary` và JMC để xác nhận dữ liệu cần thiết vẫn còn.
5. Chia sẻ file theo chính sách truy cập và thời hạn lưu trữ của tổ chức.

Ví dụ chỉ giữ event CPU và GC (đổi tên file đầu ra riêng):

~~~bash
jfr scrub \
  --include-events jdk.ExecutionSample,jdk.CPULoad \
  --include-categories GC \
  recordings/incident.jfr \
  recordings/incident-scrubbed.jfr
~~~

Lệnh scrub thay đổi tập event được giữ lại; nó không hiểu mọi quy tắc phân loại dữ liệu nhạy cảm của doanh nghiệp. Không giả định scrub một nhóm event sẽ tự động xóa mọi thông tin nhạy cảm còn lại. Hãy kiểm tra file đầu ra trước khi chia sẻ.

## 12. Tạo bản ghi có thể tái hiện và lưu cùng báo cáo sự cố

Một file JFR có giá trị hơn khi đi kèm thông tin đủ để hiểu cách nó được tạo.

Có thể lưu manifest text cùng recording:

~~~text
application=order-service
application-version=2.7.4
jdk-vendor=Eclipse Temurin
jdk-version=25.0.x
jmc-version=9.1.2
recording-file=incident.jfr
settings=profile.jfc
duration=2m
environment=staging
workload=checkout-readwrite-v3
incident-window=2026-11-27T10:00:00Z/2026-11-27T10:02:00Z
~~~

Các giá trị trên chỉ là ví dụ. Không ghi secret, token hoặc thông tin định danh người dùng vào manifest.

Lưu lại:

- Phiên bản JDK tạo recording.
- Phiên bản JMC dùng để phân tích.
- File settings `.jfc`.
- Thời lượng và thời điểm ghi.
- Workload đã chạy.
- Các lệnh đã dùng để tạo/dump recording.
- Những giả thuyết được xác nhận hoặc bác bỏ.

Nếu ứng dụng dùng custom JFR events, lưu kèm phiên bản code/schema để người đọc hiểu ý nghĩa các field.

## 13. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JMC không khởi chạy | JMC launcher đang dùng JDK cũ hơn mức yêu cầu | Cấu hình `jmc.ini` dùng JDK 21+ |
| JMC mở file nhưng không có trang phân tích mong đợi | Recording không bật event tương ứng hoặc JMC không có trang chuyên biệt | Kiểm tra `jfr metadata`, Event Browser và settings |
| `jfr` không nhận file | File chưa ghi xong, sai đường dẫn hoặc file hỏng | Kiểm tra tiến trình ghi, file size và summary |
| `jfr summary` báo file không hợp lệ | File bị truncate, copy khi chưa hoàn tất hoặc chunk bị lỗi | Dump lại bằng `JFR.dump`/`JFR.stop`; kiểm tra repository/chunk nếu JVM crash |
| Recording quá nhỏ, gần như không có event | Recording quá ngắn hoặc workload không chạy | Tăng thời lượng, chạy workload đại diện và xem settings |
| Recording rất lớn | Profile nhiều event, thời gian dài hoặc không giới hạn disk | Dùng duration/maxsize/maxage và lọc event cần thiết |
| Không thấy CPU samples | Settings không bật sampling hoặc recording không bao phủ workload | Kiểm tra event metadata và dùng profile settings cho thời gian ngắn |
| Stack trace quá ngắn | `jfr print` mặc định chỉ in một số frame | Tăng `--stack-depth`; trong JMC mở stack trace chi tiết nếu có |
| Không thấy object allocation | `default.jfc` không bật mức allocation profiling cần thiết | Tạo recording ngắn với `profile.jfc` hoặc custom settings |
| `jcmd` không tìm thấy JVM | Khác user, host/container hoặc PID namespace | Chạy cùng user trên đúng host/namespace |
| JMC không kết nối được JVM từ xa | JMX chưa cấu hình hoặc mạng/quyền truy cập không cho phép | Kiểm tra JMX agent và firewall; file JFR local không cần remote JMX |
| File được tạo nhưng không chứa khoảng sự cố | Recording bắt đầu muộn hoặc dừng sớm | Đồng bộ timestamp với log/metric và ghi lại khoảng phù hợp |
| JMC parse file lớn quá lâu | Recording chứa quá nhiều event hoặc máy phân tích thiếu memory | Lọc bằng `jfr scrub`, phân tích bằng CLI hoặc tăng tài nguyên JMC |
| Không nhận ra event custom | JMC chưa có metadata/plugin tương ứng hoặc event không được ghi | Dùng `jfr metadata`, `jfr print` và JFR API |

## 14. Checklist thực hành

- [ ] Dùng JDK 25 để tạo recording và chạy công cụ `jfr`/ `jcmd`.
- [ ] Chọn JMC 9.1.2 hoặc bản ổn định tương thích; JMC được chạy bằng JDK 21+.
- [ ] Biết phân biệt `default.jfc` cho quan sát liên tục với `profile.jfc` cho profiling ngắn.
- [ ] Tạo được recording khi khởi động bằng `-XX:StartFlightRecording`.
- [ ] Bắt đầu, kiểm tra, dump và dừng recording runtime bằng `jcmd`.
- [ ] Dùng `jfr summary`, `metadata`, `print` và `view` để kiểm tra file.
- [ ] Mở file `.jfr` trong JMC và đọc timeline/stack trace.
- [ ] Biết rằng Execution Samples là dữ liệu lấy mẫu, không phải bộ đếm chính xác số lần gọi method.
- [ ] Đối chiếu CPU, allocation, GC, lock và I/O theo giả thuyết điều tra.
- [ ] Lưu lại JDK/JMC version, settings, workload và time window.
- [ ] Kiểm tra dữ liệu nhạy cảm và scrub file trước khi chia sẻ.

### Bài tập tổng hợp

Một API `POST /orders` có p95 tăng từ 100 ms lên 800 ms sau một lần triển khai.

1. Tạo recording hai phút với `profile.jfc`.
2. Gửi workload gồm request hợp lệ và request có tranh chấp cập nhật cùng một tài nguyên.
3. Chạy `jfr summary` và xác nhận có CPU, thread và lock events.
4. Mở file trong JMC 9.1.2.
5. Tìm khoảng thời gian p95 tăng và lọc các thread có thời gian chờ monitor.
6. Đọc stack trace để xác định vị trí giữ lock.
7. So sánh với GC timeline để loại trừ giả thuyết GC pause.
8. Đề xuất một thay đổi, chạy lại workload và ghi một recording mới để kiểm chứng.

**Câu hỏi tự kiểm tra:**

1. Vì sao JFR và JMC là hai thành phần khác nhau?
2. JMC 9.1.2 cần JDK nào để chạy chính công cụ, và hỗ trợ phân tích JVM từ phiên bản nào?
3. Khi nào dùng `default.jfc`, khi nào dùng `profile.jfc`?
4. `JFR.dump` khác `JFR.stop` thế nào?
5. Vì sao 500 Execution Samples không đồng nghĩa method được gọi chính xác 500 lần?
6. Nếu JMC không có trang cho custom event, có thể dùng công cụ nào để đọc metadata và event?
7. Vì sao cần kiểm tra recording trước khi chia sẻ ra ngoài tổ chức?

## 15. Tài liệu chính thức

- [Oracle JDK 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `print`, `view`, `metadata`, `configure`, `scrub`, `assemble` và `disassemble`.
- [Oracle JDK 25 — The java Command: StartFlightRecording](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): bắt đầu recording khi JVM khởi động, cấu hình duration, filename và settings.
- [Oracle JDK 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle JDK 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): đọc recording bằng JFR CLI, JFR API và JMC.
- [Oracle — JDK Mission Control 9 Installation Instructions](https://www.oracle.com/java/technologies/javase/jmc9-install.html): yêu cầu JDK 21+ để chạy JMC 9.1.2 và khả năng phân tích JFR từ JDK 7u40+.
- [Oracle — What's New in JDK Mission Control 9](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/whats-new-jdk-mission-control.html): các thay đổi của JMC 9.1.2 và 9.1.x.
- [Oracle JMC 9 — Flight Recorder User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): loại recording, template, cách tạo và phân tích dữ liệu JFR.
- [Oracle Java SE 25 — JFR API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/module-summary.html): API JFR và khả năng ghi event tùy chỉnh.

> **Ghi nhớ:** JFR thu thập event và lưu file `.jfr`; công cụ `jfr` giúp kiểm tra/lọc dữ liệu, còn JMC giúp phân tích trực quan. Với Java 25, JMC 9.1.2 chạy bằng JDK 21+ và hỗ trợ JFR trên JVM JDK 7u40 trở lên. Bắt đầu bằng `jfr summary`, sau đó mở JMC và tập trung vào đúng time window, event và stack trace liên quan đến giả thuyết sự cố.
