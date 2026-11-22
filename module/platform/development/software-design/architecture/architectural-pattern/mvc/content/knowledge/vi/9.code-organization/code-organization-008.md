# Phạm vi sử dụng của lớp cơ sở và thành phần dùng chung

Trong ứng dụng MVC, nhiều Controller, Service, Model hoặc View có thể cần thực hiện những công việc giống nhau. Ví dụ, nhiều trang đều cần phân trang; nhiều nghiệp vụ đều cần kiểm tra quyền; nhiều Entity đều cần lưu thời điểm tạo và cập nhật; nhiều Controller cần trả lỗi theo một định dạng thống nhất.

Có thể tái sử dụng những phần này bằng lớp cơ sở (base class), thành phần dùng chung (shared component), hàm tiện ích hoặc một hợp đồng interface. Tuy nhiên, không phải đoạn mã xuất hiện ở nhiều nơi đều nên được đưa vào một lớp cha hoặc một thư viện chung. Cần xác định phạm vi thực sự của quy tắc, trách nhiệm của thành phần và những module được phép sử dụng nó.

Mục tiêu là đặt phần dùng chung tại đúng ranh giới để các thành phần MVC nhất quán, dễ kiểm thử và có thể thay đổi độc lập. Một lớp cơ sở quá lớn hoặc một gói tiện ích chứa mọi thứ có thể khiến các module phụ thuộc lẫn nhau và làm thay đổi nhỏ lan rộng khắp ứng dụng.

## 1. Lớp cơ sở và thành phần dùng chung khác nhau thế nào?

### 1.1. Lớp cơ sở

Lớp cơ sở (base class) là lớp được lớp khác kế thừa để nhận lại thuộc tính hoặc hành vi chung. Nó có thể cung cấp:

- Trường dữ liệu hoặc trạng thái chung.
- Phương thức đã triển khai mà lớp con có thể dùng.
- Phương thức trừu tượng để lớp con cung cấp phần chuyên biệt.
- Hook cho phép lớp con tùy chỉnh một bước trong quy trình.

Ví dụ, một lớp `AuditedEntity` có thể cung cấp `createdAt` và `updatedAt` cho các Entity cần theo dõi lịch sử tạo/cập nhật.

Kế thừa tạo ra quan hệ “is-a”: lớp con là một dạng của lớp cha theo ý nghĩa mô hình và hợp đồng hành vi. Nếu lớp con không thể tuân theo hợp đồng của lớp cha, việc kế thừa thường không phù hợp.

### 1.2. Thành phần dùng chung

Thành phần dùng chung (shared component) là một đối tượng hoặc module cung cấp một trách nhiệm được nhiều nơi sử dụng thông qua hợp đồng rõ ràng. Nó không nhất thiết phải có lớp cha hoặc quan hệ kế thừa.

Ví dụ:

- `PageRequestFactory` chuẩn hóa tham số phân trang.
- `CurrentUserProvider` cung cấp danh tính đã xác thực.
- `OrderAccessPolicy` kiểm tra quyền truy cập đơn hàng.
- `MoneyFormatter` định dạng tiền tệ theo Locale.
- `GlobalExceptionHandler` ánh xạ lỗi sang phản hồi HTTP.
- `Clock` cung cấp thời điểm hiện tại để nghiệp vụ và kiểm thử sử dụng thống nhất.

Thành phần dùng chung thường được ghép vào nơi sử dụng bằng dependency injection hoặc được gọi qua interface. Quan hệ này thể hiện “uses-a”: một Controller hoặc Service sử dụng một khả năng, nhưng không phải là một dạng của thành phần đó.

### 1.3. So sánh nhanh

| Tiêu chí | Lớp cơ sở | Thành phần dùng chung |
|---|---|---|
| Cơ chế tái sử dụng | Kế thừa | Composition, dependency injection, hàm hoặc module |
| Quan hệ | Lớp con là một dạng của lớp cha | Thành phần sử dụng một khả năng |
| Trạng thái | Có thể mang trạng thái chung cho lớp con | Có thể stateless hoặc quản lý trạng thái theo hợp đồng |
| Mở rộng | Override hoặc triển khai hook | Thay thế dependency, cấu hình hoặc triển khai interface |
| Ràng buộc | Gắn chặt cấu trúc lớp con với lớp cha | Thường có thể giữ phụ thuộc qua interface |
| Phù hợp | Hợp đồng và cấu trúc thực sự giống nhau | Hành vi cần chia sẻ nhưng các lớp không cùng bản chất |

