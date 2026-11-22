# Phân biệt Repository với DAO và tập hàm CRUD theo bảng

Trong phát triển phần mềm, Repository, DAO và các hàm CRUD đều có thể xuất hiện ở tầng truy cập dữ liệu. Chúng thường cùng tham gia việc đọc và ghi dữ liệu, nhưng đại diện cho những cách nhìn khác nhau về trách nhiệm.

Trong Domain-Driven Design (DDD), **Repository** cung cấp cách truy xuất và lưu Aggregate theo ngôn ngữ của mô hình miền. Caller làm việc với Order, Customer hoặc một Aggregate Root khác mà không cần biết dữ liệu được lưu bằng bảng quan hệ, document store hay cơ chế nào.

**DAO (Data Access Object)** tập trung vào việc truy cập nguồn dữ liệu. DAO thường phản ánh cấu trúc lưu trữ, câu truy vấn, bảng, view hoặc thao tác persistence. Một tập hàm CRUD theo bảng thường cung cấp các thao tác create, read, update và delete trực tiếp trên bản ghi.

Repository và DAO có thể phối hợp trong cùng kiến trúc: Repository thể hiện hợp đồng phù hợp với miền, còn implementation có thể dùng một hoặc nhiều DAO để đọc và ghi dữ liệu. Tuy nhiên, đổi tên một lớp CRUD thành `OrderRepository` không tự động biến nó thành Repository theo DDD. Điều quyết định là abstraction đang bảo vệ mô hình nào và cung cấp cách thao tác ở mức nghiệp vụ nào.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Repository trong DDD và vai trò của nó với Aggregate Root.
- Phân biệt Repository, DAO và các hàm CRUD theo bảng.
- Nhận biết vì sao một interface chỉ đổi tên `insert`, `update`, `delete` chưa chắc là Repository miền.
- Thiết kế Repository theo định danh và vòng đời của Aggregate.
- Hiểu cách Repository implementation phối hợp với DAO hoặc ORM.
- Phân biệt truy vấn nghiệp vụ với truy vấn báo cáo/read model.
- Đặt ranh giới transaction ở vị trí phù hợp.
- Review các anti-pattern như repository cho từng bảng hoặc để domain phụ thuộc SQL.

## 1. Ba cách nhìn về truy cập dữ liệu

### Repository: truy xuất Aggregate theo mô hình miền

Repository là một abstraction cho phép tìm và lưu Aggregate Root. Nó thường được thiết kế với cảm giác như một tập hợp các Aggregate trong bộ nhớ: caller yêu cầu tìm một Order theo ID, thêm hoặc lưu Order sau khi thay đổi.

Ví dụ:

- `OrderRepository` tìm và lưu Order.
- `CustomerRepository` tìm và lưu Customer.
- `ShipmentRepository` tìm và lưu Shipment.

Repository không nhất thiết phải cung cấp mọi thao tác CRUD. Nó chỉ nên cung cấp các thao tác cần thiết để ứng dụng làm việc với Aggregate theo ngôn ngữ miền. Việc một Aggregate có thể bị xóa hay chỉ được đóng/hủy theo nghiệp vụ cần được quyết định từ quy tắc, không phải vì database có lệnh DELETE.

### DAO: truy cập nguồn dữ liệu

DAO đóng gói thao tác truy cập dữ liệu cụ thể. Nó có thể:

- Chạy SQL hoặc gọi stored procedure.
- Đọc và ghi bảng, view hoặc document.
- Chuyển đổi dữ liệu lưu trữ thành record/DTO.
- Tối ưu truy vấn theo chỉ mục hoặc cấu trúc dữ liệu.
- Thực hiện các thao tác batch hoặc truy vấn chuyên biệt.

DAO thường có thể được thiết kế theo bảng hoặc theo nhóm truy vấn. Ví dụ `OrderHeaderDao`, `OrderLineDao` hoặc `CustomerReadDao`. Cách tổ chức này có thể phù hợp ở tầng persistence vì nó phản ánh cách dữ liệu được lưu hoặc truy xuất.

### Tập hàm CRUD theo bảng: thao tác trực tiếp với bản ghi

Một lớp CRUD đơn giản thường có các phương thức tương tự:

