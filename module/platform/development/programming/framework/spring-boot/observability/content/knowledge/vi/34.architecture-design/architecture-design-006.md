# Tách business telemetry và framework telemetry

Một ứng dụng Spring Boot cần hai góc nhìn observability khác nhau. **Business telemetry** cho biết hệ thống đang thực hiện nghiệp vụ gì và kết quả nghiệp vụ ra sao. **Framework telemetry** cho biết ứng dụng, máy chủ và các thành phần kỹ thuật đang xử lý công việc đó như thế nào.

Hai góc nhìn phải liên kết được với nhau trong cùng một lần điều tra sự cố, nhưng cần có tên gọi, ngữ nghĩa, người sở hữu và cách sử dụng rõ ràng. Nếu trộn chúng thành một tập metric không có ranh giới, dashboard dễ phản ánh tình trạng kỹ thuật mà không trả lời được tác động đến người dùng; ngược lại, một chỉ số nghiệp vụ giảm có thể bị quy nhầm cho một thành phần hạ tầng.

Bài này tập trung vào cách đặt ranh giới instrumentation trong Spring Boot với Micrometer Observation, metrics, logs và distributed tracing.

## 1. Hai câu hỏi vận hành khác nhau

Giả sử một dịch vụ xử lý đơn hàng. Một request đi qua HTTP server, controller, use case đặt hàng, repository, connection pool và HTTP client gọi cổng thanh toán.

Trong luồng đó có hai nhóm câu hỏi:

- Góc nhìn nghiệp vụ: Có bao nhiêu đơn được chấp nhận? Tỷ lệ thanh toán bị từ chối tăng hay giảm? Một thao tác đặt hàng mất bao lâu từ lúc bắt đầu đến khi có kết quả nghiệp vụ? Kênh bán hàng nào đang gặp vấn đề?
- Góc nhìn kỹ thuật: HTTP server có đang trả lỗi hoặc tăng độ trễ không? Connection pool còn đủ kết nối không? JVM có pause GC dài không? Request gọi cổng thanh toán có timeout không? Consumer có bị tăng lag không?

Một request trả HTTP 200 không có nghĩa đơn hàng được chấp nhận: cổng thanh toán có thể trả kết quả từ chối hợp lệ và ứng dụng biểu diễn kết quả đó trong response thành công về mặt giao thức. Tương tự, một request HTTP 500 có thể khiến thao tác nghiệp vụ thất bại, nhưng mã HTTP không đủ để phân loại nguyên nhân nghiệp vụ. Vì vậy, không dùng metric HTTP để thay thế metric kết quả nghiệp vụ.

## 2. Xác định ranh giới của từng loại telemetry

**Business telemetry** được tạo tại ranh giới use case hoặc domain operation. Nó diễn tả ý nghĩa mà sản phẩm và nghiệp vụ quan tâm: đơn hàng được tạo, thanh toán được chấp nhận, đặt chỗ bị từ chối, giao dịch hoàn tất hoặc một quy trình hết hạn.

**Framework telemetry** thường được tạo bởi Spring Boot, Actuator, Micrometer và instrumentation của thư viện. Nó mô tả hoạt động của giao thức, runtime và dependency: HTTP server/client, JDBC, connection pool, JVM, thread pool, messaging client và các thành phần nền tảng.

| Khía cạnh | Business telemetry | Framework telemetry |
|---|---|---|
| Đơn vị quan sát | Use case, domain operation, kết quả nghiệp vụ | Request, truy vấn, connection, thread, JVM, client call |
| Câu hỏi chính | Người dùng và quy trình nghiệp vụ đang gặp điều gì? | Ứng dụng và dependency đang vận hành ra sao? |
| Nơi đặt instrumentation | Application service, use case, domain boundary hoặc event handler nghiệp vụ | Spring Boot auto-configuration, web server, client, datasource, runtime |
| Ví dụ metric | `business.orders.outcomes`, `business.order.place` | `http.server.requests`, `http.client.requests`, `jvm.memory.used`, metric của HikariCP |
| Nhãn thường dùng | `outcome`, `channel`, `payment_method` với tập giá trị hữu hạn | `method`, `status`, `uri` đã chuẩn hóa, `exception`, `client_name` |
| Người sử dụng | Product, business owner, application team, on-call | Application, platform, SRE và on-call |
| Dashboard | Tỷ lệ thành công, tỷ lệ từ chối, throughput nghiệp vụ, độ trễ use case | HTTP latency, lỗi dependency, pool saturation, CPU, memory, GC |

