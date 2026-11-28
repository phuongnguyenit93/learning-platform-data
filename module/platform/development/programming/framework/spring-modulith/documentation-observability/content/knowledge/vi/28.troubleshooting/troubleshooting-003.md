# Không tạo module span

> **Chương:** Chẩn đoán lỗi  
> **Công nghệ:** Spring Modulith, Spring Boot Actuator, Micrometer Observation/Tracing  
> **Tình huống:** Ứng dụng có module graph hợp lệ và xử lý nghiệp vụ thành công nhưng không thấy span tương tác giữa các application module.

## 1. Nhận diện đúng sự cố

Spring Modulith hỗ trợ quan sát tương tác giữa các **application module** thông qua việc chặn lời gọi đi vào các Spring component thuộc API được module công bố. Khi tích hợp Micrometer Observation/Tracing, những tương tác đủ điều kiện có thể xuất hiện dưới dạng **module entry span** trong trace. Span thường mang metadata như `module.identifier`, `module.name`, `module.method` và `module.invocation-type`; các key cụ thể phụ thuộc phiên bản Spring Modulith và convention đang dùng.

Tuy nhiên, câu nói “không tạo module span” có thể chỉ ít nhất bốn tình huống khác nhau:

| Dấu hiệu quan sát | Cách hiểu ban đầu | Nhánh cần điều tra |
|---|---|---|
| Không thấy cả HTTP span lẫn module span | Tracing chưa hoạt động, sampling hoặc cấu hình quan sát có vấn đề | Micrometer, tracer, sampling |
| Có HTTP span nhưng không có span/module attribute | Modulith instrumentation chưa được bật hoặc lời gọi không đi qua API Spring bean được quan sát | Module model, API, Spring AOP |
| Log có trace ID/span ID, backend không thấy trace | Trace có thể được tạo tại local nhưng không được xuất, nhận hoặc hiển thị | Exporter, collector, truy vấn UI |
| Có module span ở xử lý đồng bộ, mất liên hệ ở listener async | Context không được truyền qua thread, executor hoặc message | Context propagation |

**Đừng đánh đồng các dấu hiệu:** `/actuator/modulith` trả về danh sách module chỉ xác nhận mô hình kiến trúc được công bố. Metric `module.events.published` ghi nhận sự kiện được phát hành cũng không chứng minh một module entry span đã được tạo. Log chứa trace ID chỉ cho thấy có trace context trong đoạn ghi log; để kết luận có **module span**, cần tìm span/observation tương ứng với metadata module.

## 2. Cơ chế tạo module span

Với mô hình module thường gặp, một Spring bean thuộc API của module `catalog` được module `checkout` gọi thông qua container:

~~~mermaid
flowchart LR
    H["HTTP request"] --> C["CheckoutController\nmodule checkout"]
    C --> S["CheckoutService\nmodule checkout"]
    S --> A["CatalogOperations\nAPI bean của catalog"]
    A --> I["Inventory logic\ncatalog.internal"]
    S -. "Lời gọi qua Spring bean" .-> O["Modulith observation\nmodule.identifier=catalog"]
    O --> T["Micrometer Tracing"]
    T --> X["Exporter / backend"]
~~~

Với cấu trúc này, **lời gọi vào `CatalogOperations`** là điểm quan trọng để kiểm chứng span module: bean nằm ở API của một application module, được container quản lý và được gọi trong luồng nghiệp vụ. Lời gọi bên trong module tới lớp thuần Java hoặc một method private không tự trở thành module entry span.

Trong nhiều phiên bản Spring Modulith, việc quan sát API component được áp dụng bằng cơ chế interceptor/proxy cho Spring bean. Do vậy, các trường hợp tự tạo đối tượng bằng `new`, tự gọi method trong cùng instance hoặc gọi mã không thuộc Spring bean có thể đi vòng qua chỗ chặn cần thiết. Việc một lớp là `public` không đủ; cần xác định lớp đó là **API của module được phát hiện** và **Spring bean thực sự được gọi**.

