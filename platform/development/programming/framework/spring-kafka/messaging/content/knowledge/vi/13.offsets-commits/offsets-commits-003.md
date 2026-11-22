# Commit đồng bộ và bất đồng bộ

Kafka consumer cần commit offset để lưu lại tiến độ đọc của consumer group. Khi commit, ứng dụng ghi nhận vị trí tiếp theo cần đọc cho từng partition. Kafka client cung cấp hai cách gửi yêu cầu commit: **commit đồng bộ** bằng commitSync và **commit bất đồng bộ** bằng commitAsync.

Commit đồng bộ chờ broker trả kết quả trước khi tiếp tục. Commit bất đồng bộ gửi yêu cầu rồi tiếp tục công việc, kết quả được thông báo sau qua callback. Hai cách có đặc tính khác nhau về độ trễ, khả năng quan sát lỗi và cách xử lý khi commit thất bại.

Trong Spring Kafka, listener container quản lý thời điểm commit theo AckMode. Thuộc tính syncCommits quyết định container dùng commitSync hay commitAsync khi gửi yêu cầu commit. Cần phân biệt rõ thời điểm commit với cách thực hiện commit: AckMode và syncCommits giải quyết hai vấn đề khác nhau.

Bài học thuộc chương **Offset và commit** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách chọn commit đồng bộ hoặc bất đồng bộ, cấu hình Spring Kafka, xử lý lỗi commit và bảo đảm consumer có thể phục hồi an toàn.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích offset được commit là vị trí tiếp theo cần đọc của partition.
- Phân biệt commitSync và commitAsync.
- Hiểu ảnh hưởng của commit latency, timeout và lỗi rebalance.
- Cấu hình syncCommits trong listener container của Spring Kafka.
- Theo dõi kết quả commit bất đồng bộ qua commit callback.
- Tránh retry commit cũ làm lùi tiến độ đã commit mới hơn.
- Phân biệt AckMode, syncCommits và asyncAcks.
- Chọn chiến lược commit theo yêu cầu độ trễ, thông lượng và khả năng phục hồi.
- Kiểm thử offset commit và các tình huống lỗi có kiểm soát.

## 1. Offset commit lưu điều gì?

Kafka lưu record theo từng partition. Mỗi record trong partition có một offset tăng dần. Consumer đọc record và commit offset để ghi nhận tiến độ của group.

Offset được commit là **offset tiếp theo mà consumer muốn đọc**, không phải offset của record cuối vừa xử lý.

Ví dụ consumer xử lý các record:

| Partition | Record cuối đã xử lý | Offset commit |
|---|---:|---:|
| orders.created-0 | 41 | 42 |
| orders.created-1 | 18 | 19 |
| orders.created-2 | 105 | 106 |

Mỗi partition có một offset riêng. Một commit request có thể chứa nhiều partition cùng lúc, nhưng không có một offset tổng thể đại diện cho toàn topic.

Nếu ứng dụng xử lý record offset 41 rồi commit 42, khi consumer group khởi động lại và tiếp tục từ offset đã commit, Kafka sẽ giao record bắt đầu từ vị trí 42 theo dữ liệu còn được giữ.

Điều này cũng giải thích rủi ro khi commit sai thời điểm:

- Commit sau khi xử lý thành công: record có thể được giao lại nếu commit chưa hoàn tất, tạo khả năng xử lý lặp.
- Commit trước khi xử lý xong: nếu ứng dụng dừng sau commit, record có thể bị bỏ qua khi group đọc tiếp.
- Không commit: group có thể tiếp tục từ offset cũ sau restart hoặc rebalance và đọc lại các record đã xử lý.

Vì vậy, commit cần gắn với tiến độ xử lý thực tế. Commit đồng bộ hay bất đồng bộ chỉ thay đổi cách gửi yêu cầu commit; chúng không tự quyết định record đã được xử lý an toàn hay chưa.

## 2. Commit đồng bộ với commitSync

commitSync gửi yêu cầu commit offset và chờ broker trả kết quả. Luồng gọi chỉ tiếp tục sau khi commit hoàn tất, gặp lỗi không thể phục hồi hoặc hết thời gian chờ theo cấu hình.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Consumer thread
    participant Broker as Kafka broker
    App->>App: Xử lý record
    App->>Broker: commitSync(offsets)
    Broker-->>App: Commit response
    App->>App: Tiếp tục poll
~~~

