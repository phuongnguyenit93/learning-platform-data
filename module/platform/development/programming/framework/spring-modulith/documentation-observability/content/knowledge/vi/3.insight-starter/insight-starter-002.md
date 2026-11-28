# Thành phần Actuator được kéo theo từ Spring Modulith Insight starter

> **Chương:** Insight starter  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Insight starter đưa những gì vào ứng dụng?

Khi thêm dependency `org.springframework.modulith:spring-modulith-starter-insight`, ứng dụng nhận được **hỗ trợ Actuator riêng của Spring Modulith**, **hạ tầng Actuator chung của Spring Boot** và **hỗ trợ observability ở cấp application module**.

Hai thành phần trực tiếp trả lời câu hỏi của bài học:

- **`spring-modulith-actuator`**: cung cấp endpoint Actuator có ID `modulith`, dùng để công bố **cấu trúc application module** của ứng dụng đang chạy.
- **`spring-boot-starter-actuator`**: cung cấp nền tảng Actuator của Spring Boot, bao gồm hạ tầng auto-configuration, quản lý endpoint, health/info/metrics và cơ chế exposure/access.

Insight starter còn mang theo hạ tầng observability của Spring Modulith, cho phép ghi nhận tương tác module và domain event thông qua Micrometer khi các điều kiện instrument được đáp ứng. **Có dependency trong classpath không đồng nghĩa tất cả endpoint sẽ tự công khai trên HTTP, mọi event đã có metric, hoặc trace đã được gửi đến hệ thống giám sát.**

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chỉ đúng những dependency Actuator và observability được kéo theo bởi Insight starter, bao gồm vai trò và phạm vi của từng thành phần.
2. Phân biệt `Actuator endpoint tồn tại`, `được expose` và `được phép truy cập`.
3. Cấu hình và kiểm tra `/actuator/modulith`, `/actuator/health`, `/actuator/info` và `/actuator/metrics` trong ứng dụng Spring Boot.
4. Nhận diện các năng lực **không tự xuất hiện** chỉ nhờ Insight starter: Prometheus registry, trace exporter, Event Publication Registry bền vững và tài liệu sơ đồ được tạo bằng `Documenter`.
5. Dùng dữ liệu Actuator để đối chiếu module graph của bản triển khai với bằng chứng runtime thích hợp.

## 2. Sơ đồ dependency: phần nào thực sự được kéo theo?

Theo bảng starter POM trong tài liệu Spring Modulith **2.2.0**, các dependency trực tiếp của Insight starter được mô tả như sau:

~~~text
org.springframework.modulith:spring-modulith-starter-insight
│
├── spring-modulith-actuator                 (runtime)
│   └── hỗ trợ endpoint /actuator/modulith
│
├── spring-modulith-observability-api        (compile trong POM của starter)
│   └── API mở rộng các cơ chế observability
│
├── spring-modulith-observability-core       (runtime)
│   └── hạ tầng ghi nhận module invocation và domain event
│
└── org.springframework.boot:spring-boot-starter-actuator (runtime)
    └── nền tảng Actuator/metrics/health của Spring Boot
~~~

**Lưu ý về scope:** Nhãn `compile` và `runtime` ở trên thể hiện **scope của dependency trong POM được công bố của chính starter**. Nếu dự án khai báo starter bằng Gradle `runtimeOnly` hay Maven `<scope>runtime</scope>`, bản thân starter và các dependency bắc cầu sẽ được giải quyết cho **runtime classpath của ứng dụng**; không vì vậy mà mọi API trong starter tự có trên compile classpath của mã ứng dụng.

| Artifact | Vai trò trong bài học | Điều cần nhớ |
|---|---|---|
| `spring-modulith-starter-insight` | Gói tiện lợi kích hoạt các hỗ trợ production-ready | Dùng một dependency để lắp ghép các khả năng liên quan |
| `spring-modulith-actuator` | Định nghĩa endpoint riêng `modulith` | Nội dung trả về là **metadata kiến trúc** |
| `spring-boot-starter-actuator` | Lắp hạ tầng Actuator của Spring Boot | Quyết định cơ chế đăng ký, expose, quản lý và truy cập endpoint |
| `spring-modulith-observability-core` | Hạ tầng instrument tương tác module/event | Dùng cùng Micrometer; không tự là backend lưu trữ trace |
| `spring-modulith-observability-api` | API phục vụ tùy biến observability | Muốn viết mã gọi API tùy biến, phải bảo đảm artifact có trong compile classpath |
| `spring-modulith-runtime` | Hạ tầng mô hình module lúc chạy, được dùng bắc cầu bởi Actuator/observability | Không cần khai báo trực tiếp trong trường hợp dùng starter phù hợp |

