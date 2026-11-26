# Thiết kế retry an toàn

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua hợp đồng sự kiện, giảm phụ thuộc trực tiếp và giữ ranh giới nghiệp vụ. Khi listener hoặc hệ thống bên ngoài gặp lỗi, retry cho phép ứng dụng thử lại công việc chưa hoàn tất. Tuy nhiên, retry chỉ an toàn khi ứng dụng kiểm soát được hiệu ứng lặp, thứ tự xử lý, thời gian chờ và trạng thái publication.

Một chiến lược retry thiếu kiểm soát có thể tạo ra đơn hàng trùng, trừ tiền nhiều lần, gửi thông báo lặp hoặc làm quá tải dependency đang gặp sự cố. Vì vậy, retry phải được thiết kế cùng idempotency, transaction, backoff, giới hạn số lần thử và quy trình xử lý lỗi không thể phục hồi.

## 1. Retry giải quyết vấn đề gì?

Trong một luồng event-driven, transaction nghiệp vụ có thể commit thành công nhưng listener xử lý event thất bại. Ví dụ, module Orders ghi nhận đơn hàng đã thanh toán rồi phát event OrderPaid. Listener cập nhật read model hoặc gửi thông tin sang module khác. Nếu listener gặp timeout hoặc database tạm thời không truy cập được, công việc chưa hoàn tất cần được thử lại.

Các lỗi thường gặp gồm:

- Timeout hoặc mất kết nối tạm thời tới database, broker hay API.
- Dịch vụ phụ thuộc trả về lỗi quá tải hoặc throttling.
- Deadlock hoặc transaction bị rollback do cạnh tranh.
- Process dừng giữa chừng khi đang xử lý event.
- Consumer nhận event nhưng không thể hoàn thành side effect.
- Lỗi cấu hình, dữ liệu không hợp lệ hoặc lỗi lập trình khiến xử lý không thể thành công dù thử lại.

Retry phù hợp với lỗi có khả năng tự phục hồi. Nó không tự sửa dữ liệu sai, credential hết hạn hoặc bug trong code. Trước khi thử lại, ứng dụng cần phân loại lỗi và quyết định lỗi nào có thể retry, lỗi nào cần dừng hoặc chuyển sang xử lý thủ công.

## 2. Xác định ranh giới transaction và publication

Với application event được phát trong một transaction nghiệp vụ, cần hiểu thời điểm listener chạy và trạng thái publication được theo dõi như thế nào. Listener đồng bộ có thể chạy trong luồng phát event; listener xử lý sau commit chỉ được thực hiện sau khi transaction phát event commit thành công.

Ví dụ một event nghiệp vụ:

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    Instant paidAt,
    BigDecimal amount
) {}
~~~

Một listener xử lý sau commit có thể cập nhật read model:

~~~java
@Component
class OrderPaidProjection {

    private final OrderSummaryRepository summaries;

    OrderPaidProjection(OrderSummaryRepository summaries) {
        this.summaries = summaries;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        summaries.markPaid(
            event.orderId(),
            event.paidAt(),
            event.amount()
        );
    }
}
~~~

Đây là ví dụ minh họa listener; transaction và persistence cần được cấu hình theo yêu cầu của ứng dụng. Nếu listener thất bại, application event không làm transaction nghiệp vụ ban đầu tự động rollback sau khi transaction đó đã commit. Ứng dụng cần một cơ chế theo dõi và phục hồi publication.

Spring Modulith Event Publication Registry theo dõi việc giao event tới listener. Với cấu hình persistence phù hợp, registry lưu trạng thái publication để nhận biết publication đã hoàn tất hoặc còn incomplete. Khi listener xử lý thành công, publication được đánh dấu hoàn tất; khi listener thất bại, publication có thể còn lại để phục hồi.

Registry không tự quyết định toàn bộ chính sách retry cho mọi lỗi. Ứng dụng vẫn phải xác định khi nào resubmit, loại lỗi nào được thử lại, khoảng chờ và giới hạn retry. Cũng cần phân biệt registry với event store: registry theo dõi publication, không mặc định lưu toàn bộ lịch sử event nghiệp vụ.

## 3. Phân loại lỗi trước khi retry

