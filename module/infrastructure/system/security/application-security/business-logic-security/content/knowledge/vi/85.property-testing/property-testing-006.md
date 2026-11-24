# Thuộc tính đơn điệu của phân quyền (Authorization monotonicity property)

Trong bảo vệ logic nghiệp vụ, một thao tác chỉ hợp lệ khi đúng người, đúng đối tượng, đúng phạm vi và đúng trạng thái. Property testing giúp kiểm tra các quan hệ giữa nhiều cấu hình quyền thay vì chỉ xác nhận một vài ví dụ cho phép hoặc từ chối.

**Authorization monotonicity** là thuộc tính mô tả quyết định phân quyền thay đổi thế nào khi năng lực được cấp thay đổi theo một quan hệ thứ tự đã xác định. Với chính sách cấp quyền cộng dồn phù hợp, thêm quyền không được làm mất quyền đã có; nhìn theo chiều thu hẹp, bỏ quyền không được mở thêm thao tác trước đó bị cấm.

Điều kiện “chính sách phù hợp” rất quan trọng. Quy tắc deny, tách biệt nhiệm vụ, giới hạn phiên và điều kiện động có thể khiến tập role thô không có tính đơn điệu. Bài học này hướng dẫn đặc tả đúng quan hệ, sinh cặp dữ liệu có ý nghĩa và kiểm tra cả quyết định lẫn hiệu ứng nghiệp vụ.

## 1. Phát biểu thuộc tính bằng tập thao tác được phép

### 1.1. Các thành phần phải tách biệt

Ký hiệu:

- `s`: danh tính chủ thể và các thuộc tính ổn định trong lần so sánh.
- `G`: cấu hình quyền được cấp theo hợp đồng, chẳng hạn tập role cộng dồn.
- `q`: yêu cầu cụ thể, gồm action và resource thực sự tồn tại.
- `c`: ngữ cảnh đánh giá, gồm tenant, trạng thái tài nguyên, thời gian, phiên bản policy và các dữ liệu có liên quan.
- `allow(s, G, q, c)`: quyết định phân quyền của hệ thống.
- `A(s, G, c)`: tập yêu cầu được cho phép trong miền đang xét.

Giả sử quan hệ `G_low ⪯ G_high` được đặc tả là cấu hình `low` có năng lực không lớn hơn `high`. Thuộc tính cần kiểm tra là:

```text
G_low ⪯ G_high
    ⇒ A(s, G_low, c) ⊆ A(s, G_high, c)
```

Với một yêu cầu cụ thể, có thể viết:

```text
allow(s, G_low, q, c) ⇒ allow(s, G_high, q, c)
```

Dạng tương đương theo chiều an toàn khi thu hẹp:

```text
deny(s, G_high, q, c) ⇒ deny(s, G_low, q, c)
```

Thuộc tính **không** nói rằng `high` bị từ chối ở một yêu cầu thì `high` phải bị từ chối ở mọi yêu cầu khác. Action, resource và ngữ cảnh phải được giữ nguyên trong cặp so sánh.

### 1.2. Quan hệ thứ tự phải đến từ hợp đồng

Trong RBAC chỉ có grant cộng dồn, có thể chọn `G_low ⊆ G_high` trên tập role. Ví dụ, `EDITOR` cho xem và sửa, còn `APPROVER` cho xem và duyệt; thêm role chỉ bổ sung grant.

Trong hệ thống khác, role là gói năng lực có hierarchy, scope hoặc deny. Tên `ADMIN`, `MANAGER`, `CUSTOMER` không tự chứng minh role nào lớn hơn role nào. Phải xác định quan hệ từ hợp đồng quyền, không xếp thứ tự theo tên role hay theo chính kết quả mà implementation đang trả về.

Nếu định nghĩa `low ⪯ high` bằng cách gọi hệ thống rồi chọn các cặp có tập quyền thực tế bao hàm nhau, test sẽ trở thành vòng lặp tự xác nhận. Generator phải tạo cặp theo mô hình độc lập; hệ thống được kiểm thử phải tự chứng minh rằng nó tôn trọng quan hệ ấy.

### 1.3. Các biến cần cố định

Khi chỉ so sánh việc thêm role, giữ nguyên ít nhất:

- User ID, tenant đang hoạt động và membership nền.
- Resource ID, chủ sở hữu, người yêu cầu và trạng thái nghiệp vụ.
- Thời điểm, phiên bản policy và các cờ tính năng liên quan.
- Phiên bản dữ liệu dùng cho quyết định, nếu test cần một snapshot nhất quán.

Nếu lần thứ nhất đánh giá đơn `DRAFT` còn lần thứ hai đánh giá đơn `PAID`, kết quả có thể đổi vì state machine. Đó chưa phải phản ví dụ của tính đơn điệu theo role.

## 2. Chọn chiều đơn điệu đúng cho từng loại chính sách

