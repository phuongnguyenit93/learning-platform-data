# Push trigger, pull consumer và cơ chế polling

Trong chương **Hàng đợi và luồng sự kiện**, cách một function nhận message ảnh hưởng trực tiếp đến độ trễ, khả năng mở rộng, chi phí và cách xử lý lỗi. Có hai mô hình giao nhận phổ biến: **push**, trong đó một thành phần chủ động gọi consumer khi có dữ liệu; và **pull**, trong đó consumer chủ động hỏi hệ thống nguồn để lấy dữ liệu. Polling là kỹ thuật thường dùng trong mô hình pull, nhưng cũng có thể được một dịch vụ nền tảng thực hiện thay cho mã ứng dụng.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Trong môi trường FaaS, người phát triển cần hiểu ai đang chờ message, ai xác nhận xử lý, khi nào message được giao lại và cách giới hạn tốc độ tiêu thụ. Các quyết định này liên quan đến trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí vận hành.

## 1. Push, pull và polling là gì?

Một hệ thống bất đồng bộ thường có producer tạo message hoặc event, một broker lưu trữ hay phân phối chúng, và consumer thực hiện công việc. Câu hỏi quan trọng là bên nào khởi tạo việc chuyển dữ liệu từ broker đến consumer.

**Push delivery** là mô hình bên cung cấp message chủ động gửi dữ liệu đến consumer khi có dữ liệu cần xử lý. Consumer thường nhận một lời gọi HTTP, một callback hoặc một lần kích hoạt function. Producer không cần biết chi tiết xử lý nội bộ của consumer; broker hoặc dịch vụ trung gian chịu trách nhiệm giao message theo subscription.

**Pull consumption** là mô hình consumer chủ động yêu cầu broker trả về message hoặc record. Consumer quyết định khi nào gọi, lấy bao nhiêu dữ liệu và có thể điều chỉnh tốc độ tiêu thụ theo khả năng xử lý hiện tại.

**Polling** là cách consumer kiểm tra định kỳ xem có dữ liệu mới hay không. Một lần poll có thể trả về một hoặc nhiều message, hoặc trả về rỗng nếu chưa có dữ liệu. Polling có thể dùng chu kỳ ngắn hoặc long polling để chờ dữ liệu trong một khoảng thời gian trước khi trả kết quả.

| Mô hình | Ai khởi tạo việc giao dữ liệu? | Consumer kiểm soát tốc độ | Ví dụ |
|---|---|---|---|
| Push | Broker hoặc dịch vụ phân phối gọi consumer | Chủ yếu qua concurrency, giới hạn subscription và phản hồi xử lý | Webhook, push subscription, function invocation |
| Pull | Consumer gọi broker để lấy dữ liệu | Trực tiếp qua poll interval, batch size và số consumer | Kafka consumer, queue receive API |
| Polling | Là kỹ thuật kiểm tra dữ liệu theo chu kỳ trong pull | Qua tần suất và thời gian chờ mỗi lần poll | Receive message mỗi vài giây, long polling |

Push và pull mô tả cách khởi tạo giao nhận. Polling mô tả cách lặp lại yêu cầu lấy dữ liệu trong một consumer pull. Vì thế, không nên xem polling là một giao thức hoàn toàn độc lập với pull.

## 2. Luồng xử lý tổng quát

Một luồng queue có thể được biểu diễn như sau:

~~~mermaid
flowchart LR
    P[Producer] --> Q[Queue / Broker]
    Q --> D{Cách giao nhận}
    D -->|Push| F[Function được gọi]
    D -->|Pull / Poll| C[Consumer lấy message]
    F --> W[Xử lý nghiệp vụ]
    C --> W
    W --> A{Kết quả}
    A -->|Thành công| ACK[ACK / Delete]
    A -->|Lỗi tạm thời| RETRY[Retry / Giao lại]
    A -->|Lỗi lâu dài| DLQ[Dead-letter queue]
    ACK --> Q
    RETRY --> Q
    DLQ --> Q
~~~

Các thành phần có trách nhiệm riêng:

- **Producer** tạo message theo hợp đồng đã thống nhất.
- **Queue hoặc broker** lưu message, quản lý thời điểm giao và có thể theo dõi trạng thái acknowledgement.
- **Dispatcher hoặc event source mapping** chuyển message đến function theo cấu hình.
- **Consumer** thực hiện nghiệp vụ và báo kết quả xử lý.
- **Dead-letter queue (DLQ)** giữ message đã thất bại quá số lần cho phép hoặc bị phân loại là không thể xử lý tự động.

Với stream, broker thường lưu một chuỗi record có offset hoặc vị trí. Consumer theo dõi vị trí đã xử lý thay vì xóa từng record như queue thông thường.

## 3. Push trigger trong hệ thống serverless

### 3.1. Push trực tiếp qua HTTP hoặc webhook

Trong mô hình push trực tiếp, broker hoặc dịch vụ phát sự kiện gửi HTTP request đến endpoint của consumer. Function có thể được triển khai phía sau API gateway hoặc một endpoint được nền tảng quản lý.

Ví dụ:

1. Order Service phát sự kiện OrderPlaced.
2. Dịch vụ phân phối gửi HTTP POST đến endpoint của Inventory Function.
3. Function xác thực nguồn, kiểm tra envelope và xử lý giữ hàng.
4. Function trả mã phản hồi theo hợp đồng của dịch vụ gửi.
5. Dịch vụ phân phối ghi nhận thành công hoặc lên lịch retry theo chính sách.

