# Hiện thực Outbox và consumer xử lý lặp an toàn với Java và Spring

Trong hệ thống microservices, một thao tác nghiệp vụ thường phải vừa cập nhật database vừa thông báo cho dịch vụ khác. Ví dụ Order Service xác nhận đơn hàng và phát sự kiện OrderConfirmed để Inventory, Payment, Shipping hoặc Notification tiếp tục xử lý.

Nếu ứng dụng thực hiện hai thao tác độc lập:

    1. Ghi đơn hàng vào PostgreSQL.
    2. Publish OrderConfirmed lên Kafka/RabbitMQ.

thì giữa hai bước có thể xảy ra lỗi. Database commit thành công nhưng broker không nhận event; hoặc broker đã nhận event nhưng ứng dụng crash trước khi biết kết quả. Một transaction local của database không thể tự động bao trùm một transaction ở broker và các side effect của consumer.

**Transactional Outbox** giải quyết khoảng trống giữa việc commit dữ liệu nghiệp vụ và ghi nhận ý định phát sự kiện bằng cách lưu cả hai trong cùng một database transaction. Một relay riêng sau đó chuyển outbox record tới broker. Vì relay có thể gửi lại message khi kết quả publish chưa rõ, **consumer phải xử lý lặp an toàn (idempotent)** bằng event ID, inbox/deduplication, business version và transaction boundary phù hợp.

Bài học này trình bày cách hiện thực Outbox và consumer an toàn với Java, Spring Boot, Spring Data JPA/JDBC, PostgreSQL và Kafka/RabbitMQ. Mục tiêu là bảo đảm một business change đã commit có thể được phát lại đáng tin cậy, message trùng không tạo side effect nghiệp vụ trùng và lỗi tạm thời có thể phục hồi mà không làm mất dữ liệu.

## 1. Bài toán dual-write

Giả sử Order Service cần tạo đơn và phát event:

    Client
      |
      v
    Order Service
      |
      +----> PostgreSQL: INSERT orders
      |
      +----> Kafka: publish OrderCreated
                    |
                    +--> Inventory
                    +--> Payment
                    +--> Notification

Cách triển khai ngây thơ:

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(...);
        kafkaTemplate.send("orders", new OrderCreated(...));
        return order;
    }

Annotation @Transactional mặc định quản lý transaction của transaction manager được cấu hình cho database. Lệnh gửi Kafka không tự động trở thành một phần nguyên tử của transaction PostgreSQL đó.

Có hai tình huống nguy hiểm:

**Database commit, publish thất bại**

    DB commit order -> thành công
    Broker publish   -> lỗi hoặc timeout

Order tồn tại nhưng Inventory/Payment không nhận được event. Nếu không có cơ chế phát lại, workflow bị mắc kẹt.

**Publish thành công, database rollback**

    Broker publish   -> thành công
    DB transaction   -> rollback

Consumer nhận OrderCreated cho một order không tồn tại. Đây là sự kiện ma.

Thứ tự publish trước hay sau commit đều có cửa sổ lỗi. Đưa publish vào cùng method có @Transactional không biến hai hệ thống thành một transaction phân tán.

### 1.1. Vì sao không chỉ dùng try/catch?

Nếu publish lỗi, code có thể rollback database; nhưng nếu broker đã nhận message và response bị mất, ứng dụng không biết publish đã thành công hay chưa. Rollback database lúc này vẫn để lại message trên broker.

Nếu commit DB trước rồi catch lỗi publish, đơn hàng vẫn tồn tại nhưng event bị mất nếu không lưu ý định gửi lại ở nơi bền vững.

Vấn đề không nằm ở thiếu try/catch. Vấn đề là **không có một điểm commit chung** cho hai hệ thống độc lập.

## 2. Transactional Outbox là gì?

Outbox là một bảng trong cùng database với dữ liệu nghiệp vụ. Trong một transaction local, ứng dụng:

1. Cập nhật aggregate hoặc business record.
2. Tạo một outbox event chứa event ID, aggregate ID, type, version và payload.
3. Commit cả hai cùng lúc.

Một relay đọc các outbox record chưa publish và gửi tới broker.

    Order Service database
      +----------------------+
      | orders               |
      | outbox_events        |
      +----------------------+
               |
               | local DB transaction
               v
       Order + Outbox commit
               |
               v
         Outbox Relay
               |
               v
        Kafka / RabbitMQ
               |
          +----+----+
          v         v
      Inventory   Payment

Nếu transaction rollback, cả order và outbox event đều không tồn tại. Nếu commit thành công, outbox event được lưu bền vững và relay có thể gửi sau khi broker phục hồi.

**Outbox không bảo đảm message chỉ được publish đúng một lần.** Relay có thể publish thành công nhưng crash trước khi đánh dấu record đã gửi. Khi khởi động lại, nó có thể gửi lại cùng event. Vì vậy consumer cần idempotency.

## 3. Các thành phần và trách nhiệm

Một thiết kế Outbox thường có bốn thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| Business application service | Thực hiện use case, cập nhật aggregate và tạo event trong transaction |
| Outbox table | Lưu ý định phát event bền vững cùng transaction business |
| Relay/publisher | Đọc record chưa gửi, publish và cập nhật trạng thái |
| Consumer/inbox | Nhận message, deduplicate và cập nhật business state an toàn |

**Producer** chịu trách nhiệm tạo event phản ánh thay đổi đã commit. **Relay** chịu trách nhiệm vận chuyển theo delivery semantics được chọn. **Consumer** chịu trách nhiệm xử lý lặp, version, transaction và side effect.

Không nên nhồi toàn bộ logic vào một @Transactional method vừa ghi DB, gửi broker, retry, sleep và xử lý lỗi. Tách transaction boundary giúp hiểu rõ phần nào đã commit và phần nào có thể chạy lại.

## 4. Thiết kế bảng outbox

Một schema PostgreSQL minh họa:

    create table outbox_events (
        id uuid primary key,
        aggregate_type varchar(120) not null,
        aggregate_id varchar(200) not null,
        aggregate_version bigint,
        event_type varchar(160) not null,
        event_version integer not null,
        payload jsonb not null,
        headers jsonb,
        occurred_at timestamptz not null,
        created_at timestamptz not null default now(),
        published_at timestamptz,
        status varchar(20) not null default 'PENDING',
        attempts integer not null default 0,
        next_attempt_at timestamptz not null default now(),
        locked_by varchar(120),
        locked_until timestamptz,
        last_error_code varchar(100)
    );

    create index outbox_pending_idx
        on outbox_events (next_attempt_at, created_at)
        where published_at is null;

    create index outbox_aggregate_idx
        on outbox_events (aggregate_type, aggregate_id,
                          aggregate_version);

Đây là schema tham khảo; trạng thái, lock và index cần phù hợp với relay implementation. Một số hệ thống chỉ dùng created_at/published_at; hệ thống khác dùng lease, retry schedule, partition và dead-letter state.

### 4.1. Ý nghĩa các cột

- id: event ID duy nhất, ổn định qua mọi lần retry.
- aggregate_type: loại aggregate, ví dụ Order.
- aggregate_id: ID của order hoặc thực thể gốc.
- aggregate_version: version business của aggregate sau thay đổi.
- event_type: tên sự kiện, ví dụ OrderConfirmed.
- event_version: version của schema/contract event.
- payload: dữ liệu consumer cần theo hợp đồng.
- headers: metadata như correlation ID, trace context hoặc tenant context an toàn.
- occurred_at: thời điểm nghiệp vụ xảy ra theo clock/transaction policy.
- created_at: thời điểm outbox record được tạo.
- published_at/status: trạng thái relay.
- attempts/next_attempt_at: retry metadata.
- locked_by/locked_until: lease cho worker đang xử lý.
- last_error_code: lỗi đã chuẩn hóa để điều tra.

