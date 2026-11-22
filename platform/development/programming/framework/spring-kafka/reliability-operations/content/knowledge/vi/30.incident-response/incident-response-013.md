# Postmortem và hành động phòng ngừa cho hệ thống Spring Kafka

Postmortem là tài liệu phân tích một sự cố sau khi dịch vụ đã được khôi phục. Mục tiêu là tái dựng điều gì đã xảy ra, xác định vì sao hệ thống cho phép sự cố phát sinh hoặc kéo dài, đánh giá ảnh hưởng và chuyển bài học thành các hành động có người phụ trách, thời hạn và cách xác nhận rõ ràng.

Trong hệ thống Spring Kafka, một sự cố hiếm khi chỉ nằm ở một dòng code. Luồng xử lý có thể đi qua producer, broker, consumer group, listener container, cơ sở dữ liệu và dịch vụ downstream. Postmortem tốt phải mô tả được các mối liên hệ này bằng bằng chứng, thay vì chỉ ghi lại exception cuối cùng xuất hiện trong log.

## 1. Khi nào cần lập postmortem?

Nên tổ chức postmortem khi sự cố gây ảnh hưởng đáng kể tới người dùng hoặc nghiệp vụ, làm gián đoạn luồng sự kiện, gây mất hoặc xử lý trùng dữ liệu, làm backlog tăng kéo dài, ảnh hưởng nhiều service, hoặc buộc đội vận hành phải can thiệp thủ công.

Không cần đợi tới khi có kết luận nguyên nhân cuối cùng mới bắt đầu viết. Có thể mở tài liệu với trạng thái “đang điều tra”, ghi lại các sự kiện đã xác minh và cập nhật khi có thêm bằng chứng. Nếu sự cố nhỏ nhưng lặp lại nhiều lần, nên tổng hợp các lần xảy ra để tìm mẫu chung.

Một postmortem thường được lập sau khi:

- Dịch vụ đã trở lại trạng thái vận hành chấp nhận được.
- Ảnh hưởng tới người dùng và dữ liệu đã được đánh giá sơ bộ.
- Các log, metric, trace và thông tin triển khai liên quan vẫn còn truy xuất được.
- Người tham gia xử lý sự cố có thể cùng đối chiếu timeline.

Việc viết postmortem không thay thế báo cáo trạng thái trong lúc incident đang diễn ra. Trong incident, ưu tiên khôi phục dịch vụ, giới hạn ảnh hưởng và giao tiếp với các bên liên quan. Phân tích sâu nguyên nhân có thể tiếp tục sau đó.

## 2. Nguyên tắc postmortem không đổ lỗi

Một postmortem hữu ích tập trung vào điều kiện hệ thống, quyết định kỹ thuật, tín hiệu quan sát và rào chắn đã có tại thời điểm xảy ra sự cố. Không quy kết sự cố cho một cá nhân chỉ vì người đó thực hiện thao tác cuối cùng trước khi hệ thống lỗi.

Ví dụ:

- Cách viết thiếu thông tin: “Kỹ sư cấu hình sai consumer.”
- Cách viết có ích hơn: “Cấu hình triển khai cho consumer group sử dụng max.poll.interval.ms thấp hơn thời gian xử lý batch trong giờ cao điểm. Hệ thống không cảnh báo khi thời gian xử lý tiến gần giới hạn và rollout chưa có kiểm tra tải đại diện.”

Cách thứ hai mô tả điều kiện có thể kiểm chứng và mở ra nhiều hướng cải thiện: kiểm tra cấu hình, đo thời gian xử lý, cảnh báo sớm và kiểm thử tải.

Không đổ lỗi không có nghĩa là bỏ qua trách nhiệm. Mỗi hành động sau postmortem vẫn cần một người chịu trách nhiệm thực hiện, một hạn hoàn thành và tiêu chí xác nhận. Trách nhiệm ở đây là cải thiện hệ thống và hoàn tất công việc đã cam kết.

Nên phân biệt rõ:

- **Sự kiện đã xác minh:** có log, metric, trace, lịch sử triển khai hoặc bằng chứng khác hỗ trợ.
- **Giả thuyết:** cách giải thích đang được xem xét nhưng chưa đủ bằng chứng.
- **Kết luận:** giải thích phù hợp nhất với bằng chứng hiện có; ghi rõ giới hạn nếu vẫn còn điểm chưa chắc chắn.

Không sửa lại timeline để khiến quyết định trong quá khứ có vẻ hiển nhiên. Hãy đánh giá quyết định dựa trên thông tin mà người trực vận hành thực sự có ở thời điểm đó.

## 3. Thu thập bằng chứng trong incident

Postmortem phụ thuộc vào chất lượng bằng chứng. Với Spring Kafka, cần quan sát cả hai phía của broker và ứng dụng.

### 3.1. Bằng chứng từ ứng dụng Spring

Thu thập log của producer, listener container và các thành phần downstream trong khoảng thời gian trước, trong và sau incident. Những thông tin thường hữu ích gồm:

