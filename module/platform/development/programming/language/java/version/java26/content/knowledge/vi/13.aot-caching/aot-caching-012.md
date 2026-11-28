# Đo khởi động, làm nóng, dung lượng và hành vi khi không dùng được cache

## 1. Mục tiêu và trạng thái hiện hành

AOT cache (Ahead-of-Time Cache) là tính năng của HotSpot JVM giúp chuyển một phần công việc thường lặp lại ở mỗi lần khởi động sang giai đoạn chuẩn bị trước. JVM có thể lưu thông tin class đã được tải/liên kết, một số đối tượng heap của JDK và dữ liệu profiling của phương thức để lần chạy sau khởi động nhanh hơn và đạt hiệu năng ổn định sớm hơn.

AOT cache phát triển qua nhiều phiên bản:

| JDK | JEP | Thay đổi |
|---|---|---|
| JDK 24 | JEP 483 — Ahead-of-Time Class Loading & Linking | Giới thiệu AOT cache và quy trình training, assembly, production |
| JDK 25 | JEP 514 — Ahead-of-Time Command-Line Ergonomics | Đơn giản hóa việc tạo cache bằng `-XX:AOTCacheOutput` |
| JDK 25 | JEP 515 — Ahead-of-Time Method Profiling | Lưu method execution profiles từ training run để JIT có dữ liệu tối ưu sớm hơn |
| JDK 26 | JEP 516 — Ahead-of-Time Object Caching with Any GC | Bổ sung định dạng object cache độc lập GC, cho phép dùng cả ZGC |
| JDK 27 | Duy trì AOT cache hiện hành | Giữ quy trình và chính sách `AOTMode` của JDK 25/26 |

Tính đến ngày 27/11/2026, JDK 27 là feature release mới hơn đã phát hành. AOT cache là tính năng HotSpot qua các tùy chọn JVM `-XX`, không phải Java language preview hoặc incubator API. Không cần `--enable-preview` hay `--add-modules` để sử dụng.

Các tùy chọn `-XX:AOT...` là tùy chọn triển khai của HotSpot, không phải giao diện Java SE được bảo đảm trên mọi JVM vendor. Kiểm tra tài liệu của runtime thực tế trước khi đưa chúng vào script triển khai.

AOT cache không phải ảnh chụp toàn bộ heap ứng dụng và cũng không phải native executable. JDK 25 bổ sung method profiles vào cache để JIT có thể bắt đầu tối ưu dựa trên hành vi đã quan sát. JIT vẫn tiếp tục biên dịch, thu thập dữ liệu mới và điều chỉnh code khi ứng dụng chạy.

Bài học hướng dẫn cách đo startup/warmup, tạo cache bằng workload đại diện, theo dõi dung lượng và chọn chế độ an toàn khi cache thiếu hoặc không tương thích.

## 2. AOT cache giải quyết công việc nào?

### 2.1. Công việc lặp lại trong mỗi lần khởi động

Khi khởi động ứng dụng Java, JVM thường phải:

1. Tìm và đọc class từ JAR hoặc module.
2. Parse, verify, load và link class.
3. Khởi tạo một số cấu trúc nội bộ và đối tượng nền tảng.
4. Thực thi phương thức để thu thập profile như tần suất gọi, nhánh được chọn và kiểu đối tượng xuất hiện.
5. Dựa vào profile để JIT biên dịch các phương thức nóng thành mã máy tối ưu.

Các bước này tạo ra hai khoảng thời gian cần phân biệt:

- **Startup time:** thời gian từ khi tiến trình bắt đầu đến khi ứng dụng sẵn sàng nhận công việc có ý nghĩa.
- **Warmup time:** thời gian từ lúc ứng dụng sẵn sàng đến khi throughput/latency đạt trạng thái ổn định gần với hiệu năng cao nhất.

AOT cache chuyển một phần công việc tải/liên kết class và thu thập method profile sang training run. Khi production khởi động, JVM có thể tái sử dụng các dữ liệu đã chuẩn bị.

### 2.2. Những gì AOT cache lưu và không lưu

| Nội dung | Vai trò |
|---|---|
| Class đã tải và liên kết | Giảm một phần công việc load/link lặp lại |
| Một số đối tượng heap của JDK | Ví dụ đối tượng `Class` cùng các `String` hoặc byte array được tham chiếu |
| Method execution profiles | Giúp JIT có dữ liệu hành vi từ training run sớm hơn |
| Toàn bộ trạng thái nghiệp vụ của ứng dụng | Không phải mục tiêu của AOT cache |
| Session người dùng, dữ liệu database hoặc request đang xử lý | Không được xem là snapshot để khôi phục |
| Native executable thay thế JVM | Không phải cách AOT cache hoạt động |

Đừng nhầm AOT cache với GraalVM Native Image. Ứng dụng vẫn chạy trên HotSpot JVM và giữ mô hình Java động. Các lớp được tải động hoặc các đường code chưa được training vẫn có thể được JVM xử lý bình thường ở runtime.

