# Thay thế giả định ORM bằng truy vấn và ranh giới ghi tường minh

Spring Data Relational R2DBC làm việc với mô hình dữ liệu quan hệ và API reactive, nhưng không cung cấp đầy đủ cơ chế unit-of-work như một ORM truyền thống. Khi chuyển từ JPA/Hibernate sang R2DBC, những giả định như persistence context, dirty checking, lazy loading, entity proxy và cascade theo object graph không còn là nền tảng để thiết kế ứng dụng.

Thay vào đó, ứng dụng cần thể hiện rõ dữ liệu nào được đọc, truy vấn nào tải các quan hệ cần thiết, thao tác nào ghi thay đổi và transaction bao quanh use case nào. Repository, R2dbcEntityTemplate hoặc DatabaseClient thực hiện truy vấn; application service điều phối các bước; aggregate root xác định ranh giới dữ liệu cần được bảo vệ cùng nhau; database constraints bảo vệ tính toàn vẹn cuối cùng.

Cách tiếp cận này không có nghĩa phải viết SQL cho mọi thao tác. Spring Data R2DBC vẫn cung cấp repository, derived query, mapping metadata, entity callbacks và các abstraction như Criteria. Điều quan trọng là không dựa vào những hành vi ORM mà Spring Data Relational không hứa hẹn.

Bài học này trình bày cách thay thế các giả định ORM bằng truy vấn và ranh giới ghi tường minh, từ thiết kế aggregate, đọc dữ liệu bằng projection/join, xử lý N+1, cập nhật có chủ đích, quản lý transaction reactive, concurrency và kiểm thử.

## 1. Khác biệt giữa ORM unit-of-work và Spring Data Relational

Trong ORM như JPA/Hibernate, một persistence context có thể theo dõi entity đã load. Khi field thay đổi, dirty checking phát hiện khác biệt và ORM tạo UPDATE khi flush. Quan hệ có thể được tải lazy qua proxy; cascade có thể truyền thao tác từ root sang object graph theo mapping.

Spring Data Relational R2DBC có mô hình khác. Repository thao tác với entity thông qua các lệnh persistence cụ thể. Việc thay đổi một object Java không tự động tạo UPDATE. Quan hệ cần được tải bằng query rõ ràng. Ranh giới aggregate ảnh hưởng đến cách Spring Data lưu dữ liệu liên quan.

| Giả định từ ORM | Cách tiếp cận với Spring Data R2DBC |
| --- | --- |
| Entity được quản lý trong persistence context. | Entity thường là object dữ liệu; không có session theo dõi thay đổi như JPA. |
| Dirty checking tự phát hiện field đã đổi. | Gọi repository/template hoặc câu UPDATE tường minh. |
| Lazy loading tự truy vấn khi truy cập relation. | Tải dữ liệu liên quan bằng query/repository rõ ràng. |
| Entity graph được điều hướng qua proxy. | Dùng join, projection hoặc nhiều query có chủ đích. |
| Cascade tự truyền persist/remove qua object graph. | Xác định aggregate boundary, lệnh ghi và foreign key rõ ràng. |
| Flush đồng bộ thay đổi trong persistence context. | Publisher reactive thực thi thao tác khi được subscribe; không có flush của session ORM. |
| Một object đã load luôn là bản mới nhất trong session. | Mỗi query có thể đọc trạng thái mới; dùng transaction/locking khi cần nhất quán. |

Spring Data Relational vẫn có mapping metadata, repository abstraction và entity callbacks. Khác biệt nằm ở mô hình quản lý trạng thái và cách các thao tác ghi được thực hiện.

## 2. Tư duy theo aggregate và ranh giới dữ liệu

Aggregate là nhóm object được quản lý như một đơn vị nhất quán trong domain. Aggregate root là điểm vào để thay đổi nhóm dữ liệu đó. Trong Spring Data Relational, thiết kế aggregate giúp xác định object nào được lưu cùng root và object nào chỉ được tham chiếu bằng ID.

Ví dụ một đơn hàng gồm:

- Order: aggregate root.
- OrderLine: dòng hàng thuộc đơn hàng.
- Product: aggregate khác, được tham chiếu qua productId.
- Customer: aggregate khác, được tham chiếu qua customerId.

Sơ đồ:

~~~mermaid
flowchart TD
    O[Order aggregate root] --> L1[OrderLine 1]
    O --> L2[OrderLine 2]
    O --> L3[OrderLine 3]
    L1 --> P1[productId reference]
    L2 --> P2[productId reference]
    L3 --> P3[productId reference]
    O --> C[customerId reference]