- `insert(OrderRow row)`
- `findById(long id)`
- `update(OrderRow row)`
- `deleteById(long id)`

Đây là giao diện hữu ích cho thao tác dữ liệu, nhưng nó không diễn đạt đầy đủ ý nghĩa của Aggregate. Caller có thể cập nhật cột trạng thái tùy ý, xóa bản ghi mà không kiểm tra chính sách, hoặc thay đổi bảng con độc lập với bảng cha.

CRUD là nhóm thao tác kỹ thuật phổ biến; nó không tự xác định ranh giới nghiệp vụ hay bất biến cần bảo vệ.

## 2. So sánh Repository, DAO và CRUD

| Tiêu chí | Repository trong DDD | DAO | CRUD theo bảng |
| --- | --- | --- | --- |
| Góc nhìn | Mô hình miền và Aggregate | Nguồn dữ liệu | Bản ghi/bảng |
| Đối tượng chính | Aggregate Root | Row, record, DTO hoặc truy vấn dữ liệu | Một bảng hoặc tài nguyên lưu trữ |
| Ngôn ngữ | `Order`, `Customer`, `Shipment` | `OrderRow`, `OrderHeader`, query result | `insert`, `update`, `delete` |
| Trách nhiệm | Truy xuất và lưu Aggregate | Đóng gói truy cập dữ liệu | Thực hiện thao tác CRUD |
| Quy tắc nghiệp vụ | Được bảo vệ bởi Aggregate; Repository hỗ trợ lưu/truy xuất | Thường không sở hữu quy tắc miền | Thường không sở hữu quy tắc miền |
| Biết cấu trúc database | Không nên để lộ ra caller | Có thể biết rõ | Thường biết rõ |
| Phạm vi điển hình | Một Repository cho mỗi Aggregate Root cần lưu trữ | Có thể nhiều DAO theo bảng hoặc truy vấn | Thường một CRUD component cho mỗi bảng |
| Caller thường gặp | Application Service | Repository implementation hoặc application/query adapter | Service kỹ thuật hoặc DAO consumer |

Không phải mọi DAO đều bắt buộc theo bảng và cũng không phải mọi Repository đều phải nằm trong package `domain`. Đây là phân biệt về abstraction và trách nhiệm. Trong kiến trúc cụ thể, interface Repository có thể được khai báo ở domain hoặc application layer; implementation thuộc infrastructure. Điều quan trọng là domain/application không phụ thuộc vào chi tiết lưu trữ.

## 3. Repository không chỉ là DAO đổi tên

Hãy xem hai interface sau:

```java
public interface OrderTableCrud {
    void insert(OrderRow row);
    Optional<OrderRow> selectById(long id);
    void update(OrderRow row);
    void deleteById(long id);
}
```

Interface này làm việc với `OrderRow` và các thao tác bảng. Nó phù hợp với một DAO hoặc CRUD gateway.

Một Repository theo DDD có thể có hợp đồng như sau:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Caller làm việc với Order Aggregate, không cần biết có bao nhiêu bảng, cột trạng thái đang dùng mã gì hay các dòng hàng được lưu ở đâu. Repository implementation chịu trách nhiệm tái tạo Aggregate và ghi trạng thái của nó theo cơ chế lưu trữ.

### Khác biệt thể hiện qua hợp đồng

Một DAO có thể cung cấp `updateStatus(orderId, "C")`. Repository miền thường không nên cung cấp một thao tác tổng quát cho phép caller cập nhật bất kỳ trạng thái nào. Thay vào đó, caller tải Order và yêu cầu hành vi `order.confirm()` hoặc `order.cancel(reason)`. Aggregate kiểm tra điều kiện, còn Repository lưu kết quả sau khi hành vi hợp lệ.

Tương tự, một DAO có thể có `insertOrderLine(row)`. Nếu OrderLine là Entity nội bộ của Order Aggregate, caller không nên lưu nó độc lập qua một repository hoặc DAO công khai trong application layer. Repository của Order tải và lưu toàn bộ phần trạng thái thuộc Aggregate theo mapping phù hợp.

### Repository có thể dùng DAO bên trong