Không nên bắt mọi exception rồi retry giống nhau. Một cách phân loại đơn giản:

| Nhóm lỗi | Ví dụ | Chính sách phù hợp |
|---|---|---|
| Tạm thời | Timeout, connection reset, deadlock | Retry với backoff |
| Quá tải/throttling | HTTP 429, HTTP 503, broker unavailable | Retry có giới hạn, tôn trọng Retry-After nếu có |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, giá trị sai miền | Dừng retry tự động, chuyển quarantine hoặc xử lý nghiệp vụ |
| Quyền truy cập/cấu hình | Credential hết hạn, ACL thiếu quyền, endpoint sai | Cảnh báo và chờ sửa cấu hình; retry chỉ khi có cơ chế tự khôi phục |
| Lỗi lập trình | Null không mong đợi, invariant bị vi phạm | Dừng hoặc giới hạn rất chặt; cần sửa code |
| Xung đột nghiệp vụ | Đơn đã bị hủy, trạng thái không cho phép chuyển tiếp | Xử lý theo quy tắc nghiệp vụ, không retry vô hạn |

Một policy có thể sử dụng các exception cụ thể thay vì dựa trên message text. Message có thể thay đổi theo phiên bản thư viện hoặc ngôn ngữ, trong khi loại exception và mã lỗi thường ổn định hơn.

Ví dụ phân loại:

~~~java
enum FailureKind {
    TRANSIENT,
    RATE_LIMITED,
    PERMANENT,
    UNKNOWN
}

FailureKind classify(Throwable error) {
    if (error instanceof SocketTimeoutException
            || error instanceof ConnectException
            || error instanceof TransientDataAccessException) {
        return FailureKind.TRANSIENT;
    }

    if (error instanceof RateLimitExceededException) {
        return FailureKind.RATE_LIMITED;
    }

    if (error instanceof InvalidEventException
            || error instanceof BusinessRuleViolationException) {
        return FailureKind.PERMANENT;
    }

    return FailureKind.UNKNOWN;
}
~~~

Các exception trong ví dụ đại diện cho loại lỗi của ứng dụng hoặc thư viện cụ thể. Cần bổ sung mapping cho database driver, HTTP client và Kafka client đang dùng. Với lỗi chưa phân loại, chính sách an toàn thường là ghi nhận và cảnh báo thay vì retry vô hạn.

## 4. Bảo đảm idempotency trước khi bật retry

Retry có thể khiến cùng một event được giao nhiều lần. Điều này có thể xảy ra khi listener đã thực hiện side effect nhưng process dừng trước khi publication được đánh dấu hoàn tất. Khi phục hồi, ứng dụng không luôn biết chắc side effect trước đó đã hoàn tất tới đâu.

Vì vậy, consumer hoặc listener cần idempotent: xử lý lại cùng một event không làm thay đổi kết quả nghiệp vụ thêm lần nữa.

Một event nên có định danh ổn định:

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    Instant paidAt,
    BigDecimal amount
) {}
~~~

Không tạo event ID mới mỗi lần retry. Các lần giao lại phải đại diện cho cùng một sự kiện nghiệp vụ.

Một bảng inbox có thể lưu event đã xử lý:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Listener ghi nhận event ID cùng thay đổi projection trong một transaction:

~~~java
@Transactional
void apply(OrderPaid event) {
    boolean firstDelivery = processedEvents.insertIfAbsent(
        "order-summary",
        event.eventId()
    );

    if (!firstDelivery) {
        return;
    }

    summaries.markPaid(
        event.orderId(),
        event.paidAt(),
        event.amount()
    );
}
~~~

Phương thức insertIfAbsent là abstraction do ứng dụng định nghĩa; nó cần dựa vào unique constraint để xử lý cạnh tranh. Ghi inbox và cập nhật projection phải cùng transaction nếu cùng database. Nếu transaction rollback, cả hai thao tác rollback. Nếu event đã được xử lý và transaction commit, lần giao lại sẽ nhận biết event ID đã tồn tại.

Idempotency ở listener không tự động bảo vệ side effect tới hệ thống ngoài. Khi gọi API thanh toán, email hoặc dịch vụ khác, hãy dùng idempotency key do dịch vụ đích hỗ trợ hoặc một quy trình đối soát riêng. Không giả định transaction database nội bộ có thể rollback một request HTTP đã được hệ thống ngoài thực hiện.

