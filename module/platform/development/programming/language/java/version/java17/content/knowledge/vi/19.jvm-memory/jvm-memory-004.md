# Chọn Serial, Parallel hoặc G1 theo đặc điểm ứng dụng trong Java 17

Garbage Collector (GC) thu hồi vùng nhớ heap mà ứng dụng không còn sử dụng. Việc chọn GC ảnh hưởng đến cách JVM sử dụng CPU, thông lượng xử lý và thời gian ứng dụng phải tạm dừng để thu gom bộ nhớ. Java 17 cung cấp các collector phổ biến gồm **Serial GC**, **Parallel GC** và **G1 GC**; mỗi loại phù hợp với một nhóm workload khác nhau.

Không có một GC tốt nhất cho mọi ứng dụng. Serial ưu tiên sự đơn giản và chi phí vận hành thấp; Parallel ưu tiên thông lượng trên hệ thống có nhiều CPU; G1 hướng đến sự cân bằng giữa thông lượng và thời gian pause có thể điều chỉnh mục tiêu. Lựa chọn nên dựa trên đặc điểm workload, giới hạn CPU/bộ nhớ và số liệu đo thực tế.

Bài này tập trung vào ba GC trên Java 17, cách hoạt động, trường hợp sử dụng, cách bật bằng JVM options và cách kiểm chứng lựa chọn qua GC log. Các tùy chọn được trình bày là các tùy chọn HotSpot đang dùng trong Java 17.

## 1. GC ảnh hưởng đến ứng dụng như thế nào?

Đối tượng Java thường được cấp phát trên heap. Khi object không còn được tham chiếu từ các đường dẫn có thể truy cập, GC có thể thu hồi vùng nhớ của nó. JVM phải xác định object nào còn sống, thu hồi vùng nhớ của object không còn cần thiết và chuẩn bị vùng trống cho các lần cấp phát tiếp theo.

Một số hoạt động GC có thể chạy song song hoặc đồng thời với ứng dụng, nhưng các collector vẫn có những giai đoạn **stop-the-world (STW)**. Trong giai đoạn STW, các thread ứng dụng bị tạm dừng để JVM thực hiện công việc cần sự nhất quán của heap.

Do đó, GC ảnh hưởng đến một số chỉ số:

- **Throughput:** tỷ lệ thời gian JVM dành cho công việc ứng dụng thay vì GC.
- **Pause time:** thời gian ứng dụng bị dừng trong một lần pause.
- **Độ trễ (latency):** thời gian người dùng chờ một request hoặc tác vụ hoàn tất; pause GC có thể góp phần làm tăng latency.
- **CPU usage:** CPU time dùng cho thread ứng dụng và thread GC.
- **Memory footprint:** heap, metadata, thread stack, direct buffer và các vùng native khác mà process sử dụng.

Ví dụ, một ứng dụng batch xử lý hàng triệu bản ghi có thể ưu tiên hoàn thành công việc nhanh nhất, ngay cả khi đôi lúc GC pause dài hơn. Một API phục vụ người dùng tương tác có thể cần hạn chế pause để giảm độ trễ ở các percentile cao như p95 hoặc p99.

Không nên đánh giá GC chỉ bằng một chỉ số. Pause ngắn nhưng CPU tiêu thụ quá nhiều có thể làm ứng dụng chậm tổng thể; throughput cao nhưng pause quá dài cũng có thể không đáp ứng SLA.

## 2. Ba lựa chọn trong Java 17

Ba collector có mục tiêu thiết kế khác nhau:

| GC | Mục tiêu chính | Đặc điểm nổi bật | Kiểu workload thường cân nhắc |
| --- | --- | --- | --- |
| Serial GC | Đơn giản, overhead thấp | Thu gom bằng một thread GC; các pha thu gom dừng thread ứng dụng | Ứng dụng nhỏ, heap nhỏ, môi trường ít CPU |
| Parallel GC | Thông lượng cao | Dùng nhiều thread GC để thu gom; có thể tận dụng nhiều core | Batch, xử lý nền, workload ưu tiên throughput |
| G1 GC | Cân bằng throughput và pause | Chia heap thành region, thu gom theo collection set, có các pha concurrent | Dịch vụ server, heap vừa/lớn, ứng dụng cần kiểm soát mục tiêu pause |

Có thể chọn rõ collector bằng các JVM option:

```bash
# Serial GC
java -XX:+UseSerialGC -jar app.jar

# Parallel GC
java -XX:+UseParallelGC -jar app.jar

# G1 GC
java -XX:+UseG1GC -jar app.jar
```

