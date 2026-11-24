# LongTaskTimer: theo dõi công việc còn đang chạy trong Spring Boot

> **Chương:** Metrics nền tảng  
> **Bài:** LongTaskTimer  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Bài toán: tác vụ chạy quá lâu nhưng biểu đồ latency chưa đổi

Giả sử một dịch vụ Spring Boot nhập danh mục sản phẩm theo lô. Thông thường mỗi lần đồng bộ mất khoảng 2 phút, nhưng trong lần triển khai mới, một đợt đồng bộ đã chạy 25 phút và vẫn chưa kết thúc.

Nếu chỉ ghi `Timer` thông thường quanh phương thức đồng bộ, dashboard về **thời gian của các lần hoàn tất** sẽ chưa nhận được mẫu mới từ công việc bị kẹt. Khi phương thức chưa trả về, phép đo thời gian hoàn thành vẫn chưa được ghi. Đây là khoảng trống quan sát quan trọng: hệ thống có thể đang bận hoặc bị treo, nhưng số liệu hoàn tất chưa phản ánh ngay.

**`LongTaskTimer`** của Micrometer dành cho tình huống đó. Nó theo dõi **những công việc đang diễn ra**, giúp trả lời:

- Hiện có bao nhiêu đợt đồng bộ đang chạy?
- Tổng thời gian đang trôi qua của tất cả đợt đồng bộ còn hoạt động là bao nhiêu?
- Khi có ít hoặc một tác vụ hoạt động, thời gian đã chạy của chúng đang tăng như thế nào?
- Có nhiều đợt đồng bộ chồng lấp nhau khiến tài nguyên bị bão hòa không?

Đây là metric rất hữu ích cho các công việc dài: import/export dữ liệu, batch, migration, xây dựng chỉ mục, làm mới cache, đồng bộ hệ thống ngoài, reindex hoặc các bước xử lý có thể kéo dài hàng phút đến hàng giờ.

**Mục tiêu của bài:** sử dụng `LongTaskTimer` đúng vòng đời, hiểu cách đọc dữ liệu active, cấu hình trong Spring Boot, kiểm tra qua Actuator/Prometheus, phân biệt với Timer hoàn tất, đồng thời tránh lỗi đo trùng, sai thời điểm stop và tăng cardinality không kiểm soát.

## 2. LongTaskTimer đo những đại lượng nào?

Một LongTaskTimer chứa các **sample** đại diện cho những tác vụ còn đang chạy. Mỗi sample bắt đầu tại `start()` và thôi được tính là đang chạy khi gọi `stop()` tương ứng.

Các phép đo cốt lõi:

| Phép đo | Ý nghĩa | Diễn giải |
| --- | --- | --- |
| **Active tasks** | Số sample vẫn đang hoạt động | Có 3 job import chưa kết thúc |
| **Duration sum of active tasks** | Tổng thời gian đã trôi qua của các sample còn hoạt động, thường xuất theo giây | Ba job đang chạy lần lượt 2, 3, 5 phút → tổng khoảng 10 phút |
| **Duration của một tác vụ đang chạy** | Tuổi tác vụ tại thời điểm lấy mẫu; có thể suy ra khi chỉ một tác vụ active | Một job duy nhất đang chạy 300 giây |
| **Thống kê bổ sung tùy implementation/backend** | Có thể có giá trị cực đại hoặc các dữ liệu khác | Chỉ sử dụng khi registry/exporter thực tế cung cấp |

Ví dụ, xét hai tác vụ song song:

~~~text
t = 00:00       Job A start
t = 02:00       Job B start
t = 05:00       Thời điểm giám sát đọc metric

Job A đang chạy 5 phút = 300 giây
Job B đang chạy 3 phút = 180 giây

active_tasks  = 2
duration_sum  ≈ 480 giây
average_age   ≈ 240 giây cho mỗi job đang chạy
~~~

**`duration_sum` không phải tổng thời gian của các job đã hoàn tất.** Nó chỉ xét những sample còn hoạt động tại thời điểm đo. Khi một sample kết thúc, sample đó rời khỏi tập active; active count giảm và tổng duration của những sample còn lại được tính lại.

Vì vậy, `duration_sum` có thể **tăng rồi giảm đột ngột** khi một job kết thúc. Đây là hành vi bình thường của LongTaskTimer, không phải counter reset hay hệ thống làm mất dữ liệu.

Một điểm cần nhớ: giá trị duration có thể **tiếp tục tăng giữa các lần scrape**, vì nó được tính từ thời điểm start đến thời điểm đọc. Metric về active duration không phải một Counter mà ta nên lấy `rate()` để đếm sự kiện.

## 3. So sánh LongTaskTimer và Timer

`Timer` thường ghi thời lượng sau khi một thao tác kết thúc. `LongTaskTimer` cho biết trạng thái của thao tác **khi nó còn chạy**.

