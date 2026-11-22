# Chạy song song, shadow traffic và đánh giá kết quả

Di chuyển một ứng dụng sang serverless là thay đổi cả cách chạy, cách mở rộng, cách lưu trạng thái và cách xử lý lỗi. Chuyển toàn bộ traffic trong một lần có thể khiến lỗi kiến trúc, sai khác dữ liệu hoặc thiếu capacity chỉ lộ ra khi người dùng thật đã bị ảnh hưởng. Chạy song song và shadow traffic giúp kiểm chứng hệ thống mới bằng workload thực tế trước khi chuyển quyền phục vụ.

**Chạy song song (parallel run)** là giai đoạn hệ thống cũ và hệ thống mới cùng hoạt động trong một khoảng thời gian để nhóm so sánh hành vi, dữ liệu và vận hành. **Shadow traffic** là cách gửi bản sao request hoặc event tới hệ thống mới để quan sát kết quả, trong khi hệ thống cũ vẫn là nơi tạo response hoặc quyết định nghiệp vụ cho người dùng. Shadow traffic không tự động có nghĩa là an toàn: nếu bản sao request tạo thanh toán, gửi email hoặc ghi vào dữ liệu production, nhóm có thể tạo side effect hai lần.

Bài học này trình bày cách tổ chức migration theo từng bước, thiết kế luồng mirror an toàn cho Java serverless, so sánh kết quả có ý nghĩa, đặt điều kiện cutover và chuẩn bị rollback. Mục tiêu cuối cùng là chứng minh hệ thống mới đáp ứng hành vi nghiệp vụ, latency, reliability, security và cost trước khi nhận toàn bộ traffic.

## 1. Vì sao cần chạy song song?

Hệ thống cũ thường chứa những hành vi không được ghi đầy đủ trong tài liệu: quy tắc validation, rounding, thứ tự cập nhật, retry, timeout, default value, timezone, cách xử lý dữ liệu cũ và những tích hợp phụ. Unit test có thể không phản ánh hết workload thực tế.

Chạy song song giúp phát hiện:

- Response hoặc business decision khác với hệ thống cũ.
- Dữ liệu thiếu, thừa, sai định dạng hoặc sai trạng thái.
- Java runtime có latency hoặc memory profile khác dự kiến.
- Trigger, queue, retry hoặc concurrency không đáp ứng traffic thật.
- Permission, network route, secret hoặc dependency chưa được cấu hình đúng.
- Chi phí trên mỗi giao dịch cao hơn mô hình hiện tại.
- Các trường hợp hiếm chỉ xuất hiện trong traffic production.

Một lần deploy thành công chỉ chứng minh artifact có thể được triển khai. Nó không chứng minh hệ thống mới tương đương về nghiệp vụ hoặc sẵn sàng thay thế hệ thống cũ.

## 2. Phân biệt parallel run, shadow traffic, canary và dual-write

Các thuật ngữ này thường bị dùng lẫn nhau nhưng chúng có hành vi khác nhau:

| Cách chạy | Request tới hệ thống mới? | Ai trả response cho user? | Có ghi dữ liệu? |
|---|---|---|---|
| Offline replay | Gửi dữ liệu đã lưu hoặc tổng hợp vào hệ thống mới | Không có user request trực tiếp | Chỉ ghi vào môi trường test/replay |
| Shadow traffic | Bản sao request được gửi tới hệ thống mới | Hệ thống cũ | Candidate nên chỉ đọc hoặc ghi vào nơi cô lập |
| Parallel run | Cả hai hệ thống xử lý cùng nghiệp vụ trong thời gian đối chiếu | Theo quy tắc đã chọn, thường hệ thống cũ trước | Có thể ghi riêng hai datastore hoặc chỉ một nơi authoritative |
| Canary | Một tỷ lệ request thật được phục vụ bởi hệ thống mới | Hệ thống được chọn cho từng request | Hệ thống phục vụ request được quyền ghi |
| Dual-write | Một thao tác ghi được gửi tới hai hệ thống | Tùy thiết kế | Có, cần consistency và recovery rõ ràng |
| Blue/green cutover | Traffic chuyển từ môi trường xanh sang môi trường mới | Môi trường đang active | Một writer được chỉ định |

Shadow traffic thường không thay thế response chính. Canary thì có: request được định tuyến tới candidate và candidate chịu trách nhiệm trả kết quả cho người dùng. Một load balancer phân phối 10% traffic sang target mới là canary hoặc weighted routing, không nhất thiết là shadow mirroring.

Dual-write là vấn đề dữ liệu riêng. Nếu ứng dụng ghi vào hai database trong cùng request, một lần ghi có thể thành công và lần còn lại thất bại. Không có transaction phân tán hoặc cơ chế reconciliation, hai hệ thống có thể lệch nhau.

## 3. Mô hình migration theo từng giai đoạn

Một lộ trình an toàn thường tăng dần mức độ tin cậy và phạm vi traffic:

~~~mermaid
flowchart TD
    A["Kiểm kê hành vi hệ thống cũ"] --> B["Replay dữ liệu lịch sử"]
    B --> C["Shadow traffic vào candidate"]
    C --> D["So sánh response và dữ liệu"]
    D --> E{"Đạt tiêu chí?"}
    E -->|"Chưa"| F["Sửa sai khác và chạy lại"]
    F --> C
    E -->|"Đạt"| G["Canary: một tỷ lệ request thật"]
    G --> H["Theo dõi SLO và nghiệp vụ"]
    H --> I{"Đạt ngưỡng mở rộng?"}
    I -->|"Chưa"| J["Rollback traffic về hệ thống cũ"]
    I -->|"Đạt"| K["Tăng tỷ lệ canary"]
    K --> L["Cutover toàn bộ"]
    L --> M["Giữ rollback window và đối soát"]
