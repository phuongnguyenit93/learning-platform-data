# Projection lồng nhau và phạm vi dữ liệu liên quan

Trong chương **Projection interface** của Spring Data Commons (`SPRING_DATA_COMMONS`), một projection có thể trả về projection khác để mô tả phần dữ liệu cần đọc ở đối tượng liên quan. Ví dụ, màn hình đơn hàng cần số đơn, tên khách hàng và thành phố, nhưng không cần toàn bộ thông tin khách hàng.

Điều cần phân biệt là **cấu trúc dữ liệu mà caller nhìn thấy** và **phạm vi dữ liệu mà store thực sự truy vấn, tải và giữ lại**. Một cây interface nhỏ không tự bảo đảm một câu truy vấn nhỏ, một lần truy cập store hay một ảnh chụp lịch sử của dữ liệu.

Bài học đi từ hợp đồng proxy chung của Commons tới ví dụ repository. Các chi tiết join và giao dịch được minh họa bằng Spring Data JPA; phần đối chiếu document store không giả định mọi module có cùng cơ chế tải dữ liệu.

## 1. Nested projection biểu diễn một đường đi qua các thuộc tính

Giả sử mô hình nghiệp vụ có các thuộc tính sau:

| Kiểu | Thuộc tính liên quan |
| --- | --- |
| `PurchaseOrder` | `id`, `tenantId`, `orderNumber`, `customer`, `lines`. |
| `Customer` | `id`, `tenantId`, `name`, `email`, `address`. |
| `Address` | `city`, `street`, `postalCode`. |
| `OrderLine` | `id`, `productName`, `quantity`, `unitPrice`. |

Trong ví dụ JPA, `customer` là quan hệ một khách hàng của đơn, `address` là giá trị được nhúng vào khách hàng, còn `lines` là collection dòng hàng. Mapping và cấu hình repository của ứng dụng được giả định đã có.

Một projection chỉ đọc phần cần cho danh sách đơn:

```java
public interface OrderSummaryView {

    Long getId();

    String getOrderNumber();

    CustomerBrief getCustomer();

    interface CustomerBrief {

        String getName();

        AddressBrief getAddress();
    }

    interface AddressBrief {

        String getCity();
    }
}
```

Đường truy cập của caller là:

```text
OrderSummaryView
  ├─ id
  ├─ orderNumber
  └─ customer -> CustomerBrief
       ├─ name
       └─ address -> AddressBrief
            └─ city
```

Các tên `customer`, `address` và `city` phải khớp thuộc tính ở đúng cấp của nguồn. Việc đặt `CustomerBrief` và `AddressBrief` bên trong interface chỉ là cách tổ chức kiểu Java; các interface ở tệp riêng cũng có thể biểu diễn cùng hợp đồng.

## 2. Proxy lồng nhau được tạo trên giá trị thuộc tính

Với interface projection, Spring tạo đối tượng proxy triển khai interface đọc dữ liệu. Khi getter liên quan trả về một giá trị cần projection, giá trị đó có thể tiếp tục được bọc bằng proxy của interface con.

Về mặt khái niệm:

```text
orderView.getCustomer()
  -> đọc thuộc tính customer của nguồn backing
  -> nhận giá trị customer
  -> biểu diễn giá trị đó bằng CustomerBrief

customerView.getAddress()
  -> đọc thuộc tính address của nguồn backing
  -> biểu diễn bằng AddressBrief
```