| Khía cạnh | `Timer` thông thường | `LongTaskTimer` |
| --- | --- | --- |
| Thời điểm có số liệu mới | Sau khi ghi xong một duration, thường khi thao tác hoàn tất | Ngay khi có sample active; duration tăng trong lúc chạy |
| Phép đo cốt lõi | Count đã ghi, tổng thời lượng đã ghi; có thể có max/histogram | Số task active, tổng thời gian đang chạy của các task active |
| Cách nhìn một tác vụ 20 phút chưa xong | Chưa có sample hoàn tất từ tác vụ này | Active count có thể là 1, active duration tăng dần |
| Phù hợp cho | HTTP latency, truy vấn DB, nghiệp vụ đã hoàn tất, p95/p99 sau xử lý | Batch đang chạy, công việc dài bất thường, số lượng công việc đồng thời |
| Khi tác vụ hoàn tất | Một duration được ghi vào thống kê | Sample được loại khỏi tập active |
| Query thời lượng đã hoàn tất | Phân tích count/sum/histogram nếu cấu hình | Không thay thế dữ liệu hoàn tất |
| Có cần kết thúc đúng cách? | Có, để ghi đủ duration | Có, để tránh giữ một tác vụ “đang chạy” mãi |

Hai công cụ này **có thể được dùng đồng thời cho cùng một job với hai ý nghĩa khác nhau**: LongTaskTimer đo “đang chạy bao lâu”, Timer đo “đã hoàn tất mất bao lâu”. Khi đó phải đặt tên metric rõ ràng và instrument chính xác một lần cho từng trách nhiệm. Không cộng count của chúng như thể cùng một đơn vị đo.

LongTaskTimer **không tự cung cấp p95 duration của các job hoàn tất**. Nếu cần phân phối thời gian hoàn tất hoặc SLO kiểu “95% import dưới 5 phút”, hãy dùng một Timer có histogram/distribution phù hợp và ghi khi công việc xong.

## 4. Vòng đời: một sample cho một lần thực thi

API cơ bản gồm:

1. Khai báo hoặc lấy `LongTaskTimer` trong `MeterRegistry`.
2. Gọi `LongTaskTimer.start()` **ngay khi công việc thực sự bắt đầu** để nhận một `LongTaskTimer.Sample`.
3. Giữ sample trong phạm vi của lần thực thi đó.
4. Gọi `sample.stop()` đúng **một lần** khi công việc hoàn tất, thất bại hoặc bị hủy.
5. Khi nhiều công việc cùng chạy, mỗi công việc có sample riêng nhưng có thể dùng chung cùng một LongTaskTimer.

~~~mermaid
sequenceDiagram
    participant App as ImportService
    participant Timer as LongTaskTimer
    participant Sample as Sample A
    participant Scraper as Prometheus
    App->>Timer: start()
    Timer-->>App: Sample A
    Note over Sample: Job A đang chạy
    Scraper->>Timer: scrape
    Timer-->>Scraper: active_count=1, duration_sum tăng
    App->>App: thực hiện công việc
    Scraper->>Timer: scrape tiếp
    Timer-->>Scraper: active_count=1, duration_sum tăng
    App->>Sample: stop()
    Note over Timer: Sample A không còn active
    Scraper->>Timer: scrape
    Timer-->>Scraper: active_count=0, duration_sum=0
~~~

**Điểm khác biệt về tư duy:** Timer thường được nhớ đến ở thời điểm hoàn thành; LongTaskTimer được giám sát **trong khoảng thời gian đang thực thi**.

### 4.1. Bắt buộc đóng sample

Nếu thiếu `stop()` ở đường lỗi, LongTaskTimer có thể tiếp tục coi job đã lỗi là đang chạy, khiến active count và duration tăng sai. Vì vậy phải dùng `finally` ở luồng đồng bộ, hoặc callback kết thúc ở luồng bất đồng bộ.

Không được dùng một biến `Sample` dùng chung cho tất cả job rồi ghi đè mỗi khi có job mới: mỗi tác vụ có thời điểm bắt đầu độc lập. Nên giữ sample trong biến cục bộ hoặc đối tượng theo từng lần thực thi.

### 4.2. Thời gian đo là thời gian thực thi hay thời gian chờ?

LongTaskTimer không biết công việc có thực sự dùng CPU hay chỉ đang đợi I/O. Nó đo **thời gian trôi qua** từ `start` đến `stop`. Nếu job chờ database 10 phút, duration cũng tăng 10 phút. Điều này rất hữu ích cho phát hiện job quá lâu, nhưng để biết tại sao chậm cần thêm logs và distributed tracing.

Nếu mục tiêu là đo thời gian **xếp hàng**, đặt sample khi enqueue và stop khi dequeue; nếu mục tiêu là đo thời gian **xử lý**, start khi worker bắt đầu nhận job. Hai phép đo cần tên khác nhau, vì ranh giới khác nhau.

## 5. Tạo LongTaskTimer bằng Micrometer API

Ví dụ nhỏ nhất dùng `MeterRegistry`:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;

public final class ImportWorker {
    private final LongTaskTimer importTimer;

    public ImportWorker(MeterRegistry registry) {
        this.importTimer = LongTaskTimer.builder("catalog.import.running")
            .description("Elapsed time of currently running catalog imports")
            .tag("job", "catalog")
            .register(registry);
    }

    public void importCatalog(Runnable work) {
        LongTaskTimer.Sample sample = importTimer.start();

        try {
            work.run();
        } finally {
            sample.stop();
        }
    }
}
~~~

Đọc ví dụ theo từng bước:

- `LongTaskTimer.builder("catalog.import.running")` định nghĩa **tên metric** phản ánh công việc còn chạy, tránh gây nhầm với duration của job đã hoàn tất.
- `tag("job", "catalog")` dùng giá trị cố định, phù hợp cardinality thấp.
- `register(registry)` đăng ký meter vào registry được cung cấp. Nên tạo hoặc lấy meter **một lần khi khởi tạo component**, thay vì tạo tên/labels mới trong mỗi request.
- `start()` tạo một sample mới cho mỗi lần gọi `importCatalog(...)`.
- `finally` luôn gọi `sample.stop()` khi `work.run()` kết thúc, kể cả khi ném `RuntimeException` hoặc `Error` theo luồng exception thông thường.

Trong Java, `Runnable` không trả kết quả; phiên bản thực tế có thể dùng `Callable<T>`, `Supplier<T>` hoặc API nghiệp vụ. Dù chọn kiểu nào, nguyên tắc vẫn là **mỗi lần start phải có kết thúc tương ứng**.

### 5.1. Cùng một timer, nhiều sample song song

Giả sử hai thread gọi `importCatalog(...)` đồng thời. Chúng dùng chung đối tượng `importTimer`, nhưng mỗi lời gọi nhận một `Sample` riêng. Khi cả hai đang chạy, `activeTasks()` có thể trả về 2. Nếu một công việc xong, count giảm còn 1 và duration sum chỉ phản ánh công việc còn lại.

Không tạo một metric riêng cho mỗi job ID để “phân biệt từng sample”. LongTaskTimer đã theo dõi nhiều sample trong một meter; muốn biết job cụ thể nào bị kẹt thì dùng log/trace có định danh phù hợp.

## 6. Tích hợp trong Spring Boot và xuất metrics

Với ứng dụng Spring Boot 3.x, Micrometer thường được tích hợp thông qua Actuator. Để kiểm tra trực tiếp bằng Prometheus exporter, có thể thêm:

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

Với Spring Boot BOM hoặc parent quản lý dependency, các dependency này thường không cần khai báo version riêng. Cách cấu hình và output cụ thể có thể thay đổi theo phiên bản Micrometer/Spring Boot.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: catalog-service
~~~

- `/actuator/metrics` phục vụ khám phá meter theo tên Micrometer và xem tags/measurements.
- `/actuator/prometheus` xuất các chuỗi đo ở định dạng Prometheus khi registry tương ứng đã được thêm và endpoint được expose.
- Tag chung `application=catalog-service` giúp dashboard phân biệt các dịch vụ.
- Hãy giới hạn quyền truy cập endpoint quản trị trên môi trường thực và đảm bảo Prometheus được kết nối qua mạng phù hợp.

### 6.1. Tạo service Spring-managed

~~~java
package example.catalog;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CatalogImportService {
    private final LongTaskTimer runningImports;

    public CatalogImportService(MeterRegistry registry) {
        this.runningImports =
            LongTaskTimer.builder("catalog.import.running")
                .description("Age of active catalog import jobs")
                .tag("job", "catalog")
                .register(registry);
    }

    public void importNow(Runnable job) {
        LongTaskTimer.Sample sample = runningImports.start();

        try {
            job.run();
        } finally {
            sample.stop();
        }
    }

    public int activeImports() {
        return runningImports.activeTasks();
    }
}
~~~

`@Service` giúp Spring tạo bean, còn `MeterRegistry` do Spring Boot cấu hình được inject vào constructor. Không cần tạo `SimpleMeterRegistry` mới trong service production, vì registry mới có thể tách khỏi exporter và dashboard đang dùng.

**Khi kiểm tra:** gọi một lần import lâu hơn vài chu kỳ scrape, sau đó truy cập Actuator. Nếu import hoàn tất quá nhanh, LongTaskTimer sẽ trở về zero trước khi bạn kịp quan sát.

## 7. Đọc số liệu bằng Actuator và Prometheus

Sau khi triển khai service và chạy một job thử:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/catalog.import.running
curl http://localhost:8080/actuator/prometheus
~~~

Tùy registry và phiên bản, endpoint metrics có thể cung cấp số đo tương ứng **active tasks** và **duration** của các công việc đang chạy, cùng các tags đã đăng ký. Xem output thật để biết measurement name và đơn vị; đừng suy ra từ tên metric.

Với Prometheus, một LongTaskTimer tên `catalog.import.running` thường được biểu diễn bằng các chuỗi có dạng:

~~~text
catalog_import_running_seconds_active_count{job="catalog",application="catalog-service"} 2
catalog_import_running_seconds_duration_sum{job="catalog",application="catalog-service"} 480
~~~

Đây là **dữ liệu minh họa** tại một thời điểm: có hai job đang chạy, tổng tuổi hai job là khoảng 480 giây. Chúng có thể đến từ cùng một instance; khi nhiều instance, exporter thường có thêm labels mục tiêu scrape như `job` hoặc `instance`. Tên series, suffix, cách đổi tên/đơn vị và các series bổ sung **phụ thuộc registry/exporter/version**; trước khi viết dashboard hay alert, hãy tìm tên series thực tế trong `/actuator/prometheus`.

### 7.1. Vì sao duration sum không phải counter?

