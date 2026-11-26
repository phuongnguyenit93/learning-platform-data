# Tầng truy cập dữ liệu

## Trách nhiệm truy xuất, lưu trữ và chuyển đổi dữ liệu của tầng dữ liệu

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — tầng truy cập dữ liệu chịu trách nhiệm giao tiếp với nơi dữ liệu được lưu hoặc cung cấp. Tầng này chuyển yêu cầu đọc/ghi của ứng dụng thành thao tác phù hợp với công nghệ cụ thể, nhận kết quả và chuyển dữ liệu về dạng mà phần còn lại của hệ thống có thể sử dụng.

Ba nhóm công việc cốt lõi là **truy xuất**, **lưu trữ** và **chuyển đổi dữ liệu**. Chúng thường xuất hiện cùng nhau trong một adapter hoặc repository implementation, nhưng cần được hiểu rõ để tránh đưa quy tắc nghiệp vụ, định dạng HTTP hoặc chi tiết cơ sở dữ liệu lan sang các tầng khác.

Bài học dùng ví dụ Java/Spring với đơn hàng được lưu bằng JPA. Tên lớp và cách chia package chỉ mang tính minh họa; một dự án có thể dùng JDBC, jOOQ, MyBatis, MongoDB, tệp hoặc dịch vụ dữ liệu bên ngoài.

## 1. Vị trí của tầng dữ liệu trong kiến trúc

Tầng dữ liệu thường nằm ở phía ngoài của phần nghiệp vụ. Nó biết cách giao tiếp với cơ sở dữ liệu hoặc nguồn dữ liệu cụ thể; tầng ứng dụng sử dụng các hợp đồng để yêu cầu đọc và ghi. Trong cách tổ chức có đảo ngược phụ thuộc, interface/port được khai báo ở phần ứng dụng hoặc miền, còn adapter triển khai interface nằm trong hạ tầng.

```text
Client
  |
  v
Presentation (HTTP / UI)
  |
  v
Application (điều phối ca sử dụng)
  |                         ^
  | gọi qua port            | triển khai port
  v                         |
Domain                 Data Access Adapter
                              |
                              v
                       Database / Data Source
```

Sơ đồ biểu diễn một lựa chọn thiết kế phổ biến: application phụ thuộc vào hợp đồng lưu trữ; adapter dữ liệu triển khai hợp đồng đó và dùng công nghệ lưu trữ. Trong kiến trúc phân tầng cổ điển, interface và implementation có thể cùng được đặt trong tầng dữ liệu. Dù chọn cách nào, cần giữ rõ hướng phụ thuộc để phần nghiệp vụ không bị ràng buộc vào JPA hay schema cụ thể.

Tầng dữ liệu có thể bao gồm repository implementation, DAO, ORM mapping, câu truy vấn, cấu hình kết nối và các adapter cho cache hoặc dịch vụ dữ liệu. Không phải dự án nào cũng cần tách mỗi trách nhiệm thành một module riêng.

## 2. Trách nhiệm truy xuất dữ liệu

**Truy xuất dữ liệu** là lấy dữ liệu từ nguồn lưu trữ theo yêu cầu của ca sử dụng. Công việc này bao gồm xác định cách tìm dữ liệu, thực thi truy vấn, xử lý kết quả và cung cấp dữ liệu theo hợp đồng đã công bố.

Các thao tác thường gặp:

- Tìm một bản ghi hoặc aggregate theo định danh.
- Tìm theo điều kiện như khách hàng, trạng thái, khoảng thời gian hoặc loại giao dịch.
- Trả về danh sách có phân trang và sắp xếp.
- Thực hiện truy vấn tổng hợp hoặc projection cho màn hình báo cáo.
- Xử lý trường hợp không tìm thấy, dữ liệu trùng hoặc kết quả vượt quá giới hạn cho phép.

Ví dụ, use case xem chi tiết đơn hàng cần tìm đơn theo `OrderId`. Tầng ứng dụng mô tả nhu cầu bằng hợp đồng `OrderRepository`; adapter JPA quyết định truy vấn bằng Spring Data JPA như thế nào.