- Tên service, phiên bản ứng dụng, môi trường và instance/pod bị ảnh hưởng.
- Topic, partition, consumer group và client ID liên quan.
- Thời điểm bắt đầu/kết thúc xử lý từng batch hoặc message, nếu có instrumentation.
- Exception đầy đủ, nguyên nhân lồng bên trong, số lần retry và trạng thái đưa message vào dead-letter topic (DLT).
- Log về partition assignment, revoke, lost partition và rebalance.
- Thời gian xử lý database hoặc HTTP call downstream.
- Lịch sử deploy, thay đổi cấu hình, restart, scale và thao tác vận hành.

Log nên có correlation ID hoặc event ID để nối một sự kiện từ producer qua consumer và tới dịch vụ downstream. Không ghi payload nhạy cảm, token, mật khẩu, thông tin định danh cá nhân hoặc dữ liệu bí mật vào postmortem. Nếu cần đối chiếu payload, sử dụng ID đã được kiểm soát hoặc bản dữ liệu đã che thông tin.

### 3.2. Bằng chứng từ Kafka

Kiểm tra trạng thái topic, partition, consumer group và broker:

```bash
# Xem partition, leader, replica và ISR của topic
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --topic orders

# Xem offset, log-end offset và lag của consumer group
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-service
```

Khi đọc kết quả consumer group, lưu ý:

- CURRENT-OFFSET là offset đã commit của group.
- LOG-END-OFFSET là vị trí cuối hiện có mà công cụ báo cho partition.
- LAG là độ chênh được công cụ tính giữa log end và committed offset.

Lag không tự động bằng số message mà người dùng đang chờ. Một số message có thể đã được xử lý nhưng chưa commit offset; ngược lại, consumer có thể commit trước khi công việc nghiệp vụ hoàn tất nếu ứng dụng thiết kế sai thứ tự. Vì vậy, phải đối chiếu lag với thời gian xử lý, trạng thái nghiệp vụ và cách commit offset.

Từ hệ thống giám sát broker, thu thập các tín hiệu phù hợp với kiến trúc đang dùng: partition offline, partition under-replicated, ISR shrink, request latency, request queue, network/thread utilization, disk usage và trạng thái controller. Tên metric có thể khác nhau giữa JMX exporter và nền tảng giám sát.

### 3.3. Bằng chứng từ hạ tầng và dịch vụ phụ thuộc

Kiểm tra cùng mốc thời gian trên:

- Kubernetes events, pod restart, OOMKilled, CPU throttling, readiness/liveness transition và lịch sử scale.
- DNS, network, TLS/SASL, firewall và thay đổi certificate.
- Database connection pool, lock wait, query latency, deadlock và giới hạn kết nối.
- API downstream: latency, timeout, rate limit và tỷ lệ lỗi.
- Thay đổi secret, ACL, quota, broker config hoặc cấu hình topic.
- Hệ thống deploy/configuration management và lịch sử thay đổi thủ công.

Cố gắng đồng bộ thời gian giữa các hệ thống, ưu tiên UTC trong tài liệu và ghi rõ nguồn timestamp. Nếu đồng hồ của một thành phần lệch, hãy nêu độ lệch ước tính thay vì ghép các sự kiện theo thứ tự không chắc chắn.

## 4. Dựng timeline có thể kiểm chứng

Timeline nên ghi các sự kiện quan trọng từ trước khi phát sinh lỗi cho tới khi xác nhận khôi phục. Không chỉ ghi lúc alert được gửi và lúc incident đóng.

| Thời gian (UTC) | Sự kiện | Bằng chứng | Ý nghĩa |
|---|---|---|---|
| 09:00 | Bắt đầu rollout consumer phiên bản mới | Deployment history | Thay đổi gần thời điểm incident |
| 09:04 | Thời gian xử lý batch tăng | Application metrics | Consumer xử lý chậm hơn |
| 09:07 | Lag của group tăng liên tục | Consumer group metrics | Tốc độ xử lý thấp hơn tốc độ ghi |
| 09:10 | Alert backlog vượt ngưỡng | Alert history | Hệ thống phát hiện sự suy giảm |
| 09:14 | Tạm dừng rollout | Incident log | Giới hạn phạm vi thay đổi |
| 09:22 | Rollback hoàn tất | Deployment history | Khôi phục phiên bản trước |
| 09:31 | Lag bắt đầu giảm | Consumer group metrics | Khả năng xử lý đã phục hồi |
| 09:45 | Đối soát nghiệp vụ hoàn tất | Reconciliation report | Xác nhận dữ liệu được xử lý |

Các thời gian trong bảng chỉ minh họa cách trình bày; khi viết postmortem thực tế phải thay bằng timestamp đã xác minh.

Timeline nên thể hiện riêng các mốc:

1. Sự kiện kỹ thuật đầu tiên làm hệ thống suy giảm.
2. Thời điểm người dùng hoặc nghiệp vụ bắt đầu chịu ảnh hưởng.
3. Thời điểm hệ thống phát hiện và người trực tiếp nhận cảnh báo.
4. Các quyết định containment như dừng rollout, giảm tải, tắt consumer hoặc chuyển traffic.
5. Các bước khôi phục và thời điểm dịch vụ trở lại bình thường.
6. Thời điểm hoàn tất đối soát dữ liệu và xác nhận không còn backlog bất thường.

