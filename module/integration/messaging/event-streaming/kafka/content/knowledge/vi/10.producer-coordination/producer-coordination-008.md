# max.in.flight.requests.per.connection và rủi ro đảo thứ tự

Kafka producer có thể gửi nhiều Produce request tới cùng một broker trước khi nhận response của các request trước. Cách gửi gối đầu này giúp tận dụng mạng và tăng thông lượng, đặc biệt khi độ trễ giữa producer và broker đáng kể. Cấu hình max.in.flight.requests.per.connection giới hạn số request chưa nhận response trên mỗi kết nối broker của producer.

Giới hạn này ảnh hưởng trực tiếp tới khả năng pipeline request và cách producer xử lý retry. Nếu producer cho phép nhiều request đang bay cùng lúc, một request cũ bị lỗi và phải gửi lại có thể hoàn tất sau request mới hơn. Khi idempotence không được bật, điều đó có thể làm record bị ghi theo thứ tự khác với thứ tự producer gửi. Với idempotent producer được cấu hình đúng, Kafka duy trì thứ tự trong partition khi retry và cho phép tối đa năm request đang bay trên một kết nối.

Bài học thuộc phần điều phối gửi của module KAFKA. Bạn sẽ hiểu giới hạn request đang chờ, cách retry tạo ra rủi ro đảo thứ tự, điều kiện bảo đảm của idempotence, đánh đổi hiệu năng và cách cấu hình trong Java/Spring Kafka.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích max.in.flight.requests.per.connection giới hạn điều gì và áp dụng ở phạm vi nào.
- Phân biệt request đang bay, batch record và số partition.
- Mô tả tình huống retry khiến batch cũ được ghi sau batch mới.
- Giải thích cách idempotent producer sử dụng producer ID, epoch và sequence number để chống ghi trùng, giữ thứ tự khi retry.
- Chọn giá trị max in-flight phù hợp với idempotence, độ trễ và thông lượng.
- Cấu hình producer trong Java và Spring Boot.
- Phân biệt bảo đảm thứ tự trong một partition với thứ tự toàn topic hoặc thứ tự nghiệp vụ giữa nhiều producer.
- Xây dựng cách kiểm chứng ordering và chẩn đoán khi producer gặp timeout hoặc retriable error.

## 2. max.in.flight.requests.per.connection là gì?

Producer Kafka không nhất thiết phải đợi response của request hiện tại mới gửi request tiếp theo. Nó có thể gửi request tới broker, tiếp tục gửi request khác trên cùng kết nối rồi xử lý các response khi chúng quay về. Cách này được gọi là pipelining.

max.in.flight.requests.per.connection đặt giới hạn số request mà producer đã gửi nhưng chưa nhận response trên một kết nối tới broker. Khi đạt giới hạn, producer phải chờ một request hoàn tất trước khi gửi thêm request trên kết nối đó.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Record | Một sự kiện hoặc bản ghi ứng dụng được producer gửi |
| Batch | Nhóm record của một partition được gom lại để gửi hiệu quả hơn |
| In-flight request | Một request giao thức đã gửi qua kết nối broker nhưng chưa nhận response |

Một Produce request có thể chứa batch của nhiều partition mà broker đó phục vụ. Vì vậy, max.in.flight.requests.per.connection không phải số record tối đa, không phải số batch tối đa cho mỗi partition và cũng không phải số partition mà producer có thể xử lý.

Cấu hình này có phạm vi **mỗi kết nối tới broker**. Producer thường duy trì kết nối tới nhiều broker, nên tổng số request đang chờ của producer trên toàn cụm có thể lớn hơn giá trị cấu hình. Ví dụ, giới hạn bằng 5 có thể cho phép tối đa năm request chưa hoàn tất trên kết nối tới Broker A và đồng thời tối đa năm request trên kết nối tới Broker B.

~~~mermaid
flowchart TB
    P["Kafka Producer"]
    subgraph A["Kết nối tới Broker A"]
        A1["Request 1<br/>đang chờ"]
        A2["Request 2<br/>đang chờ"]
        A3["Request 3<br/>đang chờ"]
        A4["Request 4<br/>đang chờ"]
        A5["Request 5<br/>đang chờ"]
    end
    subgraph B["Kết nối tới Broker B"]
        B1["Request 1<br/>đang chờ"]
        B2["Request 2<br/>đang chờ"]
    end
    P --> A
    P --> B
