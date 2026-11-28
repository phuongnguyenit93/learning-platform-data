# Vai trò của `spring-modulith-starter-insight`

## 1. Insight Starter giải quyết vấn đề gì?

Một ứng dụng Spring Boot theo kiến trúc **modular monolith** có thể được chia thành nhiều *application module* như `ordering`, `inventory` và `payment`. Tách module trên mã nguồn giúp xác định phần API công khai, phần triển khai nội bộ và hướng phụ thuộc giữa các chức năng. Tuy nhiên, khi ứng dụng chạy, đội phát triển vẫn cần biết:

- Phiên bản đang chạy thực sự nhận diện những application module nào và chúng phụ thuộc nhau ra sao?
- Lúc người dùng đặt hàng, lời gọi đã đi qua ranh giới module nào và mất thời gian ở đâu?
- Những domain event nào được phát ra, với tần suất bao nhiêu?
- Có thể cung cấp dữ liệu này cho hệ thống metrics/tracing sẵn có mà không tự viết một lớp instrumentation cho từng module không?

**`org.springframework.modulith:spring-modulith-starter-insight`** là *starter tích hợp khả năng quan sát Spring Modulith lúc chạy*. Nó đưa vào hai nhóm tính năng chính: **Spring Boot Actuator endpoint mô tả cấu trúc module** và **instrumentation dựa trên Micrometer cho tương tác module/domain event**. Starter cũng kéo theo phần hỗ trợ nền của Spring Boot Actuator.

Đây là điểm kết nối giữa **kiến trúc dự kiến trong mã nguồn** với **bằng chứng vận hành**. Insight Starter không tự sửa thiết kế module và cũng không thay thế việc kiểm tra ranh giới bằng test; nó làm cho cấu trúc và một phần tương tác runtime trở nên có thể quan sát.

### Mục tiêu bài học

Sau bài này, bạn có thể giải thích thành phần mà Insight Starter kích hoạt, thêm starter vào ứng dụng phù hợp phiên bản, bật và đọc endpoint `/actuator/modulith`, phân biệt event metrics với tracing spans, cấu hình đường xuất dữ liệu cơ bản, xử lý các lỗi quan sát thường gặp và xác định trường hợp nào nên dùng starter hoặc chỉ dùng module con tương ứng.

## 2. Insight Starter nằm ở đâu trong hệ sinh thái Spring Modulith?

Spring Modulith có nhiều nhóm chức năng. Insight Starter tập trung vào **production-ready features**, tức các khả năng hữu ích khi một ứng dụng đang chạy, thay vì bao gồm toàn bộ hệ sinh thái.

~~~mermaid
flowchart TB
    Application["Ứng dụng Spring Boot có application modules"]
    Starter["spring-modulith-starter-insight"]
    Actuator["spring-modulith-actuator"]
    Observe["spring-modulith-observability-core"]
    BootActuator["spring-boot-starter-actuator"]
    AppModules["Module structure / dependencies"]
    Meters["Micrometer event metrics"]
    Spans["Micrometer module-entry observations / spans"]
    Infra["Registry, tracing bridge, exporter, backend"]

    Application --> Starter
    Starter --> Actuator
    Starter --> Observe
    Starter --> BootActuator
    Actuator --> AppModules
    Observe --> Meters
    Observe --> Spans
    Meters -. "thêm registry nếu cần" .-> Infra
    Spans -. "thêm tracer/exporter nếu cần" .-> Infra
~~~

Sơ đồ thể hiện **vai trò tích hợp về mặt chức năng**, không phải danh sách đầy đủ mọi dependency bắc cầu của Maven/Gradle. Trong tài liệu Spring Modulith 2.2, starter gom hỗ trợ Actuator và `spring-modulith-observability-core` với khả năng chạy Actuator của Spring Boot.

