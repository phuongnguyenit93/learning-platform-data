# Phân biệt lag theo offset, tuổi bản ghi và độ trễ đầu cuối

Consumer lag, record age và end-to-end latency đều liên quan đến việc event có được xử lý kịp thời hay không, nhưng chúng đo ba khía cạnh khác nhau. **Offset lag** đo khoảng cách giữa vị trí consumer và một mốc offset của partition. **Record age** đo event cũ nhất còn chờ đã tồn tại bao lâu. **End-to-end latency** đo thời gian từ lúc nghiệp vụ phát sinh hoặc được chấp nhận đến khi kết quả cuối cùng có thể quan sát được.

Một dashboard chỉ có offset lag có thể báo 0 dù consumer không hoạt động và topic không có dữ liệu mới; hoặc báo hàng nghìn offset dù backlog mới hình thành vài giây. Ngược lại, record age có thể cao dù lag chỉ vài record. Muốn hiểu sức khỏe của Kafka pipeline, cần dùng cả ba phép đo và liên hệ chúng với deadline nghiệp vụ.

## 1. Ba câu hỏi, ba phép đo

| Phép đo | Câu hỏi trả lời | Đơn vị thường dùng |
|---|---|---|
| Offset lag | Consumer còn cách vị trí cuối của log bao nhiêu offset? | Offset / record-position delta |
| Record age | Event cũ nhất chưa xử lý đã chờ bao lâu? | Giây, phút |
| End-to-end latency | Từ lúc nghiệp vụ bắt đầu đến lúc kết quả hoàn tất mất bao lâu? | Millisecond, giây, phút |

Ví dụ luồng đặt hàng:

~~~mermaid
flowchart LR
    A["Order accepted (t0)"] --> B["Producer publish"]
    B --> C["Kafka append (t1)"]
    C --> D["Producer ACK (t2)"]
    D --> E["Consumer receives (t3)"]
    E --> F["Database commit (t4)"]
    F --> G["Order status visible (t5)"]
~~~

- Offset lag cho biết consumer đã tiến gần tới cuối partition đến đâu.
- Record age cho biết event đang chờ lâu nhất trong hàng đợi đã cũ bao nhiêu.
- End-to-end latency là t5 trừ t0, bao gồm publish, chờ, xử lý và cập nhật hệ thống đích.

Không phép đo nào thay thế hoàn toàn hai phép đo còn lại.

## 2. Offset lag được tính như thế nào?

Kafka lưu record trong từng partition với offset tăng dần. Consumer group có committed offset cho từng topic-partition. Committed offset biểu thị vị trí tiếp theo mà group sẽ đọc khi khôi phục từ checkpoint.

Một cách tính phổ biến:

\[
Lag_{offset}(p) = EndOffset(p) - CommittedOffset(p)
\]

Trong đó:

- EndOffset là vị trí offset kế tiếp ở cuối log theo boundary mà công cụ giám sát lựa chọn.
- CommittedOffset là offset kế tiếp đã được group commit.
- p là một partition cụ thể.

Ví dụ:

| Partition | End offset | Committed offset | Offset lag |
|---|---:|---:|---:|
| orders-0 | 120.500 | 120.000 | 500 |
| orders-1 | 98.100 | 98.000 | 100 |
| orders-2 | 76.020 | 76.020 | 0 |
| **Tổng** | | | **600** |

Consumer group có tổng offset lag 600, nhưng partition orders-0 chiếm 500. Nếu chỉ nhìn tổng, có thể bỏ sót partition đang nóng hoặc consumer xử lý chậm riêng.

### End offset không phải lúc nào cũng là cùng một boundary

Các công cụ có thể dùng các mốc khác nhau:

- **Log End Offset (LEO):** offset kế tiếp mà replica có thể ghi vào log cục bộ.
- **High Watermark (HW):** boundary của dữ liệu đã được replicate đủ điều kiện để consumer thông thường đọc.
- **Last Stable Offset (LSO):** boundary dùng cho consumer đọc theo isolation level read_committed; record nằm sau LSO có thể thuộc transaction chưa hoàn tất.

Vì vậy, công thức lag chỉ có ý nghĩa khi biết exporter đang lấy LEO, HW hay LSO và đang so sánh với committed offset hay consumer position. Với transactional producer và consumer read_committed, dùng LEO làm reference có thể làm lag trông lớn hơn lượng record hiện có thể đọc vì phần transaction chưa ổn định chưa được mở cho consumer.