Cả hai cách đều có chỗ dùng. Điều quan trọng là chọn theo quan hệ và phạm vi trách nhiệm, không chọn chỉ vì muốn giảm số dòng mã.

## 2. Xác định phạm vi của phần dùng chung

Trước khi tạo lớp cơ sở hoặc component, hãy xác định ai cần dùng và quy tắc đó thuộc về đâu.

### 2.1. Phạm vi toàn ứng dụng

Một số chức năng có thể được dùng ở nhiều module và không thuộc riêng nghiệp vụ nào:

- Xử lý lỗi HTTP theo quy ước chung.
- Ghi log, correlation ID và tracing.
- Xác thực người dùng và lấy ngữ cảnh request.
- Cấu hình JSON, Locale hoặc thời gian.
- Chuẩn hóa response lỗi của API.

Những thành phần này có thể nằm trong module nền tảng hoặc cấu hình web dùng chung. Chúng nên cung cấp hợp đồng ổn định và tránh phụ thuộc ngược vào một module nghiệp vụ cụ thể.

### 2.2. Phạm vi một module nghiệp vụ

Một số quy tắc chỉ có ý nghĩa trong một khu vực:

- Kiểm tra quyền xem và cập nhật đơn hàng.
- Chuẩn hóa bộ lọc của danh sách khóa học.
- Chuyển trạng thái của yêu cầu nghỉ phép.
- Tính phí vận chuyển cho quy trình giao hàng.

Không nên đưa quy tắc của đơn hàng vào một `BaseService` toàn ứng dụng chỉ vì vài Service khác cũng có phương thức tên giống nhau. Nếu quy tắc chỉ có ý nghĩa trong module đơn hàng, hãy đặt nó ở module đơn hàng để giữ quyền sở hữu rõ ràng.

### 2.3. Phạm vi một ca sử dụng hoặc một màn hình

Có những hành vi chỉ được dùng trong một luồng:

- Chuẩn bị dữ liệu cho màn hình thanh toán.
- Ánh xạ một biểu mẫu tìm kiếm sang query criteria.
- Tính toán dữ liệu hiển thị cho báo cáo cụ thể.

Không cần nâng chúng thành component dùng chung nếu chưa có người dùng thứ hai hoặc một lý do thiết kế rõ ràng. Một hàm private hoặc mapper chuyên biệt có thể là lựa chọn dễ hiểu nhất.

### 2.4. Phạm vi request, người dùng và tiến trình

Phạm vi sử dụng không đồng nghĩa với vòng đời đối tượng trong dependency injection.

| Phạm vi dữ liệu | Ví dụ | Cách quản lý cần chú ý |
|---|---|---|
| Toàn ứng dụng | Cấu hình, formatter bất biến | Có thể dùng singleton nếu an toàn luồng |
| Module | Chính sách truy cập đơn hàng | Chỉ được các thành phần thuộc module sử dụng |
| Request | Correlation ID, thông tin request | Dùng request scope hoặc truyền tường minh |
| Người dùng/phiên | Locale, múi giờ, tùy chọn cá nhân | Lấy từ ngữ cảnh phù hợp, không lưu vào singleton mutable |
| Ca sử dụng | Tiêu chí truy vấn hoặc kết quả tạm | Tạo theo lần gọi, không chia sẻ trạng thái ngoài ý muốn |

Một Spring bean mặc định thường là singleton trong ApplicationContext. Nếu bean singleton chứa trường có thể thay đổi theo từng request, dữ liệu của người dùng này có thể ảnh hưởng người dùng khác. Hãy giữ component dùng chung stateless khi có thể; nếu cần trạng thái, chọn scope hoặc truyền dữ liệu theo cách tường minh.

## 3. Khi nào nên tạo lớp cơ sở?

Lớp cơ sở phù hợp khi các lớp con thực sự có chung cấu trúc và cùng tuân theo một hợp đồng ổn định.

### 3.1. Có dữ liệu hoặc hành vi nền tảng giống nhau