Nếu chưa xác định được thời điểm bắt đầu ảnh hưởng, hãy ghi “chưa xác định” và nêu khoảng thời gian có thể xảy ra. Không tự suy ra một timestamp chính xác từ dữ liệu thiếu.

## 5. Định lượng ảnh hưởng

Phần impact phải trả lời sự cố đã ảnh hưởng tới ai, chức năng nào, trong bao lâu và ở quy mô nào. Không chỉ ghi “Kafka bị chậm”.

Với luồng event, có thể đo:

- Số message được publish trong khoảng thời gian incident.
- Số message bị chậm, bị retry, được chuyển vào DLT hoặc cần xử lý lại.
- Consumer lag lớn nhất, thời gian lag vượt ngưỡng và thời gian cần để drain backlog.
- Số partition hoặc consumer instance bị ảnh hưởng.
- Tỷ lệ xử lý thành công, lỗi và trùng lặp.
- Số giao dịch nghiệp vụ chậm, thất bại hoặc cần đối soát thủ công.
- Thời gian từ khi sự kiện được tạo tới khi nghiệp vụ hoàn tất (event-to-process latency).

Phân biệt rõ các khái niệm:

- **Message delay:** message được xử lý muộn hơn SLA.
- **Message loss:** message được xác nhận là không còn trong luồng xử lý và không thể phục hồi theo quy trình hiện có.
- **Duplicate processing:** một message được xử lý nghiệp vụ nhiều lần.
- **Data inconsistency:** trạng thái giữa các hệ thống không khớp, kể cả khi message vẫn còn.
- **Backlog:** công việc đang chờ xử lý; backlog không đồng nghĩa với mất dữ liệu.

Nếu chưa chứng minh được có mất message, không ghi “mất dữ liệu”. Có thể ghi “chưa phát hiện mất message; đang đối soát các ID trong khoảng thời gian X”. Sau khi đối soát, cập nhật kết quả và nguồn bằng chứng.

Cần ghi cả ảnh hưởng bên ngoài và nội bộ. Ví dụ, API vẫn trả HTTP 200 nhưng sự kiện đơn hàng được xử lý trễ 20 phút thì người dùng vẫn chịu ảnh hưởng nghiệp vụ.

## 6. Phân tích nguyên nhân và yếu tố góp phần

Không dừng lại ở exception cuối cùng. Hãy lần theo chuỗi điều kiện đã khiến lỗi xuất hiện, không được phát hiện sớm hoặc khó khôi phục.

Có thể chia thành bốn lớp:

- **Trigger:** sự kiện trực tiếp khởi phát, ví dụ deploy phiên bản mới, downstream chậm hoặc broker mất một broker.
- **Root cause / nguyên nhân gốc:** điều kiện kỹ thuật hoặc thiết kế khiến trigger dẫn tới sự cố, ví dụ consumer xử lý đồng bộ lâu hơn giới hạn poll và không có cơ chế cô lập dependency chậm.
- **Contributing factors / yếu tố góp phần:** những yếu tố làm sự cố nghiêm trọng hoặc kéo dài, ví dụ retry không giới hạn, batch lớn, thiếu capacity hoặc alert không đo thời gian xử lý.
- **Detection and recovery gaps / thiếu sót phát hiện và khôi phục:** tín hiệu không có, runbook không rõ, rollback khó hoặc không có đối soát sau khôi phục.

Không ép mọi incident phải có duy nhất một “root cause”. Trong hệ thống phân tán, kết quả thường đến từ nhiều điều kiện tương tác. Ghi một mô hình nguyên nhân có thể kiểm chứng sẽ hữu ích hơn một câu kết luận quá đơn giản.

### 6.1. Dùng kỹ thuật 5 Whys có kiểm soát

Ví dụ một chuỗi câu hỏi:

1. Vì sao đơn hàng được xử lý trễ? Consumer group có lag lớn.
2. Vì sao consumer group không theo kịp tốc độ ghi? Mỗi batch xử lý lâu hơn thời gian bình thường.
3. Vì sao batch xử lý lâu? Listener gọi database đồng bộ và một số truy vấn bị chậm.
4. Vì sao truy vấn chậm làm toàn bộ consumer chậm? Pool kết nối bị cạn, retry giữ luồng xử lý lâu và không có giới hạn thời gian phù hợp.
5. Vì sao sự suy giảm không được phát hiện trước khi ảnh hưởng lớn? Dashboard chỉ theo dõi broker, chưa cảnh báo event processing latency và thời gian xử lý batch.

Chuỗi này là một ví dụ minh họa, không phải kết luận cho mọi incident. Mỗi câu trả lời cần bằng chứng. Nếu một bước chưa được xác minh, ghi nó là giả thuyết và chỉ rõ dữ liệu cần thu thập.

