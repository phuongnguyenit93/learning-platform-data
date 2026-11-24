# Không instrument trùng lặp trong Spring Boot Observability

Trong một ứng dụng Spring Boot, cùng một yêu cầu có thể đi qua nhiều lớp và nhiều thư viện đã được instrument sẵn. Nếu mỗi lớp lại tự tạo metric, span hoặc log cho cùng một thao tác, hệ thống quan sát sẽ ghi nhận dữ liệu trùng: số request hoặc thời lượng bị nhân đôi, trace có các span giống nhau, log lặp lại và chi phí thu thập tăng lên. Khi đó dashboard và cảnh báo có thể dẫn đến kết luận sai.

Thiết kế đúng bắt đầu từ việc xác định ranh giới của từng thao tác và chọn một nguồn instrumentation chịu trách nhiệm cho ranh giới đó. Một Observation có thể được nhiều handler chuyển thành các tín hiệu khác nhau; đó là cách một thao tác tạo ra metrics và tracing đồng thời, không phải instrumentation trùng lặp.

## Mục tiêu và nguyên tắc

Với Spring Boot Observability, cần giữ được ba đặc tính:

- Mỗi ranh giới kỹ thuật hoặc thao tác nghiệp vụ có một instrumentation owner rõ ràng.
- Các tín hiệu được tạo từ cùng một Observation phải liên kết với nhau qua trace context và các thuộc tính nhất quán.
- Các span lồng nhau phải thể hiện những công việc khác nhau, có quan hệ nhân quả; không lặp lại cùng một công việc ở cùng một ranh giới.

Có thể dùng quy tắc sau khi thiết kế: **một thao tác, một Observation chủ đạo; nhiều handler có thể xử lý Observation đó**. Không cần tạo riêng một Observation cho metrics và một span cho tracing nếu cả hai cùng mô tả một thao tác.

## Phân biệt nhiều tín hiệu với instrumentation trùng lặp

Micrometer Observation là điểm tích hợp chung. ObservationRegistry nhận Observation; các ObservationHandler phù hợp có thể ghi nhận timer hoặc meter, tạo span qua Micrometer Tracing bridge, và thiết lập context phục vụ tương quan log. Vì vậy, một Observation có thể xuất hiện trong nhiều hệ thống quan sát mà vẫn chỉ có một lần instrument.

| Trường hợp | Có phải trùng lặp? | Cách hiểu |
|---|---|---|
| Một Observation tạo timer và span | Không | Hai tín hiệu mô tả cùng một thao tác và có thể được liên kết. |
| HTTP server span chứa span nghiệp vụ, span HTTP client và span JDBC | Không, nếu mỗi span mô tả một công việc riêng | Đây là quan hệ cha-con theo luồng xử lý. |
| Spring Boot tạo HTTP server Observation và một filter tự tạo thêm Observation cho cùng request | Có thể | Hai instrumentation cùng sở hữu một ranh giới HTTP server. |
| Observation nghiệp vụ và một Timer thủ công đo đúng cùng phương thức | Có thể | Có nguy cơ ghi nhận hai lần cùng một thời lượng hoặc số lần gọi. |
| Micrometer instrumentation và OpenTelemetry Java agent cùng instrument một HTTP client | Có thể | Hai cơ chế có thể tạo hai span cho cùng một lần gọi thư viện. |
| Cùng một metric được gửi qua hai pipeline rồi backend hợp nhất như hai nguồn độc lập | Không phải instrumentation trùng ở ứng dụng, nhưng là trùng ở pipeline | Cần kiểm tra cấu hình export và cách backend nhận diện series. |

Một trace hợp lý có thể có cấu trúc như sau:

~~~text
HTTP request
└── HTTP server Observation
    └── inventory.reserve Observation
        ├── HTTP client Observation
        └── JDBC Observation
~~~

HTTP server, thao tác nghiệp vụ, lời gọi dịch vụ ngoài và truy vấn cơ sở dữ liệu là các ranh giới khác nhau. Các span con giúp xác định thời gian được tiêu thụ ở đâu. Vấn đề chỉ xuất hiện khi hai instrumentation cùng mô tả một ranh giới và một công việc.

## Những nguồn instrumentation cần kiểm kê

Trước khi thêm instrumentation thủ công, hãy xác định những gì ứng dụng đã có. Trong một ứng dụng Spring Boot, các nguồn thường gặp gồm:

1. **Spring Boot và Micrometer**: Actuator, ObservationRegistry, các tích hợp của Spring MVC hoặc WebFlux, HTTP client, datasource và thư viện được hỗ trợ. Những tích hợp thực tế phụ thuộc phiên bản Spring Boot, Micrometer, starter và loại thư viện đang dùng.
2. **Micrometer Tracing bridge**: chuyển Observation sang span và kết nối tracing với hệ sinh thái exporter đang cấu hình.
3. **OpenTelemetry Java agent**: instrument thư viện ở runtime, chẳng hạn HTTP client, JDBC hoặc messaging. Phạm vi cụ thể phụ thuộc phiên bản agent và cấu hình.
4. **Instrumentation do ứng dụng tự viết**: servlet filter, interceptor, aspect, decorator, wrapper, Timer thủ công hoặc Observation tạo trực tiếp trong service.
5. **Annotation và AOP**: các annotation như @Observed hoặc @Timed có thể được xử lý bởi aspect nếu ứng dụng đã bật cơ chế tương ứng.

Hãy ghi lại ranh giới mà mỗi nguồn đang sở hữu. Đừng kết luận rằng một thư viện chắc chắn đã được instrument chỉ dựa trên tên dependency; cần kiểm tra phiên bản, cấu hình và dữ liệu thực tế của ứng dụng.

| Ranh giới | Nguồn nên kiểm tra trước | Khi nào cần bổ sung thủ công |
|---|---|---|
| HTTP request đi vào ứng dụng | Observation của Spring Web và cấu hình Actuator | Khi cần một thao tác nghiệp vụ riêng, không phải đo lại toàn bộ request |
| HTTP request đi ra ngoài | Observation của RestClient, WebClient hoặc client tương ứng; Java agent nếu có | Khi cần đo một nghiệp vụ bao quanh lời gọi, với tên và ý nghĩa khác |
| Truy cập JDBC | Instrumentation của datasource hoặc Java agent | Khi cần đo một nghiệp vụ dữ liệu cấp cao, không tạo lại span cho từng câu SQL |
| Xử lý nghiệp vụ | Observation do ứng dụng định nghĩa | Khi ranh giới nghiệp vụ có ý nghĩa và chưa được đo ở nơi khác |
| Tương quan log | Trace context và MDC do tracing integration quản lý | Khi cần thêm trường nghiệp vụ hữu hạn, không tạo log lifecycle trùng lặp |

## Thiết kế để mỗi ranh giới có một owner

### 1. Giữ instrumentation tự động ở các ranh giới thư viện

Nếu Spring Boot đã tạo Observation cho HTTP server, hãy tận dụng Observation đó để đo request. Tránh thêm một filter chỉ để tạo một timer hoặc span khác có cùng ý nghĩa. Nếu cần bổ sung tên route, nhóm endpoint hoặc thuộc tính, ưu tiên mở rộng convention hoặc cơ chế tùy biến Observation hiện có.

Tương tự, khi HTTP client hoặc datasource đã được instrument, không tạo thêm một span có tên và phạm vi tương đương quanh chính lời gọi thư viện. Hãy kiểm tra trace trước để biết span hiện có mang thông tin gì và còn thiếu điều gì.

### 2. Dành instrumentation thủ công cho ranh giới nghiệp vụ

Instrumentation tự động thường mô tả ranh giới kỹ thuật: nhận HTTP request, gọi HTTP client, truy vấn JDBC. Ứng dụng có thể bổ sung Observation cho thao tác nghiệp vụ có ý nghĩa riêng, chẳng hạn giữ chỗ tồn kho, tính phí hoặc xác nhận đơn hàng.

Ví dụ sau tạo một Observation cho nghiệp vụ giữ chỗ. ObservationRegistry được Spring Boot cấu hình và có thể có các handler cho metrics và tracing:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final ObservationRegistry observationRegistry;

    public InventoryService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public Reservation reserve(String sku, String warehouse) {
        return Observation.createNotStarted(
                        "inventory.reserve",
                        observationRegistry
                )
                .lowCardinalityKeyValue("warehouse", warehouse)
                .observe(() -> reserveInternal(sku, warehouse));
    }

    private Reservation reserveInternal(String sku, String warehouse) {
        // Thực hiện quy tắc và cập nhật tồn kho.
        return new Reservation(sku, warehouse);
    }
}
~~~

Observation nghiệp vụ này không thay thế HTTP server Observation hay JDBC Observation. Nó bổ sung một góc nhìn có tên và phạm vi khác. Khi lời gọi bên trong đi tới datasource đã instrument, span JDBC có thể trở thành span con trong cùng trace.

Chỉ đưa vào low-cardinality key những giá trị có tập hữu hạn và được kiểm soát, ví dụ loại thao tác, kết quả đã chuẩn hóa hoặc vùng triển khai. Không dùng SKU, order ID, user ID hay URL chứa ID động làm metric tag. Nếu cần giá trị định danh để điều tra trace, hãy cân nhắc high-cardinality attribute và chính sách dữ liệu phù hợp; loại thuộc tính này không nên biến thành nhãn metric.

