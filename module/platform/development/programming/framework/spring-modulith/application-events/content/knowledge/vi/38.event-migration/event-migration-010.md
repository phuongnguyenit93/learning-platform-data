# Kết thúc giai đoạn chuyển tiếp

Di trú event thường cần một giai đoạn chuyển tiếp vì producer, consumer, schema và hạ tầng không thể luôn được nâng cấp cùng một thời điểm. Trong giai đoạn này, hệ thống có thể phải hỗ trợ đồng thời hợp đồng cũ và mới, chạy consumer tương thích, chuyển dần producer, đối chiếu kết quả và duy trì khả năng rollback.

Kết thúc giai đoạn chuyển tiếp là thời điểm hệ thống đã chuyển toàn bộ luồng nghiệp vụ sang hợp đồng đích, dữ liệu và backlog cũ đã được xử lý, các consumer cũ không còn cần thiết, và những adapter tương thích tạm thời có thể được gỡ bỏ an toàn. Đây là một quyết định vận hành dựa trên bằng chứng, không chỉ là việc deploy phiên bản code mới.

Với Spring Modulith, cần phân biệt event nội bộ giữa các module với integration event đi qua broker. Event Publication Registry theo dõi publication tới listener nội bộ; nó không tự chứng minh message ở broker đã được tiêu thụ hoặc backlog cũ đã hết. Mỗi ranh giới cần tiêu chí hoàn tất riêng.

## 1. Mục tiêu của giai đoạn kết thúc

Một migration event thường đi theo mô hình expand, migrate, contract:

1. **Expand:** bổ sung schema, consumer hoặc adapter mới trong khi đường cũ vẫn hoạt động.
2. **Migrate:** chuyển producer và consumer từng bước, xử lý dữ liệu tồn đọng, đối chiếu kết quả.
3. **Contract:** ngừng đường cũ, gỡ compatibility code và loại bỏ tài nguyên không còn sử dụng.

Bài này tập trung vào bước contract. Mục tiêu là đưa hệ thống về một trạng thái đơn giản, trong đó:

- Producer phát hợp đồng đích theo đúng schema/version đã công bố.
- Consumer cần thiết đều đọc và xử lý hợp đồng đích.
- Không còn message hợp lệ chỉ có thể đọc bằng consumer cũ.
- Không còn dual publish hoặc bridge tạm thời ngoài kế hoạch.
- Backlog, retry và dead-letter của đường cũ đã được xử lý hoặc có quyết định lưu trữ rõ ràng.
- Khả năng rollback và quy trình khôi phục đã được xác định.
- Tài liệu, dashboard, alert và quyền truy cập phản ánh topology cuối cùng.

Kết thúc migration không có nghĩa xóa ngay mọi dữ liệu cũ. Payload lịch sử có thể cần được lưu theo retention hoặc audit policy. Điều cần chấm dứt là phụ thuộc vận hành vào đường cũ.

## 2. Xác định chính xác phạm vi cần kết thúc

Trước cutover, lập inventory các thành phần tham gia migration. Đừng chỉ tìm tên event trong code; cần bao quát cả cấu hình, deployment và tài nguyên broker.

| Thành phần | Thông tin cần xác nhận |
|---|---|
| Producer | Module/service, phiên bản payload, exchange/topic, routing key |
| Consumer | Listener, group/queue, schema version hỗ trợ, owner |
| Internal application event | Event class, module publisher, module listener |
| Integration adapter | Mapping nội bộ sang envelope/transport message |
| Compatibility bridge | Chuyển đổi event cũ sang mới hoặc ngược lại |
| Outbox/relay | Trạng thái gửi, retry, publisher confirms |
| Publication registry | Publication chưa hoàn tất theo listener |
| Broker topology | Exchange, queue, binding, topic, subscription, DLQ |
| Data history | Outbox archive, event store, payload cần replay |
| Operations | Dashboard, alert, runbook và người chịu trách nhiệm |

