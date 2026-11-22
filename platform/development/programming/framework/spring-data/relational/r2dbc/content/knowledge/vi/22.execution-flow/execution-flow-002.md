# Dùng then, thenMany và delayUntil để diễn đạt quan hệ phụ thuộc

Trong ứng dụng reactive dùng Spring Data R2DBC, nhiều thao tác phải chạy theo một thứ tự phụ thuộc: lưu dữ liệu trước rồi mới đọc tiếp, xóa dữ liệu cũ trước khi phát danh sách mới, hoặc chỉ trả entity sau khi một thao tác bất đồng bộ liên quan đã hoàn tất.

Reactor cung cấp các toán tử then, thenMany và delayUntil để diễn đạt những quan hệ này mà không cần gọi block() hoặc tự tạo subscription. Cả ba đều quan tâm đến thời điểm một publisher hoàn tất, nhưng chúng khác nhau ở việc giữ hay loại bỏ giá trị đầu vào và kiểu dữ liệu phát ra.

- **then** đợi publisher hiện tại hoàn tất thành công, bỏ các giá trị của nó và chuyển sang một Mono tiếp theo hoặc chỉ phát tín hiệu hoàn tất.
- **thenMany** cũng đợi publisher hiện tại hoàn tất thành công, bỏ các giá trị của nó rồi chuyển sang một publisher có thể phát nhiều phần tử.
- **delayUntil** giữ lại từng giá trị của publisher nguồn, nhưng chỉ phát giá trị đó sau khi publisher phụ thuộc được tạo từ giá trị ấy hoàn tất.

Chọn đúng toán tử giúp code thể hiện rõ: cần đợi một công việc hoàn tất, cần chuyển sang một luồng kết quả mới, hay cần giữ nguyên giá trị hiện tại trong khi chờ một công việc phụ thuộc.

## 1. Publisher reactive và quan hệ phụ thuộc

Trong Reactor, Mono<T> biểu diễn một kết quả có thể có hoặc không có; Flux<T> biểu diễn một chuỗi gồm không, một hoặc nhiều phần tử. Các publisher thường lazy: gọi repository hoặc client reactive tạo ra pipeline, còn thao tác I/O chỉ bắt đầu khi có subscription.

Ví dụ:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Ở thời điểm gán biến saved, chưa có bảo đảm câu SQL đã chạy. Khi publisher được subscribe, Spring Data R2DBC mới thực hiện thao tác lưu.

Nếu bước tiếp theo phụ thuộc vào việc lưu hoàn tất, hãy nối hai publisher trong cùng pipeline. Không gọi subscribe() bên trong service để tự khởi chạy bước thứ hai, vì như vậy caller không còn kiểm soát được kết quả, lỗi và cancellation của toàn bộ công việc.

### 1.1. Ba kiểu quan hệ thường gặp

Giả sử ứng dụng vừa lưu một đơn hàng:

1. Lưu order, sau đó ghi audit log. Kết quả entity order không cần được giữ từ publisher audit. Đây là quan hệ chờ hoàn tất và chuyển sang bước tiếp theo: then.
2. Xóa các session hết hạn, sau đó phát danh sách session còn hoạt động. Giá trị từ thao tác xóa không cần xuất hiện trong kết quả cuối, nhưng bước sau trả nhiều session: thenMany.
3. Lưu order, gọi dịch vụ inventory bằng ID của order vừa lưu, rồi chỉ trả order sau khi inventory xác nhận. Cần giữ chính entity order trong khi chờ thao tác phụ thuộc: delayUntil.

## 2. Dùng then khi chỉ quan tâm publisher đã hoàn tất

then() bỏ qua mọi giá trị được phát ra từ publisher nguồn và trả về Mono<Void> chỉ hoàn tất khi publisher nguồn hoàn tất thành công.

~~~java
Mono<Void> result = customerRepository.save(customer).then();
~~~

Nếu muốn chạy một Mono khác sau khi publisher nguồn hoàn tất, dùng then(Mono<V>):

