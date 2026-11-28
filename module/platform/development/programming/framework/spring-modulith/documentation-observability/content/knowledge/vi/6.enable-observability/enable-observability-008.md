# Kiểm tra telemetry sau khi ứng dụng khởi động

Ứng dụng Spring Boot khởi động thành công chỉ chứng minh rằng tiến trình đã chạy đến trạng thái đủ để phục vụ các chức năng được cấu hình. Điều đó **chưa chứng minh telemetry đang được tạo, thu thập, xuất đi hoặc hiển thị trong hệ thống quan sát**. Một ứng dụng sử dụng Spring Modulith còn cần kiểm tra xem các tương tác thực tế giữa **application module** có được ghi nhận đúng hay không, và khi một sự kiện xử lý bất đồng bộ gặp lỗi thì tín hiệu vận hành có đủ để tìm ra nguyên nhân.

Bài này thuộc chương **Bật quan sát** của chủ đề `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu là kiểm tra bằng chứng theo thứ tự: **ứng dụng đang chạy → điểm quan sát hoạt động → meter/span/log được tạo → hệ thống thu thập nhận dữ liệu → tín hiệu có thể dùng để kiểm chứng ranh giới mô-đun**. Bài viết dùng Spring Boot Actuator, Micrometer, Spring Modulith, Prometheus và OTLP/trace backend làm ví dụ; bạn có thể thay backend theo hệ thống của mình.

> **Lưu ý phiên bản:** Các artifact và thuộc tính cấu hình minh họa phù hợp với một số phiên bản Spring Boot 3.x và Spring Modulith tương thích. Kiểm tra BOM, dependency tree, danh sách endpoint và tên meter thực tế trước khi áp dụng. Không có tên metric, span hoặc endpoint tích hợp nào được giả định là luôn giống nhau ở mọi phiên bản.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **khởi động thành công**, **Actuator sẵn sàng**, **metrics được ghi**, **trace được xuất** và **telemetry thực sự đến backend**.
2. Kiểm tra health, danh sách Actuator endpoint, meter và Prometheus exposition sau khi ứng dụng chạy.
3. Tạo một lời gọi kiểm soát để xác nhận telemetry có thay đổi, kể cả phép đo tùy biến ở module.
4. Kiểm tra trace từ HTTP request qua điểm gọi module và tìm trace/log có cùng ngữ cảnh.
5. Kiểm tra độc lập nhánh application event, consumer bất đồng bộ và trạng thái publication khi có registry.
6. Khoanh vùng lỗi theo từng chặng mà không nhầm sự cố instrumentation với lỗi nghiệp vụ.

## 2. Bản đồ các chặng cần kiểm chứng

Giả sử ứng dụng quản lý đơn hàng gồm ba application module:

- `order` nhận HTTP request và phát sự kiện `OrderPlaced`.
- `inventory` cung cấp API kiểm tra hàng và nhận event để giữ hàng sau commit.
- `notification` nhận event để gửi thông báo.

Một pipeline observability điển hình:

~~~mermaid
flowchart TB
    Startup["Spring Boot khởi động"] --> Bean["Spring context + instrumentation"]
    Bean --> Request["HTTP request / module call / event listener"]
    Request --> Obs["Micrometer ObservationRegistry"]
    Obs --> Meter["MeterRegistry: timer / counter"]
    Obs --> Tracer["Tracing handler: trace / span"]
    Request -. "Log do code / framework ghi" .-> Log["Application log + traceId nếu có MDC"]
    Meter --> Actuator["Actuator metrics / prometheus"]
    Actuator --> Prom["Prometheus scrape"]
    Tracer --> Export["OTLP exporter"]
    Export --> Collector["Collector tùy chọn"]
    Collector --> TraceStore["Tracing backend"]
    Log --> LogAgent["Log collector / shipper"]
    LogAgent --> LogStore["Log backend"]
    Prom --> Dashboard["Dashboard và cảnh báo"]
    TraceStore --> Dashboard
    LogStore --> Dashboard
~~~

Các chặng có thể hoạt động độc lập. Ví dụ, `/actuator/metrics` có dữ liệu nhưng Prometheus không scrape được; hoặc HTTP timer hiển thị nhưng backend tracing trống vì thiếu tracing bridge, sampling hoặc OTLP receiver.

| Cấp độ | Bằng chứng kiểm tra | Chưa thể kết luận |
| --- | --- | --- |
| **L0 — Process** | Java process và Spring Boot khởi động | Telemetry đã được bật |
| **L1 — Actuator** | Endpoint cần thiết tồn tại và truy cập được | Một yêu cầu thực tế đã được đo |
| **L2 — Instrumentation** | Meter hoặc span tăng/xuất hiện sau request | Hệ thống bên ngoài đã nhận dữ liệu |
| **L3 — Export/collect** | Prometheus target hoạt động hoặc OTLP receiver nhận span | Dashboard đã truy vấn đúng dữ liệu |
| **L4 — End-to-end** | Metric, trace, log xem được tại backend | Nghiệp vụ hay event consumer chắc chắn hoàn tất |
| **L5 — Business** | Trạng thái đơn, hàng và event được xác minh | Không còn lỗi chưa instrument |

Hãy kiểm tra theo thứ tự từ **nguồn dữ liệu** đến **đích lưu trữ**. Cách này giúp tìm đúng mắt xích bị đứt.

## 3. Chuẩn bị cấu hình có thể quan sát

Với Maven và bộ quản lý phiên bản Spring Boot/Spring Modulith phù hợp, một ứng dụng thực hành có thể sử dụng:

~~~xml
<dependencies>
    <!-- Spring Boot endpoints và tích hợp Micrometer -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Cho phép Prometheus scrape metrics -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>

    <!-- Tích hợp quan sát application module, khi phiên bản hỗ trợ -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
    </dependency>

    <!-- Ví dụ dùng Micrometer Tracing qua OpenTelemetry -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **tập dependency minh họa**, không phải danh sách bắt buộc cho mọi dự án. Starter có thể kéo theo một số artifact; xem dependency tree để tránh khai báo trùng. Tracing exporter chỉ hữu ích khi có OTLP receiver/backend đang chạy và được cấu hình.

Ví dụ `application.yml` **chỉ dành cho môi trường local**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Ý nghĩa:

- `metrics` hỗ trợ tra tên và giá trị meter qua Actuator.
- `prometheus` xuất dữ liệu với định dạng Prometheus khi registry liên quan được đăng ký.
- `probability: 1.0` giảm khả năng mất trace do sampling khi **thực hành**; không nên mặc định dùng cho production.
- `management.otlp.tracing.endpoint` trỏ tới OTLP/HTTP trace receiver **nếu phiên bản Spring Boot đang dùng hỗ trợ cấu hình này**. Chạy ứng dụng với địa chỉ giả nhưng không có collector sẽ không thể xem trace ở backend.

Nếu ứng dụng dùng cổng HTTP khác hoặc có `management.server.port` hay `management.endpoints.web.base-path` khác mặc định, thay đúng cổng và đường dẫn trong các lệnh kiểm tra. Actuator endpoint thường không được expose hết qua HTTP; đó là hành vi có chủ đích để giới hạn thông tin quản trị.

**An toàn khi triển khai:** endpoint quản trị cần được bảo vệ bằng xác thực, phân quyền hoặc giới hạn mạng; chỉ expose những endpoint thật sự dùng. Việc mở cho local không có nghĩa nên mở công khai trên Internet.

## 4. Kiểm tra ngay sau khi ứng dụng khởi động

### Bước 1 — Xác định tiến trình và endpoint

Đọc log khởi động để biết ứng dụng có hoàn tất quá trình startup và đang nghe ở cổng nào. Sau đó dùng HTTP request thật:

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
~~~

Trên Windows PowerShell, có thể dùng `curl.exe` thay cho `curl` để tránh khác biệt với alias của PowerShell:

~~~powershell
curl.exe -i http://localhost:8080/actuator
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/metrics
~~~

Đường dẫn `/actuator` là discovery endpoint nếu endpoint links đang được cung cấp. Không thấy links chưa chắc Actuator hỏng: có thể bị bảo vệ hoặc cấu hình. Hãy kiểm tra trực tiếp endpoint đã expose và cấu hình của ứng dụng.

### Bước 2 — Đọc mã trạng thái thay vì chỉ xem nội dung

| Kết quả | Diễn giải ban đầu | Kiểm tra tiếp |
| --- | --- | --- |
| `200 OK` ở `/actuator/health` | Health endpoint có phản hồi thành công | Xác nhận trạng thái `UP` và thành phần health cần thiết |
| `503 Service Unavailable` | Health có thể ở trạng thái `DOWN` hoặc `OUT_OF_SERVICE` | Xem health contributors, dependency như database/broker |
| `404 Not Found` | Sai đường dẫn/cổng hoặc endpoint chưa tồn tại/chưa expose | Kiểm tra dependency, web exposure, base path |
| `401 Unauthorized` | Chưa xác thực | Cấp credential/token đúng cho phép kiểm tra |
| `403 Forbidden` | Đã đến endpoint nhưng không đủ quyền theo chính sách | Kiểm tra phân quyền và chính sách bảo mật |
| Connection refused/timeout | Không kết nối được tới host/cổng | Kiểm tra process, cổng, container network, proxy/firewall |

**Health không phải telemetry:** `UP` không xác nhận rằng tracing exporter gửi thành công hoặc Prometheus target đang scrape. Nó chỉ phản ánh những health contributors đã cấu hình và có thể có phạm vi hẹp hơn khả năng quan sát vận hành.

### Bước 3 — Có thấy thông tin Spring Modulith không?

Nếu phiên bản và dependency Spring Modulith có hỗ trợ endpoint Actuator `modulith` và đã expose endpoint đó, có thể kiểm tra:

~~~bash
curl -i http://localhost:8080/actuator/modulith
~~~

Endpoint này dùng để xem **thông tin cấu trúc application module** theo khả năng của phiên bản. Nó không phải endpoint thu thập Prometheus metrics và không phải OTLP receiver. Nếu trả `404`, hãy kiểm tra sự tồn tại/đăng ký/exposure của endpoint trước khi suy luận về ứng dụng. Không có endpoint `modulith` **không có nghĩa** source code không được Spring Modulith mô hình hóa.

Module graph cũng có thể được kiểm tra trong test bằng `ApplicationModules.of(...).verify()` và công cụ tạo tài liệu `Documenter`. Đó là kiểm tra kiến trúc **tĩnh**, bổ sung cho bước quan sát runtime.

## 5. Kiểm tra metrics: phải có thay đổi sau một lời gọi

Ngay sau khi khởi động, nhiều meter đã có sẵn nhưng một số meter dành cho thao tác nghiệp vụ **chỉ xuất hiện sau khi thao tác được thực thi**. Vì thế cần có một request kiểm soát và biết sẽ tìm tín hiệu nào.

### Bước 4 — Chụp trạng thái trước khi tạo traffic

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/http.server.requests
~~~

Trong ứng dụng Spring MVC được cấu hình với Micrometer, thường có các HTTP server metrics; tuy nhiên tên meter và thuộc tính thực tế có thể khác theo phiên bản/instrumentation. Kiểm tra danh sách tên ở `/actuator/metrics` trước. Việc meter không tồn tại khi **chưa có request** không đủ để kết luận lỗi cấu hình.

### Bước 5 — Gửi request có thể lặp lại

Ưu tiên một API thực tế **được phép gọi trong môi trường test**. Nếu dự án không có API ổn định, có thể dựng ví dụ tối thiểu với hai application module:

~~~java
// com.example.shop.inventory.InventoryDiagnostics
package com.example.shop.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiagnostics {

    private final ObservationRegistry observations;

    public InventoryDiagnostics(ObservationRegistry observations) {
        this.observations = observations;
    }

    public String check() {
        return Observation.createNotStarted("shop.inventory.check", observations)
                .lowCardinalityKeyValue("application.module", "inventory")
                .observe(() -> "available");
    }
}
~~~

~~~java
// com.example.shop.order.OrderDiagnosticsController
package com.example.shop.order;

import com.example.shop.inventory.InventoryDiagnostics;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderDiagnosticsController {

    private final InventoryDiagnostics inventory;

    public OrderDiagnosticsController(InventoryDiagnostics inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/demo/module-check")
    public String check() {
        return inventory.check();
    }
}
~~~

Ví dụ này giả định ứng dụng có Spring MVC và cách tổ chức package cho phép `order` gọi API công khai của `inventory`. Nó minh họa một observation **do ứng dụng tự đặt tên**. Không giả định Spring Modulith tự tạo meter mang tên `shop.inventory.check` nếu bạn không viết mã trên.

Chỉ đưa endpoint chẩn đoán này vào **môi trường local/test**, không mở vô điều kiện trong production. Sau khi chạy ứng dụng với mã ví dụ, gọi nhiều lần:

~~~bash
curl -i http://localhost:8080/demo/module-check
curl -i http://localhost:8080/demo/module-check
curl -i http://localhost:8080/demo/module-check
~~~

Kỳ vọng HTTP trả `200` và nội dung `available`. Nếu không có endpoint ví dụ trong dự án, hãy gọi endpoint nghiệp vụ thực tế và tìm meter đã xác nhận tương ứng.

### Bước 6 — Đối chiếu meter trước và sau request

~~~bash
curl -i http://localhost:8080/actuator/metrics/shop.inventory.check
curl -i http://localhost:8080/actuator/prometheus
~~~

Khi application context đã đăng ký meter observation handler phù hợp, bạn có thể thấy meter cho observation `shop.inventory.check` sau khi gọi endpoint. Kiểm tra số lượt và tổng thời lượng thực tế; đừng mặc định định dạng JSON hoặc tên thống kê luôn giống nhau. Một observation chỉ thành metric nếu handler/registry cần thiết đang hoạt động.

Endpoint `/actuator/prometheus` có thể cung cấp các series có tên đã được chuẩn hóa từ meter. Chẳng hạn timer có thể tạo các series dạng `*_seconds_count` và `*_seconds_sum`; **tên cụ thể phải lấy từ output**, không hardcode trên giả định. Muốn tính p95 từ Prometheus cần histogram bucket đã được cấu hình, chứ không chỉ timer thông thường.

> **Bài học quan trọng:** meter tăng sau request là bằng chứng **instrumentation đã được thực thi trong ứng dụng**. Nó chưa chứng minh Prometheus đã scrape thành công.

## 6. Kiểm tra Prometheus: từ exposition đến time series

Với registry Prometheus, luồng thường là:

~~~text
MeterRegistry trong ứng dụng
     |
     v
/actuator/prometheus    <--- HTTP GET định kỳ ---    Prometheus
                                                       |
                                                       v
                                                Time series / query
~~~

Prometheus thường **chủ động scrape (pull)**; nó không chờ ứng dụng chủ động đẩy dữ liệu vào URL scrape. Kiểm tra ba tầng:

1. **Ứng dụng:** `/actuator/prometheus` phản hồi và có metric mong muốn.
2. **Prometheus target:** cấu hình host/cổng/path đúng, target được scrape thành công (thường thể hiện `UP` ở trang target).
3. **Truy vấn:** query theo tên series **đã xuất thật**; quan sát giá trị thay đổi khi tiếp tục gửi traffic.

Ví dụ truy vấn khi bạn đã xác minh meter thực tế được xuất thành `shop_inventory_check_seconds_count`:

~~~promql
sum(rate(shop_inventory_check_seconds_count[5m]))
~~~

Tên series trong ví dụ **không phải tên mặc định mà Spring Modulith cam kết tạo**; nó minh họa cách dùng một counter của timer. Nếu metric chưa có dữ liệu liên tục trong đủ cửa sổ thời gian, `rate(...[5m])` có thể chưa trả kết quả như kỳ vọng. Để kiểm tra sơ bộ, có thể query trực tiếp số lần ghi nhận hoặc xem output tại endpoint.

Nếu Prometheus hiển thị `UP` nhưng không thấy series vừa đo, xem thời điểm scrape, endpoint path, chính sách relabel, naming convention và nhãn; tránh kết luận metric không tồn tại chỉ từ một câu query sai.

## 7. Kiểm tra traces: từ HTTP request đến backend

**Tracing** bổ sung một góc nhìn khác metrics: đường đi của **một lần thực thi**. Khi các điểm đo được instrument, bạn có thể thấy HTTP span, span nghiệp vụ và span mô tả tương tác module tùy phiên bản/tích hợp.

### Bước 7 — Biết rõ chặng xuất trace

~~~mermaid
sequenceDiagram
    participant Client
    participant Boot as Spring Boot
    participant Obs as Micrometer Observation
    participant Tracer as Tracer / OTLP exporter
    participant Col as OTel Collector
    participant Store as Trace backend

    Client->>Boot: HTTP /demo/module-check
    Boot->>Obs: Start HTTP observation
    Boot->>Obs: Start shop.inventory.check
    Obs->>Tracer: Tạo / kết thúc span nếu tracing handler hoạt động
    Boot-->>Client: 200 available
    Tracer-->>Col: Export spans, có thể theo batch
    Col-->>Store: Forward spans
~~~

Collector là thành phần trung gian tùy chọn: exporter có thể gửi trực tiếp đến backend hỗ trợ OTLP. Kết thúc request **không đồng nghĩa** backend đã nhận span vì còn quá trình gom batch, network, collector và lưu trữ.

### Bước 8 — Tìm trace vừa tạo

Trong backend tracing đang dùng:

1. Chọn đúng service identity của ứng dụng (chẳng hạn `shop-application`); **đừng mặc định mỗi application module là một service riêng**.
2. Chọn khoảng thời gian chứa những request kiểm soát, tính đến trễ export.
3. Tìm HTTP request tới `/demo/module-check` và span nghiệp vụ `shop.inventory.check` nếu tracing handler tạo span cho observation này.
4. Kiểm tra `traceId`, thời gian span, các thuộc tính được instrument và quan hệ parent–child nếu context được duy trì.

Ví dụ dấu vết mang tính diễn giải:

~~~text
service.name = shop-application
traceId = e5b0... (minh họa)

HTTP GET /demo/module-check        25 ms
  └─ shop.inventory.check          11 ms
~~~

**Không cam kết** span và nhãn sẽ xuất đúng như trên: HTTP instrumentation, Spring Modulith Insight và mã ứng dụng có thể đặt tên/attributes khác nhau. Việc `service.name` vẫn là tên ứng dụng là điều bình thường trong modular monolith.

Với các tương tác module tự động được Spring Modulith quan sát, hãy đối chiếu **module graph** với những span thực sự có, nhưng nhớ rằng:

- Graph thể hiện **phụ thuộc tĩnh**; trace thể hiện **một phần đường đi đã chạy và được đo**.
- Lời gọi không đi qua điểm instrumentation, gọi nội bộ trong bean hoặc đoạn code ngoài phạm vi module detection có thể không sinh span tương ứng.
- **Sampling** có thể loại bỏ trace. Với `probability: 1.0` trong local, bạn giảm một nguyên nhân mất trace nhưng vẫn cần kiểm tra exporter/backend.
- Không thấy span của module **không đủ chứng minh** module ấy chưa chạy.

### Bước 9 — Kiểm tra exporter/collector

Nếu backend trống, đi ngược từ cuối pipeline:

| Điểm kiểm tra | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Tracing bridge | Application có tạo spans không? | Dependency, cấu hình handler và tín hiệu tracing ở ứng dụng |
| Sampling | Request có được lấy mẫu không? | Cấu hình sampling và trạng thái trace |
| OTLP exporter | Có gửi đúng protocol/host/port không? | Log lỗi kết nối/export, cấu hình endpoint |
| OTLP receiver | Collector/backend có lắng nghe không? | Cấu hình receiver và telemetry nội bộ/log |
| Collector pipeline | Receiver có nối tới processor/exporter không? | Logs, trạng thái, metric receiver/exporter |
| Trace backend | Dữ liệu đã lưu và query đúng service/thời gian chưa? | Trace search hoặc truy vấn theo trace ID |

**Phân biệt protocol và port:** OTLP/gRPC thường dùng cổng `4317`, OTLP/HTTP thường dùng `4318`, nhưng không phải deployment nào cũng dùng cổng mặc định. URL `http://localhost:4318/v1/traces` chỉ có ý nghĩa nếu ứng dụng có thể truy cập đúng receiver đó; với Docker/Kubernetes, `localhost` có thể chỉ container hiện tại.