Trong một cấu hình JVM, hãy chọn một collector chính. Không bật đồng thời nhiều cờ lựa chọn như `UseSerialGC`, `UseParallelGC` và `UseG1GC` để mong JVM phối hợp chúng; các cờ này chọn những chiến lược GC khác nhau.

## 3. Serial GC: đơn giản và dùng một thread thu gom

Serial GC thực hiện các công việc thu gom bằng một thread GC. Các pha thu gom chính dừng các thread ứng dụng trong lúc GC chạy.

Bật Serial GC:

```bash
java -XX:+UseSerialGC -jar app.jar
```

### Cách hoạt động

Serial GC có các vùng thế hệ trẻ (young generation) và già (old generation):

- Young generation sử dụng cơ chế copying để di chuyển object còn sống sang vùng phù hợp và thu hồi vùng cũ.
- Old generation được thu gom bằng cơ chế mark và compact.
- Các pha thu gom diễn ra theo kiểu stop-the-world và chỉ dùng một thread GC.

Do chỉ có một thread thu gom, Serial không cần phối hợp nhiều GC worker. Điều này giúp giảm overhead trong môi trường ít CPU hoặc heap nhỏ. Tuy nhiên, khi heap lớn hoặc object graph nhiều, thời gian pause có thể tăng vì công việc GC không được chia cho nhiều core.

### Khi nào cân nhắc Serial GC?

Serial thường đáng cân nhắc khi:

- Ứng dụng nhỏ, chạy một tiến trình đơn giản.
- Heap nhỏ và tốc độ cấp phát object không cao.
- Môi trường triển khai có ít CPU hoặc bị giới hạn CPU chặt.
- Chi phí CPU và độ phức tạp của GC quan trọng hơn pause dài trong một số thời điểm.
- Ứng dụng không có yêu cầu latency nghiêm ngặt.

Ví dụ: tiện ích command-line chạy trong thời gian ngắn, tác vụ chuyển đổi dữ liệu nhỏ hoặc một service phụ có heap và mức đồng thời thấp.

### Khi nào Serial không phù hợp?

Serial thường không phải lựa chọn tốt cho server nhiều request đồng thời hoặc workload cấp phát nhiều trên heap lớn. Một thread GC có thể không thu gom đủ nhanh, khiến ứng dụng phải chờ các pha STW lâu hơn.

Không nên chọn Serial chỉ vì nó có ít thread GC. Hãy xem cả thời gian pause, tần suất GC và lượng CPU mà ứng dụng cần để hoàn thành công việc.

## 4. Parallel GC: ưu tiên thông lượng

Parallel GC còn được gọi là throughput collector. Nó sử dụng nhiều thread GC để thực hiện các pha thu gom, tận dụng nhiều core CPU nhằm rút ngắn tổng thời gian dành cho GC.

Bật Parallel GC:

```bash
java -XX:+UseParallelGC -jar app.jar
```

Trong HotSpot Java 17, lựa chọn này sử dụng các cơ chế parallel cho young generation và old generation. Các pha thu gom vẫn có stop-the-world pause; khác biệt chính là nhiều thread GC cùng làm việc trong pause đó.

### Cách hoạt động

- Young generation được thu gom bằng parallel copying.
- Old generation sử dụng parallel mark-compact.
- Nhiều GC worker xử lý các phần công việc cùng lúc.
- JVM có thể điều chỉnh kích thước vùng heap theo mục tiêu throughput và pause được cấu hình.

Parallel GC phù hợp với workload có thể tận dụng nhiều CPU và ưu tiên tổng lượng công việc hoàn tất trong một khoảng thời gian.

### Khi nào cân nhắc Parallel GC?

- Batch xử lý dữ liệu lớn.
- Tác vụ tính toán nền hoặc ETL.
- Ứng dụng có thông lượng cao là mục tiêu chính.
- Có nhiều core CPU để GC worker sử dụng.
- Có thể chấp nhận pause dài hơn G1 trong một số tình huống.
- SLA không quá nhạy với một vài khoảng dừng GC dài.

Ví dụ, một chương trình tổng hợp báo cáo chạy theo lịch có thể ưu tiên hoàn thành 10 triệu bản ghi trong thời gian ngắn. Nếu người dùng không chờ tương tác trong lúc batch chạy, throughput có thể quan trọng hơn việc giữ mọi pause thật ngắn.

### Điểm cần cân nhắc

Parallel GC có thể sử dụng nhiều CPU cho GC. Nếu container chỉ được cấp ít CPU hoặc ứng dụng đã bận xử lý request, GC worker có thể cạnh tranh CPU với thread ứng dụng.

