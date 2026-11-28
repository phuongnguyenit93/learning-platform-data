# Đánh đổi CPU, throughput và footprint khi chọn collector

Không có garbage collector nào đồng thời tối ưu mọi mục tiêu. Collector dừng ứng dụng lâu hơn có thể đạt throughput cao vì dành ít CPU cho công việc concurrent; collector giảm pause thường phải chạy thêm công việc song song với ứng dụng, dùng CPU và có thể cần thêm khoảng trống trong heap. Một collector phù hợp phải đáp ứng cả yêu cầu độ trễ, năng lực CPU, giới hạn bộ nhớ và đặc điểm workload.

Trên JDK hiện đại, G1 là lựa chọn mặc định phù hợp cho nhiều ứng dụng server. Parallel GC vẫn hữu ích khi throughput quan trọng và có thể chấp nhận pause dài hơn. ZGC và Shenandoah hướng tới độ trễ thấp bằng cách thực hiện nhiều công việc GC đồng thời với ứng dụng; Serial GC phù hợp với ứng dụng nhỏ hoặc môi trường hạn chế tài nguyên. Bài học này tập trung vào các collector còn được hỗ trợ, cách so sánh công bằng và cách chọn theo số liệu vận hành.

## 1. Ba mục tiêu cần phân biệt

### CPU dành cho GC

GC sử dụng CPU để tìm object còn sống, xử lý reference, di chuyển object hoặc thu hồi vùng nhớ. CPU dành cho GC có thể chạy:

- Trong các pause stop-the-world, khi thread ứng dụng tạm dừng và GC dùng nhiều worker thread.
- Concurrent với ứng dụng, khi thread GC và thread ứng dụng cùng tranh chấp CPU.

Một collector có pause ngắn vẫn có thể tiêu thụ nhiều CPU tổng thể. Khi CPU bị giới hạn bởi container hoặc máy đang tải cao, công việc concurrent có thể lấy mất thời gian chạy của request handler, compiler, background job hoặc thread xử lý nghiệp vụ.

### Throughput của ứng dụng

Throughput là tỷ lệ thời gian JVM thực hiện công việc ứng dụng thay vì thực hiện GC trong một khoảng thời gian đủ dài. Khi so sánh hệ thống, nên đo cả thông lượng nghiệp vụ như request/second, message/second hoặc batch records/second.

Throughput không chỉ phụ thuộc GC. Nó còn bị ảnh hưởng bởi allocation rate, lock contention, I/O, JIT compilation, CPU quota, độ lớn live set và thời gian ứng dụng chờ bên ngoài JVM.

### Footprint bộ nhớ

Footprint là working set bộ nhớ mà tiến trình thực sự giữ và sử dụng trên hệ thống. Trong môi trường container, chỉ số quan trọng thường là RSS hoặc memory working set được nền tảng container báo cáo.

Không đồng nhất các số liệu sau:

| Số liệu | Ý nghĩa |
|---|---|
| `-Xmx` | Giới hạn trên của Java heap |
| Heap reserved | Vùng địa chỉ ảo JVM dành trước cho heap |
| Heap committed | Phần heap đã được commit để sử dụng |
| Heap used | Phần heap đang chứa object theo cách thống kê của collector |
| RSS/working set | Bộ nhớ vật lý đang được tiến trình sử dụng theo cách đo của hệ điều hành/container |
| Native memory | Bộ nhớ ngoài Java heap như thread stack, metaspace, code cache và cấu trúc GC |

Một ứng dụng có `-Xmx` lớn không nhất thiết luôn dùng lượng RAM vật lý bằng giá trị đó. Ngược lại, chỉ nhìn heap used cũng không cho biết toàn bộ footprint của process.

## 2. Vì sao ba mục tiêu thường xung đột?

Một collector stop-the-world có thể dùng nhiều worker thread để hoàn tất một đợt thu gom nhanh. Trong khoảng pause, ứng dụng không chạy; sau khi GC xong, CPU được trả lại cho ứng dụng. Cách này có thể đạt throughput cao nhưng làm tăng tail latency nếu pause xảy ra đúng lúc xử lý request quan trọng.

Collector concurrent thực hiện một phần công việc khi ứng dụng vẫn chạy. Pause có thể ngắn hơn, nhưng GC và ứng dụng cùng sử dụng CPU. Collector cũng cần đủ heap headroom để ứng dụng tiếp tục cấp phát trong khi GC đang xử lý object.

