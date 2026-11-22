# Kiểm soát truy cập và nguyên tắc quyền tối thiểu

> **Chương:** Bảo mật  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **xác thực** (authentication) với **phân quyền** (authorization) và kiểm tra quyền ở cấp chức năng, đối tượng, thuộc tính.
2. Diễn đạt một chính sách truy cập dựa trên **chủ thể – tài nguyên – hành động – ngữ cảnh**, không dựa vào việc giao diện đã ẩn nút.
3. Hiểu vai trò và giới hạn của **RBAC**, **ABAC**, **ReBAC**, quyền theo phạm vi tổ chức (*tenant*) và các chính sách kết hợp.
4. Áp dụng **nguyên tắc quyền tối thiểu** (least privilege), **từ chối mặc định** (deny by default) và **phân tách nhiệm vụ** từ API, service tới tài khoản database và tác vụ nền.
5. Viết logic Java kiểm tra quyền theo từng đối tượng; biết vì sao lọc dữ liệu trong repository, thao tác ghi nguyên tử và DTO chỉ chứa trường cần thiết cũng quan trọng.
6. Xây dựng ma trận kiểm thử chống truy cập chéo tài khoản, chéo tenant, vượt vai trò và truy cập ở trạng thái nghiệp vụ không hợp lệ.
7. Giải thích những giới hạn của một kiểm thử quyền: kiểm tra một hàm chính sách không tự chứng minh mọi đường API đều dùng hàm đó.

## 1. Một chức năng chạy đúng vẫn có thể không an toàn

Giả sử API trả thông tin đơn hàng:

~~~http
GET /orders/42 HTTP/1.1
Authorization: Bearer <token-hop-le>
~~~

Người dùng A có thể xem đơn số 42 của mình. Đó là hành vi đúng **trong trường hợp được phép**. Nhưng nếu người dùng B đổi ID trên URL thành `42` rồi cũng nhận được dữ liệu đơn của A, ứng dụng đã vi phạm bảo mật dù cả hai người đều đăng nhập.

Có hai câu hỏi độc lập:

- **Xác thực (authentication):** Yêu cầu đang đại diện cho danh tính nào? Bằng chứng đăng nhập hoặc token có hợp lệ không?
- **Phân quyền (authorization):** Danh tính ấy có được thực hiện **hành động cụ thể** trên **tài nguyên cụ thể** trong **ngữ cảnh hiện tại** không?

Xác thực thành công không cấp mặc định quyền xem mọi dữ liệu. Cũng không thể suy từ việc người dùng nhìn thấy hoặc không nhìn thấy một nút trong giao diện rằng backend sẽ từ chối thao tác không được phép.

Trong phạm vi chất lượng mã, kiểm soát truy cập tốt giúp hệ thống **đáng tin cậy** vì dữ liệu và hành động được bảo vệ, **dễ hiểu** vì chính sách có nơi chịu trách nhiệm rõ, và **dễ thay đổi** vì có thể cập nhật quyền mà không bỏ sót các đường gọi.

### Ba cấp kiểm soát cần phân biệt

| Cấp | Câu hỏi | Lỗi dễ gặp |
| --- | --- | --- |
| **Chức năng (function-level)** | Người dùng có được gọi thao tác hoàn tiền, quản trị hay xuất dữ liệu không? | Người dùng thông thường gọi được endpoint chỉ dành cho nhân viên |
| **Đối tượng/bản ghi (object-level)** | Người dùng có được đọc/sửa **đơn hàng 42** không? | Đổi ID để xem đơn người khác (*BOLA/IDOR*) |
| **Thuộc tính (property/field-level)** | Người dùng được đọc hoặc sửa **trường nào** của đối tượng? | Trả cả thông tin thanh toán nội bộ hoặc cho sửa `paid=true` |

Một API có thể vượt qua kiểm tra cấp chức năng nhưng thất bại ở cấp đối tượng: vai trò `CUSTOMER` được gọi `GET /orders/{id}`, song chỉ được xem đơn của chính mình. Tương tự, có quyền đọc đơn không tự động là có quyền xem toàn bộ thông tin nội bộ của đơn.

## 2. Mô hình quyết định quyền: chủ thể, hành động, tài nguyên, ngữ cảnh

Có thể diễn đạt kiểm tra quyền bằng một câu hỏi nhất quán:

> **Có cho phép chủ thể S thực hiện hành động A trên tài nguyên R trong ngữ cảnh C không?**

| Thành phần | Ví dụ trong hệ thống đơn hàng |
| --- | --- |
| **Chủ thể (subject/principal)** | Khách hàng `alice`; nhân viên `support-7`; service đồng bộ đơn |
| **Hành động (action)** | `order:read`, `order:update-address`, `order:refund`, `order:export` |
| **Tài nguyên (resource)** | Đơn `42` thuộc khách `alice`, tenant `shop-a` |
| **Ngữ cảnh (context)** | Tenant đang hoạt động, trạng thái đơn, ca hỗ trợ được giao, thời hạn quyền |
| **Quyết định (decision)** | Cho phép, từ chối; đôi khi cần thêm nghĩa vụ như audit/phê duyệt |

Một chính sách có thể được viết bằng ngôn ngữ tự nhiên:

> “Khách hàng được đọc bản tóm tắt đơn thuộc cùng tenant và do họ sở hữu. Nhân viên hỗ trợ có quyền `orders:read:tenant` được đọc đơn trong tenant được cấp; không ai tự động xem được đơn của tenant khác.”

Chính sách này rõ hơn “nếu có role `USER` thì cho đọc”. Nó chỉ ra cả **đối tượng**, **hành động** và **ranh giới tenant**. Nếu có chức năng hoàn tiền, phải đặt **chính sách riêng** cho hành động đó, có thể phụ thuộc trạng thái thanh toán, hạn mức và phê duyệt.

### Ma trận quyền minh họa