~~~java
Mono<Order> result = auditRepository.save(auditRecord)
        .then(orderRepository.findById(orderId));
~~~

Trình tự là:

1. Subscribe vào publisher lưu audit.
2. Đợi thao tác lưu audit hoàn tất.
3. Nếu thành công, subscribe vào publisher tìm order.
4. Phát order tìm được hoặc hoàn tất rỗng nếu không có order.

Giá trị AuditRecord do save() phát ra bị bỏ qua. Giá trị của publisher thứ hai trở thành giá trị của Mono<Order> cuối cùng.

### 2.1. then() không cần publisher thứ hai

Khi chỉ cần biểu diễn rằng một thao tác phải hoàn tất trước khi service hoàn tất, dùng then():

~~~java
public Mono<Void> recordCustomerCreation(Customer customer) {
    AuditRecord audit = AuditRecord.customerCreated(customer.getId());

    return auditRepository.save(audit).then();
}
~~~

save() có thể phát ra entity đã lưu, nhưng service chỉ trả tín hiệu hoàn tất. Caller không nhận entity audit.

### 2.2. Dùng thenReturn khi muốn trả một giá trị cố định

Nếu publisher nguồn phải hoàn tất trước khi trả một giá trị có sẵn, có thể dùng thenReturn(value):

~~~java
return auditRepository.save(auditRecord)
        .thenReturn("AUDIT_RECORDED");
~~~

Đây là cách viết ngắn tương đương về ý nghĩa với việc chuyển sang một Mono phát giá trị cố định sau khi publisher nguồn hoàn tất. Giá trị audit được phát ra từ save() không được giữ lại.

### 2.3. Dùng then(Mono.defer(...)) khi cần tạo publisher sau đó

Nếu việc tạo publisher tiếp theo cần thực hiện sau khi publisher đầu hoàn tất, có thể dùng Mono.defer:

~~~java
return auditRepository.save(auditRecord)
        .then(Mono.defer(() -> notificationClient.publish(event)));
~~~

then chỉ subscribe publisher thứ hai sau khi publisher đầu hoàn tất thành công. defer còn trì hoãn việc gọi hàm tạo publisher cho đến lúc bước thứ hai thực sự được subscribe. Điều này hữu ích khi bước sau cần đọc trạng thái tại thời điểm thực thi hoặc tạo request mới.

Nếu biểu thức tạo publisher không có side effect và có thể tạo trước, không nhất thiết phải bọc bằng defer.

## 3. Dùng thenMany khi bước tiếp theo trả nhiều phần tử

thenMany(Publisher<V>) đợi publisher nguồn hoàn tất thành công, bỏ tất cả giá trị nguồn, sau đó subscribe publisher tiếp theo và phát các giá trị của publisher đó dưới dạng Flux<V>.

Ví dụ xóa session hết hạn rồi đọc danh sách còn hoạt động:

~~~java
public Flux<Session> findActiveSessions(LocalDateTime now) {
    return sessionRepository.deleteExpired(now)
            .thenMany(sessionRepository.findAllByStatus("ACTIVE"));
}
~~~

Giả sử deleteExpired trả Mono<Integer> chứa số hàng bị xóa. Số đó bị bỏ qua. Sau khi xóa hoàn tất, findAllByStatus mới được subscribe và các session được phát ra.

### 3.1. Kết quả từ publisher đầu không được nối vào Flux cuối

thenMany khác concatWith:

~~~java
Flux<String> combined = firstFlux.concatWith(secondFlux);
~~~

concatWith phát tất cả phần tử từ firstFlux, sau đó phát các phần tử từ secondFlux.

Trong khi đó:

~~~java
Flux<String> replaced = firstFlux.thenMany(secondFlux);
~~~

thenMany bỏ các phần tử của firstFlux; Flux kết quả chỉ phát phần tử từ secondFlux sau khi firstFlux hoàn tất.

### 3.2. Dùng thenMany cho luồng nhiều bước

