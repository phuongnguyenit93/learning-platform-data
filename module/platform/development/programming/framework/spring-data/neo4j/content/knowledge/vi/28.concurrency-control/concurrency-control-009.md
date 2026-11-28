# Idempotency và tác động phụ khi một giao dịch được chạy lại

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao một transaction callback có thể được thực thi nhiều lần.
- Phân biệt retry của Neo4j Java Driver với transaction do Spring quản lý.
- Nhận diện thao tác idempotent và non-idempotent trong Cypher.
- Thiết kế idempotency key và uniqueness constraint để chống xử lý trùng.
- Giữ các tác động phụ bên ngoài database khỏi transaction có thể được chạy lại.
- Dùng transactional outbox và consumer deduplication để phát sự kiện đáng tin cậy.
- Kiểm thử hành vi khi cùng một yêu cầu được gửi lại hoặc chạy đồng thời.

## 1. Vì sao một giao dịch có thể được chạy lại?

Neo4j Java Driver cung cấp managed transaction qua các phương thức Session.executeRead() và Session.executeWrite(). Ứng dụng truyền vào một callback chứa các câu lệnh Cypher và logic xử lý kết quả.

Khi gặp một lỗi được đánh dấu là transient, driver có thể tự động rollback transaction attempt hiện tại và gọi lại callback để thử lần nữa. Vì vậy, callback không có bảo đảm chỉ được gọi đúng một lần.

Đây là hành vi của managed transaction qua executeRead/executeWrite. Với explicit transaction bắt đầu bằng Session.beginTransaction(), ứng dụng tự điều khiển commit/rollback và không nhận cơ chế tự gọi lại callback managed như trên. Nếu tự thêm retry quanh explicit transaction hoặc service method, vẫn phải giả định toàn bộ nghiệp vụ có thể được chạy lại.

Ví dụ, một thao tác đặt hàng có thể trải qua các bước:

1. Tìm tồn kho của sản phẩm.
2. Trừ số lượng tồn kho.
3. Tạo Order.
4. Ghi sự kiện OrderCreated.
5. Commit transaction.

Nếu lỗi tạm thời xảy ra trước khi commit hoàn tất, driver có thể chạy lại toàn bộ callback. Những thay đổi trong transaction bị rollback sẽ không còn trong database, nhưng các tác động đã xảy ra bên ngoài transaction không tự được hoàn tác.

Đây là lý do callback cần được thiết kế để có cùng kết quả nghiệp vụ khi được thực thi lại với cùng một yêu cầu.

### Retry không có nghĩa mọi câu lệnh đã commit sẽ chạy lại

Mỗi transaction attempt là một đơn vị ACID. Nếu attempt thất bại và bị rollback, các thay đổi database trong attempt đó không được giữ lại. Callback có thể được gọi lại để tạo một attempt mới.

Tuy nhiên, một lời gọi email, HTTP API, message broker hoặc thao tác ghi file không nằm trong transaction Neo4j. Database không thể rollback những hành động đó.

Vì vậy, hãy phân biệt:

- **Database effect:** thay đổi node, relationship và property trong transaction.
- **External side effect:** hành động trên hệ thống khác hoặc trạng thái ngoài transaction.
- **Retry:** thực thi lại callback hoặc phương thức nghiệp vụ sau lỗi tạm thời.

## 2. Idempotency là gì?

Một thao tác idempotent là thao tác mà khi thực hiện nhiều lần với cùng một đầu vào, trạng thái cuối cùng tương đương với thực hiện một lần.

Có thể mô tả:

\[
f(f(state, command), command) = f(state, command)
\]

Ví dụ:

| Thao tác | Tính chất | Lý do |
|---|---|---|
| Đặt status thành CONFIRMED | Idempotent nếu cùng giá trị | Lần sau vẫn cho cùng trạng thái |
| MERGE node theo ID ổn định | Có thể idempotent | Lần sau tìm thấy node đã có |
| CREATE một Order mới | Non-idempotent | Mỗi lần chạy tạo thêm node |
| Trừ tồn kho thêm 1 | Non-idempotent | Mỗi lần chạy tiếp tục giảm |
| Tăng counter thêm 1 | Non-idempotent | Giá trị tăng theo số lần chạy |
| Gửi email xác nhận | Non-idempotent | Người nhận có thể nhận nhiều email |

