# Overflow: loại bỏ đầu hàng đợi hoặc từ chối publish theo khả năng queue

Trong RabbitMQ, producer có thể gửi message nhanh hơn tốc độ consumer xử lý. Khi backlog lớn dần, queue tiêu thụ dung lượng lưu trữ, làm tăng độ trễ và khiến các message cũ mất giá trị. **Queue length limit** và **overflow behavior** là những cơ chế giúp RabbitMQ quyết định phải làm gì khi queue đạt giới hạn: **loại bỏ message cũ ở đầu hàng đợi** (`drop-head`) hoặc **từ chối message mới** (`reject-publish`); một số phiên bản/loại queue còn có biến thể `reject-publish-dlx`.

Bài này thuộc chương **Chính sách hàng đợi** trong module **SPRING_AMQP**. Sau khi biết dùng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding, bạn cần hiểu overflow để thiết kế định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và giám sát hệ thống xử lý bất đồng bộ đáng tin cậy. Overflow là quyết định về **giữ hay từ chối message khi queue đầy**, không thay thế cơ chế retry hay acknowledgement của consumer.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt giới hạn số message `max-length` với giới hạn dung lượng body `max-length-bytes`.
2. Dự đoán queue giữ message nào khi dùng `drop-head`, và publisher nhận tín hiệu gì khi dùng `reject-publish`.
3. Phân biệt message bị loại do overflow, bị từ chối publish, hết TTL, bị dead-letter và message không định tuyến được.
4. Cấu hình queue limits bằng RabbitMQ policy hoặc queue arguments qua Spring AMQP; biết những khác biệt khi thay đổi cấu hình trên tài nguyên đã tồn tại.
5. Quan sát publisher confirms, queue depth và DLQ; chọn hành vi overflow theo yêu cầu nghiệp vụ và khả năng của **đúng loại queue/phiên bản RabbitMQ**.

## 2. Vì sao queue có thể đầy?

RabbitMQ lưu message trong queue để tách tốc độ producer và consumer:

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate<br/>150 msg/s"] --> E["Exchange"]
    E --> Q["Queue<br/>Giới hạn 1.000 message"]
    Q --> C["Consumer<br/>@RabbitListener<br/>60 msg/s"]
    Q -.-> O{"Backlog tăng<br/>đến giới hạn"}
    O --> A["drop-head:<br/>loại message cũ"]
    O --> B["reject-publish:<br/>từ chối message mới"]
~~~

Nếu producer gửi 150 message/giây và consumer hoàn tất 60 message/giây, backlog có thể tăng xấp xỉ 90 message/giây, trước khi xét các yếu tố như prefetch, thời gian retry và các consumer khác. Không có giới hạn, queue có thể tăng rất lớn dù hệ thống không bị lỗi tức thời.

Một giới hạn **không làm consumer xử lý nhanh hơn**. Nó chỉ xác định cách broker phản ứng khi backlog vượt ngưỡng. Để giải quyết tận gốc, vẫn cần đo throughput, xử lý bottleneck, tăng/giảm concurrency hợp lý, điều tiết producer và xây chính sách xử lý lỗi.

### Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Ready messages** | Message đang chờ được giao từ queue |
| **Unacknowledged messages** | Message đã giao cho consumer nhưng chưa được xác nhận |
| **Queue length limit** | Ngưỡng giới hạn số message đang được queue giữ theo cách tính của broker |
| **Queue size limit** | Ngưỡng dung lượng body của các message trong phạm vi giới hạn queue |
| **Overflow behavior** | Hành động khi queue chạm giới hạn: drop cũ hoặc reject mới |
| **Dead-letter exchange (DLX)** | Exchange có thể tiếp nhận message bị dead-letter do một số điều kiện queue |
| **Publisher confirm** | Tín hiệu broker báo kết quả xử lý publish cho producer; độc lập với consumer acknowledgement |

Trong các tài liệu RabbitMQ về length limit, **các message đang unacknowledged không được tính như những message đang chờ trong queue** khi đánh giá giới hạn độ dài. Cách hiển thị `messages_ready`, `messages_unacknowledged` và `messages` trong công cụ quản trị cần được đọc đúng. Đừng dùng một con số “tổng message” không rõ định nghĩa để suy ra queue đã hoặc chưa chạm ngưỡng.

## 3. Hai loại giới hạn: số lượng và dung lượng

RabbitMQ thường cung cấp các tham số sau cho queue phù hợp:

| Thuộc tính policy | Đối số lúc khai báo queue | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `max-length` | `x-max-length` | `1000` | Giới hạn theo số lượng message |
| `max-length-bytes` | `x-max-length-bytes` | `10485760` | Giới hạn tổng kích thước body message bằng byte |
| `overflow` | `x-overflow` | `drop-head` | Chọn cách ứng xử khi một giới hạn bị vượt |

Nếu đặt **cả `max-length` và `max-length-bytes`**, điều kiện nào đạt trước có thể kích hoạt overflow. Ví dụ, queue giới hạn 1.000 message và 10 MiB body: 200 message lớn có thể chạm giới hạn byte trước 1.000 message, trong khi nhiều message nhỏ có thể chạm giới hạn số lượng trước.

`max-length-bytes` dựa trên tổng dung lượng **message bodies** theo cách broker tính, không tương đương chính xác mức RAM/disk mà cả queue tiêu thụ, vì còn metadata, index, replication và những chi phí nội bộ khác. Không dùng `max-length-bytes` như giới hạn cứng về tổng tài nguyên máy chủ.

**Các ngưỡng không nhất thiết là giới hạn tuyệt đối tại từng thời điểm quan sát.** Với publish đồng thời, cơ chế nhận message bất đồng bộ và các đặc tính của loại queue, RabbitMQ có thể vượt ngưỡng tạm thời trước khi áp dụng overflow. Hãy xem chúng là công cụ điều tiết backlog có kiểm soát, không phải cam kết chính xác tới từng byte/message trong mọi tình huống.

