# Permission scope: xác định đúng phạm vi của quyền

## 1. Mục tiêu bài học

Trong chương **Permission Semantics** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **permission scope** là phạm vi mà một quyền có hiệu lực.

Một quyền chỉ có ý nghĩa đầy đủ khi biết:

> Chủ thể được làm hành động gì, trên tập đối tượng nào, với giới hạn và điều kiện nào?

Ví dụ, “được duyệt hoàn tiền” có thể chỉ áp dụng cho một chi nhánh trong một tenant và trong hạn mức cụ thể. Nó không tự cho phép duyệt mọi yêu cầu mà người đó xem được.

Sau bài học, bạn có thể:

- Mô tả scope bằng tập đối tượng hoặc điều kiện có thể kiểm chứng.
- Phân biệt phạm vi tenant, đơn vị, quan hệ, từng đối tượng và trường dữ liệu.
- Kết hợp nhiều grant mà không ghép nhầm hành động với scope hoặc hạn mức của grant khác.
- Áp dụng scope nhất quán cho đọc, tạo, sửa, chuyển đối tượng, batch và truy vấn dữ liệu.
- Bảo vệ scope trước thay đổi ownership, tổ chức, delegation, cache và xử lý đồng thời.
- Kiểm thử các ranh giới quyền có khả năng bị lợi dụng để vượt quyền nghiệp vụ.

## 2. Biết tên quyền chưa đủ biết phạm vi

Các phát biểu sau còn thiếu ngữ nghĩa:

~~~text
Lan có quyền READ.
Hùng có quyền APPROVE.
Nhóm hỗ trợ được quản lý refund.
~~~

Cần trả lời tiếp:

- READ loại đối tượng nào và những trường nào?
- APPROVE trong tenant, chi nhánh hoặc dự án nào?
- “Quản lý” bao gồm tạo, sửa, hủy, duyệt hay xuất dữ liệu?
- Quyền có áp dụng cho mọi đối tượng hay chỉ đối tượng được giao?
- Scope được tính theo người tạo, owner hiện tại hay quan hệ khác?
- Quyền có hạn mức, thời hạn hoặc điều kiện ủy quyền không?

Nếu các tầng hiểu khác nhau, giao diện có thể chỉ hiển thị một chi nhánh nhưng API lại cho phép thao tác toàn tenant.

| Sai lệch về scope | Cách bị lạm dụng |
|---|---|
| API chỉ kiểm tra role, không kiểm tra đối tượng | Đổi objectId để thao tác ngoài phạm vi |
| ALL không nói rõ biên tenant | Quyền toàn tổ chức bị hiểu thành toàn nền tảng |
| Quyền READ toàn tenant được trộn với APPROVE một chi nhánh | Duyệt mọi đối tượng mà actor đọc được |
| OWN không có định nghĩa | Actor đổi owner hoặc tạo thay người khác để mở rộng quyền |
| Query rỗng bộ lọc thì bỏ điều kiện scope | Không có quyền trở thành được xem tất cả |
| Kế thừa từ đối tượng cha không được đặc tả | Xem được order bị hiểu thành được sửa mọi refund liên quan |
| Cache bỏ qua tenant/action | Quyết định quyền của ngữ cảnh này bị dùng ở ngữ cảnh khác |

Định danh khó đoán không thay thế scope. UUID vẫn phải được kiểm tra quyền trước khi đọc hoặc thay đổi đối tượng.

## 3. Một grant phải giữ nguyên quan hệ giữa hành động và phạm vi

Có thể mô hình hóa một grant cho phép như sau:

~~~text
Grant =
    subject
    + actions
    + resourceType
    + targetScope
    + conditions
    + validity
~~~

Trong đó:

- subject: người hoặc nhóm nhận quyền.
- actions: các hành động được cấp.
- resourceType: loại tài nguyên.
- targetScope: tập đích hoặc predicate xác định đối tượng nằm trong phạm vi.
- conditions: giới hạn bổ sung như số tiền hoặc tập trường.
- validity: thời hạn và trạng thái hiệu lực.

Ví dụ dữ liệu khái niệm, không phải cấu hình của một sản phẩm cụ thể:

~~~json
{
  "grantId": "grant-approve-branch-a",
  "subject": "person-17",
  "actions": ["REFUND_APPROVE"],
  "resourceType": "REFUND",
  "scope": {
    "kind": "BRANCH",
    "tenantId": "tenant-1",
    "branchIds": ["branch-a"]
  },
  "conditions": {
    "currency": "VND",
    "maxAmount": 20000000
  }
}
~~~

Quyền trên không tự áp dụng cho branch-b, tenant-2, payment hoặc hành động REFUND_EXECUTE. Hạn mức 20 triệu chỉ có ý nghĩa theo đơn vị tiền và chính sách đã xác định.

### 3.1. Scope là một tập hoặc một điều kiện, không nhất thiết là danh sách ID

Một scope có thể là:

~~~text
Tập ID cụ thể:
  resource.id thuộc {r-1, r-2}

Theo thuộc tính:
  resource.tenantId = tenant-1
  và resource.branchId thuộc {branch-a, branch-b}

Theo quan hệ:
  resource được giao cho actor
  hoặc actor thuộc nhóm phụ trách đối tượng

