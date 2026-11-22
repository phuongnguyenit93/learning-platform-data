# Race condition khi nhiều consumer xử lý cùng channel

Trong Spring Integration, nhiều consumer cùng đăng ký vào một channel có thể làm tăng khả năng xử lý song song. Điều đó cũng tạo ra race condition nếu các lần xử lý cùng đọc và ghi một trạng thái dùng chung, cập nhật cùng một đối tượng nghiệp vụ, hoặc hoàn tất không theo thứ tự mong muốn.

Trước khi sửa lỗi, cần xác định channel đang phân phối message theo kiểu nào. `DirectChannel`, `ExecutorChannel`, `QueueChannel` và `PublishSubscribeChannel` có hành vi khác nhau. Đặc biệt, nhiều consumer cùng nghe một channel không phải lúc nào cũng có nghĩa là mỗi consumer đều nhận được một bản message.

## 1. Phân biệt các kiểu phân phối message

| Channel | Cách phân phối | Ý nghĩa khi có nhiều consumer |
| --- | --- | --- |
| `DirectChannel` | Subscribable, đồng bộ, point-to-point | Dispatcher chọn một subscriber cho mỗi lần gửi. Khi có nhiều subscriber, chiến lược mặc định thường phân phối luân phiên. Handler chạy trên thread gửi message. |
| `ExecutorChannel` | Subscribable, bất đồng bộ, point-to-point | Chọn một subscriber như `DirectChannel`, sau đó giao việc cho executor. Nhiều message có thể được xử lý đồng thời bởi các worker thread. |
| `QueueChannel` | Pollable, lưu message trong queue | Nhiều poller hoặc consumer cùng lấy message từ một queue. Mỗi lần `receive` thành công lấy một phần tử khỏi queue để một consumer xử lý. |
| `PublishSubscribeChannel` | Subscribable, broadcast | Mỗi subscriber đều nhận message. Nếu có executor, các subscriber có thể xử lý song song. Đây là fan-out có chủ đích, không phải nhóm consumer cạnh tranh để lấy một message. |

Với `DirectChannel`, việc gọi handler đồng bộ chỉ có nghĩa handler chạy trong thread gọi `send`. Nếu nhiều thread cùng gửi message, cùng một handler vẫn có thể được gọi đồng thời trên nhiều thread. `DirectChannel` không tự biến một handler có trạng thái dùng chung thành handler an toàn khi chạy đồng thời.

Với `QueueChannel`, nhiều poller có thể cạnh tranh lấy phần tử từ cùng queue. Một phần tử đã được một lần `receive` lấy ra sẽ không đồng thời được một poller khác lấy lại. Tuy vậy, nếu handler lỗi sau khi nhận message, việc message có được khôi phục hay không phụ thuộc vào loại channel, `MessageStore` và cấu hình transaction. Không nên mặc định rằng mọi lỗi xử lý đều tự động đưa message trở lại queue.

`PublishSubscribeChannel` có ngữ nghĩa khác hẳn: mọi subscriber đều được gọi. Nếu hai subscriber cùng sửa một payload mutable, chúng có thể ghi đè dữ liệu của nhau. Nếu mục tiêu là chia tải để mỗi message chỉ do một worker xử lý, hãy dùng mô hình point-to-point hoặc queue phù hợp.

## 2. Những race condition thường gặp

| Tình huống | Nguyên nhân | Biểu hiện |
| --- | --- | --- |
| Mất cập nhật (lost update) | Hai consumer cùng đọc một giá trị, cùng tính giá trị mới rồi ghi đè lẫn nhau | Bộ đếm hoặc số lượng tồn kho thấp hơn thực tế |
| Cập nhật sai thứ tự | Hai message của cùng một đơn hàng hoặc tài khoản được xử lý song song | Kết quả cuối cùng phản ánh dữ liệu cũ ghi sau dữ liệu mới |
| Chia sẻ payload mutable | Nhiều nhánh xử lý giữ cùng tham chiếu tới một object có thể thay đổi | Trường dữ liệu thay đổi khó dự đoán, log giữa các nhánh không nhất quán |
| Tác động nghiệp vụ bị lặp | Retry hoặc redelivery chạy lại handler sau khi một phần side effect đã hoàn tất | Gửi thông báo hai lần, trừ tiền hoặc tạo bản ghi trùng |
| Tranh chấp trạng thái correlation | Nhiều message cùng cập nhật một message group trong aggregator | Group không được giải phóng đúng lúc hoặc kết quả tổng hợp không như dự kiến |