| Thành phần | Vai trò | Khi nào cần? |
| --- | --- | --- |
| `spring-modulith-starter-insight` | Đưa Actuator cấu trúc module và module observability vào cùng ứng dụng. | Muốn bật cả hai hướng quan sát với ít khai báo. |
| `spring-modulith-actuator` | Đăng ký endpoint `modulith` để xem module và dependency. | Chỉ cần cấu trúc module runtime. |
| `spring-modulith-observability-core` | Instrument điểm vào API của module và đăng ký metrics cho domain event. | Chỉ cần tín hiệu tương tác module/event. |
| `spring-boot-starter-actuator` | Cung cấp hạ tầng Actuator và các management endpoint của Spring Boot. | Cần Actuator khi chọn từng phần riêng lẻ. |
| `spring-modulith-observability-api` | Cho phép sử dụng các API tùy biến observability, ví dụ `ModulithEventMetricsCustomizer` trong mã nguồn. | Chỉ cần ở compile scope khi tự viết cấu hình tùy biến. |
| Micrometer registry/tracing bridge/exporter | Đưa metrics và traces tới Prometheus, Zipkin, Grafana Tempo, v.v. | Khi cần lưu trữ, truy vấn, hiển thị dữ liệu ngoài tiến trình. |

**Không nên đồng nhất Insight Starter với các tính năng khác:**

- **Kiểm chứng kiến trúc**: `ApplicationModules.verify()` kiểm tra phụ thuộc vòng, truy cập vào nội bộ module và các quy tắc phụ thuộc. Đây là hoạt động phân tích/kiểm thử mã nguồn.
- **Sinh tài liệu thiết kế**: `Documenter` tạo sơ đồ module và tài liệu như Module Canvas trong quá trình xây dựng/kiểm thử.
- **Event Publication Registry**: theo dõi trạng thái công bố và xử lý event để tăng độ tin cậy cho tương tác dựa trên sự kiện. Việc có counter phát event từ Insight Starter không đồng nghĩa đã có cơ chế đảm bảo xử lý lại sự kiện.
- **Distributed tracing backend**: kho thu thập và giao diện xem trace là thành phần được cấu hình riêng; Insight Starter tạo điểm quan sát, không tự triển khai Zipkin/Tempo.

## 3. Thêm dependency đúng cách

### 3.1. Maven: cách khai báo tối thiểu

Với dự án Spring Boot có phiên bản tương thích, thêm starter ở **runtime scope**. Ví dụ minh họa dùng Spring Modulith 2.2.0, một bản phát hành ổn định tại thời điểm soạn bài:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <version>2.2.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án đã import `spring-modulith-bom` tương thích thì bỏ phần `<version>` của dependency và để BOM quản lý phiên bản. Một ví dụ quản lý dependency bằng Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>2.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

### 3.2. Gradle: cách khai báo tối thiểu

Với Gradle Kotlin DSL, nếu chưa có cơ chế BOM hoặc dependency management khác:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight:2.2.0")
}
~~~

Ở dự án dùng BOM, có thể để BOM quản lý version thay vì ghim ở từng dependency. **Không dùng lẫn phiên bản các artifact Spring Modulith một cách tùy tiện.** Cần kiểm tra bảng tương thích với Spring Boot: nhánh Spring Modulith 1.x được dùng rộng rãi với Spring Boot 3.x, còn nhánh 2.x hướng đến Spring Boot 4.x. Ví dụ trong bài sử dụng cách khai báo của nhánh **2.2**; nếu đang dùng Boot 3.x, hãy chọn phiên bản Spring Modulith 1.x tương thích và đối chiếu tên artifact con của nhánh đó.

### 3.3. Khi nào không cần starter tổng hợp?

Nếu chỉ muốn xem dependency graph của phiên bản đang chạy, có thể khai báo `spring-modulith-actuator` và `spring-boot-starter-actuator`. Nếu chỉ muốn tạo instrumentation mà không cần endpoint `modulith`, có thể dùng riêng `spring-modulith-observability-core` kèm hạ tầng Micrometer phù hợp (đối với Spring Modulith 2.x).

