# Phòng vệ nhiều lớp và giới hạn của một biện pháp bảo vệ đơn lẻ

Trong bảo mật ứng dụng, một cơ chế tốt vẫn có thể thất bại vì cấu hình sai, lỗi triển khai, hành vi người dùng, lỗ hổng chưa biết hoặc vì chính cơ chế đó chỉ xử lý **một loại rủi ro cụ thể**. HTTPS không quyết định ai được đọc đơn hàng; đăng nhập thành công không đảm bảo người dùng chỉ xem dữ liệu của mình; CSRF token không sửa lỗi SQL injection; còn một tường lửa ứng dụng web (WAF) không thay cho kiểm tra quyền ở backend.

**Phòng vệ nhiều lớp (defense in depth)** là cách thiết kế nhiều kiểm soát bổ trợ nhau tại các ranh giới khác nhau. Nếu một kiểm soát bị vượt qua, một kiểm soát khác có cơ hội **ngăn, giới hạn tác động, phát hiện hoặc giúp khôi phục**. Mục tiêu là tránh để một sai sót duy nhất đủ gây ra toàn bộ sự cố, đồng thời giữ phạm vi thiệt hại nhỏ nhất có thể.

Bài này giải thích cách xác định các lớp phòng vệ trong một ứng dụng Spring Boot/Spring Security (Servlet), giới hạn của từng biện pháp, cách ghép chúng vào một luồng nghiệp vụ và cách kiểm thử để tránh cảm giác an toàn giả.

## 1. Phòng vệ nhiều lớp là gì?

Hãy hình dung ứng dụng bán hàng có API `GET /api/orders/{id}`. Người dùng phải đăng nhập để gọi API. Nếu backend chỉ kiểm tra `authenticated()` rồi đọc đơn hàng theo ID, một tài khoản hợp lệ có thể thử ID của người khác và xem dữ liệu không thuộc quyền mình.

Một thiết kế nhiều lớp phù hợp có thể gồm:

1. Kết nối HTTPS để giảm nguy cơ lộ dữ liệu trên đường truyền.
2. Xác thực danh tính bằng cơ chế đáng tin cậy, quản lý phiên/token đúng cách.
3. Quy tắc ở HTTP endpoint yêu cầu quyền `order:read`.
4. Kiểm tra tại service rằng đơn hàng thuộc đúng tenant, chủ sở hữu hoặc phạm vi người gọi được ủy quyền.
5. Truy vấn cơ sở dữ liệu được giới hạn theo tenant/owner khi phù hợp.
6. Phản hồi chỉ chứa trường dữ liệu được phép hiển thị.
7. Logging, giám sát truy cập bất thường và kiểm tra tự động để phát hiện sai lệch.

Nếu chỉ có lớp 2, hệ thống vẫn dễ gặp **Broken Object Level Authorization (BOLA/IDOR)**. Nếu lớp 4 được viết sai, một truy vấn đã giới hạn theo tenant ở lớp 5 có thể giảm phạm vi ảnh hưởng; tuy nhiên nó chưa tự đảm bảo quyền sở hữu trong cùng tenant. Nếu thông tin đã lộ, audit và giám sát không tự hoàn tác việc rò rỉ, nhưng có thể hỗ trợ phát hiện và ứng phó.

**Điểm chính:** mỗi lớp cần có mục đích rõ ràng, áp dụng đúng ranh giới và được kiểm thử độc lập. Nhiều lớp trùng cùng một lỗi cấu hình hoặc tin cùng một dữ liệu giả mạo có thể tạo ra **nhiều bước kiểm tra nhưng chỉ một điểm thất bại thực sự**.

### 1.1. Ba vai trò khác nhau của kiểm soát

| Vai trò | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Ngăn chặn (preventive)** | Chặn hành động không hợp lệ trước khi ảnh hưởng tài sản | Authentication, authorization, CSRF, validation, parameterized queries, least privilege |
| **Phát hiện (detective)** | Nhận biết sự kiện bất thường, thất bại hoặc lạm dụng | Audit log, cảnh báo quyền bị từ chối hàng loạt, giám sát thay đổi cấu hình |
| **Giới hạn/khôi phục (limiting/recovery)** | Thu nhỏ thiệt hại và phục hồi sau sự cố | Phân tách tenant, giới hạn quyền của service account, backup có thử khôi phục, thu hồi token, incident response |

Không thể dùng kiểm soát phát hiện để thay thế hoàn toàn kiểm soát ngăn chặn. Một log rất chi tiết vẫn không ngăn được request đọc trái phép nếu backend đã trả dữ liệu cho kẻ tấn công.

### 1.2. Defense in depth không phải cộng thêm nhiều công cụ

Lắp WAF + API Gateway + Spring Security vẫn chưa đủ nếu cả ba chỉ kiểm tra “có token hay không” và cùng bỏ qua quyền trên từng bản ghi. Cần xác định cụ thể:

- **Tài sản**: dữ liệu người dùng, trạng thái đơn hàng, thông tin thanh toán, secret, tính sẵn sàng.
- **Chủ thể**: người dùng, dịch vụ, job, client chưa xác thực.
- **Tài nguyên và thao tác**: đơn hàng cụ thể, export, refund, cập nhật role, xóa dữ liệu.
- **Đường tấn công**: giả mạo danh tính, leo thang quyền, thay ID, XSS, CSRF, injection, lộ token, lỗi cấu hình.
- **Ranh giới tin cậy**: trình duyệt → backend; backend → database; backend → IdP; worker → queue; tenant A → tenant B.
- **Lớp kiểm soát**: mỗi lớp chặn nguy cơ nào, bằng bằng chứng nào, và có thể lỗi thế nào?

Một kiểm soát mạnh được đặt sai chỗ vẫn có thể không ngăn được tấn công. Ví dụ role check ở controller không bảo vệ một background job gọi trực tiếp service cùng chức năng nếu service không có ranh giới quyền tương ứng.

## 2. Ví dụ kiến trúc: nhiều lớp quanh một request

