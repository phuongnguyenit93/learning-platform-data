# N+1 khi tạo link

Trong API dùng Spring HATEOAS, một endpoint collection thường chuyển nhiều entity thành các representation có self link, relation đến resource liên quan và action link. Nếu mỗi lần tạo representation lại kích hoạt một truy vấn database riêng để đọc quan hệ lazy hoặc kiểm tra quyền, số lượng SQL có thể tăng theo số phần tử. Đây là vấn đề **N+1 query**.

Ví dụ, endpoint trả về 50 đơn hàng chỉ cần một truy vấn lấy danh sách, nhưng assembler lại truy vấn customer của từng đơn hàng. Tổng số truy vấn có thể thành 1 + 50. Nếu assembler còn truy vấn payment hoặc kiểm tra trạng thái hủy riêng cho mỗi đơn hàng, số truy vấn tiếp tục tăng.

Điểm cần phân biệt: **việc tạo URI bằng WebMvcLinkBuilder, linkTo() hoặc methodOn() tự nó không gọi database**. N+1 thường đến từ dữ liệu mà assembler đọc để tạo representation, các quan hệ JPA được khởi tạo lazy hoặc các lời gọi repository/service đặt bên trong vòng lặp tạo link. Tối ưu đúng chỗ giúp API vừa giữ được hypermedia controls vừa có hiệu năng ổn định.

## 1. N+1 query hình thành như thế nào?

N+1 là mẫu truy vấn trong đó ứng dụng chạy một truy vấn để lấy N phần tử, sau đó chạy thêm một truy vấn cho từng phần tử để lấy dữ liệu liên quan:

~~~text
GET /orders
  Query 1: SELECT * FROM orders
  Query 2: SELECT * FROM customers WHERE id = ?
  Query 3: SELECT * FROM customers WHERE id = ?
  ...
  Query N+1: SELECT * FROM customers WHERE id = ?
~~~

Với N đơn hàng, số truy vấn tăng xấp xỉ 1 + N. Nếu có nhiều quan hệ lazy độc lập, tổng số truy vấn có thể gần 1 + N + N hoặc cao hơn. Số lượng SQL tăng làm tăng round trip, thời gian chờ database, tải connection pool và độ trễ tail của endpoint.

Trong Spring HATEOAS, N+1 thường xuất hiện ở các vị trí sau:

- Assembler gọi getter của quan hệ lazy như customer, items hoặc payments.
- Assembler gọi repository/service trong mỗi lần chuyển entity thành model.
- Điều kiện thêm link truy cập dữ liệu lazy, ví dụ kiểm tra order có payment hay chưa.
- Policy phân quyền truy vấn database riêng cho từng resource.
- Representation lồng nhau khiến serializer chạm vào quan hệ lazy trong lúc ghi JSON.

Không phải cứ có nhiều link là có N+1. Một resource có thể tạo nhiều link bằng các ID đã có sẵn mà không phát sinh truy vấn nào.

## 2. Phân biệt chi phí tạo link và chi phí lấy dữ liệu

Đoạn code sau tạo self link từ ID của đơn hàng:

~~~java
Link self = linkTo(methodOn(OrderController.class)
        .one(order.getId()))
        .withSelfRel();
~~~

Spring HATEOAS dùng controller mapping để dựng URI. Lời gọi method trên proxy do methodOn() tạo ra nhằm ghi nhận handler và tham số; nó không thực thi body của controller, không gửi HTTP request và không truy vấn repository.

Ngược lại, các thao tác sau có thể kích hoạt SQL:

~~~java
String customerName = order.getCustomer().getName();
int itemCount = order.getItems().size();
boolean hasPayment = paymentRepository.existsByOrderId(order.getId());
~~~

Hai getter đầu có thể khởi tạo proxy/collection lazy. Lệnh existsByOrderId() chắc chắn tạo một truy vấn riêng nếu được gọi trong mỗi vòng lặp. Nếu assembler dùng các kết quả này để thêm relation hoặc affordance, N+1 sẽ bị hiểu nhầm là chi phí tạo link.