5 Whys không nên trở thành bài tập tìm một cá nhân để hỏi “tại sao”. Dùng nó để tìm điều kiện kỹ thuật, quy trình và rào chắn còn thiếu. Có thể kết hợp timeline, sơ đồ nhân quả, log và thử nghiệm tái hiện để kiểm chứng giả thuyết.

### 6.2. Những nhóm nguyên nhân thường gặp trong Spring Kafka

| Nhóm | Dấu hiệu có thể quan sát | Hướng điều tra |
|---|---|---|
| Consumer xử lý chậm | Lag tăng, thời gian xử lý message/batch tăng | Database, API downstream, batch size, CPU và blocking call |
| Rebalance lặp lại | Log revoke/assign liên tục, consumer không ổn định | Poll interval, heartbeat, session timeout, GC pause và thời gian xử lý |
| Poison message | Cùng một record lỗi lặp lại, partition tiến chậm | Deserialization, validation, retry policy và DLT |
| Broker/partition suy giảm | Request latency, offline hoặc under-replicated partition | Broker health, disk, network, ISR và leader |
| Producer không publish được | Send error, timeout hoặc retry tăng | Broker availability, metadata, ACL, quota và cấu hình producer |
| Commit/processing sai thứ tự | Trùng hoặc thiếu tác động nghiệp vụ sau restart | Ack mode, offset commit, transaction và idempotency |
| Cấu hình sai giữa môi trường | Một môi trường lỗi sau deploy, môi trường khác bình thường | Config drift, secret, topic name, ACL và bootstrap servers |
| Downstream không sẵn sàng | Listener chờ lâu, connection pool cạn | Timeout, circuit breaker, bulkhead và capacity downstream |

## 7. Ví dụ postmortem: consumer lag tăng do database chậm

Phần này minh họa cách nối triệu chứng, bằng chứng, nguyên nhân và hành động. Các con số và mốc thời gian đều là dữ liệu giả định để trình bày cách viết.

### Tóm tắt sự cố

Consumer group order-service xử lý topic orders chậm trong giờ cao điểm. Lag tăng liên tục, khiến một số đơn hàng được cập nhật trạng thái trễ. Broker vẫn hoạt động; producer tiếp tục publish message. Đội vận hành giảm tải truy vấn, rollback thay đổi gây tăng thời gian xử lý và theo dõi tới khi backlog được drain.

### Ảnh hưởng

- Một phần đơn hàng được cập nhật trạng thái muộn hơn SLA 5 phút.
- Lag cao nhất đạt 120.000 record trên các partition bị ảnh hưởng.
- Không có bằng chứng message bị mất; các ID đơn hàng trong khoảng thời gian incident đã được đối soát sau khi backlog giảm.
- API tiếp nhận đơn hàng vẫn hoạt động, nhưng tiến trình cập nhật trạng thái bất đồng bộ bị trễ.

### Timeline minh họa

| Thời gian (UTC) | Sự kiện |
|---|---|
| 09:00 | Rollout phiên bản listener có thay đổi truy vấn database |
| 09:05 | P95 thời gian xử lý batch tăng |
| 09:08 | Lag bắt đầu tăng trên phần lớn partition |
| 09:12 | Alert lag kích hoạt; on-call bắt đầu điều tra |
| 09:18 | Xác nhận database connection pool gần cạn |
| 09:23 | Dừng rollout và thực hiện rollback |
| 09:30 | Thời gian xử lý batch giảm |
| 09:42 | Lag giảm ổn định |
| 10:05 | Backlog trở về ngưỡng bình thường |
| 10:20 | Đối soát nghiệp vụ hoàn tất |

### Phân tích

**Trigger:** phiên bản mới làm tăng số truy vấn và thời gian xử lý mỗi batch.

**Nguyên nhân gốc:** listener thực hiện cập nhật database đồng bộ cho từng record, nhưng truy vấn mới không có index phù hợp. Thời gian xử lý tăng làm tốc độ tiêu thụ thấp hơn tốc độ producer ghi.

**Yếu tố góp phần:**

- Alert chỉ dựa trên lag tuyệt đối, không kết hợp tốc độ tăng lag và event processing latency.
- Load test không dùng phân bố dữ liệu và mức cạnh tranh database gần với giờ cao điểm.
- Retry database làm thời gian giữ batch tăng thêm khi pool đã cạn.
- Dashboard không hiển thị tương quan giữa Kafka lag và database pool saturation.

**Vì sao khôi phục được:** rollback loại bỏ truy vấn mới; sau đó database pool ổn định và consumer xử lý backlog nhanh hơn tốc độ ghi.

### Hành động sau sự cố

| Hành động | Loại | Owner minh họa | Tiêu chí hoàn thành |
|---|---|---|---|
| Thêm index và xác nhận execution plan cho truy vấn cập nhật | Phòng ngừa | Database team | Query latency đạt mục tiêu ở tải đại diện |
| Thêm metric thời gian xử lý message và batch | Phát hiện | Service team | Dashboard hiển thị p50/p95/p99 |
| Cảnh báo khi lag tăng cùng event processing latency | Phát hiện | Platform team | Alert được kiểm tra bằng thử nghiệm tải |
| Giới hạn thời gian retry và xử lý lỗi downstream có kiểm soát | Giảm thiểu | Service team | Kiểm thử timeout, retry và phục hồi |
| Bổ sung load test có database contention | Phòng ngừa | QA/Service team | Pipeline kiểm tra tải trước release |
| Viết runbook xử lý backlog và đối soát event ID | Khôi phục | On-call team | Diễn tập thành công trong môi trường staging |

