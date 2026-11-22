# Permission naming — Đặt tên quyền theo đúng ý nghĩa nghiệp vụ

## 1. Tên quyền là một phần của hợp đồng bảo mật

**Permission naming** là việc đặt mã định danh ổn định cho một khả năng được cấp phép, sao cho người thiết kế, lập trình viên, người cấp quyền và người điều tra hiểu thống nhất hành động mà mã đó đại diện.

Tên quyền không chỉ để hiển thị trên màn hình quản trị. Nó xuất hiện trong policy, role, token, cấu hình, code kiểm tra quyền và audit. Một mã mơ hồ có thể khiến cùng một nhóm người được quyền nhiều hơn dự định mà không có thay đổi rõ ràng ở giao diện cấp quyền.

Ví dụ, hệ thống ban đầu dùng `ORDER_WRITE` để sửa đơn nháp. Sau đó lập trình viên dùng lại mã này cho chức năng phê duyệt vì “đều là cập nhật đơn”. Tất cả người đang được sửa nháp có thể vô tình được phê duyệt. Lỗi nằm ở ngữ nghĩa và cách sử dụng quyền, không phải chỉ ở việc viết hoa hay dùng dấu phân cách nào.

Bài thuộc chương **Permission Semantics** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Mục tiêu là đặt tên quyền giúp bảo vệ quy tắc nghiệp vụ trước sửa giá, bỏ qua bước phê duyệt, thao tác sai quyền và thực hiện yêu cầu trùng. Mã quyền phải làm rõ hành động; quyền trên đối tượng, state machine, transaction và idempotency vẫn cần được thực thi riêng.

Sau bài học, người học cần phân biệt được mã quyền với role và grant, xây dựng một quy ước tên có giới hạn rõ ràng, tránh suy diễn quyền từ chuỗi ký tự và biết cách đổi tên/tách quyền mà không âm thầm mở rộng đặc quyền.

## 2. Phân biệt permission, role, grant, scope và policy

| Khái niệm | Ví dụ | Điều nó biểu diễn |
| --- | --- | --- |
| Permission code | `procurement.purchase_order.approve` | Loại hành động được xét cấp phép |
| Role | `PURCHASING_REVIEWER` | Một tập quyền phục vụ một vai trò công việc |
| Grant hoặc role binding | Cấp quyền phê duyệt cho An trong project P1 | Ai được dùng quyền, trong phạm vi và điều kiện nào |
| Resource scope | Tenant T1, project P1 hoặc một đơn cụ thể | Tập tài nguyên mà grant bao phủ |
| Constraint | Hạn mức, thời hạn, yêu cầu xác thực | Điều kiện giới hạn một grant hoặc quyết định |
| Policy | Reviewer không được duyệt đơn do mình tạo | Quy tắc đánh giá đầy đủ để cho phép/từ chối |
| Display label | “Phê duyệt đơn mua hàng” | Nhãn cho con người đọc, có thể dịch theo ngôn ngữ |

Không dùng `ADMIN` làm mã quyền cho mọi hành động chỉ vì đã có một role quản trị. Cũng không dùng tên quyền để thay thế toàn bộ policy, chẳng hạn cho rằng một người có mã `approve` thì luôn được duyệt mọi đơn.

Một phép kiểm tra hoàn chỉnh có thể có dạng:

```text
Có mã quyền phù hợp trong một grant có hiệu lực
    AND grant bao phủ đúng tenant và tài nguyên
    AND điều kiện của grant được thỏa mãn
    AND invariant nghiệp vụ không bị vi phạm
    => mới có cơ sở cho phép hành động.
```

### 2.1. Mã máy ổn định, nhãn hiển thị có thể thay đổi

Mã quyền nên là định danh có kiểm soát, không phụ thuộc bản dịch hoặc tên nút hiện tại. Ví dụ mã giữ nguyên, còn nhãn tiếng Việt có thể đổi từ “Duyệt đơn” thành “Phê duyệt đề nghị mua hàng” để diễn đạt rõ hơn.

Không dùng nhãn do quản trị viên nhập hoặc chuỗi được dịch ở frontend để làm khóa kiểm tra quyền. Hai nhãn giống nhau không có nghĩa hai quyền tương đương; đổi tên một nút cũng không tự làm thay đổi hợp đồng cấp phép.

### 2.2. OAuth scope không mặc nhiên là permission nội bộ

Scope của access token có thể được ánh xạ tới permission nội bộ, nhưng quan hệ đó phải được thiết kế. Không mặc định mọi chuỗi trong một claim bất kỳ đều là quyền mà resource service hiểu và tin cậy.