Ví dụ, nhiều Entity cần lưu thời điểm tạo và cập nhật. Một lớp được ánh xạ bởi JPA có thể cung cấp các trường audit chung:

```java
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
```

Entity sử dụng lớp cơ sở:

```java
@Entity
public class Order extends AuditedEntity {

    @Id
    private UUID id;

    private OrderStatus status;
}
```

Với `@MappedSuperclass`, các mapping của lớp cha được áp dụng cho Entity con; lớp cha không tự trở thành một bảng Entity riêng theo cách quan hệ kế thừa JPA thông thường. Cần bật và cấu hình auditing trong ứng dụng để các annotation thời gian được cập nhật.

Chỉ đưa trường vào lớp cơ sở khi nó thực sự áp dụng cho mọi lớp con. Không thêm `createdBy`, `tenantId`, `deletedAt` hoặc các trường khác nếu có Entity không có cùng quy tắc hoặc vòng đời.

### 3.2. Có quy trình chung với các bước mở rộng rõ ràng

Một lớp cơ sở có thể phù hợp khi các lớp con đều thực hiện cùng một quy trình, chỉ khác một bước được xác định rõ. Đây là dạng Template Method.

Ví dụ khái niệm:

```java
public abstract class ImportJob {

    public final ImportResult run(InputStream input) {
        validateFile(input);
        List<Row> rows = readRows(input);
        validateRows(rows);
        return persist(rows);
    }

    protected abstract List<Row> readRows(InputStream input);

    protected abstract ImportResult persist(List<Row> rows);

    protected void validateFile(InputStream input) {
        // Quy tắc kiểm tra chung
    }

    protected void validateRows(List<Row> rows) {
        // Kiểm tra chung
    }
}
```

Lớp cơ sở kiểm soát thứ tự của quy trình; lớp con cung cấp cách đọc và lưu dữ liệu chuyên biệt. Chỉ dùng cách này khi thứ tự bước là bất biến của hợp đồng. Nếu các quy trình khác nhau đáng kể, nên tách thành các collaborator thay vì tạo nhiều hook và cờ điều khiển.

### 3.3. Lớp con có thể tuân theo hợp đồng của lớp cha

Một lớp cha cần có hợp đồng rõ ràng về:

- Điều kiện trước khi gọi phương thức.
- Kết quả và bất biến được bảo đảm.
- Ngoại lệ có thể phát sinh.
- Quyền được override của lớp con.
- Trạng thái và vòng đời của đối tượng.

Theo nguyên tắc thay thế Liskov (Liskov Substitution Principle), đối tượng lớp con phải có thể được sử dụng ở nơi cần lớp cha mà không phá vỡ hành vi mong đợi. Nếu lớp con phải vô hiệu hóa phần lớn phương thức lớp cha hoặc ném lỗi cho các thao tác vốn được lớp cha hứa hỗ trợ, mô hình kế thừa có vấn đề.

## 4. Khi nào không nên tạo lớp cơ sở?

### 4.1. Chỉ trùng tên phương thức hoặc vài dòng mã

Hai Controller đều có phương thức `list` không có nghĩa chúng cần kế thừa cùng một `BaseController`. Một Controller có thể hiển thị HTML, Controller khác trả JSON; quy tắc phân trang, quyền và lỗi có thể khác nhau.

Hãy tìm phần quy tắc thực sự giống nhau. Nếu chỉ là một phép chuyển đổi nhỏ, một component độc lập có thể phù hợp hơn.

### 4.2. Lớp cha chứa quá nhiều trách nhiệm

Một `BaseController` chứa xác thực, truy vấn dữ liệu, phân trang, tạo thông báo, upload file, xử lý exception và audit khiến mọi Controller con bị phụ thuộc vào nhiều khả năng không liên quan.

Khi một lớp cha trở thành nơi tập trung mọi thứ “có thể dùng lại”, nó thường biến thành điểm nghẽn thay đổi. Hãy tách theo trách nhiệm và đưa dependency cụ thể vào nơi cần dùng.

### 4.3. Lớp con phải override để vô hiệu hóa hành vi

Nếu một lớp con phải override phương thức chỉ để trả về rỗng, ném `UnsupportedOperationException` hoặc bỏ qua bước của lớp cha, có thể lớp cha đang áp đặt hợp đồng không phù hợp.