Hãy đọc định nghĩa metric của exporter và giữ cùng một boundary khi so sánh qua thời gian. Không ghép end offset từ một nguồn với committed offset được diễn giải khác từ nguồn khác.

## 3. Committed offset, consumer position và offset đã xử lý

Ba vị trí thường bị nhầm:

| Vị trí | Ý nghĩa | Hạn chế |
|---|---|---|
| Committed offset | Checkpoint đã lưu cho lần khởi động/assignment tiếp theo | Có thể chậm hơn xử lý thực tế vì commit theo batch hoặc interval |
| Consumer position | Offset kế tiếp mà consumer sẽ trả về sau các record đã poll | Có thể đã đi trước công việc xử lý bất đồng bộ còn đang chạy |
| Processed offset watermark | Vị trí liên tục cao nhất mà ứng dụng xác nhận đã hoàn tất side effect | Ứng dụng phải tự instrument và chỉ tiến lên khi không còn gap chưa xử lý |

Ví dụ consumer poll các offset 100, 101 và 102 rồi gửi ba công việc sang executor:

- Consumer position có thể đã ở 103.
- Offset 100 và 102 đã xử lý xong nhưng 101 còn đang gọi database.
- Ứng dụng chưa thể an toàn commit 103 nếu commit đó làm mất khả năng đọc lại offset 101 sau crash.
- Processed watermark liên tục vẫn chỉ ở 101, tức vị trí kế tiếp chưa hoàn tất là offset 101.

Offset lag dựa trên committed offset có thể cao hơn thực tế khi ứng dụng xử lý xong nhưng chưa commit. Offset lag dựa trên consumer position có thể thấp hơn backlog xử lý thực tế khi ứng dụng poll nhanh rồi xử lý chậm. Nếu xử lý song song, nên theo dõi cả in-flight count và processed watermark.

Đối với consumer xử lý tuần tự và commit sau mỗi batch đã hoàn tất, committed offset thường là proxy hữu ích. Với asynchronous processing, không coi position là bằng chứng nghiệp vụ đã hoàn thành.

## 4. Offset delta không đồng nghĩa số record chưa xử lý chính xác

Offset là vị trí trong log, không phải số thứ tự liên tục của mọi business event mà consumer nhìn thấy. Offset lag thường được dùng như một proxy cho lượng công việc còn lại, nhưng có thể khác số record thực sự chưa đọc:

- **Log compaction:** các record cũ có thể bị loại bỏ theo key; offset bị trống vẫn không được đánh số lại.
- **Transactional records:** control batch và record thuộc transaction bị abort ảnh hưởng cách consumer nhìn thấy dữ liệu.
- **Read committed:** consumer không nhìn thấy record của transaction chưa commit, dù log đã có offset tương ứng.
- **Retention/deletion:** segment cũ có thể bị xóa; offset range và vị trí reset cần được diễn giải theo log còn tồn tại.
- **Consumer filtering:** ứng dụng có thể bỏ qua một số record theo logic, nhưng offset vẫn tiến qua chúng.

Do đó, lag 1.000 offset không nhất thiết có đúng 1.000 event nghiệp vụ đang chờ. Nếu cần ước lượng số record backlog chính xác hơn, dùng metric record-level của consumer hoặc phép đo ứng dụng, đồng thời ghi rõ cách tính và chi phí thu thập.

## 5. Record age là gì?

Record age đo tuổi của event cũ nhất còn chưa hoàn tất xử lý. Cách định nghĩa đơn giản:

\[
RecordAge = Now - Timestamp_{oldest\ pending\ record}
\]

Điểm quan trọng là timestamp phải đại diện cho mốc mà tổ chức muốn đo:

- Dùng thời điểm broker append để đo record đã nằm trong Kafka bao lâu.
- Dùng event occurrence time để đo event nghiệp vụ đã tồn tại bao lâu.
- Dùng thời điểm producer chấp nhận request nếu muốn đo thời gian chờ tính từ lúc hệ thống nhận yêu cầu.

Record age trả lời câu hỏi: “Event cũ nhất đang chờ đã bị giữ lại bao lâu?” Đây thường là tín hiệu dễ liên hệ với deadline nghiệp vụ hơn số offset thuần túy.

### Không nhầm oldest record age với thời gian từ record cuối cùng

Hai metric khác nhau:

