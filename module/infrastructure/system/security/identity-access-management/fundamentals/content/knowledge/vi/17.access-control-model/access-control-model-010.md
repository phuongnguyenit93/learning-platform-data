# Object-level access

## 1. Quyền truy cập phải gắn với đối tượng cụ thể

Một người dùng đăng nhập thành công, có vai trò `CUSTOMER` và được phép gọi API đơn hàng vẫn có thể không được xem đơn hàng `O-204`. Cần biết đơn đó thuộc tenant nào, ai sở hữu, có được chia sẻ không và người dùng đang muốn làm gì với nó.

**Object-level access** là kiểm soát quyền đối với **một tài nguyên cụ thể**, chẳng hạn một đơn hàng, hồ sơ nhân viên, tài liệu, ví hoặc ticket hỗ trợ. Trong ngữ cảnh này, “object” là đối tượng nghiệp vụ được bảo vệ; nó không nhất thiết tương ứng với một instance Java hoặc đúng một hàng trong cơ sở dữ liệu.

Câu hỏi cần trả lời là:

> Với danh tính và ngữ cảnh đã xác minh, chủ thể này có được thực hiện hành động này trên đối tượng này tại thời điểm xét quyền không?

Một quyết định có thể được biểu diễn như sau:

~~~text
authorize(subject, action, resource, context)
    -> ALLOW hoặc DENY
~~~

Trong nền tảng IAM, xác thực cung cấp danh tính để xét quyền. RBAC, ABAC, quan hệ sở hữu và quyền chia sẻ cung cấp dữ liệu cho quyết định. Object-level access là nơi các yếu tố đó gặp một tài nguyên thật và một hành động thật.

Sau bài này, người học có thể:

- Phân biệt quyền vào chức năng với quyền trên từng đối tượng và quyền trên từng thuộc tính.
- Nhận diện BOLA/IDOR trong API đọc, ghi và xử lý hàng loạt.
- Thiết kế chính sách kết hợp tenant, chủ sở hữu, quyền phạm vi tenant và quyền chia sẻ.
- Đặt kiểm tra quyền ở luồng xử lý nghiệp vụ, truy vấn dữ liệu và thời điểm thay đổi trạng thái.
- Xây dựng tình huống kiểm thử cho truy cập ngang, truy cập chéo tenant và thu hồi quyền.

## 2. Bốn lớp câu hỏi cần tách bạch

Giả sử Alice gửi yêu cầu:

~~~http
GET /api/orders/O-204
Authorization: Bearer <access-token>
~~~

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang gọi? | Token đã được xác minh và ánh xạ thành Alice |
| Function-level authorization | Alice có được sử dụng chức năng này? | Được gọi chức năng tra cứu đơn hàng |
| Object-level authorization | Alice có được đọc đúng `O-204`? | Đơn thuộc tenant đang hoạt động và có quan hệ cho phép |
| Property-level authorization | Alice được đọc hoặc sửa trường nào? | Được đọc trạng thái nhưng không được đọc ghi chú chống gian lận |