Không nhất thiết lưu toàn bộ entity vào payload. Chỉ đưa các trường consumer cần, tránh lộ PII, secret hoặc internal implementation details.

### 4.2. UUID và business key

Event ID phải được tạo một lần khi business transaction tạo outbox record. Relay không tạo ID mới khi retry. Nếu retry tạo ID khác, consumer không nhận ra hai message là cùng một event.

Aggregate ID cho biết event thuộc thực thể nào. Event ID và aggregate ID có mục đích khác nhau:

- Event ID: nhận diện một lần thay đổi logic.
- Aggregate ID: nhóm các event theo thực thể và hỗ trợ ordering.
- Idempotency key: nhận diện một logical command/request; có thể khác event ID.
- Correlation ID: nối các bước của workflow; không phải khóa deduplication.

## 5. Transaction boundary ở producer

Business record và outbox record phải được ghi bằng **cùng database transaction manager** và cùng transaction.

Ví dụ:

    @Service
    public class OrderApplicationService {
        private final OrderRepository orders;
        private final OutboxRepository outbox;
        private final EventPayloadFactory payloadFactory;

        public OrderApplicationService(
                OrderRepository orders,
                OutboxRepository outbox,
                EventPayloadFactory payloadFactory) {
            this.orders = orders;
            this.outbox = outbox;
            this.payloadFactory = payloadFactory;
        }

        @Transactional
        public OrderResult confirm(ConfirmOrderCommand command) {
            Order order = orders.findForUpdate(
                command.orderId(), command.tenantId()
            ).orElseThrow(OrderNotFoundException::new);

            order.confirm();
            long version = order.version();

            orders.save(order);

            OrderConfirmed event = payloadFactory.orderConfirmed(
                order, version
            );

            outbox.save(OutboxEvent.from(
                UUID.randomUUID(),
                "Order",
                order.id().toString(),
                version,
                "OrderConfirmed",
                1,
                event
            ));

            return OrderResult.from(order);
        }
    }

Các repository, command, event và factory là thành phần miền minh họa. Điểm quan trọng là method ghi Order và Outbox trong một transaction local. Nếu outbox insert lỗi, business update cũng rollback; nếu transaction commit, cả hai cùng bền vững.

### 5.1. Tạo event sau khi domain change hợp lệ

Không tạo event dựa trên ý định của caller trước khi kiểm tra aggregate. Ví dụ OrderConfirmed chỉ được tạo khi state transition Draft/Pending → Confirmed thành công theo domain rule.

Có thể dùng domain event do aggregate phát ra rồi application service chuyển thành integration event. Domain event và integration event không nhất thiết có payload hoặc vòng đời giống nhau:

- Domain event dùng trong phạm vi bounded context.
- Integration event là hợp đồng công khai cho service khác.
- Outbox lưu integration event sau khi business transaction được xác nhận.

### 5.2. Transaction rollback

Nếu validation, constraint hoặc outbox insert lỗi, transaction phải rollback. Cần cấu hình transaction manager và propagation đúng; không bắt exception rồi nuốt lỗi trước khi transaction kết thúc.

Spring mặc định rollback với unchecked RuntimeException và Error; checked exception có quy tắc khác trừ khi khai báo rollbackFor. Cần hiểu chính sách thực tế của dự án.

### 5.3. Tránh gọi @Transactional qua self-invocation

Trong Spring proxy mode, gọi một method @Transactional từ method khác trong cùng instance thường không đi qua proxy, do đó annotation có thể không được áp dụng như kỳ vọng.

Tách transaction boundary sang bean/service riêng hoặc dùng cách cấu hình phù hợp. Kiểm tra transaction bằng integration test với database thật; không chỉ nhìn annotation rồi giả định.

## 6. JPA entity cho Outbox

Một entity tối giản:

    @Entity
    @Table(name = "outbox_events")
    public class OutboxEventEntity {
        @Id
        private UUID id;

        @Column(name = "aggregate_type", nullable = false)
        private String aggregateType;

        @Column(name = "aggregate_id", nullable = false)
        private String aggregateId;

        @Column(name = "aggregate_version")
        private Long aggregateVersion;

        @Column(name = "event_type", nullable = false)
        private String eventType;

        @Column(name = "event_version", nullable = false)
        private int eventVersion;

        @Column(name = "payload", columnDefinition = "jsonb",
                nullable = false)
        private String payload;

        @Column(name = "created_at", nullable = false)
        private Instant createdAt;

        @Column(name = "published_at")
        private Instant publishedAt;

        protected OutboxEventEntity() {}

        // Constructor and accessors omitted in this illustrative model.
    }

Đoạn code mô tả cấu trúc, chưa phải class hoàn chỉnh cho mọi project. Có thể lưu payload JSON dưới dạng String/JsonNode hoặc dùng converter tùy driver và Hibernate version. Không dùng Java native serialization làm contract bền vững vì class/package thay đổi có thể phá khả năng đọc event lịch sử.

### 6.1. Dùng JdbcTemplate khi relay cần kiểm soát SQL

JPA thuận tiện cho business aggregate, nhưng polling relay có thể cần SQL cụ thể như SKIP LOCKED, lease và update trạng thái có điều kiện. JdbcTemplate hoặc repository native query thường dễ kiểm soát locking hơn.

Có thể kết hợp JPA cho business transaction và JDBC cho relay nếu cả hai dùng cùng DataSource/transaction manager khi cần atomicity. Không vô tình tạo hai DataSource hoặc transaction manager khác nhau rồi cho rằng chúng cùng transaction.

## 7. Relay kiểu polling publisher

Polling relay định kỳ tìm outbox record đang chờ và publish.

Một flow đơn giản:

    SELECT pending rows
       |
       v
    Publish to broker
       |
       v
    Mark published_at

Ưu điểm:

- Dễ hiểu, ít thành phần hạ tầng.
- Dùng database hiện có.
- Có thể retry từ record còn pending.
- Phù hợp hệ thống vừa/nhỏ hoặc yêu cầu latency không quá thấp.

Đánh đổi:

- Tạo polling load lên DB.
- Cần xử lý concurrency giữa nhiều relay.
- Cần tránh giữ transaction DB trong lúc chờ network broker.
- Cần quản lý trạng thái lock/lease khi worker crash.
- Có thể phát lại event sau publish thành công nhưng mark thất bại.

### 7.1. Không giữ DB transaction lâu trong lúc publish

Một thiết kế kém:

    BEGIN DB TRANSACTION
      SELECT outbox row FOR UPDATE
      publish to broker (wait network)
      UPDATE outbox SET published_at = now()
    COMMIT

Nếu broker chậm, DB transaction giữ lock lâu, làm giảm throughput và tăng lock contention. Khi nhiều worker cùng làm, có thể tạo deadlock hoặc giữ connection quá lâu.

Thường nên tách thành:

1. Claim một batch bằng transaction ngắn.
2. Commit lease/claim.
3. Publish bên ngoài transaction.
4. Mark success bằng transaction ngắn.
5. Nếu publish lỗi, lên lịch retry và bỏ lease.

