# Kiểm thử leo thang đặc quyền (Privilege escalation test)

Trong bảo vệ logic nghiệp vụ, leo thang đặc quyền xảy ra khi một chủ thể thực hiện được thao tác hoặc nhận được dữ liệu vượt quá quyền được cấp. Hệ thống có thể xác thực người dùng đúng, nhận request hợp lệ và chạy transaction thành công nhưng vẫn sai nếu người đó không có quyền trên đối tượng, trường dữ liệu hoặc bước nghiệp vụ đang thao tác.

**Privilege escalation test** chủ động kiểm tra các ranh giới ấy bằng danh tính và dữ liệu của môi trường kiểm thử. Mục tiêu là chứng minh ai được làm gì, trên đối tượng nào, trong tenant nào và ở trạng thái nào; đồng thời xác minh yêu cầu trái phép không tạo thay đổi nghiệp vụ hoặc hiệu ứng tài chính.

Bài học thuộc chương **Security Testing** của module bảo vệ logic nghiệp vụ. Các tài khoản, API, vai trò và số tiền dưới đây là ví dụ tổng hợp. Các ca kiểm thử được thiết kế cho ứng dụng và môi trường thuộc phạm vi kiểm thử đã được cho phép, với dịch vụ ngoài được thay bằng adapter test phù hợp.

## 1. Phân biệt các ranh giới đặc quyền

### 1.1. Xác thực không thay thế phân quyền

Xác thực trả lời chủ thể là ai. Phân quyền quyết định chủ thể có được thực hiện yêu cầu cụ thể hay không. Một token hợp lệ của khách hàng không tự cấp quyền duyệt hoàn tiền, sửa giá đã xác nhận hay đọc đơn của khách hàng khác.

Đơn vị kiểm tra cần đủ ngữ cảnh:

```text
decision = policy(
    subject,
    action,
    resource,
    tenant,
    businessState,
    relevantContext
)
```

Chỉ kiểm tra `isAuthenticated()` hoặc có một role chung không bảo đảm tính đúng đắn của quyết định trên từng đối tượng. Ngược lại, chỉ kiểm tra chủ sở hữu cũng chưa đủ cho chức năng cần vai trò chuyên trách như phê duyệt hoàn tiền.

### 1.2. Các dạng vượt quyền thường gặp

| Dạng | Ví dụ | Ranh giới cần chứng minh |
|---|---|---|
| Theo chiều dọc | Khách hàng gọi chức năng duyệt hoàn tiền của nhân viên tài chính | Quyền thực hiện chức năng |
| Theo chiều ngang | Khách A đọc hoặc hủy đơn của khách B | Chủ sở hữu và quyền trên đối tượng |
| Vượt tenant | Nhân viên tenant A sửa tài nguyên tenant B | Phạm vi tổ chức và membership |
| Theo trường dữ liệu | Khách sửa `approvedBy`, `unitPrice`, `role` hoặc `tenantId` | Quyền thay đổi từng thuộc tính |
| Theo quan hệ cha/con | Đường dẫn dùng order A nhưng refund thực tế thuộc order B | Tính nhất quán và phạm vi của toàn đồ thị đối tượng |
| Theo quy trình | Người yêu cầu tự duyệt hoặc bỏ bước phê duyệt | Tách biệt nhiệm vụ và chuyển trạng thái |
| Qua thành phần trung gian | Worker có quyền rộng xử lý lệnh do người không có quyền tạo | Nguồn gốc và phạm vi quyền của công việc |

Truy cập trái phép tài nguyên cùng cấp thường được gọi là vượt quyền ngang. Nó cần được kiểm tra cùng leo thang theo chiều dọc, dù cách phân loại và tên lỗi trong từng tổ chức có thể khác nhau.

Một lỗ hổng có thể kết hợp nhiều dạng: người dùng đổi `tenantId`, chọn đơn của người khác rồi gửi trạng thái `APPROVED`. Mỗi ranh giới nên có test tập trung trước khi ghép thành chuỗi tấn công dài.

## 2. Viết hợp đồng phân quyền trước khi viết request tấn công

### 2.1. Chốt quy tắc nghiệp vụ minh họa

Giả sử ứng dụng có hai tenant A và B với các quy tắc:

- `CUSTOMER` xem đơn của mình và tạo yêu cầu hoàn cho đơn của mình nếu đủ điều kiện.
- `SUPPORT` xem thông tin đơn trong tenant với dữ liệu được che theo chính sách, không được duyệt hoàn tiền.
- `FINANCE_APPROVER` xem dữ liệu cần cho xử lý tài chính và duyệt yêu cầu trong tenant, trong hạn mức được cấp, nhưng không tự duyệt yêu cầu do mình tạo.
- `TENANT_ADMIN` được quản lý một tập role được ủy quyền trong tenant; ví dụ chỉ `CUSTOMER` và `SUPPORT`. Role này không tự cấp quyền đọc dữ liệu tài chính hoặc quyền gán `FINANCE_APPROVER`.
- Yêu cầu hoàn chỉ được duyệt khi đang `SUBMITTED`, đơn đã thu tiền và các bất biến tiền hoàn còn hợp lệ.

Đây là hợp đồng giả định cho bài học. Ứng dụng thực có thể cấp quyền khác; expected value phải đến từ chính sách đã xác nhận, không suy ra chỉ từ tên role hoặc hành vi hiện tại của API.

### 2.2. Ma trận chủ thể, đối tượng và hành động

Cho đơn `ORDER-A1` thuộc `customer-a1`, yêu cầu `REFUND-A1` do khách này tạo và đang đủ điều kiện duyệt:

| Chủ thể | Xem `ORDER-A1` | Tạo yêu cầu hoàn của đơn | Duyệt `REFUND-A1` | Gán `SUPPORT` cho người khác trong A |
|---|---|---|---|---|
| `customer-a1` | Có | Có, theo điều kiện nghiệp vụ | Không | Không |
| `customer-a2`, cùng tenant | Không | Không | Không | Không |
| `support-a` | Có, theo dữ liệu được phép | Không | Không | Không |
| `finance-a`, không phải requester | Có, theo phạm vi tài chính | Không với chỉ role này | Có, nếu trong hạn mức | Không |
| `finance-b` | Không | Không | Không | Không |
| `tenant-admin-a`, chỉ có role quản lý | Không theo hợp đồng ví dụ | Không | Không | Có, trong phạm vi được ủy quyền |

Không nên tạo một role “admin” rồi mặc định nó vượt qua mọi quy tắc. Quản trị thành viên, đọc dữ liệu và phê duyệt tiền có thể là các năng lực độc lập.

### 2.3. Oracle cần kiểm tra cả dữ liệu và hiệu ứng

Với một ca bị cấm, xác định trước:

1. Quyết định từ chối hoặc cách bỏ qua trường không được phép theo hợp đồng API.
2. Dữ liệu nào không được lộ trong response.
3. Trường nghiệp vụ nào phải giữ nguyên.
4. Bản ghi giữ chỗ, lệnh outbox hoặc yêu cầu bên thanh toán nào không được tạo.
5. Audit nào được phép xuất hiện để ghi nhận lần bị từ chối.

API có thể dùng `403` hoặc chủ động trả `404` để không tiết lộ tài nguyên. Hai lựa chọn này phải nhất quán với hợp đồng. Chỉ nhận một mã lỗi không đủ chứng minh quyền được bảo vệ: API có thể ghi dữ liệu trước rồi mới trả lỗi.

## 3. Chuẩn bị fixture giúp phân biệt lỗi quyền với lỗi dữ liệu

### 3.1. Dùng tài nguyên tồn tại và có đối chứng hợp lệ

Một fixture tối thiểu nên có:

- Hai khách hàng khác nhau trong tenant A, mỗi người có đơn riêng.
- Một khách hàng và một nhân viên tài chính trong tenant B.
- Một nhân viên tài chính tenant A, không phải requester của yêu cầu đang xét.
- Một yêu cầu hoàn hợp lệ đang `SUBMITTED`, cùng các đối chứng đã duyệt, đã hủy và do chính approver tạo.
- Giá, currency, phiên bản chính sách và lịch sử giao dịch đủ để yêu cầu hợp lệ thực sự có thể chạy.
- Adapter thanh toán, hàng đợi và nơi lưu file dành cho test khi thao tác có liên quan.

Trước ca tấn công, xác minh chủ thể được phép thực hiện thành công cùng loại thao tác trên baseline tương đương. Nếu cả người có quyền cũng thất bại vì đơn không tồn tại hoặc thiếu khoản thu, ca bị cấm chưa chứng minh được gì về kiểm tra đặc quyền.

### 3.2. Một kịch bản tài chính có thể tính tay

Giả sử đơn đã thu 100.000 VND, đã hoàn 30.000 và đang giữ chỗ 20.000. Phần còn lại có thể giữ chỗ cho một ý định hoàn mới là 50.000 VND, theo chính sách giả định không có khoản khấu trừ khác.

Có thể tạo yêu cầu mới 40.000 VND làm đối chứng hợp lệ. Khách là chủ đơn được gửi yêu cầu nếu quy trình cho phép, nhưng chỉ approver phù hợp mới được duyệt. Việc tạo yêu cầu và thời điểm giữ chỗ phải đúng hợp đồng của ứng dụng; không giả định mọi hệ thống đều giữ chỗ ở cùng một bước.

Các ca sửa amount thành 60.000, tự đặt `approvedBy` hoặc dùng approver tenant B phải bị ngăn bởi ranh giới tương ứng. Không trộn mọi vi phạm vào một request đầu tiên: nếu amount đã vượt trần, ứng dụng có thể từ chối trước khi đi tới kiểm tra quyền mà test muốn quan sát.

### 3.3. Quan sát bằng quyền của bộ kiểm thử

Bộ kiểm thử cần đọc được trạng thái đáng tin cậy từ database hoặc một adapter quan sát riêng trong môi trường test. Đừng dùng chính tài khoản tấn công để xác định rằng dữ liệu không đổi: tài khoản ấy có thể chỉ không nhìn thấy thay đổi.

Snapshot nên bao phủ các đối tượng bị tác động, quyền được gán, yêu cầu phê duyệt, khoản giữ chỗ và các lệnh bên ngoài liên quan. Sắp xếp ổn định các collection khi so sánh. Audit bảo mật và metadata kỹ thuật được đánh giá theo hợp đồng riêng để tránh coi một bản ghi từ chối hợp lệ là thay đổi nghiệp vụ trái phép.

## 4. Lập bản đồ bề mặt kiểm thử

