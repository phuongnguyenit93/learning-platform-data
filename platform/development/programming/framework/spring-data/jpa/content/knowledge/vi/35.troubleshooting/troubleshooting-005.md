# TransientPropertyValueException và tham chiếu chưa được lưu

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Chẩn đoán lỗi

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao Hibernate ném TransientPropertyValueException khi một entity tham chiếu đến đối tượng liên quan chưa được lưu.
- Phân biệt entity transient, managed và detached.
- Xác định association và thuộc tính gây lỗi từ thông báo exception.
- Chọn đúng cách xử lý: tải entity đã tồn tại, lưu entity mới trước hoặc cấu hình cascade theo vòng đời aggregate.
- Hiểu owning side của quan hệ hai chiều và cập nhật đồng bộ hai phía.
- Phân biệt CascadeType.PERSIST, MERGE và ALL.
- Biết thời điểm lỗi xuất hiện khi persist, flush hoặc commit.
- Viết kiểm thử tích hợp để xác nhận quan hệ được lưu đúng và giao dịch rollback khi dữ liệu không hợp lệ.

## 2. TransientPropertyValueException là gì?

TransientPropertyValueException là exception của Hibernate, thuộc nhóm TransientObjectException. Nó thường xuất hiện khi một entity sắp được lưu hoặc flush có association trỏ đến một đối tượng transient chưa được quản lý và chưa được lưu vào cơ sở dữ liệu, trong khi thao tác persist không có cascade phù hợp để lưu đối tượng đó.

Ví dụ: ứng dụng tạo một PurchaseOrder mới và gán cho nó một Customer vừa được tạo bằng toán tử new. Nếu PurchaseOrder không cascade thao tác PERSIST tới Customer, Hibernate không thể ghi khóa ngoại customer_id trỏ đến một bản ghi Customer chưa tồn tại.

Thông báo thường cho biết entity sở hữu thuộc tính quan hệ, tên thuộc tính và kiểu entity transient. Hãy đọc đầy đủ thông báo và stack trace để xác định đúng association thay vì chỉ nhìn dòng repository.save() nơi exception được quan sát.

Lỗi này phản ánh một vấn đề trong vòng đời entity hoặc cách xây dựng object graph. Nó không đơn thuần có nghĩa là thiếu một ID hay cần gọi save() thêm một lần trên mọi Repository.

## 3. Hiểu vòng đời entity trong JPA

Một entity thường ở một trong các trạng thái sau:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Transient | Đối tượng Java mới, chưa được persistence context quản lý và chưa có bản ghi được lưu | new Customer() |
| Managed | Đang được một EntityManager quản lý; thay đổi có thể được dirty checking ghi xuống DB | Entity trả về từ findById trong transaction |
| Detached | Đã từng được quản lý nhưng hiện không còn thuộc persistence context đang hoạt động | Entity lấy từ request trước hoặc EntityManager đã đóng |
| Removed | Đã được đánh dấu xóa trong persistence context | entityManager.remove(customer) |

Điểm quan trọng: một object Java có ID không tự động trở thành managed. Gán một ID vào đối tượng mới không chứng minh bản ghi tương ứng tồn tại, cũng không đưa đối tượng vào persistence context.

Ví dụ:

~~~java
Customer customer = new Customer();
customer.setName("An");

PurchaseOrder order = new PurchaseOrder();
order.setCustomer(customer);
~~~

Cả hai object đều mới. Nếu lưu order mà không có cascade PERSIST phù hợp, Hibernate phát hiện order.customer trỏ đến Customer transient và có thể ném TransientPropertyValueException khi flush.

Detached khác transient. Một entity detached từng được lưu trước đó nhưng không còn được quản lý. Các lỗi liên quan detached có thể có dạng khác, chẳng hạn Detached entity passed to persist. Đừng xử lý mọi lỗi liên quan association bằng cách thêm cascade PERSIST một cách máy móc.