Repository implementation có thể phối hợp nhiều DAO:

- `OrderHeaderDao` đọc phần header.
- `OrderLineDao` đọc các dòng hàng.
- `OrderRepository` ghép dữ liệu thành Order Aggregate.
- Khi lưu, Repository ghi header và các dòng hàng trong transaction thích hợp.

Việc có nhiều DAO bên trong không làm thay đổi hợp đồng miền. Caller vẫn chỉ làm việc với OrderRepository.

## 4. Repository thường được định nghĩa theo Aggregate Root

Trong DDD, Repository thường được cung cấp cho Aggregate Root, không phải cho mọi Entity hoặc mọi bảng. Lý do là Aggregate Root là cổng truy cập và nơi bảo vệ các bất biến trong ranh giới Aggregate.

Giả sử Order chứa OrderLine:

- `Order` là Aggregate Root.
- `OrderLine` là Entity nội bộ.
- `OrderLine` chỉ được thêm, sửa hoặc xóa qua hành vi của Order.
- Repository tải và lưu Order, bao gồm trạng thái các dòng hàng theo mapping persistence.

Nếu tạo `OrderLineRepository` để application tải một dòng hàng rồi cập nhật trực tiếp, caller có thể bỏ qua quy tắc của Order. Khi đó, ranh giới Aggregate bị suy yếu.

Một bảng có khóa chính riêng không đồng nghĩa với việc nó cần một Repository riêng. Quyết định tạo Repository dựa trên vòng đời và trách nhiệm của Aggregate, không dựa trên số lượng bảng.

### Repository không sở hữu quy tắc nghiệp vụ

Repository không nên quyết định một đơn có được xác nhận hay không. Nó chịu trách nhiệm tìm và lưu Aggregate. Quy tắc xác nhận thuộc Order hoặc một Domain Service phù hợp.

Một số truy vấn có thể dùng tiêu chí nghiệp vụ như `findPendingOrdersForCustomer(customerId)`. Phương thức này vẫn có thể phù hợp với Repository nếu nó trả về Aggregate và phục vụ use case miền rõ ràng. Tuy nhiên, không nên biến Repository thành nơi chứa mọi phép lọc, báo cáo và truy vấn màn hình.

## 5. Ví dụ: Application Service làm việc qua Repository

Application Service điều phối use case. Nó tải Aggregate qua Repository, gọi hành vi miền rồi lưu lại:

```java
public final class ConfirmOrderService {
    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void execute(OrderId orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFound(orderId));

        order.confirm();
        orders.save(order);
    }
}

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Trong ví dụ:

- Application Service không biết tên bảng hoặc SQL.
- Repository trả về Aggregate Order.
- `order.confirm()` bảo vệ điều kiện nghiệp vụ.
- `orders.save(order)` yêu cầu lưu trạng thái Aggregate.
- Repository implementation quyết định cách ghi dữ liệu.

Repository không cần cung cấp `updateStatus()` vì đó là thao tác thay đổi trạng thái mà Order phải kiểm soát. Nếu đơn không thể xác nhận, Aggregate từ chối hành vi và Application Service xử lý kết quả theo use case.

## 6. DAO và Repository implementation ở tầng hạ tầng

Một cách triển khai có thể dùng DAO để đóng gói SQL và Repository để ánh xạ giữa persistence model với domain model.

Giả sử database có hai bảng:

```sql
CREATE TABLE order_header (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    currency CHAR(3) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES order_header(id)
);
```

DAO có thể làm việc với cấu trúc bảng:

```java
public interface OrderHeaderDao {
    Optional<OrderHeaderRow> findHeader(long id);
    void upsert(OrderHeaderRow row);
}

public interface OrderLineDao {
    List<OrderLineRow> findByOrderId(long orderId);
    void replaceForOrder(long orderId, List<OrderLineRow> rows);
}
```

Repository implementation chuyển đổi giữa row và Aggregate. Đây là phác thảo để thể hiện trách nhiệm; việc tạo lại Aggregate cần constructor/factory hoặc mapping nội bộ phù hợp với mô hình thực tế:

```java
public final class SqlOrderRepository implements OrderRepository {
    private final OrderHeaderDao headers;
    private final OrderLineDao lines;
    private final OrderMapper mapper;