~~~

OrderLine thuộc vòng đời của Order. Product và Customer có vòng đời riêng. Không cần tải toàn bộ Product object chỉ để lưu một order line; lưu productId thường đủ nếu use case chỉ cần tham chiếu.

### Aggregate root không phải object graph tùy ý

Không đưa mọi quan hệ database vào một object graph khổng lồ rồi mong repository tự tải và đồng bộ tất cả. Aggregate nên có kích thước phù hợp với quy tắc nhất quán nghiệp vụ.

Ví dụ, thay đổi quantity của một OrderLine có thể thuộc transaction cập nhật Order. Thay đổi tên Product thường là use case riêng và không nên buộc phải load hoặc save mọi Order có chứa Product đó.

### Dùng ID cho tham chiếu giữa aggregate

Ví dụ:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    UUID customerId,
    String status,
    BigDecimal total
) {}
~~~

Order giữ customerId. Khi cần hiển thị tên khách hàng, use case đọc có thể query CustomerRepository hoặc dùng join projection. Không cần giả định có một proxy Customer được lazy load khi gọi order.customer().

## 3. Mapping aggregate với Spring Data Relational

Spring Data Relational hỗ trợ mapping các object thuộc aggregate. Ví dụ Order có danh sách OrderLine:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    UUID customerId,
    String status,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}

public record OrderLine(
    UUID productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

Trong ví dụ này, Order là root; OrderLine được lưu trong bảng có cột order_id trỏ về root và line_no làm key/index nếu schema được thiết kế tương ứng.

Schema minh họa:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(14, 2) NOT NULL
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Tên cột, key column và mapping phải khớp schema thực tế. Hãy kiểm tra SQL được tạo cho insert và update trên phiên bản Spring Data Relational đang dùng.

### Hiểu semantics khi lưu aggregate

Khi lưu một aggregate có collection phụ thuộc, Spring Data Relational cần đồng bộ các row thuộc aggregate theo mapping. Với collection được map bằng @MappedCollection, cập nhật root có thể kéo theo thao tác thay thế hoặc đồng bộ các row phụ thuộc; implementation cụ thể có thể xóa rồi chèn lại các row liên quan thay vì theo dõi từng child như dirty checking của ORM.

Điều này có một số hệ quả:

- Không coi việc thay một phần tử trong List là một lệnh UPDATE độc lập.
- Cần xem xét số lượng child trong aggregate.
- Cần hiểu tác động của save root lên các row phụ thuộc.
- Không dùng collection khổng lồ như một aggregate duy nhất.
- Kiểm thử SQL và hiệu năng khi collection lớn hoặc update thường xuyên.

Nếu cần cập nhật một dòng cụ thể với concurrency cao, một lệnh UPDATE tường minh trên bảng order_lines có thể phù hợp hơn việc lưu lại toàn bộ aggregate. Khi làm vậy, phải duy trì invariant của Order và transaction boundary một cách rõ ràng.

## 4. Không có dirty checking: phải ghi thay đổi tường minh

Trong JPA, một entity đang được quản lý có thể được sửa field rồi ORM tự phát hiện khi flush. Với Spring Data R2DBC, thay đổi object trong bộ nhớ không tự ghi xuống database.

Ví dụ:

~~~java
return productRepository.findById(id)
    .doOnNext(product -> {
        // Thay đổi object trong bộ nhớ không tự tạo UPDATE.
        product.setName("New name");
    });
~~~

Đoạn code trên chỉ phát entity đã đọc. Nó không lưu thay đổi. Với record immutable, không thể sửa field trực tiếp; phải tạo object mới và gọi save hoặc lệnh update tương ứng.

Cách rõ ràng với mutable entity:

~~~java
return productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
    .flatMap(product -> {
        product.setName(command.name());
        return productRepository.save(product);
    });
~~~

Với immutable record:

~~~java
return productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
    .flatMap(current -> {
        ProductEntity updated = new ProductEntity(
            current.id(),
            command.name(),
            current.price(),
            current.status(),
            current.version()
        );
        return productRepository.save(updated);
    });
~~~

Việc gọi save là ranh giới ghi rõ ràng. Không có thay đổi nào được lưu chỉ vì object đã được load hoặc nằm trong biến local.

### Khi nào dùng save và khi nào dùng UPDATE tường minh?

Dùng repository.save khi cần lưu entity/aggregate theo mapping chuẩn của Spring Data. Dùng câu UPDATE tường minh khi:

- Chỉ cần thay đổi một vài cột.
- Muốn tránh load entity trước khi update.
- Cần thao tác nguyên tử ở database.
- Cần kiểm soát điều kiện WHERE và số hàng bị ảnh hưởng.
- Đang xử lý dữ liệu lớn hoặc update hàng loạt.

Câu UPDATE tường minh phải có điều kiện đủ chặt, đặc biệt là ID, tenant và version nếu cần optimistic concurrency.

## 5. Tạo và lưu aggregate bằng một use case

Một use case tạo order có thể cần kiểm tra customer, xác minh product, tính tổng tiền rồi lưu order cùng lines. Application service điều phối tất cả bước đó.

Ví dụ:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return customerRepository.findById(command.customerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(command.customerId())
        ))
        .flatMap(customer ->
            validateAndPriceLines(command.lines())
                .map(lines -> orderFactory.create(customer, lines))
        )
        .flatMap(orderRepository::save);
}
~~~