Ví dụ này cho thấy chỉ tăng số consumer có thể không giải quyết được vấn đề nếu database là nút thắt. Scale consumer khi downstream đã cạn connection có thể làm áp lực tăng thêm. Hành động phòng ngừa phải xử lý điều kiện gây nghẽn và cung cấp tín hiệu phát hiện trước khi ảnh hưởng lan rộng.

## 8. Chuyển kết luận thành hành động phòng ngừa

Một postmortem chỉ có giá trị vận hành khi các phát hiện được chuyển thành thay đổi cụ thể. Mỗi action item nên trả lời:

- Vấn đề hoặc rủi ro nào được xử lý?
- Thay đổi cụ thể là gì?
- Ai chịu trách nhiệm chính?
- Khi nào cần hoàn thành?
- Bằng chứng nào xác nhận hành động có hiệu quả?
- Hành động phụ thuộc vào nhóm hoặc hệ thống nào?

Tránh các đầu việc quá chung chung như “cải thiện monitoring”, “tối ưu Kafka”, “tăng độ ổn định” hoặc “cẩn thận hơn khi deploy”. Hãy chuyển chúng thành việc có thể kiểm chứng, ví dụ: “Tạo alert khi p95 event processing latency vượt 30 giây trong 10 phút và kiểm thử alert bằng cách mô phỏng database latency ở staging.”

### 8.1. Phân loại hành động

| Loại hành động | Mục đích | Ví dụ |
|---|---|---|
| Containment | Giới hạn ảnh hưởng ngay khi incident xảy ra | Tạm dừng rollout, giảm producer rate, cô lập partition hoặc dependency lỗi |
| Prevention | Loại bỏ hoặc giảm xác suất nguyên nhân | Sửa truy vấn, kiểm tra cấu hình, giới hạn retry, load test |
| Detection | Phát hiện sớm hơn | Alert lag tăng nhanh, processing latency, rebalance hoặc DLT tăng |
| Recovery | Khôi phục an toàn và có thể lặp lại | Runbook replay DLT, drain backlog, đối soát dữ liệu |
| Resilience | Giữ hệ thống hoạt động khi dependency suy giảm | Timeout, circuit breaker, bulkhead, idempotent handler |
| Learning | Cải thiện kiến thức và quy trình | Diễn tập incident, cập nhật runbook, chia sẻ bài học kỹ thuật |

Không phải incident nào cũng cần hành động ở tất cả nhóm. Ưu tiên các thay đổi trực tiếp xử lý nguyên nhân và lỗ hổng phát hiện/khôi phục đã được chứng minh.

### 8.2. Viết action item có thể đo lường

Một action item tốt có cấu trúc:

```text
Action:
  Mô tả thay đổi cụ thể

Reason:
  Phát hiện trong postmortem mà hành động này xử lý

Owner:
  Một người hoặc một vai trò chịu trách nhiệm

Due date:
  Ngày hoàn thành

Priority:
  P0 / P1 / P2 theo mức rủi ro và ảnh hưởng

Verification:
  Test, metric, alert hoặc bằng chứng vận hành xác nhận kết quả

Status:
  Open / In progress / Blocked / Done
```

Ví dụ:

```text
Action:
  Thêm alert cho consumer group khi p95 processing latency
  vượt 30 giây trong 10 phút liên tục.

Reason:
  Incident trước được phát hiện muộn vì dashboard chỉ hiển thị broker health.

Owner:
  Kafka Platform team

Due date:
  2026-12-05

Priority:
  P1

Verification:
  Mô phỏng listener xử lý chậm ở staging và xác nhận alert
  được gửi trong vòng 10 phút, có topic và group trong nội dung.

Status:
  Open
```

Ngày, ngưỡng và nhóm phụ trách trong ví dụ là giả định. Trong dự án thực tế, chọn ngưỡng theo SLA, baseline và khả năng vận hành; không sao chép máy móc con số ví dụ.

Mỗi action item cần một owner chính. Có thể có nhiều nhóm phối hợp, nhưng không nên để một đầu việc chỉ có tên một team chung chung mà không có người theo dõi. Nếu bị block, ghi rõ dependency và quyết định cần có để tiếp tục.

### 8.3. Ưu tiên theo rủi ro

Có thể phân loại đơn giản:

- **P0:** nguy cơ mất dữ liệu, xử lý sai nghiệp vụ hoặc tái diễn ngay; cần containment hoặc khắc phục khẩn cấp.
- **P1:** lỗ hổng có thể gây incident nghiêm trọng hoặc làm thời gian phát hiện/khôi phục quá dài.
- **P2:** cải thiện độ tin cậy, vận hành và khả năng quan sát có thể lên kế hoạch.

