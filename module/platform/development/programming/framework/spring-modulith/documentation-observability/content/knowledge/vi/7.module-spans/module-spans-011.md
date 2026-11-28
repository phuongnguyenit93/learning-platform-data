# Đọc duration và lỗi trên module span

Trong ứng dụng **Spring Boot** sử dụng **Spring Modulith**, một trace có thể cho thấy request đi vào module `orders`, sau đó gọi module `payments` và cuối cùng phát sự kiện cho `inventory`. Người đọc trace thường nhìn ngay vào hai chi tiết: **duration** (mất bao lâu) và **error** (có lỗi hay không). Nhưng nếu không hiểu điểm bắt đầu/kết thúc của span, quan hệ cha–con và cách lỗi được ghi nhận, rất dễ gán nhầm toàn bộ độ trễ cho một module hoặc kết luận sai rằng một nghiệp vụ đã thành công.

Bài học thuộc chương **Module spans** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Nó đặt việc đọc duration và lỗi trong mục tiêu lớn hơn: dùng **module graph**, **Actuator**, **event metrics**, **tracing** và **context propagation** để đối chiếu ranh giới application module với hành vi thực tế của hệ thống.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

1. Xác định đúng **module entry span** và đọc `module.identifier`, `module.method`, `module.invocation-type`.
2. Tính duration từ start/end timestamp và phân biệt **elapsed time** với **CPU time**.
3. Phân tích span lồng nhau, đặc biệt khác biệt giữa **inclusive duration** và **self time**.
4. Đọc `UNSET`, `ERROR`, `OK`, exception event và các trường hợp ứng dụng xử lý lỗi mà span không báo lỗi.
5. Xác định điểm cần điều tra từ một trace chậm hoặc lỗi, tránh quy kết nguyên nhân khi chỉ có một số span.
6. Phân biệt lỗi đồng bộ của module, lỗi listener bất đồng bộ và lỗi của HTTP server span.
7. Thiết lập một lab Spring Modulith có tracing để đối chiếu số liệu quan sát được với code.

## 2. Module span là gì và nằm ở đâu trong trace?

Trong OpenTelemetry, **span** mô tả một đơn vị công việc có tên, thời điểm bắt đầu/kết thúc, duration, attributes, events, status, trace ID, span ID và thông tin parent. Các span tạo thành một cấu trúc quan hệ nhân quả trong trace, được hiển thị như cây hoặc **waterfall**.

Spring Modulith có cơ chế tạo **module entry span** tại những điểm đi vào API của application module được instrument. Theo tài liệu chính thức, các Spring component thuộc API module được trang trí bằng aspect để chặn lời gọi và tạo Micrometer span. Ví dụ:

~~~text
HTTP POST /orders                         [HTTP server span]
└── orders: placeOrder(...)                [module entry span]
    └── payments: charge(...)              [module entry span]
        └── HTTP POST /payment-gateway     [HTTP client span, nếu được instrument]
~~~

**“Entry” chỉ điểm vào module, không phải gốc của toàn bộ trace.** HTTP server span có thể là parent của module entry span; một module entry span cũng có thể là parent của span đi vào module khác.

### 2.1. Thuộc tính của module entry span

Spring Modulith mô tả các tag sau:

| Span attribute | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| `module.identifier` | Technical ID của application module | `orders` |
| `module.name` | Tên module | `Orders` |
| `module.invocation-type` | Kiểu đi vào module | `bean` hoặc `event listener` |
| `module.method` | Phương thức tại entry point | `placeOrder` |

Các thuộc tính này giúp **xác định đúng span cần đọc**. Không nên dựa hoàn toàn vào tên span hiển thị, vì tên có thể thay đổi theo version hoặc convention của instrumentation.

### 2.2. Các trường quan sát khác không do Modulith định nghĩa riêng

| Trường / thông tin | Vai trò |
| --- | --- |
| `traceId` | Liên kết các span thuộc một trace |
| `spanId` | Định danh một span trong trace |
| `parentSpanId` | Xác định span cha để dựng cây nhân quả |
| Start timestamp / End timestamp | Mốc bắt đầu/kết thúc do công cụ tracing ghi nhận |
| Duration | Khoảng thời gian thực thi của span |
| Span status | `UNSET`, `ERROR` hoặc `OK` theo OpenTelemetry |
| Events | Các sự kiện trong span, có thể bao gồm `exception` |
| Span attributes | Thông tin bổ sung về operation, ví dụ module và một số thông tin HTTP/DB |

Tên hiển thị cụ thể của các trường có thể khác giữa Zipkin, Jaeger và Tempo. Hãy phân biệt **dữ liệu gốc** (status, timestamp, attributes) với cách UI trình bày bằng màu hoặc nhãn riêng.

## 3. Đọc duration: span đo khoảng thời gian nào?

**Duration = EndTimestamp − StartTimestamp.**

Trong OpenTelemetry, thời điểm thường được xuất ở độ chính xác cao (ví dụ nanosecond); công cụ tracing hay quy đổi thành ms hoặc s. Đây là **elapsed/wall-clock time** cho operation được instrument, không mặc định là thời gian CPU của module.