~~~

Hình minh họa trường hợp cấu hình cho phép tối đa năm request đang chờ trên mỗi kết nối. Broker A đang sử dụng đủ giới hạn, trong khi Broker B mới có hai request. Producer vẫn có thể tiếp tục công việc trên một kết nối khác nếu kết nối đó còn khả năng gửi.

### 2.1. Vì sao producer cần gửi nhiều request gối đầu?

Giả sử một request mất 10 ms để đi tới broker và nhận response. Nếu producer chỉ cho phép một request đang chờ, nó có thể phải đợi gần hết một vòng mạng trước khi gửi request tiếp theo trên kết nối đó. Khi tải lớn và broker xử lý nhanh, thời gian chờ mạng có thể làm giảm mức sử dụng băng thông và throughput.

Cho phép nhiều request đang bay giúp producer che giấu một phần round-trip time. Trong lúc request trước đang được broker xử lý hoặc response đang truyền về, producer có thể gửi request kế tiếp.

Cơ chế này đặc biệt hữu ích khi:

- Broker ở xa producer hoặc độ trễ mạng cao.
- Producer có nhiều batch cần gửi liên tục.
- Broker có khả năng xử lý song song nhiều request.
- Ứng dụng ưu tiên throughput và vẫn cần giới hạn số request tồn đọng.

Tuy nhiên, số request đang bay lớn hơn cũng có nghĩa là có nhiều kết quả chưa được xác nhận cùng lúc. Khi lỗi mạng hoặc lỗi broker xảy ra, producer phải quản lý nhiều request đang chờ, retry và xử lý response. Đây là nơi rủi ro ordering xuất hiện nếu idempotence không được bật.

## 3. Rủi ro đảo thứ tự khi retry

Kafka producer gom record theo partition và gửi Produce request tới broker leader của partition. Nếu request đầu tiên gặp lỗi có thể retry, trong khi request sau đã được gửi và thành công, thứ tự ghi trên broker có thể khác thứ tự producer ban đầu gửi.

Giả sử cùng một partition nhận hai batch:

- Batch A chứa sự kiện sequence=100.
- Batch B chứa sự kiện sequence=101.
- Producer gửi A trước, sau đó gửi B.
- Request chứa A gặp lỗi tạm thời và phải retry.
- Request chứa B hoàn tất trước khi lần retry của A được broker chấp nhận.

Khi đó broker có thể ghi B trước A nếu producer không dùng cơ chế bảo đảm thứ tự phù hợp.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker leader
    P->>B: Request A (sequence 100)
    P->>B: Request B (sequence 101)
    B--xP: A gặp lỗi retriable / response lỗi
    B-->>P: B được xác nhận
    P->>B: Retry A
    B-->>P: A được xác nhận
    Note over B: Nếu không có idempotence và nhiều request in-flight,<br/>thứ tự append có thể thành B rồi A
~~~

Đây là một tình huống minh họa rủi ro, không phải điều xảy ra với mọi retry. Khả năng đảo thứ tự phụ thuộc loại lỗi, thời điểm response, cách producer gửi batch và việc broker đã append dữ liệu hay chưa.

### 3.1. Điều gì xảy ra khi max in-flight bằng 1?

Nếu max.in.flight.requests.per.connection=1, producer chỉ gửi một request rồi chờ request đó hoàn tất trước khi gửi request kế tiếp trên kết nối đó.

Nếu request A gặp lỗi retryable, producer xử lý retry A trước. Chỉ sau khi A hoàn tất theo kết quả cuối cùng, producer mới tiếp tục gửi request B. Điều này ngăn B vượt qua A trên cùng kết nối trong chuỗi gửi đó.

Giới hạn bằng 1 là cách bảo vệ thứ tự đơn giản ngay cả khi idempotence không được bật, nhưng có thể làm giảm throughput do không còn nhiều request gối đầu để che giấu round-trip time.

### 3.2. Vì sao rủi ro liên quan tới thứ tự trong partition?

Kafka chỉ bảo đảm thứ tự record trong một partition. Nếu hai batch thuộc hai partition khác nhau, không có một thứ tự toàn cục giữa chúng để cấu hình max in-flight duy trì.

