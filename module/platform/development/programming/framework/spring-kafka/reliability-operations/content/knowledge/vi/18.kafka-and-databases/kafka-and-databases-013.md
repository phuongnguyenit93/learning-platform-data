# Kiểm thử failure giữa hai hệ thống

Một ứng dụng Spring Kafka thường phải phối hợp **Kafka và database** trong cùng một nghiệp vụ: nhận event từ Kafka rồi ghi PostgreSQL, tạo đơn hàng trong database rồi phát event, hoặc cập nhật database đồng thời gửi output và xác nhận offset đầu vào. Đây là các quy trình đi qua **hai hệ thống có transaction coordinator và cơ chế lưu trữ riêng**. Nếu một hệ thống đã commit trong khi hệ thống còn lại chưa commit, crash, timeout hoặc mất kết nối có thể tạo trạng thái không nhất quán.

**Kiểm thử failure giữa hai hệ thống** không chỉ kiểm tra “listener có retry khi lỗi hay không”. Mục tiêu là chủ động tạo lỗi đúng **ranh giới commit**, quan sát dữ liệu đã bền vững ở cả hai bên, và chứng minh hệ thống phục hồi theo một chính sách đã định: không mất business event quan trọng, không tạo tác dụng phụ lặp, hoặc có khả năng đối soát sai lệch.

Trong Spring Kafka, Kafka transaction có thể commit nguyên tử output Kafka và input consumer offset. Nhưng nó **không tự gộp database transaction thành một distributed ACID transaction**. Vì vậy, test phải bao phủ partial commit, outcome không rõ ràng, redelivery, duplicate và các vòng recovery sau khi instance restart.

## 1. Xác định hợp đồng độ tin cậy trước khi viết test

Trước khi dựng môi trường Testcontainers, cần diễn đạt rõ hệ thống đang hứa điều gì với nghiệp vụ.

Giả sử yêu cầu là: “Mỗi đơn hàng được ghi thành công trong database cuối cùng phải phát ra một `OrderCreated` để downstream xử lý.”

Những bảo đảm cần phân biệt:

| Bảo đảm | Ý nghĩa | Cách kiểm chứng |
|---|---|---|
| Database atomicity | Các thay đổi SQL thuộc cùng DB transaction commit/rollback cùng nhau | Đọc trạng thái DB sau khi inject failure. |
| Kafka transaction atomicity | Output Kafka và offset được đưa vào cùng Kafka transaction commit/abort cùng nhau | Đọc topic bằng consumer `read_committed`; kiểm tra committed offset. |
| At-least-once delivery | Event có thể được gửi/đọc lại, nhưng không bị bỏ vĩnh viễn trong điều kiện recovery được bảo đảm | Restart/replay và đợi eventual completion. |
| Idempotent business processing | Cùng event được xử lý nhiều lần nhưng business effect chỉ áp dụng một lần | Đếm số lần ghi sổ/thay đổi tiền hoặc unique business row. |
| Eventual publication | DB đã commit thì event cuối cùng xuất hiện trong Kafka, kể cả khi lần publish đầu lỗi | Kill/restart outbox publisher, phục hồi broker và kiểm tra event. |
| Ordering | Các event của cùng aggregate được áp dụng theo thứ tự yêu cầu | Tạo nhiều event cùng key và inject retry/rebalance. |
| Recovery visibility | Khi hai hệ thống lệch, hệ thống có log/metric và quy trình sửa được | Kiểm tra outbox pending, alert hoặc reconciliation result. |

**Exactly-once** cần nói rõ phạm vi. Exactly-once ở phía Kafka không có nghĩa database/API ngoài Kafka sẽ chỉ thực thi nghiệp vụ một lần. Trong test, thường thiết kế dựa trên **at-least-once delivery + idempotent processing** để bảo đảm kết quả cuối cùng đúng.

### 1.1. Dùng event ID ổn định

Mỗi lần retry hoặc replay nên mang một `eventId` ổn định:

~~~json
{
  "eventId": "f08b42c3-3e24-440f-ae73-cbb3c5d8c6b0",
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

Nếu publisher phát lại cùng event sau sự cố, event ID **không được thay đổi**. Nếu tạo UUID mới mỗi lần retry, downstream khó nhận ra đó là cùng business event, dù Kafka producer đã bật idempotence.

Trong database, có thể dùng unique constraint cho `event_id` và `order_id` theo chính sách nghiệp vụ. Test phải quan sát **số business effect**, không chỉ đếm số lần listener được gọi.

## 2. Vẽ commit boundaries của luồng cần kiểm thử

Có ít nhất ba mô hình phổ biến, mỗi mô hình có failure window khác nhau:

~~~text
A. DB-first synchronous producer:
   Begin DB -> SQL -> Kafka send (transactional)
   -> DB COMMIT -> Kafka COMMIT

B. Kafka transactional listener + DB:
   Begin Kafka TX -> poll/handle -> Begin DB -> SQL
   -> DB COMMIT -> Kafka output + input offsets COMMIT

C. Transactional outbox:
   Begin DB -> SQL business + INSERT outbox -> DB COMMIT
   -> Outbox publisher -> Kafka publish -> mark sent/CDC checkpoint
~~~

Mô hình A và B có **hai commit độc lập**. Mô hình C không cố commit DB và Kafka cùng một lúc; nó ghi một ý định publish bền vững trong DB trước, rồi xử lý phát event bất đồng bộ.

Bộ test phải xác định **hệ thống nào commit trước**. Không suy luận commit order chỉ từ thứ tự dòng `repository.save()` và `kafkaTemplate.send()`, vì hai lệnh này thường chạy **trước** commit thực tế.

### 2.1. Failure matrix bắt buộc

| Mốc chèn lỗi | DB đã commit? | Kafka đã commit? | Hiện tượng cần quan sát |
|---|---|---|---|
| Trước khi ghi DB | Chưa | Chưa | Không có business state/event mới. |
| Sau SQL nhưng trước DB commit | Chưa | Chưa | DB rollback; không có committed event. |
| Ngay sau DB commit, trước Kafka commit | **Rồi** | Chưa hoặc chưa rõ | Partial commit có thể xuất hiện; phải recover/outbox/reconcile. |
| Kafka commit request đã gửi nhưng response thất lạc | Rồi | **Không rõ** | Không được suy luận từ exception rằng event chắc chắn chưa được ghi. |
| Sau cả hai commit nhưng trước HTTP response | Rồi | Rồi | Client retry có thể tạo duplicate command nếu thiếu idempotency. |
| Sau Kafka publish từ outbox nhưng trước đánh dấu sent | Rồi | Rồi | Outbox phát lại event; consumer phải chịu được duplicate. |
| Sau DB commit trong Kafka listener nhưng trước input offset commit | Rồi | Chưa commit offset | Input có thể redelivery; DB phải idempotent. |

Một test được coi là có ý nghĩa khi nó chứng minh **dữ liệu sau sự cố** và **dữ liệu sau khi hệ thống phục hồi**, không chỉ xác nhận một exception được ném ra.

## 3. Thiết lập môi trường tích hợp đủ thật

Nên dùng database và Kafka broker thật trong môi trường kiểm thử, chẳng hạn **PostgreSQL Testcontainers** kết hợp **Kafka Testcontainers**. Một unit test mock `JdbcTemplate` và `KafkaTemplate` không thể chứng minh commit, visibility, offset hoặc transaction timeout như trên hệ thống thật.

Ví dụ cấu trúc JUnit 5 + Spring Boot, minh họa cách đưa endpoint động vào application context:

~~~java
@Testcontainers
@SpringBootTest
class KafkaDatabaseFailureIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test");

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse("apache/kafka:3.8.1"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.kafka.bootstrap-servers",
                kafka::getBootstrapServers);
        registry.add("spring.kafka.producer.transaction-id-prefix",
                () -> "failure-it-tx-");
    }
}
~~~

Đoạn code là khung test, cần import, module Testcontainers Kafka/PostgreSQL và classpath Spring Boot phù hợp. Package của `KafkaContainer` và Docker image support tùy phiên bản Testcontainers, vì vậy chọn image/API đúng dependency đang sử dụng thay vì mặc định mọi version giống nhau.

Các thành phần bổ sung hữu ích:

- **Toxiproxy** để cắt/điều tiết kết nối giữa application với broker hoặc database.
- **Failpoint/barrier** trong application để dừng ở những đoạn mã sát commit boundary.
- **Một process ứng dụng riêng** để kill process thật, thay vì chỉ ném exception trong cùng JVM test.
- **AdminClient** để lấy committed offsets/metadata của consumer group.
- **Test consumer** cấu hình `isolation.level=read_committed` để quan sát output Kafka.
- **Database query trực tiếp** sau sự cố để phân biệt transactional state với dữ liệu còn trong persistence context.

Không dùng chung consumer group và transactional ID giữa các test chạy song song. Mỗi test nên có namespace topic/group/instance ID riêng hoặc reset môi trường có kiểm soát.

## 4. Vì sao cần fault injection đúng ranh giới?

Ném exception tại đầu listener chỉ kiểm tra luồng rollback đơn giản. Nó **không** tái hiện trường hợp nguy hiểm hơn: **DB đã commit thành công, nhưng Kafka chưa commit**.

Ví dụ một test thiếu giá trị:

~~~java
when(repository.save(any())).thenThrow(new RuntimeException("db failure"));
assertThrows(RuntimeException.class, () -> service.handle(command));
~~~

Test này chỉ kiểm tra method xử lý lỗi khi repository ném exception; không có transaction DB thực sự commit rồi Kafka commit thất bại.

Để kiểm tra failure window, cần điều khiển ứng dụng ở những mốc như:

~~~text
[1] Sau SQL, trước DB COMMIT
[2] Ngay sau DB COMMIT, trước KAFKA COMMIT
[3] Trong lúc request commit Kafka đang gửi
[4] Sau KAFKA COMMIT, trước cập nhật tracking/outbox state
[5] Sau cả hai commit, trước response hoặc offset acknowledgment
~~~