## 4. drop-head: ưu tiên giữ message mới

`drop-head` là hành vi overflow phổ biến và thường là mặc định cho queue hỗ trợ length limit. Khi cần có chỗ cho message mới, broker **loại bỏ một hoặc nhiều message đang chờ ở đầu queue** để nhường chỗ. Đây thường là các message cũ nhất còn ở trạng thái chờ, nhưng đừng suy ra thứ tự tuyệt đối từ mô tả này nếu queue đang dùng priority, requeue hoặc những hành vi đặc thù.

### 4.1. Ví dụ có thứ tự

Giả sử một queue FIFO đơn giản, không có consumer, không bật priority, giới hạn `max-length = 5`, `overflow = drop-head`:

| Bước | Producer gửi | Queue sau bước đó | Message bị loại |
|---|---|---|---|
| 1 | M1 | M1 | — |
| 2 | M2 | M1, M2 | — |
| 3 | M3 | M1, M2, M3 | — |
| 4 | M4 | M1, M2, M3, M4 | — |
| 5 | M5 | M1, M2, M3, M4, M5 | — |
| 6 | M6 | M2, M3, M4, M5, M6 | **M1** |
| 7 | M7 | M3, M4, M5, M6, M7 | **M2** |

~~~mermaid
flowchart LR
    A["Queue đầy<br/>M1 · M2 · M3 · M4 · M5"]
    N["Publish M6"] --> A
    A --> D["Loại M1<br/>ở đầu queue"]
    D --> K["Queue còn<br/>M2 · M3 · M4 · M5 · M6"]
~~~

Đây là mô hình lý tưởng hóa để giải thích hành vi. Trong chạy thật, một consumer có thể lấy message trước đó, message có thể hết TTL, và một số loại queue có semantics quản lý backlog khác.

### 4.2. Publisher có biết M1 bị loại không?

Không nên dựa vào publisher confirm của **M6** để xác định **M1** đã bị loại. Với `drop-head`, M6 có thể được broker chấp nhận và publisher nhận confirm `ack`, trong khi M1 bị loại khỏi queue. Confirm của M1 nếu đã được gửi trước đó **không bị rút lại** khi message này về sau bị loại.

Do đó:

- `ack=true` của publisher **không đồng nghĩa** “message sẽ còn trong queue cho đến khi được xử lý”.
- Cơ chế drop-head có thể tạo **mất message có chủ đích** theo policy; nó không phù hợp với dữ liệu bắt buộc phải xử lý đầy đủ nếu không có cách khôi phục.
- Việc message bị loại do overflow không phải lỗi `NO_ROUTE`; ban đầu exchange có thể đã route thành công vào queue.

### 4.3. Khi có DLX

Nếu queue cấu hình **dead-letter exchange** và phiên bản/queue type hỗ trợ dead-letter do overflow tương ứng, các message bị loại vì giới hạn có thể được dead-letter thay vì chỉ bị bỏ. Ví dụ M1 được chuyển qua DLX đến queue lưu kiểm tra.

~~~mermaid
flowchart TD
    P["Publish M6"] --> Q["orders.work.q<br/>drop-head, max-length=5"]
    Q -->|"Giữ M6"| C["Message mới chờ xử lý"]
    Q -->|"M1 bị loại khỏi đầu queue"| DLX["orders.dlx"]
    DLX --> DLQ["orders.overflow.dlq"]
~~~

DLX phải tồn tại, có binding phù hợp và quyền cần thiết để định tuyến; cấu hình tên DLX **không tự tạo DLQ**. Tùy loại queue và chiến lược dead-lettering, quá trình chuyển sang DLQ có giới hạn độ tin cậy riêng. Nếu mục tiêu là không mất dữ liệu, phải kiểm tra đường dead-letter và các bảo đảm broker thực tế.

## 5. reject-publish: giữ backlog hiện có và từ chối message mới

Khi `overflow = reject-publish`, queue đạt giới hạn có thể **từ chối các publish mới** thay vì chủ động xóa message cũ trong queue để lấy chỗ. Điều này phù hợp khi dữ liệu đã nhận phải được ưu tiên giữ lại và producer có trách nhiệm giảm tốc độ, báo lỗi hoặc lưu message để thử lại sau.

Vẫn dùng giới hạn `max-length = 5`, không có consumer:

| Bước | Producer gửi | Queue sau bước đó | Kết quả publish |
|---|---|---|---|
| 1–5 | M1…M5 | M1, M2, M3, M4, M5 | Được chấp nhận |
| 6 | M6 | Chủ yếu vẫn giữ M1…M5 | M6 có thể bị broker từ chối |
| 7 | M7 | Chủ yếu vẫn giữ M1…M5 | M7 có thể bị broker từ chối |

Chú ý từ **“có thể”**: length limit và từ chối publish có thể có khoảng vượt ngưỡng trong thực thi thực tế, đặc biệt khi có publish đồng thời. Không viết test dựa trên giả định mọi message thứ `limit + 1` đều luôn bị từ chối đúng thời điểm với mọi queue type và phiên bản.

### 5.1. Tín hiệu cho publisher

Với RabbitMQ hỗ trợ `reject-publish` và **publisher confirms** được bật, broker có thể gửi publisher `basic.nack` cho publish bị từ chối do queue đầy. Trong Spring AMQP, producer nên quan sát confirm callback hoặc cơ chế confirm tương ứng trên `RabbitTemplate`:

~~~text
publish M6 -> exchange đã tìm được binding đến queue
queue từ chối vì overflow = reject-publish
publisher nhận negative confirm (nack) cho publish bị từ chối
~~~