Rủi ro được thảo luận ở đây là các batch liên tiếp của cùng partition được gửi qua kết nối tới broker phục vụ partition đó. Khi retry làm batch cũ hoàn tất sau batch mới, thứ tự record trong partition có thể bị thay đổi so với thứ tự producer dự định.

Nếu nghiệp vụ yêu cầu sự kiện của cùng order, account hoặc device đi theo thứ tự, hãy bảo đảm các sự kiện liên quan cùng đi vào một partition bằng key ổn định. Sau đó cấu hình producer để retry không phá vỡ thứ tự của partition.

## 4. Idempotent producer bảo vệ thứ tự như thế nào?

Kafka cung cấp idempotent producer để xử lý retry an toàn hơn. Producer được cấp producer ID; mỗi partition mà producer gửi dữ liệu có sequence number để nhận diện thứ tự batch. Broker theo dõi sequence number và producer epoch nhằm phát hiện batch lặp hoặc batch không đúng trình tự.

Khi producer gửi batch và không nhận được response, nó có thể gửi lại. Nếu broker đã append batch trước đó, sequence number cho phép broker nhận diện retry là bản gửi trùng và tránh append record lần thứ hai. Nếu batch mới hơn đã được gửi trong khi batch trước retry, broker dùng trạng thái sequence để kiểm tra thứ tự hợp lệ.

Ở mức khái niệm:

- **Producer ID (PID):** định danh producer trong giao thức Kafka.
- **Producer epoch:** thế hệ producer, giúp broker phân biệt phiên hoạt động và xử lý producer cũ bị fencing trong các tình huống phù hợp.
- **Sequence number:** số thứ tự batch theo từng topic-partition, giúp broker nhận biết batch mới, batch trùng hoặc batch sai thứ tự.
- **Idempotence:** bảo đảm retry của producer không tạo bản ghi trùng trong phạm vi cơ chế producer session và giữ thứ tự ghi trong partition theo điều kiện cấu hình.

~~~mermaid
flowchart LR
    P["Idempotent producer<br/>PID + epoch + sequence"]
    R["Produce request<br/>Partition P0, sequence N"]
    B["Broker leader"]
    C{"Sequence hợp lệ?"}
    W["Append batch vào log"]
    D["Nhận diện retry<br/>đã append"]
    E["Trả ACK / kết quả"]

    P --> R --> B --> C
    C -->|Batch mới đúng thứ tự| W --> E
    C -->|Batch trùng đã xử lý| D --> E
~~~

Sơ đồ đơn giản hóa cách broker xử lý sequence. Chi tiết protocol bao gồm trạng thái producer theo partition, epoch và các quy tắc kiểm tra sequence cụ thể.

### 4.1. Điều kiện cấu hình idempotence

Để bật idempotence, các điều kiện quan trọng của Kafka producer là:

- acks phải là all.
- retries phải lớn hơn 0.
- max.in.flight.requests.per.connection phải nhỏ hơn hoặc bằng 5.

Kafka client sẽ kiểm tra các điều kiện tương thích khi khởi tạo producer. Nếu bật idempotence nhưng cấu hình không đáp ứng yêu cầu, producer có thể báo lỗi cấu hình thay vì chạy với một bảo đảm không hợp lệ.

Với Kafka producer hiện đại, idempotence được bật mặc định từ Kafka 3.0. Tuy nhiên, không nên dựa vào mặc định nếu ứng dụng cần một hợp đồng ordering rõ ràng qua nhiều phiên bản client. Hãy cấu hình tường minh và kiểm tra đúng phiên bản kafka-clients được ứng dụng sử dụng.

Giá trị max in-flight bằng 5 là giới hạn được hỗ trợ cùng idempotence. Giá trị lớn hơn 5 không tương thích với cơ chế idempotent producer của Kafka client. Giá trị nhỏ hơn, ví dụ 1 hoặc 2, vẫn có thể sử dụng nhưng làm giảm mức pipelining.

### 4.2. Idempotence không phải exactly-once cho toàn bộ nghiệp vụ

Idempotent producer bảo vệ thao tác ghi của producer trong Kafka trước retry trùng lặp theo cơ chế của producer session. Nó không tự động bảo đảm mọi thao tác nghiệp vụ chỉ xảy ra đúng một lần.