~~~

Các giai đoạn có thể là:

1. **Baseline:** đo hệ thống cũ và xác định hành vi cần giữ.
2. **Offline replay:** phát lại request/event đã được làm sạch vào candidate.
3. **Shadow:** mirror một phần traffic production, không tạo side effect production.
4. **Comparison:** đối chiếu response, dữ liệu, latency, lỗi và cost.
5. **Canary:** cho candidate phục vụ một tỷ lệ request thật.
6. **Progressive cutover:** tăng dần traffic theo các gate đã thống nhất.
7. **Stabilization:** giữ hệ thống cũ sẵn sàng rollback trong thời gian xác định.
8. **Decommission:** chỉ ngừng hệ thống cũ sau khi hết rollback window, dữ liệu được đối soát và các phụ thuộc đã chuyển.

Không nhảy thẳng từ shadow sang 100% traffic. Shadow đánh giá khả năng xử lý request; canary mới kiểm chứng candidate trong vai trò hệ thống phục vụ người dùng.

## 4. Xác định phạm vi nghiệp vụ trước khi mirror

Không phải mọi endpoint hoặc event đều nên được đưa vào cùng một experiment. Phân loại theo loại thao tác:

| Loại thao tác | Ví dụ | Cách thử an toàn |
|---|---|---|
| Read-only | Tra cứu hồ sơ, danh mục | Mirror request và so sánh response |
| Deterministic calculation | Tính thuế, phí vận chuyển, điểm | Mirror và so sánh kết quả sau chuẩn hóa |
| Command có side effect | Tạo đơn, giữ hàng, cập nhật trạng thái | Chạy trên datastore cô lập hoặc dùng fake dependency |
| External side effect | Capture payment, gửi email/SMS, phát hành hóa đơn | Mock/sandbox hoặc chặn hoàn toàn trong shadow |
| Event consumer | SQS/Kafka/EventBridge handler | Replay vào queue riêng với idempotency namespace riêng |
| Scheduled job | Reconciliation, batch settlement | Chạy trên snapshot dữ liệu hoặc dry-run |

Một request POST không nhất thiết là không thể shadow, nhưng candidate không được thực hiện side effect production lần thứ hai. Nếu chưa có cách cô lập side effect, chỉ chạy phần validation/calculation hoặc dùng dữ liệu đã sao chép.

## 5. Kiến trúc shadow traffic

Có thể mirror traffic ở gateway/proxy hoặc trong application. Chọn vị trí dựa trên yêu cầu bảo mật, khả năng giữ nguyên request và độ tin cậy của đường gửi bản sao.

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Router"]
    G --> L["Legacy application"]
    L --> R["Response to client"]
    G -. "Mirror copy" .-> Q["Shadow queue"]
    Q --> S["Java serverless candidate"]
    S --> X["Isolated dependencies"]
    L --> O["Comparison store"]
    S --> O
    O --> A["Diff and metrics"]
~~~

Trong mô hình này:

- Hệ thống cũ tiếp tục trả response chính.
- Gateway hoặc một thành phần mirror gửi bản sao tới shadow queue.
- Candidate xử lý bản sao trong môi trường cô lập.
- Candidate ghi kết quả so sánh vào comparison store.
- Một worker phân tích diff và phát metric.
- Shadow path không được phép gửi payment, email hoặc command tới dependency production.

Mirror nên bất đồng bộ và có giới hạn tài nguyên. Nếu mirror làm chậm request chính hoặc làm cạn connection pool, chính experiment sẽ gây ảnh hưởng lên hệ thống đang phục vụ.

## 6. Chọn nơi tạo bản sao request

Có ba cách thường dùng:

**Gateway/proxy mirroring:** proxy hoặc service mesh nhận request và gửi thêm một bản sao tới candidate. Ưu điểm là ít thay đổi code legacy. Cần xác nhận proxy hỗ trợ mirror thật sự, giữ header cần thiết, giới hạn payload và không chờ candidate trả response.

**Application-level mirror:** ứng dụng cũ tạo một shadow envelope sau khi xử lý request chính. Cách này cho phép chọn trường dữ liệu, thêm correlation ID và loại bỏ thông tin nhạy cảm. Tuy nhiên, cần tránh làm tăng latency và phải xử lý trường hợp gửi bản sao thất bại.

**Event/log replay:** ghi request hoặc domain event vào stream/log có kiểm soát, sau đó replay sang candidate. Cách này thuận tiện cho thử lại và phân tích, nhưng phải lưu đủ thông tin để tái tạo ngữ cảnh và bảo vệ dữ liệu.

Không phải gateway nào cũng có tính năng duplicate request. Một số tính năng canary chỉ phân phối request giữa hai deployment, không gửi hai bản sao. Kiểm tra semantics của công cụ trước khi gọi nó là shadow traffic.

## 7. Thiết kế shadow envelope

Không nên gửi toàn bộ HTTP request thô nếu candidate chỉ cần một phần dữ liệu. Tạo envelope có schema version và metadata rõ ràng:

~~~json
{
  "schemaVersion": 1,
  "experimentId": "migration-orders-2026-11",
  "correlationId": "req-7f2d",
  "sourceSystem": "legacy-orders",
  "targetSystem": "serverless-orders",
  "capturedAt": "2026-11-17T10:15:30Z",
  "operation": "CalculateOrder",
  "tenantKey": "tenant-42",
  "idempotencyKey": "order-command-987",
  "payload": {
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-100",
        "quantity": 2
      }
    ]
  }
}
~~~

Envelope nên chứa:

- Experiment ID để phân biệt các đợt chạy.
- Correlation ID để nối log giữa legacy, queue và candidate.
- Schema version để thay đổi cấu trúc có kiểm soát.
- Source/target system và operation.
- Capture timestamp và thông tin cohort cần thiết.
- Idempotency key ổn định.
- Payload đã loại bỏ hoặc che dữ liệu không cần thiết.

Không đưa access token, cookie, password, payment card data hoặc secret vào shadow envelope. Nếu cần định danh user/tenant, ưu tiên ID giả danh hoặc tokenization. Chỉ giữ trường cần thiết để đánh giá nghiệp vụ.

## 8. Không tạo side effect production trong shadow

Đây là điều kiện an toàn quan trọng nhất. Candidate có thể thực thi code giống production nhưng các dependency cần được cấu hình để không tạo hành động thật.

Các cách kiểm soát:

- Dùng database/schema riêng với bản sao dữ liệu đã làm sạch.
- Dùng payment sandbox hoặc fake payment adapter.
- Chặn outbound email/SMS và thay bằng sink ghi nhận nội dung.
- Dùng object storage prefix riêng cho experiment.
- Dùng queue/topic riêng, không publish sang event bus production.
- Dùng IAM role chỉ có quyền truy cập resource shadow.
- Chặn network egress tới endpoint có side effect.
- Đánh dấu mọi request bằng experiment ID.
- Đặt TTL cho dữ liệu thử nghiệm và dọn sau khi hoàn tất.

Một flag trong application như SHADOW_MODE=true hữu ích nhưng không đủ nếu một nhánh code quên kiểm tra flag. Nên kết hợp application guard với IAM, network policy, sandbox credentials và resource isolation.

Với payment, chỉ dùng sandbox hoặc adapter giả. Không gửi authorization/capture thật chỉ để so sánh candidate với legacy. Với email/SMS, ghi vào sink và so sánh template/recipient đã che dữ liệu thay vì gửi tới khách hàng.

## 9. Đảm bảo shadow không ảnh hưởng hệ thống chính

Shadow traffic tạo thêm tải. Nếu mirror 100% traffic, hệ thống candidate và các dependency liên quan có thể nhận thêm một lượng request tương đương production.

Các biện pháp:

- Bắt đầu với sampling rate thấp.
- Dùng queue có retention và DLQ riêng.
- Đặt maximum concurrency cho candidate.
- Giới hạn batch size và tốc độ replay.
- Dùng timeout ngắn cho publisher.
- Có backpressure khi shadow queue backlog tăng.
- Drop bản sao khi quá tải thay vì block request chính.
- Đặt circuit breaker cho mirror publisher.
- Tách compute, database và network quota nếu có thể.
- Theo dõi impact lên latency và error rate của legacy.

Nếu mirror enqueue nằm trên critical path, queue chậm có thể kéo dài request chính. Có thể dùng outbox hoặc cơ chế asynchronous fan-out ở tầng hạ tầng; nếu phải publish đồng bộ, đặt timeout ngắn và coi shadow publish là best-effort. Ghi metric cho số bản sao bị drop để không nhầm rằng mọi request đều đã được so sánh.

Không dùng thread nền fire-and-forget trong AWS Lambda để gửi shadow sau khi handler trả response. Runtime có thể freeze hoặc tái sử dụng environment và công việc nền không được bảo đảm hoàn tất. Dùng queue bền vững, outbox hoặc proxy mirroring có kiểm soát.

## 10. Sampling traffic có chủ đích

Sampling giúp giới hạn chi phí và blast radius. Không nhất thiết mirror mọi request.

Có thể chọn mẫu theo:

- Tỷ lệ ngẫu nhiên, ví dụ 1% hoặc 5%.
- Tenant hoặc nhóm khách hàng nội bộ.
- Route hoặc loại nghiệp vụ.
- Kích thước payload.
- Region hoặc source channel.
- Request có feature/version cụ thể.
- Các trường hợp biên đã biết như currency, timezone hoặc trạng thái đơn.

Sampling cần tránh thiên lệch. Nếu chỉ chọn request nhỏ và đơn giản, candidate có thể trông tốt nhưng thất bại với payload lớn hoặc luồng hiếm. Kết hợp random sampling với targeted cohorts để vừa đại diện traffic vừa bao phủ edge cases.

Ghi lại số request đủ điều kiện, số request được chọn, số mirror thành công và số candidate xử lý xong. Nếu không có denominator, không thể biết tỷ lệ diff có đại diện hay không.

## 11. Java: tách nghiệp vụ khỏi adapter và side effect

Ứng dụng Java nên tách phần tính toán/nghiệp vụ khỏi adapter HTTP, queue, database và external service. Điều này giúp candidate có thể chạy cùng input nhưng dùng adapter giả hoặc datastore riêng.

Một cấu trúc đơn giản:

~~~java
public interface OrderCalculator {
    OrderQuote calculate(OrderCommand command);
}