- Oldest unprocessed record age: tuổi của event cũ nhất chưa hoàn tất.
- Time since last record: thời gian kể từ khi partition nhận record mới nhất.

Partition không có traffic trong 30 phút có thể có time-since-last-record là 30 phút nhưng không có backlog. Không nên cảnh báo backlog age chỉ vì partition idle. Cần có tín hiệu input rate hoặc pending count để diễn giải age.

## 6. CreateTime, LogAppendTime và event occurrence time

Kafka record có timestamp, nhưng timestamp đó có thể mang semantics khác nhau tùy cấu hình topic:

| Timestamp | Ai tạo? | Phù hợp để đo |
|---|---|---|
| CreateTime | Thường do producer gán | Thời điểm record được tạo theo đồng hồ producer; có thể gần event time nếu ứng dụng quy định |
| LogAppendTime | Broker gán lúc append | Thời điểm broker nhận record, phù hợp đo thời gian nằm trong Kafka |
| occurredAt trong payload/header | Ứng dụng nghiệp vụ gán | Thời điểm nghiệp vụ xảy ra, phù hợp đo business freshness nếu đồng hồ được đồng bộ |

Topic có thể dùng cấu hình timestamp type để chọn CreateTime hoặc LogAppendTime. Không giả định mọi topic đều cùng semantics; kiểm tra cấu hình và producer thực tế.

Nếu producer đặt CreateTime từ máy có clock lệch, phép tính Now trừ timestamp có thể âm hoặc quá lớn. Với LogAppendTime, timestamp phản ánh broker append nhưng không biết event đã chờ bao lâu ở outbox hoặc trước khi producer gửi. Với occurredAt, cần bảo đảm timezone và clock sync.

Để tách các chặng, có thể mang event occurrence time trong payload/header, dùng record timestamp của broker cho append time, rồi ghi processing completion time ở consumer. Không ghi đè một timestamp để đại diện cho mọi chặng.

## 7. Ví dụ: cùng offset lag nhưng record age rất khác

Hai consumer group cùng có offset lag 1.000:

| Luồng | Offset lag | Tốc độ input gần đây | Tuổi event cũ nhất đang chờ |
|---|---:|---:|---:|
| Search indexing | 1.000 | 50.000 event/s | 3 giây |
| Payment update | 1.000 | 2 event/s | 8 phút |

Search indexing có nhiều offset chờ nhưng tốc độ xử lý cao và backlog mới hình thành. Payment update chỉ có 1.000 offset lag nhưng event cũ nhất đã vượt deadline 2 phút. Chỉ dựa vào offset lag, cả hai luồng trông giống nhau dù mức độ ảnh hưởng hoàn toàn khác.

Chiều ngược lại cũng xảy ra: một partition chỉ lag 5 offset nhưng record cũ nhất đã chờ 20 phút vì consumer bị treo, trong khi producer gần như không phát thêm event.

Khi vận hành, nên đặt ngưỡng record age theo deadline của từng flow. Không áp một threshold chung cho analytics, payment và notification.

## 8. End-to-end latency là gì?

End-to-end latency đo thời gian từ mốc nghiệp vụ đầu vào đến khi kết quả cuối cùng sẵn sàng ở nơi consumer của dịch vụ có thể quan sát:

\[
E2E = t_{business\ completion} - t_{business\ accepted}
\]

Một hành trình có thể chia thành:

| Mốc | Ví dụ |
|---|---|
| t0 | API chấp nhận đơn hàng |
| t1 | Broker append record |
| t2 | Producer nhận ACK từ Kafka |
| t3 | Consumer bắt đầu xử lý |
| t4 | Consumer commit transaction/database side effect |
| t5 | Projection/API hiển thị trạng thái mới |

Các khoảng:

- Publish time: t2 - t0.
- Append-to-ACK/replication wait: t2 - t1.
- Queueing delay sau ACK: t3 - t2.
- Processing time: t4 - t3.
- Visibility delay: t5 - t4.
- End-to-end latency: t5 - t0.

Khoảng append-to-ACK (t2 - t1) là một phần của publish time (t2 - t0), không cộng lần thứ hai khi tính tổng. Các khoảng chỉ cộng chính xác khi timestamp được định nghĩa nhất quán, đồng hồ giữa các máy được đồng bộ và các mốc thuộc cùng một event/correlation ID.

