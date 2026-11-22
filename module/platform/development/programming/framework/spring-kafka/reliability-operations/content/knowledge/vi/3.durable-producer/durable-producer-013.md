# Producer exception và cách phân loại

Producer exception là lỗi phát sinh khi ứng dụng chuẩn bị, gửi, chờ broker xác nhận hoặc quản lý trạng thái gửi record lên Kafka. Trong mô hình producer bền vững, cách xử lý lỗi quyết định record được retry, bị từ chối, có thể đã được ghi nhưng chưa nhận được xác nhận, hay cần dừng producer để khôi phục trạng thái.

Không phải mọi exception đều có cùng ý nghĩa. Một lỗi serialization xảy ra trước khi record được gửi cần sửa dữ liệu hoặc serializer. Một lỗi mất kết nối có thể được Kafka client tự retry. Một timeout sau khi gửi request có thể để lại kết quả chưa rõ ràng. Một lỗi fencing trong transaction có thể cho biết producer hiện tại đã mất quyền sở hữu transactional ID và không được tiếp tục dùng transaction đó.

Phân loại đúng exception giúp ứng dụng chọn hành động tương ứng: sửa dữ liệu, retry có giới hạn, chờ hệ thống phục hồi, chuyển sang luồng xử lý lỗi, hoặc tạo lại producer/transaction. Retry tất cả exception theo cùng một cách thường làm sự cố kéo dài và có thể tạo duplicate nghiệp vụ.

## 1. Vòng đời gửi record và nơi exception xuất hiện

Một lần gửi qua Kafka producer có thể phát sinh lỗi ở nhiều thời điểm:

1. Ứng dụng tạo record và serializer chuyển key/value thành byte.
2. Producer kiểm tra kích thước, metadata và phân vùng đích.
3. Producer đưa record vào accumulator và chờ batch được gửi.
4. Producer gửi request đến broker leader của partition.
5. Broker kiểm tra request, ghi record và trả acknowledgement theo cấu hình acks.
6. Producer hoàn tất future/callback thành công hoặc thất bại.

Có hai nhóm thời điểm cần phân biệt:

- **Lỗi đồng bộ:** xảy ra ngay trong lời gọi send(), trước khi ứng dụng nhận được future. Ví dụ có thể là lỗi serializer, record không hợp lệ, metadata không sẵn sàng hoặc producer không thể cấp chỗ trong buffer trong giới hạn chờ.
- **Lỗi bất đồng bộ:** send() đã trả về future, nhưng sau đó request gửi thất bại hoặc hết thời gian giao. Lỗi được chuyển qua callback/future; nếu đang dùng transaction, lỗi cũng có thể được phát hiện khi flush hoặc commit.

Luồng khái quát:

~~~
Ứng dụng gọi send(record)
          |
          v
Serialize và kiểm tra record
          |
     +----+----+
     |         |
   Lỗi       Hợp lệ
     |         |
     v         v
Exception   Accumulator / batch
đồng bộ         |
                v
          Gửi đến broker
                |
          +-----+-----+
          |           |
       Thành công    Thất bại
          |           |
          v           v
       Metadata    Retry nội bộ
       thành công      |
                      v
                Future/callback
                thành công hoặc lỗi
~~~

Ứng dụng cần quan sát cả exception đồng bộ và kết quả bất đồng bộ. Chỉ bọc câu lệnh send() trong try/catch không đủ để xử lý các lỗi chỉ xuất hiện sau khi lời gọi đã trả về.

## 2. Phân loại theo bản chất lỗi

Một cách phân loại thực tế là xem lỗi xảy ra ở đâu, có khả năng tự phục hồi hay không và kết quả ghi có rõ ràng hay không.

