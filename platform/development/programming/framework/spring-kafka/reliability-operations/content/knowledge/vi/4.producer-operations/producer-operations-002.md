# Producer interceptor

Trong Spring Kafka, **Producer interceptor** là điểm mở rộng của Kafka producer client để quan sát hoặc điều chỉnh bản ghi ở thời điểm gửi và nhận kết quả xác nhận. Interceptor chạy trong tiến trình producer, trước khi bản ghi được gửi qua mạng tới broker. Nó hữu ích cho các xử lý dùng chung như bổ sung correlation header, chuẩn hóa metadata kỹ thuật hoặc thu thập một số chỉ số gửi.

Producer interceptor thuộc API Kafka client (`org.apache.kafka.clients.producer.ProducerInterceptor`). Spring Kafka sử dụng Kafka producer ở bên dưới nên ứng dụng Spring Boot có thể cấu hình interceptor qua thuộc tính producer. Interceptor này không phải interceptor ở broker và cũng không phải `RecordInterceptor` của Spring Kafka ở phía consumer.

## 1. Vị trí của interceptor trong luồng gửi

Khi ứng dụng gọi `KafkaTemplate.send()`, Spring Kafka chuyển bản ghi cho Kafka producer. Kafka producer gọi các interceptor trước khi serialize và gửi record. Sau đó producer xác định partition, serialize key/value, đưa record vào batch và gửi request tới broker. Khi có kết quả xác nhận hoặc lỗi gửi, producer gọi callback của interceptor.

```text
Ứng dụng Spring
      |
      | KafkaTemplate.send(record)
      v
Kafka producer
      |
      v
ProducerInterceptor.onSend(record)
      |
      v
Serialize key/value và chọn partition
      |
      v
Batch và gửi request tới broker
      |
      v
Broker xử lý bản ghi
      |
      v
ProducerInterceptor.onAcknowledgement(metadata, exception)
      |
      v
Callback / future của lần gửi
```

`onSend()` chạy trên luồng gọi gửi record và có thể trả về một `ProducerRecord` mới. Bản ghi được trả về sẽ tiếp tục đi qua các interceptor tiếp theo và pipeline gửi của producer. `onAcknowledgement()` được gọi khi producer nhận xác nhận hoặc xác định lần gửi thất bại. Callback này có thể chạy trên luồng I/O của producer, vì vậy cần thực hiện nhanh và tránh chặn luồng.

Nếu cấu hình nhiều interceptor, Kafka gọi `onSend()` theo thứ tự danh sách cấu hình. Các callback xác nhận được gọi theo thứ tự ngược lại. Vì vậy, thứ tự interceptor có thể ảnh hưởng đến metadata mà interceptor sau nhìn thấy và cách các interceptor quan sát kết quả.

## 2. Các phương thức của ProducerInterceptor

Interface Kafka định nghĩa bốn phương thức chính:

| Phương thức | Thời điểm gọi | Trách nhiệm |
|---|---|---|
| `configure(Map<String, ?> configs)` | Khi Kafka tạo interceptor | Đọc cấu hình producer và khởi tạo tài nguyên cần thiết |
| `onSend(ProducerRecord<K, V> record)` | Trước khi producer serialize và gửi record | Quan sát hoặc trả về record đã điều chỉnh |
| `onAcknowledgement(RecordMetadata metadata, Exception exception)` | Khi lần gửi có kết quả thành công hoặc thất bại | Ghi nhận kết quả gửi và các chỉ số kỹ thuật |
| `close()` | Khi producer đóng interceptor | Giải phóng tài nguyên do interceptor sở hữu |

### 2.1. `configure()`

Kafka gọi `configure()` khi khởi tạo interceptor. Phương thức nhận map cấu hình của producer. Có thể đọc các tham số riêng của interceptor hoặc chuẩn bị đối tượng nội bộ. Không nên mở kết nối mạng, tải dữ liệu lớn hoặc thực hiện công việc kéo dài ở đây vì việc khởi tạo producer có thể bị chậm.

Kafka client thường tự khởi tạo interceptor từ tên lớp được khai báo trong `interceptor.classes`. Vì vậy, cách cấu hình thông thường cần một constructor không tham số và không nên giả định interceptor tự động là Spring bean có thể inject các dependency bằng `@Autowired`.

