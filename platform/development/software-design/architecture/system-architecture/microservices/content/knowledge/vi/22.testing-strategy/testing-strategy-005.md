# Kiểm thử tích hợp với cơ sở dữ liệu và broker thực trong Microservices

Microservices thường lưu trạng thái trong cơ sở dữ liệu và trao đổi sự kiện qua message broker. Unit test có thể xác nhận một hàm xử lý đúng với dữ liệu giả lập, nhưng chưa chứng minh được câu SQL có chạy trên đúng database engine, transaction có được commit như mong đợi, message có đi qua exchange/topic, hay consumer có xử lý được sự kiện bất đồng bộ sau khi service đã trả HTTP response.

**Kiểm thử tích hợp (integration testing) với cơ sở dữ liệu và broker thực** chạy ứng dụng hoặc một phần ứng dụng cùng các hạ tầng thử nghiệm dùng **đúng engine, protocol và hành vi quan trọng** như production. Ví dụ: PostgreSQL trong container thật, RabbitMQ thật hoặc Kafka broker thật; ứng dụng kết nối bằng driver/client thật và thực hiện migration, truy vấn, publish, consume, acknowledge và retry theo cấu hình được chọn.

Mục tiêu là phát hiện lỗi tại **ranh giới giữa code và hạ tầng** trước khi triển khai: SQL dialect, schema migration, transaction boundary, locking, serialization, routing, consumer concurrency, duplicate delivery và xử lý lỗi. Mục tiêu không phải chứng minh mọi tính chất của toàn bộ môi trường production chỉ bằng một test container.

## 1. Phân biệt unit test, integration test và end-to-end test

| Mức kiểm thử | Thành phần được chạy | Điều cần chứng minh | Giới hạn |
| --- | --- | --- | --- |
| Unit test | Một lớp/hàm và dependency giả lập | Logic nghiệp vụ, thuật toán, validation | Không kiểm chứng driver, SQL, broker hoặc cấu hình thật |
| Integration test với database | Repository, transaction, migration và database engine thật | SQL, mapping, constraint, isolation, migration | Chưa xác nhận message broker và toàn luồng phân tán |
| Integration test với broker | Producer/consumer, serializer và broker thật | Publish, routing, delivery, acknowledgment, retry | Không tự kiểm chứng tất cả downstream hoặc nhà cung cấp ngoài |
| Integration test DB + broker | Service, database và broker thực trong môi trường cô lập | Tương tác giữa lưu dữ liệu, phát sự kiện và xử lý async | Chưa tương đương production nhiều vùng hoặc cả hệ thống |
| Contract test | Hợp đồng API/event giữa producer và consumer | Schema và tương thích các phiên bản | Không bảo đảm mọi thành phần vận hành cùng nhau |
| End-to-end test | Nhiều service và đường đi người dùng thực tế | Hành vi xuyên hệ thống từ đầu đến cuối | Tốn kém, khó cô lập lỗi và có thể không ổn định |

Một hệ thống khỏe mạnh thường có nhiều unit test nhanh, số lượng integration test đủ bao phủ các ranh giới có rủi ro, contract test khi các team phát hành độc lập và một nhóm nhỏ bài end-to-end cho luồng then chốt.

**“Thực” ở đây có nghĩa gì?** PostgreSQL chạy trong Testcontainers vẫn là PostgreSQL thật, xử lý SQL, index, constraint, transaction và lock theo engine đó. RabbitMQ container vẫn là một broker AMQP thật. Tuy nhiên một container đơn lẻ chưa mô phỏng hoàn toàn managed database với replica, failover, network policy hoặc một cụm broker nhiều node. Các đặc điểm đó cần thêm kiểm thử hạ tầng hoặc môi trường staging phù hợp.

## 2. Vì sao H2 hoặc mock broker có thể bỏ lọt lỗi?

Giả sử Order Service ghi đơn hàng vào PostgreSQL và phát OrderCreated tới RabbitMQ:

~~~text
HTTP POST /orders
       |
       v
  Order Service
       |
       +---- BEGIN TRANSACTION
       |       INSERT orders
       |       INSERT outbox_events
       |     COMMIT
       |
       +---- Outbox publisher ----> RabbitMQ exchange
                                        |
                                        v
                                  Notification consumer
                                        |
                                        v
                                  INSERT notification_jobs
~~~

Một unit test giả lập repository có thể cho rằng INSERT thành công; thực tế production có thể lỗi do unique constraint, JSONB, kiểu UUID, foreign key hoặc lock. Một mock publisher có thể trả thành công; thực tế RabbitMQ có thể không có exchange, binding key sai, quyền publish thiếu hoặc consumer không deserialize được payload.

Các trường hợp dễ bị bỏ sót khi dùng hạ tầng giả:

- **SQL dialect:** PostgreSQL có kiểu JSONB, UUID, cú pháp upsert, index và isolation khác H2.
- **Schema:** tên cột, NOT NULL, UNIQUE, khóa ngoại, migration và default value chỉ bộc lộ rõ khi chạy engine thật.
- **Transaction:** rollback/commit, visibility, lock contention và deadlock phụ thuộc DB engine, driver và cấu hình.
- **Connection pool:** sai URL, credential, timeout hoặc số connection không được thấy khi chỉ mock repository.
- **Message routing:** exchange/topic, routing key, queue binding, partition và subscription group là cơ chế thực của broker.
- **Serialization:** producer và consumer có thể không đồng ý về JSON schema, enum, timestamp, content type, headers hoặc version.
- **Delivery:** một message có thể được giao lại; acknowledgment và retry có thể tạo bản ghi trùng nếu consumer không idempotent.
- **Async timing:** consumer có thể chạy sau khi request gốc trả về; assert ngay tức thì thường gây flaky test.

Do đó, mỗi điểm tích hợp rủi ro cao cần ít nhất một bài kiểm thử đi qua driver, giao thức và hạ tầng tương ứng.

## 3. Xác định mục tiêu kiểm thử trước khi dựng container

Tránh dựng cả hệ thống microservices chỉ vì test một repository. Hãy chọn ranh giới nhỏ nhất vẫn đi qua thành phần thực cần chứng minh.

