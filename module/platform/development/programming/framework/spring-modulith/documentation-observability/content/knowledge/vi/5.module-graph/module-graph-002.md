# Base package và ý nghĩa trong dữ liệu quan sát

Trong Spring Modulith, **base package** không chỉ là cách đặt tên source code. Nó là điểm xuất phát để xác định các **application module**, từ đó tạo **module graph** và làm cơ sở cho những tính năng hiểu được ranh giới module. Khi bổ sung observability cho ứng dụng Spring Boot, cách hệ thống nhận diện module sẽ ảnh hưởng đến việc ta **gán lời gọi, sự kiện và tín hiệu vận hành cho module nào**.

Ví dụ, ứng dụng bán hàng thực sự có ba module `order`, `inventory` và `billing`. Nếu gốc package được phát hiện quá hẹp, một số module có thể không xuất hiện trong module graph; nếu gốc quá rộng, các package kỹ thuật không mong muốn có thể trở thành module. Điều này khiến bản đồ kiến trúc và dữ liệu quan sát khó đối chiếu, dù REST API vẫn hoạt động bình thường.

Bài học thuộc chương **Module graph** trong chủ đề `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`: dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát các tương tác giữa chúng trong Spring Boot, qua Actuator, metrics, tracing và context propagation. Trọng tâm ở đây là **quan hệ nhân quả giữa cách đặt base package, việc phát hiện module và cách diễn giải telemetry**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Java package, base package của ứng dụng, phạm vi component scan và base package dùng để phát hiện application module.
2. Giải thích vì sao các subpackage trực tiếp thường trở thành application module theo cách phát hiện mặc định của Spring Modulith.
3. Nhận biết việc đặt sai base package làm thiếu, thừa hoặc đổi tên module trong module graph như thế nào.
4. Phân biệt **module identity** với `service.name` của telemetry và với trace/span ID.
5. Liên hệ metadata module với các observation, span, metrics, logs và application event trong một yêu cầu thật.
6. Xây dựng cách kiểm chứng: so module graph trước, kiểm tra các tín hiệu khi chạy sau, xác minh dữ liệu nghiệp vụ cuối cùng.

## 2. Base package thực sự là gì?

Trong Java, `package` là namespace của lớp. Ta thường tổ chức lớp liên quan vào những package như `com.example.shop.order` và `com.example.shop.inventory`. Nhưng trong Spring Boot/Spring Modulith, cụm từ **base package** dễ bị dùng cho các khái niệm khác nhau:

| Khái niệm | Ý nghĩa | Tác động chính |
| --- | --- | --- |
| **Java package** | Namespace được khai báo bằng `package ...;` ở đầu file Java | Tên đầy đủ của class, phạm vi truy cập theo package |
| **Package gốc ứng dụng Spring Boot** | Package chứa lớp cấu hình ứng dụng chính, thường có `@SpringBootApplication` | Thường là gốc mặc định cho component scan và các quy ước framework |
| **Component scan base packages** | Phạm vi Spring tìm kiếm các thành phần như `@Component`, `@Service` | Bean nào được tạo trong Spring context |
| **Module detection base package** | Điểm gốc mà Spring Modulith dùng để khám phá các application module | Module nào được đưa vào module graph và được xem xét trong các tính năng hiểu ranh giới module |
| **Logical module identifier** | Tên định danh của một application module được phát hiện | Cách nhóm module trong tài liệu, kiểm tra phụ thuộc và một số thông tin quan sát |
| **Telemetry service identity** | Tên dịch vụ/ứng dụng, thường thể hiện qua thuộc tính như `service.name` | Gom trace/metric/log theo tiến trình hoặc dịch vụ, không mặc định là tên application module |

Trong cấu hình thông thường, lớp `@SpringBootApplication` nằm ở gốc package của toàn bộ ứng dụng; Spring Modulith cũng có thể dùng lớp ứng dụng này làm điểm đầu để phát hiện module. Tuy nhiên, **component scan và module detection là hai cơ chế khác nhau**. Mở rộng `scanBasePackages` cho Spring Boot không đồng nghĩa đã thay đổi mọi quy tắc phát hiện module của Spring Modulith.

