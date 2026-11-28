# Mở endpoint modulith và đọc module graph

> **Chương:** Thực hành tổng hợp  
> **Công nghệ:** Spring Modulith, Spring Boot Actuator  
> **Bài tập:** Công bố cấu trúc application module ở `/actuator/modulith`, đọc JSON thành sơ đồ phụ thuộc và kiểm chứng ranh giới kiến trúc của ứng dụng.

## 1. Mục tiêu và kết quả cần đạt

Một ứng dụng Spring Boot có thể chia thành các **application module** để hạn chế phụ thuộc chéo, mô tả API công khai và phần hiện thực nội bộ. Spring Modulith phân tích cấu trúc package và quan hệ giữa các module; **Spring Boot Actuator** cho phép công bố mô hình này qua endpoint `modulith` để kiểm tra ở môi trường đang chạy.

Sau bài thực hành, người học có thể:

1. Tạo một ứng dụng mẫu gồm ba module `catalog`, `orders` và `billing`.
2. Thêm dependency để bật Spring Modulith Actuator và cấu hình exposure trong profile `local`.
3. Mở `/actuator/modulith` bằng trình duyệt, `curl` hoặc PowerShell; xác nhận endpoint được phát hiện.
4. Đọc `displayName`, `basePackage`, `dependencies[].target`, `dependencies[].types` để vẽ **module graph**.
5. Phân biệt chiều của **phụ thuộc mã nguồn** với chiều **luồng sự kiện lúc chạy**.
6. Dùng `ApplicationModules.verify()` để kiểm tra quy tắc kiến trúc, và dùng `Documenter` nếu cần tài liệu PlantUML/Module Canvas.
7. Nhận biết giới hạn của graph tĩnh so với Actuator metrics, module entry spans và trace context.

**Tiêu chí cốt lõi:** Lệnh gọi đến endpoint trả JSON có ba module, có cạnh `orders → catalog` và `billing → orders`. Người học giải thích được vì sao cạnh thứ hai có thể ngược chiều luồng sự kiện từ `orders` sang `billing`.

## 2. Hiểu đúng module graph trước khi làm

Spring Modulith mặc định phát hiện application module ở **các package con trực tiếp** dưới root package của lớp `@SpringBootApplication`. Mỗi module có một định danh logic và một base package chứa code. Một dependency từ module A đến module B xuất hiện khi code trong A có một quan hệ mà Modulith xác định được với B.

Ví dụ dự kiến:

~~~mermaid
flowchart LR
    O["orders\ncom.example.shop.orders"]
    C["catalog\ncom.example.shop.catalog"]
    B["billing\ncom.example.shop.billing"]
    O -->|"USES_COMPONENT\nOrders gọi ProductCatalog"| C
    B -->|"EVENT_LISTENER\nBilling nghe OrderPlaced"| O
~~~

**Chiều mũi tên:** `A → B` nghĩa là **A phụ thuộc B**. Nó không nhất thiết có nghĩa request hoặc event đang chạy từ A sang B.

Trong ví dụ này, `orders` gọi trực tiếp một Spring bean của `catalog`, nên `orders → catalog`. Module `billing` có `@EventListener` lắng nghe kiểu `OrderPlaced` công bố bởi `orders`, nên `billing` phụ thuộc vào hợp đồng sự kiện của `orders`. Tuy nhiên, **sự kiện lúc chạy** được publish trong `orders` rồi chuyển đến listener ở `billing`. Hai góc nhìn này không mâu thuẫn.

Module graph ở Actuator là **mô hình kiến trúc** được phát hiện từ code/classpath và metadata, không phải kết quả đếm các cuộc gọi runtime. Graph sẽ không tự sinh thêm cạnh chỉ vì hôm nay có thêm một request HTTP.

## 3. Chuẩn bị phiên bản và dependency

Ví dụ triển khai sử dụng **Java 17, Spring Boot 3.5.x, Spring Modulith 1.4.x và Maven**. Cặp nhánh Boot 3.5 / Modulith 1.4 thuộc nhóm tương thích trong tài liệu chính thức. Dự án sử dụng Boot 4.x nên chọn nhánh Spring Modulith 2.x tương thích và kiểm tra BOM thay vì trộn các nhánh.