Đây là cơ chế projection đệ quy được mô tả trong [Spring Data Commons: Interface-based Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

Caller không cần tự viết lớp triển khai `CustomerBrief`. Tuy nhiên, proxy không tự tạo ra quan hệ còn thiếu trong dữ liệu nguồn và không mặc nhiên có một truy vấn độc lập cho mỗi interface con.

Trong ví dụ, các getter tương ứng với thuộc tính của domain, phù hợp với cách khai báo closed projection. Khả năng tối ưu việc chọn trường vẫn thuộc module thực thi query.

Cần tách các mốc thời gian:

- Proxy có thể được tạo khi một getter được gọi.
- Dữ liệu backing có thể đã được tải trước đó.
- Nếu backing chứa một quan hệ chưa được khởi tạo, việc truy cập có thể cần thêm dữ liệu theo cơ chế của store.

Không suy ra thời điểm truy vấn chỉ từ thời điểm nhìn thấy proxy con.

## 3. Khai báo repository không đồng nghĩa đã chọn mọi cột của cây

Với module có hỗ trợ projection tương ứng, một derived query có thể khai báo:

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface OrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    List<OrderSummaryView> findByTenantIdOrderByIdAsc(
        String tenantId
    );
}
```

Trong ví dụ JPA, `PurchaseOrder` là entity đã mapping, `Long` là kiểu ID và thứ tự theo ID giúp kết quả có thứ tự xác định. Đây là method query riêng; không thay kiểu trả về của một method CRUD nền để giả định rằng nó tự biến thành query projection.

Caller có thể đọc:

```java
List<OrderSummaryView> orders =
    repository.findByTenantIdOrderByIdAsc("ACME");

for (OrderSummaryView order : orders) {
    System.out.println(order.getOrderNumber());

    OrderSummaryView.CustomerBrief customer =
        order.getCustomer();

    if (customer != null) {
        System.out.println(customer.getName());
    }
}
```

Đoạn code chứng minh hợp đồng kiểu ở tầng Java. Nó chưa chứng minh câu SQL chỉ chọn `id`, `orderNumber`, `name` và `city`.

Theo phần derived queries trong [Spring Data JPA: Using Projections with JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa), việc giới hạn selection áp dụng cho thuộc tính cấp đầu của entity đích; thuộc tính lồng nhau cần join có thể khiến toàn bộ thuộc tính liên quan được chọn và materialize.

Vì vậy, không viết cam kết hiệu năng chỉ bằng cách đếm số getter trong interface.

## 4. Ví dụ với Map để nhìn rõ cấu trúc proxy

Có thể minh họa cơ chế projection bằng một nguồn Map, không cần repository hay cơ sở dữ liệu:

```java
import java.util.Map;

import org.springframework.data.projection.ProjectionFactory;
import org.springframework.data.projection.SpelAwareProxyProjectionFactory;

public class NestedProjectionDemo {

    public static void main(String[] args) {
        Map<String, Object> source = Map.of(
            "id", 31L,
            "orderNumber", "PO-0031",
            "customer", Map.of(
                "name", "Lan",
                "email", "lan@example.test",
                "address", Map.of(
                    "city", "Da Nang",
                    "street", "Example Street"
                )
            )
        );

        ProjectionFactory factory =
            new SpelAwareProxyProjectionFactory();

        OrderSummaryView view = factory.createProjection(
            OrderSummaryView.class,
            source
        );

        System.out.println(view.getOrderNumber());
        System.out.println(view.getCustomer().getName());
        System.out.println(
            view.getCustomer().getAddress().getCity()
        );
    }
}
```

Kết quả dự kiến:

```text
PO-0031
Lan
Da Nang
```

Ví dụ giả định `OrderSummaryView` đã được khai báo cùng package hoặc import phù hợp. Nó sử dụng `createProjection` của [ProjectionFactory](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/projection/ProjectionFactory.html).

Nhận xét từ chính dữ liệu ví dụ:

- Source vẫn chứa `email` và `street`.
- Interface chỉ cho caller truy cập `name` và `city` qua các getter đã khai báo.
- Tạo proxy không xóa hai trường còn lại khỏi Map.
- Không có SQL hay query MongoDB nào được thực hiện trong ví dụ này.

Đây là cách phân biệt việc giới hạn giao diện đọc với việc giới hạn dữ liệu đã nằm trong bộ nhớ. Nguồn Map chỉ minh họa mapping và proxy, không kiểm chứng fetch plan của repository.

## 5. Quan hệ null và giá trị null cần được xử lý theo từng cấp

Một đơn có thể chưa có khách hàng; một khách hàng có thể chưa có địa chỉ. Dòng sau không thể hiện hợp đồng null an toàn:

```java
String city = order.getCustomer()
    .getAddress()
    .getCity();
```

Có thể diễn đạt rõ từng cấp:

```java
OrderSummaryView.CustomerBrief customer =
    order.getCustomer();

OrderSummaryView.AddressBrief address =
    customer == null ? null : customer.getAddress();