Ví dụ:

1. Order Service gửi OrderCreated vào Kafka thành công.
2. Ứng dụng nhận ACK.
3. Một lỗi nghiệp vụ khiến ứng dụng gọi lại thao tác gửi với một lệnh gửi mới.
4. Producer có thể phát một record khác dù payload giống record trước.

Đây là hai lần gửi ở cấp ứng dụng, không phải retry trùng cùng sequence của một batch. Nếu cần loại trùng theo nghiệp vụ, hãy dùng eventId duy nhất và thiết kế consumer idempotent hoặc inbox/deduplication ở database.

Tương tự, nếu consumer đọc record, gọi một API thanh toán bên ngoài rồi lỗi trước khi commit offset, Kafka có thể giao lại record. Idempotent producer không làm cho API thanh toán trở nên idempotent.

### 4.3. Giao dịch Kafka bổ sung bảo đảm nào?

Producer transaction hỗ trợ ghi nguyên tử nhiều record, có thể trên nhiều partition và topic, trong phạm vi giao dịch Kafka. Consumer dùng isolation.level=read_committed chỉ thấy các record của giao dịch đã commit.

Transactional producer cũng sử dụng idempotence. Khi cấu hình transactional.id, Kafka producer tự bật các cơ chế cần thiết và quản lý transaction coordinator. Tuy nhiên, transaction không tạo ra một thứ tự toàn cục giữa partition; thứ tự vẫn được hiểu trong từng partition.

Nếu quy trình consume-process-produce cần bảo đảm offset đầu vào và record đầu ra được commit nhất quán trong Kafka, có thể dùng transaction theo mô hình phù hợp. Nếu quy trình gọi database hoặc dịch vụ bên ngoài, cần thiết kế outbox, inbox, idempotency hoặc cơ chế phối hợp riêng.

## 5. Chọn max in-flight theo mục tiêu

Trong đa số triển khai hiện đại, lựa chọn ban đầu hợp lý là bật idempotence và để max.in.flight.requests.per.connection ở mức 5, sau đó đo throughput và latency trong tải thực tế.

| Cấu hình | Idempotence | Rủi ro đảo thứ tự do retry | Đánh đổi |
|---|---|---|---|
| max in-flight = 1 | Tắt hoặc bật | Tránh request sau vượt request trước trên cùng kết nối | Thứ tự đơn giản, nhưng pipelining thấp và có thể giảm throughput |
| max in-flight từ 2 đến 5 | Bật | Kafka duy trì ordering theo partition trong cơ chế idempotent | Cân bằng throughput và bảo đảm retry |
| max in-flight từ 2 đến 5 | Tắt | Có thể xảy ra khi request trước retry còn request sau đã thành công | Throughput có thể cao, nhưng cần chấp nhận rủi ro ordering |
| max in-flight lớn hơn 5 | Bật | Không tương thích với điều kiện idempotence của producer | Producer có thể từ chối cấu hình |
| max in-flight lớn hơn 5 | Tắt | Rủi ro đảo thứ tự khi retry càng cần được cân nhắc | Có thể tăng pipelining nhưng tăng số request tồn đọng |

Bảng này giả định các batch liên quan được gửi tới cùng partition và cùng producer connection. Nó không nói rằng mọi request khác partition đều có thứ tự chung.

### 5.1. Khi ưu tiên thứ tự nghiêm ngặt

Nếu ứng dụng cũ chưa thể bật idempotence hoặc có ràng buộc tương thích, đặt max in-flight bằng 1 có thể là lựa chọn bảo thủ. Tuy nhiên, trước tiên hãy kiểm tra có thể bật idempotence hay không vì nó thường cho phép giữ throughput tốt hơn mà vẫn bảo đảm thứ tự khi retry.

Nếu thứ tự nghiệp vụ quan trọng, ngoài cấu hình producer còn phải kiểm tra:

- Các sự kiện của cùng thực thể dùng cùng key.
- Số partition và thuật toán partitioning ổn định.
- Không có nhiều producer độc lập cùng ghi một thực thể mà không có quy tắc tuần tự hóa nghiệp vụ.
- Ứng dụng không gửi sự kiện theo thứ tự sai từ trước khi Kafka nhận chúng.
- Consumer xử lý và commit offset theo cách không phá vỡ thứ tự cần thiết.

