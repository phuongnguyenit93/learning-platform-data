# Tài sản, chủ thể, tài nguyên và thao tác trong một ứng dụng

Bảo mật ứng dụng bắt đầu từ việc hiểu **đang bảo vệ điều gì, ai có thể tác động tới nó, người đó truy cập đối tượng nào và muốn thực hiện hành động gì**. Bốn khái niệm **tài sản (asset)**, **chủ thể (subject)**, **tài nguyên (resource)** và **thao tác (action/operation)** tạo ra ngôn ngữ chung để xác định phạm vi bảo vệ, thiết kế quy tắc truy cập và đánh giá rủi ro. Đây là nền tảng tư duy trước khi viết cấu hình Spring Security.

## 1. Bốn khái niệm và mối quan hệ

| Khái niệm | Câu hỏi cần trả lời | Ý nghĩa | Ví dụ trong hệ thống quản lý đơn hàng |
| --- | --- | --- | --- |
| **Tài sản — Asset** | Điều gì có giá trị cần bảo vệ? | Dữ liệu, năng lực hoặc trạng thái có giá trị với người dùng/tổ chức; cần bảo vệ tính bí mật, toàn vẹn và sẵn sàng | Thông tin khách hàng, số tiền đơn hàng, uy tín dữ liệu thanh toán, khả năng đặt hàng |
| **Chủ thể — Subject** | Ai hoặc thành phần nào yêu cầu hành động? | Danh tính đang tham gia vào quyết định bảo mật; có thể là người dùng, dịch vụ hoặc tác vụ hệ thống | Alice, nhân viên hỗ trợ, service xuất báo cáo |
| **Tài nguyên — Resource** | Hành động hướng tới đối tượng nào? | Đối tượng hoặc điểm truy cập cụ thể có thể được bảo vệ bằng chính sách | Đơn hàng `ORD-100`, `GET /api/orders/100`, tập tin hóa đơn, bản ghi khách hàng |
| **Thao tác — Action/Operation** | Chủ thể muốn làm gì với tài nguyên? | Hành động cần cho phép hoặc từ chối; gồm đọc, tạo, sửa, xóa và các nghiệp vụ chuyên biệt | `read`, `update`, `cancel`, `refund`, `export` |

Một quyết định phân quyền thường có dạng:

```text
can(subject, action, resource, context) -> ALLOW | DENY
```

Trong đó `context` có thể bao gồm tenant, quan hệ sở hữu, trạng thái tài nguyên, thời điểm, phạm vi mạng, mức độ nhạy cảm, hoặc điều kiện nghiệp vụ. Ví dụ:

```text
can(Alice, READ, order#100, {tenant: "shop-a", owner: "Alice"})
can(Bob,    READ, order#100, {tenant: "shop-a", owner: "Alice"})
```

Hai request truy cập cùng tài nguyên với cùng thao tác có thể nhận kết quả khác nhau vì **chủ thể khác nhau**. Ngay cả một chủ thể cũng có thể được đọc đơn hàng nhưng không được hoàn tiền cho đơn đó.

Phân biệt quan trọng: **tài sản là thứ có giá trị cần bảo vệ; tài nguyên là đối tượng hoặc điểm truy cập cụ thể dùng để tiếp cận tài sản**. Một tài sản có thể xuất hiện qua nhiều tài nguyên: dữ liệu khách hàng hiện diện trong hàng cơ sở dữ liệu, API tra cứu, tệp xuất Excel, bộ nhớ cache và log. Bảo vệ một endpoint không đảm bảo mọi bản sao hoặc mọi đường truy cập tới tài sản đều an toàn.

## 2. Nhận diện tài sản trước khi đặt rule

Một ứng dụng có thể chứa nhiều loại tài sản:

- **Dữ liệu bí mật**: mật khẩu đã băm, token, khóa API, số điện thoại, địa chỉ, lịch sử thanh toán, hợp đồng; cần hạn chế truy cập và rò rỉ.
- **Dữ liệu có tính toàn vẹn cao**: giá sản phẩm, số dư, trạng thái thanh toán, quyền tài khoản, lịch sử duyệt; cần ngăn sửa trái phép.
- **Năng lực và độ sẵn sàng của hệ thống**: khả năng đăng nhập, hoàn tất đơn hàng, xử lý thanh toán, phục vụ request; cần phòng chống lạm dụng tài nguyên và gián đoạn.
- **Tài sản nghiệp vụ vô hình**: uy tín, bằng chứng kiểm toán, tính đúng đắn của quyết định phê duyệt; các tài sản này phụ thuộc vào nhiều thành phần kỹ thuật.