Theo cây:
  resource thuộc đơn vị X hoặc các đơn vị con được phép kế thừa
~~~

Predicate phải dùng dữ liệu có thẩm quyền và ngữ nghĩa đã thống nhất. “Thuộc nhóm” có thể là thành viên hiện tại, thành viên tại thời điểm tạo hay người chịu trách nhiệm được chốt; mỗi cách cho ra một tập khác nhau.

### 3.2. Phân biệt scope và các ràng buộc liên quan

Trong bài này, targetScope trả lời đối tượng nào thuộc phạm vi. Hạn mức, thời gian, tập trường và trạng thái được biểu diễn như các ràng buộc bổ sung để dễ phân tích.

Một hệ thống có thể dùng từ scope cho nhiều chiều hơn. Điều quan trọng là hợp đồng phải chỉ rõ các chiều đó, nguồn dữ liệu và cách kết hợp, thay vì dựa vào một chuỗi nhãn chung.

Scope hợp lệ cũng không chứng minh thao tác hợp lệ về nghiệp vụ. Actor có thể được duyệt một refund nhưng refund đã bị hủy hoặc tổng hoàn tiền đã chạm trần. Cần kiểm tra cả quyền và bất biến.

## 4. Các loại scope và những câu hỏi phải chốt

| Scope | Ý nghĩa có thể chọn | Điểm phải làm rõ |
|---|---|---|
| TENANT | Đối tượng trong một tổ chức | Tenant cụ thể nào, quyền thành viên nào đang có hiệu lực |
| BRANCH/DEPARTMENT | Đối tượng của một đơn vị | Có gồm đơn vị con không; dùng đơn vị hiện tại hay snapshot |
| PROJECT | Đối tượng liên quan dự án | Quan hệ dự án do ai xác minh; có chia sẻ chéo đơn vị không |
| CREATED_BY_ACTOR | Đối tượng do actor tạo | Người tạo thực tế hay account kỹ thuật |
| OWNED_BY_ACTOR | Đối tượng actor đang sở hữu | Ai được chuyển owner; ownership có cấp quyền gì |
| ASSIGNED_TO_ACTOR | Đối tượng đang được giao | Assignment nào, còn hiệu lực không, được làm action nào |
| TEAM | Đối tượng do một nhóm phụ trách | Nhóm nào, quan hệ thành viên và phạm vi của nhóm |
| EXPLICIT_OBJECTS | Một tập đối tượng xác định | Hiệu lực, thu hồi và liên kết tenant của từng đối tượng |
| ALL_WITHIN_TENANT | Mọi đối tượng của loại đó trong tenant đã ràng buộc | Không tự mở thành mọi tenant |
| PLATFORM | Phạm vi nền tảng được cấp riêng | Action, tập tenant và điều kiện vận hành được cho phép |

Không phải các scope này tạo thành một chuỗi lồng nhau. Project có thể xuyên đơn vị; assignment là một quan hệ thay đổi; owner có thể khác người tạo.

### 4.1. Tránh một giá trị OWN mơ hồ

Giả sử khách hàng là người hưởng lợi, Lan tạo refund thay khách hàng, Hùng đang xử lý.

“Own refund” có thể bị hiểu là:

~~~text
refund.createdBy = actor
refund.customerId = actor.customerId
refund.ownerId = actor
refund.assigneeId = actor
~~~

Bốn điều kiện khác nhau. Hãy dùng tên và mô tả phản ánh đúng quan hệ. Việc Lan tạo thay khách hàng không tự cấp cho khách hàng quyền duyệt; việc Hùng được giao xử lý không tự cấp quyền chi trả.

### 4.2. ALL luôn cần một biên rõ ràng

Một role được gán tại tenant-1 với scope ALL nên được diễn đạt thành “mọi REFUND trong tenant-1” nếu đó là ý định.

Không dùng null tenant hoặc branchIds rỗng để ngầm chỉ quyền toàn hệ thống. Nên có loại scope tường minh và kiểm tra cấu trúc tương ứng.

Ví dụ quy ước:

~~~text
kind = BRANCH, branchIds = []:
    tập đích rỗng hoặc cấu hình không hợp lệ

kind = ALL_WITHIN_TENANT, tenantId = tenant-1:
    toàn bộ tài nguyên phù hợp trong tenant-1

thiếu kind hoặc không nhận diện được:
    không đủ căn cứ cấp quyền
~~~

Quy ước cụ thể có thể khác, nhưng thiếu dữ liệu không được vô tình mở rộng phạm vi.

### 4.3. Kế thừa cần nói rõ cả quan hệ lẫn hành động

Quyền xem một order không mặc định cho phép sửa invoice hoặc duyệt refund của order đó.

Nếu có kế thừa, phải xác định:

- Loại quan hệ cha–con được dùng.
- Những action được kế thừa.
- Các ràng buộc tiếp tục có hiệu lực.
- Điều kiện chặn hoặc thu hồi.
- Cách xử lý khi đối tượng đổi cha hoặc chuyển đơn vị.

Một cây tài nguyên không tự tạo ra cây quyền cho mọi hành động.

