# Garbage collection metrics

Trong chương **Application metrics** của mô-đun **SPRING_BOOT_OBSERVABILITY**, **garbage collection (GC) metrics** là nhóm chỉ số cho biết Java Virtual Machine (JVM) đang thu hồi bộ nhớ như thế nào và hoạt động đó có thể ảnh hưởng đến độ trễ ứng dụng ra sao. Khi một API Spring Boot đột nhiên tăng P95 hoặc xuất hiện timeout, các chỉ số GC giúp trả lời: *có nhiều đợt GC hơn trước, mỗi đợt dừng lâu hơn, hay heap đang chịu áp lực tăng dần?*

Mô-đun này sử dụng **Micrometer Observation, metrics, logs và distributed tracing** để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế. GC metrics thuộc nhóm **application/runtime metrics**: chúng mô tả tình trạng JVM ở mức tổng hợp. Để xác định một request cụ thể bị chậm vì lý do gì, cần đặt GC metrics cạnh HTTP latency, logs, traces và các chỉ số tài nguyên khác. Một biểu đồ GC bất thường là bằng chứng đáng kiểm tra, chưa tự chứng minh nguyên nhân của mọi request chậm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích GC là gì, phân biệt **allocation**, **promotion**, **heap usage** và **GC pause**.
2. Bật, đọc và xác minh các metrics JVM/GC mà Spring Boot Actuator thường cung cấp qua Micrometer.
3. Nhận biết các meter như `jvm.gc.pause`, `jvm.memory.used` và các metrics allocated/promoted khi JVM và binder hỗ trợ.
4. Viết PromQL để xem **số đợt GC mỗi giây**, **thời gian GC pause tích lũy**, **pause trung bình** và **P95 pause khi có histogram**.
5. Đánh giá GC theo **từng instance** thay vì gộp dữ liệu của nhiều JVM rồi diễn giải sai.
6. Kết hợp GC metrics với logs, tracing, CPU, heap và connection pool để chẩn đoán latency hoặc lỗi.
7. Nhận diện giới hạn do GC collector, JVM version, sampling, tags/cardinality và exporter.

## 2. GC hoạt động ra sao trong một ứng dụng Spring Boot?

Đối tượng Java được cấp phát trong vùng nhớ do JVM quản lý. Khi các đối tượng không còn reachable, garbage collector có thể thu hồi vùng nhớ của chúng. Tùy GC algorithm, một phần công việc được thực hiện đồng thời với application threads, còn một số pha yêu cầu **stop-the-world (STW)**: các luồng ứng dụng bị tạm dừng trong thời gian nhất định.

Trong một dịch vụ Spring Boot xử lý HTTP, pause đủ dài có thể kéo thời gian trả response lên, đặc biệt khi request đang cần chạy trên JVM bị dừng. Nhưng độ trễ cao cũng có nhiều nguyên nhân khác: chờ database, nghẽn connection pool, retry, network, khóa đồng bộ hoặc CPU saturation.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ câu hỏi |
| --- | --- | --- |
| **Heap used** | Dung lượng heap JVM đang sử dụng tại thời điểm đo. | Heap có liên tục tăng sau các chu kỳ GC không? |
| **Heap committed/max** | Dung lượng JVM đã cam kết/có thể dùng theo cấu hình. | Heap đã gần giới hạn thực tế chưa? |
| **Allocation** | Tốc độ cấp phát các đối tượng mới. | Lượng cấp phát có tăng sau deploy không? |
| **Promotion** | Dữ liệu sống được chuyển sang vùng thế hệ già trong các collector có khái niệm này. | Có quá nhiều object tồn tại qua nhiều chu kỳ GC không? |
| **GC count** | Số lần một loại sự kiện GC được quan sát. | Tần suất GC tăng bao nhiêu? |
| **GC pause duration** | Thời gian của các sự kiện GC pause được runtime/binder ghi nhận. | Mỗi pause có dài đến mức ảnh hưởng SLO không? |
| **Live data size** | Ước lượng dữ liệu còn sống sau một số đợt thu gom, nếu collector hỗ trợ. | Tập dữ liệu tồn tại có tăng dần bất thường không? |

**Không đồng nhất allocated bytes với heap used.** Ứng dụng có thể cấp phát rất nhiều object ngắn hạn nhưng heap used vẫn dao động trong khoảng ổn định nhờ GC thu hồi. Ngược lại, heap sau GC tăng liên tục có thể cho thấy working set lớn hơn hoặc retained objects tăng; cần phân tích sâu hơn trước khi kết luận memory leak.

