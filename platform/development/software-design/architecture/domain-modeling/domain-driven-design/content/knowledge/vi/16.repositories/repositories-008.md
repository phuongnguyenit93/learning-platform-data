# Cài đặt repository trong bộ nhớ cho kiểm thử và giới hạn của cách thay thế

Trong Domain-Driven Design (DDD), Repository cung cấp cách truy cập Aggregate như một tập hợp đối tượng nghiệp vụ. Application cần tải một Aggregate theo định danh hoặc lưu thay đổi của nó, nhưng không nên phải biết dữ liệu nằm trong PostgreSQL, MySQL, MongoDB hay hệ thống lưu trữ nào. Abstraction này cũng cho phép dùng một implementation nhẹ trong kiểm thử.

**InMemory Repository** là implementation lưu Aggregate trong bộ nhớ, thường bằng `Map` hoặc collection. Nó triển khai cùng interface với repository thật nhưng không kết nối database. Nhờ vậy, kiểm thử Application Service có thể chạy nhanh, tập trung vào luồng use case và không cần khởi động hạ tầng.

Tuy nhiên, thay database bằng bộ nhớ chỉ thay đổi cách lưu dữ liệu. Nó không tái tạo đầy đủ hành vi của hệ quản trị cơ sở dữ liệu. InMemory Repository không tự kiểm chứng SQL, mapping ORM, transaction, ràng buộc, khóa đồng thời hoặc khác biệt của database sản xuất. Muốn có kiểm thử đáng tin cậy, cần hiểu điều gì được kiểm tra bằng fake trong bộ nhớ và điều gì vẫn phải kiểm tra với persistence adapter thật.

## 1. Repository trong DDD là ranh giới truy cập Aggregate

Repository thường được định nghĩa cho Aggregate Root. Nó giúp Application nạp hoặc lưu một Aggregate mà không phụ thuộc cách lưu trữ cụ thể.

Ví dụ, Ordering cần tải và lưu Order:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Interface này diễn đạt nhu cầu của mô hình Ordering. Nó dùng Order và OrderId, không để lộ bảng SQL, Entity JPA, session ORM hoặc connection database.

Application Service sử dụng hợp đồng đó:

```java
public class PlaceOrderUseCase {
    private final OrderRepository orders;

    public PlaceOrderUseCase(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders);
    }

    public void handle(PlaceOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.place();
        orders.save(order);
    }
}
```

Use case chỉ quan tâm đến việc tìm Order, gọi hành vi domain và lưu kết quả. Implementation cụ thể được cung cấp ở composition root hoặc qua dependency injection.

### 1.1. Repository không phải bản sao tổng quát của database

Một repository theo DDD không cần cung cấp toàn bộ khả năng CRUD của database. Nó nên biểu diễn các thao tác có ý nghĩa với Aggregate và use case.

Ví dụ, các phương thức sau có thể phù hợp nếu nghiệp vụ thực sự cần:

- `findById(OrderId id)` để tải một Order.
- `save(Order order)` để lưu trạng thái Aggregate.
- `findOpenOrdersFor(CustomerId customerId)` nếu đây là truy vấn thuộc repository theo thiết kế của module.

Những phương thức như `executeSql`, `getConnection`, `saveAnyEntity` hoặc `findAllTables` làm lộ chi tiết persistence và khiến abstraction mất ngôn ngữ domain.

Không nhất thiết mọi truy vấn đọc đều phải đi qua Repository. Với màn hình tìm kiếm, báo cáo hoặc danh sách tổng hợp, Query Service hoặc Read Model có thể phù hợp hơn. Bài viết tập trung vào repository lưu/nạp Aggregate và implementation trong bộ nhớ cho kiểm thử.

### 1.2. Vì sao cần nhiều implementation?

| Implementation | Mục đích | Nơi sử dụng |
|---|---|---|
| JPA / JDBC Repository | Đọc và ghi dữ liệu qua database | Ứng dụng chạy thật và integration test |
| InMemory Repository | Lưu Aggregate trong collection ở bộ nhớ | Unit test hoặc application test |
| Remote / API Adapter | Truy cập dữ liệu qua một dịch vụ khác nếu kiến trúc yêu cầu | Môi trường tích hợp tương ứng |

Khả năng thay implementation là kết quả của việc thiết kế hợp đồng ổn định. Nếu application phụ thuộc trực tiếp vào `JpaRepository`, không thể thay bằng InMemory Repository mà không sửa mã sử dụng.

## 2. InMemory Repository là gì?

InMemory Repository là một lớp thực hiện repository abstraction bằng cấu trúc dữ liệu nằm trong RAM. Ví dụ, một `Map<OrderId, Order>` có thể lưu Aggregate theo định danh.