public final class LegacyOrderCalculator implements OrderCalculator {
    @Override
    public OrderQuote calculate(OrderCommand command) {
        // Logic hiện tại của hệ thống cũ.
        return legacyRules.calculate(command);
    }
}

public final class ServerlessOrderCalculator implements OrderCalculator {
    @Override
    public OrderQuote calculate(OrderCommand command) {
        // Logic của candidate Java function.
        return newRules.calculate(command);
    }
}
~~~

Cả hai implementation nhận cùng một command chuẩn hóa. Adapter chịu trách nhiệm chuyển HTTP/event payload sang domain command. Domain logic không nên tự đọc environment variable hoặc tự gọi payment provider trong bước tính toán.

Khi shadowing, gọi implementation candidate với adapter phụ thuộc cô lập. Khi canary, router chọn một implementation làm hệ thống phục vụ chính cho request đó.

## 12. Java: publish shadow envelope tới queue

Một ví dụ minh họa application-level mirroring:

~~~java
public final class OrderController {
    private final LegacyOrderService legacy;
    private final ShadowPublisher shadowPublisher;

    public OrderController(
            LegacyOrderService legacy,
            ShadowPublisher shadowPublisher) {
        this.legacy = legacy;
        this.shadowPublisher = shadowPublisher;
    }

    public OrderResponse create(OrderRequest request) {
        OrderResponse primary = legacy.create(request);

        ShadowEnvelope envelope =
                ShadowEnvelope.from(request, primary.getRequestId());

        try {
            shadowPublisher.publishWithShortTimeout(envelope);
        } catch (RuntimeException error) {
            // Không làm hỏng response chính chỉ vì mirror thất bại.
            Metrics.increment("shadow.publish.failure");
        }

        return primary;
    }
}
~~~

Ví dụ chỉ minh họa luồng; publish đồng bộ vẫn có thể thêm latency. Trong production, cân nhắc outbox hoặc fan-out ở gateway/proxy. Nếu nghiệp vụ cần bảo đảm shadow event được lưu, dùng transactional outbox thay vì nuốt lỗi publish. Shadow path có thể best-effort khi mục tiêu là so sánh và không được phép ảnh hưởng request chính.

Không đưa primary response vào envelope nếu nó chứa PII hoặc secret. Chỉ đưa các trường cần cho diff và dùng redaction trước khi publish.

## 13. Java: xử lý shadow event idempotently

Shadow consumer có thể nhận lại cùng một envelope do queue retry. Dùng experiment ID cùng correlation ID làm khóa xử lý, nhưng không dùng khóa shadow chung với nghiệp vụ production nếu việc đó có thể chặn candidate.

~~~java
public final class ShadowOrderHandler
        implements RequestHandler<ShadowEnvelope, ShadowResult> {

    private final ShadowStore store = ShadowStore.create();
    private final OrderCalculator candidate =
            ServerlessOrderCalculator.create();

    @Override
    public ShadowResult handleRequest(
            ShadowEnvelope envelope,
            Context context) {

        String key = envelope.experimentId()
                + ":" + envelope.correlationId();

        ShadowResult existing = store.findCompleted(key);
        if (existing != null) {
            return existing;
        }

        OrderCommand command =
                OrderCommand.from(envelope.payload());

        OrderQuote quote = candidate.calculate(command);

        ShadowResult result =
                ShadowResult.completed(key, quote);

        store.saveIfAbsent(result);
        return result;
    }
}
~~~

Đây là pseudocode; store cần atomic conditional write hoặc transaction. Nếu hai invocation đồng thời nhận cùng envelope, chỉ một kết quả được ghi làm kết quả chuẩn. Candidate không được gọi command handler tạo order thật.

Nếu cùng một input được replay trong experiment khác, dùng experiment ID mới để lưu kết quả mới nhưng giữ correlation ID gốc để so sánh các lần chạy.

## 14. Chuẩn hóa kết quả trước khi so sánh

So sánh JSON byte-for-byte thường tạo false positive. Hai hệ thống có thể trả cùng kết quả nghiệp vụ nhưng khác thứ tự field, timestamp, generated ID hoặc định dạng số.

Chuẩn hóa trước khi diff:

- Sắp xếp collection nếu thứ tự không có ý nghĩa.
- Chuẩn hóa timezone về UTC.
- Chuẩn hóa currency và decimal scale.
- Bỏ hoặc mask request ID được tạo độc lập.
- So sánh timestamp theo tolerance đã định nghĩa nếu nghiệp vụ cho phép.
- Chuẩn hóa null, missing field và default value theo contract.
- Chuẩn hóa text encoding và casing nếu semantics không phân biệt.
- Giữ nguyên field có ý nghĩa như trạng thái, amount, tax, inventory và permission decision.

Không loại bỏ field chỉ để làm diff pass. Mỗi normalization rule phải được giải thích và review. Nếu timestamp là dữ liệu nghiệp vụ, không được bỏ qua nó chỉ vì hai hệ thống tạo khác thời điểm.

## 15. Phân loại diff theo mức độ nghiêm trọng

Không phải mọi khác biệt đều có cùng mức rủi ro.

