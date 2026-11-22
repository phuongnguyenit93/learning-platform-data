# Tránh Repository quá lớn, generic CRUD tùy tiện và gọi save dư thừa

Repository là ranh giới giữa mô hình nghiệp vụ và cách lưu trữ dữ liệu. Một repository tốt cung cấp thao tác dữ liệu có ý nghĩa đối với aggregate hoặc use case; nó không nên trở thành nơi chứa mọi truy vấn của ứng dụng hay một bộ CRUD tổng quát không xét đến quy tắc miền.

Trong Spring Data JPA, JpaRepository cung cấp nhiều thao tác tiện lợi. Tuy nhiên, gom mọi truy vấn vào một interface, kế thừa toàn bộ CRUD cho mọi entity hoặc gọi save() sau mỗi thay đổi có thể làm thiết kế khó hiểu và dễ phát sinh lỗi.

Bài học này tập trung vào ba quyết định:

- Giữ Repository có trách nhiệm rõ ràng và mức độ liên quan cao.
- Chỉ dùng generic CRUD khi có hành vi dùng chung thực sự và vẫn giữ được giới hạn nghiệp vụ.
- Hiểu persist, merge, transaction và dirty checking để biết khi nào cần save().

## 1. Repository nên chịu trách nhiệm điều gì?

Repository cung cấp cách tìm và lưu aggregate trong mô hình miền. Nó che giấu chi tiết truy vấn và persistence để service hoặc domain logic làm việc với entity, value object và hành vi nghiệp vụ.

Ví dụ, với đơn hàng:

- PurchaseOrderRepository tìm và lưu aggregate PurchaseOrder.
- Các thao tác thêm dòng hàng, xác nhận đơn hoặc hủy đơn nên đi qua hành vi của aggregate và service tương ứng.
- Repository có thể truy vấn đơn hàng theo mã, trạng thái hoặc tiêu chí tìm kiếm.
- Repository không nên gửi email, gọi cổng thanh toán, quyết định chính sách hoàn tiền hoặc điều phối toàn bộ quy trình checkout.

Trong thiết kế theo aggregate, repository thường được định nghĩa cho aggregate root. Entity con được truy cập qua aggregate root khi cần bảo vệ invariant và vòng đời của aggregate. Nếu một entity có vòng đời độc lập hoặc có nhu cầu truy vấn riêng rõ ràng, có thể cân nhắc repository riêng; quyết định phải dựa trên ranh giới nghiệp vụ.

Một repository có trách nhiệm rõ ràng thường có các đặc điểm:

- Các phương thức phục vụ cùng một aggregate hoặc cùng một nhóm truy vấn dữ liệu liên quan.
- Tên phương thức mô tả điều kiện hoặc mục đích truy vấn.
- Không chứa quy tắc điều phối use case vốn thuộc service.
- Không để người gọi tùy ý thay đổi dữ liệu vượt qua invariant của domain model.

## 2. Dấu hiệu Repository đang quá lớn

Không có giới hạn số phương thức cố định cho một repository. Một interface có nhiều phương thức vẫn có thể hợp lý nếu tất cả phục vụ cùng một aggregate và một trách nhiệm truy cập dữ liệu thống nhất. Vấn đề xuất hiện khi interface trở thành nơi tập hợp các truy vấn và hành vi không còn cùng mục đích.

Một số dấu hiệu:

1. Có các nhóm phương thức phục vụ nhiều use case không liên quan, ví dụ quản lý đơn hàng, báo cáo kế toán, đối soát thanh toán và quản lý tồn kho cùng nằm trong một interface.
2. Người đọc khó tìm đúng phương thức vì tên gần giống nhau hoặc có nhiều overload không rõ khác biệt.
3. Repository chứa logic điều kiện, gọi nhiều repository khác hoặc thực hiện các bước nghiệp vụ.
4. Thay đổi một use case khiến nhiều caller khác phải sửa vì interface phơi bày quá nhiều chi tiết.
5. Interface có nhiều truy vấn chỉ phục vụ một màn hình hoặc một báo cáo, làm API aggregate bị chi phối bởi nhu cầu trình bày.
6. Nhiều phương thức có trách nhiệm truy vấn rất khác nhau nhưng không thể mô tả bằng một khái niệm miền chung.