Ví dụ một module entry span:

~~~text
Span: orders.placeOrder
Start: 10:15:20.120
End:   10:15:20.570
Duration: 450 ms
~~~

Kết luận chính xác: **operation mà span `orders.placeOrder` đại diện kéo dài 450 ms** theo đồng hồ đo của instrumentation.

Không thể chỉ từ 450 ms kết luận:

- CPU trong code `orders` chạy 450 ms.
- Database của `orders` chậm.
- Mọi lần `placeOrder` đều mất 450 ms.
- Độ trễ người dùng nhận được chỉ là 450 ms.
- `orders` chắc chắn có lỗi vì duration cao.

Một span có thể bao gồm thời gian chờ mạng, database, lock, module con, transaction, external API và những bước chưa instrument.

### 3.1. Duration của span cha bao gồm thời gian của span con

Giả sử trace của một request có mốc thời gian tương đối tính từ lúc nhận HTTP request:

| Span | Bắt đầu | Kết thúc | Duration |
| --- | ---: | ---: | ---: |
| `HTTP POST /orders` | 0 ms | 600 ms | **600 ms** |
| `orders.placeOrder` | 40 ms | 540 ms | **500 ms** |
| `payments.charge` | 130 ms | 450 ms | **320 ms** |
| `HTTP payment gateway` | 170 ms | 400 ms | **230 ms** |

Waterfall tương đối:

~~~text
Thời gian (ms) 0       100      200      300      400      500      600
                 |--------|--------|--------|--------|--------|--------|
HTTP POST        [=====================================================] 600
orders               [============================================]       500
payments                     [=============================]              320
gateway                          [=====================]                   230
~~~

**Không cộng 600 + 500 + 320 + 230 để tính tổng latency.** Các khoảng thời gian đã nằm lồng nhau. Người dùng chờ khoảng 600 ms trong HTTP request minh họa, không phải 1.650 ms.

Với luồng đồng bộ và thứ tự như bảng, `orders` kéo dài 500 ms **bao gồm** 320 ms của `payments`; `payments` bao gồm 230 ms chờ gateway.

### 3.2. Inclusive duration và self time

- **Inclusive duration:** toàn bộ duration của span, kể cả thời gian nằm trong các span con.
- **Self time / exclusive time (ước tính):** phần thời gian của span mà các **span con trực tiếp đã quan sát** không che phủ, sau khi xét các khoảng thời gian chồng nhau.

Trong ví dụ đơn giản, mỗi parent có đúng **một child đồng bộ nằm trọn trong parent**:

~~~text
Self time ước tính của orders = 500 ms - 320 ms = 180 ms
Self time ước tính của payments = 320 ms - 230 ms = 90 ms
~~~

Hai con số này **không phải đo CPU time**. Chúng còn có thể bao gồm chờ lock, serialization, thao tác DB chưa instrument, xử lý logic, thời gian chờ I/O không có span riêng và overhead của instrumentation.

Nếu một parent có nhiều child **chạy chồng nhau**, không thể lấy tổng duration của các child để trừ. Phải xét **hợp (union) của các khoảng thời gian con giao với parent**. Nếu có child không được ghi nhận, self time sẽ bị tính cao hơn thực tế.

Ví dụ, parent dài 500 ms, hai child đều dài 300 ms nhưng chồng nhau 200 ms:

~~~text
Độ phủ hợp của hai child = 300 + 300 - 200 = 400 ms
Self time ước tính của parent = 500 - 400 = 100 ms
~~~

Nếu trừ máy móc `500 - (300 + 300)` sẽ ra **−100 ms**, là dấu hiệu cách tính sai.

### 3.3. Khi child kéo dài hơn parent

OpenTelemetry cho phép một span con tiếp tục chạy sau khi span cha đã kết thúc, nhất là với công việc bất đồng bộ. Vì vậy không nên giả định mọi child nằm trọn trong thời gian parent.

~~~text
orders.placeOrder      [-----------]                     (200 ms)
inventory.listener        [----------------------------]   (450 ms)
~~~

Nếu listener làm việc sau khi request trả về, **450 ms của listener không được cộng vào thời gian chờ HTTP**. Nếu muốn phân tích end-to-end của một nghiệp vụ kéo dài qua sự kiện, cần xác định rõ **điểm bắt đầu/kết thúc của workflow**, các trace/links và quy ước đo khác với latency của một request.

## 4. Đọc lỗi: span status khác business outcome

OpenTelemetry định nghĩa ba giá trị status cho span:

| Status | Ý nghĩa | Cách diễn giải thận trọng |
| --- | --- | --- |
| `UNSET` | Mặc định; instrumentation chưa đặt trạng thái cụ thể | **Không đồng nghĩa đã xác nhận thành công** |
| `ERROR` | Operation được đánh dấu có lỗi | Cần xem exception/event/attributes và context để hiểu nguyên nhân |
| `OK` | Operation được xác nhận hoàn tất thành công theo quy ước của người instrument | Không đồng nghĩa toàn bộ nghiệp vụ hoặc các module khác đều thành công |

