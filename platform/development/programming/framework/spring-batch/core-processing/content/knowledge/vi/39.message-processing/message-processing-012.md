# Kiểm thử message reader writer

Trong Spring Batch, message reader và message writer cho phép một step nhận dữ liệu từ message broker hoặc gửi kết quả tới một destination như JMS queue/topic. Khác với file hoặc database, message là một đơn vị trao đổi độc lập, có thể được acknowledge, redeliver, gửi trùng hoặc hết hạn theo chính sách của broker. Vì vậy, kiểm thử message reader/writer cần xác nhận cả việc chuyển đổi payload lẫn semantics giao nhận và transaction.

Với JMS, Spring Batch cung cấp `JmsItemReader<T>` và `JmsItemWriter<T>`. Reader nhận message thông qua `JmsTemplate` và chuyển payload thành item; writer chuyển từng item thành message rồi gửi tới destination. Có thể kiểm thử hai component độc lập bằng mock `JmsTemplate`, sau đó bổ sung integration test với broker thật để xác nhận acknowledge, rollback, redelivery, header và destination behavior.

## 1. Message processing trong Spring Batch

Một message-oriented step thường có dạng:

```text
JMS Queue / Topic
       |
       v
  JmsItemReader
       |
       v
 ItemProcessor
       |
       v
  JmsItemWriter
       |
       v
Output Queue / Topic
```

Reader và writer được gọi theo chunk giống các item component khác. Ví dụ step đọc 100 message, xử lý 100 payload rồi gửi output trong một chunk. Tuy nhiên, message broker có cơ chế giao nhận riêng; việc database transaction của step rollback không tự động bảo đảm message đã nhận được redeliver hoặc message đã gửi bị thu hồi.

Khi thiết kế test, cần tách các câu hỏi:

- Reader có nhận đúng message từ đúng destination không?
- Message converter có tạo đúng Java item không?
- Khi không còn message, reader có trả `null` theo hợp đồng `ItemReader` không?
- Writer có gửi đủ item tới đúng destination với payload/header đúng không?
- Nếu chunk lỗi, message nhận có được redeliver và message gửi có bị rollback không?
- Retry/restart có thể tạo message trùng không?
- Broker xử lý poison message, delivery limit và dead-letter queue như thế nào?

## 2. JmsItemReader và JmsItemWriter

Hai component thường dùng trong Spring Batch JMS:

| Component | Trách nhiệm |
|---|---|
| `JmsItemReader<T>` | Nhận message từ destination bằng `JmsTemplate`, chuyển message thành item và trả về từng item. |
| `JmsItemWriter<T>` | Chuyển item thành JMS message và gửi tới destination bằng `JmsTemplate`. |
| `JmsTemplate` | Cung cấp API gửi/nhận JMS và sử dụng `MessageConverter` nếu gọi các phương thức `convert...`. |
| `MessageConverter` | Chuyển payload Java sang JMS message và ngược lại. |
| JMS ConnectionFactory | Tạo connection/session tới broker. |
| JMS Transaction Manager | Quản lý local JMS transaction và việc commit/rollback session. |

`JmsItemReader` thường được cấu hình bằng `JmsTemplate`, tên destination và kiểu item. `JmsItemWriter` cũng nhận `JmsTemplate` và destination đích. API cụ thể có thể thay đổi theo phiên bản Spring Batch/Spring Framework; hãy dùng package `jakarta.jms` trong hệ Spring Framework 6/Spring Batch 5 và kiểm tra API tương ứng nếu ứng dụng đang dùng thế hệ `javax.jms` cũ.

## 3. Cấu hình message reader

Ví dụ queue chứa payload customer đã được converter chuyển thành `CustomerMessage`:

```java
@Bean
@StepScope
JmsItemReader<CustomerMessage> customerMessageReader(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['inputDestination']}") String destination) {

    JmsItemReader<CustomerMessage> reader = new JmsItemReader<>();
    reader.setName("customerMessageReader");
    reader.setJmsTemplate(jmsTemplate);
    reader.setDestinationName(destination);
    reader.setItemType(CustomerMessage.class);
    return reader;
}
```

Trong ví dụ, `@StepScope` cho phép chọn destination theo JobParameters. Destination phải được validate theo cấu hình ứng dụng; không nên nhận một destination tùy ý từ message hoặc input không tin cậy.

Reader dùng `JmsTemplate` để nhận message. Khi message converter hoạt động, payload được chuyển thành kiểu `CustomerMessage`. Nếu message không thể convert hoặc payload không đúng kiểu, reader có thể phát sinh exception; không nên biến lỗi conversion thành `null` vì `null` ở `ItemReader` có nghĩa end of input.

## 4. Cấu hình message writer