Một module span không đồng nghĩa mỗi method Java đều có span riêng. Modulith nhắm đến ranh giới tương tác module, không phải instrumentation từng dòng nghiệp vụ.

## 3. Quy trình chẩn đoán theo thứ tự ít tốn công nhất

~~~mermaid
flowchart TD
    A["Gửi request kiểm thử cố định"] --> B{"Có HTTP span / trace ID?"}
    B -->|Không| C["Kiểm tra bridge, tracing,\nsampling và log/collector"]
    B -->|Có| D{"Module API bean thật sự được gọi?"}
    D -->|Không| E["Sửa luồng gọi hoặc dữ liệu thử"]
    D -->|Có| F{"Module có trong\n/actuator/modulith?"}
    F -->|Không| G["Kiểm tra root package,\ndetection strategy và classpath"]
    F -->|Có| H{"Có insight/observability\ntrên runtime classpath?"}
    H -->|Không| I["Thêm đúng dependency,\nđồng bộ BOM"]
    H -->|Có| J["Kiểm tra API package,\nSpring proxy và convention"]
    J --> K{"Local ghi nhận nhưng UI thiếu?"}
    K -->|Có| L["Kiểm tra sampling, exporter,\ncollector, filter UI"]
    K -->|Không| M["Tối giản case, kiểm tra\nlog/autoconfiguration"]
~~~

Mỗi bước nên lưu **một bằng chứng** (HTTP response, log, Actuator JSON, dependency tree hoặc trace screenshot) rồi mới chuyển nhánh. Quy trình này giúp tránh sửa đồng thời nhiều cấu hình mà không biết yếu tố nào gây lỗi.

### Bước 1 — Bảo đảm request đi đến logic cần quan sát

Chọn một luồng ngắn và tất định: HTTP → `checkout` → một public API bean của `catalog`. Ghi log ở trước và trong method được gọi. Nếu request trả 200 nhưng method mục tiêu không chạy do cache, điều kiện rẽ nhánh hoặc mock, sẽ không có module span mong đợi.

### Bước 2 — Kiểm tra module model độc lập với tracing

Gọi `/actuator/modulith` hoặc kiểm tra bằng `ApplicationModules.of(...).verify()`. Xác minh module đích được phát hiện, base package đúng và lớp API nằm ở phần giao diện công khai. Nếu graph không có module đó, instrumentation cũng không thể suy ra ranh giới mong đợi.

### Bước 3 — Xác minh dependency trên **runtime classpath**

Cần có phần quan sát Modulith; ví dụ starter `spring-modulith-starter-insight` đã tích hợp Actuator và observability. Chỉ thêm `spring-modulith-core` hoặc thư viện sinh tài liệu **không tự bật** interceptor quan sát runtime.

Để biến Micrometer observation thành trace thực, cần tracer implementation/bridge và cấu hình exporter phù hợp. Quan sát module và xuất trace là hai bước khác nhau: một bước thiếu cũng có thể khiến backend trống.

### Bước 4 — Kiểm tra điều kiện method được intercept

Xem nơi đặt bean trong API module, nơi tạo bean, kiểu gọi thực tế, proxy và khả năng thay đổi instrumentation theo phiên bản. Đừng vội nâng sampling hoặc thay collector khi không hề có lời gọi đi qua đối tượng được quan sát.

### Bước 5 — Phân biệt “không tạo” với “không hiển thị”

Tìm trace theo một request vừa gửi, service name đúng, khoảng thời gian đúng và `module.identifier`. Nếu chỉ tìm bằng tên span chứa từ `module`, có thể bỏ sót span do convention đặt tên khác. Khi đã xác nhận có trace ID, rà soát exporter, bộ lọc UI và sampling trước khi kết luận instrumentation lỗi.

## 4. Thiết lập một môi trường tái hiện tối thiểu

Các ví dụ bên dưới dùng **Spring Boot 3.x và Spring Modulith 1.x** với Maven; dependency được quản lý bằng Spring Boot parent/BOM và một **Spring Modulith BOM tương thích**. Không chép cứng một phiên bản Modulith vào từng artifact nếu BOM đã quản lý phiên bản.

