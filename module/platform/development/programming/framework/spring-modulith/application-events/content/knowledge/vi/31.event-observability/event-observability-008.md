# Dashboard vận hành

Application events giúp các module Spring Modulith giao tiếp mà không cần phụ thuộc trực tiếp vào implementation của nhau. Khi số lượng event, listener và luồng externalization tăng lên, đội vận hành cần một nơi để biết event có được publish, xử lý và chuyển tiếp đúng tiến độ hay không. Dashboard vận hành tập hợp các chỉ số, trạng thái và dấu vết cần thiết để phát hiện backlog, tìm listener lỗi và xác định event đang dừng ở ranh giới nào.

Dashboard không chỉ hiển thị số lượng event. Nó phải giúp trả lời các câu hỏi: publication nào đang chờ, listener nào xử lý chậm, lỗi có tăng không, broker có nhận message không, consumer có bị lag không và tác động tới nghiệp vụ là gì. Với Spring Modulith, cần phân biệt trạng thái publication trong ứng dụng với trạng thái xử lý ở hệ thống bên ngoài.

## 1. Dashboard vận hành cần quan sát điều gì?

Một event có thể đi qua nhiều chặng: module nghiệp vụ publish event, Event Publication Registry theo dõi publication tới listener, listener cập nhật dữ liệu hoặc externalize event, broker nhận message và consumer ở hệ thống khác xử lý. Mỗi chặng có tín hiệu vận hành riêng.

~~~mermaid
flowchart LR
    A[Business module] --> B[Application event]
    B --> C[Event Publication Registry]
    C --> D[Module listeners]
    C --> E[Externalization listener]
    E --> F[Message broker]
    F --> G[External consumers]
    C -. metrics / logs / traces .-> H[Operations dashboard]
    D -. metrics / logs / traces .-> H
    E -. metrics / logs / traces .-> H
    F -. lag / DLT .-> H
    G -. metrics / traces .-> H
~~~

Dashboard nên giúp phân biệt ít nhất bốn trạng thái:

- **Đã publish:** ứng dụng đã phát event và publication được đăng ký theo cơ chế đang dùng.
- **Listener đã hoàn tất:** listener nội bộ hoặc externalization listener đã hoàn thành công việc của nó.
- **Đã gửi tới broker:** message đã được adapter/broker xác nhận theo cơ chế gửi được cấu hình.
- **Consumer đã xử lý:** hệ thống nhận đã hoàn tất nghiệp vụ hoặc cập nhật read model.

Không suy ra trạng thái ở chặng sau chỉ từ trạng thái ở chặng trước. Ví dụ, externalization listener hoàn tất không chứng minh consumer Kafka đã xử lý message.

## 2. Nguồn dữ liệu cho dashboard

Có thể kết hợp nhiều nguồn để tạo bức tranh đầy đủ:

| Nguồn | Dữ liệu hữu ích | Mục đích |
| --- | --- | --- |
| Event Publication Registry | Publication đang chờ, đã hoàn tất, thời điểm tạo và trạng thái xử lý theo listener | Theo dõi giao event bên trong ứng dụng và phục hồi publication chưa hoàn tất |
| Micrometer metrics | Counter, timer, gauge và trạng thái xử lý do ứng dụng ghi nhận | Đo thông lượng, lỗi, độ trễ và backlog |
| Application logs | Event ID, event type, listener, correlation ID, exception và attempt | Điều tra một event hoặc một lần xử lý cụ thể |
| Distributed tracing | Span từ use case phát event qua listener và lời gọi dependency | Xem event chậm ở bước nào và dependency nào gây chậm |
| Message broker | Producer send result, consumer lag, partition, retry topic và DLT | Theo dõi chặng giao message và consumer bên ngoài |
| Business read model | Trạng thái đơn hàng, thanh toán hoặc quy trình nghiệp vụ | Hiểu tác động nghiệp vụ của event bị trễ hoặc lỗi |

Spring Modulith cung cấp Event Publication Registry để theo dõi publication. Tuy nhiên, không nên giả định mọi chỉ số mong muốn đều tự xuất hiện trong dashboard sau khi thêm dependency. Cần xác định dữ liệu nào registry hoặc persistence adapter cung cấp, sau đó bổ sung Micrometer metrics, log, trace và broker metrics cho các khoảng trống.

Với Spring Boot Actuator và Micrometer, ứng dụng có thể xuất metrics tới hệ thống giám sát như Prometheus hoặc nền tảng quan sát tương đương. Dashboard như Grafana đọc dữ liệu từ backend metrics; log và trace thường được truy vấn qua các hệ thống tương ứng. Tên metric và cách export phụ thuộc cấu hình và phiên bản ứng dụng.

