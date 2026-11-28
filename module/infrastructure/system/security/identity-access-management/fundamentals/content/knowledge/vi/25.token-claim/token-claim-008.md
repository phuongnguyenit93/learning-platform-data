# Token role

Token role là thông tin vai trò được truyền trong token hoặc ngữ cảnh token để bên nhận sử dụng khi quyết định quyền truy cập. Ví dụ, một access token có thể cho biết chủ thể được gán vai trò `training.instructor` trong ứng dụng đào tạo. API phải xác minh token, hiểu đúng ý nghĩa của vai trò và áp dụng chính sách trước khi cho phép thao tác.

Trong bài học này, “role” là vai trò phục vụ phân quyền, không phải các bên tham gia giao thức OAuth như client, authorization server và resource server. Mục tiêu là hiểu một role claim trở thành đầu vào của quyết định quyền như thế nào và vì sao chỉ thấy chữ `admin` trong token chưa đủ để cấp quyền quản trị.

## 1. Từ vai trò trong IAM đến role claim

Trong mô hình RBAC, vai trò thường gom một tập quyền phù hợp với trách nhiệm công việc. Chẳng hạn, hệ thống đào tạo có thể định nghĩa:

| Vai trò minh họa | Quyền theo chính sách ứng dụng |
|---|---|
| `training.learner` | Xem bài được đăng ký và kết quả học tập của mình |
| `training.instructor` | Quản lý nội dung của khóa học được phân công |
| `training.reviewer` | Duyệt nội dung theo quy trình xuất bản |
| `training.tenant-admin` | Quản trị người dùng trong một tenant được cấp quyền |

Tên vai trò và tập quyền trên do ứng dụng minh họa định nghĩa. Chúng không phải bộ vai trò chuẩn của OAuth hay JWT.

Một luồng cấp phát có thể gồm: quản trị viên gán vai trò cho người dùng, authorization server lấy các assignment phù hợp, phát hành access token, rồi API ánh xạ role claim sang chính sách nội bộ. Token mang thông tin về assignment; API vẫn là nơi thực thi quyền đối với yêu cầu cụ thể.

## 2. Claim roles có tồn tại, nhưng không có từ điển quyền chung

