# Định danh module ổn định khi refactor package

> **Chương:** Nhiều module  
> **Phạm vi:** Spring Modulith — tài liệu kiến trúc, Actuator và quan sát tương tác module  
> **Tình huống:** Đổi cấu trúc Java package mà vẫn giữ định danh logic của application module.

## 1. Vì sao định danh module cần ổn định?

Trong ứng dụng Spring Boot tổ chức theo mô-đun, Spring Modulith phát hiện **application module** từ các package và xây dựng mô hình quan hệ phụ thuộc giữa chúng. Khi không chỉ định thêm, định danh module thường được suy ra từ vị trí package dưới root của ứng dụng. Cách này tiện khi khởi đầu, nhưng dễ gây thay đổi ngoài ý muốn khi refactor.

Ví dụ nhóm phát triển đổi tên package `com.acme.store.orders` thành `com.acme.store.sales` vì muốn mô tả nghiệp vụ chính xác hơn. Nếu module dùng tên mặc định theo package, định danh có thể đổi từ `orders` sang `sales` dù trách nhiệm nghiệp vụ vẫn như cũ. Hậu quả có thể lan sang các nơi đang tham chiếu định danh đó:

- Khai báo `allowedDependencies` của module khác.
- Biểu đồ phụ thuộc và tài liệu module được sinh ra.
- Khóa tên module và các tham chiếu `dependencies.target` trong Spring Boot Actuator.
- Nhãn `module.identifier` trong trace/metric và tên metric gắn với module.
- Kiểm thử hoặc công cụ nội bộ dùng tên module để xác định ranh giới kiến trúc.

**Giải pháp:** định nghĩa `id` có chủ đích cho module, xem đó là định danh logic lâu dài. Khi chỉ đổi cách bố trí source code, giữ `id` và di chuyển metadata module đến package mới.

Bài dùng khả năng `@ApplicationModule(id = "...")` của Spring Modulith, có trong các phiên bản hỗ trợ định danh module riêng (chẳng hạn 1.3.x trở lên). Hãy dùng bộ dependency Spring Boot/Spring Modulith tương thích và thống nhất phiên bản của các artifact. Ví dụ tập trung vào module model; không bắt buộc triển khai microservices.

### Phân biệt bốn khái niệm

| Khái niệm | Ví dụ trước refactor | Ví dụ sau refactor | Chính sách |
|---|---|---|---|
| **Module identifier (ID)** | `orders` | `orders` | Giữ nguyên nếu trách nhiệm nghiệp vụ không đổi |
| Java base package | `com.acme.store.orders` | `com.acme.store.sales` | Có thể đổi khi tái cấu trúc code |
| Display name | `Quản lý đơn hàng` | `Quản lý đơn hàng` | Có thể đổi câu chữ nhưng nên quản lý như nhãn hiển thị |
| Tên class/API Java | `OrderManagement` | `OrderManagement` hoặc tên mới | Phụ thuộc tính tương thích với caller thực tế |

`id` không phải `displayName` và cũng không tự động là tên package. ID dùng để quy chiếu module; tên hiển thị phục vụ người đọc, còn package quyết định nơi module được phát hiện và các loại Java mà nó sở hữu.

## 2. Ví dụ trước khi refactor

Giả sử ứng dụng có root package `com.acme.store` và hai module:

~~~text
src/main/java/com/acme/store/
├── StoreApplication.java
├── orders/
│   ├── package-info.java
│   ├── OrderManagement.java
│   ├── OrderPlaced.java
│   └── internal/
│       └── OrderRepository.java
└── billing/
    ├── package-info.java
    ├── BillingService.java
    └── internal/
        └── InvoiceRepository.java
~~~

Sơ đồ ở mức module:

~~~mermaid
flowchart LR
    B["Module ID: billing\nPackage: com.acme.store.billing"]
    O["Module ID: orders\nPackage: com.acme.store.orders"]
    B -->|gọi API hoặc lắng nghe sự kiện| O
~~~