| Mức độ | Ví dụ | Hành động |
|---|---|---|
| Critical | Sai số tiền, sai quyền truy cập, duplicate payment, mất order | Chặn cutover; điều tra ngay |
| High | Sai trạng thái nghiệp vụ, thiếu record, sai inventory | Chặn mở rộng traffic |
| Medium | Sai field không ảnh hưởng quyết định chính nhưng phá contract | Sửa hoặc có phê duyệt ngoại lệ |
| Low | Timestamp, ordering hoặc formatting khác đã được xác nhận không có ý nghĩa | Ghi nhận normalization rule |
| Expected | Trường được thiết kế khác giữa hai phiên bản | Ghi rõ mapping và kiểm tra consumer compatibility |

Đặt severity theo domain. Với payment, chênh lệch 1 đồng cũng có thể là critical. Với danh sách gợi ý, thứ tự item có thể là medium hoặc low tùy contract.

Không chỉ tính một tỷ lệ diff tổng thể. Một tỷ lệ nhỏ nhưng tập trung ở giao dịch giá trị cao có thể nguy hiểm hơn nhiều so với nhiều khác biệt formatting.

## 16. So sánh dữ liệu và business invariants

Ngoài response diff, cần kiểm tra các invariant của nghiệp vụ:

- Tổng số order tạo mới theo ngày.
- Tổng amount theo currency.
- Số payment authorized/captured/refunded.
- Số inventory reservation và release.
- Trạng thái workflow cuối cùng.
- Số event đã nhận, xử lý, retry và vào DLQ.
- Quan hệ foreign key hoặc reference giữa các aggregate.
- Không có hai bản ghi cùng business key nếu contract yêu cầu duy nhất.

So sánh theo cùng một cohort và cửa sổ thời gian. Dữ liệu eventual consistency có thể chưa đồng bộ ngay; đặt reconciliation window rõ ràng và phân biệt lag bình thường với record bị mất.

Khi dữ liệu có PII, thực hiện diff bằng identifier giả danh hoặc hash có salt được quản lý an toàn. Không xuất dữ liệu cá nhân vào dashboard hoặc log diff.

## 17. Xử lý dữ liệu khi hệ thống cũ và mới có schema khác nhau

Trong migration, schema cũ và mới có thể không giống nhau. Cần xác định mapping rõ ràng:

- Field rename.
- Field split hoặc merge.
- Type conversion.
- Default value.
- Enum mapping.
- Precision và rounding.
- Timezone và timestamp semantics.
- Soft delete và tombstone.
- Versioning và backward compatibility.

Dùng expand-and-contract khi có thể:

1. Thêm field hoặc schema mới theo cách tương thích ngược.
2. Triển khai code đọc được cả dạng cũ và mới.
3. Backfill dữ liệu lịch sử.
4. Bắt đầu ghi hoặc mirror dữ liệu theo chiến lược đã chọn.
5. Chuyển reader sang schema mới.
6. Theo dõi và đối soát.
7. Chỉ xóa field cũ sau khi không còn consumer sử dụng.

Không deploy schema breaking change trước khi mọi producer/consumer liên quan đã sẵn sàng.

## 18. Dual-write và consistency

Dual-write có thể cần khi hệ thống cũ và mới phải cùng nhận cập nhật trong thời gian chuyển đổi. Nhưng nếu application ghi database A thành công rồi database B thất bại, trạng thái bị lệch.

Các chiến lược thường dùng:

**Transactional outbox:** ghi thay đổi nghiệp vụ và outbox event trong cùng transaction ở database nguồn. Một publisher đọc outbox và gửi event sang hệ thống đích. Điều này tránh trường hợp database commit nhưng event bị mất.

**Change Data Capture (CDC):** đọc transaction log của database nguồn để đồng bộ thay đổi sang target. Cần theo dõi replication lag, schema changes và checkpoint.

**Single writer:** chỉ một hệ thống có quyền ghi tại một thời điểm. Hệ thống còn lại nhận dữ liệu qua replication hoặc event. Cách này giảm xung đột và đơn giản hóa rollback.

**Reconciliation:** định kỳ so sánh source và target, phát hiện và sửa sai lệch theo business key.

Không dùng hai writer độc lập cho cùng aggregate nếu chưa có conflict resolution. Một cơ chế retry đơn giản không giải quyết được trường hợp một bên đã commit còn bên kia chưa commit.

## 19. Giữ một source of truth trong từng giai đoạn

Trong mỗi giai đoạn migration, xác định rõ hệ thống nào là nguồn dữ liệu có thẩm quyền.

| Giai đoạn | Source of truth | Candidate được phép làm gì? |
|---|---|---|
| Offline replay | Legacy production data | Đọc snapshot và ghi datastore test |
| Shadow | Legacy | Xử lý bản sao, ghi kết quả comparison |
| Canary read path | Legacy hoặc target theo domain đã xác định | Candidate phục vụ một cohort đọc |
| Canary write path | Một writer được chỉ định | Chỉ writer đó commit nghiệp vụ |
| Cutover | Target | Legacy read-only hoặc nhận CDC để rollback |
| Decommission | Target | Legacy được tắt sau khi hết retention/rollback window |

Nếu chuyển write authority, cần có bước fencing để hệ thống cũ không tiếp tục ghi sau thời điểm cutover. Có thể dùng routing gate, feature flag, database permission hoặc lease/epoch token. Chỉ đổi DNS không đủ để ngăn request cũ đang chạy tiếp tục ghi.

## 20. Thiết kế feature flag và routing

Router nên quyết định hệ thống nào xử lý request dựa trên flag hoặc cohort ổn định. Dùng hash của tenant/user/business key để một khách hàng không bị chuyển qua lại giữa legacy và target ở mỗi request.

Ví dụ logic:

~~~java
public OrderResponse route(
        OrderRequest request,
        RoutingConfig config) {

    if (config.isTargetEnabledFor(request.tenantId())) {
        return serverlessOrderService.create(request);
    }

    return legacyOrderService.create(request);
}
~~~

Shadow mode cần là một quyết định độc lập với routing:

- Primary target: hệ thống trả response cho user.
- Shadow target: hệ thống nhận bản sao để so sánh.
- Write authority: hệ thống duy nhất được commit side effect.
- Cohort: nhóm request được chọn để chạy candidate.

Không dùng một boolean như NEW_SYSTEM=true để điều khiển đồng thời routing, shadow, data writer và external side effect. Tách các flag giúp rollback chính xác và tránh bật nhầm quyền ghi.

## 21. Đánh giá latency và throughput

Khi so sánh legacy với serverless, đo cùng loại request và cùng điều kiện tải:

- p50, p95, p99 và p99.9 latency.
- Throughput request/giây hoặc event/giây.
- Error rate theo status và loại exception.
- Queue age và processing delay.
- Cold start/Init Duration nếu có.
- Throttles và concurrency.
- Dependency latency.
- Timeout và retry rate.

Shadow candidate không trả response cho user, nên latency của nó không phải latency end-to-end mà user nhận được. Đo riêng processing latency của candidate và latency tăng thêm do mirror publisher. Trong canary, đo end-to-end latency thật của request được candidate phục vụ.

Không so p99 của legacy trong một giờ cao điểm với p99 của candidate trong một giờ ít tải. Dùng cùng cohort, cửa sổ thời gian hoặc replay dataset để phép so sánh có ý nghĩa.

## 22. Đánh giá reliability và vận hành

Một candidate có latency tốt nhưng retry liên tục hoặc DLQ tăng không thể coi là tốt hơn.

Theo dõi:

| Nhóm | Chỉ số |
|---|---|
| Invocation | Invocations, Errors, Throttles, Duration |
| Queue | Visible messages, in-flight, age of oldest message |
| Retry | Retry count, redrive count, DLQ messages |
| Runtime | Init duration, memory usage, timeout, out of memory |
| Dependency | Connection failures, 429/5xx, timeout, pool saturation |
| Data | Missing, duplicate, stale read, reconciliation mismatch |
| Operations | Deployment failure, rollback time, alert count |
| Security | Access denied, secret access, unexpected egress |

Dùng cùng trace/correlation ID để nối legacy request, shadow event, candidate invocation và comparison record. Tránh đưa customer ID trực tiếp vào metric dimension vì cardinality cao và có thể lộ dữ liệu.

## 23. Đánh giá chi phí trên cùng đơn vị nghiệp vụ

Chi phí cần tính cho toàn bộ pipeline, không chỉ Lambda duration:

- Legacy compute và license còn phải duy trì.
- Lambda request và GB-seconds.
- API Gateway, queue, stream và event poller.
- Log, metric, trace và retention.
- Database, cache, NAT, storage và data transfer.
- Provisioned Concurrency hoặc minimum instances.
- Shadow traffic tạo thêm request và compute.
- Dual-write, CDC, reconciliation và replay.
- Chi phí vận hành trong thời gian hai hệ thống cùng tồn tại.

Một metric hữu ích:

~~~text
Cost per successful business operation =
Total migration-period cost / Successful business operations
~~~

Tách chi phí migration tạm thời khỏi steady-state cost. Shadow traffic thường làm chi phí tăng trong giai đoạn kiểm chứng; đó là chi phí có chủ đích để giảm rủi ro cutover. Cần giới hạn thời gian và tỷ lệ mirror để không kéo dài experiment vô hạn.

## 24. Thiết kế experiment và acceptance gates

Trước khi chạy, ghi rõ:

1. Mục tiêu nghiệp vụ.
2. Endpoint/event được chọn.
3. Cohort và sampling rate.
4. Source of truth.
5. Candidate side-effect policy.
6. Dataset hoặc payload được sử dụng.
7. Metrics và comparison rules.
8. Error budget và stop conditions.
9. Thời gian chạy và người chịu trách nhiệm.
10. Điều kiện tăng traffic, rollback và kết thúc.

Ví dụ acceptance gate:

| Tiêu chí | Điều kiện minh họa |
|---|---|
| Critical business diff | 0 |
| Duplicate side effect | 0 |
| Missing business record | 0 trong cohort đã đối soát |
| p95 latency | Không vượt SLO đã thống nhất |
| p99 latency | Không tăng quá ngưỡng cho phép so với baseline |
| Error rate | Trong error budget |
| Queue age | Dưới SLA xử lý |
| DLQ | Không có lỗi chưa phân loại |
| Data reconciliation | Không còn mismatch critical |
| Cost per success | Trong ngân sách mục tiêu |

Ngưỡng phải được owner nghiệp vụ và vận hành phê duyệt. Không dùng các con số minh họa như policy chung cho mọi workload.

## 25. Tính đủ thời gian và cỡ mẫu

Một vài chục request không đủ để kết luận hệ thống mới ổn định. Cần bao phủ:

- Peak và off-peak traffic.
- Payload nhỏ, trung bình và lớn.
- Các loại tenant hoặc customer tier.
- Error path và retry path.
- Event trễ, duplicate và out-of-order nếu có.
- Các loại currency, locale và timezone.
- Batch size và concurrency production dự kiến.