## 8. Kiểm tra logs và tương quan với trace

Logs trả lời những câu hỏi mà metric tổng hợp không thể trả lời, chẳng hạn consumer của một event cụ thể đã gặp exception gì. Khi Micrometer Tracing, MDC và log pattern được cấu hình phù hợp, log có thể chứa `traceId`/`spanId`:

~~~text
INFO traceId=e5b0... spanId=a93c... module=order
     operation=placeOrder outcome=success
WARN traceId=e5b0... spanId=b5d2... module=inventory
     operation=reserve outcome=retryable-failure
~~~

Đây là ví dụ về format log mong muốn, không phải output mặc định bắt buộc của Spring Modulith. Để kiểm tra:

1. Tìm log ứng dụng ngay sau request thử nghiệm.
2. Xác định trong log có trường trace ID không; nếu không, kiểm tra cấu hình MDC/structured logging.
3. Dùng cùng trace ID để tìm trace trong backend và các log liên quan.
4. Nếu application log có trace ID nhưng log backend không có, kiểm tra log shipper/collector đã giữ các trường đó hay chưa.

Không đưa order ID thực tế, access token, email hoặc dữ liệu nhạy cảm vào metrics tags. Nếu dùng business correlation ID cho log, áp dụng chính sách dữ liệu phù hợp. `traceId` hỗ trợ liên kết vận hành; nó không thay thế idempotency key của nghiệp vụ.