### 2.3. AOT cache bổ sung cho CDS

Class Data Sharing (CDS) lưu class metadata theo định dạng tối ưu để JVM dùng lại. AOT cache mở rộng hướng tiếp cận đó bằng việc lưu thêm các dữ liệu cần thiết cho class linking, archived heap objects và method profiles.

| Cơ chế | Lợi ích chính |
|---|---|
| CDS archive | Tái sử dụng class metadata, giảm một phần chi phí tải class |
| AOT cache | Tái sử dụng class/heap artifacts và method profiles để cải thiện startup lẫn warmup |
| JIT runtime | Tiếp tục biên dịch và tối ưu dựa trên hành vi thực tế khi ứng dụng chạy |
| Native Image | Biên dịch ứng dụng theo mô hình deployment khác; không phải AOT cache của HotSpot |

Thông thường nên đánh giá AOT cache trên JDK hiện hành trước khi tự xây dựng quy trình CDS thủ công riêng. Không tắt CDS mặc định chỉ để thử AOT cache nếu chưa có lý do cụ thể.

## 3. Quy trình ba giai đoạn: Training, Assembly, Production

AOT cache có ba giai đoạn logic:

~~~mermaid
flowchart LR
    T["Training run<br/>Chạy workload đại diện"] --> C["AOT configuration<br/>Lưu quan sát và profile"]
    C --> A["Assembly<br/>Tạo file .aot"]
    A --> P["Production run<br/>Nạp cache và chạy ứng dụng"]
    P --> M["Đo startup, warmup, latency"]
~~~

### 3.1. Training

JVM chạy ứng dụng với workload đại diện và ghi nhận:

- Những class được tải và liên kết.
- Những đường khởi động thường dùng.
- Những phương thức thường được gọi và profile thực thi của chúng.
- Các dữ liệu object của JDK có thể lưu vào AOT cache.

Training run cần giống production về hành vi. Nếu chỉ khởi động ứng dụng rồi thoát ngay, cache có thể hỗ trợ class loading nhưng không có đủ profile cho các đường xử lý nóng.

### 3.2. Assembly

JVM đọc file cấu hình AOT và tạo file cache `.aot`. Giai đoạn này không chạy logic ứng dụng. Đây là bước chuẩn bị artifact để đưa vào image hoặc package triển khai.

### 3.3. Production

Production run nạp file `.aot` và tiếp tục chạy ứng dụng bình thường. Nếu cache hợp lệ, JVM có thể tái sử dụng dữ liệu. Nếu cache không dùng được và chế độ là `auto`, ứng dụng tiếp tục chạy mà không hưởng lợi từ cache.

## 4. Tạo cache một lệnh bằng AOTCacheOutput

Từ JDK 25, JEP 514 đơn giản hóa quy trình bằng `-XX:AOTCacheOutput`. Với JDK 27, chế độ mặc định `AOTMode=auto` nhận biết tùy chọn này và thực hiện training cùng assembly.

Ví dụ ứng dụng được đóng gói trong một JAR:

~~~bash
java -XX:AOTCacheOutput=build/app.aot -cp build/app.jar com.example.Main
~~~

Khi ứng dụng kết thúc bình thường, JVM hoàn tất việc tạo cache tại `build/app.aot`. Lần chạy production:

~~~bash
java -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Có thể chỉ định `AOTMode=auto` tường minh để làm rõ ý định:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Không đặt đồng thời `-XX:AOTCache` và `-XX:AOTCacheOutput` trong cùng một invocation; hai tùy chọn này loại trừ nhau.

### 4.1. Khi nào dùng quy trình một lệnh?

Phù hợp khi:

- Ứng dụng có thể chạy training rồi kết thúc bình thường.
- Build agent có đủ CPU và bộ nhớ để chạy training và assembly.
- Workload training có thể được cung cấp qua tham số hoặc script triển khai.
- Muốn quy trình tạo cache đơn giản trong CI.

Cần lưu ý: sau training, JVM khởi chạy một JVM process thứ hai để assembly cache. Process thứ hai dùng heap riêng với kích thước tương ứng cấu hình heap của training run. Vì vậy, môi trường tạo cache có thể cần gần gấp đôi heap đã đặt, cộng thêm native memory và tài nguyên hệ điều hành.

Ví dụ training dùng `-Xmx2g`, build container cần dự trù khoảng 4 GB heap cho hai JVM trong giai đoạn assembly, chưa tính memory ngoài heap. Trên build agent nhỏ, quy trình một lệnh có thể bị OOM hoặc bị container kill.

## 5. Tạo cache theo ba bước để kiểm soát tài nguyên

Với ứng dụng server chạy lâu hoặc build agent hạn chế bộ nhớ, có thể tách riêng training và assembly.

