# Phân biệt span module với span HTTP

Trong một ứng dụng Spring Boot được tổ chức bằng **Spring Modulith**, một HTTP request có thể đi qua nhiều **application module** trước khi trả kết quả. Tracing giúp quan sát đường đi ấy bằng các **span**. Tuy nhiên, một span HTTP và một span gắn với module trả lời **hai câu hỏi khác nhau**: *“yêu cầu từ bên ngoài được phục vụ như thế nào?”* và *“phần trách nhiệm nào bên trong kiến trúc mô-đun đã tham gia xử lý?”*

Ví dụ, yêu cầu `GET /demo/orders/A-42/availability` đi vào module `order` rồi gọi API công khai của module `inventory`. Một trace có thể chứa HTTP server span bao trùm request và các module spans (nếu phần tích hợp Spring Modulith Insight đã instrument được những tương tác đó). Dù chúng cùng trace, **thời lượng, tên, ý nghĩa và phạm vi của mỗi span khác nhau**. Việc hiểu đúng giúp tìm điểm nghẽn, tránh đếm thời gian trùng và kiểm chứng ranh giới module khi ứng dụng chạy.

Bài học thuộc chương **Module spans** của chủ đề `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`: dùng Spring Modulith tạo tài liệu ranh giới application module, kết hợp Actuator, metrics, tracing và context propagation để quan sát hành vi hệ thống. Trọng tâm là phân biệt **span HTTP** với **span module**; các ví dụ về sự kiện bất đồng bộ được dùng để làm rõ giới hạn của mỗi loại.

> **Phạm vi phiên bản:** Spring Boot, Spring Modulith và Micrometer có thay đổi về artifact, tên span, attributes và điểm instrumentation giữa các phiên bản. Những tên span/attribute trong sơ đồ chỉ mang tính minh họa. Khi áp dụng, cần kiểm tra dependency tree, phiên bản tương thích, cấu hình tracing và dữ liệu thực tế trong backend.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **trace**, **span**, **parent span**, `traceId`, `spanId` và ngữ cảnh tracing.
2. So sánh HTTP span và module span về điểm bắt đầu, điểm kết thúc, phạm vi, ý nghĩa và nguồn instrumentation.
3. Đọc một trace có HTTP span bao ngoài các module spans, tránh cộng thời gian các span lồng nhau.
4. Phân biệt **module graph tĩnh** với **module spans được ghi khi runtime**.
5. Hiểu vì sao có thể có module span **không có HTTP span**, hoặc HTTP span mà **không thấy module span**.
6. Kiểm tra sự khác biệt trong Spring Boot/Modulith với Actuator, Micrometer, tracing exporter và backend.
7. Phân tích ảnh hưởng của async event, sampling và context propagation lên quan hệ giữa các spans.

## 2. Nền tảng: trace không phải một span đơn lẻ

Trong tracing, một **trace** là tập hợp các đoạn công việc được liên kết theo ngữ cảnh; mỗi đoạn được ghi là một **span**. Một span thường có:

| Thành phần | Vai trò |
| --- | --- |
| `traceId` | Nhóm các span thuộc cùng một trace hoặc ngữ cảnh trace được truyền. |
| `spanId` | Định danh của một span cụ thể. |
| `parentSpanId` (nếu có) | Liên hệ span hiện tại với span cha, tạo cây thực thi khi phù hợp. |
| Tên / operation | Mô tả thao tác được instrument. |
| Start time, end time, duration | Cho biết khoảng thời gian mà instrumentation bao quanh. |
| Attributes | Các thông tin bổ sung như phương thức HTTP, route hoặc module nếu integration cung cấp. |
| Status / error | Cách ghi trạng thái và lỗi theo tracing integration. |
| Resource, ví dụ `service.name` | Định danh dịch vụ hoặc tiến trình tạo telemetry. |

Khi một request đi qua nhiều đoạn công việc, các span có thể là **cha–con** hoặc cùng cấp. Thời gian của span cha có thể **bao gồm** thời gian của các span con, nên không được cộng duration của toàn bộ cây để lấy latency của request.

