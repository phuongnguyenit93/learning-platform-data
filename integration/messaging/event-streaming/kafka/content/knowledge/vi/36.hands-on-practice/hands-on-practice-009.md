# Pipeline CDC, Outbox và consumer khử trùng

Trong một ứng dụng đặt hàng, thao tác tạo đơn hàng thường phải cập nhật database và phát sự kiện Kafka. Nếu ứng dụng commit database trước rồi gửi Kafka, process có thể dừng giữa hai thao tác và làm mất event. Nếu gửi Kafka trước rồi database rollback, consumer có thể nhận một sự kiện cho đơn hàng chưa tồn tại. Đây là lỗi dual-write: hai hệ thống độc lập không cùng một transaction.

Bài thực hành này xây dựng pipeline **Transactional Outbox + Change Data Capture (CDC)** bằng PostgreSQL, Debezium, Kafka Connect và Spring Kafka. Ứng dụng ghi đơn hàng và event vào cùng một transaction database; Debezium đọc thay đổi từ WAL và chuyển event sang Kafka; consumer ghi projection bằng cơ chế khử trùng dựa trên event id.

Bài thuộc chương **Thực hành tổng hợp** của module **KAFKA**. Sau khi hoàn thành, người học có thể:

- Giải thích vì sao dual-write có thể làm mất hoặc phát thừa sự kiện.
- Tạo bảng outbox và ghi event trong cùng transaction với dữ liệu nghiệp vụ.
- Cấu hình PostgreSQL logical replication và Debezium Outbox Event Router.
- Định tuyến event theo aggregate type và dùng aggregate id làm Kafka key.
- Viết consumer Spring Kafka có khả năng xử lý lại cùng event mà không nhân đôi tác dụng phụ.
- Kiểm thử rollback, CDC, ordering, duplicate delivery và phục hồi connector.

## 1. Kiến trúc và luồng dữ liệu

Pipeline thực hành gồm bốn thành phần:

    Spring Boot Order Service
          |
          | Một transaction PostgreSQL
          v
    +-----------------------------+
    | orders                      |
    | outbox_events               |
    +-----------------------------+
          |
          | PostgreSQL WAL / logical replication
          v
    Debezium PostgreSQL Connector
          |
          | Outbox Event Router SMT
          v
    Kafka topic: orders.events
          |
          | key = aggregateid
          v
    Spring Kafka Consumer
          |
          | Một transaction ở database consumer
          v
    +-----------------------------+
    | processed_events            |
    | order_projection            |
    +-----------------------------+

Ứng dụng không gửi event trực tiếp sau khi lưu đơn hàng. Nó ghi một hàng vào outbox trong cùng transaction với đơn hàng. Khi transaction commit, cả hai hàng cùng xuất hiện; khi rollback, cả hai cùng biến mất. Debezium đọc thay đổi đã commit từ log database và xuất event sang Kafka.

Consumer vẫn phải chịu được duplicate delivery. Connector có thể phát lại một số bản ghi sau khi restart, mất kết nối hoặc khôi phục offset. Outbox giải quyết tính nguyên tử giữa database nguồn và ý định phát event; nó không tự tạo bảo đảm end-to-end exactly-once cho mọi hệ thống đích.

### Công nghệ và điều kiện tiên quyết

- Java 17 trở lên và Spring Boot/Spring Kafka.
- PostgreSQL có bật logical replication.
- Kafka broker và Kafka Connect worker đang chạy.
- Debezium PostgreSQL connector và Outbox Event Router SMT đã được cài trong Kafka Connect.
- Một database riêng cho projection của consumer, hoặc schema riêng được quản lý bằng transaction độc lập.

Các ví dụ dùng PostgreSQL, JSONB và Debezium 2.x. Tên thuộc tính hoặc cách cài plugin có thể khác theo phiên bản Debezium, Kafka Connect và Spring Kafka. Hãy dùng tài liệu đúng phiên bản đang triển khai, đồng thời giữ cùng một phiên bản connector trên mọi worker trong distributed Connect cluster.