Không dùng mức ưu tiên để thay thế đánh giá rủi ro. Một việc nhỏ nhưng ngăn replay nhầm dữ liệu production có thể quan trọng hơn một thay đổi dashboard lớn.

## 9. Các hành động phòng ngừa thường có ích với Spring Kafka

### 9.1. Quản lý retry và poison message

Retry vô hạn có thể khiến một message lỗi giữ partition không tiến lên, hoặc khiến downstream bị quá tải do liên tục nhận lại request. Xác định rõ lỗi nào có thể retry, số lần retry, backoff, timeout và điểm chuyển sang DLT.

- Lỗi tạm thời như network timeout có thể retry với backoff và giới hạn.
- Lỗi dữ liệu hoặc schema không hợp lệ thường cần xử lý riêng, ghi nhận nguyên nhân và chuyển vào luồng cách ly theo chính sách.
- DLT cần có alert, owner và quy trình xử lý/replay.
- Replay phải giữ khả năng idempotent để không tạo tác động nghiệp vụ trùng.
- Theo dõi tuổi của message trong DLT, số lượng tăng mới và số lượng chưa được xử lý.

Không đưa mọi exception vào retry vô hạn. Một poison message có thể làm các message phía sau trong cùng partition bị trì hoãn.

### 9.2. Kiểm soát offset và tính idempotent

Consumer có thể xử lý message rồi crash trước khi commit offset. Khi khởi động lại, message có thể được giao lại. Đây là hành vi cần tính đến trong thiết kế at-least-once.

- Thiết kế handler idempotent bằng event ID hoặc khóa nghiệp vụ phù hợp.
- Xác định thứ tự giữa ghi database và commit offset.
- Tránh commit offset trước khi công việc nghiệp vụ bền vững nếu điều đó có thể làm mất tác động cần thực hiện.
- Dùng transaction hoặc outbox/inbox pattern khi cần đảm bảo nhất quán giữa database và việc publish event; hiểu rõ phạm vi bảo đảm của từng cách.
- Kiểm thử restart/crash tại các điểm khác nhau của luồng xử lý.

Kafka idempotent producer và transaction hỗ trợ các bảo đảm trong phạm vi Kafka, nhưng không tự động làm cho một side effect bên ngoài như cập nhật database hoặc gọi HTTP trở thành exactly-once. Postmortem về duplicate hoặc lost effect cần chỉ rõ ranh giới transaction.

### 9.3. Ngăn rebalance không cần thiết

Rebalance có thể làm giảm throughput nếu consumer liên tục mất và nhận lại partition. Kiểm tra:

- Thời gian xử lý một lần poll so với max.poll.interval.ms.
- Heartbeat, session timeout và khoảng dừng do GC.
- Kích thước batch và thời gian xử lý từng record.
- Số consumer so với số partition.
- Hành vi shutdown và deploy khi container đang xử lý batch.
- Log assignment/revocation để xác định rebalance do deploy, timeout hay lỗi thành viên.

Không tăng max.poll.interval.ms một cách tùy tiện. Cần đo thời gian xử lý thực tế và cân nhắc giới hạn batch, tách công việc dài khỏi thread poll hoặc điều chỉnh concurrency theo năng lực downstream.

### 9.4. Bảo vệ dependency downstream

Consumer thường gọi database, REST API hoặc hệ thống nội bộ. Dependency chậm có thể kéo giảm throughput và gây backlog.

- Đặt connect/read timeout hữu hạn.
- Dùng connection pool có giới hạn và theo dõi mức sử dụng.
- Cân nhắc circuit breaker hoặc bulkhead để giới hạn tác động dây chuyền.
- Retry có backoff, jitter và giới hạn; tránh retry đồng thời trên nhiều lớp.
- Kiểm tra khả năng chịu tải của database trước khi tăng concurrency.
- Có chính sách tạm dừng, giảm tốc hoặc buffer công việc khi downstream không sẵn sàng.

### 9.5. Kiểm soát producer và schema

Producer cũng có thể là nguồn sự cố:

- Theo dõi send error, retry, request latency và record queue time.
- Kiểm tra timeout, delivery timeout, idempotence và giới hạn buffer.
- Quản lý schema evolution tương thích với consumer đang chạy.
- Kiểm thử rollout theo thứ tự tương thích: consumer có thể đọc schema mới trước khi producer phát dữ liệu mới, theo chính sách schema của hệ thống.
- Không log payload nhạy cảm khi điều tra lỗi serialization.

### 9.6. Bảo vệ broker và topic

Hành động phòng ngừa ở tầng Kafka gồm:

- Theo dõi partition offline, under-replicated, ISR shrink và broker disk.
- Đặt replication factor và min.insync.replicas theo yêu cầu durability và số broker.
- Kiểm soát partition count để tránh metadata và file handle tăng ngoài dự kiến.
- Theo dõi quota, request latency, network và storage.
- Kiểm tra kế hoạch nâng cấp broker, rolling restart và tương thích client.
- Quản lý ACL, TLS/SASL và certificate rotation có kiểm thử.
- Provision topic có kiểm soát, version hóa cấu hình và xác nhận topic ở đúng cluster.