Một HTTP 2xx thường được bên gửi xem là đã giao thành công, còn lỗi mạng hoặc mã phản hồi không thành công có thể dẫn đến retry. Quy tắc chính xác phụ thuộc dịch vụ. Consumer cần giả định request có thể được gửi lại, kể cả trường hợp lần xử lý trước đã hoàn tất nhưng response bị mất trên đường truyền.

### 3.2. Push subscription

Một số hệ thống pub/sub cho phép đăng ký endpoint nhận push. Broker quản lý việc gửi request, retry và thời gian chờ. Consumer không cần tự gọi API nhận message.

Push subscription phù hợp khi:

- Consumer có endpoint luôn sẵn sàng hoặc nền tảng có thể kích hoạt function.
- Muốn giảm mã polling và vận hành worker riêng.
- Độ trễ giao nhận thấp là yêu cầu quan trọng.
- Lưu lượng không vượt quá khả năng tiếp nhận được cấu hình.
- Hệ thống có thể xử lý request lặp và phản hồi đúng thời hạn.

Consumer cần có cơ chế xác thực request, giới hạn tốc độ và xử lý nhanh. Nếu nghiệp vụ kéo dài, có thể ghi nhận message bền vững rồi trả phản hồi thành công, sau đó xử lý nền bằng một cơ chế khác. Không nên trả thành công trước khi đã lưu đủ thông tin để tiếp tục xử lý, vì broker có thể ngừng retry ngay sau phản hồi đó.

### 3.3. Push trigger và event source mapping của FaaS

Nhiều nền tảng FaaS hỗ trợ kết nối queue hoặc stream với function thông qua một cấu hình tích hợp. Khi có message, nền tảng tự động gọi function, thường kèm một batch message.

Từ góc nhìn mã Java, function được kích hoạt như một lần gọi mới. Tuy nhiên, phía nền tảng có thể đang polling queue hoặc stream để phát hiện dữ liệu, rồi mới invoke function. Đây là điểm cần phân biệt: **function được gọi theo kiểu push không có nghĩa broker nhất thiết đang đẩy message trực tiếp đến function**.

Event source mapping thường quản lý một số việc:

- Đọc message hoặc record từ nguồn.
- Tạo batch theo kích thước và cửa sổ gom batch.
- Gọi function với batch.
- Theo dõi kết quả invocation.
- Retry hoặc checkpoint theo cơ chế của nguồn.
- Điều chỉnh số lượng invocation theo độ dài hàng đợi hoặc tải.

Tính năng và ngữ nghĩa cụ thể khác nhau giữa các nền tảng. Cần đọc rõ cơ chế acknowledgement, batch failure, checkpoint, concurrency và retry của dịch vụ đang dùng.

### 3.4. Ưu điểm và giới hạn của push

Push có thể giảm độ trễ vì consumer được gọi khi message sẵn sàng, không cần chờ lần poll tiếp theo. Nó cũng giảm mã vận hành vì broker hoặc dịch vụ nền tảng quản lý việc phân phối.

Tuy nhiên, producer hoặc broker có thể gửi nhanh hơn tốc độ consumer xử lý. Nếu không giới hạn concurrency, một đợt tải lớn có thể tạo nhiều function invocation đồng thời, làm quá tải cơ sở dữ liệu hoặc API phụ thuộc. Push cần có cơ chế backpressure như giới hạn concurrency, quota, rate limit hoặc buffer queue.

Consumer cũng phải phản hồi trong timeout của dịch vụ gửi. Nếu function xử lý quá lâu, bên gửi có thể timeout và gửi lại trong khi invocation đầu tiên vẫn đang chạy. Điều này làm tăng nguy cơ xử lý trùng.

## 4. Pull consumer và cách chủ động lấy message

### 4.1. Consumer gọi receive hoặc poll

Trong mô hình pull, consumer chủ động gửi yêu cầu đến broker. Một lần gọi có thể yêu cầu tối đa một số message, chỉ chờ trong thời gian giới hạn và trả về ngay khi có dữ liệu hoặc hết thời gian chờ.

Luồng cơ bản:

1. Consumer gọi receive/poll.
2. Broker trả về batch message hoặc danh sách rỗng.
3. Consumer xử lý từng message hoặc từng record.
4. Khi xử lý thành công, consumer xác nhận message hoặc commit vị trí đã xử lý.
5. Consumer tiếp tục poll theo chu kỳ hoặc ngay sau khi hoàn tất batch.

Pull cho phép consumer điều chỉnh lượng công việc đang nhận. Nếu database chậm, consumer có thể giảm batch size, giảm số worker hoặc tạm dừng poll. Đây là một cách tạo backpressure trực tiếp ở phía ứng dụng.

### 4.2. Queue pull và acknowledgement

Với queue, broker thường giữ message cho đến khi consumer xác nhận đã xử lý. Cơ chế xác nhận có thể là ACK, delete message, complete message hoặc một thao tác tương đương.

Một số queue dùng visibility timeout hoặc lease:

- Khi message được giao cho consumer, broker tạm thời ẩn message khỏi consumer khác.
- Consumer xử lý trong thời gian lease.
- Nếu consumer xác nhận thành công, message được xóa hoặc đánh dấu hoàn tất.
- Nếu lease hết hạn mà chưa xác nhận, message có thể được giao lại.

Visibility timeout cần đủ dài cho thời gian xử lý dự kiến, bao gồm cả độ trễ phụ thuộc và thời gian ghi dữ liệu. Nếu quá ngắn, message có thể được giao cho consumer thứ hai trong khi consumer đầu tiên vẫn xử lý. Nếu quá dài, message lỗi có thể mất nhiều thời gian mới được thử lại.

Một số hệ thống cho phép gia hạn visibility timeout hoặc lease khi công việc kéo dài. Việc gia hạn phải có giới hạn và cần tránh giữ message vô thời hạn.

### 4.3. Stream pull và offset

Với event stream, record thường nằm trong log có thứ tự trong từng partition. Consumer đọc từ offset và lưu checkpoint hoặc commit offset để ghi nhận vị trí đã xử lý.

Khác với queue thông thường, consumer không xóa record sau khi đọc. Nhiều consumer group có thể đọc cùng stream độc lập. Mỗi group theo dõi offset riêng, nên cùng một record có thể được nhiều nhóm xử lý.

| Queue | Event stream |
|---|---|
| Message thường được xóa hoặc đánh dấu hoàn tất sau ACK | Record được giữ theo retention policy |
| Một message thường được phân phối cho một consumer tại một thời điểm theo cơ chế queue | Nhiều consumer group có thể đọc cùng record |
| Trạng thái xử lý thường gắn với message hoặc receipt | Trạng thái đọc gắn với offset/checkpoint |
| Retry thường làm message được giao lại | Consumer có thể đọc lại bằng cách reset hoặc không commit offset |
| Phù hợp với công việc cần phân phối và hoàn tất | Phù hợp với dòng sự kiện cần nhiều consumer hoặc replay |

Không phải mọi broker đều có cùng ngữ nghĩa. Một số hệ thống có thể kết hợp queue và stream, hoặc cung cấp cả ACK theo message và checkpoint theo partition. Luôn dựa vào hợp đồng cụ thể của nền tảng.

## 5. Polling, short polling và long polling

### 5.1. Short polling

Short polling là cách consumer hỏi broker thường xuyên với thời gian chờ ngắn hoặc không chờ. Nếu chưa có message, broker trả về ngay một kết quả rỗng và consumer sẽ thử lại sau một khoảng thời gian.

Ví dụ chu kỳ:

~~~text
Poll -> Không có message -> Chờ 1 giây
Poll -> Có 5 message -> Xử lý batch
Poll -> Không có message -> Chờ 1 giây
Poll -> Có 2 message -> Xử lý batch
~~~

Ưu điểm là dễ triển khai, dễ dự đoán thời gian chờ và consumer có thể kiểm soát chu kỳ. Nhược điểm là khi queue ít hoạt động, consumer vẫn liên tục tạo request rỗng. Nếu chu kỳ dài, message mới phải chờ lâu hơn trước khi được nhận.

Short polling phù hợp khi:

- API nguồn không hỗ trợ long polling.
- Consumer cần chu kỳ kiểm tra cố định.
- Tải có tính chu kỳ hoặc công việc chỉ cần xử lý theo đợt.
- Độ trễ chờ tối đa có thể chấp nhận được.

### 5.2. Long polling

Long polling cho phép consumer yêu cầu broker chờ trong một khoảng thời gian nếu chưa có message. Broker trả kết quả sớm khi có message hoặc khi thời gian chờ kết thúc.

Ví dụ:

~~~text
Poll (wait up to 20 seconds)
  -> Message đến sau 3 giây: trả batch ngay
  -> Không có message: trả rỗng sau 20 giây
Poll tiếp
~~~

Long polling giảm số lần gọi rỗng và thường giúp giảm độ trễ so với short polling có chu kỳ dài. Consumer vẫn chủ động gọi, nhưng không phải liên tục thức dậy để hỏi broker.

Long polling không có nghĩa là broker chủ động gọi consumer. Consumer vẫn giữ một yêu cầu đang chờ phản hồi. Nó cũng không bảo đảm message được giao ngay lập tức; còn phụ thuộc thời gian chờ tối đa, batch window, tải và cấu hình nguồn.

### 5.3. Chọn thời gian poll

Có một số yếu tố cần cân bằng:

- Poll quá thường xuyên làm tăng số request rỗng và chi phí gọi API.
- Poll quá thưa làm tăng thời gian message nằm chờ.
- Long polling quá dài có thể chiếm kết nối hoặc worker trong thời gian chờ.
- Poll song song quá nhiều có thể tạo áp lực lên broker.
- Thời gian poll phải tương thích với timeout của function, HTTP client và nền tảng.

Với một function chạy theo lịch để poll queue, cần bảo đảm thời gian chờ cộng thời gian xử lý batch không vượt timeout invocation. Nếu mỗi lần poll chỉ lấy một batch nhỏ, function có thể bị gọi nhiều lần và làm tăng chi phí khởi tạo, cold start và điều phối. Với nguồn được nền tảng hỗ trợ trực tiếp, event source mapping thường giúp quản lý polling và batch hiệu quả hơn.

### 5.4. Polling thích ứng

Consumer có thể điều chỉnh thời gian nghỉ dựa trên kết quả poll:

- Có message: tiếp tục poll nhanh sau khi xử lý batch.
- Không có message: tăng thời gian nghỉ đến một giới hạn.
- Có lỗi tạm thời: dùng exponential backoff và jitter.
- Broker bị quá tải: giảm concurrency hoặc tạm dừng nhận message.
- Queue tăng nhanh: tăng số worker trong giới hạn tài nguyên phụ thuộc.

Không nên để mọi consumer cùng retry theo một lịch cố định. Khi broker hoặc dịch vụ phụ thuộc gặp sự cố, nhiều client cùng thức dậy và retry có thể tạo ra một đợt tải đột biến. Jitter giúp phân tán thời điểm retry.

## 6. Batch size, batch window và hiệu quả xử lý

Consumer thường nhận nhiều message trong một lần poll hoặc một lần function invocation. Xử lý theo batch có thể giảm chi phí giao tiếp và chi phí khởi tạo, nhưng làm tăng thời gian chờ cho message đầu tiên và ảnh hưởng phạm vi retry.

**Batch size** là số message tối đa trong một lần nhận hoặc invocation. **Batch window** là khoảng thời gian tối đa hệ thống chờ để gom thêm message trước khi gửi batch cho consumer, nếu nền tảng hỗ trợ.

| Batch nhỏ | Batch lớn |
|---|---|
| Message được xử lý sớm hơn khi lưu lượng thấp | Giảm số lần invocation hoặc poll |
| Phạm vi retry nhỏ hơn trong nhiều cơ chế | Có thể tăng throughput |
| Tốn nhiều overhead trên mỗi message | Tốn bộ nhớ và thời gian xử lý một batch |
| Hữu ích khi xử lý nặng hoặc cần độ trễ thấp | Hữu ích khi xử lý nhanh và lưu lượng đều |

Khi chọn batch size, cần tính:

- Thời gian xử lý trung bình và trường hợp xấu nhất cho một message.
- Giới hạn payload hoặc số record của nền tảng.
- Bộ nhớ function.
- Timeout invocation.
- Khả năng chịu tải của database và API phụ thuộc.
- Chính sách retry toàn batch hoặc từng message.
- Mức độ cần giữ thứ tự.

Batch size lớn không luôn tạo throughput tốt hơn. Nếu một message lỗi khiến toàn bộ batch bị retry, các message đã xử lý thành công có thể bị thực hiện lại. Consumer phải idempotent hoặc nền tảng cần hỗ trợ báo lỗi từng message.

## 7. Acknowledgement, delete và checkpoint

### 7.1. Xác nhận sau khi xử lý bền vững

Một consumer nên xác nhận message sau khi công việc đã hoàn tất và kết quả được lưu bền vững. Nếu ACK trước khi commit dữ liệu nghiệp vụ, consumer có thể mất message khi tiến trình bị dừng ngay sau ACK.

Ngược lại, nếu dữ liệu đã commit nhưng ACK bị mất, message có thể được giao lại. Đây là lý do consumer cần idempotency.

Một trình tự an toàn thường là:

1. Xác thực message và kiểm tra schema.
2. Kiểm tra khóa chống trùng.
3. Thực hiện nghiệp vụ và ghi kết quả.
4. Commit transaction.
5. ACK hoặc delete message, hoặc commit offset theo cơ chế của nguồn.

Đối với thao tác gọi dịch vụ bên ngoài, transaction cục bộ không thể bao trùm toàn bộ hiệu ứng bên ngoài. Cần dùng idempotency key của nhà cung cấp, lưu trạng thái bước xử lý và thiết kế hành động bù trừ khi phù hợp.

### 7.2. Partial batch failure

Một batch có thể chứa cả message thành công và thất bại. Nếu nền tảng chỉ nhận một kết quả thành công/thất bại cho toàn batch, một message lỗi có thể khiến tất cả message được giao lại.

Partial batch failure cho phép consumer chỉ ra message nào cần retry hoặc không được checkpoint. Cơ chế cụ thể phụ thuộc nền tảng và loại nguồn:

- Với queue, có thể xác nhận hoặc xóa message thành công và giữ message lỗi để giao lại.
- Với stream, checkpoint thường gắn với offset của partition. Nếu record ở giữa batch lỗi, consumer có thể phải đọc lại record từ vị trí đó trở đi, tùy cơ chế của event source mapping.
- Một số nền tảng có hỗ trợ batch item failure response; một số khác chỉ hỗ trợ thành công hoặc thất bại toàn batch.

Không giả định rằng mọi FaaS đều có partial batch response giống nhau. Hãy kiểm tra cấu hình trigger và định dạng response được nền tảng yêu cầu.

### 7.3. Poison message

Poison message là message luôn khiến consumer thất bại, chẳng hạn payload sai schema, dữ liệu không hợp lệ hoặc một trường hợp gây lỗi phần mềm. Nếu message này được retry liên tục, nó có thể chiếm tài nguyên và chặn các message khác, đặc biệt khi stream cần giữ thứ tự trong partition.

Cần giới hạn số lần thử, phân loại lỗi và chuyển message không thể xử lý sang DLQ hoặc vùng lưu trữ lỗi. Với stream, có thể cần ghi nhận offset lỗi, chuyển record sang luồng cách ly rồi cho phép consumer tiếp tục theo chính sách nghiệp vụ. Không nên bỏ qua record âm thầm nếu việc bỏ qua làm mất một sự kiện quan trọng.