Idempotency không có nghĩa query phải không thay đổi dữ liệu. Một lệnh cập nhật có thể thay đổi database ở lần đầu nhưng không tạo thêm thay đổi nghiệp vụ khi chạy lại cùng command.

Ví dụ, đặt trạng thái:

~~~cypher
MATCH (o:Order {id: $orderId})
SET o.status = $status
RETURN o
~~~

Nếu cùng orderId và status được truyền vào nhiều lần, trạng thái cuối vẫn như nhau.

Ngược lại:

~~~cypher
MATCH (s:Stock {sku: $sku})
SET s.available = s.available - $quantity
RETURN s.available
~~~

Chạy hai lần sẽ trừ tồn kho hai lần. Query này không idempotent nếu không có cơ chế chống xử lý trùng.

## 3. MERGE hữu ích nhưng chưa đủ để bảo đảm tính duy nhất

MERGE tìm pattern đã tồn tại; nếu không tìm thấy thì tạo pattern mới. Vì vậy, MERGE phù hợp hơn CREATE cho các thao tác có thể chạy lại.

Ví dụ:

~~~cypher
MERGE (p:Person {externalId: $externalId})
ON CREATE SET p.createdAt = datetime()
ON MATCH SET p.lastSeenAt = datetime()
RETURN p
~~~

Node Person được xác định bằng externalId. Tuy nhiên, ON MATCH SET p.lastSeenAt = datetime() vẫn làm dữ liệu thay đổi mỗi lần query chạy. Vì vậy, không thể kết luận toàn bộ query là idempotent chỉ vì nó dùng MERGE.

Hãy tách property định danh khỏi property thay đổi:

~~~cypher
MERGE (p:Person {externalId: $externalId})
ON CREATE SET p.createdAt = $createdAt
SET p.displayName = $displayName
RETURN p
~~~

Nếu cùng externalId, createdAt và displayName được truyền vào, lần chạy tiếp theo giữ trạng thái tương đương. Giá trị đầu vào nên ổn định qua các lần retry.

### Tại sao cần uniqueness constraint?

MERGE bảo đảm pattern được tìm hoặc tạo, nhưng bản thân MERGE không thay thế uniqueness constraint khi nhiều transaction chạy đồng thời.

Hãy tạo constraint cho khóa định danh:

~~~cypher
CREATE CONSTRAINT person_external_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.externalId IS UNIQUE
~~~

Với idempotency key của command:

~~~cypher
CREATE CONSTRAINT processed_command_key_unique IF NOT EXISTS
FOR (c:ProcessedCommand)
REQUIRE c.key IS UNIQUE
~~~

Constraint giúp database bảo vệ tính duy nhất của khóa khi nhiều request cùng đến. Nếu chỉ dùng MERGE trên một property không được ràng buộc duy nhất, các transaction đồng thời có thể tạo dữ liệu trùng ngoài ý muốn.

Cũng nên dùng khóa nghiệp vụ ổn định. Không nên MERGE theo tên hiển thị nếu nhiều người có thể trùng tên hoặc tên có thể thay đổi.

## 4. Idempotency key cho một yêu cầu nghiệp vụ

Idempotency key là định danh ổn định của một yêu cầu nghiệp vụ. Client tạo hoặc nhận key trước khi gửi request, sau đó dùng lại chính key đó nếu phải gửi lại cùng yêu cầu.

Ví dụ:

~~~text
POST /orders
Idempotency-Key: checkout-2026-000184
~~~

Ứng dụng lưu key cùng kết quả xử lý. Nếu request được gửi lại với cùng key, hệ thống trả lại kết quả đã tạo thay vì thực hiện nghiệp vụ lần nữa.

Một command có thể chứa:

~~~java
public record PlaceOrderCommand(
    String idempotencyKey,
    String customerId,
    String sku,
    int quantity
) {
}
~~~

Cần xác định quy tắc:

- Cùng key và cùng payload: trả lại kết quả đã xử lý.
- Cùng key nhưng payload khác: trả lỗi conflict hoặc lỗi validation.
- Key mới: xử lý như một yêu cầu mới.
- Key phải được giữ đủ lâu để bao phủ khoảng thời gian client có thể retry.

Không tự tạo key mới mỗi lần client retry. Nếu key thay đổi, server không thể biết đó là cùng một yêu cầu.

Nên lưu thêm các trường payload quan trọng hoặc fingerprint của payload để phát hiện việc tái sử dụng key sai mục đích.

Trong hệ thống nhiều tenant hoặc nhiều loại command, hãy xác định phạm vi key. Có thể dùng key duy nhất toàn database hoặc constraint ghép tenantId với key, tùy hợp đồng API. Không để hai nghiệp vụ khác nhau vô tình dùng chung một namespace idempotency key.

## 5. Ví dụ chống xử lý trùng khi đặt hàng

Giả sử một yêu cầu đặt hàng cần:

1. Tạo một ProcessedCommand theo idempotency key.
2. Trừ tồn kho đúng một lần.
3. Tạo Order.
4. Đánh dấu command đã hoàn tất.

Tạo constraint:

~~~cypher
CREATE CONSTRAINT processed_command_key_unique IF NOT EXISTS
FOR (c:ProcessedCommand)
REQUIRE c.key IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT outbox_event_id_unique IF NOT EXISTS
FOR (e:OutboxEvent)
REQUIRE e.eventId IS UNIQUE;

CREATE CONSTRAINT stock_sku_unique IF NOT EXISTS
FOR (s:Stock)
REQUIRE s.sku IS UNIQUE;

CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.id IS UNIQUE;
~~~

Mô hình dữ liệu:

~~~text
(:ProcessedCommand {key, state, orderId, customerId, sku, quantity})
(:Stock {sku, available})
(:Order {id, idempotencyKey, customerId, sku, quantity})
(:OutboxEvent {eventId, type, status, payload})
~~~

Dùng một command node làm dấu vết xử lý:

~~~cypher
MERGE (c:ProcessedCommand {key: $key})
ON CREATE SET
    c.state = 'IN_PROGRESS',
    c.orderId = $proposedOrderId,
    c.customerId = $customerId,
    c.sku = $sku,
    c.quantity = $quantity
RETURN c.state AS state,
       c.orderId AS orderId,
       c.customerId AS customerId,
       c.sku AS sku,
       c.quantity AS quantity
~~~

Nếu command đã tồn tại và có state COMPLETED, ứng dụng trả lại orderId đã lưu. Nếu command mới được tạo, state là IN_PROGRESS và ứng dụng tiếp tục xử lý trong cùng transaction.

Phần trừ tồn kho và tạo order:

~~~cypher
MATCH (c:ProcessedCommand {
    key: $key,
    state: 'IN_PROGRESS'
})
MATCH (customer:Customer {id: $customerId})
MATCH (s:Stock {sku: $sku})
WHERE s.available >= $quantity
SET s.available = s.available - $quantity

CREATE (o:Order {
    id: $orderId,
    idempotencyKey: $key,
    customerId: $customerId,
    sku: $sku,
    quantity: $quantity
})

CREATE (customer)-[:PLACED]->(o)
CREATE (c)-[:RESULTED_IN]->(o)
SET c.state = 'COMPLETED'

RETURN o.id AS orderId
~~~

Hai phần query phải chạy trong cùng một transaction. Nếu không tìm thấy Customer, không có Stock hoặc không đủ tồn kho, query thứ hai không trả record; ứng dụng cần làm transaction thất bại để command node vừa tạo và mọi thay đổi liên quan đều rollback.

Khi request được xử lý lại:

- Nếu transaction trước rollback, command node không tồn tại và lần chạy mới có thể xử lý lại.
- Nếu transaction trước đã commit nhưng client không nhận được response, command có state COMPLETED; lần chạy sau trả lại orderId cũ.
- Nếu hai request cùng key chạy đồng thời, uniqueness constraint ngăn tạo hai command node có cùng key. Tùy thời điểm tranh chấp, một request có thể gặp uniqueness conflict; hãy kết thúc transaction lỗi đó, mở transaction mới để đọc lại command và trả kết quả đã lưu sau khi xác minh payload.

