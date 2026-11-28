# Tránh instrument trùng cùng một điểm vào

> **Chương:** Bật quan sát  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Vấn đề: một lượt chạy nhưng nhiều dấu vết giống nhau

Một ứng dụng Spring Boot sử dụng Spring Modulith có thể ghi nhận tương tác tại **ranh giới application module**. Nếu nhóm phát triển đồng thời thêm `@Observed`, `@NewSpan`, `Observation` thủ công hoặc một aspect tự viết **ngay tại cùng phương thức đã được Spring Modulith quan sát**, một lượt gọi nghiệp vụ có thể xuất hiện nhiều lần trong trace hoặc bị đo nhiều lần.

Ví dụ người dùng gọi API đặt hàng một lần. Log nghiệp vụ xác nhận `CheckoutFacade.placeOrder()` chỉ chạy một lượt, nhưng trace có hai span bao cùng khoảng thời gian của phương thức:

~~~text
HTTP POST /orders
└── module checkout: CheckoutFacade.placeOrder(...)
    └── checkout.place-order: CheckoutFacade.placeOrder(...)
        └── ...
~~~

Span HTTP và span module có thể là **hai lớp quan sát hợp lệ**, vì một cái mô tả HTTP request, cái còn lại mô tả lần đi vào application module. Tuy nhiên, span `checkout.place-order` bọc **chính toàn bộ phương thức** đã có span module thường là dấu hiệu nhóm phát triển đang instrument trùng một trách nhiệm.

Nhầm lẫn này gây ra một số hậu quả:

- Trace trở nên dài, rối và khiến người điều tra đếm nhầm số lần gọi.
- Tổng thời lượng xuất hiện ở nhiều span gần giống nhau; cộng duration của chúng sẽ thổi phồng thời gian thực hiện.
- Metric có thể bị ghi thêm ở hai nơi nếu cả hai cơ chế đều tạo meter; tuy nhiên **không phải mọi span trùng đều làm cùng một counter tăng hai lần**.
- Sampling, dung lượng exporter và chi phí lưu trữ trace có thể tăng.
- Người đọc dễ kết luận có retry hoặc event bị phát lại, dù nghiệp vụ chỉ thực thi một lần.

Mục tiêu là **mỗi điểm vào có một cơ chế chịu trách nhiệm quan sát ranh giới của nó**, đồng thời vẫn giữ các span con mô tả những công đoạn thực sự khác biệt.

### Sau bài học, người học có thể

1. Xác định “điểm vào” và “trùng instrument” theo ranh giới quan sát thực tế.
2. Phân biệt span lồng nhau hợp lệ với hai observation cùng đo một hành vi.
3. Nhận diện những chồng lấn phổ biến giữa Spring Modulith, Spring Boot Actuator, Micrometer, tracing annotations và custom AOP.
4. Thiết kế sơ đồ phân công instrumentation theo tầng HTTP, application module, event listener và nghiệp vụ bên trong.
5. Điều tra một trace bị trùng mà không vô tình loại bỏ retry hoặc lỗi nghiệp vụ thật.
6. Kiểm chứng kết quả sau thay đổi bằng log, trace, metrics và bài kiểm tra kịch bản có kiểm soát.

## 2. Những khái niệm phải hiểu rõ

### 2.1. “Điểm vào” ở đây là gì?

**Điểm vào (entry point)** là chỗ một luồng xử lý đi qua một ranh giới mà đội phát triển muốn quan sát. Tùy tầng, một request có thể có nhiều điểm vào:

| Tầng | Ví dụ điểm vào | Cơ chế quan sát thường gặp |
|---|---|---|
| HTTP server | `POST /orders` do Spring MVC xử lý | HTTP server observation của Spring Boot/Spring Framework |
| Application module | Component API trong `order` được gọi từ ngoài module | Spring Modulith observability đối với module interaction phù hợp |
| Event listener | `inventory` tiếp nhận `OrderCompleted` | Spring Modulith observability với listener nằm trong phạm vi instrument |
| Công đoạn nghiệp vụ con | Kiểm tra giá, xét hạn mức, tính phí riêng biệt | `Observation` thủ công hoặc `@Observed` được cấu hình đúng |
| HTTP client/DB call | Gọi payment service, JDBC query | Instrumentation của client/driver/framework phù hợp |

Một luồng có thể hợp pháp chứa **nhiều observation cho các tầng và công đoạn khác nhau**. Không có quy tắc “một request chỉ được có một span”.

### 2.2. Instrumentation, observation, span, metric

- **Instrumentation:** mã hoặc cơ chế framework bắt đầu/kết thúc phép đo tại một điểm thực thi.
- **Observation:** abstraction của Micrometer bao lấy quá trình thực thi, có tên, context và key-value.
- **Span:** bản ghi một đoạn thực thi trong distributed tracing, có thể được tạo ra từ một observation nếu tracing handler được cấu hình.
- **Meter/metric:** số liệu đo lường tổng hợp, có thể cùng được tạo từ observation thông qua handler metrics.
- **Exporter/backend:** nơi nhận và hiển thị dữ liệu; exporter không phải nguồn gốc tạo observation tại phương thức.

