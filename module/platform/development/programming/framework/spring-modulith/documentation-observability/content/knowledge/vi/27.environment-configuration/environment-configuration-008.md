# Kiểm tra cấu hình sau khi đóng gói

> **Chương:** Cấu hình môi trường
>
> **Bối cảnh học tập:** Spring Modulith Documentation & Observability hỗ trợ tạo tài liệu ranh giới application module, xem module graph và quan sát tương tác qua Actuator, event metrics, tracing và context propagation. Bài này tập trung xác minh những khả năng đó **vẫn hoạt động trong ứng dụng Spring Boot đã được đóng gói và chạy bằng cấu hình môi trường thực tế**.

## 1. Vì sao phải kiểm tra lại sau khi đóng gói?

Giả sử ứng dụng `shop` có ba application module: `orders`, `inventory` và `payments`. Khi chạy trong IDE, dự án đọc `application-local.yaml`, test tạo sơ đồ module thành công, log có trace ID. Nhưng khi chuyển thành executable JAR và chạy với profile `staging`, endpoint `/actuator/modulith` trả về 404, các event metrics không có dữ liệu hoặc trace bị đứt sau bước xử lý bất đồng bộ.

Các triệu chứng này có thể đến từ **classpath của bản đóng gói**, profile đang kích hoạt, file cấu hình ngoài JAR, quyền truy cập Actuator, exporter telemetry, hoặc cơ chế chuyển ngữ cảnh qua luồng. Chạy được `java -jar` chỉ chứng minh ứng dụng khởi động; chưa đủ để chứng minh chức năng documentation/observability được cấu hình đúng.

Sau bài học, bạn có thể:

1. Kiểm tra đúng artifact sẽ triển khai: executable JAR, dependency runtime và tài nguyên cấu hình.
2. Xác định **cấu hình có hiệu lực** sau khi ghép cấu hình đóng gói, profile, biến môi trường và tham số khởi động.
3. Đối chiếu **module graph** ở runtime với kiến trúc đã xác minh trước khi build.
4. Xác nhận Actuator, chỉ số công bố domain event, module-entry spans và trace context khi đi qua bất đồng bộ.
5. Thiết kế smoke test và tiêu chí chấp nhận để ngăn một bản phát hành mất khả năng quan sát.

### Phân biệt bốn lớp kiểm tra

| Lớp | Câu hỏi cần trả lời | Bằng chứng phù hợp |
| --- | --- | --- |
| **Source/build** | Mã có tuân thủ ranh giới module và test tạo tài liệu không? | `ApplicationModules.verify()`, `Documenter`, kết quả test. |
| **Artifact** | Đã đóng gói đủ class, resource và dependency runtime chưa? | Nội dung JAR, dependency tree, checksum artifact. |
| **Effective configuration** | Profile nào đang chạy; override đến từ đâu; actuator được expose trên cổng nào? | Startup log, cấu hình môi trường, endpoint chẩn đoán được bảo vệ. |
| **Runtime behavior** | Module graph, event metrics và trace có thực sự xuất hiện khi có request/event? | HTTP Actuator, metric sau phát sự kiện, trace ở collector. |

Hai khái niệm dễ lẫn: **module graph** mô tả phụ thuộc tĩnh giữa các module; **trace** chỉ ghi lại tương tác phát sinh trong một lần thực thi được quan sát. Graph có thể có cạnh không được chạy trong một request; trace có thể thiếu span do sampling, thiếu instrumentation hoặc mất context. Cần kiểm tra cả hai.

## 2. Chuẩn bị artifact và ranh giới phiên bản

### 2.1. Khớp phiên bản Spring Boot với Spring Modulith

Spring Modulith chạy trên Spring Boot, vì vậy phải dùng bộ dependency tương thích. Ví dụ dưới đây minh họa **Spring Modulith 2.2.x với ứng dụng Spring Boot 4.x tương thích**; nếu dự án vẫn ở Boot 3.x, hãy dùng nhánh Spring Modulith được hỗ trợ cho Boot 3.x và tra cứu tài liệu tương ứng. Không sao chép nguyên phiên bản ví dụ vào dự án khác.