| Thay đổi | Quan hệ cần đặc tả | Kỳ vọng khi điều kiện áp dụng đúng |
|---|---|---|
| Thêm grant trong mô hình cộng dồn | Grant cũ là tập con grant mới | Tập thao tác được phép không giảm |
| Bỏ grant hoặc thu hẹp scope | Năng lực mới nằm trong năng lực cũ | Không xuất hiện thao tác mới được phép |
| Thêm deny trong mô hình deny-overrides | Tập deny tăng, các grant và ngữ cảnh giữ nguyên | Tập thao tác được phép không tăng |
| Thu hẹp tập đối tượng được ủy quyền | Scope con là tập con scope cha | Quyền ủy quyền không vượt scope cha |
| Rút ngắn khoảng hiệu lực capability | Khoảng con nằm trong khoảng cha; cùng thời điểm đánh giá | Capability con không cho phép nơi capability cha bị từ chối |
| Đổi tenant từ A sang B | Hai phạm vi thường không so sánh được bằng bao hàm | Kiểm tra cô lập tenant theo policy, không suy ra đơn điệu |
| Đổi chủ sở hữu hoặc danh tính | Chủ thể/ngữ cảnh đã đổi | Dùng property phân quyền theo đối tượng riêng |
| Thay phiên bản policy | Hàm quyết định đã thay đổi | Kiểm tra tương thích hoặc migration theo hợp đồng riêng |

Một property hữu ích luôn có miền áp dụng và các giả định cụ thể. Đừng biến một nhận định đúng với grant cộng dồn thành quy tắc cho mọi hệ thống ABAC, RBAC hoặc capability.

## 3. Những chính sách có thể không đơn điệu theo tập role thô

### 3.1. Explicit deny

Giả sử `EDITOR` cấp quyền sửa, còn `SUSPENDED` khiến mọi chỉnh sửa bị từ chối. Ta có:

```text
{EDITOR}                  → cho sửa
{EDITOR, SUSPENDED}       → từ chối sửa
```

Thêm phần tử vào tập role đã làm mất quyền, đúng theo chính sách deny-overrides. Một test mặc định rằng mọi phép thêm role phải giữ quyền sẽ báo lỗi sai.

Trong mô hình này, có thể kiểm tra hai chiều riêng: tăng grant khi deny giữ nguyên, và tăng deny khi grant giữ nguyên. Nếu `SUSPENDED` thực ra là trạng thái tài khoản, nên mô hình nó thành thuộc tính có ngữ nghĩa rõ thay vì trộn mọi điều kiện vào một tập role không phân biệt.

### 3.2. Tách biệt nhiệm vụ

Quy tắc “người yêu cầu không được tự duyệt yêu cầu của mình” phụ thuộc vào danh tính và đối tượng. Nó có thể giữ nguyên khi thêm role: dù có `APPROVER`, chủ thể vẫn không được tự duyệt. Kiểu kiểm tra đó tương thích với grant cộng dồn nếu điều kiện cấm giữ nguyên trong cặp so sánh.

Một quy tắc khác cấm tổ hợp role `REQUESTER + APPROVER` hoặc hạn chế role đang kích hoạt trong một phiên. Khi đó, phép thêm role có thể tạo cấu hình không hợp lệ hoặc làm giảm quyền theo thiết kế. Test phải xác định miền các cấu hình hợp lệ và kiểm tra việc từ chối tổ hợp cấm bằng một property riêng.

Không loại một cặp khỏi generator chỉ vì nó làm test thất bại. Điều kiện loại phải được giải thích từ chính sách trước khi quan sát kết quả của implementation.

### 3.3. Giới hạn động và chính sách có điều kiện

Quyền có thể phụ thuộc cấp xác thực, thiết bị, hạn mức còn lại hoặc thông tin rủi ro. “Thêm role” không được phép đồng thời thay đổi các thuộc tính ấy trong cùng một phép so sánh.

Các thuộc tính có ràng buộc thường tạo **thứ tự bộ phận**: có cấu hình so sánh được, có cấu hình không. Một scope cho phép sửa đơn A và một scope cho phép sửa đơn B có thể không cấu hình nào bao hàm cấu hình nào. Ép chúng thành một thang “quyền thấp → quyền cao” làm mất ý nghĩa bảo mật.

## 4. Vì sao thuộc tính này hữu ích với tấn công logic

### 4.1. Giảm thông tin không được mở đường cho đặc quyền

Các lỗi có thể làm quyền thấp lại được phép nhiều hơn:

- Tập role rỗng được hiểu thành “không có hạn chế”, thay vì không có grant.
- Scope bị thiếu được mặc định thành mọi đối tượng.
- Parser chỉ kiểm tra role đầu tiên; thứ tự collection làm thay đổi kết quả.
- Khi không tìm thấy membership, code rơi vào nhánh quản trị mặc định.
- Endpoint kiểm tra `!roles.contains(BLOCKED)` nhưng không yêu cầu grant cần thiết.
- Cấu hình ít quyền đi qua một đường xử lý thiếu kiểm tra chủ sở hữu hoặc tenant.

Property test có thể tìm các phản ví dụ mà một vài test theo role quen thuộc bỏ sót. Nó đặc biệt hữu ích khi nhiều role được kết hợp hoặc quyền được thu hẹp qua token, delegation và scope.

### 4.2. Chỉ dữ liệu có thẩm quyền mới được tham gia quyết định

Trong kiểm thử service, có thể tạo principal giả lập để khám phá mô hình quyền. Trong API thực, khách không được tự gửi `roles=[ADMIN]` rồi được hệ thống tin tưởng. Việc lấy membership, xác minh token và giải quyết scope là các ranh giới cần kiểm tra riêng.

Đặc biệt, một thuộc tính deny gắn với tài khoản không được biến mất chỉ vì request bỏ trường đó. Phải xác định rõ đâu là role đã được gán có thẩm quyền, đâu là role đang kích hoạt trong phiên và đâu là scope được phép thu hẹp. Những trường hợp này có thể có quy tắc khác nhau.

