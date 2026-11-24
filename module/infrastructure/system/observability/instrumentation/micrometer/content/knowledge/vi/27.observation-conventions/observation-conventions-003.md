# Chọn thông tin đưa vào metric hoặc ngữ cảnh phục vụ trace

## Một Observation có thể mang hai loại thông tin

Micrometer Observation mô tả một hoạt động có vòng đời, chẳng hạn xử lý request, thanh toán, tra cứu sản phẩm hoặc gửi message. Observation có thể được nhiều handler xử lý: handler metrics chuyển thông tin phù hợp thành meter và tag; handler tracing chuyển thông tin phù hợp thành span và span attributes.

Vì một Observation có thể phục vụ cả metrics lẫn traces, cần phân biệt hai nhóm thuộc tính:

- **Low-cardinality key-value:** các chiều phân loại có tập giá trị hữu hạn, ổn định, phù hợp để đưa vào metrics như tag.
- **High-cardinality key-value:** thông tin chi tiết có thể có rất nhiều giá trị khác nhau, phù hợp hơn với ngữ cảnh trace khi thực sự cần.

Một metric thường được tổng hợp qua hàng nghìn hoặc hàng triệu lần thực thi. Nếu mỗi lần thực thi tạo một tag value mới, số time series tăng theo lượng request và gây áp lực lên bộ nhớ, ingest, truy vấn và chi phí lưu trữ. Trace lại mô tả từng lần thực thi riêng, nên có thể giữ một số thuộc tính chi tiết hơn để tìm một request cụ thể.

Điều đó không có nghĩa mọi dữ liệu duy nhất đều nên đưa vào trace. Trace vẫn được lưu trữ, truy vấn và chia sẻ qua hệ thống quan sát; dữ liệu nhạy cảm, bí mật xác thực hoặc thông tin cá nhân không cần thiết phải được loại bỏ hoặc che trước khi tạo telemetry.

## Metric dimensions và span attributes trả lời hai câu hỏi khác nhau

Metrics trả lời câu hỏi về xu hướng và tổng hợp: dịch vụ có bao nhiêu request, tỷ lệ lỗi là bao nhiêu, độ trễ p95 ra sao, queue đang sâu đến mức nào. Để so sánh các nhóm, metric cần các dimension có số giá trị giới hạn và có ý nghĩa tổng hợp.

Traces trả lời câu hỏi về một lần thực thi: request cụ thể đi qua thành phần nào, span nào chậm, lỗi phát sinh ở bước nào. Span attributes có thể chứa thêm ngữ cảnh để tìm và phân tích một trace, miễn là dữ liệu đó an toàn và có ích.

| Thông tin | Metric tag / low-cardinality | Trace attribute / high-cardinality |
|---|---|---|
| HTTP method | GET, POST, PUT, DELETE | Có thể có nhưng thường không cần lặp lại nếu đã có thuộc tính chuẩn |
| Route | /orders/{id}, /products/{id} | Có thể giữ route template và thông tin bổ sung an toàn |
| Outcome | success, failure, timeout | Có thể ghi outcome và error type |
| Region | ap-southeast-1, eu-west-1 | Có thể ghi cùng resource hoặc span context |
| Payment method | card, wallet, bank_transfer | Có thể ghi chi tiết phương thức nếu cần và an toàn |
| Order ID | Không dùng làm metric tag | Chỉ ghi nếu thật sự cần tra cứu và được phép |
| User ID | Không dùng làm metric tag | Thường nên tránh; nếu có yêu cầu hợp lệ, dùng định danh giả danh và chính sách truy cập phù hợp |
| Trace ID / Span ID | Không dùng làm metric tag | Được tracing system quản lý, không cần tự thêm thành metric dimension |
| Exception message | Không dùng làm metric tag | Thường tránh vì chứa dữ liệu động hoặc nhạy cảm; ưu tiên error type có giới hạn |

Một thông tin có thể xuất hiện ở cả hai loại nếu nó thực sự cần cho cả hai mục tiêu. Ví dụ outcome=success có thể là metric tag và span attribute. Nhưng order ID thường chỉ hữu ích để tìm một giao dịch cụ thể, không phải để nhóm metrics.

