# Cắt chuyển consumer

*Di chuyển consumer sang phiên bản hoặc hạ tầng mới mà không bỏ sót và không nhân đôi tác động nghiệp vụ*

Trong một hệ thống Spring Modulith, application event có thể được xử lý bởi listener nội bộ hoặc externalize đến broker để consumer độc lập tiếp nhận. Khi cần thay consumer, chuyển từ queue/topic cũ sang mới, đổi consumer group, thay serializer hoặc triển khai một phiên bản xử lý mới, nhóm phát triển phải bảo đảm event đang chờ vẫn được xử lý và side effect không bị lặp ngoài ý muốn.

**Cắt chuyển consumer** là quá trình chuyển quyền xử lý một luồng event từ consumer hiện tại sang consumer đích theo một ranh giới có thể quan sát và phục hồi. Cắt chuyển an toàn cần xác định vị trí đã xử lý, xử lý backlog, thời điểm dừng consumer cũ, cách consumer mới tiếp tục và điều kiện rollback. Việc chỉ khởi động phiên bản mới rồi tắt phiên bản cũ không đủ để chứng minh không mất event.

## 1. Xác định phạm vi của lần cắt chuyển

Trước khi thay đổi, mô tả rõ thứ đang được di chuyển:

- **Consumer implementation:** thay đổi code listener hoặc cách xử lý nhưng vẫn dùng cùng broker destination.
- **Consumer group:** chuyển Kafka consumer sang group ID mới hoặc thay cách phân chia partition.
- **Queue/subscription:** chuyển RabbitMQ consumer sang queue mới hoặc thay binding.
- **Broker hoặc cluster:** chuyển message từ hệ thống messaging này sang hệ thống khác.
- **Schema/contract:** consumer mới đọc thêm version event hoặc chuyển đổi payload lịch sử.
- **Read model:** dựng lại projection mới và chuyển truy vấn sang dữ liệu được consumer mới tạo.

Mỗi phạm vi có cách quản lý tiến độ khác nhau. Thay code trong cùng Kafka group thường dùng cơ chế rebalance và offset của group. Dùng group ID mới tạo ra một tiến độ độc lập. Với RabbitMQ, hai consumer cùng đọc một queue sẽ cạnh tranh nhận message; hai queue được bind cùng exchange sẽ nhận hai bản độc lập. Không thể dùng một quy trình cắt chuyển duy nhất cho mọi topology.

Ghi lại nguồn event, destination, consumer hiện tại, consumer đích, event type, schema version, side effect, checkpoint và thời gian lưu message trước khi bắt đầu.

## 2. Chọn chiến lược cắt chuyển

Ba chiến lược thường dùng:

| Chiến lược | Cách thực hiện | Phù hợp khi | Rủi ro chính |
|---|---|---|---|
| Stop-the-world / drain | Dừng nhận mới, xử lý hết backlog, dừng consumer cũ rồi bật consumer mới | Luồng ít lưu lượng, có thể tạm dừng hoặc chấp nhận khoảng gián đoạn | Thời gian dừng kéo dài nếu backlog lớn hoặc producer không thể tạm dừng |
| Blue/green | Chạy consumer mới ở chế độ kiểm tra hoặc destination riêng, xác nhận sẵn sàng rồi chuyển quyền xử lý | Cần chuẩn bị phiên bản mới trước cutover | Hai consumer có thể cùng tạo side effect nếu cùng nhận dữ liệu thật |
| Canary / partition-by-partition | Chuyển một phần partition, tenant hoặc nhóm event trước, sau đó mở rộng | Lưu lượng lớn và có thể chia luồng độc lập | Phải quản lý ownership, thứ tự và checkpoint theo từng phần |

Chọn chiến lược theo khả năng tạm dừng producer, topology broker, mức độ quan trọng của event và khả năng idempotent của consumer. Shadow consumer có thể đọc bản sao để so sánh kết quả, nhưng không được gửi email, thu tiền hoặc cập nhật hệ thống bên ngoài như consumer chính.

## 3. Chuẩn bị trước khi cutover

Một lần cắt chuyển nên có các điều kiện sẵn sàng được xác nhận trước:

1. Consumer đích khởi động được, có cấu hình, quyền broker và kết nối dependency hợp lệ.
2. Consumer đích đọc được mọi schema version còn nằm trong retention hoặc backlog.
3. Checkpoint/offset bắt đầu đã được xác định và có thể đối chiếu.
4. Side effect có idempotency key hoặc cơ chế deduplication phù hợp.
5. Metric, log, trace, dashboard và alert đã phân biệt consumer cũ với consumer mới.
6. Backlog hiện tại và tốc độ xử lý đã được đo để dự tính thời gian drain/catch-up.
7. Có quy trình dừng, rollback và người chịu trách nhiệm ra quyết định.
8. Có cách xác nhận dữ liệu nghiệp vụ hoặc read model sau chuyển đổi.