RFC 6749 định nghĩa giá trị scope là danh sách các chuỗi phân biệt hoa/thường, phân cách bằng dấu cách và được authorization server định nghĩa. Nó không quy định một từ như `write` trong hệ thống của bạn phải cho phép những hành động nghiệp vụ nào. [RFC 6749, mục 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3).

Việc ánh xạ còn phải gắn với issuer, bên nhận token và ngữ cảnh tin cậy phù hợp. Một mã trùng tên trong token của hệ thống khác không tự có cùng thẩm quyền.

## 3. Chọn cấu trúc tên dựa trên nghiệp vụ

### 3.1. Một quy ước minh họa

Trong bài dùng quy ước:

```text
<business_namespace>.<resource_type>.<action>

procurement.purchase_order.read
procurement.purchase_order.edit_draft
procurement.purchase_order.submit
procurement.purchase_order.approve
```

Đây là quy ước thiết kế của ví dụ, không phải chuẩn bắt buộc cho mọi framework hoặc sản phẩm.

Các quy tắc cú pháp được chọn:

- Có đúng ba thành phần, ngăn bằng dấu chấm.
- Dùng chữ ASCII thường, chữ số và dấu gạch dưới bên trong từng thành phần.
- Dùng tên loại tài nguyên ở số ít: `purchase_order`.
- Action là động từ hoặc cụm động từ có nghĩa nghiệp vụ rõ ràng.
- Không có khoảng trắng, dấu wildcard hoặc ID tài nguyên trong mã canonical.
- So khớp chính xác, phân biệt hoa/thường; chỉ chấp nhận mã đã đăng ký.

Có thể chọn dấu `:` hoặc cấu trúc khác nếu hệ thống đã có quy ước. Điều quan trọng là cú pháp có một cách diễn giải nhất quán và ngữ nghĩa không thay đổi theo người viết kiểm tra.

### 3.2. Namespace thể hiện miền nghiệp vụ ổn định

`procurement` cho biết mã thuộc miền mua sắm. Nó không cần chứa tên pod, repository, package Java hoặc service triển khai hiện tại.

Nếu một microservice được tách thành hai service, việc quyền `approve` của miền mua sắm còn giữ nguyên ý nghĩa không nên buộc toàn bộ grant phải đổi tên. Ngược lại, hai miền có cùng từ `approve` nhưng tác dụng khác nhau cần namespace hoặc resource type đủ rõ để tránh đụng mã.

### 3.3. Đặt tên theo action, không theo thao tác HTTP

Một request `POST` có thể tạo nháp, gửi duyệt, phê duyệt hoặc hủy. Dùng `POST_ORDER` không giúp biết hành động nào được cấp phép.

Tương tự, một màn hình có thể gọi nhiều endpoint. Quyền `page_order_detail` không nên vô tình cho phép mọi mutation xuất phát từ màn hình đó. Nếu cần quyền điều hướng UI, phải phân biệt nó với quyền thực thi nghiệp vụ phía server.

## 4. Tách các hành động có rủi ro và trách nhiệm khác nhau

### 4.1. Danh mục minh họa cho đơn mua hàng

| Mã quyền | Khả năng có thể được cấp | Không được tự suy ra |
| --- | --- | --- |
| `procurement.purchase_order.read` | Đọc representation cơ sở được policy cho phép | Đọc mọi field nhạy cảm hoặc mọi đơn |
| `procurement.purchase_order.read_sensitive_fields` | Bổ sung quyền đọc một nhóm field nhạy cảm đã định nghĩa | Quyền đọc object gốc hoặc export toàn bộ dữ liệu |
| `procurement.purchase_order.create` | Tạo đề nghị trong phạm vi được cấp | Tạo thay mọi người hoặc tự phê duyệt |
| `procurement.purchase_order.edit_draft` | Sửa các trường được phép ở bản nháp | Sửa nội dung đã được duyệt hoặc đổi trạng thái tùy ý |
| `procurement.purchase_order.submit` | Gửi bản hợp lệ vào quy trình duyệt | Quyết định kết quả phê duyệt |
| `procurement.purchase_order.approve` | Thực hiện action chấp thuận khi đủ điều kiện | Sửa giá, tự duyệt hoặc duyệt mọi tenant |
| `procurement.purchase_order.reject` | Ghi quyết định từ chối hợp lệ | Quyền sửa hoặc hủy đối tượng theo action khác |
| `procurement.purchase_order.cancel_pending` | Hủy trong giai đoạn chờ theo policy | Hủy một đơn đã được phê duyệt/thực thi |
| `procurement.purchase_order.amend_approved` | Khởi tạo/thực hiện quy trình chỉnh sửa sau duyệt được định nghĩa | Giữ nguyên hiệu lực phê duyệt cho nội dung mới |
| `procurement.purchase_order.export` | Yêu cầu xuất dữ liệu trong phạm vi cho phép | Vượt phạm vi đọc hoặc xuất thêm field nhạy cảm |