## 5. Kết hợp nhiều grant mà không sinh quyền mới ngoài ý định

### 5.1. Lỗi tích chéo giữa action và scope

Actor có:

~~~text
G1: REFUND_READ    trên toàn tenant-1
G2: REFUND_APPROVE trên branch-a của tenant-1, tối đa 20 triệu
~~~

Cách tổng hợp sai:

~~~text
actions = union(actions của mọi grant)
scope   = union(scope của mọi grant)

Nếu action thuộc actions và resource thuộc scope:
    cho phép
~~~

Kết quả là APPROVE bị ghép với scope toàn tenant của READ. Hệ thống đã tạo ra quyền mà không grant nào thực sự cấp.

### 5.2. Phải có cùng một grant đáp ứng các điều kiện tương ứng

Với một yêu cầu hành động đơn, mô hình cơ bản là:

~~~text
permit =
    mandatoryBoundariesSatisfied
    ∧ tồn tại grant g đang có hiệu lực sao cho:
         g áp dụng cho subject
         ∧ action thuộc g.actions
         ∧ resource đúng g.resourceType
         ∧ resource thuộc g.targetScope
         ∧ tham số thỏa g.conditions
~~~

Trong chính sách minh họa này, các hạn chế bắt buộc vẫn áp dụng dù actor có nhiều grant.

Nếu hệ thống có explicit deny, phải định nghĩa cách kết hợp deny và permit. Không mặc định mọi sản phẩm hoặc policy engine có cùng thứ tự ưu tiên.

### 5.3. Không trộn scope của grant này với hạn mức của grant khác

Giả sử:

~~~text
G1: APPROVE tại branch-a, tối đa 20 triệu
G2: APPROVE tại branch-b, tối đa 100 triệu
~~~

Refund 70 triệu của branch-a không được phép chỉ vì actor có một grant với hạn mức 100 triệu ở nơi khác.

Phải giữ nguyên bộ điều kiện của từng grant. Quyền hiệu lực là hợp của các trường hợp hoàn chỉnh được cho phép, không phải tổ hợp tùy ý giữa các thành phần thuận lợi nhất.

## 6. Scope phải được ràng buộc với dữ liệu có thẩm quyền

### 6.1. Người gọi không tự khai phạm vi được phép

Client có thể gửi tenantId, branchId hoặc ownerId như dữ liệu của command. Server phải xác minh chúng; không dùng chính giá trị đó làm bằng chứng người gọi có quyền.

Ví dụ sai:

~~~text
Client gửi allowedBranchIds = [branch-a, branch-b].
Repository dùng allowedBranchIds để lọc.
~~~

Đó chỉ là bộ lọc người dùng yêu cầu, chưa phải scope được cấp.

Phạm vi truy vấn hiệu lực phải nằm trong quyền actor:

~~~text
effectiveTargets =
    targetsRequestedByClient
    ∩ targetsAllowedForThisAction
    ∩ mandatoryTenantBoundary
~~~

Client có thể thu hẹp tập mục tiêu. Việc yêu cầu tập rộng hơn không mở rộng quyền.

### 6.2. Role cũng có ngữ cảnh gán

Một người có thể là FINANCE_APPROVER ở tenant-1 nhưng chỉ là READER ở tenant-2.

Không tải mọi role của người đó rồi áp dụng vào tenant đang được client chọn. Grant hoặc role assignment phải giữ quan hệ với tenant, đơn vị và phạm vi nơi quyền có hiệu lực.

Tương tự, role gán tại một chi nhánh không tự trở thành role toàn tenant chỉ vì tên role giống nhau.

### 6.3. Liên kết cha–con phải được xác minh

Với đường dẫn:

~~~text
/tenants/t-1/orders/o-1/refunds/r-1
~~~

Không chỉ kiểm tra actor được truy cập o-1 rồi nạp r-1 bằng ID toàn cục. Phải xác minh r-1 thực sự thuộc o-1 và cùng biên tenant tương ứng.

Dữ liệu liên kết mới cũng cần kiểm tra. Actor được tạo refund trong branch-a không thể trỏ paymentId sang một payment ngoài scope để hoàn tiền từ giao dịch khác.

Nếu ID chỉ duy nhất trong tenant, truy vấn và khóa tham chiếu phải phản ánh ngữ nghĩa đó; không vô tình coi một ID cục bộ là định danh toàn cục.

### 6.4. Tạo mới vẫn có scope

Khi CREATE, đối tượng chưa tồn tại nhưng vẫn có phạm vi đích: payment gốc, project, folder, ngân sách hoặc tenant.

Kiểm tra:

- Actor được tạo loại đối tượng trong phạm vi đích.
- Các liên kết được tạo thuộc phạm vi được phép.
- Chủ thể hoặc đơn vị nhận đối tượng là hợp lệ.
- Các giá trị đầu vào không mở quyền rộng hơn ý định.

Không chờ tạo xong mới kiểm tra quyền trên đối tượng vừa tạo, vì có thể đã phát sinh reservation, notification hoặc job.

## 7. Áp dụng scope vào truy vấn và command

### 7.1. Query scope phải tương ứng với đúng action

Danh sách người dùng có thể xem và danh sách họ có thể approve có thể khác nhau.