Trong `pom.xml`, thêm dependency cần thiết vào phần `dependencies` hiện có:

~~~xml
<dependencies>
    <!-- API HTTP để tạo một request có thể tái hiện -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Actuator, module graph và Modulith instrumentation -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Tracer bridge dùng OpenTelemetry cho Spring Boot 3 -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <!-- Kiểm thử mô hình ứng dụng; không dùng để thay thế runtime instrumentation -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong các phiên bản Spring Modulith 1.x, artifact quan sát độc lập thường có tên `spring-modulith-observability`; ở một số phiên bản 2.x, module này được tách thành các artifact như `spring-modulith-observability-core`. Dùng `spring-modulith-starter-insight` tương thích với phiên bản đang chạy giúp giảm nguy cơ nhầm tên artifact. Không ghép Spring Boot 3 với Spring Modulith 2 chỉ bằng cách đổi một dependency; hãy kiểm tra bảng tương thích và điều chỉnh cấu hình theo nhánh thực tế.

Có thể kiểm tra cây dependency mà không sửa code:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
mvn dependency:tree -Dincludes=io.micrometer
~~~

**Điểm cần nhìn:** artifact insight và observability hiện diện ở runtime, không có nhiều phiên bản Modulith khác nhau bị kéo vào cùng một ứng dụng. Dependency `spring-modulith-docs` dùng để tạo Module Canvas/PlantUML khi chạy test; có `docs` mà không có `insight`/`observability` không đủ để tạo span runtime.

### Cấu hình profile local

Trong `src/main/resources/application-local.yml`:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics
  tracing:
    sampling:
      probability: 1.0

logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
  level:
    com.example.shop: DEBUG
~~~

Chỉ bật các cài đặt chi tiết này ở local hoặc môi trường test giới hạn truy cập. Sampling 100% giúp loại trừ nguyên nhân bỏ mẫu thường gặp; không nên dùng như cấu hình production mặc định. Khi đã có một trace từ upstream, cấu hình sampler kiểu *parent-based* còn có thể kế thừa quyết định không lấy mẫu của parent. Để thử độc lập, gửi request mới **không mang trace headers từ upstream**.

Khởi động ứng dụng:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Nếu dùng PowerShell, có thể đặt đối số Maven trong dấu nháy nếu cần để tránh shell xử lý sai:

~~~powershell
mvn spring-boot:run "-Dspring-boot.run.profiles=local"
~~~

### Chọn một mô hình module rõ ràng

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── checkout/
│   ├── CheckoutController.java
│   └── CheckoutService.java
└── catalog/
    ├── CatalogOperations.java       # API bean của module catalog
    └── internal/
        └── InventoryState.java
~~~

Với cách phát hiện mặc định, `checkout` và `catalog` là hai package con trực tiếp của root `com.example.shop`; mỗi package có thể trở thành một application module. Thông thường, các type công khai trong package gốc của module tạo thành API mặc định của module đó.

Tạo lớp khởi động ở package cha `com.example.shop`:

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

Tạo API bean ở `catalog/CatalogOperations.java`:

~~~java
package com.example.shop.catalog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogOperations {
    private static final Logger log =
            LoggerFactory.getLogger(CatalogOperations.class);

    public boolean reserve(String sku) {
        log.info("CatalogOperations.reserve called, sku={}", sku);
        return true;
    }
}
~~~

Tạo bên gọi ở `checkout/CheckoutService.java`:

~~~java
package com.example.shop.checkout;

import com.example.shop.catalog.CatalogOperations;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final CatalogOperations catalog;

    public CheckoutService(CatalogOperations catalog) {
        this.catalog = catalog;
    }

    public String checkout(String orderId) {
        log.info("Checkout for {}", orderId);
        boolean reserved = catalog.reserve("SKU-001");
        return reserved ? "accepted:" + orderId : "unavailable:" + orderId;
    }
}
~~~

Tạo HTTP entry point ở `checkout/CheckoutController.java`:

~~~java
package com.example.shop.checkout;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/checkouts")
public class CheckoutController {
    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping("/{id}")
    public String checkout(@PathVariable String id) {
        return service.checkout(id);
    }
}
~~~

Gửi một request không có trace headers:

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/checkouts/ORD-1001
~~~

Phản hồi dự kiến:

~~~text
HTTP/1.1 200
...
accepted:ORD-1001
~~~

Từ log, xác nhận có cả dòng `Checkout for ORD-1001` và `CatalogOperations.reserve called`. Tên method, URL và chuỗi phản hồi chỉ phục vụ tái hiện; điều đáng kiểm tra là `checkout` đã **gọi Spring bean thuộc API của module `catalog`**. Trong cấu hình observability phù hợp, lời gọi này là ứng viên cho một module entry span của `catalog`.

## 5. Kiểm chứng module model bằng Actuator và test

Nếu Actuator `modulith` được bật và công bố qua HTTP:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/modulith
~~~

Một phản hồi `modulith` minh họa có dạng:

~~~json
{
  "catalog": {
    "displayName": "Catalog",
    "basePackage": "com.example.shop.catalog",
    "dependencies": []
  },
  "checkout": {
    "displayName": "Checkout",
    "basePackage": "com.example.shop.checkout",
    "dependencies": [
      {
        "target": "catalog",
        "types": ["USES_COMPONENT"]
      }
    ]
  }
}
~~~

Trong thực tế, thứ tự, display name và types có thể khác tùy cách bố trí code. Điều cần xác nhận là **ID `catalog` tồn tại**, `basePackage` đúng và phần phụ thuộc `checkout → catalog` được phát hiện khi code có tham chiếu đến bean của module đích.

Có thể thêm một bài test cấu trúc:

~~~java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTest {

    @Test
    void modulesAreDetectedAndValid() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.verify();

        boolean hasCatalog = modules.stream()
                .anyMatch(module ->
                    module.getIdentifier().toString().equals("catalog"));

        assertTrue(hasCatalog);
    }
}
~~~

Test này chứng minh model có module và kiểm tra quy tắc kiến trúc cơ bản mà Spring Modulith hỗ trợ, **không chứng minh module span đã được tạo**. Muốn kiểm tra span, phải thực hiện lời gọi với instrumentation/tracing thực sự hoặc bổ sung integration test quan sát phù hợp phiên bản đang dùng.

Nếu `/actuator/modulith` không chứa `catalog`, kiểm tra:

1. Vị trí `ShopApplication`: package cha phải bao phủ các module mong muốn.
2. `spring.modulith.detection-strategy`: nếu đang chọn `explicitly-annotated`, các package muốn là module cần khai báo annotation tương ứng.
3. Cách tổ chức package: module nằm sâu dưới package khác có thể được phát hiện khác với kỳ vọng theo chiến lược hiện tại.
4. Metadata module và package scan khi chuyển lớp sang package mới.

**Lưu ý:** Endpoint Actuator có thể bị chặn bởi Spring Security; HTTP 401/403 khác với HTTP 404. Nếu deployment tách management port, hãy dùng đúng port trước khi kết luận endpoint bị thiếu.

## 6. Kiểm tra ranh giới API và proxy

Sau khi xác nhận module model đúng, đây thường là nhánh quan trọng nhất khi **HTTP span có nhưng module span không có**.

### 6.1. Bean nằm ở API module hay phần internal?

Ví dụ dễ gây hiểu nhầm:

~~~text
catalog/
├── CatalogOperations.java           # API công khai
└── internal/
    └── InventoryService.java        # Chi tiết hiện thực
~~~

Nếu code chỉ gọi một method của `InventoryService` hoặc một helper nội bộ, không nên mặc định mong đợi span ở từng method đó. Spring Modulith hướng đến việc quan sát lời gọi qua **API được module công bố**. Phần API mặc định thường là public type trong base package; các API bổ sung có thể được công bố thông qua `@NamedInterface`.

