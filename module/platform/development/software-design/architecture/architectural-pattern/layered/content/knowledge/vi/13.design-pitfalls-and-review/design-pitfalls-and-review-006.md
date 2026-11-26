# Tránh phụ thuộc vào phiên ORM và hành vi tải dữ liệu ngầm

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, nhằm giúp người học tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Sai lầm và đánh giá thiết kế**, ta xem xét một lỗi thường gặp khi dùng ORM: để nghiệp vụ hoặc tầng trình bày phụ thuộc vào phiên ORM đang mở và vô tình kích hoạt truy vấn khi đọc thuộc tính. Hiểu vòng đời entity, ranh giới transaction và kế hoạch tải dữ liệu giúp ứng dụng dự đoán được truy vấn, tránh lỗi khi entity đã detached và giữ cho hợp đồng giữa các tầng rõ ràng.

## 1. Phiên ORM và persistence context là gì?

Với JPA, `EntityManager` quản lý một **persistence context**. Trong Hibernate, khái niệm tương ứng thường được thao tác thông qua `Session`. Persistence context theo dõi các entity đang được quản lý, nhận diện một entity theo loại và khóa chính, theo dõi thay đổi và đồng bộ các thay đổi đó xuống database khi flush.

Trong một persistence context, cùng một entity type và ID thường được biểu diễn bằng cùng một object instance. ORM cũng giữ trạng thái của entity để biết đối tượng nào đang được quản lý. Đây là lý do thay đổi một trường trên entity managed trong transaction có thể được lưu mà không cần gọi `save()` một cách tường minh trong mọi trường hợp.

Các trạng thái thường gặp của entity:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Transient / New | Đối tượng Java mới, chưa được persistence context quản lý | `new OrderEntity()` |
| Managed / Persistent | Được quản lý trong persistence context hiện tại | Entity vừa được `find()` bằng `EntityManager` |
| Detached | Từng được quản lý nhưng persistence context đã đóng hoặc entity bị detach | Entity trả ra ngoài sau khi transaction/context kết thúc |
| Removed | Được đánh dấu xóa trong persistence context | `entityManager.remove(order)` |

Persistence context có phạm vi và vòng đời. Nó thường gắn với transaction hoặc một phạm vi được framework quản lý. Không nên giữ `EntityManager`/Hibernate `Session` như một đối tượng dùng chung toàn ứng dụng, cũng không truyền nó qua thread hoặc giữ nó trong một tác vụ chạy lâu.

## 2. Lazy loading là hành vi có điều kiện, không phải getter thuần dữ liệu

ORM có thể trì hoãn việc nạp quan hệ cho đến khi ứng dụng truy cập quan hệ đó. Ví dụ `OrderEntity` có danh sách `lines`; Hibernate có thể chỉ nạp đơn hàng trước, rồi mới truy vấn các dòng hàng khi gọi `order.getLines()`.

```java
@Entity
class OrderEntity {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public List<OrderLineEntity> getLines() {
        return lines;
    }
}
```

Với quan hệ lazy, collection trả về có thể là proxy hoặc persistent collection do ORM quản lý. Khi được truy cập trong lúc persistence context còn hoạt động, thao tác tưởng như chỉ đọc dữ liệu có thể phát sinh SQL. Vì vậy, getter của entity ORM không phải lúc nào cũng là một phép đọc bộ nhớ đơn giản.

JPA có quy tắc mặc định fetch khác nhau giữa các loại quan hệ: `@OneToMany` và `@ManyToMany` mặc định LAZY, còn `@ManyToOne` và `@OneToOne` mặc định EAGER theo đặc tả. Có thể khai báo tường minh để ý định rõ ràng hơn. Tuy nhiên, đặt mọi quan hệ thành EAGER không phải cách sửa an toàn: nó có thể làm truy vấn tải quá nhiều dữ liệu và tạo đồ thị object lớn ngoài nhu cầu của use case.

## 3. LazyInitializationException và entity detached

Nếu một entity có quan hệ lazy được truy cập sau khi persistence context đã đóng, ORM không còn nơi để thực hiện truy vấn bổ sung. Với Hibernate, tình huống này thường gây `LazyInitializationException`.

Ví dụ service tải một đơn hàng rồi trả entity ra ngoài:

```java
@Service
class OrderService {
    private final OrderRepository orders;

    OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderEntity findOrder(Long id) {
        return orders.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
```

Nếu controller hoặc serializer gọi `order.getLines()` sau khi transaction và persistence context đã kết thúc, collection có thể không còn được nạp. Việc đọc một thuộc tính ở tầng ngoài làm ứng dụng phát sinh lỗi, dù phương thức service đã trả về thành công.