Thay vì ép mọi lớp vào một cây kế thừa, hãy dùng interface nhỏ hoặc composition để mỗi lớp chỉ nhận khả năng cần thiết.

### 4.4. Quy tắc dùng chung thay đổi theo module

Một lớp cơ sở trong module nền tảng không nên chứa các quy tắc cụ thể như “đơn hàng đã giao không được hủy” hoặc “quản lý chỉ duyệt hồ sơ thuộc nhóm mình”. Những quy tắc này cần được sở hữu bởi module nghiệp vụ tương ứng.

Đưa chúng vào lớp cha toàn ứng dụng làm tăng phụ thuộc và có thể buộc module không liên quan phải thay đổi khi nghiệp vụ đơn hàng đổi.

### 4.5. Cần cấu hình hoặc thay thế hành vi ở thời điểm chạy

Nếu cần thay thế cách gửi email, định dạng tiền hoặc chính sách truy cập theo môi trường, dependency qua interface thường linh hoạt hơn kế thừa. Có thể cấu hình implementation hoặc dùng decorator mà không thay đổi cây lớp.

## 5. Ưu tiên composition khi chia sẻ hành vi

Composition là cách một đối tượng sử dụng các đối tượng khác để hoàn thành trách nhiệm. Nó thường phù hợp với MVC vì Controller và Service có nhiều khả năng độc lập cần phối hợp.

Ví dụ:

```java
@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;
    private final OrderAccessPolicy accessPolicy;
    private final OrderViewMapper viewMapper;

    public OrderQueryService(
            OrderRepository orderRepository,
            OrderAccessPolicy accessPolicy,
            OrderViewMapper viewMapper) {
        this.orderRepository = orderRepository;
        this.accessPolicy = accessPolicy;
        this.viewMapper = viewMapper;
    }

    public OrderDetailView getDetail(UUID id, UserId viewerId) {
        accessPolicy.requireCanView(viewerId, id);

        OrderProjection order = orderRepository
            .findDetail(id)
            .orElseThrow(OrderNotFoundException::new);

        return viewMapper.toDetailView(order);
    }
}
```

Service sử dụng ba khả năng: truy vấn, kiểm tra quyền và chuyển đổi dữ liệu. Không cần kế thừa một lớp cha chứa cả ba trách nhiệm.

Lợi ích của composition:

- Chỉ đưa vào những dependency thực sự cần.
- Có thể thay thế implementation qua interface.
- Dễ kiểm thử bằng fake hoặc mock.
- Tránh phụ thuộc vào phương thức protected và thứ tự khởi tạo lớp cha.
- Có thể dùng cùng một component trong Controller, Service hoặc job nếu hợp đồng phù hợp.

Composition không phải lý do để tạo interface cho mọi lớp. Nếu chỉ có một implementation và không có nhu cầu thay thế, một class cụ thể có thể đủ. Hãy giữ abstraction tương xứng với nhu cầu thực tế.

## 6. Các thành phần dùng chung thường gặp trong ứng dụng MVC

### 6.1. Xử lý lỗi tập trung

Nhiều Controller có thể cần ánh xạ ngoại lệ sang trang lỗi hoặc cấu trúc response nhất quán. Với Spring MVC, `@ControllerAdvice` là một cơ chế phù hợp:

```java
@ControllerAdvice
public class GlobalWebExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ModelAndView handleOrderNotFound(
            OrderNotFoundException exception) {

        ModelAndView result = new ModelAndView("errors/404");
        result.setStatus(HttpStatus.NOT_FOUND);
        return result;
    }
}
```

Handler toàn cục nên xử lý các quy tắc phản hồi chung. Nếu một lỗi chỉ có ý nghĩa trong module cụ thể, có thể đặt handler hoặc mapper chuyên biệt tại phạm vi module và bảo đảm thứ tự xử lý rõ ràng.

Không nên để lớp xử lý lỗi chung chứa quy tắc nghiệp vụ của từng module. Nó nên chuyển kết quả lỗi thành phản hồi, không tự quyết định lại nghiệp vụ.

### 6.2. Thành phần kiểm tra quyền