Với mỗi consumer, ghi rõ nó có nhận event cũ, event mới hay cả hai. Xác định consumer nào thực hiện side effect nghiệp vụ, consumer nào chỉ phục vụ audit hoặc analytics, và consumer nào có thể bị bỏ sót vì nằm ở một hệ thống ít được deploy thường xuyên.

Một migration chỉ có thể kết thúc khi danh sách producer/consumer đã được xác nhận đầy đủ. Nếu chưa biết một consumer cũ có tồn tại hay không, chưa đủ bằng chứng để xóa hợp đồng cũ hoặc queue cũ.

## 3. Đặt tiêu chí hoàn tất trước khi cutover

Tiêu chí cần đo được và gắn với luồng nghiệp vụ. Ví dụ:

- 100% producer đang hoạt động phát event theo contract đích.
- Tất cả consumer bắt buộc đã chạy phiên bản hỗ trợ contract đích.
- Không còn producer phát payload cũ trong khoảng quan sát đã thống nhất.
- Không còn message cũ trong queue, subscription, retry store hoặc delayed delivery.
- Không còn publication nội bộ chưa hoàn tất vượt quá ngưỡng được điều tra.
- DLQ cũ đã được phân loại và xử lý, archive hoặc chấp nhận loại bỏ theo quyết định nghiệp vụ.
- Số lượng và kết quả nghiệp vụ của luồng cũ/mới đã được đối chiếu.
- Không có duplicate side effect do dual publish hoặc bridge.
- Dashboard, alert và runbook đã chuyển sang topology đích.
- Owner nghiệp vụ và owner vận hành đã xác nhận cutover.

Không dùng một khoảng thời gian cố định cho mọi hệ thống. Thời gian quan sát phải dài hơn chu kỳ phát sinh event liên quan, thời gian retry tối đa, lịch batch và khoảng trễ có thể có của consumer. Với quy trình diễn ra theo tháng hoặc theo mùa, cần tính cả chu kỳ nghiệp vụ đó.

## 4. Chuẩn bị trước khi chuyển sang contract phase

Trước khi tắt đường cũ, xác minh các điều kiện sau:

**Contract đích ổn định:** event type, schema version, required fields, enum và semantics đã được chốt. Consumer mới đã có fixture và test cho payload cũ nếu cần đọc backlog.

**Consumer đích đã sẵn sàng:** listener được deploy, có quyền đọc, converter đúng, transaction và idempotency hoạt động. Consumer phải có khả năng xử lý message sau restart.

**Producer đích đã sẵn sàng:** mapping event, routing và metadata đúng; nếu dùng outbox, relay đã quan sát publisher confirm và xử lý returned message.

**Quan sát đã sẵn sàng:** có metric phân biệt message theo schema version hoặc route, backlog cũ/mới, lỗi deserialize, retry và DLQ. Log có eventId, correlationId và producer/consumer identity.

**Rollback đã được diễn tập ở mức phù hợp:** xác định phiên bản nào có thể quay lại, dữ liệu nào không thể đảo ngược và cách xử lý event mới nếu cần quay về producer cũ.

Không bắt đầu contract phase chỉ vì deployment mới đã healthy. Health của process không chứng minh mọi consumer đã nhận được event hoặc side effect đã commit.

## 5. Chuyển producer và chấm dứt dual publish

Trong giai đoạn migrate, producer có thể phát cả event cũ và mới để phục vụ consumer chưa nâng cấp. Dual publish cần có điểm kết thúc rõ ràng.

Một trình tự an toàn thường là:

1. Deploy consumer hỗ trợ contract đích trước.
2. Xác minh consumer mới đọc được cả payload cũ còn tồn đọng và payload mới.
3. Chuyển producer sang phát contract đích.
4. Theo dõi producer version, schema version, routing và kết quả xử lý.
5. Sau khi mọi producer đã chuyển, tắt cờ dual publish.
6. Xác minh không còn instance cũ hoặc scheduled job cũ phát event theo contract cũ.