## Low-cardinality: chọn dimension hữu hạn

### Dùng cho nhóm có ý nghĩa vận hành

Low-cardinality key-value nên mô tả các nhóm ổn định mà đội vận hành muốn so sánh. Ví dụ:

- operation: create, update, cancel, lookup.
- outcome: success, failure, timeout.
- method: GET, POST, PUT, DELETE.
- status: 2xx, 4xx, 5xx hoặc nhóm trạng thái đã định nghĩa.
- payment.type: card, wallet, bank_transfer.
- region: tập vùng triển khai đã cấu hình.
- cache.name: tập cache cố định của ứng dụng.

Một chiều có số giá trị nhỏ chưa chắc đã hữu ích. Chỉ thêm tag nếu nó giúp trả lời câu hỏi vận hành hoặc nghiệp vụ cụ thể. Mỗi tag bổ sung làm số series tăng theo tổ hợp với các tag khác.

Ví dụ một Timer có 4 giá trị method, 3 giá trị outcome và 5 region có thể tạo tối đa 4 × 3 × 5 = 60 tổ hợp tag cho mỗi meter name, trước khi tính các chuỗi histogram hoặc các meter khác.

### Đặt tên giá trị ổn định

Giá trị tag nên được chuẩn hóa. Không để cùng một trạng thái có nhiều cách viết như success, SUCCESS, ok và completed nếu chúng mang cùng ý nghĩa. Không dùng thông điệp lỗi hoặc tên class tự do làm outcome.

Nên ánh xạ trạng thái nội bộ sang một tập giá trị có giới hạn:

~~~java
static String outcomeFor(Throwable error) {
    if (error == null) {
        return "success";
    }
    if (error instanceof TimeoutException) {
        return "timeout";
    }
    return "failure";
}
~~~

Nếu cần phân tích loại lỗi, có thể dùng một tập error type đã chuẩn hóa như timeout, validation, dependency hoặc internal. Tránh dùng exception message vì nội dung thường khác nhau theo request và có thể chứa dữ liệu đầu vào.

### Dùng route template thay cho URL đầy đủ

Với HTTP server metrics, route template như /orders/{id} có cardinality thấp hơn nhiều so với URL thực tế /orders/12345. Nếu dùng URL đầy đủ làm tag, mỗi resource ID có thể tạo một time series riêng.

Nên ưu tiên route pattern do framework cung cấp, hoặc chuẩn hóa route thành nhóm endpoint ổn định. Nếu route không xác định, dùng một giá trị dự phòng có giới hạn như UNKNOWN thay vì ghi raw path.

## High-cardinality: chỉ giữ trong trace khi có mục đích

High-cardinality key-value phù hợp với thông tin giúp điều tra một lần thực thi cụ thể. Ví dụ reference đã được giả danh, loại dependency chi tiết hoặc một thuộc tính định danh không nhạy cảm có thể giúp tìm trace.

Tuy nhiên, cần trả lời trước khi thêm:

1. Thuộc tính có thực sự giúp tìm hoặc hiểu trace không?
2. Có thể tìm thông tin đó qua log hoặc hệ thống nghiệp vụ an toàn hơn không?
3. Giá trị có chứa dữ liệu cá nhân, bí mật hoặc dữ liệu thanh toán không?
4. Backend trace có quyền truy cập và retention phù hợp không?
5. Có cần lưu giá trị đầy đủ hay chỉ một dạng đã chuẩn hóa/giả danh?

Không đưa access token, session cookie, password, số thẻ, email, địa chỉ hoặc nội dung request đầy đủ vào Observation context. High-cardinality chỉ mô tả khả năng có nhiều giá trị; nó không phải cơ chế phân loại dữ liệu hay quyền cho phép thu thập.

### Ví dụ gắn thuộc tính có chọn lọc

~~~java
Observation.createNotStarted(
        "payment.authorize",
        observationRegistry
    )
    .lowCardinalityKeyValue("payment.type", "card")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("payment.reference", safeReference)
    .observe(() -> paymentService.authorize(command));
~~~

Trong ví dụ, payment.type và outcome phù hợp để tổng hợp metrics. safeReference chỉ nên được đưa vào trace khi đã được kiểm tra là an toàn, cần thiết và không cho phép suy ra dữ liệu nhạy cảm.