Thuộc tính trên dữ liệu hợp lệ và thuộc tính từ chối dữ liệu giả mạo bổ sung cho nhau. Chỉnh sửa payload token mà không ký lại thường chỉ kiểm tra nhánh chữ ký sai; nó chưa chứng minh hệ thống xử lý đúng một token hợp lệ nhưng có scope hẹp hơn.

## 5. Ví dụ Java: một chính sách cộng dồn có điều kiện theo đối tượng

Ví dụ Java 17 trở lên sau cố ý dùng một chính sách nhỏ có thể hiểu hết:

- `READER`, `EDITOR` và `APPROVER` đều cấp quyền xem trong cùng tenant.
- `EDITOR` được sửa đơn nháp của mình.
- `APPROVER` được duyệt đơn đang chờ duyệt do người khác tạo.
- Tài khoản không hoạt động hoặc khác tenant luôn bị từ chối.
- Trong mô hình tối giản này, chủ sở hữu cũng là người tạo yêu cầu; ứng dụng thực có thể tách hai thuộc tính.

Các điều kiện theo tenant, chủ sở hữu và trạng thái không đổi khi thêm role, nên mô hình có tính đơn điệu theo bao hàm role. Nó không chứa deny phụ thuộc tổ hợp role.

```java
package example.security;

import java.util.Set;

public final class OrderAuthorization {
    public enum Role { READER, EDITOR, APPROVER }
    public enum Action { VIEW, EDIT, APPROVE }
    public enum State { DRAFT, SUBMITTED, APPROVED }

    public record Subject(
            String id,
            String tenantId,
            boolean enabled,
            Set<Role> roles) {
        public Subject {
            roles = Set.copyOf(roles);
        }
    }

    public record Order(
            String id,
            String tenantId,
            String ownerId,
            State state) {}

    public static boolean allowed(Subject subject, Action action, Order order) {
        if (!subject.enabled()
                || !subject.tenantId().equals(order.tenantId())) {
            return false;
        }

        boolean owner = subject.id().equals(order.ownerId());
        return switch (action) {
            case VIEW -> !subject.roles().isEmpty();
            case EDIT -> subject.roles().contains(Role.EDITOR)
                    && owner && order.state() == State.DRAFT;
            case APPROVE -> subject.roles().contains(Role.APPROVER)
                    && !owner && order.state() == State.SUBMITTED;
        };
    }
}
```

Đây là bộ quyết định thuần cho đầu vào hợp lệ. Ứng dụng còn cần xác thực principal, kiểm tra sự tồn tại và tính hợp lệ của đối tượng, đánh giá policy có thẩm quyền và thực thi cập nhật theo cơ chế transaction phù hợp.

Không suy từ tên `APPROVER` rằng người đó được sửa mọi đơn, hoặc suy rằng user cùng tenant được xem theo mọi hệ thống. Các quyền trên chỉ là hợp đồng minh họa đã nêu, cần thay bằng hợp đồng thực tế khi áp dụng.

## 6. Kiểm thử thuộc tính trên các cặp quyền

### 6.1. Duyệt hết miền nhỏ bằng JUnit 5

Ba role có 8 tập con. Có 27 cặp có thứ tự `(low, high)` thỏa `low ⊆ high`: với mỗi role, nó có thể nằm ngoài cả hai tập, chỉ trong `high` hoặc trong cả hai tập. Có thể duyệt hết miền này thay vì chọn ngẫu nhiên.

Ví dụ dưới đây dùng JUnit 5, cùng package với `OrderAuthorization`. Các đối tượng kiểm thử có 2 tenant, 2 chủ sở hữu và 3 trạng thái, tổng cộng 12 ngữ cảnh tài nguyên. Thuộc tính kiểm tra 27 cặp role × 2 trạng thái tài khoản × 12 tài nguyên × 3 action, tức 1.944 phép so sánh trong mô hình nhỏ này.

