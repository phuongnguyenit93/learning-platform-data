# Bật module entry spans

## 1. Mục tiêu thực hành

Trong ứng dụng Spring Boot có nhiều **application module**, các lời gọi Java giữa module thường diễn ra trong cùng một tiến trình. Một công cụ tracing chỉ nhận diện HTTP server, JDBC hay HTTP client có thể cho thấy một request hoàn tất trong 200 ms mà không chỉ ra thời gian đã dành cho module **orders**, **catalog** hay **billing**. **Spring Modulith Documentation & Observability** cung cấp cách quan sát những lần đi vào API của application module, từ đó đối chiếu kiến trúc nguồn với luồng xử lý được ghi nhận khi ứng dụng vận hành.

Bài **“Bật module entry spans”**, thuộc chương **Thực hành tổng hợp**, xây dựng một ứng dụng nhỏ có module **orders** gọi API công khai của **catalog**, bật instrumentation của Spring Modulith, cấu hình Micrometer Tracing và kiểm tra các span sinh ra. Sau bài, bạn có thể:

1. Giải thích **module entry span** ghi nhận ranh giới nào và khác span HTTP, span JDBC, event metric ra sao.
2. Khai báo module theo cấu trúc package, xác minh phụ thuộc và xác định API được instrumentation.
3. Thêm đúng dependency để Spring Modulith tạo observation/span cho lời gọi vào module.
4. Nối **ObservationRegistry → Micrometer Tracing → tracer bridge → SDK/exporter** để nhìn thấy span đã hoàn tất.
5. Gửi một HTTP request và đọc span dựa trên các thuộc tính **module.identifier**, **module.name**, **module.method**, **module.invocation-type**.
6. Kiểm thử bằng exporter trong bộ nhớ, xử lý trường hợp thiếu span, sampling sai hoặc mất context khi chuyển sang listener bất đồng bộ.

Ví dụ định hướng **Java 17+, Spring Boot 3.x, Spring Modulith 1.x tương thích, Micrometer Tracing và OpenTelemetry**. Với Spring Boot/Spring Modulith 2.x hoặc các nhánh mới hơn, hãy dùng BOM và artifact theo tài liệu đúng phiên bản; đặc biệt tên artifact observability ở nhánh 2.x có thể khác. Không lấy một số version từ ví dụ rồi gắn vào một dự án dùng BOM khác.

## 2. Module entry span thực sự quan sát điều gì?

Khi **Spring component nằm trong API của một application module**, Spring Modulith có thể trang trí bean đó bằng interceptor/aspect. Lời gọi qua proxy tới phương thức API được instrument sẽ tạo một Micrometer observation và, nếu tracing handler hoạt động, một **module entry span**. Cơ chế được thiết kế để hiển thị **ranh giới module** khi lời gọi đi qua các API được công bố.

~~~mermaid
sequenceDiagram
    participant H as HTTP caller
    participant O as orders module
    participant P as catalog API proxy
    participant C as catalog module
    participant T as Micrometer + Tracer
    H->>O: POST /orders?sku=SKU-1
    Note over O: HTTP server span / nghiệp vụ orders
    O->>P: isAvailable(SKU-1)
    P->>T: Mở module entry observation (catalog)
    P->>C: CatalogFacade.isAvailable()
    C-->>P: true
    P->>T: Đóng observation / kết thúc span
    P-->>O: true
    O-->>H: ACCEPTED
~~~

Những điểm cần hiểu:

- **Module entry span** mô tả lần đi vào một API/module được quan sát; nó không biểu thị mỗi dòng Java, mỗi method private hay mọi thao tác bên trong module.
- Spring Modulith **không yêu cầu ứng dụng tách thành microservices**. Module là ranh giới logic bên trong cùng ứng dụng.
- Việc thêm observability dependency **không tự sửa kiến trúc**. Nó giúp quan sát đường gọi qua API; kiểm tra dependency/source vẫn là trách nhiệm của **ApplicationModules.verify()** và bài test kiến trúc.
- **Span** có thời gian bắt đầu/kết thúc, trace ID, span ID, có thể có parent, tags/attributes và trạng thái lỗi. **Metric** là measurement tổng hợp; một counter event tăng không phải là bằng chứng rằng một module entry span đã được tạo.
- **Module graph** từ source cho biết quan hệ phụ thuộc có thể xảy ra, còn trace cho biết tương tác được thực thi và ghi nhận trong một kịch bản cụ thể.