Đặc điểm của commitSync:

- Caller biết yêu cầu commit đã thành công hay thất bại trước khi tiếp tục.
- Lỗi commit có thể được xử lý ngay trong luồng gọi.
- Kafka client có thể thử lại các lỗi tạm thời có thể phục hồi trong giới hạn timeout.
- Thời gian chờ commit làm tăng thời gian giữa các lần poll.
- Nếu commit thất bại do consumer không còn thuộc generation hợp lệ sau rebalance, ứng dụng không thể coi offset đã được lưu thành công.

commitSync thường dễ hiểu và dễ vận hành hơn khi cần biết kết quả commit tại thời điểm thực hiện. Đổi lại, thời gian chờ broker có thể làm tăng latency của consumer.

Trong Kafka client, có các overload commitSync nhận timeout. Nếu không truyền timeout tường minh, client sử dụng timeout API mặc định theo cấu hình. Hãy chọn timeout phù hợp với thời gian phản hồi của cluster và giới hạn poll của consumer.

## 3. Commit bất đồng bộ với commitAsync

commitAsync gửi yêu cầu commit mà không chờ broker phản hồi ngay tại lời gọi. Consumer có thể tiếp tục công việc; kết quả commit được thông báo sau qua callback.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Consumer thread
    participant Broker as Kafka broker
    App->>App: Xử lý record
    App->>Broker: commitAsync(offsets, callback)
    App->>App: Tiếp tục công việc
    Broker-->>App: Commit response
    App->>App: Callback success hoặc failure
~~~

Đặc điểm của commitAsync:

- Lời gọi trả về nhanh hơn vì không đợi commit response.
- Lỗi commit được thông báo qua callback.
- Kafka consumer không tự retry commitAsync theo cách giống commitSync; việc retry tùy tiện có thể gây vấn đề về thứ tự offset.
- Ứng dụng cần quan sát callback và có chính sách phù hợp khi commit thất bại.
- Một commit chưa được xác nhận có thể vẫn đang chờ xử lý khi consumer tiếp tục poll.

Commit bất đồng bộ hữu ích khi muốn giảm thời gian chặn ở bước commit và chấp nhận quản lý kết quả callback. Nó đòi hỏi hiểu rõ thứ tự commit, lỗi và quá trình đóng consumer.

## 4. So sánh commitSync và commitAsync

| Tiêu chí | commitSync | commitAsync |
|---|---|---|
| Chờ kết quả broker | Có | Không chờ tại lời gọi |
| Độ trễ tại consumer thread | Có thể cao hơn do chờ response | Thấp hơn tại lời gọi |
| Nhận biết lỗi | Trực tiếp qua kết quả hoặc exception | Qua callback |
| Retry | Client xử lý retry các lỗi tạm thời trong giới hạn timeout | Không tự retry theo cơ chế tương tự commitSync |
| Nguy cơ về thứ tự | Caller chờ commit hiện tại trước khi tiếp tục | Cần tránh retry một offset cũ sau khi tiến độ mới đã được commit |
| Độ phức tạp vận hành | Thường đơn giản hơn | Cần callback, metric và chính sách lỗi |
| Phù hợp | Cần xác nhận commit rõ ràng, ưu tiên đơn giản và khả năng quan sát | Cần giảm thời gian chờ commit và có khả năng quản lý callback |

Không có lựa chọn tối ưu cho mọi ứng dụng. Hãy bắt đầu với commit đồng bộ nếu chưa có bằng chứng rằng thời gian chờ commit là bottleneck. Chỉ chuyển sang bất đồng bộ khi đã đo latency và có cách quan sát lỗi commit.

## 5. Cấu hình commit trong Spring Kafka

Spring Kafka listener container quản lý việc commit offset. Thuộc tính syncCommits quyết định container dùng commitSync hay commitAsync.

Trong ContainerProperties, syncCommits mặc định là true. Vì vậy, container thường thực hiện commit đồng bộ.

Ví dụ cấu hình listener container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    var containerProperties = factory.getContainerProperties();
    containerProperties.setAckMode(ContainerProperties.AckMode.BATCH);
    containerProperties.setSyncCommits(true);
    containerProperties.setSyncCommitTimeout(Duration.ofSeconds(10));

    return factory;
}
~~~