Ví dụ lưu một batch metadata rồi phát các bản ghi cần xử lý:

~~~java
public Flux<Order> prepareAndFindOrders(BatchRun run) {
    return batchRunRepository.save(run)
            .thenMany(orderRepository.findAllByStatus("READY"));
}
~~~

Entity BatchRun được phát ra từ save() không nằm trong Flux kết quả. Flux cuối chứa các order từ repository thứ hai.

Nếu cần dùng giá trị BatchRun để xây dựng query tiếp theo, thenMany không phù hợp vì nó loại bỏ giá trị nguồn. Khi đó dùng flatMapMany hoặc một toán tử giữ giá trị.

~~~java
return batchRunRepository.save(run)
        .flatMapMany(saved -> orderRepository.findAllByBatchId(saved.getId()));
~~~

flatMapMany nhận entity đã lưu để tạo Flux phụ thuộc. Đây là lựa chọn đúng khi bước sau cần giá trị của bước trước.

## 4. Dùng delayUntil khi cần giữ giá trị nhưng chờ publisher phụ thuộc

delayUntil được dùng khi publisher nguồn phát ra một giá trị, ứng dụng tạo một publisher phụ thuộc từ giá trị đó, và chỉ phát lại giá trị nguồn sau khi publisher phụ thuộc hoàn tất.

Ví dụ lưu order, sau đó đặt chỗ tồn kho bằng ID vừa sinh:

~~~java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

Luồng xử lý:

1. save() lưu order và phát entity đã lưu.
2. delayUntil nhận entity đó trong hàm tạo trigger.
3. inventoryClient.reserve(saved.getId()) được subscribe.
4. Khi publisher reserve hoàn tất thành công, delayUntil phát lại chính entity saved.

Kết quả vẫn là Mono<Order>. Giá trị order được giữ lại; giá trị do publisher inventory phát ra (nếu có) không thay thế entity order.

### 4.1. delayUntil không phải bộ hẹn giờ

Tên toán tử có chữ “delay”, nhưng ý nghĩa chính là trì hoãn việc phát giá trị cho đến khi một publisher phụ thuộc hoàn tất. Nó không mặc định đợi một khoảng thời gian cố định.

Nếu chỉ muốn trì hoãn theo thời gian, dùng toán tử như delayElement(Duration):

~~~java
return orderRepository.findById(id)
        .delayElement(Duration.ofSeconds(2));
~~~

Nếu muốn đợi một công việc bất đồng bộ, dùng delayUntil:

~~~java
return orderRepository.findById(id)
        .delayUntil(order -> auditClient.recordViewed(order.getId()));
~~~

### 4.2. Trigger thường là Mono<Void>

Publisher phụ thuộc thường chỉ cần báo hoàn tất, không cần phát dữ liệu. Vì vậy, kiểu Mono<Void> thường phù hợp:

~~~java
return customerRepository.findById(customerId)
        .delayUntil(customer -> auditRepository
                .save(AuditRecord.customerViewed(customer.getId()))
                .then());
~~~

Khi audit lưu xong, delayUntil phát lại Customer. Entity không bị thay bằng AuditRecord.

### 4.3. delayUntil trên Flux

Flux.delayUntil áp dụng quan hệ chờ cho từng phần tử nguồn:

~~~java
public Flux<Customer> verifyPendingCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .delayUntil(customer -> verificationClient.verify(customer.getId()));
}
~~~

Mỗi customer chỉ được phát ra sau khi publisher xác minh tương ứng hoàn tất. Các phần tử giữ thứ tự của nguồn; publisher trigger của một phần tử phải hoàn tất trước khi phần tử đó được phát ra.

Với lượng dữ liệu lớn, hãy cân nhắc giới hạn nguồn, phân trang và năng lực của dịch vụ phụ thuộc. delayUntil diễn đạt việc chờ theo từng phần tử; nó không phải lựa chọn thay thế tự động cho mọi chiến lược xử lý song song.

## 5. So sánh then, thenMany và delayUntil

