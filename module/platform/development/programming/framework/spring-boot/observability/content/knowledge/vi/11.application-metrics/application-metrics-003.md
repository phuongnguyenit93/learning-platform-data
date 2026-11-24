# JVM memory metrics: đo, đọc và điều tra bộ nhớ trong Spring Boot

> **Chương:** Application metrics  
> **Bài:** JVM memory metrics  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần theo dõi bộ nhớ JVM?

Một dịch vụ Spring Boot đôi khi chạy ổn trong nhiều giờ rồi đột ngột chậm, phát sinh nhiều đợt garbage collection (GC) hoặc bị hệ điều hành/container dừng vì thiếu bộ nhớ. Nếu chỉ theo dõi thời gian phản hồi của API, ta biết có sự cố nhưng chưa biết đó là áp lực heap, Metaspace, bộ nhớ trực tiếp (*direct buffer*) hay giới hạn bộ nhớ của container.

**JVM memory metrics** là các phép đo định lượng giúp quan sát trạng thái và xu hướng sử dụng bộ nhớ của tiến trình Java. Khi sử dụng **Spring Boot Actuator và Micrometer**, ứng dụng có thể cung cấp các meter như `jvm.memory.used`, `jvm.memory.committed` và `jvm.memory.max` mà không cần tự instrument từng lần cấp phát.

Các câu hỏi cần trả lời gồm:

- Heap đang dùng bao nhiêu byte? Có sát ngân sách heap cấu hình hay không?
- Mức dùng bộ nhớ giảm sau GC hay liên tục tăng qua nhiều chu kỳ?
- Pool nào đang chịu áp lực: Eden, Old Generation, Metaspace hay Code Cache?
- Tốc độ cấp phát và áp lực GC có liên hệ với p95 latency, lỗi 5xx hoặc timeout không?
- Heap có vẻ bình thường nhưng container vẫn bị OOMKilled: bộ nhớ còn nằm ở đâu?

Trong hệ thống observability:

| Tín hiệu | Vai trò khi điều tra bộ nhớ |
| --- | --- |
| **Metrics** | Phát hiện xu hướng, tỷ lệ dùng heap, phân bố pool, tốc độ cấp phát, thời gian dừng GC |
| **Logs** | Tìm `OutOfMemoryError`, GC logs, exception và sự kiện triển khai |
| **Traces** | Xác định endpoint, batch hoặc downstream path trùng thời điểm độ trễ tăng |
| **Thông tin runtime/container** | Đối chiếu giới hạn RAM, resident memory, OOMKill và hành vi bộ cấp phát native |

Mục tiêu bài học là biết **đọc đúng ngữ nghĩa và đơn vị**, xây dashboard/alert hữu ích, rồi kết hợp các tín hiệu để điều tra. Một biểu đồ heap cao không đủ để kết luận có memory leak.

## 2. Bản đồ bộ nhớ JVM: heap, non-heap và native

JVM quản lý nhiều vùng bộ nhớ; phần nào đo được phụ thuộc JVM, garbage collector, hệ điều hành và thư viện đi kèm.

~~~mermaid
flowchart TD
    A["Bộ nhớ tiến trình Java"] --> B["Heap do JVM quản lý"]
    A --> C["Non-heap do JVM quản lý"]
    A --> D["Bộ nhớ native / ngoài heap"]
    B --> E["Young generation: Eden, Survivor (tùy GC)"]
    B --> F["Old generation / vùng tồn tại lâu (tùy GC)"]
    C --> G["Metaspace, class metadata"]
    C --> H["Code Cache, các pool khác"]
    D --> I["Direct buffers / mmap"]
    D --> J["Thread stacks, thư viện native, cấu trúc GC/JIT"]
~~~

### 2.1. Heap

**Heap** chứa phần lớn các object Java được tạo trong quá trình chạy. Nó chịu sự quản lý của garbage collector. Chẳng hạn, khi API tải một danh sách bản ghi, nhiều object tạm có thể được cấp phát rồi thu hồi nhanh; heap used sẽ tăng và giảm theo chu kỳ GC.

Với collector phân thế hệ, thường có các pool như Eden, Survivor và Old. Tuy nhiên, **tên pool cụ thể không được chuẩn hóa cho mọi JVM/GC**. Với G1 bạn có thể thấy các ID như `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen`; collector khác có thể dùng tên và tổ chức khác.

### 2.2. Non-heap

**Non-heap** gồm nhiều vùng do JVM quản lý ngoài Java heap, chẳng hạn Metaspace và Code Cache. Việc tải quá nhiều class, tạo class động hoặc rò rỉ classloader có thể làm Metaspace tăng. Code Cache liên quan đến mã đã được JIT biên dịch. Các vùng này có giới hạn và cách cấp phát khác heap.

### 2.3. Native và bộ nhớ của container

Một tiến trình Java còn dùng bộ nhớ ở ngoài các JVM memory pools: direct byte buffers, thread stacks, bộ nhớ native của JVM/GC, thư viện JNI, các mapping và thành phần hệ điều hành khác. **Tổng `jvm.memory.used` không tương đương resident set size (RSS), cũng không bằng mức dùng memory của container.**