## 4. Ví dụ quan hệ gây lỗi

Giả sử một đơn hàng luôn thuộc về một khách hàng. Customer là dữ liệu độc lập, có thể được nhiều đơn hàng cùng tham chiếu.

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

Entity đơn hàng:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }
}
~~~

@ManyToOne không cascade thao tác nào theo mặc định. Đoạn code sau có thể gây lỗi:

~~~java
@Transactional
public Long createOrder() {
    Customer customer = new Customer("An");

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

Spring Data JPA gọi persist hoặc merge tùy việc entity được nhận diện là mới hay đã tồn tại. Nếu thao tác thực tế là persist và không có cascade PERSIST đến customer, Hibernate không thể lưu object graph này. Lỗi có thể xuất hiện ngay trong quá trình persist hoặc muộn hơn khi flush/commit.

Không nên khắc phục bằng cách gán một ID giả cho Customer. ID giả không làm bản ghi xuất hiện trong database và có thể dẫn đến lỗi khóa ngoại hoặc lỗi trạng thái entity khác.

## 5. Cách 1: tham chiếu đến entity đã tồn tại bằng entity được quản lý

Nếu Customer đã có trong database, hãy lấy entity đó trong transaction rồi gán vào PurchaseOrder.

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final CustomerRepository customerRepository;
    private final PurchaseOrderRepository orderRepository;

    @Transactional
    public Long createOrder(Long customerId) {
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy khách hàng"));

        PurchaseOrder order = new PurchaseOrder(customer);

        return orderRepository.save(order).getId();
    }
}
~~~

findById trả về Customer được quản lý trong persistence context của transaction hiện tại. Khi lưu PurchaseOrder, Hibernate có thể dùng khóa chính của Customer để ghi customer_id.

Đây thường là cách rõ ràng nhất khi nghiệp vụ cần xác nhận khách hàng tồn tại và có thể cần đọc thêm thông tin của khách hàng.

### 5.1. Dùng getReferenceById khi chỉ cần tham chiếu

Nếu chỉ cần gắn khóa ngoại và không cần đọc thuộc tính Customer, có thể dùng:

~~~java
@Transactional
public Long createOrder(Long customerId) {
    Customer customer = customerRepository.getReferenceById(customerId);

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

getReferenceById có thể trả về proxy mà không truy vấn ngay dữ liệu đầy đủ. Khi entity được sử dụng, provider có thể tải dữ liệu. Nếu ID không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được truy cập hoặc khi thao tác database thực sự kiểm tra khóa ngoại.

Nếu API cần trả lỗi 404 rõ ràng khi khách hàng không tồn tại, findById thường dễ kiểm soát hơn. Không dùng getReferenceById như bằng chứng rằng bản ghi đã tồn tại.

## 6. Cách 2: lưu entity liên quan trước khi lưu entity tham chiếu

Nếu Customer thực sự là dữ liệu mới và không thuộc vòng đời được cascade từ PurchaseOrder, hãy lưu Customer trước:

~~~java
@Transactional
public Long createOrder(String customerName) {
    Customer customer = customerRepository.save(
            new Customer(customerName));

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

Sau khi save Customer thành công, giá trị trả về là entity được lưu. Gán entity trả về cho PurchaseOrder rồi lưu đơn hàng.

Cả hai thao tác nằm trong cùng transaction Service. Nếu lưu đơn hàng thất bại và exception làm giao dịch rollback, việc tạo Customer cũng được rollback cùng transaction.

Không nhất thiết phải gọi saveAndFlush() sau Customer. Hibernate có thể sắp xếp thao tác SQL phù hợp khi flush. Chỉ flush sớm khi có lý do cụ thể, chẳng hạn muốn phát hiện lỗi ràng buộc tại một điểm rõ ràng hoặc cần ID/SQL được tạo trước khi thực hiện bước tiếp theo.

## 7. Cách 3: cascade PERSIST cho quan hệ thuộc cùng aggregate

Cascade phù hợp khi entity gốc quản lý vòng đời của entity con. Ví dụ, OrderLine được tạo và xóa cùng PurchaseOrder, không có vòng đời độc lập trong nghiệp vụ.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public Long getId() {
        return id;
    }
}
~~~

OrderLine là entity con:

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(Product product, int quantity) {
        this.product = product;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Service tạo aggregate:

~~~java
@Transactional
public Long createOrder(Long customerId, Long productId, int quantity) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Không tìm thấy khách hàng"));

    Product product = productRepository.findById(productId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Không tìm thấy sản phẩm"));

    PurchaseOrder order = new PurchaseOrder(customer);
    order.addLine(new OrderLine(product, quantity));

    return orderRepository.save(order).getId();
}
~~~

Khi persist PurchaseOrder, cascade PERSIST từ order.lines yêu cầu Hibernate persist các OrderLine mới. Customer và Product là các entity đã tồn tại và được quản lý, vì vậy không cần cascade PERSIST từ OrderLine sang hai tham chiếu đó.

### 7.1. Vì sao cascade đặt ở PurchaseOrder.lines?

PurchaseOrder là aggregate root quản lý vòng đời OrderLine. Khi tạo đơn hàng, các dòng hàng mới được tạo cùng đơn hàng. Khi xóa một dòng khỏi collection, orphanRemoval = true thể hiện rằng dòng hàng không còn thuộc aggregate và có thể bị xóa khi flush.

Cascade PERSIST trên collection giúp thao tác persist từ root truyền xuống entity con. Việc đặt cascade phải theo quan hệ sở hữu vòng đời trong nghiệp vụ, không chỉ theo việc muốn hết exception.

## 8. Không cascade PERSIST bừa bãi cho quan hệ dùng chung

Customer thường có thể được nhiều PurchaseOrder tham chiếu. Customer không phải entity con được sở hữu bởi một đơn hàng cụ thể.

Không nên mặc định khai báo:

~~~java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
~~~

Cascade ALL bao gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH. Khi xóa một PurchaseOrder, cascade REMOVE có thể lan sang Customer và gây xóa dữ liệu dùng chung hoặc vi phạm khóa ngoại.

Với quan hệ nhiều đơn hàng cùng tham chiếu một khách hàng, thông thường chỉ cần gán một Customer managed/reference vào PurchaseOrder và không cascade thao tác xóa.

Nguyên tắc thực tế:

- Cascade PERSIST khi entity gốc tạo và quản lý vòng đời entity con mới.
- Cascade MERGE khi muốn thao tác merge trên root lan tới entity liên quan theo đúng mô hình.
- Cascade REMOVE chỉ khi entity liên quan thực sự phải bị xóa cùng root.
- Cascade ALL chỉ khi toàn bộ vòng đời của entity liên quan thực sự phụ thuộc vào root.

Không thêm cascade chỉ để làm exception biến mất. Hãy xem xét ai tạo, ai cập nhật và ai chịu trách nhiệm xóa dữ liệu liên quan.

## 9. Phân biệt PERSIST và MERGE trong Spring Data JPA

Repository.save(entity) không phải lúc nào cũng gọi cùng một thao tác JPA. Spring Data JPA kiểm tra entity có được coi là mới hay không:

- Entity mới thường được persist.
- Entity đã tồn tại hoặc được nhận diện là không mới thường được merge.

Vì vậy, cascade phải phù hợp với thao tác thực tế. CascadeType.MERGE không thay thế CascadeType.PERSIST khi một entity mới được persist. Nếu root mới được persist và có association transient, chỉ khai báo MERGE sẽ không tự giải quyết đường persist đó.

Một điểm quan trọng: EntityManager.merge trả về một instance managed. Instance truyền vào có thể vẫn detached. Vì vậy, khi dùng save cho entity detached hoặc trường hợp merge, hãy tiếp tục dùng đối tượng trả về:

~~~java
PurchaseOrder managedOrder = orderRepository.save(order);
~~~

Không giả định save luôn biến chính object ban đầu thành managed.

Nếu entity dùng ID tự gán hoặc có quy tắc nhận diện trạng thái mới tùy chỉnh, hãy kiểm tra cơ chế isNew của Spring Data, trường @Version hoặc Persistable.isNew(). Nhận diện sai trạng thái có thể làm Spring chọn persist/merge không như dự kiến.

## 10. Owning side của quan hệ hai chiều

JPA dùng owning side để xác định cột khóa ngoại được ghi. Trong ví dụ PurchaseOrder và OrderLine:

- OrderLine.order là phía sở hữu vì có @ManyToOne và cột order_id.
- PurchaseOrder.lines là phía nghịch đảo vì dùng mappedBy = "order".

Nếu chỉ thêm OrderLine vào collection PurchaseOrder.lines mà không gán OrderLine.order, phía sở hữu vẫn chưa được cập nhật. Database có thể không ghi khóa ngoại như mong muốn.

Helper addLine cập nhật cả hai phía:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this);
}
~~~