Giả sử tại t = 100 giây, job A đang chạy 100 giây. Tại t = 110 giây, A hoàn tất; nếu không còn job khác thì duration sum về 0. Dùng `rate()` cho chuỗi này sẽ cho kết quả không diễn đạt được “số job/giây”, vì đây là **đo trạng thái hiện tại**, có thể giảm khi sample kết thúc.

Với **số lần hoàn thành** hoặc **throughput job**, cần Counter hoặc Timer hoàn tất. Để đo concurrency và thời gian đang chạy, dùng LongTaskTimer.

### 7.2. Vì sao job ngắn có thể biến mất giữa hai lần scrape?

Nếu Prometheus scrape mỗi 15 giây còn một job chỉ chạy 2 giây, có thể không có thời điểm scrape nào nằm trong khoảng hoạt động. Khi đó, biểu đồ `active_count` không cho thấy job này dù nó đã chạy thành công. LongTaskTimer **không ghi lịch sử hoàn tất**, nên không phù hợp để đếm tất cả các tác vụ ngắn.

Đối với tác vụ ngắn, Timer thông thường là lựa chọn chính; LongTaskTimer phù hợp với tác vụ đủ dài để quan sát khi đang chạy.

## 8. PromQL: dashboard cho các công việc đang hoạt động

Giả sử exporter thực sự có hai series:

- `catalog_import_running_seconds_active_count`: số lượng job đang chạy.
- `catalog_import_running_seconds_duration_sum`: tổng thời gian đã chạy của các job còn hoạt động, theo giây.

Các truy vấn sau dùng label `application="catalog-service"` từ ví dụ cấu hình. Tên và labels cần đối chiếu với exporter thật.

### 8.1. Tổng số job đang chạy trong cụm