**Quy tắc tư duy:** package cho ta cấu trúc code; cấu hình phát hiện biến một phần cấu trúc đó thành module graph; instrumentation và exporter quyết định tín hiệu runtime nào được tạo và gửi đi.

## 3. Từ cây package đến module graph

Xét cấu trúc dự án mẫu:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java                 # @SpringBootApplication
    ├── order/
    │   ├── OrderService.java                # API module order
    │   ├── OrderPlaced.java                 # kiểu sự kiện công khai
    │   └── internal/
    │       └── OrderRepositoryAdapter.java  # chi tiết nội bộ
    ├── inventory/
    │   ├── InventoryService.java            # API module inventory
    │   └── internal/
    │       └── StockJpaRepository.java
    └── billing/
        ├── BillingService.java
        └── internal/
            └── PaymentGatewayAdapter.java
~~~

Lớp khởi động nằm tại:

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

Với cách phát hiện application module **mặc định theo các subpackage trực tiếp** bên dưới gốc `com.example.shop`, Spring Modulith sẽ nhận diện các ranh giới logic như:

| Package | Vai trò khi áp dụng quy ước mặc định |
| --- | --- |
| `com.example.shop` | Gốc để khám phá module; chứa lớp khởi động |
| `com.example.shop.order` | Base package của application module `order` |
| `com.example.shop.inventory` | Base package của application module `inventory` |
| `com.example.shop.billing` | Base package của application module `billing` |
| `com.example.shop.order.internal` | Package con bên trong module `order`, không tự thành module ngang hàng |
| `com.example.shop.inventory.internal` | Package con bên trong module `inventory`, không tự thành module ngang hàng |

Một sơ đồ phụ thuộc **giả định** sau khi có những lời gọi được code thực sự khai báo:

~~~mermaid
flowchart LR
    subgraph Shop["Ứng dụng Spring Boot: com.example.shop"]
        Order["order"]
        Inventory["inventory"]
        Billing["billing"]
    end
    Order -->|"gọi API công khai"| Inventory
    Order -->|"gọi API công khai"| Billing
~~~

**Lưu ý:** sơ đồ này chỉ là ví dụ nếu `order` thực sự tham chiếu API của `inventory` và `billing`. Spring Modulith không tự vẽ một cạnh chỉ vì hai package ở cạnh nhau. Phụ thuộc trong graph phải xuất phát từ quan hệ trong code và quy tắc nhận diện của công cụ.

### Module API và phần nội bộ

Theo quy ước thông thường, các type ở package gốc của module là phần API được module khác có thể sử dụng; type trong subpackage như `order.internal` thuộc phần nội bộ, trừ khi có cơ chế công khai giao diện bổ sung như **named interface**. Vì thế base package còn gắn với **câu hỏi phụ thuộc nào hợp lệ**.

Một module có thể tồn tại trong graph dù trong thời điểm quan sát không có request nào đi qua nó. Ngược lại, một bean Java có thể chạy nhưng nằm ngoài phạm vi phát hiện module; khi đó không nên mặc định rằng sẽ có span “tương tác module” cho bean ấy.

## 4. Kiểm chứng base package bằng Spring Modulith

Ta có thể khám phá module từ lớp `ShopApplication`, kiểm tra ràng buộc kiến trúc và sinh tài liệu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleGraphTest {

    @Test
    void verifyAndDocumentModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.verify();
        new Documenter(modules).writeDocumentation();
    }
}
~~~

Trong dự án thật, cần cấu hình dependency Spring Modulith Core, phần hỗ trợ tài liệu (`spring-modulith-docs`), JUnit và bộ quản lý phiên bản tương thích. `ApplicationModules.of(ShopApplication.class)` sử dụng lớp ứng dụng làm điểm xuất phát; `verify()` kiểm tra các ràng buộc mà Spring Modulith hỗ trợ; `Documenter` xuất tài liệu cấu trúc module và các quan hệ giữa chúng. Đường dẫn/định dạng output cụ thể tùy phiên bản và cấu hình.