Theo chiến lược phát hiện mặc định, các package con trực tiếp của root có thể trở thành module. Tuy nhiên, **không nên dựa vào tên thư mục như một định danh vĩnh viễn** nếu source code được refactor thường xuyên.

Đặt metadata trong `orders/package-info.java` ngay từ trước khi đổi package:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng"
)
package com.acme.store.orders;
~~~

Với module `billing`, đặt `billing/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "billing",
    displayName = "Xuất hóa đơn",
    allowedDependencies = "orders"
)
package com.acme.store.billing;
~~~

Ý nghĩa:

1. `id = "orders"` và `id = "billing"` là định danh logic. Với module có ID rõ ràng, tên package không cần trùng ID.
2. `displayName` phục vụ tài liệu hoặc giao diện; không nên dùng làm khóa quy chiếu trong automation.
3. `allowedDependencies = "orders"` tham chiếu module theo tên logic và cho phép `billing` phụ thuộc vào API công khai của `orders`. Việc khai báo chỉ hạn chế phụ thuộc được phép; nó không tạo ra phụ thuộc trong source code.
4. Mỗi ID phải duy nhất trong tập module được phát hiện, không rỗng và không chứa chuỗi `::` vì `::` được dùng để phân tách module với named interface.

**Lưu ý:** API root package mặc định là phần giao diện truy cập từ module khác; các class trong `internal` không vì có ID cố định mà trở nên được truy cập công khai. Nếu cần công bố thêm một phần nội bộ cho module khác, cân nhắc `@NamedInterface` và ràng buộc truy cập cụ thể.

## 3. Refactor package mà giữ nguyên ID

Yêu cầu: chuyển module `orders` sang `sales` nhưng vẫn phục vụ cùng nghiệp vụ đơn hàng. Cấu trúc sau khi di chuyển:

~~~text
src/main/java/com/acme/store/
├── StoreApplication.java
├── sales/
│   ├── package-info.java            # ID vẫn là "orders"
│   ├── OrderManagement.java
│   ├── OrderPlaced.java
│   └── internal/
│       └── OrderRepository.java
└── billing/
    ├── package-info.java            # allowedDependencies vẫn là "orders"
    └── BillingService.java
~~~

Nội dung `sales/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng"
)
package com.acme.store.sales;
~~~

Metadata trong `billing/package-info.java` giữ nguyên:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "billing",
    displayName = "Xuất hóa đơn",
    allowedDependencies = "orders"
)
package com.acme.store.billing;
~~~

Như vậy:

~~~text
Trước: module ID = orders  ↔  base package = com.acme.store.orders
Sau:   module ID = orders  ↔  base package = com.acme.store.sales

Billing -> orders vẫn là quan hệ module logic hợp lệ.
~~~

Sơ đồ sau khi refactor:

~~~mermaid
flowchart LR
    B["Module ID: billing\nPackage: com.acme.store.billing"]
    O["Module ID: orders\nPackage: com.acme.store.sales"]
    B -->|vẫn tham chiếu "orders"| O
~~~

**Các thao tác refactor Java vẫn bắt buộc:** di chuyển class, sửa khai báo `package`, sửa `import` trong các module gọi đến, cập nhật cấu hình quét package, mapping, reflection hoặc serialization nếu đang tham chiếu tên class cũ. `@ApplicationModule(id = "orders")` chỉ giữ ổn định định danh logic của Modulith; nó không tạo alias cho class Java cũ và không tự sửa các đường dẫn/configuration khác.

### Trình tự refactor an toàn