## 5. Chọn backoff để tránh tạo thêm tải

Backoff là khoảng chờ giữa các lần retry. Retry liên tục có thể làm dependency đang quá tải chịu thêm request, khiến sự cố kéo dài. Có ba chiến lược phổ biến:

| Chiến lược | Cách tính | Đặc điểm |
|---|---|---|
| Fixed delay | Chờ cùng một khoảng thời gian | Đơn giản, phù hợp tác vụ ít tải |
| Linear backoff | Khoảng chờ tăng đều theo số lần lỗi | Tăng tải chậm và dễ dự đoán |
| Exponential backoff | Khoảng chờ tăng theo cấp số nhân | Giảm tần suất khi lỗi kéo dài |

Exponential backoff có thể được tính như sau:

d(n) = min(d_max, d_0 × m^(n - 1))

Trong đó n là số lần thất bại, d0 là khoảng chờ ban đầu, m là hệ số nhân lớn hơn 1 và dmax là giới hạn trên.

Ví dụ, bắt đầu 1 giây, nhân đôi mỗi lần và giới hạn 60 giây:

| Lần thất bại | Khoảng chờ |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| 6 | 32 giây |
| 7 trở đi | 60 giây |

Khi nhiều instance cùng retry, chúng có thể đồng bộ và gửi lại cùng lúc. **Jitter** thêm độ ngẫu nhiên vào khoảng chờ để phân tán request. Ví dụ, với jitter 20%, chọn một thời gian trong khoảng 80% đến 120% của khoảng chờ cơ sở rồi giới hạn theo max delay.

~~~java
Duration exponentialDelay(
        int failedAttempts,
        Duration initialDelay,
        Duration maxDelay,
        double multiplier) {

    if (failedAttempts < 1) {
        throw new IllegalArgumentException("failedAttempts must be positive");
    }

    double calculated = initialDelay.toMillis()
        * Math.pow(multiplier, failedAttempts - 1);

    long bounded = Math.min(
        maxDelay.toMillis(),
        (long) calculated
    );

    return Duration.ofMillis(Math.max(1, bounded));
}
~~~

Đây là hàm tính khoảng chờ cơ sở, chưa bao gồm jitter. Trong production cần kiểm tra tham số đầu vào, xử lý overflow, giới hạn số lần thử và dùng clock được inject để tính thời điểm tiếp theo. Không dùng Thread.sleep trong listener để chờ backoff vì nó giữ thread và làm mất lịch retry khi process dừng.

Nếu dịch vụ trả về Retry-After, nên tôn trọng thời điểm đó. Chính sách nội bộ có thể chọn thời điểm muộn hơn giữa thời điểm dịch vụ yêu cầu và thời điểm backoff tính được, theo giới hạn vận hành đã định.

## 6. Giới hạn số lần thử và tổng thời gian retry

Retry không nên kéo dài vô hạn. Cần có ngân sách retry được định nghĩa theo nghiệp vụ và SLA:

- Số lần thử tối đa.
- Khoảng chờ tối đa.
- Tổng thời gian publication được phép chưa hoàn tất.
- Những loại lỗi được retry tự động.
- Thời gian tối đa để xử lý một lần thử.
- Hành động khi hết ngân sách.

Số lần thử và tổng thời gian retry là hai giới hạn khác nhau. Nếu khoảng chờ tăng theo cấp số nhân, một số lần retry có thể kéo dài nhiều phút hoặc nhiều giờ. Hãy tính tổng thời gian dự kiến để bảo đảm nó phù hợp với thời hạn nghiệp vụ.

Ví dụ, event cập nhật trạng thái đơn hàng có thể được retry trong vài phút. Một event kích hoạt thanh toán hoặc cấp quyền có thể có SLA khác và cần cảnh báo sớm hơn. Không dùng cùng một policy cho mọi event nếu độ quan trọng và khả năng phục hồi khác nhau.

