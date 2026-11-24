# Query theo tag với Spring Boot Actuator Metrics Endpoint

> **Chương:** Actuator metrics endpoint  
> **Bài:** Query theo tag  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vấn đề thực tế: một metric, nhiều lát cắt dữ liệu

Một dịch vụ Spring Boot cung cấp API tạo đơn hàng. Từ dashboard, bạn thấy số lần gọi API tăng và một phần yêu cầu trả về lỗi. Tuy nhiên, cần biết **lỗi xuất hiện chủ yếu ở kênh web hay mobile**, hoặc phương thức `POST` trên route `/api/orders` có thực sự bị ảnh hưởng hay không.

Micrometer lưu các phép đo (*meters*) dưới tên và những cặp **tag key–value**. Ví dụ:

~~~text
orders.create.attempts{channel="web",    outcome="success"} → count = 120
orders.create.attempts{channel="web",    outcome="error"}   → count =   5
orders.create.attempts{channel="mobile", outcome="success"} → count =  80
orders.create.attempts{channel="mobile", outcome="error"}   → count =  10
~~~

Ở đây `orders.create.attempts` là **một tên metric** có bốn tổ hợp tags. Query theo tag giúp bạn chỉ chọn những tổ hợp mong muốn.

Với Spring Boot Actuator, một cách kiểm tra trực tiếp là:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web
~~~

Truy vấn này chọn dữ liệu có `channel=web`. Để chỉ lấy những lần lỗi trên web:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

Đây là cú pháp **lọc theo tag ở endpoint Actuator**, không phải PromQL. Nó rất hữu ích để xác minh việc gắn nhãn đúng hay sai, kiểm tra một đợt triển khai, điều tra nhanh sự cố hoặc hỗ trợ test instrumentation.

**Kết quả cần đạt:** nắm cú pháp `tag=key:value`, cách kết hợp nhiều tag, hiểu ý nghĩa của `measurements`/`availableTags`, phân biệt metric name với tên Prometheus series, và biết khi nào phải chuyển sang truy vấn time series thay vì dùng endpoint Actuator.

## 2. Endpoint /actuator/metrics có những chức năng nào?

Spring Boot Actuator cung cấp endpoint `metrics` để khám phá và kiểm tra những meter đã đăng ký trong `MeterRegistry` mà ứng dụng sử dụng.

| Đường dẫn | Mục đích | Ví dụ |
| --- | --- | --- |
| `GET /actuator/metrics` | Liệt kê tên metric hiện có | `jvm.memory.used`, `http.server.requests` |
| `GET /actuator/metrics/{metricName}` | Xem số đo và tags của metric theo tên Micrometer | `/actuator/metrics/jvm.memory.used` |
| `GET /actuator/metrics/{metricName}?tag=k:v` | Chỉ xét meter có cặp tag khớp | `?tag=area:heap` |
| `GET /actuator/metrics/{metricName}?tag=a:x&tag=b:y` | Lọc theo nhiều cặp tag | `?tag=method:POST&tag=status:500` |
| `GET /actuator/prometheus` | Xuất số liệu ở định dạng dành cho Prometheus, **không phải** API query theo tag của `/metrics` | Các series `*_total`, `*_seconds_count` |

Tên `{metricName}` phải là **tên meter trong Micrometer**, thường có dấu chấm, ví dụ `http.server.requests`. Tên metric trên Prometheus thường đổi theo naming convention, có thể chuyển dấu chấm thành dấu gạch dưới và thêm đơn vị hoặc hậu tố. Đừng tìm `http_server_requests_seconds_count` như tên đường dẫn của Actuator nếu meter trong ứng dụng có tên `http.server.requests`.

Trong một ứng dụng Spring Boot mặc định, các đường dẫn trên dùng prefix `/actuator` nếu endpoint web được expose; prefix, port và base path có thể được thay đổi bởi cấu hình management. Trên môi trường thực, cần dùng URL quản trị đúng với ứng dụng và giới hạn truy cập.

## 3. Cấu hình Spring Boot để thực hành

Ví dụ hướng tới Spring Boot 3.x, có thể điều chỉnh theo phiên bản project. Với Maven và Spring Boot parent/BOM:

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

`spring-boot-starter-actuator` cho phép tích hợp metrics và các management endpoints. `micrometer-registry-prometheus` chỉ cần khi muốn xuất dữ liệu theo định dạng Prometheus; **không bắt buộc** để gọi `/actuator/metrics` trong ứng dụng đã có một `MeterRegistry` phù hợp.

Cấu hình `application.yml` tối thiểu cho môi trường học tập:

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

Một vài lưu ý:

- Expose `metrics` chỉ giúp truy cập endpoint; **không tự tạo metric nghiệp vụ** nếu code chưa thực thi đường instrument.
- Nếu Prometheus registry không hiện diện, endpoint `prometheus` có thể không tồn tại dù đã nằm trong danh sách exposure.
- Property `management.metrics.tags.application` thêm common tag vào các meter qua cấu hình phù hợp; tên tag thực tế nên được kiểm chứng.
- Trong production, bảo vệ management endpoints bằng network policy, authentication/authorization hoặc management port riêng. Danh sách tags có thể tiết lộ cấu trúc nội bộ, trạng thái ứng dụng và thông tin triển khai.
- Ví dụ trong bài dùng `localhost:8080`. Nếu đã cấu hình `management.server.port` hoặc `management.endpoints.web.base-path`, URL cần thay đổi tương ứng.

Để xem danh sách tên meter:

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

Chỉ khi tên mong muốn xuất hiện trong kết quả, mới chuyển sang query các tags của nó.

## 4. Tạo một metric có tags để thử nghiệm

Để việc thực hành không phụ thuộc vào HTTP instrumentation hoặc tên pool JVM, ta tự tạo Counter nghiệp vụ `orders.create.attempts`. Mỗi lần thực thi tạo đơn sẽ ghi một kết quả vào một trong hai nhóm `outcome=success` hoặc `outcome=error`, phân biệt theo `channel`.

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderCreationService {
    private final MeterRegistry registry;

    public OrderCreationService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void create(String incomingChannel, Runnable work) {
        String channel = normalizeChannel(incomingChannel);
        String outcome = "success";

        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            registry.counter(
                "orders.create.attempts",
                "channel", channel,
                "outcome", outcome
            ).increment();
        }
    }

    private static String normalizeChannel(String incoming) {
        if ("web".equals(incoming)) return "web";
        if ("mobile".equals(incoming)) return "mobile";
        if ("partner".equals(incoming)) return "partner";
        return "other";
    }
}
~~~

**Giải thích:**

1. `MeterRegistry` được Spring Boot inject, nên số liệu đi vào registry đã cấu hình. Không tự tạo một registry tách biệt ngay trong service.
2. `channel` được chuẩn hóa thành bốn giá trị giới hạn (`web`, `mobile`, `partner`, `other`), tránh bùng nổ cardinality.
3. `outcome` được xác định sau khi biết kết quả của `work.run()`. `finally` ghi đúng một lần cho mỗi lời gọi đồng bộ, kể cả có ngoại lệ.
4. Hai nhánh thành công/lỗi có cùng **tên metric** nhưng khác tổ hợp tags.
5. Ví dụ đo **attempts**, không đo số đơn được tạo thành công. Một lần retry sẽ là một attempt khác; cần định nghĩa rõ semantics trước khi xây SLO.
6. Nếu ứng dụng đã có một Counter hoặc Observation ghi cùng số attempt ở đúng vị trí này, không thêm một phép đo thứ hai cùng chức năng.

Lời gọi ví dụ ở một test hoặc một service khác:

~~~java
orderCreationService.create("web", () -> repository.saveNewOrder());

orderCreationService.create("mobile", () -> {
    throw new IllegalStateException("Demo failure");
});
~~~

`repository` là thành phần nghiệp vụ giả định; ví dụ lỗi phải được bắt ở tầng test/controller thích hợp khi muốn tiếp tục kịch bản. Trong sản phẩm thật, tránh ghi exception message có dữ liệu nhạy cảm thành tag.

### Tạo dữ liệu kiểm tra có thể dự đoán

Giả sử môi trường test không có traffic nền, không bị retry và bạn gọi:

| Kênh | Thành công | Lỗi | Tổng attempts |
| --- | ---: | ---: | ---: |
| `web` | 12 | 3 | 15 |
| `mobile` | 8 | 2 | 10 |
| `partner` | 5 | 0 | 5 |
| **Tổng** | **25** | **5** | **30** |

Trong một tiến trình mới và đúng các lời gọi này, `orders.create.attempts` ghi **COUNT = 30**. Dùng query theo tag để xác minh các lát cắt, thay vì suy diễn chỉ từ tổng.

## 5. Cú pháp tag=key:value: đọc đúng một điều kiện

Cú pháp cơ bản:

~~~text
GET /actuator/metrics/{metricName}?tag={tagKey}:{tagValue}
~~~

Ví dụ:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/orders.create.attempts?tag=channel:web"
~~~

Ý nghĩa là **chọn những meter của tên đó có tag `channel` mang giá trị chính xác `web`**. Đây không phải tìm kiếm substring hay regex. Nếu bộ tag thực có `channel=mobile-app`, lọc `channel=mobile` không tự bao gồm nó.

Những trường hợp cần phân biệt:

| Query | Chọn dữ liệu |
| --- | --- |
| Không có tham số tag | Tất cả tổ hợp tags của metric có trong registry |
| `?tag=channel:web` | Chỉ những tổ hợp có `channel=web` |
| `?tag=outcome:error` | Mọi kênh có `outcome=error` |
| `?tag=channel:mobile` | Những tổ hợp có `channel=mobile` |
| `?tag=channel:WEB` | Chỉ `WEB` nếu thực sự có; không mặc định bằng `web` |

Nếu muốn trả về metric khác, thay **tên meter ở đường dẫn**, không dùng `tag` để thay tên metric. Query theo tag chỉ chọn các meter đang mang key/value tương ứng.

### Điều quan trọng về dấu hai chấm

Tham số `tag` có định dạng `key:value`. Key nằm trước dấu hai chấm đầu tiên, value nằm sau. Khi giá trị có ký tự đặc biệt hoặc URL, cần bảo đảm request được URL-encode đúng, tránh để `&` bị hiểu là dấu phân cách tham số query.

Ưu tiên dùng `curl -G --data-urlencode` trong ví dụ có dấu cách, slash, ngoặc nhọn hoặc ký tự có ý nghĩa đối với URL.

## 6. Kết hợp nhiều tag: logic AND

Actuator cho phép **lặp lại tham số `tag`** để lọc theo nhiều cặp key–value.

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

Cách hiểu: **`channel=web` VÀ `outcome=error`**. Từ bộ dữ liệu thực hành ở phần 4, ta mong chờ COUNT = 3.

~~~bash
curl -s "http://localhost:8080/actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error"
~~~

Với curl dạng encode an toàn hơn:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/orders.create.attempts" \
  --data-urlencode "tag=channel:web" \
  --data-urlencode "tag=outcome:error"
~~~

Cùng một pattern có thể áp dụng cho HTTP server metrics nếu các tags đó thực sự tồn tại:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=status:500"
~~~

Một số nhầm lẫn:

- Hai tham số `tag` **không mang nghĩa OR**. `tag=channel:web&tag=outcome:error` không có nghĩa “web hoặc lỗi”.
- Viết `tag=channel:web,outcome:error` không phải cú pháp nhiều tag của endpoint; đó chỉ là một tham số và có thể được hiểu như giá trị chứa dấu phẩy.
- Hai giá trị đối nghịch của cùng một key, ví dụ `tag=channel:web&tag=channel:mobile`, không phải phép OR. Không có một meter bình thường nào đồng thời mang hai giá trị khác nhau cho cùng tag key.
- Nếu muốn **OR**, **regex**, **group by** hoặc phân tích theo thời gian, dùng API/query backend như PromQL. Với Actuator, có thể gọi riêng từng lát cắt rồi xử lý kết quả trong test hoặc công cụ của bạn.

**Quy tắc:** một bộ tag cố định xác định nhóm phép đo; lặp `tag=key:value` là giao của các điều kiện lọc.

## 7. URL encoding: truy vấn tag có dấu cách, slash và route template

Metric HTTP server thường có tag `uri` thể hiện **route template** (tùy cấu hình và framework), chẳng hạn `/api/orders/{id}`. Truy vấn dưới dạng raw URL có thể dễ gặp vấn đề với ký tự đặc biệt, shell hoặc client.

Sử dụng:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=uri:/api/orders/{id}"
~~~

Cách này giữ lại giá trị `/api/orders/{id}` nhưng tự encode đúng khi gửi request. Trên PowerShell, `curl` có thể là alias của công cụ khác; dùng `curl.exe` với cùng arguments nếu cần hành vi chuẩn của curl.

Nếu muốn kiểm tra JVM memory pool tên `G1 Old Gen`:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/jvm.memory.used" \
  --data-urlencode "tag=area:heap" \
  --data-urlencode "tag=id:G1 Old Gen"
~~~

Mức độ phù hợp của query phụ thuộc **danh sách `id` thực tế**. Với JVM dùng ZGC, Shenandoah, Parallel GC hoặc phiên bản khác, tên pool có thể không phải `G1 Old Gen`. Luôn khám phá `availableTags` trước.

### Những giá trị không nên dùng làm tag

Không đưa vào metric tags các giá trị có số lượng biến thể lớn như `orderId`, `userId`, `requestId`, token, query string đầy đủ hoặc URL chứa ID thực. Query theo tag không biến dữ liệu high-cardinality thành thiết kế hợp lý: những giá trị đó có thể tạo hàng nghìn/hàng triệu time series.

Ví dụ, `uri=/api/orders/{id}` là route template hữu hạn, khác với `uri=/api/orders/123456` được sinh mới cho từng đơn. Nếu cần điều tra request cụ thể, dùng logs/traces với trace ID hoặc span attributes được kiểm soát, thay vì thêm request ID làm metric label.