Một cấu hình Gradle Groovy DSL tối giản cho môi trường kiểm tra runtime:

~~~groovy
dependencies {
    // Minh họa: chọn cùng một nhánh Spring Modulith cho toàn bộ artifact.
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')

    // Bao gồm module actuator, instrumentation và Boot Actuator.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Chỉ cần khi muốn lấy metric bằng định dạng Prometheus.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Sử dụng trong bài test tạo graph và kiểm tra kiến trúc.
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Giả định dự án đã có plugin Spring Boot, dependency Spring Boot starters và JUnit phù hợp. `spring-modulith-starter-insight` cung cấp thành phần Actuator/observability của Modulith; **không tự động cấu hình một backend lưu trace**. Để xuất trace, cần thêm tracer/exporter và địa chỉ collector theo **phiên bản Spring Boot đang dùng** (ví dụ OpenTelemetry/OTLP hoặc Brave/Zipkin). Khi chỉ cần endpoint cấu trúc module, có thể dùng `spring-modulith-actuator` cùng `spring-boot-starter-actuator`; khi chỉ cần instrumentation, có thể dùng `spring-modulith-observability-core`.

Kiểm tra dependency theo **runtime classpath**, vì `compileClasspath` hoặc classpath lúc test có thể chứa thư viện mà JAR phát hành không chứa. Với bản dùng Maven/Gradle, nên khóa cùng một BOM/nhóm phiên bản thay vì gắn từng artifact Spring Modulith bằng các phiên bản khác nhau.

### 2.2. Chạy xác minh kiến trúc và tạo tài liệu ở build

Ví dụ với lớp khởi động `com.acme.shop.ShopApplication`:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModulithDocumentationTests {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }

    @Test
    void generatesDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

`verify()` kiểm tra phụ thuộc vòng, truy cập vào nội bộ module và các ràng buộc phụ thuộc đã khai báo. `Documenter` tạo các mô tả C4/UML và module canvas cho developer; thông thường đầu ra nằm dưới `spring-modulith-docs` trong thư mục build. **Các file tài liệu sinh ra khi test không mặc nhiên trở thành HTTP endpoint hay được nhúng vào executable JAR.** Nếu cần phát hành cùng build, phải định nghĩa rõ bước lưu trữ/publish tài liệu như một artifact riêng.

Trình tự tham khảo:

~~~bash
# Maven: chạy test để xác minh kiến trúc trước khi package.
./mvnw clean verify

# Hoặc Gradle: chạy test và tạo bootJar.
./gradlew clean test bootJar
~~~

Đối chiếu graph/tài liệu từ build với module graph Actuator lấy từ **chính artifact đã đóng gói**. Nếu có `ApplicationModuleDetectionStrategy` tùy chỉnh, đặt cấu hình phát hiện module vào **production sources** để runtime thấy được; cấu hình chỉ nằm trong test sources có thể cho hai kết quả khác nhau.

## 3. Kiểm tra nội dung executable JAR

Giả sử file phát hành đã được đặt tên cố định là `shop.jar`. Với executable JAR chuẩn của Spring Boot:

~~~bash
jar tf shop.jar | grep 'BOOT-INF/classes/application'
jar tf shop.jar | grep 'BOOT-INF/lib/spring-modulith'
jar tf shop.jar | grep 'BOOT-INF/lib/micrometer'
~~~

Nếu làm việc trên PowerShell, thay `grep` bằng `Select-String`:

~~~powershell
jar tf shop.jar | Select-String 'BOOT-INF/classes/application'
jar tf shop.jar | Select-String 'BOOT-INF/lib/spring-modulith'
jar tf shop.jar | Select-String 'BOOT-INF/lib/micrometer'
~~~

Đường dẫn `BOOT-INF` áp dụng cho **executable JAR kiểu Spring Boot**, không áp đặt cho WAR, bản native image hoặc một cách đóng gói tùy chỉnh. Hãy kiểm tra:

- Có `application.yaml` / `application-{profile}.yaml` dự kiến trong `BOOT-INF/classes` hay không.
- Có dependency Spring Modulith Actuator và observability trên runtime classpath không; starter và các dependency transitively resolved phải đồng nhất phiên bản.
- Có registry metrics, tracer/exporter thực tế nếu yêu cầu dùng Prometheus hoặc xuất trace không.
- Artifact đúng build/commit, không phải JAR cũ ở thư mục khác. Có thể ghi hash SHA-256 trong biên bản triển khai để đối chiếu giữa môi trường thử và môi trường chạy.

**Không sửa trực tiếp cấu hình ở bên trong JAR đã phát hành.** Tạo một artifact bất biến rồi nạp cấu hình riêng theo môi trường để biết chắc cùng mã được thử ở staging và production. Không đặt secret, token hoặc mật khẩu thật trong `application*.yaml` đóng gói.

## 4. Chạy JAR với profile và cấu hình ngoài

### 4.1. Hiểu nguồn cấu hình có hiệu lực

Spring Boot đọc cấu hình từ nhiều nguồn. Trong trường hợp thông dụng, một giá trị được xác định theo thứ tự ưu tiên tăng dần như sau:

~~~mermaid
flowchart LR
    A["application.yaml trong JAR"] --> B["application-staging.yaml trong JAR"]
    B --> C["application.yaml bên ngoài JAR"]
    C --> D["application-staging.yaml bên ngoài JAR"]
    D --> E["Biến môi trường OS"]
    E --> F["Java system properties"]
    F --> G["Tham số --property=value khi chạy JAR"]
~~~

Sơ đồ là **một tập con của quy tắc ưu tiên**, chưa thể hiện mọi nguồn cấu hình của Spring Boot (như `SPRING_APPLICATION_JSON`, `@PropertySource` hoặc các nguồn trong test). `spring.config.import`, nhóm vị trí và cấu hình nhiều profile có quy tắc tải riêng. Khi chẩn đoán, đối chiếu [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) của phiên bản thực tế.

Đặc biệt:

- `spring.profiles.active` chọn profile; file `application-staging.yaml` không có tác dụng nếu `staging` không được kích hoạt.
- `spring.config.additional-location` **bổ sung** nơi đọc cấu hình; `spring.config.location` có thể **thay thế** những vị trí mặc định, nên dễ làm mất config trong JAR nếu dùng sai.
- Thư mục cấu hình ngoại vi và đường dẫn tương đối được tính từ **working directory của tiến trình**, không nhất thiết là thư mục chứa JAR; trong Docker/Kubernetes cần kiểm tra `WORKDIR`, volume mount và entrypoint.
- Để tác động đến việc tìm config, các thuộc tính khởi động rất sớm như `spring.config.location` và `spring.config.additional-location` phải truyền qua môi trường, Java system properties hoặc command line.

### 4.2. Ví dụ staging có Actuator riêng

Trong JAR, `application.yaml` chứa mặc định tối thiểu:

~~~yaml
spring:
  application:
    name: shop

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Trên host triển khai, file `./deploy/config/application-staging.yaml`:

~~~yaml
management:
  server:
    port: 19090
  endpoints:
    web:
      exposure:
        include: "health,info,modulith,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0
~~~

Chạy đúng JAR đã kiểm tra:

~~~bash
java -jar shop.jar \
  --spring.profiles.active=staging \
  --spring.config.additional-location=file:./deploy/config/ \
  --server.port=18080
~~~

File external phải có thật. Giá trị `management.server.port=19090` cho phép truy vấn Actuator qua cổng quản trị thay vì cổng ứng dụng 18080. Không có nghĩa cổng quản trị tự được bảo vệ: chỉ mở cho nội bộ, yêu cầu xác thực/ủy quyền phù hợp và tránh public expose.

Ở đây `management.tracing.sampling.probability=1.0` dành cho **smoke test cô lập** để không bỏ mẫu trace cần kiểm tra; trong production cần đặt tỷ lệ phù hợp theo tải và chính sách vận hành. Endpoint `prometheus` chỉ hoạt động nếu dependency registry Prometheus được thêm. Spring Boot thường **chỉ expose `health` qua HTTP theo mặc định**, nên cần kiểm tra cả cấu hình expose, mức access và security.

### 4.3. Bằng chứng khởi động cần ghi nhận

Sau khi chạy, xác minh rằng startup log cho thấy **active profile staging**, cổng application/management và ứng dụng bắt đầu phục vụ. Nếu dự án có cấu hình in ra marker build/version an toàn, so khớp marker với JAR đã phát hành. Không log toàn bộ `Environment` hoặc giá trị secret.

Trong môi trường thử đã bảo vệ, có thể dùng endpoint Actuator `env` / `configprops` để xác định nguồn property và giá trị được bind, nếu được expose có kiểm soát. Các endpoint này có thể chứa thông tin nhạy cảm và Spring Boot mặc định che nhiều giá trị; không bật `show-values=always` trên hệ thống mở. Khi khác biệt cấu hình gây lỗi, kiểm tra **giá trị có hiệu lực và nguồn override**, thay vì chỉ so sánh các file YAML.

## 5. Kiểm tra Application Module Actuator

Spring Modulith công bố endpoint cấu trúc module với ID **`modulith`** nếu có dependency phù hợp và endpoint được bật/cho phép truy cập. Trong cấu hình ví dụ:

~~~bash
curl -fsS http://localhost:19090/actuator/health
curl -fsS http://localhost:19090/actuator
curl -fsS http://localhost:19090/actuator/modulith
~~~

Ví dụ response giả định của `/actuator/modulith`:

~~~json
{
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.acme.shop.inventory",
    "dependencies": []
  },
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.acme.shop.orders",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["EVENT_LISTENER", "USES_COMPONENT"]
      }
    ]
  }
}
~~~

