# Thiết kế kiểm thử tải với dữ liệu và lỗi đại diện

## 1. Mục tiêu của kiểm thử tải trong Spring Cloud Stream

Spring Cloud Stream xây dựng ứng dụng xử lý sự kiện bằng các hàm Supplier, Function và Consumer kết nối tới Kafka, RabbitMQ hoặc Pulsar qua binding và binder. Khi tăng lưu lượng, kết quả phụ thuộc nhiều hơn vào số lượng message mỗi giây: kích thước payload, phân bố message key, số partition, consumer group, độ trễ downstream, cách retry, DLQ và khả năng khôi phục sau lỗi.

**Kiểm thử tải có dữ liệu và lỗi đại diện** là tạo một workload đủ giống hành vi sản xuất, bao gồm message bình thường, message phức tạp, dữ liệu sai và sự cố có kiểm soát. Mục tiêu là phát hiện giới hạn throughput, độ trễ, backlog, tài nguyên và tính đúng đắn của kết quả trước khi triển khai.

Ví dụ: service xử lý 1.000 đơn hàng/giây có thể chạy tốt nếu mọi đơn hàng dùng key phân bố đều và dịch vụ thanh toán phản hồi trong 10 ms. Cùng tốc độ đó có thể gây backlog khi 80% sự kiện dồn vào một số key nóng, 2% payload lớn và 1% request tới dịch vụ thanh toán bị timeout.

Một kiểm thử hữu ích phải trả lời được:

- Với lưu lượng bình thường, service có đáp ứng SLO và xử lý đúng kết quả không?
- Tại đỉnh tải, độ trễ đầu cuối và backlog tăng bao nhiêu?
- Hot key, payload lớn và schema cũ ảnh hưởng đến hiệu năng thế nào?
- Retry hoặc redelivery có làm tải tăng theo cấp số nhân không?
- Khi broker, consumer hoặc downstream lỗi, message đi đâu và có bị mất hoặc xử lý trùng không?
- Sau khi sự cố kết thúc, hệ thống mất bao lâu để xóa backlog và trở về ngưỡng ổn định?

## 2. Xác định ranh giới hệ thống cần đo

Trước khi sinh dữ liệu, xác định đoạn xử lý thực sự nằm trong phép đo. Một message có thể đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    G[Load generator] --> I[(Input topic / queue)]
    I --> B[Spring Cloud Stream input binding]
    B --> F[Function / Consumer]
    F --> S[(Database / HTTP dependency)]
    F --> O[Output binding]
    O --> Q[(Output topic / queue)]
    B -. Failure / retry .-> D[(Retry or DLQ)]
    I -. Lag and backlog .-> M[Metrics and tracing]
    F -. Latency and errors .-> M
    Q -. Delivery verification .-> V[Result verifier]
    D -. Failure accounting .-> V
~~~

Cần đặt rõ ít nhất ba ranh giới thời gian:

1. **Ingress latency:** từ lúc producer bắt đầu hoặc broker xác nhận publish tới khi consumer nhận được message.
2. **Processing latency:** từ lúc handler bắt đầu tới khi xử lý hoặc publish output hoàn tất theo định nghĩa cụ thể.
3. **End-to-end latency:** từ lúc message được đưa vào đầu hệ thống tới khi kết quả đầu ra hoặc trạng thái nghiệp vụ được xác nhận.

Không nhầm producer acknowledgement với việc consumer xử lý xong. Với hai broker độc lập, output publish thành công cũng không chứng minh transaction downstream hoàn tất. Quy định chính xác điểm bắt đầu, điểm kết thúc và phương pháp đồng bộ đồng hồ trước khi so sánh p95/p99.

## 3. Kiểm thử tải khác kiểm thử chức năng như thế nào?

Unit test kiểm tra logic một hàm; Spring Cloud Stream Test Binder xác minh binding, conversion và route message trong bộ nhớ. Những bài kiểm thử này rất hữu ích nhưng không tái hiện đầy đủ broker thật, partition assignment, network jitter, rebalancing, persistence, acknowledgement hay broker-level retry.

| Lớp kiểm thử | Điều được kiểm tra | Hạn chế |
|---|---|---|
| Unit test | Quy tắc nghiệp vụ của Function/Consumer | Không có broker và concurrency thực |
| Test Binder | Đường đi message, binding, conversion trong app | Không mô phỏng đầy đủ vận hành Kafka/RabbitMQ/Pulsar |
| Integration test | ACL, consumer group, serializer, retry, DLQ, broker semantics | Thường chạy ở lưu lượng nhỏ |
| Load test với broker thật | Throughput, latency, lag, skew, error amplification, recovery | Cần môi trường, quan sát và kiểm soát tải |

Kiểm thử tải nên đặt trong môi trường có loại broker, phiên bản client/binder, topic/queue, partition, replica, retention, tài nguyên và dependency tương đương production ở mức có thể. Nếu hạ tầng nhỏ hơn production, ghi rõ tỷ lệ khác biệt; kết quả đo không tự suy rộng tuyến tính.

## 4. Viết mục tiêu đo lường trước khi chạy

Một kịch bản tải chỉ có ý nghĩa khi có tiêu chí đạt và thất bại. Định nghĩa SLO minh họa cho một pipeline xử lý đơn hàng:

| Chỉ số | Mục tiêu ví dụ ở tải ổn định | Cách đo |
|---|---|---|
| Throughput đã xác nhận | Ít nhất 1.000 event hợp lệ/giây | Số event hoàn tất, không phải chỉ số publish |
| End-to-end p95 | Không quá 1.500 ms | Mốc ingress đến trạng thái đầu ra |
| End-to-end p99 | Không quá 3.000 ms | Phân bố độ trễ trên event hợp lệ |
| Consumer lag | Không tăng liên tục sau warm-up | Offset lag hoặc backlog age/size |
| DLQ sai phân loại | 0 | Event hợp lệ bị đẩy sai sang DLQ |
| Event mất dấu | 0 | Tổng đối soát event ID qua kết quả và các trạng thái lỗi |
| Thời gian phục hồi | Backlog về ngưỡng trong 10 phút | Tính từ lúc downstream/broker hoạt động lại |

Đây là **mục tiêu giả định để minh họa**, không phải số mặc định của Spring Cloud Stream. Mục tiêu thật phải dựa trên hành vi production và ràng buộc kinh doanh.

Thông thường cần theo dõi cả error budget, p50/p95/p99, backlog, memory, CPU, GC, số connection, mức sử dụng broker và tỉ lệ retry/DLQ. Một hệ thống có throughput cao nhưng bỏ mất event hoặc xử lý trùng gây hậu quả nghiệp vụ vẫn không đạt.

## 5. Dữ liệu đại diện là gì?

“Đại diện” không có nghĩa lấy vài JSON giống nhau rồi gửi thật nhanh. Dataset phải tái hiện **phân bố** của những yếu tố ảnh hưởng đến chi phí xử lý.

| Chiều dữ liệu | Ví dụ phân bố cần mô phỏng | Tác động |
|---|---|---|
| Kích thước payload | Phần lớn 1–4 KiB, một ít 32–256 KiB | Serialization, network, bộ nhớ, GC |
| Số field/độ sâu JSON | Record ngắn, record nhiều item lồng nhau | Parse và validation CPU |
| Message key | 80% traffic từ 5% khách hàng | Hot partition, thứ tự, skew |
| Schema version | Mới, phiên bản cũ còn tương thích, lỗi không tương thích | Conversion, compatibility |
| Loại sự kiện | Created, Updated, Cancelled, Refunded | Nhiều nhánh nghiệp vụ |
| Thứ tự event | Đúng thứ tự, đến muộn, trùng, đảo thứ tự | State, idempotency |
| Cardinality | Nhiều ID khác nhau, một số key lặp rất nhiều | Cache hit/miss, state store |
| Tham chiếu nghiệp vụ | Khách hàng tồn tại hoặc thiếu thông tin | DB lookup, exception |
| Timestamps | Event-time gần hiện tại và event-time cũ | Window, lateness, replay |

Phân bố nên lấy từ thống kê thực tế đã được tổng hợp và loại bỏ thông tin nhạy cảm, ví dụ histogram payload size, tỉ lệ loại event, key skew và tỉ lệ lỗi. Không cần sao chép dữ liệu khách hàng thật sang môi trường test.

## 6. Dữ liệu sạch, bất thường và sai hỏng

Tạo tập dữ liệu gồm ba nhóm:

1. **Hợp lệ phổ biến:** đúng schema, payload nhỏ, key tồn tại, thứ tự bình thường.
2. **Hợp lệ nhưng tốn tài nguyên:** payload lớn, nhiều item, key nóng, schema version cũ được hỗ trợ, event trễ.
3. **Không hợp lệ hoặc gây lỗi có chủ đích:** JSON lỗi, field bắt buộc thiếu, schema không tương thích, dữ liệu nghiệp vụ vô lý, downstream trả timeout hoặc 503.

Tỉ lệ pha trộn ví dụ cho 100.000 message:

| Nhóm không trùng nhau | Tỉ lệ | Số message |
|---|---:|---:|
| Hợp lệ thông thường | 96% | 96.000 |
| Hợp lệ nhưng payload lớn/hot workload | 2% | 2.000 |
| Hợp lệ theo schema cũ còn hỗ trợ | 0,5% | 500 |
| Payload sai định dạng hoặc thiếu trường bắt buộc | 0,5% | 500 |
| Hợp lệ nhưng gặp lỗi downstream tạm thời | 0,7% | 700 |
| Lỗi nghiệp vụ không thể retry | 0,3% | 300 |
| **Tổng** | **100%** | **100.000** |

Đây là một **mix thí nghiệm**, không đại diện mặc định cho mọi sản phẩm. Tỉ lệ có thể tách thành các scenario riêng để dễ xác định tác động của mỗi loại. Tránh thay đổi đồng thời key skew, kích thước payload và fault rate trong một thử nghiệm duy nhất mà không có baseline đối chiếu.

## 7. Sinh dữ liệu tái lập được và bảo vệ quyền riêng tư

Thay vì dùng đơn hàng thật, tạo dữ liệu tổng hợp có quan hệ nhất quán: customerId, orderId, eventId, amount, lineItems và occurredAt. Dùng seed cố định để tạo lại cùng một phân bố; event ID riêng giúp đối soát đầu vào/đầu ra.

Ví dụ payload hợp lệ:

~~~json
{
  "eventId": "evt-000042",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "orderId": "ord-000042",
  "customerId": "customer-003",
  "occurredAt": "2026-11-20T08:00:00Z",
  "amountCents": 245000,
  "items": [
    {"sku": "sku-12", "quantity": 2, "priceCents": 122500}
  ]
}
~~~

Ví dụ payload cố ý sai ở lớp JSON:

~~~text
{"eventId":"evt-bad-003","eventType":"ORDER_CREATED","amountCents":
~~~

Nếu ứng dụng consume POJO và framework tự serialize message, bạn có thể **không tạo được JSON sai** qua producer đó. Cần một raw producer/test harness chủ động gửi bytes sai vào topic/queue của môi trường test. Tách luồng phát dữ liệu hỏng khỏi producer sinh dữ liệu hợp lệ để không làm méo tỉ lệ lỗi.

Không dùng email, số điện thoại, token, địa chỉ hoặc ID thật. Nếu dữ liệu phải được lấy từ bản ghi production, thực hiện masking/ẩn danh trước khi đưa vào test, và kiểm tra rằng khóa hoặc thống kê vẫn có ý nghĩa cho mục tiêu tải.

## 8. Thiết kế phân bố key và mô phỏng hot partition

Kafka thường định tuyến message đến partition theo key; một key ổn định thường đi cùng một partition trong thời gian partition count và thuật toán routing không đổi. Với yêu cầu thứ tự theo đơn hàng, việc giữ cùng orderId làm key là quan trọng.

Nhưng phân bố key đồng đều giả tạo có thể làm kết quả tải tốt hơn thực tế. Một số tài khoản lớn hoặc thiết bị nhiều hoạt động có thể tạo phần lớn message. Thí nghiệm nên có cả:

- **Đồng đều:** nhiều key với lưu lượng tương đương để đo năng lực tối đa khi chia tải tốt.
- **Skew vừa:** nhóm nhỏ key tạo đa số message để quan sát lag theo partition.
- **Hot key cực đoan:** một key tạo phần lớn lưu lượng để xác định giới hạn xử lý tuần tự.
- **Key cardinality cao:** phần lớn message có key mới để quan sát state store/cache và chi phí lookup.

Ví dụ mô phỏng 100 khách hàng, 80% traffic chọn trong 5 customerId, 20% traffic chọn trong 95 customerId còn lại. Phân bố này không có nghĩa mỗi hot key bằng nhau trong production; điều chỉnh theo histogram thực tế.

Chỉ số aggregate consumer lag có thể che khuất một partition bị nghẽn. Đo lag và tốc độ xử lý theo partition/key range, cùng độ trễ của event thuộc hot key. Với RabbitMQ, đo queue và độ cạnh tranh của consumer; với Pulsar Key_Shared, xem phân bố key và consumer assignment.

## 9. Kích thước payload và chi phí thực tế

Giả sử tải đầu vào là 1.200 message/giây, kích thước payload trung bình 3 KiB:

~~~text
payload throughput = 1,200 × 3 KiB/s
                   = 3,600 KiB/s
                   ≈ 3.52 MiB/s
~~~

Đây chỉ là phần payload được gửi, chưa bao gồm header, record metadata, TLS, batching, replication, log segment, index, protocol overhead và output hoặc retry sinh thêm. Payload trung bình cũng che khuất tail latency: vài message 256 KiB có thể gây memory pressure hoặc deserialization pause.

Hãy đo histogram kích thước thực tế, số lần serialize/deserialize và độ trễ theo bucket kích thước. Đừng chỉ tăng message rate rồi gọi đó là stress test; nếu payload rất nhỏ, bạn có thể đang đo bottleneck không giống workload thật.

## 10. Phân biệt open-loop và closed-loop workload

Trong **open-loop load model**, generator tạo event theo lịch đến đã định, ví dụ 1.000 message/giây, độc lập với tốc độ xử lý ở downstream. Mô hình này hữu ích để quan sát backlog tăng khi service không theo kịp.

Trong **closed-loop model**, generator chỉ tạo request mới khi số lượng request đang bay giảm hoặc request trước hoàn tất. Mô hình này thường thấy trong benchmark đồng thời của API, nhưng có thể tự giảm tốc khi service chậm, khiến hệ thống trông ổn hơn thực tế.

Với ứng dụng hướng sự kiện, một arrival-rate model cố định hoặc dựa trên phân bố của production thường phản ánh sự kiện được phát từ bên ngoài tốt hơn. Chọn rõ:

- Tốc độ mục tiêu và biến thiên theo thời gian.
- Số producer, số connection và phân bố key.
- Số message được xác nhận publish thành công.
- Tỉ lệ lỗi của chính load generator.
- Chính sách xử lý khi generator không giữ được tốc độ.

Nếu generator bị nghẽn CPU hoặc broker từ chối publish, đồ thị target rate không bằng offered load thực tế. Phải đo số message thực sự được broker chấp nhận, không chỉ số lần generator dự định gửi.

## 11. Các dạng tải nên có trong kế hoạch

| Dạng tải | Mô tả | Câu hỏi cần trả lời |
|---|---|---|
| Baseline | Tải thấp, không fault | Hệ thống hoạt động đúng với cấu hình chuẩn? |
| Ramp-up | Tăng dần 25% → 50% → 100% | Điểm nào throughput bắt đầu không theo kịp? |
| Steady-state | Duy trì tải thông thường đủ lâu | Lag có ổn định? Memory có tăng liên tục? |
| Peak / burst | Tăng lên 150–250% trong thời gian ngắn | Backlog tăng bao nhiêu và có phục hồi không? |
| Soak | Tải ổn định nhiều giờ | Memory leak, resource exhaustion, log growth? |
| Recovery | Hạ tải sau spike hoặc khôi phục dependency | Mất bao lâu để xử lý hết backlog? |
| Fault under load | Broker hoặc downstream lỗi khi đang tải | Retry/DLQ, duplicate, loss và degraded SLO? |

Không cần chạy tất cả trong một lần. Chạy baseline và scenario đơn biến trước, sau đó kiểm thử kết hợp khi đã có số liệu nền. Soak test phải đủ dài để quan sát memory, GC, connection leak và việc rotate các file log.

## 12. Ma trận kịch bản tải cụ thể

Một ma trận thí nghiệm minh họa cho service có mức tải chuẩn 1.000 message/giây:

| Mã | Tải và thời gian | Dữ liệu | Lỗi đưa vào | Kết quả cần quan sát |
|---|---|---|---|---|
| T01 | 200/s trong 10 phút | 100% valid, key đều | Không | Baseline latency, overhead |
| T02 | 1.000/s trong 30 phút | Mix đại diện | Lỗi tự nhiên của mix | SLO, lag ổn định, DLQ đúng |
| T03 | Tăng 500 → 1.500/s trong 15 phút | Mix đại diện | Không fault hạ tầng | Điểm bão hòa, p99 |
| T04 | 2.000/s trong 5 phút rồi 800/s | Mix đại diện | Không | Backlog và drain time |
| T05 | 1.000/s trong 20 phút | 80% traffic vào 5% key | Không | Hot partition lag |
| T06 | 1.000/s trong 20 phút | Payload lớn 5% | Không | CPU, heap, GC, p99 |
| T07 | 1.000/s trong 20 phút | Mix đại diện | 10% downstream 503 trong 3 phút | Retry amplification, recovery |
| T08 | 1.000/s trong 20 phút | Mix đại diện | Dừng một consumer replica | Rebalance/redelivery |
| T09 | 1.000/s trong 20 phút | Mix đại diện | Broker/network gián đoạn có kiểm soát | Publish/consume recovery |
| T10 | 1.000/s trong 20 phút | Mix đại diện | Poison messages và DLQ | Số lần retry, không kẹt luồng |

Các tốc độ, thời gian và tỷ lệ trên là **ví dụ để xây dựng plan**, chưa phải khuyến nghị cho mọi môi trường. Mỗi scenario cần gắn với năng lực hạ tầng, SLO và quy trình rollback; chỉ chạy fault injection trong môi trường test được kiểm soát.

## 13. Phân loại lỗi theo khả năng retry

Không phải mọi exception đều nên retry như nhau:

| Nhóm lỗi | Ví dụ | Hướng xử lý điển hình |
|---|---|---|
| Payload không parse được | JSON sai, dữ liệu bytes lỗi | Non-retryable; chuyển DLQ hoặc reject theo policy |
| Schema không tương thích | Thiếu field bắt buộc, enum lạ | Kiểm tra version; DLQ khi không phục hồi được |
| Validation nghiệp vụ | Số lượng âm, đơn hàng không tồn tại | Non-retryable hoặc business reject |
| Downstream tạm thời | HTTP 503, 429, connection reset | Retry có giới hạn và backoff |
| Hết tài nguyên | Thread pool, connection pool, disk đầy | Tạm giảm tải, retry/backpressure có kiểm soát |
| Broker gián đoạn | Partition leader change, network timeout | Client reconnect/retry theo binder/broker |
| Xử lý trùng | Message redelivery sau ack failure | Idempotency/deduplication |

Một poison message bị retry vô hạn có thể chặn partition hoặc gây tải lỗi lớn dù message rate đầu vào nhỏ. Thiết kế đủ message sai để đo khả năng cô lập lỗi, nhưng không dùng message sai ngoài ý muốn đến hạ tầng production.

## 14. Retry amplification và DLQ phải được đo

Giả sử 100 message bị lỗi transient và mỗi message được xử lý tối đa 3 lần, tổng số **lượt xử lý** có thể đạt 300. Tốc độ publish đầu vào không đổi, nhưng request tới database hoặc API downstream có thể tăng đáng kể.

~~~text
processing attempts ≈ original messages × average attempts
~~~

Công thức chỉ là ước lượng; tổng tải thực tế còn phụ thuộc delay/backoff, thời điểm lỗi, concurrency và việc retry có phát message mới hay không.

Trong mỗi test lỗi, ghi:

- Số message đầu vào ban đầu và số lượt xử lý.
- Số retry, redelivery, backoff và retry attempts phân bố theo loại lỗi.
- Số message vượt giới hạn retry.
- Số message đến DLQ và số message DLQ publish thất bại.
- Số message thành công sau retry.
- Độ trễ từ lần nhận đầu tới trạng thái cuối cùng.
- Số side effect trùng mà idempotency đã ngăn được.

Lỗi không thể retry phải được phân loại sớm. Khi DLQ lỗi hoặc không được cấp ACL publish, hệ thống có thể giữ message lỗi hoặc xử lý lặp; đó là một scenario riêng cần kiểm tra.

## 15. Thứ tự, duplicate và idempotency dưới tải

Kafka và nhiều binder chỉ bảo đảm thứ tự trong phạm vi phù hợp như partition, không có thứ tự toàn cục qua mọi partition. Với RabbitMQ Shared consumers hoặc Pulsar Shared subscription, nhiều consumer có thể xử lý song song và hoàn tất khác thứ tự nhận.

Trong test, tạo rõ ba nhóm:

1. Event hợp lệ theo thứ tự: CREATED → CONFIRMED → SHIPPED cho cùng orderId.
2. Event đến muộn: SHIPPED đến trước CONFIRMED do upstream hoặc replay.
3. Event trùng: cùng eventId được gửi lại do redelivery/restart.

Yêu cầu cần xác minh là **trạng thái nghiệp vụ đúng**, ví dụ một đơn hàng chỉ ghi nhận một lần thanh toán, chứ không chỉ là số callback chạy. Lưu eventId và result ID để đối soát; với event trùng, đếm xử lý lại và side effect thực tế riêng biệt.

Không kết luận rằng bật transaction Kafka tự cung cấp exactly-once cho database, HTTP hoặc một broker khác. Khi có side effect ngoài Kafka, cần cơ chế idempotency/outbox/inbox hoặc transaction phù hợp.

## 16. Consumer group, partition và concurrency

Tốc độ xử lý phụ thuộc số partition, số consumer trong group và khả năng xử lý của downstream:

- Với Kafka, một partition trong một group thường chỉ được gán cho một consumer tại một thời điểm. Tăng replica vượt số partition không tự tăng song song cho phần dữ liệu đó.
- Một key nóng tập trung vào một partition có thể tạo lag cao dù các partition khác rảnh.
- Với RabbitMQ, nhiều consumer chia tải qua queue nhưng thứ tự và prefetch ảnh hưởng hành vi phân phối.
- Với Pulsar, Exclusive, Failover, Shared và Key_Shared có semantics phân phối và ordering khác nhau; cần cấu hình đúng theo bài toán.
- Với Kafka Streams state store, xử lý có state có chi phí restore/rebalance và changelog; bài test cần bao gồm giai đoạn hồi phục trạng thái.

Giữ cố định số partition và consumer replica trong baseline, rồi thử từng tổ hợp có chủ đích. Không thay cả số partition, concurrency, batch size và payload cùng lúc nếu muốn xác định nguyên nhân.

## 17. Đo lag, backlog và khả năng bắt kịp

Message throughput chỉ đo tốc độ hệ thống di chuyển dữ liệu. Khi ingestion lớn hơn processing, message tích lũy thành backlog.

Ví dụ trong 60 giây:

~~~text
incoming = 1,400 messages/s
completed = 1,000 messages/s
backlog increase ≈ (1,400 - 1,000) × 60 = 24,000 messages
~~~

Giả sử sau spike, ingress giảm còn 800/s và consumer vẫn xử lý 1.000/s, tốc độ xóa backlog lý thuyết là 200/s:

~~~text
drain time ≈ 24,000 / (1,000 - 800) = 120 s
~~~

Đây là mô hình đơn giản, giả định tốc độ xử lý ổn định và không có retry thêm. Thực tế còn phụ thuộc key skew, batch, payload, broker I/O và downstream.

Với Kafka đo consumer lag theo topic-partition/group và tuổi message; với RabbitMQ đo ready/unacked messages, queue depth và consumer count; với Pulsar đo backlog, unacked, redelivery và subscription consumer state. **Backlog age** thường quan trọng hơn chỉ đếm số lượng message.

## 18. Chỉ số phải thu thập từ cả ứng dụng lẫn broker

| Lớp | Chỉ số chính | Dấu hiệu bất thường |
|---|---|---|
| Generator | Intended rate, actual acknowledged rate, send error | Generator không đạt tốc độ mục tiêu |
| Producer | Send latency, batch size, retries, publish error | Broker hoặc network nghẽn |
| Consumer | Processed/s, handler latency, active consumers | Throughput dừng tăng khi tăng replica |
| Broker | Lag/backlog, broker CPU, disk I/O, throttling | Queue tích lũy hoặc broker quá tải |
| JVM | CPU, heap, allocation rate, GC pause, threads | Payload lớn gây pause, memory pressure |
| Dependency | DB pool wait, HTTP p95/p99, 429/503 | Downstream thành nút thắt |
| Reliability | Retry, redelivery, DLQ, duplicates, missing IDs | Lỗi bị nhân tải hoặc mất dấu |
| Recovery | Restore/rebalance duration, backlog drain time | Không hồi phục trong RTO |

Spring Boot Actuator và Micrometer có thể cung cấp metrics của JVM, ứng dụng và một số binder; exporter/broker metrics cần được cấu hình tương ứng. Không giả định mọi binder có bộ metric hoặc tên metric giống nhau.

## 19. Tính latency và xử lý sai lệch đồng hồ

Nếu generator ghi timestamp ở máy A và verifier ghi timestamp ở máy B, độ lệch đồng hồ có thể tạo latency âm hoặc sai p99. Dùng cơ chế đồng bộ đồng hồ thích hợp và theo dõi clock skew giữa node.

Giải pháp:

- Đo processing latency trong cùng process bằng đồng hồ đơn điệu nếu có thể.
- Đo end-to-end bằng timestamp UTC được đồng bộ và ghi rõ sai số.
- Gắn eventId/correlationId trong header hoặc envelope, tránh dùng customerId làm nhãn metric có cardinality cao.
- Đo percentile trên từng khoảng thời gian và xem histogram tail, không chỉ average.
- Chỉ so sánh latency giữa hai run khi cùng định nghĩa điểm bắt đầu/kết thúc.

Đừng lấy timestamp nghiệp vụ occurredAt cũ làm thời điểm ingress để đo latency xử lý mới: event có thể được phát trễ hoặc replay. Cần phân biệt event-time, publish-time và processing-time.

## 20. Tránh metric cardinality cao

Gắn eventId hoặc orderId trực tiếp làm tag Prometheus/Micrometer có thể sinh hàng triệu time series và gây thêm tải lên hệ thống quan sát. Thay vào đó:

- Metric labels chỉ gồm broker, binding, outcome, exception category hoặc scenario có tập giá trị nhỏ.
- eventId và correlationId được ghi trong structured log hoặc distributed tracing có sampling.
- DLQ report lưu ID và lỗi chi tiết cho phép đối soát.
- Chỉ số theo partition/key range được giới hạn theo quy mô hạ tầng, tránh tag mọi customerId.

Hệ thống đo lường cũng tiêu tốn CPU, RAM và I/O. Dùng cùng cấu hình sampling giữa các lần benchmark hoặc ghi lại khác biệt để tránh kết luận sai.

## 21. Fault injection có kiểm soát

Chỉ đưa lỗi vào môi trường test được phép, có phạm vi và thời gian xác định. Mỗi fault cần có trigger, cách xác nhận lỗi đã xảy ra, điều kiện ngừng và cách phục hồi.

| Fault | Cách thử trong môi trường cô lập | Điều cần quan sát |
|---|---|---|
| Downstream chậm | Thêm latency cố định/ngẫu nhiên cho API mock | Queue wait, timeout, backlog, p99 |
| Downstream trả 503 | Mock trả 503 theo tỉ lệ trong thời gian ngắn | Retry rate và backoff |
| Broker ngắt kết nối | Tạm ngắt một endpoint/test broker | Reconnect, publish/consume lỗi |
| Consumer mất một replica | Dừng một process/pod thử nghiệm | Rebalance, redelivery, recovery |
| DLQ không ghi được | Chặn ACL hoặc mô phỏng publish failure trong test | Phát hiện và cảnh báo DLQ failure |
| Schema sai | Gửi raw bytes hoặc version không được hỗ trợ | Phân loại non-retryable |
| Hot key | Tăng traffic vào một key/range | Partition lag và công bằng giữa key |
| Disk/DB chậm | Giới hạn throughput của dependency test | Thread pool, connection pool, lag |

Chạy một fault mỗi lần ở baseline để biết tác động riêng, sau đó mới kết hợp những fault có khả năng cùng xuất hiện. Đừng inject lỗi mà không có quan sát để xác nhận lỗi thực sự đến được thành phần mong muốn.

## 22. Thiết kế test harness tối giản

Load generator nên nằm ngoài service cần đo để tránh dùng chung CPU và heap với consumer. Nó cần kiểm soát chính xác event rate, key distribution, payload mix và fault profile.

Một manifest mô tả scenario, không phải cấu hình Spring Cloud Stream có thể chạy trực tiếp:

~~~yaml
scenario: orders-steady-with-faults
seed: 42
arrival:
  mode: fixed-rate
  targetMessagesPerSecond: 1000
  durationSeconds: 1200
data:
  populationSize: 100
  hotKeyCount: 5
  hotTrafficPercent: 80
  largePayloadPercent: 2
faults:
  malformedPayloadPercent: 0.5
  oldCompatibleSchemaPercent: 0.5
  downstreamTransientPercent: 0.7
  businessRejectPercent: 0.3
validation:
  requireEventId: true
  capturePublishAcknowledgement: true
  reconcileFinalOutcomes: true
~~~

Vì một event có thể thuộc nhiều thuộc tính (vừa có hot key vừa có payload lớn), cần phân biệt rõ các tỉ lệ **độc lập** theo chiều dữ liệu và các tỉ lệ **nhóm lỗi loại trừ nhau**. Manifest trên minh họa nhiều chiều; khi triển khai generator, xác định quy tắc chọn nhóm trước, sau đó áp dụng key và size để không đếm một event thành nhiều lỗi độc lập ngoài ý định.

Generator phải tự đo CPU, RAM, pending sends và publish failures. Nếu bản thân generator đạt giới hạn trước broker, kết quả không đại diện cho năng lực của service.

## 23. Ví dụ Java tạo key skew tái lập được

Đoạn code sau chỉ sinh fixture, chưa gửi message. Chạy trong một luồng để chuỗi sinh bằng seed cố định có thể lặp lại. Giả sử có 100 khách hàng, 5 khách hàng nóng chiếm khoảng 80% sự kiện:

~~~java
import java.time.Instant;
import java.util.Random;

record LoadEvent(
    String eventId,
    String customerId,
    int schemaVersion,
    Instant occurredAt,
    long amountCents
) {}

final class LoadEventFactory {
    private final Random random = new Random(42L);

    LoadEvent next(long index) {
        boolean hot = random.nextDouble() < 0.80;
        int customerNumber = hot
            ? random.nextInt(5)
            : 5 + random.nextInt(95);

        return new LoadEvent(
            "evt-" + index,
            "customer-" + customerNumber,
            2,
            Instant.parse("2026-11-20T08:00:00Z").plusMillis(index * 100),
            10_000L + random.nextInt(500_000)
        );
    }
}
~~~

Thực tế cần bổ sung loại event, số item, schema version cũ, size bucket, late event và nhóm lỗi theo thiết kế. Sử dụng key thật khi publish lên Kafka/Pulsar và xác minh routing; chỉ có trường customerId trong JSON không đảm bảo broker lấy trường đó làm partition key.

Nếu chạy generator đa luồng, không chia sẻ một Random có trạng thái để kỳ vọng cùng thứ tự kết quả qua mọi lần chạy. Có thể chia workload thành từng shard cố định với seed riêng, hoặc sinh dataset trước rồi phát lại theo lịch rõ ràng.

## 24. Binding và binder của ứng dụng trong môi trường tải

Ví dụ luồng Spring Cloud Stream với Function nhận event từ Kafka và phát event đã xác nhận. Cấu hình tối giản:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: loadtest.orders.input
          group: loadtest-order-processor
        acceptOrder-out-0:
          destination: loadtest.orders.output
      kafka:
        binder:
          brokers: ${LOADTEST_KAFKA_BROKERS}
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Provision topic, partition, ACL, retry và DLQ trước theo kịch bản; không tự động tạo tài nguyên production. Với nhiều binder, khai báo rõ binder cho từng binding. Nếu dùng RabbitMQ/Pulsar, thay binder configuration và đo các chỉ số backlog/ack phù hợp với broker đó.

Cấu hình trong đoạn code là một phần môi trường test minh họa; nó **không tự cấu hình retry/DLQ hoặc fault injection**. Những tính năng đó cần cấu hình binder tương ứng và phải được xác minh với phiên bản thực tế trước khi kết luận.

## 25. Dựng verifier để đối soát mọi event ID

Không kết luận hoàn thành chỉ dựa trên số lượng output. Tạo verifier thu thập kết quả theo eventId và trạng thái:

~~~text
INPUT_ACCEPTED
  ├── BUSINESS_SUCCESS
  ├── BUSINESS_REJECTED
  ├── DLQ_RECORDED
  └── STILL_PENDING_OR_UNKNOWN
~~~

Với message đầu vào được broker xác nhận, verifier nên biết event đang ở trạng thái nào tại thời điểm kết thúc test. Sau khi chờ đến deadline phục hồi, phải đối soát:

~~~text
accepted input IDs
  = unique successful IDs
  + unique rejected IDs
  + unique DLQ IDs
  + unique pending/unknown IDs
~~~

Nếu cùng ID xuất hiện ở nhiều nhóm, đó là dấu hiệu cần điều tra về duplicate outcome hoặc semantics nghiệp vụ; không cộng trùng vào tổng. Đếm riêng số lần giao lại và số side effect đã thực hiện.

Pending/unknown không được âm thầm xem là thành công. Một test có thể kết thúc khi còn backlog hợp lệ, nhưng kết luận cần ghi rõ số lượng và tuổi của chúng cùng thời hạn đánh giá.

## 26. Tiến trình thực hiện một vòng kiểm thử tải

1. Xác định topology, binder version, instance count, partition/queue và downstream resource.
2. Thống nhất SLO, failure budget, throughput và recovery deadline.
3. Chuẩn bị dataset tổng hợp có seed cố định, event ID và phân bố gần production.
4. Provision topic/queue, consumer group, retry/DLQ và ACL trong môi trường riêng.
5. Kiểm tra generator thực sự đạt target rate ở một bài smoke test nhỏ.
6. Warm-up JVM, connection pools, caches và consumer assignment trước khi đo chính thức.
7. Chạy baseline không fault và lưu số liệu đối chứng.
8. Chạy các scenario tải đã chọn; inject fault theo thời điểm được ghi nhận.
9. Theo dõi cả generator, service, broker, dependency và verifier.
10. Kết thúc fault, đo backlog drain và thời gian phục hồi thực tế.
11. Đối soát event ID, duplicate, retry/DLQ và kết quả nghiệp vụ.
12. Lưu báo cáo gồm cấu hình, seed, dataset profile, thời gian, metric và nguyên nhân thất bại.

Trước mỗi run, xác định rõ việc tái sử dụng consumer group, offset, queue và DLQ. Nếu chạy lại với backlog cũ, hai run có thể không so sánh được; cần reset dữ liệu test có kiểm soát hoặc tạo destination/group riêng theo run ID.

## 27. Mẫu báo cáo kết quả

Một báo cáo kiểm thử tải nên đủ thông tin để người khác lặp lại:

| Trường | Nội dung nên ghi |
|---|---|
| Scenario/run ID | T05-hot-key-2026-11-24 |
| Git revision và phiên bản binder | Revision của ứng dụng và dependency liên quan |
| Hạ tầng | Broker type/version, node size, partition count, replica count |
| Dataset | Seed, tổng ID, histogram size, key skew, schema mix |
| Offered/accepted rate | Mục tiêu và tốc độ broker thực sự nhận |
| Output throughput | Event nghiệp vụ hoàn tất mỗi giây |
| Latency | p50/p95/p99, định nghĩa mốc đo, sample count |
| Backlog/lag | Max, age, tốc độ tăng và drain time |
| Error handling | Retry attempts, redelivery, DLQ, non-retryable |
| Correctness | Missing/duplicate IDs, business rejects |
| Resources | CPU, memory, GC, broker/disk/network, downstream |
| Fault injection | Bắt đầu/kết thúc, target và cách xác nhận |
| Verdict | Pass/fail theo từng SLO và bằng chứng |

Không chỉ ghi trung bình cả run. Đồ thị theo thời gian cần đánh dấu giai đoạn ramp, peak, fault và recovery để biết tail latency thay đổi tại thời điểm nào.

## 28. Đọc kết quả và chọn hành động

| Quan sát | Giải thích có thể | Kiểm tra tiếp |
|---|---|---|
| Lag một partition tăng, các partition khác ổn | Hot key hoặc partition skew | Phân bố key, partition routing, handler trên key nóng |
| CPU cao cùng p99 tăng theo payload | Parse/serialize hoặc allocation pressure | Heap profile, GC, size histogram |
| Throughput không tăng khi thêm replica | Partition limit, DB bottleneck hoặc lock | Consumer assignment, DB pool, downstream |
| Input rate ổn nhưng attempt rate tăng | Retry amplification | Tỉ lệ 503, retry count, backoff |
| DLQ tăng nhưng input không đổi | Schema/validation lỗi hoặc dependency hỏng | DLQ reason, event sample, schema compatibility |
| Lag giảm rất chậm sau khi fault hết | Capacity headroom nhỏ hoặc retry backlog | Net processing rate, max concurrency, pending retries |
| Output count đủ nhưng side effect trùng | Redelivery và thiếu idempotency | Event ID, business transaction, inbox/outbox |
| Generator rate thấp hơn target | Generator/broker publish bottleneck | Producer latency, pending sends, CPU generator |

Chỉ thay một biến cấu hình trong thí nghiệm đối chứng kế tiếp nếu có thể. Ví dụ tăng consumer replica khi bottleneck là CPU application; tăng replica thường không giúp nếu một hot partition bị giới hạn thứ tự hoặc DB pool đã bão hòa.

## 29. Sai lầm thường gặp

- Dùng toàn bộ message giống nhau nên cache hit quá cao, không đại diện production.
- Dùng key ngẫu nhiên hoàn toàn nên không phát hiện hot partition.
- Chỉ đo throughput phát vào broker, bỏ qua throughput xử lý thành công.
- Chỉ chạy vài phút nên không nhìn thấy memory leak, backlog hoặc GC tích lũy.
- Chỉ test luồng hợp lệ, không kiểm tra poison message, retry hoặc DLQ.
- Inject đồng thời quá nhiều lỗi ngay từ đầu nên không xác định được nguyên nhân.
- Dùng dữ liệu production thật mà không xử lý quyền riêng tư.
- Cho phép producer tự giảm tốc khi consumer chậm mà không ghi nhận actual offered rate.
- Dùng Test Binder để suy ra throughput của Kafka/RabbitMQ/Pulsar production.
- Chỉ assert tổng output mà không đối soát event ID và duplicate side effect.
- Bỏ qua thời gian phục hồi khi peak hoặc sự cố đã kết thúc.
- Thay nhiều tham số rồi công bố cải thiện mà không có baseline công bằng.

## 30. Checklist thiết kế kiểm thử tải

- [ ] Có sơ đồ topology, ranh giới phép đo và định nghĩa latency.
- [ ] Có SLO/SLA minh họa rõ cho steady, peak và recovery.
- [ ] Có histogram payload size, loại event, schema version và key distribution.
- [ ] Có seed/dataset ID cố định, không dùng dữ liệu cá nhân thật.
- [ ] Có tỉ lệ message sai và fault profile được ghi lại.
- [ ] Có scenario hot key, payload lớn và duplicate/redelivery.
- [ ] Có baseline, ramp, steady, peak, soak và recovery khi phù hợp.
- [ ] Generator đo được acknowledged send rate và publish failures.
- [ ] Có metric app, broker, dependency, JVM, retry/DLQ và backlog age.
- [ ] Fault injection có trigger, duration, cách khôi phục và nhãn trên đồ thị.
- [ ] Có verifier theo event ID, phân biệt success/reject/DLQ/pending.
- [ ] Có kiểm tra idempotency, side effect duplicate và thứ tự theo yêu cầu nghiệp vụ.
- [ ] Có báo cáo đầy đủ config, version, seed, kết quả và hạn chế ngoại suy.

Thiết kế kiểm thử tải tốt cho Spring Cloud Stream bắt đầu từ **dữ liệu và lỗi gần với thực tế**, sau đó mới chọn tốc độ phát message. Một tập dữ liệu đủ phong phú phải có phân bố key, kích thước payload, schema version, event trễ, duplicate và lỗi nghiệp vụ. Kết quả cần đo end-to-end latency, throughput hoàn tất, lag/backlog, retry/DLQ, mức sử dụng tài nguyên và thời gian phục hồi. Chỉ khi đối soát được toàn bộ event ID và diễn giải được hành vi trong lúc tải cao hoặc gặp lỗi, bài kiểm thử mới cung cấp bằng chứng đáng tin cậy cho quyết định triển khai.

## Tài liệu tham khảo

- [Spring Cloud Stream — Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Apache Pulsar — Monitoring](https://pulsar.apache.org/docs/administration-stats/)