Điều cần kiểm tra trong kết quả là:

1. Tên các module được phát hiện có đúng `order`, `inventory`, `billing` không?
2. Phần code mong đợi thuộc module nào? Có package quan trọng nào nằm ngoài graph?
3. Có package kỹ thuật bất ngờ bị xem là application module không?
4. Có cạnh phụ thuộc hoặc chu trình ngoài dự kiến không?
5. Lời gọi sang phần `internal` của module khác có vi phạm ranh giới không?

Nếu graph chưa phản ánh đúng kiến trúc mong muốn, **chưa nên dùng đồ thị runtime để kết luận về tương tác module**. Hãy làm rõ phạm vi phát hiện trước.

## 5. Base package ảnh hưởng đến dữ liệu quan sát như thế nào?

Luồng ý tưởng quan trọng:

~~~mermaid
flowchart TB
    P["Gốc package / cấu hình phát hiện"] --> D["Spring Modulith khám phá module"]
    D --> G["Module graph: module ID, API, quan hệ"]
    D --> I["Tích hợp observability hiểu ranh giới module"]
    R["Lời gọi thực tế của Spring beans"] --> I
    I --> O["Micrometer Observation / tracing context"]
    O --> S["Span hoặc metric khi handler được bật"]
    S --> B["Backend observability"]
    G -. "Đối chiếu kiến trúc dự kiến" .-> B
~~~

Spring Modulith Insight có thể sử dụng hiểu biết về application module để hỗ trợ quan sát tương tác khi runtime. Vì vậy, **phạm vi phát hiện module là đầu vào để quy chiếu các hành vi được instrument vào module logic**.

Song cần phân biệt ba mức:

- **Có module trong graph**: chứng minh module được nhận diện theo cấu trúc và cấu hình hiện tại.
- **Có observation/span của module**: chứng minh một điểm instrument liên quan đã chạy và được ghi nhận theo sampling/cấu hình.
- **Có dữ liệu trong backend**: chứng minh telemetry đã đi qua exporter, mạng, collector (nếu có) và hệ thống lưu trữ đủ để truy vấn.

Không có mối suy luận tự động theo chiều ngược lại. Ví dụ, thiếu span có thể do thiếu instrumentation, trace bị sampling bỏ, exporter lỗi hoặc request chưa đi qua đoạn code đó.

### Ví dụ diễn giải trace

Giả sử một request tạo đơn gọi API module `inventory`. Trace hiển thị trong backend có thể trông như sau:

~~~text
service.name = shop-application
traceId      = a71f...  (minh họa)

HTTP POST /orders                    160 ms
└─ [module: order] placeOrder        120 ms
   └─ [module: inventory] check      35 ms
~~~

Đây là **sơ đồ minh họa về cách đọc dữ liệu**, không phải cam kết tên span hay tên tag mặc định của Spring Modulith. Tên span/thuộc tính thực tế phụ thuộc phiên bản, loại instrumentation và cấu hình Micrometer/tracing. Hãy kiểm tra output thật trước khi viết truy vấn hoặc dashboard.

Một dấu vết như trên giúp đặt câu hỏi: “Luồng xử lý của `order` có đi qua API `inventory` không?”. Nó **không thay thế** kiểm tra graph, vì lời gọi runtime được ghi nhận chỉ là một phần lưu lượng, còn graph cho biết quan hệ tĩnh dự kiến.

## 6. Module ID không phải service.name

Đây là khác biệt đặc biệt quan trọng khi quan sát **modular monolith**.

Trong một tiến trình Spring Boot, các module `order`, `inventory` và `billing` thường cùng chạy trong một **ứng dụng/dịch vụ**. Vì vậy:

| Trường hoặc khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Package gốc ứng dụng | `com.example.shop` | Vị trí trong cấu trúc Java |
| Module identifier | `inventory` | Ranh giới logic bên trong ứng dụng |
| Package gốc module | `com.example.shop.inventory` | Phần package mà module sở hữu |
| Telemetry `service.name` | `shop-application` | Danh tính dịch vụ phát telemetry |
| Span name | Tên thao tác thực thi được instrument | Dùng đọc hoạt động của một phần request |
| `traceId` | ID của một trace | Ghép những span cùng ngữ cảnh theo trace |
| Business ID | `orderId`, `eventId` | Định danh dữ liệu nghiệp vụ, xử lý lặp và đối soát |

**Không mặc định gán `service.name=inventory`** chỉ vì request đi qua module `inventory`: trong modular monolith, các module thường cùng một service identity. Thuộc tính module (nếu instrumentation cung cấp) hoặc nhãn nghiệp vụ do ứng dụng định nghĩa mới là chỗ phân biệt chúng.

Tên `service.name` thường được cấu hình qua tài nguyên telemetry hoặc cơ chế tự cấu hình của stack quan sát. Nó **không nhất thiết** giống tên Java package, tên module hay tên artifact Maven.

### Khi tự gắn nhãn module

Với một hoạt động chưa được instrumentation tự động ghi nhận, có thể dùng Micrometer Observation và một **tag hữu hạn**:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

class InventoryOperation {
    private final ObservationRegistry registry;

    InventoryOperation(ObservationRegistry registry) {
        this.registry = registry;
    }

    void reserve() {
        Observation.createNotStarted("shop.inventory.reserve", registry)
                .lowCardinalityKeyValue("application.module", "inventory")
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(this::doReserve);
    }

    private void doReserve() {
        // Thực thi nghiệp vụ; đặt xử lý lỗi/transaction phù hợp ở mã thật.
    }
}
~~~

Ở đây `application.module` là **nhãn do ví dụ chủ động đặt**, không phải tên tag tự động được Spring Modulith bảo đảm tạo ra. Cần thống nhất quy ước nhãn trong ứng dụng để dashboard không chia đôi dữ liệu thành `inventory`, `Inventory`, `com.example.shop.inventory` và những tên tương đương.

Không dùng `orderId`, email, `traceId` hoặc đường dẫn chứa ID người dùng làm **low-cardinality metric tags**: các giá trị nhiều biến thể khiến số time series tăng mạnh. Nếu cần truy một đơn riêng, hãy dùng log/trace attributes theo chính sách dữ liệu hoặc truy nguồn dữ liệu nghiệp vụ.

## 7. Khi base package đặt sai: ba tình huống dễ gặp

### Tình huống A — Lớp ứng dụng nằm quá sâu

Thay vì đặt lớp khởi động ở `com.example.shop`, nhóm phát triển chuyển nó xuống `com.example.shop.bootstrap`:

~~~text
com.example.shop/
├── bootstrap/
│   └── ShopApplication.java   # @SpringBootApplication
├── order/
├── inventory/
└── billing/
~~~

Nếu cơ chế phát hiện module lấy package chứa `ShopApplication` làm gốc, nó sẽ nhìn từ `com.example.shop.bootstrap` và có thể **không khám phá được các package ngang hàng** như `order`, `inventory`, `billing`. Spring Boot component scan mặc định cũng có thể bỏ qua các sibling packages này.

**Dấu hiệu:** module graph thiếu module mong đợi, application context thiếu bean nếu scan không mở rộng, hoặc thiếu thông tin module trong observability. Cần kiểm tra discovery và component scan **riêng rẽ**, bởi một cấu hình `scanBasePackages` rộng hơn có thể làm ứng dụng tạo bean mà chưa giải quyết phạm vi module discovery.

**Cách xử lý thường phù hợp:** đặt lớp ứng dụng ở package cha bao quát các module hoặc cấu hình rõ phạm vi module discovery bằng cơ chế được phiên bản Spring Modulith sử dụng. Sau đó sinh lại graph và so sánh.

### Tình huống B — Gốc rộng, package kỹ thuật biến thành module

~~~text
com.example.shop/
├── ShopApplication.java
├── order/
├── inventory/
├── billing/
├── config/
├── util/
└── persistence/
~~~