**Đây chỉ là dữ liệu minh họa**, không phải graph của một dự án cụ thể. Phản hồi thực tế có key theo tên module; các trường phổ biến gồm `displayName`, `basePackage`, `dependencies[].target` và `dependencies[].types`. Với nested modules còn có thể có thông tin `parent`/`nested`.

Để xác minh đúng sau khi đóng gói:

1. Kiểm tra HTTP status thành công và response có đúng các module mong đợi.
2. So sánh **tên module, package, các cạnh phụ thuộc và loại phụ thuộc** với bản tài liệu/graph được tạo ở build.
3. Tìm module bị thiếu do khác package scanning, cấu hình phát hiện module chỉ có trong test, hoặc dependency runtime bị thiếu.
4. Nếu graph khác bản đã duyệt, xem thay đổi như một **kiến trúc cần giải trình**; không sửa bằng cách mở rộng quyền truy cập module tùy tiện.

Endpoint này **công bố mô hình kiến trúc**, không thay thế việc chạy `ApplicationModules.verify()` trong CI và cũng không chứng minh mọi tương tác module đã được tracing. Tên package và quan hệ phụ thuộc có thể nhạy cảm về kiến trúc, vì vậy chỉ cho các đối tượng vận hành được ủy quyền truy cập.

## 6. Kiểm tra event metrics sau khi ứng dụng xử lý thực tế

