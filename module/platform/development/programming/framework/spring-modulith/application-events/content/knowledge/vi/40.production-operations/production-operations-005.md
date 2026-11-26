# Xử lý backlog

Backlog xuất hiện khi tốc độ event được tạo ra lớn hơn tốc độ các listener hoặc consumer xử lý trong một khoảng thời gian. Một lượng message chờ nhỏ có thể là bình thường trong giờ cao điểm; backlog trở thành sự cố khi tuổi message vượt SLA, số lượng tiếp tục tăng, hoặc các bước nghiệp vụ downstream bị chậm và không hoàn tất.

Trong ứng dụng Spring Modulith, backlog có thể nằm ở nhiều nơi: publication nội bộ chưa hoàn tất trong Event Publication Registry, bản ghi chưa gửi trong outbox, queue hoặc topic của broker, retry store, dead-letter queue (DLQ), hay công việc cập nhật projection. Mỗi nơi có cơ chế phục hồi và nguồn sự thật khác nhau. Không thể xử lý tất cả bằng cách tăng consumer hoặc xóa message.

Bài này trình bày cách phát hiện, phân loại, khoanh vùng và drain backlog trong production; cách khôi phục throughput mà vẫn giữ idempotency, thứ tự và transaction semantics; cùng cách xác nhận hệ thống đã trở lại trạng thái ổn định.

## 1. Backlog là gì và khi nào trở thành sự cố?

Backlog là tập event hoặc publication đang chờ được xử lý. Một hệ thống bất đồng bộ thường có độ trễ tự nhiên: producer commit trước, listener xử lý sau. Vì vậy, chỉ nhìn thấy message đang chờ không đủ để kết luận có sự cố.

Cần đánh giá backlog theo ít nhất bốn khía cạnh:

- **Số lượng:** còn bao nhiêu publication hoặc message chưa hoàn tất?
- **Tuổi:** message cũ nhất đã chờ bao lâu?
- **Xu hướng:** backlog đang tăng, ổn định hay giảm?
- **SLA nghiệp vụ:** độ trễ hiện tại có vượt thời gian xử lý mà nghiệp vụ chấp nhận không?

Ví dụ, queue có 50.000 message nhưng consumer đang xử lý nhanh và tuổi message cũ nhất chỉ vài giây có thể chỉ là đỉnh tải ngắn. Ngược lại, queue chỉ có 200 message nhưng message cũ nhất đã chờ hai giờ có thể là sự cố nghiêm trọng nếu đó là event thanh toán hoặc xác nhận đơn hàng.

Một backlog có thể gây ra các hệ quả:

- Projection và read model bị stale.
- Quy trình saga bị kẹt ở trạng thái chờ.
- Notification hoặc integration tới hệ thống khác bị trễ.
- Retry làm tăng tải lên database và broker.
- Message hết retention trước khi được xử lý.
- Các event đến sai thứ tự hoặc side effect bị thực hiện lặp khi phục hồi.

Định nghĩa ngưỡng cảnh báo theo tuổi và tốc độ tăng, không chỉ theo queue depth.

## 2. Phân biệt nơi backlog đang tồn tại

Trước khi hành động, xác định backlog nằm ở tầng nào. Cùng một event có thể đi qua nhiều tầng và mỗi tầng có metric riêng.

| Vị trí | Dấu hiệu | Nguồn kiểm tra |
|---|---|---|
| Spring Modulith Event Publication Registry | Publication của listener chưa hoàn tất | Registry và trạng thái theo listener |
| Transactional outbox | Bản ghi PENDING/FAILED chưa được relay gửi | Outbox table và relay metrics |
| RabbitMQ | Ready/unacked message tăng | Queue metrics, consumer và broker |
| Kafka | Consumer lag tăng | Consumer group offsets và partition lag |
| Retry/delayed queue | Message chờ tới thời điểm retry | Retry metadata và queue |
| DLQ/quarantine | Message bị tách khỏi luồng xử lý bình thường | DLQ depth, error category |
| Projection/read model | Event đã nhận nhưng projection chưa bắt kịp | Projection checkpoint/version và lag |

Event Publication Registry theo dõi việc giao application event tới từng listener nội bộ. Nó không mặc nhiên là event store lưu toàn bộ lịch sử event đã hoàn tất. Outbox lưu công việc cần gửi ra transport theo thiết kế của ứng dụng. Broker lưu message theo retention và acknowledgement semantics của broker.

