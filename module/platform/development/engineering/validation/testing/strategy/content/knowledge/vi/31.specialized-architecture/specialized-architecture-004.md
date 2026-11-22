# Kiểm chứng hệ thống hướng sự kiện với kết quả nhất quán sau một khoảng thời gian

**Chương:** Kiến trúc đặc thù  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Trong hệ thống hướng sự kiện, một thao tác có thể được tiếp nhận thành công trước khi mọi thành phần liên quan hoàn tất xử lý. Dịch vụ đơn hàng phát sự kiện `OrderCreated`, consumer cập nhật kho, dịch vụ thanh toán ghi nhận giao dịch và projection phục vụ truy vấn được cập nhật sau đó. Trong khoảng chuyển tiếp, các thành phần có thể quan sát những trạng thái khác nhau. Sau khi các sự kiện được xử lý và truyền đi, hệ thống cần hội tụ về trạng thái nhất quán theo các quy tắc đã thiết kế.

Kiểm chứng tính nhất quán sau một khoảng thời gian (eventual consistency) là xác minh rằng hệ thống duy trì các bất biến cần thiết trong suốt quá trình xử lý bất đồng bộ và cuối cùng đạt trạng thái mong đợi trong giới hạn thời gian phù hợp. Test phải xem xét cả việc sự kiện được phát, giao nhận, xử lý, thử lại, chống trùng, cập nhật dữ liệu và phản ánh trên các read model. Chỉ kiểm tra phản hồi HTTP ban đầu hoặc chờ một khoảng thời gian cố định rồi đọc dữ liệu thường không đủ để chứng minh hành vi đúng.

Bài học này trình bày mô hình nhất quán trong hệ thống hướng sự kiện, cách xác định bất biến và điều kiện hội tụ, thiết kế test bất đồng bộ có thời hạn, kiểm tra thứ tự và sự kiện trùng, xác minh outbox/inbox và projection, xử lý lỗi và dead-letter, cũng như xây dựng môi trường kiểm thử có thể quan sát và tái lập.

Sau bài học, người học có thể:

- Giải thích eventual consistency và phân biệt nó với các mức nhất quán khác.
- Xác định bất biến an toàn, điều kiện tiến triển và trạng thái cuối cần đạt.
- Thiết kế test kiểm tra hội tụ mà không phụ thuộc vào thời gian chờ tùy tiện.
- Kiểm chứng giao nhận ít nhất một lần, sự kiện trùng, thứ tự và xử lý idempotent.
- Kiểm tra outbox, inbox, retry, dead-letter và phục hồi consumer.
- Xác minh projection, read model và các luồng CQRS sau khi xử lý sự kiện.
- Kiểm tra tính nhất quán trong điều kiện tải, lỗi mạng và nhiều consumer.
- Thu thập bằng chứng, đo độ trễ hội tụ và phân loại lỗi đáng tin cậy.

## 1. Hệ thống hướng sự kiện và eventual consistency

Hệ thống hướng sự kiện (event-driven system) sử dụng sự kiện để thông báo rằng một điều đã xảy ra. Producer phát sự kiện; broker hoặc nền tảng truyền thông điệp; consumer nhận và xử lý để cập nhật trạng thái, kích hoạt hành động hoặc tạo sự kiện tiếp theo.

Ví dụ một hành trình đặt hàng:

1. Order Service ghi nhận đơn hàng và phát `OrderCreated`.
2. Inventory Service nhận sự kiện và giữ hàng.
3. Payment Service xử lý yêu cầu thanh toán và phát `PaymentAuthorized` hoặc `PaymentFailed`.
4. Order Service nhận kết quả và cập nhật trạng thái đơn hàng.
5. Search/Reporting Projection nhận các sự kiện và cập nhật dữ liệu phục vụ truy vấn.

Các bước không nhất thiết xảy ra đồng thời. Producer có thể trả về sau khi lưu đơn hàng và sự kiện vào outbox, trong khi consumer vẫn đang xử lý. Một truy vấn ngay sau đó có thể thấy đơn hàng nhưng chưa thấy trạng thái kho hoặc thanh toán mới.

### 1.1. Eventual consistency là gì?

Eventual consistency là đặc tính trong đó các bản sao hoặc thành phần dữ liệu phân tán có thể tạm thời khác nhau, nhưng nếu không có cập nhật mới và quá trình truyền/xử lý tiếp tục thành công, chúng sẽ hội tụ về trạng thái nhất quán theo mô hình đã định.

Khái niệm “cuối cùng” không có nghĩa hệ thống được phép hội tụ vô hạn mà không có giới hạn vận hành. Sản phẩm thường cần một mục tiêu thời gian hoặc SLO cho các luồng quan trọng, ví dụ projection cập nhật trong percentile 95 dưới một số giây ở tải bình thường. Test nên xác minh cả tính đúng đắn và giới hạn thời gian đã cam kết.

### 1.2. Vì sao có trạng thái tạm thời khác nhau?

Các nguyên nhân phổ biến:

- Producer và consumer hoạt động độc lập.
- Broker lưu thông điệp trước khi consumer xử lý.
- Consumer xử lý theo batch hoặc có độ trễ.
- Retry làm một thông điệp được xử lý muộn hơn.
- Partition và nhiều worker tạo ra thứ tự xử lý khác nhau.
- Read model được cập nhật bất đồng bộ.
- Mạng, database hoặc dịch vụ phụ thuộc tạm thời không sẵn sàng.
- Consumer bị dừng, khởi động lại hoặc chuyển partition.

Những khác biệt tạm thời có thể được chấp nhận nếu chúng nằm trong hợp đồng nhất quán. Những trạng thái vi phạm bất biến, như thu tiền hai lần hoặc giữ hàng vượt số lượng tồn, không được biện minh bằng eventual consistency.

### 1.3. Phân biệt với các mô hình nhất quán khác

| Mô hình/đặc tính | Kỳ vọng | Câu hỏi kiểm thử |
|---|---|---|
| Strong consistency | Sau khi thao tác hoàn tất theo hợp đồng, các lần đọc liên quan thấy giá trị mới nhất | Đọc ngay sau ghi có phản ánh kết quả đã xác nhận không? |
| Read-your-writes | Một người dùng hoặc phiên đọc được thay đổi do chính mình vừa ghi | Người tạo đơn có thấy đơn vừa tạo trong truy vấn tiếp theo không? |
| Monotonic reads | Một client không nhìn thấy phiên bản cũ hơn sau khi đã thấy phiên bản mới hơn | Trạng thái đã thấy là `PAID` có bị quay lại `PENDING` trong cùng luồng đọc không? |
| Causal consistency | Các thao tác có quan hệ nhân quả được quan sát theo thứ tự phù hợp | Kết quả thanh toán có được nhìn thấy sau sự kiện tạo đơn làm tiền đề không? |
| Eventual consistency | Các bản sao có thể tạm lệch nhưng sẽ hội tụ khi xử lý hoàn tất | Các read model có đạt trạng thái mong đợi trong giới hạn không? |