Ba thuộc tính bảo mật cổ điển giúp nhận diện ảnh hưởng khi một tài sản bị xâm phạm:

| Thuộc tính | Câu hỏi | Ví dụ sự cố |
| --- | --- | --- |
| **Confidentiality — Tính bí mật** | Người không có quyền có nhìn thấy dữ liệu không? | User A tải hóa đơn của user B |
| **Integrity — Tính toàn vẹn** | Người không có quyền có thay đổi dữ liệu/quy trình không? | User thường sửa giá thanh toán hoặc tự duyệt hoàn tiền |
| **Availability — Tính sẵn sàng** | Hệ thống/tài nguyên có còn dùng được khi cần không? | API quan trọng bị cạn tài nguyên do request lạm dụng |

Một tài sản có thể cần cả ba thuộc tính. Ví dụ số dư tài khoản vừa cần bảo mật, vừa cần đúng tuyệt đối và vừa cần khả dụng trong giao dịch. Mức độ bảo vệ phải phản ánh **tác động khi bị khai thác**, không chỉ dựa trên tên bảng hay đường dẫn API.

### 2.1. Lập bảng kiểm kê tài sản có ích cho đội phát triển

Thay vì chỉ lập danh sách endpoint, hãy ghi:

| Tài sản | Nơi xuất hiện | Rủi ro chính | Chủ sở hữu nghiệp vụ | Quy tắc bảo vệ điển hình |
| --- | --- | --- | --- | --- |
| Thông tin cá nhân khách hàng | Database, API chi tiết, CSV export, log | Rò rỉ dữ liệu | Bộ phận phụ trách khách hàng | Chỉ đúng tài khoản/nhân viên được ủy quyền; hạn chế xuất dữ liệu |
| Trạng thái hoàn tiền | Database, API refund, hàng đợi sự kiện | Thao tác gian lận | Bộ phận tài chính | Kiểm tra vai trò, quyền trên đơn hàng, giới hạn nghiệp vụ và audit |
| Phiên đăng nhập | Cookie, session store | Chiếm quyền phiên | Nhóm vận hành hệ thống | Cookie an toàn, HTTPS, quản lý phiên, CSRF đúng ngữ cảnh |
| Khả năng xử lý đơn hàng | API, DB connection, queue | Gián đoạn dịch vụ | Nhóm vận hành đơn hàng | Giới hạn sử dụng, timeout, giám sát và phân bổ tài nguyên |

Tài sản không nhất thiết ánh xạ một-một tới tài nguyên. Ví dụ dữ liệu cá nhân khách hàng có thể bị rò rỉ qua API `/customers/{id}`, tính năng export, phản hồi lỗi hoặc log, nên cần xem tất cả điểm hiển thị dữ liệu.

## 3. Chủ thể: ai đang yêu cầu quyền?

**Chủ thể** là bên thực hiện hoặc được quy trách nhiệm cho một hành động. Trong ứng dụng hiện đại, chủ thể có thể là:

1. **Người dùng**: khách, nhân viên, quản trị viên, người dùng đã đăng nhập hoặc chưa đăng nhập.
2. **Ứng dụng/dịch vụ**: một backend gọi backend khác bằng service account, OAuth2 client hoặc workload identity.
3. **Tiến trình tự động**: batch job, scheduler hoặc consumer xử lý sự kiện. Một tác vụ tự động cũng cần danh tính và giới hạn quyền thích hợp.

Cần phân biệt:

- **Actor/thực thể thực tế**: con người hoặc thành phần thực sự gây ra hành động.
- **Claimed identity/danh tính tự khai**: giá trị người gọi gửi lên, ví dụ `userId` trong request body; chưa được tin cậy chỉ vì có mặt.
- **Authenticated principal/danh tính đã được xác thực**: danh tính được hệ thống xác nhận thông qua một cơ chế hợp lệ; dùng làm đầu vào cho quyết định bảo mật.
- **Authority/permission**: các quyền được cấp cho principal; chúng mô tả điều có thể được phép thực hiện, nhưng vẫn có thể cần kiểm tra điều kiện trên tài nguyên.

Trong ứng dụng Servlet dùng Spring Security, kết quả xác thực được thể hiện qua đối tượng `Authentication`, thường nằm trong `SecurityContext`. `authentication.getName()` biểu thị tên của danh tính đã xác thực; `getAuthorities()` trả các quyền được gán. Với một số cơ chế token, principal còn có các claim hoặc định danh ổn định khác. **Không nên mặc định mọi ứng dụng đều dùng username làm khóa sở hữu dữ liệu**: mã người dùng nội bộ, subject của token hoặc tenant có thể cần ánh xạ riêng.