Producer ACK không phải end-to-end completion. Consumer ACK/commit offset cũng không nhất thiết có nghĩa người dùng đã nhìn thấy kết quả; ứng dụng có thể commit Kafka offset trước khi database transaction hoặc projection được cập nhật nếu thiết kế sai.

## 9. Dùng event ID và correlation ID để đo end-to-end

Để nối event qua nhiều service, envelope nên mang event ID và correlation ID ổn định:

~~~json
{
  "eventId": "evt-100045",
  "correlationId": "order-8472",
  "eventType": "PaymentRequested",
  "occurredAt": "2026-11-20T10:15:30.125Z",
  "payload": {
    "orderId": "order-8472",
    "amountMinor": 259900
  }
}
~~~

Consumer ghi nhận:

- Thời điểm nhận record.
- Thời điểm bắt đầu xử lý.
- Thời điểm side effect được commit.
- Kết quả success/retry/reject.
- Event ID và correlation ID dùng để tra cứu trace/log.

Khi event đi qua nhiều topic, giữ correlation ID để liên kết các span hoặc event liên quan. Event ID định danh một message; correlation ID định danh một hành trình nghiệp vụ có thể gồm nhiều message.

Không dùng event ID làm metric label vì cardinality tăng không giới hạn. Dùng ID trong trace/log có kiểm soát; metric chỉ dùng label có miền giá trị nhỏ như service, topic, consumer group, event type hoặc outcome.

## 10. Phân rã latency để tìm bottleneck

Giả sử end-to-end latency tăng từ 2 giây lên 90 giây. Chỉ nhìn E2E biết người dùng bị ảnh hưởng, nhưng chưa biết chặng nào gây ra. Hãy phân rã:

| Chặng | Metric | Dấu hiệu sự cố |
|---|---|---|
| Producer | send latency, retry, buffer wait | API publish chậm hoặc retry tăng |
| Kafka append/replication | request latency, ISR, produce error | Broker hoặc replication chậm |
| Queueing | oldest record age, offset lag theo partition | Consumer không theo kịp hoặc partition bị bỏ trống |
| Consumer processing | processing duration, error/retry | Logic, CPU hoặc dependency chậm |
| Sink/visibility | database commit, projection freshness | Hệ thống đích chậm hoặc cập nhật thất bại |

Nếu record age cao nhưng processing duration thấp, consumer có thể đang thiếu capacity hoặc assignment không cân bằng. Nếu record age thấp nhưng E2E cao, thời gian có thể bị tiêu ở producer trước khi append, trong consumer processing hoặc sau khi ghi sink.

## 11. Tổng hợp theo partition và tránh che giấu điểm nóng

Không chỉ quan sát tổng lag toàn topic hoặc toàn group. Với mỗi partition, theo dõi:

- Offset lag.
- Oldest pending record age.
- Input rate và processing rate.
- In-flight records và processing duration.
- Consumer/member đang sở hữu partition (nếu mô hình group cung cấp assignment).

Ví dụ tổng lag 1.000 có thể phân bố:

| Partition | Lag | Oldest age |
|---|---:|---:|
| orders-0 | 20 | 2 giây |
| orders-1 | 25 | 3 giây |
| orders-2 | 30 | 2 giây |
| orders-3 | 925 | 12 phút |

Tổng lag 1.000 không quá lớn, nhưng orders-3 đang có vấn đề nghiêm trọng. Dashboard nên hiển thị max lag, max age và top partition theo mức độ trễ, cùng với tổng để thấy quy mô backlog.

Khi tổng hợp:

- Sum offset lag ước lượng quy mô offset backlog của group.
- Max offset lag giúp tìm partition xấu nhất.
- Max record age phản ánh event cũ nhất đang chờ.
- p95/p99 processing latency cho biết tail processing time.

Không lấy trung bình record age giữa partition rồi dùng làm SLO nếu một partition đơn lẻ có thể làm trễ một nhóm khách hàng.

## 12. Những trường hợp làm metric sai lệch

### Consumer poll nhanh nhưng xử lý chậm

Consumer position có thể tiến lên khi poll record vào memory. Nếu xử lý qua executor, offset lag theo position giảm nhưng công việc vẫn nằm trong queue nội bộ. Instrument số record in-flight, queue age và processed watermark.

### Commit offset theo batch

Consumer xử lý xong nhiều record nhưng chỉ commit mỗi vài giây. Committed-offset lag có thể cao hơn backlog thực tế. Đây là khoảng cách checkpoint, không nhất thiết là số event chưa xử lý.