## 9. Kiểm tra telemetry của event và listener bất đồng bộ

Trong một hệ thống mô-đun, lỗi quan trọng có thể xuất hiện **sau khi request HTTP đã trả về**. Ví dụ `order` lưu đơn, phát `OrderPlaced` rồi `inventory` nhận sự kiện sau commit để giữ hàng.

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order
    participant Inv as inventory listener
    participant Metrics as Metrics / Tracing
    User->>Order: POST /orders
    Order->>Order: Lưu đơn, publish OrderPlaced
    Order-->>User: 201 Created
    Note over Order,Inv: Listener có thể chạy bất đồng bộ sau commit
    Order-->>Inv: OrderPlaced
    Inv->>Inv: Giữ hàng hoặc gặp exception
    Inv->>Metrics: Đo lượt chạy, thời gian và lỗi
~~~

Ở đây `201 Created` chỉ nói về kết quả trả về của endpoint theo hợp đồng ứng dụng; **không tự chứng minh** consumer đã hoàn tất. Với `@ApplicationModuleListener` trong Spring Modulith, việc xử lý sau commit và bất đồng bộ cần được xét theo phiên bản và cấu hình listener thực tế.

### Những tín hiệu cần kiểm tra

| Tín hiệu | Cần kiểm tra | Giới hạn |
| --- | --- | --- |
| **Log phát sự kiện** | Order đã phát event tại code path dự kiến chưa? | Log riêng không chứng minh việc commit hay xử lý thành công |
| **Publication registry**, nếu cấu hình | Publication còn chờ/hoàn tất hoặc cần xử lý lại? | Không tự bảo đảm idempotency nghiệp vụ |
| **Metric consumer** | Số lượt chạy, lỗi, độ trễ theo module và loại event | Retry có thể làm số lượt lớn hơn số event duy nhất |
| **Trace/span listener** | Listener có được instrument và liên kết với request gốc? | Nhánh async có thể không tạo cây span liên tục |
| **Trạng thái nghiệp vụ** | Đơn hàng và tồn kho có đúng sau xử lý? | Cần nguồn dữ liệu đáng tin cậy ngoài telemetry |