Đặc điểm thường gặp:

- Không cần database server hoặc kết nối mạng.
- Tạo dữ liệu trực tiếp trong test.
- Tìm kiếm theo ID nhanh và đơn giản.
- Có thể khởi tạo mới cho từng test để cô lập dữ liệu.
- Dễ quan sát trạng thái sau khi use case chạy.
- Không mô phỏng đầy đủ transaction, constraint, query planner hoặc concurrency của database thật.

Một InMemory Repository thường là **Fake** trong nhóm test double: nó có hành vi làm việc thật ở mức đơn giản, thay vì trả về một kết quả cố định.

### 2.1. Phân biệt Fake, Stub và Mock

Các test double có thể thay thế dependency trong một bài kiểm thử, nhưng chúng phục vụ các mục đích khác nhau.

| Loại | Hành vi | Ví dụ |
|---|---|---|
| Fake | Có implementation chạy được nhưng đơn giản hơn production | InMemoryOrderRepository lưu Order trong Map |
| Stub | Trả dữ liệu đã định trước để kiểm tra một tình huống | Repository luôn trả về một Order cụ thể |
| Mock | Ghi nhận hoặc xác minh tương tác được kỳ vọng | Xác minh `save(order)` được gọi đúng một lần |

InMemory Repository là Fake vì nó thực sự lưu và truy xuất dữ liệu trong phạm vi của nó. Stub có thể trả về Order có sẵn mà không cần mô phỏng việc lưu. Mock có thể xác minh Application Service gọi đúng dependency, nhưng thường gắn test với chi tiết tương tác.

Chọn loại test double theo mục tiêu:

- Kiểm tra invariant của Order: không cần repository.
- Kiểm tra use case thay đổi và lưu Order: Fake thường phù hợp.
- Kiểm tra xử lý khi không tìm thấy Order: Stub hoặc Fake đều có thể dùng.
- Kiểm tra một tương tác quan trọng với cổng ngoài: Mock có thể hữu ích.
- Kiểm tra SQL và mapping: cần persistence adapter thật.

### 2.2. InMemory Repository không phải database in-memory

Hai khái niệm này dễ bị gọi nhầm:

- **InMemory Repository** là implementation repository tự lưu đối tượng trong collection của chương trình.
- **In-memory database** là hệ quản trị cơ sở dữ liệu chạy trong bộ nhớ, vẫn thực hiện SQL, constraint, transaction và các hành vi theo engine của nó.

Một `HashMap` không thực thi SQL. H2 chạy ở chế độ in-memory vẫn là database có parser SQL, schema, transaction và driver JDBC. Tuy nhiên, H2 vẫn có thể khác PostgreSQL hoặc MySQL về kiểu dữ liệu, cú pháp, locking và hành vi cụ thể.

Vì vậy, kiểm thử với InMemory Repository và kiểm thử với database in-memory là hai cấp kiểm thử khác nhau.

## 3. Cài đặt InMemory Repository cơ bản bằng Java

Giả sử domain có `OrderId` là Value Object và `Order` là Aggregate Root. Ta cần một implementation đơn giản cho interface `OrderRepository`.

### 3.1. Định nghĩa định danh và repository contract