Nguyên tắc thiết kế: **assembler nên chuyển dữ liệu đã được tải sẵn thành representation**. Việc quyết định dữ liệu nào cần tải và tải theo cách nào thuộc query/service layer; việc đánh giá quyền nên dùng context đã chuẩn bị hoặc một truy vấn bulk.

## 3. Ví dụ gây N+1 trong assembler

Giả sử entity Order có quan hệ nhiều-một đến Customer. Quan hệ được tải lazy:

~~~java
@Entity
class Order {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    // getters
}
~~~

Một assembler đơn giản đọc tên customer để đưa vào representation:

~~~java
@Component
class OrderModelAssembler {

    EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation representation = new OrderRepresentation(
                order.getId(),
                order.getStatus().name(),
                order.getCustomer().getName());

        return EntityModel.of(
                representation,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(order.getCustomer().getId())).withRel("customer"));
    }
}
~~~

Nếu repository chỉ tải Order mà không tải Customer, mỗi lần gọi getCustomer().getName() có thể phát sinh một SELECT. Khi endpoint map một collection, Hibernate có thể chạy một query lấy orders rồi một query customer cho từng order.

Một anti-pattern khác là truy vấn trong assembler:

~~~java
EntityModel<OrderRepresentation> toModel(Order order) {
    Customer customer = customerRepository.findById(order.getCustomer().getId())
            .orElseThrow();

    boolean hasPayment = paymentRepository.existsByOrderId(order.getId());

    // Tạo representation và link từ customer/hasPayment.
}
~~~

Nếu assembler được gọi N lần, hai lời gọi repository có thể tạo thêm đến 2N truy vấn. Việc chuyển truy vấn ra một method khác nhưng vẫn gọi method đó trong vòng lặp không giải quyết N+1.

## 4. Nhận diện N+1 bằng SQL log và metrics

Trước khi tối ưu, hãy xác định truy vấn nào lặp lại và nơi kích hoạt nó.

Trong môi trường development/test, bật log SQL và bind parameter của Hibernate:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.open-in-view=false
~~~

Các logger bind parameter có thể khác theo Hibernate version. Không bật bind logging lâu dài ở production nếu câu lệnh chứa dữ liệu nhạy cảm.

Quan sát dấu hiệu:

- Cùng một mẫu SELECT lặp lại với ID khác nhau.
- Số truy vấn tăng gần tuyến tính khi tăng số phần tử collection.
- Endpoint chậm dù truy vấn đầu tiên trả ít dữ liệu.
- SQL chỉ xuất hiện khi assembler chạy hoặc khi response serialize.
- Tắt phần tạo relation/field dựa trên quan hệ lazy làm số query giảm mạnh.

Hibernate Statistics có thể cung cấp số prepared statement và entity/collection fetch. Có thể dùng datasource-proxy hoặc p6spy để ghi nhận query count theo request, thời gian từng query và SQL lặp. Khi so sánh, giữ dữ liệu, cache và kích thước trang ổn định để kết quả có ý nghĩa.

## 5. Tải trước quan hệ bằng EntityGraph

Với quan hệ to-one như Order.customer, một cách thường dùng là khai báo EntityGraph trên repository method:

~~~java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface OrderRepository extends JpaRepository<Order, UUID> {

    @EntityGraph(attributePaths = "customer")
    @Query("select o from Order o where o.status = :status")
    List<Order> findForRepresentation(@Param("status") OrderStatus status);
}
~~~

EntityGraph yêu cầu persistence provider tải customer cùng với orders theo fetch plan của truy vấn. Với quan hệ to-one, provider thường có thể thực hiện trong một SQL join, nhờ vậy assembler đọc customer mà không cần thêm một query cho từng order.

