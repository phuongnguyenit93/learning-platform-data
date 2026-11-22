# Test producer send failure

## Mục tiêu và phạm vi

Kiểm thử producer send failure nhằm chứng minh ứng dụng phát hiện đúng lỗi khi gửi bản ghi lên Kafka, truyền lỗi tới đúng tầng xử lý, áp dụng retry có giới hạn khi phù hợp và không báo thành công khi broker chưa xác nhận việc gửi. Một bài test đáng tin cậy phải phân biệt được lỗi xảy ra ngay trong lời gọi `send()`, lỗi được trả về bất đồng bộ qua future/callback và lỗi chỉ xuất hiện khi transaction commit.

Nội dung tập trung vào Spring for Apache Kafka với `KafkaTemplate`, `ProducerFactory` và Kafka producer client. Các ví dụ chính dùng Spring Kafka 3.x, Java 17+, JUnit 5, Mockito và AssertJ. Từ Spring Kafka 3.0, các phương thức `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K,V>>`. Những phiên bản cũ hơn dùng `ListenableFuture`; xem phần tương thích phiên bản trước khi áp dụng mã kiểm thử.

Mục tiêu kiểm thử:

- Phân biệt lỗi tạo producer, lỗi serialize, lỗi gọi producer và lỗi broker trả về sau khi gửi.
- Xác nhận future hoàn tất thành công hoặc thất bại đúng với kết quả gửi.
- Kiểm tra ứng dụng ghi nhận lỗi, phát metric/log phù hợp và không nuốt exception.
- Xác nhận retry có giới hạn, đúng loại exception và không tạo duplicate ngoài mong muốn.
- Kiểm tra timeout, transaction abort/commit và hành vi khi broker hoặc network không khả dụng.
- Giữ test ổn định, có thời hạn chờ hữu hạn và không phụ thuộc vào sleep ngẫu nhiên.

## 1. Mô hình lỗi của producer send

Một lần gửi qua `KafkaTemplate` có nhiều giai đoạn. Vị trí lỗi quyết định lỗi được ném ngay hay hoàn tất future bằng exception.

~~~text
Ứng dụng
   |
   | KafkaTemplate.send(...)
   v
Tạo ProducerRecord / lấy Producer từ ProducerFactory
   |
   +---- lỗi cục bộ: cấu hình, serializer, tạo producer,
   |     metadata/buffer chờ quá lâu
   |        -> có thể ném exception đồng bộ
   |
   v
KafkaProducer.send(record, callback)
   |
   +---- lỗi khi gửi / broker từ chối / network / timeout
   |        -> callback nhận exception
   |        -> CompletableFuture hoàn tất exceptionally
   |
   v
Broker xác nhận theo cấu hình acks
   |
   +---- thành công -> SendResult và RecordMetadata
   |
   +---- transaction chưa commit -> kết quả send chưa phải kết quả commit
~~~

Các nhóm lỗi thường gặp:

| Nhóm | Ví dụ | Cách quan sát thường gặp |
|---|---|---|
| Lỗi đầu vào | Topic rỗng, key/value không hợp lệ, header sai | Có thể phát sinh ngay khi tạo record hoặc gọi send |
| Lỗi serializer | Schema sai, serializer ném exception, payload không encode được | Có thể phát sinh đồng bộ hoặc trong quá trình producer xử lý send |
| Lỗi khởi tạo producer | Cấu hình sai, authentication/TLS sai, không tạo được producer | Có thể ném exception trước khi future được trả về |
| Lỗi metadata/buffer | Không lấy được metadata, buffer producer đầy và chờ quá `max.block.ms` | Lời gọi send có thể block rồi ném exception |
| Broker từ chối | Authorization, record quá lớn, topic/partition không hợp lệ | Thường được chuyển thành lỗi bất đồng bộ qua callback/future |
| Lỗi network | Broker mất kết nối, request timeout, leader thay đổi | Client có thể retry nội bộ rồi mới báo lỗi cuối cùng |
| Delivery timeout | Không giao được record trong `delivery.timeout.ms` | Future thất bại sau khi client hết thời gian giao |
| Transaction | Gửi trong transaction nhưng commit/abort thất bại | Send có thể thành công riêng lẻ, transaction vẫn không commit |

Không giả định mọi exception đều xuất hiện cùng một cách. Hành vi cụ thể phụ thuộc phiên bản Kafka client, Spring Kafka, serializer, producer configuration và thời điểm lỗi.

### 1.1. Lỗi đồng bộ và lỗi bất đồng bộ

**Lỗi đồng bộ** xảy ra trước khi producer có thể nhận bản ghi để gửi, hoặc trong lúc lấy producer/metadata/buffer. Ví dụ: `ProducerFactory.createProducer()` ném lỗi, cấu hình serializer sai hoặc producer không thể lấy metadata trong giới hạn chờ. Trong trường hợp này, lời gọi `KafkaTemplate.send()` có thể ném exception trước khi trả future.

**Lỗi bất đồng bộ** xảy ra sau khi lệnh gửi đã được chấp nhận vào luồng xử lý của producer. Ví dụ broker từ chối record, network không phục hồi được hoặc hết delivery timeout. Ứng dụng nhận lỗi qua callback và future của `KafkaTemplate` hoàn tất exceptionally.

