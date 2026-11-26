# Backoff khi thử lại application events

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua những sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và giữ ranh giới module rõ ràng. Khi listener xử lý sự kiện sau commit gặp lỗi, cơ chế retry giúp khôi phục công việc. **Backoff** quyết định khoảng chờ giữa các lần thử lại, để hệ thống có thời gian hồi phục và tránh tạo thêm tải lên dịch vụ đang gặp sự cố.

Backoff là một phần của chiến lược retry. Nó cần đi cùng việc phân loại lỗi, giới hạn số lần thử, lưu trạng thái đủ bền vững, chống xử lý trùng và khả năng quan sát. Nếu chỉ lặp lại listener liên tục, hệ thống có thể biến một lỗi tạm thời thành sự cố lan rộng.

## 1. Backoff nằm ở đâu trong vòng đời event?

Một event được publish trong luồng nghiệp vụ. Với listener xử lý sau commit, listener chỉ chạy khi transaction phát event đã commit thành công. Spring Modulith Event Publication Registry theo dõi publication của listener; publication được đánh dấu hoàn tất khi listener xử lý thành công. Nếu listener thất bại, publication chưa hoàn tất có thể được phát hiện và gửi lại.

Vòng đời retry có backoff thường diễn ra như sau:

~~~mermaid
flowchart TD
    A[Transaction publish event] --> B[Publication được ghi nhận]
    B --> C[Listener xử lý sau commit]
    C -->|Thành công| D[Publication hoàn tất]
    C -->|Lỗi tạm thời| E[Lưu lần lỗi và thời điểm retry]
    E --> F[Chờ đến nextAttemptAt]
    F --> G[Resubmit publication]
    G --> C
    C -->|Lỗi vĩnh viễn hoặc hết ngân sách| H[Đưa vào xử lý thủ công hoặc bù trừ]
~~~

Cần phân biệt ba khái niệm:

- **Publication** là lần giao một event tới một listener. Một event có thể tạo ra nhiều publication nếu có nhiều listener quan tâm.
- **Retry** là việc thực hiện lại một publication chưa hoàn tất sau khi xác định lỗi có thể phục hồi.
- **Backoff** là chính sách tính thời điểm được phép retry tiếp theo.

Event Publication Registry cung cấp dấu vết về các publication chưa hoàn tất và khả năng phục hồi chúng. Ứng dụng vẫn cần quyết định lỗi nào được retry, chờ bao lâu, tối đa bao nhiêu lần và khi nào chuyển sang xử lý thủ công. Khi cần phục hồi sau khi process khởi động lại, registry phải được cấu hình với kho lưu trữ bền vững phù hợp; trạng thái chỉ nằm trong bộ nhớ không đủ để bảo đảm phục hồi qua lần restart.

## 2. Chọn chiến lược backoff

Có một số chiến lược phổ biến:

| Chiến lược | Cách tính | Khi phù hợp |
|---|---|---|
| Fixed delay | Mỗi lần chờ cùng một khoảng thời gian | Tác vụ ít tải, lỗi có thời gian hồi phục ổn định |
| Linear backoff | Khoảng chờ tăng đều theo số lần lỗi | Muốn tăng thời gian chờ từ từ và dễ dự đoán |
| Exponential backoff | Khoảng chờ tăng theo cấp số nhân | Dịch vụ phụ thuộc có thể quá tải hoặc gián đoạn không rõ thời lượng |
| Exponential backoff with jitter | Exponential cộng thêm độ ngẫu nhiên | Nhiều instance có thể retry cùng lúc |

Với exponential backoff, gọi **n** là số lần thất bại đã ghi nhận, bắt đầu từ 1. Khoảng chờ cơ sở được tính như sau:

d(n) = min(d_max, d_0 × m^(n - 1))

Trong đó:

- **d_0** là khoảng chờ ban đầu.
- **m** là hệ số nhân, thường lớn hơn 1.
- **d_max** là khoảng chờ tối đa.

