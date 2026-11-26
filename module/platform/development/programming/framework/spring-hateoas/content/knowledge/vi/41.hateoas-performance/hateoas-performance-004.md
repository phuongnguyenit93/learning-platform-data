# N+1 khi tạo embedded trong Spring HATEOAS

Một endpoint có thể chỉ trả về một trang danh sách đơn hàng, nhưng quá trình tạo representation lại phát sinh hàng chục hoặc hàng trăm truy vấn SQL. Tình huống này thường xuất hiện khi assembler duyệt từng entity, đọc các association lazy để tạo embedded resource, rồi Hibernate tải dữ liệu liên quan bằng một truy vấn riêng cho từng phần tử.

Đây là vấn đề **N+1 query**. Spring HATEOAS không tự tạo ra N+1; nguyên nhân nằm ở cách ứng dụng tải dữ liệu trước và trong lúc ánh xạ entity thành representation. Bài này sử dụng danh sách đơn hàng có embedded customer và items để phân tích nguyên nhân, chọn fetch plan, xử lý phân trang và kiểm tra số truy vấn thực tế.

## 1. Embedded resource có thể làm lộ chi phí truy cập dữ liệu

Giả sử API trả về danh sách đơn hàng. Mỗi đơn hàng có:

- Thông tin cơ bản như mã đơn, trạng thái và tổng tiền.
- Một customer summary.
- Danh sách line item, mỗi item có tên sản phẩm và số lượng.
- Link self, customer và items.

Một representation HAL có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "number": "ORD-0042",
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/orders/42"
          },
          "customer": {
            "href": "/orders/42/customer"
          },
          "items": {
            "href": "/orders/42/items"
          }
        },
        "_embedded": {
          "customer": {
            "id": 7,
            "displayName": "Nguyen Van An"
          },
          "items": [
            {
              "id": 501,
              "productName": "Mechanical Keyboard",
              "quantity": 1
            }
          ]
        }
      }
    ]
  }
}
~~~

Client nhận được dữ liệu cần thiết trong một response. Tuy nhiên, việc tạo response có thể cần đọc nhiều bảng. Nếu mỗi lần đọc association lại phát sinh SQL riêng, số truy vấn tăng theo số đơn hàng hoặc số line item.

Cần phân biệt hai chi phí:

- **Số truy vấn database**: số lần ứng dụng round-trip tới database.
- **Kích thước representation**: lượng dữ liệu được serialize và truyền qua mạng.

Giảm N+1 không tự động làm response nhỏ hơn. Ngược lại, nhúng quá nhiều dữ liệu có thể làm response lớn dù chỉ dùng một truy vấn. Cần tối ưu cả fetch plan lẫn phạm vi embedded.

## 2. N+1 query là gì?

N+1 xuất hiện khi ứng dụng thực hiện một truy vấn để tải N bản ghi gốc, sau đó phát sinh thêm N truy vấn để tải dữ liệu liên quan.

Ví dụ endpoint tải 20 đơn hàng:

~~~sql
-- Truy vấn đầu tiên: lấy 20 đơn hàng
select id, number, status, customer_id
from orders
where status = 'PAID';

-- Sau đó, mỗi đơn hàng tải customer bằng một truy vấn riêng
select id, display_name from customers where id = 7;
select id, display_name from customers where id = 8;
select id, display_name from customers where id = 9;
-- ... tiếp tục cho các đơn còn lại
~~~

Số truy vấn là:

\[
Q(N) = 1 + N
\]

Với N = 20, ứng dụng có thể chạy 21 truy vấn. Với N = 100, số truy vấn tăng lên 101 dù endpoint chỉ thay đổi kích thước trang.

Nếu assembler còn đọc một collection lazy cho mỗi đơn hàng, số truy vấn có thể tăng thêm:

\[
Q(N) = 1 + N_{\text{customer}} + N_{\text{line collections}} + M_{\text{product}}
\]

Ở đây, `N_line collections` là số collection order-lines phải khởi tạo theo từng order. Nếu mỗi line item lại truy cập product lazy, số truy vấn còn phụ thuộc tổng số item và số product chưa được nạp trong persistence context.