| Toán tử | Chờ điều gì? | Giữ giá trị nguồn? | Kiểu kết quả thường gặp | Dùng khi |
| --- | --- | --- | --- | --- |
| then() | Nguồn hoàn tất thành công | Không | Mono<Void> | Chỉ cần chờ thao tác hoàn tất |
| then(Mono<V>) | Nguồn hoàn tất rồi mới chạy Mono tiếp theo | Không | Mono<V> | Chuyển sang một kết quả Mono khác |
| thenReturn(value) | Nguồn hoàn tất rồi phát giá trị cố định | Không | Mono<V> | Chờ xong rồi trả hằng số/object có sẵn |
| thenMany(Publisher<V>) | Nguồn hoàn tất rồi mới chạy publisher tiếp theo | Không | Flux<V> | Chuyển sang luồng nhiều phần tử |
| delayUntil(fn) | Trigger tạo từ từng giá trị hoàn tất | Có | Mono<T> hoặc Flux<T> | Giữ giá trị nguồn nhưng phải chờ công việc phụ thuộc |

### 5.1. Sơ đồ đơn giản

~~~text
then:
  Publisher<A> --complete--> Publisher<B> --emit B
        (bỏ A)

thenMany:
  Publisher<A> --complete--> Publisher<B...> --emit B...
        (bỏ A)

delayUntil:
  Publisher<A> --emit A--> Trigger(A) --complete--> emit A
        (giữ A)
~~~

## 6. Phân biệt với flatMap, flatMapMany và concatMap

Các toán tử này cũng nối publisher nhưng mục đích khác nhau.

### 6.1. flatMap: dùng giá trị nguồn để tạo kết quả mới

~~~java
return orderRepository.save(order)
        .flatMap(saved -> paymentClient.authorize(saved.getId()));
~~~

Kết quả là kết quả từ paymentClient.authorize, không phải entity order. flatMap phù hợp khi giá trị phát ra từ bước trước cần được dùng để tạo publisher tiếp theo và kết quả cuối là giá trị từ publisher đó.

### 6.2. flatMap kết hợp thenReturn: chờ phụ thuộc nhưng giữ giá trị

Có thể viết:

~~~java
return orderRepository.save(order)
        .flatMap(saved -> inventoryClient.reserve(saved.getId())
                .thenReturn(saved));
~~~

Đây là cách diễn đạt hợp lệ: gọi reserve, bỏ kết quả reserve rồi trả lại order. delayUntil thể hiện ý định này trực tiếp và ngắn hơn:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
~~~

### 6.3. flatMapMany: dùng giá trị nguồn để tạo Flux tiếp theo

~~~java
return customerRepository.findById(customerId)
        .flatMapMany(customer -> orderRepository.findAllByCustomerId(customer.getId()));
~~~

Kết quả là các order, không phải customer. Nếu chỉ muốn đợi một publisher Mono hoàn tất rồi phát một Flux độc lập, dùng thenMany.

### 6.4. concatMap: xử lý từng phần tử và giữ thứ tự

Với Flux, concatMap biến mỗi phần tử thành một publisher phụ thuộc, subscribe tuần tự và phát kết quả của publisher con:

~~~java
return customerRepository.findAllByStatus("PENDING")
        .concatMap(customer -> verificationClient.verifyAndReturn(customer));
~~~

concatMap phù hợp khi cần kết quả từ publisher con và muốn xử lý tuần tự. delayUntil phù hợp khi cần giữ nguyên customer nguồn sau khi một trigger hoàn tất.

## 7. Xử lý trường hợp publisher rỗng

Mono có thể hoàn tất mà không phát giá trị. Điều này ảnh hưởng cách các toán tử hoạt động.

### 7.1. then vẫn chạy bước tiếp theo khi nguồn rỗng

~~~java
Mono<Void> first = Mono.empty();

Mono<String> result = first.then(Mono.just("NEXT"));
~~~

Publisher đầu hoàn tất thành công dù không phát giá trị. Vì then chỉ quan tâm tín hiệu hoàn tất, publisher thứ hai vẫn được subscribe và phát NEXT.

