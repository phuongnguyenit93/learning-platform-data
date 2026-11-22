# Phạm vi persistence context và ranh giới giao dịch

Trong Domain-Driven Design (DDD), mô hình miền cần bảo vệ quy tắc nghiệp vụ, còn persistence chịu trách nhiệm lưu và khôi phục trạng thái. Khi dùng ORM như JPA/Hibernate, hai phần này thường gặp nhau thông qua **persistence context** và **database transaction**.

Hai khái niệm này liên quan chặt chẽ nhưng không đồng nghĩa. Persistence context quản lý các entity mà ORM đang theo dõi trong một phạm vi làm việc. Transaction xác định phạm vi thay đổi dữ liệu được commit hoặc rollback ở database. Nếu không hiểu ranh giới của chúng, ứng dụng dễ gặp lỗi như entity bị detached, lazy loading thất bại, cập nhật ngoài ý muốn, ghi dữ liệu quá sớm hoặc transaction kéo dài.

Nguyên tắc thực tế là **đặt transaction quanh một use case có ý nghĩa, để persistence context phục vụ phạm vi làm việc đó, và giữ các thay đổi của aggregate trong cùng ranh giới nhất quán cần thiết**. Cần hiểu rõ lúc nào ORM theo dõi object, lúc nào SQL được gửi và lúc nào dữ liệu thực sự được commit.

## 1. Phân biệt persistence context, transaction và unit of work

### 1.1. Persistence context là gì?

Trong JPA, persistence context là một tập hợp các entity instance được quản lý. EntityManager cung cấp API để persist, tìm, merge, xóa và đồng bộ entity; thay đổi trên entity đang managed thường được ghi nhận qua dirty checking.

Persistence context thường đảm nhiệm:

- Theo dõi entity đang ở trạng thái managed.
- Duy trì identity map để một database identity tương ứng với một managed object trong context.
- Phát hiện thay đổi của entity thông qua dirty checking.
- Điều phối việc đồng bộ trạng thái object với database khi flush.
- Quản lý quan hệ và cơ chế tải dữ liệu như lazy loading.

Trong Hibernate, Session là API cốt lõi tương ứng với khái niệm làm việc này; EntityManager của JPA thường được triển khai dựa trên Session.

### 1.2. Database transaction là gì?

Transaction là một đơn vị công việc ở database, gồm một hoặc nhiều câu lệnh SQL được commit hoặc rollback theo các thuộc tính giao dịch.

Transaction giúp bảo đảm các thay đổi dữ liệu tuân thủ những thuộc tính ACID ở mức mà database và cấu hình transaction cung cấp:

- **Atomicity:** các thay đổi trong transaction cùng thành công hoặc cùng bị rollback.
- **Consistency:** các ràng buộc được bảo vệ trước và sau transaction.
- **Isolation:** các transaction đồng thời nhìn thấy dữ liệu theo mức cô lập đã chọn.
- **Durability:** thay đổi đã commit được database bảo đảm lưu bền vững theo cấu hình của nó.

Transaction không tự biết quy tắc của Order, Customer hay Payment. Những invariant nghiệp vụ cần được bảo vệ bởi mô hình miền và được hỗ trợ bởi transaction cùng constraint phù hợp.

### 1.3. Unit of Work là gì?

Unit of Work là mẫu thiết kế gom các thay đổi trong một phạm vi công việc để theo dõi và ghi chúng như một đơn vị. ORM thường cung cấp phần lớn cơ chế này thông qua persistence context và transaction integration.

Có thể hình dung:

- Persistence context theo dõi entity và thay đổi của chúng.
- Transaction quyết định commit hay rollback thay đổi ở database.
- Unit of Work diễn đạt phạm vi công việc mà ứng dụng muốn hoàn thành như một đơn vị.

Trong nhiều ứng dụng JPA, một application service mở transaction, các repository dùng EntityManager tham gia vào persistence context tương ứng, và khi use case kết thúc thì transaction được commit hoặc rollback.

### 1.4. Ba khái niệm không phải một

| Khái niệm | Trách nhiệm chính | Câu hỏi nó trả lời |
|---|---|---|
| Persistence context | Quản lý entity instance và thay đổi | Object nào đang được ORM theo dõi? |
| Database transaction | Bảo đảm nhóm thao tác dữ liệu commit/rollback | Những thay đổi SQL nào được xác nhận cùng nhau? |
| Unit of Work | Gom thay đổi của một phạm vi công việc | Use case này cần hoàn thành những thay đổi nào như một đơn vị? |

Trong cấu hình phổ biến, persistence context có phạm vi transaction, nên hai phạm vi thường trùng nhau trong thực tế. Tuy nhiên, chúng vẫn là hai khái niệm khác nhau; JPA cũng có extended persistence context tồn tại lâu hơn một transaction.

## 2. Vòng đời entity trong JPA

JPA mô tả các trạng thái chính của entity: new/transient, managed, detached và removed.

### 2.1. New hoặc transient

Entity vừa được tạo bằng toán tử new và chưa được quản lý bởi persistence context:

~~~java
Order order = new Order(orderId, buyerId);
~~~

Lúc này ORM chưa theo dõi thay đổi của object và chưa có nghĩa vụ lưu nó vào database. Gọi setter hoặc hành vi miền chỉ thay đổi object trong bộ nhớ.

### 2.2. Managed

Entity trở thành managed khi được persistence context quản lý, ví dụ qua `persist`, `find` hoặc truy vấn trả về entity:

~~~java
entityManager.persist(order);

Order loaded = entityManager.find(Order.class, orderId);
~~~

Khi entity còn managed, ORM theo dõi thay đổi. Với cơ chế dirty checking, ứng dụng thường không cần gọi một phương thức update riêng sau mỗi lần thay đổi field.

### 2.3. Detached

Entity trở thành detached khi không còn được persistence context quản lý, ví dụ:

- EntityManager bị đóng.
- Gọi `entityManager.detach(entity)`.
- Gọi `entityManager.clear()` làm detach toàn bộ entity đang managed.
- Persistence context kết thúc.

Thay đổi một detached entity chỉ tác động đến object trong bộ nhớ. ORM không tự phát hiện và lưu các thay đổi đó.

### 2.4. Removed

Entity ở trạng thái removed khi được đánh dấu xóa bằng `entityManager.remove(entity)`. Lệnh SQL DELETE thường được thực hiện khi flush, sau đó thay đổi được xác nhận khi transaction commit.

### 2.5. Sơ đồ vòng đời

~~~mermaid
stateDiagram-v2
    [*] --> New
    New --> Managed: persist
    Managed --> Removed: remove
    Managed --> Detached: detach / clear / close
    Detached --> Managed: merge (bản managed được trả về)
    Removed --> [*]: flush và commit
    Managed --> [*]: context kết thúc
~~~

Sơ đồ thể hiện các chuyển trạng thái thường gặp. Chi tiết về thời điểm thực thi SQL và kết quả khi transaction rollback còn phụ thuộc provider và trạng thái transaction.

## 3. Persistence context và identity map

### 3.1. Một identity, một managed instance trong cùng context

Persistence context duy trì identity map. Nếu cùng một entity được tìm nhiều lần bằng cùng loại và cùng primary key trong một context, JPA bảo đảm các lần truy cập trả về cùng managed instance.

~~~java
Order first = entityManager.find(Order.class, orderId);
Order second = entityManager.find(Order.class, orderId);

assert first == second;
~~~

Đây là identity trong phạm vi persistence context. Một persistence context khác có thể tải cùng bản ghi thành một Java object khác.

Điều này giúp tránh việc một context quản lý hai object đại diện cho cùng một database row nhưng mang trạng thái khác nhau.

### 3.2. First-level cache

Persistence context cũng hoạt động như first-level cache:

- Nếu entity đã có trong context, ORM có thể trả lại object đang quản lý thay vì truy vấn lại database.
- Các thay đổi chưa flush được nhìn thấy qua chính managed instance.
- Một context khác không tự động thấy các thay đổi chưa commit của context hiện tại.

First-level cache có phạm vi persistence context, không phải cache dùng chung toàn ứng dụng. Nó không thay thế cache phân tán hoặc cache nghiệp vụ.

### 3.3. Không đồng nhất object identity với business identity

Hai Java object có thể đại diện cho cùng một Entity ở hai persistence context khác nhau. Ngược lại, cùng một class có thể chứa nhiều Entity với identity nghiệp vụ khác nhau.

Vì vậy:

- Không dựa vào toán tử `==` để so sánh Entity ở mọi tầng ứng dụng.
- Thiết kế equals/hashCode theo identity nghiệp vụ hoặc quy tắc phù hợp với vòng đời ID.
- Tránh dùng field mutable trong hashCode nếu Entity được đưa vào HashSet hoặc dùng làm key của HashMap.
- Không giả định proxy của ORM luôn có cùng class runtime với class entity cụ thể.

Identity map chỉ bảo đảm identity object bên trong một context; nó không tự thiết kế equality cho mô hình miền.

## 4. Dirty checking: ORM phát hiện thay đổi thế nào?

### 4.1. Thay đổi managed entity

Khi entity đang managed, ORM có thể so sánh trạng thái hiện tại với snapshot hoặc dùng cơ chế theo dõi thay đổi để xác định field nào đã thay đổi.

~~~java
Order order = entityManager.find(Order.class, orderId);
order.confirm();

// Không cần gọi entityManager.update(order).
// ORM sẽ phát hiện thay đổi khi flush.
~~~

Đây là dirty checking. Khi flush, ORM tạo câu SQL cần thiết để đồng bộ trạng thái managed entity với database trong transaction hiện tại.

### 4.2. Thay đổi detached entity không được dirty checking

~~~java
Order order = loadOrderInPreviousTransaction();
order.changeDeliveryAddress(newAddress);
~~~

Nếu object đã detached, ORM không theo dõi thay đổi trên. Việc object có field mới trong bộ nhớ không đồng nghĩa database đã được cập nhật.