Với Spring Kafka 3.x, cần xử lý cả hai đường đi. Chỉ gọi `future.get()` không thể bắt một exception đã ném trước khi biến future được gán. Ngược lại, chỉ bọc lời gọi `send()` bằng try/catch sẽ bỏ sót lỗi bất đồng bộ nếu ứng dụng không quan sát future.

### 1.2. Ý nghĩa của kết quả gửi

`SendResult<K,V>` chứa bản ghi đã gửi và `RecordMetadata` khi producer nhận xác nhận thành công theo cấu hình `acks`. Metadata cung cấp topic, partition, offset và timestamp theo thông tin broker trả về.

Kết quả thành công của một lần gửi không tự động chứng minh consumer đã xử lý bản ghi hoặc nghiệp vụ downstream đã hoàn tất. Nếu gửi trong transaction, kết quả send cũng chưa chứng minh transaction đã commit. Test cần xác định rõ điều gì là tiêu chí thành công của component đang kiểm tra.

## 2. Chuẩn bị môi trường kiểm thử

### 2.1. Dependency kiểm thử

Ví dụ dependency Maven thường dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án không dùng Spring Boot dependency management, khai báo phiên bản tương thích cho Spring Kafka, Kafka client, JUnit, Mockito và AssertJ. Tránh ép một phiên bản Kafka client khác với phiên bản được Spring Kafka quản lý nếu chưa xác minh tương thích.

### 2.2. Chọn đúng loại test

| Loại test | Thành phần thật | Dùng để kiểm tra |
|---|---|---|
| Unit test service | Mock `KafkaTemplate` | Ứng dụng phản ứng với future lỗi hoặc exception đồng bộ |
| Test `KafkaTemplate` với `MockProducer` | `KafkaTemplate` thật, producer giả lập | Callback, future, metadata và đường đi lỗi của template |
| Integration test với broker | Kafka broker thật trong test | Serializer, cấu hình client, topic, ACL và round-trip thực tế |
| Fault-injection test | Broker thật cộng proxy/fault injector | Network partition, broker mất kết nối, timeout và phục hồi |

Mỗi lớp trả lời một câu hỏi khác nhau. Unit test không chứng minh Kafka client xử lý network failure đúng; integration test thành công cũng không chứng minh service không nuốt lỗi. Kết hợp các lớp theo rủi ro của ứng dụng.

## 3. Thiết kế component để kiểm thử được

Một publisher nên trả kết quả bất đồng bộ cho caller hoặc chuyển lỗi tới một cơ chế xử lý có thể quan sát. Không bỏ future nếu kết quả gửi ảnh hưởng tới nghiệp vụ.

~~~java
@Service
public class OrderPublisher {

    private static final String TOPIC = "orders";

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
~~~

Nếu component cần log hoặc cập nhật metric, có thể gắn callback nhưng vẫn giữ nguyên trạng thái thất bại của future:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        OrderEvent event) {
    return kafkaTemplate.send(TOPIC, event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception == null) {
                    // Tăng metric send success; không log payload nhạy cảm.
                    sendSuccessCounter.increment();
                }
                else {
                    // Ghi nhận lỗi và context tối thiểu để điều tra.
                    sendFailureCounter.increment();
                    log.warn("Could not publish order event, orderId={}",
                            event.orderId(), exception);
                }
            });
}
~~~

`whenComplete` giữ nguyên kết quả thành công/thất bại của stage nguồn nếu callback hoàn tất bình thường. Nếu callback tự ném exception, stage được trả về cũng có thể thất bại vì lỗi callback. Không dùng `exceptionally(ex -> null)` chỉ để làm future trở thành thành công; cách đó che mất send failure.

Nếu API nghiệp vụ cần hợp đồng thống nhất rằng mọi lỗi đều được biểu diễn bằng future, có thể chuyển exception đồng bộ thành failed future:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publishSafely(
        OrderEvent event) {
    try {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
    catch (RuntimeException exception) {
        return CompletableFuture.failedFuture(exception);
    }
}
~~~

Chỉ áp dụng cách này khi caller được thiết kế để quan sát future. Không bắt `Throwable`, không biến lỗi thành kết quả thành công và không bỏ qua lỗi cấu hình cần fail fast khi khởi động.

## 4. Unit test service với KafkaTemplate được mock

Unit test tập trung vào hành vi của ứng dụng: truyền đúng topic/key/value, trả lại lỗi gửi cho caller và không đánh dấu thành công khi future thất bại.

### 4.1. Kiểm tra lỗi bất đồng bộ

Ví dụ dùng JUnit 5, Mockito và AssertJ:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @InjectMocks
    OrderPublisher publisher;

    @Test
    void propagatesAsynchronousSendFailure() {
        OrderEvent event = new OrderEvent("order-42");
        var sendFuture =
                new CompletableFuture<SendResult<String, OrderEvent>>();

        when(kafkaTemplate.send("orders", "order-42", event))
                .thenReturn(sendFuture);

        CompletableFuture<SendResult<String, OrderEvent>> result =
                publisher.publish(event);

        assertThat(result).isNotNull();
        assertThat(result.isDone()).isFalse();

        sendFuture.completeExceptionally(
                new org.apache.kafka.common.errors.TimeoutException(
                        "simulated broker timeout"));

        assertThatThrownBy(result::join)
                .isInstanceOf(CompletionException.class)
                .hasCauseInstanceOf(
                        org.apache.kafka.common.errors.TimeoutException.class);

        verify(kafkaTemplate).send("orders", "order-42", event);
    }
}
~~~

