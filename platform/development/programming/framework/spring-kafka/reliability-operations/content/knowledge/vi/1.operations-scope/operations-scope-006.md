# SLO, SLA và chỉ số vận hành

## 1. Vì sao cần đo mức độ tin cậy của Kafka?

Trong một hệ thống Spring Kafka, việc broker đang chạy chưa đủ để kết luận dịch vụ hoạt động tốt. Ứng dụng có thể gửi bản ghi thành công nhưng consumer xử lý chậm; consumer có thể đọc được dữ liệu nhưng lỗi khi ghi xuống cơ sở dữ liệu; hoặc cluster vẫn có broker hoạt động nhưng một số partition quan trọng không có leader.

Vì vậy, vận hành cần đo chất lượng của luồng sự kiện từ góc nhìn của ứng dụng và người dùng. Các mục tiêu SLO giúp đội ngũ thống nhất mức chất lượng cần duy trì. SLA biến một phần cam kết đó thành nghĩa vụ với khách hàng. Các chỉ số vận hành cung cấp dữ liệu để phát hiện, giải thích và xử lý vấn đề.

Một luồng sự kiện thường có các chặng:

1. Ứng dụng Spring gửi event qua Kafka producer.
2. Producer gửi record tới leader của partition.
3. Broker xác nhận record theo cấu hình acknowledgement và replication.
4. Consumer nhận record, thực thi logic nghiệp vụ và ghi kết quả xuống hệ thống đích.
5. Consumer commit offset sau khi xử lý theo đúng semantics của ứng dụng.

Mỗi chặng có thể gặp lỗi riêng. Ví dụ, producer nhận được acknowledgement chỉ cho biết Kafka đã xác nhận record theo cấu hình hiện tại; điều đó không tự chứng minh rằng consumer đã xử lý xong nghiệp vụ. Khi thiết kế SLI và SLO, cần xác định rõ đang đo chặng nào và cam kết điều gì.

## 2. Phân biệt metric, SLI, SLO, SLA và error budget

Các khái niệm này liên quan với nhau nhưng có vai trò khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ trong Spring Kafka |
|---|---|---|
| Metric | Giá trị đo được theo thời gian hoặc theo sự kiện | Consumer lag, producer request latency, số record lỗi |
| SLI (Service Level Indicator) | Chỉ số đại diện cho chất lượng dịch vụ mà người dùng nhận được | Tỷ lệ event được xử lý thành công trong vòng 60 giây |
| SLO (Service Level Objective) | Mục tiêu định lượng cho một SLI trong một khoảng thời gian | 99% event được xử lý trong vòng 60 giây trong cửa sổ 7 ngày |
| SLA (Service Level Agreement) | Cam kết chất lượng có tính thỏa thuận với khách hàng, thường kèm cách đo, ngoại lệ và biện pháp khắc phục | Cam kết availability hàng tháng và service credit nếu không đạt |
| Error budget | Mức lỗi hoặc gián đoạn được phép theo SLO | Với SLO 99,9%, ngân sách lỗi là 0,1% trong cửa sổ đo |

Một metric kỹ thuật không tự động là SLI. Chẳng hạn, CPU của broker là metric hữu ích để chẩn đoán tải, nhưng người dùng không trực tiếp cảm nhận CPU. Tỷ lệ yêu cầu publish thành công hoặc thời gian event đến được hệ thống đích thường phản ánh trải nghiệm rõ hơn.

KPI kinh doanh cũng khác SLI. Số đơn hàng mỗi ngày có thể là KPI; tỷ lệ event đơn hàng được xử lý đúng hạn có thể là SLI cho nền tảng sự kiện hỗ trợ KPI đó.

### Quan hệ giữa các khái niệm

- Metric là dữ liệu đầu vào.
- SLI biến dữ liệu thành phép đo chất lượng có định nghĩa rõ ràng.
- SLO đặt mục tiêu cho SLI và tạo cơ sở quản lý error budget.
- SLA chọn một số cam kết để thỏa thuận với khách hàng.
- Dashboard, cảnh báo và quy trình ứng phó dùng SLI cùng metric hỗ trợ để điều hành dịch vụ.

SLO nội bộ thường cần đủ chặt để đội ngũ có thời gian xử lý trước khi vi phạm SLA. Mức chênh lệch cụ thể tùy dịch vụ và thỏa thuận; không có một tỷ lệ chung áp dụng cho mọi hệ thống.

## 3. Chọn SLI phù hợp với Kafka

Bắt đầu từ hành trình quan trọng của ứng dụng: event nào cần được gửi, event cần tới đâu, trong bao lâu, và thế nào được tính là xử lý thành công. Sau đó mới chọn metric kỹ thuật để giải thích kết quả.