Pause vẫn là STW. Việc có nhiều thread GC không đồng nghĩa ứng dụng không bị dừng; nó chỉ giúp nhiều phần công việc GC được thực hiện song song trong khoảng dừng.

## 5. G1 GC: chia heap thành region và hướng đến mục tiêu pause

G1 (Garbage-First) là collector theo region. Thay vì coi heap là các vùng liên tục có kích thước cố định theo cách truyền thống, G1 chia heap thành nhiều **region** có kích thước bằng nhau. Các region được dùng cho young generation, old generation hoặc các mục đích quản lý khác tại từng thời điểm.

Bật G1:

```bash
java -XX:+UseG1GC -jar app.jar
```

Trong Java 17, G1 là GC mặc định trên các cấu hình JVM server-class theo ergonomics. Mặc định thực tế vẫn phụ thuộc nền tảng, cấu hình JVM và các tùy chọn được truyền vào. Nếu muốn biết JVM đang chọn gì, hãy kiểm tra flags và GC log thay vì suy đoán từ phiên bản Java.

### Cách hoạt động ở mức khái quát

G1 thực hiện các loại công việc chính:

1. **Young collection:** thu gom các region thuộc young generation. Các object còn sống được evacuation sang region khác.
2. **Concurrent marking:** đánh dấu object còn sống trong heap trong khi ứng dụng vẫn tiếp tục chạy ở một số giai đoạn.
3. **Mixed collection:** sau marking, G1 có thể thu gom các young region cùng một số old region được chọn.
4. **Region reclamation:** thu hồi region sau khi object còn sống đã được chuyển đi.

G1 chọn các region có nhiều vùng trống có thể thu hồi, từ đó có tên Garbage-First. Nó có thể ưu tiên collection set dự kiến thu hồi được nhiều bộ nhớ trong giới hạn pause mục tiêu.

### Pause-time goal

Có thể cấu hình mục tiêu pause bằng:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar app.jar
```

`MaxGCPauseMillis` là **mục tiêu mềm (soft goal)**. JVM cố gắng điều chỉnh công việc GC để hướng tới pause mục tiêu, nhưng không bảo đảm mọi pause đều ngắn hơn con số đã đặt. Nếu workload tạo nhiều object, có object lớn hoặc heap không đủ dư địa, một số pause vẫn có thể vượt mục tiêu.

Không nên đặt một con số rất thấp với kỳ vọng G1 sẽ luôn đáp ứng. Mục tiêu quá chặt có thể khiến GC thu gom từng phần nhỏ hơn, tăng tần suất công việc và ảnh hưởng throughput.

### Khi nào cân nhắc G1?

- Dịch vụ server xử lý nhiều request.
- Heap vừa hoặc lớn.
- Cần cân bằng giữa throughput và pause time.
- Muốn có mục tiêu pause để JVM điều chỉnh collection set.
- Workload có yêu cầu latency nhưng không phải hệ thống hard real-time.

G1 là lựa chọn tổng quát tốt cho nhiều ứng dụng server Java 17. Tuy nhiên, nó không tự bảo đảm latency thấp nếu ứng dụng cấp phát quá nhiều object, có memory leak hoặc bị giới hạn CPU/bộ nhớ.

## 6. So sánh sâu hơn

| Tiêu chí | Serial | Parallel | G1 |
| --- | --- | --- | --- |
| Thread GC | Một thread | Nhiều thread | Nhiều thread cho các pha parallel; có pha concurrent |
| Mục tiêu chính | Đơn giản, overhead thấp | Throughput | Cân bằng throughput và pause goal |
| Heap organization | Young/old generation | Young/old generation | Region-based heap, vẫn có young/old generations |
| Pha STW | Có | Có | Có |
| Pha concurrent marking | Không theo thiết kế của Serial GC | Không theo thiết kế của Parallel GC | Có |
| Khả năng tận dụng nhiều core | Thấp | Cao trong các pha GC parallel | Có |
| Pause time | Có thể dài khi heap/workload tăng | Có thể dài; nhiều worker rút ngắn công việc GC | Hướng đến pause mục tiêu, không bảo đảm cứng |
| Overhead điều phối | Thấp | Chi phí phối hợp worker | Có thêm chi phí quản lý region và concurrent work |
| Trường hợp thường cân nhắc | App nhỏ, ít CPU | Batch, throughput cao | Server, heap vừa/lớn, cần cân bằng |

Không nên dùng bảng này như một quy tắc tuyệt đối. Ví dụ, Parallel GC có thể có pause tốt trong một workload cụ thể; G1 có thể tiêu thụ nhiều CPU hơn mong đợi; Serial có thể hoạt động rất hiệu quả cho một chương trình nhỏ. Số liệu của ứng dụng mới là căn cứ quyết định.

## 7. Chọn GC theo đặc điểm workload

Hãy bắt đầu từ câu hỏi ứng dụng cần tối ưu điều gì.

### Trường hợp A: ứng dụng nhỏ, ít CPU, heap nhỏ

Ví dụ:

- Công cụ dòng lệnh.
- Tác vụ chạy ngắn.
- Tiến trình phụ trong môi trường tài nguyên hạn chế.
- Ứng dụng ít object và ít thread.

Có thể thử Serial GC:

```bash
java -Xms128m -Xmx512m -XX:+UseSerialGC -jar small-tool.jar
```

Lý do: không cần nhiều GC worker, chi phí điều phối thấp. Nhưng nếu thời gian pause ảnh hưởng trực tiếp tới tác vụ, vẫn phải đo và so sánh với G1 hoặc Parallel.

### Trường hợp B: batch hoặc xử lý nền ưu tiên throughput

Ví dụ:

- ETL theo lịch.
- Tạo báo cáo lớn.
- Xử lý ảnh/tài liệu hàng loạt.
- Tính toán nền trên máy có nhiều core.

Có thể thử Parallel GC:

```bash
java -Xms4g -Xmx4g -XX:+UseParallelGC -jar batch-job.jar
```

Lý do: nhiều thread GC có thể tận dụng CPU để hoàn thành công việc thu gom nhanh hơn. Cần bảo đảm GC không chiếm hết CPU mà ứng dụng cần cho phần xử lý chính.

### Trường hợp C: server cần cân bằng throughput và latency

Ví dụ:

- REST API.
- Dịch vụ xử lý nhiều request đồng thời.
- Backend có heap lớn hơn ứng dụng tiện ích nhỏ.
- Workload cần quan sát và kiểm soát pause time.

Có thể bắt đầu bằng G1:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar service.jar
```

