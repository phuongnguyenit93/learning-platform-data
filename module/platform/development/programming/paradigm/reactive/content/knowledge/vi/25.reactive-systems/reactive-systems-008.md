# Bảo đảm giao nhận thông điệp, trùng lặp và thứ tự xử lý

Trong một hệ thống phản ứng, sự kiện đi qua nhiều thành phần độc lập: producer tạo thông điệp, broker lưu và phân phối, consumer nhận rồi cập nhật trạng thái hoặc gọi dịch vụ khác. Mỗi ranh giới có thể gặp lỗi riêng. Producer có thể mất kết nối sau khi broker đã nhận dữ liệu nhưng trước khi nhận xác nhận; consumer có thể xử lý xong nhưng dừng trước khi commit offset; một thông điệp có thể được gửi lại; nhiều consumer có thể hoàn tất các thông điệp liên quan theo thứ tự khác nhau.

Bảo đảm giao nhận vì vậy không chỉ là chọn cấu hình broker. Ứng dụng phải xác định khi nào thông điệp được coi là đã nhận, khi nào side effect đã bền vững, cách nhận diện lần xử lý lặp và phạm vi thứ tự cần giữ. Trong pipeline reactive, backpressure điều tiết tốc độ tiêu thụ, còn acknowledgement và commit xác nhận tiến độ giao nhận. Hai cơ chế liên quan nhưng không thay thế nhau.

Bài học thuộc chương **Hệ thống phản ứng** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; nội dung này áp dụng Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java vào giao nhận thông điệp đáng tin cậy.

Các ví dụ sử dụng Project Reactor và minh họa consumer theo kiểu Reactor Kafka. Những tên như eventRepository, brokerSender hoặc OrderEvent đại diện cho thành phần ứng dụng; cần bổ sung import, kiểu miền, cấu hình broker và transaction manager tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt at-most-once, at-least-once và exactly-once theo ranh giới mà hệ thống thực sự bảo đảm.
- Giải thích vì sao acknowledgement hoặc offset commit phải gắn với thời điểm xử lý đã đạt mức bền vững cần thiết.
- Thiết kế consumer idempotent để xử lý thông điệp lặp an toàn.
- Dùng inbox và outbox để phối hợp giao nhận với thay đổi database.
- Giữ thứ tự theo khóa nghiệp vụ hoặc partition mà không tuần tự hóa toàn hệ thống.
- Thiết kế retry, dead-letter queue và xử lý thông điệp độc hại.
- Phân biệt backpressure trong Flux với acknowledgement và lưu trữ bền vững của broker.
- Kiểm thử duplicate, retry, thứ tự xử lý, commit và tình huống crash ở các ranh giới quan trọng.

## 1. Một thông điệp đi qua nhiều ranh giới có thể thất bại

~~~text
Producer
   |
   | publish message
   v
Broker / durable log
   |
   | deliver
   v
Consumer
   |
   | validate + process
   v
Database / external service
   |
   | acknowledge or commit offset
   v
Broker advances delivery position
~~~

Mỗi mũi tên có thể gặp lỗi hoặc timeout. Producer gửi thông điệp nhưng mất kết nối trước khi nhận publish confirmation sẽ không biết broker đã lưu thông điệp hay chưa. Nếu gửi lại, thông điệp có thể xuất hiện hai lần. Nếu không gửi lại, thông điệp có thể bị mất khi broker chưa nhận được.

Ở phía consumer cũng có một cửa sổ lỗi: consumer nhận thông điệp, cập nhật database thành công, rồi tiến trình dừng trước khi acknowledgement hoặc offset commit được broker xác nhận. Broker có thể giao lại thông điệp khi consumer khởi động hoặc subscription được thiết lập lại. Consumer khi đó có thể thực hiện lại side effect.

Đây là lý do giao nhận ít nhất một lần thường dẫn đến xử lý trùng. Chỉ cấu hình retry không loại bỏ được cửa sổ lỗi này. Consumer cần nhận diện một sự kiện đã được áp dụng trước đó.

Cũng cần xác định điều gì được coi là “đã xử lý”. Đưa thông điệp vào hàng đợi trong bộ nhớ chưa chắc đã đủ. Nếu tiến trình chết và hàng đợi biến mất, dữ liệu vẫn có thể mất. Với nghiệp vụ cần bảo đảm, chỉ nên xác nhận sau khi transaction database commit hoặc sau khi hệ thống đích xác nhận lưu bền vững.

## 2. Ba mô hình giao nhận thường gặp

At-most-once, at-least-once và exactly-once mô tả số lần một thông điệp hoặc hiệu ứng được quan sát trong một phạm vi xác định. Chúng không tự động nói lên rằng toàn bộ nghiệp vụ phân tán có cùng bảo đảm.