[RFC 9068, mục 2.2.3.1](https://www.rfc-editor.org/rfc/rfc9068.html#section-2.2.3.1) đề cập các claim `roles`, `groups` và `entitlements` để mang thông tin phục vụ phân quyền trong JWT access token. Tài liệu không quy định một bộ giá trị vai trò chung cho mọi ứng dụng.

Một hệ thống dùng `roles`, hệ thống khác có thể dùng một claim riêng hoặc cấu trúc lồng nhau. Ngay cả khi cùng có chuỗi `admin`, ý nghĩa vẫn phụ thuộc bên phát hành, ứng dụng đích và hợp đồng phân quyền. Không gom mọi role từ mọi issuer thành cùng một quyền quản trị toàn hệ thống.

Ví dụ payload rút gọn dưới đây dùng hợp đồng của ứng dụng minh họa: `roles` là mảng chuỗi và `tenant_id` là claim riêng. Đây không phải token hoàn chỉnh, không có chữ ký và không dùng để đăng nhập:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://api.training.example.org",
  "iat": 1999999100,
  "exp": 2000000000,
  "scope": "courses:read courses:write",
  "roles": ["training.instructor"],
  "tenant_id": "tenant-a"
}
```

Các mốc thời gian chỉ là số minh họa. Từ payload này, ứng dụng chưa thể suy ra người dùng được sửa mọi khóa học, có MFA hay có quyền trong tenant khác.

## 3. Role, scope, group và permission khác nhau thế nào?

Các khái niệm có thể liên hệ qua chính sách, nhưng không nên hoán đổi tên gọi một cách tự động:

| Khái niệm | Cách dùng trong thiết kế minh họa | Ví dụ |
|---|---|---|
| Role | Tập trách nhiệm được gán cho chủ thể trong ứng dụng | `training.instructor` |
| Scope | Phạm vi truy cập mà access token được cấp | `courses:write` |
| Group | Nhóm thành viên từ hệ thống danh tính | `department-learning` |
| Permission | Thao tác cụ thể chính sách cho phép | Sửa nội dung khóa `course-17` |

Ví dụ chính sách của API có thể yêu cầu đồng thời scope `courses:write`, role `training.instructor` và quan hệ được phân công vào khóa học. Một group phòng ban chỉ tạo role nếu có quy tắc ánh xạ đã được phê duyệt; không phải mọi thành viên phòng ban đều mặc nhiên là giảng viên.

Cách biểu diễn còn phụ thuộc sản phẩm. Với Microsoft Entra ID, `scp` biểu diễn scopes trong user token, còn `roles` có thể chứa role được gán cho người dùng hoặc application permission trong token của ứng dụng. Vì vậy, có `roles` không chứng minh luôn có người dùng đang tương tác. Xem [Microsoft: Access token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference).

Hợp đồng token cần nêu rõ chủ thể là người hay workload, role được gán cho đối tượng nào và API phải áp dụng loại chính sách nào. Không dùng một role dành cho tài khoản dịch vụ để suy ra người dùng đã đồng ý hay đã thực hiện MFA.

## 4. Xác minh token trước khi sử dụng role

Với JWT access token, việc base64url-decode payload chỉ giúp đọc dữ liệu. Quyết định quyền cần dựa trên token đã được xác minh với thuật toán, khóa, issuer, audience, thời hạn và quy tắc loại token phù hợp. [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html) nhấn mạnh xác minh mật mã, issuer/audience và chống nhầm lẫn giữa các loại JWT.

Một trình tự xử lý đề xuất:

1. Xác định cơ chế nhận access token được API hỗ trợ.
2. Xác minh token theo cấu hình tin cậy; không để token tự mở rộng danh sách issuer hay khóa được tin.
3. Kiểm tra schema role claim theo hợp đồng của issuer và API đích.
4. Ánh xạ những role được nhận biết sang authority hoặc permission nội bộ.
5. Áp dụng chính sách cho thao tác, tài nguyên và tenant đang được truy cập.

Nếu client sửa payload từ `training.learner` thành `training.tenant-admin`, chữ ký của token ban đầu không còn bảo vệ payload đã sửa. API phải từ chối token bị can thiệp, thay vì tin dữ liệu do frontend giải mã rồi gửi lại trong một header tự tạo.

Tương tự, một ID token có role không mặc nhiên là access token hợp lệ cho API. Phải kiểm tra đúng mục đích và hợp đồng của token được nhận; không dùng việc “cũng có roles” để bỏ qua các bước đó.

## 5. Ánh xạ role sang quyền một cách có kiểm soát

Phần sau là thiết kế minh họa cho API đào tạo, không phải thuật toán bắt buộc của giao thức.

Một bảng ánh xạ nội bộ có thể là:

| Role từ kết nối đã xác minh | Authority nội bộ | Điều kiện bổ sung |
|---|---|---|
| `training.instructor` | `COURSE_EDIT_ASSIGNED` | Chủ thể được phân công vào khóa học |
| `training.reviewer` | `COURSE_REVIEW` | Không duyệt bản nội dung do chính mình tạo |
| `training.tenant-admin` | `TENANT_USER_MANAGE` | Tenant đích thuộc phạm vi assignment |

Mã giả cho yêu cầu sửa khóa học:

```text
principal = verifyAccessToken(request.token)
authorities = mapRecognizedRoles(principal, trustedConnection)

require principal.hasScope("courses:write")
require authorities.contains("COURSE_EDIT_ASSIGNED")
require principal.tenantId == course.tenantId
require assignments.isInstructorOf(principal.subjectId, course.id)

