# Timeout saga

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Một saga điều phối quy trình đi qua nhiều module và nhiều transaction độc lập; giữa các bước, process manager có thể phải chờ một module nội bộ hoặc hệ thống ngoài phản hồi. Nếu phản hồi không đến đúng hạn, quy trình cần phát hiện tình trạng chờ quá lâu và chọn hành động tiếp theo.

**Timeout saga** là cơ chế xác định một bước hoặc toàn bộ quy trình đã vượt quá thời hạn được phép. Timeout giúp process manager phát hiện saga bị treo, retry khi phù hợp, đối soát kết quả chưa rõ hoặc bắt đầu bù trừ. Timeout là tín hiệu về thời gian chờ; nó không tự chứng minh thao tác ở hệ thống nhận đã thất bại.

## 1. Timeout trong một quy trình phân tán

Giả sử saga đặt hàng thực hiện các bước:

1. Order tạo đơn và yêu cầu Inventory giữ hàng.
2. Inventory phản hồi InventoryReserved.
3. Order yêu cầu Payment thu tiền.
4. Payment phản hồi PaymentCaptured hoặc PaymentFailed.
5. Order cập nhật trạng thái cuối.

Nếu Inventory không phản hồi trong 30 giây, process manager cần quyết định có retry yêu cầu giữ hàng, hỏi lại trạng thái reservation hay kết thúc bước. Nếu Payment không phản hồi trong 2 phút, hệ thống cần kiểm tra giao dịch trước khi gửi lệnh thu tiền lần nữa hoặc bù trừ.

Mỗi bước có đặc tính và mức chấp nhận chờ khác nhau. Không nên đặt một timeout chung cho toàn saga nếu các dependency có SLA khác nhau.

| Loại timeout | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Step timeout | Một bước không nhận được kết quả trong thời hạn của bước đó. | Chờ InventoryReserved quá 30 giây. |
| Request timeout | Một lần gọi hoặc gửi yêu cầu không nhận phản hồi đúng hạn. | HTTP call đến cổng thanh toán hết 5 giây. |
| Business deadline | Mốc cuối mà toàn quy trình phải đạt kết quả nghiệp vụ. | Đơn hàng phải được xác nhận trong 15 phút. |
| Inactivity timeout | Saga không có tiến triển trong một khoảng thời gian. | Không có event mới trong 10 phút. |
| Retry delay | Khoảng chờ trước lần thử tiếp theo. | Thử lại sau 20 giây. |

Request timeout thường ngắn hơn step timeout vì một bước có thể gồm nhiều lần thử. Business deadline có thể bao trùm nhiều bước và không nhất thiết bằng tổng các request timeout.

## 2. Deadline và timeout không giống nhau

**Deadline** là thời điểm tuyệt đối mà một bước hoặc saga phải có kết quả. **Timeout duration** là khoảng thời gian chờ tính từ một mốc xác định. Ví dụ, bước giữ hàng bắt đầu lúc 10:00:00 và có timeout 30 giây; deadline của bước là 10:00:30.

Nên lưu deadline dưới dạng thời điểm UTC, chẳng hạn **Instant**, để có thể so sánh giữa các instance và sau khi ứng dụng restart. Tránh lưu deadline dưới dạng chuỗi ngày giờ địa phương không có múi giờ.

Một bản ghi step có thể chứa:

| Field | Mục đích |
| --- | --- |
| startedAt | Thời điểm bước bắt đầu chờ kết quả. |
| deadlineAt | Thời điểm bước bị xem là quá hạn nếu chưa có kết quả hợp lệ. |
| timeoutPolicy | Chính sách áp dụng khi quá hạn, ví dụ retry, reconcile hoặc compensate. |
| attempt | Lần thực hiện hiện tại của bước. |
| timerGeneration | Phiên bản timer để nhận diện timeout event cũ. |
| status | REQUESTED, WAITING, SUCCEEDED, FAILED, TIMED_OUT hoặc UNKNOWN. |
| completedAt | Thời điểm nhận được kết quả kết thúc hợp lệ. |

Không nên tính lại deadline từ thời điểm ứng dụng khởi động. Nếu saga được tạo lúc 10:00 với deadline 10:05, việc restart lúc 10:04 không được làm thời hạn tự động lùi sang 10:09.

## 3. Chọn timeout theo chính sách nghiệp vụ