Khi hết ngân sách, chuyển publication sang trạng thái cần can thiệp, ghi nhận lỗi cuối cùng và phát cảnh báo. Không xóa publication incomplete chỉ để giảm số lượng backlog. Người vận hành cần có khả năng xem event ID, listener, số lần thử, loại lỗi và thời điểm thất bại.

## 7. Lưu trạng thái retry bền vững

Nếu retry chỉ được lưu trong bộ nhớ, lịch retry sẽ mất khi process restart. Với tác vụ cần phục hồi qua restart, trạng thái retry cần được lưu bền vững.

Một bản ghi retry có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| publication_id | Định danh publication được theo dõi |
| listener_id | Listener nhận event |
| failed_attempts | Số lần thất bại đã ghi nhận |
| next_attempt_at | Thời điểm sớm nhất được phép thử lại |
| last_error_code | Mã lỗi gần nhất |
| last_error_message | Thông tin lỗi đã rút gọn |
| state | PENDING, EXHAUSTED hoặc MANUAL_REVIEW |
| lease_until | Thời hạn worker đang giữ quyền xử lý |
| updated_at | Thời điểm cập nhật trạng thái |

Một coordinator định kỳ có thể tìm các publication đến hạn, claim chúng bằng lease hoặc khóa, rồi thực hiện resubmit:

~~~text
Retry scheduler
      |
      v
Find due publications
      |
      v
Claim with lease
      |
      v
Check status and failure policy
      |
      +---- budget exhausted ---> MANUAL_REVIEW + alert
      |
      v
Resubmit publication
      |
      v
Listener processes event
      |
      +---- success -----------> Registry marks complete
      |
      +---- failure -----------> Record attempt and next backoff
~~~

Cần thiết kế claim để nhiều instance không cùng resubmit một publication. Lease phải có thời hạn để instance khác có thể tiếp quản khi worker bị dừng. Nếu listener chạy bất đồng bộ, lời gọi resubmit kết thúc không đồng nghĩa xử lý event đã thành công; cần chờ trạng thái publication thực tế.

Event Publication Registry cung cấp trạng thái publication theo cơ chế của Spring Modulith. Bảng retry riêng chỉ nên được bổ sung khi ứng dụng cần lưu policy hoặc metadata mà registry không cung cấp. Tránh tạo hai nguồn trạng thái mâu thuẫn; xác định registry là nguồn trạng thái giao event và coordinator dùng metadata retry để quyết định thời điểm resubmit.

## 8. Tránh retry đồng thời và retry storm

Trong môi trường nhiều instance, cùng một publication có thể được nhiều worker nhìn thấy là đến hạn. Nếu không có cơ chế claim, nhiều instance có thể gửi lại cùng event cùng lúc.

Các biện pháp thường dùng:

- Claim bản ghi bằng transaction ngắn với row lock hoặc atomic update.
- Dùng lease có thời hạn và owner ID của worker.
- Giới hạn concurrency toàn cục hoặc theo dependency.
- Giới hạn số publication được xử lý trong mỗi batch.
- Dùng jitter để phân tán thời điểm retry.
- Có circuit breaker hoặc cơ chế pause khi dependency đang lỗi diện rộng.
- Đảm bảo lease được giải phóng hoặc hết hạn khi worker crash.

Circuit breaker và retry có vai trò khác nhau. Retry thử lại một thao tác sau lỗi; circuit breaker tạm ngăn request mới tới dependency đang có tỷ lệ lỗi cao. Kết hợp cả hai có thể giảm tải khi sự cố kéo dài, nhưng phải có trạng thái half-open hoặc cơ chế kiểm tra phục hồi để hệ thống tự hoạt động lại.

Không retry tất cả publication trong một vòng lặp không giới hạn. Backlog lớn cần được drain theo tốc độ mà dependency và consumer có thể tiếp nhận. Nếu retry làm nghẽn luồng event mới, hãy tách worker hoặc giới hạn tài nguyên riêng cho recovery.

## 9. Giữ thứ tự và xử lý event poison

Retry có thể làm thay đổi thứ tự xử lý. Giả sử aggregate phát các event với version 10, 11 và 12. Event 10 thất bại nhưng event 11 và 12 vẫn được áp dụng. Khi event 10 được retry sau đó, projection có thể bị lùi hoặc trạng thái không còn hợp lệ.

