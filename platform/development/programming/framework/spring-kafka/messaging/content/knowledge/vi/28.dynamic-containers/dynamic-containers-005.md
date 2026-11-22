# Dừng và xóa container động

Spring Kafka cho phép tạo listener container khi ứng dụng đang chạy, ví dụ mỗi tenant hoặc mỗi topic có một consumer riêng. Khi không còn nhu cầu tiêu thụ, ứng dụng cần dừng container đúng vòng đời và giải phóng tham chiếu đang quản lý. Thao tác này chỉ tác động đến consumer container trong ứng dụng; nó không xóa topic Kafka, record hay committed offset của consumer group.

Cần phân biệt ba thao tác: `pause()` tạm ngừng nhận record nhưng giữ container hoạt động; `stop()` dừng consumer và đóng vòng đời chạy; `destroy()` giải phóng tài nguyên của container do ứng dụng sở hữu. Nếu container được đăng ký trong `KafkaListenerEndpointRegistry`, còn có bước `unregisterListenerContainer()` để bỏ container khỏi registry.

## 1. Phân biệt pause, stop, destroy và unregister

| Thao tác | Mục đích | Có thể tiếp tục chạy? |
| --- | --- | --- |
| `pause()` | Tạm dừng tiêu thụ các partition đang được gán; container vẫn duy trì vòng poll và có thể resume. | Có, gọi `resume()`. |
| `stop()` | Dừng listener container, kết thúc consumer đang chạy và rời khỏi consumer group. | Có thể gọi `start()` lại trên container còn được quản lý. |
| `destroy()` | Giải phóng tài nguyên của instance container sau khi không còn dùng. | Không nên khởi động lại instance đã destroy; tạo instance mới nếu cần. |
| `unregisterListenerContainer(id)` | Xóa tham chiếu container khỏi `KafkaListenerEndpointRegistry`. | Có thể đăng ký container mới với ID đó sau khi container cũ đã dừng và được gỡ. |

`pause()` phù hợp với backpressure hoặc bảo trì ngắn hạn. `stop()` phù hợp khi một tenant ngừng sử dụng hoặc cấu hình consumer cần được thay thế. `destroy()` dành cho container do ứng dụng tự quản lý tài nguyên. `unregister` chỉ thay đổi registry, không tự dừng consumer.

Dừng container không xóa dữ liệu Kafka. Committed offset của group vẫn được broker lưu; nếu tạo container mới dùng cùng `group.id`, consumer tiếp tục theo offset đã commit. Nếu cần reset offset hoặc xóa topic, đó là thao tác quản trị Kafka riêng và phải có chính sách rõ ràng.

## 2. Tạo container động bằng container factory

Khi muốn tự quản lý listener, có thể dùng `ConcurrentKafkaListenerContainerFactory.createContainer(topic)` để tạo container trực tiếp. Ứng dụng chịu trách nhiệm lưu tham chiếu, đặt group ID, gắn listener, start, stop và destroy instance đó.

```java
public ConcurrentMessageListenerContainer<String, String> createContainer(
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String topic,
        String groupId,
        String containerName) {

    ConcurrentMessageListenerContainer<String, String> container =
        factory.createContainer(topic);
    container.getContainerProperties().setGroupId(groupId);
    container.getContainerProperties().setMessageListener(
        (MessageListener<String, String>) record ->
            orderService.process(record.value()));
    container.setBeanName(containerName);
    container.start();
    return container;
}
```

Container được tạo từ factory dùng `ConsumerFactory` và các thiết lập chung của factory. Hãy đặt `groupId` trước khi start. Nếu dùng `ConcurrentMessageListenerContainer`, concurrency có thể tạo nhiều child consumer container; hãy quản lý parent container được factory trả về để điều khiển toàn bộ nhóm.

Trong ứng dụng thực tế, lưu container theo một ID nghiệp vụ ổn định, chẳng hạn tenant ID đã được chuẩn hóa. Không tạo ID từ dữ liệu không kiểm soát hoặc để hai yêu cầu tạo cùng ID đồng thời. Dùng `ConcurrentHashMap` hoặc một service quản lý lifecycle để bảo đảm mỗi ID chỉ có một instance đang hoạt động.

## 3. Dừng container tự tạo và giải phóng tài nguyên

Không nên xóa container khỏi map ngay khi vừa gọi `stop()`. Việc dừng có thể diễn ra bất đồng bộ; callback của `stop(Runnable)` được gọi khi container hoàn tất quá trình dừng. Chỉ sau callback mới destroy instance và xóa tham chiếu đang quản lý.