```java
// Hợp đồng mà application service sử dụng
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

```java
// Repository Spring Data ở phía hạ tầng
interface SpringDataOrderRepository
        extends JpaRepository<OrderJpaEntity, UUID> {
}
```

Tầng ứng dụng không cần biết truy vấn dùng `findById`, SQL, index hay tên bảng nào. Khi cần tìm theo điều kiện phức tạp, adapter có thể dùng query method, JPQL, Criteria API hoặc SQL tùy công nghệ. Hợp đồng nên diễn đạt nhu cầu của ứng dụng, chẳng hạn `findOpenOrdersForCustomer`, thay vì phơi bày cấu trúc bảng như `selectRowsFromOrderTable`.

### Truy vấn danh sách và dữ liệu đọc

Không nên mặc định mọi truy vấn đều tải toàn bộ entity. Với danh sách lớn, tầng dữ liệu cần hỗ trợ phân trang, giới hạn số dòng và sắp xếp ổn định. Với báo cáo hoặc màn hình chỉ cần vài trường, projection hoặc read model có thể tránh tải cả aggregate và giảm lượng dữ liệu truyền đi.

Ví dụ, màn hình lịch sử đơn hàng chỉ cần mã đơn, ngày tạo và tổng tiền. Một truy vấn projection có thể trả về `OrderSummary` thay vì tải toàn bộ `Order` cùng các quan hệ không cần thiết. Read model nên có kiểu dữ liệu thuộc hợp đồng ứng dụng, không để `Page<OrderJpaEntity>` hoặc một JPA proxy lọt ra ngoài adapter.

Tầng dữ liệu cũng cần cân nhắc truy vấn lặp gây N+1, tải quan hệ quá rộng, truy vấn không có phân trang và việc giữ đối tượng lazy-loaded sau khi transaction kết thúc. Đây là các vấn đề thực thi dữ liệu; tầng ứng dụng xác định dữ liệu cần cho ca sử dụng, còn adapter chọn cách lấy dữ liệu hiệu quả và đúng hợp đồng.

## 3. Trách nhiệm lưu trữ dữ liệu

**Lưu trữ dữ liệu** là ghi những thay đổi vào nguồn lưu trữ và bảo đảm thao tác tuân theo hợp đồng. Với cơ sở dữ liệu quan hệ, công việc có thể gồm tạo mới, cập nhật, xóa, flush và phối hợp với cơ chế quản lý transaction của framework.

Ví dụ, khi `PlaceOrderService` hoàn tất việc tạo đơn, nó yêu cầu `OrderRepository.save(order)`. Adapter dữ liệu chuyển đối tượng phù hợp sang dạng lưu trữ và gọi Spring Data JPA để ghi.

```java
@Repository
class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository jpaRepository;

    JpaOrderRepository(SpringDataOrderRepository jpaRepository) {
        this.jpaRepository = jpaRepository;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpaRepository.findById(id.value())
            .map(OrderJpaEntity::toDomain);
    }

    @Override
    public void save(Order order) {
        jpaRepository.save(OrderJpaEntity.fromDomain(order));
    }
}
```

Đoạn mã giả định `OrderJpaEntity` cung cấp các phương thức ánh xạ tương ứng. Trong ứng dụng thật, adapter còn có thể xử lý xóa, truy vấn tùy chỉnh, lỗi ràng buộc và chuyển đổi ngoại lệ lưu trữ thành lỗi có ý nghĩa trong hợp đồng.

### Ai chịu trách nhiệm về transaction?

Transaction là cơ chế kỹ thuật giúp một nhóm thao tác dữ liệu tuân theo tính nguyên tử và nhất quán trong phạm vi mà nguồn lưu trữ hỗ trợ. Tầng ứng dụng thường quyết định **ranh giới transaction của ca sử dụng** vì nó biết những bước nào cần thành công hoặc thất bại cùng nhau. Trong Spring, `@Transactional` thường được đặt ở application service hoặc phương thức điều phối phù hợp; repository/DAO thực hiện thao tác trong transaction đang có.

Một số phương thức Spring Data có cấu hình transaction mặc định riêng, nhưng điều đó không thay thế quyết định ranh giới của cả ca sử dụng. Nếu `PlaceOrderService` cần đọc dữ liệu, cập nhật đơn và ghi một thay đổi liên quan trong cùng cơ sở dữ liệu, transaction thường cần bao trùm các thao tác đó. Cấu hình cụ thể phụ thuộc công nghệ và mô hình nhất quán của hệ thống.

Transaction cơ sở dữ liệu không tự động bao trùm một lời gọi HTTP tới cổng thanh toán hoặc một thông điệp đã gửi tới broker. Với tác vụ liên quan nhiều hệ thống, cần cân nhắc idempotency, retry, outbox, saga hoặc thao tác bù trừ tùy yêu cầu nghiệp vụ. Không nên giữ transaction cơ sở dữ liệu mở lâu trong khi chờ mạng nếu có thể thiết kế quy trình khác phù hợp hơn.

## 4. Trách nhiệm chuyển đổi dữ liệu

Nguồn dữ liệu và mô hình nghiệp vụ thường có hình dạng khác nhau. Tầng dữ liệu chịu trách nhiệm ánh xạ giữa biểu diễn lưu trữ và kiểu dữ liệu mà hợp đồng của ứng dụng cần. Công việc này có thể bao gồm:

- Chuyển cột và kiểu SQL thành thuộc tính Java, hoặc ngược lại.
- Chuyển khóa ngoại và quan hệ bảng thành tham chiếu hoặc collection phù hợp.
- Chuyển kiểu giá trị như tiền, ngày giờ, trạng thái và định danh.
- Chuyển dữ liệu từ entity lưu trữ sang domain model hoặc read model.
- Xử lý khác biệt giữa schema hiện tại và mô hình mà ứng dụng công bố.

### Entity lưu trữ và domain model

Trong một thiết kế tách biệt, `OrderJpaEntity` là mô hình dành cho ORM, còn `Order` là mô hình miền chứa quy tắc nghiệp vụ. Adapter ánh xạ giữa hai loại này:

```java
@Entity
@Table(name = "orders")
class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "status", nullable = false)
    private String status;

    protected OrderJpaEntity() { }

    static OrderJpaEntity fromDomain(Order order) {
        OrderJpaEntity row = new OrderJpaEntity();
        row.id = order.id().value();
        row.customerId = order.customerId().value();
        row.totalAmount = order.total().amount();
        row.status = order.status().name();
        return row;
    }

    Order toDomain() {
        return Order.reconstitute(
            new OrderId(id),
            new CustomerId(customerId),
            Money.of(totalAmount),
            OrderStatus.valueOf(status)
        );
    }
}
```

Các kiểu `Order`, `OrderId`, `CustomerId`, `Money` và `OrderStatus` là mô hình miền minh họa. Phương thức `reconstitute` biểu diễn thao tác khôi phục trạng thái đã lưu; việc khôi phục cần bảo đảm bất biến của domain model. Mã ví dụ lược bỏ constructor, getter và chi tiết mapping để tập trung vào ranh giới chuyển đổi.

Tách persistence entity khỏi domain model giúp schema, annotation ORM và quan hệ lưu trữ không buộc mô hình nghiệp vụ phải thay đổi theo. Đổi lại, cần duy trì mapping và có thể phải chuyển đổi nhiều đối tượng. Với ứng dụng đơn giản, domain model có thể đồng thời là JPA entity nếu sự gắn kết đó được chấp nhận. Đây là lựa chọn kiến trúc theo độ phức tạp và nhu cầu thay đổi, không phải quy tắc bắt buộc.

### Không trộn lẫn các loại DTO

Các kiểu dữ liệu sau phục vụ những ranh giới khác nhau:

| Kiểu dữ liệu | Mục đích | Thường được dùng ở đâu |
| --- | --- | --- |
| HTTP request/response DTO | Biểu diễn hợp đồng giao tiếp với client | Presentation/API |
| Command/query model | Biểu diễn đầu vào hoặc kết quả của ca sử dụng | Application |
| Domain model | Biểu diễn khái niệm và quy tắc nghiệp vụ | Domain |
| Persistence entity/row | Biểu diễn cấu trúc lưu trữ và mapping ORM | Data access |

Không nên trả trực tiếp JPA entity từ controller. Làm vậy có thể làm lộ schema, kéo theo quan hệ lazy, gây vòng tham chiếu khi serialize hoặc khiến thay đổi cơ sở dữ liệu làm thay đổi API. Tương tự, không nên để SQL row hoặc JPA proxy trở thành kiểu trả về của application service. Hãy chuyển đổi tại ranh giới thích hợp.

## 5. Phân biệt Repository và DAO

**DAO (Data Access Object)** thường cung cấp các thao tác truy cập dữ liệu theo nguồn lưu trữ hoặc nhóm truy vấn. Nó có thể tập trung vào câu SQL, bảng hoặc thủ tục lưu trữ.

**Repository** thường được diễn đạt như một tập hợp đối tượng miền có thể truy xuất và lưu theo định danh hoặc ranh giới aggregate. Repository che giấu cách lưu trữ để phần ứng dụng làm việc bằng ngôn ngữ của miền hoặc use case.

Trong thực tế, tên gọi và cách triển khai có thể giao nhau. Spring Data JPA dùng interface repository và tạo implementation; một adapter có thể gọi DAO hoặc repository framework bên dưới. Điều quan trọng là hợp đồng công khai có diễn đạt đúng nhu cầu của bên sử dụng và implementation có che giấu chi tiết lưu trữ hay không.

Không nên tạo một repository tổng quát có hàng chục phương thức chỉ vì mọi entity đều có `save`, `delete` và `findAll`. Hợp đồng nên phản ánh thao tác thực sự cần thiết. Với aggregate, tránh cung cấp các phương thức cho phép bên ngoài sửa trực tiếp từng bảng con nếu việc đó có thể phá vỡ bất biến của aggregate.

## 6. Những gì tầng dữ liệu không nên quyết định

Tầng dữ liệu có thể kiểm tra lỗi kỹ thuật và ràng buộc lưu trữ, nhưng không nên thay thế tầng miền hoặc tầng ứng dụng trong các quyết định sau:

- Không quyết định chính sách nghiệp vụ như khách hàng nào được hoàn tiền hoặc đơn nào được hủy; nó thực thi truy vấn và lưu trạng thái mà ứng dụng/miền yêu cầu.
- Không điều phối toàn bộ ca sử dụng như gửi email, gọi thanh toán rồi thay đổi trạng thái đơn; đó là công việc của application service hoặc quy trình ứng dụng phù hợp.
- Không định dạng HTTP status, JSON response hoặc thông báo hiển thị cho người dùng; đó là trách nhiệm của presentation.
- Không để schema cơ sở dữ liệu trở thành API mà mọi tầng đều truy cập trực tiếp.

Ví dụ, adapter có thể báo `DuplicateKeyException` hoặc lỗi kết nối. Tầng ứng dụng quyết định lỗi đó có nghĩa là xung đột nghiệp vụ, có thể thử lại hay phải trả kết quả thất bại. Việc chuyển đổi ngoại lệ kỹ thuật thành loại lỗi phù hợp nên được thực hiện tại ranh giới adapter/application theo hợp đồng đã chọn; không để chi tiết JDBC hoặc JPA lan tùy tiện khắp mã nguồn.

## 7. Chất lượng và kiểm thử tầng dữ liệu

Tầng dữ liệu cần bảo đảm truy vấn đúng, mapping không làm mất ý nghĩa dữ liệu và thao tác ghi tuân thủ hợp đồng. Có thể kiểm thử theo nhiều mức:

- Kiểm thử đơn vị cho mapper: xác nhận chuyển đổi domain model và persistence entity giữ đúng định danh, tiền, trạng thái và thời gian.
- Kiểm thử tích hợp repository với cơ sở dữ liệu phù hợp: xác nhận truy vấn, ghi, quan hệ, ràng buộc và phân trang hoạt động đúng.
- Kiểm thử application service với fake repository hoặc mock port: xác nhận ca sử dụng yêu cầu đúng thao tác và xử lý kết quả phù hợp.
- Kiểm thử hiệu năng cho truy vấn quan trọng: kiểm tra số lượng truy vấn, N+1, phân trang và khối lượng dữ liệu.

Khi kiểm thử JPA, chỉ dùng cơ sở dữ liệu thay thế trong bộ test nếu hành vi SQL và dialect tương thích với môi trường chạy. Một số lỗi về kiểu dữ liệu, constraint, locking hoặc truy vấn chỉ xuất hiện trên hệ quản trị thực tế. Với luồng quan trọng, kiểm thử tích hợp trên loại cơ sở dữ liệu tương ứng giúp phát hiện sai lệch.

Các câu hỏi hữu ích khi review tầng dữ liệu:

1. Hợp đồng truy vấn có thể hiện nhu cầu của use case mà không lộ bảng hoặc framework không?
2. Adapter có xử lý phân trang, sắp xếp, tải quan hệ và giới hạn kết quả phù hợp không?
3. Mapping có giữ đúng định danh, giá trị tiền tệ, thời gian, trạng thái và bất biến khi khôi phục domain object không?
4. Transaction có bao trùm đúng các thao tác dữ liệu cần nhất quán không?
5. Lỗi kỹ thuật có được chuyển qua ranh giới bằng hợp đồng rõ ràng không?
6. Có JPA entity, lazy proxy hoặc kiểu dữ liệu của driver bị rò rỉ sang API/application không?

Tầng dữ liệu tốt giúp ứng dụng đọc và ghi dữ liệu đúng, hiệu quả và có thể thay đổi công nghệ với tác động được kiểm soát. Ranh giới rõ ràng cũng giúp kiểm thử từng phần: application tập trung vào điều phối, domain tập trung vào quy tắc nghiệp vụ, còn adapter dữ liệu tập trung vào truy vấn, lưu trữ và ánh xạ.

## Tự kiểm tra

1. Vì sao application service nên phụ thuộc vào hợp đồng repository thay vì trực tiếp tạo `EntityManager` hoặc gọi JDBC?
2. Khi nào một truy vấn danh sách nên trả về projection/read model thay vì tải toàn bộ domain aggregate?
3. Việc tách `OrderJpaEntity` khỏi `Order` mang lại lợi ích gì và tạo thêm chi phí nào?
4. Vì sao `@Transactional` ở repository không luôn thay thế được ranh giới transaction của application service?
5. Những rủi ro nào xuất hiện nếu controller trả trực tiếp JPA entity cho client?

