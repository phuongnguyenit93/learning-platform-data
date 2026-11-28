# Chọn cấu hình heap và mục tiêu độ trễ có căn cứ

## 1. Mục tiêu và bối cảnh phiên bản

G1 được thiết kế để cân bằng thời gian dừng của garbage collection (GC), throughput và mức sử dụng bộ nhớ. Muốn cấu hình G1 đúng, trước tiên cần xác định ngân sách bộ nhớ của tiến trình, lượng dữ liệu sống mà ứng dụng phải giữ, tốc độ cấp phát object và mức độ trễ mà hệ thống có thể chấp nhận.

Bài học dùng JDK 27 làm mốc hiện hành, đồng thời chỉ ra khác biệt liên quan khi chạy JDK 26:

- JDK 26 sử dụng G1 làm mặc định trong môi trường server-class. Trong môi trường bị giới hạn tài nguyên, JVM có thể chọn Serial GC nếu không chỉ định collector.
- JDK 27 đưa G1 thành collector mặc định trong mọi môi trường theo JEP 523. Serial GC vẫn còn và có thể được chọn tường minh nếu benchmark cho thấy phù hợp hơn.
- G1 mặc định đặt mục tiêu pause `-XX:MaxGCPauseMillis=200` ms. Đây là mục tiêu mềm, không phải cam kết mọi pause đều nhỏ hơn 200 ms.
- JDK 27 thay đổi mặc định `MinHeapFreeRatio` và `MaxHeapFreeRatio` riêng cho G1 từ 40/70 thành 0/100. Điều này ngăn các ngưỡng free-space này tự điều chỉnh heap sau Full GC và tránh một số lần tăng/giảm heap không cần thiết.
- G1 tiếp tục tự điều chỉnh kích thước heap và young generation dựa trên hành vi ứng dụng, trừ khi cấu hình thủ công làm hạn chế các heuristic đó.

Mục tiêu của bài là chọn `-Xms`, `-Xmx`, `MaxRAMPercentage` và `MaxGCPauseMillis` dựa trên số liệu, biết khi nào giữ mặc định và biết cách chẩn đoán trước khi thay đổi các tùy chọn nâng cao.

## 2. G1 cân bằng ba mục tiêu

### 2.1. Heap, pause time và throughput có quan hệ với nhau

Ba mục tiêu cần cân bằng:

- **Heap footprint:** lượng RAM tiến trình dùng cho Java heap.
- **Pause time:** khoảng thời gian GC dừng application threads để thu gom và di chuyển object.
- **Throughput:** tỷ lệ thời gian CPU dành cho công việc ứng dụng thay vì GC.

Heap quá nhỏ có thể khiến GC xảy ra thường xuyên, concurrent marking không kịp hoàn tất và có nguy cơ evacuation failure hoặc Full GC. Heap quá lớn có thể làm tiến trình chiếm nhiều RAM, tăng áp lực lên container/host và kéo dài một số pha xử lý khi có nhiều dữ liệu sống.

Mục tiêu pause càng thấp thì G1 thường phải thu gom theo các collection set nhỏ hơn hoặc thực hiện GC thường xuyên hơn. Điều này có thể giảm từng khoảng dừng nhưng tăng tổng chi phí GC và làm giảm throughput. Nới pause target có thể giảm tần suất collection, đổi lại mỗi lần dừng có thể dài hơn.

### 2.2. G1 không phải real-time collector

G1 dùng dữ liệu các lần GC trước để dự đoán công việc có thể hoàn thành trong một pause. Nó cố gắng đáp ứng mục tiêu với xác suất cao trong thời gian dài, nhưng không bảo đảm giới hạn cứng cho từng pause.

Vì vậy:

- Không đặt `MaxGCPauseMillis` bằng toàn bộ SLA của request.
- Nếu API có p99 latency 200 ms, GC pause cần chiếm một phần nhỏ trong ngân sách đó vì request còn chịu ảnh hưởng của CPU scheduling, lock, I/O, network và các safepoint khác.
- Không dùng G1 như một giải pháp bảo đảm hard real-time.
- Theo dõi p95/p99 của ứng dụng song song với GC pause; hai chỉ số này liên quan nhưng không giống nhau.

