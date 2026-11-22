# Quá nhiều lớp gián tiếp và chi phí lần theo hành vi

Một phương thức có thể chỉ dài ba dòng nhưng để hiểu kết quả của nó, lập trình viên phải mở thêm sáu tệp. Controller gọi facade; facade gọi manager; manager gọi handler; handler gọi processor; processor gọi service; cuối cùng service mới truy cập dữ liệu hoặc thực thi quy tắc. Mỗi lớp đứng riêng đều có vẻ đơn giản, trong khi **hành vi tổng thể lại khó lần theo**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Chủ đề **Độ phức tạp** không chỉ nói về số lượng nhánh **if** hay vòng lặp. Nó còn liên quan **chi phí nhận thức khi lần theo lời gọi, dữ liệu và tác dụng phụ** qua nhiều lớp gián tiếp.

Mục tiêu của bài học là nhận diện sự gián tiếp dư thừa, hiểu khi nào một lớp trung gian có giá trị thật, và biết cách giảm độ khó bảo trì mà không vô tình làm thay đổi hành vi.

## 1. Gián tiếp trong phần mềm là gì?

**Indirection (gián tiếp)** xảy ra khi bên gọi không làm việc trực tiếp với thành phần thực hiện nhiệm vụ mà đi qua một đối tượng, interface, adapter, handler hoặc phương thức trung gian.

Ví dụ đường đi của một API xem trạng thái đơn hàng:

~~~mermaid
flowchart LR
    A["HTTP Controller"] --> B["OrderStatusFacade"]
    B --> C["OrderStatusManager"]
    C --> D["OrderStatusQueryHandler"]
    D --> E["OrderStatusService"]
    E --> F["OrderRepository"]
    F --> G[("Database")]
~~~

Một lớp trung gian có thể có vai trò tốt: tách giao thức khỏi nghiệp vụ, kiểm soát transaction, giới hạn phụ thuộc bên ngoài hoặc cung cấp hợp đồng ổn định. Vấn đề xuất hiện khi **lớp chỉ chuyển lời gọi**, không thêm trách nhiệm hoặc ý nghĩa nào đáng kể.

| Khái niệm | Câu hỏi cần đặt ra | Ví dụ |
| --- | --- | --- |
| **Lớp gián tiếp** | Lời gọi đi qua bước nào trước khi tới nơi thực hiện? | Controller → Facade → Service. |
| **Trừu tượng hóa có ích** | Bước trung gian có giấu chi tiết dễ thay đổi hoặc tạo hợp đồng rõ không? | PaymentGateway tách nghiệp vụ khỏi API thanh toán. |
| **Gián tiếp dư thừa** | Nếu bỏ bước này, có mất quy tắc hoặc trách nhiệm thật không? | Manager chỉ gọi cùng một phương thức trên Service. |
| **Chi phí lần theo hành vi** | Cần tìm qua bao nhiêu nơi để hiểu dữ liệu, quyết định, lỗi và tác dụng phụ? | Phải mở nhiều interface và implementation mới thấy nơi kiểm tra quyền. |

**Không có quy tắc cố định rằng ít lớp luôn tốt hơn.** Một hệ thống có nhiều tầng được phân trách nhiệm rõ có thể dễ hiểu hơn một lớp khổng lồ. Cần đánh giá giá trị của từng ranh giới.

## 2. Vì sao nhiều lớp trung gian gây khó hiểu?

Khi một người bảo trì muốn sửa hành vi, họ thường cần trả lời:

1. **Điểm vào ở đâu?** Endpoint, job, message consumer hay method được gọi từ nơi khác?
2. **Bản triển khai thực tế nào chạy?** Interface có nhiều implementation không? Dependency injection lựa chọn thế nào?
3. **Quyết định nằm ở đâu?** Điều kiện nghiệp vụ, phân quyền và validation được kiểm tra tại bước nào?
4. **Dữ liệu thay đổi ra sao?** DTO được ánh xạ, trạng thái được cập nhật và giá trị được biến đổi ở đâu?
5. **Tác dụng phụ xảy ra khi nào?** Truy vấn CSDL, phát sự kiện, gửi thanh toán hoặc gọi mạng nằm ở tầng nào?
6. **Đường thất bại đi đâu?** Lớp nào bắt ngoại lệ, rollback, retry hoặc thay đổi mã lỗi?
7. **Kết quả trả về thế nào?** Lớp nào biến kết quả nội bộ thành phản hồi cho người dùng?