Một ví dụ sai về ranh giới tin cậy:

```http
GET /api/orders/100
X-User-Id: alice
```

Header `X-User-Id` do client tự gửi không chứng minh client là Alice. Nếu ứng dụng lấy header này làm chủ thể đã xác thực, kẻ tấn công có thể thay bằng `bob`. Hãy lấy chủ thể từ cơ chế xác thực đáng tin cậy và xác minh chữ ký, thời hạn, issuer, audience hoặc điều kiện cần thiết cho loại token đang dùng.

### 3.1. Ai là chủ thể trong một tình huống CSRF?

Nếu trình duyệt của Alice đã đăng nhập bằng session cookie và một trang độc hại khiến trình duyệt gửi POST, backend có thể nhìn thấy **principal Alice** do cookie được tự động đính kèm. Nhưng chủ thể gây ra hành động không hẳn là Alice chủ động bấm chức năng đó. Đây là lý do **xác thực danh tính** và **chứng minh request thay đổi trạng thái là hợp lệ** (ví dụ CSRF token khi phù hợp) là hai kiểm tra riêng.

## 4. Tài nguyên: đối tượng cần được kiểm soát

Tài nguyên có thể nằm ở nhiều cấp độ:

| Cấp độ | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| URL/API | `/api/admin/reports`, `/api/orders/{id}` | Request có được vào chức năng/endpoint này không? |
| Bản ghi hoặc đối tượng | Order `100` thuộc Alice, Tenant A | Người gọi có quan hệ sở hữu hoặc quyền với đúng object này không? |
| Trường dữ liệu | `customer.email`, `order.discountRate` | Có được xem/sửa từng trường nhạy cảm không? |
| Tài liệu/tệp | Hóa đơn PDF, ảnh riêng tư, bản export | Có được tải, chia sẻ hoặc tạo đường dẫn truy cập không? |
| Năng lực nghiệp vụ | Hoàn tiền, thay đổi quyền, xuất toàn bộ dữ liệu | Có được thực hiện chức năng nhạy cảm này không? |
| Hạ tầng | Admin console, secret, queue, storage bucket | Danh tính nào được đọc/ghi/quản trị? |

**URL không phải toàn bộ tài nguyên.** Hai request cùng đi qua `GET /api/orders/{id}` nhưng trỏ tới hai bản ghi khác nhau. Rule `authenticated()` trên URL chỉ yêu cầu login; nó không tự kiểm tra một user có sở hữu `orderId` đó hay không.

Một lỗi phổ biến là **Broken Object Level Authorization (BOLA)**, thường được gọi là IDOR khi lộ ID có thể đoán hoặc thay đổi: người dùng hợp lệ đổi `/api/orders/100` thành `/api/orders/101` và thấy dữ liệu của người khác. Vấn đề cốt lõi là **thiếu quyết định phân quyền trên đúng object**, không phải việc ID dễ đoán. Chuyển từ ID tuần tự sang UUID có thể làm khó dò tìm nhưng không thay thế kiểm tra quyền.

Đối với nhiều tenant, cùng một `orderId` cũng có thể cần thêm `tenantId` để xác định đúng tài nguyên. Tenant phải được suy ra từ ngữ cảnh đáng tin cậy; không coi tham số `tenantId` do client gửi là bằng chứng người gọi thuộc tenant đó.

## 5. Thao tác: phân biệt HTTP method và hành động nghiệp vụ

Các thao tác phổ biến gồm `create`, `read`, `update`, `delete` (CRUD). Tuy nhiên, bảo mật thực tế còn có:

- `approve`: phê duyệt đơn hàng hoặc yêu cầu;
- `refund`: hoàn tiền;
- `export`: tải hàng loạt dữ liệu;
- `share`: cấp quyền cho người khác;
- `assign-role`: thay đổi quyền truy cập;
- `rotate-key`: xoay vòng khóa;
- `cancel`: hủy tác vụ hoặc giao dịch.

Không thể suy ra đầy đủ quyền chỉ từ HTTP method:

- `GET /api/orders/100` là đọc một đơn hàng; `GET /api/orders/export` có thể tiết lộ hàng nghìn đơn hàng và cần quyền khác.
- `POST /api/orders/100/refund` là thao tác tài chính có điều kiện; không tương đương POST tạo tài nguyên thông thường.
- `PATCH /api/users/100` có thể sửa thông tin cá nhân, nhưng thay đổi trường `roles` thường phải yêu cầu quyền quản trị bổ sung.
- `DELETE /api/orders/100` có thể bị cấm sau khi đã thanh toán, bất kể người gọi có quyền xóa đơn hàng nháp.

Hãy đặt tên quyền bằng hành vi nghiệp vụ đủ rõ, ví dụ `order:read:own`, `order:read:any`, `order:refund` hoặc `user:assign-role`. Tên quyền không tự bảo vệ ứng dụng; server phải thực sự thực thi policy tại nơi hành động xảy ra.

## 6. Ghép chủ thể, tài nguyên, thao tác và ngữ cảnh thành chính sách

Một quyết định bảo mật có thể mô tả như sau:

```text
Subject       = alice (authenticated, tenant-a)
Action        = READ
Resource      = order#100 (owner=alice, tenant=tenant-a)
Context       = application rules + order state
Policy        = sameTenant && (isOwner || hasPermission("order:read:any"))
Decision      = ALLOW
```

Một policy theo các thuộc tính của chủ thể, tài nguyên và ngữ cảnh là cách tư duy gần với **Attribute-Based Access Control (ABAC)**. Một policy dựa trên role, chẳng hạn admin/user, gần với **Role-Based Access Control (RBAC)**. Trong hệ thống thật có thể kết hợp role, permission, ownership, tenant, trạng thái đối tượng và ràng buộc nghiệp vụ.

### 6.1. Ma trận quyền ví dụ

Giả sử Shop A có Alice (khách hàng), Bob (khách hàng), auditor (nhân viên kiểm tra), và Shop B có administrator riêng. Đơn hàng `ORD-100` thuộc Alice tại Shop A.

| Chủ thể | Tài nguyên | Thao tác | Quyết định | Lý do |
| --- | --- | --- | --- | --- |
| Alice | `ORD-100` | Đọc | Allow | Đã xác thực, cùng tenant, sở hữu đơn |
| Bob | `ORD-100` | Đọc | Deny | Cùng tenant nhưng không sở hữu; không có quyền xem mọi đơn |
| Auditor của Shop A | `ORD-100` | Đọc | Allow | Có quyền `order:read:any` trong Shop A |
| Auditor của Shop A | `ORD-100` | Sửa | Deny | Quyền đọc không bao gồm quyền sửa |
| Admin của Shop B | `ORD-100` | Đọc | Deny | Sai tenant, dù mang role admin tại tenant khác |
| Khách ẩn danh | `ORD-100` | Đọc | Deny | Chưa xác thực |
| Alice | `ORD-100` | Hoàn tiền | Deny nếu không có quyền/điều kiện hoàn tiền | Sở hữu không tự đồng nghĩa được làm mọi thao tác |

Trong ví dụ này, quyền `:any` chỉ có phạm vi **cùng tenant**. Quyền dành cho nhân viên hoặc quản trị viên phải có phạm vi tường minh; role `ADMIN` không mặc nhiên được vượt qua giới hạn tenant.

### 6.2. Trật tự suy nghĩ khi thiết kế một quyết định

1. **Xác định tài sản:** nếu hành động được cho phép sai, tài sản nào bị ảnh hưởng, thuộc tính nào của tài sản bị hỏng?
2. **Xác minh chủ thể:** principal đến từ nguồn nào, đã xác thực hay chưa, các permission/tenant đã được xác minh ra sao?
3. **Xác định tài nguyên thực:** ID trong URL tương ứng bản ghi/tệp/đối tượng nào và thuộc ai?
4. **Xác định thao tác đúng nghĩa:** đây là đọc, sửa, export, hoàn tiền hay hành động nào khác? Có nguy cơ đặc biệt không?
5. **Đánh giá policy:** kiểm tra role/authority, tenant, ownership, trạng thái đối tượng và ngữ cảnh; không có quy tắc cho phép thì từ chối.
6. **Thực thi an toàn:** chặn trước khi có tác dụng phụ; hạn chế rò rỉ thông tin trong response và log.
7. **Kiểm thử:** có case được phép và các case bị từ chối khi thiếu login, sai role, sai owner, sai tenant, sai trạng thái.

## 7. Ví dụ Java 17 chạy độc lập: mô hình hóa quyết định