## 3. Spring Boot lấy GC metrics từ đâu?

Ứng dụng Spring Boot có Actuator và Micrometer metrics thường được tích hợp với các JVM meter binders. Các binder JVM có thể sử dụng thông tin quản lý JVM (như MXBeans và GC notifications) để công bố những số đo phù hợp. Các metrics thực sự có mặt phụ thuộc **Java version, garbage collector, Micrometer version, việc bật binder và runtime**.

Một luồng thu thập điển hình:

~~~mermaid
flowchart LR
    JVM["JVM và garbage collector"] --> Binder["Micrometer JVM / GC meter binders"]
    Binder --> Registry["MeterRegistry"]
    Registry --> Actuator["Actuator /metrics"]
    Registry --> Exporter["Prometheus registry /prometheus"]
    Exporter --> Prom["Prometheus scrape"]
    Prom --> Dashboard["Dashboard, alert, truy vấn PromQL"]
    JVM --> GCLogs["GC logs / JFR nếu bật riêng"]
    App["Spring Boot requests"] --> Tracing["Micrometer Observation / tracing"]
    App --> Logs["Application logs"]
    Dashboard --> Correlation["Đối chiếu GC với HTTP latency"]
    GCLogs --> Correlation
    Tracing --> Correlation
    Logs --> Correlation
~~~

Các GC metrics **không nhất thiết phát sinh từ custom `Observation`**. Chúng thường là các meter do JVM binder đăng ký. Vì vậy, dù không tự gọi `Observation.createNotStarted(...)`, ứng dụng vẫn có thể có `jvm.gc.pause` nếu hạ tầng metrics đã được cấu hình và JVM cung cấp dữ liệu phù hợp.

**Điểm cần nhớ:** `MeterRegistry` thu thập số đo. `ObservationRegistry` quản lý vòng đời các hoạt động được quan sát. Tracing bridge/exporter xử lý spans; logging framework xử lý logs. Không phải cứ có GC metrics là đã có tracing hoặc GC logs chi tiết.

## 4. Những tên metric quan trọng

Trong giao diện Actuator, tên meter Micrometer thường dùng dấu chấm. Trong Prometheus, tên được chuyển đổi thành dạng underscore và có thể có hậu tố đơn vị/loại meter.

| Tên meter trong Micrometer/Actuator | Điều đo được | Lưu ý |
| --- | --- | --- |
| `jvm.gc.pause` | Duration và count của các GC pause được phát hiện. | Đây là `Timer`; thường là điểm bắt đầu khi điều tra pause. |
| `jvm.memory.used` | Memory used theo vùng và pool của JVM. | Phân biệt `area=heap` và `area=nonheap`. |
| `jvm.memory.committed` | Memory đã commit theo vùng/pool. | Không đồng nghĩa lượng memory đang sử dụng. |
| `jvm.memory.max` | Giới hạn memory được JVM công bố cho vùng/pool. | Một số vùng có thể báo giới hạn không xác định. |
| `jvm.gc.memory.allocated` | Lượng bytes được ước tính đã cấp phát, nếu binder/collector hỗ trợ. | Là counter có ý nghĩa phụ thuộc cấu trúc vùng nhớ JVM. |
| `jvm.gc.memory.promoted` | Lượng bytes đã được promoted, nếu runtime hỗ trợ. | Không phải mọi GC đều có khái niệm promotion giống nhau. |
| `jvm.gc.live.data.size` | Ước lượng kích thước dữ liệu còn sống sau GC. | Tính sẵn có và cách cập nhật phụ thuộc collector. |
| `jvm.gc.max.data.size` | Thông tin về dung lượng dữ liệu tối đa theo binder/JVM. | Không thay thế toàn bộ chỉ số heap max. |

Các metrics allocated/promoted/live data có thể không xuất hiện trên một JVM cụ thể. Sự vắng mặt của chúng **chưa đủ** để kết luận Spring Boot bị lỗi. Hãy bắt đầu bằng danh sách meter thực tại `/actuator/metrics`.

### GC pause có những tag nào?

`jvm.gc.pause` thường có các tags mô tả sự kiện như `action` và `cause`, tùy runtime và phiên bản instrumentation. Ví dụ, có thể có hành động mô tả việc kết thúc GC và nguyên nhân khiến GC chạy.