Writer gửi mỗi item tới destination:

```java
@Bean
@StepScope
JmsItemWriter<CustomerMessage> customerMessageWriter(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['outputDestination']}") String destination) {

    JmsItemWriter<CustomerMessage> writer = new JmsItemWriter<>();
    writer.setJmsTemplate(jmsTemplate);
    writer.setDestinationName(destination);
    return writer;
}
```

Trong chunk, writer gửi từng item thành một message. Nếu một lần gửi thất bại giữa chunk, kết quả thực tế phụ thuộc JMS session/transaction đang dùng. Không được mặc định các message đã gửi trước lỗi sẽ tự biến mất khi Spring Batch rollback transaction database.

Nếu output cần có correlation ID, event type hoặc batch ID, có thể dùng một `MessageConverter` tùy chỉnh, `MessagePostProcessor` hoặc writer adapter chuyên biệt để gắn header/property phù hợp. Test cần kiểm tra các metadata này như một phần hợp đồng tích hợp.

## 5. Cấu hình MessageConverter

JMS message có nhiều dạng như `TextMessage`, `BytesMessage`, `MapMessage` và `ObjectMessage`. `MessageConverter` quyết định cách chuyển payload Java thành message và ngược lại.

Với payload dạng String hoặc các kiểu được `SimpleMessageConverter` hỗ trợ, cấu hình đơn giản có thể đủ. Với DTO JSON, có thể dùng Jackson-based converter:

```java
@Bean
MappingJackson2MessageConverter customerMessageConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}

@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory,
                        MessageConverter customerMessageConverter) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(customerMessageConverter);
    return template;
}
```

Converter JSON có thể dùng type id để xác định Java type khi nhận message. Cần giới hạn các type được phép và không tin cậy type metadata do bên gửi tùy ý cung cấp. Với hệ thống liên kết nhiều service, schema/version rõ ràng và discriminator allowlist thường an toàn, dễ kiểm soát hơn việc cho phép deserialize mọi class.

## 6. Kiểm thử reader độc lập bằng mock JmsTemplate

Unit test cho reader nên xác nhận:

- Reader dùng đúng destination.
- Payload được trả về theo thứ tự nhận.
- Reader trả `null` khi `JmsTemplate` không còn message.
- Reader không trả nhầm kiểu item.
- Exception từ broker/converter được truyền ra theo contract.

Ví dụ dùng Mockito với payload String:

```java
@ExtendWith(MockitoExtension.class)
class JmsItemReaderTest {

    @Mock
    private JmsTemplate jmsTemplate;

    private JmsItemReader<String> reader;

    @BeforeEach
    void setUp() {
        reader = new JmsItemReader<>();
        reader.setName("testJmsReader");
        reader.setJmsTemplate(jmsTemplate);
        reader.setDestinationName("customer.input");
        reader.setItemType(String.class);
        reader.afterPropertiesSet();
        reader.open(new ExecutionContext());
    }

    @AfterEach
    void tearDown() {
        reader.close();
    }

    @Test
    void readsMessagesUntilNoMessageIsAvailable() throws Exception {
        when(jmsTemplate.receiveAndConvert("customer.input"))
                .thenReturn("C001", "C002", null);

        assertThat(reader.read()).isEqualTo("C001");
        assertThat(reader.read()).isEqualTo("C002");
        assertThat(reader.read()).isNull();

        verify(jmsTemplate, times(3))
                .receiveAndConvert("customer.input");
    }
}
```

Ví dụ giả định phiên bản `JmsItemReader` đang dùng gọi overload `receiveAndConvert(String destinationName)`. Nếu implementation/version sử dụng overload nhận `Destination`, hãy mock đúng overload đó. Unit test nên phản ánh API thật trong dependency của dự án.

`open()` và `close()` được gọi để tôn trọng lifecycle `ItemStream` của reader. Không nên chỉ gọi `read()` trên một reader stream chưa mở nếu contract yêu cầu `open(ExecutionContext)` trước.

## 7. Kiểm thử reader trả null và end of input

Với queue hữu hạn hoặc một batch có tín hiệu kết thúc rõ ràng, reader có thể trả `null` khi không còn message. Test cần xác nhận `null` chỉ xuất hiện ở điều kiện kết thúc đã định nghĩa.

Một queue JMS thông thường không có EOF tự nhiên. Nếu `JmsTemplate.receiveAndConvert(...)` trả `null` do timeout hoặc queue hiện đang rỗng, `JmsItemReader` có thể trả `null` cho Spring Batch. Framework hiểu đây là end of input và step có thể hoàn tất. Message đến sau đó sẽ không tự khởi động lại step.

Do đó, trước khi dùng `JmsItemReader` cho queue, cần quyết định một trong các mô hình:

- Batch có số message hoặc số record dự kiến đã biết.
- Message cuối là sentinel/end marker theo hợp đồng.
- Có metadata batch/manifest xác định khi nào đã nhận đủ message.
- Queue được drain trong một cửa sổ thời gian hữu hạn và timeout được coi là kết thúc theo nghiệp vụ.
- Dùng message-driven consumer hoặc integration flow phù hợp cho luồng liên tục thay vì một step batch hữu hạn.

Không test rằng “queue rỗng tạm thời” đồng nghĩa “batch hoàn tất” trừ khi đó là quy tắc nghiệp vụ đã thống nhất.

## 8. Kiểm thử message converter riêng

Không nên chỉ test reader/writer với String nếu production dùng DTO JSON. Hãy test converter độc lập để xác nhận format message.

Ví dụ kiểm tra chuyển DTO sang JSON `TextMessage` và ngược lại:

```java
@Test
void convertsCustomerPayloadToAndFromTextMessage() throws Exception {
    CustomerMessage input = new CustomerMessage("C001", "Nguyen An");

    Message message = converter.toMessage(input, session);
    assertThat(message).isInstanceOf(TextMessage.class);

    CustomerMessage restored = (CustomerMessage) converter.fromMessage(message);
    assertThat(restored.customerId()).isEqualTo("C001");
    assertThat(restored.name()).isEqualTo("Nguyen An");
}
```

Đây là test contract minh họa; cách tạo `Session`/message trong unit test phụ thuộc JMS provider và converter. Với converter cần broker/session thật, integration test sẽ phù hợp hơn.

Các trường hợp nên kiểm tra:

- Payload hợp lệ và đúng schema.
- Field bắt buộc bị thiếu.
- JSON sai cú pháp hoặc type không hỗ trợ.
- Ký tự Unicode và encoding.
- Header/type id/correlation ID.
- Version schema cũ và mới.
- Payload quá lớn hoặc vượt giới hạn cấu hình.

## 9. Kiểm thử writer độc lập bằng mock JmsTemplate

Unit test writer xác nhận mỗi item được gửi tới đúng destination và lỗi gửi được truyền ra.

```java
@ExtendWith(MockitoExtension.class)
class JmsItemWriterTest {

    @Mock
    private JmsTemplate jmsTemplate;

    private JmsItemWriter<String> writer;

    @BeforeEach
    void setUp() {
        writer = new JmsItemWriter<>();
        writer.setJmsTemplate(jmsTemplate);
        writer.setDestinationName("customer.output");
        writer.afterPropertiesSet();
    }

    @Test
    void sendsEveryItemToConfiguredDestination() throws Exception {
        writer.write(new Chunk<>(List.of("C001", "C002", "C003")));

        verify(jmsTemplate).convertAndSend("customer.output", "C001");
        verify(jmsTemplate).convertAndSend("customer.output", "C002");
        verify(jmsTemplate).convertAndSend("customer.output", "C003");
        verifyNoMoreInteractions(jmsTemplate);
    }

    @Test
    void propagatesSendFailure() {
        doThrow(new JmsException("broker unavailable"))
                .when(jmsTemplate)
                .convertAndSend("customer.output", "C001");

        assertThatThrownBy(() -> writer.write(
                new Chunk<>(List.of("C001"))))
                .isInstanceOf(JmsException.class);
    }
}
```

Ví dụ giả định writer dùng `convertAndSend(String destinationName, Object message)`. Nếu version hoặc implementation dùng destination object hay overload có `MessagePostProcessor`, hãy verify đúng method thực tế.

Mock test xác nhận lời gọi được tạo đúng; nó không chứng minh broker đã nhận, persist hoặc deliver message. Những điều đó cần integration test.

## 10. Kiểm thử chunk rỗng và writer failure

Nên kiểm tra writer với chunk rỗng theo contract của phiên bản đang dùng. Không nên gửi message giả khi chunk không có item.

Một test quan trọng khác là lỗi xảy ra sau khi writer đã gửi một phần chunk:

```text
Chunk: A, B, C
  send A -> success
  send B -> success
  send C -> exception
```

Unit test có thể xác nhận exception được truyền ra và các lời gọi trước lỗi đã xảy ra. Nhưng mock không thể xác nhận A/B có bị broker rollback hay không. Điều đó phụ thuộc session transaction và transaction manager.

Không viết assertion rằng “writer ném exception nên không có message nào được gửi” nếu chưa cấu hình một transaction bao phủ việc gửi và chưa xác minh broker hỗ trợ semantics đó. Nếu gửi từng message bằng session auto-ack/non-transacted, các message đã gửi trước lỗi có thể đã tồn tại ở destination.

## 11. Kiểm thử destination và routing