### 5.2. Khi ưu tiên throughput

Nếu tải cao và độ trễ mạng đáng kể, nhiều request in-flight giúp producer duy trì đường truyền tốt hơn. Bật idempotence với giới hạn tối đa 5 là một điểm bắt đầu phổ biến.

Không nên tăng giới hạn vượt 5 để tìm throughput nếu vẫn cần idempotence; client không hỗ trợ tổ hợp đó. Thay vào đó, đo batch size, linger, compression, số partition, số broker, network và consumer capacity.

### 5.3. Khi hệ thống không cần ordering

Nếu các record độc lập và thứ tự không có ý nghĩa nghiệp vụ, ứng dụng có thể cân nhắc idempotence và max in-flight theo yêu cầu throughput, nhưng vẫn nên giữ retry an toàn và khả năng xử lý duplicate. Không cần đánh đổi độ bền dữ liệu chỉ vì thứ tự không quan trọng.

Việc không cần ordering không có nghĩa record không thể bị trùng hoặc mất theo cách ứng dụng quan sát. Cần phân biệt ordering, delivery semantics và durability.

## 6. Ví dụ cấu hình Java producer

Ví dụ dưới đây bật idempotence, xác nhận ghi từ ISR và cho phép tối đa năm request chưa được xác nhận trên mỗi kết nối broker.

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

public class OrderProducerConfig {

    public static KafkaProducer<String, String> createProducer() {
        Properties props = new Properties();

        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "kafka-1:9092,kafka-2:9092,kafka-3:9092");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());

        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
        props.put(
                ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
                5
        );

        return new KafkaProducer<>(props);
    }
}
~~~

Cấu hình trên thể hiện các ràng buộc cốt lõi. Trong ứng dụng thật, cần quản lý producer lifecycle, đóng producer đúng cách, cấu hình bảo mật, timeout, serializer, metrics và xử lý callback/future. retries là số lần retry được phép, còn delivery.timeout.ms giới hạn tổng thời gian producer cố gắng giao record; không nên xem retries lớn là cho phép retry vô thời hạn.

Nếu muốn cấu hình an toàn theo thứ tự đơn giản nhất, có thể đặt max in-flight bằng 1. Khi idempotence đã bật, giá trị 1 vẫn hợp lệ nhưng thường không cần thiết nếu chưa có bằng chứng workload yêu cầu giới hạn pipelining thấp như vậy.

## 7. Cấu hình trong Spring Boot và Spring Kafka

Spring Kafka sử dụng Kafka producer client bên dưới. Cấu hình producer của Spring Boot được chuyển tới Kafka client thông qua ProducerFactory.

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1:9092
      - kafka-2:9092
      - kafka-3:9092
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Dấu ngoặc vuông giúp Spring Boot giữ nguyên tên thuộc tính Kafka có dấu chấm trong map properties. Kiểm tra cấu hình đã bind đúng với phiên bản Spring Boot đang dùng và không có cấu hình khác ghi đè ở Java Config.

Nếu dùng Java configuration để tạo ProducerFactory, có thể khai báo các property tương ứng trong map:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
props.put(
    ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
    5
);

ProducerFactory<String, String> producerFactory =
    new DefaultKafkaProducerFactory<>(props);

KafkaTemplate<String, String> kafkaTemplate =
    new KafkaTemplate<>(producerFactory);
~~~

Trong ứng dụng Spring, không cần tự tạo một KafkaProducer mới cho từng lần gửi. ProducerFactory và KafkaTemplate quản lý việc tạo, tái sử dụng producer theo cấu hình. Tạo quá nhiều producer độc lập có thể làm tăng số kết nối, bộ đệm, producer ID và chi phí tài nguyên.

### 7.1. Cấu hình key để giữ thứ tự theo thực thể

Ví dụ gửi sự kiện theo orderId:

~~~java
kafkaTemplate.send(
    "orders",
    orderId,
    orderCreatedEvent
);
~~~

Khi dùng key orderId, partitioner mặc định ánh xạ cùng key tới cùng partition trong điều kiện số partition và quy tắc partitioning không đổi. Các sự kiện của cùng order có thể giữ thứ tự trong partition.