N+1 đặc biệt nguy hiểm vì response vẫn đúng về dữ liệu. Chỉ có latency và tải database tăng mạnh khi số phần tử lớn.

## 3. Vì sao assembler dễ kích hoạt N+1?

Một entity có thể khai báo association lazy:

~~~java
@Entity
class Order {

    @Id
    private Long id;

    private String number;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    // getters
}
~~~

Khi repository tải danh sách Order, Hibernate có thể chỉ tải các cột của bảng orders và tạo proxy hoặc persistent collection cho association.

Assembler đọc association để tạo representation:

~~~java
OrderModel toModel(Order order) {

    String customerName = order.getCustomer().getDisplayName();

    List<ItemModel> items = order.getLines().stream()
        .map(line -> new ItemModel(
            line.getId(),
            line.getProduct().getName(),
            line.getQuantity()
        ))
        .toList();

    return new OrderModel(
        order.getId(),
        order.getNumber(),
        customerName,
        items
    );
}
~~~

Khi gọi `getCustomer()`, `getLines()` hoặc `getProduct()`, Hibernate có thể chạy SQL để khởi tạo association. Nếu assembler được gọi lần lượt cho từng đơn hàng, những lần truy cập đó lặp lại theo từng phần tử.

Vấn đề không nằm ở việc tạo Link hay gọi `toModel()` tự thân. Vấn đề là mapping đang duyệt object graph chưa được tải theo nhu cầu của endpoint.

## 4. Nhận diện đúng nơi phát sinh truy vấn

N+1 có thể xuất hiện ở nhiều giai đoạn:

| Giai đoạn | Ví dụ |
|---|---|
| Repository | Tải danh sách entity nhưng không tải association cần dùng |
| Assembler | Gọi getter của association lazy để tạo embedded data |
| HAL builder | Nhận entity hoặc collection lazy rồi duyệt nội dung để nhúng |
| Representation processor | Đọc association để bổ sung field hoặc link |
| JSON serialization | Serializer truy cập getter lazy khi ghi response |
| Service loop | Gọi repository một lần cho từng entity |

Hãy quan sát SQL được phát ra trong cả request, không chỉ trong repository method. Một repository có thể chạy một query, nhưng assembler và serializer vẫn phát sinh thêm nhiều truy vấn sau đó.

Link builder dùng `methodOn(...)` để tạo controller proxy và xây URI. Việc tạo proxy này không gọi method controller thật và không nên truy vấn database. Nếu controller method hoặc helper được gọi trực tiếp bằng code thông thường trong assembler, đó lại là một đường thực thi khác cần kiểm tra.

## 5. Ví dụ sai: truy vấn repository bên trong assembler

Một cách triển khai dễ gây N+1 là inject repository vào assembler:

~~~java
@Component
class OrderModelAssembler {

    private final CustomerRepository customerRepository;
    private final OrderLineRepository lineRepository;

    OrderModelAssembler(
            CustomerRepository customerRepository,
            OrderLineRepository lineRepository) {
        this.customerRepository = customerRepository;
        this.lineRepository = lineRepository;
    }

    OrderModel toModel(Order order) {

        Customer customer = customerRepository
            .findById(order.getCustomer().getId())
            .orElseThrow();

        List<OrderLine> lines =
            lineRepository.findByOrderId(order.getId());

        return new OrderModel(
            order.getId(),
            order.getNumber(),
            customer.getDisplayName(),
            lines.stream()
                .map(this::toItemModel)
                .toList()
        );
    }
}
~~~

Khi `toModel()` chạy cho từng đơn hàng, assembler thực hiện hai repository calls. Với 30 đơn hàng, riêng hai lời gọi đó có thể tạo 60 truy vấn, chưa kể truy vấn ban đầu và việc tải product.

Assembler nên tập trung vào chuyển dữ liệu đã có thành representation và tạo link. Việc quyết định dữ liệu nào cần tải nên nằm ở query/service layer, nơi có thể nhìn thấy toàn bộ nhu cầu của endpoint.