Ví dụ, `-Xmx1g` chỉ giới hạn **Java heap tối đa** khoảng 1 GiB; tiến trình vẫn có thể tiêu thụ nhiều hơn 1 GiB vì non-heap/native. Vì thế cấu hình container memory limit quá sát `-Xmx` có thể khiến container bị OOMKill dù biểu đồ heap chưa đạt 100%.

## 3. Phân biệt used, committed và max

Micrometer lấy thông tin các memory pool từ các API quản lý của JVM rồi biểu diễn thành các meter. Ba đại lượng cốt lõi:

| Metric Micrometer | Ý nghĩa | Cách hiểu |
| --- | --- | --- |
| `jvm.memory.used` | Số byte đang dùng trong một memory pool tại thời điểm đọc | Bộ nhớ đang chứa dữ liệu theo định nghĩa của JVM |
| `jvm.memory.committed` | Số byte JVM đã cam kết dành cho pool | Lượng bộ nhớ JVM đã bảo đảm có thể sử dụng cho pool |
| `jvm.memory.max` | Mức tối đa JVM công bố cho pool, nếu xác định được | Ngân sách/gới hạn của pool, không phải lượng dùng hiện tại |

Trong các tình huống thông thường: `used ≤ committed` và `committed ≤ max` **khi max là giới hạn hữu hạn và dữ liệu nhất quán**. Tuy nhiên, một số memory pool báo **max không xác định** (ví dụ giá trị `-1`), một số collector có logic pool động, vì vậy không nên mặc nhiên lấy max của mọi pool làm mẫu số hợp lệ.

~~~text
Ví dụ một heap pool tại thời điểm T:
  used       = 600 MiB
  committed  = 768 MiB
  max        = 1024 MiB

  Used/committed = 78,125%
  Used/max       = 58,594%
~~~

Hai tỷ lệ trả lời hai câu hỏi khác nhau:

- **Used/committed:** pool đang sử dụng bao nhiêu phần tài nguyên đã cam kết.
- **Used/max:** pool đang chiếm bao nhiêu phần **giới hạn công bố**.

Ngay cả tỷ lệ `used/max` cao cũng chưa chứng minh memory leak: GC có thể chưa chạy, heap có thể cố ý chứa cache hoặc collector đang tối ưu để hạn chế thu gom. Cần so sánh **xu hướng sau GC**, allocation rate, GC pause, mức tải và hành vi ứng dụng.

### 3.1. Đơn vị byte và cách quy đổi

Các metric bộ nhớ thường dùng đơn vị **byte**. Khi hiển thị:

~~~text
MiB = bytes / 1024 / 1024
GiB = bytes / 1024 / 1024 / 1024
~~~

Đừng nhầm `MB` (thập phân, 10^6 byte) với `MiB` (nhị phân, 2^20 byte). Trong dashboard, phải chọn và ghi rõ đơn vị để đối chiếu chính xác với giới hạn `-Xmx` và container.

## 4. Những JVM memory metrics thường gặp

Bảng dưới phân biệt metric lõi, metric lân cận và tính khả dụng. Tên trước cột xuất sang Prometheus là **tên theo Micrometer**, tùy phiên bản có thể không xuất hiện trong mọi ứng dụng.

| Meter | Dữ liệu | Cần lưu ý |
| --- | --- | --- |
| `jvm.memory.used` | Gauge byte đang dùng theo `area` và `id` | Heap/nonheap, nhiều pool |
| `jvm.memory.committed` | Gauge byte đã commit theo pool | Không đồng nghĩa mức dùng vật lý của container |
| `jvm.memory.max` | Gauge giới hạn pool khi JVM báo được | Có thể không xác định hoặc không hữu ích ở một số pool |
| `jvm.buffer.memory.used` | Bộ nhớ các buffer pool, ví dụ direct/mapped | Bổ sung góc nhìn ngoài Java heap |
| `jvm.buffer.count` | Số buffer theo loại | Không phải số object Java trong heap |
| `jvm.buffer.total.capacity` | Tổng dung lượng buffer | Không đồng nghĩa resident memory |
| `jvm.gc.memory.allocated` | Số byte đã cấp phát, thường biểu diễn như FunctionCounter | Dùng tốc độ tăng để xem allocation pressure khi meter có sẵn |
| `jvm.gc.memory.promoted` | Số byte được promote lên old generation khi hỗ trợ | Phụ thuộc GC/JVM |
| `jvm.gc.pause` | Timer các đợt dừng GC | Dùng count/sum hoặc histogram tùy registry |
| `jvm.gc.live.data.size` | Ước lượng kích thước dữ liệu còn sống sau GC khi hỗ trợ | Không có trong mọi GC/version |

Các nhãn thường gặp:

- `area=heap` hoặc `area=nonheap` giúp phân biệt loại vùng nhớ.
- `id` thường là tên **memory pool do JVM cung cấp**, ví dụ `G1 Old Gen` hay `Metaspace`.
- Với buffer metrics, nhãn có thể dùng `id=direct` hoặc `id=mapped`.
- `application` có thể là common tag do ứng dụng cấu hình, còn `instance` thường là label gắn từ Prometheus scrape target chứ không nhất thiết do ứng dụng tự gắn.

**Không nên lập quy tắc cảnh báo dựa trên một tên series chưa thấy ở exporter thật.** Sau khi biết phiên bản Spring Boot/Micrometer, kiểm tra `/actuator/metrics` và `/actuator/prometheus` để xác nhận meter, labels và đơn vị.