### Kiểm tra payload khi key đã tồn tại

Sau khi đọc command node, so sánh customerId, sku và quantity đã lưu với command hiện tại. Nếu bất kỳ giá trị nào khác, từ chối request. Không được dùng lại key của đơn hàng cũ cho khách hàng, sản phẩm hoặc số lượng khác.

Một command node được tạo và chuyển sang COMPLETED trong cùng transaction. Nếu transaction rollback, cả node command cũng rollback. Nếu ứng dụng thiết kế quy trình nhiều transaction với trạng thái IN_PROGRESS được commit riêng, cần thêm lease, timeout và quy trình phục hồi cho command bị bỏ dở.

## 6. Managed transaction callback phải an toàn khi chạy lại

Ví dụ dưới đây minh họa cách dùng Java Driver managed transaction. Đây là API ở tầng driver; trong một ứng dụng SDN, có thể dùng repository hoặc Neo4jClient cho các query tương ứng.

Ví dụ này dùng trực tiếp Driver với managed transaction. Nếu service đang dùng @Transactional của Spring Data Neo4j, hãy thực hiện các query qua repository hoặc Neo4jClient tham gia transaction Spring; không mở thêm session/transaction độc lập cho cùng một đơn vị nghiệp vụ.

~~~java
import java.util.Map;
import java.util.UUID;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;

public class OrderWriter {

    private final Driver driver;

    public OrderWriter(Driver driver) {
        this.driver = driver;
    }

    public OrderResult placeOrder(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        // Sinh một lần bên ngoài callback để giữ ổn định qua retry.
        String proposedOrderId = UUID.randomUUID().toString();

        try (Session session = driver.session()) {
            return session.executeWrite(tx -> {

                Record claim = tx.run("""
                    MERGE (c:ProcessedCommand {key: $key})
                    ON CREATE SET
                        c.state = 'IN_PROGRESS',
                        c.orderId = $orderId,
                        c.customerId = $customerId,
                        c.sku = $sku,
                        c.quantity = $quantity
                    RETURN c.state AS state,
                           c.orderId AS orderId,
                           c.customerId AS customerId,
                           c.sku AS sku,
                           c.quantity AS quantity
                    """,
                    Map.of(
                        "key", command.idempotencyKey(),
                        "orderId", proposedOrderId,
                        "customerId", command.customerId(),
                        "sku", command.sku(),
                        "quantity", command.quantity()
                    )
                ).single();

                String storedSku = claim.get("sku").asString();
                String storedCustomerId = claim.get("customerId").asString();
                int storedQuantity = claim.get("quantity").asInt();
                String state = claim.get("state").asString();
                String orderId = claim.get("orderId").asString();

                if (!storedCustomerId.equals(command.customerId())
                        || !storedSku.equals(command.sku())
                        || storedQuantity != command.quantity()) {
                    throw new IllegalArgumentException(
                        "Idempotency key was reused with another payload"
                    );
                }

                if ("COMPLETED".equals(state)) {
                    return new OrderResult(orderId, false);
                }

                if (!"IN_PROGRESS".equals(state)) {
                    throw new IllegalStateException(
                        "Unsupported command state: " + state
                    );
                }

                tx.run("""
                    MATCH (c:ProcessedCommand {
                        key: $key,
                        state: 'IN_PROGRESS'
                    })
                    MATCH (customer:Customer {id: $customerId})
                    MATCH (s:Stock {sku: $sku})
                    WHERE s.available >= $quantity
                    SET s.available = s.available - $quantity

                    CREATE (o:Order {
                        id: $orderId,
                        idempotencyKey: $key,
                        customerId: $customerId,
                        sku: $sku,
                        quantity: $quantity
                    })

                    CREATE (customer)-[:PLACED]->(o)
                    CREATE (c)-[:RESULTED_IN]->(o)
                    SET c.state = 'COMPLETED'

                    CREATE (e:OutboxEvent {
                        eventId: $eventId,
                        type: 'OrderCreated',
                        orderId: $orderId,
                        status: 'PENDING',
                        createdAt: datetime()
                    })
                    CREATE (c)-[:EMITTED]->(e)
                    RETURN o.id AS orderId
                    """,
                    Map.of(
                        "key", command.idempotencyKey(),
                        "orderId", orderId,
                        "customerId", command.customerId(),
                        "sku", command.sku(),
                        "quantity", command.quantity(),
                        "eventId", command.idempotencyKey() + ":OrderCreated"
                    )
                ).single().get("orderId").asString();

                return new OrderResult(orderId, true);
            });
        }
    }
    public record OrderResult(String orderId, boolean created) {
    }
}
~~~