Service lấy dữ liệu và map model:

~~~java
@Service
class OrderQueryService {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderQueryService(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @Transactional(readOnly = true)
    CollectionModel<EntityModel<OrderRepresentation>> findPendingOrders() {
        List<EntityModel<OrderRepresentation>> models =
                repository.findForRepresentation(OrderStatus.PENDING)
                        .stream()
                        .map(assembler::toModel)
                        .toList();

        return CollectionModel.of(models);
    }
}
~~~

Transaction bao quanh quá trình tải dữ liệu và dựng model. Tuy vậy, không nên dựa vào Open Session in View để vô tình tải lazy association trong lúc serialize response. Tải những dữ liệu representation cần trước khi rời khỏi service layer, sau đó map sang DTO.

EntityGraph là fetch plan chứ không phải chỉ thị rằng mọi association đều nên eager. Chỉ đưa vào graph các quan hệ thực sự cần cho representation của endpoint.

## 6. Dùng JOIN FETCH cho quan hệ phù hợp

JPQL fetch join là một lựa chọn khác:

~~~java
@Query("""
       select o
       from Order o
       join fetch o.customer
       where o.status = :status
       """)
List<Order> findWithCustomerByStatus(@Param("status") OrderStatus status);
~~~

Fetch join tải association trong cùng truy vấn. Với quan hệ to-one, đây thường là cách đơn giản để tránh N+1. Dùng LEFT JOIN FETCH nếu quan hệ có thể null và đơn hàng vẫn cần xuất hiện trong kết quả.

Cẩn trọng khi fetch join collection to-many. Một order có nhiều item sẽ nhân số dòng SQL; fetch nhiều collection có thể tạo tích Descartes, làm dữ liệu trùng lặp và tăng mạnh lượng dữ liệu đọc. Hibernate có thể khử entity trùng trong persistence context, nhưng chi phí truyền và xử lý row vẫn tồn tại.

Không dùng collection fetch join trực tiếp với pagination một cách tùy tiện. Database phân trang trên row join chứ không phải trên tập entity cha; Hibernate có thể phải phân trang trong memory hoặc phát cảnh báo. Với trang lớn, cách này vừa tốn bộ nhớ vừa làm kết quả khó dự đoán.

## 7. Batch fetching cho quan hệ lazy

Khi không thể join tất cả quan hệ cần thiết, Hibernate batch fetching gom nhiều khóa lazy vào một truy vấn IN thay vì phát một truy vấn cho từng entity.

Có thể cấu hình trên association:

~~~java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<OrderItem> items = new ArrayList<>();
~~~

Hoặc cấu hình mặc định ở mức ứng dụng:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~

Với 120 order, batch size 50 có thể giảm việc tải collection từ khoảng 120 truy vấn xuống một số ít truy vấn theo từng batch. Số lượng thực tế phụ thuộc association, persistence context, dialect và cách truy cập dữ liệu.

Batch fetching giảm N+1 nhưng không nhất thiết đưa số truy vấn về một. Nó phù hợp khi cần lazy loading có kiểm soát hoặc khi join collection tạo quá nhiều row. Hãy đo lại query count và lượng dữ liệu sau khi bật batch.

## 8. Dùng DTO projection để chỉ lấy dữ liệu representation cần

Nếu assembler chỉ cần ID, trạng thái và tên customer, không nhất thiết phải tải entity graph đầy đủ. DTO projection có thể lấy đúng các field trong một truy vấn:

~~~java
public record OrderLinkData(
        UUID id,
        OrderStatus status,
        UUID customerId,
        String customerName) {
}
~~~

Repository dùng constructor projection:

~~~java
@Query("""
       select new com.example.orders.OrderLinkData(
           o.id, o.status, c.id, c.name)
       from Order o
       join o.customer c
       where o.status = :status
       """)
List<OrderLinkData> findLinkData(@Param("status") OrderStatus status);
~~~

Assembler nhận DTO đã có dữ liệu:

~~~java
@Component
class OrderModelAssembler {

