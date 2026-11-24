# Role approval threshold — Ngưỡng phê duyệt theo vai trò

## 1. Vai trò nào thực sự đủ thẩm quyền?

Trong chương **Approval Limits**, ngưỡng phê duyệt theo vai trò xác định một yêu cầu phải được những vai trò nào chấp thuận, trong phạm vi nào và với điều kiện gì trước khi được thực thi.

Ví dụ, một khoản chi nhỏ có thể cần người giám sát; khoản lớn cần quản lý tài chính; khoản rủi ro cao cần cả người chịu trách nhiệm tài chính và người kiểm soát rủi ro độc lập.

Câu hỏi cần trả lời không chỉ là “người này có role APPROVER không?”, mà gồm:

- Vai trò đó có quyền duyệt đúng loại thao tác không?
- Quyền có áp dụng cho tenant, đơn vị và đối tượng cụ thể không?
- Thẩm quyền số tiền, mức rủi ro và thời hạn có đủ không?
- Chính sách cần một người hay nhiều người thuộc các nhóm trách nhiệm khác nhau?
- Người đã lập yêu cầu, người được hưởng lợi hoặc người được ủy quyền có bị loại không?
- Tập phê duyệt còn hợp lệ khi yêu cầu chuẩn bị tạo tác động nghiệp vụ không?

Một endpoint chỉ dùng `hasRole("APPROVER")` thường mới kiểm tra được điều kiện rất thô. Nếu không gắn vai trò với đối tượng, nội dung và trạng thái giao dịch, kẻ lạm dụng vẫn có thể vượt quy trình.

## 2. Tách chính sách yêu cầu khỏi quyền của người thao tác

### 2.1. Hai quyết định khác nhau

**Chính sách của yêu cầu** quyết định cần loại bằng chứng nào. Nó được xác định từ dữ liệu nghiệp vụ đã xác minh: loại thao tác, số tiền, người hưởng, mức rủi ro và phiên bản chính sách.

**Quyền của người thao tác** quyết định người đó có thể cung cấp bằng chứng cho phần nào của chính sách.

~~~text
Dữ liệu yêu cầu đã xác minh
    -> chính sách phê duyệt cần đáp ứng

Danh tính + quyền được cấp + phạm vi + điều kiện hiện tại
    -> những trách nhiệm người này được phép đảm nhận

Tập bằng chứng hợp lệ
    -> đã đủ điều kiện chuyển trạng thái hay chưa
~~~

Không chọn tuyến phê duyệt dựa trên vai trò mà người gọi tự khai. Một người có quyền thấp không làm yêu cầu tự chuyển xuống tuyến thấp; một người có quyền quản trị cũng không làm yêu cầu tự mất điều kiện kiểm soát độc lập.

### 2.2. Phân biệt bốn thành phần

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Vai trò | Nhóm trách nhiệm và quyền được cấp | FINANCE_MANAGER |
| Phạm vi | Đối tượng hoặc miền mà quyền áp dụng | Tenant A, chi nhánh B, lệnh chi nhà cung cấp |
| Điều kiện thẩm quyền | Ràng buộc kèm theo quyền | Tiền tệ VND, tối đa 100 triệu, còn hiệu lực |
| Yêu cầu phối hợp phê duyệt | Cách nhiều bằng chứng cùng đáp ứng chính sách | Một người tài chính và một người kiểm soát độc lập |

Một role tồn tại trong hồ sơ không đồng nghĩa role đó được áp dụng cho mọi đối tượng. Một người có thể là FINANCE_MANAGER ở tenant A và chỉ là người xem ở tenant B.

OWASP khuyến nghị mặc định từ chối và kiểm tra quyền trên mỗi yêu cầu. Việc kiểm tra cần dùng cả thuộc tính và quan hệ liên quan đến đối tượng, thay vì chỉ dựa vào một nhãn vai trò rộng. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

## 3. Ma trận vai trò phải biểu diễn đúng AND và OR

### 3.1. Chính sách minh họa

Giả sử giá trị A là tổng nghĩa vụ chi bằng VND đã được tính hợp lệ phía server. Các ngưỡng dưới đây là giả định của ví dụ:

| Giá trị A | Yêu cầu về vai trò |
|---|---|
| `0 < A <= 20.000.000` | Một người đủ quyền thuộc SUPERVISOR **hoặc** FINANCE_MANAGER **hoặc** FINANCE_DIRECTOR |
| `20.000.000 < A <= 200.000.000` | Một người đủ quyền thuộc FINANCE_MANAGER **hoặc** FINANCE_DIRECTOR |
| `200.000.000 < A <= 2.000.000.000` | Một FINANCE_DIRECTOR **và** một RISK_CONTROLLER, là hai chủ thể độc lập |
| `A > 2.000.000.000` | Quy trình ngoại lệ được thiết kế riêng; không tự động thực thi |

