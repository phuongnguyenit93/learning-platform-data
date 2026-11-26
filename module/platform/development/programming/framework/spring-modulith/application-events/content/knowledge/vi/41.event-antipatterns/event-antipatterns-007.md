# Retry không giới hạn

*Nhận diện và loại bỏ vòng lặp retry vô hạn trong luồng application event*

Retry giúp hệ thống phục hồi khi một thao tác thất bại tạm thời. Tuy nhiên, nếu consumer tự động thử lại mãi mà không có giới hạn số lần, thời gian, tốc độ hoặc điều kiện dừng, retry có thể biến một lỗi nhỏ thành sự cố diện rộng. Một listener không thể xử lý payload độc hại sẽ liên tục nhận lại cùng event; một database đang quá tải phải phục vụ thêm nhiều lần thử; một publication cũ có thể chiếm tài nguyên và đẩy các event mới ra phía sau.

**Retry không giới hạn** là anti-pattern trong đó một event được thử lại vô hạn hoặc gần như vô hạn mà không có ngân sách retry, thời hạn xử lý, phân loại lỗi và lối thoát rõ ràng. Hệ thống thường nhầm lẫn giữa “không bỏ event” với “phải thử lại mãi”. Độ tin cậy cần có khả năng phục hồi và khả năng kết thúc một lần xử lý lỗi theo cách có thể quan sát, điều tra và can thiệp.

## 1. Vì sao retry vô hạn nguy hiểm?

Giả sử listener của module billing nhận OrderCompleted và ghi hóa đơn. Database gặp lỗi kết nối trong 10 phút. Nếu listener retry ngay lập tức, mỗi lần thất bại lại tạo thêm một lần truy cập database. Khi database bắt đầu phục hồi, hàng nghìn lần retry đồng thời tiếp tục tranh connection, lock và CPU. Dependency bị lỗi ban đầu vì vậy khó trở lại bình thường hơn.

Retry vô hạn tạo ra các rủi ro:

- **Retry amplification:** một event đầu vào tạo ra hàng chục hoặc hàng nghìn lần gọi dependency.
- **Resource exhaustion:** thread, connection, heap, queue và dung lượng lưu trữ bị chiếm bởi công việc không thể hoàn tất.
- **Poison message loop:** một payload sai schema hoặc vi phạm invariant được giao lại liên tục dù không thể tự phục hồi.
- **Starvation:** event mới hoặc event quan trọng phải chờ phía sau một nhóm event lỗi cũ.
- **Duplicate side effect:** một lần xử lý đã commit một phần nhưng chưa ghi nhận hoàn tất; retry lặp lại tác động.
- **Chi phí tăng:** broker, database và dịch vụ ngoài chịu tải không cần thiết, có thể phát sinh quota hoặc chi phí theo request.
- **Mất khả năng quan sát:** log lỗi lặp lại quá nhiều che khuất nguyên nhân gốc và làm alert bị nhiễu.
- **Khó triển khai và phục hồi:** backlog không có điểm kết thúc, khiến việc drain, cutover hoặc rollback trở nên khó dự đoán.

Retry là một cơ chế phục hồi, không phải bằng chứng rằng một thao tác cuối cùng chắc chắn sẽ thành công.

## 2. Phân biệt lỗi tạm thời và lỗi không thể retry

Không phải mọi exception đều có thể được giải quyết bằng cách thử lại. Trước khi thiết kế chính sách, phân loại lỗi theo khả năng tự phục hồi:

| Nhóm lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Tạm thời | Timeout ngắn, connection reset, broker leader election | Retry có backoff và giới hạn |
| Quá tải | HTTP 429, pool cạn, database đang throttling | Giảm tốc độ, tôn trọng Retry-After, retry có budget |
| Phụ thuộc gián đoạn | Database hoặc dịch vụ ngoài không sẵn sàng | Circuit breaker, backoff, giới hạn tổng thời gian |
| Dữ liệu/hợp đồng | JSON sai, schema version không hỗ trợ, field bắt buộc thiếu | Quarantine hoặc DLQ để sửa dữ liệu/hợp đồng |
| Nghiệp vụ | Aggregate không ở trạng thái cho phép, tham chiếu không tồn tại | Xử lý nghiệp vụ hoặc đánh dấu thất bại có lý do |
| Cấu hình/quyền | Credential hết hạn, ACL từ chối, destination sai | Dừng retry nhanh, cảnh báo và sửa cấu hình |
| Lỗi lập trình | Null không mong đợi, invariant bị phá vỡ | Dừng vòng lặp, ghi nhận lỗi và sửa code |