```java
package example.security;

import example.security.OrderAuthorization.Action;
import example.security.OrderAuthorization.Order;
import example.security.OrderAuthorization.Role;
import example.security.OrderAuthorization.State;
import example.security.OrderAuthorization.Subject;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderAuthorizationPropertyTest {
    private static Subject subject(Set<Role> roles, boolean enabled) {
        return new Subject("alice", "tenant-a", enabled, roles);
    }

    private static List<Set<Role>> roleSets() {
        var result = new ArrayList<Set<Role>>();
        Role[] roles = Role.values();
        for (int mask = 0; mask < (1 << roles.length); mask++) {
            var set = EnumSet.noneOf(Role.class);
            for (int bit = 0; bit < roles.length; bit++) {
                if ((mask & (1 << bit)) != 0) {
                    set.add(roles[bit]);
                }
            }
            result.add(Set.copyOf(set));
        }
        return result;
    }

    private static List<Order> orders() {
        var result = new ArrayList<Order>();
        int number = 0;
        for (String tenant : List.of("tenant-a", "tenant-b")) {
            for (String owner : List.of("alice", "bob")) {
                for (State state : State.values()) {
                    result.add(new Order("order-" + number++, tenant, owner, state));
                }
            }
        }
        return result;
    }

    @Test
    void addingRolesPreservesEveryAlreadyAllowedRequest() {
        List<Set<Role>> sets = roleSets();
        List<Order> resources = orders();
        for (Set<Role> lower : sets) {
            for (Set<Role> upper : sets) {
                if (!upper.containsAll(lower)) {
                    continue;
                }
                for (boolean enabled : new boolean[] {true, false}) {
                    Subject low = subject(lower, enabled);
                    Subject high = subject(upper, enabled);
                    for (Order order : resources) {
                        for (Action action : Action.values()) {
                            boolean allowedLow =
                                    OrderAuthorization.allowed(low, action, order);
                            boolean allowedHigh =
                                    OrderAuthorization.allowed(high, action, order);

                            assertTrue(!allowedLow || allowedHigh,
                                    () -> "monotonicity violated: lower=" + lower
                                            + ", upper=" + upper
                                            + ", enabled=" + enabled
                                            + ", action=" + action
                                            + ", order=" + order);
                        }
                    }
                }
            }
        }
    }

    @Test
    void independentExamplesAnchorThePolicyMeaning() {
        var ownDraft = new Order("own-draft", "tenant-a", "alice", State.DRAFT);
        var otherDraft = new Order("other-draft", "tenant-a", "bob", State.DRAFT);
        var ownSubmitted = new Order(
                "own-submitted", "tenant-a", "alice", State.SUBMITTED);
        var otherSubmitted = new Order(
                "other-submitted", "tenant-a", "bob", State.SUBMITTED);
        var foreign = new Order("foreign", "tenant-b", "bob", State.SUBMITTED);

        assertTrue(OrderAuthorization.allowed(
                subject(Set.of(Role.READER), true), Action.VIEW, ownDraft));
        assertTrue(OrderAuthorization.allowed(
                subject(Set.of(Role.EDITOR), true), Action.EDIT, ownDraft));
        assertFalse(OrderAuthorization.allowed(
                subject(Set.of(Role.EDITOR), true), Action.EDIT, otherDraft));
        assertTrue(OrderAuthorization.allowed(
                subject(Set.of(Role.APPROVER), true), Action.APPROVE, otherSubmitted));
        assertFalse(OrderAuthorization.allowed(
                subject(Set.of(Role.APPROVER), true), Action.APPROVE, ownSubmitted));

        for (Action action : Action.values()) {
            assertFalse(OrderAuthorization.allowed(
                    subject(Set.of(), true), action, ownDraft));
            assertFalse(OrderAuthorization.allowed(
                    subject(EnumSet.allOf(Role.class), true), action, foreign));
            assertFalse(OrderAuthorization.allowed(
                    subject(EnumSet.allOf(Role.class), false), action, ownDraft));
        }
    }
}
```

Đây là ví dụ kiểm thử theo thuộc tính bằng cách duyệt miền hữu hạn. Khi miền lớn hơn, có thể dùng một framework property testing để sinh cặp dữ liệu và thu nhỏ phản ví dụ, giữ nguyên hợp đồng và assertions. Đoạn mã minh họa không khẳng định bộ test đã được chạy trong một project cụ thể.

### 6.2. Vì sao cần các ví dụ neo độc lập

Một implementation luôn trả `true` thỏa `allow(low) ⇒ allow(high)`. Implementation luôn trả `false` cũng thỏa quan hệ ấy. Chỉ kiểm tra đơn điệu không đủ chứng minh phân quyền đúng.

Các ví dụ neo phải lấy từ hợp đồng: một yêu cầu chắc chắn được phép, một yêu cầu chắc chắn bị cấm và những ranh giới quan trọng như tenant, chủ sở hữu, tự duyệt và tài khoản bị khóa. Expected value không được lấy từ chính một helper quyền của production.

Ví dụ trên duyệt hết các tổ hợp đã mô hình hóa, nhưng chưa kiểm tra mọi user, tenant, resource, schema hoặc chính sách của ứng dụng. Tính đầy đủ trong một mô hình hữu hạn không tự trở thành bằng chứng đầy đủ cho hệ thống vận hành.

### 6.3. Cách chuyển sang kiểm thử hệ thống thật

Giữ generator và hợp đồng độc lập, rồi thay lời gọi bộ quyết định minh họa bằng adapter gọi service hoặc policy engine thực. Nếu service đọc quyền từ database, mỗi nhánh phải được dựng với dữ liệu có thẩm quyền tương ứng và dùng cùng ngữ cảnh nghiệp vụ ban đầu.

Đối với thao tác có ghi dữ liệu, không gọi `low` rồi gọi `high` trên cùng đối tượng đã bị thay đổi. Có thể đánh giá endpoint quyết định thuần, hoặc phục hồi hai bản baseline tương đương trước từng nhánh. Nếu nhánh đầu sửa đơn sang trạng thái khác, nhánh sau không còn là một phép so sánh cùng `c`.

## 7. Generator và shrinking phải giữ quan hệ giữa hai nhánh

### 7.1. Sinh cặp hợp lệ ngay từ đầu

Với mô hình role cộng dồn, một generator có thể làm:

```text
context := sinh một ngữ cảnh hợp lệ
lower := sinh tập role trong miền chính sách
extra := sinh tập role bổ sung
upper := lower ∪ extra

lowSubject  := cùng identity, tenant, enabled; roles = lower
highSubject := cùng identity, tenant, enabled; roles = upper

kiểm tra allow(lowSubject, request, context)
       ⇒ allow(highSubject, request, context)
```

Không cần sinh hai tập độc lập rồi loại gần hết các cặp không có bao hàm. Với miền có ràng buộc role, generator phải dựng các cấu hình hợp lệ theo hợp đồng; các tổ hợp cấm được kiểm tra bằng nhóm từ chối riêng.

Nên có chủ đích các lớp dữ liệu sau:

- Tập rỗng, tập đầy đủ, một role và nhiều role.
- Cặp bằng nhau để kiểm tra tính ổn định và cặp bao hàm nghiêm ngặt để thực sự thay đổi năng lực.
- Yêu cầu hợp lệ trong cùng tenant và đối tượng thực sự tồn tại ở tenant khác.
- Chủ đơn và người khác; đơn nháp, chờ duyệt và đã hoàn tất.
- Role có grant trùng nhau, role không liên quan đến action đang xét và hierarchy nhiều cấp nếu policy hỗ trợ.
- Scope chính xác, scope bao phủ một nhóm tài nguyên và scope rỗng theo ngữ nghĩa đã chốt.

Theo dõi số ca có `allow(low) = true`. Nếu tất cả `low` đều bị từ chối, mệnh đề kéo theo có thể luôn đúng mà không kiểm tra nhánh bảo toàn quyền. Đồng thời cần các ca `deny(high)` để kiểm tra chiều thu hẹp và các ví dụ neo để phân biệt hệ thống luôn cho phép.

### 7.2. Không so sánh scope bằng hình thức chuỗi

`order:1` không tự bao hàm `order:10`, và chuỗi ngắn hơn không tự là scope hẹp hơn. Wildcard, đường dẫn, nhóm đối tượng và role hierarchy phải được diễn giải theo hợp đồng.

Khi miền tài nguyên nhỏ, mô hình tham chiếu có thể biểu diễn scope thành tập ID cụ thể và kiểm tra bao hàm tập hợp. Khi scope tượng trưng phức tạp hơn, cần oracle độc lập đủ chính xác cho các mẫu được sinh. Tránh dùng chính bộ parser/matcher production để vừa dựng quan hệ bao hàm vừa kiểm tra implementation.

### 7.3. Thu nhỏ phản ví dụ mà không làm mất ý nghĩa

Một phản ví dụ cho property grant cộng dồn có dạng:

```text
lower ⊆ upper
same subject identity, request and context
allow(lower) = true
allow(upper) = false
```

Shrinker cần giữ các tiền điều kiện ấy trong quá trình tìm trường hợp nhỏ hơn. Có thể thử bỏ một role khỏi cả hai tập, hoặc bỏ một role chỉ có trong `upper`, miễn là vẫn giữ quan hệ bao hàm và tiếp tục gây lỗi. Nếu bỏ một role khỏi `upper` mà vẫn để trong `lower`, cặp mới không còn hợp lệ.

Với scope, có thể thu nhỏ tập đối tượng và action nhưng vẫn giữ đối tượng gây lỗi cùng quan hệ cha/con. Với API có chữ ký, thay claim cần tái phát hành token hợp lệ bằng cơ chế test tương ứng; cắt chuỗi token rồi nhận lỗi chữ ký không phải một phản ví dụ cùng loại.

Khi lưu lỗi, ghi seed, phiên bản generator, phiên bản policy, clock, `lower`, `upper`, request và dữ liệu đối tượng. Với lỗi tích hợp, cần cả phiên bản dữ liệu, cache và lịch sự kiện đủ để tái hiện. Sau khi điều tra, thêm phản ví dụ tối thiểu thành test hồi quy cố định.

## 8. Áp dụng cho delegation và scope thu hẹp

### 8.1. Thu hẹp năng lực được ủy quyền

Giả sử capability cha cấp quyền trên một tập action và resource, trong một tenant và một khoảng hiệu lực. Một capability con được phát hành theo cơ chế thu hẹp phải có các ràng buộc tương ứng:

```text
actions_child ⊆ actions_parent
resources_child ⊆ resources_parent
validity_child ⊆ validity_parent
tenant/audience phù hợp quan hệ được policy cho phép
```

Trong một mô hình mà quyền con luôn được kiểm tra cùng hiệu lực cha ở thời điểm hiện tại, property có thể là:

```text
allow(child, action, resource, now)
    ⇒ allow(parent, action, resource, now)
```

Phải xác định việc kiểm tra cha là động hay dựa trên snapshot lúc cấp. Với token độc lập có hiệu lực đến hạn theo hợp đồng, việc cha bị thu hồi sau lúc cấp có thể cần cơ chế revocation hoặc thời gian lan truyền riêng. Test cấp quyền phải chứng minh quyền con không vượt năng lực được phép ủy quyền tại thời điểm cấp; test thu hồi phải kiểm tra đúng hợp đồng thu hồi đã chọn.

Khi người nhận còn có grant riêng, hãy so sánh **năng lực đến từ đường ủy quyền đang xét**. Tổng quyền của người nhận có thể rộng hơn capability cha vì các grant độc lập hợp lệ; điều đó không tự là lỗi trong cơ chế thu hẹp.

### 8.2. Những cặp kiểm thử cần có

| Cha và con | Yêu cầu kiểm tra | Kỳ vọng |
|---|---|---|
| Cha cho xem/sửa; con chỉ xem | Con gọi sửa | Bị từ chối |
| Cha cho đơn A/B; con chỉ A | Con gọi thao tác trên B | Bị từ chối |
| Cha hiệu lực đến `T2`; con đến `T1 < T2` | Đánh giá tại `T1` và quanh biên theo hợp đồng | Không kéo dài quyền của con ngoài khoảng con |
| Cha tenant A; yêu cầu cấp con tenant B | Phát hành hoặc sử dụng scope vượt phạm vi | Bị từ chối theo quan hệ tenant đã chốt |
| Scope con rỗng | Gọi một action có bảo vệ | Không biến scope rỗng thành wildcard |
| Token con hợp lệ; request thêm role/scope rộng | Gọi API bằng dữ liệu mở rộng phía client | Không nhận thêm năng lực |