Nhiều thư viện instrumentation để status ở `UNSET` khi không phát hiện lỗi; đó là hành vi bình thường theo OpenTelemetry. Đừng xem mọi span màu trung tính là `OK` nếu backend không ghi nhận giá trị đó.

**Span status là đánh giá về operation của span**, không phải một bản sao của HTTP status code hay “trạng thái đơn hàng”. Một nghiệp vụ thanh toán bị từ chối có thể là kết quả domain hợp lệ và được biểu diễn bằng response bình thường; ngược lại, một exception không được xử lý có thể khiến operation báo `ERROR`.

### 4.1. Exception event khác span status

Khi instrumentation ghi nhận exception, span có thể chứa một event tên `exception` với các thuộc tính, nếu chính sách và giới hạn xuất dữ liệu cho phép:

- `exception.type`: tên/class của lỗi.
- `exception.message`: thông điệp lỗi, có thể bị lọc hoặc rút gọn.
- `exception.stacktrace`: stack trace, có thể bị giới hạn hoặc không xuất vì chi phí và bảo mật.

Theo quy ước OpenTelemetry, exception **nên được ghi trên span khi nó không được xử lý tại thời điểm span kết thúc và dẫn tới trạng thái ERROR**. Việc gọi API ghi exception **không thay thế** việc đặt status `ERROR` nếu instrumentation cần đánh dấu lỗi; tùy thư viện, bạn có thể thấy event, status hoặc cả hai.

Ví dụ thông tin hiển thị **minh họa**:

~~~text
Span: payments.charge
module.identifier: payments
module.invocation-type: bean
duration: 120 ms
status: ERROR
event: exception
  exception.type: java.lang.IllegalStateException
  exception.message: Payment provider unavailable
~~~

Đây là biểu diễn đọc hiểu, **không phải JSON khẳng định backend nào cũng trả chính xác những trường và cách đặt tên này**.

### 4.2. Lỗi HTTP và lỗi module có thể khác nhau

Giả sử `OrderService.placeOrder()` gọi `PaymentService.charge()`; `PaymentService` ném exception. Có một số kết quả có thể xảy ra:

1. Exception **thoát ra khỏi `PaymentService`**: module entry span của `payments` có cơ hội được đánh dấu lỗi bởi instrumentation.
2. `OrderService` **bắt lỗi và chuyển thành trạng thái đơn hàng `PAYMENT_FAILED`**: module entry span `orders` có thể kết thúc bình thường, tùy instrumentation và cách xử lý.
3. Controller trả HTTP **409 Conflict** để báo trạng thái nghiệp vụ: HTTP server span có thể không mang status `ERROR`, theo quy ước của HTTP instrumentation và cách xử lý lỗi.
4. Nếu lỗi không được xử lý và dẫn đến HTTP **500**, HTTP span thường được phân loại lỗi theo HTTP server instrumentation; nhưng không nên suy status của mọi span con nếu chưa xem trace.

Vì thế:

**HTTP status 4xx/5xx ≠ tự động suy ra status của mọi module span.**

Cần đọc riêng từng span và phân biệt *lỗi kỹ thuật*, *điều kiện nghiệp vụ được dự kiến*, *exception đã được catch* và *HTTP response*.

## 5. Cách lỗi xuất hiện trong một cây span

### 5.1. Tình huống A — Lỗi chưa xử lý đi qua nhiều module

~~~text
HTTP POST /orders                    [ERROR, 520 ms]
└── orders.placeOrder               [ERROR hoặc theo instrumentation, 480 ms]
    └── payments.charge             [ERROR, 310 ms]
        └── HTTP payment gateway    [ERROR, 290 ms]
~~~

Đây là một ví dụ mà lỗi có thể **lan ngược** qua lời gọi đồng bộ. Span nhỏ nhất báo lỗi/exception có thể là điểm bắt đầu điều tra hợp lý, nhưng vẫn cần xem thông tin bên trong: gateway trả lỗi thật, timeout do client đặt quá ngắn hay sự cố kết nối?

**Không mặc định “parent của span ERROR chắc chắn cũng ERROR”.** Parent status phụ thuộc việc exception có thoát qua biên instrumentation, có bị bắt và xử lý, cùng quy ước của thư viện.

### 5.2. Tình huống B — Child lỗi nhưng parent xử lý được

~~~text
HTTP POST /orders                      [UNSET/OK, HTTP 202]
└── orders.placeOrder                 [UNSET/OK]
    └── payments.charge               [ERROR]
~~~

`payments` ném lỗi; `orders` bắt exception, tạo đơn ở trạng thái chờ thanh toán, trả response được chấp nhận. Đây có thể là nghiệp vụ hợp lệ nếu được thiết kế như vậy. Khi đó **không dùng lỗi của child để tuyên bố request cuối cùng thất bại**.

### 5.3. Tình huống C — Lỗi nghiệp vụ dự kiến, không có `ERROR`