Trong quy ước này, `read_sensitive_fields` là quyền bổ sung: đọc field nhạy cảm còn cần `read` trên cùng tài nguyên và policy field phù hợp. `export` cũng cần giao với phạm vi đọc/xuất của các tài nguyên liên quan. Không dựa vào hình dạng tên để suy ra các quan hệ đó.

### 4.2. “Write” thường che nhiều hành động khác nhau

`write`, `manage`, `process`, `handle` hoặc `full_access` có thể phù hợp với một khả năng thật sự được định nghĩa rộng. Tuy nhiên, nếu không mô tả rõ, chúng dễ gom chung các trách nhiệm đáng lẽ phải tách.

Đối với quy trình phê duyệt, ít nhất cần phân biệt các ý định như:

```text
Tạo hoặc sửa đề nghị
    -> Gửi vào quy trình
    -> Chấp thuận hoặc từ chối
    -> Thực thi tác dụng được cho phép
```

Có quyền yêu cầu hoàn tiền không đồng nghĩa được duyệt hoặc thực hiện hoàn tiền. Có quyền chỉnh đơn nháp không đồng nghĩa được duyệt đơn. Chỉ dùng tên `write` ở tất cả các bước sẽ làm việc phân tách trách nhiệm khó kiểm tra.

### 4.3. Không biến tên thành bản sao của mọi điều kiện động

Các tên như `approve_under_100m_in_pending_before_5pm` đưa nhiều dữ kiện thay đổi vào mã định danh. Chúng tạo ra danh mục phình to và khó bảo trì khi hạn mức hoặc giờ làm việc thay đổi.

Trong ví dụ, `approve` là capability ổn định; hạn mức, tiền tệ, phạm vi tài nguyên và thời hạn nằm ở grant/policy. `edit_draft` được tách riêng vì đó là khả năng nghiệp vụ mà quản trị viên cần cấp khác với chỉnh sửa sau duyệt.

Tiêu chí là: hai hành động có cần được cấp, thu hồi hoặc kiểm toán độc lập hay không? Nếu có, thường cần hai quyền hoặc hai khả năng được mô tả rõ. Nếu chỉ khác giá trị một tham số giới hạn, thường nên dùng constraint có kiểu dữ liệu và ý nghĩa xác định.

## 5. Tách mã quyền khỏi phạm vi và điều kiện cấp

### 5.1. Không nhét resource ID vào danh mục quyền

Tránh sinh mã như:

```text
procurement.purchase_order.approve_order_123
procurement.purchase_order.approve_tenant_t1
```

Chúng trộn loại khả năng với một lần cấp cụ thể. Danh mục sẽ tăng theo số tài nguyên và khó xác định hai grant có cùng ngữ nghĩa hay không.

Một grant có cấu trúc minh họa:

```json
{
  "permission_code": "procurement.purchase_order.approve",
  "principal_id": "reviewer-an",
  "scope": {
    "type": "PROJECT",
    "tenant_id": "tenant-t1",
    "project_id": "project-p1"
  },
  "constraints": {
    "max_amount_minor_units": 100000000,
    "currency": "VND"
  },
  "valid_until": "2026-12-01T00:00:00Z"
}
```

Đây là dữ liệu ví dụ, không phải payload mà client được tự gửi để cấp quyền cho mình. Operation quản lý grant phải xác minh quyền của người cấp và các giới hạn được phép cấp.

`scope` ở đây là phạm vi tài nguyên của grant nội bộ, khác với trường `scope` dạng chuỗi trong OAuth. Dùng cùng một từ không có nghĩa hai cấu trúc tự động thay thế cho nhau.

### 5.2. Các điều kiện phải thuộc cùng một grant phù hợp

Giả sử một người có:

| Grant | Permission | Phạm vi | Hạn mức |
| --- | --- | --- | --- |
| G1 | `procurement.purchase_order.approve` | Project A | 500 triệu VND |
| G2 | `procurement.purchase_order.approve` | Project B | 50 triệu VND |

Người đó không được dùng G1 lấy hạn mức 500 triệu rồi dùng G2 lấy phạm vi B để duyệt đơn 200 triệu ở B. Cùng mã permission không cho phép ghép tùy ý các mảnh điều kiện có lợi từ nhiều grant.