```java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }
}

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Hợp đồng cần được hiểu rõ:

- `findById` trả về `Optional.empty()` khi không có Order.
- `save` thêm Order mới hoặc lưu trạng thái mới của Order đã tồn tại, theo semantics mà module thống nhất.
- Định danh của Order không thay đổi trong quá trình lưu.
- Repository không tự thực hiện quy tắc đặt, hủy hoặc xác nhận đơn; những hành vi đó thuộc Aggregate.

Nếu `save` trong hệ thống chỉ cập nhật bản ghi đã tồn tại, hoặc interface tách thành `add` và `update`, InMemory implementation phải tuân theo chính xác contract đó. Tên phương thức không đủ để suy ra semantics.

### 3.2. Cài đặt bằng Map

Một phiên bản tối giản:

```java
public final class InMemoryOrderRepository
        implements OrderRepository {

    private final Map<OrderId, Order> store = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public void save(Order order) {
        store.put(order.id(), order);
    }
}
```

Cài đặt này phù hợp để minh họa ý tưởng: định danh là key, Aggregate là value. Nhưng nó có một giới hạn quan trọng: Map giữ cùng tham chiếu đối tượng được truyền vào.

Nếu test gọi `save(order)`, sau đó thay đổi `order` mà không gọi `save` lần nữa, lần `findById` tiếp theo vẫn có thể thấy thay đổi vì repository và test đang dùng cùng một object trong bộ nhớ. Database thông thường không tự phản ánh mọi thay đổi của một object Java đã tách khỏi persistence context. Fake quá đơn giản vì thế có thể che giấu lỗi mà test với ORM sẽ phát hiện.

### 3.3. Tránh chia sẻ cùng tham chiếu mutable

Nếu muốn fake gần với semantics lưu/nạp hơn, hãy tạo bản sao khi lưu và khi đọc. Ví dụ dưới đây giả định Aggregate có phương thức `copy()` thực hiện sao chép sâu các thành phần mutable và giữ nguyên định danh:

```java
public final class InMemoryOrderRepository
        implements OrderRepository {

    private final Map<OrderId, Order> store = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(store.get(id))
            .map(Order::copy);
    }

    @Override
    public void save(Order order) {
        store.put(order.id(), order.copy());
    }
}
```

Cách này giúp thay đổi object bên ngoài sau khi lưu không tự động làm thay đổi dữ liệu fake; mỗi lần đọc cũng trả về một instance riêng. Nó gần hơn với tình huống Aggregate được nạp lại từ persistence.

Tuy nhiên, `copy()` phải sao chép sâu các thành phần có thể thay đổi. Nếu chỉ sao chép collection nhưng vẫn dùng chung mutable child object, vấn đề aliasing vẫn còn. Value Object bất biến có thể được chia sẻ an toàn.

Một lựa chọn khác là lưu snapshot trung gian và tái tạo Aggregate khi đọc. Với Aggregate phức tạp, snapshot thường giúp kiểm soát rõ dữ liệu được giữ. Mapper phải tái tạo Aggregate ở trạng thái hợp lệ; không nên gọi constructor tạo mới nếu constructor đó phát sinh hành vi hoặc sự kiện dành cho một Aggregate mới.

### 3.4. Ví dụ snapshot cho fake

```java
public record StoredOrder(
    OrderId id,
    OrderStatus status,
    List<StoredOrderLine> lines
) {}

public record StoredOrderLine(
    ProductId productId,
    int quantity,
    Money unitPrice
) {}
```

Repository chuyển đổi giữa Aggregate và snapshot:

```java
public final class InMemoryOrderRepository
        implements OrderRepository {

    private final Map<OrderId, StoredOrder> store = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(store.get(id))
            .map(OrderMapper::toDomain);
    }

    @Override
    public void save(Order order) {
        store.put(order.id(), OrderMapper.toStored(order));
    }
}
```

Snapshot ở đây là representation nội bộ của fake. Nếu production repository cũng dùng persistence model riêng, mapper tương ứng cần được kiểm thử bằng integration test với adapter thật.

## 4. Dùng InMemory Repository trong kiểm thử Application Service

Mục tiêu phổ biến nhất là kiểm tra use case có phối hợp đúng Aggregate và repository hay không.

### 4.1. Tạo dữ liệu ban đầu

Dùng factory hoặc test data builder để tạo Order hợp lệ:

```java
Order order = Order.draft(
    new OrderId(UUID.randomUUID()),
    List.of(
        OrderLine.of(
            new ProductId("SKU-100"),
            2,
            Money.of("120000", "VND")
        )
    )
);
```

Dữ liệu test nên được tạo qua factory hoặc builder có ý nghĩa, tránh gán trực tiếp hàng loạt field private. Điều này giúp fixture tuân theo invariant giống ứng dụng.

### 4.2. Kiểm tra use case lưu trạng thái sau khi xử lý

```java
class PlaceOrderUseCaseTest {

    private InMemoryOrderRepository orders;
    private PlaceOrderUseCase useCase;

    @BeforeEach
    void setUp() {
        orders = new InMemoryOrderRepository();
        useCase = new PlaceOrderUseCase(orders);
    }