## 5. Spring Boot thu thập JVM memory metrics như thế nào?

Spring Boot Actuator tích hợp Micrometer `MeterRegistry`. Khi các auto-configuration phù hợp hoạt động, Micrometer cung cấp `JvmMemoryMetrics` và những binder liên quan để đăng ký các gauges JVM vào registry.

~~~mermaid
flowchart LR
    A["JVM MemoryMXBean / MemoryPoolMXBean"] --> B["Micrometer JVM binders"]
    B --> C["MeterRegistry của Spring Boot"]
    C --> D["Actuator /actuator/metrics"]
    C --> E["PrometheusMeterRegistry"]
    E --> F["/actuator/prometheus"]
    F --> G["Prometheus scrape định kỳ"]
    G --> H["Grafana dashboard / alert"]
    H --> I["Đối chiếu logs, traces và số liệu container"]
~~~

Đường dữ liệu này có các đặc điểm:

1. **Gauge** đọc trạng thái bộ nhớ tại thời điểm thu thập; nó không đếm từng lần `new` object.
2. Micrometer sử dụng **binder** để đưa thông tin runtime vào MeterRegistry. Thông thường không cần viết custom code đo heap thủ công.
3. `/actuator/metrics` cho phép tra cứu meter và tags ở mức Micrometer; đây không phải endpoint scrape Prometheus.
4. `/actuator/prometheus` xuất metric theo định dạng Prometheus nếu có registry Prometheus và endpoint được expose.
5. Prometheus lấy mẫu theo **scrape interval**. Một đỉnh sử dụng heap ngắn hơn khoảng scrape có thể bị bỏ lỡ; GC giữa hai lần scrape cũng có thể làm biểu đồ trông phẳng hơn thực tế.

**Lưu ý về Observation:** `ObservationRegistry` điều phối observation cho nghiệp vụ, HTTP server hoặc client; `MeterRegistry` là nơi lưu meters. JVM memory gauges thường được đăng ký qua binder thay vì tạo `Observation` cho từng phép đo. Không nên tạo một Observation cho mỗi lần đọc heap chỉ để có metric JVM.

## 6. Cấu hình dự án Spring Boot

Ví dụ dưới dùng cấu hình phổ biến của **Spring Boot 3.x**. Các dự án đang ở phiên bản khác cần đối chiếu namespace property, dependency và đầu ra exporter thực tế.

### 6.1. Maven dependencies

Khi dự án dùng Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Actuator cung cấp cơ sở instrumentation/management. Registry Prometheus cần khi muốn scrape định dạng Prometheus; chỉ có Actuator không đồng nghĩa đã có `/actuator/prometheus`.

### 6.2. Cấu hình `application.yml`

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
~~~

Với cấu hình này:

- `/actuator/metrics` giúp tìm metric như `jvm.memory.used`.
- `/actuator/prometheus` phục vụ scrape nếu có `micrometer-registry-prometheus`.
- Common tag `application=order-service` giúp phân biệt dịch vụ trên backend.

Ở production, nên giới hạn network và quyền truy cập các endpoint quản trị. Không cần expose công khai toàn bộ Actuator để Prometheus hoạt động.

### 6.3. Kịch bản chạy thử

1. Khởi động ứng dụng, tạo traffic nhẹ và để JVM tải những class cần thiết.
2. Gọi `/actuator/metrics` để kiểm tra danh sách meter có `jvm.memory.used`.
3. Gọi metric chi tiết để xem `measurements`, `availableTags`.
4. Quan sát đầu ra Prometheus và đối chiếu tên series có hậu tố `_bytes`.
5. Khi đã xác nhận dữ liệu, mới viết dashboard/alert dựa trên tên và labels thực tế.

Không cần cố ý gây `OutOfMemoryError` để học các phép đo cơ bản. Một endpoint hoặc job cấp phát object ở mức có kiểm soát trong môi trường test là đủ để quan sát xu hướng.

## 7. Đọc dữ liệu ở Actuator

Ví dụ ứng dụng chạy tại `localhost:8080`:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:nonheap"
curl http://localhost:8080/actuator/prometheus
~~~

Một kết quả `/actuator/metrics/jvm.memory.used` có thể chứa thông tin tương tự:

~~~json
{
  "name": "jvm.memory.used",
  "measurements": [
    { "statistic": "VALUE", "value": 315621376.0 }
  ],
  "availableTags": [
    { "tag": "area", "values": ["heap", "nonheap"] },
    { "tag": "id", "values": ["G1 Eden Space", "G1 Old Gen", "Metaspace"] }
  ]
}
~~~

Đây là **JSON minh họa**, không phải output cố định. Những pool hiển thị phụ thuộc JVM và GC; `measurements` của nhiều series có thể được Actuator tổng hợp theo filter được cung cấp. Vì vậy:

- Khi muốn biết **heap used**, lọc bằng `tag=area:heap`.
- Khi muốn biết pool cụ thể, có thể kết hợp thêm `tag=id:<tên-pool>` bằng query string được URL-encode đúng.
- Với tỷ lệ heap, cần đọc bộ nhớ **used** và giới hạn **max** cùng phạm vi/nhãn. Không được lấy `used` của một pool chia cho `max` của một pool khác.

