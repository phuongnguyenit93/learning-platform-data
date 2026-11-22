# Đồng hồ, thứ tự sự kiện và quan hệ nhân quả trong hệ thống phân tán

## 1. Vì sao thời gian trở thành vấn đề trong Microservices?

Trong một tiến trình đơn, chương trình thường có một luồng thực thi hoặc cơ chế đồng bộ cho biết thao tác nào đi trước thao tác nào. Trong Microservices, các dịch vụ chạy trên nhiều máy, có đồng hồ riêng, trao đổi thông điệp qua mạng và có thể xử lý song song. Không có một đồng hồ vật lý toàn cục mà mọi tiến trình đều đọc với độ chính xác tuyệt đối.

Giả sử luồng đặt hàng gồm:

1. **Order Service** tạo đơn hàng.
2. **Payment Service** ghi nhận thanh toán sau khi nhận yêu cầu từ Order.
3. **Inventory Service** giữ hàng, độc lập với việc xử lý thanh toán.
4. **Shipping Service** chỉ được xuất hàng sau khi đã có cả xác nhận thanh toán và giữ hàng thành công.

Các câu hỏi cần giải đáp là: sự kiện nào xảy ra trước sự kiện nào, sự kiện nào có quan hệ nguyên nhân–kết quả, và sự kiện nào thực sự độc lập? Nếu Payment ghi thời gian 10:00:00.120 còn Order ghi 10:00:00.180, liệu Payment đã xảy ra trước Order? **Không thể kết luận như vậy chỉ từ hai timestamp**, vì đồng hồ của các máy có thể lệch nhau.

Bài này phân biệt ba khái niệm:

- **Thời gian vật lý (physical time):** gần với thời gian ngoài đời thực, hữu ích cho lịch, báo cáo, SLA và thời hạn.
- **Thứ tự (ordering):** quy tắc sắp xếp các sự kiện, có thể chỉ có trong từng tiến trình, từng aggregate hoặc trên toàn hệ thống.
- **Quan hệ nhân quả (causality):** sự kiện nào có thể ảnh hưởng đến sự kiện nào thông qua trình tự xử lý và trao đổi thông điệp.

Ba khái niệm có liên hệ nhưng không đồng nhất. Muốn thiết kế đúng phải chọn loại thông tin phù hợp với điều hệ thống cần bảo đảm.

## 2. Đồng hồ vật lý: wall clock, monotonic clock và sai lệch giữa các nút

### 2.1. Wall clock

Wall clock biểu diễn một thời điểm trên lịch, thường lưu bằng timestamp UTC: ví dụ 2026-11-11T03:45:12.345Z. Trong Java, có thể dùng **Instant.now()** cho mục đích ghi thời gian tạo bản ghi, thời gian hiển thị, audit hoặc đối soát.

Nhưng wall clock trên hai máy có thể không trùng nhau:

- **Clock offset/skew:** hai máy đang hiển thị thời gian khác nhau tại cùng một thời điểm thực.
- **Clock drift:** tốc độ chạy của đồng hồ không hoàn toàn giống nhau; sai lệch có thể tăng dần.
- **Điều chỉnh thời gian:** dịch vụ đồng bộ như NTP có thể điều chỉnh hoặc làm trôi tốc độ đồng hồ; cách hệ điều hành xử lý bước nhảy và leap second khác nhau.
- **Độ chính xác và độ phân giải:** timestamp có thể bị làm tròn, nhiều thao tác cùng giá trị dù diễn ra khác lúc.
- **Độ trễ mạng và xử lý:** thời điểm gửi, nhận, ghi vào database và hoàn tất giao dịch là những sự kiện khác nhau.

NTP/PTP giúp giảm sai lệch; chúng **không biến các timestamp thành bằng chứng chắc chắn về thứ tự nhân quả** trong mọi tình huống. Hạ tầng có đồng hồ đồng bộ tốt vẫn cần mô hình phân tán xử lý timeout, message delay và lỗi từng phần.

### 2.2. Monotonic clock

Monotonic clock dùng để đo **khoảng thời gian trong cùng một tiến trình hoặc miền đồng hồ**; nó được thiết kế để không đi ngược do việc chỉnh wall clock. Trong Java, dùng **System.nanoTime()** để tính thời gian đã trôi qua:

~~~java
long started = System.nanoTime();
try {
    processOrder();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordLatency(elapsedNanos);
}
~~~

Giá trị nanoTime không phải Unix timestamp. **Không gửi giá trị nanoTime của máy A sang máy B rồi so sánh trực tiếp**: hai máy không chia sẻ cùng một mốc đếm có ý nghĩa để so thứ tự hoặc độ trễ đầu cuối.