Tài liệu Spring Modulith mô tả bốn thuộc tính quan trọng của module entry span:

| Thuộc tính span | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| **module.identifier** | Định danh kỹ thuật của application module | **catalog** |
| **module.name** | Tên module để người đọc nhận biết | **Catalog** hoặc tên mặc định mà framework xác định |
| **module.invocation-type** | Kiểu lời gọi được instrument, chẳng hạn **bean** hoặc **event listener** | **bean** |
| **module.method** | Phương thức đang thực thi trên module | **CatalogFacade.isAvailable(...)** hoặc biểu diễn do framework cung cấp |

Giá trị cụ thể và tên span có thể thay đổi theo convention/phiên bản. Khi viết assertion, ưu tiên key đã được tài liệu của phiên bản sử dụng xác nhận; tránh giả định tên hiển thị của span là một chuỗi bất biến.

## 3. Tạo ứng dụng có một đường gọi xuyên module rõ ràng

Giả sử ứng dụng tên **shop** có package gốc **com.example.shop**. Theo cách phát hiện module mặc định, các package con trực tiếp có thể trở thành application module:

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── orders/
│   ├── OrderController.java
│   └── OrderService.java
└── catalog/
    ├── CatalogFacade.java
    └── internal/
        └── CatalogRepository.java
~~~

**catalog** công bố **CatalogFacade** trong package gốc của module; phần triển khai nội bộ có thể nằm dưới **catalog.internal**. **orders** chỉ phụ thuộc vào API công khai của catalog, tránh import class nằm trong **catalog.internal**.

### 3.1. Spring Boot entry point

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

### 3.2. API công khai của catalog

~~~java
package com.example.shop.catalog;

import org.springframework.stereotype.Service;

@Service
public class CatalogFacade {

    public boolean isAvailable(String sku) {
        // Dữ liệu giả để cô lập việc quan sát ranh giới module.
        return "SKU-1".equals(sku);
    }
}
~~~

Ở bài này, class **CatalogFacade** nằm ngay package **catalog**, là một Spring bean và có method **public**. Đây là đường gọi phù hợp để kiểm tra instrumentation của API module. Nếu chuyển toàn bộ API sang **catalog.internal**, Spring Modulith có thể không xem đó là API được công bố theo quy tắc module mặc định; **đừng di chuyển code chỉ để ép instrumentation**. Hãy thiết kế boundary đúng trước.

### 3.3. Orders gọi catalog qua bean của Spring

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogFacade;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final CatalogFacade catalog;

    public OrderService(CatalogFacade catalog) {
        this.catalog = catalog;
    }

    public String place(String sku) {
        return catalog.isAvailable(sku) ? "ACCEPTED" : "OUT_OF_STOCK";
    }
}
~~~

~~~java
package com.example.shop.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<String> place(@RequestParam String sku) {
        return ResponseEntity.ok(service.place(sku));
    }
}
~~~

Đường đi cần kiểm chứng là **HTTP → orders → catalog**. Một lời gọi tới **CatalogFacade.isAvailable()** đi qua bean mà Spring quản lý; đây là điểm để module instrumentation chặn và ghi span. Nếu chỉ gọi **new CatalogFacade().isAvailable(...)** hoặc tự gọi method khác trong cùng object mà không qua proxy, bạn đã bỏ qua một phần cơ chế AOP và có thể không nhận được span mong đợi.

**Tính chất demo:** phương thức **place** mới giả lập quyết định đặt hàng, chưa lưu order hoặc tạo giao dịch. Khi đưa vào dự án thật cần xác thực đầu vào, transaction, repository, error handling và các test nghiệp vụ.

## 4. Bật instrumentation của Spring Modulith