Một lỗi timeout có thể là tạm thời, nhưng retry vẫn cần giới hạn vì dependency có thể không phục hồi trong thời gian ứng dụng chờ. Một lỗi 401/403 hoặc schema không hợp lệ thường không tự biến mất sau vài giây. Cần phân loại theo mã lỗi, loại exception và ngữ cảnh nghiệp vụ thay vì bắt mọi exception rồi retry giống nhau.

## 3. Retry không giới hạn khác với retry có kiểm soát

Retry có kiểm soát đặt ra ít nhất bốn giới hạn:

1. **Maximum attempts:** số lần thử tối đa cho một event hoặc một bước xử lý.
2. **Maximum elapsed time:** tổng thời gian tối đa được phép retry.
3. **Retry rate/budget:** số lần thử lại được phép trong một cửa sổ thời gian hoặc tỷ lệ so với lưu lượng bình thường.
4. **Terminal state:** trạng thái cuối khi đã hết ngân sách, chẳng hạn FAILED, QUARANTINED hoặc DEAD_LETTERED.

Ví dụ, một listener có thể thử lại tối đa năm lần trong 15 phút với khoảng chờ tăng dần. Sau đó event được chuyển sang luồng xử lý lỗi để người vận hành kiểm tra. Các con số phải dựa trên SLO và khả năng phục hồi của dependency, không lấy một cấu hình chung cho mọi event.

Giới hạn số lần thử không có nghĩa là xóa event khi hết retry. Event cần được lưu lại cùng nguyên nhân, attempt count, thời điểm cuối và cách phục hồi. Một trạng thái terminal có thể được xử lý thủ công hoặc replay sau khi nguyên nhân đã được khắc phục.

## 4. Exponential backoff và jitter

Retry ngay lập tức thường gây tải cao nhất đúng lúc dependency đang lỗi. Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Một công thức minh họa:

    delay(n) = min(maxDelay, initialDelay × multiplier^(n - 1))

Trong đó n là số lần thử. Ví dụ initial delay 1 giây, multiplier 2 và max delay 1 phút tạo khoảng chờ 1, 2, 4, 8, 16, 32 rồi 60 giây.

Nếu mọi consumer dùng cùng lịch retry, chúng có thể thức dậy cùng lúc và tạo một đợt tải mới. Jitter thêm độ ngẫu nhiên vào khoảng chờ để phân tán các lần thử:

    actualDelay = random(0, calculatedDelay)

Hoặc dùng full jitter/equal jitter theo chính sách của thư viện retry. Khi dependency trả Retry-After, cân nhắc tôn trọng thời gian đó trong giới hạn tổng retry budget.

Backoff không thay thế maximum attempts hoặc maximum elapsed time. Một lịch retry tăng dần nhưng không có điểm dừng vẫn là retry vô hạn.

## 5. Retry budget và giới hạn tổng tải

Retry budget giới hạn lượng tải phát sinh thêm do lỗi. Một hệ thống có thể cho phép retry tối đa một tỷ lệ nhất định so với request thành công hoặc giới hạn số lần retry trong mỗi phút. Khi budget cạn, hệ thống tạm ngừng retry mới hoặc chuyển event sang trạng thái chờ phục hồi.

Ví dụ:

- Tối đa 4 lần retry cho mỗi event.
- Không retry quá 10 phút kể từ lần đầu.
- Tối đa 100 retry mỗi phút cho một dependency.
- Khi tỷ lệ lỗi vượt ngưỡng, mở circuit breaker và giảm tốc độ consumer.
- Không retry song song cùng một event khi một attempt khác vẫn đang giữ lease.