Không nên mã hóa cứng một giá trị `action` hay `cause` trong dashboard trước khi nhìn được dữ liệu thực tế: tên và tập giá trị có thể khác giữa G1, ZGC, Shenandoah và các JVM khác. Khi so sánh theo thời gian, cần lưu ý một lần đổi GC algorithm có thể làm thay đổi các tags và loại sự kiện được quan sát.

## 5. Cấu hình Actuator và Prometheus

Ví dụ một ứng dụng **Spring Boot 3.x, Java 17+** dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Spring Boot BOM nên quản lý các phiên bản Micrometer tương thích với phiên bản Spring Boot đang dùng. Đa số trường hợp, không cần đăng ký thủ công một GC binder thứ hai khi auto-configuration đã cung cấp metrics JVM.

Ví dụ `application.yml` cho môi trường thử nghiệm:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Cấu hình này cho phép xem metrics qua Actuator và Prometheus registry khi các điều kiện auto-configuration phù hợp được đáp ứng. **Nó không tự cài đặt hay khởi chạy Prometheus server.** Cần cấu hình Prometheus scrape endpoint và đảm bảo ứng dụng được truy cập qua đúng cổng/path.

Kiểm tra khi ứng dụng chạy:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.gc.pause
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/prometheus
~~~

Thao tác kiểm tra nên theo thứ tự:

1. `/actuator/metrics` có liệt kê meter `jvm.gc.pause` không?
2. `/actuator/metrics/jvm.gc.pause` có các measurements và available tags nào?
3. `/actuator/prometheus` có những chuỗi liên quan `jvm_gc_...` nào?
4. Prometheus target có trạng thái scrape thành công và sử dụng đúng các labels để nhận diện instance hay không?
5. Khi ứng dụng sinh tải, GC pause count và sum có thay đổi như dự đoán không?

Không nên gây áp lực heap lớn trên môi trường production chỉ để “ép” GC xuất hiện. Trong môi trường thử nghiệm riêng, dùng traffic hoặc một chương trình tạo đối tượng có giới hạn để quan sát biến động có kiểm soát.

### Bảo vệ endpoint

`/actuator/metrics` và `/actuator/prometheus` chứa thông tin vận hành của ứng dụng. Chỉ expose cho hệ thống giám sát và người có quyền, sử dụng security/network policy hoặc management port thích hợp. Các endpoint quản trị không nên được công khai tùy tiện trên Internet.

## 6. Đọc biểu đồ GC pause cơ bản

Đối với một `Timer` như `jvm.gc.pause`, Prometheus registry thường xuất count và sum với đơn vị giây, ví dụ:

~~~text
jvm_gc_pause_seconds_count{application="order-api",action="...",cause="..."} 75
jvm_gc_pause_seconds_sum{application="order-api",action="...",cause="..."} 2.84
~~~

Đây là **số liệu minh họa**, không phải kết quả đo từ ứng dụng thật. `count=75` nghĩa là 75 sự kiện pause được meter ghi nhận từ lúc series khởi tạo; `sum=2.84` tương ứng tổng thời lượng 2,84 giây. Không suy ra 75 lần GC đã xảy ra trong phút vừa qua nếu chưa tính mức tăng trong một cửa sổ thời gian.

Giả sử Prometheus có nhãn `job="order-api"` và `instance` định danh một JVM/process. Các ví dụ bên dưới cần chỉnh nhãn theo dữ liệu thực tế.

### 6.1 Tần suất GC pause mỗi giây

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{job="order-api"}[5m])
)
~~~

Đây là số **sự kiện pause được ghi nhận mỗi giây**, trung bình trên cửa sổ năm phút. Nhân 60 nếu muốn ước lượng sự kiện/phút. Một sự kiện pause không nhất thiết tương đương toàn bộ một chu kỳ GC, đặc biệt với collector có nhiều pha. Không gọi metric này là “số full GC” nếu các tags không chứng minh điều đó.

### 6.2 Thời gian GC pause tích lũy trong mỗi giây

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
~~~

Vì tử số có đơn vị giây pause và `rate` chia cho thời gian thực (giây), kết quả có đơn vị **giây pause/giây thời gian thực**. Nếu giá trị xấp xỉ `0.02`, có thể hiểu là khoảng 2% thời gian đo được đang được ghi nhận dưới dạng GC pause trong cửa sổ đó.

Để thể hiện dưới dạng phần trăm:

~~~promql
100 *
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
~~~

