# Mối liên hệ giữa cấu trúc mô-đun, Actuator, metrics và traces

## 1. Từ kiến trúc trên mã nguồn đến hành vi khi chạy

Trong một ứng dụng Spring Boot theo kiến trúc **modular monolith**, các application module cùng chạy trong một tiến trình nhưng có ranh giới chức năng riêng. Spring Modulith hỗ trợ nhận diện, kiểm chứng và sinh tài liệu cho các ranh giới đó. Khi đưa ứng dụng vào vận hành, Spring Modulith còn có thể công bố cấu trúc mô-đun qua Spring Boot Actuator và quan sát những tương tác qua ranh giới bằng Micrometer.

Bài này kết nối bốn góc nhìn thường bị nhầm lẫn:

1. **Module graph** trả lời: *Trong mã nguồn, mô-đun nào phụ thuộc mô-đun nào?*
2. **Actuator `modulith`** trả lời: *Ứng dụng đang chạy công bố cấu trúc mô-đun và các loại quan hệ nào?*
3. **Metrics** trả lời: *Trong một khoảng thời gian, sự kiện hoặc hoạt động được đo đã xuất hiện bao nhiêu lần, có xu hướng gì?*
4. **Traces** trả lời: *Trong một lần xử lý cụ thể, yêu cầu đã đi qua những điểm quan sát nào và mất thời gian ở đâu?*

Đây là những lớp thông tin bổ sung cho nhau. Cấu trúc tĩnh mô tả **quan hệ có thể tồn tại**, còn tín hiệu runtime mô tả **hành vi đã thực sự xảy ra và đã được ghi nhận**. Một cạnh trong graph không chứng minh cạnh ấy được sử dụng trong mọi request; ngược lại, không thấy span không đủ để kết luận hai mô-đun không tương tác.

### Mục tiêu học tập

Sau bài này, bạn có thể đọc một module graph, đối chiếu nó với endpoint `/actuator/modulith`, giải thích ý nghĩa của các event metrics và module-entry spans, đồng thời dùng chúng để điều tra một luồng xử lý đi qua nhiều mô-đun. Bạn cũng sẽ biết điều kiện để có đủ tín hiệu, giới hạn của từng loại dữ liệu và cách tránh suy luận sai.

## 2. Một ví dụ xuyên suốt: đặt hàng và thanh toán

