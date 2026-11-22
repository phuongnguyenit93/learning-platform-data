# Giới hạn của REST event khi repository được gọi từ luồng ngoài HTTP

## Mục tiêu

Spring Data REST cung cấp repository event như `beforeCreate`, `beforeSave`, `beforeDelete` và các event thay đổi association. Đây là các điểm móc thuận tiện để áp dụng xử lý gắn với vòng đời resource được thao tác qua endpoint do Spring Data REST quản lý.

Nhưng các REST event không phải cơ chế vòng đời chung cho mọi lần gọi repository. Khi service, scheduled job, message listener, batch process hoặc một controller tùy chỉnh gọi trực tiếp `repository.save(...)`, luồng đó không đi qua request handler của Spring Data REST và không nên dựa vào `@HandleBeforeSave` hay `@HandleBeforeCreate` để bảo vệ nghiệp vụ.

## REST event được gọi trong trường hợp nào?

Spring Data REST phát các event khi request đi qua các endpoint repository REST và framework thực hiện thao tác tương ứng. Một số event thường dùng:

| Event | Thời điểm trong luồng REST |
| --- | --- |
| `BeforeCreateEvent` / `AfterCreateEvent` | Trước / sau khi tạo resource mới qua collection endpoint |
| `BeforeSaveEvent` / `AfterSaveEvent` | Trước / sau khi lưu resource đã tồn tại |
| `BeforeDeleteEvent` / `AfterDeleteEvent` | Trước / sau khi xóa resource qua REST |
| `BeforeLinkSaveEvent` / `AfterLinkSaveEvent` | Trước / sau khi thêm hoặc thay association |
| `BeforeLinkDeleteEvent` / `AfterLinkDeleteEvent` | Trước / sau khi gỡ association |

Ví dụ handler xử lý trước khi một `Order` được lưu qua Spring Data REST:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderRestEventHandler {

        @HandleBeforeSave
        public void beforeSave(Order order) {
            if (order.getStatus() == OrderStatus.CANCELLED
                    && order.hasBeenShipped()) {
                throw new IllegalStateException(
                    "A shipped order cannot be cancelled.");
            }
        }
    }

Handler trên được gọi khi thao tác lưu đi qua vòng đời repository REST phù hợp. Nó không tự động chạy chỉ vì một bean khác gọi `orderRepository.save(order)`.

## Điều gì xảy ra khi gọi repository từ service?

Giả sử service cập nhật đơn hàng trực tiếp:

    @Service
    public class OrderService {
        private final OrderRepository orderRepository;

        public OrderService(OrderRepository orderRepository) {
            this.orderRepository = orderRepository;
        }

        @Transactional
        public void cancelOrder(Long id) {
            Order order = orderRepository.findById(id)
                    .orElseThrow();
            order.setStatus(OrderStatus.CANCELLED);
            orderRepository.save(order);
        }
    }

Khi `cancelOrder` được gọi từ controller tùy chỉnh, scheduled job hoặc message listener, lời gọi repository không đi qua Spring Data REST. Vì vậy `OrderRestEventHandler.beforeSave` không phải nơi đáng tin cậy để thực thi quy tắc cấm hủy đơn đã giao.

Điều này cũng áp dụng cho các luồng như:

- Scheduled task gọi repository để cập nhật dữ liệu theo lịch.
- Consumer nhận message từ Kafka hoặc RabbitMQ rồi lưu entity.
- Batch job import hoặc đồng bộ dữ liệu.
- Service được gọi từ một REST controller tự viết.
- Test gọi trực tiếp service hoặc repository thay vì gửi HTTP request đến endpoint Spring Data REST.

Đừng suy luận rằng một thao tác có HTTP ở bên ngoài thì REST event chắc chắn được phát. Chỉ request được xử lý qua luồng endpoint của Spring Data REST mới đi qua các hook vòng đời của Spring Data REST.

## Đặt quy tắc nghiệp vụ ở domain hoặc service layer

Nếu một quy tắc phải đúng cho mọi cách cập nhật dữ liệu, hãy đặt nó ở nơi mọi luồng đều phải đi qua: domain method hoặc service nghiệp vụ. REST event có thể gọi lại cùng logic đó để tích hợp với endpoint tự động.

Ví dụ chuyển quy tắc vào domain object:

    @Entity
    public class Order {
        @Enumerated(EnumType.STRING)
        private OrderStatus status;

        private boolean shipped;

        public void cancel() {
            if (shipped || status == OrderStatus.SHIPPED) {
                throw new IllegalStateException(
                    "A shipped order cannot be cancelled.");
            }
            this.status = OrderStatus.CANCELLED;
        }
    }