### Consumer dừng nhưng topic không có traffic

Offset lag có thể bằng 0 vì end offset không tăng. Consumer availability vẫn có thể bằng 0. Dùng heartbeat/member state, poll activity hoặc synthetic event để phát hiện consumer không hoạt động.

### Transaction chưa commit

Consumer read_committed chỉ nhìn thấy dữ liệu tới LSO. Lag tính từ LEO có thể bao gồm vùng log chưa ổn định; đối chiếu isolation level và boundary exporter sử dụng.

### Clock skew

CreateTime hoặc occurredAt từ producer có thể lệch clock. Đồng bộ NTP/chrony, ghi UTC và theo dõi clock offset. Dùng monotonic clock để đo duration bên trong một process; dùng timestamp UTC/correlation trace khi cần nối nhiều service.

### Topic compacted hoặc retention

Offset delta không bằng số record có thể đọc. Compaction và retention có thể làm mất record cũ theo policy, nhưng không làm offset được đánh số lại. Đừng diễn giải offset lag như số business event chính xác.

### Retry và duplicate

Record có thể được xử lý lại sau crash hoặc rebalance. Event-level E2E nên định danh theo event ID và quy định completion lần đầu hay completion cuối; nếu không, duplicate có thể làm sai latency distribution và success ratio.

## 13. Instrumentation và metric gợi ý

Các metric dưới đây là ví dụ do ứng dụng/exporter định nghĩa; tên metric built-in và label thực tế phụ thuộc Kafka client, exporter và version:

~~~text
kafka_consumer_offset_lag{topic,partition,group}
kafka_consumer_record_age_seconds{topic,partition,group}
kafka_consumer_inflight_records{topic,partition,group}
kafka_consumer_processed_offset{topic,partition,group}
kafka_consumer_committed_offset{topic,partition,group}
event_processing_duration_seconds{service,event_type}
event_end_to_end_duration_seconds{flow}
event_oldest_pending_age_seconds{flow,topic}
event_completion_total{flow,result}
~~~

Ý nghĩa:

- Offset lag: đo vị trí log so với checkpoint hoặc processed watermark đã chọn.
- Record age: đo timestamp của oldest pending event so với thời điểm hiện tại.
- In-flight: số record đã nhận nhưng chưa hoàn tất.
- Processed offset: watermark liên tục do ứng dụng xác nhận.
- E2E histogram: thời gian từ business acceptance đến business completion.

Đặt tên metric và tài liệu hóa rõ nguồn offset, timestamp semantics, boundary LEO/HW/LSO, trạng thái completion và đơn vị. Không dùng cùng một metric name cho committed lag và position lag.

Tránh label có cardinality cao như event ID, order ID, customer ID hoặc raw exception. Partition label có thể tăng theo số partition; chỉ bật chi tiết này ở mức cần thiết và kiểm soát số series. Dùng trace/log cho drill-down chi tiết.

## 14. Alerting theo đúng loại tín hiệu

Không tạo một alert chung tên “Kafka lag high” rồi dùng nó cho mọi vấn đề. Mỗi phép đo cần ngưỡng và hành động khác nhau:

| Alert | Ví dụ điều kiện | Hành động đầu tiên |
|---|---|---|
| Offset lag tăng liên tục | Lag tăng nhiều cửa sổ liên tiếp và processing rate thấp hơn input rate | Kiểm tra consumer capacity, assignment và partition skew |
| Oldest record age vượt deadline | Event cũ nhất chưa xử lý vượt 2 phút ở payment flow | Xác định partition, consumer và downstream dependency |
| E2E latency SLO burn | Tỷ lệ payment hoàn tất trong 120 giây giảm dưới mục tiêu | Theo trace phân rã publish, queue, process và sink |
| In-flight queue tăng | Poll rate cao nhưng completion rate thấp | Kiểm tra executor, backpressure và xử lý bất đồng bộ |
| Consumer không hoạt động | Không có poll/heartbeat hoặc group member mất | Kiểm tra process, rebalance, network và deployment |

Chọn ngưỡng theo business deadline, tốc độ event, khả năng drain backlog và tier của luồng. Một ngưỡng 10.000 offset có thể phù hợp với analytics nhưng quá cao với payment.

## 15. Ví dụ đọc dashboard

Giả sử dashboard cho thấy:

- Tổng offset lag: 300.
- Partition có max lag: 270.
- Oldest pending record age: 9 phút.
- Consumer processing p95: 40 ms.
- End-to-end latency p99: 9 phút 20 giây.