Trong các hàng có trách nhiệm tài chính, người đảm nhận phải có trần tiền bao phủ toàn bộ A, đúng tiền tệ và phạm vi. Một FINANCE_MANAGER có trần 80 triệu không được duyệt lệnh 100 triệu.

Trong hàng thứ ba:

- FINANCE_DIRECTOR chịu trách nhiệm chấp thuận nghĩa vụ tài chính.
- RISK_CONTROLLER xác nhận phần kiểm soát rủi ro theo phạm vi được giao.
- Quyền kiểm soát rủi ro không tự cấp thẩm quyền chi tiền.
- Một người giữ cả hai role không được một mình đáp ứng cả hai vị trí.

Phải định nghĩa điều kiện của từng trách nhiệm. Không bắt mọi role đều dùng chung một loại trần tiền nếu nhiệm vụ của họ khác nhau; cũng không bỏ trần của người chịu trách nhiệm tài chính.

### 3.2. Hai chữ ký bất kỳ không tương đương hai trách nhiệm

Với khoản chi 300 triệu:

| Bằng chứng | Đã đủ theo chính sách ví dụ? |
|---|---|
| Hai FINANCE_DIRECTOR, không có RISK_CONTROLLER | Chưa đủ trách nhiệm kiểm soát |
| Hai RISK_CONTROLLER, không có FINANCE_DIRECTOR | Chưa đủ trách nhiệm tài chính |
| Một người có cả hai role, chỉ người đó duyệt | Chưa đủ hai chủ thể độc lập |
| Một FINANCE_DIRECTOR và một RISK_CONTROLLER khác người, đều hợp lệ | Đủ phần vai trò |
| Hai role đúng nhưng cùng thuộc tenant khác | Không hợp lệ |
| Hai người đúng vai trò nhưng một bằng chứng thuộc bản nội dung cũ | Chưa đủ cho bản hiện tại |

“Đủ phần vai trò” vẫn chưa đồng nghĩa được phép thực thi: còn trạng thái, ngân sách, dữ liệu đã chốt và các bất biến nghiệp vụ khác.

### 3.3. Không có đường mặc định làm giảm quyền kiểm soát

Nếu cấu hình role thiếu, không có người phù hợp hoặc dịch vụ quyền không cung cấp được thông tin có độ tin cậy cần thiết, không chuyển yêu cầu sang “không cần duyệt”.

Có thể đưa yêu cầu vào trạng thái chờ phân công hoặc lỗi cấu hình. Tuyến ngoại lệ phải có thẩm quyền riêng, không phải một nút bỏ qua mọi kiểm tra.

## 4. Tránh coi vai trò là một thang điểm đơn giản

### 4.1. Lỗi từ phép so sánh cấp bậc

Một cách triển khai dễ sai:

~~~java
if (actorRole.ordinal() >= requiredRole.ordinal()) {
    approve();
}
~~~

Thứ tự khai báo enum không chứng minh quan hệ thẩm quyền. ADMIN quản trị tài khoản không mặc nhiên được chi tiền; FINANCE_DIRECTOR không mặc nhiên thay được RISK_CONTROLLER.

Tương tự, không lấy role có “điểm cao nhất” của người dùng rồi bỏ qua các ràng buộc còn lại.