Ví dụ dùng khoảng chờ ban đầu 2 giây, hệ số nhân 2 và giới hạn 5 phút:

| Lần thất bại | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 2 giây |
| 2 | 4 giây |
| 3 | 8 giây |
| 4 | 16 giây |
| 5 | 32 giây |
| 6 | 64 giây |
| 7 | 128 giây |
| 8 | 256 giây |
| 9 trở đi | 300 giây |

Giới hạn trên ngăn thời gian chờ tăng vô hạn. Tuy nhiên, exponential backoff đơn thuần vẫn có thể khiến nhiều instance cùng retry tại những thời điểm giống nhau. Hiện tượng đó thường được gọi là *thundering herd*.

Jitter thêm một yếu tố ngẫu nhiên vào khoảng chờ. Ví dụ với jitter 20%, hệ thống chọn một giá trị trong khoảng 80% đến 120% của khoảng chờ cơ sở, sau đó vẫn giới hạn ở **maxDelay**. Nhờ vậy các instance phân tán lần retry theo thời gian.

Không nên đặt khoảng chờ quá ngắn chỉ để giảm độ trễ. Nếu dịch vụ đích đang quá tải, retry dày sẽ làm tăng cạnh tranh tài nguyên, số kết nối và hàng đợi. Hãy chọn khoảng chờ dựa trên đặc tính dịch vụ, thời gian phục hồi dự kiến và ngân sách độ trễ của nghiệp vụ.

## 3. Phân loại lỗi trước khi áp dụng backoff

Backoff không biến mọi lỗi thành lỗi có thể phục hồi. Trước khi lên lịch retry, listener hoặc lớp điều phối cần phân loại nguyên nhân:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout mạng, kết nối bị ngắt, HTTP 503, database deadlock | Retry có backoff và giới hạn số lần |
| Bị giới hạn tốc độ | HTTP 429 hoặc thông báo throttling | Tôn trọng **Retry-After** nếu dịch vụ cung cấp; áp dụng backoff và giới hạn tải |
| Cấu hình hoặc quyền truy cập | Credential hết hạn, thiếu quyền, endpoint sai | Chỉ retry nếu có cơ chế sửa lỗi tự động; nếu không, cảnh báo và chờ can thiệp |
| Dữ liệu hoặc nghiệp vụ không hợp lệ | Thiếu trường bắt buộc, trạng thái nghiệp vụ không cho phép | Không retry vô hạn; chuyển sang xử lý lỗi nghiệp vụ hoặc quy trình bù trừ phù hợp |
| Lỗi lập trình | Null không mong đợi, mapping sai, invariant bị vi phạm | Dừng retry tự động hoặc giới hạn rất chặt; ghi nhận để sửa lỗi |

Không nên bắt mọi **Exception** rồi xem đó là lỗi tạm thời. Cách làm này khiến lỗi dữ liệu hoặc lỗi lập trình lặp đi lặp lại, tiêu tốn tài nguyên và che khuất nguyên nhân gốc. Nên định nghĩa các loại lỗi có thể retry, các loại lỗi không thể retry và một chính sách mặc định rõ ràng cho trường hợp chưa phân loại.

Nếu dịch vụ ngoài trả về thời gian chờ cụ thể, chẳng hạn **Retry-After**, hãy xem đó là ràng buộc từ dịch vụ đích. Chính sách nội bộ có thể chọn thời điểm muộn hơn giữa thời điểm dịch vụ yêu cầu và thời điểm backoff tính được, đồng thời vẫn áp dụng giới hạn vận hành đã thống nhất.

## 4. Gắn backoff với Spring Modulith

Listener trong Spring Modulith có thể được khai báo bằng **@ApplicationModuleListener** để xử lý application event theo mô hình listener của ứng dụng. Ví dụ:

~~~java
@Component
class InvoiceProjectionListener {

    private final InvoiceProjection projection;