Diễn giải:

1. Lag tập trung ở một partition, không phải toàn group.
2. Record cũ nhất đã chờ lâu, dù số offset không lớn.
3. Processing p95 thấp cho thấy mỗi record được xử lý nhanh khi tới lượt.
4. Có thể partition không được consume, consumer assignment bị lệch, hoặc input key skew.
5. Nếu record age được tính từ cùng mốc business acceptance/occurredAt với E2E, hai giá trị gần nhau cho thấy phần lớn thời gian bị mất trước khi processing bắt đầu. Nếu age dùng LogAppendTime, nó chỉ đo thời gian từ lúc broker append và không bao gồm thời gian trước đó.

Hướng điều tra: xem assignment/member, input rate theo partition, heartbeat/rebalance, oldest timestamp của record chưa hoàn tất và tình trạng dependency. Không tăng toàn bộ consumer ngay nếu partition count hoặc assignment là giới hạn.

Một trường hợp khác:

- Offset lag: 50.000.
- Oldest pending age: 4 giây.
- Consumer processing p95: 20 ms.
- Input rate vừa tăng đột biến gấp 10 lần.

Đây có thể là burst backlog mà consumer đang xử lý nhanh. Cần theo dõi lag có giảm không và tính drain time; chưa chắc đã là sự cố nếu age vẫn nằm trong deadline.

## 16. Công thức ước lượng thời gian xử lý backlog

Nếu input tiếp tục đến với tốc độ λ event/giây và consumer xử lý được μ event/giây, khi μ lớn hơn λ, thời gian drain gần đúng:

\[
T_{drain} \approx \frac{B}{\mu - \lambda}
\]

Trong đó B là số event backlog ước lượng, không nhất thiết bằng offset lag tuyệt đối vì offset gap/compaction/transaction có thể làm hai giá trị khác nhau.

Ví dụ backlog thực tế 24.000 event, input rate 100 event/s, processing rate 500 event/s:

\[
T_{drain} \approx \frac{24.000}{500 - 100} = 60\text{ giây}
\]

Nếu processing rate chỉ bằng hoặc thấp hơn input rate, backlog không thể giảm. Khi đó cần tăng capacity, giảm ingress hoặc khắc phục bottleneck downstream. Công thức là ước lượng steady-state; partition skew, retry, batch, latency variance và rate limit có thể làm thời gian thực tế dài hơn.

## 17. Production checklist

- [ ] Tài liệu hóa offset lag đang dùng committed offset hay consumer position.
- [ ] Xác định reference boundary là LEO, HW hay LSO và isolation level của consumer.
- [ ] Theo dõi lag riêng từng topic-partition, có sum và max.
- [ ] Không coi offset delta là số business record chính xác trong topic compacted/transactional.
- [ ] Theo dõi oldest pending record age với timestamp semantics rõ ràng.
- [ ] Phân biệt CreateTime, LogAppendTime và business occurredAt.
- [ ] Đồng bộ clock; dùng monotonic clock để đo duration trong process.
- [ ] Với xử lý bất đồng bộ, đo in-flight và processed contiguous watermark.
- [ ] Đo end-to-end latency từ business acceptance đến sink/business completion.
- [ ] Dùng event ID/correlation ID để nối trace mà không đưa ID vào metric label.
- [ ] Kết hợp offset lag, record age, processing duration và E2E latency.
- [ ] Có alert riêng cho lag tăng, age vượt deadline, E2E SLO burn và consumer không hoạt động.
- [ ] Đặt ngưỡng theo tier và business deadline, không dùng một ngưỡng cho mọi topic.
- [ ] Kiểm thử partition skew, consumer pause, async processing, rebalance và downstream outage.
- [ ] Có runbook xác định partition/consumer/dependency gây trễ và xác nhận backlog đã drain.

Offset lag cho biết khoảng cách vị trí trong log; record age cho biết event cũ nhất đang chờ đã tồn tại bao lâu; end-to-end latency cho biết người dùng phải đợi bao lâu để nhận kết quả. Dùng riêng lẻ từng metric dễ dẫn tới kết luận sai. Kết hợp cả ba, theo dõi ở cấp partition và định nghĩa timestamp/offset boundary rõ ràng sẽ giúp phát hiện backlog thực sự, tìm đúng bottleneck và bảo vệ SLO nghiệp vụ.