Vì thế **hai instrumentation trên cùng phương thức** có thể sinh hai observation. Trong môi trường có tracing, chúng có thể tạo hai span; với metrics phù hợp, chúng có thể tạo hai phép ghi nhận. Số lượng dấu vết thực tế phụ thuộc ObservationRegistry, các handler và cấu hình tương ứng.

### 2.3. Phân biệt duplicate và nested span hợp lệ

~~~mermaid
flowchart TB
    subgraph Good["Hợp lệ: mỗi tầng một trách nhiệm"]
      A["HTTP server span"] --> B["order module entry span"]
      B --> C["validate-credit business span"]
      B --> D["HTTP client span"]
    end
    subgraph Duplicate["Nghi ngờ trùng: hai nguồn cùng đo một đoạn"]
      X["HTTP server span"] --> Y["order module entry span"]
      Y --> Z["@Observed: order module entry span lần hai"]
    end
~~~

**Đánh giá theo ngữ nghĩa**, không chỉ theo số lượng:

- `HTTP POST /orders` và `order module entry` có thể gần như cùng duration nhưng đại diện **hai ranh giới khác nhau**.
- `order module entry` và `credit-check` lồng nhau là hợp lý vì `credit-check` là công đoạn cụ thể bên trong.
- Hai span cùng đo `OrderFacade.placeOrder()` từ lúc vào đến lúc ra, chỉ khác tên do hai thư viện gắn vào, là **ứng viên trùng instrument**.
- Hai span tương tự có thời điểm không trùng nhau có thể là hai **lần gọi thực** do retry, re-entry hoặc request thứ hai. Cần điều tra trước khi xóa.

## 3. Spring Modulith quan sát những điểm nào?

Spring Modulith có hỗ trợ observability cho tương tác giữa các application module; tùy phiên bản, cấu hình và mô hình module, nó có thể ghi nhận invocation trên các Spring component thuộc **API được công bố của module** và các **event listener** phù hợp.

Các observation/span liên quan đến module có thể mang thuộc tính như:

| Thuộc tính | Câu hỏi giúp trả lời |
|---|---|
| `module.identifier` | Đây là application module nào? |
| `module.name` | Module được hiển thị dưới tên gì? |
| `module.invocation-type` | Phép gọi được nhận diện thuộc loại bean invocation hay event listener? |
| `module.method` | Phương thức nào là điểm instrument? |

**Giới hạn quan trọng:** Không phải mọi phương thức nội bộ, mọi lời gọi Java hay mọi listener đều tự động được tạo span. Cơ chế nhận diện module, Spring bean/proxy, khả năng bật observability, cấu hình ObservationRegistry và phiên bản Spring Modulith quyết định điểm nào thực sự được instrument.

Spring Boot Actuator và Micrometer cung cấp hạ tầng thu thập/quan sát. Với starter Insight của Spring Modulith, các thành phần Modulith Actuator và observability được đưa vào theo dependency của dòng phiên bản tương ứng. Nhưng muốn có trace thực sự trong Zipkin, Tempo hoặc một collector khác, dự án còn phải cấu hình tracer, exporter và backend phù hợp.

**Thứ tự kiểm tra:** xác nhận có span module tự động **trước** khi quyết định thêm annotation hoặc tạo `Observation` thủ công trên cùng điểm vào.

## 4. Những nguồn tạo trùng thường gặp

| Nguồn thứ nhất | Nguồn thứ hai | Rủi ro/chẩn đoán |
|---|---|---|
| Spring Modulith quan sát public API của module | `@Observed` trên chính API method đó, với `ObservedAspect` đã được bật | Hai observation cùng bao một lần vào module |
| Spring Modulith quan sát public API của module | `Observation.createNotStarted(...).observe(...)` bọc toàn bộ body của method | Hai đoạn đo có cùng phạm vi thực thi |
| Spring Modulith quan sát event listener | `@Observed` hoặc `@NewSpan` có hiệu lực trên cùng listener | Listener có thể có span module và span do annotation |
| Spring Modulith observability | Aspect tùy chỉnh bắt tất cả `@Service`/`@Component` và mở observation cho cả public API module | Một API bean bị hai tầng AOP instrument |
| HTTP server instrumentation của Spring Boot | Custom filter/interceptor mở observation “HTTP server” cho cùng toàn bộ request | Hai HTTP server span/metrics cùng trách nhiệm |
| Micrometer instrumentation của client | Custom wrapper mở observation mang cùng ngữ nghĩa HTTP client call | Đếm/đo trùng network call nếu cùng phạm vi |
| Agent Java tự động | Instrumentation thủ công/trong framework cùng mục tiêu | Có thể xuất hai span tương tự hoặc bị agent suppression tùy phiên bản |