    InvoiceProjectionListener(InvoiceProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(InvoiceIssued event) {
        projection.apply(event);
    }
}
~~~

Trong ví dụ này, listener cập nhật projection từ event **InvoiceIssued**. Khi listener thất bại, publication tương ứng chưa được đánh dấu hoàn tất. Event Publication Registry giúp ứng dụng tìm lại publication còn dang dở và phục hồi việc giao event.

Có thể dùng **IncompleteEventPublications** để xem xét và gửi lại các publication cũ chưa hoàn tất. Ví dụ thao tác phục hồi theo ngưỡng tuổi:

~~~java
@Component
class PublicationRecovery {

    private final IncompleteEventPublications incompletePublications;

    PublicationRecovery(IncompleteEventPublications incompletePublications) {
        this.incompletePublications = incompletePublications;
    }

    void resubmitOldPublications() {
        incompletePublications.resubmitIncompletePublicationsOlderThan(
            Duration.ofMinutes(5)
        );
    }
}
~~~

Đây là thao tác gửi lại theo ngưỡng tuổi. Một ngưỡng cố định không tự tạo ra lịch exponential backoff riêng cho từng publication. Nếu cần backoff theo từng lần thất bại, ứng dụng phải lưu thêm trạng thái retry, chẳng hạn số lần thất bại và thời điểm được phép thử tiếp theo, rồi chỉ resubmit publication đến hạn.

Một thiết kế điều phối retry có thể lưu các trường sau:

| Trường | Ý nghĩa |
|---|---|
| **publication_id** | Định danh ổn định của publication cần phục hồi |
| **listener_id** | Listener nhận publication |
| **failed_attempts** | Số lần xử lý thất bại đã ghi nhận |
| **next_attempt_at** | Thời điểm sớm nhất được phép retry |
| **last_error_code** | Mã lỗi đã phân loại gần nhất |
| **last_error_message** | Thông tin lỗi đã rút gọn, không chứa bí mật |
| **state** | Trạng thái như **PENDING**, **EXHAUSTED** hoặc **MANUAL_REVIEW** |
| **lease_until** | Thời hạn giữ quyền xử lý để tránh nhiều instance retry cùng publication |

Quy trình của một retry coordinator có thể được mô tả như sau:

1. Đọc các publication còn incomplete và các bản ghi retry đã đến hạn.
2. Claim từng bản ghi bằng lease hoặc cơ chế khóa tương đương để chỉ một instance xử lý tại một thời điểm.
3. Kiểm tra lại publication vẫn chưa hoàn tất và lỗi trước đó vẫn thuộc nhóm có thể retry.
4. Nếu đã hết ngân sách retry, chuyển bản ghi sang trạng thái chờ can thiệp và phát cảnh báo.
5. Nếu còn ngân sách, tính thời điểm retry tiếp theo, ghi nhận attempt và resubmit publication.
6. Để Event Publication Registry xác nhận kết quả xử lý. Chỉ xem publication là hoàn tất khi listener thực sự thành công; việc gọi resubmit thành công không đồng nghĩa listener đã xử lý xong.

Khi listener chạy bất đồng bộ, bước resubmit có thể kết thúc trước khi listener hoàn tất. Vì vậy không được đánh dấu thành công chỉ dựa trên việc lời gọi resubmit không ném exception. Registry vẫn là nguồn trạng thái publication; retry coordinator cần đối chiếu trạng thái này ở những lần quét tiếp theo.

Có thể chạy coordinator định kỳ bằng scheduler:

~~~java
@Component
class PublicationRetryScheduler {

    private final PublicationRetryCoordinator coordinator;

