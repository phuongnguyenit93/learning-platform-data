# Thiết kế giao diện lưu trữ theo nhu cầu ca sử dụng

Tầng truy cập dữ liệu cung cấp cách đọc và ghi dữ liệu cho phần còn lại của ứng dụng. Khi thiết kế giao diện lưu trữ, điểm xuất phát nên là những gì ca sử dụng cần làm và những bảo đảm mà nghiệp vụ yêu cầu. Từ đó mới xác định các thao tác mà một repository hoặc storage port cần cung cấp.

Một giao diện lưu trữ tốt diễn đạt ý định ở mức ứng dụng hoặc miền nghiệp vụ, chẳng hạn tìm đơn hàng cần xử lý, lưu thay đổi của đơn hàng hay lấy lịch sử giao dịch theo khoảng thời gian. Nó không nên buộc tầng Application phải biết tên bảng, câu SQL, kiểu entity của JPA hoặc cách một database cụ thể tổ chức dữ liệu.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, thiết kế giao diện lưu trữ là cách giữ ranh giới giữa ca sử dụng và công nghệ lưu trữ. Giao diện cần đủ cụ thể để bảo vệ trách nhiệm và hợp đồng, đồng thời đủ gọn để không tạo thêm lớp trừu tượng chỉ nhằm che đi một lời gọi CRUD đơn giản.

## 1. Bắt đầu từ nhu cầu của ca sử dụng

Hãy xét một ứng dụng bán hàng có các ca sử dụng: đặt hàng, hủy đơn, xem chi tiết đơn và tra cứu lịch sử mua hàng. Mỗi ca sử dụng cần những khả năng lưu trữ khác nhau:

| Ca sử dụng | Nhu cầu dữ liệu | Thao tác lưu trữ có ý nghĩa |
|---|---|---|
| Đặt hàng | Lấy thông tin sản phẩm, tạo đơn hàng | Tìm sản phẩm theo mã, lưu đơn hàng mới |
| Hủy đơn | Đọc đơn hàng và kiểm tra trạng thái hiện tại | Tải đơn hàng cần hủy, lưu trạng thái sau khi hủy |
| Xem chi tiết | Lấy thông tin hiển thị cho một đơn | Truy vấn chi tiết theo mã đơn |
| Lịch sử mua hàng | Lấy danh sách theo khách hàng, sắp xếp và phân trang | Tìm đơn theo khách hàng với bộ lọc và phân trang |

Nếu chỉ nhìn vào cấu trúc bảng, nhóm có thể tạo một giao diện chung với các phương thức như insert, update, delete và findAll. Những phương thức đó mô tả cách thao tác dữ liệu ở mức thấp, nhưng không thể hiện tại sao một use case cần dữ liệu, nó cần dữ liệu nào và các điều kiện nào phải được giữ.

Thay vào đó, hãy đọc luồng nghiệp vụ và ghi lại:

- Đối tượng hoặc thông tin nào cần được tải?
- Cần tìm theo định danh, trạng thái, chủ sở hữu hay điều kiện nào?
- Use case có thay đổi trạng thái của một aggregate hay chỉ đọc dữ liệu để hiển thị?
- Có yêu cầu nguyên tử, khóa hoặc phát hiện cập nhật đồng thời không?
- Kết quả cần là một aggregate, một projection, một trang dữ liệu hay một giá trị tổng hợp?

Những câu trả lời này hình thành hợp đồng lưu trữ. Cùng một bảng dữ liệu có thể phục vụ nhiều ca sử dụng với các giao diện khác nhau; ngược lại, một use case có thể cần phối hợp nhiều repository hoặc nguồn dữ liệu.

## 2. Giao diện nên diễn đạt ý định, không phơi bày chi tiết database

Một repository cho aggregate đơn hàng có thể cung cấp những thao tác ở mức nghiệp vụ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);

    void save(Order order);
}
~~~

Application hoặc Domain có thể dùng hợp đồng này để tải một đơn hàng, thực hiện hành vi trên aggregate rồi lưu thay đổi. Tên phương thức cho biết đối tượng cần tìm hoặc lưu, không cho biết dữ liệu nằm trong bảng nào hay được truy vấn bằng công nghệ nào.

Ngược lại, một giao diện như sau làm lộ mô hình lưu trữ và thiếu ngữ nghĩa:

~~~java
public interface GenericDao<T> {
    T select(String table, String whereClause);
    void insert(String table, Map<String, Object> values);
    void update(String table, Map<String, Object> values);
    void delete(String table, Object id);
}
~~~

