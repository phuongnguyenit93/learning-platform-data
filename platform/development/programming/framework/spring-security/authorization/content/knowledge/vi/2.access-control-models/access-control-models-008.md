# Phân tách nhiệm vụ và kiểm soát hành động nhạy cảm

## 1. Vấn đề: một người không nên tự thực hiện toàn bộ quy trình rủi ro cao

Trong một ứng dụng Spring Security, câu hỏi phân quyền không dừng ở “tài khoản này có `ROLE_MANAGER` hoặc `payment:approve` không?”. Khi một hành động có thể chuyển tiền, thay đổi quyền quản trị, xuất dữ liệu nhạy cảm hoặc xóa hồ sơ quan trọng, hệ thống còn phải kiểm tra **người yêu cầu**, **người xác nhận**, **đối tượng cụ thể**, **trạng thái quy trình**, **phạm vi được giao** và **bằng chứng phê duyệt**.

Giả sử một nhân viên tạo yêu cầu thanh toán 120 triệu đồng. Người đó đồng thời được gán quyền lập phiếu và quyền phê duyệt do kiêm nhiệm công việc. Nếu ứng dụng chỉ kiểm tra `hasAuthority("payment:approve")` thì họ có thể tự duyệt phiếu của mình. Kiểm tra quyền chức năng vẫn đúng theo cấu hình, nhưng chính sách kiểm soát rủi ro đã thất bại.

**Phân tách nhiệm vụ** (separation of duties, viết tắt **SoD**) là nguyên tắc ngăn một chủ thể nắm hoặc thực hiện những bước không được phép kết hợp trong cùng quy trình. Ý nghĩa thực tế là hạn chế khả năng một người tự tạo, tự phê duyệt và tự hoàn tất một giao dịch mà không có kiểm soát độc lập.

Một hệ thống tốt cần hai lớp:

1. **Hạn chế quyền được cấp:** không cấp những quyền xung đột cho cùng người khi chính sách yêu cầu tách hoàn toàn.
2. **Hạn chế cách sử dụng quyền:** ngay cả khi một người có nhiều quyền hợp lệ, không cho dùng chúng để thực hiện các bước xung đột trên **cùng một đối tượng hoặc giao dịch**.

SoD không thay thế xác thực, phân quyền hay kiểm toán. Nó là **ràng buộc bổ sung đối với việc cấp và sử dụng quyền**, đặc biệt có giá trị ở các thao tác nhạy cảm.

### Bức tranh trước và sau

| Quy trình dễ bị lạm dụng | Quy trình có kiểm soát |
| --- | --- |
| A tạo yêu cầu → A tự duyệt → A thực hiện thanh toán | A tạo yêu cầu → B độc lập xem xét → C thực hiện nếu đủ phê duyệt |
| Admin A tự tạo tài khoản đặc quyền rồi tự cấp quyền | A đề nghị nâng quyền → B duyệt phạm vi/thời hạn → hệ thống cấp và ghi log |
| Người quản lý tự sửa thông tin thanh toán rồi tự xác nhận | Người sửa và người phê duyệt thay đổi là hai chủ thể khác nhau |
| Chỉ kiểm tra quyền `approve` | Kiểm tra quyền + quan hệ với người tạo + tenant + hạn mức + trạng thái + bằng chứng |

Mục tiêu học: hiểu các dạng SoD, mô hình hóa chính sách, triển khai chốt chặn đáng tin trong Spring Security, kiểm thử hành động bị cấm và vận hành các ngoại lệ có kiểm soát.

## 2. Khái niệm và ranh giới cần phân biệt

### 2.1. Vai trò, quyền, nhiệm vụ và hành động

- **Vai trò (role):** nhóm trách nhiệm nghề nghiệp, ví dụ `PAYMENT_CREATOR` hoặc `PAYMENT_APPROVER`.
- **Quyền (permission/authority):** khả năng cụ thể như `payment:create`, `payment:submit`, `payment:approve`, `payment:execute`, `user:grant-privilege`.
- **Nhiệm vụ (duty):** một bước có ý nghĩa trong quy trình, như lập hồ sơ, kiểm tra hồ sơ, duyệt hoặc thực thi.
- **Hành động nhạy cảm (sensitive action):** thao tác có hậu quả lớn về tiền bạc, dữ liệu, quyền truy cập hoặc tính toàn vẹn hệ thống.
- **Ràng buộc xung đột (conflict constraint):** quy tắc cấm kết hợp hai vai trò/quyền/nhiệm vụ trong một phạm vi xác định.
- **Phê duyệt độc lập:** quyết định được đưa ra bởi một chủ thể đủ thẩm quyền, không chính là người tạo ra yêu cầu hoặc thực hiện bước bị cấm kết hợp.

Ví dụ, `ROLE_APPROVER` hoặc authority `payment:approve` mới là điều kiện cấp quyền chức năng; **không tự động chứng minh người duyệt độc lập với người lập**. Danh tính phải dựa trên ID ổn định do server xác thực, không dựa trên tên hiển thị hoặc email do phía client cung cấp.

### 2.2. Static SoD và Dynamic SoD

**Phân tách nhiệm vụ tĩnh (Static SoD, SSD):** hạn chế việc **gán** các vai trò/quyền xung đột cho cùng người.

Ví dụ: chính sách không cho một người đồng thời sở hữu `ROLE_AUDITOR` và `ROLE_AUDIT_SUBJECT_ADMIN`. Tại điểm cấp vai trò, ứng dụng phải từ chối việc tạo tổ hợp xung đột. Nếu có phân cấp vai trò hoặc nhóm quyền kế thừa, phải xét cả **quyền hiệu lực** chứ không chỉ vai trò gán trực tiếp.

**Phân tách nhiệm vụ động (Dynamic SoD, DSD):** hạn chế việc **thực hiện** hai nhiệm vụ xung đột trong một phiên làm việc, một quy trình hoặc trên cùng một đối tượng.

Ví dụ: một nhân viên có cả `payment:create` và `payment:approve` do luân phiên ca trực. Họ có thể lập giao dịch X và duyệt giao dịch Y, nhưng không được tự duyệt giao dịch X. Quy tắc này thường được gọi là **người lập–người duyệt (maker–checker)**.

| Tiêu chí | SoD tĩnh | SoD động |
| --- | --- | --- |
| Đối tượng kiểm soát | Phân quyền/gán vai trò | Lần thực hiện hành động, quy trình, đối tượng |
| Thời điểm | Khi cấp, đổi hoặc kế thừa quyền | Ngay khi hành động nhạy cảm được yêu cầu |
| Ví dụ | Không cấp đồng thời hai vai trò xung đột | Có cả hai quyền nhưng không tự duyệt phiếu đã lập |
| Dữ liệu cần | Vai trò, authority, phân cấp và nhóm xung đột | Danh tính, người tạo, lịch sử duyệt, tenant, trạng thái, hạn mức |
| Lỗi dễ gặp | Chỉ kiểm tra role gán trực tiếp | Chỉ kiểm tra vai trò mà bỏ quan hệ với giao dịch |