Không cộng các con số ở mọi tầng thành một backlog tổng nếu chúng mô tả cùng một event ở các giai đoạn khác nhau. Hãy gắn eventId, correlationId, listener/consumer và aggregateId để nối các tầng mà không đếm trùng.

## 3. Đo baseline và xác định mức độ ưu tiên

Trước khi drain, lưu lại trạng thái hiện tại để có thể đánh giá tiến triển và xác định thời điểm backlog bắt đầu tăng.

Các chỉ số nên thu thập:

- Tổng số message/publication đang chờ theo từng listener hoặc consumer.
- Tuổi message cũ nhất và phân phối tuổi P50/P95/P99.
- Arrival rate: số event được tạo mỗi giây/phút.
- Completion rate: số event xử lý thành công mỗi giây/phút.
- Retry rate, redelivery rate và số message vào DLQ.
- Số consumer/worker đang hoạt động và trạng thái health.
- Processing latency và error rate theo event type.
- Outbox age, publication incomplete age và consumer lag.
- Database CPU, I/O, lock wait, connection pool và broker resource usage.

Có thể xếp mức ưu tiên theo tác động nghiệp vụ:

| Mức | Tình huống | Hướng xử lý |
|---|---|---|
| Khẩn cấp | Event thanh toán/đơn hàng vượt SLA, side effect có nguy cơ sai | Bảo vệ dữ liệu, khoanh vùng, xử lý có kiểm soát |
| Cao | Backlog tăng liên tục, oldest age tiến gần SLA | Khôi phục throughput và xử lý nguyên nhân |
| Trung bình | Backlog tăng theo đỉnh tải nhưng vẫn drain được | Theo dõi, điều chỉnh capacity |
| Thấp | Backlog nhỏ, tuổi thấp, completion rate cao hơn arrival rate | Theo dõi bình thường |

Ghi lại thời điểm, môi trường, event type, listener, queue/topic và thay đổi triển khai gần nhất. Dữ liệu này giúp liên hệ backlog với một producer mới, một consumer lỗi hoặc một dependency vừa suy giảm.

## 4. Tính tốc độ drain và thời gian phục hồi

Để backlog giảm, completion rate phải lớn hơn arrival rate trong khoảng thời gian đủ dài.

Nếu B là số message đang chờ, lambda là arrival rate và mu là completion rate, tốc độ giảm ròng là mu trừ lambda, với điều kiện mu lớn hơn lambda.

Thời gian drain gần đúng:

\[
T \approx \frac{B}{\mu - \lambda}
\]

Ví dụ backlog có 120.000 message, producer tiếp tục tạo 40 message/giây và consumer xử lý 100 message/giây. Tốc độ giảm ròng là 60 message/giây; thời gian drain lý tưởng khoảng 2.000 giây, chưa tính retry, message nặng và biến động tải.

Nếu completion rate chỉ bằng arrival rate, backlog không giảm. Nếu completion rate thấp hơn arrival rate, tăng số worker một chút có thể chỉ làm backlog tiếp tục tăng chậm hơn.

Đây là ước lượng để lập kế hoạch. Trong thực tế, đo tốc độ theo từng event type/partition và tính đến giới hạn downstream, retry, lock contention và thời gian xử lý không đồng đều.

## 5. Chẩn đoán nguyên nhân trước khi tăng consumer

Backlog thường là triệu chứng của một bottleneck hoặc lỗi lặp lại. Các nguyên nhân phổ biến:

- Consumer bị dừng, crash hoặc không được đăng ký.
- Listener liên tục ném exception do bug hoặc dữ liệu không hợp lệ.
- Database chậm, connection pool cạn hoặc lock contention.
- Broker không cấp message do thiếu quyền, sai binding hoặc consumer không hoạt động.
- Một partition/queue có tải lệch hoặc hot key.
- Executor hết thread hoặc queue nội bộ bị đầy.
- External API bị throttling hoặc timeout.
- Message quá lớn làm deserialize/GC tốn thời gian.
- Retry policy requeue quá nhanh gây vòng lặp nóng.
- Deployment mới tạo ra event type hoặc schema version consumer chưa hỗ trợ.

Đi theo chuỗi xử lý:

1. Producer có tạo event đúng tốc độ không?
2. Publication/outbox có được ghi thành công không?
3. Relay có gửi được message và nhận confirm không?
4. Broker có route message tới đúng queue/topic không?
5. Consumer có nhận message không?
6. Listener có bắt đầu xử lý và commit side effect không?
7. Ack/completion có được ghi nhận không?

Tìm exception đầu tiên trong chuỗi, không chỉ exception cuối cùng sau nhiều lần retry. Nếu tất cả message của một event type cùng lỗi deserialize, tăng consumer sẽ làm lỗi lặp nhanh hơn.

## 6. Khoanh vùng và bảo vệ hệ thống

Trong lúc điều tra, tránh để backlog làm sập database hoặc dependency downstream.

Các biện pháp có thể áp dụng tùy kiến trúc:

- Giới hạn concurrency hoặc prefetch để giảm áp lực lên database.
- Tạm dừng consumer của event type gây lỗi nếu xử lý tiếp có thể tạo side effect sai.
- Giới hạn tốc độ producer hoặc áp dụng admission control khi downstream không đáp ứng.
- Tách queue/worker theo nhóm event có SLA khác nhau.
- Dùng circuit breaker cho dependency ngoài đang lỗi.
- Giữ outbox bền vững khi broker tạm thời không sẵn sàng.
- Cô lập message poison vào DLQ/quarantine thay vì retry vô hạn.
- Bảo vệ connection pool và tài nguyên dùng chung cho request đồng bộ.

Không pause toàn bộ consumer nếu chỉ một nhóm event gây lỗi và các nhóm khác vẫn an toàn. Ngược lại, nếu database là bottleneck chung, tăng concurrency ở từng queue có thể làm ảnh hưởng toàn bộ ứng dụng.

Trước khi dừng hoặc restart consumer, kiểm tra acknowledgement mode, unacked message và shutdown behavior để hiểu message sẽ được commit, requeue hay redeliver.

## 7. Khôi phục backlog của Spring Modulith Event Publication Registry

Trong Spring Modulith, Event Publication Registry theo dõi publication tới các transactional listener. Nếu listener thất bại, publication có thể còn ở trạng thái chưa hoàn tất để ứng dụng điều tra và resubmit theo API của phiên bản đang dùng.

Quy trình phục hồi:

1. Xác định listener có nhiều publication chưa hoàn tất.
2. Lấy mẫu event và exception để tìm nguyên nhân gốc.
3. Kiểm tra listener bean, transaction, database và event contract.
4. Sửa lỗi code/cấu hình hoặc khôi phục dependency.
5. Xác minh listener xử lý thành công một event đại diện.
6. Resubmit publication theo API công khai được hỗ trợ.
7. Theo dõi số publication chưa hoàn tất và tuổi bản ghi giảm.
8. Kiểm tra side effect nghiệp vụ và duplicate.

Spring Modulith cung cấp API IncompleteEventPublications để truy vấn/resubmit publication chưa hoàn tất; tên method và overload cần đối chiếu đúng phiên bản dependency. Không tự cập nhật hoặc xóa hàng trong bảng registry bằng SQL để ép trạng thái hoàn tất.

Publication thường được theo dõi theo listener. Một event có thể đã hoàn tất ở listener A nhưng vẫn chưa hoàn tất ở listener B. Chỉ phục hồi listener lỗi và giữ nguyên kết quả đã hoàn tất của listener khác theo semantics framework.

Registry không tự bảo đảm listener idempotent. Trường hợp listener đã commit side effect nhưng lỗi xảy ra trước khi publication được đánh dấu hoàn tất có thể dẫn tới xử lý lại. Listener cần deduplicate bằng event ID hoặc khóa nghiệp vụ và cập nhật dedupe record cùng transaction với side effect khi có thể.

## 8. Khôi phục backlog của transactional outbox

Outbox relay đọc các bản ghi cần gửi và publish tới broker. Backlog outbox có thể tăng dù broker vẫn khỏe nếu relay dừng, credential sai, publisher confirm không đến hoặc message không được route.

Kiểm tra:

- Số record PENDING/FAILED và tuổi record cũ nhất.
- Relay process, lease/claim và số worker.
- Kết nối broker, quyền publish và virtual host.
- Exchange/topic, routing key, mandatory return.
- Publisher confirm ACK/NACK/timeout.
- Retry count và lỗi gần nhất.
- Transaction cập nhật trạng thái SENT.