Ở Spring Modulith dòng **1.x**, dependency **spring-modulith-starter-insight** là lựa chọn thực hành tiện lợi vì tích hợp **Actuator + Modulith observability**. Khi đã có Actuator, có thể dùng artifact observability phù hợp thay vì lặp lại starter. Ở dòng **2.x**, starter Insight tiếp tục là cách chọn ổn định, nhưng artifact triển khai bên trong có thay đổi tên; hãy dùng BOM của đúng nhánh.

Ví dụ dependencies Maven, đặt trong **pom.xml** của ứng dụng vốn đã có Boot parent hoặc Boot BOM và Modulith BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Quan trọng về phiên bản:**

- **Spring Boot BOM** quản lý nhiều dependency của Micrometer, OTel và Spring; **Spring Modulith BOM** quản lý các artifact Modulith. Khai báo Modulith BOM phù hợp với nhánh Spring Boot của dự án.
- Nếu dùng riêng artifact trên nhánh **1.x**, tên thường là **spring-modulith-observability**; ở dòng **2.x**, tài liệu có **spring-modulith-observability-core**. Dùng **starter-insight** giúp tránh phụ thuộc trực tiếp vào chi tiết đó khi không cần.
- **starter-insight** đem tới hỗ trợ Actuator/module observation nhưng không tự bảo đảm có exporter truy vết. **micrometer-tracing-bridge-otel** nối Micrometer Tracing với OTel; SDK/exporter và cấu hình tương ứng hoàn thiện đường gửi span.
- Nếu dự án đang dùng **micrometer-tracing-bridge-brave**, cần exporter/reporter của Brave phù hợp. Không thêm song song hai bridge chỉ để bật Modulith.
- Chỉ đặt **spring-modulith-starter-insight** vào scope runtime và dùng **spring-modulith-starter-core** trong compile scope khi cần API core; không để cấu hình production vô tình phụ thuộc vào test classes.

Tài liệu chính thức về các cơ chế và artifact: **https://docs.spring.io/spring-modulith/reference/production-ready.html**. Khi tích hợp vào dự án cụ thể, luôn đối chiếu hướng dẫn tương ứng với bản Spring Modulith đã khóa.

### Không cần tự viết aspect cho entry span

Với observability integration được kích hoạt đúng và application module được nhận diện, Spring Modulith tự trang trí các Spring component thuộc API module để tạo observation tại điểm vào. Không cần thêm một **@Aspect** tự viết quanh cùng method để lấy module entry span, vì dễ tạo hai span trùng và đo lặp latency. Bạn vẫn có thể dùng **@Observed** cho tác vụ riêng chưa được Modulith instrument; cần xác định đó là operation khác, không phủ hai lần lên cùng boundary.

## 5. Cấu hình Actuator, sampling và exporter

Trong môi trường chạy thử, cấu hình **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Đây là **cấu hình local/integration** minh họa cho Spring Boot 3.x khi dùng OTLP tracing HTTP; collector phải thực sự được chạy ở địa chỉ cấu hình. Property và cách dựng exporter có thể khác ở bản Boot khác: kiểm tra configuration metadata và startup logs của dự án. **Sampling 1.0 (100%)** giúp dễ xác nhận span trong bài; ở production cần dùng sampling phù hợp thay vì để cố định 100% không kiểm soát.

Khi chỉ muốn kiểm thử span mà không dựng collector, có thể dùng **InMemorySpanExporter** và cấu hình test ở mục 9; không cần OTLP endpoint chạy để làm test đó. Ngoài ra có thể xem log tracing nếu được cấu hình, nhưng log có trace ID **không chứng minh** span đã tới backend.

**Actuator endpoint** **/actuator/modulith** cung cấp metadata kiến trúc của application module khi dependency và exposure được cấu hình. Nó không phải API để liệt kê toàn bộ module entry spans runtime. Endpoint **/actuator/metrics** cho biết meter, còn span cần đọc từ tracer/exporter/backend tương ứng.

Trong môi trường production cần hạn chế Actuator exposure, yêu cầu xác thực/phân quyền và không công khai module graph ra Internet tùy ý. OTLP endpoint nên sử dụng TLS và bảo vệ thông tin đăng nhập theo hạ tầng đang dùng.

## 6. Chạy thử và nhận diện module entry span