Đây là lý do cần xác định rõ transaction và persistence context bao quanh use case.

### 4.3. Không cần gọi save cho mọi thay đổi managed

Trong JPA, nếu một entity đã managed, thay đổi của nó sẽ được đồng bộ khi flush. Một số repository abstraction vẫn có phương thức `save`, nhưng việc gọi lại save cho entity managed thường không cần thiết để dirty checking hoạt động.

Hãy hiểu semantics của framework đang dùng:

- `persist` dành cho entity mới.
- `merge` sao chép trạng thái từ entity detached hoặc new theo semantics JPA vào một managed instance.
- `remove` đánh dấu entity managed để xóa.
- Dirty checking theo dõi thay đổi của entity managed.

Spring Data JPA `save` thường chọn `persist` hoặc `merge` dựa trên việc nhận diện entity mới. Vì vậy, không nên xem `save` là một lệnh SQL UPDATE trực tiếp hay giả định nó luôn trả về chính object đầu vào.

## 5. Flush không phải commit

Đây là một trong những điểm quan trọng nhất khi làm việc với ORM.

### 5.1. Flush làm gì?

Flush đồng bộ thay đổi đang được persistence context quản lý xuống database bằng các câu SQL INSERT, UPDATE hoặc DELETE. Các câu SQL được thực thi trong transaction hiện tại, nhưng transaction chưa nhất thiết được commit.

~~~java
order.confirm();
entityManager.flush();

// SQL đã được gửi xuống database trong transaction.
// Transaction vẫn có thể rollback sau đó.
~~~

### 5.2. Commit làm gì?

Commit kết thúc transaction thành công và xác nhận các thay đổi theo cơ chế của database. Khi commit, JPA provider thường flush persistence context trước khi commit nếu cần.

Nếu transaction rollback sau flush, database sẽ hoàn tác các thay đổi thuộc transaction đó. Tuy nhiên, object trong bộ nhớ không nhất thiết tự quay lại trạng thái trước khi thay đổi.

Sau rollback, trạng thái entity và persistence context có thể không còn phù hợp để tiếp tục dùng như trước. Hãy kết thúc phạm vi làm việc đó và tải lại dữ liệu trong transaction/context mới thay vì cố tái sử dụng object đã tham gia transaction thất bại.

### 5.3. Khi nào flush xảy ra?

Flush có thể xảy ra:

- Khi ứng dụng gọi `entityManager.flush()`.
- Trước khi transaction commit.
- Trước một truy vấn trong chế độ flush AUTO nếu provider xác định các thay đổi có thể ảnh hưởng đến kết quả truy vấn.
- Ở những điểm đồng bộ do provider quy định.

Không nên dựa vào việc SQL chỉ được phát ra đúng lúc commit. Một truy vấn có thể kích hoạt flush trước đó.

### 5.4. Constraint violation có thể xuất hiện lúc flush

Một lệnh `persist` có thể chỉ đăng ký entity mới vào persistence context. Lỗi unique constraint hoặc foreign key có thể chỉ xuất hiện khi SQL được thực thi ở flush hoặc commit.

Nếu muốn phát hiện lỗi database sớm trong use case:

~~~java
entityManager.persist(order);
entityManager.flush();
~~~

Flush sớm có thể hữu ích để xác định vị trí lỗi, nhưng không thay thế validation nghiệp vụ. Nó cũng không commit transaction.

### 5.5. So sánh các mốc

| Mốc | Object trong persistence context | Database |
|---|---|---|
| Tạo object mới | New/transient | Chưa có bản ghi |
| Gọi persist | Managed | SQL có thể chưa chạy |
| Thay đổi managed entity | ORM ghi nhận thay đổi | Có thể chưa đồng bộ |
| Flush | Vẫn managed | SQL đã thực thi trong transaction |
| Commit | Transaction kết thúc; context có thể kết thúc hoặc tiếp tục tùy scope | Thay đổi được xác nhận |
| Rollback | Không nên tiếp tục dựa vào trạng thái entity trong bộ nhớ | Thay đổi transaction bị hoàn tác |

## 6. Phạm vi persistence context trong ứng dụng

### 6.1. Transaction-scoped persistence context

Đây là kiểu phổ biến: persistence context gắn với transaction. Khi transaction kết thúc, các entity thuộc context thường trở thành detached nếu không còn context khác quản lý chúng.

Trong Spring với JPA, transaction manager thường bind EntityManager vào thread đang thực hiện transaction. Các repository tham gia cùng transaction sẽ dùng cùng persistence context tương ứng.

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant A as Application Service
    participant R1 as Order Repository
    participant R2 as Payment Repository
    participant DB as Database
    C->>A: confirmOrder()
    Note over A,DB: Mở transaction và persistence context
    A->>R1: findById()
    R1->>DB: SELECT Order
    DB-->>R1: Order row
    R1-->>A: Managed Order
    A->>R2: recordPayment()
    R2-->>A: Managed Payment
    Note over A,DB: Dirty checking, flush SQL và commit
    DB-->>A: Commit thành công
    A-->>C: Kết quả use case