Khi cần xác định thời hạn trong tiến trình, hãy tính deadline từ monotonic clock và cấu hình timeout rõ ràng. Khi cần lưu lịch biểu diễn cho người dùng, dùng Instant/UTC. Các yêu cầu độ chính xác rất cao cần hiểu đặc tính hệ điều hành, độ lệch đồng hồ và hệ thống đồng bộ thời gian thực tế.

### 2.3. Minh họa lỗi khi sắp xếp theo thời gian ghi nhận

Giả sử đồng hồ Order đi nhanh 150 ms so với đồng hồ Payment:

| Sự kiện thực tế | Timestamp cục bộ được ghi |
| --- | --- |
| Order tạo đơn và gửi thông điệp | Order: 12:00:00.250 |
| Payment nhận thông điệp và chấp nhận thanh toán sau đó | Payment: 12:00:00.180 |

Nếu sắp xếp tăng dần theo timestamp, Payment xuất hiện trước Order, dù Payment chỉ có thể xảy ra sau khi nhận thông điệp của Order. Timestamp chỉ phản ánh quan sát tại từng máy; nó không diễn tả đầy đủ mối quan hệ nhân quả.

**Nguyên tắc:** lưu thời gian vật lý để quan sát và đối soát, nhưng dùng các cơ chế thứ tự và phiên bản nghiệp vụ khi tính đúng đắn phụ thuộc vào quan hệ trước–sau.

## 3. Quan hệ “happens-before” của Lamport

Ký hiệu **a → b** (“a happens-before b”) nghĩa là sự kiện a có quan hệ nhân quả đi trước b. Quan hệ này được xác định từ ba quy tắc:

1. **Thứ tự trong cùng một tiến trình:** nếu a diễn ra trước b theo thứ tự thực thi của một tiến trình, thì a → b.
2. **Gửi và nhận thông điệp:** nếu a là hành động gửi một thông điệp, b là hành động nhận chính thông điệp đó, thì a → b.
3. **Tính bắc cầu:** nếu a → b và b → c thì a → c.

Nếu cả a → b lẫn b → a đều không có, gọi a và b là **đồng thời về mặt nhân quả (concurrent)**, ký hiệu a ∥ b. “Concurrent” không có nghĩa hai sự kiện xảy ra đúng cùng một phần nghìn giây; nó có nghĩa mô hình không xác lập đường ảnh hưởng nhân quả giữa chúng.

### 3.1. Ví dụ ba dịch vụ

~~~text
Order Service           Payment Service         Inventory Service
     |                         |                         |
     | createOrder (a)         |                         |
     |--- OrderCreated ------->|                         |
     |                         | receive (b)             |
     |                         | authorize (c)           |
     |------ ReserveStock ------------------------------->|
     |                         |                         | reserve (d)
     |                         |                         |
~~~

Có thể khẳng định a → b → c khi a là sự kiện tạo và gửi OrderCreated, b nhận thông điệp, c thực hiện theo kết quả nhận. Việc giữ hàng d là một nhánh khác được kích hoạt sau a. **Không thể mặc định c → d hoặc d → c** nếu không có thông điệp hoặc phụ thuộc nào nối hai nhánh.

Bởi vậy Shipping không được kiểm tra “timestamp thanh toán lớn hơn timestamp giữ hàng” để quyết định điều kiện xuất hàng. Shipping cần biết **cả hai điều kiện nghiệp vụ đã hoàn tất**, bất kể chúng đến theo thứ tự nào.

### 3.2. Thứ tự một phần và thứ tự toàn phần

Happens-before tạo thành **thứ tự một phần (partial order)**: nó chỉ so sánh được những sự kiện có đường nhân quả. Một hệ thống có thể tạo **thứ tự toàn phần (total order)** bằng cách thêm quy tắc giải hòa để mọi cặp sự kiện đều so sánh được; ví dụ dùng số thứ tự kèm ID nút.

Điểm cần nhớ: **một thứ tự toàn phần được tạo ra không đồng nghĩa mọi cặp sự kiện đều có quan hệ nhân quả**. Việc gán sự kiện độc lập A đứng trước B là một quyết định sắp xếp, không chứng minh A gây ra B.

## 4. Lamport logical clock

Lamport clock là một bộ đếm logic giúp duy trì tính chất: **nếu a → b thì L(a) < L(b)**, trong đó L là timestamp logic của sự kiện.

Mỗi tiến trình i duy trì một số nguyên Li:

1. Trước một sự kiện cục bộ hoặc khi gửi thông điệp, tăng Li lên 1 và gắn giá trị mới cho sự kiện.
2. Khi gửi thông điệp, đính kèm Li.
3. Khi nhận thông điệp mang giá trị T, cập nhật Li = max(Li, T) + 1; sự kiện nhận mang giá trị vừa cập nhật.

### 4.1. Ví dụ tính từng bước

Giả sử Order và Payment bắt đầu với đồng hồ logic 0.

| Bước | Tiến trình | Hành động | Lamport clock |
| --- | --- | --- | --- |
| 1 | Order | Tạo đơn (sự kiện nội bộ) | 1 |
| 2 | Order | Gửi OrderCreated | 2, mang theo T=2 |
| 3 | Payment | Nhận OrderCreated | max(0, 2)+1 = 3 |
| 4 | Payment | Chấp nhận thanh toán | 4 |
| 5 | Inventory | Xử lý một tác vụ độc lập, bắt đầu từ 0 | 1 |

Order gửi thông điệp tại L=2 và Payment nhận tại L=3, nên hai sự kiện được đánh số đúng theo quan hệ gửi–nhận. Inventory có L=1 không có nghĩa sự kiện của Inventory đã xảy ra trước sự kiện Payment trong thời gian thực.

**Giới hạn:** chiều ngược lại không đúng: L(a) < L(b) **không đủ để kết luận a → b**. Một sự kiện ở tiến trình độc lập có thể có số nhỏ hơn nhưng không có quan hệ nhân quả.

Có thể tạo một thứ tự toàn phần ổn định bằng cặp **(Lamport timestamp, node ID)** và quy tắc so sánh từ trái sang phải. Đây vẫn chỉ là thứ tự được chọn khi cần phân xử, không phải phép đo thời gian thực.

### 4.2. Ví dụ triển khai tối thiểu bằng Java

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class LamportClock {
    private final AtomicLong value = new AtomicLong(0);

    // Gọi cho sự kiện nội bộ hoặc ngay trước khi gửi thông điệp.
    public long tick() {
        return value.incrementAndGet();
    }

    // Gọi khi nhận thông điệp có Lamport timestamp từ nút khác.
    public long onReceive(long remoteTimestamp) {
        return value.updateAndGet(
            current -> Math.max(current, remoteTimestamp) + 1
        );
    }

    public long current() {
        return value.get();
    }
}
~~~

Ví dụ sử dụng:

~~~java
LamportClock orderClock = new LamportClock();
LamportClock paymentClock = new LamportClock();

long sentTimestamp = orderClock.tick();            // 1
long receivedTimestamp =
        paymentClock.onReceive(sentTimestamp);      // 2
long authorizedTimestamp = paymentClock.tick();    // 3
~~~

Trong thực tế, gắn timestamp logic vào metadata của message và duy trì state đúng theo vòng đời của producer/consumer; khởi động lại tiến trình cần chiến lược giữ trạng thái hoặc đổi định danh epoch. Bộ đếm Java ở trên chỉ minh họa thuật toán cục bộ, chưa xử lý lưu bền, tràn số hay các đặc tính lỗi của hệ thống sản xuất.

## 5. Vector clock: nhận biết quan hệ nhân quả và sự kiện đồng thời

Lamport clock bảo đảm chiều a → b kéo theo timestamp tăng, nhưng không quyết định được hai sự kiện có concurrent hay không. **Vector clock** dùng một vector bộ đếm, mỗi thành phần gắn với một tiến trình hoặc tác nhân tham gia.

Với hai tiến trình A và B, vector có dạng [vA, vB]:

- Bắt đầu tại [0, 0].
- Mỗi sự kiện cục bộ tại A tăng thành phần A; tại B tăng thành phần B.
- Khi gửi, mang theo vector hiện tại.
- Khi nhận, lấy **max theo từng thành phần** giữa vector cục bộ và vector nhận, rồi tăng thành phần của tiến trình nhận.

### 5.1. So sánh hai vector

Với hai vector X và Y có cùng tập thành phần:

- **X < Y** khi với mọi i, X[i] ≤ Y[i] và tồn tại ít nhất một i có X[i] < Y[i]. Trong mô hình vector clock chuẩn, sự kiện X có quan hệ nhân quả trước sự kiện Y.
- **X = Y** khi từng thành phần bằng nhau.
- **X và Y concurrent** nếu có thành phần X lớn hơn Y và có thành phần khác X nhỏ hơn Y; không vector nào nhỏ hơn vector kia theo thứ tự thành phần.

Ví dụ:

| Sự kiện | Vector clock | Kết luận |
| --- | --- | --- |
| A chỉnh sửa hồ sơ độc lập | [1, 0] | — |
| B chỉnh sửa hồ sơ độc lập | [0, 1] | [1,0] và [0,1] concurrent |
| B nhận bản cập nhật A rồi xử lý tiếp | [1, 2] | [1,0] < [1,2] và [0,1] < [1,2] |

Khi A và B chỉnh cùng một đối tượng trong lúc mất kết nối, hai bản cập nhật concurrent có thể cần **phát hiện xung đột và hòa giải**, thay vì chọn bản có timestamp vật lý mới nhất rồi âm thầm mất dữ liệu.

### 5.2. Chi phí của vector clock

Vector clock cần metadata tăng theo số tác nhân; quản lý thành viên tham gia, restart, xoá thành phần và quy mô lớn phức tạp. Hệ thống thực tế có thể dùng version vector, dotted version vector hoặc cơ chế chuyên biệt khác. Không nhất thiết áp dụng vector clock cho mọi API; nhiều luồng nghiệp vụ chỉ cần version tăng dần theo aggregate hoặc một hàng đợi có thứ tự trong phạm vi khóa.

## 6. Hybrid Logical Clock (HLC) và ranh giới sử dụng

**Hybrid Logical Clock** kết hợp giá trị thời gian vật lý với thành phần logic để cung cấp timestamp gần với wall clock, đồng thời giữ một số bảo đảm về thứ tự nhân quả khi các nút trao đổi metadata đúng giao thức.

HLC thường được biểu diễn bằng cặp như **(physical, logical)**. Khi đồng hồ vật lý không tiến đủ nhanh để phân biệt sự kiện hoặc khi nhận timestamp lớn hơn từ nút khác, thành phần logic giúp giữ thứ tự. Điều này hữu ích trong một số cơ sở dữ liệu phân tán và quy trình quản lý phiên bản.

Cần phân biệt:

- **Lamport clock:** đơn giản, bảo đảm thứ tự tăng theo happens-before, không phản ánh giờ thực.
- **Vector clock:** có thể phân biệt nhân quả với đồng thời trong mô hình tác nhân đã định nghĩa; metadata lớn hơn.
- **HLC:** gần với thời gian vật lý và duy trì ràng buộc nhân quả nhất định; **không mặc nhiên thay thế vector clock** để kết luận hai cập nhật có concurrent.
- **Timestamp UTC:** phù hợp cho lịch, audit và hiển thị; tự nó không tạo bảo đảm thứ tự nhân quả.

Chọn cơ chế theo invariant cần giữ, thay vì đưa mọi loại timestamp vào một trường rồi cho rằng chúng có cùng ý nghĩa.

## 7. Các cấp độ thứ tự trong Microservices

| Phạm vi cần thứ tự | Có thể đạt bằng | Giới hạn quan trọng |
| --- | --- | --- |
| Trong một luồng hoặc một transaction cục bộ | Thứ tự chương trình, lock, giao dịch DB | Không tự lan qua các tiến trình khác. |
| Trong một aggregate (ví dụ cùng orderId) | Version tăng dần, optimistic concurrency, single writer hoặc partition theo khóa | Chỉ bảo đảm cho aggregate/khóa được định nghĩa. |
| Trong một partition của message log | Offset và thứ tự log của partition | Không bảo đảm thứ tự chung giữa nhiều partition; xử lý song song cần giữ đúng thứ tự cần thiết. |
| Thứ tự nhân quả giữa các dịch vụ | Quan hệ thông điệp, metadata logic/causal dependency | Chỉ so sánh những sự kiện có quan hệ nhân quả; các sự kiện độc lập có thể concurrent. |
| Một thứ tự toàn phần trên phạm vi xác định | Sequencer/leader, replicated log hay giao thức đồng thuận | Thêm phối hợp, chi phí và giới hạn thông lượng/độ trễ; phải nêu rõ phạm vi và mô hình lỗi. |

**“Message broker bảo đảm ordering” là phát biểu thiếu phạm vi.** Ví dụ với Apache Kafka, thứ tự offset được duy trì **trong từng partition**, không phải toàn topic khi có nhiều partition. Producer, consumer và quy trình retry cần được cấu hình và thiết kế để duy trì thứ tự xử lý nghiệp vụ cần thiết; một consumer xử lý đa luồng hoặc gửi lại vào luồng khác có thể làm kết quả xử lý lệch thứ tự nhận.

Không có một “total order tự nhiên” cho tất cả sự kiện trên mọi máy. Nếu thực sự cần thứ tự toàn phần để xử lý một tài nguyên chung, phải chỉ rõ cơ chế xác lập thứ tự, thời điểm commit và cách xử lý failover. Đôi khi chỉ cần thứ tự **theo từng đơn hàng**, giúp hệ thống phân tán tải tốt hơn.