Đây là phép ước lượng từ các sự kiện pause mà binder ghi nhận. **Không mặc định đây là phần trăm CPU tiêu thụ bởi toàn bộ GC**, cũng không khẳng định nó đo được mọi pha concurrent của G1/ZGC/Shenandoah.

### 6.3 Thời lượng pause trung bình

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
/
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{job="order-api"}[5m])
)
~~~

Kết quả tính bằng **giây trên một sự kiện pause**. Ví dụ `0.035` tương ứng 35 ms trung bình. Nếu không có GC pause trong cửa sổ, mẫu số có thể bằng không, gây kết quả trống hoặc không xác định. Dashboard/alert cần xử lý trường hợp này.

**Trung bình không thay thế P95/P99.** Một số ít pause rất dài có thể gây timeout dù pause trung bình vẫn thấp. Muốn đo tail latency của GC pause, cần histogram hoặc dữ liệu sự kiện chi tiết phù hợp.

## 7. P95 GC pause và histogram

Có thể cấu hình histogram cho timer `jvm.gc.pause` trong một môi trường đã xác minh Micrometer/registry hỗ trợ:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        jvm.gc.pause: true
~~~

Khi registry thực sự xuất histogram buckets, Prometheus có thể có `jvm_gc_pause_seconds_bucket`. Ví dụ P95:

~~~promql
histogram_quantile(
  0.95,
  sum by (instance, le) (
    rate(jvm_gc_pause_seconds_bucket{job="order-api"}[5m])
  )
)
~~~

Kết quả là **ước lượng P95 duration của những pause được ghi nhận**, không phải P95 HTTP request latency. Cũng không có nghĩa 95% **thời gian chạy ứng dụng** không bị GC ảnh hưởng: mẫu thống kê ở đây là các **GC events**, không phải các HTTP requests.

Nếu `_bucket` không có, truy vấn P95 bên trên sẽ không có kết quả. Bạn cần xác nhận cấu hình histogram đã được áp dụng, runtime có sự kiện và endpoint Prometheus thực sự xuất bucket series.

**Chi phí:** thêm buckets làm tăng số time series theo tổ hợp tags; không nên bật histogram cho mọi meter chỉ vì muốn có P95. Cân nhắc SLO và yêu cầu điều tra thực tế trước khi tăng độ chi tiết.

## 8. Heap, allocation, promotion và live data

GC pause chỉ là một phần câu chuyện. Để biết **tại sao** các đợt GC thay đổi, hãy xem memory và tốc độ cấp phát.

### 8.1 Heap usage

Một số series thường gặp ở Prometheus registry:

~~~text
jvm_memory_used_bytes{area="heap",id="..."} ...
jvm_memory_committed_bytes{area="heap",id="..."} ...
jvm_memory_max_bytes{area="heap",id="..."} ...
~~~

`id` thường biểu diễn tên memory pool, có thể khác giữa các collector. Cần quan sát tên và nhãn thật; đừng giả định mọi JVM đều có `Eden Space`, `Old Gen` hoặc số pool giống nhau.

Để nhìn tổng heap usage của mỗi JVM khi dữ liệu theo pool đầy đủ và phù hợp:

~~~promql
sum by (instance) (
  jvm_memory_used_bytes{job="order-api",area="heap"}
)
~~~

Nếu muốn tính tỉ lệ heap đã dùng so với giới hạn, chỉ dùng các vùng có max hợp lệ và nhất quán; một số pool có giới hạn không xác định. Có thể chọn một metric heap max tổng thể do hệ thống quan sát cung cấp hoặc kiểm tra trước khi chia. **Không cộng bừa các giá trị max=-1** rồi xem đó là dung lượng heap thật.

Heap used thường tạo đường răng cưa: allocation làm tăng memory, GC thu hồi làm giảm. Sau một chu kỳ GC, heap used không nhất thiết quay về cùng mức do working set, cache và behavior của collector thay đổi.

### 8.2 Allocation rate

Nếu binder/collector hỗ trợ meter `jvm.gc.memory.allocated` và exporter đưa ra một counter dạng byte, có thể có chuỗi tương tự:

~~~text
jvm_gc_memory_allocated_bytes_total{job="order-api"} ...
~~~

Ví dụ PromQL **chỉ áp dụng khi tên series thực tế tồn tại**:

~~~promql
sum by (instance) (
  rate(jvm_gc_memory_allocated_bytes_total{job="order-api"}[5m])
)
~~~