Kiểm tra bằng cách đổi luồng test thành `CheckoutService → CatalogOperations.reserve()`. Nếu có span ở đường này nhưng không có trong luồng cũ, nhiều khả năng lỗi nằm ở vị trí API/đường gọi, chưa cần đổi exporter.

### 6.2. Đối tượng có phải bean do Spring quản lý?

Đây là lời gọi dễ đi vòng qua interceptor:

~~~java
// Ví dụ sai mục tiêu quan sát: tự tạo object, không đi qua Spring container.
CatalogOperations catalog = new CatalogOperations();
catalog.reserve("SKU-001");
~~~

Còn đây là cách dùng phù hợp với ví dụ:

~~~java
// Constructor-injected Spring bean:
public CheckoutService(CatalogOperations catalog) {
    this.catalog = catalog;
}
~~~

Nếu lớp tồn tại trên classpath nhưng không được container tạo thành bean (`@Component`/`@Service` hoặc `@Bean` tương ứng), logic quan sát bean của Modulith sẽ không tự nhận diện một instance được tạo thủ công.

### 6.3. Có bypass proxy hay không?

Những tình huống cần xem xét:

- **Self-invocation:** method của một bean gọi method khác trên chính `this`, nên một số lời gọi không đi qua proxy Spring AOP.
- **Method private/final hoặc class final:** tùy kiểu proxy và cấu hình, method có thể không được advice như kỳ vọng.
- **Bean được tạo theo cách đặc biệt:** wrapper/proxy tùy chỉnh, bean khởi tạo quá sớm hoặc cấu hình AOP khác có thể ảnh hưởng việc chặn lời gọi.
- **Đường xử lý không vào bean đích:** dùng mock, cache, event listener không chạy hoặc trả kết quả ở nhánh khác.

Không dùng `AopUtils.isAopProxy(bean)` như chứng cứ duy nhất. Một bean có thể là proxy vì `@Transactional` mà vẫn chưa có advice của Modulith. Cách kiểm tra thực tế là tạo một lời gọi đã biết chắc từ module khác tới API bean rồi quan sát span, đồng thời kiểm tra các điều kiện cấu hình.

## 7. Phân biệt span, metric, log và Actuator

Các tín hiệu thường bị diễn giải lẫn nhau:

| Tín hiệu | Có thể chứng minh | Không đủ để chứng minh |
|---|---|---|
| `/actuator/modulith` liệt kê `catalog` | Spring Modulith biết module này | Lời gọi vào module đã tạo span |
| Log `CatalogOperations.reserve called` | Method đã chạy | Method được instrument thành module entry span |
| Log có `traceId` | Thread đang có trace context ở thời điểm ghi log | Span hiện tại là module span |
| Meter `module.events.published` tăng | Có event được publish và ghi nhận | Có module entry span của bean đã được export |
| HTTP span xuất hiện | Tracing cho HTTP hoạt động | Modulith interceptor hoạt động |
| Span có `module.identifier=catalog` | Có dữ liệu tracing về module đích | Mọi method trong module đều được quan sát |
| Trace có cả span HTTP và module | Quan sát qua ranh giới module hoạt động cho luồng này | Các luồng bất đồng bộ khác đều được propagate context |

Trong trace backend, tìm theo **service name** `shop-modulith`, khoảng thời gian ngay sau request và tag/attribute `module.identifier=catalog`. Các thuộc tính `module.invocation-type` và `module.method` có thể giúp phân biệt sự kiện với bean method khi phiên bản đang dùng hỗ trợ chúng.

Không ép tên span hiển thị phải có một chuỗi cố định. Convention quan sát có thể đổi tên span mà vẫn giữ metadata module. Hãy kiểm tra attributes và đường đi trước khi kết luận span bị thiếu.

## 8. Tracing bridge, sampling và exporter

### 8.1. Không có cả HTTP span

Nếu request chạy thành công nhưng không thấy trace ID, trước tiên kiểm tra dependency tracing, sampling và cấu hình log. Với Spring Boot 3, một lựa chọn phổ biến là `micrometer-tracing-bridge-otel` kết hợp Actuator. Tracing bridge và exporter là hai thành phần khác nhau: bridge cung cấp tích hợp với Micrometer; exporter gửi span ra nơi lưu trữ.