Một hệ thống có thể cung cấp các bảo đảm khác nhau ở các ranh giới khác nhau. Ví dụ, ghi vào cơ sở dữ liệu chính có thể nhất quán mạnh, trong khi projection tìm kiếm được cập nhật eventual. Test cần xác định chính xác hợp đồng của từng API hoặc luồng dữ liệu.

## 2. Xác định điều gì phải nhất quán

Trước khi viết test, cần xác định trạng thái nào có thể tạm thời khác nhau và trạng thái nào luôn phải đúng. Nếu không định nghĩa rõ, test dễ hoặc quá chặt (đòi hỏi mọi thành phần cập nhật tức thì) hoặc quá lỏng (chấp nhận mọi sai lệch miễn là chờ đủ lâu).

### 2.1. Xác định bất biến (invariants)

Bất biến là điều kiện phải luôn đúng trong mọi trạng thái được hệ thống cho phép. Ví dụ:

- Một giao dịch thanh toán không được ghi nhận thành công nhiều hơn một lần cho cùng một yêu cầu idempotent.
- Số lượng hàng đã giữ không được vượt quá số lượng có thể bán theo chính sách tồn kho.
- Một đơn hàng không thể chuyển từ trạng thái cuối `CANCELLED` trở lại `PAID` nếu không có quy trình nghiệp vụ mới được phép.
- Mỗi sự kiện thuộc một aggregate có định danh và phiên bản hợp lệ.
- Tổng tiền thanh toán phải khớp với số tiền của đơn hàng theo quy tắc đã xác nhận.
- Một message đã được xác nhận xử lý không được làm mất tác dụng nghiệp vụ.

Bất biến cần được diễn đạt bằng dữ liệu có thể quan sát, không chỉ bằng câu “hệ thống phải đúng”.

### 2.2. Phân biệt safety và liveness

- **Safety:** điều xấu không được xảy ra. Ví dụ không thu tiền hai lần, không phát hành hàng trước khi thanh toán hợp lệ, không làm mất sự kiện đã xác nhận lưu bền vững.
- **Liveness:** điều tốt cuối cùng phải xảy ra. Ví dụ đơn hàng hợp lệ cuối cùng chuyển sang trạng thái đã xác nhận, projection cuối cùng phản ánh sự kiện mới hoặc message lỗi tạm thời cuối cùng được xử lý sau retry.

Eventual consistency chủ yếu liên quan đến tiến triển và hội tụ, nhưng không được đánh đổi safety. Một test tốt kiểm tra cả bất biến trong suốt quá trình và trạng thái cuối.

### 2.3. Định nghĩa trạng thái cuối mong đợi

Với mỗi luồng, xác định:

- Aggregate hoặc entity chính.
- Sự kiện đầu vào và các sự kiện tiếp theo.
- Trạng thái hợp lệ cuối cùng.
- Read model hoặc hệ thống phụ cần hội tụ.
- Quan hệ dữ liệu cần giữ.
- Những trạng thái trung gian được phép.
- Trạng thái không bao giờ được phép.

Ví dụ, sau `OrderCreated` và `PaymentAuthorized`, Order Service có thể chuyển đơn sang `CONFIRMED`, Inventory Service giữ hàng và Order Projection hiển thị trạng thái xác nhận. Trong thời gian chờ, projection có thể vẫn là `PENDING`; nhưng không được hiển thị `CANCELLED` nếu không có sự kiện hủy hợp lệ.

### 2.4. Xác định ranh giới nhất quán

Không nên giả định mọi dữ liệu đều hội tụ cùng lúc. Hãy xác định ranh giới:

- Trong một aggregate hoặc một database transaction.
- Giữa producer và broker.
- Giữa broker và consumer.
- Giữa service ghi (write model) và projection đọc (read model).
- Giữa các service nghiệp vụ.
- Giữa hệ thống nội bộ và nhà cung cấp bên ngoài.

Mỗi ranh giới có thể có cơ chế đảm bảo và thời hạn khác nhau. Test cần quan sát đúng điểm cần xác minh.

## 3. Thiết kế điều kiện hội tụ và giới hạn thời gian

Một test eventual consistency cần biết thế nào là hội tụ và phải đợi tối đa bao lâu. Chờ vô hạn làm test treo; chờ một khoảng cố định rồi đọc một lần tạo flaky test.

### 3.1. Định nghĩa predicate hội tụ

Predicate là điều kiện có thể đánh giá đúng/sai để xác định trạng thái mong đợi đã xuất hiện. Ví dụ:

- Projection chứa đúng `orderId` và trạng thái `CONFIRMED`.
- Số lượng bản ghi liên quan bằng một.
- Tổng tiền đọc từ read model bằng giá trị mong đợi.
- Consumer offset đã vượt qua vị trí của sự kiện cần kiểm tra.
- Không còn message của test trong hàng đợi xử lý hoặc trạng thái pending tương ứng.
- Tất cả service liên quan đều phản ánh cùng một version nghiệp vụ.

Không nên chỉ kiểm tra “có bản ghi”. Bản ghi có thể đã được tạo nhưng chưa có trường quan trọng, hoặc chứa phiên bản cũ.

### 3.2. Dùng thời hạn có căn cứ

Thời hạn kiểm tra cần dựa trên SLO, độ trễ quan sát được, kích thước dữ liệu, tải và loại môi trường. Có thể dùng một giới hạn tối đa cho test, ví dụ 5 giây trong môi trường tích hợp nhanh, nhưng con số phải phù hợp với hệ thống.

Không nên chọn timeout quá sát mức trung bình. Hãy xem percentile cao, biến động và thời gian khởi động consumer. Với test hiệu năng, đo phân bố độ trễ riêng thay vì chỉ dùng một timeout đủ rộng để test pass.

### 3.3. Polling đến khi điều kiện đúng

Thay vì ngủ một khoảng cố định, test nên kiểm tra điều kiện lặp lại với khoảng nghỉ hợp lý và deadline rõ ràng.