### 5.1. Bước 1: Training và ghi cấu hình

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=build/app.aotconfig -cp build/app.jar com.example.Main
~~~

Ứng dụng chạy theo workload training. Khi tiến trình kết thúc bình thường, JVM hoàn tất file `app.aotconfig`.

### 5.2. Bước 2: Assembly trên máy build phù hợp

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=build/app.aotconfig -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Ở chế độ `create`, JVM đọc file cấu hình và tạo cache. Logic ứng dụng không được thực thi trong giai đoạn assembly.

Có thể chạy assembly trên máy có nhiều CPU/RAM hơn training machine. Tuy nhiên, cache cuối cùng vẫn phải dành cho đúng JDK release, hệ điều hành và kiến trúc CPU của production.

### 5.3. Bước 3: Production

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Dùng cùng JDK release, nền tảng và classpath phù hợp với cache đã tạo.

### 5.4. Vì sao tách ba bước?

| Điều kiện | Một lệnh `AOTCacheOutput` | Ba bước |
|---|---|---|
| CI có đủ memory | Đơn giản, phù hợp | Có thể dư thao tác |
| Container build nhỏ | Có thể thiếu memory khi assembly chạy JVM thứ hai | Có thể training ở môi trường production-like, assembly trên máy lớn |
| Training server lâu dài | Cần xử lý shutdown và assembly sau khi thoát | Có thể tách training khỏi assembly |
| Muốn lưu file `.aotconfig` để kiểm soát | Có thể để JVM dùng file tạm | Chủ động lưu và tái sử dụng cấu hình |

Không dùng training configuration cũ sau khi thay đổi ứng dụng hoặc dependency mà không đánh giá lại tính hợp lệ. Khi build thay đổi, nên tạo lại cả training và cache theo artifact mới.

## 6. Thiết kế training workload có giá trị

### 6.1. Training cần đại diện cho production

AOT cache hiệu quả khi training run tải các class và thực hiện những đường xử lý mà production thực sự dùng.

Ví dụ một API service có các luồng chính:

- Khởi động Spring/ApplicationContext.
- Đọc cấu hình và tạo bean.
- Xác thực request.
- Đọc dữ liệu từ database.
- Serialize/deserialize JSON.
- Gọi dịch vụ phụ trợ.
- Xử lý các endpoint được gọi nhiều nhất.

Nếu training chỉ gọi endpoint health check, profile có thể không bao gồm các phương thức nóng của nghiệp vụ. Khi production nhận traffic thật, JIT vẫn cần thu thập dữ liệu và warmup những đường code đó.

### 6.2. Tránh làm cache phình vì workload không liên quan

Không nên dùng toàn bộ test suite nặng làm training mặc định. Test framework, mocking library và các test hiếm khi chạy ở production có thể làm tăng số class và dữ liệu được ghi vào cache mà không cải thiện đường xử lý thực tế.

Cách tiếp cận phù hợp:

1. Khởi động ứng dụng với cấu hình production-like.
2. Chạy smoke test cho các đường khởi động và endpoint quan trọng.
3. Gửi lượng request đại diện cho traffic thường gặp.
4. Bao phủ các nhánh quan trọng có tác động đến latency/throughput.
5. Kết thúc training một cách graceful để JVM ghi dữ liệu.

Có thể mock external service trong training để tránh tác dụng phụ, nhưng mock phải giữ đường gọi trong ứng dụng gần giống production. Không tải hàng loạt class chỉ để tăng độ phủ nếu các class đó không dùng khi triển khai.

### 6.3. Dùng dữ liệu production-like an toàn

Không nên training trực tiếp bằng dữ liệu thật nếu việc đó có thể gửi email, tạo giao dịch, cập nhật database hoặc gây side effect. Hãy dùng staging, dữ liệu giả lập và external service được mock có kiểm soát.

Mục tiêu là tái hiện đường code và cấu trúc tải, không phải sao chép dữ liệu nghiệp vụ hoặc trạng thái người dùng vào cache.

## 7. Đo startup và warmup đúng cách

Không kết luận AOT cache có lợi chỉ vì log cho biết cache đã được nạp. Cần đo thời gian ứng dụng sẵn sàng và thời gian đạt hiệu năng ổn định.

### 7.1. Các mốc đo cần tách riêng

| Chỉ số | Định nghĩa thực hành |
|---|---|
| Process startup | Từ lúc launcher tạo JVM process đến mốc ứng dụng bắt đầu |
| Ready time | Từ lúc process bắt đầu đến khi health/readiness check thành công |
| First useful request | Thời điểm request nghiệp vụ đầu tiên hoàn thành |
| Warmup time | Thời gian từ ready đến khi throughput/latency đạt vùng ổn định |
| Peak/steady throughput | Số request/transaction hoàn tất mỗi giây sau warmup |
| p50/p95/p99 latency | Độ trễ request ở các phân vị sau khi hệ thống ổn định |
| CPU và memory | CPU trong startup/warmup, RSS, heap và native memory |
| Cache size | Kích thước file `.aot` trên đĩa |