Test chủ động hoàn tất future bằng exception, không cần khởi động broker hoặc chờ timeout thật. Nếu publisher gắn callback để ghi metric, bổ sung assertion rằng failure counter tăng và success counter không tăng.

Lưu ý: `join()` bọc lỗi bất đồng bộ trong `CompletionException`; `get()` bọc trong `ExecutionException`. Khi kiểm tra loại exception, hãy xét cause hoặc unwrap wrapper. Không khẳng định mọi lỗi đều có cùng một wrapper nếu đường đi lỗi có thể ném đồng bộ.

### 4.2. Kiểm tra exception đồng bộ khi gọi send

Mock `KafkaTemplate` có thể ném exception ngay từ lời gọi:

~~~java
@Test
void exposesSynchronousSendInvocationFailure() {
    OrderEvent event = new OrderEvent("order-42");

    when(kafkaTemplate.send("orders", "order-42", event))
            .thenThrow(new KafkaException("producer is unavailable"));

    assertThatThrownBy(() -> publisher.publish(event))
            .isInstanceOf(KafkaException.class)
            .hasMessageContaining("producer is unavailable");
}
~~~

Test này phù hợp nếu publisher giữ nguyên hợp đồng của `KafkaTemplate` và để exception đồng bộ truyền ra. Nếu publisher đã chuyển lỗi đồng bộ thành failed future bằng `publishSafely()`, kiểm tra future trả về thất bại:

~~~java
@Test
void convertsSynchronousFailureToFailedFutureWhenApiRequiresIt() {
    OrderEvent event = new OrderEvent("order-42");

    when(kafkaTemplate.send("orders", "order-42", event))
            .thenThrow(new KafkaException("producer is unavailable"));

    CompletableFuture<SendResult<String, OrderEvent>> result =
            publisher.publishSafely(event);

    assertThat(result.isCompletedExceptionally()).isTrue();
    assertThatThrownBy(result::join)
            .isInstanceOf(CompletionException.class)
            .hasCauseInstanceOf(KafkaException.class);
}
~~~

Hai ví dụ thể hiện hai hợp đồng API khác nhau. Chọn một hợp đồng phù hợp với ứng dụng và giữ nhất quán cho caller.

### 4.3. Kiểm tra không nuốt lỗi trong callback

Nếu publisher thực hiện metric/log trong `whenComplete`, hãy kiểm tra:

- Future trả về vẫn thất bại khi future gốc thất bại.
- Metric failure được cập nhật đúng một lần cho mỗi lần gửi thất bại.
- Metric success không tăng khi gửi lỗi.
- Callback không log payload, credential hoặc dữ liệu nhạy cảm.
- Một exception trong code ghi metric không làm mất nguyên nhân send failure.

Không chỉ verify rằng `kafkaTemplate.send()` đã được gọi. Assertion quan trọng là caller quan sát được kết quả đúng.

### 4.4. Kiểm tra exception được phân loại đúng

Nếu ứng dụng phân loại lỗi thành retryable và non-retryable, kiểm tra từng nhóm bằng parameterized test:

~~~java
@ParameterizedTest
@MethodSource("nonRetryableFailures")
void doesNotRetryPermanentSendFailures(RuntimeException failure) {
    // Arrange: publisher nhận failure từ KafkaTemplate.
    // Act: kích hoạt đường xử lý lỗi.
    // Assert: không lên lịch retry và trả lỗi cho caller.
}

static Stream<Arguments> nonRetryableFailures() {
    return Stream.of(
            Arguments.of(new SerializationException("bad payload")),
            Arguments.of(new RecordTooLargeException("record too large")),
            Arguments.of(new AuthorizationException("not authorized"))
    );
}
~~~

Đây là khung minh họa; constructor và loại exception cụ thể cần khớp Kafka client version của dự án. Chỉ retry các lỗi tạm thời mà policy đã cho phép. Không retry vô hạn lỗi schema, authorization hoặc payload không thể gửi.

## 5. Kiểm thử KafkaTemplate bằng MockProducer

`MockProducer` thuộc Kafka client, cho phép kiểm soát lần gửi tiếp theo và kết quả callback mà không cần broker. Kết hợp `MockProducer` với `KafkaTemplate` thật để kiểm tra cách Spring Kafka chuyển kết quả producer thành `CompletableFuture<SendResult<...>>`.

### 5.1. Tạo ProducerFactory trả về MockProducer

Ví dụ dưới đây dùng Mockito để cung cấp producer giả lập:

~~~java
@SuppressWarnings("unchecked")
private ProducerFactory<String, String> producerFactoryFor(
        MockProducer<String, String> mockProducer) {
    ProducerFactory<String, String> producerFactory =
            Mockito.mock(ProducerFactory.class);
    when(producerFactory.createProducer()).thenReturn(mockProducer);
    return producerFactory;
}
~~~

Nếu phiên bản Spring Kafka của dự án dùng overload hoặc factory API khác, điều chỉnh mock theo interface của phiên bản đó. Với test không dùng transaction, factory cần trả về producer không transactional. Mỗi test nên dùng producer riêng để trạng thái completion/history không rò rỉ giữa các test.