Người gọi phải biết tên bảng, cấu trúc cột và cú pháp điều kiện. Những chi tiết đó khiến tầng Application phụ thuộc vào database. Hơn nữa, giao diện không thể hiện quy tắc như “chỉ hủy được đơn đang chờ xử lý” hoặc “chỉ tải đơn thuộc khách hàng hiện tại”. Quy tắc nghiệp vụ vẫn phải được bảo vệ ở use case và Domain, nhưng hợp đồng lưu trữ cần hỗ trợ chúng bằng những thao tác rõ ràng.

Cũng cần tránh giao diện quá chung như một repository chứa hàng chục phương thức cho mọi màn hình và mọi loại dữ liệu. Khi một interface có nhiều trách nhiệm không liên quan, thay đổi một nhu cầu đọc có thể ảnh hưởng tới các nơi chỉ cần thao tác ghi. Hãy nhóm phương thức theo khái niệm và khả năng mà chúng phục vụ.

## 3. Không phải mỗi ca sử dụng đều cần một repository riêng

Thiết kế theo nhu cầu ca sử dụng không có nghĩa là tạo một interface cho từng use case. Các ca sử dụng có thể chia sẻ một hợp đồng nếu chúng thao tác trên cùng một khái niệm và cần cùng những bảo đảm.

Ví dụ, PlaceOrder và CancelOrder đều có thể dùng OrderRepository để tải và lưu aggregate Order. Không cần tạo PlaceOrderRepository và CancelOrderRepository chỉ để đổi tên cùng một phương thức findById.

Tuy nhiên, nhu cầu truy vấn cho màn hình lịch sử đơn hàng có thể khác hẳn thao tác tải aggregate. Màn hình cần tên sản phẩm, tổng tiền, trạng thái và ngày tạo, có thể lấy từ nhiều bảng. Nó không cần khởi tạo toàn bộ aggregate Order cùng các quan hệ. Khi đó, một query port riêng là hợp lý:

~~~java
public record OrderHistoryFilter(
        UUID customerId,
        OrderStatus status,
        Instant from,
        Instant to
) {}

public record OrderHistoryItem(
        UUID orderId,
        Instant createdAt,
        BigDecimal total,
        String statusLabel
) {}

public record PageResult<T>(
        List<T> items,
        long totalItems,
        int page,
        int pageSize
) {}

public interface SearchOrderHistory {
    PageResult<OrderHistoryItem> search(
            OrderHistoryFilter filter,
            int page,
            int pageSize
    );
}
~~~

Port này phản ánh nhu cầu đọc của use case lịch sử mua hàng. Infrastructure có thể triển khai bằng JPQL projection, SQL hoặc một công cụ truy vấn khác. Use case không phải biết dữ liệu được join từ bao nhiêu bảng.

Điểm cần phân biệt:

- Repository của aggregate thường hỗ trợ tải và lưu đối tượng có quy tắc, trạng thái và vòng đời nghiệp vụ.
- Query port thường trả về DTO hoặc read model tối ưu cho một truy vấn, báo cáo hoặc màn hình.
- Cả hai đều là hợp đồng ở ranh giới ứng dụng, nhưng có mục đích và hình dạng dữ liệu khác nhau.

Không cần ép mọi truy vấn phải đi qua repository aggregate. Cũng không nên biến query port thành một nơi chứa quy tắc nghiệp vụ. Nó cung cấp dữ liệu theo tiêu chí đã yêu cầu; Application và Domain vẫn quyết định hành động nào hợp lệ.

## 4. Đặt giao diện ở đâu và ai triển khai?

Vị trí đặt interface phụ thuộc vào trách nhiệm mà hợp đồng phục vụ:

- Nếu hợp đồng mô tả cách truy xuất một aggregate của Domain, nó có thể nằm trong Domain.
- Nếu hợp đồng là một cổng mà một ca sử dụng Application cần để thực hiện công việc, nó có thể nằm trong Application.
- Lớp triển khai dùng JPA, JDBC, MongoDB hoặc API bên ngoài thuộc Infrastructure.

Ví dụ cấu trúc module:

~~~text
orders
├── domain
│   ├── Order.java
│   ├── OrderId.java
│   └── OrderRepository.java
├── application
│   ├── PlaceOrderService.java
│   ├── CancelOrderService.java
│   └── SearchOrderHistory.java
└── infrastructure
    └── persistence
        ├── JpaOrderRepositoryAdapter.java
        ├── SpringDataOrderJpaRepository.java
        └── OrderJpaEntity.java
~~~