Kết quả có đơn vị **bytes/giây**. Allocation rate tăng sau triển khai có thể chỉ ra một đường xử lý tạo nhiều object ngắn hạn hơn trước. Tuy nhiên, cách binder ước tính lượng allocation phụ thuộc JVM/GC, nên số này không phải phép đo tuyệt đối của mọi lần cấp phát object.

### 8.3 Promotion và live data

Metrics promoted bytes hoặc live data size có thể cung cấp thêm tín hiệu về lượng đối tượng sống lâu. Chẳng hạn một release làm tăng cả allocation rate và promoted bytes có thể khiến các pha GC tốn công hơn. Tuy nhiên:

- **Promotion** là khái niệm phụ thuộc GC algorithm; không thể mặc định mọi collector đều báo số liệu giống nhau.
- **Live data size** là số đo tại những thời điểm/pha nhất định, không phải một snapshot hoàn chỉnh mọi đối tượng sống.
- Một mức live data tăng còn có thể do cache ấm lên, tăng traffic hoặc thay đổi working set hợp lệ.

Nếu nghi ngờ memory leak, cần theo dõi tăng trưởng **sau GC** qua thời gian đủ dài, so sánh cùng mức tải và sử dụng thêm heap dump, allocation profiler hoặc Java Flight Recorder ở môi trường phù hợp. Không kết luận leak chỉ từ biểu đồ heap used tăng trong vài phút.

## 9. Collector ảnh hưởng cách đọc dữ liệu

Không có một mô hình metrics duy nhất phản ánh chính xác mọi garbage collector.

| Collector/tình huống | Điều đáng chú ý | Cẩn trọng khi kết luận |
| --- | --- | --- |
| **G1 GC** | Có các pause young/mixed, còn nhiều công việc được làm theo pha. | Pause duration tăng không tự chứng minh full GC. |
| **ZGC/Shenandoah** | Nhiều công việc được thực hiện đồng thời với ứng dụng. | GC CPU work và latency impact không thể suy ra chỉ từ STW pause sum. |
| **JDK/collector thay đổi sau deploy** | Tên pool, cause/action tags và semantics có thể khác. | Dashboard cũ có thể lọc nhầm hoặc bỏ sót series. |
| **Ứng dụng gần heap limit** | GC có thể chạy nhiều hơn, throughput giảm. | Kiểm tra allocation, retained data, container memory và OOM cùng lúc. |
| **GC không có sự kiện trong cửa sổ đo** | Timer không tăng, query rate bằng 0. | Không đồng nghĩa Micrometer bị lỗi. |

JVM có thể có các cấu hình khác nhau giữa môi trường local và production. Khi dashboard báo thay đổi đột ngột sau một lần nâng Java hoặc đổi GC, hãy xác minh lại ý nghĩa meter và tags, không chỉ so sánh đường biểu đồ với phiên bản cũ.

## 10. Liên kết GC metrics với HTTP latency

Để kiểm tra một giả thuyết “GC làm API chậm”, đặt các biểu đồ lên **cùng một time range và cùng instance**:

1. P95/P99 latency của HTTP server route bị ảnh hưởng.
2. Error rate và request throughput.
3. GC pause count, pause sum rate và histogram/P95 pause nếu có.
4. Heap used/committed/max, allocation rate và các tín hiệu promoted/live data có sẵn.
5. CPU process, JVM threads, connection pool, downstream latency và queue length.

Ví dụ mô phỏng:

| Thời điểm | HTTP P95 | GC pause trung bình | GC pause time/giây | CPU process |
| --- | ---: | ---: | ---: | ---: |
| 10:00–10:05 | 180 ms | 15 ms | 0,006 s/s | 32% |
| 10:05–10:10 | 1.100 ms | 210 ms | 0,12 s/s | 78% |
| 10:10–10:15 | 900 ms | 160 ms | 0,09 s/s | 71% |

**Các số liệu trong bảng hoàn toàn giả định.** Chúng cho thấy GC pause và latency cùng tăng, nhưng chưa chứng minh GC là nguyên nhân duy nhất. Có thể traffic/allocations tăng tạo cả áp lực GC lẫn downstream load, hoặc CPU saturation kéo dài các khoảng chờ.

Khi các request có nhiều instance, **không gộp mọi JVM trước khi kiểm tra instance bất thường**. Một JVM có memory pressure riêng có thể làm tail latency tăng, trong khi trung bình toàn cluster vẫn bình thường.

### Phân biệt metric theo thời gian với một trace đơn lẻ