Destination là một phần của contract. Unit test nên xác nhận:

- Reader nhận từ đúng queue/topic.
- Writer gửi đến đúng queue/topic.
- JobParameters hoặc configuration profile chọn đúng destination.
- Không gửi nhầm môi trường dev/test/prod.
- Routing theo message type không đưa payload vào destination sai.

Nếu dùng `Destination` object thay vì destination name, test nên xác nhận đúng object được truyền tới `JmsTemplate`. Với dynamic destination, cần whitelist tên được phép và test input không hợp lệ.

Không dùng tên queue cố định được chia sẻ giữa nhiều test chạy song song. Dùng destination có suffix theo test run hoặc tạo broker riêng cho test để tránh message từ test khác lọt vào.

## 12. Integration test với broker thật

Unit test mock không mô phỏng đầy đủ:

- JMS session và acknowledge mode.
- Message persistence.
- Delivery count và redelivery.
- Selector và destination semantics.
- Transaction commit/rollback.
- Dead-letter queue và expiration.
- Serialization theo provider thực tế.

Vì vậy, với message reader/writer dùng trong production, cần integration test với broker cùng loại hoặc tương thích với broker production. Có thể chạy broker ephemeral trong test bằng embedded broker nếu provider hỗ trợ, hoặc dùng container test chuyên dụng.

Một integration test cơ bản:

1. Khởi tạo broker test và connection factory.
2. Tạo queue riêng cho test.
3. Gửi một số message có payload/headers đã biết.
4. Mở `JmsItemReader` và đọc item.
5. Xác nhận thứ tự, nội dung và end condition.
6. Ghi item qua `JmsItemWriter`.
7. Dùng consumer test nhận message output.
8. Xác nhận payload, destination và metadata.
9. Dọn queue/broker sau test.

Broker test phải được đóng trong `@AfterEach`/`@AfterAll` hoặc lifecycle của Testcontainers để không rò rỉ thread, port và resource giữa các test.

## 13. Kiểm thử send/receive end-to-end

Một test end-to-end có thể gửi message vào input queue, chạy một step và kiểm tra output queue:

```text
Test producer
     |
     v
input.queue
     |
     v
Spring Batch Job
  JmsItemReader
  ItemProcessor
  JmsItemWriter
     |
     v
output.queue
     |
     v
Test consumer assertions
```

Test nên xác nhận:

- JobExecution và StepExecution kết thúc đúng trạng thái.
- `readCount`, `writeCount`, `filterCount`, `skipCount` đúng với input.
- Output queue có đủ message mong đợi.
- Payload sau conversion giữ nguyên dữ liệu quan trọng.
- Header như correlation ID, event type, batch ID được giữ hoặc tạo đúng.
- Input queue còn/không còn message theo acknowledge/transaction policy đã chọn.
- Không có message thừa từ lần test trước.

## 14. JMS acknowledgement và transaction

Đây là phần quan trọng nhất khi test reader. JMS có acknowledge mode và transaction riêng. `JmsTemplate` mặc định thường dùng `AUTO_ACKNOWLEDGE` khi không có JMS transaction được quản lý. Với synchronous receive, message có thể được acknowledge ngay khi nhận thành công.

Nếu `JmsItemReader` nhận message và Spring Batch sau đó rollback chunk do processor/writer lỗi, message đã được auto-acknowledge có thể không được redeliver. Database rollback không tự trả message về queue.

Nếu muốn message receive được commit cùng chunk, cần cấu hình JMS transaction phù hợp và dùng transaction manager quản lý JMS session cho step. Khi JMS là resource duy nhất, `JmsTransactionManager` có thể quản lý local JMS transaction. Khi step vừa ghi database vừa nhận/gửi JMS, một local transaction manager không tự atomic cả hai resource; cần XA/JTA nếu hệ thống hỗ trợ, hoặc thiết kế outbox/inbox và idempotency.

Test phải mô phỏng lỗi sau khi receive và xác nhận broker behavior theo cấu hình thật. Không suy luận acknowledge behavior chỉ từ việc step status là `FAILED`.

## 15. Kiểm thử rollback và redelivery

Một test transaction nên xác minh cả trường hợp commit và rollback:

**Commit:**

1. Gửi message vào input queue.
2. Chạy step với JMS transaction manager phù hợp.
3. Cho chunk hoàn tất.
4. Xác nhận message được consume/acknowledge theo thiết kế.

**Rollback:**

1. Gửi message vào input queue.
2. Làm processor hoặc writer phát sinh exception trước commit.
3. Xác nhận JMS session rollback.
4. Dùng consumer test nhận lại message.
5. Kiểm tra redelivery flag/count theo broker.