Đối với server, thời gian từ `main()` đến khi gọi `System.out.println("Started")` không nhất thiết bằng readiness của ứng dụng. Nên dùng mốc health endpoint hoặc tín hiệu readiness mà orchestrator đang sử dụng.

### 7.2. Thiết kế phép đo có và không có cache

Chạy hai cấu hình trên cùng một JDK, phần cứng, classpath, JVM options và workload:

Không dùng AOT cache:

~~~bash
java -XX:AOTMode=off -cp build/app.jar com.example.Main
~~~

Dùng AOT cache:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Thực hiện nhiều lần và so sánh median cùng p95/p99 nếu số lần chạy đủ lớn. Không lấy một lần startup duy nhất làm kết luận.

### 7.3. Phân biệt cold start và warm start

- **Cold start:** cache file hoặc dữ liệu chưa nằm trong filesystem page cache; đọc từ storage có thể tạo thêm latency.
- **Warm start:** cache file đã được hệ điều hành đọc trước đó hoặc còn trong page cache; memory-mapped object có thể được truy cập rất nhanh.

Kết quả cold/warm có thể khác nhau rõ rệt. Khi benchmark, ghi rõ cách chuẩn bị page cache và không so sánh một lần cold start với nhiều lần warm start.

Trên JDK 26+, AOT cache có định dạng object GC-specific có thể memory-map trực tiếp; định dạng GC-agnostic/streamable có thể đọc và materialize object trong nền. Streamable format có thể che giấu disk latency tốt hơn trong cold start nhưng cần CPU để stream và tạo object. Hãy đo cả cold lẫn warm start trên storage thực tế.

### 7.4. Đo warmup bằng tải ổn định

Dùng load generator phát tải theo các khoảng thời gian cố định. Ghi throughput và latency theo từng khoảng, ví dụ:

~~~text
Thời gian sau readiness | Throughput | p95 latency
0-10 giây              | ...        | ...
10-20 giây             | ...        | ...
20-30 giây             | ...        | ...
30-60 giây             | ...        | ...
60-120 giây            | ...        | ...
~~~

Warmup được xem là gần ổn định khi throughput và latency không còn thay đổi lớn giữa các khoảng liên tiếp trong cùng điều kiện tải. Không lấy thời điểm CPU đạt 100% hoặc thời điểm request đầu tiên thành công làm đại diện cho peak performance.

### 7.5. Kiểm soát yếu tố gây nhiễu

Giữ nhất quán:

- Cùng JDK vendor, feature release và build.
- Cùng OS, CPU architecture, CPU quota và memory limit.
- Cùng `-Xms`, `-Xmx`, collector và các JVM options.
- Cùng artifact, dependency và thứ tự classpath.
- Cùng cấu hình application, dữ liệu và số lượng request đồng thời.
- Cùng trạng thái filesystem page cache khi đo cold/warm.
- Cùng cách xác định readiness và thời gian warmup.

Đo cả CPU và memory. Cache có thể giảm công việc load/link, nhưng streaming object có thể dùng thêm CPU trong startup. Một cấu hình giảm startup nhưng tăng CPU peak quá mức có thể không phù hợp với container có CPU quota thấp.

## 8. Đo dung lượng và quản lý cache artifact

### 8.1. Cache size không có một con số cố định

Kích thước `.aot` phụ thuộc:

- Số class được tải và link trong training.
- Các đối tượng JDK có thể được lưu.
- Số lượng và nội dung method profiles.
- Cấu hình runtime và định dạng object cache.
- Mức độ training bao phủ đường khởi động và xử lý thực tế.

Không có một giá trị dung lượng chuẩn áp dụng cho mọi ứng dụng. Cache lớn hơn chưa chắc tốt hơn; nó có thể phản ánh training tải quá nhiều class không cần thiết.

### 8.2. Đo file cache trên Windows

Sau khi tạo cache:

~~~powershell
Get-Item .\build\app.aot | Select-Object FullName, Length, LastWriteTime
~~~

Đổi byte sang MiB để dễ theo dõi:

~~~powershell
$item = Get-Item .\build\app.aot
[math]::Round($item.Length / 1MB, 2)
~~~

Có thể đo thêm thời gian tạo cache và tài nguyên build agent:

- Thời gian training run.
- Thời gian assembly.
- Peak RSS của hai JVM trong quy trình một lệnh.
- CPU time trong assembly.
- Kích thước `.aotconfig` nếu dùng quy trình ba bước.
- Kích thước `.aot` được đưa vào image/artifact.

### 8.3. Dung lượng file không bằng heap tăng thêm

Không cộng toàn bộ kích thước file `.aot` vào heap như thể cache là một object graph ứng dụng được nạp hoàn toàn vào heap.