Ví dụ đối với Order Service:

| Cần kiểm tra | Hạ tầng phải chạy thật | Thành phần có thể thay bằng test double |
| --- | --- | --- |
| Migration tạo bảng và index đúng | PostgreSQL | Email gateway bên ngoài |
| Transaction rollback khi lưu đơn lỗi | PostgreSQL | Hệ thống thanh toán ngoài phạm vi test |
| Publish event với routing key/schema đúng | RabbitMQ + producer thật | Dịch vụ nhận email bên ngoài |
| Consumer xử lý message và lưu projection | RabbitMQ + PostgreSQL + consumer thật | API bên thứ ba được consumer gọi |
| Idempotency khi cùng event được giao hai lần | RabbitMQ + PostgreSQL | Clock hoặc nguồn ngẫu nhiên có thể điều khiển |
| Phục hồi sau broker restart | Broker thật với kịch bản failure có kiểm soát | Một số service không liên quan |

**Không mock chính thứ đang được kiểm thử.** Nếu mục tiêu là kiểm chứng giao tiếp với PostgreSQL, dùng PostgreSQL thật và repository/JDBC thật. Nếu mục tiêu là xử lý message RabbitMQ, dùng publisher/listener/broker thật. Có thể mock một nhà cung cấp SMS hoặc payment bên ngoài nếu nó nằm ngoài ranh giới cần kiểm tra.

## 4. Môi trường thử nghiệm: container cô lập và tái lập được

**Testcontainers** là một lựa chọn phổ biến cho integration test Java. Thư viện tạo container Docker từ test, cung cấp host/port/credential thực tế và dừng container theo vòng đời phù hợp.

Một môi trường lý tưởng có các tính chất:

1. **Tái lập:** dùng image version rõ ràng, migration cùng version ứng dụng, không phụ thuộc database cài tay trên laptop.
2. **Cô lập:** mỗi test hoặc test suite sở hữu dữ liệu, queue, topic, consumer group phù hợp; không dùng chung trạng thái production.
3. **Tự khởi động:** test có cơ chế chờ readiness, không yêu cầu người chạy mở terminal dựng hệ thống trước.
4. **Rõ ràng về quyền:** credential riêng cho test, không dùng secret production, không truy cập broker production.
5. **Dễ chạy ở CI:** runner có khả năng thực thi container, tải image, dung lượng và thời gian phù hợp.
6. **Không phụ thuộc thứ tự:** chạy riêng từng test hoặc đổi thứ tự không làm kết quả khác nhau.
7. **Có khả năng điều tra:** khi lỗi, lưu exception, container logs có chọn lọc, trạng thái migration và thông tin kết nối không nhạy cảm.

Không dùng Docker container sống sẵn do người lập trình tạo bằng tay làm giả định bắt buộc cho toàn bộ test; điều đó khiến CI và máy khác khó tái hiện.

### 4.1. Phụ thuộc Gradle minh họa

Một dự án Spring Boot dùng Gradle Groovy có thể khai báo các dependency test sau. Version của Testcontainers và các image phải được pin hoặc quản lý bằng BOM tương thích với bản Spring Boot/Java của dự án; ví dụ không tự quy định version cho repository đang dùng.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:rabbitmq'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu dự án không dùng JPA thì thay starter bằng JDBC hoặc R2DBC đúng công nghệ thật. Nếu dùng Kafka, thay module RabbitMQ bằng module Kafka tương ứng; không kéo cả hai broker vào một test khi hệ thống chỉ dùng một.

Ngoài dependencies, runtime test cần Docker hoặc một container runtime tương thích. Trong CI nên dùng image cache hoặc registry mirror có kiểm soát, tránh phụ thuộc ngẫu nhiên vào tốc độ tải image ngoài Internet.

## 5. Cấu hình Spring Boot kết nối PostgreSQL và RabbitMQ thật

Đoạn sau minh họa một test Spring Boot dùng **PostgreSQLContainer** và **RabbitMQContainer**. Các tên loại container và image có thể thay đổi theo major version Testcontainers đang dùng; ví dụ cần căn chỉnh với bộ thư viện được pin trong dự án.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class InfrastructureIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:4-management");

    @DynamicPropertySource
    static void databaseAndBroker(DynamicPropertyRegistry props) {
        props.add("spring.datasource.url", postgres::getJdbcUrl);
        props.add("spring.datasource.username", postgres::getUsername);
        props.add("spring.datasource.password", postgres::getPassword);

        props.add("spring.rabbitmq.host", rabbit::getHost);
        props.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        props.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        props.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void migrationCreatedOrdersTable() {
        Integer count = jdbc.queryForObject(
            "select count(*) from orders",
            Integer.class
        );
        assertThat(count).isNotNull();
    }
}
~~~

**Ý nghĩa kỹ thuật:**

- Testcontainers cung cấp một database engine và broker thật; Spring Boot khởi tạo application context và bean thực.
- DynamicPropertySource đưa endpoint/credential được cấp ở runtime vào đúng property Spring Boot; không hardcode cổng 5432/5672 của máy host.
- Đoạn code giả định ứng dụng có migration tạo bảng orders. Nếu không có migration, bài kiểm thử này phải báo lỗi; không nên âm thầm dùng Hibernate ddl-auto=create để che lỗi migration cần kiểm tra.
- Hai container được chia sẻ trong một test class. Các test method vẫn cần chiến lược cô lập dữ liệu, vì container class-level không có nghĩa trạng thái tự reset giữa từng phương thức.
- PostgreSQL và RabbitMQ image tag chỉ là ví dụ; pin theo chính sách cập nhật và version production mục tiêu. Đặc biệt với major-version thay đổi, cần xác minh module/container API tương thích.

### 5.1. Cấu hình migration

Nếu dùng Flyway hoặc Liquibase, nên để integration test thực thi **chính bộ migration của ứng dụng** lên database sạch. Khi ứng dụng chạy, test kiểm chứng bảng, constraint, index và dữ liệu seed cần thiết.

Ví dụ cấu hình test:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