Ví dụ cổng thanh toán trả kết quả `DECLINED` một cách bình thường; ứng dụng ghi trạng thái từ chối vào domain model và kết thúc method mà không ném exception. Span `payments` có thể không báo lỗi. Điều này không phải tracing hỏng: operation kỹ thuật có thể thành công khi **kết quả nghiệp vụ không được chấp nhận**.

Muốn đo tỷ lệ từ chối thanh toán, cần **business metric** hoặc structured log riêng, chẳng hạn counter với nhãn outcome có tập giá trị hữu hạn. Không dùng `span.status=ERROR` như thước đo chính xác cho mọi thất bại nghiệp vụ.

### 5.4. Tình huống D — Listener bất đồng bộ lỗi sau khi HTTP đã xong

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant O as orders
    participant E as Event publication
    participant I as inventory listener
    C->>O: POST /orders
    O->>E: publish OrderPlaced
    O-->>C: HTTP 201
    E-->>I: process OrderPlaced (async)
    I--xI: IllegalStateException
    Note over I: Listener span có thể ERROR<br/>trên nhánh hoặc trace khác
~~~

HTTP 201 nói về kết quả của request **ở thời điểm trả response**. Lỗi listener xảy ra **sau đó** và không nhất thiết làm HTTP server span thành `ERROR`. Quan hệ trace giữa publisher và listener phụ thuộc **context propagation**, executor, transaction và thời điểm xử lý event.

Cần kết hợp **event publication registry, logs và trace của listener** để biết tác vụ bất đồng bộ có được retry/hoàn tất hay không. Counter `module.events.published` chỉ đo công bố event, **không chứng minh listener thành công**.

## 6. Một ví dụ số đầy đủ: tìm đoạn chậm và lỗi

Giả sử trace có các span theo thời gian tương đối:

| Span | Start | End | Duration | Status |
| --- | ---: | ---: | ---: | --- |
| HTTP server `POST /orders` | 0 ms | 960 ms | 960 ms | `ERROR` |
| `orders.placeOrder` | 35 ms | 925 ms | 890 ms | `ERROR` |
| `payments.charge` | 110 ms | 850 ms | 740 ms | `ERROR` |
| HTTP client `POST /charge` | 160 ms | 820 ms | 660 ms | `ERROR` |

Cách phân tích theo thứ tự hợp lý:

1. **Tìm operation kết thúc lỗi:** xác định các span nào `ERROR` và xem exception events/HTTP status cụ thể. Nếu HTTP client timeout, cần xác định timeout ở caller hay lỗi trả từ server đích.
2. **So duration theo cây:** `payments` có 740 ms trong 890 ms của `orders`; HTTP client chiếm 660 ms trong 740 ms của `payments`.
3. **Tính phần ngoài child có ý nghĩa hạn chế:** self time ước tính của `orders` khoảng `890 − 740 = 150 ms`; của `payments` khoảng `740 − 660 = 80 ms`, giả định mỗi parent có đúng một child đồng bộ được instrument và nằm trọn trong interval.
4. **Xác định vùng điều tra tiếp:** 660 ms ở HTTP client là vùng chờ lớn nhất được instrument. Cần thêm status/timeout, logs và trace phía dịch vụ nhận; chỉ từ duration chưa thể khẳng định lỗi mạng hay máy chủ.
5. **Không cộng duration lồng nhau:** tổng thời gian request vẫn là 960 ms, không phải `960 + 890 + 740 + 660`.

Tỷ lệ `740/890 ≈ 83%` cho biết **phần lớn khoảng thời gian của module `orders` chồng lên operation `payments`** trong trace này. Không thể khẳng định `payments` tiêu thụ 83% CPU hoặc là nguyên nhân gốc khi thiếu dữ liệu sâu hơn.

### 6.1. Nếu span dài nhưng không có child nào thì sao?

Một span `inventory.reserve` dài 2 giây mà không thấy HTTP/DB child có thể do:

- Công việc thuần CPU trong module.
- Chờ khóa, scheduler hoặc I/O chưa được instrument.
- Child bị mất do sampling/filter/exporter hoặc backend chỉ hiển thị một phần trace.
- Instrumentation chưa bao phủ thao tác nằm bên trong.
- Dữ liệu span chỉ được tìm theo một truy vấn khiến các span con khác chưa được tải.

**Thiếu child span không phải bằng chứng về CPU bottleneck.** Trước khi tối ưu code, xem thread dump, profiling, SQL timing hoặc instrumentation có mục tiêu.

### 6.2. Một trace không đủ để kết luận xu hướng

Một span `payments.charge` dài 740 ms có thể là outlier. Muốn đánh giá hiệu năng dài hạn, cần nhiều mẫu cùng **module/method**, cùng phiên bản ứng dụng và điều kiện tải, sau đó quan sát phân phối `p50/p95/p99` hoặc metric timer thích hợp.