| Mô hình | Thời điểm xác nhận điển hình | Hệ quả khi lỗi | Đánh đổi |
|---|---|---|---|
| At-most-once | Xác nhận hoặc commit trước khi xử lý | Có thể mất thông điệp nếu tiến trình dừng sau commit nhưng trước side effect | Chấp nhận mất dữ liệu để tránh giao lại do lỗi xử lý |
| At-least-once | Xử lý thành công rồi mới xác nhận hoặc commit | Có thể nhận lại nếu side effect xong nhưng commit chưa được xác nhận | Tránh mất thông điệp trong cửa sổ xử lý, cần idempotency |
| Exactly-once trong phạm vi hỗ trợ | Kết quả và tiến độ commit nguyên tử trong cùng transaction | Loại bỏ kết quả lặp trong phạm vi transaction đó | Chỉ bao gồm các tài nguyên tham gia transaction |

### At-most-once

Consumer commit offset hoặc acknowledge trước khi xử lý. Nếu tiến trình dừng sau commit, broker coi thông điệp đã được tiêu thụ dù side effect chưa xảy ra. Cách này có thể phù hợp với telemetry mà dữ liệu mất được chấp nhận, nhưng không phù hợp với lệnh thanh toán hoặc thay đổi số dư.

### At-least-once

Consumer xử lý trước, sau đó mới acknowledge hoặc commit. Nếu xử lý thất bại, thông điệp chưa được xác nhận và có thể được giao lại. Nếu side effect đã commit nhưng acknowledgement bị mất, thông điệp cũng có thể được giao lại. Vì vậy consumer cần idempotency. Đây là mô hình thường dùng cho nghiệp vụ cần tránh mất thông điệp; cần kết hợp retry có giới hạn, deduplication và giám sát backlog.

### Exactly-once có phạm vi

Broker hỗ trợ transaction có thể bảo đảm việc đọc, xử lý và ghi thông điệp trong cùng broker transaction. Ví dụ, Kafka hỗ trợ transactional consume-transform-produce, trong đó output records và consumer offsets được commit trong cùng transaction Kafka. Consumer đọc theo isolation phù hợp để không quan sát dữ liệu của transaction chưa commit.

Bảo đảm này không tự bao gồm database bên ngoài, email, HTTP service hoặc thiết bị vật lý. Nếu consumer cập nhật database rồi commit offset Kafka, hai thao tác đó không trở thành transaction nguyên tử chỉ vì broker bật exactly-once. Với side effect ngoài broker, hãy dùng idempotency, inbox/outbox hoặc giao thức phối hợp phù hợp. Khi nói exactly-once, luôn nêu rõ đối tượng được bảo đảm: message trong broker, kết quả trong một transaction hay hiệu ứng nghiệp vụ quan sát được.

## 3. Acknowledgement và offset commit phải theo sau xử lý

Trong broker queue, acknowledgement thường báo consumer đã xử lý thông điệp. Trong Kafka, consumer commit offset báo tiến độ đã tiêu thụ của partition. Chi tiết API khác nhau, nhưng nguyên tắc thiết kế tương tự: xác nhận sau khi công việc cần bảo vệ đã đạt trạng thái bền vững.

Với Reactor Kafka, receiver phát ReceiverRecord; mỗi record có ReceiverOffset để acknowledge hoặc commit:

~~~java
Flux<ReceiverRecord<String, OrderEvent>> records =
    receiver.receive();

Flux<Void> processing =
    records.concatMap(record ->
        processOrder(record.value())
            .then(record.receiverOffset().commit())
    );
~~~

Đây là hình thức đơn giản: xử lý record hoàn tất rồi mới commit offset. concatMap giữ thứ tự xử lý trong subscription này và chỉ chuyển sang record tiếp theo sau khi Publisher của record hiện tại hoàn tất. Cách này dễ reasoning nhưng giới hạn throughput ở mức tuần tự cho luồng đang xử lý.

Trong Reactor Kafka, acknowledge() đánh dấu offset đã xử lý để cơ chế commit theo cấu hình có thể gom nhiều offset; commit() yêu cầu commit offset đã được acknowledge đến vị trí tương ứng. Hãy đọc tài liệu và cấu hình của phiên bản Reactor Kafka đang dùng để hiểu commit interval, batch size, retry và hành vi khi rebalance. Không coi lời gọi acknowledge như bằng chứng broker đã xác nhận commit tức thì. Với broker queue manual acknowledgement, chỉ ack sau khi side effect hoàn tất hoặc đã được ghi vào nơi bền vững có thể tiếp tục xử lý.

### Vì sao không commit trước side effect?

~~~java
receiver.receive()
    .concatMap(record ->
        record.receiverOffset().commit()
            .then(processOrder(record.value()))
    );
~~~

Nếu commit thành công rồi processOrder lỗi hoặc tiến trình dừng, broker sẽ không giao lại record đó theo offset đã commit. Side effect bị mất. Đây là lựa chọn at-most-once. Với at-least-once, thứ tự phải là process rồi commit. Tuy nhiên, nếu process đã commit database mà offset commit thất bại, broker có thể phát lại record. Consumer phải chịu được tình huống đó.

### Commit offset không xác nhận riêng từng record