Đây là ranh giới theo **ngữ nghĩa và trách nhiệm**, không chỉ theo cách tạo metric. Một custom metric vẫn là framework telemetry nếu nó đo số connection đang mở của một client. Một Observation do lập trình viên tạo vẫn là business telemetry nếu nó bao quanh use case đặt hàng.

Cũng không phải mọi log do ứng dụng ghi đều là business telemetry. Log ghi lỗi kết nối database là tín hiệu kỹ thuật; log ghi nhận một đơn hàng đã được chấp nhận là tín hiệu nghiệp vụ. Hãy phân loại theo điều mà tín hiệu mô tả.

## 3. Đặt instrumentation theo tầng kiến trúc

Spring Boot đã cung cấp instrumentation cho nhiều thành phần phổ biến. Nên giữ các tín hiệu framework ở đúng tầng mà chúng mô tả, sau đó bổ sung business telemetry tại ranh giới use case. Không cần tự tạo lại metric HTTP, JDBC hoặc JVM nếu instrumentation có sẵn đã đáp ứng mục đích vận hành.

Luồng ví dụ:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / HTTP server instrumentation"]
    B --> C["Controller"]
    C --> D["Use case: Place order"]
    D --> E["Business Observation và outcome metric"]
    D --> F["Order repository"]
    F --> G["JDBC / datasource instrumentation"]
    D --> H["Payment gateway client"]
    H --> I["HTTP client instrumentation"]
    E --> J["Metrics, traces và logs backend"]
    G --> J
    I --> J
~~~

Trong luồng này:

- HTTP server instrumentation đo thời gian và trạng thái xử lý request ở tầng web.
- Business Observation đo thời gian của thao tác đặt hàng theo ngữ nghĩa nghiệp vụ.
- JDBC instrumentation đo hoạt động truy cập database.
- HTTP client instrumentation đo lời gọi đến cổng thanh toán.
- Trace liên kết các span theo cùng một trace context, giúp lần theo đường đi của request.

Một use case có thể được gọi từ HTTP, message consumer, scheduler hoặc một use case khác. Nếu chỉ đo tại controller, các luồng không đi qua HTTP sẽ thiếu business telemetry và cùng một nghiệp vụ có thể bị đo khác nhau tùy cách kích hoạt. Đặt Observation tại application service hoặc ranh giới use case giúp ngữ nghĩa ổn định hơn.

Không cần tạo business Observation cho mọi method nội bộ. Chọn các thao tác có ý nghĩa vận hành và có thể diễn giải độc lập, chẳng hạn `business.order.place`, `business.payment.authorize` hoặc `business.reservation.confirm`. Các method getter, mapper hoặc lời gọi tiện ích thường không cần trở thành span hay metric riêng.

## 4. Dùng Micrometer Observation cho thao tác nghiệp vụ

Micrometer Observation cung cấp một abstraction để ghi nhận một thao tác. Tùy các handler đã đăng ký trong `ObservationRegistry`, một Observation có thể tạo metrics, span tracing hoặc được tích hợp với các thành phần khác. Spring Boot có thể cấu hình registry và instrumentation cho các thư viện được hỗ trợ khi có dependency phù hợp.

Ví dụ dưới đây đặt Observation quanh use case đặt hàng. `channel` là giá trị từ enum có tập lựa chọn được kiểm soát; `outcome` mô tả kết quả cuối cùng của use case.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import java.util.Locale;

public class PlaceOrderService {

    private final ObservationRegistry observationRegistry;
    private final MeterRegistry meterRegistry;

    public PlaceOrderService(
            ObservationRegistry observationRegistry,
            MeterRegistry meterRegistry) {
        this.observationRegistry = observationRegistry;
        this.meterRegistry = meterRegistry;
    }