Nhiều ca sử dụng có thể cần kiểm tra quyền truy cập. Thay vì lặp lại truy vấn và điều kiện ở từng Controller, có thể tạo policy hoặc authorization service:

```java
@Component
public class OrderAccessPolicy {

    private final OrderRepository orderRepository;

    public OrderAccessPolicy(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public void requireCanView(UserId userId, UUID orderId) {
        boolean allowed =
            orderRepository.existsVisibleTo(orderId, userId);

        if (!allowed) {
            throw new AccessDeniedException("Access denied");
        }
    }
}
```

Ví dụ này minh họa policy trong module đơn hàng. Nó nên được dùng ở mọi ca sử dụng cần kiểm tra quyền trên đơn hàng, kể cả khi request không đi qua giao diện. Không dựa vào việc View đã ẩn nút hoặc liên kết.

### 6.3. Thành phần phân trang và sắp xếp

Chuẩn hóa giới hạn phân trang là hành vi có thể dùng ở nhiều query. Có thể đóng gói thành factory hoặc validator:

```java
@Component
public class PageRequestFactory {

    public Pageable create(int page, int size) {
        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), 100);

        return PageRequest.of(safePage, safeSize);
    }
}
```

Nếu mỗi module có giới hạn kích thước hoặc trường sắp xếp khác nhau, không nên ép tất cả vào một chính sách toàn cục. Component chung có thể cung cấp giới hạn kỹ thuật tối đa; module vẫn chịu trách nhiệm xác định bộ lọc và trường sắp xếp hợp lệ.

### 6.4. Mapper và formatter

Mapper chuyển dữ liệu từ Entity hoặc projection sang DTO/ViewModel. Formatter trình bày ngày giờ, số và tiền theo Locale. Hai trách nhiệm này có thể được dùng chung nếu quy tắc thực sự giống nhau.

Cần tránh một `CommonMapper` khổng lồ chứa mọi ánh xạ của tất cả module. Mapper của đơn hàng nên thuộc module đơn hàng; formatter ngày/tiền có thể thuộc phần trình bày dùng chung nếu có hợp đồng rõ ràng.

### 6.5. Audit, logging và tracing

Các khả năng như ghi người tạo/cập nhật, correlation ID, log cấu trúc và tracing thường cắt ngang nhiều module. Chúng có thể được cung cấp qua listener, interceptor, filter hoặc thư viện nền tảng.

Không nên buộc từng Controller tự ghi log cùng một cấu trúc hoặc tự tạo correlation ID. Nhưng cũng không ghi dữ liệu nhạy cảm như mật khẩu, token hoặc toàn bộ request body vào log chỉ vì component logging được dùng chung.

### 6.6. Thành phần lấy ngữ cảnh người dùng

Một thành phần có thể cung cấp User ID, Locale hoặc tenant hiện tại từ ngữ cảnh đã xác thực. Hợp đồng cần phân biệt dữ liệu do máy chủ xác minh với dữ liệu client gửi lên.

Nếu thành phần phụ thuộc request context, cần xác định rõ cách dùng trong tác vụ nền không có HTTP request. Không giả định mọi Service luôn chạy bên trong một request web.

## 7. Tổ chức thành phần dùng chung theo ranh giới module

Một cấu trúc package có thể phân chia theo module nghiệp vụ và phần hạ tầng dùng chung:

```text
com.example.app
├── shared
│   ├── web
│   │   ├── GlobalWebExceptionHandler.java
│   │   └── PageRequestFactory.java
│   ├── security
│   │   └── CurrentUserProvider.java
│   └── audit
│       └── AuditedEntity.java
├── orders
│   ├── web
│   │   └── OrderController.java
│   ├── application
│   │   └── OrderQueryService.java
│   ├── domain
│   │   ├── Order.java
│   │   └── OrderAccessPolicy.java
│   ├── infrastructure
│   │   └── JpaOrderRepository.java
│   └── view
│       └── OrderViewMapper.java
└── leave
    ├── web
    ├── application
    ├── domain
    └── infrastructure
```

Đây chỉ là một cách tổ chức minh họa. Dự án có thể dùng package theo tầng hoặc theo feature. Điều quan trọng là hướng phụ thuộc:

- Module nghiệp vụ có thể sử dụng các hợp đồng nền tảng ổn định.
- Thành phần shared không nên phụ thuộc vào Controller hoặc Entity cụ thể của module nghiệp vụ.
- Quy tắc nghiệp vụ thuộc module nào thì module đó sở hữu.
- Không để module đơn hàng gọi trực tiếp lớp nội bộ của module nghỉ phép chỉ vì lớp đó có phương thức tiện dụng.

### 7.1. Phân biệt shared kernel và tiện ích kỹ thuật

Một số khái niệm miền có thể được chia sẻ giữa các module, ví dụ `Money`, `UserId` hoặc `TenantId`. Đây là phần mô hình dùng chung cần thống nhất ngữ nghĩa, không chỉ là thư viện tiện ích.

Ngược lại, các hàm chuyển đổi chuỗi, tạo UUID hoặc định dạng thời gian là tiện ích kỹ thuật. Không nên trộn hai nhóm này vào một package `common` không có ranh giới rõ.

Nếu shared kernel thay đổi, nhiều module có thể phải thay đổi theo. Vì vậy, chỉ chia sẻ mô hình miền khi các bên thực sự thống nhất cùng một khái niệm và quy tắc.

## 8. Thiết kế interface và hợp đồng cho component dùng chung

Một component dùng chung cần có hợp đồng nhỏ, thể hiện đúng khả năng mà người gọi cần.

Ví dụ:

```java
public interface CurrentUserProvider {
    UserId requireUserId();
    Locale currentLocale();
}
```

Các lớp cần danh tính hoặc Locale có thể phụ thuộc vào interface này. Trong kiểm thử, có thể cung cấp implementation giả:

```java
public class FixedCurrentUserProvider
        implements CurrentUserProvider {

    private final UserId userId;
    private final Locale locale;

    public FixedCurrentUserProvider(UserId userId, Locale locale) {
        this.userId = userId;
        this.locale = locale;
    }

    @Override
    public UserId requireUserId() {
        return userId;
    }

    @Override
    public Locale currentLocale() {
        return locale;
    }
}
```

Interface nên mô tả nhu cầu của bên sử dụng. Không đưa hàng chục phương thức vào một interface chỉ vì các implementation cùng nằm trong package shared. Có thể tách interface theo vai trò để mỗi module chỉ phụ thuộc vào phần cần thiết.

Không phải mọi component đều cần interface. Nếu một helper nhỏ, thuần và ổn định chỉ có một cách triển khai, dùng class cụ thể thường đơn giản hơn. Interface có giá trị khi cần tách hợp đồng khỏi implementation, có nhiều implementation hoặc cần một điểm thay thế có ý nghĩa.

## 9. Tránh trạng thái dùng chung không an toàn

Một component singleton có thể được nhiều request sử dụng đồng thời. Nếu nó giữ dữ liệu thay đổi theo người dùng, có nguy cơ rò rỉ trạng thái giữa các request.

Ví dụ không an toàn:

```java
@Component
public class CurrentUserContext {

    private UserId currentUser;

    public void setCurrentUser(UserId userId) {
        this.currentUser = userId;
    }

    public UserId getCurrentUser() {
        return currentUser;
    }
}
```

Nếu bean này là singleton, request của người dùng A có thể ghi đè `currentUser` trong khi request B đang sử dụng. Không lưu danh tính request vào trường mutable của singleton.

Các cách an toàn hơn:

- Truyền `UserId` tường minh qua tham số của ca sử dụng.
- Dùng SecurityContext của framework trong ranh giới phù hợp.
- Dùng bean request-scoped khi thực sự cần trạng thái theo request.
- Dùng component stateless để đọc ngữ cảnh hiện tại qua API được framework hỗ trợ.

Với tác vụ bất đồng bộ, SecurityContext hoặc request context có thể không tự truyền sang thread khác. Cần truyền thông tin cần thiết một cách tường minh và chỉ truyền dữ liệu đã được xác minh.

## 10. Kiểm thử lớp cơ sở và component dùng chung

Thành phần được nhiều nơi sử dụng có phạm vi ảnh hưởng lớn. Kiểm thử cần xác nhận hợp đồng của nó và cách các module tích hợp.