Ứng dụng Spring MVC dùng cookie session có thể có đường đi khái niệm:

```text
Trình duyệt / Mobile / Service client
    |
    |  TLS, cookie/token handling, kiểm soát phía client
    v
Reverse proxy / Load balancer / Gateway
    |  TLS termination, giới hạn request, rate limit, logging
    |  Không là nguồn quyền duy nhất trên từng business object
    v
Spring SecurityFilterChain
    |  CSRF khi phù hợp, Authentication, Authorization theo request
    |  Security headers và các cơ chế bảo vệ khác
    v
Controller + Request DTO
    |  Parse/validate đầu vào, giới hạn kích thước
    v
Service / Domain policy
    |  Đúng principal? đúng tenant? đúng owner?
    |  Có permission cho action? trạng thái nghiệp vụ cho phép?
    v
Repository / Database / External dependency
    |  Query tham số hóa, tenant scoping, least-privilege DB identity
    |  Transaction, constraints, idempotency nếu có side effect
    v
Response projection / Audit / Monitoring
    |  Chỉ trả dữ liệu được phép; ghi sự kiện có kiểm soát
```

Sơ đồ thể hiện **trách nhiệm**, không phải thứ tự chạy chính xác của mọi security filter. Một số kiểm tra có thể được thực hiện ở nhiều vị trí; một số request bị chặn trước khi tới controller. Từng bước phải được thiết kế theo ứng dụng thực tế.

### 2.1. Vì sao hai lớp cùng kiểm tra quyền vẫn có giá trị?

- **Request authorization** có thể chặn sớm những nhóm URL không thuộc quyền người gọi: `/api/admin/**` yêu cầu `ROLE_ADMIN`.
- **Method/service authorization** có thể quyết định quyền theo hành động và đúng đối tượng: `Order 100` thuộc ai, đang ở trạng thái nào, người gọi thuộc tenant nào.
- **Data access scoping** có thể tránh việc truy vấn trả cả dữ liệu tenant khác ngay từ đầu.

Các lớp phục vụ **các câu hỏi khác nhau**: được vào nhóm chức năng không, được thực hiện thao tác cụ thể không, và có đọc/ghi đúng tập dữ liệu không. Cần tránh lặp cơ học cùng một `hasRole("USER")` ở cả ba tầng mà quên object ownership.

## 3. Giới hạn của từng biện pháp bảo vệ thường gặp

| Biện pháp | Giúp giải quyết | Không tự giải quyết | Lớp bổ sung cần nghĩ tới |
| --- | --- | --- | --- |
| **HTTPS/TLS** | Bảo vệ dữ liệu khi truyền, xác thực server theo cấu hình TLS | BOLA/IDOR, user có quyền sai, XSS trong ứng dụng | Authorization đúng object, xử lý dữ liệu an toàn |
| **Đăng nhập / MFA** | Xác minh người dùng với mức bảo đảm phù hợp | User đã login đọc dữ liệu người khác, tài khoản có quyền quá lớn | Authorization, least privilege, quản lý session |
| **JWT signature validation** | Xác minh token không bị sửa và nguồn phát phù hợp khi kiểm tra đúng | Token sai audience, scope quá rộng, ownership, token bị đánh cắp còn hiệu lực | Kiểm tra issuer/audience/thời hạn/scope, object authorization, hạn chế vòng đời token |
| **`hasRole` / URL authorization** | Chặn những endpoint không đúng role | Truy cập object khác trong cùng endpoint, business state | Kiểm tra owner, tenant, action và trạng thái ở service |
| **CSRF protection** | Chống request giả mạo trong mô hình credential tự đính kèm như cookie | XSS, SQL injection, thiếu phân quyền, cố ý thao tác sai từ user hợp lệ | Authn/authz, output encoding, validation |
| **CORS** | Hạn chế truy cập xuyên origin của JavaScript trong trình duyệt | Xác thực, phân quyền, CSRF nói chung, client không phải browser | Authentication, authorization, CSRF theo threat model |
| **`@Valid` / Bean Validation** | Kiểm tra ràng buộc kiểu dữ liệu và các constraint đã khai báo | Injection nếu ghép SQL, kiểm tra ownership, quy tắc nghiệp vụ chưa mô tả | Prepared statements, domain validation, authorization |
| **Prepared statements** | Giảm nguy cơ SQL injection do trộn code SQL và dữ liệu | Leo thang quyền, rò rỉ từ response, sai truy vấn tenant | Least privilege DB account, scope query, response minimization |
| **Security headers / CSP** | Giảm một số rủi ro phía trình duyệt khi cấu hình đúng | Không đảm bảo mọi XSS biến mất, không sửa IDOR | Output encoding, context-aware escaping, review frontend |
| **Rate limit** | Giảm lạm dụng request và chi phí tài nguyên | Một request duy nhất gây rò rỉ dữ liệu, bypass logic nghiệp vụ | Quyền đối tượng, tài nguyên, kiểm soát chi phí/thực thi |
| **WAF** | Chặn một số mẫu tấn công đã biết trước khi tới app | Lỗi logic quyền, payload mới, lỗ hổng đi qua đường tin cậy | Cải thiện code, threat model, security tests |
| **Logging/monitoring** | Phát hiện, điều tra, cảnh báo | Không tự ngăn thao tác đã được cho phép sai | Chính sách từ chối, kiểm soát tại điểm thực thi, response |
| **Backup** | Phục hồi dữ liệu sau một số sự cố | Ngăn lộ dữ liệu, chống sửa quyền, đảm bảo recovery chưa được thử | Kiểm soát quyền, mã hóa, kiểm thử phục hồi, lưu trữ an toàn |

Không có hàng nào trong bảng là “vô dụng”. Vấn đề là **mỗi công cụ có phạm vi bảo vệ**. Khi thiết kế, cần hỏi rõ “mối đe dọa nào vẫn còn sau lớp này?” thay vì đánh dấu checkbox “đã có security”.