Spring Modulith có **Event Publication Registry** khi được cấu hình với cơ chế lưu phù hợp; registry này theo dõi lifecycle publication. Nó **không phải Collector** và không tự tạo mọi event metric. Nếu muốn có chỉ số tùy chỉnh theo consumer, có thể thêm `Timer`/`Counter` hoặc `Observation` quanh listener.

Ví dụ điểm đếm lượt xử lý consumer:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

class EventOutcomeMetrics {
    private final MeterRegistry meters;

    EventOutcomeMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    void recordInventoryResult(boolean success) {
        Counter.builder("shop.event.consumer.processed")
                .tag("consumer.module", "inventory")
                .tag("event.type", "OrderPlaced")
                .tag("outcome", success ? "success" : "failure")
                .register(meters)
                .increment();
    }
}
~~~

Trong listener thật, gọi phương thức này **đúng một lần cho mỗi lượt thực thi** trong nhánh thành công/thất bại, bảo đảm exception vẫn được ném hoặc xử lý theo chính sách nghiệp vụ. Tên metric ở trên là **do ví dụ tự đặt**; không phải tên meter tích hợp được Spring Modulith bảo đảm sinh. Số lần xử lý listener **không phải** số event duy nhất khi có retry.

### Kiểm tra context propagation

Khi listener chạy ở thread khác, tracing context có thể không được truyền từ publisher sang listener. Dấu hiệu:

~~~text
HTTP /orders    traceId=A
order publish   traceId=A
inventory event traceId=B   <-- Có thể bị tách ngữ cảnh hoặc tạo trace mới
~~~

Nếu kỳ vọng liên kết trace, hãy kiểm tra executor thực sự được listener sử dụng, cơ chế capture/restore context và instrumentation phù hợp. Ở những phiên bản Spring Framework/Micrometer hỗ trợ, `ContextPropagatingTaskDecorator` có thể giúp truyền context qua tác vụ của executor. Với message broker, cần cơ chế truyền và đọc tracing headers tương ứng.

**Không đồng nhất context với transaction:** giữ trace ID không làm listener tham gia cùng transaction đã commit, cũng không bảo đảm event chỉ được xử lý một lần. Với tác vụ async, trace link hoặc correlation/event ID có thể phù hợp hơn là bắt buộc mọi span nằm dưới một span HTTP đã kết thúc.

## 10. Kịch bản đối chiếu: telemetry đầy đủ nhưng nghiệp vụ vẫn lỗi

Giả sử dashboard thể hiện:

- HTTP response thành công và p95 độ trễ thấp.
- Prometheus ghi nhận counter lỗi của `inventory` tăng lên.
- Tracing backend có HTTP span nhưng không có span listener cùng trace.
- Publication registry (nếu có) cho biết một số publication chưa hoàn tất.