Ví dụ Java với Awaitility:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        OrderView view = orderQuery.findById(orderId);
        assertNotNull(view);
        assertEquals("CONFIRMED", view.status());
        assertEquals(expectedTotal, view.total());
    });
```

Đoạn mã minh họa cách chờ predicate thay vì dùng `Thread.sleep`. Nếu dự án không dùng Awaitility, có thể xây dựng helper polling tương đương. Helper cần deadline, khoảng polling, xử lý lỗi truy vấn tạm thời và thông báo timeout có bằng chứng hữu ích.

### 3.4. Không biến polling thành che giấu lỗi

Polling chỉ nên chờ những trạng thái được phép đến muộn. Không nên bắt mọi exception rồi bỏ qua cho đến hết timeout. Nếu truy vấn trả lỗi xác thực, schema sai hoặc dữ liệu không hợp lệ, test nên thất bại ngay. Chỉ retry lỗi tạm thời đã được xác định.

Khi hết hạn, thông báo cần có:

- ID của entity hoặc correlation ID.
- Trạng thái thực tế cuối cùng.
- Predicate chưa thỏa mãn.
- Thời gian đã chờ và số lần polling.
- Sự kiện/offset/consumer liên quan nếu có.
- Log hoặc trace để tiếp tục điều tra.

### 3.5. Xác định trạng thái ổn định

Một predicate đúng một lần chưa chắc chứng minh hệ thống đã ổn định. Nếu trạng thái có thể bị cập nhật muộn bởi sự kiện cũ hoặc consumer khác, cần kiểm tra version, sequence hoặc quan sát trong một khoảng ổn định phù hợp.

Ví dụ, sau khi projection đạt `CONFIRMED`, test có thể xác minh version không giảm và trạng thái không bị ghi đè bởi event cũ trong khoảng theo dõi. Không cần đợi tùy tiện nếu hệ thống có version/sequence rõ ràng để chứng minh tính đơn điệu.

## 4. Kiểm chứng luồng phát và giao nhận sự kiện

Một trạng thái cuối đúng có thể che giấu lỗi trong đường đi sự kiện nếu một thành phần khác vô tình tạo ra cùng kết quả. Khi cần xác minh pipeline, hãy kiểm tra cả event được tạo, lưu bền vững, truyền và xử lý.

### 4.1. Xác minh producer phát sự kiện đúng

Kiểm tra:

- Đúng loại event và schema version.
- Đúng aggregate/entity ID.
- Đúng event ID hoặc message ID.
- Đúng timestamp, correlation ID và causation ID nếu hợp đồng có.
- Payload phản ánh trạng thái đã commit.
- Không phát event cho transaction đã rollback.
- Event không chứa dữ liệu nhạy cảm ngoài hợp đồng.

### 4.2. Xác minh lưu bền vững trước khi xác nhận

Nếu producer dùng broker hoặc outbox, cần kiểm tra semantics của bước xác nhận. Một API có thể trả thành công khi event đã được lưu trong outbox nhưng chưa được broker nhận. Hợp đồng cần nói rõ “đã chấp nhận” nghĩa là gì.

Test cần tạo lỗi giữa bước ghi dữ liệu và phát event để xác minh không có trạng thái commit mà thiếu sự kiện cần thiết, hoặc event được phát khi transaction nghiệp vụ chưa commit.

### 4.3. Kiểm tra giao nhận ít nhất một lần

Nhiều broker cung cấp semantics at-least-once: message có thể được giao lại nếu consumer xử lý xong nhưng chưa xác nhận offset/ack trước khi bị dừng. Consumer phải an toàn khi nhận cùng event nhiều lần.

Test nên mô phỏng:

- Consumer nhận event và xử lý thành công.
- Consumer bị dừng trước khi ack.
- Broker giao lại event.
- Consumer xử lý lần giao lại mà không tạo tác dụng phụ trùng.

Không giả định broker chỉ giao một lần nếu hợp đồng không bảo đảm điều đó. “Exactly once” ở một tầng kỹ thuật cũng không tự bảo đảm mọi tác dụng phụ xuyên nhiều database và dịch vụ chỉ xảy ra đúng một lần.

### 4.4. Kiểm tra ack và commit offset

Xác minh consumer chỉ ack/commit sau khi tác dụng cần bảo vệ đã được lưu bền vững theo thiết kế. Nếu ack trước khi ghi database và tiến trình bị dừng, message có thể mất khỏi luồng xử lý trong khi dữ liệu chưa được cập nhật.

Với xử lý theo batch, cần kiểm tra lỗi ở giữa batch và semantics commit offset để không bỏ sót hoặc xử lý sai phạm vi message.

## 5. Kiểm tra sự kiện trùng và tính idempotent

Trong hệ thống phân tán, giao nhận lại là điều có thể xảy ra. Idempotency giúp một thao tác được áp dụng nhiều lần nhưng tạo cùng hiệu ứng nghiệp vụ như áp dụng một lần.

### 5.1. Xác định khóa chống trùng

Khóa có thể là event ID, message ID, idempotency key hoặc tổ hợp aggregate ID và sequence tùy hợp đồng. Cần xác định phạm vi duy nhất và thời gian lưu khóa.

Không dùng payload hash tùy tiện nếu hai sự kiện hợp lệ có payload giống nhau nhưng mang ý nghĩa khác nhau. Định danh phải phản ánh danh tính sự kiện theo thiết kế.

### 5.2. Phát lại cùng một event

Test gửi cùng event nhiều lần và xác minh:

- Tác dụng nghiệp vụ chỉ được áp dụng một lần theo yêu cầu.
- Không tạo bản ghi, giao dịch hoặc thông báo trùng.
- Consumer vẫn ghi nhận việc nhận/giao lại theo cơ chế quan sát.
- Kết quả cuối không phụ thuộc số lần giao lại.
- Event khác ID nhưng payload giống nhau vẫn được xử lý theo quy tắc nghiệp vụ, không bị loại nhầm.

### 5.3. Idempotency trong consumer

Một cách triển khai phổ biến là lưu event ID đã xử lý cùng cập nhật nghiệp vụ trong một transaction phù hợp. Nếu cập nhật dữ liệu thành công nhưng ghi dấu đã xử lý thất bại, message có thể được giao lại và tạo hiệu ứng trùng. Test cần kiểm tra ranh giới transaction và unique constraint.

Ví dụ pseudocode:

```java
@Transactional
public void handle(OrderCreated event) {
    if (processedEventRepository.exists(event.eventId())) {
        return;
    }

    inventoryRepository.reserve(event.orderId(), event.items());
    processedEventRepository.insert(event.eventId());
}
```

Ví dụ giả định thao tác giữ hàng và ghi event đã xử lý cùng tham gia một transaction. Nếu chúng ở hai hệ thống lưu trữ khác nhau, cần một thiết kế khác như inbox, idempotency key ở downstream hoặc quy trình đối soát; không thể giả định `@Transactional` bao trùm các hệ thống độc lập.

### 5.4. Kiểm tra tác dụng phụ bên ngoài

Với email, thanh toán hoặc gọi API đối tác, database transaction nội bộ không thể tự rollback tác dụng phụ đã xảy ra bên ngoài. Test cần xác minh idempotency key được truyền đến provider, trạng thái không xác định được xử lý bằng truy vấn/đối soát và retry không tạo giao dịch thứ hai.

## 6. Kiểm chứng thứ tự sự kiện và sự kiện đến muộn

Không phải mọi broker bảo đảm thứ tự toàn cục. Nhiều hệ thống chỉ bảo đảm thứ tự trong một partition hoặc một khóa. Test cần phản ánh đúng hợp đồng thay vì giả định mọi sự kiện luôn đến theo thời gian tạo.

### 6.1. Xác định phạm vi ordering

Làm rõ:

- Thứ tự có được bảo đảm toàn cục, theo partition, theo key hay không?
- Producer có thể gửi đồng thời nhiều event cho cùng aggregate không?
- Consumer có xử lý song song không?
- Có sequence/version để phát hiện event cũ không?
- Sự kiện có thể bị replay hoặc đến muộn sau retry không?

### 6.2. Kiểm tra event đến sai thứ tự

Ví dụ, `OrderPaid` đến trước `OrderCreated` do đường truyền hoặc cấu hình consumer. Hệ thống có thể:

- Tạm lưu event và chờ tiền đề.
- Từ chối và retry.
- Đưa vào hàng đợi xử lý lại.
- Chấp nhận nếu trạng thái hiện tại đã đủ thông tin.

Test cần xác minh đúng chính sách. Không nên tự chọn một cách xử lý mà hợp đồng nghiệp vụ chưa quy định.

### 6.3. Sequence/version và chống ghi đè bởi event cũ

Nếu event mang version hoặc sequence, consumer có thể từ chối event cũ hơn version đã xử lý. Test tạo chuỗi version 1, 3, 2 và xác minh:

- Version 3 không bị ghi đè bởi version 2 đến muộn.
- Khoảng trống version 2 được xử lý theo chính sách (chờ, replay hoặc reconciliation).
- Event trùng cùng version không tạo tác dụng phụ mới.
- Trạng thái cuối phản ánh quy tắc chuyển trạng thái hợp lệ.

Không phải mọi event đều có thể sắp xếp chỉ bằng timestamp vì đồng hồ giữa producer có thể lệch. Sequence theo aggregate hoặc offset broker thường cung cấp thông tin thứ tự đáng tin hơn trong phạm vi được định nghĩa.

### 6.4. Kiểm tra sự kiện trễ và thời gian hết hạn

Một sự kiện có thể đến sau khi trạng thái nghiệp vụ đã thay đổi. Ví dụ `PaymentAuthorized` đến sau khi đơn đã bị hủy. Test cần xác minh hệ thống có từ chối chuyển trạng thái không hợp lệ, kích hoạt hoàn tiền hoặc đưa vào quy trình đối soát theo quy tắc.

## 7. Kiểm tra Outbox và Inbox pattern

Outbox và inbox thường được dùng để tăng độ tin cậy khi dữ liệu nghiệp vụ và sự kiện cần được phối hợp qua ranh giới phân tán.

### 7.1. Transactional outbox

Producer ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction database. Một publisher riêng đọc outbox và gửi event đến broker. Điều này giảm nguy cơ commit dữ liệu nhưng mất event hoặc phát event cho transaction đã rollback.

Test nên kiểm tra:

- Khi transaction nghiệp vụ commit, bản ghi outbox tương ứng tồn tại.
- Khi transaction rollback, không có event nghiệp vụ được phát.
- Publisher có thể gửi lại bản ghi chưa được đánh dấu đã gửi.
- Nếu publisher gửi thành công nhưng lỗi trước khi cập nhật trạng thái outbox, lần chạy sau không tạo tác dụng nghiệp vụ trùng ở consumer.
- Bản ghi lỗi có trạng thái và cơ chế xử lý rõ.
- Outbox được dọn dẹp theo chính sách sau khi bảo đảm truy vết.

### 7.2. Inbox hoặc processed-message store

Consumer có thể lưu message ID đã xử lý để chống trùng. Test cần kiểm tra:

- Cùng message ID được giao nhiều lần chỉ tạo một hiệu ứng.
- Message ID khác nhau không bị gộp nhầm.
- Dấu đã xử lý và cập nhật nghiệp vụ có tính nguyên tử trong phạm vi thiết kế.
- Lỗi trước commit cho phép xử lý lại an toàn.
- Dữ liệu inbox được giữ đủ lâu so với cửa sổ replay.

### 7.3. Kiểm tra điểm lỗi giữa các bước

Với outbox/inbox, tạo lỗi ở các ranh giới:

1. Trước commit transaction.
2. Sau commit nhưng trước khi publisher đọc outbox.
3. Sau khi gửi broker nhưng trước khi đánh dấu outbox đã gửi.
4. Sau khi consumer nhận message nhưng trước khi cập nhật dữ liệu.
5. Sau cập nhật dữ liệu nhưng trước ack/commit offset.

Ở mỗi điểm, xác minh không mất dữ liệu/sự kiện và không tạo tác dụng phụ vượt quy tắc. Chỉ mô phỏng crash ở môi trường kiểm thử có thể reset và quan sát.

## 8. Kiểm chứng projection và kiến trúc CQRS

Trong CQRS, write model nhận lệnh và cập nhật trạng thái nghiệp vụ; read model/projection được xây dựng từ sự kiện để phục vụ truy vấn. Hai mô hình có thể tạm thời khác nhau.

### 8.1. Xác minh projection cuối cùng

Sau khi phát sinh command hoặc event, test cần poll read model đến khi:

- Entity xuất hiện với đúng định danh.
- Các trường quan trọng có giá trị mong đợi.
- Version hoặc sequence đã đạt mức cần thiết.
- Tổng hợp và quan hệ dữ liệu nhất quán.
- Không có bản ghi trùng hoặc dữ liệu cũ ghi đè.

### 8.2. Kiểm tra read-your-writes nếu có cam kết

Một hệ thống eventual vẫn có thể cung cấp read-your-writes cho người tạo dữ liệu bằng cách trả về write model, dùng session token hoặc chờ projection đạt version yêu cầu. Nếu sản phẩm có cam kết này, test phải xác minh đúng ranh giới người dùng/phiên, không suy ra từ eventual consistency chung.

### 8.3. Kiểm tra rebuild và replay projection

Projection thường có thể được xây dựng lại từ event log. Test cần kiểm tra:

- Replay từ checkpoint hoặc từ đầu tạo ra cùng trạng thái logic.
- Replay không tạo tác dụng phụ ngoài ý muốn.
- Event schema cũ được xử lý theo chính sách versioning.
- Projection mới có thể chạy song song và được so sánh trước khi chuyển truy vấn.
- Khi replay thất bại, checkpoint không vượt qua event chưa được xử lý đúng.

### 8.4. Kiểm tra xóa và tombstone

Xóa dữ liệu trong hệ thống hướng sự kiện có thể được biểu diễn bằng event hoặc tombstone. Test cần xác minh projection loại bỏ hoặc đánh dấu dữ liệu theo hợp đồng, không để bản ghi cũ xuất hiện trở lại khi event đến trễ hoặc projection replay.

## 9. Kiểm tra retry, backoff và dead-letter queue

Retry giúp xử lý lỗi tạm thời nhưng có thể tạo tải, kéo dài thời gian hội tụ hoặc làm thông điệp lặp. Chính sách cần giới hạn và có quan sát.

### 9.1. Phân loại lỗi có thể retry

Ví dụ lỗi tạm thời có thể retry:

- Timeout mạng ngắn.
- Database tạm thời không sẵn sàng.
- Rate limit có hướng dẫn thời gian chờ.
- Broker hoặc dependency đang phục hồi.

Lỗi không thể giải quyết bằng retry lặp lại như schema không hợp lệ, dữ liệu thiếu bắt buộc hoặc lỗi logic cần được phân loại riêng. Chính sách có thể đưa chúng vào dead-letter hoặc luồng xử lý ngoại lệ.

### 9.2. Kiểm tra backoff và giới hạn

Test xác minh:

- Số lần retry tối đa.
- Khoảng backoff và jitter theo cấu hình.
- Retry không tạo tải tăng đột biến không kiểm soát.
- Thời gian hội tụ vẫn nằm trong giới hạn khi lỗi tạm thời được phục hồi.
- Hết số lần retry dẫn đến trạng thái rõ ràng.

Không cần chờ toàn bộ thời gian backoff thực trong mọi unit test. Có thể inject clock/scheduler hoặc dùng cấu hình test rút ngắn; cần có integration test xác minh cấu hình thực tế ở mức phù hợp.

### 9.3. Dead-letter queue (DLQ)

Khi message không thể xử lý sau chính sách retry, nó có thể được đưa vào DLQ. Test cần xác minh:

- Message được chuyển đúng DLQ và giữ metadata cần thiết.
- Lý do lỗi và số lần thử được ghi nhận.
- Không mất correlation ID hoặc event ID.
- Alert/metric được phát khi DLQ tăng.
- Quy trình sửa dữ liệu hoặc code rồi replay được kiểm soát.
- Replay không tạo hiệu ứng trùng.

DLQ không phải nơi để bỏ quên thông điệp. Cần có owner, thời hạn xử lý và quy trình đối soát.

### 9.4. Kiểm tra phục hồi consumer

Dừng consumer, tạo backlog, khởi động lại và xác minh:

- Consumer tiếp tục từ offset/checkpoint đúng.
- Message chưa xử lý không bị mất.
- Message đã xử lý không tạo tác dụng phụ trùng.
- Lag giảm về mức bình thường trong giới hạn đã xác định.
- Các partition được gán lại và xử lý đúng.

## 10. Kiểm tra saga và quy trình nhiều dịch vụ

Saga điều phối một nghiệp vụ qua nhiều bước cục bộ, có thể dùng choreography hoặc orchestration. Không có một transaction ACID duy nhất bao trùm toàn bộ dịch vụ.

### 10.1. Xác định trạng thái và chuyển tiếp hợp lệ

Với mỗi bước, ghi:

- Event/command kích hoạt.
- Điều kiện tiền đề.
- Trạng thái thành công.
- Lỗi có thể xảy ra.
- Hành động bù (compensation) nếu có.
- Trạng thái cuối và điều kiện kết thúc.

Ví dụ đặt hàng: tạo đơn → giữ hàng → ủy quyền thanh toán → xác nhận đơn. Nếu thanh toán thất bại sau khi giữ hàng, hệ thống có thể phát lệnh giải phóng hàng.

### 10.2. Kiểm tra cả đường thành công và bù trừ

Test cần bao gồm:

- Mọi bước thành công và saga hoàn tất.
- Một bước thất bại và các bước bù được kích hoạt.
- Lệnh bù bị retry hoặc đến trùng.
- Sự kiện thành công đến muộn sau khi quy trình đã bù.
- Orchestrator/consumer khởi động lại giữa chừng.
- Một bước bù thất bại và cần xử lý thủ công.

### 10.3. Không giả định compensation là rollback

Compensation là hành động nghiệp vụ mới, không nhất thiết xóa được tác dụng phụ trước đó. Ví dụ hoàn tiền không làm cho giao dịch chưa từng xảy ra. Test cần xác minh trạng thái lịch sử và kết quả bù, không chỉ mong dữ liệu quay lại y hệt ban đầu.

## 11. Kiểm tra tính nhất quán dưới tải và lỗi

Hệ thống có thể hội tụ ở tải thấp nhưng không đáp ứng khi backlog tăng, consumer chậm hoặc dependency bị giới hạn.

### 11.1. Đo propagation lag

Propagation lag là thời gian từ khi event được tạo/commit đến khi trạng thái đích phản ánh event. Cần định nghĩa mốc bắt đầu và kết thúc, dùng timestamp có nguồn đáng tin và tránh so sánh đồng hồ lệch giữa máy.

Đo theo percentile và phân đoạn theo loại event, partition, consumer hoặc môi trường. Giá trị trung bình có thể che giấu một nhóm thông điệp bị chậm lâu.

### 11.2. Kiểm tra backlog và khả năng bắt kịp

Tạo tải có kiểm soát rồi giảm hoặc dừng producer, quan sát consumer có xử lý backlog và đưa lag về mức bình thường không. Xác minh không mất message, không tạo trùng và thời gian hội tụ phù hợp mục tiêu.

### 11.3. Kiểm tra partition và consumer scale

Tăng/giảm số consumer hoặc thay đổi assignment trong môi trường test để xác minh:

- Thứ tự trong phạm vi partition được giữ theo hợp đồng.
- Không có hai consumer cùng tạo tác dụng phụ ngoài thiết kế.
- Rebalance không làm mất hoặc xử lý sai message.
- Checkpoint/offset được quản lý đúng.
- Lag sau scale có xu hướng giảm theo kỳ vọng.

### 11.4. Kiểm tra lỗi phụ thuộc

Mô phỏng broker mất kết nối, database chậm, consumer crash hoặc provider trả lỗi. Quan sát hệ thống duy trì safety và tiếp tục hội tụ khi dependency phục hồi.

### 11.5. Tách kiểm thử chức năng và hiệu năng

Một test chức năng có timeout đủ rộng không thay thế kiểm thử tải. Kiểm thử chức năng xác minh trạng thái cuối đúng trong giới hạn hợp lý; kiểm thử hiệu năng đo phân bố latency, throughput, backlog và khả năng phục hồi ở tải đã định nghĩa.

## 12. Xây dựng môi trường kiểm thử bất đồng bộ

Test eventual consistency cần kiểm soát được event, dữ liệu và consumer nhưng vẫn đủ gần với hạ tầng thực tế.

### 12.1. Dùng định danh riêng cho mỗi test

Tạo aggregate ID, correlation ID, tenant hoặc namespace riêng. Điều này giúp lọc đúng sự kiện và tránh test này đọc nhầm dữ liệu của test khác.

Không dùng một topic hoặc tài khoản dùng chung mà không có quy tắc cô lập. Nếu test chạy song song, dữ liệu và subscription phải được phân tách phù hợp.

### 12.2. Khởi tạo và dọn dẹp có kiểm soát

Test nên:

- Tạo dữ liệu cần thiết qua API hoặc fixture đã định nghĩa.
- Xác minh consumer và broker sẵn sàng.
- Ghi nhận offset hoặc watermark trước khi phát event nếu cần.
- Phát event có correlation ID duy nhất.
- Chờ predicate hội tụ.
- Thu thập trạng thái và trace.
- Dọn dữ liệu hoặc namespace sau khi hoàn tất.

Cleanup không nên xóa dữ liệu trước khi đã lưu bằng chứng thất bại. Nếu test bị timeout, giữ đủ thông tin để điều tra theo chính sách lưu trữ.

### 12.3. Chờ theo event hoặc watermark khi có thể

Polling read model là cách phổ biến, nhưng một test harness có thể theo dõi event ID, offset hoặc watermark để biết consumer đã đi qua vị trí cần thiết. Đây là bằng chứng mạnh hơn một khoảng sleep cố định.

Tuy nhiên, offset đã vượt qua một event không chứng minh projection cập nhật đúng. Vẫn cần xác minh trạng thái nghiệp vụ cuối.

### 12.4. Cô lập consumer và subscription

Kiểm tra test có dùng consumer group riêng hay không, cách reset offset và cách tránh đọc message cũ. Reset offset trên một consumer group dùng chung có thể ảnh hưởng test khác hoặc môi trường khác.

### 12.5. Dùng broker thật và broker mô phỏng đúng mục tiêu

Broker thật trong container hoặc môi trường tích hợp phù hợp để kiểm tra partition, ack, offset, persistence và rebalance. Fake broker phù hợp với unit test logic xử lý event. Một fake không chứng minh semantics thực của broker; cần integration test ở ranh giới quan trọng.

## 13. Thiết kế bộ test theo tầng

Không cần xác minh mọi tình huống bất đồng bộ ở E2E. Chia test theo câu hỏi giúp suite nhanh, rõ và dễ chẩn đoán.

| Tầng | Nội dung phù hợp | Phụ thuộc |
|---|---|---|
| Unit | State transition, idempotency logic, sequence/version, mapping | Event fixture, fake repository, clock/scheduler kiểm soát |
| Component | Consumer handler và xử lý lỗi cục bộ | Fake broker/client, database test hoặc adapter giả |
| Contract | Event schema, version, required fields, compatibility | Schema registry/contract fixture/provider verification |
| Integration | Publish, ack, retry, outbox/inbox, projection và transaction | Broker/database thật trong môi trường kiểm thử |
| System/E2E | Luồng nhiều service và trạng thái nghiệp vụ cuối | Các service đại diện, broker và dependency test |
| Performance/resilience | Lag, backlog, throughput, recovery và rebalance | Môi trường có năng lực và tải được kiểm soát |

### 13.1. Unit test cho consumer

Kiểm tra logic với event fixture xác định: trạng thái hợp lệ, event trùng, event cũ, payload thiếu, version sai và lỗi nghiệp vụ. Không cần broker thật cho mọi nhánh.

### 13.2. Integration test cho đường đi event

Xác minh producer ghi event, broker truyền, consumer xử lý và dữ liệu được cập nhật. Dùng correlation ID và trạng thái đọc lại để nối các bước.

### 13.3. E2E cho hành trình đại diện

Giữ một số luồng quan trọng như tạo đơn, giữ hàng, thanh toán và xác nhận. E2E nên kiểm tra trạng thái cuối và bất biến chính, không phụ thuộc vào một thứ tự nội bộ không được cam kết.

### 13.4. Resilience test cho lỗi và phục hồi

Tạo lỗi có kiểm soát ở broker, consumer hoặc dependency; xác minh retry, DLQ, replay và hội tụ. Những test này cần môi trường riêng và giới hạn tải để tránh ảnh hưởng hệ thống khác.

## 14. Ví dụ tổng hợp: đơn hàng và projection tìm kiếm

Giả sử khi tạo đơn hàng, Order Service ghi đơn và phát `OrderCreated`. Search Projection nhận sự kiện và cập nhật tài liệu tìm kiếm. API đọc đơn từ projection có thể trả dữ liệu cũ trong một khoảng ngắn.

### 14.1. Hợp đồng cần xác minh

- API tạo đơn trả về `orderId` và xác nhận đơn đã được ghi theo hợp đồng.
- Event có `eventId`, `orderId`, version và correlation ID.
- Projection cuối cùng có đúng `orderId`, trạng thái và tổng tiền.
- Projection không tạo tài liệu trùng cho cùng order.
- Nếu event được giao lại, kết quả cuối không đổi.
- Projection hội tụ trong giới hạn thời gian đã đặt cho môi trường kiểm thử.

### 14.2. Kịch bản test

1. Tạo đơn với ID riêng cho test.
2. Ghi nhận correlation ID và vị trí event nếu broker hỗ trợ.
3. Gọi API đọc projection ngay sau khi tạo và chấp nhận trạng thái chưa cập nhật nếu hợp đồng cho phép.
4. Poll đến khi projection có trạng thái và tổng tiền mong đợi, với deadline rõ ràng.
5. Phát lại cùng event hoặc mô phỏng giao lại.
6. Xác minh chỉ có một tài liệu logic và version không giảm.
7. Lưu thời gian hội tụ, số lần polling và trace.

### 14.3. Ví dụ pseudocode

```java
String orderId = UUID.randomUUID().toString();
String correlationId = UUID.randomUUID().toString();