## 6. Fetch plan phải xuất phát từ representation

Trước khi sửa query, hãy xác định chính xác response cần những dữ liệu nào.

Ví dụ endpoint danh sách đơn hàng cần:

| Dữ liệu trong representation | Nguồn |
|---|---|
| id, number, status, total | orders |
| customer.id, customer.displayName | customers |
| item.id, item.quantity, item.unitPrice | order_lines |
| item.productName | products |
| self, customer, items links | URI được tạo từ route và ID |

Từ danh sách này, thiết kế fetch plan chỉ tải những association cần thiết. Không tải toàn bộ entity graph chỉ vì entity có nhiều quan hệ.

Một nguyên tắc hữu ích là: **mỗi use case đọc có một kế hoạch truy vấn riêng**. Endpoint danh sách, endpoint chi tiết và endpoint báo cáo có thể cần các tập dữ liệu khác nhau dù cùng đọc bảng Order.

## 7. Giải pháp 1: fetch join cho association phù hợp

JPQL fetch join yêu cầu persistence provider tải association trong cùng truy vấn với entity gốc.

Ví dụ khi cần customer và một collection items cho một tập đơn hàng có kích thước giới hạn:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("""
        select distinct o
        from Order o
        left join fetch o.customer
        left join fetch o.lines line
        left join fetch line.product
        where o.status = :status
        """)
    List<Order> findForRepresentation(
        @Param("status") OrderStatus status
    );
}
~~~

Truy vấn này lấy order, customer, line và product trong một câu SQL join. Assembler có thể duyệt các association đã được khởi tạo mà không phát sinh truy vấn riêng cho từng đơn hàng.

Dùng `left join fetch` khi đơn hàng vẫn cần xuất hiện dù chưa có customer hoặc chưa có item. Dùng `join fetch` khi association bắt buộc phải tồn tại và muốn loại bỏ các bản ghi không có association đó.

`distinct` giúp diễn đạt kết quả entity gốc không trùng lặp trong JPQL khi collection join tạo nhiều dòng kết quả cho cùng một order. Dù vậy, SQL result vẫn có thể chứa nhiều dòng vì mỗi line item là một dòng join.

### Không fetch join nhiều collection song song một cách tùy tiện

Giả sử Order có cả `lines` và `payments`. Fetch cả hai collection trong một query có thể tạo tích Descartes giữa hai tập phần tử.

Một đơn có 5 lines và 4 payments có thể tạo 20 dòng kết quả cho cùng một đơn hàng. Khi số collection và số phần tử tăng, lượng dữ liệu trung gian có thể lớn hơn rất nhiều so với dữ liệu cuối cùng cần serialize.

Hibernate cũng cảnh báo việc fetch nhiều association dạng to-many song song có thể gây Cartesian product và hiệu năng kém. Hãy cân nhắc DTO projection hoặc tải từng collection bằng truy vấn theo tập ID.

## 8. Giải pháp 2: EntityGraph cho fetch plan theo use case

Spring Data JPA hỗ trợ `@EntityGraph` để chỉ định association cần tải cho một repository method.

Ví dụ:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    Optional<Order> findWithDetailsById(Long id);
}
~~~

Khi cần một representation chi tiết cho một đơn hàng, entity graph giúp khai báo rõ những association mà use case cần.

Có thể dùng named entity graph được định nghĩa trên entity hoặc dynamic graph qua `attributePaths`. Các path lồng nhau như `lines.product` giúp mô tả association ở nhiều cấp.

EntityGraph mô tả fetch plan cho persistence provider. Nó không bảo đảm trong mọi trường hợp rằng tất cả dữ liệu sẽ được tải bằng đúng một câu SQL. Hãy kiểm tra SQL thực tế, đặc biệt khi graph có collection lớn hoặc nhiều association to-many.

EntityGraph thường phù hợp với endpoint chi tiết hoặc một tập association có giới hạn. Với danh sách có phân trang và nhiều collection, hãy xem xét chiến lược tải hai bước ở phần sau.