## 3. Hiểu các mặc định heap và GC trên JDK 27

### 3.1. G1 là mặc định trong mọi môi trường

Từ JDK 27, nếu không chỉ định garbage collector, HotSpot chọn G1 bất kể số CPU và lượng RAM khả dụng. Trước đó, một số môi trường bị giới hạn tài nguyên có thể dùng Serial GC theo ergonomics.

Ví dụ chỉ định G1 tường minh:

~~~bash
java -XX:+UseG1GC -jar app.jar
~~~

Trong JDK 27, lệnh này thường không cần thiết vì G1 đã là mặc định. Tuy nhiên, nó giúp cấu hình triển khai thể hiện rõ ý định và giữ hành vi nhất quán nếu runtime thay đổi môi trường. Trước khi chọn G1 trong một container rất nhỏ, hãy benchmark với Serial GC nếu ứng dụng có yêu cầu footprint cực thấp.

### 3.2. Các mặc định quan trọng

| Tùy chọn | Mặc định JDK 27 | Ý nghĩa |
|---|---:|---|
| `-XX:MaxGCPauseMillis` | 200 ms | Mục tiêu pause mềm của G1 |
| `-XX:GCTimeRatio` | 24 | Mục tiêu tỷ lệ thời gian GC khoảng 1/25, tức 4% |
| `-XX:MaxRAMPercentage` | 25% | Giới hạn heap tối đa theo phần trăm bộ nhớ JVM nhìn thấy |
| `-XX:+G1UseAdaptiveIHOP` | Bật | Tự dự đoán ngưỡng bắt đầu concurrent marking |
| `-XX:G1IHOP` | 45% ở các chu kỳ đầu | Ngưỡng ban đầu trước khi Adaptive IHOP có đủ dữ liệu |
| `-XX:G1NewSizePercent` | 5% | Giới hạn dưới của young generation (experimental) |
| `-XX:G1MaxNewSizePercent` | 60% | Giới hạn trên của young generation (experimental) |
| `-XX:G1HeapRegionSize` | Tự chọn | G1 chọn kích thước region để có khoảng 2.048 region, tối đa 32 MB theo ergonomics |
| `-XX:G1ReservePercent` | 10% | Phần heap dự trữ để giảm rủi ro thiếu chỗ khi promotion/evacuation |

Đây là các mặc định tham khảo; một số giá trị do JVM chọn theo CPU, heap và môi trường. Không cần đặt lại tất cả các giá trị này trên command line. Hãy bắt đầu bằng ergonomics mặc định, chỉ điều chỉnh một tham số khi log và benchmark chỉ ra vấn đề cụ thể.

`G1NewSizePercent` và `G1MaxNewSizePercent` là tùy chọn experimental của HotSpot, không phải điểm bắt đầu cho cấu hình production. Nếu buộc phải thử, hãy kiểm tra đúng tài liệu của JDK đang chạy, bật tùy chọn experimental theo yêu cầu của JVM và đánh giá trên môi trường thử nghiệm trước.

## 4. Chọn kích thước heap theo ngân sách tiến trình

### 4.1. Phân biệt Java heap với RAM của process

`-Xmx` chỉ giới hạn Java heap. Tổng RAM tiến trình còn gồm:

- Metaspace chứa metadata của class.
- Code cache cho mã JIT đã biên dịch.
- Thread stack của platform threads và virtual thread carrier threads.
- Direct buffers, native memory và thư viện JNI.
- Cấu trúc nội bộ của JVM và GC.
- Các vùng memory-mapped hoặc tài nguyên native khác.

Trong container, memory limit áp dụng cho toàn bộ tiến trình và các thành phần tính vào cgroup, không chỉ heap. Nếu đặt `-Xmx` gần bằng memory limit, tiến trình có thể bị OOMKilled dù heap chưa đầy.