Định dạng GC-specific có thể memory-map các object đã lưu. Định dạng streamable cần tạo object theo cách tương thích GC. Phần class archive, mapped pages, page cache và heap runtime có cách sử dụng memory khác nhau.

Để đánh giá memory footprint, đo đồng thời:

- File size của cache.
- Process RSS.
- Heap committed/used.
- Native memory.
- Container memory.
- Page faults và CPU khi startup nếu có công cụ hệ điều hành hỗ trợ.

### 8.4. Quản lý cache theo build

Cache phải được version hóa cùng artifact ứng dụng. Một cách đặt tên dễ quản lý:

~~~text
artifacts/
  service-1.4.2/
    service.jar
    service.aot
  service-1.4.3/
    service.jar
    service.aot
~~~

Không ghi đè một cache đang được process production sử dụng. Tạo cache mới trong pipeline, kiểm tra tính hợp lệ và chuyển phiên bản triển khai theo cách atomic. Giữ lại cache cũ cùng artifact cũ để có thể rollback đúng cặp.

## 9. Điều kiện tương thích giữa training và production

AOT cache không phải file có thể tùy ý mang từ máy này sang máy khác.

Các điều kiện chính:

| Yếu tố | Yêu cầu |
|---|---|
| Ứng dụng | Cùng application artifact và trạng thái dependency tương ứng |
| JDK | Cùng JDK feature release |
| Hệ điều hành | Cùng loại OS tương thích |
| CPU | Cùng architecture |
| Garbage collector | Nên giữ giống training; chỉ đổi GC khi đã xác nhận cache dùng định dạng GC-agnostic/streamable và kiểm thử trên runtime đích |
| JAR timestamps | Giữ nguyên timestamp của JAR qua training và production |
| Classpath | Training dùng danh sách JAR; không dùng thư mục, wildcard hoặc nested JAR |
| Thứ tự classpath | Production phải giữ classpath training theo cùng thứ tự và có thể thêm phần tử ở cuối |
| JVM options | Tránh option hoặc agent làm biến đổi class theo cách không tương thích |
| Workload | Training phải đại diện cho đường khởi động và các đường code quan trọng trong production |

Nếu thêm, xóa hoặc nâng phiên bản thư viện, đổi JAR, thay JDK, chuyển OS hoặc CPU architecture, hãy tạo lại cache.

### 9.1. Classpath và timestamp

Ví dụ classpath có thể kiểm soát:

~~~bash
java -XX:AOTCacheOutput=build/app.aot -cp "build/app.jar:lib/core.jar:lib/json.jar" com.example.Main
~~~

Trên Windows, dấu phân tách classpath là dấu chấm phẩy:

~~~powershell
java -XX:AOTCacheOutput=build/app.aot -cp "build/app.jar;lib/core.jar;lib/json.jar" com.example.Main
~~~

Không dùng classpath gồm thư mục class đã giải nén, wildcard như `lib/*` hoặc nested JAR nếu muốn cache classpath được hỗ trợ. Với ứng dụng module, dùng modular JAR trên module path theo các giới hạn trong tài liệu JDK.

JAR timestamps cần được giữ nguyên giữa training và production. Pipeline không nên đóng gói lại cùng nội dung JAR nhưng làm thay đổi timestamp sau khi tạo cache.

### 9.2. Classpath production là superset

Production có thể bổ sung một số JAR ở cuối classpath training, nhưng các JAR đã có trong training phải giữ đúng thứ tự. Các phần thêm mới không có dữ liệu cache được tạo từ training; JVM có thể tải chúng theo cách thông thường.

Không đổi thứ tự thư viện hoặc thay một JAR cùng tên bằng phiên bản khác rồi kỳ vọng cache cũ tiếp tục hợp lệ.

### 9.3. Agent và tùy chọn JVM

Một số JVMTI agent hoặc class-file hook có thể biến đổi class khi JVM khởi động. Điều đó làm cache không tương thích hoặc khiến JVM từ chối sử dụng cache.

Ví dụ, các agent gọi `AddToBootstrapClassLoaderSearch` hoặc `AddToSystemClassLoaderSearch` là một trường hợp cần kiểm tra kỹ. Các tùy chọn chẩn đoán, instrumentation hoặc module path không giống training cũng có thể làm giảm mức sử dụng cache.

Khi production có APM/profiling agent, hãy tạo và kiểm tra cache với đúng agent và đúng JVM options dự kiến dùng ở production. Không bỏ agent trong benchmark nếu nó luôn hiện diện trong production.

## 10. JDK 26: AOT cache dùng được với mọi GC

### 10.1. Vấn đề trước JDK 26

Trước JEP 516, một số AOT object caching phụ thuộc định dạng object/reference của garbage collector. Các object được memory-map vào heap theo layout cụ thể nên không thể dùng chung định dạng với mọi GC. Đây là giới hạn khiến phần AOT object cache không hoạt động đầy đủ với ZGC.