### 2.2. `onSend()`

`onSend()` nhận record trước khi serialize. Đây là vị trí phù hợp để bổ sung header kỹ thuật, ví dụ correlation ID nếu bản ghi chưa có. Phương thức có thể trả lại record ban đầu hoặc tạo record mới với metadata đã điều chỉnh.

Nên giữ `onSend()` nhẹ, xác định và không có side effect bên ngoài. Không gọi database, REST API, dịch vụ định danh hoặc hệ thống log từ xa theo kiểu đồng bộ trong phương thức này. Mỗi lần gửi đều đi qua đường xử lý này, vì vậy một thao tác chậm sẽ trực tiếp làm tăng latency gửi và giảm throughput.

Việc thay đổi key hoặc partition có thể làm thay đổi nơi lưu record và thứ tự quan sát được của nghiệp vụ. Chỉ thay đổi các trường đó khi có quy tắc routing rõ ràng. Không nên dùng interceptor để âm thầm sửa payload nghiệp vụ.

### 2.3. `onAcknowledgement()`

Phương thức nhận `RecordMetadata` khi gửi thành công và `Exception` khi gửi thất bại. Khi thành công, metadata có thể cho biết topic, partition, offset và timestamp của record. Khi thất bại, metadata có thể không có giá trị; cần kiểm tra `exception` trước khi đọc metadata.

Đây là nơi phù hợp để cập nhật counter hoặc ghi nhận kết quả kỹ thuật ở mức nhẹ. Không thực hiện retry thủ công trong callback này. Retry của producer đã được điều khiển bởi cấu hình Kafka producer như `retries` và `delivery.timeout.ms`; việc tự gửi lại trong callback có thể tạo vòng lặp hoặc nhân đôi tải.

Với producer dùng transaction, callback xác nhận của một record không đồng nghĩa giao dịch chứa record đó đã commit. Record có thể được broker xác nhận ở cấp produce request nhưng transaction sau đó vẫn có thể bị abort. Nếu cần biết kết quả commit của transaction, hãy theo dõi kết quả transaction ở tầng quản lý transaction của ứng dụng.

### 2.4. `close()`

Kafka gọi `close()` khi producer đóng. Nếu interceptor sở hữu tài nguyên như executor hoặc registry riêng, cần giải phóng chúng tại đây. Tránh tạo thread hoặc client riêng nếu không thực sự cần; tài nguyên dùng chung thường nên được quản lý bởi ứng dụng và vòng đời của Spring.

## 3. Ví dụ: bổ sung correlation ID vào header

Giả sử các sự kiện đi qua nhiều dịch vụ và đội vận hành cần tìm các log liên quan đến cùng một luồng xử lý. Producer interceptor có thể bổ sung header `x-correlation-id` khi record chưa có header này. Nếu ứng dụng đã truyền correlation ID từ request hoặc upstream, interceptor giữ nguyên giá trị đó.

```java
package com.example.kafka;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;

public class CorrelationIdProducerInterceptor
        implements ProducerInterceptor<String, String> {

    private static final String HEADER_NAME = "x-correlation-id";

    @Override
    public ProducerRecord<String, String> onSend(
            ProducerRecord<String, String> record) {

        Headers headers = new RecordHeaders(record.headers());

        if (headers.lastHeader(HEADER_NAME) == null) {
            String correlationId = UUID.randomUUID().toString();
            headers.add(
                    HEADER_NAME,
                    correlationId.getBytes(StandardCharsets.UTF_8));
        }

        return new ProducerRecord<>(
                record.topic(),
                record.partition(),
                record.timestamp(),
                record.key(),
                record.value(),
                headers);
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {

        if (exception != null) {
            // Cập nhật counter lỗi bằng thao tác thread-safe, không block.
            return;
        }

        if (metadata != null) {
            // Có thể ghi nhận topic/partition/offset vào metric nhẹ.
        }
    }

    @Override
    public void configure(Map<String, ?> configs) {
        // Không cần cấu hình bổ sung trong ví dụ này.
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên riêng nếu interceptor có sở hữu.
    }
}
```