Trong **một số dòng phiên bản 1.x**, packaging của observability có thể dùng tên artifact khác, chẳng hạn `spring-modulith-observability`. Vì vậy phải xem **dependency tree của phiên bản dự án thực tế**, không mặc định mọi version đều có chính xác sơ đồ 2.2.0.

### Sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    App["Ứng dụng Spring Boot"] --> Insight["spring-modulith-starter-insight"]
    Insight --> SA["spring-modulith-actuator"]
    Insight --> BA["spring-boot-starter-actuator"]
    Insight --> OC["spring-modulith-observability-core"]
    Insight --> OA["spring-modulith-observability-api"]
    SA --> M["Endpoint modulith: cấu trúc module"]
    BA --> E["Actuator runtime: health, info, metrics, exposure, access"]
    OC --> O["Micrometer: observation, span, event metric"]
    O -. "Cần cấu hình/driver phù hợp" .-> Back["Backend metrics/tracing bên ngoài"]
    E --> H["HTTP /actuator/... nếu được phép và expose"]
    M --> H
~~~

Sơ đồ chỉ mô tả **vai trò và phụ thuộc khái niệm**, không khẳng định mọi endpoint hoặc mọi backend đã sẵn sàng ngay khi thêm starter.

## 3. Những endpoint cần nhận diện

Insight starter tích hợp vào hệ sinh thái Actuator chung, nhưng **không phải endpoint nào bên dưới cũng do Spring Modulith tự định nghĩa**.

| Endpoint mẫu | Thành phần phụ trách | Tác dụng | Có tự công khai qua HTTP? |
|---|---|---|---|
| `/actuator/modulith` | Spring Modulith Actuator | Trả metadata về các application module, base package, quan hệ phụ thuộc | **Không mặc định**; cần được expose, cho phép truy cập và đáp ứng điều kiện khởi tạo |
| `/actuator/health` | Spring Boot Actuator | Thông tin trạng thái health theo các health indicator đang có | Thông thường đây là endpoint duy nhất được expose mặc định qua HTTP |
| `/actuator/info` | Spring Boot Actuator | Thông tin ứng dụng khi có `InfoContributor`/cấu hình phù hợp | Cần expose; nội dung có thể rỗng nếu chưa cung cấp dữ liệu |
| `/actuator/metrics` | Spring Boot Actuator + Micrometer | Liệt kê và xem các meter đã được ghi nhận | Cần expose; không phải nơi lưu toàn bộ trace |
| `/actuator/prometheus` | Spring Boot Actuator + Prometheus registry | Xuất metrics ở định dạng Prometheus scrape | **Không tự có chỉ nhờ Insight starter**; cần `micrometer-registry-prometheus` và expose |
| `/actuator/loggers`, `/actuator/beans`, `/actuator/env`... | Spring Boot Actuator | Quan sát/điều chỉnh thông tin vận hành tùy endpoint | Có điều kiện và quyền truy cập riêng; chỉ mở khi có nhu cầu |

Đường dẫn `/actuator` là **base path mặc định** của HTTP Actuator endpoint. Dự án có thể thay đổi bằng `management.endpoints.web.base-path`, cấu hình management port, context path hoặc policy của hệ thống. Với ứng dụng không có môi trường web phù hợp, không thể suy ra rằng HTTP endpoint đã tồn tại chỉ vì JAR có mặt trong classpath.

**Ba trạng thái cần phân biệt:**

1. **Có thành phần trên classpath:** dependency được resolve ở runtime, giúp auto-configuration có khả năng kích hoạt.
2. **Endpoint được tạo và cho phép:** điều kiện auto-configuration, endpoint access/enablement và cấu hình ứng dụng phù hợp.
3. **Endpoint được expose ra HTTP và gọi được:** web exposure, HTTP server, URL/port đúng và chính sách xác thực/phân quyền chấp nhận request.

Trong các bản Spring Boot hiện hành, chỉ expose `health` qua HTTP theo mặc định; muốn truy cập `modulith` hoặc `metrics` cần cấu hình rõ ràng.