## 3. Các chỉ số cốt lõi

Dashboard nên bắt đầu bằng một bộ chỉ số nhỏ có định nghĩa rõ ràng:

| Chỉ số | Cách hiểu | Ý nghĩa vận hành |
| --- | --- | --- |
| Published events | Số event được publish trong khoảng thời gian | Đo lưu lượng đầu vào |
| Completed publications | Số publication listener hoàn tất | Đo lượng công việc đã xử lý xong ở ứng dụng |
| Pending publications | Số publication chưa hoàn tất tại thời điểm đo | Phát hiện backlog |
| Oldest pending age | Tuổi của publication chưa hoàn tất lâu nhất | Phát hiện event bị mắc kẹt lâu |
| Listener processing duration | Thời gian từ lúc listener bắt đầu đến khi hoàn tất | Tìm listener xử lý chậm |
| Listener failure rate | Tỷ lệ lần xử lý listener thất bại | Phát hiện lỗi code hoặc dependency |
| Retry attempts | Số lần thử lại theo listener hoặc loại lỗi | Phát hiện dependency không ổn định |
| Externalization send failures | Số lần gửi integration event thất bại | Theo dõi ranh giới ra broker/API |
| Consumer lag | Chênh lệch giữa message đã ghi và offset consumer đã xử lý | Theo dõi mức bắt kịp của consumer |
| Dead-letter count | Số message được chuyển vào DLT/quarantine | Phát hiện message cần điều tra |

Định nghĩa đơn vị và cửa sổ đo nhất quán. `Pending publications` là số bản ghi tại một thời điểm; `Published events` là số phát sinh trong một cửa sổ. Không đặt hai số này cạnh nhau rồi coi chênh lệch của chúng là backlog nếu chưa tính các trạng thái và listener target tương ứng.

## 4. Bố cục dashboard đề xuất

Một dashboard vận hành có thể chia thành các hàng sau:

### Hàng 1 — Tình trạng tổng thể

Hiển thị trạng thái hệ thống và các tín hiệu quan trọng nhất:

- Số event publish trong 5 phút, 1 giờ và 24 giờ.
- Pending publication hiện tại.
- Tuổi của publication pending lâu nhất.
- Tỷ lệ listener thành công và thất bại.
- Độ trễ xử lý p50, p95 và p99.
- Số message trong DLT và consumer lag lớn nhất.

Đặt các tín hiệu cần hành động ở vị trí dễ nhìn. Mỗi con số cần có đơn vị, cửa sổ thời gian và liên kết tới trang chi tiết để tránh hiểu sai.

### Hàng 2 — Publication Registry

Hiển thị số publication theo trạng thái và listener target. Dùng biểu đồ thời gian để xem pending có tăng liên tục hay giảm sau khi phục hồi. Một bảng chi tiết có thể hiển thị:

| Trường | Nội dung |
| --- | --- |
| Event type | Loại application event |
| Listener | Listener target cần xử lý |
| Created at | Thời điểm publication được tạo |
| Pending age | Thời gian publication còn chưa hoàn tất |
| Last failure | Loại lỗi gần nhất nếu có |
| Attempts | Số lần xử lý/thử lại nếu hệ thống có ghi nhận |
| Correlation ID | Khóa liên kết với luồng nghiệp vụ |

Không phải mọi persistence adapter đều lưu đủ mọi trường trên. Chỉ hiển thị dữ liệu có nguồn thực tế; nếu attempt hoặc last failure không được lưu, hãy instrument ở listener hoặc hệ thống retry tương ứng.

### Hàng 3 — Listener

Đặt thông lượng, độ trễ và lỗi cạnh nhau theo listener. Một listener có thể chậm do truy vấn database, xử lý CPU hoặc gọi dependency ngoài. Phân tách theo listener giúp nhận biết một module đang gặp vấn đề trong khi các listener khác vẫn bình thường.

Các biểu đồ nên gồm:

- Số lần xử lý thành công/thất bại theo listener.
- Processing duration p50/p95/p99.
- Retry theo exception class hoặc nhóm lỗi.
- Số publication pending theo listener.
- Thời gian xử lý và backlog theo event type.

### Hàng 4 — Externalization và broker

Đối với event được externalize, hiển thị kết quả gửi tới từng destination, lỗi producer, thời gian gửi và số lần retry. Ở phía broker, theo dõi consumer lag, throughput, partition mất cân bằng, retry topic và DLT.

