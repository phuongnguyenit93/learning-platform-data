# Role — Vai trò trong phân quyền

## 1. Vai trò là một đơn vị tổ chức quyền

Role, hay vai trò, biểu diễn một nhóm quyền gắn với trách nhiệm trong hệ thống. Thay vì cấp từng quyền riêng lẻ cho mỗi tài khoản, hệ thống định nghĩa những vai trò như người xem hồ sơ, người chỉnh sửa thông tin công việc hoặc người quản trị danh tính, rồi gán vai trò phù hợp cho chủ thể.

Trong mô hình RBAC, hai quan hệ nền tảng là gán người dùng vào vai trò và gán quyền vào vai trò. Mô hình còn có khái niệm kích hoạt vai trò trong phiên. Đây là các khái niệm được trình bày trong tài liệu mô hình RBAC của NIST; trang dự án hiện được lưu trữ để tham khảo lịch sử, không phải tài liệu cập nhật cho một sản phẩm cụ thể. [Nguồn: NIST, Role Based Access Control FAQs](https://csrc.nist.gov/projects/role-based-access-control/faqs).

Ví dụ, một nhân viên nhân sự cần đọc hồ sơ và sửa thông tin công việc. Nếu có 50 người cùng trách nhiệm đó, cấp một role đã được duyệt giúp nhóm IAM quản lý nhất quán hơn so với tự chọn lại hàng chục permission cho từng người.

Role không chứng minh danh tính người dùng. Xác thực xác định ngữ cảnh chủ thể; phân quyền dùng role cùng các điều kiện khác để quyết định chủ thể được làm gì. Việc đăng nhập bằng MFA cũng không tự cấp một role quản trị.

## 2. Role khác permission, group và scope như thế nào?

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Subject | Ai hoặc workload nào đang yêu cầu? | Tài khoản `u-104`, dịch vụ đồng bộ nhân sự |
| Permission | Được thực hiện hành động nào? | `profile:work-info:update` |
| Role | Những quyền nào đi cùng một trách nhiệm? | `HR_EDITOR` |
| Group | Những chủ thể nào được tập hợp theo một tiêu chí? | Nhóm nhân sự chi nhánh phía Nam |
| Scope của assignment | Vai trò có hiệu lực ở đâu? | Tenant A, phòng ban D1 hoặc một dự án |
| Policy hoặc constraint | Còn điều kiện nào phải thỏa? | Không tự phê duyệt yêu cầu của mình |

Một group có thể được ánh xạ tới role, nhưng hai khái niệm không tự đồng nhất. Nhóm thư mục “Phòng Nhân sự” mô tả tập người; role `HR_EDITOR` mô tả quyền theo trách nhiệm của ứng dụng. Không phải mọi thành viên phòng nhân sự đều cần quyền chỉnh sửa cùng một loại dữ liệu.

Tương tự, chức danh “trưởng phòng” là dữ liệu tổ chức, không phải một bộ quyền kỹ thuật cố định cho mọi dịch vụ. Ứng dụng phải định nghĩa rõ chức danh hoặc quan hệ tổ chức nào dẫn đến quyền nào và trong phạm vi nào.

Trong bài, “scope của assignment” là phạm vi tài nguyên áp dụng cho một lần gán vai trò. Nó không mặc nhiên có cùng nghĩa với tham số OAuth `scope`. Nếu một token OAuth có scope truy cập API, hệ thống vẫn cần hiểu chủ thể, quyền và phạm vi tài nguyên theo hợp đồng của dịch vụ.

## 3. Mô hình Subject → Role → Permission

Mối quan hệ cơ bản có thể biểu diễn như sau:

```text
An ── được gán ──> HR_EDITOR
                         ├── profile:basic:read
                         └── profile:work-info:update

Bình ─ được gán ──> HR_VIEWER
                         └── profile:basic:read
```

Một role có thể được gán cho nhiều chủ thể. Một chủ thể cũng có thể được gán nhiều role. Tên role là định danh của một tập quyền theo chính sách, không phải một từ khóa tự có quyền lực.

Nếu ứng dụng chỉ lưu chuỗi `ADMIN` nhưng không định nghĩa nó được làm gì, role đó chưa tạo thành một mô hình phân quyền có thể kiểm chứng. Tương tự, đặt tên `SUPER_ADMIN` không tự khiến framework hiểu rằng nó kế thừa mọi quyền.

Mô hình dữ liệu khái niệm:

```text
role
  id
  code
  description
  owner
  status
  policy_version

role_permission
  role_id
  permission_code

subject_role_assignment
  subject_id
  role_id
  scope
  valid_from
  valid_until
  status
  approved_by
```

Các trường trên minh họa trách nhiệm quản lý, không phải schema bắt buộc. Cần phân biệt sửa định nghĩa role với gán role cho một người: thêm permission vào một role có thể làm thay đổi quyền của tất cả chủ thể đang được gán role đó.

## 4. Ví dụ phân vai cho cổng nhân sự

Cổng nhân sự giả định có các trách nhiệm sau. Dấu “Có” chỉ cho biết quyền thuộc role; mọi quyết định vẫn chịu scope và điều kiện liên quan.

| Role | Đọc hồ sơ cơ bản | Sửa thông tin công việc | Xem dữ liệu lương | Quản lý gán role |
| --- | --- | --- | --- | --- |
| `EMPLOYEE` | Có, trong phạm vi bản thân | Không | Không qua quyền này | Không |
| `HR_VIEWER` | Có, trong phạm vi được cấp | Không | Không | Không |
| `HR_EDITOR` | Có, trong phạm vi được cấp | Có, trong phạm vi được cấp | Không | Không |
| `PAYROLL_VIEWER` | Theo quyền bổ sung được duyệt | Không | Có, trong phạm vi được cấp | Không |
| `IAM_ADMIN` | Không tự được cấp | Không | Không | Có, theo giới hạn ủy quyền |

Ví dụ này chủ động tách quản trị danh tính khỏi truy cập dữ liệu lương. Người hỗ trợ cấp quyền không nhất thiết phải đọc mọi dữ liệu của người mà họ hỗ trợ.

Role `EMPLOYEE` ở đây không bao gồm mọi chức năng tự phục vụ có thể có trong một sản phẩm thực tế. Nếu cần sửa địa chỉ liên hệ hoặc xem phiếu lương của bản thân, nhóm thiết kế bổ sung permission và quy tắc phù hợp; không suy diễn từ tên “nhân viên” rằng mọi quyền đó đã tồn tại.

`IAM_ADMIN` cũng không được phép gán bất kỳ role nào cho bất kỳ ai. Chức năng quản lý assignment cần biết người quản trị được quản lý tenant nào, được gán những role nào và có cần phê duyệt hay không. Một permission quản trị quá rộng có thể trở thành đường tự nâng quyền.

## 5. Gán role phải có phạm vi

Xét hai assignment:

```text
An → HR_EDITOR → tenant A, department D1
An → HR_VIEWER → tenant A, department D2
```

An có thể sửa thông tin công việc thuộc D1 và chỉ xem hồ sơ được cấp ở D2. Không được lấy toàn bộ role của An thành một tập không có phạm vi rồi kết luận An có quyền sửa mọi hồ sơ ở tenant A.

Một request cập nhật hồ sơ cần đánh giá tối thiểu các quan hệ sau:

```text
chủ thể đang hoạt động
    AND assignment còn hiệu lực
    AND role có permission cho hành động
    AND assignment bao phủ tenant và tài nguyên đích
    AND các ràng buộc nghiệp vụ được thỏa mãn
```

Tenant và phòng ban của tài nguyên phải đến từ dữ liệu tin cậy. Nếu client gửi `departmentId=D1` nhưng hồ sơ thật thuộc D2, backend không được dùng khai báo của client để cho phép cập nhật.

Một role quản trị tenant A không tự trở thành role quản trị tenant B. Khi cùng một người tham gia nhiều tổ chức, các assignment phải giữ được quan hệ giữa chủ thể, role và scope tương ứng.

Scope cũng không chỉ là bộ lọc giao diện. API đọc chi tiết, cập nhật, xuất báo cáo, tìm kiếm và xử lý hàng loạt đều cần áp dụng phạm vi phù hợp. Một endpoint được bỏ sót có thể làm người có role đúng truy cập sai dữ liệu.

## 6. Nhiều role, kế thừa và xung đột

Trong một mô hình đơn giản chỉ có permission cho phép, các role hợp lệ có thể đóng góp quyền theo phép hợp. Tuy nhiên, khi có scope, điều kiện hoặc quy tắc từ chối, không thể chỉ hợp nhất các chuỗi permission rồi bỏ qua phần còn lại.

Ví dụ, An có `HR_EDITOR` trong D1 và `HR_VIEWER` trong D2. Hợp các permission toàn cục sẽ làm mất thông tin khiến một quyền chỉ được dùng ở D1. Quyết định phải giữ nguồn assignment hoặc một biểu diễn quyền hiệu lực có cùng ý nghĩa.

Role hierarchy là quan hệ kế thừa quyền được định nghĩa rõ. Trong cổng nhân sự có thể chọn `HR_EDITOR` kế thừa quyền đọc của `HR_VIEWER`, nhưng phải kiểm tra tác động và scope. Không suy ra hierarchy từ chức danh hoặc sơ đồ tổ chức.

Nếu sản phẩm có explicit deny, phải xác định cách kết hợp chính sách: deny có ưu tiên không, phạm vi nào áp dụng và xử lý xung đột thế nào. RBAC cơ bản không tự định nghĩa một quy tắc ưu tiên chung cho mọi hệ thống có allow và deny.

Không giải quyết xung đột bằng cách chọn role có tên “cao nhất” theo thứ tự chuỗi. Quyền hiệu lực phải đến từ quan hệ và chính sách, không đến từ cách sắp xếp tên.

## 7. Tách nhiệm vụ và kích hoạt đặc quyền

Không phải mọi tập role đều nên được kết hợp tự do. Ví dụ, người tạo yêu cầu cấp quyền không nên tự phê duyệt chính yêu cầu đó. Một số tổ chức còn không cho cùng một người đồng thời giữ hai vai trò có trách nhiệm xung đột.

Cần phân biệt:

- Ràng buộc khi gán: ngăn cấp đồng thời những role không được phép cùng tồn tại trên một chủ thể.
- Ràng buộc khi kích hoạt hoặc sử dụng: người có nhiều role vẫn phải chọn vai trò hoặc tuân thủ điều kiện cho phiên, giao dịch cụ thể.

Tài liệu mô hình RBAC của NIST phân biệt static separation of duty và dynamic separation of duty, cũng như việc kích hoạt một tập con các role đã được gán trong phiên. [Nguồn: NIST, RBAC Model Components](https://csrc.nist.gov/projects/role-based-access-control/faqs).

Đối với role đặc quyền, một assignment có thể chưa đủ để sử dụng ngay. Chính sách có thể yêu cầu kích hoạt có thời hạn, lý do công việc, phê duyệt hoặc MFA đủ mới. Các điều kiện này phải được backend kiểm tra, không chỉ ghi trong hướng dẫn người dùng.

Xác thực lại thành công không tạo role chưa được cấp. Ngược lại, có role đặc quyền không tự làm mọi phiên của chủ thể đạt mức MFA cần thiết. Phân quyền và mức xác thực là hai chiều cần phối hợp.

## 8. Role được kiểm tra ở đâu trong request?

Một luồng xử lý có thể đi như sau:

```text
Xác minh credential hoặc phiên
        ↓
Xác định chủ thể và tenant hợp lệ
        ↓
Lấy assignment và định nghĩa role có hiệu lực
        ↓
Xác định tài nguyên, hành động và scope thực tế
        ↓
Đánh giá permission cùng các ràng buộc
        ↓
Cho phép hoặc từ chối trước khi đọc hoặc sửa dữ liệu bảo vệ
```

OWASP khuyến nghị ít quyền nhất, từ chối mặc định và kiểm tra quyền trên mọi request. Đăng nhập thành công hoặc biết định danh tài nguyên không thay thế kiểm tra quyền. [Nguồn: OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Một đường dẫn như `/admin/**` có thể dùng role để chặn truy cập ở mức tổng quát, nhưng tài nguyên cụ thể vẫn cần kiểm tra quyền ở lớp thích hợp. Người có role quản trị một phạm vi không nên đi qua cổng `/admin` rồi đọc được mọi tenant.

Tương tự, ẩn nút “Sửa” giúp giao diện dễ sử dụng, nhưng request trực tiếp vẫn phải bị từ chối khi thiếu quyền. Không dùng UUID khó đoán để thay thế authorization ở mức đối tượng.

Nếu dịch vụ khác hoặc job nền gọi cùng nghiệp vụ, cần biết nó hoạt động dưới danh tính nào và quyền được ủy quyền ra sao. Không mặc định một lời gọi nội bộ được bỏ qua scope và kiểm soát đặc quyền.

## 9. Ví dụ với Spring Security

Trong Spring Security, `hasRole('HR_EDITOR')` theo cấu hình mặc định kiểm tra authority `ROLE_HR_EDITOR`; `hasAuthority(...)` kiểm tra trực tiếp giá trị authority được cung cấp. Muốn dùng annotation phương thức cần bật method security và gọi qua thành phần Spring được bảo vệ. [Nguồn: Spring Security, Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Một phương thức minh họa có thể kiểm tra role ở mức tổng quát:

```java
@PreAuthorize("hasRole('HR_EDITOR')")
public void updateWorkInfo(UUID profileId, WorkInfoPatch patch) {
    workInfoService.updateWithinAuthorizedScope(profileId, patch);
}
```

Đây là đoạn trích về vị trí kiểm tra, không phải một service hoàn chỉnh. `workInfoService` phải thực sự xác định chủ thể hiện tại, đọc metadata tài nguyên từ nguồn tin cậy và kiểm tra assignment bao phủ hành động, tenant và phòng ban. Tên method không tự tạo kiểm soát scope.

Một thiết kế khác ánh xạ role thành authority về permission rồi dùng biểu thức:

```java
@PreAuthorize("hasAuthority('profile:work-info:update')")
```

Cách này vẫn cần scope ở lớp quyết định quyền. Nếu authority chỉ giữ tên permission mà không giữ phạm vi, không được coi annotation đã phân quyền ở mức đối tượng.

Framework không tự tải mọi quan hệ role–permission nghiệp vụ chỉ từ tên role. Thành phần tạo `Authentication` hoặc dịch vụ authorization cần có ánh xạ được quản lý. Cũng cần kiểm tra đường gọi nội bộ trong bean và các endpoint khác để không vô tình đi ngoài cơ chế bảo vệ đã cấu hình.

## 10. Vòng đời assignment và thay đổi quyền

Một role assignment nên gắn với nhu cầu công việc, có người chịu trách nhiệm và có khả năng thu hồi. Trong cổng nhân sự, vòng đời có thể là:

```text
Yêu cầu cấp quyền
    ↓
Kiểm tra trách nhiệm, scope và xung đột nhiệm vụ
    ↓
Phê duyệt nếu cần
    ↓
Assignment có hiệu lực trong thời hạn cho phép
    ↓
Rà soát, thay đổi hoặc thu hồi khi nhu cầu kết thúc
```

Khi người dùng chuyển bộ phận, cần đánh giá quyền cũ trước khi bổ sung quyền mới. Chỉ cộng role theo mỗi lần đổi công việc sẽ gây tích lũy đặc quyền.

Một assignment hết hạn phải không còn được dùng trong quyết định quyền, kể cả khi job dọn dữ liệu chưa xóa bản ghi. Role bị vô hiệu hóa hoặc permission bị rút khỏi role cũng phải được phản ánh theo cơ chế cập nhật của hệ thống.

Thay định nghĩa role có phạm vi tác động khác với thu hồi role của một người. Trước khi thêm permission nhạy cảm vào role đang được sử dụng rộng, cần biết những chủ thể và assignment nào sẽ được hưởng quyền mới.

Audit nên ghi người yêu cầu, người phê duyệt, role, scope, thời điểm, lý do và thay đổi. Không ghi credential hoặc token thô chỉ để chứng minh thao tác cấp quyền đã xảy ra.

## 11. Role trong phiên, token và liên kết danh tính

Một token hoặc phiên có thể mang snapshot role tại thời điểm phát hành. Nếu assignment bị thu hồi sau đó, chữ ký token vẫn có thể hợp lệ về mặt mật mã. Điều đó không chứng minh role cũ còn được tổ chức cho phép.

Hệ thống cần quyết định cách cập nhật quyền: tra trạng thái hiện tại, dùng phiên bản phân quyền, vô hiệu hóa phiên hoặc token theo cơ chế hỗ trợ, hay chấp nhận một khoảng trễ đã được định nghĩa. Không viết “role đã thu hồi” trong database rồi cho rằng mọi API tự biết ngay.

Trong SSO/OIDC, role hoặc group do IdP gửi chỉ được dùng sau khi xác minh nguồn và hợp đồng ánh xạ. Một role tên `admin` ở IdP không mặc nhiên là quản trị toàn bộ ứng dụng. Cần xét issuer, ứng dụng nhận quyền, tenant và những giá trị được phép ánh xạ.

Không tin role trong request body, cookie tự sửa hoặc payload token chỉ được decode mà chưa xác minh. Cũng không cho dữ liệu hồ sơ tự phục vụ như chức danh hiển thị trở thành role có hiệu lực mà thiếu quy trình cấp quyền.

Workload identity cũng có thể được gán role. Assignment của workload nên phản ánh tác vụ của dịch vụ với scope phù hợp, thay vì dùng role quản trị của một nhân viên hoặc sao chép phiên người dùng để chạy tự động hóa.

## 12. Đặt tên và tránh role explosion

Tên role nên phản ánh trách nhiệm ổn định, còn mô tả cần nêu quyền, phạm vi được sử dụng và chủ sở hữu chính sách. Những tên quá chung như `POWER_USER`, `LEVEL_9` hoặc `ADMIN_2` khiến người cấp quyền khó biết thực sự đang cho phép điều gì.

Không nên tạo một role mới cho mọi tổ hợp người dùng, phòng ban và tài nguyên nếu có thể biểu diễn bằng assignment có scope. Ví dụ:

```text
Khó quản lý khi nhân rộng:
HR_EDITOR_D1_TENANT_A
HR_EDITOR_D2_TENANT_A
HR_EDITOR_D1_TENANT_B
...

Một hướng biểu diễn khác:
role = HR_EDITOR
assignment.scope = tenant A, department D1
```

Đây là lựa chọn mô hình, không phải quy tắc cấm mọi role chuyên biệt. Một trách nhiệm hoặc quy trình khác thực sự có thể cần role khác. Vấn đề là không dùng tên role để mã hóa mọi chi tiết vốn thay đổi độc lập.

Khi quyết định còn phụ thuộc quan hệ với tài nguyên, trạng thái hồ sơ hoặc thuộc tính chủ thể, role có thể phối hợp với ABAC hoặc kiểm tra quan hệ. Ví dụ, quyền “phê duyệt yêu cầu của nhân viên thuộc nhóm mình” không chỉ được giải quyết bằng việc mọi trưởng nhóm đều có chuỗi `MANAGER`.

Không xem role là phương án thay thế toàn bộ policy. Nó là một đơn vị tổ chức quyền có ích khi trách nhiệm được định nghĩa rõ và những điều kiện còn lại không bị bỏ quên.

## 13. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người dùng không có assignment phù hợp | Mặc định từ chối hành động bảo vệ |
| Có `HR_VIEWER` nhưng gọi API cập nhật | Bị từ chối |
| Có `HR_EDITOR` ở D1 nhưng sửa hồ sơ D2 | Bị từ chối nếu không có assignment khác bao phủ |
| Có role ở tenant A nhưng truy cập tenant B | Không được dùng role A để vượt phạm vi |
| Client sửa trường role hoặc department | Không tạo quyền mới |
| Assignment hết hạn nhưng bản ghi chưa bị dọn | Không còn đóng góp quyền |
| Token còn hợp lệ sau khi thu hồi role | Áp dụng cơ chế cập nhật hoặc khoảng trễ đã được thiết kế |
| Người quản trị gán role ngoài giới hạn được ủy quyền | Bị từ chối |
| Role mới xung đột với nhiệm vụ hiện có | Xử lý theo ràng buộc gán hoặc kích hoạt |
| UI ẩn nút nhưng client gọi trực tiếp API | Backend vẫn thực thi quyết định quyền |
| Thêm permission vào role phổ biến | Xác định và kiểm tra được phạm vi chủ thể bị ảnh hưởng |
| Gọi nghiệp vụ qua job hoặc dịch vụ khác | Có danh tính và scope phù hợp, không được bỏ qua policy |

Kiểm tra role không chỉ là kiểm tra một người được phép vào trang. Cần kiểm tra cả hành động, đối tượng, phạm vi, thời điểm và các đường gọi khác nhau tới cùng nghiệp vụ.

## 14. Bài tập vận dụng

Một cổng nhân sự gán `HR_EDITOR` cho An tại phòng D1 và `HR_VIEWER` tại phòng D2. API hợp mọi permission của An thành một tập toàn cục rồi kiểm tra `profile:work-info:update`. Bộ phận hỗ trợ còn có thể gán bất kỳ role nào nếu giữ `IAM_ADMIN`; token đã phát không được đánh giá lại khi assignment thay đổi.

Hãy thiết kế lại và giải thích:

1. Cần giữ những quan hệ nào để permission cập nhật chỉ có hiệu lực ở phạm vi được cấp?
2. Vì sao có role quản trị assignment không đồng nghĩa được gán mọi role?
3. Việc thêm permission vào định nghĩa role khác gì với cấp role cho một người?
4. Backend cần thực thi thay đổi assignment ra sao đối với phiên và token đang tồn tại?
5. Những trường hợp nào nên dùng role riêng, và trường hợp nào nên dùng scope hoặc điều kiện trên tài nguyên?

Một mô hình role tốt phải giúp người cấp quyền giải thích được trách nhiệm được giao, đồng thời giúp backend quyết định đúng trên tài nguyên cụ thể. Vai trò chỉ hỗ trợ nguyên tắc ít quyền nhất khi quyền bên trong, phạm vi gán và vòng đời sử dụng đều được quản lý rõ ràng.