Không nên gửi key null nếu cần thứ tự theo orderId. Cũng cần chú ý khi tăng số partition: phép ánh xạ key sang partition có thể thay đổi, khiến sự kiện mới của cùng key đi vào partition khác so với sự kiện cũ. Nếu thứ tự qua toàn bộ vòng đời thực thể là bắt buộc, cần có kế hoạch partitioning và migration phù hợp.

## 8. Các yếu tố khác ảnh hưởng tới ordering

max.in.flight chỉ là một phần trong thiết kế ordering. Có những nguyên nhân khác khiến ứng dụng quan sát sự kiện sai thứ tự.

### 8.1. Nhiều producer cùng ghi một partition

Hai producer độc lập không chia sẻ cùng sequence number hoặc một thứ tự gửi chung. Broker ghi theo thứ tự request được xử lý và append. Nếu hai service cùng ghi sự kiện cho một order, Kafka không tự suy ra sự kiện nào phải trước.

Giải pháp có thể là một producer owner cho thực thể, một luồng command tuần tự hóa, partitioning theo owner hoặc một cơ chế version/sequence nghiệp vụ để consumer phát hiện sự kiện đến muộn.

### 8.2. Producer gọi send đồng thời từ nhiều thread

KafkaProducer thread-safe, nhưng nhiều thread ứng dụng có thể gọi send đồng thời. Thứ tự được xác định bởi cách các record được đưa vào accumulator và gửi đi, không nhất thiết tương ứng với thứ tự thời gian nghiệp vụ mà các thread mong muốn.

Nếu cần thứ tự nghiệp vụ, hãy tuần tự hóa việc tạo/gửi sự kiện theo key hoặc mang theo version/sequence từ nguồn dữ liệu. Không dựa vào thời điểm hai thread bắt đầu gọi send để suy ra thứ tự mong muốn.

### 8.3. Partition count thay đổi

Partitioner mặc định thường ánh xạ key dựa trên số partition hiện tại. Khi tăng partition count, cùng một key có thể ánh xạ sang partition khác. Kafka không thể tạo một thứ tự liên partition giữa record cũ ở partition cũ và record mới ở partition mới.

Trước khi tăng partition cho topic có yêu cầu ordering theo key, hãy đánh giá ảnh hưởng và kế hoạch chuyển tiếp. Một lựa chọn là dùng partitioner tùy chỉnh hoặc thiết kế topic/version mới để quản lý migration.

### 8.4. Consumer xử lý song song hoặc commit không đúng thứ tự

Ngay cả khi broker lưu record đúng thứ tự, consumer có thể phá vỡ thứ tự quan sát ở tầng nghiệp vụ nếu dispatch record tới nhiều worker bất đồng bộ rồi ghi kết quả không tuần tự.

Ví dụ, consumer đọc sequence 10 rồi 11, nhưng worker xử lý 11 hoàn tất trước 10. Nếu hệ thống cập nhật trạng thái ngay khi mỗi worker xong, trạng thái cuối có thể phản ánh sai thứ tự.

Khi cần thứ tự, consumer cần xử lý tuần tự theo partition hoặc key, hoặc dùng cơ chế kiểm soát sequence/version ở tầng nghiệp vụ. Offset commit cũng phải phản ánh chính xác các record đã hoàn tất theo thứ tự cần thiết.

## 9. Retry, timeout và giới hạn thời gian giao record

Producer có nhiều cấu hình liên quan tới retry và thời gian giao record:

| Cấu hình | Vai trò |
|---|---|
| retries | Số lần producer có thể thử lại request lỗi có thể retry |
| request.timeout.ms | Thời gian client chờ response cho một request trước khi xem là timeout |
| delivery.timeout.ms | Tổng thời gian tối đa để producer giao record, gồm chờ batch, request và retry |
| retry.backoff.ms | Thời gian chờ giữa các lần retry |
| max.in.flight.requests.per.connection | Số request chưa nhận response tối đa trên một kết nối broker |

delivery.timeout.ms phải đủ lớn so với request timeout, linger và thời gian retry dự kiến. Trong Kafka client, cấu hình delivery timeout cần tương thích với request timeout và linger. Hãy kiểm tra tài liệu của đúng phiên bản client khi thay đổi các giới hạn này.