Luồng phụ thuộc khi biên dịch đi từ Application/Domain tới hợp đồng; Infrastructure phụ thuộc vào hợp đồng để cung cấp phần thực thi. Lúc chạy, Spring có thể tiêm adapter vào use case bằng dependency injection.

~~~mermaid
flowchart LR
    A[Application use case] --> P[Storage port / interface]
    D[Domain] --> P
    I[Infrastructure adapter] -. implements .-> P
    I --> J[Spring Data / JDBC]
    J --> DB[(Database)]
~~~

Không có một quy tắc duy nhất buộc mọi repository phải đặt trong Domain. Nếu một query phục vụ riêng màn hình hoặc báo cáo, đặt query port trong Application thường diễn đạt đúng hơn vì nhu cầu đó thuộc ca sử dụng. Điều quan trọng là interface không kéo các kiểu phụ thuộc của Infrastructure vào tầng cao hơn.

## 5. Chọn chữ ký phương thức và kiểu kết quả có ý nghĩa

Một giao diện lưu trữ là hợp đồng giữa hai phần của hệ thống. Chữ ký phương thức cần thể hiện rõ điều kiện đầu vào và khả năng xảy ra khi truy vấn.

### Dùng định danh có ý nghĩa

Nếu hệ thống có nhiều loại ID, có thể dùng kiểu định danh riêng như OrderId thay cho việc truyền UUID hoặc String ở khắp nơi. Điều này giúp tránh truyền nhầm productId vào phương thức cần orderId.

~~~java
public record OrderId(UUID value) {}

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Với hệ thống đơn giản, dùng UUID trực tiếp vẫn có thể hợp lý. Kiểu định danh riêng có ích khi nó làm rõ mô hình và giảm lỗi, nhưng cũng có chi phí chuyển đổi và khai báo thêm.

### Thể hiện trường hợp không tìm thấy

Nếu không tìm thấy là kết quả hợp lệ của thao tác truy vấn, Optional có thể biểu đạt điều đó:

~~~java
Optional<Order> findById(OrderId id);
~~~

Use case quyết định cách xử lý kết quả rỗng, ví dụ trả lỗi OrderNotFound hoặc hiển thị trang không tồn tại. Một số hệ thống chọn ném exception ngay trong repository; lựa chọn này cũng có thể hợp lý nếu được thống nhất, nhưng cần rõ ai chịu trách nhiệm chuyển lỗi thành kết quả ứng dụng.

Không nên trả null vì buộc mọi nơi gọi phải tự nhớ kiểm tra và dễ phát sinh NullPointerException.

### Phân biệt lưu mới và lưu thay đổi khi có ý nghĩa

Một phương thức save có thể xử lý cả insert và update nếu semantics của repository được định nghĩa rõ. Nếu hệ thống cần phân biệt tạo mới, cập nhật hoặc bảo đảm aggregate đã tồn tại, có thể dùng phương thức cụ thể hơn. Không nên phơi bày tên thao tác SQL chỉ vì adapter dùng SQL.

### Thiết kế phân trang và sắp xếp có giới hạn

Với truy vấn danh sách lớn, hợp đồng nên nhận tiêu chí phân trang và trả thông tin trang. Không nên trả toàn bộ dữ liệu rồi để Application lọc hoặc sắp xếp trong bộ nhớ.

Cần giới hạn pageSize, xác định thứ tự sắp xếp ổn định và tránh cho client truyền trực tiếp tên cột SQL tùy ý. Có thể định nghĩa enum cho các trường sắp xếp được hỗ trợ và kiểm tra hướng tăng/giảm. Với dữ liệu rất lớn hoặc liên tục thay đổi, cursor/keyset pagination có thể phù hợp hơn offset pagination.

### Không trả kiểu của framework lưu trữ qua interface

Hãy cẩn thận với các kiểu như EntityManager, JpaRepository, Page<Entity> hoặc Specification của Spring Data trong hợp đồng mà Application phụ thuộc. Chúng gắn tầng Application vào framework. Có thể chuyển sang kiểu PageResult, filter hoặc sort model do ứng dụng định nghĩa, rồi để adapter ánh xạ sang kiểu cụ thể.

## 6. Ví dụ adapter Spring Data JPA

Hợp đồng aggregate có thể được triển khai bằng adapter. Adapter chịu trách nhiệm chuyển giữa mô hình Domain và entity lưu trữ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Spring Data repository là chi tiết nội bộ của Infrastructure:

~~~java
interface SpringDataOrderJpaRepository
        extends JpaRepository<OrderJpaEntity, UUID> {
}
~~~