Giả sử ứng dụng có ba mô-đun trong các package con của package gốc `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderService.java             # API của module order
│   ├── OrderCompleted.java           # sự kiện công khai
│   └── internal
│       └── OrderRepositoryAdapter.java
├── payment
│   ├── PaymentService.java           # API của module payment
│   └── internal
│       └── PaymentGatewayAdapter.java
└── notification
    ├── OrderNotificationListener.java
    └── internal
        └── EmailSender.java
~~~

`OrderService` dùng API của `PaymentService` để thu tiền. Khi hoàn thành đơn hàng, `order` phát `OrderCompleted`; `notification` có listener nhận sự kiện ấy để gửi thông báo. Cách tổ chức thực tế còn tùy quy tắc phân ranh giới và API của từng mô-đun; cấu trúc trên chỉ minh họa ý tưởng.

**Đồ thị phụ thuộc tĩnh** được nhìn theo chiều *mô-đun phụ thuộc → mô-đun cung cấp kiểu/API*:

~~~mermaid
flowchart LR
    Order["order"] -->|"dùng PaymentService"| Payment["payment"]
    Notification["notification"] -->|"tham chiếu OrderCompleted"| Order
~~~

**Luồng nghiệp vụ runtime** có thể có chiều khác vì nó mô tả dữ liệu và hành vi:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant O as order
    participant P as payment
    participant E as ApplicationEventPublisher
    participant N as notification
    C->>O: POST /orders
    O->>P: charge(...)
    P-->>O: kết quả thanh toán
    O->>E: publishEvent(OrderCompleted)
    E-->>N: chuyển sự kiện tới listener
    O-->>C: kết quả tạo đơn
    Note over E,N: Listener có thể chạy đồng bộ hoặc bất đồng bộ tùy cấu hình
~~~

Một điểm dễ nhầm: với quan hệ sự kiện, graph phụ thuộc có thể biểu diễn **`notification → order`**, vì mã của listener tham chiếu kiểu `OrderCompleted` do `order` cung cấp, trong khi sơ đồ luồng nghiệp vụ biểu diễn **`order → notification`** theo chiều sự kiện được phát và xử lý. Hai sơ đồ không mâu thuẫn; chúng trả lời hai câu hỏi khác nhau.

## 3. Module graph: bản đồ kiến trúc từ mã nguồn

Spring Modulith nhận diện các application module từ cách tổ chức package và cấu hình module. Theo mô hình mặc định thường gặp, các package trực tiếp dưới package chứa lớp `@SpringBootApplication` là ứng viên mô-đun. Một mô-đun có phần API được phép công bố và phần triển khai nội bộ. Phụ thuộc qua ranh giới có thể xuất hiện dưới dạng tham chiếu kiểu, phụ thuộc Spring bean hoặc listener sự kiện.

### Sinh và kiểm chứng bản đồ

Trong bài test hoặc tác vụ sinh tài liệu, có thể dùng `ApplicationModules` và `Documenter`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModulithDocumentationTests {

    @Test
    void verifyAndDocumentArchitecture() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.verify();
        new Documenter(modules).writeDocumentation();
    }
}
~~~

Ví dụ giả định lớp test nhìn thấy `ShopApplication` và project đã khai báo các module kiểm thử/tài liệu Spring Modulith tương ứng. `verify()` kiểm tra các quy tắc kiến trúc, gồm phụ thuộc vòng, truy cập trái phép vào phần nội bộ của mô-đun và giới hạn phụ thuộc nếu được khai báo. `Documenter` có thể sinh sơ đồ tổng thể, sơ đồ từng module và Module Canvas để giải thích ranh giới, API cũng như quan hệ phụ thuộc.

Nhờ đó, graph là một **hợp đồng kiến trúc có thể kiểm tra bằng mã**. Khi refactor `order`, ta không chỉ xem biểu đồ có đẹp hay không, mà còn có thể để test phát hiện nếu `order` truy cập thẳng vào lớp `payment.internal.PaymentGatewayAdapter`.

Tuy nhiên, graph không cho biết một lời gọi xảy ra bao nhiêu lần, thời gian thực thi là bao lâu, hay listener có xử lý thành công một sự kiện cụ thể hay không. Đó là phần của observability.

## 4. Actuator: công bố bản đồ mô-đun từ tiến trình đang chạy

Spring Modulith cung cấp endpoint Actuator có ID **`modulith`**. Khi bật hỗ trợ và cho phép HTTP exposure, `GET /actuator/modulith` trả về mô tả các mô-đun mà ứng dụng đã phát hiện, cùng các phụ thuộc giữa chúng.

Ví dụ JSON *minh họa* với hai mô-đun:

~~~json
{
  "order": {
    "displayName": "Order",
    "basePackage": "com.example.shop.order",
    "dependencies": [
      {
        "target": "payment",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "payment": {
    "displayName": "Payment",
    "basePackage": "com.example.shop.payment",
    "dependencies": []
  }
}
~~~

Các trường cần nhận biết:

| Trường | Ý nghĩa khi đọc |
| --- | --- |
| Khóa cấp cao như `order`, `payment` | Định danh kỹ thuật của application module. |
| `displayName` | Tên hiển thị cho con người. |
| `basePackage` | Package gốc mà mô-đun được nhận diện. |
| `dependencies[].target` | Mô-đun đích mà mô-đun hiện tại phụ thuộc vào. |
| `dependencies[].types[]` | Loại phụ thuộc: `DEFAULT` (tham chiếu kiểu thông thường), `USES_COMPONENT` (phụ thuộc Spring component), `EVENT_LISTENER` (quan hệ listener sự kiện). |
| `parent`, `nested` nếu có | Quan hệ module cha/con trong mô hình mô-đun lồng nhau. |

**Actuator không phải nhật ký các lời gọi.** Khi endpoint cho thấy `order` phụ thuộc `payment`, điều đó xác nhận quan hệ kiến trúc được nhận diện tại runtime, không chứng minh request vừa rồi đã gọi `PaymentService`. Endpoint này cũng không tự báo tỷ lệ lỗi hoặc độ trễ của `payment`.

Đồng thời, Actuator sử dụng cấu trúc mô-đun được phát hiện theo cấu hình ứng dụng đang chạy. Nếu bạn tùy biến cách phát hiện module chỉ trong nguồn test, thì runtime có thể không nhìn thấy sự tùy biến đó; cần đưa phần cấu hình liên quan vào nguồn production khi muốn Actuator và observability dùng cùng ranh giới.

## 5. Metrics: bức tranh tổng hợp về sự kiện

Spring Modulith tích hợp với Micrometer để ghi nhận các sự kiện domain được phát trong ứng dụng. Tài liệu Spring Modulith mô tả hai họ counter:

- **`module.events.published`**: counter tổng hợp các lần phát domain event, kèm thông tin mô-đun và kiểu sự kiện.
- **`module.events.published.$moduleIdentifier.$simpleEventTypeName`**: counter riêng cho kiểu sự kiện của mô-đun tương ứng; có thể được bổ sung tag mang ý nghĩa nghiệp vụ thông qua API tùy biến.

Các tag thông dụng của counter tổng hợp gồm `module.identifier`, `module.name` và `module.event.type`. Trong dashboard, chúng giúp phân biệt chẳng hạn sự kiện từ `order` so với sự kiện từ một mô-đun khác.

Giả sử trong 5 phút, mô-đun `order` phát 300 sự kiện `OrderCompleted`; metrics có thể giúp trả lời *tần suất phát sự kiện có tăng bất thường không?*. Tuy nhiên, **300 lần phát không có nghĩa là 300 thông báo email đã gửi thành công**. Counter phát sự kiện không tự đo số listener hoàn tất, số bản ghi được commit, thời gian xử lý hoặc tính duy nhất về mặt nghiệp vụ. Muốn theo dõi chúng cần bổ sung tín hiệu riêng hoặc dùng cơ chế ghi nhận và theo dõi xử lý sự kiện thích hợp.

### Metrics khác với traces ra sao?

Metrics gom nhiều lần xử lý thành chuỗi số liệu để quan sát xu hướng; traces giữ cấu trúc của **một lần thực thi cụ thể**. Nếu tỷ lệ lỗi thanh toán tăng, metrics là nơi phát hiện xu hướng; traces hữu ích để điều tra yêu cầu cụ thể đã chậm ở bước nào. Một counter sự kiện riêng lẻ cũng không thay thế được span đo độ trễ của API mô-đun.

Khi dùng `/actuator/metrics`, hãy truy vấn tên meter trong Micrometer, chẳng hạn:

~~~http
GET /actuator/metrics/module.events.published
GET /actuator/metrics/module.events.published?tag=module.identifier:order
~~~

Endpoint metrics phải được expose và meter chỉ xuất hiện khi được đăng ký hoặc đã có hoạt động liên quan. Với Prometheus, tên meter có thể được chuyển theo quy tắc đặt tên của registry, nên không nên suy ra tên chuỗi Prometheus chỉ từ tên Micrometer.

## 6. Traces: hành trình của một request qua ranh giới module

Khi kích hoạt observability của Spring Modulith, các Spring component thuộc API mô-đun có thể được gắn bộ chặn để tạo Micrometer Observation/span tại **điểm đi vào mô-đun**. Tín hiệu này giúp thấy các chặng của một lần thực thi thay vì chỉ nhìn tổng lượt phát sự kiện.

Một span module-entry có thể mang các thuộc tính:

| Thuộc tính | Diễn giải |
| --- | --- |
| `module.identifier` | Định danh mô-đun nhận lời gọi. |
| `module.name` | Tên mô-đun. |
| `module.method` | Phương thức được gọi qua điểm quan sát. |
| `module.invocation-type` | Kiểu đi vào mô-đun, ví dụ `bean` hoặc `event listener`. |

Với `POST /orders`, một trace **có thể** có các chặng tương tự:

~~~text
Trace: POST /orders
└── HTTP server span
    └── module-entry: order / createOrder(...)
        └── module-entry: payment / charge(...)
    ... module-entry: notification / on(OrderCompleted)
        (nếu listener được instrument và ngữ cảnh trace được nối tiếp)
~~~

Tên span, quan hệ cha/con và các chặng thật sự phụ thuộc vào phiên bản, API nào được instrument, kiểu thực thi và tracing backend. Sơ đồ trên dùng để hiểu **mối liên hệ logic**, không khẳng định mọi ứng dụng đều tạo đúng một cây span như vậy.

Khi xem một trace, hãy đối chiếu:

1. **Module** nào xuất hiện: thực sự có lời gọi qua điểm API quan sát được hay không?
2. **Thời lượng** từng span: thời gian tiêu tốn tập trung ở mô-đun nào?
3. **Quan hệ cha/con và thứ tự**: lời gọi đồng bộ có nằm trong cùng trace hay phần xử lý bất đồng bộ đang ở một trace khác?
4. **Lỗi**: có span hoặc log nào báo lỗi không, và lỗi thuộc thao tác nào?

Một span chỉ cho biết vùng thực thi đã được instrument. Nó không tự chứng minh mã nguồn tuân thủ mọi luật ranh giới; kiểm chứng cấu trúc vẫn thuộc về `ApplicationModules.verify()` và việc xem graph.

### Sự kiện bất đồng bộ và context propagation

Với lời gọi đồng bộ qua các Spring bean đã được instrument, ngữ cảnh quan sát đang hoạt động thường có thể được nối tiếp để các span có cùng trace. Nhưng khi listener chuyển sang thread khác, executor khác hoặc qua hệ thống messaging, **trace context cần được truyền phù hợp với cơ chế thực thi**. Nếu thiếu context propagation, span của listener có thể xuất hiện như một trace độc lập hoặc không được ghi nhận như mong đợi.

Vì vậy, *không thấy listener dưới cùng một trace* chưa đủ để nói listener không chạy. Hãy kiểm tra đồng thời counter phát sự kiện, cấu hình listener/executor, việc truyền context và log có correlation ID. Không giả định rằng chỉ thêm Spring Modulith observability là tất cả các ranh giới bất đồng bộ tự động nối trace trong mọi cấu hình.

## 7. Bật observability trong ứng dụng Spring Boot

### 7.1. Chọn dependency phù hợp

Giải pháp gọn nhất khi muốn **cả endpoint mô-đun và quan sát tương tác** là `spring-modulith-starter-insight`. Starter này đưa vào hỗ trợ Actuator và observability của Spring Modulith cùng phần nền tảng Spring Boot Actuator.

Ví dụ Gradle Kotlin DSL, giả sử project đã quản lý phiên bản tương thích của Spring Boot và Spring Modulith bằng BOM/plugin:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")

    // Chỉ cần khi muốn xuất metrics cho Prometheus.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Với Spring Boot 4.x: ví dụ một starter cho OpenTelemetry/OTLP.
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
}
~~~

**Lưu ý về phiên bản:** cách thêm tracer/exporter phụ thuộc thế hệ Spring Boot đang dùng. Với Spring Boot 3.x, hãy sử dụng các thư viện Micrometer Tracing bridge và exporter tương ứng theo tài liệu của chính phiên bản đó; không chép nguyên cấu hình Boot 4.x vào project Boot 3.x. Nếu chỉ cần bản đồ module tại runtime, có thể dùng `spring-modulith-actuator` cùng `spring-boot-starter-actuator`. Nếu chỉ cần instrument tương tác, có thể dùng `spring-modulith-observability-core` cùng hạ tầng tracing/metrics cần thiết.

Spring Modulith tạo observation và metadata trong ứng dụng, còn hệ thống như Zipkin, Tempo hoặc Jaeger cần **tracer và exporter** phù hợp để nhận span. Có starter insight nhưng chưa cấu hình tracer/backend thì chưa có nghĩa là đã xem được distributed trace ở dashboard.

### 7.2. Expose endpoint cần dùng

Một cấu hình `application.yml` minh họa cho **môi trường phát triển**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0 # debug cục bộ: ghi mẫu toàn bộ trace
~~~

Giá trị `1.0` phù hợp khi thử nghiệm một lượng request nhỏ; ở môi trường nhiều lưu lượng cần chọn tỷ lệ sampling theo chi phí và nhu cầu quan sát. `prometheus` chỉ hữu ích khi có registry tương ứng. Endpoint `modulith` cung cấp thông tin cấu trúc nội bộ, vì vậy nên giới hạn quyền truy cập, chẳng hạn trên management network riêng và qua cơ chế xác thực/phân quyền.

Ví dụ truy vấn sau khi khởi động ứng dụng và phát sinh vài lượt nghiệp vụ:

~~~bash
curl -s http://localhost:8080/actuator/modulith
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/module.events.published
curl -s http://localhost:8080/actuator/prometheus
~~~

Cổng, base path, tình trạng đăng nhập và URL thực tế phụ thuộc cấu hình ứng dụng. Traces thường được xem ở tracing backend, **không** phải bằng `/actuator/modulith`. Nếu endpoint trả 404, hãy kiểm tra dependency, endpoint access và web exposure trước khi kết luận module hoặc metrics không tồn tại.

## 8. Đối chiếu bốn nguồn thông tin khi xử lý sự cố

| Câu hỏi thực tế | Nguồn ưu tiên | Giới hạn khi diễn giải |
| --- | --- | --- |
| `order` có được phép gọi API `payment` không? | Module graph và `ApplicationModules.verify()` | Chỉ kiểm chứng quan hệ trong mã nguồn theo quy tắc đã khai báo. |
| Phiên bản đang chạy nhận diện bao nhiêu module? | `/actuator/modulith` | Ảnh chụp cấu trúc runtime, không phải bản ghi giao dịch. |
| Event `OrderCompleted` được phát nhiều hơn hôm qua không? | `module.events.published` và dashboard metrics | Đo số lần phát, không mặc định đo xử lý thành công. |
| Một request chậm tại `payment` hay `notification`? | Trace có module-entry spans | Chỉ thấy các chặng được instrument, lấy mẫu và truyền context thành công. |
| Thay đổi code có phá ranh giới module không? | Kiểm chứng kiến trúc trong test/CI | Metrics hay traces không thay thế được phép kiểm tra phụ thuộc. |

### Tình huống A: Graph có cạnh nhưng trace không có span

Giả sử `/actuator/modulith` cho thấy `order → payment`, nhưng trace của `POST /orders` không có span `payment`. Một số khả năng hợp lý:

- Luồng request hiện tại không đi qua nhánh thanh toán.
- Quan hệ phụ thuộc được nhận diện từ tham chiếu kiểu hoặc bean nhưng lời gọi cụ thể không đi qua API được instrument.
- Tracing chưa được cấu hình đủ, trace đã bị sampling loại bỏ, hoặc chỉ một phần span được xuất.
- Lời gọi đi qua ranh giới bất đồng bộ nhưng context không được truyền như mong đợi.

Trình tự kiểm tra: xác nhận đường đi nghiệp vụ, xem bean/API có thuộc phạm vi quan sát, kiểm tra tracer và sampling, rồi mới xem cấu hình async/context. **Không xóa cạnh kiến trúc chỉ vì vắng span.**

### Tình huống B: Counter sự kiện tăng nhưng không thấy thông báo

Giả sử `module.events.published` cho `OrderCompleted` tăng, nhưng người dùng không nhận được email. Điều duy nhất counter xác nhận là ứng dụng đã ghi nhận việc **phát** sự kiện; nó không xác nhận listener chạy xong. Cần kiểm tra cấu hình subscription/listener, lỗi gửi email, cách thực thi bất đồng bộ, cơ chế retry/ghi nhận công bố sự kiện và trace hoặc log tương ứng. Nên thêm metric nghiệp vụ riêng như `notifications.sent` và `notifications.failed` nếu cần theo dõi kết quả gửi.

### Tình huống C: Dashboard báo chậm nhưng không xác định được module

Hãy bắt đầu bằng metrics tổng quan để chọn khoảng thời gian và loại request bất thường, sau đó lọc trace tương ứng, đọc các span vào module và đối chiếu với graph. Nếu một span `payment` rất dài, kiểm tra lời gọi bên trong (database, HTTP client hoặc gateway) bằng instrumentation phù hợp. Độ dài của span ở biên mô-đun phản ánh **thời gian của vùng thực thi được đo**; nó không mặc nhiên quy mọi nguyên nhân vào chính mã của mô-đun đó.

## 9. Một quy trình kiểm chứng kiến trúc có thể lặp lại

Để đối chiếu thiết kế với vận hành mà không nhầm lẫn giữa cấu trúc và thực thi, có thể dùng quy trình:

1. **Thiết kế:** xác định API công khai, phần internal và chiều phụ thuộc dự kiến giữa `order`, `payment` và `notification`.
2. **Kiểm chứng tĩnh:** dùng `ApplicationModules.verify()` và tài liệu do `Documenter` sinh để phát hiện phụ thuộc vòng hoặc truy cập internal ngoài ý muốn.
3. **Kiểm chứng bản đang chạy:** xem `/actuator/modulith` có nhận đúng các module và loại phụ thuộc dự kiến hay không.
4. **Tạo một tình huống nghiệp vụ có thể tái hiện:** thực hiện yêu cầu đặt hàng thành công, biết trước sự kiện nào cần phát và listener nào cần chạy.
5. **Đọc metrics:** kiểm tra có counter sự kiện tương ứng và đánh giá tần suất, không xem counter như kết quả cuối cùng của listener.
6. **Đọc trace:** tìm các module-entry span, đo độ trễ từng chặng; với xử lý async, kiểm tra trace context và log/metric liên quan nếu span bị tách.
7. **Sửa và xác minh lại:** nếu phát hiện vấn đề, thay đổi ranh giới hoặc cấu hình quan sát phù hợp rồi lặp lại cả phép kiểm tra tĩnh lẫn runtime.

### Tự kiểm tra

**Câu 1.** `/actuator/modulith` cho thấy quan hệ `notification → order`; tại sao sơ đồ nghiệp vụ vẫn có thể vẽ `order → notification`?

**Đáp án:** Actuator biểu diễn chiều phụ thuộc mã nguồn (listener tham chiếu event do `order` cung cấp), còn sơ đồ nghiệp vụ biểu diễn chiều lan truyền sự kiện.

**Câu 2.** Có 100 lần tăng của `module.events.published` cho `OrderCompleted`. Có thể khẳng định đã gửi 100 email không?

**Đáp án:** Không. Đó là số lần phát sự kiện được ghi nhận; cần metric/log/traces riêng để biết listener và hoạt động gửi email có thành công hay không.

**Câu 3.** Cùng một request có span `order` nhưng không có span `payment`. Điều này đủ chứng minh không hề có phụ thuộc giữa hai module?

**Đáp án:** Không. Phụ thuộc tĩnh và hoạt động động khác nhau; instrumentation, sampling, nhánh thực thi và truyền context đều ảnh hưởng khả năng nhìn thấy span.

**Câu 4.** Khi muốn phát hiện một module mới gọi vào class `internal` của module khác, nên ưu tiên công cụ nào?

**Đáp án:** `ApplicationModules.verify()` trong test/CI, phối hợp với module graph; metrics/traces không thay thế phép kiểm chứng cấu trúc.

## 10. Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): application module, API công khai và ranh giới phụ thuộc.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm tra phụ thuộc vòng và truy cập internal.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): starter insight, endpoint `modulith`, module-entry spans và event metrics.
- [Spring Modulith — Documenter API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html): sinh sơ đồ module và Module Canvas.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cấu hình expose và bảo vệ endpoint.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html), [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer, registry, sampling và exporter.

**Ghi nhớ:** Module graph và Actuator cho biết **ranh giới được nhận diện**; metrics cho biết **xu hướng của hoạt động đã đo**; traces giúp điều tra **đường đi của một lần thực thi**. Chỉ khi đọc chúng cùng nhau và hiểu giới hạn của từng nguồn, ta mới có đủ bằng chứng để đánh giá kiến trúc mô-đun trong lúc hệ thống vận hành.