## 9. Giải pháp 3: DTO projection để chỉ lấy dữ liệu representation cần

Nếu assembler chỉ cần một số field, không nhất thiết phải tải entity đầy đủ. Spring Data JPA hỗ trợ DTO projection để query trả về object chứa đúng dữ liệu cần thiết.

Khai báo các read model:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;

public record OrderSummaryRow(
    Long id,
    String number,
    Long customerId,
    String customerName,
    BigDecimal total
) {}
~~~

~~~java
package com.example.orders.read;

import java.math.BigDecimal;

public record OrderLineRow(
    Long orderId,
    Long id,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

Repository tải phần summary bằng constructor expression:

~~~java
public interface OrderReadRepository
        extends Repository<Order, Long> {

    @Query("""
        select new com.example.orders.read.OrderSummaryRow(
            o.id,
            o.number,
            c.id,
            c.displayName,
            o.total
        )
        from Order o
        left join o.customer c
        where o.status = :status
        """)
    List<OrderSummaryRow> findSummariesByStatus(
        @Param("status") OrderStatus status
    );
}
~~~

Repository khác tải toàn bộ line item cho danh sách ID:

~~~java
public interface OrderLineReadRepository
        extends Repository<OrderLine, Long> {

    @Query("""
        select new com.example.orders.read.OrderLineRow(
            line.order.id,
            line.id,
            product.name,
            line.quantity,
            line.unitPrice
        )
        from OrderLine line
        join line.product product
        where line.order.id in :orderIds
        order by line.order.id, line.id
        """)
    List<OrderLineRow> findRowsByOrderIds(
        @Param("orderIds") Collection<Long> orderIds
    );
}
~~~

Hai query có thể lấy dữ liệu cho toàn bộ danh sách. Query đầu lấy summary và customer; query thứ hai lấy tất cả line item cùng product name theo danh sách order ID.

Kết quả không cần khởi tạo entity graph và assembler không cần gọi getter lazy.

## 10. Gom dữ liệu theo ID thay vì truy vấn từng order

Sau khi có hai tập kết quả, service gom line item theo order ID.

~~~java
Map<Long, List<OrderLineView>> itemsByOrder =
    lineRows.stream().collect(
        Collectors.groupingBy(
            OrderLineRow::orderId,
            LinkedHashMap::new,
            Collectors.mapping(
                row -> new OrderLineView(
                    row.id(),
                    row.productName(),
                    row.quantity(),
                    row.unitPrice()
                ),
                Collectors.toList()
            )
        )
    );
~~~

Sau đó kết hợp với summary:

~~~java
List<OrderView> views = summaries.stream()
    .map(row -> {
        CustomerSummaryView customer =
            row.customerId() == null
                ? null
                : new CustomerSummaryView(
                    row.customerId(),
                    row.customerName()
                );

        return new OrderView(
            new OrderSummaryView(
                row.id(),
                row.number(),
                row.total()
            ),
            customer,
            itemsByOrder.getOrDefault(row.id(), List.of())
        );
    })
    .toList();
~~~

Số query không còn phụ thuộc tuyến tính vào số đơn hàng. Với danh sách có dữ liệu, service thực hiện một query lấy summary và một query lấy line items.

Nếu danh sách rỗng, bỏ qua query thứ hai. Không gọi query `IN (...)` với danh sách ID rỗng vì cú pháp và hành vi có thể khác nhau giữa provider hoặc database.

## 11. Giải pháp 4: tải hai bước khi endpoint có phân trang

Fetch join collection trực tiếp cùng query phân trang có thể làm database trả nhiều dòng cho mỗi entity gốc. Một order có nhiều line item sẽ xuất hiện trên nhiều dòng SQL, nên provider không thể áp dụng giới hạn trang đơn giản như khi chỉ tải root entity.

Hibernate thường phải lấy toàn bộ kết quả join rồi phân trang trong bộ nhớ hoặc phát cảnh báo, tùy cấu hình và phiên bản. Nếu giới hạn SQL được áp dụng trực tiếp trên các dòng join, collection của một order còn có nguy cơ bị cắt cụt. Đây là lý do cần cẩn trọng với `Page<Order>` kết hợp collection fetch join.

Một chiến lược an toàn hơn là:

1. Query trang ID hoặc summary của các order.
2. Lấy toàn bộ association cần thiết cho tập ID của trang bằng một query thứ hai.
3. Gom dữ liệu theo order ID.
4. Ánh xạ thành view model theo đúng thứ tự trang ban đầu.

Với DTO projection, query summary có thể trả `Page<OrderSummaryRow>`:

~~~java
@Query(
    value = """
        select new com.example.orders.read.OrderSummaryRow(
            o.id,
            o.number,
            c.id,
            c.displayName,
            o.total
        )
        from Order o
        left join o.customer c
        where o.status = :status
        """,
    countQuery = """
        select count(o)
        from Order o
        where o.status = :status
        """
)
Page<OrderSummaryRow> findPageSummaries(
    @Param("status") OrderStatus status,
    Pageable pageable
);
~~~

Service chỉ tải line items cho các ID trong trang:

~~~java
@Transactional(readOnly = true)
public Page<OrderView> findPage(
        OrderStatus status,
        Pageable pageable) {

    Page<OrderSummaryRow> page =
        orderReadRepository.findPageSummaries(status, pageable);

    if (page.isEmpty()) {
        return page.map(row -> toView(row, List.of()));
    }

    List<Long> ids = page.getContent().stream()
        .map(OrderSummaryRow::id)
        .toList();

    Map<Long, List<OrderLineView>> itemsByOrder =
        loadItemsByOrder(ids);

    return page.map(row ->
        toView(
            row,
            itemsByOrder.getOrDefault(row.id(), List.of())
        )
    );
}
~~~

Trong ví dụ này, query summary và query items là hai truy vấn dữ liệu chính. `Page` có thể cần thêm count query để tính tổng số phần tử; vì vậy tổng số SQL thường là hai hoặc ba tùy việc Spring Data có cần chạy count query hay không.

Nếu client chỉ cần biết có trang tiếp theo hay không mà không cần tổng số phần tử, cân nhắc `Slice` để tránh count query.

Khi query thứ hai dùng `where id in :ids`, kết quả không nhất thiết giữ thứ tự ID đầu vào. Hãy giữ thứ tự từ `page.getContent()` khi ghép dữ liệu, như đoạn `page.map(...)` ở trên.

## 12. Giải pháp 5: batch fetching khi không thể join tất cả association

Có trường hợp join fetch tạo result set quá lớn hoặc nhiều collection khiến Cartesian product không thể chấp nhận. Hibernate cung cấp batch fetching để gom nhiều association lazy vào một truy vấn có `IN`.

Ví dụ:

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
class Order {

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Hoặc cấu hình mặc định cho các association lazy:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi ứng dụng duyệt nhiều association chưa khởi tạo trong cùng persistence context, Hibernate có thể tải một nhóm association trong một query thay vì mỗi association một query.

Nếu có N collection và batch size B, số query tải collection thường gần với:

\[
Q_{\text{batch}} \approx \left\lceil \frac{N}{B} \right\rceil
\]

Cộng thêm query lấy entity gốc và các association khác.

Batch fetching giúp giảm round-trip, nhưng không làm mọi association được tải bằng một query duy nhất. Đây là biện pháp giảm tác động của N+1 khi fetch join hoặc projection không phù hợp. Hãy đo số truy vấn và kích thước batch với dữ liệu thực tế.

`@BatchSize` là annotation riêng của Hibernate, không thuộc chuẩn JPA. Nó có tác dụng với association lazy và persistence context còn hoạt động trong lúc các association được truy cập.

## 13. Không dùng EAGER để chữa N+1

Đổi association từ LAZY sang EAGER thường không phải cách sửa phù hợp.

`FetchType.EAGER` yêu cầu provider tải association khi entity được nạp, nhưng không bắt buộc provider phải dùng join trong cùng câu SQL. Provider có thể chạy truy vấn phụ cho từng association và vẫn tạo N+1.

EAGER trên entity còn khiến những use case không cần association cũng phải tải dữ liệu, làm object graph lớn và khó dự đoán.

Giữ mapping mặc định theo hướng lazy cho association phù hợp, rồi định nghĩa fetch plan theo từng query hoặc use case bằng fetch join, EntityGraph, projection hoặc batch fetching.

## 14. Tách transaction đọc dữ liệu khỏi quá trình serialize

Một lỗi thường gặp là trả JPA entity từ controller và để Jackson đọc association lazy trong lúc serialize response.

Nếu Open Session in View được bật, persistence context có thể còn mở trong giai đoạn serialize. Request vẫn thành công nhưng SQL tiếp tục phát sinh sau khi controller đã trả về.

Cấu hình:

~~~properties
spring.jpa.open-in-view=false
~~~

giúp phát hiện sớm trường hợp controller trả entity còn association chưa được tải. Khi đó, hãy tạo DTO/view model trong service transaction.

Ví dụ:

~~~java
@Service
class OrderQueryService {

    @Transactional(readOnly = true)
    public List<OrderView> findViews(OrderStatus status) {
        // Query các dữ liệu cần thiết và tạo OrderView ở đây.
    }
}
~~~

`readOnly = true` không tự loại bỏ N+1. Nó chỉ đánh dấu transaction đọc và có thể giúp persistence provider tối ưu một số thao tác. Fetch plan vẫn phải được thiết kế đúng.

Khi service trả về DTO thuần, serializer không còn cần mở lazy association. Assembler có thể chạy sau transaction mà không phát sinh SQL.

## 15. Tạo HAL embedded từ dữ liệu đã tải

Spring HATEOAS cung cấp `HalModelBuilder` để xây dựng representation theo cấu trúc HAL. Builder có thể nhúng một object hoặc collection dưới relation được chỉ định.

Ví dụ model view:

~~~java
public record OrderSummaryView(
    Long id,
    String number,
    BigDecimal total
) {}

public record CustomerSummaryView(
    Long id,
    String displayName
) {}

public record OrderLineView(
    Long id,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderView(
    OrderSummaryView summary,
    CustomerSummaryView customer,
    List<OrderLineView> items
) {}
~~~

Assembler chỉ nhận `OrderView` đã có dữ liệu:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderHalAssembler implements
        RepresentationModelAssembler<OrderView, RepresentationModel<?>> {

    @Override
    public RepresentationModel<?> toModel(OrderView order) {

        Long id = order.summary().id();

        Link self = linkTo(
            methodOn(OrderController.class).one(id)
        ).withSelfRel();

        Link customerLink = linkTo(
            methodOn(OrderController.class).customer(id)
        ).withRel("customer");

        Link itemsLink = linkTo(
            methodOn(OrderController.class).items(id)
        ).withRel("items");

        HalModelBuilder builder = HalModelBuilder
            .halModelOf(order.summary())
            .link(self)
            .link(itemsLink)
            .embed(order.items(), LinkRelation.of("items"));

        if (order.customer() != null) {
            builder.preview(order.customer())
                .forLink(customerLink);
        }

        return builder.build();
    }
}
~~~

`preview(...).forLink(...)` tạo customer preview trong `_embedded` đồng thời công bố link relation tương ứng. `embed(collection, relation)` đưa danh sách items vào `_embedded` dưới relation `items`.

Assembler không gọi repository và không đọc JPA association. Nó chỉ chuyển dữ liệu đã tải thành HAL model và tạo URI. Nhờ đó, số truy vấn database không tăng theo số model được tạo.

## 16. Dùng CollectionModel và RepresentationModelAssembler đúng phạm vi

Với một collection representation đơn giản, `RepresentationModelAssembler` cung cấp `toModel()` và `toCollectionModel()` để chuyển domain object thành representation model.

~~~java
CollectionModel<OrderModel> model =
    orderModelAssembler.toCollectionModel(orders);
~~~

Điều này giúp chuẩn hóa việc tạo item model và collection links. Tuy nhiên, `toCollectionModel()` không tự tối ưu truy vấn database. Nếu `toModel()` đọc association lazy, N+1 vẫn xảy ra cho từng phần tử.

Hãy đảm bảo input của assembler đã được tải theo fetch plan phù hợp hoặc đã được chuyển thành DTO. Assembler là lớp mapping hypermedia, không nên là nơi thực hiện query per item.

Với HAL, `HalModelBuilder` phù hợp khi cần kiểm soát rõ `_embedded` và preview. Với các collection resource tiêu chuẩn, `CollectionModel` và assembler thường đơn giản hơn.

## 17. Phân biệt embedded data với link-only representation

Không phải quan hệ nào cũng cần nhúng đầy đủ dữ liệu.

Có thể chỉ cung cấp link customer:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/orders/42/customer"
    }
  }
}
~~~