### 3.1. Producer availability và publish success

Một SLI phổ biến là tỷ lệ thao tác publish hợp lệ được Kafka xác nhận thành công:

[
SLI_{publish} =
rac{	ext{số thao tác publish tốt}}
{	ext{tổng số thao tác publish hợp lệ}}
	imes 100%
]

Cần định nghĩa “thao tác publish tốt”. Một định nghĩa có thể là record được xác nhận thành công và có latency không vượt quá ngưỡng đã chọn. Mẫu số cần tính cả các thao tác hợp lệ thất bại do timeout, lỗi broker hoặc lỗi mạng; nếu chỉ đếm các request thành công thì SLI sẽ luôn đẹp một cách giả tạo.

Với producer có retry, cần phân biệt một thao tác nghiệp vụ logic với các lần gửi lại ở tầng client. Nếu đếm mỗi lần retry như một thao tác độc lập, mẫu số có thể bị phóng đại. Hãy chọn một điểm đo nhất quán, chẳng hạn mỗi event đầu vào của ứng dụng là một logical publish operation.

Các metric hỗ trợ thường gồm:

- Số record gửi thành công và thất bại.
- Producer error rate và retry rate.
- Request latency, record queue time và batch size.
- Buffer available bytes và số lần buffer cạn.
- Timeout, lỗi metadata hoặc lỗi xác thực.

### 3.2. Publish latency

Latency nên được đo bằng histogram để quan sát phân phối và các giá trị ở đuôi. p50 cho biết trải nghiệm điển hình; p95 và p99 cho thấy nhóm request chậm mà giá trị trung bình có thể che khuất.

Phân biệt các loại latency:

- Producer request latency: thời gian client chờ phản hồi từ broker.
- Publish completion latency: thời gian từ lúc ứng dụng bắt đầu gửi event đến khi nhận kết quả gửi.
- End-to-end latency: thời gian từ lúc event được tạo hoặc broker nhận đến khi nghiệp vụ ở consumer hoàn tất.

Các số đo này trả lời những câu hỏi khác nhau. Không dùng producer request latency để thay thế cho end-to-end latency nếu cam kết của dịch vụ là xử lý event hoàn chỉnh.

### 3.3. Consumer lag và event freshness

Consumer lag thường được tính theo số offset:

[
Lag_{records} = LogEndOffset - CommittedOffset
]

Lag tăng cho biết consumer đang tụt lại so với dữ liệu mới trên partition. Tuy nhiên, số record bị trễ không trực tiếp cho biết event đã chờ bao lâu. Một partition có thể có lag vài nghìn record nhưng xử lý rất nhanh nếu throughput cao; một partition khác có lag nhỏ nhưng event cũ vẫn có thể nằm chờ lâu.

Vì thế nên theo dõi cả:

- Lag theo consumer group, topic và partition.
- Tuổi của record cũ nhất chưa xử lý, nếu có thể đo.
- Event freshness: thời gian từ khi event được chấp nhận hoặc ghi vào Kafka đến khi consumer hoàn tất xử lý.
- Tốc độ event vào và tốc độ xử lý ra.
- Số lần rebalance, thời gian rebalance và lỗi commit offset.

Event freshness thường gần với trải nghiệm người dùng hơn offset lag. Khi đo thời gian qua nhiều máy, cần đồng bộ clock và thống nhất timestamp nguồn; nếu clock lệch, phép đo có thể âm hoặc sai lệch đáng kể.

### 3.4. Processing success và xử lý lỗi

Với luồng nghiệp vụ, một SLI có thể là tỷ lệ event được xử lý thành công trong thời hạn:

[
SLI_{processing} =
rac{	ext{event hoàn tất thành công trong thời hạn}}
{	ext{event hợp lệ được nhận}}
	imes 100%
]

Cần nói rõ “hoàn tất” nghĩa là gì: logic nghiệp vụ đã chạy xong, dữ liệu đã commit xuống hệ thống đích, hay consumer chỉ mới nhận record. Nếu event được đưa vào dead-letter topic (DLT/DLQ), thông thường không nên tính là xử lý nghiệp vụ thành công. DLQ là cơ chế cô lập và điều tra lỗi; nó không đồng nghĩa với hoàn thành yêu cầu ban đầu.

Theo dõi thêm:

- Processing duration và tỷ lệ lỗi theo loại lỗi.
- Retry count, số record vào retry topic và thời gian chờ retry.
- DLQ ingress rate, số lượng tồn và tuổi record cũ nhất.
- Duplicate processing và idempotency conflict.
- Commit failures và số record được xử lý nhưng chưa commit.