Nếu đã có POM từ Spring Initializr với `spring-boot-starter-parent`, hãy thêm các mục sau vào các phần `dependencyManagement` và `dependencies` **hiện có**. Mỗi phần chỉ xuất hiện một lần trong POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>1.4.14</version>
            <scope>import</scope>
            <type>pom</type>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- API HTTP để thử nghiệp vụ -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Cần trên compile classpath để dùng @ApplicationModule. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-core</artifactId>
    </dependency>

    <!-- Insight kéo theo Modulith Actuator, observability và Boot Actuator -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Kiểm tra cấu trúc module và JUnit -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ cần khi muốn sinh sơ đồ và Module Canvas -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-docs</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Lựa chọn tối thiểu:** Nếu chỉ cần **endpoint `modulith`** mà chưa cần module metrics/tracing, có thể thay starter Insight bằng hai dependency runtime:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-actuator</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Chọn **một trong hai cách** cấu hình Actuator: Insight starter *hoặc* Modulith Actuator + Boot Actuator. Nếu chọn Insight, không cần khai báo trùng các phần đã được starter kéo vào. `spring-modulith-core` được giữ ở compile scope vì ví dụ dùng `@ApplicationModule` trong mã nguồn chính; các runtime starter không thay thế compile dependency đó. `spring-modulith-docs` dành cho build/test; chỉ thêm nó không tạo endpoint runtime.

Mở rộng sang tracing đòi hỏi tracer bridge, registry/exporter và collector phù hợp với Spring Boot; chỉ mở `/actuator/modulith` **không đòi hỏi** thiết lập OTLP, Zipkin hay Prometheus.

## 4. Tạo ứng dụng ba module

Đặt mã Java theo cấu trúc dưới đây, để lớp ứng dụng ở package cha `com.example.shop`:

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── catalog/
│   ├── package-info.java
│   └── ProductCatalog.java
├── orders/
│   ├── package-info.java
│   ├── OrderPlaced.java
│   ├── OrderService.java
│   └── OrderController.java
└── billing/
    ├── package-info.java
    └── BillingListener.java
src/main/resources/
├── application.yml
└── application-local.yml
src/test/java/com/example/shop/
└── ModuleGraphTest.java
~~~

Ba module được khai báo ID riêng để việc đổi tên package về sau không vô tình đổi định danh trong graph hoặc các truy vấn quan sát.

### 4.1. Lớp khởi động

Tạo `ShopApplication.java`:

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

### 4.2. Module catalog — cung cấp API sản phẩm

Tạo `catalog/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "catalog",
        displayName = "Danh mục sản phẩm"
)
package com.example.shop.catalog;
~~~

Tạo `catalog/ProductCatalog.java`:

~~~java
package com.example.shop.catalog;

import org.springframework.stereotype.Service;

@Service
public class ProductCatalog {
    public boolean isAvailable(String sku) {
        // Dữ liệu mẫu để không phải cấu hình database.
        return "SKU-001".equals(sku);
    }
}
~~~

`ProductCatalog` là public Spring bean nằm trong base package của module `catalog`, nên mặc định có thể đóng vai trò **API của module** mà module khác sử dụng. Nếu chuyển lớp sang `catalog.internal`, phải xem lại ranh giới API thay vì chỉ sửa import.

### 4.3. Module orders — phụ thuộc catalog và phát sự kiện

Tạo `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "orders",
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "catalog"
)
package com.example.shop.orders;
~~~

Tạo `orders/OrderPlaced.java`:

~~~java
package com.example.shop.orders;

public record OrderPlaced(String orderId, String sku) {}
~~~

Tạo `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.ProductCatalog;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ProductCatalog catalog;
    private final ApplicationEventPublisher events;

    public OrderService(ProductCatalog catalog,
                        ApplicationEventPublisher events) {
        this.catalog = catalog;
        this.events = events;
    }

    public boolean place(String orderId, String sku) {
        // Đây là phụ thuộc bean: orders -> catalog.
        if (!catalog.isAvailable(sku)) {
            return false;
        }

        events.publishEvent(new OrderPlaced(orderId, sku));
        return true;
    }
}
~~~

Tạo `orders/OrderController.java`:

~~~java
package com.example.shop.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/orders")
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/{id}")
    public ResponseEntity<String> place(
            @PathVariable String id,
            @RequestParam String sku) {

        if (!orders.place(id, sku)) {
            return ResponseEntity.badRequest().body("unknown-sku");
        }
        return ResponseEntity.ok("created:" + id);
    }
}
~~~

Vì `orders` tiêm `ProductCatalog` của `catalog`, Modulith có thể nhận diện cạnh `orders → catalog`. Khai báo `allowedDependencies = "catalog"` chỉ cho phép phụ thuộc đó; nó không tự tạo cạnh khi code không gọi đến `catalog`.

### 4.4. Module billing — lắng nghe sự kiện của orders

Tạo `billing/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "billing",
        displayName = "Xuất hóa đơn",
        allowedDependencies = "orders"
)
package com.example.shop.billing;
~~~

