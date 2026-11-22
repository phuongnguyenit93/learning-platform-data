# Giới hạn của Spring Data REST với nghiệp vụ nhiều bước, hợp đồng công khai và mô hình miền phức tạp

## Mục tiêu và phạm vi

Spring Data REST tự động xuất các Spring Data repository thành tài nguyên HTTP. Với repository quản lý `Order`, ứng dụng có thể có collection resource như `/orders`, item resource như `/orders/{id}` và search resource cho các query method được công khai. Các thao tác HTTP thường được ánh xạ từ CRUD repository: đọc collection/item, tạo bằng `POST`, cập nhật bằng `PUT` hoặc `PATCH`, và xóa bằng `DELETE`.

Representation mặc định thường dùng HAL, cung cấp liên kết để client khám phá tài nguyên. Spring Data REST còn hỗ trợ phân trang, sắp xếp, metadata ALPS/JSON Schema, projections, excerpts, validation và các sự kiện vòng đời REST.

Cách tiếp cận này giảm đáng kể mã CRUD lặp lại khi repository và domain model phù hợp với dữ liệu mà client cần truy cập. Nó hữu ích cho API nội bộ, công cụ quản trị hoặc dịch vụ dữ liệu có quy tắc ghi đơn giản.

Giới hạn xuất hiện khi API cần biểu đạt ý định nghiệp vụ, bảo vệ một hợp đồng công khai ổn định hoặc che giấu cấu trúc miền phức tạp. Spring Data REST xuất tài nguyên dựa trên repository; nó không tự xác định use case, quy trình, quyền nghiệp vụ hay ranh giới aggregate thay cho ứng dụng.

## 1. CRUD không diễn tả được quy trình nghiệp vụ nhiều bước

CRUD mô tả thao tác trên trạng thái của một tài nguyên:

- `POST /orders`: tạo một đơn hàng.
- `GET /orders/{id}`: đọc đơn hàng.
- `PUT /orders/{id}`: thay thế representation của tài nguyên.
- `PATCH /orders/{id}`: cập nhật một phần tài nguyên.
- `DELETE /orders/{id}`: xóa tài nguyên.

Một quy trình nghiệp vụ mô tả hành động hợp lệ và điều kiện để thực hiện hành động đó. Ví dụ, đơn hàng có thể đi qua các trạng thái `DRAFT → SUBMITTED → APPROVED → SHIPPED`. Chỉ đơn đã gửi mới được duyệt; chỉ đơn đã duyệt mới được giao. Nếu client có thể gửi `PATCH {"status":"SHIPPED"}`, nó có thể bỏ qua kiểm tra tồn kho, quyền phê duyệt, thanh toán hoặc các quy tắc chuyển trạng thái.

Quy tắc chuyển trạng thái nên nằm trong aggregate/domain object. Phương thức miền phải từ chối chuyển trạng thái không hợp lệ, bất kể lời gọi đến từ REST controller, tác vụ nền hay một use case nội bộ. Nhờ vậy, invariant được bảo vệ ở nơi có thẩm quyền về trạng thái của đối tượng.

Ví dụ Java 17 dưới đây minh họa một domain object có chuyển trạng thái hợp lệ. Lưu thành `OrderWorkflowDemo.java`:

```java
import java.util.Objects;
import java.util.UUID;

enum OrderStatus {
    DRAFT, SUBMITTED, APPROVED, SHIPPED
}

final class Order {
    private final UUID id;
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id) {
        this.id = Objects.requireNonNull(id);
    }

    void submit() {
        transition(OrderStatus.DRAFT, OrderStatus.SUBMITTED);
    }

    void approve() {
        transition(OrderStatus.SUBMITTED, OrderStatus.APPROVED);
    }

    void ship() {
        transition(OrderStatus.APPROVED, OrderStatus.SHIPPED);
    }

    UUID getId() {
        return id;
    }

    OrderStatus status() {
        return status;
    }

    private void transition(OrderStatus expected, OrderStatus next) {
        if (status != expected) {
            throw new IllegalStateException(
                "Cannot change order from " + status + " to " + next
            );
        }
        status = next;
    }
}

public class OrderWorkflowDemo {
    public static void main(String[] args) {
        Order order = new Order(UUID.fromString(
            "00000000-0000-0000-0000-000000000001"
        ));

        order.submit();
        order.approve();

        System.out.println(order.status());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac OrderWorkflowDemo.java
java OrderWorkflowDemo
```