Khi một request timeout, producer có thể chưa biết broker đã append record hay chưa. Idempotence giúp retry cùng batch không tạo duplicate trong cơ chế producer session. Nhưng nếu hết delivery timeout, callback/future có thể báo lỗi cho ứng dụng; ứng dụng cần quyết định có phát lại nghiệp vụ bằng event ID mới hay thực hiện đối soát.

Không nên đặt timeout cực lớn để che giấu broker quá tải. Cần giám sát request latency, retry rate, buffer exhaustion và thời gian record nằm trong accumulator.

## 10. Đo lường hiệu năng khi thay đổi max in-flight

Để đánh giá tác động của max in-flight, không chỉ so sánh một con số throughput. Cần đo cả hiệu năng và tính đúng đắn.

Các chỉ số nên thu thập:

- Producer record-send rate và byte rate.
- Record error rate, retry rate và request timeout.
- Request latency trung bình và percentile cao (p95, p99).
- Buffer pool wait time và record queue time.
- Batch size trung bình, compression rate và request size.
- Broker request handler idle, network processor idle và replication lag.
- Thứ tự sequence quan sát được trong từng partition.

Một kế hoạch thử nghiệm có thể so sánh:

| Kịch bản | Idempotence | Max in-flight | Mục tiêu |
|---|---|---:|---|
| A | Tắt | 1 | Đường cơ sở với một request chờ |
| B | Tắt | 5 | Quan sát throughput và rủi ro retry ordering |
| C | Bật | 5 | Đo pipelining cùng bảo đảm idempotent |
| D | Bật | 1 | So sánh mức an toàn với giới hạn pipeline |

Để kiểm tra ordering, mỗi record nên mang key và sequence nghiệp vụ tăng dần. Consumer kiểm tra sequence trong từng partition, ghi nhận khoảng nhảy hoặc record đến sai thứ tự. Muốn quan sát rủi ro retry, cần tạo lỗi retryable có kiểm soát, ví dụ gián đoạn mạng giữa producer và broker trong môi trường thử nghiệm. Kết quả đảo thứ tự có thể phụ thuộc thời điểm lỗi, nên một lần chạy không đủ để chứng minh cấu hình an toàn.

Không thực hiện fault injection trên production chỉ để tái hiện tình huống. Dùng môi trường kiểm thử có thể khôi phục và giới hạn phạm vi tác động.

## 11. Quy tắc lựa chọn thực tế

Có thể dùng các nguyên tắc sau khi thiết kế producer:

1. **Mặc định ưu tiên idempotence.** Với producer hiện đại, bật tường minh enable.idempotence=true nếu ứng dụng cần retry an toàn.
2. **Giữ max in-flight không vượt 5 khi dùng idempotence.** Đây là giới hạn tương thích của cơ chế producer.
3. **Không hạ xuống 1 theo phản xạ.** Chỉ làm vậy khi cần giới hạn pipelining, tương thích hệ thống cũ hoặc có bằng chứng workload cần điều đó.
4. **Nếu idempotence tắt và retry bật, cân nhắc max in-flight bằng 1 khi ordering quan trọng.** Nếu để nhiều hơn 1, phải chấp nhận và xử lý nguy cơ đảo thứ tự.
5. **Chọn key theo phạm vi ordering nghiệp vụ.** Kafka bảo đảm thứ tự trong partition, vì vậy các record liên quan phải cùng partition.
6. **Đặt timeout theo SLA và khả năng phục hồi.** delivery.timeout.ms, request.timeout.ms và retry backoff cần nhất quán.
7. **Đo dưới lỗi và tải thực.** So sánh throughput, p99 latency, retry và ordering trong tình huống broker/network không hoàn hảo.
8. **Thiết kế consumer idempotent.** Producer idempotence không thay thế kiểm soát duplicate ở tầng nghiệp vụ hoặc side effect bên ngoài Kafka.

## 12. Tình huống tổng hợp

Order Service gửi các sự kiện cho cùng orderId=ORD-900:

~~~text
sequence 41: OrderCreated
sequence 42: PaymentAuthorized
sequence 43: OrderPacked
sequence 44: OrderShipped
~~~

Topic orders có nhiều partition và producer dùng orderId làm key. Các record của ORD-900 được ánh xạ vào cùng partition P2.

### Trường hợp A: Idempotence tắt, max in-flight bằng 5