### 9.7. Nâng chất lượng triển khai

Mỗi thay đổi liên quan tới producer, consumer, topic hoặc broker nên có kế hoạch rollout và rollback.

- Đưa cấu hình Kafka vào quản lý version; kiểm tra khác biệt giữa môi trường.
- Kiểm tra compatibility của schema và cấu hình consumer trước release.
- Dùng canary hoặc rollout từng phần khi phù hợp.
- Theo dõi lag, processing latency, error rate và rebalance trong thời gian rollout.
- Định nghĩa điều kiện dừng rollout và cách rollback.
- Diễn tập rollback để biết thao tác có thực sự khôi phục được phiên bản và cấu hình trước đó.

## 10. Thiết kế monitoring để phát hiện trước khi người dùng bị ảnh hưởng

Không nên chỉ giám sát trạng thái broker. Broker có thể UP nhưng consumer xử lý quá chậm, DLT tăng hoặc sự kiện không hoàn tất nghiệp vụ.

Một bộ tín hiệu nên bao phủ nhiều lớp:

| Lớp | Tín hiệu | Câu hỏi vận hành |
|---|---|---|
| Producer | Send error, retry, request latency | Producer có gửi được event không? |
| Broker | Offline/under-replicated partitions, request latency, disk | Cluster có đủ khả năng phục vụ không? |
| Consumer | Lag, processing latency, poll interval, rebalance | Consumer có theo kịp và ổn định không? |
| Listener | Handler error, retry count, DLT rate | Message có được xử lý đúng không? |
| Dependency | DB/API latency, timeout, pool saturation | Nút thắt có nằm ngoài Kafka không? |
| Business | Event-to-process latency, số trạng thái chờ quá lâu | Người dùng có nhận được kết quả đúng hạn? |

Alert nên có ngữ cảnh đủ để hành động: cluster, environment, topic, consumer group, partition nếu liên quan, thời gian bắt đầu và dashboard/runbook liên kết.

Đừng cảnh báo chỉ dựa vào một ngưỡng lag cố định nếu throughput giữa các topic khác nhau. Có thể kết hợp:

- Lag tuyệt đối và tốc độ tăng lag.
- Tuổi của message cũ nhất chưa xử lý.
- Event processing latency so với SLA.
- Tỷ lệ lỗi/retry/DLT.
- Thời gian consumer không có tiến triển offset.
- Tín hiệu sức khỏe của dependency downstream.

Một alert tốt phải có hướng xử lý. Nếu không có hành động cụ thể khi alert kích hoạt, cần xem lại ngưỡng hoặc chuyển nó thành dashboard theo dõi.

## 11. Kiểm tra hành động sau postmortem

Đóng action item khi có bằng chứng thay đổi đã được triển khai và tiêu chí xác nhận đạt. Một PR được merge chưa chắc đã chứng minh rủi ro được giảm.

Ví dụ tiêu chí xác nhận:

- Alert: thử tạo điều kiện lỗi có kiểm soát và xác nhận alert đến đúng người trực với đủ ngữ cảnh.
- Retry: mô phỏng timeout, lỗi vĩnh viễn và phục hồi; xác nhận số lần retry, backoff và DLT đúng thiết kế.
- Idempotency: phát lại cùng event ID nhiều lần và xác nhận chỉ có một tác động nghiệp vụ.
- Recovery: diễn tập drain backlog hoặc replay DLT, xác nhận không bỏ sót và không xử lý trùng.
- Capacity: chạy tải đại diện và xác nhận processing latency, lag và dependency pool nằm trong ngưỡng.
- Runbook: người trực khác tác giả thực hiện theo tài liệu và hoàn tất mà không cần hướng dẫn miệng.

Sau khi hoàn thành, theo dõi một khoảng thời gian phù hợp với chu kỳ tải. Nếu chỉ kiểm thử ở staging mà chưa có tín hiệu production, ghi rõ giới hạn đó. Với hành động dài hạn, có thể chia thành các mốc nhỏ để giảm rủi ro và dễ theo dõi.

## 12. Mẫu tài liệu postmortem

Có thể dùng mẫu sau cho mỗi incident. Những mục không áp dụng nên ghi “Không áp dụng” kèm lý do; mục chưa biết nên ghi “Chưa xác định” cùng kế hoạch xác minh.