Timeout cần phản ánh SLA của dependency và hậu quả khi chờ quá lâu. Giá trị quá ngắn tạo retry và bù trừ không cần thiết; giá trị quá dài khiến tài nguyên và cam kết nghiệp vụ bị giữ lâu.

Khi chọn timeout, cân nhắc:

- Thời gian xử lý bình thường và độ biến động của dependency.
- Số lần retry cùng khoảng backoff dự kiến.
- Thời hạn nghiệp vụ mà người dùng hoặc đối tác chấp nhận.
- Thời gian cần thiết để thực hiện bù trừ.
- Khả năng tra cứu trạng thái giao dịch khi response bị mất.
- Giới hạn giữ hàng, giữ chỗ hoặc giữ tài nguyên của module liên quan.

Ví dụ minh họa:

| Bước | Timeout mỗi lần thử | Số lần thử tối đa | Hành động sau khi hết hạn |
| --- | --- | --- | --- |
| Reserve inventory | 10 giây | 3 | Kiểm tra reservation; nếu chưa tồn tại thì retry, nếu không xác định thì điều tra. |
| Charge payment | 8 giây | Theo chính sách cổng thanh toán | Tra cứu transaction bằng idempotency key trước khi quyết định tiếp tục. |
| Confirm shipment | 60 giây | 2 | Chuyển sang REQUIRES_ATTENTION nếu trạng thái đối tác không xác định. |

Các con số chỉ là ví dụ. Giá trị thực tế phải được quyết định theo hợp đồng dịch vụ và yêu cầu nghiệp vụ, không lấy trực tiếp từ bảng này.

## 4. Timeout không đồng nghĩa với thất bại

Đây là quy tắc quan trọng nhất khi thiết kế timeout saga. Timeout chỉ cho biết process manager chưa nhận được kết quả trước deadline. Nó không cho biết chắc chắn hệ thống đích chưa thực hiện hành động.

Ví dụ, Payment đã thu tiền thành công nhưng response bị mất trên mạng. Process manager hết thời gian chờ và phát hiện PaymentTimedOut. Nếu lập tức gửi một lệnh thu tiền mới với khóa khác, khách hàng có thể bị thu tiền hai lần. Nếu lập tức đánh dấu thanh toán thất bại rồi giải phóng hàng, hệ thống có thể rơi vào trạng thái đã thu tiền nhưng đơn hàng bị hủy.

Vì vậy, kết quả của một bước có thể cần các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| WAITING | Đã gửi yêu cầu và đang chờ kết quả. |
| SUCCEEDED | Có xác nhận thành công hợp lệ. |
| FAILED | Có xác nhận thất bại rõ ràng theo hợp đồng. |
| TIMED_OUT | Đã quá deadline nhưng kết quả nghiệp vụ chưa được xác nhận. |
| UNKNOWN | Đã thử đối soát nhưng chưa xác định được hệ thống đích đã thực hiện hay chưa. |
| REQUIRES_ATTENTION | Không thể tự xử lý an toàn; cần người hoặc quy trình đối soát. |

Khi bước thanh toán timeout, hãy tra cứu trạng thái bằng paymentTransactionId hoặc idempotency key. Nếu provider xác nhận đã thu tiền, tiếp tục nhánh thành công. Nếu xác nhận chưa thu tiền, có thể retry cùng khóa hoặc chuyển sang bù trừ theo chính sách. Nếu trạng thái vẫn không rõ, giữ saga ở trạng thái cần đối soát thay vì tự suy đoán.

## 5. Các cách phát hiện timeout

Timeout saga thường cần một cơ chế đánh thức process manager khi deadline đến. Có một số cách triển khai:

| Cách | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Scheduled scanner | Tác vụ định kỳ truy vấn các step có deadline đã qua. | Muốn triển khai đơn giản và lưu deadline trong database. |
| Durable delayed message | Hệ thống gửi message có thời điểm giao trong tương lai. | Hạ tầng messaging hỗ trợ lịch giao bền vững. |
| Dedicated scheduler | Scheduler quản lý timer và phát timeout event khi đến hạn. | Có nhiều timer và cần quản lý tập trung. |
| Workflow engine | Công cụ workflow quản lý timer, state và retry. | Quy trình dài, nhiều nhánh hoặc yêu cầu điều phối phức tạp. |