Budget nên được phân chia theo dependency hoặc nhóm listener. Nếu một API bên ngoài đang lỗi, retry của module reporting không nên tiêu hết tài nguyên dành cho module thanh toán. Dùng bulkhead, rate limiter và concurrency limit để cô lập tải.

## 6. Ví dụ retry có giới hạn trong Spring

Với Spring Retry hoặc cơ chế retry được ứng dụng lựa chọn, cấu hình phải thể hiện cả số lần thử và backoff. Ví dụ khái quát bằng annotation:

    @Retryable(
        retryFor = TransientDataAccessException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 1_000,
            multiplier = 2.0,
            maxDelay = 10_000,
            random = true
        )
    )
    public void updateProjection(OrderCompleted event) {
        projectionRepository.apply(event);
    }

Đây là ví dụ cho Spring Retry; cần dùng đúng dependency, import và phiên bản thư viện của dự án. Chỉ retry exception được xác định là tạm thời. Không đặt retryFor là Exception.class một cách mặc định vì lỗi validation, schema và lập trình cũng sẽ bị thử lại.

Khi hết số lần thử, có thể dùng recovery callback hoặc để exception đi ra ngoài để tầng xử lý publication ghi nhận thất bại. Recovery callback không nên chỉ nuốt lỗi và trả về bình thường nếu side effect chưa hoàn tất; làm vậy có thể khiến hệ thống đánh dấu listener thành công.

## 7. Không retry bằng vòng lặp tự viết không có điểm dừng

Một vòng lặp như sau là anti-pattern:

    while (true) {
        try {
            dependency.call();
            break;
        } catch (Exception ex) {
            log.warn("Call failed; retrying", ex);
        }
    }

Vòng lặp không có delay, giới hạn số lần, deadline hoặc phân loại lỗi. Nó có thể giữ thread vô thời hạn, tạo log storm và tiếp tục gọi dependency đang quá tải.

Nếu cần retry thủ công, dùng một abstraction có giới hạn rõ ràng:

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return dependency.call();
        } catch (TransientDependencyException ex) {
            if (attempt == maxAttempts || deadlineExceeded()) {
                throw ex;
            }
            sleep(backoffWithJitter(attempt));
        }
    }

Ví dụ trên chỉ minh họa cấu trúc. Trong ứng dụng bất đồng bộ, không nên giữ thread listener ngủ lâu giữa các lần retry; hãy lên lịch retry bằng scheduler, retry topic hoặc cơ chế broker phù hợp. Nếu dùng thread sleep, cần tính thời gian giữ thread và shutdown behavior.

## 8. Retry trong listener Spring Modulith

Với Spring Modulith, @ApplicationModuleListener thường dùng cho listener bất đồng bộ sau khi transaction publisher commit và trong transaction riêng. Event Publication Registry theo dõi publication cần giao và giúp phát hiện publication chưa hoàn tất.

Khi listener ném exception, transaction xử lý listener có thể rollback và publication không được đánh dấu hoàn tất theo cơ chế registry. Điều này hỗ trợ phục hồi, nhưng không đồng nghĩa framework tự cung cấp một chính sách retry vô hạn hoặc retry có giới hạn phù hợp với mọi ứng dụng.

Ứng dụng cần quyết định:

- Listener exception nào được retry tự động và ở tầng nào.
- Retry diễn ra trong cùng tiến trình, scheduler hay broker.
- Số lần thử, khoảng chờ và tổng thời gian tối đa.
- Publication hết budget được lưu ở đâu và ai chịu trách nhiệm xử lý.
- Resubmit publication cũ được giới hạn tốc độ như thế nào.
- Handler có idempotent khi side effect đã commit nhưng completion chưa được ghi nhận không.

Không bắt exception rồi ghi log như thể xử lý thành công. Nếu lỗi chưa được khắc phục, cần để transaction thất bại hoặc chuyển trạng thái lỗi theo một quy trình được theo dõi rõ ràng.

## 9. Registry chưa hoàn tất không phải lý do để retry mãi

Event Publication Registry ghi nhận trạng thái giao publication đến transactional listener hoặc externalization target. Một publication còn chưa hoàn tất có thể do listener thất bại, tiến trình dừng hoặc dependency không sẵn sàng. Resubmit có thể phù hợp sau khi nguyên nhân được khắc phục.

