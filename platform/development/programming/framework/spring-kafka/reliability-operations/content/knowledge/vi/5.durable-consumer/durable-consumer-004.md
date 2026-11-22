# session.timeout.ms và heartbeat

Trong Kafka consumer group, heartbeat giúp coordinator biết consumer nào vẫn còn kết nối và tham gia group. Tham số **session.timeout.ms** xác định khoảng thời gian coordinator chờ heartbeat hợp lệ trước khi xem consumer là đã mất phiên. Khi phiên hết hạn, coordinator có thể bắt đầu rebalance và phân phối lại partition cho các consumer còn hoạt động.

Trong ứng dụng Spring Kafka, các tham số này ảnh hưởng trực tiếp đến thời gian phát hiện consumer mất kết nối, mức độ nhạy với gián đoạn ngắn và tần suất rebalance. Cấu hình quá thấp có thể khiến một consumer khỏe mạnh bị loại khỏi group khi mạng hoặc JVM tạm thời chậm. Cấu hình quá cao làm hệ thống mất nhiều thời gian hơn để phát hiện một consumer thực sự đã chết. Cần hiểu rõ heartbeat, session timeout và giới hạn xử lý **max.poll.interval.ms** trước khi thay đổi.

## 1. Heartbeat trong consumer group hoạt động như thế nào?

Consumer group coordinator theo dõi các thành viên của group. Một consumer gửi heartbeat định kỳ để thông báo rằng nó vẫn còn tham gia group. Coordinator nhận heartbeat và duy trì trạng thái thành viên trong thời gian phiên còn hiệu lực.

Luồng khái quát:

~~~text
Consumer A                  Group Coordinator
    |                              |
    |------ JoinGroup ------------>|
    |<----- SyncGroup --------------|
    |                              |
    |------ Heartbeat ------------>|
    |<----- Heartbeat response -----|
    |                              |
    |------ Heartbeat ------------>|
    |<----- Heartbeat response -----|
    |                              |
    |     (mất kết nối / ngừng gửi) |
    |                              |
    |       session timeout        |
    |                              |
    |<------ rebalance ------------|
    |                              |
~~~

Sau khi tham gia group và nhận assignment, consumer tiếp tục gửi heartbeat theo chu kỳ. Nếu coordinator không nhận được heartbeat trong khoảng session timeout, nó có thể đánh dấu member là đã rời group. Các partition do member đó sở hữu sẽ được phân phối lại theo giao thức rebalance.

Heartbeat là tín hiệu về tình trạng tham gia group, không phải bằng chứng rằng nghiệp vụ đang xử lý record thành công. Consumer có thể gửi heartbeat đều nhưng listener xử lý chậm, downstream bị treo hoặc backlog tăng. Vì vậy, cần theo dõi cả heartbeat/rebalance và consumer lag, thời gian xử lý record.

## 2. session.timeout.ms là gì?

**session.timeout.ms** là khoảng thời gian tối đa coordinator chờ heartbeat từ một consumer trước khi xem consumer đó không còn hoạt động trong group. Khi timeout hết hạn, coordinator có thể loại member và khởi động rebalance.

Tham số này tạo ra một đánh đổi:

- Giá trị nhỏ giúp phát hiện consumer chết nhanh hơn và giảm thời gian partition bị giữ bởi member không còn hoạt động.
- Giá trị lớn cho consumer thêm thời gian vượt qua gián đoạn mạng, pause JVM hoặc tải hệ thống ngắn hạn.
- Giá trị quá nhỏ có thể gây false positive: consumer còn sống nhưng heartbeat đến coordinator trễ.
- Giá trị quá lớn có thể kéo dài thời gian phát hiện lỗi và thời gian khôi phục thông lượng sau khi consumer thực sự chết.

Với classic consumer group protocol, client gửi giá trị session.timeout.ms trong quá trình tham gia group. Broker giới hạn giá trị này bằng các cấu hình như **group.min.session.timeout.ms** và **group.max.session.timeout.ms**. Nếu client đặt giá trị nằm ngoài giới hạn broker, việc tham gia group có thể thất bại.

Không nên chọn timeout chỉ dựa trên mong muốn “rebalance càng nhanh càng tốt”. Hãy đo độ trễ mạng, thời gian pause JVM, tải CPU, tình trạng coordinator và SLA phục hồi để chọn ngưỡng có biên an toàn.