Với chiến lược xem mỗi subpackage trực tiếp là module, các package `config`, `util`, `persistence` có thể bị nhận diện như module logic. Điều này **không tự chứng minh kiến trúc sai**: đôi khi đó là các module hạ tầng có chủ đích; nhưng nếu chúng chỉ là phần tổ chức kỹ thuật dùng chung, graph có thể trở nên nhiễu.

**Tác động lên dữ liệu quan sát:** các ranh giới hiển thị không phản ánh cách nhóm phát triển phân chia miền nghiệp vụ. Chẳng hạn, thông tin được gắn theo module `persistence` có thể ít hữu ích hơn thông tin theo miền `order`. Không nên sửa bằng cách tùy tiện đổi nhãn telemetry mà chưa thống nhất lại ranh giới module trong code.

**Cách xử lý:** thiết kế lại vị trí các package kỹ thuật, xác định rõ module có chủ đích, hoặc cấu hình chiến lược phát hiện/module API tương ứng. Xác minh kết quả bằng graph và test.

### Tình huống C — Component scan rộng hơn module detection

~~~java
package com.example.shop.bootstrap;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.shop")
class ShopApplication {
}
~~~

Cấu hình trên có thể giúp Spring Boot tìm các bean dưới `com.example.shop`; tuy nhiên nó **không bảo đảm** Spring Modulith sẽ suy ra cùng phạm vi base package cho module graph, vì hai chức năng được điều khiển bởi hai cơ chế khác nhau. Không nên xem việc ứng dụng khởi động được là phép kiểm tra cấu hình module graph.

Trong ba tình huống, giải pháp chung là **kiểm tra kết quả thực tế của module detection**; sau đó mới kết luận về phạm vi instrumentation và telemetry.

## 8. Thay đổi package ảnh hưởng gì đến dashboard và alert?

Giả sử nhóm refactor từ:

~~~text
com.example.shop.inventory/
~~~

sang:

~~~text
com.example.shop.stock/
~~~

Nếu cách khám phá mặc định nhận diện module qua các subpackage trực tiếp, identifier có thể đổi từ `inventory` sang `stock`. Điều này có thể ảnh hưởng:

- **Module graph/tài liệu**: nút và cạnh được thể hiện theo tên hoặc ranh giới mới.
- **Điểm instrumentation hiểu module**: dữ liệu có liên quan tới module cũ/mới có thể được gán khác tùy tích hợp.
- **Nhãn metric tự định nghĩa**: nếu còn gắn `application.module=inventory` thủ công trong code, dashboard có nguy cơ lệch với module graph mới.
- **Truy vấn và alert**: bộ lọc theo tên module có thể bỏ sót dữ liệu mới hoặc coi tên mới là một chuỗi riêng.
- **Log điều tra**: trường module trong log nếu là chuỗi cứng có thể không phản ánh cấu trúc đã refactor.

Tuy nhiên, **không phải mọi thay đổi Java package đều làm đổi mọi tên telemetry**: ví dụ `service.name` có thể giữ nguyên, tên metric thủ công cũng có thể không đổi, và trace ID không có quan hệ cấu trúc với package.

Quy trình refactor hợp lý:

1. Xác định module identity mong muốn sau thay đổi.
2. Đổi package, API và điểm phụ thuộc; chạy xác minh graph.
3. Kiểm tra instrumentation và những nhãn/tên operation đang xuất thực tế.
4. Cập nhật dashboard/alert có liên quan và theo dõi giai đoạn dữ liệu mang tên cũ–mới.
5. Ghi nhận sự thay đổi ngữ nghĩa để người vận hành không nhầm lẫn giữa lỗi hệ thống và đổi tên module.

## 9. Base package, event và context propagation

Một application event là cách giao tiếp giữa các module mà không cần module phát gọi trực tiếp từng consumer. Ví dụ:

~~~text
order (phát OrderPlaced)
   ├── inventory (listener giữ hàng)
   └── billing   (listener chuẩn bị thanh toán)
~~~