~~~text
Stop-the-world collector
Application:  RUN ---- PAUSE GC ---- RUN -------- RUN
GC:                   COLLECT

Concurrent collector
Application:  RUN -------- RUN -------- RUN --------
GC:                 MARK/EVACUATE/RECLAIM
                    (chạy đồng thời một phần)
~~~

Sơ đồ chỉ minh họa nguyên tắc. Mỗi collector vẫn có các pha stop-the-world; “concurrent” không có nghĩa là không bao giờ dừng ứng dụng.

## 3. So sánh các collector còn dùng trên JDK hiện đại

| Collector | Đặc điểm chính | Điểm mạnh | Chi phí cần cân nhắc |
|---|---|---|---|
| Serial GC | Thu gom bằng một GC thread, chủ yếu stop-the-world | Đơn giản, overhead thấp, phù hợp workload nhỏ | Pause có thể dài khi heap hoặc live set lớn; không tận dụng nhiều CPU |
| Parallel GC | Nhiều GC thread làm việc song song, chủ yếu stop-the-world | Throughput cao khi có nhiều CPU; phù hợp batch và workload chấp nhận pause | Pause có thể dài; CPU tăng mạnh trong đợt GC |
| G1 GC | Generational, parallel và mostly concurrent; mặc định trên server-class machine ở HotSpot | Cân bằng latency và throughput, điều khiển pause theo mục tiêu | Công việc concurrent và remembered sets tạo overhead CPU/bộ nhớ |
| ZGC | Collector concurrent hướng tới pause rất thấp; generational từ JDK 24 | Giảm ảnh hưởng pause tới request latency, phù hợp heap lớn và SLO nghiêm ngặt | Cần CPU headroom và heap headroom; throughput có thể thấp hơn collector thiên throughput |
| Shenandoah | Collector concurrent hướng tới pause thấp | Có thể phù hợp ứng dụng nhạy latency | Chi phí concurrent và native overhead; availability/tính năng phụ thuộc JDK distribution và nền tảng |

Không phải mọi nhà cung cấp JDK đều đóng gói cùng một tập collector trên mọi hệ điều hành. Trước khi chọn Shenandoah hoặc một collector đặc thù, kiểm tra tài liệu và khả năng hỗ trợ của đúng runtime sẽ triển khai.

## 4. Serial GC: overhead thấp cho ứng dụng nhỏ

Serial GC dùng một thread để thực hiện công việc thu gom. Vì không phải điều phối nhiều GC worker, nó có overhead tương đối thấp và có thể là lựa chọn hợp lý cho:

- Ứng dụng command-line chạy ngắn.
- Công cụ nhỏ có heap và live set thấp.
- Môi trường chỉ có một CPU hoặc bị giới hạn CPU nghiêm ngặt.
- Ứng dụng không có yêu cầu pause-time chặt.

Bật tường minh:

~~~text
java -XX:+UseSerialGC -jar small-tool.jar
~~~

Serial GC không phải lựa chọn mặc định cho mọi ứng dụng ít người dùng. Một service có heap nhỏ nhưng yêu cầu phản hồi ổn định vẫn cần đo pause và tail latency. Khi workload tăng, một thread GC có thể trở thành giới hạn.

## 5. Parallel GC: ưu tiên throughput

Parallel GC còn được gọi là throughput collector. Nó dùng nhiều GC worker thread để thu gom song song, giúp giảm thời gian hoàn tất công việc GC so với một thread trên máy nhiều CPU.

Phù hợp khi:

- Công việc chạy theo batch hoặc job nền.
- Throughput tổng quan quan trọng hơn pause của từng request.
- Ứng dụng có thể chấp nhận pause dài hơn.
- Máy có CPU đủ để cấp cho nhiều GC worker.

Bật tường minh:

~~~text
java -XX:+UseParallelGC -jar batch-worker.jar
~~~

Parallel GC có thể đạt throughput tốt vì phần lớn công việc thu gom diễn ra trong các pause; ứng dụng không phải chia CPU liên tục với các pha concurrent dài. Tuy nhiên, trong pause, các thread ứng dụng dừng. Một đợt GC lớn có thể làm latency tăng mạnh hoặc khiến các request chờ phía sau.

Không nên chọn Parallel chỉ vì benchmark micro đo được throughput cao hơn. Nếu ứng dụng phục vụ tương tác trực tiếp, hãy đo p95/p99 latency và số request timeout trong cùng workload.