## 2. Tạo cấu trúc database nguồn

Tạo bảng đơn hàng và outbox trong cùng database:

    CREATE TABLE orders (
        id UUID PRIMARY KEY,
        customer_id VARCHAR(100) NOT NULL,
        amount NUMERIC(18, 2) NOT NULL,
        currency VARCHAR(3) NOT NULL,
        status VARCHAR(30) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE outbox_events (
        id UUID PRIMARY KEY,
        aggregatetype VARCHAR(255) NOT NULL,
        aggregateid VARCHAR(255) NOT NULL,
        type VARCHAR(255) NOT NULL,
        payload JSONB NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
    );

Các cột outbox theo quy ước của Outbox Event Router:

| Cột | Vai trò |
|---|---|
| id | Định danh duy nhất của event |
| aggregatetype | Nhóm aggregate dùng để định tuyến topic |
| aggregateid | Định danh aggregate, được dùng làm Kafka key |
| type | Loại event, ví dụ OrderCreated |
| payload | Nội dung event |
| timestamp | Thời điểm tạo event |

Trong ví dụ này, aggregatetype có giá trị orders, vì vậy topic đích là orders.events. aggregateid là order id, nên các event của cùng một đơn hàng có cùng Kafka key. Cần giữ tên cột và kiểu dữ liệu phù hợp với cấu hình SMT; nếu đổi tên cột, phải cập nhật connector config tương ứng.

Không cần tạo một bảng riêng cho mỗi loại event. Một outbox table có thể lưu nhiều aggregate type và event type, miễn là schema và chính sách phân quyền phù hợp.

## 3. Ghi đơn hàng và outbox trong cùng transaction

Định nghĩa event có event id ổn định. Đưa event id vào payload để consumer dễ khử trùng; Outbox Event Router cũng có thể chuyển id của outbox thành metadata/header theo cấu hình:

    public record OrderCreated(
            UUID eventId,
            UUID orderId,
            String customerId,
            BigDecimal amount,
            String currency,
            Instant occurredAt) {
    }

Service ghi đơn hàng và outbox:

    @Service
    public class OrderService {
        private final OrderRepository orderRepository;
        private final JdbcTemplate jdbcTemplate;
        private final ObjectMapper objectMapper;

        public OrderService(
                OrderRepository orderRepository,
                JdbcTemplate jdbcTemplate,
                ObjectMapper objectMapper) {
            this.orderRepository = orderRepository;
            this.jdbcTemplate = jdbcTemplate;
            this.objectMapper = objectMapper;
        }

        @Transactional
        public UUID createOrder(
                String customerId,
                BigDecimal amount,
                String currency) {

            UUID orderId = UUID.randomUUID();
            UUID eventId = UUID.randomUUID();
            Instant now = Instant.now();

            Order order = new Order(
                    orderId, customerId, amount, currency, "CREATED");
            orderRepository.save(order);

            OrderCreated event = new OrderCreated(
                    eventId, orderId, customerId, amount, currency, now);

            final String payload;
            try {
                payload = objectMapper.writeValueAsString(event);
            }
            catch (JsonProcessingException ex) {
                throw new IllegalStateException(
                        "Cannot serialize OrderCreated event", ex);
            }

            jdbcTemplate.update("""
                    INSERT INTO outbox_events
                        (id, aggregatetype, aggregateid, type, payload, timestamp)
                    VALUES (?, ?, ?, ?, CAST(? AS jsonb), ?)
                    """,
                    eventId,
                    "orders",
                    orderId.toString(),
                    "OrderCreated",
                    payload,
                    Timestamp.from(now));

            return orderId;
        }
    }

Đoạn code giả định OrderRepository và JdbcTemplate dùng cùng PostgreSQL DataSource và cùng transaction manager. Không đặt thao tác ghi outbox trong transaction độc lập như REQUIRES_NEW. Nếu hai thao tác dùng hai transaction khác nhau, lỗi dual-write vẫn còn.

Việc serialize payload diễn ra trước khi transaction commit. Nếu serialize thất bại, exception runtime làm transaction rollback; đơn hàng không được lưu một mình. Tương tự, nếu insert outbox thất bại, transaction cũng rollback phần ghi đơn hàng.

Không gọi KafkaTemplate.send() trong service này để phát cùng event. Debezium sẽ đọc outbox từ WAL sau khi transaction nguồn commit. Tránh gửi đồng thời bằng cả CDC và KafkaTemplate vì như vậy tạo hai đường phát và có thể nhân đôi event.

## 4. Bật logical replication trên PostgreSQL

Debezium PostgreSQL connector sử dụng logical decoding để đọc thay đổi. Trên PostgreSQL, cấu hình máy chủ cần đáp ứng tối thiểu:

    wal_level = logical
    max_replication_slots = 10
    max_wal_senders = 10

Giá trị thực tế cần dựa trên số connector và tải hệ thống. Thay đổi một số tham số có thể cần restart PostgreSQL. Không áp dụng trực tiếp lên production nếu chưa đánh giá cửa sổ bảo trì và dung lượng WAL.

Tạo user riêng cho connector, cấp quyền kết nối, đọc bảng và quyền replication theo phiên bản PostgreSQL:

    CREATE ROLE debezium LOGIN REPLICATION PASSWORD 'use-a-secret-store';
    GRANT CONNECT ON DATABASE orders TO debezium;
    GRANT USAGE ON SCHEMA public TO debezium;
    GRANT SELECT ON TABLE public.outbox_events TO debezium;

Debezium cũng cần quyền tạo hoặc sử dụng publication và replication slot. Cách cấp quyền cụ thể phụ thuộc phiên bản PostgreSQL, cấu hình publication và cách vận hành connector. Trong môi trường production, ưu tiên tạo publication/slot theo quy trình quản trị có kiểm soát thay vì cấp quyền superuser cho connector.

Nếu connector được phép tự tạo publication, cấu hình publication theo danh sách bảng được capture. Nếu tự tạo publication, bảo đảm bảng outbox nằm trong publication đó. Tên slot và publication phải duy nhất trong cluster và không được dùng chung cho hai connector độc lập.

## 5. Cấu hình Debezium PostgreSQL Connector

Trước khi tạo connector, xác nhận plugin Debezium và Outbox Event Router SMT đã có trên mọi Kafka Connect worker. Một worker thiếu plugin có thể làm task không khởi động dù REST API đã nhận cấu hình.

Ví dụ cấu hình connector:

    {
      "name": "orders-outbox-connector",
      "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "tasks.max": "1",
        "database.hostname": "postgres",
        "database.port": "5432",
        "database.user": "debezium",
        "database.password": "inject-from-secret-store",
        "database.dbname": "orders",
        "topic.prefix": "orders-cdc",
        "plugin.name": "pgoutput",
        "slot.name": "orders_outbox_slot",
        "publication.name": "orders_outbox_publication",
        "publication.autocreate.mode": "filtered",
        "table.include.list": "public.outbox_events",
        "transforms": "outbox",
        "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
        "transforms.outbox.table.field.event.id": "id",
        "transforms.outbox.table.field.event.key": "aggregateid",
        "transforms.outbox.table.field.event.type": "type",
        "transforms.outbox.table.field.event.payload": "payload",
        "transforms.outbox.route.by.field": "aggregatetype",
        "transforms.outbox.route.topic.replacement": "${routedByValue}.events",
        "transforms.outbox.table.expand.json.payload": "true"
      }
    }