Adapter chuyển đổi qua mapper hoặc hàm chuyển đổi:

~~~java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value())
                .map(OrderJpaEntity::toDomain);
    }

    @Override
    public void save(Order order) {
        OrderJpaEntity entity = OrderJpaEntity.fromDomain(order);
        jpa.save(entity);
    }
}
~~~

Ví dụ đã lược bỏ chi tiết mapping và xử lý version để tập trung vào ranh giới. Trong dự án thực tế, adapter cần quyết định cách ánh xạ quan hệ, value object, trạng thái và khóa phiên bản. Nếu domain aggregate được tải một phần, adapter phải bảo đảm dữ liệu đủ để thực hiện các hành vi mà use case gọi.

Một query adapter có thể triển khai SearchOrderHistory bằng projection:

~~~java
@Repository
public class JpaSearchOrderHistoryAdapter
        implements SearchOrderHistory {
    private final SpringDataOrderHistoryRepository jpa;

    public JpaSearchOrderHistoryAdapter(
            SpringDataOrderHistoryRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public PageResult<OrderHistoryItem> search(
            OrderHistoryFilter filter,
            int page,
            int pageSize) {

        Pageable pageable = PageRequest.of(
                page,
                Math.min(pageSize, 100),
                Sort.by(Sort.Direction.DESC, "createdAt")
        );

        Page<OrderHistoryProjection> result =
                jpa.search(filter, pageable);

        List<OrderHistoryItem> items = result.getContent().stream()
                .map(row -> new OrderHistoryItem(
                        row.getOrderId(),
                        row.getCreatedAt(),
                        row.getTotal(),
                        row.getStatusLabel()
                ))
                .toList();

        return new PageResult<>(
                items,
                result.getTotalElements(),
                result.getNumber(),
                result.getSize()
        );
    }
}
~~~

Phương thức minh họa cần được bổ sung validation page/pageSize và truy vấn phù hợp trong Spring Data repository. Điểm quan trọng là kiểu Page của Spring Data được giữ bên trong adapter; Application nhận PageResult do ứng dụng định nghĩa.

## 7. Giao dịch và cập nhật đồng thời thuộc hợp đồng nào?

Một giao diện lưu trữ không chỉ là danh sách phương thức. Nó còn tham gia vào các bảo đảm mà use case cần.

Thông thường, Application service xác định ranh giới giao dịch cho một ca sử dụng. Ví dụ, đặt hàng có thể cần kiểm tra sản phẩm, tạo Order và lưu đơn hàng trong cùng một transaction. Không nên để mỗi phương thức repository tự mở và commit một transaction độc lập nếu use case cần nhiều thao tác nguyên tử.

~~~java
@Service
public class CancelOrderService {
    private final OrderRepository orders;

    public CancelOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void cancel(OrderId id) {
        Order order = orders.findById(id)
                .orElseThrow(OrderNotFoundException::new);

        order.cancel();
        orders.save(order);
    }
}
~~~

Trong ví dụ này, quy tắc hủy nằm trong Order; use case điều phối và xác định transaction. Repository chỉ tải và lưu aggregate. Nếu có nhiều repository được gọi trong cùng use case, cấu hình transaction cần bao phủ chúng theo yêu cầu nhất quán.

Khi hai request đồng thời sửa cùng một aggregate, có thể xảy ra lost update. Adapter có thể dùng optimistic locking với trường version, ví dụ JPA @Version, để phát hiện một bản ghi đã bị thay đổi kể từ lúc được đọc. Ứng dụng cần quyết định cách phản hồi: thử lại khi phù hợp, báo xung đột hoặc yêu cầu người dùng làm mới dữ liệu.

Nếu cơ chế cạnh tranh là một phần quan trọng của hợp đồng, hãy thể hiện rõ bằng exception hoặc kết quả có thể nhận diện, thay vì để tầng trên đoán một lỗi database chung. Không nên đưa annotation JPA hay LockModeType vào interface Application chỉ để điều khiển một adapter cụ thể.

## 8. Tránh một số kiểu giao diện lưu trữ gây khó bảo trì

| Thiết kế | Vấn đề | Hướng điều chỉnh |
|---|---|---|
| Generic DAO thao tác theo tên bảng và map cột | Tầng Application biết cấu trúc lưu trữ | Đặt tên phương thức theo đối tượng và nhu cầu nghiệp vụ |
| Một repository khổng lồ cho mọi truy vấn | Nhiều trách nhiệm và phụ thuộc không liên quan | Chia theo aggregate hoặc nhóm truy vấn có mục đích |
| Interface trả JpaRepository, EntityManager hoặc JPA entity | Framework và schema rò rỉ qua ranh giới | Dùng port và DTO do Application/Domain định nghĩa |
| Tạo một repository cho từng use case dù phương thức giống nhau | Trùng lặp interface và adapter | Chia sẻ hợp đồng khi cùng ngữ nghĩa và bảo đảm |
| Trả toàn bộ bản ghi rồi lọc trong Application | Tốn bộ nhớ và truyền dữ liệu dư thừa | Đưa filter, phân trang và projection vào query port |
| Repository tự quyết định quy tắc nghiệp vụ | Ranh giới trách nhiệm bị đảo lộn | Repository cung cấp dữ liệu; Domain/Application quyết định hợp lệ |

Không cần loại bỏ mọi giao diện CRUD. Với một ứng dụng nhỏ, Spring Data repository có thể là lựa chọn đủ tốt nếu được giữ trong Infrastructure và không làm rò kiểu framework sang tầng Application. Mục tiêu không phải tạo thêm abstraction bằng mọi giá; mục tiêu là tạo một hợp đồng hữu ích ở nơi có ranh giới thay đổi hoặc cần bảo vệ phụ thuộc.

## 9. Kiểm thử hợp đồng lưu trữ

Có thể kiểm thử use case bằng một implementation giả của interface để xác minh hành vi ứng dụng mà không cần database:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> data = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(data.get(id));
    }

    @Override
    public void save(Order order) {
        data.put(order.getId(), order);
    }
}
~~~