## 8. Backpressure và kiểm soát tốc độ consumer

Backpressure là cơ chế điều chỉnh tốc độ producer, broker hoặc consumer để tránh một thành phần bị quá tải. Trong serverless, function có thể được mở rộng nhanh, nhưng database hoặc dịch vụ bên ngoài thường có giới hạn kết nối và throughput thấp hơn.

Các cách kiểm soát phổ biến:

- Giới hạn concurrency tối đa của function.
- Giới hạn số message mỗi lần poll hoặc batch.
- Giới hạn số poll đồng thời.
- Tạm dừng hoặc giảm tốc độ nhận khi dependency chậm.
- Dùng queue làm buffer để hấp thụ đợt tải.
- Dùng token bucket hoặc rate limiter cho API bên ngoài.
- Chọn số consumer phù hợp với số partition của stream.
- Theo dõi tuổi message lâu nhất và tốc độ tăng queue.

Ví dụ, Inventory Function có thể nhận 500 message mỗi giây, trong khi cơ sở dữ liệu chỉ xử lý ổn định 100 giao dịch mỗi giây. Nếu function mở rộng theo toàn bộ lưu lượng, số kết nối và transaction chờ có thể tăng nhanh. Cần giới hạn concurrency hoặc tốc độ nhận để giữ tải trong khả năng xử lý.

Một queue có thể hấp thụ đợt tải tăng đột biến, nhưng không làm tăng throughput bền vững của consumer. Nếu tốc độ message đến luôn lớn hơn tốc độ xử lý, backlog sẽ tăng theo thời gian. Cần tăng năng lực consumer, tối ưu xử lý hoặc giảm tải đầu vào.

## 9. Retry, visibility timeout, offset và dead-letter queue

### 9.1. Queue retry

Khi message không được ACK, queue có thể giao lại sau visibility timeout hoặc khi lease hết hạn. Cần cấu hình số lần giao tối đa hoặc chính sách retry phù hợp. Sau nhiều lần thất bại, message được chuyển vào DLQ nếu dịch vụ hỗ trợ.

Visibility timeout nên lớn hơn thời gian xử lý dự kiến của batch, có tính đến thời gian chờ dependency và ghi dữ liệu. Nếu xử lý có thể kéo dài, cần gia hạn lease hoặc chia công việc thành các bước nhỏ có trạng thái bền vững.

### 9.2. Stream retry và checkpoint

Với stream, consumer thường commit offset sau khi xử lý thành công. Nếu không commit, consumer có thể đọc lại record sau khi restart hoặc rebalance. Nếu commit offset quá sớm, record có thể bị bỏ qua dù nghiệp vụ chưa hoàn tất.

Checkpoint nên phản ánh vị trí liên tục đã xử lý thành công trong mỗi partition. Không nên commit offset cao hơn một record chưa hoàn tất trong cùng partition nếu ứng dụng yêu cầu xử lý theo thứ tự.

### 9.3. Dead-letter và vùng cách ly

DLQ giữ message đã vượt quá chính sách retry hoặc bị đánh dấu không thể xử lý. Cần lưu lý do lỗi, số lần thử, thời điểm, nguồn và định danh message. Với CloudEvents, giữ source và id gốc để có thể truy vết.

DLQ không phải nơi lưu trữ vĩnh viễn thay cho hệ thống lưu trữ nghiệp vụ. Cần có thời hạn lưu, quyền truy cập, quy trình điều tra và cách replay có kiểm soát. Trước khi replay, cần sửa nguyên nhân lỗi và xác định consumer có thể xử lý an toàn message cũ hay không.

## 10. Thứ tự và khả năng mở rộng

### 10.1. Queue ordering

Một số queue cung cấp FIFO hoặc nhóm thứ tự, nhưng nhiều queue thông thường không bảo đảm thứ tự tuyệt đối khi có nhiều consumer, retry hoặc message visibility. Nếu nghiệp vụ yêu cầu thứ tự theo từng đơn hàng, có thể dùng message group key theo orderId hoặc một partition key tương đương.

Giữ thứ tự thường làm giảm mức song song trong cùng nhóm. Có thể xử lý nhiều nhóm độc lập đồng thời, nhưng các message thuộc cùng một nhóm phải tuân theo chính sách thứ tự.

### 10.2. Stream partitions và consumer groups

Stream thường chia dữ liệu thành nhiều partition. Mỗi partition có thứ tự record riêng. Consumer group chia partition cho các consumer thành viên để xử lý song song. Số consumer đang hoạt động hiệu quả trong một group thường bị giới hạn bởi số partition, tùy broker.

Nếu có quá ít partition, tăng số function instance không nhất thiết làm tăng throughput vì một partition không thể được chia tùy ý cho nhiều consumer trong cùng group mà vẫn giữ một luồng offset duy nhất. Nếu có quá nhiều partition, chi phí quản lý và rebalance có thể tăng.

### 10.3. Rebalance

Khi consumer tham gia hoặc rời group, broker có thể phân phối lại partition. Consumer cần lưu offset đúng và xử lý việc dừng nhận record, hoàn tất công việc đang chạy và commit checkpoint theo quy tắc. Xử lý song song không kiểm soát có thể làm record sau được commit trước record trước.