Kết luận hợp lý ban đầu: **vấn đề đáng kiểm tra ở xử lý event sau khi HTTP hoàn tất**. Đây chưa phải bằng chứng duy nhất xác định nguyên nhân. Cần:

1. Xác minh `OrderPlaced` thực sự được phát sau các bước transaction mong đợi.
2. Kiểm tra exception của listener qua log; đối chiếu metric failure.
3. Kiểm tra các lần retry, idempotency và publication status nếu có registry.
4. Kiểm tra context propagation để hiểu vì sao trace listener không nối với HTTP.
5. Đối chiếu trạng thái đơn và kho để xác nhận kết quả nghiệp vụ.

Không nên sửa module graph chỉ vì trace thiếu một span. Trước tiên hãy phân biệt **sự cố vận hành** với **thiếu instrumentation hoặc thiếu telemetry**.

## 11. Bảng tra lỗi theo vị trí trong pipeline

| Triệu chứng sau startup | Chặng nghi ngờ | Cách kiểm chứng cụ thể |
| --- | --- | --- |
| `/actuator/health` không truy cập được | Process/port/network/security | Xem log startup, cổng, URL, HTTP status |
| Health `UP` nhưng `/actuator/metrics` là `404` | Actuator endpoint hoặc exposure | Kiểm tra dependency, base path, cấu hình expose |
| `metrics` có nhưng meter nghiệp vụ chưa có | Điểm instrument hoặc chưa chạy thao tác | Tạo traffic rồi query đúng tên meter |
| Meter có nhưng `/actuator/prometheus` là `404` | Prometheus registry hoặc exposure | Kiểm tra registry, endpoint và quyền truy cập |
| Prometheus endpoint có dữ liệu nhưng target `DOWN` | Scrape/network/auth/TLS | Xem target, host/cổng/path và lỗi kết nối |
| Target `UP` nhưng query rỗng | Tên series, label, scrape interval | Xem series thật, chỉnh PromQL và thời gian |
| Có metric HTTP nhưng backend trace trống | Tracing bridge, sampler, OTLP exporter hoặc receiver | Kiểm tra dependency, sampling, exporter logs, collector |
| Chỉ có HTTP span, không có span module | Tích hợp Modulith/điểm gọi/sampling | Kiểm tra module detection và phạm vi instrumentation |
| Trace xuất hiện trễ | Batch/export/storage | Chờ đủ chu kỳ hợp lý và xem exporter/backend |
| Listener có log nhưng khác trace ID | Context propagation/async | Kiểm tra executor, broker headers, correlation |
| Listener lỗi nhưng HTTP vẫn trả thành công | Xử lý sau commit/bất đồng bộ | Xem consumer, publication status và dữ liệu nghiệp vụ |
| Metric tạo quá nhiều time series | High-cardinality tags | Giới hạn các giá trị nhãn; chuyển ID riêng sang log/trace có kiểm soát |