Trong ví dụ, listener container xử lý theo AckMode.BATCH và commit đồng bộ với timeout được chỉ định. Kiểu dữ liệu, ConsumerFactory và tên bean cần được điều chỉnh theo ứng dụng. API timeout có thể khác theo phiên bản Spring Kafka đang dùng; hãy kiểm tra phiên bản dependency của dự án.

Để chuyển sang commit bất đồng bộ:

~~~java
containerProperties.setSyncCommits(false);
~~~

Khi syncCommits=false, container sử dụng commitAsync. Có thể cài đặt callback để quan sát kết quả commit.

## 6. Theo dõi commit bất đồng bộ bằng callback

Kafka consumer API cho phép truyền OffsetCommitCallback vào commitAsync. Spring Kafka cung cấp ContainerProperties để cấu hình callback dùng khi container commit bất đồng bộ.

Ví dụ:

~~~java
containerProperties.setSyncCommits(false);
containerProperties.setCommitCallback((offsets, exception) -> {
    if (exception != null) {
        log.error(
                "Kafka offset commit failed, offsets={}",
                offsets,
                exception
        );
        return;
    }

    log.debug("Kafka offset commit completed: {}", offsets);
});
~~~

Callback nhận:

- offsets: map các TopicPartition tới OffsetAndMetadata được yêu cầu commit.
- exception: lỗi nếu commit thất bại; null nếu commit thành công.

Callback là nơi phù hợp để ghi log, tăng counter lỗi hoặc phát tín hiệu giám sát. Không nên thực hiện truy vấn database, gọi HTTP đồng bộ hoặc xử lý nặng trong callback vì có thể ảnh hưởng luồng consumer.

Nên theo dõi tối thiểu:

- Số commit thành công.
- Số commit thất bại.
- Loại exception và nguyên nhân.
- Thời gian từ lúc gửi commit tới lúc nhận callback nếu ứng dụng đo được.
- Partition và offset liên quan để điều tra.

Không dùng offset hoặc group ID làm metric label có cardinality không giới hạn. Thông tin chi tiết theo partition phù hợp hơn với log hoặc trace; metric nên dùng nhãn có số lượng giá trị được kiểm soát.

## 7. Vì sao không nên retry commitAsync một cách tùy tiện?

Một vấn đề quan trọng của commit bất đồng bộ là thứ tự tiến độ.

Giả sử consumer gửi commit offset 20 rồi tiếp tục gửi commit offset 30. Callback báo lỗi cho commit 20 có thể được gọi trong khi commit 30 đã được gửi nhưng ứng dụng chưa nhận kết quả của nó. Nếu callback xếp một tác vụ retry offset 20 chạy muộn hơn, sau khi commit 30 đã thành công, request retry cũ có thể ghi lùi group về offset 20 nếu broker chấp nhận nó.

Điều này làm consumer đọc lại nhiều record hơn cần thiết và có thể lặp tác động nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant B as Broker
    C->>B: commitAsync(offset=20)
    C->>B: commitAsync(offset=30)
    B-->>C: callback offset=20 báo lỗi
    C->>C: Xếp tác vụ retry offset 20
    B-->>C: callback offset=30 thành công
    C->>B: Tác vụ retry gửi lại offset=20
    B-->>C: Retry offset=20 thành công
    Note over C: Commit cũ có thể ghi lùi tiến độ
~~~

Kafka consumer thông thường gọi callback theo thứ tự các request commit bất đồng bộ được gửi. Tuy nhiên, callback có thể xếp tác vụ retry lên executor hoặc hàng đợi khác; tác vụ đó có thể chạy sau khi commit mới hơn đã thành công. Vì vậy, logic retry thủ công vẫn phải kiểm tra tiến độ mới nhất và tránh gửi lại offset cũ.

Nguyên tắc an toàn:

- Không retry lại offset cũ một cách mù quáng sau khi đã có commit mới hơn.
- Nếu cần retry, phải bảo đảm offset gửi lại không thấp hơn tiến độ mới nhất mà consumer đã xử lý an toàn.
- Cân nhắc dùng commitSync ở ranh giới cần xác nhận chắc chắn, chẳng hạn trước khi kết thúc hoặc trong luồng cần bảo đảm thứ tự.
- Ưu tiên cơ chế commit do Spring Kafka container quản lý thay vì tự gọi commit từ nhiều nơi.
- Ghi nhận lỗi commit và đánh giá khả năng record được giao lại sau restart/rebalance.

