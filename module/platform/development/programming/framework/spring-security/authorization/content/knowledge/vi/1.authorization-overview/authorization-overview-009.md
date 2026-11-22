# Trình tự học từ mô hình quyền đến cấu hình, kiểm thử và vận hành

## 1. Định hướng: học phân quyền theo thứ tự nào?

Học **phân quyền (authorization)** trong Spring Security thường dễ bị đảo ngược: bắt đầu bằng `hasRole("ADMIN")` hoặc thêm `@PreAuthorize`, sau đó mới hỏi hệ thống thực sự muốn bảo vệ điều gì. Cách này dễ tạo ra những kiểm tra đúng cú pháp nhưng sai nghiệp vụ, như “đã có quyền sửa” thì được sửa tài liệu của bất kỳ khách hàng nào.

Một lộ trình vững chắc bắt đầu từ **mô hình quyền**, chuyển mô hình thành **quyết định có thể thực thi**, gắn chúng vào **các điểm truy cập**, chứng minh bằng **kiểm thử**, rồi duy trì tính đúng đắn khi hệ thống **vận hành và thay đổi**.

```text
Nhu cầu nghiệp vụ và tài sản cần bảo vệ
               |
               v
[1] Mô hình quyền + ma trận cho phép/từ chối
               |
               v
[2] Chính sách quyết định quyền độc lập, rõ ràng
               |
               v
[3] Cấu hình và các điểm cưỡng chế trong Spring Security
               |
               v
[4] Kiểm thử quyền theo chức năng, đối tượng, trạng thái
               |
               v
[5] Vận hành: cấp/thu hồi quyền, quan sát, cập nhật chính sách
               |
               +-------- phản hồi khi có lỗi hoặc chính sách đổi --------+
                                                                        |
                                                                        v
                                                  Quay lại mô hình quyền
```

Lộ trình này là một **vòng lặp**, không phải chuỗi bước “cấu hình một lần là xong”. Ví dụ, khi thêm trạng thái “đã khóa” vào tài liệu, phải xem lại chính sách trước, sau đó điều chỉnh code, kiểm thử và quy trình vận hành.

### Đích đến của người học

Sau bài này, bạn cần có khả năng:

- Chuyển yêu cầu nghiệp vụ thành ma trận quyền rõ **ai – làm gì – trên đối tượng nào – trong điều kiện nào**.
- Phân biệt xác thực, quyền chức năng, quyền theo đối tượng và quyết định truy cập.
- Cấu hình chốt chặn HTTP và chốt chặn tại dịch vụ/dữ liệu trong Spring Security.
- Chứng minh bằng kiểm thử rằng một yêu cầu hợp lệ được cho phép và từng yêu cầu không hợp lệ thực sự bị chặn.
- Mô tả cách xử lý thay đổi quyền, ghi nhận quyết định truy cập, sự cố phụ thuộc và việc triển khai chính sách.

Trình tự ngắn gọn: **Hiểu chính sách → Diễn đạt chính sách → Thực thi → Kiểm chứng → Duy trì**.

## 2. Nền tảng cần nắm trước khi cấu hình

### 2.1. Xác thực khác phân quyền

- **Xác thực (authentication):** danh tính nào đang gửi yêu cầu? Một `Authentication` hợp lệ có thể mang principal và các `GrantedAuthority`.
- **Phân quyền (authorization):** principal đó có được làm hành động đã yêu cầu trên tài nguyên cụ thể với ngữ cảnh hiện tại hay không?
- **Thực thi quyền (enforcement):** thành phần nào thực sự chặn thao tác trước khi tài nguyên bị đọc, sửa, phê duyệt hay xóa?

Trong Spring Security, `SecurityFilterChain` có thể kiểm tra các quy tắc HTTP, còn method security có thể bảo vệ lời gọi phương thức. Nhưng **cả hai đều cần chính sách đúng** và việc kiểm tra quyền với đối tượng thực tế. Một phiên đăng nhập hợp lệ không có nghĩa người dùng được xử lý mọi đối tượng mà họ đoán được ID.

### 2.2. Những khái niệm phải ghép đúng

| Khái niệm | Nghĩa | Ví dụ |
| --- | --- | --- |
| Chủ thể (principal) | Người dùng hoặc dịch vụ có danh tính đáng tin | Người dùng 10 |
| Hành động (action) | Phép thực hiện trên tài nguyên | `request:approve` |
| Tài nguyên (resource) | Đối tượng đang được truy cập | Yêu cầu 102 |
| Ngữ cảnh (context) | Điều kiện ảnh hưởng quyết định | Tenant 1, trạng thái PENDING |
| Vai trò (role) | Nhóm nhiệm vụ của chủ thể | EDITOR, APPROVER |
| Quyền chức năng (permission/authority) | Khả năng cụ thể được cấp | `request:update` |
| Chính sách (policy) | Điều kiện cuối cùng để cho phép | Có quyền, cùng tenant, không phải người lập |
| Điểm cưỡng chế (enforcement point) | Nơi hệ thống bắt buộc áp dụng quyết định | Filter, service, truy vấn dữ liệu |