```java
public void stopAndRemove(String id) {
    ConcurrentMessageListenerContainer<String, String> container =
        containers.get(id);
    if (container == null) {
        return;
    }

    container.stop(() -> {
        container.destroy();
        containers.remove(id, container);
    });
}
```

Dùng `remove(id, container)` để tránh xóa nhầm instance mới nếu cùng ID đã được thay thế trong lúc callback hoàn tất. Trong service đầy đủ, cần khóa hoặc quản lý trạng thái `STARTING`, `RUNNING`, `STOPPING`, `STOPPED` để không cho một lệnh start mới chạy đua với callback stop cũ.

Khi dừng, container hoàn tất hoặc chấm dứt xử lý theo shutdown timeout và lifecycle của nó, rồi đóng consumer. Hãy cấu hình shutdown timeout phù hợp với thời gian xử lý tối đa của listener. Không tự đóng `KafkaConsumer` bên trong listener hoặc từ thread quản lý; consumer được container sở hữu và phải được đóng qua lifecycle của container.

## 4. Dừng và unregister container do @KafkaListener quản lý

Các container được tạo từ `@KafkaListener` không phải là bean thông thường trong application context. Spring Kafka đăng ký và quản lý chúng qua `KafkaListenerEndpointRegistry`. Lấy container bằng ID của annotation rồi gọi lifecycle trên container cụ thể.

```java
@KafkaListener(
    id = "tenant-orders-42",
    topics = "orders.tenant-42",
    groupId = "orders-tenant-42",
    autoStartup = "false")
public void listen(OrderEvent event) {
    orderService.process(event);
}
```

Có thể start hoặc stop listener theo ID:

```java
MessageListenerContainer container =
    registry.getListenerContainer("tenant-orders-42");

if (container != null) {
    container.start();
}
```

Từ Spring Kafka 2.8.9, `KafkaListenerEndpointRegistry` có `unregisterListenerContainer(id)`. Trình tự dừng và gỡ container như sau:

```java
public void stopAndUnregister(String id) {
    MessageListenerContainer container = registry.getListenerContainer(id);
    if (container == null) {
        return;
    }

    container.stop(() -> registry.unregisterListenerContainer(id));
}
```

`unregisterListenerContainer` chỉ xóa container khỏi registry; phương thức này không gọi `stop()` hoặc các phương thức lifecycle/disposable khác. Vì vậy, phải dừng container trước khi unregister. Sau khi gỡ, ID có thể được dùng lại cho một endpoint/container mới. Với phiên bản Spring Kafka trước 2.8.9, không có API unregister này; có thể stop container nhưng registry vẫn giữ đăng ký cho đến khi application context kết thúc.

Các container được khai báo thành bean trong application context không do `KafkaListenerEndpointRegistry` quản lý. Hãy lấy chúng từ context và để Spring quản lý lifecycle hoặc gọi lifecycle theo cách mà bean đó quy định; không tìm chúng bằng `registry.getListenerContainer(id)`.

## 5. Đăng ký lại container với cùng ID

Nếu dùng dynamic endpoint hoặc prototype bean có `@KafkaListener`, ID listener phải duy nhất trong registry. Sau khi container cũ đã dừng và được unregister, ID đó có thể được dùng lại. Không đăng ký container mới ngay khi mới phát lệnh stop vì consumer cũ có thể vẫn đang xử lý record và chưa rời group.

Với prototype bean, mỗi instance có thể nhận ID và topic khác nhau. Khi tạo instance sau khi application context đã refresh, container có thể tự start theo quy tắc lifecycle của registry; hãy kiểm soát `autoStartup` và `alwaysStartAfterRefresh` theo phiên bản Spring Kafka nếu cần trì hoãn start.

## 6. Điều gì xảy ra với consumer group và offset?

Khi container dừng, consumer đóng và rời group. Kafka có thể thực hiện rebalance để phân phối các partition của nó cho consumer còn lại. Các offset đã commit vẫn tồn tại trên broker. Container mới dùng cùng `group.id` tiếp tục từ offset đã commit; nếu dùng group ID mới, Kafka áp dụng `auto.offset.reset` khi group chưa có committed offset.

Record đang xử lý tại thời điểm stop cần được xét theo acknowledgement mode. Nếu record đã xử lý xong và offset được commit, nó không được giao lại cho group. Nếu process dừng trước khi commit, record có thể được giao lại cho consumer khác hoặc khi container khởi động lại. Vì vậy, listener vẫn cần idempotent và không nên xem stop là bảo đảm mọi side effect bên ngoài đã hoàn tất.

Không dùng `destroy()` để kỳ vọng xóa consumer group hoặc committed offset. Nếu yêu cầu nghiệp vụ là xóa group hoặc reset offset, dùng Kafka Admin API hoặc công cụ quản trị riêng sau khi chắc chắn không còn consumer hoạt động trong group.