### 3.1. Đừng nhầm HTTPS với quyền truy cập

Giả sử kết nối giữa Alice và server đã mã hóa bằng HTTPS, nhưng endpoint `GET /api/invoices/123` chỉ yêu cầu login. Alice thay ID thành `124` và server trả hóa đơn của Bob. TLS bảo vệ **đường truyền của dữ liệu bị trả sai**; nó không khiến quyết định phân quyền trở nên đúng.

Do đó phải xác minh quyền trên hóa đơn, áp dụng truy vấn giới hạn owner/tenant, tránh trả trường nhạy cảm không cần thiết và kiểm thử cả ID thuộc người khác.

### 3.2. Đừng nhầm MFA với kiểm soát tác động sau đăng nhập

MFA tăng khả năng chống chiếm tài khoản bằng một yếu tố bị lộ. Nhưng user đã đăng nhập hợp lệ vẫn có thể khai thác API thiếu kiểm tra quyền; token/session bị chiếm đoạt cũng cần phòng vệ riêng. Cần quản lý quyền tối thiểu, phát hiện hành vi bất thường, chính sách session/token và kiểm tra object.

### 3.3. Đừng nhầm CORS với CSRF

CORS chủ yếu kiểm soát khả năng JavaScript trên website khác đọc/khai thác phản hồi xuyên origin theo cơ chế trình duyệt. Nó không phải hệ thống permission ở server. CSRF nhắm tới việc trình duyệt có thể gửi credential tự động, chẳng hạn cookie session, theo request không do người dùng chủ động tạo ra.

Một form HTML từ website ngoài có thể gửi request gây tác dụng phụ trong một số điều kiện ngay cả khi script của website đó không được đọc response. Vì vậy cấu hình CORS “chặn origin lạ” **không thay thế** CSRF token đối với ứng dụng dùng cookie và endpoint thay đổi trạng thái. Với API chỉ nhận bearer token do client chủ động thêm vào header và không dùng các credential tự đính kèm, đánh giá CSRF phải dựa trên mô hình xác thực thật, không dựa vào nhãn “REST API”.

### 3.4. Đừng nhầm password hashing với bảo vệ phiên

Password hashing phù hợp (ví dụ BCrypt/Argon2 qua cơ chế được chọn) giúp giảm tác động khi database mật khẩu bị lộ; nó không mã hóa phiên, không bảo vệ cookie bị chiếm, không kiểm tra quyền và không ngăn kẻ tấn công dùng mật khẩu hợp lệ. Cần kết hợp HTTPS, cookie flags hợp lý, session lifecycle, xác thực đa yếu tố khi cần và giám sát.

## 4. Tình huống trọng tâm: API đơn hàng

Xét các tài sản: dữ liệu đơn hàng, địa chỉ khách hàng, số tiền và trạng thái đơn. Các chủ thể: Alice, Bob, nhân viên chăm sóc khách hàng và một service chạy nền. Các hành động: đọc, hủy, hoàn tiền và export.

### 4.1. Thiết kế sơ sài

```java
// Anti-pattern: chỉ xác thực, chưa kiểm tra quyền trên object.
@GetMapping("/api/orders/{id}")
public OrderDto getOrder(@PathVariable long id) {
    return orderService.findById(id);
}
```

Dù Spring Security đã cấu hình `/api/orders/**` yêu cầu `authenticated()`, code vẫn có thể trả dữ liệu đơn hàng của người khác. Mã ID khó đoán không khắc phục bản chất lỗi phân quyền.

### 4.2. Thiết kế nhiều lớp có mục đích

| Lớp | Điều kiện cần kiểm tra | Nếu thiếu lớp đó |
| --- | --- | --- |
| Client/transport | HTTPS, không đưa token vào URL, quản lý cookie/session | Dữ liệu hoặc phiên dễ bị lộ theo đường khác |
| SecurityFilterChain | Có danh tính hợp lệ, có quyền `order:read` | Người chưa xác thực hoặc sai quyền vẫn có thể gọi API |
| Service policy | Đúng tenant, đúng owner hoặc được ủy quyền cụ thể | User hợp lệ có thể đổi ID sang đơn của người khác |
| Repository | Truy vấn theo tenant/đối tượng được phép, dùng tham số | Một lỗi lọc ở tầng trên có thể mở rộng phạm vi dữ liệu đọc |
| Response | DTO chỉ chứa trường phù hợp với vai trò | Có thể vô tình trả internalNote, payment token hoặc dữ liệu thừa |
| Audit/monitoring | Ghi quyết định bị từ chối và truy cập nhạy cảm | Khó phát hiện dò ID hoặc phân tích sự cố |

Các lớp kiểm tra nên dựa trên **dữ liệu đáng tin cậy**. Không dùng `ownerId`/`tenantId` do client đưa vào body làm bằng chứng quyền. Thông tin tenant trong principal phải được xác minh, còn dữ liệu chủ sở hữu đơn hàng cần lấy từ kho dữ liệu của server.

### 4.3. Hủy đơn là hành động khác với đọc đơn

Ngay cả Alice là chủ sở hữu, cô ấy có thể được đọc một đơn đã giao nhưng không còn quyền hủy. Vì vậy policy cần cả **action** và **trạng thái tài nguyên**:

```text
ALLOW cancel nếu:
  caller đã xác thực
  AND có permission order:cancel
  AND caller và order cùng tenant
  AND caller là owner hoặc được ủy quyền hủy
  AND order đang ở trạng thái được phép hủy
  AND mọi lớp bảo vệ request liên quan đã chấp nhận
```

Nếu bất kỳ điều kiện bắt buộc nào không đạt, không thực hiện hủy. Với một yêu cầu POST từ trình duyệt đang sử dụng session cookie, CSRF protection là lớp bổ sung cần xét. Nếu dữ liệu thay đổi đồng thời, kiểm tra trạng thái và ghi thay đổi phải được thực hiện nhất quán qua transaction/conditional update thích hợp.