**RBAC** (kiểm soát dựa trên vai trò) thuận tiện để nhóm các quyền thông thường. **ABAC** (kiểm soát dựa trên thuộc tính) diễn đạt các điều kiện theo tenant, trạng thái hay phòng ban. Quyền trên đối tượng còn có thể dựa vào quan hệ chủ sở hữu/chia sẻ. Một hệ thống thực tế thường kết hợp các mô hình này; tên vai trò đơn lẻ không thể thay thế điều kiện theo tài nguyên.

Trước khi học API Spring Security, hãy trả lời được: “Một người có `ROLE_EDITOR` có được sửa hồ sơ của nhóm khác không?”. Nếu chưa biết **phạm vi tài nguyên** và **trạng thái nghiệp vụ**, câu trả lời chính xác là: **chưa đủ dữ kiện để cho phép**.

## 3. Bước 1 — Mô hình hóa quyền từ một bài toán thật

Dùng một tình huống xuyên suốt: hệ thống quản lý **yêu cầu mua sắm**. Mỗi yêu cầu có mã, tenant, người tạo và trạng thái `DRAFT`, `PENDING` hoặc `APPROVED`. Người tạo có thể sửa bản nháp; người có nhiệm vụ phê duyệt được duyệt yêu cầu đang chờ, nhưng không tự duyệt yêu cầu của chính mình.

### 3.1. Liệt kê tài nguyên, chủ thể và hành động

Tài nguyên: `PurchaseRequest`. Chủ thể: người lập yêu cầu, người phê duyệt, người chỉ được xem. Hành động có thể là `read`, `update`, `submit`, `approve`. Mỗi hành động cần một permission riêng và một quy tắc phạm vi cụ thể.

Ma trận ban đầu:

| Hành động | Quyền chức năng | Điều kiện trên đối tượng | Trạng thái hợp lệ |
| --- | --- | --- | --- |
| Xem | `request:read` | Cùng tenant và có phạm vi xem được giao | Theo quy định xem của nghiệp vụ |
| Sửa | `request:update` | Cùng tenant, chính người tạo | `DRAFT` |
| Gửi duyệt | `request:submit` | Cùng tenant, chính người tạo | `DRAFT` |
| Phê duyệt | `request:approve` | Cùng tenant, khác người tạo | `PENDING` |

Ma trận này là **giả định nghiệp vụ của ví dụ**. Nếu hệ thống cho phép người xem chỉ thấy hồ sơ của phòng ban mình, phải thêm điều kiện đó vào hàng “Xem”; nếu có ủy quyền phê duyệt, phải mô tả quan hệ ủy quyền và thời hạn. Không áp dụng ma trận này cho mọi hệ thống mà không xác nhận quy tắc nghiệp vụ.

### 3.2. Viết chính sách dưới dạng câu đầy đủ

Thay vì ghi “EDITOR được update”, hãy diễn đạt:

> Cho phép sửa yêu cầu khi chủ thể đã được xác thực, còn hoạt động, có `request:update`, cùng tenant với yêu cầu, là người tạo yêu cầu và yêu cầu đang ở trạng thái `DRAFT`.

Đối với phê duyệt:

> Cho phép phê duyệt khi chủ thể đã được xác thực, còn hoạt động, có `request:approve`, cùng tenant, **không phải người tạo** và yêu cầu đang `PENDING`.

Mọi trường hợp khác bị từ chối. Đặc biệt: **thiếu thông tin thì không tự cho phép**; **quyền chức năng chỉ là điều kiện cần**; **người vừa lập vừa có permission approve vẫn không được tự phê duyệt nếu chính sách cấm**.

### 3.3. Chỉ rõ nguồn dữ liệu đáng tin

| Dữ kiện | Nguồn nên lấy | Nguồn không thể tin trực tiếp |
| --- | --- | --- |
| Danh tính người dùng | Principal đã xác thực phía máy chủ | `userId` tự gửi trong JSON |
| Quyền hiện hành | Authority được xác minh hoặc dịch vụ chính sách đáng tin | Vai trò do client tự khai |
| Tenant đang hoạt động | Tenant đã kiểm tra quyền thành viên với principal | Header `X-Tenant-Id` chưa xác minh |
| Chủ sở hữu và trạng thái | Bản ghi từ kho dữ liệu tin cậy | Trường `ownerId`/`status` client gửi để hợp thức hóa |
| Quan hệ chia sẻ/ủy quyền | Dữ liệu nghiệp vụ có kiểm soát | Danh sách ID do người dùng tự nhập |

Đầu ra của bước 1 phải là **bảng chính sách được người phụ trách nghiệp vụ chấp nhận**, kèm các ví dụ cho phép/từ chối và cách xử lý ngoại lệ. Chỉ chuyển sang bước tiếp theo khi có thể giải thích vì sao mỗi trường hợp bị từ chối. Đây là chỗ áp dụng **quyền tối thiểu**, **mặc định từ chối** và **không tự phê duyệt** trước khi viết framework code.

## 4. Bước 2 — Biến mô hình thành hàm quyết định dễ kiểm tra

Bước này giúp tách hai câu hỏi: “Chính sách đúng không?” và “Spring Security đã gọi chính sách đúng chỗ chưa?”. Nên bắt đầu từ logic thuần Java, với đầu vào tường minh và kết quả cho phép/từ chối có thể kiểm thử riêng.