### 10.2. JEP 516 bổ sung GC-agnostic object format

JDK 26 bổ sung định dạng object độc lập GC, thường được gọi là streamable format. JVM đọc object từ cache và tạo chúng theo layout mà GC đang dùng thay vì yêu cầu layout trong file phải giống trực tiếp với heap.

Nhờ vậy, AOT cache có thể dùng với các collector, bao gồm ZGC.

| Định dạng | Cách nạp | Đặc điểm |
|---|---|---|
| GC-specific / mappable | Memory-map object theo layout tương thích | Có thể rất nhanh khi cache đã nằm trong filesystem page cache |
| GC-agnostic / streamable | Stream object và materialize trong nền | Dùng được với GC khác nhau; cần CPU cho việc tạo object nhưng có thể che disk latency trong cold start |

JDK chọn định dạng theo heuristic. Tùy chọn `-XX:+AOTStreamableObjects` có thể được dùng trong thử nghiệm nâng cao để yêu cầu streamable format. Không bật tùy chọn này theo thói quen; hãy benchmark cold/warm startup và CPU trên môi trường triển khai trước.

JEP 516 giúp AOT object caching hỗ trợ mọi GC, nhưng không nên mặc định rằng mọi cache đã tạo bằng một cấu hình GC bất kỳ đều có thể đổi sang GC khác mà không kiểm tra. Khi training và production dùng collector khác nhau, xác nhận định dạng object đã lưu là streamable/GC-agnostic, đọc log AOT và thử khởi động bằng đúng collector production trước khi phát hành.

## 11. Xác nhận JVM có thực sự dùng cache

Không chỉ nhìn thấy file `.aot` tồn tại. Cần xác nhận JVM đã nạp và sử dụng cache.

### 11.1. Unified logging

Chạy production với:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -Xlog:aot,class+path=info -cp build/app.jar com.example.Main
~~~

`-Xlog:aot` ghi thông tin liên quan đến AOT cache. `class+path=info` hỗ trợ chẩn đoán classpath và nguồn class.

Nếu cache không được dùng, kiểm tra log để biết có mismatch classpath, JDK, platform hoặc JVM option hay không.

### 11.2. Kiểm tra class loading

Có thể thêm:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -Xlog:class+load=info -cp build/app.jar com.example.Main
~~~

Class được dùng từ archive có thể hiển thị nguồn `shared objects file`. So sánh số class được nạp từ archive và số class phải load thông thường.

Không dùng riêng log class loading để kết luận toàn bộ cache đã có hiệu quả. Cần xem log AOT, thời gian startup và kết quả benchmark.

### 11.3. JFR và hot methods

Có thể dùng Java Flight Recorder để xem class được tải và phương thức thường được gọi trong training:

~~~bash
jfr configure jdk.ClassLoad#enabled=true
~~~

Sau đó chạy ứng dụng với JFR recording theo cấu hình phù hợp và phân tích:

~~~bash
jfr print --events jdk.ClassLoad recording.jfr
jfr view hot-methods recording.jfr
~~~

Nếu các method nóng trong production không xuất hiện trong training, bổ sung workload tương ứng và tạo lại cache.

## 12. Hành vi khi cache không tồn tại hoặc không dùng được

AOT cache là tối ưu hóa hiệu năng. Ứng dụng phải hoạt động đúng ngay cả khi không có cache.

### 12.1. AOTMode=auto — lựa chọn production khuyến nghị

Trong JDK 27, `auto` là chế độ mặc định:

- Nếu có `AOTCacheOutput`, JVM thực hiện training và assembly.
- Nếu cache được chỉ định và có thể nạp, JVM dùng cache.
- Nếu cache không tồn tại, không truy cập được hoặc không tương thích, JVM tiếp tục chạy mà không dùng cache.

Đây là lựa chọn phù hợp cho production khi không kiểm soát hoàn toàn mọi JVM option hoặc agent được thêm vào command line. Cache lỗi không nên làm ứng dụng ngừng hoạt động nếu ứng dụng vẫn có thể chạy bình thường mà không có tối ưu hóa AOT.

Ví dụ:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/app.aot -Xlog:aot -cp build/app.jar com.example.Main
~~~

### 12.2. AOTMode=required — chỉ dùng để fail-fast

`required` yêu cầu JVM phải nạp được cache. Nếu file thiếu hoặc không tương thích, JVM in lỗi và thoát ngay.

~~~bash
java -XX:AOTMode=required -XX:AOTCache=build/app.aot -cp build/app.jar com.example.Main
~~~

Dùng chế độ này trong CI hoặc bước kiểm tra tính tương thích để phát hiện lỗi sớm. Không mặc định dùng trong production nếu việc cache không dùng được không nên làm service mất khả năng khởi động.

Tên `on` là alias của `required` và tài liệu JDK khuyến cáo không dùng vì có thể bị deprecated/xóa trong tương lai. Hãy dùng `required` khi thật sự cần fail-fast.