Ví dụ giả định đã có Customer và Stock node cùng constraint cho ProcessedCommand.key, Order.id, OutboxEvent.eventId, Stock.sku và Customer.id. Trong triển khai thực tế, hãy kiểm tra kết quả cập nhật tồn kho và tạo order trong cùng transaction; nếu không đủ hàng hoặc không tìm thấy Customer/Stock, phải ném lỗi để rollback toàn bộ attempt.

Các điểm quan trọng:

- proposedOrderId được tạo bên ngoài callback, nên cùng giá trị được dùng qua các lần retry trong một lời gọi.
- Idempotency key được giữ ổn định qua các lần client gửi lại request.
- Command đã COMPLETED không trừ tồn kho lần nữa.
- Order và OutboxEvent được tạo trong cùng transaction với cập nhật tồn kho.
- Callback không gọi email, HTTP API hoặc message broker.

Nếu transaction attempt rollback, command, Order, OutboxEvent và thay đổi tồn kho đều rollback cùng nhau. Nếu transaction đã commit nhưng response bị mất, lần gọi lại tìm thấy command COMPLETED và trả lại orderId cũ.

Ví dụ tập trung vào luồng thành công và không trình bày nhánh xử lý uniqueness conflict giữa hai transaction đồng thời. Trong service production, bắt lỗi conflict ở ngoài transaction đã thất bại, sau đó đọc ProcessedCommand bằng key trong một transaction mới; chỉ trả kết quả nếu payload khớp và state đã COMPLETED. Không tiếp tục chạy query trên transaction đã bị đánh dấu rollback-only.

## 7. Spring @Transactional và retry của Driver là hai cơ chế khác nhau

Trong Spring Data Neo4j, @Transactional xác định ranh giới transaction và phối hợp với Neo4jTransactionManager. Nó giúp commit hoặc rollback các thao tác repository, Neo4jClient và template tham gia cùng transaction.

Tuy nhiên, bản thân @Transactional không có nghĩa Spring sẽ tự động gọi lại method khi gặp lỗi transient.

Cần phân biệt:

| Cơ chế | Vai trò |
|---|---|
| Spring @Transactional | Mở ranh giới transaction, commit hoặc rollback |
| Neo4j Java Driver executeWrite/executeRead | Managed transaction có cơ chế retry callback khi gặp lỗi transient đủ điều kiện |
| Spring Retry hoặc retry ở tầng ứng dụng | Có thể gọi lại method/service theo policy do ứng dụng cấu hình |

Nếu ứng dụng bổ sung retry ở tầng service, method nghiệp vụ vẫn có thể được gọi nhiều lần. Hãy đặt ranh giới transaction sao cho mỗi attempt có transaction phù hợp và bảo đảm command idempotent.

Ví dụ service dùng SDN:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Order createOrder(PlaceOrderCommand command) {
        // Repository/Neo4jClient thao tác trong transaction này.
        // Idempotency key phải được kiểm tra và lưu cùng kết quả.
        return orders.createIdempotently(command);
    }
}
~~~

Phần createIdempotently ở ví dụ là method minh họa cho repository fragment hoặc custom query implementation. Hãy giữ kiểm tra key, thay đổi tồn kho, tạo order và ghi outbox trong cùng transaction nếu chúng phải thành công hoặc thất bại cùng nhau.