Service gọi domain method trong transaction:

    @Transactional
    public void cancelOrder(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow();
        order.cancel();
    }

Với REST endpoint tự động, có thể dùng event handler để gọi cùng domain method hoặc chuyển thao tác sang service nghiệp vụ qua custom controller. Không duy trì hai bản sao của cùng một quy tắc ở REST handler và service, vì chúng có thể lệch nhau theo thời gian.

Domain method phù hợp với bất biến gắn với chính entity. Service phù hợp với quy tắc cần phối hợp nhiều repository, kiểm tra quyền, truy cập dữ liệu liên quan hoặc điều phối nhiều thao tác trong cùng transaction.

## Phân biệt REST event với các cơ chế event khác

Các cơ chế dưới đây có phạm vi khác nhau; không thay thế lẫn nhau:

### Spring Data REST repository events

- Được phát trong vòng đời request do Spring Data REST xử lý.
- Có thể dùng `@RepositoryEventHandler` cùng `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete` hoặc các link handler.
- Phù hợp với xử lý đặc thù của REST representation và endpoint.
- Không phải hook bao phủ mọi lời gọi trực tiếp đến repository.

### Spring Data domain events

Aggregate root có thể công bố domain event bằng `@DomainEvents`; Spring Data repository phát các event này khi các phương thức repository được hỗ trợ, chẳng hạn `save` hoặc `delete`, được gọi trên aggregate.

    public class Order {
        private final List<Object> domainEvents = new ArrayList<>();

        public void cancel() {
            // kiểm tra bất biến và đổi trạng thái
            domainEvents.add(new OrderCancelledEvent(/* order id */));
        }

        @DomainEvents
        Collection<Object> domainEvents() {
            return domainEvents;
        }

        @AfterDomainEventPublication
        void clearDomainEvents() {
            domainEvents.clear();
        }
    }

Domain event mô tả điều đã xảy ra trong nghiệp vụ, ví dụ `OrderCancelledEvent`. Nó khác REST event ở chỗ mục tiêu là truyền đạt sự kiện domain cho các thành phần khác. Cơ chế này vẫn phụ thuộc vào việc thao tác đi qua các phương thức repository có hỗ trợ phát domain event; thao tác trực tiếp bằng `EntityManager` hoặc SQL không mặc nhiên kích hoạt nó.

Không dùng domain event để thay thế validation trước khi lưu. Bất biến cần được kiểm tra đồng bộ trong domain/service method; event thường dùng để thông báo cho phần còn lại của hệ thống.

### JPA lifecycle callbacks

JPA có callback như `@PrePersist`, `@PreUpdate`, `@PostPersist` và `@PostUpdate`. Callback được gọi bởi persistence provider khi entity trải qua vòng đời tương ứng, bất kể thay đổi bắt đầu từ HTTP hay từ service.

    @Entity
    public class Customer {
        @PrePersist
        @PreUpdate
        void normalizeEmail() {
            if (email != null) {
                email = email.trim().toLowerCase(Locale.ROOT);
            }
        }
    }

Lifecycle callback phù hợp với thao tác cục bộ trên entity, chẳng hạn chuẩn hóa giá trị hoặc đặt trường nội bộ. Tránh dùng callback để gọi repository khác, thực hiện network I/O, kiểm tra quyền hoặc điều phối transaction; các hành động đó khó kiểm soát và có thể tạo phụ thuộc vòng đời persistence.

### Auditing và database constraints