Đối với Java consumer, nên xử lý record theo partition tuần tự nếu cần giữ thứ tự. Nếu xử lý song song, phải theo dõi offset hoàn tất theo từng partition và chỉ commit đến vị trí liên tục đã xử lý.

## 11. Ví dụ Java: pull consumer cho Kafka

Ví dụ dưới đây minh họa một consumer Java chủ động poll Kafka. Consumer tắt auto commit, xử lý các record trong batch và chỉ commit offset sau khi xử lý toàn bộ batch thành công.

~~~java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public final class OrderStreamConsumer {
    private final KafkaConsumer<String, String> consumer;
    private final OrderEventProcessor processor;

    public OrderStreamConsumer(
            KafkaConsumer<String, String> consumer,
            OrderEventProcessor processor) {
        this.consumer = consumer;
        this.processor = processor;
    }

    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                if (records.isEmpty()) {
                    continue;
                }

                try {
                    for (ConsumerRecord<String, String> record : records) {
                        processor.processIdempotently(
                                record.topic(),
                                record.partition(),
                                record.offset(),
                                record.key(),
                                record.value());
                    }

                    consumer.commitSync();
                } catch (Exception processingFailure) {
                    // Không commit batch chưa hoàn tất.
                    // Dừng consumer để supervisor áp dụng backoff hoặc phục hồi.
                    throw new IllegalStateException(
                            "Batch processing failed", processingFailure);
                }
            }
        } finally {
            consumer.close();
        }
    }

    public static KafkaConsumer<String, String> createConsumer() {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", "localhost:9092");
        properties.put("group.id", "order-service");
        properties.put("key.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        properties.put("value.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        properties.put("enable.auto.commit", "false");
        properties.put("auto.offset.reset", "earliest");

        return new KafkaConsumer<>(properties);
    }
}
~~~

Trước khi chạy, ứng dụng cần subscribe vào topic, chẳng hạn gọi consumer.subscribe(List.of("orders")). Phần cấu hình bootstrap server, xác thực và TLS cần lấy từ cấu hình triển khai an toàn, không hardcode trong production.

Một số điểm cần hiểu:

- poll chủ động lấy record và cũng giúp consumer tham gia duy trì group membership.
- commitSync chỉ chạy sau khi cả batch hoàn tất.
- Nếu một record lỗi, batch chưa commit nên các record đã xử lý trước đó có thể được đọc lại sau khi consumer khởi động lại.
- Vì vậy processor.processIdempotently phải chống xử lý trùng bằng khóa nghiệp vụ hoặc topic-partition-offset.
- Nếu xử lý một batch quá lâu, consumer có thể vượt max.poll.interval.ms và bị rời group. Cần chọn batch size, thời gian xử lý và cấu hình poll phù hợp.
- Trong production, cần xử lý lỗi, backoff, rebalance và shutdown có kiểm soát; ví dụ trên tập trung vào vòng poll và commit.

Không nên chạy KafkaConsumer từ nhiều thread cùng lúc. KafkaConsumer không thread-safe. Nếu cần xử lý song song, có thể chuyển record sang worker pool nhưng phải quản lý offset hoàn tất theo partition và chỉ commit khi tất cả record trước đó trong partition đã hoàn tất.

## 12. Ví dụ Java: xử lý batch message trong function

Với một nền tảng FaaS có event source mapping, function có thể nhận một batch message trong một invocation. Adapter nền tảng chuyển batch thành kiểu dữ liệu Java, gọi nghiệp vụ và trả kết quả theo giao thức của nền tảng.

Ví dụ sau là mô hình minh họa độc lập với nhà cung cấp:

~~~java
import java.util.List;

public record QueueMessage(
        String messageId,
        String body,
        int receiveCount) {
}

public record BatchResult(List<String> failedMessageIds) {
}

public interface MessageProcessor {
    void processIdempotently(QueueMessage message);
}

public final class QueueBatchFunction {
    private final MessageProcessor processor;

    public QueueBatchFunction(MessageProcessor processor) {
        this.processor = processor;
    }

    public BatchResult handle(List<QueueMessage> messages) {
        List<String> failures = new java.util.ArrayList<>();

        for (QueueMessage message : messages) {
            try {
                processor.processIdempotently(message);
            } catch (Exception failure) {
                failures.add(message.messageId());
            }
        }

        return new BatchResult(List.copyOf(failures));
    }
}
~~~

BatchResult ở đây minh họa ý tưởng partial batch failure. Mỗi nền tảng có thể yêu cầu một cấu trúc response khác nhau, hoặc chỉ hỗ trợ success/failure ở cấp invocation. Adapter triển khai thực tế phải chuyển danh sách failedMessageIds sang đúng response schema của nền tảng.

Nếu nền tảng không hỗ trợ partial batch failure, cần cân nhắc xử lý idempotent để việc retry toàn batch không tạo hiệu ứng lặp. Không xác nhận toàn bộ batch thành công nếu còn message chưa được xử lý bền vững.

## 13. Polling trong Java function chạy theo lịch

Có thể dùng scheduler để kích hoạt function định kỳ, rồi function poll queue hoặc API nhận message. Mô hình này hữu ích khi nguồn không có event source mapping hoặc công việc cần chạy theo đợt.

Ví dụ:

~~~java
public final class ScheduledQueuePoller {
    private final QueueClient queueClient;
    private final MessageProcessor processor;

    public ScheduledQueuePoller(
            QueueClient queueClient,
            MessageProcessor processor) {
        this.queueClient = queueClient;
        this.processor = processor;
    }

    public void runOnce() {
        var messages = queueClient.receive(
                10,
                java.time.Duration.ofSeconds(15));

        for (QueueMessage message : messages) {
            processor.processIdempotently(message);
            queueClient.acknowledge(message);
        }
    }
}
~~~

Đây là pseudo-adapter: QueueClient đại diện cho API của broker. Trong production, cần xử lý từng message riêng, phân loại lỗi, chỉ ACK sau khi transaction nghiệp vụ hoàn tất và tránh làm mất ACK khi một message trong batch lỗi.

Khi dùng scheduler, cần xem xét:

- Lịch chạy có thể chồng lấn nếu một invocation chưa kết thúc.
- Nhiều instance có thể cùng poll nếu scheduler cho phép concurrency.
- Cần khóa hoặc cơ chế phân phối công việc nếu chỉ một consumer được phép chạy.
- Poll wait duration phải nhỏ hơn timeout function.
- Cần giới hạn thời gian xử lý batch để không vượt timeout.
- Nếu function thường xuyên poll rỗng, chi phí invocation và cold start có thể cao.

Nếu nền tảng có tích hợp queue-native, event source mapping thường phù hợp hơn vì nền tảng quản lý việc đọc, batch và invocation. Scheduled polling vẫn hữu ích khi cần tích hợp nguồn không hỗ trợ trực tiếp hoặc có lịch xử lý đặc thù.

## 14. Bảo mật và quyền truy cập

Push và pull có bề mặt bảo mật khác nhau.

Với push HTTP:

- Xác thực danh tính dịch vụ gọi endpoint.
- Kiểm tra chữ ký hoặc token theo cơ chế của nhà cung cấp.
- Chỉ cho phép đúng nguồn phát và subscription được cấu hình.
- Giới hạn request size và rate.
- Bảo vệ endpoint khỏi truy cập công khai ngoài ý muốn.

Với pull consumer:

- Cấp quyền receive/read cho đúng queue hoặc topic.
- Chỉ cấp quyền ACK/delete hoặc commit offset khi consumer cần.
- Quản lý credential bằng secret manager hoặc IAM role.
- Dùng TLS khi kết nối broker.
- Giới hạn quyền đọc theo topic, queue, consumer group hoặc tenant.

Không nên cấp quyền quản trị broker cho function chỉ để nhận message. Quyền publish và consume nên tách biệt nếu nghiệp vụ và nền tảng cho phép.

## 15. Độ trễ, cold start và chi phí

### 15.1. Độ trễ

Push có thể giảm thời gian chờ do polling, nhưng vẫn chịu độ trễ từ broker, batch window, invocation và cold start. Pull có thể tăng độ trễ nếu poll interval dài hoặc consumer xử lý batch quá lớn trước khi tiếp tục poll.

Long polling giúp giảm request rỗng mà vẫn nhận message tương đối sớm. Batch window tăng khả năng gom message nhưng có thể làm message đầu tiên phải chờ lâu hơn.

### 15.2. Cold start

Nếu mỗi batch kích hoạt một function instance mới, cold start có thể ảnh hưởng thời gian xử lý. Batch lớn có thể giảm số invocation nhưng làm mỗi invocation kéo dài và dùng nhiều bộ nhớ. Batch nhỏ có thể phản hồi nhanh nhưng tạo nhiều lần gọi hơn.

Cần đo thời gian từ lúc message được đưa vào queue đến khi nghiệp vụ hoàn tất, không chỉ đo thời gian chạy handler. Metric hữu ích gồm tuổi message, thời gian chờ trong queue, thời gian invocation, thời gian xử lý batch và thời gian retry.

### 15.3. Chi phí

Chi phí có thể gồm:

- Số lần receive/poll hoặc push invocation.
- Số lần function invocation và thời gian thực thi.
- Thời gian giữ kết nối long polling.
- Số message, kích thước payload và lưu trữ.
- Retry, dead-letter và replay.
- Log, trace và metric.
- Tài nguyên broker, partition và consumer group.

Short polling có thể tạo nhiều request rỗng. Long polling thường giảm số lần gọi rỗng. Push có thể giảm overhead polling nhưng có thể tạo nhiều invocation khi lưu lượng tăng. Event source mapping có thể tính phí hoặc chịu giới hạn theo nhà cung cấp. Hãy so sánh tổng chi phí trên workload thực tế.

## 16. Chọn push hay pull trong tình huống thực tế

| Tình huống | Mô hình nên cân nhắc | Lý do |
|---|---|---|
| Gửi thông báo đến một endpoint khi có event | Push | Consumer được gọi khi dữ liệu sẵn sàng |
| Java worker cần tự điều chỉnh tốc độ đọc từ broker | Pull | Consumer kiểm soát poll, batch và concurrency |
| Queue được tích hợp trực tiếp với FaaS | Event source mapping | Nền tảng quản lý polling và invocation |
| Stream có partition và consumer group | Pull | Consumer theo dõi offset và xử lý theo partition |
| Nguồn không có push hoặc trigger native | Polling | Consumer chủ động kiểm tra nguồn |
| Tải không đều, cần giảm request rỗng | Long polling hoặc event source mapping | Chờ dữ liệu thay vì hỏi liên tục |
| Consumer có giới hạn nghiêm ngặt về throughput | Pull có giới hạn hoặc push kèm concurrency cap | Điều tiết tốc độ để bảo vệ dependency |