Đây là skeleton minh họa. Nếu validateAndPriceLines truy vấn nhiều product, cần chọn cách truy vấn phù hợp và bảo đảm các bước ghi nằm trong transaction cần thiết.

Không gọi subscribe bên trong service:

~~~java
orderRepository.save(order).subscribe();
return Mono.just(order);
~~~

Cách này tách thao tác ghi khỏi publisher của use case, khiến caller không đợi kết quả và lỗi không được truyền về đúng luồng. Hãy trả publisher hoàn chỉnh để WebFlux hoặc caller quản lý subscription.

## 6. Đọc dữ liệu quan hệ bằng query tường minh

Không có lazy loading tự động. Nếu endpoint cần order cùng customer name và product name, hãy quyết định rõ dữ liệu cần đọc và xây dựng query phù hợp.

Có ba cách thường gặp:

1. Nhiều query theo từng repository, kết hợp reactive.
2. Một câu SQL JOIN và map sang projection.
3. Query root trước, sau đó tải child/reference theo nhóm ID.

Chọn dựa trên kích thước kết quả, số round trip, transaction consistency và độ phức tạp SQL.

### Nhiều query có chủ đích

Ví dụ lấy order rồi lấy customer:

~~~java
public Mono<OrderDetails> getOrder(UUID orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> new OrderDetails(
                    order.id(),
                    order.status(),
                    customer.name()
                ))
        );
}
~~~

Cách này dễ đọc và tận dụng repository riêng. Nhưng nếu list endpoint trả 100 order rồi mỗi order lại gọi customerRepository.findById, ứng dụng có thể tạo N+1 query.

## 7. Tránh N+1 bằng join hoặc batch fetch

N+1 xảy ra khi ứng dụng chạy một query lấy N bản ghi rồi chạy thêm một query cho từng bản ghi để lấy dữ liệu liên quan.

Ví dụ không hiệu quả:

~~~java
return orderRepository.findRecentOrders()
    .flatMap(order ->
        customerRepository.findById(order.customerId())
            .map(customer -> toSummary(order, customer))
    );
~~~

Nếu có 100 orders, đường này có thể thực thi 1 query orders và tới 100 query customer. flatMap có thể chạy một số query đồng thời nhưng không làm giảm số lượng query.

### Cách 1: JOIN và projection

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

Projection:

~~~java
public record OrderSummary(
    UUID orderId,
    String orderStatus,
    UUID customerId,
    String customerName
) {}
~~~

Có thể thực hiện qua DatabaseClient và map từng row:

~~~java
return databaseClient.sql("""
    SELECT
        o.id AS order_id,
        o.status AS order_status,
        c.id AS customer_id,
        c.name AS customer_name
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.status = :status
    ORDER BY o.id
    """)
    .bind("status", status)
    .map((row, metadata) -> new OrderSummary(
        row.get("order_id", UUID.class),
        row.get("order_status", String.class),
        row.get("customer_id", UUID.class),
        row.get("customer_name", String.class)
    ))
    .all();
~~~

JOIN giúp database lấy dữ liệu liên quan trong một query và trả đúng shape cho use case. Không cần hydrate toàn bộ entity graph nếu API chỉ cần summary.

### Cách 2: Batch fetch theo tập ID

Nếu cần giữ repository riêng và quan hệ là nhiều customer:

1. Lấy danh sách orders.
2. Thu thập các customerId khác nhau.
3. Query customers bằng một điều kiện IN.
4. Tạo Map customerId → Customer.
5. Ghép kết quả trong memory.