**Base package giúp xác định module sở hữu lớp phát sự kiện, kiểu event và listener**, thông qua cấu trúc các application module được nhận diện. Tuy nhiên, nó **không tự đảm bảo**:

- Mọi event đều được lưu bền hoặc có event publication registry.
- Listener chạy thành công hay chạy đúng một lần.
- Có metrics riêng theo loại event và consumer.
- Span của listener bất đồng bộ luôn nằm cùng trace với request HTTP.

Ví dụ cùng một request:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as order
    participant I as inventory listener
    participant T as Tracing / Metrics
    C->>O: POST /orders
    O->>T: HTTP/order observation
    O->>O: publish OrderPlaced
    O-->>C: HTTP response
    Note over O,I: Listener có thể chạy sau commit, trên thread khác
    O-->>I: OrderPlaced
    I->>T: listener processing observation
    I->>I: reserve stock
~~~

Trong lúc debug, nhóm vận hành có thể biết `inventory` là consumer vì cấu trúc code và graph liên quan; nhưng việc **nối trace** giữa request gốc và listener còn phụ thuộc **context propagation** qua executor hoặc broker. Nếu thiếu propagation, listener có thể sinh trace ID mới; khi đó cần thêm correlation/event ID phù hợp trong log và dữ liệu nghiệp vụ.

Event metrics và publication state cũng là hai thứ khác nhau. Ví dụ, counter `event.processing.failure` chỉ đếm lượt xử lý lỗi được instrument; nó không tự cho biết còn bao nhiêu publication chưa hoàn tất. Nếu dùng Spring Modulith Event Publication Registry, trạng thái publication phải được theo dõi qua phần tích hợp được cấu hình; trong khi metric về lượt chạy consumer có thể do ứng dụng tự xây dựng.

## 10. Đối chiếu module graph với telemetry: quy trình thực hành

Giả sử team muốn trả lời: “Vì sao tạo đơn chậm và liệu có tương tác ngoài dự kiến giữa các module?”

~~~mermaid
flowchart TD
    Graph["1. Sinh module graph từ đúng base package"] --> Expected["2. Xác định các module / API / phụ thuộc dự kiến"]
    Expected --> Traffic["3. Tạo request đi qua các module"]
    Traffic --> Observed["4. Xem trace, metrics và logs"]
    Observed --> Compare{"5. So khớp được các bước?"}
    Compare -->|"Có"| Validate["6. Kiểm tra độ trễ, lỗi và kết quả nghiệp vụ"]
    Compare -->|"Không"| Investigate["Kiểm tra detection, instrumentation, sampling, exporter và propagation"]
    Investigate --> Observed
~~~

### Bước 1 — Chốt phạm vi kiến trúc

Kiểm tra lớp ứng dụng gốc, danh sách application module và module graph sau `ApplicationModules.of(...)`. Không chuyển sang telemetry khi chưa biết chính xác một thao tác thuộc module nào về mặt thiết kế.

### Bước 2 — Xác định tương tác dự kiến

Ghi nhận các tuyến nghiệp vụ và những API công khai được gọi. Nếu `order` gọi `inventory.checkAvailability()`, một tương tác module đã được mô tả trong code; nếu `order` trực tiếp truy cập lớp trong `inventory.internal`, đó là dấu hiệu cần kiểm tra quy tắc ranh giới.

### Bước 3 — Kích hoạt observation và xem output thực

Tùy phiên bản, dự án có thể dùng Spring Modulith Insight, Spring Boot Actuator, Micrometer tracing bridge và exporter. Gửi request có kiểm soát để thấy hoạt động ở runtime. Mỗi thành phần có vai trò riêng:

| Thành phần | Mục đích kiểm chứng | Điều không nên suy luận |
| --- | --- | --- |
| `ApplicationModules` / `Documenter` | Module có được phát hiện và graph có hợp lý không? | Module ấy chắc chắn đã chạy trong request vừa rồi |
| Spring Modulith Insight | Có ghi nhận tương tác module trong phạm vi hỗ trợ không? | Mọi method call đều được instrument |
| Actuator `/actuator/metrics` | Có meter và giá trị đang được ghi trong ứng dụng không? | Tất cả meter đã được scrape và lưu vào Prometheus |
| Actuator `/actuator/prometheus` (nếu cấu hình) | Ứng dụng có xuất metrics đúng định dạng cho Prometheus không? | Có trace được export |
| Trace backend | Request đi qua những span nào được instrument/lấy mẫu? | Đã thấy đầy đủ mọi hoạt động, kể cả listener async |
| Logs và event registry (nếu có) | Lỗi, correlation và trạng thái xử lý event | Có thể thay thế nguồn dữ liệu nghiệp vụ cuối cùng |

### Bước 4 — So kết quả với trạng thái thật

Nếu HTTP request trả thành công nhưng listener giữ hàng lỗi, module graph vẫn có thể đúng. Vấn đề nằm ở một luồng nghiệp vụ sau commit. Cần bổ sung số liệu xử lý listener, trace/log tương quan, publication state (nếu có) và dữ liệu giữ hàng thực tế, thay vì quy kết lỗi cho cách đặt package.

## 11. Bài tập minh họa: base package đổi, telemetry hiểu khác ra sao?

Thực hiện trong môi trường thực hành; không cần có traffic production.

**Lần A — Cấu trúc chuẩn:**

~~~text
com.example.shop.ShopApplication
com.example.shop.order.OrderService
com.example.shop.inventory.InventoryService
~~~

Chạy kiểm tra module graph. Dự kiến theo quy ước mặc định: `order` và `inventory` là hai module. Tạo một request đi qua cả hai, rồi quan sát dữ liệu đang được instrument và ghi nhận các tên module thực xuất hiện.

**Lần B — Chuyển lớp khởi động xuống package con:**

~~~text
com.example.shop.launcher.ShopApplication
com.example.shop.order.OrderService
com.example.shop.inventory.InventoryService
~~~

Chạy lại kiểm tra module graph với lớp khởi động làm điểm vào. So sánh tập module; nếu discovery bị hẹp, giải thích vì sao. Đừng chỉ kiểm tra HTTP có phản hồi: component scan và module discovery có thể có phạm vi khác nhau.

**Lần C — Sửa phạm vi phát hiện:**

Đưa lớp khởi động về gốc phù hợp hoặc cấu hình phát hiện module rõ ràng theo phiên bản Spring Modulith đang dùng. Xác minh graph một lần nữa rồi chạy cùng request. So sánh các tín hiệu thực tế của cùng một hành vi nghiệp vụ.

Ghi kết quả vào bảng:

| Nội dung so sánh | Lần A | Lần B | Lần C |
| --- | --- | --- | --- |
| Package chứa lớp `@SpringBootApplication` | … | … | … |
| Base package/module detection thực tế | … | … | … |
| Module graph nhìn thấy | … | … | … |
| Spring beans có được scan không? | … | … | … |
| Span/metric/log có module attribution nào? | … | … | … |
| Phát hiện bất thường hoặc giới hạn quan sát | … | … | … |

Lưu ý: nếu ở lần B ứng dụng không khởi động vì thiếu bean, đó cũng là kết quả có ý nghĩa — bạn cần giải thích bằng **component scan**. Không ép tạo telemetry ở một kịch bản chưa có request chạy thật.

## 12. Sai lầm thường gặp

| Nhận định dễ sai | Điều đúng hơn |
| --- | --- |
| “Đặt `@SpringBootApplication` ở đâu cũng giống nhau.” | Vị trí ảnh hưởng các quy ước package. Hãy kiểm tra component scan và Modulith module detection riêng. |
| “Có package là có module.” | Module phụ thuộc gốc phát hiện và chiến lược phát hiện; package con thường thuộc module cha. |
| “Mọi module đều là một microservice.” | Application module là ranh giới logic; nhiều module có thể cùng một ứng dụng/tiến trình và cùng `service.name`. |
| “Có module trong graph thì phải có span.” | Span cần lời gọi thực tế được instrument, tracing handler, sampling và đường export phù hợp. |
| “Không thấy span nghĩa là không gọi module.” | Có thể thiếu instrumentation, context, sampling hoặc exporter. |
| “Đổi tên package không ảnh hưởng dashboard.” | Có thể đổi module identity và nhãn thống kê; cần đối chiếu dữ liệu thực tế. |
| “Mở rộng `scanBasePackages` là đủ để Modulith nhận ra module.” | Hai cơ chế có thể độc lập; phải kiểm tra module graph được phát hiện. |
| “Base package quyết định trace ID.” | Trace ID do tracing context tạo hoặc truyền; base package chủ yếu giúp nhận diện cấu trúc/module. |
| “Base package bảo đảm event xử lý tin cậy.” | Độ tin cậy event phụ thuộc transaction, publication registry, retry, idempotency và consumer. |