Giữ rõ ranh giới giữa metrics của ứng dụng phát và metrics của broker/consumer. Nếu publisher gửi thành công nhưng consumer lag tăng, vấn đề có thể nằm ở consumer hoặc broker. Nếu publication externalization pending, vấn đề có thể nằm trước hoặc trong thao tác gửi.

### Hàng 5 — Tác động nghiệp vụ và liên kết điều tra

Cho phép điều hướng từ event type hoặc correlation ID tới trace, log và bản ghi nghiệp vụ phù hợp. Ví dụ, nếu `OrderConfirmed` bị trễ, operator cần biết đơn hàng nào bị ảnh hưởng và listener nào đang chờ.

Chỉ hiển thị dữ liệu nghiệp vụ tối thiểu cần thiết. Dashboard chung không nên hiển thị địa chỉ, thông tin thanh toán hoặc payload nhạy cảm chỉ để thuận tiện điều tra.

## 5. Ví dụ instrument listener bằng Micrometer

Micrometer có thể ghi counter cho kết quả xử lý và timer cho thời gian chạy listener. Ví dụ dưới đây minh họa cách ghi nhận một listener cụ thể:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryProjectionListener {

    private final InventoryProjectionService projection;
    private final MeterRegistry registry;

    InventoryProjectionListener(
            InventoryProjectionService projection,
            MeterRegistry registry) {
        this.projection = projection;
        this.registry = registry;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            projection.apply(event);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(Timer.builder("application.event.listener.duration")
                    .description("Listener processing duration")
                    .tag("listener", "inventory-projection")
                    .tag("event.type", "order-confirmed")
                    .tag("outcome", outcome)
                    .register(registry));

            registry.counter("application.event.listener.processed",
                    "listener", "inventory-projection",
                    "event.type", "order-confirmed",
                    "outcome", outcome).increment();
        }
    }
}
~~~

Ví dụ dùng tag cố định cho listener và event type đã biết. Trong hệ thống thật, hãy chuẩn hóa tên metric và tag theo quy ước chung; không tạo metric mới cho từng event ID hoặc aggregate ID.

Với listener bất đồng bộ, timer đo thời gian thực thi listener. Nếu muốn đo end-to-end lag, cần có timestamp phát sinh event và timestamp hoàn tất, sau đó ghi một metric riêng. Không dùng processing duration thay cho event age hoặc publication lag.

## 6. Đo backlog và độ trễ đúng cách

Backlog và latency trả lời hai câu hỏi khác nhau:

- **Backlog:** có bao nhiêu publication/message đang chờ xử lý?
- **Age/latency:** công việc chờ lâu đến mức nào?

Một backlog 100 event có thể bình thường nếu listener xử lý nhanh và lưu lượng đang tăng; một publication pending duy nhất trong nhiều giờ có thể nghiêm trọng nếu nó chặn một quy trình quan trọng.

Định nghĩa các phép đo:

1. `pending_count`: số publication chưa hoàn tất tại thời điểm scrape.
2. `oldest_pending_age_seconds`: thời điểm hiện tại trừ thời điểm tạo của publication pending lâu nhất.
3. `listener_duration_seconds`: thời gian từ lúc listener bắt đầu tới lúc kết thúc một lần xử lý.
4. `event_processing_lag_seconds`: thời điểm listener hoàn tất trừ thời điểm event phát sinh.
5. `consumer_lag`: chênh lệch offset/log end và offset consumer đã commit theo cách broker định nghĩa.

Không cộng pending publication của nhiều listener thành số event nghiệp vụ duy nhất nếu một event được gửi tới nhiều listener. Một event có thể tạo nhiều publication target; dashboard phải nói rõ đang đếm event hay publication.

## 7. Thiết kế tag và tránh cardinality cao

Metrics cần chiều phân tích hữu ích nhưng số lượng time series phải được kiểm soát. Các tag thường phù hợp:

- `listener`: tên listener ổn định.
- `event.type`: tên event đã chuẩn hóa hoặc thuộc allowlist.
- `outcome`: success, failure, retry hoặc skipped theo định nghĩa rõ.
- `destination`: tên logic của destination đã cấu hình.
- `exception`: nhóm exception ổn định, không dùng message đầy đủ.

Không dùng các giá trị có thể thay đổi liên tục hoặc có số lượng lớn làm tag:

- `eventId`, `orderId`, `customerId`, `correlationId`.
- Email, số điện thoại, tenant ID không giới hạn hoặc dữ liệu cá nhân.
- Exception message chứa giá trị động.
- URL đầy đủ có query string hoặc request body.

Đặt các định danh duy nhất trong structured log hoặc trace attribute có kiểm soát thay vì metric label. Nếu cần lọc theo event ID, operator có thể tìm log/trace theo ID sau khi mở dashboard chi tiết.

## 8. Alert theo SLO và ngưỡng vận hành

Alert nên gắn với tác động và khả năng hành động. Tránh gửi cảnh báo chỉ vì một lần xử lý thất bại nếu hệ thống tự retry và phục hồi trong SLA.

| Tín hiệu | Ví dụ điều kiện cảnh báo | Hành động ban đầu |
| --- | --- | --- |
| Oldest pending age | Vượt thời gian xử lý cho phép của luồng nghiệp vụ | Kiểm tra listener, dependency và retry backlog |
| Pending count | Tăng liên tục qua nhiều cửa sổ đo | Xác định listener gây backlog và khả năng xử lý |
| Listener failure rate | Vượt ngưỡng trong một khoảng thời gian đủ dài | Phân loại exception và xem trace/log mẫu |
| Processing latency | p95/p99 vượt SLO | Tìm bước chậm, database hoặc dependency ngoài |
| Externalization failure | Producer send lỗi kéo dài | Kiểm tra kết nối broker, ACL, serializer và adapter |
| Consumer lag | Tăng và không giảm theo thời gian | Kiểm tra consumer health, throughput và partition assignment |
| DLT/quarantine growth | Có message mới hoặc số lượng tăng bất thường | Phân loại lỗi, kiểm tra payload và quy trình replay |

Ngưỡng phải dựa trên SLA/SLO của từng luồng. Ví dụ, một event cập nhật dashboard báo cáo có thể chấp nhận độ trễ dài hơn event khởi tạo giao hàng. Không có một ngưỡng pending hoặc latency chung phù hợp với mọi event.

Alert cần có owner, mức độ ưu tiên, runbook và liên kết tới dashboard/trace. Dùng cửa sổ đánh giá và điều kiện kéo dài phù hợp để giảm cảnh báo chập chờn. Có thể dùng multi-window alerting để phát hiện cả lỗi tăng đột biến lẫn suy giảm kéo dài.

## 9. Liên kết metrics, logs và traces

Metrics cho biết vấn đề xảy ra ở đâu và có quy mô thế nào. Log giải thích một lần xử lý cụ thể. Trace cho thấy đường đi qua các thành phần và thời gian ở từng bước.

Mỗi lần xử lý nên ghi các trường phù hợp:

- `event.id`: định danh event ổn định.
- `event.type`: loại event.
- `listener`: tên listener xử lý.
- `aggregate.id` và `aggregate.version`: đối tượng nghiệp vụ và phiên bản nếu có.
- `correlation.id`: liên kết các thao tác thuộc cùng một quy trình.
- `causation.id`: event hoặc command dẫn tới event hiện tại nếu hệ thống có theo dõi.
- `attempt`: lần xử lý hoặc retry.
- `outcome`: success/failure và nhóm lỗi.

Không đặt các ID này thành metric label có cardinality cao. Dùng structured logging và tracing để tìm theo ID. Khi event đi qua broker, truyền trace context qua header theo chuẩn tracing mà các service cùng hỗ trợ.

## 10. Dashboard cho Event Publication Registry

Registry là nguồn quan trọng để quan sát publication tới listener. Dashboard có thể trình bày:

1. Tổng publication đang pending và đã hoàn tất theo khoảng thời gian.
2. Pending publication theo listener và event type.
3. Tuổi publication pending lâu nhất.
4. Xu hướng pending tăng/giảm.
5. Danh sách publication cũ cần điều tra nếu persistence adapter cung cấp thông tin chi tiết.

Không truy vấn bảng nội bộ của registry bằng SQL tự viết nếu chưa hiểu schema và phiên bản persistence adapter. Ưu tiên API hoặc cơ chế truy vấn được Spring Modulith và adapter đang dùng hỗ trợ. Nếu cần dashboard chi tiết hơn, có thể xây dựng một read model vận hành từ dữ liệu được công bố hoặc từ persistence abstraction ổn định.

Publication đã hoàn tất có thể được dọn theo retention. Dashboard lịch sử dài hạn vì thế cần metrics được lưu ở hệ thống monitoring hoặc audit riêng; không dựa vào việc giữ mọi publication hoàn tất vô thời hạn trong registry.