updateCourse(course, requestedChanges)
```

Các điều kiện trên được chọn cho tình huống cụ thể. Không có quy tắc chung rằng mọi endpoint luôn phải kiểm tra cả role lẫn scope; mỗi API cần công bố chính sách phù hợp với mô hình token và nghiệp vụ của mình.

Khi ánh xạ, nên quy định rõ:

- Role nào được chấp nhận từ từng kết nối và trong phạm vi tài nguyên nào.
- Kiểu dữ liệu, tên claim, phân biệt hoa thường và cách xử lý dữ liệu sai schema.
- Role không được nhận biết không sinh thêm quyền.
- Thiếu role không thỏa mãn chính sách yêu cầu role đó; không tự thay bằng role mặc định có đặc quyền.
- Role hierarchy và quy tắc xung đột, nếu có, phải được định nghĩa rõ; không suy từ thứ tự phần tử trong mảng.

Nếu một endpoint chỉ yêu cầu xác thực và cho người dùng xem hồ sơ của chính mình, việc không có role claim có thể vẫn phù hợp với hợp đồng. Phải phân biệt token không hợp lệ với token hợp lệ nhưng thiếu quyền cho thao tác đang yêu cầu.

## 6. Phạm vi ứng dụng và tenant

Giả sử một người là quản trị viên của tenant A nhưng chỉ là học viên ở tenant B. Một token chỉ ghi `roles: ["admin"]` mà không có hợp đồng phạm vi rõ ràng dễ dẫn tới việc cấp quyền quá rộng.

Thiết kế có thể cấp token cho ngữ cảnh tenant đang hoạt động, hoặc để API tra assignment theo tenant. Dù chọn cách nào, cần ràng buộc role với tài nguyên và miền quản trị phù hợp.

Ví dụ yêu cầu:

```http
DELETE /tenants/tenant-b/users/user-99 HTTP/1.1
Host: api.training.example.org
Authorization: Bearer <access-token>
```

Trong chính sách minh họa, nếu token xác lập role quản trị cho tenant A, đổi đường dẫn thành tenant B không làm assignment tự chuyển theo. API phải kiểm tra tenant của tài nguyên và phạm vi quyền, thay vì chỉ nhìn `hasRole("admin")`.

Claim `tenant_id` cũng cần có ngữ nghĩa được tin cậy: ai được phát hành nó, nó đại diện tenant nào và quan hệ với role ra sao. Một claim đã ký không làm mọi cách diễn giải tùy ý của ứng dụng trở nên đúng.

Không tự động gộp vai trò cùng tên từ nhà cung cấp bên ngoài với vai trò đặc quyền nội bộ. Ví dụ, role `admin` do đối tác dùng để quản lý hồ sơ của họ không nên được ánh xạ thẳng thành quản trị viên nền tảng đào tạo.

## 7. Liên hệ với Spring Security

Trong Spring Security Resource Server, việc ánh xạ claims thành `GrantedAuthority` là bước có thể cấu hình. Tài liệu hướng dẫn `JwtGrantedAuthoritiesConverter` để chọn claim và tiền tố authority, cũng như kết hợp converter khi cần đọc nhiều nguồn. Xem [Spring Security: JWT, cấu hình authority](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

Với một hợp đồng minh họa, có thể giữ hai nhóm tên riêng:

```text
scope "courses:write"        -> SCOPE_courses:write
role  "training.instructor"  -> ROLE_training.instructor
```

Ứng dụng cần cấu hình ánh xạ tương ứng. Không giả định chỉ cần token có claim `roles` là framework tự hiểu đúng mọi role của sản phẩm phát hành token.

Sự nhất quán giữa authority thực tế và điều kiện kiểm tra rất quan trọng. Nếu converter tạo `ROLE_training.instructor` nhưng chính sách lại tìm `ROLE_INSTRUCTOR`, người dùng có thể bị từ chối dù token hợp lệ. Chiều ngược lại, converter tự biến mọi chuỗi từ claim tùy ý thành authority quản trị có thể mở quyền quá rộng.

Ánh xạ authority không thay thế bước xác minh JWT, và điều kiện role ở endpoint không thay thế kiểm tra quyền trên đối tượng nghiệp vụ.

## 8. Role trong token là thông tin tại một thời điểm

Giả sử AS phát hành JWT có role giảng viên lúc 09:00. Đến 09:05, người dùng bị gỡ role. Nếu API chỉ xác minh JWT cục bộ và không có cơ chế kiểm tra thay đổi trạng thái, token đã phát hành vẫn có thể được chấp nhận đến khi hết hạn.

Một timeline minh họa:

| Thời điểm | Trạng thái |
|---|---|
| 09:00 | Token T1 được cấp với role giảng viên |
| 09:05 | Assignment giảng viên bị gỡ ở nguồn quản lý |
| 09:06 | API chỉ nhìn T1 có thể vẫn thấy role cũ |
| Khi T1 hết hiệu lực hoặc cơ chế thu hồi được áp dụng | Quyền theo T1 không còn được chấp nhận |

Những lựa chọn thiết kế cần đánh giá gồm token thời hạn ngắn, introspection phản ánh trạng thái hiện tại, kiểm tra assignment trực tuyến cho thao tác nhạy cảm, hoặc cơ chế vô hiệu hóa token/phiên được hệ thống hỗ trợ. Mỗi lựa chọn có đánh đổi về tải, độ trễ và thời gian thu hồi thực tế.

Không mặc định introspection luôn tính lại role từ nguồn mới nhất; điều đó còn phụ thuộc cách AS triển khai. Nếu kết quả được cache, cần tính cả thời gian cache vào mục tiêu thu hồi quyền.

Với offboarding, quy trình cần bao quát assignment, token, khả năng cấp token tiếp theo và phiên ứng dụng. Chỉ ẩn nút trên giao diện hoặc gỡ role ở một bảng mà API không đọc chưa đủ để chứng minh quyền đã bị thu hồi tại mọi điểm thực thi.

## 9. Role đặc quyền cần điều kiện bổ sung

Role quản trị là một đầu vào của chính sách, không phải bằng chứng về độ mới của xác thực hay mức đảm bảo danh tính. Trong một thiết kế quản trị có kiểm soát, ứng dụng có thể yêu cầu thêm:

- Assignment có thời hạn và được phê duyệt cho đúng tenant.
- Xác thực tăng cường theo chính sách của tác vụ nhạy cảm.
- Tách người yêu cầu với người phê duyệt.
- Kiểm tra trạng thái trực tuyến trước khi thay đổi quyền người khác.
- Nhật ký quyết định gồm chủ thể, kết nối tin cậy, tenant, thao tác, tài nguyên, chính sách và kết quả.

Không suy ra MFA chỉ từ tên role hoặc một claim tùy ý do client gửi. Nếu chính sách cần mức đảm bảo xác thực, phải dùng tín hiệu được xác minh và cách diễn giải đã thống nhất với bên xác thực.

Hạn chế đưa quá nhiều role nội bộ vào token. Chỉ phát hành thông tin cần cho bên nhận, tránh lộ cấu trúc tổ chức hoặc các assignment không liên quan. Nhật ký vận hành cũng không nên lưu toàn bộ access token chỉ để chứng minh đã thấy role nào.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả có thể xảy ra | Hướng thiết kế phù hợp |
|---|---|---|
| Decode JWT rồi tin roles ngay | Chấp nhận payload giả hoặc token sai ngữ cảnh | Xác minh token trước khi ánh xạ |
| Coi mọi `admin` là cùng một quyền | Role ở ứng dụng/issuer khác thành quyền nội bộ | Ánh xạ theo kết nối và tài nguyên đích |
| Kiểm tra role mà bỏ tenant | Truy cập chéo miền quản trị | Ràng buộc assignment với tenant/tài nguyên |
| Tự động gộp group thành role | Cấp quyền từ quan hệ thành viên không phù hợp | Dùng quy tắc ánh xạ được kiểm soát |
| Chỉ kiểm tra ở giao diện | Gọi trực tiếp API để vượt hạn chế | Thực thi tại mọi điểm truy cập phía máy chủ |
| Gỡ role nhưng không xét token cũ | Đặc quyền tồn tại lâu hơn dự kiến | Đo và thiết kế thời gian thu hồi thực tế |
| Có role thì bỏ qua quyền trên đối tượng | Giảng viên sửa khóa không được phân công | Kết hợp RBAC với điều kiện tài nguyên |

## 11. Tự kiểm tra bằng tình huống

**Người dùng có role giảng viên, scope ghi khóa học, nhưng không được phân công vào khóa cần sửa. Có cho phép không?**

Theo chính sách minh họa, không. Role và scope thỏa điều kiện ở cấp ứng dụng nhưng chưa thỏa quan hệ với khóa học cụ thể.

**Một token hợp lệ do issuer được tin cậy cấp cho API khác chứa role `admin`. Có dùng tại API đào tạo không?**

Không thể cấp quyền chỉ dựa vào role. Token phải dành cho API này và thỏa đúng hợp đồng xác minh, ánh xạ và chính sách của nó.

**Token có `roles` nhưng không có người dùng tương tác có bất thường không?**

Không nhất thiết. Một workload có thể được cấp application role hoặc permission theo mô hình của nhà cung cấp. API cần phân biệt chính sách dành cho workload với thao tác yêu cầu ngữ cảnh người dùng.

**Một role bị gỡ lúc 09:05 nhưng token cũ còn thời hạn. Bằng chứng nào cho thấy quyền đã hết?**

Cần kiểm tra hành vi tại điểm thực thi: token cũ có bị từ chối cho thao tác đó không, nhờ cơ chế nào và sau bao lâu. Trạng thái assignment mới tại nguồn quản lý không tự chứng minh mọi API đã áp dụng thay đổi.

Một role claim hữu ích khi nó có nguồn tin cậy, phạm vi rõ ràng và quy tắc ánh xạ nhất quán. Quyết định cuối cùng vẫn cần gắn chủ thể với đúng thao tác, đúng tài nguyên, đúng tenant và trạng thái quyền hiện tại theo chính sách hệ thống.