~~~promql
sum(
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

Dùng phép cộng qua các instance để lấy tổng concurrency. Nếu muốn so sánh tải giữa các instance:

~~~promql
sum by (instance) (
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

`active_count` là gauge; **không** áp dụng `rate()` hoặc `increase()` như với Counter.

### 8.2. Tổng thời gian đã chạy của các job còn active

~~~promql
sum(
  catalog_import_running_seconds_duration_sum{
    application="catalog-service"
  }
)
~~~

Giá trị 600 **không nhất thiết** có nghĩa là một job đang chạy 10 phút: có thể là hai job đã chạy mỗi job 5 phút, hoặc sáu job đã chạy mỗi job 100 giây. Đây là tổng tuổi của các job đang active, không phải thời lượng lớn nhất trong số đó.

### 8.3. Tuổi trung bình của các job hiện còn chạy

~~~promql
sum(
  catalog_import_running_seconds_duration_sum{
    application="catalog-service"
  }
)
/
sum(
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

Kết quả là **số giây trung bình đã chạy của các job active** tại thời điểm đánh giá, **không phải** latency trung bình của các job đã hoàn tất. Khi không có job active, mẫu số bằng 0; dashboard cần xử lý trường hợp này riêng (ví dụ hiển thị “không có job đang chạy”) thay vì coi đó là một giá trị latency hợp lệ.

### 8.4. Tách theo loại job

Nếu có một bộ giá trị hữu hạn cho label `job` như `catalog`, `inventory`, `pricing`, có thể truy vấn:

~~~promql
sum by (job) (
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

Lưu ý ví dụ này chỉ có ý nghĩa nếu metric chung thực sự được đăng ký cho các loại job đó. Nếu mỗi công việc dùng **tên metric khác nhau**, phải chọn đúng series; không tự giả định `job` luôn tồn tại.

**Không tính percentile p95 của job hoàn tất từ `active_count` và `duration_sum`.** Hai chuỗi này mô tả trạng thái hiện tại và không mang phân phối các lần hoàn tất. Nếu cần percentile, dùng Timer thông thường và histogram phù hợp.

## 9. Cảnh báo với LongTaskTimer: phải hiểu đúng phép đo

LongTaskTimer thích hợp để cảnh báo khi **quá nhiều job cùng hoạt động** hoặc khi **tuổi trung bình của các job đang chạy** tăng bất thường.

Ví dụ: hệ thống mong mỗi thời điểm tối đa 3 import chạy đồng thời. Cảnh báo nếu toàn cụm có hơn 3 import active liên tục 10 phút:

~~~yaml
groups:
  - name: catalog-imports
    rules:
      - alert: TooManyCatalogImportsRunning
        expr: |
          sum(
            catalog_import_running_seconds_active_count{
              application="catalog-service",job="catalog"
            }
          ) > 3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Có hơn 3 catalog import chạy đồng thời"
~~~

Đây là **ngưỡng minh họa**. Trong thực tế, chọn ngưỡng từ thiết kế worker pool, giới hạn concurrency, thời gian dự kiến và đặc điểm tải.

### 9.1. Không dùng duration_sum như “max job duration”

Giả sử ngưỡng mong muốn là “báo khi có **bất kỳ một job** chạy quá 15 phút”. Một rule dạng:

~~~promql
sum(catalog_import_running_seconds_duration_sum) > 900
~~~

**không đáp ứng chính xác** yêu cầu đó: hai job đã chạy mỗi job 8 phút tạo tổng 960 giây, dù không job nào vượt 15 phút.

Nếu backend/exporter có **phép đo max active duration** phù hợp, hãy xác minh tên và semantics rồi dùng nó. Nếu không có, cân nhắc bổ sung cơ chế giám sát riêng theo từng job đang chạy (ví dụ trạng thái job trong cơ sở dữ liệu và một gauge/health check có cardinality được kiểm soát). Tránh đoán rằng mọi exporter đều phát một series `_max` có tên giống nhau.

Có thể cảnh báo **tuổi trung bình của các job active** khi đó là mục tiêu phù hợp, nhưng phải đặt tên cảnh báo rõ ràng và xử lý mẫu số bằng 0. Không coi average age là max age.

### 9.2. Kết hợp với số lần hoàn tất và lỗi

Một cảnh báo đầy đủ cho job nền thường cần cả:

- Số job active và active duration từ LongTaskTimer.
- Số job hoàn tất thành công/thất bại từ Counter hoặc Timer hoàn tất.
- Thời điểm hoàn thành gần nhất hoặc tiến độ từ hệ thống quản lý job khi cần.

Một job có thể “đang chạy rất lâu” mà thực ra là công việc hợp lệ; cần kết hợp SLA của job, kỳ vọng batch size và tín hiệu tài nguyên trước khi phân loại sự cố.

## 10. Đo đồng thời active duration và thời gian hoàn tất

Đối với job dài, nên có hai góc nhìn riêng: **đang chạy** và **đã hoàn tất**. Ví dụ dưới đây phối hợp `LongTaskTimer` với `Timer` thông thường nhưng chỉ tạo **một lần instrument cho mỗi mục đích**.

~~~java
package example.catalog;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CatalogImportMetrics {
    private final MeterRegistry registry;
    private final LongTaskTimer activeTimer;

    public CatalogImportMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.activeTimer = LongTaskTimer
            .builder("catalog.import.running")
            .description("Current duration of running imports")
            .tag("job", "catalog")
            .register(registry);
    }

    public void runImport(Runnable work) {
        LongTaskTimer.Sample active = activeTimer.start();
        Timer.Sample completed = Timer.start(registry);
        String outcome = "success";

        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            active.stop();

            completed.stop(
                Timer.builder("catalog.import.completed")
                    .description("Duration of finished import attempts")
                    .tag("job", "catalog")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
~~~

Ý nghĩa:

1. `catalog.import.running` phản ánh số lượng và thời gian đã trôi qua của job **chưa hoàn tất**.
2. `catalog.import.completed` nhận một mẫu duration **sau khi job hoàn tất hoặc thất bại**; nhờ vậy có thể tính throughput và latency distribution của các lần thử đã xong.
3. `outcome` có hai giá trị hữu hạn `success` và `error`, phù hợp metric tags. Nếu có trường hợp hủy hoặc bị từ chối hợp lệ, cần định nghĩa thêm kết quả theo semantics nghiệp vụ.
4. `finally` giải phóng long-task sample và ghi completed Timer kể cả khi `work.run()` ném `RuntimeException` hoặc `Error` qua đường code thông thường.
5. Nếu sử dụng retry, phải định nghĩa rõ một lần ghi là **attempt** hay **logical import**; đặt tên và vị trí instrument theo mục tiêu.

### Tránh đếm trùng khi đã có observation hoặc annotation

Nếu code đã gắn `@Timed(longTask = true)` cùng ranh giới của `runImport(...)`, **không thêm LongTaskTimer thủ công cùng tên và cùng boundary**. Nếu `@Observed` đã tạo Timer đo thời lượng hoàn tất của cùng bước, hãy kiểm tra meter handler trước khi tạo thêm một Timer khác có cùng ý nghĩa.

Tạo cả LongTaskTimer và Timer là hợp lệ khi chúng phục vụ **hai phép đo khác nhau** như trên; một lỗi đo trùng xảy ra khi hai cơ chế cùng thực hiện **một chức năng đo** cho cùng thao tác, khiến count hoặc span bị nhân đôi.

## 11. Dùng @Timed(longTask = true) và điều kiện để hoạt động

Micrometer cung cấp annotation `@Timed` với lựa chọn `longTask = true` cho trường hợp muốn instrument một phương thức bằng AOP. Đây có thể là lựa chọn gọn hơn gọi `start()/stop()` thủ công khi ranh giới đo trùng chính xác với vòng đời phương thức.

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class ScheduledImportService {
    @Timed(
        value = "catalog.import.running",
        longTask = true,
        extraTags = {"job", "catalog"}
    )
    public void executeImport() {
        // Công việc đồng bộ dài, hoàn tất khi method trả về.
        performImport();
    }

    private void performImport() {
        // Xử lý dữ liệu theo lô.
    }
}
~~~

Để annotation có tác dụng trong mô hình dùng Spring AOP, cần **`TimedAspect`** được đăng ký và có hỗ trợ AOP tương ứng. Một cấu hình minh họa (chỉ thêm nếu ứng dụng chưa có aspect tương đương):

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimerAspectConfig {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Với proxy-based Spring AOP, lời gọi **từ chính một method sang method khác của cùng bean** thường không qua proxy, nên annotation có thể không được intercept. Ngoài ra, các kiểu xử lý bất đồng bộ cần xác minh cách aspect đo thời điểm hoàn tất; không mặc định method trả về future nghĩa là timer tiếp tục chạy đến khi future hoàn thành.

**Quy tắc lựa chọn:** dùng một trong hai cách cho cùng ranh giới công việc: **manual `LongTaskTimer.Sample`** hoặc **`@Timed(longTask = true)`** đã được AOP instrument. Nếu có cả hai cùng theo dõi đúng method, phải kiểm tra dữ liệu trùng.

## 12. Công việc bất đồng bộ: stop khi kết quả thực sự hoàn tất

Một lỗi dễ gặp:

~~~java
LongTaskTimer.Sample sample = timer.start();
try {
    executor.submit(this::importData);
} finally {
    sample.stop(); // Sai nếu muốn đo thời gian importData thực sự chạy.
}
~~~

Ở đây sample kết thúc ngay sau khi lệnh `submit` trả về, trong khi `importData` vẫn chạy trên thread khác. Metric sẽ chỉ đo **thời gian gửi tác vụ**, không đo công việc dài.

Với `CompletionStage`, có thể giữ sample cho đến khi kết quả thực sự hoàn thành:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class AsyncImportMonitor {
    private final LongTaskTimer timer;

    public AsyncImportMonitor(LongTaskTimer timer) {
        this.timer = timer;
    }

    public <T> CompletionStage<T> monitor(
            Supplier<CompletionStage<T>> submit) {

        LongTaskTimer.Sample sample = timer.start();

        try {
            CompletionStage<T> stage = submit.get();

            // Callback được gọi cả khi stage thành công hoặc thất bại.
            return stage.whenComplete((value, error) -> sample.stop());
        } catch (RuntimeException | Error ex) {
            // Cả trường hợp việc khởi tạo stage thất bại.
            sample.stop();
            throw ex;
        }
    }
}
~~~

Phạm vi đo ở ví dụ là từ khi `monitor(...)` bắt đầu đến khi stage hoàn tất. Nếu muốn tách **thời gian chờ trong queue** với **thời gian thực thi**, hãy start sample khi worker thực sự bắt đầu xử lý, hoặc thiết kế hai phép đo có boundary và tên riêng.

**Cần lưu ý:**

- `whenComplete` có thể chạy trên thread khác; `sample.stop()` phải được gắn với đúng lần thực thi, không giữ chung sample ở một field singleton.
- Nếu stage hoàn tất bằng lỗi hoặc bị hủy và callback vẫn được thực thi, sample sẽ được stop. Nếu future bị bỏ quên và không bao giờ hoàn tất, sample vẫn active — có thể là dấu hiệu công việc bị kẹt hoặc vòng đời code chưa xử lý đầy đủ.
- LongTaskTimer bản thân không thay thế **context propagation**. Nếu dùng Micrometer Observation và distributed tracing cùng callback async, cần truyền current observation/trace context qua executor, Reactor hoặc cơ chế phù hợp với framework; chỉ giữ tham chiếu `Sample` không đủ để nối các spans.
- Với các job có khả năng chạy xuyên nhiều tiến trình hoặc được giao lại khi instance chết, metric trong bộ nhớ không thể đại diện duy nhất cho trạng thái nghiệp vụ; cần đối chiếu với hệ thống quản lý job bền vững.

## 13. Cardinality: chọn tag có giới hạn cho long-running jobs

Dù LongTaskTimer dùng để theo dõi công việc đang chạy, nó vẫn là một meter có **tổ hợp tags**. Tag không kiểm soát sẽ tạo ra nhiều meter/time series giống như Timer hay Counter.

| Tag nên cân nhắc | Tag cần tránh | Lý do |
| --- | --- | --- |
| `job=catalog/inventory/pricing` | `jobId=UUID...` | ID mới cho mỗi job làm tăng số meter |
| `environment=dev/staging/prod` | `requestId=...` | Request ID gần như duy nhất |
| `outcome` khi có định nghĩa và thời điểm gắn phù hợp | `userId=...` | Không phù hợp với metrics và có thể là dữ liệu cá nhân |
| `region` thuộc tập cố định | `filePath` chứa tên file sinh tự do | Số giá trị không giới hạn, có thể lộ thông tin |
| `workerPool` thuộc tập cố định | `exceptionMessage=...` | Tạo nhiều giá trị và có thể chứa dữ liệu nhạy cảm |

Với LongTaskTimer, nên tránh gắn **outcome chỉ biết khi kết thúc** vào timer đang chạy: một tag `outcome=success` trước khi có kết quả sẽ đánh lừa dashboard, còn việc tạo timer mới theo outcome ở phút cuối có thể làm rối lifecycle. Hãy gắn outcome vào Timer/Counter **hoàn tất** trong phần 10; LongTaskTimer active chỉ cần tags đã biết khi job bắt đầu.

Ví dụ, một meter có 4 loại job, 3 region và 6 instance có thể phát sinh tới **4 × 3 × 6 = 72 tổ hợp** cho mỗi series output. Nếu thêm job ID với hàng chục nghìn giá trị, số series tăng mạnh dù trong cùng thời điểm chỉ có vài job active. Tùy registry, meter được đăng ký theo tag có thể còn tồn tại trong suốt vòng đời tiến trình sau khi job hoàn tất, nên không dựa vào việc sample đã stop để tránh cardinality explosion.

### Liên kết với logs và traces

Muốn biết **job cụ thể nào** chạy 40 phút, dùng job ID hoặc correlation ID trong logs/traces khi chính sách dữ liệu cho phép, rồi nối với khoảng thời gian mà metrics phát hiện bất thường. Tránh gắn ID này làm metric tag.

Một `Observation` nghiệp vụ có thể giúp ghi low-cardinality tags, span attributes và trace context. Nhưng **không mặc định mỗi Observation là một LongTaskTimer**. Việc tạo long-task sample phải qua instrumentation tương ứng (manual hoặc `@Timed(longTask = true)`); nếu cần cả Timer hoàn tất, Span và LongTaskTimer, hãy xác định owner cho từng phép đo để không đếm trùng.

Sampling của tracing không phải sampling của metrics: một job có thể đóng góp vào LongTaskTimer dù trace của nó không được export. Vì vậy kết hợp metrics, logs và traces giúp điều tra mà vẫn giữ khả năng tổng hợp đáng tin cậy.

## 14. Các lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `active_count` luôn bằng 0 | Job hoàn tất trước lần scrape; code chưa start; xem sai registry | Chạy job thử đủ lâu, xem Actuator ngay khi đang chạy |
| `active_count` không giảm dù job đã báo lỗi | Bỏ quên `sample.stop()` trên nhánh exception/cancellation | Đảm bảo stop ở `finally` hoặc callback completion |
| Duration tăng nhưng không có job thật | Sample bị bỏ quên, future không hoàn tất hoặc scope đo bị mở quá rộng | Đối chiếu thread/job state và đường kết thúc |
| Timer hoàn tất không có mẫu của job đang kẹt | Đây là khác biệt bản chất của Timer với LongTaskTimer | Theo dõi LongTaskTimer khi active; ghi Timer sau khi xong |
| Prometheus không tìm thấy `..._active_count` | Thiếu registry, endpoint chưa expose, tên output khác hoặc chưa có meter | Kiểm tra dependency, `/actuator/metrics` và exporter thực tế |
| Tổng duration tăng và giảm “không đều” | Một số sample bắt đầu/kết thúc làm tổng tuổi active thay đổi | Đọc cùng active count và timeline |
| `rate(duration_sum)` khó giải thích | Áp dụng hàm của Counter cho gauge-like measurement | Query trực tiếp hoặc phân tích average active age |
| Có 3 job nhưng count bằng 6 | Instrument trùng hoặc mỗi logical job tạo nhiều sample | Xác nhận ranh giới và số lần start/stop |
| Tag/series tăng không kiểm soát | Dùng job ID, file name hoặc URL làm tag | Chuyển ID sang logs/traces, giảm tập tag |
| Khi app restart active count về 0 | Sample chỉ tồn tại trong bộ nhớ tiến trình | Đối chiếu với job state bền vững và requeue logic |
| Có metric nhưng không thấy trace | Chưa có tracing bridge/exporter, sampling hoặc mất propagation | Kiểm tra tracing pipeline riêng |
| Job thực tế chậm nhưng active duration thấp | `start` xảy ra sau thời gian queue/wait hoặc `stop` quá sớm | Xác nhận chính xác boundary đang đo |

### Quy trình điều tra khi LongTaskTimer báo bất thường

1. Kiểm tra **active count** theo instance và theo loại công việc. Xem có quá nhiều job đồng thời so với worker pool hay không.
2. Xem **duration sum** cùng active count. Không suy ra “một job quá lâu” từ tổng duration khi có nhiều job.
3. Đối chiếu **Timer hoàn tất**, số lỗi, thời điểm job hoàn tất gần nhất hoặc dữ liệu trạng thái job bên ngoài.
4. Tìm log theo thời gian và correlation ID; xác minh job đã thực sự bắt đầu/chạy hay đang chờ lock/I/O.
5. Mở trace của job được sample nếu có; quan sát spans database, HTTP downstream hoặc messaging để tìm bước chậm.
6. Sau khi khắc phục, kiểm tra active count trở về mức bình thường và completed duration/error rate được cải thiện.

## 15. Tình huống tổng hợp: import kẹt trong production

**Bối cảnh:** dịch vụ `catalog-service` chạy 3 instance, mỗi instance cho phép tối đa 2 import song song. Bình thường mỗi import mất 2–4 phút. Sau một lần nâng cấp schema, dashboard hiển thị:

~~~text
catalog_import_running_seconds_active_count
  instance=A: 2, instance=B: 2, instance=C: 1

Tổng active jobs = 5
Tổng tuổi của 5 jobs = 2.400 giây
Tuổi trung bình của job đang chạy = 480 giây
~~~

Con số 480 giây (~8 phút) **không khẳng định cả 5 job đều chạy đúng 8 phút**. Một số có thể vừa bắt đầu, một số đã quá 15 phút. Điều cần xem tiếp là trạng thái từng job trong hệ thống quản lý batch và dấu vết của các lần thực thi liên quan.

**Điều tra:** log cho thấy các job đợi lock từ database sau khi schema thay đổi; traces của những request đã được sample cho thấy span gọi DB kéo dài. Metrics về pool connections và throughput cũng thay đổi cùng thời điểm.

**Khắc phục:** xử lý lock contention, điều chỉnh mức concurrency phù hợp, và bổ sung cảnh báo khi active count vượt mức mong đợi liên tục. Sau sửa, LongTaskTimer cho thấy số job chạy đồng thời giảm; Timer hoàn tất ghi lại duration 2–4 phút như kỳ vọng.

**Bài học:** LongTaskTimer phát hiện **công việc chưa xong**, Timer xác nhận **thời gian của công việc đã xong**, logs và traces giúp tìm nguyên nhân. Một tín hiệu đơn lẻ hiếm khi đủ để chứng minh gốc rễ sự cố.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### 16.1. Thiết kế instrument

Một Spring Boot service có `DailyReconciliationJob` chạy từ 30 giây đến 20 phút và có thể chạy song song trên 2 instance. Hãy:

1. Thêm `LongTaskTimer` tên `reconciliation.jobs.running`, với tag `job=daily`.
2. Gọi `sample.start` hay `timer.start()` đúng chỗ trong code? Viết lại theo API Micrometer và bảo đảm có `sample.stop()` trong `finally`.
3. Giữ một `Timer` riêng tên `reconciliation.jobs.completed` để ghi duration sau khi job kết thúc; gắn `outcome=success/error`.
4. Chạy hai job chồng lấp nhau đủ lâu để quan sát active count tăng từ 0 → 1 → 2 → 1 → 0.
5. Kiểm tra `/actuator/metrics` và `/actuator/prometheus` khi job đang chạy và sau khi xong.

### 16.2. Đọc số liệu và thiết kế dashboard

Giả sử tại một thời điểm có 3 job đang chạy với tuổi 20, 40 và 100 giây:

- `active_count` phải bằng **3**.
- `duration_sum` khoảng **160 giây**.
- Tuổi trung bình khoảng **160 / 3 ≈ 53,3 giây**.
- Không thể suy ra chính xác **max age = 100 giây** chỉ từ hai số tổng hợp trên nếu chưa biết từng sample.
- Khi job 100 giây kết thúc, active count còn 2 và duration sum giảm theo thời lượng của sample đã dừng.

Hãy viết PromQL hiển thị tổng active count toàn cụm và tuổi trung bình của những job active, đồng thời giải thích vì sao mẫu số bằng 0 cần xử lý riêng.

### 16.3. Tìm lỗi lifecycle

Cho mã sai:

~~~java
LongTaskTimer.Sample sample = timer.start();
CompletableFuture.runAsync(this::doImport);
sample.stop();
~~~

Hãy giải thích phép đo đang phản ánh điều gì, vì sao không theo dõi thời gian import, và viết lại bằng callback hoàn tất hoặc instrument trực tiếp trong worker. Nếu công việc bị hủy hoặc báo lỗi, phải bảo đảm sample được kết thúc.

### 16.4. Câu hỏi kiểm tra

1. Vì sao một job đang kẹt có thể chưa làm thay đổi Timer duration của các lần hoàn tất?
2. `LongTaskTimer.duration(TimeUnit.SECONDS)` biểu diễn điều gì khi có ba job đang chạy?
3. Điều gì xảy ra với `active_count` và `duration_sum` khi một sample stop?
4. Vì sao `rate()` không phải cách tính “job/giây” từ `active_count`?
5. Một job chạy 1 giây với scrape interval 15 giây có nhất thiết xuất hiện trên biểu đồ không?
6. Vì sao `duration_sum > 900` không chứng minh một job riêng lẻ chạy quá 900 giây?
7. Khi nào nên dùng `@Timed(longTask = true)`, khi nào nên dùng manual sample?
8. Nếu muốn p95 duration **các job hoàn tất**, cần loại meter nào?
9. Tại sao không gắn `jobId` làm metric label, dù muốn biết job nào đang bị kẹt?
10. Nếu app restart trong khi job vẫn có trạng thái “running” trên DB, metric active sẽ thể hiện điều gì và cần kiểm tra thêm gì?

**Tiêu chí hoàn thành:** hiểu đúng dữ liệu active, tự instrument và đóng sample an toàn, đọc được metric thực tế trong Spring Boot, không nhầm gauge với Counter, biết phối hợp Timer hoàn tất, xử lý async và hạn chế cardinality.

## 17. Ghi nhớ

- **`LongTaskTimer` theo dõi các công việc còn đang chạy**; `Timer` thông thường đo các lần ghi thời lượng khi công việc đã hoàn tất.
- `start()` trả về `LongTaskTimer.Sample`; phải gọi `stop()` khi công việc kết thúc, kể cả nhánh lỗi/hủy, để active count không bị sai.
- Hai số quan trọng là **active tasks** và **tổng thời gian đang chạy của các active tasks**. Tổng này không phải thời lượng lớn nhất của một job và có thể giảm khi job kết thúc.
- Khi cần SLO thời lượng hoàn tất hoặc throughput, bổ sung **Timer/Counter** có ý nghĩa riêng; đừng cố tính p95 hoàn tất từ long-task active duration.
- Trong Spring Boot, dùng `MeterRegistry` được quản lý sẵn, kiểm tra tên series và đơn vị thực trên exporter. Với Prometheus, active count là gauge-like measurement nên không dùng `rate()` để đếm job.
- Với async, stop lúc việc thực sự hoàn tất; với metrics, giữ tags hữu hạn. Dùng logs/traces để tìm job cụ thể, kiểm tra sampling và context propagation khi điều tra lỗi.

## Tài liệu tham khảo

- [Micrometer Reference — Timers và Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