Tên property redelivery có thể khác theo JMS provider. JMS định nghĩa cờ `JMSRedelivered`; một số broker còn cung cấp delivery count như property mở rộng. Test portable nên kiểm tra `JMSRedelivered` khi có thể và chỉ kiểm tra provider-specific count trong test riêng cho broker đó.

## 16. Phân biệt transaction của JMS và transaction database

Một chunk có thể cần cập nhật database và gửi message. Có ba tình huống:

| Cấu hình | Rủi ro |
|---|---|
| Database transaction nhưng JMS send non-transacted | Database rollback không thu hồi message đã gửi. |
| JMS local transaction nhưng database transaction riêng | JMS rollback không tự rollback database và ngược lại. |
| XA/JTA transaction bao phủ cả hai resource | Có thể phối hợp commit/rollback nguyên tử nếu broker, database và transaction manager được cấu hình đúng; tăng độ phức tạp vận hành. |

Với nhiều hệ thống, transactional outbox thường là lựa chọn đơn giản hơn: batch ghi dữ liệu và outbox record trong cùng database transaction; publisher riêng gửi message sau commit. Consumer dùng idempotency/inbox để chống duplicate.

Integration test nên xác nhận failure window: database commit nhưng send chưa xảy ra; send thành công nhưng metadata chưa commit; process dừng giữa hai bước. Test mock không thể chứng minh tính atomic của hai hệ thống.

## 17. Kiểm thử JmsItemWriter khi gửi trùng

Spring Batch có thể retry chunk hoặc restart job sau lỗi. Nếu một message đã được broker nhận nhưng step chưa ghi nhận thành công, lần retry có thể gửi lại cùng item.

Ví dụ:

```text
Chunk gửi event E-100
  broker nhận E-100
  process chết trước khi chunk metadata commit

Restart/retry
  chunk được chạy lại
  writer gửi E-100 lần nữa
```

Đây là duplicate delivery/duplicate publication. JMS delivery guarantee không tự bảo đảm ứng dụng chỉ nhìn thấy một lần xử lý ở mọi failure window.

Test nên dùng event ID ổn định và xác nhận:

- Writer có thể gửi cùng event nhiều lần khi retry.
- Consumer deduplicate theo event ID hoặc idempotency key.
- Side effect của consumer chỉ được áp dụng một lần theo nghiệp vụ.
- Audit có thể nhận diện message redelivered/duplicate.

Không tạo event ID mới mỗi lần retry. ID phải được tạo trước hoặc ổn định theo business key để các attempt nhận diện cùng một sự kiện.

## 18. Kiểm thử poison message và dead-letter queue

Poison message là message luôn gây lỗi khi xử lý, ví dụ payload sai schema, thiếu field bắt buộc hoặc dữ liệu không thể parse. Nếu broker redeliver liên tục, một message có thể làm worker thất bại lặp lại.

Test cần xác nhận:

- Exception nào làm message bị rollback/redeliver.
- Broker hoặc application giới hạn số lần delivery thế nào.
- Khi vượt delivery limit, message được chuyển tới dead-letter queue (DLQ) hay bị loại.
- Payload, original destination, delivery count và exception context có được giữ không.
- Có thể replay message sau khi sửa dữ liệu hoặc code không.

DLQ policy phụ thuộc broker. Một số broker dùng address/queue cấu hình riêng, một số dùng dead-letter strategy và delivery count. Không giả định tên DLQ hoặc property cụ thể giống nhau giữa ActiveMQ Artemis, ActiveMQ Classic, IBM MQ, RabbitMQ JMS client hoặc broker khác.

## 19. Kiểm thử message headers và correlation

Message thường có metadata ngoài payload:

- `JMSMessageID` do provider tạo.
- `JMSCorrelationID` để liên kết request/response hoặc event chain.
- `JMSType` nếu ứng dụng sử dụng.
- `JMSReplyTo` nếu có request/reply.
- Custom properties như `eventType`, `schemaVersion`, `batchId`, `tenantId`.

Test writer nên xác nhận header/property được gắn đúng. Test reader nên xác nhận converter hoặc adapter giữ metadata cần thiết trong item wrapper.

Ví dụ wrapper:

```java
public record InboundMessage<T>(
        T payload,
        String correlationId,
        String eventType,
        String batchId) {
}
```

Nếu chỉ dùng `JmsItemReader<T>` trả payload, một số metadata có thể không được đưa vào object. Khi nghiệp vụ cần header, có thể dùng custom converter/reader trả wrapper hoặc custom `ItemReader` nhận `Message` và map cả payload lẫn headers.

Không dùng `JMSMessageID` làm idempotency key duy nhất nếu broker có thể tạo ID mới khi message được publish lại. Business event ID ổn định thường phù hợp hơn.