Không phải mọi mốc đều dễ inject bằng một hook trong cùng method. Spring transaction synchronization, lifecycle callback và độ ưu tiên callback cần được hiểu chính xác. Nếu cần bảo đảm mạnh về **thời điểm** của failure, hãy dựng seam rõ ràng trong luồng thử nghiệm hoặc chạy ứng dụng riêng để control crash/network tại boundary.

## 5. Test DB-first: lỗi trước DB commit

Ở mô hình DB-first dùng database transaction làm primary, lỗi khi thực hiện SQL hoặc validation trước commit thường phải dẫn đến DB rollback, trong khi Kafka transaction cũng không trở thành output đã commit.

Ví dụ:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void createOrder(CreateOrder request) {
    orderRepository.insert(request.orderId());

    kafkaTemplate.send(
            "orders.created",
            request.orderId(),
            new OrderCreated(request.eventId(), request.orderId()));

    if (failureSwitch.failBeforeDbCommit()) {
        throw new IllegalStateException("injected-before-db-commit");
    }
}
~~~

Test cần xác nhận:

1. Method kết thúc bằng exception.
2. Đọc lại database trong **transaction mới**: không có order được lưu.
3. Consumer `read_committed`: không nhìn thấy `OrderCreated` đã commit.
4. Event không bị mất khỏi inbox hoặc command queue theo thiết kế, nếu có nguồn đầu vào cần retry.
5. Application không để transactional producer bị giữ trong trạng thái không thể sử dụng.

Nếu dùng JPA, nhớ `flush()` không đồng nghĩa `commit()`; test phải kiểm tra dữ liệu sau khi transaction kết thúc, không chỉ gọi `entityManager.flush()`.

## 6. Test cửa sổ DB commit thành công, Kafka commit thất bại

Đây là kịch bản quan trọng nhất của **DB-first commit order**. Khi database đã commit, không có lời gọi rollback thông thường nào có thể thu hồi transaction đó.

~~~text
DB COMMIT OK
      |
      +---- fault injection: Kafka unavailable / TX commit fails
      |
KAFKA COMMIT FAILED hoặc UNKNOWN
      |
      +---- DB row vẫn tồn tại
      +---- Kafka event có thể chưa visible
      +---- recovery phải có dữ liệu để đối soát
~~~

### 6.1. Điều khiển mốc bằng hai method có transaction riêng

Một mô hình giúp test đạt mốc chính xác hơn là **Kafka transactional listener gọi database writer trong bean khác**:

~~~java
@Service
public class OrderDbWriter {

    private final JdbcTemplate jdbc;

    public OrderDbWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void apply(OrderEvent event) {
        jdbc.update(
                "INSERT INTO processed_orders (event_id, order_id) "
                + "VALUES (?, ?) ON CONFLICT DO NOTHING",
                event.eventId(), event.orderId());
    }
}
~~~

Listener có container Kafka transaction:

~~~java
@KafkaListener(
        topics = "orders.in",
        containerFactory = "transactionalListenerFactory")
public void onEvent(ConsumerRecord<String, OrderEvent> record) {
    dbWriter.apply(record.value());       // DB commit khi method trả về

    failureGate.afterDbCommit();          // điểm chặn phục vụ test

    kafkaTemplate.send(
            "orders.out",
            record.key(),
            new OrderAccepted(record.value().eventId()));
}
~~~

Khi `dbWriter.apply()` đã trả về thành công qua Spring proxy, DB transaction của nó đã kết thúc. Kafka listener container vẫn chưa commit Kafka transaction hiện tại cho tới khi listener hoàn tất. `failureGate` là seam test, **không phải API built-in của Spring Kafka**.

Trong test, cho gate báo đã đến mốc này rồi inject lỗi: ngắt Kafka network của **application process** bằng Toxiproxy, dừng application process hoặc ném exception để buộc Kafka transaction rollback. Tùy cách inject, test lần lượt kiểm tra:

- DB đã có `processed_orders(event_id)`.
- Kafka transaction output chưa commit và input offset chưa commit, hoặc kết quả commit vẫn chưa rõ khi network đứt đúng thời điểm.
- Khi broker/ứng dụng hoạt động lại, input record được giao lại.
- Unique constraint giúp DB không tạo business effect lần thứ hai.
- Output Kafka sau recovery nhất quán với event ID ban đầu.

Lưu ý: nếu chỉ ném exception ở `failureGate`, test đang kiểm tra **rollback Kafka sau DB commit** (deterministic). Nếu muốn chứng minh **Kafka commit request bị mất phản hồi**, phải inject ở đường network/commit request; đó là một kịch bản khác.

### 6.2. Không chặn trong cùng JVM rồi tưởng đã crash

Một failpoint dùng `CountDownLatch` hữu ích cho việc dừng tạm thời và điều khiển thứ tự chạy. Nhưng gọi `Thread.interrupt()`, ném exception hoặc hủy một future **không giống process crash**:

- Spring có thể chạy finally/rollback/lifecycle callbacks.
- Kafka producer có thể được đóng đúng cách.
- Database connection có thể còn sống và cleanup tự động.
- Transaction commit có thể được framework xử lý khi method trở về.