### 5.2. Mô phỏng broker trả lỗi

~~~java
@Test
void completesKafkaTemplateFutureExceptionallyWhenProducerSendFails()
        throws Exception {
    MockProducer<String, String> mockProducer =
            new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

    mockProducer.errorNext(
            new org.apache.kafka.common.errors.TimeoutException(
                    "simulated send timeout"));

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactoryFor(mockProducer));

    CompletableFuture<SendResult<String, String>> future =
            template.send("orders", "order-42", "payload");

    assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
            .isInstanceOf(ExecutionException.class)
            .hasCauseInstanceOf(
                    org.apache.kafka.common.errors.TimeoutException.class);
}
~~~

`errorNext()` cấu hình lỗi cho lần gửi kế tiếp của `MockProducer`. Với `autoComplete=true`, kết quả được hoàn tất tự động và callback của KafkaTemplate được gọi trong test. Vì vậy không cần sleep để chờ callback.

Test này xác minh đường đi từ producer callback tới future của KafkaTemplate. Nó không mô phỏng retry nội bộ của Kafka broker/network và không thay thế integration test với broker thật.

### 5.3. Kiểm tra đường gửi thành công làm đối chứng

Nên có một test đối chứng để xác nhận fixture hoạt động:

~~~java
@Test
void completesFutureWithMetadataWhenMockProducerSucceeds()
        throws Exception {
    MockProducer<String, String> mockProducer =
            new MockProducer<>(
                    true,
                    new StringSerializer(),
                    new StringSerializer());

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactoryFor(mockProducer));

    SendResult<String, String> result =
            template.send("orders", "order-42", "payload")
                    .get(2, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
    assertThat(result.getProducerRecord().key()).isEqualTo("order-42");
    assertThat(mockProducer.history()).hasSize(1);
}
~~~

Metadata cụ thể của `MockProducer` là metadata giả lập. Không dùng test này để xác nhận partitioner, broker acknowledgement hoặc replication.

### 5.4. Kiểm tra ProducerListener

`KafkaTemplate` hỗ trợ `ProducerListener` để nhận thông báo send success/error. Có thể dùng listener để cập nhật metric hoặc ghi log:

~~~java
AtomicReference<Exception> observedFailure = new AtomicReference<>();

template.setProducerListener(new ProducerListener<String, String>() {
    @Override
    public void onError(
            ProducerRecord<String, String> record,
            RecordMetadata metadata,
            Exception exception) {
        observedFailure.set(exception);
    }
});
~~~

Sau khi gọi send bằng `MockProducer.errorNext(...)`, đợi future hoàn tất rồi kiểm tra `observedFailure.get()`. Với lỗi send thất bại trước khi có metadata, tham số metadata có thể là `null`; code listener phải xử lý trường hợp đó.

`ProducerListener` là điểm quan sát bổ sung. Nó không thay thế việc trả future cho caller hoặc xử lý exception đồng bộ.

## 6. Kiểm thử lỗi khởi tạo producer và lỗi đồng bộ

Lỗi trước khi gửi thường không thể mô phỏng chỉ bằng `MockProducer.errorNext()`, vì phương thức đó mô phỏng callback lỗi của lần send. Hãy tách test theo điểm phát sinh lỗi.

### 6.1. ProducerFactory không tạo được producer

Có thể mock `ProducerFactory.createProducer()` ném lỗi:

~~~java
@Test
void handlesProducerCreationFailure() {
    ProducerFactory<String, String> factory =
            Mockito.mock(ProducerFactory.class);
    when(factory.createProducer())
            .thenThrow(new KafkaException("cannot create producer"));

    KafkaTemplate<String, String> template = new KafkaTemplate<>(factory);

    assertThatThrownBy(() -> template.send("orders", "payload"))
            .isInstanceOf(KafkaException.class)
            .hasMessageContaining("cannot create producer");
}
~~~

Nếu phiên bản đang dùng bọc lỗi trong loại exception khác, điều chỉnh assertion theo contract thực tế. Điểm cần xác nhận là lỗi không bị bỏ qua và caller có thể nhận biết producer không được tạo.

### 6.2. Serializer ném exception

Serializer có thể lỗi do payload sai định dạng hoặc schema không hợp lệ. Có thể kiểm tra serializer trực tiếp:

~~~java
class FailingStringSerializer implements Serializer<String> {

    @Override
    public byte[] serialize(String topic, String data) {
        throw new SerializationException("cannot serialize value");
    }
}
~~~

Sau đó dùng serializer trong producer test hoặc kiểm tra component mapping/serialization riêng. Khi viết test với `MockProducer`, xác minh phiên bản Kafka client thực sự gọi serializer trong đường gửi đang dùng. Nếu cần chứng minh chính KafkaProducer xử lý lỗi serializer như production, dùng producer client thật với broker test hoặc test riêng không phụ thuộc broker nếu serializer chạy trước network.

Không chỉ kiểm tra rằng exception được ném. Hãy xác nhận record không được tính là gửi thành công, không tăng success metric và không kích hoạt retry vô hạn cho payload không thể serialize.

### 6.3. Lỗi chờ metadata hoặc buffer