## 6. G1: lựa chọn cân bằng và mặc định phổ biến

G1 chia heap thành region, thu gom theo từng collection set và thực hiện một số pha concurrent. Nó hướng tới việc đáp ứng mục tiêu pause-time với xác suất cao trong khi vẫn giữ throughput tốt.

G1 là collector mặc định trên các cấu hình HotSpot server-class thông dụng. Khi không có yêu cầu đặc biệt, nên bắt đầu bằng mặc định của JVM và đo trước khi đổi collector.

G1 thường phù hợp khi:

- Ứng dụng server cần cân bằng throughput và latency.
- Heap vừa đến lớn, live set và allocation rate thay đổi theo tải.
- Pause cần tương đối ngắn và có thể dự đoán.
- Nhóm vận hành muốn bắt đầu từ một collector có ergonomics tốt.

Bật tường minh nếu cần cố định cấu hình benchmark:

~~~text
java -XX:+UseG1GC -jar service.jar
~~~

### G1 dùng CPU và bộ nhớ ở đâu?

G1 thực hiện một phần công việc marking và refinement đồng thời với ứng dụng. Các thread này tiêu thụ CPU trong lúc request handler vẫn chạy. G1 cũng duy trì remembered sets để theo dõi tham chiếu giữa các region; cấu trúc này tạo thêm native memory và công việc cập nhật.

Đổi lại, G1 có thể thu gom từng phần heap qua nhiều pause thay vì chờ một lần thu gom toàn bộ old generation. Điều này thường giúp tránh các pause rất dài, nhưng không bảo đảm mọi pause đều ngắn.

### Pause-time goal không phải cam kết cứng

Có thể đặt mục tiêu pause:

~~~text
-XX:MaxGCPauseMillis=200
~~~

Đây là mục tiêu hướng dẫn cho ergonomics, không phải giới hạn thời gian tuyệt đối. Nếu heap, live set, allocation rate hoặc CPU không cho phép, G1 có thể vượt mục tiêu. Ép mục tiêu quá thấp có thể làm GC thực hiện nhiều công việc hơn, ảnh hưởng throughput hoặc khiến heap cần lớn hơn.

Tránh cố định young generation bằng các tùy chọn như `-Xmn` khi chưa có bằng chứng. G1 cần linh hoạt điều chỉnh young generation để cân bằng pause và hiệu quả thu gom.

### Cải thiện G1 trên JDK 26

JDK 26 có thay đổi G1 nhằm tăng throughput bằng cách giảm lượng synchronization giữa application thread và GC thread theo JEP 522. Đây là cải thiện của runtime; mức lợi ích thực tế vẫn phụ thuộc workload, CPU và cấu hình. Khi so sánh collector, cần ghi rõ JDK build vì kết quả trên các JDK khác nhau có thể khác.

## 7. ZGC: ưu tiên latency rất thấp

ZGC thực hiện phần lớn công việc nặng concurrent với ứng dụng và hướng tới pause rất thấp, không tăng tuyến tính theo kích thước heap. Đây là lựa chọn cần cân nhắc khi latency là yêu cầu quan trọng của sản phẩm, chẳng hạn:

- API có SLO p99 nghiêm ngặt.
- Hệ thống giao dịch hoặc xử lý tương tác cần giảm pause spikes.
- Heap lớn nhưng không muốn pause tăng tương ứng với kích thước heap.

Bật ZGC:

~~~text
java -XX:+UseZGC -jar latency-service.jar
~~~

Từ JDK 24, ZGC là generational collector; tùy chọn cũ `ZGenerational` đã bị loại bỏ. Khi dùng JDK hiện đại, không sao chép các hướng dẫn cũ yêu cầu bật chế độ generational bằng flag riêng.

### CPU và heap headroom

Vì ZGC làm nhiều việc concurrent, GC cần CPU trong khi ứng dụng tiếp tục chạy. Nếu CPU quota quá thấp hoặc máy đã bão hòa, concurrent GC có thể không theo kịp allocation rate.

ZGC cũng cần đủ heap headroom cho live set và object mới được cấp phát trong khi GC đang chạy. Nếu đặt `-Xmx` sát live set, ứng dụng có thể gặp allocation stall hoặc hết bộ nhớ dù pause của collector thấp.