    @Test
    void placesAndPersistsOrder() {
        OrderId id = new OrderId(UUID.randomUUID());
        Order order = TestOrders.draftWithOneLine(id);
        orders.save(order);

        useCase.handle(new PlaceOrderCommand(id));

        Order saved = orders.findById(id).orElseThrow();

        assertEquals(OrderStatus.PLACED, saved.status());
    }
}
```

Test này kiểm tra luồng Application: use case tìm Order, gọi hành vi đặt đơn và lưu Aggregate. Nó không cần database để kiểm tra trách nhiệm điều phối đó.

Nếu repository trả về cùng tham chiếu mutable, test có thể vẫn pass ngay cả khi use case quên gọi `save`. Đây là lý do cần cân nhắc copy/snapshot hoặc bổ sung test kiểm tra hành vi lưu. Fake nên tránh che lỗi quan trọng của contract.

### 4.3. Kiểm tra trường hợp không tìm thấy Aggregate

```java
@Test
void failsWhenOrderDoesNotExist() {
    OrderId missingId = new OrderId(UUID.randomUUID());

    assertThrows(
        OrderNotFoundException.class,
        () -> useCase.handle(new PlaceOrderCommand(missingId))
    );
}
```

Trường hợp này kiểm tra cách use case phản ứng với `Optional.empty()`. Không cần mock toàn bộ repository nếu fake đã có hành vi tìm kiếm theo ID.

### 4.4. Kiểm tra invariant trực tiếp trên Aggregate

Một bài kiểm thử domain nên kiểm tra Order mà không thông qua repository:

```java
@Test
void cannotPlaceAnEmptyOrder() {
    Order order = Order.draft(
        new OrderId(UUID.randomUUID()),
        List.of()
    );

    assertThrows(
        InvalidOrderException.class,
        order::place
    );
}
```

Kiểm thử này xác minh quy tắc thuộc Order. Việc dùng InMemory Repository ở đây không đem lại giá trị nếu mục tiêu chỉ là kiểm tra invariant.

## 5. Giữ contract nhất quán giữa fake và repository thật

Một InMemory Repository chỉ hữu ích khi nó tôn trọng contract mà application dựa vào. Nếu fake và production adapter có semantics khác nhau, test có thể pass trong khi ứng dụng thật thất bại.

### 5.1. Viết rõ semantics của từng phương thức

Với mỗi phương thức repository, cần xác định:

- Khi không tìm thấy dữ liệu thì trả `Optional.empty()`, null hay ném exception?
- `save` là insert, update hay upsert?
- Khi ID trùng, hành vi là ghi đè hay báo lỗi?
- Thứ tự kết quả có được bảo đảm không?
- Phân trang dùng chỉ số bắt đầu từ đâu và có giới hạn nào?
- Có cho phép lưu Aggregate ở trạng thái không hợp lệ không?
- Xóa là xóa vật lý, xóa mềm hay chỉ đánh dấu ngừng hoạt động?
- Các lỗi persistence được chuyển thành loại lỗi nào ở ranh giới?

Fake không nên tự chọn hành vi thuận tiện nếu production contract đã quy định khác.

### 5.2. Kiểm tra quy tắc uniqueness

Nếu repository contract yêu cầu một mã đơn hàng duy nhất, fake có thể cần kiểm tra trùng. Nhưng cần xác định uniqueness thuộc domain hay persistence:

- Nếu mã đơn phải duy nhất vì quy tắc nghiệp vụ, domain có thể biểu diễn định danh và application có thể yêu cầu kiểm tra.
- Nếu database có unique index để bảo vệ tính duy nhất dưới tải đồng thời, chỉ fake dùng Map chưa kiểm chứng race condition.
- Nếu hai yêu cầu đồng thời cùng tạo một mã, database thật cần constraint hoặc cơ chế đồng bộ để chỉ một thao tác thành công.

Một đoạn kiểm tra trong Map có thể mô phỏng hành vi từ chối trùng ở luồng tuần tự, nhưng không chứng minh tính duy nhất an toàn khi nhiều transaction chạy đồng thời.

### 5.3. Kiểm tra semantics truy vấn

Nếu repository cung cấp truy vấn theo trạng thái hoặc thời gian, fake cần thực hiện cùng điều kiện và thứ tự mà contract yêu cầu.

Ví dụ, contract có thể yêu cầu danh sách đơn mới nhất theo `createdAt` giảm dần. Một `HashMap.values()` không bảo đảm thứ tự. Nếu fake trả về thứ tự không xác định, test có thể chập chờn hoặc không phát hiện lỗi sắp xếp.

Hãy sắp xếp rõ trong fake nếu thứ tự là một phần của contract:

```java
return store.values().stream()
    .filter(order -> order.customerId().equals(customerId))
    .sorted(Comparator.comparing(Order::createdAt).reversed())
    .limit(limit)
    .map(Order::copy)
    .toList();
```

Nếu contract không cam kết thứ tự, test không nên phụ thuộc vào thứ tự ngẫu nhiên của collection.

### 5.4. Tách lỗi domain khỏi lỗi persistence

Một Aggregate từ chối hành vi vì invariant không hợp lệ là lỗi domain. Một database từ chối ghi vì mất kết nối, timeout hoặc vi phạm constraint là lỗi persistence hoặc infrastructure.

InMemory Repository có thể mô phỏng một số lỗi đã định trước để kiểm tra phản ứng của Application Service. Nhưng không nên biến mọi lỗi thành `IllegalStateException` chung hoặc giả định database exception luôn giống lỗi domain.

Application cần xử lý kết quả theo contract; adapter thật chịu trách nhiệm chuyển đổi lỗi công nghệ ở ranh giới.

## 6. Contract test cho nhiều implementation

Một cách giảm sai lệch là viết cùng một bộ contract test và chạy nó với từng implementation của repository.

Ví dụ, lớp kiểm thử trừu tượng định nghĩa các hành vi bắt buộc:

```java
abstract class OrderRepositoryContractTest {