`@Observed` **không tự có hiệu lực chỉ vì annotation có mặt**: phải có cơ chế xử lý annotation tương ứng, ví dụ `ObservedAspect` được cấu hình. Tương tự, `@NewSpan` cần hỗ trợ annotation/tracing của phiên bản Spring Boot/Micrometer đang sử dụng. Nếu cơ chế annotation chưa hoạt động, nó không sinh span và không thể là nguyên nhân gây trùng.

Mỗi nguồn tạo ra span còn có thể có **tên khác nhau**. Việc cùng tên không phải điều kiện bắt buộc của duplication.

### Chống kết luận nhầm

Hai span cùng phương thức chưa chắc do hai instrument nếu:

- Method thực sự bị gọi hai lần trong một request.
- Có retry ở client, framework listener, tác vụ hoặc ứng dụng.
- Bean/proxy gọi lại một API khác cũng sử dụng chung code.
- Một sự kiện có nhiều listener riêng biệt.
- Trace bị ghép sai correlation do context propagation hoặc cách hiển thị backend.
- Hệ thống nhận hai yêu cầu có nội dung giống nhau.

Trước khi xóa annotation, phải đối chiếu **số lần thực thi nghiệp vụ**, **phạm vi và thời điểm của span**, **span ID/parent ID** và **cơ chế nào tạo ra từng observation**.

## 5. Ví dụ: vô tình quan sát hai lần ở một module API

Giả sử application module `checkout` công bố component API `CheckoutFacade` ở base package của module; handler HTTP bên ngoài gọi vào facade này.

### 5.1. Ban đầu: dùng module observability

~~~java
package com.example.shop.checkout;

import org.springframework.stereotype.Service;

@Service
public class CheckoutFacade {

    private final CheckoutWorkflow workflow;

    public CheckoutFacade(CheckoutWorkflow workflow) {
        this.workflow = workflow;
    }

    public void placeOrder(String orderReference) {
        workflow.place(orderReference);
    }
}
~~~

Trong ví dụ, `CheckoutWorkflow` là một thành phần ứng dụng đã có; phần triển khai được lược bỏ. Giả sử Spring Modulith đã instrument `CheckoutFacade.placeOrder()` ở ranh giới module và môi trường đã có tracing phù hợp.

Trace dự kiến:

~~~text
POST /checkout                    [HTTP server]
└── checkout: placeOrder(...)     [Spring Modulith module invocation]
    └── ...
~~~

**Không cần tự mở thêm span đo toàn bộ `placeOrder`** chỉ để biết lần vào module này đã xảy ra.

### 5.2. Thêm annotation nhưng cùng phạm vi

Một thành viên khác thêm `@Observed` để “đảm bảo facade có trace”:

~~~java
package com.example.shop.checkout;

import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class CheckoutFacade {

    private final CheckoutWorkflow workflow;

    public CheckoutFacade(CheckoutWorkflow workflow) {
        this.workflow = workflow;
    }

    @Observed(name = "checkout.place-order")
    public void placeOrder(String orderReference) {
        workflow.place(orderReference);
    }
}
~~~

**Khi `@Observed` đã có aspect xử lý và Spring Modulith cũng đã instrument cùng entry**, trace có thể hiển thị:

~~~text
POST /checkout                    [HTTP server]
└── checkout: placeOrder(...)     [Modulith]
    └── checkout.place-order      [@Observed]
        └── ...
~~~

Đây là ví dụ về **hai scope đo gần như trùng nhau**. Đừng dựa riêng vào tên span để gán nguồn: cần kiểm tra instrumentation scope, annotation và cấu hình aspect.

### 5.3. Một biến thể khác: tự tạo Observation ngay trong facade

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void placeOrder(String orderReference) {
    Observation.createNotStarted("checkout.place-order", observationRegistry)
            .observe(() -> workflow.place(orderReference));
}
~~~

Nếu đây chỉ là wrapper quanh **toàn bộ cùng nghiệp vụ của method** đã được Modulith quan sát, nó tạo thêm một observation gần tương đương. Vì nó được bắt đầu bên trong method, span có thể là span con của span module; **quan hệ parent–child không tự chứng minh nó có ý nghĩa riêng**.

### 5.4. Cách sửa: chỉ instrument một công đoạn bên trong thực sự cần đo

Giữ Spring Modulith chịu trách nhiệm span ở module boundary và đặt observation thủ công cho **một công đoạn nghiệp vụ riêng**, ví dụ kiểm tra hạn mức tín dụng:

~~~java
package com.example.shop.checkout;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutFacade {

    private final CreditPolicy creditPolicy;
    private final CheckoutWorkflow workflow;
    private final ObservationRegistry observations;

    public CheckoutFacade(
            CreditPolicy creditPolicy,
            CheckoutWorkflow workflow,
            ObservationRegistry observations) {
        this.creditPolicy = creditPolicy;
        this.workflow = workflow;
        this.observations = observations;
    }

    public void placeOrder(String orderReference) {
        Observation.createNotStarted("checkout.credit-policy", observations)
                .observe(() -> creditPolicy.validate(orderReference));

        workflow.place(orderReference);
    }
}
~~~