Kafka lưu offset theo partition. Commit offset của một record thường biểu diễn vị trí tiếp theo cần đọc, nên commit offset cao hơn có thể khiến các offset thấp hơn cũng được coi là đã tiêu thụ. Nếu xử lý song song trong cùng partition và record có offset lớn hoàn tất trước record nhỏ, commit offset lớn quá sớm có thể làm mất record nhỏ khi tiến trình dừng.

~~~text
Partition P:
offset 10 ---- đang xử lý chậm
offset 11 ---- xử lý xong
offset 12 ---- xử lý xong

Commit đến 13 có thể khiến broker bỏ qua offset 10 khi khởi động lại.
~~~

Với xử lý theo partition, hãy giữ thứ tự hoàn tất hoặc chỉ commit đến offset liên tục cao nhất mà mọi record trước đó đã xử lý xong. Cách đơn giản là concatMap trong từng partition. Nếu cần song song, phải có bộ theo dõi offset hoàn tất liên tục và kiểm thử kỹ khi rebalance hoặc crash.

## 4. Idempotency: xử lý lặp mà không lặp side effect

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng khóa hoặc đầu vào mà kết quả nghiệp vụ cuối không bị nhân đôi. Ví dụ, đặt trạng thái đơn hàng thành SHIPPED thường có thể thiết kế idempotent; cộng thêm 100.000 đồng vào số dư không tự idempotent nếu gọi hai lần.

Thông điệp nên có eventId ổn định được tạo từ producer và giữ nguyên qua mọi lần retry. Consumer dùng eventId để nhận diện thông điệp đã xử lý.

~~~java
Mono<Void> handle(OrderEvent event) {
    return transactionalOperator.transactional(
        inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }
                return orderRepository.apply(event);
            })
    );
}
~~~

Giả sử insertIfAbsent trả Mono<Boolean> và database có unique constraint trên event_id. Nếu eventId đã tồn tại, thao tác insert trả false và business update được bỏ qua. Nếu chưa tồn tại, inbox record và thay đổi nghiệp vụ được thực hiện trong cùng transaction database.

Điều kiện quan trọng là inbox record và business update phải cùng tham gia một transaction. Nếu ghi inbox thành công rồi cập nhật nghiệp vụ ở transaction khác, tiến trình có thể dừng giữa hai bước: lần giao lại thấy eventId đã tồn tại và bỏ qua, dù thay đổi nghiệp vụ chưa xảy ra.

### Vì sao unique constraint quan trọng?

Hai bản sao cùng eventId có thể đến gần như đồng thời từ hai consumer hoặc hai đường retry. Một câu lệnh kiểm tra rồi mới insert ở tầng ứng dụng có race: consumer A và B cùng thấy event chưa tồn tại rồi cùng cập nhật nghiệp vụ. Ràng buộc unique ở database là điểm phân xử nguyên tử. Chỉ một insert được chấp nhận; consumer còn lại nhận biết bản ghi đã tồn tại và không áp dụng side effect lần nữa.

Nếu cần xử lý sự kiện nhiều bước, có thể lưu trạng thái inbox như RECEIVED, PROCESSING, COMPLETED và quản lý lease/timeout. State machine phức tạp chỉ cần thiết khi nghiệp vụ yêu cầu phục hồi giữa các bước; với một transaction ngắn, ghi inbox và business change cùng lúc thường đơn giản hơn.

### Idempotency key phải ổn định

Không tạo eventId mới mỗi lần retry. Nếu retry tạo khóa mới, consumer không thể nhận ra đó là cùng một sự kiện. Khóa cần được sinh tại nguồn nghiệp vụ hoặc lấy từ message identity ổn định của producer. Với lệnh từ client, idempotency key có thể gắn với request và lưu cùng kết quả; nếu client gửi lại request sau timeout, server trả kết quả của thao tác đã thực hiện thay vì thực hiện lần nữa.

## 5. Outbox: ghi thay đổi nghiệp vụ và sự kiện trong cùng transaction

Một lỗi phổ biến xảy ra khi ứng dụng cập nhật database rồi publish sự kiện:

~~~java
orderRepository.save(order)
    .flatMap(saved ->
        brokerSender.send(new OrderCreated(saved.id()))
            .thenReturn(saved)
    );
~~~

Nếu database commit nhưng publish thất bại, hệ thống có đơn hàng mà không có sự kiện. Nếu publish thành công nhưng database rollback, consumer có thể nhận sự kiện cho một đơn hàng không tồn tại.

Transactional outbox giải quyết sự không nguyên tử này bằng cách ghi sự kiện vào cùng database transaction với thay đổi nghiệp vụ:

~~~java
Mono<Order> createOrder(Order order) {
    return transactionalOperator.transactional(
        orderRepository.save(order)
            .flatMap(saved ->
                outboxRepository.insert(
                    OutboxEvent.orderCreated(saved)
                ).thenReturn(saved)
            )
    );
}
~~~

Sau commit, cả đơn hàng và outbox record đều tồn tại hoặc cùng rollback. Một publisher riêng đọc outbox và gửi sự kiện đến broker:

~~~java
Flux<Void> publishOutboxBatch() {
    return outboxRepository.findUnpublishedBatch(100)
        .concatMap(entry ->
            brokerSender.send(entry.event())
                .then(outboxRepository.markPublished(entry.id()))
        );
}
~~~

Ví dụ giả định Mono từ brokerSender hoàn tất sau khi broker xác nhận đã nhận sự kiện. Nếu API chỉ xác nhận đã đưa vào buffer nội bộ, cần chờ publisher confirmation phù hợp trước khi đánh dấu published.

Outbox loại bỏ khoảng trống giữa commit database và việc tạo bản ghi sự kiện, nhưng publisher vẫn có thể gặp lỗi sau khi broker nhận message và trước khi markPublished hoàn tất. Khi đó, lần chạy sau gửi lại cùng event. Vì vậy outbox thường tạo giao nhận at-least-once; consumer vẫn cần idempotency.

### Tránh hai publisher cùng gửi một outbox record

Nếu nhiều worker cùng đọc các bản ghi chưa publish, cần cơ chế claim để chúng không gửi cùng một record đồng thời. Có thể dùng trạng thái, lease, câu lệnh cập nhật có điều kiện hoặc SELECT ... FOR UPDATE SKIP LOCKED tùy database. Claim phải có thời hạn hoặc cơ chế phục hồi nếu worker chết khi đang giữ lease.

Không đánh dấu record published trước khi broker xác nhận. Làm vậy có thể mất sự kiện nếu publish thất bại. Nếu broker đã nhận nhưng database không đánh dấu được, chấp nhận khả năng gửi trùng và dựa vào eventId ổn định cùng consumer deduplication.

## 6. Inbox ở phía consumer

Outbox bảo đảm producer có bản ghi bền vững để gửi lại. Inbox giúp consumer xử lý bản gửi lại an toàn. Hai mẫu này bổ sung cho nhau:

~~~text
Producer database transaction
  +-- update business data
  `-- insert outbox(eventId)
             |
             v
       Outbox publisher
             |
             v
           Broker
             |
             v
       Consumer handler
  +-- insert inbox(eventId) with unique key
  +-- apply business update
  `-- commit one database transaction
~~~

Nếu consumer nhận eventId lần đầu, inbox insert và business update commit cùng nhau. Nếu nhận lại cùng eventId, unique constraint báo trùng và consumer bỏ qua side effect đã hoàn tất.

Một inbox record chỉ nên được coi là hoàn tất khi thay đổi nghiệp vụ liên quan đã commit. Nếu cần lưu trạng thái xử lý nhiều bước, hãy xác định trạng thái trung gian và cách phục hồi rõ ràng.

### Thời hạn lưu deduplication

Không xóa inbox record quá sớm. Broker có thể replay từ offset cũ, message có thể được gửi lại sau outage dài hoặc operator có thể chạy lại batch. Nếu dedup record đã bị xóa trước khi cửa sổ replay kết thúc, sự kiện cũ có thể được áp dụng lần nữa.

Retention nên lớn hơn khoảng thời gian tối đa mà hệ thống cho phép replay hoặc retry, có tính đến backup restore, disaster recovery và quy trình vận hành. Với nghiệp vụ tài chính hoặc kiểm toán, có thể cần lưu dấu vết lâu dài hoặc dựa vào khóa nghiệp vụ có unique constraint.

## 7. Thứ tự xử lý: xác định phạm vi cần giữ

Giữ thứ tự có nhiều mức: thứ tự producer gửi vào partition hoặc queue; thứ tự broker giao cho consumer; thứ tự consumer hoàn tất side effect; thứ tự thay đổi được nhìn thấy ở database; và thứ tự toàn cục giữa nhiều partition hoặc producer.

Một broker thường chỉ bảo đảm thứ tự trong phạm vi cụ thể. Kafka bảo đảm thứ tự trong một partition, không có thứ tự toàn cục giữa nhiều partition. Một queue có thể giao theo FIFO nhưng xử lý đồng thời nhiều message vẫn làm thứ tự hoàn tất khác với thứ tự nhận.

### Partition theo khóa nghiệp vụ

Nếu các sự kiện của cùng một đơn hàng phải theo thứ tự, hãy dùng orderId làm message key để broker định tuyến chúng vào cùng partition:

~~~text
order-101: CREATED -> PAID -> SHIPPED  (cùng partition)
order-202: CREATED -> CANCELLED       (có thể ở partition khác)
~~~

Consumer có thể xử lý các partition khác nhau song song, nhưng nên giữ thứ tự trong từng partition. Điều này tạo khả năng mở rộng mà vẫn giữ thứ tự của một aggregate. Không dùng một khóa chung cho mọi message nếu không cần thứ tự toàn cục vì nó dồn dữ liệu vào một partition; cũng không dùng khóa ngẫu nhiên cho các sự kiện cùng aggregate nếu cần giữ thứ tự.

### Xử lý tuần tự trong từng partition