    public SqlOrderRepository(
        OrderHeaderDao headers,
        OrderLineDao lines,
        OrderMapper mapper
    ) {
        this.headers = headers;
        this.lines = lines;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return headers.findHeader(id.value())
            .map(header -> {
                List<OrderLineRow> lineRows =
                    lines.findByOrderId(header.id());
                return mapper.toDomain(header, lineRows);
            });
    }

    @Override
    public void save(Order order) {
        OrderHeaderRow header = mapper.toHeaderRow(order);
        List<OrderLineRow> lineRows = mapper.toLineRows(order);

        headers.upsert(header);
        lines.replaceForOrder(order.id().value(), lineRows);
    }
}
```

Đoạn code trên cần một số thành phần mapper/DAO bổ sung và cần được thực hiện trong transaction phù hợp. Điểm quan trọng là lớp SqlOrderRepository chịu trách nhiệm chuyển đổi giữa hai mô hình. Application Service không cần ghép `OrderHeaderRow` và `OrderLineRow` hoặc biết cách cập nhật hai bảng.

## 7. CRUD không phải lúc nào cũng là API nghiệp vụ phù hợp

Các thao tác CRUD mô tả cách dữ liệu được tạo, đọc, cập nhật và xóa. Nghiệp vụ thường mô tả hành động bằng ý nghĩa cụ thể hơn:

| CRUD kỹ thuật | Hành vi nghiệp vụ có thể phù hợp |
| --- | --- |
| `updateStatus(id, "C")` | `order.confirm()` |
| `deleteOrder(id)` | `order.cancel(reason)` hoặc `order.archive()` theo chính sách |
| `insertOrderLine(row)` | `order.addItem(productId, quantity, price)` |
| `updateQuantity(lineId, 4)` | `order.changeLineQuantity(lineId, 4)` |
| `updateBalance(accountId, amount)` | `account.deposit(amount)` hoặc `account.withdraw(amount)` |

Không phải mọi CRUD đều sai. Một màn hình quản trị đơn giản hoặc một bảng dữ liệu tham chiếu có thể phù hợp với CRUD. Vấn đề xuất hiện khi thao tác CRUD cho phép thay đổi một Aggregate mà không thông qua hành vi bảo vệ bất biến.

Hãy hỏi liệu thao tác đó chỉ cập nhật dữ liệu hay đang thay đổi một sự thật nghiệp vụ. Nếu có quy tắc về trạng thái, quyền, điều kiện hoặc tác động liên quan, API cần phản ánh hành vi và để mô hình kiểm soát.

## 8. Repository và truy vấn đọc phức tạp

Repository trong DDD thường phục vụ việc tải Aggregate để thay đổi hoặc làm việc trong một use case. Nhưng màn hình và báo cáo có thể cần truy vấn nhiều Aggregate, lọc, phân trang, tổng hợp hoặc join nhiều nguồn.

Không nên ép mọi truy vấn đó đi qua Repository của Aggregate. Có thể dùng query service, DAO hoặc read model riêng.

Ví dụ:

```java
public interface OrderQueries {
    List<OrderSummaryView> findRecentOrders(
        CustomerId customerId,
        int limit
    );