Tương tự, nếu bỏ dòng hàng, nên có helper duy trì cả collection và tham chiếu ngược:

~~~java
public void removeLine(OrderLine line) {
    lines.remove(line);
    line.setOrder(null);
}
~~~

Với orphanRemoval = true, việc loại entity khỏi collection được quản lý có thể đánh dấu entity con để xóa khi flush. Cần bảo đảm logic nghiệp vụ cho phép thao tác này và không tái sử dụng entity con đã bị orphan.

Thiếu cập nhật owning side thường gây lỗi khóa ngoại null hoặc dữ liệu quan hệ không như mong muốn. Đây là vấn đề khác với TransientPropertyValueException, nhưng có thể xuất hiện cùng lúc trong một object graph được dựng chưa đúng.

## 11. Lỗi xuất hiện ở persist, flush hay commit?

JPA có thể trì hoãn SQL cho tới khi flush. Vì vậy, dòng code gây lỗi không nhất thiết là dòng thực hiện INSERT.

Một luồng phổ biến:

1. Service tạo entity và gán association.
2. Repository.save gọi persist hoặc merge.
3. Hibernate đưa entity vào persistence context.
4. Khi flush, Hibernate kiểm tra association và lập lịch SQL.
5. Nếu một tham chiếu transient không được cascade persist, Hibernate ném exception.
6. Giao dịch thất bại và phải rollback.

Flush có thể xảy ra khi gọi saveAndFlush, EntityManager.flush, trước một query theo FlushMode AUTO hoặc khi transaction commit.

Để khoanh vùng lỗi trong môi trường phát triển, có thể flush rõ ràng sau khi dựng aggregate:

~~~java
@Transactional
public Long createOrder(...) {
    PurchaseOrder order = buildOrder(...);

    PurchaseOrder saved = orderRepository.save(order);
    orderRepository.flush();

    return saved.getId();
}
~~~

Đây là kỹ thuật chẩn đoán hoặc khi cần đồng bộ SQL tại một điểm xác định. Flush không phải commit. Sau flush, giao dịch vẫn có thể rollback và các thay đổi chưa được xác nhận hoàn tất.

Không thêm flush sau mọi thao tác Repository một cách tùy tiện vì có thể làm giảm batching và tăng số lần đồng bộ database.

## 12. Cách đọc exception và tìm association lỗi

Khi gặp TransientPropertyValueException:

1. Đọc root cause đầy đủ trong stack trace; lớp bọc bên ngoài có thể là exception được Spring dịch.
2. Tìm tên entity sở hữu thuộc tính quan hệ.
3. Tìm tên thuộc tính và kiểu entity transient được nhắc trong thông báo.
4. Mở mapping của association đó để xem cascade, optional, JoinColumn và mappedBy.
5. Kiểm tra object graph ngay trước save/flush.
6. Xác định entity liên quan phải là bản ghi có sẵn, entity mới thuộc aggregate hay entity detached.
7. Chọn cách tải/lưu/cascade tương ứng rồi kiểm thử lại.