Client chỉ tải customer khi thực sự cần. Cách này giảm số dữ liệu phải truy vấn và kích thước response, đổi lại client có thể cần thêm HTTP request.

Một preview nhỏ thường cân bằng tốt hơn:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/orders/42/customer"
    }
  },
  "_embedded": {
    "customer": {
      "displayName": "Nguyen Van An"
    }
  }
}
~~~

Chỉ nhúng field client cần để hiển thị hoặc ra quyết định. Không cần nhúng toàn bộ customer entity, địa chỉ, lịch sử thanh toán và mọi association của customer vào từng đơn hàng.

## 18. Kiểm tra N+1 bằng Hibernate Statistics

Đừng chỉ đánh giá query plan bằng cách đọc code. Hãy đo số SQL được chuẩn bị trong một integration test hoặc khi chạy request thực tế.

Có thể bật Hibernate statistics trong môi trường test:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Ví dụ integration test dùng Hibernate `Statistics`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderRepresentationQueryTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    EntityManager entityManager;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Test
    void createsEmbeddedRepresentationsWithoutNPlusOne() throws Exception {

        // Fixture được tạo trước đó trong test.
        entityManager.flush();
        entityManager.clear();

        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.clear();

        mockMvc.perform(
                get("/orders")
                    .param("status", "PAID")
                    .param("page", "0")
                    .param("size", "20")
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk());

        long statementCount =
            statistics.getPrepareStatementCount();

        assertThat(statementCount).isLessThanOrEqualTo(3L);
    }
}
~~~