Trong phần lớn ứng dụng Spring Kafka, không cần tự xây dựng vòng retry commitAsync. Hãy dùng cơ chế container và callback để quan sát lỗi; thiết kế idempotency để chịu được redelivery khi offset chưa được commit.

## 8. AckMode và syncCommits là hai cấu hình khác nhau

AckMode xác định **khi nào** container quyết định commit offset. syncCommits xác định **commit theo cách nào**.

Ví dụ:

| Cấu hình | Ý nghĩa |
|---|---|
| AckMode.RECORD + syncCommits=true | Sau mỗi record listener thành công, container commit đồng bộ theo chính sách RECORD. |
| AckMode.BATCH + syncCommits=true | Sau khi xử lý thành công các record của poll, container commit đồng bộ. |
| AckMode.BATCH + syncCommits=false | Sau khi xử lý thành công các record của poll, container gửi commit bất đồng bộ. |
| AckMode.MANUAL + syncCommits=false | Listener chủ động acknowledge; container thực hiện commit bất đồng bộ theo semantics của chế độ manual. |

Chuyển syncCommits từ true sang false không làm thay đổi ranh giới xử lý được xác nhận bởi AckMode. Nó chỉ thay đổi cách gửi yêu cầu commit tới broker.

Cũng cần phân biệt commitAsync với thuộc tính asyncAcks của Spring Kafka. asyncAcks cho phép acknowledgement của các record trong cùng một poll đến không theo thứ tự và container trì hoãn commit cho tới khi đủ acknowledgement. Đây là một tính năng khác; nó không đơn giản có nghĩa container dùng Kafka commitAsync.

## 9. Ảnh hưởng của commit tới poll loop và rebalance

Consumer cần tiếp tục poll trong khoảng thời gian phù hợp để duy trì membership của group. Khi dùng commitSync, thời gian chờ commit là một phần thời gian consumer chưa gọi poll tiếp theo.

Nếu broker phản hồi chậm, commitSync có thể làm thời gian giữa hai lần poll tăng. Nếu tổng thời gian xử lý và commit vượt max.poll.interval.ms, consumer có thể bị xem là không còn tiến triển và group có thể rebalance.

CommitAsync giảm thời gian chặn tại lời gọi, nhưng không loại bỏ các rủi ro khác của poll loop. Listener vẫn phải xử lý record trong giới hạn phù hợp, và commit callback cũng cần gọn nhẹ.

Khi rebalance xảy ra:

- Partition có thể bị thu hồi khỏi consumer hiện tại.
- Commit offset sau khi partition đã bị thu hồi hoặc generation không còn hợp lệ có thể thất bại.
- Record chưa được commit có thể được giao cho consumer member mới.
- Ứng dụng cần idempotency để xử lý lại an toàn.

Không nên dùng commitAsync chỉ để che giấu listener xử lý quá lâu. Hãy đo thời gian xử lý record, commit latency, poll interval và rebalance frequency trước khi thay đổi cấu hình.

## 10. Commit khi shutdown và trước khi rời group

Khi ứng dụng dừng, listener container cần kết thúc xử lý và lưu tiến độ phù hợp trước khi consumer đóng. Spring Kafka quản lý vòng đời container và có thể thực hiện commit theo cấu hình, trạng thái xử lý và cách container dừng.

Với commit đồng bộ, kết quả commit có thể được chờ trước khi hoàn tất bước đóng. Với commit bất đồng bộ, cần hiểu callback và thời điểm consumer đóng; không giả định callback sẽ được xử lý như một thao tác blocking trước khi shutdown hoàn tất trong mọi tình huống.

Các nguyên tắc vận hành:

- Dừng nhận công việc mới một cách có kiểm soát.
- Cho listener đang xử lý thời gian hoàn tất trong giới hạn shutdown timeout.
- Không commit offset của record chưa xử lý thành công.
- Đảm bảo record chưa commit có thể được giao lại sau khi restart.
- Theo dõi lỗi commit trong giai đoạn shutdown.
- Thiết kế handler idempotent để chịu được redelivery.

Nếu ứng dụng xử lý bất đồng bộ bên ngoài listener, cần quản lý các công việc đang chạy trước khi container dừng. Commit offset trước khi công việc hoàn tất có thể làm mất cơ hội giao lại record khi process bị dừng.

## 11. Commit offset và exactly-once

CommitSync hay commitAsync đều không tự tạo ra exactly-once cho toàn bộ nghiệp vụ.

