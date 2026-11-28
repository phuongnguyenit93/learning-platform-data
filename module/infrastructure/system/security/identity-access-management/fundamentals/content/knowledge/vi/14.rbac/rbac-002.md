# Role assignment

## 1. Gán vai trò là quyết định cấp quyền

Trong một ứng dụng quản lý hóa đơn, Lan cần tạo bản nháp và gửi đề nghị thanh toán. Minh cần xem và phê duyệt các đề nghị đó. Thay vì thêm từng permission trực tiếp cho mỗi người, hệ thống định nghĩa các vai trò như `INVOICE_PREPARER` và `INVOICE_APPROVER`, rồi gán vai trò phù hợp cho từng danh tính.

**Role assignment** là việc thiết lập quan hệ giữa một chủ thể và một vai trò. Quan hệ này cho biết chủ thể được nhận những quyền mà vai trò đại diện, trong phạm vi và điều kiện mà hệ thống quy định.

Gán vai trò không phải thao tác trang trí hồ sơ. Một bản ghi mới có thể làm người dùng đọc thêm dữ liệu, phê duyệt giao dịch hoặc thay đổi cấu hình hệ thống. Do đó, việc gán phải có căn cứ nghiệp vụ, thẩm quyền cấp, phạm vi tài nguyên và cách kết thúc hiệu lực.