Ví dụ khái quát:

~~~java
return orderRepository.findRecentOrders()
    .collectList()
    .flatMapMany(orders -> {
        List<UUID> customerIds = orders.stream()
            .map(Order::customerId)
            .distinct()
            .toList();

        return customerRepository.findAllById(customerIds)
            .collectMap(Customer::id)
            .flatMapMany(customers ->
                Flux.fromIterable(orders)
                    .map(order -> toSummary(
                        order,
                        customers.get(order.customerId())
                    ))
            );
    });
~~~

Cách này giảm số query từ N+1 xuống một query orders và một query customers, nhưng ví dụ collectList giữ toàn bộ orders trong memory. Với kết quả lớn, phải phân trang hoặc xử lý theo chunk.

### Chọn JOIN hay batch fetch

- JOIN phù hợp khi dữ liệu cần trả có quan hệ rõ và query có thể được tối ưu bằng index.
- Batch fetch phù hợp khi cần giữ repository boundaries hoặc dữ liệu được lấy từ nhiều query khác nhau.
- Với dữ liệu lớn, phân trang root trước rồi batch fetch child cho từng trang.
- Tránh một JOIN một-nhiều không kiểm soát làm nhân số hàng và phá semantics pagination.

## 8. Projection thay cho tải toàn bộ entity

Một use case chỉ cần vài field không nhất thiết phải tải entity đầy đủ. Projection giúp giảm dữ liệu truyền từ database và làm rõ hợp đồng đọc.

Ví dụ danh sách order chỉ cần ID, status và total:

~~~java
public record OrderListItem(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Custom query:

~~~java
@Query("""
    SELECT id, status, total
    FROM orders
    WHERE customer_id = :customerId
    ORDER BY id DESC
    """)
Flux<OrderListItem> findOrderList(UUID customerId);
~~~

Cách map projection qua repository phụ thuộc dạng projection và phiên bản Spring Data. Nếu query có alias hoặc phép tính phức tạp, DatabaseClient cho phép ánh xạ tường minh.

Projection không phải entity được quản lý và không nên được dùng làm đối tượng save nếu nó không biểu diễn đầy đủ mô hình persistence.

### Read model riêng cho màn hình

Một màn hình có thể cần dữ liệu tổng hợp từ nhiều bảng. Tạo read DTO hoặc projection riêng thường rõ ràng hơn việc tải một aggregate rồi gọi nhiều getter quan hệ.

Read model có thể được tối ưu theo query của use case. Write model vẫn giữ aggregate boundary để bảo vệ invariant khi thay đổi dữ liệu.

## 9. Tải quan hệ nhiều-nhiều một cách tường minh

Giả sử Product và Tag có quan hệ nhiều-nhiều qua product_tags. Không nên giả định truy cập product.tags tự kích hoạt query lazy.

Có thể dùng JOIN:

~~~sql
SELECT
    p.id AS product_id,
    p.name AS product_name,
    t.id AS tag_id,
    t.name AS tag_name
FROM products p
LEFT JOIN product_tags pt ON pt.product_id = p.id
LEFT JOIN tags t ON t.id = pt.tag_id
WHERE p.id = :productId
ORDER BY t.name;
~~~

JOIN trả một row cho mỗi tag; nếu product không có tag, LEFT JOIN vẫn trả row với các cột tag null. Mapper cần gom các row thành một DTO có danh sách tags.

Với danh sách nhiều product, nên nhóm row theo productId hoặc dùng hai query: lấy product page, sau đó lấy tất cả tags theo danh sách product IDs. Không query tags riêng cho từng product.

## 10. Cập nhật một phần bằng câu UPDATE tường minh

Nếu chỉ thay status, không nhất thiết phải đọc toàn bộ entity rồi save:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(UUID id, String status);
~~~

Service:

~~~java
public Mono<Void> changeStatus(UUID id, String status) {
    return orderRepository.updateStatus(id, status)
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new OrderNotFoundException(id));
            }
            return Mono.empty();
        });
}
~~~

Ví dụ giả định repository method trả số hàng bị ảnh hưởng dưới dạng Mono<Integer>. Kiểu return được hỗ trợ phụ thuộc Spring Data R2DBC version và cách khai báo modifying query. Kiểm tra API của phiên bản dự án.

Lệnh update trực tiếp có các đặc điểm:

- Không cần hydrate toàn bộ entity.
- Không tự động chạy entity lifecycle theo cùng đường save.
- Không tự động áp dụng mọi logic trong mapper/service.
- Cần tự cập nhật audit fields nếu không có cơ chế tương ứng.
- Cần kiểm tra rowsUpdated để phát hiện ID không tồn tại.
- Cần thêm điều kiện version/tenant nếu nghiệp vụ yêu cầu.

Không coi UPDATE tường minh là thay thế toàn bộ domain logic. Application service vẫn cần kiểm tra trạng thái hợp lệ và quyền thực hiện.

## 11. Cập nhật có điều kiện và optimistic locking

Nếu hai request cùng cập nhật một order, thao tác sau có thể ghi đè thay đổi trước. Có thể dùng version field để phát hiện xung đột.

Entity:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    String status,
    BigDecimal total,
    @Version Long version
) {}
~~~

Spring Data Relational hỗ trợ optimistic locking qua @Version trong các thao tác save được hỗ trợ. Khi phiên bản đã lưu khác với version của entity, thao tác có thể phát sinh OptimisticLockingFailureException.

Với SQL UPDATE tường minh, phải đưa version vào điều kiện và tăng version:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu rowsUpdated bằng 0, có thể do bản ghi không tồn tại hoặc version đã thay đổi. Tùy API, có thể cần query bổ sung để phân biệt not found và conflict. Không trả thành công nếu không có hàng nào được cập nhật.

### Kiểm tra trạng thái chuyển đổi

Một số trạng thái chỉ cho phép chuyển theo graph nghiệp vụ. Ví dụ PAID không được quay lại DRAFT. Đừng chỉ kiểm tra request status hợp lệ theo enum; phải kiểm tra chuyển đổi từ trạng thái hiện tại.

Có thể đưa điều kiện trạng thái vào UPDATE:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND status = :expectedStatus
  AND version = :expectedVersion;
~~~

Câu lệnh này giúp điều kiện cạnh tranh được kiểm tra nguyên tử tại database. Service cần diễn giải rowsUpdated = 0 thành conflict hoặc not found theo hợp đồng API.

## 12. Xóa dữ liệu và foreign key

Không giả định gọi delete root sẽ tự xóa mọi object liên quan như cascade remove của JPA. Hành vi phụ thuộc mapping aggregate và schema database.

Với quan hệ được sở hữu trong aggregate, Spring Data Relational có semantics lưu aggregate riêng. Với quan hệ giữa các aggregate, cần xác định hành vi xóa rõ ràng và thiết kế foreign key:

- ON DELETE RESTRICT/NO ACTION để ngăn xóa khi còn tham chiếu.
- ON DELETE CASCADE nếu database được phép tự xóa row phụ thuộc theo quy tắc domain.
- Xóa phụ thuộc bằng các lệnh rõ ràng trong cùng transaction nếu cần.
- Soft delete nếu cần giữ lịch sử hoặc audit.

Ví dụ xóa order và lines bằng lệnh rõ ràng:

~~~java
public Mono<Void> deleteOrder(UUID orderId) {
    return transaction.transactional(
        orderLineRepository.deleteByOrderId(orderId)
            .then(orderRepository.deleteById(orderId))
    );
}
~~~

Đoạn code giả định các repository method được triển khai và cùng dùng một R2DBC ConnectionFactory/transaction manager. Nếu foreign key dùng ON DELETE CASCADE, có thể không cần lệnh xóa child riêng. Hãy chọn một chủ sở hữu rõ ràng cho quy tắc xóa.

Không xóa Product chỉ vì một OrderLine đang tham chiếu tới productId. Product là aggregate khác và có vòng đời riêng.

## 13. Transaction boundary theo use case

Transaction nên bao quanh một use case cần tính nguyên tử, không nên bao quanh một object graph lớn chỉ vì ORM trước đây dùng session dài.

Ví dụ chuyển order sang PAID cần:

1. Cập nhật order status.
2. Ghi payment record.
3. Ghi audit/event record trong cùng database nếu cần.
4. Commit tất cả hoặc rollback tất cả.

Có thể dùng @Transactional trên service trả về reactive type:

~~~java
@Service
public class PaymentService {

    @Transactional
    public Mono<Void> markPaid(UUID orderId, Payment payment) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> validateCanPay(order, payment))
            .flatMap(order -> orderRepository.save(order.markPaid()))
            .then(paymentRepository.save(payment))
            .then();
    }
}
~~~

Với reactive transaction, transaction context được truyền qua Reactor Context và publisher. Method phải trả publisher để Spring quản lý transaction. Nếu method gọi subscribe riêng, thao tác đó có thể nằm ngoài transaction.