Timer trong bộ nhớ như ScheduledExecutorService có thể hữu ích cho tác vụ ngắn hạn trong một tiến trình, nhưng không đủ làm nguồn sự thật cho saga bền vững. Timer sẽ mất khi process restart và nhiều instance có thể cùng tạo timer cho một saga. Nếu dùng scheduler trong bộ nhớ, phải có cơ chế khôi phục từ deadline đã lưu.

## 6. Dùng scheduled scanner với deadline lưu trong database

Một cách dễ hiểu là lưu deadlineAt trong bảng saga step. Tác vụ định kỳ tìm các bước đang chờ có deadline đã qua rồi phát tín hiệu timeout. Ví dụ sau chỉ minh họa cấu trúc; repository cần dùng truy vấn có giới hạn batch và cơ chế claim/locking phù hợp:

~~~java
@Component
@RequiredArgsConstructor
class SagaTimeoutScanner {

    private final SagaTimeoutService timeouts;

    @Scheduled(fixedDelayString = "\${saga.timeout.scan-delay:1000}")
    void scan() {
        timeouts.processExpiredSteps();
    }
}
~~~

Service lấy các step hết hạn và phát event:

~~~java
@Service
@RequiredArgsConstructor
class SagaTimeoutService {

    private final SagaStepRepository steps;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public void processExpiredSteps() {
        Instant now = clock.instant();

        for (SagaStep step : steps.findExpiredForUpdate(now)) {
            if (!step.isWaiting()) {
                continue;
            }

            step.markTimeoutSignalled();
            events.publishEvent(new SagaStepTimedOut(
                step.getSagaId(),
                step.getStepId(),
                step.getTimerGeneration(),
                now
            ));
        }
    }
}
~~~

findExpiredForUpdate và markTimeoutSignalled là các phương thức repository/domain minh họa. Trong môi trường nhiều instance, truy vấn phải bảo đảm một step chỉ được claim bởi một worker tại một thời điểm, ví dụ bằng row locking, optimistic version hoặc cơ chế claim có lease. Nếu không, nhiều instance có thể phát cùng timeout event.

Event timeout nên được phát trong ranh giới transaction có cơ chế lưu publication phù hợp. Với transactional listener nội bộ, Event Publication Registry của Spring Modulith có thể theo dõi publication và hỗ trợ recovery theo cấu hình. Nếu dùng scheduler phát message ra broker, cần outbox hoặc cơ chế tương đương để không mất thông báo giữa lúc cập nhật timer và gửi message.

## 7. Timer generation và timeout event đến muộn

Một tình huống phổ biến là timeout đã được lên lịch nhưng bước hoàn tất trước deadline. Hệ thống có thể cố hủy timer, nhưng việc hủy không phải lúc nào cũng ngăn được message đã nằm trong hàng đợi hoặc timeout event đã được phát.

Dùng timerGeneration hoặc attempt để phân biệt timer hiện tại với timer cũ. Mỗi lần bước được khởi động lại hoặc gia hạn deadline, tăng generation. Timeout event mang generation tại thời điểm được tạo.

Ví dụ:

~~~java
public record SagaStepTimedOut(
    UUID sagaId,
    String stepId,
    long timerGeneration,
    Instant detectedAt
) {}
~~~

Khi nhận timeout, process manager chỉ áp dụng nếu:

- Saga và step vẫn tồn tại.
- Step vẫn ở trạng thái chờ có thể timeout.
- Generation của event bằng generation hiện tại trong database.
- Deadline hiện tại thực sự đã qua.
- Chưa có kết quả thành công hoặc thất bại hợp lệ được commit.

Nếu PaymentCaptured đã hoàn tất step và tăng generation, timeout event cũ sẽ bị bỏ qua như một event stale. Cơ chế generation giúp xử lý cả trường hợp timer không hủy được và message bị giao trễ.

## 8. Race giữa timeout và kết quả thành công

Timeout event và response thành công có thể đến gần như đồng thời. Ví dụ, scanner phát PaymentTimedOut trong lúc listener PaymentCaptured cũng đang cập nhật saga. Nếu cả hai handler cùng đọc state WAITING rồi ghi kết quả, trạng thái cuối có thể phụ thuộc vào thứ tự commit.