Không nên chữa lỗi bằng cách mở persistence context vô thời hạn hoặc gọi `Hibernate.initialize()` ở nhiều nơi mà không xác định nhu cầu dữ liệu. Cần thiết kế use case để biết rõ dữ liệu nào phải được nạp và chuyển kết quả ra khỏi ranh giới persistence dưới dạng phù hợp.

## 4. Open Session in View có thể che khuất ranh giới

Một số ứng dụng Spring cấu hình Open Session in View (OSIV), giữ persistence context mở trong suốt vòng đời HTTP request. Khi controller hoặc view truy cập một quan hệ lazy, ORM vẫn có thể truy vấn database dù transaction của application service đã kết thúc.

OSIV có thể làm một số lỗi lazy loading không xuất hiện ngay, nhưng nó cũng khiến việc đọc dữ liệu ở tầng trình bày âm thầm kích hoạt SQL. Một endpoint trả về danh sách đơn hàng rồi serializer đọc `customer`, `lines` và `product` có thể tạo ra nhiều truy vấn ngoài dự kiến.

OSIV không đồng nghĩa toàn bộ request chạy trong một transaction duy nhất. Persistence context có thể còn mở trong khi transaction nghiệp vụ đã hoàn tất; truy vấn lazy phát sinh sau đó có thể chạy trong transaction/connection riêng theo cấu hình. Vì vậy, các lần đọc có thể không cùng một ranh giới nhất quán với thao tác nghiệp vụ ban đầu.

Đối với ứng dụng phân tầng, thường dễ kiểm soát hơn khi application service xác định kế hoạch đọc, hoàn tất việc ánh xạ DTO trong ranh giới transaction cần thiết, rồi trả dữ liệu thuần cho tầng trình bày. OSIV có thể được giữ trong một số ứng dụng có chủ đích, nhưng không nên dựa vào nó để che việc thiếu fetch plan.

## 5. N+1 query: dấu hiệu tải quan hệ ngầm

Giả sử trang danh sách hiển thị 50 đơn hàng và tên khách hàng của mỗi đơn. Truy vấn đầu tiên lấy 50 đơn. Nếu `customer` là lazy và mỗi lần gọi `order.getCustomer().getName()` tạo một truy vấn riêng, tổng số truy vấn có thể là 1 + 50. Đây là vấn đề **N+1 query**.

```java
List<OrderEntity> orders = orderRepository.findRecentOrders();

for (OrderEntity order : orders) {
    // Nếu customer chưa được nạp, mỗi lần truy cập có thể phát sinh SQL.
    log.info("Customer: {}", order.getCustomer().getName());
}
```

N+1 không chỉ xảy ra trong vòng lặp viết tường minh. Nó có thể xuất hiện trong mapper, getter lồng nhau, template engine, JSON serializer hoặc `toString()`/`equals()` được viết để truy cập quan hệ. Vì truy vấn nằm sau một thao tác đọc tưởng như bình thường, rất dễ bỏ sót khi review code.

Không phải mọi lần truy cập lazy đều tạo truy vấn mới. Persistence context có thể đã chứa entity liên quan, hoặc ORM có batch fetching. Nhưng nếu không có kế hoạch tải, số lượng truy vấn có thể tăng theo số bản ghi và gây chậm rõ rệt khi dữ liệu thực tế lớn hơn dữ liệu phát triển.

## 6. Xác định dữ liệu cần cho use case trước khi truy vấn

Mỗi use case đọc nên xác định dữ liệu thực sự cần trả về. Trang danh sách đơn hàng có thể chỉ cần mã đơn, trạng thái, ngày tạo, tên khách hàng và tổng tiền. Trang chi tiết có thể cần địa chỉ giao hàng và các dòng hàng. Hai nhu cầu này không nhất thiết phải tải cùng một đồ thị entity.

Một cách tốt là thiết kế query theo mục đích:

| Use case | Dữ liệu cần | Cách tải có thể phù hợp |
|---|---|---|
| Danh sách đơn hàng | ID, trạng thái, ngày tạo, tổng tiền, tên khách | DTO projection |
| Chi tiết một đơn | Thông tin đơn và các dòng hàng | Fetch join hoặc entity graph có giới hạn |
| Báo cáo doanh thu | Nhóm, tổng và số lượng | Aggregate query/projection |
| Cập nhật trạng thái đơn | Aggregate cần thay đổi và dữ liệu cần để kiểm tra bất biến | Tải aggregate trong transaction |