Điều này cũng có nghĩa nếu findById() trả Mono.empty(), đoạn sau:

~~~java
return customerRepository.findById(id)
        .then(auditRepository.recordLookup(id));
~~~

vẫn ghi audit dù không tìm thấy customer. Nếu audit chỉ được ghi khi customer tồn tại, hãy dùng flatMap:

~~~java
return customerRepository.findById(id)
        .flatMap(customer -> auditRepository.recordLookup(id)
                .thenReturn(customer));
~~~

### 7.2. thenMany cũng chạy publisher sau khi nguồn rỗng

~~~java
return Mono.<Integer>empty()
        .thenMany(Flux.just("A", "B"));
~~~

Flux cuối vẫn phát A và B, vì nguồn đã hoàn tất thành công. Nếu cần chỉ chạy bước sau khi nguồn có giá trị, dùng flatMapMany trên Mono:

~~~java
return customerRepository.findById(id)
        .flatMapMany(customer -> orderRepository.findAllByCustomerId(customer.getId()));
~~~

Nếu customer không tồn tại, Flux kết quả hoàn tất rỗng và query order không được gọi.

### 7.3. delayUntil không gọi trigger khi nguồn không phát giá trị

~~~java
return customerRepository.findById(id)
        .delayUntil(customer -> auditRepository.recordLookup(id));
~~~

Nếu findById hoàn tất rỗng, không có customer để truyền vào hàm trigger. Audit không được gọi và kết quả cũng hoàn tất rỗng.

Đây là khác biệt quan trọng: then/thenMany chờ completion của nguồn, còn delayUntil cần một giá trị nguồn để tạo publisher phụ thuộc.

## 8. Xử lý lỗi trong chuỗi phụ thuộc

Các toán tử sequencing chỉ chuyển sang bước sau khi publisher trước hoàn tất thành công.

### 8.1. Lỗi ở publisher nguồn

~~~java
return auditRepository.save(auditRecord)
        .then(notificationClient.publish(event));
~~~

Nếu lưu audit phát lỗi, publisher notification không được subscribe. Lỗi audit được truyền xuống caller.

### 8.2. Lỗi ở publisher tiếp theo

~~~java
return auditRepository.save(auditRecord)
        .then(notificationClient.publish(event));
~~~

Nếu audit thành công nhưng publish phát lỗi, pipeline cuối phát lỗi từ bước publish. Việc audit đã lưu thành công không tự động bị hoàn tác, trừ khi cả hai thao tác tham gia cùng một transaction có thể rollback và thực sự dùng cùng resource transaction.

### 8.3. Lỗi trong trigger của delayUntil

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
~~~

Nếu reserve phát lỗi, entity order không được phát ra từ pipeline cuối; lỗi trigger được truyền xuống caller. Thao tác lưu order có thể đã hoàn tất trước khi reserve thất bại.

Nếu cần bù trừ khi reserve thất bại, hãy biểu diễn compensation rõ ràng:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .onErrorResume(error -> orderRepository.markReservationFailed(saved.getId())
                        .then(Mono.error(error))));
~~~

Ví dụ này chỉ minh họa cách nối publisher bù trừ. Trong hệ thống thực tế, cần thiết kế trạng thái order, retry, idempotency và xử lý trường hợp compensation cũng thất bại.

### 8.4. Dùng onErrorResume có chủ đích

Không nên nuốt lỗi chỉ để pipeline tiếp tục:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .onErrorResume(error -> Mono.empty()));
~~~

Code này biến lỗi reserve thành completion thành công. delayUntil sau đó phát order như thể trigger đã hoàn tất bình thường. Chỉ làm vậy nếu nghiệp vụ chấp nhận reservation thất bại mà vẫn trả order và có cơ chế xử lý trạng thái rõ ràng.

## 9. Cancellation và publisher không hoàn tất

Publisher phụ thuộc phải hoàn tất để toán tử có thể chuyển tiếp hoặc phát giá trị.