Output chính xác:

```text
APPROVED
```

Nếu gọi `ship()` ngay sau khi tạo đơn, hoặc gọi `approve()` hai lần, domain object ném `IllegalStateException`. Ví dụ độc lập này tập trung vào invariant; trong ứng dụng thực tế, aggregate thường có thêm mapping JPA, thuộc tính, repository và quy tắc miền khác.

### Đưa hành động vào application service

Controller nên nhận command, kiểm tra đầu vào và gọi application service. Service tải aggregate, gọi hành vi miền, lưu kết quả và trả DTO. Ranh giới transaction thường đặt ở application service để các thao tác cơ sở dữ liệu thuộc cùng một use case có thể commit hoặc rollback cùng nhau.

Ví dụ khung tích hợp Spring dưới đây lược bỏ import, mapping JPA và phần khai báo đầy đủ của entity:

```java
@RepositoryRestResource(exported = false)
interface OrderRepository extends JpaRepository<Order, UUID> {
}

record OrderView(UUID id, OrderStatus status) {
}

@Service
class OrderApplicationService {
    private final OrderRepository orders;

    OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderView approve(UUID id) {
        Order order = orders.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"
            ));

        order.approve();
        orders.save(order);

        return new OrderView(order.getId(), order.status());
    }
}

@RestController
@RequestMapping("/api/v1/orders")
class OrderCommandController {
    private final OrderApplicationService service;

    OrderCommandController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    public OrderView approve(@PathVariable UUID id) {
        return service.approve(id);
    }
}
```

Repository vẫn được inject và dùng nội bộ, nhưng `@RepositoryRestResource(exported = false)` ngăn Spring Data REST xuất repository đó thành REST resource. Controller riêng cung cấp command endpoint `POST /api/v1/orders/{id}/approve`. Nếu muốn controller nằm trong namespace và dùng cấu hình base path của Spring Data REST, có thể dùng `@RepositoryRestController`; controller đó được phục vụ dưới base path của Spring Data REST. Cần chọn rõ một kiểu tổ chức endpoint để tránh vô tình mở cả CRUD lẫn command endpoint cho cùng aggregate.

Tên endpoint nên thể hiện ý định như `POST /orders/{id}/approve`, `POST /orders/{id}/cancel` hoặc `POST /orders/{id}/ship`. Không nên để client tự gán trường trạng thái nội bộ. Request/response DTO giới hạn các trường mà use case nhận và trả về, đồng thời giảm phụ thuộc giữa JSON công khai và entity persistence.

### Quy trình kéo dài hoặc đi qua nhiều hệ thống

Một transaction cơ sở dữ liệu phù hợp với use case ngắn, có ranh giới rõ. Không nên giữ transaction mở trong khi chờ cổng thanh toán, hãng vận chuyển hoặc dịch vụ từ xa. Với quy trình kéo dài hoặc phối hợp nhiều hệ thống, hãy cân nhắc:

- Lưu trạng thái tiến trình và điều phối các bước bằng process manager, workflow hoặc saga.
- Dùng transactional outbox để ghi sự kiện cần phát cùng transaction cập nhật dữ liệu; worker gửi sự kiện sau đó và có cơ chế retry.
- Thiết kế command idempotent hoặc hỗ trợ idempotency key để retry không tạo hiệu ứng lặp.
- Dùng optimistic locking, chẳng hạn trường `@Version`, hoặc điều kiện phiên bản để phát hiện hai yêu cầu đồng thời cập nhật cùng aggregate.
- Xác định rõ trạng thái trung gian, timeout, retry, bù trừ và cách xử lý khi một dịch vụ ngoài không phản hồi.