~~~

Các repository cùng tham gia một transaction không nên tự mở một transaction độc lập cho mỗi lời gọi nếu use case cần tính nguyên tử chung.

### 6.2. Extended persistence context

JPA hỗ trợ extended persistence context, thường gắn với một stateful component trong môi trường phù hợp và có thể tồn tại qua nhiều transaction.

Nó có thể hữu ích cho một quy trình hội thoại nhiều bước, nhưng kéo theo rủi ro:

- Entity managed tồn tại lâu và giữ nhiều trạng thái trong bộ nhớ.
- Dữ liệu có thể cũ so với các transaction khác.
- Khó kiểm soát thay đổi và đồng bộ đồng thời.
- Context dài hạn không phù hợp để giữ một request web hoặc session người dùng tùy tiện.

Không nên dùng extended context chỉ để tránh detached entity. Với ứng dụng web thông thường, transaction ngắn cùng DTO hoặc command giữa các request thường dễ kiểm soát hơn.

### 6.3. Open Session in View (OSIV)

Một số ứng dụng web giữ persistence context mở trong suốt vòng đời HTTP request để view có thể truy cập quan hệ lazy sau khi application service kết thúc.

OSIV có thể làm giảm lỗi lazy loading ngoài transaction trong một số tình huống, nhưng cũng có rủi ro:

- Truy vấn database có thể phát sinh trong lúc serialize response hoặc render view.
- Controller vô tình kích hoạt nhiều truy vấn N+1.
- Ranh giới transaction nghiệp vụ khó nhìn thấy.
- Thời gian giữ persistence context dài hơn cần thiết.
- Hiệu năng phụ thuộc vào cách view truy cập object graph.

Nếu dùng OSIV, cần chủ động giới hạn dữ liệu được tải và theo dõi truy vấn. Một lựa chọn rõ ràng hơn cho nhiều use case là lấy projection hoặc DTO cần thiết trong transaction rồi trả ra ngoài.

### 6.4. EntityManager không dùng chung giữa các thread

EntityManager và Hibernate Session không được thiết kế để nhiều thread cùng thao tác đồng thời. Không lưu EntityManager/Session vào static field, singleton tùy tiện hoặc chia sẻ giữa các request.

Mỗi luồng công việc cần persistence context phù hợp với transaction và thread của nó. Với xử lý bất đồng bộ, hãy mở transaction và context riêng ở phía worker.

## 7. Đặt ranh giới transaction ở application use case

### 7.1. Transaction bao quanh một hành động nghiệp vụ

Application service thường là nơi thích hợp để xác định transaction boundary vì nó điều phối toàn bộ use case.

~~~java
@Service
public class ConfirmOrderService {
    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(OrderId orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFound(orderId));

        order.confirm();
    }
}
~~~

Khi phương thức chạy trong transaction, repository tải Order thành managed entity. Hành vi miền thay đổi trạng thái; dirty checking đồng bộ thay đổi khi flush. Nếu không có lỗi, transaction manager commit khi phương thức hoàn tất theo quy tắc transaction.

Ví dụ lược bỏ phần kiểm tra quyền, reservation và xử lý lỗi để tập trung vào ranh giới transaction.

### 7.2. Repository không nên tự commit từng thao tác

Repository có trách nhiệm tải và lưu aggregate. Nó thường không nên tự mở/commit transaction riêng cho mỗi thao tác khi đã được gọi trong một use case cần nhiều thay đổi nguyên tử chung.

Nếu mỗi repository tự commit độc lập, một use case có thể gặp tình huống:

1. Order được cập nhật và commit thành công.
2. Payment ghi nhận thất bại.
3. Hệ thống để lại trạng thái nghiệp vụ chỉ hoàn thành một nửa.

Transaction boundary ở application service giúp gom các thao tác database thuộc cùng một đơn vị công việc.

### 7.3. Spring transaction propagation

Spring hỗ trợ nhiều propagation mode. Một số mode thường gặp:

| Propagation | Hành vi khái quát | Trường hợp sử dụng |
|---|---|---|
| REQUIRED | Tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có | Mặc định phù hợp cho nhiều use case |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và tạo transaction độc lập | Ghi nhận một phần công việc độc lập có chủ đích |
| MANDATORY | Yêu cầu phải có transaction đang hoạt động | Bảo vệ service chỉ được gọi trong transaction |
| SUPPORTS | Tham gia nếu có, nếu không thì chạy không transaction | Thao tác đọc không bắt buộc transaction |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại | Công việc được chủ ý chạy ngoài transaction |
| NEVER | Từ chối nếu có transaction | Bảo đảm thao tác không chạy trong transaction |

Không nên dùng REQUIRES_NEW chỉ để tránh lỗi transaction. Nó có thể commit một phần thay đổi ngay cả khi transaction bên ngoài rollback, làm thay đổi ngữ nghĩa nguyên tử của use case.

### 7.4. Cẩn thận với proxy của @Transactional

