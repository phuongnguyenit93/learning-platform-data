# Tránh tác dụng phụ, truy vấn lặp và phụ thuộc vòng trong callback

Spring Data R2DBC hỗ trợ entity callback để thực thi logic tại những thời điểm nhất định trong vòng đời chuyển đổi và lưu entity. Callback hữu ích cho các thao tác nhỏ, có tính nhất quán như chuẩn hóa dữ liệu, bổ sung metadata hoặc điều chỉnh giá trị trước khi ghi. Tuy nhiên, callback dễ trở thành nơi tập trung quá nhiều trách nhiệm: truy vấn repository khác, ghi thêm entity, gọi HTTP, gửi message hoặc gọi ngược lại chính repository đã kích hoạt nó.

Những hành vi đó có thể gây truy vấn lặp kiểu N+1, tạo vòng gọi đệ quy, phát sinh phụ thuộc bean khó quản lý và làm side effect xảy ra sai thời điểm so với transaction. Cách dùng an toàn là giữ callback ngắn, có thể dự đoán và tập trung vào entity hiện tại; đặt orchestration, truy vấn liên quan và side effect ở service/use case có ranh giới rõ ràng.

## 1. Entity callback nằm ở đâu trong vòng đời persistence?

Khi Spring Data R2DBC lưu hoặc đọc entity qua repository hay `R2dbcEntityTemplate`, framework thực hiện các bước chuyển đổi giữa object Java và dữ liệu relational. Entity callback cho phép ứng dụng tham gia vào một số điểm trong quá trình đó.

Các callback thường gặp gồm:

| Callback | Thời điểm khái quát | Mục đích phù hợp |
| --- | --- | --- |
| `BeforeConvertCallback<T>` | Trước khi entity được chuyển thành dữ liệu ghi | Chuẩn hóa hoặc bổ sung giá trị trên entity |
| `BeforeSaveCallback<T>` | Trước khi ghi dữ liệu đã được chuyển đổi | Điều chỉnh outbound row nếu thật sự cần |
| `AfterSaveCallback<T>` | Sau thao tác lưu entity | Quan sát kết quả lưu hoặc cập nhật metadata cục bộ |
| `AfterConvertCallback<T>` | Sau khi row được chuyển thành entity | Điều chỉnh entity sau mapping bằng dữ liệu đã có |

Tên callback và chữ ký cụ thể cần đối chiếu phiên bản Spring Data Relational đang dùng. Các callback reactive trả về publisher để framework phối hợp với pipeline; chúng không phải listener đồng bộ được phép chặn thread.

Luồng khái quát khi ghi:

~~~mermaid
flowchart TD
    A[Repository save / Template insert or update]
    B[BeforeConvertCallback]
    C[Convert entity to outbound row]
    D[BeforeSaveCallback]
    E[Execute SQL through R2DBC]
    F[AfterSaveCallback]
    G[Return saved entity publisher]
    A --> B --> C --> D --> E --> F --> G
~~~

Luồng đọc có bước chuyển row thành entity và callback sau mapping. Callback chỉ được gọi khi thao tác đi qua đường mapping entity tương ứng của Spring Data. SQL tự viết bằng `DatabaseClient` và mapping `Row` thủ công không tự động trở thành một entity lifecycle đầy đủ như thao tác repository/template.

## 2. Callback phù hợp với loại logic nào?

Callback nên xử lý logic nhỏ, cục bộ, không cần điều phối nhiều tài nguyên:

- Chuẩn hóa chuỗi trước khi lưu, ví dụ trim khoảng trắng.
- Tạo slug từ tên nếu quy tắc hoàn toàn xác định từ entity hiện tại.
- Bổ sung dấu thời gian hoặc metadata đơn giản.
- Áp dụng quy tắc chuyển đổi thuần túy trên entity.
- Điều chỉnh giá trị trong outbound row trước khi gửi xuống database.

Ví dụ chuẩn hóa email:

~~~java
import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.mapping.SqlIdentifier;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class NormalizeCustomerCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalizedEmail = customer.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        Customer normalized = new Customer(
                customer.id(),
                customer.name().trim(),
                normalizedEmail
        );

        return Mono.just(normalized);
    }
}
~~~

Callback chỉ đọc entity đầu vào, tạo entity đã chuẩn hóa và trả về publisher. Nó không truy vấn database, không gọi service khác và không phát side effect bên ngoài.

Với entity bất biến như record, phải trả về instance đã thay đổi. Không giả định Spring Data sẽ sửa trực tiếp object ban đầu.

## 3. Callback reactive không phải nơi để block

Các callback trong Spring Data R2DBC là reactive. Chữ ký nhận/trả publisher cho phép callback tham gia vào pipeline mà không cần chặn thread.

Không dùng:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    Customer existing = customerRepository
            .findById(customer.id())
            .block();

    return Mono.just(customer);
}
~~~

Đoạn code này có nhiều vấn đề:

- `block()` chặn thread trong một luồng reactive.
- Callback biến một phép biến đổi nhỏ thành truy vấn database.
- Mỗi lần save có thể phát sinh thêm một query.
- Nếu callback được kích hoạt từ chính đường persistence mà truy vấn sử dụng, có thể tạo vòng gọi lại.
- Lỗi truy vấn bị ném đồng bộ thay vì được phối hợp tự nhiên trong reactive pipeline.

Nếu một tác vụ thực sự cần dữ liệu từ repository khác, hãy chuyển nó ra service trước khi gọi save:

~~~java
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return tenantRepository.findById(command.tenantId())
            .switchIfEmpty(Mono.error(
                    new TenantNotFoundException(command.tenantId())
            ))
            .flatMap(tenant -> {
                Customer customer = new Customer(
                        null,
                        tenant.id(),
                        command.name(),
                        command.email()
                );
                return customerRepository.save(customer);
            });
}
~~~

Service thể hiện rõ truy vấn cần thiết và thứ tự nghiệp vụ. Callback của Customer có thể tiếp tục chỉ chuẩn hóa dữ liệu của chính Customer.

## 4. Truy vấn trong callback có thể tạo N+1

Giả sử một callback sau khi đọc Order truy vấn Customer để bổ sung tên khách hàng:

~~~java
@Component
public class EnrichOrderCallback
        implements AfterConvertCallback<Order> {

    private final CustomerRepository customerRepository;

    public EnrichOrderCallback(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            Row row,
            RowMetadata metadata) {

        return customerRepository.findById(order.customerId())
                .map(customer -> order.withCustomerName(customer.name()));
    }
}
~~~

Đây là một ví dụ không nên dùng cho danh sách lớn. Khi truy vấn 100 Order, callback có thể tạo thêm 100 truy vấn Customer:

~~~text
SELECT orders ...                 -- 1 truy vấn
  callback Order 1 -> SELECT customer WHERE id = ?
  callback Order 2 -> SELECT customer WHERE id = ?
  callback Order 3 -> SELECT customer WHERE id = ?
  ...
  callback Order 100 -> SELECT customer WHERE id = ?
~~~

Đó là vấn đề N+1: một truy vấn lấy tập chính và thêm một truy vấn cho mỗi entity. Reactive không loại bỏ chi phí round trip hoặc tải lên database; nó chỉ thay đổi cách biểu diễn và tiêu thụ bất đồng bộ.

Callback cũng có thể bị gọi khi entity được đọc trong nhiều use case khác nhau. Một query tưởng như đơn giản có thể bất ngờ kéo theo nhiều query khác và làm độ trễ khó dự đoán.

## 5. Dùng JOIN hoặc truy vấn theo lô thay cho N+1

Nếu màn hình cần Order cùng tên Customer, hãy tạo read model bằng một truy vấn JOIN:

~~~java
public record OrderSummary(
        Long orderId,
        Long customerId,
        String customerName,
        String status
) {}