Không nên chạy scheduler quét publication chưa hoàn tất rồi resubmit toàn bộ ở mỗi chu kỳ mà không có giới hạn. Cách này có thể tạo vòng lặp retry vô hạn ở cấp vận hành, ngay cả khi listener không tự retry.

Quy trình phục hồi cần:

1. Chọn publication theo tuổi, listener/target và nhóm lỗi.
2. Kiểm tra attempt count và lần lỗi gần nhất.
3. Loại trừ lỗi vĩnh viễn hoặc payload không hợp lệ khỏi retry tự động.
4. Xác nhận dependency đã phục hồi.
5. Giới hạn batch size và tốc độ resubmit.
6. Đặt retry budget và thời gian chờ tiếp theo.
7. Chuyển publication vượt budget sang trạng thái cần can thiệp.
8. Theo dõi kết quả và không lặp lại resubmit khi chưa có thay đổi điều kiện.

Registry không tự thay thế distributed scheduler hoặc retry budget. Nếu nhiều application instance cùng chạy job phục hồi, cần lease, lock hoặc cơ chế điều phối để tránh resubmit đồng thời cùng một publication.

## 10. Retry ở broker: RabbitMQ

Với RabbitMQ, NACK/reject có thể requeue message hoặc route đến dead-letter exchange tùy cờ và cấu hình queue. Requeue ngay lập tức khi listener luôn lỗi có thể khiến message được giao lại liên tục, tạo hot loop.

Các biện pháp thường dùng:

- Dùng retry queue hoặc delayed message pattern để tạo khoảng chờ giữa các lần thử.
- Ghi nhận số lần giao/thử trong header hoặc metadata do ứng dụng quản lý.
- Giới hạn số lần retry và route message vượt giới hạn đến DLQ.
- Cấu hình dead-letter exchange và queue có retention, quyền truy cập, cảnh báo.
- Theo dõi redelivery count, unacknowledged messages và queue age.
- Tránh NACK requeue tức thì cho lỗi không thể tự phục hồi.

Không chỉ dựa vào redelivered flag để làm retry counter bền vững trong mọi topology. Nếu message được republish qua retry queue hoặc nhiều exchange, metadata có thể thay đổi theo cách vận chuyển. Dùng header/record retry có quy ước và kiểm thử với topology thực tế.

## 11. Retry ở broker: Kafka

Kafka thường xử lý retry bằng cách không commit offset cho record chưa hoàn tất, dùng error handler/retry topic hoặc chuyển record lỗi đến dead-letter topic. Nếu consumer liên tục đọc lại cùng offset mà không có backoff hoặc đường thoát, partition có thể bị chặn và các record sau không được xử lý.

Các điểm cần xác định:

- Offset chỉ tiến qua record đã xử lý thành công liên tục trong từng partition.
- Retry topic cần giữ event ID, original topic/partition/offset và attempt metadata.
- Thời gian retry phải phù hợp với thứ tự nghiệp vụ; chuyển retry sang topic khác có thể làm thay đổi thứ tự tương đối.
- Record hết retry budget cần được đưa vào DLT/quarantine để partition chính tiếp tục tiến theo chính sách.
- Replay từ DLT cần giữ định danh gốc và có idempotency.

Không commit offset trước khi side effect bền vững chỉ để tránh partition bị kẹt. Nếu cần tiếp tục xử lý record sau, phải có thiết kế retry topic hoặc cơ chế tách luồng rõ ràng và hiểu ảnh hưởng đến ordering.

## 12. Dead-letter và quarantine là lối thoát có kiểm soát

Dead-letter queue/topic (DLQ/DLT) hoặc quarantine lưu message không thể tiếp tục retry tự động. Đây không phải thùng rác; nó là vùng cách ly để điều tra, sửa dữ liệu hoặc replay có kiểm soát.

Một bản ghi quarantine nên có:

- Event ID, event type và schema version.
- Consumer/listener hoặc destination gây lỗi.
- Số lần thử, thời điểm đầu tiên và gần nhất.
- Error category và thông điệp lỗi đã được làm sạch dữ liệu nhạy cảm.
- Thông tin nguồn như topic/partition/offset hoặc exchange/queue khi có.
- Correlation ID và dấu vết truy vết phù hợp.
- Trạng thái xử lý thủ công và người chịu trách nhiệm.

Không chuyển message vào DLQ rồi quên nó. Cần alert theo số lượng và tuổi message, quy trình phân loại, quyền replay và retention. Trước khi replay, sửa nguyên nhân gốc và xác nhận handler idempotent.

## 13. Idempotency vẫn cần thiết dù retry có giới hạn

Retry có giới hạn không loại bỏ duplicate. Có thể xảy ra tình huống listener cập nhật database thành công, nhưng ứng dụng dừng trước khi publication registry hoặc broker ghi nhận completion. Lần giao tiếp theo sẽ xử lý cùng event lần nữa.

Các biện pháp:

- Dùng eventId ổn định qua mọi lần retry/resubmit.
- Lưu inbox theo consumerName và eventId với unique constraint.
- Cập nhật inbox và read model trong cùng transaction.
- Dùng idempotency key ở API ngoài nếu dịch vụ đích hỗ trợ.
- Dùng aggregate sequence/version để phát hiện event cũ hoặc sai thứ tự.
- Không tạo event ID mới khi republish cùng một sự kiện lịch sử.

Với side effect không thể đảo ngược như thu tiền, hoàn tiền hoặc gửi thông báo, cần kiểm tra trạng thái hệ thống đích trước khi retry khi kết quả lần gọi trước không rõ ràng.

## 14. Circuit breaker và backpressure phối hợp với retry

Retry và circuit breaker giải quyết hai vấn đề khác nhau. Retry thử lại một thao tác sau lỗi; circuit breaker tạm ngăn gọi dependency khi tỷ lệ lỗi hoặc timeout vượt ngưỡng. Backpressure và rate limiting giảm lượng công việc đi vào hệ thống đang quá tải.

Một chính sách phối hợp:

1. Retry ngắn với backoff cho lỗi thoáng qua.
2. Khi dependency tiếp tục lỗi, circuit breaker mở và từ chối các lần gọi mới trong một khoảng.
3. Listener không giữ thread hoặc connection trong lúc chờ dài; event được lên lịch retry hoặc chuyển sang trạng thái chờ.
4. Khi circuit half-open, chỉ cho một lượng nhỏ request thử nghiệm.
5. Khi dependency phục hồi, tăng dần concurrency và tốc độ drain backlog.

Không cấu hình retry ở mọi tầng mà không tính tổng số lần thử. Nếu HTTP client retry 3 lần, service retry 4 lần và broker retry 5 lần, một event có thể tạo ra nhiều chục lần gọi downstream. Hãy xác định một tầng chịu trách nhiệm retry chính và giới hạn tổng retry budget xuyên suốt.

## 15. Quan sát retry và phát hiện vòng lặp vô hạn

Metric và log nên cho biết event đang tiến triển hay chỉ lặp lại:

- Retry attempts theo listener, event type và dependency.
- Số event đã hết retry budget hoặc chuyển vào DLQ.
- Tuổi publication chưa hoàn tất lâu nhất.
- Số lần delivery/redelivery và duplicate bị bỏ qua.
- Thời gian giữa các lần retry và tổng elapsed time.
- Tỷ lệ retry thành công so với retry thất bại.
- Circuit breaker state, dependency latency và connection pool utilization.
- Queue depth, consumer lag và tốc độ completion.

Alert khi attempt count vượt ngưỡng, một event tồn tại quá lâu, retry rate tăng đột biến, DLQ tăng hoặc backlog không giảm. Không dùng eventId làm metric tag vì cardinality cao; đặt ID trong log có kiểm soát để điều tra một event cụ thể.

Log cần ghi retry attempt, next retry time, error category, consumer/listener, event ID và correlation ID. Tránh log toàn bộ payload, credential hoặc dữ liệu cá nhân.

## 16. Runbook khi retry tăng bất thường