Với mô hình grant cho phép của ví dụ:

```text
Có ít nhất một grant mà đồng thời:
    permission khớp chính xác
    AND chủ thể/phạm vi khớp
    AND thời gian còn hiệu lực
    AND toàn bộ constraint của grant được thỏa mãn.

Ngoài ra, tất cả invariant bắt buộc của action vẫn phải đúng.
```

Nếu hệ thống hỗ trợ explicit deny, phải định nghĩa cách kết hợp deny và allow của engine đó. Không mặc định mọi sản phẩm có cùng quy tắc ưu tiên, cũng không suy ra cách kết hợp từ một tiền tố tên quyền.

### 5.3. “Own” phải có nghĩa nghiệp vụ xác định

Một quyền như `edit_own` chỉ rõ hơn `edit` khi tài liệu định nghĩa “own” là gì: người tạo, người đứng tên yêu cầu, người đang phụ trách hay một quan hệ khác.

Đổi owner hiện tại không được vô tình xóa lịch sử requester–reviewer. Trong nhiều trường hợp nên giữ mã capability ổn định và biểu diễn quan hệ `REQUESTER` hoặc một loại scope có ngữ nghĩa rõ trong grant/policy.

Nếu vẫn dùng `own` và `any` như hai khả năng độc lập, phải ghi rõ phạm vi của `any`. Nó có thể là mọi tài nguyên trong project được cấp, không mặc nhiên là mọi tenant trên hệ thống.

## 6. So khớp tên chính xác và không suy diễn quyền ngầm

### 6.1. Không dùng substring hoặc prefix thay cho permission check

```java
// Sai: quyền có tên chứa chuỗi này chưa chắc là quyền cần kiểm tra.
boolean allowed = authorityText.contains("purchase_order.approve");

// Sai nếu chưa định nghĩa rõ một mô hình wildcard/hierarchy an toàn.
boolean allowedByPrefix = grantedCode.startsWith("procurement.purchase_order");
```

Các mã `approve`, `approve_comment` và `approve_override` không mặc nhiên tương đương. Một chuỗi do bên ngoài cung cấp có chứa tên mong muốn cũng không trở thành grant hợp lệ.

So khớp mã canonical bằng equality sau khi nguồn cấp quyền đã được xác minh. Mã có đúng cú pháp nhưng không có trong registry vẫn là mã không được biết, không được tự cấp nghĩa.

### 6.2. Dấu phân cách không tạo ra quan hệ kế thừa

Theo quy ước trong bài:

```text
procurement.purchase_order.approve
    không tự bao hàm procurement.purchase_order.read
    không tự bao hàm procurement.purchase_order.reject
    không tự bao hàm procurement.purchase_order.edit_draft.
```

Role reviewer nếu cần cả đọc, approve và reject thì liệt kê các quyền tương ứng. Một quan hệ implication nếu cần phải được đăng ký và kiểm thử rõ, giữ đúng scope/constraint khi suy ra quyền. Không tạo hierarchy chỉ bằng `split(".")` hoặc độ dài chuỗi.

### 6.3. Wildcard có thể cấp cả hành động chưa tồn tại hôm nay

Quy ước canonical của ví dụ không cho phép `*`. Nếu tầng role/policy khác hỗ trợ wildcard, cần xác định nó bao gồm quyền tương lai hay chỉ một tập đã chốt.

Ví dụ `procurement.purchase_order.*` hôm nay có thể gồm read và sửa nháp; khi thêm action mới nhạy cảm, người có wildcard có thể nhận thêm quyền mà không qua một lần cấp riêng. Tài liệu Kubernetes RBAC nêu cụ thể rủi ro wildcard tự bao phủ resource/subresource/verb mới trong mô hình của Kubernetes. Đây là ví dụ về tác động của semantics wildcard, không phải quy tắc chung cho mọi engine. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Một cách vô tình tạo wildcard trong code Java là dùng `EnumSet.allOf(Permission.class)` để xây role nghiệp vụ thông thường. Thêm enum mới sẽ thay đổi role đó. Các bundle quyền nghiệp vụ nên có danh sách rõ hoặc cơ chế quản lý thay đổi tương đương.

### 6.4. Không “sửa hộ” mọi chuỗi gần giống

Với quy ước canonical được chọn, không tự trim khoảng trắng, đổi mọi dấu `:` thành `.`, chuyển chữ hoa thành chữ thường hoặc ánh xạ mọi từ gần nghĩa tại nhiều service khác nhau.