Các điểm cần hiểu:

- database.hostname, database.port, database.user, database.password và database.dbname xác định database nguồn. Không lưu mật khẩu thật trong file cấu hình được commit vào Git.
- topic.prefix là định danh connector trong các topic CDC nội bộ của Debezium. Event Router định tuyến event outbox theo aggregatetype.
- plugin.name=pgoutput sử dụng logical decoding tích hợp của PostgreSQL.
- slot.name và publication.name xác định tài nguyên logical replication.
- table.include.list giới hạn bảng được capture trong bài thực hành.
- transforms.outbox.* cấu hình Outbox Event Router: lấy id làm event id, aggregateid làm Kafka key, type làm event type và payload làm value.
- table.expand.json.payload=true yêu cầu SMT mở rộng JSON payload để consumer nhận nội dung JSON theo dạng dữ liệu, thay vì coi payload như chuỗi JSON lồng bên trong.

Với cấu hình trên, hàng outbox có aggregatetype là orders được định tuyến đến topic orders.events. Giá trị aggregateid được dùng làm key. Hãy tạo topic trước trong môi trường cần kiểm soát cấu hình; không phụ thuộc vào auto topic creation ở production.

Thuộc tính publication.autocreate.mode có thể khác hoặc không có ở các phiên bản Debezium cũ. Nếu dùng phiên bản không hỗ trợ, tạo publication theo hướng dẫn của connector rồi đặt chế độ tự tạo phù hợp. Kiểm tra chính xác tên thuộc tính của phiên bản connector đang chạy.