String city = address == null ? null : address.getCity();
```

Hoặc dùng `Optional` ở tầng tiêu thụ:

```java
import java.util.Optional;

String city = Optional.ofNullable(order.getCustomer())
    .map(OrderSummaryView.CustomerBrief::getAddress)
    .map(OrderSummaryView.AddressBrief::getCity)
    .orElse("(chua co thanh pho)");
```

Spring Data cũng hỗ trợ một số nullable wrapper cho getter, chẳng hạn `Optional<String>`. Nếu chọn kiểu wrapper trong interface, caller phải dùng đúng hợp đồng đó; đừng vừa khai báo `String` vừa giả định framework tự trả `Optional`.

Cần phân biệt ba tình huống:

| Hiện tượng | Điều phải xác định |
| --- | --- |
| Nguồn backing có `customer = null` | Getter con không thể cung cấp một khách hàng thực. |
| Có customer nhưng `city = null` | Thiếu giá trị ở cấp địa chỉ, không đồng nghĩa thiếu toàn bộ customer. |
| Đơn không xuất hiện trong kết quả | Có thể do điều kiện query hoặc join, chưa phải vấn đề null của proxy. |

Nếu query dùng inner join, một root không có quan hệ phù hợp có thể bị loại trước khi projection được tạo. Projection không tự đổi inner join thành left join để giữ root.

Nếu một getter không có giá trị như mong đợi, còn cần kiểm tra tên thuộc tính, alias và mapping của query. Không dùng null làm bằng chứng duy nhất rằng dữ liệu nghiệp vụ thật sự không tồn tại.

## 6. Phạm vi dữ liệu liên quan gồm nhiều quyết định độc lập

Với yêu cầu “lấy đơn hàng và khách hàng tóm tắt”, ít nhất có bốn câu hỏi:

| Phạm vi | Ví dụ câu hỏi |
| --- | --- |
| Root được chọn | Những đơn nào thuộc tenant và khớp điều kiện? |
| Thuộc tính được trình bày | Caller có đọc được email hoặc địa chỉ đầy đủ không? |
| Quan hệ được tải | Store có tải customer, address hoặc lines không? |
| Ý nghĩa thời gian của dữ liệu | Đây là địa chỉ khách hàng hiện tại hay địa chỉ tại lúc đặt đơn? |

Projection chủ yếu biểu diễn phần dữ liệu được đọc qua một kiểu kết quả. Các quyết định còn lại phải được thiết kế bằng query, mapping và mô hình nghiệp vụ.

### Bộ lọc root không tự lọc collection con

Giả sử nghiệp vụ chọn “các đơn có ít nhất một dòng hàng đang chờ xử lý”. Điều kiện tồn tại một dòng phù hợp có thể chọn root, nhưng không có nghĩa `getLines()` tự chỉ trả các dòng đang chờ.

Nếu màn hình chỉ được nhận những dòng khớp điều kiện, cần query hoặc bước lắp ghép dữ liệu có hợp đồng đó. Việc đổi kiểu phần tử từ entity sang `LineView` chỉ đổi phần thuộc tính được đọc của mỗi phần tử.

### Dữ liệu hiện tại không tự trở thành snapshot lịch sử

Nếu đường projection là `order.customer.address.city`, kết quả phản ánh giá trị mà mô hình và query đọc từ customer.

Giả sử khách hàng đổi địa chỉ sau khi đặt đơn. Muốn hiển thị nơi giao hàng tại thời điểm đặt đơn, domain có thể cần một giá trị `shippingAddress` được lưu trên đơn. Thêm một nested interface không tự tạo ra dữ liệu lịch sử chưa được lưu.

### Phạm vi tenant và quyền đọc thuộc query, nghiệp vụ

Getter ít trường không thay thế điều kiện chọn root hay việc kiểm soát quyền đọc dữ liệu liên quan. Nếu hệ thống có tenant, quan hệ giữa đơn và khách hàng phải tuân thủ ràng buộc tenant của ứng dụng.

Việc không khai báo `getEmail()` giúp hạn chế hợp đồng đọc của view; nó không chứng minh email chưa từng được tải hoặc mọi caller đã được cấp đúng quyền.

## 7. Collection lồng nhau làm tăng cả số phần tử và phạm vi tải

Một projection chi tiết có thể đọc collection:

```java
import java.util.List;