Nếu `jvm.memory.used` không xuất hiện, hãy kiểm tra Actuator dependency, endpoint exposure, binder JVM có được kích hoạt hay không và có cấu hình tắt meter không. Không nên tạo một gauge bằng tay trước khi xác định lý do auto-configuration chưa có.

## 8. Đọc chuỗi Prometheus và đơn vị

Với registry Prometheus, các meter Micrometer thường được đổi tên sang dạng `snake_case` và gắn đơn vị byte trong tên:

~~~text
# Ví dụ minh họa, tên pool và giá trị chỉ mang tính ví dụ
jvm_memory_used_bytes{area="heap",id="G1 Eden Space",application="order-service"} 1.6777216E8
jvm_memory_used_bytes{area="heap",id="G1 Old Gen",application="order-service"} 2.097152E8
jvm_memory_committed_bytes{area="heap",id="G1 Old Gen",application="order-service"} 4.194304E8
jvm_memory_max_bytes{area="heap",id="G1 Old Gen",application="order-service"} 1.073741824E9
~~~

Các đại lượng trên là **gauge**, không phải counter. Giá trị có thể tăng hoặc giảm giữa những lần scrape. Đặc biệt, heap used thường giảm sau GC.

Những lưu ý khi đọc một series:

- `area="heap"`: pool thuộc vùng Java heap.
- `id="G1 Old Gen"`: pool của collector G1 trên một JVM phù hợp. Dùng tên pool từ dữ liệu thực, không hardcode nếu cần chạy trên nhiều collector.
- `application="order-service"`: common tag ví dụ của Spring Boot.
- `instance`: thường xuất hiện khi Prometheus gắn metadata cho target được scrape.
- `_bytes`: giá trị theo byte; khi hiển thị MiB chia 1.048.576.

**Một điểm thực tế:** JVM có thể không báo `max` cho mọi pool. Giá trị không xác định có thể được exporter biểu diễn bằng giá trị âm hoặc không có series hữu ích. Vì vậy phải lọc hoặc loại các mẫu số không hợp lệ khi tính tỷ lệ.

## 9. PromQL: từ mức dùng đến tỷ lệ heap

Những truy vấn sau giả định series trên đã được xác minh ở `/actuator/prometheus` và Prometheus có label `application`/`instance` phù hợp.

### 9.1. Tổng heap used theo instance, đơn vị MiB

~~~promql
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
) / 1024 / 1024
~~~

Các memory pools thuộc heap được cộng lại cho cùng một target. Đây là tổng **heap used** được đo theo pools, không phải resident memory của tiến trình.

### 9.2. Tổng non-heap used theo instance, đơn vị MiB

~~~promql
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="nonheap"
  }
) / 1024 / 1024
~~~

Non-heap used giúp quan sát Metaspace/Code Cache, nhưng cũng **không bao gồm toàn bộ native memory**.

### 9.3. Heap committed và heap max

~~~promql
sum by (application, instance) (
  jvm_memory_committed_bytes{
    application="order-service",
    area="heap"
  }
)
~~~

Ở nhiều collector, phép cộng `jvm_memory_max_bytes` theo mọi pool **không luôn cho giới hạn heap đúng**: pool có thể báo `max=-1` hoặc cùng phản ánh giới hạn theo những cách khác nhau. Trước khi tính %heap, cần xem các pools và xác định mẫu số đáng tin cậy từ JVM đang chạy.

Nếu cấu hình JVM/G1 của ứng dụng thực tế cho thấy **`G1 Old Gen` báo một max hợp lệ đại diện cho giới hạn heap** thì truy vấn minh họa theo collector cụ thể là:

~~~promql
100 *
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
)
/
max by (application, instance) (
  jvm_memory_max_bytes{
    application="order-service",
    area="heap",
    id="G1 Old Gen"
  } > 0
)
~~~

**Đây không phải truy vấn đa collector phổ quát.** Với ZGC, Shenandoah, Parallel GC hoặc triển khai khác, phải đối chiếu pool có max hợp lệ, hoặc dùng một phép đo tổng heap max được cấu hình riêng và kiểm chứng với `MemoryMXBean`/`-Xmx`. Nếu mẫu số thiếu, kết quả có thể không có dữ liệu; không nên thay giá trị bằng 0% rồi cho rằng heap an toàn.

### 9.4. Xem pool nào tăng

~~~promql
topk(
  5,
  jvm_memory_used_bytes{
    application="order-service"
  }
)
~~~

Đây là top 5 series theo byte đang dùng, có thể từ nhiều instance và cả heap/nonheap. Khi cần so sánh **các pool của một instance**, thêm bộ lọc `instance="..."` theo label thực; khi cần chỉ heap, thêm `area="heap"`.

Không áp dụng `rate(jvm_memory_used_bytes[5m])` như thể đây là counter cấp phát: `used` có thể giảm sau GC, nên tốc độ chênh lệch giữa hai lần đọc không tương đương allocation rate.

## 10. GC metrics: hiểu chuyển động của heap

Heap memory metrics chỉ cho thấy **trạng thái**. Để biết vì sao heap tăng hoặc latency cao, cần thêm dữ liệu về thu gom rác:

| Nhóm đo | Câu hỏi | Gợi ý diễn giải |
| --- | --- | --- |
| Allocation | JVM cấp phát object nhanh đến mức nào? | Tăng bất thường có thể do xử lý dữ liệu nặng hoặc lỗi tạo object |
| Promotion | Bao nhiêu byte sống đủ lâu để chuyển lên old generation? | Promotion cao có thể làm old gen chịu áp lực |
| GC pause | Tổng thời gian và tần suất dừng ứng dụng vì GC ra sao? | Pause dài/tăng tần suất có thể liên quan latency |
| Live data sau GC | Lượng dữ liệu còn sống sau các lần GC phù hợp có tăng? | Dấu hiệu cần điều tra khi tăng bền vững, không tự chứng minh leak |

Khi meter `jvm.gc.memory.allocated` được cung cấp dưới dạng counter sau khi xuất Prometheus, series có thể có tên như `jvm_gc_memory_allocated_bytes_total`. Truy vấn tốc độ cấp phát:

~~~promql
sum by (application, instance) (
  rate(jvm_gc_memory_allocated_bytes_total{
    application="order-service"
  }[5m])
)
~~~

Kết quả thường là **byte/giây**. Tuy nhiên, meter allocation trong Micrometer có thể suy ra từ GC/memory-pool dữ liệu; không phải bộ đếm chính xác tuyệt đối của mọi lần cấp phát trên mọi collector. Hãy kiểm tra series và tính khả dụng trong môi trường thực.

Với GC pause timer, một truy vấn minh họa cho **tổng giây pause/giây quan sát**:

~~~promql
sum by (application, instance) (
  rate(jvm_gc_pause_seconds_sum{
    application="order-service"
  }[5m])
)
~~~

Nếu kết quả là `0.05`, có thể diễn giải gần đúng rằng tổng pause được ghi tương đương 0,05 giây mỗi giây (xấp xỉ 5% thời gian), **theo cách collector/metric ghi nhận GC pauses**. Không áp dụng kết luận này như một phép đo chính xác về CPU hoặc thời gian mất của từng request.

Khi cần số lần pause mỗi giây, dùng series `jvm_gc_pause_seconds_count` với `rate()`. Muốn p95 pause từ histogram, phải xác nhận exporter có các bucket phù hợp; không thể suy p95 từ `_count` và `_sum`.

## 11. Heap cao: bình thường, áp lực bộ nhớ hay memory leak?

Một biểu đồ heap có dạng “răng cưa” thường là dấu hiệu JVM cấp phát object rồi GC thu hồi:

~~~text
heap used
  ^
  |      /|       /|       /|
  |     / |      / |      / |
  |____/  |_____/  |_____/  |____> thời gian
         GC       GC       GC
~~~

Điều cần xem là **đáy sau GC có tăng dần qua nhiều chu kỳ hay không**, không chỉ nhìn đỉnh. Một heap sử dụng 85% trước GC nhưng giảm xuống 35% sau GC có thể hoàn toàn bình thường. Ngược lại, sau mỗi lần GC đầy đủ, mức dữ liệu còn sống tiếp tục tăng dù workload tương tự thì cần điều tra retention hoặc leak.

| Dấu hiệu | Giả thuyết có thể | Dữ liệu đối chiếu |
| --- | --- | --- |
| Heap used dao động mạnh nhưng hồi phục tốt | Cấp phát/GC bình thường, có thể allocation pressure cao | Allocation rate, GC pause, throughput |
| Old generation sau GC tăng đều | Cache phình, giữ tham chiếu, memory leak hoặc workload giữ dữ liệu nhiều hơn | GC logs, live-data, heap dump khi phù hợp |
| Heap used sát max và GC hoạt động liên tục | Memory pressure, nguy cơ `OutOfMemoryError` | GC pause, error logs, container/heap limit |
| Metaspace tăng qua nhiều lần reload/deploy | Nhiều class/classloader, có thể classloader leak | Class loading metrics, heap/classloader analysis |
| Heap ổn nhưng container bị OOMKilled | Native/direct memory, thread stacks, memory overhead hoặc limit quá thấp | Container memory, RSS, buffer metrics, NMT khi bật |

**Memory leak** nghĩa là ứng dụng giữ lại dữ liệu không còn cần thiết, khiến GC không thu hồi được. Heap tăng theo thời gian là **triệu chứng có thể có nhiều nguyên nhân**. Để xác nhận, cần bằng chứng sâu hơn: heap dump, dominator tree, allocation profiling hoặc dữ liệu retention phù hợp, trong khuôn khổ quy trình vận hành an toàn.

## 12. Phân biệt JVM memory với container memory

Một ứng dụng chạy trong Kubernetes có thể được cấu hình:

~~~yaml
resources:
  requests:
    memory: "768Mi"
  limits:
    memory: "1536Mi"
~~~

Ví dụ trên là một **đoạn cấu hình container** minh họa, không phải cấu hình Actuator. Nếu JVM dùng `-Xmx1024m` thì giới hạn heap khoảng 1 GiB, nhưng tiến trình còn cần RAM cho Metaspace, thread stack, direct buffers, native allocations và overhead. Tổng bộ nhớ container có thể tiến gần 1,5 GiB trong khi `jvm.memory.used{area="heap"}` vẫn chưa đạt max.

Đối chiếu các nguồn:

- **JVM heap/non-heap:** `jvm.memory.*` từ Micrometer.
- **Buffer pools:** `jvm.buffer.*` nếu binder và JVM cung cấp.
- **Process RSS hoặc memory resident:** metric tiến trình do hệ điều hành/collector cung cấp, nếu có; không đồng nghĩa heap.
- **Container/cgroup memory:** metric của hệ thống giám sát container/Kubernetes; giới hạn và thống kê phụ thuộc môi trường.
- **Sự kiện OOMKill:** thông tin trạng thái của container/orchestrator và logs liên quan.

Khi thấy container OOMKilled, đừng vội tăng `-Xmx`: tăng heap tối đa trong cùng memory limit có thể **làm ít chỗ hơn cho native memory** và khiến sự cố nặng hơn. Cần lập ngân sách bộ nhớ cho toàn tiến trình và đánh giá nguyên nhân.

## 13. Dashboard nền tảng cho JVM memory

Một dashboard hữu ích nên tập trung vào các câu hỏi vận hành thay vì đặt mọi meter lên một màn hình.

| Panel đề xuất | Dữ liệu | Mục đích |
| --- | --- | --- |
| Heap used / committed / giới hạn | `jvm.memory.used/committed/max` | Xem ngân sách và xu hướng |
| Heap pools | Heap `area`, `id` theo instance | Xác định pool chịu áp lực |
| Non-heap pools | Metaspace, Code Cache... | Phát hiện áp lực ngoài heap |
| Allocation rate | `jvm.gc.memory.allocated` nếu có | Xem tốc độ tạo dữ liệu |
| GC pauses | `jvm.gc.pause` count/sum (và buckets nếu có) | Nhận biết áp lực GC |
| Process/container memory | RSS/cgroup metrics từ nguồn phù hợp | Phát hiện vượt ngân sách tổng |
| Request latency và lỗi | `http.server.requests` Timer và 5xx | Liên hệ dấu hiệu JVM với trải nghiệm người dùng |

Lưu ý khi đặt các panel cạnh nhau: các metric có **đơn vị, nhịp scrape và cách tổng hợp khác nhau**. Heap used là gauge ở một thời điểm; GC pause sum/counter cần `rate()` trên khoảng đo; HTTP p95 cần histogram buckets hoặc nguồn phân phối phù hợp.

### 13.1. Nhãn nào nên giữ?

Nhãn `application`, `instance`, `area`, `id` và `region` hữu hạn thường đủ để chia metric JVM theo dịch vụ, instance và memory pool. Không gắn `userId`, `orderId`, `requestId` hoặc URL thực làm labels. JVM memory dùng chung cho tiến trình, không có quan hệ một-một với từng người dùng hoặc request.

Ngay cả khi tag tự định nghĩa có cardinality thấp, thêm nó vào mọi JVM meter vẫn nhân số series theo số tổ hợp. Chỉ thêm common tags thật sự cần cho dashboard và routing của monitoring backend.

## 14. Cảnh báo: tránh lấy một ngưỡng heap làm chân lý

Một cảnh báo “heap used > 90%” có thể hữu ích, nhưng cũng có nhiều **false positives**: GC chưa diễn ra, pool có max không ổn định, hoặc collector chủ động sử dụng heap rộng để tối ưu throughput. Nên kết hợp với GC pressure, mức used sau GC, độ trễ và giới hạn container.

Ví dụ rule cho một hệ thống **đã xác minh** rằng pool `G1 Old Gen` báo max phù hợp với giới hạn heap:

~~~yaml
groups:
  - name: spring-boot-jvm-memory
    rules:
      - alert: HighJvmHeapUsage
        expr: |
          (
            sum by (application, instance) (
              jvm_memory_used_bytes{
                application="order-service",area="heap"
              }
            )
            /
            max by (application, instance) (
              jvm_memory_max_bytes{
                application="order-service",
                area="heap",
                id="G1 Old Gen"
              } > 0
            )
          ) > 0.90
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "JVM heap usage cao kéo dài"
~~~

**Phạm vi của rule:** chỉ là minh họa theo pool/collector đã kiểm chứng; không copy nguyên cho mọi JVM. Không có sample max hợp lệ thì rule có thể không đánh giá được. Một hệ thống với SLO nghiêm ngặt có thể cần alert dựa trên GC pauses, OOMKilled, memory headroom hoặc error-budget burn rate thay vì chỉ occupancy.

Trước khi áp dụng:

1. Xác minh metric và labels có tồn tại trong Prometheus.
2. Kiểm tra độ chính xác của mẫu số trên đúng collector/version/JVM flags.
3. Điều chỉnh thời gian `for` dựa trên scrape interval và chu kỳ GC; tránh báo động từ một đỉnh ngắn.
4. Đối chiếu với tốc độ allocation, GC pause, old-gen sau GC và container memory.
5. Gắn hướng dẫn xử lý cho cảnh báo, giải thích các bước khoanh vùng và ngưỡng nào cần escalation.

## 15. Điều tra sự cố thực tế: p95 tăng và heap đi lên

**Bối cảnh.** Dịch vụ `order-service` có 4 instance. Sau một bản phát hành, p95 latency tăng từ 180 ms lên 900 ms, tỉ lệ 5xx từ 0,2% lên 3%. Biểu đồ heap used của một số instance tăng nhanh, GC pause cũng tăng.