1. **Ghi nhận hiện trạng.** Xuất danh sách module ID, base package, quan hệ phụ thuộc, module graph và các chỉ số đang dùng trong dashboard.
2. **Gắn ID rõ ràng trước khi di chuyển.** Nếu hệ thống hiện dùng ID mặc định `orders`, khai báo tường minh `id = "orders"` và xác minh mô hình trước khi refactor.
3. **Di chuyển package và metadata cùng nhau.** Đổi `package-info.java` sang `package com.acme.store.sales;`. Tránh để lại bản `package-info.java` cũ khiến công cụ hiểu nhầm còn module khác.
4. **Sửa tham chiếu Java.** Thực hiện refactor symbol/import, cấu hình component scan, các tên class dùng bằng reflection và test fixtures liên quan.
5. **Chạy xác minh cấu trúc.** Mô hình phải nhận diện đúng hai module; `orders` vẫn có ID `orders` nhưng `basePackage` mới.
6. **So sánh tài liệu và tín hiệu runtime.** Module graph không tự nhiên tăng module lạ, Actuator giữ khóa `orders`, trace/metric dùng `module.identifier = orders`.
7. **Đánh giá trường hợp đặc biệt.** Nếu thật sự chia một module thành hai ranh giới nghiệp vụ mới, cần thiết kế ID và kế hoạch di trú riêng; không dùng một ID cũ để che giấu thay đổi kiến trúc.

Nếu di chuyển module vào package lồng sâu hơn, chẳng hạn `com.acme.store.commerce.sales`, cần kiểm tra chiến lược phát hiện module: mặc định Spring Modulith thường xem các package con trực tiếp của root là module, nên thêm một cấp package có thể làm thay đổi ranh giới được phát hiện. Có thể chọn chiến lược `spring.modulith.detection-strategy=explicitly-annotated` với annotation trên đúng các package cần làm module, hoặc cấu hình phát hiện khác phù hợp kiến trúc. Chạy lại kiểm thử cấu trúc sau khi thay đổi chiến lược.

## 4. Kiểm chứng bằng ApplicationModules và kiểm thử

Tạo mô hình module từ lớp khởi động ứng dụng:

~~~java
package com.acme.store;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
}
~~~

Trong mã kiểm thử (ví dụ `src/test/java/com/acme/store/ModuleIdentityTest.java`):

~~~java
package com.acme.store;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentityTest {

    @Test
    void idsRemainStableWhenOrderPackageIsMoved() {
        ApplicationModules modules = ApplicationModules.of(StoreApplication.class);

        // Kiểm tra chu kỳ phụ thuộc, truy cập API nội bộ và
        // các ràng buộc allowedDependencies đã khai báo.
        modules.verify();

        Map<String, String> modulePackages = modules.stream()
            .collect(Collectors.toMap(
                module -> module.getIdentifier().toString(),
                module -> module.getBasePackage().getName()
            ));

        assertTrue(modulePackages.keySet().containsAll(
            Set.of("orders", "billing")
        ));

        // ID logic không đổi, dù package chứa module đã đổi.
        assertEquals("com.acme.store.sales", modulePackages.get("orders"));
        assertEquals("com.acme.store.billing", modulePackages.get("billing"));
    }
}
~~~

Test trên kiểm tra ba điều khác nhau:

- `ApplicationModules.of(...)` phát hiện mô hình module từ package/metadata.
- `modules.verify()` kiểm tra các vi phạm kiến trúc mà Spring Modulith hỗ trợ: chu kỳ giữa module, truy cập class nội bộ từ module khác và ràng buộc phụ thuộc đã khai báo.
- `module.getIdentifier()` và `module.getBasePackage()` cho thấy **ID vẫn `orders` nhưng base package đã là `sales`**.

Để kiểm tra hồi quy trong hệ thống nhiều module, có thể lưu một danh sách ID kỳ vọng trước refactor (snapshot được review trong mã test) rồi so với tập ID sau refactor. Nếu danh sách có thêm/bớt phần tử, chỉ cho phép khi đó là quyết định thay đổi kiến trúc có chủ đích.

### Phân biệt kiểm tra ổn định ID và kiểm tra tương thích Java

Bài test trên **không chứng minh** API Java không thay đổi. Một module có ID ổn định vẫn có thể đổi method public, kiểu dữ liệu hoặc hành vi sự kiện. Vì thế cần thêm unit/integration test của caller, kiểm thử hợp đồng sự kiện, kiểm tra migration cấu hình nếu các contract này nằm trong phạm vi refactor.