Hãy dành ngân sách riêng cho native memory, metaspace, direct buffer, stack, code cache, GC metadata, sidecar nếu có và phần headroom cho biến động tải.

### 4.2. JVM nhận biết container

Trên Linux, `UseContainerSupport` được bật mặc định. JVM đọc giới hạn CPU và memory của container để tính tài nguyên khả dụng. Có thể kiểm tra chi tiết nhận diện container bằng:

~~~bash
java -Xlog:os+container=trace -version
~~~

Nếu chạy trong Kubernetes hoặc Docker, xác nhận JVM nhìn thấy đúng memory limit và CPU quota. Không giả định JVM luôn dùng RAM vật lý của host làm cơ sở tính heap.

### 4.3. -Xms và -Xmx

- `-Xms`: kích thước heap ban đầu và cũng là giới hạn heap tối thiểu.
- `-Xmx`: kích thước heap tối đa.
- Khi `-Xms` nhỏ hơn `-Xmx`, heap có thể tăng dần theo nhu cầu.
- Khi `-Xms` bằng `-Xmx`, JVM không cần tăng/giảm dung lượng heap trong khoảng đó.

Ví dụ:

~~~bash
java -Xms1g -Xmx3g -jar app.jar
~~~

Heap khởi tạo ở 1 GB và có thể tăng đến 3 GB. Đây là cấu hình minh họa; giá trị thật phải dựa trên live set sau GC, allocation rate, số request đồng thời và giới hạn RAM của môi trường.

Không mặc định đặt `-Xms` bằng `-Xmx` cho mọi ứng dụng. Heap cố định giúp giảm công việc resize và có thể làm pause ổn định hơn, nhưng chiếm trước nhiều RAM và khiến JVM mất khả năng thu hẹp footprint khi tải giảm.

### 4.4. Dùng MaxRAMPercentage trong container

`-XX:MaxRAMPercentage` đặt giới hạn heap tối đa theo tỷ lệ phần trăm của bộ nhớ JVM nhìn thấy. Mặc định là 25%.

Ví dụ container có memory limit 4 GiB và JVM nhận đúng giới hạn đó:

~~~bash
java -XX:MaxRAMPercentage=55 -XX:InitialRAMPercentage=20 -jar app.jar
~~~

Với ví dụ này, heap tối đa vào khoảng 2,2 GiB; phần còn lại khoảng 1,8 GiB dành cho native memory, metaspace, thread stacks, direct buffers, code cache và headroom. Tỷ lệ 55% chỉ là số minh họa để giải thích cách tính, không phải giá trị khuyến nghị cho mọi container.

Chọn tỷ lệ theo số liệu RSS và native memory của ứng dụng. Nếu tiến trình thường bị OOMKilled khi heap còn trống, hãy kiểm tra native memory và giảm heap budget hoặc giới hạn direct buffers phù hợp.

### 4.5. Khi nào đặt Xms bằng Xmx và AlwaysPreTouch?

Có thể đặt heap cố định khi:

- Ứng dụng chạy liên tục với tải ổn định.
- Độ trễ khởi tạo hoặc resize heap trong giờ cao điểm cần được giảm.
- Máy/container có đủ RAM để giữ toàn bộ heap đã cam kết.
- Đã benchmark và xác nhận không gây áp lực memory lên node.

Ví dụ:

~~~bash
java -Xms3g -Xmx3g -XX:+AlwaysPreTouch -jar app.jar
~~~

`AlwaysPreTouch` yêu cầu JVM chạm các trang heap trước khi cấp phát cho ứng dụng, chuyển một phần công việc cấp phát và ánh xạ memory sang thời điểm startup. Đổi lại, thời gian khởi động có thể dài hơn và memory được chạm sớm hơn. Chỉ bật khi cần tính ổn định và đã dành đủ ngân sách bộ nhớ.

## 5. Chọn mục tiêu pause có căn cứ

### 5.1. MaxGCPauseMillis là soft goal