~~~text
Heap capacity
+--------------------------------------+
| Live set | GC headroom | Free margin |
+--------------------------------------+
          ^ ứng dụng vẫn cấp phát
            trong khi GC chạy concurrent
~~~

Kích thước headroom cần thiết phụ thuộc allocation rate, live set, thời gian một chu kỳ GC và tải hệ thống. Không có một tỷ lệ cố định đúng cho mọi ứng dụng.

### Footprint và uncommit

ZGC có thể uncommit heap memory không còn dùng để trả lại bộ nhớ cho hệ điều hành. Hành vi này giúp giảm footprint ở môi trường cần chia sẻ RAM với nhiều process. Tuy nhiên, commit/uncommit trong lúc ứng dụng chạy có thể ảnh hưởng latency.

Nếu ưu tiên latency rất thấp và đã biết nhu cầu heap ổn định, có thể cân nhắc cấu hình `-Xms` và `-Xmx` bằng nhau cùng `-XX:+AlwaysPreTouch` để xử lý việc backing memory sớm hơn lúc startup. Cách này có thể tăng footprint và thời gian khởi động, nên chỉ dùng khi benchmark chứng minh có lợi.

## 8. Shenandoah: lựa chọn low-pause khi runtime hỗ trợ

Shenandoah là collector concurrent hướng tới pause thấp, với thời gian pause không tỷ lệ trực tiếp với kích thước heap. Một số JDK distribution cung cấp Shenandoah, nhưng khả năng hỗ trợ phụ thuộc nhà cung cấp, nền tảng và build.

Kiểm tra đúng runtime trước khi đưa vào cấu hình:

~~~text
java -XX:+UseShenandoahGC -version
~~~

Nếu runtime không hỗ trợ, JVM sẽ báo lỗi khi nhận tùy chọn. Không giả định một JDK vendor có Shenandoah chỉ vì tài liệu OpenJDK mô tả collector này.

Shenandoah cũng thực hiện nhiều công việc concurrent nên cần CPU headroom và có thể làm giảm throughput so với collector thiên throughput. Khi so sánh với ZGC, cần dùng cùng workload, JDK distribution đã xác nhận hỗ trợ và cùng giới hạn tài nguyên.

## 9. CPU, throughput và footprint: nhìn theo tình huống

| Tình huống | Collector đáng thử trước | Lý do | Điều cần đo |
|---|---|---|---|
| CLI nhỏ, chạy ngắn, heap nhỏ | Serial | Overhead thấp, không cần nhiều GC worker | Startup, tổng thời gian chạy, RSS |
| Batch xử lý dữ liệu, chấp nhận pause | Parallel | Tập trung throughput và tận dụng nhiều CPU | Records/second, GC CPU, thời gian pause dài nhất |
| Backend server thông thường | G1 mặc định | Cân bằng latency và throughput | p95/p99, throughput, GC CPU, committed heap |
| API có SLO tail latency rất nghiêm ngặt | ZGC hoặc Shenandoah nếu hỗ trợ | Giảm ảnh hưởng pause tới request | p99/p99.9, CPU headroom, allocation stalls, RSS |
| Container có memory limit chặt | Đo G1, ZGC và collector phù hợp workload | Cách giữ/uncommit heap và native overhead khác nhau | RSS/working set, heap committed, native memory, OOM |
| CPU quota rất thấp | Đo G1 mặc định và Serial/Parallel tùy workload | Concurrent GC có thể tranh CPU với ứng dụng | CPU throttling, GC CPU, throughput, tail latency |

Đây là điểm bắt đầu để thử nghiệm, không phải quy tắc chọn collector chỉ dựa vào loại ứng dụng. Cấu trúc object, live set, allocation rate và phần cứng có thể làm kết quả thay đổi.

## 10. Footprint không chỉ là kích thước heap

Khi collector cần thêm cấu trúc để quản lý heap hoặc thực hiện concurrent work, native memory của process có thể tăng. G1 có remembered sets; các collector concurrent khác có metadata, barrier và worker state riêng.

Khi đánh giá memory footprint, ghi nhận ít nhất:

- RSS hoặc container working set.
- Heap used, committed và max.
- Metaspace và compressed class space nếu có.
- Số thread và thread stack.
- Code cache.
- Direct buffer và native allocation do thư viện sử dụng.
- Memory limit và CPU quota của container.