## 8. Thứ tự đến, thứ tự xử lý và thứ tự nghiệp vụ không giống nhau

Một event có thể trải qua các mốc:

1. Nghiệp vụ phát sinh tại producer.
2. Dữ liệu được commit vào database.
3. Event được đưa vào outbox hoặc broker.
4. Broker xác nhận đã lưu event.
5. Consumer nhận event.
6. Consumer hoàn thành xử lý và commit trạng thái.
7. Consumer xác nhận đã xử lý.

Các mốc này có timestamp khác nhau. Một consumer nhanh có thể hoàn thành trước consumer nhận event sớm hơn. Khi network retry, event gửi trước cũng có thể đến sau. Cần ghi rõ trường timestamp đại diện cho mốc nào, ví dụ **occurredAt**, **publishedAt**, **ingestedAt**, **processedAt**, không dùng chung một trường mơ hồ.

Ví dụ một luồng cập nhật trạng thái:

~~~text
OrderCreated (version 1)
OrderPaid    (version 2)
OrderShipped (version 3)
~~~

Nếu consumer nhận version 3 trước version 2, không được suy ra đơn đã thanh toán chỉ vì 3 có timestamp lớn. Có thể dùng state machine cùng version và cơ chế phát hiện thiếu sự kiện: chỉ áp dụng version kế tiếp, chờ sự kiện thiếu, đọc lại snapshot đáng tin cậy hoặc yêu cầu tái đồng bộ.

Tùy nghiệp vụ, consumer có thể xử lý event cũ bằng cách bỏ qua nếu state đã mới hơn, nhưng phải chứng minh hành vi là an toàn. Chẳng hạn cập nhật một giá trị cộng dồn không thể đơn giản “bỏ event cũ” nếu mỗi event mang một delta cần áp dụng chính xác một lần.

## 9. Thiết kế event metadata để tái dựng quan hệ

Một schema event tối thiểu hữu ích có thể chứa:

~~~json
{
  "eventId": "evt_9a7c",
  "eventType": "OrderPaid",
  "aggregateType": "Order",
  "aggregateId": "order-123",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-11T10:20:30.450Z",
  "correlationId": "checkout-77",
  "causationId": "evt_9a6b",
  "producer": "payment-service",
  "payload": {
    "paymentId": "pay-456",
    "status": "AUTHORIZED"
  }
}
~~~

Ý nghĩa chính:

- **eventId:** định danh ổn định để phát hiện giao hàng lặp.
- **aggregateId:** khóa nghiệp vụ cho ordering/routing theo từng đối tượng.
- **aggregateVersion:** thứ tự thay đổi được nguồn sở hữu cấp cho cùng aggregate; cần quản lý tăng số một cách nguyên tử.
- **occurredAt:** thời gian vật lý để quan sát; không dùng một mình để áp các quy tắc nhân quả.
- **correlationId:** nối các hoạt động cùng một yêu cầu hoặc workflow cho tracing.
- **causationId:** chỉ sự kiện/yêu cầu trực tiếp kích hoạt event hiện tại; giúp tái dựng đồ thị nhân quả ở mức ứng dụng.
- **producer:** nguồn phát sinh và phạm vi chịu trách nhiệm.

Không nhất thiết mọi event đều cần mọi trường. Không cho rằng correlationId tự bảo đảm thứ tự: nhiều event cùng correlationId vẫn có thể chạy song song. CausationId giúp truy vết khi producer thiết lập đúng, nhưng không thay thế transaction, version hay các quy tắc kiểm soát trạng thái.

## 10. Những mẫu thiết kế xử lý đúng sự kiện ngoài thứ tự

### 10.1. Optimistic concurrency và version theo aggregate

Với trạng thái Order, cơ sở dữ liệu có thể kiểm tra version cũ trước khi cập nhật:

~~~sql
UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE id = :orderId
  AND version = :expectedVersion
  AND status = 'AWAITING_PAYMENT';
~~~

Nếu số hàng bị cập nhật bằng 0, phải đọc trạng thái hiện tại và quyết định đó là xung đột, event lặp, trạng thái không hợp lệ hay cần retry. Đừng tăng version mù hoặc ghi đè theo timestamp từ dịch vụ khác.

Bộ đếm version theo aggregate thường đủ cho nhiều use case có **một nguồn sở hữu trạng thái**. Nếu có nhiều writer độc lập chấp nhận ghi đồng thời, cần cơ chế giải quyết tranh chấp rõ hơn.

### 10.2. Transactional outbox để gắn dữ liệu và event