Nếu nghiệp vụ cho phép xử lý bù hoặc chấp nhận một trạng thái terminal khác, hãy ghi rõ trạng thái đó trong định nghĩa SLI. Không thay đổi định nghĩa “thành công” chỉ để làm đẹp dashboard.

### 3.5. Broker, partition và replication health

Các metric này giúp phát hiện nguyên nhân ảnh hưởng đến availability hoặc durability:

| Metric | Ý nghĩa vận hành |
|---|---|
| Offline partitions | Partition không có leader khả dụng; cần điều tra ngay với topic quan trọng |
| Under-replicated partitions (URP) | Số replica chưa theo kịp leader |
| ISR shrink/expand rate | Tần suất replica rời khỏi hoặc quay lại ISR |
| Leader election rate | Tần suất thay đổi leader; tăng đột biến có thể gây gián đoạn |
| Active controller | Trạng thái controller của cluster |
| Request handler/network processor idle | Mức nhàn rỗi của các pool xử lý request và network |
| Bytes/messages in và out | Throughput vào/ra broker |
| Disk usage, disk latency và network utilization | Áp lực tài nguyên có thể dẫn đến replication hoặc request chậm |

URP bằng 0 là tín hiệu tốt nhưng không chứng minh toàn bộ luồng nghiệp vụ đang khỏe. Ngược lại, một broker có CPU cao chưa chắc đã làm SLO bị vi phạm. Hãy liên hệ metric hạ tầng với SLI của dịch vụ.

### 3.6. Durability và khả năng phục hồi

Durability liên quan đến khả năng giữ lại record đã được xác nhận. Các cấu hình thường được xem xét cùng nhau gồm replication factor, `acks`, `min.insync.replicas`, producer idempotence và chính sách leader election.

Ví dụ, với replication factor bằng 3, cấu hình producer `acks=all` và broker `min.insync.replicas=2` yêu cầu ít nhất hai replica trong ISR xác nhận trước khi request thành công. “All” ở đây nói đến các replica hiện có trong ISR, không có nghĩa mọi replica được cấu hình ban đầu đều luôn xác nhận. Cấu hình này giúp cân bằng độ bền dữ liệu và khả năng ghi khi một replica gặp sự cố, nhưng không phải lời bảo đảm tuyệt đối rằng không thể mất dữ liệu trong mọi tình huống.

Các chỉ số và mục tiêu cần cân nhắc:

- Số sự kiện mất dữ liệu đã xác nhận (confirmed acknowledged-record loss).
- Recovery Point Objective (RPO): lượng dữ liệu tối đa có thể mất theo cam kết.
- Recovery Time Objective (RTO): thời gian mục tiêu để khôi phục dịch vụ.
- Thời gian phục hồi replica và partition sau sự cố.
- Kết quả kiểm thử khôi phục, failover và disaster recovery.

Không tuyên bố RPO bằng 0 chỉ dựa trên `acks=all`. Cần đánh giá cả topology, replication, leader election, storage, backup, quy trình vận hành và kết quả kiểm thử phục hồi.

## 4. Viết SLO có thể đo và vận hành được

Một SLO hữu ích phải trả lời được năm câu hỏi:

1. **Đo cái gì?** Chọn SLI gắn với một hành trình hoặc kết quả người dùng quan tâm.
2. **Đơn vị nào được tính?** Xác định event, request, partition hay khoảng thời gian.
3. **Thế nào là tốt?** Đặt ngưỡng latency, trạng thái thành công hoặc deadline rõ ràng.
4. **Đo ở đâu và trong bao lâu?** Chọn nguồn dữ liệu, phạm vi topic/group và cửa sổ đo.
5. **Ai chịu trách nhiệm?** Gắn owner và quy trình phản ứng khi SLO có nguy cơ bị vi phạm.

Ví dụ về các SLO khởi điểm cho một luồng event quan trọng:

| SLI | Ví dụ mục tiêu | Cách hiểu |
|---|---|---|
| Publish success | Ít nhất 99,95% logical publish hợp lệ được xác nhận trong 250 ms, tính theo cửa sổ trượt 30 ngày | Đo thao tác gửi ở phía ứng dụng |
| Event freshness | Ít nhất 99% event được xử lý hoàn tất trong 60 giây, tính theo cửa sổ trượt 7 ngày | Đo từ mốc nhận event đã thống nhất đến khi xử lý xong |
| Processing success | Ít nhất 99,9% event hợp lệ hoàn tất nghiệp vụ trong 5 phút | DLQ và lỗi terminal không được tính là thành công |
| Write availability | Ít nhất 99,9% khoảng thời gian một phút, các partition quan trọng có thể nhận ghi | Phù hợp khi cần SLI dạng time-based |
| Durability | Không có trường hợp mất record đã được xác nhận; mọi sự cố được ghi nhận và điều tra | Theo dõi như mục tiêu bảo vệ dữ liệu, kèm RPO/RTO nếu có |