## 5. Tài liệu module graph sau khi đổi package

Spring Modulith có `Documenter` để sinh sơ đồ quan hệ module và Module Canvas. Với dependency `spring-modulith-docs` trong test scope (hoặc `spring-modulith-starter-test` nếu phiên bản đang dùng đã mang theo), có thể tạo test tài liệu:

~~~java
package com.acme.store;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTest {

    @Test
    void generateArchitectureDocumentation() {
        var modules = ApplicationModules.of(StoreApplication.class);
        modules.verify();

        new Documenter(modules)
            .writeModulesAsPlantUml()
            .writeIndividualModulesAsPlantUml()
            .writeModuleCanvases();
    }
}
~~~

Kết quả được dùng để kiểm tra sau refactor:

| Thuộc tính trong tài liệu | Kết quả mong đợi |
|---|---|
| Tập module | Vẫn gồm `orders` và `billing` |
| Quan hệ logic | `billing → orders` vẫn tương ứng với phụ thuộc nguồn |
| Vị trí package | Module `orders` được phản ánh ở `com.acme.store.sales` |
| API / internal | Các phần được công bố và phần nội bộ tương ứng cấu trúc mới |
| Tên hiển thị | Có thể giữ `Quản lý đơn hàng` để người đọc nhận ra nghiệp vụ |

Khi so sánh PlantUML hoặc Module Canvas giữa hai phiên bản, cần phân biệt **thay đổi kỹ thuật có chủ đích** (đường dẫn package, tên class) và **thay đổi định danh logic ngoài ý muốn** (một node `orders` biến mất và node `sales` xuất hiện). Không đòi hỏi mọi ký tự trong tài liệu sinh ra giống hệt nhau: sơ đồ có thể chứa chi tiết cấu trúc Java vốn được phép thay đổi.

## 6. Kiểm tra ở Actuator: ID ổn định, basePackage thay đổi

Spring Modulith có thể công bố cấu trúc module bằng endpoint Actuator `modulith`. Trong ứng dụng đã bật `spring-modulith-starter-insight`, hoặc đã khai báo các dependency Actuator và Modulith phù hợp, cấu hình ví dụ cho môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith
~~~

Truy cập:

~~~http
GET /actuator/modulith HTTP/1.1
Host: localhost:8080
~~~

Payload minh họa trước khi refactor (lược bớt thông tin):

~~~json
{
  "orders": {
    "displayName": "Quản lý đơn hàng",
    "basePackage": "com.acme.store.orders",
    "dependencies": []
  },
  "billing": {
    "displayName": "Xuất hóa đơn",
    "basePackage": "com.acme.store.billing",
    "dependencies": [
      {
        "target": "orders",
        "types": ["USES_COMPONENT"]
      }
    ]
  }
}
~~~

Sau refactor đúng kỳ vọng:

~~~json
{
  "orders": {
    "displayName": "Quản lý đơn hàng",
    "basePackage": "com.acme.store.sales",
    "dependencies": []
  },
  "billing": {
    "displayName": "Xuất hóa đơn",
    "basePackage": "com.acme.store.billing",
    "dependencies": [
      {
        "target": "orders",
        "types": ["USES_COMPONENT"]
      }
    ]
  }
}
~~~

`orders` vẫn là khóa của module trong JSON; `basePackage` đổi. `billing.dependencies[].target` vẫn tham chiếu `orders`, vì module ở cấp logic không đổi. `types` trong ví dụ mang tính minh họa; giá trị thực phản ánh loại phụ thuộc mà Spring Modulith phát hiện (chẳng hạn dùng bean, nghe event hoặc phụ thuộc kiểu dữ liệu).

**Lưu ý triển khai:** Actuator không mặc nhiên công bố mọi endpoint qua HTTP; cần dependency, cấu hình exposure và quyền truy cập tương ứng. Metadata kiến trúc có thể tiết lộ cấu trúc hệ thống, nên giới hạn endpoint này theo cơ chế kiểm soát truy cập của môi trường thực tế.