~~~mermaid
flowchart TB
    T["Trace ID = T1"]
    T --> H["HTTP server span: GET /demo/orders/{sku}/availability"]
    H --> O["Module span: order"]
    O --> I["Module span: inventory"]
    H --> L["Khác: serialization / middleware / ..."]
~~~

Sơ đồ là một **cây span giả định** nếu tất cả các điểm nêu trên được instrument và context được duy trì. Một trace thật có thể không có span `order`, `inventory` hoặc `serialization` dù code tương ứng chạy; việc có bao nhiêu span phụ thuộc instrumentation.

## 3. Span HTTP là gì?

**HTTP server span** là span được tạo tại phía ứng dụng **nhận HTTP request**. Trong Spring Boot, instrumentation HTTP của Spring MVC/WebFlux và hệ sinh thái Micrometer có thể tạo observation cho request, rồi chuyển thành span khi đã cấu hình tracing handler tương ứng.

Một HTTP server span thường mô tả:

- **Điểm vào:** request HTTP đến server và được instrumentation nhận diện.
- **Điểm kết thúc:** quá trình xử lý request hoàn tất theo phạm vi mà HTTP instrumentation đo.
- **Tên/attributes:** thường thể hiện method, route đã chuẩn hóa, status code, server name hoặc thông tin HTTP phù hợp với phiên bản.
- **Latency:** thời gian xử lý request ở phạm vi HTTP server, bao gồm nhiều bước bên trong như controller, service, repository, middleware hoặc chờ đợi.
- **Trạng thái:** mã trả lời HTTP và tín hiệu lỗi theo cách instrument. `200`/`201` không bảo đảm mọi tác vụ bất đồng bộ sau response đã thành công.

Ví dụ về mặt ý nghĩa:

~~~text
Span: HTTP GET /demo/orders/{sku}/availability
Span kind: SERVER
HTTP method: GET
HTTP status: 200
Duration: 145 ms
~~~

Đây là biểu diễn minh họa. Tên và key attributes thực tế của OpenTelemetry/Micrometer có thể khác theo semantic conventions, phiên bản và HTTP instrumentation.

**HTTP span hiểu giao thức và endpoint**, nhưng bản thân nó không nhất thiết biết các application module mà request đã đi qua. Nếu một request chậm 145 ms, chỉ nhìn HTTP span vẫn chưa biết chậm ở `order`, `inventory` hay thao tác bên ngoài.

### Không chỉ có server span

Khi ứng dụng gọi một dịch vụ ngoài qua HTTP client và client instrumentation hoạt động, tracing có thể tạo **HTTP client span** khác với HTTP server span ở phía nhận. Cả hai đều là spans liên quan đến giao thức HTTP; chúng vẫn **không phải module spans**.

Trong modular monolith, lời gọi Java từ `order` sang `inventory` thường **không phát sinh HTTP client span**, vì cả hai module có thể nằm trong **cùng tiến trình Spring Boot**. Đây là lý do module-level instrumentation hữu ích.

## 4. Span module là gì?

Một **module span** trong phạm vi bài này là span dùng để thể hiện một đoạn thực thi gắn với **application module** hoặc một tương tác qua ranh giới module, khi một cơ chế instrumentation (chẳng hạn tính năng observability/Insight của Spring Modulith ở phiên bản hỗ trợ) tạo ra thông tin ấy.

Module span có thể giúp trả lời:

- Request đã đi vào hoặc tương tác với module `inventory` ở bước nào?
- Đoạn công việc được instrument của module kéo dài bao lâu?
- Lỗi có xuất hiện trong phạm vi thao tác gắn với module không?
- Hệ thống đang thực hiện tương tác module như ranh giới mong đợi hay có luồng lạ cần điều tra?

Ví dụ diễn giải một module span:

~~~text
Span: [module interaction] inventory
Logical module: inventory
Operation: inventory.checkAvailability
Duration: 28 ms
~~~

**Các tên và trường trên do ví dụ đặt để dễ đọc**, không khẳng định Spring Modulith luôn phát sinh chính xác những span attributes này. Hãy xem backend thực tế để biết span name và key attributes của integration đang dùng.