```markdown
# Postmortem: [Tên sự cố]

## Metadata
- Incident ID:
- Service / environment:
- Topic / consumer group / cluster:
- Severity:
- Incident commander:
- Authors / reviewers:
- Date:
- Status: Draft / Review / Final

## Executive summary
Mô tả ngắn điều gì xảy ra, ảnh hưởng chính và trạng thái hiện tại.

## Customer and business impact
- Người dùng/chức năng bị ảnh hưởng:
- Thời gian bắt đầu và kết thúc:
- Số lượng giao dịch/message bị ảnh hưởng:
- SLA/SLO bị vi phạm:
- Kết quả đối soát dữ liệu:

## Detection
- Alert hoặc tín hiệu đầu tiên:
- Thời gian phát hiện:
- Thời gian người trực phản hồi:
- Khoảng thời gian hệ thống chưa phát hiện được:

## Timeline (UTC)
| Time | Event | Evidence | Decision / impact |
|---|---|---|---|

## Technical details
- Producer:
- Broker / topic / partition:
- Consumer group / listener:
- Downstream dependencies:
- Deployment/configuration changes:
- Logs, metrics, traces, links:

## Root cause and contributing factors
- Trigger:
- Root cause:
- Contributing factors:
- Detection gaps:
- Recovery gaps:
- Confirmed facts:
- Open hypotheses:

## Resolution
- Containment:
- Recovery steps:
- Data reconciliation:
- Validation that service is healthy:

## What went well
-

## What made the incident harder
-

## Action items
| ID | Action | Type | Priority | Owner | Due date | Verification | Status |
|---|---|---|---|---|---|---|---|

## Follow-up
- Date to review outstanding actions:
- Evidence to collect:
- Runbook/dashboard/alert updates:
- Lessons to share:
```

Mẫu này có thể được điều chỉnh theo quy trình incident của tổ chức. Giữ tài liệu ngắn gọn ở phần tóm tắt nhưng đủ bằng chứng ở các phần kỹ thuật để người không tham gia incident vẫn hiểu được quyết định và kết luận.

## 13. Quy trình tổ chức buổi review

Một buổi review hiệu quả cần người điều phối, người nắm luồng ứng dụng, người hiểu Kafka/hạ tầng và người đại diện nghiệp vụ khi có ảnh hưởng tới khách hàng.

Gợi ý trình tự:

1. Thống nhất phạm vi incident và kết quả khôi phục.
2. Đọc timeline, xác nhận từng sự kiện và nguồn bằng chứng.
3. Định lượng ảnh hưởng, xác nhận trạng thái dữ liệu.
4. Phân tích trigger, nguyên nhân và yếu tố góp phần.
5. Xác định lỗ hổng phát hiện, containment và recovery.
6. Đề xuất action item, ưu tiên, owner, deadline và tiêu chí xác nhận.
7. Xác định tài liệu/runbook/dashboard cần cập nhật.
8. Chốt người theo dõi và ngày review các action còn mở.

Nếu có bất đồng về nguyên nhân, ghi lại giả thuyết và bằng chứng cần bổ sung. Không nên kéo dài buổi review để ép một kết luận chưa có dữ liệu. Có thể giao một action điều tra riêng, với thời hạn và người chịu trách nhiệm.

## 14. Theo dõi xu hướng qua nhiều postmortem

Một incident đơn lẻ cho thấy điểm yếu cụ thể; nhiều postmortem có thể cho thấy vấn đề hệ thống trong cách thiết kế hoặc vận hành.

Định kỳ tổng hợp:

- Số incident theo service, topic, consumer group và loại nguyên nhân.
- Tần suất incident tái diễn.
- Mean time to detect (MTTD) và mean time to recover (MTTR), với định nghĩa thống nhất.
- Tỷ lệ action item hoàn thành đúng hạn.
- Số action bị quá hạn hoặc bị block.
- Tỷ lệ incident có phát hiện qua monitoring trước khi khách hàng báo.
- Tỷ lệ incident cần replay, đối soát hoặc can thiệp thủ công.
- Xu hướng processing latency, lag và DLT trên các luồng quan trọng.

Không dùng các số liệu này để xếp hạng cá nhân. Dùng chúng để xác định service nào cần đầu tư vào observability, test tải, tự động hóa recovery hoặc cải thiện thiết kế.

Action item quá hạn nên được xem lại theo rủi ro. Nếu một hành động không còn phù hợp, ghi rõ lý do và quyết định thay thế; không chỉ đóng để làm đẹp tỷ lệ hoàn thành.

## 15. Tiêu chuẩn kết thúc postmortem

Một postmortem có thể chuyển sang trạng thái final khi:

- Phạm vi và ảnh hưởng đã được mô tả bằng dữ liệu có thể truy xuất.
- Timeline có nguồn bằng chứng và phân biệt rõ sự kiện với giả thuyết.
- Nguyên nhân và yếu tố góp phần giải thích được đường đi từ trigger tới impact.
- Các điểm chưa chắc chắn được ghi rõ.
- Hành động có owner, priority, due date và tiêu chí xác nhận.
- Runbook, dashboard, alert hoặc quy trình cần thiết đã có đầu việc cập nhật.
- Có lịch theo dõi action còn mở.

Không cần mọi action item phải hoàn thành trước khi postmortem được final. Cần có kế hoạch theo dõi riêng và cơ chế nhắc việc để bài học không dừng lại ở tài liệu.

Với Spring Kafka, postmortem tốt phải nối được trạng thái của producer, broker, partition, consumer group, listener và hệ thống downstream với tác động nghiệp vụ thực tế. Khi mỗi kết luận đều có bằng chứng và mỗi hành động đều có cách xác minh, sự cố trở thành đầu vào cụ thể để cải thiện độ tin cậy của hệ thống.