Nếu thứ tự là bắt buộc, cần:

- Dùng aggregate ID hoặc khóa nghiệp vụ để phân vùng công việc.
- Theo dõi aggregate version hoặc sequence.
- Không xử lý event sau khi còn event trước chưa hoàn tất nếu nghiệp vụ yêu cầu tuần tự.
- Thiết kế handler phát hiện version bị thiếu hoặc event cũ.
- Có chính sách xử lý poison event để không khóa vô hạn toàn bộ luồng.

Poison event là event liên tục thất bại do payload không hợp lệ, schema không tương thích hoặc lỗi nghiệp vụ không thể phục hồi. Retry vô hạn một poison event sẽ chiếm tài nguyên và có thể chặn các event tiếp theo cùng aggregate.

Sau số lần thử đã định, có thể chuyển event sang quarantine hoặc dead-letter queue/topic, lưu payload và metadata cần thiết, đồng thời cảnh báo owner. Chỉ tiếp tục event sau nếu nghiệp vụ cho phép. Với luồng cần thứ tự nghiêm ngặt, cần dừng aggregate hoặc partition liên quan cho đến khi event lỗi được xử lý; không âm thầm bỏ qua.

## 10. Retry ở producer và consumer

Cần phân biệt retry ở các ranh giới:

| Nơi retry | Lỗi được xử lý | Cơ chế theo dõi |
|---|---|---|
| Application listener | Listener xử lý event thất bại | Event Publication Registry và recovery policy |
| Externalization producer | Gửi event tới broker hoặc endpoint thất bại | Publication state, producer acknowledgment và retry |
| Kafka producer client | Lỗi gửi tạm thời trong quá trình producer retry | Producer config, delivery timeout và send result |
| Kafka consumer | Consumer xử lý record thất bại | Consumer retry policy, offset và DLT |
| API downstream | Hệ thống ngoài không phản hồi hoặc trả lỗi | Retry client, idempotency key và timeout |

Không cộng dồn retry ở mọi tầng mà không tính tổng số lần. Ví dụ, listener retry 5 lần, Kafka producer retry 5 lần và HTTP client retry 5 lần có thể tạo ra nhiều request hơn dự kiến. Định nghĩa retry budget theo toàn bộ luồng hoặc ít nhất ghi rõ mỗi tầng có ngân sách riêng.

Kafka producer idempotence giúp hạn chế duplicate do retry nội bộ producer theo semantics Kafka. Nó không thay thế idempotency ở consumer và không bảo đảm một side effect ngoài Kafka chỉ xảy ra một lần. Tương tự, Event Publication Registry theo dõi publication của listener nhưng không thay thế consumer offset hoặc inbox ở hệ thống nhận.

## 11. Kết hợp retry với compensation

Retry phù hợp khi thao tác chưa hoàn thành do lỗi tạm thời và có thể thực hiện lại an toàn. Compensation phù hợp khi một bước nghiệp vụ đã tạo ra hiệu ứng cần được hoàn tác hoặc bù bằng một hành động nghiệp vụ khác.

Ví dụ, hệ thống giữ chỗ thành công nhưng dịch vụ thanh toán tạm thời không phản hồi. Trước hết có thể retry yêu cầu thanh toán bằng cùng idempotency key. Nếu hết thời hạn nghiệp vụ và quyết định hủy đơn, hệ thống có thể phát event giải phóng chỗ. Đây là compensation vì nó thay đổi trạng thái nghiệp vụ để bù cho bước trước.

Không chạy compensation chỉ vì một lần timeout. Dịch vụ đích có thể đã hoàn tất thao tác nhưng phản hồi bị mất. Cần đối soát theo transaction ID hoặc idempotency key trước khi quyết định thử lại hay bù trừ.

Một quy trình có thể là:

1. Thử lại lỗi tạm thời trong retry budget.
2. Đối soát trạng thái dịch vụ ngoài khi kết quả không rõ.
3. Nếu thao tác chưa hoàn thành và còn thời gian, tiếp tục retry.
4. Nếu nghiệp vụ hết hạn hoặc không thể tiếp tục, khởi chạy compensation theo quy tắc đã định.
5. Ghi audit cho cả retry lẫn compensation.