| Nhóm | Ví dụ | Ý nghĩa | Hướng xử lý |
|---|---|---|---|
| Dữ liệu/serialization | SerializationException, lỗi schema hoặc dữ liệu không hợp lệ | Producer không thể tạo payload hợp lệ | Sửa dữ liệu, serializer hoặc schema; không retry cùng payload vô hạn |
| Cấu hình/quyền truy cập | ConfigException, AuthenticationException, TopicAuthorizationException | Client thiếu cấu hình, xác thực hoặc quyền | Sửa cấu hình, credential, ACL; retry chỉ sau khi điều kiện thay đổi |
| Lỗi broker/metadata tạm thời | NotLeaderOrFollowerException, LeaderNotAvailableException, một số lỗi replica | Partition leader hoặc trạng thái cluster đang thay đổi | Để producer retry trong giới hạn; kiểm tra broker và partition nếu kéo dài |
| Lỗi mạng/request | NetworkException, DisconnectException, RequestTimedOutException | Request không hoàn tất hoặc acknowledgement không về đúng hạn | Kiểm tra mạng, broker, timeout; phân biệt kết quả chưa rõ |
| Hết thời gian giao | TimeoutException khi hết delivery.timeout.ms | Producer không thể báo thành công trong thời hạn giao | Kiểm tra nguyên nhân; xem đây là kết quả có thể chưa rõ ràng và xử lý duplicate |
| Giới hạn tài nguyên/kích thước | RecordTooLargeException, lỗi buffer hoặc chờ metadata quá lâu | Record/request vượt giới hạn hoặc producer thiếu tài nguyên | Điều chỉnh kích thước, batching, buffer hoặc tải; không retry y nguyên nếu giới hạn không đổi |
| Trạng thái producer/transaction | ProducerFencedException, InvalidProducerEpochException, OutOfOrderSequenceException | Producer có thể mất quyền sở hữu hoặc trạng thái sequence không còn hợp lệ | Dừng/đóng producer bị lỗi và khởi tạo lại theo quy tắc; với transaction phải rollback/phục hồi đúng cách |

Các exception cụ thể có thể khác nhau theo phiên bản Kafka client, broker và Spring Kafka. Một số exception thuộc nhóm retriable trong Kafka client; một số exception chỉ được xem là có thể retry trong một ngữ cảnh nhất định. Hãy dựa vào kiểu exception và tài liệu của phiên bản đang dùng, không phân loại chỉ bằng chuỗi message.

### 2.1. Lỗi dữ liệu và serialization

Producer phải chuyển key và value thành byte trước khi gửi. Nếu serializer không xử lý được kiểu dữ liệu, thiếu trường bắt buộc, gặp schema không tương thích hoặc lỗi chuyển đổi, lần gửi có thể thất bại ngay trong lời gọi send().

Ví dụ:

~~~java
public class OrderSerializer implements Serializer<OrderCreated> {

    @Override
    public byte[] serialize(String topic, OrderCreated data) {
        if (data == null || data.orderId() == null) {
            throw new SerializationException("orderId is required");
        }
        return encode(data);
    }
}
~~~

Nếu lỗi xuất phát từ payload không hợp lệ, gửi lại cùng payload sẽ tiếp tục thất bại. Cần xác định dữ liệu nào được phép phát, kiểm tra hợp lệ trước khi gửi và ghi nhận lỗi cùng business key để có thể sửa hoặc đưa vào luồng xử lý dữ liệu lỗi.

Với schema registry hoặc serializer phụ thuộc dịch vụ ngoài, lỗi kết nối đến registry có thể tạm thời; lỗi schema không tương thích có thể mang tính lâu dài. Hai trường hợp này cần chính sách khác nhau dù đều xuất hiện trong quá trình serialization.

### 2.2. Lỗi cấu hình, xác thực và phân quyền

Các lỗi như cấu hình sai bootstrap server, security protocol, truststore, SASL credential hoặc ACL thường không được giải quyết bằng cách gửi lại liên tục.

Ví dụ thường gặp:

- AuthenticationException: broker không chấp nhận thông tin xác thực hoặc cơ chế xác thực.
- TopicAuthorizationException: principal không có quyền thao tác với topic.
- ClusterAuthorizationException: principal thiếu quyền ở cấp cluster.
- ConfigException: giá trị cấu hình không hợp lệ hoặc thiếu cấu hình bắt buộc.

Đây thường là lỗi cần can thiệp cấu hình hoặc quản trị. Ứng dụng nên phát cảnh báo rõ ràng, giữ thông tin topic/cluster/principal có thể công khai an toàn và tránh ghi credential hoặc secret vào log.

### 2.3. Lỗi broker và metadata có thể phục hồi

Partition có thể đang bầu leader, broker leader có thể tạm thời không sẵn sàng, hoặc metadata mà producer đang giữ đã cũ. Các exception như NotLeaderOrFollowerException và LeaderNotAvailableException thường gắn với thay đổi trạng thái partition.

Kafka producer có cơ chế refresh metadata và retry một số lỗi retriable. Nếu cluster phục hồi trong thời gian cho phép, ứng dụng có thể nhận thành công mà không cần tự gửi lại record. Nếu lỗi vượt quá giới hạn giao, future cuối cùng thất bại và ứng dụng cần xử lý kết quả đó.