Ví dụ consumer đọc OrderCreatedEvent, cập nhật database rồi commit offset. Nếu database commit thành công nhưng Kafka offset commit thất bại, record có thể được giao lại. Consumer sẽ cần nhận diện event đã xử lý để không cập nhật database lần nữa.

Ngược lại, nếu offset được commit trước khi database hoàn tất và ứng dụng dừng, record có thể không được giao lại dù tác động nghiệp vụ chưa hoàn tất.

Để giảm rủi ro:

- Dùng eventId ổn định cho mỗi sự kiện.
- Lưu inbox/deduplication key trong cùng transaction database với thay đổi nghiệp vụ.
- Đảm bảo thao tác nghiệp vụ có tính idempotent.
- Với luồng consume-transform-produce, cân nhắc Kafka transaction và commit offset cùng transaction.
- Với database và Kafka, cân nhắc outbox/inbox vì Kafka transaction không tự bao phủ transaction database.

Kafka transaction có thể phối hợp ghi output record với offset input trong một transaction Kafka. Đây là phạm vi khác với commitSync/commitAsync thông thường. Khi dùng transaction, hãy kiểm tra commit hoặc abort của transaction thay vì suy luận từ callback của một commit offset riêng lẻ.

## 12. Chọn sync hay async theo tình huống

| Tình huống | Hướng cân nhắc | Lý do |
|---|---|---|
| Ứng dụng mới, chưa có số liệu bottleneck | Sync commit | Hành vi rõ ràng, dễ chẩn đoán. |
| Luồng xử lý cần biết commit thành công trước khi tiếp tục | Sync commit | Caller chờ được kết quả. |
| Commit latency đã đo được là bottleneck | Đánh giá async commit | Giảm thời gian chờ tại lời gọi commit. |
| Hệ thống có metric/callback và chính sách redelivery rõ | Có thể dùng async commit | Có khả năng quan sát lỗi và vận hành. |
| Xử lý side effect khó idempotent | Ưu tiên thiết kế lại tính lặp an toàn trước | Không cách commit nào tự loại bỏ rủi ro giữa xử lý và commit. |
| Listener thường xuyên vượt poll interval | Tối ưu xử lý và batch trước | Async commit không sửa được bottleneck xử lý. |

Hãy đo throughput, commit latency, consumer lag, rebalance và lỗi commit trên tải đại diện. Chỉ thay đổi sang async nếu lợi ích đo được lớn hơn độ phức tạp vận hành bổ sung.

## 13. Kiểm thử commit đồng bộ và bất đồng bộ

Kiểm thử nên xác minh offset group đã lưu, không chỉ kiểm tra phương thức listener hoàn tất.

Các lớp kiểm thử:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Configuration test | syncCommits có giá trị đúng và AckMode đúng. |
| Sync commit integration test | Sau xử lý, offset group được cập nhật tới vị trí mong đợi. |
| Async commit callback test | Callback nhận success hoặc exception theo tình huống. |
| Multi-partition test | Offset được commit riêng theo từng TopicPartition. |
| Rebalance test | Commit sau khi partition bị thu hồi được xử lý đúng. |
| Failure test | Commit lỗi không làm ứng dụng ghi nhận nhầm tiến độ. |
| Shutdown test | Container dừng có kiểm soát và record chưa commit có thể được giao lại. |
| Idempotency test | Redelivery không lặp side effect. |

Có thể dùng AdminClient để đọc offset đã commit của group bằng API listConsumerGroupOffsets. Ví dụ kiểm tra offset sau khi xử lý:

~~~java
Map<TopicPartition, OffsetAndMetadata> committed =
        adminClient.listConsumerGroupOffsets("orders-fulfillment")
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS);

OffsetAndMetadata position = committed.get(
        new TopicPartition("orders.created", 0)
);

assertThat(position).isNotNull();
assertThat(position.offset()).isEqualTo(expectedNextOffset);
~~~

Test cần bảo đảm consumer đã xử lý và commit trước khi đọc offset. Dùng Awaitility hoặc một điều kiện đồng bộ với timeout rõ ràng; tránh Thread.sleep cố định.