Điểm quan trọng là tránh để ORM tự tạo schema mới làm test “xanh” trong khi migration đã quên cột hoặc tạo constraint sai. Với dự án dùng Liquibase, cấu hình tương đương theo engine đó; không bật song song hai công cụ nếu không phải thiết kế đã được thống nhất.

### 5.2. Kiểm thử SQL và constraint

Một repository test nên kiểm tra những điều mà mock không tái hiện được:

- Insert/read/update với kiểu UUID, numeric, timestamp, JSONB và nullability phù hợp.
- Unique constraint ngăn hai thực thể có business key trùng nhau.
- Foreign key và cascade/delete theo hợp đồng dữ liệu.
- Transaction rollback: lỗi ở giữa một nhóm thao tác không để lại nửa đơn hàng.
- Quy tắc locking khi hai giao dịch cùng cập nhật tồn kho hoặc trạng thái đơn.
- Mapping từ enum/string, timezone và số thập phân chính xác.

Ví dụ kiểm tra constraint ở tầng database:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void duplicateBusinessReferenceIsRejected() {
    String ref = "test-" + UUID.randomUUID();

    jdbc.update(
        "insert into orders (id, business_ref, status) values (?, ?, ?)",
        UUID.randomUUID(), ref, "NEW"
    );

    assertThatThrownBy(() -> jdbc.update(
        "insert into orders (id, business_ref, status) values (?, ?, ?)",
        UUID.randomUUID(), ref, "NEW"
    )).isInstanceOf(DataIntegrityViolationException.class);
}
~~~

Đoạn code giả định bảng orders có các cột id, business_ref, status và ràng buộc UNIQUE trên business_ref. Trong dự án thực, dùng schema và dữ liệu hợp lệ từ migration. Trọng tâm không phải tên cột mà là **constraint thật của PostgreSQL từ chối dữ liệu trùng**.

## 6. Kiểm thử broker thực: publish, routing, consume và ack

Một broker test cần xác nhận đường đi qua cơ chế mà broker triển khai, không chỉ kiểm tra method publish đã được gọi.

### Với RabbitMQ

- **Exchange** nhận message đã publish; loại exchange và routing key quyết định cách chuyển tiếp.
- **Queue và binding** quyết định consumer nào có thể nhận message.
- **Message serialization** quyết định JSON/headers/content type mà consumer có thể đọc.
- **Acknowledgment** thông báo message đã được xử lý theo chính sách.
- **Retry, dead-letter exchange/queue, TTL** phụ thuộc cấu hình producer, consumer và broker.
- **Publisher confirms/returns** có thể giúp xác định tình trạng message được broker tiếp nhận/routing trong phạm vi phù hợp, nhưng không chứng minh consumer đã hoàn tất side effect.

### Với Kafka

- **Topic/partition** xác định lưu trữ và thứ tự bên trong một partition.
- **Producer acknowledgment** thể hiện mức xác nhận theo cấu hình acks, replica và broker.
- **Consumer group/offset commit** quyết định vị trí đọc và khả năng phát lại.
- **Serializer/Schema Registry** có thể ảnh hưởng tính tương thích schema và khả năng decode.
- **Retry/DLQ** có thể do ứng dụng/framework quản lý và phải được kiểm tra trong môi trường thực.

Hai broker có ngữ nghĩa khác nhau. RabbitMQ ack và Kafka offset commit không phải một cơ chế; không thiết kế test chung bằng cách coi chúng tương đương hoàn toàn.

## 7. Kiểm thử hành vi bất đồng bộ mà không dùng sleep cố định

Consumer chạy ở thread khác hoặc process khác. Test phát message rồi gọi assert ngay thường thất bại vì consumer chưa kịp xử lý. Một cách chờ hợp lý là **poll cho đến khi trạng thái sau cùng xuất hiện hoặc hết deadline**, ví dụ dùng Awaitility.

Giả sử hệ thống có listener thật nhận OrderCreated từ RabbitMQ, sau đó ghi một bản ghi vào notification_jobs. Khi cả broker và database thật cùng chạy, có thể kiểm tra end-to-end ở phạm vi consumer bằng cách publish vào exchange thật:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

class OrderCreatedConsumerIntegrationTest {
    @Autowired
    RabbitTemplate rabbit;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void consumesOrderCreatedAndPersistsNotificationJob() {
        UUID eventId = UUID.randomUUID();
        String payload = """
            {"eventId":"%s","orderId":"order-demo","type":"OrderCreated"}
            """.formatted(eventId);

        rabbit.convertAndSend(
            "orders.events",
            "order.created",
            payload
        );

        await()
            .atMost(Duration.ofSeconds(15))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                Integer count = jdbc.queryForObject(
                    "select count(*) from notification_jobs where event_id = ?",
                    Integer.class,
                    eventId
                );
                assertThat(count).isEqualTo(1);
            });
    }
}
~~~

Đây là ví dụ cho **phần thân test**: test class cần kế thừa hoặc dùng cùng cấu hình container/Spring context đã trình bày ở phần 5. Ứng dụng cũng phải có exchange, binding, listener, schema message và bảng notification_jobs đúng hợp đồng; các tên ở đây là minh họa để thay bằng tên thật của module.

Vì sao Awaitility tốt hơn Thread.sleep(5000)?

- Nếu xử lý xong sau 100 ms, test có thể hoàn thành sớm.
- Nếu hệ thống thực sự lỗi, chờ đến thời hạn rõ ràng rồi đưa ra assert failure.
- Poll interval và timeout được khai báo tập trung, dễ hiệu chỉnh.
- Không dựa vào một thời gian giả định cố định trên máy phát triển hoặc CI chậm.

**Không kéo dài timeout vô hạn để làm test “xanh”.** Timeout phải có căn cứ từ hành vi của hệ thống và đặc điểm môi trường CI. Khi hết deadline, log container, trạng thái queue, consumer và database phải có đủ thông tin điều tra.

## 8. Tại sao phải kiểm thử trạng thái sau commit?