Kế hoạch tải là một phần của thiết kế use case, không nên để serializer tự quyết định qua việc đọc getter.

## 7. Dùng DTO projection cho truy vấn đọc

Nếu chỉ cần dữ liệu để hiển thị, truy vấn có thể trả DTO thay vì entity ORM. DTO không mang proxy lazy và không cho tầng trình bày vô tình tải thêm quan hệ.

```java
public record OrderSummary(
    Long id,
    String status,
    String customerName,
    BigDecimal total
) {}
```

JPQL constructor projection:

```java
public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query("""
        select new com.example.orders.application.OrderSummary(
            o.id, o.status, c.name, o.total
        )
        from OrderEntity o
        join o.customer c
        where o.createdAt >= :from
        order by o.createdAt desc, o.id desc
        """)
    List<OrderSummary> findSummariesSince(Instant from);
}
```

Ví dụ dùng projection với các trường được chọn rõ. Tên package DTO trong JPQL cần là tên đầy đủ của lớp; kiểu tham số và thuộc tính phải khớp entity thực tế. Spring Data cũng hỗ trợ interface projection hoặc projection dựa trên truy vấn khác tùy trường hợp.

Application service có thể trả `List<OrderSummary>` cho controller. Tầng trình bày chuyển DTO thành response JSON mà không cần giữ persistence context mở. DTO cũng tạo hợp đồng rõ ràng, tránh vô tình công khai trường nội bộ hoặc quan hệ ORM.

## 8. Dùng fetch join hoặc EntityGraph khi cần entity graph

Với use case cần aggregate đầy đủ để thực hiện nghiệp vụ, có thể tải các quan hệ cần thiết trong truy vấn. JPQL `join fetch` là một lựa chọn:

```java
@Query("""
    select distinct o
    from OrderEntity o
    left join fetch o.lines
    where o.id = :id
    """)
Optional<OrderEntity> findWithLinesById(Long id);
```

Truy vấn này tải đơn hàng cùng các dòng hàng trong một lần truy vấn. `distinct` giúp loại trùng root entity trong kết quả ở các tình huống join collection; cách ORM xử lý SQL và kết quả còn phụ thuộc provider.

Spring Data JPA cũng hỗ trợ `@EntityGraph` để khai báo thuộc tính cần tải theo phương thức repository:

```java
@EntityGraph(attributePaths = {"customer", "lines"})
Optional<OrderEntity> findDetailedById(Long id);
```

EntityGraph hữu ích khi muốn mô tả fetch plan mà không viết JPQL join thủ công. Tuy nhiên, không nên tải toàn bộ quan hệ chỉ vì có thể. Hãy chọn đúng graph theo use case, xem SQL được sinh và kiểm tra số lượng bản ghi/join.

**Lưu ý với phân trang và collection:** fetch join một collection cùng phân trang có thể tạo kết quả sai kỳ vọng hoặc khiến Hibernate phải lấy nhiều hàng rồi phân trang trong bộ nhớ; một số cấu hình có thể phát cảnh báo hoặc ném lỗi. Không nên áp dụng collection fetch join trực tiếp cho truy vấn page lớn. Có thể phân trang ID trước, sau đó tải quan hệ cho tập ID đó bằng truy vấn thứ hai, hoặc dùng DTO projection phù hợp. Nếu dùng hai bước, cần giữ thứ tự trang và xử lý trường hợp dữ liệu thay đổi giữa hai truy vấn theo mức nhất quán của use case.

## 9. Batch fetching và giới hạn của nó

Khi cần truy cập một quan hệ lazy cho nhiều entity, batch fetching có thể gom nhiều khóa vào một truy vấn thay vì phát một truy vấn cho mỗi entity. Hibernate hỗ trợ `@BatchSize` hoặc cấu hình `hibernate.default_batch_fetch_size`.

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 25)
private List<OrderLineEntity> lines = new ArrayList<>();
```

Batch fetching có thể giảm số truy vấn trong một số tình huống, nhưng không thay thế việc thiết kế fetch plan. Nó vẫn có thể tải dữ liệu không cần thiết, phụ thuộc vào cách truy cập và giới hạn batch, và không biến một truy vấn đọc thiếu kiểm soát thành hợp đồng rõ ràng. Với endpoint danh sách, DTO projection thường dễ dự đoán hơn nếu chỉ cần một số trường.

## 10. Giữ transaction và persistence context ở đúng ranh giới

Application service thường là nơi xác định ranh giới transaction cho một use case. Nếu cần cập nhật aggregate, service tải aggregate, gọi hành vi miền và lưu thay đổi trong cùng transaction. Nếu cần đọc DTO, service có thể thực hiện truy vấn và ánh xạ kết quả trong transaction rồi trả DTO ra ngoài.

```java
@Service
class OrderQueryService {
    private final OrderJpaRepository repository;