Nếu trace backend hiển thị một HTTP span dài 1.2 giây đúng khoảng thời gian có GC pause 300 ms, điều đó làm giả thuyết GC gây trễ trở nên đáng chú ý. Nhưng một tracing span bao gồm cả chờ thread, scheduler, network và dependency; nó không tự gắn nhãn phần nào do GC pause.

Để củng cố giả thuyết, hãy đối chiếu GC logs/JFR có timestamp phù hợp, nhiều traces bị chậm cùng thời điểm trên đúng instance, và dữ liệu latency/CPU. **Trace ID không nằm sẵn trong từng sự kiện GC toàn JVM**: GC thường là sự kiện runtime ảnh hưởng nhiều thread, không phải span con của một request.

## 11. GC logs và Java Flight Recorder bổ sung điều gì?

Metrics phù hợp cho dashboard và alerts; muốn điều tra chi tiết một lần GC, có thể cần **GC unified logging** hoặc **Java Flight Recorder (JFR)** theo cơ chế JVM cung cấp.

Ví dụ JVM 17 bật GC logging trong môi trường thử nghiệm:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Cần xác định đường ghi file có quyền và đủ dung lượng, chính sách rotation/retention, cũng như ảnh hưởng vận hành. Nếu ứng dụng chạy container, có thể chọn stdout hoặc giải pháp log collection phù hợp thay vì ghi file không được thu thập.

GC logs có thể cho biết pause type, cause, một số memory statistics và timestamp chi tiết hơn. JFR có thể ghi nhiều JVM events phục vụ phân tích latency và allocation. Hãy sử dụng đúng công cụ/phiên bản Java, cân nhắc chi phí lưu trữ và mức tải.

**Lưu ý về thời gian:** dashboard Prometheus dùng timestamp từ quá trình scrape; logs/JFR có timestamp riêng. Đồng bộ đồng hồ, timezone và chuyển đổi uptime khi cần để tránh kết luận nhầm hai sự kiện diễn ra cùng lúc.

### Logs và tracing correlation

Application logs có thể chứa `traceId` và `spanId` nhờ Micrometer Tracing/MDC, cho phép mở trace của request bị lỗi. GC logs thông thường không có ID của request, vì GC thuộc JVM. Đường điều tra là:

~~~text
HTTP latency alert
   -> GC metrics theo instance + time window
   -> GC logs/JFR đúng JVM và thời điểm
   -> application logs có traceId
   -> distributed trace của request liên quan
   -> xác nhận giả thuyết bằng nhiều nguồn dữ liệu
~~~

Đây là cách liên kết **tín hiệu theo thời gian và instance**, không phải biến mỗi GC event thành một span của từng request.

## 12. Sampling, exporter và tag/cardinality

### Sampling của traces không thay đổi cách hiểu GC metrics

GC metrics thường do meter binders đăng ký vào `MeterRegistry`. Nếu tracing chỉ giữ 10% request do sampling, GC metrics **không tự giảm còn 10%**. Một request bị sample out vẫn có thể chịu GC pause; metrics của JVM vẫn tiếp tục tích lũy theo cơ chế ghi đo.

Vì vậy, khi P95 HTTP và GC metrics có dữ liệu nhưng không tìm thấy trace của một request lỗi, hãy kiểm tra tracing sampler, exporter, collector, backend và context propagation. Không quy lỗi cho GC binder chỉ vì không có trace tương ứng.

### Exporter metrics cần hoạt động

Prometheus registry tạo dữ liệu để server Prometheus scrape. Nếu scrape lỗi, dashboard không có điểm mới dù ứng dụng vẫn ghi metrics trong tiến trình. Kiểm tra `/actuator/prometheus`, target status, network, authentication, port và nhãn `job`/`instance`. Nếu ứng dụng restart, counters/timers cũng có thể reset; các hàm PromQL như `rate()` được thiết kế để xử lý counter reset trong điều kiện phù hợp.

### Tags cần số giá trị hữu hạn

Các tag hữu ích có thể gồm collector action/cause, application, environment hoặc instance. Tuy nhiên, đừng thêm `requestId`, `userId`, `orderId`, timestamp hay URL thô vào GC metric tags. GC là hiện tượng **toàn JVM**, không thuộc về một request ID cụ thể; gắn mỗi request ID vào GC metric vừa sai ngữ nghĩa vừa gây cardinality lớn.