`-XX:MaxGCPauseMillis` là gợi ý cho G1 về thời gian pause mong muốn. Mặc định là 200 ms. JVM theo dõi trung bình có trọng số và độ biến thiên của pause; nếu dự đoán mục tiêu không đạt, nó điều chỉnh kích thước collection set và young generation.

Ví dụ:

~~~bash
java -XX:MaxGCPauseMillis=150 -jar app.jar
~~~

Giá trị 150 ms chỉ là mục tiêu. Một pause riêng lẻ vẫn có thể dài hơn vì object copy, humongous allocation, reference processing, hệ điều hành, CPU throttling hoặc áp lực bộ nhớ.

### 5.2. Chọn giá trị theo SLA

Bắt đầu bằng 200 ms mặc định, sau đó điều chỉnh theo ngân sách độ trễ:

| Mục tiêu vận hành | Cách tiếp cận |
|---|---|
| Ứng dụng batch ưu tiên throughput | Có thể giữ mặc định hoặc nới pause target sau khi đo |
| API tương tác cần pause ngắn hơn | Thử giảm target từng bước nhỏ và đo p95/p99 |
| Hệ thống có pause back-to-back | Kiểm tra tần suất GC, allocation rate và pause interval trước khi đổi target |
| SLA rất thấp hoặc hard real-time | G1 có thể không đáp ứng; benchmark collector khác và đánh giá kiến trúc |

Không đặt target cực thấp ngay từ đầu. Nếu heap nhỏ hoặc allocation rate cao, G1 có thể phải thu gom liên tục, khiến ứng dụng mất throughput và không có đủ thời gian chạy giữa các pause.

### 5.3. Trade-off khi giảm hoặc tăng pause target

| Thay đổi | Tác động có thể gặp |
|---|---|
| Giảm `MaxGCPauseMillis` | Collection set nhỏ hơn, pause mục tiêu ngắn hơn, GC có thể thường xuyên hơn và throughput giảm |
| Tăng `MaxGCPauseMillis` | Collection set lớn hơn, có thể giảm tần suất GC và tăng throughput, nhưng từng pause có thể dài hơn |
| Tăng heap tối đa | Tạo thêm khoảng trống cho allocation và marking, có thể giảm tần suất GC; tốn thêm RAM |
| Giảm heap tối đa | Giảm footprint, nhưng có thể tăng GC frequency, marking pressure và nguy cơ Full GC |

Pause target nên nhỏ hơn phần ngân sách SLA dành cho GC, không nên bằng toàn bộ latency mục tiêu của request.

## 6. G1 tự điều chỉnh young generation và IHOP

### 6.1. Không khóa cứng kích thước young generation

G1 điều chỉnh young generation để cân bằng pause target với tần suất collection. Young generation lớn thường chứa được nhiều allocation hơn giữa hai lần GC, nhưng cũng có thể làm lượng object sống phải copy trong một pause tăng lên.

Tránh đặt kích thước young generation cố định bằng `-Xmn`, `-XX:NewRatio` hoặc cấu hình `NewSize`/`MaxNewSize` theo cách khiến G1 không còn tự điều chỉnh được. Việc khóa young generation có thể làm mất khả năng đáp ứng pause-time goal.

Nếu log cho thấy pha Object Copy của young collection chiếm phần lớn pause, trước tiên kiểm tra số lượng object sống, allocation rate và cấu trúc object. Chỉ cân nhắc các giới hạn young-generation nâng cao sau khi đã xác định rõ trade-off và kiểm thử trên workload thật.

### 6.2. Adaptive IHOP

IHOP (Initiating Heap Occupancy Percent) là ngưỡng old-generation occupancy để G1 bắt đầu concurrent marking. G1 mặc định bật Adaptive IHOP, quan sát thời gian marking và lượng dữ liệu được cấp phát trong lúc marking để dự đoán thời điểm bắt đầu phù hợp.

Trong các chu kỳ đầu chưa đủ dữ liệu, `-XX:G1IHOP` mặc định là 45% old generation. Sau khi có đủ mẫu, G1 tự tính lại ngưỡng.

