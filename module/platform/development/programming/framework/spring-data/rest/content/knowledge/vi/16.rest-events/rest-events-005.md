# BeforeDeleteEvent và AfterDeleteEvent khi xóa tài nguyên trong Spring Data REST

## Mục tiêu

Spring Data REST phát các repository events trong quá trình xử lý REST request. Khi client xóa một item resource, hai event quan trọng là:

- **BeforeDeleteEvent**: phát trước khi entity được xóa khỏi repository.
- **AfterDeleteEvent**: phát sau khi thao tác xóa entity khỏi repository hoàn tất.

Hai event cho phép ứng dụng bổ sung logic quanh thao tác DELETE, ví dụ kiểm tra điều kiện xóa, ghi nhận audit, làm mới cache hoặc phát thông báo cho một thành phần khác.

Cần phân biệt ba mốc thời gian: trước khi gọi thao tác xóa, sau khi repository thực hiện thao tác xóa, và sau khi transaction database commit. Tên AfterDeleteEvent chỉ nói thao tác repository đã chạy xong; nó không tự bảo đảm transaction đã commit.

## 1. Luồng xóa một item resource

Giả sử repository Order được export tại /api/orders. Client gửi:

~~~http
DELETE /api/orders/42
~~~

Với thao tác xóa một entity qua REST exporter, luồng khái quát là:

~~~text
HTTP DELETE /api/orders/42
        |
        v
Spring Data REST tìm entity Order có id = 42
        |
        v
BeforeDeleteEvent
        |
        v
Repository thực hiện delete(entity)
        |
        v
AfterDeleteEvent
        |
        v
Hoàn tất xử lý request / transaction commit
~~~

Spring Data REST phát BeforeDeleteEvent trước khi entity bị xóa khỏi repository và AfterDeleteEvent sau thao tác xóa. Các event này là custom Spring application events do REST exporter phát ra.

Nếu entity không được tìm thấy, thao tác có thể kết thúc bằng response không tìm thấy và không có entity để thực hiện chuỗi event xóa như trên. Status code và response body cụ thể cần được kiểm thử theo cấu hình exporter và phiên bản đang dùng.

Ví dụ endpoint item:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Client không cần gọi service hoặc controller tự viết để kích hoạt event. Khi request đi qua Spring Data REST repository exporter, framework phát các event tương ứng trong quá trình xử lý entity.

## 2. Ý nghĩa của BeforeDeleteEvent

BeforeDeleteEvent đại diện cho entity đang chuẩn bị bị xóa. Đây là thời điểm phù hợp cho các công việc cần đọc trạng thái entity trước khi repository xóa nó:

- Kiểm tra điều kiện nghiệp vụ, ví dụ đơn hàng đã thanh toán thì không cho xóa.
- Kiểm tra trạng thái hoặc quan hệ phụ thuộc trước khi xóa.
- Ghi nhận thông tin audit về yêu cầu xóa.
- Chuẩn bị dữ liệu cần thiết cho một quy trình xóa có kiểm soát.
- Từ chối thao tác bằng exception nếu điều kiện không thỏa mãn.

Ví dụ, không cho xóa Order đã thanh toán:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    @HandleBeforeDelete
    public void handleBeforeDelete(Order order) {
        if (order.getStatus() == OrderStatus.PAID) {
            throw new OrderDeletionNotAllowedException(
                    "Không thể xóa đơn hàng đã thanh toán");
        }
    }
}
~~~

Các annotation có ý nghĩa:

- `@RepositoryEventHandler(Order.class)`: đăng ký class làm event handler và giới hạn domain type cần xử lý là Order.
- `@HandleBeforeDelete`: đánh dấu phương thức nhận event trước khi xóa.
- Tham số đầu tiên của phương thức là entity đang được xử lý.

Nếu ném exception, thao tác xóa bị ngắt tại handler trước khi repository thực hiện delete. Nên định nghĩa exception nghiệp vụ và ánh xạ nó thành HTTP status phù hợp, chẳng hạn 409 Conflict, bằng exception handler của ứng dụng. Không nên để lỗi nghiệp vụ bị trả thành một lỗi 500 không có ý nghĩa với client.

BeforeDeleteEvent phù hợp để bảo vệ điều kiện trước khi xóa, nhưng quy tắc nghiệp vụ cốt lõi nên được đặt trong service/domain layer nếu nhiều luồng khác nhau cùng có thể xóa entity.

## 3. Ý nghĩa của AfterDeleteEvent