Với ứng dụng thực tế cần cả bản đồ module và quan sát tương tác, **Insight Starter thường là lựa chọn đầu tiên** vì giảm việc lắp ghép dependency thủ công. Nhưng starter là một **tập hợp tiện ích runtime**, không phải công tắc tự động cung cấp mọi dashboard, exporter, phép kiểm tra kiến trúc hay tài liệu thiết kế.

## 4. Ví dụ xuyên suốt: hệ thống đặt hàng

Giả sử ứng dụng Spring Boot có cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering
│   ├── OrderService.java
│   └── OrderPlaced.java
├── inventory
│   └── InventoryService.java
└── notification
    └── OrderPlacedListener.java
~~~

- `ordering` gọi API công khai của `inventory` để giữ hàng.
- `ordering` phát domain event `OrderPlaced` sau khi xử lý nghiệp vụ.
- `notification` có listener tiêu thụ `OrderPlaced` để gửi thông báo.

~~~mermaid
sequenceDiagram
    actor Client
    participant O as ordering
    participant I as inventory
    participant E as ApplicationEventPublisher
    participant N as notification
    Client->>O: POST /orders
    O->>I: reserveItems(...)
    I-->>O: đã giữ hàng
    O->>E: publishEvent(OrderPlaced)
    E-->>N: phát tới listener
    O-->>Client: kết quả đặt hàng
    Note over E,N: Thời điểm xử lý listener phụ thuộc cấu hình đồng bộ/bất đồng bộ
~~~

Với cùng một lượt đặt hàng, Insight Starter mở ra **hai góc nhìn bổ sung**:

1. Actuator công bố rằng `ordering` có quan hệ phụ thuộc với `inventory` và module tiêu thụ sự kiện có thể phụ thuộc vào loại event của `ordering`.
2. Metrics và traces giúp tìm tần suất phát `OrderPlaced` và các điểm đi vào API module đã được instrument trong lúc xử lý yêu cầu.

Lưu ý chiều quan hệ: trong module graph, listener tham chiếu lớp `OrderPlaced` có thể tạo cạnh **`notification → ordering`**; trong sơ đồ nghiệp vụ, event đi từ `ordering` đến `notification`. Graph phụ thuộc mã nguồn và luồng dữ liệu runtime có thể khác chiều.

## 5. Tính năng thứ nhất: module graph qua Spring Boot Actuator

Insight Starter kích hoạt thành phần để có thể truy vấn thông tin các application module từ tiến trình Spring Boot. Endpoint có **ID `modulith`**; khi được phép truy cập qua HTTP, đường dẫn thường là:

~~~http
GET /actuator/modulith
~~~

Phản hồi JSON **minh họa** cho hệ thống đặt hàng:

~~~json
{
  "ordering": {
    "displayName": "Ordering",
    "basePackage": "com.example.shop.ordering",
    "dependencies": [
      { "target": "inventory", "types": ["USES_COMPONENT"] }
    ]
  },
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": []
  },
  "notification": {
    "displayName": "Notification",
    "basePackage": "com.example.shop.notification",
    "dependencies": [
      { "target": "ordering", "types": ["EVENT_LISTENER"] }
    ]
  }
}
~~~

| JSON field | Ý nghĩa |
| --- | --- |
| `ordering`, `inventory`... | Tên kỹ thuật của module, dùng làm khóa trong JSON. |
| `displayName` | Tên dễ đọc của module. |
| `basePackage` | Package gốc được dùng để nhận diện module. |
| `dependencies[].target` | Module mà module hiện tại phụ thuộc. |
| `dependencies[].types[]` | Kiểu phụ thuộc: `DEFAULT` (tham chiếu kiểu), `USES_COMPONENT` (dùng Spring component), `EVENT_LISTENER` (listener sự kiện). |
| `parent` và `nested` nếu có | Thông tin module lồng nhau. |

Endpoint cho biết **kiến trúc được nhận diện trong ứng dụng đang chạy**. Nó không trả về request nào đang hoạt động, số lần gọi một API hay thời gian phản hồi. Vì vậy:

- Thấy cạnh `ordering → inventory` **không có nghĩa** mọi đơn hàng đều gọi API giữ hàng.
- Không thấy một cạnh mong đợi là tín hiệu cần kiểm tra cách nhận diện module hoặc cấu hình runtime.
- Nếu dự án tùy chỉnh cách nhận diện module chỉ trong source test, runtime không mặc nhiên áp dụng các tùy chỉnh ấy. Những tùy chỉnh cần dùng ở runtime phải có mặt trong production sources.

Để phát hiện vi phạm ranh giới trước khi triển khai, vẫn cần phép kiểm chứng bằng `ApplicationModules.verify()` và kiểm thử kiến trúc phù hợp.

## 6. Tính năng thứ hai: metrics từ domain event

Spring Modulith quan sát các domain event được phát trong ứng dụng thông qua Micrometer. Hai họ counter quan trọng là:

| Metric | Diễn giải |
| --- | --- |
| `module.events.published` | Counter tổng hợp các lần phát domain event. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho một loại event của một module, có thể gắn thêm tag nghiệp vụ. |

Counter tổng hợp có các tag như `module.identifier`, `module.name` và `module.event.type` để phân tách theo module và loại event. Counter riêng theo event có thể được điều chỉnh bằng `ModulithEventMetricsCustomizer` khi thêm `spring-modulith-observability-api` ở compile scope.

Trong ví dụ, số lần phát `OrderPlaced` có thể dùng để trả lời câu hỏi: *Trong 10 phút vừa rồi, module ordering phát bao nhiêu sự kiện đặt hàng và tốc độ có tăng bất thường không?* Counter này **không đồng nghĩa** số đơn hàng đã commit thành công hoặc số email đã gửi xong.

Một metric có tên `module.events.published` là **tên meter Micrometer**. Khi xuất qua Prometheus, registry có thể chuẩn hóa tên theo quy ước của Prometheus; không nên tự đoán tên chuỗi sau xuất mà chưa xem dữ liệu thực tế.

### Ví dụ kiểm tra metrics

Khi ứng dụng đã chạy và `metrics` endpoint được expose:

~~~bash
curl -s http://localhost:8080/actuator/metrics/module.events.published
~~~

Để lọc một module, có thể dùng query parameter theo tag được đăng ký:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:ordering"
~~~

Nếu muốn Prometheus scrape dữ liệu, ứng dụng cần thêm registry tương ứng, ví dụ với Gradle:

~~~kotlin
dependencies {
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Khi cấu hình Actuator cho phép, có thể truy cập `/actuator/prometheus`. **Insight Starter không tự cung cấp Prometheus server hoặc dashboard**; registry chỉ xuất dữ liệu theo định dạng phù hợp để hệ thống bên ngoài thu thập.

## 7. Tính năng thứ ba: observations và tracing qua ranh giới module

Với `spring-modulith-observability-core` được đưa vào bởi Insight Starter, các Spring component thuộc **API công khai của application module** có thể được gắn aspect để chặn lời gọi và tạo Micrometer Observation. Khi tích hợp tracer phù hợp, các observation đó có thể trở thành **span** trong trace.

Các tag của module-entry span theo tài liệu:

| Tag | Ví dụ minh họa | Ý nghĩa |
| --- | --- | --- |
| `module.identifier` | `inventory` | Định danh module được gọi. |
| `module.name` | `Inventory` | Tên hiển thị của module. |
| `module.method` | `reserveItems` | Phương thức ở điểm vào được quan sát. |
| `module.invocation-type` | `bean` hoặc `event listener` | Kiểu lời gọi đi vào module. |

Trace của một lần đặt hàng **có thể** mang cấu trúc logic như sau:

~~~text
Trace: POST /orders
└── HTTP request span
    └── ordering module entry
        └── inventory module entry: reserveItems(...)
    ... notification listener: on(OrderPlaced)
        (nếu listener được instrument và trace context được nối tiếp)
~~~

Các tên span thực tế, quan hệ cha/con và span nào xuất hiện phụ thuộc phiên bản, đường thực thi, phạm vi instrumentation và tracer. Không phải mọi method nội bộ hoặc mọi lời gọi tự gọi trong cùng một bean đều được ghi riêng thành module-entry span.

### Trace khác metric như thế nào?

Metrics tổng hợp nhiều lần xử lý để phát hiện xu hướng và bất thường. Trace mô tả hành trình của **một lần xử lý** qua các vùng được instrument, từ đó giúp phân tích chặng nào chậm. Hai loại dữ liệu trả lời hai câu hỏi khác nhau:

- Metrics: “Tốc độ phát `OrderPlaced` tăng từ 10 lên 200 lần/phút lúc nào?”
- Trace: “Request đặt hàng `A-123` đã mất nhiều thời gian ở `inventory` hay ở chặng khác?”

Nếu một span có độ trễ cao, hãy kiểm tra các thao tác bên trong như JDBC, HTTP client hoặc gateway. Thời gian của module-entry span gồm thời gian thực thi trong phạm vi chặng được đo, không tự chứng minh toàn bộ nguyên nhân đều đến từ logic nội bộ của module ấy.

### Context propagation đối với listener bất đồng bộ

Một trace chỉ nối liền các chặng khi ngữ cảnh trace được truyền qua lời gọi tương ứng. Với listener chạy ở thread khác hoặc qua message broker, context có thể mất hoặc được tách nếu executor/messaging không được instrument đúng. Khi đó event đã phát và listener có thể vẫn chạy, nhưng span của listener không nằm cùng trace của HTTP request.

Những việc cần kiểm tra gồm: listener đồng bộ hay bất đồng bộ, `TaskExecutor` được cấu hình ra sao, có cơ chế truyền Micrometer context/trace context hay không, và tracer có xuất các span liên quan không. **Có Insight Starter không đảm bảo tự động nối mọi trace xuyên qua mọi ranh giới bất đồng bộ.**

## 8. Cấu hình để thấy dữ liệu thực tế

### 8.1. Expose các management endpoint cần thiết

Trong môi trường phát triển, có thể sử dụng `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0
~~~

Giải thích:

- `modulith`: endpoint mô tả application module.
- `metrics`: endpoint liệt kê và đọc các Micrometer meter đã đăng ký.
- `prometheus`: endpoint xuất dữ liệu cho Prometheus **khi có Prometheus registry**.
- `sampling.probability: 1.0`: dùng toàn bộ lượt lấy mẫu khi thử nghiệm. Với lưu lượng lớn, cần cân nhắc sampling để tránh chi phí lưu trữ cao.

Tùy phiên bản Spring Boot, endpoint còn phải được phép truy cập theo cấu hình access/security của Actuator. Ở production, nên giới hạn truy cập vào endpoint nội bộ như `modulith` và `metrics` bằng network policy và xác thực phù hợp. Không nên công khai sơ đồ kiến trúc của ứng dụng ra Internet.

### 8.2. Thêm tracer và exporter khi cần xem trace

Insight Starter tạo instrumentation ở mức module nhưng **chưa đủ** để xuất spans tới Zipkin, Grafana Tempo hoặc một backend khác. Bạn phải bổ sung bộ tracer/exporter tương thích với Spring Boot và hệ thống đích.

Ví dụ cho ứng dụng **Spring Boot 4.x** gửi trace qua OpenTelemetry/OTLP:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight:2.2.0")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
}
~~~

Spring Boot còn có lựa chọn Brave/Zipkin, ví dụ `spring-boot-starter-zipkin` cho Boot 4.x. Cấu hình địa chỉ OTLP/Zipkin exporter phải theo tài liệu của Spring Boot và backend mà dự án dùng; không có một URL chung phù hợp mọi hệ thống.

Với **Spring Boot 3.x**, tổ hợp dependency tracing khác với những starter của Boot 4.x. Hãy sử dụng bridge (OpenTelemetry hoặc Brave), exporter và cấu hình được hướng dẫn trong tài liệu dành cho đúng phiên bản Boot 3.x.

### 8.3. Kiểm tra thủ công trên máy phát triển

Sau khi khởi động ứng dụng mẫu:

~~~bash
# Bản đồ module: cần expose "modulith"
curl -s http://localhost:8080/actuator/modulith

# Danh sách các meter đã được đăng ký
curl -s http://localhost:8080/actuator/metrics

# Counter domain event, sau khi phát event mẫu
curl -s http://localhost:8080/actuator/metrics/module.events.published

# Dùng được khi có Prometheus registry và endpoint được expose
curl -s http://localhost:8080/actuator/prometheus
~~~

Sau đó tạo một đơn hàng có đi qua `inventory` và phát `OrderPlaced`. Với tracer/exporter đã hoạt động, tìm trace tương ứng trong giao diện backend. Cổng `8080` và base path `/actuator` chỉ là giá trị ví dụ; cấu hình ứng dụng có thể thay đổi chúng.

## 9. Mô hình “có starter” và “có quan sát được” không giống nhau

Việc dependency được resolve thành công mới chỉ xác nhận khả năng tích hợp thư viện. Để thật sự xem được dữ liệu, phải thông suốt cả chuỗi:

~~~mermaid
flowchart LR
    A["Ứng dụng khởi động và nhận diện modules"]
    B["Actuator/Observability instrumentation"]
    C["Meter / Observation"]
    D["Registry / Tracer"]
    E["Exporter / Backend"]
    F["Query / Dashboard"]
    A --> B --> C --> D --> E --> F
~~~

Từ mô hình này có thể phân loại tình huống:

| Hiện tượng | Khả năng cần kiểm tra | Kiểm tra đề xuất |
| --- | --- | --- |
| `/actuator/modulith` trả 404 | Endpoint chưa được đăng ký, chưa được expose hoặc bị giới hạn access. | Dependency runtime, endpoint exposure/access, cổng và management base path. |
| JSON `modulith` thiếu module | Cách nhận diện module hoặc cấu hình production không giống dự kiến. | Package layout, custom detection strategy và việc cấu hình có trong production source. |
| `/actuator/metrics` có nhưng không thấy event counter | Chưa có event phù hợp được phát, meter chưa được đăng ký hoặc tính năng observability chưa kích hoạt. | Phát event thử, kiểm tra cấu hình và dependency. |
| Thấy counter nhưng Prometheus không scrape được | Thiếu Prometheus registry, endpoint chưa expose hoặc cấu hình scrape sai. | Dependency registry, `/actuator/prometheus`, URL/port, xác thực. |
| Không thấy span trong backend | Thiếu tracer/exporter, sai endpoint hoặc sampling đã loại trace. | Dependency tracing, export config, backend, sampling. |
| Không thấy listener trong cùng trace | Listener async hoặc một ranh giới chưa truyền context/được instrument. | Executor/messaging instrumentation, context propagation, log correlation. |
| Traces có module nhưng vẫn vi phạm kiến trúc | Tracing không phải công cụ kiểm chứng phụ thuộc tĩnh. | Chạy `ApplicationModules.verify()` ở test/CI. |

### Ba ngộ nhận cần tránh

**“Thêm Insight Starter là tự có Grafana dashboard.”** Sai. Starter giúp tạo dữ liệu quan sát; vẫn phải cấu hình registry hoặc tracer, exporter, hệ thống thu thập và dashboard.

**“Counter `OrderPlaced` tăng nghĩa là listener đã xử lý thành công.”** Sai. Counter phản ánh việc phát domain event được instrument. Cần log, trạng thái xử lý sự kiện hoặc metric nghiệp vụ riêng cho kết quả listener.

**“Thấy dependency trong `/actuator/modulith` nghĩa là request vừa rồi đã gọi dependency đó.”** Sai. Actuator trình bày quan hệ cấu trúc. Muốn điều tra hành vi một request cụ thể cần trace/log phù hợp.

## 10. Quy trình triển khai đề xuất cho dự án thật

1. **Xác nhận ranh giới:** thiết kế package và API của module, chạy `ApplicationModules.verify()` trong test để phát hiện phụ thuộc sai.
2. **Chọn phiên bản:** dùng Spring Modulith phù hợp với Spring Boot và quản lý version thống nhất bằng BOM.
3. **Thêm Insight Starter:** khai báo `spring-modulith-starter-insight` ở runtime; chỉ thêm module con riêng lẻ khi có nhu cầu đặc thù.
4. **Bật endpoint có kiểm soát:** expose `modulith` và `metrics` trong môi trường phù hợp, bảo vệ truy cập.
5. **Kết nối hệ thống quan sát:** thêm metrics registry hoặc tracer/exporter theo backend đang dùng.
6. **Tạo giao dịch kiểm chứng:** thực hiện một luồng đặt hàng đã biết trước các API module và domain event sẽ được dùng.
7. **Đối chiếu bằng chứng:** xác nhận graph runtime, event counter và trace phù hợp; với listener async, kiểm tra việc truyền context.
8. **Theo dõi liên tục:** đặt dashboard/alert theo các chỉ số thực sự cần, chạy kiến trúc test trên CI và rà soát khi thiết kế module thay đổi.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao dự án đã có `spring-boot-starter-actuator` vẫn cần `spring-modulith-starter-insight` nếu muốn xem module graph và event metrics?

**Trả lời:** Actuator của Boot cung cấp hạ tầng management nói chung; Insight Starter bổ sung hỗ trợ riêng của Spring Modulith cho endpoint `modulith` và observability ở ranh giới application module/domain event.

**Câu 2.** Thêm Insight Starter và mở `/actuator/modulith` có tự tạo tập tài liệu thiết kế module dạng sơ đồ không?

**Trả lời:** Không. Endpoint là nguồn thông tin cấu trúc runtime. Việc sinh tài liệu kiến trúc từ mã nguồn là nhiệm vụ của `Documenter`.

**Câu 3.** Tại sao trace trong Tempo/Zipkin vẫn rỗng dù có starter?

**Trả lời:** Cần kiểm tra tracer, exporter, địa chỉ backend, sampling và việc có tương tác qua điểm instrument hay không. Insight Starter một mình không triển khai pipeline xuất trace.

**Câu 4.** Ở ứng dụng gửi event bất đồng bộ, vì sao có event counter tăng nhưng không có span listener trong cùng trace?

**Trả lời:** Counter phản ánh sự kiện đã được phát; listener có thể chạy ở thread khác, thiếu context propagation hoặc chưa có instrumentation/tracing đúng chỗ. Phải xem cấu hình async và dữ liệu theo dõi việc xử lý sự kiện.

**Câu 5.** Khi nào nên dùng riêng `spring-modulith-actuator`?

**Trả lời:** Khi chỉ cần công bố cấu trúc application module ở runtime và chưa có nhu cầu thêm instrumentation tương tác, cùng với hạ tầng Spring Boot Actuator cần thiết.

## 12. Tài liệu tham khảo

- [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): `spring-modulith-starter-insight`, Actuator, module-entry spans và event metrics.
- [Spring Modulith – Reference](https://docs.spring.io/spring-modulith/reference/): khai báo Spring Modulith BOM và liên kết tài liệu phiên bản.
- [Spring Modulith – Spring Boot Compatibility](https://docs.spring.io/spring-modulith/reference/appendix.html): đối chiếu phiên bản Spring Boot và Spring Modulith.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access và bảo vệ management endpoint.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer meters và registry.
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracer, sampling và truyền trace context.

**Kết luận:** `spring-modulith-starter-insight` là cửa ngõ đơn giản để đem **bản đồ application module** và **tín hiệu tương tác runtime** vào khả năng quan sát của một Spring Boot modular monolith. Hãy xem nó như lớp instrumentation và cung cấp metadata: cấu trúc phải tiếp tục được kiểm chứng bằng test, còn metrics/traces phải được kết nối với hạ tầng thu thập và đọc trong bối cảnh luồng nghiệp vụ thực tế.