Lý do: G1 quản lý heap theo region, có concurrent marking và có thể điều chỉnh collection set theo pause goal.

Mốc 200 ms trong ví dụ chỉ là một cấu hình minh họa, không phải giá trị phù hợp cho mọi dịch vụ. Hãy đặt mục tiêu dựa trên SLA và số liệu pause thực tế.

### Bảng gợi ý ban đầu

| Đặc điểm ứng dụng | GC nên thử đầu tiên | Cần xác nhận bằng số liệu |
| --- | --- | --- |
| Heap nhỏ, ít CPU, tác vụ đơn giản | Serial | Pause có ảnh hưởng đến thời gian hoàn thành không? |
| Batch CPU-bound, nhiều core, ưu tiên throughput | Parallel | Tổng thời gian GC và throughput thực tế. |
| Server, nhiều request, cần cân bằng latency/throughput | G1 | p95/p99 latency, pause distribution và CPU. |
| Container bị giới hạn CPU | Serial hoặc G1/Parallel tùy workload | Số GC worker và CPU contention. |
| Heap lớn, allocation rate cao | G1 là điểm bắt đầu hợp lý | Evacuation pause, concurrent cycle và khả năng cấp phát. |

Đây là hướng thử nghiệm ban đầu, không phải quy tắc lựa chọn cố định.

## 8. G1 là mặc định có nghĩa gì?

Từ Java 9, G1 trở thành GC mặc định trên các cấu hình server-class của HotSpot. Vì vậy, trên nhiều môi trường chạy Java 17 server, ứng dụng có thể đang dùng G1 dù không truyền `-XX:+UseG1GC`.

Tuy nhiên, không nên suy ra GC thực tế chỉ từ phiên bản Java:

- JVM có thể chọn collector khác theo ergonomics và đặc điểm môi trường.
- Cờ dòng lệnh có thể ghi đè lựa chọn mặc định.
- Container CPU/memory limits và nền tảng có thể ảnh hưởng cách JVM tính toán cấu hình.
- Các bản phân phối JDK hoặc cấu hình triển khai có thể khác nhau.

Kiểm tra flags đang có hiệu lực:

```bash
java -XX:+PrintCommandLineFlags -version
```

Trong tiến trình đang chạy, có thể dùng `jcmd`:

```bash
jcmd <pid> VM.flags
jcmd <pid> VM.info
```