Cần xử lý kỹ crash giữa từng bước; claim lease hết hạn giúp worker khác tiếp quản.

## 8. Claim batch an toàn với FOR UPDATE SKIP LOCKED

PostgreSQL hỗ trợ SKIP LOCKED để nhiều relay worker lấy các row khác nhau mà không chờ row đang bị worker khác khóa.

Một ví dụ claim bằng lease:

    with candidates as (
        select id
          from outbox_events
         where published_at is null
           and next_attempt_at <= now()
           and (
             locked_until is null
             or locked_until < now()
           )
         order by created_at, id
         for update skip locked
         limit :batch_size
    )
    update outbox_events o
       set locked_by = :worker_id,
           locked_until = now() + interval '30 seconds',
           attempts = attempts + 1
      from candidates c
     where o.id = c.id
    returning o.*;

Câu SQL minh họa; cần kiểm tra cú pháp, isolation, index và semantics của trạng thái trong phiên bản PostgreSQL đang dùng.

Sau claim, transaction kết thúc và worker publish từng event. Nếu worker chết, lease hết hạn để worker khác lấy lại.

### 8.1. Lease và fencing

Lease 30 giây chỉ là ví dụ. Nếu publish mất 45 giây, lease có thể hết khi worker cũ vẫn đang hoạt động; worker khác có thể claim cùng event. Điều đó tạo duplicate publish, vì vậy consumer vẫn phải idempotent.

Có thể gia hạn lease khi công việc kéo dài, dùng worker identity và claim token/epoch để ngăn worker cũ mark trạng thái sau khi quyền lease đã đổi. Tuy nhiên không thể loại bỏ mọi duplicate chỉ bằng lease.

### 8.2. Thứ tự event theo aggregate

ORDER BY created_at không bảo đảm các event của cùng aggregate được publish theo business version nếu nhiều worker claim song song.

Nếu ordering là bắt buộc:

- Dùng aggregate ID làm partition/routing key.
- Đảm bảo chỉ một worker xử lý một aggregate/lane tại một thời điểm, hoặc chỉ claim event tiếp theo khi version trước đã publish.
- Có sequence/version và consumer kiểm tra gap.
- Không để retry một event cũ bị bỏ qua trong khi event mới hơn được công bố nếu nghiệp vụ đòi thứ tự.

Ordering toàn cục rất tốn kém và thường không cần. Thường chỉ cần ordering theo aggregate hoặc workflow.

## 9. Publish rồi mark: cửa sổ duplicate không thể tránh bằng polling đơn giản

Giả sử:

    1. Relay gửi event E đến broker.
    2. Broker nhận và xác nhận publish.
    3. Relay crash trước khi cập nhật published_at.
    4. Relay mới lấy lại E.
    5. E được gửi lần hai.

Đây là hành vi bình thường của mô hình at-least-once. Nếu relay mark published trước khi gửi:

    1. Mark E published.
    2. Relay crash trước khi broker nhận E.
    3. E không bao giờ được gửi lại.

Do đó thứ tự an toàn thường là **publish được broker xác nhận rồi mới mark published**, chấp nhận duplicate và thiết kế consumer idempotent.

Nếu broker confirmation bị timeout, kết quả có thể không rõ: broker có thể đã nhận message. Hãy retry cùng event ID, không tạo event ID mới.

## 10. Broker acknowledgment và delivery semantics

Cần phân biệt:

- **Producer send completion:** client library đã gửi request.
- **Broker acknowledgment/confirmation:** broker xác nhận nhận theo cấu hình durability/replication.
- **Consumer delivery:** message được giao cho consumer.
- **Consumer acknowledgment/offset commit:** consumer xác nhận đã xử lý theo semantics broker.

Với RabbitMQ, publisher confirms và durable queues/messages cần được cấu hình theo yêu cầu. Consumer ack sau khi business transaction commit. Với Kafka, producer acks/idempotence và consumer offset commit phải được cấu hình phù hợp.

Không coi callback send hoàn tất là bằng chứng dữ liệu đã bền vững nếu cấu hình broker không bảo đảm điều đó.

### 10.1. Kafka

Producer có thể dùng idempotent producer để giảm duplicate do retry ở tầng producer theo phạm vi Kafka hỗ trợ. Nhưng nó không thay thế event ID/inbox ở consumer và không giải quyết atomicity giữa PostgreSQL và Kafka.

Một transactional Kafka producer có thể phối hợp write topic và offset trong Kafka transaction cho một số pipeline Kafka-to-Kafka. Nó không tự gộp transaction PostgreSQL của Order Service với database của Inventory Service.

### 10.2. RabbitMQ

Publisher confirms giúp producer biết broker đã xác nhận publish. Durable queue, persistent message và replication/quorum queue tùy cấu hình quyết định khả năng sống sót của message. Consumer ack chỉ nên thực hiện sau khi local business transaction commit.

Nếu consumer ack trước commit rồi DB rollback, message có thể mất khỏi queue nhưng business update không tồn tại.

## 11. CDC relay thay cho polling

Một lựa chọn là dùng Change Data Capture đọc transaction log của database, ví dụ Debezium với PostgreSQL WAL, rồi phát outbox row sang Kafka.

    Business DB transaction
      +--> orders
      +--> outbox_events
                |
                v
           PostgreSQL WAL
                |
                v
             Debezium
                |
                v
              Kafka
                |
                v
            Consumers

Ưu điểm:

- Không cần polling query liên tục.
- Có thể giảm write/update published_at trên outbox.
- CDC theo transaction log và hỗ trợ throughput cao.
- Offset và log stream có thể phục hồi theo cơ chế connector.

Đánh đổi:

- Thêm hạ tầng connector, schema registry/serialization và vận hành.
- Cần giám sát replication slot/WAL retention; connector dừng lâu có thể làm disk tăng.
- Phải quản lý snapshot, schema evolution và offset.
- Connector replay có thể phát lại record.
- Consumer vẫn cần idempotency.

Nếu dùng CDC, không cần thêm cột published_at chỉ để đánh dấu relay đã gửi nếu connector quản lý checkpoint. Nhưng cần policy cleanup outbox sau khi connector đã tiến qua mốc an toàn, không xóa row còn cần replay.

## 12. Spring Boot: cấu hình producer và transaction manager

Một cấu hình khái niệm:

    @Configuration
    public class OutboxConfiguration {
        @Bean
        Clock clock() {
            return Clock.systemUTC();
        }
    }

Spring Boot có thể tự cấu hình DataSource, JPA và KafkaTemplate từ properties. Điều quan trọng là business service và outbox repository sử dụng cùng database transaction manager.

Nếu có nhiều database, phải chỉ rõ transaction manager nào quản lý cả hai thao tác. Hai @Transactional manager riêng không tự tạo một transaction nguyên tử xuyên database.

Không cố dùng @Transactional("dbTxManager") rồi giả định Kafka send cũng nằm trong transaction đó. Nếu sử dụng Kafka transaction manager, cần hiểu rõ cách phối hợp và giới hạn giữa hai hệ thống; Outbox thường được chọn để tránh dựa vào distributed commit giữa DB và broker.

## 13. Spring Boot: tạo business record và outbox cùng transaction