Một trang “chờ tôi duyệt” phải dùng scope của APPROVE và các điều kiện liên quan, không dùng READ toàn tenant rồi hiển thị nút approve cho mọi dòng.

Ngay cả khi danh sách đã được lọc, endpoint approve vẫn kiểm tra lại đối tượng hiện tại. Một URL, checkbox hoặc kết quả tìm kiếm cũ không phải bằng chứng quyền còn hiệu lực.

### 7.2. Truy vấn phải giữ cấu trúc từng grant

Giả sử actor có đúng hai grant APPROVE:

~~~text
branch-a: tối đa 20 triệu VND
branch-b: tối đa 100 triệu VND
~~~

Một điều kiện khái niệm có thể là:

~~~sql
SELECT r.*
FROM refund r
WHERE r.tenant_id = :trusted_tenant
  AND r.currency = 'VND'
  AND (
       (r.branch_id = :branch_a AND r.amount <= :limit_a)
    OR (r.branch_id = :branch_b AND r.amount <= :limit_b)
  );
~~~

Các tham số phạm vi và hạn mức được tạo từ grant có thẩm quyền, không từ danh sách allowed do client khai.

Không biến thành:

~~~sql
WHERE tenant_id = :trusted_tenant
  AND branch_id IN (:branch_a, :branch_b)
  AND amount <= :largest_limit
~~~

Điều kiện sau mở hạn mức của branch-b sang branch-a.

Cũng cần giữ đúng dấu ngoặc. Một nhánh OR thoát khỏi điều kiện tenant có thể phá biên cô lập ngay cả khi mỗi nhánh trông có vẻ hợp lý khi đọc riêng.

SQL trên chỉ minh họa hai grant cùng currency. Chính sách thực có thể còn assignment, delegation, trạng thái, explicit deny hoặc điều kiện khác phải được thực thi.

### 7.3. Tập rỗng không được biến thành bỏ lọc

Một lỗi thường xuất hiện trong code dựng query:

~~~text
Nếu allowedIds không rỗng:
    thêm WHERE id IN allowedIds
Nếu allowedIds rỗng:
    bỏ qua WHERE đó
~~~

Nếu allowedIds rỗng vì không có quyền, bỏ điều kiện sẽ trả mọi đối tượng trong biên còn lại.

Phải phân biệt rõ:

~~~text
Không có mục tiêu được cấp:
    kết quả rỗng hoặc từ chối theo hợp đồng

Có grant toàn tenant:
    dùng một scope tường minh tương ứng
~~~

Không dùng cùng một giá trị rỗng cho cả hai ý nghĩa.

### 7.4. Query là một lớp thực thi, không phải quyền mặc định cho command

Có thể dùng điều kiện scope để hạn chế SELECT/UPDATE, kết hợp với kiểm tra domain trên đối tượng được bảo vệ.

Với UPDATE có điều kiện, cần kiểm tra số dòng tác động. Không đổi trạng thái hay phát outbox tiếp nếu phần cập nhật được bảo vệ không tác động dòng nào.

Đối với danh sách, tìm kiếm, count, tổng tiền và phân trang, phạm vi phải áp dụng trước khi công bố kết quả. Lấy một trang rộng rồi lọc trong bộ nhớ có thể làm thiếu trang, lộ tổng số hoặc bỏ sót đối tượng hợp lệ.

Nếu một policy không thể biểu diễn đầy đủ bằng query, có thể kết hợp query thu hẹp an toàn với bước đánh giá chính xác hơn. Cần thiết kế phân trang, tổng hợp và hiệu năng phù hợp; không giả định bộ lọc sơ bộ đã cấp quyền đầy đủ.

## 8. Bộ đánh giá scope nên giữ grant nguyên vẹn

Mã Java sau là phác thảo quyết định quyền, không phải thư viện hoàn chỉnh. Các grant và facts được server lấy từ nguồn có thẩm quyền. Ví dụ dùng tập grant cho phép; các hạn chế bắt buộc được kiểm tra riêng theo chính sách đã chọn.

~~~java
Decision evaluate(
        Subject subject,
        Action action,
        Resource resource,
        ActionParameters parameters,
        PolicyFacts facts,
        List<PermitGrant> grants) {

    facts.requireTrustedAndSufficient();

    if (!boundaries.allow(subject, resource, facts)) {
        return Decision.deny("OUTSIDE_MANDATORY_BOUNDARY");
    }
    if (restrictions.forbid(
            subject, action, resource, parameters, facts)) {
        return Decision.deny("MANDATORY_RESTRICTION");
    }

    for (var grant : grants) {
        if (!grant.isEffectiveAt(facts.now())) continue;
        if (!grant.appliesTo(subject, facts)) continue;
        if (!grant.actions().contains(action)) continue;
        if (!grant.resourceType().equals(resource.type())) continue;
        if (!grant.scope().matches(resource, facts)) continue;
        if (!grant.conditions().matches(
                resource, parameters, facts)) continue;

        return Decision.permit(
                grant.id(),
                facts.policyVersion(),
                resource.version());
    }

    return Decision.deny("NO_MATCHING_GRANT");
}
~~~

Điểm chính là action, resource type, scope và conditions đều được kiểm tra trên **cùng grant**.

