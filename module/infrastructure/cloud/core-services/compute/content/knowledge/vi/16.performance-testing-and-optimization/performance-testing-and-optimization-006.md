# Tối ưu JVM, heap và garbage collection trên tài nguyên cloud

## Mục tiêu bài học

Ứng dụng Java chạy trên máy ảo hoặc container cần chia sẻ tài nguyên CPU và bộ nhớ với hệ điều hành, agent giám sát và các workload khác. JVM quản lý heap, thread, class metadata, code cache và nhiều vùng native memory. Nếu chỉ đặt heap càng lớn càng tốt hoặc chọn garbage collector theo cảm tính, ứng dụng có thể gặp pause dài, CPU bị throttling, container bị OOM kill hoặc chi phí compute tăng mà hiệu năng không cải thiện.

Tối ưu JVM trên cloud là quá trình đo tải thực tế, phân bổ bộ nhớ có headroom, chọn garbage collector phù hợp với mục tiêu latency/throughput và kiểm chứng từng thay đổi dưới điều kiện gần production.

Sau bài học này, bạn có thể:

- Phân biệt heap, non-heap và native memory của JVM.
- Ước lượng heap phù hợp với giới hạn RAM của VM hoặc container.
- Hiểu cách CPU quota và cgroup ảnh hưởng đến JVM và garbage collection.
- Chọn collector theo mục tiêu throughput, latency và kích thước heap.
- Thu thập GC log, JFR, JMX và các chỉ số JVM quan trọng.
- Thiết kế benchmark, thử nghiệm tải và rollout thay đổi có kiểm soát.
- Chẩn đoán memory leak, allocation pressure, long pause và OOM.

## 1. Vì sao cần tối ưu JVM trên cloud?

JVM cung cấp môi trường thực thi và quản lý bộ nhớ cho ứng dụng Java. Garbage collector (GC) tự động thu hồi object không còn được tham chiếu, giúp lập trình viên giảm công việc quản lý bộ nhớ thủ công. Tuy nhiên, GC vẫn tiêu thụ CPU, dùng bộ nhớ phụ trợ và có thể tạo các khoảng dừng hoặc biến động độ trễ.

Trên cloud, tài nguyên thường được giới hạn theo kích thước VM, loại instance, CPU quota, memory limit hoặc chính sách của nền tảng điều phối. Một JVM có thể nhìn thấy số CPU hoặc RAM khác với kỳ vọng nếu phiên bản JDK chưa nhận diện đúng cgroup. Một container có heap còn trống vẫn có thể bị hệ điều hành kết thúc vì tổng RSS, direct buffer, thread stack và native memory vượt memory limit.

Các triệu chứng thường gặp:

- CPU tăng cao dù request rate không đổi vì GC chạy thường xuyên.
- Độ trễ p99 tăng khi có stop-the-world pause hoặc CPU throttling.
- Heap tăng dần sau mỗi chu kỳ GC, có thể do live set tăng hoặc memory leak.
- Full GC xảy ra liên tục, allocation bị chậm hoặc ứng dụng gần như ngừng xử lý.
- Container bị OOMKilled dù heap chưa chạm Xmx.
- JVM khởi động chậm hoặc warm-up làm latency tăng sau scale-out.
- Tăng heap hoặc số vCPU làm chi phí cloud tăng nhưng throughput không cải thiện.

Một cấu hình tốt cần cân bằng ba mục tiêu: throughput, latency và mức tiêu thụ tài nguyên. Không thể tối ưu một chỉ số riêng lẻ mà bỏ qua hai chỉ số còn lại.

~~~mermaid
flowchart TD
    A["Tải ứng dụng và SLO"] --> B["Đo CPU, heap, native memory và GC"]
    B --> C["Xác định nút thắt"]
    C --> D["Điều chỉnh heap, collector hoặc CPU"]
    D --> E["Benchmark dưới tải đại diện"]
    E --> F{"Đạt SLO và headroom?"}
    F -->|Có| G["Canary và rollout"]
    F -->|Không| C
    G --> H["Theo dõi production"]
~~~

## 2. JVM sử dụng những vùng bộ nhớ nào?

Không phải toàn bộ bộ nhớ của một tiến trình Java đều nằm trong heap. Khi tính memory limit cho VM hoặc container, cần tính cả vùng do JVM quản lý và phần native mà JVM hoặc thư viện sử dụng.

| Thành phần | Nội dung | Dấu hiệu cần theo dõi |
|---|---|---|
| Java heap | Object, array và phần lớn dữ liệu tạo bởi ứng dụng | Used, committed, max, old/young generation, allocation rate |
| Metaspace | Metadata của class và classloader | Used/committed, số class được nạp, classloader bị giữ |
| Code cache | Mã máy được JIT compiler sinh ra | Used, free và tình trạng đầy code cache |
| Thread stack | Stack cho mỗi Java thread | Số thread, stack size và native memory |
| Direct/off-heap buffer | Buffer ngoài heap, thường dùng cho I/O và network | Direct memory usage, số buffer và giới hạn |
| GC/JIT/native structures | Cấu trúc nội bộ của JVM và collector | Native memory, GC worker và compiler thread |
| JNI/native library | Thư viện C/C++, driver và vùng nhớ cấp phát ngoài heap | RSS, native allocation và leak trong thư viện |
| Memory-mapped file | File được ánh xạ vào address space | Mapped memory, page residency và giới hạn hệ điều hành |