Kafka producer có thể chờ metadata hoặc buffer trước khi `send()` trả về. `max.block.ms` giới hạn một số thao tác chờ đồng bộ này. Kiểm thử loại lỗi này cần producer client thật và cấu hình có kiểm soát, hoặc mock điểm lấy producer/metadata tương ứng.

Không dùng một test unit có `Thread.sleep()` để mô phỏng buffer đầy. Nếu cần kiểm tra hành vi thật, cấu hình môi trường test có giới hạn thời gian thấp, tạo áp lực có chủ đích và dùng timeout của test để tránh treo build.

## 7. Kiểm thử retry và delivery timeout

### 7.1. Phân biệt retry của Kafka client và retry của ứng dụng

Kafka producer client có retry nội bộ đối với một số lỗi có thể phục hồi. Các cấu hình liên quan gồm:

- `retries`: số lần client thử lại theo policy và phiên bản client.
- `delivery.timeout.ms`: tổng thời gian tối đa để báo kết quả giao record, bao gồm thời gian chờ và retry.
- `request.timeout.ms`: giới hạn chờ phản hồi request.
- `linger.ms`: thời gian producer có thể chờ gom batch trước khi gửi.
- `max.block.ms`: giới hạn một số thao tác đồng bộ chờ metadata hoặc buffer.
- `enable.idempotence`: hỗ trợ chống duplicate do retry nội bộ của producer trong phạm vi session/producer protocol.

Retry của ứng dụng là một tầng riêng: service nhận future thất bại rồi chủ động gọi `send()` lại. Nếu bật cả retry nội bộ và retry ứng dụng, số lần gửi và thời gian chờ tổng thể có thể lớn hơn dự tính.

Không cộng số lần retry theo một công thức đơn giản nếu client version có semantics khác. Hãy đo tổng thời gian, số lần gọi send ở tầng ứng dụng và metric producer trong môi trường test.

### 7.2. Kiểm tra retry có giới hạn

Nếu ứng dụng có retry policy, test các trường hợp:

1. Lỗi tạm thời lần đầu, lần sau thành công: ứng dụng gửi lại đúng số lần dự kiến.
2. Tất cả lần gửi đều lỗi: dừng sau giới hạn và trả lỗi cuối cùng.
3. Lỗi không retry được: không lên lịch retry.
4. Backoff có thời gian tối đa và không tạo vòng lặp vô hạn.
5. Hết thời hạn nghiệp vụ: không tiếp tục retry khi kết quả đã không còn hữu ích.
6. Mỗi lần retry giữ key/correlation ID cần thiết để truy vết và deduplicate.

Ví dụ logic cần kiểm tra có thể dùng mock future hoàn tất lần lượt:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> first =
        new CompletableFuture<>();
CompletableFuture<SendResult<String, OrderEvent>> second =
        new CompletableFuture<>();

when(kafkaTemplate.send(eq("orders"), anyString(), any(OrderEvent.class)))
        .thenReturn(first, second);

// Gọi publisher, làm first thất bại với lỗi retryable,
// kích hoạt scheduler/test clock, rồi hoàn tất second thành công.
// Xác nhận số lần gọi send và kết quả cuối cùng.
~~~

Để test backoff mà không chờ thời gian thật, inject scheduler, clock hoặc retry abstraction để test điều khiển được. Nếu code dùng framework retry, dùng test support của framework đó để xác minh số lần thử và delay.

### 7.3. Chọn exception retryable

Không nên retry tất cả `Exception`. Phân loại theo nguyên nhân và policy:

| Loại lỗi | Hành vi thường phù hợp |
|---|---|
| Network tạm thời, broker leader thay đổi | Cho Kafka client retry theo cấu hình; đánh giá retry ứng dụng nếu cần |
| Timeout sau khi client hết delivery deadline | Có thể retry ở tầng ứng dụng nếu nghiệp vụ cho phép và có idempotency |
| Authorization/ACL | Không retry liên tục; sửa quyền/cấu hình |
| Serialization/schema error | Không retry cùng payload; sửa dữ liệu hoặc schema |
| Record quá lớn | Không retry nguyên trạng; sửa kích thước hoặc giới hạn |
| Topic/partition không tồn tại do cấu hình | Không retry mù; xác minh cấu hình và provisioning |
| Producer bị đóng hoặc ứng dụng shutdown | Xử lý theo lifecycle; không tạo retry nền vô hạn |

Một timeout không chứng minh broker chắc chắn chưa ghi record. Broker có thể đã nhận và ghi dữ liệu nhưng acknowledgement không đến được producer. Nếu ứng dụng gửi lại, có thể xuất hiện duplicate ở tầng nghiệp vụ. Vì vậy retry cần idempotency hoặc deduplication khi duplicate gây tác động.

### 7.4. Idempotence không thay thế idempotency nghiệp vụ

`enable.idempotence=true` giúp producer protocol xử lý duplicate do retry nội bộ trong một producer session theo semantics Kafka. Nó không bảo đảm một lệnh gửi lại từ ứng dụng sau timeout, restart hoặc process mới sẽ chỉ tạo một sự kiện nghiệp vụ.

Để kiểm soát duplicate ở cấp nghiệp vụ:

- Dùng event ID ổn định xuyên suốt các lần retry.
- Thiết kế consumer/downstream xử lý idempotent hoặc deduplicate theo event ID.
- Lưu trạng thái gửi và nghiệp vụ trong cùng một transaction phù hợp, hoặc dùng outbox pattern khi cần atomicity giữa database và Kafka.
- Kiểm tra duplicate bằng integration test, không chỉ đếm lời gọi mock.