Một bộ lọc quá chặt trên `cause` hoặc `action` có thể làm mất dữ liệu sau nâng JVM/collector. Hãy quan sát cardinality thực tế trước khi thêm các chiều mới vào dashboard.

## 13. Runbook điều tra GC-related latency

Khi có cảnh báo tăng độ trễ, có thể theo quy trình sau:

1. **Định vị sự cố:** ghi service, environment, instance/pod, thời điểm, JVM version, GC algorithm và phiên bản deploy.
2. **Xem HTTP metrics:** route/method nào tăng P95/P99 hoặc 5xx? Traffic có tăng không? Một instance hay toàn cụm?
3. **Xem GC metrics:** pause count, pause sum rate, thời lượng trung bình, histogram nếu có. Kiểm tra từng instance.
4. **Xem heap và cấp phát:** heap sau GC có tăng không? Allocation/promotion thay đổi ra sao? Có sát container/JVM memory limit không?
5. **Kiểm tra CPU và tài nguyên khác:** thread count, CPU, queue, connection pool, dependency latency. Tránh bỏ sót bottleneck không liên quan GC.
6. **Đối chiếu GC logs/JFR:** tìm pha GC và sự kiện kéo dài khớp thời gian. Chú ý timestamp và tags/cause khác nhau giữa collectors.
7. **Đối chiếu application logs/traces:** một số request chậm ở cùng instance có khoảng chờ tương ứng không? Có retry, timeout hoặc dependency chậm không?
8. **Thử giả thuyết trong môi trường phù hợp:** đánh giá allocations, object retention, cấu hình heap, cache hoặc workload; không thay đổi GC flags mù quáng.
9. **Xác nhận sau khắc phục:** so sánh độ trễ, error rate, GC pressure và traffic trên một cửa sổ đủ dài; ghi lại thay đổi.
10. **Cập nhật dashboard/alerts:** thêm ngưỡng và ghi chú collector/version, giữ các chỉ số có ý nghĩa điều tra.