## 20. Kiểm thử queue và topic semantics

Queue và topic có semantics khác nhau:

- Queue thường phân phối mỗi message tới một consumer trong nhóm competing consumers.
- Topic publish-subscribe phân phối message tới subscriber theo subscription semantics; durable subscription có lifecycle riêng.
- Selector lọc message theo header/property.
- Durable subscription có thể giữ message khi subscriber offline theo cấu hình broker.

Test cần xác nhận destination type phù hợp. Nếu dùng topic, hãy kiểm tra durable/non-durable subscription, client ID và subscription name theo broker. Nếu dùng selector, gửi message cả khớp và không khớp để xác nhận đúng tập item.

Đừng dùng chung topic subscription giữa các test song song nếu không có isolation. Test có thể nhận message của nhau và tạo kết quả không ổn định.

## 21. Kiểm thử message ordering

JMS queue thường giữ thứ tự gửi/nhận theo các điều kiện của provider, nhưng concurrency, message priority, redelivery, multiple producers và competing consumers có thể làm thứ tự quan sát khác với thứ tự đơn giản trong test.

Nếu thứ tự nghiệp vụ quan trọng:

- Dùng một producer/consumer path có thứ tự xác định.
- Gắn sequence number hoặc aggregate version vào payload.
- Kiểm tra thứ tự theo business key/version thay vì chỉ dựa vào `JMSMessageID`.
- Test redelivery và nhiều consumer theo đúng cấu hình production.
- Cân nhắc partition theo aggregate key để các event cùng aggregate được xử lý tuần tự.

Không viết test đòi thứ tự toàn cục trong môi trường nhiều consumer nếu hệ thống không cam kết điều đó.

## 22. Kiểm thử message expiration và delivery delay

Message có thể có time-to-live (TTL), delivery delay hoặc timestamp. Test cần xác nhận:

- Message hết hạn trước khi reader nhận có bị broker loại hoặc chuyển DLQ theo policy không.
- Message delay chưa đến thời điểm giao không bị hiểu nhầm là EOF nếu reader dùng timeout.
- Job có thể kết thúc sớm khi queue tạm thời rỗng hay phải đợi batch completion signal.
- Đồng hồ trong test được kiểm soát để tránh phụ thuộc thời gian thực không ổn định.

Nếu dùng TTL, hãy đặt giá trị đủ dài cho integration test hoặc cấu hình clock/wait phù hợp. Tránh test dựa vào sleep dài; ưu tiên polling với deadline và điều kiện cụ thể.

## 23. Kiểm thử message conversion lỗi

Một payload có thể đến broker thành công nhưng không thể chuyển thành item. Test nên tạo message sai schema hoặc content type để xác nhận:

- Reader phát sinh exception có ý nghĩa.
- Job áp dụng đúng skip/retry/fail policy.
- Message có được acknowledge hay redeliver theo transaction/ack mode không.
- Poison message có thể đi DLQ sau số lần thử phù hợp.
- Raw payload và metadata đủ để điều tra.

Không catch mọi conversion exception rồi trả `null`. Điều đó khiến Spring Batch coi lỗi payload là EOF và step có thể kết thúc như thể queue đã hết dữ liệu.

## 24. Kiểm thử Step với @SpringBatchTest

`@SpringBatchTest` cung cấp tiện ích cho test Spring Batch như `JobLauncherTestUtils` và `JobRepositoryTestUtils` trong cấu hình phù hợp. Có thể dùng để chạy job/step với message reader/writer thật được cấu hình cho broker test.

Ví dụ cấu trúc:

```java
@SpringBatchTest
@SpringBootTest
class MessageImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JmsTemplate jmsTemplate;

    @Test
    void importsMessagesFromInputQueue() throws Exception {
        jmsTemplate.convertAndSend("customer.input",
                new CustomerMessage("C001", "Nguyen An"));

        JobExecution execution = jobLauncherTestUtils.launchJob(
                new JobParametersBuilder()
                        .addString("runId", UUID.randomUUID().toString())
                        .toJobParameters());

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

Đây là skeleton; job cần có điều kiện kết thúc rõ ràng cho queue, chẳng hạn số message đã biết hoặc end marker. Nếu reader kết thúc khi queue timeout, test phải kiểm soát timeout và không gửi message sau khi reader đã nhận `null`.

`JobRepositoryTestUtils` có thể giúp dọn metadata job execution giữa các test. Nó không tự xóa message trong broker; test phải dọn destination hoặc dùng queue riêng.

## 25. Kiểm thử restart của message step

Restart test cần trả lời câu hỏi: message đã nhận nhưng chunk rollback có được redeliver không, và output message đã gửi trước lỗi có bị gửi lại không?

Một test có kiểm soát:

1. Gửi message có event ID `E-001` vào input queue.
2. Chạy step và cố tình làm writer thất bại ở lần đầu.
3. Xác nhận database/chunk transaction rollback.
4. Xác nhận input message còn hoặc được redeliver theo JMS transaction policy.
5. Restart cùng JobInstance hoặc retry chunk theo thiết kế.
6. Xác nhận event `E-001` được xử lý đúng một lần về mặt nghiệp vụ nhờ idempotency.
7. Xác nhận output queue không có duplicate ngoài semantics được chấp nhận.

Nếu dùng auto-acknowledge, message có thể đã bị consume dù chunk rollback. Test này sẽ phát hiện rủi ro đó. Nếu dùng local JMS transaction, cần xác nhận receive/ack được rollback. Nếu kết hợp database và JMS, cần test failure window giữa hai resource.

## 26. Test isolation và cleanup

Message broker giữ state bên ngoài test JVM. Nếu không cô lập, test có thể phụ thuộc thứ tự chạy hoặc để lại message cho test tiếp theo.

Thực hành tốt:

- Dùng queue/topic riêng theo test class hoặc test run.
- Dọn message còn lại sau mỗi test.
- Khởi động broker ephemeral và đóng đúng lifecycle.
- Dùng database/test metadata riêng nếu job có JobRepository.
- Không chạy test song song trên cùng destination nếu chúng cạnh tranh nhận message.
- Dùng timeout có giới hạn để test không treo vô hạn.
- Log correlation ID/test ID để truy vết message.
- Không dùng `Thread.sleep` cố định dài; dùng polling có deadline.

Nếu test dùng embedded broker singleton, cần reset destination và connection state trước mỗi test. Nếu dùng Testcontainers, cần chờ broker ready và đóng container sau suite.

## 27. Kiểm thử consumer idempotency

Message broker có thể redeliver khi consumer rollback, connection mất hoặc acknowledgement không được xác nhận. Producer cũng có thể publish lại sau timeout không rõ kết quả. Vì vậy consumer thường cần idempotency.

Một pattern phổ biến là lưu `event_id` trong bảng inbox có unique constraint:

```sql
CREATE TABLE processed_message (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Consumer xử lý message trong transaction:

1. Thử insert `event_id` vào bảng inbox.
2. Nếu insert thành công, áp dụng thay đổi nghiệp vụ.
3. Commit cả inbox marker và business update.
4. Nếu event ID đã tồn tại, bỏ qua side effect lặp theo quy tắc.

Test cần gửi cùng event hai lần và xác nhận business state chỉ thay đổi một lần. Nếu marker và business update không cùng transaction, vẫn có failure window có thể gây mất hoặc lặp xử lý.

## 28. Kiểm thử message properties và selector

Nếu reader dùng message selector, hãy test cả message khớp và không khớp:

```text
eventType = 'CUSTOMER_CREATED'
tenantId = 'tenant-01'
```

Test nên xác nhận:

- Message đúng selector được nhận.
- Message không khớp vẫn ở destination hoặc được subscriber khác nhận theo semantics broker.
- Selector dùng đúng kiểu property (String, number, boolean).
- Tên property không dùng reserved JMS header sai cách.
- Message thiếu property được xử lý như dự kiến.

Selector có thể có cú pháp và behavior phụ thuộc JMS provider. Hãy chạy integration test với broker production-compatible thay vì chỉ mock `JmsTemplate`.

## 29. Kiểm thử lỗi kết nối và timeout

Broker có thể không khả dụng khi reader/writer mở connection hoặc gửi/nhận message. Cần test:

- Connection refused hoặc broker restart.
- Timeout khi nhận message.
- Send timeout hoặc producer flow control.
- Consumer connection mất sau receive nhưng trước commit.
- Writer gặp lỗi sau một số send thành công.
- Reconnect có tạo consumer/session mới đúng cách không.

Retry chỉ phù hợp với lỗi có khả năng phục hồi. Payload sai schema hoặc destination sai cấu hình không nên retry vô hạn. Với lỗi kết nối, cấu hình backoff và giới hạn retry để tránh job treo hoặc tạo tải lớn lên broker.

## 30. Những lỗi thường gặp khi test message reader/writer

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Reader trả null ngay | Queue rỗng hoặc receive timeout; Batch hiểu đó là EOF. | Định nghĩa batch completion/end marker hoặc dùng mô hình message-driven. |
| Step rollback nhưng message biến mất | `AUTO_ACKNOWLEDGE` đã acknowledge khi receive. | Dùng JMS transaction phù hợp và test rollback/redelivery. |
| Message output vẫn tồn tại sau database rollback | JMS send không tham gia transaction database. | Dùng XA/JTA khi phù hợp hoặc transactional outbox. |
| Message gửi trùng sau retry | Send thành công nhưng chunk metadata chưa commit. | Idempotency key và consumer deduplication. |
| Unit test pass nhưng production conversion lỗi | Mock không chạy converter/broker thật. | Thêm integration test với message converter và broker thực tế. |
| Test nhận message từ test khác | Dùng chung queue/topic và không cleanup. | Destination riêng và cleanup sau test. |
| Test treo | Reader chờ vô hạn khi queue không có message. | Cấu hình timeout có giới hạn hoặc gửi end marker. |
| Message sai type bị coi là EOF | Conversion error bị catch và đổi thành null. | Propagate exception hoặc route rejected message. |
| Header bị mất | Reader chỉ trả payload, metadata không được map vào item. | Dùng wrapper/custom converter và test headers. |
| Redelivery test không ổn định | Dựa vào provider-specific delivery count hoặc timing. | Kiểm tra `JMSRedelivered`, dùng broker thật và polling deadline. |
| Queue/topic semantics sai | Dùng queue test cho behavior durable topic hoặc selector. | Test đúng loại destination/subscription. |
| Writer gửi một phần chunk | Gửi không transactional hoặc session commit độc lập. | Kiểm thử partial failure, JMS transaction và idempotency. |

## 31. Quy trình xây dựng test strategy

Khi kiểm thử message reader/writer, có thể đi theo các tầng:

1. **Unit test reader:** mock `JmsTemplate`, xác nhận destination, payload, thứ tự, EOF và exception.
2. **Unit test writer:** verify `convertAndSend`, destination, số lần gọi và lỗi gửi.
3. **Converter test:** kiểm tra JSON/text/bytes, type mapping, schema version và header.
4. **Broker integration test:** gửi/nhận thật, queue/topic, selector, message properties và cleanup.
5. **Transaction test:** xác nhận ack/commit/rollback/redelivery theo JMS transaction manager.
6. **Chunk test:** xác nhận read/process/write counts và behavior khi một chunk lỗi.
7. **Restart/retry test:** xác nhận message không mất hoặc lặp ngoài semantics được thiết kế.
8. **Failure test:** broker unavailable, timeout, poison message, DLQ và partial send.
9. **Idempotency test:** gửi lại cùng event ID và xác nhận business effect chỉ áp dụng một lần.
10. **Concurrency test:** competing consumers, ordering và destination isolation.

Unit test cho feedback nhanh; integration test mới xác nhận broker semantics. Không nên thay thế một tầng bằng tầng khác.

## 32. Những điểm cần ghi nhớ

- `JmsItemReader` nhận message qua `JmsTemplate`; `JmsItemWriter` gửi item tới destination qua `JmsTemplate`.
- `MessageConverter` quyết định payload Java được chuyển thành `TextMessage`, `BytesMessage` hoặc dạng message khác như thế nào.
- Unit test có thể mock `JmsTemplate` để kiểm tra destination, số lần receive/send, payload và exception.
- Reader trả `null` khi không có message; Spring Batch hiểu là EOF. Queue rỗng tạm thời không nhất thiết có nghĩa batch đã hoàn tất.
- JMS `AUTO_ACKNOWLEDGE` có thể acknowledge message ngay khi receive; chunk rollback không tự redeliver message đã acknowledge.
- Muốn receive/ack tham gia chunk transaction, cần cấu hình JMS transaction manager phù hợp; local JMS transaction không tự atomic với database transaction.
- `JmsItemWriter` gửi message theo item; lỗi giữa chunk có thể để lại partial send nếu không có transaction bao phủ.
- Retry/restart có thể tạo duplicate publication; dùng event ID ổn định và idempotent consumer.
- Integration test với broker thật cần kiểm tra redelivery, `JMSRedelivered`, delivery count, selector, DLQ, expiration và transaction behavior.
- Queue, topic, durable subscription và selector có semantics khác nhau; test đúng loại destination.
- Test message converter riêng cho schema, type, Unicode và header/correlation metadata.
- Dùng destination riêng, timeout có giới hạn và cleanup để test độc lập, không treo.
- Nếu cần xử lý liên tục, cân nhắc message-driven architecture; `ItemReader`/EOF phù hợp hơn với một batch có điểm kết thúc xác định.

Kiểm thử message reader/writer cần đi xa hơn việc xác nhận một payload được nhận hoặc gửi. Hãy kiểm tra converter, destination, end condition, acknowledgement, transaction, redelivery, duplicate và failure window với broker tương thích production. Khi kết hợp unit test nhanh với integration test có transaction và idempotency rõ ràng, message-based batch mới có thể xử lý lỗi và restart mà không âm thầm làm mất hoặc nhân đôi sự kiện.