Đừng áp đặt một mô hình cho mọi tổ chức. SoD tĩnh dễ lý giải và quản trị nhưng có thể làm giảm linh hoạt; SoD động hỗ trợ luân phiên nhiệm vụ nhưng đòi hỏi trạng thái/hành vi được ghi nhận chính xác.

### 2.3. Maker–checker, four-eyes, dual control và nhiều cấp duyệt

Các thuật ngữ liên quan nhưng không hoàn toàn đồng nghĩa:

- **Maker–checker:** người khởi tạo và người kiểm tra/phê duyệt là các chủ thể độc lập; thường áp dụng cho một đối tượng cụ thể.
- **Four-eyes principle:** ít nhất hai người độc lập cùng tham gia xem xét một hành động; thường được hiện thực bằng maker–checker.
- **Dual control:** để thực hiện bước nhạy cảm cần sự tham gia/phê duyệt của ít nhất hai chủ thể có thẩm quyền theo chính sách; có thể yêu cầu đồng thời hoặc theo từng bước.
- **Nhiều cấp phê duyệt:** giao dịch có thể phải qua hai người duyệt, hai cấp tổ chức, hoặc một người duyệt và một người vận hành. Hai lượt bấm của cùng một người **không phải** hai chủ thể độc lập.

Số lần “approve” và số **danh tính riêng biệt** là hai đại lượng khác nhau. Nếu yêu cầu “hai người phê duyệt”, việc người B duyệt hai lần hoặc hai tài khoản cùng được điều khiển bởi một người có thể làm sai mục đích kiểm soát. Phải định nghĩa thế nào là độc lập ở tầng tổ chức: khác user ID, khác nhóm, khác cấp báo cáo, khác đơn vị hay không có lợi ích liên quan. Hệ thống chỉ kiểm chứng được những quan hệ được quản lý và ghi nhận đáng tin.

### 2.4. Ngăn ngừa, phát hiện và khôi phục

SoD là kiểm soát **ngăn ngừa**: chặn giao dịch trước khi gây hậu quả. Nhật ký kiểm toán, cảnh báo và đối soát là kiểm soát **phát hiện**: tìm các hành vi đã diễn ra hoặc bị từ chối. Hoàn tác/khôi phục là kiểm soát **khắc phục** khi có sai sót. Chỉ có log sau khi đã chuyển tiền không thay cho kiểm tra phê duyệt trước khi chuyển.

SoD giảm rủi ro do một người đơn lẻ lạm dụng quyền; không thể loại bỏ hoàn toàn thông đồng giữa nhiều người, danh tính bị chiếm đoạt hoặc một người điều khiển nhiều tài khoản. Vì vậy vẫn cần xác thực mạnh, quản lý danh tính, giám sát và đối soát độc lập.

## 3. Xác định hành động nào phải bảo vệ chặt hơn

Không phải API nào cũng cần hai người duyệt. Tăng kiểm soát có chi phí vận hành và có thể gây tắc nghẽn nếu đặt nhầm chỗ. Bắt đầu bằng phân loại tác động và xác định “ranh giới nguy hiểm” của chức năng.

| Nhóm hành động | Ví dụ | Kiểm soát thường cần xem xét |
| --- | --- | --- |
| Tiền và nghĩa vụ pháp lý | Chuyển tiền, hoàn tiền lớn, duyệt chi | Maker–checker, hạn mức, nhiều cấp duyệt, ghi bằng chứng |
| Thay đổi quyền truy cập | Tạo admin, cấp quyền đặc biệt, đổi vai trò | Phê duyệt độc lập, quyền tạm thời, kiểm toán |
| Dữ liệu nhạy cảm | Export hàng loạt, cấp quyền truy cập dữ liệu cá nhân | Phạm vi dữ liệu, phê duyệt theo mức rủi ro, hạn mức |
| Thay đổi cấu hình trọng yếu | Đổi secret, tắt kiểm soát, sửa điều kiện duyệt | Người đề nghị khác người duyệt, xác thực tăng cường |
| Xóa/đảo ngược khó phục hồi | Xóa vĩnh viễn, hủy giao dịch quyết toán | Hai bước xác nhận, chờ phê duyệt, cơ chế khôi phục |
| Hành động hằng ngày ít rủi ro | Xem dữ liệu công khai, đổi giao diện | Phân quyền thông thường; không mặc định yêu cầu hai người |

Cần phân biệt **độ nhạy của hành động** với **độ nhạy của dữ liệu**. Xem một bản ghi riêng lẻ có thể đủ quyền đọc; xuất toàn bộ hàng triệu bản ghi có rủi ro cao hơn nhiều dù cùng endpoint dữ liệu.

Một chính sách hợp lý phải trả lời:

1. Ai được **đề xuất** thao tác?
2. Ai được **phê duyệt**, có cần độc lập với người đề xuất không?
3. Có cần **hai người duyệt khác nhau** hoặc **hai cấp**?
4. Khi nào cần **xác thực lại hoặc MFA tăng cường (step-up authentication)**?
5. Ai được **thực thi** sau phê duyệt, và có được trùng người lập/người duyệt không?
6. Hạn mức giá trị, tenant, trạng thái, thời gian, thời hạn phê duyệt là gì?
7. Nếu dữ liệu đổi sau khi duyệt, phê duyệt cũ có còn hợp lệ không?

Câu hỏi cuối cực kỳ quan trọng: không thể duyệt nội dung A rồi cho phép sửa thành nội dung B và vẫn dùng phê duyệt của A.

## 4. Thiết kế chính sách: ví dụ giao dịch thanh toán

Giả sử ứng dụng có `PaymentRequest` với các trường tin cậy được lưu phía server:

| Trường | Ý nghĩa |
| --- | --- |
| `id` | ID giao dịch |
| `tenantId` | Tổ chức sở hữu giao dịch |
| `createdBy` | ID người lập, không tự ý sửa từ request |
| `amountVnd`, `beneficiary` | Số tiền và người thụ hưởng |
| `status` | DRAFT, PENDING, APPROVED, REJECTED, EXECUTED |
| `version` | Phiên bản của yêu cầu để chống dùng phê duyệt cũ |
| `approvals` | Các bản ghi phê duyệt có danh tính, thời gian, quyết định và phiên bản nội dung |
| `executedBy` | Chủ thể thực thi sau khi đủ điều kiện |

### 4.1. Ma trận nhiệm vụ và ràng buộc

Đây là **chính sách minh họa**, không phải mặc định Spring Security:

| Hành động | Authority | Điều kiện quan trọng | Thao tác khi đạt |
| --- | --- | --- | --- |
| Tạo nháp | `payment:create` | Tenant hợp lệ, phạm vi được giao | Tạo DRAFT với `createdBy` từ principal |
| Sửa nháp | `payment:edit` | Cùng tenant, là người lập, DRAFT | Sửa dữ liệu, tăng phiên bản |
| Gửi duyệt | `payment:submit` | Cùng tenant, là người lập, DRAFT, dữ liệu hợp lệ | DRAFT → PENDING, đóng nội dung cần duyệt |
| Phê duyệt | `payment:approve` | Cùng tenant, khác người lập, đủ hạn mức, PENDING, chưa duyệt lần này | Ghi sự kiện duyệt cho phiên bản hiện tại |
| Từ chối | `payment:reject` | Cùng tenant, có thẩm quyền, PENDING | PENDING → REJECTED, ghi lý do |
| Thực thi | `payment:execute` | Cùng tenant, đúng phạm vi, đủ phê duyệt còn hiệu lực, APPROVED | Thực thi một lần, cập nhật EXECUTED |

Thêm quy tắc minh họa về ngưỡng:

- Dưới 100 triệu: cần ít nhất **một người duyệt đủ hạn mức** và khác người lập.
- Từ 100 triệu trở lên: cần **hai người duyệt khác nhau**, đều khác người lập; tùy tổ chức có thể yêu cầu người thứ hai thuộc cấp quản lý khác.
- Mỗi người chỉ đóng góp **một quyết định** cho một phiên bản giao dịch; không thể bấm hai lần để tạo hai chữ ký duyệt.
- Người thực thi có thể phải khác người lập/người duyệt nếu quy trình quy định. Đây là **ràng buộc độc lập** với việc đã đủ số lượt duyệt.
- Nếu tiền, người thụ hưởng hoặc trường nhạy cảm thay đổi sau khi được duyệt, phải **làm mất hiệu lực phê duyệt cũ và duyệt lại**.

Ngưỡng chỉ là ví dụ để luyện thiết kế; tổ chức phải tự phê duyệt con số và điều kiện phù hợp.

### 4.2. Trạng thái là một phần của chính sách

```text
DRAFT --(submit, người lập)--> PENDING
PENDING --(reject, người có quyền)--> REJECTED
PENDING --(đủ duyệt độc lập, đúng version)--> APPROVED
APPROVED --(execute, quyền và giới hạn hợp lệ)--> EXECUTED

Không được:
  DRAFT -> EXECUTED
  PENDING -> EXECUTED nếu chưa đủ duyệt
  EXECUTED -> APPROVED lần nữa
  PENDING -> tự phê duyệt bởi người lập
```

Khi viết API, không cho client tự gửi `status="APPROVED"` và được server lưu trực tiếp. Các chuyển trạng thái phải nằm trong phương thức nghiệp vụ thực thi kiểm tra quyền và điều kiện. Một endpoint quản trị “sửa trực tiếp status” có thể trở thành đường vòng phá vỡ toàn bộ SoD.

### 4.3. Bất biến (invariant) cần bảo đảm

Một số bất biến có thể ghi thành điều kiện để kiểm thử:

```text
approval.approverId != payment.createdBy
approval.tenantId == payment.tenantId
approval.paymentVersion == payment.version
count(distinct validApproverId) >= requiredApproverCount(payment)
payment.status == APPROVED trước khi execute
execute không được hoàn tất hơn một lần cho cùng phiên bản giao dịch
```

Đếm người duyệt chỉ sau khi xác minh từng bản ghi phê duyệt được ghi qua luồng được ủy quyền, còn hiệu lực và gắn với **đúng phiên bản nội dung**. Không tin tập ID phê duyệt do client gửi.

### 4.4. Ai quyết định quyền?

Phân biệt rõ:

- **Chủ thể (principal):** ai đang đăng nhập? Identity provider hoặc cơ chế login kiểm chứng danh tính.
- **Permission:** được phép thực hiện loại hành động nào? Có thể biểu diễn bằng `GrantedAuthority`.
- **Ràng buộc nghiệp vụ:** có phải người lập, cùng tenant, đúng hạn mức, đúng trạng thái, không duyệt trùng, không vi phạm xung đột vai trò?
- **Quyết định cuối cùng:** chỉ cho phép khi **tất cả** điều kiện bắt buộc đúng. Nếu thiếu thông tin chính sách, mặc định từ chối.

RBAC diễn đạt quyền cơ sở; ABAC/quan hệ đối tượng diễn đạt tenant, số tiền, trạng thái và lịch sử phê duyệt. SoD có thể dùng cả hai loại điều kiện. Không có một annotation Spring Security mặc định nào tự hiểu “khác người lập của giao dịch này”.

## 5. Ví dụ Java 17 chạy độc lập: quyết định có được duyệt không?

Ví dụ này cố tình tách logic khỏi Spring để có thể kiểm tra nguyên tắc trước khi đưa vào framework. Chương trình thực hiện **đánh giá** quyền duyệt; nó chưa ghi cập nhật vào database và không thay thế giao dịch nguyên tử ở ứng dụng thật.

Lưu file với tên `SeparationOfDutiesDemo.java`:

```java
import java.util.Set;

public class SeparationOfDutiesDemo {
    enum Status { DRAFT, PENDING, APPROVED, EXECUTED }

    record Actor(
        long id,
        long tenantId,
        Set<String> authorities,
        long approvalLimitVnd,
        boolean active
    ) {}

    record Payment(
        long id,
        long tenantId,
        long createdBy,
        long amountVnd,
        Status status,
        Set<Long> approvedBy
    ) {}

    static boolean canApprove(Actor actor, Payment payment) {
        return actor != null
            && payment != null
            && actor.active()
            && actor.authorities() != null
            && payment.approvedBy() != null
            && actor.authorities().contains("payment:approve")
            && actor.tenantId() == payment.tenantId()
            && actor.id() != payment.createdBy()
            && payment.status() == Status.PENDING
            && payment.amountVnd() >= 0
            && payment.amountVnd() <= actor.approvalLimitVnd()
            && !payment.approvedBy().contains(actor.id());
    }

    // Chỉ đếm danh tính duyệt đã được server xác minh và lưu.
    // Phương thức này minh họa điều kiện số lượng, không tự ký duyệt.
    static boolean enoughApprovals(Payment payment) {
        if (payment == null || payment.approvedBy() == null) {
            return false;
        }
        int required = payment.amountVnd() >= 100_000_000 ? 2 : 1;
        return payment.approvedBy().size() >= required
            && !payment.approvedBy().contains(payment.createdBy());
    }

    public static void main(String[] args) {
        Actor maker = new Actor(
            10, 1, Set.of("payment:create", "payment:approve"),
            500_000_000, true
        );
        Actor reviewerA = new Actor(
            20, 1, Set.of("payment:approve"), 50_000_000, true
        );
        Actor reviewerB = new Actor(
            30, 1, Set.of("payment:approve"), 200_000_000, true
        );
        Actor otherTenant = new Actor(
            40, 2, Set.of("payment:approve"), 200_000_000, true
        );

        Payment small = new Payment(
            101, 1, 10, 40_000_000, Status.PENDING, Set.of()
        );
        Payment largeOneApproval = new Payment(
            102, 1, 10, 120_000_000, Status.PENDING, Set.of(20L)
        );
        Payment largeTwoApprovals = new Payment(
            102, 1, 10, 120_000_000, Status.PENDING, Set.of(20L, 30L)
        );
        Payment draft = new Payment(
            103, 1, 10, 40_000_000, Status.DRAFT, Set.of()
        );

        System.out.println("maker self-approve: "
            + canApprove(maker, small));
        System.out.println("independent reviewer: "
            + canApprove(reviewerA, small));
        System.out.println("reviewer over limit: "
            + canApprove(reviewerA, largeOneApproval));
        System.out.println("second independent reviewer: "
            + canApprove(reviewerB, largeOneApproval));
        System.out.println("cross tenant: "
            + canApprove(otherTenant, small));
        System.out.println("wrong status: "
            + canApprove(reviewerB, draft));
        System.out.println("one approval enough for large: "
            + enoughApprovals(largeOneApproval));
        System.out.println("two approvals enough for large: "
            + enoughApprovals(largeTwoApprovals));
        System.out.println("missing actor: "
            + canApprove(null, small));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac SeparationOfDutiesDemo.java
java SeparationOfDutiesDemo
```

Kết quả chuẩn (stdout):

```text
maker self-approve: false
independent reviewer: true
reviewer over limit: false
second independent reviewer: true
cross tenant: false
wrong status: false
one approval enough for large: false
two approvals enough for large: true
missing actor: false
```

Diễn giải:

- Người tạo có cả hai permission nhưng vẫn không được duyệt giao dịch của chính mình: **SoD động**, khác với việc cấm sở hữu đồng thời hai quyền (SoD tĩnh).
- Reviewer A duyệt được phiếu nhỏ, nhưng không được duyệt phiếu 120 triệu vì vượt hạn mức; A cũng đã có trong danh sách phê duyệt phiếu lớn.
- Reviewer B cùng tenant, khác người lập, còn hiệu lực, đủ hạn mức và chưa duyệt nên có thể đóng góp lượt duyệt thứ hai.
- Khác tenant, sai trạng thái hoặc thiếu actor đều bị từ chối.
- Một phiếu lớn cần hai ID duyệt khác nhau. `Set<Long>` minh họa việc đếm duy nhất; trong thực tế phải bảo đảm các bản ghi phê duyệt **được tạo qua chốt kiểm soát và gắn với phiên bản nội dung hiện tại**. Không được nạp một tập ID bất kỳ từ HTTP request rồi xem là đủ duyệt.

Đây là mô hình cố ý nhỏ. Khi triển khai cần xét quan hệ cấp quản lý, người được ủy quyền, hết hạn quyền, dấu vết quyết định, xác thực tăng cường và thay đổi song song trong kho dữ liệu.

## 6. Thực thi bằng Spring Security: quyền chức năng và quyền theo giao dịch

Các ví dụ sau dùng **Spring Security 6 trên Servlet/Spring MVC**, phù hợp cách cấu hình phổ biến của Spring Boot 3.x. Đây là **các đoạn mã tích hợp vào ứng dụng**, cần những lớp nghiệp vụ, repository và xác thực tương ứng; chúng không phải chương trình Java biên dịch độc lập như mục 5.

### 6.1. Kiểm tra ngay từ HTTP bằng `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class PaymentSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/api/payments")
                .hasAuthority("payment:create")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/submit")
                .hasAuthority("payment:submit")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/approve")
                .hasAuthority("payment:approve")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/execute")
                .hasAuthority("payment:execute")
            .requestMatchers(HttpMethod.POST, "/api/admin/privileges/grant")
                .hasAuthority("privilege:grant")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Cấu hình nêu các loại thao tác được phép theo authority, rồi mặc định từ chối. Nó **không thể tự phân biệt** người phê duyệt với người tạo cùng giao dịch, không biết hạn mức và không biết đã đủ hai người duyệt hay chưa. Những điều kiện này phải được kiểm tra ở tầng nghiệp vụ và kho dữ liệu.

Các matcher chỉ là ví dụ về API đã được xem xét; hệ thống thực cần bổ sung đúng các endpoint đọc/chỉnh sửa hợp lệ. Quy tắc mặc định `denyAll()` sẽ chặn các endpoint không liệt kê, kể cả endpoint đọc. Thứ tự matcher và phạm vi các `SecurityFilterChain` khác cần kiểm tra cẩn thận.

Cấu hình mẫu không đặt chính sách login, JWT, CORS hay CSRF. Với ứng dụng dùng cookie/phiên, không tắt CSRF theo thói quen. Nếu dùng OAuth2/JWT resource server, bảo đảm cách ánh xạ scope/claim sang `GrantedAuthority` khớp với chuỗi mà `hasAuthority(...)` kiểm tra. `hasRole("APPROVER")` trong cấu hình thông thường kiểm tra authority `ROLE_APPROVER`; nó không tương đương `hasAuthority("payment:approve")` nếu hệ thống chưa ánh xạ quyền.

### 6.2. Chốt kiểm tra ở service