## 7. Đối chiếu metric, tracing và context propagation

Phần observability của Spring Modulith giúp theo dõi lời gọi vào API của module và sự kiện được công bố. Khi có Micrometer/Tracing và exporter thích hợp, span có thể chứa các tag như:

| Tag hoặc metric | Ý nghĩa trong đợt refactor |
|---|---|
| `module.identifier` | Định danh module; kỳ vọng luôn là `orders` |
| `module.name` | Tên module phục vụ quan sát; cần kiểm tra nếu đổi display name |
| `module.invocation-type` | Phân biệt lời gọi bean hoặc event listener |
| `module.method` | Phản ánh method; có thể thay đổi khi refactor tên class/method |
| `module.events.published` | Bộ đếm các domain event được phát hành |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Metric riêng theo ID module và tên đơn giản của loại event |

Nếu không gắn ID rõ ràng, chuỗi metric theo module có thể bị tách thành hai nhóm `orders` và `sales` sau khi chuyển package. Dashboard và alert tham chiếu `module.identifier` hoặc tên metric có thể mất tính liên tục theo module. Với ID cố định, phần nhận diện module được duy trì; dù vậy metric theo tên event hoặc trace theo `module.method` vẫn thay đổi nếu chính class/event/method được đổi tên.

### Trường hợp sự kiện xử lý bất đồng bộ

Giả sử `orders` công bố `OrderPlaced`, còn `billing` nhận sự kiện trên một executor khác:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant E as Event / Executor
    participant B as billing
    O->>E: publish(OrderPlaced)
    E-->>B: xử lý sự kiện bất đồng bộ
    Note over O,B: Trace cần context propagation qua luồng xử lý
~~~

Có **hai vấn đề độc lập** phải kiểm chứng:

1. **Module identity:** module phát hành vẫn được ghi nhận là `orders`, module nhận vẫn là `billing`. Điều này phụ thuộc mô hình module và ID được khai báo.
2. **Trace continuity:** span ở listener có thuộc cùng trace với phần publish hay không. Điều này phụ thuộc cơ chế truyền trace context qua ranh giới thread hoặc message; ID ổn định **không tự động bảo đảm context propagation**.

Khi dùng `@ApplicationModuleListener`, `@Async` hoặc executor riêng, cần kiểm tra cấu hình Micrometer Context Propagation/Tracing của Spring Boot và executor thực tế. Với message broker, cần kiểm tra việc truyền/khôi phục trace headers. Nên quan sát một giao dịch mẫu và so sánh `traceId`, `parentSpanId` cùng `module.identifier` ở từng bước. Tránh kết luận context propagation đúng chỉ vì trên dashboard vẫn xuất hiện đúng tên module.

### Kịch bản giám sát trước và sau refactor

| Kiểm tra | Trước | Sau đúng kỳ vọng |
|---|---|---|
| Span API module đơn hàng | `module.identifier=orders` | Giữ nguyên |
| Metric event gắn module | Chứa `orders` | Vẫn chứa `orders` |
| Tag/tên class, method | Vị trí mã cũ | Được phép đổi theo code |
| Module graph | `billing → orders` | Giữ quan hệ logic |
| Base package | `com.acme.store.orders` | `com.acme.store.sales` |
| Trace qua listener async | Có liên kết context nếu đã cấu hình | Vẫn có liên kết, xác minh riêng |