Một collector có heap committed thấp hơn vẫn có thể có RSS cao hơn nếu native overhead hoặc thread count lớn. Ngược lại, RSS có thể chưa giảm ngay sau GC vì JVM giữ vùng committed để tái sử dụng.

## 11. Thiết kế benchmark so sánh công bằng

Đổi collector chỉ có ý nghĩa khi so sánh trên workload đại diện. Một benchmark chỉ cấp phát object trong vòng lặp nhỏ có thể không phản ánh hành vi production.

### Cố định điều kiện

Trong lượt so sánh đầu:

1. Dùng cùng phiên bản JDK và cùng vendor/build.
2. Dùng cùng máy hoặc cùng loại instance.
3. Giữ nguyên CPU quota, memory limit và số worker của ứng dụng.
4. Dùng cùng dataset, request mix, concurrency và thời gian chạy.
5. Giữ cấu hình heap tương đương để so sánh collector trước; sau đó mới tinh chỉnh riêng theo từng collector.
6. Chạy warm-up trước khi đo để giảm ảnh hưởng JIT compilation và cache lạnh.
7. Lặp lại nhiều lần và so sánh median cùng percentile, không chọn một lần chạy thuận lợi.

Nếu đang đo footprint, không nên ép giá trị `-Xms` và `-Xmx` bằng nhau cho mọi collector một cách máy móc. Hãy tách hai phép thử: một phép thử cố định heap để so sánh GC behavior; một phép thử cấu hình vận hành thực tế để đo RSS và memory limit.

### Đo các chỉ số giống nhau

| Chỉ số | Mục đích |
|---|---|
| Application throughput | Số request/record xử lý mỗi giây |
| p50/p95/p99/p99.9 latency | Độ trễ trung vị và tail latency |
| GC pause count và duration | Tần suất và thời gian dừng ứng dụng |
| GC CPU time | CPU dành cho công việc GC |
| CPU utilization/throttling | Mức tranh chấp CPU và giới hạn container |
| Allocation rate | Lượng object được cấp phát theo thời gian |
| Live set/heap occupancy | Lượng dữ liệu còn sống và áp lực lên heap |
| Heap committed và RSS | Bộ nhớ heap và footprint tiến trình |
| Full GC/allocation stall/OOM | Dấu hiệu collector không theo kịp workload |

Không chỉ nhìn pause trung bình. Một hệ thống có average pause thấp nhưng p99.9 cao vẫn có thể vi phạm SLO.

## 12. Bật unified GC logging trên JDK hiện đại

Unified logging là cách hiện hành để thu thập GC log:

~~~text
java \
    -Xlog:gc*,gc+heap=info,gc+cpu=info:file=logs/gc.log:time,uptime,level,tags \
    -jar service.jar
~~~

Trên PowerShell hoặc Windows command prompt, có thể viết lệnh trên một dòng và điều chỉnh dấu phân cách đường dẫn theo hệ điều hành.

Các tag thường hữu ích:

| Tag | Thông tin |
|---|---|
| `gc` | Sự kiện GC và pause |
| `gc+heap` | Trạng thái heap trước/sau các sự kiện |
| `gc+cpu` | User, system và real time của GC pause |
| `gc+ergo` | Quyết định ergonomics của JVM |
| `gc+phases` | Các pha chi tiết của GC |

Không bật mọi mức debug trong production nếu chưa đánh giá lượng log và overhead. Bắt đầu bằng `gc*` và thêm tag chi tiết khi cần điều tra.

Có thể xác minh collector và flags thực tế:

~~~text
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`VM.flags` giúp xem các cờ đang có hiệu lực; `GC.heap_info` cung cấp thông tin heap theo collector. Output phụ thuộc phiên bản JVM, vì vậy cần đọc cùng GC log và tài liệu của runtime đích.

## 13. Đọc GC log để biết collector đang trả giá ở đâu

Một quy trình phân tích:

1. Xác định tên collector và JDK build từ startup log hoặc `VM.flags`.
2. Đếm số pause theo loại và thời gian của từng pause.
3. Xem p95/p99 của pause, không chỉ average.
4. Đối chiếu `gc+cpu` để biết GC tiêu thụ bao nhiêu CPU và thời gian real có bị kéo dài bởi CPU scheduling hay không.
5. Xem heap before/after và allocation rate để hiểu áp lực cấp phát.
6. Đối chiếu timestamp với application latency, throughput và CPU throttling.
7. Kiểm tra Full GC, evacuation failure, allocation stall hoặc concurrent cycle không hoàn tất kịp.