## 12. Quan sát retry và hỗ trợ vận hành

Retry cần được quan sát như một luồng công việc riêng. Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Incomplete publication count | Số publication chưa hoàn tất |
| Oldest incomplete age | Tuổi publication lâu nhất |
| Retry attempts by listener | Listener nào thường xuyên thất bại |
| Retry success rate | Tỷ lệ phục hồi sau retry |
| Exhausted count | Publication đã hết ngân sách |
| Retry delay distribution | Khoảng chờ thực tế |
| Dependency error rate | Dependency nào đang gây lỗi |
| Queue/backlog size | Công việc đang chờ xử lý |
| Poison event count | Event cần quarantine hoặc can thiệp |

Log nên có event ID, publication ID, listener ID, aggregate ID/version, attempt hiện tại, next attempt time, failure kind và correlation ID. Ghi stack trace ở nơi phù hợp nhưng tránh lặp log đầy đủ ở mọi tầng. Không ghi credential, token hoặc payload nhạy cảm.

Cảnh báo nên dựa trên tuổi publication, tỷ lệ lỗi và backlog tăng liên tục, không chỉ một lần thất bại. Với event quan trọng, có thể cảnh báo khi publication chưa hoàn tất vượt SLA hoặc chuyển sang MANUAL_REVIEW.

## 13. Kiểm thử retry an toàn

Một bộ kiểm thử cần chứng minh rằng retry phục hồi được lỗi mà không tạo side effect trùng:

1. Lỗi tạm thời ở lần đầu, lần sau thành công; publication cuối cùng được đánh dấu hoàn tất.
2. Lỗi vĩnh viễn không bị retry vô hạn.
3. Backoff tăng theo policy và không vượt max delay.
4. Jitter nằm trong khoảng cấu hình.
5. Hết retry budget thì publication được chuyển sang trạng thái cần can thiệp và phát cảnh báo.
6. Giao cùng event nhiều lần không làm thay đổi kết quả nghiệp vụ nhiều lần.
7. Process dừng sau side effect nhưng trước khi registry cập nhật; lần giao lại vẫn idempotent.
8. Nhiều worker cùng nhìn thấy một publication đến hạn nhưng chỉ một worker claim được.
9. Lease hết hạn sau worker crash và worker khác có thể tiếp quản.
10. Event version sai thứ tự được phát hiện theo policy.
11. Poison event được quarantine hoặc dừng đúng phạm vi.
12. Restart không làm mất trạng thái retry nếu state được lưu bền vững.

Dùng Clock giả để kiểm thử nextAttemptAt mà không cần chờ thời gian thật. Với jitter, inject nguồn ngẫu nhiên để test có thể lặp lại. Integration test cần kiểm tra transaction, Event Publication Registry, adapter và side effect thực tế ở mức phù hợp.

## 14. Checklist trước khi bật retry trong production

Trước khi bật retry cho listener hoặc externalization flow, hãy xác nhận:

- Lỗi nào được xem là tạm thời, lỗi nào là vĩnh viễn.
- Listener có idempotent không và event ID được giữ ổn định qua retry không.
- Side effect nội bộ và bên ngoài được bảo vệ bằng transaction hoặc idempotency key như thế nào.
- Retry budget, timeout, backoff, jitter và max delay có phù hợp SLA không.
- Trạng thái publication và lịch retry có được lưu bền vững không.
- Nhiều instance có thể claim cùng publication hay không.
- Event ordering và aggregate version được xử lý thế nào.
- Poison event được quarantine, cảnh báo và replay ra sao.
- Retry có làm quá tải dependency hoặc chặn event mới không.
- Metrics, logs, dashboard, owner và runbook đã sẵn sàng chưa.

Thiết kế retry an toàn bắt đầu từ việc giả định event có thể được giao lại và side effect có thể đã xảy ra trước khi lỗi được ghi nhận. Khi phân loại lỗi, giữ event ID ổn định, bảo vệ listener bằng idempotency, dùng backoff có giới hạn, lưu trạng thái bền vững và có quy trình xử lý poison event, các module Spring Modulith có thể phục hồi sau lỗi mà vẫn bảo vệ tính nhất quán của dữ liệu nghiệp vụ.