public Flux<OrderSummary> findOrderSummaries() {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   c.id AS customer_id,
                   c.name AS customer_name,
                   o.status
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            ORDER BY o.id
            """)
            .map((row, metadata) -> new OrderSummary(
                    row.get("order_id", Long.class),
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("status", String.class)
            ))
            .all();
}
~~~

Truy vấn này trả dữ liệu cần thiết trong một lượt đọc. Nó không cần callback truy vấn Customer cho từng Order.

Nếu không thể dùng JOIN, có thể tải tập Customer theo lô:

~~~java
public Mono<List<OrderSummary>> findSummaries() {
    return orderRepository.findAll()
            .collectList()
            .flatMap(orders -> {
                Set<Long> customerIds = orders.stream()
                        .map(Order::customerId)
                        .collect(Collectors.toSet());

                return customerRepository.findAllById(customerIds)
                        .collectMap(Customer::id)
                        .map(customers -> orders.stream()
                                .map(order -> toSummary(
                                        order,
                                        customers.get(order.customerId())
                                ))
                                .toList()
                        );
            });
}
~~~

Ví dụ batch này giảm số query Customer xuống một query theo tập ID, nhưng `collectList()` giữ toàn bộ Order trong bộ nhớ. Với dữ liệu lớn, hãy phân trang Order rồi tải Customer theo ID của từng trang. Có thể dùng `R2dbcEntityTemplate` hoặc `DatabaseClient` để thực hiện JOIN trực tiếp.

## 6. Callback gọi lại repository có thể tạo đệ quy

Một lỗi nguy hiểm hơn N+1 là callback gọi lại chính đường persistence đã kích hoạt callback:

~~~java
@Component
public class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    private final CustomerRepository repository;

    public CustomerAfterConvertCallback(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Customer> onAfterConvert(
            Customer customer,
            Row row,
            RowMetadata metadata) {

        return repository.findById(customer.id());
    }
}
~~~

Luồng gọi có thể trở thành:

1. `findById` đọc Customer.
2. Spring Data chuyển row thành Customer.
3. `AfterConvertCallback` chạy.
4. Callback gọi `findById` lần nữa.
5. Truy vấn lồng nhau đọc Customer và kích hoạt cùng callback.
6. Vòng lặp tiếp tục cho đến khi cạn tài nguyên hoặc phát lỗi.

Không gọi repository để đọc lại cùng entity trong callback sau mapping. Callback nhận entity đã được đọc; nếu cần xác minh hoặc tải dữ liệu khác, thực hiện trong service hoặc query chuyên biệt bên ngoài callback.

## 7. Phụ thuộc vòng giữa callback, service và repository

Callback là một Spring bean. Nếu callback inject service, service lại dùng repository, và thao tác repository kích hoạt callback, ứng dụng có thể có chu trình phụ thuộc về mặt thực thi:

~~~mermaid
flowchart LR
    A[Repository save/read] --> B[Entity callback]
    B --> C[Domain service]
    C --> A
~~~

Tùy cấu hình, chu trình có thể còn tạo phụ thuộc bean ở thời điểm khởi tạo:

~~~text
CustomerRepository / mapping infrastructure
        -> CustomerCallback
        -> CustomerService
        -> CustomerRepository
~~~

Ngay cả khi Spring khởi tạo được các bean, callback có thể gọi lại service/repository và kích hoạt cùng chuỗi lần nữa. Dùng `@Lazy` hoặc setter injection chỉ trì hoãn việc giải quyết dependency; nó không sửa được vòng gọi logic.

Thiết kế nên tách trách nhiệm:

- Repository chỉ thực hiện truy vấn và persistence.
- Callback chỉ biến đổi entity hoặc outbound row hiện tại.
- Service/use case điều phối nhiều repository và quy tắc nghiệp vụ.
- Thành phần phát event/side effect chạy ở ranh giới thích hợp sau khi dữ liệu đã được commit.

Nếu một callback cần gọi service để quyết định cách lưu, nhiều khả năng logic đó thuộc service trước khi gọi repository.

## 8. Không ghi thêm entity từ callback lưu

Một callback trước hoặc sau khi lưu Order mà lại gọi `orderRepository.save(...)` có thể tự kích hoạt callback đó lần nữa:

~~~java
@Component
public class OrderSaveCallback
        implements AfterSaveCallback<Order> {

    private final OrderRepository repository;

    public OrderSaveCallback(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Order> onAfterSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        return repository.save(order.withProcessed(true));
    }
}
~~~

Đây là vòng lặp persistence: save Order gọi AfterSaveCallback; callback save Order lần nữa; lần save thứ hai tiếp tục gọi callback. Kể cả khi có điều kiện thoát, luồng vẫn khó hiểu và có thể ghi dữ liệu nhiều lần.

Nếu nghiệp vụ cần lưu thêm một bản ghi liên quan, đặt thao tác đó trong service và transaction rõ ràng:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderAuditRepository.save(toAudit(order))
                            .thenReturn(order)
            );
}
~~~

Service thể hiện rõ có hai thao tác ghi và có thể kiểm soát transaction, lỗi, retry cũng như thứ tự thực thi.

## 9. Không gọi dịch vụ bên ngoài từ callback persistence

Một `AfterSaveCallback` có thể bị cám dỗ dùng để gửi email, gọi HTTP hoặc publish message:

~~~java
@Component
public class NotifyAfterSaveCallback
        implements AfterSaveCallback<Order> {

    private final NotificationClient notificationClient;

    @Override
    public Publisher<Order> onAfterSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        return notificationClient.sendOrderCreated(order)
                .thenReturn(order);
    }
}
~~~

Không nên gắn side effect bên ngoài vào callback lưu vì:

- Callback có thể chạy trước khi transaction bên ngoài commit.
- Notification có thể đã được gửi nhưng transaction database sau đó rollback.
- Retry transaction có thể gọi callback nhiều lần và gửi trùng.
- Timeout/cancellation có thể khiến ứng dụng không biết hệ thống ngoài đã nhận request hay chưa.
- Lỗi notification có thể làm publisher save thất bại dù dữ liệu database đã được ghi trong transaction chưa commit.

Callback không phải ranh giới đáng tin cậy để bảo đảm side effect xảy ra đúng một lần sau commit.

## 10. Dùng transactional outbox cho side effect

Nếu cần phát sự kiện sau khi lưu Order, hãy lưu bản ghi outbox trong cùng transaction với dữ liệu nghiệp vụ:

~~~sql
CREATE TABLE outbox_event (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

Service:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    outboxRepository.save(toOutboxEvent(order))
                            .thenReturn(order)
            );
}
~~~

Order và outbox event cùng commit hoặc rollback. Một tiến trình riêng đọc các event chưa publish, gửi đến broker hoặc dịch vụ ngoài, rồi đánh dấu đã xử lý. Consumer nên idempotent vì việc gửi và xác nhận có thể bị lặp khi worker crash giữa hai bước.

Outbox không tự bảo đảm exactly-once delivery. Nó tạo nền tảng để đạt at-least-once delivery với xử lý idempotent và tránh mất event khi transaction nghiệp vụ commit.

## 11. Phân biệt callback với domain service và lifecycle event

Không phải mọi logic xảy ra quanh lúc save đều nên đặt trong callback:

| Loại logic | Nơi phù hợp |
| --- | --- |
| Chuẩn hóa thuộc tính của entity hiện tại | Entity method hoặc `BeforeConvertCallback` |
| Bổ sung audit metadata đơn giản | Spring Data auditing hoặc callback phù hợp |
| Kiểm tra quy tắc cần truy vấn nhiều aggregate | Application/domain service trước khi save |
| Ghi nhiều entity trong một use case | Service trong reactive transaction |
| Tạo read model từ nhiều bảng | JOIN bằng `DatabaseClient` hoặc truy vấn chuyên biệt |
| Gửi email, HTTP hoặc message | Outbox/dispatcher hoặc cơ chế after-commit phù hợp |
| Ghi log/metric vòng đời | Callback nhẹ hoặc observability layer |

Lifecycle event và entity callback cũng có mục đích khác nhau. Callback là hook có thể thay đổi entity/row và tham gia pipeline persistence. Event thường thông báo rằng một sự kiện đã xảy ra; listener không nên được xem là cơ chế transaction nguyên tử với hệ thống ngoài nếu không có thiết kế bổ sung.

## 12. Tránh truy vấn lặp khi đọc danh sách entity

Nếu cần thêm dữ liệu liên quan vào response, hãy xác định rõ query shape trước:

1. Dữ liệu nào cần hiển thị?
2. Có thể lấy bằng JOIN không?
3. Có thể tải theo tập ID một lần cho mỗi trang không?
4. Có thể tạo projection/DTO trực tiếp từ SQL không?
5. Kết quả có cần phân trang hoặc giới hạn không?

Ví dụ không nên:

~~~java
return orderRepository.findAll()
        .flatMap(order ->
                customerRepository.findById(order.customerId())
                        .map(customer -> toSummary(order, customer))
        );
~~~

Với N Order, pipeline có thể thực hiện một truy vấn Order và N truy vấn Customer. Dùng `flatMap` làm các truy vấn bất đồng bộ, nhưng không làm giảm số lượng query.

Giải pháp JOIN:

~~~sql
SELECT o.id, o.status, c.id AS customer_id, c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

Nếu dùng truy vấn theo lô, giới hạn tập Order trước rồi lấy Customer bằng `findAllById(ids)`. Đừng thu thập một bảng không giới hạn vào bộ nhớ chỉ để tránh N+1.

## 13. Callback nên idempotent và không phụ thuộc số lần gọi

Callback có thể được gọi lại khi:

- Một thao tác persistence được retry.
- Service gọi save nhiều lần.
- Một luồng import xử lý lại bản ghi.
- Transaction được thực hiện lại sau deadlock/serialization conflict.
- Entity được đọc ở nhiều query khác nhau.

Vì vậy, callback không nên giả định “mỗi entity chỉ đi qua callback đúng một lần trong toàn bộ vòng đời”. Hãy viết logic sao cho cùng đầu vào tạo cùng kết quả và không tạo side effect lặp.

Ví dụ chuẩn hóa chuỗi là idempotent:

~~~java
String normalized = email.trim().toLowerCase(Locale.ROOT);
~~~

Áp dụng nhiều lần vẫn cho cùng kết quả.

Ngược lại, logic như:

~~~java
entity.setAttemptCount(entity.getAttemptCount() + 1);
~~~

có thể tăng bộ đếm mỗi lần callback chạy, kể cả khi transaction cuối cùng rollback hoặc được retry. Nếu đây là số lần xử lý nghiệp vụ, hãy cập nhật nó tại service/use case bằng một thao tác có ngữ nghĩa rõ ràng.

## 14. Callback và dữ liệu cần thiết từ database

Nếu callback thực sự cần một giá trị được database tạo ra, hãy xác định giá trị đó có thể được tạo bằng cơ chế database hoặc Spring Data mà không cần query lồng:

- Dùng identity/sequence cho ID tự sinh.
- Dùng default expression cho giá trị mặc định ở database.
- Dùng auditing infrastructure cho created/modified metadata.
- Dùng converter cho chuyển đổi kiểu dữ liệu.
- Dùng projection hoặc JOIN cho dữ liệu đọc tổng hợp.

Không truy vấn lại entity ngay sau khi save chỉ để lấy ID được sinh nếu publisher save đã trả về entity chứa ID. Hãy dùng giá trị được phát ra:

~~~java
return customerRepository.save(customer)
        .flatMap(saved ->
                auditRepository.save(toAudit(saved.id()))
                        .thenReturn(saved)
        );
~~~

Điều này tránh một lượt SELECT không cần thiết và giữ logic orchestration ở service.

## 15. Thứ tự callback và phụ thuộc giữa các callback

Ứng dụng có thể đăng ký nhiều callback cùng kiểu hoặc các callback ở những giai đoạn khác nhau. Nếu thứ tự xử lý quan trọng, hãy cấu hình thứ tự bằng cơ chế ordering mà phiên bản Spring Data/Spring hỗ trợ, chẳng hạn `Ordered` hoặc `@Order` khi phù hợp.

Không nên tạo chuỗi callback mà callback A phụ thuộc vào việc callback B đã ghi database hoặc gọi service. Thứ tự đó khó quan sát và có thể tạo phụ thuộc vòng.

Nếu hai phép biến đổi cần chạy theo một thứ tự nghiệp vụ bắt buộc, cân nhắc gộp chúng thành một component rõ ràng hoặc thực hiện trong service trước khi gọi repository. Callback nên là bước chuyển đổi đơn giản, không phải workflow engine.

## 16. Xử lý lỗi trong callback

Vì callback trả publisher, lỗi có thể được phát bất đồng bộ:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        return Mono.error(new InvalidCustomerException(
                "Email is required"
        ));
    }

    return Mono.just(customer);
}
~~~

Validation cục bộ đơn giản có thể được thực hiện ở callback, nhưng validation nghiệp vụ cần nhiều aggregate hoặc truy vấn database nên nằm trong service. Nếu callback phát lỗi, thao tác persistence tương ứng sẽ thất bại và transaction bên ngoài có thể rollback theo cấu hình.

Không bắt mọi exception rồi trả lại entity:

~~~java
// Không nên che giấu mọi lỗi trong callback.
return someTransformation()
        .onErrorResume(error -> Mono.just(customer));
~~~

Cách này có thể khiến dữ liệu không đạt quy tắc nhưng vẫn được ghi. Nếu có lỗi có thể phục hồi, hãy phân loại cụ thể và quyết định ở tầng nghiệp vụ.

## 17. Callback và reactive transaction

Callback được thực thi trong pipeline persistence mà nó tham gia. Nếu thao tác repository nằm trong reactive transaction, callback cũng là một phần của quá trình đó. Tuy nhiên, việc callback thực hiện truy vấn lồng hoặc gọi hệ thống ngoài không tự động làm các side effect đó trở thành một đơn vị nguyên tử đúng nghĩa.

Ví dụ, callback gửi HTTP rồi publisher save phát lỗi sau đó:

- HTTP request có thể đã được hệ thống ngoài xử lý.
- Transaction database có thể rollback.
- Retry có thể gửi HTTP request lần nữa.

Transaction R2DBC chỉ quản lý resource database mà transaction manager sở hữu. Nó không rollback email, HTTP hoặc message broker.

Giữ callback cục bộ giúp transaction ngắn và có hành vi dễ dự đoán. Những thao tác database bổ sung nên được nối tường minh trong service transaction; side effect bên ngoài nên dùng outbox hoặc cơ chế sau commit có khả năng phục hồi.

## 18. Kiểm thử callback

Kiểm thử callback nên xác nhận phép biến đổi cục bộ:

~~~java
@Test
void normalizesEmailBeforeConvert() {
    NormalizeCustomerCallback callback =
            new NormalizeCustomerCallback();

    Customer input = new Customer(
            null,
            "  An Nguyen  ",
            "  AN@EXAMPLE.COM "
    );

    Customer result = Mono.from(
            callback.onBeforeConvert(
                    input,
                    SqlIdentifier.unquoted("customer")
            )
    ).block();

    assertEquals("An Nguyen", result.name());
    assertEquals("an@example.com", result.email());
}
~~~

Đây là unit test cho logic biến đổi thuần túy; việc dùng `block()` trong test đồng bộ là có chủ đích và không nên chuyển cách đó vào callback/service production.

Integration test cần xác nhận callback thực sự được gọi trên đường repository/template và giá trị đã biến đổi được lưu/đọc đúng. Đồng thời, kiểm tra:

- Callback không tạo query phụ ngoài dự kiến.
- Callback không tự gọi save gây đệ quy.
- Nhiều entity trong một query không tạo N+1.
- Lỗi callback làm publisher persistence thất bại đúng cách.
- Retry không làm lặp side effect.
- Callback không tạo vòng phụ thuộc bean.

Nếu cần kiểm tra số query, có thể dùng logging/metrics hoặc quan sát statement ở test integration phù hợp với driver. Không chỉ dựa vào mock callback để kết luận không có truy vấn lặp ở runtime.

## 19. Các lỗi thường gặp

1. **Truy vấn repository bên trong callback cho từng entity.** Có thể tạo N+1 và tăng độ trễ.
2. **Gọi lại chính repository trong AfterConvertCallback.** Có thể kích hoạt callback lần nữa và tạo đệ quy.
3. **Gọi save từ AfterSaveCallback.** Có thể lặp vô hạn chuỗi save/callback.
4. **Inject service vào callback trong khi service gọi lại repository đó.** Tạo phụ thuộc vòng ở thời gian chạy hoặc lúc khởi tạo bean.
5. **Dùng @Lazy để che vòng phụ thuộc.** Chỉ trì hoãn lỗi, không sửa chu trình logic.
6. **Dùng block() trong callback reactive.** Chặn thread và làm mất lợi ích reactive.
7. **Gửi email hoặc HTTP từ callback.** Side effect có thể xảy ra trước commit và bị lặp khi retry.
8. **Giả định callback chỉ chạy một lần.** Retry hoặc nhiều thao tác persistence có thể gọi lại callback.
9. **Tăng counter hoặc tạo ID ngẫu nhiên ở callback mà không cân nhắc retry.** Có thể làm thay đổi dữ liệu qua mỗi attempt.
10. **Dùng callback để điều phối nhiều aggregate.** Logic đó thuộc application/domain service.
11. **Thu thập toàn bộ entity rồi truy vấn từng quan hệ.** Có thể tạo N+1 hoặc dùng quá nhiều bộ nhớ.
12. **Phụ thuộc vào thứ tự callback ngầm định.** Cấu hình ordering rõ ràng hoặc chuyển workflow sang service.

## Quy tắc lựa chọn nhanh

- Dùng callback cho phép biến đổi nhỏ, cục bộ và có tính idempotent trên entity/row hiện tại.
- Dùng `BeforeConvertCallback` cho chuẩn hóa entity trước khi chuyển đổi.
- Dùng `BeforeSaveCallback` khi thật sự cần điều chỉnh dữ liệu đã chuyển thành outbound row.
- Không gọi `block()`, `subscribe()` hoặc repository lồng bên trong callback.
- Không truy vấn từng entity liên quan trong callback; dùng JOIN hoặc truy vấn theo lô.
- Không save entity từ callback save; điều phối nhiều lần ghi trong service và transaction.
- Không gọi HTTP, gửi email hoặc publish message từ callback persistence; dùng transactional outbox hoặc cơ chế sau commit phù hợp.
- Tránh callback inject service mà service lại gọi repository kích hoạt callback.
- Thiết kế callback idempotent vì persistence có thể được retry hoặc thực hiện nhiều lần.
- Kiểm thử cả phép biến đổi callback và số query/transaction trên database thực tế.

Entity callback là hook hữu ích trong vòng đời mapping của Spring Data R2DBC, nhưng nó nên giữ phạm vi nhỏ và dễ dự đoán. Khi callback truy vấn repository, ghi thêm entity hoặc gọi hệ thống ngoài, nó có thể tạo N+1, đệ quy, phụ thuộc vòng và side effect xảy ra trước commit hoặc lặp khi retry. Hãy dùng callback cho phép biến đổi cục bộ; để service điều phối truy vấn và nhiều thao tác database; dùng JOIN hoặc batch query cho dữ liệu liên quan; và dùng transactional outbox cho side effect cần phát sau commit. Cách phân chia này giúp callback không trở thành một workflow ẩn bên trong quá trình persistence.