## 5. Java 17 chạy độc lập: một lớp vượt qua chưa đồng nghĩa được phép

Ví dụ sau mô phỏng các **cổng kiểm soát** cho hành động đọc/hủy đơn hàng. Không cần Spring Boot hoặc thư viện ngoài. Mục đích là thấy người gọi phải vượt qua các kiểm tra khác nhau; chỉ có một permission hay một danh tính hợp lệ chưa đủ.

Tạo tệp **`DefenseInDepthDemo.java`**:

```java
import java.util.Objects;
import java.util.Set;

public class DefenseInDepthDemo {

    enum Action { READ, CANCEL }

    enum Decision {
        ALLOW,
        UNAUTHENTICATED,
        CSRF_REJECTED,
        MISSING_PERMISSION,
        WRONG_TENANT,
        WRONG_OWNER,
        INVALID_STATE,
        INVALID_INPUT
    }

    record Caller(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record Order(
        String id,
        String tenantId,
        String ownerId,
        boolean cancellable
    ) {}

    // Context này do server xác định, không tin cờ do client tự gửi.
    record RequestContext(boolean csrfRequired, boolean csrfValid) {}

    static Decision decide(
        Caller caller,
        Action action,
        Order order,
        RequestContext context
    ) {
        if (caller == null || order == null || action == null
                || context == null || order.id() == null
                || order.id().isBlank()) {
            return Decision.INVALID_INPUT;
        }

        // Lớp 1: xác thực.
        if (!caller.authenticated()) {
            return Decision.UNAUTHENTICATED;
        }

        // Lớp 2: tính hợp lệ của request trong mô hình yêu cầu CSRF.
        if (context.csrfRequired() && !context.csrfValid()) {
            return Decision.CSRF_REJECTED;
        }

        // Lớp 3: quyền cho hành động.
        String requiredPermission = switch (action) {
            case READ -> "order:read";
            case CANCEL -> "order:cancel";
        };

        if (caller.permissions() == null
                || !caller.permissions().contains(requiredPermission)) {
            return Decision.MISSING_PERMISSION;
        }

        // Lớp 4: cách ly tenant.
        if (!Objects.equals(caller.tenantId(), order.tenantId())
                || caller.tenantId() == null) {
            return Decision.WRONG_TENANT;
        }

        // Lớp 5: quyền trên object cụ thể.
        if (!Objects.equals(caller.userId(), order.ownerId())
                || caller.userId() == null) {
            return Decision.WRONG_OWNER;
        }

        // Lớp 6: bất biến nghiệp vụ.
        if (action == Action.CANCEL && !order.cancellable()) {
            return Decision.INVALID_STATE;
        }

        return Decision.ALLOW;
    }

    static void check(
        String label,
        Caller caller,
        Action action,
        Order order,
        RequestContext context
    ) {
        System.out.println(
            label + ": " + decide(caller, action, order, context)
        );
    }

    public static void main(String[] args) {
        Caller alice = new Caller(
            "alice", "shop-a", true,
            Set.of("order:read", "order:cancel")
        );
        Caller bob = new Caller(
            "bob", "shop-a", true,
            Set.of("order:read", "order:cancel")
        );
        Caller viewer = new Caller(
            "alice", "shop-a", true,
            Set.of("order:read")
        );
        Caller otherTenant = new Caller(
            "alice", "shop-b", true,
            Set.of("order:read", "order:cancel")
        );
        Caller guest = new Caller(
            "guest", "shop-a", false,
            Set.of("order:read")
        );

        Order draft = new Order("ORD-100", "shop-a", "alice", true);
        Order paid = new Order("ORD-100", "shop-a", "alice", false);

        RequestContext safeRead = new RequestContext(false, false);
        RequestContext validPost = new RequestContext(true, true);
        RequestContext invalidPost = new RequestContext(true, false);

        check("Alice reads", alice, Action.READ, draft, safeRead);
        check("Guest reads", guest, Action.READ, draft, safeRead);
        check("Alice cancel without CSRF", alice, Action.CANCEL,
            draft, invalidPost);
        check("Viewer cancels", viewer, Action.CANCEL, draft, validPost);
        check("Other tenant reads", otherTenant, Action.READ,
            draft, safeRead);
        check("Bob reads Alice order", bob, Action.READ,
            draft, safeRead);
        check("Alice cancels paid", alice, Action.CANCEL,
            paid, validPost);
        check("Alice cancels draft", alice, Action.CANCEL,
            draft, validPost);
    }
}
```

Với JDK 17 trở lên:

```bash
javac DefenseInDepthDemo.java
java DefenseInDepthDemo
```

**Stdout dự kiến chính xác:**

```text
Alice reads: ALLOW
Guest reads: UNAUTHENTICATED
Alice cancel without CSRF: CSRF_REJECTED
Viewer cancels: MISSING_PERMISSION
Other tenant reads: WRONG_TENANT
Bob reads Alice order: WRONG_OWNER
Alice cancels paid: INVALID_STATE
Alice cancels draft: ALLOW
```

Giải thích:

- Alice đọc đơn của mình: vượt qua xác thực, quyền đọc, tenant và owner; request đọc không yêu cầu kiểm tra CSRF trong mô hình demo.
- Guest có permission giả lập nhưng `authenticated=false` nên bị chặn ngay ở lớp danh tính.
- Alice có quyền hủy nhưng request POST mô phỏng bị thiếu CSRF token hợp lệ nên bị chặn ở lớp bảo vệ request.
- Viewer là Alice đã xác thực nhưng chỉ có `order:read`, không có quyền hủy.
- Caller ở tenant khác vẫn không được đọc dù có permission; Bob ở cùng tenant nhưng không sở hữu vẫn bị từ chối.
- Alice không được hủy đơn đã ở trạng thái không cho phép. Chỉ trường hợp mọi điều kiện đạt mới trả ALLOW.