Nếu lỗi hiếm, cần đủ sample để có cơ hội quan sát. Nếu không thấy lỗi trong một sample nhỏ, điều đó không chứng minh xác suất lỗi bằng 0. Kết hợp traffic thật đã được làm sạch, synthetic edge cases và replay có kiểm soát.

Giữ experiment đủ lâu để bao phủ chu kỳ nghiệp vụ như cuối ngày, batch settlement, báo cáo hoặc lịch reset quota. Với workload theo mùa, có thể cần một canary window dài hơn hoặc test tải riêng.

## 26. Canary cutover sau shadow

Khi shadow đạt acceptance gate, bắt đầu canary. Canary có nghĩa một tỷ lệ request thật được candidate phục vụ và chịu trách nhiệm trả response/commit nghiệp vụ.

Một ví dụ tăng traffic:

~~~text
Stage 0: 0% target, 100% legacy
Stage 1: 1% target, 99% legacy
Stage 2: 5% target, 95% legacy
Stage 3: 10% target, 90% legacy
Stage 4: 25% target, 75% legacy
Stage 5: 50% target, 50% legacy
Stage 6: 100% target
~~~

Đây là lịch minh họa. Giữ mỗi stage đủ lâu để quan sát latency, lỗi và business outcome. Với write path, cohort cần ổn định và có source of truth rõ. Tránh route một user sang legacy rồi request tiếp theo sang target nếu hai hệ thống không chia sẻ trạng thái tương thích.

Nếu candidate gặp lỗi, ngừng tăng traffic và quay cohort về legacy theo runbook. Không tự động rollback chỉ vì một metric nhiễu trong một cửa sổ ngắn; dùng threshold, duration và business severity đã thống nhất.

## 27. Rollback và khả năng tương thích ngược

Rollback traffic chỉ dễ nếu dữ liệu và contract vẫn tương thích với hệ thống cũ.

Trước cutover, xác minh:

- Legacy vẫn đọc được dữ liệu do target ghi.
- Schema mới có backward compatibility hoặc có mapping ngược.
- Event đã phát hành không khiến consumer cũ lỗi.
- Queue/checkpoint có thể tiếp tục từ vị trí an toàn.
- Target không tạo side effect mà legacy không biết.
- Secret, IAM và network cho legacy vẫn còn trong rollback window.
- Có cách fence writer và chuyển quyền ghi về một nơi.

Nếu target ghi schema mới không tương thích, quay traffic về legacy có thể làm ứng dụng lỗi ngay cả khi deployment rollback thành công. Đây là lý do expand-and-contract và single-writer quan trọng.

Không xóa database cũ, queue cũ hoặc IAM role cũ ngay sau khi cutover. Chờ hết rollback window và hoàn tất reconciliation trước khi decommission.

## 28. Khi nào shadow traffic không phù hợp?

Shadow traffic có thể không phù hợp hoặc cần thiết kế đặc biệt khi:

- Request chứa dữ liệu nhạy cảm không thể sao chép hợp pháp.
- Operation có side effect không thể sandbox hoặc cô lập.
- Candidate không thể xử lý cùng schema/payload với legacy.
- Request có tính thời gian thực và mirror làm tăng tải đáng kể.
- Hệ thống có rate limit thấp hoặc chi phí mỗi request rất cao.
- Dữ liệu thay đổi liên tục khiến kết quả so sánh không còn cùng snapshot.
- Candidate phụ thuộc vào state được tạo trong request trước đó.
- Request chứa nonce, one-time token hoặc thao tác không thể replay.

Trong các trường hợp này, có thể dùng synthetic test, offline replay đã làm sạch, contract test, deterministic simulation hoặc shadow một phần read-only calculation.

## 29. Những lỗi thường gặp khi chạy song song

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi shadow nhưng vẫn gửi email/payment thật | Side effect hai lần | Fake adapter, sandbox và egress policy |
| Mirror 100% ngay từ đầu | Tăng tải và chi phí đột ngột | Sampling và tăng dần |
| So sánh JSON thô | False positive do timestamp/ID/order | Canonicalization có review |
| Bỏ qua các field khác nhau | Che giấu lỗi nghiệp vụ | Severity và invariant theo domain |
| Dùng một idempotency store chung | Shadow có thể chặn nghiệp vụ chính | Namespace riêng cho experiment |
| Dùng thread nền fire-and-forget trong Lambda | Bản sao có thể không được gửi | Queue/outbox/proxy mirror |
| Dual-write không có reconciliation | Hai datastore lệch nhau | Single writer, outbox/CDC và repair |
| Canary cohort thay đổi liên tục | So sánh thiếu nhất quán | Hash cohort ổn định |
| Chỉ đo latency candidate trong shadow | Nhầm với latency user thật | Đo riêng shadow processing và canary E2E |
| Rollback sau schema breaking change | Legacy không đọc được dữ liệu mới | Expand-and-contract và backward compatibility |
| Không có rollback window | Không còn đường quay lại | Giữ legacy, data và routing trong thời gian đã định |

## 30. Runbook cho shadow experiment

Một runbook tối thiểu cần có:

**Trước khi chạy**

- Xác định owner, experiment ID và thời gian.
- Xác nhận source of truth và side-effect policy.
- Kiểm tra candidate role, network egress và datastore.
- Chọn sampling rate và maximum concurrency.
- Bật dashboard, alarm và log correlation.
- Kiểm tra queue retention, DLQ và cách dừng mirror.

**Trong khi chạy**