Các con số trên chỉ là ví dụ để minh họa cách viết. Chúng không phải cam kết mặc định cho mọi cluster. Hãy dùng baseline thực tế, mức độ quan trọng của luồng, khả năng phục hồi và yêu cầu của khách hàng để chọn mục tiêu.

### 4.1. Định nghĩa good event và bad event

Ví dụ SLO publish: “99,95% thao tác publish hợp lệ được xác nhận trong 250 ms”.

- Good event: logical publish hợp lệ nhận acknowledgement thành công trong không quá 250 ms.
- Bad event: publish thất bại hoặc hoàn tất sau 250 ms.
- Denominator: toàn bộ logical publish operation hợp lệ trong phạm vi đo.
- Exclusion: chỉ loại các trường hợp được định nghĩa rõ trong chính sách SLO hoặc SLA; không loại lỗi hệ thống chỉ vì chúng khó đo.

Việc định nghĩa mẫu số quan trọng ngang việc chọn target. Nếu bỏ các request timeout, record bị retry hoặc event xử lý thất bại khỏi mẫu số mà không có lý do rõ ràng, SLI sẽ không phản ánh chất lượng thực tế.

### 4.2. Chọn cửa sổ đo

Cửa sổ đo cần phù hợp với mục đích:

- Cửa sổ ngắn như 5 phút hoặc 1 giờ hỗ trợ phát hiện sự cố và burn rate nhanh.
- Cửa sổ 7 ngày giúp quan sát xu hướng trong tuần.
- Cửa sổ 28 hoặc 30 ngày thường phù hợp cho báo cáo mục tiêu theo tháng.

Có thể dùng rolling window để không phải đợi đến cuối tháng mới biết SLO đang gặp rủi ro. Nếu SLA quy định theo tháng dương lịch, báo cáo SLA vẫn phải tính đúng cửa sổ và quy tắc trong hợp đồng.

### 4.3. SLI theo event và SLI theo thời gian

SLI theo event lấy số event tốt chia cho tổng event. Cách này phản ánh trực tiếp chất lượng của các request hoặc message, nhưng cần xử lý đúng mẫu số và retry.

SLI theo thời gian lấy số khoảng thời gian đạt điều kiện chia cho tổng khoảng thời gian. Ví dụ, tỷ lệ phút mà các partition trọng yếu vẫn có thể nhận ghi. Cách này phù hợp với availability dạng uptime, nhưng một phút lỗi có thể ảnh hưởng rất ít hoặc rất nhiều event tùy lưu lượng. Không nên trộn hai cách tính trong cùng một SLO mà không nêu rõ.

## 5. Error budget và cách dùng trong vận hành

Error budget là phần chất lượng còn được phép tiêu hao khi SLO không yêu cầu 100%.

Với SLO 99,9%:

[
ErrorBudget = 100% - 99,9% = 0,1%
]

Nếu có 1.000.000 logical event trong cửa sổ đo, ngân sách tương ứng là 1.000 bad event. Với SLO dạng time-based 99,9% trong một tháng 30 ngày, ngân sách thời gian tương đương:

[
30 	imes 24 	imes 60 	imes 0,001 = 43,2 	ext{ phút}
]

Hai phép tính trên áp dụng cho hai loại SLI khác nhau: một bên đếm event, một bên đếm thời gian.

### 5.1. Burn rate

Burn rate cho biết tốc độ tiêu hao error budget so với tốc độ cho phép:

[
BurnRate =
rac{	ext{tỷ lệ lỗi quan sát được}}
{	ext{tỷ lệ lỗi cho phép theo SLO}}
]

Ví dụ SLO cho phép 0,1% lỗi. Nếu trong một cửa sổ gần đây quan sát được 0,5% lỗi, burn rate là 5x. Nếu tốc độ này kéo dài, budget sẽ cạn nhanh hơn dự kiến.

Có thể dùng nhiều cửa sổ để phân biệt sự cố nghiêm trọng với dao động ngắn:

- Cửa sổ ngắn phát hiện burn nhanh cần đánh thức on-call.
- Cửa sổ dài xác nhận vấn đề có kéo dài và đủ lớn để ảnh hưởng mục tiêu hay không.
- Ngưỡng cụ thể cần được hiệu chỉnh theo lưu lượng, độ trễ đo và mức độ nghiêm trọng của dịch vụ.