## 8. Kiểm thử timeout và broker không khả dụng

### 8.1. Cấu hình timeout dành riêng cho test

Khi chạy integration test, có thể dùng deadline ngắn hơn production để test kết thúc nhanh, nhưng phải tuân thủ ràng buộc cấu hình Kafka client. Ví dụ minh họa:

~~~properties
request.timeout.ms=1000
delivery.timeout.ms=4000
linger.ms=0
max.block.ms=1500
~~~

`delivery.timeout.ms` phải phù hợp với tổng thời gian request timeout và linger theo yêu cầu của Kafka client version đang dùng. Nếu cấu hình không hợp lệ, producer có thể từ chối khởi tạo; đó là lỗi cấu hình test, không phải bằng chứng send failure đã được kiểm tra.

Không đặt timeout quá thấp tới mức test thất bại ngẫu nhiên trên CI. Mục tiêu là giới hạn thời gian test trong môi trường được kiểm soát, không tạo một cuộc đua thời gian.

### 8.2. Embedded Kafka cho integration test

`spring-kafka-test` cung cấp `@EmbeddedKafka` để chạy broker trong test. Dùng nó để xác nhận cấu hình thật của ứng dụng, serialization, topic routing và round-trip:

~~~java
@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext
class OrderPublisherIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Test
    void sendsEventToEmbeddedBroker() throws Exception {
        OrderEvent event = new OrderEvent("order-42");

        SendResult<String, OrderEvent> result =
                kafkaTemplate.send("orders", event.orderId(), event)
                        .get(5, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
    }
}
~~~

Đây là test đường thành công. Embedded broker hữu ích cho integration nhưng không tự tạo ra mọi tình huống broker/network failure. Dừng broker hoặc phá kết nối có thể phụ thuộc lifecycle, timing và cách test framework quản lý broker; tránh viết test dựa vào một lần shutdown ngẫu nhiên nếu không kiểm soát được trạng thái.

### 8.3. Fault injection có kiểm soát

Để kiểm tra broker không khả dụng, network partition hoặc mất acknowledgement:

1. Khởi động Kafka broker riêng cho test, thường bằng Testcontainers hoặc môi trường integration cô lập.
2. Đặt một proxy TCP có thể bật/tắt kết nối giữa producer và broker, hoặc dùng cơ chế fault injection của môi trường test.
3. Tạo producer sau khi môi trường đã ở trạng thái xác định.
4. Kích hoạt lỗi ở đúng thời điểm: trước send, sau khi request được gửi hoặc trong lúc chờ acknowledgement.
5. Gọi send và đợi future với timeout hữu hạn.
6. Xác nhận loại lỗi cuối cùng, thời gian hoàn tất, metric và hành vi retry.
7. Khôi phục network/broker và xác nhận producer có thể gửi lại theo lifecycle được hỗ trợ.

Để kiểm tra timeout, cấu hình `delivery.timeout.ms` phù hợp với test và bảo đảm proxy giữ lỗi đủ lâu. Không giả định mọi lần broker ngừng hoạt động đều tạo đúng một exception cụ thể; Kafka client có thể retry, refresh metadata và chỉ trả lỗi cuối cùng sau deadline.

### 8.4. Kiểm thử authorization và record quá lớn

Authorization failure có thể được kiểm tra trong môi trường Kafka có ACL bật:

- Cấp cho principal quyền kết nối nhưng thiếu quyền ghi topic.
- Gửi record và xác nhận future thất bại với lỗi authorization phù hợp.
- Xác nhận ứng dụng không retry liên tục lỗi cấu hình/quyền.
- Khôi phục ACL và xác nhận gửi thành công.

Record quá lớn cần kiểm tra ở giới hạn cấu hình broker/topic/producer phù hợp. Chỉ tăng giới hạn ở một phía không bảo đảm gửi thành công; broker, topic và consumer phải có cấu hình tương thích. Dùng payload test không chứa dữ liệu thật và ghi rõ giới hạn đã áp dụng.

## 9. Kiểm thử transaction producer

Khi dùng Kafka transaction, cần phân biệt ba sự kiện:

1. Producer gửi record và nhận acknowledgement.
2. Ứng dụng gọi commit transaction.
3. Broker xác nhận transaction commit.

Send future thành công ở bước đầu không chứng minh transaction đã commit. Nếu transaction abort, consumer dùng `isolation.level=read_committed` không được nhìn thấy record thuộc transaction bị abort.

Kiểm thử transaction nên bao gồm:

- Gửi thành công và commit; consumer `read_committed` nhận record.
- Gửi record rồi chủ động ném exception trong transaction; transaction abort và consumer `read_committed` không nhận record.
- Commit thất bại do broker/network; ứng dụng báo lỗi transaction và không đánh dấu nghiệp vụ đã hoàn tất.
- Producer transactional ID được cấu hình đúng và không bị trùng theo cách gây fencing ngoài dự kiến.

Ví dụ ý tưởng với KafkaTemplate:

~~~java
template.executeInTransaction(operations -> {
    operations.send("orders", "order-42", "payload");
    throw new IllegalStateException("force rollback in test");
});
~~~