Đăng ký connector qua Kafka Connect REST API:

    curl -X POST http://localhost:8083/connectors \
      -H "Content-Type: application/json" \
      --data @orders-outbox-connector.json

Kiểm tra trạng thái:

    curl http://localhost:8083/connectors/orders-outbox-connector/status

Connector và task cần ở trạng thái RUNNING. Nếu task FAILED, xem trace trong response và log của Connect worker; lỗi thường gặp gồm thiếu plugin, quyền publication/slot, sai thông tin kết nối, không truy cập được database hoặc cấu hình SMT không hợp lệ.

Khi connector chạy lần đầu, chế độ snapshot có thể đọc dữ liệu đang có trong bảng được capture. Bài lab nên bắt đầu với outbox table rỗng hoặc có kế hoạch rõ ràng cho các hàng cũ; nếu không, event lịch sử có thể được phát lại trong quá trình khởi tạo connector.

## 6. Tạo topic và kiểm tra key/order

Tạo topic đích với số partition phù hợp và replication factor theo môi trường:

    kafka-topics.sh \
      --bootstrap-server localhost:9092 \
      --create \
      --topic orders.events \
      --partitions 6 \
      --replication-factor 1

Replication factor 1 chỉ phù hợp với broker đơn trong lab cục bộ. Trong môi trường nhiều broker, chọn replication factor và min.insync.replicas theo yêu cầu độ bền dữ liệu.

Event Router dùng aggregateid làm key. Vì vậy, mọi event có cùng order id được đưa vào cùng partition khi số partition và quy tắc partitioning không đổi. Kafka bảo đảm thứ tự trong partition, không có thứ tự tổng thể giữa sáu partition.

Nếu tăng số partition của topic, phép ánh xạ key sang partition có thể thay đổi. Event cũ và mới của cùng order có thể đi vào partition khác nhau sau thay đổi đó. Nếu thứ tự xuyên suốt theo aggregate là yêu cầu bắt buộc, phải có kế hoạch thay đổi partition và kiểm thử trước khi áp dụng.

## 7. Consumer Spring Kafka có idempotency