### 5.2. Chính sách khi error budget giảm

Đội ngũ cần thống nhất trước hành động tương ứng:

- Khi burn rate tăng nhanh: xác nhận impact, mở incident nếu cần, tìm nguyên nhân và giảm ảnh hưởng.
- Khi budget giảm đáng kể: xem lại các thay đổi gần đây, ưu tiên công việc reliability và đánh giá rủi ro release.
- Khi budget cạn: áp dụng chính sách hạn chế thay đổi có rủi ro theo thỏa thuận nội bộ cho đến khi có kế hoạch khôi phục độ tin cậy.
- Sau incident: cập nhật timeline, nguyên nhân, biện pháp khắc phục và bài học cho SLO hoặc runbook.

Error budget giúp đưa quyết định release và reliability về cùng một cách đo. Nó không thay thế đánh giá mức độ nghiêm trọng của sự cố; một lỗi hiếm nhưng gây mất dữ liệu có thể cần phản ứng ngay cả khi tổng budget còn nhiều.

## 6. SLA: biến mục tiêu thành cam kết với khách hàng

SLA thường nêu rõ dịch vụ nào được bảo vệ, mức cam kết, cách tính, cửa sổ đo, điều kiện loại trừ, trách nhiệm thông báo và biện pháp khắc phục nếu không đạt. Biện pháp có thể là service credit hoặc quy trình hỗ trợ đã thỏa thuận.

Khi xây dựng SLA cho nền tảng Kafka hoặc dịch vụ Spring Kafka, cần làm rõ:

- **Phạm vi dịch vụ:** cluster, topic, tenant, region và luồng nghiệp vụ nào nằm trong cam kết.
- **Định nghĩa availability:** dựa trên request publish, partition có thể ghi, hay event được xử lý hoàn tất.
- **Ngưỡng và cửa sổ:** target phần trăm, thời gian đo và cách tổng hợp.
- **Nguồn dữ liệu:** telemetry nào là nguồn chính thức, cách xử lý khoảng trống dữ liệu.
- **Ngoại lệ:** bảo trì đã thông báo, sự cố phía khách hàng hoặc phụ thuộc bên ngoài, nếu hợp đồng có quy định.
- **Thông báo và khắc phục:** thời hạn báo cáo, quy trình yêu cầu service credit và đầu mối hỗ trợ.

SLA về availability của nền tảng không tự động bao gồm SLA thời gian phản hồi của đội hỗ trợ. Đây là hai cam kết khác nhau và cần định nghĩa riêng.

SLO nội bộ có thể bao phủ nhiều khía cạnh hơn SLA: publish success, event freshness, processing success, durability và thời gian phục hồi. SLA nên dùng các phép đo có thể giải thích, kiểm chứng và thống nhất với khách hàng. Các điều khoản hợp đồng cần được chủ sở hữu dịch vụ và bộ phận có thẩm quyền rà soát trước khi công bố.

## 7. Thiết kế dashboard và cảnh báo

Dashboard cần giúp người trực trả lời nhanh ba câu hỏi: người dùng có đang bị ảnh hưởng không, luồng nào đang gặp vấn đề, và metric nào có thể giải thích nguyên nhân.

### 7.1. Bố cục dashboard gợi ý

| Khu vực | Nội dung nên hiển thị |
|---|---|
| SLO overview | SLI hiện tại, target, error budget còn lại và burn rate |
| Producer | Publish success, p95/p99 latency, retry/error rate, buffer availability |
| Broker | Offline partitions, URP, ISR changes, leader elections, request latency |
| Consumer | Lag theo group/topic, event freshness, processing rate, rebalance và commit errors |
| Failure handling | Retry topic ingress, DLQ ingress, DLQ backlog và tuổi record cũ nhất |
| Capacity | Disk, network, CPU, request handler idle, throughput và quota throttling |
| Incidents | Sự cố đang mở, thời điểm bắt đầu, luồng bị ảnh hưởng và liên kết runbook |

Cho phép lọc theo môi trường, cluster, topic và consumer group. Giữ tập nhãn có kiểm soát; không đưa event ID, order ID, customer ID hoặc các giá trị thay đổi liên tục vào label metric vì sẽ tạo cardinality rất lớn.

### 7.2. Cảnh báo theo triệu chứng và tác động

Ưu tiên cảnh báo dựa trên SLI hoặc burn rate. Dùng metric kỹ thuật để bổ sung ngữ cảnh và hướng dẫn chẩn đoán.

Ví dụ:

- Publish success giảm hoặc p99 latency vượt SLO: cảnh báo đội sở hữu producer và broker.
- Event freshness xấu đi cùng consumer lag tăng: kiểm tra tốc độ xử lý, downstream dependency và rebalance.
- Offline partition xuất hiện ở topic trọng yếu: cảnh báo mức độ cao.
- URP hoặc ISR shrink tăng kéo dài: kiểm tra broker, network, disk và replication.
- DLQ ingress tăng đột biến hoặc backlog già đi: điều tra lỗi dữ liệu, schema hoặc logic xử lý.
- Disk sắp đầy hoặc quota throttling kéo dài: cảnh báo capacity trước khi ảnh hưởng trực tiếp tới SLI.

Không cần page on-call cho mọi metric dao động nhỏ. Cảnh báo cần có ngưỡng, thời gian duy trì, mức độ nghiêm trọng, owner và runbook. Một cảnh báo không có hành động rõ ràng thường chỉ tạo nhiễu.

## 8. Thu thập và tính toán metric

Một hệ thống quan sát Kafka thường kết hợp nhiều nguồn:

- **Broker JMX:** thông tin request, throughput, partition, replication và tài nguyên broker.
- **Producer/consumer client metrics:** latency, retry, error, buffer, lag và rebalance.
- **Application metrics:** kết quả xử lý nghiệp vụ, event freshness, số event hoàn tất và DLQ.
- **Distributed tracing:** liên kết producer, consumer và downstream call bằng trace hoặc correlation ID.
- **Logs:** chi tiết lỗi để điều tra; tránh ghi payload nhạy cảm hoặc thông tin bí mật.

Tên metric cụ thể phụ thuộc phiên bản Kafka, client Spring Kafka, exporter và quy tắc ánh xạ JMX. Hãy kiểm tra metric thực tế đang được scrape trước khi dùng trong dashboard.

### 8.1. Ví dụ metric do ứng dụng phát ra

Ứng dụng có thể định nghĩa các counter và histogram với nhãn có cardinality thấp:

| Metric ví dụ | Loại | Mục đích |
|---|---|---|
| `kafka_publish_total` | Counter | Tổng logical publish operation hợp lệ |
| `kafka_publish_duration_seconds` | Histogram | Thời gian hoàn tất publish |
| `event_processing_total` | Counter | Số event xử lý theo kết quả |
| `event_processing_duration_seconds` | Histogram | Thời gian xử lý event |
| `event_freshness_seconds` | Histogram | Độ trễ từ mốc nhận event đến khi hoàn tất |

Các nhãn như `topic`, `consumer_group`, `environment` và `outcome` thường có thể kiểm soát được. Không dùng ID duy nhất của từng message làm nhãn. Có thể đưa ID vào trace hoặc log có kiểm soát để phục vụ điều tra.

### 8.2. Ví dụ PromQL

Các truy vấn dưới đây minh họa cách tính. Giả sử ứng dụng phát histogram `kafka_publish_duration_seconds`, trong đó chỉ publish thành công được đưa vào histogram, còn counter `kafka_publish_total` đếm tất cả logical publish operation hợp lệ.

Tỷ lệ publish thành công trong tối đa 250 ms, trên cửa sổ 30 ngày:

```promql
sum(increase(kafka_publish_duration_seconds_bucket{le="0.25"}[30d]))
/
sum(increase(kafka_publish_total[30d]))
```