Test phải xác nhận transaction bị rollback theo API/version thực tế và dùng consumer `read_committed` để kiểm tra kết quả. Cấu hình producer transaction ID prefix, transaction manager và consumer isolation đúng với phiên bản Spring Kafka. Không dùng một test chỉ kiểm tra future của send để kết luận transaction đã commit.

## 10. Kiểm tra callback, thread và timeout của test

### 10.1. Không bỏ qua future

Đoạn code sau tạo nguy cơ lỗi bị bỏ qua:

~~~java
kafkaTemplate.send("orders", key, event);
return "accepted";
~~~

Nếu nghiệp vụ cần biết Kafka đã xác nhận hay chưa, việc trả về `accepted` ngay sau lời gọi send chỉ có nghĩa ứng dụng đã bắt đầu gửi. Cần trả future, xử lý callback hoặc ghi trạng thái pending riêng.

### 10.2. Không chờ vô hạn

Trong test, luôn đặt giới hạn chờ:

~~~java
SendResult<String, String> result =
        future.get(3, TimeUnit.SECONDS);
~~~

Nếu future không hoàn tất, test cần thất bại với timeout để chỉ ra callback/future bị treo. Timeout của `future.get(...)` chỉ giới hạn thời gian test chờ; nó không thay đổi `delivery.timeout.ms` của producer.

### 10.3. Tránh sleep và race condition

Không dùng:

~~~java
Thread.sleep(2000);
assertThat(failureCounter.count()).isEqualTo(1);
~~~

Thay bằng:

- Hoàn tất future chủ động trong unit test.
- Dùng `CountDownLatch` hoặc future với timeout khi callback chạy trên thread khác.
- Dùng Awaitility nếu dự án đã có dependency và điều kiện cần chờ là trạng thái bất đồng bộ thực.
- Dùng test clock/scheduler giả lập cho backoff.
- Chỉ dùng timeout thực ở integration/fault-injection test có deadline phù hợp.

Callback có thể chạy trên thread của Kafka producer hoặc thread gọi hoàn tất future tùy implementation. Không giả định callback luôn chạy trên một thread riêng. Tránh callback block lâu, chờ network hoặc thực hiện thao tác nặng làm nghẽn luồng gửi.

## 11. Ma trận kiểm thử đề xuất

| Case | Cách mô phỏng | Kết quả cần xác nhận |
|---|---|---|
| Gửi thành công | `MockProducer` auto-complete hoặc embedded broker | Future thành công, metadata đúng |
| Broker callback lỗi | `MockProducer.errorNext(...)` | Future thất bại, cause được giữ |
| Tạo producer thất bại | Mock `ProducerFactory.createProducer()` ném lỗi | Lỗi đồng bộ được truyền hoặc chuẩn hóa theo API |
| Serializer lỗi | Serializer ném `SerializationException` | Không báo success, không retry payload lỗi vô hạn |
| Timeout giao record | Fault injection/broker không phản hồi | Future thất bại trong deadline cấu hình |
| Authorization failure | Kafka ACL test | Lỗi được phân loại non-retryable |
| Record quá lớn | Cấu hình giới hạn broker/topic | Lỗi rõ ràng, không lặp vô hạn |
| Retryable network failure | Proxy gây mất kết nối có kiểm soát | Retry hữu hạn, kết quả cuối cùng đúng |
| Retry lần đầu lỗi, lần sau thành công | Mock future/scheduler | Số lần gửi và kết quả cuối đúng policy |
| Hết retry | Tất cả lần gửi lỗi | Trả lỗi cuối, không còn tác vụ retry |
| Transaction abort | Ném exception trong transaction | Consumer `read_committed` không thấy record |
| Transaction commit lỗi | Fault injection lúc commit | Không báo nghiệp vụ hoàn tất |
| Shutdown khi đang gửi | Đóng context/producer có kiểm soát | Không treo vô hạn, lỗi được quan sát |

Không cần đưa mọi case vào một test class. Giữ unit test nhanh và xác định; đặt test cần broker, ACL hoặc proxy vào integration suite riêng.

## 12. Những lỗi thường gặp khi viết test

### Chỉ verify lời gọi send

`verify(kafkaTemplate).send(...)` chỉ chứng minh code đã gọi method. Nó không chứng minh future được quan sát, exception được truyền tới caller hay metric phản ánh đúng kết quả.

### Dùng exception sai tầng

`MockProducer.errorNext()` mô phỏng callback failure của lần send. Nó không mô phỏng việc `ProducerFactory` không tạo được producer. Dùng fixture đúng với vị trí lỗi.

### Dùng `get()` nhưng không xử lý lỗi đồng bộ

Nếu `send()` ném exception trước khi trả future, biến future chưa được gán và `get()` không thể bắt lỗi đó. Test riêng đường gọi đồng bộ.

### Kiểm tra sai wrapper exception

`join()` và `get()` dùng wrapper khác nhau cho lỗi bất đồng bộ. Kiểm tra cause thay vì chỉ so sánh message của wrapper. Với lỗi đồng bộ, assertion có thể cần kiểm tra exception gốc.

### Chờ timeout production trong test

Giữ nguyên delivery timeout dài trong một test fault-injection có thể làm build kéo dài. Dùng cấu hình riêng cho test và đặt deadline chờ ở test framework. Bảo đảm cấu hình test vẫn hợp lệ với Kafka client.