Ví dụ một interface mất tính tập trung:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    BigDecimal sumRevenueByMonth(int year, int month);

    List<PurchaseOrder> findOrdersWithUnmatchedPayments();

    List<PurchaseOrder> findOrdersWaitingForInventory();

    List<OrderExportRow> exportOrders(LocalDate from, LocalDate to);

    // Nhiều truy vấn đặc thù cho các use case khác...
}
~~~

Không phải tất cả phương thức trên đều sai khi đặt trong repository đơn hàng. Câu hỏi là liệu chúng có cùng trách nhiệm và cùng mô hình dữ liệu hay không. Báo cáo tổng hợp hoặc export thường phù hợp với query service/read model riêng; đối soát có thể thuộc module thanh toán; tồn kho có thể thuộc module inventory.

Đừng chia repository chỉ theo số dòng hoặc số method. Hãy chia khi có một ranh giới trách nhiệm rõ ràng và người dùng của API thực sự khác nhau.

## 3. Tổ chức Repository theo trách nhiệm

### 3.1. Giữ repository aggregate root gọn

Repository chính nên giữ các thao tác cơ bản và truy vấn gắn với aggregate PurchaseOrder.

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);

    boolean existsByOrderNumber(String orderNumber);
}
~~~

Tên phương thức cho biết rõ dữ liệu cần tìm. Các hành vi như confirm(), cancel() hoặc addLine() nên được đặt trong aggregate hoặc được điều phối bởi service, thay vì tạo một repository method cho mỗi bước thay đổi trạng thái.

### 3.2. Tách truy vấn đọc phục vụ báo cáo

Khi một báo cáo cần projection hoặc phép tổng hợp riêng, có thể tạo query repository/read service chuyên biệt. Nó có thể dùng cùng database và cùng bảng nhưng phục vụ mô hình đọc khác với aggregate repository.

~~~java
public record MonthlyRevenue(
        int year,
        int month,
        BigDecimal total) {
}

public interface OrderReportingRepository {
    List<MonthlyRevenue> summarizeRevenue(int year);
}
~~~

Một class triển khai có thể dùng EntityManager, JPQL, Criteria API hoặc native SQL để tính dữ liệu báo cáo. Service báo cáo gọi thành phần này, trong khi PurchaseOrderRepository vẫn tập trung vào thao tác aggregate.

Không bắt buộc phải tạo repository riêng cho mọi projection nhỏ. Nếu truy vấn chỉ phục vụ một thao tác đơn giản và vẫn thuộc cùng trách nhiệm của aggregate, đặt trong repository hiện có là hợp lý.

### 3.3. Dùng repository fragment cho nhóm truy vấn tùy biến

Spring Data JPA hỗ trợ ghép fragment vào repository. Cách này hữu ích khi một nhóm thao tác truy cập dữ liệu có triển khai riêng, chẳng hạn truy vấn tìm kiếm động.

~~~java
public interface PurchaseOrderSearch {
    Page<PurchaseOrder> search(
            OrderSearchCriteria criteria,
            Pageable pageable);
}
~~~