    EntityModel<OrderRepresentation> toModel(OrderLinkData data) {
        OrderRepresentation representation = new OrderRepresentation(
                data.id(), data.status().name(), data.customerName());

        return EntityModel.of(
                representation,
                linkTo(methodOn(OrderController.class)
                        .one(data.id())).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(data.customerId())).withRel("customer"));
    }
}
~~~

Projection tách việc lấy dữ liệu khỏi việc dựng hypermedia. Nó cũng tránh vô tình kích hoạt lazy loading khi serializer đọc entity. Đổi lại, DTO projection cần được duy trì theo nhu cầu representation; khi một endpoint cần dữ liệu khác, có thể tạo projection riêng thay vì tải toàn bộ aggregate.

## 9. Gom kiểm tra quyền và trạng thái thành truy vấn bulk

Một nguyên nhân khác của N+1 là kiểm tra action link bằng service cho từng order:

~~~java
for (Order order : orders) {
    boolean canCancel = permissionService.canCancel(authentication, order.getId());
    // Thêm link cancel nếu canCancel.
}
~~~

Nếu canCancel() truy vấn database mỗi lần, collection có thể tạo N truy vấn quyền. Thay vào đó, lấy tập ID có thể hủy trong một lần:

~~~java
@Query("""
       select o.id
       from Order o
       where o.id in :orderIds
         and o.owner.username = :username
         and o.status = :status
       """)
Set<UUID> findCancellableOrderIds(
        @Param("orderIds") Collection<UUID> orderIds,
        @Param("username") String username,
        @Param("status") OrderStatus status);
~~~

Service chuẩn bị context một lần:

~~~java
Set<UUID> cancellableIds = orderRepository.findCancellableOrderIds(
        orderIds, authentication.getName(), OrderStatus.PENDING);

List<EntityModel<OrderRepresentation>> models = orders.stream()
        .map(order -> assembler.toModel(
                order, cancellableIds.contains(order.getId())))
        .toList();
~~~

Assembler chỉ đọc boolean đã tính trước để quyết định có thêm action link hay không. Với policy dựa trên authority đã có trong Authentication, có thể kiểm tra trực tiếp trong memory mà không cần query. Với policy phức tạp, hãy thiết kế bulk policy method nhận tập resource IDs và trả về kết quả theo ID.

Bulk query phải giữ nguyên quy tắc authorization của hệ thống. Không thay thế một policy chính xác bằng phép kiểm tra đơn giản hơn chỉ để giảm query; tối ưu phải giữ nguyên semantics quyền truy cập.

## 10. Kết hợp dữ liệu cho collection phân trang

Với endpoint phân trang, tránh collection fetch join trực tiếp khi cần tải to-many association. Một mẫu an toàn hơn là hai bước:

1. Lấy trang ID của các order theo filter và sort, kèm count query nếu cần Page.
2. Tải dữ liệu cần cho representation của các ID trong trang bằng một query bulk, rồi sắp xếp lại theo thứ tự ID của trang.

Ví dụ repository:

~~~java
@Query(
    value = "select o.id from Order o where o.status = :status",
    countQuery = "select count(o) from Order o where o.status = :status")
Page<UUID> findPageIds(
        @Param("status") OrderStatus status, Pageable pageable);

@EntityGraph(attributePaths = "customer")
@Query("select o from Order o where o.id in :ids")
List<Order> findPageDetails(@Param("ids") Collection<UUID> ids);
~~~

Service có thể dựng model theo đúng thứ tự trang:

~~~java
Page<UUID> idPage = repository.findPageIds(status, pageable);

Map<UUID, Order> byId = idPage.isEmpty()
        ? Map.of()
        : repository.findPageDetails(idPage.getContent()).stream()
                .collect(Collectors.toMap(Order::getId, Function.identity()));