Trong cấu hình proxy-based phổ biến của Spring, lời gọi một phương thức transaction từ một phương thức khác trong cùng instance (self-invocation) có thể không đi qua proxy, nên annotation không được áp dụng như mong đợi.

Hãy đặt transaction boundary ở public application service method được gọi qua Spring bean proxy, hoặc dùng cơ chế transaction rõ ràng phù hợp với kiến trúc. Đừng giả định mọi lời gọi nội bộ đều tự động mở transaction.

### 7.5. Quy tắc rollback

Với cấu hình Spring mặc định, transaction thường rollback khi có `RuntimeException` hoặc `Error` thoát khỏi phương thức; checked exception không tự động kích hoạt rollback theo mặc định. Nếu use case cần rollback với checked exception, hãy cấu hình rollback rule phù hợp, chẳng hạn `rollbackFor`.

### 7.6. readOnly không đồng nghĩa không thể ghi

@Transactional(readOnly = true) thể hiện ý định chỉ đọc và có thể cho phép framework/provider tối ưu. Nó không phải một bảo đảm độc lập rằng database chắc chắn từ chối mọi câu lệnh ghi. Hãy dùng đúng mục đích và dựa vào quyền database hoặc cấu hình transaction nếu cần cưỡng chế.

## 8. Ranh giới aggregate và transaction trong DDD

### 8.1. Aggregate là ranh giới invariant

Aggregate xác định nhóm object cần duy trì các invariant nhất quán. Aggregate Root là điểm truy cập để thay đổi trạng thái bên trong.

Ví dụ:

- Order sở hữu OrderLine và bảo đảm tổng tiền, số lượng, trạng thái đơn nhất quán.
- InventoryItem hoặc Stock aggregate bảo vệ quy tắc giữ chỗ và số lượng khả dụng.
- Payment aggregate quản lý trạng thái giao dịch thanh toán.

Transaction database thường là công cụ thực thi thay đổi nhất quán cho một aggregate trong một use case.

### 8.2. Một transaction có thể cập nhật nhiều aggregate, nhưng cần lý do

Không có luật kỹ thuật rằng một transaction chỉ được phép cập nhật một aggregate. Một database transaction có thể thay đổi nhiều aggregate nếu nghiệp vụ cần tính nguyên tử và tất cả nằm trong cùng một ranh giới lưu trữ phù hợp.

Tuy nhiên, nếu nhiều aggregate thường xuyên phải được tải và cập nhật cùng nhau để bảo vệ một invariant, cần xem lại ranh giới aggregate. Có thể chúng đang bị tách sai hoặc quy tắc thuộc về một aggregate root khác.

DDD thường khuyến nghị thiết kế invariant nhất quán bên trong aggregate và phối hợp giữa các aggregate bằng domain event hoặc quy trình nhất quán cuối cùng khi phù hợp. Đây là hướng thiết kế để giảm coupling, không phải giới hạn của SQL transaction.

### 8.3. Không kéo transaction qua nhiều bounded context chỉ vì tiện

Ordering, Inventory và Payment có thể là các Bounded Context riêng. Nếu chúng có database hoặc service độc lập, một transaction ACID cục bộ không thể tự động bao trùm tất cả.

Một quy trình xác nhận đơn có thể:

1. Ordering tạo yêu cầu giữ chỗ.
2. Inventory xử lý giữ chỗ trong transaction của nó.
3. Payment xử lý thanh toán trong transaction riêng.
4. Ordering cập nhật kết quả và xác nhận đơn.

Nếu một bước thất bại, quy trình cần retry, hành động bù trừ hoặc Saga theo chính sách. Không nên giữ transaction database mở trong lúc chờ một service từ xa.

## 9. Detached entity và merge

### 9.1. Vì sao entity trở thành detached?

Một service có thể tải entity trong transaction rồi trả object ra ngoài. Khi transaction-scoped persistence context kết thúc, object thường detached.

~~~java
Order order = loadOrderInPreviousTransaction();
// Transaction kết thúc ở đây.
order.changeDeliveryAddress(newAddress);
// Thay đổi chỉ nằm trong object detached.
~~~

Nếu sau đó gọi một repository method khác trong transaction mới, không nên giả định object cũ tự được gắn vào context mới.

### 9.2. merge không gắn lại chính object đầu vào

Trong JPA, `merge(detachedEntity)` sao chép trạng thái của object đầu vào sang một managed instance tương ứng và trả về managed instance đó.

~~~java
Order managed = entityManager.merge(detachedOrder);

// managed là instance do persistence context quản lý.
// detachedOrder vẫn là object detached ban đầu.
~~~

Đây là điểm dễ nhầm: hãy dùng object được trả về từ merge nếu thật sự cần tiếp tục làm việc với managed instance.

### 9.3. Rủi ro của merge toàn bộ graph

Nếu detached object cũ được gửi từ client hoặc lưu lâu trong session, trạng thái của nó có thể đã lỗi thời. Merge có thể sao chép các field cũ vào managed entity và ghi đè thay đổi mới hơn, tùy mapping và trạng thái được cung cấp.

Một số rủi ro:

- Field không có trong request bị gán null hoặc giá trị mặc định.
- Collection cũ ghi đè quan hệ hiện tại.
- Trạng thái aggregate bị thay đổi ngoài hành vi nghiệp vụ.
- Optimistic locking phát hiện xung đột muộn.
- Caller không biết field nào thực sự bị cập nhật.

### 9.4. Cách thường rõ ràng hơn: tải rồi áp dụng command

Thay vì nhận một Entity detached rồi merge toàn bộ, application service có thể:

1. Nhận command chứa ý định thay đổi.
2. Tải aggregate trong transaction hiện tại.
3. Gọi hành vi miền để kiểm tra invariant.
4. Để dirty checking lưu thay đổi.

~~~java
@Transactional
public void changeDeliveryAddress(
        OrderId orderId,
        ShippingAddress newAddress) {
    Order order = orders.findById(orderId)
        .orElseThrow(() -> new OrderNotFound(orderId));

    order.changeDeliveryAddress(newAddress);
}
~~~

Cách này giữ quy tắc trong aggregate và chỉ thay đổi những field mà hành vi nghiệp vụ cho phép.

## 10. Lazy loading, N+1 và DTO boundary

### 10.1. Lazy association cần persistence context

ORM có thể trì hoãn tải quan hệ cho đến khi ứng dụng truy cập:

~~~java
Order order = orders.findById(orderId).orElseThrow();
List<OrderLine> lines = order.lines();
~~~

Nếu lines được mapping lazy và chưa tải, ORM cần persistence context để thực hiện truy vấn. Truy cập sau khi context đóng có thể gây LazyInitializationException trong Hibernate hoặc lỗi tương ứng từ provider.

### 10.2. N+1 query

Một truy vấn tải danh sách 100 Order, sau đó mỗi lần đọc customer hoặc lines lại phát sinh một truy vấn riêng, có thể tạo thành N+1 query.

Để xử lý:

- Dùng fetch join khi use case cần dữ liệu liên quan.
- Dùng EntityGraph để mô tả fetch plan.
- Dùng projection/DTO cho màn hình chỉ cần một tập field cụ thể.
- Dùng batch fetching khi phù hợp.
- Kiểm tra SQL thực tế bằng log, profiler hoặc test.

Không nên đổi mọi quan hệ thành EAGER để chữa N+1. EAGER có thể tải quá nhiều dữ liệu và làm các use case khác phát sinh truy vấn không cần thiết.

### 10.3. Chuyển sang DTO trước khi rời transaction

Controller hoặc serializer không nên vô tình quyết định database query bằng cách đi qua entity graph. Với response cần dữ liệu xác định, hãy truy vấn và tạo DTO trong transaction:

~~~java
@Transactional(readOnly = true)
public OrderDetailsView getOrderDetails(OrderId id) {
    Order order = orders.findDetailsById(id)
        .orElseThrow(() -> new OrderNotFound(id));

    return new OrderDetailsView(
        order.id(),
        order.status(),
        order.lines().stream()
            .map(line -> new OrderLineView(
                line.productId(),
                line.quantity(),
                line.unitPrice()
            ))
            .toList()
    );
}
~~~

DTO là dữ liệu đã được chuẩn bị cho use case. Nó không còn phụ thuộc vào lazy proxy hoặc persistence context sau khi được tạo.

## 11. Đồng thời và khóa dữ liệu

Transaction boundary xác định phạm vi thay đổi, nhưng không tự ngăn mọi xung đột khi nhiều người dùng cập nhật cùng entity.

### 11.1. Optimistic locking với @Version

Optimistic locking phù hợp khi xung đột không thường xuyên. Entity có version:

~~~java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    // Các field persistence khác.
}
~~~

Khi cập nhật, ORM dùng version để phát hiện bản ghi đã bị thay đổi bởi transaction khác. Nếu version không còn khớp, transaction có thể thất bại với optimistic locking exception.

Application layer cần quyết định trả conflict, tải lại và đánh giá lại, hoặc retry toàn bộ use case khi an toàn. Không nên chỉ retry câu UPDATE mà bỏ qua quy tắc nghiệp vụ.

### 11.2. Pessimistic locking

Pessimistic locking khóa bản ghi hoặc tài nguyên theo cơ chế database, ví dụ JPA `LockModeType.PESSIMISTIC_WRITE`. Nó có thể hữu ích khi tranh chấp cao và cần tuần tự hóa thao tác.

Đánh đổi:

- Transaction có thể phải chờ khóa.
- Khóa lâu làm giảm throughput.
- Có nguy cơ deadlock nếu thứ tự khóa không nhất quán.
- Cần timeout và chính sách xử lý khi không lấy được khóa.

Chỉ dùng khi có bằng chứng về nhu cầu đồng bộ mạnh hoặc mức tranh chấp phù hợp.

### 11.3. Database constraint vẫn cần thiết

Validation trong domain model bảo vệ quy tắc ở cấp ứng dụng, nhưng database constraint là lớp bảo vệ quan trọng trước race condition và các đường ghi khác:

- UNIQUE cho giá trị phải duy nhất.
- NOT NULL cho dữ liệu bắt buộc.
- FOREIGN KEY cho quan hệ tham chiếu.
- CHECK cho điều kiện dữ liệu mà database hỗ trợ.

Không nên dựa vào một lần kiểm tra trước khi insert để bảo đảm uniqueness. Hai transaction đồng thời có thể cùng thấy giá trị chưa tồn tại. Unique constraint mới là cơ chế cuối cùng bảo vệ điều kiện đó ở database.

## 12. Domain event và transaction

### 12.1. Không công bố event trước khi commit

Giả sử Order được xác nhận trong transaction và ứng dụng gửi OrderConfirmed lên message broker ngay lập tức. Nếu transaction database sau đó rollback, consumer có thể nhận một sự kiện cho thay đổi chưa từng được commit.

Đó là lỗi không nhất quán giữa database và message broker.

### 12.2. Publish sau commit có giới hạn

Có thể đăng ký handler chạy sau khi transaction commit. Cách này tránh gửi event cho transaction rollback, nhưng nếu process dừng sau commit và trước khi publish, event có thể bị mất.

### 12.3. Transactional Outbox

Transactional Outbox lưu thay đổi nghiệp vụ và bản ghi sự kiện vào cùng database transaction:

1. Aggregate thay đổi trạng thái.
2. Application layer lưu aggregate.
3. Cùng transaction đó, ghi một outbox record.
4. Sau commit, publisher đọc outbox và gửi message.
5. Publisher đánh dấu đã gửi hoặc dùng cơ chế retry phù hợp.

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant DB as Database
    participant P as Outbox Publisher
    participant B as Message Broker
    A->>DB: UPDATE Order
    A->>DB: INSERT OutboxEvent
    Note over DB: Cùng một transaction
    DB-->>A: Commit
    P->>DB: Đọc event chưa gửi
    P->>B: Publish event
    B-->>P: Acknowledge
    P->>DB: Đánh dấu đã gửi
~~~

Publisher có thể gửi lặp nếu bị lỗi sau khi broker nhận message nhưng trước khi outbox được đánh dấu. Consumer cần idempotent hoặc dùng event ID để loại trừ xử lý trùng.

Outbox giúp bảo đảm không mất ý định phát sự kiện giữa database commit và publish theo cách đáng tin cậy hơn, nhưng không tự tạo exactly-once delivery trên toàn hệ thống.

## 13. Những sai lầm thường gặp

**Đồng nhất persistence context với transaction.** Chúng liên quan nhưng có trách nhiệm khác nhau. Hãy xác định cả phạm vi theo dõi entity và phạm vi commit/rollback.

**Giữ persistence context quá lâu.** Context dài hạn làm entity dễ cũ, giữ nhiều object và khó quản lý thay đổi đồng thời. Ưu tiên phạm vi ngắn theo use case.

**Mở transaction ở từng repository method.** Các thao tác của cùng use case có thể bị commit riêng và không còn tính nguyên tử chung. Đặt transaction boundary ở application service khi phù hợp.

**Tưởng persist đồng nghĩa SQL đã chạy.** Persist thường đưa entity vào trạng thái managed; SQL có thể chỉ chạy ở flush hoặc commit.

**Tưởng flush đồng nghĩa commit.** Flush chỉ đồng bộ SQL trong transaction. Transaction vẫn có thể rollback.

**Thay đổi detached entity rồi chờ ORM tự lưu.** ORM không theo dõi detached object. Hãy tải lại aggregate trong transaction mới và áp dụng command.

**Merge object nhận từ client một cách mù quáng.** Merge có thể sao chép cả graph và ghi đè dữ liệu mới. Ưu tiên tải aggregate rồi gọi hành vi miền.

**Dùng OSIV để che mọi lỗi lazy loading.** Nó có thể đẩy truy vấn ra ngoài transaction nghiệp vụ và gây N+1. Hãy định nghĩa fetch plan hoặc DTO rõ ràng.

**Chuyển tất cả quan hệ sang EAGER.** Điều đó có thể làm tải dữ liệu quá mức và tạo hiệu năng khó đoán. Chọn fetch theo từng use case.

**Giữ transaction mở khi gọi HTTP hoặc message broker.** Thời gian chờ mạng làm khóa và connection bị giữ lâu. Tách giao tiếp từ xa thành bước ngoài transaction hoặc quy trình bất đồng bộ.

**Cho rằng một transaction giải quyết mọi xung đột.** Cần chọn isolation, optimistic/pessimistic locking và constraint theo tình huống.

**Phát event trước commit.** Consumer có thể thấy thay đổi đã rollback. Dùng publish sau commit hoặc Outbox tùy yêu cầu độ tin cậy.

## 14. Quy trình thiết kế persistence boundary