Nếu quy trình chưa hoàn tất khi HTTP request kết thúc, API có thể trả `202 Accepted` cùng liên kết hoặc mã để truy vấn trạng thái tiến trình. Nếu xử lý đồng bộ, cần quy định rõ kết quả thành công và lỗi nghiệp vụ; ví dụ `409 Conflict` cho chuyển trạng thái không hợp lệ. Mã trạng thái và cấu trúc lỗi cần nhất quán trong hợp đồng API.

## 2. Event và validation: hook hữu ích nhưng không thay thế use case

Spring Data REST phát các sự kiện trong vòng đời xử lý REST, gồm `BeforeCreateEvent`, `AfterCreateEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, `BeforeLinkSaveEvent`, `AfterLinkSaveEvent`, `BeforeDeleteEvent` và `AfterDeleteEvent`. Có thể lắng nghe bằng `AbstractRepositoryEventListener` hoặc dùng `@RepositoryEventHandler` cùng các annotation như `@HandleBeforeSave`, `@HandleAfterCreate`.

Các hook này phù hợp với xử lý gắn trực tiếp vào vòng đời REST: chuẩn hóa dữ liệu đơn giản, kiểm tra bổ sung, ghi audit hoặc phản ứng nhẹ sau thao tác. Spring Data REST cũng hỗ trợ đăng ký `Validator` theo sự kiện, ví dụ validator trước khi tạo hoặc lưu tài nguyên.

Không nên giấu toàn bộ quy trình thanh toán, duyệt đơn, gửi hàng hoặc phối hợp nhiều aggregate trong event handler. Logic như vậy khó nhìn thấy từ endpoint, khó gọi lại từ luồng nội bộ và khó quản lý retry/transaction. Sự kiện của REST exporter cũng không nên được coi là domain event bus chung cho mọi lời gọi repository trong ứng dụng. Hãy để application service điều phối use case, domain object bảo vệ invariant, và dùng domain event/outbox khi cần phát thông tin ra ngoài ranh giới transaction.

Bean Validation phù hợp với ràng buộc dữ liệu đầu vào như trường bắt buộc, độ dài, định dạng hoặc giới hạn số. Domain method phù hợp với quy tắc phụ thuộc trạng thái và quan hệ nghiệp vụ. Ví dụ, chuỗi mã đơn hàng có độ dài hợp lệ là kiểm tra đầu vào; đơn đã hủy không được giao là invariant miền. Hai lớp kiểm tra này bổ sung cho nhau.

## 3. Hợp đồng công khai có thể thay đổi cùng repository và entity

Theo mặc định, Spring Data REST phát hiện các repository phù hợp và tạo tài nguyên dựa trên chúng. Tên collection thường được suy ra từ tên domain class; các phương thức repository quyết định những thao tác HTTP và search resource có thể được xuất. Nếu repository kế thừa CRUD đầy đủ, API có thể mở nhiều thao tác đọc/ghi ngay khi repository được thêm vào.

Điều này tạo liên kết giữa cấu trúc persistence và hợp đồng HTTP:

- Đổi tên entity hoặc repository có thể ảnh hưởng URI, collection relation hoặc search resource.
- Thêm một phương thức public vào repository có thể làm xuất hiện search endpoint mới.
- Thêm, bỏ hoặc đổi kiểu thuộc tính entity có thể làm thay đổi JSON được serialize.
- Thay đổi association có thể ảnh hưởng cách representation chứa liên kết hoặc dữ liệu lồng nhau.
- Thay đổi kiểu ID hoặc cách tạo ID có thể tác động đến URI tài nguyên và client lưu URI đó.

Với API công khai, thay đổi nội bộ có thể trở thành breaking change cho client. Hypermedia giúp client khám phá liên kết và giảm việc hard-code URL, nhưng không tự tạo chính sách versioning, deprecation hay tương thích ngược. HATEOAS không thay thế việc quản lý hợp đồng API.

### Kiểm soát repository và method được xuất

Spring Data REST cung cấp một số cơ chế để giới hạn bề mặt API:

- Dùng `@RepositoryRestResource(exported = false)` để giữ repository cho ứng dụng nhưng không xuất repository đó thành REST resource.
- Dùng `@RestResource(exported = false)` trên phương thức repository hoặc association không được phép công khai.
- Cấu hình `RepositoryDetectionStrategy.ANNOTATED` để chỉ xuất repository được đánh dấu rõ bằng `@RepositoryRestResource`.
- Dùng `RepositoryRestConfiguration.getExposureConfiguration()` để tắt HTTP method ở phạm vi toàn cục hoặc theo domain type.
- Dùng `@RepositoryRestResource(path = "...", collectionResourceRel = "...")` và `@RestResource(path = "...", rel = "...")` khi cần đặt tên path hoặc relation có chủ đích.

Những cơ chế này kiểm soát việc xuất resource và method; chúng không thay thế authorization. Cần cấu hình Spring Security, method security và kiểm thử quyền cho từng thao tác. Khi bảo vệ repository bằng method security, hãy kiểm tra đầy đủ các overload CRUD có thể được xuất; bảo vệ một method không có nghĩa mọi method tương tự tự động được bảo vệ. Cũng cần kiểm tra quyền trên association resource và search resource, không chỉ collection/item resource.

### Thiết kế hợp đồng public ổn định

Nếu API phục vụ đối tác hoặc client bên ngoài, thường nên dùng controller và DTO riêng:

1. Xác định request/response DTO theo ngôn ngữ nghiệp vụ, không theo toàn bộ entity.
2. Chọn endpoint và HTTP method theo hành động; xác định status code, lỗi, phân trang và quy tắc idempotency.
3. Đặt version rõ ràng, ví dụ `/api/v1`, và có chính sách deprecation.
4. Map DTO sang application service/aggregate; không bind trực tiếp request vào entity có trường nội bộ hoặc nhạy cảm.
5. Viết contract test cho JSON, status code, link và các tình huống lỗi để phát hiện thay đổi ngoài ý muốn.
6. Ghi rõ giới hạn tương thích và cách client xử lý trường mới, trường bị deprecated hoặc lỗi validation.

Spring Data REST có metadata ALPS và JSON Schema, cùng HAL để khám phá API. Đây là thông tin hữu ích cho client và công cụ, nhưng không thay thế tài liệu hợp đồng, quy tắc tương thích và kiểm thử phiên bản mà một API công khai cần có.

## 4. Mô hình miền phức tạp cần ranh giới representation rõ ràng

Spring Data REST tổ chức tài nguyên quanh repository và domain object. Với association, API có thể cung cấp liên kết đến tài nguyên liên quan và association resource để đọc hoặc thay đổi quan hệ. Nếu kiểu liên quan có repository riêng, representation thường dùng URI link; nếu không, dữ liệu liên quan có thể được đưa trực tiếp vào representation của object cha.

Cách này thuận tiện với mô hình đơn giản, nhưng có thể gây khó khăn khi:

- Aggregate có nhiều quan hệ hai chiều, collection lớn hoặc nhiều cấp lồng nhau.
- Entity persistence chứa trường nội bộ, trạng thái tính toán hoặc dữ liệu chỉ dành cho một vai trò.
- Client cần một view tổng hợp theo use case, khác với cấu trúc entity/bảng.
- Một thay đổi trong mô hình miền không nên làm thay đổi public API.
- Việc đọc một representation kích hoạt tải nhiều association, gây N+1 query hoặc payload lớn.
- Việc cập nhật một association trực tiếp có thể bỏ qua quy tắc của aggregate root.

Cần xác định aggregate root và quy tắc sở hữu quan hệ. Nếu một association chỉ được thay đổi thông qua hành vi của aggregate root, đừng công khai association resource theo cách cho phép client cập nhật trực tiếp. Nếu client cần một view tổng hợp, tạo DTO/query model phù hợp với use case thay vì buộc representation phản chiếu toàn bộ object graph.

### Dùng projections và excerpts đúng mục đích

Projection cho phép chọn những thuộc tính xuất hiện trong representation. Projection có thể tạo view gọn hơn, kết hợp dữ liệu thành thuộc tính ảo hoặc đưa thêm dữ liệu cần thiết cho một màn hình. Excerpt projection có thể được áp dụng mặc định cho tài nguyên collection để tạo preview.

Excerpt projection được cấu hình cho collection không tự động áp dụng cho tài nguyên item đơn lẻ. Client có thể cần chỉ định projection khi đọc item. Hãy kiểm thử cả collection và item để tránh giả định hai representation giống nhau.

Projection là công cụ định hình dữ liệu trả về, không phải ranh giới bảo mật. Một projection có thể làm lộ thuộc tính mà representation mặc định không xuất, kể cả trường có annotation như `@JsonIgnore` trong một số cấu hình. Vì vậy, cần rà soát từng projection như một bề mặt xuất dữ liệu. Không đưa password, token, secret hoặc dữ liệu cá nhân nhạy cảm vào projection chỉ vì field gốc đang bị ẩn.

Projection cũng không thay thế command DTO hoặc domain behavior. Nếu client cần cấu trúc request khác entity, hoặc cần thao tác có quy tắc nghiệp vụ, hãy dùng DTO và endpoint riêng. Với dữ liệu nhạy cảm hoặc nhiều vai trò truy cập, DTO tường minh thường dễ kiểm soát hơn projection dùng chung.

## 5. Chọn cách tiếp cận theo loại API

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| CRUD nội bộ, entity đơn giản, ít quy tắc ghi | Spring Data REST có thể xuất repository trực tiếp. |
| Search theo thuộc tính và phân trang đơn giản | Repository query methods và search resources có thể phù hợp. |
| Quy trình nhiều bước, chuyển trạng thái, phê duyệt hoặc thanh toán | Command endpoint gọi application service và domain method. |
| API public cần versioning và tương thích ngược | Controller/DTO riêng; kiểm soát rõ path, payload, lỗi và chính sách version. |
| Entity có nhiều quan hệ hoặc dữ liệu nhạy cảm | Giới hạn repository exposure; dùng DTO/projection đã được rà soát. |
| Ứng dụng cần CRUD tiện lợi cùng một số use case đặc biệt | Kết hợp Spring Data REST cho phần CRUD phù hợp với controller/service riêng cho command. |

Không cần loại bỏ Spring Data REST khỏi toàn bộ ứng dụng chỉ vì có một workflow phức tạp. Có thể xuất những repository thật sự phù hợp và ẩn những repository cần đi qua use case riêng. Điều quan trọng là quyết định rõ tài nguyên nào được công khai và bảo đảm mọi đường ghi đều giữ invariant của domain.

## 6. Checklist trước khi xuất một repository

- Repository này có thật sự đại diện cho tài nguyên mà client nên đọc/ghi trực tiếp không?
- Client có được phép gọi mọi method CRUD được xuất không? Có cần tắt `save`, `delete` hoặc một method cụ thể không?
- Có thể thay đổi entity mà không làm đổi public JSON contract không?
- Các association có làm lộ cấu trúc persistence hoặc cho phép sửa quan hệ vượt quy tắc nghiệp vụ không?
- Các projection/excerpt có làm lộ trường nhạy cảm hoặc tạo tải dữ liệu quá lớn không?
- Authorization đã bao phủ từng method, search resource và association resource chưa?
- Những hành động như approve, cancel, pay, ship có endpoint/use case rõ ràng và kiểm tra invariant không?
- Transaction có bao trùm đúng ranh giới use case không? Quy trình dài có cần outbox, saga hoặc idempotency không?
- Có contract test cho HAL links, payload, status code, validation error và quyền truy cập không?
- Có chính sách versioning và deprecation cho client bên ngoài không?

Nếu nhiều câu trả lời chưa rõ, hãy giới hạn export trước và thiết kế API qua service/DTO. Việc xuất repository nên là quyết định kiến trúc có chủ đích, không phải hệ quả ngẫu nhiên của việc tạo interface.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing repository exposure and HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Overriding response handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