## 8. Đọc JSON: measurements và availableTags

Khi query một metric, Actuator thường trả JSON bao gồm `name`, `description`, `baseUnit`, `measurements` và `availableTags`. Ví dụ minh họa cho Counter sau khi lọc `channel=web`:

~~~json
{
  "name": "orders.create.attempts",
  "description": null,
  "baseUnit": null,
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 15.0
    }
  ],
  "availableTags": [
    {
      "tag": "outcome",
      "values": ["success", "error"]
    }
  ]
}
~~~

Ví dụ minh họa này phù hợp với dữ liệu phần 4: 12 thành công và 3 lỗi trên web, tổng COUNT = 15. Output thực tế có thể kèm tag khác như `application` hoặc có thứ tự khác, tùy cấu hình Spring Boot/Micrometer.

Giải thích từng trường:

| Trường JSON | Ý nghĩa |
| --- | --- |
| `name` | Tên metric được tra cứu theo tên Micrometer |
| `description` | Mô tả metric nếu có; có thể `null` |
| `baseUnit` | Đơn vị cơ sở nếu meter định nghĩa; có thể `null` |
| `measurements` | Những statistic mà meter cung cấp và giá trị được tổng hợp cho tập meter phù hợp |
| `availableTags` | Những tag/value khác có thể dùng để thu hẹp tiếp trong tập meter phù hợp, tùy dữ liệu và các tag đã lọc |

### Statistic phụ thuộc loại meter

| Loại meter | Những statistic thường gặp | Đừng diễn giải sai |
| --- | --- | --- |
| Counter | `COUNT` | Giá trị tích lũy từ khi meter tồn tại, không phải “request/giây” |
| Gauge | `VALUE` | Giá trị tại thời điểm đọc, có thể tăng hoặc giảm |
| Timer | `COUNT`, `TOTAL_TIME`, `MAX` | Count số mẫu đã ghi; tổng thời lượng và max không phải p95 |
| DistributionSummary | `COUNT`, `TOTAL`, `MAX` (phụ thuộc meter/phiên bản) | Tổng giá trị mẫu khác với duration của Timer |
| LongTaskTimer | Số công việc active và thời gian đang chạy, dưới statistic tương ứng | Không phải số job hoàn tất và latency p95 |

Khi query một tên meter mà có nhiều tổ hợp tags phù hợp, endpoint có thể **tổng hợp các measurements trên tập meter đó**. Vì vậy giá trị COUNT sau khi lọc `channel=web` có thể bằng tổng số đếm của `outcome=success` và `outcome=error`. Các statistic khác như MAX có semantics riêng, không được coi mọi giá trị đều là phép tổng đơn giản.

### Thực hành đọc availableTags

Với metric có `channel` và `outcome`:

1. Gọi không filter để xem các tag keys và giá trị có sẵn.
2. Thêm `tag=channel:web`; kết quả chỉ còn tập meter thuộc web.
3. Xem `availableTags` để nhận biết còn những giá trị `outcome` nào trong tập đó.
4. Thêm `tag=outcome:error` để thu hẹp kết quả.
5. So sánh các measurements với kết quả kịch bản test.

`availableTags` là công cụ khám phá, **không phải bảng dữ liệu thô của từng request**. Nó không cung cấp danh sách tất cả các tổ hợp tags kèm số đo riêng; khi cần từng lát cắt, query thêm điều kiện hoặc dùng backend time series.

## 9. Ví dụ chi tiết: lọc HTTP server metrics theo method, uri và status

Trong ứng dụng Spring MVC/WebFlux với instrumentation phù hợp, có thể có metric `http.server.requests`. Các tags phổ biến tùy framework/version gồm `method`, `uri`, `status`, `outcome`, `exception`. Không nên coi mọi tag chắc chắn tồn tại ở mọi phiên bản hoặc endpoint.

### 9.1. Khám phá tên và tags

~~~bash
curl -s http://localhost:8080/actuator/metrics

curl -s http://localhost:8080/actuator/metrics/http.server.requests
~~~

Nếu metric này có sẵn, output sẽ cho biết `availableTags`, ví dụ `method=GET/POST`, `status=200/404/500` và `uri` gồm những route templates đã được quan sát. Tên route/tags thực tế có thể khác, nhất là khi request chưa thực thi hoặc route không được framework nhận diện.

### 9.2. Lọc POST /api/orders

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=uri:/api/orders"
~~~

Kết quả Timer có thể chứa `COUNT`, `TOTAL_TIME` và `MAX`. Để chọn thêm status 500:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=status:500"
~~~

Đây là truy vấn “POST và route này và status 500”, không phải “mọi lỗi 5xx”. Với status 500, 502, 503... khác nhau, một điều kiện `status:500` chỉ khớp đúng giá trị `500`.