- Nếu publisher nguồn không bao giờ hoàn tất, then và thenMany không chạy bước sau.
- Nếu trigger của delayUntil không hoàn tất, giá trị nguồn tương ứng chưa được phát ra.
- Nếu publisher phát lỗi, lỗi truyền xuống downstream và các bước sau bị bỏ qua.
- Nếu downstream cancel, Reactor truyền cancellation về các publisher đang hoạt động theo quy tắc của operator và publisher đó.

Đặt timeout phù hợp cho các thao tác mạng hoặc database có thể treo lâu:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .timeout(Duration.ofSeconds(3)));
~~~

Timeout không bảo đảm side effect ở hệ thống ngoài bị đảo ngược. Nó chỉ kết thúc publisher ở phía ứng dụng; hệ thống ngoài có thể đã nhận và xử lý request. Với thao tác không idempotent, cần idempotency key hoặc cơ chế tra cứu trạng thái để tránh thực hiện lặp.

## 10. Reactive transaction và các toán tử sequencing

then, thenMany và delayUntil giữ các publisher trong cùng một pipeline. Nếu pipeline chạy trong reactive transaction, các thao tác R2DBC tham gia transaction có thể dùng cùng transaction context khi chúng dùng đúng ConnectionFactory và transaction manager.

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved));
}
~~~

Ở đây thao tác lưu order và audit được nối tuần tự. Nếu cả hai repository dùng cùng R2DBC transaction manager và lỗi được truyền ra ngoài, lỗi ở audit có thể làm rollback cả transaction.

### 10.1. Không kéo dài transaction bằng lời gọi dịch vụ ngoài

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

Nếu transaction bao trùm toàn bộ publisher, connection database có thể bị giữ trong lúc ứng dụng chờ dịch vụ inventory. Khi dịch vụ ngoài chậm, pool R2DBC có thể bị chiếm connection lâu hơn cần thiết.

Nếu cần phối hợp database với dịch vụ ngoài, cân nhắc lưu trạng thái/outbox trong transaction ngắn, commit, rồi phát sự kiện qua worker. Không giả định transaction R2DBC có thể rollback side effect đã xảy ra ở HTTP service hoặc message broker.

### 10.2. Không gọi subscribe() bên trong service

Tránh:

~~~java
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order)
            .flatMap(saved -> inventoryClient.reserve(saved.getId()))
            .subscribe();

    return Mono.just(order);
}
~~~

Subscription độc lập làm tách rời công việc khỏi publisher trả về. Caller không chờ reservation, không nhận lỗi từ reservation và transaction context có thể không được giữ như mong muốn.

Hãy trả toàn bộ pipeline:

~~~java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

## 11. Ví dụ tổng hợp: lưu, ghi audit rồi phát danh sách

Một use case có thể gồm nhiều loại phụ thuộc:

1. Lưu order và nhận ID.
2. Ghi audit dựa trên ID vừa sinh.
3. Sau khi audit hoàn tất, phát các order gần đây.

~~~java
public Flux<OrderListItem> createAndRefresh(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved))
            .thenMany(orderReadRepository.findRecent());
}
~~~

flatMap được dùng ở bước audit vì cần ID của order đã lưu. thenReturn(saved) bỏ entity audit và trả lại order. thenMany đợi toàn bộ pipeline lưu/audit hoàn tất rồi mới subscribe query danh sách và phát Flux<OrderListItem>.

Nếu không cần phát danh sách mà chỉ cần trả order đã lưu, dùng:

~~~java
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId())));
}
~~~

delayUntil giữ order và chờ audit hoàn tất. Hai ví dụ có kết quả khác nhau nên chọn toán tử theo kiểu dữ liệu mà API cần trả về.

## 12. Ví dụ xử lý từng phần tử của Flux

Giả sử cần phát từng khách hàng sau khi gửi một yêu cầu kiểm tra bất đồng bộ:

~~~java
public Flux<Customer> verifyCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .delayUntil(customer -> verificationClient.verify(customer.getId()));
}
~~~

Nếu muốn chỉ phát kết quả từ dịch vụ xác minh, dùng flatMap:

~~~java
public Flux<VerificationResult> verifyCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .flatMap(customer -> verificationClient.verifyAndReturn(customer.getId()));
}
~~~

Nếu cần xử lý tuần tự và phát kết quả xác minh theo thứ tự nguồn:

~~~java
public Flux<VerificationResult> verifyCustomersInOrder() {
    return customerRepository.findAllByStatus("PENDING")
            .concatMap(customer -> verificationClient.verifyAndReturn(customer.getId()));
}
~~~

Ba pipeline khác nhau ở giá trị được phát ra và cách xử lý publisher con. Chọn theo hợp đồng của API, không chỉ theo độ ngắn của code.

## 13. Những lỗi thường gặp khi chọn toán tử

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không nhận được entity đã lưu | Dùng then() và đã bỏ giá trị nguồn | Dùng flatMap, delayUntil hoặc giữ giá trị bằng thenReturn |
| Query sau đó chạy dù entity không tồn tại | Dùng then sau Mono.empty() | Dùng flatMap hoặc flatMapMany nếu bước sau cần entity |
| Publisher thứ hai không chạy | Publisher đầu phát lỗi hoặc không hoàn tất | Kiểm tra lỗi, timeout và completion của nguồn |
| Flux cuối chỉ chứa dữ liệu bước sau | Dùng thenMany, vốn bỏ dữ liệu nguồn | Dùng concatWith nếu muốn nối cả hai luồng |
| Entity được phát trước khi side effect xong | Dùng doOnNext để gọi publisher hoặc không nối publisher phụ thuộc | Dùng delayUntil hoặc flatMap phù hợp |
| Kết quả cuối là dữ liệu từ dịch vụ phụ thuộc | Dùng flatMap nhưng muốn giữ entity nguồn | Dùng delayUntil hoặc flatMap(...thenReturn(source)) |
| Audit chạy dù không tìm thấy bản ghi | Dùng then sau một Mono có thể rỗng | Đặt audit trong flatMap khi chỉ chạy nếu có giá trị |
| Lỗi dịch vụ ngoài bị che giấu | Dùng onErrorResume trả Mono.empty() không có chủ đích | Chuyển lỗi thành trạng thái nghiệp vụ rõ hoặc truyền lỗi |
| Transaction giữ connection quá lâu | Chờ HTTP/message publisher trong transaction | Thu hẹp transaction, cân nhắc outbox/after-commit |
| Side effect chạy hai lần | Retry publisher không idempotent | Dùng idempotency key và thiết kế retry an toàn |

## 14. Bảng chọn toán tử theo ý định

| Ý định | Toán tử nên dùng |
| --- | --- |
| Chờ thao tác hoàn tất, không cần giá trị nào | then() |
| Chờ thao tác A rồi trả kết quả từ Mono B | then(monoB) |
| Chờ thao tác A rồi trả một giá trị cố định | thenReturn(value) |
| Chờ thao tác A rồi phát Flux B | thenMany(fluxB) |
| Chờ publisher được tạo từ giá trị A rồi phát lại A | delayUntil(value -> trigger(value)) |
| Dùng giá trị A để tạo Mono B và trả kết quả B | flatMap(value -> monoB) |
| Dùng giá trị A để tạo Flux B và trả các giá trị B | flatMapMany(value -> fluxB) |
| Nối toàn bộ phần tử của Flux A rồi đến Flux B | concatWith(fluxB) |
| Xử lý tuần tự từng phần tử và phát kết quả xử lý | concatMap(value -> publisher(value)) |

## 15. Kiểm thử thứ tự thực thi

Nên kiểm thử cả giá trị kết quả và thứ tự subscribe vào publisher phụ thuộc. Có thể dùng StepVerifier, PublisherProbe hoặc TestPublisher của Reactor Test tùy tình huống.