Trong mô hình RBAC, quan hệ kế thừa và các ràng buộc là thành phần phải được xác định. Role hierarchy không có nghĩa mọi trách nhiệm trong tổ chức nằm trên một trục cấp bậc duy nhất. [NIST RBAC FAQs](https://csrc.nist.gov/projects/role-based-access-control/faqs)

### 4.2. Kế thừa quyền không làm tăng số người độc lập

Nếu chính sách cho FINANCE_DIRECTOR kế thừa quyền của FINANCE_MANAGER, người đó có thể đủ điều kiện cho một vị trí tài chính cấp thấp hơn trong đúng phạm vi.

Nhưng người đó vẫn là một chủ thể. Kế thừa role không tạo thêm một người duyệt thứ hai hoặc tự sinh chữ ký của một bộ phận khác.

Có thể biểu diễn quan hệ được cho phép bằng permission hoặc tập role tường minh, chẳng hạn:

~~~text
Vị trí tài chính cho tuyến trung bình:
    FINANCE_MANAGER OR FINANCE_DIRECTOR

Vị trí kiểm soát rủi ro:
    RISK_CONTROLLER

Ràng buộc toàn cục:
    các vị trí bắt buộc độc lập phải do các chủ thể khác nhau đảm nhận
~~~

Nếu tổ chức hỗ trợ một role thay thế khác, thay đổi phải đi qua quản trị chính sách. Không suy ra từ tên gọi như “senior”, “head” hoặc “admin”.

## 5. Kiểm tra một quyền được cấp có đủ điều kiện hay không

### 5.1. Quyền được cấp phải có phạm vi

Một bản cấp quyền minh họa:

~~~json
{
  "grantId": "grant-example",
  "subjectId": "person-example",
  "role": "FINANCE_MANAGER",
  "tenantId": "tenant-a",
  "businessUnitId": "unit-b",
  "action": "PAYMENT_APPROVE",
  "currency": "VND",
  "maxAmount": "100000000",
  "validFrom": "2026-11-01T00:00:00Z",
  "validUntil": "2026-12-01T00:00:00Z",
  "status": "ACTIVE"
}
~~~

Đây là mô hình phía server để giải thích chính sách, không phải dữ liệu client được tự gửi để cấp quyền cho mình.

Khi xét lệnh chi, cần kiểm tra một đường cấp quyền hợp lệ bao phủ toàn bộ điều kiện liên quan:

~~~text
đúng subject
AND đúng role hoặc permission được chính sách chấp nhận
AND đúng action
AND đúng tenant và phạm vi đối tượng
AND đúng tiền tệ, đủ trần nếu vị trí có thẩm quyền tiền
AND còn hiệu lực và chưa bị thu hồi
AND điều kiện ủy quyền, nếu có, được thỏa
~~~

Không ghép role của tenant A với quyền xem đối tượng ở tenant B để tạo quyền duyệt ở tenant B. Các điều kiện phải thuộc một đường cấp quyền hợp lệ hoặc cơ chế kết hợp được chính sách cho phép rõ ràng.

### 5.2. Nguồn danh tính và role

Danh tính người thao tác phải đến từ ngữ cảnh xác thực đã kiểm tra. Không lấy `approverId`, `role`, `tenantId` hoặc `maxAmount` trong body làm căn cứ thẩm quyền.

Nếu dùng token có role:

- Xác thực token và nguồn phát hành theo cấu hình của hệ thống.
- Kiểm tra role có ngữ nghĩa và phạm vi phù hợp với ứng dụng không.
- Xác định độ trễ thu hồi quyền mà chính sách chấp nhận.
- Không coi một token còn hạn là bằng chứng quyền chưa từng bị thu hồi.
- Không tin header truyền danh tính nội bộ nếu nó có thể được client bên ngoài tự đặt.

Quyền đọc màn hình duyệt và quyền thực hiện hành động duyệt có thể khác nhau. Việc thấy một yêu cầu trong danh sách không cấp quyền chấp thuận yêu cầu đó.

### 5.3. Nhận diện cùng một chủ thể

Để áp dụng quy tắc độc lập, hệ thống cần định danh chủ thể có ý nghĩa nghiệp vụ, ví dụ nhân sự hoặc danh tính tổ chức đã được liên kết.

Nếu chỉ dùng username, một người có hai tài khoản có thể bị tính thành hai người duyệt. Không dùng email hiển thị hoặc tên hiển thị làm định danh chắc chắn; chúng có thể thay đổi hoặc không duy nhất.

Với service account, cần phân biệt:

- Chủ thể kỹ thuật đang gọi.
- Người hoặc tiến trình mà nó đại diện.
- Người lập và người chịu trách nhiệm về yêu cầu.

Một worker không trở thành người duyệt độc lập chỉ vì dùng tài khoản khác với người tạo lệnh.

## 6. Tách biệt trách nhiệm và ủy quyền

### 6.1. Không tự duyệt qua một vai trò khác

Một người có cả quyền tạo và quyền duyệt có thể được phép sử dụng hai chức năng đó trên các yêu cầu khác nhau. Trong chính sách ví dụ, họ không được duyệt chính yêu cầu mình đã lập.

Có thể cần loại thêm các quan hệ xung đột lợi ích: người hưởng trực tiếp, người đã sửa dữ liệu quan trọng hoặc người đang đại diện cho người lập. Danh sách này phải được định nghĩa theo nghiệp vụ, không suy đoán từ tên role.

Phân biệt:

| Loại kiểm soát | Ví dụ |
|---|---|
| Kiểm soát lúc cấp role | Không cho cùng một người giữ hai vai trò xung đột |
| Kiểm soát trên giao dịch | Có thể giữ cả hai role nhưng không tự duyệt yêu cầu do mình lập |
| Kiểm soát tập người duyệt | Hai trách nhiệm bắt buộc do hai chủ thể độc lập đảm nhận |

Một hệ thống có thể dùng nhiều loại cùng lúc. Chỉ chặn role xung đột khi cấp quyền chưa chắc đủ cho ủy quyền tạm thời hoặc tài khoản đại diện.

### 6.2. Ủy quyền không mở rộng quyền gốc

Một ủy quyền cần thể hiện:

- Ai cấp, ai nhận và theo vai trò nào.
- Action, tenant, đơn vị và loại đối tượng được bao phủ.
- Trần tiền hoặc điều kiện nghiệp vụ có liên quan.
- Khoảng hiệu lực và trạng thái thu hồi.
- Có được ủy quyền tiếp không.
- Quan hệ với người lập và các người duyệt khác.

Quyền được ủy quyền không được vượt phạm vi và điều kiện mà bên cấp thực sự được phép chuyển giao. Không cho một người tự tạo hai đường ủy quyền để được tính thành hai trách nhiệm độc lập.

Trong chính sách ví dụ, người đại diện cho người lập không được dùng ủy quyền để lách điều kiện không tự duyệt.

### 6.3. Quyền cấu hình cũng cần được kiểm soát

Nếu người dùng có thể tự cấp FINANCE_DIRECTOR cho mình hoặc sửa chính sách để role hiện tại được duyệt mọi lệnh, kiểm tra tại endpoint duyệt vẫn có thể bị vô hiệu hóa.

Các thao tác cấp role, thay trần, sửa quan hệ kế thừa, sửa tập role thay thế và tạo ngoại lệ cần có phạm vi quản trị riêng, lịch sử thay đổi và kiểm soát độc lập phù hợp với mức rủi ro.

Không mặc định người quản trị kỹ thuật có quyền quyết định tài chính. Nếu có cơ chế khẩn cấp, phải định nghĩa loại thao tác, phạm vi, thời hạn, người chịu trách nhiệm và quy trình rà soát.

## 7. Tính đủ số phê duyệt theo đúng trách nhiệm

### 7.1. Bài toán là gán người cho vị trí

Với tuyến giá trị cao trong ví dụ, có hai vị trí bắt buộc:

~~~text
Vị trí F: FINANCE_DIRECTOR đủ thẩm quyền cho yêu cầu.
Vị trí R: RISK_CONTROLLER đủ phạm vi kiểm soát.

Cần một người cho F và một người khác cho R.
Mọi bằng chứng phải thuộc đúng yêu cầu và phiên bản nội dung.
~~~

Không chỉ đếm số dòng trong bảng approval, số role trong token hay số lần nhấn nút.

Một trường hợp cần xử lý đúng:

~~~text
Người A đủ điều kiện cho F và R.
Người B chỉ đủ điều kiện cho F.

Phân công hợp lệ:
    B đảm nhận F.
    A đảm nhận R.
~~~

Nếu thuật toán luôn lấy A cho F trước rồi kết luận không ai làm R, nó sẽ từ chối sai. Với nhiều vị trí, cần tìm một cách gán thỏa ràng buộc thay vì gán tham lam theo thứ tự danh sách.

### 7.2. Ví dụ Java cho hai vị trí độc lập

Đoạn mã Java 17+ chỉ đánh giá tập bằng chứng của tuyến giá trị cao. Các đối tượng `EligibleApproval` phải được tạo ở server sau khi đã kiểm tra đối tượng, snapshot, hiệu lực quyền và điều kiện của từng role.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Set;

final class HighValueRolePolicy {
    enum Role {
        FINANCE_DIRECTOR,
        RISK_CONTROLLER
    }

    record EligibleApproval(
            String principalId,
            Set<Role> qualifiedRoles) {

        EligibleApproval {
            Objects.requireNonNull(principalId);
            if (principalId.isBlank()) {
                throw new IllegalArgumentException("Missing principal");
            }
            qualifiedRoles = Set.copyOf(qualifiedRoles);
        }

        boolean canFill(Role role) {
            return qualifiedRoles.contains(role);
        }
    }

    static boolean isSatisfied(
            String makerPrincipalId,
            List<EligibleApproval> approvals) {

        Objects.requireNonNull(makerPrincipalId);
        Objects.requireNonNull(approvals);

        for (var financial : approvals) {
            if (financial.principalId().equals(makerPrincipalId)
                    || !financial.canFill(Role.FINANCE_DIRECTOR)) {
                continue;
            }

            for (var controller : approvals) {
                if (controller.principalId().equals(makerPrincipalId)
                        || controller.principalId()
                            .equals(financial.principalId())) {
                    continue;
                }

                if (controller.canFill(Role.RISK_CONTROLLER)) {
                    return true;
                }
            }
        }
        return false;
    }
}
~~~

Các giới hạn của ví dụ cần giữ rõ:

1. `qualifiedRoles` không phải role client gửi; nó là kết quả kiểm tra quyền cho đúng yêu cầu.
2. `principalId` là định danh chủ thể đã chuẩn hóa, không chỉ ID phiên đăng nhập.
3. Mã xét cả các cách gán hai vị trí, nên xử lý được trường hợp A có hai role và B chỉ có role tài chính.
4. Việc một người có nhiều bản ghi không giúp vượt điều kiện khác chủ thể.
5. Ví dụ chỉ loại người lập. Nếu chính sách có thêm quan hệ xung đột, cần loại hoặc đánh giá chúng trước khi chấp nhận bằng chứng.
6. Mã không thực hiện khóa, truy vấn quyền, kiểm tra ngân sách hoặc gửi lệnh chi.

Không dùng kết quả của hàm này như một giấy phép không thời hạn. Nó phản ánh tập đầu vào đã được kiểm tra tại một thời điểm trong quy trình.

## 8. Phê duyệt gắn với nội dung và phiên bản

### 8.1. Bằng chứng cần nói rõ điều đã được duyệt

Một bản ghi phê duyệt có thể cần:

| Nhóm dữ liệu | Nội dung |
|---|---|
| Đối tượng | Tenant, request ID, loại thao tác |
| Phiên bản | Phiên bản nội dung và snapshot được duyệt |
| Người duyệt | Chủ thể, tài khoản thao tác, quan hệ đại diện nếu có |
| Thẩm quyền | Role đủ điều kiện, bản cấp quyền, phạm vi và nguồn ủy quyền |
| Chính sách | Phiên bản chính sách, vị trí có thể đáp ứng, điều kiện đã kiểm tra |
| Quyết định | Chấp thuận hoặc từ chối, thời điểm, hạn hiệu lực, lý do phù hợp |
| Truy vết | Request ID kỹ thuật và thông tin phục vụ audit |

Nếu hệ thống cho phép một bằng chứng dùng cho nhiều vị trí mà người đó đủ điều kiện, vẫn phải bảo đảm một người không lấp nhiều vị trí yêu cầu độc lập. Có thể lưu kết quả phân công cuối cùng để giải thích tại sao tập phê duyệt đủ điều kiện.

OWASP nhấn mạnh việc người dùng nhận biết dữ liệu giao dịch quan trọng, bảo vệ dữ liệu đã xác nhận và kiểm tra sự cho phép trước thực thi. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)