Đối với mỗi lỗi, chọn **điểm kiểm chứng gần nhất với nguồn**: đừng bắt đầu bằng dashboard nếu bạn chưa xác nhận ứng dụng thực sự phát ra meter/span tương ứng.

## 12. Quy trình kiểm chứng nhanh có thể lặp lại

Đây là trình tự có thể dùng khi bật observability ở môi trường phát triển hoặc staging:

~~~mermaid
flowchart TD
    A["Ứng dụng đã khởi động?"] --> B{"Health / Actuator truy cập được?"}
    B -->|"Không"| X["Kiểm tra process, port, security, exposure"]
    B -->|"Có"| C["Kích hoạt request có thể lặp lại"]
    C --> D{"Meter tăng sau request?"}
    D -->|"Không"| E["Kiểm tra instrumentation và handler"]
    D -->|"Có"| F{"Prometheus scrape được?"}
    F -->|"Không"| G["Kiểm tra registry, endpoint và target"]
    F -->|"Có"| H{"Trace đến backend?"}
    H -->|"Không"| I["Kiểm tra tracing, sampling, OTLP, Collector"]
    H -->|"Có"| J["Đối chiếu module interactions / logs"]
    J --> K["Kích hoạt event và kiểm tra consumer"]
    K --> L["Đối chiếu kết quả nghiệp vụ"]
~~~

**Các tiêu chí đạt** nên được ghi thành bằng chứng, ví dụ:

| Hạng mục | Bằng chứng tối thiểu | Trạng thái ghi nhận |
| --- | --- | --- |
| Ứng dụng | Startup log, `/actuator/health` và HTTP response | PASS/FAIL |
| Module graph | Danh sách module/API đúng phạm vi dự kiến | PASS/FAIL |
| Meter | Tên meter và số liệu thay đổi sau request | PASS/FAIL |
| Prometheus | Target scrape được, series có dữ liệu | PASS/FAIL |
| Trace | Trace ID và spans cho request thử nghiệm | PASS/FAIL |
| Log correlation | Có thể nối log với trace/correlation ID | PASS/FAIL |
| Event listener | Thấy lượt xử lý, lỗi và trạng thái sau commit | PASS/FAIL |
| Nghiệp vụ | Trạng thái cuối phù hợp với quy tắc nghiệp vụ | PASS/FAIL |