Audience là một phần của ý nghĩa token; hai audience khác nhau thường không so sánh được bằng thứ tự đơn giản. Cần đặc tả rõ trường hợp nào được ủy quyền sang audience khác thay vì mặc định mọi tập audience đều có thể cộng dồn.

## 9. Kiểm thử tại API và service có hiệu ứng nghiệp vụ

### 9.1. So sánh hai thế giới có cùng baseline

Một property tích hợp cho thao tác duyệt hoặc hoàn tiền có thể được tổ chức như sau:

1. Tạo resource tồn tại, payload hợp lệ và dữ liệu lịch sử đáp ứng điều kiện nghiệp vụ đang xét.
2. Chọn cặp quyền có quan hệ từ hợp đồng; cố định danh tính, tenant, resource, policy và clock.
3. Dựng baseline thứ nhất với quyền `low`, tạo phiên/token test hợp lệ theo cơ chế của hệ thống rồi gọi endpoint.
4. Dựng lại baseline tương đương với quyền `high` và gọi cùng thao tác. Bảo đảm cache, phiên và dữ liệu không còn mang cấu hình từ nhánh trước.
5. Phân loại kết quả thành quyết định cho phép/từ chối và kết quả nghiệp vụ. Không coi mọi HTTP lỗi là từ chối quyền.
6. Kiểm tra quan hệ đơn điệu và các oracle độc lập về quyền, trạng thái và hiệu ứng.

Hai tài khoản có ID khác nhau chưa chắc là hai baseline tương đương: việc đổi danh tính có thể đổi quan hệ chủ sở hữu hoặc quy tắc tự duyệt. Nếu test dùng hai môi trường/bản sao, cần ánh xạ nhất quán để mỗi nhánh vẫn biểu diễn cùng danh tính và cùng quan hệ với đối tượng theo mô hình.

Payload sai, resource không tồn tại hoặc số tiền vượt hạn mức có thể làm cả hai nhánh thất bại trước bước quyền. Các trường hợp đó cần test riêng; chúng không thay được dữ liệu đủ điều kiện để quan sát quyết định phân quyền.

### 9.2. Từ chối phải bảo vệ hiệu ứng, không chỉ phản hồi

Với một yêu cầu bị cấm, hãy kiểm tra theo phạm vi thao tác:

| Thao tác | Dữ liệu/hiệu ứng cần bảo vệ |
|---|---|
| Sửa giá | Giá, phiên bản báo giá, tổng đơn và lịch sử điều chỉnh nghiệp vụ |
| Duyệt | Trạng thái, người duyệt và điều kiện tách biệt nhiệm vụ |
| Hoàn tiền | Khoản giữ chỗ, refund intent, outbox và lệnh gửi provider |
| Chuyển quyền sở hữu | Chủ sở hữu và các quyền phát sinh từ quan hệ mới |
| Xem dữ liệu | Nội dung trả về và dữ liệu nhạy cảm trong phản hồi lỗi |

Yêu cầu bị từ chối có thể ghi audit hoặc chỉ số bảo mật theo thiết kế. Điều cần chứng minh là không có thay đổi nghiệp vụ được bảo vệ hoặc hiệu ứng bên ngoài trái phép, không phải database tuyệt đối không ghi gì.

Ví dụ, API trả `403` nhưng trước đó đã tạo refund intent và outbox vẫn là thất bại bảo mật. Với xử lý bất đồng bộ, cần kiểm tra công việc đã commit và quan sát worker bằng cơ chế có deadline phù hợp; không chỉ xem trạng thái ngay trước khi worker chạy.

### 9.3. Các property bổ sung ở ranh giới biểu diễn

Một tập quyền có thể được chuyển qua token, JSON, database và cache. Ngoài quan hệ bao hàm, cần các thuộc tính phù hợp với hợp đồng biểu diễn:

- Đổi thứ tự role không đổi quyền nếu role được hiểu là tập hợp.
- Lặp lại cùng role không tạo thêm quyền hoặc thay đổi thứ tự ưu tiên ngoài thiết kế.
- Thêm metadata không liên quan không đổi quyết định.
- Bỏ claim bắt buộc, claim sai kiểu hoặc role không biết được xử lý theo hợp đồng; không tạo grant mặc định ngoài ý muốn.
- Scope rỗng, scope thiếu và wildcard được phân biệt nếu chúng có ngữ nghĩa khác nhau.
- Chuyển đổi tenant trong request không tự chuyển phạm vi quyền của token.

Property đầu vào sai không nhất thiết bắt buộc một HTTP status duy nhất cho mọi API. Oracle cần quy định điều có ý nghĩa bảo mật: không cấp năng lực không được cho phép, không lộ dữ liệu và không thực hiện hiệu ứng trái phép.

## 10. Cache, thu hồi quyền và ranh giới thời gian

### 10.1. Grant đã giảm nhưng cache còn quyết định cũ

Một bộ quyết định thuần có thể đúng trong khi service dùng cache sai. Ví dụ, cache chỉ theo `userId` có thể dùng lại quyết định từ tenant A cho tenant B hoặc từ action xem sang action sửa.

Các kịch bản cần kiểm tra gồm:

- Làm nóng cache bằng quyền rộng rồi đánh giá scope hẹp.
- Làm nóng cache ở tenant A rồi truy cập đối tượng tenant B.
- Làm nóng cache cho action xem rồi thử action duyệt.
- Thay membership hoặc trạng thái tài khoản, sau đó đánh giá theo hợp đồng thu hồi.
- Thay chủ sở hữu hoặc trạng thái resource khi policy phụ thuộc các thuộc tính đó.
- Chạy lại cùng property với cache lạnh và cache nóng.

