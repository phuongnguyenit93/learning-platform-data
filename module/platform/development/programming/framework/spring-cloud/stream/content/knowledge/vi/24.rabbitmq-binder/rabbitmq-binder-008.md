# TTL, thời hạn queue, giới hạn độ dài và overflow

RabbitMQ có nhiều cơ chế giới hạn vòng đời và dung lượng của queue. Message TTL quyết định một message được phép nằm chờ trong queue bao lâu. Queue expiration quyết định một queue không còn được sử dụng sẽ tồn tại bao lâu trước khi broker xóa nó. Queue length limit giới hạn số message hoặc tổng dung lượng body trong backlog. Khi đạt giới hạn, overflow policy quyết định broker loại message cũ hay từ chối message mới.

Spring Cloud Stream RabbitMQ Binder cung cấp các thuộc tính để khai báo những giới hạn này khi provision queue. Cần phân biệt thuộc tính của binder với chính sách (policy) do RabbitMQ quản trị, vì cả hai đều có thể tác động đến queue. Chọn đúng loại giới hạn giúp kiểm soát backlog, tránh giữ message quá hạn, giảm nguy cơ đầy bộ nhớ/đĩa và định nghĩa rõ cách publisher nhận biết khi queue không còn chấp nhận dữ liệu.

## 1. Phân biệt message TTL và queue expiration

RabbitMQ dùng từ TTL cho hai đối tượng khác nhau:

| Cơ chế | RabbitMQ argument/policy | Ý nghĩa |
|---|---|---|
| Message TTL theo queue | `x-message-ttl` / `message-ttl` | Giới hạn thời gian một message được giữ trong queue |
| Per-message TTL | `expiration` trong AMQP message properties | Đặt thời hạn riêng cho từng message |
| Queue expiration | `x-expires` / `expires` | Xóa queue sau một khoảng thời gian queue không được sử dụng |

Message TTL không xóa queue. Queue expiration cũng không phải thời gian sống của message. Ví dụ, queue có thể tồn tại nhiều ngày nhưng chỉ giữ message tối đa năm phút; hoặc queue tạm thời có thể bị xóa sau một giờ không có consumer dù message TTL không được đặt.

Với RabbitMQ Binder, các thuộc tính consumer quan trọng là:

- `ttl`: thời gian message được giữ trong queue khi binder khai báo queue, tính bằng mili giây. Binder dùng cấu hình này để đặt message TTL cấp queue (`x-message-ttl`).
- `expires`: thời gian queue không được sử dụng trước khi broker tự xóa queue, tính bằng mili giây (`x-expires`).

Ví dụ: `ttl: 300000` có nghĩa message có thời gian sống trong queue là 5 phút. `expires: 3600000` có nghĩa queue có thể bị xóa sau một giờ không được sử dụng theo định nghĩa của RabbitMQ. Hai thuộc tính không thay thế nhau.

## 2. Message TTL theo queue

Message TTL phù hợp với dữ liệu chỉ còn ý nghĩa trong một khoảng thời gian. Ví dụ:

- Lệnh cập nhật trạng thái giao hàng chỉ còn hữu ích trong 10 phút.
- Yêu cầu làm mới dữ liệu có thể bị bỏ qua nếu đã chờ quá lâu.
- Sự kiện tạm thời về trạng thái thiết bị không cần xử lý sau một thời hạn xác định.
- Message trong queue xử lý nhanh không nên tích lũy thành backlog quá cũ.

Khai báo TTL cho queue của input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              ttl: 300000
~~~

Thuộc tính mở rộng Rabbit binder nằm dưới `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`. Giá trị `ttl` được tính bằng mili giây; ví dụ 300000 tương đương 5 phút. Queue được binder provision cho destination/group sẽ áp dụng giới hạn này cho message nằm chờ trong queue.

RabbitMQ bảo đảm message đã hết TTL sẽ không được giao cho consumer. Broker cố gắng loại bỏ message đã hết hạn tại hoặc ngay sau thời điểm hết hạn. Với classic queue, message hết hạn thường được dọn khi nó đi đến đầu queue; do đó message đã hết hạn có thể vẫn xuất hiện trong thống kê queue trong lúc còn bị chặn phía sau message chưa hết hạn. Không dùng TTL như một bộ hẹn giờ chính xác đến từng mili giây để kích hoạt tác vụ.

Nếu queue có dead-letter exchange (DLX), message hết hạn có thể được dead-letter theo cấu hình broker. Nếu không có DLX phù hợp, message hết hạn bị loại bỏ. Hãy xác định rõ dữ liệu hết hạn có thể bỏ đi hay phải chuyển sang luồng điều tra/đối soát.