### Ví dụ mất cập nhật

Đoạn code sau vẫn không an toàn dù dùng `ConcurrentHashMap`:

```java
private final ConcurrentMap<String, Integer> reserved = new ConcurrentHashMap<>();

void reserve(String sku) {
    int current = reserved.getOrDefault(sku, 0);
    reserved.put(sku, current + 1);
}
```

`getOrDefault` và `put` là hai thao tác riêng. Giả sử hai consumer cùng đọc giá trị `5`; cả hai đều tính ra `6`, sau đó cùng ghi `6`. Một lần reserve đã bị mất.

Nếu đây chỉ là bộ đếm trong bộ nhớ và phép cộng theo từng SKU là toàn bộ thao tác cần bảo vệ, có thể dùng thao tác nguyên tử theo key:

```java
void reserve(String sku) {
    reserved.merge(sku, 1, Integer::sum);
}
```

`merge` làm cho việc cập nhật một key trở thành một thao tác nguyên tử trong `ConcurrentHashMap`. Điều này không thay thế transaction cơ sở dữ liệu, không bảo vệ trạng thái giữa nhiều instance ứng dụng và cũng không tự kiểm tra quy tắc nghiệp vụ như giới hạn tồn kho.

Với dữ liệu nghiệp vụ quan trọng, hãy để cơ sở dữ liệu thực thi điều kiện cập nhật trong một câu lệnh nguyên tử, chẳng hạn:

```sql
UPDATE inventory
SET reserved = reserved + :quantity
WHERE sku = :sku
  AND reserved + :quantity <= available;
```

Consumer kiểm tra số dòng được cập nhật để biết thao tác có thành công hay đã vượt giới hạn. Với JPA, có thể dùng optimistic locking qua trường `@Version`; khi phát hiện xung đột, đọc lại dữ liệu và retry toàn bộ thao tác trong transaction mới. Pessimistic lock phù hợp với một số luồng tranh chấp cao, nhưng cần đánh giá thời gian giữ lock và nguy cơ deadlock.

## 3. Chủ động chọn mức đồng thời

Hãy xác định rõ mục tiêu của luồng trước khi tăng số worker:

- Nếu cần xử lý tuần tự trong cùng thread gửi, `DirectChannel` là lựa chọn đơn giản. Nó vẫn có thể nhận lời gọi đồng thời từ nhiều producer thread.
- Nếu cần chuyển việc sang worker thread, dùng `ExecutorChannel` và giới hạn kích thước pool cùng hàng đợi của executor.
- Nếu cần tách producer khỏi consumer bằng queue, dùng `QueueChannel` và cấu hình poller có chủ đích.
- Nếu mọi nhánh đều phải nhận message, dùng `PublishSubscribeChannel`; hãy thiết kế payload và side effect cho ngữ nghĩa broadcast.

Ví dụ tạo `ExecutorChannel` với pool có giới hạn:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("si-worker-");
    return executor;
}