NotEnoughReplicasException và NotEnoughReplicasAfterAppendException cần được đọc trong bối cảnh cấu hình replication, min.insync.replicas và acks. Chúng báo hiệu broker không đáp ứng điều kiện replica mà request yêu cầu. Hãy kiểm tra ISR và sức khỏe cluster thay vì hạ acks ngay lập tức để làm biến mất lỗi.

### 2.4. Lỗi mạng và timeout

Mất kết nối, request timeout hoặc broker phản hồi chậm có thể khiến producer không nhận được kết quả đúng hạn. Một request có thể đã tới broker và được ghi, nhưng acknowledgement bị mất trên đường về. Vì vậy, timeout không phải lúc nào cũng chứng minh record chưa được ghi.

Đây là điểm quan trọng khi thiết kế retry ở tầng ứng dụng. Nếu gửi lại như một lần gửi nghiệp vụ mới, record có thể xuất hiện hai lần. Idempotent producer bảo vệ retry nội bộ của cùng producer theo protocol Kafka; nó không tự nhận diện hai lời gọi send() độc lập của ứng dụng là cùng một nghiệp vụ.

Khi kết quả chưa rõ ràng, hãy dùng event ID/business key ổn định và thiết kế consumer idempotent nếu duplicate có thể ảnh hưởng nghiệp vụ.

### 2.5. Lỗi kích thước và tài nguyên

RecordTooLargeException có thể xuất hiện khi record hoặc request vượt giới hạn phía producer/broker/topic. Cần kiểm tra các giới hạn có liên quan như max.request.size, message.max.bytes và max.message.bytes của topic, cùng kích thước sau serialization và compression.

Nếu record lớn hơn giới hạn cố định, retry cùng record không giúp ích. Có thể cần giảm payload, lưu dữ liệu lớn ở object storage rồi gửi reference, hoặc điều chỉnh giới hạn một cách có kiểm soát trên toàn tuyến producer-broker-consumer.

Producer cũng có thể chờ buffer hoặc metadata đến max.block.ms. Khi buffer đầy vì broker chậm hoặc producer không gửi kịp, lời gọi gửi có thể chặn rồi thất bại. Tăng buffer có thể hấp thụ burst ngắn, nhưng không giải quyết được tình trạng throughput đầu vào liên tục cao hơn throughput đầu ra.

## 3. Retriable, non-retriable và fatal exception

Kafka client có phân loại exception trong hệ thống kiểu của nó, trong đó RetriableException thể hiện lỗi mà request có thể thử lại. Tuy vậy, ứng dụng không nên chỉ dựa vào một phép kiểm tra kiểu đơn giản để quyết định retry vô hạn. Cần kết hợp loại lỗi, thời hạn giao, trạng thái transaction và tác động nghiệp vụ.

### 3.1. Retriable exception

Retriable exception thường phản ánh tình trạng có thể thay đổi theo thời gian: leader đang chuyển, kết nối bị ngắt, broker chưa sẵn sàng hoặc replica chưa đáp ứng điều kiện. Kafka producer đã có retry nội bộ cho nhiều loại lỗi này.

Hành vi mong muốn:

1. Cho producer thực hiện retry nội bộ trong giới hạn cấu hình.
2. Theo dõi số lần retry, độ trễ gửi và tỷ lệ lỗi cuối cùng.
3. Chỉ thực hiện retry ở tầng ứng dụng sau khi lần gửi đã kết thúc thất bại.
4. Đặt giới hạn thời gian và số lần retry của ứng dụng để không tạo vòng lặp vô hạn.

Nếu lỗi chỉ là một đợt leader election ngắn, retry nội bộ thường là lựa chọn phù hợp. Nếu lỗi kéo dài, cần xử lý như sự cố cluster hoặc dependency.

### 3.2. Non-retriable exception

Non-retriable exception thường không biến mất nếu gửi lại cùng request với cùng điều kiện. Ví dụ:

- Payload không thể serialize.
- Topic không hợp lệ hoặc quyền truy cập bị từ chối.
- Cấu hình client không hợp lệ.
- Record luôn vượt giới hạn kích thước.

Hành động đúng thường là sửa nguyên nhân, từ chối dữ liệu hoặc đưa record vào quy trình xử lý lỗi. Retry tự động chỉ có ý nghĩa sau khi nguyên nhân đã thay đổi, chẳng hạn ACL vừa được cấp hoặc schema đã được sửa.