1. Xác định use case và các thay đổi dữ liệu phải cùng thành công hoặc cùng thất bại.
2. Xác định aggregate root và invariant cần bảo vệ.
3. Chọn application service làm transaction boundary phù hợp.
4. Đảm bảo repository tham gia transaction hiện tại thay vì commit độc lập.
5. Xác định entity nào cần managed trong suốt use case.
6. Chọn fetch plan để tránh lazy loading ngoài context và N+1.
7. Phân biệt flush với commit; chỉ flush sớm khi có lý do.
8. Xác định xử lý detached entity, DTO và merge.
9. Chọn optimistic/pessimistic locking cùng database constraint khi cần.
10. Nếu phát sự kiện, xác định cách bảo đảm nhất quán giữa database và broker.
11. Giữ transaction ngắn, tránh gọi dịch vụ từ xa khi đang giữ khóa hoặc connection.
12. Kiểm thử ranh giới bằng database integration test, flush và reload.

~~~mermaid
flowchart TD
    A["Use case bắt đầu"] --> B["Application Service mở transaction"]
    B --> C["Repository tải aggregate vào persistence context"]
    C --> D["Aggregate thực hiện hành vi và bảo vệ invariant"]
    D --> E["ORM dirty checking"]
    E --> F["Flush SQL"]
    F --> G{"Có lỗi hoặc xung đột?"}
    G -->|Có| H["Rollback và xử lý lỗi"]
    G -->|Không| I["Commit transaction"]
    I --> J["Trả DTO/kết quả"]
    I --> K["Publish Outbox event nếu có"]
~~~

## 15. Kiểm thử persistence context và transaction

Unit test domain model kiểm tra invariant và hành vi. Integration test cần xác minh ORM thực sự đồng bộ dữ liệu đúng với database.

### 15.1. Kiểm tra dirty checking

Một test nên:

1. Tạo và lưu Order.
2. Flush để gửi SQL.
3. Clear persistence context để loại object đang managed khỏi bộ nhớ.
4. Tải lại Order từ database.
5. Xác minh trạng thái đã được lưu.

~~~java
entityManager.persist(order);
entityManager.flush();
entityManager.clear();

Order reloaded = entityManager.find(Order.class, order.id());
assertEquals(OrderStatus.SUBMITTED, reloaded.status());
~~~

Nếu không clear và tải lại, test có thể chỉ đang đọc cùng object managed trong first-level cache, chưa chứng minh dữ liệu đã được lưu đúng.

### 15.2. Kiểm tra rollback

Tạo một use case cập nhật nhiều bản ghi trong transaction, cố ý gây lỗi sau một thay đổi, rồi xác minh database không giữ lại phần thay đổi đã rollback.

Lưu ý test framework có thể tự rollback transaction của test ở cuối. Cần kiểm tra trạng thái bằng transaction hoặc persistence context mới nếu muốn xác minh kết quả sau rollback.

### 15.3. Kiểm tra optimistic locking

Mở hai transaction riêng cùng tải một entity version N. Transaction thứ nhất cập nhật và commit. Transaction thứ hai cập nhật bản sao cũ và cần nhận conflict khi flush hoặc commit.

Test nên xác minh application layer chuyển conflict thành hành vi phù hợp, chẳng hạn yêu cầu tải lại hoặc báo người dùng thử lại.

### 15.4. Kiểm tra query count và lazy loading

Với use case trả danh sách Order, đo số query và kiểm tra dữ liệu cần thiết được tải trong transaction. Tránh chỉ dựa vào việc test chạy thành công khi OSIV đang bật.

## 16. Checklist trước khi chốt transaction boundary

**Persistence context**

- Entity nào đang managed trong use case?
- Context có phạm vi ngắn và dễ dự đoán không?
- Có entity nào bị dùng sau khi detached không?
- Có chia sẻ EntityManager hoặc Session giữa các thread không?
- Có dùng lazy relation sau khi context kết thúc không?

**Transaction**

- Use case nào cần commit/rollback cùng nhau?
- Transaction boundary có nằm ở application service phù hợp không?
- Repository có vô tình commit độc lập không?
- Có giữ transaction trong lúc gọi dịch vụ từ xa không?
- Đã hiểu propagation, isolation và rollback rule chưa?

**ORM**

- Đã phân biệt persist, merge, remove, flush và commit chưa?
- Có đang merge một graph cũ hoặc dữ liệu từ client không?
- Có query N+1 hoặc fetch EAGER quá mức không?
- Test có flush, clear và reload để kiểm chứng database không?

**DDD và tính nhất quán**

- Aggregate root có bảo vệ invariant không?
- Các thay đổi xuyên aggregate có lý do rõ ràng không?
- Bounded Context có sở hữu dữ liệu của mình không?
- Có cần optimistic/pessimistic locking hoặc database constraint không?
- Event có được công bố sau commit hoặc qua Outbox không?

Persistence context giúp ORM theo dõi object; transaction giúp database xác nhận một nhóm thay đổi; application service xác định use case cần hoàn thành như một đơn vị. Khi phân biệt rõ ba phạm vi này, đội phát triển có thể giữ invariant của aggregate, tránh cập nhật ngoài ý muốn và thiết kế luồng lưu trữ dễ kiểm thử, vận hành.