Reactor Kafka cung cấp luồng theo partition qua receivePartitioned() ở các phiên bản hỗ trợ API này. Có thể xử lý từng partition tuần tự và xử lý nhiều partition đồng thời:

~~~java
receiver.receivePartitioned()
    .flatMap(
        partition ->
            partition.concatMap(record ->
                processIdempotently(record.value())
                    .then(record.receiverOffset().commit())
            ),
        partitionConcurrency
    );
~~~

concatMap giữ thứ tự trong mỗi partition. flatMap bên ngoài cho phép nhiều partition hoạt động đồng thời. partitionConcurrency cần phù hợp với số partition được gán và năng lực database. Đây là mẫu tổng quát; cần đối chiếu API và cách commit offset của phiên bản Reactor Kafka đang sử dụng. Khi dùng commit theo batch hoặc acknowledge, vẫn phải bảo đảm không commit vượt qua record trước đó chưa xử lý xong trong cùng partition.

### Không có thứ tự toàn cục miễn phí

Nếu hai aggregate ở hai partition khác nhau, consumer có thể xử lý đồng thời và hoàn tất theo thứ tự khác nhau. Nếu nghiệp vụ thực sự cần thứ tự toàn cục, cần một điểm tuần tự hóa hoặc một nguồn thứ tự duy nhất. Điều đó thường làm giảm khả năng mở rộng và cần được biện minh bằng yêu cầu nghiệp vụ.

## 8. Parallel processing và offset commit có thể gây mất dữ liệu

flatMap tăng concurrency nhưng có thể làm record hoàn tất không theo thứ tự nhận. Với Kafka, commit offset là tiến độ theo partition, không phải acknowledgement độc lập cho từng record.

Giả sử offset 40 xử lý chậm, offset 41 xử lý nhanh. Nếu consumer commit offset tiếp theo là 42 trước khi offset 40 hoàn tất, broker có thể bắt đầu lại từ 42 sau restart. Offset 40 sẽ bị bỏ qua dù side effect chưa được thực hiện.

Có ba chiến lược:

1. **Tuần tự hóa trong partition:** dùng concatMap để record trước hoàn tất rồi mới xử lý record sau. Đây là cách dễ hiểu và an toàn cho thứ tự.
2. **Song song giữa partition:** mỗi partition có một luồng tuần tự; các partition chạy đồng thời.
3. **Theo dõi offset hoàn tất liên tục:** cho phép xử lý song song trong partition nhưng chỉ commit offset cao nhất mà mọi offset trước nó đã hoàn tất. Cách này phức tạp và cần xử lý gap, retry, rebalance và cancellation.

Không dùng flatMap không giới hạn trên một partition rồi commit từng record độc lập nếu chưa hiểu semantics commit tích lũy. Kiểm thử crash sau khi record sau hoàn tất nhưng record trước còn chạy để phát hiện lỗi.

## 9. Retry, backoff và dead-letter queue

Retry hữu ích với lỗi tạm thời như timeout, broker unavailable hoặc database connection reset. Retry vô hạn có thể giữ partition bị kẹt, chiếm connection và làm backlog tăng. Retry cần có giới hạn, backoff và phân loại lỗi.

~~~java
Mono<Void> processRecord(ReceiverRecord<String, OrderEvent> record) {
    return Mono.defer(() ->
            processIdempotently(record.value())
        )
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(3))
                .filter(this::isTransient)
        )
        .then(record.receiverOffset().commit());
}
~~~

Mono.defer bảo đảm mỗi lần retry gọi lại thao tác xử lý. Retry chỉ áp dụng cho lỗi được phân loại là transient. Nếu hết số lần retry, Publisher phát lỗi và commit không chạy; record chưa được xác nhận có thể được giao lại theo cấu hình broker và vòng đời consumer.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout ngắn, kết nối database gián đoạn, rate limit có thời hạn | Retry có backoff và giới hạn |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, schema không hỗ trợ | Ghi dead-letter kèm payload và nguyên nhân |
| Lỗi nghiệp vụ có thể từ chối | Đơn hàng đã đóng, hạn mức không đủ | Ghi nhận kết quả từ chối theo mô hình nghiệp vụ |
| Lỗi lập trình | Null bất ngờ, invariant bị vi phạm | Không retry mù; báo lỗi hoặc chuyển quy trình điều tra |

### Chỉ commit sau khi dead-letter được xác nhận

~~~java
Mono<Void> processOrDeadLetter(ReceiverRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    return processIdempotently(event)
        .onErrorResume(
            this::isPermanent,
            error -> deadLetterSender.send(
                event.eventId(), event, error
            ).then()
        )
        .then(record.receiverOffset().commit());
}
~~~

Mẫu này giả định send của dead-letter sender chỉ hoàn tất sau khi broker xác nhận đã nhận message. Nếu publish dead-letter thành công nhưng commit offset gốc thất bại, record gốc có thể được giao lại và dead-letter có thể được gửi trùng. Dead-letter consumer cũng cần eventId và xử lý idempotent.