### Bước 1 — phân loại triệu chứng

Xem cùng một cửa sổ thời gian:

- RPS và tỉ lệ lỗi có tăng tương ứng không? Nếu RPS không đổi mà heap/GC tăng, có thể có thay đổi cách xử lý bên trong.
- Instance nào có `jvm_memory_used_bytes` tăng; pool nào tăng nhiều nhất?
- `jvm_gc_pause_seconds_sum` và allocation rate có tăng cùng thời điểm không?
- Container memory còn headroom hay vừa xuất hiện OOMKill/restart?

### Bước 2 — hình thành giả thuyết

Một vài giả thuyết có thể kiểm tra:

| Quan sát | Giả thuyết | Bằng chứng cần tìm |
| --- | --- | --- |
| Eden tăng nhanh, GC dày, sau GC hồi phục | Object tạm tạo quá nhiều | Allocation profile, workload mới, GC pause |
| Old gen giữ nhiều dữ liệu sau GC | Cache/collection phình, giữ tham chiếu | Heap dump hoặc live-set analysis |
| Non-heap Metaspace tăng | Sinh class/classloader liên tục | Class loading, classloader analysis |
| Heap ổn, RSS/container memory tăng | Direct/native memory hoặc thread stack | Buffer pool, thread count, NMT/container |
| CPU/GC bình thường nhưng p95 tăng | Sự cố downstream/DB/lock | Traces, connection pool, logs |

### Bước 3 — tìm code path và nguyên nhân

Dùng logs để tìm `OutOfMemoryError`, thay đổi cấu hình bộ nhớ, batch load và warning GC nếu đã bật log thích hợp. Dùng tracing để xem một request chậm đang tiêu thời gian ở code nội bộ, database hay downstream. Nếu trace sampling chưa chọn request liên quan, có thể tái hiện trong môi trường thử nghiệm với chính sách sampling phù hợp.

**Không đặt trace ID hay request ID làm tag cho `jvm.memory.used`.** Metric JVM là trạng thái của toàn tiến trình; việc liên kết với request nên dựa trên thời gian, instance, các trace/span attributes và log correlation.

### Bước 4 — xác nhận sau sửa

Sau khi sửa đường code gây tạo object quá mức hoặc giữ tham chiếu, theo dõi vài chu kỳ GC và traffic đại diện:

- Heap used sau GC có ổn định lại không?
- Allocation rate và GC pause có giảm?
- p95/p99, 5xx và throughput có trở về ngưỡng mong muốn?
- Container RSS và số lần restart/OOMKill có được kiểm soát?

Một khoảng giảm sau GC là tín hiệu tích cực nhưng chưa phải bằng chứng chắc chắn không còn leak. Hãy theo dõi đủ thời gian cho dạng tải tạo ra vấn đề ban đầu.

## 16. Lỗi thường gặp khi đọc JVM memory metrics

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra phù hợp |
| --- | --- | --- |
| `/actuator/metrics/jvm.memory.used` trả 404 | Endpoint chưa expose hoặc JVM binder chưa có/đã bị tắt | Dependency Actuator, management endpoints, cấu hình metrics |
| Có metric ở Actuator nhưng thiếu trên Prometheus | Thiếu Prometheus registry, endpoint hoặc scrape target | `/actuator/prometheus` và trạng thái target |
| `jvm_memory_max_bytes` bằng số âm hoặc thiếu | Pool không công bố max hữu hạn | Kiểm tra `area`/`id`, collector, `MemoryMXBean`, JVM flags |
| Tỷ lệ heap > 100% hoặc âm | Cộng sai pool max, nhầm đơn vị/instance, max không hợp lệ | Đối chiếu từng pool và mẫu số |
| Heap gần 100% nhưng ứng dụng vẫn ổn | GC chưa xảy ra, collector giữ heap rộng | Xem nhịp GC và đáy sau GC |
| Heap bình thường nhưng OOMKilled | Native/direct memory, RSS, cgroup limit hoặc memory overhead | Container memory, RSS, `jvm.buffer.*` |
| Không thấy đỉnh heap dù log có GC | Scrape interval bỏ lỡ biến động ngắn | Điều chỉnh độ phân giải khi phù hợp, xem GC metrics/logs |
| `rate(jvm_memory_used_bytes)` âm hoặc khó hiểu | `jvm.memory.used` là gauge có thể giảm sau GC | Dùng gauge trực tiếp; allocation rate lấy từ GC counters |
| Mỗi lần deploy có tên pool khác nhau | Thay JVM/collector/version | Không hardcode pool nếu muốn dashboard đa collector |
| Alert memory liên tục nhiễu | Cảnh báo theo đỉnh nhất thời, nhầm max và workload | Bổ sung `for`, post-GC và GC pressure |
| Biểu đồ cộng heap của tất cả instance gây hiểu sai | Dashboard gộp cả cụm nhưng ngưỡng theo mỗi JVM | `sum by (instance)` hoặc lọc target cụ thể |

Một chỉ số có thể đo đúng về mặt kỹ thuật nhưng **diễn giải sai về mặt vận hành**. Luôn gắn câu hỏi cần trả lời với đơn vị, mẫu số và phạm vi tổng hợp rõ ràng.

## 17. Thực hành kiểm chứng với Spring Boot