### 8.2. Thay đổi quan trọng phải được đánh giá lại

Các thay đổi như tăng tiền, đổi tiền tệ, đổi người hưởng, đổi tài khoản nhận, đổi nguồn chi hoặc đổi nhóm nghĩa vụ có thể làm sai tuyến role ban đầu.

Trong chính sách minh họa, chúng tạo phiên bản nội dung mới và làm bằng chứng cũ không còn đáp ứng bản mới. Client phải nhìn thấy và xác nhận đúng nội dung mới.

Phân biệt hai loại phiên bản:

- **Phiên bản nội dung:** thay đổi khi dữ liệu nghiệp vụ cần duyệt thay đổi.
- **Phiên bản cập nhật kỹ thuật:** phục vụ kiểm soát đồng thời, có thể đổi khi ghi thêm một quyết định.

Không làm chữ ký thứ nhất tự mất hiệu lực chỉ vì chữ ký thứ hai được ghi, nếu nội dung nghiệp vụ không đổi. Ngược lại, không giữ nguyên phiên bản nội dung khi người hưởng hoặc số tiền đã đổi.

### 8.3. State machine tham chiếu

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> PendingApproval: chốt nội dung và chính sách
    PendingApproval --> PendingApproval: thêm bằng chứng chưa đủ
    PendingApproval --> Ready: đủ vị trí và chủ thể hợp lệ
    PendingApproval --> Rejected: từ chối theo quy tắc
    PendingApproval --> Draft: sửa nội dung quan trọng
    Ready --> PendingApproval: bằng chứng không còn đáp ứng
    Ready --> Draft: sửa nội dung quan trọng
    Ready --> ExecutionQueued: kiểm tra cuối và ghi lệnh
    ExecutionQueued --> Executed: xác nhận kết quả
    ExecutionQueued --> ReconciliationRequired: chưa rõ kết quả bên ngoài