Không đặt `G1IHOP` thủ công nếu chưa có dấu hiệu marking bắt đầu quá muộn hoặc workload thay đổi rõ rệt. Nếu concurrent marking không hoàn thành trước khi old generation cạn chỗ, hãy kiểm tra allocation rate, marking duration, heap headroom và humongous objects trước.

Trong JDK 27, tên tùy chọn hiện hành là `-XX:G1IHOP`. Alias `-XX:InitiatingHeapOccupancyPercent` đã bị deprecated; cấu hình mới nên dùng tên hiện hành.

## 7. Đọc GC log trước khi thay đổi tham số

### 7.1. Bật unified logging

Bắt đầu bằng log đủ thông tin về collection, heap, CPU và safepoint:

~~~bash
java -Xlog:gc*=info,gc+heap=info,gc+cpu=info,safepoint=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Khi cần phân tích sâu:

~~~bash
java -Xlog:gc*=debug,gc+ergo+cset=debug:file=gc-debug.log:time,uptime,level,tags -jar app.jar
~~~

Các tag thường dùng:

| Logging selector | Thông tin |
|---|---|
| `gc` | Loại GC, pause, heap trước và sau collection |
| `gc+heap=info` | Heap region, Eden/Survivor/Old và humongous regions |
| `gc+cpu=info` | User, system và real time của pause |
| `gc+phases=debug` | Thời gian từng pha như Merge Heap Roots, Scan Heap Roots, Object Copy |
| `gc+ergo+cset=debug` | Dự đoán và lựa chọn collection set |
| `safepoint` | Thời gian và nguyên nhân liên quan safepoint |

### 7.2. Chỉ số cần thu thập

Đừng chỉ xem thời gian pause trung bình. Hãy thu thập:

- p50, p95, p99 và maximum GC pause.
- Số lần GC mỗi phút và tổng thời gian dừng.
- Tỷ lệ thời gian CPU dành cho GC.
- Heap occupancy sau GC và live set ổn định.
- Allocation rate và promotion rate.
- Thời gian concurrent marking.
- Số lần Full GC và evacuation failure.
- Số humongous regions trước/sau collection.
- Process RSS, native memory, container memory và CPU throttling.
- p95/p99 latency của request và throughput nghiệp vụ.

Nếu GC pause ngắn nhưng request latency vẫn cao, bottleneck có thể nằm ở CPU throttling, lock, I/O, network, queue hoặc safepoint khác.

### 7.3. Nhận biết một số dấu hiệu

| Dấu hiệu trong log | Ý nghĩa cần điều tra |
|---|---|
| `Pause Full (G1 Compaction Pause)` | Full heap collection; thường rất tốn thời gian |
| `Evacuation Failure: Allocation` | Không đủ vùng đích để di chuyển object |
| `Humongous regions: X->Y` | Số region dành cho object lớn; kiểm tra object lớn và fragmentation |
| `Object Copy` kéo dài | Có nhiều object sống cần copy trong collection set |
| `Merge Heap Roots` hoặc `Scan Heap Roots` kéo dài | Chi phí remembered set và tham chiếu liên vùng cao |
| Concurrent marking chưa kịp hoàn tất | Kiểm tra allocation rate, marking duration và IHOP |
| `Real` lớn hơn nhiều so với `User + Sys` | Tiến trình có thể bị thiếu CPU hoặc bị hệ điều hành trì hoãn |

## 8. Điều chỉnh theo triệu chứng

### 8.1. Pause trẻ kéo dài

Kiểm tra pha `Object Copy`, số object sống và kích thước young generation. Nếu phần lớn pause là do copy object, giảm số object sống hoặc giảm allocation/retention có thể hiệu quả hơn việc giảm heap một cách tùy tiện.

G1 có các tùy chọn nâng cao để giới hạn young generation, nhưng chúng có thể giảm throughput hoặc khiến GC xảy ra thường xuyên hơn. Không khóa young generation bằng một giá trị cố định khi mục tiêu là để G1 tự đáp ứng pause target.