Khóa cache hoặc cơ chế invalidation phải phản ánh những yếu tố thực sự quyết định quyền. Không có một danh sách trường bắt buộc giống nhau cho mọi hệ thống; test nên làm thay đổi từng yếu tố có ý nghĩa và kiểm tra không tái dùng quyết định sai ngữ cảnh.

### 10.2. Thu hồi quyền cần có hợp đồng hiệu lực rõ ràng

“Bỏ quyền không mở thêm thao tác” là quan hệ giữa các cấu hình tại ngữ cảnh đã cố định. Việc hệ thống đang chạy chuyển từ quyền cũ sang quyền mới còn phụ thuộc cơ chế đồng bộ, thời hạn token và cache.

Phải xác định ít nhất:

- Quyền bị thu hồi có hiệu lực ngay hay sau một giới hạn lan truyền đã công bố?
- Token tự chứa được kiểm tra lại quyền hiện tại hay giữ snapshot đến thời điểm nào?
- Khi nào một thao tác được coi là đã được ủy quyền: lúc nhận request, lúc đánh giá policy hay tại ranh giới commit?
- Request đang xử lý khi có thu hồi được tiếp tục hay phải đánh giá lại đối với thao tác nhạy cảm?

Nếu hợp đồng yêu cầu hiệu lực ngay, test phải kiểm tra các quyết định sau điểm thu hồi có hiệu lực không dùng grant cũ. Nếu hợp đồng cho phép một khoảng trễ, dùng clock và điểm đồng bộ có thể kiểm soát để kiểm tra giới hạn đó; không khẳng định mọi request ngay sau thay đổi đều bắt buộc bị từ chối.

Các quy tắc này phải do thiết kế bảo mật xác định trước. Không chọn khoảng trễ tùy ý chỉ để một test thu hồi đang thất bại trở thành pass.

### 10.3. Quyền, trạng thái và transaction phải được gắn kết

Giả sử một yêu cầu sửa đơn được kiểm tra khi user còn quyền và đơn còn `DRAFT`, nhưng trước khi ghi, đơn chuyển sang `APPROVED` hoặc quyền bị thu hồi. Kết quả hợp lệ phụ thuộc điểm hiệu lực đã đặc tả và cách bảo vệ cập nhật.

Property test ở mức service cần kết hợp với integration test có lịch xen kẽ cụ thể. Tùy hệ thống, có thể cần kiểm tra phiên bản đối tượng, cập nhật có điều kiện, khóa hoặc đánh giá lại quyền ở một ranh giới nhất quán. Một boolean `allowed=true` không tự bảo đảm trạng thái lúc ghi còn hợp lệ.

Không dùng tính đơn điệu để yêu cầu một action luôn được phép mãi sau khi từng được phép. Sau khi duyệt xong, quy trình có thể cấm duyệt lại; sau khi tiền được giữ chỗ, phần còn lại có thể giảm. Đó là tiến triển của state machine và bất biến tài chính, cần được mô hình hóa bằng các property trạng thái riêng.

## 11. Đọc phản ví dụ và tránh các thuộc tính yếu

### 11.1. Phân loại kết quả của cặp so sánh

Với một cặp hợp lệ `low ⪯ high` trong mô hình grant cộng dồn:

| `allow(low)` | `allow(high)` | Ý nghĩa |
|---|---|---|
| `false` | `false` | Không vi phạm đơn điệu; vẫn cần biết lý do từ chối và các ca có nhánh được phép |
| `false` | `true` | Có thể là kết quả tăng quyền hợp lệ |
| `true` | `true` | Bảo toàn quyền trong cặp này; chưa chứng minh từng quyết định đúng |
| `true` | `false` | Phản ví dụ của đơn điệu nếu mọi tiền điều kiện thực sự được giữ |

Khi gặp phản ví dụ, kiểm tra lần lượt: quan hệ quyền có đúng theo hợp đồng không; hai nhánh có cùng ngữ cảnh không; policy có deny hoặc tổ hợp cấm không; cache/token có bị lẫn không; cuối cùng mới kết luận lỗi trong bộ quyết định.

Nếu phát hiện mô hình chính sách không đúng, sửa đặc tả và bộ sinh theo hợp đồng đã được xác nhận. Nếu cặp hợp lệ thật sự bị xử lý sai, giữ phản ví dụ và sửa implementation. Không xóa một role hoặc một tình huống khỏi dữ liệu chỉ để test xanh.

### 11.2. Một phản ví dụ nhỏ dễ giải thích

Giả sử implementation vô tình chỉ cấp quyền sửa khi user có đúng một role:

```text
EDIT được phép khi:
    có EDITOR và số role bằng 1
    và là chủ đơn và đơn đang DRAFT
```

Với cùng user và cùng đơn nháp của user:

```text
lower = {EDITOR}          → cho sửa
upper = {EDITOR, READER}  → từ chối sửa
```

Đây là phản ví dụ của mô hình cộng dồn. Shrinking có thể bỏ các role và resource không liên quan để giữ đúng cặp nhỏ này. Lỗi thực tế có thể đến từ điều kiện `size == 1`, xử lý phần tử đầu tiên hoặc một nhánh fallback không nhất quán.