MockMvc chạy toàn bộ MVC request, gồm service query, assembler và serialization. Với fetch plan hai bước, ba truy vấn dự kiến là query trang summary, query line items cho toàn bộ ID và count query nếu Spring Data cần chạy. Nếu số truy vấn tăng theo số order hoặc line item, hãy kiểm tra lại assembler và fetch plan.

Statistics là dữ liệu cấp SessionFactory. Nếu test chạy song song, các test khác có thể làm thay đổi bộ đếm. Hãy cô lập test query count, tránh chạy song song với test sử dụng cùng SessionFactory hoặc dùng công cụ theo dõi SQL theo request/thread.

## 19. Kiểm tra số truy vấn theo kích thước collection

Một test chỉ xác nhận endpoint trả HTTP 200 không thể phát hiện N+1. Nên kiểm tra số truy vấn khi số phần tử tăng.

Ví dụ kỳ vọng:

| Số order | Thiết kế N+1 | Thiết kế tải theo tập |
|---:|---:|---:|
| 5 | 6 hoặc nhiều hơn | Khoảng 2–3 |
| 20 | 21 hoặc nhiều hơn | Khoảng 2–3 |
| 100 | 101 hoặc nhiều hơn | Khoảng 2–3 |

Con số cụ thể phụ thuộc count query, association và batch size. Điều cần xác nhận là query count không tăng một lần cho mỗi order hoặc mỗi item.