Một thao tác phê duyệt cần diễn ra trong ranh giới nghiệp vụ thật sự và sử dụng dữ liệu server đáng tin. Ví dụ:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApprovalService {
    private final PaymentRepository payments;
    private final CurrentActor currentActor;
    private final PaymentPolicy policy;
    private final ApprovalRepository approvals;

    public PaymentApprovalService(
            PaymentRepository payments,
            CurrentActor currentActor,
            PaymentPolicy policy,
            ApprovalRepository approvals) {
        this.payments = payments;
        this.currentActor = currentActor;
        this.policy = policy;
        this.approvals = approvals;
    }

    @Transactional
    @PreAuthorize("hasAuthority('payment:approve')")
    public void approve(long paymentId) {
        var actor = currentActor.requireAuthenticated();
        var payment = payments.findByIdForUpdate(paymentId)
            .orElseThrow(() -> new PaymentNotFoundException(paymentId));

        if (!policy.canApprove(actor, payment)) {
            throw new AccessDeniedException("Approval denied");
        }

        approvals.insertDecision(
            payment.id(),
            payment.version(),
            actor.id(),
            "APPROVE"
        );
        if (policy.hasEnoughApprovals(payment)) {
            payment.markApproved();
        }
    }
}
```

Đây là **mã khung minh họa**. `PaymentRepository`, `CurrentActor`, `PaymentPolicy`, `ApprovalRepository`, `PaymentNotFoundException` và các phương thức miền là giao diện/lớp của ứng dụng cần hiện thực. Phương thức `insertDecision` phải bảo đảm dữ liệu không bị ghi trùng; `hasEnoughApprovals(payment)` trong hệ thống thật phải **đọc/đếm lại quyết định sau khi ghi** theo cùng phiên bản và giao dịch. Nếu `payment.approvals` là bộ sưu tập lưu trong bộ nhớ trước khi insert, phải nạp lại hoặc cập nhật nhất quán trước khi đếm, không giả định đối tượng JPA đã tự cập nhật.

Nếu dùng khóa bi quan với Spring Data JPA, repository có thể cung cấp truy vấn kiểu:

```java
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PaymentRepository
        extends JpaRepository<PaymentRequest, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from PaymentRequest p where p.id = :id")
    Optional<PaymentRequest> findByIdForUpdate(@Param("id") Long id);
}
```

Khóa một bản ghi hỗ trợ tuần tự hóa cập nhật cùng giao dịch nếu cơ sở dữ liệu và phạm vi transaction bảo đảm điều đó; **không tự nó bảo vệ toàn bộ bộ đếm nếu quyết định duyệt được ghi ở bảng khác mà không đồng bộ theo cùng khóa**. Nên kết hợp unique constraint cho `(payment_id, version, approver_id)`, trạng thái chuyển có điều kiện, transaction thích hợp và thiết kế idempotent. Nếu thao tác gửi tiền đi hệ thống bên ngoài, cần cơ chế chống thực thi trùng ngay cả khi request bị retry.

Có thể áp dụng optimistic locking với `@Version` thay thế, nhưng phải xử lý xung đột và tính lại điều kiện; không “retry mù” khiến một hành động bị thực thi ngoài ý muốn.

### 6.3. Không cho phép đi vòng điểm kiểm tra

Với method security, bật `@EnableMethodSecurity` và hiểu rằng `@PreAuthorize` thường được thực thi qua proxy Spring AOP. Lời gọi từ một phương thức sang phương thức khác trên **cùng instance** có thể tránh proxy (self-invocation). Vì vậy phải thiết kế các điểm vào công khai hợp lý, bảo vệ dịch vụ nghiệp vụ và giữ các bất biến ở lớp dữ liệu, không coi annotation là bằng chứng đủ cho mọi luồng.

Cần kiểm kê các đường đi khác ngoài REST: message consumer, batch job, GraphQL, WebSocket, admin console, export, script vận hành và tài khoản dịch vụ. Một job nội bộ không nên mặc định được tin tưởng chỉ vì không đi qua HTTP filter. Mỗi điểm nhạy cảm phải áp dụng chính sách được thiết kế rõ.

Đặc biệt, controller không nên nhận `createdBy`, `approvedBy`, `tenantId` hoặc `status` rồi ghi trực tiếp thành sự thật. Nếu client chọn tenant đang thao tác, hệ thống phải xác nhận principal thuộc tenant đó và có quyền trên tài nguyên.

### 6.4. Kiểm soát đường cấp quyền (SoD tĩnh)

Để ngăn cấp đồng thời hai vai trò xung đột, kiểm tra phải chạy **khi gán role**, không chỉ khi người dùng gọi API. Ví dụ, policy không cho người có vai trò `AUDITOR` nhận quyền quản lý tài khoản họ đang kiểm toán.

Một mô hình kiểm tra:

```text
grantRole(targetUser, candidateRole):
  1. Xác minh người yêu cầu có quyền cấp vai trò này.
  2. Tải vai trò/quyền hiệu lực hiện có của targetUser.
  3. Xét phân cấp vai trò và nhóm quyền xung đột.
  4. Từ chối nếu tổ hợp mới vi phạm SoD tĩnh.
  5. Nếu quyền nhạy cảm, yêu cầu phê duyệt độc lập.
  6. Áp dụng thay đổi trong giao dịch nhất quán.
  7. Ghi audit: ai đề nghị, ai duyệt, ai được cấp, vì sao.