Nếu có tag `outcome=SERVER_ERROR` theo convention thực tế, query theo `outcome` có thể phù hợp cho một nhóm 5xx. **Đừng đoán enum/tag values**; hãy xem `availableTags` và thử bằng traffic có kiểm soát.

### 9.3. Lỗi status không chỉ có trong HTTP

Một observation nghiệp vụ có thể gắn `outcome=error` trong khi HTTP response vẫn là 200 do ứng dụng bắt lỗi và trả kết quả dự phòng. Ngược lại HTTP 500 không luôn đồng nghĩa một giao dịch nghiệp vụ bị mất dữ liệu. Tag `status`, `outcome`, `exception` có những semantics khác nhau; phân tích SLI/SLO phải xác định định nghĩa “lỗi” cho từng tầng.

## 10. Ví dụ thứ hai: lọc JVM memory metrics theo area và id

Metric `jvm.memory.used` thường là Gauge với tags `area` và `id`. Mục đích là xác định pool nào dùng nhiều byte thay vì chỉ xem tổng toàn JVM.

~~~bash
# Xem các pool đã đăng ký và các giá trị của area/id.
curl -s "http://localhost:8080/actuator/metrics/jvm.memory.used"

# Chỉ lấy heap pools.
curl -s "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"

# Lấy đúng một pool khi biết tên.
curl -sG "http://localhost:8080/actuator/metrics/jvm.memory.used" \
  --data-urlencode "tag=area:heap" \
  --data-urlencode "tag=id:G1 Old Gen"
~~~

Nếu không chỉ định `id`, số đo `VALUE` có thể phản ánh kết quả tổng hợp của nhiều pool phù hợp. Nếu lọc thêm tên pool cụ thể, dữ liệu được thu hẹp xuống những meter có tag tương ứng. Tuy nhiên không nên coi số đo “used” đó là toàn bộ memory container hoặc RSS.

**Về giới hạn:** `jvm.memory.used` đo bộ nhớ JVM theo các pools; direct buffers, thread stacks và native memory có những đường đo riêng hoặc không được phản ánh đầy đủ. Với nghi vấn OOMKill ở container, cần xem cả process/container metrics và logs.

## 11. So sánh Actuator tag query với Prometheus/PromQL

Hai cách đều có thể chọn một tập metric theo nhãn, nhưng trả lời **những loại câu hỏi khác nhau**.

| Khía cạnh | Actuator `/actuator/metrics` | Prometheus + PromQL |
| --- | --- | --- |
| Nguồn dữ liệu | Registry của **một instance/process** được gọi | Các mẫu đã scrape từ một hoặc nhiều targets theo thời gian |
| Kiểu truy vấn | Tên metric + các cặp `tag=key:value` | Biểu thức chọn series, phép toán, aggregation, label matchers |
| Lọc nhãn | Chủ yếu theo giá trị khớp chính xác | `=`, `!=`, regex `=~`, `!~` |
| Kết hợp nhiều điều kiện | Lặp `tag` với ý nghĩa AND | Kết hợp matchers, aggregation, logic PromQL |
| Query theo thời gian | Không phải cơ chế query time-window | Có range vectors và các hàm `rate()`, `increase()`, `histogram_quantile()`... |
| Group by | Không có cú pháp group by tổng quát | `sum by (...)`, `max by (...)`... |
| Mục đích chính | Khám phá, debug, xác minh instrumentation | Dashboard lịch sử, SLI/SLO, alert, phân tích biến động |

Với Counter `orders.create.attempts`, truy vấn Actuator:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

trả số đo theo registry instance hiện tại. Nó **không trả số lỗi mỗi giây trong 5 phút**.

Trong Prometheus, một Counter này có thể được xuất dưới tên `orders_create_attempts_total` (hãy kiểm tra exporter thực tế). Truy vấn tốc độ lỗi cho web:

~~~promql
sum(
  rate(orders_create_attempts_total{
    channel="web",outcome="error"
  }[5m])
)
~~~

Tính tỷ lệ lỗi trên web:

~~~promql
sum(
  rate(orders_create_attempts_total{
    channel="web",outcome="error"
  }[5m])
)
/
sum(
  rate(orders_create_attempts_total{
    channel="web"
  }[5m])
)
~~~

Kết quả là tỷ lệ từ 0 đến 1 khi mẫu số dương. Trong khoảng không có traffic, mẫu số có thể bằng 0 hoặc không có dữ liệu. Dashboard/alert phải xử lý trường hợp đó.

**Không dùng Actuator để tính rate bằng cách gọi hai lần rồi trừ giá trị một cách tùy ý trên production** nếu không quản lý thời điểm, restart, target, reset và phân nhóm. Với giám sát liên tục, hãy dùng backend time series có cơ chế lấy mẫu và hàm xử lý counter phù hợp.

