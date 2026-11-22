# BeforeLinkSaveEvent và AfterLinkSaveEvent khi thay đổi liên kết

Spring Data REST cung cấp các repository event để ứng dụng can thiệp vào vòng đời xử lý tài nguyên REST. Khi client thay đổi một association giữa hai entity, hai sự kiện quan trọng là BeforeLinkSaveEvent và AfterLinkSaveEvent.

BeforeLinkSaveEvent được phát trước khi liên kết tới entity liên quan được lưu vào parent resource. AfterLinkSaveEvent được phát sau khi liên kết đó được lưu vào parent. Nhờ hai điểm mở rộng này, ứng dụng có thể kiểm tra quy tắc nghiệp vụ trước khi thay đổi quan hệ và thực hiện các xử lý tiếp theo sau thao tác liên kết.

## 1. Thay đổi liên kết khác với lưu một entity

Giả sử một đơn hàng có nhiều sản phẩm. PurchaseOrder là entity cha, Product là entity được liên kết:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @ManyToMany
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

Repository của đơn hàng được công bố:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Khi đọc đơn hàng 42, HAL representation có thể cung cấp association link:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "items": {
      "href": "http://localhost:8080/api/orders/42/items"
    }
  }
}
~~~

Client có thể dùng association resource để thêm sản phẩm đã tồn tại vào đơn hàng:

~~~http
POST /api/orders/42/items
Content-Type: text/uri-list

http://localhost:8080/api/products/7
~~~

Thao tác này thay đổi mối liên kết giữa PurchaseOrder và Product. Nó khác với POST /api/products, vốn tạo một Product mới trong repository collection.

Vì đây là thao tác lưu một liên kết, Spring Data REST có thể phát BeforeLinkSaveEvent và AfterLinkSaveEvent. Các event này cho phép ứng dụng xử lý quan hệ mà không cần đưa toàn bộ logic vào controller.

## 2. BeforeLinkSaveEvent là gì?

BeforeLinkSaveEvent được phát trước khi một linked object được lưu vào parent trong repository. Event mang hai đối tượng:

- **Parent:** entity sở hữu association, được truyền làm source của event.
- **Linked object:** entity được liên kết với parent, có thể lấy qua getLinked().

Với ví dụ đơn hàng, parent là PurchaseOrder 42 và linked object là Product 7.

Đây là thời điểm phù hợp để kiểm tra những quy tắc cần được thỏa mãn trước khi quan hệ thay đổi:

- Đơn hàng phải ở trạng thái cho phép bổ sung sản phẩm.
- Sản phẩm phải đang hoạt động.
- Sản phẩm phải thuộc đúng kho hoặc tenant.
- Người dùng phải có quyền thay đổi danh sách sản phẩm.
- Số lượng hoặc giới hạn liên kết phải phù hợp với nghiệp vụ.

Nếu quy tắc không được thỏa mãn, handler có thể từ chối thao tác bằng exception nghiệp vụ. Ứng dụng nên ánh xạ exception sang HTTP status phù hợp bằng cơ chế xử lý lỗi của mình, ví dụ 409 Conflict hoặc 422 Unprocessable Entity.

BeforeLinkSaveEvent không phải sự kiện tạo Product mới. Nó tập trung vào việc liên kết entity đã được phân giải với parent resource.

## 3. AfterLinkSaveEvent là gì?

AfterLinkSaveEvent được phát sau khi linked object đã được lưu vào parent trong repository.

Trong ví dụ, khi Product 7 đã được liên kết với PurchaseOrder 42, ứng dụng có thể sử dụng sự kiện này để:

- Ghi log hoặc audit việc bổ sung sản phẩm.
- Cập nhật số liệu tổng hợp cần thiết.
- Gửi thông tin tới một thành phần khác.
- Ghi nhận lịch sử thay đổi association.
- Kích hoạt một quy trình nghiệp vụ tiếp theo.

AfterLinkSaveEvent cũng mang parent và linked object. Cách xác định hai đối tượng giống với BeforeLinkSaveEvent.

Không nên dùng AfterLinkSaveEvent để từ chối một liên kết không hợp lệ, vì tại thời điểm đó thao tác lưu liên kết đã diễn ra. Các điều kiện có thể chặn thao tác nên được kiểm tra trong BeforeLinkSaveEvent hoặc trong service nghiệp vụ trước khi cập nhật.

Cũng cần phân biệt AfterLinkSaveEvent với AfterSaveEvent:

| Event | Đối tượng được quan tâm | Thời điểm |
|---|---|---|
| BeforeLinkSaveEvent | Parent và linked object | Trước khi lưu liên kết. |
| AfterLinkSaveEvent | Parent và linked object | Sau khi lưu liên kết vào parent. |
| BeforeSaveEvent | Entity được lưu | Trước khi lưu entity. |
| AfterSaveEvent | Entity được lưu | Sau thao tác lưu entity. |

Nếu client chỉ thay đổi association, event link save giúp xác định đúng thao tác đang xảy ra thay vì phải suy luận từ một sự kiện save tổng quát.

## 4. Tạo annotated event handler

Cách phổ biến để xử lý repository event là tạo một Spring bean có annotation @RepositoryEventHandler. Các method được đánh dấu bằng @HandleBeforeLinkSave và @HandleAfterLinkSave sẽ nhận sự kiện tương ứng.

Ví dụ:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterLinkSave;
import org.springframework.data.rest.core.annotation.HandleBeforeLinkSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderLinkEventHandler {

    @HandleBeforeLinkSave
    public void beforeLinkSave(
            PurchaseOrder order,
            Product product) {

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new OrderLinkNotAllowedException(
                "Chỉ đơn hàng ở trạng thái DRAFT mới được thêm sản phẩm"
            );
        }

        if (!product.isActive()) {
            throw new OrderLinkNotAllowedException(
                "Không thể thêm sản phẩm đã ngừng hoạt động"
            );
        }
    }

    @HandleAfterLinkSave
    public void afterLinkSave(
            PurchaseOrder order,
            Product product) {

        // Ghi nhận việc liên kết sản phẩm với đơn hàng.
    }
}
~~~

Một số điểm cần hiểu trong ví dụ:

- @Component đăng ký handler vào Spring ApplicationContext.
- @RepositoryEventHandler(PurchaseOrder.class) giới hạn handler cho event của domain type PurchaseOrder.
- @HandleBeforeLinkSave đánh dấu method xử lý trước khi lưu liên kết.
- @HandleAfterLinkSave đánh dấu method xử lý sau khi lưu liên kết.
- Tham số đầu tiên là parent entity; tham số thứ hai là linked object.
- Kiểu tham số đầu tiên giúp Spring Data REST xác định domain type mà method quan tâm.

Nếu ứng dụng dùng nhiều domain type, có thể tạo handler riêng cho từng parent để logic rõ ràng và tránh xử lý nhầm association.

## 5. Đăng ký handler trong Spring

Handler phải là bean được Spring quản lý để Spring Data REST có thể phát hiện các method có annotation sự kiện.

Có hai cách phổ biến.

**Dùng @Component**

~~~java
@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderLinkEventHandler {
    // Các method xử lý event.
}
~~~

Cách này phù hợp khi package của handler nằm trong phạm vi component scan của ứng dụng Spring Boot.

**Khai báo bằng @Bean**

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PurchaseOrderLinkEventHandler purchaseOrderLinkEventHandler() {
        return new PurchaseOrderLinkEventHandler();
    }
}
~~~

Chỉ cần một cách đăng ký bean phù hợp. Không nên đồng thời khai báo cùng một handler bằng component scan và một @Bean khác, vì có thể tạo hai instance và khiến logic được gọi lặp.

BeanPostProcessor của Spring Data REST sẽ kiểm tra bean có @RepositoryEventHandler, tìm các method có annotation xử lý event và kết nối chúng với các repository event tương ứng.

## 6. Xử lý sự kiện bằng AbstractRepositoryEventListener

Ngoài annotated handler, có thể kế thừa AbstractRepositoryEventListener để override các callback.

Ví dụ:

~~~java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderRepositoryEventListener
        extends AbstractRepositoryEventListener<PurchaseOrder> {

    @Override
    protected void onBeforeLinkSave(
            PurchaseOrder parent,
            Object linked) {

        if (parent.getStatus() != OrderStatus.DRAFT) {
            throw new OrderLinkNotAllowedException(
                "Đơn hàng không cho phép thay đổi sản phẩm"
            );
        }
    }

    @Override
    protected void onAfterLinkSave(
            PurchaseOrder parent,
            Object linked) {

        // Xử lý sau khi liên kết được lưu.
    }
}
~~~

Hai callback quan trọng là:

- onBeforeLinkSave(parent, linked): xử lý trước khi liên kết được lưu.
- onAfterLinkSave(parent, linked): xử lý sau khi liên kết được lưu.