Những bước chuẩn hóa không thống nhất có thể làm nơi cấp quyền và nơi kiểm tra hiểu khác nhau. Nếu cần hỗ trợ tên cũ, dùng bảng alias có kiểm soát, mục tiêu rõ và thời hạn chuyển đổi, thay vì sửa chuỗi tùy ý.

Các ký tự Unicode nhìn giống chữ ASCII cũng không được chấp nhận như cùng một mã. Dùng nhãn hiển thị đa ngôn ngữ cho con người; mã máy canonical tuân tập ký tự đã chọn.

## 7. Quản lý danh mục quyền như một hợp đồng có chủ sở hữu

### 7.1. Tên cần đi cùng định nghĩa

Một entry registry minh họa:

```yaml
code: procurement.purchase_order.approve
displayNameVi: Phê duyệt đơn mua hàng
resourceType: PURCHASE_ORDER
action: APPROVE
semanticsVersion: 1
owner: procurement
status: ACTIVE
grantableScopes:
  - PROJECT
  - RESOURCE
description: >-
  Cho phép yêu cầu ghi quyết định chấp thuận trên đơn nằm trong scope
  của grant, khi mọi điều kiện authorization và nghiệp vụ đều đạt.
doesNotImply:
  - procurement.purchase_order.edit_draft
  - procurement.purchase_order.reject
requiredPolicies:
  - resource_scope_match
  - independent_reviewer
  - current_reviewed_content
  - approval_limit
  - valid_source_state
```

Đây là hợp đồng minh họa. Các tên trong `requiredPolicies` là tham chiếu thiết kế; viết chúng vào YAML không làm engine tự thực thi nếu không có implementation và kiểm tra tương ứng.

Registry nên giúp xác định mã duy nhất, chủ sở hữu định nghĩa, trạng thái vòng đời, phạm vi được cấp, tác dụng cho phép và những điều không được suy ra. Không chỉ có một danh sách tên mà mỗi service tự giải thích.

### 7.2. Kiểu dữ liệu Java giúp tránh lỗi chuỗi rải rác