### 12.3. AOTMode=off — baseline không cache

~~~bash
java -XX:AOTMode=off -cp build/app.jar com.example.Main
~~~

Dùng để tạo baseline benchmark hoặc xác nhận ứng dụng vẫn chạy khi không có AOT cache. Các tùy chọn AOT khác bị bỏ qua trong chế độ này.

### 12.4. Ma trận hành vi

| Tình huống | `auto` | `required` | `off` |
|---|---|---|---|
| Cache hợp lệ | Dùng cache | Dùng cache | Không dùng |
| Cache không tồn tại | Chạy không cache | Báo lỗi và thoát | Chạy không cache |
| Cache sai JDK/OS/CPU | Chạy không cache | Báo lỗi và thoát | Chạy không cache |
| Cache không truy cập được | Chạy không cache | Báo lỗi và thoát | Chạy không cache |
| JVM option/agent không tương thích | Chạy không cache | Báo lỗi và thoát | Chạy không cache |
| Muốn benchmark baseline | Không phù hợp nếu cache được tìm thấy | Không phù hợp | Phù hợp |

Điểm cần nhớ: fallback trong `auto` bảo đảm khả năng chạy mà không có cache, nhưng startup và warmup có thể chậm hơn. Đây là hành vi đúng với một tối ưu hóa tùy chọn.

## 13. Chẩn đoán lỗi cache

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JVM báo không thể load cache | Sai đường dẫn, file thiếu hoặc quyền đọc không đủ | Kiểm tra file và quyền truy cập |
| Cache không tương thích | Khác JDK release, OS, CPU architecture hoặc app artifact | Tạo lại cache trên đúng target |
| Một số class không lấy từ cache | Training không tải class đó hoặc classpath khác | Kiểm tra `-Xlog:aot,class+path=info`, điều chỉnh training |
| Startup không nhanh hơn | Training quá ngắn hoặc cache không được dùng | Xác nhận log AOT và mở rộng workload đại diện |
| Warmup vẫn dài | Method profiles không bao phủ đường xử lý nóng | Chạy các luồng nghiệp vụ quan trọng trong training |
| Build agent bị OOM khi tạo cache | One-step assembly khởi chạy JVM thứ hai với heap riêng | Tách training và assembly, giảm heap training hoặc dùng máy build lớn hơn |
| Cache lớn bất thường | Training tải nhiều class/test framework không cần thiết | Dùng smoke test và workload gọn hơn |
| Cache cũ sau khi nâng thư viện | Artifact hoặc dependency đã đổi | Tạo lại cache cho build mới |
| Dùng ZGC nhưng cache object không phù hợp | Định dạng object cũ/không tương thích | Dùng JDK 26+ và kiểm tra streamable object format |
| Production có APM agent nhưng cache tạo không có agent | JVM option/bytecode transformation khác nhau | Tạo và kiểm tra cache với cấu hình agent tương đương production |

Nếu cache không nạp được trong `auto`, ứng dụng vẫn chạy. Không nên tìm cách bỏ qua lỗi tương thích bằng việc ép JVM dùng cache cũ; hãy tạo cache mới theo đúng JDK, artifact và platform.

## 14. Đánh giá chi phí và lợi ích

### 14.1. Các chi phí phải tính

| Chi phí | Mô tả |
|---|---|
| Training time | Thời gian chạy workload đại diện |
| Assembly time | CPU/RAM để tạo cache từ cấu hình training |
| Build storage | Lưu `.aot` và có thể cả `.aotconfig` |
| Artifact distribution | Đưa cache cùng phiên bản ứng dụng tới production |
| Startup CPU | Streamable format có thể cần CPU để materialize object |
| Cache maintenance | Tạo lại khi app/JDK/platform thay đổi |
| Pipeline complexity | CI phải quản lý training, assembly, versioning và rollback |

### 14.2. Khi AOT cache có lợi

- Ứng dụng khởi động thường xuyên hoặc cần scale-out nhanh.
- Service có nhiều class load/link trong startup.
- Workload có các đường xử lý lặp lại, profile tương đối ổn định.
- Serverless, CLI hoặc worker có thời gian sống ngắn, nơi startup chiếm tỷ trọng đáng kể.
- Muốn giảm thời gian đạt throughput ổn định sau khi process bắt đầu.

### 14.3. Khi lợi ích có thể nhỏ

- Ứng dụng chạy rất lâu và startup chỉ chiếm phần rất nhỏ tổng thời gian.
- Startup chủ yếu chờ database/network/remote service thay vì load/link class.
- Training không mô phỏng được workload thật.
- Ứng dụng có nhiều class được tải động sau khi production bắt đầu.
- Cache không thể sử dụng do classpath hoặc agent thay đổi thường xuyên.
- Chi phí pipeline và phân phối cache lớn hơn lợi ích startup/warmup.