Trong tài liệu nền tảng RBAC của NIST, quan hệ người dùng–vai trò và quan hệ vai trò–permission là hai thành phần riêng. Mô hình cũng phân biệt vai trò được gán với vai trò được kích hoạt trong phiên. [NIST — RBAC FAQs](https://csrc.nist.gov/projects/role-based-access-control/faqs).

Ở phạm vi IAM, chủ thể có thể là con người hoặc danh tính workload nếu hệ thống hỗ trợ. Tài khoản kỹ thuật cũng cần được gán vai trò theo nhiệm vụ của workload; không nên mặc nhiên nhận quyền quản trị chỉ vì chạy trong mạng nội bộ.

## 2. Phân biệt gán vai trò, định nghĩa vai trò và sử dụng quyền

Ba quan hệ sau có trách nhiệm khác nhau:

```text
Chủ thể --được gán--> Vai trò --chứa--> Permission
                               |
                               +--> được sử dụng trong phạm vi cho phép
```

Ví dụ:

```text
Lan  -> INVOICE_PREPARER -> invoice:read
                         -> invoice:create
                         -> invoice:submit

Minh -> INVOICE_APPROVER -> invoice:read
                         -> invoice:approve
```

| Thao tác | Điều bị thay đổi | Phạm vi ảnh hưởng |
| --- | --- | --- |
| Gán `INVOICE_PREPARER` cho Lan | Quan hệ chủ thể–vai trò | Quyền mà Lan nhận qua assignment này |
| Thêm `invoice:delete` vào `INVOICE_PREPARER` | Định nghĩa vai trò | Có thể ảnh hưởng mọi người đang nhận vai trò |
| Kích hoạt vai trò được phép dùng | Tập vai trò có hiệu lực trong phiên hoặc cửa sổ kích hoạt | Các thao tác của phiên tương ứng |
| Cho phép Lan đọc hóa đơn I-42 | Quyết định authorization cho một yêu cầu | Hành động và tài nguyên đang được đánh giá |
| Thu hồi assignment của Lan | Chấm dứt một nguồn vai trò | Các quyền nhận qua nguồn đó, sau khi thay đổi được thực thi |

Một người có thể được gán nhiều vai trò. Một vai trò có thể được gán cho nhiều người. Trong cách ký hiệu thường gặp:

```text
U: tập chủ thể
R: tập vai trò
P: tập permission

UA ⊆ U × R: quan hệ gán chủ thể–vai trò
PA ⊆ P × R: quan hệ gán permission–vai trò
```

Phạm vi tài nguyên, thời hạn và nguồn cấp là những thông tin triển khai thường được bổ sung vào assignment. Chúng không nhất thiết xuất hiện dưới cùng một schema hoặc có cùng tên trong mọi sản phẩm RBAC.

Việc có vai trò là đầu vào cho authorization. Nó chưa tự chứng minh người dùng được thao tác với mọi bản ghi: quyền còn có thể bị giới hạn bởi tenant, dự án, trạng thái tài nguyên hoặc các ràng buộc nghiệp vụ.

## 3. Một assignment cần trả lời những câu hỏi nào?

Xét bản ghi minh họa:

```yaml
assignmentId: ra-1042
subjectId: user-lan
roleId: invoice-preparer
scope:
  tenantId: tenant-a
  projectId: project-p
grantState: GRANTED
validFrom: '2026-12-01T01:00:00Z'
validUntil: '2027-03-01T01:00:00Z'
sourceType: DIRECT
requestId: access-request-281
approvedBy: user-manager
createdBy: access-workflow-service
reason: Phụ trách lập đề nghị thanh toán cho dự án P
```

Đây là schema giảng dạy, không phải cấu hình của một sản phẩm cụ thể. Nó cho thấy assignment không nên chỉ là một cột `role = ADMIN` trên bảng người dùng.

### 3.1. Đúng danh tính

`subjectId` nên là định danh ổn định trong miền danh tính phù hợp. Tên hiển thị và địa chỉ email có thể đổi hoặc được tái sử dụng, nên không thích hợp làm căn cứ duy nhất cho một quyền dài hạn.

Nếu liên kết danh tính từ nhiều nhà cung cấp, cần xác định đầy đủ miền phát hành và định danh chủ thể. Hai tài khoản cùng chuỗi tên hoặc email chưa chắc là cùng một danh tính được hệ thống tin cậy.

Việc gán phải kiểm tra trạng thái và loại chủ thể: người đã nghỉ việc, tài khoản đang khóa hoặc workload đã ngừng sử dụng không nên tiếp tục được cấp quyền theo một luồng chỉ kiểm tra rằng ID tồn tại.

### 3.2. Đúng vai trò

Vai trò cần có định danh rõ và ý nghĩa nghiệp vụ có thể giải thích. Người duyệt phải biết role chứa các permission nào, có kế thừa quyền từ role khác không và có nằm trong nhóm đặc quyền hay không.

Tên `MANAGER` quá chung nếu người dùng và người phê duyệt hiểu khác nhau. Với hệ thống hóa đơn, tên thể hiện năng lực như `INVOICE_APPROVER` thường giúp trao đổi chính xác hơn, nhưng tên rõ vẫn phải đi kèm định nghĩa permission rõ.

Nếu vai trò thay đổi nội dung sau khi được gán, người dùng có thể nhận quyền mới mà không có assignment mới. Vì vậy, quản lý thay đổi định nghĩa vai trò cũng là một phần của kiểm soát quyền.

### 3.3. Đúng phạm vi

Lan có vai trò lập hóa đơn ở dự án P thuộc tenant A không có nghĩa Lan được lập hóa đơn ở dự án Q hoặc tenant B.

```text
(Lan, PREPARER, tenant A / project P)
khác với
(Lan, PREPARER, tenant A / project Q)
```

Nếu hệ thống hỗ trợ phạm vi cha–con, cần định nghĩa rõ assignment ở tenant có áp dụng xuống mọi dự án hay không. Không tự suy ra rằng thiếu `projectId` nghĩa là toàn bộ dự án. Thiếu dữ liệu bắt buộc phải được xử lý như dữ liệu không hợp lệ, trừ khi schema có biểu diễn phạm vi toàn tenant được thiết kế riêng.

Khi tài nguyên được chuyển sang dự án khác, assignment theo dự án cũ không nên được mang sang một cách ngầm định. Cần đánh giá theo vị trí và phạm vi có hiệu lực của tài nguyên.

### 3.4. Đúng thời hạn và căn cứ

Quyền phục vụ một đợt hỗ trợ ngắn không nên trở thành quyền lâu dài do bỏ quên ngày kết thúc. Ngược lại, không cần ép mọi quyền công việc thông thường thành quyền ngắn hạn nếu hệ thống có cách quản lý vòng đời phù hợp.

Một quy ước dễ kiểm tra là khoảng hiệu lực nửa mở:

```text
validFrom <= thời điểm đánh giá < validUntil
```

Đúng tại `validUntil`, assignment không còn hiệu lực. Quy ước này giúp hai khoảng thời gian nối tiếp không bị chồng nhau tại ranh giới. Thời điểm phải được tính từ đồng hồ server đáng tin cậy và biểu diễn nhất quán, thay vì nhận trực tiếp giá trị `now` do client gửi.

Lý do, yêu cầu cấp quyền và người phê duyệt giúp trả lời vì sao assignment tồn tại. Một ô lý do có nội dung bất kỳ không thay thế việc xác minh nhu cầu và thẩm quyền.

## 4. Vai trò được gán và vai trò được kích hoạt

Một người có thể được phép đảm nhiệm cả vai trò vận hành thông thường và vai trò xử lý sự cố. Hệ thống có thể cho phép chỉ kích hoạt một phần vai trò đã được phê duyệt khi cần sử dụng.

```text
Vai trò được phê duyệt cho người dùng
             |
             +--> Chọn hoặc yêu cầu kích hoạt
                          |
                          +--> Vai trò đang dùng trong phiên/thời hạn hiện tại
```

Tập vai trò được kích hoạt không được vượt tập vai trò mà người dùng được phép sử dụng. Việc chọn vai trò trên giao diện hoặc gửi `role=ADMIN` trong request không tạo ra một assignment hợp lệ.

Một ví dụ sản phẩm là Microsoft Entra Privileged Identity Management, phân biệt assignment đủ điều kiện kích hoạt với assignment đang hoạt động. Việc kích hoạt có thể yêu cầu phê duyệt, MFA hoặc lý do sử dụng tùy chính sách. [Microsoft Learn — Privileged Identity Management](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure).

Không phải hệ thống RBAC nào cũng có cơ chế này. Trong một ứng dụng đơn giản, mọi role được gán còn hiệu lực có thể được dùng ngay. Khi đó vẫn phải kiểm soát phạm vi, thời hạn và các ràng buộc của assignment.

Cần tránh trộn ba chiều thông tin thành một trạng thái mơ hồ:

| Chiều thông tin | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Tiến trình yêu cầu | Chờ duyệt, bị từ chối, đã duyệt | Yêu cầu đã được chấp thuận chưa? |
| Vòng đời assignment | Đã cấp, đã thu hồi | Quan hệ cấp vai trò còn tồn tại hiệu lực không? |
| Điều kiện sử dụng | Đến giờ bắt đầu chưa, còn hạn không, đã kích hoạt chưa | Hiện tại có được dùng vai trò này không? |

Một yêu cầu đã duyệt nhưng provisioning thất bại chưa có nghĩa quyền đã sẵn sàng. Một assignment đã được ghi nhưng thời điểm bắt đầu ở tương lai chưa được dùng ngay. Một assignment đủ điều kiện kích hoạt cũng chưa đồng nghĩa quyền đặc quyền đang được bật.

## 5. Các nguồn cấp vai trò và quyền thực tế

### 5.1. Gán trực tiếp

Assignment liên kết trực tiếp người dùng với vai trò và phạm vi. Cách này dễ giải thích cho một ngoại lệ cụ thể nhưng có thể tạo nhiều bản ghi khó quản lý nếu dùng cho toàn bộ tổ chức mà thiếu quy trình rà soát.

```text
Lan -> PREPARER tại project P
```

Khi thu hồi, cần chỉ ra assignment nào bị thu hồi. Nếu người dùng còn nhận cùng role qua một nhóm, quyền thực tế có thể vẫn tồn tại.

### 5.2. Gán qua nhóm

Nhóm tập hợp danh tính; vai trò tập hợp năng lực. Một nhóm có thể được liên kết với role để cấp quyền hàng loạt theo cấu hình của hệ thống.

```text
Lan -> thành viên nhóm Accounts-P
Accounts-P -> PREPARER tại project P
```

Lúc này, thay đổi thành viên nhóm là một đường cấp quyền. Người được thêm thành viên vào nhóm có thể gián tiếp cấp các role mà nhóm đang nhận. Do đó, quyền quản lý nhóm nhạy cảm phải được bảo vệ tương xứng với quyền quản lý assignment.

Nếu có nhóm lồng nhau, cần xác định rõ cách tính thành viên gián tiếp, vòng lặp, độ sâu và độ trễ đồng bộ. Không mặc định mọi sản phẩm đều hỗ trợ cùng một kiểu kế thừa nhóm.

### 5.3. Nhận quyền qua phân cấp vai trò

Một role có thể nhận thêm permission qua phân cấp role đã được định nghĩa. Đây là quan hệ giữa các vai trò, khác với việc nhóm chứa người dùng.

```text
Lan -> SENIOR_PREPARER
SENIOR_PREPARER -> bao gồm quyền của PREPARER
```

Trong mô hình này, thu hồi một assignment trực tiếp tới `PREPARER` không chắc làm Lan mất toàn bộ quyền chuẩn bị hóa đơn, vì assignment `SENIOR_PREPARER` vẫn cấp các permission tương ứng.

Phân cấp role không nên được suy ra từ sơ đồ chức danh. Trưởng phòng không nhất thiết được kế thừa mọi quyền thao tác của nhân viên, đặc biệt với quyền phê duyệt hoặc kiểm soát độc lập.

### 5.4. Đồng bộ và ánh xạ từ hệ thống khác

Directory hoặc IdP có thể là nguồn nhóm và vai trò. Ứng dụng cần ánh xạ rõ role bên ngoài sang role nội bộ, gắn đúng ứng dụng và phạm vi tenant.

Một chuỗi `admin` do client tự gửi không có giá trị như role claim từ nguồn đã được xác minh. Ngay cả claim hợp lệ cũng phải được diễn giải theo đúng hợp đồng: role quản trị của một ứng dụng không tự trở thành role quản trị của ứng dụng khác.

Khi một dịch vụ đồng bộ quản lý assignment, cần xác định nguồn chuẩn. Nếu quản trị viên xóa bản ghi ở hệ thống đích nhưng nhóm nguồn vẫn còn, lần đồng bộ sau có thể cấp lại quyền. Hành động thu hồi phải xử lý đúng nguồn cấp và có readback kết quả tại nơi thực thi.

## 6. Ai được phép gán vai trò?

Quyền sử dụng chức năng nghiệp vụ và quyền cấp chức năng đó cho người khác là hai quyền khác nhau.

Minh có thể được phê duyệt hóa đơn nhưng không được tự chọn thêm người phê duyệt. Một quản trị viên quyền tại tenant A có thể được cấp `PREPARER` trong A, nhưng không được gán role cho người khác ở tenant B hoặc cấp role quản trị toàn hệ thống.

Một yêu cầu gán role cần kiểm tra tối thiểu:

1. Danh tính người thao tác đã được xác minh và còn được phép thực hiện nghiệp vụ quản trị quyền.
2. Người thao tác có quyền gán đúng role tại đúng phạm vi, trong thời hạn được ủy quyền.
3. Danh tính nhận quyền, role và phạm vi tồn tại, tương thích với chính sách.
4. Đã có phê duyệt cần thiết; người duyệt có thẩm quyền cho chính yêu cầu này.
5. Thời hạn, điều kiện tiên quyết và ràng buộc xung đột vai trò được đáp ứng.
6. Thay đổi được ghi an toàn, kiểm toán được và được chuyển tới nơi thực thi.

Không nên dùng quy tắc chung như “ai có role thì được cấp role đó”. Được đọc tài liệu không có nghĩa được chia sẻ quyền đọc; được phê duyệt hóa đơn không có nghĩa được cấp quyền phê duyệt.

### 6.1. Giới hạn quyền ủy quyền

Một mô hình ủy quyền có thể ghi rõ:

```text
Người quản trị: admin-a
Phạm vi được quản trị: tenant A / project P
Vai trò được gán: VIEWER, PREPARER
Thời hạn assignment tối đa: theo chính sách cấp quyền dự án
Không được gán: APPROVER, ROLE_ADMIN hoặc role toàn hệ thống
```

Các giới hạn phải được kiểm tra ở server. Việc ẩn role nhạy cảm khỏi danh sách trên giao diện không ngăn người dùng gửi request trực tiếp với ID role đó.

Phê duyệt cũng phải gắn với đối tượng được duyệt. Nếu một request được duyệt cho role `VIEWER` tại project P, client không được đổi payload thành `APPROVER` tại project Q sau khi duyệt. Có thể dùng yêu cầu bất biến hoặc version của request để ràng buộc nội dung phê duyệt với nội dung được áp dụng.

### 6.2. Những đường leo thang đặc quyền gián tiếp

Ngay cả khi endpoint gán role được bảo vệ, quyền vẫn có thể bị mở qua những đường khác:

- Người dùng tự sửa trường nhóm hoặc role trong hồ sơ của mình.
- Quản trị viên phạm vi hẹp sửa nội dung của role mà mình được phép gán, thêm permission quản trị rồi gán role đó.
- Người quản lý nhóm thêm chính mình vào nhóm nhận quyền đặc quyền.
- Một role được phép gán có quan hệ kế thừa mới dẫn tới role nhạy cảm.
- Tác vụ đồng bộ dùng role mặc định quá rộng khi không ánh xạ được nhóm nguồn.

Kiểm soát role assignment vì thế phải xét cả định nghĩa role, mapping, thành viên nhóm và quyền quản trị các cấu hình liên quan.

## 7. Ràng buộc khi gán vai trò

### 7.1. Separation of duties

Trong ví dụ hóa đơn, tổ chức có thể quy định một người không được đồng thời có `PREPARER` và `APPROVER` trong cùng dự án. Đây là một lựa chọn phân tách nhiệm vụ ở mức cấp vai trò.

Nếu cấm đồng thời nhận hai role, hệ thống phải kiểm tra khi cấp assignment. Nếu cho phép được gán cả hai nhưng cấm kích hoạt đồng thời trong một phiên, việc kiểm soát nằm ở thời điểm kích hoạt. Hai lựa chọn này có mức hạn chế khác nhau và không thể thay thế tùy tiện.

Ngoài ra, quy tắc “không được duyệt hóa đơn mình đã lập” là ràng buộc trên giao dịch cụ thể. Người dùng có thể đã lập hóa đơn hôm qua bằng một role, rồi được chuyển sang role phê duyệt hôm nay. Chỉ nhìn các role đang có hôm nay không đủ để ngăn tự duyệt; cần đối chiếu danh tính người lập trong lịch sử giao dịch.

### 7.2. Phải kiểm tra quyền nhận được qua mọi nguồn

Nếu Lan đã nhận `PREPARER` qua nhóm, một luồng gán trực tiếp `APPROVER` chỉ kiểm tra bảng assignment trực tiếp sẽ bỏ sót xung đột.

Tập kiểm tra cần phản ánh các nguồn có thể tạo ra role hoặc năng lực bị cấm kết hợp, bao gồm phân cấp và mapping mà ứng dụng hỗ trợ. Phạm vi xung đột cũng phải rõ: cùng dự án, cùng tenant hay toàn tổ chức.

Ví dụ, cho Lan chuẩn bị hóa đơn ở project P và phê duyệt ở project Q chỉ hợp lệ nếu chính sách cho phép hai phạm vi này độc lập. Nếu một hóa đơn có thể di chuyển giữa dự án, cần đánh giá thêm ràng buộc trên giao dịch.

### 7.3. Phải xét cả assignment ở tương lai

Hai assignment có thể chưa có hiệu lực hiện tại nhưng sẽ xung đột khi cùng bắt đầu trong tương lai.

Với khoảng thời gian nửa mở `[from, until)`, hai khoảng A và B chồng nhau khi:

```text
A.from < B.until AND B.from < A.until
```

Nếu A kết thúc đúng lúc B bắt đầu thì hai khoảng không chồng nhau theo quy ước này. Tuy nhiên, các ràng buộc trên lịch sử giao dịch vẫn cần kiểm tra độc lập.

### 7.4. Giới hạn số lượng và điều kiện tiên quyết

Một hệ thống có thể giới hạn số người giữ một role nhạy cảm trong một phạm vi hoặc yêu cầu hoàn thành đào tạo trước khi nhận role. Đây là chính sách bổ sung, không phải thuộc tính tự có của mọi RBAC engine.

Kiểm tra cần sử dụng nguồn dữ liệu có thẩm quyền và thời hạn phù hợp. Một chứng nhận đã hết hạn không nên được coi là đạt chỉ vì người dùng từng hoàn thành nó.

Nếu điều kiện có thể thay đổi sau khi cấp, cần xác định cách xử lý khi nó không còn đạt: thu hồi assignment, ngừng kích hoạt hay kiểm tra lại ở mỗi lần sử dụng quyền.

## 8. Ví dụ Java: thời hạn, phạm vi và xung đột assignment

Ví dụ sau dùng Java 17 và chỉ mô hình hóa assignment trực tiếp, phạm vi chính xác theo cặp tenant–project, không có kế thừa role hoặc nhóm. `PREPARER` và `APPROVER` được coi là xung đột nếu cùng chủ thể, cùng phạm vi và có thời gian hiệu lực chồng nhau.

Code minh họa cách tính role có hiệu lực và phát hiện một loại xung đột. Nó không phải API cấp quyền hoàn chỉnh: các bước xác thực người quản trị, phê duyệt, kiểm tra trạng thái người dùng và ghi giao dịch vẫn phải do lớp dịch vụ thực hiện.

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class RoleAssignmentDemo {
    enum Role {
        VIEWER, PREPARER, APPROVER
    }

    enum GrantState {
        GRANTED, REVOKED
    }

    private static String requireId(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing identifier");
        }
        return value;
    }

    record Scope(String tenantId, String projectId) {
        Scope {
            tenantId = requireId(tenantId);
            projectId = requireId(projectId);
        }
    }

    record Assignment(
            String id,
            String subjectId,
            Role role,
            Scope scope,
            Instant validFrom,
            Instant validUntil,
            GrantState state) {
        Assignment {
            id = requireId(id);
            subjectId = requireId(subjectId);
            Objects.requireNonNull(role);
            Objects.requireNonNull(scope);
            Objects.requireNonNull(validFrom);
            Objects.requireNonNull(validUntil);
            Objects.requireNonNull(state);
            if (!validFrom.isBefore(validUntil)) {
                throw new IllegalArgumentException("Invalid time window");
            }
        }

        boolean effectiveAt(Instant now) {
            Objects.requireNonNull(now);
            return state == GrantState.GRANTED
                    && !now.isBefore(validFrom)
                    && now.isBefore(validUntil);
        }
    }

    static Set<Role> effectiveRoles(String subjectId,
                                    Scope scope,
                                    Instant now,
                                    List<Assignment> assignments) {
        requireId(subjectId);
        Objects.requireNonNull(scope);
        Objects.requireNonNull(now);
        Objects.requireNonNull(assignments);

        Set<Role> roles = new HashSet<>();
        for (Assignment assignment : assignments) {
            if (assignment.subjectId().equals(subjectId)
                    && assignment.scope().equals(scope)
                    && assignment.effectiveAt(now)) {
                roles.add(assignment.role());
            }
        }
        return Set.copyOf(roles);
    }

    private static boolean incompatible(Role left, Role right) {
        return (left == Role.PREPARER && right == Role.APPROVER)
                || (left == Role.APPROVER && right == Role.PREPARER);
    }

    static boolean hasConflict(Assignment candidate,
                               List<Assignment> existing) {
        Objects.requireNonNull(candidate);
        Objects.requireNonNull(existing);

        if (candidate.state() != GrantState.GRANTED) {
            return false;
        }

        for (Assignment assignment : existing) {
            boolean sameSubjectAndScope =
                    assignment.subjectId().equals(candidate.subjectId())
                    && assignment.scope().equals(candidate.scope());
            boolean overlaps = assignment.validFrom()
                    .isBefore(candidate.validUntil())
                    && candidate.validFrom()
                    .isBefore(assignment.validUntil());

            if (assignment.state() == GrantState.GRANTED
                    && sameSubjectAndScope
                    && overlaps
                    && incompatible(assignment.role(), candidate.role())) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        Scope projectP = new Scope("tenant-a", "project-p");
        Assignment preparer = new Assignment(
                "ra-1", "user-lan", Role.PREPARER, projectP,
                Instant.parse("2026-12-01T08:00:00Z"),
                Instant.parse("2026-12-01T09:00:00Z"),
                GrantState.GRANTED);
        List<Assignment> assignments = List.of(preparer);

        System.out.println(effectiveRoles(
                "user-lan", projectP,
                Instant.parse("2026-12-01T08:30:00Z"), assignments));
        System.out.println(effectiveRoles(
                "user-lan", projectP,
                Instant.parse("2026-12-01T09:00:00Z"), assignments));

        Assignment approver = new Assignment(
                "ra-2", "user-lan", Role.APPROVER, projectP,
                Instant.parse("2026-12-01T08:45:00Z"),
                Instant.parse("2026-12-01T09:30:00Z"),
                GrantState.GRANTED);
        System.out.println(hasConflict(approver, assignments));
    }
}
```

Đầu ra dự kiến:

```text
[PREPARER]
[]
true
```

Đúng 09:00Z, assignment `ra-1` hết hiệu lực. Assignment đề xuất `ra-2` chồng thời gian với `ra-1` từ 08:45Z tới trước 09:00Z nên bị phát hiện xung đột.

Hàm `hasConflict` trả `false` chỉ cho biết chưa thấy loại xung đột mà ví dụ định nghĩa. Kết quả đó không có nghĩa người gọi được phép cấp role. Cũng không nên truyền danh sách assignment do client tự khai báo; dữ liệu đầu vào phải được tải từ nguồn cấp quyền có thẩm quyền.

Một điểm hạn chế khác là phép so sánh `Scope.equals`: code chỉ hỗ trợ cùng phạm vi chính xác. Nếu bổ sung role toàn tenant áp dụng xuống dự án, phải thay logic bằng quan hệ bao phủ hoặc giao nhau giữa các scope, đồng thời cập nhật kiểm tra xung đột tương ứng.

## 9. Ghi assignment an toàn trong hệ thống thực tế

### 9.1. Kiểm tra và ghi phải bảo vệ được tính đồng thời

Giả sử hai quản trị viên cùng cấp `PREPARER` và `APPROVER` cho Lan. Cả hai đọc dữ liệu khi Lan chưa có role nào, đều thấy không xung đột rồi cùng ghi. Kết quả cuối cùng vi phạm quy tắc dù từng lần kiểm tra riêng lẻ đều vượt qua.

Quy trình cần bảo đảm tính nhất quán cho tập assignment bị ràng buộc. Tùy hệ lưu trữ, có thể sử dụng mức cô lập giao dịch phù hợp, khóa một bản ghi điều phối theo chủ thể–phạm vi hoặc cơ chế ràng buộc có khả năng kiểm tra các khoảng thời gian liên quan.

Chỉ đặt unique constraint trên `(subjectId, roleId, scopeId)` không ngăn được xung đột giữa hai role khác nhau. Kiểm tra xung đột cũng phải được thực hiện lại khi gia hạn, đổi phạm vi hoặc thay đổi mapping role, chứ không chỉ khi tạo mới.

Một luồng khái niệm:

```text
Nhận yêu cầu đã xác thực
  -> tải nội dung phê duyệt và thẩm quyền hiện tại
  -> bắt đầu giao dịch với cơ chế nhất quán phù hợp
  -> đọc tập assignment và các ràng buộc liên quan
  -> kiểm tra scope, thời hạn, xung đột và giới hạn cấp
  -> ghi assignment và sự kiện kiểm toán bền vững
  -> commit
  -> đồng bộ thay đổi tới các nơi thực thi
  -> xác minh trạng thái và độ trễ thực thi
```

Chi tiết giao dịch phải được chọn theo cơ sở dữ liệu và phạm vi ràng buộc thực tế. Sơ đồ trên không tự bảo đảm an toàn chỉ bằng việc bọc code trong một annotation giao dịch.

### 9.2. Retry không được tạo quyền ngoài ý muốn

Một request có thể được gửi lại khi client timeout. Hệ thống nên có khóa idempotency hoặc định danh yêu cầu để nhận biết thao tác đã được áp dụng, đồng thời kiểm tra nội dung lặp lại có khớp yêu cầu ban đầu không.

Không nên biến request lặp thành gia hạn vô hạn hoặc tạo nhiều nguồn assignment không cần thiết. Nếu role, phạm vi hoặc thời hạn thay đổi, đó là thay đổi quyền cần được xử lý theo chính sách tương ứng.

### 9.3. Ghi thành công và có hiệu lực là hai kết quả cần phân biệt

Assignment có thể được ghi ở hệ thống quản trị nhưng chưa tới ứng dụng đích. Nếu provisioning bất đồng bộ, phản hồi nên cho biết thay đổi đang chờ áp dụng thay vì khẳng định người dùng chắc chắn đã có quyền.

Có thể dùng outbox hoặc một cơ chế phát sự kiện bền vững để tránh tình trạng cơ sở dữ liệu đã đổi nhưng sự kiện đồng bộ bị mất. Consumer cần xử lý retry, sự kiện trùng và thứ tự thay đổi, đặc biệt khi sự kiện cấp và thu hồi tới sai thứ tự.

Sự kiện cũ không được làm sống lại một assignment đã thu hồi bằng phiên bản mới hơn. Vì vậy, định danh assignment, version và nguồn thay đổi cần được thiết kế rõ.

## 10. Thu hồi assignment và giới hạn của token

### 10.1. Thu hồi một nguồn không chắc thu hồi toàn bộ quyền

Trước khi kết luận Lan đã mất quyền phê duyệt, cần kiểm tra Lan có còn nhận quyền qua nhóm, một assignment khác, role kế thừa hoặc một cơ chế ngoại lệ hay không.

Màn hình quản trị hữu ích nên thể hiện đường dẫn quyền, chẳng hạn:

```text
Quyền invoice:approve trong project P
  Nguồn 1: assignment trực tiếp ra-15 -> APPROVER
  Nguồn 2: nhóm Finance-P -> assignment ga-9 -> APPROVER
```

Nếu chỉ xóa `ra-15`, nguồn thứ hai vẫn còn. Cần thu hồi đúng nguồn hoặc thay đổi membership phù hợp, đồng thời giữ lại lịch sử để giải thích hành động.

### 10.2. Claim trong token có thể là snapshot cũ

Giả sử access token được phát hành lúc 08:00 chứa role `APPROVER`, còn assignment bị thu hồi lúc 08:10. Nếu ứng dụng chỉ kiểm tra token tự chứa và không có cơ chế cập nhật quyền trong thời gian token còn hiệu lực, role cũ có thể tiếp tục được chấp nhận theo thiết kế hiện tại.

Không thể hứa thu hồi ngay chỉ vì bản ghi assignment đã bị đổi. Độ trễ phụ thuộc thời hạn token, cache, session, cơ chế kiểm tra trực tuyến và cách truyền thay đổi tới nơi thực thi.

Các lựa chọn thiết kế có thể gồm thời hạn token phù hợp, đối chiếu phiên bản quyền, tra quyền ở server, vô hiệu hóa phiên hoặc cơ chế thu hồi mà nền tảng hỗ trợ. Cần cân nhắc cả khả dụng và tải hệ thống; không có một biện pháp duy nhất phù hợp mọi ứng dụng.

### 10.3. Hết hạn phải được thực thi khi sử dụng quyền

Job dọn assignment hết hạn có ích cho vận hành, nhưng quyền không nên tiếp tục được dùng chỉ vì job chạy trễ. Nơi đánh giá quyền cần kiểm tra thời hạn hoặc sử dụng dữ liệu đã được bảo đảm còn hiệu lực.

Tương tự, thay đổi trạng thái tài khoản phải có cách tác động tới quyền thực tế. Khóa người dùng trong directory nhưng giữ mọi phiên và cache đặc quyền không giới hạn sẽ tạo khoảng cách giữa quyết định quản trị và thực thi.

## 11. Role assignment trong vòng đời danh tính

### 11.1. Khi gia nhập

Quyền ban đầu nên xuất phát từ công việc được xác minh và phạm vi cần thiết. Không sao chép toàn bộ role từ một người cùng chức danh mà chưa kiểm tra các ngoại lệ, quyền tạm thời hoặc quyền lịch sử của người đó.

Một bộ quyền nền tảng có thể được cấp tự động nếu điều kiện rõ và dữ liệu nguồn đáng tin cậy. Role nhạy cảm có thể cần phê duyệt riêng. Tự động hóa không làm mất trách nhiệm giải thích vì sao assignment được tạo.

### 11.2. Khi chuyển vị trí hoặc dự án

Chỉ thêm role mới sẽ gây tích lũy quyền. Quá trình chuyển công việc cần đối chiếu role cũ còn cần thiết hay không, chấm dứt các assignment không còn căn cứ và quản lý riêng giai đoạn bàn giao nếu có.

Nếu cần giữ quyền cũ trong một thời gian ngắn để bàn giao, nên thể hiện bằng một ngoại lệ có thời hạn và người chịu trách nhiệm. Không dùng lời hứa “sẽ xóa sau” thay cho điều kiện kết thúc rõ ràng.

### 11.3. Khi rời tổ chức hoặc ngừng workload

Cần xử lý account, assignment, nhóm, phiên và các thông tin xác thực liên quan theo quy trình thu hồi. Assignment không nên tiếp tục tạo quyền cho một danh tính mới chỉ vì tái sử dụng email hoặc tên tài khoản cũ.

Với workload, thay thế một service không có nghĩa service mới tự nhận toàn bộ quyền của service cũ. Hãy cấp theo nhiệm vụ và môi trường cụ thể, đồng thời thu hồi danh tính và assignment không còn dùng.

### 11.4. Khi rà soát định kỳ

Người rà soát cần nhìn thấy subject, role, permission liên quan, scope, nguồn cấp, thời hạn, căn cứ và việc sử dụng gần đây nếu dữ liệu đó có sẵn. Chỉ đưa danh sách tên role mà không giải thích quyền sẽ khiến việc xác nhận mang tính hình thức.

Không sử dụng gần đây là tín hiệu để xem xét, không phải bằng chứng tuyệt đối rằng quyền không cần thiết. Ngược lại, quyền đang được dùng không chứng minh nó còn phù hợp với công việc hiện tại.

## 12. Kiểm toán và khả năng giải thích quyền

Một sự kiện cấp vai trò có thể chứa:

```json
{
  "eventType": "ROLE_ASSIGNMENT_GRANTED",
  "assignmentId": "ra-1042",
  "subjectId": "user-lan",
  "roleId": "invoice-preparer",
  "tenantId": "tenant-a",
  "projectId": "project-p",
  "requestedBy": "user-lan",
  "approvedBy": "user-manager",
  "executedBy": "access-workflow-service",
  "requestId": "access-request-281",
  "validFrom": "2026-12-01T01:00:00Z",
  "validUntil": "2027-03-01T01:00:00Z",
  "assignmentVersion": 1
}
```

Người yêu cầu, người phê duyệt và dịch vụ thực thi có thể là ba danh tính khác nhau. Việc chỉ ghi `createdBy=system` sẽ làm mất ngữ cảnh quyết định nếu không có liên kết tới yêu cầu và phê duyệt.

Cần ghi cả thay đổi phạm vi, gia hạn, thu hồi, mapping và định nghĩa role có ảnh hưởng tới quyền. Log phải được bảo vệ phù hợp; không đưa token, bí mật hoặc dữ liệu cá nhân không cần thiết vào sự kiện.

Hai hướng truy vấn cần hỗ trợ là:

- Từ người dùng: hiện tại nhận những role nào, trong phạm vi nào, qua những nguồn nào?
- Từ quyền hoặc role: ai đang hoặc sẽ có quyền này, ai cấp, hiệu lực đến khi nào?

Khi điều tra một thao tác trong quá khứ, dữ liệu trạng thái hiện tại có thể không đủ. Cần khả năng liên hệ thời điểm thao tác với assignment, phiên bản role và các điều kiện có hiệu lực khi đó.

## 13. Những tình huống cần kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người quản trị hợp lệ cấp role trong phạm vi được ủy quyền | Tạo đúng assignment đã được phê duyệt |
| Người dùng thông thường gọi trực tiếp API cấp role | Bị chặn ở server |
| Quản trị viên project P cấp role tại project Q | Bị chặn nếu không có ủy quyền tương ứng |
| Request đã duyệt bị đổi role hoặc scope trước khi áp dụng | Không áp dụng nội dung khác phê duyệt |
| Assignment bắt đầu ở tương lai | Chưa tạo quyền sử dụng ở hiện tại |
| Đánh giá đúng tại `validUntil` | Assignment không còn hiệu lực |
| Cấp hai role xung đột qua hai request đồng thời | Trạng thái cuối không vi phạm ràng buộc |
| Role xung đột đã có qua nhóm hoặc kế thừa | Không bỏ sót khi kiểm tra |
| Hai assignment tương lai có khoảng thời gian chồng nhau | Phát hiện xung đột theo chính sách |
| Retry cùng request và cùng nội dung | Không nhân bản quyền hoặc tự gia hạn |
| Thu hồi một assignment nhưng còn nguồn khác | Hiển thị và đánh giá đúng quyền còn lại |
| Sự kiện cấp cũ tới sau sự kiện thu hồi mới | Không làm sống lại quyền cũ |
| Token hoặc cache giữ role sau khi thu hồi | Hành vi phù hợp yêu cầu và giới hạn độ trễ đã thiết kế |
| Người lập hóa đơn đổi sang role phê duyệt | Không tự duyệt hóa đơn của mình nếu nghiệp vụ cấm |
| Đồng bộ không ánh xạ được role nguồn | Không tự cấp một role rộng để thay thế |

Kiểm thử cần quan sát dữ liệu cuối cùng và tác dụng quyền, không chỉ mã phản hồi API. Một request trả lỗi nhưng đã tạo assignment ở hệ thống đích vẫn là lỗi cấp quyền. Một request thu hồi thành công ở hệ thống quản trị nhưng quyền còn hoạt động vượt giới hạn đã cam kết cũng cần được phát hiện.

## 14. Bài tập tình huống

Lan được gán `PREPARER` tại project P qua nhóm kế toán. Sau đó, quản trị viên cấp trực tiếp `APPROVER` cho Lan trong cùng project, có hiệu lực vào tuần sau. Luồng cấp mới chỉ kiểm tra các assignment trực tiếp đang có hiệu lực hiện tại, nên chấp nhận yêu cầu.

Một tháng sau, Lan chuyển sang project Q. Hệ thống thêm role của Q nhưng không xử lý membership nhóm cũ. Quản trị viên xóa assignment trực tiếp và thông báo rằng Lan đã mất quyền tại P.

Hãy xác định những điều cần kiểm tra trước khi kết luận quyền đã đúng.

### Gợi ý phân tích

Trước hết, nguồn nhóm có thể đã tạo role xung đột với assignment trực tiếp. Luồng kiểm tra phải tính đủ nguồn quyền, đúng phạm vi và cả khoảng thời gian tương lai. Nếu nghiệp vụ dùng ràng buộc theo giao dịch, còn phải lưu và kiểm tra danh tính người lập hóa đơn, thay vì chỉ dựa vào role hiện tại.

Tiếp theo, việc chuyển dự án cần đối chiếu các assignment và membership cũ với nhiệm vụ mới. Xóa một assignment trực tiếp không xóa nguồn nhóm. Hệ thống phải kiểm tra quyền thực tế tại project P sau thay đổi, đồng thời xét token, cache và độ trễ đồng bộ.

Cuối cùng, người rà soát cần phân biệt “đã xóa một bản ghi” với “mọi nguồn quyền thuộc phạm vi cần thu hồi đã chấm dứt và nơi thực thi đã áp dụng”. Một assignment được quản lý tốt phải giải thích được ai nhận role, nhận qua đâu, được làm gì, ở phạm vi nào và tới khi nào.

## 15. Tài liệu tham khảo

- [NIST — Role Based Access Control FAQs](https://csrc.nist.gov/projects/role-based-access-control/faqs): các quan hệ nền tảng, vai trò và kích hoạt trong mô hình RBAC. Đây là nguồn khái niệm thuộc dự án lưu trữ của NIST.
- [NIST — Role Based Access Control](https://csrc.nist.gov/projects/role-based-access-control): tài liệu nền tảng và các hướng nghiên cứu về quản trị quyền dựa trên vai trò.
- [Microsoft Learn — What is Privileged Identity Management?](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure): ví dụ triển khai assignment và kích hoạt role có điều kiện trong một nền tảng IAM.