`CreditPolicy` và `CheckoutWorkflow` trong ví dụ là những dependency nghiệp vụ do ứng dụng định nghĩa. Đoạn code minh họa cách đặt instrumentation; để chạy cần triển khai các kiểu và dependency tương ứng.

Lúc này:

~~~text
POST /checkout                         [HTTP]
└── checkout: placeOrder(...)          [Modulith boundary]
    └── checkout.credit-policy         [business sub-step]
~~~

Span con `checkout.credit-policy` có **ý nghĩa khác và phạm vi hẹp hơn** span module. Nếu cơ chế khác đã tự instrument `CreditPolicy.validate(...)`, cần kiểm tra lại để tránh lặp lỗi ở điểm mới.

## 6. Phân quyền sở hữu instrumentation theo tầng

Một quy tắc dễ vận hành là **mỗi ranh giới có một nguồn chịu trách nhiệm chính**:

| Ranh giới cần quan sát | Nguồn chính được khuyến nghị | Khi nào bổ sung thủ công? |
|---|---|---|
| HTTP request vào Spring MVC/WebFlux | Framework/Boot HTTP server observation | Chỉ cho nghiệp vụ con chưa được đo, không bọc lại toàn HTTP request |
| Lời gọi đi vào public API của application module | Spring Modulith module observability, nếu đã hoạt động tại đó | Khi muốn đo công đoạn con có ngữ nghĩa riêng |
| Spring Modulith event listener | Spring Modulith observability, nếu listener đã được instrument | Khi cần phân đoạn xử lý bên trong listener |
| HTTP client đã có Micrometer instrumentation | Instrumentation client/library tương ứng | Khi cần tách công việc chuẩn bị payload/xử lý kết quả, không đo lặp request |
| Thao tác nội bộ thuần nghiệp vụ chưa được đo | `Observation` hoặc `@Observed` do nhóm quản lý | Khi độ trễ, lỗi và context của thao tác thực sự có giá trị |
| Sự kiện công bố theo Modulith | Event metrics của Modulith | Chỉ thêm business metric bổ sung cho ý nghĩa riêng, ví dụ số đơn hợp lệ |

Nguyên tắc này là **quyết định thiết kế thực hành**, không phải khẳng định Spring Modulith luôn bật instrument ở mọi entry. Hãy xem trace/metrics thực tế của version đã triển khai trước khi chọn nơi thêm thủ công.

Ví dụ một hệ thống có controller HTTP gọi `OrderApplicationService.submit()`, rồi service gọi `CreditRules.check()` và gửi REST request đến payment gateway:

~~~mermaid
flowchart TD
    H["HTTP POST /orders\nBoot HTTP span"]
      --> M["order module entry\nSpring Modulith span"]
    M --> B["credit-rule validation\nBusiness observation thủ công"]
    M --> C["payment HTTP call\nHTTP client instrumentation"]
    M --> E["publish OrderCompleted\nSpring Modulith event metric"]
~~~

Mỗi nút thể hiện **một ngữ nghĩa riêng**. Không nên tạo thêm span `order.submit` bằng ba cơ chế khác nhau chỉ vì ba team cùng muốn nhìn thấy lời gọi đó.

## 7. Event listener và xử lý bất đồng bộ: trường hợp dễ nhầm

Giả sử module `inventory` nghe sự kiện `OrderCompleted` từ module `order`:

~~~java
package com.example.shop.inventory.internal;

import com.example.shop.order.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    private final InventoryUpdater updater;

    OrderCompletedListener(InventoryUpdater updater) {
        this.updater = updater;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        updater.apply(event.orderId());
    }
}
~~~

`@ApplicationModuleListener` hỗ trợ kiểu xử lý sự kiện của Spring Modulith, thường bao gồm thực thi bất đồng bộ cùng transactional event listener semantics theo framework/version. Nếu phần observability của Modulith đã ghi được span listener, việc gắn thêm `@Observed` lên **cùng `on(...)`** (và bật aspect) có nguy cơ tạo một tầng quan sát trùng.

### Điểm cần phân biệt trong luồng bất đồng bộ

1. **Listener chạy một lần, có hai span gần cùng phạm vi:** nghi instrumentation chồng lấn.
2. **Listener chạy hai lần:** có thể là retry, publication resubmission, duplicate event hay logic ứng dụng; không xử lý bằng cách xóa span.
3. **Listener chạy nhưng span không thuộc cùng trace:** xem context propagation, executor, sampling, exporter; đây là bài toán liên kết trace, khác với duplicate instrumentation.
4. **Metric publish tăng một lần nhưng listener được gọi nhiều lần:** event publication, nhiều listener và retry có semantics khác nhau; cần log/bằng chứng publication theo từng listener.

**Ví dụ chồng lấn cần xem xét:**

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.modulith.events.ApplicationModuleListener;