### 15.1. Kiểm thử then

~~~java
@Test
void thenSubscribesSecondPublisherAfterFirstCompletes() {
    PublisherProbe<String> second = PublisherProbe.of(Mono.just("done"));

    Mono<String> result = Mono.just("ignored")
            .then(second.mono());

    StepVerifier.create(result)
            .expectNext("done")
            .verifyComplete();

    second.assertWasSubscribed();
}
~~~

Test xác nhận publisher thứ hai được subscribe và giá trị nguồn ignored không xuất hiện.

### 15.2. Kiểm thử thenMany

~~~java
@Test
void thenManyEmitsOnlySecondPublisherValues() {
    Flux<String> result = Flux.just("old-1", "old-2")
            .thenMany(Flux.just("new-1", "new-2"));

    StepVerifier.create(result)
            .expectNext("new-1", "new-2")
            .verifyComplete();
}
~~~

Test xác nhận các phần tử nguồn bị bỏ qua và Flux sau được phát đầy đủ.

### 15.3. Kiểm thử delayUntil

~~~java
@Test
void delayUntilPreservesSourceValueUntilTriggerCompletes() {
    PublisherProbe<Void> trigger = PublisherProbe.of(Mono.empty());

    Mono<String> result = Mono.just("order-10")
            .delayUntil(ignored -> trigger.mono());

    StepVerifier.create(result)
            .expectNext("order-10")
            .verifyComplete();

    trigger.assertWasSubscribed();
}
~~~

Test xác nhận trigger được subscribe và giá trị nguồn được giữ lại.

### 15.4. Các trường hợp cần kiểm tra thêm

- Publisher nguồn hoàn tất rỗng.
- Publisher nguồn phát lỗi.
- Publisher thứ hai hoặc trigger phát lỗi.
- Trigger không hoàn tất cho tới khi test chủ động cho phép.
- Downstream cancel khi publisher phụ thuộc đang chạy.
- Flux có nhiều phần tử và trigger hoàn tất theo thời điểm khác nhau.
- Side effect không bị subscribe hai lần ngoài ý muốn.
- Transaction reactive vẫn được giữ khi các publisher R2DBC được nối trong cùng pipeline.

## 16. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Có publisher phụ thuộc cần nối?] --> B{Có cần giữ giá trị nguồn?}
    B -->|Không| C{Publisher tiếp theo trả nhiều phần tử?}
    C -->|Không| D[then hoặc then Mono]
    C -->|Có| E[thenMany]
    B -->|Có| F{Publisher phụ thuộc được tạo từ giá trị nguồn?}
    F -->|Có và chỉ cần chờ hoàn tất| G[delayUntil]
    F -->|Có và cần trả kết quả publisher phụ thuộc| H[flatMap hoặc flatMapMany]
    F -->|Không| I[Xem xét zip/concat/merge theo quan hệ thực tế]
    D --> J[Kiểm thử empty, error và cancel]
    E --> J
    G --> J
    H --> J
    I --> J
~~~

## 17. Kết luận

then, thenMany và delayUntil đều giúp biểu diễn quan hệ phụ thuộc trong pipeline reactive nhưng có hợp đồng khác nhau. then và thenMany bỏ giá trị nguồn, đợi nguồn hoàn tất rồi chuyển sang publisher tiếp theo; delayUntil giữ giá trị nguồn và chỉ phát nó sau khi publisher phụ thuộc hoàn tất.

Hãy dùng then khi chỉ quan tâm bước trước đã xong, thenMany khi bước sau phát một luồng nhiều phần tử, và delayUntil khi cần giữ entity hoặc giá trị hiện tại trong lúc chờ một thao tác bất đồng bộ. Nếu bước sau cần kết quả từ giá trị nguồn, dùng flatMap hoặc flatMapMany. Luôn giữ các thao tác trong cùng publisher chain, xử lý rõ empty/error/cancel và tránh kéo dài reactive transaction bằng lời gọi dịch vụ ngoài không cần thiết.