Ví dụ với Spring Data:

    @Service
    public class OrderService {
        private final OrderRepository orderRepository;
        private final OutboxRepository outboxRepository;
        private final ObjectMapper objectMapper;

        public OrderService(
                OrderRepository orderRepository,
                OutboxRepository outboxRepository,
                ObjectMapper objectMapper) {
            this.orderRepository = orderRepository;
            this.outboxRepository = outboxRepository;
            this.objectMapper = objectMapper;
        }

        @Transactional
        public Order confirm(ConfirmOrderCommand command) {
            Order order = orderRepository
                .findByIdAndTenantId(
                    command.orderId(), command.tenantId()
                )
                .orElseThrow(OrderNotFoundException::new);

            order.confirm();
            orderRepository.save(order);

            OrderConfirmed payload = new OrderConfirmed(
                order.getId(),
                order.getTenantId(),
                order.getVersion(),
                order.getTotal()
            );

            OutboxEvent event = OutboxEvent.create(
                UUID.randomUUID(),
                "Order",
                order.getId().toString(),
                order.getVersion(),
                "OrderConfirmed",
                1,
                serialize(payload, objectMapper)
            );

            outboxRepository.save(event);
            return order;
        }
    }

Đây là mẫu minh họa; cần thêm constructor, entity mapping, validation, error handling và imports của dự án. Order và OutboxEvent phải được persist trong cùng transaction. Nếu serialize payload lỗi trước commit, transaction phải rollback.

### 13.1. Event payload bất biến

Sau khi lưu outbox, payload nên là snapshot của event tại thời điểm transaction commit. Đừng để relay sau này query Order hiện tại rồi tự dựng event cũ: order có thể đã đổi trạng thái, làm event lịch sử không còn đúng.

Payload cần đủ dữ liệu consumer theo contract, nhưng không cần chứa mọi field trong entity. Có thể chỉ chứa aggregate ID/version rồi consumer gọi API owner nếu use case cho phép, nhưng cách đó tạo dependency đồng bộ và có thể không tái tạo đúng lịch sử.

## 14. Consumer xử lý lặp an toàn: Inbox pattern

Consumer có thể nhận một event nhiều lần do:

- Relay publish lại.
- Broker redeliver sau consumer restart.
- Consumer xử lý xong nhưng crash trước ack/offset commit.
- Offset được reset hoặc message replay.
- Operator chủ động replay DLQ.
- Producer retry vì không nhận được confirmation.

**Inbox pattern** lưu event ID đã xử lý trong cùng database transaction với business update của consumer.

Schema:

    create table processed_messages (
        consumer_name varchar(150) not null,
        event_id uuid not null,
        processed_at timestamptz not null default now(),
        primary key (consumer_name, event_id)
    );

Consumer thực hiện:

1. Bắt đầu transaction database.
2. Thử insert (consumer_name, event_id).
3. Nếu unique conflict, event đã xử lý; không chạy business side effect lần nữa.
4. Nếu insert thành công, cập nhật business state.
5. Commit cả processed record và business state cùng nhau.
6. Sau khi transaction commit thành công, ack message hoặc commit Kafka offset theo cách xử lý đã chọn.

Nếu transaction rollback, cả inbox record và business update rollback. Khi message được giao lại, consumer có thể xử lý từ đầu.

### 14.1. Vì sao inbox phải cùng transaction?

Thiết kế sai:

    INSERT processed_messages;  -- transaction A commit
    UPDATE inventory;           -- transaction B lỗi

Khi message được giao lại, inbox nói đã xử lý dù inventory chưa cập nhật. Event bị bỏ qua vĩnh viễn.

Thiết kế đúng:

    BEGIN
      INSERT processed_messages;
      UPDATE inventory;
    COMMIT

Cả hai cùng thành công hoặc cùng rollback trong cùng local DB transaction.

### 14.2. Insert-on-conflict trong PostgreSQL

Một cách lấy quyền xử lý:

    insert into processed_messages (
        consumer_name, event_id
    )
    values (:consumer_name, :event_id)
    on conflict do nothing;

Nếu affected row count bằng 1, event mới được nhận. Nếu bằng 0, event đã được ghi nhận trước đó. Phải thực hiện trong cùng transaction với business update.

Unique constraint là cơ chế phối hợp giữa nhiều consumer instance; kiểm tra SELECT trước rồi INSERT riêng lẻ có race condition.

## 15. Spring Boot: consumer idempotent với inbox

Ví dụ dùng JdbcTemplate và transaction:

    @Service
    public class InventoryEventHandler {
        private static final String CONSUMER = "inventory-order-events";

        private final JdbcTemplate jdbc;
        private final InventoryRepository inventory;

        public InventoryEventHandler(
                JdbcTemplate jdbc,
                InventoryRepository inventory) {
            this.jdbc = jdbc;
            this.inventory = inventory;
        }

        @Transactional
        public void handle(OrderConfirmed event) {
            int inserted = jdbc.update(
                """
                insert into processed_messages(
                    consumer_name, event_id
                )
                values (?, ?)
                on conflict do nothing
                """,
                CONSUMER,
                event.eventId()
            );

            if (inserted == 0) {
                return; // duplicate: business update đã được commit
            }

            inventory.reserveForOrder(
                event.tenantId(),
                event.orderId(),
                event.items()
            );
        }
    }

Nếu reserveForOrder ném unchecked exception và cùng transaction manager, inbox insert rollback cùng business update. Khi broker giao lại, handler có thể thử lại.

Nếu business method bắt exception rồi nuốt, transaction có thể commit inbox sai. Hãy để lỗi propagate hoặc đánh dấu rollback rõ theo policy. Với checked exception, cấu hình rollbackFor khi cần.

**Không tự ack message trước khi method transactional commit.** Nếu listener gọi một bean transactional khác, cần hiểu thời điểm proxy commit và acknowledgment của listener container. Cấu hình ack mode phải phù hợp; test crash/rollback để xác minh.

## 16. Consumer acknowledgment và Kafka offset

Với Kafka, offset commit xác nhận consumer group đã tiến tới vị trí nào. Nếu commit offset trước database transaction:

    Commit offset -> success
    DB update     -> fail

Kafka sẽ không giao lại event theo offset đã commit, dẫn đến mất business update.

Nếu DB commit trước offset:

    DB update     -> success
    Consumer crash before offset commit

Kafka giao lại event; inbox dedupe ngăn business update lần hai. Đây là thứ tự thường phù hợp với local DB consumer.

Tuy nhiên cần chú ý batch listener, acknowledgment mode, concurrent partitions và việc container tự commit. Cấu hình phải bảo đảm offset không tiến qua record chưa được xử lý thành công theo semantics mong muốn.

Kafka transaction có thể atomically commit output Kafka records và consumed offsets trong một Kafka transaction; nếu business state nằm trong PostgreSQL, inbox/local transaction vẫn cần cơ chế phối hợp.

## 17. RabbitMQ acknowledgment

Với RabbitMQ:

- Manual acknowledgment giúp consumer chỉ ack sau khi business transaction commit.
- Nếu consumer crash trước ack, broker có thể redeliver.
- Nếu ack trước DB commit và transaction rollback, message có thể bị mất.
- Nếu DB commit xong nhưng ack thất bại, message redeliver; inbox xử lý duplicate.

Cần cấu hình prefetch để giới hạn số message chưa ack và tránh một consumer giữ quá nhiều công việc. Retry có thể dùng delayed retry/dead-letter topology phù hợp; không requeue liên tục message lỗi vì tạo hot loop.

## 18. Idempotency theo event ID và theo business key

Inbox event ID giải quyết duplicate của **cùng một message**. Nhưng hai event khác nhau có thể biểu diễn cùng một logical action nếu producer tạo event mới cho một request retry.