**Giới hạn rõ ràng của mô phỏng:** Các record `Caller`, `Order` và `RequestContext` được dựng thủ công. Chúng **không tự chứng thực** password/token, không thực sự xác minh CSRF token, không truy vấn database, không có transaction và không thực hiện thao tác hủy. Trong ứng dụng thật, Spring Security xác thực danh tính và xử lý CSRF ở các bộ phận tương ứng; service dùng dữ liệu đáng tin cậy để kiểm tra quyền, rồi thay đổi trạng thái nhất quán trong database. Đừng coi cờ `csrfValid` do client gửi là bằng chứng hợp lệ.

Một chi tiết quan trọng: ví dụ đặt kiểm tra theo thứ tự dễ hiểu; hệ thống thật có thể đổi thứ tự để tránh rò rỉ thông tin hoặc giảm tải. Nhưng quyết định cuối cùng phải đáp ứng **tất cả điều kiện bắt buộc**, không được coi điều kiện đầu tiên đạt là đủ.

## 6. Phòng vệ nhiều lớp với Spring Security

Spring Security tập trung vào authentication, authorization, bảo vệ một số dạng khai thác và tích hợp với ứng dụng. Nó cung cấp nhiều công cụ ở ranh giới HTTP và method; việc kiểm tra **quyền trên dữ liệu thực**, tính đúng đắn nghiệp vụ và độ an toàn toàn hệ thống vẫn cần thiết kế cụ thể.

### 6.1. Lớp HTTP: `SecurityFilterChain`

Ví dụ cấu hình *minh họa* trên ứng dụng Spring Boot 3 / Spring Security 6 dùng Servlet:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("order:cancel")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Đây là đoạn mã cho dự án Spring, **không phải chương trình độc lập**: cần các import `@Configuration`, `@EnableMethodSecurity`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `HttpMethod`, `Customizer`, các dependency Spring Boot Web/Security và cách cấp identity phù hợp.

- `permitAll()` cho GET catalog nhưng vẫn xử lý request qua security filter chain; công khai truy cập không đồng nghĩa vô hiệu hóa các cơ chế bảo vệ khác.
- `hasAuthority("order:read")` và `hasAuthority("order:cancel")` chặn nhóm request không có authority yêu cầu; chính sách riêng phải quyết định đúng object.
- `anyRequest().denyAll()` đóng các request chưa có rule cho phép; khi thêm API mới phải cập nhật chủ động.
- `httpBasic()` chỉ là cơ chế authentication dễ trình bày. Production cần HTTPS và chính sách xác thực thích hợp.
- `csrf()` giữ CSRF protection, hữu ích với các tình huống credential tự đính kèm; các POST cần CSRF token hợp lệ theo cơ chế được cấu hình. Không tắt CSRF toàn cục chỉ để thử POST dễ hơn.

**Thứ tự matcher quan trọng:** trường hợp cụ thể phải đứng trước trường hợp bao quát. Ví dụ không đặt `anyRequest().permitAll()` trước matcher quản trị; rule khớp sớm có thể làm các rule sau không còn hiệu lực.

### 6.2. Lớp service: method security và chính sách nghiệp vụ

`@EnableMethodSecurity` kích hoạt các annotation method security như `@PreAuthorize`. Ví dụ một phần service:

```java
@PreAuthorize("hasAuthority('order:read')")
public OrderDto getOrder(long orderId, Authentication auth) {
    return orderPolicy.readOrderFor(auth, orderId);
}
```

Đây là **đoạn minh họa không độc lập**: `OrderDto` và `orderPolicy` là thành phần ứng dụng cần định nghĩa. `orderPolicy.readOrderFor` phải lấy tài nguyên thật và kiểm tra owner/tenant, không đơn giản gọi repository theo ID rồi trả mọi dữ liệu.

Nếu service còn được gọi từ scheduled job hoặc message consumer, cần một mô hình identity/permission cho đường gọi đó; không tự tạo `ROLE_ADMIN` để “cho job chạy được”. Method security hoạt động theo cơ chế Spring proxy/AOP và cần gọi qua ranh giới được áp dụng; **self-invocation** trong cùng đối tượng có thể không đi qua proxy. Chính sách nghiệp vụ quan trọng nên được bảo vệ ở những ranh giới nhất quán và có test chứng minh.

### 6.3. Lớp repository/database: lọc dữ liệu và giảm phạm vi quyền

Ví dụ ý tưởng truy vấn:

```sql
SELECT id, total_amount, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :authenticatedUserId;
```

Các biến là tham số truy vấn được bind bởi driver/ORM; không nối `orderId` hoặc `tenantId` vào chuỗi SQL tùy ý. Dữ liệu `tenantId` và `authenticatedUserId` phải đến từ ngữ cảnh đã xác minh, không lấy nguyên từ request body.

Tùy mô hình nghiệp vụ, quyền `order:read:any` có thể cần truy vấn khác nhưng vẫn phải bị giới hạn theo tenant. Tài khoản database của ứng dụng nên có các quyền cần thiết thay vì quyền quản trị toàn hệ thống. Có thể bổ sung row-level security khi nền tảng và kiến trúc phù hợp, nhưng phải kiểm tra chính sách thiết lập đúng cho mỗi connection/transaction; đây là lớp bổ sung, không thay thế authorization trong service.

### 6.4. Lớp response: nguyên tắc ít dữ liệu nhất

Ngay cả khi principal được phép xem đơn hàng, không có nghĩa được xem tất cả trường nội bộ: secret, thông tin hệ thống thanh toán, nội dung điều tra gian lận hoặc ghi chú nội bộ. DTO/projection theo quyền có thể bảo vệ tốt hơn việc serialize nguyên entity.

Tránh trả stack trace, SQL, thông tin môi trường hoặc dữ liệu nhạy cảm trong error message. Log cần đủ bằng chứng điều tra nhưng không ghi password, bearer token hoặc header `Authorization` đầy đủ.

### 6.5. Lớp khác Spring Security không tự bao phủ toàn bộ

Spring Security không tự đảm bảo:

- Query/ORM đúng tenant và tham số hóa;
- Chống lỗi business logic, BOLA/IDOR và race condition;
- Input validation đầy đủ, output encoding phù hợp ngữ cảnh;
- Rate limit, giới hạn kích thước payload, queue/backpressure;
- Secret management, chính sách hạ tầng và phiên bản dependency an toàn;
- Log/audit chính xác, giám sát và phản ứng sự cố;
- Backup/restore và quy trình khôi phục dữ liệu đã được kiểm thử.

Bảo mật ứng dụng cần kết hợp framework với thiết kế domain, hạ tầng, quy trình phát triển và vận hành.

## 7. Những lớp phòng vệ ở biên trình duyệt

### 7.1. CSRF, SameSite và session cookie

Với ứng dụng web dùng session cookie, trình duyệt có thể tự gửi cookie cho request đến server; kẻ tấn công có thể lợi dụng hành vi này để gây request làm thay đổi trạng thái. CSRF protection giúp server kiểm tra request có dấu hiệu hợp lệ theo cơ chế token.

Một chiến lược nhiều lớp có thể dùng: CSRF token, cookie `SameSite` phù hợp, `Secure`/`HttpOnly` cho cookie theo nhu cầu, giới hạn các method thay đổi trạng thái, kiểm tra Origin/Referer khi thích hợp và authorization ở backend. **SameSite chỉ là một lớp bổ sung**, không nên tự thay thế mọi kiểm tra CSRF trong ứng dụng yêu cầu bảo vệ bằng token.

`HttpOnly` giúp hạn chế JavaScript đọc cookie; nó không cấm trình duyệt tự đính kèm cookie vào request và không làm biến mất toàn bộ tác động của XSS. `Secure` giúp cookie chỉ được gửi qua kênh HTTPS theo quy tắc trình duyệt; nó không tự đảm bảo phân quyền đúng.

### 7.2. XSS và Content Security Policy

Input validation, output encoding theo ngữ cảnh (HTML, attribute, JavaScript, URL), template escaping và tránh các API nguy hiểm là những lớp giảm nguy cơ XSS. Content Security Policy (CSP) có thể giảm khả năng chạy script không mong muốn nếu được thiết kế đúng, nhưng CSP không phải giấy phép để đưa dữ liệu chưa escape vào trang.

Không nên cho rằng một `Content-Security-Policy` header tự giải quyết tất cả XSS hoặc thông tin đăng nhập bị đánh cắp. Khi ứng dụng có XSS, mã chạy trong origin hợp lệ có thể thực hiện hành động theo quyền người dùng trong nhiều bối cảnh; CSRF token cũng không phải biện pháp chữa XSS.

### 7.3. CORS và quyền của API

CORS có thể cho phép hay giới hạn origin nào được trình duyệt dùng để đọc phản hồi theo cơ chế browser. Nó không bảo vệ API khỏi curl, backend client hay request không có kiểm tra quyền. API vẫn cần xác minh token/session và quyết định đúng subject/action/resource. Không dùng `allowedOrigins("*")` làm “chính sách ai cũng có quyền”, và không coi CORS là authentication.

## 8. Tư duy giới hạn thiệt hại: giả sử một lớp đã bị vượt qua

Phòng vệ nhiều lớp còn có ý nghĩa sau khi tấn công đã vượt qua một điểm bảo vệ.

### 8.1. Token của một user bị lộ

- Lớp bị vượt qua: kẻ tấn công có thể trình diện bearer token hợp lệ.
- Lớp còn lại: scope/authority tối thiểu, token hết hạn hợp lý, chính sách thu hồi khi phù hợp, kiểm tra object/tenant, cảnh báo truy cập bất thường.
- Giới hạn: trong thời gian token hợp lệ, những quyền thực sự có trong token vẫn có thể bị lạm dụng; cần quy trình phát hiện, thu hồi và ứng phó. MFA lúc đăng nhập **không tự vô hiệu hóa** token đã bị đánh cắp.

### 8.2. Endpoint quên kiểm tra owner

- Lớp bị lỗi: `authenticated()` vẫn cho mọi tài khoản hợp lệ vào.
- Lớp giảm thiệt hại: service policy nếu được thực thi, truy vấn giới hạn dữ liệu theo tenant, DTO tối thiểu, audit, test BOLA.
- Giới hạn: tenant scoping không tự ngăn Bob đọc dữ liệu của Alice trong **cùng một tenant**; cần kiểm tra ownership hoặc chính sách cụ thể.

### 8.3. Một service account bị chiếm quyền

- Lớp bị lỗi: kẻ tấn công có được credential của service.
- Lớp còn lại: least privilege, cô lập mạng, quyền DB giới hạn, ràng buộc tenant, hạn mức truy cập và giám sát.
- Giới hạn: segmentation/rate limit làm giảm phạm vi, không tự ngăn hết các hành động mà chính service account đã được cấp quyền.

### 8.4. Một dependency hoặc kiểm soát bị lỗi

Nếu dịch vụ phân quyền không phản hồi, không được tự chuyển sang `permitAll()`. Với các nghiệp vụ nhạy cảm, nguyên tắc **fail closed** nghĩa là không thực hiện hành động khi không có quyết định cho phép đáng tin cậy. HTTP 503 có thể phản ánh dependency chưa sẵn sàng; việc từ chối vì thiếu quyền có thể dùng 403. Fail closed không có nghĩa mọi lỗi bắt buộc phải trả 403.

Lớp khác vẫn có thể hoạt động an toàn: catalog công khai có thể tiếp tục phục vụ khi một hệ thống phân quyền riêng của chức năng hoàn tiền bị gián đoạn, miễn là không tạo bypass cho nghiệp vụ nhạy cảm.

## 9. Thiết kế các lớp độc lập vừa đủ

Nhiều lớp không có nghĩa thêm cùng một rule ở mọi nơi. Để tăng hiệu quả thực sự:

1. **Đa dạng hóa kiểm soát theo rủi ro.** Ví dụ xác thực bằng token, quyền object trong service, query tenant scoped ở database và audit độc lập.
2. **Giảm phụ thuộc chung.** Nếu các lớp đều tin `tenantId` client gửi, sai sót cùng nguồn sẽ vượt qua tất cả. Phải có nguồn dữ liệu tin cậy.
3. **Không tạo lối tắt.** Endpoint “internal”, admin API, job, async worker và message consumer vẫn cần mô hình danh tính và quyền đúng.
4. **Deny by default.** Các route không có chính sách cấp quyền tường minh nên bị từ chối ở phạm vi cần bảo vệ.
5. **Kiểm soát phạm vi quyền.** Database account, service account, token scope và permission của người dùng chỉ nên có quyền cần thiết.
6. **Ưu tiên sửa nguyên nhân gốc.** WAF giảm rủi ro tạm thời, nhưng lỗi BOLA ở service vẫn phải được sửa; không biến lớp bổ sung thành lý do trì hoãn khắc phục.
7. **Đo khả năng phát hiện và phục hồi.** Định nghĩa ai nhận cảnh báo, thời gian phát hiện, cách thu hồi credential, kiểm tra backup/restore, và cơ chế audit.
8. **Giữ trải nghiệm sử dụng hợp lý.** Lớp quá nặng hoặc lỗi khiến người vận hành phải tạo bypass nguy hiểm là dấu hiệu cần thiết kế lại, tự động hóa và kiểm thử.

Một lớp chỉ có giá trị khi nó thực sự có thể từ chối/phát hiện/giảm thiệt hại cho một trường hợp đã được nêu rõ. Hãy kiểm tra tác động khi **giả định từng lớp lần lượt thất bại** thay vì chỉ chứng minh luồng bình thường thành công.

## 10. Kiểm thử theo tình huống và theo lớp

| Ca kiểm thử | Lớp cần chứng minh | Kết quả mong muốn |
| --- | --- | --- |
| Anonymous gọi `GET /api/orders/100` | Authentication + request authorization | Không trả đơn hàng |
| User có `order:read` nhưng đọc đơn của user khác | Object authorization | Bị từ chối/ẩn sự tồn tại theo chính sách |
| User cùng role nhưng ở tenant khác | Tenant boundary | Không đọc hoặc sửa dữ liệu tenant khác |
| User có quyền đọc nhưng gọi `POST /cancel` | Action permission | Bị từ chối |
| Owner có quyền hủy nhưng đơn đã thanh toán | Domain state | Không thay đổi đơn nếu chính sách cấm hủy |
| Browser POST session cookie thiếu CSRF token hợp lệ | Request exploit protection | Request bị chặn |
| JSON sai loại hoặc vượt giới hạn | Input validation | 4xx, không gọi nghiệp vụ |
| Payload cố chèn SQL qua tham số ID | Query parameterization | Không thay đổi ý nghĩa câu SQL |
| API đọc thành công | Response projection | Không lộ trường nhạy cảm ngoài scope |
| Policy service timeout | Fail closed | Không cho phép side effect, lỗi phù hợp |
| Lộ một credential ít quyền | Least privilege | Không có quyền vượt phạm vi được cấp |
| Security header cấu hình sai | Browser protections | Test phát hiện header thiếu/sai và xem lại rủi ro |
| Cấu hình route mới thiếu policy | Default deny | Không tự mở endpoint |

Chỉ kiểm tra mã 401/403 chưa đủ: với thao tác thay đổi trạng thái, cần chứng minh không có side effect xảy ra. Ví dụ request bị từ chối phải không ghi database, không gửi message và không gọi payment provider. Các kiểm thử quyền theo object nên có user cùng role nhưng khác owner, khác tenant và trường hợp tài nguyên không tồn tại.

### 10.1. Spring Security test ở mức request

Với `spring-security-test` và Spring MVC MockMvc, có thể kiểm tra rule ở URL:

```java
// Đoạn minh họa trong Spring Boot test, không phải Java độc lập.
mvc.perform(get("/api/orders/100")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:read"))))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders/100/cancel")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:cancel"))))
    .andExpect(status().isForbidden()); // Không có CSRF token hợp lệ
```

Ví dụ giả định controller/service/test fixture cho phép Alice đọc/hủy đơn, một `MockMvc` đã được cấu hình Spring Security và các static import phù hợp. Lệnh POST minh họa bảo vệ CSRF khi filter đang bật; nếu code dùng bearer token với cơ chế khác hoặc tùy biến CSRF, phải kiểm tra hành vi theo cấu hình thực tế. HTTP 200 của request đọc chỉ là **một điều kiện**, chưa chứng minh object authorization đúng với user khác. Thêm các test quyền sở hữu ở service hoặc integration test.

Một trường hợp POST được phép về CSRF có thể sử dụng `.with(csrf())`, nhưng vẫn cần user có quyền và trạng thái đơn hàng hợp lệ. Không nên “fix” test bằng cách tắt `csrf` toàn cục.

### 10.2. Kiểm thử độc lập từng lớp

Hãy làm ít nhất một “negative test” cho mỗi lớp trọng yếu. Có thể dùng request thực với token sai, service policy bị mock trả deny, database với dữ liệu hai tenant, response snapshot để phát hiện trường lộ, cấu hình thiếu security property hoặc dependency timeout. Khi một lớp bị giả lập lỗi, xác minh lớp khác vẫn từ chối hoặc giảm phạm vi theo thiết kế.

Đừng cố mô phỏng việc một lớp **bị bypass** trong production. Trong test, kiểm thử có kiểm soát bằng fixture/mocks và cô lập môi trường để tìm khoảng trống chính sách.

## 11. Lỗi tư duy thường gặp