Không bắt đầu cutover khi consumer mới chỉ “healthy” ở mức process sống. Cần kiểm tra nó có thể deserialize event, truy cập database và hoàn tất một giao dịch thử nghiệm theo đúng chính sách.

## 4. Chọn điểm bắt đầu cho consumer mới

Điểm bắt đầu quyết định event nào consumer mới sẽ đọc:

- **Tiếp tục từ checkpoint hiện tại:** phù hợp khi chuyển consumer cùng một luồng và có thể chuyển giao tiến độ đã xác nhận.
- **Đọc từ vị trí cuối hiện tại:** phù hợp với một consumer mới chỉ quan tâm event phát sinh sau thời điểm cutover, nếu nghiệp vụ cho phép bỏ lịch sử.
- **Replay từ đầu hoặc snapshot:** phù hợp khi dựng lại projection hoặc thay đổi logic cần tính lại dữ liệu.
- **Đọc từ watermark đã đối soát:** phù hợp khi chuyển broker hoặc nguồn event có cơ chế đồng bộ riêng.

Không mặc định consumer mới phải bắt đầu từ `latest`. Nếu consumer cần trạng thái đầy đủ, bắt đầu từ `latest` sẽ bỏ qua dữ liệu lịch sử. Cũng không mặc định bắt đầu từ `earliest` an toàn: message cũ có thể tạo side effect trùng nếu không có inbox hoặc read model mới tách biệt.

Với Kafka, offset là theo từng partition và biểu diễn vị trí tiếp theo cần đọc khi commit. Với aggregate sequence, checkpoint thường cần khóa theo aggregate. Với RabbitMQ, queue không cung cấp một offset toàn cục tương đương Kafka; cần dựa trên message còn trong queue, acknowledgement và cơ chế lưu dấu/đối soát của ứng dụng.

## 5. Cắt chuyển consumer Kafka

Kafka phân phối partition cho các consumer trong cùng group. Nếu consumer cũ và mới dùng cùng `group.id`, broker sẽ rebalance và phân chia partition giữa các member. Đây là cách rolling deployment phổ biến khi code mới tương thích với cùng topic và schema. Trong lúc rebalance, cần xử lý việc thu hồi partition và bảo đảm offset chỉ commit sau khi record đã được xử lý bền vững.

Nếu consumer mới dùng group ID khác, group mới có offset độc lập. Nó có thể đọc lại toàn bộ retention hoặc bắt đầu ở `latest` tùy `auto.offset.reset` và trạng thái group. Khi chạy đồng thời hai group, cả hai đều nhận cùng luồng event. Điều này hữu ích cho shadow/canary nhưng có thể nhân đôi side effect nếu cả hai đều ghi cùng dữ liệu hoặc gọi cùng API.

Quy trình chuyển Kafka group có thể là:

1. Xác định offset đã commit của group cũ cho từng partition.
2. Chọn cách tiếp tục: dùng lại group ID với rolling deployment, hoặc tạo group mới và gán offset ban đầu rõ ràng.
3. Nếu dùng group mới, kiểm tra topic/partition mapping và đặt offset theo checkpoint đã đối soát.
4. Chạy consumer mới với side effect bị cô lập hoặc idempotent trong giai đoạn xác nhận.
5. So sánh lag, số record đã xử lý và kết quả read model.
6. Chuyển quyền xử lý chính thức, dừng group cũ và theo dõi rebalance.

Khi chuyển từ group cũ sang group mới, không sao chép một offset lớn nhất duy nhất cho toàn topic. Mỗi partition có tiến độ riêng. Nếu consumer xử lý song song, chỉ chuyển offset liên tục đã hoàn tất; không commit vượt qua record lỗi hoặc record còn đang chạy.

## 6. Cắt chuyển consumer RabbitMQ

RabbitMQ consumer đọc message từ queue. Nhiều consumer cùng queue thường cạnh tranh nhận các message khác nhau; chúng không tự động nhận mỗi message một bản. Vì vậy, chạy consumer cũ và mới đồng thời trên cùng queue sẽ chia tải giữa hai phiên bản. Cách này có thể phù hợp cho rolling deployment khi hai phiên bản tương thích với payload và side effect.