Khi retry rate tăng hoặc publication tồn đọng kéo dài:

1. Xác định listener, destination và dependency bị ảnh hưởng.
2. So sánh event rate, completion rate, backlog age và retry rate.
3. Phân loại lỗi tạm thời, quá tải, dữ liệu, nghiệp vụ hay cấu hình.
4. Kiểm tra có nhiều tầng retry chồng lặp hay không.
5. Tạm dừng hoặc giảm tốc độ resubmit nếu dependency đang quá tải.
6. Sửa nguyên nhân gốc trước khi mở lại retry.
7. Chuyển poison message hoặc lỗi không thể phục hồi sang quarantine/DLQ.
8. Resubmit một batch nhỏ, quan sát completion và duplicate.
9. Tăng dần tốc độ khi dependency ổn định.
10. Đối soát read model hoặc side effect và ghi nhận event còn cần xử lý thủ công.

Không xóa publication chưa hoàn tất, purge queue hoặc tăng retry vô hạn để làm biến mất cảnh báo. Những thao tác này có thể làm mất dấu event hoặc khuếch đại sự cố.

## 17. Kiểm thử chính sách retry

Kiểm thử nên chứng minh cả giới hạn lẫn khả năng phục hồi:

1. Lỗi tạm thời được retry đúng số lần và cuối cùng thành công.
2. Lỗi vĩnh viễn không bị retry vô hạn và được chuyển sang trạng thái lỗi/quarantine.
3. Exponential backoff và jitter nằm trong giới hạn cấu hình.
4. Maximum elapsed time hoặc retry budget dừng việc thử lại đúng lúc.
5. Circuit breaker mở khi dependency lỗi kéo dài và giảm số lần gọi.
6. Retry nhiều tầng không nhân số lần gọi vượt budget tổng.
7. RabbitMQ requeue/DLX hoặc Kafka retry topic/DLT hoạt động đúng.
8. Publication registry giữ publication chưa hoàn tất và resubmit theo chính sách.
9. Duplicate sau commit nhưng trước ACK/completion không lặp side effect.
10. DLQ có metadata đủ để điều tra và replay có kiểm soát.
11. Backlog được drain dần sau khi dependency phục hồi mà không tạo retry storm.
12. Shutdown hoặc restart giữa các lần retry không làm mất trạng thái attempt/checkpoint.

Test retry nên dùng clock/scheduler có thể kiểm soát hoặc cấu hình delay ngắn trong test. Tránh chờ thời gian thực dài và không dùng Thread.sleep làm bằng chứng duy nhất. Với broker, dùng integration test hoặc Testcontainers để xác nhận redelivery, offset và dead-letter semantics.

## 18. Những điểm cần nhớ

- Retry không giới hạn là anti-pattern vì có thể khuếch đại sự cố, giữ tài nguyên vô hạn và làm backlog không thể phục hồi.
- Phân loại lỗi trước khi retry; lỗi schema, nghiệp vụ và cấu hình thường cần quarantine hoặc can thiệp.
- Đặt maximum attempts, maximum elapsed time, retry budget và terminal state.
- Dùng exponential backoff, jitter, tôn trọng Retry-After và tránh retry đồng thời cùng event.
- Không viết vòng lặp vô hạn hoặc bắt mọi exception rồi thử lại.
- Spring Modulith Event Publication Registry giúp theo dõi publication chưa hoàn tất; resubmit vẫn cần giới hạn và idempotency.
- RabbitMQ requeue tức thì và Kafka đọc lại offset liên tục có thể tạo hot loop; dùng retry queue/topic và DLQ/DLT phù hợp.
- Kết hợp inbox/idempotency, circuit breaker, backpressure, metric và runbook.
- DLQ/quarantine cần owner, retention, alert và quy trình replay có kiểm soát.

Retry đáng tin cậy phải có giới hạn và lối thoát. Khi lỗi được phân loại đúng, số lần thử và tổng thời gian được kiểm soát, còn event không thể phục hồi được cách ly để xử lý, ứng dụng Spring Modulith có thể phục hồi từ lỗi tạm thời mà không biến dependency đang hỏng thành sự cố lớn hơn.
