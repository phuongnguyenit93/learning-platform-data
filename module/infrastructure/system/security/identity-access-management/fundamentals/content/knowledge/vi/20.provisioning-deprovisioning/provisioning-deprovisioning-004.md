# Manual provisioning

## 1. Manual provisioning là gì?

**Manual provisioning** là việc một người được ủy quyền trực tiếp thực hiện những thao tác cấp phát danh tính hoặc quyền truy cập theo một yêu cầu đã được xác minh.

Thao tác có thể diễn ra trên cổng quản trị, công cụ dòng lệnh hoặc API quản trị. Điểm đặc trưng là con người còn chịu trách nhiệm chọn đối tượng, diễn giải yêu cầu, quyết định hoặc thực hiện các bước của từng lượt cấp phát.

Ví dụ:

~~~text
Một quản trị viên nhận yêu cầu cho cộng tác viên vào cổng báo cáo.
Quản trị viên kiểm tra danh tính và phê duyệt.
Quản trị viên tạo account ứng dụng nếu cần.
Quản trị viên thêm membership tenant và gán quyền đã duyệt.
Người kiểm tra xác nhận quyền thực tế rồi hoàn tất yêu cầu.
~~~

Cấp phát thủ công vẫn có thể dùng phần mềm để sinh ID, kiểm tra dữ liệu, ghi audit hoặc hỗ trợ một số bước. Mức độ thủ công được hiểu theo cách quy trình vận hành, không phải theo việc có dùng máy tính hay không.

Trong IAM, manual provisioning cần liên kết với xác thực, directory, membership, nhóm, RBAC/ABAC, SSO và vòng đời thu hồi. Tạo account là một phần của công việc; kết quả cần là **đúng chủ thể có đúng quyền, trong đúng phạm vi và thời hạn**.

Sau bài này, người học có thể:

- Phân biệt tạo tài khoản với cấp quyền và chuẩn bị credential.
- Xác định người yêu cầu, người thụ hưởng, người phê duyệt và người thực hiện.
- Viết một yêu cầu cấp phát có phạm vi đủ rõ để thực thi.
- Thực hiện runbook có kiểm tra trước, đọc lại trạng thái và xử lý lỗi.
- Kiểm soát việc thay đổi yêu cầu sau phê duyệt.
- Chuẩn bị thời hạn, rà soát và thu hồi quyền sau khi cấp.

## 2. Cấp phát những đối tượng nào?

Một yêu cầu “tạo user” có thể bao gồm nhiều đối tượng khác nhau:

| Đối tượng | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Directory account | Tài khoản nội bộ `U-81` | Đã tồn tại chưa, thuộc đúng người không? |
| Application account | Hồ sơ cục bộ trong cổng báo cáo | Có cần tạo riêng hay ứng dụng dùng liên kết SSO? |
| Tenant membership | U-81 tham gia T-A | Trạng thái và phạm vi membership là gì? |
| Role hoặc grant | `REPORT_VIEWER` | Quyền thực tế gồm hành động và tài nguyên nào? |
| Group membership | Nhóm được policy dùng để cấp quyền | Nhóm có các quyền kế thừa nào? |
| License/entitlement sử dụng | Được dùng một tính năng của sản phẩm | Có thực sự cần và có phù hợp phạm vi không? |
| Credential hoặc liên kết đăng nhập | Phương thức đăng nhập được phép | Ai thiết lập, bàn giao và xác minh? |
| Thời hạn truy cập | Grant hết hiệu lực vào một thời điểm | Cơ chế nào thực thi hoặc theo dõi việc thu hồi? |

Có account trong directory không tự đồng nghĩa có membership trong mọi tenant. Có license cũng không tự chứng minh người dùng được đọc mọi dữ liệu.

Ngược lại, thêm một người vào nhóm có thể trao nhiều quyền qua quan hệ kế thừa. Một thao tác quản trị nhìn đơn giản có thể tác động đến nhiều ứng dụng.

Vì vậy, yêu cầu phải mô tả **trạng thái đích cần đạt**, không chỉ tên một nút cần bấm.

## 3. Một tình huống xuyên suốt

Bài dùng một tổ chức giả định cần cấp quyền cho cộng tác viên trong 14 ngày. Các quy tắc dưới đây là chính sách của ví dụ, không phải yêu cầu thời gian áp dụng cho mọi doanh nghiệp.

~~~text
Người thụ hưởng:
    Directory user U-81 đã được xác minh.
    Danh tính đăng nhập được liên kết qua IdP đã cấu hình.

Ứng dụng đích:
    reports-portal

Tenant:
    T-A

Trạng thái mong muốn:
    Có account ứng dụng nếu hệ thống yêu cầu.
    Có membership hợp lệ trong T-A.
    Có REPORT_VIEWER chỉ cho R-100 và R-101.

Không thuộc phạm vi yêu cầu:
    Xuất dữ liệu.
    Sửa báo cáo.
    Mời thành viên.
    Quản trị tenant.

Thời hạn:
    Từ 2026-11-27 08:00 +07:00
    Đến trước 2026-12-11 08:00 +07:00

Chủ sở hữu nhu cầu:
    Sponsor U-10

Phê duyệt:
    Người có thẩm quyền trên ứng dụng và phạm vi tài nguyên.

Thực hiện:
    Quản trị viên được quyền cấp đúng loại truy cập đó.
~~~

Các mốc ngày giờ chỉ phục vụ tình huống học tập.

Nếu ứng dụng chỉ hỗ trợ `REPORT_VIEWER` cho toàn bộ tenant mà không giới hạn được hai báo cáo, trạng thái đích chưa thể được đáp ứng bằng role đó. Quản trị viên cần làm rõ hoặc thay đổi phương án qua quy trình phù hợp; không tự cấp toàn tenant rồi ghi “đã xong”.