Nếu pause ngắn nhưng throughput giảm và CPU tăng, có thể collector đang dùng nhiều CPU cho công việc concurrent. Nếu GC CPU thấp nhưng pause dài, có thể workload thiên stop-the-world, heap/live set lớn hoặc GC không có đủ worker/CPU. Nếu RSS cao dù heap used thấp, kiểm tra committed heap, native memory và chính sách uncommit.

## 14. Ví dụ benchmark ba cấu hình

Giả sử một API service có yêu cầu p99 dưới 100 ms. Có thể tạo ba application run giống nhau:

~~~text
# Baseline: G1 mặc định
java -Xms2g -Xmx4g \
    -Xlog:gc*:file=logs/g1.log:time,uptime,level,tags \
    -jar service.jar

# Thử Parallel khi muốn biết throughput tối đa
java -XX:+UseParallelGC -Xms2g -Xmx4g \
    -Xlog:gc*:file=logs/parallel.log:time,uptime,level,tags \
    -jar service.jar

# Thử ZGC khi p99 latency là ưu tiên
java -XX:+UseZGC -Xms2g -Xmx4g \
    -Xlog:gc*:file=logs/zgc.log:time,uptime,level,tags \
    -jar service.jar
~~~

Các con số heap chỉ là ví dụ. Trong thực tế cần xác định live set, allocation rate và memory limit trước khi chọn `-Xms`/`-Xmx`. ZGC cần đủ headroom để thu gom concurrent; cùng một `-Xmx` không bảo đảm mọi collector có điều kiện hoạt động tối ưu.

Chạy cùng kịch bản tải và ghi lại:

| Kết quả | G1 | Parallel | ZGC |
|---|---:|---:|---:|
| Requests/second | Đo thực tế | Đo thực tế | Đo thực tế |
| p99 latency | Đo thực tế | Đo thực tế | Đo thực tế |
| p99 GC pause | Đo thực tế | Đo thực tế | Đo thực tế |
| GC CPU time | Đo thực tế | Đo thực tế | Đo thực tế |
| Peak RSS | Đo thực tế | Đo thực tế | Đo thực tế |
| Allocation stalls | Đo thực tế | Đo thực tế | Đo thực tế |

Chọn cấu hình đạt SLO và giới hạn tài nguyên trong tải bình thường lẫn tải đỉnh. Nếu hai cấu hình đều đạt SLO, ưu tiên cấu hình có throughput tốt hơn và footprint/CPU phù hợp hơn với chi phí vận hành.

## 15. Các lỗi chọn và tuning collector thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Chọn collector chỉ vì pause trung bình thấp | Có thể bỏ qua p99, throughput hoặc CPU cost | Đo tail latency, throughput và GC CPU cùng lúc |
| Chọn ZGC cho mọi service | CPU và heap headroom có thể trở thành chi phí không cần thiết | Chỉ chọn khi SLO latency chứng minh lợi ích |
| Chọn Parallel cho API có SLO chặt | Pause dài có thể làm tăng timeout và tail latency | Benchmark G1 và collector low-pause |
| Tăng `-Xmx` mà không đo live set | RSS có thể vượt memory limit | Đo live set, committed heap và native footprint |
| Đặt `MaxGCPauseMillis` quá thấp | G1 có thể tăng công việc GC hoặc cần thêm heap | Điều chỉnh sau khi có GC log và SLO thực tế |
| Cố định young generation quá sớm | Cản trở ergonomics của G1 | Để G1 tự điều chỉnh trước |
| So sánh collector trên JDK khác nhau | Nhầm cải thiện runtime với khác biệt collector | Dùng cùng JDK build trong lượt benchmark |
| Benchmark không có warm-up | JIT và cache làm sai kết quả | Tách warm-up khỏi giai đoạn đo |
| Chỉ nhìn heap used | Bỏ qua native memory và RSS | Theo dõi toàn bộ process/container footprint |
| Ép `-Xms` và `-Xmx` bằng nhau cho mọi bài đo footprint | Có thể làm tăng RSS và không phản ánh cấu hình vận hành thực tế | Có lượt so sánh kiểm soát và lượt đo cấu hình production |
| Dùng flag cũ từ bài viết không rõ phiên bản | Flag có thể bị loại bỏ hoặc thay đổi ý nghĩa | Kiểm tra `java -XX:+PrintFlagsFinal -version` và docs của JDK đang chạy |