Mỗi lần phải chuyển tệp hoặc tìm implementation là thêm một **bước điều hướng**. Mỗi điều kiện, kiểu dữ liệu và quan hệ cần nhớ làm tăng **gánh nặng nhận thức**.

Các dấu hiệu thường gặp:

| Biểu hiện | Hậu quả đối với việc hiểu và sửa mã |
| --- | --- |
| Nhiều method tên **handle / process / execute** | Người đọc khó biết method nào thật sự sở hữu quy tắc. |
| Các lớp chỉ có một dependency và một lời gọi chuyển tiếp | Tăng tệp và bước điều hướng nhưng không bổ sung thông tin. |
| Interface không thể hiện hợp đồng riêng | Phải nhảy từ khai báo sang implementation mà chưa hiểu thêm. |
| DTO giống nhau được chuyển đổi qua nhiều tầng | Tăng công việc mapping và nguy cơ bỏ sót trường. |
| Ngoại lệ được bọc nhiều lần không có lý do | Khó tìm nguyên nhân gốc và hợp đồng lỗi thật. |
| Hành vi được gắn bằng annotation hoặc cấu hình ẩn | Mã nhìn đơn giản nhưng runtime có thể thực hiện thêm công việc. |

Đây chủ yếu là **chi phí hiểu mã**, khác với chi phí runtime. Một lời gọi Java bổ sung không nhất thiết làm API chậm đáng kể, nhưng vẫn có thể khiến việc sửa một quy tắc tốn thời gian.

## 3. Ví dụ: chuỗi lớp chỉ chuyển lời gọi

Giả sử hệ thống có đường đi:

~~~text
OrderStatusController
  -> OrderStatusFacade
    -> OrderStatusManager
      -> OrderStatusQueryHandler
        -> OrderStatusService
          -> OrderRepository
~~~

Các lớp trung gian tương tự nhau. Đoạn dưới đây minh họa ba lớp chuyển tiếp, với kiểu **Status** giả định đã được khai báo trong mô hình đơn hàng:

~~~java
final class OrderStatusFacade {
    private final OrderStatusManager manager;

    OrderStatusFacade(OrderStatusManager manager) {
        this.manager = manager;
    }

    Status getStatus(long orderId, String actorId) {
        return manager.getStatus(orderId, actorId);
    }
}

final class OrderStatusManager {
    private final OrderStatusQueryHandler handler;

    OrderStatusManager(OrderStatusQueryHandler handler) {
        this.handler = handler;
    }

    Status getStatus(long orderId, String actorId) {
        return handler.getStatus(orderId, actorId);
    }
}

final class OrderStatusQueryHandler {
    private final OrderStatusService service;

    OrderStatusQueryHandler(OrderStatusService service) {
        this.service = service;
    }

    Status getStatus(long orderId, String actorId) {
        return service.getStatus(orderId, actorId);
    }
}
~~~

Ba lớp đều giữ nguyên tham số và kết quả. Chúng không áp dụng quy tắc truy cập, không chuyển đổi dữ liệu, không điều phối các bước và không tạo ra hợp đồng riêng có thể thấy trong ví dụ. Người đọc muốn biết **ai được xem trạng thái đơn hàng** phải lần tới OrderStatusService.

Khi một API cần thêm tham số **tenantId**, tham số có thể phải đi qua hàng loạt chữ ký không làm gì với nó. Cấu trúc này làm tăng **phạm vi thay đổi cơ học**, ngay cả khi hành vi chỉ đổi ở một nơi.

Nhưng chưa nên xóa lớp chỉ vì thân method có một dòng: cần kiểm tra **caller, annotation, proxy, transaction, interceptor, hợp đồng công khai và cấu hình framework**. Giá trị hoặc tác dụng phụ có thể nằm ngoài thân phương thức.

## 4. Cấu trúc gọn hơn và ranh giới còn lại

Với ca sử dụng đọc trạng thái đơn hàng, một đường đi rõ ràng hơn có thể là:

~~~mermaid
flowchart LR
    A["HTTP Controller"] --> B["OrderStatusService"]
    B --> C["OrderRepository"]
    C --> D[("Database")]
~~~

Controller chịu trách nhiệm chuyển đổi HTTP. Service thực hiện quy tắc nghiệp vụ và phân quyền. Repository cách ly chi tiết truy xuất dữ liệu.

Ví dụ Java 17 minh họa nơi sở hữu hành vi:

~~~java
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;

public final class OrderStatusService {
    public enum Status { DRAFT, CONFIRMED, CANCELLED }

    public record Order(long id, String ownerId, Status status) {}

    public interface OrderRepository {
        Optional<Order> findById(long orderId);
    }

    private final OrderRepository repository;

    public OrderStatusService(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Status getStatus(long orderId, String actorId) {
        if (orderId <= 0 || actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("Invalid request");
        }

        Order order = repository.findById(orderId)
                .orElseThrow(() -> new NoSuchElementException("Order not found"));

        if (!actorId.equals(order.ownerId())) {
            throw new SecurityException("Access denied");
        }

        return order.status();
    }
}
~~~

Ở đây, các câu hỏi quan trọng được giải quyết tại những nơi dễ dự đoán:

- **Controller:** Request, response HTTP và thông tin người dùng xác thực được chuyển như thế nào?
- **OrderStatusService:** Đầu vào hợp lệ không? Người gọi có được xem đơn này không?
- **OrderRepository:** Đơn hàng được truy xuất từ kho lưu trữ ra sao?

Đoạn ví dụ chưa phải thiết kế đầy đủ cho hệ thống thực tế. **actorId phải đến từ ngữ cảnh xác thực đáng tin cậy ở máy chủ**; cần xem xét phân quyền đa tenant, quyền được ủy quyền và cách phản hồi tránh tiết lộ sự tồn tại của tài nguyên. Việc đơn giản hóa luồng gọi không được làm mất các yêu cầu bảo mật này.

**Mục tiêu không phải chuyển SQL hoặc logic phân quyền vào Controller.** Mục tiêu là bỏ các bước trung gian không có trách nhiệm để người bảo trì tìm đúng nơi quyết định nhanh hơn.

## 5. Lớp gián tiếp nào có giá trị thật?

Một ranh giới có thể đáng giữ dù implementation ngắn, nếu nó bảo vệ một trách nhiệm rõ ràng:

| Ranh giới | Giá trị tạo ra | Khi nào thường hợp lý |
| --- | --- | --- |
| **HTTP Controller/Adapter** | Cô lập giao thức, phân tích request, ánh xạ response. | Các ca sử dụng phục vụ HTTP hoặc cần hợp đồng API rõ. |
| **Application Service** | Điều phối một ca sử dụng và các quy tắc nghiệp vụ. | Có điều kiện, thứ tự thao tác hoặc giao dịch cần giữ. |
| **Repository** | Giấu SQL, CSDL, mapping lưu trữ khỏi nghiệp vụ. | Logic ứng dụng không cần biết chi tiết persistence. |
| **PaymentGateway** | Tách nghiệp vụ khỏi nhà cung cấp thanh toán. | Có hợp đồng tính phí/hoàn tiền ổn định, cần adapter riêng. |
| **Authorization Policy** | Đóng gói quy tắc quyền được nhiều luồng dùng. | Quy tắc có ý nghĩa và cần kiểm thử độc lập. |
| **Retry/Cache Decorator** | Áp dụng chính sách kỹ thuật nhất quán. | Có tính an toàn, phạm vi và cách quan sát được xác định rõ. |
| **Public Facade** | Giữ API ổn định cho các bên sử dụng. | Có caller bên ngoài hoặc yêu cầu tương thích lâu dài. |

Ví dụ một ranh giới ra bên ngoài:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Dù chỉ có một implementation, hợp đồng này giúp nghiệp vụ tránh phụ thuộc vào kiểu HTTP request, định dạng lỗi hoặc thư viện SDK cụ thể của nhà cung cấp. Nếu sau đó thêm **PaymentGatewayManager** rồi **PaymentGatewayInvoker** chỉ để gọi tiếp, hai lớp mới có thể không mang thêm giá trị.

**Một interface với một implementation không tự động là thiết kế thừa.** Nó có thể tạo biên giới kiến trúc, tách mô-đun hoặc ngăn phụ thuộc vào hạ tầng. Cần đánh giá hợp đồng thay vì chỉ đếm implementation.

## 6. Trừu tượng hóa quá sớm có thể tạo độ phức tạp

Một số cấu trúc đáng xem xét lại:

- **Factory** chỉ khởi tạo một đối tượng đơn giản, không có chính sách hoặc nhiều cách tạo.
- **Strategy** có một implementation duy nhất và chưa có khác biệt hành vi thực tế.
- **Base class** mang nhiều hook không được dùng nhưng buộc lớp con biết chi tiết nội bộ.
- **Generic Handler** dùng nhiều tham số kiểu làm mờ ca sử dụng cụ thể.
- **Chuỗi mapper 1:1** thay tên kiểu dữ liệu mà không có chuyển đổi ngữ nghĩa.
- **Interface cho mọi class** theo quy ước cứng nhắc, không tạo ranh giới phụ thuộc có ý nghĩa.

Một phép thử hữu ích: **“Nếu bỏ lớp này và nối caller tới nơi thực sự xử lý, chúng ta mất điều gì?”**

Nếu câu trả lời chỉ là “mất một tệp và một lời gọi”, có thể nên đơn giản hóa. Nếu câu trả lời là “mất hợp đồng công khai, kiểm soát transaction, khả năng cách ly hạ tầng hoặc chính sách dùng chung”, lớp đó có vai trò cần bảo vệ.

Không nên tạo hàng loạt lớp dựa trên khả năng **có thể sẽ cần trong tương lai** khi chưa có trường hợp sử dụng rõ. Trừu tượng hóa giúp quản lý sự khác biệt hiện có hoặc đủ chắc chắn, không phải để dự đoán mọi thay đổi.

## 7. Gián tiếp ẩn trong framework và runtime

Không phải lớp trung gian nào cũng xuất hiện trong đường gọi Java tường minh:

- **Dependency injection** chọn implementation dựa trên cấu hình hoặc profile.
- **Proxy/AOP** thêm transaction, logging, security hoặc cache quanh lời gọi.
- **Annotation** kích hoạt hành vi framework tại thời điểm chạy.
- **Event bus** làm một lời gọi publish dẫn đến nhiều consumer, có thể bất đồng bộ.
- **Reflection/dynamic dispatch** chọn kiểu triển khai lúc chạy.
- **Serialization/mapper** thay đổi dữ liệu ngoài thân service.

Ví dụ một phương thức chỉ gọi service.submit() nhưng có annotation quản lý giao dịch có thể không phải wrapper vô nghĩa. Nếu bỏ lớp đó, **ranh giới transaction** cũng có thể thay đổi. Tương tự, đổi đường gọi từ qua proxy sang gọi trực tiếp trong cùng đối tượng có thể khiến interceptor không được áp dụng, tùy framework.

Vì vậy, **“method chỉ có một dòng” là tín hiệu điều tra**, chưa đủ kết luận phải xóa.

## 8. Lần theo một hành vi cụ thể như thế nào?

Xét một request xem trạng thái đơn:

~~~text
GET /orders/{id}/status
  -> HTTP Controller nhận request
  -> Cơ chế xác thực cung cấp actorId
  -> OrderStatusService kiểm tra đầu vào và quyền
  -> OrderRepository tải dữ liệu
  -> Service trả trạng thái hoặc từ chối
  -> Controller ánh xạ kết quả thành HTTP response
~~~

Để phân tích mã hiện tại, thực hiện theo thứ tự:

1. **Bắt đầu bằng hành vi quan sát được.** Ví dụ endpoint, job hoặc message tạo ra kết quả gì?
2. **Tìm điểm vào thực sự.** Kiểm tra route, handler hoặc cấu hình để tránh suy từ tên class.
3. **Lần theo từng lời gọi.** Ghi rõ lớp nào kiểm tra, biến đổi dữ liệu, điều phối hay chỉ chuyển tiếp.
4. **Đánh dấu ranh giới kỹ thuật.** CSDL, mạng, transaction, cache, hàng đợi, event và tác vụ bất đồng bộ.
5. **Tìm nơi sở hữu bất biến.** Ví dụ, “chỉ chủ đơn được xem trạng thái” phải có chỗ chịu trách nhiệm rõ.
6. **Lần theo các nhánh lỗi.** Kiểm tra exception mapping, rollback, retry, fallback và thông tin được trả cho phía gọi.
7. **Kiểm chứng đường chạy thực tế.** Khi có nhiều implementation hoặc proxy, dùng cấu hình, debugger, log và trace để xác định đúng đích.

Khi IDE đưa bạn tới **interface** qua chức năng “Go to definition”, hãy tiếp tục tìm implementation được dùng trong runtime. Không nên coi định nghĩa interface là nơi duy nhất quyết định hành vi.

### Bản đồ trách nhiệm sau khi lần theo

| Thành phần | Quyết định nó sở hữu | Điều nó không nên phải biết |
| --- | --- | --- |
| Controller | Cách chuyển request/response HTTP | SQL và chi tiết lưu trữ. |
| OrderStatusService | Quy tắc xem trạng thái, kiểm tra quyền | Cấu trúc bảng hoặc HTTP SDK. |
| OrderRepository | Cách đọc đơn và ánh xạ dữ liệu | Chính sách trình bày HTTP. |

Nếu thêm một **OrderStatusManager** chỉ có nhiệm vụ “gọi OrderStatusService”, bản đồ trách nhiệm sẽ không có câu trả lời rõ ràng cho lớp mới.

## 9. Phân biệt độ phức tạp đọc mã và hiệu năng

Đừng đánh đồng nhiều bước gọi với thuật toán chậm:

| Loại chi phí | Điều cần quan sát | Công cụ/biện pháp phù hợp |
| --- | --- | --- |
| **Chi phí nhận thức** | Mất bao nhiêu công để hiểu hoặc sửa ca sử dụng? | Review luồng thực tế, xác định các bước điều hướng và trách nhiệm. |
| **Độ phức tạp thuật toán** | Công sức tăng ra sao theo kích thước đầu vào? | Phân tích thuật toán, độ phức tạp thời gian/bộ nhớ. |
| **Overhead runtime** | Bước trung gian có làm tăng thời gian chạy hoặc tài nguyên? | Profiler, benchmark, distributed tracing và số đo latency. |

Bốn method Java chỉ chuyển tiếp có thể gây nhiều công đọc hơn công chạy. Nhưng nếu mỗi tầng gọi CSDL, mạng, serialize một object lớn hoặc giữ lock, chi phí runtime cũng có thể tăng rõ rệt.

Không kết luận rằng xóa ba lớp sẽ làm API nhanh hơn ba lần nếu không có số đo. Lợi ích chắc chắn cần đánh giá trước hết là **khả năng hiểu và thay đổi**; hiệu năng phải được xác minh riêng.

## 10. Refactor an toàn khi muốn bỏ lớp gián tiếp

Giả sử các lớp **Facade → Manager → Handler** chỉ chuyển tiếp và chưa tìm thấy trách nhiệm độc lập. Một quy trình an toàn gồm:

1. **Xác nhận caller và hợp đồng.** Ai đang gọi? API có được module khác dùng hay không?
2. **Kiểm tra hành vi ẩn.** Tìm transaction, security, cache, retry, metrics, tracing, exception mapping, listener và cấu hình dependency injection.
3. **Xác định nơi sở hữu logic.** Giữ quy tắc trong service, truy cập dữ liệu ở repository và giao thức trong adapter.
4. **Thay đường gọi một cách có kiểm soát.** Kết nối caller tới đúng service hoặc hợp đồng phù hợp.
5. **Xóa cấu trúc không còn dùng.** Loại class, interface, mapping và cấu hình thừa trong phạm vi đã xác nhận.
6. **Kiểm chứng hành vi.** So sánh đầu ra, ngoại lệ, quyền truy cập, transaction, số lần gọi phụ thuộc và tác dụng phụ.
7. **Đọc lại luồng sau sửa.** Một người khác có thể tìm nơi đưa ra quyết định mà không phải lần qua các lớp vô nghĩa không?

Nếu lớp đang là API công khai, không nên phá tương thích một cách vô tình; có thể cần giữ facade trong giai đoạn chuyển đổi hoặc có phương án migration rõ ràng.

### Ví dụ JUnit 5 bảo vệ ca sử dụng

Đoạn kiểm thử sau sử dụng repository giả lập cho OrderStatusService ở phần 4:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class OrderStatusServiceTest {
    @Test
    void ownerCanViewStatus() {
        var service = new OrderStatusService(id -> Optional.of(
                new OrderStatusService.Order(
                        id, "user-A",
                        OrderStatusService.Status.CONFIRMED)));

        assertEquals(OrderStatusService.Status.CONFIRMED,
                service.getStatus(42L, "user-A"));
    }

    @Test
    void anotherUserCannotViewStatus() {
        var service = new OrderStatusService(id -> Optional.of(
                new OrderStatusService.Order(
                        id, "user-A",
                        OrderStatusService.Status.CONFIRMED)));

        assertThrows(SecurityException.class,
                () -> service.getStatus(42L, "user-B"));
    }

    @Test
    void invalidRequestStopsBeforeRepository() {
        var service = new OrderStatusService(id -> {
            fail("Repository must not be called");
            return Optional.empty();
        });

        assertThrows(IllegalArgumentException.class,
                () -> service.getStatus(0L, "user-A"));
    }

    @Test
    void missingOrderIsHandled() {
        var service = new OrderStatusService(id -> Optional.empty());

        assertThrows(java.util.NoSuchElementException.class,
                () -> service.getStatus(42L, "user-A"));
    }
}
~~~

Các ca trên bảo vệ một số quy tắc của **service**; chúng chưa kiểm thử được cấu hình framework, transaction hay mapping HTTP. Nếu refactor thay đổi những điểm này, cần kiểm thử tích hợp phù hợp để chứng minh hành vi vẫn đúng.

## 11. Khi nào nên giữ các lớp trung gian?

Có nhiều trường hợp lớp trung gian có vai trò rõ rệt:

**Ranh giới giao dịch:** Application service điều phối nhiều thao tác ghi và xác định nơi commit/rollback. Gộp không cân nhắc có thể làm trạng thái bị cập nhật nửa chừng.

**Ranh giới với hạ tầng:** PaymentGateway tách nghiệp vụ khỏi SDK và giao thức nhà cung cấp. Bỏ ranh giới khiến thay đổi API bên ngoài lan vào logic nghiệp vụ.

**Quy tắc dùng chung:** Authorization policy tập trung quy tắc quyền để tránh các ca sử dụng thực hiện không nhất quán.

**Ranh giới bảo mật:** Lớp quản lý tenant, kiểm tra quyền hoặc audit có thể có trách nhiệm bắt buộc. Không được xóa chỉ để giảm số lần gọi.

**Tích hợp bất đồng bộ:** Consumer, handler và lớp điều phối có thể sở hữu retry, xác nhận message, chống xử lý lặp và truy vết sự kiện.

**Hợp đồng công khai ổn định:** Facade giữ API tương thích trong khi implementation phía sau thay đổi theo thời gian.

Điểm chung: người bảo trì có thể giải thích **vì sao lớp tồn tại** và **điều gì sẽ mất nếu bỏ nó**.

## 12. Đánh đổi khi giảm tầng gián tiếp

| Lợi ích có thể đạt | Rủi ro cần kiểm tra |
| --- | --- |
| Ít bước điều hướng để tìm quy tắc | API wrapper có thể đang được caller khác sử dụng. |
| Ít tệp và chữ ký phải chỉnh sửa cơ học | Annotation/proxy có thể chứa hành vi không hiển thị trong thân method. |
| Đường đi từ điểm vào tới side effect rõ hơn | Mất chỗ áp dụng validation, caching hoặc mapping riêng nếu bỏ nhầm. |
| Dễ nhận biết chủ sở hữu quy tắc | Gộp quá mức có thể tạo một class chứa nhiều trách nhiệm. |
| Đường lỗi có thể đơn giản hơn | Có thể làm mất thông tin trace/metrics hoặc exception mapping có ý nghĩa. |

Không cố tối thiểu số class bằng mọi giá. Hãy tìm **mức gián tiếp vừa đủ để che giấu thay đổi và làm rõ trách nhiệm**.

## 13. Checklist review một chuỗi gọi nhiều tầng

Khi gặp một tầng trung gian, hãy tự hỏi:

- **Trách nhiệm:** Tầng này thực sự kiểm tra, quyết định, biến đổi, điều phối hay chỉ chuyển tiếp?
- **Hợp đồng:** Nó có bảo vệ interface/biên mô-đun hoặc một đặc tính độc lập không?
- **Caller:** Thành phần nào khác đang phụ thuộc vào nó?
- **Framework:** Có transaction, proxy, caching, security hoặc interceptor không?
- **Dữ liệu:** Nó có làm mất thông tin hoặc ánh xạ dữ liệu cần thiết không?
- **Lỗi:** Nó có đổi, nuốt, ghi nhận hoặc phục hồi lỗi không?
- **Khả năng điều hướng:** Sau khi đọc tên và trách nhiệm của lớp, ta có biết hành vi thật nằm đâu không?
- **Kiểm chứng:** Nếu rút gọn, có thể bảo vệ hành vi bằng kiểm thử hoặc bằng chứng runtime nào?

**Tín hiệu thực tế:** Nếu ba lớp liên tiếp nhận và trả nguyên dữ liệu, không có trách nhiệm riêng, nên xem lại. Đó là **lý do để điều tra**, không phải quy định phải xóa ngay.

## 14. Tình huống tự luyện

### A. Chuỗi wrapper

~~~text
Controller -> CustomerFacade -> CustomerManager
           -> CustomerQueryHandler -> CustomerRepository
~~~

Ba lớp ở giữa chỉ chuyển cùng lệnh **findCustomerById**, không có kiểm tra, mapping, annotation hoặc hợp đồng bên ngoài.

**Câu hỏi:** Bạn sẽ cải thiện cấu trúc bằng cách nào?

**Gợi ý:** Xác minh caller và cấu hình rồi cân nhắc đưa logic truy vấn và kiểm tra nghiệp vụ vào CustomerService, với repository vẫn chịu trách nhiệm truy xuất dữ liệu. Không chuyển SQL vào Controller.

### B. Ranh giới thanh toán

~~~text
CheckoutService -> PaymentGateway -> ExternalPaymentAdapter
~~~

Gateway định nghĩa hợp đồng charge/refund, adapter chuyển đổi định dạng và lỗi riêng của nhà cung cấp.

**Câu hỏi:** Có phải gián tiếp dư thừa không?

**Gợi ý:** Thường là ranh giới cần thiết: nó cô lập phụ thuộc bên ngoài. Hãy xem xét vai trò của từng lớp thay vì chỉ đếm số tầng.

### C. Wrapper có annotation transaction

Một lớp chỉ gọi service.submit(), nhưng đang là nơi framework bắt đầu transaction. Lập trình viên xóa lớp và gọi service trực tiếp, không kiểm tra lại transaction.

**Câu hỏi:** Vì sao một thay đổi cấu trúc nhỏ có thể làm sai dữ liệu?

**Gợi ý:** Thay đổi đường gọi hoặc vị trí annotation có thể thay đổi ranh giới transaction và rollback. Cần xem hành vi của framework và kiểm thử các trường hợp ghi thất bại.

### D. API chậm và có sáu method

API phản hồi chậm; luồng gọi Java đi qua sáu method. Chưa có số đo của từng bước.

**Câu hỏi:** Có thể kết luận sáu lớp gây chậm không?

**Gợi ý:** Chưa. Cần dùng profiler, trace hoặc benchmark để tìm thời gian thật tiêu tốn ở mạng, CSDL, serialization, lock hoặc thuật toán. Vấn đề khó điều hướng và vấn đề hiệu năng cần bằng chứng riêng.

---

**Ghi nhớ:** Gián tiếp hữu ích khi tạo hợp đồng rõ, phân trách nhiệm hoặc bảo vệ ranh giới thay đổi. Gián tiếp trở thành gánh nặng khi người đọc phải lần qua nhiều lớp chỉ để tìm một quyết định mà mỗi lớp gần như không bổ sung thông tin. Hãy đánh giá **đường đi thực tế, trách nhiệm và hành vi ẩn**, rồi tinh giản những lớp dư thừa bằng refactor có kiểm chứng.