Phải quyết định kết quả bằng một chuyển trạng thái nguyên tử trong database. Có thể dùng optimistic locking với @Version, row lock hoặc câu lệnh cập nhật có điều kiện:

~~~sql
UPDATE saga_step
SET status = 'TIMED_OUT',
    state_version = state_version + 1
WHERE saga_id = :sagaId
  AND step_id = :stepId
  AND status = 'WAITING'
  AND timer_generation = :generation
  AND deadline_at <= :now;
~~~

Nếu số hàng được cập nhật bằng 0, điều kiện timeout không còn đúng: step có thể đã thành công, đã được xử lý bởi worker khác hoặc timer đã cũ. Handler phải đọc lại trạng thái trước khi quyết định hành động tiếp theo.

Tương tự, handler thành công chỉ được chuyển WAITING sang SUCCEEDED khi generation và định danh giao dịch khớp. Nếu timeout đã chuyển sang UNKNOWN hoặc REQUIRES_ATTENTION, response thành công đến muộn cần đi qua nhánh đối soát. Không được để event đến muộn ghi đè trạng thái một cách vô điều kiện.

## 9. Timeout, retry và backoff

Timeout có thể kích hoạt retry, nhưng không phải mọi timeout đều nên retry. Trước hết phải xác định thao tác có an toàn khi gửi lại không và kết quả lần trước có rõ ràng không.

Một chính sách thường gồm:

1. Hết deadline của attempt hiện tại.
2. Tra cứu kết quả nếu dependency có thể đã thực hiện side effect.
3. Nếu chắc chắn chưa thực hiện và lỗi có tính tạm thời, lên lịch attempt tiếp theo.
4. Dùng idempotency key ổn định cho cùng một hành động nghiệp vụ.
5. Tăng attempt và tính deadline mới theo backoff.
6. Nếu vượt giới hạn retry hoặc deadline nghiệp vụ, chuyển sang bù trừ hoặc REQUIRES_ATTENTION.

Backoff tăng dần giúp tránh dồn tải vào dependency đang gặp sự cố. Có thể thêm jitter để nhiều saga không cùng retry vào một thời điểm. Cần có giới hạn tổng thời gian, tổng số attempt và business deadline; nếu chỉ tăng backoff mà không có giới hạn, saga có thể tồn tại vô thời hạn.

Retry một request và retry giao một event là hai việc khác nhau. Event Publication Registry theo dõi việc giao event đến transactional listener nội bộ; chính sách retry nghiệp vụ của saga cần được quản lý trong step state/process manager. Không dùng trạng thái publication completed để kết luận dependency ngoài đã thành công.

## 10. Timeout và bù trừ

Khi một bước hết deadline, process manager phải đánh giá các cam kết đã phát sinh trước khi chọn bù trừ. Nếu bước trước đã giữ hàng nhưng thanh toán chưa rõ kết quả, không nên giải phóng hàng ngay nếu việc đó có thể dẫn đến đơn hàng đã thu tiền nhưng không còn reservation.

Một quy trình quyết định có thể là:

| Kết quả đối soát | Hành động tiếp theo |
| --- | --- |
| Dependency xác nhận thành công | Tiếp tục bước thuận hoặc xử lý event kết quả tương ứng. |
| Dependency xác nhận chưa thực hiện | Retry cùng idempotency key hoặc bù theo chính sách. |
| Dependency xác nhận thất bại rõ ràng | Chuyển sang bù các bước đã hoàn tất nếu nghiệp vụ yêu cầu. |
| Dependency không xác định | Giữ trạng thái UNKNOWN/REQUIRES_ATTENTION và tiếp tục đối soát. |

Khi đã quyết định bù trừ, lưu trạng thái COMPENSATING và phát yêu cầu bù trong transaction phù hợp. Theo dõi từng bước bù riêng; chỉ chuyển COMPENSATED khi mọi hành động bắt buộc đã hoàn tất. Timeout của chính bước bù cũng cần deadline, retry và quy trình escalation riêng.

## 11. Timeout toàn saga và deadline nghiệp vụ

Ngoài timeout từng step, saga có thể có deadline tổng thể. Ví dụ, khách hàng chỉ có 15 phút để hoàn tất quy trình checkout. Deadline tổng thể giúp ngăn một saga kéo dài vô hạn dù từng bước vẫn thỉnh thoảng có phản hồi.