## 8. Vì sao không gửi email hoặc gọi API bên trong transaction callback?

Ví dụ không an toàn:

~~~java
return session.executeWrite(tx -> {
    tx.run("""
        CREATE (:Order {id: $id})
        """,
        Map.of("id", orderId)
    ).consume();

    emailClient.sendOrderConfirmation(customerEmail, orderId);

    return orderId;
});
~~~

Có hai vấn đề:

1. Email có thể đã gửi thành công nhưng transaction Neo4j sau đó rollback.
2. Nếu driver chạy lại callback, email có thể được gửi nhiều lần.

Tương tự, không nên gọi API thanh toán, gửi message, cập nhật cache dùng chung hoặc ghi file trực tiếp trong callback có thể được retry.

Ngay cả khi gọi external API sau khi transaction commit, ứng dụng vẫn có thể gặp trường hợp database commit thành công rồi process dừng trước khi gọi API. Vì vậy, chỉ di chuyển lệnh gọi ra sau commit chưa giải quyết được toàn bộ vấn đề giao nhận.

## 9. Transactional outbox để phát sự kiện sau commit

Transactional outbox lưu ý định phát sự kiện ngay trong cùng transaction với dữ liệu nghiệp vụ.

Trong ví dụ đặt hàng, transaction tạo:

- Order.
- Cập nhật tồn kho.
- ProcessedCommand ở trạng thái COMPLETED.
- OutboxEvent ở trạng thái PENDING.

Tất cả được commit hoặc rollback cùng nhau.

Một worker riêng đọc sự kiện chưa gửi:

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e.eventId AS eventId,
       e.type AS type,
       e.orderId AS orderId
ORDER BY e.createdAt
LIMIT $batchSize
~~~

Worker gửi message đến broker với eventId ổn định. Sau khi broker xác nhận nhận message, worker cập nhật trạng thái:

~~~cypher
MATCH (e:OutboxEvent {eventId: $eventId})
SET e.status = 'PUBLISHED',
    e.publishedAt = datetime()
RETURN e.eventId
~~~

Nếu worker gửi message thành công nhưng lỗi xảy ra trước khi cập nhật PUBLISHED, worker có thể gửi lại cùng event. Đây là cơ chế giao ít nhất một lần (at-least-once), không phải bảo đảm exactly-once.

Nếu có nhiều publisher worker, hai worker có thể cùng đọc một event đang PENDING. Hãy thiết kế cơ chế claim/lease hoặc phân vùng công việc để giảm gửi trùng. Dù có cơ chế claim, vẫn phải chấp nhận khả năng gửi lại sau timeout hoặc process crash và giữ consumer idempotent.

Consumer cần deduplicate theo eventId. Ví dụ lưu event đã xử lý trong cùng transaction với thay đổi nghiệp vụ của consumer:

~~~cypher
MERGE (d:ConsumedEvent {eventId: $eventId})
ON CREATE SET d.status = 'PROCESSING',
              d.receivedAt = datetime()
RETURN d.status AS status
~~~

Tạo uniqueness constraint cho ConsumedEvent.eventId. Consumer chỉ thực hiện thay đổi nghiệp vụ nếu event chưa được xử lý; việc ghi dấu đã nhận và thay đổi domain phải nằm trong cùng transaction của consumer.

~~~cypher
CREATE CONSTRAINT consumed_event_id_unique IF NOT EXISTS
FOR (e:ConsumedEvent)
REQUIRE e.eventId IS UNIQUE
~~~

Luồng xử lý consumer có thể được tổ chức như sau:

1. MERGE ConsumedEvent theo eventId và đọc trạng thái.
2. Nếu trạng thái đã PROCESSED, kết thúc mà không áp dụng lại thay đổi.
3. Nếu event mới, cập nhật dữ liệu domain trong transaction.
4. Đặt trạng thái event thành PROCESSED trong chính transaction đó.

Nếu transaction consumer rollback, cả dấu vết xử lý và thay đổi domain rollback. Nếu transaction đã commit nhưng acknowledgement gửi về broker bị mất, lần giao lại tìm thấy PROCESSED và không thực hiện lại nghiệp vụ.