Không có tỷ lệ tăng tốc cố định áp dụng cho mọi ứng dụng. Phải đo trên đúng JDK, CPU, collector, container và workload triển khai.

## 15. Quy trình triển khai AOT cache trong CI/CD

Một pipeline có thể thực hiện:

1. Build ứng dụng và dependency thành artifact bất biến.
2. Chốt JDK release, OS và CPU architecture target.
3. Chạy training với smoke test và workload production-like.
4. Tạo cache bằng `AOTCacheOutput` hoặc quy trình ba bước.
5. Đo kích thước file `.aot` và thời gian assembly.
6. Chạy smoke test với `AOTMode=required` để xác nhận cache tương thích.
7. Chạy benchmark startup/warmup có cache và không cache.
8. Đóng gói cache cùng đúng application artifact.
9. Deploy production với `AOTMode=auto` để giữ fallback.
10. Theo dõi log AOT, startup/readiness, warmup, throughput và latency.
11. Tạo cache mới cho mỗi build/dependency/JDK/platform thay đổi.
12. Rollback cả ứng dụng lẫn cache về cùng phiên bản nếu cần.

Cache cần được quản lý như một build artifact có nguồn gốc rõ ràng. Không tải cache từ nguồn không tin cậy và không cấp quyền ghi cache cho user không cần thiết.

## 16. Checklist đánh giá trước khi bật trong production

- [ ] Dùng JDK release và build giống môi trường production.
- [ ] Training và production chạy cùng OS/CPU architecture.
- [ ] JAR timestamp và thứ tự classpath được giữ nguyên.
- [ ] Classpath chỉ dùng các dạng được AOT hỗ trợ; không có directory/wildcard/nested JAR.
- [ ] Training chạy các đường khởi động và method nóng đại diện.
- [ ] Training không tạo side effect lên dữ liệu production.
- [ ] Đã đo thời gian training, assembly và dung lượng cache.
- [ ] Đã benchmark startup/readiness và warmup với/không cache.
- [ ] Đã xác nhận JVM thực sự nạp cache bằng `-Xlog:aot`.
- [ ] Đã kiểm tra cache với APM/JVMTI agent và JVM options thực tế.
- [ ] Production dùng `AOTMode=auto` để giữ khả năng fallback.
- [ ] Đã kiểm thử tình huống cache thiếu, stale hoặc không tương thích.
- [ ] Cache được version hóa cùng application artifact và có quy trình regenerate.
- [ ] Có kế hoạch rollback đồng bộ ứng dụng và cache.

## 17. Kết luận

AOT cache giúp giảm thời gian khởi động và rút ngắn warmup bằng cách chuẩn bị trước class loading/linking, một số JDK heap objects và method execution profiles.

Các điểm quan trọng:

- Quy trình có ba giai đoạn: training, assembly và production.
- JDK 25 cho phép tạo cache một lệnh bằng `-XX:AOTCacheOutput`; JDK 27 vẫn hỗ trợ.
- JDK 25 bổ sung method profiles để JIT tối ưu sớm hơn; cache không phải native executable thay thế JIT.
- JDK 26 với JEP 516 cho phép object cache hoạt động với mọi GC, bao gồm ZGC, nhờ định dạng GC-agnostic.
- Training phải đại diện cho production và cache phải khớp JDK, OS, CPU, application artifact và classpath.
- Đo startup, readiness, warmup, throughput, latency, CPU, memory và file size thay vì chỉ nhìn thời gian khởi động.
- `AOTMode=auto` là chế độ production an toàn vì JVM tiếp tục chạy không cache khi cache không dùng được.
- `AOTMode=required` phù hợp kiểm tra fail-fast; `AOTMode=off` dùng làm baseline.
- Khi build, dependency, JDK hoặc platform thay đổi, hãy tạo lại cache.

AOT cache là một tối ưu hóa có thể triển khai theo CI/CD. Giá trị thực tế chỉ được xác nhận khi phép đo trên workload production-like cho thấy startup hoặc warmup tốt hơn mà chi phí CPU, memory, dung lượng và vận hành vẫn chấp nhận được.

## Tài liệu tham khảo chính thức

- [JEP 483 — Ahead-of-Time Class Loading & Linking (JDK 24)](https://openjdk.org/jeps/483)
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics (JDK 25)](https://openjdk.org/jeps/514)
- [JEP 515 — Ahead-of-Time Method Profiling (JDK 25)](https://openjdk.org/jeps/515)
- [JEP 516 — Ahead-of-Time Object Caching with Any GC (JDK 26)](https://openjdk.org/jeps/516)
- [The java Command — Java SE 27, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [HotSpotAOTCacheMXBean — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html)
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations — Inside Java](https://inside.java/2026/01/09/run-aot-cache/)
- [JDK 26 Release Notes — Ahead-of-Time Object Caching with Any GC](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