Thay `<pid>` bằng process ID của ứng dụng. Công cụ `jcmd` đi kèm JDK. Hãy xem các flags liên quan đến collector, heap và số thread GC để biết cấu hình thực tế.

## 9. Ghi GC log trên Java 17

Java 17 sử dụng Unified Logging. Có thể bật GC log bằng tùy chọn:

```bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
```

Ví dụ chạy G1 với log:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC \
     -Xlog:gc*:file=gc-g1.log:time,uptime,level,tags \
     -jar service.jar
```

Tương tự, tạo log riêng cho Serial và Parallel:

```bash
java -Xms2g -Xmx2g -XX:+UseSerialGC \
     -Xlog:gc*:file=gc-serial.log:time,uptime,level,tags \
     -jar service.jar

java -Xms2g -Xmx2g -XX:+UseParallelGC \
     -Xlog:gc*:file=gc-parallel.log:time,uptime,level,tags \
     -jar service.jar
```

Đặt tên file log riêng để không nhầm kết quả của các lần chạy. Trong production, cần quản lý dung lượng và vòng đời log để tránh log chiếm đầy đĩa.

### Những gì cần quan sát trong GC log

Tùy collector và mức logging, log có thể cho thấy:

- Thời điểm và loại GC event.
- Pause duration.
- Dung lượng heap trước và sau GC.
- Dung lượng vùng young/old hoặc region.
- Concurrent marking/cycle của G1.
- Lý do kích hoạt GC.
- Số liệu CPU và worker ở mức log tương ứng.

Không chỉ đếm số lần GC. Một ứng dụng có nhiều young GC ngắn có thể hoạt động tốt hơn ứng dụng có ít lần GC nhưng mỗi lần pause rất dài.

## 10. Đo những chỉ số nào để so sánh?

Để chọn GC, nên thu thập các nhóm chỉ số sau.

### Pause time

Xem:

- Pause trung bình.
- Pause lớn nhất.
- Phân phối p50, p95, p99.
- Tần suất pause trong một đơn vị thời gian.

Đối với API, pause p99 có thể ảnh hưởng mạnh đến request latency dù pause trung bình thấp.

### Throughput và thời gian hoàn thành

Đo số request/giây hoặc số bản ghi/giây, cùng thời gian hoàn thành một batch. Nếu mục tiêu là throughput, cần so sánh lượng công việc hoàn tất trong cùng điều kiện.

### CPU

GC dùng CPU để đánh dấu, copy, compact hoặc evacuation. Hãy quan sát CPU toàn process và mức cạnh tranh CPU giữa GC thread và application thread.

### Heap và allocation rate

Xem:

- Heap occupancy trước và sau GC.
- Tốc độ cấp phát object.
- Tần suất young GC.
- Old generation tăng liên tục hay ổn định.
- Full GC hoặc các sự kiện thu gom bất thường.

Nếu heap tăng liên tục sau nhiều chu kỳ GC, có thể ứng dụng đang giữ tham chiếu tới object không cần thiết. Đổi GC không sửa được memory leak.

### Chỉ số ứng dụng

Kết hợp GC metrics với:

- Request latency.
- Error rate và timeout.
- Throughput.
- Queue depth.
- CPU throttling trong container.
- Memory usage của toàn process.

Một GC có pause tốt nhưng làm CPU throttling tăng có thể khiến latency ứng dụng xấu đi.

## 11. Quy trình benchmark công bằng

Không nên đổi GC trong production chỉ dựa vào một nhận xét như “G1 chậm hơn” hoặc “Parallel nhanh hơn”. Hãy thử trên workload đại diện.

Một quy trình thực tế:

1. **Chọn workload:** dùng dữ liệu, concurrency và tỷ lệ đọc/ghi gần với môi trường thật.
2. **Giữ môi trường nhất quán:** cùng JDK 17 build, CPU, memory limit, heap size, cấu hình ứng dụng và endpoint.
3. **Chạy từng collector riêng:** Serial, Parallel và G1 cần là các process/lần chạy riêng.
4. **Warm up:** để JIT, cache và hệ thống đạt trạng thái ổn định trước khi lấy số liệu chính.
5. **Ghi log:** bật Unified GC Logging và metrics ứng dụng.
6. **Lặp lại:** chạy nhiều lần để giảm ảnh hưởng của nhiễu môi trường.
7. **So sánh:** xem pause distribution, throughput, CPU, heap occupancy và SLA.
8. **Kiểm chứng trong môi trường gần production:** trước khi triển khai rộng, thử với giới hạn tài nguyên và tải thực tế.

Giữ cùng `-Xms` và `-Xmx` trong lần so sánh đầu tiên giúp giảm một biến số. Sau khi chọn được collector phù hợp, có thể thử điều chỉnh heap hoặc các tham số riêng của collector.

Không dùng một microbenchmark quá nhỏ để kết luận về GC của hệ thống lớn. GC chịu ảnh hưởng bởi allocation rate, tuổi thọ object, object graph, số thread, heap size và thời gian chạy.

## 12. Tùy chọn điều chỉnh cần biết

### 12.1. Heap size

`-Xms` đặt heap ban đầu; `-Xmx` đặt giới hạn heap tối đa:

```bash
java -Xms2g -Xmx2g -XX:+UseG1GC -jar app.jar
```

Dùng cùng giá trị trong ví dụ giúp heap không thay đổi kích thước theo cùng cách như một cấu hình chỉ đặt `-Xmx`. Tuy nhiên, không phải mọi ứng dụng đều nên đặt `-Xms` bằng `-Xmx`; quyết định phụ thuộc memory limit và hành vi cấp phát.

Đừng đặt `-Xmx` bằng toàn bộ memory limit của container. Process còn cần metaspace, thread stacks, direct buffers, JIT code cache và native memory khác.

### 12.2. Mục tiêu pause của G1

`-XX:MaxGCPauseMillis` cho G1 một mục tiêu pause mềm:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=150 -jar app.jar
```