Nếu xử lý event có nhiều bước hoặc gọi một hệ thống ngoài khác, consumer cũng cần idempotency key ở hệ thống đích hoặc một outbox tiếp theo.

### Vì sao không chỉ dùng AFTER_COMMIT event listener?

Spring cung cấp TransactionalEventListener với phase AFTER_COMMIT để chạy listener sau khi transaction commit. Cách này ngăn listener gửi email hoặc message trước khi dữ liệu được commit.

Tuy nhiên, process có thể dừng sau commit nhưng trước khi listener hoàn tất. Nếu sự kiện chỉ nằm trong bộ nhớ, không có bản ghi bền vững để worker phục hồi. Outbox lưu sự kiện trong database nên có thể được đọc và gửi lại sau khi process khởi động lại.

## 10. Side effect nào được phép trong callback?

Một quy tắc thực tế là callback chỉ nên chứa thao tác cần nằm trong transaction database và logic tính toán thuần.

| Hoạt động | Có nên đặt trong callback có thể retry? | Lý do |
|---|---|---|
| Chạy Cypher trong transaction | Có | Được commit/rollback cùng transaction |
| Tính giá trị từ dữ liệu đã đọc | Có | An toàn nếu không sửa trạng thái bên ngoài |
| Tạo UUID ngẫu nhiên | Nên tạo trước callback nếu cần giữ ổn định | Retry có thể sinh ID khác |
| Đọc đồng hồ hệ thống | Nên lấy một timestamp ổn định trước callback nếu cùng một thời điểm có ý nghĩa | Retry có thể tạo thời gian khác |
| Gửi email | Không | Không rollback được, có thể gửi trùng |
| Gọi HTTP API | Không | Hệ thống ngoài không tham gia transaction Neo4j |
| Gửi message broker | Không | Có thể gửi trước rollback hoặc gửi trùng |
| Tăng biến static hoặc global | Không | Giá trị bị tăng lại khi callback chạy lại |
| Ghi file | Không | File không được transaction Neo4j quản lý |
| Ghi outbox node trong cùng transaction | Có | Ý định phát sự kiện commit cùng dữ liệu nghiệp vụ |

Không dùng biến mutable bên ngoài callback làm nguồn sự thật. Nếu callback cần dữ liệu như orderId, timestamp hoặc idempotency key, hãy tạo hoặc nhận chúng trước callback rồi truyền vào dưới dạng giá trị ổn định.

## 11. Các tình huống cần xử lý

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Driver retry transaction | Callback chạy nhiều lần | Thiết kế callback idempotent |
| Client gửi lại cùng request | Tạo order hoặc trừ tồn kho hai lần | Dùng idempotency key |
| Hai request cùng key đến đồng thời | Tạo command trùng | Unique constraint và transaction |
| Cùng key nhưng payload khác | Trả nhầm kết quả của request cũ | So sánh payload/fingerprint và trả conflict |
| Commit thành công nhưng response bị mất | Client tưởng thất bại rồi gửi lại | Trả kết quả cũ theo key |
| Email gửi trước rollback | Người nhận nhận email cho order không tồn tại | Dùng outbox |
| Worker gửi message rồi crash | Message có thể được gửi lại | Consumer deduplicate eventId |
| Worker crash trước khi gửi message | Sự kiện bị bỏ sót nếu không có outbox | Lưu outbox trong transaction |
| Retry sau thời gian dài | Key đã bị xóa, request bị xử lý lại | Giữ key theo chính sách retention phù hợp |

## 12. Kiểm thử idempotency và side effect

Không chỉ kiểm tra rằng một lần gọi thành công. Hãy kiểm tra việc gọi lặp và gọi đồng thời.

### Gọi cùng command hai lần

Giả sử stock ban đầu là 10 và command đặt 2 sản phẩm.

Sau khi gọi cùng idempotency key hai lần, trạng thái mong đợi:

| Dữ liệu | Kết quả |
|---|---:|
| Số node Order cho key đó | 1 |
| Số node ProcessedCommand cho key đó | 1 |
| Số OutboxEvent OrderCreated | 1 |
| Stock còn lại | 8 |
| Order ID trả về ở cả hai lần | Giống nhau |