Một API có thể vượt qua ba lớp đầu mà vẫn trả thừa trường nhạy cảm. Việc có quyền truy cập đối tượng không trao quyền đối với tất cả thuộc tính của nó; OWASP mô tả nhóm lỗi liên quan ở API3:2023. [Nguồn: OWASP — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Ngược lại, chỉ trả vài trường cũng không sửa được lỗi người dùng truy cập đối tượng của người khác. Một trạng thái đơn hàng, tên khách hàng hoặc tổng tiền vẫn có thể là dữ liệu cần bảo vệ.

Trong OAuth, scope như `orders:read` thường giới hạn loại hành động mà bên gọi được yêu cầu. Việc scope đó cho phép đọc những đơn hàng nào phụ thuộc hợp đồng của hệ thống. Nếu scope chỉ mô tả khả năng gọi chức năng, resource server vẫn phải xét quyền trên từng đơn. Đăng nhập qua SSO hoặc hoàn thành MFA cũng không tự tạo quan hệ sở hữu với một đơn hàng.

## 3. Từ tham chiếu đối tượng đến BOLA/IDOR

### 3.1. Một API có vẻ hợp lệ nhưng thiếu kiểm tra quan trọng

Đoạn mã sau là ví dụ có chủ đích về cách triển khai thiếu quyền ở mức đối tượng:

~~~java
// KHÔNG AN TOÀN: chưa xét quyền trên đơn được tìm thấy.
public OrderView getOrder(String requestedId) {
    Order order = repository.findById(requestedId)
        .orElseThrow(NotFoundException::new);

    return toView(order);
}
~~~

Nếu middleware chỉ yêu cầu người gọi đăng nhập, Bob cũng có thể gọi hàm này với mã đơn của Alice. Cơ sở dữ liệu tìm thấy đơn không có nghĩa Bob được phép đọc nó.

OWASP gọi lỗi kiểm soát quyền trên đối tượng trong API là **Broken Object Level Authorization — BOLA**. Việc thay tham chiếu do client gửi để truy cập đối tượng ngoài quyền thường được gọi là **Insecure Direct Object Reference — IDOR**. Tham chiếu có thể nằm ở path, query, header hoặc body; không chỉ ở số ID trên URL. [Nguồn: OWASP — API1:2023](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

Ví dụ trong một ứng dụng thử nghiệm do đội phát triển kiểm soát:

~~~http
GET /api/orders/O-101
GET /api/orders/O-204
~~~

Hai yêu cầu đều đúng cú pháp. Tuy nhiên, nếu `O-101` thuộc Alice còn `O-204` thuộc Bob, việc đổi mã đơn phải dẫn đến một quyết định quyền mới.

### 3.2. ID khó đoán giúp hạn chế dò tìm, không tạo ra quyền

Đổi mã số tăng dần thành UUID có thể làm việc đoán mã khó hơn. Nhưng ID vẫn có thể xuất hiện trong lịch sử, email, log hoặc một liên kết được chuyển tiếp. Khi người dùng đã biết ID, server vẫn phải xét quyền. OWASP coi độ phức tạp của định danh là biện pháp bổ sung, đồng thời khuyến nghị tra cứu trong tập dữ liệu chủ thể được phép truy cập. [Nguồn: OWASP — IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html).

Định danh trả lời “đối tượng nào?”. Chính sách trả lời “ai được làm gì với đối tượng đó?”. Thiết kế không nên gộp hai câu hỏi này một cách ngầm định.

Một đường dẫn lưu trữ hoặc khóa chính được che bằng mã hóa cũng không làm biến mất nhu cầu xét quyền. Nếu hệ thống cố ý dùng liên kết như một capability, quyền của liên kết phải được thiết kế riêng: tài nguyên, hành động, thời hạn và điều kiện sử dụng phải rõ ràng.

## 4. Xây dựng một chính sách nghiệp vụ xuyên suốt

Các phần tiếp theo dùng một **hệ thống đơn hàng giả định**, với quy tắc do bài học đặt ra. Đây là ví dụ thiết kế, không phải chính sách bắt buộc cho mọi doanh nghiệp.

### 4.1. Dữ liệu và chủ thể

Mỗi đơn hàng có:

~~~text
Order
    id
    tenantId
    ownerId
    state
    version
~~~

Mỗi ngữ cảnh chủ thể đã được server xác minh có:

~~~text
SubjectContext
    subjectId
    activeTenantId
    activeMembership
    tenantPermissions
~~~

Một quyền chia sẻ đọc có:

~~~text
ReadGrant
    tenantId
    orderId
    subjectId
    expiresAt
    revoked
~~~

`ownerId` là người được xác định sở hữu đơn theo mô hình nghiệp vụ của ví dụ. Không mặc định rằng người tạo, người thanh toán, người được giao xử lý và người sở hữu luôn là cùng một người.

`tenantPermissions` là quyền đã được giải quyết cho tenant đang hoạt động. Một quyền quản lý trong tenant A không tự áp dụng cho tenant B.

### 4.2. Quy tắc đọc và hủy đơn

Để thực hiện một hành động, trước hết cần:

1. Chủ thể hợp lệ.
2. Tư cách thành viên trong tenant đang hoạt động còn hiệu lực.
3. Tenant của đơn trùng tenant đã được xác minh trong ngữ cảnh yêu cầu.

Sau đó áp dụng quy tắc của hành động:

| Hành động | Điều kiện bổ sung để cho phép |
| --- | --- |
| `READ` | Là chủ sở hữu, hoặc có `READ_ALL_ORDERS` trong tenant, hoặc có quyền chia sẻ đọc còn hiệu lực cho đúng đơn |
| `CANCEL` | Đơn đang `DRAFT` và chủ thể là chủ sở hữu hoặc có `CANCEL_ALL_ORDERS` trong tenant |
| `SHARE` | Chưa được định nghĩa trong ví dụ; mặc định từ chối |
| `TRANSFER` | Chưa được định nghĩa trong ví dụ; mặc định từ chối |

Theo chính sách này:

- Quyền chia sẻ đọc không cho phép hủy.
- Quyền `READ_ALL_ORDERS` không cho phép hủy.
- Quyền `CANCEL_ALL_ORDERS` không tự cho phép đọc toàn bộ đơn.
- Chủ sở hữu không được hủy đơn đã `PAID`.
- Chủ sở hữu không tự được cấp quyền chia sẻ hoặc chuyển quyền sở hữu.
- Khi mất tư cách thành viên tenant, quan hệ sở hữu hoặc grant cũ không đủ để tiếp tục truy cập.

Doanh nghiệp có thể chọn những quy tắc khác, chẳng hạn cho người sở hữu được chia sẻ tài liệu. Điều cần giữ là mỗi quyền được định nghĩa và kiểm tra rõ ràng, thay vì suy diễn từ chữ “owner” hoặc “admin”.

### 4.3. Công thức hóa để phát hiện lỗ hổng

~~~text
base =
    valid_subject
    AND active_membership
    AND subject.activeTenantId = order.tenantId

can_read =
    base
    AND (
        order.ownerId = subject.id
        OR has_tenant_permission(READ_ALL_ORDERS)
        OR active_read_grant(subject, order, now)
    )

can_cancel =
    base
    AND order.state = DRAFT
    AND (
        order.ownerId = subject.id
        OR has_tenant_permission(CANCEL_ALL_ORDERS)
    )
~~~

Ngoặc quanh các nhánh `OR` có ý nghĩa bảo mật. Biểu thức:

~~~text
same_tenant AND is_owner OR has_read_grant
~~~

có thể cho phép grant vượt qua điều kiện tenant nếu được đánh giá theo độ ưu tiên toán tử thông thường. Quy tắc của ví dụ là mọi nhánh cho phép đều nằm bên trong ranh giới `base`.

## 5. Dữ liệu dùng để xét quyền phải đến từ đâu?

Một policy đúng vẫn cho kết quả sai nếu đầu vào do người gọi tự khai.

| Dữ liệu | Nguồn phù hợp trong ví dụ | Nguồn không đủ làm bằng chứng |
| --- | --- | --- |
| `subjectId` | Ngữ cảnh xác thực đã được server xác minh | `userId` trong JSON |
| Tenant đang hoạt động | Tenant được chọn và đã đối chiếu membership của chủ thể | Chỉ đọc thẳng `X-Tenant-Id` |
| `ownerId`, `state` | Bản ghi đơn hàng do server quản lý | Trường tương ứng trong body cập nhật |
| Quyền tenant | Dữ liệu phân quyền đã được giải quyết đúng tenant | Cờ `isAdmin=true` do client gửi |
| Grant chia sẻ | Kho quyền có kiểm tra đối tượng, chủ thể, tenant và hiệu lực | Client nói rằng đơn “đã được chia sẻ” |
| Thời điểm xét quyền | Đồng hồ và quy tắc thời gian của server | `currentTime` trong request |

Client có thể chọn tenant hoặc truyền một mã đơn; đó là dữ liệu yêu cầu, không phải bằng chứng rằng quyền tồn tại.

Một token có chữ ký hợp lệ chỉ bảo vệ tính xác thực và toàn vẹn của các claim theo quy trình xác minh tương ứng. Nếu membership vừa bị thu hồi nhưng ứng dụng chỉ dùng claim từ token cũ, quyền có thể còn hiệu lực trong khoảng thời gian ứng dụng chấp nhận dữ liệu cũ. Cần định nghĩa chính sách về độ mới của dữ liệu quyền; không thể chỉ dựa vào việc token chưa hết hạn.

Nếu cùng hệ thống tin cậy nhiều identity provider, định danh chủ thể cần được chuẩn hóa để tránh va chạm giữa các issuer. Chỉ so sánh một tên đăng nhập hiển thị hoặc một `sub` không có ngữ cảnh issuer có thể nhận nhầm người.

## 6. Đặt điểm thực thi trong luồng nghiệp vụ

Một cấu trúc dễ kiểm soát là đặt policy tại lớp service/use case và bảo đảm các lối vào nghiệp vụ đều đi qua nó. Controller xử lý giao thức; policy quyết định quyền; repository giới hạn dữ liệu và thực thi các điều kiện truy vấn.

~~~mermaid
flowchart TD
    A[Nhận yêu cầu và mã đối tượng] --> B[Xác minh chủ thể và tenant]
    B --> C[Nạp metadata trong phạm vi tenant]
    C --> D[Xét quyền theo hành động và đối tượng]
    D -->|DENY| E[Phản hồi từ chối theo hợp đồng API]
    D -->|ALLOW| F[Đọc dữ liệu hoặc ghi với điều kiện nhất quán]
    F --> G[Chọn trường được trả và ghi audit]
    G --> H[Trả kết quả]
~~~

Với API đọc, có thể nạp metadata tối thiểu rồi xét quyền trước khi tải nội dung nhạy cảm. Không nên gửi dữ liệu cho client trước và kỳ vọng giao diện sẽ giấu nó.

Với API ghi, cần giữ quyết định phù hợp với trạng thái thực sự được sửa; việc kiểm tra quyền rồi để một khoảng trống tùy ý trước khi ghi là chưa đủ.

OWASP khuyến nghị quyền tối thiểu, từ chối mặc định, kiểm tra quyền trên mỗi yêu cầu và đặt kiểm tra ở vị trí phù hợp. Các nguyên tắc đó là cơ sở cho việc dùng một luồng thực thi có thể kiểm soát, thay vì chỉ ẩn nút trên giao diện. [Nguồn: OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Một API gateway có thể xác minh token hoặc scope, nhưng thường không có đủ dữ liệu về chủ sở hữu, trạng thái đơn và grant. Nếu ứng dụng quyết định phân quyền ở service, service phải thực thi quyết định đó cho cả HTTP, tác vụ nội bộ và các lối vào khác có cùng ngữ nghĩa.

## 7. Ví dụ Java: biểu diễn policy tường minh

Đoạn mã Java sau minh họa phần quyết định cho chính sách đơn hàng. Các `record` được tạo bởi mã server từ dữ liệu đã xác minh; việc một kiểu dữ liệu có tên “Context” không tự làm đầu vào của nó đáng tin cậy.

Ví dụ dùng cú pháp Java 17, không phụ thuộc framework. Nó không bao gồm bộ xác minh token, repository, xử lý transaction hoặc ánh xạ lỗi HTTP.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

final class OrderAccess {
    enum Action {
        READ, CANCEL, SHARE, TRANSFER
    }

    enum Permission {
        READ_ALL_ORDERS, CANCEL_ALL_ORDERS
    }

    enum State {
        DRAFT, PAID, CANCELLED
    }

    record SubjectContext(
        String subjectId,
        String activeTenantId,
        boolean activeMembership,
        Set<Permission> tenantPermissions
    ) {
        SubjectContext {
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(activeTenantId);
            tenantPermissions = Set.copyOf(tenantPermissions);
        }
    }

    record Order(
        String id,
        String tenantId,
        String ownerId,
        State state,
        long version
    ) {
        Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(ownerId);
            Objects.requireNonNull(state);
        }
    }

    record ReadGrant(
        String tenantId,
        String orderId,
        String subjectId,
        Instant expiresAt,
        boolean revoked
    ) {
        ReadGrant {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(expiresAt);
        }

        boolean matches(
            SubjectContext subject,
            Order order,
            Instant now
        ) {
            return !revoked
                && now.isBefore(expiresAt)
                && tenantId.equals(order.tenantId())
                && orderId.equals(order.id())
                && subjectId.equals(subject.subjectId());
        }
    }

    record Decision(boolean allowed, String reason) {
        static Decision allow(String reason) {
            return new Decision(true, reason);
        }

        static Decision deny(String reason) {
            return new Decision(false, reason);
        }
    }

    static Decision decide(
        SubjectContext subject,
        Action action,
        Order order,
        ReadGrant readGrant,
        Instant now
    ) {
        if (subject == null || action == null
                || order == null || now == null) {
            return Decision.deny("MISSING_INPUT");
        }

        if (!subject.activeMembership()) {
            return Decision.deny("INACTIVE_MEMBERSHIP");
        }

        if (!subject.activeTenantId().equals(order.tenantId())) {
            return Decision.deny("TENANT_MISMATCH");
        }

        boolean owner =
            subject.subjectId().equals(order.ownerId());

        return switch (action) {
            case READ -> {
                boolean readAll = subject.tenantPermissions()
                    .contains(Permission.READ_ALL_ORDERS);

                boolean shared = readGrant != null
                    && readGrant.matches(subject, order, now);

                yield owner || readAll || shared
                    ? Decision.allow("READ_PERMITTED")
                    : Decision.deny("NO_READ_RELATION");
            }

            case CANCEL -> {
                boolean cancelAll = subject.tenantPermissions()
                    .contains(Permission.CANCEL_ALL_ORDERS);

                yield order.state() == State.DRAFT
                        && (owner || cancelAll)
                    ? Decision.allow("CANCEL_PERMITTED")
                    : Decision.deny("CANCEL_NOT_PERMITTED");
            }

            default -> Decision.deny("ACTION_NOT_CONFIGURED");
        };
    }
}
~~~

Các lựa chọn thiết kế cần chú ý:

- Kiểm tra membership và tenant xảy ra trước mọi nhánh hành động.
- Grant khớp đồng thời người nhận, đơn hàng, tenant và thời hạn.
- Tại đúng `expiresAt`, grant không còn được chấp nhận vì kiểm tra dùng `isBefore`.
- Quyền đọc grant không xuất hiện trong nhánh `CANCEL`.
- `SHARE` và `TRANSFER` có tên trong mô hình nhưng chưa có quy tắc cho phép.
- `reason` phục vụ xử lý nội bộ; không nhất thiết trả nguyên văn cho người gọi.

Kiểu `Decision` giúp phân biệt một kết quả từ chối nghiệp vụ với lỗi hạ tầng. Nếu kho quyền bị lỗi, lớp gọi cần có hành vi đã định nghĩa; không được bắt ngoại lệ rồi tự chuyển thành `ALLOW`.

Ví dụ dùng snapshot đầu vào tại một thời điểm. Nếu ownership hoặc membership có thể thay đổi đồng thời, service phải bổ sung cơ chế nhất quán ở bước thực thi. Bản thân một hàm policy thuần không khóa dữ liệu và không thu hồi cache.

## 8. Truy vấn trong phạm vi được phép

### 8.1. Trường hợp đơn giản: chỉ chủ sở hữu được đọc

Khi chính sách thực tế chỉ cho chủ sở hữu đọc đơn trong tenant, truy vấn có thể ràng buộc cả ba thuộc tính:

~~~sql
SELECT id, state, created_at
FROM orders
WHERE tenant_id = :verified_tenant_id
  AND id = :requested_order_id
  AND owner_id = :verified_subject_id;
~~~

`requested_order_id` do client cung cấp. Hai giá trị `verified_*` được tạo ở phía server sau xác thực và kiểm tra membership.

Truy vấn trên chỉ minh họa **nhánh owner-only**. Nó không thể hiện đầy đủ chính sách có quyền đọc toàn tenant hoặc grant chia sẻ. Nếu doanh nghiệp hỗ trợ các nhánh đó, cần thêm điều kiện tương ứng; không nên vô tình làm mất chức năng hợp lệ trong quá trình vá lỗi quyền.

### 8.2. Truy vấn đọc cho chính sách của bài

Giả sử hệ thống lưu membership ở `tenant_memberships` và grant đọc ở `order_read_grants`, có thể biểu diễn chính sách đọc bằng SQL tham số hóa:

~~~sql
SELECT o.id, o.state, o.created_at
FROM orders o
WHERE o.tenant_id = :verified_tenant_id
  AND o.id = :requested_order_id
  AND EXISTS (
      SELECT 1
      FROM tenant_memberships m
      WHERE m.tenant_id = o.tenant_id
        AND m.subject_id = :verified_subject_id
        AND m.status = 'ACTIVE'
  )
  AND (
      o.owner_id = :verified_subject_id
      OR :server_can_read_all = TRUE
      OR EXISTS (
          SELECT 1
          FROM order_read_grants g
          WHERE g.tenant_id = o.tenant_id
            AND g.order_id = o.id
            AND g.subject_id = :verified_subject_id
            AND g.revoked = FALSE
            AND g.expires_at > :authorization_time
      )
  );
~~~

Đây là mẫu logic; cú pháp bind boolean và kiểu thời gian cần tương thích với driver và cơ sở dữ liệu được dùng.

`server_can_read_all` phải là quyền server đã giải quyết cho đúng tenant. Nó không được bind trực tiếp từ query parameter hoặc body. `authorization_time` cũng phải do server chọn.

Dùng `EXISTS` cho grant tránh nhân bản một đơn nếu dữ liệu có nhiều grant phù hợp. Những ràng buộc dữ liệu khác như khóa duy nhất, khóa ngoại và chỉ mục cần được thiết kế theo schema thật.

Khi policy tồn tại ở Java và SQL, hai biểu diễn có thể lệch nhau. Cần kiểm thử chúng trên cùng tập tình huống hoặc có cơ chế sinh predicate từ một nguồn chính sách phù hợp. “Tập trung policy” chỉ có ích khi mọi lối thực thi áp dụng cùng ý nghĩa.

### 8.3. Nạp đối tượng rồi kiểm tra cũng có thể hợp lệ

Không phải mọi chính sách đều chuyển thành một câu SQL đơn giản. Một service có thể:

~~~text
1. Lấy subject và tenant đã xác minh.
2. Nạp metadata của đơn trong tenant đó.
3. Nạp dữ liệu grant cần thiết.
4. Gọi policy cho đúng action.
5. Nếu DENY, dừng trước khi trả nội dung hoặc phát sinh tác dụng phụ.
6. Nếu ALLOW, thực hiện use case trong cơ chế nhất quán đã chọn.
7. Tạo DTO theo quyền trường và trả kết quả.
~~~

Điểm quyết định là dữ liệu không bị công bố hoặc thay đổi trái phép trong các bước trước khi có quyền. Tránh để `toString()`, log debug, sự kiện hoặc bước tải file làm lộ nội dung ngay khi đối tượng vừa được nạp.

## 9. Ràng buộc nhiều đối tượng và quan hệ cha–con

Quyền trên đối tượng cha không chứng minh rằng mọi mã con do client đưa vào đều thuộc đối tượng đó.

Xét endpoint:

~~~http
GET /api/projects/P-10/documents/D-88
~~~

Nếu server chỉ kiểm tra người dùng được đọc `P-10` rồi tải `D-88` bằng ID toàn cục, một tài liệu thuộc dự án khác có thể lọt vào kết quả.

Cần xác minh:

~~~text
subject được phép đọc P-10
AND D-88 thực sự thuộc P-10
AND tenant của hai đối tượng phù hợp
AND policy của D-88 cho phép hành động yêu cầu
~~~

Điều kiện cuối phụ thuộc mô hình kế thừa quyền. Nếu mọi tài liệu kế thừa quyền dự án thì cần áp dụng đúng quy tắc đó. Nếu tài liệu có mức hạn chế riêng, phải xét cả hạn chế riêng.

Tương tự, yêu cầu tạo một đối tượng mới cũng có các đối tượng hiện hữu cần bảo vệ:

~~~http
POST /api/projects/P-10/documents
Content-Type: application/json

{
  "folderId": "F-27",
  "title": "Báo cáo"
}
~~~

Chưa có document ID không có nghĩa chưa cần object-level authorization. Phải xét quyền tạo dưới `P-10`, quyền dùng `F-27` và quan hệ giữa folder với project. Những trường như tenant và owner mặc định cần được server gán theo chính sách.

Với chuyển một tài liệu giữa hai thư mục, có thể cần quyền lấy khỏi nguồn và đưa vào đích. Chỉ kiểm tra thư mục nguồn sẽ bỏ sót tài nguyên đích bị tác động.

## 10. Phân biệt quyền trên đối tượng với quyền sửa thuộc tính

Giả sử Alice được sửa địa chỉ giao hàng của đơn do mình sở hữu. Điều đó không cho phép request tự ý thay người sở hữu:

~~~json
{
  "shippingAddress": "Địa chỉ mới",
  "ownerId": "another-user",
  "tenantId": "another-tenant",
  "state": "PAID"
}
~~~

Nếu framework bind trực tiếp toàn bộ JSON vào entity và gọi `save`, quyền trên đối tượng có thể bị dùng để sửa các trường quản lý quyền hoặc trạng thái nghiệp vụ.

Một thiết kế cụ thể hơn là DTO dành cho đúng use case:

~~~java
record UpdateShippingAddressRequest(String shippingAddress) {}
~~~

Sau khi xét `UPDATE_SHIPPING_ADDRESS` theo chính sách thật, service chỉ cập nhật trường cho phép. Chuyển owner, chuyển tenant và đánh dấu đã thanh toán là những use case khác, cần quyền và điều kiện riêng.

Ở chiều trả dữ liệu, cũng nên chọn DTO/projection theo nhu cầu. Không serialize nguyên entity chứa thông tin nội bộ chỉ vì người dùng được đọc đơn.

Trong ví dụ Java trước, chưa có quy tắc `UPDATE_SHIPPING_ADDRESS`. Tên hành động ở phần này nhằm minh họa cách mở rộng use case; cần bổ sung policy tương ứng trước khi triển khai thực tế.

## 11. Danh sách, tìm kiếm, đếm và thao tác hàng loạt

### 11.1. Bộ lọc quyền cần tham gia truy vấn danh sách

API chi tiết đã an toàn nhưng API danh sách trả toàn bộ tenant vẫn có thể làm lộ dữ liệu.

Trong chính sách ví dụ, danh sách đơn của Alice phải bao gồm đúng tập đơn Alice được đọc: đơn sở hữu, đơn có grant còn hiệu lực và các đơn thuộc phạm vi quyền `READ_ALL_ORDERS` nếu quyền đó tồn tại.

Về mặt logic:

~~~text
visible_orders = filter(all_orders, can_read(subject, order))

result = paginate(sort(visible_orders))
total  = count(visible_orders)
~~~

Nếu ứng dụng phân trang toàn bộ dữ liệu rồi mới loại các đơn không có quyền, người dùng có thể thấy trang rỗng, tổng số sai hoặc dữ liệu về phạm vi ngoài quyền. Với truy vấn tìm kiếm, facet và tổng hợp, các số đếm cũng phải tuân theo phạm vi dữ liệu được phép biết.

Nếu kỹ thuật bắt buộc phải lọc sau do policy phức tạp, cần thiết kế thuật toán phân trang và metadata tương ứng, không giả định một lần `LIMIT` trên tập toàn cục vẫn cho kết quả đúng.

### 11.2. Không dùng quyền trên một phần tử cho cả batch

Ví dụ một yêu cầu:

~~~json
{
  "orderIds": ["O-101", "O-204", "O-309"]
}
~~~

Server cần xác định tập ID hợp lệ, nạp đúng đối tượng và xét hành động trên từng phần tử. Không được kiểm tra phần tử đầu tiên rồi cập nhật tất cả.

Hai hợp đồng có thể được chọn:

| Hợp đồng batch | Hành vi |
| --- | --- |
| Toàn bộ hoặc không phần tử nào | Một phần tử không đủ quyền làm toàn bộ thao tác thất bại và không để lại thay đổi |
| Kết quả từng phần tử | Chỉ thực hiện những phần tử hợp lệ và trả kết quả theo hợp đồng công khai đã định nghĩa |

Với hợp đồng toàn bộ, không được lần lượt ghi từng đơn rồi chỉ báo lỗi khi gặp đơn bị từ chối. Cần transaction hoặc cơ chế thực thi tương đương để đáp ứng tính toàn bộ.

Với kết quả từng phần tử, thông báo “đơn tồn tại nhưng của người khác” có thể tiết lộ sự tồn tại. API có thể dùng một lỗi công khai chung cho đối tượng không thấy hoặc không được phép, trong khi audit nội bộ vẫn lưu nguyên nhân phù hợp.

Cần quy định thêm cách xử lý ID trùng, ID không tồn tại, giới hạn kích thước batch và retry. Những quy định này giúp việc xét quyền có cùng ý nghĩa với số đối tượng thực sự bị tác động.

## 12. Trạng thái thay đổi giữa lúc kiểm tra và thực hiện

### 12.1. Khoảng trống TOCTOU

Xét diễn tiến sau:

~~~text
T1: Alice là owner của O-101, đơn đang DRAFT.
T2: Service kiểm tra CANCEL -> ALLOW.
T3: Một giao dịch khác chuyển đơn sang PAID.
T4: Service ghi state = CANCELLED mà không kiểm tra lại điều kiện.
~~~

Quyết định tại T2 đúng với snapshot cũ nhưng thao tác tại T4 vi phạm chính sách. Đây là một dạng khoảng trống **time of check to time of use — TOCTOU**.

Trường hợp tương tự có thể xảy ra khi owner đổi, grant bị thu hồi hoặc membership bị vô hiệu hóa.

### 12.2. Gắn điều kiện với thao tác ghi

Với riêng nhánh chủ sở hữu hủy đơn nháp, có thể dùng một lệnh cập nhật có điều kiện:

~~~sql
UPDATE orders
SET state = 'CANCELLED',
    version = version + 1
WHERE tenant_id = :verified_tenant_id
  AND id = :requested_order_id
  AND owner_id = :verified_subject_id
  AND state = 'DRAFT'
  AND version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM tenant_memberships m
      WHERE m.tenant_id = orders.tenant_id
        AND m.subject_id = :verified_subject_id
        AND m.status = 'ACTIVE'
  );
~~~

Mẫu này cố ý chỉ mô tả nhánh owner của `CANCEL`. Muốn hỗ trợ `CANCEL_ALL_ORDERS` cần đưa nhánh đó vào thiết kế thực thi và bảo đảm quyền được lấy từ nguồn phù hợp.

Service phải kiểm tra số hàng cập nhật. Không có hàng được cập nhật không đồng nghĩa thành công; có thể đơn không thuộc phạm vi, đã đổi phiên bản hoặc không còn ở trạng thái phù hợp.

`version` chỉ phát hiện các thay đổi có tham gia cùng cơ chế phiên bản. Nếu ownership được cập nhật nhưng code không tăng version, việc so sánh version không bảo vệ được thay đổi đó.

### 12.3. Transaction không tự giải quyết mọi thu hồi đồng thời

Một câu lệnh có `EXISTS` kiểm tra membership vẫn chịu quy tắc snapshot và đồng thời của cơ sở dữ liệu. Nó không tự bảo đảm một lệnh thu hồi membership ở giao dịch khác luôn thắng thao tác đang chạy.

Cần định nghĩa ý nghĩa nghiệp vụ, ví dụ:

- Yêu cầu đã được cho phép trước khi thu hồi có được hoàn tất không?
- Hay mọi thao tác chưa commit đều phải bị chặn nếu thu hồi được chốt trước?
- Điểm nào được coi là thời điểm có hiệu lực của thay đổi quyền?

Nếu cần bảo đảm mạnh hơn, thiết kế phải phối hợp việc khóa hoặc kiểm tra phiên bản dữ liệu quyền, thứ tự giao dịch và xử lý retry phù hợp với cơ sở dữ liệu. Chỉ thêm `@Transactional` mà không xem mức cô lập và quy trình cập nhật quyền chưa đủ để khẳng định hết race condition.

Với thao tác phát sinh tác dụng phụ bên ngoài như gửi lệnh thanh toán, cần gắn quyền với bước tạo lệnh có kiểm soát. Rollback cơ sở dữ liệu không tự thu hồi một yêu cầu đã gửi sang hệ thống khác.

## 13. Cache và vòng đời quyền truy cập

Cache dữ liệu và cache quyết định quyền có mục đích khác nhau.

Ứng dụng có thể cache nội dung đơn theo khóa đủ phân biệt tenant và order, nhưng mỗi lần sử dụng vẫn cần kiểm tra quyền phù hợp với chủ thể. Một đối tượng được cache do Alice đọc không được tự động trở thành dữ liệu Bob được đọc.

Với cache quyết định, khóa chỉ có `orderId` là thiếu. Tùy mô hình, cần bao gồm chủ thể, tenant, action, phiên bản policy, phiên bản dữ liệu quyền và các yếu tố ngữ cảnh liên quan.

Ví dụ về những thay đổi phải được xem xét:

| Sự kiện | Quyết định cũ có thể sai ở đâu? |
| --- | --- |
| Thu hồi grant chia sẻ | Cache `READ = ALLOW` còn tồn tại |
| Đổi chủ sở hữu | Owner cũ tiếp tục đọc hoặc hủy |
| Gỡ thành viên khỏi tenant | Membership cũ vẫn được chấp nhận |
| Đổi đơn từ `DRAFT` sang `PAID` | Cache hủy đơn tiếp tục cho phép |
| Thay policy | Kết quả lưu theo phiên bản policy cũ vẫn được dùng |

Trong ví dụ của bài, grant có thời điểm hết hạn. Cache một kết quả cho phép từ grant không nên tiếp tục dùng sau thời điểm đó. Tuy nhiên, giảm TTL đến `expiresAt` chỉ xử lý hết hạn theo lịch; nó không tự giải quyết thu hồi sớm.

Cần có mục tiêu rõ ràng về độ trễ thu hồi và cơ chế đáp ứng mục tiêu đó. Với thao tác nhạy cảm, có thể cần đọc lại dữ liệu quyền ở bước thực thi thay vì chấp nhận cache cũ.

Không có cache nào ngăn người dùng tiếp tục giữ một bản sao đã được phép tải trước đó. Thu hồi quyền điều khiển những lần truy cập hoặc thao tác tiếp theo trong phạm vi hệ thống kiểm soát.

## 14. Tác vụ nền, workload identity và đường tải file

### 14.1. Tác vụ nền không mặc nhiên có quyền của người yêu cầu

Giả sử Alice được phép xuất báo cáo lúc tạo job. Đến lúc worker chạy, Alice đã mất membership. Nếu yêu cầu nghiệp vụ là quyền phải còn hiệu lực khi xuất, kiểm tra ở thời điểm tạo job là chưa đủ.

Đối với một job được thực hiện thay người dùng, cần lưu thông tin yêu cầu tối thiểu như:

~~~text
requestedBy
tenantId
requestedAction
resourceSelection
requestedAt
~~~

Các thông tin đó phải do server ghi, được bảo vệ khỏi sửa trái phép và được xác minh theo thiết kế khi thực thi.

Worker có danh tính workload để kết nối kho dữ liệu. Danh tính đó trả lời worker nào đang chạy; nó không tự chứng minh Alice có quyền đọc mọi dữ liệu worker có thể truy cập.

Có thể thiết kế hai loại công việc khác nhau:

- Job thay người dùng: áp dụng quyền của người yêu cầu theo thời điểm và quy tắc đã công bố.
- Job hệ thống: áp dụng policy riêng cho workload, tenant và phạm vi công việc được ủy nhiệm.

Không tự chuyển loại thứ nhất thành loại thứ hai chỉ vì tài khoản dịch vụ có quyền cơ sở dữ liệu rộng.

File xuất ra cũng là tài nguyên cần bảo vệ. API tải kết quả phải xét quyền trên job hoặc file phù hợp; đoán được `jobId` không được trở thành cách tải báo cáo của người khác.

### 14.2. Liên kết tải có chữ ký cần hợp đồng riêng

Nếu ứng dụng cấp một signed URL cho file, endpoint cấp URL phải xác minh quyền trên đúng file. Sau khi phát hành, khả năng sử dụng URL phụ thuộc cơ chế của nơi phục vụ file.

Trong nhiều thiết kế, ai sở hữu URL hợp lệ đều có thể tải file đến khi URL hết hiệu lực. Vì vậy cần xác định rõ thời hạn, phương thức, tài nguyên đích và cơ chế thu hồi mà hệ thống thực sự hỗ trợ. Không được khẳng định URL tự bị vô hiệu hóa ngay khi grant trong ứng dụng bị thu hồi.

Nếu yêu cầu là xét quyền hiện tại ở mỗi lần tải, có thể cần cho luồng tải đi qua điểm thực thi quyền, hoặc một cơ chế xác minh khác đáp ứng yêu cầu đó.

Cũng cần kiểm tra cả đường dẫn thumbnail, bản xem trước và tệp đính kèm. Bảo vệ API metadata nhưng để nội dung tương ứng công khai vẫn làm mất ý nghĩa của quyền ở mức đối tượng.

## 15. Phản hồi lỗi và audit

### 15.1. Chọn phản hồi công khai có chủ đích

Với một API yêu cầu xác thực:

- Thiếu hoặc không có thông tin xác thực hợp lệ thường được xử lý theo luồng authentication, chẳng hạn `401`.
- Chủ thể đã được xác thực nhưng không được thực hiện yêu cầu có thể nhận `403`.
- Nếu cần giấu sự tồn tại của tài nguyên bị cấm, server có thể dùng `404` theo hợp đồng API.

RFC 9110 cho phép dùng `404` để không công bố sự tồn tại của một tài nguyên bị cấm. Điều đó không bắt buộc mọi lỗi quyền phải trả `404`. [Nguồn: RFC 9110, mục 15.5.4–15.5.5](https://www.rfc-editor.org/rfc/rfc9110.html#name-403-forbidden).

Nếu đã chọn giấu sự tồn tại, cần xem xét cả response body, header, metadata và các endpoint liên quan. Trả `404` nhưng ghi “đơn thuộc Bob” trong body vẫn tiết lộ dữ liệu.

Phản hồi dữ liệu nhạy cảm và phản hồi từ chối cũng cần chính sách cache HTTP phù hợp. Một lớp cache dùng chung không được tái sử dụng kết quả của Alice cho Bob chỉ vì họ gọi cùng URL.

### 15.2. Audit nội bộ giữ đủ ngữ cảnh quyết định

Một sự kiện audit có thể chứa:

~~~text
actorSubjectId
callingWorkloadId
tenantId
resourceType
resourceId
action
decision
internalReason
policyVersion
requestId
occurredAt
~~~

`actorSubjectId` và `callingWorkloadId` giúp phân biệt người yêu cầu với service đang thực hiện thay họ.

Không cần log toàn bộ đơn hàng, token hoặc nội dung file để chứng minh đã xét quyền. ID tài nguyên và thông tin định danh trong audit cũng cần kiểm soát truy cập, thời hạn lưu và mục đích sử dụng.

Khi phát hiện nhiều lần từ chối liên tiếp trên các ID khác nhau, đội vận hành có thể điều tra hành vi dò tìm. Đây là khả năng quan sát bổ sung; nó không thay thế việc chặn yêu cầu trái phép ngay tại điểm thực thi.

## 16. Ma trận kiểm thử cho chính sách ví dụ

Chuẩn bị dữ liệu trong môi trường kiểm thử được phép:

~~~text
Tenant A:
    Alice: thành viên active, không có quyền toàn tenant
    Bob: thành viên active, không có quyền toàn tenant
    Reader: thành viên active, có READ_ALL_ORDERS
    Operator: thành viên active, có CANCEL_ALL_ORDERS

Tenant B:
    Carol: thành viên active

O-101: tenant A, owner Alice, DRAFT
O-102: tenant A, owner Alice, PAID
O-204: tenant A, owner Bob, DRAFT
O-309: tenant B, owner Carol, DRAFT
~~~

Theo policy đã định nghĩa:

| Chủ thể và điều kiện | Đối tượng | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| Alice | `O-101` | `READ` | Cho phép |
| Alice | `O-101` | `CANCEL` | Cho phép |
| Alice | `O-102` | `CANCEL` | Từ chối vì trạng thái |
| Alice, chưa được chia sẻ | `O-204` | `READ` | Từ chối |
| Alice, có grant đọc còn hiệu lực | `O-204` | `READ` | Cho phép |
| Alice, chỉ có grant đọc | `O-204` | `CANCEL` | Từ chối |
| Alice, grant vừa hết hạn | `O-204` | `READ` | Từ chối |
| Alice, grant bị thu hồi | `O-204` | `READ` | Từ chối |
| Reader trong tenant A | `O-204` | `READ` | Cho phép |
| Reader trong tenant A | `O-204` | `CANCEL` | Từ chối |
| Operator trong tenant A, không có grant đọc | `O-204` | `READ` | Từ chối |
| Operator trong tenant A | `O-204` | `CANCEL` | Cho phép |
| Reader trong tenant A | `O-309` | `READ` | Từ chối vì tenant |
| Alice, membership không còn active | `O-101` | `READ` | Từ chối |
| Alice | `O-101` | `SHARE` | Từ chối vì chưa cấu hình action |

Ngoài kiểm thử hàm policy, cần kiểm thử tích hợp để chứng minh endpoint và luồng dữ liệu thật đều thực thi nó:

1. Đổi mã đơn trong path, query hoặc body phải được xét quyền lại.
2. Gửi `ownerId` hoặc tenant khác trong body không được sửa quyền của đối tượng.
3. API danh sách và tổng số không bao gồm dữ liệu ngoài phạm vi.
4. Request batch trộn đơn được phép và không được phép phải tuân thủ đúng hợp đồng đã chọn.
5. Nối một parent hợp lệ với child thuộc parent khác phải bị chặn.
6. Tải file xuất của chủ thể khác phải bị từ chối.
7. Grant hết hạn tại đúng ranh giới thời gian phải cho kết quả đã định nghĩa.
8. Thay owner, trạng thái hoặc membership trong tình huống đồng thời phải tuân thủ bảo đảm nhất quán đã chọn.
9. Cache được làm nóng bởi người A không được làm người B có thêm quyền.
10. Không có side effect thành công khi hành động đã bị từ chối.

Các test về từ chối cần kiểm tra trạng thái dữ liệu và tác dụng phụ, không chỉ mã HTTP. Một endpoint trả lỗi sau khi đã cập nhật đơn vẫn vi phạm yêu cầu.

Ma trận trên là nội dung thiết kế để người học áp dụng. Nó không phải báo cáo rằng ví dụ trong tài liệu đã được chạy trên một ứng dụng thật.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Cách diễn đạt chính xác hơn |
| --- | --- |
| Có token hợp lệ là được xem đơn | Token cung cấp thông tin chủ thể; còn phải xét quyền trên đơn |
| Có `orders:read` là được đọc mọi đơn | Phạm vi đối tượng phụ thuộc hợp đồng quyền của hệ thống |
| UUID đã chặn IDOR | Vẫn cần policy khi người gọi biết ID |
| Cùng tenant là đủ | Trong tenant vẫn có giới hạn sở hữu, chia sẻ và hành động |
| Owner luôn có mọi quyền | Quyền owner là quy tắc nghiệp vụ phải định nghĩa |
| Đọc được thì được sửa hoặc chia sẻ | Mỗi action cần điều kiện phù hợp |
| Controller đã kiểm tra nên background job được bỏ qua | Mỗi lối thực thi cần policy đúng với danh tính và công việc của nó |
| Chỉ cần bỏ qua trường nhạy cảm khi trả JSON | Còn phải giới hạn đối tượng được truy cập và trường được sửa |
| Có transaction là hết race | Cần cơ chế nhất quán cho đúng dữ liệu và thay đổi quyền liên quan |
| Dùng `404` là đủ bảo mật | Nội dung, metadata, cache và endpoint khác vẫn phải đúng quyền |

## 18. Bài tập vận dụng

Một hệ thống quản lý tài liệu có người sở hữu, nhóm được chia sẻ và quản trị viên tenant. Tài liệu có thể ở trạng thái `DRAFT` hoặc `LOCKED`.

Hãy tự định nghĩa chính sách cho bốn hành động `READ`, `EDIT`, `SHARE` và `MOVE`. Với mỗi hành động, xác định:

- Dữ liệu nào cần lấy từ danh tính đã xác minh?
- Những thuộc tính và quan hệ nào thuộc nguồn dữ liệu server?
- Trạng thái `LOCKED` ảnh hưởng đến hành động nào?
- Quyền quản trị viên có vượt giới hạn tenant không?
- Khi di chuyển tài liệu, cần kiểm tra quyền trên thư mục nguồn và đích như thế nào?
- Nếu quyền chia sẻ bị thu hồi trong lúc job xuất đang đợi, hệ thống phải xử lý ra sao?

Một đáp án tốt không chỉ có tên role. Nó mô tả được chủ thể, hành động, đối tượng, ranh giới tenant, quan hệ có hiệu lực và thời điểm kiểm tra; sau đó chuyển các điều kiện đó thành những trường hợp cho phép và từ chối có thể kiểm chứng.