Bài tập dưới đây dùng một ứng dụng Spring Boot có Actuator và Prometheus registry.

### Bài tập A — khám phá và đọc dữ liệu

1. Khởi động ứng dụng, gọi `/actuator/metrics` và tìm `jvm.memory.used`, `jvm.memory.committed`, `jvm.memory.max`.
2. Lấy output `jvm.memory.used` với `area=heap` và `area=nonheap`. Ghi lại danh sách `id` của JVM đang chạy.
3. Đọc `/actuator/prometheus`, tìm các series `jvm_memory_used_bytes`, `jvm_memory_committed_bytes`, `jvm_memory_max_bytes`.
4. Chuyển một giá trị byte sang MiB. Giải thích khác biệt `used`, `committed`, `max`.
5. Kiểm tra pool nào báo `max` không xác định và giải thích tại sao không dùng nó làm mẫu số tỷ lệ.

### Bài tập B — PromQL và dashboard

Thiết kế các panel sau:

- Heap used MiB theo `instance`.
- Non-heap used MiB theo `instance`.
- Heap pool breakdown theo `id`.
- Allocation rate và GC pause nếu meter tương ứng có sẵn.
- HTTP error rate và latency trên cùng timeline.

Tự xác minh rằng biểu đồ không cộng các instance khi mục đích là cảnh báo một JVM. Nếu tính %heap, giải thích mẫu số đến từ đâu và vì sao hợp lệ với collector hiện tại.

### Bài tập C — mô phỏng tải có kiểm soát

Trong môi trường test, chạy một tác vụ phân bổ một số object tạm theo batch nhỏ và để GC quản lý bình thường. Quan sát `jvm.memory.used` trước, trong và sau khi tạo tải. Không cố tình tạo OOM hoặc dùng payload lớn gây ảnh hưởng hệ thống dùng chung.

Ghi nhận:

1. Used thay đổi thế nào theo thời gian?
2. Sau một hoặc nhiều GC, bộ nhớ có giảm không?
3. `committed` hoặc `max` có nhất thiết thay đổi cùng nhịp used không?
4. Scrape interval có làm mất một số đỉnh ngắn không?
5. Có thể kết luận memory leak chỉ từ biểu đồ used không?

### Bài tập D — phân tích tình huống

Một container limit 1,5 GiB, JVM cấu hình `-Xmx1g`; heap used khoảng 600 MiB nhưng container bị OOMKilled. Hãy liệt kê các vùng bộ nhớ ngoài heap có thể chiếm phần còn lại và nguồn dữ liệu cần xem. Giải thích vì sao tăng `-Xmx` lên 1,3 GiB trong cùng container limit có thể là quyết định không phù hợp.

### Câu hỏi tự kiểm tra

1. Tại sao `jvm.memory.used` là Gauge thay vì Counter?
2. `used`, `committed` và `max` khác nhau như thế nào?
3. Có thể coi tổng `jvm.memory.used` là RSS của tiến trình Java không?
4. Vì sao heap used giảm ngay sau GC không có nghĩa metric bị reset?
5. Những memory pool nào có thể thay đổi theo collector/version?
6. Vì sao không lấy `rate(jvm_memory_used_bytes)` để đo allocation rate?
7. Tại sao `jvm_memory_max_bytes` không phải lúc nào cũng có mẫu số dương hợp lệ cho tổng heap?
8. Heap cao lúc trước GC và heap cao sau GC khác nhau về ý nghĩa thế nào?
9. Nếu có 4 instance, dùng phép tổng toàn cụm có phù hợp để cảnh báo heap từng JVM không?
10. Metrics, logs và traces đóng vai trò gì trong phân tích lỗi do áp lực bộ nhớ?

**Tiêu chí hoàn thành:** giải thích đúng ba đại lượng used/committed/max; nhận diện heap/non-heap và giới hạn native/container; đọc được Actuator/Prometheus, tính/biện minh tỷ lệ sử dụng đúng collector; phân biệt Gauge với Counter; có thể lập dashboard và quy trình điều tra cùng GC, logs và traces.

## 18. Ghi nhớ

- **JVM memory metrics** cho biết trạng thái các memory pools; `jvm.memory.used`, `committed` và `max` có ý nghĩa và giới hạn khác nhau.
- **Heap, non-heap, native memory và container memory không đồng nhất.** `-Xmx` chỉ giới hạn heap; vẫn cần ngân sách cho phần bộ nhớ còn lại.
- `jvm.memory.used` là **Gauge**, không phải Counter. Không dùng `rate()` trên used để thay thế tốc độ cấp phát.
- **Max có thể không xác định theo pool**; kiểm tra `area/id` và collector trước khi xây tỷ lệ heap hoặc alert.
- Kết hợp JVM memory với allocation, GC pause, process/container memory và latency/error rate giúp phân biệt memory pressure, tải bình thường và dấu hiệu leak.
- Spring Boot Actuator + Micrometer cung cấp các meter JVM; Prometheus scrape để hiển thị xu hướng. Không cần tạo Observation thủ công cho mỗi lần đọc heap.
- Theo dõi tags hữu hạn như `application/instance/area/id`, tránh ID từng request; dùng logs/traces để đi từ triệu chứng memory tới đường xử lý cụ thể.

## Tài liệu tham khảo

- [Micrometer Reference — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Java SE — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Java SE — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