Heap là vùng dễ nhìn thấy nhất qua các công cụ Java, nhưng không đại diện cho tổng bộ nhớ của tiến trình. RSS của process còn phụ thuộc các trang đã resident trong RAM, native allocation, mapped file và cách hệ điều hành quản lý memory.

### 2.1. Heap reserved, committed và used

Ba khái niệm này cần phân biệt:

- **Max/reserved:** giới hạn tối đa mà JVM có thể dùng cho heap theo cấu hình và ergonomics.
- **Committed:** phần heap JVM đã cam kết có thể sử dụng.
- **Used:** phần heap hiện chứa object đang được cấp phát.

Used thường nhỏ hơn hoặc bằng committed; committed không nhất thiết bằng max. Reserved address space cũng không đồng nghĩa toàn bộ dung lượng đã chiếm RAM vật lý.

Sau GC, used có thể giảm nhưng committed có thể vẫn giữ cao để JVM tái sử dụng nhanh. Vì vậy, biểu đồ heap committed không giảm không tự động chứng minh memory leak.

### 2.2. Live set và allocation rate

**Live set** là lượng object còn được giữ sau khi GC đã thu hồi các object không còn cần thiết, tại một trạng thái tải cụ thể. Live set tăng liên tục qua nhiều chu kỳ GC có thể là dấu hiệu ứng dụng giữ thêm dữ liệu hoặc cache không có giới hạn.

**Allocation rate** là tốc độ ứng dụng tạo object, thường đo bằng byte/giây. Allocation rate cao có thể tạo nhiều young GC, nhưng nếu object chết nhanh và GC xử lý hiệu quả thì đó chưa chắc là vấn đề.

Để chọn heap, cần quan sát cả live set, allocation rate, thời gian giữ object, tốc độ promotion sang old generation và headroom dành cho burst. Không nên chọn Xmx chỉ dựa trên heap used ở một thời điểm.

## 3. Phân bổ heap trong giới hạn RAM cloud

### 3.1. Tính cả bộ nhớ ngoài heap

Giả sử một container có memory limit 4 GiB. JVM không thể dùng toàn bộ 4 GiB làm heap vì còn cần memory cho:

- Metaspace và code cache.
- Thread stack của request thread, worker, GC và compiler.
- Direct buffer của NIO, HTTP client và framework.
- Native library, TLS, compression và driver.
- GC bookkeeping và cấu trúc JVM.
- Agent giám sát, sidecar và tiến trình phụ nếu chúng dùng chung giới hạn cgroup.
- Phần dự phòng cho spike, page cache và biến động runtime.

Một cách ước lượng ban đầu là dành phần lớn RAM cho heap nhưng vẫn giữ headroom đủ lớn cho native memory và biến động. Ví dụ minh họa với container 4 GiB có thể bắt đầu thử heap max khoảng 2.5–2.8 GiB, sau đó đo RSS, native memory, GC và tải thực tế để điều chỉnh. Đây không phải tỷ lệ cố định cho mọi ứng dụng.

~~~mermaid
flowchart TD
    A["Memory limit của container / VM"] --> B["Heap"]
    A --> C["Metaspace và code cache"]
    A --> D["Thread stacks"]
    A --> E["Direct buffers và native libraries"]
    A --> F["GC/JIT và runtime overhead"]
    A --> G["Agent, sidecar và headroom"]
~~~

Nếu đặt Xmx sát memory limit, ứng dụng có thể bị OOM kill trước khi Java ném OutOfMemoryError. Hệ điều hành hoặc container runtime nhìn tổng bộ nhớ của cgroup, không chỉ heap.

### 3.2. Cấu hình Xms và Xmx

- Xms đặt kích thước heap ban đầu.
- Xmx đặt giới hạn heap tối đa.

Ví dụ:

~~~bash
java -Xms1g -Xmx3g -jar orders-service.jar
~~~

Heap ban đầu 1 GiB và tối đa 3 GiB. JVM có thể tăng heap khi cần. Cấu hình Xms bằng Xmx giúp kích thước heap ổn định hơn trong một số workload, nhưng có thể làm tăng mức memory cam kết sớm và giảm khả năng co giãn. Không nên đặt Xms = Xmx theo thói quen nếu container có memory limit chặt.

Khi sizing, hãy thử nhiều giá trị Xmx và đo:

- Live set sau các chu kỳ GC ổn định.
- Allocation rate và tần suất GC.
- Pause time và tail latency.
- RSS/working set và native memory.
- OOM hoặc memory pressure của cgroup.
- Throughput trên mỗi vCPU và chi phí mỗi request.

### 3.3. Dùng tỷ lệ RAM thay cho Xmx cố định

Các JVM hiện đại có thể hỗ trợ cờ phần trăm RAM như:

~~~bash
java -XX:InitialRAMPercentage=30.0 \
     -XX:MaxRAMPercentage=65.0 \
     -jar orders-service.jar
~~~