    public OrderResult place(PlaceOrder command) {
        String channel = command.channel()
                .name()
                .toLowerCase(Locale.ROOT);

        Observation observation = Observation
                .createNotStarted("business.order.place", observationRegistry)
                .lowCardinalityKeyValue("channel", channel)
                .start();

        try (Observation.Scope scope = observation.openScope()) {
            OrderResult result = executePlacement(command);

            observation.lowCardinalityKeyValue("outcome", "accepted");
            recordOutcome(channel, "accepted");
            return result;
        } catch (BusinessRuleRejectedException exception) {
            observation.lowCardinalityKeyValue("outcome", "rejected");
            recordOutcome(channel, "rejected");
            throw exception;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            recordOutcome(channel, "error");
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private void recordOutcome(String channel, String outcome) {
        Counter.builder("business.orders.outcomes")
                .tag("channel", channel)
                .tag("outcome", outcome)
                .register(meterRegistry)
                .increment();
    }

    private OrderResult executePlacement(PlaceOrder command) {
        // Thực thi use case: kiểm tra quy tắc, lưu đơn và phối hợp thanh toán.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
~~~

Đây là ví dụ minh họa về vị trí và vòng đời instrumentation; các kiểu `OrderResult`, `PlaceOrder` và `BusinessRuleRejectedException` thuộc mô hình ứng dụng. Trong mã thực tế, hãy bảo đảm việc phân loại `accepted`, `rejected` và `error` phản ánh đúng hợp đồng của use case. Nếu có thêm trạng thái như `pending` hoặc `cancelled`, chỉ thêm khi chúng là các kết quả có ý nghĩa và có tập giá trị được kiểm soát.

Một số điểm cần giữ nhất quán:

1. Observation bao quanh toàn bộ thao tác nghiệp vụ cần đo. Thời gian của nó bao gồm các bước mà use case thực sự chờ để đưa ra kết quả, như kiểm tra quy tắc, truy cập repository và gọi dependency đồng bộ.
2. Outcome được ghi tại điểm đã biết kết quả cuối cùng. Không tăng counter ở đầu request, vì request có thể chưa hoàn tất hoặc có thể bị từ chối trước khi tạo ra kết quả.
3. Counter có cùng tên nhưng phân biệt bằng các tag hữu hạn. Tổng số outcome có thể được truy vấn bằng cách nhóm hoặc lọc theo `outcome` và `channel`.
4. Nếu Observation handler đã xuất timer cho `business.order.place`, không tạo thêm một Timer thủ công cho cùng thao tác chỉ để có cùng dữ liệu. Hai instrumentation trùng nhau làm tăng chi phí và gây nhầm lẫn khi đọc dashboard.
5. Nếu ứng dụng dùng `@Observed` hoặc một cơ chế AOP để tạo Observation, không đồng thời bọc cùng method bằng Observation thủ công. Chọn một cơ chế cho mỗi ranh giới.

`ObservationRegistry` và `MeterRegistry` nên được inject từ cấu hình Spring Boot. Cần có dependency và exporter phù hợp với hệ thống đang dùng; chỉ tạo Observation không tự bảo đảm dữ liệu đã được gửi đến backend nếu registry không có handler hoặc exporter tương ứng.

## 5. Thiết kế metric name và tag có ngữ nghĩa ổn định

Tên metric nên cho biết tín hiệu thuộc miền nào và đo điều gì. Một quy ước dễ đọc là dùng tiền tố `business` cho metric nghiệp vụ do ứng dụng định nghĩa, trong khi giữ tên chuẩn của các instrumentation framework do Spring Boot và Micrometer cung cấp.

Ví dụ:

| Tín hiệu | Tên hoặc nhóm metric | Ý nghĩa |
|---|---|---|
| Kết quả đặt hàng | `business.orders.outcomes` | Số outcome theo kênh và loại kết quả |
| Thời gian đặt hàng | `business.order.place` | Thời gian thực hiện use case |
| HTTP server | `http.server.requests` | Thời gian và trạng thái request ở tầng web |
| HTTP client | `http.client.requests` | Thời gian và trạng thái lời gọi HTTP đi |
| JVM | `jvm.memory.used`, `jvm.gc.pause` | Bộ nhớ và hoạt động garbage collection |
| Connection pool | Các metric HikariCP | Số connection đang hoạt động, nhàn rỗi, chờ và giới hạn pool |

Tên hiển thị trong backend có thể được chuẩn hóa theo naming convention của registry/exporter. Ví dụ, Prometheus thường chuyển dấu chấm trong tên Micrometer thành dấu gạch dưới. Vì vậy, cần phân biệt tên metric trong mã ứng dụng với tên đã được exporter chuyển đổi.

### Low-cardinality và high-cardinality

Với metrics, số lượng chuỗi thời gian tăng theo tổ hợp các tag. Nếu một metric có ba tag với lần lượt 5, 10 và 20 giá trị, nó có thể tạo ra tối đa 1.000 tổ hợp chuỗi thời gian. Thêm một tag chứa hàng trăm nghìn giá trị sẽ làm chi phí lưu trữ, truy vấn và thu thập tăng mạnh.

Tag phù hợp cho business metrics thường là:

- `outcome`: `accepted`, `rejected`, `error`.
- `channel`: `web`, `mobile`, `partner`.
- `payment_method`: `card`, `bank_transfer`, `wallet`, nếu tập giá trị được kiểm soát.
- `region`: mã vùng có danh sách hữu hạn và có ý nghĩa vận hành.

Không đưa các giá trị sau vào metric tag:

- `order_id`, `user_id`, `account_id` hoặc mã giao dịch.
- Email, số điện thoại, token, session ID hay dữ liệu cá nhân.
- URL đầy đủ chứa path variable hoặc query string.
- Nội dung exception, câu SQL, message tùy ý hoặc tên file do người dùng gửi.

`uri` trong metric HTTP cũng cần được chuẩn hóa thành route template, chẳng hạn `/orders/{id}`, thay vì giữ `/orders/928374`. Spring Boot và instrumentation web thường cung cấp route pattern khi framework nhận diện được route; cần kiểm tra cấu hình nếu metric đang xuất hiện URL động.

Micrometer Observation phân biệt low-cardinality và high-cardinality key-value. Low-cardinality values phù hợp để đưa vào metrics. High-cardinality values có thể hữu ích cho span hoặc log khi đã được kiểm soát, nhưng không nên biến chúng thành metric dimension. Ví dụ, mã đơn hàng có thể giúp tìm một trace cụ thể, song phải cân nhắc quyền truy cập, chính sách dữ liệu và khả năng nhận diện cá nhân trước khi đưa vào trace hoặc log. Không mặc định rằng mọi backend đều xử lý high-cardinality attributes giống nhau.

Các resource attributes chung như `service.name`, `deployment.environment`, `service.instance.id` hoặc vùng triển khai có thể dùng để phân biệt dịch vụ và môi trường. Chúng mô tả nơi tín hiệu được phát ra, không thay thế các tag thể hiện kết quả nghiệp vụ.

## 6. Liên kết metrics, logs và traces mà vẫn giữ đúng ý nghĩa

Ba tín hiệu bổ sung cho nhau:

- **Metrics** trả lời xu hướng và mức độ: tỷ lệ chấp nhận đơn, số lỗi, throughput, độ trễ p95/p99, mức sử dụng connection pool.
- **Traces** cho biết một thao tác cụ thể đã đi qua những thành phần nào, mất thời gian ở đâu và span nào phát sinh lỗi.
- **Logs** ghi lại chi tiết có ngữ cảnh tại một thời điểm, như lý do từ chối, mã lỗi nghiệp vụ hoặc thông tin chẩn đoán đã được cho phép.

Business telemetry có thể xuất hiện trên cả ba tín hiệu. Ví dụ, use case đặt hàng tạo một Observation/span `business.order.place`, counter `business.orders.outcomes` và log event `order.placement.completed`. Framework telemetry có thể tạo span HTTP server, JDBC và HTTP client, cùng các metric HTTP, datasource và JVM.

Một log nghiệp vụ có cấu trúc có thể biểu diễn như sau:

~~~json
{
  "event.name": "order.placement.completed",
  "order.channel": "web",
  "order.outcome": "accepted",
  "trace_id": "giá-trị-do-tracing-cung-cấp",
  "span_id": "giá-trị-do-tracing-cung-cấp"
}
~~~

Các trường `trace_id` và `span_id` trong ví dụ là giá trị minh họa. Khi Micrometer Tracing được cấu hình với logging integration tương ứng, trace context có thể được đưa vào MDC để log pattern hoặc structured logging ghi lại tự động. Hãy kiểm tra cấu hình thực tế trước khi giả định các trường này luôn tồn tại.

Log event nên diễn tả sự kiện đã xảy ra, không sao chép toàn bộ request hoặc domain object. Nếu cần tìm một đơn hàng cụ thể, chỉ ghi định danh đã được phê duyệt và bảo vệ bằng chính sách truy cập, retention và masking phù hợp. Không đưa dữ liệu nhạy cảm vào tag metrics hoặc span chỉ vì backend cho phép lưu thuộc tính đó.

Không dùng log làm counter chính. Log có thể bị lọc, sampling, trễ hoặc mất trong pipeline. Metrics phù hợp hơn để tính tỷ lệ và cảnh báo tổng hợp. Ngược lại, không cố đưa mọi chi tiết chẩn đoán vào metric vì metrics có giới hạn về cardinality và không giữ ngữ cảnh của từng lần xảy ra.

## 7. Tổ chức exporter, dashboard và quyền sở hữu

Business telemetry và framework telemetry có thể đi qua cùng `MeterRegistry`, `ObservationRegistry`, OTLP exporter hoặc backend. Việc tách biệt trước tiên nên được thực hiện bằng ngữ nghĩa, naming convention, tag schema, dashboard và ownership.

Một cách tổ chức thực tế:

- Dashboard nghiệp vụ hiển thị số lượng outcome, tỷ lệ chấp nhận/từ chối, throughput và độ trễ use case.
- Dashboard kỹ thuật hiển thị HTTP server/client, JVM, datasource, thread pool, messaging và dependency health.
- Trace view hiển thị cả span business và span framework trong cùng trace để liên kết tác động với nguyên nhân.
- Alert nghiệp vụ cảnh báo khi tỷ lệ thành công hoặc độ trễ use case vượt SLO.
- Alert kỹ thuật cảnh báo khi pool cạn, HTTP client timeout tăng, consumer lag cao hoặc tài nguyên runtime tiến gần giới hạn.

Chỉ tách thành các registry, exporter hoặc tenant riêng khi có yêu cầu cụ thể về bảo mật, retention, chi phí, quyền sở hữu hoặc cách vận hành. Việc chia pipeline quá sớm làm tăng cấu hình, tăng nguy cơ mất liên kết giữa tín hiệu và khiến đội trực phải truy vấn nhiều nơi. Nếu cần tách, hãy xác định rõ tín hiệu nào được gửi đi đâu, resource attributes nào được giữ, trace context được liên kết ra sao và ai chịu trách nhiệm cho từng pipeline.

Không tạo một exporter riêng cho business telemetry chỉ vì tên metric có tiền tố `business`. Tiền tố và schema đã đủ để phân loại trong phần lớn hệ thống. Ranh giới hạ tầng riêng chỉ có giá trị khi giải quyết được một yêu cầu vận hành hoặc quản trị cụ thể.

## 8. Sampling và dữ liệu nghiệp vụ

Metrics thường được tổng hợp theo chu kỳ thu thập và không áp dụng trace sampling theo cách thông thường. Nếu trace sampling chỉ giữ lại một phần request, một trace cụ thể có thể không xuất hiện trong backend dù counter nghiệp vụ vẫn tăng chính xác. Do đó:

- Dùng metrics để theo dõi tổng số, tỷ lệ, xu hướng và SLO.
- Dùng traces được sampling để điều tra đường đi của request và phân tích độ trễ.
- Điều chỉnh sampling policy theo tải, chi phí và mức độ quan trọng của luồng. Có thể ưu tiên giữ trace có lỗi hoặc có đặc điểm cần điều tra nếu tracing backend hỗ trợ cơ chế phù hợp.
- Không coi trace là sổ cái của giao dịch. Nếu nghiệp vụ yêu cầu lưu lại mọi giao dịch, mọi quyết định hoặc bằng chứng kiểm toán, hãy dùng database, audit log hoặc event store có bảo đảm lưu trữ tương ứng.

Đặc biệt với thanh toán, đối soát và giao dịch tài chính, counter và trace phục vụ observability không thay thế dữ liệu giao dịch bền vững. Sampling, retention hoặc lỗi pipeline telemetry không được làm mất bằng chứng nghiệp vụ bắt buộc.

## 9. Dùng hai góc nhìn trong một cuộc điều tra

Giả sử dashboard cho thấy tỷ lệ đơn hàng được chấp nhận giảm từ 98% xuống 84%.

Bắt đầu từ business telemetry để xác nhận phạm vi tác động: outcome nào tăng, kênh nào bị ảnh hưởng, thời điểm bắt đầu và độ trễ use case có thay đổi không. Sau đó chuyển sang framework telemetry để kiểm tra HTTP client của cổng thanh toán, timeout, connection pool, HTTP server và tài nguyên JVM.

Có thể gặp một số tình huống:

| Quan sát | Diễn giải có thể có | Bước kiểm tra tiếp theo |
|---|---|---|
| Tỷ lệ `rejected` tăng, HTTP 5xx không tăng | Nghiệp vụ từ chối hợp lệ hoặc quy tắc nghiệp vụ thay đổi | Phân tích reason code có tập giá trị hữu hạn; đối chiếu thay đổi sản phẩm và provider |
| Tỷ lệ `error` tăng, `http.client.requests` có timeout tăng | Dependency có thể không phản hồi đúng hạn | Mở trace mẫu để xem span gọi dependency, timeout và retry |
| Business latency tăng, DB pool active gần giới hạn | Use case có thể đang chờ connection hoặc truy vấn chậm | Kiểm tra metric pool, JDBC span và truy vấn có liên quan |
| HTTP latency tăng nhưng business latency ổn định | Phần thời gian tăng có thể nằm ngoài use case được đo | Kiểm tra filter, serialization, gateway, network hoặc phần xử lý sau use case |
| Business throughput giảm cùng consumer lag tăng | Luồng xử lý bất đồng bộ có thể bị nghẽn | Kiểm tra consumer framework metrics, tốc độ xử lý và lỗi message |

Các bảng trên chỉ đưa ra hướng điều tra. Một metric đơn lẻ không chứng minh quan hệ nhân quả. Hãy dùng timestamp, service identity, trace context và các dimension tương thích để đối chiếu tín hiệu. Khi không có trace do sampling, metrics vẫn cho biết phạm vi và thời điểm để thu hẹp tìm kiếm.

## 10. Kiểm tra chất lượng instrumentation

Trước khi đưa telemetry vào dashboard và alert, cần xác minh rằng tên, đơn vị, tag và thời điểm ghi nhận đúng với hợp đồng nghiệp vụ.

- Một thao tác nghiệp vụ hoàn tất chỉ làm tăng đúng một outcome counter, kể cả khi có retry ở tầng kỹ thuật.
- Retry của HTTP client không bị hiểu nhầm thành nhiều đơn hàng hoặc nhiều lần hoàn tất use case.
- `accepted`, `rejected` và `error` được định nghĩa rõ; lỗi kỹ thuật không bị gộp với từ chối nghiệp vụ hợp lệ.
- Observation bao quanh đúng ranh giới use case và được dừng trong mọi nhánh thành công hoặc exception.
- Metrics không có tag chứa ID, URL động, email hoặc giá trị không giới hạn.
- Framework metrics vẫn được xuất và giữ tên/ý nghĩa chuẩn sau khi cấu hình exporter.
- Trace có thể nối span business với span HTTP, JDBC hoặc messaging khi cùng một trace context được truyền đúng.
- Log không chứa payload nhạy cảm và có thể liên kết với trace khi tracing được bật.
- Dashboard nghiệp vụ và dashboard kỹ thuật có chủ sở hữu, ngưỡng cảnh báo và cách xử lý rõ ràng.

Có thể dùng `SimpleMeterRegistry` trong unit test để xác minh tên metric, tag và số lần tăng counter. Với Observation, có thể kiểm tra lifecycle bằng registry và handler thử nghiệm phù hợp. Integration test nên xác minh propagation qua các ranh giới HTTP hoặc messaging mà ứng dụng thực sự sử dụng. Không cần kiểm tra chi tiết nội bộ của mọi metric do framework sinh ra trong từng unit test nghiệp vụ; hãy kiểm tra ở cấp cấu hình hoặc integration test phù hợp.

## 11. Những cách làm dễ gây nhầm lẫn

**Dùng HTTP status làm outcome nghiệp vụ.** HTTP status mô tả kết quả giao thức. Một giao dịch bị từ chối có thể được trả về bằng HTTP 200 hoặc 4xx tùy API contract. Hãy ghi outcome tại use case.

**Đặt business metric ở controller.** Cách này bỏ sót các đường gọi từ message, scheduler hoặc use case khác và làm kết quả phụ thuộc vào transport. Đặt metric tại application/domain boundary phù hợp hơn.

**Đưa mã định danh vào metric tag.** Mỗi đơn hàng hoặc người dùng tạo ra một time series mới, làm backend khó vận hành và truy vấn. Dùng dimension hữu hạn cho metrics; chỉ dùng định danh trong trace/log khi được phép và có kiểm soát.

**Tạo metric thủ công trùng với auto-instrumentation.** Metric trùng lặp làm dashboard đếm hai lần hoặc khiến hai nhóm người dùng hiểu khác nhau về cùng một đại lượng. Tận dụng instrumentation framework và chỉ bổ sung tín hiệu mà framework không biết về ngữ nghĩa nghiệp vụ.

**Đo mọi method như một business operation.** Quá nhiều Observation/span làm trace khó đọc và tăng chi phí. Chọn use case hoặc domain operation có ý nghĩa; để framework instrumentation đo các lời gọi kỹ thuật chi tiết.

**Tách exporter chỉ dựa trên tên gọi.** Pipeline riêng làm tăng vận hành mà chưa chắc đem lại lợi ích. Bắt đầu bằng schema và dashboard có ranh giới; chỉ tách hạ tầng khi có yêu cầu rõ ràng.

**Coi telemetry là dữ liệu kiểm toán.** Metrics có tính tổng hợp, traces có sampling và logs có retention. Dữ liệu kiểm toán cần cơ chế lưu trữ và tính toàn vẹn riêng.

## 12. Quy ước kiến trúc nên thống nhất trong nhóm

Một nhóm Spring Boot có thể thống nhất các quy tắc sau để mọi dịch vụ tạo telemetry nhất quán:

1. Giữ framework instrumentation do Spring Boot/Micrometer cung cấp cho HTTP, JVM, database, messaging và client.
2. Đặt business Observation tại ranh giới use case, với tên mô tả hành động nghiệp vụ.
3. Dùng low-cardinality key-value cho các dimension hữu hạn; không đưa định danh hoặc dữ liệu cá nhân vào metric tags.
4. Dùng counter cho outcome nghiệp vụ và Observation/timer cho thời gian xử lý; xác định rõ điểm ghi nhận để tránh đếm trùng khi retry.
5. Dùng structured logs cho sự kiện cần chi tiết và trace context để liên kết; không ghi toàn bộ payload.
6. Giữ business và framework telemetry trong cùng trace khi có thể, nhưng phân loại dashboard, alert và ownership theo mục tiêu sử dụng.
7. Dùng metrics cho SLO và xu hướng; dùng trace sampling cho điều tra; dùng hệ thống lưu trữ nghiệp vụ riêng cho audit.
8. Chỉ thêm pipeline riêng khi có yêu cầu cụ thể về bảo mật, retention, chi phí hoặc trách nhiệm vận hành.

Khi tách đúng hai lớp telemetry, đội sản phẩm có thể biết người dùng đang chịu tác động gì, còn đội kỹ thuật có thể lần từ tác động đó đến thành phần gây ra vấn đề. Micrometer Observation giúp nối hai góc nhìn trong một luồng xử lý; quy ước tên, tag, sampling và ownership giúp dữ liệu vẫn dễ hiểu khi hệ thống phát triển.