Dual publish có thể tạo hai message đại diện cho cùng một sự kiện nghiệp vụ. Nếu hai consumer path cùng thực hiện side effect, cần một idempotency key ổn định dùng chung hoặc một cơ chế chọn một path làm authoritative. Không dựa vào việc hai payload giống nhau để giả định chúng sẽ tự được deduplicate.

Nếu cần giữ hai bản biểu diễn trong một thời gian, giữ cùng logical event ID khi contract cho phép và lưu rõ schema version/route. Consumer phải deduplicate theo định danh sự kiện nghiệp vụ, không chỉ theo message ID do broker tự tạo.

Không tắt dual publish trước khi consumer cũ đã được chuyển hoặc backlog cũ có thể được xử lý bởi consumer mới. Ngược lại, không để dual publish tồn tại vô thời hạn vì nó tăng chi phí, làm khó quan sát và tạo rủi ro side effect trùng.

## 6. Chuyển consumer và ngừng nhận hợp đồng cũ

Sau khi producer đã phát contract đích, consumer cần được chuyển theo từng nhóm.

Với consumer hỗ trợ cả hai version, theo dõi số message theo version và kết quả decode. Khi không còn payload cũ trong nguồn live, có thể lên kế hoạch bỏ decoder cũ sau khi backlog/replay window đã kết thúc.

Với consumer cũ không thể nâng cấp trực tiếp, dùng adapter hoặc bridge tạm thời để chuyển đổi. Bridge phải có owner, metric, alert và ngày kết thúc. Nó không nên trở thành một tầng phụ thuộc vĩnh viễn.

Trước khi dừng consumer cũ:

- Xác minh producer không còn gửi tới route cũ.
- Kiểm tra queue/subscription cũ không còn message cần xử lý.
- Xác minh retry, delayed message và unacked delivery đã được giải quyết.
- Kiểm tra consumer group hoặc subscription không còn cần cho replay.
- Xác nhận không có batch job hoặc tool vận hành dùng endpoint cũ.

Nếu consumer cũ còn có side effect, cần xác định message cuối cùng đã được xử lý thành công. Chỉ dừng consumer sau khi trạng thái nghiệp vụ tương ứng đã được xác minh.

## 7. Drain backlog và xử lý message cũ

Backlog là một trong những lý do phổ biến khiến migration chưa thể kết thúc. Queue có thể hiển thị depth bằng 0 nhưng message vẫn tồn tại ở retry store, DLQ, delayed queue hoặc hệ thống archive.

Lập inventory theo từng nơi lưu trữ:

| Nơi lưu | Việc cần làm |
|---|---|
| Queue/topic cũ | Drain bằng consumer tương thích hoặc chuyển đổi có kiểm soát |
| Unacked/in-flight | Chờ xử lý, xác minh redelivery hoặc dừng consumer an toàn |
| Retry queue/delayed delivery | Chờ hết lịch retry hoặc chuyển theo policy |
| DLQ | Phân loại, sửa nguyên nhân, replay hoặc archive |
| Outbox PENDING | Gửi thành công, đánh dấu theo confirm semantics hoặc xử lý lỗi |
| Publication chưa hoàn tất | Xác minh listener và resubmit theo API hỗ trợ |
| Event archive | Giữ theo retention và khả năng replay đã công bố |

Không xóa queue cũ chỉ vì queue depth hiện tại bằng 0. Kiểm tra consumer count, unacked count, delayed message, DLQ và nguồn retry bên ngoài broker.

Với Kafka, cần xem consumer lag, offset đã commit và retention của topic. Với RabbitMQ, cần xem ready/unacked message, queue arguments, DLX và retry topology. Với broker khác, dùng chỉ số tương ứng.

Nếu message cũ không thể chuyển đổi an toàn, đưa vào quarantine hoặc archive cùng event ID, schema version, lỗi và quyết định xử lý. Không âm thầm bỏ message để đạt tiêu chí backlog bằng 0.