## 3. Per-message TTL

Ngoài TTL chung của queue, RabbitMQ hỗ trợ expiration riêng trên từng message. Publisher đặt thuộc tính AMQP `expiration` dưới dạng chuỗi số mili giây. Khi cả queue TTL và per-message TTL cùng tồn tại, RabbitMQ áp dụng thời hạn ngắn hơn.

Ví dụ với Spring AMQP `RabbitTemplate`:

~~~java
rabbitTemplate.convertAndSend(
    "orders.exchange",
    "orders.created",
    event,
    message -> {
        message.getMessageProperties().setExpiration("60000");
        return message;
    }
);
~~~

Trong ví dụ, message có TTL riêng là 60 giây. Đây là API Spring AMQP trực tiếp; nó minh họa cách đặt AMQP message property. Nếu ứng dụng gửi qua Spring Cloud Stream Rabbit binder, hãy kiểm tra header mapping hoặc cơ chế tùy biến message converter/producer của phiên bản đang dùng trước khi giả định một header tùy ý sẽ được chuyển thành `expiration`.

Per-message TTL phù hợp khi các message trên cùng queue có thời hạn khác nhau. Tuy nhiên, với classic queue, message hết hạn nằm phía sau message chưa hết hạn có thể chưa được dọn ngay; nó sẽ không được giao cho consumer nhưng có thể vẫn chiếm tài nguyên cho đến khi broker có thể loại bỏ nó.

## 4. Queue expiration: xóa queue không được sử dụng

Thuộc tính `expires` của Rabbit binder quy định thời gian queue không được sử dụng trước khi RabbitMQ tự xóa queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        replies-in-0:
          destination: rpc.replies
          group: temporary-client
      rabbit:
        bindings:
          replies-in-0:
            consumer:
              expires: 3600000
~~~

Trong ví dụ, queue có thể hết hạn sau một giờ không được sử dụng. RabbitMQ định nghĩa queue được sử dụng khi có consumer trực tuyến; việc redeclare queue hoặc gọi `basic.get` cũng làm mới thời điểm sử dụng. Thời hạn `x-expires` phải là số nguyên dương, không phải 0.

Queue expiration hữu ích cho queue tạm thời, ví dụ reply queue của RPC hoặc queue được tạo cho một consumer ngắn hạn. Nó thường không phù hợp với queue nghiệp vụ lâu dài cần tồn tại để giữ message khi ứng dụng tạm ngừng.

Khi queue hết hạn, broker xóa queue và các message còn nằm trong queue đó. Không xem queue expiration như một cơ chế archive. Nếu message cần được lưu giữ để kiểm toán hoặc xử lý sau này, phải dùng destination bền vững, DLQ hoặc kho lưu trữ riêng.

## 5. Giới hạn số message bằng maxLength

`maxLength` đặt giới hạn số lượng message trong queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-length: 10000
~~~

Khi queue đạt giới hạn 10000 message, RabbitMQ áp dụng overflow behavior để quyết định message nào bị loại hoặc publish nào bị từ chối. Đây là giới hạn backlog của broker, không phải giới hạn tổng số message ứng dụng đã nhận trong suốt vòng đời.

Với classic queue, giới hạn độ dài chỉ tính message ở trạng thái ready (đang chờ được giao). Message đã được giao cho consumer nhưng chưa ack (unacknowledged) không được tính vào giới hạn. Quorum queue còn tính thêm message delayed, bao gồm delayed retry và message đang chờ at-least-once dead-lettering theo semantics của quorum queue.

Vì vậy, `max-length: 10000` không có nghĩa tổng số message đang tồn tại trong toàn bộ quy trình, bao gồm cả message đang được consumer xử lý, luôn nhỏ hơn 10000. Hãy quan sát riêng `messages_ready` và `messages_unacknowledged`.

## 6. Giới hạn dung lượng bằng maxLengthBytes

`maxLengthBytes` giới hạn tổng dung lượng body của các message trong queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        image-jobs-in-0:
          destination: image.jobs
          group: image-worker
      rabbit:
        bindings:
          image-jobs-in-0:
            consumer:
              max-length-bytes: 104857600
~~~

Giá trị 104857600 tương đương 100 MiB. RabbitMQ tính tổng độ dài body message; message properties và overhead giao thức không được tính vào giá trị body này. Đây là giới hạn dung lượng backlog, không phải giới hạn kích thước của một message đơn lẻ.

Có thể cấu hình đồng thời `maxLength` và `maxLengthBytes`. Khi một trong hai giới hạn chạm ngưỡng, overflow behavior được áp dụng. Ví dụ:

~~~yaml
max-length: 10000
max-length-bytes: 104857600
~~~

Queue bị giới hạn bởi số message hoặc tổng byte tùy điều kiện nào đạt trước. Nếu message có kích thước rất khác nhau, giới hạn byte thường giúp kiểm soát dung lượng tốt hơn giới hạn số lượng đơn thuần.

## 7. Chọn overflow behavior

RabbitMQ hỗ trợ các chiến lược xử lý khi queue length limit đạt ngưỡng. Rabbit binder hiện cung cấp thuộc tính `overflowBehavior`, với các giá trị phổ biến:

| Giá trị | Hành vi | Hệ quả |
|---|---|---|
| `drop-head` | Loại message cũ nhất ở đầu queue để dành chỗ cho message mới | Message cũ có thể mất khỏi luồng xử lý; nếu có DLX, việc dead-letter phụ thuộc cấu hình broker |
| `reject-publish` | Từ chối message mới được publish khi queue đầy | Publisher có thể nhận `basic.nack` nếu publisher confirms được bật và phải xử lý việc gửi thất bại |

Ví dụ chọn từ chối message mới:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-length: 10000
              overflow-behavior: reject-publish
~~~

`drop-head` phù hợp với dữ liệu dạng trạng thái mới nhất, nơi message cũ có thể bị bỏ qua khi backlog quá lớn. Không dùng chiến lược này cho lệnh thanh toán, thay đổi số dư hoặc sự kiện cần xử lý đầy đủ nếu chưa có cơ chế khôi phục.

`reject-publish` tạo áp lực ngược lên publisher. Publisher cần quan sát publisher confirm/nack và retry có kiểm soát hoặc chuyển lỗi sang quy trình khác. Không giả định giá trị boolean trả về từ một lời gọi gửi ở tầng ứng dụng luôn phản ánh chính xác mọi trường hợp queue overflow; hãy cấu hình và kiểm thử cơ chế publisher confirm/error của binder.

RabbitMQ còn có biến thể `reject-publish-dlx` ở một số phiên bản broker, trong đó message publish bị từ chối được dead-letter. Tuy nhiên, thuộc tính `overflowBehavior` của Rabbit binder hiện tài liệu hóa `drop-head` và `reject-publish`; không đặt `reject-publish-dlx` vào cấu hình binder nếu phiên bản binder không hỗ trợ giá trị đó. Nếu cần hành vi nâng cao, quản lý queue bằng RabbitMQ policy và xác minh tương thích broker.

## 8. Kết hợp TTL, expires và queue limits

Một queue có thể dùng đồng thời các giới hạn:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              ttl: 300000
              expires: 86400000
              max-length: 10000
              max-length-bytes: 104857600
              overflow-behavior: reject-publish
~~~

Ý nghĩa:

- Message được giữ trong queue tối đa 5 phút nếu chưa được giao.
- Queue có thể bị xóa sau 24 giờ không được sử dụng.
- Backlog bị giới hạn ở 10000 message hoặc 100 MiB body.
- Khi đạt giới hạn, broker từ chối message publish mới thay vì loại message cũ.

Không nên đặt `expires` ngắn cho queue nghiệp vụ chỉ vì muốn dọn message cũ. Queue bị xóa sẽ làm mất cả queue và backlog của nó. Nếu muốn message hết hạn mà queue vẫn tồn tại, dùng message TTL. Nếu muốn queue tạm thời biến mất khi không còn consumer, dùng queue expiration.

## 9. Giới hạn riêng cho DLQ

DLQ cũng là queue và có thể tích lũy message lỗi. Rabbit binder có các thuộc tính riêng để kiểm soát vòng đời và dung lượng của DLQ:

- `dlqTtl`: message TTL áp dụng cho DLQ.
- `dlqExpires`: thời gian queue DLQ không được sử dụng trước khi bị xóa.
- `dlqMaxLength`: số message tối đa trong DLQ.
- `dlqMaxLengthBytes`: tổng dung lượng body tối đa trong DLQ.
- `dlqOverflowBehavior`: cách xử lý overflow của DLQ.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              dlq-ttl: 604800000
              dlq-expires: 2592000000
              dlq-max-length: 5000
              dlq-max-length-bytes: 52428800
              dlq-overflow-behavior: reject-publish
~~~

Trong ví dụ, message trong DLQ có TTL 7 ngày; queue DLQ có thể hết hạn sau 30 ngày không được sử dụng; DLQ có giới hạn 5000 message hoặc 50 MiB. Các giới hạn này cần phù hợp với thời gian điều tra và quy trình replay. Nếu DLQ bị xóa hoặc overflow theo kiểu drop-head, message lỗi có thể mất trước khi được xử lý.