Không có một mô hình tối ưu cho mọi hệ thống. Cần cân nhắc độ trễ, khả năng kiểm soát tốc độ, đặc tính queue hay stream, hỗ trợ của nền tảng, retry và chi phí.

## 17. Các lỗi thiết kế thường gặp

**Polling quá thường xuyên:** Consumer tạo nhiều request rỗng, tăng chi phí và áp lực lên broker. Dùng long polling hoặc tăng thời gian nghỉ thích ứng khi không có message.

**Polling quá thưa:** Message phải chờ lâu trước khi được nhận. Điều chỉnh interval theo SLA độ trễ hoặc dùng push/event source mapping.

**ACK trước khi ghi dữ liệu:** Nếu function lỗi sau ACK, message đã bị xóa nhưng nghiệp vụ chưa hoàn tất. Chỉ ACK sau khi kết quả được lưu bền vững.

**Visibility timeout quá ngắn:** Message được giao lại trong khi consumer đầu vẫn xử lý. Đặt lease đủ dài hoặc gia hạn khi cần.

**Không idempotent:** Retry, timeout hoặc mất response có thể tạo hiệu ứng nghiệp vụ trùng. Dùng khóa chống trùng bền vững.

**Batch quá lớn:** Invocation có thể vượt timeout, tốn bộ nhớ hoặc làm phạm vi retry rộng. Chọn batch size theo thời gian xử lý và giới hạn nền tảng.

**Một message lỗi làm kẹt cả batch:** Dùng partial batch failure nếu được hỗ trợ hoặc thiết kế consumer idempotent và DLQ.

**Mở rộng consumer không giới hạn:** Function tạo nhiều kết nối đồng thời và làm quá tải database. Đặt concurrency cap, rate limit và backpressure.

**Commit offset trước khi xử lý xong:** Record có thể bị bỏ qua sau restart. Chỉ commit checkpoint của phần liên tục đã xử lý thành công.

**Không tính rebalance:** Consumer có thể mất partition trong lúc xử lý. Lưu checkpoint đúng và xử lý shutdown/rebalance có kiểm soát.

**Dùng scheduled polling nhưng không chống chồng lấn:** Hai invocation có thể poll cùng lúc và xử lý trùng. Dùng khóa phân tán hoặc giới hạn concurrency, đồng thời giữ idempotency.

**Coi event source mapping là push thuần túy:** Phía nền tảng có thể đang poll queue hoặc stream. Hiểu rõ nơi đặt batch, checkpoint, retry và concurrency để vận hành đúng.

## 18. Checklist trước khi triển khai consumer

- [ ] Đã xác định queue hay stream và ngữ nghĩa lưu trữ của nguồn.
- [ ] Đã chọn push, pull hoặc event source mapping phù hợp.
- [ ] Nếu dùng polling, đã chọn short polling hay long polling và thời gian chờ.
- [ ] Poll interval, batch size và batch window phù hợp với SLA.
- [ ] Timeout function, HTTP client, visibility timeout hoặc lease không xung đột.
- [ ] Consumer chỉ ACK/delete sau khi nghiệp vụ được lưu bền vững.
- [ ] Với stream, offset/checkpoint chỉ tiến qua phần liên tục đã xử lý thành công.
- [ ] Đã xử lý duplicate bằng idempotency key hoặc source + event id.
- [ ] Đã xác định retry, backoff, jitter, DLQ và quy trình replay.
- [ ] Có xử lý partial batch failure nếu nền tảng hỗ trợ.
- [ ] Có giới hạn concurrency và cơ chế backpressure.
- [ ] Đã xem xét ordering, partition key, consumer group và rebalance.
- [ ] Quyền receive, ACK, publish và subscribe được cấp tối thiểu.
- [ ] Có metric về queue depth, oldest message age, poll rỗng, retry, DLQ và thời gian xử lý.
- [ ] Đã ước lượng chi phí polling, invocation, lưu trữ và vận hành trên tải đại diện.

## Kết luận

Push giúp broker hoặc dịch vụ phân phối chủ động gọi consumer khi message sẵn sàng. Pull cho phép consumer chủ động lấy dữ liệu và kiểm soát tốc độ. Polling là cách lặp lại yêu cầu nhận dữ liệu trong pull; short polling kiểm tra nhanh theo chu kỳ, còn long polling chờ message trong một khoảng thời gian để giảm request rỗng. Với FaaS, event source mapping có thể thực hiện polling ở tầng nền tảng rồi kích hoạt function theo batch.

Lựa chọn đúng cần dựa trên độ trễ, throughput, khả năng backpressure, batch, acknowledgement hoặc checkpoint, retry, idempotency, ordering, cold start và chi phí. Dù dùng mô hình nào, consumer vẫn phải lưu trạng thái bền vững, xác nhận sau khi xử lý thành công và chịu được việc message được giao lại. Đây là điều kiện để các Java function vận hành đáng tin cậy khi lưu lượng thay đổi và các thành phần phụ thuộc gặp lỗi.