Khác với annotated handler có thể khai báo tham số thứ hai theo kiểu Product, callback của AbstractRepositoryEventListener nhận linked dưới kiểu Object. Nếu cần xử lý nhiều kiểu linked object, hãy kiểm tra kiểu trước khi ép kiểu.

Ví dụ:

~~~java
if (linked instanceof Product product) {
    // Xử lý Product.
}
~~~

Cách kế thừa listener hữu ích khi muốn tập trung nhiều callback vào một lớp. Annotated handler thường dễ đọc hơn khi muốn khai báo rõ domain type và linked type ngay trên từng method.

Chọn một cách triển khai phù hợp cho mỗi luồng xử lý để tránh đăng ký trùng logic.

## 7. Phân biệt sự kiện link save với sự kiện create/save thông thường

Spring Data REST có các event cho vòng đời entity và các event dành riêng cho association.

Ví dụ:

| Thao tác HTTP | Event cần quan tâm |
|---|---|
| POST /api/products | BeforeCreateEvent và AfterCreateEvent. |
| PUT hoặc PATCH /api/products/7 | BeforeSaveEvent và AfterSaveEvent. |
| POST tới association resource của đơn hàng | BeforeLinkSaveEvent và AfterLinkSaveEvent. |
| Thay đổi entity cha qua repository item resource | BeforeSaveEvent và AfterSaveEvent. |

Bảng trên mô tả các luồng điển hình. Event thực tế phụ thuộc request, association được công bố và cách Spring Data REST xử lý repository.

Ví dụ, khi client tạo Product mới, handler beforeCreate phù hợp để kiểm tra dữ liệu Product trước khi lưu. Khi client thêm Product đã tồn tại vào PurchaseOrder, handler beforeLinkSave phù hợp để kiểm tra quy tắc liên kết giữa hai entity.

Không nên đặt toàn bộ quy tắc kiểm tra Product vào beforeLinkSave nếu quy tắc đó cũng cần áp dụng khi Product được tạo từ repository collection. Trong trường hợp đó, hãy dùng beforeCreate hoặc beforeSave cho quy tắc của entity và beforeLinkSave cho quy tắc riêng của association.

## 8. Kiểm soát transaction và tác vụ phụ

Spring application events mặc định được xử lý đồng bộ. Vì vậy, handler thường chạy trong luồng xử lý request khi Spring Data REST phát event.

Điều này có một số hệ quả:

- Logic trong handler có thể làm request chậm.
- Exception từ xử lý trước khi lưu có thể ngăn thao tác tiếp tục.
- Lỗi phát sinh trong xử lý sau khi lưu có thể ảnh hưởng tới kết quả request tùy transaction và exception handling.
- AfterLinkSaveEvent cho biết thao tác lưu liên kết đã diễn ra, nhưng không nên tự hiểu rằng transaction cơ sở dữ liệu chắc chắn đã commit.

Với các tác vụ nhẹ như ghi audit nội bộ, handler sau lưu có thể là điểm bắt đầu phù hợp. Với việc gửi email, gọi HTTP service khác hoặc phát thông điệp ra hệ thống ngoài, nên cân nhắc cơ chế xử lý sau commit như @TransactionalEventListener với TransactionPhase.AFTER_COMMIT khi event được phát trong transaction phù hợp, hoặc dùng transactional outbox.

Ví dụ listener sau commit:

~~~java
@Component
public class OrderLinkCommittedListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterLinkCommit(AfterLinkSaveEvent event) {
        PurchaseOrder order =
            (PurchaseOrder) event.getSource();

        Object linked = event.getLinked();

        // Phát thông báo sau khi transaction commit.
    }
}
~~~

Cách này yêu cầu event được phát trong một transaction đang hoạt động. Nếu không có transaction, listener mặc định không chạy; hãy cấu hình fallbackExecution chỉ khi đó thực sự là hành vi mong muốn.

Nếu cần bảo đảm thông điệp không bị mất giữa thời điểm commit dữ liệu và gửi message, transactional outbox thường phù hợp hơn việc gọi hệ thống bên ngoài trực tiếp trong callback.

## 9. Những lưu ý khi kiểm tra association

Khi viết logic cho BeforeLinkSaveEvent và AfterLinkSaveEvent, cần xác định đúng hai phía của quan hệ:

- Parent là entity sở hữu association đang được thay đổi.
- Linked object là entity được tham chiếu hoặc thêm vào association.
- Với quan hệ JPA hai chiều, cần hiểu phía owning side và mappedBy.
- Nếu có nhiều loại association trong cùng parent, kiểm tra đúng linked type và property nghiệp vụ.
- Không giả định mọi thay đổi entity đều phát link save event; chỉ những thao tác lưu liên kết qua luồng Spring Data REST tương ứng mới kích hoạt event này.

Ví dụ, nếu PurchaseOrder có cả items và approver, hai loại liên kết có thể cần các quy tắc khác nhau. Handler có thể kiểm tra trạng thái đơn hàng và loại linked object, hoặc tách logic theo domain type và service nghiệp vụ.

Không nên dùng event handler để thay thế kiểm tra quyền truy cập. Việc người dùng có được phép sửa đơn hàng hay không nên được kiểm tra bằng Spring Security hoặc service authorization. Handler có thể bổ sung quy tắc nhất quán của domain, nhưng cần bảo đảm các đường ghi khác ngoài Spring Data REST cũng áp dụng cùng quy tắc.

## 10. Quy trình thực hành và kiểm tra

Giả sử đơn hàng 42 đang ở trạng thái DRAFT và cần thêm sản phẩm 7:

1. GET /api/orders/42 để xác nhận parent resource tồn tại và lấy association link.
2. GET /api/products/7 để xác nhận sản phẩm tồn tại.
3. Gửi POST tới association href với Content-Type text/uri-list và body là URI sản phẩm.
4. Đặt breakpoint trong beforeLinkSave để xác nhận parent và linked object được truyền đúng.
5. Kiểm tra trường hợp đơn hàng không ở trạng thái DRAFT; handler phải từ chối thao tác.
6. Với sản phẩm hợp lệ và đơn hàng DRAFT, xác nhận beforeLinkSave được gọi trước khi liên kết được lưu.
7. Xác nhận afterLinkSave được gọi sau khi association được lưu vào parent.
8. GET lại /api/orders/42 hoặc association resource để xác nhận trạng thái liên kết.
9. Kiểm tra transaction và log khi handler sau lưu có thực hiện tác vụ phụ.

Có thể kiểm tra bằng cách gửi thêm một sản phẩm không hoạt động hoặc thay đổi trạng thái đơn hàng sang CONFIRMED. Các trường hợp này giúp xác nhận quy tắc trước khi lưu được áp dụng đúng.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Handler không được gọi | Bean chưa được đăng ký hoặc method thiếu annotation. | Kiểm tra component scan, @Bean và annotation handler. |
| Handler nhận sai domain type | Tham số đầu tiên không phải parent entity mà event sử dụng. | Đặt parent làm tham số đầu tiên và kiểm tra @RepositoryEventHandler. |
| Ép kiểu linked object gây lỗi | Association liên kết tới nhiều domain type khác nhau. | Dùng kiểu cụ thể đúng association hoặc kiểm tra instanceof. |
| BeforeLinkSave không chạy khi tạo entity | Đang xử lý create event thay vì association event. | Dùng BeforeCreate/BeforeSave cho entity và BeforeLinkSave cho quan hệ. |
| Exception bị trả về thành 500 | Exception nghiệp vụ chưa được ánh xạ HTTP phù hợp. | Dùng exception handler để trả status và nội dung lỗi phù hợp. |
| Gửi message trước khi transaction commit | Coi AfterLinkSaveEvent là sự kiện after-commit. | Dùng AFTER_COMMIT hoặc transactional outbox cho tác vụ ngoài hệ thống. |
| Quan hệ không được lưu như mong muốn | Mapping JPA hoặc owning side chưa được cập nhật đúng. | Kiểm tra owning side, mappedBy và transaction. |

BeforeLinkSaveEvent là điểm kiểm tra trước khi association được lưu; AfterLinkSaveEvent là điểm xử lý sau khi liên kết được lưu vào parent. Đăng ký handler đúng domain type, nhận parent và linked object đúng thứ tự, rồi đặt kiểm tra nghiệp vụ trước thao tác và tác vụ phụ ở thời điểm phù hợp. Nhờ vậy, ứng dụng có thể kiểm soát thay đổi quan hệ trong Spring Data REST mà vẫn giữ logic rõ ràng theo vòng đời của association.

## Tài liệu tham khảo

- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [BeforeLinkSaveEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/BeforeLinkSaveEvent.html)
- [AfterLinkSaveEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AfterLinkSaveEvent.html)
- [LinkedEntityEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/LinkedEntityEvent.html)