## 3. heartbeat.interval.ms điều khiển chu kỳ heartbeat

Với classic consumer group protocol, **heartbeat.interval.ms** xác định tần suất consumer gửi heartbeat đến coordinator. Heartbeat thường được gửi thường xuyên hơn session timeout để có cơ hội phát hiện và xử lý lỗi trước khi phiên hết hạn.

Một quy tắc cấu hình thường dùng là:

~~~text
heartbeat.interval.ms <= session.timeout.ms / 3
~~~

Ví dụ, nếu session.timeout.ms là 15 giây, có thể bắt đầu thử nghiệm với heartbeat.interval.ms khoảng 5 giây. Đây là điểm khởi đầu phổ biến, không phải công thức bắt buộc cho mọi workload. Cần cân nhắc độ trễ mạng, tải coordinator, số consumer trong group và yêu cầu phát hiện lỗi.

Heartbeat quá thường xuyên làm tăng số request điều phối và tải cho broker/coordinator, nhất là khi có rất nhiều consumer. Heartbeat quá thưa khiến consumer có ít cơ hội chứng minh mình còn hoạt động trước khi session timeout.

### 3.1. Ví dụ cấu hình Spring Boot

Với classic group protocol, có thể cấu hình consumer trong Spring Boot như sau:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[session.timeout.ms]": 15000
        "[heartbeat.interval.ms]": 5000
        "[max.poll.interval.ms]": 300000
~~~

Các giá trị trên chỉ là ví dụ để minh họa quan hệ giữa ba tham số. Cần xác nhận broker cho phép session timeout 15 giây và điều chỉnh theo phiên bản Kafka, hạ tầng cùng đặc tính xử lý. Không sao chép nguyên cấu hình này vào production nếu chưa đo thời gian xử lý và hành vi khi mạng gián đoạn.

Có thể khai báo qua ConsumerFactory nếu ứng dụng tự cấu hình consumer properties:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 15_000);
props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 5_000);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);

DefaultKafkaConsumerFactory<String, OrderEvent> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props, keyDeserializer, valueDeserializer);
~~~

Nếu Spring Boot đã tạo ConsumerFactory từ cấu hình property, tránh tạo một factory thứ hai chỉ để đặt timeout nếu không có yêu cầu riêng. Giữ cấu hình consumer tập trung giúp các instance có hành vi nhất quán và dễ vận hành.

## 4. Phân biệt session timeout và max.poll.interval.ms

Đây là điểm quan trọng nhất khi xử lý consumer bị rebalance. **session.timeout.ms** và **max.poll.interval.ms** bảo vệ hai điều kiện khác nhau:

| Tham số | Theo dõi điều gì? | Khi vượt giới hạn |
|---|---|---|
| session.timeout.ms | Coordinator không nhận được heartbeat hợp lệ trong bao lâu | Member có thể bị xem là mất phiên và bị loại khỏi group |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa hai lần gọi poll() của ứng dụng | Consumer bị xem là không tiếp tục tiến triển trong vòng poll; group có thể rebalance |

Heartbeat chứng minh consumer vẫn duy trì kết nối group. poll() chứng minh ứng dụng tiếp tục lấy và tiến triển với dữ liệu. Hai việc này có liên quan nhưng không giống nhau.

Kafka consumer client có thể duy trì heartbeat ở thread nền trong khi ứng dụng xử lý record được trả về từ lần poll trước. Do đó, listener xử lý lâu có thể vẫn gửi heartbeat bình thường nhưng vượt max.poll.interval.ms. Khi đó consumer bị xem là không gọi poll đúng hạn và có thể mất assignment.

Ngược lại, nếu mạng đến coordinator bị gián đoạn hoặc consumer process bị dừng, heartbeat không đến được coordinator và session timeout có thể hết hạn dù max.poll.interval.ms chưa bị vượt.

### 4.1. Ví dụ xử lý chậm

Giả sử consumer poll 100 record và listener xử lý mỗi record mất trung bình 4 giây. Thời gian xử lý batch có thể xấp xỉ 400 giây, chưa tính overhead và các record chậm bất thường. Nếu max.poll.interval.ms chỉ là 300.000 ms (5 phút), consumer có nguy cơ vượt poll interval dù heartbeat thread vẫn hoạt động.

Hướng xử lý:

- Giảm max.poll.records để giới hạn thời gian xử lý mỗi batch.
- Tối ưu logic listener và các lời gọi downstream.
- Tăng max.poll.interval.ms nếu SLA và thiết kế thực sự cho phép thời gian xử lý dài hơn.
- Chuyển công việc dài sang kiến trúc worker có kiểm soát, nhưng chỉ ack sau khi công việc đã được lưu bền vững hoặc đã được chuyển giao an toàn.

Không tăng session.timeout.ms để chữa lỗi vượt max.poll.interval.ms. Hai tham số xử lý hai nguyên nhân khác nhau.

## 5. Heartbeat và vòng đời listener trong Spring Kafka

Spring Kafka chạy listener container để quản lý Kafka consumer, poll, gọi listener, commit offset và phối hợp rebalance. Mỗi consumer trong container tham gia group và có heartbeat theo cơ chế của Kafka client.

Với listener xử lý từng record:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Listener thường được gọi trong luồng xử lý của container. Nếu phương thức mất nhiều thời gian, cần xem xét tổng thời gian xử lý các record được trả về trong một poll và so sánh với max.poll.interval.ms. Heartbeat thread không biến một listener bị treo thành một consumer đang tiến triển bình thường.

Với batch listener, tổng thời gian xử lý batch có thể lớn hơn nhiều so với thời gian xử lý một record. Cần chọn max.poll.records, concurrency và poll interval theo thời gian xử lý ở phân vị cao, không chỉ theo trung bình.

### 5.1. Container concurrency và số consumer

Spring Kafka cho phép đặt concurrency cho listener container:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Concurrency tạo nhiều consumer trong cùng group từ một ứng dụng listener container. Mỗi consumer có vòng đời heartbeat và assignment riêng. Nếu số consumer đang hoạt động vượt số partition, một số consumer sẽ không được gán partition và không tăng thông lượng xử lý.

Khi tăng concurrency, cần đánh giá:

- Số partition của các topic được subscribe.
- Năng lực CPU, memory và downstream.
- Tổng số consumer trên tất cả instance ứng dụng.
- Tải heartbeat và group coordination.
- Thời gian rebalance khi triển khai hoặc autoscaling.

Tăng concurrency không phải cách khắc phục trực tiếp cho session timeout. Nếu nguyên nhân là coordinator/network hoặc JVM pause, thêm consumer có thể làm tải group coordinator và broker tăng thêm.

## 6. Điều gì xảy ra khi heartbeat bị mất?

Một số nguyên nhân phổ biến làm heartbeat không đến coordinator đúng hạn:

- Process consumer bị crash hoặc container bị kill.
- Máy chủ hoặc pod bị mất mạng đến broker.
- Broker coordinator bị quá tải, restart hoặc mất khả năng xử lý request.
- JVM stop-the-world pause kéo dài hoặc CPU bị throttling mạnh.
- DNS, TLS, authentication hoặc network route gặp sự cố.
- Consumer bị block hoặc dừng trong quá trình khởi tạo/đóng client.
- Cấu hình heartbeat/session timeout quá chặt so với điều kiện thực tế.

Khi coordinator xác định session đã hết hạn, member có thể bị loại khỏi group. Các consumer còn lại nhận thông báo rebalance và có thể phải revoke rồi nhận lại partition. Trong thời gian rebalance, một phần xử lý có thể tạm dừng. Record chưa được commit có thể được giao lại, vì vậy consumer nghiệp vụ phải idempotent.

Một lần rebalance không nhất thiết đồng nghĩa với mất dữ liệu. Tuy nhiên, rebalance liên tục có thể làm giảm throughput, tăng lag và tăng số lần xử lý lặp. Cần xác định nguyên nhân trước khi tăng timeout hoặc thay đổi chiến lược assignment.

## 7. Static membership và group.instance.id

Kafka hỗ trợ static membership thông qua **group.instance.id**. Một consumer có định danh thành viên ổn định có thể rời đi và quay lại trong thời gian session còn hiệu lực mà không nhất thiết gây rebalance ngay như dynamic membership. Điều này hữu ích khi ứng dụng triển khai rolling restart hoặc pod có danh tính ổn định.

Static membership thay đổi hành vi phát hiện member rời group:

- Khi instance khởi động lại nhanh với cùng định danh, nó có thể lấy lại vị trí thành viên và giảm rebalance không cần thiết.
- Nếu instance thực sự mất lâu, coordinator vẫn phải phát hiện session hết hạn trước khi giải phóng assignment.
- group.instance.id phải duy nhất trong một group. Hai consumer cùng dùng một định danh có thể gây fencing hoặc lỗi thành viên.
- Nếu dùng Spring Kafka concurrency, mỗi consumer cần định danh riêng; kiểm tra cách phiên bản Spring Kafka đang dùng tạo suffix cho các child consumer.

Static membership không thay thế heartbeat và không làm consumer được phép ngừng poll vô hạn. Nó chủ yếu thay đổi cách coordinator xử lý thành viên có định danh ổn định khi rời group và quay lại.

## 8. Classic protocol và consumer group protocol mới

Các tham số session.timeout.ms và heartbeat.interval.ms được cấu hình ở client trong classic consumer group protocol. Kafka cũng có consumer group protocol mới, được chọn bằng group.protocol=consumer ở các phiên bản client/broker hỗ trợ.

Khi sử dụng protocol mới:

- Một số thiết lập heartbeat và session timeout được broker quản lý thay vì client.
- heartbeat.interval.ms và session.timeout.ms phía client không còn là nơi điều khiển chu kỳ và timeout theo cách classic protocol sử dụng.
- Các cấu hình broker như group.consumer.heartbeat.interval.ms và group.consumer.session.timeout.ms điều khiển các giá trị tương ứng.
- Cần kiểm tra khả năng tương thích của broker, Kafka client và Spring Kafka trước khi chuyển protocol.

Không trộn hướng dẫn classic protocol với consumer protocol mới. Nếu ứng dụng đang dùng classic protocol, cấu hình hai tham số ở client như ví dụ trước. Nếu bật group.protocol=consumer, hãy đọc tài liệu phiên bản Kafka đang triển khai và điều chỉnh ở broker theo cơ chế của protocol mới.

## 9. Chọn timeout theo tải và môi trường

Không có một cặp timeout đúng cho mọi ứng dụng. Một consumer xử lý event nhẹ trên mạng nội bộ có thể dùng session timeout ngắn hơn một consumer chạy qua mạng liên vùng hoặc môi trường có pause JVM dài hơn.

Khi lựa chọn:

1. Đo thời gian heartbeat response và độ trễ mạng đến coordinator.
2. Đo JVM pause, CPU throttling và thời gian scheduler không cấp CPU.
3. Xác định thời gian phát hiện consumer chết mà nghiệp vụ chấp nhận được.
4. Kiểm tra giới hạn group.min.session.timeout.ms và group.max.session.timeout.ms của broker khi dùng classic protocol.
5. Đặt heartbeat interval đủ nhỏ so với session timeout theo khuyến nghị của protocol.
6. Kiểm tra max.poll.interval.ms độc lập với thời gian xử lý batch.
7. Thử nghiệm consumer restart, broker restart và network interruption trong môi trường staging.

Một bộ giá trị minh họa cho classic protocol có thể là:

| Tham số | Giá trị ví dụ | Ý nghĩa |
|---|---:|---|
| session.timeout.ms | 15.000 ms | Coordinator phát hiện member mất phiên sau khoảng 15 giây không có heartbeat hợp lệ |
| heartbeat.interval.ms | 5.000 ms | Consumer gửi heartbeat khoảng mỗi 5 giây |
| max.poll.interval.ms | 300.000 ms | Ứng dụng phải tiếp tục poll trong giới hạn 5 phút |

Đây không phải cấu hình chuẩn production. Với consumer có thời gian xử lý batch dài, max.poll.interval.ms có thể cần cao hơn; với yêu cầu phục hồi nhanh, session timeout có thể cần thấp hơn nếu hạ tầng đáp ứng. Broker cũng có thể từ chối session timeout nằm ngoài giới hạn cho phép.

## 10. Metrics để theo dõi heartbeat và rebalance

Để biết consumer có duy trì membership ổn định hay không, cần theo dõi metrics của Kafka consumer client và Spring Kafka listener container.