Nếu cập nhật đơn hàng thành công nhưng service chết trước khi publish event, các hệ thống khác không biết trạng thái mới. Mẫu **transactional outbox** ghi thay đổi nghiệp vụ và bản ghi event trong **cùng transaction cục bộ**. Sau đó worker/CDC đưa event ra broker.

Outbox xử lý khoảng hở giữa commit và publish, nhưng **không tự bảo đảm chỉ giao một lần**; khi retry vẫn có thể phát event lặp. Consumer cần idempotency hoặc deduplication, và publisher cần giữ thứ tự thích hợp cho aggregate khi có nhiều worker. Nếu dùng CDC, hiểu rõ thứ tự commit có thể được bảo toàn trong log nguồn ở phạm vi nào và việc phân phối sang broker thay đổi ra sao.

### 10.3. Idempotent consumer và deduplication

Khi nhận lại eventId đã xử lý, consumer phải không tạo thêm tác động không mong muốn. Một phương án là lưu eventId đã xử lý trong bảng dedup cùng transaction với cập nhật nghiệp vụ. Một phương án khác là thiết kế thao tác đặt trạng thái có điều kiện thay vì cộng/trừ không kiểm soát.

Không nhầm **idempotent** với **có thứ tự**. Hai bản sao của cùng event có thể được xử lý an toàn nhờ dedup, nhưng hai event hợp lệ về cùng aggregate vẫn có thể cần version để phân định thứ tự.

### 10.4. Giữ, xử lý lại hoặc tái đồng bộ khi thiếu tiền đề

Nếu Shipping nhận OrderShipped trước OrderPaid (do đường truyền, retry hoặc sai logic upstream), các lựa chọn gồm:

- Giữ event chờ tiền đề kèm timeout và giới hạn bộ đệm.
- Đọc trạng thái chuẩn từ service chủ sở hữu.
- Từ chối chuyển trạng thái và đưa vào retry/DLQ có kiểm soát.
- Đưa workflow về trạng thái cần hòa giải nếu đã có side effect không thể đảo.

Việc chờ vô hạn khiến hệ thống nghẽn; cần có cảnh báo khi thiếu event, cấu hình replay và quy trình xử lý thủ công cho ngoại lệ. Không dùng sleep cố định để “đợi event tới đúng thứ tự”.

### 10.5. Saga và quan hệ nhân quả nghiệp vụ

Saga điều phối các bước giao dịch xuyên dịch vụ và hành động bù trừ khi lỗi. Saga giúp thể hiện **thứ tự phụ thuộc** (chẳng hạn PaymentAuthorized mới được ConfirmOrder), nhưng không tự biến toàn bộ hệ thống thành một transaction ACID. Một bước bù trừ không nhất thiết xóa hoàn toàn tác động đã quan sát bên ngoài.

Cần phân biệt điều kiện “Payment và Inventory đều xong” với yêu cầu “Payment phải diễn ra trước Inventory”. Hai bước đầu có thể concurrent; chỉ bước Shipping phụ thuộc cả hai kết quả.

## 11. Event time, processing time và dữ liệu đến muộn

Trong xử lý stream, có ít nhất hai khái niệm:

- **Event time:** thời điểm sự kiện được cho là phát sinh tại nguồn, có thể bị lệch đồng hồ hoặc đến muộn.
- **Processing time:** thời điểm hệ thống xử lý stream nhận và tính toán event.

Ví dụ một lượt mua phát sinh lúc 10:02 theo nguồn nhưng do mất mạng tới hệ thống tổng hợp lúc 10:09. Nếu thống kê “số đơn mỗi 5 phút” theo event time, lượt mua có thể thuộc cửa sổ 10:00–10:05 dù đến sau khi cửa sổ ban đầu được tính.

**Watermark** là cơ chế ước lượng tiến độ event time để hệ thống biết khi nào có thể đóng/hoàn thiện một cửa sổ theo chính sách chấp nhận dữ liệu đến muộn. Watermark không bảo đảm rằng sẽ không còn bất kỳ event cũ nào; cần quyết định cách xử lý dữ liệu rất muộn: cập nhật lại kết quả, phát correction, đưa vào side output hoặc bỏ theo hợp đồng sản phẩm.

Đặc biệt, **event time window không giải quyết mặc nhiên causal ordering**. Một bảng điều khiển doanh thu có thể cho phép cập nhật lại số liệu; trạng thái thanh toán hoặc tồn kho lại cần invariant và state transition chặt chẽ hơn.

## 12. Một ví dụ từ đầu đến cuối: Checkout có event đến sai thứ tự