Để kiểm thử commitAsync callback thất bại, nên dùng unit test cho logic callback hoặc một test broker/network fault có kiểm soát. Không dựa vào việc dừng broker ngẫu nhiên trong suite test vì lỗi có thể không tái hiện ổn định.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ commitAsync đã thành công ngay khi method trả về | Consumer có thể tiếp tục dù broker chưa xác nhận offset | Theo dõi callback và hiểu trạng thái pending. |
| Retry commit cũ sau khi đã gửi commit mới | Có nguy cơ ghi lùi offset | Không retry mù; bảo đảm offset retry không cũ hơn tiến độ an toàn. |
| Bật auto-commit cùng container-managed commit | Tiến độ có thể được commit ngoài AckMode dự kiến | Để enable.auto.commit=false. |
| Dùng async để che giấu listener chậm | Consumer vẫn có thể vượt max.poll.interval.ms | Tối ưu poll loop và thời gian xử lý. |
| Bỏ qua callback exception | Không quan sát được lỗi commit | Ghi metric/log và theo dõi commit failure. |
| Commit trước khi xử lý hoàn tất | Có thể bỏ qua record sau restart | Chỉ xác nhận tiến độ đã xử lý an toàn. |
| Cho rằng sync commit bảo đảm exactly-once | Side effect database vẫn có thể lặp khi commit offset thất bại | Dùng idempotency hoặc inbox/outbox. |
| Nhầm asyncAcks với commitAsync | Cấu hình và hành vi bị hiểu sai | Phân biệt acknowledgement order với cách gửi commit request. |

## 15. Bài tập tổng hợp: so sánh sync và async commit

Hãy xây dựng consumer cho topic orders.created với group orders-fulfillment.

Yêu cầu:

1. Cấu hình AckMode.BATCH và enable.auto.commit=false.
2. Chạy với syncCommits=true và ghi nhận thời gian xử lý poll cùng commit latency.
3. Đọc offset đã commit bằng AdminClient sau khi xử lý nhiều record.
4. Chuyển syncCommits=false và cấu hình commit callback.
5. Ghi nhận callback success và tạo metric cho commit failure.
6. Mô phỏng lỗi broker hoặc rebalance trong môi trường test để kiểm tra commit thất bại.
7. Xác minh consumer không retry một offset cũ sau khi đã tiến tới offset mới hơn.
8. Dừng consumer trong lúc xử lý để kiểm tra redelivery của record chưa commit.
9. Chạy test với nhiều partition và xác minh offset được lưu riêng theo partition.
10. So sánh throughput, commit latency, lag và tần suất lỗi giữa hai cấu hình.
11. Thêm idempotency cho eventId để xử lý an toàn khi record được giao lại.
12. Ghi rõ lý do lựa chọn sync hoặc async dựa trên kết quả đo.

Bài tập hoàn thành khi bạn chứng minh được cách đọc offset commit, quan sát callback bất đồng bộ, phân tích lỗi commit và giải thích vì sao commit strategy không thay thế idempotency.

## 16. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Offset model | Offset tiếp theo và partition | Tính đúng offset commit sau record cuối. |
| 2. Sync commit | commitSync và timeout | Giải thích được vì sao caller chờ kết quả. |
| 3. Async commit | commitAsync và callback | Theo dõi được kết quả và lỗi commit. |
| 4. Spring Kafka | syncCommits, commitCallback | Cấu hình đúng trong listener container. |
| 5. Ordering | Nhiều commit bất đồng bộ | Tránh retry commit cũ làm lùi tiến độ. |
| 6. Poll/rebalance | Commit latency và membership | Hiểu ảnh hưởng tới poll interval và partition assignment. |
| 7. Reliability | Idempotency và transaction | Không nhầm commit offset với exactly-once nghiệp vụ. |
| 8. Testing | AdminClient, EmbeddedKafka/Testcontainers | Kiểm tra được offset đã commit và failure path. |
| 9. Operations | Metrics, logs, shutdown | Theo dõi được commit latency và lỗi trong vận hành. |

Bài học hoàn thành khi bạn có thể giải thích chính xác sự khác nhau giữa commitSync và commitAsync, cấu hình được syncCommits trong Spring Kafka, theo dõi lỗi commit bất đồng bộ và lựa chọn chiến lược dựa trên số liệu.

Commit đồng bộ ưu tiên biết kết quả trước khi tiếp tục; commit bất đồng bộ giảm thời gian chờ tại lời gọi nhưng yêu cầu quan sát callback và quản lý thứ tự tiến độ cẩn thận. Dù chọn cách nào, offset chỉ nên phản ánh công việc đã hoàn tất an toàn, còn tác động nghiệp vụ cần idempotency hoặc cơ chế transaction phù hợp.