| Chủ thể | Đọc đơn của mình | Đọc đơn người khác cùng tenant | Sửa địa chỉ đơn mình ở trạng thái DRAFT | Hoàn tiền |
| --- | :---: | :---: | :---: | :---: |
| Khách hàng đã xác thực | Có | Không | Có | Không |
| Nhân viên hỗ trợ có quyền đọc theo tenant | Theo quyền | Có | Không mặc định | Không mặc định |
| Nhân viên xử lý hoàn tiền được cấp quyền | Theo quyền | Theo quyền và phạm vi | Không mặc định | Có điều kiện, giới hạn và ghi nhận |
| Chủ thể thuộc tenant khác | Không | Không | Không | Không |
| Không xác thực | Không | Không | Không | Không |

Đây chỉ là chính sách minh họa; hệ thống thật phải xác định quyền theo nhu cầu nghiệp vụ và quy định áp dụng. **Một nhãn vai trò không tự nói rõ giới hạn đối tượng hoặc thao tác.**

## 3. Từ chối mặc định và nguyên tắc quyền tối thiểu

**Deny by default (mặc định từ chối):** Không có bằng chứng quyền hợp lệ thì không thực hiện thao tác. Một lỗi kết nối tới dịch vụ phân quyền không được vô tình biến thành “cho phép” (*fail open*).

**Least privilege (quyền tối thiểu):** Chỉ cấp những quyền cần để hoàn thành nhiệm vụ đã xác định, trong phạm vi tài nguyên, thời gian và điều kiện cần thiết.

**Kiểm tra ở mọi đường truy cập:** API REST, job nền, giao diện quản trị, export, webhook, GraphQL resolver hay thao tác hàng loạt phải tuân theo chính sách phù hợp. Bảo vệ một controller nhưng để lại một phương thức khác đi thẳng xuống repository có thể tạo đường vòng.

**Phân tách nhiệm vụ (separation of duties):** Với hành động có hậu quả cao, một người không nhất thiết được vừa tạo vừa phê duyệt cùng giao dịch. Đây là biện pháp khác với chỉ giảm số lượng permission; có thể cần xác nhận từ hai chủ thể độc lập.

Ví dụ về quyền tối thiểu:

| Đối tượng được cấp quyền | Quyền quá rộng | Hướng giới hạn |
| --- | --- | --- |
| Khách hàng | Đọc mọi đơn hàng khi đã đăng nhập | Chỉ đơn thuộc quyền truy cập của mình |
| Nhân viên hỗ trợ | Xem tất cả tenant và sửa mọi trường | Chỉ tenant/ca xử lý được phân công; mặc định chỉ đọc các trường cần |
| Dịch vụ gửi email | Tài khoản DB có toàn quyền ghi/xóa đơn | Chỉ đọc dữ liệu cần dựng thông báo; không có quyền sửa giá |
| Job xuất báo cáo | Đọc toàn bộ dữ liệu cá nhân mọi môi trường | Chỉ tập dữ liệu/phạm vi báo cáo được phép và thời hạn cần thiết |
| Tài khoản triển khai | Admin vĩnh viễn trên mọi môi trường | Quyền triển khai theo môi trường và thời hạn; đặc quyền cao có kiểm soát |
| API token | Quyền tổng quát không hết hạn | Scope hẹp, thời hạn hợp lý, cơ chế thu hồi và giám sát |

“Cấp quyền ít nhất” không có nghĩa từ chối mọi thứ khiến hệ thống không dùng được. Quyền phải **đủ để thực hiện nghiệp vụ hợp lệ**, nhưng không mở rộng “phòng khi cần” thiếu kiểm soát.

## 4. RBAC, ABAC và ReBAC: chọn cách mô hình hóa quyền

### 4.1. RBAC — kiểm soát dựa trên vai trò

**Role-Based Access Control** gán quyền cho vai trò, rồi gán vai trò cho người dùng.

~~~text
alice → CUSTOMER → order:read-own
support-7 → SUPPORT → order:read-assigned
refund-2 → REFUND_AGENT → order:refund-limited
~~~

RBAC giúp tổng hợp quyền, thuận tiện quản trị các nhóm công việc quen thuộc. Nhưng nếu chỉ dùng vai trò `SUPPORT` mà không biết nhân viên được giao tenant hoặc đơn nào, RBAC có thể quá thô.

### 4.2. ABAC — kiểm soát dựa trên thuộc tính

**Attribute-Based Access Control** xét thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh.

Ví dụ:

~~~text
ALLOW order:update-address
WHEN actor.id == order.ownerId
 AND actor.tenantId == order.tenantId
 AND order.status == DRAFT
 AND actor.isActive == true
~~~

Chính sách ABAC diễn đạt được quyền phụ thuộc trạng thái và phạm vi. Đổi lại, cần quản lý nguồn thuộc tính đáng tin cậy: nếu `actor.tenantId` chỉ do client tùy ý gửi lên, chính sách trông chặt chẽ vẫn không an toàn.

### 4.3. ReBAC — kiểm soát dựa trên quan hệ

**Relationship-Based Access Control** xem các quan hệ đã được xác lập, chẳng hạn `user → member-of → organization`, `agent → assigned-to → ticket`, hoặc `document → shared-with → team`.

ReBAC hữu ích với tài liệu được chia sẻ, cây tổ chức và quyền phân cấp. Tuy nhiên, quan hệ có thể thay đổi: cần xác định thời điểm cập nhật, thu hồi và tính nhất quán của dữ liệu quyền.

### 4.4. Kết hợp thực tế

Một hệ thống có thể dùng **RBAC để xác định loại hành động**, **ABAC để kiểm tra thuộc tính bản ghi**, và **ReBAC để xác minh quan hệ phân công**. Không nên chọn một mô hình chỉ vì tên gọi; hãy bắt đầu từ chính sách thực tế.

| Nhu cầu | Mô hình thường hữu ích | Điểm phải kiểm tra |
| --- | --- | --- |
| Chỉ vai trò kế toán được phát hành hóa đơn | RBAC | Vai trò có đang được cấp đúng người? |
| Khách chỉ sửa địa chỉ của đơn DRAFT thuộc mình | ABAC | Chủ sở hữu, tenant và trạng thái được xác minh phía máy chủ? |
| Nhân viên chỉ xem ticket được phân công | ReBAC hoặc ABAC | Quan hệ phân công có còn hiệu lực? |
| Admin tenant chỉ quản trị tenant hiện tại | RBAC + điều kiện tenant | Quyền admin có bị áp dụng xuyên tenant? |
| Duyệt hoàn tiền vượt hạn mức | Chính sách kết hợp và quy trình phê duyệt | Hạn mức, danh tính người duyệt và tính độc lập |