Tương tự, nếu việc thêm vào một group còn cho phép xuất dữ liệu, group đó không phù hợp với yêu cầu đã mô tả dù tên group có chữ “viewer”.

## 4. Trách nhiệm và phạm vi thẩm quyền

### 4.1. Các vai trò trong quy trình

| Vai trò | Trách nhiệm trong ví dụ |
| --- | --- |
| Requester — người yêu cầu | Gửi nhu cầu và dữ liệu định vị cần thiết |
| Beneficiary — người thụ hưởng | Tài khoản nhận quyền |
| Sponsor — người bảo trợ nhu cầu | Xác nhận lý do, thời hạn và theo dõi khi nhu cầu thay đổi |
| Approver — người phê duyệt | Cho phép một thay đổi cụ thể trong phạm vi mình quản lý |
| Executor — người thực hiện | Áp dụng thay đổi bằng quyền quản trị phù hợp |
| Verifier — người xác minh | Đối chiếu trạng thái thực tế với yêu cầu đã duyệt |
| Account/resource owner | Chịu trách nhiệm duy trì hoặc kết thúc quyền theo chính sách |

Một người có thể giữ nhiều vai trò nếu chính sách cho phép và rủi ro phù hợp. Với truy cập nhạy cảm, tổ chức có thể yêu cầu tách người phê duyệt và người thực hiện.

NIST SP 800-53 Rev. 5, điều khiển AC-2, đề cập việc xác định loại tài khoản, người quản lý, quyền được cấp, phê duyệt và quản lý vòng đời theo chính sách của tổ chức. Đây là một khung tham chiếu để thiết kế quy trình rõ trách nhiệm. [Nguồn: NIST SP 800-53 Rev. 5 — AC-2](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf).

### 4.2. Chức danh không tự quyết định mọi quyền phê duyệt

Một trưởng nhóm có thể xác nhận nhu cầu công việc nhưng không nhất thiết được phê duyệt quyền quản trị nền tảng hoặc dữ liệu của tenant khác.

Cần tách:

~~~text
Người này có nhu cầu hợp lệ.
Người này được phép nhận quyền cụ thể.
Người phê duyệt có thẩm quyền trên quyền/phạm vi đó.
Người thực hiện được phép gán quyền/phạm vi đó.
~~~

Cả bốn điều kiện có thể cần được kiểm tra theo policy.