Spring Modulith observability hỗ trợ các metric về việc phát domain event:

| Tên metric Micrometer | Ý nghĩa |
| --- | --- |
| `module.events.published` | Counter tổng hợp các domain event đã được công bố. |
| `module.events.published.{moduleIdentifier}.{simpleEventTypeName}` | Counter theo module và loại event tương ứng. |

Các tag thông dụng có `module.identifier`, `module.name` và `module.event.type` (tùy metric). Tag chứa order ID, user ID hoặc request ID sẽ gây cardinality rất cao và làm tăng chi phí lưu trữ, nên tránh đưa trực tiếp vào metric.

Một quy trình kiểm chứng có quan hệ nguyên nhân rõ ràng:

1. Ghi nhận giá trị counter ban đầu (nếu đã tồn tại).
2. Gọi **một API nghiệp vụ thử nghiệm** thực sự phát sự kiện, ví dụ tạo đơn hàng hợp lệ trong môi trường kiểm thử tách biệt.
3. Truy vấn `/actuator/metrics/module.events.published` sau khi xử lý.
4. Tìm giá trị metric và tag của module/event mong đợi; nếu có counter riêng, xác nhận nó cũng thay đổi.
5. Nếu dùng Prometheus, đọc `/actuator/prometheus` từ mạng nội bộ và đối chiếu metric đã được chuyển sang cách đặt tên của hệ thống scrape.