## 5. Đặt kiểm soát ở ranh giới tin cậy

Hãy xem luồng một request:

~~~mermaid
flowchart LR
    C["Client không đáng tin"] --> A["API: xác thực request"]
    A --> P["Policy: kiểm tra hành động/tài nguyên"]
    P --> S["Service: giữ bất biến nghiệp vụ"]
    S --> R["Repository: giới hạn truy vấn theo tenant/quyền"]
    R --> D[("Database")]
    S --> O["DTO: chỉ trường được phép trả về"]
    O --> C
    P -. "Audit có kiểm soát" .-> L["Log / giám sát"]
~~~

Những kiểm soát ở các lớp có nhiệm vụ khác nhau:

1. **API/ingress:** Xác thực token/phiên, kiểm tra quyền truy cập endpoint, validate input cơ bản.
2. **Application/service:** Quyết định có được thực hiện **hành động trên đối tượng cụ thể** không; giữ chính sách sát use case.
3. **Repository/data access:** Ràng buộc tenant và phạm vi bản ghi ngay trong truy vấn; tránh tải hoặc sửa rộng rồi lọc tùy tiện.
4. **Response mapping:** Không trả trực tiếp toàn bộ entity có chứa trường nội bộ hoặc bí mật nếu client chỉ cần bản tóm tắt.
5. **Hạ tầng:** Giới hạn quyền tài khoản database/service, quản lý secret, theo dõi truy cập và thu hồi.

Đây là **phòng vệ nhiều lớp** (*defense in depth*), không phải lý do sao chép các phiên bản khác nhau của cùng chính sách ở khắp nơi. Quyết định nghiệp vụ nên có **nguồn quy tắc nhất quán**, còn các lớp khác hỗ trợ bảo vệ ranh giới phù hợp.

**Ranh giới tin cậy quan trọng:** `userId`, `tenantId`, `role`, `isAdmin` nằm trong URL/body/header tùy ý có thể bị client sửa. Chúng không được tự trở thành danh tính hoặc quyền. Đầu vào từ client chỉ là yêu cầu; danh tính và phạm vi quyền phải lấy từ **ngữ cảnh xác thực đã được máy chủ xác minh**, có thể kết hợp dữ liệu phân quyền từ nguồn đáng tin cậy.

## 6. Ví dụ Java: phân quyền theo đơn hàng và tenant

Giả sử một ứng dụng Java có hệ thống đa tenant. Mỗi đơn thuộc một tenant và có người sở hữu. API “Xem tóm tắt đơn” phải bảo đảm:

- Người dùng chỉ xem đơn thuộc tenant đang được cấp quyền.
- Chủ đơn được xem tóm tắt đơn mình.
- Nhân viên có permission `orders:read:tenant` được xem tóm tắt các đơn cùng tenant, **không mặc nhiên được xem mọi tenant**.
- Phản hồi chỉ gồm mã đơn và số tiền; địa chỉ giao hàng và dữ liệu nội bộ không được trả ở endpoint này.
- Khi tài nguyên không tồn tại hoặc không có quyền, phản hồi công khai có thể cố ý không tiết lộ sự tồn tại của đơn, theo chính sách API.

### 6.1. Các kiểu và service có hợp đồng rõ

Ví dụ Java 17:

~~~java
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

record Actor(String userId, String tenantId, Set<String> permissions) {
    Actor {
        Objects.requireNonNull(userId, "userId");
        Objects.requireNonNull(tenantId, "tenantId");
        if (userId.isBlank() || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid authenticated identity");
        }
        permissions = Set.copyOf(permissions); // Không-null, snapshot bất biến.
    }
}

record Order(
        long id,
        String tenantId,
        String ownerId,
        long amountDueVnd
) {}

record OrderSummary(long id, long amountDueVnd) {}

interface OrderRepository {
    Optional<Order> findByIdAndTenant(long orderId, String tenantId);
}

final class OrderReader {
    private final OrderRepository repository;