Nếu chưa triển khai Prometheus hoặc tracing backend, ghi rõ **NOT CONFIGURED/NOT VERIFIED** tại chặng đó thay vì đánh dấu PASS chỉ dựa vào Actuator. Điều này giúp phân biệt năng lực đã kiểm chứng với dự định cấu hình.

## 13. Bài thực hành: chạy thử và cố ý làm hỏng một chặng

Hãy làm trên ứng dụng Spring Boot có ít nhất hai application module và một tuyến API có thể gọi trong môi trường test.

1. **Khởi động và xác minh nền tảng.** Ghi cổng HTTP, trạng thái health, danh sách endpoint được expose.
2. **Gọi API có kiểm soát.** Ghi thời điểm gọi, status và một ID thử nghiệm không nhạy cảm; thực hiện ít nhất ba lần để dễ so thay đổi meter.
3. **Quan sát meter.** Lấy tên metric từ Actuator, đối chiếu số lượt và thời lượng trước/sau traffic. Giải thích vì sao timer xuất hiện muộn hoặc tên Prometheus khác tên Micrometer.
4. **Quan sát Prometheus.** Kiểm tra endpoint exposition, trạng thái target, query một series thật; phân biệt lỗi scrape với lỗi thiếu instrumentation.
5. **Quan sát trace.** Tìm request trong tracing backend, ghi service name, trace ID, span duration và những module interactions được thể hiện. Ghi rõ phần nào chưa instrument hoặc không xuất hiện.
6. **Quan sát event.** Phát một event bằng luồng nghiệp vụ; kiểm tra listener, lỗi xử lý và correlation giữa request gốc với consumer. Nếu có publication registry, kiểm tra trạng thái publication.
7. **Thử lỗi telemetry có kiểm soát.** Tạm trỏ exporter đến OTLP receiver không hoạt động hoặc tạm tắt scrape tại môi trường thử nghiệm. Chứng minh request nghiệp vụ có thể vẫn xử lý trong khi dữ liệu backend biến mất; khôi phục cấu hình và kiểm tra lại.
8. **Thử lỗi nghiệp vụ có kiểm soát.** Cho listener ném exception trong test và xem metric/log/trạng thái publication thay đổi ra sao; đối chiếu trạng thái nghiệp vụ cuối.

Ghi kết quả theo mẫu:

| Thao tác | Tín hiệu thấy ở ứng dụng | Tín hiệu thấy ở backend | Điều kết luận được | Phần chưa xác minh |
| --- | --- | --- | --- | --- |
| HTTP request | … | … | … | … |
| Module API call | … | … | … | … |
| Event consumer thành công | … | … | … | … |
| Event consumer thất bại | … | … | … | … |
| Mất kết nối OTLP | … | … | … | … |

### Câu hỏi tự kiểm tra

1. Vì sao `/actuator/health` trả `UP` nhưng trace backend vẫn có thể trống?
2. Thấy `/actuator/metrics` có meter mới đã đủ kết luận Prometheus thu thập thành công chưa?
3. Sau một request, meter nghiệp vụ vẫn chưa có. Những nguyên nhân nào có thể xảy ra ngoài việc ứng dụng chưa bật Actuator?
4. Vì sao `service.name` của `order` và `inventory` có thể giống nhau trong modular monolith?
5. Nếu HTTP request kết thúc trước listener, cần thêm tín hiệu nào để đo thành công/thất bại của consumer?
6. Tại sao không nên dùng `orderId` hoặc `traceId` làm tag metric?
7. Khi trace đứt ở listener bất đồng bộ, cần kiểm tra gì trước khi kết luận listener không chạy?
8. Hãy phân biệt một lỗi **không tạo span**, một lỗi **không export span** và một lỗi **query sai backend**.

## 14. Tổng kết

Sau khi ứng dụng Spring Boot dùng Spring Modulith khởi động, công việc bật quan sát chỉ hoàn tất khi **có thể tạo traffic, nhìn thấy tín hiệu tại nguồn, xác minh được đường thu thập và đối chiếu với hành vi nghiệp vụ**. Bắt đầu từ Actuator/health để biết trạng thái nền tảng, dùng Micrometer metrics để thấy số đo thay đổi, Prometheus để kiểm tra scraping, tracing/OTLP để theo đường đi của request, và logs cùng trạng thái event để giải thích các lỗi bất đồng bộ.

**Module graph** cho biết ranh giới application module được định nghĩa thế nào; **telemetry** cho biết những gì đã chạy và được ghi nhận; **dữ liệu nghiệp vụ** xác nhận kết quả cuối. Kiểm chứng từng chặng theo thứ tự giúp bạn tránh kết luận sai khi thiếu span, thiếu metric hoặc một consumer gặp lỗi sau khi HTTP đã trả thành công.