- Theo dõi legacy latency/error rate.
- Theo dõi mirror publish success/drop.
- Theo dõi candidate invocation, errors và queue age.
- Kiểm tra diff theo severity.
- Kiểm tra side effect và data isolation.
- Dừng experiment nếu vượt stop condition.

**Sau khi chạy**

- Ngừng mirror và drain queue theo chính sách.
- Đối soát số request đủ điều kiện, mirrored, processed và compared.
- Tổng hợp diff và business invariant.
- Ghi lại cost và latency.
- Xóa hoặc archive dữ liệu thử nghiệm theo retention policy.
- Quyết định sửa, chạy lại, canary hoặc hủy migration.

## 31. Runbook cho cutover và rollback

**Cutover**

1. Xác nhận mọi acceptance gate đã đạt.
2. Xác nhận target capacity, quota và downstream.
3. Xác định writer authority và fencing mechanism.
4. Xác nhận schema compatibility.
5. Chọn cohort canary đầu tiên.
6. Chuyển routing theo tỷ lệ đã phê duyệt.
7. Theo dõi SLO, data consistency và business success.
8. Tăng traffic theo gate.
9. Chuyển 100% khi các stage đều ổn định.
10. Giữ legacy sẵn sàng trong rollback window.

**Rollback**

1. Dừng tăng traffic ngay.
2. Chuyển routing cohort về legacy.
3. Fencing target writer nếu cần.
4. Kiểm tra request đang chạy và message in-flight.
5. Đối soát giao dịch target đã commit.
6. Replay event chưa hoàn tất bằng idempotency key gốc.
7. Kiểm tra schema và data compatibility.
8. Khôi phục target traffic chỉ sau khi nguyên nhân được xử lý và gate được chạy lại.

Rollback không nhất thiết là xóa dữ liệu target. Thường cần giữ lại dữ liệu để điều tra và reconciliation.

## 32. Báo cáo đánh giá migration

Báo cáo nên có:

- Phạm vi endpoint/event và cohort.
- Thời gian, sampling rate và số lượng request đủ điều kiện.
- Số request được mirror, xử lý, so sánh và bị drop.
- Diff rate theo severity.
- Business invariant và reconciliation result.
- Latency p50/p95/p99 và throughput.
- Error, retry, throttle, queue age và DLQ.
- Chi phí trên mỗi nghiệp vụ thành công.
- Security/privacy review.
- Kết quả acceptance gate.
- Quyết định: tiếp tục shadow, sửa, canary, rollback hoặc decommission.
- Action item, owner và deadline.

Một báo cáo tốt phải phân biệt số liệu quan sát được với giả thuyết. Nếu sample chưa đủ hoặc một loại traffic chưa được bao phủ, ghi rõ giới hạn thay vì kết luận toàn hệ thống đã tương đương.

## 33. Checklist production

**Thiết kế experiment**

1. Có baseline và acceptance gate?
2. Source of truth được xác định cho từng giai đoạn?
3. Shadow và canary được phân biệt rõ?
4. Sampling có đại diện và bao phủ edge cases?
5. Có correlation ID và experiment ID?

**Bảo vệ nghiệp vụ và dữ liệu**

6. Candidate không tạo side effect production?
7. Payment/email/SMS dùng sandbox hoặc sink?
8. Datastore, queue và IAM được cô lập?
9. Payload được redaction và retention có giới hạn?
10. Idempotency key được giữ ổn định khi replay?
11. Dual-write có outbox/CDC/reconciliation?
12. Có single-writer hoặc fencing khi cutover?

**Đánh giá**

13. Response được canonicalize có kiểm soát?
14. Critical business diff bằng 0 theo policy?
15. Có so sánh business invariant và dữ liệu?
16. Đã đo p50/p95/p99, errors, retries và queue age?
17. Đã tính cost per successful operation?
18. Sample bao phủ peak và chu kỳ nghiệp vụ?

**Cutover và rollback**

19. Canary cohort ổn định?
20. Target có đủ quota, concurrency và downstream capacity?
21. Schema tương thích ngược?
22. Có runbook cutover/rollback?
23. Legacy còn sẵn sàng trong rollback window?
24. Có reconciliation trước khi decommission?

## Tài liệu tham khảo

- [AWS Prescriptive Guidance: Strangler fig pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html)
- [AWS Database Migration Service: Change data capture](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Task.CDC.html)
- [AWS Lambda: Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Amazon API Gateway: Canary release deployment](https://docs.aws.amazon.com/apigateway/latest/developerguide/canary-release.html)
- [OpenTelemetry: Distributed traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [AWS Well-Architected: Operational excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)

## Kết luận

Chạy song song và shadow traffic giúp kiểm chứng serverless candidate bằng workload thực tế trước khi chuyển quyền phục vụ. Shadow giữ hệ thống cũ làm primary và gửi bản sao tới candidate; canary mới chuyển một phần request thật sang hệ thống mới. Dual-write là một bài toán consistency riêng và cần single-writer, outbox/CDC hoặc reconciliation.

Với Java serverless, hãy tách domain logic khỏi adapter và side effect, dùng queue/outbox thay cho thread nền không được bảo đảm, cô lập database và external service, giữ idempotency key ổn định và chuẩn hóa kết quả trước khi diff. Đánh giá cả correctness, data invariants, latency, reliability và cost per successful operation. Chỉ tăng traffic khi acceptance gate đạt, schema tương thích và rollback đã được diễn tập.