Ví dụ sao chép headers sang `RecordHeaders` mới để thêm metadata mà không sửa trực tiếp collection header của record đầu vào. Constructor `ProducerRecord` giữ lại topic, partition, timestamp, key và value ban đầu. Nếu correlation ID đã tồn tại, interceptor không ghi đè.

Trong production, cần quyết định rõ cách tạo correlation ID. Nếu mỗi record được phát sinh từ cùng một request nghiệp vụ, ID nên được tạo ở tầng request hoặc event và truyền qua các dịch vụ. Việc tự tạo UUID trong interceptor chỉ là phương án dự phòng khi không có ID. Nếu mỗi record trong một batch tự nhận UUID riêng, chúng sẽ không còn cùng một correlation ID dù xuất phát từ cùng một thao tác nghiệp vụ.

## 4. Đăng ký interceptor trong Spring Boot

Khai báo lớp interceptor trong cấu hình producer của Spring Boot. Ví dụ dưới đây dùng serializer chuỗi để minh họa:

```properties
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.properties[interceptor.classes]=com.example.kafka.CorrelationIdProducerInterceptor
```

Thuộc tính `interceptor.classes` là cấu hình Kafka producer. Có thể khai báo nhiều lớp bằng danh sách tên lớp phân tách bằng dấu phẩy. Mỗi interceptor phải tương thích với kiểu key/value mà producer sử dụng và phải có thể được Kafka client khởi tạo.

Với ứng dụng có nhiều `ProducerFactory` hoặc nhiều `KafkaTemplate`, cần xác minh cấu hình interceptor được áp dụng cho đúng producer factory. Một producer được tạo từ factory khác có thể không dùng interceptor này. Việc khai báo ở một cấu hình producer không tự động tác động đến mọi Kafka producer trong JVM.

Sau khi cấu hình, có thể kiểm tra bằng cách gửi một record không có `x-correlation-id` và xác nhận header xuất hiện ở consumer hoặc công cụ đọc Kafka. Tiếp tục gửi một record đã có header để xác nhận interceptor giữ nguyên giá trị. Kiểm tra cả đường gửi lỗi để chắc chắn callback lỗi không gây exception thứ cấp hoặc làm nghẽn producer.

## 5. Producer interceptor, ProducerListener và RecordInterceptor

Spring Kafka cung cấp một số điểm mở rộng có tên gần nhau nhưng chạy ở các giai đoạn khác nhau. Chọn đúng cơ chế giúp tránh đưa logic vào sai tầng.

| Cơ chế | Vị trí | Trường hợp phù hợp |
|---|---|---|
| Kafka `ProducerInterceptor` | Bên trong Kafka producer client, trước gửi và khi nhận kết quả gửi | Bổ sung header kỹ thuật, quan sát producer ở mức client |
| Spring Kafka `ProducerListener` | Callback của `KafkaTemplate` khi gửi thành công hoặc thất bại | Xử lý kết quả gửi trong ứng dụng Spring, sử dụng dependency Spring-managed |
| Spring Kafka `RecordInterceptor` | Phía consumer listener container, trước khi gọi listener | Quan sát hoặc điều chỉnh record trước khi listener xử lý |
| `KafkaTemplate` callback / `CompletableFuture` | Tại từng lệnh gửi của ứng dụng | Xử lý kết quả riêng cho một thao tác gửi |

### 5.1. Khi cần dependency do Spring quản lý

Kafka client tạo `ProducerInterceptor` theo cấu hình producer. Vì thế, không nên đặt logic phụ thuộc vào repository, service hoặc bean Spring bên trong interceptor rồi giả định Spring sẽ inject tự động. Nếu cần sử dụng dependency do Spring quản lý để xử lý kết quả gửi, `ProducerListener` thường phù hợp hơn.

Ví dụ listener:

```java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.ProducerListener;

public class OrderProducerListener
        implements ProducerListener<String, OrderCreated> {

    @Override
    public void onSuccess(
            ProducerRecord<String, OrderCreated> record,
            RecordMetadata metadata) {
        // Ghi nhận kết quả gửi thành công bằng các bean của ứng dụng
        // sau khi listener được đăng ký với KafkaTemplate.
    }

    @Override
    public void onError(
            ProducerRecord<String, OrderCreated> record,
            RecordMetadata metadata,
            Exception exception) {
        // Ghi nhận lỗi gửi và kích hoạt xử lý phù hợp ở tầng ứng dụng.
    }
}
```