Trong trace backend, p95 tính trên **các spans đã thu thập và lấy mẫu**; phải hiểu sampling và tính đại diện trước khi coi đó là SLO của mọi request. Metrics chuyên đo latency thường phù hợp hơn để lập dashboard/SLO ở mức tổng hợp.

## 7. Lab: bật tracing để đọc duration và error

Để xem module entry span trên UI, cần **Spring Modulith observability instrumentation** và **tracer/exporter/backend** phù hợp. Ví dụ dưới đây dùng **Spring Boot 4.x với Spring Modulith 2.x tương thích**, giả định dự án đã quản lý phiên bản dependency bằng Spring Boot/Modulith BOM. Với nhánh khác, đối chiếu tài liệu dependency và property theo phiên bản thực tế.

### 7.1. Dependency Gradle minh họa

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Spring Modulith: actuator + observability cho ranh giới module.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // OpenTelemetry tracer / OTLP exporter của Spring Boot 4.x.
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

`spring-modulith-starter-insight` bao gồm support Actuator và Modulith observability. Nếu chỉ cần phần observability ở nhánh Spring Modulith 2.x có API tương ứng, có thể dùng `spring-modulith-observability-core` theo tài liệu chính thức và bổ sung dependency Boot cần thiết.

Không nên thêm hai tracer implementation cùng lúc khi không có yêu cầu cụ thể. Tài liệu Spring Boot còn hướng dẫn lựa chọn Brave + Zipkin; ví dụ chọn OpenTelemetry + OTLP để nhất quán với collector.

### 7.2. Cấu hình `application.yml`

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0

  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces

  endpoints:
    web:
      exposure:
        include: health,info,modulith
~~~

Các lưu ý:

- `probability: 1.0` giúp lab dễ tìm đủ trace; production cần điều chỉnh sampling và giới hạn dữ liệu.
- URL giả định có **OpenTelemetry collector/OTLP HTTP receiver** hoạt động ở `localhost:4318`. Trên Docker, `localhost` phải được hiểu theo **container đang chạy ứng dụng**, nên có thể phải đổi hostname cho đúng network.
- Expose `/actuator/modulith` để đọc cấu trúc module; endpoint này **không phải nơi truy vấn lịch sử spans**. Dùng Tempo, Jaeger, Zipkin hoặc backend tương ứng để xem trace.
- Có sampler 100% vẫn không bảo đảm backend nhận được dữ liệu nếu exporter/collector/network bị lỗi hoặc operation không được instrument.

### 7.3. Ví dụ code có hai module và một đường gây exception

**Module `payments` công khai component ở API package:**

~~~java
// com/example/shop/payments/PaymentService.java
package com.example.shop.payments;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    public void charge(UUID orderId, BigDecimal amount) {
        // Điều kiện lỗi giả lập để học cách đọc trace; không phải
        // quy tắc giao dịch thanh toán hoàn chỉnh.
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount must not be negative");
        }

        // Gọi payment gateway thực tế được lược bỏ.
    }
}
~~~

**Module `orders` gọi component của `payments`:**

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.payments.PaymentService;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public UUID placeOrder(BigDecimal amount) {
        UUID orderId = UUID.randomUUID();
        paymentService.charge(orderId, amount);
        return orderId;
    }
}
~~~

**Controller kích hoạt đường đi trong một HTTP request:**

~~~java
// com/example/shop/web/OrderController.java
package com.example.shop.web;

import com.example.shop.orders.OrderService;
import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/orders")
    public Map<String, String> create(@RequestParam BigDecimal amount) {
        UUID id = orders.placeOrder(amount);
        return Map.of("orderId", id.toString());
    }
}
~~~

Giả định ứng dụng có `ShopApplication` ở `com.example.shop`, các package con được Spring Modulith nhận diện như application module. Ở lab, handler exception và mapping HTTP response có thể khác nhau tùy cấu hình; ví dụ mặc định không có `@ControllerAdvice` để làm rõ đường exception.

Gửi hai request:

~~~bash
# Luồng bình thường, mục tiêu là thấy duration của orders và payments.
curl -i -X POST "http://localhost:8080/orders?amount=125.00"

# Gây exception từ payments; mục tiêu là kiểm tra span status.
curl -i -X POST "http://localhost:8080/orders?amount=-1.00"
~~~

**Điều quan sát cần tìm:**

1. Mở trace của mỗi request trong backend.
2. Tìm các span có `module.identifier=orders` và `module.identifier=payments`.
3. Đọc start/end/duration và quan hệ parent của hai module spans.
4. Ở request âm, xem span `payments` có `ERROR` hoặc exception event hay không; sau đó xem span `orders` và HTTP server span.
5. Ghi lại giá trị **thực tế**, không mặc định status của cả ba span đều giống nhau. Tracing backend, handler và version có thể quyết định cách lỗi được hiển thị.

**Chú ý:** Trong ví dụ này, exception là chủ động để kiểm tra instrumentation, không phải mẫu xử lý validation cho production. Ứng dụng thực tế nên validation đầu vào đúng chỗ, không đưa message nhạy cảm vào exception và phân loại business outcome hợp lý.

### 7.4. Ghi lại kết quả lab