    protected abstract OrderRepository newRepository();

    @Test
    void returnsEmptyWhenOrderIsMissing() {
        OrderRepository repository = newRepository();

        assertTrue(
            repository.findById(
                new OrderId(UUID.randomUUID())
            ).isEmpty()
        );
    }

    @Test
    void savesAndFindsOrderById() {
        OrderRepository repository = newRepository();
        Order order = TestOrders.draftWithOneLine(
            new OrderId(UUID.randomUUID())
        );

        repository.save(order);

        Order loaded = repository.findById(order.id())
            .orElseThrow();

        assertEquals(order.id(), loaded.id());
        assertEquals(order.status(), loaded.status());
    }
}
```

Implementation InMemory có thể kế thừa bộ contract test:

```java
class InMemoryOrderRepositoryTest
        extends OrderRepositoryContractTest {

    @Override
    protected OrderRepository newRepository() {
        return new InMemoryOrderRepository();
    }
}
```

Production adapter cũng có thể chạy cùng contract test, nhưng cần chuẩn bị database và dọn dữ liệu giữa các test. Với JPA/JDBC, test đó thường là integration test.

Contract test giúp phát hiện khác biệt về semantics cơ bản giữa các implementation. Nó không thay thế test riêng cho SQL, transaction, mapping hoặc hành vi đặc thù của từng adapter.

### 6.1. Contract test nên kiểm tra điều gì?

Tùy repository contract, có thể kiểm tra:

- Tìm ID tồn tại và ID không tồn tại.
- Lưu Aggregate mới và tải lại.
- Cập nhật Aggregate đã tồn tại.
- Hành vi khi ID hoặc business key bị trùng.
- Thứ tự và phân trang nếu contract cam kết.
- Không làm lộ cùng mutable reference giữa các lần đọc.
- Xử lý trạng thái hoặc dữ liệu bị vô hiệu hóa theo quy tắc đã thống nhất.

Những kiểm tra về lock, isolation, SQL dialect, schema và index thuộc integration test của adapter thật.

## 7. Giới hạn của InMemory Repository

InMemory Repository làm kiểm thử nhanh, nhưng môi trường của nó khác database thực tế.

### 7.1. Không kiểm tra SQL và mapping ORM

Fake không chạy câu SQL và không dùng ORM. Nó không thể phát hiện:

- JPQL hoặc SQL sai.
- Mapping sai tên cột hoặc quan hệ.
- Kiểu dữ liệu không tương thích.
- Constructor hoặc converter của ORM hoạt động sai.
- Lazy loading gây lỗi ngoài transaction.
- Native query sai theo database dialect.
- Schema migration thiếu cột hoặc index.

Các vấn đề này cần test adapter với database tương ứng.

### 7.2. Không kiểm tra transaction và rollback thực

Một Map không có transaction theo nghĩa database. Nếu use case lưu nhiều Aggregate rồi một thao tác sau thất bại, các thay đổi trước đó có thể đã nằm trong Map.

Fake có thể tự xây dựng cơ chế snapshot/rollback đơn giản, nhưng điều đó chỉ kiểm tra implementation giả do nhóm viết. Nó không chứng minh transaction manager, propagation, isolation hoặc rollback của database hoạt động đúng.

Muốn kiểm tra atomicity, hãy chạy integration test với persistence adapter thật và xác minh trạng thái sau khi lỗi xảy ra.

### 7.3. Không kiểm tra khóa và xử lý đồng thời

Database thật có thể dùng optimistic locking, pessimistic locking, version column hoặc cơ chế concurrency khác. Một `HashMap` đơn giản không mô phỏng những bảo đảm đó.

Ngay cả `ConcurrentHashMap` cũng không tương đương transaction database. Nó chỉ cung cấp một số thao tác collection an toàn luồng, không bảo vệ invariant trên nhiều bản ghi hoặc nhiều thao tác liên quan.

Các tình huống như hai người cùng đặt số lượng hàng cuối cùng, hai transaction cập nhật cùng Order hoặc hai request tạo cùng business key cần được kiểm tra với database và cơ chế đồng thời thực tế.

### 7.4. Không tự áp dụng constraint và quan hệ tham chiếu

Database có thể bảo vệ:

- NOT NULL.
- UNIQUE.
- FOREIGN KEY.
- CHECK constraint.
- Referential integrity.
- Cascade theo schema.

Fake chỉ kiểm tra những gì code của nó chủ động thực hiện. Nếu không viết kiểm tra, dữ liệu thiếu hoặc tham chiếu mồ côi có thể được lưu mà database thật sẽ từ chối.

Đừng nhầm việc domain có invariant với việc database constraint không cần thiết. Một số quy tắc nên được bảo vệ ở domain; một số ràng buộc dữ liệu cần được database bảo vệ thêm, đặc biệt khi có nhiều tiến trình ghi.

### 7.5. Khác biệt về kiểu dữ liệu và so sánh

Database có thể xử lý collation, chữ hoa/chữ thường, dấu tiếng Việt, null, decimal precision, timestamp và timezone theo quy tắc riêng. Java collection thường so sánh theo `equals()` hoặc comparator được viết trong code.

Ví dụ, tìm kiếm không phân biệt hoa thường có thể hoạt động trong một database với collation cụ thể nhưng không hoạt động trong fake dùng `String.equals`. Ngược lại, fake có thể chấp nhận hai giá trị mà unique index của database coi là trùng.

Giá trị tiền tệ, độ chính xác thập phân, thời gian và quy tắc chuẩn hóa cần được kiểm tra ở adapter thật.

### 7.6. Không kiểm tra phân trang và hiệu năng truy vấn thật

Một Map có thể lọc toàn bộ dữ liệu trong bộ nhớ. Database có index, query planner, giới hạn tài nguyên và chi phí I/O. Fake không phát hiện:

- Query N+1.
- Thiếu index.
- Full table scan.
- Join quá tốn kém.
- Pagination không ổn định khi dữ liệu thay đổi.
- Query hoạt động khác khi dữ liệu lớn.

Test với fake xác minh logic lọc ở mức đơn giản, không đo hiệu năng truy vấn persistence.

### 7.7. Không kiểm tra schema migration và dữ liệu cũ

Fake thường tạo dữ liệu trực tiếp từ object hiện tại. Nó không chạy qua schema cũ, migration hoặc dữ liệu lịch sử có thể thiếu trường hay mang giá trị không còn hợp lệ.

Các thay đổi schema cần được kiểm tra bằng migration test hoặc integration test trên database thực tế. Cũng cần có chiến lược xử lý dữ liệu cũ khi mô hình domain thay đổi.

### 7.8. Tóm tắt phạm vi kiểm chứng

| Nội dung | InMemory Repository | Repository thật với database |
|---|---|---|
| Điều phối use case | Phù hợp | Phù hợp |
| Tương tác qua repository contract | Phù hợp | Phù hợp |
| Invariant của Aggregate | Có thể kiểm tra riêng, không cần repository | Có thể kiểm tra qua luồng persistence |
| SQL và ORM mapping | Không kiểm tra | Có |
| Transaction và rollback | Không mô phỏng đầy đủ | Có |
| Unique/FK/check constraint | Chỉ nếu fake tự viết | Có |
| Lock và concurrency | Không tương đương | Có |
| Collation, decimal, timezone | Không tương đương | Có |
| Query plan và index | Không kiểm tra | Có |
| Schema migration | Không kiểm tra | Có |
| Tốc độ kiểm thử use case | Thường nhanh | Thường chậm hơn |

## 8. Khi nào nên dùng InMemory Repository?

InMemory Repository phù hợp khi mục tiêu là kiểm tra logic application trong môi trường đơn giản, không cần phụ thuộc persistence engine.

Các trường hợp thường hữu ích:

- Kiểm thử Application Service gọi repository và domain behavior đúng.
- Kiểm tra một use case qua nhiều Aggregate giả lập nhưng không cần SQL.
- Tạo fixture nhanh cho test.
- Chạy nhiều test nhỏ với dữ liệu cô lập.
- Phát triển prototype hoặc ví dụ giảng dạy.
- Kiểm tra contract cơ bản của repository.

Không nên dùng nó làm bằng chứng duy nhất cho việc persistence adapter đã hoạt động đúng. Nếu ứng dụng dùng database quan hệ, cần một tập integration test chạy trên engine tương ứng với môi trường sản xuất.

### 8.1. Không cần fake repository cho mọi bài kiểm thử

Một số test có thể gọi trực tiếp Aggregate:

```java
@Test
void orderRejectsInvalidTransition() {
    Order order = TestOrders.placed();

    assertThrows(
        InvalidOrderTransitionException.class,
        order::place
    );
}
```

Một số test cần kiểm tra application orchestration, khi đó fake repository hữu ích. Một số test cần xác minh SQL hoặc transaction, khi đó cần database thật. Chọn công cụ theo câu hỏi mà test cần trả lời.

### 8.2. Tránh dùng InMemory Repository để kiểm thử toàn bộ ứng dụng

Nếu mọi test đều dùng fake, lỗi tích hợp có thể chỉ xuất hiện khi triển khai. Ví dụ, code có thể giả định database trả về thứ tự ổn định, nhưng query thật không có ORDER BY. Hoặc fake cho phép lưu hai bản ghi trùng business key trong khi database từ chối.

Một bộ kiểm thử cân bằng thường có:

- Nhiều unit test cho domain model.
- Application test dùng fake hoặc stub ở các ranh giới cần thiết.
- Contract test cho repository abstraction.
- Integration test cho persistence adapter với database thật.
- Một số end-to-end test cho luồng quan trọng.

## 9. Thiết kế InMemory Repository để test ổn định

Một fake tốt nên đơn giản nhưng có semantics rõ ràng. Không cần xây dựng một database thu nhỏ.

### 9.1. Mỗi test nên có repository riêng

Tạo instance mới trong `@BeforeEach` hoặc fixture riêng cho từng test. Tránh static Map hoặc singleton dùng chung dữ liệu giữa test.

Nếu dữ liệu còn lại từ test trước, kết quả sẽ phụ thuộc thứ tự chạy. Test chạy song song có thể ghi đè dữ liệu của nhau. Isolation của fixture là điều kiện cơ bản để kiểm thử đáng tin cậy.

### 9.2. Cung cấp helper test mà không mở rộng production contract

Có thể thêm phương thức như `clear()` hoặc `size()` trong chính class fake để hỗ trợ test. Không cần đưa chúng vào interface `OrderRepository` nếu application không có nhu cầu nghiệp vụ đó.

Ví dụ:

```java
public void clear() {
    store.clear();
}