Đăng ký listener trên `KafkaTemplate` đang sử dụng. Ví dụ cấu hình tường minh:

```java
@Configuration
class OrderKafkaConfiguration {

    @Bean
    ProducerListener<String, OrderCreated> orderProducerListener() {
        return new OrderProducerListener();
    }

    @Bean
    KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory,
            ProducerListener<String, OrderCreated> producerListener) {
        KafkaTemplate<String, OrderCreated> template =
                new KafkaTemplate<>(producerFactory);
        template.setProducerListener(producerListener);
        return template;
    }
}
```

Ví dụ này tạo một `KafkaTemplate` tường minh từ `ProducerFactory` và gắn listener vào template đó. Trong ứng dụng đang dùng `KafkaTemplate` tự động cấu hình bởi Spring Boot, hãy gắn listener vào template hiện có hoặc tùy chỉnh bean theo cấu trúc ứng dụng. Không tạo thêm một `KafkaTemplate` ngoài ý muốn chỉ để đăng ký listener. Các callback vẫn nên ngắn gọn vì chúng được thực thi trên đường hoàn tất gửi của producer.

### 5.2. Khi cần xử lý record ở phía consumer

`RecordInterceptor` của Spring Kafka được gắn với listener container và chạy trước listener method. Nó có thể dùng để bổ sung context cho quá trình tiêu thụ hoặc bỏ qua record theo quy tắc được thiết kế. Nó không can thiệp vào record đang được producer gửi. Không nhầm `RecordInterceptor` với Kafka `ProducerInterceptor` chỉ vì cả hai đều có từ interceptor trong tên.

## 6. Những giới hạn cần hiểu rõ

### 6.1. Interceptor không thay thế xác nhận gửi

`onSend()` được gọi trước khi broker xác nhận. Việc interceptor chạy xong chỉ cho biết record đã đi qua hook phía client; nó không chứng minh broker đã lưu record. Ứng dụng vẫn phải xử lý future/callback từ `KafkaTemplate.send()` hoặc `ProducerListener` để biết kết quả gửi.

Tương tự, `onAcknowledgement()` chỉ cung cấp kết quả ở cấp record produce request. Khi bật Kafka transaction, callback thành công cho record không phải bằng chứng transaction đã commit. Cần theo dõi kết quả transaction riêng.

### 6.2. Không dùng exception để từ chối record

Kafka producer bắt và ghi log exception phát sinh từ các phương thức interceptor để tránh interceptor làm hỏng luồng gửi của client. Do đó, ném exception trong `onSend()` không phải cách đáng tin cậy để từ chối một record hoặc áp dụng validation bắt buộc. Nếu dữ liệu không hợp lệ, hãy kiểm tra ở tầng service/domain trước khi gọi `KafkaTemplate.send()` và trả lỗi rõ ràng cho caller.

### 6.3. Không bảo đảm exactly-once cho side effect

Interceptor không làm cho thao tác gửi, ghi database hoặc gọi dịch vụ ngoài Kafka trở thành một giao dịch nguyên tử. Việc thêm event ID hoặc correlation ID vào header cũng không tự khử trùng. Nếu consumer nhận lại cùng một event, hệ thống đích vẫn cần idempotency hoặc cơ chế deduplication phù hợp.

Nếu cần exactly-once trong luồng Kafka-to-Kafka, phải cấu hình và sử dụng Kafka transactions đúng cách, đồng thời consumer đọc với `read_committed`. Nếu có side effect bên ngoài Kafka, hãy thiết kế outbox/inbox hoặc cơ chế nhất quán tương ứng ở tầng nghiệp vụ.

### 6.4. Không làm nghẽn luồng producer

`onSend()` nằm trên đường gửi đồng bộ của client; xử lý lâu làm chậm các lần gửi. `onAcknowledgement()` có thể chạy trên luồng I/O; chặn luồng này có thể trì hoãn xử lý các phản hồi khác. Không thực hiện các công việc sau trong interceptor:

- Gọi REST API, database hoặc dịch vụ bên ngoài theo cách đồng bộ.
- Chờ khóa lâu, sleep hoặc chờ future hoàn tất.
- Serialize lại payload lớn nếu không có yêu cầu rõ ràng.
- Ghi log toàn bộ payload cho mọi record ở lưu lượng cao.
- Tạo retry riêng hoặc gửi record mới trong callback xác nhận.

Nếu cần xử lý bất đồng bộ, hãy cân nhắc hàng đợi nội bộ có giới hạn và chính sách khi đầy. Không tạo executor không giới hạn trong interceptor vì backlog của executor có thể trở thành một nguồn cạn bộ nhớ mới.

### 6.5. Bảo vệ metadata và dữ liệu nhạy cảm

Header Kafka được truyền cùng record và có thể được nhiều consumer, công cụ quan sát hoặc hệ thống lưu trữ đọc. Không đưa access token, mật khẩu, session secret hoặc dữ liệu cá nhân không cần thiết vào header. Correlation ID nên là mã định danh kỹ thuật, không chứa thông tin bí mật.

Khi sửa header, cần giữ lại các header có sẵn và tránh thêm lặp một giá trị nếu quy ước của hệ thống yêu cầu duy nhất. Cũng cần thống nhất encoding, tên header và cách xử lý khi upstream gửi giá trị không hợp lệ.

## 7. Quan sát và xử lý lỗi

Interceptor có thể bổ sung tín hiệu về kết quả gửi, nhưng cần phối hợp với metric của Kafka producer và metric nghiệp vụ. Các chỉ số nên quan sát gồm:

- Số lần gửi thành công và thất bại.
- Tỷ lệ lỗi theo topic và loại exception.
- Thời gian gửi hoặc thời gian xác nhận ở phía producer.
- Số lần retry và các lỗi timeout.
- Số record được bổ sung correlation header dự phòng.

Không nên dùng event ID, correlation ID hoặc key có độ phân biệt cao làm label metric vì sẽ tạo cardinality lớn. Dùng metric có nhãn giới hạn như application, cluster, topic và kết quả; lưu ID chi tiết trong log hoặc trace có kiểm soát.

Một số tình huống thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Header không xuất hiện | Producer đang dùng factory khác; interceptor chưa được đăng ký; record được gửi qua producer khác | Kiểm tra cấu hình `interceptor.classes` trên đúng producer factory và kiểm tra record ở consumer |
| Header bị ghi đè hoặc lặp | Interceptor không kiểm tra header hiện có; nhiều interceptor cùng sửa một header | Thống nhất quy tắc sở hữu header, kiểm tra trước khi thêm và kiểm tra thứ tự interceptor |
| Gửi record chậm sau khi thêm interceptor | `onSend()` làm việc nặng hoặc chờ I/O | Loại bỏ xử lý blocking, đo thời gian hook và chuyển logic nghiệp vụ sang tầng khác |
| Exception trong interceptor nhưng record vẫn được gửi | Kafka client bắt exception của interceptor để bảo vệ pipeline gửi | Thực hiện validation bắt buộc trước `KafkaTemplate.send()`; không dùng exception interceptor làm cơ chế từ chối |
| Metric thành công nhưng transaction bị abort | Callback xác nhận record không phản ánh kết quả commit cuối cùng của transaction | Theo dõi kết quả transaction riêng và chỉ công bố nghiệp vụ sau khi transaction commit |
| Không inject được Spring bean | Kafka client tự tạo interceptor từ cấu hình lớp | Dùng interceptor nhẹ không phụ thuộc Spring hoặc dùng `ProducerListener`/callback được quản lý bởi Spring |

Khi điều tra, cần phân biệt lỗi ở hook interceptor với lỗi serialize, lỗi kết nối, lỗi broker và lỗi nghiệp vụ. Interceptor không thể sửa lỗi broker từ phía client; metric và exception cần giữ đủ thông tin để xác định đúng tầng gây lỗi.

## 8. Kiểm thử interceptor