~~~bash
# Sau khi đã phát event thử nghiệm.
curl -fsS http://localhost:19090/actuator/metrics/module.events.published
curl -fsS http://localhost:19090/actuator/prometheus
~~~

**Không suy luận “mất metric” từ một counter chưa bao giờ được tạo**: có loại metric chỉ xuất hiện sau khi event thực sự được ghi nhận. Kiểm tra đúng tên event, đúng module phát, registry có sẵn, endpoint `metrics` được expose và application không bị filter metrics. Kiểm tra counter tăng không có nghĩa listener đã chạy thành công; đó là hai bước khác nhau.

Nếu dùng **Event Publication Registry** để hỗ trợ listener giao dịch, cần kiểm tra cả trạng thái hoàn tất/thất bại của event publication theo cơ chế registry của dự án. `spring.modulith.events.republish-outstanding-events-on-restart` không nên bật bừa để sửa metrics: hành vi replay có rủi ro tạo xử lý lại, đặc biệt trong triển khai nhiều instance.

## 7. Kiểm tra tracing và context propagation

### 7.1. Điều kiện tạo và nhìn thấy trace

Spring Modulith có thể đặt instrumentation quanh các Spring component thuộc **API của application module**, tạo module-entry spans khi tương tác đi qua ranh giới module. Các span có thể gắn thông tin như:

- `module.identifier`: định danh module.
- `module.name`: tên module.
- `module.method`: phương thức được gọi.
- `module.invocation-type`: lời gọi Spring bean hoặc event listener.

Một backend quan sát trace (ví dụ collector OTLP và hệ thống hiển thị trace, hoặc Zipkin) **không được tạo ra chỉ bằng cách thêm Modulith Insight**. Bạn cần dependency Micrometer Tracing, tracer/exporter, cấu hình endpoint exporter và đường mạng đến collector theo phiên bản Spring Boot. Khi chỉ có metric mà không có trace, hãy kiểm tra **tracing bridge/exporter** và sampling trước khi nghi ngờ module graph.

Luồng quan sát điển hình:

~~~mermaid
sequenceDiagram
    participant C as API client
    participant O as orders module
    participant E as Domain event
    participant I as inventory listener
    participant T as Trace collector
    C->>O: POST order (trace context)
    O->>O: Tạo đơn
    O->>E: Publish OrderPlaced
    E-->>I: Delivery (có thể bất đồng bộ)
    I->>I: Cập nhật tồn kho
    O-->>C: Phản hồi
    O-->>T: Export span(s)
    I-->>T: Export span(s)
~~~

Đây là sơ đồ nghiệp vụ mẫu; thời điểm xử lý event và mối quan hệ cha/con của span phụ thuộc cấu hình executor, giao dịch, sampling và truyền trace context.

### 7.2. Kiểm tra qua ranh giới bất đồng bộ

Trong luồng đồng bộ cùng thread, thông tin observation/trace thường có sẵn trong `ThreadLocal`. Với `@Async`, custom executor, message broker hoặc Reactor, context có thể bị mất nếu không có cơ chế propagation phù hợp. Khi đó hai span riêng biệt vẫn có thể xuất hiện nhưng không còn liên kết qua cùng trace, dẫn đến chẩn đoán sai là “module không nhận event”.

Checklist kiểm chứng:

1. Gửi một request thử nghiệm có thể tìm lại bằng **correlation ID không chứa dữ liệu cá nhân**.
2. Xác nhận span ở module gọi và module nhận có thuộc trace mong đợi hay không; kiểm tra parent/child hoặc span links theo cơ chế instrument thực tế.
3. Khi dùng executor tự cấu hình, xem xét **Micrometer Context Propagation** và `ContextPropagatingTaskDecorator`; với executor do Spring Boot tự tạo, kiểm tra tùy chọn propagation có hỗ trợ ở nhánh Boot đang dùng.
4. Khi dùng Reactor, kiểm tra cấu hình context propagation phù hợp; khi gọi qua HTTP, bảo đảm client được tạo từ builder có tracing instrumentation.
5. So sánh log `traceId`/`spanId`, dữ liệu trace trong collector và thời điểm listener hoàn tất; đừng chỉ dựa vào một dòng log.

Ví dụ property **cần đối chiếu với tài liệu Spring Boot của phiên bản đang dùng**:

~~~yaml
# Tùy phiên bản Spring Boot và kiểu execution, các tùy chọn này có thể hữu ích.
spring:
  reactor:
    context-propagation: auto
  task:
    execution:
      propagate-context: true
~~~

Hai property trên mô tả hướng cấu hình cho các nhánh Spring Boot hỗ trợ chúng; **không áp dụng máy móc** nếu project dùng task executor tự định nghĩa hoặc phiên bản Boot không nhận property. Khi tự cung cấp executor, hãy đăng ký task decorator theo API Spring Framework tương thích và thử nghiệm thread hop thực tế.

### 7.3. Tiêu chí trace đạt

Với sampling 100% tại môi trường smoke test, request thành công tạo span ở điểm vào, module API được instrument và event listener có hoạt động như thiết kế. Trên UI collector, quan sát module tags và quan hệ span. Nếu listener chạy sau commit/bất đồng bộ, phải tính đến độ trễ xử lý/xuất dữ liệu; không kết luận lỗi chỉ vì trace chưa xuất hiện ngay khi API trả về.

Trace không phản ánh đầy đủ mọi câu lệnh gọi nội bộ cùng module, và không chứng minh hợp đồng kiến trúc là đúng. Đối chiếu trace với graph cùng kết quả `verify()` mới đủ cơ sở đánh giá hành vi theo ranh giới module.

## 8. Smoke test có thể lặp lại sau khi đóng gói

Tạo một tập kiểm tra nhỏ, chỉ chạy trên môi trường kiểm thử có backend phụ thuộc phù hợp. Không dùng dữ liệu đơn hàng thật hay secret trong fixture.

~~~text
Input:
  artifact: shop.jar (đã ghi checksum)
  profile: staging
  external config: ./deploy/config/application-staging.yaml
  application port: 18080
  management port: 19090

Gate 1 - Bootstrap:
  - Tiến trình khởi động thành công với đúng artifact/profile.
  - Không có lỗi binding, thiếu bean, missing dependency, failed exporter nghiêm trọng.

Gate 2 - Configuration:
  - Đúng nơi đọc external config; override cổng/exposure như mong đợi.
  - Các endpoint quản trị chỉ có thể truy cập qua mạng/identity cho phép.

Gate 3 - Module graph:
  - /actuator/modulith có response hợp lệ.
  - Module names/packages/dependencies khớp baseline đã duyệt.

Gate 4 - Observability:
  - Gọi nghiệp vụ phát 1 domain event thử nghiệm.
  - Counter module.events.published có dữ liệu phù hợp.
  - Trace đi qua module API và listener theo kỳ vọng; có module tags.

Gate 5 - Hồi quy và phát hành:
  - Kiểm thử đơn hàng và listener thành công.
  - Có log/metric/trace đủ để tra cứu, không lộ secrets.
  - Lưu kết quả gate cùng version/config fingerprint của bản phát hành.
~~~

### Ma trận chẩn đoán nhanh