Chạy ứng dụng bằng công cụ build của dự án:

~~~bash
./mvnw spring-boot:run
~~~

Nếu dùng Gradle, lệnh tương ứng thường là **./gradlew bootRun**. Với ứng dụng local chạy ở port 8080, thực hiện:

~~~bash
curl -i -X POST 'http://localhost:8080/orders?sku=SKU-1'
curl -s http://localhost:8080/actuator/modulith
~~~

Kết quả HTTP đầu tiên dự kiến là **200 OK** với body **ACCEPTED**; thử **sku=SKU-404** để thấy **OUT_OF_STOCK**. Kết quả Actuator (nếu được bật đúng) cần thể hiện các module như **orders** và **catalog**, cùng quan hệ phụ thuộc từ **orders** sang **catalog**. Kết quả JSON thực tế phụ thuộc bản Spring Modulith; không nên hard-code một cấu trúc response chưa được xác nhận.

Trên Jaeger, Zipkin hoặc Grafana Tempo (tùy collector và exporter), chọn service **shop-modulith** rồi tìm trace tương ứng với HTTP request mới gửi. Một trace có thể hiển thị về mặt logic:

~~~text
HTTP POST /orders            [HTTP server span]
└── orders ...               [có thể có span tùy điểm vào API]
    └── catalog ...          [module entry span tại CatalogFacade]
~~~

**Điều cần kiểm tra thay vì chỉ nhìn tên:**

1. Có span được gắn **module.identifier=catalog** khi **CatalogFacade.isAvailable()** được gọi qua Spring bean.
2. **module.invocation-type** phản ánh lời gọi bean; **module.method** gắn tới API được thực thi theo convention đang dùng.
3. Thời gian bắt đầu/kết thúc tương ứng với đoạn xử lý catalog, nằm trong hoặc có liên hệ nhân quả với HTTP request tùy tracing pipeline.
4. Có **traceId** thích hợp và parent/link nếu hiện diện; cùng một process, cùng thread và instrumentation được nối đúng thường có quan hệ parent-child.
5. Không có thông tin như mã đơn hàng, email hoặc khóa bí mật trong span attributes nếu ứng dụng không có yêu cầu thu thập được phê duyệt.

**Không thấy một span riêng cho method private trong catalog là điều bình thường.** Mục tiêu của module entry spans là ranh giới module/API; các phương thức nội bộ không nhất thiết tạo span mới.

### Phân biệt module entry spans với event metrics

Spring Modulith cũng có khả năng ghi metric cho domain event publication; ở một số nhánh tài liệu, counter tổng hợp được mô tả với tên **module.events.published** và counter theo module/loại event. Metric có thể xuất hiện khi event được phát, nhưng nó **không thay thế** dấu vết thực thi của listener. Nếu ví dụ chỉ gọi method đồng bộ và chưa phát event, không được yêu cầu counter event phải tăng chỉ vì module entry span đã xuất hiện.

## 7. Kiểm tra source boundary trước khi đánh giá trace

Tạo test kiểm tra kiến trúc ứng dụng:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void modulesObeyDeclaredBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ApplicationModules.verify()** có thể phát hiện các vi phạm được Spring Modulith hỗ trợ kiểm tra như phụ thuộc vòng hoặc tham chiếu tới phần implementation không được công bố. Nó xác nhận **cấu trúc source**, còn trace/entry span là bằng chứng **runtime**; cần dùng cả hai.

Nếu thêm **spring-modulith-docs** vào test classpath, có thể sinh module graph bằng **Documenter**:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void generateModuleGraph() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeModulesAsPlantUml();
    }
}
~~~

Các artifact được sinh ở vị trí quy định theo phiên bản/cấu hình test. Đối chiếu module graph có cạnh **orders → catalog** với trace cho kịch bản gọi **POST /orders**. Một module dependency có trong source mà chưa thấy span có thể do nhánh chưa được thực thi, phương thức không đi qua proxy, sampling bỏ trace hoặc instrumentation/collector chưa đúng. Không đồng nhất **cạnh source** với **cạnh runtime**.

## 8. Hiểu điều kiện và giới hạn tự động instrument