    PublicationRetryScheduler(PublicationRetryCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @Scheduled(fixedDelay = 15_000)
    void retryDuePublications() {
        coordinator.retryDuePublications();
    }
}
~~~

Scheduler chỉ đánh thức coordinator theo chu kỳ. Chính coordinator phải kiểm tra **next_attempt_at**, claim bản ghi, giới hạn số publication mỗi lượt và xác minh trạng thái registry. Không nên dùng **Thread.sleep()** trong listener để chờ backoff: cách đó giữ thread, giảm năng lực xử lý và làm mất lịch retry khi process dừng.

## 5. Cài đặt chính sách exponential backoff

Một lớp chính sách nhỏ có thể tính khoảng chờ độc lập với phần lưu trạng thái và phần resubmit. Ví dụ dưới đây dùng jitter đối xứng quanh khoảng chờ cơ sở:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class ExponentialBackoff {

    private final long initialMillis;
    private final long maxMillis;
    private final double multiplier;
    private final double jitter;

    public ExponentialBackoff(
            Duration initialDelay,
            Duration maxDelay,
            double multiplier,
            double jitter) {

        this.initialMillis = initialDelay.toMillis();
        this.maxMillis = maxDelay.toMillis();
        this.multiplier = multiplier;
        this.jitter = jitter;

        if (initialMillis <= 0 || maxMillis < initialMillis) {
            throw new IllegalArgumentException("Invalid delay range");
        }
        if (!Double.isFinite(multiplier) || multiplier <= 1.0) {
            throw new IllegalArgumentException("Multiplier must be greater than 1");
        }
        if (jitter < 0.0 || jitter > 1.0) {
            throw new IllegalArgumentException("Jitter must be between 0 and 1");
        }
    }

    public Duration delayAfterFailure(int failedAttempts) {
        if (failedAttempts < 1) {
            throw new IllegalArgumentException("failedAttempts must be positive");
        }

        double exponential =
            initialMillis * Math.pow(multiplier, failedAttempts - 1);

        long baseMillis = exponential >= maxMillis
            ? maxMillis
            : (long) exponential;

        double factor = jitter == 0.0
            ? 1.0
            : ThreadLocalRandom.current().nextDouble(
                1.0 - jitter,
                1.0 + jitter
            );

        long jitteredMillis = Math.round(baseMillis * factor);
        long boundedMillis = Math.max(
            1L,
            Math.min(maxMillis, jitteredMillis)
        );

        return Duration.ofMillis(boundedMillis);
    }
}
~~~

Khởi tạo chính sách với 2 giây ban đầu, tối đa 5 phút, hệ số nhân 2 và jitter 20%:

~~~java
ExponentialBackoff backoff = new ExponentialBackoff(
    Duration.ofSeconds(2),
    Duration.ofMinutes(5),
    2.0,
    0.2
);
~~~

Sau khi một attempt thất bại và được phân loại là lỗi tạm thời, coordinator tăng số lần thất bại rồi tính lịch tiếp theo:

~~~java
int nextFailedAttempts = retryState.failedAttempts() + 1;

Duration delay = backoff.delayAfterFailure(nextFailedAttempts);
Instant nextAttemptAt = clock.instant().plus(delay);

retryStateStore.scheduleNextAttempt(
    retryState.publicationId(),
    nextFailedAttempts,
    nextAttemptAt
);
~~~

**retryStateStore** và **retryState** ở đây là abstraction do ứng dụng định nghĩa để lưu trạng thái retry. Chúng cần dùng cùng một định danh ổn định với publication được theo dõi. Nên dùng **Clock** được inject thay vì gọi trực tiếp thời gian hệ thống ở nhiều nơi; điều này giúp logic thời điểm nhất quán và dễ kiểm thử.

Khi ghi nhận attempt, cần cân nhắc tình huống process dừng giữa lúc cập nhật trạng thái và lúc resubmit. Một cách triển khai là claim bản ghi, ghi nhận attempt cùng lease trong transaction ngắn, sau đó mới thực hiện resubmit. Nếu process dừng sau khi ghi nhận nhưng trước khi gửi lại, publication sẽ được thử muộn hơn một chu kỳ; registry vẫn giữ publication chưa hoàn tất để phục hồi. Cơ chế claim phải hết hạn được để instance khác có thể tiếp quản khi worker gặp sự cố.

## 6. Giới hạn retry và xử lý khi hết ngân sách

Retry không nên kéo dài vô hạn. Cần xác định tối thiểu:

- Số lần thử tối đa.
- Khoảng chờ tối đa.
- Tổng thời gian một publication được phép nằm trong trạng thái chờ retry.
- Nhóm lỗi được retry tự động.
- Người hoặc quy trình chịu trách nhiệm xử lý publication bị dừng retry.

Khi hết ngân sách, chuyển trạng thái retry sang **EXHAUSTED** hoặc **MANUAL_REVIEW**, phát cảnh báo và giữ đủ thông tin để điều tra. Không xóa publication incomplete chỉ để làm sạch dashboard. Người vận hành cần biết event nào, listener nào, lỗi cuối cùng là gì và đã thử bao nhiêu lần. Sau khi nguyên nhân được sửa, có thể chủ động gửi lại publication theo quy trình vận hành.

Cần tách retry khỏi compensation. Retry phù hợp khi thao tác chưa hoàn thành do lỗi tạm thời và có thể thực hiện lại an toàn. Compensation phù hợp khi một bước nghiệp vụ đã tạo ra hiệu ứng cần được hoàn tác hoặc bù bằng một hành động nghiệp vụ khác. Ví dụ, nếu hệ thống đã giữ chỗ thành công nhưng không thể hoàn tất bước thanh toán sau nhiều lần thử, việc giải phóng chỗ có thể là compensation. Không nên tự động compensation chỉ vì một lần timeout: thao tác ở dịch vụ đích có thể đã thành công dù phản hồi bị mất.

## 7. Bảo đảm xử lý lặp an toàn

Publication chưa hoàn tất có thể được gửi lại sau khi listener đã thực hiện một phần công việc. Vì vậy, retry trong hệ thống event thường phải chấp nhận khả năng giao ít nhất một lần và thiết kế listener có tính idempotent.

Một số cách thường dùng:

- Event mang **eventId** ổn định. Listener lưu **eventId** đã xử lý với ràng buộc unique trong cùng transaction với cập nhật dữ liệu nghiệp vụ.
- Khi gọi dịch vụ ngoài, truyền idempotency key nếu dịch vụ đó hỗ trợ.
- Với thao tác cập nhật projection, dùng phép cập nhật có thể chạy lại an toàn hoặc kiểm tra phiên bản event để tránh áp dụng dữ liệu cũ.
- Không tạo event ID mới cho mỗi lần retry. Các lần gửi lại phải đại diện cho cùng một sự kiện nghiệp vụ.
- Giữ transaction listener ngắn và đặt cập nhật dữ liệu cùng dấu vết đã xử lý trong một transaction khi chúng thuộc cùng database.

Ví dụ, một bảng inbox có thể lưu cặp định danh event và consumer:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Listener bắt đầu bằng việc ghi nhận event vào inbox. Nếu khóa đã tồn tại, listener biết event đã được xử lý và có thể kết thúc an toàn. Việc ghi inbox và thay đổi dữ liệu nghiệp vụ cần nằm trong cùng transaction để tránh tình huống đánh dấu đã xử lý nhưng nghiệp vụ chưa được cập nhật, hoặc ngược lại.

Idempotency không thay thế Event Publication Registry. Registry theo dõi publication tới listener; inbox hoặc idempotency key bảo vệ hiệu ứng nghiệp vụ khi cùng event được giao lại. Hai cơ chế giải quyết hai phần khác nhau của bài toán.

## 8. Quan sát và vận hành backoff

Một retry policy chỉ hữu ích khi có thể biết nó đang hoạt động ra sao. Nên theo dõi các chỉ số:

| Chỉ số | Điều cần nhận biết |
|---|---|
| Số publication incomplete | Khối lượng công việc chưa hoàn tất |
| Tuổi publication lâu nhất | Publication bị kẹt hoặc chưa được phục hồi |
| Số retry theo listener và loại lỗi | Listener hoặc dependency thường xuyên thất bại |
| Số publication exhausted | Công việc cần can thiệp thủ công |
| Thời gian từ lần lỗi đến lần retry | Backoff thực tế có đúng cấu hình |
| Tỷ lệ retry thành công | Retry có giúp phục hồi hay chỉ lặp lại lỗi |

Log nên có event ID, publication ID, listener, attempt hiện tại, thời điểm retry kế tiếp, loại lỗi và correlation ID nếu có. Không ghi token, credential, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào log.

Khi chạy nhiều instance, coordinator cần giới hạn concurrency và dùng claim/lease hoặc khóa tương đương để tránh nhiều instance cùng resubmit một publication. Cũng cần giới hạn số publication được xử lý trong mỗi lượt quét để retry không chiếm hết tài nguyên của luồng xử lý event mới. Nếu dependency đang bị throttling, có thể áp dụng giới hạn đồng thời ở cấp dependency thay vì chỉ ở từng listener.

## 9. Kiểm thử chính sách retry

Có thể kiểm thử chính sách và luồng phục hồi ở các lớp khác nhau:

1. **Kiểm thử công thức:** lần thất bại đầu tiên trả về khoảng chờ ban đầu; các lần sau tăng theo hệ số; kết quả không vượt **maxDelay**.
2. **Kiểm thử jitter:** kết quả nằm trong khoảng đã cấu hình và không vượt giới hạn tối đa.
3. **Kiểm thử phân loại lỗi:** lỗi tạm thời được lên lịch; lỗi vĩnh viễn không bị retry vô hạn.
4. **Kiểm thử thời điểm:** publication chưa đến **next_attempt_at** không được gửi lại; publication đến hạn được claim đúng một lần trong điều kiện cạnh tranh.
5. **Kiểm thử registry:** listener thành công làm publication hoàn tất; listener thất bại vẫn để lại publication có thể phục hồi.
6. **Kiểm thử restart:** publication chưa hoàn tất và lịch retry vẫn được khôi phục từ kho lưu trữ bền vững sau khi ứng dụng khởi động lại.
7. **Kiểm thử idempotency:** gửi lại cùng event không tạo hiệu ứng nghiệp vụ trùng lặp.

Để kiểm thử thời gian, inject **Clock** giả và điều khiển thời điểm trong test thay vì chờ thật. Với jitter, có thể inject nguồn số ngẫu nhiên vào chính sách để test có kết quả xác định. Kiểm thử tích hợp nên xác minh trạng thái publication và dữ liệu nghiệp vụ sau cả lần thành công lẫn lần thất bại.

## 10. Các quyết định cần chốt khi đưa vào production

Trước khi bật retry tự động cho một listener, cần trả lời được các câu hỏi sau:

- Listener có thể chạy lại an toàn không? Event ID hoặc idempotency key được lưu ở đâu?
- Những exception nào được xem là tạm thời? Exception nào cần dừng ngay?
- Khoảng chờ ban đầu, hệ số nhân, jitter và giới hạn tối đa dựa trên đặc tính dependency nào?
- Số lần retry và tổng thời gian retry tối đa là bao nhiêu?
- Publication incomplete được lưu bền vững và truy vấn bằng cách nào?
- Coordinator có tránh được hai instance xử lý cùng publication không?
- Khi hết ngân sách, ai nhận cảnh báo và quy trình gửi lại thủ công là gì?
- Khi thao tác đã tạo hiệu ứng một phần, nghiệp vụ cần retry tiếp hay chạy compensation?

Một cấu hình backoff tốt giúp các module tiếp tục giao tiếp qua event contract ngay cả khi một listener hoặc dependency gặp sự cố ngắn hạn. Khi kết hợp lịch retry có giới hạn, publication registry bền vững, idempotency và giám sát, việc phục hồi trở thành một quy trình có thể dự đoán và vận hành được, đồng thời vẫn giữ ranh giới nghiệp vụ giữa các module Spring Modulith.