| Triệu chứng sau khi đóng gói | Nguyên nhân có khả năng | Bước kiểm tra ưu tiên |
| --- | --- | --- |
| Chạy IDE được, `java -jar` không khởi động | Sai profile, secret thiếu, datasource/broker không có, file config ngoài không được nạp. | Startup log, active profile, working directory, config locations và dependency runtime. |
| `/actuator/health` trả lời, `/actuator/modulith` = 404 | Chưa có `spring-modulith-actuator`/Insight, chưa expose, endpoint không available hoặc path/port sai. | Nội dung JAR, endpoint discovery, management port/base path, policy access. |
| `/actuator/modulith` = 401/403 | Security chặn endpoint. | Authentication, role, ingress/proxy và SecurityFilterChain. Không tắt bảo mật để kiểm tra trên môi trường mở. |
| Graph khác diagram ở test | Runtime classpath/package scanning khác; custom detection chỉ có ở test; artifact cũ. | So build metadata, marker artifact, vị trí custom strategy và phiên bản dependency. |
| `/actuator/metrics` chạy nhưng thiếu event counter | Chưa có sự kiện, thiếu observability module/registry, lọc metric. | Phát event thử nghiệm rồi đo lại, kiểm tra registry/runtime deps. |
| Counter tăng nhưng listener không hoàn tất | Listener thất bại, xử lý async chậm, transaction rollback hoặc lỗi event registry. | Log exception, trạng thái event publication, cơ chế retry và nghiệp vụ cuối. |
| Có request log nhưng không thấy trace | Sampling, thiếu tracer/exporter, collector sai địa chỉ hoặc mạng chặn. | Sampling môi trường test, runtime deps, exporter logs và collector. |
| Trace gãy khi qua `@Async` | Thiếu context propagation qua thread hop. | Executor, task decorator, correlation IDs và trace linkage. |
| Metric có nhưng Prometheus không scrape được | Thiếu Prometheus registry, endpoint không expose hoặc firewall/target sai. | `/actuator/prometheus` trên cổng quản trị và cấu hình scrape. |

**Phân biệt mã lỗi HTTP:** 404 có thể là endpoint không tồn tại/không expose hoặc đang gọi sai path; 401/403 là vấn đề quyền; connection refused/timeout thường là cổng, network hoặc tiến trình. Khi Actuator chạy trên cổng riêng, đừng kiểm tra nhầm cổng business API.

## 9. Đóng gói vào container và cấu hình vận hành

Nếu phát hành bằng Docker/Kubernetes, áp dụng cùng nguyên tắc **kiểm tra artifact sau khi build** cho image:

- Xác nhận image chứa đúng JAR và dependency runtime; image digest phải cố định giữa staging và production.
- Kiểm tra `ENTRYPOINT`, `WORKDIR`, biến `SPRING_PROFILES_ACTIVE`, `SPRING_CONFIG_ADDITIONAL_LOCATION`, đường dẫn volume mount và quyền đọc thư mục config.
- Truy vấn Actuator theo cổng và network namespace của container; phân biệt cổng trong container với cổng host/Service.
- Lưu log, metrics, trace về hệ thống thu thập của môi trường; kiểm tra collector endpoint, TLS và policy mạng.
- Với nhiều replica, đối chiếu graph và effective config giữa replica; graph khác nhau cùng phiên bản có thể cho thấy classpath/image hoặc cấu hình không đồng nhất.

Không đưa `env`, `configprops`, `modulith` hay các endpoint chẩn đoán sâu trực tiếp ra Internet. Giới hạn quyền, expose tối thiểu và giữ bí mật trong Secret Manager/volume phù hợp. Một endpoint chạy được tại `localhost` trong container chưa có nghĩa lộ ra ngoài; ngược lại, một Service/Ingress cấu hình sai có thể vô tình public management port.

### Ví dụ cách kiểm tra biến môi trường và command line

~~~bash
# Truyền các thuộc tính sớm qua môi trường của tiến trình.
SPRING_PROFILES_ACTIVE=staging \
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/opt/shop/config/ \
java -jar /opt/shop/shop.jar
~~~