Nếu facts thiếu hoặc đánh giá lỗi, tầng thực thi không được biến exception thành permit. Có thể biểu diễn Indeterminate riêng và trả lỗi/chờ theo hợp đồng.

Bộ đánh giá không tự bảo đảm đối tượng không đổi sau khi evaluate. Command handler phải ràng buộc quyết định với đúng version và dữ kiện cần thiết.

Nếu hệ thống có nhiều grant góp phần cho quyền theo trường, phải đặc tả phép kết hợp riêng. Chỉ được hợp các trường từ những grant thực sự khớp với chính đối tượng/ngữ cảnh đang xét; không hợp toàn bộ cột actor từng được xem ở nơi khác.

### 8.1. Grant cấp quyền và biên bắt buộc là hai lớp

Một mô hình an toàn có thể biểu diễn:

~~~text
Phạm vi hiệu lực =
    hợp của các trường hợp grant hoàn chỉnh cho phép
    ∩ biên bắt buộc của phiên/tenant/chính sách
~~~

Ví dụ, một grant đã được lưu sai tenant không được vượt biên tenant mà actor hiện được phép hoạt động.

Nếu có quyền vận hành xuyên tenant, cần loại quyền và ngữ cảnh riêng được cấp rõ ràng, thay vì bỏ biên khi actor có role mang tên ADMIN.

### 8.2. Lưu bằng chứng grant khớp để giải thích quyết định

Audit có thể ghi grantId, scope kind, policy version và resource version đã được dùng. Điều này giúp phân biệt:

~~~text
Actor được approve vì grant cụ thể tại branch-a.
~~~

với một thông báo khó kiểm tra:

~~~text
Actor có role finance.
~~~

Bằng chứng quyết định phải phản ánh quyền thực sự được dùng, không chỉ liệt kê mọi quyền actor đang có.

## 9. Scope có thể thay đổi trong lúc thao tác

### 9.1. Sửa chính thuộc tính dùng để xác định scope

Nếu actor được sửa một đối tượng vì nó thuộc branch-a, liệu họ có được chuyển nó sang branch-b không?

Đây là thao tác có ảnh hưởng đến quyền. Cần quy định quyền trên:

- Nguồn đang chứa đối tượng.
- Đích nhận đối tượng.
- Hành động chuyển.
- Những quan hệ và assignment sẽ bị thay đổi.
- Hiệu lực của approval đã có.

Không chỉ authorize ảnh chụp trước rồi cho phép thay tenantId, branchId, projectId hoặc ownerId tùy ý.

Tương tự, nếu “được giao cho tôi” cấp quyền duyệt, actor không được tự sửa assigneeId để đưa mọi đối tượng vào scope của mình.

### 9.2. Ownership không xóa lịch sử nghiệp vụ

Một scope có thể phụ thuộc owner hiện tại, nhưng quy tắc cấm tự duyệt có thể phụ thuộc người tạo/người sửa trong lịch sử.

Chuyển owner không được mặc định xóa xung đột nhiệm vụ. Đó là hai điều kiện khác nhau và có nguồn dữ liệu khác nhau.

### 9.3. Tránh sử dụng quyết định trên dữ liệu cũ

Ví dụ:

~~~text
T1: refund thuộc branch-a, actor đủ scope để approve.
T2: một command hợp lệ chuyển refund hoặc đổi assignment.
T1: approve mà không kiểm tra dữ kiện đã đổi.
~~~

Cần khóa, version hoặc cập nhật có điều kiện bảo vệ các thuộc tính ảnh hưởng quyết định. Mọi đường ghi liên quan phải tham gia cùng giao thức.

Nếu scope dựa trên membership hoặc cây tổ chức ở dịch vụ khác, transaction cục bộ không tự bảo vệ dữ liệu đó. Phải định nghĩa độ mới và cơ chế thu hồi/kiểm chứng đáp ứng yêu cầu.

Có thể cần theo dõi cả resource version, entitlement version và hierarchy version; chỉ tăng version của refund không phát hiện mọi thay đổi ở dữ liệu bên ngoài.

### 9.4. Batch cần scope từng mục tiêu và hợp đồng kết quả rõ ràng

Một batch có thể gồm đối tượng ở nhiều branch. Mỗi phần tử phải được đối chiếu với grant phù hợp; không dùng quyền của phần tử đầu cho cả danh sách.

Cần chọn hợp đồng:

- Toàn bộ batch được chấp nhận hoặc không phần tử nào tạo hiệu ứng.
- Hoặc trả kết quả riêng từng phần tử theo cách được sản phẩm cho phép.

Không âm thầm bỏ đối tượng ngoài quyền rồi báo tất cả thành công. Đồng thời không dùng thông báo chi tiết để tiết lộ đối tượng mà actor không được biết.

Quyền theo từng đối tượng vẫn chưa bảo đảm hạn mức tổng của batch; ràng buộc tổng, nếu có, cần được đánh giá và bảo vệ riêng.

## 10. Scope còn ảnh hưởng dữ liệu nào được trả về

### 10.1. Phạm vi dòng và phạm vi trường