Kiểm tra cùng lúc ba điều:

1. Có tracer implementation thực sự trong runtime classpath?
2. `management.tracing.sampling.probability` có giá trị cho phép mẫu được giữ không?
3. Request đang thử có trace header từ hệ thống khác mang quyết định sampling không?

Nếu chỉ dựa vào log MDC, xác minh ứng dụng dùng pattern logging thực tế có in `traceId` và `spanId`. Logback tùy chỉnh có thể thay thế pattern của `application-local.yml`; thiếu ID trong log không luôn đồng nghĩa hoàn toàn không có span.

### 8.2. Có local trace nhưng backend trống

Để xem trace trên backend qua OTLP/HTTP ở Spring Boot 3, bổ sung exporter khi thực sự có collector:

~~~xml
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Ví dụ trong `application-local-otel.yml` (một profile bổ sung):

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://127.0.0.1:4318/v1/traces
~~~

Khởi động với cả hai profile khi collector đang chạy:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local,local-otel
~~~

Cổng `4318` thường dành cho OTLP/HTTP; cổng `4317` thường dùng cho OTLP/gRPC. Địa chỉ backend UI (Jaeger, Zipkin, Grafana Tempo…) không nhất thiết là URL ingest OTLP. Xác nhận cấu hình collector và pipeline trace nhận dữ liệu.

Nếu thử local mà không có collector, chỉ cấu hình tracing bridge để đọc log và không bật exporter khi chưa cần; khi exporter đã nằm trên classpath, cần chú ý đến cấu hình tự động xuất trace của phiên bản Boot đang dùng để tránh log lỗi kết nối vô ích.

**Khác biệt phiên bản cần nhớ:**

- Ví dụ trên dùng Spring Boot **3.x**: thuộc tính OTLP trace endpoint thông dụng là `management.otlp.tracing.endpoint`.
- Với Spring Boot **4.x**, tài liệu hiện hành sử dụng các starter và nhóm thuộc tính OTLP mới, ví dụ `spring-boot-starter-opentelemetry` và `management.opentelemetry.tracing.export.otlp.*`.
- Không áp dụng nguyên xi cả dependency và property từ nhánh Boot khác mà chưa đối chiếu tài liệu của phiên bản trong dự án.

### 8.3. Sampling 100% vẫn không thấy module span?

Sampling chỉ quyết định trace nào được ghi và xuất. Nếu method không thuộc API bean được instrument, tăng sampling từ 10% lên 100% không tạo ra điểm đo mới. Ngược lại, nếu instrumentation đã tạo observation nhưng trace bị bỏ mẫu hoặc exporter lỗi, module span có thể không xuất hiện trong backend dù lời gọi và metric vẫn có.

Để kiểm tra, dùng một request mới không có upstream parent, cấu hình sampler phù hợp, đợi đủ thời gian flush/export, rồi tìm trace theo đúng service/time range. Không tăng sampling lên 100% trên production chỉ để điều tra một lỗi.

## 9. Event listener và context propagation: một nhánh đặc biệt

Với event, cần tách **event đã được publish**, **listener đã chạy**, **listener được instrument** và **trace context đã đi tới listener** thành bốn kiểm chứng khác nhau.

~~~mermaid
sequenceDiagram
    participant H as HTTP / checkout
    participant O as orders
    participant E as Event publisher
    participant B as billing listener
    participant T as Tracing backend
    H->>O: Tạo đơn hàng
    O->>E: publish(OrderPlaced)
    E-->>B: xử lý event
    B->>T: span (nếu có instrumentation)
    Note over E,B: Async cần truyền observation/trace context
~~~

Trường hợp `@EventListener` đồng bộ mặc định chạy trong cùng thread của sự kiện thường dễ quan sát hơn. Khi chuyển sang `@Async`, `@ApplicationModuleListener` hoặc executor/message broker khác, có thể xảy ra:

- Listener chưa chạy do giao dịch chưa commit, lỗi xử lý hoặc điều kiện event không thỏa.
- Listener chạy nhưng không nằm trong điểm instrumentation đang dùng.
- Listener có span nhưng dùng trace ID khác vì ngữ cảnh bị mất khi đổi thread.
- Listener nằm cùng trace nhưng span bị bỏ mẫu hoặc không được gửi tới backend.

**Cần kiểm tra listener thực sự chạy trước**, bằng log theo event ID; sau đó xác minh module attributes và trace ID.

### Ví dụ truyền context qua executor

Với Spring Framework 6.1+ và Micrometer Context Propagation phù hợp:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncTracingConfig {

    @Bean(name = "tracedExecutor")
    ThreadPoolTaskExecutor tracedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setThreadNamePrefix("trace-demo-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Khi listener `@Async("tracedExecutor")` chạy, decorator có thể giúp khôi phục observation context trong worker thread. Cần xác nhận listener **đang dùng đúng executor này**. Với `@ApplicationModuleListener`, việc xử lý bất đồng bộ còn phụ thuộc cơ chế listener và executor/transaction mà Spring Modulith thực sự sử dụng; không mặc định annotation đó chọn `tracedExecutor` nếu không có cấu hình tương ứng.

Với message broker, task decorator trong tiến trình không đủ: trace headers cần được chèn vào message khi publish và khôi phục khi consume. Đối chiếu `traceId`, `parentSpanId` hoặc span links (theo mô hình truyền context của công cụ), không chỉ dựa trên việc log của listener vẫn xuất hiện.

**Mấu chốt:** Một trace bị đứt giữa hai luồng xử lý chưa chắc là “Modulith không tạo module span”. Có thể mỗi bên vẫn tạo span riêng, nhưng propagation hoặc liên kết trace bị thiếu.

## 10. Bảng tra lỗi nhanh

| Triệu chứng | Giả thuyết cần kiểm tra | Cách xác minh | Hướng xử lý |
|---|---|---|---|
| `/actuator/modulith` 404 | Thiếu starter insight, chưa expose endpoint, sai management port | Kiểm tra dependency và `/actuator` | Bật Actuator/insight và exposure đúng môi trường |
| Có graph nhưng không có HTTP trace | Tracing bridge thiếu hoặc bị tắt, không lấy mẫu | Kiểm tra runtime dependency, sampling, log MDC | Bổ sung tracer phù hợp, thử request mới |
| Có HTTP trace, thiếu module span | API bean không được gọi hoặc Modulith instrumentation thiếu | Tái hiện bằng `CheckoutService → CatalogOperations` | Sửa đường gọi và runtime dependency |
| Bean chạy nhưng không có span | Bean thuộc internal, self-invocation, proxy không intercept | Kiểm tra package API, cách tiêm phụ thuộc, call stack | Gọi qua API bean của module |
| `module.events.published` tăng nhưng không có span | Event metric và module entry span là tín hiệu khác nhau | Kiểm tra listener/bean được instrument | Đừng lấy metric event làm bằng chứng span |
| Log có trace ID nhưng backend trống | Exporter/collector sai, UI filter hoặc delay | Kiểm tra endpoint OTLP, log exporter, service name | Sửa pipeline xuất và truy vấn trace |
| Trace xuất hiện không đều | Sampling, upstream parent, traffic ít | Lặp request mới, xem sampling config | Chỉnh sampling tạm ở local |
| Module span có ở sync, async không nối trace | Context propagation qua executor/broker thiếu | So trace ID trước/sau thread hop | Dùng decorator/propagation phù hợp |
| Span có tag module khác kỳ vọng | Refactor package đổi module ID, config discovery khác | So Actuator ID, `module.identifier` | Giữ ID logic ổn định hoặc cập nhật cấu hình |
| Lên backend khác mất module attributes | Custom observation convention, exporter processor hoặc filter | So raw attributes và pipeline | Kiểm tra convention/processor, mapping tags |
| Chạy được local, production không có module span | Khác dependency, profile, sampling, security hoặc artifact | So runtime dependency và config hiệu lực | Chuẩn hóa build/deployment và kiểm tra theo môi trường |

## 11. Kiểm thử hồi quy sau khi sửa

Nên lưu một bộ thử có thể lặp lại cho mỗi lỗi module span:

1. **Xác nhận startup:** profile test đang active, runtime dependency đủ và không có lỗi instrumentation/exporter trong log khởi động.
2. **Xác nhận kiến trúc:** `ApplicationModules.verify()` pass; `/actuator/modulith` liệt kê đúng các module và base package.
3. **Xác nhận nghiệp vụ:** `POST /demo/checkouts/ORD-1001` trả `accepted:ORD-1001`; log xác nhận `CatalogOperations.reserve()` đã chạy.
4. **Xác nhận tracing nền:** trace/log của HTTP request có ID hợp lệ trên môi trường test, khi sampling cho phép.
5. **Xác nhận module span:** tìm span có `module.identifier=catalog` tương ứng với lời gọi `reserve` trong đúng trace; đối chiếu các attribute đã công bố ở phiên bản đang dùng.
6. **Xác nhận exporter:** nếu backend được cấu hình, trace có mặt trong backend đúng thời điểm, đúng service và đúng môi trường; kiểm tra exporter/collector khi không tìm thấy.
7. **Xác nhận async riêng:** nếu có listener bất đồng bộ, kiểm tra nó chạy và trace context/parent relationship được truyền hợp lý.

Có thể dùng mẫu ghi nhận bằng chứng:

| Mục kiểm tra | Kết quả trước sửa | Kết quả sau sửa |
|---|---|---|
| Module ID / base package | `catalog / ...` | `catalog / ...` |
| API bean được gọi | Có / Không | Có |
| Tracing bridge hoạt động | Có / Không | Có |
| HTTP span | Có / Không | Có |
| Module span với `module.identifier=catalog` | Không | Có |
| Trace được export | Có / Không / Không cấu hình | Có nếu có collector |
| Listener async giữ trace context | Có / Không / Không áp dụng | Có nếu có async |

**Không kết luận hoàn thành chỉ vì HTTP 200 hoặc Actuator trả JSON.** Tiêu chí cốt lõi của bài là thấy được **span cho một lời gọi có chủ đích qua ranh giới module** và giải thích rõ nó được tạo/hiển thị nhờ những thành phần nào.

## 12. Câu hỏi tự đánh giá

1. Vì sao một Spring bean trong `catalog.internal` có thể chạy bình thường nhưng không có module entry span mong đợi?
2. Nếu `/actuator/modulith` trả về đúng `catalog` và `checkout`, tại sao điều đó chưa chứng minh khả năng quan sát runtime đã bật?
3. Log có cùng trace ID ở controller và service, nhưng không có `module.identifier` trên span nào. Bạn kiểm tra điểm gì trước khi sửa OTLP collector?
4. Tại sao đặt `management.tracing.sampling.probability=1.0` không sửa được self-invocation?
5. Listener `@Async` có log xử lý thành công nhưng dùng trace ID mới. Đây là lỗi instrumentation, context propagation hay exporter? Cần bằng chứng gì để phân biệt?

## 13. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight starter, Actuator module, quan sát module, module entry span và event metrics.
- [Spring Modulith 1.4 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/1.4/production-ready.html): artifact `spring-modulith-observability` ở nhánh 1.x.
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cách phát hiện module, API package, named interface.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracer, sampling và exporter theo phiên bản Spring Boot hiện hành.
- [Spring Boot 3.4 — Common Application Properties](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/): các thuộc tính OTLP tracing ở nhánh 3.x.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): observation và context propagation qua thread.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): mối quan hệ giữa observation, metric và trace.

> **Ghi nhớ:** Chẩn đoán “không tạo module span” theo thứ tự **lời gọi thực tế → module model → API Spring bean → instrumentation → tracing/sampling → exporter/backend → propagation**. Mỗi tầng có bằng chứng riêng; đừng xem thiếu dữ liệu trên UI như chứng cứ duy nhất rằng Modulith không tạo span.