## 8. Đối chiếu kết quả nghiệp vụ trước khi gỡ đường cũ

Trong thời gian chuyển tiếp, hệ thống có thể chạy shadow consumer hoặc so sánh kết quả cũ/mới. Trước khi kết thúc, phải tổng hợp kết quả đối chiếu.

Các phép đối chiếu có thể gồm:

- Số event được phát theo từng producer và schema version.
- Số event được consumer nhận, áp dụng, deduplicate và từ chối.
- Số aggregate được cập nhật ở đường cũ và đường mới.
- Tổng số bản ghi hoặc số liệu nghiệp vụ theo khoảng thời gian.
- Các invariant quan trọng, ví dụ không tạo hai reservation cho cùng một order.
- Chênh lệch trạng thái và danh sách aggregate cần reconciliation.

So sánh count tổng thể là chưa đủ. Hai đường có thể cùng số lượng nhưng xử lý hai tập event khác nhau. Nếu có thể, đối chiếu theo event ID hoặc aggregate ID và sequence/version.

Nếu phát hiện sai lệch, dừng contract phase, phân loại nguyên nhân và sửa dữ liệu theo quy trình có audit. Không xóa bridge hoặc consumer cũ khi vẫn còn chênh lệch chưa giải thích được.

## 9. Giữ idempotency trong giai đoạn cuối

Trong lúc chuyển producer/consumer, cùng một logical event có thể đến từ cả route cũ và route mới. Retry và replay cũng có thể khiến message đã xử lý xuất hiện lần nữa.

Consumer cần idempotency dựa trên định danh ổn định của sự kiện nghiệp vụ. Ghi processed event và side effect trong cùng transaction khi cả hai nằm trong cùng database transaction.

Khi hai schema version biểu diễn cùng một event, canonical event ID hoặc migration mapping phải cho phép consumer nhận diện chúng là một logical event. Nếu legacy event không có ID, cần một quy tắc migration xác định để tạo idempotency key từ dữ liệu ổn định; tránh dùng timestamp hoặc thứ tự nhận message làm khóa.

Không xóa bảng inbox/deduplication cùng lúc với queue cũ nếu còn khả năng redelivery hoặc replay. Retention của dedupe record phải dài hơn khoảng thời gian message có thể xuất hiện lại.

## 10. Kết thúc migration trong Spring Modulith nội bộ

Với application events giữa các module trong cùng ứng dụng, migration có thể liên quan tới package API, event class, listener signature hoặc cách module phát event.

Trước khi xóa event cũ:

1. Xác minh mọi publisher đã chuyển sang event contract mới.
2. Xác minh tất cả listener cần thiết đã xử lý event mới.
3. Kiểm tra không còn module phụ thuộc vào class/package cũ.
4. Xác minh test module và dependency rule phản ánh ranh giới mới.
5. Kiểm tra publication chưa hoàn tất của listener cũ.
6. Xác định có cần giữ adapter nội bộ cho replay hoặc dữ liệu đã lưu hay không.

Event Publication Registry theo dõi publication tới listener. Publication chưa hoàn tất cần được xử lý qua API và persistence implementation được hỗ trợ của phiên bản Spring Modulith đang dùng. Không tự xóa hàng registry để làm sạch trạng thái migration.

Nếu listener cũ đã bị loại khỏi code nhưng registry vẫn còn publication chưa hoàn tất gắn với listener đó, cần có kế hoạch xử lý dữ liệu tồn đọng trước khi xóa compatibility path. Không giả định registry là event store dài hạn hoặc nó tự chuyển publication sang listener mới.

## 11. Kết thúc migration khi có broker hoặc externalization

Khi application event được chuyển thành integration message, cần kiểm tra ranh giới vận chuyển riêng.

Với RabbitMQ:
- Xác minh producer không còn publish exchange/routing key cũ.
- Xác minh queue cũ đã drain và không còn unacked delivery.
- Kiểm tra DLX, retry queue, binding và consumer count.
- Chỉ xóa exchange/queue/binding sau khi xác nhận không còn client sử dụng.