## 16. Quy trình chọn collector trong thực tế

1. Xác định SLO latency, throughput tối thiểu, CPU quota và memory limit.
2. Đo allocation rate, live set và thời gian pause của cấu hình hiện tại.
3. Bắt đầu với collector mặc định của JDK, thường là G1 trên server-class machine.
4. Bật GC logging ở mức phù hợp và thu thập số liệu trong workload đại diện.
5. Nếu throughput là ưu tiên và pause có thể chấp nhận, benchmark Parallel.
6. Nếu tail latency là ưu tiên và pause hiện tại vi phạm SLO, benchmark ZGC hoặc Shenandoah khi runtime hỗ trợ.
7. Nếu workload nhỏ và tài nguyên hạn chế, thử Serial khi có lý do đo được.
8. So sánh CPU, throughput, pause percentiles, RSS và allocation stalls.
9. Điều chỉnh heap trước khi thêm nhiều tuning flag chuyên sâu.
10. Triển khai canary, quan sát production và giữ phương án rollback.

## 17. Checklist review

- [ ] Đã định nghĩa rõ latency SLO và throughput mục tiêu.
- [ ] Đã ghi nhận CPU quota, memory limit và loại máy.
- [ ] Đã đo allocation rate và live set.
- [ ] Đã xác minh collector thực tế trên JVM đích.
- [ ] Đã bắt đầu từ mặc định trước khi đổi collector.
- [ ] Đã dùng cùng JDK build, workload và điều kiện tải để so sánh.
- [ ] Đã đo p95/p99/p99.9 latency và pause, không chỉ average.
- [ ] Đã đo GC CPU time và CPU throttling.
- [ ] Đã đo heap committed, RSS và native footprint.
- [ ] Đã kiểm tra headroom cho collector concurrent.
- [ ] Đã xem GC log trước khi thay nhiều tuning flag.
- [ ] Đã benchmark trên tải đỉnh và workload gần production.
- [ ] Đã thử canary và có rollback plan.
- [ ] Đã xác minh collector được hỗ trợ bởi JDK vendor/platform thực tế.

## 18. Ghi nhớ

- CPU, throughput và footprint là các mục tiêu liên quan nhưng không thể tối ưu độc lập.
- Serial có overhead thấp cho workload nhỏ; Parallel ưu tiên throughput và chấp nhận pause dài hơn.
- G1 là lựa chọn cân bằng và mặc định phổ biến trên HotSpot server-class machine.
- ZGC và Shenandoah hướng tới pause thấp bằng công việc concurrent, đổi lại cần CPU và heap headroom.
- ZGC là generational từ JDK 24; không dùng lại tùy chọn generational cũ đã bị loại bỏ.
- Shenandoah chỉ nên chọn sau khi xác minh runtime distribution và nền tảng hỗ trợ.
- G1 có remembered-set và concurrent-work overhead; JDK 26 cải thiện throughput G1 qua JEP 522.
- `-XX:MaxGCPauseMillis` là mục tiêu hướng dẫn, không phải cam kết pause-time.
- `-Xmx` không phải footprint; cần xem heap committed, RSS và native memory.
- Dùng unified GC logging, `jcmd` và benchmark đại diện để ra quyết định.
- Không có collector tốt nhất cho mọi workload; chọn theo SLO và số liệu trên môi trường thực tế.

Chọn collector là một quyết định vận hành dựa trên trade-off. Hãy bắt đầu với mặc định phù hợp của JDK, đo pause, throughput, CPU và footprint trên cùng workload, rồi chỉ đổi collector khi số liệu cho thấy cấu hình mới giải quyết được một giới hạn cụ thể mà không vượt quá ngân sách tài nguyên.

## Tài liệu tham khảo

- [Available Collectors — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html) — đặc điểm và hướng dẫn chọn Serial, Parallel, G1 và ZGC.
- [Garbage-First (G1) Garbage Collector — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html) — mục tiêu latency/throughput, overhead concurrent và remembered sets.
- [Garbage Collection Tuning Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/introduction-garbage-collection-tuning.html) — định nghĩa throughput, latency, footprint và chiến lược tuning.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — các tùy chọn bật collector và cấu hình runtime.
- [The Z Garbage Collector — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html) — generational ZGC, heap headroom và uncommit.
- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522) — thay đổi throughput của G1 trong JDK 26.