1. **“Có Spring Security là đủ.”** Framework không tự quyết định quyền trên tất cả domain object, tiền xử lý dữ liệu, query, hạ tầng hay logic tài chính.
2. **“Đăng nhập thành công là được làm mọi việc.”** Authentication chỉ xác minh danh tính; authorization cần dựa vào subject, action, resource và ngữ cảnh.
3. **“HTTPS nên API đã an toàn.”** TLS bảo vệ truyền tải, không sửa lỗi policy hoặc input handling.
4. **“CORS đã chặn site ngoài, khỏi cần CSRF.”** CORS và CSRF nhắm tới những nguy cơ khác nhau.
5. **“Chỉ admin mới thấy nút nên API được bảo vệ.”** Ẩn UI không thay thế kiểm tra quyền phía server.
6. **“Thêm WAF để khỏi sửa lỗi backend.”** Lớp ở edge có thể hữu ích nhưng không phải nguồn chân lý cho quyền trên từng đối tượng.
7. **“ID ngẫu nhiên nên không ai truy cập được ID khác.”** Dù ID khó đoán, thiếu object authorization vẫn là lỗ hổng.
8. **“Có `@Valid` là chống được mọi tấn công từ input.”** Ràng buộc DTO không thay thế prepared statements, output encoding và quyền nghiệp vụ.
9. **“Đã ghi log nên sẽ ngăn được tấn công.”** Log phục vụ phát hiện và điều tra; tác động đã xảy ra không tự được rollback.
10. **“Nhiều lớp cùng lấy role từ request header nghĩa là an toàn hơn.”** Dữ liệu đầu vào không được xác minh có thể đánh lừa tất cả lớp đồng thời.
11. **“Một lớp bảo vệ bị lỗi thì cho qua tạm.”** Với kiểm soát cấp quyền hoặc điều kiện nhạy cảm, lỗi cần được xử lý an toàn; không suy diễn thành ALLOW.
12. **“Đã có test happy path thì đủ.”** Phải kiểm thử thiếu login, thiếu role, sai owner, sai tenant, sai trạng thái và side effect khi request bị từ chối.

## 12. Checklist áp dụng cho một chức năng mới

Trước khi đưa một chức năng vào production, trả lời đủ các nhóm câu hỏi:

**Tài sản và rủi ro**
- Dữ liệu, trạng thái hoặc năng lực nào có giá trị? Điều gì xảy ra nếu bị đọc, sửa hoặc gián đoạn?
- Những actor nào có thể gây rủi ro? Có đường gọi nào ngoài REST controller không?
- Điểm tin cậy nào bị vượt qua (browser, gateway, queue, service, database)?

**Cơ chế chặn**
- Danh tính được xác thực từ đâu? Token/session có đúng audience, scope, thời hạn và quy tắc quản lý?
- Request có rule theo endpoint/method không? Những route chưa khai báo có bị deny mặc định không?
- Service có kiểm tra đúng resource, owner, tenant và trạng thái nghiệp vụ không?
- Truy vấn dữ liệu có giới hạn phạm vi, tham số hóa và dùng tài khoản ít quyền không?
- Input được kiểm tra; response có lược bỏ dữ liệu nhạy cảm không?
- CSRF, cookie, CORS, browser headers và rate limit đã được lựa chọn đúng mô hình đe dọa chưa?

**Phát hiện, phục hồi và thử nghiệm**
- Những trường hợp từ chối/cảnh báo nào cần audit, metrics và alert? Log có tránh secret không?
- Khi token hoặc account bị lộ, có cơ chế thu hồi và giới hạn phạm vi tác động không?
- Khi dependency lỗi hoặc cấu hình bị thiếu, hệ thống có từ chối hành động nhạy cảm không?
- Đã test sai owner, sai tenant, sai quyền, sai trạng thái, sai CSRF và không có side effect chưa?
- Nếu giả sử một lớp thất bại, lớp khác còn có thể hạn chế thiệt hại nào?

## 13. Tự kiểm tra

**Câu 1.** API đã dùng HTTPS và yêu cầu user login nhưng Bob vẫn đọc được đơn hàng Alice bằng cách đổi ID. Đang thiếu lớp bảo vệ nào?

**Câu 2.** Một người dùng có `ROLE_USER` gọi `POST /api/orders/100/cancel` nhưng không có quyền `order:cancel`. Có thể xem role chung là đủ không?

**Câu 3.** Một ứng dụng session cookie có CORS rất chặt nhưng không dùng CSRF token cho POST nhạy cảm. Vì sao CORS không tự đảm bảo chống CSRF?

**Câu 4.** Đã dùng `@Valid` để đảm bảo `orderId` không rỗng. Có cần prepared statements và kiểm tra quyền sở hữu không?

**Câu 5.** Nếu service policy timeout, hệ thống có thể cho phép thao tác nhạy cảm để giữ availability không?

**Câu 6.** Nếu owner check ở service bị sai, bộ lọc tenant tại repository có còn giá trị không? Nó bảo vệ được những gì và không bảo vệ được những gì?

**Câu 7.** Khi một token hợp lệ bị đánh cắp, các lớp nào có thể giới hạn thiệt hại, và MFA có tự ngăn mọi việc dùng token đó không?

**Gợi ý trả lời**

1. Thiếu authorization theo đúng object (ownership/tenant); HTTPS và authentication không giải quyết điều đó.
2. Không. Cần permission cho đúng action và những điều kiện tài nguyên liên quan.
3. Browser có thể gửi credential tự động; CORS không phải kiểm tra ý định và quyền của request thay đổi trạng thái.
4. Có. Validation, query safety và authorization giải quyết các rủi ro khác nhau.
5. Không. Không đủ bằng chứng cho phép thì chặn thao tác, báo lỗi/giám sát phù hợp.
6. Có thể chặn truy cập **xuyên tenant**, nhưng không chặn đọc sai owner **trong cùng tenant**; vẫn cần sửa policy.
7. Scope/permission nhỏ, TTL, thu hồi token khi phù hợp, object authorization và giám sát làm giảm tác động. MFA lúc login không tự vô hiệu hóa một token bị chiếm.

### Nguồn tham khảo

- [OWASP Developer Guide – Security Principles / Defense in Depth](https://owasp.github.io/www-project-developer-guide/release/foundations/security_principles/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [Spring Security – Servlet Authorization: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