Nếu tạo queue mới và bind nó vào cùng exchange, queue mới nhận bản sao message được publish sau khi binding tồn tại. Nó không tự nhận lại message cũ đã được queue cũ xử lý hoặc đã rời queue. Muốn chuyển backlog, cần kế hoạch drain queue cũ, shovel/federation hoặc sao chép có kiểm soát tùy yêu cầu và công cụ broker.

Một quy trình stop-and-drain cho RabbitMQ:

1. Xác nhận queue cũ, số message ready và unacknowledged.
2. Ngừng cấp message mới cho consumer cũ hoặc tạm dừng producer theo kế hoạch.
3. Chờ consumer hoàn tất xử lý và ACK các delivery đang giữ.
4. Xác nhận unacknowledged về 0 và queue ready đã drain, hoặc ghi lại phần backlog còn lại để chuyển tiếp.
5. Dừng consumer cũ sau khi delivery đang xử lý đã kết thúc.
6. Bật consumer mới trên queue đích và xác nhận message được xử lý.

Nếu channel đóng trước ACK, message unacknowledged có thể được requeue. Consumer mới cần idempotent để chịu được redelivery. Khi dùng DLX, kiểm tra cả dead-letter queue và message retry đang chờ; queue chính rỗng không có nghĩa mọi event đã hoàn tất.

## 7. Dựng consumer mới ở chế độ shadow

Shadow consumer giúp so sánh logic mới với logic hiện tại trước khi nhận quyền xử lý chính. Có thể triển khai bằng consumer group riêng, queue riêng hoặc bản sao dữ liệu test. Trong giai đoạn này:

- Đọc cùng event stream với consumer chính.
- Tính kết quả projection hoặc quyết định nghiệp vụ trong vùng dữ liệu riêng.
- Không thực hiện side effect không thể đảo ngược.
- Ghi nhận event ID, kết quả tính toán và sai khác theo quy tắc bảo mật.
- So sánh số lượng, trạng thái, tổng tiền hoặc invariant giữa hai phiên bản.

Shadow mode không nên ghi vào cùng read model production nếu điều đó làm lẫn kết quả hai phiên bản. Nếu cần ghi, dùng schema/table/generation riêng. Khi so sánh, tính đến độ trễ khác nhau: hai consumer có thể đang ở hai checkpoint khác nhau nên cần đối chiếu cùng một watermark.

## 8. Canary theo partition, tenant hoặc event type

Với luồng lớn, có thể chuyển từng phần để giới hạn phạm vi ảnh hưởng. Ví dụ, consumer mới nhận 5% tenant hoặc một nhóm partition trước, sau đó tăng dần. Canary cần một khóa phân chia ổn định để mọi event của cùng aggregate hoặc tenant đi qua đúng consumer trong cùng giai đoạn.

Khi chia partition:

- Không để cùng aggregate được xử lý đồng thời bởi consumer cũ và mới nếu thứ tự nghiệp vụ quan trọng.
- Theo dõi checkpoint riêng cho từng partition hoặc shard.
- Chuyển ownership tại ranh giới đã xác định, không chuyển giữa một chuỗi event đang xử lý dở.
- Đảm bảo retry và dead-letter vẫn route về đúng consumer sở hữu luồng.
- Có khả năng dừng mở rộng canary và đưa phần đã chuyển về phiên bản cũ nếu cần.

Nếu phân chia theo tenant, cần bảo đảm tenant mapping nhất quán giữa producer, router và consumer. Thay đổi thuật toán partitioning có thể di chuyển aggregate sang shard khác; khi đó cần drain hoặc fencing để tránh hai consumer cùng sở hữu một aggregate.

## 9. Bảo đảm không xử lý trùng khi có hai consumer

Trong cutover, duplicate có thể xuất hiện vì replay, hai consumer group cùng đọc, queue mới nhận bản sao, ACK bị mất hoặc consumer cũ hoàn tất side effect nhưng chưa ghi checkpoint. Không dựa vào việc “consumer chỉ chạy một instance” để bảo vệ dữ liệu.

Các biện pháp thường dùng:

- Dùng `eventId` ổn định qua mọi lần publish/retry.
- Lưu inbox theo `(consumerName, eventId)` với unique constraint.
- Cập nhật inbox và read model trong cùng transaction.
- Dùng idempotency key ở API ngoài cho thanh toán, email hoặc tác vụ không thể lặp.
- Dùng aggregate sequence/version để phát hiện event cũ hoặc thiếu.
- Tách dữ liệu shadow/canary khỏi side effect production.