AfterDeleteEvent đại diện cho entity mà thao tác delete trong repository vừa xử lý xong. Đây là thời điểm phù hợp cho các hành động hậu xử lý như:

- Ghi nhận sự kiện xóa vào audit log.
- Xóa hoặc đánh dấu stale một mục trong cache.
- Cập nhật chỉ mục tìm kiếm.
- Cập nhật metric hoặc thống kê.
- Thông báo cho một thành phần nội bộ rằng entity đã được yêu cầu xóa khỏi repository.

Ví dụ:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final OrderAuditService auditService;

    public OrderDeleteEventHandler(OrderAuditService auditService) {
        this.auditService = auditService;
    }

    @HandleAfterDelete
    public void handleAfterDelete(Order order) {
        auditService.recordDeletion(
                order.getId(),
                order.getOrderNumber());
    }
}
~~~

Phương thức AfterDelete nhận entity vừa được xóa. Nếu cần lưu thông tin sau khi xóa, hãy lấy các giá trị cần thiết từ entity trong handler hoặc chuyển chúng thành một event object nhỏ. Đừng giả định rằng sau khi xóa, mọi association lazy của entity vẫn có thể được truy cập an toàn.

**AfterDeleteEvent không đồng nghĩa với AFTER_COMMIT.** Repository có thể đã hoàn thành lời gọi delete trong khi transaction bao quanh request vẫn chưa commit. Nếu transaction sau đó rollback, thay đổi database có thể không tồn tại dù handler AfterDelete đã chạy.

## 4. Đăng ký annotated event handler

Cách được khuyến nghị cho domain-specific logic là tạo một Spring bean có `@RepositoryEventHandler`, sau đó đánh dấu method bằng annotation tương ứng.

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final OrderPolicy orderPolicy;
    private final OrderAuditService auditService;

    public OrderDeleteEventHandler(
            OrderPolicy orderPolicy,
            OrderAuditService auditService) {
        this.orderPolicy = orderPolicy;
        this.auditService = auditService;
    }

    @HandleBeforeDelete
    public void beforeDelete(Order order) {
        orderPolicy.assertCanDelete(order);
    }

    @HandleAfterDelete
    public void afterDelete(Order order) {
        auditService.recordDeletion(order.getId());
    }
}
~~~

Các import chính:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleAfterDelete;
import org.springframework.data.rest.core.annotation.HandleBeforeDelete;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
~~~

Spring Data REST dùng BeanPostProcessor để phát hiện bean có `@RepositoryEventHandler`, quét các method có annotation event handler và nối chúng với event tương ứng.

Có hai cách đăng ký bean:

1. Đánh dấu class bằng `@Component` hoặc stereotype tương đương để component scan phát hiện.
2. Khai báo bean bằng `@Bean` trong một class cấu hình được nạp vào ApplicationContext.

Ví dụ khai báo thủ công:

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    OrderDeleteEventHandler orderDeleteEventHandler(
            OrderPolicy orderPolicy,
            OrderAuditService auditService) {
        return new OrderDeleteEventHandler(orderPolicy, auditService);
    }
}
~~~

Không cần đồng thời dùng `@Component` và khai báo thêm một bean cho cùng class, vì điều đó có thể tạo hai instance và khiến handler chạy hai lần.

Kiểu của tham số đầu tiên trong method handler xác định domain type mà method quan tâm. Có thể khai báo nhiều handler method cho các domain type khác nhau trong một class; dùng `@RepositoryEventHandler(Order.class)` ở cấp class để giới hạn phạm vi khi cần.

## 5. Dùng AbstractRepositoryEventListener thay cho annotation

Một lựa chọn khác là kế thừa `AbstractRepositoryEventListener` và override các callback:

~~~java
@Component
public class OrderRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeDelete(Object entity) {
        if (entity instanceof Order order) {
            // Kiểm tra điều kiện trước khi xóa Order.
        }
    }

    @Override
    protected void onAfterDelete(Object entity) {
        if (entity instanceof Order order) {
            // Xử lý sau thao tác xóa Order.
        }
    }
}
~~~

Cách này hữu ích khi muốn tập trung nhiều loại repository event trong một listener. Tuy nhiên, listener tổng quát phải tự kiểm tra kiểu entity trong callback. Annotated handler thường dễ đọc và an toàn kiểu hơn khi logic chỉ áp dụng cho một vài domain type.

Các callback xóa tương ứng là:

| Event | Callback |
| --- | --- |
| BeforeDeleteEvent | `onBeforeDelete(entity)` |
| AfterDeleteEvent | `onAfterDelete(entity)` |