Spring Modulith có mô hình **application module** xuất phát từ base package và cấu trúc ứng dụng. Phần tích hợp observability có thể dựa trên mô hình đó để nhận diện ranh giới tương tác. Khả năng tạo module spans phụ thuộc việc bật đúng integration, phương thức được gọi nằm trong phạm vi instrument và cách lời gọi diễn ra (ví dụ có đi qua cơ chế proxy/interceptor hay không).

**Module span biểu diễn một phần công việc logic bên trong kiến trúc**, không khẳng định có cuộc gọi mạng hoặc một microservice riêng. Nhiều application module có thể cùng sử dụng `service.name` và cùng JVM.

## 5. So sánh HTTP span và module span

| Tiêu chí | HTTP server span | Module span |
| --- | --- | --- |
| Đơn vị được mô tả | Một request HTTP tại server | Một đoạn thực thi/tương tác gắn với application module |
| Ranh giới chính | Giao thức HTTP và server request lifecycle | Ranh giới module/điểm instrument trong kiến trúc logic |
| Nguồn thông tin | Spring Boot/Micrometer HTTP instrumentation | Spring Modulith Insight hoặc instrumentation module tương ứng |
| Khi thường bắt đầu | Khi server instrumentation bắt đầu xử lý request | Khi lời gọi tới điểm module được instrument diễn ra |
| Khi thường kết thúc | Khi phạm vi request đo được kết thúc | Khi đoạn thực thi gắn module kết thúc |
| Dữ liệu để lọc | Method, route chuẩn hóa, status HTTP, service | Module, operation, kết quả và attributes nếu được instrument |
| Hệ thống cần để tạo | HTTP stack có observation và tracing integration | Mô hình module + cơ chế instrumentation tương ứng + tracing integration |
| Có bắt buộc khi request chạy? | Không, vẫn phụ thuộc cấu hình instrumentation | Không; mọi lời gọi module chưa chắc sinh span |
| Có thể xuất hiện ngoài HTTP? | Server HTTP span: không, vì không có request HTTP server | Có thể, nếu công việc nền/listener được instrument |
| Độ trễ phản ánh | Latency ở phạm vi HTTP server | Duration của thao tác được instrument gắn module |
| Số lượng trong một request | Thường có một server span cho một HTTP request được instrument | Có thể không có, có một hoặc nhiều module spans |
| Thể hiện cấu trúc tĩnh? | Không | Không; module spans là hành vi runtime, cần so với module graph riêng |

Trực giác hữu ích: **HTTP span là góc nhìn của người gọi qua HTTP; module span là góc nhìn của người thiết kế kiến trúc bên trong ứng dụng.** Hai góc nhìn bổ sung cho nhau, vì thế cùng một request có thể có cả hai mà không bị xem là đo thừa.

## 6. Ví dụ: request đi qua hai application module

Giả sử ứng dụng được bố trí:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── order/
    │   └── OrderAvailabilityController.java
    └── inventory/
        └── InventoryAvailability.java
~~~

Theo cách khám phá thông thường từ lớp ứng dụng tại `com.example.shop`, hai subpackage trực tiếp `order` và `inventory` có thể được Spring Modulith nhận diện thành hai application module.

Lớp khởi động:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Module `inventory` công khai một API đơn giản:

~~~java
package com.example.shop.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryAvailability {

    public boolean isAvailable(String sku) {
        // Chỉ để minh họa đường gọi; logic thật sẽ truy dữ liệu tồn kho.
        return sku != null && !sku.isBlank();
    }
}
~~~

Module `order` chứa điểm vào HTTP và gọi module `inventory`:

~~~java
package com.example.shop.order;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderAvailabilityController {

    private final InventoryAvailability inventory;

    public OrderAvailabilityController(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/demo/orders/{sku}/availability")
    public boolean check(@PathVariable String sku) {
        return inventory.isAvailable(sku);
    }
}
~~~

Để chạy mã cần thêm Spring MVC/Web starter và các dependency khác của ứng dụng. Đây là ví dụ **không thực hiện lưu đơn hay giữ hàng**; nó dùng một API đọc trạng thái để dễ tái hiện tương tác. `InventoryAvailability` nằm tại package gốc của module `inventory` nên phù hợp làm API công khai theo quy ước mặc định.

### Hai sơ đồ nhìn cùng một request

**Module graph tĩnh** diễn tả phụ thuộc do `order` tham chiếu API `inventory`:

~~~mermaid
flowchart LR
    Order["Module order"] -->|"Java call / dependency"| Inventory["Module inventory"]
~~~

**Trace runtime** có thể diễn tả:

~~~mermaid
flowchart TB
    HTTP["HTTP SERVER: GET /demo/orders/{sku}/availability
    duration 145 ms"]
    OrderSpan["MODULE: order
    duration 100 ms (minh họa)"]
    InvSpan["MODULE: inventory
    duration 28 ms (minh họa)"]
    HTTP --> OrderSpan
    OrderSpan --> InvSpan
~~~

Cây span này **chỉ là một cách biểu diễn giả định** nếu tất cả các đoạn đã được instrument và tracing context phù hợp. Tùy phiên bản và phạm vi instrumentation, backend có thể cho thấy HTTP span và chỉ một span cho tương tác tới `inventory`; điều đó không tự làm module graph sai.

Nếu request trả `200` trong 145 ms, module `inventory` mất 28 ms theo một module span, ta có thể nói rằng **đoạn instrumented của module đó chiếm 28 ms trong request được quan sát**. Không thể kết luận tất cả phần còn lại chỉ ở `order`: latency có thể bao gồm HTTP routing, serialization, security filter, database, network nội bộ hoặc thời gian ở đoạn chưa instrument.

## 7. Quan hệ cha–con và cách đọc duration đúng

Giả sử một trace có thời điểm tương đối:

| Span | Bắt đầu | Kết thúc | Duration |
| --- | ---: | ---: | ---: |
| HTTP server | 0 ms | 150 ms | 150 ms |
| Module `order` | 12 ms | 132 ms | 120 ms |
| Module `inventory` | 35 ms | 65 ms | 30 ms |
| Repository bên trong `inventory` (nếu instrument) | 40 ms | 60 ms | 20 ms |

Các span lồng nhau, nên **không** cộng `150 + 120 + 30 + 20 = 320 ms` rồi gọi đó là latency của request. Latency ở HTTP scope vẫn là 150 ms. Phép cộng 320 ms đã đếm những khoảng cùng thời gian nhiều lần.

~~~text
Timeline minh họa (đơn vị: mili giây)

HTTP server: [0 ........................................ 150]
order:             [12 ........................... 132]
inventory:                  [35 ....... 65]
repository:                    [40 ... 60]

inventory nằm trong khoảng đo của order;
repository nằm trong khoảng đo của inventory.
~~~

Trong thực tế, biểu đồ timeline của tracing backend thể hiện rõ các khoảng lồng nhau. Khi cần điều tra độ trễ:

1. Xem **HTTP server duration** để biết người gọi chờ bao lâu ở phía server được đo.
2. Xem **module span duration** để biết phần công việc được instrument bên trong module chiếm bao lâu.
3. Xem span con như JDBC/HTTP client nếu có, để xác định module đang chờ downstream hay tự xử lý lâu.
4. Xem **khoảng chưa được instrument**; không tự quy hết phần này cho một module nếu thiếu dữ liệu.
5. Nếu công việc song song, xem overlap và đường găng (*critical path*) thay vì cộng duration.

Một module span “dài” cũng có thể chủ yếu là thời gian **chờ I/O bên ngoài**; tên module giúp xác định trách nhiệm điều phối thao tác, chưa đủ chỉ ra nguyên nhân chi tiết.

## 8. Span module có thể tồn tại khi không có HTTP request

Không phải mọi nghiệp vụ trong Spring Boot đều bắt đầu bằng HTTP. Ứng dụng có thể khởi chạy tác vụ qua:

- `@Scheduled` job.
- Application event và listener sau commit.
- Message consumer (Kafka/RabbitMQ) hoặc stream processor.
- CLI/task khởi động nền.
- Một lời gọi Java từ thành phần khác trong cùng JVM.

Với các đường thực thi này, sẽ **không có HTTP server span mới** vì không có request HTTP server. Tuy nhiên, module instrumentation hoặc observation tự thêm có thể tạo module-related spans nếu tracing context được thiết lập.

Ví dụ luồng event:

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order
    participant Inv as inventory listener
    participant Trace as Tracing backend
    User->>Order: POST /orders
    Order->>Trace: HTTP + order spans (nếu instrument)
    Order->>Order: Publish OrderPlaced
    Order-->>User: 201 Created
    Note over Order,Inv: Listener có thể chạy async, sau commit
    Order-->>Inv: OrderPlaced
    Inv->>Trace: Listener/module span (nếu instrument)
~~~

Nếu listener chạy trên thread mới mà tracing context không được truyền, span của listener có thể bắt đầu **trace mới**, xuất hiện độc lập hoặc mất trace context hoàn toàn. Đó là lý do không thể dùng “thiếu span con dưới HTTP” làm bằng chứng listener không chạy.

### Phân biệt truyền context và lan truyền transaction

| Cơ chế | Mục đích | Điều không được bảo đảm |
| --- | --- | --- |
| **Trace context propagation** | Liên kết/tương quan các span và logs qua thread/process | Event đã xử lý thành công |
| **Transaction context** | Quản lý commit/rollback trong một phạm vi giao dịch | Tự tồn tại qua listener async sau commit |
| **Event Publication Registry** nếu cấu hình | Theo dõi lifecycle publication để hỗ trợ tin cậy | Không tự xuất module span hoặc đầy đủ event metrics |
| **Event ID/idempotency key** | Theo dõi và kiểm soát xử lý trùng theo nghiệp vụ | Không thay thế tracing instrumentation |

Với async công việc có vòng đời riêng, một **span link** hoặc correlation ID nghiệp vụ có thể phù hợp hơn cố gắng ép mọi span thành cây cha–con kéo dài vô hạn. Cách thể hiện tùy tracing integration và thiết kế xử lý sự kiện.

## 9. Khi nào chỉ thấy HTTP span mà không thấy module span?

Đây là tình huống thực tế dễ gặp. Có HTTP span chứng minh rằng **HTTP instrumentation và tracing pipeline đã hoạt động cho request đó**; nó không bảo đảm instrumentation module cũng được bật.

| Khả năng | Dấu hiệu | Điều cần kiểm tra |
| --- | --- | --- |
| Chưa có Spring Modulith Insight phù hợp | Chỉ thấy HTTP/JDBC spans | Dependency và cấu hình Modulith observability trong phiên bản dùng |
| Module detection sai gốc package | Graph thiếu `order`/`inventory` | Gốc `ShopApplication`, module graph và chiến lược phát hiện |
| Lời gọi không cắt qua ranh giới module | Chỉ thấy một module hoặc không thấy module | Cấu trúc package, vị trí API và thực tế code path |
| Lời gọi không qua proxy/interceptor phù hợp | Service chạy nhưng thiếu module observation | Cơ chế instrumentation, self-invocation, kiểu bean và vị trí gọi |
| Phương thức/bean nằm ngoài phạm vi instrument | Một số phương thức hiện span, số khác không | Phạm vi hỗ trợ cụ thể của phiên bản |
| Trace bị sampling hoặc export lọc | Không thấy đủ spans ở backend | Sampler, collector processors/exporters, query time range |
| Context bị đứt ở async | Listener có trace khác | Executor, task decorator, tracing headers |
| Truy vấn backend chưa đúng | Có trace nhưng filter theo span name sai | Tìm trước theo service/time/trace ID, sau đó xem span attributes |

Ngược lại, **có module span mà không có HTTP span** cũng có thể hoàn toàn hợp lệ khi module chạy từ scheduler, event listener hoặc message consumer không qua HTTP.

Một cách khoanh vùng tốt là chia câu hỏi:

1. **Graph** có nhận diện đúng module không?
2. **Runtime** có thực sự gọi API/consumer mong đợi không?
3. **Instrumentation** có tạo observation/span cho điểm gọi đó không?
4. **Tracing/export** có giữ và chuyển dữ liệu không?
5. **Backend/query** có hiển thị đúng khoảng thời gian và service không?

## 10. Bật và kiểm tra spans trong Spring Boot / Spring Modulith

Một tập dependency Maven tham khảo với version do BOM/parent tương thích quản lý:

~~~xml
<dependencies>
    <!-- REST endpoint / Spring MVC cho ví dụ -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <!-- Actuator + Micrometer -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <!-- Module-level observability ở các phiên bản Modulith hỗ trợ -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
    </dependency>
    <!-- Tracing bridge và OTLP exporter minh họa -->
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

Không phải dự án nào cũng cần khai báo nguyên bộ này: một số starter có thể đã kéo dependency liên quan. Hãy kiểm tra dependency tree và BOM của phiên bản Spring Modulith đang dùng; thiếu tương thích có thể dẫn đến không có instrumentation hoặc lỗi khởi động.

Ví dụ `application.yml` cho **local/test**, giả định có OTLP/HTTP receiver đang chạy ở `localhost:4318`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Ý nghĩa:

- Actuator hỗ trợ kiểm tra health và meters; có Actuator **chưa đủ** để xuất traces.
- Tracing bridge và exporter phù hợp là điều kiện để observation trở thành spans được gửi tới backend.
- Sampling `1.0` thuận tiện cho bài thử nghiệm, nhưng không nên mặc định dùng cho production vì chi phí lưu trữ/hiệu năng.
- OTLP endpoint chỉ hoạt động khi có receiver tương ứng; trong Docker/Kubernetes, `localhost` có thể là chính container của ứng dụng và **không trỏ đến Collector**.
- Spring Modulith Insight giúp quan sát module theo phạm vi phiên bản hỗ trợ; **không có cam kết mọi Java method đều có module span**.

### Kiểm tra bằng một request cụ thể

Sau khi chạy ứng dụng mẫu và tracing backend:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/demo/orders/A-42/availability
~~~

Trên PowerShell có thể dùng `curl.exe` nếu `curl` trỏ tới alias khác. Kiểm tra thứ tự:

1. Endpoint trả `200` và dữ liệu như mong đợi.
2. Tracing backend có **HTTP server span** cho đường dẫn đã gọi, ở service ứng dụng.
3. Trong cùng trace có **module span** hoặc span tương tác module do Spring Modulith cung cấp **nếu integration thực sự instrument điểm gọi này**.
4. So tên/attributes thật với module graph: nó có liên quan `order` và `inventory` như dự kiến không?
5. Kiểm tra start/end/duration và quan hệ parent–child; không cộng durations của những span lồng nhau.

Nếu chỉ có HTTP span, hãy kiểm tra module graph và phạm vi instrumentation trước khi đổi các cấu hình exporter đang hoạt động.

### Vai trò của Actuator và metrics

`/actuator/metrics` giúp tra các meter đã đăng ký trong ứng dụng. Một observation có thể sinh timer khi metric handler phù hợp được bật, nhưng **timer không phải span**. Tracing backend mới là nơi thường tìm span và cây trace.

Nếu có Prometheus registry, `/actuator/prometheus` có thể xuất số đo cho Prometheus scrape. Nhiều phiên bản dùng tên meter/tag khác nhau; không suy đoán rằng module span luôn tạo một metric có tên cố định hay một timer luôn đủ histogram để tính p95.

## 11. Khi cần thêm span nghiệp vụ thủ công

Một module span gắn với ranh giới kiến trúc có thể cho biết thao tác diễn ra tại module nào, nhưng chưa chắc đủ chi tiết để biết vì sao bên trong module chậm. Ta có thể tự instrument thao tác nghiệp vụ bằng Micrometer Observation:

~~~java
package com.example.shop.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {
    private final ObservationRegistry observations;

    public StockReservationService(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void reserve() {
        Observation.createNotStarted("shop.stock.reserve", observations)
                .lowCardinalityKeyValue("application.module", "inventory")
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(this::persistReservation);
    }

    private void persistReservation() {
        // Thay bằng thao tác nghiệp vụ thực tế.
    }
}
~~~

Khi có `TracingObservationHandler` và context đúng, đoạn observation này **có thể** tạo span nghiệp vụ bên trong span HTTP hoặc module span. Đây là span **do ứng dụng chủ động đặt**; không nên đánh đồng với module span do Spring Modulith Insight tạo ra.

Quan hệ lý tưởng có thể là:

~~~text
HTTP server span
└─ Module interaction: inventory
   └─ Business observation: shop.stock.reserve
      └─ Database span (nếu instrument)
~~~

Không cần bọc thêm nếu thao tác đã có đủ thông tin từ instrumentation framework. Span quá nhiều làm tăng chi phí và khiến trace khó đọc; hãy thêm khi cần trả lời câu hỏi cụ thể.

**Lưu ý cardinality:** nhãn metric `application.module=inventory` và `operation=reserve` có số giá trị hữu hạn, phù hợp cho metrics. Tránh dùng `orderId`, email, `traceId` hoặc dữ liệu động làm low-cardinality labels; nếu thật sự cần thông tin định danh để điều tra, cân nhắc log/span attributes với chính sách bảo vệ dữ liệu.

## 12. Đọc lỗi và trạng thái: đừng nhầm HTTP thành công với module thành công

Một vài tình huống thường gặp:

| Tình huống | HTTP span | Module span | Kết luận hợp lý |
| --- | --- | --- | --- |
| Controller gọi `inventory` đồng bộ, tất cả thành công | Có thể status `200` | Có thể có span `inventory` kết thúc bình thường | Luồng được instrument hoạt động; cần xem duration thực |
| `inventory` ném exception và HTTP trả `500` | Có thể ghi status/error HTTP | Có thể ghi lỗi của thao tác module | Lỗi nằm trên code path được đo; xem stack trace/log và nghiệp vụ |
| `inventory` ném exception nhưng controller bắt và trả `200` | HTTP span có thể phản ánh response `200` | Module/span nghiệp vụ có thể ghi exception tùy instrumentation | Trạng thái HTTP không bảo đảm mọi bước bên trong thành công |
| HTTP trả `201` rồi listener async thất bại | HTTP span đã kết thúc thành công | Listener có thể có span riêng hoặc trace khác | Phải kiểm tra consumer/event publication, không suy từ HTTP |
| HTTP span có nhưng thiếu span module | Request được instrument ở HTTP | Chưa biết module có chạy hay không | Kiểm tra discovery, điểm instrument, sampling, context, export |
| Có module-related span từ scheduled job | Không có HTTP server span | Có thể có span module/operation | Hành vi runtime bắt đầu từ background task, hoàn toàn hợp lệ |

Ngoài error status, cần xem **logs**. Micrometer Tracing cùng logging configuration phù hợp có thể đưa `traceId`/`spanId` vào MDC để tìm log của cùng trace. Tuy nhiên, logs có pipeline riêng; xuất spans bằng OTLP **không tự động** đưa logs đến cùng backend.

## 13. Thực hành: chứng minh hai loại span không thay thế nhau

Thực hiện trong môi trường local/test để có thể chủ động tạo traffic và lỗi.

### Thí nghiệm A — Chỉ kiểm tra HTTP

1. Chạy ứng dụng có HTTP instrumentation và tracing backend.
2. Gọi `GET /demo/orders/A-42/availability` ba lần.
3. Mở một trace, ghi HTTP span name, HTTP status, duration và `service.name`.
4. Viết điều **HTTP span chứng minh**: request được instrument và xử lý trong khoảng đo. Ghi rõ điều **chưa biết**: request đã đi qua module nào, có đoạn nội bộ chưa instrument nào.

### Thí nghiệm B — Đối chiếu module graph và module spans

1. Chạy kiểm chứng cấu trúc trong test bằng Spring Modulith, ví dụ:

   ~~~java
   package com.example.shop;

   import org.junit.jupiter.api.Test;
   import org.springframework.modulith.core.ApplicationModules;

   class ModularityTests {
       @Test
       void respectsModuleBoundaries() {
           ApplicationModules.of(ShopApplication.class).verify();
       }
   }
   ~~~

2. Xác nhận các module `order` và `inventory`, quan hệ API công khai mà code mẫu thiết lập.
3. Bật/kiểm tra Spring Modulith Insight phù hợp, gọi lại request như thí nghiệm A.
4. Trong trace có module spans thì xác định tên/attributes/duration của chúng. Nếu chưa có, ghi **NOT OBSERVED** và lần lượt kiểm tra module detection, instrumentation và exporter; không tự điền span giả.
5. Giải thích sự khác biệt giữa dependency tĩnh `order → inventory` và một lần tương tác runtime có trace.

### Thí nghiệm C — Thao tác không bắt đầu từ HTTP

1. Tạo hoặc dùng một scheduled job/event listener thử nghiệm gọi API `inventory`.
2. Xác định có telemetry ở nhánh này không và liệu nó xuất hiện cùng trace với request trước đó không.
3. Nếu listener async, kiểm tra executor và context propagation; đừng kết luận listener hỏng chỉ từ việc HTTP trace thiếu span con.
4. Đối chiếu số lượt chạy với metrics/logs để kiểm chứng công việc thực sự diễn ra.

### Bảng ghi nhận kết quả

| Lời gọi | HTTP server span | Module span | Trace context | Bằng chứng nghiệp vụ |
| --- | --- | --- | --- | --- |
| HTTP gọi `order → inventory` | … | … | … | … |
| HTTP trả lỗi | … | … | … | … |
| Listener chạy sau commit | … | … | … | … |
| Scheduled job gọi module | … | … | … | … |

Khi thu thập, ghi **tên thực tế** của span và attributes thay vì dựa vào tên minh họa. Nếu sampling được bật ở mức thấp, hãy tăng phù hợp trong local test để thu được đủ dữ liệu, rồi khôi phục chính sách cho môi trường vận hành.

## 14. Câu hỏi tự kiểm tra

1. Vì sao một HTTP server span `150 ms` và module span `inventory 30 ms` không đồng nghĩa request mất `180 ms`?
2. Nếu HTTP span chỉ ra `GET /orders/{id}` chậm, thông tin bổ sung từ module spans giúp khoanh vùng vấn đề gì?
3. Tại sao hai module trong cùng một Spring Boot process thường cùng `service.name`, dù module spans có tên khác nhau?
4. Vì sao module graph có cạnh phụ thuộc nhưng tracing backend không hiển thị module span cho một request vừa gửi?
5. Có thể có module span khi không có HTTP server span không? Hãy nêu hai ví dụ.
6. Một listener bất đồng bộ thất bại sau khi HTTP trả `201`: cần theo dõi những tín hiệu nào ngoài HTTP span?
7. Việc thêm một observation thủ công trong `inventory` có đồng nghĩa Spring Modulith đã tự instrument module đó không?
8. Khi trace và log không chia sẻ cùng ID trong listener async, bạn nên kiểm tra context propagation ở đâu?
9. Span “module `inventory`” mất 300 ms có đủ chứng minh code Java bên trong module tiêu tốn CPU 300 ms không?
10. Nếu tracing exporter ngừng hoạt động nhưng Actuator metrics vẫn tăng, có thể rút ra kết luận gì về các chặng observability?

## 15. Tổng kết

**HTTP server span** mô tả một yêu cầu tại ranh giới giao thức HTTP. **Module span** mô tả một đoạn thực thi được instrument theo ranh giới trách nhiệm của **application module**. Khi cùng xuất hiện trong một trace, chúng cho ta hai lát cắt bổ sung: trải nghiệm HTTP ở phía nhận request và cách các phần logic bên trong ứng dụng tham gia xử lý.

Để dùng các span đúng cách, cần kết hợp **module graph của Spring Modulith**, **Micrometer Observation/tracing**, **Actuator và metrics**, rồi kiểm tra dữ liệu thực trong backend. Không cộng duration của các span lồng nhau, không coi module span là lời gọi mạng, không dùng HTTP status để khẳng định listener bất đồng bộ thành công, và không coi việc thiếu span là bằng chứng module không chạy. Những kết luận về kiến trúc mô-đun trong runtime phải được đối chiếu với cả instrumentation, context propagation và trạng thái nghiệp vụ.