MaxRAMPercentage giúp JVM tính giới hạn heap dựa trên lượng RAM mà runtime nhận diện được. InitialRAMPercentage ảnh hưởng heap ban đầu. Tên cờ, giá trị mặc định và cách nhận diện container phụ thuộc phiên bản JDK và vendor.

Cách này hữu ích khi cùng một image được chạy với nhiều memory limit khác nhau. Tuy nhiên, phải xác minh JVM thực sự nhận diện giới hạn cgroup. Với JDK cũ hoặc cấu hình container đặc biệt, JVM có thể tính theo RAM của host thay vì memory limit của container.

Kiểm tra flags và thông tin JVM:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Trên các JDK hỗ trợ cgroup awareness, kiểm tra thêm thông tin runtime và container bằng công cụ JVM hoặc log khởi động. Không suy ra heap max chỉ từ YAML Kubernetes; hãy xác nhận giá trị mà tiến trình thực sự sử dụng.

### 3.4. Ví dụ sizing trong Kubernetes

Một Deployment có memory request 3 GiB và limit 4 GiB có thể bắt đầu với cấu hình heap tối đa khoảng 65% limit:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-service:2.1.0
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:InitialRAMPercentage=30.0 -XX:MaxRAMPercentage=65.0 -XX:+UseG1GC"
          resources:
            requests:
              cpu: "1"
              memory: 3Gi
            limits:
              cpu: "2"
              memory: 4Gi
~~~

Ví dụ chỉ là điểm bắt đầu. Request và limit cần dựa trên tải, QoS, node capacity và chính sách cluster. Kubernetes thường áp dụng memory request/limit riêng cho từng container; hãy sizing heap theo limit của container ứng dụng và sizing sidecar theo limit riêng của nó. Nếu nền tảng hoặc runtime có thêm giới hạn cgroup ở cấp Pod, hãy xác minh giới hạn thực tế mà tiến trình nhìn thấy. Kiểm tra container không bị OOMKilled và heap max được JVM nhận diện đúng.

## 4. CPU quota và JVM trên máy ảo/container

JVM sử dụng số CPU khả dụng để quyết định số thread cho GC, JIT compiler, ForkJoinPool và một số cơ chế runtime. Trong container, CPU limit có thể được áp dụng bằng quota/cgroup. Nếu JVM không nhận diện đúng CPU quota, nó có thể tạo quá nhiều thread so với năng lực CPU thực tế.

Hậu quả có thể gồm:

- Context switch tăng.
- GC worker tranh CPU với application thread.
- Concurrent GC không có đủ CPU để hoàn thành kịp thời.
- CPU throttling làm pause hoặc request latency kéo dài.
- Thread pool mặc định lớn hơn mức phù hợp với container.

Các JDK hiện đại có hỗ trợ container awareness, nhưng mức hỗ trợ phụ thuộc phiên bản và vendor. Xác minh số processor mà JVM nhìn thấy, thay vì giả định JVM luôn biết đúng quota.

Một số lệnh kiểm tra:

~~~bash
# Xem thông tin CPU mà hệ điều hành guest nhìn thấy
nproc
lscpu

# Xem JVM flags và thông tin runtime
jcmd <pid> VM.info
jcmd <pid> VM.flags
~~~

Nếu cần, JVM có cờ ActiveProcessorCount để chỉ định số CPU mà JVM nên coi là khả dụng:

~~~bash
java -XX:ActiveProcessorCount=2 -jar orders-service.jar
~~~

Chỉ dùng khi đã xác minh auto-detection sai hoặc cần mô phỏng giới hạn cụ thể. Đặt số thấp hơn thực tế có thể giảm song song; đặt cao hơn quota có thể làm tăng tranh chấp CPU.

Khi điều chỉnh CPU limit, đo cả CPU throttling, run queue, GC worker activity, request throughput và p99 latency. Tăng CPU không luôn làm GC nhanh hơn nếu bottleneck nằm ở memory bandwidth, lock contention hoặc I/O.

## 5. Garbage collection hoạt động như thế nào?

GC tìm và thu hồi object không còn reachable từ các GC root như stack, static field và JNI reference. Các collector khác nhau ở cách phân vùng heap, xác định object sống, di chuyển object và cân bằng pause với throughput.

Các khái niệm thường gặp:

- **Young generation:** vùng thường chứa object mới cấp phát; object chết sớm có thể được thu hồi với chi phí thấp.
- **Old generation:** chứa object sống lâu hoặc đã được promotion.
- **Minor/young collection:** thu hồi vùng young theo thiết kế của collector.
- **Major/old/full collection:** thuật ngữ và phạm vi phụ thuộc collector; không phải mọi JVM đều định nghĩa giống nhau.
- **Stop-the-world pause:** một số pha GC tạm dừng application thread.
- **Concurrent phase:** GC làm việc đồng thời với ứng dụng, vẫn tiêu thụ CPU.
- **Promotion:** object sống lâu được chuyển sang vùng quản lý khác, thường là old generation.
- **Allocation failure:** JVM không thể cấp phát object theo cách bình thường và có thể phải kích hoạt GC hoặc ném lỗi.

GC không phải công việc miễn phí. Collector cần CPU để đánh dấu, quét, di chuyển object và duy trì metadata. Collector giảm pause có thể dùng nhiều CPU hoặc memory hơn; collector tối ưu throughput có thể chấp nhận pause dài hơn.