Không chuyển lỗi tạm thời sang DLQ ngay lập tức nếu hệ thống có thể phục hồi. Cũng không commit record lỗi vĩnh viễn trước khi payload và nguyên nhân đã được lưu bền vững ở nơi có thể điều tra.

### Retry có thể phá thứ tự

Nếu record A lỗi và được trì hoãn để retry, trong khi record B cùng aggregate vẫn được xử lý, B có thể hoàn tất trước A. Nếu nghiệp vụ yêu cầu thứ tự, hãy tạm dừng partition/queue, giữ các record sau chờ A, hoặc đưa A vào quy trình lỗi có ranh giới rõ trước khi tiếp tục. Đừng dùng retry delay độc lập cho từng record mà bỏ qua quan hệ thứ tự.

## 10. Backpressure không phải acknowledgement

Trong Reactor, backpressure điều khiển số phần tử downstream yêu cầu từ upstream. Nó giúp tránh để consumer reactive nhận nhiều phần tử hơn mức đang yêu cầu. Tuy nhiên, backpressure không tự xác nhận thông điệp đã được xử lý bền vững.

| Cơ chế | Câu hỏi được trả lời | Điều nó không bảo đảm |
|---|---|---|
| request(n) | Consumer có thể nhận thêm bao nhiêu phần tử? | Side effect đã commit hay message đã ack |
| Buffer trong pipeline | Giữ bao nhiêu phần tử đang chờ? | Dữ liệu sống sót sau process crash |
| Acknowledge | Consumer tuyên bố đã xử lý đến đâu? | Side effect ngoài broker đã atomic |
| Offset commit | Broker lưu tiến độ tiêu thụ nào? | Database và broker cùng commit một transaction |
| Inbox/idempotency | Xử lý lặp có tạo side effect lần nữa không? | Thông điệp luôn được giao nếu producer không publish thành công |

Ví dụ, buffer(100) gom 100 record thành một batch. Điều đó không có nghĩa broker đã lưu hoặc consumer đã xác nhận batch. Nếu tiến trình chết trước khi commit, broker có thể giao lại các record. Nếu buffer nằm trong bộ nhớ, nó biến mất khi tiến trình dừng.

Tương tự, limitRate điều chỉnh request ở ranh giới reactive nhưng không thay thế giới hạn queue của broker, database hoặc HTTP client. Hãy theo dõi demand, prefetch, số record đang xử lý, lag, pending acknowledgement và thời gian commit.

## 11. Kiểm thử duplicate, retry và thứ tự

Một bộ kiểm thử giao nhận nên xác nhận cả các ranh giới, không chỉ kiểm tra hàm map trả đúng dữ liệu.

### Duplicate không áp dụng side effect lần hai

~~~java
@Test
void duplicateEventIsAppliedOnlyOnce() {
    OrderEvent event = new OrderEvent("evt-100", "order-7");

    StepVerifier.create(handle(event).then(handle(event)))
        .verifyComplete();

    StepVerifier.create(orderRepository.findById("order-7"))
        .assertNext(order ->
            assertEquals(1, order.appliedEventCount())
        )
        .verifyComplete();
}
~~~

Test giả định handle dùng inbox với unique constraint và transaction thật. Gửi cùng eventId hai lần nhưng business effect chỉ được áp dụng một lần. Với test tích hợp, cần xác nhận inbox record và thay đổi nghiệp vụ nằm trong cùng transaction.

### Commit chỉ chạy sau khi xử lý thành công

~~~java
AtomicBoolean processed = new AtomicBoolean();
AtomicBoolean committed = new AtomicBoolean();

Mono<Void> work =
    Mono.fromRunnable(() -> processed.set(true))
        .then(Mono.fromRunnable(() -> {
            if (!processed.get()) {
                throw new IllegalStateException("commit too early");
            }
            committed.set(true);
        }));

StepVerifier.create(work).verifyComplete();
assertTrue(processed.get());
assertTrue(committed.get());
~~~

Đây là kiểm thử thứ tự của pipeline giả lập. Integration test với broker cần kiểm tra offset thực sự được commit sau khi side effect đã commit, và kiểm tra record có thể được giao lại khi xử lý lỗi trước commit.

### Lỗi xử lý không được commit

~~~java
AtomicBoolean committed = new AtomicBoolean();

Mono<Void> work =
    Mono.<Void>error(new IllegalStateException("database unavailable"))
        .then(Mono.fromRunnable(() -> committed.set(true)));

StepVerifier.create(work)
    .expectErrorMessage("database unavailable")
    .verify();

assertFalse(committed.get());
~~~

Nếu xử lý lỗi, bước commit ở sau then không được chạy. Kiểm thử này xác nhận luồng điều khiển; cần bổ sung integration test để xác nhận broker thực tế vẫn có thể giao lại record.

### Thứ tự trong một partition

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3)
            .concatMap(value ->
                Mono.delay(Duration.ofMillis(10)).thenReturn(value)
            )
    )
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