public interface OrderDetailView {

    Long getId();

    String getOrderNumber();

    List<LineView> getLines();

    interface LineView {

        String getProductName();

        Integer getQuantity();
    }
}
```

Trong cơ chế projection của Commons, kết quả collection có thể được chuyển thành collection chứa projection của từng phần tử. Một minh họa implementation là [ProjectingMethodInterceptor, Spring Data Commons 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/projection/ProjectingMethodInterceptor.java).

Tuy nhiên, hỗ trợ chuyển kiểu của từng phần tử không bảo đảm mọi module có thể tối ưu một query nested collection giống nhau.

Cần xác định:

- Nguồn đã có toàn bộ collection hay sẽ tải khi getter được gọi?
- Một root có tối đa bao nhiêu phần tử con?
- Thứ tự của collection do đâu quyết định?
- Query có trả đúng những phần tử con mà use case cần không?

Tên kiểu `List<LineView>` không tự thêm giới hạn số dòng hàng và cũng không tự yêu cầu `ORDER BY` trong store.

Ví dụ một trang có 20 đơn, mỗi đơn có 1.000 dòng: nếu tất cả collection được tải thì có thể có 20.000 phần tử con, dù trang root chỉ có 20 phần tử.

Nếu join hai collection độc lập, số hàng trung gian còn có thể tăng theo tổ hợp. Một đơn có 3 dòng và 4 nhãn có thể tạo 12 tổ hợp trong một truy vấn join cả hai collection, tùy hình dạng query.

Đối với màn hình danh sách, thường nên dùng view tóm tắt, số lượng hoặc tổng hợp cần thiết. Chi tiết collection có thể được truy vấn bằng endpoint hoặc query riêng có giới hạn phù hợp.

Không suy ra rằng phân trang root cũng phân trang từng collection con.

## 8. Fetch plan và số truy vấn phải được xem tại module store

### Trường hợp quan hệ trong JPA

Một nested projection có thể đọc từ dữ liệu đã nằm trong tuple, entity hoặc đối tượng backing khác, tùy cách query được thực thi.

Nếu một quan hệ cần tải thêm khi getter được gọi, việc duyệt nhiều root có thể làm phát sinh nhiều lượt truy cập. Một kiểu hình cần xem xét là:

```text
1 query chọn danh sách đơn
  + truy cập dữ liệu customer cho từng nhóm hoặc từng đơn
  + truy cập lines khi đọc chi tiết
```

Không khẳng định mọi nested projection đều gây N+1, cũng không khẳng định proxy luôn loại bỏ N+1. Cache, fetch plan, query cụ thể và mapping quan hệ đều ảnh hưởng kết quả.

Khi đánh giá JPA, cần quan sát câu truy vấn và dữ liệu được materialize trong đúng đường sử dụng thực tế, gồm cả các getter được service hoặc serializer gọi.

### Trường hợp document store

Trong MongoDB, đối tượng lồng có thể được nhúng trong cùng document hoặc được biểu diễn bằng tham chiếu. Hai cách lưu có chi phí và cơ chế đọc khác nhau.

Spring Data MongoDB có cơ chế projection riêng và cách chọn trường của query. Xem [MongoDB: Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html) và [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html).

Một nested interface biểu diễn `customer.address.city` không tự nói rằng dữ liệu đó nằm cùng document, được tra từ collection khác hay đã được ứng dụng lắp ghép. Nó cũng không tự thêm phép lookup hoặc quy tắc lọc array theo ý nghĩa nghiệp vụ.

Không chuyển kết luận “JPA dùng join” thành mô tả chung cho mọi implementation của Commons.

## 9. Giữ cây view có điểm kết thúc rõ ràng

Một thiết kế dễ mở rộng ngoài ý muốn là:

```text
OrderView
  -> CustomerView
       -> List<OrderView>
            -> CustomerView
                 -> ...
```

Quan hệ hai chiều có thể hợp lý trong domain, nhưng response cho một use case không nhất thiết cần đi cả hai chiều.

Có thể dùng các kiểu khác nhau cho từng vị trí:

```text
OrderDetailView
  -> CustomerBrief
       -> id
       -> name
  -> List<LineBrief>
       -> productName
       -> quantity