## 6. Chọn garbage collector theo mục tiêu

Không có collector tốt nhất cho mọi ứng dụng. Lựa chọn dựa trên JDK, kích thước heap, object lifetime, allocation rate, CPU available và SLO latency.

| Collector | Đặc điểm chính | Khi cân nhắc |
|---|---|---|
| G1 GC | Chia heap thành region, cân bằng throughput và pause; thường là lựa chọn mặc định trên các JDK server hiện đại | Workload server tổng quát, heap vừa đến lớn, cần pause có mục tiêu |
| Parallel GC | Thu gom song song, ưu tiên throughput; có thể tạo pause dài hơn | Batch hoặc workload ưu tiên tổng lượng xử lý hơn tail latency |
| ZGC | Collector có các pha concurrent và hướng tới pause rất ngắn trên các JDK hỗ trợ | Workload latency-sensitive, heap lớn hoặc yêu cầu pause thấp |
| Shenandoah | Collector concurrent, hướng tới giảm pause; tính sẵn có phụ thuộc bản phân phối JDK | Môi trường JDK hỗ trợ và workload cần latency thấp |
| Serial GC | Collector đơn giản, dùng ít thread; phù hợp ứng dụng nhỏ | JVM nhỏ, ít CPU hoặc workload nhẹ |
| Epsilon GC | Không thu hồi object; dùng cho thử nghiệm đặc thù | Benchmark allocation hoặc kiểm tra hành vi khi không có GC, không dùng cho dịch vụ lâu dài |

G1 thường là điểm khởi đầu hợp lý nếu không có dữ liệu cho thấy cần collector khác. ZGC và Shenandoah có thể giảm pause nhưng không tự động tăng throughput hoặc giảm tổng chi phí. Parallel GC có thể đạt throughput tốt nhưng pause cần được so với SLO.

CMS đã bị loại bỏ khỏi các JDK hiện đại; không nên chọn cấu hình cũ dựa trên hướng dẫn dành cho phiên bản Java đã lỗi thời. Tên cờ, tính năng generational và trạng thái mặc định của ZGC thay đổi theo JDK; luôn xác minh theo phiên bản runtime thực tế.

### 6.1. G1 GC

Bật G1 rõ ràng:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx3g -jar orders-service.jar
~~~

G1 chia heap thành nhiều region và cố gắng thu hồi các region có nhiều khoảng trống trong giới hạn pause goal. Cờ MaxGCPauseMillis đặt mục tiêu pause, không phải cam kết mọi pause đều nằm dưới ngưỡng đó.

~~~bash
java -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -Xms1g -Xmx3g \
     -jar orders-service.jar
~~~

Không giảm pause goal liên tục mà không đo. Pause goal quá tham vọng có thể làm GC thực hiện nhiều công việc hơn hoặc giảm throughput. Hãy quan sát pause distribution, allocation rate, old generation và CPU trước khi thay đổi.

### 6.2. Parallel GC

Bật Parallel GC:

~~~bash
java -XX:+UseParallelGC -Xms1g -Xmx3g -jar batch-worker.jar
~~~

Parallel GC thường phù hợp với batch, xử lý nền hoặc workload có thể chấp nhận pause dài hơn để đạt throughput. Số GC thread được JVM chọn theo số CPU khả dụng; trong container, cần xác minh CPU detection và quota.

### 6.3. ZGC và Shenandoah

Ví dụ bật ZGC trên JDK có hỗ trợ:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx8g -jar low-latency-api.jar
~~~

Một số phiên bản JDK hỗ trợ tùy chọn generational ZGC với cờ riêng; ở các phiên bản mới hơn trạng thái mặc định có thể đã thay đổi. Hãy kiểm tra tài liệu đúng phiên bản trước khi thêm cờ.

Shenandoah có thể được bật bằng cờ UseShenandoahGC trên các bản JDK cung cấp collector này. Không phải mọi vendor/build đều có sẵn Shenandoah.

Trước khi đổi collector, kiểm tra:

- JDK vendor và version.
- Collector có trong build hay không.
- Heap size và memory headroom.
- CPU quota và mức CPU concurrent GC cần.
- Throughput, p95/p99 latency và pause distribution.
- Tương thích với framework, native agent và yêu cầu vận hành.

## 7. Đọc GC log và các chỉ số quan trọng

GC log là nguồn dữ liệu quan trọng để hiểu heap và hoạt động collector. Với JDK 9 trở lên, unified logging có thể bật bằng:

~~~bash
java -Xlog:gc*,safepoint:file=/var/log/orders/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
     -Xms1g -Xmx3g \
     -jar orders-service.jar
~~~

Cấu hình này ghi log GC và safepoint vào file, có rotation theo số file và kích thước. Đường dẫn phải tồn tại và user chạy JVM phải có quyền ghi. Trong container, có thể gửi log ra stdout/stderr để nền tảng thu thập, nhưng cần cấu hình retention và tránh log tăng không giới hạn.

Với JDK 8, cú pháp GC log khác, ví dụ:

~~~bash
java -Xloggc:/var/log/orders/gc.log \
     -XX:+PrintGCDetails \
     -XX:+PrintGCDateStamps \
     -XX:+UseGCLogFileRotation \
     -XX:NumberOfGCLogFiles=5 \
     -XX:GCLogFileSize=20M \
     -jar orders-service.jar