### 4.1. Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ chương trình dưới tên `AuthorizationLearningPathDemo.java`. Ví dụ cô đọng ba hành động READ, EDIT, APPROVE. Hành động SUBMIT đã có trong ma trận nhưng được để sang bài tập mở rộng, thay vì gộp giả định vào code một cách vô tình.

```java
import java.util.Set;

public class AuthorizationLearningPathDemo {
    enum Action { READ, EDIT, APPROVE }
    enum Status { DRAFT, PENDING, APPROVED }

    record Actor(
        long userId,
        long tenantId,
        Set<String> permissions,
        boolean active
    ) {}

    record PurchaseRequest(
        long id,
        long tenantId,
        long authorId,
        Status status
    ) {}

    static boolean allowed(
        Actor actor,
        Action action,
        PurchaseRequest request
    ) {
        // Thiếu danh tính/đối tượng, bị vô hiệu hoặc khác tenant:
        // mặc định từ chối.
        if (actor == null || action == null || request == null
                || !actor.active()
                || actor.tenantId() != request.tenantId()) {
            return false;
        }

        return switch (action) {
            case READ ->
                actor.permissions().contains("request:read");
            case EDIT ->
                actor.permissions().contains("request:update")
                    && actor.userId() == request.authorId()
                    && request.status() == Status.DRAFT;
            case APPROVE ->
                actor.permissions().contains("request:approve")
                    && actor.userId() != request.authorId()
                    && request.status() == Status.PENDING;
        };
    }

    static void show(String scenario, boolean result) {
        System.out.println(scenario + ": " + result);
    }

    public static void main(String[] args) {
        Actor author = new Actor(
            10, 1, Set.of("request:read", "request:update"), true
        );
        Actor approver = new Actor(
            20, 1, Set.of("request:read", "request:approve"), true
        );
        Actor outsider = new Actor(
            30, 2, Set.of("request:read", "request:approve"), true
        );
        Actor authorWithApprove = new Actor(
            10, 1, Set.of("request:approve"), true
        );

        PurchaseRequest draft =
            new PurchaseRequest(101, 1, 10, Status.DRAFT);
        PurchaseRequest pending =
            new PurchaseRequest(102, 1, 10, Status.PENDING);

        show("author edits own draft",
            allowed(author, Action.EDIT, draft));
        show("author cannot self-approve",
            allowed(authorWithApprove, Action.APPROVE, pending));
        show("approver approves pending",
            allowed(approver, Action.APPROVE, pending));
        show("approver cannot approve draft",
            allowed(approver, Action.APPROVE, draft));
        show("other tenant cannot read",
            allowed(outsider, Action.READ, pending));
        show("missing principal is denied",
            allowed(null, Action.READ, pending));
        show("approver cannot edit draft",
            allowed(approver, Action.EDIT, draft));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AuthorizationLearningPathDemo.java
java AuthorizationLearningPathDemo
```

Kết quả chuẩn:

```text
author edits own draft: true
author cannot self-approve: false
approver approves pending: true
approver cannot approve draft: false
other tenant cannot read: false
missing principal is denied: false
approver cannot edit draft: false
```

Diễn giải: trường hợp đầu được phép vì đủ quyền, chủ sở hữu, tenant và trạng thái. Người tạo không thể tự duyệt dù được cấp `request:approve`. Người phê duyệt hợp lệ chỉ duyệt yêu cầu đang chờ; họ không có quyền sửa bản nháp. Người ở tenant khác và yêu cầu thiếu principal đều bị từ chối.

Đây là **mô hình học tập**, không phải toàn bộ chính sách sản xuất. Kiểu `Actor` ở ứng dụng thật cần được khởi tạo từ danh tính đã xác minh; quyền và trạng thái có thể thay đổi; việc phê duyệt cần đảm bảo tính nhất quán với kho dữ liệu và các cập nhật đồng thời.

### 4.2. Tiêu chí hoàn thành bước 2

Đặt các câu hỏi sau cho từng rule: đầu vào nào quyết định kết quả? Có đường nào cho phép khi thiếu dữ liệu? Người khác tenant có bị chặn trước khi trả dữ liệu không? Kết quả có phụ thuộc dữ liệu client tự khai không? Hai người cùng role nhưng khác quan hệ với đối tượng có thể nhận kết quả khác nhau không?

Một chính sách đạt yêu cầu khi:

- Mọi nhánh cho phép được diễn đạt tường minh, mọi nhánh còn lại từ chối.
- Hàm quyết định đủ đơn giản để đọc và kiểm thử độc lập.
- Không rải logic “admin được làm mọi thứ” hay điều kiện tenant khác nhau khắp controller.
- Phân biệt được **quyết định chính sách** với **thao tác thực thi** và với **mã HTTP trả về**.

## 5. Bước 3 — Gắn chính sách vào Spring Security đúng ranh giới

Học cấu hình từ ngoài vào trong: **HTTP → phương thức nghiệp vụ → dữ liệu/đối tượng**. Mỗi lớp bảo vệ một loại sai sót khác nhau.