Repository chính kết hợp fragment:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                PurchaseOrderSearch {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Class triển khai fragment theo quy ước tên, ví dụ PurchaseOrderSearchImpl, chứa phần truy vấn tùy biến. Cần đặt class trong package được Spring Data repository scanning phát hiện và tuân theo repository implementation postfix mà dự án cấu hình.

Fragment giúp chia phần triển khai theo nhóm trách nhiệm nhưng API bên ngoài vẫn có thể được ghép thành một repository. Nếu hai nhóm truy vấn thuộc hai bounded context hoặc hai mô hình đọc độc lập, nên cân nhắc tách thành bean riêng thay vì ghép tất cả vào một interface.

## 4. Generic CRUD: khi nào hữu ích, khi nào nguy hiểm?

Generic repository hoặc generic service thường được tạo để tránh lặp code. Ví dụ một BasicRepository<T, ID> hoặc BaseService<T, ID> cung cấp các thao tác lưu, tìm theo ID, truy vấn toàn bộ và xóa theo ID cho mọi entity.

Tái sử dụng có ích khi hành vi thật sự giống nhau. Nhưng generic CRUD tùy tiện dễ bỏ qua sự khác nhau về vòng đời và quy tắc của từng aggregate.

Các rủi ro thường gặp:

- Phơi bày thao tác xóa theo ID cho entity mà nghiệp vụ yêu cầu kiểm tra trạng thái trước.
- Cho phép lưu trực tiếp entity con, bỏ qua hành vi của aggregate root.
- Dùng truy vấn toàn bộ không giới hạn trên bảng lớn, gây tải dữ liệu không kiểm soát.
- Tạo API chung không thể diễn đạt truy vấn hoặc invariant riêng của domain.
- Dồn logic khác nhau vào điều kiện theo kiểu entity, khiến generic service trở thành một lớp điều phối khó bảo trì.

Một hợp đồng chung có thể trông nhất quán nhưng không phản ánh được quy tắc của từng loại dữ liệu. Ví dụ, một khách hàng có thể còn hợp đồng hiệu lực; một đơn hàng có thể đã thanh toán; một dòng hàng có thể chỉ được thay đổi thông qua aggregate PurchaseOrder. Một thao tác CRUD chung không thể tự biết những điều kiện này.

### 4.1. Chỉ tái sử dụng hợp đồng thực sự chung

Nếu dự án có một nhóm thao tác persistence tối thiểu thật sự giống nhau, Spring Data cho phép định nghĩa base repository với @NoRepositoryBean. Annotation này nói với Spring Data không tạo repository bean trực tiếp cho interface trung gian.

~~~java
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface BasicRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    <S extends T> S save(S entity);
}
~~~

Repository cụ thể chọn dùng hợp đồng tối thiểu đó:

~~~java
public interface CustomerRepository
        extends BasicRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

Cách này không tự động tạo một service CRUD tổng quát. Mỗi repository cụ thể vẫn định nghĩa những truy vấn cần thiết và service vẫn chịu trách nhiệm cho use case. Nếu cần đầy đủ JpaRepository, có thể kế thừa nó ở repository cụ thể; không nên buộc mọi loại entity phải công khai tất cả thao tác chỉ vì một base interface.

### 4.2. Không dùng generic để che giấu domain behavior

Các hành vi như approve, cancel, publish, archive hoặc settle có ý nghĩa nghiệp vụ. Chúng nên được mô tả bằng phương thức có tên cụ thể trên aggregate hoặc service.

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void cancelOrder(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order not found"));

        order.cancel();
    }
}
~~~

PurchaseOrder.cancel() có thể kiểm tra trạng thái và bảo vệ invariant. Service tải aggregate trong transaction rồi gọi hành vi miền. Một thao tác CRUD tổng quát không thể thay thế quyết định nghiệp vụ đó.

## 5. Hiểu đúng save() trong Spring Data JPA

JpaRepository.save() là API tiện lợi của Spring Data JPA. Trong triển khai mặc định, Spring Data xác định entity có mới hay không rồi chọn persist() hoặc merge():

- Entity được xác định là mới: gọi EntityManager.persist(entity).
- Entity được xác định là đã tồn tại: gọi EntityManager.merge(entity).