| Trường cần ghi | Request thành công | Request gây exception |
| --- | --- | --- |
| HTTP status | Tự đo | Tự đo |
| Trace ID | Tự đo | Tự đo |
| `orders` duration | Tự đo | Tự đo |
| `orders` span status | Tự đo | Tự đo |
| `payments` duration | Tự đo | Tự đo |
| `payments` span status | Tự đo | Tự đo |
| Exception event có không? | Tự đo | Tự đo |
| Module span parent-child có đúng không? | Tự đo | Tự đo |

So sánh duration **trên cùng cấu hình, cùng nhánh code** và nhiều lượt gọi để tránh kết luận từ một phép đo duy nhất.

## 8. Khi nào nên tạo span tùy chỉnh?

Module entry span được thiết kế để đánh dấu **ranh giới module**; nó không bao phủ từng bước nghiệp vụ nội bộ. Nếu span `orders` dài nhưng không biết phần nào tốn thời gian, có thể thêm **observation có chủ đích** cho một operation đáng quan tâm.

Ví dụ service trong module có một thao tác giữ hàng cần được quan sát:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class StockReservationService {

    private final ObservationRegistry registry;

    StockReservationService(ObservationRegistry registry) {
        this.registry = registry;
    }

    void reserve() {
        Observation observation =
                Observation.start("inventory.reserve-stock", registry);

        try (Observation.Scope scope = observation.openScope()) {
            doReserve();
        } catch (RuntimeException exception) {
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private void doReserve() {
        // Logic nghiệp vụ thực tế.
    }
}
~~~

Nếu Micrometer Tracing được cấu hình và đoạn code chạy dưới context phù hợp, observation này có thể sinh một span chi tiết bên dưới operation hiện tại. Lời gọi `observation.error(...)` ghi lỗi vào observation để handler xử lý; mức độ xuất hiện của exception events/status phụ thuộc tracer bridge, instrumentation convention và exporter.

**Đừng tạo span cho mọi helper method.** Hãy tạo thêm observation khi operation có ý nghĩa phân tích riêng, chẳng hạn gọi payment provider, dự trữ tồn kho hoặc thực hiện batch operation. Tên observation nên ổn định theo loại thao tác, tránh nhúng order ID/user ID vào tên.

### 8.1. Không gán nhãn nhạy cảm

Tránh đưa email, mã truy cập, token, thông tin thẻ thanh toán và dữ liệu cá nhân vào span attributes hoặc exception messages. Dùng `traceId` để liên kết logs và kiểm tra theo chính sách truy cập/retention.

Với metrics, chỉ dùng tag có tập giá trị hữu hạn (low cardinality) như `module.identifier`, `outcome`. Trace attributes có thể chi tiết hơn, nhưng không phải lý do để ghi dữ liệu bí mật.

## 9. Kiểm tra độ tin cậy của số liệu trên waterfall

Một waterfall chỉ có giá trị khi bạn hiểu khả năng thiếu hoặc sai lệch của dữ liệu:

| Hiện tượng | Vì sao ảnh hưởng cách đọc duration/error |
| --- | --- |
| Sampling thấp | Một số trace không được gửi; không đại diện đầy đủ cho mọi request |
| Exporter/collector thất bại | Trace bị thiếu span, thiếu event hoặc không thể tìm thấy |
| Chưa instrument child operation | Parent có duration dài nhưng thiếu phân rã công việc bên trong |
| Mở trace chưa đầy đủ | Có thể thiếu root/parent hoặc span từ service khác |
| Thread async không truyền context | Listener xuất hiện ở trace khác, khó nối kết workflow |
| Khác đồng hồ giữa các process | Timestamp có thể lệch; so sánh thứ tự và thời lượng xuyên host cần thận trọng |
| Backend chỉ hiển thị status bằng màu | Có thể lẫn status chính thức với heuristic của UI |
| Exception được catch bên trong method | Module entry span có thể không thấy exception thoát ra |
| HTTP status được mapping bởi handler | Status HTTP và status module span không nhất thiết trùng |
| App hoạt động nhiều phiên bản | Duration/exception của các version khác nhau không nên gộp như cùng điều kiện |

OpenTelemetry mô tả timestamp được thu theo đồng hồ của tiến trình ghi span; do đó **không lấy chênh lệch timestamp ở hai host làm số liệu nhân quả tuyệt đối nếu hệ thống có clock skew**. Quan hệ parent và links vẫn hữu ích để dựng mối liên hệ, nhưng không thay thế việc xác minh bối cảnh thực tế.

### 9.1. Span thiếu status có thể vẫn có exception không?

Có thể. Backend/instrumentation có thể chỉ ghi một số tín hiệu, đặc biệt khi có code tùy chỉnh, policy ghi lỗi hoặc dữ liệu bị lược. Hãy xem **cả status, events, attributes, logs**. Đừng kết luận không có lỗi vì UI chỉ hiển thị `UNSET`.

Ngược lại, `ERROR` không nhất thiết là toàn bộ giao dịch phải rollback: một child operation có thể lỗi rồi được xử lý bằng retry/fallback. Muốn đánh giá thành công nghiệp vụ cuối cùng, cần outcome ở tầng nghiệp vụ.

### 9.2. Khi nào xem error rate ở metrics thay vì đếm spans `ERROR`?

Nếu mục tiêu là tỷ lệ lỗi trong 24 giờ, **metric counter/timer có label outcome phù hợp** thường hiệu quả hơn. Đếm số span `ERROR` chỉ phản ánh phần đã instrument và được sampling/export, hơn nữa một request lỗi có thể tạo nhiều error spans.

Đặc biệt, metric `module.events.published` do Spring Modulith cung cấp là **event-publication counter**, không phải **module error counter**. Không coi số publish event là số lỗi hay số listener hoàn tất. Nếu cần error rate theo module, thiết kế thêm metric hoặc observation/timer phù hợp, kết hợp logs và trạng thái nghiệp vụ.

## 10. Quy trình đọc một module span chậm hoặc lỗi

Khi dashboard hiển thị một module span bất thường, làm theo thứ tự:

1. **Xác định scope:** span này thuộc `module.identifier` nào, `module.method` gì, kiểu `bean` hay `event listener`? Có cùng trace ID với request muốn điều tra không?
2. **Xem thời gian:** đọc start/end/duration, đơn vị ms/s; so vị trí span trên waterfall với HTTP server span và module spans khác.
3. **Đọc quan hệ cha–con:** tìm child trực tiếp dài nhất và các đoạn chờ nằm trong parent; tránh cộng duration lồng nhau.
4. **Kiểm tra error:** xem `UNSET`/`ERROR`/`OK`, exception event, loại exception, status của HTTP/DB client span nếu có.
5. **Xem code và bối cảnh:** kiểm tra exception có được catch, có fallback/retry, có gọi dịch vụ ngoài, có transaction hoặc listener bất đồng bộ.
6. **Kiểm tra trace completeness:** sampling, exporter, clock skew, context propagation, giới hạn số event/attributes và query của backend.
7. **Đối chiếu dữ liệu độc lập:** logs có trace ID, metric latency/error, event registry, database query timing, module graph và Actuator.
8. **Lặp lại có kiểm soát:** tái hiện trường hợp chậm/lỗi trong lab và so nhiều traces hoặc metric percentile trước khi quyết định tối ưu.

Chỉ sau bước này mới nên gắn nguyên nhân cho một module hoặc một dependency cụ thể.

## 11. Những lỗi suy luận thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Span `orders` dài 800 ms nên CPU của `orders` tốn 800 ms.” | Duration đo elapsed time của operation; có thể chứa chờ I/O và thời gian của module con. |
| “Cộng thời gian các span sẽ ra thời gian request.” | Các span lồng nhau/chồng nhau, nên không cộng trực tiếp. |
| “Parent tự động `ERROR` nếu child `ERROR`.” | Error status phụ thuộc instrumentation và việc exception có bị catch không. |
| “`UNSET` nghĩa là thành công tuyệt đối.” | `UNSET` là trạng thái mặc định, chưa có kết luận tường minh. |
| “Có exception event chắc chắn HTTP trả 500.” | Exception có thể được xử lý hoặc chuyển thành nghiệp vụ/HTTP status khác. |
| “HTTP 200 chứng minh listener async đã thành công.” | Listener có thể xử lý sau response và lỗi ở nhánh/trace khác. |
| “Một child chiếm 90% parent là nguyên nhân gốc.” | Nó là vùng thời gian lớn đã quan sát; cần phân rã sâu hơn và đối chiếu nguyên nhân. |
| “Không có span của DB nghĩa là DB không tham gia.” | Có thể thiếu instrumentation, sampling, exporter hoặc truy vấn trace chưa đầy đủ. |
| “Đếm error spans sẽ ra tỷ lệ request lỗi.” | Một request có thể có nhiều error spans và bị sampling; dùng metric thích hợp. |
| “Module graph mô tả duration và lỗi.” | Graph mô tả cấu trúc/phụ thuộc; trace mô tả các lần thực thi được quan sát. |

## 12. Bài tập thực hành

### Bài 1 — Tính duration và self time

Cho trace có các span đồng bộ nằm trọn trong nhau:

~~~text
HTTP request         0..800 ms
orders               40..750 ms
payments             120..620 ms
payment HTTP client  150..580 ms
~~~

Hãy tính:

1. Duration của từng span.
2. Self time **ước tính** của `orders` và `payments` nếu không có các child khác.
3. Vì sao tổng duration các span không phải latency request?

**Đáp án định hướng:** HTTP 800 ms, orders 710 ms, payments 500 ms, HTTP client 430 ms. Self time ước tính của orders 210 ms; payments 70 ms. Tổng request vẫn 800 ms vì các interval lồng nhau.

### Bài 2 — Hai child chạy song song

Parent span dài 500 ms, child A có interval `50..350 ms`, child B `150..450 ms`. Tính độ phủ hợp của hai child và self time ước tính của parent, giả định parent là `0..500 ms` và dữ liệu đã đủ.

**Đáp án định hướng:** Union A và B là `50..450 ms` = 400 ms; self time ước tính 100 ms. Trừ trực tiếp `300 + 300` là sai.

### Bài 3 — Child lỗi nhưng request thành công

Trace có `payments` mang `ERROR`, `orders` mang `UNSET`, HTTP server trả `202 Accepted`. Hãy đề xuất **ít nhất hai** diễn giải có thể xảy ra và hai nguồn dữ liệu cần xem thêm.

**Gợi ý:** `orders` có thể catch lỗi rồi trả trạng thái chờ xử lý, hoặc lỗi được ghi ở một attempt đã retry thành công. Cần xem structured logs, retry/fallback flow và business status.

### Bài 4 — Listener bất đồng bộ

HTTP `POST /orders` kết thúc 200 ms và trả 201. Sau đó `inventory` chạy 600 ms rồi ném exception. Hãy giải thích:

1. Duration nào đại diện cho thời gian chờ của HTTP client?
2. Vì sao listener có thể ở trace khác?
3. Nên nhìn vào đâu để xác nhận listener đã retry hoặc chưa hoàn tất?

**Gợi ý:** HTTP latency là 200 ms; trace context cần propagation qua async; event publication registry/logs và listener trace cho biết trạng thái xử lý.

### Bài 5 — Điều tra module chậm

Trong lab, tạo hai lần gọi `orders → payments`, một lần bình thường và một lần `payments` ném exception. Từ tracing backend, ghi lại duration, status, exception events, parent span ID và HTTP status. Viết một đoạn giải thích tại sao status của module span có thể khác HTTP span khi thêm `@ExceptionHandler`.

### Bài 6 — Chọn công cụ đúng

Đặt câu hỏi và chọn nguồn quan sát:

| Câu hỏi | Nguồn phù hợp |
| --- | --- |
| Module nào phụ thuộc module nào? | Module graph / `/actuator/modulith` |
| Một lần gọi cụ thể chậm ở bước nào? | Tracing/module spans |
| Trung vị và p95 latency của request tăng bao nhiêu? | Metric latency distribution (hoặc trace analytics có hiểu sampling) |
| `OrderPlaced` được publish bao nhiêu lần? | Modulith event publication metrics |
| Listener async đã hoàn tất hay đang retry? | Event publication registry, logs, listener spans |
| Lỗi exception cụ thể xảy ra ở đâu trong request? | Error span + exception event + log correlation |

## 13. Câu hỏi tự kiểm tra

1. `duration` của một module span đo CPU time hay elapsed time?
2. Một span con dài 300 ms nằm trong parent dài 500 ms. Có được cộng thành 800 ms không?
3. Khi nào có thể ước tính self time bằng duration parent trừ duration child?
4. Vì sao không được trừ tổng duration của hai child chạy song song?
5. `UNSET` khác `OK` như thế nào?
6. Exception event và span status `ERROR` có phải cùng một trường không?
7. Vì sao child `ERROR` không bảo đảm parent `ERROR`?
8. HTTP 201 có chứng minh listener bất đồng bộ đã thành công không?
9. Vì sao không thấy database span chưa đủ kết luận không có database call?
10. Cần kết hợp module span với metric nào để đánh giá latency dài hạn?
11. `module.invocation-type` giúp phân biệt hai kiểu entry nào?
12. Tại sao cần kiểm tra context propagation khi tìm span của event listener?

## 14. Ghi nhớ

**Duration của module span là thời gian đã trôi qua trong operation tại ranh giới module**, có thể bao gồm các lời gọi con và thời gian chờ. Đọc duration theo **waterfall và quan hệ parent–child**, không cộng mù quáng các khoảng lồng nhau hoặc đồng nhất elapsed time với CPU time.

**Status của span mô tả lỗi của operation được instrument**, không tự thay thế HTTP status hay kết quả nghiệp vụ. `UNSET` không bảo đảm thành công; `ERROR` cần được giải thích cùng exception event, logs, retry/fallback và vị trí của span trong trace.

Trong Spring Modulith, module graph và Actuator cho biết **cấu trúc và dependency**, event metrics cho biết **publication**, còn module spans cho biết **một lần đi vào ranh giới module đã diễn ra thế nào**. Kết hợp các nguồn này, đặc biệt khi có async/context propagation, mới đưa ra được kết luận vận hành có căn cứ.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observing Application Modules và Module Entry Span](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Boot — Tracing: Micrometer Tracing, OpenTelemetry, sampling, correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Observability và context propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [OpenTelemetry — Trace API: time, span status, exception recording](https://opentelemetry.io/docs/specs/otel/trace/api/).
- [OpenTelemetry — Trace Data Model: duration, parent-child, partial traces, clock skew](https://opentelemetry.io/docs/specs/otel/trace/data-model/).
- [OpenTelemetry — Exceptions: event và attributes](https://opentelemetry.io/docs/specs/otel/trace/exceptions/).