Một lỗi rất thường gặp: service ghi database trong transaction rồi publish event **trước khi transaction commit**. Consumer nhận event tức thì, truy vấn DB nhưng chưa thấy dữ liệu; hoặc DB rollback sau khi broker đã nhận event, khiến sự kiện mô tả một đơn hàng không tồn tại.

~~~text
Tình huống không an toàn:

BEGIN
  INSERT orders
  PUBLISH OrderCreated  ---> consumer có thể chạy ngay
ROLLBACK / COMMIT lỗi
  => broker đã có sự kiện, DB chưa lưu đơn hàng
~~~

Việc đổi thứ tự thành “commit DB trước, rồi publish” cũng không tự tạo atomicity:

~~~text
COMMIT orders thành công
Process crash trước khi publish
  => DB có đơn, broker không có sự kiện
~~~

Đó là **dual-write problem**: database và broker là hai hệ thống độc lập, một transaction database thông thường không bao trùm broker.

### Transactional Outbox

Một giải pháp phổ biến là ghi dữ liệu nghiệp vụ và outbox event **trong cùng transaction database**, rồi một publisher riêng đọc outbox và gửi broker.

~~~text
BEGIN
  INSERT orders
  INSERT outbox_events(event_id, type, payload, status=PENDING)
COMMIT
          |
          v
Outbox publisher đọc event chưa gửi
          |
          v
Publish đến RabbitMQ/Kafka
          |
          v
Ghi nhận trạng thái publish theo policy
          |
          v
Consumer xử lý event, bảo vệ idempotency
~~~

Test tích hợp nên kiểm tra:

1. Transaction thành công: có cả orders và outbox_events.
2. Transaction thất bại: không có một trong hai bản ghi bị commit riêng lẻ.
3. Publisher đọc outbox và gửi message thực đến broker.
4. Publisher hoặc process lỗi sau khi broker đã nhận nhưng trước khi mark sent: event có thể được gửi lại.
5. Consumer nhận message trùng nhưng chỉ tạo side effect nghiệp vụ một lần.

Outbox **không tự mang lại exactly-once delivery** trên toàn hệ thống. Nó giúp không mất intent phát sự kiện sau commit, nhưng duplicate vẫn có thể xuất hiện. Consumer idempotency là phần bắt buộc của thiết kế.

## 9. At-least-once delivery, idempotency và sự kiện trùng

Trong đa số hệ thống message thực tế, consumer phải chịu được **at-least-once** hoặc việc phát lại do retry/rebalance/restart. Một message bị xử lý xong nhưng ack/offset commit thất bại có thể được giao lại.

Một thiết kế idempotent thường dùng event_id hoặc idempotency key bền vững:

~~~sql
create table processed_events (
    consumer_name varchar(100) not null,
    event_id uuid not null,
    processed_at timestamptz not null default now(),
    primary key (consumer_name, event_id)
);
~~~

Trong cùng transaction xử lý side effect ở database, consumer có thể cố ghi processed_events; nếu khóa duy nhất đã tồn tại, bỏ qua xử lý lặp theo chính sách đã xác định. Tuy nhiên phải **gắn kiểm tra trùng và side effect trong cùng transaction** khi có thể. Kiểm tra SELECT “chưa có” rồi INSERT ở hai bước riêng mà không có constraint vẫn có race condition.

Ví dụ tình huống cần test:

~~~text
Given OrderCreated(eventId=E1) được publish hai lần.
When consumer nhận hai lần, kể cả chạy đồng thời.
Then notification_jobs chỉ có một bản ghi nghiệp vụ của E1.
And không có side effect gửi email/thu tiền thêm lần nữa.
~~~

Nếu side effect nằm ở API bên ngoài như SMS hoặc payment, giao dịch database không thể tự rollback email đã gửi. Cần idempotency key với bên thứ ba nếu được hỗ trợ, hoặc state machine và cơ chế đối soát riêng. Đừng kiểm tra “đã gửi một lần” chỉ bằng việc đếm row ở bảng processed_events nếu thực tế đã gọi API hai lần.

## 10. Transaction boundary và bẫy @Transactional trong test

Spring test có thể chạy method trong transaction riêng và rollback sau khi test kết thúc. Điều này hữu ích cho kiểm thử repository đồng bộ, nhưng dễ gây nhầm lẫn ở luồng asynchronous.

Ví dụ một test có @Transactional, insert order nhưng chưa commit, rồi publish message. Consumer trên connection khác không nhìn thấy order chưa commit. Test fail không phải vì broker sai mà vì **transaction của test đã che dữ liệu cần quan sát**.

Nguyên tắc:

- Dùng @Transactional rollback cho bài kiểm tra repository đồng bộ khi phù hợp.
- Với test publish/consume qua thread hoặc process khác, **ưu tiên tạo dữ liệu đã commit** trước khi gửi event.
- Khi cần điều khiển transaction trong test, dùng TransactionTemplate, TestTransaction hoặc gọi endpoint/service thật bảo đảm commit, tùy kiến trúc.
- Đối với kiểm thử lỗi và rollback, xác nhận trạng thái database **sau** khi transaction kết thúc.
- Không viết assert ở cùng persistence context rồi kết luận database thật đã commit; cần đọc lại với transaction/connection độc lập nếu muốn chứng minh visibility.

Một bài test “đơn hàng đã được commit thì consumer đọc được” khác về mục đích với bài test “repository save gọi đúng entity manager”. Cần chọn transaction boundary tương ứng.

## 11. Kiểm thử migration và tương thích schema

Microservices có thể được triển khai độc lập. Khi version mới thay đổi database hoặc cấu trúc message, integration test cần bao phủ cả schema hiện tại lẫn quá trình chuyển đổi.

### 11.1. Migration từ database sạch

Bắt đầu bằng PostgreSQL container mới, chạy toàn bộ migration của module từ version đầu. Xác nhận:

- Không lỗi cú pháp SQL trên engine mục tiêu.
- Bảng/index/constraint tồn tại đúng như ứng dụng yêu cầu.
- Hibernate/JDBC mapping tương thích schema sau migration.
- Seed/reference data cần thiết có và không bị chèn trùng.
- Những migration dữ liệu có tính idempotent hoặc có điều kiện rõ ràng.