    Page<OrderReportRow> searchOrders(
        OrderSearchCriteria criteria,
        PageRequest page
    );
}
```

OrderQueries có thể được triển khai bằng SQL tối ưu, projection hoặc materialized view. Nó trả dữ liệu phục vụ đọc, không nhất thiết trả Aggregate có hành vi.

Đây là cách phân biệt command side và query side:

- **Command/write:** tải Aggregate Root qua Repository, gọi hành vi miền và lưu thay đổi.
- **Query/read:** dùng DAO/query service/read model để trả dữ liệu phù hợp với nhu cầu hiển thị hoặc báo cáo.

Nếu dự án dùng CQRS, hai đường đọc và ghi có thể được tách rõ hơn. Tuy nhiên, không cần triển khai CQRS chỉ vì có Repository và DAO; một ứng dụng đơn giản có thể dùng cùng database và transaction mà vẫn giữ abstraction riêng.

## 9. Transaction và Unit of Work

Repository thường hoạt động trong một ranh giới transaction do Application Service hoặc Unit of Work điều phối. Khi lưu một Aggregate gồm nhiều bảng, các thay đổi cần được ghi nhất quán theo chính sách giao dịch của hệ thống.

Ví dụ, lưu Order và các OrderLine có thể cần cùng một transaction. Nếu ghi header thành công nhưng ghi lines thất bại, database không nên để lại một Aggregate ở trạng thái nửa vời nếu mô hình yêu cầu tính nguyên tử.

Application Service có thể định nghĩa transaction boundary bằng framework hoặc abstraction:

```java
@Transactional
public void confirm(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(() -> new OrderNotFound(orderId));

    order.confirm();
    orders.save(order);
}
```

`@Transactional` là ví dụ với Spring. Trong kiến trúc khác, transaction có thể được quản lý bằng Unit of Work hoặc cơ chế tương đương. Repository không nên tự mở một transaction độc lập cho mỗi câu SQL nếu use case cần nhiều thao tác persistence cùng thành công hoặc cùng rollback.

### Không dùng transaction để thay thế ranh giới Aggregate

Một transaction database có thể cập nhật nhiều Aggregate, nhưng điều đó không có nghĩa chúng nên được gộp vào cùng một Aggregate. Ranh giới Aggregate được xác định bởi bất biến cần bảo vệ; transaction boundary là quyết định thực thi. Khi quy trình đi qua nhiều Bounded Context hoặc dịch vụ độc lập, có thể cần eventual consistency và cơ chế điều phối thay vì một transaction phân tán.

## 10. Repository, DAO và các lựa chọn triển khai

Có nhiều cách triển khai Repository:

- Dùng ORM như JPA/Hibernate để tải và lưu Aggregate.
- Dùng JDBC hoặc SQL mapper để kiểm soát truy vấn.
- Dùng document database để lưu một Aggregate trong một document.
- Dùng một hoặc nhiều DAO bên dưới Repository.
- Dùng adapter gọi một persistence service khác.

Công nghệ không quyết định abstraction. Repository có thể dùng SQL hoặc ORM; DAO cũng có thể dùng ORM. Điều quan trọng là caller thấy hợp đồng nào và hợp đồng đó thể hiện trách nhiệm gì.

Ví dụ với Spring Data JPA:

```java
public interface SpringDataOrderJpaRepository
        extends JpaRepository<OrderJpaEntity, Long> {
}
```

Interface trên là repository của tầng persistence theo cách gọi của Spring Data. Nó cung cấp các thao tác CRUD trên `OrderJpaEntity`. Nó không tự động là Domain Repository theo nghĩa DDD nếu application/domain trực tiếp sử dụng nó và để lộ persistence entity.

Một adapter có thể triển khai Domain Repository bằng Spring Data:

```java
public final class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;
    private final OrderMapper mapper;

    public JpaOrderRepository(
        SpringDataOrderJpaRepository jpa,
        OrderMapper mapper
    ) {
        this.jpa = jpa;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value()).map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        jpa.save(mapper.toJpaEntity(order));
    }
}
```

Ví dụ chỉ minh họa adapter và mapping. Trong ứng dụng JPA thực tế, cần xử lý đúng việc cập nhật Entity đang managed, cascade cho child entity, optimistic locking, version và transaction. Không nên tạo một mapper đơn giản nếu nó làm mất identity hoặc ghi đè trạng thái không mong muốn.

## 11. Những sai lầm thường gặp

- **Đổi tên DAO thành Repository:** interface vẫn thao tác trực tiếp trên row hoặc bảng, không cung cấp hợp đồng theo Aggregate.
- **Tạo Repository cho mỗi bảng:** làm lộ cấu trúc lưu trữ và cho phép thao tác child entity độc lập.
- **Dùng CRUD tổng quát cho mọi thay đổi:** caller có thể cập nhật trạng thái hoặc xóa dữ liệu mà không qua quy tắc miền.
- **Đưa SQL hoặc ORM type vào domain contract:** mô hình bị khóa vào công nghệ lưu trữ.
- **Đưa mọi truy vấn báo cáo vào Repository:** Repository trở thành nơi chứa các query không liên quan đến vòng đời Aggregate.
- **Để Repository chứa quy tắc nghiệp vụ:** việc xác nhận, hủy hoặc định giá không nên được quyết định trong lớp truy cập dữ liệu.
- **Mỗi DAO tự mở transaction:** một use case nhiều bước có thể không còn tính nguyên tử.
- **Giả định một bảng là một Aggregate:** ranh giới mô hình không được quyết định bởi schema.
- **Giả định Repository bắt buộc là một collection đầy đủ trong bộ nhớ:** đó là cách hình dung abstraction, không phải yêu cầu phải tải toàn bộ dữ liệu.
- **Cho rằng Spring Data JPA tự động thay thế DDD Repository:** CRUD repository của framework là chi tiết persistence; cần adapter nếu hợp đồng miền khác.

## 12. Quy trình thiết kế và review Repository

Khi thiết kế một Repository, có thể thực hiện theo các bước sau:

1. **Xác định Aggregate Root.** Làm rõ Entity nào đại diện cho ranh giới nhất quán và sở hữu các đối tượng nội bộ.
2. **Xác định use case cần truy xuất.** Những thao tác nào cần tải hoặc lưu Aggregate?
3. **Thiết kế hợp đồng theo ngôn ngữ miền.** Dùng kiểu ID và Aggregate thay vì row, table name hoặc SQL type.
4. **Chỉ cung cấp thao tác cần thiết.** Tránh thêm CRUD hoặc `findAll()` nếu use case không cần.
5. **Tách truy vấn đọc chuyên biệt.** Dùng query service/DAO/read model cho báo cáo, tìm kiếm hoặc projection.
6. **Triển khai ở infrastructure.** Dùng ORM, DAO hoặc SQL và chuyển đổi dữ liệu sang mô hình miền.
7. **Xác định transaction boundary.** Đảm bảo các thay đổi cần nguyên tử được thực hiện trong cùng một Unit of Work.
8. **Kiểm thử mapping và persistence.** Xác nhận Aggregate được tái tạo đúng, child entity không bị mất và quy tắc miền vẫn được bảo vệ.
9. **Review phụ thuộc.** Application/domain không nên biết chi tiết bảng, query hoặc provider cụ thể.

Checklist:

- [ ] Repository làm việc với Aggregate Root thay vì từng bảng?
- [ ] Interface dùng thuật ngữ miền và kiểu ID rõ ràng?
- [ ] Caller không nhận row/ORM entity thay cho Aggregate?
- [ ] Các hành vi nghiệp vụ được thực hiện trên Aggregate, không qua update cột tùy ý?
- [ ] Child Entity không có Repository riêng nếu vòng đời thuộc Root?
- [ ] DAO/SQL/ORM nằm trong implementation hạ tầng?
- [ ] Truy vấn đọc phức tạp được tách khỏi Repository ghi?
- [ ] Transaction boundary bao phủ các thao tác cần tính nguyên tử?
- [ ] Mapping giữ đúng identity, quan hệ và bất biến của Aggregate?
- [ ] Các thao tác CRUD chỉ được dùng ở nơi phù hợp với ý nghĩa nghiệp vụ?

## Kết luận

Repository trong DDD là abstraction để truy xuất và lưu Aggregate Root theo ngôn ngữ của mô hình miền. DAO đóng gói thao tác truy cập nguồn dữ liệu; CRUD theo bảng biểu diễn các thao tác tạo, đọc, cập nhật và xóa bản ghi. Ba khái niệm có thể phối hợp nhưng không thể thay thế nhau chỉ bằng cách đổi tên.

Hãy thiết kế hợp đồng Repository theo Aggregate và use case, để Aggregate bảo vệ quy tắc nghiệp vụ, còn implementation dùng DAO, ORM hoặc SQL để xử lý persistence. Dùng query service hoặc read model cho các truy vấn đọc chuyên biệt, đặt transaction ở ranh giới use case phù hợp và giữ chi tiết lưu trữ bên trong infrastructure. Khi đó, mô hình miền không bị chi phối bởi schema, còn tầng dữ liệu vẫn có đủ tự do để tối ưu cách lưu và truy vấn.