@ApplicationModuleListener
@Observed(name = "inventory.order-completed")
void on(OrderCompleted event) {
    updater.apply(event.orderId());
}
~~~

Nếu cả hai cơ chế đều hoạt động ở cùng listener, nên để Modulith giữ **entry span của listener**, và chỉ đặt observation bổ sung cho nghiệp vụ bên trong khi thật sự cần, như `inventory.stock-reconciliation`.

Lưu ý: khả năng instrument event listener, tên span và trạng thái publication phụ thuộc bản Spring Modulith, cấu hình quan sát và cách listener được đăng ký. **Đọc trace từ đúng bản chạy để xác nhận**, không suy diễn chỉ từ annotation.

## 8. Cách điều tra khi thấy span hoặc số liệu bị trùng

Không sửa mã ngay khi nhìn thấy hai span giống nhau. Đi theo bốn lớp bằng chứng dưới đây.

### Bước 1 – Khoanh vùng đúng một lần thực thi

Tạo một kịch bản xác định: dùng môi trường thử nghiệm ít traffic, một request với correlation ID rõ ràng và ghi lại thời gian bắt đầu/kết thúc.

Ghi các thông tin:

- Build/commit và phiên bản Spring Boot, Spring Modulith, Micrometer.
- Tên entry point, ứng dụng/module, request ID hoặc event ID ở log nghiệp vụ.
- Số lần handler/facade/listener thực sự chạy.
- Số lượng trace/span quan sát được, span ID, parent span ID, tên và tags.

**Không đưa ID có cardinality cao hoặc dữ liệu nhạy cảm vào metric tag**; ID chỉ phục vụ correlation ở log/trace có kiểm soát.

### Bước 2 – So các span theo phạm vi

| Dấu hiệu | Cách hiểu ban đầu | Cần kiểm tra tiếp |
|---|---|---|
| HTTP server span chứa Modulith module span | Thường hợp lệ: hai ranh giới | Tên/tags và vị trí instrument |
| Module span chứa business substep có thời lượng nhỏ hơn | Thường hợp lệ: hai công đoạn | Công đoạn có thực sự khác biệt? |
| Modulith span chứa `@Observed` span cùng method, thời gian gần trùng | Nghi có hai nguồn instrument cùng entry | Annotation, aspect, cấu hình observability |
| Hai span cùng tên nhưng không chồng thời gian | Có thể hai lượt method call | Count call, retry, re-entry |
| Hai span cùng root nhưng khác trace ID | Có thể context propagation gặp vấn đề | Executor, context transfer, backend |
| Event listener span lặp và log listener lặp | Có thể xử lý thật bị lặp | Registry, retry, event ID, idempotency |

Không cộng thời lượng của span cha và con để tính tổng thời gian request; duration lồng nhau chứa các đoạn chồng thời gian, không phải những khoảng độc lập.

### Bước 3 – Xác định ai tạo observation

Tìm **trong phần mã có quyền kiểm tra**, tại chính phương thức bị nghi ngờ:

- Annotation `@Observed`, `@NewSpan` hoặc annotation tùy biến trên class/method.
- `Observation.createNotStarted(...)`, `Observation.start(...)`, các helper wrapper tương tự.
- Custom `@Aspect` hoặc interceptor áp vào controller, service, listener.
- Instrumentation tự động của Spring Modulith trên API module và listener.
- Instrumentation HTTP server/client/DB của Spring Boot, Micrometer hoặc Java agent.

Nếu thấy `@Observed` nhưng không có aspect xử lý, annotation có thể **chưa tạo observation nào**. Nếu Spring Modulith không instrument điểm vào đó, annotation thủ công có thể lại là nguồn duy nhất. Chẩn đoán phải dựa trên dữ liệu trace và dependency/configuration của build thật.

### Bước 4 – Kiểm tra metric riêng biệt

Trong Spring Boot Actuator, nếu `metrics` được expose và quyền truy cập cho phép:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
~~~

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Xem những meter phát sinh khi chạy một kịch bản, ví dụ `module.events.published` nếu hệ thống có hỗ trợ và thật sự phát domain event. **Counter event published không dùng để kết luận trực tiếp rằng method đã được instrument hai lần**; nó đo một loại hành vi khác. Hãy kiểm tra tên meter, tag, số lần tăng và nguồn tạo meter cụ thể.

Khi chẩn đoán tracing, nên dùng một exporter/backend có khả năng hiển thị span và tags đầy đủ. Chỉ gọi `/actuator/modulith` không đủ: endpoint này trả **metadata kiến trúc module**, không phải danh sách span runtime.

## 9. Cách sửa an toàn theo từng tình huống

### 9.1. Trường hợp A: `@Observed` chồng lên Modulith entry

**Triệu chứng:** Một request gọi facade một lần; trong trace có span module và span `@Observed` cùng bao toàn bộ method.

**Cách làm:**