Giả sử Order Service cấp version tăng dần cho mỗi đơn. Payment và Inventory xử lý hai nhánh song song; Order nhận các kết quả rồi ra quyết định.

~~~text
Order #O42:
v1: OrderCreated
      |
      +----> PaymentAuthorized ----+
      |                            |
      +----> StockReserved --------+--> OrderConfirmed (v2)
                                             |
                                             +--> ShipmentRequested
~~~

Giả sử các timestamp được ghi:

| Event | Thời gian trên service phát sinh | Quan hệ quan trọng |
| --- | --- | --- |
| OrderCreated | 10:00:00.200 | Tiền đề của hai yêu cầu Payment và Inventory. |
| PaymentAuthorized | 10:00:00.150 | Vẫn xảy ra sau khi Payment nhận yêu cầu; đồng hồ Payment chạy chậm. |
| StockReserved | 10:00:00.310 | Song song về nhân quả với PaymentAuthorized nếu không có phụ thuộc thêm. |
| OrderConfirmed | 10:00:00.275 | Chỉ được tạo khi đã biết cả Payment và Inventory thành công; đồng hồ Order lệch. |

Thứ tự timestamp là PaymentAuthorized → OrderCreated → OrderConfirmed → StockReserved, nhưng **đó không phải thứ tự hợp lệ của workflow**.

Thiết kế phù hợp:

1. Order sở hữu state machine của đơn và tăng version theo từng lần chuyển trạng thái được commit.
2. Các sự kiện phản hồi có eventId/correlationId, được dedup khi nhận.
3. PaymentAuthorized và StockReserved có thể tới theo thứ tự bất kỳ; Order ghi nhận hai cờ điều kiện riêng.
4. Chỉ khi đủ điều kiện và chuyển trạng thái thành công, Order phát OrderConfirmed từ outbox.
5. Shipping xử lý OrderConfirmed bằng idempotency và kiểm tra trạng thái hợp lệ, thay vì dựa trên chênh lệch timestamp.
6. Tracing dùng correlationId/causationId để tái dựng luồng; timestamp UTC phục vụ theo dõi độ trễ với lưu ý sai lệch đồng hồ.

Cách làm này diễn tả **quan hệ nhân quả bằng trạng thái, thông điệp và điều kiện nghiệp vụ**, còn thời gian vật lý chỉ là dữ liệu quan sát bổ sung.

## 13. Kiểm thử các giả định về thời gian và thứ tự

Các bài thử có giá trị cho Microservices thường chủ động gây ra những tình huống mà môi trường phát triển ít gặp:

- **Clock skew:** cho các service ghi timestamp với độ lệch giả lập; bảo đảm dữ liệu nghiệp vụ vẫn hợp lệ.
- **Reorder:** giao event version n+1 trước n; xác minh consumer đợi, retry hoặc tái đồng bộ theo hợp đồng.
- **Duplicate delivery:** gửi lại cùng eventId, kiểm tra side effect chỉ xuất hiện theo thiết kế.
- **Delayed delivery:** giữ event nhiều giây hoặc phút, kiểm tra timeout và xử lý trễ.
- **Concurrent updates:** hai tiến trình cùng sửa một aggregate, kiểm tra optimistic lock hoặc conflict resolution.
- **Consumer restart:** khởi động lại giữa cập nhật database và acknowledgment; xác minh không mất tác vụ, xử lý retry đúng.
- **Partition/failover:** cắt kết nối hoặc đổi leader/worker, kiểm tra ordering scope và replay.
- **Late stream events:** gửi event của cửa sổ đã qua watermark; kiểm tra chính sách correction hoặc bỏ qua.

Điều quan trọng là test **invariant nghiệp vụ**. Ví dụ, “không xuất hàng trước khi thỏa điều kiện thanh toán và tồn kho”, “một giao dịch không bị trừ tiền hai lần”, “version đã commit không bị bản cũ ghi đè”. Kiểm tra rằng log được sắp xếp đẹp theo timestamp là chưa đủ.

## 14. Chọn cơ chế theo câu hỏi cần trả lời