~~~

Cờ và hành vi logging phụ thuộc bản cập nhật JDK 8; kiểm tra phiên bản runtime và flags được hỗ trợ trước khi áp dụng.

Các metric cần theo dõi:

| Metric | Câu hỏi vận hành |
|---|---|
| Heap used/committed/max | Heap còn headroom không? |
| Old generation occupancy | Live set có tăng qua các chu kỳ không? |
| Allocation rate | Ứng dụng tạo object nhanh tới mức nào? |
| GC count và GC time | GC xảy ra bao nhiêu lần và tiêu tốn bao nhiêu thời gian? |
| Pause duration p50/p95/p99/max | GC ảnh hưởng tail latency ra sao? |
| Promotion rate | Object có chuyển sang old generation quá nhanh không? |
| Full GC count | Có tình trạng GC toàn heap bất thường không? |
| Metaspace/code cache | Có classloader leak hoặc code cache pressure không? |
| Direct buffer usage | Off-heap buffer có tăng tới giới hạn không? |
| Process RSS/container working set | Tổng memory thực tế có gần memory limit không? |
| CPU throttling | GC và ứng dụng có bị giới hạn CPU không? |

Không chỉ xem số lần GC. Một lần GC dài có thể nghiêm trọng hơn nhiều lần GC ngắn. Tương tự, tổng GC time thấp nhưng một pause lớn vẫn có thể phá vỡ SLO p99.

## 8. Dùng JFR, JMX và công cụ chẩn đoán

### 8.1. Java Flight Recorder (JFR)

JFR thu thập sự kiện runtime như allocation, GC, thread scheduling, lock contention, class loading và một số hoạt động I/O. Đây là công cụ hữu ích để xác định nguyên nhân CPU cao, allocation pressure hoặc latency spike.

Có thể bắt đầu recording ngắn bằng jcmd trên JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=5m filename=/tmp/performance.jfr
~~~

Sau khi hoàn tất, mở file bằng Java Mission Control hoặc công cụ tương thích. Tập settings profile có thể thu thập nhiều sự kiện hơn; cần đánh giá overhead, dung lượng file và dữ liệu nhạy cảm trước khi dùng lâu dài trên production.

JFR giúp trả lời:

- Thread nào tiêu thụ CPU?
- Object nào được cấp phát nhiều?
- Có lock contention hoặc thread parking không?
- GC pause và allocation có trùng thời điểm latency tăng không?
- Có class loading hoặc compilation spike sau khi scale-out không?

### 8.2. JMX và metrics endpoint

JMX có thể cung cấp heap pool, GC count/time, thread count, class loading và runtime information. Với ứng dụng production, không mở JMX port trực tiếp ra Internet. Dùng local attach, tunnel hoặc collector được bảo vệ; giới hạn quyền và xác thực theo cấu hình.

Micrometer, Spring Boot Actuator hoặc OpenTelemetry Java agent có thể xuất JVM metrics vào hệ thống monitoring. Cần kiểm soát endpoint và nhãn để tránh lộ thông tin hoặc tạo cardinality cao.

### 8.3. jcmd và jstat

Một số lệnh hữu ích:

~~~bash
# Thông tin JVM
jcmd <pid> VM.version
jcmd <pid> VM.info
jcmd <pid> VM.flags

# Heap summary
jcmd <pid> GC.heap_info

# Thống kê GC theo chu kỳ ngắn
jstat -gcutil <pid> 1000 10

# Thread dump
jcmd <pid> Thread.print
~~~

Các lệnh có thể yêu cầu cùng user, quyền attach và JDK tools tương thích. Heap histogram hoặc dump có thể tốn CPU, I/O và dung lượng; chỉ chạy theo runbook phù hợp.

### 8.4. Heap dump và OutOfMemoryError

Có thể yêu cầu JVM ghi heap dump khi gặp OOME:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/lib/orders/dumps \
     -XX:+ExitOnOutOfMemoryError \
     -Xmx3g \
     -jar orders-service.jar
~~~

Đảm bảo thư mục tồn tại, đủ dung lượng và có quyền ghi. Heap dump có thể chứa token, dữ liệu cá nhân, payload hoặc thông tin nghiệp vụ nhạy cảm. Mã hóa, giới hạn truy cập và thời gian lưu; không tải dump production lên nơi phân tích công cộng.

ExitOnOutOfMemoryError giúp tiến trình kết thúc rõ ràng khi gặp OOME để orchestrator có thể thay thế instance theo chính sách. Cần cân nhắc readiness, restart backoff và khả năng lặp lỗi trước khi bật tự động.

## 9. Phân biệt Java heap OOM và container OOMKilled

Hai tình huống này có nguyên nhân và dấu vết khác nhau.

**Java heap OutOfMemoryError:** JVM không thể cấp phát object trong heap. Có thể thấy exception, heap dump nếu bật, GC log và dấu hiệu heap gần Xmx.

**Metaspace OutOfMemoryError:** class metadata không thể cấp phát thêm theo giới hạn hoặc tài nguyên khả dụng. Có thể liên quan classloader leak, dynamic class generation hoặc cấu hình metaspace.