## 4. Cách thêm Insight starter vào dự án

### 4.1. Dự án dùng Gradle

Giả sử dự án Spring Boot hiện hữu đã có ứng dụng web và đã quản lý phiên bản tương thích bằng Spring Boot/Spring Modulith BOM:

~~~groovy
dependencies {
    // Các dependency Spring Boot và ứng dụng nghiệp vụ đã có ở dự án.
    // Thêm khả năng actuator + observability của Spring Modulith:
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Không cần khai báo lặp `spring-modulith-actuator` và `spring-boot-starter-actuator` nếu starter version đang dùng đã kéo chúng theo như tài liệu của dòng 2.2.0. Việc khai báo thêm trực tiếp có thể hợp lệ cho lý do đặc biệt của build, nhưng nên kiểm tra tránh thừa hoặc gây xung đột phiên bản.

### 4.2. Dự án dùng Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ Maven **giả định** dependency management/BOM Spring Modulith đã cấu hình; nếu chưa có thì phải nhập BOM hoặc chỉ định phiên bản tương thích rõ ràng. Không sao chép tùy tiện một version cố định giữa các Spring Boot major version.

### 4.3. Nếu chỉ muốn endpoint cấu trúc module

Khi không cần trọn gói Insight, có thể chọn các dependency chuyên biệt:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Cách này cung cấp **hỗ trợ endpoint kiến trúc cùng nền tảng Actuator**, nhưng **không tự đưa đầy đủ hạ tầng observability Spring Modulith của Insight starter**. Nếu bài toán cần span/metric module ở runtime, hãy thêm thành phần observability tương ứng phiên bản hoặc dùng Insight starter.

### 4.4. Kiểm chứng dependency tree

Đừng chỉ nhìn `build.gradle` hoặc `pom.xml` rồi suy đoán starter đã đưa vào những gì. Với ứng dụng thực tế, kiểm tra **resolved runtime classpath**:

~~~bash
# Gradle; trên Windows dùng gradlew.bat thay ./gradlew
./gradlew dependencies --configuration runtimeClasspath

# Tìm lý do một artifact được chọn và phiên bản đã resolve
./gradlew dependencyInsight \
  --dependency spring-modulith-actuator \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-starter-actuator \
  --configuration runtimeClasspath
~~~

~~~bash
# Maven: xem cây dependency đã giải quyết
mvn dependency:tree

# Hoặc lọc riêng thành phần Actuator
mvn dependency:tree -Dincludes=org.springframework.modulith:spring-modulith-actuator
~~~

**Kết quả mong đợi:** Có starter Insight và các thành phần Actuator liên quan tại runtime với các phiên bản được quản lý nhất quán. Nếu xuất hiện nhiều phiên bản không tương thích, phải điều chỉnh BOM/dependency management theo dòng Spring Boot/Spring Modulith đang dùng.

## 5. Cấu hình Actuator để có thể gọi endpoint

Ví dụ `application.yml` cho môi trường phát triển hoặc kiểm thử có kiểm soát:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
~~~

Cấu hình trên yêu cầu Spring Boot expose bốn endpoint qua HTTP **nếu chúng được đăng ký và được phép truy cập**. Nó không tự thêm Prometheus registry, exporter tracing hoặc backend lưu sự kiện.

Khi chạy ứng dụng Spring Boot web ở cổng mặc định `8080`, có thể thử:

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/modulith
curl -i http://localhost:8080/actuator/metrics
~~~

Đường dẫn thực tế có thể khác khi dự án đổi management port, path, context hoặc có proxy. Nếu cần authentication, bổ sung cơ chế đăng nhập/header phù hợp với môi trường; tuyệt đối không đưa token thật vào tài liệu hoặc log công khai.

### 5.1. Discovery endpoint

Phản hồi `GET /actuator`, khi discovery được bật và người gọi được phép, thường có cấu trúc `_links`. Một phần phản hồi minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "modulith": {
      "href": "http://localhost:8080/actuator/modulith",
      "templated": false
    }
  }
}
~~~

Không thấy liên kết ở discovery **không phải lúc nào cũng có nghĩa dependency vắng mặt**: có thể endpoint bị tắt, chưa expose, không được cấp quyền, hoặc discovery đã bị vô hiệu hóa. Hãy kiểm tra cả cấu hình và quyền truy cập.