Tạo `billing/BillingListener.java`:

~~~java
package com.example.shop.billing;

import com.example.shop.orders.OrderPlaced;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {
    private static final Logger log =
            LoggerFactory.getLogger(BillingListener.class);

    @EventListener
    public void on(OrderPlaced event) {
        log.info("Billing received order {} for {}",
                event.orderId(), event.sku());
    }
}
~~~

`billing` biết kiểu sự kiện `OrderPlaced` do `orders` công bố, nên code ở `billing` có dependency về `orders`. Theo cơ chế mặc định của Spring, `@EventListener` ở ví dụ này chạy **đồng bộ** khi sự kiện được phát hành, nếu ứng dụng không cấu hình event multicaster bất đồng bộ.

Quan hệ này được biểu diễn trong module graph theo hướng **`billing → orders`**. Tại runtime, `orders` publish event và listener ở `billing` nhận event. Đừng vẽ cạnh graph ngược chỉ vì quan sát hướng sự kiện.

## 5. Cấu hình profile local để mở endpoint

Trong `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: shop-modulith
~~~

Trong `src/main/resources/application-local.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,info,modulith
~~~

Các điểm quan trọng:

- `server.port=8080` dành cho API nghiệp vụ; `management.server.port=8081` dành cho Actuator trong môi trường local.
- `management.server.address=127.0.0.1` giới hạn kết nối Actuator trên loopback của môi trường tiến trình đang chạy.
- `management.endpoints.web.exposure.include` cho phép truy cập `modulith` qua HTTP; Spring Boot không mặc định công bố mọi endpoint quản trị qua web.
- Cấu hình `local` chỉ nạp khi kích hoạt profile. Không khai báo `spring.profiles.active` ngay trong `application-local.yml`.
- Với Docker/container hoặc remote IDE, `127.0.0.1` bên trong container **khác** loopback của máy host; cần thiết kế lại cổng và kiểm soát truy cập cho môi trường tương ứng.

Nếu ứng dụng có Spring Security, endpoint có thể vẫn trả 401/403 dù đã được expose. Đây là vấn đề **ủy quyền truy cập**, không nhất thiết là thiếu dependency.

Chạy ứng dụng từ root dự án Maven:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Trên Windows PowerShell, có thể dùng:

~~~powershell
mvn spring-boot:run "-Dspring-boot.run.profiles=local"
~~~

Quan sát log khởi động: ứng dụng chọn profile `local`; API lắng nghe ở port 8080 và management server lắng nghe ở port 8081.

## 6. Mở `/actuator/modulith` và lấy JSON

Thực hiện từng bước, dùng **cổng quản trị 8081**:

~~~bash
curl -i http://127.0.0.1:8081/actuator/health
curl -i http://127.0.0.1:8081/actuator
curl -i http://127.0.0.1:8081/actuator/modulith
~~~

Trên PowerShell, nên dùng `curl.exe` (tránh nhầm alias `curl` ở một số phiên bản PowerShell):

~~~powershell
curl.exe -i http://127.0.0.1:8081/actuator/modulith
~~~

Hoặc lấy JSON thành đối tượng PowerShell để khám phá:

~~~powershell
$modules = Invoke-RestMethod -Uri "http://127.0.0.1:8081/actuator/modulith"
$modules | ConvertTo-Json -Depth 10
$modules.PSObject.Properties.Name
$modules.orders.dependencies
~~~

Trong trình duyệt cũng có thể mở:

~~~text
http://127.0.0.1:8081/actuator/modulith
~~~

**Giải thích luồng kiểm tra:**