**Direct buffer memory:** ứng dụng không thể cấp phát direct buffer theo giới hạn hoặc native memory khả dụng.

**Native thread creation failure:** JVM không tạo thêm thread do giới hạn native memory, process/thread limit hoặc tài nguyên hệ điều hành.

**Container OOMKilled:** kernel hoặc runtime kết thúc container vì tổng memory cgroup vượt giới hạn. JVM có thể không kịp tạo heap dump hay ghi Java exception.

Khi điều tra, đối chiếu:

- Exit code và trạng thái OOMKilled từ orchestrator.
- Container memory usage/limit và cgroup memory events.
- Process RSS, heap used/committed và non-heap metrics.
- Kernel log hoặc node event nếu được phép truy cập.
- GC log, application log và thời điểm tăng tải.
- Sidecar hoặc process khác cùng cgroup/Pod.

Nếu heap còn thấp nhưng container OOMKilled, hãy điều tra direct buffer, thread stack, native library, mapped file, agent và tiến trình phụ. Tăng Xmx trong trường hợp này thường làm tình hình xấu hơn.

## 10. Nhận diện memory leak và allocation pressure

Memory leak trong Java thường xảy ra khi object không còn cần thiết về mặt nghiệp vụ nhưng vẫn reachable từ GC root. Heap dump có thể giúp tìm đường tham chiếu giữ object.

Dấu hiệu thường gặp:

- Heap used sau GC tăng dần qua nhiều chu kỳ tương đương.
- Old generation occupancy liên tục tăng.
- Số object hoặc collection tăng theo thời gian.
- Metaspace tăng do classloader không được giải phóng.
- Cache, listener, ThreadLocal hoặc static collection giữ reference ngoài dự kiến.

Allocation pressure khác memory leak. Ứng dụng có thể tạo rất nhiều object ngắn hạn, làm GC chạy thường xuyên nhưng live set sau GC ổn định. Khi đó cần xem allocation profile, object churn và cách xử lý dữ liệu.

Một quy trình điều tra:

1. Ghi nhận tải, throughput và latency tại thời điểm sự cố.
2. Lấy GC log và metric heap theo thời gian.
3. So sánh live set sau các chu kỳ GC tương tự.
4. Nếu cần, tạo heap dump ở thời điểm đại diện.
5. Phân tích dominator tree, retained size và đường reference tới GC root.
6. Kiểm tra cache, collection, listener, ThreadLocal, classloader và buffer pool.
7. Sửa nguyên nhân trong ứng dụng, sau đó benchmark lại.

Không kết luận leak chỉ từ việc heap committed không giảm. Hãy quan sát used sau GC và xu hướng live set qua nhiều chu kỳ.

## 11. Quy trình tối ưu theo số liệu

Tối ưu JVM nên thay đổi từng yếu tố và có baseline để so sánh.

### Bước 1: Xác định SLO và workload

Ghi nhận:

- Throughput hoặc request/giây.
- p50, p95 và p99 latency.
- Error rate và timeout.
- CPU, memory limit, disk và network.
- Tải bình thường, peak, burst và batch window.
- Mức sẵn sàng và thời gian warm-up khi scale-out.

### Bước 2: Thu thập baseline

Chạy workload đại diện trong thời gian đủ dài để thấy steady state. Thu thập GC log, JFR hoặc metrics JVM, container stats và application metrics. Ghi lại JDK vendor/version, flags, image digest, VM type và CPU/memory limits.

### Bước 3: Tìm nút thắt

- CPU bão hòa: xem application CPU, GC CPU, throttling và thread contention.
- Heap tăng sau GC: kiểm tra live set, cache và leak.
- GC pause dài: xác định collector phase, heap size, object distribution và CPU.
- Container OOM: kiểm tra toàn bộ memory, không chỉ heap.
- Tail latency tăng: đối chiếu GC pause, safepoint, lock, network và dependency latency.

### Bước 4: Điều chỉnh một biến

Ví dụ thay đổi heap max, initial heap, collector, pause goal hoặc CPU limit. Không thay đồng thời nhiều cờ GC vì sẽ khó xác định thay đổi nào tạo ra kết quả.

### Bước 5: Benchmark lại

Dùng cùng dữ liệu, cùng tải, cùng thời gian warm-up và cùng cấu hình hạ tầng. So sánh throughput, p99, GC pause, CPU, RSS, OOM và chi phí. Lặp lại đủ lần để tránh kết luận từ một lần chạy.

### Bước 6: Canary và rollout

Đưa cấu hình mới lên một phần nhỏ instance. Theo dõi cùng tập metric và so với nhóm baseline. Có điều kiện rollback rõ ràng nếu p99, error rate, OOM hoặc CPU tăng vượt ngưỡng đã thống nhất.

~~~mermaid
flowchart TD
    A["Xác định SLO và tải đại diện"] --> B["Thu thập baseline"]
    B --> C["Phân tích GC, heap, CPU và RSS"]
    C --> D["Chọn một thay đổi"]
    D --> E["Benchmark lặp lại"]
    E --> F{"Tốt hơn và còn headroom?"}
    F -->|Không| G["Hoàn nguyên và giả thuyết khác"]
    G --> C
    F -->|Có| H["Canary"]
    H --> I{"Production metrics ổn định?"}
    I -->|Không| G
    I -->|Có| J["Rollout và theo dõi"]