Fake repository hữu ích cho unit test Application và Domain, nhưng không chứng minh adapter JPA hoạt động đúng. Cần có integration test cho adapter để xác minh mapping, truy vấn, transaction, optimistic locking và hành vi database.

Có thể tổ chức kiểm thử theo ba lớp:

- **Use case test:** dùng fake hoặc mock để kiểm tra luồng điều phối, trường hợp không tìm thấy và hành vi khi lưu.
- **Adapter integration test:** chạy với database kiểm thử tương thích để xác minh câu truy vấn, mapping và semantics của repository.
- **Contract test:** nếu có nhiều adapter triển khai cùng một port, chạy chung một bộ kiểm thử để bảo đảm chúng thực hiện cùng hợp đồng, bao gồm cách biểu diễn dữ liệu không tồn tại, phân trang và lỗi xung đột.

Hợp đồng nên mô tả những điều caller có thể dựa vào: kết quả khi không tìm thấy, phạm vi dữ liệu được trả về, thứ tự và phân trang, khả năng lưu thay đổi, cùng loại lỗi có thể phát sinh. Tên phương thức dễ đọc là cần thiết nhưng chưa đủ nếu semantics của nó mơ hồ.

## 10. Quy trình thiết kế một storage port

Khi thêm một ca sử dụng mới, có thể đi theo quy trình sau:

1. Viết rõ mục tiêu và các bước nghiệp vụ của ca sử dụng.
2. Xác định dữ liệu cần đọc, dữ liệu cần thay đổi và các bất biến phải bảo vệ.
3. Chọn aggregate repository nếu use case cần tải và lưu một đối tượng miền có vòng đời; chọn query port nếu cần projection hoặc kết quả truy vấn chuyên biệt.
4. Định nghĩa kiểu đầu vào và đầu ra theo ngôn ngữ của Application/Domain; tránh kiểu phụ thuộc framework hoặc database.
5. Xác định semantics khi không tìm thấy, khi có dữ liệu lớn, khi cập nhật đồng thời và khi lưu thất bại.
6. Viết use case dựa trên interface, rồi triển khai adapter trong Infrastructure.
7. Kiểm thử use case bằng fake/mock và kiểm thử adapter với database thực tế hoặc database tương thích.

Không phải mỗi ca sử dụng đều cần interface mới. Hãy dùng chung hợp đồng khi các ca sử dụng cần cùng một khả năng với cùng ngữ nghĩa; tách hợp đồng khi nhu cầu, dữ liệu trả về hoặc bảo đảm khác nhau rõ rệt.

Thiết kế giao diện lưu trữ theo nhu cầu ca sử dụng giúp Application diễn đạt điều nó cần, Domain giữ các quy tắc và Infrastructure tự do lựa chọn công nghệ lưu trữ. Một hợp đồng vừa đủ cụ thể làm cho code dễ hiểu, dễ kiểm thử và ít bị ảnh hưởng khi schema hoặc công nghệ database thay đổi.

