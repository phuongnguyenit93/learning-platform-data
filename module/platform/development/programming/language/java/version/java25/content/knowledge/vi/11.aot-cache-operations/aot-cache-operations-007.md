# Thiết kế phép đo có và không có cache với nhiều lần chạy độc lập

## 1. Mục tiêu: đo lợi ích AOT cache có thể tái lập

AOT cache của HotSpot JVM có thể giảm thời gian khởi động và hỗ trợ warm-up bằng cách tái sử dụng artifacts được chuẩn bị trong lần chạy training. Tuy nhiên, kết quả phụ thuộc vào ứng dụng, workload training, JDK, hệ điều hành, CPU, classpath và cách đo. Một lần chạy nhanh hơn chưa đủ chứng minh cache có lợi; một lần chạy chậm hơn cũng chưa đủ kết luận cache làm giảm hiệu năng.

Bài thuộc chương **Vận hành AOT** của module **JAVA_VERSION_JAVA25**. Đề bài trực tiếp là **“Thiết kế phép đo có và không có cache với nhiều lần chạy độc lập”**. Nội dung tập trung vào cách thiết kế thí nghiệm, tạo baseline, lặp lại các lần khởi chạy JVM độc lập, đo startup và warm-up riêng, phân tích phân phối số liệu và đưa ra quyết định triển khai.