Muốn kiểm thử hard crash, chạy Spring Boot application như một **child process/container** rồi kill process từ một test controller độc lập. Sau đó khởi động lại cùng cấu hình group và quan sát trạng thái đã bền vững.

## 7. Test Kafka-first: Kafka event đã commit, database chưa commit

Dù chủ đề chính của nhiều ứng dụng là DB-first, bộ kiểm thử failure giữa hai hệ thống nên có cả hướng ngược lại nếu kiến trúc có luồng Kafka-first hoặc nested transactions.

~~~text
Kafka output COMMIT thành công
         |
         v
DB COMMIT lỗi
         |
         +---- Consumer thấy Kafka event
         +---- DB không có business state tương ứng
~~~

Ví dụ, một service dùng Kafka transaction outer/inner theo cấu hình riêng rồi cố gắng ghi DB sau đó. Lỗi database có thể khiến event đã visible trước khi business state tồn tại.

Test phải chứng minh có hoặc không có tình huống này theo thiết kế cụ thể. Nếu yêu cầu “downstream không bao giờ thấy order chưa tồn tại”, Kafka-first có thể không phù hợp trừ khi có cơ chế bù trừ, trạng thái pending hoặc hợp đồng eventual consistency được chấp nhận.

**Không suy luận Kafka-first chỉ từ việc `kafkaTemplate.send()` được gọi trước `repository.save()`**. Phải kiểm chứng transaction commit boundary thật.

## 8. Test unknown outcome khi mất phản hồi commit

Một dạng lỗi khó hơn failure rõ ràng là **unknown outcome**:

~~~text
Application                        Kafka broker
     |                                  |
     +---- EndTxn(COMMIT) request ------>|
     |                                  | commit có thể đã thành công
     X  Mất network trước response      |
     |                                  |
     +---- Không biết chắc kết quả ------+
~~~

Ứng dụng có thể nhận timeout hoặc exception, nhưng broker có thể đã commit. Nếu test tự giả định “có exception nên event chắc chắn không tồn tại”, kết luận đó không đáng tin cậy.

Một test unknown outcome cần:

1. Dùng event ID cố định và quan sát dữ liệu downstream sau khi kết nối trở lại.
2. Kiểm tra Kafka record bằng consumer `read_committed`.
3. Không tạo event ID mới khi thử lại.
4. Kiểm chứng deduplication nếu retry dẫn tới duplicate output.
5. Đánh dấu tình huống **cần reconciliation** thay vì phân loại cứng thành “đã commit” hoặc “chưa commit” dựa trên exception.
6. Ghi nhận kết quả test bằng trạng thái thực tế ở broker và database.

Muốn tạo ra mốc network chính xác cần test harness có quyền điều khiển đường đi request/response, đôi khi phải dùng proxy hoặc instrumentation có chủ đích. Không coi việc tắt broker ngẫu nhiên là bằng chứng chắc chắn đã chặn đúng commit response.

## 9. Test redelivery sau DB commit trong Kafka listener

Một lỗi phổ biến: **DB đã ghi bền vững, nhưng Kafka input offset không commit**. Kafka consumer group có thể giao lại cùng record khi restart hoặc rebalance.

Ví dụ input `PaymentCaptured(eventId=E-5, amount=100)`:

~~~text
Consumer nhận E-5
       |
       v
Database tăng/giảm số dư hoặc ghi ledger
       |
       v
DB COMMIT thành công
       |
       v
Kafka transaction rollback / offset chưa commit
       |
       v
E-5 redelivery
       |
       v
Business operation có nguy cơ chạy lần 2
~~~

Test không chỉ đếm số lần listener gọi; phải xác nhận **số lần thay đổi dữ liệu nghiệp vụ**.

Một thiết kế inbox/idempotency trong PostgreSQL:

~~~sql
CREATE TABLE consumed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE account_ledger (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    amount BIGINT NOT NULL
);
~~~

Trong một database transaction, đầu tiên insert marker với `ON CONFLICT DO NOTHING`; chỉ xử lý thay đổi ledger nếu insert marker thành công. Nếu lỗi business khiến DB transaction rollback, marker phải rollback cùng ledger.

Test gửi lại cùng event ID hai hoặc nhiều lần và xác nhận:

- Marker có đúng một row cho consumer/event.
- Ledger có đúng một transaction nghiệp vụ.
- Offset Kafka sau recovery tiến đúng khi listener hoàn tất.
- Nếu listener xử lý duplicate, nó vẫn có thể xác nhận thành công mà không thực hiện lại side effect.

Không coi việc `account.balance` cuối cùng “trông đúng” là đủ nếu hệ thống có audit hoặc side effect khác như email, gọi payment API, hay ghi bảng ledger. Hãy kiểm tất cả những hiệu ứng không được phép lặp.

## 10. Test transactional outbox qua failure giữa DB và Kafka

**Transactional outbox** đổi bài toán từ “hai commit phải xảy ra cùng lúc” thành “DB lưu bền vững business state và ý định phát event trong cùng transaction; publisher có thể retry về sau”.

~~~text
CreateOrder
     |
     v
DB TRANSACTION
  +---- orders INSERT
  +---- outbox_events INSERT
     |
     v