Nếu consumer mới thay thế consumer cũ nhưng dùng một consumer name khác trong inbox, cùng event có thể được xem là chưa xử lý. Khi mục tiêu là tiếp tục cùng một projection, cần quyết định rõ giữ cùng logical consumer identity hay tạo generation mới có dữ liệu riêng. Đừng thay consumer name tùy tiện trong lúc cutover.

## 10. Đồng bộ checkpoint và read model

Consumer migration thường đi cùng thay đổi projection hoặc schema database. Checkpoint phải phản ánh chính xác phần dữ liệu đã được áp dụng.

Với read model mới, một cách an toàn là tạo generation mới:

1. Tạo bảng/index mới cho projection version đích.
2. Khởi tạo checkpoint tại vị trí snapshot hoặc cursor đã xác định.
3. Replay event đến một watermark đã chọn.
4. Bắt kịp event mới trong khi consumer cũ vẫn phục vụ truy vấn.
5. Đối chiếu count, tổng hợp và invariant nghiệp vụ tại cùng watermark.
6. Chuyển query/API sang generation mới.
7. Giữ generation cũ trong thời gian rollback đã định.

Không cập nhật checkpoint trước khi read model được ghi bền vững. Nếu checkpoint tiến trước dữ liệu, event có thể bị bỏ qua sau restart. Nếu dữ liệu commit nhưng checkpoint chưa tiến, event có thể được áp dụng lại; inbox/idempotency phải bảo vệ trường hợp đó.

## 11. Phối hợp với Spring Modulith Event Publication Registry

Event Publication Registry theo dõi publication cần giao đến transactional listener hoặc externalization target. Khi cắt chuyển một listener nội bộ, cần hiểu registry đang lưu publication cho listener identity nào và consumer mới có tiếp tục nhận publication chưa hoàn tất hay tạo một listener identity khác.

Registry không tự động di chuyển offset Kafka, message ready/unacknowledged của RabbitMQ hoặc lịch sử event trong broker. Khi chuyển external consumer, cần dùng công cụ và checkpoint của broker/ứng dụng tương ứng. Khi chuyển listener nội bộ Spring Modulith, cần kiểm tra trạng thái publication chưa hoàn tất, hành vi resubmit và cách phiên bản mới nhận lại event.

Không xóa publication chưa hoàn tất chỉ để làm sạch registry trong lúc cutover. Trước khi resubmit, xác nhận handler idempotent và biết side effect trước đó đã xảy ra đến đâu. Nếu listener name hoặc target thay đổi, lập kế hoạch ánh xạ publication cũ sang consumer mới thay vì giả định framework tự chuyển trạng thái.

## 12. Cutover, rollback và điểm không thể quay lại

Một kế hoạch cutover cần ghi rõ thời điểm chuyển quyền xử lý và điều kiện rollback. Trước cutover, consumer cũ thường là nguồn xử lý chính; consumer mới ở shadow hoặc chưa nhận traffic. Sau cutover, consumer mới xử lý event mới và consumer cũ phải ngừng tạo side effect.

Rollback không đơn giản là bật consumer cũ trở lại. Consumer mới có thể đã commit dữ liệu hoặc tạo side effect mà consumer cũ chưa biết. Trước khi rollback:

- Xác định event cuối cùng đã được consumer mới xử lý bền vững.
- Lưu checkpoint/offset theo partition hoặc stream.
- Xác nhận consumer cũ có thể đọc schema mới đã phát trong thời gian cutover.
- Xác nhận inbox/idempotency ngăn event đã xử lý bị áp dụng lại.
- Quyết định consumer cũ tiếp tục từ checkpoint mới hay rebuild/đối soát.
- Không chạy song song hai consumer có side effect xung đột.

Điểm không thể quay lại có thể là lúc producer bắt đầu phát schema mà consumer cũ không hiểu, lúc side effect không thể đảo ngược được tạo ra hoặc lúc dữ liệu cũ bị xóa. Trước điểm đó, cần có checkpoint và bằng chứng để quyết định tiếp tục hay rollback.

## 13. Runbook cắt chuyển consumer

Một runbook thực tế có thể đi theo các bước:

1. **Inventory:** xác nhận source, destination, consumer group/queue, owner, schema version và side effect.
2. **Baseline:** ghi lại event rate, backlog, oldest event age, lag, error rate và checkpoint hiện tại.
3. **Preflight:** kiểm tra cấu hình, quyền truy cập, kết nối, schema compatibility, idempotency và dashboard của consumer mới.
4. **Shadow/canary:** chạy consumer mới trong vùng cô lập hoặc một phần luồng; so sánh kết quả tại cùng watermark.
5. **Freeze/drain nếu cần:** tạm dừng cấp message mới hoặc dừng consumer cũ theo chiến lược; xử lý hết in-flight delivery.
6. **Transfer progress:** chuyển offset/checkpoint hoặc xác định cursor khởi đầu; kiểm tra từng partition/queue.
7. **Switch ownership:** bật consumer mới làm consumer chính và ngăn consumer cũ tạo side effect.
8. **Verify:** xác nhận completion rate, backlog, dữ liệu read model và số event lỗi.
9. **Observe:** giữ dashboard/alert tăng cường trong cửa sổ ổn định đã định.
10. **Retire old consumer:** chỉ dừng hẳn và xóa tài nguyên cũ sau khi hết cửa sổ rollback và retention cần thiết.

## 14. Metric và tiêu chí hoàn tất

Theo dõi consumer cũ và mới bằng nhãn riêng để so sánh:

- Event processing rate và completion rate.
- Kafka lag theo group/partition hoặc RabbitMQ ready/unacknowledged theo queue.
- Publication chưa hoàn tất và tuổi publication lâu nhất.
- Checkpoint/offset cuối đã commit.
- Retry, redelivery, duplicate skipped và dead-letter count.
- Processing latency p50/p95/p99 và lỗi deserialize.
- Chênh lệch read model hoặc kết quả nghiệp vụ tại cùng watermark.

Không kết luận cutover thành công chỉ vì consumer mới đang `UP`. Tiêu chí hoàn tất nên gồm: consumer mới xử lý được event mới, backlog không tăng ngoài ngưỡng, dữ liệu đạt invariant, không có event bị bỏ sót, duplicate được kiểm soát và consumer cũ không còn giữ side effect.

## 15. Kiểm thử trước và sau cắt chuyển

Các kịch bản cần kiểm tra trong staging hoặc môi trường tương thích:

1. Consumer mới đọc được event/schema cũ và mới.
2. Consumer mới tiếp tục từ offset/checkpoint chính xác.
3. Consumer cũ và mới chạy overlap không tạo side effect trùng.
4. Dừng consumer cũ khi đang có delivery in-flight; message được ACK hoặc redelivery đúng chính sách.
5. Rebalance Kafka không làm commit vượt qua record chưa xử lý.
6. RabbitMQ queue mới/old queue có routing và backlog được chuyển theo kế hoạch.
7. Consumer mới lỗi giữa DB commit và ACK/offset commit nhưng retry không nhân đôi tác động.
8. Rollback consumer mới về consumer cũ sau khi đã xử lý một phần event.
9. Canary dừng giữa chừng và có thể tiếp tục mà không mất ownership của partition/tenant.
10. Metric, alert và runbook phân biệt rõ consumer cũ, mới và backlog.

Kiểm thử broker cần xác nhận semantics thật của queue, partition, acknowledgement và redelivery. Mock listener hoặc kiểm tra process health không đủ để chứng minh cắt chuyển an toàn.

## 16. Những điểm cần nhớ

- Cắt chuyển consumer là chuyển quyền xử lý cùng với tiến độ, backlog và trách nhiệm side effect.
- Chọn stop-and-drain, blue/green hoặc canary theo topology và khả năng tạm dừng producer.
- Kafka offset theo partition; group ID mới có tiến độ độc lập. RabbitMQ consumer cùng queue cạnh tranh message, queue mới cần routing/copy backlog riêng.
- Shadow consumer phải cô lập side effect; không cho hai consumer cùng tạo tác động production ngoài ý muốn.
- Chuyển checkpoint sau khi dữ liệu đã bền vững và chỉ commit tiến độ liên tục đã hoàn tất.
- Dùng event ID, inbox, idempotency key và aggregate version để bảo vệ duplicate.
- Event Publication Registry theo dõi publication của Spring Modulith, không thay thế broker offset hoặc queue state.
- Rollback phải tính đến event mới, schema mới và side effect đã commit; không chỉ bật lại consumer cũ.
- Chỉ kết thúc cutover khi backlog, dữ liệu, metric và quyền xử lý đã được xác nhận.

Khi consumer mới được chuẩn bị và kiểm chứng trước, tiến độ được chuyển giao theo đúng semantics của broker, còn consumer cũ dừng tại ranh giới đã đối soát, hệ thống có thể thay đổi cách xử lý event mà không bỏ sót message. Kết hợp shadow/canary, checkpoint, idempotency và runbook rollback giúp cắt chuyển consumer trong Spring Modulith có thể kiểm soát và phục hồi.