public int size() {
    return store.size();
}
```

Các helper này là tiện ích test. Không để production code phụ thuộc vào chúng.

### 9.3. Tránh cài đặt quá nhiều tính năng database

Không cần xây dựng query language, transaction manager, index hoặc locking engine trong fake. Càng cố mô phỏng database, fake càng phức tạp và có thể sai khác với database thật theo cách khó nhận biết.

Hãy chỉ triển khai contract mà Application cần. Các semantics quan trọng cần được kiểm tra bằng contract test và integration test tương ứng.

### 9.4. Dùng test data builder để tạo Aggregate hợp lệ

Builder giúp giảm lặp nhưng không nên cho phép tạo trạng thái bất hợp lệ mà production không thể tạo.

Ví dụ:

```java
public final class TestOrders {
    private TestOrders() {}

    public static Order draftWithOneLine(OrderId id) {
        return Order.draft(
            id,
            List.of(
                OrderLine.of(
                    new ProductId("SKU-100"),
                    1,
                    Money.of("50000", "VND")
                )
            )
        );
    }

    public static Order placed() {
        Order order = draftWithOneLine(
            new OrderId(UUID.randomUUID())
        );
        order.place();
        return order;
    }
}
```

Builder nên gọi factory và hành vi domain công khai. Nếu test phải sửa field private bằng reflection để tạo dữ liệu, đó có thể là dấu hiệu cần xem lại API tạo Aggregate hoặc cách chuẩn bị fixture.

## 10. Quy trình đưa InMemory Repository vào dự án

Có thể áp dụng theo các bước sau:

1. **Xác định repository contract hiện có.** Tìm interface thuộc phía domain hoặc application và xác định nó quản lý Aggregate Root nào.
2. **Viết rõ semantics.** Làm rõ cách xử lý ID không tồn tại, save, update, duplicate, sort, pagination và delete.
3. **Tạo fake tối thiểu.** Dùng Map hoặc collection phù hợp với định danh Aggregate.
4. **Quyết định cách xử lý object reference.** Nếu Aggregate mutable, cân nhắc deep copy hoặc snapshot để tránh test dùng chung trạng thái ngoài ý muốn.
5. **Tạo fixture riêng cho mỗi test.** Không chia sẻ static data hoặc instance mutable giữa các test.
6. **Viết application tests.** Kiểm tra use case qua repository abstraction và domain behavior.
7. **Viết contract tests.** Chạy cùng bộ kiểm tra semantics cơ bản cho fake và adapter thật.
8. **Giữ integration tests cho persistence.** Kiểm tra mapping, SQL, constraint, transaction, migration và concurrency với database tương ứng.
9. **Không mở rộng fake thành database thu nhỏ.** Khi test cần kiểm chứng tính năng database, chuyển test đó sang integration test.

Quy trình này giữ fake ở mức dễ hiểu và đảm bảo mỗi loại test có phạm vi rõ ràng.

## 11. Những sai lầm thường gặp

**Coi test pass với InMemory Repository là database đã đúng.** Fake không chạy SQL, không kiểm tra mapping và không chứng minh transaction hoạt động. Hãy chạy integration test cho adapter thật.

**Dùng cùng một object reference khi lưu và đọc mà không nhận ra.** Test có thể pass dù application quên gọi save. Hãy cân nhắc copy hoặc snapshot khi cần mô phỏng ranh giới lưu/nạp.

**Để fake có semantics khác production.** Nếu fake trả về thứ tự ổn định còn database không cam kết thứ tự, test có thể tạo kỳ vọng sai. Contract cần được định nghĩa và kiểm tra.

**Viết fake quá phức tạp.** Cố mô phỏng transaction, SQL và locking khiến fake trở thành một database kém chính xác. Chỉ triển khai những gì contract cần.

**Dùng mock cho mọi repository test.** Mock chỉ xác minh tương tác; nó không chứng minh dữ liệu được lưu và tải đúng. Fake thường phù hợp hơn cho kiểm thử use case cần trạng thái.

**Dùng InMemory Repository làm test tích hợp duy nhất.** Lỗi mapping, constraint, migration và dialect sẽ bị bỏ sót. Cần database thật ở một lớp kiểm thử riêng.

**Chia sẻ dữ liệu test toàn cục.** Static Map và fixture dùng chung gây rò dữ liệu giữa test, lỗi phụ thuộc thứ tự và xung đột khi chạy song song. Tạo repository mới cho mỗi test.

**Đưa helper test vào production interface.** `clear()` hoặc `size()` thường không phải năng lực nghiệp vụ. Giữ chúng trong fake hoặc fixture.

**Tạo repository cho mọi Entity con.** Repository thường quản lý Aggregate Root. Nếu OrderLine thuộc Aggregate Order, thao tác với nó qua Order để bảo vệ invariant.

## 12. Checklist đánh giá InMemory Repository

Trước khi sử dụng fake trong test, hãy kiểm tra:

**Repository contract**

- Interface thuộc đúng phía lõi và dùng ngôn ngữ domain chưa?
- Contract có định nghĩa rõ `find`, `save`, duplicate và thứ tự kết quả không?
- Repository có tập trung vào Aggregate Root không?
- Các query đọc chuyên biệt có nên tách sang Query Service không?

**Implementation trong bộ nhớ**

- Key có dùng định danh ổn định của Aggregate không?
- Fake có giữ cùng semantics với contract production không?
- Có nguy cơ chia sẻ mutable reference giữa test và repository không?
- Có cần deep copy hoặc snapshot không?
- Mỗi test có dữ liệu và instance repository riêng không?
- Có tránh static state và phụ thuộc thứ tự test không?

**Phạm vi kiểm thử**

- Test đang kiểm tra domain behavior, application orchestration hay persistence?
- InMemory Repository có phù hợp với câu hỏi của test không?
- Contract test có chạy trên các implementation cần thiết không?
- SQL, mapping, constraint và transaction đã được kiểm tra bằng integration test chưa?
- Concurrency, lock, migration và hành vi database đặc thù có test phù hợp không?

**Khả năng bảo trì**

- Fake có đủ nhỏ để người đọc hiểu ngay không?
- Có đang cố mô phỏng database quá mức không?
- Helper test có bị đưa vào production interface không?
- Khi contract thay đổi, fake và repository thật có được cập nhật cùng nhau không?

## 13. Kết luận

InMemory Repository là một Fake hữu ích để kiểm thử Application Service và các luồng sử dụng Repository mà không cần database. Nó triển khai cùng abstraction với repository thật, lưu Aggregate bằng collection và giúp test chạy nhanh, dễ cô lập dữ liệu. Muốn tránh kết quả sai lệch, cần định nghĩa rõ contract, chú ý việc chia sẻ mutable object và giữ semantics của fake nhất quán với production adapter.

Giới hạn của nó cũng cần được nhìn nhận rõ. InMemory Repository không kiểm tra SQL, ORM mapping, transaction, constraint, concurrency, collation, migration hay hiệu năng truy vấn thật. Những hành vi đó cần integration test với database tương ứng. Hãy dùng fake để kiểm tra đúng phạm vi của nó, dùng contract test để giữ các implementation nhất quán và dùng database thật để xác minh ranh giới persistence.