Không đăng ký cả annotated handler và AbstractRepositoryEventListener để cùng thực hiện một side effect nếu chưa có chủ đích, vì cả hai cơ chế có thể cùng nhận event.

## 6. Phân biệt xóa entity và gỡ association link

DELETE trên item resource và DELETE trên association resource là hai thao tác khác nhau.

Ví dụ:

~~~http
DELETE /api/orders/42
~~~

Request này xóa entity Order có id 42 khỏi repository. Đây là trường hợp của BeforeDeleteEvent và AfterDeleteEvent.

Trong khi đó:

~~~http
DELETE /api/orders/42/customer
~~~

có thể chỉ gỡ liên kết giữa Order và Customer. Nó không mặc nhiên xóa entity Customer khỏi repository.

Spring Data REST có các event riêng cho thao tác trên association link, gồm:

- `BeforeLinkDeleteEvent`: trước khi xóa link tới entity liên quan khỏi parent.
- `AfterLinkDeleteEvent`: sau khi link liên quan được xóa khỏi parent.

Các event link-delete có thể được xử lý bằng `@HandleBeforeLinkDelete` và `@HandleAfterLinkDelete`, hoặc callback tương ứng trong `AbstractRepositoryEventListener`. Với callback, listener nhận cả parent và linked entity.

Ví dụ minh họa:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderLinkEventHandler {

    @HandleBeforeLinkDelete
    public void beforeCustomerUnlinked(Order order, Customer customer) {
        // Kiểm tra việc gỡ Customer khỏi Order.
    }

    @HandleAfterLinkDelete
    public void afterCustomerUnlinked(Order order, Customer customer) {
        // Ghi nhận association đã được gỡ.
    }
}
~~~

Chữ ký handler link event có hai tham số: parent entity và linked entity. Đây là điểm khác với BeforeDelete/AfterDelete, vốn xử lý một entity bị xóa khỏi repository.

Nếu nghiệp vụ muốn xóa Customer thật sự, client phải gọi item resource của Customer và thao tác đó mới thuộc lifecycle delete entity. Không dùng event gỡ link để thực hiện thay cho xóa entity.

## 7. AfterDelete và thời điểm transaction commit

Spring application events mặc định được xử lý đồng bộ. Điều đó có nghĩa là khi REST exporter publish event, listener thường chạy ngay trong luồng xử lý request.

Trình tự khái quát:

~~~text
Repository delete
       |
       v
AfterDeleteEvent được publish
       |
       v
Listener đồng bộ chạy
       |
       v
Transaction hoàn tất / commit hoặc rollback
~~~

Vì vậy, tên AfterDelete chỉ nói thao tác repository đã chạy xong. Nó không phải bằng chứng rằng transaction đã commit thành công.

Nếu listener gửi email, gọi HTTP tới hệ thống khác hoặc xóa dữ liệu bên ngoài ngay trong AfterDelete, có thể xảy ra tình huống:

1. Listener thực hiện side effect bên ngoài thành công.
2. Transaction database sau đó rollback.
3. Database vẫn giữ entity, nhưng hệ thống ngoài đã nhận thông báo xóa.

Đây là lý do không nên đặt side effect không thể đảo ngược trực tiếp trong handler AfterDelete.

### Dùng TransactionalEventListener cho hành động sau commit

Có thể publish một application event riêng từ handler AfterDelete, rồi xử lý nó sau khi transaction commit:

~~~java
public record OrderDeletedEvent(
        Long orderId,
        String orderNumber) {
}
~~~

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final ApplicationEventPublisher publisher;

    public OrderDeleteEventHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @HandleAfterDelete
    public void afterDelete(Order order) {
        publisher.publishEvent(new OrderDeletedEvent(
                order.getId(),
                order.getOrderNumber()));
    }
}
~~~

Listener chỉ chạy sau commit:

~~~java
@Component
public class OrderDeletionNotificationListener {

    private final SearchIndexService searchIndexService;