p99 publish latency trong 5 phút:

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(kafka_publish_duration_seconds_bucket[5m])
  )
)
```

Consumer lag theo group và topic, nếu exporter cung cấp metric với tên và label tương ứng:

```promql
max by (consumer_group, topic) (
  kafka_consumergroup_lag
)
```

Số partition đang under-replicated, nếu exporter ánh xạ JMX thành metric này:

```promql
max(kafka_server_replicamanager_underreplicatedpartitions)
```

Đây là ví dụ phụ thuộc schema exporter, không phải tên metric bắt buộc. Với cửa sổ dài như 30 ngày, hệ thống Prometheus cần retention phù hợp hoặc recording rule/long-term storage. Cũng cần kiểm tra cách histogram xử lý lỗi, counter reset và các label trước khi dùng kết quả làm báo cáo SLO chính thức.

### 8.3. Instrumentation trong Spring Kafka

Ở tầng ứng dụng, hãy đặt điểm đo quanh thao tác gửi và quanh phần xử lý nghiệp vụ:

- Ghi nhận thời điểm bắt đầu publish và kết quả callback thành công/thất bại.
- Đo thời gian từ lúc listener nhận record đến khi nghiệp vụ hoàn tất.
- Ghi nhận retry, lỗi terminal và việc chuyển sang DLT.
- Chỉ đánh dấu processing success sau khi điều kiện hoàn tất đã được đáp ứng.
- Dùng trace/correlation ID để nối các chặng; giữ metric label ở mức tổng hợp.

Nếu consumer commit offset trước khi nghiệp vụ hoàn tất, metric “record đã đọc” sẽ đánh giá quá cao chất lượng. Với xử lý bất đồng bộ, cần xác định rõ thời điểm hoàn tất và cơ chế commit tương ứng.

## 9. Dùng metric để chẩn đoán sự cố

| Triệu chứng | Kiểm tra tiếp | Hướng điều tra |
|---|---|---|
| Publish error tăng | Producer error/retry, request latency, broker request queue, network | Xác định lỗi phía client, broker, quota hay kết nối |
| Publish p99 tăng | Broker request latency, batching, buffer, network và tải partition | Tìm bottleneck theo topic/partition và thời điểm |
| Consumer lag tăng liên tục | Event ingress rate so với processing rate, consumer instances, rebalance, downstream latency | Xác định consumer thiếu năng lực hay downstream đang chậm |
| Event freshness xấu nhưng lag nhỏ | Tuổi record, thời gian xử lý, retry delay và clock synchronization | Tìm event bị giữ lâu hoặc xử lý chậm ở một bước |
| URP hoặc ISR shrink tăng | Broker health, disk/network, replication traffic và log broker | Kiểm tra replica không theo kịp leader |
| DLQ tăng đột biến | Schema/version, payload validation, exception type và retry policy | Xác định poison message hoặc lỗi tương thích |
| Rebalance xảy ra liên tục | Consumer logs, thời gian xử lý mỗi poll, heartbeat và membership | Tìm consumer mất kết nối hoặc xử lý vượt giới hạn |
| Disk tăng nhanh | Retention, segment growth, throughput và dung lượng từng broker | Dự báo thời điểm đầy và kiểm tra phân bố partition |

Không thay đổi hàng loạt timeout, replication hoặc consumer concurrency chỉ dựa trên một biểu đồ. Trước hết xác định metric nào thay đổi, thời điểm bắt đầu, phạm vi ảnh hưởng và thay đổi hệ thống gần đó. Sau khi khôi phục, ghi lại nguyên nhân và cập nhật runbook.

## 10. Những sai lầm thường gặp khi đặt mục tiêu

**Chỉ đo broker uptime.** Broker process có thể đang chạy trong khi partition quan trọng không thể ghi hoặc consumer không xử lý được. Hãy đo cả request và kết quả end-to-end.

**Dùng average latency làm tiêu chuẩn duy nhất.** Trung bình có thể che khuất nhóm event chậm. Dùng histogram và theo dõi p95/p99 cùng tỷ lệ đáp ứng deadline.

**Coi offset lag là thời gian trễ.** Lag là số record, không phải số giây. Kết hợp lag với event age/freshness và throughput.

**Không định nghĩa denominator.** Loại request lỗi, retry hoặc event DLQ khỏi mẫu số có thể làm SLI sai lệch. Viết rõ logical operation, điều kiện hợp lệ và quy tắc loại trừ.

**Đếm retry như event mới.** Một event gửi nhiều lần có thể làm sai tỷ lệ thành công và lưu lượng. Phân biệt logical event với attempt ở tầng transport.

**Coi DLQ là thành công.** DLQ giúp cách ly lỗi nhưng thường vẫn là event chưa hoàn tất nghiệp vụ. Chỉ tính trạng thái terminal là thành công khi hợp đồng nghiệp vụ định nghĩa như vậy.

**Đặt target 100% cho mọi chỉ số.** Mục tiêu tuyệt đối thường không tạo được quyết định vận hành hữu ích và có thể khiến đội ngũ tối ưu sai chỗ. Chọn target dựa trên rủi ro, baseline và nhu cầu thực tế; riêng các yêu cầu bảo vệ dữ liệu có thể được theo dõi như mục tiêu không chấp nhận sự cố.

**Tạo cảnh báo từ mọi metric.** Quá nhiều cảnh báo làm giảm khả năng nhận ra sự cố quan trọng. Gắn cảnh báo với tác động, burn rate, owner và hành động tiếp theo.

**Không kiểm tra chất lượng dữ liệu đo.** Clock lệch, metric mất mẫu, label thay đổi, counter reset hoặc retention không đủ đều có thể làm báo cáo SLO sai. Cần có kiểm tra cho chính pipeline telemetry.

## 11. Quy trình vận hành SLO định kỳ

Một vòng vận hành thực tế có thể triển khai theo các bước:

1. Chọn luồng Kafka quan trọng và mô tả kết quả mà ứng dụng cần đạt.
2. Thống nhất định nghĩa SLI, good/bad event, mẫu số, phạm vi và cửa sổ đo.
3. Thu thập baseline trong các giai đoạn tải bình thường và cao điểm.
4. Chọn SLO phù hợp, ghi rõ owner và nguồn dữ liệu chính thức.
5. Xây dashboard theo SLI; bổ sung metric broker, producer, consumer và downstream để chẩn đoán.
6. Thiết lập cảnh báo theo burn rate và các triệu chứng nghiêm trọng.
7. Trong incident, ưu tiên khôi phục dịch vụ và giảm impact; sau đó điều tra nguyên nhân.
8. Định kỳ xem lại SLI, error budget, incident, thay đổi kiến trúc và nhu cầu khách hàng.

SLO không phải tài liệu viết một lần rồi bỏ quên. Khi lưu lượng, topology, yêu cầu nghiệp vụ hoặc dependency thay đổi, cách đo và mục tiêu cũng cần được xem xét lại. Mọi thay đổi định nghĩa nên được ghi phiên bản để so sánh báo cáo qua các giai đoạn.

## 12. Ví dụ tổng hợp: luồng đơn hàng

Giả sử một ứng dụng Spring Boot phát event `OrderCreated` lên topic `orders.created`. Consumer xử lý event để cập nhật hệ thống fulfillment.

Một bộ đo có thể được thiết kế như sau:

| Chặng | SLI | Metric hỗ trợ |
|---|---|---|
| Producer gửi event | Tỷ lệ logical publish được xác nhận trong 250 ms | Publish success, p99 latency, retry rate |
| Kafka lưu và phân phối | Tỷ lệ thời gian partition quan trọng có thể ghi | Offline partitions, URP, ISR changes, leader elections |
| Consumer nhận event | Tỷ lệ event freshness dưới 60 giây | Consumer lag, tuổi record cũ nhất, records consumed rate |
| Xử lý fulfillment | Tỷ lệ event hoàn tất nghiệp vụ trong 5 phút | Processing success, processing duration, downstream errors |
| Xử lý ngoại lệ | DLQ backlog được phát hiện và xử lý trong thời hạn vận hành | DLQ ingress, backlog age, retry count |

Giả sử trong 30 ngày có 2.000.000 logical publish operation hợp lệ. SLO publish yêu cầu 99,95% thành công trong 250 ms. Ngân sách lỗi là:

[
2.000.000 	imes (1 - 0,9995) = 1.000 	ext{ thao tác}
]

Nếu đã có 700 thao tác bad event, hệ thống đã dùng 70% budget. Đội ngũ nên xem xét xu hướng burn rate, thời điểm lỗi, topic/partition liên quan và các thay đổi gần đó. Nếu lỗi tập trung ở consumer fulfillment, publish SLO có thể vẫn đạt trong khi processing SLO đã xấu đi. Hai SLI riêng biệt giúp xác định đúng chặng bị ảnh hưởng.

Khi báo cáo cho khách hàng, chỉ dùng phép đo và quy tắc được ghi trong SLA. Dashboard nội bộ có thể cung cấp thêm nhiều chỉ số để đội vận hành hiểu nguyên nhân và chủ động giữ chất lượng dịch vụ.

## 13. Checklist khi đưa một SLO vào sử dụng

- [ ] SLI đại diện cho một kết quả có ý nghĩa với ứng dụng hoặc người dùng.
- [ ] Good event, bad event và denominator được định nghĩa cụ thể.
- [ ] Logical event được phân biệt với retry/transport attempt.
- [ ] Phạm vi topic, consumer group, môi trường và tenant đã rõ.
- [ ] Ngưỡng latency hoặc deadline có đơn vị và mốc bắt đầu/kết thúc.
- [ ] Cửa sổ đo và nguồn dữ liệu đã được thống nhất.
- [ ] Dashboard hiển thị SLI, target, error budget và xu hướng.
- [ ] Cảnh báo có owner, mức độ và runbook.
- [ ] DLQ, retry, duplicate và event freshness được xử lý trong định nghĩa.
- [ ] SLA bên ngoài khớp với cách đo và ngoại lệ đã thỏa thuận.
- [ ] Có lịch xem lại mục tiêu sau incident hoặc thay đổi kiến trúc.

Khi các điểm này rõ ràng, đội vận hành có thể dùng SLO để quyết định ưu tiên reliability, dùng SLA để quản lý cam kết dịch vụ và dùng metric Kafka/Spring Kafka để phát hiện cũng như xử lý nguyên nhân gây suy giảm chất lượng.