1. `/actuator/health` chứng minh management server đang phản hồi.
2. `/actuator` thường cho danh sách liên kết endpoint; nếu bật discovery, tìm mục `"modulith"`.
3. `/actuator/modulith` trả JSON mô tả ứng dụng; việc nhận JSON không yêu cầu trước đó phải gọi API tạo đơn hàng.
4. Nếu `/actuator` không hiển thị liên kết, vẫn thử gọi trực tiếp đường dẫn và kiểm tra cấu hình discovery/exposure/security trước khi kết luận.

Để thử nghiệp vụ và xem log module sau đó, gửi:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/demo/orders/ORD-1001?sku=SKU-001"
~~~

Kỳ vọng phản hồi HTTP 200, body `created:ORD-1001`, và log có `Billing received order ORD-1001`. Bước này chứng minh ứng dụng demo chạy; **không làm thay đổi** graph đã được phát hiện từ source.

## 7. Đọc JSON thành module graph

Phản hồi dự kiến về mặt cấu trúc (ví dụ minh họa, thứ tự phần tử và `types` thực tế có thể thay đổi tùy phiên bản/phân tích code):

~~~json
{
  "catalog": {
    "displayName": "Danh mục sản phẩm",
    "basePackage": "com.example.shop.catalog",
    "dependencies": []
  },
  "orders": {
    "displayName": "Quản lý đơn hàng",
    "basePackage": "com.example.shop.orders",
    "dependencies": [
      {
        "target": "catalog",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "billing": {
    "displayName": "Xuất hóa đơn",
    "basePackage": "com.example.shop.billing",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

### 7.1. Đọc node của đồ thị

Mỗi **key cấp cao nhất** như `"orders"` là **technical name / ID** của một application module; các module khác dùng ID này để tham chiếu trong `dependencies[].target`.

| Trường JSON | Cách đọc |
|---|---|
| `catalog`, `orders`, `billing` | Node/ID logic của module |
| `displayName` | Tên hiển thị cho người đọc |
| `basePackage` | Package gốc chứa hiện thực module |
| `dependencies` | Các **phụ thuộc đi ra** từ module hiện tại |
| `dependencies[].target` | ID của module **được phụ thuộc** |
| `dependencies[].types` | Một hay nhiều loại quan hệ mà Modulith nhận diện |
| `parent` (nếu có) | ID module cha trong cấu trúc nested module |
| `nested` (nếu có) | Danh sách module lồng bên trong module hiện tại |

**Ví dụ:** `catalog.dependencies = []` nghĩa là Modulith không phát hiện phụ thuộc *đi ra* từ `catalog` đến các application module khác trong mô hình này. Điều đó **không** nghĩa là không module nào sử dụng `catalog` — vì `orders.dependencies` đang tham chiếu nó.

### 7.2. Đọc edge của đồ thị

Với mỗi phần tử trong `dependencies`, lấy node hiện tại làm **nguồn**, `target` làm **đích**, và `types` làm nhãn cạnh.

| Nguồn | Đích | Loại | Diễn giải |
|---|---|---|---|
| `orders` | `catalog` | `USES_COMPONENT` | Orders dùng Spring bean từ API Catalog |
| `billing` | `orders` | `EVENT_LISTENER` | Billing lắng nghe sự kiện thuộc hợp đồng của Orders |

Theo tài liệu Spring Modulith Actuator, `types[]` có thể chứa:

- `DEFAULT`: phụ thuộc kiểu Java thông thường giữa các module.
- `USES_COMPONENT`: phụ thuộc vào Spring component/bean của module khác.
- `EVENT_LISTENER`: dependency phát sinh từ listener nhận sự kiện của module khác.

Một cặp module có thể có **nhiều loại phụ thuộc cùng lúc**, ví dụ một service vừa tiêm bean, vừa lắng nghe sự kiện. Không giả định `types` chỉ chứa một phần tử. Các kiểu này biểu diễn **cách code phụ thuộc**, không tự báo tần suất gọi, độ trễ hay số sự kiện đã xử lý.

### 7.3. Tự vẽ đồ thị từ JSON

~~~mermaid
flowchart LR
    B["billing"] -->|"EVENT_LISTENER"| O["orders"]
    O -->|"USES_COMPONENT"| C["catalog"]
~~~

Cách suy luận thủ công:

1. Lấy danh sách các key cấp cao nhất làm tập node `V`.
2. Với từng module `u`, duyệt mọi mục `dependencies`.
3. Với mỗi mục, thêm cạnh có hướng `u → target` vào tập `E`.
4. Ghi `types` làm nhãn để biết vì sao có cạnh.
5. So sánh với kiến trúc mong đợi; xem có cạnh lạ, phụ thuộc vòng hoặc module ngoài dự kiến không.

Với ba node, ta có:

~~~text
V = {catalog, orders, billing}
E = {(orders, catalog), (billing, orders)}
~~~

Không có cạnh `orders → billing` trong graph chỉ vì `orders` phát `OrderPlaced`. `orders` biết `ApplicationEventPublisher` của Spring và kiểu sự kiện do chính nó sở hữu, không nhất thiết cần import bất kỳ lớp nào của `billing`.

### 7.4. Nested modules và refactor package

Trong hệ thống lớn hơn có nested module, JSON có thể thêm `parent` và `nested`. Đây là metadata cấu trúc, **khác** với dependency edge. Không vẽ quan hệ cha-con thành cạnh `USES_COMPONENT` nếu nó không nằm trong `dependencies`.

Khi đổi package `com.example.shop.orders` sang `com.example.shop.sales` mà giữ `@ApplicationModule(id = "orders")`, key logic có thể vẫn là `orders` trong khi `basePackage` đổi. Vì vậy dashboard, kiểm thử và sơ đồ nên phân biệt **ID ổn định** với **vị trí mã nguồn**.

## 8. Kiểm chứng graph bằng kiểm thử kiến trúc

Actuator giúp **nhìn thấy** mô hình module đang được công bố. Để **kiểm tra tính hợp lệ của các phụ thuộc**, thêm test từ `ApplicationModules`.

Tạo `src/test/java/com/example/shop/ModuleGraphTest.java`:

~~~java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleGraphTest {

    @Test
    void verifiesTheIntendedModuleModel() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        // Kiểm tra cycle, phụ thuộc vào internal API và allowedDependencies.
        modules.verify();

        Map<String, String> basePackages = modules.stream()
                .collect(Collectors.toMap(
                        module -> module.getIdentifier().toString(),
                        module -> module.getBasePackage().getName()));

        assertEquals(Set.of("catalog", "orders", "billing"),
                basePackages.keySet());
        assertEquals("com.example.shop.catalog",
                basePackages.get("catalog"));
        assertEquals("com.example.shop.orders",
                basePackages.get("orders"));
        assertEquals("com.example.shop.billing",
                basePackages.get("billing"));
        assertTrue(modules.stream().anyMatch(module ->
                module.getIdentifier().toString().equals("orders")));
    }
}
~~~

Chạy trong dự án Maven:

~~~bash
mvn test
~~~

`verify()` có thể phát hiện các vi phạm kiến trúc như **chu kỳ phụ thuộc**, **truy cập vào kiểu nội bộ** của module khác và **vi phạm `allowedDependencies`**. Test trên còn kiểm tra đúng tập ID và base package của ví dụ.

**Giới hạn:** Test chỉ kiểm tra những ràng buộc được mô hình Modulith nhận diện; không tự chứng minh mọi kết nối database, HTTP ngoài tiến trình, reflection hoặc message broker đều được thể hiện trong module graph.

### Bổ sung tài liệu sơ đồ (tùy chọn)

Nếu đã có dependency test-scope `spring-modulith-docs`, có thể tạo test riêng:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTest {

    @Test
    void writesModuleDiagrams() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.verify();

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
~~~

Tài liệu sinh ra hỗ trợ review module graph và ranh giới API trong pull request. **Endpoint Actuator** mô tả ứng dụng đang chạy; **Documenter** sinh tài liệu khi thực thi test. Hai công cụ có thể dựa trên cùng mô hình module nhưng phục vụ hai cách kiểm tra khác nhau.

## 9. Phân biệt module graph với metrics và tracing

Trong chủ đề Spring Modulith Documentation & Observability, cần biết lúc nào nên dùng từng loại bằng chứng:

| Cần tìm hiểu | Nguồn bằng chứng thích hợp | Điều chưa thể kết luận |
|---|---|---|
| Có những module nào? | `/actuator/modulith` | Module có đang nhận request hay không |
| Module A phụ thuộc Module B bằng kiểu nào? | `dependencies[].target`, `types` | Hôm nay đã gọi bao nhiêu lần |
| Có vi phạm ranh giới không? | `ApplicationModules.verify()` | Một trace cụ thể đi qua đâu |
| Sự kiện đã được publish bao nhiêu lần? | Event metrics (nếu bật instrumentation) | Listener đã xử lý thành công mọi sự kiện |
| Lời gọi API module đi qua các bước nào? | Module entry spans và trace backend | Tất cả các dependency tĩnh đều được gọi |
| Trace qua `@Async` có liên tục không? | Trace context/span trong luồng gửi và nhận | Chỉ nhìn graph là đủ |

Starter Insight cung cấp nền tảng quan sát module; để **xem trace ngoài tiến trình**, còn phải chọn Micrometer tracing bridge và exporter/collector phù hợp. Để **đọc số liệu tổng hợp**, cần thêm registry tương ứng và exposure của endpoint metrics nếu muốn gọi qua HTTP. Những phần này là mở rộng, **không phải điều kiện** để đọc module graph.

Ví dụ diễn giải chính xác: Graph cho biết `billing` phụ thuộc `orders` do nghe `OrderPlaced`; tracing có thể cho thấy lúc chạy `orders` phát sự kiện và `billing` xử lý nó. Nếu listener chạy trên thread khác, còn phải xác minh **context propagation** để nối các span — module graph không cung cấp thông tin đó.

## 10. Xử lý lỗi thường gặp khi mở endpoint

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và xử lý |
|---|---|---|
| `/actuator/health` cũng không kết nối được | Sai cổng, ứng dụng chưa chạy hoặc management server không lắng nghe | Kiểm tra startup log, `8081`, profile `local` |
| Health có nhưng `/actuator/modulith` trả 404 | Chưa có Modulith Actuator/Insight ở runtime; endpoint chưa expose; sai path | Kiểm tra dependency, `management.endpoints.web.exposure.include`, base path |
| HTTP 401/403 | Spring Security hoặc gateway yêu cầu quyền | Kiểm tra security config/credential của môi trường phát triển |
| JSON rỗng hoặc thiếu module | Root package khác dự kiến hoặc module detection strategy thay đổi | Kiểm tra vị trí `ShopApplication`, package con, `spring.modulith.detection-strategy` |
| Graph có module tên lạ | Package bị đổi hoặc ID chưa khai báo ổn định | Kiểm tra `@ApplicationModule(id = "...")` và base package |
| Không thấy `orders → catalog` | Orders không thật sự dùng kiểu/bean trong Catalog; code demo khác | Kiểm tra constructor injection và mã đang chạy |
| Không thấy `billing → orders` | Listener chưa tham chiếu đúng event type hoặc module detection không nhận ra listener | Kiểm tra `@EventListener`, kiểu `OrderPlaced`, package, phiên bản |
| `dependencies` có `DEFAULT` ngoài dự kiến | Có phụ thuộc Java type thông thường ngoài phụ thuộc bean/event | Tìm import/field/signature giữa hai module |
| Có lỗi cycle trong `modules.verify()` | Hai chiều phụ thuộc tạo vòng hoặc gián tiếp qua module thứ ba | Xem nguồn/đích từng cạnh rồi thay đổi hợp đồng giữa module |
| Có graph nhưng không có span/module metrics | Actuator graph và instrumentation là hai thành phần khác nhau | Kiểm tra tracer bridge, sampling, runtime instrumentation, exporter |
| Truy cập được trên host nhưng không từ container khác | Bind `127.0.0.1` chỉ áp dụng ở network namespace của tiến trình | Cân nhắc binding/port mapping và kiểm soát truy cập đúng môi trường |

Một lỗi hay gặp là đọc `dependencies` như **incoming dependencies**. Hãy luôn đọc từ module đang xét đến `target`. Nếu muốn biết module nào sử dụng `catalog`, tìm các phần tử `dependencies[]` của **mọi module khác** có `target = "catalog"`.

## 11. Bảo vệ endpoint khi đưa ra ngoài local

`/actuator/modulith` có thể tiết lộ danh sách module, tên package, ranh giới nghiệp vụ và quan hệ phụ thuộc. Những thông tin này hữu ích cho developer và vận hành nhưng có thể nhạy cảm ở hệ thống triển khai công khai.

Khi đưa lên staging/production:

1. Chỉ expose `modulith` ở môi trường thật sự cần; dùng cấu hình profile riêng.
2. Giới hạn truy cập management port bằng network policy, reverse proxy hoặc Spring Security.
3. Không phụ thuộc riêng vào “đường dẫn khó đoán”: endpoint có ID rõ ràng `modulith`.
4. Tránh bật toàn bộ endpoint Actuator bằng ký tự `*` nếu không có lý do và kiểm soát truy cập phù hợp.
5. Khi vận hành qua container hoặc proxy, xác nhận địa chỉ bind, cổng management và quyền truy cập.
6. Không đưa dữ liệu JSON Actuator trực tiếp vào response công khai của API nghiệp vụ.

Trong môi trường nội bộ, endpoint là công cụ **quan sát kiến trúc runtime**. Nó không thay cho các kiểm thử ở CI nhằm phát hiện kiến trúc bị phá vỡ trước khi triển khai.

## 12. Bài tập mở rộng và checklist nghiệm thu

### Bài tập A — Đọc đồ thị

Từ phản hồi JSON ở mục 7, hãy trả lời:

1. Có bao nhiêu module được phát hiện? ID của từng module là gì?
2. Module nào phụ thuộc `catalog`? Trường JSON nào chứng minh điều đó?
3. `billing → orders` diễn tả quan hệ mã nguồn hay chiều event đang chạy?
4. Nếu `catalog.dependencies=[]`, có thể khẳng định Catalog không được module nào dùng không? Vì sao?
5. Nếu `orders` tiêm thêm một bean từ `billing`, graph và `modules.verify()` có thể thay đổi thế nào?

### Bài tập B — Chủ động tạo một thay đổi

Thêm một Spring bean `CatalogDiscounts` vào **API package** `catalog`, rồi cho `orders` gọi bean này. Mở lại Actuator sau khi build và chạy ứng dụng mới.

**Kỳ vọng:** `orders → catalog` vẫn là một quan hệ phụ thuộc; JSON không nhất thiết tăng thêm cạnh thứ hai chỉ vì có hai bean đến cùng một module. Loại `USES_COMPONENT` vẫn thích hợp để mô tả. Nếu đưa bean vào `catalog.internal` nhưng `orders` tiếp tục gọi trực tiếp, `verify()` có thể báo vi phạm ranh giới API.

### Bài tập C — Refactor package và giữ ID

Đổi package `com.example.shop.orders` thành `com.example.shop.sales`, chuyển `package-info.java` và các class cùng nhau, sửa import, giữ `id="orders"`. Mở lại endpoint: khóa `orders` vẫn là ID logic, còn `basePackage` có thể chuyển thành `com.example.shop.sales`. So sánh module graph trước và sau bằng cùng cách đọc ở mục 7.

### Checklist hoàn thành

- [ ] Ứng dụng khởi động được với profile `local`.
- [ ] Có ba module `catalog`, `orders`, `billing` trong graph.
- [ ] `GET http://127.0.0.1:8081/actuator/modulith` trả JSON và có key module hợp lệ.
- [ ] Đọc được `displayName`, `basePackage`, `dependencies.target` và `types`.
- [ ] Vẽ đúng cạnh `orders → catalog` và `billing → orders`, giải thích được chiều mũi tên.
- [ ] Phân biệt graph phụ thuộc code với luồng xử lý event/trace runtime.
- [ ] `ApplicationModules.verify()` pass với mô hình ví dụ.
- [ ] Endpoint chỉ được mở trong phạm vi quản trị phù hợp với môi trường.

**Câu hỏi tổng kết:** Nếu một trace cho thấy sự kiện đi từ `orders` đến `billing` nhưng JSON Actuator thể hiện `billing → orders`, đó có phải lỗi của Spring Modulith không? Hãy giải thích bằng **kiểu phụ thuộc** và **chiều luồng xử lý**.

## 13. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): starter Insight, endpoint `modulith`, schema JSON và các loại `dependencies.types`.
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): application module, API package, ID và cách phát hiện module.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và các quy tắc ranh giới.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): PlantUML và Module Canvas.
- [Spring Modulith — Spring Boot Compatibility](https://docs.spring.io/spring-modulith/reference/appendix.html): kiểm tra cặp phiên bản Modulith và Spring Boot.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, security và HTTP management endpoint.

> **Ghi nhớ:** Muốn đọc module graph, hãy bắt đầu từ **ID module**, xác định **các dependency đi ra** và chuyển từng `target` thành một cạnh có hướng. Dùng `verify()` để kiểm tra ranh giới, dùng metrics/tracing để hiểu hành vi lúc chạy; ba nguồn bằng chứng bổ sung cho nhau.