### 3.3. Fatal exception và producer không thể tiếp tục

Một số lỗi làm trạng thái producer không còn an toàn để tiếp tục. Ví dụ trong giao dịch transactional:

- ProducerFencedException: producer khác đã khởi tạo cùng transactional ID và fencing producer hiện tại.
- InvalidProducerEpochException: epoch của producer không còn hợp lệ.
- Một số trường hợp OutOfOrderSequenceException: sequence của producer không còn nhất quán theo yêu cầu protocol.

Với lỗi fencing, kiểm tra xem transactional ID có bị dùng trùng giữa các instance hay không. Mỗi instance ứng dụng cần một transaction ID prefix duy nhất, đồng thời cần giữ tính ổn định của prefix trong vòng đời instance.

Không tiếp tục gửi bằng producer đã bị fencing. Để Spring Kafka transaction manager/container xử lý rollback theo cơ chế tương ứng, đóng producer bị lỗi và khởi tạo producer mới với transactional identity hợp lệ. Không tự tạo một transactional ID mới cho từng record; identity phải đại diện cho producer instance theo thiết kế.

## 4. Phân biệt timeout của producer

Một số timeout có ý nghĩa khác nhau và thường bị nhầm lẫn:

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| max.block.ms | Lời gọi gửi đồng bộ ở phía client | Thời gian tối đa producer chờ metadata hoặc buffer trước khi trả quyền điều khiển/lỗi cho caller |
| request.timeout.ms | Một request gửi đến broker | Thời gian client chờ phản hồi cho request |
| delivery.timeout.ms | Toàn bộ vòng đời giao một record | Giới hạn thời gian từ lúc record sẵn sàng gửi đến khi báo thành công hoặc thất bại, bao gồm batching, request và retry |
| Timeout của Future.get() | Caller chờ kết quả | Giới hạn thời gian thread ứng dụng chờ future; không phải giới hạn giao record của Kafka |

delivery.timeout.ms là giới hạn tổng thể quan trọng cho kết quả giao record. request.timeout.ms cần nhỏ hơn hoặc bằng giới hạn giao theo cấu hình hợp lệ của Kafka client. Tăng timeout có thể giúp chịu được broker chậm hoặc mạng có độ trễ cao, nhưng cũng làm lỗi được báo muộn hơn và giữ tài nguyên lâu hơn.

Ví dụ, Future.get(2, SECONDS) có thể ném java.util.concurrent.TimeoutException vì thread gọi đã chờ hai giây. Điều đó không tự động hủy record trong producer accumulator. Future vẫn có thể hoàn tất sau đó. Không được coi timeout của get() là bằng chứng rằng Kafka không ghi record.

Khi producer báo TimeoutException vì hết thời hạn giao, ứng dụng biết producer không thể xác nhận thành công trong giới hạn đã đặt. Tùy acks, thời điểm mất kết nối và trạng thái broker, kết quả thực tế có thể chưa rõ ràng. Hãy tránh phát lại một nghiệp vụ như một event mới mà không có cơ chế idempotency.

## 5. Producer retry nội bộ và retry của ứng dụng

Kafka producer có thể tự retry request thất bại khi exception được xem là retriable. Cơ chế này tận dụng sequence number và idempotence khi được bật để bảo vệ khỏi duplicate do retry protocol trong phạm vi producer session.

Retry của ứng dụng là một lần gọi send() mới sau khi lần gửi trước đã thất bại. Nó có thể mang sequence mới và được xem như một record mới. Vì vậy, hai tầng retry có trách nhiệm khác nhau:

| Tầng retry | Ai thực hiện? | Phạm vi | Lưu ý |
|---|---|---|---|
| Retry nội bộ | Kafka producer client | Request/batch của lần gửi hiện tại | Được điều khiển bởi retry, backoff và delivery timeout; idempotence bảo vệ protocol retry |
| Retry ứng dụng | Service hoặc workflow của ứng dụng | Gửi lại nghiệp vụ sau khi lần trước báo lỗi | Cần event ID ổn định, giới hạn retry và xử lý kết quả chưa rõ |
| Retry phía consumer | Consumer hoặc listener error handler | Xử lý lại record đã được ghi vào Kafka | Không thay thế retry gửi record của producer |