## 12. Một instance khác có thể trả kết quả khác

Trong hệ thống có 5 pod Spring Boot, mỗi pod giữ `MeterRegistry` của chính nó. Nếu truy cập `/actuator/metrics` qua load balancer, hai lần gọi có thể đi vào **hai pod khác nhau**.

Ví dụ:

~~~text
Pod A: orders.create.attempts{channel="web",outcome="error"} = 3
Pod B: orders.create.attempts{channel="web",outcome="error"} = 1
Pod C: orders.create.attempts{channel="web",outcome="error"} = 5
~~~

Một lệnh curl tới endpoint qua load balancer không phản ánh tổng toàn cụm = 9; nó chỉ phản ánh số liệu của target được định tuyến đến. Nếu hai request lần lượt vào A và B, bạn có thể thấy COUNT giảm 3 → 1 dù không có reset Counter.

Điều cần làm:

1. Khi debug local, xác định **đúng instance** bằng cách truy cập management endpoint trực tiếp trong môi trường được phép.
2. Nếu dùng Kubernetes, giữ nhất quán pod/target khi đối chiếu trước–sau trong một test.
3. Để xem tổng toàn cụm, dùng Prometheus scrape từng instance và `sum(...)` phù hợp.
4. Lưu ý Counter có thể reset khi ứng dụng restart hoặc meter được tạo lại; số tích lũy của từng pod không phải số giao dịch vĩnh viễn.
5. Giữ labels phân biệt service, môi trường và instance nhưng tránh gắn ID duy nhất của **mỗi request** vào metric.

Đây là khác biệt quan trọng giữa “query theo tag ở một JVM” và “truy vấn time series toàn cụm”.

## 13. Cardinality, bảo mật và quyền truy cập endpoint

Tag dùng cho metrics nên có số lượng giá trị giới hạn: `method`, `status`, `uri` dưới dạng **route template**, `outcome` và `channel` đã chuẩn hóa. Nếu thêm `userId`, email, IP động, request ID hoặc order ID, số lượng tổ hợp nhãn có thể tăng rất nhanh.

Giả sử metric có 4 channel, 3 outcome và 8 instance. Số tổ hợp tối đa cho mỗi dạng series có thể là:

~~~text
4 × 3 × 8 = 96 tổ hợp tags
~~~

Nếu thêm một `requestId` gần như khác nhau cho 100.000 lần gọi, số chuỗi có thể tăng theo số lần gọi; chi phí bộ nhớ, scrape và truy vấn đều tăng. Với histogram, số bucket có thể nhân thêm chi phí.

**Query theo tag không phải lời biện minh để đưa ID vào metrics.** Khi cần tìm một yêu cầu cụ thể:

- Dùng metrics low-cardinality để xác định thời điểm, route, outcome và instance bị ảnh hưởng.
- Dùng logs với `traceId/spanId` khi đã cấu hình correlation.
- Dùng distributed tracing để xem span đi qua các dịch vụ; một số span có thể mang high-cardinality attributes theo chính sách dữ liệu.
- Kiểm tra context propagation, sampler và exporter nếu trace không xuất hiện. Một lần query Actuator trả ra metric **không chứng minh** trace đã được export.

### Bảo vệ Actuator

Ngay cả khi không lộ dữ liệu người dùng, `availableTags` có thể tiết lộ API routes, trạng thái deployment và thông tin hệ thống. Trong production:

- Chỉ expose những endpoint cần thiết.
- Giới hạn truy cập bằng private network, proxy, authentication/authorization và cấu hình Spring Security phù hợp.
- Tránh gửi thông tin nhạy cảm vào metric name, tag key hoặc tag value từ đầu.
- Kiểm tra management port/base path và không mặc định các endpoint được bảo vệ giống như business API.
- Không tạo endpoint công khai nhận tag name/value tự do rồi chuyển tiếp thành truy vấn khi không có nhu cầu rõ ràng.