| Bề mặt | Biến đổi có chủ đích | Điều phải giữ |
|---|---|---|
| Endpoint quản trị hoặc nghiệp vụ đặc quyền | Gọi bằng phiên khách hàng hợp lệ | Không thực hiện chức năng vượt role |
| Path/query chứa ID | Thay bằng ID tồn tại của người khác | Kiểm tra quyền đối tượng, không chỉ tìm thấy bản ghi |
| Body chứa ID hoặc nested object | Dùng resource khác với resource trên path | Kiểm tra quan hệ và phạm vi nhất quán |
| Trường nhạy cảm | Thêm `role`, `approvedBy`, `price`, `tenantId`, `status` | Không chấp nhận thay đổi ngoài quyền |
| API quản lý thành viên | Tự gán role hoặc gán role ngoài tập được ủy quyền | Kiểm tra cả người gán, người nhận và role đích |
| Bulk, export, search | Trộn ID được phép và không được phép | Không lọt dữ liệu hoặc hiệu ứng trái phép trong một phần tử |
| Endpoint thay thế | Thử cùng năng lực ở phiên bản/API khác đang được hỗ trợ | Chính sách bảo vệ nhất quán với hợp đồng từng đường |
| Tác vụ bất đồng bộ | Gửi lệnh hoặc payload vượt phạm vi của người tạo | Worker không trở thành đường nâng quyền |
| Session/token/cache | Dùng phiên đúng người nhưng quyền hẹp hoặc đã thu hồi | Không kế thừa quyết định có quyền rộng ngoài hợp đồng |
| Workflow | Bỏ bước, tự duyệt hoặc lặp bước đã kết thúc | Quyền và state machine cùng được kiểm tra |

Chỉ kiểm tra route trên giao diện dễ bỏ sót các đường gọi trực tiếp. Nút bị ẩn không phải ranh giới phân quyền. Ngược lại, thay HTTP method hoặc đoán route không tồn tại rồi nhận `404` cũng chưa kiểm tra được chức năng đặc quyền; phải bắt đầu từ đường nghiệp vụ có thật trong phạm vi test.

## 5. Các kịch bản cốt lõi cần thực hiện

### 5.1. Leo thang theo chiều dọc: khách hàng tự duyệt hoàn tiền

Với `REFUND-A1` hợp lệ đang `SUBMITTED`:

1. Dùng fixture đối chứng để xác minh `finance-a` được duyệt khi đúng tenant, không tự duyệt và trong hạn mức.
2. Phục hồi baseline ban đầu.
3. Dùng phiên hợp lệ của `customer-a1` gọi thao tác duyệt trực tiếp.
4. Kiểm tra từ chối, trạng thái vẫn `SUBMITTED`, không có approver trái phép và không tạo lệnh tiền mới.
5. Thử các trường `role`, `approvedBy` hoặc header tự khai vai trò theo hợp đồng đầu vào của ứng dụng; chúng không được trở thành nguồn cấp quyền.

Đối chứng và ca tấn công phải dùng baseline tương đương. Nếu duyệt thật ở bước đầu rồi gọi lại cùng yêu cầu đã duyệt, lỗi trạng thái ở lần sau có thể che mất việc API thiếu kiểm tra role.

### 5.2. Vượt quyền ngang: dùng đối tượng của người khác

Dùng `customer-a2` yêu cầu xem, hủy hoặc tạo hoàn cho `ORDER-A1`. Đơn này phải tồn tại và được `customer-a1` truy cập hợp lệ.

Kiểm tra từng action riêng. Việc endpoint xem đơn kiểm tra owner đúng không chứng minh endpoint tạo refund, xuất hóa đơn hoặc tải file đính kèm cũng đúng. Hãy dùng ID có sẵn trong fixture, không cần dò tài nguyên ngoài phạm vi test.

### 5.3. Vượt tenant: có role đúng ở phạm vi sai

Dùng `finance-b` duyệt `REFUND-A1`. Đây là đối chứng quan trọng: chủ thể có role chuyên trách nhưng ở tenant khác. Nếu test chỉ dùng khách hàng không có role, hệ thống có thể vượt qua nhờ kiểm tra role và vẫn thiếu kiểm tra tenant.

Nếu ứng dụng hỗ trợ một user tham gia nhiều tenant, tạo membership khác nhau ở mỗi tenant rồi đổi tenant đang hoạt động. Request không được chọn membership thuận lợi từ tenant khác để áp vào đối tượng đích.

### 5.4. Đối tượng cha/con không khớp

Với API minh họa:

```text
POST /orders/{orderId}/refunds/{refundId}/approve
```

Tạo một cặp `orderId` và `refundId` cùng thuộc quyền của người thử nhưng không có quan hệ cha/con; thêm một cặp trong đó refund thuộc tenant khác. Hệ thống phải giải quyết đúng đối tượng và kiểm tra quan hệ, không chỉ kiểm tra quyền trên order trong path rồi cập nhật refund tìm được bằng ID độc lập.

Sau khi bị từ chối, quan sát cả order trên path và order thực sự sở hữu refund. Một snapshot chỉ theo đối tượng trên path có thể bỏ sót thay đổi trái phép ở đối tượng con.

### 5.5. Mass assignment trên trường đặc quyền

Một request tạo hoặc cập nhật có thể mang thêm trường không thuộc quyền khách hàng:

```json
{
  "reason": "Yeu cau hoan trong moi truong test",
  "amount": "40000",
  "status": "APPROVED",
  "approvedBy": "finance-a",
  "tenantId": "tenant-b"
}
```

Đây là payload minh họa để kiểm tra binding và quyền theo trường. Hợp đồng có thể yêu cầu từ chối các trường ấy hoặc bỏ qua chúng; trong cả hai trường hợp, trạng thái, approver và tenant có thẩm quyền không được bị thay đổi theo ý khách.

Với trường được phép điều chỉnh bởi nhân viên có quyền riêng, thêm đối chứng nhân viên hợp lệ. Kiểm tra cả đường cập nhật từng trường lẫn đường bind cả object, import hoặc bulk nếu chúng tồn tại trong ứng dụng.

## 6. Ví dụ Java: contract test kiểm tra từ chối và hiệu ứng

### 6.1. Hợp đồng của adapter kiểm thử

