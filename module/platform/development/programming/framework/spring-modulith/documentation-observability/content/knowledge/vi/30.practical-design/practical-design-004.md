# Chọn span cần giữ trong trace

## 1. Tại sao phải chọn span có chủ đích?

Một ứng dụng Spring Boot sử dụng **Spring Modulith** có thể chứa nhiều application module như `ordering`, `inventory`, `payment` và `notification`. Module graph mô tả ranh giới và quan hệ phụ thuộc; Actuator, event metrics và tracing giúp quan sát cách chúng tương tác khi ứng dụng chạy. Với mỗi yêu cầu hoặc sự kiện, trace trả lời: *luồng xử lý đi qua đâu, mất thời gian ở bước nào và lỗi bắt đầu từ đâu?*

Nếu chỉ thấy root span `POST /orders: 1.8s`, nhóm vận hành chưa biết 1.8 giây đó nằm ở inventory, database, payment gateway hay listener. Nếu tạo span cho mọi getter, mapper và vòng lặp, một request lại có hàng nghìn span, tốn tài nguyên và khó đọc.

Bài **“Chọn span cần giữ trong trace”**, thuộc chương **Thiết kế thực tế** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`, hướng dẫn cách chọn đúng ranh giới quan sát để có đủ dữ liệu chẩn đoán với chi phí hợp lý.

Phân biệt ngay hai quyết định:

1. **Span nào nên được tạo?** Instrumentation xác định các bước có ý nghĩa về latency, lỗi, quan hệ nhân quả hoặc trách nhiệm module.
2. **Trace nào nên được lưu?** Sampling và retention xác định phần dữ liệu được backend giữ lại theo ngân sách và mức độ quan trọng.

Một span được tạo tốt vẫn có thể bị sampling loại khỏi backend. Ngược lại, lưu 100% trace không giúp phân tích được gì nếu instrumentation chỉ tạo những span không phản ánh điểm nghẽn thực tế.

## 2. Các khái niệm nền tảng

Một **trace** mô tả một công việc logic gồm nhiều **span**. Một span thường có tên operation, thời gian bắt đầu/kết thúc, duration, status, thuộc tính và mốc sự kiện. Trong một trace có thể có quan hệ parent-child; các hoạt động bất đồng bộ hoặc retry cũng có thể được liên kết bằng **span links** khi cách biểu diễn đó phù hợp.

~~~text
Trace T1
  SERVER POST /orders
    INTERNAL ordering.placeOrder
      INTERNAL inventory.reserve
      CLIENT HTTP payment-gateway/authorize
      DB ordering INSERT
~~~

| Thuật ngữ | Ý nghĩa khi thiết kế |
| --- | --- |
| Root span | Điểm vào request, message hoặc một tác vụ độc lập |
| Child span | Một operation xảy ra trong ngữ cảnh của span cha |
| Span link | Quan hệ nhân quả giữa những span/traces không phù hợp với cây cha-con thông thường |
| Span event | Mốc tức thời nằm trong một span, không đo một khoảng thời gian riêng |
| Span attributes | Thuộc tính hỗ trợ phân loại và chẩn đoán |
| Trace ID | Mã liên kết các span của cùng trace; không dùng làm metric label |
| Context propagation | Duy trì ngữ cảnh qua thread, async event hoặc process |
| Sampling | Quy tắc quyết định trace/span được ghi hoặc giữ theo khả năng hệ thống |
| Retention | Chính sách thời gian lưu và quyền truy cập dữ liệu trace |

Một domain event như `OrderPlaced` **không mặc nhiên phải là một span**. Nếu chỉ cần đánh dấu thời điểm công bố event, thêm span event vào operation đang tồn tại có thể đủ. Ngược lại, listener gửi email qua dịch vụ ngoài trong 500 ms thường đáng có span riêng vì đây là công việc có độ trễ và lỗi độc lập.

## 3. Bắt đầu từ module graph và đường nghiệp vụ

Giả sử hệ thống bán hàng có bốn module:

~~~text
com.acme.shop
├── ordering
├── inventory
├── payment
└── notification
~~~

Luồng đặt hàng:

~~~mermaid
flowchart LR
    H["HTTP POST /orders"] --> O["ordering.placeOrder"]
    O --> I["inventory.reserve"]
    O --> P["payment.authorize"]
    O --> W["ordering.persist"]
    O --> E["publish OrderPlaced"]
    E --> N["notification.handleOrderPlaced"]
    N --> M["email-provider"]
~~~

Module graph của Spring Modulith giúp xác định `ordering` được phép phụ thuộc vào API nào của `inventory` và `payment`, module `notification` nhận loại event nào. Nhưng module graph là quan hệ **tĩnh**, không chứng minh mọi request đều đi qua mọi cạnh.

Trước khi chọn span, hãy ghi:

- Entrypoint: HTTP, scheduler, command, message consumer hoặc event handler.
- Ranh giới module: operation API nào cần quan sát riêng.
- Dependency tốn thời gian: database, HTTP client, broker, filesystem, lock hoặc cache miss.
- Bước có lỗi cần phân loại: timeout, hết hàng, payment declined, retries và publication failure.
- Các đoạn đồng bộ/bất đồng bộ: listener chạy cùng thread, sau commit hay trên executor.
- Instrumentation đã có: Spring Boot, Micrometer, HTTP client, JDBC, OpenTelemetry hoặc Spring Modulith observability.

**Nguyên tắc:** trước khi thêm span thủ công, xem trace thực tế của ứng dụng và tài liệu kiến trúc. Không nên tạo span thứ hai để đo đúng một HTTP call đã có client span với đủ thông tin.

## 4. Quy tắc quyết định giữ hay bỏ một span

| Thao tác | Mặc định | Lý do |
| --- | --- | --- |
| HTTP server/consumer entrypoint | Giữ | Xác định điểm bắt đầu và request context |
| HTTP client, database, message producer/consumer | Giữ instrumentation có sẵn khi cần | Phân biệt dependency gây latency |
| Operation nghiệp vụ lớn ở ranh giới module | Giữ nếu có trách nhiệm/failure mode riêng | Xác định module chịu trách nhiệm |
| Listener xử lý event với I/O hoặc retry | Giữ | Phân tích hậu xử lý bất đồng bộ |
| Một retry attempt qua HTTP client | Giữ nếu giúp phân biệt attempts | Thấy lỗi và duration của từng lần gọi |
| Getter, setter, mapper đơn giản | Không tạo | Nhiễu, ít giá trị |
| Hàm tiện ích chạy hàng nghìn lần | Không tạo từng span | Dễ gây bùng nổ span |
| Validation nhẹ trong bộ nhớ | Thường dùng span event khi lỗi | Không cần đo duration riêng |
| Cache hit/miss liên tục | Ưu tiên metric tổng hợp | Tránh một span cho mỗi lookup |
| Một mốc publish thành công | Ưu tiên span event | Là điểm thời gian, không phải một bước kéo dài |
| Batch xử lý nhiều record | Một span theo batch/chunk | Chi phí không tăng tuyến tính theo item |

Năm câu hỏi để review một span dự kiến:

1. Span giải thích câu hỏi chẩn đoán nào mà span cha chưa giải thích?
2. Nó đại diện cho **trách nhiệm module** hay chỉ là chi tiết triển khai?
3. Nó xuất hiện bao nhiêu lần trên một request, kể cả khi có retry và vòng lặp?
4. Nó có thuộc tính nào nhạy cảm hoặc quá dài không?
5. Nó đã được một instrumentation khác đo trùng chưa?

Nếu không thể trả lời rõ, ưu tiên metric aggregate hoặc log an toàn thay vì bổ sung span thường trực.

## 5. Ba mức chi tiết của trace

### Mức tối thiểu

~~~text
SERVER POST /orders
  CLIENT payment-gateway/authorize
~~~

Giúp theo dõi request và dependency ngoài nhưng khó phân biệt module nội bộ.

### Mức cân bằng

~~~text
SERVER POST /orders
  INTERNAL ordering.placeOrder
    INTERNAL inventory.reserve
    CLIENT payment-gateway/authorize
    DB ordering INSERT
~~~

Đây là điểm xuất phát phù hợp cho nhiều hệ thống: mỗi span phản ánh một bước có latency hoặc trách nhiệm rõ ràng.

### Mức điều tra chuyên sâu

~~~text
SERVER POST /orders
  INTERNAL ordering.placeOrder
    INTERNAL ordering.validateRules
    INTERNAL inventory.reserve
      INTERNAL inventory.lockStock
    INTERNAL payment.authorize
      CLIENT HTTP payment-gateway (attempt 1)
      CLIENT HTTP payment-gateway (attempt 2)
    DB ordering INSERT
    EVENT OrderPlaced.published
~~~

Mức điều tra có thể hữu ích khi lỗi chỉ xuất hiện ở một nhánh hiếm. Tuy nhiên, không nên mặc định thêm span vào từng rule hoặc từng item nếu thường xuyên có nhiều nghìn item.

Không có một con số span tối ưu cho mọi hệ thống. Cần cân bằng **khả năng định vị lỗi** với số span/request, chi phí exporter/backend và tính dễ đọc của trace.

## 6. Đặt tên span ổn định, thuộc tính có chọn lọc

Tên span cần mô tả loại operation, không mô tả dữ liệu của từng request:

| Nên dùng | Tránh dùng |
| --- | --- |
| `ordering.placeOrder` | `placeOrder-ORD-12345` |
| `inventory.reserve` | `reserve-customer-2001` |
| `payment.authorize` | `payment-Bearer-...` |
| `notification.handleOrderPlaced` | `handle-<toString(event)>` |
| `HTTP POST /orders/{id}` | `HTTP POST /orders/ORD-12345` |

Ví dụ schema thuộc tính tự định nghĩa:

~~~text
span.name = inventory.reserve
span.kind = INTERNAL
module.name = inventory
module.operation = reserve
event.type = OrderPlaced
outcome = success
retry.count = 0
~~~

Các key trên mang tính **minh họa**; phải ưu tiên semantic conventions có sẵn trong tracing stack, rồi chỉ bổ sung những key ứng dụng thật sự cần. Tên module, operation, event type và outcome thường là tập giá trị nhỏ, ổn định.

Tránh đưa vào span name, events, attributes hoặc baggage: access token, email khách hàng, số thẻ, raw payload, HTTP authorization headers, cookie, mật khẩu, SQL parameters hoặc exception message chứa input từ người dùng.

Trace ID có thể được dùng để liên hệ trace với log theo chính sách; **không biến trace ID thành tag của Counter/Timer**, vì mỗi request tạo ra một giá trị mới, làm cardinality metrics tăng.

## 7. Khi nào Spring Modulith đã cung cấp đủ spans?

Spring Modulith có thành phần observability tích hợp với hệ quan sát của Spring Boot/Micrometer, và Spring Boot có thể đã tạo spans cho HTTP, database hoặc messaging. Tên và số span thực tế phụ thuộc version, dependencies, phương thức gọi và configuration.

Trước khi instrument thủ công, nên:

1. Kiểm tra thành phần observability và tracing đang có hiệu lực trong ứng dụng.
2. Tạo một request với dữ liệu kiểm thử.
3. Mở trace trong backend và kiểm tra cây span, duration, attributes, status.
4. Xác định span nào đã phản ánh chính xác API module và dependency đang gọi.
5. Chỉ thêm span cho bước nghiệp vụ quan trọng chưa có, hoặc nơi cần phân biệt latency/failure.

Không được suy ra rằng cứ có một cạnh trên module graph thì Spring Modulith sẽ tự sinh một span trong mọi cấu hình. Một lời gọi qua API module có thể đã được đo; một callback hoặc self-invocation lại có thể không hiện lên như dự đoán. **Trace thực tế** là bằng chứng cần dùng.

## 8. Ví dụ tạo observation cho operation nghiệp vụ

Khi cần một operation quan trọng chưa được quan sát, có thể sử dụng Micrometer Observation. Với các ObservationHandlers và tracing dependencies tương thích, observation được biểu diễn thành telemetry theo cấu hình.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderTracingFacade {

    private final ObservationRegistry registry;
    private final OrderService service;

    public OrderTracingFacade(
            ObservationRegistry registry, OrderService service) {
        this.registry = registry;
        this.service = service;
    }

    public OrderReceipt placeOrder(PlaceOrder command) {
        Observation observation = Observation
                .createNotStarted("ordering.placeOrder", registry)
                .lowCardinalityKeyValue("module", "ordering")
                .lowCardinalityKeyValue("operation", "placeOrder")
                .start();

        try (Observation.Scope scope = observation.openScope()) {
            return service.placeOrder(command);
        } catch (RuntimeException ex) {
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }
}
~~~

`OrderService`, `PlaceOrder` và `OrderReceipt` là kiểu minh họa của ứng dụng. Khi chạy thực tế, cần dependency Micrometer và các handlers/exporter phù hợp.

Ý nghĩa:

- `start()` và `stop()` đo vòng đời operation.
- `openScope()` làm observation thành ngữ cảnh đang hoạt động trên đường xử lý đồng bộ, rồi đóng scope an toàn.
- `observation.error(ex)` ghi nhận lỗi trong observation mà không nuốt exception.
- Hai low-cardinality values chỉ là tên module/operation ổn định, không chứa ID đơn hàng.
- Nếu Spring Modulith đã tạo một span cho đúng operation này, hãy xem xét bỏ wrapper để tránh đo trùng.

Với Reactor hoặc xử lý bất đồng bộ, scope ThreadLocal trong đoạn code không tự bảo đảm propagation qua mọi scheduler. Cần dùng integration với context propagation phù hợp và kiểm tra bằng trace.

## 9. Ranh giới module là điểm đặt span có giá trị

Giả sử `ordering` gọi `inventory.reserve` và `payment.authorize`. Đây thường là hai ứng viên span vì mỗi module có trách nhiệm và failure mode khác nhau.

~~~mermaid
flowchart LR
    O["ordering.placeOrder"] --> I["inventory.reserve"]
    O --> P["payment.authorize"]
    I --> DB["inventory DB"]
    P --> G["payment gateway"]
~~~

Nếu `inventory.reserve` mất 400 ms do database lock, span của module và database giúp định vị lỗi. Nếu `payment.authorize` mất 800 ms do provider timeout, span client và retry cho biết nguồn chậm.

Ngược lại, nếu `ordering` gọi 500 getter của `inventory` trong một vòng lặp, giữ 500 spans nhỏ sẽ làm trace khó đọc. Có thể thiết kế API batch và một span `inventory.reserveBatch` với `batch.size` được phép, kết hợp metric tổng hợp.

**Ranh giới module quan sát được không đồng nghĩa ranh giới hợp lệ về kiến trúc.** Nếu `ordering` gọi trực tiếp lớp `inventory.internal.StockRepository`, trace có thể cho thấy tương tác nhưng vẫn cần `ApplicationModules.verify()` để phát hiện vi phạm phụ thuộc và sửa thiết kế API.

## 10. Event đồng bộ, bất đồng bộ và xử lý sau commit

Tương tác theo domain event trong Spring Modulith cần được xem riêng vì **thời điểm xử lý và quan hệ nhân quả** có thể khác một lời gọi method thông thường.

### Listener đồng bộ

Nếu một listener chạy cùng thread với publisher, trace context thường có thể được duy trì trong lời gọi đồng bộ:

~~~text
Trace T-order
  ordering.placeOrder
    event OrderPlaced.published
    notification.handleOrderPlaced
~~~

Nếu listener chỉ cập nhật một biến trạng thái ngắn, span event có thể đủ. Nếu listener gọi email provider hoặc thực hiện truy vấn tốn thời gian, một span listener giúp xác định lỗi/latency riêng.

### Listener bất đồng bộ

Khi listener chạy trên executor khác, propagation không mặc nhiên đúng trong mọi cấu hình:

~~~text
HTTP request thread
  ordering.placeOrder
    publish OrderPlaced

executor thread
  notification.handleOrderPlaced
    email-provider.send
~~~

Có thể sử dụng cơ chế context propagation tương thích với Micrometer, Spring Boot và executor của dự án để mang trace context đến listener. Cần kiểm tra thực tế: listener span nối vào trace gốc, xuất hiện trong trace khác có link hay hoàn toàn rời rạc?

### Listener sau commit, retry hoặc replay lâu sau request

Một event có thể được xử lý sau khi transaction gốc kết thúc hoặc replay từ publication registry nhiều phút sau. Cố kéo mọi bước vào cùng một parent-child tree có thể không phản ánh đúng vòng đời.

**Span link** thích hợp khi muốn biểu diễn quan hệ giữa một lần publish và một hoạt động được khôi phục độc lập, nếu cơ chế publication cho phép lưu/khôi phục ngữ cảnh phù hợp. Nếu không có context gốc, nên lưu correlation identifier an toàn ở dữ liệu nghiệp vụ/registry để có thể tra cứu; không nên suy luận rằng luôn có một trace hoàn chỉnh xuyên thời gian.

| Bước event | Chọn cách ghi | Điều cần kiểm tra |
| --- | --- | --- |
| Tạo object `OrderPlaced` | Không tạo span | Đây thường là xử lý bộ nhớ ngắn |
| Publish event thành công | Span event trên operation cha | Chỉ tạo span mới nếu cần đo độ trễ publish |
| Ghi publication registry | Dùng DB instrumentation hoặc span có lý do | Không log payload/secret để debug |
| Listener gửi email | Span listener và HTTP client | Có độ trễ/lỗi độc lập |
| Retry HTTP client | Client span theo attempt khi có giá trị | Tránh span trùng lặp |
| Retry sau commit | Trace riêng và span link nếu hỗ trợ | Không tạo quan hệ cha-con giả |
| Batch xử lý N event | Span cho batch/chunk nếu phù hợp | Tránh span theo từng item không giới hạn |

Việc dùng `@ApplicationModuleListener`, `@Async`, transactional listeners hoặc event publication registry phải được xem theo cơ chế đang cấu hình; không thể áp một quy tắc propagation duy nhất cho mọi listener.

## 11. Context propagation: giữ tương quan, không phát tán dữ liệu

Ngữ cảnh tracing gồm trace ID/span ID và các trường sampling cần thiết. Ngoài ra, hệ sinh thái Micrometer có thể chuyển thêm baggage, MDC hoặc dữ liệu quan sát tùy cấu hình. Các lớp này có phạm vi khác nhau:

1. **Trace context:** dùng để nối hoặc liên kết spans.
2. **Observation/baggage context:** thêm ngữ cảnh có thể lan qua thread/process; nên rất hạn chế về nội dung.
3. **Security, transaction và request context:** có mục đích riêng; không tự động cần được truyền theo trace.

Một anti-pattern là sao chép tất cả HTTP headers hoặc event payload vào baggage để bảo đảm listener “nhận đủ thông tin”. Điều đó có thể làm lộ authorization token, email hoặc dữ liệu khách hàng sang logs/traces/remote calls.

### Test propagation với executor thực tế

1. Gửi request `A` vào `ordering`, ghi trace ID qua tracer với dữ liệu test.
2. Cho request A phát `OrderPlaced` và để listener thực sự chạy bất đồng bộ.
3. Xem span listener có liên kết theo thiết kế (cùng trace hoặc span link) không.
4. Cho request `B` chạy trên cùng executor để xác minh không có MDC/baggage của A bị giữ lại.
5. Tạo tình huống listener exception, timeout hoặc retry để kiểm tra context khi đường thoát khác thường.
6. Nếu trace bị đứt, xem cấu hình task executor/context propagation trước khi tự tạo ID mới và gắn vào metrics.

Trong mô hình reactive, sử dụng context integration tương thích với Reactor thay vì giả định `ThreadLocal` scope sẽ tự theo mọi operator. Một correlation link bị thiếu không đồng nghĩa listener chưa xử lý event; event metrics và publication state là nguồn kiểm tra bổ sung.

## 12. Span hay span event cho validation, retry và cache?

Một **span event** phù hợp cho mốc thời gian không cần đo duration riêng:

~~~text
ordering.placeOrder
  event validation.passed
  event OrderPlaced.published
~~~

Nếu validation chỉ là vài phép so sánh hoặc gọi hàm trong bộ nhớ, thêm span riêng có thể không giúp phát hiện vấn đề. Nếu validation gọi external rules engine, có timeout và ảnh hưởng SLO, tạo span operation riêng hợp lý.

### Retry có hai mức quan sát

Nếu chỉ cần biết có retry, có thể ghi span event:

~~~text
payment.authorize
  event retry.scheduled: attempt=1
  event retry.scheduled: attempt=2
~~~

Nếu cần biết từng request ra provider mất bao lâu, tận dụng client spans:

~~~text
payment.authorize
  CLIENT POST payment-provider (attempt 1, timeout)
  CLIENT POST payment-provider (attempt 2, timeout)
  CLIENT POST payment-provider (attempt 3, success)
~~~

Không tạo thêm một wrapper span cho đúng cùng khoảng HTTP I/O chỉ vì muốn hiển thị tên khác, trừ khi wrapper đại diện cho operation nghiệp vụ rộng hơn hoặc có thông tin riêng.

### Cache

Cache hit/miss thường nên đo bằng metric tổng hợp. Chỉ khi cache miss gây truy vấn tốn kém hoặc có lỗi đặc thù mới cần span giúp phân tích. Nếu cần, ghi thuộc tính có tập giá trị nhỏ như `cache.result=miss` lên operation hiện có.

## 13. Sampling: trace nào đáng giữ?

Chọn span cần tạo chỉ là một nửa bài toán. Hệ thống production có thể xử lý hàng triệu request; lưu tất cả trace ở mức chi tiết cao làm tăng chi phí, áp lực exporter và backend.

### Head sampling

Head sampling ra quyết định sớm khi trace bắt đầu, thường theo tỷ lệ hoặc parent context. Ưu điểm: giảm dữ liệu từ nguồn. Hạn chế: chưa biết request cuối cùng sẽ lỗi hay chậm.

Ví dụ cấu hình Spring Boot với Micrometer tracing tương thích:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Giá trị `0.10` là **ví dụ 10%**, không phải khuyến nghị cố định. Một lỗi hiếm có thể nằm trong 90% trace không được giữ; việc thiếu trace không chứng minh lỗi không xảy ra.

### Tail sampling

Tail sampling chọn trace sau khi đã nhận spans hoặc qua một khoảng đợi ở collector/backend. Có thể ưu tiên trace lỗi, latency cao, retry nhiều hoặc một operation quan trọng. Nhờ thấy kết quả cuối, nó hữu ích cho điều tra lỗi hiếm.

Nhược điểm là collector cần buffer, ghi nhận đủ spans, cấu hình routing và thời gian quyết định phù hợp. Trace dài/không kết thúc kịp hoặc dữ liệu đến nhiều collector khác nhau có thể làm quyết định không đầy đủ.

**Quan trọng:** collector không thể khôi phục span đã bị upstream SDK head sampling loại bỏ trước khi gửi. Khi triển khai tail sampling, phải đảm bảo nguồn gửi dữ liệu cần thiết để collector ra quyết định.

### Một chính sách chọn trace minh họa

| Trường hợp | Ưu tiên lưu | Mục đích |
| --- | --- | --- |
| Operation lỗi có status đáng tin cậy | Cao | Root cause |
| Latency vượt ngưỡng SLO | Cao | Tìm dependency chậm |
| Event publication lỗi hoặc retry | Cao | Điều tra luồng bất đồng bộ |
| Request thành công phổ biến | Theo tỷ lệ | Baseline phân phối latency |
| Health check/polling đều đặn | Thấp hoặc loại bỏ | Ít thông tin chẩn đoán |
| Batch rất lớn | Theo batch/chunk | Hạn chế dữ liệu mỗi item |
| Sau rollout instrumentation mới | Tăng tạm có giới hạn | Xác minh context và span names |

Các chính sách chỉ áp dụng được nếu sampling stack có thuộc tính/status cần thiết ở đúng nơi ra quyết định. Phải thử nghiệm với exporter thật và kiểm tra tỷ lệ drop, không suy từ cấu hình YAML.

## 14. Giữ cấu trúc trace đủ để đọc nguyên nhân

Một lỗi thường gặp là còn lại một span đơn lẻ:

~~~text
paymentGateway.authorize ERROR
~~~

Thiếu root span, caller module và nhánh retry, người trực vận hành khó biết request nào gọi ra provider, có bao nhiêu attempts và lỗi ảnh hưởng nghiệp vụ gì.

Mục tiêu nên là một trace có đủ:

- Root/server hoặc consumer entrypoint.
- Operation nghiệp vụ quan trọng ở module chủ trì.
- Các bước ranh giới module có trách nhiệm độc lập.
- Dependency thực sự gây latency/failure.
- Status, error category và các mốc retry/publication có giá trị.

Không nhất thiết giữ mọi span trong mọi trường hợp; nhưng **lọc span ngẫu nhiên, không xét quan hệ cha-con**, có thể tạo các cây trace khó hiểu. Ưu tiên chính sách sampling có nhận biết trace và dữ liệu đủ để kết luận.

Khi trace không đầy đủ, nguyên nhân có thể là sampling, propagation, exporter failure, pod restart, backend ingest limit hoặc do không có instrumentation. Đối chiếu log an toàn và metrics trước khi kết luận một operation không được chạy.

## 15. Giữ span trong ngân sách chi phí và an toàn dữ liệu

Số traces không phải yếu tố chi phí duy nhất. Một trace gồm 500 span tốn hơn nhiều so với trace 10 span. Một span có attributes chứa JSON lớn cũng làm tăng byte volume và nguy cơ lộ dữ liệu.

| Nguồn chi phí/rủi ro | Điều chỉnh |
| --- | --- |
| Quá nhiều spans per trace | Không instrument helper, loop, từng record |
| Span names thay đổi theo orderId | Dùng tên operation ổn định |
| Attributes/events quá dài | Thu tập field tối thiểu, có giới hạn |
| Exception message chứa input | Ghi error category an toàn, kiểm tra nơi exporter lưu exception |
| Trace ID chuyển thành metric tag | Loại khỏi low-cardinality key values |
| Auto instrumentation trùng manual | Gỡ wrapper không bổ sung ý nghĩa |
| Fan-out/retry bất đồng bộ lớn | Span theo batch/attempt quan trọng, theo dõi chi phí |
| Tail sampling đệm quá nhiều traces | Đo RAM/queue, điều chỉnh ngưỡng, routing và thời gian đợi |

**High-cardinality trace attributes không tự động trở thành Prometheus metric label.** Sự cố cardinality xảy ra nếu code hoặc collector tạo metrics từ các attributes động, chẳng hạn `customer.id` hay `trace.id`. Dù chỉ là trace attribute, thông tin cá nhân và bí mật vẫn không nên xuất ra backend.

Nên theo dõi số spans/trace theo operation, spans/sec, byte volume, dropped spans, exporter queue, latency của exporter, tài nguyên collector và tỷ lệ trace đủ điều kiện để chẩn đoán. Dùng service metrics để kiểm chứng tracing có ảnh hưởng tới hành vi ứng dụng hay không.

## 16. Thiết kế theo môi trường và quy trình bật tracing sâu

| Môi trường | Cách tiếp cận |
| --- | --- |
| Local | Có thể tăng span detail với dữ liệu giả để hiểu flow |
| Staging/integration | Kiểm tra span names, propagation, sampling và context cleanup |
| Production bình thường | Giữ operation/IO quan trọng, giới hạn byte volume và retention |
| Production đang điều tra | Tăng sampling hoặc chi tiết một luồng trong thời hạn kiểm soát |
| Batch tải rất cao | Ưu tiên span per batch/chunk và metrics aggregate |

Nếu cần tăng tracing ở production:

1. Định nghĩa lỗi cần phân tích, module/operation và thời hạn.
2. Chọn span hoặc policy sampling hẹp nhất đủ thông tin.
3. Kiểm tra thuộc tính không chứa token, email, payload hoặc dữ liệu thanh toán.
4. Xác định exporter/backend, người truy cập và retention.
5. Theo dõi số span, bytes và drop rate khi bật.
6. Khôi phục cấu hình bình thường sau khi có kết quả.
7. Đưa phát hiện thành kiểm thử hoặc metric ổn định để lần sau không cần bật trace sâu.

Sampling không phải cơ chế bảo vệ bí mật: một trace có token được lấy mẫu và lưu vẫn là dữ liệu nhạy cảm đã xuất.

## 17. Một trace thiết kế tốt cho luồng đặt hàng

Ví dụ kỳ vọng, sử dụng tên và thời gian **minh họa**:

~~~text
Trace T-order-101
SERVER POST /orders                    490 ms
  INTERNAL ordering.placeOrder         475 ms
    INTERNAL inventory.reserve         105 ms
      DB inventory UPDATE               83 ms
    INTERNAL payment.authorize         290 ms
      CLIENT HTTP payment-provider     275 ms
    DB ordering INSERT                  45 ms
    EVENT OrderPlaced.published
~~~

Nếu `notification` xử lý event sau commit với một lifecycle độc lập:

~~~text
Trace T-event-401
CONSUMER notification.handleOrderPlaced 210 ms
  CLIENT email-provider.send            190 ms
LINK -> context from T-order-101 (nếu có)
~~~

Đây là bản thiết kế cần kiểm tra bằng trace thực tế; không khẳng định Spring Modulith tự sinh đúng các tên span hoặc link như mô tả.

Từ trace đặt hàng, người vận hành thấy payment là dependency chiếm phần lớn thời gian. Từ trace listener, có thể điều tra lỗi gửi email mà không gắn nhầm nó vào latency HTTP nếu sự kiện thực sự được xử lý sau request. **Event metrics** nói listener lỗi bao nhiêu lần trên toàn bộ traffic; **trace** diễn giải một execution cụ thể.

## 18. Kiểm chứng trace đã chọn và khả năng chẩn đoán

Chạy các kịch bản có dữ liệu giả:

| Kịch bản | Điều cần thấy |
| --- | --- |
| Đặt hàng thành công | Root span và các bước module quan trọng đúng quan hệ |
| Hết tồn kho | Error category rõ, không lộ payload |
| Payment timeout và retry | Dependency/attempt gây chậm được thể hiện |
| Listener bất đồng bộ | Có parent/link/correlation phù hợp thiết kế |
| Retry sau commit | Có thể tra cứu theo publication state và trace liên quan |
| Request bị sampling bỏ | Error rate/latency tổng thể vẫn có trong metrics |
| Batch có 1.000 item | Span count không tăng một-một theo item |
| Marker dữ liệu nhạy cảm giả | Không xuất trong attributes, baggage hoặc span events |
| Request A rồi B trên cùng executor | Không rò MDC/context từ A sang B |

Kiểm tra bằng exporter/backend thật hoặc môi trường test có khả năng thu spans. Một test chỉ kiểm tra method `Observation` được gọi không đủ chứng minh spans đến được backend hoặc propagation đã hoạt động.

Khi không thấy listener span, xác định đây là do listener chưa chạy, bị sampling loại, context đứt hay exporter lỗi. Đối chiếu với trạng thái event publication và metrics đã bật.

## 19. Kết hợp trace với module graph, Actuator và metrics

| Công cụ | Điều nó xác nhận tốt |
| --- | --- |
| `ApplicationModules.verify()` | Phụ thuộc tĩnh tuân thủ ranh giới module |
| `Documenter` / module graph | Module có những cạnh dependency nào theo thiết kế |
| Actuator/module metadata | Ứng dụng đã triển khai nhận diện module và health ra sao |
| Event metrics/publication state | Event được phát/xử lý/retry/lỗi bao nhiêu lần |
| Trace | Một request/event đã đi qua bước nào và mất bao lâu |
| Context propagation test | Dữ liệu quan sát có nối qua thread/event đúng hay không |

Chẳng hạn, module graph cho thấy `ordering → payment` hợp lệ, metrics báo lỗi payment tăng và một trace lỗi cho thấy `payment.authorize` timeout. Ba nguồn bằng chứng bổ sung nhau. Một trace bị sampling thiếu không thể chứng minh payment không được gọi; một module graph đúng cũng không thể chứng minh provider đang hoạt động.

## 20. Các sai lầm hay gặp

**Span cho mọi method:** tăng nhiễu và chi phí, không tăng khả năng phân biệt lỗi.

**Span thủ công trùng với HTTP/DB auto instrumentation:** cây trace phình ra và khó đọc; chỉ giữ wrapper nếu nó có ý nghĩa nghiệp vụ rộng hơn.

**Đặt tên span bằng orderId hoặc serialized event:** làm tên động, tăng chi phí nhóm dữ liệu và có thể lộ PII.

**Ép event replay vào trace ban đầu:** không phản ánh thời gian và khả năng tách biệt của xử lý sau commit; cân nhắc span link.

**Giả định `@Async` luôn truyền trace:** thread mới cần propagation phù hợp, phải kiểm tra cleanup.

**Coi sampling là bảo mật:** dữ liệu nhạy cảm vẫn có thể được xuất trên trace được giữ.

**Gắn traceId vào Timer:** khiến metrics cardinality tăng theo mỗi request.

**Dùng trace thay metric:** tracing được sampling, không đủ để đếm mọi lỗi/SLO; cần metrics aggregate.

**Chỉ xem trace mà bỏ module graph:** lời gọi runtime thành công không bảo đảm module tuân thủ ranh giới kiến trúc.

## 21. Bài thực hành: chọn spans cho OrderPlaced

**Bối cảnh:** `ordering` gọi `inventory`, `payment`, lưu đơn, phát `OrderPlaced`. `notification` nhận event và gửi email sau commit.

1. Vẽ module graph và chọn các ranh giới quan trọng.
2. Thu một trace hiện hữu; ghi lại spans do Spring Boot/Modulith/HTTP client tự sinh.
3. Đề xuất tối đa các spans thủ công thực sự cần để phân biệt latency và failure modes; giải thích từng span giúp trả lời câu hỏi gì.
4. Chọn một thao tác chỉ cần span event và một thao tác cần listener span.
5. Tạo tình huống payment timeout, có retry, xem thời gian của từng attempt.
6. Cho listener chạy bất đồng bộ, xác minh propagation và chống rò context khi thread tái sử dụng.
7. Thử head sampling trong môi trường test với tỉ lệ đã chọn và phân tích vì sao lỗi hiếm có thể không có trace.
8. Đo spans/trace, volume exporter và kiểm tra không có PII/secret trong attributes.
9. So sánh kết quả trace với event metrics và module graph.
10. Loại một span dư thừa, xem khả năng phân tích latency có thay đổi đáng kể không.

**Câu hỏi tự đánh giá:**

- Vì sao `inventory.reserve` có giá trị hơn hàng chục spans getter?
- Khi nào nên dùng span event thay vì span riêng cho `OrderPlaced.published`?
- Parent-child và span link khác nhau thế nào với event replay sau nhiều phút?
- Vì sao một trace lỗi có thể không xuất hiện dù metrics báo lỗi?
- Vì sao tăng sampling không giải quyết vấn đề lộ token trong attributes?
- Làm sao giữ đủ telemetry cho SLO mà không tạo span theo từng item của batch?

## 22. Checklist trước khi triển khai tracing vào production

- [ ] Đã liệt kê ranh giới application module và các operation nghiệp vụ cần quan sát.
- [ ] Đã kiểm tra spans có sẵn từ Spring Boot, Modulith, HTTP client, JDBC và messaging.
- [ ] Mỗi span thủ công giải quyết được một câu hỏi về lỗi, latency hoặc quan hệ nhân quả.
- [ ] Không tạo span mặc định cho getter, helper hoặc từng item trong vòng lặp lớn.
- [ ] Tên span ổn định, attributes tối thiểu; không chứa raw payload, token hoặc PII.
- [ ] Đã chọn rõ span event cho mốc tức thời và child span cho công việc có duration.
- [ ] Đã thiết kế listener đồng bộ, async, after-commit, retry và replay phù hợp.
- [ ] Context propagation/cleanup đã kiểm tra trên executor và event listener thật.
- [ ] Hiểu rõ giới hạn head/tail sampling và dữ liệu cần được collector nhận.
- [ ] Span count, byte volume, exporter queue/drop rate và collector resources trong ngân sách.
- [ ] Không có trace ID, event ID hoặc customer ID trong low-cardinality metric tags.
- [ ] Cấu trúc trace được giữ đủ để định vị dependency và operation gặp lỗi.
- [ ] Module graph, Actuator và event metrics được đối chiếu độc lập với tracing.
- [ ] Đã thử case thành công, lỗi, timeout, retry, batch và async bằng dữ liệu giả.
- [ ] Có retention, quyền truy cập backend và cách tăng sampling có thời hạn khi điều tra.

**Tiêu chí hoàn thành:** Trace được giữ giúp giải thích **request hoặc event nào** đi qua **module/dependency nào**, **bước nào gây lỗi hoặc tốn thời gian** với số spans và lượng dữ liệu vừa đủ. Tracing cần kết hợp module graph để kiểm chứng ranh giới, Actuator để kiểm tra hệ thống đã triển khai và event metrics để đo hành vi tổng thể; không cần biến mọi method Java thành một span.