### 8.2. Mixed collection kéo dài

Mixed collection thu gom cả young và một số old regions. Dùng `gc+ergo+cset=debug` để xem thời gian dự đoán cho young regions và old regions.

Nếu old regions chiếm phần lớn pause, có thể phân bổ công việc thu hồi old generation qua nhiều collection hơn. Tuy nhiên, giảm lượng old region được thu gom mỗi lần có thể khiến G1 thu hồi không đủ dung lượng trong một chu kỳ. Hãy theo dõi old-generation occupancy và nguy cơ Full GC sau khi điều chỉnh.

### 8.3. Concurrent marking không kịp

Nếu old generation tăng nhanh và marking chưa kết thúc trước khi thiếu vùng trống:

1. Đo allocation/promotion rate và thời gian concurrent marking.
2. Xác định heap có đủ headroom hay không.
3. Kiểm tra số humongous objects và region bị chiếm.
4. Nếu memory budget cho phép, tăng `-Xmx`.
5. Nếu workload thay đổi, kiểm tra Adaptive IHOP đã có đủ mẫu mới chưa.
6. Chỉ điều chỉnh `G1ReservePercent`, `ConcGCThreads` hoặc `G1IHOP` sau khi log chỉ ra nguyên nhân cụ thể.

Không đặt ngưỡng IHOP thấp tùy ý; marking quá sớm có thể làm tăng concurrent CPU và giảm tài nguyên dành cho ứng dụng.

### 8.4. Nhiều humongous objects

G1 coi object có kích thước từ một nửa region trở lên là humongous object. Các object này chiếm một chuỗi region liên tiếp và phần trống ở region cuối có thể không được dùng cho allocation khác.

Nếu log cho thấy nhiều humongous regions:

- Kiểm tra ứng dụng có tạo byte array hoặc buffer rất lớn hay không.
- Cân nhắc streaming/chunking thay vì giữ nhiều object lớn cùng lúc.
- Đánh giá lifetime của object lớn và khả năng tái sử dụng buffer.
- Chỉ thử tăng `G1HeapRegionSize` khi có số liệu chứng minh fragmentation hoặc humongous allocation là vấn đề; region lớn hơn cũng có thể làm tăng lượng object phải copy trong một pause.

### 8.5. Pause bị ảnh hưởng bởi hệ điều hành

Trong `gc+cpu=info`, so sánh `User`, `Sys` và `Real`:

- `Sys` cao có thể liên quan cấp phát/thu hồi memory từ OS hoặc hoạt động I/O.
- `Real` cao hơn nhiều tổng `User + Sys` có thể cho thấy process không được cấp đủ CPU.
- Ghi log lên thiết bị I/O đang bận có thể gây chậm bất thường.
- Trên Linux, Transparent Huge Pages có thể tạo các lần stall do OS gom page.

Trong một số môi trường cần pause ổn định, đặt `-Xms` bằng `-Xmx` và dùng `-XX:+AlwaysPreTouch` có thể chuyển chi phí chạm memory sang startup. Hãy đo tác động lên thời gian khởi động và RSS trước khi áp dụng.

## 9. Ví dụ cấu hình theo mục tiêu

Các ví dụ dưới đây là điểm khởi đầu để benchmark. Chúng không phải profile dùng chung cho mọi service.

### 9.1. Cấu hình cân bằng

Giữ pause target mặc định 200 ms, giới hạn heap theo ngân sách và bật log:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx3g -Xlog:gc*=info,gc+heap=info,gc+cpu=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Dùng khi muốn kiểm soát heap tối đa nhưng vẫn để G1 tự điều chỉnh young generation và các heuristic còn lại.

### 9.2. Thử nghiệm ưu tiên latency

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx3g -XX:MaxGCPauseMillis=150 -Xlog:gc*=info,gc+phases=debug,gc+cpu=info:file=gc-latency.log:time,uptime,level,tags -jar app.jar
~~~