    public OrderDeletionNotificationListener(
            SearchIndexService searchIndexService) {
        this.searchIndexService = searchIndexService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderDeleted(OrderDeletedEvent event) {
        searchIndexService.removeOrder(event.orderId());
    }
}
~~~

Các import chính cho phần transaction event:

~~~java
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;
~~~

`@TransactionalEventListener` mặc định gắn với transaction đang hoạt động. Nếu event được publish ngoài transaction, listener không chạy trừ khi bật `fallbackExecution = true`. Hãy xác định rõ transaction boundary của request và test trường hợp không có transaction.

Nếu cần bảo đảm thông điệp không bị mất giữa database và message broker, cân nhắc **transactional outbox**: ghi một bản ghi outbox trong cùng transaction xóa entity, sau commit có worker đọc outbox và gửi message. Outbox giúp xử lý retry, crash và tính nhất quán tốt hơn việc gọi hệ thống ngoài trực tiếp từ event handler.

## 8. BeforeDelete không thay thế authorization và service rule

BeforeDeleteEvent có thể kiểm tra điều kiện nghiệp vụ, nhưng không phải ranh giới bảo mật duy nhất.

Ví dụ, không cho xóa Order đã thanh toán là một quy tắc domain. Nếu cùng Order có thể bị xóa từ REST API, scheduled job, message consumer hoặc service nội bộ, quy tắc phải được dùng chung ở service/domain layer.

Các lớp trách nhiệm nên được phân biệt:

- **Spring Security / authorization:** người gọi có quyền xóa tài nguyên này không?
- **Service/domain policy:** trạng thái hiện tại có cho phép xóa không?
- **BeforeDeleteEvent:** tích hợp thêm logic cho đường đi qua Spring Data REST exporter.
- **Database constraints:** bảo vệ tính toàn vẹn dữ liệu ở mức lưu trữ.

Đừng chỉ kiểm tra quyền bằng cách xem một field của entity trong handler. Authorization thường phụ thuộc user hiện tại, tenant, ownership và policy; hãy dùng Spring Security và service kiểm tra quyền phù hợp.

## 9. Phạm vi phát event

BeforeDeleteEvent và AfterDeleteEvent là event của **Spring Data REST REST exporter**. Chúng được phát khi thao tác đi qua pipeline repository REST của Spring Data REST.

Không nên giả định rằng mọi cách gọi `repository.delete(...)` trong ứng dụng đều phát các event này. Ví dụ, service tự gọi repository, scheduled task hoặc batch job không tự động đi qua REST exporter.

Nếu cần logic chạy cho tất cả đường xóa:

- Đặt quy tắc nghiệp vụ và side effect cần thiết ở service/domain layer dùng chung.
- Dùng JPA lifecycle callback như `@PreRemove` hoặc `@PostRemove` cho các nhu cầu gắn với thao tác entity của JPA, sau khi đã hiểu giới hạn của chúng.
- Lưu ý bulk JPQL/native delete có thể bỏ qua entity lifecycle callbacks vì database xóa theo câu lệnh hàng loạt thay vì tải từng entity.

Spring Data REST event handler nên được xem là hook tích hợp của REST API, không phải event bus toàn ứng dụng thay thế mọi lifecycle mechanism.

## 10. Cascade delete và dữ liệu liên quan

Nếu Order có quan hệ `@OneToMany(cascade = CascadeType.REMOVE)` hoặc `orphanRemoval = true`, xóa Order có thể kéo theo việc xóa OrderLine. Tuy nhiên, đừng giả định REST exporter sẽ phát một cặp BeforeDelete/AfterDelete riêng cho mọi entity bị xóa do cascade JPA.

Exporter xử lý entity được gửi tới repository delete. Các thao tác cascade ở tầng ORM có lifecycle riêng; nếu cần audit từng child, hãy thiết kế logic ở service/domain hoặc JPA lifecycle phù hợp và kiểm thử bằng database thật.

Ngoài ra, ràng buộc khóa ngoại có thể khiến delete thất bại nếu còn entity phụ thuộc. BeforeDeleteEvent có thể kiểm tra trước để trả lỗi nghiệp vụ dễ hiểu, nhưng database constraint vẫn là lớp bảo vệ cuối cùng trước dữ liệu tham chiếu không hợp lệ.

## 11. Kiểm thử BeforeDeleteEvent và AfterDeleteEvent

Nên kiểm thử ít nhất ba hành vi:

1. Request DELETE hợp lệ phát before và after handler, sau đó entity không còn trong repository.
2. Handler BeforeDelete từ chối entity theo policy thì repository không xóa entity.
3. Handler AfterDelete chỉ thực hiện side effect mong muốn và xử lý transaction boundary đúng cách.

Ví dụ kiểm thử HTTP DELETE:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderDeleteResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void deletesOrderThroughRestExporter() throws Exception {
        Order order = orderRepository.save(new Order("PO-42"));

        mockMvc.perform(delete("/api/orders/{id}", order.getId()))
            .andExpect(status().isNoContent());

        assertThat(orderRepository.findById(order.getId())).isEmpty();
    }
}
~~~