Một người có thể xem thông tin cơ bản của refund trong toàn tenant nhưng chỉ được xem thông tin nhạy cảm tại branch mình phụ trách.

Ví dụ:

~~~text
G1: READ_BASIC, toàn tenant-1
    fields = id, status, amount

G2: READ_SENSITIVE, branch-a trong tenant-1
    fields = beneficiaryAccountDetails
~~~

Không được hợp mọi fields trước rồi trả thông tin nhạy cảm cho mọi dòng thuộc G1. Phải kiểm tra quyền trường trên từng đối tượng/ngữ cảnh tương ứng.

Serialization, projection hoặc bước dựng response cần thực thi đúng chính sách. Ẩn một cột trong giao diện không ngăn API trả cột đó.

### 10.2. Bộ lọc phải đi cùng các dạng đọc khác

Scope cần áp dụng cho:

- Detail endpoint.
- Danh sách, search và autocomplete.
- Count và tổng hợp.
- Báo cáo, export và job sinh file.
- Attachment, liên kết tải và các đối tượng được join.
- Receipt hoặc kết quả công việc đã lưu.

Một API list lọc đúng nhưng endpoint tải attachment chỉ kiểm tra attachmentId vẫn có thể làm lộ tài liệu của đối tượng ngoài scope.

Nếu dùng liên kết tải có thời hạn, phải kiểm tra quyền khi tạo liên kết và đặc tả hiệu lực truy cập/thu hồi trong thời gian liên kết còn dùng được. Không mặc định đường dẫn khó đoán tự thực thi quyền hiện tại.

### 10.3. Aggregate cũng có phạm vi

Tổng tiền hoàn toàn tenant có thể tiết lộ thông tin ngoài quyền của người chỉ được xem một branch.

Không chỉ lọc dữ liệu bảng rồi gọi một endpoint thống kê không có scope. Count, sum và các con số trên dashboard phải được tính theo phạm vi được phép hoặc theo một quyền tổng hợp riêng đã được chính sách cấp.

## 11. Delegation, token và cache không được làm rộng scope

### 11.1. Được dùng quyền chưa chắc được cấp lại quyền

Một người được approve tại branch-a không tự có quyền tạo grant cho người khác. Hành động quản lý quyền hoặc delegation cần được cấp riêng, với điều kiện tương ứng.

Nếu được ủy quyền, phạm vi hiệu lực phải nằm trong thẩm quyền nguồn và chính sách cho phép ủy quyền:

~~~text
DelegatedAuthority ⊆ SourceAuthority ∩ DelegationPolicy
~~~

Ở đây authority nên được hiểu là tập các yêu cầu hành động hoàn chỉnh: action, đối tượng, tham số và thời điểm. Không chỉ so một nhãn scope rồi bỏ mất hạn mức hoặc biên tenant.

Ví dụ:

~~~text
Nguồn:
  APPROVE branch-a, tối đa 20 triệu, đến thời điểm T

Ủy quyền không thể tự trở thành:
  APPROVE toàn tenant, tối đa 100 triệu, không hết hạn
~~~

Nếu grant nguồn bị thu hồi hoặc hết hiệu lực, delegation phụ thuộc không được tiếp tục hoạt động như một quyền mồ côi, trừ khi chính sách có cơ chế cấp quyền độc lập khác được quản lý rõ ràng.

### 11.2. Không có thứ tự rộng–hẹp đơn giản cho mọi scope

SELF, TEAM, PROJECT và BRANCH không phải lúc nào cũng xếp được thành một thứ tự tuyến tính.

Ví dụ một người sở hữu đối tượng ở nhiều project nhưng team của họ chỉ phụ trách một tập nhỏ trong một branch. So sánh enum hoặc tên scope không chứng minh được tập đích của delegation nằm trong tập nguồn.

Có thể cần:

- Kiểm tra bao hàm dựa trên cấu trúc scope được hỗ trợ.
- Giới hạn kiểu delegation để việc bao hàm có thể xác minh.
- Hoặc luôn áp dụng đồng thời predicate nguồn và predicate ủy quyền tại lúc sử dụng.

Không nới quyền khi không chứng minh được phạm vi là hợp lệ.

### 11.3. Chuỗi quyền trong token cần ngữ nghĩa rõ

Một token có chuỗi refund.approve có thể chỉ thể hiện capability nền. Nó không tự nói được phép approve refund nào.

Nếu hệ thống chủ ý đưa tenant hoặc resource scope vào token, phải xác minh nguồn cấp, đối tượng sử dụng, hạn dùng và các ràng buộc đó theo giao thức đã thiết kế. Handler vẫn cần dữ liệu nghiệp vụ để tránh sử dụng quyền trên nội dung đã thay đổi.

Không coi mọi cách dùng từ scope trong token, giao diện quản trị và domain model là cùng một khái niệm nếu chưa có ánh xạ rõ ràng.

### 11.4. Cache phải phản ánh các dữ kiện làm thay đổi tập đích

Một quyết định có thể phụ thuộc:

~~~text
subject và tenant đang hoạt động
action và resource type
resourceId, version và các thuộc tính scope
grant/entitlement version
policy version
membership, assignment hoặc hierarchy version
tham số và điều kiện thời gian
~~~