Khung dưới dùng Java 17 trở lên và JUnit 5. `Driver` là adapter do project triển khai để gọi service hoặc API thật trong môi trường test. `Actor` là handle của danh tính test; adapter ánh xạ handle sang phiên hoặc token được tạo đúng cơ chế. Nó không có nghĩa là server tin `userId` hoặc `tenantId` tùy ý do client gửi.

Hợp đồng minh họa của fixture:

- `reset()` phục hồi database, queue, cache và fake provider thuộc lần chạy, rồi tạo yêu cầu 40.000 VND hợp lệ đang `SUBMITTED` của khách A.
- `financeA` có quyền duyệt yêu cầu này, không phải requester; `customerA` và `financeB` không được duyệt.
- Duyệt thành công giữ trạng thái phê duyệt của yêu cầu là `APPROVED` và dẫn tới đúng một hiệu ứng hoàn tiền được fake provider ghi nhận. Trạng thái xử lý thanh toán, nếu có, được quản lý riêng theo mô hình ứng dụng.
- `settleTestWork()` xử lý/chờ các công việc test liên quan tới điểm ổn định có deadline, thất bại nếu không đạt; nó không gọi dịch vụ production.
- `snapshot()` trả các collection bất biến, sắp xếp ổn định và bao phủ dữ liệu nghiệp vụ liên quan cùng hiệu ứng của fake provider. Audit lần truy cập bị cấm được kiểm tra riêng.

```java
package example.security;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

abstract class PrivilegeEscalationContractTest {
    record Actor(String userId, String tenantId) {}

    record Fixture(
            Actor customerA, Actor financeA, Actor financeB, String refundId) {}

    record Reply(int status) {}

    record OrderView(
            String id, String tenantId, String ownerId, String state,
            long totalMinor, String currency, String policyVersion) {}

    record RefundView(
            String id, String orderId, String tenantId, String requesterId,
            String state, String approvedBy, long amountMinor, String currency) {}

    record ReservationView(
            String id, String refundId, long amountMinor, String currency) {}

    record OutboxView(
            String id, String refundId, String command, String state,
            long amountMinor, String currency) {}

    record RoleBinding(String userId, String tenantId, String role) {}

    record ProviderEffect(
            String providerTransactionId, String refundId, String kind,
            long amountMinor, String currency) {}

    record BusinessSnapshot(
            List<OrderView> orders,
            List<RefundView> refunds,
            List<ReservationView> reservations,
            List<OutboxView> outbox,
            Set<RoleBinding> roleBindings,
            List<ProviderEffect> providerEffects) {
        BusinessSnapshot {
            orders = List.copyOf(orders);
            refunds = List.copyOf(refunds);
            reservations = List.copyOf(reservations);
            outbox = List.copyOf(outbox);
            roleBindings = Set.copyOf(roleBindings);
            providerEffects = List.copyOf(providerEffects);
        }
    }

    interface Driver {
        Fixture reset();
        Reply approveRefund(Actor actor, String refundId);
        void settleTestWork();
        BusinessSnapshot snapshot();
    }

    protected abstract Driver driver();

    private void assertDeniedWithoutBusinessEffect(
            Driver app, Actor actor, String refundId) {
        BusinessSnapshot before = app.snapshot();

        Reply reply = app.approveRefund(actor, refundId);
        app.settleTestWork();

        assertTrue(reply.status() == 403 || reply.status() == 404,
                "request must be denied according to this API contract");
        assertEquals(before, app.snapshot(),
                "denied request must not change protected business state");
    }

    @Test
    void customerCannotApproveOwnRefundRequest() {
        Driver app = driver();
        Fixture fixture = app.reset();

        assertDeniedWithoutBusinessEffect(
                app, fixture.customerA(), fixture.refundId());
    }

    @Test
    void financeRoleInAnotherTenantCannotApprove() {
        Driver app = driver();
        Fixture fixture = app.reset();

        assertDeniedWithoutBusinessEffect(
                app, fixture.financeB(), fixture.refundId());
    }

    @Test
    void authorizedApproverProvidesAPositiveControl() {
        Driver app = driver();
        Fixture fixture = app.reset();

        Reply reply = app.approveRefund(fixture.financeA(), fixture.refundId());
        app.settleTestWork();

        assertTrue(reply.status() >= 200 && reply.status() < 300);
        BusinessSnapshot after = app.snapshot();
        RefundView refund = after.refunds().stream()
                .filter(row -> row.id().equals(fixture.refundId()))
                .findFirst().orElseThrow();
        assertEquals("APPROVED", refund.state());
        assertEquals(fixture.financeA().userId(), refund.approvedBy());
        assertEquals(40_000L, refund.amountMinor());
        assertEquals("VND", refund.currency());
        assertEquals(1L, after.providerEffects().stream()
                .filter(effect -> effect.refundId().equals(fixture.refundId())
                        && effect.kind().equals("REFUND")
                        && effect.amountMinor() == 40_000L
                        && effect.currency().equals("VND"))
                .count());
    }
}
```

Đây là abstract contract test, cần một lớp con và adapter để chạy trên ứng dụng. Ví dụ không khẳng định đã được thực thi trong một project cụ thể. Nếu API dùng bất đồng bộ, trạng thái phản hồi và điểm quan sát phải được điều chỉnh theo hợp đồng thực tế, đồng thời giữ oracle về quyền và hiệu ứng.

### 6.2. Giới hạn cần hiểu khi áp dụng

Khung chỉ minh họa hai ranh giới duyệt hoàn và một đối chứng hợp lệ. Nó chưa kiểm tra toàn bộ quyền theo đối tượng, nội dung response, role assignment, callback hoặc chuyển trạng thái. Các trường trong snapshot cần được mở rộng khi hệ thống có dữ liệu được bảo vệ khác.