Ví dụ client gửi CreatePayment hai lần, producer vô tình tạo hai event ID khác nhau. Inbox sẽ coi đó là hai event khác nhau. Vì vậy cần thêm idempotency ở command boundary:

- Client gửi Idempotency-Key ổn định cho một logical command.
- Producer lưu key, caller scope và request hash.
- Unique constraint ngăn tạo hai order/payment command cùng key.
- Nếu cùng key/payload, trả kết quả cũ hoặc trạng thái đang xử lý.
- Nếu cùng key nhưng payload khác, trả conflict theo contract.

Consumer cũng có thể cần unique business constraint như một reservation chỉ tồn tại một lần cho (tenant_id, order_id). Event ID dedupe và business uniqueness bảo vệ hai lớp khác nhau.

## 19. External side effects không nằm trong inbox transaction

Giả sử consumer xử lý OrderConfirmed:

    BEGIN DB
      INSERT processed_messages
      UPDATE inventory
      CALL external shipping API
    COMMIT

Cuộc gọi HTTP không được database transaction bao phủ. Nếu shipping API thành công nhưng DB commit thất bại, event redelivery có thể tạo shipment thứ hai.

Không nên giữ transaction DB mở trong lúc gọi external API để giả vờ atomic. Thay vào đó:

1. Trong local transaction, ghi inbox + cập nhật state + tạo một outbox command.
2. Commit.
3. Một relay gửi command ra external API.
4. Dùng idempotency key ổn định với provider nếu hỗ trợ.
5. Lưu external operation reference/trạng thái.
6. Reconcile nếu response timeout hoặc outcome không rõ.

Ví dụ:

    OrderConfirmed
       |
       v
    Shipping Consumer transaction
       +--> inbox record
       +--> shipment_request status=PENDING
       +--> outbox CreateShipment
       |
       v
    Commit
       |
       v
    External API relay
       |
       v
    Shipping provider

Khi provider không hỗ trợ idempotency, cần query theo external reference, thiết kế dedup ở phía mình hoặc quy trình đối soát. Không thể đảm bảo exactly-once external side effect chỉ bằng local inbox.

## 20. Ordering và business version

Inbox chỉ chặn event ID trùng; nó không tự ngăn event cũ ghi đè event mới.

Ví dụ:

    Order v10: CONFIRMED
    Order v11: CANCELLED

Consumer nhận v11 trước, sau đó nhận v10. Nếu cập nhật state vô điều kiện, order bị hồi sinh thành CONFIRMED.

Cần:

- aggregate ID và sequence/version.
- partition key theo aggregate nếu cần ordering ở broker.
- consumer version guard.
- gap detection nếu phải xử lý mọi transition.
- tombstone hoặc trạng thái cuối để ngăn event cũ làm sống lại dữ liệu.

Một upsert có điều kiện:

    update order_projection
       set status = :status,
           version = :incoming_version
     where order_id = :order_id
       and version < :incoming_version;

Nếu update count bằng 0, có thể là event cũ hoặc aggregate chưa tồn tại; cần phân biệt hai trường hợp. Nếu version nhảy từ 10 lên 12 và event 11 chứa transition bắt buộc, consumer không thể tùy tiện bỏ qua 11.

### 20.1. Kafka partition key

Đặt message key là aggregate ID thường giúp event của cùng aggregate đi cùng partition. Tuy nhiên:

- Chỉ giữ thứ tự trong một partition.
- Tăng số partition có thể ảnh hưởng phân bố key.
- Nhiều topic không có ordering chung.
- Consumer concurrency trong một partition cần xử lý theo semantics container.
- Retry topic có thể làm event cũ quay lại sau event mới.

Version guard vẫn cần thiết ngay cả khi dùng partition key.

## 21. Retry, backoff và dead-letter queue cho consumer

Phân loại lỗi:

**Transient:** network tạm thời, database failover, rate limit có thể hồi phục. Có thể retry có giới hạn và backoff.

**Permanent/business:** payload sai schema, vi phạm invariant, tenant không tồn tại, event không được hỗ trợ. Không retry vô hạn.

**Unknown outcome:** external API timeout sau khi có thể đã thực hiện side effect. Cần idempotency/status lookup/reconciliation.

Retry policy nên có:

- Số lần tối đa hoặc retry budget.
- Exponential backoff và jitter.
- Phân loại exception/status.
- Deadline/TTL của công việc.
- DLQ hoặc quarantine có alert.
- Cách replay an toàn sau khi sửa lỗi.
- Metric về attempts và oldest message age.

Không dùng requeue ngay lập tức liên tục cho message lỗi; nó có thể chiếm consumer và broker CPU, làm các message tốt bị đói.

### 21.1. DLQ không phải nơi kết thúc trách nhiệm

DLQ cần owner, dashboard, retention, reason code, quyền truy cập và replay procedure. Khi replay:

- Giữ nguyên event ID nếu đó là cùng logical event.
- Kiểm tra consumer đã xử lý event trước đó chưa.
- Không thay payload tùy tiện rồi giữ nguyên event ID mà không có audit.
- Nếu tạo một business correction event mới, dùng event ID mới và liên kết causation/correlation.
- Đánh giá thứ tự với những event tiếp theo của cùng aggregate.

## 22. Cleanup và retention của outbox/inbox

Outbox có thể tăng không giới hạn nếu relay không cleanup. Inbox cũng tăng theo số message đã xử lý.

### 22.1. Outbox retention

Các lựa chọn:

- Xóa record đã publish sau retention period.
- Archive vào object storage hoặc bảng lịch sử.
- Partition theo thời gian và drop partition khi hết retention.
- Giữ một tập event quan trọng lâu hơn theo yêu cầu audit.

Chỉ cleanup sau khi:

- Broker xác nhận publish theo cấu hình.
- Connector/consumer replay window không còn cần record.
- Có backup/recovery policy phù hợp.
- Không cần record để reconciliation hoặc audit.

Không xóa pending/failed record chỉ vì đã quá tuổi. Cần cảnh báo và xử lý.

### 22.2. Inbox retention

Nếu xóa processed event ID quá sớm, message cũ được replay có thể chạy side effect lần nữa. Retention cần ít nhất phù hợp với broker retention, DLQ replay window, backup restore window và policy vận hành.

Với các thao tác tài chính, có thể cần business uniqueness/ledger constraint lâu hơn inbox retention. Không dựa vào một bảng dedupe ngắn hạn để bảo vệ bất biến lâu dài.

### 22.3. Partitioning và index

Với hàng trăm triệu outbox rows:

- Partition theo created_at/thời gian.
- Index partial cho pending records.
- Tránh index quá nhiều làm chậm producer transaction.
- Cleanup theo partition thay vì DELETE khối lớn.
- Theo dõi vacuum/bloat và disk.
- Dùng payload size limit và không lưu dữ liệu không cần thiết.

Schema và retention phải dựa trên throughput, broker replay, compliance và khả năng backup/restore.

## 23. Spring Boot listener: xử lý message và ack đúng thời điểm

Một listener có thể gọi bean handler transactional:

    @Component
    public class OrderEventListener {
        private final InventoryEventHandler handler;

        public OrderEventListener(InventoryEventHandler handler) {
            this.handler = handler;
        }

        @KafkaListener(
            topics = "orders.events",
            groupId = "inventory-service"
        )
        public void onMessage(OrderConfirmed event) {
            handler.handle(event);
        }
    }