Không nhất thiết nhét mọi dữ kiện vào một cache key khổng lồ. Có thể cache nguồn dữ liệu quyền với cơ chế vô hiệu hóa phù hợp rồi tính quyết định cuối. Nhưng thiết kế phải chứng minh không dùng quyết định cũ cho ngữ cảnh khác.

Không cache vĩnh viễn danh sách ID “được giao cho tôi” nếu assignment có thể thay đổi. Sau khi đối tượng đổi branch, cache hoặc chỉ mục scope cũ cũng phải được xử lý theo cam kết hiệu lực.

TTL chỉ tạo một giới hạn độ trễ theo thiết kế; nó không tự bảo đảm thu hồi quyền tức thời.

## 12. Kiểm thử scope bằng dữ liệu phân biệt được lỗi

### 12.1. Bộ dữ liệu minh họa

Hùng có ba grant:

~~~text
G1: READ toàn tenant-1
G2: APPROVE branch-a của tenant-1, tối đa 20 triệu VND
G3: APPROVE branch-b của tenant-1, tối đa 100 triệu VND
~~~

Các điều kiện khác như trạng thái, phân tách nhiệm vụ và hạn mức nghiệp vụ được chuẩn bị hợp lệ để kiểm thử tập trung vào scope.

| Đối tượng | Thuộc tính | READ | APPROVE |
|---|---|---|---|
| R1 | tenant-1, branch-a, 10 triệu | Cho phép | Cho phép theo G2 |
| R2 | tenant-1, branch-a, 70 triệu | Cho phép | Từ chối |
| R3 | tenant-1, branch-b, 70 triệu | Cho phép | Cho phép theo G3 |
| R4 | tenant-1, branch-c, 10 triệu | Cho phép | Từ chối |
| R5 | tenant-2, branch-a, 10 triệu | Từ chối | Từ chối |

R2 phát hiện lỗi lấy hạn mức lớn nhất từ mọi grant. R4 phát hiện lỗi lấy scope READ cho APPROVE. R5 phát hiện mất biên tenant hoặc coi branchId là đủ để quyết định.

Một test chỉ có R1 và R3 đều hợp lệ sẽ không phát hiện hai lỗi kết hợp grant quan trọng này.

### 12.2. Ma trận kiểm thử bổ sung

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Actor đổi objectId sang đối tượng cùng tenant ngoài scope | Không đọc/sửa/duyệt ngoài phạm vi |
| Actor đổi tenant trong URL hoặc body | Không tự mở quyền thành viên hoặc dùng role của tenant khác |
| Refund không thuộc order được nêu trên URL | Không chấp nhận quan hệ giả |
| CREATE liên kết payment ngoài scope | Không tạo đối tượng hoặc hiệu ứng liên quan |
| Không có grant phù hợp | Từ chối hoặc tập kết quả rỗng theo hợp đồng |
| Scope BRANCH có danh sách rỗng | Không bỏ điều kiện lọc để trả mọi branch |
| Thiếu hoặc không nhận diện scope kind | Không mặc định ALL |
| Có ALL_WITHIN_TENANT | Không truy cập tenant khác |
| Có quyền trên cha | Chỉ kế thừa action/quan hệ được chính sách quy định |
| Đổi owner/assignee để tự đưa đối tượng vào scope | Cần quyền cho thay đổi; không tự mở quyền hành động |
| Chuyển đối tượng từ branch có quyền sang branch không có quyền | Kiểm tra quyền chuyển, nguồn và đích theo hợp đồng |
| Scope/hạn mức từ các grant khác nhau | Không tạo tổ hợp quyền mới ngoài ý định |
| Batch trộn đối tượng trong và ngoài scope | Đúng hợp đồng toàn bộ/từng phần; không âm thầm bỏ kiểm tra |
| Có READ_BASIC rộng, READ_SENSITIVE hẹp | Trường nhạy cảm chỉ xuất hiện cho dòng đúng scope |
| Count/export/attachment ngoài scope | Không lộ qua đường đọc khác |
| Grant nguồn delegation bị thu hồi | Quyền phụ thuộc không tiếp tục ngoài chính sách |
| Cache được tạo cho tenant/action khác | Không áp dụng nhầm |
| Membership hoặc hierarchy thay đổi | Quyền thay đổi theo cam kết hiệu lực |
| Scope đổi đồng thời với command | Không dùng quyết định trên dữ kiện cũ để tạo hiệu ứng trái phép |

### 12.3. Kiểm tra sau từ chối phải bao gồm dữ liệu bền vững

Với R2 hoặc R4 bị từ chối approve, đọc lại bằng transaction mới và xác nhận:

~~~text
trạng thái refund không đổi
không có approval decision mới
không tăng reservation của payment
không có outbox chi trả/phê duyệt của lần bị chặn
không có job tiếp tục thực hiện thay người gọi
~~~

Security log về lần bị chặn có thể được ghi. Nó không phải chứng từ approve thành công.

Không chỉ xác nhận HTTP response hoặc kiểm tra hàm scope.matches được gọi. Phải quan sát hành vi từ điểm vào thực tế tới dữ liệu được commit.

### 12.4. Kiểm thử cạnh tranh với thay đổi scope