Spring Data auditing như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` có thể áp dụng trong các luồng persistence đã bật auditing, không phụ thuộc request phải đi qua Spring Data REST. Cần cấu hình `@EnableJpaAuditing` hoặc auditing phù hợp với module đang dùng và cung cấp auditor khi cần.

Database constraints như `NOT NULL`, `UNIQUE`, foreign key và check constraint là lớp bảo vệ cuối cùng cho tính toàn vẹn dữ liệu. Chúng vẫn được áp dụng khi ghi từ REST, service, batch hoặc SQL trực tiếp.

## Xử lý công việc sau khi transaction commit

Nếu cần gửi email, phát message ra broker hoặc gọi hệ thống ngoài sau khi lưu thành công, tránh thực hiện side effect trước khi transaction commit. Nếu transaction rollback sau khi gửi message, hệ thống bên ngoài có thể nhận một sự kiện cho thay đổi chưa được lưu.

Có thể dùng `@TransactionalEventListener` để xử lý sau commit:

    @Component
    public class OrderNotificationListener {

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderCancelled(OrderCancelledEvent event) {
            // gửi thông báo sau khi transaction đã commit
        }
    }

Service hoặc domain layer phát `OrderCancelledEvent` trong transaction. Listener chỉ xử lý khi transaction commit thành công. Nếu cần độ tin cậy cao khi gửi message ra hệ thống khác, cân nhắc transactional outbox thay vì chỉ dựa vào listener trong bộ nhớ.

`@TransactionalEventListener` không tự biến mọi event thành sự kiện sau commit; cần phát event trong transaction đang hoạt động và chọn đúng phase. Với event cần xử lý cả khi không có transaction, cấu hình fallback execution có chủ đích và hiểu rõ khác biệt về tính nhất quán.

## Cách kết hợp các cơ chế

Với một quy tắc nghiệp vụ quan trọng, có thể phân chia trách nhiệm như sau:

1. Domain method kiểm tra bất biến và thay đổi trạng thái hợp lệ.
2. Service `@Transactional` tải entity, gọi domain method, phối hợp các repository và lưu thay đổi.
3. Spring Data REST event chỉ xử lý tích hợp riêng cho endpoint REST; nếu cần, chuyển tiếp vào cùng service/domain logic.
4. Domain event thông báo điều đã xảy ra để các thành phần khác phản ứng.
5. `@TransactionalEventListener(AFTER_COMMIT)` thực hiện side effect sau khi dữ liệu đã commit.
6. JPA callback xử lý thao tác cục bộ ở vòng đời entity; auditing và database constraint bảo vệ metadata và tính toàn vẹn.

Không đặt cùng một logic nghiệp vụ ở nhiều lớp event. Xác định rõ mỗi cơ chế chịu trách nhiệm gì để tránh xử lý lặp, phụ thuộc vào thứ tự event hoặc bỏ sót luồng gọi.

## Kiểm tra các luồng gọi khác nhau

Viết test riêng cho từng đường đi vì một HTTP test không chứng minh service hoặc batch path được bảo vệ:

- **Spring Data REST HTTP test:** gửi POST, PUT/PATCH, DELETE hoặc request association đến endpoint REST; xác nhận REST handler được gọi đúng event.
- **Service test:** gọi trực tiếp service; xác nhận domain invariant vẫn chặn trạng thái không hợp lệ dù không có REST event.
- **Repository/domain event test:** gọi phương thức repository hỗ trợ `@DomainEvents`; xác nhận domain event được phát đúng một lần và được dọn theo vòng đời aggregate.
- **Persistence test:** lưu entity qua JPA; xác nhận callback, auditing và database constraint hoạt động.
- **Transaction test:** buộc transaction rollback; xác nhận listener `AFTER_COMMIT` không chạy và không có side effect ngoài transaction.
- **Batch/message test:** chạy đúng entry point của job hoặc consumer để xác nhận nó gọi service/domain logic dùng chung.

Đừng chỉ assert rằng method REST handler đã chạy. Hãy kiểm tra kết quả cuối cùng trong database, event được phát, trạng thái rollback và việc side effect chỉ xảy ra sau commit.

## Quy trình áp dụng

1. Liệt kê mọi entry point có thể ghi entity: Spring Data REST, custom controller, service, job, consumer và batch.
2. Đưa bất biến nghiệp vụ vào domain method hoặc service dùng chung.
3. Giữ `@RepositoryEventHandler` cho xử lý đặc thù của Spring Data REST.
4. Dùng `@DomainEvents` để công bố sự kiện nghiệp vụ từ aggregate khi thao tác qua repository hỗ trợ cơ chế này.
5. Dùng JPA callback cho xử lý cục bộ và auditing cho thông tin tạo/sửa.
6. Giữ database constraint để bảo vệ dữ liệu trước mọi đường ghi.
7. Dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox cho side effect cần xảy ra sau commit.
8. Kiểm tra độc lập từng luồng HTTP và ngoài HTTP.

Spring Data REST events chỉ nên được xem là hook của vòng đời REST. Nếu một quy tắc phải đúng khi repository được gọi từ bất kỳ nơi nào, hãy đặt quy tắc ở domain/service layer và dùng REST event như lớp tích hợp mỏng cho endpoint tự động.