~~~

## 12. Benchmark và kiểm thử tải JVM

Bài benchmark phải đại diện cho cách ứng dụng thực sự được sử dụng. Một bài test chỉ tạo object trong vòng lặp không phản ánh đầy đủ database, network, serialization, lock contention hoặc request concurrency.

Các kiểu kiểm thử:

| Kiểu test | Mục đích | Ví dụ |
|---|---|---|
| Load test | Đo hiệu năng ở tải dự kiến | Giữ 500 request/giây trong 30 phút |
| Stress test | Tìm giới hạn và cách hệ thống suy giảm | Tăng tải từng bậc đến khi SLO không còn đạt |
| Spike test | Đánh giá burst đột ngột | Tăng tải gấp 3 lần trong thời gian ngắn |
| Soak test | Phát hiện leak hoặc suy giảm theo thời gian | Giữ tải ổn định nhiều giờ |
| Startup/warm-up test | Đo thời gian sẵn sàng sau khi tạo instance | Scale từ 0 hoặc từ ít replica lên nhiều replica |
| Microbenchmark | Đo một đoạn code nhỏ trong JVM | Dùng JMH cho phép đo vi mô phù hợp |

Với Java microbenchmark, JMH giúp xử lý warm-up, fork và các vấn đề tối ưu hóa của JIT. Không dùng vòng lặp tự viết đơn giản để kết luận hiệu năng của một method vì JIT có thể inline, loại bỏ hoặc biến đổi phép tính.

Khi benchmark GC:

- Dùng cùng JDK và cùng flags giữa các lần chạy.
- Giữ cùng CPU quota, memory limit và instance family.
- Chạy warm-up trước khi đo.
- Ghi lại allocation rate và live set.
- Dùng workload có object lifetime tương tự production.
- Đo nhiều lần và báo phân phối, không chỉ một giá trị trung bình.
- Kiểm tra cả p99 và error rate, không chỉ throughput.
- Đảm bảo dữ liệu và dependency không làm sai lệch kết quả.

## 13. Ví dụ lựa chọn cấu hình theo workload

### 13.1. REST API ưu tiên latency

Mục tiêu là giữ p99 thấp và ổn định. Bắt đầu với G1 nếu chưa có bằng chứng cần collector khác. Chọn heap đủ chứa live set và burst, giữ headroom cho direct buffer, thread stack và native memory. Nếu pause GC là nguyên nhân rõ ràng của tail latency, thử ZGC hoặc Shenandoah trên JDK hỗ trợ rồi benchmark lại.

Theo dõi request p99, GC pause p99, allocation rate, old generation, CPU throttling và RSS. Đừng giảm MaxGCPauseMillis chỉ vì muốn con số đẹp nếu throughput giảm hoặc CPU tăng.

### 13.2. Batch worker ưu tiên throughput

Batch có thể chấp nhận pause dài hơn nếu tổng thời gian hoàn thành tốt. Parallel GC là một lựa chọn cần benchmark. Heap lớn hơn có thể giảm tần suất GC nhưng cũng tăng thời gian xử lý một số chu kỳ và memory footprint.

Đo records/giây, tổng thời gian job, CPU-seconds, GC time và số lần retry. Kiểm tra batch có tạo object lớn hoặc giữ dữ liệu lâu hơn cần thiết không.

### 13.3. Container nhỏ và nhiều replica

Với container có memory limit thấp, cần giữ native headroom và tránh heap chiếm gần hết cgroup. Tối ưu allocation, giới hạn thread pool, direct buffer và agent overhead. Nhiều replica nhỏ có thể cải thiện fault isolation nhưng làm tăng tổng baseline memory và chi phí scheduling.

Đo chi phí trên mỗi request hoặc mỗi tác vụ hoàn tất, không chỉ xem CPU/memory của một Pod.

## 14. Các cờ JVM thường gặp và nguyên tắc sử dụng

| Cờ | Mục đích | Lưu ý |
|---|---|---|
| Xms | Heap ban đầu | Xms lớn có thể tăng memory cam kết lúc khởi động |
| Xmx | Giới hạn heap tối đa | Chừa native headroom trong memory limit |
| InitialRAMPercentage | Tỷ lệ RAM dùng tính heap ban đầu | Phụ thuộc container awareness và JDK |
| MaxRAMPercentage | Tỷ lệ RAM dùng tính heap tối đa | Xác minh JVM nhìn thấy đúng RAM/cgroup |
| UseG1GC | Chọn G1 | Thường là lựa chọn tổng quát trên JDK server hiện đại |
| UseParallelGC | Chọn Parallel GC | Cân nhắc workload ưu tiên throughput |
| UseZGC | Chọn ZGC | Kiểm tra JDK support và CPU/memory overhead |
| MaxGCPauseMillis | Mục tiêu pause cho collector hỗ trợ | Là goal, không phải SLA |
| ActiveProcessorCount | Số CPU JVM coi là khả dụng | Chỉ override khi auto-detection sai hoặc cần kiểm soát |
| HeapDumpOnOutOfMemoryError | Ghi heap dump khi OOME | Cần dung lượng, quyền và bảo vệ dữ liệu |
| ExitOnOutOfMemoryError | Kết thúc JVM khi OOME | Cần restart policy và backoff phù hợp |
| NativeMemoryTracking | Theo dõi native memory qua JVM | Có overhead; bật theo nhu cầu và đo tác động |