```

`CustomerBrief` ở đây không khai báo collection đơn của khách hàng. Cây kết quả kết thúc ở các giá trị mà màn hình cần.

Một lỗi khác là chỉ dùng projection ở root nhưng trả entity ở nhánh:

```java
public interface WideOrderView {

    Long getId();

    Customer getCustomer();
}
```

Caller nhận kiểu domain `Customer`, nên hợp đồng nhánh đó có thể cho phép truy cập nhiều thuộc tính và quan hệ hơn `CustomerBrief`. Nếu serializer duyệt chúng, phạm vi truy cập có thể tiếp tục mở rộng.

Dùng kiểu con dành riêng cho use case giúp biểu đạt rõ các đường truy cập mong muốn. Độ sâu được kiểm soát bằng thiết kế kiểu; không mặc định framework sẽ tự áp một giới hạn độ sâu thích hợp cho ứng dụng.

## 10. Đọc dữ liệu cần thiết trong service rồi tạo response giá trị

Nếu backing còn phụ thuộc tài nguyên JPA, việc getter con cần tải thêm có thể thất bại sau khi persistence context phù hợp đã đóng.

Một lựa chọn là service đọc những giá trị cần thiết trong phạm vi giao dịch rồi tạo response không chứa proxy:

```java
public record CustomerResponse(
    String name,
    String city
) {}
```

```java
public record OrderResponse(
    Long id,
    String orderNumber,
    CustomerResponse customer
) {}
```

Service minh họa, sử dụng Java 17:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {

    private final OrderReadRepository repository;

    public OrderQueryService(OrderReadRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<OrderResponse> summaries(String tenantId) {
        return repository
            .findByTenantIdOrderByIdAsc(tenantId)
            .stream()
            .map(this::toResponse)
            .toList();
    }

    private OrderResponse toResponse(OrderSummaryView order) {
        OrderSummaryView.CustomerBrief customer =
            order.getCustomer();

        CustomerResponse customerResponse = null;

        if (customer != null) {
            OrderSummaryView.AddressBrief address =
                customer.getAddress();

            customerResponse = new CustomerResponse(
                customer.getName(),
                address == null ? null : address.getCity()
            );
        }

        return new OrderResponse(
            order.getId(),
            order.getOrderNumber(),
            customerResponse
        );
    }
}
```

Lời gọi `summaries` cần đi qua bean và proxy giao dịch đã được cấu hình; transaction manager phải phù hợp với repository. Cách đặt phạm vi ở service được giải thích trong [Spring Data JPA: Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).

Khi method trả về bình thường, các giá trị trong response đã được lấy. Response không chứa `Customer`, `Address` hoặc interface proxy cần tiếp tục đọc quan hệ.

Điều đó làm rõ vòng đời đọc nhưng chưa giải quyết hiệu năng: nếu các getter đã tạo nhiều truy vấn bên trong service, việc đưa chúng vào giao dịch không tự giảm số truy vấn. Ví dụ cũng chưa phân trang danh sách root; use case lớn cần bổ sung giới hạn phù hợp.

Các record trên được ứng dụng tự lắp ghép. Đây không phải khẳng định rằng class-based DTO projection của repository tự có cùng cơ chế proxy lồng nhau như interface projection.

## 11. Khi cần kiểm soát selection, cân nhắc query phẳng

Nếu use case chỉ cần vài scalar qua một quan hệ to-one, một query có selection tường minh có thể dễ đánh giá hơn việc dựa vào cây proxy.

Ví dụ dành riêng cho JPA, với `Customer.address` là embeddable:

```java
public interface FlatOrderRow {

    Long getOrderId();

    String getOrderNumber();

    String getCustomerName();

    String getCustomerCity();
}
```

```java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface FlatOrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    @Query("""
        select
            o.id as orderId,
            o.orderNumber as orderNumber,
            c.name as customerName,
            c.address.city as customerCity
        from PurchaseOrder o
        left join o.customer c
        where o.tenantId = :tenantId
        order by o.id
        """)
    List<FlatOrderRow> findRows(
        @Param("tenantId") String tenantId
    );
}
```