### Gọi đồng thời cùng key

Tạo hai thread hoặc hai request cùng gửi một idempotency key và cùng payload. Sau khi cả hai hoàn tất:

- Chỉ có một command được ghi nhận.
- Chỉ có một order được tạo.
- Tồn kho chỉ bị trừ một lần.
- Cả hai request nhận cùng orderId hoặc cùng kết quả nghiệp vụ.

Unique constraint là phần bảo vệ ở database; kiểm tra bằng code trước khi ghi không đủ để chống race condition vì hai request có thể cùng vượt qua bước kiểm tra. Nếu một request nhận uniqueness conflict, service cần đọc lại command trong transaction mới để trả kết quả đã hoàn tất thay vì tạo một command khác.

### Gửi cùng key với payload khác

Gửi lần đầu với quantity bằng 2, lần sau dùng cùng key nhưng quantity bằng 3. Request thứ hai phải bị từ chối. Không trả lại order của payload cũ như thể yêu cầu mới đã được xử lý.

### Kiểm tra outbox và consumer

- Tạo Order và OutboxEvent trong cùng transaction.
- Buộc transaction rollback và xác nhận cả hai không tồn tại.
- Commit thành công và xác nhận event PENDING tồn tại.
- Giả lập worker gửi message thành công rồi thất bại trước khi đánh dấu PUBLISHED.
- Chạy lại worker và xác nhận consumer chỉ áp dụng thay đổi nghiệp vụ một lần.

Nếu có thể, bổ sung fault injection để mô phỏng lỗi transient và quan sát callback được gọi lại. Test nên xác nhận trạng thái cuối cùng của database, không chỉ số lần callback chạy.

## 13. Checklist trước khi thêm retry

Trước khi bật retry cho một thao tác SDN hoặc Neo4j Driver, hãy trả lời:

1. Command có một idempotency key ổn định không?
2. Database có uniqueness constraint bảo vệ key không?
3. Cùng key nhưng payload khác có bị từ chối không?
4. Các cập nhật tăng/giảm counter có được bảo vệ khỏi xử lý lặp không?
5. Mọi thay đổi graph cần đi cùng nhau có nằm trong cùng transaction không?
6. Callback có gọi email, HTTP API, broker hoặc ghi file không?
7. Timestamp và ID cần ổn định có được tạo bên ngoài callback không?
8. Outbox event có được ghi cùng transaction nghiệp vụ không?
9. Consumer có deduplicate theo eventId không?
10. Test có bao phủ request lặp, request đồng thời và trường hợp response bị mất không?

## Kết luận

Một transaction callback của Neo4j Java Driver có thể được chạy lại khi driver retry lỗi transient. Vì vậy, callback cần tạo cùng hiệu ứng nghiệp vụ khi chạy nhiều lần với cùng command. MERGE hữu ích cho thao tác có thể chạy lại, nhưng cần khóa ổn định và uniqueness constraint để bảo vệ trước request đồng thời.

Dùng idempotency key để nhận diện một yêu cầu, lưu kết quả đã xử lý và từ chối trường hợp tái sử dụng key với payload khác. Giữ email, HTTP API và message broker ngoài transaction callback. Khi cần phát sự kiện sau commit một cách bền vững, ghi outbox event cùng transaction nghiệp vụ và để consumer deduplicate theo eventId.

Trong Spring Data Neo4j, @Transactional quản lý transaction boundary; bản thân annotation không tự động retry method. Hãy xác định rõ retry đến từ Neo4j Driver managed transaction hay từ policy ở tầng ứng dụng, rồi kiểm thử cả đường chạy lặp và tác động phụ bên ngoài.

## Tài liệu tham khảo

- [Neo4j Java Driver Manual: Managed transactions and retry behavior](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver API: Session.executeWrite and executeRead](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Session.html)
- [Neo4j Cypher Manual: MERGE and constraints](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual: CREATE versus MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/create/)
- [Spring Data Neo4j API: Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