@Bean
MessageChannel workChannel(ThreadPoolTaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
```

Các con số trên chỉ là ví dụ. Hãy chọn pool dựa trên thời gian xử lý, số kết nối cơ sở dữ liệu, khả năng của dịch vụ downstream và giới hạn tài nguyên của ứng dụng. Queue có giới hạn giúp kiểm soát lượng việc chờ trong bộ nhớ; cần theo dõi cả tình trạng queue đầy và chính sách từ chối task của executor.

Khi có nhiều flow đăng ký vào cùng `workChannel`, dispatcher của `ExecutorChannel` chọn một consumer cho mỗi message. Ví dụ hai flow có thể cùng đăng ký như sau:

```java
@Bean
IntegrationFlow consumerA(OrderHandlerA handler) {
    return IntegrationFlow.from("workChannel")
            .handle(handler, "handle")
            .get();
}

@Bean
IntegrationFlow consumerB(OrderHandlerB handler) {
    return IntegrationFlow.from("workChannel")
            .handle(handler, "handle")
            .get();
}
```

Hai flow trên là hai subscriber cạnh tranh nhận message. Chúng không cùng nhận một message như hai subscriber của `PublishSubscribeChannel`. Dù vậy, hai message khác nhau vẫn có thể được giao cho cùng một consumer ở những thời điểm chồng lấn nếu có nhiều worker thread.

Với `QueueChannel`, poller quyết định lúc nào consumer gọi `receive` và mỗi chu kỳ lấy bao nhiêu message. `maxMessagesPerPoll` là số message tối đa xử lý trong một lần poll; nó không phải số consumer. Muốn tăng mức đồng thời, cần cấu hình số poller hoặc executor phù hợp với phiên bản Spring Integration đang dùng. Ví dụ cấu hình Java DSL:

```java
@Bean
MessageChannel workQueue() {
    return new QueueChannel(500);
}

@Bean
IntegrationFlow queueConsumer(Executor workerExecutor, OrderHandler handler) {
    return IntegrationFlow.from("workQueue",
                    endpoint -> endpoint.poller(Pollers.fixedDelay(100)
                            .taskExecutor(workerExecutor)
                            .maxMessagesPerPoll(20)))
            .handle(handler, "handle")
            .get();
}
```

Khi triển khai nhiều poller cùng đọc một queue, hãy kiểm tra số lần poll thực tế, số task đồng thời và khả năng xử lý của downstream. Tăng `maxMessagesPerPoll` có thể tăng lượng việc một chu kỳ poll xử lý, nhưng tự nó không đảm bảo tăng số thread xử lý song song.

## 4. Bảo vệ thứ tự xử lý theo nghiệp vụ

Thứ tự gửi message không đồng nghĩa với thứ tự handler hoàn tất. Với nhiều producer, các lần gửi có thể chồng lấn. Với `ExecutorChannel` hoặc nhiều poller, message được lấy trước có thể hoàn tất sau message được lấy sau. `QueueChannel` mặc định dùng thứ tự queue khi lấy message, nhưng xử lý song song vẫn có thể làm thứ tự hoàn tất khác thứ tự lấy.

Nếu mọi message đều độc lập, xử lý song song thường phù hợp. Nếu các message cùng tác động một aggregate nghiệp vụ, hãy chọn một cơ chế giữ thứ tự theo khóa:

1. **Phân vùng theo khóa nghiệp vụ:** đưa các message có cùng `orderId`, `accountId` hoặc `customerId` vào cùng partition/queue và xử lý tuần tự trong partition đó.
2. **Khóa theo key:** chỉ khóa phần cập nhật cần tuần tự. Khóa Java trong một JVM không bảo vệ được nhiều instance; khi chạy nhiều instance cần cơ chế phối hợp dùng chung hoặc khóa ở cơ sở dữ liệu.
3. **Optimistic locking:** dùng version để phát hiện một consumer đã ghi trên phiên bản cũ. Retry phải đọc lại và tính lại toàn bộ thay đổi.
4. **Ràng buộc thứ tự trong dữ liệu:** lưu sequence/version của sự kiện và từ chối hoặc trì hoãn sự kiện cũ hơn trạng thái đã áp dụng.

Tránh khóa toàn bộ handler bằng `synchronized` nếu handler gọi dịch vụ chậm hoặc truy cập mạng. Cách đó thường làm giảm thông lượng và chỉ đồng bộ trong một instance. Chỉ dùng khóa khi đã xác định được trạng thái cần bảo vệ và phạm vi khóa phù hợp.

## 5. Kết hợp transaction, retry và idempotency

Transaction bảo vệ một nhóm thao tác trong cùng transaction manager; nó không tự giải quyết mọi race condition giữa các consumer. Cần đặt transaction bao quanh phần đọc, kiểm tra và ghi dữ liệu phải nhất quán. Với `DirectChannel`, handler chạy đồng bộ trên thread gửi nên có thể tham gia transaction gắn với thread đó nếu cấu hình phù hợp. `ExecutorChannel` chuyển xử lý sang thread khác; transaction context gắn với thread gửi không tự truyền sang worker. Hãy mở transaction tại consumer cho các thao tác dữ liệu của consumer.

Retry cũng có thể khiến một message được xử lý nhiều lần. Ví dụ handler đã gọi dịch vụ thanh toán thành công nhưng bị timeout trước khi nhận phản hồi. Retry có thể gọi thanh toán lần nữa dù lần đầu đã tạo side effect. Vì vậy, mỗi message có side effect cần một khóa idempotency ổn định, thường là `eventId` hoặc ID nghiệp vụ duy nhất.

Một mẫu phổ biến là ghi nhận `messageId` trong bảng inbox có unique constraint, rồi cập nhật dữ liệu nghiệp vụ trong cùng transaction:

```sql
INSERT INTO processed_message(message_id, processed_at)
VALUES (:messageId, CURRENT_TIMESTAMP);
```

Nếu khóa đã tồn tại, consumer nhận biết đây là message đã xử lý và bỏ qua side effect tương ứng. Việc ghi inbox và cập nhật nghiệp vụ phải nằm trong cùng transaction để không tạo trạng thái “đã đánh dấu nhưng chưa xử lý”. Với dịch vụ bên ngoài, hãy truyền idempotency key nếu dịch vụ hỗ trợ; nếu không, cần thiết kế đối soát hoặc quy trình xử lý kết quả không xác định.

Giới hạn số lần retry, dùng backoff cho lỗi tạm thời và đưa message không thể xử lý vào error flow hoặc dead-letter channel để điều tra. Không retry vô hạn một lỗi dữ liệu cố định. Với `QueueChannel`, hãy xác minh cụ thể hành vi rollback/khôi phục message của `MessageStore` đang dùng; transaction của cơ sở dữ liệu nghiệp vụ không tự bảo đảm việc nhận message từ mọi loại queue cũng được rollback nguyên tử.

## 6. Chú ý khi dùng aggregator và correlation

Aggregator gom nhiều message thành một message group, thường dựa trên correlation key. Nhiều message cùng correlation key có thể đến đồng thời, vì vậy message group store, thao tác cập nhật group và điều kiện release phải phù hợp với mức đồng thời của hệ thống.

- Dùng correlation key ổn định và phân biệt rõ các lần chạy nghiệp vụ khác nhau; không gom các message chỉ vì chúng có cùng loại.
- Chọn `MessageGroupStore` phù hợp. Khi chạy nhiều instance, store và cơ chế lock phải phối hợp được giữa các instance; lock chỉ nằm trong bộ nhớ của một JVM không đủ.
- Kiểm tra `sequenceNumber` và `sequenceSize` nếu luồng split/aggregate phụ thuộc vào số thứ tự và số lượng message dự kiến.
- Xác định cách xử lý message trùng, message đến muộn, group hết hạn và group không bao giờ đủ điều kiện release.
- Bảo đảm thao tác side effect sau khi aggregate cũng idempotent, vì việc retry hoặc phát lại message có thể khiến kết quả tổng hợp được xử lý lại.

Khi nghi ngờ race trong aggregator, hãy kiểm tra correlation key, trạng thái group trong store, lock đang dùng và log của các message thuộc cùng group. Đừng chỉ nhìn tổng số message vì hai group khác nhau có thể có cùng số lượng phần tử nhưng trạng thái hoàn toàn khác.

## 7. Chẩn đoán race condition khi chạy runtime

Để tái hiện và khoanh vùng lỗi, cần quan sát được message nào đang chạy trên thread nào và cùng tác động vào khóa nghiệp vụ nào.

**Ghi log có ngữ cảnh.** Ghi `messageId`, `correlationId`, khóa nghiệp vụ, tên endpoint và `Thread.currentThread().getName()`. Có thể bật message history của Spring Integration để theo dõi các component đã đi qua. Không ghi payload nhạy cảm hoặc toàn bộ header tùy tiện vào log.

**Theo dõi hàng đợi và executor.** Quan sát queue depth, tuổi của message lâu nhất, số thread active, kích thước pool, task đang chờ, task bị từ chối và thời gian xử lý handler. Với poller, theo dõi tần suất poll, số message mỗi chu kỳ và thời gian xử lý một lượt. Queue tăng liên tục thường cho thấy tốc độ tiêu thụ thấp hơn tốc độ nhận việc.

**Theo dõi xung đột dữ liệu.** Đếm lỗi optimistic locking, deadlock, lock wait, lỗi unique constraint, số lần retry và số message đi vào error flow. Nếu chỉ một `orderId` hoặc `accountId` xuất hiện trong nhiều log đồng thời, hãy kiểm tra xem luồng có cần tuần tự hóa theo key hay không.

**Chụp trạng thái thread khi bị treo.** Thread dump giúp tìm thread `BLOCKED`, `WAITING` hoặc chờ I/O; Java Flight Recorder có thể bổ sung dữ liệu về contention, thời gian CPU và hoạt động của thread pool. Đối chiếu thời điểm đó với queue depth và log message để tìm điểm nghẽn.

**Tạo tái hiện có kiểm soát.** Trong kiểm thử đồng thời, dùng `CountDownLatch` hoặc `CyclicBarrier` để buộc hai consumer cùng đọc trạng thái trước khi ghi. Cách này làm lộ lost update ổn định hơn việc dựa vào `Thread.sleep`. Kiểm tra bất biến nghiệp vụ sau khi xử lý nhiều message, gồm cả trường hợp cùng key, message trùng và lỗi xảy ra giữa chừng. Nếu hệ thống yêu cầu thứ tự, hãy kiểm tra thứ tự theo từng key thay vì giả định toàn hệ thống chỉ có một thứ tự toàn cục.

## 8. Quy trình xử lý khi phát hiện race

1. Xác định channel thực tế và loại endpoint đăng ký vào channel đó: subscriber, poller, aggregator hay service activator.
2. Xác định số producer thread, số consumer, executor, poller và số instance ứng dụng. Đừng suy ra mức đồng thời chỉ từ số bean hoặc số flow.
3. Chọn message và khóa nghiệp vụ có lỗi; dựng lại timeline đọc, kiểm tra, ghi, retry và side effect của từng consumer.
4. Phân loại nguyên nhân: cập nhật không nguyên tử, sai thứ tự, payload mutable, xử lý trùng hay tranh chấp message group.
5. Chọn cơ chế phù hợp: thao tác nguyên tử, transaction, optimistic/pessimistic locking, partition theo key, payload bất biến hoặc idempotency.
6. Kiểm thử với nhiều consumer và nhiều instance nếu môi trường production chạy phân tán. Đo lại throughput, độ trễ, queue depth và tỷ lệ retry sau khi sửa.

Một cấu hình nhiều consumer chỉ an toàn khi dữ liệu mà chúng cùng truy cập có quy tắc đồng bộ rõ ràng. Hãy quyết định phần nào được phép chạy song song, phần nào phải tuần tự theo khóa nghiệp vụ, và cách hệ thống nhận biết một message đã được áp dụng. Khi ba điều đó được xác định, việc chọn channel, executor, poller và transaction trong Spring Integration sẽ dễ kiểm soát hơn.