Với Kafka:
- Xác minh producer không còn ghi topic cũ.
- Xác minh consumer group đã xử lý tới offset mục tiêu.
- Xem xét retention, compacted data và consumer replay.
- Chỉ ngừng topic cũ sau khi mọi consumer, batch job và tool đã chuyển.

Với Spring Modulith externalization, xác minh mapping, serialization và publication completion semantics theo đúng phiên bản thư viện. Không coi publication nội bộ hoàn tất là bằng chứng broker đã nhận hoặc consumer ngoài đã xử lý nếu adapter không cung cấp bảo đảm đó.

Outbox relay chỉ nên đánh dấu record đã gửi theo semantics publisher confirm/return của transport. Các record PENDING/FAILED cần được giải quyết trước khi đóng đường cũ.

## 12. Gỡ compatibility adapter, upcaster và feature flag

Sau khi mọi producer/consumer đã chuyển và backlog cũ được xử lý, có thể loại bỏ thành phần tạm thời.

Trước khi xóa một thành phần, xác minh:

- Không còn traffic đi qua adapter.
- Không còn payload cũ trong live queue hoặc retry store.
- Không còn archive/replay window cần decoder cũ.
- Consumer mới không còn phụ thuộc alias hoặc default tạm thời.
- Feature flag đã ở trạng thái đích trên mọi instance.
- Dashboard không còn tham chiếu metric hoặc route tạm thời.
- Runbook đã cập nhật.

Không nhất thiết phải xóa mọi upcaster. Nếu event lịch sử được lưu lâu dài và có thể replay, decoder/upcaster cho version cũ có thể phải được giữ như một phần của compatibility policy. Khi đó, hãy kết thúc bridge vận hành nhưng giữ bộ đọc lịch sử trong phạm vi có owner và test fixture.

Feature flag cũ nên được xóa khỏi code và cấu hình sau khi trạng thái cuối đã ổn định. Một flag không còn được sử dụng vẫn gây nhầm lẫn và có thể bị bật nhầm trong incident.

## 13. Rollback window và điểm không thể quay lại

Kết thúc migration cần có kế hoạch rollback rõ ràng. Trước cutover, xác định:

- Phiên bản producer cũ còn có thể chạy hay không.
- Consumer cũ còn đọc được event mới hay không.
- Database schema và outbox có thay đổi không thể đảo ngược không.
- Event mới đã tạo side effect nào không thể bù không.
- Queue/topic cũ còn tồn tại trong bao lâu.
- Có thể chuyển producer về contract cũ mà không làm mất event không.

Trong rollback window, có thể giữ consumer tương thích hoặc bridge ở trạng thái sẵn sàng nhưng không nhận traffic thường xuyên. Khi rollback, không đơn giản bật lại producer cũ nếu consumer đã xóa decoder hoặc dữ liệu đã chuyển theo semantics mới.

Sau khi gỡ route cũ và xóa compatibility code, hệ thống có thể bước qua điểm không thể quay lại bằng một thao tác config. Từ thời điểm đó, sự cố nên được xử lý bằng forward fix hoặc migration tiến lên, không giả định có thể rollback toàn bộ.

Ghi rõ ai có quyền quyết định rollback, điều kiện kích hoạt và cách đối chiếu event đã phát trong khoảng cutover. Không giữ hai đường chạy đồng thời vô thời hạn chỉ vì chưa thống nhất quyết định kết thúc rollback window.

## 14. Xóa tài nguyên cũ có kiểm soát

Sau khi xác nhận không còn traffic, có thể dọn:

- Exchange, queue, topic hoặc binding cũ.
- Consumer group/subscription cũ.
- Credential và permission chỉ dành cho route cũ.
- Config key, environment variable và secret reference cũ.
- Feature flag và adapter tạm thời.
- Dashboard, alert và runbook đã lỗi thời.
- Index hoặc bảng staging chỉ dùng trong migration, nếu không còn retention/audit requirement.