Để một lời gọi vào catalog có cơ hội tạo module entry span, kiểm tra lần lượt:

| Điều kiện | Tại sao cần | Phép kiểm tra |
| --- | --- | --- |
| Module được Spring Modulith phát hiện | Framework phải biết ranh giới module và bean thuộc module nào. | **ApplicationModules.of(...).verify()**, Actuator module metadata. |
| Target là bean của Spring | Bean post-processor/aspect hoạt động trên object do Spring quản lý. | Inject **CatalogFacade** qua constructor; tránh **new CatalogFacade()**. |
| API thuộc phần công khai của module | Modulith quan sát các component của module API. | **CatalogFacade** nằm trong package gốc hoặc named interface hợp lệ. |
| Lời gọi đi qua proxy | Interceptor cần có cơ hội chặn method invocation. | Không kết luận từ self-invocation hay method private. |
| Có observability integration | Thiếu Modulith observability thì chỉ còn logic nghiệp vụ. | Kiểm tra **starter-insight**/artifact đúng phiên bản trên runtime classpath. |
| Observation handler hoạt động | Observation cần được chuyển thành span. | Kiểm tra **ObservationRegistry** và tracing handler. |
| Tracing pipeline sẵn sàng | SDK/exporter/sampler quyết định span có xuất được không. | Test in-memory exporter trước khi kiểm tra backend. |

**Các giới hạn cần lưu ý:** Spring AOP có hạn chế về final class/method, phương thức không được proxy, self-invocation và proxy bị bypass. Nếu API module là interface với nhiều implementation, cần kiểm tra kiểu proxy và điểm injection thực. **Không nên sửa visibility của các class nghiệp vụ chỉ nhằm tăng số span**; instrumentation nên phản ánh boundary thật.

Một bean thuộc **catalog.internal** có thể vẫn được ứng dụng gọi qua đường vi phạm kiến trúc, nhưng không vì thế mà Spring Modulith bảo đảm có module entry span cho lời gọi đó. Hãy giải quyết vi phạm boundary trước rồi mới bổ sung kiểm thử observability.

## 9. Viết integration test kiểm chứng module entry span

Thay vì phụ thuộc collector trên mạng trong mọi bài test, dùng **InMemorySpanExporter** của OpenTelemetry SDK. Ví dụ sau chỉ dành cho phương án **micrometer-tracing-bridge-otel**; với Brave phải dùng cơ chế thu span tương ứng.

Thêm dependencies vào test classpath:

~~~xml
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-sdk</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-sdk-testing</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ở **src/test/java/com/example/shop/InMemoryTracingConfig.java**:

~~~java
package com.example.shop;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class InMemoryTracingConfig {

    @Bean
    InMemorySpanExporter testSpanExporter() {
        return InMemorySpanExporter.create();
    }

    @Bean(destroyMethod = "close")
    SdkTracerProvider testTracerProvider(InMemorySpanExporter exporter) {
        return SdkTracerProvider.builder()
                .setSampler(Sampler.alwaysOn())
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
    }

    @Bean
    @Primary
    OpenTelemetry testOpenTelemetry(SdkTracerProvider provider) {
        return OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build();
    }
}
~~~

**Điều kiện thiết yếu:** Micrometer Tracing bridge trong ApplicationContext phải dùng đúng **OpenTelemetry SDK** đã được nối với **InMemorySpanExporter**, và **ObservationRegistry** phải có tracing observation handler. **@Primary** chỉ ưu tiên một bean khi inject; nếu dự án vẫn dựng provider/exporter khác qua auto-configuration, phải điều chỉnh config theo phiên bản Boot và vô hiệu hóa exporter mạng trong test. Chỉ tạo exporter trong bộ nhớ mà không nối nó vào pipeline tracing thật sẽ khiến danh sách span rỗng.

Ở **src/test/resources/application-test.yml**, đặt sampling 100% và tắt các exporter mạng tùy phiên bản/stack đang dùng. Với ứng dụng đã tự cấu hình export, cần kiểm tra không có telemetry rời máy test:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Tạo integration test **src/test/java/com/example/shop/ModuleEntrySpanTests.java**:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(InMemoryTracingConfig.class)
class ModuleEntrySpanTests {