Ví dụ sau mô phỏng quyết định truy cập đơn hàng trong bộ nhớ, chưa cần framework hoặc database. Nó cho thấy **chủ thể, tài nguyên, thao tác và policy** phối hợp thế nào. Đây là bài tập về tư duy phân quyền, **không phải hệ thống xác thực production**: thuộc tính `authenticated` và permission được giả lập bằng dữ liệu trong code.

Tạo tệp `AccessModel.java`:

```java
import java.util.Set;

public class AccessModel {

    record Subject(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record OrderResource(String id, String tenantId, String ownerId) {}

    enum Action { READ, UPDATE, EXPORT }

    static boolean allowed(
        Subject subject,
        Action action,
        OrderResource resource
    ) {
        if (subject == null || !subject.authenticated()) {
            return false;
        }

        // Cả quyền "any" cũng chỉ có hiệu lực trong cùng tenant.
        if (!subject.tenantId().equals(resource.tenantId())) {
            return false;
        }

        String permissionBase = switch (action) {
            case READ -> "order:read";
            case UPDATE -> "order:update";
            case EXPORT -> "order:export";
        };

        boolean anyInTenant = subject.permissions()
            .contains(permissionBase + ":any");

        boolean own = subject.userId().equals(resource.ownerId())
            && subject.permissions().contains(permissionBase + ":own");

        return anyInTenant || own;
    }

    static void show(
        String label,
        Subject subject,
        Action action,
        OrderResource resource
    ) {
        System.out.println(label + ": " + allowed(subject, action, resource));
    }

    public static void main(String[] args) {
        OrderResource order = new OrderResource("ORD-100", "shop-a", "alice");

        Subject alice = new Subject(
            "alice", "shop-a", true,
            Set.of("order:read:own", "order:update:own")
        );
        Subject bob = new Subject(
            "bob", "shop-a", true, Set.of("order:read:own")
        );
        Subject auditor = new Subject(
            "auditor", "shop-a", true, Set.of("order:read:any")
        );
        Subject otherTenantAdmin = new Subject(
            "admin", "shop-b", true, Set.of("order:read:any")
        );
        Subject anonymous = new Subject(
            "guest", "shop-a", false, Set.of("order:read:any")
        );

        show("Alice reads own", alice, Action.READ, order);
        show("Bob reads Alice's order", bob, Action.READ, order);
        show("Auditor reads", auditor, Action.READ, order);
        show("Auditor updates", auditor, Action.UPDATE, order);
        show("Other tenant admin reads", otherTenantAdmin, Action.READ, order);
        show("Anonymous reads", anonymous, Action.READ, order);
        show("Alice exports", alice, Action.EXPORT, order);
        show("Alice updates own", alice, Action.UPDATE, order);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AccessModel.java
java AccessModel
```

Kết quả chuẩn:

```text
Alice reads own: true
Bob reads Alice's order: false
Auditor reads: true
Auditor updates: false
Other tenant admin reads: false
Anonymous reads: false
Alice exports: false
Alice updates own: true
```

Giải thích:

- Alice có quyền `order:read:own` và là chủ đơn nên được đọc. Bob có cùng permission nhưng không sở hữu nên bị từ chối.
- Auditor chỉ có quyền `order:read:any` nên được đọc mọi đơn **trong Shop A**; không có `order:update:any` nên không được sửa.
- Người quản trị ở Shop B bị chặn trước khi xét quyền `:any`.
- Người chưa xác thực luôn bị từ chối trong policy này, ngay cả khi đối tượng `Subject` bị gán permission bằng tay.
- Alice được sửa đơn của mình theo mô hình đơn giản, nhưng chưa chắc được phép sửa nếu đơn đã thanh toán; đó là một điều kiện ngữ cảnh cần bổ sung trong hệ thống thật.

Hãy thử đổi `order.ownerId` thành `bob`, hoặc thay `Action.READ` bằng `Action.EXPORT`. Kết quả thay đổi theo tài nguyên và thao tác dù danh tính người gọi giữ nguyên.

**Giới hạn cố ý của ví dụ:** code không xác thực password/token, không thực thi transaction, không có database và không kiểm tra trạng thái đơn. Trong ứng dụng thực tế, các dữ liệu về danh tính/tenant/permission phải được thiết lập từ nguồn đáng tin cậy, còn quyền trên object phải được kiểm tra tại server theo dữ liệu mới và chính sách nghiệp vụ.

## 8. Ánh xạ bốn khái niệm vào Spring Security

Trong Spring Security Servlet, một chuỗi xử lý hợp lý ở mức khái niệm là:

```text
HTTP request
    |
    v
SecurityFilterChain
    |--> Các lớp bảo vệ request phù hợp (ví dụ CSRF)
    |--> Authentication -> SecurityContext (ai?)
    |--> Authorization request-level (có được gọi endpoint?)
    v
Controller -> Service -> Repository
                |
                |--> Load resource theo ID + tenant
                |--> Kiểm tra ownership, permission, trạng thái (làm gì, với object nào?)
                v
          Thực hiện nghiệp vụ / từ chối
```

Sơ đồ minh họa trách nhiệm; thứ tự filter thực tế do cơ chế/cấu hình Spring Security quyết định. Ở tầng nghiệp vụ, phép kiểm tra có thể nằm tại method security, service, policy component hoặc truy vấn database được giới hạn phù hợp.

| Khái niệm của bài | Thể hiện thường gặp trong Spring |
| --- | --- |
| Chủ thể | `Authentication` và principal trong `SecurityContext`; quyền từ `GrantedAuthority` |
| Thao tác | HTTP method trong `requestMatchers`; hoặc hành động nghiệp vụ trong service như `approve`, `refund` |
| Tài nguyên | URL request, domain object `Order`/`Invoice`, ID bản ghi, tệp, tenant |
| Quyết định | `authorizeHttpRequests`, method security `@PreAuthorize` hoặc policy nghiệp vụ |
| Tài sản cần bảo vệ | Thông tin khách hàng, giao dịch, secret, trạng thái hệ thống; do thiết kế nghiệp vụ xác định, không tự suy ra từ annotation |

### 8.1. Kiểm tra theo đường dẫn: bảo vệ điểm vào

Ví dụ cấu hình Spring Boot 3 / Spring Security 6 theo Servlet:

```java
@Configuration
@EnableMethodSecurity
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là **đoạn cấu hình minh họa**, không phải tệp Java độc lập: cần imports và dependencies Spring Boot Web, Spring Security, một cơ chế cung cấp user/authentication, controller/service phù hợp. Ví dụ chỉ thể hiện rằng catalog GET công khai, đơn hàng yêu cầu login, các request còn lại bị từ chối mặc định. Spring Security thường bật CSRF protection ở cấu hình Servlet; các request thay đổi trạng thái phải đáp ứng CSRF khi áp dụng.

Quan trọng: `authenticated()` không tự giới hạn `orderId` theo người dùng. Nếu dừng tại đây, người đăng nhập có thể truy cập ID của người khác nếu service không kiểm tra quyền trên object.

### 8.2. Kiểm tra tại service: bảo vệ đúng tài nguyên

Khi đã bật `@EnableMethodSecurity`, một service có thể yêu cầu policy kiểm tra đúng đơn hàng đang truy cập:

```java
@PreAuthorize("@orderPolicy.canRead(authentication, #p0)")
public OrderDto getOrder(long orderId) {
    return orderService.loadOrder(orderId);
}
```

Đây là **đoạn minh họa**: ứng dụng cần một bean có tên `orderPolicy`, phương thức `canRead(Authentication, long)`, `OrderDto` và `orderService` thực sự. Tham chiếu `#p0` lấy tham số thứ nhất của method; `authentication` là danh tính trong ngữ cảnh Spring Security. Với một ứng dụng thật, policy cần:

1. Xác nhận principal được xác thực và có permission tương ứng;
2. Tìm hoặc giới hạn đơn hàng theo tenant đáng tin cậy;
3. So sánh owner hoặc quyền xem mọi đơn trong tenant;
4. Đánh giá điều kiện nghiệp vụ khác nếu có;
5. Từ chối khi tài nguyên không tồn tại hoặc không có quyền.

Chỉ gọi `@PreAuthorize("isAuthenticated()")` ở method vẫn chưa đủ để ngăn IDOR. Nên bảo vệ tại tầng có đầy đủ thông tin về đối tượng và tại các đường thực thi khác nhau, không chỉ ở controller. Với các thao tác có điều kiện trạng thái hoặc cạnh tranh cập nhật, cần kiểm tra trong transaction hoặc câu lệnh update có điều kiện phù hợp để tránh trạng thái bị thay đổi giữa lúc kiểm tra và lúc ghi (**time-of-check/time-of-use**).

Không lấy `ownerId` hoặc `tenantId` trong body làm bằng chứng quyền. Ví dụ client gửi `{"ownerId":"alice"}` không có nghĩa chủ thể đang gọi là Alice.

## 9. Từ bảng khái niệm đến threat modeling

Bốn khái niệm cũng giúp đặt câu hỏi về những tình huống tấn công:

| Tình huống | Tài sản bị đe dọa | Chủ thể liên quan | Tài nguyên & thao tác | Kiểm soát cần có |
| --- | --- | --- | --- | --- |
| User đổi ID URL để đọc đơn của người khác | Bí mật dữ liệu cá nhân | User đã đăng nhập | Order khác chủ, `read` | Kiểm tra owner/tenant ở server |
| Nhân viên đọc được đơn nhưng gọi API hoàn tiền | Toàn vẹn giao dịch | Nhân viên có quyền `read` | Order, `refund` | Permission riêng cho refund, kiểm tra trạng thái/giới hạn |
| Service ở Tenant B gửi ID tài nguyên Tenant A | Tách biệt dữ liệu tenant | Service account | Order Tenant A, `read/update` | Xác thực service và giới hạn tenant từ ngữ cảnh tin cậy |
| Website ngoài ép trình duyệt gửi POST | Toàn vẹn dữ liệu | Kẻ tấn công điều khiển request từ trình duyệt nạn nhân | Thao tác thay đổi trạng thái | CSRF khi dùng credential tự đính kèm như cookie, cùng với authz |
| Export dữ liệu vượt phạm vi | Bí mật dữ liệu hàng loạt | User/nhân viên có login | Báo cáo, `export` | Quyền export riêng, lọc theo tenant, ghi audit, giới hạn lượng dữ liệu |
| Tác vụ tự động bị cấp quyền quản trị toàn hệ thống | Nhiều tài sản | Service account | API, dữ liệu, `read/write/admin` | Nguyên tắc ít quyền nhất, credential lifecycle, phân phạm vi rõ |

Một request “được xác thực” vẫn có thể nguy hiểm. Khi threat modeling, hãy hỏi thêm: kẻ tấn công có thể đóng vai chủ thể nào, đổi tài nguyên nào, yêu cầu thao tác nào, lợi dụng điều kiện ngữ cảnh nào và gây ảnh hưởng tới tài sản ra sao?

## 10. Những lỗi thiết kế cần phát hiện sớm

### 10.1. Chỉ định nghĩa quyền theo role toàn cục

Rule `hasRole("USER")` cho phép user vào một nhóm API nhưng không trả lời “user này có quyền với bản ghi nào?”. Cần xét thêm ownership, tenant, quan hệ nhóm và trạng thái tài nguyên. Role là một đầu vào cho policy, không phải toàn bộ policy.

### 10.2. Tin tưởng thuộc tính do client gửi

`userId`, `tenantId`, `isAdmin` và `permissions` trong JSON body/query/header đều có thể bị sửa. Kiểm tra định danh/quyền từ principal đã xác thực và dữ liệu phía server; chỉ dùng các trường client gửi làm yêu cầu cần xác minh.

### 10.3. Bỏ qua các hành động không thuộc CRUD

Xuất dữ liệu, hoàn tiền, cấp quyền, kích hoạt tài khoản và thay đổi khóa bảo mật có rủi ro khác nhau dù cùng gọi POST/PATCH. Phải đặt quyền và điều kiện nghiệp vụ riêng theo hành động.

### 10.4. Chỉ chặn ở giao diện hoặc ở một controller

Ẩn nút “Xóa” không phải phân quyền. Client khác vẫn gọi HTTP trực tiếp. Ngay cả khi đã bảo vệ controller, job, message consumer hoặc service nội bộ khác vẫn có thể gọi cùng nghiệp vụ; nên thực thi policy ở ranh giới thích hợp và bảo vệ mọi đường vào.

### 10.5. Dùng ID khó đoán để thay thế authorization

UUID, số ngẫu nhiên hoặc URL dài không chứng minh quyền. Nếu người dùng nhận được ID qua log, link chia sẻ hoặc lỗi hiển thị, backend vẫn phải kiểm tra sở hữu và tenant.

### 10.6. Hiểu “ADMIN” thành quyền vô hạn

Admin thường có **phạm vi quản trị**: một cửa hàng, một phòng ban hoặc một tổ chức. Nếu quyền vô tình vượt tenant, mức độ ảnh hưởng khi một tài khoản bị xâm phạm tăng mạnh. Quyền hệ thống đặc biệt phải được xác định rõ ranh giới.

### 10.7. Lộ thông tin qua phản hồi và nhật ký