Một lỗi nghiêm trọng theo chiều thu hẹp là tập role rỗng được hiểu thành toàn quyền, trong khi một tập không rỗng thiếu `EDITOR` bị từ chối sửa. Cặp `{}` và `{READER}` trên action sửa sẽ làm lộ việc giảm quyền lại mở thêm khả năng. Ví dụ neo “không có grant thì không được sửa” cũng phải bắt lỗi này.

### 11.3. Các lỗi trong chính bộ kiểm thử

| Lỗi thiết kế test | Hậu quả | Cách sửa |
|---|---|---|
| Assert `allow(high) ⇒ allow(low)` cho grant cộng dồn | Cấm cả việc tăng quyền hợp lệ | Dùng đúng chiều hoặc dạng deny tương đương |
| Chỉ sinh `low = high` | Hầu hết chỉ kiểm tra quyết định ổn định | Có cặp bao hàm nghiêm ngặt |
| Mọi request đều khác tenant | Tất cả bị từ chối, property dễ pass | Thêm đối chứng cùng tenant và action thực sự được phép |
| Thêm role đồng thời đổi user hoặc resource | Không còn so sánh cùng ngữ cảnh | Giữ danh tính và quan hệ đối tượng tương đương |
| Gọi thao tác ghi trên cùng baseline hai lần | Nhánh sau gặp trạng thái đã đổi | Phục hồi baseline hoặc dùng decision thuần |
| Bỏ các cặp có deny sau khi thấy thất bại | Che sai khác mô hình hoặc lỗi thực thi | Chốt miền và các property grant/deny từ trước |
| Oracle dùng lại helper quyền production | Cùng một lỗi tồn tại ở expected và actual | Dùng hợp đồng và ví dụ neo độc lập |
| Chỉ kiểm tra boolean/HTTP status | Có thể bỏ sót ghi dữ liệu hoặc gọi provider trái phép | Kiểm tra trạng thái bền vững và hiệu ứng ngoài |
| Thu nhỏ token thành chuỗi sai chữ ký | Đổi lỗi phân quyền thành lỗi xác thực | Sinh lại token test hợp lệ sau thay đổi claim |

### 11.4. Thử sức bộ test bằng thay đổi sai có ý nghĩa

Một bộ test phù hợp với ví dụ phải phát hiện được việc:

- Cho role rỗng đi vào nhánh toàn quyền.
- Từ chối user chỉ vì có thêm role không liên quan.
- Bỏ kiểm tra tenant, chủ sở hữu hoặc tự duyệt.
- Dùng scope rỗng như wildcard ngoài hợp đồng.
- Tái dùng cache từ cấu hình quyền rộng cho cấu hình hẹp.
- Ghi thay đổi nghiệp vụ trước khi kiểm tra quyền rồi vẫn trả lỗi.

Không phải mọi lỗi trong danh sách đều vi phạm tính đơn điệu thuần. Bỏ kiểm tra tenant có thể vẫn giữ quan hệ bao hàm role nhưng vi phạm oracle phân quyền theo đối tượng. Vì vậy, cần kết hợp property quan hệ với các bất biến bảo mật độc lập và ví dụ neo.

## 12. Bài tập áp dụng và tiêu chí hoàn thành

Chọn một API điều chỉnh giá, duyệt yêu cầu hoặc hoàn tiền trong ứng dụng và thực hiện:

1. Ghi rõ subject, action, resource và các thuộc tính ngữ cảnh mà quyết định phụ thuộc.
2. Phân loại grant, deny, role hierarchy, scope và quy tắc tách biệt nhiệm vụ. Nêu chính xác chiều nào có tính đơn điệu.
3. Định nghĩa `low ⪯ high` từ hợp đồng độc lập với implementation; ghi các trường hợp không so sánh được.
4. Sinh cặp quyền có quan hệ, giữ nguyên danh tính và ngữ cảnh; bao phủ tập rỗng, tập đầy đủ, cặp bằng nhau và cặp bao hàm nghiêm ngặt.
5. Thêm ví dụ neo có kết quả tính từ hợp đồng: được phép hợp lệ, khác chủ, khác tenant, trạng thái sai và tự duyệt nếu có.
6. Kiểm tra đủ ca làm tiền đề `allow(low)` đúng và ca `deny(high)` đúng; không chỉ đếm số lần chạy.
7. Tạo một lỗi giả định khiến thêm role làm mất grant; thu nhỏ và lưu phản ví dụ tối thiểu.
8. Kiểm tra một scope con không thể mở thêm action hoặc resource so với phạm vi cha theo hợp đồng delegation.
9. Chạy biến thể cache nóng/lạnh và thu hồi quyền theo điểm hiệu lực đã đặc tả.
10. Với request bị từ chối, kiểm tra không có cập nhật nghiệp vụ, giữ chỗ tiền hoặc lệnh bên ngoài trái phép.

Hoàn thành khi có bằng chứng cho **quan hệ quyền đã đặc tả**, **tính đúng đắn của các quyết định quan trọng** và **sự bảo vệ hiệu ứng nghiệp vụ**. Ghi rõ giới hạn của mô hình, miền dữ liệu đã xét và các chính sách không có tính đơn điệu theo cùng quan hệ.

Authorization monotonicity có giá trị khi quan hệ thứ tự phản ánh đúng ý nghĩa quyền của hệ thống. Kết hợp nó với kiểm tra theo đối tượng, state machine, transaction và oracle độc lập giúp phát hiện cả lỗi kết hợp quyền lẫn những đường lạm dụng mà một thuộc tính đơn lẻ không đủ bao phủ.