    OrderQueryService(OrderJpaRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> recentOrders(Instant from) {
        return repository.findSummariesSince(from);
    }
}
```

Ở đây, query trả DTO đã hoàn chỉnh; controller không cần truy cập lazy association. `readOnly = true` là gợi ý/hint cho transaction và provider, không phải cơ chế bảo đảm mọi thao tác ghi đều bị chặn trong tất cả cấu hình.

Không nên để transaction kéo dài qua thao tác chờ người dùng, gọi dịch vụ mạng lâu hoặc xử lý batch không giới hạn. Persistence context dài làm tăng bộ nhớ, giữ nhiều entity managed và có thể kéo theo thời gian khóa hoặc kết nối dài tùy cách quản lý. Với batch lớn, hãy xử lý theo từng chunk, flush/clear phù hợp và xác định ranh giới transaction.

## 11. Entity không phải response DTO

Trả JPA entity trực tiếp từ controller có thể tạo nhiều vấn đề:

- JSON serializer truy cập lazy association và kích hoạt truy vấn ngoài dự kiến.
- Quan hệ hai chiều có thể gây vòng lặp serialization.
- Cấu trúc bảng và entity trở thành hợp đồng API; thay đổi mapping có thể làm thay đổi JSON.
- Các trường nội bộ, dữ liệu nhạy cảm hoặc quan hệ không nên công khai có thể bị lộ.
- Response có thể phụ thuộc vào persistence context còn mở.

Thay vì trả `OrderEntity`, hãy định nghĩa DTO cho response:

```java
public record OrderDetailResponse(
    String orderNumber,
    String status,
    List<OrderLineResponse> lines
) {}

public record OrderLineResponse(
    String productCode,
    String productName,
    int quantity
) {}
```

Mapper chuyển từ DTO query hoặc dữ liệu đã tải tường minh sang response. Việc mapping nên diễn ra ở application/presentation boundary trong khi dữ liệu cần thiết còn sẵn sàng. Tránh để serializer tự đi sâu vào entity graph.

## 12. Detached entity và thao tác merge

Khi persistence context đóng, entity được trả ra ngoài thường trở thành detached. Thay đổi trường trên detached entity không tự động được dirty checking ghi xuống database. JPA `merge()` sao chép trạng thái của đối tượng detached vào một instance managed; giá trị trả về từ `merge()` mới là instance managed. Đối tượng đầu vào vẫn detached.

Điều này quan trọng khi nhận entity từ tầng trình bày hoặc dùng entity làm request DTO. Không nên nhận một object graph do client gửi rồi `merge()` nguyên trạng vào database: client có thể bỏ sót trường, gửi ID quan hệ không hợp lệ hoặc ghi đè dữ liệu ngoài quyền của họ. Hãy nhận command/DTO, tải aggregate hiện có trong transaction, kiểm tra quyền và yêu cầu aggregate thực hiện hành vi cần thiết.

Ví dụ cập nhật trạng thái an toàn hơn:

```java
@Transactional
public void markAsPaid(OrderId id) {
    Order order = orders.findById(id)
        .orElseThrow(() -> new OrderNotFoundException(id));

    order.markAsPaid();
    orders.save(order);
}
```

Use case làm việc với mô hình nghiệp vụ và repository port. Adapter persistence quản lý việc tải và lưu entity ORM. Không để controller tự giữ entity qua nhiều request hoặc tự sửa các trường của entity detached.

## 13. Các dấu hiệu thiết kế cần review

Khi review code dùng ORM, hãy chú ý các dấu hiệu sau:

| Dấu hiệu | Rủi ro | Hướng xử lý |
|---|---|---|
| Controller hoặc serializer gọi getter của lazy association | SQL phát sinh ở tầng trình bày, có thể gây N+1 | Trả DTO đã hoàn chỉnh từ query/application service |
| Service trả entity rồi tầng khác tiếp tục truy cập quan hệ | Phụ thuộc vào persistence context và OSIV | Chốt fetch plan và ánh xạ trong ranh giới phù hợp |
| Đặt mọi quan hệ thành EAGER | Tải quá nhiều dữ liệu, join không cần thiết | Dùng LAZY mặc định có chủ đích và fetch theo use case |
| Một vòng lặp truy cập quan hệ trên nhiều entity | N+1 query | Projection, fetch join có giới hạn, EntityGraph hoặc batch fetching |
| `toString()`, `equals()` hoặc `hashCode()` duyệt quan hệ lazy | Truy vấn bất ngờ, đệ quy hoặc lỗi detached | Dựa trên trường ổn định, không duyệt association tùy tiện |
| Entity được giữ trong session hoặc truyền qua thread | Sai vòng đời, lỗi đồng thời và rò rỉ context | Truyền ID/DTO và tải lại trong transaction của tác vụ |
| Dùng `merge()` trực tiếp object graph từ request | Ghi đè trường hoặc quan hệ ngoài ý muốn | Map command vào aggregate đã tải và kiểm tra quyền |

Không phải mọi lazy loading đều sai. Lazy loading là công cụ hữu ích khi quan hệ không phải lúc nào cũng cần. Vấn đề xuất hiện khi việc nạp dữ liệu không được kiểm soát và tầng gọi không biết một thao tác truy cập sẽ phát sinh SQL.

## 14. Kiểm thử để phát hiện tải dữ liệu ngầm

Unit test miền không thể phát hiện N+1 vì nó không chạy ORM. Cần kiểm thử ở ranh giới repository/adapter và quan sát SQL thực tế:

- Integration test repository xác minh fetch plan và mapping với database thử nghiệm.
- Đếm số câu SQL khi tải một trang có nhiều bản ghi; số truy vấn không nên tăng tuyến tính theo số dòng nếu use case được thiết kế để tải theo batch/projection.
- Kiểm tra truy cập lazy sau khi transaction kết thúc không nằm trong hợp đồng trả về; response DTO phải sử dụng được sau khi persistence context đóng.
- Kiểm thử phân trang cùng quan hệ collection để phát hiện việc join làm nhân bản bản ghi hoặc phân trang trong bộ nhớ.
- Dùng Hibernate statistics, datasource proxy hoặc log SQL trong môi trường test để quan sát số lần prepare/execute query.
- Kiểm tra endpoint serialization để chắc chắn không có truy vấn database phát sinh từ getter trong quá trình tạo JSON.

Ví dụ, tạo 1 đơn hàng và tạo 50 đơn hàng rồi so sánh số truy vấn của use case danh sách. Nếu số truy vấn tăng từ vài truy vấn lên hơn 50, có thể có N+1. Cần kiểm tra cả số hàng trả về và dữ liệu response, vì giảm query count mà thiếu dữ liệu cũng không phải kết quả đúng.

## 15. Quy trình chọn fetch strategy

Khi thiết kế một use case đọc hoặc cập nhật, hãy thực hiện theo các bước:

1. Xác định dữ liệu đầu ra hoặc bất biến mà use case cần xử lý.
2. Quyết định nên trả DTO/projection hay cần aggregate managed.
3. Chọn query, fetch join hoặc EntityGraph cho đúng quan hệ cần thiết.
4. Kiểm tra phân trang, số lượng bản ghi và nguy cơ nhân bản hàng khi join collection.
5. Giữ việc đọc lazy trong transaction/persistence context có chủ đích.
6. Ánh xạ dữ liệu ra DTO trước khi rời ranh giới persistence nếu caller không cần entity.
7. Đo số truy vấn và độ trễ với kích thước dữ liệu gần thực tế.

Không có một fetch strategy đúng cho mọi use case. Một aggregate nhỏ có thể được tải cùng một số quan hệ; một danh sách lớn thường phù hợp hơn với projection; báo cáo tổng hợp có thể dùng truy vấn aggregate trực tiếp. Hãy chọn theo dữ liệu cần và chi phí thực tế.

## 16. Ghi nhớ

Persistence context/ORM session quản lý vòng đời entity và có thể thực hiện truy vấn khi ứng dụng truy cập quan hệ lazy. Nếu entity rời context rồi mới được truy cập, Hibernate có thể ném `LazyInitializationException`; nếu context vẫn mở qua OSIV, truy vấn ngầm có thể xuất hiện ở controller hoặc serializer và tạo N+1. Hãy để application service xác định dữ liệu use case cần, dùng DTO projection cho truy vấn đọc, fetch join hoặc EntityGraph có giới hạn khi cần entity graph, và giữ transaction ở phạm vi rõ ràng. Không trả JPA entity trực tiếp qua API, không dựa vào OSIV để che fetch plan, và không `merge()` tùy tiện object graph từ request. Kiểm thử integration với SQL/query count và dữ liệu đủ lớn để phát hiện tải ngầm, phân trang sai và phụ thuộc vào persistence context.