DB COMMIT
     |
     v
Outbox publisher -> Kafka
     |
     v
Mark published / CDC checkpoint
~~~

### 10.1. Các bất biến cần chứng minh

| Tình huống | Điều phải đúng |
|---|---|
| Lỗi trước DB commit | Không có order mới và không có outbox event mới. |
| DB commit thành công, Kafka down | Order và outbox event còn trong DB; publisher không làm mất event. |
| Kafka phục hồi | Outbox event cuối cùng được publish, dùng cùng event ID. |
| Publisher chết sau publish, trước mark sent | Có thể publish duplicate nhưng downstream không áp dụng business effect hai lần. |
| Hai publisher cạnh tranh | Cơ chế claim/lock không để hai worker cùng thực hiện side effect bất kiểm soát. |
| Publish mãi thất bại | Outbox có retry state, cảnh báo và thủ tục vận hành; không bị xóa âm thầm. |

### 10.2. Ví dụ schema

~~~sql
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL
);
~~~

Business service ghi hai bảng trong cùng DB transaction. Trong test, khi inject exception trước commit, cả `orders` và `outbox_events` phải rollback. Khi Kafka down sau commit, cả hai row vẫn tồn tại và sẵn sàng cho publisher chạy lại.

### 10.3. Lỗi sau publish, trước mark sent

Test này xác nhận outbox delivery semantics đúng:

~~~text
Publisher đọc outbox event X
       |
       v
Kafka publish thành công
       |
       v
Inject crash trước UPDATE published_at
       |
       v
Publisher restart đọc lại X
       |
       v
Kafka có thể nhận X lần nữa
       |
       v
Consumer dựa trên eventId để deduplicate
~~~

Đừng kỳ vọng outbox loại bỏ mọi duplicate tại Kafka. Mô hình phổ biến là **at-least-once publication**. Test nên kiểm chứng event ID không đổi qua các lần publish và consumer không nhân đôi hiệu ứng.

Nếu dùng CDC (ví dụ Debezium outbox pattern), failure windows nằm ở connector offset/checkpoint và broker publication. Cần kiểm thử restart connector, snapshot/replay và duplicate thay vì chỉ kiểm tra polling publisher.

## 11. Fault injection: chọn công cụ phù hợp loại lỗi

| Phương pháp | Tạo được lỗi gì? | Giới hạn |
|---|---|---|
| Ném exception tại failpoint của service | Lỗi nghiệp vụ/rollback deterministic trước hoặc sau DB operation | Không mô phỏng hard crash hay mất response ở mức network. |
| Barrier/Latch và process controller | Dừng xử lý đúng giai đoạn trước khi kill | Cần test harness riêng để không bị deadlock. |
| Toxiproxy | Packet loss, latency, reset, cắt kết nối broker/DB | Khó đảm bảo packet bị cắt chính xác tại EndTxn nếu không instrumentation. |
| Stop/restart Kafka container | Broker unavailable, producer timeout, recovery | Có thể ảnh hưởng toàn bộ test, không chỉ một kết nối. |
| Stop/restart PostgreSQL container | DB connection failure, transaction failure | Không nên suy luận commit đã/ chưa xảy ra chỉ từ socket exception. |
| Kill ứng dụng con bằng supervisor test | Hard crash, không chạy cleanup thông thường | Cần process riêng, thu thập log và restart độc lập. |
| Tùy biến wrapper/transaction synchronization có chủ đích | Inject tại lifecycle seam cụ thể | Phải xác minh ordering thực tế của Spring callbacks. |
| Proxy API/database client giả lập lỗi | Mô phỏng dependency timeout hoặc response không rõ | Không thay thế commit test với database và Kafka thật. |

Nên dùng **hai lớp test**: unit/contract test nhanh với failpoint, và integration/failure test có broker/database thật. Đối với hard crash/unknown outcome, dùng test controller ngoài process.

Không đưa failpoint không được bảo vệ vào production. Nếu cần giữ một cơ chế chaos testing trong môi trường staging, hãy kiểm soát bằng configuration, quyền truy cập, audit và chỉ cho phép trên environment được phê duyệt.

## 12. Thiết kế failpoint mà không làm lệch code nghiệp vụ

Có thể định nghĩa một seam chỉ được bật trong test:

~~~java
public interface FailureGate {
    void afterDatabaseCommit();
    void beforeKafkaTransactionCompletes();
}
~~~

Implementation mặc định không làm gì:

~~~java
@Component
@ConditionalOnMissingBean(FailureGate.class)
class NoopFailureGate implements FailureGate {
    @Override
    public void afterDatabaseCommit() {
    }

    @Override
    public void beforeKafkaTransactionCompletes() {
    }
}
~~~

Trong test, một implementation sử dụng `CountDownLatch` để báo “đã đến boundary” và chờ controller tiếp tục. Quan trọng: tên phương thức như `afterDatabaseCommit()` chỉ chính xác nếu nó **thực sự được gọi sau DB transaction commit**, ví dụ từ một service transactional đã trả về qua proxy. Đừng đặt tên `afterCommit` cho một callback chạy khi SQL đã flush nhưng DB chưa commit.