| Câu hỏi nghiệp vụ/kỹ thuật | Cơ chế nên xem xét |
| --- | --- |
| Giao dịch diễn ra vào ngày giờ nào để hiển thị hoặc audit? | Timestamp UTC có nguồn và định nghĩa mốc rõ ràng. |
| Một hàm mất bao lâu để chạy? | Monotonic clock trong cùng tiến trình. |
| Sau khi nhận message, làm sao đảm bảo timestamp logic tăng? | Lamport clock hoặc cơ chế logical time phù hợp. |
| Hai phiên bản có quan hệ nhân quả hay concurrent? | Vector clock/version vector hoặc tracking causal dependency. |
| Cập nhật Order nào mới hơn trong cùng nguồn sở hữu? | Aggregate version, optimistic concurrency và state machine. |
| Giữ thứ tự event cho cùng một orderId? | Partition theo orderId và/hoặc single writer, version trong consumer. |
| Cần thứ tự toàn phần cho mọi thao tác trên tài nguyên chung? | Sequencer, leader log hoặc cơ chế đồng thuận với phạm vi rõ ràng. |
| Tính báo cáo theo thời điểm event thực sự phát sinh? | Event time, window, watermark và chính sách late data. |
| Tái dựng đường đi của request xuyên dịch vụ? | Trace context, correlationId, causationId và log có timestamp. |

Các lựa chọn có thể kết hợp. Ví dụ Order Service dùng transaction + aggregateVersion để giữ tính đúng đắn, Kafka partition key theo orderId để giảm khả năng đảo thứ tự, outbox để tránh mất event, và tracing với timestamp UTC để vận hành.

## 15. Câu hỏi tự luyện và đáp án

### Bài 1: Timestamp nhỏ hơn có xảy ra trước không?

Service A gửi thông điệp lúc đồng hồ A hiển thị 15:30:10.200. Service B nhận thông điệp đó lúc đồng hồ B hiển thị 15:30:10.150. Event nào trước?

**Đáp án:** Hành động gửi trước hành động nhận theo quan hệ happens-before. Timestamp vật lý không đủ tin cậy để đảo kết luận này; đồng hồ hai service có thể lệch.

### Bài 2: Hai vector clock có đồng thời không?

Cho X = [3, 1, 0] và Y = [2, 2, 0]. Quan hệ giữa X và Y?

**Đáp án:** Concurrent. X lớn hơn Y ở thành phần thứ nhất nhưng nhỏ hơn ở thành phần thứ hai. Không vector nào nhỏ hơn vector kia theo thứ tự thành phần.

### Bài 3: Hai event có cùng aggregateId nhưng đến đảo thứ tự

Consumer nhận OrderUpdated version 8 trước version 7. Có nên sắp xếp bằng occurredAt để áp version 7 rồi 8?

**Đáp án:** Không cần và không nên dựa vào occurredAt để xác lập thứ tự nghiệp vụ. Dùng version từ nguồn sở hữu và chính sách xử lý event thiếu: giữ version 8, chờ hoặc lấy lại version 7/snapshot khi phù hợp, và áp trạng thái theo invariant.

### Bài 4: Có cần global total order cho toàn bộ đơn hàng?

Một sàn thương mại có hàng triệu đơn độc lập nhưng chỉ cần bảo đảm cập nhật đúng thứ tự trong **mỗi** đơn. Cần một sequencer duy nhất cho mọi đơn không?

**Đáp án:** Thường không. Có thể thiết kế ordering theo orderId/aggregate và phân vùng tải; global total order làm tăng phối hợp không cần thiết. Chỉ chọn thứ tự toàn phần rộng hơn nếu một invariant thật sự liên kết các đơn.

## 16. Tóm tắt kiến thức cốt lõi

1. **Wall clock cho biết giờ quan sát**, không tự chứng minh nhân quả giữa các máy. Dùng monotonic clock để đo khoảng thời gian cục bộ.
2. **Happens-before** dựa trên thứ tự tiến trình, gửi–nhận thông điệp và tính bắc cầu; nhiều cặp sự kiện có thể concurrent.
3. **Lamport clock** bảo đảm quan hệ nhân quả kéo theo số logic tăng; số logic tăng không chứng minh nhân quả theo chiều ngược lại.
4. **Vector clock** phân biệt được trước–sau nhân quả và concurrent trong mô hình của nó, với chi phí metadata lớn hơn.
5. **HLC** cân bằng thông tin gần thời gian vật lý với thứ tự logic, nhưng không tự động giải quyết mọi xung đột hoặc bảo đảm total order toàn cục.
6. **Ordering phải được nêu rõ phạm vi**: trong transaction, theo aggregate, theo partition, theo nhân quả hoặc toàn cục.
7. Với Microservices, tính đúng đắn thường đến từ **state machine, aggregate version, idempotency, outbox và invariant nghiệp vụ**; timestamp và tracing đóng vai trò hỗ trợ quan sát.

Câu hỏi cần đặt ra khi thiết kế không chỉ là “sự kiện nào có timestamp nhỏ hơn?”, mà là **“hệ thống có bằng chứng gì về quan hệ trước–sau, và quy tắc nghiệp vụ thực sự cần loại thứ tự nào?”**