### TransactionalOperator

Có thể điều khiển transaction rõ hơn trong reactive chain:

~~~java
public Mono<Void> markPaid(UUID orderId, Payment payment) {
    Mono<Void> work = orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> validateCanPay(order, payment))
        .flatMap(order -> orderRepository.save(order.markPaid()))
        .then(paymentRepository.save(payment))
        .then();

    return transactionalOperator.transactional(work);
}
~~~

TransactionalOperator hữu ích khi transaction boundary là một phần của composition hoặc cần chọn rõ publisher nào thuộc transaction.

### Chỉ một transaction manager cho đúng connection factory

R2dbcTransactionManager quản lý transaction qua ConnectionFactory tương ứng. Nếu ứng dụng có nhiều database/ConnectionFactory, cần transaction manager phù hợp cho từng resource. Một reactive transaction không tự tạo distributed transaction xuyên nhiều database.

## 14. Không dùng transaction dài thay cho thiết kế aggregate

Không nên mở transaction khi bắt đầu một request rồi giữ nó trong lúc:

- Gọi HTTP service bên ngoài.
- Chờ người dùng xác nhận.
- Xử lý file lớn.
- Gửi email hoặc webhook.
- Chạy một tác vụ import kéo dài.

Transaction dài giữ connection và có thể giữ lock, làm tăng contention. Hãy thực hiện các bước không cần transaction trước hoặc sau ranh giới transaction, rồi mở transaction ngắn cho phần cập nhật database cần atomic.

Nếu cần phát message sau commit, transactional outbox thường phù hợp hơn việc gửi message trực tiếp trong transaction. Ghi outbox record cùng transaction với thay đổi domain; worker đọc outbox sau commit và phát message theo cơ chế retry/idempotency.

## 15. Read consistency và nhiều query

Một use case đọc bằng nhiều query có thể nhìn thấy trạng thái database khác nhau nếu có transaction khác cập nhật giữa các query.

Ví dụ:

1. Query Order.
2. Query Customer.
3. Query OrderLines.

Nếu các query chạy ngoài transaction, kết quả có thể không cùng một snapshot. Tùy database và isolation level, transaction có thể cung cấp read consistency tốt hơn.

Không phải mọi endpoint đều cần transaction read. Với dữ liệu dashboard chấp nhận eventual consistency, nhiều query độc lập có thể phù hợp. Với báo cáo tài chính hoặc quyết định nghiệp vụ cần snapshot nhất quán, hãy chọn transaction/isolation hoặc một query join phù hợp.

### JOIN có thể giúp consistency và giảm round trip

Một query join thường quan sát dữ liệu trong một statement snapshot theo semantics database, đồng thời giảm số lần trao đổi. Tuy nhiên, join một-nhiều có thể nhân bản row và làm pagination phức tạp.

Chọn giữa một query join và nhiều query theo yêu cầu nhất quán, kích thước dữ liệu và query plan.

## 16. Pagination khi đọc aggregate và quan hệ

Không phân trang trực tiếp trên kết quả JOIN một-nhiều nếu mục tiêu là phân trang aggregate root. Một order có 10 lines tạo 10 rows join; LIMIT 20 có thể chỉ bao phủ hai order thay vì 20 order.

Một cách làm:

1. Query page các order IDs theo sort ổn định.
2. Query order details cho danh sách IDs đó.
3. Query lines cho tất cả order IDs trong page.
4. Nhóm lines theo orderId và dựng response DTO.

Ví dụ khái quát:

~~~java
return orderRepository.findPageIds(pageable)
    .collectList()
    .flatMapMany(orderIds ->
        orderRepository.findAllById(orderIds)
            .collectList()
            .flatMapMany(orders ->
                lineRepository.findByOrderIdIn(orderIds)
                    .collectMultimap(OrderLine::orderId)
                    .flatMapMany(linesByOrder ->
                        Flux.fromIterable(orders)
                            .map(order -> toDetails(
                                order,
                                linesByOrder.getOrDefault(
                                    order.id(),
                                    List.of()
                                )
                            ))
                    )
            )
    );
~~~

Đây là ví dụ minh họa; kiểu collection và method repository cần khớp model thực tế. Với trang rất lớn, giữ dữ liệu trong memory cần được giới hạn. Query IDs phải có ORDER BY ổn định và query detail nên giữ đúng thứ tự trang nếu response yêu cầu.

## 17. Ghi dữ liệu lớn và bulk operation