Ví dụ một tập con của registry được biểu diễn bằng enum:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public enum Permission {
    ORDER_READ("procurement.purchase_order.read"),
    ORDER_EXPORT("procurement.purchase_order.export"),
    ORDER_EDIT_DRAFT("procurement.purchase_order.edit_draft"),
    ORDER_SUBMIT("procurement.purchase_order.submit"),
    ORDER_APPROVE("procurement.purchase_order.approve"),
    ORDER_REJECT("procurement.purchase_order.reject");

    private final String code;

    Permission(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    private static final Map<String, Permission> BY_CODE =
        Arrays.stream(values()).collect(Collectors.toUnmodifiableMap(
            Permission::code, Function.identity()));

    public static Permission fromExactCode(String code) {
        if (code == null) {
            throw new IllegalArgumentException("Unknown permission code");
        }
        Permission permission = BY_CODE.get(code);
        if (permission == null) {
            throw new IllegalArgumentException("Unknown permission code");
        }
        return permission;
    }
}
```

Tên enum là chi tiết code Java; chuỗi `code()` mới là mã canonical trong hợp đồng. Không dùng `name()` rồi tùy tiện thay đổi convention khi serialize ra token hoặc audit.

Đoạn này chỉ ánh xạ mã chính xác, chưa xác minh ai cấp mã, scope hoặc quyền trên object. Exception với mã không biết phải được đường gọi xử lý thành từ chối/lỗi cấu hình an toàn trước khi có tác dụng nghiệp vụ, không bắt exception rồi chuyển thành `ALLOW`.

Trong hệ thống lớn, có thể sinh các định nghĩa cần thiết từ một registry được quản lý để giảm lệch giữa enum, tài liệu và identity provider. Mọi service vẫn phải biết phần hợp đồng mình hỗ trợ; enum ở đây chỉ là tập con minh họa, không phải toàn bộ danh mục ở phần trước.

### 7.3. Backend quyết định action cần quyền nào

```java
public void approveOrder(ApproveOrderCommand cmd, TrustedActor actor) {
    transactions.executeWithoutResult(tx -> {
        PurchaseOrder order = orders.lockByTenant(
            actor.tenantId(), cmd.orderId());

        authorization.require(
            actor, Permission.ORDER_APPROVE, order);

        businessRules.requireApprovable(actor, order);
        approvals.recordAndApply(cmd, actor, order);
    });
}
```

Đây là khung minh họa application service; các dependency là hợp đồng chưa được triển khai trong bài. Permission bắt buộc được operation chọn bằng hằng số, không lấy từ trường `required_permission` mà client có thể đổi sang quyền đọc.

`authorization.require` phải kiểm tra grant, scope và constraint; `businessRules` cùng đường ghi bảo vệ trạng thái, nội dung và các invariant còn lại. Tên quyền tốt không thay thế các bước đó.

## 8. Những kiểu tên dễ làm lệch ý nghĩa

| Tên hoặc cách dùng mơ hồ | Vấn đề | Hướng diễn đạt rõ hơn |
| --- | --- | --- |
| `ADMIN` dùng như một permission duy nhất | Trộn role với mọi hành động | Role có tập permission và phạm vi được mô tả rõ |
| `ORDER_WRITE` | Không biết gồm sửa, submit, approve hay hủy | Tách action cần cấp/thu hồi độc lập |
| `button_approve_order` | Gắn bảo mật vào UI cụ thể | `procurement.purchase_order.approve` |
| `POST_ORDER` | Gắn với HTTP verb, bỏ qua ý định nghiệp vụ | `create`, `submit` hoặc `approve` theo operation thật |
| `order_123_approve` | Trộn loại quyền với một object | Permission ổn định và resource scope có cấu trúc |
| `approve_under_500m` | Đưa tham số động vào danh mục mã | Capability approve và constraint số tiền/tiền tệ |
| `approve_admin` | Gắn action với người giữ role hiện tại | Action ổn định, role mapping tách riêng |
| `read_all` | Không biết “all” là mọi field, object hay tenant | Tách projection và scope có định nghĩa rõ |
| `delete` dùng chung cho archive/cancel/purge | Các tác dụng khác nhau bị coi như đồng nghĩa | Dùng động từ nghiệp vụ thật và định nghĩa tác dụng |
| `process` cho cả yêu cầu lẫn thực thi | Dễ bỏ qua bước phê duyệt | Tách create/request, approve và execute nếu cần độc lập |
| `edit_v2` vì endpoint chuyển sang `/v2` | Trộn phiên bản transport với nghĩa quyền | Giữ mã nếu ngữ nghĩa không đổi; version API quản lý riêng |

Không phải cứ tên dài hơn là rõ hơn. Một tên ngắn nhưng có định nghĩa ổn định và được kiểm tra đúng thường tốt hơn chuỗi chứa nhiều từ nhưng mỗi nơi diễn giải khác nhau.

## 9. Quyền, role và ủy quyền phải được thay đổi có kiểm soát

### 9.1. Role là tập quyền tường minh

Ví dụ role reviewer có thể chứa:

```text
PURCHASING_REVIEWER
  - procurement.purchase_order.read
  - procurement.purchase_order.approve
  - procurement.purchase_order.reject
```

Đây mới là tập capability. Binding của role còn cần phạm vi tài nguyên và các constraint. Role không tự cấp quyền sửa giá chỉ vì có chữ `PURCHASING`, cũng không vượt maker–checker vì người dùng đang có nhiều role.

Thêm một quyền vào role đang được nhiều người sử dụng là thay đổi quyền thực tế. Cần xem ai bị ảnh hưởng, scope nào được bao phủ và có phá phân tách trách nhiệm không.

### 9.2. Cấp quyền không được trở thành quyền tự nâng đặc quyền

Một khả năng quản lý grant không nên mặc nhiên cho phép cấp mọi mã trong registry cho bản thân hoặc cho người khác.

Policy cần xác định người cấp được ủy quyền những permission nào, trong scope nào, hạn mức/thời hạn tối đa ra sao và có được cấp lại quyền quản trị grant hay không. Chỉ đặt tên `permission_grant.create` không giải quyết được các giới hạn này.

Trong quy trình ủy quyền, giữ danh tính người thực hiện và người được đại diện theo policy. Đổi chuỗi mã permission hoặc tạo role mới không được dùng để né quy tắc requester và reviewer phải độc lập.

### 9.3. Tên gần nhau không có nghĩa được thay thế cho nhau

`approve`, `approve_override`, `approve_emergency` nếu cùng tồn tại phải có khác biệt được định nghĩa. Không dùng một phép `startsWith("approve")` để chấp nhận tất cả như quyền thông thường.

Một action ngoại lệ có thể cần policy và bằng chứng khác, nhưng vẫn phải có phạm vi và trách nhiệm rõ. Không đặt tên ngoại lệ rồi triển khai nó như lối tắt bỏ mọi kiểm tra.

## 10. Đổi tên, tách quyền và quản lý vòng đời

### 10.1. Đổi nhãn không cần đổi mã

Nếu chỉ sửa bản dịch, mô tả hoặc bố cục UI, giữ mã canonical. Việc đổi mã kéo theo identity provider, token đang sống, role, cache, audit và các service tiêu thụ; không nên làm chỉ vì sở thích trình bày.

### 10.2. Đổi mã thật sự cần kế hoạch tương thích

Nếu cần đổi mã nhưng ngữ nghĩa giữ nguyên:

1. Ghi rõ ánh xạ cũ–mới và xác nhận hai capability thật sự tương đương.
2. Giới hạn alias tại điểm ánh xạ được kiểm soát; không để mỗi service tự chuẩn hóa tên.
3. Theo dõi nơi cấp và nơi dùng mã cũ, cập nhật role/grant và giao diện quản trị.
4. Xử lý token/cache còn chứa mã cũ theo cơ chế hiệu lực/thu hồi của hệ thống.
5. Chốt thời điểm ngừng cấp mới, sau đó ngừng chấp nhận mã cũ theo kế hoạch.
6. Giữ khả năng giải thích audit lịch sử: mã nào đã được dùng và policy/catalog version nào áp dụng.

Không tái sử dụng một mã đã bỏ cho hành động khác. Audit cũ và token chưa hết hiệu lực có thể bị diễn giải sai.

### 10.3. Tách quyền rộng không được tự động trao mọi quyền mới

Giả sử `ORDER_WRITE` trước đây thực tế chỉ cho sửa draft. Khi tách thành `edit_draft`, `submit` và `approve`, không được ánh xạ mọi holder cũ sang cả ba.

Phải đối chiếu hành vi và thẩm quyền đã được cấp trước đó. Nếu quyền cũ quá mơ hồ để xác định entitlement, cần làm rõ/cấp lại theo quy trình quản lý quyền. “Tương thích ngược” không phải lý do để tự bổ sung khả năng phê duyệt.

Nếu quyền cũ thực sự bao gồm nhiều action, việc thu hẹp hoặc thay đổi mapping cũng là thay đổi cần quản lý. Không chỉ đổi tên đẹp hơn rồi giả định rủi ro đã biến mất.

### 10.4. Phân biệt đổi capability với đổi policy

Điều chỉnh policy mà vẫn giữ cùng loại hành động có thể giữ mã permission và tăng version policy, nhưng tác động cấp quyền vẫn phải được đánh giá. Nới hạn mức, mở scope hoặc bỏ điều kiện độc lập đều có thể làm tăng quyền thực tế dù tên không đổi.

Nếu tác dụng nghiệp vụ thay đổi đáng kể, tạo capability mới hoặc định nghĩa lại bằng một quy trình migration rõ ràng. Chỉ thêm trường `semanticsVersion` vào registry mà không thay đổi cách hệ thống kiểm tra token/grant không tự ngăn grant cũ được dùng theo nghĩa mới.

Trạng thái `DEPRECATED` có thể cho phép dùng grant cũ theo nghĩa cũ nhưng chặn cấp mới. Trạng thái `RETIRED` cần được nơi kiểm tra quyền hiểu đúng và từ chối theo chính sách. Đừng chỉ đổi màu trên màn hình quản trị.

## 11. Gắn mã quyền với thực thi, audit và kiểm thử

### 11.1. Những invariant mà tên quyền không thay thế

Một người có `procurement.purchase_order.approve` vẫn phải bị chặn nếu:

- Đơn nằm ngoài tenant/project/resource scope được cấp.
- Người đó không độc lập với phía maker theo policy.
- Đơn chưa qua bước bắt buộc hoặc đã hết hiệu lực.
- Giá/nội dung đã đổi so với phiên bản được xét duyệt.
- Số tiền/tiền tệ vượt constraint của grant phù hợp.

Nếu request đã được commit rồi mất response, retry phải dùng idempotency để trả kết quả cũ, không ghi thêm lần duyệt. Nếu hai lệnh tranh chấp, transaction/version phải bảo vệ trạng thái. Đặt tên `approve_once` không tự tạo ra các bảo đảm này.

Nguyên tắc quyền tối thiểu và mặc định từ chối hỗ trợ việc thêm action mới mà không trao rộng quyền ngoài dự định. Các kiểm tra phải được thực thi, không chỉ thể hiện trong nhãn của permission. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 11.2. Audit cần ghi mã và căn cứ, không chỉ label

Audit có thể lưu permission canonical được yêu cầu, operation thực tế, principal, scope/resource, grant hoặc policy version, kết quả và reason code. Nếu có alias, lưu đủ thông tin để biết đầu vào đã được ánh xạ như thế nào theo hợp đồng.

Nhãn hiển thị đổi theo ngôn ngữ không nên làm mất khả năng tìm kiếm cùng một capability qua thời gian. Cũng không ghi token nguyên văn chỉ để nhớ user có những quyền nào.

Cache quyền phải xét mã canonical cùng principal, scope, resource và các version/ngữ cảnh liên quan. Đổi catalog hoặc thu hồi grant có thể cần invalidation hoặc cơ chế kiểm tra độ mới; tên mã đúng không tự bảo đảm cache còn đúng.

### 11.3. Kiểm thử ngữ nghĩa quan trọng hơn kiểm tra chuỗi có đẹp không

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Mã đúng cú pháp nhưng chưa đăng ký | Không được tự cấp nghĩa hoặc cho phép action |
| Mã có khoảng trắng, sai hoa/thường hoặc ký tự nhìn giống | Xử lý đúng hợp đồng canonical, không tự nâng quyền |
| Có `read`, gọi `approve` | Bị từ chối nếu không có grant approve phù hợp |
| Có `edit_draft`, gọi action sau phê duyệt | Không được dùng quyền nháp để sửa nội dung đã duyệt |
| Có `approve`, không có `reject` | Không suy ra reject từ tên hoặc role chưa được cấp |
| Có `read_sensitive_fields` nhưng không có quyền đọc object | Không đọc dữ liệu chỉ nhờ quyền field bổ sung |
| Có export nhưng object nằm ngoài scope đọc/xuất | Không xuất tài nguyên ngoài quyền |
| Grant cùng mã ở hai project có hạn mức khác nhau | Không ghép scope của grant này với hạn mức của grant khác |
| Thêm permission nhạy cảm vào registry | Role nghiệp vụ cũ không tự nhận chỉ vì enum/wildcard |
| Client đổi `required_permission` thành quyền dễ hơn | Backend vẫn dùng permission cố định của operation |
| Cùng tên mã từ issuer/bên nhận không phù hợp | Không chấp nhận như entitlement tin cậy |
| Đổi label hoặc bản dịch | Không thay đổi quyền thực tế |
| Alias mã cũ sang mã mới | Chỉ ánh xạ đã định nghĩa, không mở rộng capability |
| Tách `write` thành nhiều action | Không tự cấp approve cho mọi holder cũ |
| Permission đã retired còn trong token/cache | Xử lý theo hiệu lực hiện tại đã định nghĩa, không cho qua ngầm |
| Reviewer là maker hoặc tài nguyên ngoài tenant | Bị policy theo đối tượng chặn dù mã permission đúng |
| Retry một action đã commit | Không tạo thêm tác dụng nghiệp vụ |
| Policy/registry lỗi hoặc không có cấu hình | Không rơi vào nhánh mặc định cho phép |

Kiểm thử nên xác minh kết quả hành động và dữ liệu đã commit, không chỉ kiểm tra enum chứa một chuỗi. Với một action bị từ chối, bảo đảm không có thay đổi state, decision, outbox hoặc tác dụng phụ trái phép.

Các khung Java và cấu trúc trong bài mang tính minh họa thiết kế; chúng chưa được chạy như một ứng dụng hoàn chỉnh.

## 12. Bài tập thiết kế danh mục quyền

Một hệ thống hiện có ba tên `ORDER_VIEW`, `ORDER_WRITE` và `ORDER_ADMIN`. Tính năng thực tế gồm đọc đơn, xem dữ liệu nhạy cảm, sửa nháp, gửi duyệt, approve/reject, xuất báo cáo và chỉnh sửa sau khi đã duyệt.

Hãy thực hiện:

1. Lập danh sách action cần được cấp hoặc thu hồi độc lập; đặt tên theo một convention thống nhất.
2. Mô tả rõ tác dụng và những quyền không được suy ra cho từng mã.
3. Tách tenant/project/resource scope và hạn mức khỏi mã canonical.
4. Định nghĩa các role cần dùng, liệt kê tường minh capability và điều kiện binding.
5. Xác định dữ liệu nào cho biết holder của `ORDER_WRITE` cũ thật sự đã được cấp action gì; nêu những mapping không thể tự suy đoán.
6. Thiết kế kế hoạch alias/deprecation, xử lý token/cache và giữ nghĩa audit lịch sử.
7. Viết các trường hợp phủ định chứng minh người sửa nháp không được duyệt, reviewer không tự duyệt và grant ở project này không mở quyền project khác.

Một tên permission tốt giúp nhận diện chính xác khả năng đang được yêu cầu và giữ hợp đồng đó ổn định qua thời gian. Thiết kế an toàn còn phải gắn mã với grant có phạm vi, policy được thực thi và cơ chế thay đổi quyền không âm thầm mở rộng thẩm quyền nghiệp vụ.