Việc xác định entity mới thường dựa trên thuộc tính version không primitive nếu có, hoặc ID; entity có thể tùy chỉnh chiến lược bằng Persistable.isNew(). Không nên kết luận chỉ từ việc ID có giá trị hay không nếu dự án dùng assigned ID hoặc cơ chế isNew tùy chỉnh.

### 5.1. Persist và merge khác nhau

**persist(entity):**

- Đưa entity mới vào persistence context.
- Entity truyền vào trở thành managed.
- INSERT thường được phát ra khi flush, trừ trường hợp provider cần insert sớm, chẳng hạn một số chiến lược sinh ID.

**merge(entity):**

- Sao chép trạng thái từ entity đầu vào vào một managed instance.
- Trả về managed instance đó.
- Entity đầu vào không vì thế tự trở thành managed.
- Với entity detached, cần dùng object trả về từ save()/merge() nếu tiếp tục thao tác trong persistence context.

Ví dụ:

~~~java
PurchaseOrder detached = receiveFromAnotherLayer();

PurchaseOrder managed = repository.save(detached);

// Nếu merge được dùng, managed là instance được quản lý.
// Đừng giả định detached đã được gắn lại vào persistence context.
managed.changeDeliveryAddress("Hanoi");
~~~

Merge không đồng nghĩa với một câu UPDATE luôn được chạy ngay. SQL được quyết định khi flush và phụ thuộc trạng thái thực tế, dirty checking cùng mapping.

Cũng không nên gửi một entity detached chỉ có vài trường được điền rồi merge như một bản cập nhật từng phần. Các thuộc tính không được điền có thể ghi đè trạng thái hiện tại bằng null hoặc giá trị mặc định. Với cập nhật nghiệp vụ, cách an toàn thường là tải entity trong transaction rồi thay đổi đúng thuộc tính cần đổi.

## 6. Khi nào không cần gọi save() lần nữa?

Một entity đã được load trong transaction đang hoạt động thường là managed. Khi thay đổi thuộc tính của entity managed, Hibernate theo dõi thay đổi và ghi SQL khi flush hoặc commit. Cơ chế này gọi là **dirty checking**.

Ví dụ:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeCustomerName(Long id, String newName) {
        Customer customer = repository.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Customer not found"));

        customer.changeName(newName);

        // Không cần gọi repository.save(customer)
        // vì customer đang managed trong transaction này.
    }
}
~~~

Trong ví dụ, transaction mở trước khi repository tìm Customer. Entity được quản lý trong persistence context. Khi customer.changeName() thay đổi trạng thái, dirty checking phát hiện thay đổi và flush sẽ phát UPDATE cần thiết.

Gọi repository.save(customer) ngay sau đó thường không cần thiết về mặt JPA nếu entity vẫn managed. Nó có thể làm người đọc tưởng rằng save() là lệnh bắt buộc để ghi mọi thay đổi. Hãy dùng save() khi cần lưu entity mới hoặc khi cần merge một entity detached theo chủ đích.

### 6.1. save() vẫn phù hợp cho entity mới

~~~java
@Transactional
public Long createCustomer(String email, String name) {
    Customer customer = new Customer(email, name);
    Customer saved = repository.save(customer);
    return saved.getId();
}
~~~

Ở đây save() phù hợp vì customer là entity mới và cần được persist. Việc lấy object trả về cũng nhất quán với hợp đồng của Spring Data.

### 6.2. saveAndFlush() không đồng nghĩa với commit

saveAndFlush() lưu entity qua repository và yêu cầu EntityManager flush persistence context. Flush đồng bộ các thay đổi đang chờ với database, nhưng transaction vẫn có thể tiếp tục và sau đó rollback.

Dùng flush có chủ đích khi:

- Cần phát hiện constraint violation tại vị trí kiểm thử.
- Cần database nhận thay đổi trước khi chạy truy vấn hoặc thao tác tiếp theo phụ thuộc vào SQL đã flush.
- Cần kiểm soát thời điểm đồng bộ persistence context.