### Giả định timeout đồng nghĩa record chưa được ghi

Producer có thể mất acknowledgement sau khi broker đã ghi record. Retry ở tầng ứng dụng có thể tạo duplicate. Kiểm tra event ID, idempotency và đối soát dữ liệu.

### Dùng Embedded Kafka để chứng minh mọi network failure

Embedded broker phù hợp cho integration cơ bản. Muốn kiểm tra mất kết nối, timeout hoặc broker failure cần fault injection có kiểm soát và assertion theo hành vi client thực tế.

### Để callback nuốt exception

Một callback có thể log lỗi nhưng future gốc vẫn thất bại; ngược lại, code dùng `exceptionally` trả về giá trị mặc định có thể làm caller tưởng gửi thành công. Xác định rõ hợp đồng lỗi và test trạng thái future cuối cùng.

## 13. Checklist hoàn thành test producer send failure

### Thiết kế

- [ ] Xác định phiên bản Spring Kafka và kiểu future được sử dụng.
- [ ] Phân loại lỗi đồng bộ, bất đồng bộ và lỗi transaction.
- [ ] Xác định caller cần nhận exception hay failed future.
- [ ] Xác định lỗi nào retry được và giới hạn retry.
- [ ] Xác định cách chống duplicate ở tầng nghiệp vụ.

### Unit test

- [ ] Test future hoàn tất exceptionally.
- [ ] Test exception ném trực tiếp từ lời gọi send.
- [ ] Test caller không nhận kết quả thành công khi send thất bại.
- [ ] Test metric/log success và failure đúng.
- [ ] Test phân loại retryable/non-retryable.
- [ ] Test số lần retry, backoff và dừng khi hết giới hạn.

### KafkaTemplate/Integration test

- [ ] Test `MockProducer.errorNext()` chuyển lỗi sang future.
- [ ] Test success path và metadata.
- [ ] Test ProducerFactory không tạo được producer.
- [ ] Test serializer nếu serialization là rủi ro của ứng dụng.
- [ ] Test broker/ACL/timeout với môi trường có kiểm soát khi cần.
- [ ] Test transaction commit/abort nếu producer dùng transaction.

### Độ ổn định

- [ ] Mọi future trong test đều có timeout chờ hữu hạn.
- [ ] Không dùng sleep tùy tiện để chờ callback.
- [ ] MockProducer/factory không chia sẻ trạng thái giữa test.
- [ ] Test cleanup producer, context, proxy và container.
- [ ] Test failure có thể tái hiện trên CI với cấu hình rõ ràng.

## 14. Báo cáo kết quả kiểm thử

Khi ghi kết quả trong pull request hoặc báo cáo reliability, nêu rõ tầng test, failure injection và bằng chứng quan sát được:

~~~text
Test name:
Spring Kafka version:
Kafka client version:
Test layer: unit / MockProducer / embedded broker / fault injection
Failure point:
Injected exception or fault:
Producer timeout configuration:
Expected result:
Observed future/callback result:
Retry attempts:
Duplicate/idempotency assertion:
Transaction outcome (if applicable):
Cleanup status:
~~~

Một test chỉ có ý nghĩa khi người đọc biết lỗi được chèn ở đâu và assertion chứng minh hành vi nào. Ghi rõ giới hạn của fixture: MockProducer kiểm tra callback/future của client API; embedded broker kiểm tra tích hợp với broker; fault injection kiểm tra hành vi khi network/broker gặp lỗi.

## 15. Tương thích phiên bản Spring Kafka

Từ Spring Kafka 3.0, các API `KafkaTemplate.send(...)` trả về `CompletableFuture`. Các ứng dụng dùng Spring Kafka 2.x thường gặp `ListenableFuture` và callback theo API của Spring:

~~~java
ListenableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.addCallback(
        result -> log.info("Send completed"),
        exception -> log.warn("Send failed", exception));
~~~

Đây là dạng API cũ để nhận biết khi đọc codebase. Không trộn `ListenableFuture` với ví dụ `CompletableFuture` trong cùng test nếu dự án chưa nâng cấp. Khi nâng phiên bản:

- Cập nhật kiểu trả về và callback.
- Cập nhật assertion cho exception/wrapper.
- Kiểm tra `MockProducer`, `ProducerFactory` và Kafka client API tương ứng.
- Chạy lại test transaction, retry và shutdown vì semantics phụ thuộc version/configuration.

## 16. Nguyên tắc vận hành sau kiểm thử

Khi test phát hiện producer send failure, kết quả nên dẫn tới một hành vi vận hành rõ ràng: log đủ thông tin để truy vết, metric thể hiện tỷ lệ lỗi, alert có ngưỡng phù hợp, retry dừng đúng lúc và bản ghi không bị đánh dấu thành công sai. Với các luồng quan trọng, cần có cách đối soát event ID hoặc outbox để xác định bản ghi nào đã được gửi và bản ghi nào cần xử lý lại.

Không dùng retry để che lỗi cấu hình kéo dài. Không reset hoặc xóa trạng thái gửi chỉ để làm dashboard sạch. Khi một timeout có thể đã xảy ra sau khi broker ghi record, điều tra duplicate bằng key/event ID và trạng thái consumer trước khi phát lại.