`auto-bind-dlq` yêu cầu binder tạo DLQ và liên kết dead-letter exchange. `republish-to-dlq` điều khiển binder republish message lỗi với header chẩn đoán bổ sung như exception message và stack trace. Đây là xử lý lỗi consumer sau retry; message hết TTL hoặc bị overflow có thể đi theo dead-letter behavior của broker nếu queue có DLX. Hãy phân biệt dead-letter do consumer reject với dead-letter do TTL/overflow.

## 10. Binder properties và RabbitMQ policies

Rabbit binder có thể khai báo queue arguments khi tự provision queue. RabbitMQ cũng hỗ trợ policies để quản trị tập trung các thuộc tính như message TTL, queue expiration, max-length, max-length-bytes và overflow.

Có hai cách quản lý thường gặp:

| Cách | Khi phù hợp |
|---|---|
| Rabbit binder properties | Ứng dụng sở hữu việc provision queue và cấu hình cần đi cùng binding |
| RabbitMQ policies | Đội vận hành quản trị giới hạn tập trung, cần thay đổi policy mà không phát hành lại ứng dụng |

Nếu queue đã tồn tại với arguments khác với những gì binder muốn khai báo, RabbitMQ có thể từ chối redeclare bằng lỗi `PRECONDITION_FAILED` do queue declaration không tương thích. Trước khi thay đổi TTL, expires, max-length hoặc queue type, hãy kiểm tra arguments hiện tại và chọn một nguồn cấu hình nhất quán. Không xóa queue production chỉ để giải quyết xung đột cấu hình nếu chưa đánh giá backlog và kế hoạch chuyển dữ liệu.

Policies giúp thay đổi một số giới hạn động mà không cần xóa queue. Tuy nhiên, cần xem quy tắc ưu tiên giữa client-provided arguments, user policies và operator policies của phiên bản RabbitMQ đang dùng. Xác nhận giá trị hiệu lực trong Management UI hoặc `rabbitmqctl list_queues` sau khi áp dụng.

## 11. Chọn giới hạn theo đặc tính nghiệp vụ

Không có một bộ giá trị TTL/length phù hợp cho mọi queue. Hãy xác định:

- Message có còn giá trị sau bao lâu?
- Backlog tối đa mà hệ thống có thể xử lý trước khi dữ liệu trở nên lỗi thời?
- Một message trung bình và message lớn nhất có kích thước bao nhiêu?
- Khi queue đầy, mất message cũ hay từ chối message mới gây thiệt hại ít hơn?
- Có DLQ và quy trình replay để phục hồi message bị từ chối/hết hạn không?
- Consumer có thể offline trong bao lâu trước khi queue cần được giữ lại?

Ví dụ:

| Loại queue | TTL gợi ý theo nghiệp vụ | Overflow thường cân nhắc |
|---|---|---|
| Trạng thái cảm biến mới nhất | Ngắn; dữ liệu cũ nhanh mất giá trị | `drop-head` nếu chấp nhận bỏ trạng thái cũ |
| Lệnh thanh toán | Không đặt TTL tùy tiện; thời hạn do nghiệp vụ quyết định | `reject-publish` để publisher biết queue đã đầy |
| Job tạo thumbnail | TTL vừa phải theo thời hạn xử lý | `reject-publish` hoặc DLQ có giới hạn |
| Reply queue tạm thời | Queue `expires` để dọn tài nguyên khi client biến mất | Không dùng làm kho lưu trữ |
| DLQ điều tra | TTL dài đủ cho vận hành và replay | `reject-publish` để tránh âm thầm loại message lỗi |

Các giá trị trong bảng chỉ là cách lựa chọn theo đặc tính nghiệp vụ, không phải giá trị mặc định bắt buộc. Với dữ liệu tài chính hoặc audit, cần có chính sách lưu giữ rõ ràng và không dựa vào queue TTL để thay thế lưu trữ lâu dài.

## 12. Theo dõi queue limits trong production

Các số liệu cần quan sát:

- `messages_ready`: số message đang chờ giao.
- `messages_unacknowledged`: số message đã giao nhưng chưa được ack.
- `message_bytes_ready`: tổng dung lượng body của message ready.
- Tốc độ publish và consume.
- Số publisher nack/confirm thất bại khi queue overflow.
- Số message expired hoặc dead-lettered.
- Độ tuổi của message cũ nhất trong backlog.
- Số lượng queue tạm thời và queue đã hết hạn.