Chỉ đánh dấu outbox record SENT theo semantics gửi đã được xác nhận. Nếu broker confirm thành công nhưng relay dừng trước khi cập nhật trạng thái, record có thể được gửi lại. Đây là cửa sổ duplicate cần consumer idempotent xử lý.

Khi relay phục hồi, tăng throughput từ từ và theo dõi broker/consumer capacity. Không chạy nhiều relay trên cùng tập record nếu cơ chế claim không bảo đảm phân phối công việc an toàn.

Outbox là nguồn công việc cần gửi, không phải bằng chứng consumer đã xử lý. Sau khi outbox hết PENDING, vẫn cần theo dõi queue/topic lag và kết quả consumer.

## 9. Khôi phục backlog RabbitMQ

Với RabbitMQ, phân biệt ready message và unacknowledged message:

- **Ready:** broker đang giữ message chờ consumer nhận.
- **Unacked:** consumer đã nhận nhưng chưa ack/nack.
- **DLQ:** message đã được dead-letter theo policy.

Nếu ready tăng, kiểm tra consumer count, routing, queue binding, prefetch và tốc độ xử lý. Nếu unacked tăng, consumer có thể đang xử lý chậm, bị treo hoặc giữ message quá lâu trước khi ack.

Các bước thường dùng:

1. Xác minh consumer đang kết nối đúng virtual host và queue.
2. Kiểm tra ready, unacked, redelivery và consumer utilization.
3. Kiểm tra prefetch để tránh một consumer giữ quá nhiều message.
4. Xác minh listener commit transaction trước acknowledgement theo thiết kế.
5. Kiểm tra retry/DLX và lỗi đầu tiên.
6. Tăng consumer có kiểm soát nếu downstream còn capacity.
7. Theo dõi queue depth và oldest message age trong quá trình drain.

Không purge queue để làm số liệu về 0 nếu chưa xác định message có thể bỏ. Purge là thao tác loại bỏ message và có thể làm mất event nghiệp vụ. Chỉ dùng khi có quyết định nghiệp vụ rõ, có audit và đã xác định side effect.

Nếu queue depth giảm nhưng unacked tăng, backlog chưa thực sự được giải quyết; message chỉ chuyển từ broker-ready sang consumer-in-flight.

## 10. Khôi phục backlog Kafka

Với Kafka, backlog thường được quan sát qua consumer lag: chênh lệch giữa offset mới nhất của partition và offset đã commit bởi consumer group.

Kiểm tra:

- Lag theo từng partition, không chỉ tổng group.
- Consumer group có đủ member và partition assignment không.
- Một partition có hot key hoặc event nặng không.
- Consumer poll, processing latency và commit interval.
- Rebalance liên tục hoặc lỗi heartbeat.
- Retention của topic và nguy cơ dữ liệu hết hạn trước khi đọc.
- Dead-letter topic và retry topic nếu có.

Tăng số consumer không luôn tăng throughput. Trong một consumer group, số consumer hữu ích bị giới hạn bởi số partition được gán; consumer vượt quá số partition có thể idle. Nếu một partition nóng, cần xem key distribution và thời gian xử lý của record trên partition đó.

Không reset offset tùy tiện để “bỏ qua backlog”. Reset offset về phía trước có thể bỏ mất event chưa xử lý; reset về phía sau có thể replay side effect. Mọi thay đổi offset cần có phạm vi, event range, idempotency và kế hoạch đối chiếu rõ ràng.

Theo dõi lag theo partition và oldest record age. Tổng lag giảm có thể che giấu một partition vẫn bị kẹt.

## 11. Phân loại retry và message poison

Một message poison là message liên tục thất bại do payload, schema, dữ liệu hoặc logic cố định. Retry không giới hạn sẽ chiếm capacity và làm các message hợp lệ phía sau bị chậm.

Phân loại lỗi:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout database, broker reconnect | Retry có backoff và giới hạn |
| Dependency unavailable | External API outage | Circuit breaker, retry theo SLA |
| Contract/schema | Version không hỗ trợ, deserialize lỗi | Quarantine/DLQ, cập nhật consumer hoặc contract |
| Dữ liệu nghiệp vụ | Thiếu tham chiếu bắt buộc, trạng thái không hợp lệ | Điều tra, sửa dữ liệu hoặc compensation |
| Bug code | Null pointer, mapping lỗi | Dừng retry nóng, sửa và deploy bản mới |