### 3. Không bọc lại cùng phương thức bằng nhiều cơ chế

Một phương thức có thể bị instrument nhiều lần nếu vừa có annotation được aspect xử lý, vừa tự tạo Observation bên trong. Ví dụ, khi ObservedAspect đã được bật, đặt @Observed trên phương thức rồi lại tạo Observation cùng tên trong thân phương thức có thể tạo hai Observation lồng nhau cho cùng một thao tác.

Tình huống tương tự xảy ra khi kết hợp @Timed, Timer thủ công và Observation có meter handler. Trước khi giữ nhiều cơ chế, hãy xác định từng cơ chế đo điều gì. Nếu chúng đều đo cùng số lần gọi hoặc cùng thời lượng, hãy chọn một cơ chế làm nguồn chuẩn.

### 4. Không tạo Timer thủ công nếu Observation đã ghi nhận metric đó

Ví dụ dưới đây có nguy cơ ghi nhận hai lần thời lượng của inventory.reserve nếu ObservationRegistry đang có meter handler tạo timer tương ứng:

~~~java
public Reservation reserve(String sku, String warehouse) {
    Timer.Sample sample = Timer.start(meterRegistry);
    try {
        return Observation.createNotStarted(
                        "inventory.reserve",
                        observationRegistry
                )
                .observe(() -> reserveInternal(sku, warehouse));
    } finally {
        sample.stop(meterRegistry.timer("inventory.reserve"));
    }
}
~~~

Ở đây Observation có thể đã tạo meter, trong khi Timer.Sample lại ghi một timer khác cho cùng lời gọi. Cách đơn giản hơn là để Observation làm nguồn ghi nhận:

~~~java
public Reservation reserve(String sku, String warehouse) {
    return Observation.createNotStarted(
                    "inventory.reserve",
                    observationRegistry
            )
            .lowCardinalityKeyValue("warehouse", warehouse)
            .observe(() -> reserveInternal(sku, warehouse));
}
~~~

Nếu cần metric có quy tắc tổng hợp khác, hãy thiết kế tên metric, đơn vị, tag và mục đích riêng; xác minh rằng nó không đo lại cùng một đại lượng dưới cùng ý nghĩa. Trường hợp thật sự cần Timer độc lập phải được giải thích rõ và có kiểm thử để tránh dashboard cộng hoặc so sánh nhầm hai đại lượng.

### 5. Tránh hai agent cùng instrument một thư viện

OpenTelemetry Java agent có thể tự instrument các thư viện mà Micrometer hoặc Spring Boot cũng hỗ trợ. Khi cả hai cùng bật instrumentation cho cùng một HTTP client hoặc JDBC driver, trace có thể xuất hiện các span gần như giống hệt nhau.

Cần chọn một cơ chế làm owner cho từng thư viện hoặc ranh giới. Có thể tiếp tục dùng Spring Boot/Micrometer cho các tích hợp của ứng dụng và tắt có chọn lọc instrumentation tương ứng của agent, hoặc chọn agent cho ranh giới đó và tránh tạo span thủ công trùng phạm vi. Cấu hình tắt/bật cụ thể phụ thuộc phiên bản agent và thư viện, vì vậy hãy kiểm tra tài liệu của phiên bản đang chạy trước khi thay đổi.

Không nên tắt toàn bộ agent hay toàn bộ Observation chỉ vì thấy một cặp span trùng. Hãy xác định đúng instrumentation nào tạo span dư, sau đó điều chỉnh ở phạm vi nhỏ nhất có thể.

## Tùy biến instrumentation hiện có

Khi instrumentation hiện tại đã đo đúng ranh giới nhưng thiếu thuộc tính, hãy bổ sung thông tin vào nó thay vì tạo một instrumentation mới.

Các hướng thường dùng:

- Dùng ObservationConvention hoặc convention chuyên biệt của Spring để chuẩn hóa tên và key-value cho Observation đã có.
- Dùng cơ chế tùy biến ObservationRegistry hoặc ObservationFilter khi cần áp dụng quy tắc chung.
- Bổ sung thuộc tính nghiệp vụ có tập giá trị hữu hạn để phân nhóm metric.
- Dùng trace context và MDC để liên kết log với trace, thay vì tự tạo một span chỉ nhằm lấy trace ID.
- Chuẩn hóa route template thay cho URL đầy đủ có ID động.

Tên Observation cần mô tả công việc và có quy ước nhất quán. Ví dụ, inventory.reserve mô tả thao tác nghiệp vụ; HTTP client Observation mô tả lời gọi ra ngoài. Tránh đặt cùng một tên chung cho mọi lớp, vì khi đọc trace sẽ khó biết mỗi span đại diện cho công việc nào.