Chuẩn bị actor chỉ được approve branch-a và refund đang thuộc branch-a.

Cho hai command qua hai transaction độc lập:

~~~text
A: approve refund theo version hiện tại.
B: chuyển refund sang branch-b bằng quyền chuyển hợp lệ,
   nếu trạng thái cho phép.
~~~

Điều phối để hai command cạnh tranh tại điểm bảo vệ thuộc tính scope.

Kết quả phải tương ứng với một thứ tự hợp lệ hoặc xung đột được phát hiện. Không được có command approve được đánh giá cho branch-a nhưng áp dụng lên revision đã chuyển sang branch-b.

Nếu approve đã làm đối tượng không còn được chuyển trực tiếp, luồng B phải tuân thủ trạng thái đó. Nếu B thắng, A phải thấy dữ kiện mới hoặc bị chặn bởi version.

### 12.5. Kiểm thử delegation theo phạm vi thực tế

Cho nguồn có grant APPROVE branch-a tối đa 20 triệu. Thử tạo hoặc sử dụng delegation:

~~~text
branch-a, 10 triệu:
    có thể hợp lệ nếu được phép ủy quyền

branch-a, 30 triệu:
    không được vượt nguồn

branch-b, 10 triệu:
    không được vượt nguồn

toàn tenant-1:
    không được mở rộng từ branch-a

branch-a sau khi nguồn hết hiệu lực:
    không còn hợp lệ theo quan hệ phụ thuộc đã chọn
~~~

Kiểm tra cả lúc cấp delegation và lúc dùng. Chỉ kiểm tra lúc tạo chưa phát hiện nguồn quyền bị thu hồi về sau.

## 13. Audit phải giải thích phạm vi thực sự được áp dụng

Thông tin có thể cần gồm:

~~~text
actor/account và danh tính nghiệp vụ
tenant đang hoạt động
action, resource type, resourceId
resource version và thuộc tính scope quan trọng
grantId hoặc nguồn thẩm quyền khớp
policy/entitlement/hierarchy version liên quan
decision và reason code
command/transitionId, kết quả commit
delegation hoặc ngoại lệ nếu có
~~~

Không cần sao chép toàn bộ danh bạ hay hồ sơ nhạy cảm vào log. Chọn bằng chứng đủ để giải thích quyết định theo chính sách lưu trữ và kiểm soát truy cập.

Một lần bị từ chối có thể được ghi nội bộ là OUTSIDE_BRANCH_SCOPE, trong khi response bên ngoài không tiết lộ tên branch hoặc dữ liệu của đối tượng mà actor chưa có quyền biết.

Các mẫu đáng theo dõi gồm dò nhiều objectId, đổi tenant liên tục, sử dụng scope rỗng, chuyển owner trước thao tác nhạy cảm hoặc tăng đột biến các grant/delegation rộng. Cần đánh giá trong ngữ cảnh thay vì xem mọi lần bị từ chối là tấn công.

## 14. Khung đặc tả một permission scope

Trước khi đặt tên quyền trong code, hãy hoàn thiện:

~~~text
Action và resource type:
Subject/role assignment áp dụng trong ngữ cảnh nào:

Biên tenant bắt buộc:
Target scope và ý nghĩa quan hệ:
Nguồn dữ liệu xác định scope:
Có kế thừa không; kế thừa action nào:
Ngữ nghĩa của ALL, NONE, thiếu dữ liệu và giá trị rỗng:

Ràng buộc tham số, trường dữ liệu và thời gian:
Cách kết hợp nhiều grant:
Cách xử lý explicit deny nếu có:
Delegation và quy tắc không mở rộng quyền:

Quy tắc tạo, chuyển owner/đơn vị/đối tượng cha:
Cơ chế nhất quán và hiệu lực thu hồi:
Ánh xạ vào query, detail, batch, export và job:
Audit và các ca vượt biên cần kiểm thử:
~~~

## 15. Câu hỏi tự kiểm tra

1. Vì sao READ toàn tenant cộng APPROVE một branch không tạo APPROVE toàn tenant?
2. Vì sao không thể lấy hạn mức lớn nhất của mọi grant cho mọi đối tượng?
3. OWN trong sản phẩm của bạn nghĩa là người tạo, owner, người thụ hưởng hay người được giao?
4. Scope rỗng, scope thiếu và toàn tenant được biểu diễn khác nhau thế nào?
5. Khi tạo một đối tượng chưa tồn tại, phạm vi đích được kiểm tra ở đâu?
6. Chuyển branch hoặc owner có thể làm thay đổi quyền của những ai?
7. Những nguồn dữ liệu ngoài resource version nào ảnh hưởng quyết định scope?
8. Query count, file export và attachment có thực thi cùng biên dữ liệu không?
9. Làm sao chứng minh delegation không rộng hơn thẩm quyền nguồn?
10. Bộ test nào của bạn phát hiện được lỗi tích chéo action, scope và hạn mức?

Một scope được định nghĩa tốt phải có thể trả lời bằng dữ liệu: **đối tượng này có thuộc đúng phạm vi của grant đang cấp cho hành động này không?** Mọi cách tổng hợp quyền, dựng query, cache và thực hiện command phải giữ nguyên quan hệ đó.