Một người được phép tạo account cũng không mặc nhiên được gán role đặc quyền. Ví dụ, tài liệu Microsoft Entra phân biệt quyền cần cho tạo user, mời guest và gán vai trò quản trị. [Nguồn: Microsoft — Create, invite, and delete users](https://learn.microsoft.com/en-us/entra/fundamentals/how-to-create-delete-users).

### 4.3. Kiểm soát việc tự nâng quyền

Với tình huống giả định nhạy cảm, tổ chức yêu cầu người phê duyệt không đồng thời là người thụ hưởng hoặc người thực hiện.

Quy tắc này phải được kiểm tra trong workflow, không chỉ ghi ở đầu runbook. Nếu một cổng quản trị cho phép sửa approver thành chính người đang thao tác sau khi yêu cầu đã duyệt, việc tách trách nhiệm chỉ còn trên giấy.

Cơ chế khẩn cấp, nếu có, cần phạm vi và đường kiểm tra riêng. Không dùng từ “gấp” để tự biến một yêu cầu thông thường thành quyền bỏ mọi kiểm soát.

## 5. Một yêu cầu cấp phát có thể thực thi

### 5.1. Định danh đúng người và đúng môi trường

Một yêu cầu nên định vị được:

~~~text
Request ID và revision.
Người yêu cầu.
Người thụ hưởng bằng định danh ổn định.
Nguồn xác nhận danh tính/người bảo trợ.
Ứng dụng và môi trường đích.
Tenant hoặc phạm vi quản trị.
Role/nhóm/quyền cần cấp.
Phạm vi tài nguyên.
Thời điểm bắt đầu và kết thúc.
Lý do nghiệp vụ.
Người phê duyệt và phạm vi phê duyệt.
Người chịu trách nhiệm rà soát/thu hồi.
~~~

Không chỉ ghi “cấp giống anh Bình” hoặc “cho vào hệ thống như mọi người”. Hai người cùng chức danh có thể có quyền khác nhau do công việc, tenant hoặc ngoại lệ lịch sử.

### 5.2. Mẫu ticket minh họa

~~~yaml
requestId: REQ-204
revision: 3
environment: production
targetApplication: reports-portal

beneficiary:
  directoryUserId: U-81
  identityReference: verified-idp-link-81

scope:
  tenantId: T-A
  roleId: REPORT_VIEWER
  resourceIds:
    - R-100
    - R-101
  roleCatalogRevision: reports-policy-7

validFrom: "2026-11-27T08:00:00+07:00"
validUntil: "2026-12-11T08:00:00+07:00"

businessReason: "Đối chiếu báo cáo trong đợt hợp tác đã được xác nhận"
sponsorId: U-10
approverId: U-20
reviewOwnerId: U-10

acceptance:
  - "Đọc được R-100 và R-101 trong thời hạn"
  - "Không được xuất hoặc sửa dữ liệu"
  - "Không được truy cập tenant T-B"
~~~

Schema này do bài học tự định nghĩa, không phải một định dạng ticket chuẩn. Ticket không chứa password, activation token hoặc secret MFA.

`roleCatalogRevision` giúp xác định ý nghĩa role được dùng khi phê duyệt. Nếu role thay đổi quyền trong lúc ticket chờ thực hiện, cần xem lại tác động trước khi áp dụng.

### 5.3. Phê duyệt phải gắn với nội dung cụ thể

Một phê duyệt cho revision 3 không tự áp dụng cho revision 4 có thêm quyền export.

Nội dung cần được ràng buộc gồm:

~~~text
Người thụ hưởng.
Hệ thống/môi trường.
Tenant.
Role hoặc grant.
Tài nguyên.
Thời hạn.
Phiên bản policy/quyền có liên quan.
~~~

Hệ thống có thể dùng snapshot có version hoặc cơ chế ràng buộc tương đương. Một dòng “approved” không có đối tượng và phạm vi rõ ràng không đủ để biết thay đổi nào được cho phép.

Nếu yêu cầu đổi sau phê duyệt, cần đánh giá lại theo quy trình. Không sửa ticket để khớp quyền đã cấp rồi coi đó là bằng chứng phê duyệt trước.

## 6. Kiểm tra trước khi thao tác

### 6.1. Xác nhận trạng thái hiện tại

Trước khi tạo mới, cần biết:

1. Account directory đã tồn tại và còn phù hợp không?
2. Account ứng dụng đã tồn tại chưa?
3. Liên kết danh tính có đúng không?
4. Membership tenant hiện tại là gì?
5. Người dùng đang có những quyền nào liên quan?
6. Role/group dự định gán thực sự trao những quyền nào?
7. Có ràng buộc xung đột quyền hoặc giới hạn tài khoản không?
8. Yêu cầu và phê duyệt còn hiệu lực không?

Tra account theo định danh nguồn/ID ổn định phù hợp. Email và tên hiển thị có thể hỗ trợ tìm kiếm nhưng không tự đủ để kết luận hai account là một.

Nếu có account gần giống hoặc mapping mâu thuẫn, dừng phần cấp phát phụ thuộc vào kết luận đó để xử lý. Tạo thêm account cho nhanh có thể làm phân tán quyền và khó thu hồi.

### 6.2. Xác minh quyền của người thực hiện

Quản trị viên cần dùng danh tính quản trị được phép, trong đúng ứng dụng, môi trường và tenant.

Không dùng account quản trị chung nếu hệ thống cần truy vết theo từng người. Không mượn credential của người thụ hưởng để hoàn thành thao tác.

Phiên quản trị có thể cần xác thực gần đây hoặc MFA theo chính sách. Việc được đăng nhập vào console chưa chứng minh người đó được gán mọi role có thể nhìn thấy.

### 6.3. Biết rõ công cụ sẽ tác động gì

Trước khi bấm lưu hoặc chạy lệnh quản trị, cần xác định:

~~~text
Đang thao tác production hay môi trường thử nghiệm?
Tenant đích đã đúng chưa?
Thay đổi là thêm một grant hay thay toàn bộ danh sách?
Nhóm được chọn có quyền kế thừa nào?
Công cụ có gửi lời mời hoặc thông báo ngay không?
Thời hạn được lưu để thực thi hay chỉ là ghi chú?
Có bước nào làm account hoạt động trước khi đủ điều kiện không?
~~~

Một form “save groups” có thể thay cả tập group thay vì chỉ thêm một group. Không suy ra ngữ nghĩa từ nhãn nút nếu công cụ có tài liệu hoặc preview cho biết khác.

## 7. Runbook cấp phát thủ công

### 7.1. Luồng tổng thể

~~~mermaid
flowchart TD
    A[Nhận yêu cầu có phạm vi] --> B[Xác minh danh tính và trạng thái hiện tại]
    B --> C[Phê duyệt đúng nội dung và thẩm quyền]
    C --> D[Thực hiện thay đổi đã được phép]
    D --> E[Đọc lại trạng thái tại hệ thống đích]
    E --> F[Hoàn tất điều kiện kích hoạt và bàn giao]
    F --> G[Xác minh quyền hiệu lực và giới hạn]
    G --> H[Ghi bằng chứng, chủ sở hữu và hạn thu hồi]
    H --> I[Đóng yêu cầu theo điều kiện nghiệm thu]
~~~

Nếu một bước thất bại, trạng thái cần phản ánh phần đã làm và phần chưa làm. Không chuyển thẳng sang “completed” vì một account đã xuất hiện trong danh sách.

### 7.2. Các bước thực hiện

| Bước | Thao tác trong ví dụ | Bằng chứng cần giữ |
| --- | --- | --- |
| 1 | Mở ticket đúng revision đã duyệt | Request ID, revision, người duyệt |
| 2 | Xác nhận account U-81 và ứng dụng đích | ID nguồn và ID đích liên quan |
| 3 | Tạo account ứng dụng nếu thật sự chưa có | ID account do hệ thống cấp |
| 4 | Thiết lập liên kết SSO hoặc phương thức đăng nhập được phép | Tham chiếu liên kết, không lưu secret |
| 5 | Thêm membership T-A theo policy | Membership ID/trạng thái |
| 6 | Cấp role/phạm vi R-100, R-101 | Role, resource scope, thời hạn |
| 7 | Áp dụng điều kiện truy cập cần thiết | Trạng thái policy phù hợp |
| 8 | Đọc lại dữ liệu đích | Trạng thái lưu thực tế |
| 9 | Bàn giao luồng kích hoạt cho đúng người | Kết quả giao nhận không chứa secret |
| 10 | Xác minh quyền hiệu lực và giới hạn | Kết quả kiểm tra theo acceptance |
| 11 | Ghi owner và cách kết thúc quyền | Chủ sở hữu, thời hạn, cơ chế thu hồi |
| 12 | Đóng ticket khi đủ điều kiện | Kết quả và phần tồn đọng nếu có |

Thứ tự cụ thể phụ thuộc hệ thống đích. Ví dụ, một IdP có thể cần user tồn tại trước khi gán ứng dụng; một ứng dụng khác tạo account khi đăng nhập lần đầu.

Nếu có trạng thái `PENDING_ACTIVATION`, cần phân biệt việc chuẩn bị xong với việc người dùng đã được phép sử dụng. Không kích hoạt sớm hơn `validFrom` nếu trạng thái quyền yêu cầu chờ đến thời điểm đó.

### 7.3. Ghi lại trạng thái công việc và trạng thái account riêng

Có thể dùng trạng thái yêu cầu như:

~~~text
SUBMITTED
APPROVED
APPLYING
WAITING_ACTIVATION
VERIFYING
COMPLETED
NEEDS_REVIEW
CANCELLED
~~~

Account có thể mang trạng thái khác như `PENDING`, `ACTIVE` hoặc `SUSPENDED`.

Một ticket `APPROVED` chưa có nghĩa account đã active. Account active cũng chưa chứng minh ticket đủ điều kiện nghiệm thu. Hai loại trạng thái phục vụ hai mục đích khác nhau.

## 8. Cấp quyền tối thiểu và kiểm tra quyền hiệu lực

OWASP khuyến nghị quyền tối thiểu, từ chối mặc định và kiểm tra quyền phù hợp cho các yêu cầu truy cập. Trong cấp phát, điều này hỗ trợ việc mô tả rõ quyền nào được phép cấp thay vì cho role rộng làm mặc định. [Nguồn: OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Với ví dụ REQ-204, cần đối chiếu cả quyền trực tiếp và quyền được thừa hưởng:

~~~text
Role trực tiếp.
Group membership.
Nhóm lồng nhau nếu hệ thống hỗ trợ.
Grant ở tenant hoặc ứng dụng.
Quan hệ sở hữu hoặc chia sẻ.
Các rule ABAC có thể mở rộng/giới hạn quyền.
~~~

“Chỉ thêm viewer” có thể vẫn làm người dùng có export nếu họ đang thuộc một group khác. Kết quả cần kiểm tra là quyền hiệu lực theo policy, không chỉ danh sách thao tác vừa thực hiện.

Không tự xóa các quyền có sẵn ngoài phạm vi yêu cầu để ép kết quả giống ticket. Nếu phát hiện quyền dư hoặc xung đột, cần xác định nguồn, owner và quy trình xử lý phù hợp.

Sao chép toàn bộ quyền của một đồng nghiệp dễ mang theo grant tạm thời hoặc ngoại lệ không còn cần thiết. Nếu dùng mẫu quyền, mẫu cần được quản lý và có ý nghĩa rõ ràng.

## 9. Chuẩn bị đăng nhập và bàn giao cho đúng người

### 9.1. Ưu tiên đúng luồng xác thực đã thiết kế

Nếu ứng dụng dùng SSO và người dùng đã có danh tính phù hợp tại IdP, việc cấp phát có thể chỉ cần account/mapping và quyền ứng dụng. Không cần tự tạo thêm password cục bộ nếu kiến trúc không yêu cầu.

Nếu cần thiết lập credential mới, dùng luồng của hệ thống quản lý xác thực và chính sách tương ứng:

~~~text
Xác định đúng người nhận.
Cấp lời mời hoặc phương thức kích hoạt được phép.
Người nhận hoàn thành bước xác minh và thiết lập cần thiết.
Áp dụng yêu cầu MFA hoặc điều kiện truy cập.
Ghi nhận kết quả kích hoạt theo hợp đồng.
~~~

Có link kích hoạt không đồng nghĩa đã chứng minh đầy đủ danh tính của người nhận theo mọi mức bảo đảm. Luồng phải phù hợp với mức tin cậy mà ứng dụng cần.

### 9.2. Không đưa secret vào ticket hoặc bằng chứng thông thường

Ticket có thể được nhiều người đọc, gửi qua email hoặc lưu lâu. Không nên chứa:

- Password ban đầu hay password hiện tại.
- Token kích hoạt hoặc reset còn dùng được.
- Seed MFA hoặc recovery code.
- Access token, refresh token hoặc secret API.
- Ảnh chụp chứa các thông tin trên.

Nếu hệ thống yêu cầu password tạm, dùng cơ chế sinh và bàn giao được phép, áp dụng điều kiện sử dụng/đổi theo policy thực sự hỗ trợ. Không đặt một password chung cho cả đợt onboarding để dễ ghi nhớ.

Không yêu cầu người dùng gửi lại password để chứng minh rằng đã nhận account.

### 9.3. Luồng đặt hoặc đặt lại password

Nếu thiết kế bàn giao có sử dụng reset token, OWASP hướng dẫn token reset cần được sinh an toàn, lưu an toàn, dùng một lần và hết hạn sau khoảng thời gian phù hợp. [Nguồn: OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Cần biết token ràng buộc với account nào, endpoint nào chấp nhận và kết quả sau khi dùng. Gửi lại thông báo không được làm quản trị viên vô tình chuyển credential sang một email khác chưa được xác minh.

Đổi người nhận, thêm phương thức đăng nhập hoặc khôi phục account là các thay đổi danh tính nhạy cảm. Không thực hiện chỉ vì có người trả lời vào chuỗi email của ticket.

### 9.4. Bàn giao khác với xác minh quyền

Một email thông báo đã gửi không chứng minh người dùng đã hoàn tất activation. Activation thành công cũng chưa chứng minh role và phạm vi tài nguyên đúng.

Nếu chưa đủ điều kiện kích hoạt, dùng trạng thái chờ phù hợp. Ghi rõ ai cần làm bước tiếp theo và khi nào phải rà soát lại; không đóng yêu cầu hoàn chỉnh theo một điều kiện chưa xảy ra.

## 10. Guard Java cho phê duyệt gắn với đúng nội dung

### 10.1. Mục tiêu của helper

Một cổng quản trị có thể hỗ trợ manual provisioning bằng cách ngăn dùng phê duyệt cũ cho một kế hoạch đã sửa.

Ví dụ Java 17 sau kiểm tra:

~~~text
Nội dung thực hiện trùng snapshot đã duyệt.
Phê duyệt chưa hết hạn.
Grant chưa hết thời gian nghiệp vụ.
Role catalog vẫn đúng revision được duyệt.
Người duyệt không là beneficiary hoặc executor
theo quy tắc tách trách nhiệm của tình huống minh họa.
~~~

`StoredApproval` phải được đọc từ kho phê duyệt có thẩm quyền. Không tạo nó từ JSON “approved=true” do người gọi tự gửi.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

final class ManualProvisioningGuard {
    record AccessPlan(
        UUID requestId,
        long revision,
        UUID beneficiaryId,
        String applicationId,
        String environment,
        String tenantId,
        String roleId,
        Set<String> resourceIds,
        Instant validFrom,
        Instant validUntil,
        String roleCatalogRevision
    ) {
        AccessPlan {
            Objects.requireNonNull(requestId);
            Objects.requireNonNull(beneficiaryId);
            Objects.requireNonNull(applicationId);
            Objects.requireNonNull(environment);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(roleId);
            Objects.requireNonNull(validFrom);
            Objects.requireNonNull(validUntil);
            Objects.requireNonNull(roleCatalogRevision);
            resourceIds = Set.copyOf(resourceIds);

            if (revision < 1 || !validUntil.isAfter(validFrom)) {
                throw new IllegalArgumentException(
                    "Invalid access plan"
                );
            }
        }
    }

    record StoredApproval(
        UUID approverId,
        AccessPlan approvedSnapshot,
        Instant expiresAt
    ) {
        StoredApproval {
            Objects.requireNonNull(approverId);
            Objects.requireNonNull(approvedSnapshot);
            Objects.requireNonNull(expiresAt);
        }
    }

    static void assertPlanApproved(
        AccessPlan currentPlan,
        StoredApproval approval,
        UUID executorId,
        String currentRoleCatalogRevision,
        Instant now
    ) {
        Objects.requireNonNull(currentPlan);
        Objects.requireNonNull(approval);
        Objects.requireNonNull(executorId);
        Objects.requireNonNull(currentRoleCatalogRevision);
        Objects.requireNonNull(now);

        if (!currentPlan.equals(approval.approvedSnapshot())) {
            throw new IllegalStateException(
                "Plan differs from approved snapshot"
            );
        }

        if (!now.isBefore(approval.expiresAt())
                || !now.isBefore(currentPlan.validUntil())) {
            throw new IllegalStateException(
                "Approval or access interval has expired"
            );
        }

        if (!currentPlan.roleCatalogRevision()
                .equals(currentRoleCatalogRevision)) {
            throw new IllegalStateException(
                "Role catalog requires review"
            );
        }

        if (approval.approverId()
                    .equals(currentPlan.beneficiaryId())
                || approval.approverId().equals(executorId)) {
            throw new IllegalStateException(
                "Separation-of-duties rule violated"
            );
        }
    }
}
~~~

### 10.2. Các giới hạn cần hiểu đúng

Helper không tự xác thực executor, không kiểm tra toàn bộ thẩm quyền approver và không cấp quyền tại hệ thống đích. Những kiểm tra đó thuộc workflow và policy tương ứng.

`currentRoleCatalogRevision` phải được server lấy từ cấu hình/quyền hiện tại đáng tin cậy, không nhận một chuỗi tùy ý của client rồi coi là bằng chứng.

Helper cho phép kiểm tra một kế hoạch có `validFrom` trong tương lai để phục vụ chuẩn bị theo quy trình. Nó không cho phép bật quyền trước thời điểm bắt đầu. Điểm kích hoạt và backend thực thi grant vẫn cần tuân theo `validFrom`.

Nếu thay đổi role catalog không ảnh hưởng quyền đang xét, tổ chức có thể có quy tắc đánh giá khác. Ví dụ chọn yêu cầu review lại khi revision thay đổi để minh họa việc kiểm soát ý nghĩa quyền.

Các record và phép so sánh chỉ giúp tránh một nhóm sai sót. Chúng không thay thế bước đối chiếu quyền hiệu lực sau khi thao tác thủ công.

## 11. Đọc lại trạng thái và xác minh kết quả

### 11.1. Phân biệt ba loại bằng chứng

| Bằng chứng | Chứng minh được gì? | Chưa chứng minh được gì? |
| --- | --- | --- |
| Ticket đã duyệt | Một thay đổi được phép theo phạm vi đã ghi | Thay đổi đã được áp dụng |
| Console báo lưu thành công | Công cụ nhận hoặc thực hiện thao tác theo ngữ nghĩa của nó | Mọi điểm thực thi đã có quyền đúng |
| Readback và kiểm tra quyền hiệu lực | Trạng thái quan sát được phù hợp acceptance tại thời điểm kiểm tra | Không cần theo dõi các thay đổi về sau |

Không dùng một ảnh chụp thông báo “success” thay cho kiểm tra account, tenant, role và thời hạn thực tế.

### 11.2. Đọc lại bằng định danh ổn định

Sau WRITE, tra lại đúng account/grant/membership được tác động:

~~~text
Target account ID.
Target application.
Tenant ID.
Membership state.
Role/group/grant ID.
Resource scope.
validFrom và validUntil.
Nguồn hoặc request tạo thay đổi nếu hệ thống hỗ trợ.
~~~

Ưu tiên ID hệ thống cấp và các trường trạng thái thay vì chỉ tên hiển thị. Tên giống nhau không đủ để biết đã sửa đúng người.

Với hệ thống đồng bộ bất đồng bộ, ghi rõ trạng thái đã lưu, trạng thái đang lan truyền và trạng thái thực sự có hiệu lực. Không coi “đã đưa vào hàng đợi” là đã hoàn tất cấp quyền.

### 11.3. Kiểm tra cả hành động được phép và giới hạn

Với REQ-204:

~~~text
Dương:
    Đọc được R-100, R-101 khi đủ điều kiện và trong thời hạn.

Âm:
    Không được sửa.
    Không được export.
    Không được truy cập tenant T-B.
    Không nhận role quản trị ngoài yêu cầu.
~~~

Có thể dùng công cụ đánh giá quyền, tài nguyên kiểm thử hoặc quy trình xác minh được phép. Không cần xuất dữ liệu khách hàng thật hoặc mượn password beneficiary chỉ để kiểm tra một quyền bị cấm.

Nếu người dùng có quyền export từ một grant khác, không đánh dấu đạt kiểm tra âm. Chuyển phần xung đột sang review và xác định nguồn quyền; không tự gỡ quyền ngoài phạm vi để làm kết quả đẹp.

### 11.4. Điều kiện đóng yêu cầu

Trong quy trình minh họa, `COMPLETED` cần có:

1. Đúng beneficiary, ứng dụng, môi trường và tenant.
2. Thay đổi thực tế phù hợp nội dung đã duyệt.
3. Các điều kiện kích hoạt cần thiết đã hoàn tất.
4. Kiểm tra quyền hiệu lực và giới hạn đạt acceptance.
5. Owner, thời hạn và cách kết thúc quyền đã được xác định.
6. Bằng chứng không chứa secret và không có lỗi tồn đọng chưa được giải quyết.

Nếu một tổ chức chia việc chuẩn bị và kích hoạt thành hai yêu cầu, mỗi yêu cầu có thể có completion gate riêng. Cần ghi rõ kết quả nào đã được nghiệm thu, tránh dùng một nhãn “done” cho mọi giai đoạn.

## 12. Lỗi từng phần, trạng thái chưa biết và khắc phục

### 12.1. Tạo account thành công nhưng cấp quyền thất bại

Ví dụ:

~~~text
Account ứng dụng đã được tạo.
Membership T-A chưa được thêm do lỗi.
Lời mời chưa gửi.
~~~

Ghi lại ID account đã tạo và phần chưa hoàn tất. Nếu chính sách cho phép trạng thái chờ không có quyền, có thể giữ account ở trạng thái đó để tiếp tục xử lý.

Không cấp một role rộng hơn chỉ để vượt lỗi của role đã duyệt. Không báo hoàn tất vì bước tạo account thành công.

### 12.2. Timeout không chứng minh thao tác thất bại

Một lệnh lưu có thể đã thành công ở server nhưng client nhận timeout. Bấm tạo lại có thể tạo trùng account, gửi nhiều lời mời hoặc thêm grant ngoài dự định.

Trước khi retry, tra trạng thái bằng request/correlation ID hoặc định danh ổn định của đối tượng. Phân biệt:

~~~text
Chưa thực hiện.
Đã thực hiện.
Đang xử lý.
Không xác định được kết quả.
~~~

Nếu công cụ hỗ trợ idempotency, dùng theo hợp đồng của nó. Không tự cho rằng mọi API quản trị đều idempotent.

### 12.3. Chỉ khắc phục phần thay đổi thuộc lượt việc này

Giả sử user đã có account và membership ở nhiều tenant. Ticket chỉ thêm một grant trong T-A.

Nếu cấp phát thất bại, không vô hiệu hóa toàn bộ user hoặc xóa account dùng chung làm cách rollback mặc định.

Cần biết:

~~~text
Đối tượng nào đã có từ trước?
Grant nào do lượt việc này tạo?
Đối tượng có đang phục vụ nhu cầu khác không?
Có thay đổi đồng thời nào từ nguồn khác không?
Quyền nào có thể thu hồi trong phạm vi khắc phục?
~~~

Ngay cả một membership cũng có thể được nhiều nhu cầu dựa vào. Việc gỡ nó cần xét ý nghĩa và nguồn cấp tương ứng, không chỉ dựa vào việc ticket vừa chạm tới membership.

### 12.4. Cấp nhầm tenant hoặc quá quyền

Đây là sai lệch cần xử lý kịp thời theo quy trình vận hành:

1. Xác định chính xác grant hoặc đối tượng bị tác động.
2. Chặn/thu hồi phần truy cập sai trong phạm vi được ủy quyền.
3. Kiểm tra tác động ở các điểm thực thi liên quan.
4. Ghi lại sự kiện và báo cho owner theo quy trình.
5. Chỉ cấp lại trạng thái đúng sau khi có đủ điều kiện.

Không sửa ticket để biến quyền cấp nhầm thành quyền đã được phê duyệt. Việc gỡ quyền sau đó không tự làm biến mất một lần đọc dữ liệu đã xảy ra.

### 12.5. Không mở quyền khi chưa đủ thông tin

Nếu không xác minh được beneficiary, không truy cập được nguồn phê duyệt hoặc role catalog đang nhập nhằng, không hoàn tất phần cấp quyền phụ thuộc vào thông tin đó.

Có thể chuyển yêu cầu sang trạng thái cần xử lý tiếp, kèm nguyên nhân và owner. Tính khả dụng của quy trình không được tạo ra một nhánh “cứ cấp admin tạm rồi sửa sau”.

## 13. Thời hạn, gia hạn và liên kết với deprovisioning

### 13.1. Ghi ngày hết hạn chưa đồng nghĩa tự hết quyền

Có hai trường hợp khác nhau:

| Cách ghi thời hạn | Ý nghĩa thực tế |
| --- | --- |
| Backend thực thi `validUntil` của grant | Grant không được dùng ngoài khoảng hiệu lực theo policy triển khai |
| Chỉ ghi ngày trong ticket hoặc ghi chú | Cần một quy trình khác thực hiện thu hồi; chưa có bảo đảm kỹ thuật tự chặn |

Nếu hệ thống đích không hỗ trợ expiry, cần chỉ định ai thu hồi, khi nào và cách phát hiện quá hạn. Không tuyên bố quyền tự hết chỉ vì ticket có trường ngày.

Nếu nhu cầu yêu cầu hết quyền chính xác tại thời điểm kết thúc nhưng công cụ không đáp ứng được, cần chọn cơ chế thực thi phù hợp hoặc xử lý yêu cầu đó trước khi cấp.

### 13.2. Gia hạn là một thay đổi quyền

Với quyền 14 ngày, sửa ngày kết thúc thành không thời hạn là thay đổi ý nghĩa grant. Không thực hiện như một chỉnh sửa hành chính vô hại.

Gia hạn cần:

~~~text
Nhu cầu còn tồn tại.
Beneficiary và phạm vi vẫn đúng.
Role hiện tại vẫn phù hợp.
Người phê duyệt có thẩm quyền.
Thời hạn mới rõ ràng.
Bằng chứng được cập nhật theo quy trình.
~~~

Không dùng một phê duyệt cũ mãi mãi cho các lần gia hạn tiếp theo.

### 13.3. Kết thúc một grant khác với đóng toàn bộ account

Trong ví dụ, khi công việc T-A kết thúc, có thể chỉ cần thu hồi role/phạm vi của đợt đó. Nếu U-81 còn nhiệm vụ khác, account và quyền khác cần được xử lý theo policy tương ứng.

Ngược lại, khi tài khoản phải kết thúc toàn cục, chỉ gỡ một role của reports-portal chưa đủ. Cần quy trình deprovisioning bao quát những ứng dụng, phiên, credential và quan hệ có liên quan.

Manual provisioning tốt để lại đủ định danh và nguồn cấp để người thực hiện deprovisioning biết cần thu hồi cái gì.

### 13.4. Rà soát cần có chủ sở hữu

Người bảo trợ hoặc owner có thể thay đổi vị trí hoặc rời tổ chức. Quy trình nên xác định cách chuyển trách nhiệm và xử lý khi không còn owner hợp lệ.

Một danh sách account “có người theo dõi” chỉ hữu ích khi người đó còn được giao trách nhiệm và có cơ chế hành động khi nhu cầu kết thúc.

## 14. Audit và hồ sơ hoàn tất

Một hồ sơ công việc có thể ghi:

~~~text
requestId và revision
beneficiaryId
application/environment/tenant
approvedRole và resourceScope
approvalReference
approverId
executorId
verifierId nếu có
targetAccountId
membershipId/grantId đã tác động
thời điểm bắt đầu/kết thúc thao tác
validFrom/validUntil
readbackResult
effectiveAccessVerification
partialFailure hoặc remediationReference
reviewOwner
outcome
~~~

Các trường cần phù hợp quy trình thật; không bắt người vận hành chép dữ liệu không phục vụ xác minh hoặc truy vết.

Bằng chứng nên cho phép trả lời:

~~~text
Ai yêu cầu và ai cho phép?
Cho tài khoản nào, ở hệ thống/tenant nào?
Quyền gì và trong bao lâu?
Ai thực hiện thao tác gì?
Hệ thống đích thực sự lưu gì?
Đã kiểm tra giới hạn nào?
Ai chịu trách nhiệm kết thúc?
~~~

Không coi comment do executor tự viết là bằng chứng duy nhất rằng trạng thái backend đúng. Khi công cụ có audit hoặc ID giao dịch, nên liên kết những bằng chứng đó.

Ảnh chụp có thể hỗ trợ ở công cụ không có xuất trạng thái tốt, nhưng cần che secret và thông tin ngoài phạm vi. Tên file ảnh hay timestamp không tự chứng minh nội dung không bị thay đổi; mức bằng chứng cần phù hợp yêu cầu của tổ chức.

## 15. Giới hạn của quy trình thủ công và cách cải thiện

### 15.1. Những điểm dễ sai khi khối lượng tăng

- Chọn nhầm tenant hoặc account tên gần giống.
- Quên một ứng dụng hoặc bước cấp/thu hồi.
- Sao chép quyền đồng nghiệp có ngoại lệ.
- Gia hạn mà không xem lại nhu cầu.
- Đóng ticket trước khi quyền có hiệu lực đúng.
- Để quyền tạm thời tồn tại lâu sau ngày kết thúc.
- Thực hiện trùng do nhiều người cùng xử lý.

Thêm nhiều thao tác chép tay không tự làm quy trình an toàn hơn. Các trường và bước kiểm tra cần có mục đích rõ ràng.

### 15.2. Tự động hóa phần lặp lại nhưng giữ rõ thẩm quyền

Có thể cải thiện dần bằng:

~~~text
Danh mục role đã quản lý.
Mẫu yêu cầu theo loại nhu cầu.
Kiểm tra bắt buộc về beneficiary/tenant/time window.
Ràng buộc phê duyệt với revision.
Công cụ hiển thị diff trước khi apply.
Readback có cấu trúc.
Theo dõi expiry và lỗi tồn đọng.
Đối soát định kỳ giữa yêu cầu và trạng thái đích.
~~~

Một thao tác chạy bằng script vẫn cần quyền phù hợp và phạm vi được phép. Tự động hóa không tự tạo ra nguồn có thẩm quyền hoặc làm yêu cầu mơ hồ trở nên đúng.

Khi chuyển sang provisioning tự động, có thể dùng quy trình thủ công đã chuẩn hóa để xác định dữ liệu đầu vào, policy, điều kiện thành công và cách khắc phục. Không chỉ tự động lặp lại các thao tác bấm vốn đang cấp quá quyền.

### 15.3. Đo chất lượng thay vì chỉ đếm ticket đóng

Các chỉ số có thể gồm:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Thời gian từ yêu cầu hợp lệ đến quyền được xác minh | Người dùng nhận đúng truy cập nhanh đến đâu? |
| Tỷ lệ phải làm lại | Mức độ lỗi danh tính, scope hoặc thao tác là gì? |
| Sai lệch sau đối soát | Trạng thái thực tế có khớp phê duyệt không? |
| Quyền quá hạn chưa thu hồi | Chu trình kết thúc quyền có hoạt động không? |
| Lỗi từng phần chưa xử lý | Có account/grant đang ở trạng thái không rõ không? |
| Tỷ lệ quyền cấp ngoài mẫu | Có nhiều ngoại lệ cần xem lại thiết kế role không? |

Một ticket đóng nhanh nhưng quyền sai hoặc không được thu hồi đúng hạn không phải kết quả tốt.

## 16. Tình huống kiểm thử và diễn tập

Có thể diễn tập trên môi trường hoặc tài nguyên kiểm thử được phép:

| Tình huống | Kỳ vọng theo quy trình minh họa |
| --- | --- |
| Ticket đủ thông tin, phê duyệt đúng scope | Được tiếp tục thực hiện và xác minh |
| Beneficiary chỉ có tên/email nhập nhằng | Chưa cấp phần phụ thuộc định danh |
| Chọn nhầm environment hoặc tenant | Bị phát hiện trước apply hoặc chuyển khắc phục nếu đã áp dụng |
| Executor được tạo user nhưng không được gán role | Không thực hiện phần vượt quyền |
| Request sửa resource scope sau phê duyệt | Không dùng phê duyệt snapshot cũ |
| Role catalog đổi quyền sau phê duyệt | Review theo policy trước thực hiện |
| Approver là beneficiary trong tình huống yêu cầu tách trách nhiệm | Bị chặn |
| Approval đã hết hạn | Không được áp dụng |
| validFrom ở tương lai | Có thể chuẩn bị nếu được phép, chưa bật quyền sớm |
| Account đích đã tồn tại | Không tạo trùng chỉ vì ticket gọi là “new user” |
| Lệnh tạo account timeout | Tra trạng thái trước retry |
| Account tạo thành công, membership thất bại | Ghi lỗi từng phần, không báo hoàn tất |
| Grant mới không có expiry backend | Không tuyên bố tự thu hồi theo ngày trong ticket |
| Có quyền export từ một nguồn cũ | Không đánh dấu đạt acceptance cấm export |
| Activation chưa hoàn tất | Giữ trạng thái chờ theo gate đã định nghĩa |
| Ảnh chụp có token kích hoạt | Không lưu như bằng chứng thông thường |
| Rollback một grant trong T-A | Không làm mất quyền hợp lệ ở tenant khác |
| Quyền được gia hạn | Có nhu cầu và phê duyệt phù hợp cho thời hạn mới |
| Grant đã tới ngày kết thúc | Cơ chế thực thi/thu hồi được kiểm tra theo hợp đồng |
| Có thay đổi đồng thời ngoài ticket | Không ghi đè hoặc gỡ quyền không thuộc phạm vi |

Với helper Java, các test cần có:

1. Snapshot giống hoàn toàn thì qua bước ràng buộc.
2. Đổi beneficiary, tenant, môi trường, role, resource hoặc thời hạn thì không khớp.
3. Tại đúng thời điểm hết hạn approval, helper từ chối.
4. Tại đúng thời điểm hết hạn grant, helper từ chối.
5. Sửa tập resource từ bên ngoài không làm thay đổi snapshot đã sao chép.
6. Role catalog revision khác bị xử lý theo rule của ví dụ.
7. Quy tắc approver khác executor/beneficiary được áp dụng.

Cần kiểm tra tích hợp riêng cho quyền executor, kho approval, thao tác đích, readback và hiệu lực grant. Một helper kiểm tra snapshot đạt không chứng minh toàn bộ provisioning thành công.

Những test trên là nội dung hướng dẫn, không phải báo cáo rằng ví dụ đã được chạy trên một hệ thống IAM thật.

## 17. Bài tập vận dụng

Một doanh nghiệp cần cấp quyền cho ba loại người dùng:

~~~text
Nhân viên mới:
    Tài khoản công ty và truy cập ứng dụng theo công việc.

Cộng tác viên:
    Truy cập giới hạn một tenant và có ngày kết thúc.

Quản trị viên tạm thời:
    Quyền đặc biệt cho một thay đổi được phê duyệt.
~~~

Hãy thiết kế một runbook manual provisioning cho từng loại, xác định:

- Ai xác nhận danh tính và nhu cầu?
- Đối tượng nào cần tạo mới, đối tượng nào chỉ cần liên kết?
- Ai được phê duyệt và ai được thực hiện?
- Scope và thời hạn nào phải được ràng buộc với phê duyệt?
- Có group hoặc quyền kế thừa nào cần kiểm tra?
- Credential được thiết lập và bàn giao bằng luồng nào?
- Kết quả đọc lại và kiểm tra âm là gì?
- Nếu chỉ một phần thao tác thành công, khắc phục thế nào?
- Cơ chế nào chặn hoặc thu hồi quyền khi kết thúc?
- Hồ sơ nào giúp người vận hành sau biết chính xác cần thu hồi gì?

Một quy trình hoàn chỉnh phải nối được **nhu cầu hợp lệ**, **phê duyệt có phạm vi**, **thao tác đúng thẩm quyền**, **quyền thực tế đã xác minh** và **trách nhiệm kết thúc truy cập**.