`basic.nack` của **publisher confirm** khác hoàn toàn với `basic.nack` do **consumer** gửi để từ chối một delivery. Cùng tên giao thức nhưng hai luồng tín hiệu có vai trò khác nhau.

Nếu không bật confirms, việc `RabbitTemplate.convertAndSend(...)` chạy hết mà không ném exception tại chỗ **không chứng minh** message đã được queue chấp nhận. Hệ thống cần đưa khả năng publish bị từ chối vào hợp đồng lỗi của producer.

### 5.2. mandatory và basic.return không thay confirms

Một message bị `reject-publish` vẫn đã có đường routing từ exchange đến queue; nó bị từ chối ở bước queue tiếp nhận vì giới hạn. Đây khác với **unroutable** (exchange không tìm được queue). Vì vậy:

- `mandatory=true` và **publisher returns** giúp phát hiện message không định tuyến được theo điều kiện `basic.return`.
- **Publisher confirms** giúp quan sát publish được broker chấp nhận hay bị từ chối, bao gồm trường hợp queue reject do overflow.
- Không dùng một callback return `312 NO_ROUTE` làm tín hiệu chính cho `reject-publish`.

Nếu exchange không tồn tại, broker thường đóng channel với lỗi `404 NOT_FOUND`; đó lại là trường hợp khác, không phải queue overflow.

### 5.3. Một publish có thể route đến nhiều queue

Đây là rủi ro rất quan trọng:

~~~mermaid
flowchart TD
    P["Producer gửi 1 publish"] --> E["Exchange"]
    E -->|"Binding A"| A["queue A<br/>còn chỗ: nhận message"]
    E -->|"Binding B"| B["queue B<br/>đầy: reject-publish"]
    B -.-> N["Publisher có thể nhận nack"]
~~~

Với một publish định tuyến đến nhiều queue, việc **một queue từ chối** không đồng nghĩa RabbitMQ đã rollback những bản message được chấp nhận ở các queue còn lại. Producer có thể thấy negative confirm trong khi queue A đã nhận message. Nếu producer tự gửi lại toàn bộ publish mà không có cơ chế chống trùng, queue A có thể nhận thêm bản sao.

Hệ quả thiết kế: retry ở producer phải có **message ID/idempotency key ổn định**, giới hạn lần gửi lại và đối chiếu trạng thái hệ thống. Không giả định `nack` luôn có nghĩa “không queue nào đã nhận message”.

## 6. So sánh drop-head, reject-publish và reject-publish-dlx

| Tiêu chí | `drop-head` | `reject-publish` | `reject-publish-dlx`* |
|---|---|---|---|
| Khi queue quá giới hạn | Loại message cũ ở đầu queue để có chỗ | Từ chối message publish mới | Từ chối message mới và cố gắng dead-letter message bị từ chối |
| Ưu tiên | Giữ dữ liệu mới | Giữ backlog đã nhận | Giữ backlog và có đường xử lý message mới bị từ chối |
| Phản hồi publisher | Publish mới có thể được confirm `ack` | Publish bị từ chối có thể nhận confirm `nack` | Cần xác minh semantics confirm của bản broker/queue đang dùng |
| Rủi ro chính | Mất message cũ nếu không có DLX/phương án giữ lại | Producer phải xử lý từ chối; retry có thể trùng | Phụ thuộc khả năng dead-letter, topology và queue type |
| Trường hợp phù hợp | Telemetry/live status, dữ liệu cũ nhanh hết giá trị | Task/command cần ưu tiên bảo toàn backlog hiện có | Nhu cầu điều tiết kèm tuyến xử lý message mới nếu được hỗ trợ |

\* **`reject-publish-dlx` không phải lựa chọn có thể mặc định áp dụng cho mọi loại queue và mọi phiên bản RabbitMQ.** Trước khi sử dụng, hãy kiểm tra RabbitMQ documentation của đúng phiên bản, queue type, tính năng dead-letter và kết quả test thực tế. Với hệ thống yêu cầu hỗ trợ rộng hoặc không chắc loại queue, hai mode cần nắm chắc trước tiên là `drop-head` và `reject-publish`.

Lựa chọn nên dựa vào **ý nghĩa message**:

- **Dữ liệu nhanh lỗi thời** như vị trí cảm biến 5 giây một lần hoặc chỉ số UI realtime: giữ phiên bản mới có thể quan trọng hơn giữ mọi trạng thái cũ; `drop-head` đôi khi hợp lý.
- **Lệnh thu tiền, tạo hóa đơn, xác nhận đơn hàng:** loại bỏ message cũ có thể gây sai nghiệp vụ; cần ưu tiên giữ dữ liệu đã nhận, có quy trình xử lý publish bị từ chối và kiểm tra yêu cầu durability.
- **Event tích hợp nhiều subscriber:** một subscriber backlog đầy có thể làm publisher quan sát negative confirm dù subscriber khác nhận message. Cần thiết kế tránh retry mù gây trùng.

Không nên chọn policy chỉ vì nó cho phép queue duy trì dưới một con số. Hãy xác định ai chịu trách nhiệm khi dữ liệu bị loại hoặc publish thất bại trước.

## 7. Khả năng queue type và phiên bản RabbitMQ ảnh hưởng ra sao?

RabbitMQ có nhiều loại queue, phổ biến là **classic queue** và **quorum queue**. Chúng khác nhau về lưu trữ, replication, thứ tự thực tế dưới một số điều kiện, khả năng hỗ trợ và semantics của những tính năng nâng cao.