Trong Windows PowerShell, đặt biến môi trường của **tiến trình shell hiện tại** trước khi chạy JAR:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'staging'
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = 'file:C:/shop/config/'
java -jar C:/shop/shop.jar
~~~

Cấu hình ở nguồn ngoài JAR có thể vượt mặc định bên trong JAR; nếu command line đồng thời ghi đè chính thuộc tính đó, command line thường ưu tiên cao hơn. Hãy lưu một “config fingerprint” **không chứa secret**: profile, vị trí config, các feature flags đã duyệt, phiên bản dependency và checksum artifact.

## 10. Bài tập vận dụng

**Tình huống:** Dự án Spring Boot đã generate module canvas ở CI; sau khi deploy `shop.jar` trên staging, API đặt hàng chạy được nhưng `/actuator/modulith` 404 và trace chỉ có span HTTP, không có span thuộc `inventory`.

**Yêu cầu thực hành:**

1. Không đổi code nghiệp vụ ngay. Kiểm tra JAR chứa `spring-modulith-starter-insight` (hoặc các artifact thay thế tương đương) và các dependency trace exporter hay chưa.
2. Xác nhận profile, management port, chính sách expose/access endpoint và đường dẫn actuator. Nếu thiếu dependency, tạo lại artifact, không chỉnh config để “cứu” lớp class chưa được đóng gói.
3. Đối chiếu graph `orders` → `inventory` từ `/actuator/modulith` với tài liệu CI và kết quả `ApplicationModules.verify()`.
4. Gửi một event thử nghiệm, ghi nhận giá trị `module.events.published` trước và sau. Kiểm tra việc xử lý listener, nhất là trường hợp chạy bất đồng bộ.
5. Kiểm tra exporter, collector và context propagation rồi tìm trace có module-entry span. Nếu trace đã có nhưng mất liên kết qua thread, xử lý executor/context thay vì sửa module graph.

**Kết quả đạt:** Cùng JAR đã kiểm thử khởi động với đúng cấu hình staging; graph runtime khớp baseline; event counter tăng sau tác vụ tương ứng; các span mô-đun được thu thập hoặc có giải thích rõ khi ứng dụng không instrument đường gọi đó; Actuator được bảo vệ; bản phát hành có bằng chứng kiểm chứng lưu lại.

## 11. Ghi nhớ

- **Cấu hình đóng gói không đồng nhất với cấu hình có hiệu lực:** profile, nguồn ngoài JAR, OS environment và command line có thể làm kết quả runtime khác IDE.
- **Sinh tài liệu module ở build** và **xem graph từ Actuator ở runtime** là hai phép kiểm tra bổ sung cho nhau. `Documenter` không tự biến các file diagram thành HTTP endpoint.
- **Actuator `modulith`** yêu cầu đúng runtime dependency, endpoint availability/exposure và quyền truy cập; response graph cho thấy mô hình tĩnh.
- **Event metric** cần luồng phát sự kiện; **module-entry spans** cần instrumentation và hệ thống tracing; **trace liên tục** qua async cần truyền context.
- Smoke test nên chạy trên **đúng artifact triển khai**, kiểm tra cả health, effective config, module graph, metrics, traces và quyền truy cập. Coi đây là điều kiện chặn phát hành.

### Tài liệu chính thức để tra cứu

1. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight starter, `/actuator/modulith`, module spans và event metrics.
2. [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): `Documenter`, UML/C4, module canvas.
3. [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()`.
4. [Spring Modulith — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html): các thuộc tính thuộc Modulith theo nhánh phiên bản.
5. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự ưu tiên và vị trí nạp cấu hình.
6. [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): availability, exposure và security.
7. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracer, exporter và sampling.
8. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): truyền observation context trong async/reactive.

Khi dùng phiên bản cụ thể, chọn đường dẫn tài liệu đã khóa đúng nhánh Spring Modulith/Spring Boot đang vận hành: ký hiệu property, starter và tính năng telemetry có thể thay đổi giữa Boot 3.x/4.x và các nhánh Modulith.