So sánh với baseline ở cùng tải. Chỉ giữ target 150 ms nếu p95/p99 request latency cải thiện mà throughput, CPU và GC frequency vẫn nằm trong giới hạn.

### 9.3. Thử nghiệm ưu tiên throughput

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx4g -XX:MaxGCPauseMillis=300 -Xlog:gc*=info,gc+heap=info:file=gc-throughput.log:time,uptime,level,tags -jar app.jar
~~~

Target rộng hơn có thể giúp giảm tần suất GC và tăng throughput, nhưng cần kiểm tra maximum pause có vượt ngân sách hay không. Chỉ tăng heap nếu host/container còn đủ RAM cho native memory và các process khác.

### 9.4. Container có giới hạn RAM

~~~bash
java -XX:+UseG1GC -XX:MaxRAMPercentage=55 -XX:InitialRAMPercentage=20 -XX:MaxGCPauseMillis=200 -Xlog:os+container=info,gc*=info:file=gc-container.log:time,uptime,level,tags -jar app.jar
~~~

Ví dụ này giả định JVM nhận đúng memory limit của container. Hãy đo RSS, heap committed, metaspace, direct buffer và thread count trong môi trường thật. Nếu process vẫn tiến gần cgroup limit, giảm heap budget hoặc tìm nguồn native memory tăng bất thường.

## 10. Quy trình tuning có thể lặp lại

1. **Ghi rõ mục tiêu.** Xác định throughput tối thiểu, p95/p99 latency, pause budget, memory limit và giới hạn CPU.
2. **Chạy baseline.** Dùng G1 default settings, chỉ giới hạn `-Xmx` khi cần; bật GC log và metrics ứng dụng.
3. **Đo live set.** Xem heap sau GC ở tải bình thường và tải đỉnh; phân biệt dữ liệu sống với allocation tạm thời.
4. **Kiểm tra memory budget.** Cộng heap, metaspace, direct memory, thread stacks, code cache và native RSS trong cgroup.
5. **Điều chỉnh heap trước.** Nếu heap max bị chạm và GC time cao, thử tăng heap khi còn RAM; nếu process có headroom lớn, không nhất thiết phải giữ heap tối đa quá cao.
6. **Điều chỉnh pause target sau.** Nếu GC pause là nguyên nhân chính của latency, giảm target từng bước; nếu throughput bị ảnh hưởng và pause còn dư ngân sách, nới target.
7. **Đọc pha GC.** Xác định pause đến từ Object Copy, Merge/Scan Heap Roots, Reference Processing, mixed collection hay vấn đề hệ điều hành.
8. **Thay đổi một tham số mỗi lần.** Giữ lại kết quả để biết thay đổi nào tạo tác động.
9. **Chạy lại tải đại diện.** Có warmup, thời lượng đủ dài, cùng dữ liệu và cùng giới hạn CPU/RAM.
10. **Ghi lại cấu hình cuối.** Lưu JDK build, container limit, JVM flags, GC log, throughput và p95/p99 latency.

Không kết luận chỉ từ một lần chạy. Cần nhiều lần đo để phân biệt tác động thật với nhiễu do JIT warmup, CPU scheduling, cache và tải nền.

## 11. Khác biệt heap đáng chú ý khi nâng JDK 26 lên 27

| Nội dung | JDK 26 | JDK 27 |
|---|---|---|
| Collector mặc định trong môi trường bị giới hạn | Có thể chọn Serial GC theo ergonomics | G1 là mặc định trong mọi môi trường nếu không chỉ định collector |
| `MinHeapFreeRatio` của G1 | 40 | 0 |
| `MaxHeapFreeRatio` của G1 | 70 | 100 |
| Tên ngưỡng bắt đầu marking | `G1IHOP` đã có | `G1IHOP` là tên hiện hành; alias cũ đã deprecated |
| Pause target mặc định G1 | 200 ms | 200 ms |
| Adaptive IHOP | Bật mặc định | Bật mặc định |