Ví dụ kiểm thử policy từ chối xóa:

~~~java
@Test
void doesNotDeletePaidOrder() throws Exception {
    Order order = orderRepository.save(
            new Order("PO-PAID", OrderStatus.PAID));

    mockMvc.perform(delete("/api/orders/{id}", order.getId()))
        .andExpect(status().isConflict());

    assertThat(orderRepository.findById(order.getId())).isPresent();
}
~~~

Ví dụ thứ hai giả định ứng dụng đã ánh xạ `OrderDeletionNotAllowedException` thành HTTP 409. Cần cấu hình exception handler tương ứng; annotation event handler tự nó không quy định status code cho mọi exception.

Để kiểm thử AfterCommit:

- Gửi DELETE trong transaction thật.
- Xác nhận custom event chỉ kích hoạt listener sau commit.
- Kiểm thử rollback để xác nhận side effect sau commit không chạy.
- Kiểm tra trường hợp event được publish khi không có transaction nếu ứng dụng có đường đi đó.

Không chỉ kiểm tra method listener đã được gọi. Hãy xác nhận trạng thái database, response HTTP và side effect cuối cùng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Handler không chạy | Bean chưa được component scan hoặc không được khai báo trong ApplicationContext | Kiểm tra @Component/@Bean và package scan |
| Handler chạy cho nhiều domain type ngoài dự kiến | Handler không được giới hạn domain type | Dùng @RepositoryEventHandler(Order.class) hoặc tham số đúng kiểu |
| BeforeDelete chạy nhưng entity vẫn tồn tại | Handler ném exception hoặc repository delete thất bại | Kiểm tra exception, transaction và constraint |
| AfterDelete chạy nhưng database vẫn có entity | Transaction sau đó rollback | Dùng transaction-aware listener cho side effect sau commit |
| Gửi message trước commit rồi database rollback | Side effect ngoài được thực hiện đồng bộ trong AfterDelete | Publish event riêng và dùng AFTER_COMMIT hoặc outbox |
| DELETE association không chạy BeforeDelete | Request chỉ gỡ liên kết, không xóa entity | Dùng link-delete event phù hợp |
| Xóa entity qua service không phát event | Request không đi qua Spring Data REST exporter | Đưa logic chung vào service/domain layer |
| Handler bị gọi hai lần | Cùng class được đăng ký bằng nhiều cách hoặc nhiều handler cùng xử lý side effect | Kiểm tra component scan và khai báo bean |
| Cascade child không có audit riêng | ORM cascade không phải từng REST delete request | Dùng domain/JPA lifecycle phù hợp và test cascade |
| HTTP status không như mong đợi | Exception từ handler chưa được ánh xạ | Dùng exception handler và kiểm thử response |

## 13. Chọn đúng event cho từng nhu cầu

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Chặn xóa Order trước repository delete | `@HandleBeforeDelete` |
| Ghi nhận handler đã đi qua thao tác delete của REST exporter | `@HandleAfterDelete` |
| Làm việc với entity trước/sau khi gỡ association | `@HandleBeforeLinkDelete` / `@HandleAfterLinkDelete` |
| Thực hiện side effect chỉ sau transaction commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Bảo đảm phát message bền vững sau database commit | Transactional outbox |
| Áp dụng policy cho cả REST, job và service | Service/domain layer dùng chung |
| Theo dõi JPA entity lifecycle | `@PreRemove` / `@PostRemove` với giới hạn của JPA |

## Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Events](https://docs.spring.io/spring-data/rest/reference/events.html): tám repository events, cách viết ApplicationListener và annotated handler, đăng ký bean và mặc định xử lý event đồng bộ.
- [Spring Data REST 5.1.2 API — BeforeDeleteEvent](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/BeforeDeleteEvent.html): event phát trước khi entity bị xóa khỏi repository.
- [Spring Data REST 5.1.2 API — AfterDeleteEvent](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AfterDeleteEvent.html): event phát sau khi entity bị xóa khỏi repository.
- [Spring Data REST 5.1.2 API — AbstractRepositoryEventListener](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AbstractRepositoryEventListener.html): callback onBeforeDelete và onAfterDelete.
- [Spring Data REST 5.1.2 API — Event package hierarchy](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-tree.html): các event liên quan đến xóa entity và xóa association link.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): dùng @TransactionalEventListener và các transaction phase như AFTER_COMMIT.