### 5.1. Chốt chặn HTTP (Servlet)

Đoạn dưới là **cấu hình minh họa trong ứng dụng Spring Boot Servlet sử dụng Spring Security 6**, cần ứng dụng có cơ chế xác thực riêng. Các chuỗi `request:read`, `request:update`... phải thực sự xuất hiện trong `GrantedAuthority` của principal sau khi xác thực.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health/public")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/requests/*")
                .hasAuthority("request:read")
            .requestMatchers(HttpMethod.PATCH, "/api/requests/*")
                .hasAuthority("request:update")
            .requestMatchers(HttpMethod.POST, "/api/requests/*/submit")
                .hasAuthority("request:submit")
            .requestMatchers(HttpMethod.POST, "/api/requests/*/approve")
                .hasAuthority("request:approve")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Ý nghĩa các quy tắc:

- Chỉ endpoint trạng thái công khai đã xác nhận mới dùng `permitAll()`; các đường không liệt kê sẽ bị `denyAll()`.
- Match theo cả đường dẫn lẫn HTTP method, để quyền “đọc” không vô tình thành quyền “sửa”.
- `hasAuthority("request:approve")` chỉ kiểm tra **quyền chức năng**. Nó chưa biết yêu cầu đó thuộc tenant nào, ai tạo và có đang `PENDING` hay không.
- Thứ tự matcher và mọi `SecurityFilterChain` khác phải được kiểm tra đồng thời. Quy tắc quá rộng đứng trước quy tắc hẹp có thể làm sai chính sách.
- Cấu hình mẫu không cố ý thay đổi CSRF, CORS, session hay JWT. Hãy thiết kế những phần này theo kiểu client/xác thực thực tế; không tắt CSRF một cách máy móc khi ứng dụng dùng cookie hoặc phiên.

Nếu sử dụng OAuth2 Resource Server, phải kiểm tra chính xác cách ánh xạ scope/claim sang `GrantedAuthority`. Trong cấu hình thông thường, scope có thể trở thành authority mang tiền tố `SCOPE_`; chỉ dùng `hasAuthority("request:read")` khi hệ thống thực sự cấp authority mang đúng chuỗi ấy.

Tại ứng dụng WebFlux, cơ chế tương ứng nằm ở `SecurityWebFilterChain` và `authorizeExchange`. Ý tưởng phân quyền giữ nguyên, nhưng không sao chép nguyên cú pháp Servlet sang reactive.

### 5.2. Chốt chặn ở phương thức nghiệp vụ