```

Phân tách người **đề nghị nâng quyền**, người **duyệt nâng quyền** và chủ thể **được nâng quyền** có thể cần cả SoD động. Đừng tạo ngoại lệ âm thầm cho `ROLE_ADMIN`; quyền phá rào phải được quy định rõ ràng và kiểm toán riêng.

## 7. Hành động nhạy cảm cần kiểm soát nhiều lớp

SoD là thành phần trọng tâm nhưng không phải tất cả. Khi hậu quả cao, cần các lớp bổ sung được ràng buộc vào **hành động và nội dung cụ thể**.

### 7.1. Xác thực tăng cường và xác nhận có ngữ cảnh

Người dùng đã đăng nhập có thể cần xác thực lại hoặc MFA (step-up authentication) trước khi phê duyệt khoản tiền lớn, cấp quyền quản trị hoặc xuất dữ liệu nhạy cảm. Xác thực tăng cường giúp giảm rủi ro phiên bị chiếm đoạt, nhưng **không chứng minh sự độc lập của người duyệt**.

Thông báo phê duyệt nên hiển thị thông tin cốt lõi như số tiền, người thụ hưởng, tenant, người lập và phạm vi hiệu lực. Chỉ hiển thị “Bạn có đồng ý?” mà không ràng buộc quyết định với phiên bản nội dung sẽ tạo điều kiện cho thay đổi sau duyệt.

### 7.2. Phê duyệt phải gắn với đúng nội dung và thời hạn

Một bản ghi quyết định nên chứa:

- ID người duyệt đã được xác thực, quyền/phạm vi hiệu lực tại thời điểm duyệt.
- ID giao dịch và **phiên bản nội dung được duyệt**, hoặc dấu vân tay nội dung đã chuẩn hóa khi phù hợp.
- Quyết định, thời gian, trạng thái và lý do (nếu cần).
- Thời điểm hết hạn, loại phê duyệt và mức xác thực tăng cường nếu chính sách yêu cầu.

Nếu thay số tiền hoặc tài khoản thụ hưởng sau phê duyệt, quy trình phải quay lại bước xác nhận phù hợp. Một dấu vân tay chỉ có ý nghĩa nếu được tính từ dữ liệu chuẩn hóa đáng tin và gắn với quyết định ở server; **không tin giá trị hash do client gửi**.

### 7.3. Hạn mức, hạn chế tần suất và kích hoạt theo rủi ro

Nâng mức kiểm soát có thể dựa trên tiền, loại dữ liệu, số lượng bản ghi, tài khoản thụ hưởng mới, thời điểm bất thường hoặc hành động đặc quyền. Tuy nhiên, đừng dùng “rủi ro thấp” để bỏ qua ràng buộc SoD bắt buộc do chính sách nghiệp vụ đặt ra.

Ví dụ: dưới một ngưỡng đã phê duyệt cần một người duyệt khác người lập; trên ngưỡng cần hai người duyệt độc lập; chuyển tới tài khoản thụ hưởng mới có thể cần xác thực tăng cường. Các luật này phải được viết thành chính sách có thể kiểm thử, không nằm rải rác trong controller.

### 7.4. Tài khoản đặc quyền và quyền khẩn cấp

Đôi khi hệ thống cần chế độ xử lý khẩn cấp (break-glass) khi quy trình duyệt thông thường không sẵn sàng. Đây là **ngoại lệ có quy trình**, không phải quyền bỏ qua mọi kiểm soát:

- Người kích hoạt phải có thẩm quyền rõ, nêu lý do và chứng minh tình huống cần thiết.
- Quyền có phạm vi nhỏ, thời hạn ngắn, tự hết hiệu lực; hạn chế tác vụ được phép.
- Có ghi log mức độ chi tiết phù hợp, cảnh báo độc lập và rà soát sau sự kiện.
- Không dùng tài khoản chung làm danh tính thay thế cho hai người độc lập.
- Nếu chính sách không cho phép break-glass với một loại giao dịch, hệ thống phải giữ nguyên ràng buộc đó ngay cả trong khẩn cấp.

Quyền được cấp theo nhu cầu trong thời gian ngắn (just-in-time privilege) và rà soát định kỳ giúp giảm rủi ro đặc quyền tích lũy, nhưng vẫn phải kiểm soát những ai được quyền yêu cầu và phê duyệt đặc quyền đó.

## 8. Kiểm thử: chứng minh cả chặn quyền lẫn giữ nguyên dữ liệu

Kiểm thử thành công một giao dịch hợp lệ là cần thiết nhưng chưa đủ. Các ca quan trọng nhất của SoD là những thao tác trông có vẻ hợp lệ ở lớp authority nhưng vẫn **phải bị từ chối bởi quan hệ giữa các chủ thể**.

### 8.1. Ma trận kiểm thử tối thiểu

| Kịch bản | Kỳ vọng | Bất biến cần xác nhận |
| --- | --- | --- |
| Người lập có `payment:approve` tự duyệt giao dịch | Từ chối | Không phát sinh Approval |
| Người duyệt khác người lập, cùng tenant, đúng hạn mức | Cho phép | Ghi một quyết định đúng version |
| Người duyệt khác tenant nhưng có authority | Từ chối | Không lộ dữ liệu hoặc ghi quyết định |
| Người duyệt vượt hạn mức | Từ chối | Trạng thái không đổi |
| Người duyệt gửi lại lần hai | Từ chối hoặc idempotent theo hợp đồng API | Không có hai lượt duyệt của cùng người |
| Hai danh tính khác nhau duyệt phiếu lớn | Đủ điều kiện nếu mọi rule đúng | Đếm đúng hai bản ghi độc lập |
| Hai tài khoản do cùng người kiểm soát theo chính sách cấm | Từ chối/đưa đi rà soát theo mô hình danh tính | Không coi hai tài khoản là hai người độc lập |
| Thanh toán bị sửa sau lượt duyệt | Phê duyệt cũ không còn hiệu lực | Không execute bằng bản duyệt cũ |
| Người đã bị thu hồi quyền cố duyệt | Từ chối | Không phát sinh quyết định |
| Hai request approve chạy đồng thời | Kết quả nhất quán | Không bỏ qua giới hạn hoặc tạo trùng |
| Client gửi `createdBy` giả | Bỏ qua hoặc từ chối theo hợp đồng | Dùng principal/server data thật |
| Endpoint phụ hoặc job gọi trực tiếp service | Bảo vệ tương đương | Không đi vòng bằng kênh khác |
| Người không có `payment:approve` | Từ chối | Không cập nhật payment/approval |
| Hệ thống chính sách/DB bị lỗi | Không cho phép tự động | Không phát sinh thực thi trái phép |

Khi hệ thống cần hai cấp duyệt cụ thể, thêm test “hai người cùng cấp vẫn không đủ” và “người được ủy quyền hết hạn không còn hợp lệ”. Mỗi ràng buộc trong ma trận nghiệp vụ cần ít nhất một trường hợp vượt qua và một trường hợp vi phạm.

### 8.2. Kiểm thử HTTP, dịch vụ và dữ liệu

Với Spring MVC, `MockMvc` và `spring-security-test` có thể kiểm tra matcher, authority, đăng nhập và CSRF. Ví dụ **đoạn gọi đặt bên trong một lớp JUnit test đã có MockMvc, controller và fixture phù hợp**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Ví dụ minh họa trong một phương thức @Test:
mockMvc.perform(post("/api/payments/101/approve")
        .with(user("maker")
            .authorities(new SimpleGrantedAuthority("payment:approve")))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

Trong đoạn minh họa, `SimpleGrantedAuthority` là `org.springframework.security.core.authority.SimpleGrantedAuthority`; hệ thống test phải ánh xạ `maker` tới **ID người tạo thật** và fixture 101 phù hợp. Kết quả 403 đến từ chính sách SoD chỉ khi request vượt qua lớp CSRF, đường dẫn tồn tại và service thực sự từ chối việc tự duyệt.

Một bài test HTTP trả 403 **không tự chứng minh** SoD đúng: 403 cũng có thể xuất phát từ thiếu token CSRF hoặc sai matcher. Test cần xác định nơi từ chối và kiểm tra dữ liệu sau call: không có bản ghi duyệt, số lượt không tăng, trạng thái và version không thay đổi.

Kiểm thử dịch vụ nên gọi trực tiếp entrypoint nghiệp vụ thông qua cấu hình bảo mật tương ứng. Có thể kiểm thử `PaymentPolicy` thuần túy để dễ phát hiện sai logic; sau đó kiểm thử tích hợp thật để xác minh transaction, constraint dữ liệu, concurrency và method security. Tránh chỉ mock repository đến mức không bao giờ phát hiện lỗi SQL hoặc unique constraint.

### 8.3. Kiểm thử hành vi đồng thời và khôi phục

Hai request phê duyệt có thể đến gần như cùng lúc; nếu cả hai đọc “chưa có ai duyệt” rồi cùng ghi, hệ thống có thể đếm sai hoặc tạo bản ghi trùng. Kiểm thử với transaction thực và dữ liệu giống sản xuất để bảo đảm:

- Cùng một principal không thể tạo hai quyết định cho cùng giao dịch/phiên bản.
- Hai người khác nhau được ghi nhận đầy đủ, đúng thứ tự logic của quy trình.
- Chỉ trạng thái hợp lệ mới chuyển tiếp; thao tác execute không chạy hai lần khi client retry.
- Một bản ghi thay đổi version khiến phê duyệt gắn với version cũ mất hiệu lực.
- Khi DB báo lỗi, không có trạng thái “đã duyệt” một phần nhưng tiền vẫn được chuyển.

Với thao tác gọi hệ thống bên ngoài, transaction database đơn thuần không thể tự hoàn tác giao dịch từ một nhà cung cấp thanh toán. Có thể cần idempotency key, outbox/inbox, trạng thái xử lý rõ và đối soát để bảo đảm không gửi lệnh hai lần hoặc bỏ sót kết quả. Đây là phần **thực thi an toàn của hành động nhạy cảm**, không chỉ là kiểm tra permission.

### 8.4. Phân biệt mã lỗi với quyết định quyền

- **401** thường dùng khi API yêu cầu xác thực nhưng không có danh tính hợp lệ.
- **403** thường dùng khi đã xác thực nhưng không đủ quyền hoặc vi phạm SoD.
- **404** có thể dùng khi muốn tránh tiết lộ sự tồn tại của đối tượng ngoài phạm vi.
- **409** có thể phù hợp khi trạng thái/phiên bản thay đổi hoặc đã có quyết định duyệt.
- **5xx** là lỗi kỹ thuật, không được biến thành mặc định cho phép khi dịch vụ quyền gặp sự cố.

Mã HTTP là một phần hợp đồng API; điều bắt buộc phải kiểm tra là **không thực hiện hành động trái chính sách**, dù response được thiết kế theo cách nào.

## 9. Vận hành: kiểm soát rủi ro khi quyền và tổ chức thay đổi

Một chính sách SoD có thể bị phá vỡ về sau khi nhân sự chuyển nhóm, vai trò mới kế thừa thêm permission, quản trị viên được cấp quyền khẩn cấp hoặc quy trình phê duyệt thay đổi. Vận hành cần bảo đảm các ràng buộc tiếp tục đúng.

### 9.1. Quản lý vòng đời quyền

- **Trước khi cấp:** kiểm tra xung đột vai trò hiệu lực, người đề nghị và người phê duyệt, phạm vi tenant và thời hạn quyền.
- **Trong khi sử dụng:** kiểm tra quan hệ với giao dịch ở thời điểm thao tác; log người lập, người duyệt và phiên bản nội dung.
- **Khi chuyển nhiệm vụ:** thu hồi quyền không còn cần thiết; rà soát vai trò được kế thừa và quyền đặc biệt.
- **Khi quyền bị thu hồi:** bảo đảm quyết định tiếp theo nhìn thấy quyền hiệu lực mới theo cơ chế phiên/token/cache của hệ thống. Nếu JWT chứa quyền cũ còn hạn, cập nhật DB **không tự làm JWT cũ hết hiệu lực**; cần chiến lược phù hợp như token ngắn, tra cứu quyền động hoặc thu hồi phiên.
- **Kiểm tra định kỳ:** đối chiếu vai trò thực tế với quy tắc xung đột; phát hiện người vừa sở hữu quyền lập vừa duyệt ở phạm vi bị cấm hoặc người có nhiều tài khoản dùng chung.

### 9.2. Nhật ký kiểm toán

Một sự kiện phê duyệt hoặc từ chối nên ghi tối thiểu:

| Dữ liệu | Tại sao cần? |
| --- | --- |
| Thời điểm, correlation/request ID | Xâu chuỗi một giao dịch qua nhiều dịch vụ |
| Principal và danh tính nghiệp vụ | Ai thực hiện |
| Tenant, tài nguyên, phiên bản được xét | Đã duyệt đối tượng/nội dung nào |
| Hành động và quyết định | Đã đề nghị, duyệt, từ chối hay thực thi |
| Lý do từ chối có mã hóa ổn định | Phát hiện vi phạm SoD, sai tenant, hết hạn, vượt hạn mức |
| Phiên bản chính sách và loại xác thực | Giải thích quyết định tại thời điểm đó |
| Tình trạng thực thi | Phân biệt “đã duyệt” và “đã chuyển tiền/xóa dữ liệu” |

Hạn chế ghi token, cookie, dữ liệu bí mật, số tài khoản đầy đủ hoặc payload nhạy cảm không cần thiết. Kiểm soát quyền đọc và khả năng sửa log; điều tra sẽ vô nghĩa nếu người bị điều tra có thể tự xóa hoặc sửa bằng chứng.

### 9.3. Cảnh báo và kiểm soát bổ sung

Theo dõi tỷ lệ tự duyệt bị từ chối, cố duyệt vượt hạn mức, nhiều lần thử một giao dịch, thay đổi vai trò nhạy cảm, người phê duyệt mới bất thường và tần suất dùng chế độ khẩn cấp. Cảnh báo phải phân biệt thao tác người dùng nhầm với chuỗi hành vi nguy hiểm để giảm nhiễu.

SoD không tự ngăn thông đồng; cần đối soát giao dịch, phát hiện bất thường, kiểm tra mối quan hệ giữa người lập–duyệt, kiểm tra phân cấp tổ chức và giới hạn quyền truy cập dữ liệu. Tùy quy định, có thể yêu cầu người duyệt ở đơn vị khác hoặc một bộ phận kiểm soát độc lập.

### 9.4. Thay đổi chính sách một cách an toàn

Khi thay ngưỡng phê duyệt, thêm cấp duyệt hoặc thay cấu trúc tổ chức:

1. Mô tả thay đổi bằng chính sách rõ ràng và kiểm tra tác động tới dữ liệu đang chờ.
2. Cập nhật điều kiện cấp quyền, quyền hiệu lực, kiểm tra đối tượng và chuyển trạng thái.
3. Quy định hồ sơ đang PENDING phải theo luật cũ hay mới; nếu cần, bắt duyệt lại có kiểm soát.
4. Viết test cho ngoại lệ và đường từ chối; chạy kiểm thử đồng thời với database thật.
5. Triển khai có theo dõi mã lỗi, cảnh báo, audit và khả năng quay lại.
6. Xác nhận lại mọi bất biến sau triển khai: không tự duyệt, đúng tenant, đúng hạn mức, đủ số người độc lập, đúng version.

Đừng vá lỗi bằng cách thêm ngoại lệ `if (isAdmin) allow` mà không đưa ngoại lệ vào chính sách. Chính sách bảo mật phải có người chịu trách nhiệm, được giải thích và kiểm chứng.

## 10. Lỗi thường gặp và cách sửa từ nguyên nhân

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Kiểm tra `ROLE_APPROVER` rồi cho duyệt ngay | Vai trò không nói ai đã lập hồ sơ | Kiểm tra `createdBy != approverId` và toàn bộ điều kiện đối tượng |
| SoD tĩnh chỉ xét vai trò gán trực tiếp | Quyền xung đột có thể đến từ role kế thừa | Xét quyền hiệu lực và ma trận xung đột khi cấp quyền |
| Coi hai lần bấm là hai người duyệt | Một người tạo nhiều quyết định | Ràng buộc danh tính duy nhất theo giao dịch/version |
| Dựa vào tên/địa chỉ email client gửi để so người | Dữ liệu có thể đổi hoặc giả mạo | Dùng ID nội bộ ổn định từ principal/server data |
| Quên ràng buộc tenant | Người ở tổ chức khác có quyền chức năng vẫn duyệt | Kiểm tra tenant và quan hệ tài nguyên |
| Cho sửa số tiền sau phê duyệt mà không duyệt lại | Kết quả duyệt không còn áp dụng cho nội dung mới | Gắn quyết định vào version và vô hiệu hóa khi đổi dữ liệu |
| Đếm approval trong bộ nhớ cũ | Trạng thái sau insert có thể không phản ánh bản ghi mới | Đồng bộ trạng thái hoặc truy vấn đếm lại trong transaction |
| Chỉ dựa vào `@PreAuthorize` trên self-invocation | Có đường gọi bỏ qua proxy | Đặt chốt trên service entrypoint thực tế và dữ liệu |
| Không xử lý hai lượt duyệt đồng thời | Trùng bản ghi, vượt ngưỡng hoặc chuyển trạng thái sai | Transaction, constraint, khóa/version và idempotency |
| MFA được xem như thay thế người duyệt thứ hai | Một người xác thực nhiều lần vẫn là một người | Tách xác thực mạnh khỏi SoD |
| Quyền khẩn cấp mở mọi hành động vĩnh viễn | Ngoại lệ trở thành đường vòng cố định | Phạm vi hẹp, thời hạn, cảnh báo và rà soát |
| Chỉ kiểm tra ở màn hình/web | API khác hoặc job vẫn thao tác được | Chặn tại nghiệp vụ/dữ liệu trên mọi đường |
| Xem đủ lượt duyệt là đã “thực thi an toàn” | Có thể thực thi trùng hoặc mất kết quả hệ thống ngoài | Kiểm soát trạng thái, idempotency và đối soát |

## 11. Thực hành theo từng mức

### Mức 1 — Phân biệt SoD tĩnh và động

Vẽ hai ma trận: một ma trận cặp role không được cùng cấp và một ma trận các bước không được cùng một người thực hiện trên một giao dịch. Trả lời: “Người có `payment:create` và `payment:approve` có luôn vi phạm SoD không?”. **Không nhất thiết**: SoD tĩnh có thể cấm cả hai quyền cùng tồn tại; SoD động có thể cho phép có cả hai nhưng cấm tự duyệt cùng giao dịch.

### Mức 2 — Chứng minh bằng Java

Chạy `SeparationOfDutiesDemo.java`. Thêm trường `requiresIndependentDepartment` và thuộc tính phòng ban của actor; viết thêm điều kiện người lập/người duyệt phải khác bộ phận khi chính sách yêu cầu. Tạo ca cho phép và từ chối, đảm bảo không làm hỏng các trường hợp hiện có.

### Mức 3 — Xây API duyệt

Xây endpoint `POST /api/payments/{id}/approve` với authority rõ, lấy principal từ server, kiểm tra tenant/limit/maker và ghi quyết định theo version. Test hai user cùng authority nhưng khác quan hệ với giao dịch. Thử cố gửi `createdBy` giả trong body rồi xác minh không thay đổi quyết định.

### Mức 4 — Chống race condition

Dùng hai request đồng thời cùng người duyệt và hai request từ hai người duyệt khác nhau. Chứng minh không có bản ghi trùng, số người duyệt chính xác và state machine chỉ chuyển trạng thái hợp lệ. Nếu có thao tác ra hệ thống ngoài, thêm test retry và idempotency.

### Mức 5 — Quyền đặc biệt và vận hành

Thiết kế quy trình đề nghị cấp quyền `privilege:grant`: người đề nghị, người duyệt, chủ thể nhận quyền, phạm vi/thời hạn và audit. Mô tả chế độ khẩn cấp và ít nhất hai cảnh báo cần phát hiện. Giải thích điều gì xảy ra nếu người duyệt nghỉ việc hoặc quyền của họ bị thu hồi khi một hồ sơ còn đang chờ.

## 12. Tự kiểm tra cuối bài

1. **Tại sao có quyền `payment:approve` vẫn có thể bị từ chối?** Vì còn ràng buộc khác người lập, cùng tenant, đúng trạng thái, hạn mức, lịch sử phê duyệt và version.
2. **SoD tĩnh khác SoD động ở đâu?** SoD tĩnh cấm cấu hình quyền xung đột; SoD động cấm kết hợp thao tác xung đột trên phiên/quy trình/đối tượng cụ thể.
3. **Hai lần nhấn Approve của cùng một người có tính là hai phê duyệt độc lập không?** Không. Phải kiểm tra danh tính và ngữ cảnh độc lập theo chính sách.
4. **Một người xác thực MFA hai lần có đáp ứng four-eyes không?** Không; MFA xác thực cùng một người, không tạo người thứ hai.
5. **Sửa người thụ hưởng sau khi đủ lượt duyệt có được execute không?** Không thể dùng nguyên phê duyệt cũ; phải xác nhận lại nội dung mới theo chính sách.
6. **Vì sao permission check trên HTTP chưa đủ?** HTTP không biết đầy đủ lịch sử giao dịch, tenant, người lập, hạn mức và trạng thái; còn có các đường vào khác.
7. **Chỉ dùng transaction có chặn được mọi lỗi phê duyệt đồng thời không?** Không. Cần thiết kế khóa hoặc version, constraint dữ liệu và xử lý đúng phạm vi transaction.
8. **Hệ thống phải làm gì khi không kiểm tra được chính sách cho hành động nhạy cảm?** Không tự cho phép; trả lỗi phù hợp và giữ bất biến dữ liệu.

**Ghi nhớ:** phân tách nhiệm vụ là kiểm soát **ai có thể kết hợp những bước nào, trên đối tượng nào và vào thời điểm nào**. Khi triển khai với Spring Security, hãy bắt đầu từ xung đột nghiệp vụ, diễn đạt thành điều kiện được kiểm chứng phía server, đặt chốt ở các đường thực thi thực tế và kiểm thử rằng không ai có thể tự tạo–tự duyệt–tự thực thi ngoài chính sách.