## 7. Tránh race condition khi start và stop

Container động thường được quản lý bởi API hoặc job có thể nhận nhiều lệnh đồng thời. Một yêu cầu start có thể đến trong khi stop đang chạy; hai yêu cầu stop cũng có thể cùng đọc một tham chiếu. Nếu không có state machine, ứng dụng dễ tạo hai container cho cùng tenant hoặc xóa tham chiếu khi consumer cũ chưa đóng.

Một lifecycle service nên áp dụng các quy tắc:

- Chỉ tạo container khi ID chưa có container ở trạng thái `STARTING`, `RUNNING` hoặc `STOPPING`.
- Chuyển sang `STOPPING` trước khi gọi `stop()` để từ chối lệnh start trùng.
- Chỉ đánh dấu `STOPPED` và xóa map sau callback dừng hoàn tất.
- Nếu cần start lại, tạo instance mới sau khi instance cũ đã dừng và destroy.
- Xử lý callback lỗi hoặc timeout bằng trạng thái lỗi có thể quan sát và cơ chế retry vận hành.

Nếu nhiều application instance cùng quản lý một tenant, map trong bộ nhớ không đủ để bảo đảm duy nhất toàn cluster. Cần một cơ chế điều phối phân tán hoặc phân công tenant rõ ràng để tránh hai instance cùng tạo consumer theo chính sách không mong muốn.

## 8. Khi nào nên pause thay vì stop?

Dùng `pause()` khi muốn tạm ngừng nhận record nhưng giữ consumer và assignment, ví dụ hệ thống phụ thuộc đang quá tải hoặc cần bảo trì ngắn. Container tiếp tục thực hiện poll để duy trì consumer group; khi điều kiện phục hồi, gọi `resume()`.

Dùng `stop()` khi muốn giải phóng consumer, thay cấu hình hoặc kết thúc vòng đời container. Khi stop, consumer rời group và có thể gây rebalance. Nếu mục tiêu chỉ là điều tiết tốc độ hoặc tạm ngừng xử lý, pause thường ít xáo trộn assignment hơn.

## 9. Kiểm thử vòng đời container động

Một kiểm thử tích hợp nên tạo container từ factory, gửi record vào topic và xác minh listener nhận được record. Sau đó gọi `stop(Runnable)` và đợi callback; xác minh `isRunning()` là `false`, consumer không nhận record mới và tham chiếu được xóa khỏi map.

Với container do registry quản lý, kiểm thử lấy đúng ID, stop rồi unregister; sau đó xác minh `getListenerContainer(id)` trả về `null` và có thể đăng ký lại ID nếu phiên bản hỗ trợ. Kiểm thử thêm hai lệnh stop đồng thời, start trong khi stop, lỗi khởi tạo consumer, shutdown khi listener đang xử lý và restart bằng cùng group ID để xác minh offset tiếp tục đúng.

Dùng Embedded Kafka hoặc Testcontainers để quan sát consumer group, rebalance và committed offset. Không chỉ kiểm tra biến `isRunning`; cần xác minh consumer thực sự đã ngừng poll và không còn xử lý record sau khi lifecycle callback hoàn tất.

## 10. Checklist vận hành

- Gán ID duy nhất và lưu rõ container do factory hay registry quản lý.
- Đặt `group.id`, listener, concurrency và các thuộc tính cần thiết trước khi gọi `start()`.
- Dùng `pause/resume` cho tạm ngừng; dùng `stop` cho kết thúc vòng đời.
- Chờ callback của `stop(Runnable)` trước khi destroy, unregister hoặc xóa tham chiếu.
- Chỉ gọi `unregisterListenerContainer` trên phiên bản Spring Kafka từ 2.8.9 trở lên và nhớ rằng unregister không tự stop container.
- Theo dõi trạng thái, số container đang chạy, consumer group, rebalance và shutdown timeout.
- Giới hạn số container động để tránh tạo quá nhiều consumer thread, socket và kết nối broker.

Dừng và xóa container động là một quy trình lifecycle: dừng consumer, đợi shutdown hoàn tất, giải phóng tài nguyên do ứng dụng sở hữu và gỡ đăng ký khỏi nơi quản lý. Khi phân biệt đúng `pause`, `stop`, `destroy` và `unregister`, ứng dụng có thể tạo và thu hồi consumer theo nhu cầu mà không nhầm lẫn với việc xóa topic hoặc offset Kafka.

## Tài liệu tham khảo

- [Dynamically Creating Containers - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/dynamic-containers.html)
- [@KafkaListener Lifecycle Management - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html)