Một policy thường gồm số lần thử tối đa, exponential backoff, jitter, phân loại exception và DLQ. Không dùng requeue ngay lập tức không giới hạn.

Khi đưa message vào DLQ, lưu eventId, eventType, schemaVersion, correlationId, consumer, attempt count, timestamp và error category. Hạn chế lưu payload nhạy cảm trong log; payload gốc có thể được giữ trong vùng quarantine có quyền truy cập và retention phù hợp.

## 12. Drain DLQ và replay an toàn

DLQ là nơi cô lập message thất bại, không phải thùng rác. Trước khi replay:

1. Phân nhóm lỗi theo nguyên nhân và event version.
2. Xác định message có side effect nào đã xảy ra trước khi lỗi không.
3. Sửa nguyên nhân ở consumer, dữ liệu hoặc dependency.
4. Xác minh decoder hỗ trợ schema version của message.
5. Chọn một nhóm nhỏ để replay thử.
6. Kiểm tra idempotency và trạng thái nghiệp vụ.
7. Replay theo batch có giới hạn.
8. Theo dõi success/failure và giữ lại message vẫn lỗi.

Không replay toàn bộ DLQ ngay sau khi deploy nếu chưa kiểm tra mẫu. Một lỗi contract cố định có thể làm DLQ tăng trở lại rất nhanh.

Khi replay cùng một event, giữ eventId gốc để deduplication nhận diện duplicate. Nếu cần phân biệt lần chạy phục hồi, thêm replayRunId hoặc recoveryRunId ở metadata vận hành; không tạo eventId mới để biến một message cũ thành event nghiệp vụ mới.

Nếu consumer đã thực hiện side effect trước khi lỗi, cần kiểm tra inbox/processed-event record hoặc trạng thái nghiệp vụ trước khi phát lại. Không giả định broker redelivery luôn đồng nghĩa side effect chưa xảy ra.

## 13. Tăng throughput có kiểm soát

Sau khi xử lý nguyên nhân lỗi, có thể tăng năng lực drain. Tăng concurrency theo từng bước và đo phản ứng của toàn chuỗi.

Các nút điều chỉnh:

- Số consumer instance.
- Số worker/thread trong listener executor.
- Prefetch hoặc số message in-flight.
- Batch size khi đọc/ghi.
- Số partition và mức song song theo partition.
- Connection pool database.
- Rate limit khi gọi external API.

Tăng worker chỉ hữu ích khi bottleneck nằm ở khả năng xử lý song song. Nếu database đã ở mức CPU cao hoặc lock wait lớn, thêm worker có thể làm completion rate giảm. Nếu external API có rate limit, cần giới hạn tốc độ gọi thay vì gửi dồn backlog.

Tăng capacity theo nhịp:

1. Ghi baseline.
2. Tăng một tham số nhỏ.
3. Quan sát throughput, error rate, database và broker.
4. Giữ nếu completion rate tăng mà lỗi không tăng.
5. Giảm lại nếu lock, timeout hoặc redelivery tăng.
6. Lặp lại tới khi đạt drain rate an toàn.

Không thay đổi đồng thời prefetch, worker count, batch size và connection pool nếu chưa có cách xác định tham số nào gây tác động.

## 14. Bảo vệ thứ tự và tính nhất quán nghiệp vụ

Backlog có thể làm event đến muộn hoặc sai thứ tự do retry và nhiều consumer. Một event version mới có thể được xử lý trước event version cũ của cùng aggregate nếu kiến trúc không giữ ordering.

Các biện pháp:

- Dùng aggregateVersion hoặc sequence để phát hiện event cũ/gap.
- Partition theo aggregate key khi broker hỗ trợ ordering theo partition.
- Dùng optimistic/pessimistic locking khi cập nhật projection.
- Giữ event chưa thể áp dụng trong inbox chờ nếu cần đủ sequence.
- Không bỏ qua event gap mà không có reconciliation.
- Đảm bảo saga/process manager có trạng thái bền vững và xử lý event đến muộn.