Handler là bean riêng có @Transactional. Điều này giúp listener gọi qua Spring proxy và transaction hoàn tất trước khi listener method return, tùy cấu hình container/ack mode.

Cần cấu hình Kafka listener container để commit offset sau khi listener xử lý thành công. Nếu listener tự acknowledge, chỉ acknowledge sau handler commit. Kiểm tra batch mode, async return type và error handler vì chúng thay đổi lifecycle.

Đối với RabbitMQ, listener container có manual ack semantics tương tự: handler commit xong mới basicAck. Khi handler lỗi, reject/nack theo retry/DLQ policy.

Không copy cấu hình mặc định giữa Kafka và RabbitMQ; delivery/ack/offset semantics khác nhau.

## 24. Transaction propagation và nhiều datasource

Outbox chỉ atomic khi business row và outbox row dùng cùng transaction boundary. Những tình huống cần đặc biệt chú ý:

- Business repository dùng primary DataSource, outbox repository dùng một DataSource khác.
- @Transactional chỉ gắn một transaction manager trong khi có nhiều DB.
- Method gọi nội bộ không qua proxy.
- Async executor chạy ngoài transaction.
- Transaction bị commit trước khi outbox save do propagation REQUIRES_NEW.
- Event publish trong @TransactionalEventListener nhưng cấu hình AFTER_COMMIT bị hiểu nhầm là durable outbox.

Nếu business data nằm ở database A còn outbox nằm ở database B, hai ghi vẫn là dual-write. Phải đặt outbox ở cùng DB với nguồn sự thật hoặc dùng một cơ chế phối hợp khác đã được thiết kế/kiểm chứng.

## 25. @TransactionalEventListener(AFTER_COMMIT) có thay thế Outbox không?

Spring hỗ trợ:

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void publish(OrderCreated event) {
        kafkaTemplate.send(...);
    }

Cách này bảo đảm listener chạy sau khi transaction commit, nhưng **không bền vững qua crash** giữa commit DB và listener thực hiện publish:

    DB commit thành công
    Process crash
    AFTER_COMMIT listener chưa publish
    Event bị mất

Vì vậy AFTER_COMMIT hữu ích cho side effect nội bộ không quan trọng hoặc khi có cơ chế bền vững khác, nhưng không thay thế transactional outbox khi yêu cầu không bỏ lỡ integration event.

Có thể kết hợp Spring application event để tách code trong process, nhưng outbox record vẫn là durable source cho relay.

## 26. Outbox relay concurrency và starvation

Nhiều worker có thể claim batch song song. Cần giải quyết:

- Row locking/lease.
- Worker chết hoặc treo.
- Lease hết hạn khi publish còn chạy.
- Một poison event liên tục chiếm đầu queue.
- Ordering theo aggregate.
- Retry schedule không làm pending record bị đói.
- Batch size và broker throughput.
- Worker scale up/down.
- Shutdown graceful để không bỏ claim sai.

Nếu ORDER BY created_at và một event cũ lỗi mãi, có thể chặn những event khác nếu retry không đưa nó sang schedule riêng. Dùng next_attempt_at, attempts và quarantine sau ngưỡng phù hợp.

Không đánh dấu event thành PUBLISHED chỉ để bỏ qua lỗi. Nếu business event không thể publish, cần trạng thái failed/quarantined có người xử lý và alert.

## 27. Phân biệt event nghiệp vụ và integration event

Một domain event có thể chứa chi tiết nội bộ để các domain handler trong cùng bounded context dùng. Integration event là hợp đồng công khai cho service khác.

Ví dụ:

    Domain event:
      OrderPricingRecalculated

    Integration event:
      OrderConfirmed

Không publish mọi internal event ra broker. Integration event nên:

- Có schema ổn định.
- Mang ý nghĩa đã xảy ra.
- Chứa dữ liệu tối thiểu cần thiết.
- Có event ID, aggregate ID, version, occurredAt.
- Có tenant/correlation context nếu hợp lệ.
- Không lộ entity internals.
- Có versioning/compatibility policy.

Consumer không nên suy diễn trạng thái nghiệp vụ từ tên event nếu semantics chưa được tài liệu hóa.

## 28. Observability cho Outbox và consumer

Cần theo dõi cả producer, relay và consumer.

| Metric | Ý nghĩa |
| --- | --- |
| outbox_pending_count | Số record đang chờ |
| outbox_oldest_pending_age_seconds | Tuổi record chờ lâu nhất |
| outbox_publish_total | Số publish thành công |
| outbox_publish_failures_total | Số lần publish lỗi |
| outbox_retry_total | Số lần retry |
| outbox_lease_expired_total | Lease hết hạn |
| outbox_quarantined_total | Record không thể xử lý tự động |
| consumer_received_total | Số message nhận |
| consumer_processed_total | Số message xử lý mới |
| consumer_duplicate_total | Số message dedupe |
| consumer_processing_failures_total | Số xử lý lỗi |
| consumer_processing_duration_seconds | Thời gian xử lý |
| consumer_lag | Độ trễ so với broker |
| inbox_size | Số event ID đã ghi nhận |
| business_reconciliation_mismatch | Sai lệch cần đối soát |

Tên metric là ví dụ. Dùng labels có cardinality giới hạn như service, topic, event_type, status và consumer group; không gắn order_id/event_id vào metric labels.

### 28.1. Alert cần có

- Outbox oldest pending age vượt SLO.
- Pending count tăng liên tục.
- Relay publish error hoặc lease expiry tăng.
- DLQ/quarantine có message mới.
- Consumer lag vượt deadline nghiệp vụ.
- Duplicate rate tăng bất thường.
- Inbox DB hoặc outbox DB tăng nhanh/disk thấp.
- Consumer xử lý thành công nhưng business reconciliation phát hiện thiếu state.
- Relay không publish event dù DB có pending records.

Một hệ thống có thể có broker khỏe nhưng relay bị dừng; cần dashboard end-to-end từ business commit tới consumer outcome.

## 29. Bảo mật và dữ liệu trong event

Outbox và broker có thể lưu dữ liệu lâu hơn request gốc. Cần:

- Chỉ đưa dữ liệu consumer thực sự cần.
- Không gửi password, access token, secret hoặc thông tin xác thực.
- Phân loại PII và áp dụng mã hóa/access policy.
- Bảo vệ bảng outbox/inbox và DLQ bằng least privilege.
- Giới hạn quyền đọc/replay event.
- Không ghi toàn bộ payload vào log khi debug.
- Có retention và deletion policy.
- Xác thực tenant context ở consumer; không tin tenant ID từ payload nếu producer không đáng tin.
- Kiểm tra schema và kích thước message để tránh payload độc hại/quá lớn.

Nếu payload event chứa snapshot PII, cần xác định khi người dùng yêu cầu xóa thì event lịch sử, DLQ, archive và backup được xử lý theo policy nào. Không tự ý sửa payload lịch sử mà không có audit.

## 30. Failure matrix: chuyện gì xảy ra ở mỗi điểm?