1. Xác nhận Modulith module span đã có các thuộc tính module cần cho mục tiêu quan sát.
2. Gỡ `@Observed` tại chính method được instrument tự động, nếu nó không còn thêm ngữ nghĩa riêng.
3. Chuyển observation thủ công vào bước con thực sự cần đo như `order.risk-evaluation`.
4. Chạy lại cùng kịch bản; so span ID, số lần thực thi method và metrics trước/sau.

**Không** xóa toàn bộ quan sát module chỉ để sửa một annotation trùng nếu hệ thống còn nhiều entry cần xem.

### 9.2. Trường hợp B: custom AOP bắt quá rộng

**Triệu chứng:** Mọi method thuộc `@Service` đều có span nội bộ, kể cả public API đã được Spring Modulith quan sát; trace có nhiều tầng đo cùng ý nghĩa.

**Cách làm:** Thu hẹp pointcut của aspect. Chỉ áp dụng cho annotation tùy chỉnh đánh dấu **công đoạn nghiệp vụ riêng** hoặc những method chưa được framework quan sát. Ví dụ annotation của dự án:

~~~java
package com.example.shop.observability;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface BusinessStep {}
~~~

~~~java
@Service
class RiskAssessment {

    @BusinessStep
    public Decision evaluate(Order order) {
        // Một công đoạn riêng, không trùng module entry.
        return Decision.approved();
    }
}
~~~

`BusinessStep` chỉ là marker; để instrument nó cần có aspect được triển khai đúng. Mục đích của ví dụ là **thu hẹp phạm vi áp dụng** thay vì bắt mọi service, không phải một cấu hình hoàn chỉnh. Kiểm tra proxy/self-invocation và aspect ordering trước khi coi việc gắn marker là đã có span.

### 9.3. Trường hợp C: custom HTTP filter chồng lên Boot

Nếu Spring Boot/Spring Framework đã có HTTP server observation, một custom filter mở thêm observation tên giống `http.server.requests` cho cùng request thường không cần thiết. Cân nhắc **bổ sung low-cardinality key-values hoặc convention phù hợp vào observation đã tồn tại**, nếu cần thêm thông tin, thay vì tạo observation HTTP server thứ hai. Cơ chế tùy biến cụ thể phải chọn theo API/phiên bản framework.

### 9.4. Trường hợp D: cùng event listener nhận lại event

Nếu log nghiệp vụ cho thấy listener thật sự chạy hai lần, **đó là lỗi hoặc semantics nghiệp vụ cần điều tra**. Không sửa bằng cách vô hiệu span, bởi điều đó chỉ che triệu chứng. Kiểm tra publication/resubmission, chiến lược retry, cách gắn listener, duplicate messages và khả năng idempotent của cập nhật dữ liệu.

### 9.5. Trường hợp E: không thấy span sau khi bỏ annotation

Nếu gỡ annotation thì span biến mất hoàn toàn, có thể điểm đó **không hề được Modulith instrument** trong phiên bản/cấu hình hiện tại. Khi đó cần khôi phục một nguồn instrument thích hợp, hoặc điều chỉnh cách đặt API/module boundary và cấu hình observability. Nguyên tắc “tránh trùng” không có nghĩa “bỏ hết instrument thủ công”.

## 10. Kiểm chứng trước và sau khi sửa

Một kịch bản kiểm thử hữu ích nhất cần chứng minh **cả số lần thực thi và chất lượng telemetry**:

| Tiêu chí | Trước khi sửa | Sau khi sửa mong muốn |
|---|---|---|
| Request nghiệp vụ | 1 request có correlation ID | Vẫn đúng 1 request |
| Method entry thực thi | 1 lượt hoặc số lượt theo logic thực | Không thay đổi ngoài ý muốn |
| Span cho HTTP request | 1 HTTP server observation hợp lệ | Giữ nguyên |
| Span ranh giới module | Có nếu Modulith instrument điểm này | Giữ được 1 phạm vi module entry |
| Span `@Observed` trùng toàn method | Có, nếu nguyên nhân là annotation | Không còn tầng instrument trùng |
| Span nghiệp vụ con | Có khi đã chủ đích đo công đoạn riêng | Giữ các span con có ý nghĩa |
| Event publication và listener execution | Được ghi nhận theo hành vi thật | Không tăng/giảm vì chỉ đổi instrumentation |
| Metrics liên quan | Phù hợp với số lần measurement thực | Không phát sinh hai bản ghi đo đồng ngữ nghĩa |
| Trace context xuyên async | Có parent/link đúng theo thiết kế | Giữ khả năng correlation |

### Hướng dẫn chạy thử có kiểm soát