`ProviderEffect` biểu diễn giao dịch tài chính đã xảy ra trong fake, không phải số lần gửi HTTP. Có thể có nhiều lần thử hợp lệ nhưng chỉ một khoản hoàn. Với đối chứng cho phép, project nên bổ sung kiểm tra không có hiệu ứng ngoài dự kiến, bất biến tổng tiền và quan hệ đúng giữa outbox, refund và giao dịch provider.

Với các ca bị cấm, snapshot phải bao gồm cả công việc đang chờ đã commit, không chỉ hiệu ứng đã hoàn tất. Chỉ đếm số lời gọi provider ở một thời điểm có thể bỏ sót một outbox trái phép sẽ chạy sau đó.

## 7. Kiểm thử việc gán role và ủy quyền

### 7.1. Người có quyền quản lý cũng phải có giới hạn

Một endpoint quản lý thành viên thường cần kiểm tra đồng thời:

```text
actor được quản lý thành viên trong tenant đích
target thực sự thuộc phạm vi được quản lý
requestedRole nằm trong tập role actor được phép cấp
thao tác tự thay quyền đáp ứng chính sách riêng
quy tắc phê duyệt hoặc tách biệt nhiệm vụ, nếu có, vẫn được giữ
```

Test tối thiểu nên có:

- Khách hàng tự thêm `SUPPORT` hoặc `FINANCE_APPROVER` cho mình.
- Tenant admin A cấp role cho tài khoản tenant B bằng cách thay ID.
- Tenant admin chỉ được cấp `SUPPORT` thử cấp role tài chính ngoài tập được ủy quyền.
- Request chứa cả role được phép và role bị cấm để kiểm tra tính nguyên tử hoặc chính sách từng phần.
- Gửi `tenantId`, `userId`, `role` mâu thuẫn giữa path và body.
- Thử thay quyền qua đường import, bulk hoặc endpoint cập nhật profile nếu có binding tới cùng dữ liệu.
- Dùng lại request gán role sau khi actor bị thu hồi quyền quản lý.

Không coi việc có quyền gọi endpoint là đủ. Một người có quyền quản lý thành viên vẫn có thể không được cấp một role cụ thể hoặc sửa chính tài khoản của mình.

### 7.2. Scope con không được mở rộng quyền cha

Khi phát hành token hay delegation có scope hẹp, kiểm tra con không nhận thêm action, resource hoặc tenant ngoài phạm vi được cấp theo hợp đồng. Scope rỗng không được biến thành toàn quyền nếu chính sách định nghĩa nó là không có grant.

Nếu người nhận có quyền độc lập khác, tách phần quyền do delegation cung cấp khỏi tổng quyền của người nhận. Nếu không, một test có thể kết luận sai rằng capability con vượt cha trong khi quyền bổ sung đến từ membership hợp lệ khác.

Token tự chứa, refresh token và membership có thể có thời gian hiệu lực khác nhau. Phải ghi rõ lúc nào quyền mới hoặc quyền bị thu hồi được phản ánh; đừng tự giả định sửa database sẽ làm mọi token cũ mất hiệu lực ngay.

## 8. Kết hợp quyền với state machine, cache và transaction

### 8.1. Có role đúng nhưng trạng thái sai vẫn phải bị chặn

Với cùng approver hợp lệ, thử duyệt yêu cầu ở các trạng thái:

| Trạng thái | Điều cần xác định từ hợp đồng |
|---|---|
| `DRAFT` | Chưa được gửi thì có được duyệt không? |
| `SUBMITTED` | Đủ điều kiện duyệt hay còn thiếu bước kiểm tra? |
| `APPROVED` | Retry trả kết quả cũ hay bị từ chối, và có tạo thêm hiệu ứng không? |
| `CANCELLED` | Có đường khôi phục hợp lệ riêng hay hoàn toàn cấm duyệt? |
| Đang chờ kết quả thanh toán | Có được đổi amount hoặc approver không? |

Tạo thêm yêu cầu do chính approver lập để kiểm tra cấm tự duyệt. Chỉ có role `FINANCE_APPROVER` không làm điều kiện này biến mất. Nếu hệ thống yêu cầu nhiều người duyệt, kiểm tra một người không được tính thành nhiều người bằng các phiên hoặc lần gọi khác nhau.

### 8.2. Cache không được chuyển quyền giữa ngữ cảnh

Các kịch bản quan trọng:

- Làm nóng cache bằng nhân viên có quyền rồi gọi bằng khách hàng.
- Làm nóng cache ở tenant A rồi đổi tenant hoặc đối tượng sang B.
- Làm nóng cache cho action xem rồi thử duyệt hoặc sửa.
- Thay đổi owner, trạng thái hoặc membership và kiểm tra theo cơ chế invalidation đã chốt.
- Chạy lại cùng kịch bản với cache lạnh để phân biệt lỗi policy và lỗi tái dùng quyết định.

Khóa cache và invalidation phải phù hợp với các yếu tố mà quyết định thực sự phụ thuộc. Cache chỉ theo role hoặc chỉ theo user có thể thiếu action, scope hay ngữ cảnh đối tượng.

### 8.3. Thu hồi quyền và thao tác đang chạy

Đặc tả trước điểm hiệu lực của việc thu hồi: ngay lập tức, sau một khoảng lan truyền được công bố, hoặc tại lần phát hành token tiếp theo trong một thiết kế cụ thể. Các thao tác tài chính nhạy cảm cần quyết định rõ cách xử lý request đã được kiểm tra quyền nhưng chưa commit.

Một integration test có thể điều phối:

1. Request duyệt bắt đầu với principal hợp lệ.
2. Dừng ở một mốc kiểm soát được trước cập nhật nghiệp vụ.
3. Thu hồi membership, đổi hạn mức hoặc chuyển yêu cầu sang trạng thái khác.
4. Cho request tiếp tục và kiểm tra theo điểm hiệu lực đã đặc tả.
5. Đối chiếu dữ liệu commit, khoản giữ chỗ và lệnh ra ngoài.

Tùy thiết kế, cần kiểm tra phiên bản dữ liệu, cập nhật có điều kiện, khóa hoặc đánh giá lại ở ranh giới nhất quán. Test phải kiểm tra kết quả hợp đồng, không khẳng định một cơ chế khóa cụ thể tự giải quyết mọi vấn đề phân quyền.

Hai request hợp lệ cùng lúc cũng không được cộng lại thành một quyền vượt hạn mức. Quyền duyệt từng yêu cầu và bất biến tổng tiền phải được giữ dưới concurrency; idempotency chỉ xử lý đúng phạm vi ý định mà nó đại diện.

## 9. Các đường vượt quyền gián tiếp

### 9.1. Worker trở thành bên thực hiện hộ trái phép

Một worker thường dùng service account có quyền rộng để xử lý nhiều tenant. Nếu nó chỉ tin `tenantId`, `userId` hoặc `approved=true` trong payload, người gửi lệnh có thể nhờ worker thực hiện việc mà chính họ không được phép làm. Đây là tình huống thành phần có quyền bị lợi dụng để làm thay một yêu cầu vượt phạm vi.

Thiết kế cần xác định nguồn gốc công việc, phạm vi đối tượng và điểm quyết định quyền. Công việc có thể cần gắn với actor, tenant, business intent, resource và bằng chứng quyết định có thẩm quyền. Việc đánh giá lại quyền hiện tại hay tiếp tục theo quyết định lúc nhận phải theo hợp đồng, đặc biệt khi quyền bị thu hồi giữa hai bước.

Các ca kiểm thử nên bao gồm:

- Khách hàng gọi API tạo công việc tài chính mà không có quyền cần thiết.
- Actor hợp lệ nhưng resource trong công việc thuộc tenant khác.
- Payload khai actor hoặc tenant khác với danh tính đã được xác thực.
- Công việc đã xếp hàng trong khi membership thay đổi trước lúc chạy.
- Worker xử lý lại cùng business intent sau timeout hoặc restart.
- Trạng thái resource đổi trước khi worker ghi kết quả.

Đánh giá đúng ranh giới đang kiểm thử. Chèn trực tiếp một message tùy ý vào queue qua quyền quản trị test có thể kiểm tra khả năng tự bảo vệ của worker, nhưng chưa chứng minh khách hàng bên ngoài tạo được message ấy. Muốn kết luận về đường API, phải tái hiện đường đi từ danh tính khách tới công việc đã được chấp nhận.

### 9.2. Bulk và import cần kiểm tra từng phần tử

Tạo một batch chứa:

```text
item 1: đối tượng actor được phép xử lý
item 2: đối tượng khác chủ nhưng cùng tenant
item 3: đối tượng tenant khác
item 4: đối tượng có trạng thái không cho phép thao tác
```

Hợp đồng có thể chọn rollback toàn batch hoặc trả kết quả từng phần. Trong cả hai trường hợp, phần tử trái phép không được cập nhật hoặc tạo hiệu ứng. Với chế độ từng phần, kết quả lỗi không được lộ dữ liệu mà actor không có quyền xem.

Không chỉ kiểm tra batch mà phần tử đầu tiên bị cấm. Một implementation chỉ kiểm tra phần tử đầu có thể vượt qua ca đó; phải đổi vị trí phần tử hợp lệ và trái phép. Với import có trường tenant/owner/role, áp dụng cùng giới hạn theo trường như đường cập nhật thông thường.

### 9.3. Search, export và file kết quả

Quyền xem từng đối tượng cần được giữ qua đường danh sách, tìm kiếm và xuất dữ liệu. Thử các bộ lọc tenant, owner, trạng thái và ID của fixture để kiểm tra không xuất hiện tài nguyên ngoài phạm vi.

Với export bất đồng bộ, kiểm tra cả quyền tạo job, quyền xem trạng thái job và quyền tải kết quả. Một người có thể bị cấm gọi API đơn nhưng vẫn tải được file do người khác tạo nếu đường tải chỉ kiểm tra biết `jobId`.

Nếu hệ thống dùng liên kết tải có thời hạn hoặc capability riêng, oracle phải theo đúng phạm vi và thời hạn của cơ chế đó. Không mặc định mọi liên kết đều cần cùng loại session, nhưng phải kiểm tra liên kết không cấp phạm vi rộng hơn thiết kế và dữ liệu trả về đúng quyền.

### 9.4. Idempotency không phải giấy phép bỏ qua phân quyền

Một lỗi có thể xuất hiện khi hệ thống tra cache idempotency và trả kết quả cũ trước khi kiểm tra người gọi được xem kết quả ấy. Tạo ca:

1. Actor có quyền thực hiện thao tác với key test đã biết.
2. Actor khác hoặc actor ở tenant khác gửi cùng key.
3. Kiểm tra không trả tài nguyên hoặc dữ liệu ngoài quyền và không tạo hiệu ứng mới.

Phạm vi key, việc xử lý payload khác và quyền đọc trạng thái phải được đặc tả. Nếu quyền bị thu hồi sau khi một ý định đã được chấp nhận, việc hoàn tất ý định cũ phải theo hợp đồng xử lý đang chạy; điều đó không tự cho phép người gọi mới truy cập kết quả hoặc phát sinh ý định mới.

Một request có key khác cũng không được vượt kiểm tra quyền hoặc trạng thái. Deduplication không thay thế owner check, tenant check hay ràng buộc số tiền.