Nếu hệ thống có database đã tồn tại từ nhiều version trước, bài test từ database sạch **chưa đủ**. Cần kiểm thử đường nâng cấp từ snapshot/schema version được hỗ trợ, với dữ liệu đã có, đúng quy định bảo mật của dữ liệu test.

### 11.2. Thay đổi event schema

Một producer mới có thể thêm trường tùy chọn; consumer cũ phải biết bỏ qua trường không quen thuộc nếu hợp đồng cho phép. Ngược lại, việc đổi tên trường bắt buộc hoặc thay enum có thể làm consumer crash.

Nên có test với các payload điển hình:

- Producer mới → consumer hiện tại.
- Producer cũ → consumer mới trong giai đoạn rollout.
- Thiếu trường tùy chọn, xuất hiện trường mới.
- Trường bắt buộc bị thiếu/sai kiểu.
- Event được phát lại sau nhiều giờ/ngày từ DLQ hoặc log broker.

Contract test kiểm tra tương thích schema, còn broker integration test xác nhận serializer, content type, headers, routing và consumer configuration cùng hoạt động thật.

## 12. Cô lập dữ liệu, queue và consumer giữa các test

Testcontainers giúp tạo môi trường thật, nhưng **không tự cô lập mọi phương thức test**. Nếu nhiều test dùng chung database hoặc queue, có thể ảnh hưởng lẫn nhau.

Các phương án:

### 12.1. Database

- Dùng database/schema/container riêng cho từng test class khi cần cô lập mạnh.
- Dùng @Transactional rollback cho repository test đồng bộ phù hợp.
- Dọn dữ liệu bằng SQL có kiểm soát giữa các test; tôn trọng thứ tự foreign key và các background worker đang chạy.
- Sinh ID/business key độc nhất bằng UUID, tránh hardcode cùng một order ID cho mọi test.
- Đối với test async, chờ consumer hoàn tất rồi mới dọn; nếu dọn quá sớm consumer có thể ghi lại dữ liệu sau cleanup.
- Không tái dùng database production hoặc staging dùng chung để thử các thao tác phá hủy.

### 12.2. RabbitMQ

- Tạo queue/exchange/routing key riêng cho nhóm test hoặc dùng test namespace hợp lệ.
- Nếu các test dùng chung queue, consumer có thể “ăn” message của bài khác; tránh tranh chấp.
- Dọn queue sau khi chắc chắn không còn consumer đang xử lý; cân nhắc việc purge có thể xóa message của test song song.
- Kiểm tra policy retry/DLQ bằng queue quan sát riêng, đừng giả định message đi thẳng về queue gốc khi fail.
- Broker side effect có thể không rollback khi transaction của test kết thúc.

### 12.3. Kafka

- Dùng topic và consumer group riêng cho test khi phù hợp.
- Đọc từ đúng offset và bảo đảm consumer đã sẵn sàng; nếu test bắt đầu subscribe sau khi publish, hành vi phụ thuộc auto-offset-reset và group state.
- Dùng event key nhất quán khi cần kiểm thử thứ tự theo partition.
- Khi test chạy song song, tránh cùng group/topic/offset làm test tranh nhau message ngoài ý muốn.
- Cleanup topic và trạng thái consumer group cần cân nhắc chi phí và giới hạn API broker.

**Test isolation là một phần của tính đúng đắn.** Một bài test chỉ pass khi chạy riêng nhưng fail khi chạy cả suite thường báo hiệu trạng thái dùng chung, race condition hoặc phụ thuộc thứ tự.

## 13. Kiểm thử consumer failure và chính sách retry

Không chỉ kiểm tra happy path. Một consumer thực có thể gặp dữ liệu không hợp lệ, DB unavailable, lỗi tạm thời, lỗi vĩnh viễn hoặc việc xử lý kéo dài.

| Sự cố | Hành vi cần định nghĩa | Điều cần assert |
| --- | --- | --- |
| Payload JSON sai hoặc schema không hỗ trợ | Reject hoặc chuyển DLQ theo policy | Không mất dấu sự kiện, không retry vô hạn |
| DB timeout tạm thời | Retry/backoff có giới hạn | Không tạo side effect trùng |
| Event đã xử lý | Idempotent skip hoặc xác nhận an toàn | Không thêm business record mới |
| Consumer crash trước ack | Broker có thể redeliver | Kết quả cuối cùng đúng |
| Publish đến exchange/topic sai | Báo lỗi hoặc unroutable theo broker config | Có tín hiệu vận hành, không giả thành công |
| Hàng đợi tăng nhanh | Backpressure và giới hạn concurrency | Không cạn toàn bộ thread/connection |
| Lỗi nghiệp vụ không thể khắc phục | Không retry vô hạn | Chuyển DLQ hoặc trạng thái xử lý lỗi |
| Event cũ sau schema upgrade | Tương thích hoặc từ chối có kiểm soát | Không crash loop hoặc mất dữ liệu |

Một integration test “publish thành công” không chứng minh message được xử lý thành công. Nên có ít nhất một test xác nhận **trạng thái sau cùng** của consumer bằng dữ liệu được commit hoặc output quan sát được.

### 13.1. Dead-letter queue

Nếu hệ thống định nghĩa DLQ, hãy gửi message lỗi có chủ đích, chờ message xuất hiện trong DLQ và xác nhận metadata lý do phù hợp. Không để test thực hiện vòng retry dài theo cấu hình production; có thể dùng policy retry rút gọn cho môi trường test nhưng phải giữ cùng kiểu xử lý và ranh giới ngữ nghĩa.

Một poison message không được làm tất cả message hợp lệ phía sau ngừng xử lý vô hạn, trừ khi đây là chính sách đã cân nhắc về thứ tự và an toàn.

### 13.2. Broker unavailable và network failure

Có thể kiểm thử quá trình service ứng xử khi broker không khả dụng bằng cách dừng kết nối hoặc mô phỏng fault mạng có kiểm soát. Kiểm tra:

- Producer timeout/confirm failure có được truyền thành trạng thái đúng không?
- Outbox có giữ event chưa phát để retry sau khi broker phục hồi không?
- Retry có backoff, giới hạn và không làm tăng request vô hạn không?
- Khi broker trở lại, event có được phát/consume và kết quả cuối có đúng không?
- Telemetry có cho thấy publish failure, outbox backlog hoặc consumer lag không?

Các bài failure test nên cô lập riêng để không làm ảnh hưởng test khác sử dụng chung container; chạy song song mà dừng broker chung sẽ tạo kết quả không xác định.

## 14. Kiểm thử nhất quán và độ trễ trong microservices

Phần lớn giao tiếp qua broker là **eventual consistency**: một service commit dữ liệu, service khác cập nhật read model hoặc trạng thái sau đó. Test cần xác định đúng mốc hoàn tất thay vì assert đồng bộ không có căn cứ.

Ví dụ:

~~~text
POST /orders -> 201 Created
  Order DB có order trạng thái CREATED
  Outbox có OrderCreated
  Publisher gửi broker
  Inventory consumer cập nhật reservation
  Notification consumer tạo notification job
  API query cuối cùng thấy trạng thái READY
~~~

Một test nên định nghĩa **điều kiện cuối** và **deadline**:

- Khi tạo order thành công, record orders phải commit ngay theo hợp đồng.
- Outbox event phải tồn tại trong cùng transaction.
- Trong khoảng thời gian phù hợp, consumer dự kiến tạo kết quả và không nhân đôi.
- Nếu chưa đạt trạng thái cuối trước timeout, test thất bại với đủ thông tin.
- Không coi eventual consistency là lý do cho phép mọi trạng thái không rõ ràng vô thời hạn.

Nếu hệ thống có saga hoặc workflow nhiều bước, test cần bao phủ chuyển trạng thái và bù trừ (compensation). Ví dụ thanh toán thất bại sau khi giữ hàng cần có hành vi hoàn trả trạng thái nhất quán; không kiểm tra chỉ rằng một message đã được publish.

## 15. Đồng thời, lock và race condition trên database thật

Mô hình microservices có thể xử lý nhiều yêu cầu song song. Repository fake chạy tuần tự thường không lộ race condition mà PostgreSQL thật sẽ thể hiện.

Một bài test đặt hàng cạnh tranh có thể tạo hai tác vụ cùng giữ một đơn vị tồn kho:

~~~text
Stock(item A) = 1

Request 1: reserve(A, quantity=1) ----+
                                      +---- chạy đồng thời
Request 2: reserve(A, quantity=1) ----+

Kỳ vọng:
- Chỉ một reservation thành công.
- Stock không âm.
- Request còn lại nhận kết quả hết hàng hoặc conflict hợp lệ.
~~~

Để kiểm chứng, test phải tạo **concurrency thật**, ví dụ hai task với barrier để bắt đầu gần đồng thời, mỗi task dùng transaction/connection riêng. Assert kết quả sau commit và kiểm tra ràng buộc DB. Không gọi hai method liên tiếp trong một thread rồi coi đó là concurrency test.

Các kỹ thuật ứng dụng có thể dùng gồm:

- Update có điều kiện: UPDATE stock SET quantity = quantity - 1 WHERE item_id = ? AND quantity >= 1.
- Optimistic locking với version column và retry có giới hạn.
- Pessimistic locking khi yêu cầu serialize thao tác.
- Unique constraint bảo vệ business key.
- Transaction isolation phù hợp với bất biến nghiệp vụ.

Test cần kiểm chứng **invariant**, không quá phụ thuộc vào thứ tự scheduling. Ví dụ “có đúng một giao dịch thành công, tồn kho cuối bằng 0” bền vững hơn “request số 1 phải thắng”.

## 16. Test broker không phải lúc nào cũng cần cả hệ thống

Để giữ integration test nhanh và ổn định, có thể chia bộ kiểm thử:

**Repository integration tests:** chạy PostgreSQL thật, test migrations, mapping, transaction, constraints và SQL dialect. Không bật Rabbit listener nếu không liên quan.

**Messaging integration tests:** chạy broker thật, producer/consumer và serializer đúng; dùng handler test hoặc DB thật tùy side effect cần chứng minh.

**DB + broker workflow tests:** chạy cả PostgreSQL và broker thật, kiểm tra outbox, consumer idempotency và kết quả sau cùng.

**Contract tests:** kiểm tra schema và phiên bản event/API mà không cần toàn bộ topology chạy mỗi lần.

**End-to-end smoke tests:** triển khai những service quan trọng trong staging hoặc môi trường tạm và kiểm tra luồng nghiệp vụ người dùng.

Nên ưu tiên các bài kiểm thử **có tín hiệu phân biệt được lỗi nằm ở đâu**. Nếu một bài test khởi động 15 service, fail có thể rất khó khoanh vùng; với test nhỏ, lỗi được quy về ranh giới database hoặc broker rõ hơn.

## 17. Tổ chức fixture và dữ liệu kiểm thử

Dữ liệu test nên rõ ràng, tối thiểu và sinh theo một quy ước nhất quán:

- Mỗi test chỉ tạo entity cần thiết; dùng builder hoặc fixture factory cho trạng thái nghiệp vụ.
- Sinh ID độc nhất, nhất là khi chạy nhiều class song song.
- Dùng dữ liệu không nhạy cảm; không sao chép production database chứa PII vào CI.
- Schema migration được chạy trước fixture.
- Sử dụng Clock có thể kiểm soát khi logic dựa trên thời gian (TTL, expiration, retry).
- Không phụ thuộc timezone của máy chạy; dùng UTC hoặc format xác định.
- Với event, có event_id, event_type, version, occurred_at, correlation_id nếu là một phần hợp đồng.
- Tách test payload hợp lệ và payload cố tình bị lỗi; giải thích vì sao expected outcome khác nhau.
- Nếu test consumer retry, chọn số lần retry/deadline đủ nhỏ để test chạy nhanh nhưng vẫn phản ánh policy.

Tránh seed quá nhiều dòng, nhất là nếu không kiểm tra logic query lớn. Dữ liệu lớn cho performance test nên nằm trong suite riêng, có mục đích và giới hạn rõ.