Không nên cấu hình retry ở mọi tầng mà không có một ngân sách thời gian chung. Ví dụ, producer đã retry nội bộ trong 2 phút, service retry 5 lần và workflow retry tiếp nhiều lần có thể kéo dài sự cố, tạo tải lớn và khiến cùng một nghiệp vụ được phát lại nhiều lần.

### 5.1. Cấu hình nền tảng cho producer bền vững

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
~~~

Đây là cấu hình minh họa; các giá trị timeout phải phù hợp với độ trễ cluster và SLO của ứng dụng. Với producer idempotent, các ràng buộc của Kafka client về acks, retries và số request đang bay phải được giữ hợp lệ. Các phiên bản Kafka hiện đại mặc định bật idempotence trong nhiều cấu hình, nhưng khai báo tường minh có thể giúp ý định vận hành dễ đọc hơn.

acks=all yêu cầu acknowledgement từ các replica trong ISR theo quy tắc broker. Nó cần đi cùng cấu hình replication và min.insync.replicas phù hợp. acks=all không có nghĩa mọi replica trong cluster đều phải xác nhận, và không thể bù cho một replication factor hoặc ISR được cấu hình thiếu.

## 6. Xử lý exception với KafkaTemplate

Trong Spring Kafka 3.x, KafkaTemplate.send() trả về CompletableFuture<SendResult<K,V>>. Các phiên bản cũ hơn dùng ListenableFuture; hãy điều chỉnh ví dụ theo phiên bản thư viện của dự án.

Một cách xử lý bất đồng bộ:

~~~java
public void publish(OrderCreated event) {
    try {
        kafkaTemplate.send("orders.created", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    Throwable cause = unwrap(error);
                    handleProducerFailure(event, cause);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info("Published orderId={} topic={} partition={} offset={}",
                    event.orderId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
            });
    }
    catch (RuntimeException error) {
        // Lỗi đồng bộ khi chuẩn bị hoặc đăng ký lần gửi.
        handleProducerFailure(event, error);
    }
}

private Throwable unwrap(Throwable error) {
    if (error instanceof CompletionException && error.getCause() != null) {
        return error.getCause();
    }
    return error;
}
~~~

Ví dụ này minh họa hai nơi bắt lỗi: catch xử lý lỗi xảy ra trước khi future được trả về; whenComplete xử lý kết quả bất đồng bộ. Trong ứng dụng thực tế, handleProducerFailure cần phân loại exception, ghi metric và chọn chính sách phù hợp. Không nên chỉ log rồi bỏ qua nếu event là dữ liệu bắt buộc phải phát.

Nếu dùng KafkaTemplate trong một luồng transactional, cần bảo đảm lỗi gửi không bị nuốt. Exception bất đồng bộ có thể được phát hiện khi transaction flush/commit; hãy để lỗi làm transaction rollback khi nghiệp vụ yêu cầu. Với luồng cần biết chắc từng kết quả trước khi tiếp tục, có thể chờ future trong một thời hạn phù hợp, nhưng tránh chờ vô hạn hoặc dùng timeout của caller như kết luận về trạng thái broker.

### 6.1. Chờ kết quả có giới hạn

Đôi khi ứng dụng cần kết quả gửi ngay trong luồng xử lý:

~~~java
public SendResult<String, OrderCreated> publishAndWait(
        OrderCreated event) {
    try {
        return kafkaTemplate
            .send("orders.created", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted while publishing", ex);
    }
    catch (ExecutionException ex) {
        throw new IllegalStateException("Kafka publish failed", ex.getCause());
    }
    catch (TimeoutException ex) {
        // Đây là timeout của thao tác chờ Future.get().
        // Future gửi có thể vẫn đang chạy.
        throw new IllegalStateException("Timed out waiting for publish result", ex);
    }
}
~~~

Không nên dùng get() cho mọi lần gửi nếu throughput cao: nó biến luồng gửi bất đồng bộ thành chờ tuần tự và có thể làm giảm throughput. Nếu cần chờ, hãy chọn timeout dựa trên yêu cầu nghiệp vụ và xử lý đúng trường hợp caller hết thời gian chờ nhưng future vẫn chưa kết thúc.

### 6.2. Quan sát bằng ProducerListener

Spring Kafka cho phép gắn ProducerListener vào KafkaTemplate để nhận callback thành công/thất bại ở một nơi chung. Cách này hữu ích cho logging và metric dùng chung, nhưng không thay thế trách nhiệm xử lý lỗi ở nghiệp vụ gọi gửi.

Thông tin log nên có:

- Topic và partition nếu đã xác định được.
- Business key hoặc event ID, tránh ghi toàn bộ payload nhạy cảm.
- Loại exception gốc và nhóm phân loại.
- Số lần retry ứng dụng, nếu có.
- Correlation ID/trace ID để liên kết với request nguồn.

Không log credential, token, dữ liệu cá nhân hoặc payload nhạy cảm chỉ để điều tra lỗi producer.

## 7. Phân loại và chọn hành động

Một quy trình quyết định đơn giản:

~~~
Producer send thất bại
        |
        v
Xác định exception gốc
        |
        +--> Dữ liệu / serialization?
        |       |
        |       +--> Sửa payload/schema hoặc đưa vào luồng lỗi
        |
        +--> Authentication / authorization / config?
        |       |
        |       +--> Cảnh báo và sửa cấu hình/quyền
        |
        +--> Retriable network / broker error?
        |       |
        |       +--> Để retry nội bộ; theo dõi delivery timeout
        |
        +--> Timeout / kết quả chưa rõ?
        |       |
        |       +--> Dùng event ID ổn định và kiểm soát duplicate
        |
        +--> Producer fenced / epoch / sequence fatal?
                |
                +--> Dừng producer hiện tại và phục hồi transaction
~~~

Khi đã có exception cuối cùng, hãy ghi nhận:

1. Exception gốc sau khi bỏ wrapper như ExecutionException hoặc CompletionException.
2. Topic và business event ID.
3. Exception có phải retriable theo Kafka client hay không.
4. Lần gửi có nằm trong transaction không.
5. Có khả năng record đã được ghi nhưng acknowledgement bị mất không.
6. Chính sách tiếp theo: sửa dữ liệu, retry, lưu pending, chuyển DLT/outbox hay dừng luồng.

Không nên dùng exception.getMessage().contains("timeout") hoặc so khớp chuỗi log để phân loại. Message có thể thay đổi giữa phiên bản và không biểu diễn đầy đủ trạng thái exception. Hãy dùng kiểu exception, nguyên nhân gốc và ngữ cảnh lần gửi.

## 8. Retry ở tầng ứng dụng và kiểm soát duplicate

Nếu ứng dụng quyết định retry sau khi future thất bại, hãy dùng một chính sách rõ ràng:

- Giới hạn số lần retry hoặc tổng thời gian retry.
- Dùng exponential backoff có jitter để các instance không retry đồng loạt.
- Chỉ retry những lỗi có khả năng phục hồi hoặc lỗi chưa rõ kết quả nhưng có cơ chế chống duplicate.
- Giữ event ID/business key không đổi qua các lần retry.
- Ghi nhận trạng thái pending/dead-letter để có thể phục hồi sau restart.
- Đặt giới hạn tổng thời gian từ lúc nhận nghiệp vụ đến lúc phát thành công hoặc báo lỗi.

Ví dụ chính sách:

~~~java
RetryPolicy policy = new RetryPolicy(
    5,                 // tối đa 5 lần ở tầng ứng dụng
    Duration.ofMillis(200),
    Duration.ofSeconds(10),
    true               // exponential backoff có jitter
);
~~~

Đây là pseudo-code mô tả chính sách, không phải API chuẩn của Spring Kafka. Hãy triển khai bằng cơ chế retry phù hợp với ứng dụng, chẳng hạn scheduler, retry library hoặc workflow bền vững.

Với lỗi dữ liệu không thể sửa tự động, không retry liên tục. Lưu record lỗi cùng thông tin chẩn đoán vào nơi có thể truy vết, rồi cho phép người vận hành hoặc quy trình sửa dữ liệu phát lại sau.

### 8.1. Idempotency ở consumer

Nếu producer gửi lại một nghiệp vụ do kết quả trước chưa rõ, consumer có thể nhận hai record cùng event ID. Consumer có thể dùng bảng inbox hoặc unique constraint để chỉ áp dụng nghiệp vụ một lần:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng database transaction với thay đổi nghiệp vụ, consumer kiểm tra và ghi event_id. Nếu ID đã tồn tại, bỏ qua phần cập nhật lặp. Cần bảo đảm việc kiểm tra, ghi nhận và cập nhật nghiệp vụ nằm trong cùng database transaction để tránh race condition.

Idempotent consumer không thay thế producer idempotence. Hai cơ chế giải quyết hai phạm vi khác nhau: producer idempotence bảo vệ retry protocol của producer; idempotent consumer bảo vệ nghiệp vụ khi record được phát hoặc giao lại nhiều lần.

## 9. Exception trong Kafka transaction

Transactional producer bổ sung các trạng thái cần được xử lý cẩn thận. Khi transaction đang mở, một send thất bại có thể khiến transaction không thể commit an toàn. Ứng dụng cần để lỗi đi tới transaction boundary và thực hiện rollback theo cấu hình Spring Kafka.

### 9.1. Không nuốt exception trong listener

Ví dụ listener gửi output:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void handle(OrderCreated event) {
    kafkaTemplate.send("billing.requests", event.orderId(),
        createBillingRequest(event));
}
~~~

Khi container được cấu hình Kafka transaction manager, transaction bao trùm output và offset đầu vào. Nếu listener bắt lỗi gửi rồi chỉ log và trả về bình thường, container có thể xem lần xử lý là thành công và commit transaction/offset theo luồng bình thường. Khi lỗi phải làm rollback, hãy để exception truyền ra hoặc đánh dấu transaction rollback-only bằng cơ chế phù hợp.

### 9.2. ProducerFencedException

Lỗi fencing thường xuất hiện khi có producer khác dùng cùng transactional ID. Broker tăng epoch để producer mới sở hữu identity đó; producer cũ bị từ chối. Điều này thường liên quan đến prefix không duy nhất giữa các pod, hai instance cùng khởi tạo một identity hoặc một tiến trình cũ chưa dừng.

Hành động:

1. Ghi nhận transactional ID/prefix và instance nhận lỗi.
2. Kiểm tra cách tạo prefix theo pod/instance.
3. Dừng sử dụng producer đã bị fencing.
4. Để transaction hiện tại rollback hoặc được coordinator kết thúc theo cơ chế của Kafka.
5. Khởi tạo lại producer sau khi identity đã được bảo đảm duy nhất.

Không retry liên tục trên producer bị fencing; lỗi này cần giải quyết quyền sở hữu identity.

### 9.3. Timeout khi commit transaction

Timeout trong lúc commit khác với timeout khi caller chờ một future gửi đơn lẻ. Producer có thể không nhận được kết quả commit đúng hạn dù coordinator đã xử lý request. Vì thế, ứng dụng cần tuân theo hợp đồng của Kafka client và Spring Kafka phiên bản đang dùng để phục hồi transaction; không tự giả định rằng commit chắc chắn thất bại hoặc chắc chắn thành công.

Không phát lại toàn bộ nghiệp vụ như một transaction mới chỉ vì thread gọi commit bị timeout. Trước tiên cần xử lý trạng thái producer/transaction theo hướng dẫn của framework, sau đó dùng event ID và idempotency để bảo vệ nghiệp vụ nếu workflow phải được chạy lại.

## 10. Giám sát và chẩn đoán producer exception

Theo dõi tỷ lệ lỗi theo loại exception, topic và ứng dụng. Một chỉ số lỗi tổng thể có thể che giấu việc một topic cụ thể liên tục bị từ chối do ACL hoặc một partition liên tục thiếu ISR.

Các tín hiệu nên quan sát:

| Tín hiệu | Điều cần phát hiện |
|---|---|
| Send success/failure rate | Tỷ lệ gửi thành công và thất bại theo topic |
| Retry rate | Producer có phải retry thường xuyên hay không |
| Record error rate theo exception class | Nhóm lỗi nào đang tăng |
| Request latency và record queue time | Broker chậm hay producer bị backlog |
| Buffer available bytes / waiting threads | Producer có bị cạn buffer hoặc chặn thread không |
| Record send rate và byte rate | Throughput đầu vào/đầu ra |
| Batch size và compression rate | Hiệu quả batching/compression |
| Delivery timeout count | Record hết hạn giao |
| Transaction abort/fencing count | Vấn đề về transaction hoặc transactional ID |
| Under-replicated partitions và ISR shrink | Nguyên nhân phía broker có thể gây lỗi producer |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và hệ thống giám sát. Hãy kiểm tra metric thực tế được export trong ứng dụng thay vì giả định mọi phiên bản đều có cùng tên.

### 10.1. Runbook chẩn đoán nhanh

**Khi SerializationException tăng:**

1. Xác định topic, serializer và loại payload.
2. Kiểm tra thay đổi schema hoặc dữ liệu đầu vào gần thời điểm lỗi.
3. Kiểm tra lỗi phụ thuộc schema registry nếu có.
4. Tách dữ liệu lỗi khỏi retry tự động và sửa nguồn dữ liệu/serializer.

**Khi TimeoutException hoặc NetworkException tăng:**

1. So sánh request latency, record queue time và delivery timeout.
2. Kiểm tra kết nối producer đến broker, DNS, TLS và broker request latency.
3. Kiểm tra partition leader, ISR, under-replicated partitions và tải broker.
4. Đánh giá kết quả chưa rõ của các lần gửi cuối cùng và nguy cơ duplicate khi replay.

**Khi NotEnoughReplicasException tăng:**

1. Kiểm tra replication factor và min.insync.replicas.
2. Kiểm tra ISR của các partition bị ảnh hưởng.
3. Xác định broker nào mất kết nối hoặc đang phục hồi.
4. Khôi phục replication health trước khi cân nhắc thay đổi chính sách durability.

**Khi ProducerFencedException xuất hiện:**

1. Xác định transactional ID/prefix của producer bị lỗi.
2. Kiểm tra số replica ứng dụng và cách sinh instance identity.
3. Tìm instance cũ hoặc tiến trình trùng identity.
4. Khởi tạo lại producer với identity duy nhất và xác minh transaction mới hoạt động.

## 11. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Retry mọi exception vô hạn | Lỗi cấu hình/dữ liệu kéo dài và gây tải | Phân loại retriable, non-retriable và fatal; đặt retry budget |
| Chỉ bắt exception quanh send() | Bỏ sót lỗi bất đồng bộ từ future/callback | Xử lý cả lỗi đồng bộ lẫn future completion |
| Coi Future.get() timeout là record chưa được ghi | Gửi lại có thể tạo duplicate | Phân biệt caller wait timeout với delivery timeout |
| Chỉ dùng retry ứng dụng, tắt idempotence | Duplicate do retry request có thể tăng | Bật idempotence phù hợp và dùng event ID ổn định |
| Hạ acks để giảm lỗi replica | Giảm durability trong khi nguyên nhân cluster chưa được xử lý | Khôi phục ISR và cấu hình replication phù hợp |
| Nuốt lỗi gửi trong transaction | Offset hoặc transaction có thể commit theo luồng thành công | Để lỗi truyền tới transaction boundary khi cần rollback |
| Dùng chung transactional ID giữa nhiều pod | Producer cũ bị fencing | Tạo transaction ID prefix duy nhất theo instance |
| Chỉ log message, không lưu event ID/topic | Khó điều tra và replay chính xác | Log exception class, topic, key/event ID và correlation ID |

## 12. Checklist phân loại trước khi xử lý

Khi producer phát sinh exception, hãy lần lượt trả lời:

1. Lỗi xảy ra đồng bộ trong send() hay bất đồng bộ qua future/callback?
2. Exception gốc là kiểu gì sau khi bỏ ExecutionException, CompletionException hoặc wrapper của Spring?
3. Đây là lỗi dữ liệu, cấu hình/quyền, broker/metadata, mạng/timeout, kích thước/tài nguyên hay trạng thái producer/transaction?
4. Kafka client có thể retry nội bộ loại lỗi này không, và delivery.timeout.ms còn bao nhiêu thời gian?
5. Record có thể đã được broker ghi nhưng acknowledgement bị mất không?
6. Producer idempotence có được bật và cấu hình hợp lệ không?
7. Lần gửi có thuộc transaction không? Exception có làm transaction cần rollback không?
8. Nếu ứng dụng gửi lại, event ID có giữ nguyên và consumer có xử lý idempotent không?
9. Có thể sửa nguyên nhân trước khi retry không, hay cần chuyển record vào luồng xử lý lỗi?
10. Metric, log và alert nào cho biết lỗi đã phục hồi hoặc đang lan rộng?

Một producer bền vững cần xử lý được cả lỗi tạm thời lẫn lỗi không thể phục hồi. Kafka client đảm nhận retry protocol trong giới hạn cấu hình; ứng dụng chịu trách nhiệm phân loại kết quả cuối cùng, kiểm soát retry nghiệp vụ, giữ khả năng truy vết và bảo vệ hệ thống khỏi duplicate. Khi exception liên quan đến transaction hoặc producer identity, việc phục hồi trạng thái phải hoàn tất trước khi tiếp tục phát record.