## 10. Ghi bằng chứng đủ để sửa lỗi và đánh giá tác động

### 10.1. Cấu trúc một ca kiểm thử có thể tái hiện

| Thành phần | Nội dung cần ghi |
|---|---|
| Quy tắc | Ai được làm gì, trên phạm vi nào và điều kiện nào |
| Actor | Danh tính tổng hợp, tenant, role/membership và quyền thực tế theo fixture |
| Baseline | Resource tồn tại, owner/requester, trạng thái, phiên bản policy và dữ liệu tiền liên quan |
| Đối chứng | Actor được phép thực hiện cùng loại thao tác trên baseline tương đương |
| Request | Method, route, payload và quan hệ ID cần thiết để tái hiện |
| Expected | Quyết định, dữ liệu được phép trả và hiệu ứng bị cấm |
| Observed | Response đã loại thông tin xác thực, trạng thái commit, outbox và giao dịch fake |
| Điều phối | Clock, điểm dừng, cache nóng/lạnh và lịch worker nếu ảnh hưởng kết quả |
| Giới hạn | Điều đã chứng minh và các đường chưa kiểm tra |

Thông tin xác thực không cần xuất hiện nguyên vẹn trong báo cáo. Lưu tên actor hoặc tham chiếu fixture và cách tạo phiên test, thay vì sao chép token/cookie. Dữ liệu minh họa nên đủ tái hiện mà không kèm thông tin người dùng thật.

### 10.2. Mô tả tác động bằng điều đã quan sát

Một phát hiện tốt có thể ghi:

> Khách hàng A dùng phiên của mình gọi thao tác duyệt yêu cầu hoàn 40.000 VND của chính họ. Yêu cầu chuyển từ `SUBMITTED` sang `APPROVED`, `approvedBy` nhận ID không có role tài chính và fake provider ghi nhận một khoản hoàn. Đối chứng với approver hợp lệ cho thấy fixture đủ điều kiện nghiệp vụ. Không cần đổi token hay can thiệp database trong bước tái hiện.

Mô tả này nêu rõ đường vào, đặc quyền thiếu và hiệu ứng đã chứng minh. Nếu chỉ đổi được trạng thái mà chưa tạo khoản tiền, phải ghi đúng mức đó; không tự suy ra tiền đã chuyển. Nếu chỉ thử một tenant và một action, ghi phạm vi ấy thay vì kết luận mọi tenant hoặc mọi chức năng đều bị ảnh hưởng.

Với lỗi dữ liệu trả về, ghi các trường hoặc nhóm dữ liệu bị lộ bằng giá trị tổng hợp. Với lỗi gán role, kiểm tra quyền mới thực sự được sử dụng theo hợp đồng cập nhật phiên/quyền; một chuỗi `role` hiển thị trong response nhưng không có hiệu lực chưa đủ chứng minh leo thang thành công.

### 10.3. Phân biệt sai chính sách và sai thực thi

Nếu tài liệu chưa nêu hỗ trợ viên có được tạo yêu cầu hoàn hay không, cần chốt quy tắc với người sở hữu nghiệp vụ. Không lấy hành vi đang có làm bằng chứng rằng hành vi ấy hợp lệ, và cũng không gán lỗi chỉ vì tên role có vẻ “thấp”.

Khi chính sách đã rõ, truy nguồn điều kiện thiếu: function permission, object permission, tenant, trường được sửa, trạng thái, hạn mức hoặc thời điểm đánh giá. Việc phân loại đúng giúp sửa ở lớp có trách nhiệm và tìm các đường tương tự cần hồi quy.

## 11. Xây hồi quy đủ mạnh

### 11.1. Các lỗi trong chính cách kiểm thử

| Cách kiểm thử yếu | Khoảng trống | Cách cải thiện |
|---|---|---|
| Chỉ dùng tài khoản quản trị | Không quan sát giới hạn của user thông thường | Tạo actor theo từng hàng của ma trận quyền |
| Gửi ID không tồn tại | Chỉ kiểm tra lookup thất bại | Dùng ID tồn tại và đối chứng chủ thể hợp lệ |
| Chỉ kiểm tra UI ẩn nút | API trực tiếp vẫn có thể thực hiện | Gọi đường nghiệp vụ thật với phiên quyền thấp |
| Dùng token bị sửa làm mọi ca vượt quyền | Nhánh chữ ký sai chặn trước kiểm tra quyền | Dùng token hợp lệ của actor có quyền thấp |
| Mọi ca bị cấm đồng thời sai amount hoặc state | Điều kiện dữ liệu che thiếu kiểm tra quyền | Baseline đủ điều kiện, thay một ranh giới chính mỗi ca |
| Chỉ assert `403` | Có thể đã ghi dữ liệu hoặc xếp công việc | So sánh trạng thái commit và hiệu ứng ngoài |
| Dùng cùng baseline sau đối chứng có ghi | Trạng thái đã đổi, kết quả không còn so sánh được | Reset độc lập trước từng nhánh |
| Test bulk chỉ có phần tử đầu bị cấm | Kiểm tra phần tử đầu sai vẫn có thể pass | Đổi vị trí và kết hợp phần tử thuộc các phạm vi |
| Quan sát bằng chính actor bị cấm | Không thấy dữ liệu không đồng nghĩa không có thay đổi | Dùng adapter quan sát test có thẩm quyền |
| Mock mọi kiểm tra quyền và repository | Không kiểm tra truy vấn, binding và transaction thực | Thêm integration test ở ranh giới có rủi ro |

### 11.2. Dùng property testing để mở rộng tổ hợp

Từ ma trận đã chốt, có thể sinh nhiều cặp actor/resource với oracle độc lập:

```text
Nếu hợp đồng xác định actor không được thực hiện action trên resource:
    không trả dữ liệu vượt quyền
    không có thay đổi nghiệp vụ được bảo vệ
    không có hiệu ứng bên ngoài trái phép
```

Điều kiện “không được” phải lấy từ mô hình chính sách hoặc fixture, không lấy từ chính response của API. Nếu dùng API để quyết định ca nào phải bị cấm, một implementation luôn cho phép có thể làm bộ test không còn ca âm nào.

Các biến sinh có ích gồm quan hệ cùng/khác owner, cùng/khác tenant, role liên quan, trạng thái, người yêu cầu/người duyệt và hạn mức. Tập dữ liệu cần có cả ca cho phép hợp lệ để phát hiện lỗi luôn từ chối hoặc fixture không thể thực thi.

Với chính sách cấp quyền cộng dồn phù hợp, có thể kiểm tra giảm grant không mở thêm quyền. Tuy nhiên, deny, tổ hợp role cấm và tách biệt nhiệm vụ có thể cần quan hệ riêng; không mặc định mọi phép thêm role đều phải giữ nguyên quyền. Property theo đối tượng và oracle nghiệp vụ vẫn cần thiết dù một property quan hệ đã pass.

### 11.3. Thử sức bộ test bằng thay đổi sai giả định

Bộ hồi quy nên thất bại nếu implementation:

- Bỏ kiểm tra role ở endpoint duyệt.
- Bỏ điều kiện tenant hoặc owner khi tìm resource.
- Chỉ kiểm tra đối tượng cha rồi cập nhật đối tượng con theo ID độc lập.
- Bind trực tiếp `approvedBy`, `status`, `role` hoặc `tenantId` từ payload không có quyền.
- Cho tenant admin cấp role ngoài tập được ủy quyền.
- Trả kết quả idempotency cho chủ thể khác trước khi kiểm tra phạm vi truy cập.
- Xếp outbox trước khi quyết định quyền rồi trả lỗi.
- Dùng quyết định cache từ user, action hoặc tenant khác.

Không cần dùng một công cụ mutation testing để đặt các câu hỏi này. Mỗi thay đổi sai tương ứng với một loại lỗi mà fixture và assertion phải có khả năng phân biệt. Code coverage cao nhưng thiếu các đối chứng ấy vẫn có thể bỏ lọt vượt quyền.

### 11.4. Đánh giá bao phủ theo tuple có ý nghĩa

Theo dõi các tổ hợp `(actor category, action, resource relation, tenant relation, state, entry point)` đã kiểm tra. Với action tài chính, thêm hạn mức và trạng thái ý định/lần thử khi chúng ảnh hưởng quyền hoặc bất biến.

Không cần duyệt mọi tích Descartes nếu chi phí quá lớn; ưu tiên các ranh giới có tác động và các đường dùng chung logic. Ghi rõ phần chưa bao phủ, đặc biệt endpoint thay thế, worker, bulk và dữ liệu lịch sử. Số lượng request hoặc số role đơn thuần không chứng minh chất lượng kiểm thử.

## 12. Bài tập áp dụng và tiêu chí hoàn thành

Chọn một luồng duyệt điều chỉnh giá hoặc hoàn tiền và thực hiện:

1. Viết ma trận quyền theo actor, action, owner, tenant, trạng thái và hạn mức nếu có.
2. Tạo fixture gồm hai khách cùng tenant, một khách tenant khác, approver từng tenant và người quản lý role có phạm vi giới hạn.
3. Chứng minh một đối chứng được phép thành công trên baseline hợp lệ; reset trước mỗi ca tiếp theo.
4. Dùng phiên khách hàng hợp lệ gọi chức năng duyệt trực tiếp, rồi thử actor có role đúng ở tenant sai.
5. Thay ID bằng tài nguyên tồn tại của khách khác; thử quan hệ cha/con không khớp.
6. Gửi các trường đặc quyền ngoài quyền của actor; kiểm tra giá trị lưu thực sự theo hợp đồng reject/ignore.
7. Kiểm tra tự gán role, cấp role ngoài phạm vi ủy quyền và thay role của thành viên tenant khác.
8. Thử tự duyệt, bỏ bước, lặp bước hoàn tất và trạng thái không đủ điều kiện.
9. Thêm một ca bulk trộn quyền, một ca worker hoặc export nếu ứng dụng có các đường đó.
10. Kiểm tra cache nóng/lạnh, retry dùng cùng key và thu hồi quyền theo điểm hiệu lực đã đặc tả.
11. Đối chiếu response, dữ liệu commit, khoản giữ chỗ, outbox và hiệu ứng của adapter ngoài; tách audit hợp lệ khỏi thay đổi nghiệp vụ bị cấm.
12. Lưu bằng chứng tái hiện bằng dữ liệu tổng hợp và đưa ca đã tìm được thành hồi quy cố định.

Hoàn thành khi mỗi ranh giới quan trọng có **quy tắc rõ ràng**, **đối chứng hợp lệ**, **ca vượt quyền có mục tiêu** và **oracle kiểm tra cả dữ liệu lẫn hiệu ứng**. Các chính sách chưa thống nhất phải được ghi thành câu hỏi cần chốt, thay vì chọn expected value tùy ý.

Kiểm thử leo thang đặc quyền có giá trị khi chứng minh được quyền của chủ thể gắn với đúng đối tượng và đúng bước nghiệp vụ trên mọi đường thực thi có liên quan. Kết hợp kiểm tra quyền với state machine, transaction, idempotency và quan sát hiệu ứng giúp ngăn những thao tác vượt quyền mà việc kiểm tra đăng nhập hoặc ẩn chức năng trên giao diện không thể bảo đảm.