## Kiểm tra dấu hiệu trùng lặp

Có thể phát hiện instrumentation dư bằng cách đối chiếu cả trace, metrics và logs.

**Trong trace:**

- Tìm hai span có cùng tên, cùng span kind, cùng thuộc tính và thời gian bắt đầu gần như đồng thời.
- Kiểm tra hai span có cùng bao phủ một lời gọi HTTP, câu truy vấn hoặc request hay không.
- Xem quan hệ parent-child. Hai span lồng nhau chỉ hợp lý khi span con đại diện cho một bước riêng; hai span cùng mô tả một lời gọi có thể là dấu hiệu trùng.
- Kiểm tra instrumentation scope hoặc thông tin thư viện tạo span nếu exporter/backend có hiển thị.

**Trong metrics:**

- So sánh số request trước và sau khi bật một agent hoặc aspect.
- Tìm các metric có cùng ý nghĩa, cùng đơn vị và cùng bộ tag nhưng được tạo từ hai nguồn.
- Kiểm tra metric count hoặc duration tăng gần gấp đôi sau khi thêm instrumentation.
- Phân biệt việc đo hai đại lượng khác nhau với việc ghi cùng một đại lượng hai lần.

**Trong logs:**

- Kiểm tra cùng một sự kiện nghiệp vụ có bị ghi ở filter, aspect và service hay không.
- Kiểm tra log có trace ID và span ID đúng với trace hiện hành.
- Tránh ghi log start/stop ở nhiều lớp nếu những dòng đó không bổ sung thông tin điều tra.

Một dấu hiệu đơn lẻ chưa đủ kết luận. Chẳng hạn, hai span cùng tên có thể đến từ hai lần retry hợp lệ. Hãy đối chiếu parent span, thời điểm, thuộc tính, số lần thử và mã nguồn instrumentation trước khi tắt một nguồn.

## Quy trình quyết định trước khi thêm instrumentation

1. **Xác định câu hỏi cần trả lời.** Cần biết thời gian của HTTP request, lời gọi dịch vụ ngoài, truy vấn DB hay một nghiệp vụ như giữ chỗ tồn kho?
2. **Xác định ranh giới hiện đã được đo.** Kiểm tra cấu hình Spring Boot, Micrometer, agent, annotation/aspect và trace thực tế.
3. **Chọn owner.** Với ranh giới thư viện, ưu tiên tích hợp đã có. Với ranh giới nghiệp vụ chưa được biểu diễn, tạo một Observation nghiệp vụ.
4. **Tái sử dụng Observation hiện tại khi chỉ cần thêm metadata.** Dùng convention hoặc filter thay vì tạo span mới cùng phạm vi.
5. **Kiểm tra cardinality.** Metric tag phải có tập giá trị hữu hạn; dữ liệu định danh không được đưa vào low-cardinality tag.
6. **Xác minh sau thay đổi.** So sánh trace, số lần ghi metric và log trước/sau. Một thao tác mẫu phải tạo đúng số span và metric dự kiến.

## Kiểm thử và tiêu chí hoàn thành

Nên có kiểm thử ở cấp tích hợp cho những ranh giới quan trọng. Với một request đi qua controller, service và repository, xác minh rằng:

- HTTP server được ghi nhận một lần.
- Observation nghiệp vụ chỉ xuất hiện một lần cho mỗi lần thực hiện nghiệp vụ.
- HTTP client hoặc JDBC span chỉ xuất hiện khi có lời gọi tương ứng và không bị tạo đôi bởi agent cùng instrumentation của ứng dụng.
- Metrics được tạo từ Observation có tên, đơn vị và tag như dự kiến.
- Khi nghiệp vụ phát sinh exception, Observation vẫn kết thúc đúng vòng đời và lỗi được ghi nhận.
- Log có thể tương quan với trace mà không phát sinh nhiều log lifecycle giống nhau.

Có thể dùng registry hoặc exporter dành cho kiểm thử để thu thập Observation, meter và span trong môi trường test. Không nên chỉ kiểm tra rằng “có dữ liệu”; cần kiểm tra số lượng, tên, quan hệ cha-con và các thuộc tính chính. Khi nâng phiên bản Spring Boot, Micrometer hoặc Java agent, chạy lại các kiểm thử này vì phạm vi auto-instrumentation có thể thay đổi.

Một thiết kế đạt yêu cầu khi mỗi ranh giới có owner rõ ràng, trace thể hiện các bước xử lý thực sự khác nhau, metrics không bị ghi nhận hai lần và log vẫn liên kết được với trace. Điều này giúp số liệu phản ánh đúng hành vi ứng dụng và giúp nhóm phát triển điều tra lỗi, độ trễ cũng như hành vi production một cách tin cậy.