Ví dụ nếu thông báo chỉ ra PurchaseOrder.customer tham chiếu Customer chưa lưu, hãy kiểm tra nơi tạo PurchaseOrder và cách gán Customer. Nếu thông báo chỉ ra OrderLine.product, hãy kiểm tra việc tải Product hiện hữu hoặc việc tạo Product mới có đúng nghiệp vụ không.

Không nên chỉ sửa association đầu tiên nhìn thấy. Một entity có thể có nhiều quan hệ; sau khi sửa lỗi đầu tiên, flush có thể phát hiện một association transient khác.

## 13. Phân biệt với các lỗi liên quan

| Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| TransientPropertyValueException | Association trỏ tới entity transient không được cascade persist | Entity liên quan đã được lưu chưa, cascade có đúng không |
| Detached entity passed to persist | Persist một entity detached đã có identity | Có đang persist nhầm entity đã tồn tại không; có cần reference managed hoặc merge không |
| PropertyValueException | Thuộc tính bắt buộc bị null hoặc giá trị không hợp lệ theo mapping | Kiểm tra dữ liệu và nullable/optional |
| DataIntegrityViolationException hoặc lỗi FK | Database từ chối khóa ngoại hoặc constraint | Kiểm tra ID tham chiếu có bản ghi thật không, constraint và thứ tự ghi |
| EntityNotFoundException | Tham chiếu hoặc proxy yêu cầu một entity không tồn tại | Kiểm tra ID, dữ liệu bị xóa và thời điểm truy cập proxy |

Tên exception bên ngoài có thể khác tùy Spring, Hibernate và thời điểm lỗi. Luôn xem cause chain và thông báo database nếu có.

Đặc biệt, tạo một object Customer chỉ có ID tự gán không giống với việc lấy một reference hợp lệ từ EntityManager. Nếu ID không tồn tại, database có thể báo lỗi khóa ngoại khi ghi. Nếu ID trùng bản ghi đã tồn tại, object tự tạo vẫn không tự động trở thành entity managed.

## 14. Transaction và xử lý exception

Nên đặt thao tác dựng aggregate và lưu các entity liên quan trong một Service transaction:

~~~java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    Customer customer = customerRepository.findById(command.customerId())
            .orElseThrow(() ->
                    new EntityNotFoundException("Không tìm thấy khách hàng"));

    PurchaseOrder order = new PurchaseOrder(customer);
    // Thêm các dòng hàng và cập nhật owning side.

    return orderRepository.save(order).getId();
}
~~~

Nếu exception xảy ra trong transaction, hãy để lỗi phù hợp truyền ra ngoài để Spring rollback theo quy tắc mặc định. Spring mặc định rollback với RuntimeException và Error. Nếu chuyển exception thành checked exception, cần cân nhắc rollbackFor phù hợp.

Không bắt TransientPropertyValueException rồi ghi log và tiếp tục trong cùng transaction. Sau lỗi persistence, transaction hoặc persistence context có thể đã ở trạng thái không thể tiếp tục an toàn. Hãy để transaction kết thúc và rollback; sau đó xử lý lỗi ở ranh giới thích hợp hoặc bắt đầu transaction mới nếu có một quy trình khôi phục hợp lệ.

Không dùng REQUIRES_NEW chỉ để che lỗi object graph. Giao dịch riêng có thể làm dữ liệu liên quan commit độc lập, phá vỡ tính nguyên tử của nghiệp vụ.

## 15. Kiểm thử để ngăn lỗi tái diễn

Nên có kiểm thử tích hợp chạy với Hibernate và loại database phù hợp. Tối thiểu cần kiểm tra các trường hợp:

- Tạo đơn hàng với Customer đã tồn tại: khóa ngoại được lưu đúng.
- Tạo đơn hàng cùng OrderLine mới: cascade PERSIST từ aggregate root lưu các dòng hàng.
- Gán Customer transient không có cascade: thao tác thất bại như dự kiến.
- Cố gắng tham chiếu ID không tồn tại: nhận lỗi phù hợp từ kiểm tra ứng dụng hoặc constraint database.
- Thay đổi hai phía của quan hệ hai chiều: owning side được ghi đúng.
- Khi một bước sau thất bại: các thay đổi thuộc cùng transaction được rollback.

Ví dụ kiểm thử đường thành công có thể dùng repository để kiểm tra trạng thái sau khi gọi Service:

~~~java
@Test
void createsOrderForExistingCustomer() {
    Customer customer = customerRepository.saveAndFlush(
            new Customer("An"));

    Long orderId = orderService.createOrder(customer.getId());

    PurchaseOrder reloaded = orderRepository.findById(orderId)
            .orElseThrow();

    assertEquals(customer.getId(), reloaded.getCustomer().getId());
}
~~~

Đây là đoạn kiểm thử tích hợp minh họa; lớp test cần inject các repository/service và cấu hình database phù hợp. Nếu phương thức test chạy trong transaction do @DataJpaTest quản lý, các thao tác có thể rollback khi test kết thúc. Điều đó vẫn phù hợp để kiểm tra dữ liệu trong transaction test, nhưng nếu cần xác minh commit thực tế của Service, hãy thiết kế test boundary riêng và đọc lại sau khi transaction Service đã kết thúc.

Với kiểm thử lỗi, có thể gọi saveAndFlush để ép lỗi xuất hiện trong phạm vi assertion. Nếu transaction test bị đánh dấu rollback-only sau exception, không tiếp tục dùng persistence context đó để kiểm tra trạng thái như thể nó vẫn bình thường. Dùng transaction hoặc test case độc lập để xác minh dữ liệu sau rollback.

## 16. Checklist xử lý TransientPropertyValueException

- [ ] Đã đọc root cause và xác định entity/thuộc tính quan hệ gây lỗi.
- [ ] Đã phân biệt entity liên quan là transient, managed hay detached.
- [ ] Nếu entity liên quan đã tồn tại, đã tải bằng findById hoặc getReferenceById phù hợp.
- [ ] Nếu entity liên quan mới, đã lưu trước hoặc cascade PERSIST từ đúng aggregate root.
- [ ] Không dùng ID giả để mô phỏng một entity đã tồn tại.
- [ ] Không cascade REMOVE/ALL bừa bãi trên quan hệ dùng chung như Customer hoặc Product.
- [ ] Đã kiểm tra owning side và cập nhật cả hai phía của quan hệ hai chiều.
- [ ] Đã kiểm tra save đang đi theo persist hay merge và dùng entity trả về khi cần.
- [ ] Đã hiểu lỗi xuất hiện ở persist, flush hay commit.
- [ ] Không bắt lỗi rồi tiếp tục trong transaction đã thất bại.
- [ ] Có kiểm thử tích hợp cho đường thành công, đường lỗi và rollback.

## 17. Kết luận

TransientPropertyValueException thường cho biết một entity đang tham chiếu đến đối tượng liên quan chưa được lưu và thao tác hiện tại không có cascade PERSIST phù hợp. Cách sửa phụ thuộc vòng đời nghiệp vụ: tải entity managed nếu bản ghi đã tồn tại, lưu entity mới trước nếu nó độc lập, hoặc cascade từ aggregate root nếu entity con được tạo và quản lý cùng root. Kiểm tra owning side, phân biệt transient với detached và quan sát thời điểm flush giúp tìm đúng nguyên nhân. Sau khi sửa, hãy xác nhận bằng kiểm thử tích hợp rằng khóa ngoại và rollback hoạt động đúng.