## 11. Quy trình điều tra từ dashboard

Khi alert xuất hiện, operator có thể đi theo trình tự:

1. **Xác định phạm vi:** event type, listener, destination và thời điểm bắt đầu bất thường.
2. **Kiểm tra backlog:** pending count, oldest pending age và xu hướng tăng/giảm.
3. **Phân loại lỗi:** xem exception class, status code, retry attempt và trace mẫu.
4. **Xác định ranh giới lỗi:** publisher/registry, listener nội bộ, externalization adapter, broker hay consumer.
5. **Kiểm tra dependency:** database, HTTP service, KMS, broker, credential hoặc network.
6. **Chọn hành động:** chờ retry, khôi phục dependency, điều chỉnh capacity hoặc chuyển message lỗi vào quarantine theo quy trình.
7. **Xác minh phục hồi:** pending giảm, processing latency trở lại SLO, consumer lag giảm và nghiệp vụ đạt trạng thái mong đợi.

Không xóa publication pending hoặc DLT chỉ để làm dashboard xanh. Trước khi resubmit/replay, xác định listener hoặc consumer đã tạo side effect chưa và bảo đảm idempotency để tránh xử lý trùng.

## 12. Kiểm thử dashboard và dữ liệu quan sát

Dashboard cần được kiểm thử cùng instrumentation để bảo đảm số liệu có ý nghĩa:

- Publish event và xác minh counter tăng đúng một lần theo định nghĩa.
- Listener thành công và thất bại ghi outcome tương ứng.
- Listener chậm làm duration và lag tăng theo cách dự kiến.
- Publication pending làm pending count/age phản ánh đúng.
- Retry làm attempt tăng nhưng không làm số event nghiệp vụ bị đếm thành nhiều event mới.
- Externalization gửi thành công không tự làm consumer lag bằng 0.
- Event ID và correlation ID xuất hiện trong log/trace nhưng không trở thành metric tag.
- Alert kích hoạt theo SLO và có liên kết runbook.

Kiểm thử nên xác minh metric name, tag và đơn vị; tránh chỉ so sánh chuỗi dashboard. Khi thay đổi listener hoặc event type, cập nhật quy ước instrumentation để biểu đồ không bị chia thành nhiều series không cần thiết.

## 13. Bảo mật dashboard vận hành

Dashboard có thể tiết lộ cấu trúc hệ thống, loại nghiệp vụ, tần suất giao dịch và trạng thái dependency. Vì vậy:

- Yêu cầu xác thực và phân quyền theo vai trò operator.
- Tách quyền xem metrics tổng hợp khỏi quyền xem log/trace chi tiết.
- Che hoặc loại payload, thông tin cá nhân, token và credential.
- Giới hạn quyền truy vấn DLT và publication detail.
- Audit thao tác resubmit, replay, purge hoặc thay đổi trạng thái.
- Bảo vệ endpoint Actuator; chỉ expose những endpoint cần thiết qua mạng quản trị.

Dashboard chỉ nên hỗ trợ quan sát theo quyền được cấp. Hành động thay đổi dữ liệu hoặc replay event cần quy trình riêng, xác nhận và audit phù hợp.

## 14. Những sai lầm cần tránh

- Coi publication hoàn tất là consumer bên ngoài đã xử lý xong.
- Chỉ hiển thị tổng số event mà không tách listener, destination và consumer.
- Dùng event ID, order ID hoặc tenant ID làm metric label.
- Đo processing duration rồi gọi nhầm là end-to-end event lag.
- Đếm một event nhiều listener thành nhiều event nghiệp vụ mà không ghi rõ đơn vị.
- Dùng một ngưỡng alert cho mọi loại event.
- Đọc trực tiếp schema nội bộ của registry mà không xét adapter/version.
- Đưa payload nhạy cảm vào dashboard, log hoặc trace.
- Xóa pending/DLT để làm sạch số liệu thay vì xử lý nguyên nhân.

## Kết luận

Dashboard vận hành cho Spring Modulith cần cho thấy event đang ở đâu trong vòng đời: publication, listener, externalization, broker hay consumer. Kết hợp Event Publication Registry với Micrometer, logs, traces, broker metrics và trạng thái nghiệp vụ để đo backlog, tuổi publication, processing latency, lỗi, retry và consumer lag. Dùng tag có cardinality thấp, alert theo SLO và runbook rõ ràng để operator có thể tìm đúng ranh giới lỗi, phục hồi an toàn và xác minh hệ thống đã hội tụ.