### Phân biệt fixture và production-like data

Fixture nhỏ xác nhận đúng hành vi. Dữ liệu có kích thước và phân phối giống production giúp phát hiện vấn đề index, query plan hoặc tải broker; đó là bài **performance/capacity test** khác với integration test thông thường. Đừng yêu cầu mỗi integration test seed hàng triệu bản ghi mới coi là “thật”.

## 18. Gợi ý cấu trúc test suite trong repository Java

Một cấu trúc có thể điều chỉnh theo dự án:

~~~text
src/test/java/com/example/orders/
  unit/
    OrderPolicyTest.java
  integration/
    repository/
      OrderRepositoryIT.java
      InventoryLockingIT.java
    messaging/
      OrderCreatedConsumerIT.java
      OutboxPublisherIT.java
    workflow/
      CreateOrderWorkflowIT.java
  contract/
    OrderCreatedContractTest.java

src/test/resources/
  application-test.yml
  fixtures/
    order-created-v1.json
    order-created-v2.json
~~~

Không bắt buộc tên class kết thúc bằng IT; quan trọng là **cấu hình Gradle/JUnit thật sự phát hiện và chạy test**. Một số build chia task test và integrationTest để tối ưu feedback. Khi có task riêng, hãy chắc CI chạy task đó trong pipeline thích hợp; test bị bỏ qua âm thầm còn nguy hiểm hơn test chậm.

Dùng profile test để tắt job nền không liên quan, chặn outbound calls tới hệ thống ngoài và chỉ chạy những consumer cần thiết. Tuy nhiên không tắt chính listener, transaction manager, serializer hoặc policy retry đang là mục tiêu kiểm thử.

## 19. Chiến lược chạy trên máy phát triển và CI

Quy trình có thể là:

~~~text
Pull Request
  |-- compile + unit tests
  |-- integration tests có DB thật
  |-- integration tests có broker thật
  |-- selected DB + broker workflow tests
  |-- contract tests
  |
Merge / release candidate
  |-- extended integration / failure scenarios
  |-- staged end-to-end smoke tests
  |-- performance / resilience suites theo lịch
~~~

Lựa chọn bước nào chạy mỗi PR phụ thuộc thời gian, tần suất thay đổi và mức rủi ro. Một test rủi ro cao như ràng buộc không trừ tồn kho âm hoặc idempotency thanh toán đáng được chạy thường xuyên dù có chi phí lớn hơn unit test.

### 19.1. CI runner

Cần kiểm tra:

1. Runner có thể chạy container với quyền và cấu hình phù hợp.
2. Image tải từ registry được phép, được pin và quét theo policy.
3. CPU, RAM, disk và cổng đủ cho database, broker, application context và collector khi cần.
4. Test không phụ thuộc cổng cố định hoặc container tồn tại từ job trước.
5. Nguồn dữ liệu, credential, queue/topic dành riêng cho test; không kết nối production.
6. Có giới hạn tổng thời gian, chẩn đoán khi timeout và lưu artifact log cần thiết.
7. Chạy song song không làm nhiều test dừng cùng một broker hoặc dùng chung key/queue.
8. Nếu dùng cache/reuse container để tăng tốc, phải có cơ chế reset để bảo đảm tính độc lập.

Trong môi trường CI bảo mật nghiêm ngặt, không phải runner nào cũng cho phép Docker-in-Docker hoặc socket Docker. Có thể dùng runner có container runtime, dịch vụ CI phù hợp hoặc môi trường ephemeral được cấp trước, miễn là test vẫn kết nối đến hạ tầng thật và có cô lập.

### 19.2. Chi phí khởi động và tối ưu

Khởi động DB và broker là phần tốn thời gian. Có thể chia sẻ container giữa nhiều test class **khi chắc chắn không rò rỉ trạng thái**, gom các test có cùng Spring context, tối ưu migration, chọn image gọn và dùng suite riêng cho failure test. Không bật reuse container xuyên nhiều lần chạy một cách tùy tiện nếu khiến test phụ thuộc dữ liệu cũ.

Không cần dựng lại toàn bộ hạ tầng cho từng assert nhỏ; cũng không dùng một hệ thống chung lâu dài khiến test trở thành kiểm thử “ai chạy trước người đó thắng”.

## 20. Phân tích failure: test fail vì ứng dụng hay vì môi trường?

Một integration test có thể thất bại do logic ứng dụng hoặc do hạ tầng test không sẵn sàng. Cần phân biệt từ chứng cứ:

| Triệu chứng | Giả thuyết có thể kiểm tra | Bằng chứng hữu ích |
| --- | --- | --- |
| Không kết nối được PostgreSQL | Container chưa ready, network, URL, credential | Container health/log, JDBC exception, URL đã cấu hình |
| Migration fail | SQL syntax, phụ thuộc migration, extension thiếu | Flyway/Liquibase logs, schema version |
| Producer thành công nhưng không có consumer effect | Sai binding/group, serializer, listener chưa start, event chưa commit | Broker topology, headers, consumer log, DB state |
| Test async timeout không ổn định | Race, shared state, scheduling, quá ngắn, retry | Timeline, queue lag, concurrent tests, latency |
| Double side effect | At-least-once delivery, idempotency thiếu hoặc race | Duplicate event IDs, unique constraint, transaction logs |
| Test chỉ fail khi chạy cả suite | Data leak, container/queue shared, order dependency | Test order, IDs, cleanup, parallel policy |
| Crash sau khi DB commit | Publish không atomic, outbox chưa có | Orders/outbox rows, publisher checkpoint |
| Chỉ fail trên CI | Tài nguyên, image, runtime hoặc timing khác | Runner metrics, container logs, startup/migration time |

Thay vì tăng Thread.sleep từ 1 giây lên 30 giây mà không hiểu lý do, hãy đo readiness, event flow, queue, transaction visibility và trạng thái consumer. Một sửa chữa đúng thường là chờ điều kiện có ý nghĩa, cô lập dữ liệu, thêm transaction boundary hoặc sửa cấu hình.