Không dùng saveAndFlush() sau mỗi entity như một thói quen. Flush quá thường xuyên có thể làm giảm hiệu năng và phá vỡ lợi ích của việc gom các thao tác trong một transaction.

## 7. Ranh giới transaction quyết định trạng thái managed

Dirty checking chỉ áp dụng cho entity đang được quản lý trong persistence context. Nếu phương thức service không có transaction phù hợp, hoặc entity đã detached, thay đổi trong object Java không tự động được ghi xuống database.

Một luồng thường gặp:

1. Service mở transaction.
2. Repository tải aggregate.
3. Service gọi phương thức domain để thay đổi trạng thái.
4. Khi transaction flush hoặc commit, JPA đồng bộ thay đổi.
5. Persistence context kết thúc.

Với truy vấn chỉ đọc, có thể dùng @Transactional(readOnly = true) để thể hiện ý định và cho phép provider tối ưu phù hợp. Đây không phải cơ chế bảo đảm database từ chối mọi câu ghi; nó là metadata transaction và hành vi tối ưu phụ thuộc stack.

Không nên dựa vào Open Session in View để giữ entity managed xuyên suốt mọi tầng của ứng dụng. Hãy xác định transaction boundary ở service/use case và trả DTO khi cần dữ liệu cho API hoặc giao diện sau khi transaction kết thúc.

## 8. Cập nhật aggregate mà không gọi save dư thừa

Giả sử PurchaseOrder có hành vi addLine() và cancel(). Service có thể tải aggregate, thay đổi qua API của nó rồi kết thúc transaction:

~~~java
@Transactional
public void addLine(Long orderId, String sku, int quantity) {
    PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Order not found"));

    order.addLine(new OrderLine(sku, quantity));
}
~~~

Nếu PurchaseOrder.lines có cascade PERSIST phù hợp và helper method cập nhật owning side OrderLine.order, Hibernate có thể persist dòng hàng mới khi flush. Không cần gọi save() cho cả order và line trong trường hợp này.

Cần phân biệt:

- Entity cha managed: dirty checking theo dõi thay đổi thuộc tính của cha.
- Entity con mới được thêm vào quan hệ: cần cascade PERSIST hoặc phải persist con rõ ràng.
- Entity con detached: phải có chiến lược merge/persist rõ ràng; không thể chỉ thêm tùy tiện vào collection rồi kỳ vọng tự gắn lại.
- Quan hệ hai chiều: luôn đồng bộ owning side để khóa ngoại được ghi đúng.

Tránh gọi save() dư thừa không có nghĩa là bỏ qua cascade hoặc bỏ qua trạng thái entity. Cần hiểu entity đang new, managed hay detached trước khi quyết định.

## 9. Chọn API repository theo nhu cầu

| Nhu cầu | Cách phù hợp |
|---|---|
| Lưu aggregate mới | repository.save(newEntity) |
| Tải aggregate theo ID | repository.findById(id) |
| Cập nhật entity đã managed trong transaction | Thay đổi entity; dirty checking |
| Đồng bộ entity detached có chủ đích | Dùng kết quả trả về từ repository.save()/merge |
| Phát hiện constraint ngay tại điểm gọi | flush() hoặc saveAndFlush() có chủ đích |
| Truy vấn báo cáo/projection riêng | Query repository hoặc read service |
| Tìm kiếm động phức tạp | Specification, Criteria API hoặc repository fragment |
| Thực hiện use case qua nhiều repository | Application service có transaction phù hợp |

Tên API nên phản ánh ý nghĩa. Ví dụ findByOrderNumber() mô tả truy vấn; cancelOrder() mô tả use case và phù hợp với service. Đừng biến repository thành nơi chứa mọi hành động chỉ vì nó đang có sẵn bean truy cập database.

## 10. Các anti-pattern thường gặp