CreateOrderResult created = orderClient.create(
    validOrderRequest(orderId, correlationId));

assertEquals(orderId, created.orderId());

await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        SearchOrderView view = searchClient.find(orderId);
        assertNotNull(view);
        assertEquals("CREATED", view.status());
        assertEquals(expectedTotal, view.total());
        assertEquals(1, searchClient.countByOrderId(orderId));
    });
```

Pseudocode giả định API tìm kiếm có thể trả về kết quả chưa có trong giai đoạn hội tụ và test có quyền truy vấn theo ID. Nếu endpoint trả `404` tạm thời, helper cần coi riêng trạng thái “chưa có” là có thể chờ, nhưng vẫn thất bại ngay với lỗi xác thực, lỗi schema hoặc lỗi không retry được.

### 14.4. Kiểm tra event trùng và đến muộn

Gửi lại cùng `eventId`, sau đó xác minh projection không tăng số tài liệu và không lặp tác dụng phụ. Gửi một event version cũ sau version mới, xác minh projection không bị ghi đè. Nếu hợp đồng yêu cầu event gap phải được xử lý bằng replay, kiểm tra cơ chế đó riêng.

### 14.5. Tiêu chí kết luận

Test đạt khi trạng thái cuối đúng, các bất biến không bị vi phạm, sự kiện trùng không tạo hiệu ứng lặp và thời gian hội tụ nằm trong giới hạn. Nếu hết deadline, báo cáo cần nêu trạng thái projection, offset/lag, consumer và trace để xác định lỗi nằm ở producer, broker, consumer hay read model.

## 15. Ví dụ: thanh toán và giữ hàng qua saga

Một luồng khác gồm giữ hàng, thanh toán và xác nhận đơn. Các thao tác diễn ra ở nhiều service và không có transaction toàn cục.

### 15.1. Các bất biến

- Không xác nhận đơn nếu thanh toán bị từ chối.
- Không giữ hàng vượt tồn kho có thể bán.
- Một payment authorization không được áp dụng hai lần.
- Nếu thanh toán thất bại sau khi giữ hàng, hàng phải được giải phóng theo chính sách.
- Nếu hủy đơn xảy ra trước khi kết quả thanh toán đến muộn, hệ thống phải xử lý theo quy tắc bù trừ.

### 15.2. Kịch bản thành công

- Phát `OrderCreated`.
- Inventory xử lý và phát `InventoryReserved`.
- Payment xử lý và phát `PaymentAuthorized`.
- Order cập nhật `CONFIRMED`.
- Read model hội tụ về trạng thái đã xác nhận.

Test xác minh từng sự kiện hoặc trace theo correlation ID, nhưng không giả định thời điểm chính xác giữa các consumer. Trạng thái cuối và các bất biến mới là oracle chính.

### 15.3. Kịch bản lỗi và bù trừ

- Payment từ chối sau khi inventory đã giữ hàng.
- Order chuyển sang trạng thái phù hợp.
- Saga phát lệnh giải phóng hàng.
- Inventory xử lý lệnh bù, kể cả khi lệnh bị giao lại.
- Projection cuối cùng phản ánh đơn thất bại và hàng đã được giải phóng.

Test cần xác minh không có trạng thái sai kéo dài vượt deadline và các hành động bù không bị lặp gây sai lệch. Nếu một bước bù thất bại, hệ thống phải tạo trạng thái cần điều tra hoặc xử lý thủ công, không âm thầm coi saga hoàn tất.

## 16. Đo độ trễ hội tụ và thiết lập SLO

Eventual consistency cần được đo bằng thời gian từ sự kiện nguồn đến khi trạng thái đích phản ánh đúng sự kiện.

### 16.1. Xác định mốc đo

Ví dụ:

- Bắt đầu: timestamp event được commit vào outbox hoặc broker theo hợp đồng.
- Kết thúc: projection cập nhật version tương ứng và truy vấn đọc được trạng thái mới.

Không trộn timestamp từ các máy có clock lệch mà không hiệu chỉnh. Nếu có thể, dùng timestamp cùng nguồn hoặc đo elapsed time từ test harness.

### 16.2. Dùng percentile thay vì chỉ trung bình

Đo median, P90, P95 hoặc P99 tùy nhu cầu. Trung bình có thể che một nhóm event bị chậm nhiều phút. Phân đoạn theo event type, partition, consumer, tenant và tải để tìm nơi phát sinh lag.

### 16.3. Phân biệt test deadline và SLO vận hành

Test deadline là giới hạn để test kết luận trong môi trường và kịch bản cụ thể. SLO là mục tiêu dịch vụ trong điều kiện vận hành được định nghĩa. Hai giá trị có liên quan nhưng không nhất thiết giống nhau. Không dùng một test đơn lẻ để tuyên bố SLO dài hạn đạt.

### 16.4. Theo dõi chỉ số bổ trợ

- Consumer lag hoặc backlog depth.
- Thời gian xử lý mỗi message.
- Tỷ lệ retry và số attempt.
- Số message trong DLQ.
- Tỷ lệ lỗi handler.
- Độ trễ outbox đến broker.
- Độ trễ broker đến projection.
- Số bản ghi projection chờ cập nhật.

Các chỉ số giúp phân biệt độ trễ do producer, broker, consumer hay read model.

## 17. Các lỗi thiết kế test thường gặp

### 17.1. Dùng sleep cố định rồi đọc một lần

Một khoảng sleep ngắn có thể không đủ ở CI; khoảng dài làm suite chậm và vẫn không bảo đảm hội tụ. Dùng polling theo predicate với deadline và chẩn đoán timeout.

### 17.2. Chỉ kiểm tra phản hồi của producer

HTTP 202 hoặc phản hồi chấp nhận chỉ có thể chứng minh yêu cầu được tiếp nhận theo hợp đồng. Nó không chứng minh consumer đã xử lý hoặc projection đã hội tụ.

### 17.3. Chờ một trạng thái nhưng không kiểm tra bất biến

Projection có thể đạt trạng thái `CONFIRMED` nhưng tạo hai giao dịch. Kiểm tra cả trạng thái cuối lẫn số lượng, tổng tiền và tác dụng phụ.

### 17.4. Giả định thứ tự toàn cục

Test có thể flaky nếu yêu cầu event đến theo thứ tự mà broker không cam kết. Xác định ordering key và kiểm tra version/sequence trong phạm vi hợp đồng.

### 17.5. Không kiểm tra giao lại

Test chỉ gửi mỗi event một lần sẽ bỏ sót lỗi idempotency. Tạo kịch bản duplicate và crash tại ranh giới ack/commit.

### 17.6. Coi exactly-once là bảo đảm xuyên hệ thống

Semantics broker không tự bảo đảm email, thanh toán, database và API đối tác chỉ tạo hiệu ứng một lần. Kiểm tra idempotency ở từng ranh giới có tác dụng phụ.

### 17.7. Polling bỏ qua mọi lỗi

Nếu helper nuốt mọi exception, lỗi xác thực hoặc schema có thể bị che thành timeout. Chỉ retry lỗi tạm thời đã được phân loại.

### 17.8. Dùng dữ liệu và consumer group chung

Test có thể đọc nhầm message cũ hoặc làm thay đổi offset của test khác. Cô lập ID, group, topic/namespace và dữ liệu theo lần chạy.

### 17.9. Không giữ bằng chứng khi timeout

Chỉ ghi “eventual consistency timeout” không đủ để điều tra. Lưu trạng thái hiện tại, event ID, offset, consumer lag, số lần polling và trace.

### 17.10. Dùng một test E2E cho mọi lỗi

E2E khó tạo chính xác duplicate, out-of-order hoặc crash ở ranh giới ack. Dùng unit/component/integration test để kiểm soát từng tình huống, giữ E2E cho luồng đại diện.

## 18. Quy trình xây dựng và thực thi kiểm thử eventual consistency

1. **Mô tả luồng sự kiện:** producer, broker, consumer, database, projection và dependency.
2. **Xác định hợp đồng nhất quán:** ranh giới nào strong, eventual, read-your-writes hoặc causal.
3. **Định nghĩa bất biến:** điều không được xảy ra trong mọi trạng thái.
4. **Định nghĩa trạng thái cuối:** predicate hội tụ và version/sequence cần đạt.
5. **Đặt giới hạn thời gian:** dựa trên SLO, tải và môi trường.
6. **Thiết kế test theo tầng:** unit, component, contract, integration, E2E và resilience.
7. **Cô lập dữ liệu:** ID, correlation, consumer group và namespace riêng.
8. **Tạo kịch bản bình thường và lỗi:** duplicate, out-of-order, retry, crash, backlog và dependency unavailable.
9. **Thực thi với polling có deadline:** không dùng sleep tùy tiện hoặc retry mọi exception.
10. **Thu thập bằng chứng:** event, offset, trạng thái dữ liệu, trace, lag và số attempt.
11. **Phân loại kết quả:** PASS, FAIL, BLOCKED hoặc INCONCLUSIVE theo bằng chứng.
12. **Đánh giá xu hướng:** đo propagation lag, tỷ lệ retry, DLQ và khả năng phục hồi.
13. **Cập nhật hợp đồng và test:** khi event schema, consumer hoặc SLO thay đổi.

## 19. Danh sách rà soát kiểm chứng hệ thống hướng sự kiện

Trước khi hoàn tất một bộ test eventual consistency, hãy kiểm tra:

- [ ] Producer, broker, consumer và read model được xác định rõ.
- [ ] Ranh giới nhất quán và bảo đảm giao tiếp được mô tả.
- [ ] Bất biến safety và điều kiện liveness được định nghĩa.
- [ ] Trạng thái cuối và predicate hội tụ có thể quan sát.
- [ ] Deadline dựa trên yêu cầu và có thông báo timeout hữu ích.
- [ ] Test dùng polling có giới hạn thay vì sleep cố định.
- [ ] Lỗi không retry được không bị helper che giấu.
- [ ] Event ID, correlation ID, sequence/version được kiểm tra.
- [ ] Duplicate delivery và idempotency được xác minh.
- [ ] Ordering, event đến muộn và version cũ được kiểm tra theo hợp đồng.
- [ ] Outbox/inbox, ack/offset và điểm lỗi giữa các bước được kiểm tra.
- [ ] Retry, backoff, DLQ, replay và phục hồi consumer có test.
- [ ] Projection hội tụ đúng và không bị event cũ ghi đè.
- [ ] Saga và hành động bù được xác minh ở cả đường thành công và lỗi.
- [ ] Dữ liệu, consumer group và namespace được cô lập.
- [ ] Test lưu được event, trạng thái, offset, lag và trace khi thất bại.
- [ ] Độ trễ hội tụ được đo theo percentile và tải phù hợp.
- [ ] Kết quả phân biệt lỗi sản phẩm, broker, consumer, môi trường và test.

## 20. Kết luận

Kiểm chứng hệ thống hướng sự kiện với kết quả nhất quán sau một khoảng thời gian đòi hỏi nhóm xác định rõ những khác biệt tạm thời nào được phép và trạng thái nào cuối cùng phải đạt. Test cần kiểm tra bất biến safety trong suốt quá trình, điều kiện liveness và predicate hội tụ trong thời hạn có căn cứ. Polling theo điều kiện có deadline tạo test ổn định và cung cấp chẩn đoán tốt hơn việc chờ một khoảng cố định rồi đọc một lần.

Một chiến lược đầy đủ cần bao phủ đường đi sự kiện, giao nhận lại, idempotency, ordering, outbox/inbox, projection, retry, DLQ, saga và phục hồi consumer. Mỗi tầng kiểm thử chứng minh một phần hợp đồng; broker thật và môi trường tích hợp cần được dùng ở nơi semantics hạ tầng quan trọng. Khi dữ liệu được cô lập, trạng thái được quan sát và độ trễ hội tụ được đo, nhóm có thể xác minh không chỉ rằng hệ thống cuối cùng đạt kết quả đúng mà còn rằng nó duy trì các bất biến và phục hồi có kiểm soát khi xảy ra lỗi.