JDK 27 thay đổi lựa chọn collector mặc định trong môi trường nhỏ và cách Full GC ảnh hưởng tới heap sizing qua free-space ratios. Khi nâng cấp, hãy kiểm tra:

- Ứng dụng trước đây có vô tình dùng Serial GC trong container nhỏ không.
- Container có đủ CPU và memory cho G1 concurrent work không.
- Các JVM options có dùng tên alias cũ của IHOP không.
- Script triển khai có đang đặt Min/MaxHeapFreeRatio tường minh hay không.
- Kết quả p95/p99, throughput và RSS có thay đổi sau khi đổi JDK không.

Nếu muốn giữ Serial GC trong môi trường nhỏ vì benchmark chứng minh phù hợp, có thể chọn tường minh bằng `-XX:+UseSerialGC`. JDK 27 vẫn cung cấp Serial GC; thay đổi JEP 523 không loại bỏ collector này.

## 12. Những cấu hình không nên áp dụng theo thói quen cũ

- Không đặt young generation cố định bằng `-Xmn` hoặc `NewRatio` khi muốn G1 tự điều chỉnh pause.
- Không đặt `Xms = Xmx` chỉ vì cho rằng heap cố định luôn nhanh hơn; phải xét memory budget và tải biến động.
- Không đặt `MaxGCPauseMillis` cực thấp nếu chưa đo allocation rate và khả năng đáp ứng của heap.
- Không thay `G1IHOP` thủ công trước khi kiểm tra Adaptive IHOP, marking duration và old-gen allocation.
- Không tăng `G1HeapRegionSize` chỉ vì thấy có humongous object; hãy đo số region và fragmentation trước.
- Không coi GC log trung bình là đại diện cho tail latency.
- Không dùng các alias đã deprecated hoặc tùy chọn GC cũ chỉ vì chúng còn được chấp nhận tạm thời.
- Không giả định `-Xmx` bằng memory limit của container là an toàn.

## 13. Kết luận

Cấu hình G1 có căn cứ bắt đầu từ ngân sách bộ nhớ và SLA, sau đó mới điều chỉnh pause target. Trên JDK 27, G1 là collector mặc định trong mọi môi trường; heap tối đa mặc định theo ergonomics thường dựa trên 25% bộ nhớ JVM nhìn thấy. G1 dùng Adaptive IHOP và tự điều chỉnh young generation để cân bằng pause, throughput và footprint.

Các nguyên tắc quan trọng:

- Đặt `-Xmx` theo live set và memory budget toàn tiến trình, không theo tổng RAM host một cách máy móc.
- Dành chỗ cho native memory, metaspace, direct buffers, thread stacks và headroom của container.
- Bắt đầu với pause target mặc định 200 ms; chỉ giảm hoặc tăng khi số liệu chứng minh cần thiết.
- Xem pause target là soft goal, không phải hard SLA.
- Giữ young generation và Adaptive IHOP ở chế độ tự điều chỉnh trừ khi GC log chỉ ra vấn đề cụ thể.
- Đo p95/p99, throughput, GC pause, heap occupancy, Full GC, native RSS và CPU throttling cùng nhau.
- Khi nâng từ JDK 26 lên JDK 27, chú ý G1 trở thành default trong môi trường nhỏ và free-ratio defaults đổi thành 0/100.

Một cấu hình tốt là cấu hình đáp ứng được SLA với footprint và chi phí vận hành phù hợp trên đúng workload production, không phải cấu hình có nhiều JVM flags nhất.

## Tài liệu tham khảo chính thức

- [Garbage-First Garbage Collector Tuning — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html)
- [Garbage-First (G1) Garbage Collector — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [Ergonomics — Java SE 27 GC Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/ergonomics.html)
- [Factors Affecting Garbage Collection Performance — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/factors-affecting-garbage-collection-performance.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523)
- [JDK 27 Release Notes — G1 defaults and heap free ratios](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JDK 27: Default G1 in All Environments — Inside Java](https://inside.java/2026/07/20/quality-heads-up/)