Nếu use case cập nhật hàng nghìn row, không nhất thiết load tất cả entity rồi save từng cái. Có thể dùng UPDATE theo điều kiện, batch statement hoặc SQL nhiều hàng tùy semantics.

Ví dụ cập nhật trạng thái theo nhóm:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE status = :oldStatus
  AND created_at < :cutoff;
~~~

Lệnh này thực hiện thay đổi trực tiếp trên database. Nó không gọi domain method cho từng order, không chạy logic validation trên từng entity và không tự áp dụng entity callbacks như đường save thông thường.

Trước khi dùng bulk update, xác định:

- Invariant nào phải được kiểm tra?
- Có cần cập nhật version?
- Có cần audit từng row?
- Có trigger hoặc database constraint bảo vệ dữ liệu?
- Có cần trả về các ID đã thay đổi?
- Nếu một số row không thỏa điều kiện thì semantics ra sao?
- Transaction có cần nguyên tử toàn bộ không?

Bulk operation phù hợp khi điều kiện và tác động có thể biểu diễn chính xác bằng SQL và database constraints. Nếu mỗi entity có quy tắc domain riêng, xử lý theo nhóm có giới hạn và transaction phù hợp hơn.

## 18. Tách read model và write model khi cần

Một số use case đọc cần JOIN nhiều bảng, aggregate dữ liệu và tính toán; use case ghi lại cần bảo vệ invariant của một aggregate. Không bắt buộc cùng một object model phải phục vụ cả hai.

Có thể dùng:

- Entity/aggregate cho thao tác ghi.
- Projection hoặc DTO cho truy vấn đọc.
- Repository/DatabaseClient query riêng cho từng read use case.
- Application service điều phối lệnh ghi.

Đây là cách áp dụng một phần tư duy CQRS mà không nhất thiết triển khai event sourcing hoặc hệ thống phức tạp.

Ví dụ:

~~~java
public record OrderDetailsView(
    UUID orderId,
    String status,
    String customerName,
    BigDecimal total,
    List<OrderLineView> lines
) {}
~~~

Read query có thể join orders, customers và order_lines rồi map thành view. Lệnh thay đổi status vẫn đi qua Order aggregate/service để kiểm tra transition và version.

Không tạo một DTO đọc rồi gọi repository.save(dto) như thể đó là entity. Read model và write model có trách nhiệm khác nhau.

## 19. Database constraints là hàng rào cuối cùng

Validation trong service giúp trả lỗi nghiệp vụ dễ hiểu, nhưng không thay thế constraint. Các request đồng thời có thể cùng vượt qua bước kiểm tra trước khi ghi.

Dùng database constraints cho invariant có thể diễn đạt ở schema:

- PRIMARY KEY cho identity.
- UNIQUE cho business key duy nhất.
- FOREIGN KEY cho tham chiếu.
- NOT NULL cho field bắt buộc.
- CHECK cho điều kiện trên một row.
- Index phù hợp cho truy vấn và uniqueness.

Ví dụ:

~~~sql
CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Application service vẫn nên kiểm tra sớm để trả lỗi có ý nghĩa. Khi database constraint phát lỗi do race condition hoặc dữ liệu không hợp lệ, chuyển exception cụ thể thành domain/API error.

## 20. Kiểm thử ranh giới đọc và ghi

Repository test nên xác nhận query và mapping. Service test nên xác nhận orchestration và transaction semantics. Integration test trên database thật cần kiểm tra constraint, concurrency và SQL đặc thù.

### Test không có dirty checking

Một test có thể chứng minh rằng load và thay đổi object nhưng không save thì database không đổi:

~~~java
StepVerifier.create(
    productRepository.findById(id)
        .doOnNext(product -> product.setName("Changed in memory"))
        .then(productRepository.findById(id))
)
.assertNext(reloaded ->
    assertEquals("Original", reloaded.getName())
)
.verifyComplete();
~~~

Ví dụ giả định ProductEntity mutable và query thứ hai chạy sau khi object đầu tiên được đọc. Nếu entity là record, có thể tạo bản sao trong memory nhưng không gọi save; kết quả đọc lại vẫn là giá trị cũ.

### Test explicit update

Kiểm tra số hàng bị ảnh hưởng:

~~~java
StepVerifier.create(orderRepository.updateStatus(id, "PAID"))
    .expectNext(1)
    .verifyComplete();
~~~

Sau đó đọc lại để xác nhận trạng thái. Đồng thời test ID không tồn tại trả 0 và service chuyển thành not found theo hợp đồng.

### Test optimistic concurrency