concatMap chờ từng Publisher con hoàn tất trước khi xử lý phần tử tiếp theo, nên đầu ra giữ thứ tự nguồn. Nếu thay bằng flatMap, thứ tự hoàn tất có thể khác khi mỗi tác vụ có thời gian xử lý khác nhau. Với broker thật, hãy kiểm thử nhiều record cùng partition, nhiều partition và tình huống rebalance.

### Kiểm thử crash window

Tạo integration test mô phỏng tình huống: consumer cập nhật database và commit transaction; test cố ý không commit offset hoặc làm consumer dừng trước bước commit; khởi động consumer lại để record được giao lại; xác nhận inbox nhận diện eventId đã xử lý và business effect không bị lặp. Đây là test quan trọng cho mô hình at-least-once. Một unit test chỉ gọi handle hai lần chưa mô phỏng đầy đủ việc broker redeliver sau process crash.

## 12. Quan sát vận hành và phục hồi

Bảo đảm giao nhận cần được quan sát liên tục. Một pipeline có thể đúng về mặt code nhưng vẫn mất khả năng xử lý khi backlog tăng hoặc DLQ tích lũy.

Nên theo dõi:

- **Consumer lag:** chênh lệch giữa offset mới nhất và offset đã commit.
- **Processing latency:** thời gian từ lúc nhận đến khi side effect hoàn tất.
- **Commit latency và commit failure:** thời gian và số lần commit thất bại.
- **Redelivery/duplicate rate:** số message được giao lại hoặc bị inbox nhận diện là trùng.
- **Retry count:** số lần retry theo loại lỗi.
- **DLQ volume và age:** số lượng và tuổi của message đang chờ điều tra.
- **In-flight records:** số record đã nhận nhưng chưa xử lý/commit.
- **Partition assignment/rebalance:** số lần phân công lại và thời gian consumer tạm ngừng.
- **Outbox backlog:** số record chưa publish và thời gian tồn đọng lâu nhất.

Khi lag tăng, cần phân biệt producer phát quá nhanh, consumer xử lý chậm, database bị nghẽn, commit bị lỗi hay partition bị kẹt bởi một message độc hại. Chỉ tăng số consumer không phải lúc nào cũng tăng throughput: số consumer trong một consumer group bị giới hạn bởi số partition có thể được phân công.

### Phục hồi DLQ có kiểm soát

DLQ không phải nơi lưu dữ liệu rồi quên. Cần lưu eventId, key, payload, schema version, thời điểm lỗi và nguyên nhân; phân loại lỗi có thể sửa bằng dữ liệu hay cần sửa code; xác định message có còn đúng thứ tự nghiệp vụ khi replay; sửa dữ liệu hoặc consumer rồi replay với eventId ổn định; dùng inbox/idempotency để replay không nhân đôi side effect đã hoàn tất; ghi lại người hoặc job đã replay, thời điểm và kết quả.

Nếu replay một message cũ sau khi aggregate đã chuyển sang trạng thái mới hơn, consumer cần kiểm tra version hoặc sequence để không ghi đè trạng thái mới bằng dữ liệu cũ.

## 13. Những lỗi thiết kế thường gặp

- **Acknowledge trước khi side effect bền vững:** process chết sau ack có thể làm mất nghiệp vụ. Với at-least-once, xử lý và commit side effect trước rồi mới ack/commit offset.
- **Cho rằng xử lý xong nghĩa là broker đã biết:** side effect có thể commit nhưng acknowledgement chưa đến broker. Message vẫn có thể được giao lại; cần idempotency.
- **Dùng UUID mới cho mỗi lần retry:** mỗi lần thử trông như message mới và deduplication không có tác dụng. Giữ eventId ổn định.
- **Chỉ kiểm tra trùng ở tầng ứng dụng:** hai consumer có thể cùng vượt qua bước kiểm tra. Dùng unique constraint hoặc thao tác nguyên tử ở nơi lưu deduplication.
- **Ghi inbox và business effect ở hai transaction độc lập:** crash giữa hai transaction có thể làm đánh dấu đã xử lý nhưng chưa áp dụng nghiệp vụ. Gộp chúng trong cùng transaction nếu cùng database.
- **Publish message rồi mới lưu thay đổi database mà không có outbox:** hai hệ thống có thể lệch trạng thái khi một bước thành công và bước kia thất bại. Ghi outbox cùng transaction nghiệp vụ.
- **Commit offset vượt qua record chưa hoàn tất:** xử lý song song trong partition có thể làm mất record sau crash. Tuần tự hóa hoặc chỉ commit offset liên tục đã hoàn tất.
- **Giả định broker bảo đảm thứ tự toàn cục:** thứ tự thường chỉ có trong một queue hoặc partition. Partition theo khóa aggregate nếu cần thứ tự theo thực thể.
- **Retry vô hạn một poison message:** một record có thể chặn partition và làm lag tăng. Phân loại lỗi, giới hạn retry và dùng DLQ có kiểm soát.
- **Nhầm backpressure với durable delivery:** request(n) điều tiết luồng trong bộ nhớ; nó không lưu dữ liệu qua crash và không thay thế ack/commit.
- **Gọi exactly-once cho toàn bộ hệ thống:** transaction broker không tự bao gồm database hoặc email. Nêu rõ ranh giới bảo đảm và dùng outbox/inbox cho side effect bên ngoài.