1. Trên môi trường dev/test, thiết lập tracing backend và mức sampling phù hợp để thấy được lượt chạy thử. Sampling 100% chỉ nên dùng ngắn hạn có kiểm soát, tránh tăng tải hệ thống sản xuất.
2. Đánh dấu request bằng một ID kiểm thử; log một dòng ở điểm bắt đầu **thực thi nghiệp vụ** và một dòng ở điểm kết thúc, nhằm đếm số lần gọi thật.
3. Chạy một request, xuất trace đủ spans và ghi nhận tên/tags/parent IDs.
4. Xác nhận nguồn instrument trùng trên method hoặc aspect trước khi sửa.
5. Chỉ loại bỏ/thu hẹp nguồn trùng, sau đó chạy lại cùng dữ liệu và điều kiện.
6. So sánh kết quả nghiệp vụ, số lần thực thi và trace. Một trace “ít span hơn” chưa đủ nếu kết quả nghiệp vụ đã bị thay đổi.
7. Thử thêm kịch bản lỗi, retry và event bất đồng bộ nếu ứng dụng có các nhánh đó; bảo đảm không làm mất dấu vết thực sự cần thiết.

**Điểm đánh giá quan trọng:** Không dùng duy nhất số span để xác định thành công. Phải chứng minh mỗi span còn lại có ý nghĩa đo lường riêng và hành vi nghiệp vụ không bị ảnh hưởng.

## 11. Những biện pháp chỉ che dấu vấn đề

| Biện pháp hấp dẫn nhưng dễ sai | Vì sao không giải quyết nguồn gốc |
|---|---|
| Hạ sampling để ít thấy span giống nhau | Các nguồn instrument vẫn chồng lấn; dữ liệu chỉ ít được lấy mẫu hơn |
| Đổi tên `@Observed` span cho khác module span | Đổi tên không đổi scope đo giống nhau |
| Dùng `MeterFilter` loại metric sau khi tạo | Có thể ẩn meter, nhưng không đảm bảo ngăn observation/span trùng |
| Bỏ tracing ở tất cả module | Có nguy cơ mất khả năng xem tương tác qua ranh giới |
| Xóa span ở tracing backend | Chỉ thay đổi cách hiển thị/lưu trữ, không sửa mã tạo observation |
| Gộp các span cùng tên bằng xử lý hậu kỳ | Có thể gộp nhầm những lần gọi thật, retry hoặc listener khác nhau |
| Đếm số span bằng số lần publish event | Hai số đo khác semantics; không dùng làm bằng chứng trực tiếp cho nhau |

Một số thư viện/agent có cơ chế suppression hoặc gộp span tự động, nhưng không nên giả định cơ chế đó luôn hoạt động giống nhau giữa các version hoặc các lớp instrumentation.

## 12. Kết hợp với module graph và kiểm chứng kiến trúc

Chủ đề này thuộc module học **Spring Modulith Documentation & Observability**: một mặt ta dùng `ApplicationModules` và `Documenter` để xác định các ranh giới hợp lệ, mặt khác dùng Actuator, metrics và tracing để kiểm tra tương tác khi hệ thống chạy.

Ví dụ module graph có ba module:

~~~mermaid
flowchart LR
    API["web adapter"] --> Order["order"]
    Order --> Inventory["inventory"]
    Order --> Notification["notification"]
~~~

Sơ đồ ở trên thể hiện mô hình trao đổi **minh họa**, không cố định chiều dependency mà `Documenter` có thể suy ra từ mã cụ thể. Nếu `order` phát event để `inventory` lắng nghe, static dependency có thể hướng từ consumer đến publisher event API, trong khi runtime event đi theo hướng ngược lại.

**Liên hệ với instrument trùng:**

- Graph cho biết **vị trí ranh giới** giữa module; dùng nó để chọn nơi ưu tiên module observability.
- Tracing cho biết **điểm nào thực sự được đo** trong một lượt chạy và những span nào lồng nhau.
- Actuator `/actuator/modulith` trả metadata về module của bản triển khai, **không phải** công cụ đếm số lần gọi của entry point.
- Event metrics cho biết lượt publish được instrument, **không tự chứng minh** một listener đã hoàn tất hay rằng có duplicate instrumentation.
- Context propagation giúp liên hệ trace qua bất đồng bộ, **không tự loại bỏ** hai nguồn instrument cùng điểm vào.

Tổ chức nội dung theo ranh giới module giúp telemetry phản ánh cấu trúc, nhưng mỗi observation phải có **một ý nghĩa và phạm vi đo rõ ràng**.

## 13. Các tình huống tự luyện tập

### Tình huống A: Span HTTP và module cùng xuất hiện

Một request `POST /orders` sinh span `http.server.requests` và span `order.place`. Hai span cùng khoảng thời gian nhưng có tags khác nhau.

**Câu hỏi:** Có phải instrument trùng?

**Gợi ý:** Chưa đủ bằng chứng. HTTP request và module API là hai ranh giới hợp lệ. Hãy kiểm tra xem có hai observation cùng đo chính một HTTP request hoặc cùng một method entry không.

### Tình huống B: `@Observed` trên module facade

`OrderFacade.place()` được Spring Modulith instrument và có `@Observed` có hiệu lực trên cùng method. Trace hiển thị hai span lồng nhau với duration tương đương, log nghiệp vụ chỉ ghi một lượt vào.

**Câu hỏi:** Nên thay đổi gì?