## 14. Lỗi thường gặp khi query theo tag

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `GET /actuator/metrics` trả 404 | Thiếu Actuator, endpoint chưa expose, base path/port khác hoặc security/routing | Kiểm tra dependency, exposure và management URL |
| `/actuator/metrics` hoạt động nhưng không thấy metric nghiệp vụ | Đường code chưa chạy, meter chưa được đăng ký, sai registry hoặc MeterFilter chặn | Gọi thử instrumentation, kiểm tra đúng MeterRegistry |
| Lọc `tag=channel:web` không có dữ liệu | Tag key/value khác, viết sai chữ hoa/thường hoặc metric chưa có tổ hợp đó | Đọc `availableTags` và tags thật |
| Dùng `tag=method:POST, status:500` không khớp | Ghép nhiều điều kiện thành một value | Lặp `tag=method:POST&tag=status:500` |
| Tag có dấu cách/ngoặc nhọn không khớp | URL encoding sai hoặc shell xử lý ký tự đặc biệt | Dùng `curl -G --data-urlencode` |
| Query `http_server_requests_seconds_count` trong `/actuator/metrics` thất bại | Nhầm tên Prometheus series với tên Micrometer meter | Dùng `http.server.requests` nếu meter thực có tên này |
| Cùng query nhưng số đếm lúc cao lúc thấp | Load balancer chọn pod khác, restart/reset hoặc tác vụ đang chạy thay đổi Gauge | Cố định instance và xét loại metric |
| Chọn `status:500` nhưng muốn toàn bộ 5xx | Exact match không phải nhóm trạng thái | Xác minh tag `outcome` hoặc dùng PromQL |
| `/actuator/metrics` có dữ liệu nhưng Prometheus thiếu | Registry Prometheus, endpoint, scrape config/target hoặc auth lỗi | Kiểm tra từng chặng xuất dữ liệu |
| `availableTags` quá nhiều giá trị | Instrumentation chứa ID tự do hoặc high-cardinality tag | Chuẩn hóa route/tags, loại các nhãn không hữu hạn |
| COUNT tăng nhưng p95 không đổi hoặc không có | Counter không có duration; Timer chưa có histogram thích hợp | Dùng Timer + histogram/PromQL cho percentile |
| Metric hiện nhưng trace tương ứng không thấy | Tracing chưa bật, sampling/exporter/propagation khác đường metrics | Kiểm tra tracing pipeline riêng |

**Mã HTTP khi filter không khớp:** tùy phiên bản và trường hợp, truy vấn có thể không tìm thấy meter phù hợp hoặc trả dữ liệu không như kỳ vọng. Cần xem response body/status thực tế; không dựa duy nhất vào việc endpoint tồn tại để kết luận tag filter hoạt động. Khi debug, bắt đầu bằng truy vấn không filter rồi tăng dần số điều kiện.

## 15. Quy trình điều tra lỗi: dùng tag query từng bước

Tình huống: một nhóm API của `order-service` bắt đầu trả lỗi sau bản triển khai.

**Bước 1 — kiểm tra meter đang tồn tại.**

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
~~~

Ghi lại tên tags từ `availableTags`, đặc biệt `uri`, `method`, `status`, `outcome`. Không giả định tag tự xuất hiện khi chưa có traffic.

**Bước 2 — cô lập route và method.**

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=method:POST"
~~~

Xác nhận COUNT và TOTAL_TIME phản ánh các request thực sự hoàn tất thuộc route và method này.

**Bước 3 — thu hẹp vào lỗi.**

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=status:500"
~~~

Nếu status không phải 500, chọn tag/value thực tế từ `availableTags`. Với yêu cầu nhóm lỗi 5xx, chuyển sang PromQL hoặc một tag outcome chuẩn nếu phù hợp.

**Bước 4 — so sánh metric nghiệp vụ.** Query `orders.create.attempts` theo `channel` và `outcome` để xác định lỗi đến từ bước tạo đơn hay từ tầng HTTP/server.

**Bước 5 — kiểm tra lịch sử và toàn cụm.** Dùng backend time series để xem error rate theo phút, biến động trước/sau deploy, p95 latency và tác động trên các instance. Actuator là snapshot của một process, không thay thế dashboard.

**Bước 6 — liên kết logs/traces.** Dựa vào thời gian và service, tìm log theo trace ID hoặc span có liên quan. Kiểm tra propagation và sampling khi điều tra request xuyên dịch vụ.

**Bước 7 — xác nhận sau khắc phục.** Lặp lại test có traffic xác định, kiểm tra tag mới không làm tăng cardinality, rồi theo dõi error rate/latency trên Prometheus.

### Phân biệt việc “không có dữ liệu” với “không có lỗi”

Một metric hoặc tổ hợp tags chưa từng được ghi có thể không tồn tại ở registry, chứ không nhất thiết có COUNT = 0. Đừng mặc định truy vấn trống có nghĩa hệ thống không lỗi: có thể sai tên, sai tag, query nhầm instance hoặc exporter chưa sẵn sàng.

## 16. Thực hành kiểm thử có đáp án dự kiến

Giả sử từ một tiến trình mới, chỉ có các lần gọi trong bảng:

| Tổ hợp | COUNT |
| --- | ---: |
| `channel=web, outcome=success` | 12 |
| `channel=web, outcome=error` | 3 |
| `channel=mobile, outcome=success` | 8 |
| `channel=mobile, outcome=error` | 2 |
| `channel=partner, outcome=success` | 5 |