## 21. Những sai lầm thường gặp

**“Dùng H2 là đã kiểm thử PostgreSQL.”** H2 kiểm tra một số tích hợp JDBC/JPA nhưng khác SQL dialect, kiểu dữ liệu, index, lock và transaction. Với hành vi phụ thuộc PostgreSQL, cần PostgreSQL thật.

**“Mock RabbitTemplate là đã kiểm thử messaging.”** Mock chỉ xác nhận code gọi một method. Nó chưa kiểm tra exchange, routing, content type, queue binding hoặc consumer thật.

**“Test chạy xanh vì có Thread.sleep đủ dài.”** Sleep không chứng minh điều kiện sau cùng, làm test chậm và vẫn flaky khi CI thay đổi tải. Poll vào trạng thái có thể quan sát với timeout.

**“Test @Transactional rollback mọi thứ, kể cả broker.”** Database transaction không tự rollback message đã publish và thường không chia sẻ context với consumer ở thread khác.

**“Consumer nhận một lần nên có exactly-once.”** Broker có thể redeliver khi crash/ack lỗi. Cần thử duplicate và bảo vệ idempotency của side effect.

**“Producer publish trả success nghĩa là đơn đã xử lý xong.”** Publish/confirm, consumer ack và nghiệp vụ hoàn thành là ba mốc khác nhau.

**“Có outbox là không bao giờ xuất hiện message trùng.”** Publisher có thể gửi lại sau crash. Outbox giải quyết sự mất đồng bộ DB–publish theo thiết kế, không loại bỏ mọi duplicate.

**“Container được chia sẻ thì test nào cũng độc lập.”** Row, queue, topic, offset hoặc consumer group có thể tồn tại qua test; phải thiết kế isolation và cleanup.

**“Test trên container đã tương đương cluster production.”** Single-node container không tái hiện đầy đủ replica/failover, bảo mật mạng, managed-service limits hoặc khả năng chịu tải thật.

**“Chỉ cần happy path.”** Những lỗi quan trọng nhất thường ở rollback, duplicate event, poison message, broker unavailable, migration và concurrency.

## 22. Checklist thiết kế một bài integration test có giá trị

Trước khi thêm test, trả lời:

1. **Hợp đồng:** hành vi cụ thể nào cần chứng minh? Repository, event, transaction hay workflow?
2. **Ranh giới thực:** DB engine, broker, serializer, migration và listener nào phải là thật?
3. **Điều kiện bắt đầu:** container và application đã ready, schema đã migrate, binding/topic đã tạo?
4. **Fixture:** dữ liệu tối thiểu, ID độc nhất, credential test và thời gian xác định?
5. **Trigger:** gọi service/API thật hay publish message qua client thật?
6. **Quan sát kết quả:** đọc lại database đã commit, broker state hoặc side effect được kiểm soát?
7. **Async:** điều kiện cuối và deadline đủ rõ, có poll thay vì sleep?
8. **Failure:** rollback, retry, duplicate, malformed payload, unavailable có được bao phủ?
9. **Isolation:** test độc lập khi chạy cùng suite hoặc song song?
10. **Chẩn đoán:** khi fail có log/schema/queue/trace đủ để tìm nguyên nhân?
11. **CI:** test thực sự được discovery và chạy trong pipeline, không bị skip âm thầm?
12. **An toàn:** không đụng production hoặc làm lộ credential/dữ liệu nhạy cảm?

## 23. Bài tập thực hành: Order Service với PostgreSQL và RabbitMQ

Bạn có Order Service lưu bảng orders, outbox_events; một publisher đọc outbox và gửi OrderCreated; Notification Service nhận event và ghi notification_jobs. Hệ thống yêu cầu: một đơn hợp lệ luôn được lưu trước khi phát event, sự kiện không mất khi publisher crash, và cùng event không tạo hai thông báo.

Hãy viết các integration test cho những kịch bản:

**A. Lưu đơn và outbox cùng transaction**

- Tạo order với dữ liệu hợp lệ; sau khi commit, assert có một order và một outbox event tương ứng.
- Gây lỗi ràng buộc khi ghi order; assert không còn outbox event orphan.
- Xác minh schema từ migration thật trong PostgreSQL container.

**B. Publish và consume qua broker thật**

- Để outbox publisher gửi OrderCreated tới exchange thật.
- Dùng Awaitility kiểm tra notification_jobs có record tương ứng.
- Kiểm tra event_id và schema/version được consumer hiểu đúng.

**C. Duplicate delivery và sự cố**

- Publish cùng event_id hai lần; assert chỉ một business side effect.
- Mô phỏng lỗi DB tạm thời trong consumer, xác nhận retry/backoff không tạo trùng.
- Dừng publisher sau khi broker nhận nhưng trước khi mark sent, khởi động lại và kiểm tra idempotency.
- Gửi payload không hợp lệ và xác nhận xử lý theo DLQ policy.

**D. Cô lập và CI**

- Sinh event_id/order_id riêng cho từng test, không phụ thuộc thứ tự.
- Thử chạy cả suite nhiều lần và chạy song song theo phạm vi được hỗ trợ.
- Xác nhận Docker runtime, migration, broker topology và test task luôn sẵn có trong CI.

**Tiêu chí đạt:** Test chạy qua PostgreSQL và RabbitMQ thật; quan sát **trạng thái nghiệp vụ đã commit**, không chỉ method invocation; phản ánh đúng trường hợp thành công, lỗi, retry và duplicate; lỗi có thể chẩn đoán từ database/broker/log. Không cần khởi động toàn bộ các microservice không liên quan.

---

**Điểm cần nhớ:** Kiểm thử tích hợp với database và broker thực xác nhận rằng những lời hứa của ứng dụng vẫn đúng khi bước ra khỏi unit test: schema thật chấp nhận dữ liệu, transaction thật giữ invariant, broker thật định tuyến và chuyển message, consumer thật xử lý bất đồng bộ và hệ thống chịu được giao lại. Chọn đúng ranh giới, kiểm tra kết quả sau commit và thiết kế isolation là nền tảng để test có giá trị và đáng tin cậy.