Producer gửi batch chứa sequence 41 trước và batch chứa sequence 42 sau. Request đầu gặp lỗi retriable. Request sau có thể được broker xử lý thành công trước lần retry của request đầu. Nếu batch sau được append trước, thứ tự trong partition có thể là 42 rồi 41. Consumer nhận dữ liệu theo thứ tự log đã ghi, không tự biết thứ tự nghiệp vụ dự định.

### Trường hợp B: Idempotence bật, max in-flight bằng 5

Producer dùng PID và sequence number cho batch. Broker kiểm tra sequence theo partition. Khi producer retry batch cũ, broker nhận biết batch đã xử lý hoặc xác định sequence hợp lệ, tránh duplicate và duy trì thứ tự theo cơ chế idempotent. Nhiều request vẫn có thể đang bay, nên producer không cần giảm mặc định xuống một chỉ để giữ thứ tự retry.

### Trường hợp C: Idempotence tắt, max in-flight bằng 1

Producer chỉ có một request chưa hoàn tất trên kết nối. Nếu batch 41 cần retry, batch 42 chưa được gửi vượt lên trước trên kết nối đó. Cách này giữ thứ tự gửi trong chuỗi request nhưng giảm khả năng pipeline.

Dù chọn trường hợp nào, nếu một producer khác cũng gửi sự kiện cho ORD-900, hoặc partition count thay đổi khiến key ánh xạ sang partition khác, các cấu hình trên không tạo ra một thứ tự nghiệp vụ chung. Cần thiết kế ownership, key, version và consumer phù hợp.

## 13. Tự kiểm tra

**Câu 1.** max.in.flight.requests.per.connection giới hạn điều gì?

**Đáp án:** Số request đã gửi nhưng chưa nhận response trên mỗi kết nối producer tới một broker. Nó không giới hạn số record hoặc số partition.

**Câu 2.** Vì sao nhiều request in-flight có thể gây đảo thứ tự khi idempotence tắt?

**Đáp án:** Request cũ có thể gặp lỗi và phải retry trong khi request mới hơn đã được gửi và broker xử lý thành công. Retry của request cũ có thể được append sau request mới.

**Câu 3.** Đặt max in-flight bằng 1 có tác dụng gì?

**Đáp án:** Producer chờ request hiện tại hoàn tất trước khi gửi request tiếp theo trên kết nối đó, tránh request sau vượt request trước trong chuỗi retry; đổi lại pipelining và throughput có thể giảm.

**Câu 4.** Khi bật idempotence, max in-flight tối đa được hỗ trợ là bao nhiêu?

**Đáp án:** 5. Cấu hình idempotence còn yêu cầu acks=all và retries lớn hơn 0.

**Câu 5.** Producer ID và sequence number giúp ích gì?

**Đáp án:** Chúng giúp broker nhận diện producer và thứ tự batch theo partition, phát hiện retry trùng hoặc sequence không hợp lệ, từ đó tránh append duplicate do retry và giữ thứ tự trong phạm vi bảo đảm của idempotence.

**Câu 6.** Idempotent producer có bảo đảm một sự kiện nghiệp vụ chỉ được gửi đúng một lần trong mọi tình huống không?

**Đáp án:** Không. Nó bảo vệ retry của batch trong producer session. Ứng dụng vẫn cần event ID, idempotent consumer hoặc deduplication khi có lần gửi mới ở tầng nghiệp vụ.

**Câu 7.** Nếu producer dùng key orderId, Kafka có bảo đảm thứ tự của order trên toàn topic không?

**Đáp án:** Không. Thứ tự chỉ được bảo đảm trong partition. Key giúp các record cùng order đi vào cùng partition khi partitioning ổn định, nhưng không tạo thứ tự toàn cục giữa partition hoặc nhiều producer độc lập.

---

max.in.flight.requests.per.connection là một nút điều chỉnh sự cân bằng giữa pipelining và khả năng giữ thứ tự khi retry. Với Kafka producer hiện đại, idempotence cùng giới hạn tối đa năm request trên mỗi kết nối thường cho phép đạt throughput tốt mà vẫn bảo vệ thứ tự trong partition. Khi thiết kế, hãy kết hợp cấu hình này với key, partitioning, retry, timeout và cách consumer xử lý để bảo đảm thứ tự nghiệp vụ từ đầu tới cuối.