    OrderReader(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    Optional<OrderSummary> read(Actor actor, long orderId) {
        Objects.requireNonNull(actor, "actor");

        return repository.findByIdAndTenant(orderId, actor.tenantId())
                .filter(order ->
                        actor.tenantId().equals(order.tenantId())
                        && (actor.userId().equals(order.ownerId())
                        || actor.permissions().contains("orders:read:tenant")))
                .map(order ->
                        new OrderSummary(order.id(), order.amountDueVnd()));
    }
}
~~~

Trong ví dụ:

1. `Actor` là đối tượng **đã xác thực/được tin cậy của phía server**. Không tạo `Actor` bằng cách tin trực tiếp vào `userId`, `tenantId`, `permissions` mà client gửi trong JSON.
2. Repository có hợp đồng `findByIdAndTenant` để loại bản ghi ngoài tenant ở cấp dữ liệu. Service kiểm tra tiếp owner hoặc permission theo chính sách.
3. Permission `orders:read:tenant` **chỉ có ý nghĩa trong tenant của Actor**, không phải quyền đọc toàn hệ thống.
4. `OrderSummary` giúp kiểm soát trường đầu ra; thêm trường mới phải được review theo mục đích công bố dữ liệu.
5. `Optional.empty()` gộp kết quả “không tìm thấy/không được công bố” ở **giao diện đọc công khai** theo một chính sách chống lộ sự tồn tại tài nguyên; bên trong cần cơ chế audit riêng nếu cần phân biệt truy cập bị từ chối.
6. Kiểu `Actor` bất biến về tham chiếu tập quyền, nhưng **không tự giải quyết việc thu hồi quyền giữa phiên đăng nhập**. Nguồn và thời hạn hiệu lực của quyền phải được thiết kế rõ.

Đoạn mã minh họa các hợp đồng cốt lõi, không tự triển khai xác thực token, HTTP status, auditing hoặc database. Những phần đó phải được ghép và kiểm thử ở ranh giới thật.

### 6.2. Truy vấn dữ liệu cần tự giới hạn phạm vi

Triển khai `findByIdAndTenant` phải bảo đảm điều kiện lọc tenant thực sự được áp dụng. Với SQL tham số:

~~~sql
SELECT id, tenant_id, owner_id, amount_due_vnd
FROM orders
WHERE id = ? AND tenant_id = ?;
~~~

Giá trị `tenant_id` phải đến từ ngữ cảnh đã xác minh. Không nên làm như sau:

~~~java
// Sai: tenantId được lấy trực tiếp từ query parameter của người gọi
// và dùng thay cho tenant thực mà họ được cấp quyền.
String tenantId = request.getParameter("tenantId");
return repository.findByIdAndTenant(orderId, tenantId);
~~~

Dùng `PreparedStatement` hoặc API truy vấn tham số giúp giảm SQL injection ở vị trí giá trị, nhưng **không thay thế phân quyền**. Một truy vấn có tham số vẫn có thể đọc sai tenant nếu tham số tenant đến từ nguồn không đáng tin.

Để **liệt kê hoặc tìm kiếm nhiều bản ghi**, phải áp dụng phạm vi tenant và quyền ngay tại truy vấn/trước phân trang. Nếu lấy 100 đơn rồi lọc trong bộ nhớ, tổng số trang, số lượng bản ghi hoặc thông tin thống kê có thể bị sai; đồng thời có nguy cơ đã tải dữ liệu không được phép.

### 6.3. Quyền là điều kiện theo hành động, không phải thuộc tính cố định của người dùng

Có quyền **đọc đơn** không đồng nghĩa có quyền **sửa địa chỉ**, **duyệt hoàn tiền** hay **xóa đơn**. Một hành động có thể còn phụ thuộc trạng thái:

~~~text
ALLOW order:update-address
IF actor.id == order.ownerId
 AND actor.tenantId == order.tenantId
 AND order.status == DRAFT
~~~

Với hành động hoàn tiền, điều kiện có thể thêm quyền chuyên biệt, hạn mức, thời gian, trạng thái `PAID` và người phê duyệt độc lập. Không nên biến permission `orders:read:tenant` thành “quyền tổng quát với mọi hành động trên đơn hàng”.

## 7. Kiểm thử mã phân quyền: đúng khi được phép, từ chối khi không được phép

Unit test có thể chứng minh **logic chính sách** của `OrderReader` trong ví dụ. Test dùng repository giả nhưng phải giữ chính sách tenant của contract:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Set;

class OrderReaderTest {
    private final List<Order> orders = List.of(
            new Order(42L, "shop-a", "alice", 240_000L),
            new Order(43L, "shop-a", "bob", 150_000L),
            new Order(42L, "shop-b", "carol", 990_000L)
    );

    private final OrderRepository fakeRepository = (orderId, tenantId) ->
            orders.stream()
                    .filter(order -> order.id() == orderId)
                    .filter(order -> order.tenantId().equals(tenantId))
                    .findFirst();

    private final OrderReader reader = new OrderReader(fakeRepository);

    @Test
    void ownerCanReadOwnOrder() {
        Actor alice = new Actor("alice", "shop-a", Set.of());

        assertEquals(
                new OrderSummary(42L, 240_000L),
                reader.read(alice, 42L).orElseThrow());
    }

    @Test
    void anotherCustomerInSameTenantCannotReadIt() {
        Actor bob = new Actor("bob", "shop-a", Set.of());

        assertTrue(reader.read(bob, 42L).isEmpty());
    }

    @Test
    void supportPermissionDoesNotCrossTenant() {
        Actor support = new Actor(
                "support-1", "shop-b", Set.of("orders:read:tenant"));

        assertEquals(
                new OrderSummary(42L, 990_000L),
                reader.read(support, 42L).orElseThrow());
        assertTrue(reader.read(support, 43L).isEmpty());
    }