Khi business deadline đến, process manager cần xem trạng thái từng bước và các cam kết đã phát sinh. Nếu mọi bước đã hoàn tất, timeout tổng thể cũ phải bị bỏ qua. Nếu đang chờ một dependency, có thể chuyển sang nhánh hết hạn, bù trừ hoặc yêu cầu can thiệp tùy nghiệp vụ.

Không nên tự động hủy mọi saga chỉ vì deadline tổng thể đã qua. Một giao dịch thanh toán có thể đã hoàn tất nhưng event xác nhận đang bị chậm; một đơn hàng có thể đã được giao dù webhook đến muộn. Cần đối soát các hệ thống có side effect trước khi chọn kết quả cuối.

Deadline nghiệp vụ nên được phân biệt với SLA kỹ thuật. SLA có thể đo thời gian phản hồi của Payment; deadline nghiệp vụ quyết định đơn hàng có còn được phép tiếp tục hay không. Hai mốc có thể dẫn đến hành động khác nhau.

## 12. Lưu trữ, phục hồi và nhiều instance

Timeout phải tiếp tục hoạt động sau restart. Vì vậy, lưu deadlineAt, status, attempt, generation và policy trong persistence bền vững. Khi ứng dụng khởi động lại, scanner hoặc scheduler đọc lại các step đã quá hạn để tiếp tục xử lý.

Trong môi trường nhiều instance, cần tránh mỗi instance cùng xử lý một timeout. Các lựa chọn gồm:

- Claim row bằng SELECT ... FOR UPDATE trong transaction ngắn.
- Dùng optimistic locking và chỉ chấp nhận một cập nhật thành công.
- Claim theo lease có lockedUntil để worker khác tiếp quản khi instance chết.
- Dùng một scheduler phân tán hoặc delayed message bền vững có cơ chế chống giao trùng.

Không giữ database lock trong lúc gọi HTTP hoặc chờ hệ thống ngoài. Claim công việc trong transaction ngắn, thực hiện lời gọi ngoài transaction, rồi ghi kết quả trong transaction mới. Nếu cần bảo đảm phát event sau khi cập nhật state, dùng transactional event publication hoặc outbox phù hợp.

Event Publication Registry của Spring Modulith hỗ trợ theo dõi publication đến transactional listener và recovery publication chưa hoàn tất. Registry không phải timer store và không tự phát timeout khi deadline đến. Process manager hoặc scheduler vẫn phải quản lý deadline và trạng thái saga.

## 13. Đồng hồ và tính chính xác thời gian

Các instance có thể lệch đồng hồ. Nếu một instance tính deadline bằng clock nhanh hơn và instance khác kiểm tra bằng clock chậm hơn, timeout có thể bị phát sớm hoặc muộn.

Các thực hành hữu ích:

- Đồng bộ đồng hồ máy chủ bằng NTP hoặc dịch vụ thời gian chuẩn.
- Lưu thời điểm dưới dạng UTC/Instant.
- Dùng một nguồn thời gian nhất quán cho việc kiểm tra deadline, ví dụ thời gian database trong truy vấn claim.
- Tiêm Clock vào logic ứng dụng để kiểm thử mà không phụ thuộc thời gian thật.
- Không dùng timestamp từ client hoặc event bên ngoài làm bằng chứng duy nhất cho thời điểm timeout.
- Có khoảng dung sai phù hợp khi SLA không yêu cầu độ chính xác mili giây.

Đối với timeout trong cùng một request ngắn, monotonic clock có thể phù hợp để đo elapsed duration vì không bị ảnh hưởng bởi việc chỉnh đồng hồ hệ thống. Đối với deadline saga cần lưu bền vững qua restart, dùng Instant/UTC; không lưu giá trị monotonic clock.

## 14. Kiểm thử timeout saga

Không nên dùng Thread.sleep dài trong test để chờ timeout thực. Tiêm Clock có thể điều khiển thời gian, còn scanner có thể được gọi trực tiếp hoặc scheduler giả có thể kích hoạt theo ý muốn.