Giảm mục tiêu pause có thể làm G1 chọn collection set nhỏ hơn hoặc điều chỉnh công việc, nhưng có thể tăng tần suất GC và ảnh hưởng throughput. Hãy thay đổi từng bước và quan sát log.

### 12.3. Mục tiêu throughput của Parallel

Parallel GC có thể dùng `-XX:GCTimeRatio` để biểu diễn mục tiêu tỷ lệ thời gian dành cho ứng dụng so với thời gian GC:

```bash
java -XX:+UseParallelGC -XX:GCTimeRatio=19 -jar batch.jar
```

Giá trị này là mục tiêu cho ergonomics, không phải cam kết tuyệt đối về throughput. JVM có thể điều chỉnh heap để hướng đến mục tiêu, trong giới hạn tài nguyên và các cấu hình khác.

Có thể đặt mục tiêu pause bằng `-XX:MaxGCPauseMillis` cho Parallel GC, nhưng việc tối ưu pause có thể làm giảm throughput. Không nên đặt cả hai mục tiêu cực đoan mà không hiểu trade-off.

### 12.4. Không chỉnh số thread GC ngay từ đầu

Các cờ như `-XX:ParallelGCThreads` và `-XX:ConcGCThreads` cho phép tác động đến số thread ở các pha GC phù hợp. Tuy nhiên, JVM có ergonomics để tự chọn số thread dựa trên CPU và cấu hình.

Chỉ chỉnh các cờ này khi log và profiling cho thấy có vấn đề cụ thể, chẳng hạn GC thread cạnh tranh CPU hoặc số worker không phù hợp với giới hạn container. Thay đổi số thread mà không đo có thể làm hiệu năng tệ hơn.

## 13. Những dấu hiệu cho thấy cần xem lại lựa chọn GC

### Pause dài và ảnh hưởng p99

Nếu ứng dụng có pause dài trùng với request latency tăng, hãy xem GC event, heap pressure và allocation rate. G1 có thể là lựa chọn đáng thử nếu đang dùng Serial hoặc Parallel và ứng dụng cần cân bằng pause.

### CPU GC quá cao

Nếu GC sử dụng nhiều CPU, kiểm tra allocation rate, object lifetime, heap size và số worker. Parallel có thể tận dụng nhiều core để tăng throughput nhưng cũng có thể cạnh tranh với application thread. G1 cũng cần CPU cho marking và evacuation.

### Full GC lặp lại

Full GC thường là dấu hiệu cần điều tra heap pressure, old generation, khả năng cấp phát hoặc object được giữ tham chiếu lâu. Không nên chỉ đổi collector để che triệu chứng.

### Heap luôn gần đầy

Heap occupancy cao sau GC có thể do live set thực sự lớn, memory leak hoặc heap quá nhỏ. Cần phân tích heap dump hoặc dữ liệu allocation/liveness phù hợp. Tăng `-Xmx` chỉ là giải pháp nếu ứng dụng thật sự cần thêm heap và máy/container còn đủ memory.

### Pause goal không đạt