| Điểm lỗi | Trạng thái có thể xảy ra | Cách phục hồi |
| --- | --- | --- |
| Trước DB commit | Business và outbox rollback | Client retry command theo idempotency |
| Outbox insert lỗi | Business transaction rollback | Sửa DB/validation, retry |
| Sau DB commit, trước relay | Outbox còn pending | Relay tiếp tục khi hoạt động |
| Broker từ chối publish | Outbox chưa published | Backoff và retry |
| Broker nhận, response bị mất | Kết quả publish không rõ | Retry cùng event ID; consumer dedupe |
| Publish thành công, relay crash trước mark | Event được gửi lại | Inbox/idempotent consumer |
| Consumer crash trước DB commit | Inbox/business rollback | Broker redeliver |
| Consumer DB commit, crash trước ack | Message redeliver | Inbox nhận duplicate và bỏ qua |
| External API thành công, DB chưa ghi kết quả | Side effect ngoài đã xảy ra | Idempotency provider/reconciliation |
| Event sai schema | Consumer không xử lý | Quarantine/DLQ, fix consumer rồi replay |
| Outbox disk đầy | Producer transaction có thể fail | Alert/capacity/cleanup an toàn |

Đây là cách phân tích hữu ích trước khi triển khai: liệt kê từng điểm crash, state bền vững và bước retry tiếp theo.

## 31. Kiểm thử với PostgreSQL và broker thật

Unit test mock repository không thể chứng minh transaction, locking, unique constraint hoặc ack semantics.

Các integration tests nên bao gồm:

**Producer atomicity**
- Business insert/update và outbox commit cùng nhau.
- Outbox insert failure làm business transaction rollback.
- Domain validation failure không tạo event.
- Transaction rollback không phát event.
- Payload lưu là snapshot đúng tại thời điểm commit.

**Relay**
- Pending row được publish và mark.
- Broker unavailable thì record vẫn pending/retry.
- Publish thành công nhưng relay crash trước mark tạo duplicate có cùng event ID.
- Hai relay worker claim không xử lý cùng row trong điều kiện bình thường.
- Lease hết hạn được worker khác tiếp quản.
- Ordering theo aggregate đáp ứng policy.

**Consumer**
- Cùng event ID nhận nhiều lần chỉ tạo một business update.
- Event duplicate đồng thời ở hai consumer instance vẫn bị unique constraint chặn.
- DB transaction rollback thì inbox record không còn.
- Crash sau commit trước ack dẫn tới duplicate được dedupe.
- Event cũ không ghi đè version mới.
- Delete/tombstone không bị event cũ hồi sinh.

**External side effect**
- Timeout sau khi provider có thể đã thực hiện lệnh.
- Retry cùng idempotency key.
- Reconciliation cho UNKNOWN.
- Không tạo double charge/double shipment.

**Operations**
- DLQ, retry schedule và replay.
- Retention/cleanup không xóa pending record.
- Backlog tăng và alert.
- Rolling deploy khi producer/consumer khác schema version.

Có thể dùng Testcontainers cho PostgreSQL và Kafka/RabbitMQ phù hợp. Awaitility hoặc polling có timeout để đợi trạng thái async; không dùng sleep cố định làm bằng chứng xử lý xong.

## 32. Ví dụ integration test cho consumer duplicate

Pseudo-test với JUnit:

    @Test
    void duplicateEventChangesInventoryOnlyOnce() {
        OrderConfirmed event = sampleEvent(
            UUID.fromString("00000000-0000-0000-0000-000000000123")
        );

        handler.handle(event);
        handler.handle(event);

        assertThat(inventory.reservedQuantity(event.orderId()))
            .isEqualTo(2);

        assertThat(inbox.count(
            "inventory-order-events", event.eventId()
        )).isEqualTo(1);
    }

Đây là cấu trúc test minh họa. Cần tạo database/container thật, dữ liệu ban đầu và assertion phù hợp. Quan trọng là test **business state cuối cùng**, không chỉ verify handler được gọi một lần. Cũng nên có test chạy hai lần song song để chứng minh unique constraint xử lý race.

## 33. Outbox với nhiều event trong một transaction

Một business command có thể tạo nhiều event. Cần quyết định:

- Tất cả event được ghi trong cùng transaction không?
- Thứ tự event trong aggregate được biểu diễn bằng sequence nào?
- Nếu một event không publish được, event sau có được phép đi trước không?
- Consumer nào cần nhận từng event?
- Event nào là public contract, event nào nội bộ?

Ví dụ một order có thể phát OrderConfirmed và InvoiceRequested. Nếu cả hai cùng phản ánh một commit, lưu cả hai trong cùng transaction. Nếu thứ tự có ý nghĩa, gắn aggregate_version/event_sequence và relay/consumer tuân thủ.

Không dùng cùng một aggregate_version cho nhiều event rồi giả định có thể sắp thứ tự nếu consumer cần thứ tự nội bộ; có thể cần event sequence riêng hoặc thứ tự ổn định bổ sung.

## 34. Batch relay và throughput

Batch size lớn giảm query overhead nhưng tăng thời gian giữ lease và khả năng publish nhiều event trước khi crash. Batch nhỏ giảm blast radius nhưng tốn round trips.

Cần đo:

- Outbox insert rate.
- Relay fetch latency.
- Broker publish confirmation latency.
- DB update latency.
- Pending age và queue depth.
- Batch retry/failure rate.
- DB pool utilization.
- Broker throughput/partition distribution.

Không chạy hàng chục relay worker chỉ để giảm backlog nếu broker hoặc consumer là bottleneck. Scale relay cần đánh giá ordering, lock contention và downstream capacity.

## 35. Outbox cleanup và schema evolution

Một bảng outbox production cần chiến lược vòng đời:

- Retain published records trong khoảng phục vụ audit/replay cần thiết.
- Archive hoặc partition theo thời gian nếu dữ liệu lớn.
- Cleanup theo batch để tránh transaction delete quá lớn.
- Giữ pending/failed records cho đến khi xử lý hoặc quyết định vận hành.
- Không xóa record chỉ vì quá tuổi.
- Giữ schema event lịch sử đủ để replay hoặc có upcaster/converter.
- Có thể nâng schema payload nhưng consumer vẫn đọc được message lịch sử.

Khi thay schema outbox, không deploy consumer/relay giả định field mới đã tồn tại trước khi database migration được apply. Dùng expand-contract cho bảng và serializer.

## 36. Khi nào nên chọn CDC relay thay polling?

Polling phù hợp khi throughput vừa, vận hành đơn giản và latency vài giây chấp nhận được. CDC phù hợp khi event rate lớn, muốn giảm query polling hoặc tổ chức đã có nền tảng log-based streaming.

| Tiêu chí | Polling relay | CDC relay |
| --- | --- | --- |
| Thành phần vận hành | Ít hơn | Connector/CDC stack |
| Latency | Theo polling/batch | Có thể thấp hơn |
| DB polling load | Có | Ít query polling hơn |
| Publish status column | Thường có | Có thể không cần |
| Checkpoint | DB row/lease | Connector offset/log position |
| Replay | Theo outbox rows | Theo offset/retention |
| Failure mode | Lock/lease/duplicate | WAL retention/connector lag/schema |
| Phù hợp | Đơn giản, volume vừa | Streaming platform, volume lớn |

Không có lựa chọn tốt nhất cho mọi trường hợp. Hãy tính chi phí vận hành, recovery, retention và yêu cầu ordering.

## 37. Những sai lầm thường gặp

**“Đặt @Transactional là đủ để DB và Kafka commit cùng nhau.”** Transaction manager mặc định của DB không tự bao trùm broker.

**“Gửi message xong rồi mới lưu outbox.”** Outbox phải được ghi trong cùng transaction với business change.

**“Mark published trước khi gửi.”** Crash sau mark có thể làm mất event.