Ngoài query count, hãy quan sát:

- Tổng thời gian database.
- Số dòng trả về từ join.
- Dung lượng response.
- Thời gian mapping và serialization.
- Bộ nhớ tiêu thụ khi tạo embedded collection.
- Số request tiếp theo mà client phải gọi nếu chuyển từ embed sang link-only.

Một query duy nhất trả hàng trăm nghìn dòng do Cartesian product không phải là tối ưu. Mục tiêu là giảm round-trip mà vẫn giữ result set ở kích thước hợp lý.

## 20. Các dấu hiệu cho thấy fetch plan chưa phù hợp

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Query count tăng theo số order | Association lazy được tải trong vòng lặp | Kiểm tra getter trong assembler |
| Query count tăng theo số line | Product hoặc association của line bị tải riêng | Kiểm tra nested association |
| Response chậm dù query count thấp | Join trả quá nhiều dòng hoặc response lớn | Xem execution plan và payload |
| Bộ nhớ tăng khi tải một trang | Nhúng collection quá lớn hoặc load nhiều entity | Giới hạn embedded và dùng pagination |
| Lỗi LazyInitializationException khi tắt OSIV | Mapping đọc association ngoài transaction | Tạo DTO trong service transaction |
| Query phát sinh sau khi controller return | Jackson hoặc processor đọc lazy property | Trả representation DTO đã hoàn chỉnh |
| Dữ liệu item bị lặp | Join nhiều collection tạo Cartesian product | Tách query hoặc group theo ID |
| Phân trang trả số phần tử bất thường | Fetch join collection kết hợp limit/offset | Dùng page ID/summary rồi tải association |