Một biện pháp như tăng `-Xmx` có thể giảm áp lực heap trong một số tình huống, nhưng cũng có thể trì hoãn việc nhận diện leak hoặc tăng memory footprint của container. Cần dựa trên bằng chứng thay vì coi tăng heap là phương án mặc định.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/metrics/jvm.gc.pause` chưa có dữ liệu | Chưa có GC event được ghi nhận; binder/config/runtime khác dự đoán. | Kiểm tra danh sách meter, JVM, collector và tạo traffic thử nghiệm có kiểm soát. |
| Metrics tồn tại trong Actuator nhưng không hiện trên Prometheus | Registry/export endpoint hoặc scrape target chưa đúng. | Xem `/actuator/prometheus`, target health, quyền truy cập và labels. |
| GC count tăng nhưng HTTP latency không tăng | Các pause ngắn hoặc không nằm trên đường xử lý request quan trọng. | So sánh pause duration và HTTP latency theo instance/time window. |
| HTTP latency tăng nhưng GC pause không đổi | Nút thắt ở dependency, lock, queue, network hoặc công việc concurrent GC không nằm trong pause metric. | Đối chiếu traces, connection pool, CPU và runtime logs. |
| Pause P95 trống | Chưa có histogram buckets hoặc query sai label. | Kiểm tra `jvm_gc_pause_seconds_bucket` và cấu hình distribution. |
| Query gộp sai hai JVM | Thiếu group by `instance` hoặc job/namespace chưa đúng. | Thêm bộ lọc, kiểm tra nhãn nhận diện process. |
| Allocation/promoted/live data metric không có | Collector hoặc JDK/Micrometer binder không cung cấp. | Xem meter names thật, dùng heap/GC logs/JFR thay thế khi cần. |
| Heap used liên tục tăng | Tăng traffic, cache ấm lên, retained objects hoặc leak. | So sánh sau GC, allocation, working set và heap dump/JFR. |
| Biểu đồ thay đổi sau nâng Java | Collector, pool IDs, tag values hoặc binder semantics thay đổi. | Xác minh metrics/labels mới trước khi so sánh. |
| Có GC metrics nhưng thiếu trace cho request chậm | Sampling, exporter, context propagation hoặc instrumentation. | Kiểm tra tracing pipeline độc lập với metrics JVM. |

## 15. Bài tập tự kiểm tra

### Bài 1: Count và sum có ý nghĩa gì?

Trong năm phút, `jvm_gc_pause_seconds_count` tăng thêm 20 và `jvm_gc_pause_seconds_sum` tăng thêm 1 giây. Duration pause trung bình là bao nhiêu?

**Đáp án:** Khoảng `1 / 20 = 0,05` giây, tức **50 ms cho mỗi pause**. Đây là trung bình; vẫn có thể tồn tại một số pause dài hơn nhiều. Cần histogram, log hoặc JFR để đánh giá phân vị/đợt kéo dài.

### Bài 2: Có phải memory leak?

Heap used tăng từ 40% lên 70% trong mười phút sau deploy, nhưng traffic cũng tăng gấp ba. Có thể khẳng định bị memory leak không?

**Đáp án:** Không. Cần đối chiếu working set, bộ nhớ còn sống sau GC, allocation, cache và xu hướng qua thời gian đủ dài. Heap sau GC liên tục tăng trong điều kiện tải tương đương mới là dấu hiệu đáng điều tra hơn, nhưng vẫn chưa phải bằng chứng duy nhất.

### Bài 3: P95 của GC có giống P95 HTTP không?

Dashboard cho thấy P95 GC pause là 80 ms, còn P95 HTTP request là 800 ms. Có thể suy ra 720 ms còn lại là thời gian database không?

**Đáp án:** Không. Hai phân vị đo **hai tập sự kiện khác nhau**. Không thể trừ chúng để suy ra dependency time. Cần traces, logs, client metrics và thông tin từ hệ thống phụ thuộc.

### Bài 4: Vì sao có metrics nhưng không có trace?

Ứng dụng ghi lại hàng trăm GC pauses trong metrics nhưng chỉ có vài traces HTTP được lưu. Có nghĩa tracing đã mất GC spans không?

**Đáp án:** Không. GC binder thường phát metrics cho sự kiện toàn JVM, không tạo một span riêng cho mỗi GC event trong request trace. Việc trace ít còn có thể do sampling. Muốn điều tra GC chi tiết, dùng GC logs/JFR và liên hệ thời gian với request traces.

### Bài 5: Phân vị theo nhiều instance

Một dashboard tính trung bình P95 GC pause từ ba JVM. Đó có phải P95 pause toàn cụm không?

**Đáp án:** Không. Phân vị không có tính cộng gộp bằng trung bình cộng. Khi cần P95 toàn bộ tập pause và có histogram buckets tương thích, có thể gộp bucket counts/rates phù hợp trước khi dùng `histogram_quantile`. Trong chẩn đoán sự cố, vẫn nên giữ biểu đồ **theo instance** để phát hiện JVM riêng lẻ bất thường.

## 16. Checklist vận hành GC metrics

- [ ] Actuator và registry implementation phù hợp đã được thêm vào ứng dụng Spring Boot.
- [ ] Xác nhận meter names và labels thực ở `/actuator/metrics`, `/actuator/prometheus`.
- [ ] Có Prometheus target scrape hoạt động và bảo vệ các endpoint quản trị.
- [ ] Dashboard có GC pause count, total pause time và các heap memory metrics quan trọng.
- [ ] Bật histogram GC pause có chọn lọc khi cần P95/P99; kiểm tra sự tồn tại của bucket series.
- [ ] Kiểm tra từng JVM/instance; lưu ý thay đổi collector, Java version và tên pool.
- [ ] Allocation, promotion và live data chỉ được dùng khi runtime thực sự hỗ trợ.
- [ ] Không gắn request ID, user ID hoặc dữ liệu nhạy cảm thành nhãn GC metrics.
- [ ] Có thể đối chiếu GC metrics với HTTP latency, CPU, connection pool, logs và traces.
- [ ] Hiểu rằng tracing sampling không thay thế phép đo GC toàn JVM.
- [ ] Có cách bật và thu thập GC logs/JFR khi cần chẩn đoán sâu hơn.
- [ ] Sau thay đổi, so sánh metrics ở cùng workload hoặc có điều chỉnh theo traffic.

**Ghi nhớ:** **Garbage collection metrics** cho thấy sức khỏe quản lý bộ nhớ và các khoảng pause được JVM ghi nhận, nhưng chỉ là một phần bức tranh về độ trễ Spring Boot. Hãy bắt đầu từ `jvm.gc.pause` và `jvm.memory.used`, mở rộng sang allocation/promotion khi có dữ liệu, đối chiếu cùng instance và thời gian với HTTP metrics, logs, traces; sau đó dùng GC logs hoặc JFR để kiểm chứng nguyên nhân trước khi tối ưu cấu hình JVM.