| Loại kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test lớp cơ sở | Xác nhận hành vi chung và hook | Quy trình import luôn kiểm tra file trước khi lưu |
| Unit test component | Xác nhận đầu vào/đầu ra và trường hợp biên | PageRequestFactory giới hạn size từ 1 đến 100 |
| Contract test | Xác nhận implementation tuân theo interface | CurrentUserProvider trả User ID và Locale đúng |
| Integration test | Xác nhận cấu hình framework | ControllerAdvice ánh xạ exception thành 404 |
| Module test | Xác nhận module dùng component đúng | Order service từ chối người không có quyền |
| Concurrency test | Xác nhận không rò trạng thái giữa request | Hai request có User ID khác nhau không đọc nhầm ngữ cảnh |

Khi thay đổi một component dùng chung, cần xem các caller bị ảnh hưởng và chạy các kiểm thử phù hợp. Không cần viết test cho mọi wrapper hoặc getter đơn giản; tập trung vào hợp đồng, quy tắc biên và rủi ro lan truyền.

## 11. Dấu hiệu thiết kế dùng chung quá mức

Có thể đang trừu tượng hóa quá sớm hoặc đặt sai phạm vi khi gặp những dấu hiệu sau:

- Lớp `BaseController` có nhiều dependency mà phần lớn lớp con không dùng.
- Lớp con phải override nhiều phương thức để vô hiệu hóa hành vi của lớp cha.
- Một thay đổi nhỏ trong package shared buộc nhiều module không liên quan sửa theo.
- Component chung có nhiều tham số boolean để điều khiển các nhánh hành vi khác nhau.
- Package `common` chứa cả quy tắc nghiệp vụ, truy cập dữ liệu, giao diện và tiện ích.
- Các module sao chép logic gần giống nhau nhưng thực chất có quy tắc khác nhau.
- Component singleton giữ dữ liệu người dùng hoặc request trong trường mutable.
- Không xác định được ai sở hữu quy tắc hoặc ai có quyền thay đổi hợp đồng.

Khi gặp các dấu hiệu này, hãy quay lại câu hỏi: thành phần đang bảo vệ quy tắc nào, ai thực sự dùng nó và điều gì cần thay đổi cùng nhau? Có thể tách component, thu hẹp interface, đưa quy tắc về module sở hữu hoặc xóa abstraction chưa cần thiết.

## 12. Quy trình quyết định có nên dùng chung hay không

Trước khi tạo lớp cơ sở hoặc component dùng chung, hãy đi qua các bước:

1. Xác định hành vi hoặc dữ liệu đang lặp lại.
2. So sánh ngữ nghĩa, điều kiện và cách thay đổi của các nơi sử dụng.
3. Xác định phạm vi sở hữu: toàn ứng dụng, module hay một ca sử dụng.
4. Nếu có quan hệ “is-a” ổn định và hợp đồng chung, cân nhắc lớp cơ sở hoặc interface.
5. Nếu chỉ cần một khả năng, ưu tiên component và composition.
6. Xác định vòng đời và trạng thái: stateless, singleton, request-scoped hay theo ca sử dụng.
7. Giữ hợp đồng nhỏ và chỉ công khai phương thức cần thiết.
8. Viết kiểm thử cho quy tắc chung và một số cách tích hợp tiêu biểu.
9. Theo dõi mức phụ thuộc của caller sau khi áp dụng; nếu thay đổi lan rộng, xem lại ranh giới.

Không cần tạo abstraction chỉ vì dự đoán rằng có thể sẽ có thêm implementation trong tương lai. Có thể bắt đầu bằng mã cục bộ rõ ràng và tách ra khi nhu cầu dùng chung xuất hiện.

## Kết luận

Lớp cơ sở phù hợp khi nhiều lớp thực sự chia sẻ cấu trúc và hợp đồng hành vi ổn định. Thành phần dùng chung phù hợp khi nhiều nơi cần cùng một khả năng nhưng không có quan hệ kế thừa tự nhiên. Trong MVC, hãy đặt quy tắc nghiệp vụ tại module sở hữu, đặt chức năng cắt ngang tại phần nền tảng phù hợp, giữ component dùng chung an toàn với nhiều request và ưu tiên composition khi cần ghép các khả năng độc lập. Phạm vi được xác định đúng giúp tái sử dụng mã mà vẫn giữ được ranh giới và khả năng thay đổi của từng thành phần.