Một API có thể trả 403 để bảo vệ dữ liệu nhưng vẫn rò rỉ tên khách hàng qua error message hoặc log. Khi cần tránh tiết lộ tài nguyên có tồn tại, ứng dụng có thể chọn cách phản hồi phù hợp với chính sách, ví dụ 404 cho đối tượng không được phép truy cập. Log nên ghi mã người gọi, thao tác, loại tài nguyên, kết quả, thời điểm và correlation ID mà không ghi secret hoặc dữ liệu nhạy cảm không cần thiết.

### 10.8. Phân quyền đúng ở thời điểm đọc nhưng sai khi ghi

Quyền có thể đổi hoặc đơn hàng chuyển trạng thái trong lúc request đang chạy. Với tác vụ nhạy cảm, việc kiểm tra quyền và thay đổi dữ liệu nên tuân theo ranh giới transaction và cơ chế kiểm soát đồng thời thích hợp. Cũng cần kiểm tra lại ở những bước chuyển trạng thái quan trọng.

## 11. Checklist thiết kế và kiểm thử

Trước khi đưa một endpoint hoặc một nghiệp vụ vào hoạt động, trả lời:

- **Tài sản:** dữ liệu/trạng thái nào có giá trị? Ảnh hưởng tới confidentiality, integrity và availability ra sao?
- **Chủ thể:** ai có thể gọi? danh tính/authority/tenant được xác minh từ đâu?
- **Tài nguyên:** request tham chiếu bản ghi, tệp, trường dữ liệu hoặc chức năng nào? ranh giới tenant/owner nằm ở đâu?
- **Thao tác:** đây chính xác là `read`, `update`, `approve`, `refund` hay `export`? Có điều kiện trạng thái không?
- **Chính sách:** ai được phép, với đối tượng nào, trong điều kiện nào? Mặc định deny hay có rule quá rộng?
- **Thực thi:** check ở tầng nào? mọi đường gọi nghiệp vụ có cùng kiểm soát không? có rủi ro race condition không?
- **Kiểm thử âm:** anonymous, sai role, sai owner, sai tenant, sai trạng thái, sai loại thao tác có bị từ chối không?
- **Phòng vệ khác:** có cần CSRF, validation, rate limit, audit, cookie/transport/header protections và giới hạn export không?

Một ma trận test tối thiểu cho `GET /api/orders/{id}` gồm: Alice đọc đơn của Alice (allow), Bob đọc đơn của Alice (deny), user Tenant B đọc đơn Tenant A (deny), anonymous gọi API (deny). Với `POST /api/orders/{id}/refund` còn cần case thiếu quyền refund, đơn không đủ điều kiện hoàn tiền và request CSRF không hợp lệ trong cơ chế dùng cookie.

## 12. Tự kiểm tra

**Câu 1.** Dữ liệu số dư khách hàng thuộc loại nào: tài sản hay tài nguyên? Một endpoint trả về số dư là gì?

**Câu 2.** Hai người có `ROLE_USER`. Vì sao không thể chỉ dùng `hasRole("USER")` để cho phép họ xem mọi `/api/orders/{id}`?

**Câu 3.** Một nhân viên có quyền xem mọi đơn của Shop A. Điều đó có tự cho phép nhân viên export mọi đơn hoặc xem đơn Shop B không?

**Câu 4.** Client gửi `{"userId":"alice","isAdmin":true}`. Những trường này có thể dùng làm danh tính và quyền đã được xác thực không?

**Câu 5.** Hai endpoint GET `/api/orders/100` và `/api/orders/export` có nhất thiết cùng permission vì đều dùng GET không?

**Câu 6.** Trong ứng dụng session cookie, một POST giả mạo được trình duyệt gửi khi người dùng đang login sẽ liên quan đến vấn đề nào ngoài authorization?

**Đáp án gợi ý:**

1. Dữ liệu số dư là tài sản cần bảo vệ; endpoint và bản ghi/tài liệu cụ thể chứa số dư là tài nguyên/đường truy cập tới tài sản.
2. Vì role chỉ mô tả quyền khái quát, không xác minh quan hệ với đúng object; cần kiểm tra owner, tenant hoặc điều kiện nghiệp vụ.
3. Không. Quyền đọc không mặc nhiên bao gồm export hoặc quyền xuyên tenant.
4. Không. Đó là dữ liệu client tự khai; server phải dùng principal/authority đã xác thực và dữ liệu đáng tin cậy.
5. Không. Export có phạm vi, tác động và quyền nghiệp vụ riêng.
6. Cần xét CSRF protection khi credential được trình duyệt tự đính kèm; request đã có principal không chứng minh người dùng chủ động gửi request đó.

### Tài liệu đọc tiếp

- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [OWASP API Security – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