## 13. Checklist khi thiết kế module observability

1. **Chốt application root:** lớp ứng dụng chính và các package module có cùng gốc rõ ràng.
2. **Nhận diện module:** xác nhận mỗi subpackage trực tiếp có đúng là một application module có chủ đích.
3. **Kiểm thử ranh giới:** chạy `ApplicationModules.verify()` để phát hiện phụ thuộc không hợp lệ trong phạm vi hỗ trợ.
4. **Sinh tài liệu:** tạo graph, kiểm tra module identifiers, API công khai và cạnh phụ thuộc.
5. **Chọn điểm đo:** xác định HTTP, lời gọi API module, event listener và thao tác nghiệp vụ quan trọng.
6. **Đặt nhãn nhất quán:** nếu tự gắn `application.module`, dùng tên module ổn định và tránh high-cardinality metric tags.
7. **Kiểm tra telemetry:** đối chiếu module graph với trace/metrics/logs sau khi tạo traffic có kiểm soát.
8. **Kiểm tra async:** xác nhận context propagation qua executor/broker và quan sát riêng lỗi của consumer.
9. **Quản lý refactor:** khi thay đổi package hoặc module ID, đánh giá ảnh hưởng tới dashboard, alert và tài liệu.
10. **Kiểm chứng nghiệp vụ:** dùng dữ liệu ứng dụng làm nguồn xác nhận trạng thái cuối cùng, đặc biệt với quy trình event-driven.

### Câu hỏi tự kiểm tra

1. Tại sao `order.internal` thường không phải một application module ngang hàng với `order`?
2. Việc đặt `ShopApplication` tại `com.example.shop.bootstrap` có thể ảnh hưởng gì đến module discovery? Điều đó giống hay khác component scan?
3. Trong modular monolith, tại sao `service.name` có thể giữ nguyên khi yêu cầu đi từ `order` sang `inventory`?
4. Module graph cho thấy có phụ thuộc từ `order` sang `inventory`, nhưng trace vừa xem không có span của `inventory`. Hãy nêu ít nhất ba nguyên nhân hợp lý.
5. Khi đổi package `inventory` thành `stock`, cần kiểm tra những gì để dashboard và alert vẫn diễn giải đúng?
6. Một listener chạy sau commit có thể nhận biết module sở hữu thông qua package; điều gì còn cần thiết để nối trace của listener với request gốc?

## 14. Tổng kết

Trong Spring Modulith, **base package là đầu vào quan trọng của quá trình phát hiện application module**. Từ các package con, công cụ xây dựng module graph để diễn đạt ranh giới, API và quan hệ phụ thuộc. Khi bật các tích hợp observability phù hợp, metadata này còn giúp chúng ta diễn giải những lời gọi hoặc sự kiện **được instrument** theo từng module.

Phân biệt rõ **package → module identity → instrumentation → telemetry → backend** sẽ giúp tránh các kết luận nhầm lẫn: module không xuất hiện trong graph chưa chắc không có code chạy; module có trong graph chưa chắc đã có span; một ứng dụng có nhiều module vẫn có thể mang cùng `service.name`. Cách làm đáng tin cậy là kiểm chứng cấu trúc bằng Spring Modulith trước, quan sát hành vi runtime sau, và đối chiếu cả hai với kết quả nghiệp vụ thực tế.