RabbitMQ Management UI và `rabbitmqctl list_queues` giúp xem trạng thái queue. Ví dụ:

~~~bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged message_bytes_ready consumers
~~~

Nếu `messages_ready` tăng liên tục, consumer có thể chậm hơn publisher hoặc bị lỗi. Nếu `messages_unacknowledged` tăng, consumer có thể đang giữ nhiều delivery hoặc xử lý quá lâu. Tăng maxLength chỉ kéo dài thời gian trước khi queue đầy; nó không sửa được throughput bottleneck.

Khi `reject-publish` được dùng, bật và xử lý publisher confirms để ứng dụng biết broker đã nhận hay từ chối publish. Khi `drop-head` được dùng, theo dõi số message bị loại/dead-letter để nhận biết dữ liệu có thể bị mất do giới hạn.

## 13. Kiểm thử TTL, queue expiration và overflow

Không chỉ kiểm tra YAML khởi động thành công. Hãy kiểm thử hành vi thực tế với RabbitMQ:

1. Publish một message vào queue có TTL ngắn, không có consumer; xác nhận message hết hạn và không được giao.
2. Lặp lại với DLX đã cấu hình; xác nhận message hết hạn đi đến dead-letter destination theo chính sách.
3. Đặt `expires` cho queue tạm thời; dừng consumer, không redeclare hoặc gọi basic.get trong khoảng thời gian cấu hình; xác nhận queue bị xóa.
4. Tạo queue có `max-length` nhỏ rồi publish vượt ngưỡng; kiểm tra `drop-head` loại message cũ hoặc `reject-publish` từ chối message mới.
5. Kiểm tra `max-length-bytes` với body có kích thước khác nhau.
6. Xác nhận message unacknowledged không bị tính như message ready trong classic queue.
7. Kiểm tra queue đã tồn tại với arguments khác và xác nhận quy trình triển khai xử lý `PRECONDITION_FAILED`.
8. Kiểm tra DLQ có TTL, expires và giới hạn riêng; xác nhận message lỗi còn đủ thời gian để điều tra.
9. Bật publisher confirms và mô phỏng queue đầy để xác nhận publisher nhận được nack và có chính sách retry/backpressure.
10. Kiểm tra restart broker/consumer và xác nhận durable queue, persistent message cùng retention policy phù hợp với yêu cầu.

Test Binder có thể kiểm tra cấu hình binding và logic function, nhưng không mô phỏng đầy đủ TTL, queue deletion, dead lettering và overflow của RabbitMQ. Dùng RabbitMQ broker thật hoặc Testcontainers để xác minh những hành vi này.

## 14. Checklist cấu hình

- [ ] Đã phân biệt message TTL (`ttl`) với queue expiration (`expires`).
- [ ] Đã chọn TTL theo thời gian message còn có giá trị nghiệp vụ.
- [ ] Đã hiểu per-message expiration và quan hệ với queue TTL.
- [ ] Đã đặt `max-length` và/hoặc `max-length-bytes` theo năng lực xử lý.
- [ ] Đã chọn `overflow-behavior` phù hợp: `drop-head` hay `reject-publish`.
- [ ] Nếu từ chối publish, publisher confirms/nack được quan sát và xử lý.
- [ ] Đã đánh giá message hết hạn có cần dead-letter hay có thể loại bỏ.
- [ ] Đã đặt giới hạn riêng cho DLQ nếu DLQ được provision.
- [ ] Đã xác định queue do binder hay RabbitMQ policy quản trị.
- [ ] Đã kiểm tra queue arguments hiện có để tránh `PRECONDITION_FAILED`.
- [ ] Đã theo dõi ready, unacknowledged, byte backlog và tuổi message.
- [ ] Đã integration test TTL, queue expiration, overflow và DLQ với RabbitMQ thật.

TTL, queue expiration và queue length limits giải quyết ba vấn đề khác nhau: message cũ có thể hết hạn, queue tạm thời có thể được dọn khi không còn dùng, và backlog có thể bị giới hạn theo số lượng hoặc dung lượng. Trong Spring Cloud Stream Rabbit binder, hãy cấu hình `ttl`, `expires`, `max-length`, `max-length-bytes` và `overflow-behavior` theo đúng semantics của broker; đồng thời thiết kế DLQ, publisher confirms và giám sát để việc hết hạn hoặc queue đầy trở thành hành vi có thể dự đoán và phục hồi.

## Tài liệu tham khảo

- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl)
- [RabbitMQ — Queue Length Limit](https://www.rabbitmq.com/docs/maxlength)
- [RabbitMQ — Configurable Limits](https://www.rabbitmq.com/docs/limits)