**“Publish rồi mark thì chắc chắn chỉ một lần.”** Crash giữa hai bước có thể gây duplicate; consumer phải idempotent.

**“Consumer SELECT trước rồi INSERT inbox là đủ.”** Hai instance có thể cùng SELECT chưa thấy row và cùng xử lý; unique constraint/atomic insert phải quyết định.

**“Inbox insert commit riêng rồi mới cập nhật business state.”** Có thể đánh dấu processed dù business update thất bại.

**“Ack trước DB commit.”** Crash sau ack nhưng trước commit có thể mất business update.

**“Event ID giải quyết mọi duplicate.”** Hai event ID khác nhau vẫn có thể cùng logical command; cần idempotency/business unique key.

**“Kafka idempotent producer bảo vệ mọi consumer side effect.”** Nó chỉ xử lý một phạm vi duplicate ở producer/broker, không bao trùm database và API ngoài.

**“External API nằm trong @Transactional.”** HTTP call không rollback cùng database transaction.

**“Retry vô hạn giúp message không mất.”** Nó tạo hot loop, backlog và có thể làm dependency quá tải.

**“DLQ là xong.”** Message chưa xử lý vẫn cần owner, alert, retention và replay.

**“Inbox có thể xóa sau vài giờ.”** Replay từ backup/DLQ sau đó có thể tạo side effect lần nữa.

**“Event ordering tự được bảo đảm.”** Cần xác định phạm vi partition/aggregate, version và retry semantics.

**“Outbox payload cứ serialize entity.”** Điều đó tạo contract gắn chặt với JPA model, có thể lộ PII và phá replay khi entity đổi.

## 38. Hướng dẫn triển khai theo từng bước

1. **Xác định business event:** sự kiện chỉ được tạo khi aggregate chuyển trạng thái hợp lệ.
2. **Định nghĩa contract:** event type, ID, aggregate key, schema version, business version và payload tối thiểu.
3. **Tạo outbox schema:** index pending, trạng thái, retry/lease và retention.
4. **Ghi outbox trong business transaction:** dùng cùng DB transaction manager.
5. **Chọn relay:** polling hoặc CDC dựa trên volume, latency và năng lực vận hành.
6. **Xác nhận publish:** dùng broker confirmation/ack phù hợp.
7. **Chấp nhận at-least-once:** retry cùng event ID, không giả định exactly-once.
8. **Tạo inbox:** unique key theo consumer + event ID.
9. **Cập nhật business state trong cùng transaction inbox:** commit/rollback đồng thời.
10. **Đặt ack/offset sau commit:** kiểm tra listener container config.
11. **Bảo vệ side effect ngoài:** idempotency key, outbox command và reconciliation.
12. **Xử lý ordering:** aggregate version/sequence, partition key và gap policy.
13. **Thiết kế retry/DLQ:** có giới hạn, backoff, jitter, owner và replay.
14. **Quan sát:** pending age, publish failures, duplicate rate, consumer lag và business outcome.
15. **Kiểm thử failure windows:** crash ở từng điểm trước/sau commit, publish, mark và ack.
16. **Vận hành retention:** cleanup an toàn, backup, schema evolution và audit.

## 39. Bài tập thực hành

Một Order Service dùng PostgreSQL và Kafka. Khi đơn được xác nhận, Inventory Service cần giữ hàng; Notification Service gửi email. Giả định:

- Một order có thể nhận lệnh confirm lặp do client retry.
- Producer có thể crash sau DB commit.
- Broker có thể nhận event nhưng relay không nhận được confirmation.
- Consumer có thể crash sau DB commit trước ack.
- Inventory reservation không được tạo hai lần.
- Email provider có thể gửi thành công nhưng response timeout.
- Các event của cùng order cần được xử lý theo version.

**Yêu cầu:**

1. Thiết kế bảng outbox gồm event ID, aggregate key/version, payload, status và retry/lease.
2. Định nghĩa transaction ghi order và outbox cùng commit.
3. Chọn polling hay CDC relay và giải thích.
4. Xử lý publish thành công nhưng relay crash trước mark.
5. Thiết kế inbox unique theo consumer_name + event_id.
6. Đảm bảo inbox và inventory update cùng local transaction.
7. Chọn thời điểm Kafka offset/RabbitMQ ack.
8. Chống hai consumer instance xử lý cùng event đồng thời.
9. Phân biệt event duplicate với command retry có event ID mới.
10. Xử lý version 12 đến trước version 11.
11. Đưa email sang external command/outbox và xử lý timeout không rõ kết quả.
12. Định nghĩa retry, DLQ, retention và replay.
13. Thiết kế metrics/alerts để phát hiện pending backlog và duplicate rate.
14. Viết integration tests cho crash sau commit trước ack.
15. Giải thích vì sao không thể cam kết exactly-once cho toàn workflow chỉ bằng broker.

**Hướng giải tham khảo:** Order và outbox ghi trong cùng PostgreSQL transaction; relay publish rồi mark, chấp nhận duplicate; event ID giữ nguyên; Inventory consumer insert inbox và reserve hàng cùng transaction; offset/ack sau commit; business idempotency key bảo vệ command retry; version guard bảo vệ ordering; Email consumer tạo outbound request bền vững và dùng provider idempotency/reconciliation; DLQ và metrics có owner.

## 40. Checklist nghiệm thu

### Producer / Outbox

- Event chỉ phát sinh khi business state transition hợp lệ?
- Business row và outbox row dùng cùng database transaction?
- Rollback không để lại event?
- Event ID ổn định qua mọi retry?
- Aggregate ID/version và schema version rõ?
- Payload có contract, không phụ thuộc JPA entity?
- Relay có broker confirmation phù hợp?
- Publish thành công nhưng mark thất bại có thể duplicate an toàn?
- Claim/lease/concurrency có giới hạn?
- Ordering theo aggregate có được xử lý nếu cần?

### Consumer / Inbox

- Inbox unique theo consumer và event ID?
- Inbox insert và business update cùng transaction?
- Ack/offset chỉ tiến sau commit?
- Duplicate đồng thời được database constraint xử lý?
- Business command retry có idempotency key?
- Event cũ/out-of-order có version guard?
- External side effect có provider idempotency hoặc reconciliation?
- Retry/DLQ có giới hạn, alert và replay policy?

### Vận hành

- Pending age/backlog/lag được quan sát?
- Disk/WAL/partition/inbox retention đủ?
- Cleanup không xóa pending hoặc replay cần thiết?
- PII và quyền truy cập event được bảo vệ?
- Có test crash ở từng failure window?
- Có runbook cho broker outage, relay backlog, DLQ và replay?
- Schema evolution tương thích với event lịch sử?
- Business invariants được kiểm tra sau xử lý?

---

**Điểm cốt lõi:** Transactional Outbox làm cho **business change và ý định phát event cùng commit trong một database transaction**. Relay gửi event theo mô hình thường là at-least-once, vì vậy duplicate là một failure mode cần được thiết kế sẵn. Consumer dùng Inbox/unique event ID, cập nhật business state cùng transaction và ack sau commit; command retry cần idempotency key, ordering cần version/sequence, còn external side effects cần outbox tiếp theo và reconciliation. Khi kết hợp các cơ chế này với retry có giới hạn, DLQ, observability và integration tests ở từng failure window, workflow phân tán có thể phục hồi an toàn khi process, database, broker hoặc consumer gặp lỗi.