Với G1, `MaxGCPauseMillis` là mục tiêu mềm. Nếu pause vượt mục tiêu, kiểm tra kích thước object, humongous allocations, heap headroom, allocation rate và CPU availability. Không coi việc tăng hoặc giảm con số mục tiêu là cách sửa mọi vấn đề.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| Parallel GC không dừng ứng dụng vì có nhiều thread. | Parallel GC vẫn có STW pause; nhiều thread chỉ chia sẻ công việc GC trong pause. |
| G1 bảo đảm mọi pause dưới `MaxGCPauseMillis`. | Đây là mục tiêu mềm, không phải giới hạn thời gian cứng. |
| G1 luôn nhanh hơn Parallel. | G1 và Parallel có mục tiêu khác nhau; workload và phần cứng quyết định kết quả. |
| Serial luôn chậm. | Với heap nhỏ và ít CPU, overhead thấp của Serial có thể phù hợp. |
| GC mặc định giống nhau trên mọi máy Java 17. | JVM ergonomics và cấu hình môi trường có thể ảnh hưởng collector được chọn. |
| Tăng `-Xmx` luôn sửa được GC chậm. | Heap lớn hơn có thể giảm tần suất GC nhưng cũng có thể làm một số pha thu gom dài hơn và tăng memory footprint. |
| Ít lần GC hơn luôn tốt hơn. | Cần xét pause duration, throughput và tác động đến ứng dụng. |
| GC log có thể cho biết memory leak ngay lập tức. | Log giúp phát hiện dấu hiệu; xác định object giữ tham chiếu thường cần heap analysis. |
| Chỉ cần chọn GC, không cần đo. | Lựa chọn phải được kiểm chứng bằng workload đại diện và số liệu. |

## 15. Serial, Parallel hay G1: quy trình ra quyết định

Có thể dùng chuỗi câu hỏi sau để chọn điểm bắt đầu:

```text
Ứng dụng có heap nhỏ, ít CPU và ít đồng thời?
                 |
          +------+------+
          |             |
         Có            Không
          |             |
          v             v
      Thử Serial   Mục tiêu chính là throughput?
                        |
                  +-----+-----+
                  |           |
                 Có          Không
                  |           |
                  v           v
            Thử Parallel   Cần cân bằng latency
                           và throughput?
                                |
                                v
                              Thử G1
                                |
                                v
                       Benchmark workload thật
                                |
                                v
                    Chọn theo pause, CPU, throughput,
                    heap và SLA thực tế
```

Đây là quy trình chọn **điểm bắt đầu**. Kết quả benchmark có thể khiến bạn chọn collector khác với gợi ý ban đầu.

## 16. Ví dụ chạy cùng ứng dụng với ba GC

Giả sử có một ứng dụng batch hoặc service đóng gói thành `app.jar`. Để so sánh, chạy các process riêng với cùng heap size và cùng GC log format:

```bash
java -Xms2g -Xmx2g -XX:+UseSerialGC \
     -Xlog:gc*:file=serial.log:time,uptime,level,tags \
     -jar app.jar

java -Xms2g -Xmx2g -XX:+UseParallelGC \
     -Xlog:gc*:file=parallel.log:time,uptime,level,tags \
     -jar app.jar

java -Xms2g -Xmx2g -XX:+UseG1GC \
     -Xlog:gc*:file=g1.log:time,uptime,level,tags \
     -jar app.jar
```

Trong mỗi lần chạy, dùng cùng bộ dữ liệu và cùng kịch bản tải. Ghi lại ít nhất:

| Chỉ số | Serial | Parallel | G1 |
| --- | --- | --- | --- |
| Thời gian hoàn thành workload | Đo | Đo | Đo |
| Throughput (request/s hoặc record/s) | Đo | Đo | Đo |
| Pause p95/p99/max | Đo | Đo | Đo |
| Tổng thời gian GC | Đo | Đo | Đo |
| CPU process | Đo | Đo | Đo |
| Heap sau GC | Đo | Đo | Đo |
| Số lần Full GC | Đo | Đo | Đo |
| Error/timeout ứng dụng | Đo | Đo | Đo |

Không điền số liệu dự đoán vào bảng. Kết quả phụ thuộc ứng dụng và môi trường chạy.

## 17. Một số lưu ý cho ứng dụng container

Trong môi trường container, JVM có thể nhận biết giới hạn CPU và memory của container trên các nền tảng được hỗ trợ. Điều này ảnh hưởng đến ergonomics, kích thước heap mặc định và số thread GC.

Khi so sánh các collector trong container:

- Giữ cùng CPU quota và memory limit.
- Kiểm tra JVM nhận diện số CPU như thế nào.
- Không giả định host có 32 core nghĩa là container cũng được dùng cả 32 core.
- Theo dõi CPU throttling và memory pressure.
- Dành bộ nhớ cho native memory ngoài heap.
- Dùng cùng cấu hình heap trong các lần benchmark.

Một GC parallel có nhiều worker chưa chắc hữu ích nếu container chỉ được cấp một hoặc hai CPU. Ngược lại, ép Serial trong một container có nhiều CPU và workload cấp phát cao có thể làm GC trở thành nút thắt.

## 18. Khi nào ba lựa chọn này chưa đủ?

Serial, Parallel và G1 đáp ứng nhiều workload Java phổ biến. Tuy nhiên, nếu hệ thống có yêu cầu pause cực thấp hoặc đặc điểm heap đặc biệt, có thể cần đánh giá các collector khác được JDK/vendor cung cấp, chẳng hạn ZGC hoặc Shenandoah trên bản phân phối phù hợp.

Không nên xem G1 là collector hard real-time. Nếu SLA yêu cầu giới hạn pause rất nghiêm ngặt, cần thử nghiệm riêng collector low-latency, xem xét kiến trúc, allocation rate và giới hạn tài nguyên. Việc một collector tồn tại trong Java 17 không đồng nghĩa nó có cùng trạng thái hỗ trợ hoặc mặc định trên mọi bản phân phối JDK; hãy kiểm tra tài liệu của vendor và build đang triển khai.

Bài này tập trung vào cách chọn Serial, Parallel và G1; không cần chuyển sang collector khác nếu workload hiện tại đã đáp ứng SLA.

## 19. Bài thực hành

### Bài 1 — chạy và nhận diện collector

Chạy cùng một ứng dụng nhỏ ba lần với:

- `-XX:+UseSerialGC`
- `-XX:+UseParallelGC`
- `-XX:+UseG1GC`

Bật `-Xlog:gc*` và xác định collector nào được dùng trong log.

### Bài 2 — đo throughput của batch

Tạo workload xử lý một tập dữ liệu lớn có cấp phát object. Chạy với Serial, Parallel và G1 trong cùng điều kiện. Ghi thời gian hoàn thành và số bản ghi xử lý mỗi giây.

### Bài 3 — quan sát pause

Dùng GC log để ghi lại pause time của từng collector. So sánh p95, p99 và max pause; giải thích vì sao pause trung bình không đủ để mô tả trải nghiệm của request.

### Bài 4 — thử mục tiêu pause của G1

Chạy G1 với các giá trị `-XX:MaxGCPauseMillis` khác nhau, ví dụ 100 và 200. Quan sát tần suất GC, pause distribution và throughput. Giải thích vì sao mục tiêu này không phải cam kết cứng.

### Bài 5 — kiểm tra ảnh hưởng CPU

Chạy cùng workload với CPU quota thấp và cao. Quan sát thay đổi của Serial và Parallel. Giải thích vì sao nhiều GC worker có thể không mang lại lợi ích nếu CPU bị giới hạn.

### Bài 6 — nhận diện vấn đề không giải quyết được bằng đổi GC

Tạo một workload giữ tham chiếu tới object trong một Collection tăng liên tục. Theo dõi heap sau GC. Giải thích vì sao chuyển từ Serial sang G1 không tự giải quyết memory leak.

## 20. Ghi nhớ nhanh

| Đặc điểm | Serial GC | Parallel GC | G1 GC |
| --- | --- | --- | --- |
| JVM option | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | `-XX:+UseG1GC` |
| Mục tiêu | Đơn giản, overhead thấp | Throughput | Cân bằng throughput và pause |
| GC thread | Một | Nhiều | Parallel và concurrent |
| Heap organization | Young/old | Young/old | Region-based, young/old |
| Pause | STW | STW | Có STW và concurrent phases |
| Workload gợi ý | Nhỏ, ít CPU | Batch, throughput cao | Server, latency cần cân bằng |

**Nguyên tắc cốt lõi:** Bắt đầu từ đặc điểm workload: Serial cho ứng dụng nhỏ và ít CPU, Parallel cho workload ưu tiên throughput trên nhiều core, G1 cho nhiều ứng dụng server cần cân bằng throughput và pause. Trong Java 17, G1 thường là mặc định trên server-class JVM, nhưng hãy xác nhận collector thực tế bằng flags/GC log. Benchmark trong cùng điều kiện, theo dõi pause p95/p99, throughput, CPU và heap trước khi chốt lựa chọn.