Một số metric hữu ích (tên chính xác và tag phụ thuộc phiên bản Kafka client):

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| heartbeat-rate | Tốc độ heartbeat | Giảm hoặc ngừng bất thường khi consumer vẫn được kỳ vọng hoạt động |
| heartbeat-total | Tổng số heartbeat | Kiểm tra hoạt động heartbeat trong một khoảng thời gian |
| heartbeat-response-time-max | Thời gian phản hồi heartbeat lớn nhất | Tăng có thể cho thấy coordinator hoặc network chậm |
| last-heartbeat-seconds-ago | Số giây từ heartbeat gần nhất | Giá trị tăng bất thường cần điều tra |
| rebalance-rate / rebalance-total | Tốc độ và tổng số lần rebalance | Tăng liên tục có thể chỉ ra group instability |
| rebalance-latency-avg / rebalance-latency-max | Thời gian hoàn tất rebalance | Rebalance kéo dài làm giảm thời gian xử lý hữu ích |
| assigned-partitions | Số partition được gán cho consumer | Xác định phân bố assignment và consumer không có partition |
| records-lag-max | Lag lớn nhất theo record | Phát hiện consumer không theo kịp producer |
| poll-idle-ratio-avg | Tỷ lệ thời gian consumer không bận xử lý record | Giúp hiểu consumer đang nhàn hay liên tục bận |

Không nên chỉ đặt alert khi heartbeat-rate bằng 0. Một consumer có thể vẫn gửi heartbeat nhưng xử lý record quá chậm. Kết hợp heartbeat metrics với rebalance rate, lag, poll interval, listener duration và lỗi downstream.

Các dashboard nên phân biệt group, client, topic và partition bằng các tag ổn định. Tránh dùng member id hoặc client id động làm nhãn không giới hạn nếu chúng tạo cardinality lớn sau mỗi lần triển khai.

## 11. Chẩn đoán lỗi thường gặp

### 11.1. Consumer liên tục bị loại khỏi group

Kiểm tra:

1. Log consumer có thông báo session timeout hoặc heartbeat failure không?
2. heartbeat-response-time-max và last-heartbeat-seconds-ago có tăng trước rebalance không?
3. Broker coordinator có restart, quá tải hoặc mất kết nối không?
4. JVM có GC pause dài, CPU throttling hoặc container bị thiếu tài nguyên không?
5. session.timeout.ms có nằm trong giới hạn broker và đủ biên an toàn không?
6. Có nhiều consumer khởi động/dừng cùng lúc do autoscaling hoặc health check không?

Nếu heartbeat không đến coordinator, tập trung kiểm tra network, broker, JVM và timeout. Chỉ tăng max.poll.interval.ms sẽ không sửa lỗi heartbeat bị mất.

### 11.2. Heartbeat vẫn đều nhưng rebalance do xử lý chậm

Nếu heartbeat metrics bình thường nhưng consumer vẫn rời group, hãy kiểm tra max.poll.interval.ms. Đo thời gian xử lý một poll batch ở p95/p99, số record mỗi poll, downstream latency và các đoạn code block.

Giảm max.poll.records, tối ưu listener hoặc tăng poll interval có kiểm soát. Nếu listener thực hiện công việc bất đồng bộ, bảo đảm record chưa bị ack trước khi công việc được lưu bền vững hoặc chuyển giao an toàn.

### 11.3. Rebalance tăng sau khi triển khai

Rolling deployment có thể làm consumer rời group và tham gia lại. Nếu tất cả instance restart cùng lúc, group có thể trải qua nhiều đợt rebalance và lag tăng. Kiểm tra:

- Chiến lược rollout và số instance restart đồng thời.
- Graceful shutdown của listener container.
- Static membership nếu ứng dụng có identity ổn định và phù hợp.
- Thời gian khởi động, kết nối broker và hoàn tất assignment.
- Số partition và số consumer trong group.

Không bật static membership một cách máy móc. Nếu ID không duy nhất hoặc instance bị mất lâu, việc giữ membership có thể kéo dài thời gian assignment bị giữ lại.

### 11.4. Heartbeat response chậm

Kiểm tra network latency đến broker coordinator, broker request queue, CPU/disk pressure và thay đổi topology. Nếu nhiều consumer group cùng bị ảnh hưởng, khả năng cao vấn đề nằm ở broker hoặc hạ tầng mạng chung. Nếu chỉ một ứng dụng bị ảnh hưởng, xem tài nguyên pod, DNS, TLS và cấu hình client của ứng dụng đó.

## 12. Runbook khi consumer mất heartbeat

Khi alert cho thấy heartbeat thất bại hoặc rebalance tăng bất thường:

1. Xác định group, consumer instance, topic và partition bị ảnh hưởng.
2. Kiểm tra log để phân biệt session timeout với max.poll.interval.ms.
3. Đối chiếu heartbeat response time, lần heartbeat gần nhất, rebalance latency và consumer lag.
4. Kiểm tra trạng thái broker coordinator, network, DNS, TLS và tài nguyên JVM/container.
5. Nếu lỗi do listener chậm, đo thời gian batch và downstream; điều chỉnh poll interval hoặc batch size theo kết quả.
6. Nếu lỗi do hạ tầng, khôi phục network/broker hoặc tài nguyên trước khi thay timeout.
7. Sau khi group ổn định, theo dõi lag đến khi bắt kịp và kiểm tra duplicate delivery ở nghiệp vụ.
8. Ghi nhận nguyên nhân và cập nhật alert/runbook nếu ngưỡng hiện tại tạo false positive.

Trong lúc sự cố, không liên tục restart tất cả consumer để “thử lại”. Hành động đó có thể tạo thêm rebalance, tăng tải coordinator và làm tình trạng lag nghiêm trọng hơn.

## 13. Kiểm thử heartbeat và session timeout

Kiểm thử nên mô phỏng cả lỗi kết nối lẫn lỗi tiến triển xử lý:

- Dừng một consumer process đột ngột và đo thời gian partition được phân phối lại.
- Chặn network giữa consumer và broker coordinator trong môi trường test.
- Tạo JVM pause hoặc CPU throttling có kiểm soát để quan sát heartbeat.
- Làm listener xử lý lâu hơn max.poll.interval.ms để phân biệt poll timeout với session timeout.
- Restart broker đang giữ coordinator và quan sát group recovery.
- Rolling restart consumer với và không có static membership để so sánh rebalance.
- Xác nhận record chưa commit được giao lại và không tạo duplicate business effect.

Ghi nhận thời gian từ khi lỗi bắt đầu đến khi coordinator phát hiện, đến khi rebalance hoàn tất và đến khi consumer group bắt kịp backlog. Ba khoảng thời gian này khác nhau và đều có thể ảnh hưởng SLA phục hồi.

## 14. Checklist cấu hình production

### Heartbeat và session

- [ ] Đã xác định consumer đang dùng classic hay consumer group protocol mới.
- [ ] Với classic protocol, session.timeout.ms nằm trong giới hạn broker.
- [ ] heartbeat.interval.ms được đặt phù hợp so với session timeout.
- [ ] Timeout có biên an toàn dựa trên network latency, JVM pause và tải thực tế.
- [ ] Không dùng session timeout để xử lý vấn đề vượt max.poll.interval.ms.

### Listener và poll

- [ ] Thời gian xử lý poll batch nằm trong giới hạn max.poll.interval.ms.
- [ ] max.poll.records phù hợp với thời gian xử lý và năng lực downstream.
- [ ] Consumer không ack trước khi tác động nghiệp vụ bền vững.
- [ ] Consumer idempotent để chịu được record được giao lại.
- [ ] Concurrency phù hợp với số partition và tài nguyên ứng dụng.

### Quan sát và phục hồi

- [ ] Có dashboard heartbeat, heartbeat response, rebalance và consumer lag.
- [ ] Có log phân biệt session timeout với poll interval timeout.
- [ ] Có alert cho rebalance bất thường và lag vượt SLA.
- [ ] Runbook xác định cách kiểm tra coordinator, network và JVM.
- [ ] Đã diễn tập consumer crash, network interruption và rolling restart.

## Kết luận

session.timeout.ms đặt giới hạn thời gian coordinator chờ heartbeat trước khi xem consumer mất phiên; heartbeat.interval.ms điều khiển chu kỳ heartbeat trong classic group protocol. Hai tham số này giúp phát hiện member mất kết nối, còn max.poll.interval.ms kiểm soát việc ứng dụng có tiếp tục poll và tiến triển xử lý hay không. Trong Spring Kafka, cần cấu hình chúng theo phiên bản protocol, broker bounds, thời gian xử lý listener và điều kiện hạ tầng. Theo dõi heartbeat, rebalance, lag và thời gian xử lý cùng nhau sẽ giúp phân biệt lỗi kết nối với consumer xử lý chậm, giảm rebalance không cần thiết và phục hồi group có kiểm soát.