## 14. Quy trình thiết kế bảo đảm giao nhận

Trước khi triển khai consumer hoặc producer, hãy trả lời:

1. **Mất thông điệp có chấp nhận được không?** Chọn at-most-once hay at-least-once theo yêu cầu nghiệp vụ.
2. **Điểm nào xác định xử lý thành công?** Sau khi ghi database, sau khi gọi API hay sau khi lưu vào queue bền vững?
3. **Acknowledgement/commit đặt ở đâu?** Chỉ xác nhận sau khi công việc cần bảo vệ đã hoàn tất.
4. **Event identity là gì?** Có khóa ổn định qua retry, replay và producer restart không?
5. **Deduplication nằm ở đâu?** Có unique constraint và transaction chung với business update không?
6. **Producer cần outbox không?** Nếu database change và publish phải cùng tồn tại, hãy lưu outbox trong transaction.
7. **Thứ tự cần giữ ở phạm vi nào?** Theo aggregate key, partition, queue hay toàn cục?
8. **Concurrency ảnh hưởng offset ra sao?** Có commit vượt qua record chưa hoàn tất không?
9. **Lỗi được phân loại thế nào?** Retry transient, DLQ permanent, cảnh báo programming error.
10. **Backpressure và buffer được giới hạn ra sao?** Theo dõi demand, prefetch, in-flight và broker lag.
11. **Replay có an toàn không?** Giữ eventId, kiểm tra sequence/version và idempotency.
12. **Đã kiểm thử crash window chưa?** Mô phỏng side effect thành công nhưng ack/commit thất bại.

Một thiết kế đáng tin cậy không dựa vào một tùy chọn broker duy nhất. Nó kết hợp identity ổn định, xác nhận đúng thời điểm, xử lý idempotent, thứ tự có phạm vi rõ và quy trình phục hồi quan sát được.

## 15. Bài tập vận dụng

Một dịch vụ thương mại điện tử nhận OrderCreated từ broker. Consumer phải tạo bản ghi giao hàng trong database, sau đó phát ShipmentRequested sang một topic khác. Các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự. Consumer có thể bị restart bất kỳ lúc nào.

Hãy thiết kế producer và consumer, sau đó trả lời:

1. Producer tạo OrderCreated cần dùng eventId ổn định như thế nào để retry không tạo identity mới?
2. Nếu producer lưu đơn hàng trong database và publish OrderCreated, tại sao transactional outbox giúp tránh trạng thái đơn hàng đã commit nhưng message chưa được gửi?
3. Consumer nên commit offset trước hay sau khi transaction tạo bản ghi giao hàng hoàn tất? Điều gì xảy ra nếu process dừng giữa hai bước?
4. Nếu database đã commit nhưng offset chưa commit, consumer cần làm gì khi OrderCreated được giao lại?
5. Inbox với unique constraint cần nằm trong transaction nào cùng với việc tạo bản ghi giao hàng?
6. Làm thế nào partition theo orderId để giữ thứ tự sự kiện của cùng đơn hàng?
7. Vì sao xử lý flatMap đồng thời trong một partition có thể làm commit offset vượt qua record chưa hoàn tất?
8. Lỗi database timeout nên retry thế nào? Lỗi payload không hợp lệ nên đi DLQ theo quy trình nào?
9. Nếu gửi ShipmentRequested thành công nhưng đánh dấu outbox published thất bại, duplicate sẽ được xử lý ở đâu?
10. Viết integration test mô phỏng database commit thành công, offset commit thất bại, consumer restart và record được giao lại.

Bài tập nên xác định rõ ranh giới transaction của database, broker và consumer. Nếu ShipmentRequested được gửi ra broker, hãy dùng outbox thứ hai trong transaction tạo bản ghi giao hàng để không phụ thuộc vào một lời gọi publish nằm ngoài transaction database.

## Kết luận

Giao nhận thông điệp đáng tin cậy cần xác định chính xác thời điểm xử lý được coi là hoàn tất. At-most-once có thể mất dữ liệu; at-least-once có thể giao lặp và cần consumer idempotent; exactly-once chỉ có ý nghĩa trong phạm vi transaction mà broker hoặc hệ thống thực sự hỗ trợ. Inbox và outbox phối hợp database với message broker, còn partition key và xử lý tuần tự theo partition giữ thứ tự trong phạm vi nghiệp vụ cần thiết. Backpressure kiểm soát demand trong pipeline, acknowledgement/offset commit xác nhận tiến độ bền vững. Kết hợp các cơ chế này với retry có giới hạn, DLQ, metrics và kiểm thử crash window giúp hệ thống reactive phục hồi an toàn khi có lỗi.