Thứ tự dọn nên bắt đầu từ producer route, sau đó consumer và cuối cùng tài nguyên broker/schema. Giữ lại quan sát trong một khoảng thời gian sau khi traffic đã về 0 để phát hiện client bị bỏ sót.

Không xóa dữ liệu audit, event archive, processed-event record hoặc schema cũ chỉ vì migration hoàn tất. Chúng có thể cần cho compliance, điều tra, replay hoặc đối chiếu. Mỗi loại dữ liệu cần retention policy riêng.

## 15. Quan sát sau cutover

Sau khi tắt đường cũ, tiếp tục quan sát trong khoảng ổn định đã định.

Các metric nên theo dõi:

- Event publish theo producer, event type và schema version.
- Consumer success/failure và processing latency.
- Retry, redelivery, duplicate và DLQ.
- Outbox PENDING/FAILED và tuổi record lâu nhất.
- Publication chưa hoàn tất theo listener nội bộ.
- Queue depth, unacked count hoặc consumer lag.
- Số event bị từ chối do unsupported version.
- Chênh lệch reconciliation và side effect trùng.
- Traffic còn sót trên route cũ.

Metric theo event type/version/route nên có tập giá trị kiểm soát. Không dùng eventId hoặc correlationId làm label có cardinality cao; giữ các ID đó trong log và trace để điều tra.

Đặt cảnh báo cho bất kỳ traffic mới nào xuất hiện trên route cũ sau khi cutover. Một message cũ phát sinh sau nhiều ngày có thể cho thấy một batch job, instance cũ hoặc integration bên ngoài chưa được cập nhật.

## 16. Kiểm thử trước và sau khi kết thúc chuyển tiếp

Bộ kiểm thử nên chứng minh cả điều kiện cutover và hành vi khi đường cũ bị tắt.

| Kịch bản | Điều cần xác minh |
|---|---|
| Producer mới phát event | Payload và schema version đúng contract đích |
| Producer cũ đã dừng | Không phát sinh event mới trên route cũ |
| Consumer mới đọc backlog cũ | Decode/upcast hoặc quarantine theo policy |
| Queue cũ được drain | Không còn ready, unacked hoặc delayed message cần xử lý |
| DLQ cũ | Mọi message được xử lý, archive hoặc có quyết định rõ |
| Dual publish bị tắt | Không còn hai side effect cho một logical event |
| Event bị redeliver | Idempotency ngăn xử lý trùng |
| Publication nội bộ chưa hoàn tất | Được phục hồi hoặc xử lý theo API registry |
| Compatibility bridge bị tắt | Luồng đích vẫn hoạt động độc lập |
| Rollback trong window | Producer/consumer tương thích với trạng thái rollback |
| Replay sau migration | Version cũ được đọc theo retention policy |
| Tài nguyên cũ bị gỡ | Không có client hợp lệ bị ảnh hưởng |

Integration test với broker cần xác minh routing, publisher confirms, acknowledgement và redelivery. Scenario test của Spring Modulith xác minh application event nội bộ; nó không thay thế kiểm thử transport bên ngoài.

## 17. Runbook kết thúc giai đoạn chuyển tiếp

Một runbook có thể đi theo trình tự sau:

1. Xác nhận inventory producer/consumer và owner đã đầy đủ.
2. Kiểm tra tiêu chí cutover và bằng chứng từ dashboard.
3. Deploy consumer đích và xác minh khả năng đọc payload cần hỗ trợ.
4. Chuyển producer cuối cùng sang contract đích.
5. Tắt dual publish và xác minh route cũ không còn traffic mới.
6. Drain queue, retry, delayed message, outbox và publication cũ.
7. Phân loại và xử lý DLQ; không xóa message chưa rõ side effect.
8. Đối chiếu số lượng và trạng thái nghiệp vụ giữa đường cũ/mới.
9. Theo dõi rollback window và quyết định đóng nó.
10. Tắt consumer/bridge cũ và gỡ topology cũ.
11. Xóa feature flag/config/permission không còn dùng.
12. Cập nhật schema catalog, tài liệu, dashboard và runbook.
13. Lưu bằng chứng hoàn tất, quyết định retention và owner chịu trách nhiệm.