- Đọc entity với version v.
- Cập nhật bằng version v.
- Thử cập nhật lại bằng version cũ.
- Xác nhận thao tác thứ hai conflict hoặc không cập nhật row.
- Đọc lại để xác nhận trạng thái cuối.

### Test transaction rollback

Tạo use case ghi nhiều bảng, ép một bước sau phát lỗi rồi xác nhận các thao tác trước rollback khi nằm trong cùng transaction. Dùng TransactionalOperator hoặc @Transactional với reactive publisher thực sự được subscribe trong transaction context.

Không chỉ test bằng mock vì mock không chứng minh ConnectionFactory, transaction manager và database cùng tham gia một transaction.

## 21. Các lỗi thường gặp khi chuyển từ ORM sang R2DBC

| Triệu chứng | Giả định cũ | Cách thiết kế lại |
| --- | --- | --- |
| Sửa object nhưng DB không đổi | Mong dirty checking tự flush. | Gọi save hoặc UPDATE tường minh. |
| Truy cập relation nhưng không có dữ liệu | Mong lazy loading. | Query relation rõ ràng. |
| List endpoint chậm | N+1 qua từng entity. | JOIN projection hoặc batch fetch. |
| Save root làm nhiều SQL ngoài dự kiến | Chưa hiểu aggregate mapping. | Kiểm tra semantics collection và ranh giới aggregate. |
| Xóa root để lại row phụ thuộc hoặc lỗi FK | Mong cascade ORM. | Thiết kế FK và delete behavior rõ ràng. |
| Dữ liệu ghi đè nhau | Không kiểm soát concurrency. | @Version hoặc conditional UPDATE. |
| Transaction không bao hết các thao tác | Gọi subscribe/block tách publisher. | Trả publisher và dùng reactive transaction. |
| Một service gọi nhiều query nhưng dữ liệu không cùng snapshot | Giả định persistence context giữ trạng thái. | Chọn transaction/isolation hoặc query join. |
| Bulk update bỏ qua audit/domain logic | Mong callback và lifecycle chạy cho từng entity. | Thực hiện metadata và invariant rõ ràng. |
| Entity graph quá lớn | Dùng object graph như ORM. | Giới hạn aggregate và dùng ID reference. |
| Pagination trả thiếu root | LIMIT áp dụng lên rows của JOIN một-nhiều. | Phân trang root IDs rồi tải relation. |
| Update không phát hiện bản ghi không tồn tại | Không kiểm tra rowsUpdated. | Kiểm tra số hàng bị ảnh hưởng. |

## 22. Quy trình thiết kế persistence tường minh

Khi chuyển một use case từ ORM sang Spring Data Relational R2DBC, hãy làm theo trình tự:

1. **Xác định aggregate root:** object nào sở hữu invariant và vòng đời của các row phụ thuộc?
2. **Phân biệt aggregate và reference:** object nào thuộc aggregate; object nào chỉ cần ID?
3. **Thiết kế query đọc:** endpoint cần entity đầy đủ, projection, join hay nhiều query?
4. **Tránh N+1:** batch fetch hoặc join theo use case; không query từng relation trong loop.
5. **Thiết kế lệnh ghi:** save aggregate, UPDATE tường minh hay bulk operation?
6. **Xác định field được phép đổi:** tránh ghi đè field server quản lý hoặc dữ liệu ngoài tenant.
7. **Đặt transaction boundary:** bao quanh các thao tác database cần atomic cho use case.
8. **Xử lý concurrency:** @Version hoặc điều kiện version/state trong UPDATE.
9. **Giữ integrity ở database:** FK, unique, check và index.
10. **Xác định behavior ngoài persistence:** auditing, callbacks, outbox và side effect.
11. **Kiểm thử SQL thật:** repository, mapping, query plan, transaction và constraint.
12. **Đo hiệu năng:** số query, round trip, connection usage và kích thước aggregate.

Spring Data Relational R2DBC khuyến khích persistence được thể hiện qua query và lệnh ghi rõ ràng. Không có dirty checking hay lazy loading để tự xử lý thay đổi và quan hệ như một ORM unit-of-work. Aggregate boundary xác định dữ liệu nào được lưu cùng nhau; repository, template và SQL xác định chính xác dữ liệu được đọc/ghi; application service xác định transaction cho use case; database constraint và optimistic locking bảo vệ tính toàn vẹn khi có concurrency. Khi thiết kế theo các ranh giới này, hành vi persistence trở nên dễ dự đoán, dễ đo lường và phù hợp với mô hình reactive.