    @Autowired MockMvc http;
    @Autowired InMemorySpanExporter exporter;

    @Test
    void recordsCatalogModuleEntry() throws Exception {
        exporter.reset();

        http.perform(post("/orders").param("sku", "SKU-1"))
                .andExpect(status().isOk())
                .andExpect(content().string("ACCEPTED"));

        assertThat(exporter.getFinishedSpanItems())
                .anySatisfy(span -> {
                    String moduleId = span.getAttributes()
                            .get(AttributeKey.stringKey("module.identifier"));
                    assertThat(moduleId).isEqualTo("catalog");
                });
    }
}
~~~

Khi thử trên phiên bản cụ thể, kiểm tra **module.identifier** được ghi dưới dạng string span attribute như tài liệu của phiên bản mô tả. Test này không khóa tên span cụ thể; nó tìm **module entry span của catalog** qua tag. Nếu integration setup chạy request async hoặc span xuất bằng **BatchSpanProcessor**, cần đợi span hoàn tất với timeout rõ ràng trước assertion; cấu hình ví dụ dùng **SimpleSpanProcessor** nên xuất đồng bộ khi span kết thúc.

**Kiểm tra sâu hơn:** sau khi tìm span catalog, assert thêm **module.invocation-type** và **module.method** nếu phiên bản hiện dùng ghi các thuộc tính đó; đối chiếu traceId của catalog span với HTTP request span tương ứng. Không buộc **parentSpanId** phải bằng HTTP span nếu có span trung gian hợp lệ.

Trong ví dụ, class test và test configuration là minh họa để tích hợp vào một project Spring Boot thực; không có nghĩa bài học này đã chạy ứng dụng hay xác nhận mọi auto-configuration của một phiên bản chưa biết.

## 10. Mở rộng: module entry spans với event listener bất đồng bộ

Một hệ thống doanh nghiệp thường có luồng **orders** phát **OrderPlaced**, **billing** xử lý event. Với Spring Modulith, việc instrument entry của event listener có thể tạo span với **module.invocation-type** là **event listener** theo hỗ trợ của phiên bản đã chọn. Khi dùng **@ApplicationModuleListener**, nhớ rằng delivery có thể bất đồng bộ và sau transaction commit.

~~~mermaid
sequenceDiagram
    participant H as HTTP
    participant O as orders
    participant E as Event infrastructure
    participant B as billing
    H->>O: placeOrder
    O->>E: publish OrderPlaced
    E-->>B: giao event sau commit/async
    B->>B: handle OrderPlaced
    Note over E,B: Context có thể bị đứt tại thread/commit boundary
~~~

Module entry span của **billing** có thể xuất hiện trong trace khác nếu mất context qua executor, transaction callback hoặc replay. Điều này không nhất thiết có nghĩa event bị mất hoặc kiến trúc sai. Khi chẩn đoán:

1. Xác minh listener đã thực sự chạy và publication đã hoàn thành hay còn pending.
2. Kiểm tra tracing handler/exporter đã tạo span của listener chưa.
3. So traceId/span parent hoặc links giữa publisher và consumer, xác định **thread và executor thực tế**.
4. Với task chạy trong cùng tiến trình, dùng **ContextPropagatingTaskDecorator** (Spring Framework 6.1+ và **io.micrometer:context-propagation**) trên executor thực sự nhận task.
5. Với event sau commit, quan sát thời điểm context gốc đã hết scope hay chưa. Với broker hoặc retry/replay sau restart, truyền context qua message headers hoặc dùng span links/correlation ID; ThreadLocal cũ không tồn tại.

Đừng giả định mọi async span phải là child trực tiếp của request HTTP. Trace và event ID có thể được liên kết theo mô hình phù hợp với luồng và vòng đời thực tế.

## 11. Phân biệt Actuator/module graph, spans và event metrics

Spring Modulith cho ta ba loại dữ liệu bổ sung nhau:

| Nguồn | Câu hỏi trả lời | Không tự trả lời |
| --- | --- | --- |
| **ApplicationModules / Documenter / /actuator/modulith** | Module nào tồn tại, dependency nào được phát hiện? | Lời gọi đã thực sự chạy ở request này chưa? |
| **Module entry spans** | Phương thức API/module nào được truy cập trong kịch bản được tracing? | Tất cả các dependency source và tất cả nhánh chưa chạy? |
| **Event publication metrics / registry** | Event nào được phát, bao nhiêu lượt/loại event; trạng thái xử lý nếu registry hỗ trợ? | Trace context đã được nối qua async hay chưa? |

Một module graph có cạnh **orders → catalog**, nhưng không thấy catalog entry span có thể là vì request kiểm thử không đi qua nhánh gọi catalog hoặc instrumentation bị thiếu. Một span **catalog** xuất hiện trong trace cũng không tự chứng minh mọi quy tắc ranh giới module đều đúng. Hãy giữ hai lớp kiểm tra: **static architecture** và **runtime observation**.

Khi phát hiện span có tên khó đọc hoặc tag không chính xác, kiểm tra **ModulithObservationConvention** (nếu phiên bản có SPI này) và convention Micrometer trước khi tùy biến. Việc đổi convention có thể khiến dashboard/test cũ không nhận ra span; ghi rõ tên key nào được dự án quy ước, khóa version và lưu trường hợp hồi quy.

## 12. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| **/actuator/modulith** trả 404 | Thiếu Actuator/Modulith actuator, endpoint không exposed hoặc URL/context path khác. | Kiểm tra dependency, endpoint exposure và Spring Security. |
| Graph có catalog nhưng trace không có catalog entry | API bị đặt trong package internal, gọi không qua Spring proxy, hoặc instrumentation không được bật. | So cấu trúc package, điểm injection, runtime classpath. |
| Có HTTP span nhưng không có module entry span | Thiếu Modulith observability hoặc bean post-processor/interceptor chưa áp dụng. | Kiểm tra starter, module được phát hiện và bean/API thực tế. |
| Có counter nhưng không có span | Metric handler có, tracing handler/bridge/sampler/exporter thiếu hoặc sai. | Test in-memory exporter, kiểm tra **Tracer.currentSpan()**. |
| Span có trong test nhưng collector rỗng | OTLP endpoint, protocol, TLS, xác thực hoặc exporter không hoạt động. | Đọc exporter logs, collector logs và test network. |
| Listener xuất hiện ở trace khác | Context mất khi đổi thread, sau commit hoặc replay. | Kiểm tra executor, context propagation, message carrier. |
| Span không có **module.identifier** | Span đang xem không phải module entry, hoặc convention/version khác. | Xem raw attributes, phân biệt HTTP/JDBC span với module span. |
| Tên span/module khác dự kiến | Thay module display name, conventions hoặc bản Modulith. | Đối chiếu module graph và tài liệu API phiên bản đang dùng. |
| Test exporter rỗng dù service trả đúng | Test SDK không được bridge dùng, span chưa hoàn tất hoặc sampler bỏ. | Kiểm tra bean/provider/handler được inject và trạng thái span. |
| Hai span cùng ý nghĩa | Instrumentation tự động và **@Observed**/custom **@Aspect** cùng đo một API. | Tìm trùng instrumentation và chọn một boundary cần quan sát. |

### Quy trình gỡ lỗi có thể tái hiện

1. Khóa revision, active profile, dependency versions và sampling; dùng một request có thể lặp lại.
2. Chạy **ApplicationModules.verify()**, kiểm tra package API và quan hệ orders → catalog.
3. Thử trực tiếp **CatalogFacade** qua Spring bean; nếu không có entry span, kiểm tra Modulith instrumentation.
4. Xác nhận ObservationRegistry có tracing handler, bridge dùng đúng SDK và exporter nhận span.
5. Nếu in-memory exporter nhận span nhưng collector ngoài không có, chuyển sang kiểm tra network/exporter/collector.
6. Nếu thêm event async, tách lỗi **event chưa xử lý** khỏi lỗi **đã xử lý nhưng không nối trace**.
7. Sau khi sửa, chạy lại cùng bài test, so span tags/trace links và kết quả nghiệp vụ.