Với Kafka transaction do listener container quản lý, code listener **không tự thực hiện final Kafka commit**. Do đó, một failpoint trong listener chỉ đặt được tại “trước khi listener trả về”; commit thực tế xảy ra sau đó ở container. Nếu cần can thiệp chính xác vào pha commit của transaction manager, phải dùng instrumentation thích hợp hoặc failpoint ở transaction lifecycle.

## 13. Kiểm chứng Kafka transaction bằng read_committed

Khi kiểm tra record bị rollback, dùng consumer với:

~~~java
Map<String, Object> config = Map.of(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers,
    ConsumerConfig.GROUP_ID_CONFIG, uniqueTestGroupId,
    ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest",
    ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed",
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class,
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
~~~

Đoạn này minh họa configuration map. Trong test thực tế, cấu hình deserializer phải khớp với kiểu event trên topic.

Các điều kiện quan trọng:

- `read_committed` không trả record từ transaction đã abort.
- Producer send future thành công **không** đủ chứng minh transaction commit.
- Consumer `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit/bị abort; dùng nó để test Kafka transaction visibility sẽ dễ kết luận sai.
- Với transaction còn mở, last stable offset có thể ảnh hưởng vị trí mà consumer `read_committed` đọc được.
- Kiểm tra output topic và **consumer group committed offset** bằng API thích hợp; chúng không phải cùng một quan sát.

Ví dụ logic kiểm tra offset: nếu input ở partition 0 offset 41 được xử lý và commit trong Kafka transaction, committed group offset sau đó thường là 42. Nếu transaction rollback, offset transaction chưa commit, dù consumer position trong bộ nhớ có thể đã tiến do poll.

Đừng chỉ xác nhận “topic có record” rồi tuyên bố thành công; phải xác nhận **record đã committed** và có event ID đúng.

## 14. Database assertion phải chạy sau transaction test

Một cạm bẫy phổ biến trong Spring tests: đặt `@Transactional` trực tiếp trên test method. Spring Test có thể mở một transaction bao quanh toàn test rồi rollback ở cuối. Điều đó hữu ích cho unit/integration test database thông thường, nhưng có thể che khuất commit thực của application và làm sai bài test phối hợp Kafka.

Với failure-window test:

- Tránh bọc toàn bộ test method trong test-managed transaction nếu đang cần quan sát **durable commit**.
- Để application service tự bắt đầu/kết thúc transaction.
- Dùng một connection/transaction mới để query trạng thái DB sau khi application hoàn tất hoặc crash.
- Nếu dùng JPA, clear persistence context hoặc mở EntityManager mới; không dựa vào entity đã cache.
- Khi cần kiểm tra isolation, xác định isolation level và database-specific behavior.

Ví dụ query trực tiếp:

~~~java
Integer count = jdbcTemplate.queryForObject(
        "SELECT count(*) FROM outbox_events WHERE event_id = ?",
        Integer.class,
        eventId);

assertThat(count).isEqualTo(1);
~~~

Nếu test mong database rollback, query phải được thực hiện khi service transaction đã thật sự kết thúc. Nếu query chạy trong cùng transaction chưa commit, test có thể đọc dữ liệu tạm và đưa ra kết luận sai.

## 15. Chạy restart/rebalance test có kiểm soát

Một failure có thể khiến consumer group rebalance, producer bị fence hoặc record được giao lại. Test nên chủ động đánh giá tình huống này:

~~~text
Instance A: poll event E
      |
      v
DB commit success
      |
      v
A bị kill trước Kafka offset commit
      |
      v
Consumer group rebalance
      |
      v
Instance B nhận lại partition
      |
      v
E redelivery
      |
      v
DB deduplication -> không nhân đôi effect
      |
      v
Kafka offset tiến sau xử lý thành công
~~~

Để test deterministic hơn, dùng **một input partition**, kiểm soát consumer instance và biết trước offset của event. Khi kiểm thử nhiều partition hoặc concurrency cao, cần phân biệt duplicate do redelivery của cùng partition với xử lý song song độc lập.

Nếu transaction producer A đã bị fence, không retry mãi trên producer session cũ. Test nên xác nhận instance hợp lệ tạo producer session mới và tiếp tục công việc. Việc trùng `transactional.id` giữa hai active-active replicas là lỗi cấu hình khác với một failover có kiểm soát.

## 16. Race conditions và thứ tự business event

Sự nhất quán không chỉ nằm ở số record. Sau failure/recovery, event có thể đến trễ hoặc bị xử lý lại ngoài thứ tự dự kiến, nhất là khi dùng retry topic, outbox đa worker hoặc nhiều aggregate.

Ví dụ cùng một order:

~~~text
OrderCreated (version 1)
OrderPaid    (version 2)
OrderShipped (version 3)
~~~

Nếu `OrderCreated` gặp sự cố publish và `OrderPaid` được phát trước, consumer downstream có thể thấy version 2 trước version 1. Tùy nghiệp vụ, điều này có thể không chấp nhận được.

Các test nên kiểm tra:

1. Kafka key theo `orderId`/aggregate ID đúng.
2. Publisher có bảo tồn thứ tự event của cùng aggregate khi outbox retry không.
3. Consumer có versioning hoặc buffering nếu event có thể out-of-order.
4. DLT/replay không áp dụng event cũ đè lên trạng thái mới.
5. Nếu dùng nhiều outbox workers, cơ chế claim có vô tình phá ordering theo aggregate không.

Kafka bảo đảm thứ tự **trong từng partition** theo thứ tự record được ghi. Nó không tự bảo đảm thứ tự business event nếu publisher phát chúng sai thứ tự hoặc đổi partition key qua các phiên bản.

## 17. Đặt kỳ vọng theo trạng thái cuối thay vì timing cứng

Failure giữa hai hệ thống thường liên quan thời gian bất định: leader election, transaction coordinator recovery, consumer rebalance, database reconnect và retry backoff.

Một test thiếu ổn định:

~~~java
publishEvent();
Thread.sleep(2000);
assertThat(orderRepository.count()).isEqualTo(1);
~~~

Nếu môi trường CI chậm hơn, test thất bại dù hệ thống đúng; nếu logic lỗi nhưng hoàn tất nhanh, test lại có thể pass sai.

Nên chờ **điều kiện quan sát được** với timeout hữu hạn, ví dụ:

~~~java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        assertThat(outboxRepository.countPending()).isZero();
        assertThat(ledgerRepository.countByEventId(eventId))
                .isEqualTo(1);
    });
~~~

Ví dụ trên minh họa dùng Awaitility. Điều kiện thành công cần gắn với SLO của hệ thống và event ID cụ thể. Không chỉ chờ “consumer group đang running” vì điều đó chưa chứng minh event đã xử lý.

Đối với những thời điểm **không mong có output**, chờ một khoảng nhỏ rồi đếm zero chỉ là bằng chứng yếu. Nên kết hợp producer transaction state, committed offset và mốc synchronization rõ ràng để xác nhận sự kiện bị abort/chưa commit.

## 18. Không phụ thuộc thứ tự kết quả mơ hồ của callback

Một sai lầm là viết:

~~~java
@Transactional
void createOrder() {
    writeDatabase();
    kafkaTemplate.send("orders", event);
    registerAfterCommitCallback(() -> throw new RuntimeException());
}
~~~

Rồi tuyên bố callback này chắc chắn chạy **trước Kafka transaction commit**. Thực tế thứ tự thực thi `TransactionSynchronization` phụ thuộc lifecycle, ordering của các synchronizations và cách transaction manager tích hợp. Nếu không xác minh order hoặc dùng một seam rõ ràng, injection có thể rơi vào mốc khác với dự định.

Cách đáng tin cậy hơn:

- Với Kafka transactional listener: đặt barrier **sau khi DB writer transactional hoàn tất**, nhưng trước listener return.
- Với DB-primary transaction synchronization: dùng instrumentation được xác minh về thứ tự commit hoặc wrapper transaction manager trong test để inject đúng secondary commit.
- Với hard crash: parent test kiểm tra DB đã commit, sau đó kill child process trước khi Kafka transaction hoàn tất.
- Với outcome không rõ: inject network fault ở tầng protocol rồi xác nhận dữ liệu thực tế, không giả định lỗi nghĩa là chưa commit.

Test description nên ghi rõ **mốc đã được bảo đảm** và **mốc chỉ được mô phỏng gần đúng**.

## 19. Failure matrix nâng cao cho outbox và DLT

Khi hệ thống dùng outbox, inbox, retry hoặc DLT, các trường hợp quan trọng mở rộng:

| Failure | Hành vi đúng |
|---|---|
| Outbox insert lỗi trong DB transaction | Business mutation cũng rollback. |
| Kafka down sau DB commit | Outbox pending còn lại; publisher retry khi broker phục hồi. |
| Publisher gửi thành công rồi mất kết nối trước ack | Có thể retry và duplicate; event ID ổn định. |
| Publisher nhận ack nhưng update published marker lỗi | Record có thể phát lại; dedup an toàn. |
| Consumer xử lý DB xong, offset commit lỗi | Event redelivery; inbox chặn duplicate side effect. |
| DLT publish lỗi do ACL/serializer | Không đánh dấu recovery thành công âm thầm. |
| Retry vượt giới hạn | Record được cách ly hoặc operator can thiệp theo runbook, không bỏ mất. |
| Schema thay đổi trong thời gian chờ | Publisher/consumer vẫn giải mã được event cũ hoặc có migration plan. |
| Reconciliation job restart giữa chừng | Có checkpoint và idempotent event replay. |
| Cùng event được replay từ DLT và redelivery từ main | Dedup vẫn ngăn double application. |

Không phải mọi hệ thống đều dùng DLT/outbox. Chọn các ca tương ứng với kiến trúc đang chạy, nhưng phải nêu rõ giới hạn của những ca chưa được kiểm thử.

## 20. Quan sát và thu thập bằng chứng trong test

Mỗi failure-window test nên sinh một **evidence bundle** tối thiểu:

- `eventId`, `aggregateId`, topic, partition, offset và consumer group.
- DB row count và giá trị business state sau failure và sau recovery.
- Outbox/inbox marker, retry count, published state nếu có.
- Kafka record đã commit theo `read_committed`.
- Committed offset của consumer group; không nhầm với consumer position trong bộ nhớ.
- Thời gian failure injection, restart, rebalance, retry và recovery.
- Exception class từ database, producer transaction, listener/error handler.
- Log correlation ID để truy ra thao tác của cả hai hệ thống.

Một sự cố Kafka commit có kết quả không rõ ràng nên được ghi nhận như **UNKNOWN** cho tới khi đối soát trạng thái. Test không nên tự chuẩn hóa lỗi đó thành `FAILED` hay `COMMITTED` chỉ dựa trên exception.

Trong production, metric hữu ích gồm:

| Metric | Để phát hiện |
|---|---|
| Secondary Kafka commit failures sau DB commit | Partial commit theo mô hình DB-first. |
| Outbox pending count/oldest age | Event bền vững đang bị mắc trước publish. |
| Inbox duplicate suppression count | Mức độ redelivery hoặc publisher duplicate. |
| Consumer lag per partition | Partition bị kẹt hoặc retry kéo dài. |
| DLT publish/recovery failure rate | Record không thể được cách ly/khôi phục. |
| Reconciliation mismatch count | DB và Kafka view chưa đồng nhất. |
| Transaction abort/fencing count | Vấn đề transaction coordinator, producer identity hoặc churn. |

## 21. Checklist viết test có ý nghĩa

Trước khi coi một bài kiểm thử failure giữa Kafka và database là đủ tốt, hãy trả lời:

1. **Hệ thống nào commit trước** trong đường code thực tế?
2. Test có dùng broker/database thật hay chỉ mock method?
3. Failpoint nằm **trước hay sau commit**, và có chứng cứ xác nhận mốc đó không?
4. Sau failure, test có đọc lại DB bằng transaction/connection mới không?
5. Kafka assertion có dùng `read_committed` nếu kiểm tra transaction visibility không?
6. Có kiểm tra input **committed offset**, không chỉ Kafka output không?
7. Nếu kết quả commit không rõ, recovery có dùng event ID ổn định không?
8. Khi record bị giao lại, business side effect có được thực hiện **đúng một lần về mặt nghiệp vụ** không?
9. Nếu Kafka down sau DB commit, có outbox/reconciliation để event cuối cùng được phát không?
10. Nếu publisher crash sau Kafka publish, consumer có chịu được duplicate không?
11. Nếu quá trình phục hồi kéo dài, metric và alert có đủ để vận hành không?
12. Test có deterministic, timeout hữu hạn và không dùng sleeps cứng để thay thế state checks không?
13. Transactional ID, topic và consumer group có cách ly giữa các ca test không?
14. Có kiểm thử hard crash thật bằng process riêng khi bài toán cần chứng minh crash consistency không?
15. Khi chạy rollback/redeploy, event schema và dữ liệu tồn đọng có tiếp tục được xử lý đúng không?

## 22. Lựa chọn chiến lược kiểm thử theo mức độ rủi ro

| Mức độ | Bộ test | Khi nào phù hợp |
|---|---|---|
| Nền tảng | Unit test idempotency/unique constraints và cấu hình error classification | Mọi service có Kafka + DB. |
| Tích hợp | PostgreSQL + Kafka Testcontainers, lỗi trước commit, redelivery, DLT | Service cần at-least-once và transaction semantics ổn định. |
| Chuyên sâu | Fault injection DB committed/Kafka rollback, unknown outcome, Toxiproxy | Workflow quan trọng, phụ thuộc commit synchronization. |
| Crash consistency | Ứng dụng child process, hard kill, restart, đối soát | Thanh toán, ledger, đặt hàng hoặc workflow cần bảo đảm recovery thực tế. |
| End-to-end | Outbox/inbox, nhiều replica, rebalance, CDC, event replay và reconciliation | Hệ thống nhiều service với yêu cầu vận hành lâu dài. |

Mức độ càng cao thì thời gian và chi phí kiểm thử càng lớn, nhưng cũng giúp phát hiện những lỗi mà mock hoặc happy-path test không thể nhìn thấy. Nên chạy test nhanh ở mỗi pull request, còn chaos/crash test nặng có thể được tổ chức riêng trong pipeline tích hợp có môi trường kiểm soát.

**Kiểm thử failure giữa hai hệ thống** là kiểm thử các trạng thái **đã commit, chưa commit và chưa thể biết chắc** của từng tài nguyên. Với Spring Kafka và database, mục tiêu không phải chứng minh rằng hai transaction độc lập bất ngờ trở thành một transaction nguyên tử, mà là chứng minh hệ thống **không mất dữ liệu nghiệp vụ quan trọng, có thể phục hồi sau partial commit và chịu được duplicate**. Một bộ test đáng tin cậy cần tạo lỗi đúng ranh giới, quan sát durable state từ cả hai phía và xác nhận kết quả cuối cùng bằng outbox, inbox, idempotency hoặc reconciliation đã được thiết kế rõ ràng.