Nếu cần drain nhanh, không hy sinh invariant bằng cách chạy song song các event của cùng aggregate khi chúng phải tuần tự. Có thể song song giữa các aggregate độc lập và giữ ordering trong từng aggregate.

Sau khi backlog giảm, kiểm tra projection checkpoint/version và trạng thái saga. Queue hết message không chứng minh dữ liệu downstream đã đúng.

## 15. Backpressure và ngăn backlog tái diễn

Drain chỉ xử lý phần tồn đọng. Để tránh backlog quay lại, hệ thống cần điều chỉnh tốc độ producer và consumer theo capacity downstream.

Các kỹ thuật:

- Giới hạn tốc độ publish hoặc áp dụng admission control.
- Tách luồng event có SLA/cost khác nhau.
- Dùng bounded executor queue để tránh tăng memory vô hạn.
- Dùng circuit breaker và rate limiter cho dependency ngoài.
- Điều chỉnh batch và concurrency theo metric.
- Autoscale consumer dựa trên lag và oldest age, có giới hạn.
- Giữ outbox bền vững khi broker tạm thời không sẵn sàng.
- Cảnh báo sớm khi arrival rate vượt completion rate trong một khoảng liên tục.

Autoscaling chỉ hiệu quả khi có thể tăng consumer và bottleneck có thể mở rộng. Với Kafka, partition count giới hạn số consumer hữu ích trong một group. Với database, connection và lock capacity có thể là giới hạn trước số instance.

Không autoscale chỉ theo queue depth tức thời; dùng thêm oldest age, processing latency và downstream saturation để tránh scale lên khi consumer đang bị lỗi cố định.

## 16. Quan sát tiến độ drain

Trong khi xử lý backlog, dashboard cần hiển thị cùng lúc lượng tồn, tốc độ vào/ra và chất lượng xử lý.

Metric cần có:

- Backlog depth theo registry/listener/queue/topic/consumer.
- Oldest message/publication age.
- Arrival rate và successful completion rate.
- Retry, redelivery, duplicate và DLQ rate.
- Consumer count, active worker và in-flight message.
- Outbox PENDING/FAILED và relay throughput.
- Database CPU, I/O, lock wait, connection pool.
- Consumer lag theo partition.
- Projection lag và saga age.

Dùng eventId, correlationId, aggregateId và listener/consumer name trong log để điều tra một event cụ thể. Không dùng các ID có cardinality cao làm metric label.

Một dashboard chỉ có queue depth là chưa đủ. Depth giảm trong khi error rate tăng có thể do message bị dead-letter hoặc bị drop. Cần phân biệt processed successfully, retried, dead-lettered và discarded theo quyết định có audit.

## 17. Xác nhận backlog đã được xử lý

Không kết thúc incident chỉ vì queue depth bằng 0. Xác nhận ở từng tầng:

- Publication nội bộ chưa hoàn tất đã về mức bình thường và các listener cần thiết đã hoàn tất.
- Outbox PENDING/FAILED đã được gửi hoặc có quyết định xử lý.
- Broker ready và unacked message ở mức bình thường.
- Kafka lag đã về ngưỡng mục tiêu ở từng partition.
- Retry queue và DLQ đã được phân loại; không còn message lỗi bị bỏ quên.
- Projection/read model bắt kịp source version/checkpoint.
- Saga/process manager không còn trạng thái chờ quá SLA.
- Không có duplicate side effect hoặc reconciliation mismatch.
- Oldest age và completion latency trở lại trong SLA.
- Arrival rate và completion rate ổn định sau khi tải trở về bình thường.

Giữ theo dõi sau khi backlog đã drain để phát hiện message cũ phát sinh từ retry schedule, consumer restart hoặc batch job chạy theo lịch.

Ghi lại số lượng đã xử lý, số lượng replay, số lượng quarantine, thời gian drain, nguyên nhân gốc và thay đổi cấu hình. Đây là bằng chứng để đánh giá incident và cải thiện capacity.

## 18. Runbook xử lý backlog

Một trình tự vận hành thực tế:

1. Xác định event type, listener/consumer và tầng đang có backlog.
2. Ghi baseline: depth, oldest age, arrival/completion rate và error rate.
3. Đánh giá tác động nghiệp vụ và SLA.
4. Tìm exception đầu tiên, dependency hoặc thay đổi triển khai liên quan.
5. Khoanh vùng consumer/producer gây lỗi; bảo vệ database và downstream.
6. Phân loại message lỗi tạm thời, poison, schema hoặc nghiệp vụ.
7. Sửa nguyên nhân và xác minh bằng một nhóm nhỏ.
8. Phục hồi registry/outbox/consumer bằng API hoặc cơ chế được hỗ trợ.
9. Drain retry/DLQ theo batch có giới hạn và giữ idempotency.
10. Tăng throughput từng bước nếu downstream còn capacity.
11. Theo dõi ordering, projection, saga và reconciliation.
12. Xác nhận mọi tầng đã về ngưỡng bình thường.
13. Ghi incident evidence, nguyên nhân gốc và hành động phòng ngừa.

Với thao tác có thể bỏ message, reset offset, purge queue hoặc xóa publication, cần xác định rõ phạm vi và side effect trước khi thực hiện. Không dùng các thao tác phá hủy để làm dashboard hiển thị backlog bằng 0.

## 19. Lỗi thường gặp khi xử lý backlog

**Chỉ nhìn queue depth.** Có thể còn unacked, retry, DLQ hoặc publication chưa hoàn tất. Đo từng tầng và oldest age.

**Tăng consumer trước khi tìm nguyên nhân.** Nếu lỗi là schema hoặc database lock, tải sẽ tăng mà backlog không giảm. Phân loại lỗi trước.

**Retry poison message liên tục.** Message lỗi cố định chiếm capacity. Quarantine/DLQ và xử lý nguyên nhân.

**Purge queue để giải quyết incident.** Có thể mất event nghiệp vụ. Chỉ loại bỏ khi có quyết định rõ và audit.

**Reset Kafka offset để lag về 0.** Có thể bỏ qua event chưa xử lý hoặc replay side effect. Lập kế hoạch theo partition, offset và idempotency.

**Replay toàn bộ DLQ cùng lúc.** Có thể tái tạo sự cố và gây tải đột biến. Thử một batch nhỏ rồi tăng dần.

**Đánh dấu outbox SENT khi mới gửi mà chưa có confirm.** Có thể mất message. Chỉ cập nhật theo semantics transport.

**Giả định registry là event store.** Publication registry theo dõi giao listener, không thay thế lịch sử event dài hạn.

**Không kiểm tra side effect trước replay.** Event có thể đã thực hiện một phần nghiệp vụ. Kiểm tra idempotency và trạng thái trước khi gửi lại.

**Drain nhanh bằng cách phá ordering.** Projection hoặc aggregate có thể sai. Giữ sequence và invariant theo aggregate.

## 20. Checklist phòng ngừa và phục hồi

- [ ] Có metric depth và oldest age cho từng tầng event.
- [ ] Có arrival rate, completion rate và retry/DLQ rate.
- [ ] Có cảnh báo khi backlog tăng liên tục hoặc vượt SLA.
- [ ] Có owner và runbook cho registry, outbox, broker và consumer.
- [ ] Listener/consumer idempotent khi nhận duplicate.
- [ ] Retry có backoff, giới hạn và phân loại exception.
- [ ] Poison message được quarantine/DLQ.
- [ ] Có giới hạn concurrency, prefetch và batch size.
- [ ] Producer có backpressure hoặc admission control phù hợp.
- [ ] Có cơ chế phục hồi publication/outbox theo API được hỗ trợ.
- [ ] Có kiểm tra ordering/version và reconciliation.
- [ ] Có quy trình replay an toàn và giữ event identity.
- [ ] Có xác nhận sau drain ở mọi tầng.
- [ ] Có lưu incident evidence và cải thiện capacity sau sự cố.

Xử lý backlog là quá trình phục hồi có kiểm soát: xác định đúng tầng tồn đọng, tìm nguyên nhân gốc, bảo vệ tài nguyên downstream, rồi tăng throughput và replay theo batch. Với Spring Modulith, cần tách publication nội bộ khỏi outbox và broker; giữ listener idempotent, tôn trọng transaction và ordering, đồng thời xác nhận trạng thái nghiệp vụ sau khi message đã được giao. Khi đo cả tuổi backlog, tốc độ vào/ra và kết quả side effect, đội vận hành có thể drain an toàn và ngăn backlog tái diễn.