Trong Java 25, AOT cache được tạo bằng cơ chế dòng lệnh được cải thiện ở JEP 514; JEP 515 bổ sung method execution profiles vào cache. Vì vậy, phép đo nên quan sát cả **time-to-ready** lẫn **thời gian đạt trạng thái hiệu năng ổn định**. [JEP 514](https://openjdk.org/jeps/514) · [JEP 515](https://openjdk.org/jeps/515)

### Kết quả học tập

Sau bài này, bạn có thể:

1. Xác định đại lượng cần đo: process startup, application readiness, warm-up, throughput hay latency.
2. Tạo hai nhánh thử nghiệm có và không có AOT cache với cùng artifact và môi trường.
3. Thiết kế nhiều lần chạy độc lập, ngẫu nhiên hóa thứ tự và giảm nhiễu.
4. Phân biệt fresh JVM process với cold OS page cache.
5. Chọn số lần lặp và thống kê phù hợp; không suy luận từ một mẫu đơn lẻ.
6. Đo riêng startup, warm-up, tài nguyên và chi phí tạo/phân phối cache.
7. Xác nhận cache thực sự được nạp và nhận diện benchmark không hợp lệ.
8. Viết báo cáo có thể tái lập, có ngưỡng chấp nhận và quyết định rollout rõ ràng.

## 2. Xác định câu hỏi benchmark trước khi chạy

Cụm từ “ứng dụng khởi động nhanh hơn” thường gộp nhiều chỉ số khác nhau. Hãy xác định trước câu hỏi cần trả lời.

| Câu hỏi | Chỉ số chính | Điểm kết thúc |
| --- | --- | --- |
| JVM bắt đầu chạy đến lúc gọi main mất bao lâu? | Process/VM startup | Mốc main bắt đầu |
| Ứng dụng sẵn sàng nhận công việc khi nào? | Startup-to-ready / time-to-ready | Readiness probe đạt điều kiện |
| Sau khi ready, bao lâu mới đạt hiệu năng ổn định? | Warm-up time | Đạt ngưỡng latency/throughput đã định |
| Ứng dụng xử lý được bao nhiêu tải? | Throughput | Request/s hoặc records/s trong cửa sổ cố định |
| Chất lượng phản hồi thay đổi ra sao? | p50/p95/p99 latency | Phân phối latency dưới tải giống nhau |
| Cache có đáng chi phí không? | Cache size, training/assembly time, CPU/RAM | Tổng chi phí pipeline và vận hành |

**Không dùng một chỉ số thay cho tất cả.** AOT cache có thể cải thiện time-to-ready nhưng không thay đổi throughput steady-state; JEP 515 có thể cải thiện warm-up mà startup-to-ready chỉ thay đổi ít. Kết luận phải bám đúng câu hỏi.

### Định nghĩa mốc đo

Với server:

- **T0 — process launch:** bộ điều khiển benchmark yêu cầu khởi chạy tiến trình JVM.
- **T1 — process started:** hệ điều hành đã tạo process.
- **T2 — application ready:** readiness endpoint hoặc tín hiệu readiness thực sự đạt.
- **T3 — steady state:** workload đạt ngưỡng hiệu năng định trước trong số cửa sổ liên tiếp.

Khi đo time-to-ready, đại lượng chính là `T2 - T0`. Khi đo warm-up, đại lượng là `T3 - T2` hoặc thời gian từ T0 đến T3 nếu hệ thống cần tổng thời gian. Ghi rõ định nghĩa trong báo cáo để người khác không so sánh hai đại lượng khác nhau.

## 3. Hai nhánh thử nghiệm: không cache và có cache

Mỗi nhánh phải dùng cùng một artifact ứng dụng và cùng môi trường. Chỉ thay đổi cấu hình AOT mà thí nghiệm muốn đánh giá.

### Nhánh A — Baseline không dùng AOT cache

Ví dụ với JDK 25:

~~~bash
java -XX:AOTMode=off -Xms512m -Xmx2g -jar service.jar
~~~

`-XX:AOTMode=off` yêu cầu JVM không dùng AOT cache. Giữ các tùy chọn heap, GC, system properties, environment variables và cấu hình ứng dụng giống nhánh có cache.

### Nhánh B — Chạy với cache đã tạo

~~~bash
java -XX:AOTCache=service.aot -XX:AOTMode=on -Xms512m -Xmx2g -jar service.jar
~~~

`-XX:AOTMode=on` là chế độ fail-fast: nếu cache không tồn tại hoặc không tương thích, JVM báo lỗi thay vì âm thầm bỏ cache. Chế độ này hữu ích trong benchmark và CI để bảo đảm nhánh B thực sự đang kiểm tra cache. Khi vận hành production, `auto` thường phù hợp hơn nếu ứng dụng phải tiếp tục chạy ngay cả khi cache không được nạp.

### Điều kiện so sánh

| Thành phần | Baseline A | Cached B |
| --- | --- | --- |
| Application JAR | Cùng artifact | Cùng artifact |
| JDK vendor/build | Cùng | Cùng |
| OS/CPU | Cùng máy hoặc nhóm máy tương đương | Cùng |
| Heap/GC | Cùng cấu hình | Cùng cấu hình |
| Environment/config | Cùng | Cùng |
| Dependencies/classpath | Cùng | Cùng |
| Workload và dữ liệu | Cùng | Cùng |
| AOT cache | Tắt | Nạp cache đã xác minh |

Nếu đồng thời thay JDK, GC, heap, framework, container base image hoặc code, bạn không còn đo riêng tác động của AOT cache. Đó có thể là một thí nghiệm nâng cấp hữu ích, nhưng phải đặt tên và thiết kế như một thí nghiệm khác.

**Lưu ý:** `-XX:AOTMode` liên quan đến cách JVM cấu hình AOT class linking. Hãy giữ các tùy chọn JVM liên quan nhất quán và ghi lại toàn bộ command line. Nếu cần tách riêng ảnh hưởng của AOT cache với một tối ưu hóa JVM khác, hãy thiết kế một ma trận thí nghiệm riêng thay vì trộn chúng vào phép so sánh A/B đầu tiên.

## 4. Tạo cache trước, không tính chi phí training vào startup

Quy trình benchmark cần tách thành hai giai đoạn:

1. **Preparation:** build artifact, chạy training, assembly và xác minh cache.
2. **Measurement:** nhiều lần khởi chạy ứng dụng mới, có hoặc không có cache.

Ví dụ tạo cache với Java 25:

~~~bash
java -XX:AOTCacheOutput=service.aot -jar service.jar
~~~

Đây là quy trình gọn của JDK 25 theo JEP 514. Với server, cần để ứng dụng chạy trong lúc workload training được gửi vào, rồi kết thúc recording có kiểm soát để JVM hoàn tất cache. Không dùng một lần chạy chỉ mở server rồi tắt ngay nếu mục tiêu là đánh giá warm-up và method profiles.

Nếu muốn tách training khỏi assembly:

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=service.aotconfig -jar service.jar
~~~

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=service.aotconfig -XX:AOTCache=service.aot -jar service.jar
~~~

Giai đoạn `create` không chạy nghiệp vụ ứng dụng; nó tạo cache từ configuration đã ghi. Dùng quy trình tách riêng khi cần điều phối tài nguyên hoặc pipeline nhiều stage.

**Không tính thời gian training/assembly vào time-to-ready của lần chạy có cache.** Đây là chi phí chuẩn bị artifact, cần báo cáo riêng trong phần chi phí tổng thể.

### Xác minh cache trước khi benchmark

~~~bash
java -XX:AOTCache=service.aot -XX:AOTMode=on -Xlog:aot -jar service.jar
~~~

Chạy smoke test để bảo đảm cache nạp được. Nếu log báo mismatch hoặc cache không được sử dụng, dừng benchmark và sửa điều kiện tương thích. Không ghi kết quả của nhánh B là “có cache” chỉ vì command line có chứa tên file `.aot`.

## 5. Thế nào là một lần chạy độc lập?

Đối với startup benchmark, **một mẫu độc lập là một lần khởi chạy JVM process mới** với ứng dụng bắt đầu từ trạng thái process mới. Không phải một request HTTP, một vòng lặp trong cùng JVM hay một lần gọi method.

~~~text
Run 01: JVM process mới -> readiness -> workload -> shutdown
Run 02: JVM process mới -> readiness -> workload -> shutdown
Run 03: JVM process mới -> readiness -> workload -> shutdown
...
Run N : JVM process mới -> readiness -> workload -> shutdown
~~~

Trong mỗi lần chạy:

- Tạo process JVM mới.
- Dùng cùng artifact và cấu hình của nhánh tương ứng.
- Ghi mốc launch, readiness và các chỉ số tài nguyên.
- Gửi workload theo kịch bản giống nhau nếu đo warm-up.
- Kết thúc process và chờ tài nguyên được giải phóng trước lần tiếp theo.

**Không đo startup nhiều lần trong cùng một JVM** rồi coi các lần lặp là mẫu độc lập. JVM đã tải class, khởi tạo JIT, giữ heap và cache nội bộ; các lần lặp trong cùng process không còn đại diện cho startup mới.

## 6. Phân biệt fresh process, cold start và OS page cache

Một JVM process mới không đồng nghĩa toàn bộ máy tính ở trạng thái lạnh.

| Trạng thái | Ý nghĩa |
| --- | --- |
| Fresh JVM process | Process mới, heap/JIT state của process trước không được tái sử dụng |
| Warm OS page cache | File JAR, thư viện native hoặc cache có thể còn trong RAM của hệ điều hành |
| Cold OS page cache | Các trang file chưa có sẵn trong page cache; có thể phát sinh I/O vật lý |
| Fresh container/pod | Container mới nhưng node và page cache của host có thể vẫn ấm |
| Fresh host/VM | Máy mới hoặc vừa khởi động lại; còn phụ thuộc storage và hạ tầng |

### Hai chế độ đo nên tách riêng

**A. Cold process trên host bình thường**

Mỗi mẫu tạo JVM mới, nhưng không cố xóa page cache hệ điều hành. Đây thường là kịch bản sát với việc restart process hoặc tạo thêm instance trên node đang hoạt động.

**B. Cold host/page-cache**

Đo riêng trên máy/VM được chuẩn bị để giảm ảnh hưởng của cache file hệ điều hành. Cách thực hiện phụ thuộc OS và quyền quản trị; không nên tùy tiện chạy lệnh xóa page cache trên production host. Nếu cần, dùng VM/host thử nghiệm riêng, reboot hoặc quy trình quản trị đã được phê duyệt.

Không trộn hai chế độ trong cùng một tập dữ liệu. Ghi rõ benchmark là “fresh JVM process, host page cache uncontrolled/warm” hay “cold host” để tránh gọi sai tên.

## 7. Chọn workload training đại diện

Cache chỉ có giá trị khi training phản ánh những gì ứng dụng sẽ thực thi ở deployment. JDK 25 có JEP 515 để lưu method execution profiles trong AOT cache; vì vậy workload training không chỉ ảnh hưởng tới class loading mà còn ảnh hưởng tới profile method được ghi nhận.

### Ma trận coverage training

| Loại ứng dụng | Luồng nên có trong training |
| --- | --- |
| REST API | Startup, authentication, endpoint chính, validation, serialization |
| Spring Boot | ApplicationContext, controller/service, repository/client và readiness |
| Batch | Đọc input mẫu, xử lý pipeline, ghi output test |
| Messaging | Khởi tạo listener, deserialize và xử lý message mẫu |
| CLI | Các lệnh thường dùng và nhánh xử lý chính |
| Worker nền | Scheduler/task, queue polling và thao tác dữ liệu đại diện |

Một training chỉ làm startup rồi thoát có thể hữu ích để kiểm tra startup artifacts. Nó không chứng minh method profile phản ánh các luồng nghiệp vụ chưa từng được thực thi.

### Tách training khỏi các lần đo

- Tạo cache một lần từ workload đã xác định.
- Không cập nhật source/dependency giữa lúc tạo cache và đo.
- Dùng cùng cache cho tất cả lần chạy của nhánh B.
- Không chạy training lại giữa chừng trong một tập mẫu.
- Nếu thay workload training, tạo cache mới và bắt đầu một thí nghiệm mới có version.

### Tránh training quá rộng

Test suite lớn có thể tải test framework, mock, assertion library và các class không có trong production. Điều này làm cache phình và thay đổi class loading. Dùng smoke/integration workload có chọn lọc, dữ liệu giả và external services sandbox; tránh phát lại side effects production.

## 8. Xác định workload đo warm-up

Warm-up cần một workload ổn định, giống nhau ở cả hai nhánh.

Một kịch bản đơn giản cho REST API:

1. Chờ readiness đạt.
2. Bắt đầu load generator sau một khoảng chờ cố định.
3. Gửi cùng request mix, concurrency, payload size và tốc độ tải.
4. Ghi latency/throughput theo các cửa sổ thời gian liên tiếp.
5. Xác định thời điểm đạt ngưỡng steady-state đã định trước.
6. Dừng tải, lưu metrics và kết thúc process.

### Định nghĩa steady-state trước khi chạy

Ví dụ một quy ước có thể dùng:

- Throughput đạt ít nhất 95% mục tiêu đã định.
- p95 latency không vượt SLO.
- Điều kiện được duy trì trong ba cửa sổ liên tiếp, mỗi cửa sổ 30 giây.

Đây chỉ là ví dụ. Hệ thống cần chọn tiêu chí dựa trên SLO và loại workload. Với batch, steady-state có thể là tốc độ xử lý records/s; với API, có thể là throughput và latency dưới tải cố định.

### Không nhầm request samples với run samples

Trong một JVM process, 10.000 request có thể tạo ra 10.000 quan sát latency, nhưng chúng chịu chung startup, JIT state, heap state và môi trường của process đó. Chúng **không phải 10.000 mẫu startup độc lập**.

Với warm-up, hãy tính một giá trị time-to-steady-state cho mỗi process run; sau đó so sánh phân phối của các run. Các request trong cùng run giúp mô tả chất lượng phục vụ của run đó, không làm tăng số lần chạy JVM độc lập.

## 9. Số lần lặp: bao nhiêu là đủ?

Không có một con số đúng cho mọi ứng dụng. Số mẫu phụ thuộc độ biến động, đại lượng cần ước lượng, mức cải thiện kỳ vọng và độ rộng khoảng tin cậy chấp nhận được.

Gợi ý thực tế:

| Mục đích | Số lần chạy độc lập mỗi nhánh | Cách diễn giải |
| --- | ---: | --- |
| Smoke/kiểm tra pipeline | 3–5 | Chỉ xác nhận quy trình chạy; chưa đủ kết luận hiệu năng |
| Pilot để ước lượng biến động | 10–15 | Tìm noise, lỗi và ước lượng sơ bộ độ lệch |
| So sánh trung vị có kiểm soát | 30–50 trở lên | Điểm bắt đầu thực dụng, vẫn cần xem độ rộng CI |
| Ước lượng p95 ổn định | Thường 100–200+ | Cần nhiều mẫu hơn; chọn theo precision mong muốn |
| So sánh hạ tầng nhiều vùng/instance | Tùy phân tầng | Cần nhiều mẫu trên từng tầng môi trường |

Các số này là **hướng dẫn lập kế hoạch**, không phải bảo đảm thống kê. Nếu dữ liệu biến động mạnh, ngay cả 50 mẫu cũng có thể chưa đủ. Nếu yêu cầu ra quyết định chặt chẽ, hãy dùng pilot để ước lượng độ lệch và tính số mẫu cần thiết cho hiệu ứng tối thiểu mà nhóm quan tâm.

### Vì sao p95 cần nhiều mẫu?

p95 là phân vị đuôi. Với 20 lần khởi chạy, chỉ có khoảng một quan sát ở 5% đuôi trên; giá trị đó không đủ để ước lượng p95 ổn định. Nếu chỉ có ít mẫu, báo trung vị và khoảng tin cậy, đồng thời ghi rõ p95 là ước lượng sơ bộ.

Không tăng số request trong một JVM để giả vờ tăng sample size của startup. Muốn tăng mẫu startup, phải tăng số process launch độc lập.

## 10. Ngẫu nhiên hóa thứ tự chạy và dùng paired blocks

Nếu chạy toàn bộ baseline trước rồi mới chạy cache, máy có thể nóng dần, hạ tầng cloud thay đổi, node có background jobs hoặc cache file hệ điều hành ấm hơn. Khi đó, kết quả có thể bị lẫn với thứ tự thực nghiệm.

Dùng thiết kế **paired block**:

~~~text
Block 01: A (no cache) -> B (with cache)
Block 02: B (with cache) -> A (no cache)
Block 03: B (with cache) -> A (no cache)
Block 04: A (no cache) -> B (with cache)
...
~~~

Trong mỗi block, hai lần chạy diễn ra gần nhau trong cùng điều kiện; thứ tự A/B được ngẫu nhiên hóa. Cách này giúp giảm ảnh hưởng của drift theo thời gian.

Mỗi lần chạy vẫn là process mới. Pairing chỉ giúp so sánh hai điều kiện gần nhau hơn, không biến các mẫu thành độc lập hoàn toàn về mặt môi trường. Nếu dùng nhiều máy, hãy phân tầng theo host/instance và báo kết quả từng tầng trước khi gộp.

### Những điều cần tránh

- Chạy A song song với B trên cùng host, gây tranh CPU/memory/I/O.
- Chạy nhiều benchmark khác cùng lúc.
- Luôn chạy baseline vào buổi sáng và cached vào buổi chiều.
- Chọn thứ tự sau khi nhìn kết quả.
- Bỏ mẫu chậm mà không có tiêu chí loại trừ định trước.

## 11. Kiểm soát biến môi trường

Để A/B có ý nghĩa, giữ các yếu tố dưới đây cố định hoặc ghi nhận rõ:

| Nhóm | Cần kiểm soát |
| --- | --- |
| JDK | Vendor, exact version/build, architecture |
| JVM | Heap, GC, flags, agents, system properties |
| Application | Artifact checksum, dependencies, classpath order |
| OS/host | Kernel/OS build, CPU model, RAM, storage |
| Container | CPU quota, memory limit, image digest |
| Runtime load | Background process, co-tenancy, CPU throttling |
| Application config | Profile, environment variables, secrets sandbox |
| Dependencies | Database, broker, network endpoint, test data |
| Logging | Log level, appenders, output destination |
| Observability | Agents, JFR settings, tracing/exporter |
| File cache | Warm/cold page-cache policy |
| Workload | Request mix, payload, concurrency, arrival rate |

### JVM flags và agents

Giữ các flags giống nhau giữa A/B, chỉ thay cấu hình AOT cần thử. Các agent thay đổi class loading có thể làm cache không tương thích; xác minh bằng `-XX:AOTMode=on` và log trước khi chạy benchmark. Nếu cần agent trong production, benchmark phải dùng đúng agent đó.

### Không để load generator trở thành bottleneck

Load generator nên chạy ở máy riêng hoặc có đủ tài nguyên. Theo dõi CPU/network của nó. Nếu chính load generator bão hòa, throughput/latency quan sát được không còn phản ánh năng lực ứng dụng.

## 12. Đo startup-to-ready bằng tín hiệu thực

Không nên chỉ lấy timestamp dòng log “Started ...” nếu ứng dụng còn cần đăng ký endpoint, mở kết nối hoặc hoàn tất readiness sau đó. Hãy dùng readiness endpoint hoặc tín hiệu phục vụ thực tế mà production orchestration cũng sử dụng.

Với Spring Boot, có thể dùng readiness health group nếu ứng dụng đã cấu hình Actuator phù hợp. Ví dụ đường dẫn có thể là:

~~~text
/actuator/health/readiness
~~~

Benchmark controller nên:

1. Ghi thời điểm trước khi tạo process.
2. Khởi chạy JVM.
3. Poll readiness endpoint theo chu kỳ cố định.
4. Ghi thời điểm lần đầu readiness đạt trạng thái thành công.
5. Nếu timeout hoặc process thoát, ghi lần chạy là failure; không thay bằng một số startup giả.
6. Gửi workload sau readiness nếu đo warm-up.

Dùng đồng hồ monotonic trong harness, chẳng hạn `System.nanoTime()` hoặc clock monotonic tương đương. Không dùng chênh lệch giữa timestamp wall-clock của hai máy vì clock skew có thể làm sai số.

### Tách timeout và failure

Nếu một lần chạy không đạt readiness trong giới hạn, ghi process state, exit code, thời gian timeout, log lỗi đã làm sạch, nhánh A/B và điều kiện môi trường.

Không bỏ các lần timeout khỏi bảng rồi chỉ tính những lần thành công; tỷ lệ failure là một kết quả hiệu năng/vận hành cần báo cáo riêng.
## 13. Đo warm-up bằng cửa sổ thời gian

Ghi throughput và latency theo các cửa sổ cố định, ví dụ 10 hoặc 30 giây. Một run có thể tạo chuỗi:

~~~text
time since ready | throughput | p95 latency | CPU
0-30s            | ...
30-60s           | ...
60-90s           | ...
90-120s          | ...
...
~~~

Từ chuỗi này, tính thời điểm đầu tiên thỏa tiêu chí steady-state và duy trì qua số cửa sổ liên tiếp đã định trước.

### Ví dụ minh họa

Giả sử tiêu chí là throughput ≥ 950 request/s và p95 ≤ 100 ms trong ba cửa sổ 30 giây liên tiếp.

| Run | Thời điểm đầu tiên đạt 2 điều kiện | Duy trì đủ 3 cửa sổ? | Warm-up time |
| --- | ---: | --- | ---: |
| A-01 | 120 s | Có | 120 s |
| A-02 | 150 s | Có | 150 s |
| B-01 | 60 s | Có | 60 s |
| B-02 | 90 s | Có | 90 s |

Số liệu chỉ để minh họa cách tính. Trong benchmark thật, phải lưu đầy đủ time series và áp dụng cùng tiêu chí cho cả hai nhánh. Không được chọn tiêu chí steady-state sau khi đã xem nhánh nào thắng.

## 14. Phân tích kết quả: median, p95, độ phân tán và CI

Với mỗi nhánh, báo ít nhất:

- Số lần chạy độc lập hợp lệ và số lần failure.
- Median của startup-to-ready.
- p95 nếu có đủ mẫu.
- Median/p95 warm-up time.
- Độ phân tán (IQR hoặc MAD; có thể thêm standard deviation nếu dữ liệu phù hợp).
- Khoảng tin cậy cho chênh lệch hoặc tỷ lệ cải thiện.

### Công thức phần trăm cải thiện

Với metric mà **thấp hơn là tốt hơn** (startup, latency, warm-up):

\[
Improvement(\%) =
\frac{Baseline - Cached}{Baseline} \times 100
\]

Ví dụ minh họa: median time-to-ready baseline 2,4 giây, cached 1,9 giây:

\[
\frac{2.4 - 1.9}{2.4} \times 100 \approx 20.8\%
\]

Nếu cached lớn hơn baseline, kết quả là số âm: cache làm chỉ số đó xấu đi.

Với throughput (cao hơn là tốt hơn), dùng công thức tăng trưởng:

\[
Gain(\%) =
\frac{Cached - Baseline}{Baseline} \times 100
\]

### Ưu tiên so sánh paired differences

Với paired blocks, tính chênh lệch hoặc tỷ lệ B/A trong từng block rồi phân tích phân phối các chênh lệch đó. Có thể dùng bootstrap để ước lượng khoảng tin cậy cho median improvement hoặc median ratio.

Không chỉ nhìn hai median riêng biệt rồi kết luận chắc chắn. Nếu khoảng tin cậy của hiệu ứng rất rộng hoặc chứa cả cải thiện lẫn suy giảm đáng kể, kết luận phù hợp là **chưa đủ bằng chứng** và cần thêm mẫu/kiểm soát nhiễu.

### Không xóa outlier tùy tiện

Một startup chậm có thể do host contention, GC, disk I/O hoặc một lỗi thực tế của cache. Chỉ loại mẫu khi có quy tắc định trước và bằng chứng độc lập, ví dụ host bị mất kết nối hoặc có một tiến trình benchmark khác chạy nhầm. Báo số mẫu bị loại, lý do và kết quả trước/sau khi loại nếu việc loại ảnh hưởng đáng kể.

## 15. Báo cáo startup và warm-up riêng biệt

Bảng kết quả nên tách các metric:

| Metric | Baseline | Cached | Thay đổi | Kết luận |
| --- | ---: | ---: | ---: | --- |
| Startup-to-ready median | ... | ... | ...% | ... |
| Startup-to-ready p95 | ... | ... | ...% | ... |
| Warm-up-to-steady median | ... | ... | ...% | ... |
| Warm-up-to-steady p95 | ... | ... | ...% | ... |
| Steady throughput | ... | ... | ...% | ... |
| Steady p95 latency | ... | ... | ...% | ... |
| RSS peak | ... | ... | ...% | ... |
| CPU during startup | ... | ... | ...% | ... |
| Cache artifact size | — | ... | ... | ... |

Một kết quả có thể là startup giảm 20%, warm-up giảm 30%, nhưng steady-state throughput gần như không đổi. Điều đó vẫn có thể có giá trị nếu dịch vụ scale-out thường xuyên hoặc có thời gian sống ngắn; nếu server chạy nhiều ngày và hiếm restart, lợi ích có thể nhỏ hơn chi phí.

## 16. Theo dõi tài nguyên và chi phí của cache

Không đánh giá AOT cache chỉ bằng giây startup. Cache tạo thêm một artifact và một pipeline chuẩn bị.

Theo dõi:

- Kích thước file `.aot`.
- Thời gian training và assembly.
- CPU/RAM tiêu thụ trong quá trình tạo cache.
- Peak memory khi tiến trình training và assembly chồng lấp.
- Chi phí lưu trữ, phân phối cache tới các node.
- RSS/heap và CPU khi khởi động có cache.
- Tỷ lệ cache load thành công sau deploy.
- Chi phí tái tạo cache mỗi lần build.

Trong quy trình một lệnh `-XX:AOTCacheOutput`, JVM khởi chạy một JVM khác để assembly sau training. Tiến trình assembly có heap riêng; với cấu hình heap lớn, tài nguyên đỉnh có thể xấp xỉ gấp đôi heap training, chưa kể overhead khác. Nếu benchmark trong container giới hạn RAM, hãy kiểm tra memory peak để không nhầm OOM của quy trình tạo cache với hiệu năng ứng dụng.

## 17. Tương thích cache là điều kiện bắt buộc của benchmark hợp lệ

Theo tài liệu Java 25, AOT cache gắn với ứng dụng, JDK release, OS và CPU architecture. Training và deployment cần nhất quán về môi trường, classpath và trạng thái artifact.

Checklist trước mỗi tập đo:

- Cùng JDK release; ghi rõ vendor và build.
- Cùng OS và CPU architecture.
- Cùng application artifact và dependency set.
- Giữ nguyên JAR timestamps giữa training và deployment.
- Classpath là danh sách JAR tương thích, giữ thứ tự; classpath production phải là superset theo yêu cầu của tài liệu AOT.
- Không dùng JVMTI agents thay đổi bootstrap/system class loader theo cách không tương thích.
- Dùng cùng JVM flags liên quan tới class loading và instrumentation.
- Tạo cache mới sau khi rebuild ứng dụng, đổi dependency hoặc nâng JDK.

### Xác minh bằng `AOTMode=on`

~~~bash
java -XX:AOTCache=service.aot -XX:AOTMode=on -Xlog:aot,class+path=info -jar service.jar
~~~

Nếu cache không nạp được, JVM phải báo lỗi ở chế độ `on`. Sửa nguyên nhân trước benchmark. Khi chạy production có thể dùng `auto` để fallback không cache nếu cache không tương thích; nhưng trong benchmark, chế độ strict giúp tránh ghi nhãn nhầm một run không dùng cache thành run cached.

### Lưu ý riêng về GC ở JDK 25

AOT object cache của JDK 25 chưa hỗ trợ ZGC. Nếu ứng dụng đang dùng ZGC, không thiết kế nhánh cached như thể JDK 25 có thể nạp cache trong cấu hình đó. JDK 26 mở rộng AOT object caching cho mọi GC qua JEP 516; khi chuyển JDK, cần tạo cache mới và thiết kế thí nghiệm mới thay vì gộp số liệu giữa hai release.

## 18. Các lỗi thiết kế benchmark thường gặp

| Lỗi | Vì sao làm sai kết quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ chạy mỗi nhánh một lần | Không biết mức biến động | Lặp nhiều process độc lập |
| Gửi nhiều request trong cùng JVM rồi tính là nhiều startup samples | Các request dùng chung JVM state | Mỗi startup sample phải là process mới |
| Chạy hết baseline rồi mới chạy cache | Drift nhiệt độ/host/load | Randomized paired blocks |
| Gọi fresh process là cold machine | OS page cache vẫn có thể ấm | Ghi rõ page-cache condition |
| Tính thời gian tạo cache vào startup | Trộn preparation cost với deployment startup | Báo riêng training/assembly |
| Training chỉ startup nhưng kết luận warm-up | Không có method profiles đại diện | Training workflow nghiệp vụ thực |
| Không xác minh cache load | Nhánh B có thể chạy không cache | Dùng `AOTMode=on` và `-Xlog:aot` |
| Khác heap/GC/CPU limit giữa hai nhánh | Không cô lập được tác động AOT | Giữ cấu hình runtime nhất quán |
| Chạy benchmark song song trên cùng host | Cạnh tranh tài nguyên | Tuần tự hóa run hoặc dùng host riêng |
| Bỏ timeout/failure khỏi báo cáo | Làm kết quả trông tốt giả tạo | Báo tỷ lệ failure và điều kiện loại |
| Chỉ báo trung bình | Outlier kéo lệch kết quả | Median, p95, IQR/MAD, CI |
| Dùng p95 với rất ít mẫu | Đuôi phân phối không ổn định | Tăng mẫu hoặc ghi rõ exploratory |
| Bật JFR/tracing chỉ ở một nhánh | Instrumentation làm thay đổi overhead | Cùng instrumentation hoặc đo riêng |
| Thay code/dependency giữa các run | Cache và artifact không còn tương ứng | Freeze artifact, tạo lại cache khi thay đổi |

## 19. Ví dụ báo cáo kết quả (số liệu giả lập)

Giả sử đã chạy 40 paired blocks, mỗi block có một lần baseline và một lần cached, tổng cộng 80 lần khởi chạy JVM mới. Cùng JDK 25, cùng artifact, cùng máy, cùng heap/GC và cùng workload.

| Metric | Không cache | Có cache | Cải thiện |
| --- | ---: | ---: | ---: |
| Startup-to-ready median | 2,40 s | 1,90 s | 20,8% |
| Startup-to-ready p95 | 3,20 s | 2,50 s | 21,9% |
| Warm-up median | 150 s | 95 s | 36,7% |
| Steady throughput | 1.000 req/s | 1.005 req/s | 0,5% |
| Steady p95 latency | 85 ms | 84 ms | 1,2% |
| Peak RSS | 620 MB | 650 MB | +4,8% |
| Cache artifact | — | 38 MB | — |

**Diễn giải giả lập:**

- Startup và warm-up cải thiện rõ trong workload này.
- Steady-state throughput và latency gần như không đổi; cache chủ yếu giúp giai đoạn đầu.
- Peak RSS tăng nhẹ; cần đánh giá mức tăng này có ảnh hưởng tới container density hay không.
- Chưa thể quyết định production chỉ từ bảng trên: còn phải xem CI time, cache distribution, cache load success, khoảng tin cậy và chi phí tái tạo.

Ví dụ nếu paired bootstrap CI cho median startup improvement là 15–25%, kết quả có độ chắc chắn tốt hơn một con số 20,8% đơn lẻ. Nếu CI rộng từ -5% đến +30%, chưa đủ bằng chứng để tuyên bố cải thiện ổn định.

**Các số liệu trong bảng hoàn toàn minh họa**, không phải benchmark chính thức của Oracle hay dự báo cho ứng dụng cụ thể.

## 20. Ngưỡng chấp nhận và quyết định triển khai

Trước khi chạy, nhóm cần thống nhất ngưỡng:

- Startup-to-ready phải giảm tối thiểu bao nhiêu phần trăm hoặc bao nhiêu mili giây?
- Warm-up có phải SLO quan trọng không?
- Peak RSS được phép tăng tối đa bao nhiêu?
- Cache artifact được phép chiếm bao nhiêu dung lượng?
- Training/assembly được phép tiêu thụ bao nhiêu CPU/RAM và thời gian CI?
- Tỷ lệ cache load thành công tối thiểu là bao nhiêu?
- Có fallback không cache khi deploy lỗi hay không?

Ví dụ policy minh họa:

| Điều kiện | Quyết định |
| --- | --- |
| Startup cải thiện có CI đủ hẹp, warm-up tốt hơn, RSS trong ngân sách | Đề xuất canary |
| Startup cải thiện nhưng cache load failure xuất hiện | Chưa rollout; sửa tương thích |
| Warm-up tốt hơn nhưng startup không đổi, service chạy rất lâu | So sánh lợi ích thực tế với chi phí |
| Startup giảm nhưng RSS vượt giới hạn container | Không chấp thuận trước khi giải quyết memory budget |
| Kết quả không khác biệt rõ | Không thêm cache vào pipeline nếu không có lợi ích khác |
| Số mẫu ít hoặc CI quá rộng | Tiếp tục đo, không kết luận |

Một tiêu chí tốt nên gắn với SLO và business impact, không chọn ngưỡng sau khi đã nhìn thấy số liệu.

## 21. Bài thực hành: benchmark AOT cache cho một dịch vụ Java 25

### Bối cảnh

Bạn có một REST service chạy JDK 25, khởi động trong container và nhận request từ load balancer. Mục tiêu là giảm time-to-ready khi autoscaling, đồng thời không làm tăng RSS vượt giới hạn.

### Nhiệm vụ

1. Ghi JDK vendor/build, OS/CPU, container limits, JVM flags và checksum của application artifact.
2. Tạo workload training có startup và ít nhất hai luồng nghiệp vụ đại diện.
3. Tạo `service.aot` bằng `-XX:AOTCacheOutput`.
4. Xác minh cache bằng `-XX:AOTMode=on` và log AOT.
5. Viết hai command launch giống nhau, một dùng `AOTMode=off`, một dùng cache.
6. Dùng harness bên ngoài tạo process JVM mới cho mỗi lần chạy và đo launch-to-readiness bằng monotonic clock.
7. Pilot 10–15 lần mỗi nhánh để tìm nguồn nhiễu; sau đó chọn sample size chính thức theo độ biến động và metric cần báo cáo.
8. Chạy paired blocks, randomize A/B order, không chạy hai benchmark đồng thời trên cùng host.
9. Trong từng run, gửi cùng workload và đo warm-up-to-steady-state, throughput và p95 latency.
10. Báo median, p95 (nếu đủ mẫu), IQR/MAD, confidence interval và failure rate.
11. Ghi peak RSS, CPU, cache size, training/assembly time và chi phí pipeline.
12. Viết kết luận: đạt ngưỡng hay chưa, giới hạn áp dụng, và điều kiện canary/rollback.

### Mẫu bảng ghi kết quả

| Run | Block | Variant | Process start | Ready time (ms) | Warm-up (s) | Peak RSS (MB) | Failure |
| ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| 1 | 1 | A | ... | ... | ... | ... | ... |
| 2 | 1 | B | ... | ... | ... | ... | ... |
| 3 | 2 | B | ... | ... | ... | ... | ... |
| 4 | 2 | A | ... | ... | ... | ... | ... |

Đây là mẫu bảng; mỗi dòng phải tương ứng một process run mới. Không điền nhiều request cùng process thành nhiều dòng startup.

### Câu hỏi tự đánh giá

1. Fresh JVM process có đồng nghĩa cold OS page cache không?
2. Vì sao một startup sample phải là một process mới?
3. Vì sao cần ngẫu nhiên hóa thứ tự A/B?
4. Tại sao startup-to-ready và warm-up-to-steady là hai metric riêng?
5. Khi nào `AOTMode=on` phù hợp hơn `auto` trong benchmark?
6. Vì sao không tính training/assembly vào startup của deployment run?
7. JEP 515 làm workload training quan trọng như thế nào?
8. Tại sao 20 lần chạy thường chưa đủ để ước lượng p95 đáng tin cậy?
9. Làm thế nào để phân biệt cache không load với cache load nhưng không cải thiện?
10. Nếu warm-up cải thiện nhưng steady-state throughput không đổi, có thể kết luận gì?
11. Vì sao phải ghi RSS và cache artifact size cùng với startup time?
12. JDK 25 có giới hạn gì khi benchmark AOT cache với ZGC?

## 22. Checklist trước khi chấp nhận kết quả benchmark

- [ ] Câu hỏi benchmark và metric chính được định nghĩa trước.
- [ ] Baseline và cached variant dùng cùng artifact, JDK, OS/CPU, heap/GC và workload.
- [ ] Cache được tạo riêng trước phép đo và không tính training/assembly vào startup.
- [ ] Nhánh cache được xác minh bằng `AOTMode=on` và log AOT.
- [ ] Mỗi mẫu startup là một JVM process mới.
- [ ] Phân biệt fresh process với cold OS page cache.
- [ ] Có pilot để ước lượng noise và chọn số mẫu.
- [ ] A/B order được ngẫu nhiên hóa trong paired blocks.
- [ ] Không chạy benchmark song song gây tranh tài nguyên.
- [ ] Readiness và steady-state criteria được xác định trước.
- [ ] Warm-up workload giống nhau ở hai nhánh.
- [ ] Load generator không phải bottleneck.
- [ ] Báo median, p95 khi đủ mẫu, độ phân tán, CI và failure rate.
- [ ] Không loại outlier nếu thiếu tiêu chí và bằng chứng độc lập.
- [ ] Theo dõi CPU, RSS, cache size, training/assembly cost.
- [ ] Cache phù hợp JDK/OS/CPU/artifact/classpath; không dùng cache cũ sau rebuild.
- [ ] Đã xem xét giới hạn GC của JDK mục tiêu.
- [ ] Có ngưỡng chấp nhận, kế hoạch canary và fallback không cache.

**Tiêu chí hoàn thành:** người học có thể thiết kế một phép so sánh AOT cache có và không có cache bằng nhiều lần chạy JVM độc lập, xác nhận cache được nạp, đo riêng startup và warm-up, kiểm soát OS page cache và các yếu tố môi trường, phân tích phân phối số liệu cùng khoảng tin cậy, rồi đưa ra quyết định dựa trên SLO và chi phí thực tế.

## 23. Tài liệu chính thức và hướng dẫn benchmark

- [The java Command — Java SE 25, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, `AOTMode`, điều kiện tương thích và cách xử lý khi cache không nạp được.
- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): kiến trúc và tính nhất quán giữa training với deployment.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): cách tạo cache gọn hơn trong JDK 25.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method profiles được đưa vào AOT cache để hỗ trợ warm-up.
- [Inside Java — Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): quy trình training/assembly, lựa chọn workload, tương thích và xác minh cache.
- [HotSpotAOTCacheMXBean — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html): thông tin quản lý AOT recording và cách kết thúc recording.
- [JDK 26 — Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): thay đổi AOT object caching với JEP 516 khi chuyển sang JDK 26.

Khi áp dụng bài benchmark cho JDK mới hơn Java 25, hãy kiểm tra command options, giới hạn GC và điều kiện cache theo release mục tiêu. Không gộp số liệu của hai JDK release vào một tập so sánh rồi quy toàn bộ chênh lệch cho AOT cache.