| Câu hỏi khi cấu hình | Tại sao cần xác minh? |
|---|---|
| Queue là classic hay quorum? | Không thể giả định mọi overflow mode hoạt động giống nhau trên mọi queue type |
| Broker đang chạy phiên bản nào? | Tính năng và giới hạn có thể thay đổi theo release |
| Mode `reject-publish-dlx` có được hỗ trợ không? | Hỗ trợ phụ thuộc loại queue/phiên bản; không nên áp dụng chỉ từ ví dụ online |
| Queue có priority, TTL, DLX hoặc single active consumer không? | Thứ tự và thời điểm message rời queue có thể không giống ví dụ FIFO tối giản |
| Chính sách dead-letter có bảo đảm nào? | Cần đánh giá riêng để tránh kỳ vọng một tuyến DLX tự động đảm bảo không mất dữ liệu |
| Đã có queue cùng tên được khai báo chưa? | Thay đổi client `x-arguments` không mặc nhiên cập nhật được queue cũ |

Với **quorum queue**, một số giới hạn và chế độ overflow có những khác biệt hoặc hạn chế so với classic queue; hãy đọc documentation và changelog của RabbitMQ server đang chạy. Không đưa ra kết luận như “quorum queue luôn cho phép tất cả overflow mode” hoặc “đạt đúng 1.000 message thì mọi publish kế tiếp chắc chắn bị reject”. Với workload quan trọng, phải chạy thử đúng queue type và cấu hình production dự kiến.

Tài liệu tham khảo chính thức cần chọn đúng version:

- [RabbitMQ Queue Length Limits](https://www.rabbitmq.com/docs/maxlength) — limits và overflow.
- [RabbitMQ Policies](https://www.rabbitmq.com/docs/parameters) — policy, operator policy và cách áp dụng.
- [RabbitMQ Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx) — trigger dead-letter, cấu hình và hạn chế.
- [RabbitMQ Publisher Confirms](https://www.rabbitmq.com/docs/confirms) — confirms và consumer acknowledgements.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/) — `RabbitTemplate`, listener và admin/declarations.

Các URL “docs” thường trỏ đến tài liệu hiện hành; nếu hệ thống dùng RabbitMQ/Spring AMQP phiên bản cũ, cần chọn nhánh/version tương ứng và đối chiếu trước khi áp dụng.

## 8. Khai báo overflow bằng RabbitMQ policy

**RabbitMQ policy** là cách thuận tiện để áp dụng một nhóm tham số cho các queue khớp pattern. Ưu điểm là có thể quản lý/điều chỉnh một số tham số vận hành mà không phải sửa mã Java và redeploy consumer.

Ví dụ ở môi trường thử nghiệm, đặt queue name `lab.overflow.q`, số lượng tối đa 5 và mode `drop-head`:

~~~bash
rabbitmqctl set_policy --apply-to queues \
  "lab-drop-head" "^lab\.overflow\.q$" \
  '{"max-length":5,"overflow":"drop-head"}'
~~~

Đổi sang `reject-publish` bằng cách thiết lập một policy tương ứng **sau khi đã xác minh rule precedence và các chính sách đang áp dụng**:

~~~bash
rabbitmqctl set_policy --apply-to queues \
  "lab-reject-publish" "^lab\.overflow\.q$" \
  '{"max-length":5,"overflow":"reject-publish"}'
~~~

Các ví dụ này dùng cú pháp shell kiểu Bash; trong PowerShell/Windows, xử lý quote và backslash phải phù hợp shell. Hãy thực hiện trong virtual host của môi trường thực hành và kiểm tra policy thực tế được áp dụng trong RabbitMQ Management UI. Cần tránh để **hai policy cùng khớp** mà không hiểu priority, vì policy có quy tắc chọn/ưu tiên riêng.

Trong RabbitMQ Management UI, cách làm tương đương là:

1. Mở trang quản lý **Policies** của đúng virtual host.
2. Tạo một policy với pattern khớp chính xác queue thí nghiệm và `Apply to = Queues`.
3. Đặt `max-length = 5` và `overflow = drop-head` hoặc `reject-publish`, tùy lượt thử.
4. Xác nhận trong trang queue rằng policy đang có hiệu lực, thay vì chỉ xem bản ghi policy đã tạo.

### 8.1. Policy và x-arguments: trường nào được ưu tiên?

Client có thể khai báo `x-max-length` và `x-overflow` trực tiếp khi tạo queue. RabbitMQ còn có **regular policy** và **operator policy** để quản trị giới hạn. Khi trùng một thuộc tính, quy tắc ưu tiên phụ thuộc loại policy và tham số:

- Với nhiều tham số, **client-provided x-argument** có độ ưu tiên hơn **regular policy** cho cùng key.
- **Operator policy** có thể đặt giới hạn quản trị, đặc biệt với tham số số; giới hạn thấp hơn thường được chọn khi cần giới hạn chặt.
- Cách kết hợp cụ thể, nhất là với các thuộc tính không phải số, cần kiểm tra theo đúng RabbitMQ version.

Vì vậy, nếu bạn thay `overflow` trong policy nhưng queue thực tế vẫn dùng hành vi cũ, hãy kiểm tra **client arguments**, chính sách đang match, priority và operator policies. Đừng kết luận policy “không hoạt động” chỉ bằng cách nhìn số message còn trong queue.

### 8.2. Tại sao ưu tiên policy cho cấu hình vận hành?

Giá trị ngưỡng cần điều chỉnh theo tải: 5.000 message hôm nay có thể quá thấp hoặc quá cao sau khi tăng consumer. Với regular policy, đội vận hành có thể đổi ngưỡng phù hợp trong môi trường mà queue type/feature hỗ trợ. Nhưng có những thuộc tính không thể đổi trên tài nguyên đã tồn tại hoặc bị giới hạn bởi broker; **policy không biến mọi queue argument thành cấu hình động**.

Nếu đã hard-code `x-max-length` trong annotation hoặc `QueueBuilder`, thay regular policy có thể **không ghi đè** giá trị client. Khi chuyển sang quản lý bằng policy, cần xử lý quy tắc ưu tiên và kế hoạch thay đổi topology đang tồn tại.

## 9. Khai báo queue limit bằng Spring AMQP

Nếu ứng dụng sở hữu topology, có thể đặt queue arguments qua `QueueBuilder`. Ví dụ Spring AMQP với `spring-boot-starter-amqp`:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OverflowLabTopology {

    @Bean
    DirectExchange overflowLabExchange() {
        return new DirectExchange("lab.overflow.x", true, false);
    }

    @Bean
    Queue dropHeadQueue() {
        return QueueBuilder.durable("lab.overflow.drop.q")
                .withArgument("x-max-length", 5)
                .withArgument("x-overflow", "drop-head")
                .build();
    }

    @Bean
    Queue rejectPublishQueue() {
        return QueueBuilder.durable("lab.overflow.reject.q")
                .withArgument("x-max-length", 5)
                .withArgument("x-overflow", "reject-publish")
                .build();
    }

    @Bean
    Binding dropHeadBinding(DirectExchange overflowLabExchange,
                            Queue dropHeadQueue) {
        return BindingBuilder.bind(dropHeadQueue)
                .to(overflowLabExchange)
                .with("drop");
    }

    @Bean
    Binding rejectPublishBinding(DirectExchange overflowLabExchange,
                                 Queue rejectPublishQueue) {
        return BindingBuilder.bind(rejectPublishQueue)
                .to(overflowLabExchange)
                .with("reject");
    }
}
~~~

Giải thích:

- Exchange `lab.overflow.x` là direct exchange.
- Key `drop` route message vào queue `lab.overflow.drop.q`; key `reject` route vào `lab.overflow.reject.q`.
- Hai queue được đặt giới hạn 5 message nhưng có overflow mode khác nhau.
- `x-max-length` phải được truyền dưới dạng số, không phải chuỗi `"5"`; kiểu field-table khác nhau có thể khiến broker từ chối khai báo.
- Các `@Bean` về queue/exchange/binding thường được `RabbitAdmin` khai báo khi cấu hình và quyền broker phù hợp. Nếu resource đã tồn tại với thuộc tính không tương thích, broker có thể báo `PRECONDITION_FAILED`.

**Chỉ dùng code này trong môi trường test** hoặc đổi thành tên resource riêng. Đừng triển khai cùng lúc một queue cũ đã được tạo với arguments khác rồi mong Spring AMQP tự cập nhật mọi thuộc tính.

### 9.1. Cấu hình bằng @Queue trên @RabbitListener

Với những hệ thống muốn đặt topology ngay tại listener, có thể dùng `@Argument`:

~~~java
import org.springframework.amqp.rabbit.annotation.Argument;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WorkConsumer {

    @RabbitListener(bindings = @QueueBinding(
        value = @Queue(
            value = "orders.work.q",
            durable = "true",
            arguments = {
                @Argument(
                    name = "x-max-length",
                    value = "1000",
                    type = "java.lang.Integer"
                ),
                @Argument(
                    name = "x-overflow",
                    value = "reject-publish"
                )
            }
        ),
        exchange = @Exchange(
            value = "orders.work.x",
            type = "direct",
            durable = "true"
        ),
        key = "order.process"
    ))
    public void handle(String payload) {
        // Xử lý nghiệp vụ; cần idempotency nếu có redelivery.
    }
}
~~~

Trong annotation, `@Argument(value = "1000", type = "java.lang.Integer")` chuyển giá trị sang kiểu số mà broker yêu cầu. Tham số `x-overflow` là chuỗi mode. Đặt `x-max-length` tại queue khác với cấu hình `max-length` trong policy; hãy quyết định nguồn quản lý để tránh xung đột.

### 9.2. Chú ý thay đổi queue đang tồn tại

Nếu queue đã được khai báo với một số arguments, việc sửa code rồi restart có thể bị từ chối do **inequivalent arguments**. Để đổi cách quản lý từ x-arguments sang policy, cần xác nhận khả năng cập nhật của từng thuộc tính và chuẩn bị migration phù hợp. Không xóa một durable queue có message chỉ để “cho khai báo lại được”.

## 10. Bật publisher confirms để quan sát reject-publish

Trong Spring Boot có các property phù hợp ở các phiên bản hỗ trợ:

~~~properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
~~~

Trong bài này, **publisher confirms là tín hiệu quan trọng nhất để quan sát `reject-publish`**. Publisher returns và mandatory được bật thêm để tránh nhầm một trường hợp **không có route** với trường hợp **queue từ chối khi đầy**.

Đoạn code minh họa đăng ký callback vào `RabbitTemplate`; connection factory phải thực sự bật publisher confirms và template được publisher sử dụng là template có callback này:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OverflowPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OverflowPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
        this.rabbitTemplate.setConfirmCallback((correlation, ack, cause) -> {
            String id = correlation == null ? "unknown" : correlation.getId();
            System.out.printf(
                    "CONFIRM id=%s ack=%s cause=%s%n", id, ack, cause
            );
        });
        this.rabbitTemplate.setReturnsCallback(returned -> {
            System.err.printf(
                    "RETURN code=%d exchange=%s routingKey=%s%n",
                    returned.getReplyCode(),
                    returned.getExchange(),
                    returned.getRoutingKey()
            );
        });
    }

    public void publish(String routingKey, String messageId) {
        rabbitTemplate.convertAndSend(
                "lab.overflow.x",
                routingKey,
                messageId,
                new CorrelationData(messageId)
        );
    }
}
~~~

Lưu ý triển khai:

- `RabbitTemplate` có callback confirm/returns dùng chung; ví dụ đăng ký trong constructor chỉ để minh họa. Trong ứng dụng thật, nên đặt cấu hình callback tại **một vị trí sở hữu template**, tránh nhiều component ghi đè callback của nhau.
- `CorrelationData(messageId)` giúp liên hệ publisher confirm với lần publish; nó không tự lưu message trong outbox hay tự chống xử lý trùng.
- Callback và kết quả publish là **bất đồng bộ**. Với workflow cần quyết định giao dịch, cần phương án chờ kết quả có timeout hoặc dùng callback quản lý trạng thái dài hạn.
- `ack=true` không bảo đảm consumer hoàn tất nghiệp vụ hoặc message vẫn đang ở queue. `ack=false` không chứng minh mọi queue đích đều không nhận message.
- Nếu cùng template được sử dụng ở những phần ứng dụng khác, tuyệt đối không thay callback mà không quản lý ownership và correlation.

Ví dụ lệnh gửi bảy message vào mỗi queue test (thực hiện khi ứng dụng đã tạo topology và **không có consumer** đang đọc queue):

~~~java
for (int i = 1; i <= 7; i++) {
    publisher.publish("drop", "D" + i);
    publisher.publish("reject", "R" + i);
}
~~~

Vì publishes và confirms là bất đồng bộ, khi kiểm thử phải quan sát đủ thời gian và ghi lại correlation ID; không đọc queue ngay sau vòng lặp rồi coi đó là kết quả cuối cùng.

## 11. Thí nghiệm đối chiếu hai queue

### Chuẩn bị

1. Dùng RabbitMQ riêng cho bài thực hành; xác nhận broker version và queue type. Hai queue trong ví dụ chủ yếu minh họa **classic queue** khi chức năng overflow tương ứng được hỗ trợ.
2. Tạo topology của mục 9 và xác nhận exchange/bindings có trong RabbitMQ Management UI.
3. Không khởi động listener đối với `lab.overflow.drop.q` và `lab.overflow.reject.q`; nếu có consumer, message có thể được lấy ngay và làm sai kết quả kiểm tra backlog.
4. Bật publisher confirms theo cấu hình thực tế của ứng dụng.
5. Gửi chuỗi D1…D7 qua key `drop` và R1…R7 qua key `reject`.

### Kết quả dự đoán trong mô hình đơn giản

| Quan sát | drop-head, max-length 5 | reject-publish, max-length 5 |
|---|---|---|
| Message mới D6/R6 | D6 có thể được nhận để thay thế message cũ | R6 có thể bị từ chối vì queue đầy |
| Backlog khi ổn định | Chủ yếu D3…D7 | Chủ yếu R1…R5 |
| Tín hiệu producer | Những publish mới thường có confirm `ack` | Publish bị từ chối có thể có confirm `nack` |
| Message đầu queue | D1, D2 bị loại theo mô hình FIFO này | R1, R2 được giữ |
| Có `basic.return 312 NO_ROUTE` không? | Không, nếu exchange/binding đúng | Không phải tín hiệu overflow thông thường |

Đây là **kết quả mô phỏng để học khái niệm**, không phải assertion cứng cho mọi broker/version. Nếu quá tải đồng thời, queue type khác, policy khác hoặc consumer vẫn hoạt động, số lượng và trình tự có thể lệch. Hãy đối chiếu cả logs confirm, queue arguments/policy, ready count và danh sách message thực tế.

### Thử tiếp với DLX

Muốn thấy message bị drop-head chuyển sang DLQ, cần cấu hình topology dead-letter bổ sung:

~~~java
@Bean
DirectExchange overflowDlx() {
    return new DirectExchange("lab.overflow.dlx", true, false);
}

@Bean
Queue overflowDlq() {
    return QueueBuilder.durable("lab.overflow.dlq").build();
}

@Bean
Binding overflowDlqBinding(DirectExchange overflowDlx,
                           Queue overflowDlq) {
    return BindingBuilder.bind(overflowDlq)
            .to(overflowDlx)
            .with("drop");
}
~~~

Để hoàn chỉnh ví dụ, queue nguồn `lab.overflow.drop.q` cần được tạo với `x-dead-letter-exchange = "lab.overflow.dlx"` (hoặc policy tương ứng), và quy tắc dead-letter routing key cần trùng binding `drop` nếu không override. Ví dụ:

~~~java
QueueBuilder.durable("lab.overflow.drop.q")
        .withArgument("x-max-length", 5)
        .withArgument("x-overflow", "drop-head")
        .deadLetterExchange("lab.overflow.dlx")
        .build();
~~~

Chú ý: snippet thứ hai là **thay thế cấu hình khi tạo queue nguồn**, không phải câu lệnh có thể áp dụng trực tiếp lên queue đã tồn tại. Nếu muốn bật DLX trên queue đã có, phải dùng phương án policy/migration được phiên bản RabbitMQ cho phép.

Sau khi xác nhận DLX, hãy gửi thêm message và kiểm tra message bị loại có đến `lab.overflow.dlq` không. Nếu không, kiểm tra DLX/binding, quyền và khả năng dead-letter của queue type/phiên bản trước khi kết luận.

## 12. Khi nào nên chọn mỗi overflow mode?

| Câu hỏi thiết kế | Nếu trả lời “có” | Hướng xem xét |
|---|---|---|
| Message cũ nhanh chóng không còn giá trị? | Ví dụ chỉ cần trạng thái cảm biến mới nhất | `drop-head` với số liệu đo mất mát |
| Không được đánh mất task đã chấp nhận? | Lệnh tài chính, tạo đơn, nghiệp vụ phải thực thi đầy đủ | Tránh chủ động drop-head; xem `reject-publish` và cơ chế bền vững |
| Producer có thể điều tiết hoặc lưu lại message chưa được nhận? | Có outbox/backpressure/retry có giới hạn | `reject-publish` khả thi hơn |
| Một publish đến nhiều queue? | Event nhiều subscriber với backlog riêng | Xem rủi ro một queue nack nhưng queue khác đã nhận |
| Muốn phân tích message bị loại? | Cần audit, giám sát hoặc tái xử lý | Thiết kế DLX phù hợp và kiểm tra khả năng hỗ trợ |
| Queue sử dụng quorum/feature đặc thù? | Có | Kiểm tra version/capability, test riêng trước khi cấu hình |

**Ví dụ 1 — dashboard realtime:** queue lưu cập nhật nhiệt độ mỗi giây. Nếu consumer chậm, giữ dữ liệu mới có thể hợp lý, còn các mẫu cũ có thể bị bỏ qua có kiểm soát. `drop-head` phù hợp nếu ứng dụng chấp nhận mất các cập nhật trung gian và có metric cảnh báo.

**Ví dụ 2 — thanh toán:** mỗi message yêu cầu một bước thanh toán hoặc ghi nhận hóa đơn. Dùng `drop-head` mà không có phương án khôi phục có thể làm mất nghiệp vụ. Thường cần bảo toàn message, publisher confirms, xử lý negative confirm, outbox, idempotency và kế hoạch tăng năng lực xử lý.

**Ví dụ 3 — fanout nhiều subscriber:** một queue audit chậm đạt giới hạn reject-publish trong khi queue notification vẫn nhận. Producer thử gửi lại toàn bộ publish có thể khiến notification xử lý trùng. Cần tách trách nhiệm subscriber, xác định semantics confirm và dùng event ID ổn định.

## 13. Những lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Queue luôn quanh ngưỡng, message mới vẫn vào | Đang dùng `drop-head`, message cũ bị loại | Kiểm tra effective policy, queue arguments, DLQ và tốc độ publish |
| Publisher confirm `nack` dù exchange/binding đúng | Queue reject publish vì overflow, hoặc lỗi broker khác | Kiểm tra effective overflow policy, queue depth, loại queue và nguyên nhân confirm |
| Producer không thấy lỗi dù một số message biến mất | Không bật confirms; `drop-head`; hoặc message hết TTL sau enqueue | Tách các giai đoạn publish, route, enqueue, consume, TTL |
| Đổi policy mà mode không đổi | Client `x-overflow` ưu tiên hoặc policy khác đang match | Xem arguments hiệu lực, policy priority và operator policy |
| Spring AMQP startup lỗi `PRECONDITION_FAILED` | Queue cùng tên tồn tại với arguments không tương thích | So sánh topology thực tế, xây migration được kiểm soát |
| DLQ trống dù drop-head đang chạy | Thiếu DLX/đường binding, quyền hoặc hỗ trợ dead-letter phù hợp | Xác minh DLX, dead-letter routing key, queue type và logs broker |
| Queue tăng dù max-length đã đặt | Có thể đang đếm tổng unacked, overshoot tạm thời hoặc đo không đúng metric | Đối chiếu ready/unacked, version/queue type, chính sách thật |
| Test không thấy overflow | Consumer đang lấy message, binding nhầm hoặc policy không áp dụng | Dừng consumer trong test, xác nhận queue, exchange, routing key |

**Cần phân biệt bốn nhóm sự kiện:**

- **Unroutable:** exchange không tìm được queue; `mandatory=true` có thể tạo `basic.return`.
- **Overflow reject-publish:** exchange đã route nhưng queue từ chối message mới; quan sát publisher confirms.
- **Overflow drop-head:** queue có thể loại message cũ đã được route; publisher confirm cho message cũ không tự đổi trạng thái.
- **Consumer processing failure:** message đã được giao, listener lỗi và tùy ack/retry/DLX mà message được requeue, dead-letter hoặc loại bỏ. Overflow mode không quyết định toàn bộ luồng xử lý này.

## 14. Tích hợp overflow với retry, dead-letter và khả năng phục hồi

Một thiết kế xử lý bất đồng bộ đáng tin cậy cần xem overflow là **một lớp bảo vệ tài nguyên**, kết hợp với cơ chế nghiệp vụ:

~~~mermaid
flowchart TD
    P["Producer + Outbox"] --> C{"Publish được broker xác nhận?"}
    C -->|"Được chấp nhận"| Q["Queue còn backlog"]
    C -->|"Nack / không rõ kết quả"| S["Lưu trạng thái, retry có giới hạn<br/>và idempotency"]
    Q --> O{"Overflow policy"}
    O -->|"drop-head"| D["Message cũ bị loại<br/>hoặc dead-letter nếu cấu hình"]
    O -->|"reject-publish"| R["Message mới bị từ chối"]
    Q --> L["@RabbitListener xử lý"]
    L --> A{"Nghiệp vụ thành công?"}
    A -->|Có| ACK["Consumer ack"]
    A -->|Không| DLX["Retry / reject / DLQ<br/>theo thiết kế"]
~~~

Một số điểm cần thiết:

1. **Publisher confirm và consumer ack khác nhau.** Confirm cho biết broker xử lý publish theo cơ chế xác nhận; ack của consumer liên quan delivery đã nhận.
2. **Retry ở producer không phải retry ở consumer.** Khi queue từ chối publish, producer phải quyết định gửi lại sau. Khi consumer lỗi xử lý message đã nhận, cơ chế retry/requeue nằm ở phía xử lý delivery.
3. **Outbox giúp không đánh mất ý định phát message** khi publish có kết quả không chắc chắn, nhưng phải có chiến lược định danh và consumer idempotent để đối phó gửi trùng.
4. **DLX không phải cơ chế bảo đảm tuyệt đối** nếu queue đích, binding, quyền hoặc dead-letter strategy không đáp ứng. Kiểm tra end-to-end.
5. **Overflow không thay thế backpressure.** Consumer chậm kéo dài thì drop hoặc reject chỉ giới hạn hệ quả; cần tìm nút thắt và điều tiết tốc độ phía producer.
6. **Transaction không tự vô hiệu hóa overflow.** Nếu tích hợp giao dịch, vẫn phải hiểu khả năng từ chối, mất kết nối và phạm vi transaction thực tế của các thành phần liên quan.

## 15. Bài tập tự kiểm tra

### Bài 1 — Dự đoán queue

Queue FIFO không consumer, `max-length=3`, `overflow=drop-head`. Producer gửi A, B, C, D, E. Những message nào còn trong queue?

**Đáp án trong mô hình đơn giản:** C, D, E. A, B lần lượt bị loại từ đầu queue. Trong hệ thống thực, TTL, priority, concurrency và đặc tính queue có thể thay đổi trình tự quan sát.

### Bài 2 — Phân tích nack

Queue có binding hợp lệ, `overflow=reject-publish`, `max-length=10`. Publisher nhận negative confirm khi queue đầy. Đây có phải `312 NO_ROUTE` không, và có nên retry ngay liên tục?

**Gợi ý:** không; broker có route tới queue nhưng queue từ chối message mới. Retry liên tục chỉ tăng tải. Cần đợi backlog giảm, thực hiện backoff có giới hạn, lưu trạng thái publish và kiểm tra idempotency.

### Bài 3 — Nhiều queue cùng một exchange

Một publish đến queue A (đang có chỗ) và queue B (`reject-publish`, đã đầy). Producer nhận `nack`. Vì sao gửi lại ngay có thể làm dữ liệu bị trùng?

**Gợi ý:** queue A có thể đã nhận message dù B từ chối. Khi retry toàn bộ publish, A có thể nhận thêm bản sao. Cần ID ổn định và consumer idempotent; hoặc tách đường publish và điều phối phù hợp.

### Bài 4 — Chọn policy cho nghiệp vụ

Hệ thống A gửi trạng thái cảm biến 20 lần/giây; hệ thống B gửi lệnh tạo hóa đơn. Đề xuất overflow mode và ghi rõ tiêu chí chấp nhận mất message.

**Gợi ý:** A có thể chọn `drop-head` nếu chỉ cần giá trị mới nhất và có metric về dữ liệu bị loại. B nên tránh bỏ task cũ; ưu tiên cơ chế bảo toàn, giám sát publish reject, outbox và xử lý an toàn khi đầy.

### Bài 5 — Đọc bảng metrics

RabbitMQ Management UI cho biết `messages_ready=5`, `messages_unacknowledged=20` và policy `max-length=5`. Có thể kết luận policy không hoạt động vì tổng 25 message không?

**Gợi ý:** không. Cần phân biệt ready/unacknowledged và cách queue length limit được áp dụng; message unacknowledged đã được giao cho consumer không thể suy từ tổng count để kết luận vi phạm.

### Bài 6 — Đổi policy không hiệu lực

Queue được tạo với `x-overflow=drop-head`. Đội vận hành thêm regular policy `overflow=reject-publish`, nhưng thực tế vẫn drop message cũ. Hãy nêu giả thuyết kiểm tra.

**Gợi ý:** đối chiếu effective client arguments và regular policy precedence, operator policy, queue type/version và pattern/priority. Nếu cần bỏ x-argument đã định nghĩa, lên kế hoạch thay đổi topology phù hợp.

### Bài 7 — Test DLX của overflow

Queue dùng drop-head và có `x-dead-letter-exchange`, nhưng DLQ không nhận M1 khi queue đầy. Hãy liệt kê bước chẩn đoán.

**Gợi ý:** kiểm tra DLX có tồn tại, dead-letter routing key và binding, quyền truy cập, queue type hỗ trợ tính năng, effective policy/arguments và logs broker. Không tự động kết luận message vẫn đang trong queue chỉ vì DLQ trống.

## 16. Checklist trước khi đưa overflow vào production

- [ ] Xác định **ngữ nghĩa mất dữ liệu**: có thể bỏ message cũ hay phải giữ mọi task đã chấp nhận?
- [ ] Ghi rõ loại queue, RabbitMQ version, giới hạn message/bytes và overflow mode thực sự được hỗ trợ.
- [ ] Quyết định nguồn quản lý config: regular policy, operator policy hoặc client `x-arguments`; hiểu precedence.
- [ ] Kiểm tra đúng virtual host, queue đang tồn tại, quyền khai báo và khả năng migration.
- [ ] Bật publisher confirms nếu cần biết publish bị reject; đừng chỉ dựa vào exception đồng bộ.
- [ ] Phân biệt `basic.return NO_ROUTE` với negative publisher confirm khi overflow.
- [ ] Với message có nhiều queue đích, thiết kế **idempotency** trước khi retry toàn publish.
- [ ] Nếu dùng DLX, kiểm chứng có đầy đủ exchange/queue/binding/permissions và khả năng dead-letter của queue type.
- [ ] Theo dõi `messages_ready`, `messages_unacknowledged`, throughput publish/consume, publisher nacks, DLQ và tốc độ bị loại/rejected.
- [ ] Test khi consumer chậm, consumer dừng, publisher burst, network lỗi và broker restart.
- [ ] Có phản ứng vận hành khi backlog tiến gần ngưỡng: mở rộng năng lực xử lý, điều tiết producer, báo động và lưu dữ liệu cần thiết.

**Ghi nhớ:** `drop-head` giải phóng chỗ bằng cách loại message đang chờ ở đầu queue; `reject-publish` ưu tiên giữ backlog hiện có và từ chối publish mới khi quá giới hạn. Đó là **hai lựa chọn đánh đổi nghiệp vụ khác nhau**. Hiểu queue limits, publisher confirms, chính sách dead-letter và các ràng buộc queue type/phiên bản giúp ứng dụng Spring AMQP xử lý backlog có chủ đích, tránh mất message âm thầm và xây nền tảng bất đồng bộ có thể quan sát, kiểm chứng.