Các trường hợp nên kiểm tra:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Step chưa đến deadline | Không phát timeout event. |
| Step đã quá deadline | Timeout được phát đúng một lần theo cơ chế claim. |
| Kết quả thành công trước deadline | Timer bị vô hiệu về mặt logic; timeout cũ không làm đổi state. |
| Timeout và success đồng thời | Chỉ một chuyển trạng thái hợp lệ được commit; conflict được xử lý. |
| Timeout event cũ | Generation không khớp nên event bị bỏ qua. |
| Dependency đã thực hiện nhưng response mất | Process manager đối soát trước khi retry hoặc bù. |
| Retry | Attempt tăng, deadline mới và idempotency key được dùng đúng. |
| Hết retry | Saga chuyển nhánh bù trừ hoặc REQUIRES_ATTENTION theo policy. |
| Restart | Deadline còn hạn và đã quá hạn đều được phục hồi đúng. |
| Nhiều scheduler instance | Một step không bị nhiều worker xử lý timeout đồng thời. |
| Timeout khi đang bù | Bước bù có retry/escalation và không đánh dấu COMPENSATED sai. |
| Business deadline | Chỉ saga chưa đạt kết quả hợp lệ mới đi vào nhánh hết hạn. |

Ngoài trạng thái, hãy kiểm tra side effect: không thu tiền hai lần, không giải phóng reservation hai lần và không làm mất event tiếp theo khi process dừng giữa cập nhật state với phát event.

## 15. Quan sát và vận hành timeout

Timeout cần được quan sát theo saga, step và dependency. Chỉ đếm số timeout tổng thể không đủ để xác định hệ thống nào đang gây chậm.

Các chỉ số hữu ích:

- Số step đang chờ, đã quá deadline, UNKNOWN và REQUIRES_ATTENTION.
- Tuổi của step quá hạn lâu nhất và số saga vượt business deadline.
- Số timeout theo module, event type và dependency.
- Tỷ lệ timeout dẫn đến thành công sau retry, bù trừ hoặc can thiệp thủ công.
- Số timeout event stale bị bỏ qua do generation không khớp.
- Số lần claim thất bại, lock conflict và timeout bị phát trùng.
- Thời gian từ deadline đến lúc phát hiện và xử lý timeout.

Log và trace nên có sagaId, stepId, attempt, timerGeneration, deadlineAt, eventId, business key và correlationId. Khi điều tra, người vận hành cần biết deadline được tính từ lúc nào, timeout được phát khi nào, kết quả đối soát ra sao và bước kế tiếp đã được commit chưa.

Dashboard nên phân biệt timeout request, timeout step và business deadline. Cảnh báo có thể dựa trên số saga quá hạn hoặc tuổi của saga quá hạn lâu nhất. Với các bước thanh toán, vận chuyển hoặc giữ tài nguyên, cần có quy trình đối soát thủ công và audit trail cho thao tác can thiệp.

## 16. Checklist thiết kế timeout saga

- Mỗi step chờ có deadline và timeout policy rõ ràng.
- Deadline được lưu bền vững dưới dạng thời điểm UTC và không bị tính lại sau restart.
- Timeout duration, retry delay và business deadline được phân biệt.
- Timeout không bị xem là bằng chứng dependency chưa thực hiện side effect.
- Kết quả UNKNOWN có quy trình đối soát trước khi retry hoặc bù trừ.
- Timeout event có sagaId, stepId và timerGeneration để chống event cũ.
- Timeout và success cạnh tranh được giải quyết bằng chuyển trạng thái nguyên tử.
- Scheduler nhiều instance có cơ chế claim/locking/lease.
- Timer được phục hồi từ persistence; timer trong bộ nhớ không phải nguồn sự thật.
- Retry có backoff, jitter khi phù hợp, giới hạn attempt và deadline tổng thể.
- Bù trừ có deadline và chính sách phục hồi riêng.
- Event Publication Registry được dùng để theo dõi publication đến listener, không thay thế timer store.
- Integration test bao phủ race, stale timeout, restart, duplicate và side effect không lặp.
- Dashboard theo dõi timeout theo step, dependency, tuổi và kết quả xử lý.

Timeout saga giúp process manager nhận biết quy trình đã chờ quá lâu và đưa ra quyết định tiếp theo có kiểm soát. Khi deadline được lưu bền vững, timeout event có generation, race với kết quả thành công được xử lý nguyên tử và trạng thái không xác định được đối soát trước khi retry hoặc bù trừ, saga có thể phục hồi an toàn qua lỗi mạng, restart và các phản hồi đến trễ mà vẫn giữ đúng cam kết nghiệp vụ.