Không nên “chữa” bằng cách tăng sampling production lên 100% lâu dài hoặc bỏ assertion span. Khi kiểm tra telemetry có dữ liệu người dùng, tránh đưa **orderId**, **email**, **traceId** vào metric labels có cardinality cao, giới hạn trace/log retention và phân quyền truy cập.

## 13. Bài tập mở rộng và tiêu chí nghiệm thu

### Bài tập

1. Thêm module **shipping** và một API **ShippingFacade** công khai. Cho **orders** lần lượt gọi **catalog** và **shipping**; so module graph và trace sau một HTTP request.
2. Chuyển **CatalogFacade** từ package gốc sang **catalog.internal** trong nhánh test có kiểm soát; chạy **ApplicationModules.verify()** và quan sát hành vi instrumentation. Hoàn nguyên để giữ thiết kế hợp lệ.
3. Dùng **InMemorySpanExporter** để kiểm tra **module.identifier=catalog**. Bổ sung assertion **module.invocation-type** cho phiên bản của bạn và tránh khóa tên span hiển thị nếu đó là implementation detail.
4. Bật event **OrderPlaced** với listener **billing**. Xác minh event chạy, counter publication phù hợp và module entry span của listener nếu instrumentation hỗ trợ.
5. Chuyển listener sang async, thử context decorator ở đúng executor và so trước/sau; ghi rõ điều kiện after-commit hoặc replay có thể cần span link thay parent trực tiếp.
6. Đổi từ OTel bridge sang Brave ở một nhánh test cô lập cùng BOM tương thích, dùng exporter/test handler phù hợp rồi so tên/tags và quan hệ trace.

### Bảng nghiệm thu

| Tiêu chí | Bằng chứng cần lưu | Kết quả mong đợi |
| --- | --- | --- |
| Cấu trúc module | **ApplicationModules.verify()** và module graph | Nhận diện **orders**, **catalog**, phụ thuộc hợp lệ |
| Gọi API module | POST **/orders?sku=SKU-1** | HTTP 200, **ACCEPTED**, method CatalogFacade chạy |
| Instrumentation Modulith | Raw span attributes | Có module entry span của **catalog** |
| Tracing pipeline | InMemorySpanExporter hoặc collector test | Có finished span, traceId hợp lệ |
| Quan hệ trace | Parent/span link hoặc cùng trace theo kịch bản | Liên hệ HTTP → module được giải thích rõ |
| Event (nếu mở rộng) | Publication state, listener log/trace | Event xử lý đúng; không nhầm delivery với trace |
| Bảo mật và vận hành | Actuator exposure, sampling, labels | Không lộ thông tin nhạy cảm, không tăng cardinality bất hợp lý |

### Câu hỏi tự kiểm tra

1. Vì sao lời gọi vào **CatalogFacade** qua Spring bean có thể tạo module entry span, còn **new CatalogFacade()** không thể trông chờ cùng instrumentation?
2. **module.identifier**, **module.invocation-type** và **module.method** giúp giải thích điều gì về trace?
3. Vì sao **/actuator/modulith** hiển thị module nhưng collector chưa chắc có span?
4. Vì sao counter **module.events.published** tăng không có nghĩa listener đã có span nối với publisher?
5. Khi một span chỉ xuất hiện ở test exporter nhưng không xuất hiện trên Jaeger/Tempo, cần điều tra tầng nào?
6. Khi có **@ApplicationModuleListener** sau commit, tại sao một decorator đúng vẫn có thể không thấy parent span ban đầu?
7. Khi nào việc thay **ModulithObservationConvention** làm thay đổi dashboard hoặc assertion?

**Kết quả cần nộp:** ứng dụng mẫu hai module, đồ thị source và phép kiểm tra ranh giới, cấu hình Modulith observability cùng Micrometer Tracing, HTTP request minh họa, module entry span **catalog** có các attributes phù hợp, test exporter và bảng bằng chứng trước/sau khi sửa lỗi (nếu có). Qua đó, bạn bật và kiểm chứng được **module entry spans** để liên hệ thiết kế application module với hành vi thực sự được quan sát trong Spring Boot.