~~~

Các nhánh hủy và hết hạn có thể cần bổ sung theo nghiệp vụ. Không cho client tự đặt `Ready` hoặc bỏ qua `PendingApproval`.

Một yêu cầu đã có quyết định từ chối không được tự chuyển thành sẵn sàng chỉ vì một lượt duyệt khác đến muộn. Chính sách cần xác định từ chối có kết thúc vòng duyệt hay không và xử lý mọi quyết định theo cùng state machine.

## 9. Transaction và việc quyền thay đổi đồng thời

### 9.1. Ghi quyết định trong ranh giới nhất quán

Luồng tham chiếu:

~~~text
BEGIN
  1. Lấy danh tính từ ngữ cảnh xác thực.
  2. Đọc và khóa hoặc kiểm soát phiên bản của yêu cầu cần duyệt.
  3. Kiểm tra tenant, quyền trên đối tượng và trạng thái.
  4. So sánh phiên bản nội dung mà người dùng đã xem.
  5. Đọc chính sách và kiểm tra hiệu lực quyền, phạm vi, ủy quyền.
  6. Kiểm tra xung đột lợi ích.
  7. Ghi bằng chứng gắn với đúng chủ thể và nội dung.
  8. Đọc lại tập bằng chứng hợp lệ, tính đủ các vị trí.
  9. Chuyển trạng thái nếu điều kiện thỏa; ghi audit và idempotency.
COMMIT
~~~

Có thể dùng ràng buộc duy nhất tương đương:

~~~text
UNIQUE(tenantId, requestId, contentVersion, approverPrincipalId)
~~~

Trong mô hình ví dụ, một chủ thể đóng góp một quyết định duyệt cho một phiên bản nội dung. Nếu hỗ trợ rút quyết định hoặc thay đổi ý kiến, cần mô hình lịch sử và quy tắc hiệu lực riêng; không xóa audit rồi thêm một dòng mới để tăng số người.