Consumer ghi projection vào database đích. Tạo bảng lưu event đã xử lý và bảng projection:

    CREATE TABLE processed_events (
        event_id UUID PRIMARY KEY,
        processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE order_projection (
        order_id UUID PRIMARY KEY,
        customer_id VARCHAR(100) NOT NULL,
        amount NUMERIC(18, 2) NOT NULL,
        currency VARCHAR(3) NOT NULL,
        last_event_id UUID NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

Consumer DTO có thể dùng cùng cấu trúc payload:

    public record OrderCreated(
            UUID eventId,
            UUID orderId,
            String customerId,
            BigDecimal amount,
            String currency,
            Instant occurredAt) {
    }

Service xử lý một lần theo event id:

    @Service
    public class OrderProjectionService {
        private final JdbcTemplate jdbcTemplate;

        public OrderProjectionService(JdbcTemplate jdbcTemplate) {
            this.jdbcTemplate = jdbcTemplate;
        }

        @Transactional
        public void applyOnce(OrderCreated event) {
            int inserted = jdbcTemplate.update("""
                    INSERT INTO processed_events (event_id)
                    VALUES (?)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    event.eventId());

            if (inserted == 0) {
                return;
            }

            jdbcTemplate.update("""
                    INSERT INTO order_projection
                        (order_id, customer_id, amount, currency,
                         last_event_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, now())
                    ON CONFLICT (order_id) DO UPDATE SET
                        customer_id = EXCLUDED.customer_id,
                        amount = EXCLUDED.amount,
                        currency = EXCLUDED.currency,
                        last_event_id = EXCLUDED.last_event_id,
                        updated_at = now()
                    """,
                    event.orderId(),
                    event.customerId(),
                    event.amount(),
                    event.currency(),
                    event.eventId());
        }
    }

Việc insert vào processed_events và cập nhật order_projection nằm trong cùng transaction database. Nếu cập nhật projection thất bại, insert event id cũng rollback. Khi event được giao lại, consumer có thể thử lại từ đầu. Nếu transaction đã commit nhưng Kafka offset chưa commit, lần giao lại sẽ gặp event id đã tồn tại và không lặp tác dụng phụ.

Listener gọi service:

    @KafkaListener(
            topics = "orders.events",
            groupId = "orders-projection")
    public void onOrderCreated(OrderCreated event) {
        orderProjectionService.applyOnce(event);
    }

Cấu hình JSON deserializer cần trỏ về DTO đã kiểm soát. Ví dụ với Spring Boot:

    spring:
      kafka:
        consumer:
          enable-auto-commit: false
          key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
          value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
          properties:
            spring.json.value.default.type: com.example.events.OrderCreated
            spring.json.trusted.packages: com.example.events
            spring.json.use.type.headers: false

Đảm bảo Jackson có module Java Time nếu DTO chứa Instant. Chỉ tin cậy package event cần thiết; không mở trusted packages cho mọi kiểu class. Chọn acknowledgment mode và error handler để offset chỉ được commit sau khi listener/service xử lý thành công theo chính sách ứng dụng. Không bật auto commit theo thời gian cho luồng cần kiểm soát chính xác thời điểm xác nhận.

Khử trùng ở database consumer chỉ bảo vệ các tác dụng phụ nằm trong cùng transaction database đó. Nếu consumer gọi API thanh toán hoặc gửi email, thao tác bên ngoài không rollback cùng database. Khi cần chống lặp cho hệ thống ngoài, truyền event id làm idempotency key tới dịch vụ đích hoặc ghi tiếp một outbox ở consumer để phát lệnh ra ngoài theo quy trình bền vững.

## 8. Chạy bài thực hành

Thực hiện theo thứ tự:

1. Khởi chạy PostgreSQL, Kafka broker và Kafka Connect; xác nhận connector plugin có trên worker.
2. Bật logical replication và tạo database user, publication/slot theo cấu hình lab.
3. Tạo bảng orders và outbox_events; tạo topic orders.events.
4. Khởi động Order Service và đăng ký Debezium connector.
5. Kiểm tra connector/task ở trạng thái RUNNING.
6. Khởi động consumer projection và xác nhận database đích đã có bảng processed_events, order_projection.
7. Gọi API tạo một đơn hàng.
8. Kiểm tra database nguồn có một hàng orders và một hàng outbox_events với cùng order id trong payload.
9. Đọc topic orders.events; xác nhận event có event id, order id và key tương ứng.
10. Kiểm tra database consumer có một event id và một projection cho đơn hàng đó.

Có thể đọc topic bằng console consumer để quan sát key và value:

    kafka-console-consumer.sh \
      --bootstrap-server localhost:9092 \
      --topic orders.events \
      --from-beginning \
      --property print.key=true \
      --property key.separator=" : "

Nếu topic đã có dữ liệu từ các lần chạy trước, dùng group id mới hoặc giới hạn phép đọc để không nhầm dữ liệu cũ với event vừa tạo. Trong môi trường dùng dữ liệu thật, không dùng from-beginning tùy tiện vì có thể in ra payload nhạy cảm.

## 9. Kịch bản kiểm thử bắt buộc

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Commit thành công | Tạo một đơn hàng bình thường | Cả orders và outbox_events có dữ liệu; Kafka nhận một event logic |
| Rollback nguồn | Gây exception runtime sau khi lưu order và trước khi transaction commit | Cả order và outbox row đều không tồn tại; không có event được phát từ transaction đó |
| Event trùng | Gửi lại cùng payload với cùng eventId | processed_events chỉ có một hàng cho event id; projection không bị áp dụng lặp |
| Hai event cùng aggregate | Tạo hai event tuần tự cho cùng order id | Cùng Kafka key và cùng partition; offset tăng theo thứ tự broker ghi |
| Hai aggregate khác nhau | Tạo event cho hai order id | Có thể ở cùng hoặc khác partition; không yêu cầu thứ tự toàn cục |
| Connector restart | Tạm dừng connector, tạo event rồi khởi động lại connector | Event được chuyển tiếp sau khi connector phục hồi; consumer chịu được khả năng giao lại |
| Consumer restart sau DB commit | Cho service commit database rồi dừng consumer trước khi offset được xác nhận | Kafka có thể giao lại event; idempotency ngăn cập nhật trùng |
| Schema/payload lỗi | Đưa một event sai cấu trúc vào topic thử nghiệm | Consumer báo lỗi có ngữ cảnh; record được retry hoặc cách ly theo error policy |

Với bài rollback, tạo một nhánh test hoặc endpoint chỉ dùng trong môi trường lab để cố ý ném exception runtime sau khi ghi outbox. Không tạo endpoint gây lỗi này trong production.

Để xác minh event trùng, có thể phát lại cùng event id vào topic thử nghiệm hoặc gọi handler hai lần bằng cùng DTO. Kết quả phải thể hiện một bản ghi processed_events và một tác dụng phụ nghiệp vụ. Không tạo event id mới cho lần retry của cùng một event logic.

## 10. Vận hành, retention và phục hồi

### Theo dõi connector và WAL

Theo dõi connector/task state, lỗi task, thời gian xử lý, lượng WAL giữ lại bởi replication slot và dung lượng database. Nếu connector dừng lâu, replication slot có thể giữ WAL chưa được xác nhận, làm đĩa PostgreSQL tăng nhanh. Cần cảnh báo slot lag và có quy trình xử lý connector bị mất khả năng phục hồi; xóa slot đang hoạt động hoặc reset offset một cách tùy tiện có thể làm mất khả năng tiếp tục CDC đúng điểm.

### Dọn outbox

Outbox table sẽ tăng theo số event. Thiết kế retention và cleanup dựa trên thời gian lưu cần thiết, tiến độ connector, khả năng snapshot lại và yêu cầu điều tra. Không xóa ngay sau khi insert chỉ vì đã thấy event trên Kafka trong một lần quan sát. Một quy trình cleanup an toàn cần biết connector đã đọc đến đâu và có cách khôi phục nếu connector phải snapshot hoặc tái tạo slot.

Có thể phân vùng bảng theo thời gian hoặc dùng job xóa theo lô khi quy mô lớn. Dọn dữ liệu theo lô nhỏ để tránh transaction dài và bloat. Giữ event id và metadata cần thiết ở hệ thống đích để vẫn điều tra được sau khi outbox đã được dọn.

### Retention của Kafka và replay

Retention của topic phải đủ dài cho thời gian consumer gián đoạn và cửa sổ replay. Nếu consumer bị dừng lâu hơn retention, Kafka có thể xóa event trước khi consumer đọc. DLT và outbox không thay thế kế hoạch backup/retention cho dữ liệu nghiệp vụ.

Khi replay, giữ nguyên event id để consumer nhận ra cùng một event. Nếu muốn áp dụng một thay đổi nghiệp vụ mới, tạo một event mới với id mới và quan hệ nguồn gốc rõ ràng; không sửa event cũ rồi phát lại dưới cùng định danh.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Connector task FAILED ngay khi khởi động | Thiếu plugin, sai config hoặc không kết nối được PostgreSQL | Connect worker log, connector status và REST config |
| Không thấy event trên topic | Table không nằm trong publication/include list, transaction chưa commit hoặc SMT route sai | Kiểm tra outbox row, publication, slot, connector task và topic đích |
| Topic sai tên | aggregatetype hoặc route replacement không đúng | Đối chiếu giá trị aggregatetype với cấu hình route |
| Key Kafka rỗng | Sai tên cột aggregate id hoặc mapping key của SMT | Kiểm tra table.field.event.key và dữ liệu aggregateid |
| Consumer deserialize lỗi | Payload không được mở rộng thành JSON hoặc DTO không khớp | Kiểm tra table.expand.json.payload, byte/value và JSON deserializer |
| Event bị xử lý hai lần | Connector phát lại hoặc consumer commit offset sau DB commit thất bại | Kiểm tra event id và processed_events |
| Outbox table tăng nhanh | Không có cleanup hoặc connector lag | Theo dõi slot lag, WAL và chính sách retention |
| PostgreSQL hết dung lượng | Replication slot giữ WAL quá lâu | Khôi phục connector/slot theo runbook và giải phóng dung lượng an toàn |
| Thứ tự theo order bị sai | Key không ổn định, consumer xử lý song song hoặc tăng số partition | Kiểm tra key, partition, concurrency và cách thay đổi partition |

Không xóa replication slot, publication hoặc connector offset chỉ để làm trạng thái chuyển sang RUNNING. Trước khi reset, cần xác định điểm WAL đã xử lý, dữ liệu còn trong outbox và chiến lược snapshot/replay; reset sai có thể bỏ sót hoặc phát lại lượng lớn event.

## 12. Tiêu chí hoàn thành

- [ ] Ghi order và outbox event trong cùng một transaction database.
- [ ] Kiểm chứng rollback không để lại order hoặc outbox row.
- [ ] PostgreSQL logical replication và Debezium connector hoạt động.
- [ ] Outbox Event Router định tuyến theo aggregate type.
- [ ] Kafka key lấy từ aggregate id.
- [ ] Consumer xử lý event trong transaction database đích.
- [ ] Bảng processed_events ngăn cùng event id tạo tác dụng phụ hai lần.
- [ ] Test duplicate delivery và consumer restart đều cho kết quả đúng.
- [ ] Kiểm tra ordering trong cùng partition và hiểu giới hạn khi tăng partition.
- [ ] Có kế hoạch giám sát connector, replication slot, WAL, outbox cleanup và Kafka retention.

Kết quả của bài thực hành là một pipeline CDC có thể phục hồi: database nguồn lưu trạng thái nghiệp vụ và ý định phát event một cách nguyên tử; Debezium chuyển event sang Kafka; consumer khử trùng trước khi cập nhật trạng thái đích. Khi vận hành đúng, hệ thống có thể chịu được restart và giao lại bản tin mà không phụ thuộc vào một lần gửi duy nhất.