Query biểu đạt rõ các giá trị cần trả và dùng left join cho customer tùy chọn. Alias tương ứng với thuộc tính của interface phẳng.

Không giả định đổi alias thành `customer_name` sẽ tự tạo cấu trúc `CustomerBrief` trong mọi loại query. Mapping kết quả phẳng và nested projection là hai hợp đồng cần thiết kế riêng.

Ứng dụng có thể lắp `FlatOrderRow` thành `OrderResponse`. Nếu cần phân biệt chắc chắn “không có customer” với “customer tồn tại nhưng các trường đọc đều null”, nên chọn thêm ID customer làm dữ liệu phân biệt.

Query scalar không tự cung cấp collection con đã nhóm. Khi cần nhiều dòng con, phải quyết định query riêng, cách nhóm và giới hạn dữ liệu, thay vì kỳ vọng một alias tự dựng toàn bộ object graph.

## 12. Chọn nested view theo nhu cầu dữ liệu

| Nhu cầu | Cách tổ chức nên cân nhắc |
| --- | --- |
| Đọc một vài thuộc tính của đối tượng liên quan, cấu trúc rõ | Nested interface projection. |
| Kiểm soát chặt scalar nào được select qua quan hệ | Query tường minh và kết quả phẳng hoặc DTO phù hợp. |
| Danh sách root có collection con rất lớn | Tách view tóm tắt khỏi truy vấn chi tiết có giới hạn. |
| Response dùng sau khi rời phạm vi persistence | Đọc và lắp response giá trị trong service. |
| Hiển thị dữ liệu tại một thời điểm lịch sử | Lưu hoặc truy vấn snapshot đúng trong domain. |
| Cần nhiều cấp quan hệ hai chiều | Thiết kế cây đọc hữu hạn cho từng use case. |

Nested projection có ích khi cây interface phản ánh đúng điều caller cần đọc. Việc thêm một getter nhánh cần được coi là thay đổi phạm vi dữ liệu của use case, vì nó có thể kéo theo quan hệ, collection hoặc truy vấn bổ sung.

Không dùng một projection rất rộng cho mọi màn hình chỉ để giảm số lượng interface nếu mỗi màn hình có phạm vi dữ liệu khác nhau.

## 13. Thực hành: tách hình dạng kết quả khỏi hành vi truy vấn

Bắt đầu với `OrderSummaryView` và nguồn Map ở phần 4:

1. Đọc số đơn, tên khách hàng và thành phố.
2. Tạo nguồn bằng `HashMap` với `customer = null`, vì `Map.of` không nhận giá trị null.
3. Tạo nguồn có customer nhưng address null.
4. Thêm email vào nguồn mà giữ nguyên interface.
5. Đổi tên getter `getCity()` thành một tên không khớp thuộc tính nguồn và phân tích vấn đề mapping.

Các tình huống đó kiểm tra cách projection biểu diễn dữ liệu, không kiểm chứng SQL hay việc tải quan hệ.

Sau đó, trong môi trường tích hợp có module store thật, phân tích thêm:

| Tình huống | Điều cần làm rõ |
| --- | --- |
| Danh sách đơn có customer | Cột hoặc trường nào được đọc, bao nhiêu lượt truy cập store? |
| Một đơn không có customer | Query có giữ root không, getter biểu diễn thiếu quan hệ ra sao? |
| Đọc thêm lines | Có tải toàn collection không, thứ tự và giới hạn ở đâu? |
| Chỉ lọc đơn có một dòng phù hợp | Collection được trả có bị lọc tương ứng hay vẫn theo mapping gốc? |
| Serializer gọi getter sau khi service trả về | Dữ liệu đã là giá trị hay vẫn cần persistence context? |
| Khách hàng đổi địa chỉ | View đang đọc địa chỉ hiện tại hay thông tin lưu trên đơn? |

Điểm cần đạt là mô tả được cả ba phần: cây getter được công bố, dữ liệu backing thực tế và hành vi truy vấn của module. Khi ba phần đó được xác định rõ, nested projection trở thành một hợp đồng đọc có thể kiểm chứng cho đúng phạm vi dữ liệu liên quan.