Kiểm thử nên tập trung vào hành vi mà interceptor chịu trách nhiệm, đồng thời giữ kiểm thử tích hợp cho cấu hình Kafka producer.

### 8.1. Kiểm thử đơn vị cho `onSend()`

Các trường hợp cần kiểm tra:

1. Record chưa có correlation ID: kết quả có header hợp lệ.
2. Record đã có correlation ID: giá trị hiện tại được giữ nguyên.
3. Record có các header khác: các header đó vẫn tồn tại sau khi interceptor chạy.
4. Topic, partition, timestamp, key và value: không thay đổi ngoài quy tắc đã thiết kế.
5. Header encoding: giá trị được mã hóa và giải mã theo cùng chuẩn, ví dụ UTF-8.

Ví dụ kiểm tra ý tưởng với JUnit:

```java
@Test
void addsCorrelationIdWhenMissing() {
    CorrelationIdProducerInterceptor interceptor =
            new CorrelationIdProducerInterceptor();

    ProducerRecord<String, String> input =
            new ProducerRecord<>("orders", "order-42", "created");

    ProducerRecord<String, String> output = interceptor.onSend(input);

    Header header = output.headers().lastHeader("x-correlation-id");
    assertNotNull(header);
    assertFalse(new String(header.value(), StandardCharsets.UTF_8).isBlank());
    assertEquals("orders", output.topic());
    assertEquals("order-42", output.key());
    assertEquals("created", output.value());
}
```

Nếu phiên bản Java của dự án chưa hỗ trợ `String.isBlank()`, có thể dùng `trim().isEmpty()` trong assertion. Bài kiểm thử đơn vị không cần kết nối Kafka vì chỉ kiểm tra biến đổi record trong interceptor.

### 8.2. Kiểm thử tích hợp

Khởi tạo producer với cấu hình `interceptor.classes` trong môi trường Kafka kiểm thử. Gửi record qua `KafkaTemplate`, đọc record từ topic và xác nhận header được broker lưu cùng record. Kiểm tra cả record có header sẵn, record không có header và đường gửi thất bại.

Nếu ứng dụng có nhiều producer factory, hãy kiểm tra từng factory liên quan. Một kiểm thử trên factory mặc định không chứng minh producer cho luồng khác đã đăng ký interceptor. Với transaction, bổ sung trường hợp commit và abort để bảo đảm metric hoặc log của ứng dụng không nhầm lẫn giữa xác nhận record và kết quả transaction.

## 9. Nguyên tắc thiết kế khi đưa vào production

Một interceptor production nên có phạm vi nhỏ, hành vi dễ dự đoán và chi phí thực thi thấp. Trước khi triển khai, hãy thống nhất các nguyên tắc sau:

1. Chỉ dùng interceptor cho metadata kỹ thuật hoặc quan sát chung của producer.
2. Tạo correlation ID ở tầng request/event khi có thể; interceptor chỉ bổ sung giá trị dự phòng.
3. Không phụ thuộc Spring dependency injection trong interceptor do Kafka client tự khởi tạo.
4. Không dùng exception interceptor để validation hoặc từ chối record.
5. Không thực hiện I/O blocking trong `onSend()` hay `onAcknowledgement()`.
6. Không coi callback xác nhận record là kết quả commit của transaction.
7. Giữ nguyên key, partition, timestamp, payload và header hiện có trừ khi có quy tắc được phê duyệt.
8. Theo dõi hiệu năng producer trước và sau khi bật interceptor; có thể tắt cấu hình interceptor để khoanh vùng sự cố nếu cần.
9. Kiểm tra mọi `ProducerFactory` thực sự gửi dữ liệu cho topic cần áp dụng.
10. Không đưa bí mật hoặc dữ liệu nhạy cảm vào header và metric label.

Producer interceptor là một hook nhỏ trong vòng đời gửi của Kafka client. Khi dùng đúng phạm vi, nó giúp chuẩn hóa metadata và tăng khả năng quan sát cho các luồng Spring Kafka. Các yêu cầu về validation nghiệp vụ, retry, idempotency, giao dịch và xử lý kết quả gửi vẫn cần được giải quyết ở những tầng có trách nhiệm tương ứng.