Với Counter `orders.create.attempts`, thử xác định các kết quả:

| Query | COUNT dự kiến |
| --- | ---: |
| Không filter | 30 |
| `tag=channel:web` | 15 |
| `tag=outcome:success` | 25 |
| `tag=outcome:error` | 5 |
| `tag=channel:web&tag=outcome:error` | 3 |
| `tag=channel:mobile&tag=outcome:success` | 8 |
| `tag=channel:partner` | 5 |

Các số trên chỉ đúng cho workload giả định, trong điều kiện không có request nền hoặc retry và Counter bắt đầu từ 0. Nếu có common tags như `application`, số đo vẫn có thể đúng nhưng `availableTags` sẽ có thêm keys.

### Nhiệm vụ A — viết HTTP requests

1. Viết curl lấy tất cả metric names.
2. Viết curl lấy `orders.create.attempts` không filter.
3. Viết curl lọc `channel=mobile` và `outcome=error`.
4. Viết curl lọc `jvm.memory.used` theo `area=heap` và tên pool có dấu cách.
5. Giải thích cách encode `uri=/api/orders/{id}` đúng.

### Nhiệm vụ B — đọc JSON và trả lời

Từ response `/actuator/metrics/orders.create.attempts?tag=channel:web`, xác định `measurements` đang diễn tả điều gì và `availableTags` dùng để làm gì. Nếu thấy `outcome=success,error`, giải thích tại sao COUNT tổng không tự tách thành hai dòng.

### Nhiệm vụ C — xây truy vấn lịch sử

Viết PromQL tính số lần lỗi/giây của `channel=web` trong 5 phút và tỉ lệ lỗi trong mọi lần thử của kênh đó. Tự xác nhận tên Counter đã xuất ra Prometheus trước khi viết expression.

### Nhiệm vụ D — thử thay đổi môi trường

Chạy ứng dụng với hai instance và truy cập một endpoint qua load balancer. Giải thích vì sao COUNT từng lần gọi có thể khác nhau. Sau đó dùng Prometheus để tổng hợp COUNT/`rate()` giữa instances đúng cách.

### Câu hỏi tự kiểm tra

1. Cú pháp query theo tag trong Actuator là gì?
2. Khi dùng hai tham số `tag`, chúng kết hợp theo AND hay OR?
3. `tag=status:500` có chọn được mọi status 5xx không?
4. Vì sao `http.server.requests` và `http_server_requests_seconds_count` là hai cách đặt tên ở hai tầng khác nhau?
5. `availableTags` có trả dữ liệu từng request không?
6. Vì sao `COUNT=100` ở Actuator không có nghĩa là 100 request/giây?
7. Vì sao không nên thêm `requestId` làm metric tag chỉ để query được request cụ thể?
8. Vì sao query qua load balancer có thể trả các giá trị khác nhau cho cùng metric?
9. Khi một query trả trống, phải kiểm tra những giả thuyết nào trước khi nói “không có lỗi”?
10. Endpoint `/actuator/metrics` có thể thay thế PromQL cho dashboard theo 7 ngày không?

**Tiêu chí hoàn thành:** thao tác được với endpoint `/actuator/metrics`, lọc một hoặc nhiều tags đúng cú pháp, biết URL-encode, đọc `measurements`/`availableTags`, phân biệt Counter/Gauge/Timer, xác định đúng tên Micrometer, sử dụng PromQL khi cần thời gian hoặc aggregation toàn cụm, và bảo vệ tag cardinality.

## 17. Ghi nhớ

- Cú pháp trọng tâm là **`/actuator/metrics/{metricName}?tag=key:value`**. Nhiều điều kiện dùng **tham số `tag` lặp lại**, mang nghĩa **AND**.
- Bắt đầu bằng `/actuator/metrics` và truy vấn **không filter** để khám phá meter và `availableTags` trước khi lọc.
- `measurements` trả statistic của meter đang chọn; COUNT, VALUE, TOTAL_TIME, MAX có ý nghĩa khác nhau. Đừng diễn giải snapshot là rate hoặc percentile.
- Tên Micrometer có thể khác tên Prometheus series; `/actuator/metrics` không dùng cú pháp PromQL.
- Actuator query theo tag phục vụ **khám phá và debug một instance**. Với xu hướng nhiều phút/ngày, regex, group by, aggregation toàn cụm và alert, dùng backend time series như Prometheus.
- Chỉ gắn labels **low cardinality** vào metrics; không dùng user/request/order IDs làm tag. Dùng logs và traces để điều tra một request cụ thể.
- Bảo vệ endpoint quản trị, kiểm tra port/base path/auth và phân biệt lỗi instrumentation với lỗi scrape/exporter/sampling/propagation.

## Tài liệu tham khảo

- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Reference — MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html)
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