Page<Order> orderPage = idPage.map(byId::get);
return orderPage.map(assembler::toModel);
~~~

Đây là khung minh họa cho bước bulk load; đoạn code bỏ qua truy vấn detail khi trang rỗng, sau đó map các ID về entity theo đúng thứ tự của trang ban đầu. Có thể chuyển Page<Order> thành PagedModel bằng PagedResourcesAssembler rồi map từng phần tử qua assembler. Điểm quan trọng là số query không tăng theo số phần tử của trang.

Nếu chỉ cần dữ liệu to-one, một Page query có EntityGraph có thể đủ. Với to-many, cân nhắc projection, batch fetching hoặc hai bước như trên. Luôn kiểm tra SQL thực tế để bảo đảm database phân trang ở đúng tập ID cha.

## 11. Không để serializer kích hoạt lazy loading

Một lỗi khó phát hiện là service đã trả entity ra ngoài, còn Jackson/HAL serializer mới đọc thuộc tính lazy. Khi Open Session in View được bật, session có thể vẫn mở trong lúc serialize nên request không lỗi nhưng phát sinh nhiều SQL muộn.

Ví dụ DTO vô tình giữ entity:

~~~java
public record OrderRepresentation(UUID id, Customer customer) {
}
~~~

Nếu serializer đi sâu vào Customer, nó có thể tải các quan hệ khác ngoài dự kiến. Thay bằng DTO phẳng:

~~~java
public record OrderRepresentation(
        UUID id, String customerName, String status) {
}
~~~

Đặt spring.jpa.open-in-view=false trong test hoặc ứng dụng phù hợp để phát hiện việc truy cập lazy ngoài transaction. Đây không thay thế fetch planning; nó giúp lỗi ranh giới tải dữ liệu xuất hiện sớm thay vì bị che bởi session mở kéo dài.

## 12. Đo query count trong test

Có thể bật Hibernate Statistics trong test và xác nhận số SQL không tăng tuyến tính theo số order. Ví dụ với repository dùng EntityGraph:

~~~java
import java.util.List;
import java.util.UUID;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.hateoas.EntityModel;

import jakarta.persistence.EntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.properties.hibernate.generate_statistics=true",
        "spring.jpa.open-in-view=false"
})
class OrderRepresentationQueryTest {

    @Autowired
    EntityManager entityManager;

    @Autowired
    OrderRepository repository;

    @Test
    void loadsCustomerDataWithoutOneQueryPerOrder() {
        // Fixture tạo nhiều Order có Customer khác nhau trước khi đo.
        entityManager.flush();
        entityManager.clear();

        SessionFactory sessionFactory =
                entityManager.getEntityManagerFactory().unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();
        statistics.clear();

        List<Order> orders = repository.findForRepresentation(OrderStatus.PENDING);

        OrderModelAssembler assembler = new OrderModelAssembler();
        List<EntityModel<OrderRepresentation>> models = orders.stream()
                .map(assembler::toModel)
                .toList();

        assertThat(models).hasSameSizeAs(orders);
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1);
    }
}
~~~

Test giả định query repository tải customer bằng EntityGraph và assembler chỉ đọc các field đã tải. Fixture phải được tạo trước khi xóa statistics; nếu test còn gọi query phụ để xác minh fixture, thực hiện các thao tác đó trước statistics.clear(). Query count chính xác có thể khác khi thêm filter, tenant lookup hoặc count query; hãy đặt assertion theo contract truy vấn của test.

Đối với endpoint phân trang, thường có ít nhất một query lấy page và một query count. Nếu dùng hai bước lấy ID và detail, số query có thể là hai hoặc ba nhưng vẫn phải ổn định khi tăng page size trong cùng giới hạn. Mục tiêu là phát hiện số query tăng theo từng item, không phải ép mọi endpoint về đúng một SQL.

## 13. Quy trình tối ưu

Khi endpoint collection chậm, có thể xử lý theo thứ tự:

1. Đo thời gian endpoint, query count, tổng thời gian SQL và số row trả về.
2. Xác định query lặp bằng SQL log hoặc datasource proxy.
3. Tìm getter lazy, repository call và policy call trong assembler/mapper.
4. Liệt kê chính xác field, quan hệ và điều kiện link mà representation cần.
5. Chọn EntityGraph, fetch join to-one, batch fetch, DTO projection hoặc bulk lookup.
6. Map DTO/model trong transaction đọc dữ liệu; tránh để serializer tự khởi tạo lazy association.
7. Đo lại với page size và dữ liệu gần với production.
8. Kiểm thử rằng relation, affordance và quyền truy cập vẫn giữ nguyên sau tối ưu.

Đừng tối ưu bằng cách loại bỏ link nghiệp vụ mà client cần. Hãy tối ưu cách lấy dữ liệu dùng để quyết định link và cách dựng representation.

## 14. Lỗi thường gặp

**Đổ lỗi cho linkTo() gây N+1:** link builder dựng URI từ mapping; hãy tìm truy vấn trong getter lazy hoặc service được gọi khi assemble.

**Gọi repository trong assembler cho từng item:** chuyển sang query bulk hoặc chuẩn bị context trước vòng lặp.

**Dùng EAGER cho mọi association:** có thể tải dữ liệu không cần, tạo join lớn và làm chậm các endpoint khác. Chọn fetch plan theo use case.

**Fetch join nhiều collection cùng lúc:** có thể nhân số row và tạo Cartesian product. Dùng batch fetch, projection hoặc query theo hai bước.

**Fetch join collection với pagination:** dễ làm phân trang ở memory hoặc tạo kết quả không mong muốn. Phân trang ID cha trước rồi bulk load detail.

**Dựa vào Open Session in View:** serializer có thể kích hoạt lazy query sau khi service kết thúc. Chuyển sang DTO và tải dữ liệu có chủ đích.

**Chỉ đo thời gian, không đếm query:** N+1 có thể bị che bởi cache ở local. Đo query count với cache được kiểm soát và dữ liệu đủ lớn.

**Tối ưu query nhưng bỏ sót authorization:** bulk permission lookup phải tương đương policy cũ và vẫn được kiểm tra lại ở command endpoint.

## 15. Checklist tránh N+1 khi tạo link

- Assembler không gọi repository/service theo từng entity.
- Link được tạo từ ID và dữ liệu đã có; không ghép URL bằng quy ước hard-code.
- Quan hệ to-one cần cho representation được tải bằng EntityGraph hoặc fetch join phù hợp.
- Quan hệ to-many được xử lý bằng batch fetch, projection hoặc query riêng theo batch.
- Action link dùng permission context hoặc bulk authorization lookup.
- DTO không giữ entity lazy để serializer truy cập về sau.
- Pagination không fetch join collection một cách tùy tiện.
- Open Session in View được cân nhắc và kiểm thử rõ ràng.
- SQL log/metrics cho thấy query count không tăng tuyến tính theo số item.
- Test xác nhận cả query budget và nội dung hypermedia.

N+1 khi tạo link thực chất thường là N+1 khi **chuẩn bị dữ liệu cho representation**. Spring HATEOAS có thể tạo hàng trăm link từ ID mà không cần truy vấn database; vấn đề xuất hiện khi mỗi link phụ thuộc vào một quan hệ lazy hoặc một lần kiểm tra quyền riêng. Khi query layer tải trước dữ liệu cần thiết, assembler chỉ chuyển dữ liệu thành representation, và test đo query count theo kích thước collection, API có thể giữ được khả năng điều hướng hypermedia mà vẫn có hiệu năng ổn định.

## Tài liệu tham khảo

- [Spring Data JPA Reference – EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Hibernate ORM User Guide – Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Spring HATEOAS Reference – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring Boot Reference – Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