## 21. Chọn chiến lược theo loại endpoint

| Endpoint | Chiến lược thường phù hợp |
|---|---|
| Chi tiết một order | EntityGraph hoặc fetch join cho association cần thiết |
| Danh sách nhỏ, không phân trang | Fetch join một collection phù hợp hoặc DTO projection |
| Danh sách lớn có phân trang | Page summary + query items theo tập ID |
| Nhiều collection to-many | Tách query, DTO projection hoặc batch fetching |
| Embedded chỉ gồm vài field | DTO projection |
| Association lazy không thể join hợp lý | Batch fetching như biện pháp giảm round-trip |
| Dữ liệu thay đổi theo workflow | Query/read model riêng cho từng representation |

Không có một annotation duy nhất giải quyết mọi N+1. Hãy chọn theo số lượng entity, cardinality của association, yêu cầu phân trang và lượng dữ liệu client thực sự cần.

## 22. Checklist khi tạo embedded representation

Trước khi hoàn tất một endpoint Spring HATEOAS có embedded resources, hãy kiểm tra:

1. Đã liệt kê tất cả field và embedded relation cần có trong response.
2. Đã xác định association nào là to-one và association nào là to-many.
3. Assembler không gọi repository cho từng entity.
4. Fetch plan chỉ tải association cần thiết.
5. Không fetch join nhiều collection song song nếu có nguy cơ Cartesian product.
6. Không phân trang trực tiếp trên query fetch join collection.
7. Với trang lớn, đã cân nhắc DTO projection hoặc tải hai bước theo ID.
8. Association lazy được truy cập trong transaction có kiểm soát.
9. Serializer nhận DTO/view model thay vì JPA entity graph chưa hoàn chỉnh.
10. Query count được kiểm tra với số lượng entity đủ lớn.
11. Payload size và thời gian serialization cũng được đo.
12. Relation và link vẫn được tạo đúng sau khi tách query khỏi assembler.

N+1 khi tạo embedded thường xuất phát từ việc assembler hoặc serializer truy cập association chưa được tải. Khi fetch plan được thiết kế theo representation, service có thể lấy dữ liệu theo tập, nhóm theo ID và chuyển thành DTO trước khi Spring HATEOAS xây HAL model. Cách làm này giữ cho số truy vấn ổn định khi danh sách lớn lên, đồng thời giúp kiểm soát payload, pagination và cấu trúc hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — HAL ModelBuilder](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.building)
- [Spring HATEOAS API — HalModelBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html)
- [Spring HATEOAS API — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring Data JPA — EntityGraph](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/EntityGraph.html)
- [Spring Data — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM User Guide — Association fetching and batch fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/)
- [Hibernate ORM — A Short Guide, Association fetching](https://docs.hibernate.org/stable/orm/introduction/html_single/#fetching)