**Gợi ý:** Xác định hai nguồn và loại bỏ/thu hẹp manual observation cùng phạm vi; có thể chuyển observation tùy chỉnh vào nghiệp vụ con cần đo.

### Tình huống C: Hai span listener, hai lần cập nhật kho

Listener xử lý một event ID hai lần, log có hai lần gọi và số lượng tồn kho bị giảm hai lần.

**Câu hỏi:** Có nên bỏ `@Observed` để giải quyết nghiệp vụ?

**Gợi ý:** Không. Dữ liệu cho thấy hai lượt xử lý thật. Cần điều tra retry/resubmission/duplicate event và xử lý idempotency. Có thể có duplicate instrumentation đồng thời, nhưng nó là vấn đề riêng.

### Tình huống D: Không có span listener

Sau khi gỡ `@Observed`, không còn bất kỳ span nào cho listener trong tracing backend.

**Câu hỏi:** Điều này chứng minh Spring Modulith bị lỗi?

**Gợi ý:** Không. Cần kiểm tra liệu listener có nằm trong phạm vi Modulith observability, tracing handler/exporter có hoạt động, sampling/context propagation có đúng hay không. Có thể `@Observed` là instrumentation duy nhất trước đó.

### Tình huống E: Metric tăng hai lần

Một operation nghiệp vụ chạy một lần nhưng hai meter cùng tên/semantics được ghi nhận. Trace hiển thị hai span chồng lấn. Người vận hành đề nghị dùng bộ lọc metrics để loại một meter.

**Câu hỏi:** Có nên chấp nhận đây là cách sửa cuối cùng?

**Gợi ý:** Không nên nếu đã xác định được hai nguồn instrument trên cùng điểm. Lọc meter có thể che triệu chứng; nên sửa nguồn instrument ở mã/configuration, sau đó xác nhận lại cả span và metric.

## 14. Danh sách kiểm tra khi review code

- [ ] Xác định được entry point nào đã được Spring Modulith hoặc Spring Boot instrument tự động.
- [ ] Không gắn thêm `@Observed`/`@NewSpan` hoặc manual `Observation` với cùng phạm vi chỉ để “thêm span” cho điểm đó.
- [ ] Các observation thủ công có tên, phạm vi và mục đích nghiệp vụ rõ ràng.
- [ ] Custom AOP pointcut không vô tình áp lên mọi public module API.
- [ ] Khi thấy span giống nhau, đã phân biệt duplicate instrumentation với lời gọi thật lặp lại.
- [ ] Sử dụng trace/span IDs, module tags, log correlation và dữ liệu nghiệp vụ để điều tra.
- [ ] Không dùng event publish counter thay cho số lần xử lý listener hay số lần instrument method.
- [ ] Không dùng sampling, metric filter hoặc backend deduplication làm giải pháp chính cho instrumentation chồng lấn.
- [ ] Sau thay đổi, giữ được span HTTP, module, event và business substep thực sự có ý nghĩa.
- [ ] Kiểm tra trường hợp bất đồng bộ/retry và context propagation nếu áp dụng.
- [ ] Ghi nhận version Spring Boot, Spring Modulith, Micrometer và cấu hình export khi so sánh kết quả.

## 15. Ghi nhớ

**Tránh instrument trùng không có nghĩa giảm số lượng span bằng mọi giá.** Mục tiêu là để mỗi span/metric có một **ngữ nghĩa đo lường, một phạm vi và một nguồn sinh ra rõ ràng**.

Trong ứng dụng Spring Modulith:

1. Ưu tiên hạ tầng framework ở những điểm nó đã quan sát đúng: HTTP request, ranh giới module và listener phù hợp.
2. Dùng `@Observed`/`Observation` thủ công cho công đoạn bổ sung, không đo lại nguyên phạm vi module entry.
3. Nếu trace cho thấy hai span tương tự, xác minh **một hay hai lần thực thi nghiệp vụ** trước khi kết luận.
4. Kết hợp module graph, Actuator, metrics, tracing, event publication và context propagation theo đúng câu hỏi cần trả lời.
5. Sau khi loại trùng, kiểm tra cả telemetry và **kết quả nghiệp vụ** để không che đi lỗi retry/event thật.

## Tài liệu tham khảo

1. [Spring Modulith Reference – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Modulith Actuator, observability của module, event metrics và span.
2. [Spring Modulith Reference – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html) — Application module, API và ranh giới module.
3. [Spring Modulith Reference – Events](https://docs.spring.io/spring-modulith/reference/events.html) — Event listener, publication và cách xử lý sự kiện.
4. [Spring Boot Reference – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Micrometer Observation trong Spring Boot.
5. [Spring Boot Reference – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — Tracer, span, sampling, exporter và propagation.
6. [Micrometer Observation Documentation](https://docs.micrometer.io/micrometer/reference/observation.html) — ObservationRegistry, observation handlers và instrumentation.
7. [Spring Framework Reference – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html) — Instrumentation tích hợp ở cấp framework và tùy biến observation.