Không nên thêm payment.reference vào low-cardinality chỉ để truy vấn metric cho một giao dịch. Hãy dùng trace search, log correlation hoặc hệ thống nghiệp vụ để tra cứu từng giao dịch.

## Đưa thuộc tính vào Observation

### Thêm low và high cardinality key-value trực tiếp

Observation API cho phép bổ sung các thuộc tính trước khi bắt đầu lifecycle:

~~~java
Observation observation = Observation.createNotStarted(
    "order.submit",
    observationRegistry
);

observation.lowCardinalityKeyValue("channel", "web");
observation.lowCardinalityKeyValue("outcome", "success");
observation.highCardinalityKeyValue("order.reference", safeOrderReference);

OrderResult result = observation.observe(
    () -> orderService.submit(command)
);
~~~

Các low-cardinality values có thể được dùng làm metric dimensions bởi handler metrics và cũng có thể xuất hiện trong trace theo convention. High-cardinality values được dành cho handler tracing hoặc handler khác có khả năng giữ thông tin chi tiết; chúng không nên trở thành tag của metrics.

Nên bổ sung low-cardinality values trước khi gọi observe để handler nhận được chúng trong quá trình bắt đầu. Nếu giá trị outcome chỉ biết sau khi khối mã hoàn tất, hãy dùng context/convention hoặc cập nhật thuộc tính theo API và thời điểm handler hỗ trợ. Không gắn outcome mặc định là success trước khi thao tác thực sự thành công.

### Tạo context riêng cho một loại Observation

Khi một nhóm Observation có nhiều thuộc tính và logic phân loại, có thể tạo context chuyên biệt:

~~~java
public final class PaymentObservationContext extends Observation.Context {

    private final String paymentType;
    private final String outcome;
    private final String safeReference;

    public PaymentObservationContext(
            String paymentType,
            String outcome,
            String safeReference
    ) {
        this.paymentType = paymentType;
        this.outcome = outcome;
        this.safeReference = safeReference;
    }

    public String paymentType() {
        return paymentType;
    }

    public String outcome() {
        return outcome;
    }

    public String safeReference() {
        return safeReference;
    }
}
~~~

Context giúp tách dữ liệu của hoạt động khỏi code tạo Observation. Convention có thể đọc context này và quyết định thuộc tính nào được đưa vào metrics hoặc traces.

Không nên nhồi mọi object nghiệp vụ vào context. Chỉ giữ các giá trị cần cho convention và handler; tránh giữ object lớn hoặc tham chiếu làm kéo dài vòng đời dữ liệu.

## Chuẩn hóa bằng ObservationConvention

### Convention tập trung hóa tên và thuộc tính

ObservationConvention cho phép định nghĩa quy tắc dùng chung cho một loại Observation. Convention có thể quyết định:

- Tên Observation.
- Contextual name nếu cần cho trace.
- Low-cardinality key-values.
- High-cardinality key-values.
- Context nào mà convention hỗ trợ.

Nhờ đó, các component không phải tự tạo tag và span attributes theo cách khác nhau. Convention cũng giúp thay đổi quy tắc phân loại ở một nơi và kiểm thử tập trung.

Ví dụ convention cho payment:

~~~java
public final class PaymentObservationConvention
        implements ObservationConvention<PaymentObservationContext> {

    @Override
    public boolean supportsContext(PaymentObservationContext context) {
        return true;
    }

    @Override
    public String getName() {
        return "payment.authorize";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            PaymentObservationContext context
    ) {
        return KeyValues.of(
            KeyValue.of("payment.type", context.paymentType()),
            KeyValue.of("outcome", context.outcome())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            PaymentObservationContext context
    ) {
        return KeyValues.of(
            KeyValue.of("payment.reference", context.safeReference())
        );
    }
}
~~~

Các API và package cụ thể cần đối chiếu phiên bản Micrometer đang dùng. Ý tưởng quan trọng là convention phân loại thuộc tính theo nơi tiêu thụ; không gom mọi thuộc tính vào một danh sách tag duy nhất.

Có thể tạo Observation với convention và context supplier:

~~~java
PaymentObservationContext context =
    new PaymentObservationContext("card", "success", safeReference);

Observation.createNotStarted(
        new PaymentObservationConvention(),
        () -> context,
        observationRegistry
    )
    .observe(() -> paymentService.authorize(command));
~~~

Trong dự án thực tế, context thường được tạo sau khi có đủ dữ liệu để phân loại. Nếu outcome chỉ xác định được sau khi xử lý, có thể cập nhật context trước khi stop theo lifecycle phù hợp hoặc thiết kế convention dựa trên trạng thái cuối cùng. Tránh đóng băng outcome sai ở thời điểm bắt đầu.

### Contextual name và metric name

Tên Observation nên ổn định, mô tả loại hoạt động, ví dụ payment.authorize hoặc order.submit. Contextual name có thể cung cấp tên dễ đọc hơn cho span, nhưng không nên chứa ID duy nhất hoặc dữ liệu request.

Metric name và span name có mục đích khác nhau. Metric name phải ổn định để tổng hợp; span name phải mô tả thao tác và không tạo quá nhiều dạng tên động. Convention giúp giữ hai quy tắc này nhất quán nhưng vẫn cho phép handler diễn giải khác nhau.

## Handler metrics và tracing sử dụng thuộc tính ra sao?

ObservationRegistry điều phối Observation đến các ObservationHandler đã đăng ký. Handler metrics có thể tạo Timer và đưa low-cardinality key-values thành meter tags. Handler tracing có thể tạo span và đưa thêm high-cardinality values thành span attributes.

Không nên giả định mọi handler đều xuất mọi thuộc tính. Việc ánh xạ phụ thuộc handler, convention, filter và phiên bản thư viện. Nếu một thuộc tính không xuất hiện ở backend, hãy kiểm tra handler cụ thể và dữ liệu exposition thay vì kết luận Observation API đã bỏ thuộc tính.

### Metrics cần giới hạn dimension

Metrics backend thường tạo series theo tổ hợp tên metric và label. Với mỗi dimension mới, số tổ hợp có thể tăng theo phép nhân. Nếu một Timer có:

- 4 giá trị method.
- 3 giá trị outcome.
- 5 giá trị region.
- 20 bucket histogram.

Số series histogram có thể xấp xỉ 4 × 3 × 5 × 20 = 1.200 cho một metric và một service instance, chưa tính count, sum, max hoặc resource dimensions. Khi nhân với nhiều service instance và nhiều metric, chi phí tăng nhanh.

Vì vậy, metrics chỉ nên nhận các chiều có giá trị tổng hợp. Dùng MeterFilter để giới hạn tag hoặc số meter có thể là lớp bảo vệ bổ sung, nhưng không thay thế việc chọn thuộc tính đúng ngay từ ObservationConvention.

### Traces có thể giữ chi tiết nhưng vẫn cần kiểm soát

Trace backend có thể lưu nhiều span attributes, nhưng số lượng span, kích thước mỗi span, index fields và thời gian retention đều có chi phí. Thuộc tính high-cardinality chỉ nên được giữ khi có use case tìm kiếm hoặc điều tra cụ thể.

Một trace có hàng trăm thuộc tính không giúp điều tra tốt hơn nếu không ai truy vấn chúng. Hãy ưu tiên các thuộc tính giải thích operation, dependency, outcome, retry hoặc lỗi; loại bỏ payload và dữ liệu không liên quan.

Sampling có thể làm một số trace không xuất hiện, nhưng không nên dùng sampling như biện pháp bảo vệ dữ liệu nhạy cảm. Dữ liệu phải được lọc trước khi được thêm vào Observation.

## Exemplar liên kết metrics với trace

Một số registry và backend hỗ trợ exemplar để gắn tham chiếu trace vào một observation metric hoặc histogram sample. Exemplar cho phép chuyển từ điểm bất thường trên metric sang trace mẫu mà không cần thêm trace ID làm metric tag.

Cơ chế này phụ thuộc registry, exporter, backend và cấu hình context propagation. Không phải mọi backend đều hỗ trợ hoặc hiển thị exemplar mặc định.

Khi exemplar được hỗ trợ:

- Metric vẫn dùng các dimension có cardinality thấp.
- Trace ID được gắn vào exemplar của sample phù hợp.
- Người vận hành có thể mở trace liên quan từ biểu đồ metric.
- Số time series không tăng theo số trace ID.

Không tự tạo tag trace_id để mô phỏng exemplar. Điều đó làm cardinality tăng theo từng trace và phá vỡ khả năng tổng hợp metrics.

## Chọn thuộc tính theo từng tình huống

| Tình huống | Nên đưa vào metrics | Có thể đưa vào trace nếu cần |
|---|---|---|
| HTTP request | method, route template, status class, outcome | route, error type, client/server details |
| Thanh toán | payment type, outcome, provider group | safe transaction reference, dependency details |
| Database | operation, database system, pool name | statement type, sanitized query metadata |
| Message processing | destination group, outcome, consumer group | message reference đã giả danh, delivery attempt |
| Cache | cache name, operation, result hit/miss | key category hoặc metadata an toàn |
| Batch processing | job type, outcome, batch size bucket | job reference đã giả danh, bước xử lý chi tiết |

Với SQL, không đưa câu query đầy đủ chứa literal hoặc dữ liệu người dùng vào metrics hoặc traces nếu không có chính sách làm sạch. Dùng operation name, statement type hoặc query fingerprint đã được chuẩn hóa khi thực sự cần.

Với message, không đưa payload vào span attributes. Nếu cần điều tra message cụ thể, dùng message ID đã được giả danh hoặc cơ chế tra cứu an toàn ở hệ thống nghiệp vụ.

## Kiểm thử convention và thuộc tính xuất ra

### Kiểm thử low/high cardinality ở convention

Có thể viết unit test cho convention để xác nhận tên và tập key-value:

~~~java
PaymentObservationConvention convention =
    new PaymentObservationConvention();

PaymentObservationContext context =
    new PaymentObservationContext("card", "success", "ref-123");

assertThat(convention.getName()).isEqualTo("payment.authorize");

assertThat(convention.getLowCardinalityKeyValues(context))
    .contains(
        KeyValue.of("payment.type", "card"),
        KeyValue.of("outcome", "success")
    );

assertThat(convention.getHighCardinalityKeyValues(context))
    .contains(KeyValue.of("payment.reference", "ref-123"));
~~~

Test cần xác nhận không có ID duy nhất trong low-cardinality set. Có thể kiểm tra tập giá trị cho từng key được giới hạn bằng enum hoặc mapping rõ ràng.

### Kiểm tra meter tags

Dùng ObservationRegistry có metrics handler và SimpleMeterRegistry trong test, thực thi Observation rồi kiểm tra Timer được tạo với đúng tag. Cần dùng đúng convention và handler tương ứng với phiên bản Micrometer.

~~~java
Timer timer = registry.find("payment.authorize")
    .tag("payment.type", "card")
    .tag("outcome", "success")
    .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
~~~

Nếu handler dùng tên meter hoặc tag convention khác, hãy xác minh từ MeterRegistry thay vì giả định tên. Test phải chứng minh high-cardinality value không xuất hiện như metric tag.

### Kiểm tra span attributes

Với tracing test, dùng in-memory span exporter hoặc test span handler để xác minh:

- Span name ổn định.
- Low-cardinality attributes cần thiết xuất hiện.
- High-cardinality attributes an toàn xuất hiện khi được cấu hình.
- ID duy nhất không bị đưa vào metric tags.
- Dữ liệu nhạy cảm bị loại bỏ hoặc che.
- Context và parent-child relationship được giữ đúng.

Không chỉ kiểm tra convention object. Hãy kiểm tra payload thực tế mà handler tạo ra vì convention có thể được filter, transform hoặc kết hợp với thuộc tính từ instrumentation khác.

### Kiểm tra cardinality

Có thể chạy một workload với nhiều ID khác nhau nhưng cùng operation/outcome. Kỳ vọng:

- Số meter và time series không tăng theo số ID.
- Metric tags chỉ chứa các chiều hữu hạn.
- Trace attributes có thể chứa reference an toàn nếu policy cho phép.
- Không có raw ID hoặc dữ liệu nhạy cảm trong metrics exposition.

Kiểm thử cardinality nên dùng nhiều giá trị giả lập và kiểm tra số series thực tế trong registry/exporter. Đừng đưa các ID này thành tag production chỉ để tiện test.

## Những sai lầm thường gặp

**Đưa mọi Observation key-value vào metric tag.** High-cardinality có thể làm số time series tăng rất lớn. Phân loại rõ low và high cardinality.

**Dùng ID duy nhất làm low-cardinality.** Request ID, order ID, user ID hoặc message ID không phải dimension tổng hợp. Để chúng ở trace context khi an toàn và thực sự cần.

**Nghĩ high-cardinality đồng nghĩa được phép ghi mọi dữ liệu.** Trace vẫn là dữ liệu được lưu và truy cập. Loại bỏ secret, payload và thông tin cá nhân không cần thiết.

**Dùng URL đầy đủ làm route tag.** ID trong path tạo series riêng. Dùng route template hoặc endpoint group.

**Đặt outcome trước khi biết kết quả.** Metrics có thể phân loại sai success/failure. Xác định thời điểm và cách cập nhật context cho outcome cuối cùng.

**Lặp lại thuộc tính mặc định không có giá trị.** Các key-value trùng lặp làm tăng kích thước span và khó thống nhất convention. Chỉ giữ thuộc tính cần thiết.

**Cho rằng mọi handler xuất cùng một thuộc tính.** Metrics và tracing handler có quy tắc ánh xạ khác nhau. Kiểm tra dữ liệu ở từng backend.

**Dùng trace ID làm metric tag để liên kết dashboard.** Sử dụng exemplar hoặc khả năng liên kết metrics-traces của backend.

**Chỉ unit test convention.** Handler hoặc filter có thể thay đổi kết quả. Kiểm thử cả meter tags và span attributes được xuất.

**Bật histogram trên metric có nhiều dimension không giới hạn.** Bucket nhân với tag combinations làm cardinality tăng nhanh. Tính ngân sách trước khi bật.

## Checklist chọn thông tin cho metrics và traces

Trước khi thêm key-value vào Observation, hãy xác minh:

1. Thuộc tính phục vụ câu hỏi tổng hợp hay điều tra một lần thực thi?
2. Nếu dùng làm metric tag, tập giá trị có hữu hạn và ổn định không?
3. Có thể chuẩn hóa thành enum, route template hoặc nhóm operation không?
4. Tổ hợp các tag có tạo cardinality phù hợp ngân sách không?
5. Thuộc tính có cần xuất trong trace hay có thể tra cứu qua log/hệ thống nghiệp vụ?
6. Giá trị có chứa secret, payload hoặc dữ liệu cá nhân không cần thiết không?
7. High-cardinality value đã được giả danh hoặc làm sạch khi cần chưa?
8. Convention có tập trung hóa tên và key-value cho loại Observation không?
9. Metrics handler và tracing handler có ánh xạ thuộc tính đúng mục tiêu không?
10. Có dùng exemplar thay vì trace ID metric tag khi backend hỗ trợ không?
11. Test có kiểm tra cả convention, metric tags và span attributes không?
12. Có kiểm tra cardinality khi bật histogram hoặc thêm dimension mới không?

## Kết luận

Chọn thông tin cho Observation cần bắt đầu từ mục tiêu sử dụng. Metrics cần low-cardinality dimensions có tập giá trị hữu hạn để tổng hợp và so sánh; traces có thể giữ thêm high-cardinality context để điều tra một lần thực thi, nhưng vẫn phải tuân thủ nguyên tắc tối thiểu hóa dữ liệu và bảo vệ thông tin.

Hãy dùng ObservationConvention để chuẩn hóa tên và thuộc tính, giữ ID duy nhất ngoài metric tags, dùng route template và outcome đã chuẩn hóa, đồng thời kiểm tra cách metrics và tracing handler thực sự xuất dữ liệu. Khi cần liên kết dashboard với trace, ưu tiên exemplar hoặc cơ chế correlation của backend thay vì tạo series theo trace ID. Kiểm thử cả convention, meter tags, span attributes và cardinality để bảo đảm telemetry vừa hữu ích vừa có chi phí kiểm soát được.