## 8. Sai lầm thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sau refactor xuất hiện module `sales` thay `orders` | Không khai báo `id` hoặc quên di chuyển annotation | Khai báo `id = "orders"` trên package module mới và xác minh tập ID |
| `allowedDependencies` không còn khớp | Caller dùng tên package mới thay cho ID logic hoặc tham chiếu ID cũ không còn tồn tại | Dùng tên định danh thực từ mô hình module; chạy `modules.verify()` |
| Module bị gộp vào `commerce` | Đưa package xuống sâu nhưng vẫn dùng chiến lược phát hiện trực tiếp | Cấu hình discovery phù hợp và kiểm tra module model |
| Cùng một ID dùng cho hai module | Copy metadata khi tách package nhưng chưa thiết kế ID mới | Mỗi ranh giới module phải có ID duy nhất, xác minh lỗi cấu hình |
| Sơ đồ khác trước dù ID đúng | Package/class hoặc API đã thay đổi hợp lệ | So sánh node/edge logic riêng với chi tiết code |
| Dashboard bị tách dữ liệu | Metric dùng tên event/method/display name đã đổi | Kiểm tra nhãn thực; lập kế hoạch chuyển truy vấn dashboard nếu cần |
| Trace bị đứt khi qua event listener | Thiếu context propagation qua executor/broker | Kiểm thử trace context và cấu hình propagator thích hợp |
| Build pass nhưng tương tác lỗi runtime | Refactor đổi tên class dùng reflection, serialization hoặc scan | Kiểm thử tích hợp và rà soát cấu hình tham chiếu theo chuỗi |

Không dùng `displayName` để cố "giữ tên" khi ID đã đổi. Hai metadata này đảm nhiệm vai trò khác nhau. Đặt `displayName = "orders"` trong module có ID `sales` vẫn không biến nó thành module ID `orders`.

## 9. Thực hành và tiêu chí hoàn thành

**Bài tập:** Ứng dụng có ba module `catalog`, `orders` và `billing`. Module `billing` chỉ được gọi API công khai của `orders`. Hãy chuyển package `com.acme.store.orders` thành `com.acme.store.sales` mà không đổi định danh module `orders`.

Yêu cầu hoàn thành:

1. Đặt ID tường minh cho tất cả module có thể bị ảnh hưởng. ID `orders` không thay đổi trước/sau.
2. Di chuyển metadata `@ApplicationModule` cùng mã nguồn; sửa Java imports mà không làm phát sinh phụ thuộc vào `internal`.
3. Giữ `allowedDependencies = "orders"` ở `billing`; sửa nếu đang tham chiếu tên package không đúng với ID.
4. Chạy test `ApplicationModules.of(StoreApplication.class).verify()` và test snapshot ID/base package.
5. Sinh lại module graph. Tài liệu nhận diện cùng module `orders` tại package mới; các cạnh phụ thuộc được giữ nếu không thay đổi về kiến trúc.
6. Kiểm tra `/actuator/modulith` tại môi trường được phép truy cập. Khóa `orders` và `dependencies.target` được giữ, `basePackage` được đổi.
7. Gửi một tương tác có event và quan sát metric/span: `module.identifier` ổn định; trace context vẫn được truyền qua đoạn bất đồng bộ nếu hệ thống có tracing.

**Câu hỏi suy luận:**

- Khi đổi `com.acme.store.orders` thành `com.acme.store.sales` mà giữ ID `orders`, điều gì cần thay trong source code và điều gì có thể giữ nguyên ở tầng giám sát?
- Nếu đổi cả `id` thành `sales`, những API/metadata nào cần được cập nhật theo, và vì sao dashboard thời gian có thể bị chia chuỗi dữ liệu?
- Nếu `orders` được tách thật sự thành hai module `order-entry` và `order-fulfillment`, vì sao không nên gán cả hai cùng ID `orders`?
- Vì sao có thể nhìn thấy đúng tag `module.identifier=orders` trong hai span nhưng chúng vẫn nằm trong hai trace khác nhau?

## 10. Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): phát hiện module, ranh giới package, `@ApplicationModule`, `allowedDependencies` và named interface.
- [Spring Modulith — API của ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html): ý nghĩa `id` và `displayName`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): quy tắc xác minh cấu trúc module.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): mô hình module, PlantUML và Module Canvas.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, metric, span và các khóa metadata quan sát.

> **Ghi nhớ:** Tên package mô tả **vị trí hiện thực**; `@ApplicationModule(id = "...")` biểu diễn **danh tính logic**. Refactor chỉ thay đổi vị trí code thì nên giữ ID ổn định, sau đó xác minh cả kiến trúc tĩnh lẫn quan sát runtime.