Giả sử API đã được chặn bởi permission `request:approve`, lớp dịch vụ vẫn phải đánh giá tenant, người tạo và trạng thái. Có thể đặt `@PreAuthorize("hasAuthority('request:approve')")` tại điểm vào công khai và gọi một thành phần chính sách.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {
    private final PurchaseRequestRepository requests;
    private final CurrentActor currentActor;
    private final ApprovalPolicy policy;

    public ApprovalService(
            PurchaseRequestRepository requests,
            CurrentActor currentActor,
            ApprovalPolicy policy) {
        this.requests = requests;
        this.currentActor = currentActor;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("hasAuthority('request:approve')")
    public void approve(long requestId) {
        var actor = currentActor.requireAuthenticated();
        var request = requests.findById(requestId)
            .orElseThrow(() -> new RequestNotFoundException(requestId));

        if (!policy.mayApprove(actor, request)) {
            throw new AccessDeniedException("Not allowed");
        }

        request.markApproved(actor.userId());
    }
}
```

Đây là **mã minh họa tích hợp**, cần các kiểu miền `PurchaseRequestRepository`, `CurrentActor`, `ApprovalPolicy`, `RequestNotFoundException` và mô hình `PurchaseRequest` do ứng dụng định nghĩa. `CurrentActor` phải dùng principal đã được hệ thống xác thực; `ApprovalPolicy` hiện thực đúng ma trận ở bước 1. `markApproved` chỉ được thực thi sau khi quyền được xác nhận.

Lưu ý quan trọng:

1. `@EnableMethodSecurity` bật hỗ trợ method security theo kiểu thông thường; các annotation như `@PreAuthorize` thường được thực thi qua Spring AOP proxy. **Self-invocation** (một phương thức gọi phương thức khác trên chính cùng instance) có thể bỏ qua kiểm tra trên proxy.
2. `@Transactional` tự nó **không đảm bảo** không xảy ra race giữa kiểm tra trạng thái và ghi. Tùy mô hình dữ liệu, cần optimistic locking (chẳng hạn cột version), khóa có chủ đích hoặc câu lệnh cập nhật có điều kiện `WHERE status = 'PENDING' ...` và kiểm tra số dòng đã đổi.
3. Với tìm kiếm, phân trang và xuất dữ liệu, cần lọc **ngay từ truy vấn** theo tenant và phạm vi người dùng. Lọc sau khi lấy toàn bộ dữ liệu hoặc chỉ ẩn trên giao diện có thể làm lộ nội dung.
4. Phương thức có thể được gọi từ controller khác, job hoặc thành phần nội bộ. Phải biết đường đi nào bảo đảm chính sách được thực thi, tránh dựa độc nhất vào đường dẫn HTTP.

### 5.3. Vai trò của từng lớp

| Lớp | Giải quyết điều gì? | Không giải quyết một mình |
| --- | --- | --- |
| `SecurityFilterChain` | Chặn request không phù hợp theo URL/method/authority | Chủ sở hữu, tenant, trạng thái của bản ghi |
| Method security | Bảo vệ thao tác nghiệp vụ khi nhiều điểm gọi chung | Cập nhật đồng thời và lọc dữ liệu hàng loạt |
| Chính sách đối tượng | Quyền trên bản ghi cụ thể và trạng thái | Đường đi bị bỏ quên nếu không được gọi |
| Repository/transaction | Chỉ đọc/ghi dữ liệu nằm trong phạm vi hợp lệ; giữ nhất quán | Danh tính và permission không được kiểm chứng |

Đầu ra của bước 3: với mọi hành động trong ma trận, chỉ ra rõ **điểm nào kiểm tra permission**, **điểm nào kiểm tra quyền trên đối tượng**, và **điểm nào giữ dữ liệu nhất quán**. Nếu không vẽ được đường đi đó, cấu hình chưa đủ.

## 6. Bước 4 — Kiểm thử để chứng minh tính đúng đắn

Kiểm thử phân quyền khác với kiểm thử nghiệp vụ thành công: ngoài xác nhận thao tác hợp lệ chạy được, phải chủ động thử những trường hợp **đáng lẽ bị chặn**. Một bài test trả 403 do thiếu CSRF không chứng minh được policy đã chặn đúng.

### 6.1. Biến ma trận quyền thành ma trận kiểm thử

| Trường hợp | Principal/quyền | Đối tượng | Kỳ vọng |
| --- | --- | --- | --- |
| Tác giả sửa bản nháp | Có `request:update` | Cùng tenant, chính tác giả, DRAFT | Cho phép |
| Người lạ sửa bản nháp | Có `request:update` | Cùng tenant, không phải tác giả | Từ chối |
| Người phê duyệt duyệt yêu cầu | Có `request:approve` | Cùng tenant, khác tác giả, PENDING | Cho phép |
| Tác giả tự duyệt | Có `request:approve` | Cùng tenant, chính tác giả, PENDING | Từ chối |
| Phê duyệt nháp | Có `request:approve` | DRAFT | Từ chối |
| Đọc hồ sơ khác tenant | Có `request:read` | Tenant khác | Từ chối |
| Không có quyền chức năng | Đã đăng nhập, thiếu authority | Dữ liệu hợp lệ | Từ chối |
| Chưa đăng nhập | Không có principal hợp lệ | Bất kỳ tài nguyên bảo vệ | Không thực hiện thao tác |
| Method hoặc URL chưa khai báo | Có tài khoản hợp lệ | Đường dẫn chưa định nghĩa trong chính sách | Từ chối theo chính sách mặc định |
| Quyền vừa bị thu hồi | Principal không còn quyền hiệu lực | Dữ liệu từng được xem | Không tiếp tục cấp quyền theo cơ chế thu hồi của hệ thống |

Cần kiểm thử các đường đi khác nhau: endpoint đọc chi tiết, danh sách, tìm kiếm, export, upload, tác vụ bất đồng bộ và các điểm gọi dịch vụ nội bộ nếu chúng có thể chạm đến cùng tài nguyên.

### 6.2. Bốn tầng kiểm thử nên học theo thứ tự

**Tầng 1 — Chính sách thuần Java.** Kiểm tra từng quy tắc bằng dữ liệu giả xác định, bao gồm giá trị null, tenant khác, quyền thiếu và trạng thái khác. Đoạn chạy độc lập ở mục 4 là bước quan sát cơ bản; trong dự án, chuyển chúng thành JUnit assertions.

**Tầng 2 — HTTP security.** Với Spring MVC/MockMvc và `spring-security-test`, kiểm tra matcher, trạng thái chưa xác thực, thiếu authority và các đường dẫn không được khai báo. Đối với POST/PATCH/DELETE khi CSRF bật, cần token CSRF hợp lệ để thử **quyết định phân quyền** thực sự, nếu không kết quả 403 có thể chỉ do CSRF. Một mẫu minh họa đặt **bên trong lớp test đã cấu hình MockMvc, principal và dữ liệu**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Chỉ minh họa phần gọi trong một @Test có biến mockMvc.
mockMvc.perform(post("/api/requests/102/approve")
        .with(user("approver")
            .authorities(new SimpleGrantedAuthority("request:approve")))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

Trong ví dụ này, `SimpleGrantedAuthority` là `org.springframework.security.core.authority.SimpleGrantedAuthority`; kết quả 2xx chỉ đúng khi fixture thật có yêu cầu 102 ở `PENDING`, người dùng thuộc đúng tenant, không phải tác giả, và controller/service triển khai thao tác thành công. Đây **không phải chương trình chạy độc lập** và không thể thay thế test với dữ liệu thực tế.

**Tầng 3 — Dịch vụ và dữ liệu.** Gọi lớp dịch vụ từ các đường hợp lệ để chứng minh kiểm tra đối tượng vẫn áp dụng; xác nhận truy vấn không lộ bản ghi khác tenant; kiểm tra transaction không sửa trạng thái khi bị từ chối. Cần kiểm tra cạnh tranh cập nhật: hai người duyệt cùng một yêu cầu, quyền/tenant thay đổi giữa các lần thao tác, hoặc đối tượng chuyển trạng thái ngay trước lệnh ghi.

**Tầng 4 — Luồng nghiệp vụ đầu cuối.** Chạy hành trình tạo → sửa → gửi duyệt → phê duyệt → xem kết quả với các danh tính thích hợp. Sau mỗi hành động, kiểm tra cả **HTTP result**, **dữ liệu thực tế** và **sự kiện kiểm toán** nếu có.

### 6.3. Đọc kết quả test đúng cách

- **401** thường biểu thị yêu cầu chưa được xác thực với API; một số ứng dụng tương tác có thể chuyển hướng đăng nhập.
- **403** thường biểu thị một yêu cầu đã được nhận diện nhưng bị từ chối quyền; CSRF cũng có thể dẫn đến 403.
- **404** đôi khi được chủ động dùng cho tài nguyên ngoài phạm vi để tránh tiết lộ sự tồn tại.
- **5xx** có thể phản ánh lỗi dịch vụ chính sách, nhưng thao tác nhạy cảm **không được tự cho phép khi không xác minh được quyền**.

Không cố định duy nhất một mã HTTP cho mọi tình huống. Quyết định kiểm thử quan trọng là **không có dữ liệu nhạy cảm bị trả về và không có tác động nghiệp vụ trái phép**. Khi test thất bại, xác định tầng gây lỗi (matcher, ánh xạ authority, chính sách đối tượng, kho dữ liệu, CSRF) trước khi sửa.

Đầu ra của bước 4: ma trận kiểm thử có cả ca cho phép và từ chối, test chạy ổn định, chứng cứ về trạng thái dữ liệu sau yêu cầu và khả năng phát hiện một đường vòng mới.

## 7. Bước 5 — Vận hành chính sách và quyền theo thời gian

Một chính sách đúng hôm nay có thể sai sau khi thay đổi nhân sự, cấu trúc tenant, trạng thái tài nguyên hoặc luồng duyệt. Phân quyền cần quy trình vận hành như mọi thành phần bảo mật khác.

### 7.1. Cấp, thay đổi và thu hồi quyền

**Cấp quyền:** xác định người phê duyệt yêu cầu cấp, công việc cần làm, danh sách permission tối thiểu, phạm vi tenant/tài nguyên và thời hạn. Tài khoản dịch vụ chỉ được quyền cho công việc của nó, không mặc nhiên dùng quyền quản trị.

**Đổi vị trí hoặc trách nhiệm:** thu hồi quyền cũ trước hoặc cùng lúc chuyển quyền; không tích lũy role chỉ vì lịch sử công việc. Có đợt rà soát quyền định kỳ và xử lý quyền đặc biệt hết hạn.

**Thu hồi quyền:** phải hiểu cơ chế truyền hiệu lực. Nếu permission đã được đưa vào JWT tự chứa với thời hạn dài, việc cập nhật bảng quyền trên server **không tự động** thay đổi các token đã phát hành. Cân nhắc token ngắn hạn, tra cứu quyền động, danh sách thu hồi, phiên có version hoặc cơ chế hiệu lực phù hợp với mức rủi ro. Lựa chọn nào cũng cần kiểm thử độ trễ thu hồi thực tế.

**Quyền khẩn cấp:** nếu có cơ chế nâng quyền tạm thời, cần người có thẩm quyền, lý do, thời hạn ngắn và nhật ký riêng; không biến tài khoản khẩn cấp thành đường tắt lâu dài.

### 7.2. Quan sát được quyết định cho phép và từ chối

Nhật ký kiểm toán nên ghi các thông tin đủ để điều tra mà không lộ bí mật:

| Trường | Mục đích |
| --- | --- |
| Thời gian, request/correlation ID | Gắn các sự kiện thuộc cùng yêu cầu |
| Principal hoặc định danh dịch vụ | Ai yêu cầu |
| Hành động và định danh tài nguyên phù hợp | Đã cố làm gì |
| Tenant/phạm vi đã được kiểm chứng | Đã yêu cầu trong ngữ cảnh nào |
| Kết quả và mã lý do có kiểm soát | Cho phép, từ chối, phụ thuộc lỗi |
| Phiên bản chính sách | Quy tắc nào đang có hiệu lực |

Không ghi token thô, cookie, mật khẩu hay toàn bộ nội dung tài nguyên nhạy cảm vào log chỉ để “dễ debug”. Bảo vệ và giới hạn thời gian lưu log theo yêu cầu hệ thống.

Theo dõi cả **tăng đột biến số lần bị từ chối**, **endpoint có bất thường sau triển khai**, **thời gian đánh giá chính sách** và **tỷ lệ lỗi từ dịch vụ phụ thuộc**. Nhiều lần 403 có thể chỉ là thao tác bình thường bị chặn; cảnh báo cần ngữ cảnh để giảm báo động sai.

### 7.3. Độ tin cậy, hiệu năng và nhất quán

- **Hỏng dịch vụ chính sách:** với hành động nhạy cảm, nếu không đánh giá được thì không cho qua. Có thể trả lỗi kỹ thuật thích hợp thay vì giả vờ rằng đây luôn là lỗi thiếu quyền.
- **Cache quyền:** phải xem xét tenant, principal, action, tài nguyên, phiên bản chính sách, trạng thái và thời hạn. Cache theo riêng user ID dễ trả nhầm quyết định cho tài nguyên/tenant khác. Cần cơ chế vô hiệu hóa hoặc hết hạn khi quyền bị thu hồi.
- **Đồng thời:** kiểm tra trước rồi ghi sau có thể dùng dữ liệu cũ; cần biện pháp giao dịch/khóa/version hoặc cập nhật có điều kiện phù hợp cho hành động nhạy cảm.
- **Kênh khác HTTP:** job, message consumer, RPC nội bộ, batch/export không tự động thừa hưởng filter của HTTP. Chúng cũng cần định danh và chính sách tại điểm truy cập.
- **Hiệu suất:** tránh gọi dịch vụ quyền N lần không cần thiết trong danh sách lớn; tối ưu truy vấn theo phạm vi, nhưng không lấy lợi ích hiệu suất làm lý do bỏ kiểm tra đối tượng.

### 7.4. Đưa chính sách mới vào sản xuất

Một thay đổi permission nên đi theo tuyến:

```text
Thay đổi yêu cầu nghiệp vụ
  -> sửa ma trận chính sách, có người phụ trách xác nhận
  -> cập nhật policy + matcher + service + dữ liệu
  -> bổ sung test cho quyền mới và các đường từ chối cũ
  -> chạy kiểm thử tích hợp và rà soát ảnh hưởng
  -> triển khai có theo dõi lỗi, 401/403, nhật ký kiểm toán
  -> xác nhận trường hợp hợp lệ vẫn hoạt động, ca cấm vẫn bị chặn
```

Cần có kế hoạch khôi phục nếu chính sách mới chặn nhầm người hợp lệ hoặc mở rộng quyền ngoài ý muốn. Khi phát hiện điểm truy cập chưa được bảo vệ, xử lý ở cả **mô hình chính sách**, **đường thực thi** và **kiểm thử hồi quy**, không chỉ thêm một `if` vá lỗi trong controller.

Đầu ra bước 5 là một **quy trình vận hành có chủ sở hữu rõ ràng**: cách phê duyệt thay đổi quyền, cách thu hồi, dữ liệu dùng để truy vết, chỉ số nhận biết lỗi và cách xác nhận khi triển khai.

## 8. Những lối học tắt thường dẫn đến lỗi

| Cách làm thiếu bước | Hậu quả | Điều cần học bổ sung |
| --- | --- | --- |
| Viết `hasRole("ADMIN")` trước khi có ma trận | Một role bao trùm nhiều nhiệm vụ không liên quan | Mô hình tài nguyên, hành động, quyền tối thiểu |
| Bật `authenticated()` cho mọi endpoint | Người đăng nhập gọi được chức năng không thuộc nhiệm vụ | Quyền theo chức năng, mặc định từ chối |
| Chỉ kiểm tra URL, không kiểm tra record | Đổi ID để đọc/sửa tài nguyên người khác (IDOR/BOLA) | Quyền theo đối tượng, tenant, owner, trạng thái |
| Chỉ viết annotation mà không hiểu proxy | Self-invocation có thể đi vòng method security | Ranh giới AOP và dịch vụ thật sự được gọi |
| Test một người quản trị gọi thành công | Bỏ sót ca thiếu quyền, sai tenant, tự duyệt | Ma trận test cả cho phép/từ chối |
| Test POST trả 403 nhưng quên CSRF | Hiểu nhầm lỗi CSRF thành policy chính xác | Phân biệt bộ lọc HTTP và kiểm tra quyền |
| Phê duyệt dựa trên trạng thái đã đọc trước đó | Hai yêu cầu đồng thời có thể làm sai trạng thái | Giao dịch, version, cập nhật có điều kiện |
| Thu hồi role nhưng tin JWT cũ tự hết quyền ngay | Quyền vẫn có hiệu lực cho đến khi token/phiên được xử lý | Cơ chế thu hồi và thời gian hiệu lực |
| Cache cho phép theo user mà bỏ tài nguyên/tenant | Quyết định cho đối tượng A bị áp dụng sang B | Khóa cache đúng ngữ cảnh, invalidation |
| Log thiếu danh tính/quy tắc hoặc ghi token thô | Khó điều tra hoặc rò dữ liệu nhạy cảm | Nhật ký kiểm toán an toàn |

Đọc thuộc các API không giải quyết được các lỗi trên. Mục tiêu học là hiểu **nơi sinh ra quyền**, **nơi đánh giá quyền**, **nơi chặn hành động** và **cách chứng minh hệ thống đã chặn đúng**.

## 9. Lộ trình thực hành từ dễ đến khó

### Bài thực hành 1 — Ma trận (không dùng Spring)

Tạo bảng cho một chức năng gồm hai tenant, ba permission và ba trạng thái. Viết ít nhất tám tình huống, bao gồm người cùng role nhưng khác tenant, người có quyền nhưng sai trạng thái, và người không được tự phê duyệt. **Đạt** khi không có ca nào cần đoán kết quả.

### Bài thực hành 2 — Bộ quyết định thuần Java

Mở rộng `AuthorizationLearningPathDemo`: thêm `Action.SUBMIT` và quy tắc “tác giả có `request:submit`, cùng tenant, còn hoạt động, trạng thái DRAFT”. Thêm các ca hợp lệ và bị chặn. **Đạt** khi mã biên dịch, output đúng theo ma trận và không có nhánh tự cho phép khi thiếu dữ liệu.

### Bài thực hành 3 — Spring Security HTTP

Ánh xạ từng hành động sang HTTP method, endpoint và authority. Kết thúc bằng `anyRequest().denyAll()`. Kiểm tra chỗ nào public, chỗ nào yêu cầu danh tính, chỗ nào yêu cầu permission riêng. **Đạt** khi thay đổi HTTP method hoặc URL chưa khai báo không vô tình mở thêm quyền.

### Bài thực hành 4 — Chốt chặn theo tài nguyên

Đưa logic tenant/tác giả/trạng thái vào một thành phần chính sách dùng ở service. Bảo đảm các đường đọc chi tiết, đọc danh sách và thao tác ghi không bỏ qua nó. **Đạt** khi hai người cùng permission nhưng khác quyền trên tài nguyên nhận kết quả khác nhau như ma trận.

### Bài thực hành 5 — Kiểm thử và tình huống xấu

Viết unit test policy, test HTTP với danh tính/CSRF đúng, test dịch vụ và test cơ sở dữ liệu sau thao tác bị từ chối. Thêm ca đổi tenant, đoán ID, quyền bị thu hồi và phê duyệt đồng thời. **Đạt** khi kiểm thử phát hiện được ít nhất một phiên bản code cố tình bỏ điều kiện tenant hoặc trạng thái.

### Bài thực hành 6 — Vận hành

Mô tả cách cấp và thu hồi `request:approve`, thông tin kiểm toán cần ghi, chính sách khi dịch vụ quyền lỗi và cách giám sát một lần triển khai đổi rule. **Đạt** khi có thể giải thích được ai chịu trách nhiệm, quyền có hiệu lực lúc nào, thu hồi lúc nào và phải tra cứu bằng chứng ở đâu.

## 10. Bản đồ hoàn thành: từng giai đoạn để lại điều gì?

| Giai đoạn | Hiện vật cần có | Câu hỏi kiểm tra trước khi sang giai đoạn kế |
| --- | --- | --- |
| 1. Mô hình | Ma trận quyền và tình huống cho phép/từ chối | Có mô tả đủ actor, action, resource, context không? |
| 2. Chính sách | Hàm quyết định và test độc lập | Có nhánh cho phép nào do thiếu điều kiện không? |
| 3. Cấu hình | Điểm kiểm tra HTTP, method, dữ liệu và bản đồ đường đi | Có đường nào vào chức năng mà né được kiểm tra không? |
| 4. Kiểm thử | Ma trận test, dữ liệu fixture và bằng chứng kết quả | Trường hợp bị từ chối có chắc chắn không sinh tác động phụ không? |
| 5. Vận hành | Quy trình cấp/thu hồi, audit, giám sát, xử lý thay đổi | Khi quyền đổi hoặc phụ thuộc lỗi, hệ thống xử lý an toàn thế nào? |

### Tự kiểm tra cuối bài

1. Vì sao không bắt đầu chỉ bằng `hasRole("ADMIN")`? Vì chưa mô tả được hành động, đối tượng, phạm vi và trạng thái nghiệp vụ; role không tự thay ma trận quyền.
2. Có `request:approve` là đủ phê duyệt mọi hồ sơ không? Không; còn phải xét tenant, người tạo, trạng thái và các điều kiện nghiệp vụ.
3. Vì sao cần lớp kiểm tra ngoài HTTP? Vì service có thể được gọi từ đường khác và quyền phụ thuộc đối tượng cụ thể, không chỉ URL.
4. Vì sao POST trả 403 chưa đủ chứng minh kiểm thử phân quyền đúng? Vì CSRF hoặc cơ chế khác cũng có thể gây 403; cần xác minh điểm từ chối và trạng thái dữ liệu.
5. Thu hồi quyền trong database có vô hiệu hóa ngay JWT đã phát hành không? Không nhất thiết; cần cơ chế hiệu lực và thu hồi phù hợp.
6. Khi thêm một trạng thái nghiệp vụ mới, phải chỉnh phần nào? Bắt đầu từ mô hình và chính sách, sau đó cập nhật enforcement, test và cách vận hành.

**Ghi nhớ:** một chức năng được coi là có phân quyền đầy đủ khi quyền được **định nghĩa đúng**, được **thực thi trên mọi đường truy cập thực tế**, có **bằng chứng kiểm thử về cả cho phép và từ chối**, và có **quy trình duy trì tính đúng đắn khi dữ liệu, người dùng hoặc chính sách thay đổi**.