Không sao chép một bộ flags dài từ blog hoặc một hệ thống khác. Một số cờ nội bộ thay đổi giữa JDK và có thể bị loại bỏ. Ưu tiên cờ được tài liệu phiên bản hỗ trợ, giữ cấu hình đơn giản và ghi rõ lý do của mỗi flag.

Để điều tra native memory trên HotSpot, có thể bật Native Memory Tracking khi JVM khởi động rồi truy vấn bằng jcmd:

~~~bash
java -XX:NativeMemoryTracking=summary -jar orders-service.jar

jcmd <pid> VM.native_memory summary
~~~

Native Memory Tracking chỉ theo dõi các vùng native mà JVM có thể ghi nhận; nó không thay thế RSS/cgroup metrics và không nhất thiết giải thích mọi allocation từ thư viện native bên ngoài. Tính năng này có overhead, vì vậy cần đánh giá trước khi bật lâu dài trên production.

## 15. Những sai lầm thường gặp

**Đặt Xmx bằng toàn bộ memory limit:** JVM còn cần native memory, thread stack, direct buffer và agent. Hãy chừa headroom và đo RSS.

**Tăng heap để xử lý mọi OOM:** nếu nguyên nhân là native memory, thread leak hoặc container limit, tăng Xmx làm rủi ro OOMKilled cao hơn.

**Đặt Xms bằng Xmx trên mọi container:** heap lớn ngay từ đầu có thể tăng memory commitment và làm giảm mật độ replica. Chỉ dùng khi workload và headroom cho phép.

**Chọn collector theo danh tiếng:** collector ít pause có thể dùng thêm CPU hoặc memory. Benchmark trên đúng JDK và workload.

**Chỉ xem average GC pause:** một pause dài có thể làm hỏng p99. Xem phân phối, max, safepoint và application latency.

**Chỉ xem heap used:** bỏ qua metaspace, direct buffer, thread stack và native allocation. Đối chiếu RSS và cgroup memory.

**Bật quá nhiều GC flags:** làm cấu hình khó hiểu và khó nâng cấp. Thay đổi từng cờ, đo tác động và xóa cờ không còn cần.

**Không bật GC log:** thiếu dữ liệu để phân tích pause và allocation. Bật log có rotation và retention phù hợp.

**Tạo heap dump trên filesystem không đủ chỗ:** có thể làm sự cố nghiêm trọng hơn hoặc mất dump. Dành dung lượng và bảo vệ dữ liệu trước.

**Benchmark không có warm-up:** kết quả bị ảnh hưởng bởi JIT compilation và class loading. Chạy warm-up và nhiều lần lặp.

**Bỏ qua CPU throttling:** GC và application thread cùng bị giới hạn, làm pause và latency tăng. Theo dõi quota và throttled time.

**Tối ưu một instance mà bỏ qua chi phí fleet:** cấu hình heap/GC tốt hơn có thể cho phép giảm replica hoặc tăng mật độ. Đo chi phí trên mỗi đơn vị công việc ở cấp dịch vụ.

## 16. Checklist vận hành JVM trên cloud

- [ ] Đã ghi nhận JDK vendor, version, runtime flags và loại workload.
- [ ] Đã xác minh JVM nhận diện đúng CPU và memory limit của VM/container.
- [ ] Xmx chừa đủ headroom cho metaspace, code cache, thread stack, direct buffer và native memory.
- [ ] Xms phù hợp với hành vi scale-out và mức memory cam kết.
- [ ] Đã đo live set, allocation rate và old generation sau warm-up.
- [ ] Collector được chọn theo SLO latency/throughput và đã benchmark.
- [ ] Có GC log với rotation hoặc retention phù hợp.
- [ ] Có JVM metrics về heap, GC, thread, class loading và direct buffer.
- [ ] Có process RSS/container memory và CPU throttling.
- [ ] Có JFR hoặc quy trình thu thập dữ liệu khi điều tra.
- [ ] Heap dump được bảo vệ và có đủ dung lượng lưu.
- [ ] Phân biệt Java OOME với container OOMKilled.
- [ ] Benchmark có warm-up, tải đại diện, nhiều lần chạy và p99.
- [ ] Mỗi thay đổi JVM được rollout canary và có điều kiện rollback.
- [ ] Đo chi phí trên mỗi request/job cùng với hiệu năng.

Tối ưu JVM trên tài nguyên cloud bắt đầu bằng việc hiểu tổng bộ nhớ của tiến trình, xác minh CPU và memory limit mà JVM nhìn thấy, rồi đo live set, allocation rate và GC pause dưới tải đại diện. Hãy dành headroom ngoài heap, chọn collector theo SLO và JDK thực tế, bật GC log/JFR để có bằng chứng và thay đổi từng yếu tố. Benchmark, canary và theo dõi chi phí trên mỗi đơn vị công việc giúp cấu hình JVM duy trì hiệu năng ổn định khi tải và quy mô cloud thay đổi.