### 5.2. Endpoint `modulith` thực sự trả dữ liệu gì?

Ví dụ khi ứng dụng có hai module `order` và `inventory`:

~~~json
{
  "order": {
    "basePackage": "com.example.shop.order",
    "displayName": "Order",
    "dependencies": []
  },
  "inventory": {
    "basePackage": "com.example.shop.inventory",
    "displayName": "Inventory",
    "dependencies": [
      {
        "target": "order",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Dữ liệu trên chỉ là **ví dụ minh họa**. Phản hồi thật phụ thuộc cấu trúc mã nguồn, chiến lược nhận diện module, phiên bản và những module thực sự phát hiện được.

Các trường đáng chú ý:

| Trường JSON | Ý nghĩa |
|---|---|
| `$.{moduleName}` | Tên kỹ thuật của application module, ví dụ `order` |
| `displayName` | Tên hiển thị thân thiện |
| `basePackage` | Package gốc được nhận diện của module |
| `parent`, `nested` | Thông tin phân cấp module nếu có nested module và phiên bản hỗ trợ |
| `dependencies[].target` | Tên module đích mà module hiện tại phụ thuộc |
| `dependencies[].types[]` | Loại quan hệ; ví dụ `DEFAULT`, `USES_COMPONENT` hoặc `EVENT_LISTENER` |

Một chi tiết dễ nhầm: ở ví dụ này **`inventory` có quan hệ phụ thuộc đến `order`** vì nó sử dụng event API từ `order`. Cạnh phụ thuộc cấu trúc không đồng nghĩa hệ thống đã thực thi một event cụ thể; muốn biết event có chạy hay không, cần metric, trace, log hoặc publication state tương ứng.

## 6. Actuator đóng vai trò nào trong quan sát module?

### 6.1. Endpoint kiến trúc `modulith`

`/actuator/modulith` là **bản đồ cấu trúc của ứng dụng đang triển khai**, hữu ích để:

- Xác nhận runtime nhận diện những module nào.
- So sánh dependency thực tế của build hiện hành với tài liệu kiến trúc sinh ra từ `Documenter` trong CI.
- Phân biệt một phụ thuộc kiểu `EVENT_LISTENER` với `USES_COMPONENT` hoặc `DEFAULT`.
- Rà soát lệch phiên bản khi sơ đồ đã sinh ở commit A nhưng ứng dụng đang chạy commit B.

**Giới hạn:** Endpoint không phải API quản trị event publication, không liệt kê toàn bộ request trong quá khứ và không tự xuất PlantUML/C4 diagram. `Documenter` là công cụ chuyên sinh tài liệu kiến trúc, thường dùng ở test/build; endpoint Actuator trả JSON phục vụ kiểm tra mô hình lúc chạy.

### 6.2. Endpoint metrics của Spring Boot

Khi actuator metrics được expose, thử:

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Spring Modulith observability có thể đăng ký metric dạng:

- `module.events.published`: counter tổng hợp cho domain event publication mà instrumentation ghi nhận.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`: counter theo module và loại event.

Sau khi thực thi chức năng thực sự publish event, có thể tìm meter tương ứng hoặc xem:

~~~bash
curl -i http://localhost:8080/actuator/metrics/module.events.published
~~~

Không thấy meter này ngay khi ứng dụng vừa khởi động **không đủ để kết luận cấu hình Insight lỗi**: meter có thể chưa được ghi nhận vì chưa có event thuộc phạm vi instrument. Cũng cần kiểm tra khả năng bật metric, bộ lọc, sự hiện diện của Micrometer registry và phiên bản thư viện.

Điểm cốt lõi: **metric `published` cho biết việc phát event đã được ghi nhận**, không tự đảm bảo event đã được xử lý thành công ở mọi listener.

### 6.3. Span/trace thuộc phần observability, không phải JSON của endpoint modulith

Các span về lời gọi qua ranh giới module được phát sinh nhờ hạ tầng observability nếu instrumentation được áp dụng và tracer/observation được cấu hình thích hợp. Spring Modulith hỗ trợ các thuộc tính span như:

| Key | Ý nghĩa |
|---|---|
| `module.identifier` | Định danh module |
| `module.invocation-type` | Kiểu gọi vào module, chẳng hạn bean invocation hoặc event listener |
| `module.method` | Phương thức được instrument |
| `module.name` | Tên module |

Để xem chúng trong Zipkin, Grafana Tempo hoặc nền tảng tracing tương thích, dự án còn cần tracer/exporter/backend phù hợp. **Insight starter kéo theo Boot Actuator, nhưng không tự triển khai server Zipkin, Prometheus hay Tempo.**

Ví dụ với Spring Boot 4.x có thể dùng starter tracing chuyên dụng tương ứng, như `spring-boot-starter-opentelemetry` cho OTLP hoặc `spring-boot-starter-zipkin` cho Zipkin, theo tài liệu của dòng Boot đang dùng. Với Spring Boot 3.x, cách khai báo tracing bridge/exporter có thể khác. Vì vậy hãy tham khảo trang tracing của **đúng phiên bản Spring Boot** thay vì sao chép một bộ dependency cho mọi dự án.

## 7. Những thứ Insight starter không tự cung cấp

| Thành phần/tính năng | Có tự được giải quyết hoàn chỉnh khi chỉ thêm Insight? | Muốn sử dụng cần làm gì? |
|---|---|---|
| Boot Actuator foundation | Có, thông qua `spring-boot-starter-actuator` | Cấu hình exposure/access cho endpoint cần dùng |
| Endpoint `modulith` | Có hỗ trợ thông qua `spring-modulith-actuator` | Có ứng dụng/mô hình module hợp lệ, cho phép truy cập, expose |
| Meter/observation của module | Có hạ tầng Spring Modulith observability | Có đường thực thi được instrument, metric registry/observation phù hợp |
| `/actuator/prometheus` | **Chưa đầy đủ** | Thêm `io.micrometer:micrometer-registry-prometheus`, cấu hình/export endpoint |
| Trace gửi lên Zipkin/OTLP | **Chưa đầy đủ** | Thêm bridge/tracing starter, exporter, endpoint/collector, sampling |
| Event Publication Registry lưu JDBC/JPA/MongoDB... | **Không mặc định bởi Insight** | Chọn event registry starter/backend, hạ tầng lưu trữ và cấu hình tương ứng |
| PlantUML, Application Module Canvas trong build | **Không do Insight trực tiếp sinh ra** | Dùng `spring-modulith-docs`/`spring-modulith-starter-test` và API `Documenter` |
| Kiểm tra quy tắc dependency của module trong CI | **Không vì endpoint tồn tại mà tự kiểm tra** | Dùng `ApplicationModules.verify()` và các kiểm thử kiến trúc |
| Truyền trace context qua mọi executor/thread | **Không được đảm bảo** | Xác nhận executor, context propagation, cấu hình tracing và kết quả thực nghiệm |

Các dòng trong bảng phân biệt **thư viện hỗ trợ khả năng** với **hệ thống vận hành khả năng đó**. Đây là điểm nền tảng khi dùng Actuator để kiểm chứng kiến trúc trong production.

## 8. Ví dụ thực tế: xác nhận starter và điều tra tích hợp giữa các module

Giả sử nhóm triển khai hệ thống thương mại điện tử:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderService.java
│   └── OrderCompleted.java
└── inventory
    └── InventoryOrderListener.java
~~~

`order` phát `OrderCompleted` khi đơn hàng hoàn tất; `inventory` tiêu thụ event để cập nhật tồn kho. Người vận hành muốn trả lời hai câu hỏi khác nhau:

**Câu hỏi A – Kiến trúc ở bản deploy này có nhận diện quan hệ giữa hai module không?**

Kiểm tra `/actuator/modulith`. Nếu JSON có `inventory.dependencies[].target = "order"` và loại `EVENT_LISTENER`, đó là **bằng chứng về quan hệ module trong mô hình đang chạy**. Có thể so sánh JSON với module graph được tạo trong CI từ đúng revision.

**Câu hỏi B – Đơn hàng số 42 có thực sự làm tồn kho thay đổi không?**

Endpoint `modulith` **không trả lời được**. Cần chạy yêu cầu nghiệp vụ cụ thể và thu thập thêm:

1. Log/trace gắn request hoặc event ID phù hợp.
2. Metric publication với loại event, module và khoảng thời gian phù hợp.
3. Event Publication Registry nếu ứng dụng đã cấu hình backend và listener thuộc phạm vi được theo dõi.
4. Trạng thái dữ liệu tồn kho sau khi listener hoàn thành, kể cả ảnh hưởng retry/idempotency.

Hình dung hai góc nhìn:

~~~mermaid
flowchart LR
    subgraph Structure["Cấu trúc từ /actuator/modulith"]
        I["inventory"] -->|"tham chiếu event/API"| O["order"]
    end
    subgraph Execution["Hành vi khi đơn hàng hoàn tất"]
        P["order.publish(OrderCompleted)"] -->|"sự kiện runtime"| L["inventory.listener"]
        L --> R["Cập nhật tồn kho"]
    end
~~~

**Không so sánh cứng hướng mũi tên** giữa hai sơ đồ: trong cấu trúc, consumer có thể phụ thuộc vào kiểu event thuộc publisher; trong hành vi, event đi từ publisher sang consumer.

### Bài thực hành nhanh

Ở một ứng dụng Spring Boot web mẫu có Spring Modulith Insight starter và module `order`/`inventory`:

1. Kiểm tra trong runtime dependency tree có `spring-modulith-actuator` và `spring-boot-starter-actuator`.
2. Chạy ứng dụng với cấu hình expose `health,info,metrics,modulith`.
3. Gọi `GET /actuator` và xác nhận liên kết `modulith` xuất hiện khi discovery được bật.
4. Gọi `GET /actuator/modulith`; ghi lại các module, `basePackage` và dependency được nhận diện.
5. Thực hiện một thao tác phát event ở môi trường thử nghiệm, rồi xem `/actuator/metrics`; đừng suy ra listener đã thành công chỉ từ counter phát sự kiện.
6. Khi có tracing backend, so sánh span ở luồng event với quan hệ module; nếu thiếu span, kiểm tra sampling, instrumentation và context propagation.

## 9. Xử lý các lỗi cấu hình thường gặp

| Hiện tượng | Giả thuyết cần kiểm tra | Hướng giải quyết |
|---|---|---|
| Chỉ xem được `/actuator/health` | Đây là hành vi exposure mặc định; `modulith` chưa được expose | Thêm `modulith` vào `management.endpoints.web.exposure.include` |
| `/actuator/modulith` trả 404 | Thiếu dependency runtime, endpoint không đăng ký, không expose, sai base path/port hoặc bị giới hạn access | Kiểm tra dependency tree, cấu hình, URL và log startup |
| `/actuator/modulith` trả 401 hoặc 403 | Cơ chế xác thực/phân quyền không chấp nhận request | Dùng thông tin xác thực hợp lệ và cấu hình quyền phù hợp |
| Có `modulith` nhưng danh sách module không như mong đợi | Khác package layout, chiến lược nhận diện hoặc bản build | Đối chiếu source revision, module detection strategy và metadata deployment |
| `/actuator/metrics` có mặt nhưng thiếu event meter | Chưa có event được ghi nhận, instrumentation chưa hoạt động, meter bị lọc | Chạy kịch bản phát event có kiểm soát và kiểm tra cấu hình metrics |
| `/actuator/prometheus` trả 404 | Thiếu Prometheus registry hoặc endpoint chưa được expose | Thêm `micrometer-registry-prometheus` và cấu hình exposure |
| Không thấy trace ở backend | Thiếu tracer/exporter, sampling bỏ qua, backend unreachable hoặc mất context | Kiểm tra từng thành phần tracing và executor |
| Registry không có publication | Chưa có backend registry phù hợp hoặc listener không thuộc phạm vi registry | Cấu hình event registry độc lập; kiểm tra semantic của listener |
| Dữ liệu module khác sơ đồ trong tài liệu | Tài liệu được sinh từ revision khác | Đối chiếu commit ID/build artifact trước khi kết luận kiến trúc thay đổi |

Mã HTTP trong bảng là các **tình huống thường gặp**, không phải chẩn đoán tuyệt đối. Cấu hình security, reverse proxy hoặc routing của hệ thống có thể tạo kết quả khác.

## 10. Lưu ý khi mở Actuator trong hệ thống thực

Một endpoint có thể cung cấp thông tin hữu ích cho người phát triển nhưng cũng làm lộ cấu trúc package, dependency hoặc dữ liệu vận hành. Do đó:

- Chỉ expose những endpoint cần thiết; thường không expose toàn bộ bằng ký tự `*` ở môi trường production.
- Bảo vệ `/actuator/modulith`, `/actuator/metrics` và các endpoint nhạy cảm bằng chính sách truy cập thích hợp của ứng dụng/hạ tầng.
- Cân nhắc cổng management riêng, mạng nội bộ hoặc proxy được kiểm soát; việc đổi cổng không thay cho xác thực.
- Tránh dùng tag metric có độ biến thiên cực lớn như `orderId` hoặc thông tin định danh khách hàng. Với trace/log, áp dụng chính sách bảo vệ dữ liệu hiện hành.
- Gắn version/build ID vào quy trình quan sát để tránh nhầm metadata kiến trúc giữa các lần triển khai.

Bản thân starter chỉ tạo **nền tảng kỹ thuật**. Quyền truy cập, tính sẵn sàng của dữ liệu, lưu trữ observability và tiêu chuẩn an toàn vẫn thuộc cấu hình hệ thống.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Nếu đã khai báo `spring-modulith-starter-insight` trong runtime, có cần khai báo thêm `spring-boot-starter-actuator` chỉ để endpoint `modulith` hoạt động không?

**Đáp án:** Với dependency tree của Spring Modulith 2.2.0, không cần khai báo lại vì starter Insight đã kéo theo Boot Actuator starter. Vẫn phải bảo đảm phiên bản tương thích và cấu hình expose/access.

**Câu 2.** `/actuator/modulith` trả JSON có `inventory → order`. Có thể kết luận listener của `inventory` đã xử lý xong mọi `OrderCompleted` không?

**Đáp án:** Không. Đó là metadata về **dependency cấu trúc**. Cần bằng chứng runtime để xác định event đã phát, listener chạy và kết quả nghiệp vụ.

**Câu 3.** Vì sao ứng dụng có Insight starter nhưng gọi `/actuator/prometheus` vẫn 404?

**Đáp án:** Endpoint Prometheus cần registry phù hợp (thường `micrometer-registry-prometheus`), cấu hình exposure và quyền truy cập. Starter Insight không tự bổ sung toàn bộ stack Prometheus.

**Câu 4.** Vì sao `spring-modulith-observability-api` được ghi `compile` trong POM của starter nhưng mã ứng dụng khai báo Insight bằng `runtimeOnly` không nên mặc định import API đó?

**Đáp án:** Scope trong POM diễn đạt quan hệ dependency **bên trong starter**; `runtimeOnly` tại ứng dụng giới hạn dependency ở runtime classpath của ứng dụng. Nếu cần biên dịch mã gọi API tùy biến, phải khai báo nó trong compile/implementation classpath phù hợp.

**Câu 5.** Thêm Insight starter có tự sinh PlantUML documentation và chạy `verify()` mỗi lần triển khai không?

**Đáp án:** Không. Các công việc này được thực hiện bằng API `Documenter` và kiểm tra kiến trúc trong test/build theo thiết lập dự án.

## 12. Tổng kết

- `spring-modulith-starter-insight` **kéo theo hai thành phần Actuator quan trọng**: `spring-modulith-actuator` và `spring-boot-starter-actuator`. Nó đồng thời mang theo các thành phần observability của Spring Modulith.
- `/actuator/modulith` là **endpoint kiến trúc**: trả metadata về module/dependency của bản chạy, không phải nhật ký tất cả lời gọi.
- Có endpoint trong classpath, endpoint được expose và người dùng có quyền truy cập là **ba điều kiện khác nhau**.
- `/actuator/metrics` là nơi xem các meter được ghi nhận; Prometheus và tracing backend cần tích hợp thêm.
- Để kiểm chứng kiến trúc mô-đun lúc vận hành, kết hợp **module graph/Documenter**, **Actuator**, **metrics/traces** và **kiểm tra kết quả nghiệp vụ** theo cùng build và môi trường.

## Tài liệu tham khảo

1. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Insight starter, `modulith` actuator, observability spans/metrics.
2. [Spring Modulith – Appendix, Starter POMs and Individual JARs](https://docs.spring.io/spring-modulith/reference/appendix.html) — Thành phần dependency được kéo theo; bảng trong bài tham chiếu dòng 2.2.0.
3. [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Danh sách endpoint, exposure, access và security.
4. [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer, `metrics` và registry.
5. [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — Tích hợp tracer, sampling và exporter.