### 9.2. Khóa yêu cầu không tự khóa toàn bộ quyền

Trong PostgreSQL, khóa hàng có thể điều phối các thao tác cạnh tranh trên bản ghi đó. Muốn bảo vệ một quyết định, cần xác định đầy đủ các dữ liệu cùng tham gia bất biến và thứ tự truy cập thích hợp. [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

Ví dụ, hai transaction có thể cùng duyệt, trong khi transaction thứ ba sửa nội dung hoặc từ chối. Nếu tất cả cùng tuân thủ giao thức khóa/phiên bản của yêu cầu, có thể tuần tự hóa các chuyển trạng thái liên quan.

Nhưng khóa hàng của yêu cầu không tự ngăn một quản trị viên thu hồi role ở dịch vụ danh tính bên ngoài. Cũng không làm cache quyền trở thành dữ liệu mới nhất.

### 9.3. Quy định rõ tác động của thu hồi quyền

Một lựa chọn trong bài là: **tại cổng tạo lệnh thực thi, bằng chứng chỉ được tính nếu quyền liên quan vẫn hợp lệ theo chính sách thu hồi**.

Để thực thi lựa chọn đó, hệ thống cần một cơ chế phù hợp, chẳng hạn:

- Dữ liệu quyền trong cùng miền nhất quán và giao thức điều phối với thao tác thu hồi.
- Phiên bản quyền hoặc dấu hiệu thu hồi mà cổng quyết định kiểm tra được.
- Dịch vụ quyền tập trung có mức bảo đảm và độ trễ được xác định.
- Trạng thái chờ khi không xác minh được hiệu lực cần thiết.

Chỉ lưu `authorizationRevision` trong bản ghi approval không tự chứng minh revision đó còn hiện hành. Nó hữu ích để đối chiếu khi có cơ chế xác minh tương ứng.

Nếu hệ thống chấp nhận một khoảng trễ thu hồi, phải coi đó là lựa chọn chính sách và kiểm soát rủi ro có chủ đích. Không mô tả một hệ thống dùng cache đồng bộ trễ như thể quyền bị thu hồi tức thời ở mọi nơi.

## 10. Cổng thực thi cuối và bất biến nghiệp vụ

### 10.1. Không thực thi chỉ vì có cờ đã duyệt

Trước khi tạo lệnh thực thi, kiểm tra:

1. Nội dung hiện tại trùng phiên bản đã được duyệt.
2. Chính sách đã chốt còn được phép áp dụng.
3. Tập bằng chứng còn hợp lệ và có thể gán đủ các vị trí độc lập.
4. Không có từ chối, hủy, đình chỉ hoặc thu hồi đang ngăn thực thi.
5. Hạn mức tổng, ngân sách và các điều kiện nghiệp vụ vẫn thỏa.
6. Chưa có một lệnh thực thi khác cho cùng ý định.

Ví dụ với hoàn tiền:

~~~text
đúng quyền trên giao dịch gốc
AND đủ bằng chứng theo role
AND chuyển trạng thái hợp lệ
AND tiền đã hoàn + tiền đang giữ <= tổng tiền đủ điều kiện hoàn
AND chỉ một tác dụng phụ cho cùng ý định
~~~

Một FINANCE_DIRECTOR duyệt không làm yêu cầu hoàn tiền vượt tổng hợp lệ trở nên hợp lệ. Role không cho phép bỏ qua mọi bất biến trừ khi chính sách có một thao tác ngoại lệ được định nghĩa riêng; nhiều bất biến cốt lõi vẫn không có ngoại lệ như vậy.

### 10.2. Ranh giới cam kết phải rõ

Một phương án là ghi chuyển trạng thái, lệnh thực thi bất biến và outbox trong cùng transaction. Worker dùng lệnh đã chốt, không lấy lại số tiền hoặc người hưởng từ một bản ghi có thể sửa tùy ý.

Phải xác định cách xử lý quyền bị thu hồi sau khi lệnh đã được cam kết nhưng trước khi gửi ra ngoài:

- Nếu lệnh đã được coi là cam kết hợp lệ, xử lý hủy theo quy trình đã định.
- Nếu quyền phải còn hợp lệ ngay lúc gửi, worker cần kiểm tra theo chính sách đó.
- Nếu tác dụng phụ đã xảy ra, cần xử lý kết quả hoặc bù trừ theo nghiệp vụ; không chỉ xóa cờ approved.

Transaction nội bộ không tự bao trùm dịch vụ thanh toán. Không hứa hủy tức thời một lệnh đã được đối tác tiếp nhận nếu hệ thống không có cơ chế thực hiện.

### 10.3. Retry không tạo thêm người duyệt hoặc lệnh chi

Bảo vệ theo từng lớp:

| Lớp | Kiểm soát |
|---|---|
| Retry cùng ý định duyệt | Idempotency key đúng phạm vi và kiểm tra payload |
| Một chủ thể có nhiều tài khoản | Định danh chủ thể chuẩn hóa và ràng buộc đóng góp |
| Gửi nhiều quyết định đồng thời | Khóa/phiên bản, ràng buộc duy nhất và state machine |
| Retry tạo lệnh thực thi | Định danh nghiệp vụ duy nhất hoặc cập nhật trạng thái có điều kiện |
| Worker nhận sự kiện lặp | Cơ chế xử lý lặp an toàn và idempotency với đối tác nếu hỗ trợ |
| Timeout không rõ kết quả | Tra cứu, chờ xác nhận hoặc đối soát |

Khi trả kết quả idempotency đã lưu, vẫn kiểm tra quyền đọc. Cùng key nhưng payload khác cần phản hồi xung đột theo hợp đồng.

Outbox không tự làm tác dụng phụ bên ngoài chỉ xảy ra một lần. Không đổi key và tạo lệnh mới chỉ vì chưa nhận được phản hồi.

## 11. API và giao diện phải phản ánh quyền có điều kiện

### 11.1. Client gửi quyết định, không gửi thẩm quyền

Request minh họa:

~~~json
{
  "requestId": "payment-request-example",
  "expectedContentVersion": 4,
  "decision": "APPROVE",
  "comment": "Đã đối chiếu chứng từ."
}
~~~

Server lấy người duyệt từ phiên xác thực, đọc quyền và tự tính các vị trí mà bằng chứng có thể đáp ứng.

Không tin các trường như:

~~~json
{
  "approverId": "another-person",
  "role": "FINANCE_DIRECTOR",
  "approvalCount": 2,
  "skipRiskController": true,
  "status": "Ready"
}
~~~

Đây là ví dụ dữ liệu không được phép quyết định thẩm quyền, không phải hợp đồng đầu vào được khuyến nghị.

### 11.2. Nút bấm không phải ranh giới bảo vệ

Giao diện có thể dùng `canApprove` để hiện nút và giải thích người dùng cần làm gì. Giá trị đó chỉ là snapshot hỗ trợ trải nghiệm.

Server phải kiểm tra lại khi hành động được gọi. Nếu role đã đổi hoặc phiên bản nội dung không còn khớp, nút còn hiển thị không làm hành động hợp lệ.

Một mã phản hồi có thể phân biệt:

| Tình huống | Hướng xử lý minh họa |
|---|---|
| Không có quyền thực hiện trên đối tượng | Lỗi phân quyền theo hợp đồng, có thể che sự tồn tại |
| Nội dung hoặc trạng thái đã đổi | Lỗi xung đột, chẳng hạn 409 |
| Yêu cầu hợp lệ nhưng chưa đủ tập phê duyệt | Giữ trạng thái chờ, trả tiến độ người dùng được phép biết |
| Không xác minh được nguồn quyền cần thiết | Lỗi khả dụng hoặc trạng thái chờ rõ ràng |

Không coi “tôi duyệt được phần của mình” là “toàn bộ yêu cầu đã sẵn sàng”. Phản hồi nên phân biệt quyết định vừa ghi và trạng thái tổng thể.

### 11.3. Không làm lộ sơ đồ quyền không cần thiết

Người có quyền xem quy trình có thể cần biết còn thiếu trách nhiệm kiểm soát nào. Họ không mặc nhiên được xem mọi role, trần tiền và quan hệ ủy quyền của toàn bộ tổ chức.

Thông báo hỗ trợ nên đủ hành động được mà không tiết lộ dữ liệu tenant khác hoặc lý do nội bộ nhạy cảm. Log chi tiết nằm ở kênh được phân quyền.

## 12. Kiểm thử tình huống lạm dụng và tính đúng của chính sách

Bảng sau mô tả các kịch bản cần kiểm tra cho một triển khai, không phải kết quả đã chạy kiểm thử hệ thống cụ thể.

| Kịch bản | Điều cần xác minh |
|---|---|
| Có role đúng nhưng thuộc tenant khác | Không duyệt được đối tượng ngoài phạm vi |
| Có role đúng nhưng sai chi nhánh hoặc action | Không ghép quyền từ các phạm vi khác nhau |
| FINANCE_MANAGER không đủ trần tiền | Không cung cấp bằng chứng tài chính cho lệnh đó |
| ADMIN kỹ thuật không có quyền tài chính | Không được phép duyệt chỉ vì tên role có vẻ cao |
| Hai người đều là FINANCE_DIRECTOR | Không thay được vị trí RISK_CONTROLLER |
| Một người có cả hai role | Không đáp ứng yêu cầu hai chủ thể độc lập |
| Một người dùng hai tài khoản | Không được đếm thành hai người |
| Người lập đổi sang role khác | Không tự duyệt được yêu cầu của mình |
| Người đại diện hoặc được ủy quyền của người lập | Không lách quy tắc xung đột đã định |
| Ủy quyền hết hạn, bị thu hồi hoặc vượt phạm vi | Không được tính là quyền hợp lệ |
| A có hai role, B chỉ có FINANCE_DIRECTOR | Chấp nhận cách gán B tài chính, A kiểm soát nếu các điều kiện khác thỏa |
| Thay đổi thứ tự danh sách bằng chứng | Không thay kết quả đủ/thiếu của cùng một tập hợp |
| Gửi lại cùng approval hoặc cùng idempotency key | Không tăng số người hoặc số vị trí được đáp ứng |
| Client tự gửi role hoặc approvalCount | Không ảnh hưởng dữ liệu thẩm quyền |
| Sửa người hưởng hoặc số tiền sau khi đã duyệt | Bằng chứng cũ không áp cho nội dung mới |
| Đồng thời duyệt, sửa nội dung và từ chối | Không xuất hiện trạng thái sẵn sàng trái quy tắc |
| Thu hồi role trước cổng thực thi | Áp dụng đúng chính sách hiệu lực và độ trễ đã cam kết |
| Nguồn quyền lỗi hoặc cache quá cũ | Không tự chấp nhận dữ liệu không đủ độ tin cậy |
| Thay cấu hình role hoặc quan hệ kế thừa | Không hồi tố giảm kiểm soát ngoài quy trình thay đổi |
| Batch, import, worker hoặc API quản trị | Không có đường thực thi bỏ qua chính sách chung |
| Worker nhận lại sự kiện hoặc timeout | Không thêm tác dụng phụ cho cùng ý định |

Kiểm thử cần có cả tình huống bị từ chối và tình huống hợp lệ. Chỉ kiểm tra chặn role sai có thể bỏ sót lỗi từ chối sai do thuật toán gán người cho vị trí.

Một số thuộc tính hữu ích:

- Thêm bản sao của cùng bằng chứng không tạo thêm người độc lập.
- Đổi thứ tự tập bằng chứng không thay kết quả.
- Loại bỏ bằng chứng hợp lệ không làm một tập thiếu trở thành đủ.
- Một role bị loại khỏi tập đủ điều kiện không tự sinh quyền thay thế.
- Bằng chứng của bản nội dung khác không giúp đáp ứng bản hiện tại.

Với xử lý đồng thời, quan sát dữ liệu đã commit, tập bằng chứng được chọn, trạng thái cuối và số tác dụng phụ. Một response báo lỗi không chứng minh giao dịch chưa được thực hiện.

## 13. Audit và quản trị thay đổi

Audit cần ghi nhận đủ để trả lời ai đã duyệt nội dung nào, với role và quyền nào, dưới chính sách nào, và tập bằng chứng được dùng để mở cổng thực thi ra sao.

Cần theo dõi riêng các sự kiện:

- Cấp, thu hồi và thay đổi phạm vi role.
- Tạo, sửa và thu hồi ủy quyền.
- Sửa chính sách ngưỡng và role thay thế.
- Duyệt, từ chối, hết hiệu lực và không còn đủ tập bằng chứng.
- Tạo lệnh thực thi, hủy và xác nhận kết quả.

Chính sách cần có phiên bản và mốc hiệu lực. Khi thay đổi, phải xác định tác động tới yêu cầu mới, yêu cầu đang chờ và yêu cầu đã được duyệt nhưng chưa thực thi. Không để một node dùng tuyến cũ và node khác tự dùng tuyến mới mà thiếu quy tắc chuyển tiếp.

Không xóa lịch sử khi role bị thu hồi. Một phê duyệt có thể đã hợp lệ lúc được ghi nhưng không còn đủ điều kiện cho cổng thực thi hiện tại; cả hai thông tin đều cần để giải thích quyết định.

Log và công cụ hỗ trợ cũng cần kiểm soát quyền truy cập. Không ghi token bí mật hoặc toàn bộ dữ liệu tài khoản nhạy cảm vào log chung.

## 14. Các bất biến cần giữ

Một ngưỡng phê duyệt theo vai trò có hiệu lực khi:

- Chính sách xuất phát từ đối tượng và dữ liệu nghiệp vụ đã xác minh.
- Role được áp dụng cùng action, phạm vi, thẩm quyền và thời hạn.
- Một người có nhiều role vẫn chỉ là một chủ thể khi xét tính độc lập.
- Tập phê duyệt đáp ứng đủ từng trách nhiệm, không chỉ đủ số dòng.
- Bằng chứng gắn với đúng nội dung và phiên bản.
- Việc sửa nội dung, đổi quyền hoặc thu hồi được xử lý theo chính sách rõ ràng.
- Không có kênh thực thi bỏ qua kiểm tra cuối, transaction và cơ chế chống trùng.

Tên vai trò giúp tổ chức quyền. Quyết định an toàn đòi hỏi chứng minh đúng người đang đảm nhận đúng trách nhiệm trên đúng giao dịch, và bằng chứng đó còn đáp ứng điều kiện tại ranh giới thực thi đã chọn.