**Một GenericService<T, ID> cho toàn bộ nghiệp vụ.** Lớp chung có nhiều điều kiện theo loại entity và không thể thể hiện invariant. Hãy tái sử dụng phần kỹ thuật nhỏ, giữ hành vi nghiệp vụ ở service và domain model cụ thể.

**Một repository cho mọi bảng.** Repository tổng quát làm mất ranh giới aggregate, khuyến khích cập nhật entity con trực tiếp và khó bảo vệ quy tắc miền.

**Repository chứa logic điều phối.** Nếu phương thức gọi repository khác, gửi email, gọi payment gateway hoặc quyết định nhiều bước nghiệp vụ, trách nhiệm đó thường thuộc application service.

**Tách repository thành quá nhiều interface nhỏ.** Mỗi interface chỉ có một phương thức không tự động làm thiết kế tốt hơn. Chỉ tách khi có trách nhiệm hoặc người dùng khác biệt; nếu chỉ chia phần triển khai truy vấn, fragment có thể phù hợp.

**Gọi save() sau mọi thay đổi.** Với entity managed trong transaction, dirty checking đã xử lý thay đổi. Save dư thừa làm nhiễu luồng code và có thể khiến người đọc hiểu sai lifecycle.

**Dùng save() để cập nhật entity detached từng phần.** Merge có thể sao chép cả trạng thái null hoặc mặc định lên entity managed. Hãy tải aggregate rồi cập nhật có chủ đích.

**Dùng saveAndFlush() liên tục.** Flush quá nhiều làm tăng round-trip và giảm khả năng gom SQL. Chỉ flush khi có lý do rõ ràng.

**Công khai thao tác xóa theo ID ở mọi nơi.** Một số aggregate cần kiểm tra điều kiện xóa hoặc ghi nhận lịch sử. Hãy để service thực thi quy tắc trước khi gọi thao tác persistence phù hợp.

## 11. Cách kiểm tra thiết kế sau khi refactor

Khi tách một repository lớn hoặc loại bỏ generic CRUD, hãy kiểm tra:

1. Mỗi repository có trách nhiệm dữ liệu thống nhất và ranh giới aggregate rõ ràng.
2. Các truy vấn báo cáo hoặc read model không làm nhiễu API cập nhật aggregate nếu chúng thuộc trách nhiệm khác.
3. Service điều phối use case, transaction và các dependency cần thiết.
4. Domain model bảo vệ invariant thông qua hành vi có tên rõ ràng.
5. Generic base repository chỉ chứa hợp đồng thực sự dùng chung; không phơi bày thao tác nguy hiểm cho mọi entity.
6. Các luồng tạo mới dùng save() phù hợp; các luồng cập nhật entity managed tận dụng dirty checking.
7. Các luồng merge detached sử dụng object trả về và không ghi đè ngoài ý muốn.
8. Test tích hợp xác nhận dữ liệu sau flush/clear và kiểm tra số câu SQL khi cần.

Không cần refactor một repository chỉ vì nó có nhiều dòng. Hãy dựa trên cohesion, độ phụ thuộc giữa các use case và mức độ khó khăn khi thay đổi.

## Kết luận

Repository nên biểu đạt các thao tác dữ liệu thuộc về aggregate hoặc nhóm truy vấn có trách nhiệm thống nhất. Generic CRUD chỉ có ích khi hợp đồng thật sự chung và không làm mất quy tắc miền. Với entity managed trong transaction, dirty checking tự ghi thay đổi khi flush hoặc commit nên thường không cần gọi save() thêm lần nữa.

Thiết kế tốt giữ query ở repository, điều phối use case ở service, invariant ở domain model và transaction ở ranh giới ứng dụng phù hợp. Khi từng lớp giữ đúng vai trò, code Spring Data JPA dễ đọc, dễ kiểm thử và ít thao tác persistence dư thừa hơn.