Mỗi bước cần ghi thời điểm, người thực hiện, kết quả và cách rollback hoặc phục hồi. Với thao tác có thể ảnh hưởng dữ liệu hoặc xóa tài nguyên, yêu cầu xác nhận theo quy trình thay đổi của hệ thống.

## 18. Lỗi thường gặp khi kết thúc migration

**Tắt producer cũ trước khi consumer mới sẵn sàng.** Backlog có thể không được xử lý. Triển khai consumer tương thích và xác minh trước.

**Xóa queue khi depth bằng 0.** Có thể còn unacked, delayed hoặc retry message. Kiểm tra đầy đủ trạng thái broker và nguồn retry.

**Quên batch job hoặc producer ít chạy.** Traffic cũ có thể xuất hiện trở lại. Quan sát lâu hơn chu kỳ chạy của producer.

**Giữ dual publish quá lâu.** Tăng chi phí và nguy cơ duplicate side effect. Đặt tiêu chí và thời điểm tắt ngay từ đầu.

**Dùng message count làm bằng chứng duy nhất.** Hai đường có thể xử lý khác tập event. Đối chiếu theo event ID, aggregate và invariant nghiệp vụ.

**Xóa decoder cũ khi còn event archive cần replay.** Dữ liệu lịch sử không đọc được. Giữ upcaster hoặc định nghĩa migration archive riêng.

**Xóa publication chưa hoàn tất bằng SQL.** Có thể che giấu listener thất bại. Xử lý qua API và quy trình phục hồi được hỗ trợ.

**Rollback sau khi đã gỡ compatibility.** Producer cũ có thể không còn tương thích. Xác định rollback window và điểm không thể quay lại trước khi cutover.

**Không cập nhật quyền và tài liệu.** Credential, dashboard và runbook cũ tiếp tục gây nhầm lẫn. Dọn chúng sau khi traffic đã chuyển hoàn toàn.

## 19. Checklist xác nhận migration đã kết thúc

Chỉ đánh dấu hoàn tất khi có bằng chứng cho từng mục:

- [ ] Inventory producer, consumer, bridge và broker resource đã được owner xác nhận.
- [ ] Producer đang hoạt động chỉ phát contract đích.
- [ ] Consumer bắt buộc đã xử lý thành công contract đích.
- [ ] Dual publish và compatibility route không còn traffic.
- [ ] Backlog, unacked, retry và delayed message cũ đã được giải quyết.
- [ ] DLQ và publication chưa hoàn tất đã có quyết định xử lý.
- [ ] Reconciliation không còn sai lệch chưa giải thích.
- [ ] Idempotency bảo vệ side effect trong retry/replay.
- [ ] Rollback window đã đóng theo quyết định được ghi nhận.
- [ ] Adapter, feature flag và topology cũ đã được gỡ theo kế hoạch.
- [ ] Schema/decoder lịch sử còn lại có owner và retention policy.
- [ ] Dashboard, alert, runbook và tài liệu đã cập nhật.
- [ ] Metric sau cutover không cho thấy traffic hoặc lỗi bất thường trên đường cũ.

Kết thúc giai đoạn chuyển tiếp là việc xác nhận hệ thống đã vận hành ổn định trên hợp đồng đích và không còn phụ thuộc vào đường cũ trong luồng live. Với Spring Modulith, cần xác minh riêng publication nội bộ, listener và registry; với broker, cần xác minh routing, backlog, acknowledgement và consumer. Khi cutover, reconciliation, retention, rollback và cleanup đều có bằng chứng, migration mới thực sự hoàn tất và đội vận hành có thể duy trì một topology đơn giản, rõ trách nhiệm.