    @Test
    void sameTenantSupportCanReadOtherOwnersOrder() {
        Actor support = new Actor(
                "support-2", "shop-a", Set.of("orders:read:tenant"));

        assertTrue(reader.read(support, 42L).isPresent());
    }
}
~~~

Bài test `supportPermissionDoesNotCrossTenant` thể hiện rằng `orderId = 42` có thể lặp lại giữa các tenant trong ví dụ; chính sách truy vấn theo tenant giúp chọn đúng bản ghi. Nó cũng xác minh nhân viên thuộc `shop-b` không đọc được đơn `43` chỉ tồn tại ở `shop-a`.

**Giới hạn:** Test này không chứng minh:

- API đã xây dựng `Actor` từ token hợp lệ chứ không từ body/header giả mạo.
- Mọi endpoint, job và export đều đi qua `OrderReader` hoặc chính sách tương ứng.
- Triển khai repository thật đã thêm `WHERE tenant_id = ?`.
- Response JSON không vô tình trả thêm entity có trường nhạy cảm.
- Việc thu hồi quyền có hiệu lực đúng thời điểm.

Vì vậy, kiểm thử cấp API/integration với database và hai danh tính/tenant là cần thiết cho ranh giới thật. Các bài test này bổ sung chứ không thay thế unit test chính sách.

## 8. Kiểm soát thao tác ghi và tranh chấp trạng thái

Quyết định quyền thường phụ thuộc **trạng thái tài nguyên**: chỉ đơn ở `DRAFT` mới được sửa địa chỉ. Nếu service đọc trạng thái, kiểm tra quyền, rồi sau một khoảng thời gian mới ghi, trạng thái có thể đã đổi do request khác. Đây là rủi ro **time-of-check/time-of-use (TOCTOU)**.

Một kỹ thuật bổ sung là gắn những điều kiện có liên quan vào **thao tác cập nhật nguyên tử ở database**:

~~~sql
UPDATE orders
SET shipping_address = ?
WHERE id = ?
  AND tenant_id = ?
  AND owner_id = ?
  AND status = 'DRAFT';
~~~

Giá trị `tenant_id` và `owner_id` phải đến từ ngữ cảnh xác thực đã được xác minh, không lấy trực tiếp từ payload do client tự khai. Khi số hàng bị ảnh hưởng bằng 0, ứng dụng cần xử lý theo hợp đồng: có thể không tồn tại, không có quyền hoặc không còn ở trạng thái cho phép.

Đây là biện pháp phù hợp với **chính sách chủ sở hữu và trạng thái đơn đơn giản**. Với quyền nhân viên, phê duyệt hai bước hoặc quan hệ phức tạp, điều kiện UPDATE và transaction phải được thiết kế tương ứng; không thể dùng một SQL mẫu cho mọi hệ thống.

Cần xem thêm:

- **Mass assignment:** Không nhận toàn bộ JSON rồi ánh xạ trực tiếp lên entity nếu client chỉ được sửa `shippingAddress`; các trường như `ownerId`, `paid`, `amountDueVnd` phải được kiểm soát riêng.
- **Kiểm tra trên PUT/PATCH/DELETE:** Nhiều hệ thống bảo vệ GET nhưng bỏ sót thao tác ghi hoặc endpoint xử lý hàng loạt.
- **Cập nhật đồng thời:** Tùy chính sách, có thể cần version/optimistic locking để tránh một yêu cầu ghi đè dữ liệu mới hơn.
- **Tác dụng phụ ngoài DB:** Nếu đã gửi yêu cầu thanh toán hoặc email, rollback DB không tự hoàn tác hệ thống ngoài; cần cơ chế trạng thái và bù trừ phù hợp.
- **Thu hồi quyền giữa lúc xử lý:** Cần quy định thời điểm kiểm tra quyền và cách xử lý với công việc kéo dài; kiểm tra lúc bắt đầu có thể chưa đủ.

## 9. Ranh giới tenant không phải bộ lọc giao diện

Trong hệ thống nhiều tenant, lỗi thường gặp là tin rằng người dùng chọn tenant trên giao diện có nghĩa đã được cấp tenant đó.

Ví dụ client gửi:

~~~json
{
  "tenantId": "shop-b",
  "orderId": 42
}
~~~

Nếu server dùng `tenantId` này để tìm và trả đơn mà không kiểm tra quyền của danh tính trên `shop-b`, người dùng có thể tự chọn tổ chức khác để truy cập dữ liệu.

Hướng an toàn:

1. Xác thực danh tính.
2. Xác minh người dùng hoặc service **được cấp quyền đối với tenant được chọn**.
3. Xây dựng ngữ cảnh quyền từ dữ liệu đã xác minh, không lấy các quyền trong payload làm sự thật.
4. Buộc mọi truy vấn/lệnh ghi sử dụng tenant đó.
5. Đảm bảo các luồng nền, cache, export và file đính kèm cũng dùng đúng phạm vi.
6. Kiểm thử với ít nhất hai tenant và dữ liệu có ID giống nhau hoặc gần giống nhau.

**Cơ chế database hỗ trợ Row-Level Security (RLS)** có thể tăng phòng vệ nếu phù hợp và được cấu hình đúng. Nhưng phải kiểm tra quyền DB role, chính sách RLS, ngữ cảnh tenant trên từng kết nối và **việc tái sử dụng connection pool** để tránh để sót ngữ cảnh tenant từ request trước. Không nên coi việc bật một tính năng DB là bằng chứng toàn bộ ứng dụng đã cô lập tenant.

## 10. Quyền tối thiểu ở cấp dịch vụ, cơ sở dữ liệu và hạ tầng

Kiểm soát truy cập không chỉ áp dụng cho người dùng cuối. Mỗi service account, tiến trình nền và quyền database là một **chủ thể** cần chính sách riêng.

### 10.1. Tài khoản dịch vụ và database

Giả sử service gửi email xác nhận chỉ cần đọc mã đơn, địa chỉ email và trạng thái gửi. Nếu cấp tài khoản database toàn quyền `SELECT/INSERT/UPDATE/DELETE` trên mọi bảng, việc một thành phần này bị xâm nhập có thể lan sang dữ liệu không liên quan.

Tùy kiến trúc, có thể:

- Chỉ cấp quyền đọc hoặc đọc từ view chứa các trường được phép.
- Không cấp khả năng xóa/sửa dữ liệu nghiệp vụ nếu service không cần.
- Dùng các danh tính riêng cho runtime, migration, quản trị và tác vụ hỗ trợ.
- Phân tách quyền giữa môi trường thử nghiệm và môi trường thật.
- Giới hạn tài nguyên, mạng và secret mà workload có thể truy cập.

Ví dụ ý tưởng quyền DB (cú pháp và cơ chế thực thi phụ thuộc hệ quản trị):

~~~sql
-- Minh họa chủ ý phân quyền, không phải script áp dụng nguyên xi.
GRANT SELECT ON order_notification_view TO notification_service;
-- Không tự cấp UPDATE/DELETE trên orders cho notification_service.
~~~

Không nên áp dụng trực tiếp một đoạn `GRANT` minh họa khi chưa kiểm tra quyền kế thừa, schema, view và cơ chế cấp quyền của hệ quản trị thực tế.

### 10.2. Scope và thời hạn hiệu lực của token

Một access token có thể chứa scope như `orders:read`, nhưng scope **không đủ** để tự kết luận được đọc mọi đơn. Vẫn cần kiểm tra chủ thể, tenant, quan hệ sở hữu và chính sách nghiệp vụ.

Với token/credential:

- Xác minh chữ ký hoặc cơ chế xác thực tương ứng, issuer, audience, thời hạn và điều kiện sử dụng theo hợp đồng.
- Cấp scope hẹp nhất; phân biệt quyền đọc, ghi, export và quản trị.
- Tránh sử dụng một token đặc quyền cho nhiều dịch vụ không cần cùng quyền.
- Thiết kế thu hồi/rotation và xử lý khi tài khoản bị khóa, nhân viên chuyển nhóm hoặc kết thúc nhiệm vụ.
- Không đưa token và bí mật vào log, URL công khai hoặc response không cần thiết.

**Một JWT còn thời hạn không tự chứng minh quyền bên trong còn hợp lệ**, nếu hệ thống có chính sách thu hồi tức thời. Cần xác định cách lấy hoặc làm mới quyết định quyền, thời gian cache và khả năng chấp nhận độ trễ thu hồi.

### 10.3. Quyền cao tạm thời và tình huống khẩn cấp

Có nhiệm vụ cần quyền nâng cao, chẳng hạn xử lý sự cố. Một thiết kế phù hợp thường giới hạn **ai**, **được làm gì**, **trong bao lâu**, **vì lý do nào**, cùng thông tin phê duyệt/audit thích hợp. Có thể áp dụng quyền nâng cao tạm thời (*just-in-time access*) hoặc đường truy cập khẩn cấp (*break-glass*) được quy định rõ.

Không nên tạo một tài khoản “super admin” dùng chung và không có lịch sử truy cập chỉ vì thuận tiện vận hành. Nhưng cũng không nên xóa khả năng ứng cứu sự cố cần thiết; nguyên tắc là **đặc quyền có mục đích, có thời hạn và có thể truy vết**.

## 11. Trả lỗi và ghi nhận truy cập mà không làm lộ dữ liệu

Khi không có quyền, server phải từ chối hành động. Nhưng **trả gì cho client** và **ghi gì trong nội bộ** là hai câu hỏi khác nhau.

| Trường hợp | Hướng xử lý HTTP thường gặp | Điều cần cân nhắc |
| --- | --- | --- |
| Chưa có danh tính hợp lệ | `401 Unauthorized` với cơ chế xác thực phù hợp | Không tiết lộ token hoặc thông tin xác thực |
| Có danh tính nhưng thiếu quyền thực hiện | `403 Forbidden` | Có thể cho biết thao tác bị cấm |
| Tài nguyên không tồn tại hoặc không muốn tiết lộ nó tồn tại | `404 Not Found` theo chính sách | Tránh cho phép dò ID và suy thông tin về chủ sở hữu |
| Hành động không hợp lệ do trạng thái nghiệp vụ | `409 Conflict` hoặc mã phù hợp hợp đồng | Không nhầm với lỗi xác thực hay không tìm thấy |
| Dịch vụ đánh giá quyền không khả dụng | Lỗi được xử lý theo chính sách an toàn | Không mặc định cấp quyền để “duy trì dịch vụ” |

Lựa chọn `403` hay `404` tùy mục đích của API và chính sách giảm rò rỉ thông tin. Cần nhất quán về hành vi quan sát được; nếu cần chống dò tài nguyên, không chỉ che message mà vẫn để lộ thông tin qua các đường khác.

### Audit nên ghi những gì?

Một sự kiện có thể ghi:

- Mã tương quan request hoặc operation.
- Danh tính được xác minh (hoặc tham chiếu phù hợp), hành động và loại tài nguyên.
- Quyết định cho phép/từ chối và mã lý do do server kiểm soát.
- Thời điểm, phạm vi tenant, điểm thực thi chính sách.
- Thông tin phê duyệt hoặc quyền tạm thời nếu nghiệp vụ yêu cầu.

Không ghi toàn bộ token, mật khẩu, payload chứa dữ liệu cá nhân hoặc địa chỉ giao hàng chỉ để “đủ log”. Quyền đọc audit log, thời gian lưu và việc xuất log cũng phải được kiểm soát.

**Audit không thay thế authorization:** ghi lại một hành động trái phép sau khi đã cho thực hiện không ngăn được thiệt hại. **Authorization cũng không thay thế audit:** với thao tác giá trị cao, cần biết ai đã làm gì để điều tra và kiểm tra tuân thủ.

## 12. Một hệ thống có nhiều đường đi cần một chính sách nhất quán

Một chính sách đúng trong service nhưng không được gọi từ endpoint phụ vẫn là lỗ hổng. Những đường cần xem xét:

| Đường truy cập | Điều dễ bị bỏ sót |
| --- | --- |
| REST/GraphQL API | Resolver hoặc route khác không kiểm tra quyền theo tài nguyên |
| Danh sách, tìm kiếm, thống kê | Chỉ lọc sau phân trang; tổng số bản ghi tiết lộ dữ liệu ngoài phạm vi |
| Xuất CSV/PDF/báo cáo | Có quyền xem trang không đồng nghĩa có quyền xuất toàn bộ trường |
| Tệp đính kèm | Link tải file có thể truy cập trực tiếp mà bỏ qua kiểm tra quyền đơn mẹ |
| Batch operation | Có quyền với một ID nhưng không kiểm tra từng phần tử của danh sách |
| Job nền/webhook | Thiếu danh tính dịch vụ rõ, dùng quyền admin quá rộng |
| Cache | Khóa cache thiếu tenant hoặc quyền; trả dữ liệu đã cache cho chủ thể khác |
| Event/notification | Phát sự kiện chứa dữ liệu không phù hợp tới consumer hoặc kênh không được cấp |
| Admin/debug endpoint | Chỉ ẩn đường dẫn; không xác thực và phân quyền thực |

Ví dụ khóa cache chỉ dựa vào `orderId` có thể nguy hiểm nếu cùng ID tồn tại ở nhiều tenant hoặc kết quả phụ thuộc quyền xem trường. Cần thiết kế khóa và vòng đời cache theo **phạm vi dữ liệu cùng chính sách quyền**, hoặc chỉ cache nội dung không phụ thuộc chủ thể theo cơ chế có thể chứng minh an toàn.

Với dữ liệu export, cần phân quyền **trước khi chạy truy vấn lớn**, không xuất toàn bộ rồi lọc một phần file sau cùng. Khi một danh sách gồm cả mục có và không có quyền, hợp đồng phải quy định có **từ chối toàn bộ** hay xử lý từng mục, cùng cách báo cáo kết quả không làm lộ thông tin.

## 13. Kiểm thử quyền theo ma trận rủi ro

Không nên chỉ kiểm thử “admin gọi API thành công”. Kiểm thử truy cập phải bao gồm các kịch bản **bị từ chối** và các ranh giới khó nhìn thấy.

### 13.1. Ma trận bắt buộc cho một API đọc đơn

| Tình huống | Kỳ vọng |
| --- | --- |
| Chủ đơn, cùng tenant, token hợp lệ | Chỉ nhận trường được phép |
| Khách khác cùng tenant biết ID của đơn | Bị từ chối hoặc phản hồi không tồn tại theo chính sách |
| Khách có ID thuộc tenant khác | Không nhận dữ liệu và không lộ trường nhạy cảm |
| Nhân viên có quyền đọc theo tenant A | Đọc trong A theo chính sách; không đọc tenant B |
| Nhân viên chỉ có quyền export nhưng không có quyền đọc đơn | Không tự suy ra quyền đọc nếu chính sách không cấp |
| Token/phiên không hợp lệ, hết hạn hoặc bị thu hồi | Không được coi là danh tính hợp lệ theo thiết kế |
| Client tự gửi `isAdmin=true` hoặc `tenantId` khác | Không thay đổi quyền được xác minh phía server |
| Service kiểm tra quyền gặp lỗi | Không cho truy cập trái phép; ghi nhận lỗi để xử lý |
| API trả lỗi | Không lộ thông tin nhạy cảm/chi tiết nội bộ |
| API trả thành công | Không có trường không được cấp; kết quả không lẫn dữ liệu tenant khác |

### 13.2. Ma trận cho thao tác ghi và vòng đời quyền

| Tình huống | Kỳ vọng |
| --- | --- |
| Chủ đơn sửa địa chỉ khi đơn DRAFT | Thành công nếu đủ điều kiện |
| Chủ đơn sửa địa chỉ khi đơn PAID/SHIPPED | Bị từ chối theo quy tắc trạng thái |
| Người khác sửa địa chỉ bằng cách đổi `orderId` | Bị từ chối |
| Client gửi kèm `paid=true` hoặc `ownerId` trong DTO | Không được ghi trái phép các trường này |
| Hai request đổi trạng thái cạnh tranh | Không bỏ qua điều kiện quyền/trạng thái ở lúc commit |
| Quyền nhân viên vừa bị thu hồi | Quyết định quyền mới tuân theo chính sách hiệu lực/thu hồi |
| Gọi batch gồm nhiều ID, một ID ngoài phạm vi | Có kết quả đúng theo chính sách toàn phần/từng phần |
| Đổi chính sách quyền trong lúc job nền còn chạy | Có điểm kiểm tra lại hoặc thời hạn quyền rõ |
| Tải tệp đính kèm bằng URL trực tiếp | Kiểm tra quyền tương ứng hoặc dùng liên kết có phạm vi/thời hạn |
| Gọi API qua đường tích hợp thứ hai | Chính sách không bị bỏ qua |

### 13.3. Chọn đúng cấp kiểm thử

- **Unit test:** xác minh ma trận chính sách như `owner/tenant/action/status`, trường hợp biên và mặc định từ chối.
- **API/integration test:** xác minh middleware dựng danh tính đáng tin, service thực thi kiểm tra, repository lọc đúng tenant, các status code và DTO hợp đồng.
- **Database test:** xác minh query thật, transaction, ràng buộc cập nhật và cấu hình RLS nếu có.
- **Contract test:** xác minh các client hiểu đúng `401/403/404` và dữ liệu trả về; quyền có thể thay đổi theo phiên bản API.
- **Đánh giá bảo mật được ủy quyền:** đối với luồng rủi ro cao, có thể cần kiểm thử chuyên sâu hoặc review độc lập theo quy trình tổ chức.

**Coverage cao không chứng minh không có BOLA/IDOR.** Một bộ test có thể chạy qua mọi câu lệnh nhưng không có tài khoản thứ hai, tenant thứ hai hoặc kịch bản thay ID. Điều phải kiểm chứng là **tác động thực của policy lên các đường truy cập**.

## 14. Kết hợp bảo mật với cấu trúc mã dễ hiểu

Trong một module code quality, bảo mật không nên trở thành một mạng điều kiện `if` rải rác, khó tìm hoặc khó kiểm chứng. Cấu trúc tốt thường có:

1. **Hợp đồng hành động rõ:** `readOrder`, `updateShippingAddress`, `refundOrder` là những thao tác khác nhau, không dùng một cờ `isAdmin` để bỏ qua toàn bộ quy tắc.
2. **Nguồn danh tính đáng tin:** một điểm chuẩn hóa dữ liệu xác thực, không để mỗi controller tự đoán từ request.
3. **Chính sách tập trung theo phạm vi hợp lý:** quyết định quyền có tên và test riêng; tránh tạo một “siêu policy engine” khó hiểu khi hệ thống còn đơn giản.
4. **Repository bảo vệ phạm vi dữ liệu:** query có tenant và điều kiện được kiểm chứng; các thao tác ghi cần kiểm soát concurrency.
5. **DTO và serializer có chủ đích:** chỉ trả các trường cần cho ca sử dụng.
6. **Phương án ghi audit vừa đủ:** hỗ trợ điều tra nhưng không tiết lộ dữ liệu nhạy cảm.
7. **Kiểm thử theo hành vi bị cấm:** tạo dữ liệu và danh tính đối lập, không chỉ test happy path.

Ví dụ, một phương thức như sau khó review:

~~~java
// Phản ví dụ: nhiều cờ mở đường tắt, không gắn với tài nguyên cụ thể.
if (isAdmin || trusted || bypassCheck || userLoggedIn) {
    return orderRepository.findById(orderId);
}
~~~

Tên `trusted` hoặc `bypassCheck` không giải thích **ai cấp quyền**, **quyền gì**, **đối với tài nguyên nào**. Trong bản sửa, nên định nghĩa một policy có đầu vào xác thực, tài nguyên và hành động rõ ràng; mỗi ngoại lệ phải có lý do và phạm vi được kiểm soát.

### Dấu hiệu cần hỏi lại trong code review

- “Role `ADMIN` này có phạm vi **toàn hệ thống** hay chỉ tenant?”
- “`userId` và `tenantId` ở đâu ra, đã được xác minh hay do client khai?”
- “Quyền kiểm tra trên **bản ghi cụ thể** hay chỉ trên endpoint?”
- “Các route export, update, batch và file download có đi qua chính sách tương đương không?”
- “Nếu dịch vụ quyền timeout, ứng dụng có từ chối không?”
- “Có giữ lại trạng thái quyền đã thu hồi trong cache/token quá lâu không?”
- “Khi hai request chạy cùng lúc, kiểm tra ở service có còn đúng tại thời điểm ghi?”
- “Test nào chứng minh một khách không đọc/sửa được đơn của khách khác?”

Đặt câu hỏi cụ thể giúp review có thể kiểm chứng, thay vì chỉ ghi “cần tăng bảo mật”.

## 15. Những ngộ nhận thường gặp

**“Đã đăng nhập là được dùng API.”** Xác thực chỉ nhận diện chủ thể; phân quyền quyết định từng hành động trên từng tài nguyên.

**“Frontend ẩn nút là đủ.”** Client có thể gửi HTTP request tùy ý. Quyết định quyền phải được server thực thi.

**“Chỉ cần role `USER` hoặc `SUPPORT`.”** Vai trò thường chưa nói rõ đối tượng, tenant, trạng thái và hạn mức.

**“Dùng PreparedStatement là đã chống truy cập chéo tenant.”** Truy vấn tham số chống SQL injection ở giá trị; nó không xác minh người gọi được phép dùng tenant được truyền vào.

**“Admin phải có quyền với mọi thứ.”** Có nhiều loại admin và phạm vi. Một tenant admin không mặc nhiên là global admin; quyền cao phải được định nghĩa rõ.

**“Không trả trường bí mật là không cần kiểm tra quyền.”** Ngay cả mã đơn, số tiền hoặc trạng thái cũng có thể là dữ liệu không được phép xem.

**“Chỉ kiểm tra quyền ở lúc GET là đủ.”** PATCH, DELETE, batch, export và tác vụ nền có thể tạo hậu quả lớn hơn.

**“Cache và job nền không cần authorization vì chạy ở backend.”** Chúng vẫn sử dụng danh tính và dữ liệu có phạm vi; thiếu kiểm soát có thể làm lộ dữ liệu hoặc thực hiện hành động quá quyền.

**“Test chính sách đã xanh thì mọi endpoint đều an toàn.”** Cần kiểm tra ranh giới HTTP, xác thực, repository thật và mọi đường gọi liên quan.

**“Khi hệ thống phân quyền lỗi, cho phép tạm để không gián đoạn.”** Fail open có thể chuyển lỗi vận hành thành truy cập trái phép. Cần chính sách dự phòng an toàn được thiết kế trước.

## 16. Bài tập tình huống

### Tình huống A — API chi tiết đơn hàng

Một controller kiểm tra token, sau đó gọi `orderRepository.findById(orderId)` rồi trả entity đầy đủ.

Hãy chỉ ra: lỗi cấp đối tượng nào có thể xảy ra; dữ liệu nào có thể bị lộ thêm; nguồn nào cần cung cấp tenant; và **hai cấp test** nào nên bổ sung.

### Tình huống B — nhân viên hỗ trợ nhiều cửa hàng

Một nhân viên được cấp role `SUPPORT` để hỗ trợ cửa hàng A. Họ sửa tham số `tenantId=B` và đọc đơn cửa hàng B.

Hãy đề xuất policy gồm chủ thể, hành động, tài nguyên và ngữ cảnh. Quyết định nào cần thực thi ở API/service? Bộ lọc nào cần có ở truy vấn dữ liệu? Kiểm thử nào chứng minh role không vượt tenant?

### Tình huống C — cập nhật trạng thái tranh chấp

Người dùng được sửa địa chỉ của đơn DRAFT. Sau khi service kiểm tra, một request khác chuyển đơn thành SHIPPED; request đầu vẫn ghi địa chỉ.

Hãy giải thích rủi ro TOCTOU và đề xuất một thao tác database có điều kiện giúp bảo vệ quy tắc tại thời điểm ghi. Cần xử lý kết quả cập nhật 0 hàng ra sao?

### Tình huống D — tài khoản dịch vụ quyền quá rộng

Dịch vụ gửi email có tài khoản database được phép xóa bảng đơn hàng và đọc toàn bộ bảng người dùng.

Hãy lập danh sách quyền thực sự cần, quyền nên bỏ, cách kiểm soát secret và một số tín hiệu giám sát giúp phát hiện lạm dụng.

## 17. Câu hỏi tự kiểm tra

1. Xác thực và phân quyền khác nhau như thế nào? Vì sao kiểm tra token hợp lệ không thay thế kiểm tra owner?
2. Một khách hàng có quyền gọi `GET /orders/{id}`. Điều kiện nào còn thiếu để kết luận được đọc đơn `42`?
3. Phân biệt RBAC, ABAC và ReBAC bằng mỗi loại một ví dụ.
4. Tại sao role `SUPPORT` phải đi kèm phạm vi tenant hoặc nhiệm vụ được giao?
5. Trong ví dụ Java, vì sao `Actor` phải được xây từ ngữ cảnh đã xác minh thay vì body request?
6. Câu SQL `WHERE tenant_id = ?` có tự bảo đảm an toàn không nếu tham số được lấy từ phía client?
7. Điều gì có thể sai nếu service kiểm tra `status == DRAFT` rồi ghi dữ liệu sau khi request khác thay đổi trạng thái?
8. Khi nào trả 404 thay cho 403 có thể phù hợp? Tại sao quyết định này cần thống nhất theo hợp đồng?
9. Vì sao token có scope `orders:read` chưa đủ để đọc mọi đơn hàng?
10. Nêu ba đường truy cập ngoài controller thông thường có thể bỏ sót authorization.
11. Hãy lập ba test âm tính để phát hiện lỗi truy cập chéo tài khoản, tenant và cấp vai trò.
12. Một dịch vụ cần đọc tóm tắt đơn để gửi email. Nguyên tắc quyền tối thiểu ảnh hưởng thế nào tới tài khoản database của nó?
13. Điều gì cần làm khi cơ chế kiểm tra quyền không khả dụng để không biến lỗi hạ tầng thành đặc quyền mới?
14. Làm thế nào để kiểm chứng chính sách được áp dụng thật ở repository/API, chứ không chỉ được viết đúng trong một unit test?

## Ghi nhớ

**Kiểm soát truy cập an toàn phải quyết định “ai được làm gì với tài nguyên nào, trong hoàn cảnh nào” ngay tại những ranh giới thực thi hành động.** Xác thực là điều kiện đầu vào, không phải sự cho phép toàn cục. Hãy từ chối mặc định, cấp quyền tối thiểu, giới hạn tenant và bản ghi, kiểm soát trường dữ liệu và cả các thao tác ghi, job nền, cache, export. Viết chính sách rõ, kiểm tra cả đường bị từ chối và quan sát được quyết định quyền — đó là cách làm mã vừa đáng tin cậy vừa dễ hiểu và dễ thay đổi.
