# Sponsor trong quản lý danh tính bên thứ ba (Third-party identity)

## 1. Sponsor là ai?

Trong hệ thống **Identity and Access Management (IAM)**, **sponsor** là người hoặc vai trò được tổ chức sở hữu tài nguyên giao trách nhiệm **bảo trợ nhu cầu truy cập của một danh tính bên ngoài**. Sponsor thường là nhân viên hoặc người quản lý nội bộ có hiểu biết về dự án, hợp đồng và mục đích hợp tác với đối tác, nhà cung cấp, nhà thầu hoặc khách mời.

Giả sử công ty A thuê công ty B kiểm thử ứng dụng. Hai kỹ sư B cần vào môi trường staging của A trong sáu tuần. Trưởng nhóm dự án phía A làm sponsor: xác nhận hai người có tham gia công việc, yêu cầu quyền đọc log của ứng dụng đúng dự án, chỉ định ngày hết hạn và tái xác nhận khi công việc thay đổi. Người này là **đầu mối chịu trách nhiệm về nhu cầu kinh doanh** của quyền truy cập.

Sponsor không nhất thiết là:

- Người dùng bên ngoài được cấp quyền;
- Người sở hữu hệ thống định danh hoặc triển khai SSO;
- Quản trị viên trực tiếp tạo tài khoản;
- Chủ sở hữu mọi tài nguyên mà khách muốn truy cập;
- Người có quyền tự phê duyệt mọi đặc quyền, bất kể mức rủi ro;
- Người quản lý nhân sự bên đối tác.

Một sponsor có thể đồng thời là chủ tài nguyên theo cơ cấu tổ chức, nhưng các quyền **đề nghị, phê duyệt, thực thi và kiểm toán** vẫn cần được phân định theo chính sách. Đặc biệt với quyền sản xuất, dữ liệu nhạy cảm hoặc đặc quyền quản trị, việc sponsor xác nhận nhu cầu không tự động thay thế phê duyệt của resource owner, bảo mật hoặc các cấp liên quan.

### Sponsor khác sponsor của một dự án nói chung

Trong tài liệu này, từ **Sponsor** chỉ **người/vai trò bảo trợ quyền truy cập IAM của bên thứ ba**. Thuật ngữ sponsor cũng có thể dùng để chỉ lãnh đạo tài trợ ngân sách dự án hoặc tổ chức tài trợ chương trình. Các vai trò đó không mặc nhiên có trách nhiệm, thẩm quyền hoặc khả năng truy cập giống IAM sponsor.

### Mục tiêu học tập

Sau bài học, người học cần có khả năng:

1. Giải thích vì sao mỗi external principal hoặc quan hệ truy cập cần một owner/sponsor có trách nhiệm.
2. Phân biệt sponsor, requester, approver, resource owner, IAM administrator và người quản trị IdP bên ngoài.
3. Thiết kế yêu cầu cấp quyền và rà soát theo **Joiner–Mover–Leaver (JML)** có sponsor tham gia.
4. Liên kết sponsor với **IdP, SSO, SCIM, RBAC/ABAC, guest account và service account**.
5. Xử lý trường hợp sponsor đổi vai trò, nghỉ việc, không phản hồi hoặc hết hợp đồng.
6. Thu thập bằng chứng kiểm toán để phát hiện và giảm **quyền truy cập tồn dư**.

## 2. Vì sao third-party identity cần sponsor?

Nhân viên nội bộ thường có bản ghi từ HR làm nguồn khởi phát Joiner–Mover–Leaver. Đối với danh tính bên ngoài, tổ chức A không phải lúc nào cũng nhận được sự kiện nhân viên B nghỉ việc, chuyển dự án hoặc kết thúc hợp đồng. IdP của B có thể vẫn xác thực người dùng hợp lệ, trong khi nhu cầu truy cập hệ thống A đã kết thúc.

**Sponsor lấp khoảng trống về trách nhiệm kinh doanh:** họ biết công việc nào đang diễn ra, chủ thể nào thực sự cần quyền, khi nào yêu cầu trở nên không còn hợp lệ, và ai ở A phải được liên hệ khi cần kiểm chứng.

| Vấn đề thường gặp | Nếu không có sponsor rõ ràng | Khi sponsor hoạt động đúng |
|---|---|---|
 Yêu cầu mời người bên ngoài | Không ai xác nhận lý do hoặc phạm vi | Nhu cầu được chứng thực, có dự án/hợp đồng và thời hạn |
 Đối tác thay người | Người cũ có thể giữ quyền | Có đầu mối yêu cầu thu hồi và duyệt người thay thế |
 Guest không đăng nhập lâu ngày | Không rõ còn cần dùng không | Có người xác nhận giữ, giảm hoặc thu hồi |
 Đổi dự án | Quyền cũ cộng dồn với quyền mới | Sponsor kích hoạt xem xét quyền trước–sau |
 Tài khoản có quyền cao | Không rõ ai nhận rủi ro kinh doanh | Sponsor đưa ra lý do; resource owner/IAM phê duyệt theo chính sách |
 Sự cố hoặc kết thúc hợp đồng | Không rõ ai chịu trách nhiệm xác nhận phạm vi ảnh hưởng | Sponsor phối hợp khóa quyền, rà soát và đối soát |
 Sponsor nghỉ việc | Tài khoản bên ngoài trở thành mồ côi | Có quy trình bàn giao và tái chứng nhận |

**Có sponsor là điều kiện quản trị, không phải cơ chế xác thực.** Tên sponsor trong hồ sơ không chứng minh user đã đăng nhập đúng, cũng không thể thay token validation, MFA, kiểm tra quyền backend hoặc thu hồi session.

## 3. Ranh giới vai trò và trách nhiệm

Một triển khai IAM nên phân biệt trách nhiệm giữa các bên tham gia để tránh sponsor vừa yêu cầu vừa tự cấp mọi quyền mà không có kiểm soát.

| Vai trò | Câu hỏi chịu trách nhiệm | Hành động điển hình |
|---|---|---|
 **External user / workload owner bên B** | Ai hoặc hệ thống nào cần truy cập? | Cung cấp thông tin danh tính và công việc, thông báo thay đổi |
 **Requester** | Ai khởi tạo yêu cầu? | Gửi phiếu mời hoặc đổi quyền, có thể chính là sponsor |
 **Sponsor phía A** | Vì sao bên ngoài cần quyền và còn cần tới khi nào? | Xác nhận nhu cầu, thời hạn, đối tác/dự án, chủ động review và Leaver |
 **Resource owner phía A** | Ai được phép làm gì trên tài nguyên tôi sở hữu? | Duyệt role, dữ liệu, project/environment scope |
 **IAM administrator / automation** | Cấp và thu hồi quyền bằng cơ chế kỹ thuật nào? | Provision user, grant, group, federation và deprovision |
 **Security / compliance** | Rủi ro và chính sách nào phải đáp ứng? | Đặt điều kiện đặc quyền, SoD, MFA, giám sát, audit |
 **Partner/vendor manager** | Quan hệ hợp đồng và đầu mối tổ chức còn hợp lệ? | Xác minh pháp nhân, hiệu lực hợp đồng, thông báo chấm dứt |
 **App owner** | Quyền thực tế trong ứng dụng có đúng không? | Thực thi authorization tại backend, xuất quyền, đối soát |
 **Reviewer / auditor** | Bằng chứng phê duyệt, rà soát và thu hồi có đầy đủ không? | Kiểm tra dấu vết, ngoại lệ và remediation |

### 3.1. Ví dụ RACI rút gọn

RACI gồm **Responsible** (thực hiện), **Accountable** (chịu trách nhiệm cuối cùng cho một quyết định), **Consulted** (được tham vấn), **Informed** (được thông báo). Bảng sau chỉ là ví dụ để thiết kế workflow; cơ cấu thực tế phải được tổ chức phê duyệt.

| Hoạt động | Sponsor | Resource owner | IAM | Vendor/partner manager |
|---|---|---|---|---|
 Xác nhận mục đích và thời hạn yêu cầu | A/R | C | I | C |
 Xác nhận trạng thái hợp đồng | C | I | I | A/R |
 Phê duyệt quyền trên tài nguyên | C | A/R | I | I |
 Provision/deprovision kỹ thuật | I | C | A/R | I |
 Rà soát nhu cầu còn hợp lệ | A/R | C | C | C |
 Xác minh quyền thực tế đã bị thu hồi | C | A | R | I |

Một hoạt động có thể cần Security hoặc cấp phê duyệt khác dù không thể hiện hết trong bảng. Tránh dùng RACI để hợp pháp hóa việc thiếu phân tách nhiệm vụ: người đề nghị quyền admin production không nên tự hoàn tất mọi bước duyệt và cấp quyền nếu chính sách yêu cầu phê duyệt độc lập.

### 3.2. Sponsor có thể làm gì và không nên làm gì?

**Được thực hiện theo chính sách:** mở yêu cầu truy cập; xác nhận external user có hợp tác; chọn dự án và mục đích; đề xuất phạm vi, thời hạn và mức quyền; phê duyệt nhu cầu nếu được ủy quyền; yêu cầu rút quyền; tái xác nhận trong access review.

**Không tự suy ra quyền:** bỏ qua xác minh danh tính, thay đổi issuer IdP theo yêu cầu không xác minh, thêm user vào vai trò admin toàn cục, vô hiệu hóa kiểm tra MFA, cho phép vượt tenant, kéo dài grant vô hạn hoặc xóa bằng chứng kiểm toán. Các tác vụ kỹ thuật và phê duyệt đặc biệt vẫn thuộc chủ thể được phân quyền.

## 4. Dữ liệu cần gắn với sponsor

Một hệ thống có thể lưu sponsor trên **guest principal**, **partner relationship**, **membership**, **grant** hoặc một **access request**. Thiết kế tốt cần chỉ rõ sponsor chịu trách nhiệm cho **đúng phạm vi nào**; nếu một người ngoài tham gia nhiều dự án, các quyền của họ có thể thuộc nhiều sponsor khác nhau.

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| external_principal_id | Bản ghi danh tính người ngoài | G-1084 |
| principal_type | Human hay workload | human |
| home_organization_id | Tổ chức đối tác/vender đã xác minh | partner-B |
| sponsor_id | Chủ thể nội bộ có trách nhiệm | employee-A-17 |
| sponsor_status | Sponsor còn đủ điều kiện đảm nhận? | active |
| business_justification | Lý do sử dụng | Kiểm tra báo cáo dự án P42 |
| contract_ref / project_id | Căn cứ hợp tác và tài nguyên | CTR-2026-42 / P42 |
| resource_owner_id | Người quyết định quyền trên tài nguyên | owner-A-9 |
| approved_role / scope | Role, tenant, dự án, thao tác | reader / tenant-B / P42 |
| access_expires_at | Thời điểm quyền chấm dứt nếu không gia hạn | 2026-12-31T00:00:00Z |
| review_due_at | Hạn tái chứng nhận | 2026-12-01T00:00:00Z |
| approval_reference | Phiếu, phiên bản chính sách, quyết định duyệt | REQ-2042 |
| actual_provisioning_status | Đã áp dụng trên hệ thống đích chưa | applied / failed / partial |

### 4.1. Sponsor khác với người chủ trì cuộc họp hay người gửi lời mời

Một người gửi lời mời qua email chưa chắc có trách nhiệm lâu dài hoặc thẩm quyền duyệt. **Requester, inviter và sponsor** có thể là ba người khác nhau. Thiết kế cần ghi rõ ai là sponsor sau khi hoàn tất Joiner, kể cả khi lời mời được gửi tự động hoặc do trợ lý dự án thực hiện.

### 4.2. Một guest có nhiều sponsor

Giả sử chuyên gia B tham gia P42 của bộ phận X và P51 của bộ phận Y. Sponsor X có trách nhiệm với quyền P42; sponsor Y với quyền P51. Nếu X kết thúc hợp tác, thu hồi P42 không nhất thiết phải khóa toàn bộ guest khi P51 còn hợp lệ. Trái lại, nếu user B nghỉ việc ở B và không còn được phép đại diện, cần xử lý toàn bộ membership theo sự kiện Leaver phù hợp.

Đây là lý do **quyền cấp theo quan hệ/scope** hữu ích hơn mô hình một cờ active cho toàn bộ tài khoản.

### 4.3. Không lưu bí mật vào hồ sơ sponsor

Access request và hồ sơ sponsor có thể chứa thông tin doanh nghiệp hoặc cá nhân nhạy cảm. Chỉ lưu tham chiếu cần thiết; bảo vệ quyền xem theo vai trò. Không đặt password, access token, private key hoặc thông tin xác thực còn sử dụng được vào ghi chú công việc hoặc log duyệt.

## 5. Joiner: sponsor bắt đầu một yêu cầu truy cập

Trong **Joiner–Mover–Leaver**, sponsor thường là người nhận diện nhu cầu và phát động quy trình cho external user.

### 5.1. Trước khi gửi lời mời

Sponsor phải trả lời tối thiểu:

1. Người hoặc hệ thống bên ngoài thuộc tổ chức nào, đã được xác minh quan hệ chưa?
2. Công việc nào thật sự cần truy cập, có ticket/hợp đồng/dự án làm căn cứ không?
3. Tài nguyên, hành động, tenant, môi trường và dữ liệu cần đến mức nào?
4. Thời gian cần quyền từ lúc nào đến lúc nào; có kỳ review và hạn mời riêng không?
5. Resource owner nào có thẩm quyền duyệt? Có điều kiện Security hoặc phê duyệt đặc quyền không?
6. Nguồn IdP/SSO, danh tính khách và cơ chế provisioning nào sẽ được dùng?
7. Ai thông báo cho A nếu nhân viên B rời tổ chức hoặc mất vai trò?

**Least privilege:** Nếu nhà thầu B chỉ cần đọc log của staging trong 14 ngày, sponsor cần đề xuất quyền đọc đúng ứng dụng và 14 ngày; không đề nghị quyền admin toàn môi trường.

### 5.2. Luồng Joiner có sponsor

~~~mermaid
sequenceDiagram
    actor B as Người dùng bên ngoài B
    participant S as Sponsor A
    participant O as Resource owner A
    participant IAM as IAM / approval workflow
    participant IDP as IdP tin cậy
    participant APP as Ứng dụng đích A
    S->>IAM: Yêu cầu mời, lý do, scope, expiry
    IAM->>O: Trình duyệt entitlement trên tài nguyên
    O-->>IAM: Duyệt/từ chối theo chính sách
    IAM-->>B: Lời mời có hạn nếu được duyệt
    B->>IDP: Xác thực danh tính
    IDP-->>IAM: Chứng cứ xác thực đã kiểm tra
    IAM->>IAM: Liên kết principal và sponsor, tạo grants
    IAM->>APP: Provision quyền đã duyệt
    APP-->>IAM: Kết quả áp dụng
    IAM-->>S: Thông báo và bằng chứng Joiner
~~~

Hình trên là luồng logic. Trong triển khai thực tế, ứng dụng hoặc relying party/service provider thường nhận và kiểm tra trực tiếp OIDC token hoặc SAML assertion; IAM có thể được tích hợp hoặc đóng vai trò broker. Sponsor **không trực tiếp xác minh token**, nhưng cần biết quyền chỉ có hiệu lực sau khi các điều kiện kỹ thuật và phê duyệt đã hoàn tất.

### 5.3. Các giai đoạn phê duyệt

| Giai đoạn | Điều kiện hoàn tất | Tác nhân chính |
|---|---|---|
 Business need | Có lý do, dự án, hợp đồng, thời hạn rõ | Sponsor |
 Identity/relationship verification | Đúng tổ chức, chủ thể và trust source | IAM, vendor/partner manager |
 Resource authorization | Role và scope đã được duyệt | Resource owner |
 Security conditions | MFA, thiết bị, PAM/JIT nếu quyền nhạy cảm | IAM/Security |
 Provisioning | Local principal, group/grant được tạo đúng | IAM và app owner |
 Evidence/notification | Ghi trạng thái và thời hạn, xác nhận với sponsor | IAM workflow |

Sponsor có thể phải yêu cầu bổ sung chứng cứ khi người được mời không khớp identity đã dự kiến, khi hợp đồng đã hết hạn hoặc khi quyền được yêu cầu vượt phạm vi dự án. **Đã duyệt nhu cầu không có nghĩa hệ thống đã provision thành công**; cần phân biệt approval state và actual access state.

## 6. Sponsor trong thiết lập danh tính, SSO và SCIM

Sponsor tạo cơ sở nghiệp vụ; **IdP, SSO, SCIM, local IAM và resource server** thực hiện các chức năng kỹ thuật riêng.

| Thành phần | Công việc chính | Điều sponsor cần quan tâm |
|---|---|---|
| IdP của đối tác | Xác thực nhân viên B theo chính sách nguồn | Đối tác có đầu mối tin cậy, có cơ chế báo Leaver? |
| OIDC/SAML SSO | Chuyển bằng chứng xác thực đến ứng dụng A | Trust đã được cấu hình an toàn, không dùng email làm bằng chứng cấp quyền? |
| Guest/local principal | Liên kết external subject với bản ghi tại A | Guest có owner, status và đúng đối tác? |
| SCIM | Đồng bộ user/group khi có tích hợp | Tín hiệu Mover/Leaver có tới đúng nơi và được đối soát? |
| JIT provisioning | Tạo bản ghi khi user đăng nhập lần đầu | Có invitation/sponsor/grant hợp lệ trước khi cấp quyền? |
| RBAC/ABAC | Quyết định role, tenant, dự án và điều kiện | Scope có phản ánh đúng yêu cầu không? |
| Resource server | Thực thi quyền trên API/dữ liệu | Có thể kiểm chứng guest không vượt phạm vi? |

### 6.1. Sponsor không đồng nghĩa IdP owner

Khi nhân viên B đăng nhập bằng OIDC/SAML, A phải xác minh issuer, audience, chữ ký, thời hạn và điều kiện giao thức; đối với OIDC liên kết chủ thể dựa trên cặp **(iss, sub)** từ ID token hợp lệ, không dựa riêng email. Sponsor không được thay trust issuer hoặc tự gộp danh tính chỉ vì B gửi một email có cùng tên.

Với SAML, SP phải xác minh issuer/entityID, audience, chữ ký, điều kiện thời gian, recipient/destination và các ràng buộc theo luồng. IAM hoặc đội vận hành có trách nhiệm cấu hình trust; sponsor cung cấp xác nhận quan hệ đối tác và phối hợp với bên B qua kênh đã được thẩm định.

### 6.2. Sponsor không thay thế nguồn provisioning

SCIM có thể truyền trạng thái active/inactive và group, nhưng chỉ với các hệ thống có hỗ trợ và tích hợp đúng. Nếu B gửi sự kiện nhân viên nghỉ việc chậm, sponsor A có thể biết dự án đã kết thúc sớm hơn và phải kích hoạt thu hồi theo chính sách A. Ngược lại, sponsor chỉ có thể không biết nhân viên B đã nghỉ việc, nên **hạn truy cập, access review và đối soát độc lập** vẫn cần thiết.

### 6.3. JIT provisioning và JIT privileged access là hai việc khác

- **JIT provisioning:** tạo guest/local principal tại lần đăng nhập đầu tiên khi thỏa điều kiện được duyệt.
- **JIT elevation:** tạm nâng quyền trên tài nguyên nhạy cảm trong một khoảng thời gian/ticket, thường qua PAM.

Sponsor có thể bảo trợ nhu cầu cho cả hai nhưng quyền cấp, approver và thời hạn thường khác nhau. Không nên cấp quyền production admin lâu dài cho guest chỉ vì JIT đã tạo tài khoản thành công.

## 7. Mover: sponsor cập nhật nhu cầu và ngăn quyền tích lũy

**Mover** có thể xảy ra khi một người bên ngoài chuyển dự án, thay vai trò, đổi tổ chức, thay hình thức hợp tác hoặc khi hợp đồng được gia hạn nhưng thu hẹp phạm vi. Sponsor cần bảo đảm quyền **được tính lại theo nhu cầu mới**, thay vì chỉ cấp bổ sung quyền.

### 7.1. Các sự kiện cần sponsor xử lý

| Sự kiện | Câu hỏi của sponsor | Hành động IAM liên quan |
|---|---|---|
 Kỹ sư B chuyển từ P42 sang P51 | Còn công việc nào ở P42 không? | Thu hồi grant P42, duyệt quyền P51 mới |
 Từ quyền xem tài liệu sang chỉnh sửa | Có lý do, thời hạn và chủ dữ liệu duyệt không? | Phê duyệt tăng quyền, thay role và kiểm tra SoD |
 Hợp đồng vẫn còn nhưng phạm vi giảm | Hạng mục nào không còn được phép? | Gỡ các grants ngoài hợp đồng |
 Vendor B thay nhân sự C bằng D | C còn cần truy cập? D đã được xác minh chưa? | Leaver cho C, Joiner cho D |
 Người ngoài chuyển sang đơn vị B khác | Quan hệ danh tính và hợp đồng nào đang áp dụng? | Đánh giá lại partner mapping và membership |
 B thay IdP hoặc domain email | Danh tính được chuyển đổi có đúng người không? | Tổ chức quy trình account linking có xác minh |
 Sponsor A chuyển công tác | Ai sẽ nhận quyền bảo trợ? | Tái chỉ định sponsor và review các grants |
 Ứng dụng được chuyển chủ sở hữu | Owner mới có chấp nhận quyền hiện hữu? | Review theo resource owner mới |

### 7.2. Quy trình Mover có bằng chứng

1. **Nhận tín hiệu:** từ sponsor, đối tác, hệ thống hợp đồng, ticket, IdP/SCIM hoặc access review.
2. **Đối chiếu thực tế:** xác định tất cả membership/grant hiện có, kể cả chia sẻ trực tiếp ở ứng dụng.
3. **Xác định nhu cầu mới:** sponsor nêu công việc, phạm vi, người chịu trách nhiệm và hạn mới.
4. **Phê duyệt đúng thẩm quyền:** resource owner quyết định quyền trên tài nguyên của mình; Security xem xét đặc quyền khi cần.
5. **Thu hồi quyền thừa:** IAM/app owner loại group, role, grant và session đặc biệt không còn hợp lệ.
6. **Cấp quyền mới có giới hạn:** xác định đúng tenant, project, môi trường, tài nguyên và expiry.
7. **Xác minh sau thay đổi:** thử cả yêu cầu được phép lẫn bị từ chối; lưu quyền trước/sau và kết quả.

**Ví dụ:** Một nhà thầu B có quyền đọc dữ liệu dự án P42. Sau ba tháng, sponsor A chuyển nhà thầu sang P51 và yêu cầu thêm role editor. Nếu IAM chỉ thêm role P51, người đó vẫn có thể đọc P42 dù không còn công việc liên quan. Sponsor cần xác nhận P42 được thu hồi và resource owner P51 phê duyệt role mới.

### 7.3. Gia hạn có điều kiện

Khi hợp đồng kéo dài, sponsor không nên gia hạn vô điều kiện mọi guest hoặc service account. Mỗi đợt gia hạn cần xác nhận **principal nào còn tham gia**, **grant nào còn cần**, **đối tác còn hợp lệ**, **sponsor còn trách nhiệm** và **thời hạn mới có cơ sở nào**.

Việc kéo dài contract end date không đồng nghĩa tất cả grants cũng phải được kéo dài. Có thể một nhóm tư vấn chỉ tham gia giai đoạn thiết kế; quyền của nhóm đó nên hết hạn khi giai đoạn hoàn tất dù hợp đồng tổng thể còn hiệu lực.

## 8. Leaver: sponsor kích hoạt và theo dõi thu hồi

**Leaver** bắt đầu khi người dùng bên ngoài nghỉ việc, rời dự án, mất quyền đại diện, hết hợp đồng, không còn sponsor hợp lệ hoặc bị đình chỉ do rủi ro. Sponsor chịu trách nhiệm xác nhận **mục đích truy cập đã kết thúc** và phối hợp thực hiện thu hồi; IAM và chủ ứng dụng phải xử lý kỹ thuật và xác minh quyền thực tế.

### 8.1. Phân biệt phạm vi thu hồi

| Phạm vi kết thúc | Xử lý thích hợp | Điều cần tránh |
|---|---|---|
 Một grant dự án P42 | Gỡ đúng role/membership P42, xử lý phiên/ủy quyền phụ thuộc | Xóa toàn bộ quyền hợp lệ ở P51 khi không cần |
 Một người B rời công ty | Chặn mọi local principal/membership không còn hợp lệ theo quan hệ với B | Chỉ gỡ một group mà giữ ứng dụng khác |
 Một ứng dụng do B vận hành ngừng dùng | Disable client, key, API scope và workload permission liên quan | Chỉ khóa tài khoản nhân viên B |
 Một hợp đồng A–B hết hạn | Thu hồi mọi quyền phát sinh từ hợp đồng đó | Bỏ sót grants được cấp thủ công |
 Toàn bộ quan hệ với B chấm dứt | Offboard user, workload, federation/provisioning và quyền downstream theo phạm vi | Xóa log hoặc dữ liệu có nghĩa vụ lưu giữ |

### 8.2. Luồng thu hồi

~~~mermaid
flowchart TD
    E["Sponsor hoặc nguồn tin cậy phát Leaver"] --> D["Xác định user, hợp đồng, scope và thời điểm"]
    D --> BLOCK["IAM chặn quyền và đăng nhập mới theo trạng thái"]
    BLOCK --> G["Gỡ group, role, membership và direct share"]
    G --> S["Thu hồi session, refresh token, quyền tạm nếu hỗ trợ"]
    S --> W["Thu hồi workload/credential phụ thuộc khi có"]
    W --> R{"Ứng dụng đích đã xác nhận?"}
    R -->|"Chưa"| F["Tạo lỗi remediation và theo dõi"]
    F --> R
    R -->|"Đã xác nhận"| A["Sponsor nhận kết quả và audit đóng yêu cầu"]
~~~

Thứ tự có thể thay đổi trong sự cố an ninh khẩn cấp: khi rủi ro cao, việc **chặn truy cập ngay** được ưu tiên, phần đối soát và thủ tục tiếp tục thực hiện sau.

### 8.3. Thu hồi quyền không chỉ là khóa IdP

IdP của B có thể vô hiệu hóa người dùng nhưng A vẫn giữ:

- Guest/local principal, membership hoặc group;
- Phiên ứng dụng A đang hoạt động;
- Refresh token hoặc access token còn hạn;
- Quyền đọc trực tiếp trong SaaS, repository hoặc ACL ngoài IAM;
- Phiên đặc quyền PAM đã mở;
- OAuth client, API key hoặc service account được người đó từng sở hữu.

Một JWT đã phát hành thường tiếp tục hợp lệ đến thời điểm hết hạn **nếu resource server chỉ kiểm tra token mà không đánh giá trạng thái hiện tại**. Thiết kế thu hồi có thể dùng session invalidation, token TTL phù hợp, introspection, revocation nếu được hỗ trợ hoặc kiểm tra policy tại resource server. Không thể suy rằng sự kiện disable từ SCIM lập tức vô hiệu hóa mọi access token.

### 8.4. Sponsor phải nhận bằng chứng gì?

Sponsor nên nhận kết quả đủ để phân biệt:

- **Requested:** yêu cầu thu hồi đã được tạo;
- **Accepted:** workflow/IAM nhận và đồng ý xử lý;
- **Applied:** các hệ thống đích báo đã xóa grant;
- **Verified:** xác minh quyền thực tế đã không còn hiệu lực ở phạm vi cần thu hồi;
- **Exception:** có hệ thống lỗi, chưa xác minh hoặc có nghĩa vụ lưu giữ đặc biệt.

Sponsor không nên bấm “đã xong” chỉ khi ticket ở trạng thái closed nhưng một ứng dụng vẫn còn quyền. IAM/app owner cần giữ trạng thái lỗi và remediation rõ ràng; sponsor phối hợp giải quyết các vấn đề về phạm vi nghiệp vụ.

### 8.5. Khi nào cần tạm đình chỉ ngay?

Nếu vendor bị nghi xâm nhập, nhân viên ngoài mất tư cách đại diện, hoặc quyền truy cập nhạy cảm không thể xác minh, sponsor có thể **yêu cầu đình chỉ** theo kênh đã định nghĩa. Đội có thẩm quyền thực hiện khóa truy cập và phối hợp điều tra. Việc đình chỉ không tự động kết luận sự cố đã xảy ra, nhưng giới hạn rủi ro trong lúc xác minh.

## 9. Chuyển giao sponsor và xử lý sponsor mồ côi

Điểm thất bại thường gặp là sponsor A nghỉ việc, đổi bộ phận hoặc không còn phụ trách hợp đồng nhưng guest vẫn active. Sponsor cũ có thể không còn được phép phê duyệt, còn sponsor mới chưa biết quyền nào đang tồn tại.

### 9.1. Những sự kiện kích hoạt reassignment

- Sponsor thôi việc, chuyển vị trí hoặc mất quyền tham gia dự án;
- Hợp đồng được giao sang bộ phận khác;
- Dự án có resource owner mới;
- Sponsor bị đình chỉ hoặc không phản hồi review quá hạn;
- Vendor/partner được tái cơ cấu, đổi người quản lý quan hệ;
- Phát hiện tài khoản ngoài không có sponsor hoặc sponsor không tồn tại.

### 9.2. Quy trình chuyển giao

1. **Tổng hợp danh sách quyền được sponsor cũ bảo trợ:** theo principal, partner, dự án, scope và ngày hết hạn.
2. **Chọn sponsor mới có trách nhiệm hợp lệ:** người đó thuộc tổ chức A, được chỉ định cho hợp đồng/dự án và đồng ý nhận nhiệm vụ theo workflow.
3. **Tái xác nhận business need:** không tự kế thừa mọi quyền; với grants đặc biệt hoặc quá hạn cần phê duyệt lại.
4. **Cập nhật ownership:** ghi sponsor_id mới, thời điểm, người phê duyệt và phạm vi kế thừa.
5. **Thông báo và đặt hạn review:** để sponsor mới không bỏ sót tài khoản.
6. **Xử lý quyền không có người nhận:** áp dụng grace period hoặc đình chỉ/thu hồi theo mức rủi ro và chính sách.

Ví dụ: Sponsor X bảo trợ năm khách thuộc P42. X nghỉ việc nhưng hợp đồng vẫn còn. Hệ thống cần điều phối chuyển năm grant tới sponsor Y. Y xác nhận chỉ còn ba người làm việc; hai guest còn lại phải bị thu hồi. Việc cập nhật một tên sponsor mà không rà soát quyền không giải quyết được rủi ro truy cập tồn dư.

### 9.3. Fallback owner và chính sách không phản hồi

Để tránh hồ sơ vô chủ, tổ chức có thể đăng ký **owner team** hoặc người quản lý cấp trên làm điểm chuyển giao, nhưng cần quy tắc rõ ai được nhận và duyệt quyền. Đối với review quá hạn, có thể cảnh báo, giới hạn hoặc đình chỉ quyền theo mức độ nhạy cảm, rồi xử lý ngoại lệ đã phê duyệt. Không mặc định “im lặng là đồng ý gia hạn”.

### 9.4. Một sponsor có quá nhiều guest

Khi sponsor bảo trợ hàng nghìn guest, trách nhiệm rà soát dễ trở thành hình thức. Hệ thống nên tổ chức theo **team owner, hệ thống, hợp đồng, dự án và đợt review**, phân công rõ người thực tế có đủ kiến thức để xác nhận. Có thể tự động hóa dữ liệu đối soát, nhưng **quyết định giữ quyền** vẫn cần người hoặc chính sách được ủy quyền chịu trách nhiệm.

## 10. Access review và recertification với sponsor

**Access review** kiểm tra các quyền hiện tại có còn hợp lệ theo mục đích, vai trò và thời hạn không. **Recertification** là việc người có thẩm quyền xác nhận giữ, giảm hoặc thu hồi quyền sau khi được trình bày đủ thông tin.

### 10.1. Những trường dữ liệu cần hiển thị cho sponsor

| Thông tin | Vì sao cần cho quyết định |
|---|---|
 Principal, tổ chức nguồn và định danh liên kết | Xác định đúng người hoặc workload |
 Dự án, hợp đồng, ứng dụng và resource owner | Biết mục đích và trách nhiệm |
 Quyền và mức nhạy cảm | Đánh giá quyền thừa hoặc đặc quyền |
 Lần truy cập gần đây và cách sử dụng | Tín hiệu tham khảo về nhu cầu |
 Ngày tạo, ngày hết hạn và review trước | Nhận diện grants lâu ngày hoặc quá hạn |
 Các nhóm/ACL/downstream grants có hiệu lực | Tránh đánh giá thiếu quyền thực tế |
 Sponsor cũ/mới và nguồn phê duyệt | Làm rõ trách nhiệm và lịch sử |
 Trạng thái ứng dụng đích và lỗi đồng bộ | Không coi danh sách IAM là toàn bộ thực tế |

Không nên dựa duy nhất vào **last login**: một tài khoản hiếm sử dụng có thể rất nhạy cảm; ngược lại một tài khoản dùng thường xuyên có thể vẫn đang truy cập ngoài phạm vi được duyệt.

### 10.2. Các quyết định review

Sponsor có thể đưa ra kết quả theo phạm vi được ủy quyền:

1. **Keep:** giữ nguyên quyền khi có nhu cầu xác nhận và còn đáp ứng chính sách.
2. **Reduce:** chỉ giữ subset quyền hoặc giảm role/phạm vi.
3. **Reassign:** chuyển sponsor hoặc resource owner theo quy trình.
4. **Expire/End:** không gia hạn hoặc thu hồi theo ngày kết thúc.
5. **Escalate:** chuyển cho resource owner, Security hoặc quản lý hợp đồng khi có thông tin mâu thuẫn.

Quyết định được lưu kèm lý do và thời điểm. **Keep không nên tự động gia hạn vô hạn**; việc gia hạn cần có giới hạn thời gian và các phê duyệt bổ sung khi chính sách yêu cầu.

### 10.3. Khi sponsor không phản hồi

Một workflow có thể gửi nhắc trước hạn, escalations tới người quản lý/owner team, rồi đình chỉ hoặc thu hồi theo rủi ro. Với dữ liệu rất nhạy cảm, chính sách có thể chọn từ chối tiếp tục sau hạn review; với quyền ít nhạy cảm, có thể áp dụng grace period được kiểm soát. Cần ghi nhận ngoại lệ và tránh tạo ra tình trạng quyền quá hạn vĩnh viễn.

### 10.4. Tần suất phụ thuộc rủi ro

Người ngoài được quyền admin production, giải mã dữ liệu hoặc xem thông tin nhạy cảm thường cần xác nhận chặt hơn khách chỉ đọc tài liệu ít nhạy cảm. Tổ chức có thể kết hợp:

- Review định kỳ theo mức độ rủi ro;
- Review theo sự kiện khi đổi sponsor, hợp đồng, dự án, IdP hoặc quyền;
- Review khi phát hiện tài khoản inactive, không owner, quyền đặc biệt hoặc sai lệch provisioning;
- Review khẩn cấp trong sự cố.

Không có chu kỳ cố định phù hợp mọi tài nguyên. Cần xác định SLA, độ bao phủ và cách đối soát theo chính sách quản trị.

## 11. Sponsor và chính sách RBAC/ABAC theo tài nguyên

Sponsor mô tả **mục đích kinh doanh** của yêu cầu. **RBAC (Role-Based Access Control)** và **ABAC (Attribute-Based Access Control)** chuyển quyết định đã duyệt thành giới hạn kỹ thuật ở hệ thống đích.

### 11.1. RBAC không đủ nếu thiếu scope

Vai trò report_viewer có thể cho phép đọc báo cáo, nhưng chưa xác định **báo cáo của tenant nào**. Nếu sponsor chỉ yêu cầu “role viewer” và IAM gắn vào toàn ứng dụng, user bên ngoài có nguy cơ đọc chéo khách hàng.

Một grant cần chỉ rõ cả:

- Ai: principal và partner/vendor;
- Làm gì: action hoặc role;
- Ở đâu: tenant, resource, project và môi trường;
- Khi nào: thời hạn và điều kiện phiên;
- Vì sao: hợp đồng, ticket và sponsor;
- Ai phê duyệt: resource owner và người có thẩm quyền.

### 11.2. Chính sách minh họa

~~~text
authorize(principal, request, context):
    if not context.authentication_valid: DENY
    if principal.status != "active": DENY

    partner = get_partner(principal.partner_id)
    if partner.status != "active": DENY

    grant = get_effective_grant(principal, request.resource_id)
    if grant is missing: DENY
    if grant.status != "active": DENY
    if now >= grant.expires_at: DENY
    if grant.sponsor_id is missing: DENY
    if not sponsor_is_valid_for_scope(grant.sponsor_id, grant.scope): DENY

    if request.action not in grant.allowed_actions: DENY
    if request.resource.tenant_id != grant.tenant_id: DENY
    if request.resource.project_id not in grant.project_ids: DENY
    if not relationship_is_current(partner.id, grant.contract_ref): DENY
    if not context.meets_risk_policy: DENY

    ALLOW
~~~

Đây là **mã giả**, không phải chính sách áp dụng nguyên xi cho mọi hệ thống. Việc kiểm tra sponsor tại mỗi request chỉ phù hợp nếu dữ liệu sponsor có độ tin cậy, khả năng sẵn sàng và cách xử lý sự cố rõ ràng. Một số triển khai chọn kiểm tra sponsor tại lúc cấp/đổi quyền và đối soát định kỳ; các kiểm tra trọng yếu như trạng thái principal, grant, tenant và hạn vẫn cần được thực thi tại API/resource server.

### 11.3. Sponsor không được tự tăng trần quyền

Giả sử sponsor yêu cầu guest_editor cho P42. Nếu IdP của B gửi claim Global-Admin, A chỉ áp dụng mapping được A phê duyệt, không biến claim đó thành đặc quyền hệ thống. Khi cần quyền privileged, resource owner và Security/PAM có thể phải tham gia workflow độc lập.

### 11.4. Tách quyền nhiều tenant

Nếu guest U tham gia P42 của B và P51 của C, cần gắn từng grant với sponsor và partner context tương ứng. Sponsor P42 không được duyệt quyền P51 nếu họ không có thẩm quyền trên tenant C. Khi một relationship kết thúc, chỉ thu hồi đúng phần liên quan, trừ khi danh tính của U đã bị vô hiệu toàn bộ.

## 12. Sponsor trong PAM/JIT và service account

### 12.1. Quyền đặc biệt cấp theo phiên

Vendor B cần chỉnh cấu hình production trong một sự cố được ghi ticket. Sponsor A xác nhận đây là công việc có thật, còn resource owner hoặc người có thẩm quyền duyệt quyền theo phạm vi. **Privileged Access Management (PAM)** có thể cấp **Just-in-Time (JIT) elevation** với hạn ngắn, session tracking, kiểm soát credential và tự thu hồi.

~~~mermaid
sequenceDiagram
    actor V as Kỹ sư vendor B
    participant S as Sponsor A
    participant O as Resource owner / Security A
    participant PAM as PAM / JIT
    participant P as Production system
    V->>S: Yêu cầu quyền cho ticket INC-2048
    S->>S: Xác nhận hợp đồng và nhu cầu
    S->>O: Trình action, system, risk, expiry
    O-->>PAM: Duyệt quyền tạm
    PAM->>P: Cấp quyền theo session/ticket
    V->>P: Thực hiện tác vụ đã được duyệt
    PAM->>P: Hết phiên, thu hồi quyền
    PAM-->>S: Kết quả và audit evidence
~~~

Sponsor cần biết thời điểm đặc quyền kết thúc và ứng dụng xác nhận thu hồi. Có thể tổ chức **break-glass** cho sự cố nghiêm trọng với policy, giám sát và hậu kiểm riêng. Sponsor không tự được bỏ qua các giới hạn chỉ vì tình huống khẩn cấp.

### 12.2. Service account và workload identity có cần sponsor?

Tài khoản dịch vụ thường phục vụ chương trình, đồng bộ API hoặc tác vụ tự động; chúng không đi theo HR lifecycle của một cá nhân. Vì vậy, ngoài **technical owner** (chịu trách nhiệm vận hành credential và ứng dụng), một số hệ thống cần **business sponsor** xác nhận nhu cầu của workload bên ngoài và hợp đồng liên quan.

| Loại chủ thể | Ai xác nhận nhu cầu? | Ai quản lý kỹ thuật? | Sự kiện Leaver chính |
|---|---|---|---|
| Guest của kỹ sư B | Sponsor dự án A | IAM, app owner, IdP phù hợp | Nghỉ việc, rời dự án, hết hạn |
| OAuth client của hệ thống B | Business sponsor / API product owner A | Client owner, API/IAM team | Ngừng tích hợp, hết hợp đồng |
| Service account vận hành bởi vendor B | Sponsor dịch vụ A | Service owner, IAM/secret manager | Ngừng dịch vụ, đổi owner, compromise |
| Workload federation identity | Owner hợp đồng/dịch vụ A | Platform/IAM team | Thay workload hoặc mất trust |

Sponsor không nên yêu cầu nhà cung cấp dùng mật khẩu guest của kỹ sư để chạy cron job. Cần **workload identity riêng**, scope/audience tối thiểu, owner rõ, credential lưu trong secret manager hoặc xác thực máy thích hợp, hạn review và khả năng thu hồi khi contract kết thúc.

### 12.3. Khi người sở hữu workload thay đổi

Nếu kỹ sư B điều hành một integration rời công ty, có thể vẫn cần duy trì workload hoạt động. Trước khi giữ credential, cần xác nhận **technical owner mới**, đảm bảo chỉ chủ thể được ủy quyền có thể sử dụng key/secret, thực hiện rotation khi cần và review scope. Sponsor phải xét nhu cầu kinh doanh của integration độc lập với việc kỹ sư cũ còn có guest account hay không.

## 13. Tự động hóa vòng đời có sponsor

Tự động hóa hữu ích nhất khi làm rõ **ai cần hành động, hạn nào, kết quả đã áp dụng chưa và ai nhận ngoại lệ**. Ghi sponsor trong một trường dữ liệu nhưng không có reminder, event hoặc escalation sẽ khó ngăn tài khoản mồ côi.

### 13.1. Các trạng thái workflow tham khảo

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| requested | Sponsor gửi nhu cầu có scope và expiry | Kiểm tra điều kiện, chọn approver |
| pending_approval | Resource owner hoặc Security cần duyệt | Duyệt, từ chối, yêu cầu bổ sung |
| approved | Quyền đã được duyệt nhưng chưa chắc được provision | IAM tạo/liên kết principal và grants |
| provisioning | Đang cập nhật ứng dụng đích | Theo dõi lỗi và xác nhận |
| active | Grant đang có hiệu lực | Theo dõi expiry, review, Mover/Leaver |
| review_due | Đến hạn sponsor xác nhận nhu cầu | Keep, reduce, revoke hoặc escalate |
| suspension_requested | Có rủi ro hoặc thiếu owner | Khóa theo chính sách và xác minh |
| revoking | Đang thu hồi trên các hệ thống | Theo dõi session, token, grants |
| revoked_verified | Hoàn tất kiểm chứng trong phạm vi yêu cầu | Lưu audit, đóng workflow |
| remediation_required | Sai lệch hoặc lỗi chưa thể xác nhận | Giao app owner/IAM xử lý và kiểm tra lại |

Các trạng thái chỉ minh họa workflow, không phải chuẩn giao thức IAM. Hệ thống có thể đơn giản hơn nhưng vẫn cần phân biệt **đã đề nghị**, **đã duyệt**, **đã áp dụng** và **đã kiểm chứng**.

### 13.2. Event-driven lifecycle

Các nguồn sự kiện có thể gồm:

- **HR hoặc directory của A:** sponsor nghỉ việc, mất quyền hoặc đổi bộ phận;
- **Contract/vendor management:** hợp đồng hết hạn, bị đình chỉ hoặc thay đổi phạm vi;
- **IdP/SCIM từ B:** user rời tổ chức, đổi nhóm hoặc inactive;
- **Project/ticket management:** dự án đóng, yêu cầu hỗ trợ hoàn tất;
- **IAM/PAM:** grant hết hạn, quyền đặc biệt kết thúc, review quá hạn;
- **Reconciliation:** phát hiện quyền đích còn sống hoặc principal không owner.

Mỗi event nên có nguồn, định danh ổn định, thời gian, correlation ID, đối tượng bị ảnh hưởng và quy tắc xử lý khi đến trễ hoặc lặp. Với sự kiện đến sai thứ tự, cần kiểm tra trạng thái hiện tại trước khi provision để tránh tái kích hoạt quyền đã thu hồi.

### 13.3. Ví dụ hồ sơ yêu cầu

~~~json
{
  "request_id": "REQ-2042",
  "request_type": "third_party_access",
  "principal_id": "G-1084",
  "principal_type": "human",
  "partner_id": "partner-B",
  "sponsor_id": "employee-A-17",
  "business_reason": "review-report-P42",
  "resource_id": "project-P42-reporting",
  "tenant_id": "tenant-B",
  "requested_actions": ["reports.read"],
  "valid_until": "2026-12-31T00:00:00Z",
  "approval": {
    "resource_owner_id": "employee-A-9",
    "decision": "approved"
  },
  "provisioning_state": "applied",
  "review_due_at": "2026-12-01T00:00:00Z"
}
~~~

Đây là mô hình logic, không phải schema bắt buộc. Trạng thái applied cần được đối soát với quyền thực tế. Dữ liệu cá nhân và tham chiếu hợp đồng phải được bảo vệ theo chính sách.

### 13.4. Mã giả khi sponsor mất hiệu lực

~~~text
onSponsorDeactivated(sponsorId):
    grants = findActiveThirdPartyGrantsBySponsor(sponsorId)
    for grant in grants:
        ownerTeam = findApprovedFallbackOwner(grant.resourceId)
        createReassignmentTask(ownerTeam, grant)
        notifyResourceOwner(grant.resourceId, grant)

        if grant.isHighRisk():
            applyConfiguredSuspensionPolicy(grant)
        else:
            setReviewDeadline(grant, configuredGracePeriod(grant))

    trackUntilReassignedOrRevoked(grants)
~~~

Tùy chính sách, một số quyền có thể bị đình chỉ ngay, các quyền khác có thời gian xử lý có kiểm soát. Không mặc định sponsor tạm nghỉ dẫn tới khóa tất cả user; cần phân loại sự kiện và thẩm quyền thật sự.

### 13.5. Chống xung đột cấp và thu hồi

Nếu SCIM từ B báo user inactive ngay sau khi sponsor duyệt một grant, tác vụ cấp quyền đến muộn có thể kích hoạt lại tài khoản. Hệ thống cần:

1. Kiểm tra trạng thái principal/partner/relationship trước khi áp dụng grant;
2. Dùng ID và version/timestamp để nhận diện quyết định cũ;
3. Làm các thao tác provisioning idempotent khi có thể;
4. Không cho workflow cũ tự vượt trạng thái revoked/offboarded;
5. Cảnh báo và đối soát khi nhận event lặp, thiếu hoặc sai thứ tự.

## 14. Audit và chỉ số chất lượng sponsor

### 14.1. Audit phải chứng minh chuỗi quyết định

Một hồ sơ kiểm toán tốt trả lời: **ai yêu cầu, ai bảo trợ, ai phê duyệt, quyền nào, phạm vi nào, trong bao lâu, đã áp dụng chưa và đã được thu hồi ra sao?**

| Sự kiện | Nội dung nên ghi |
|---|---|
 Sponsor assigned | Sponsor, principal/grant, scope, người chỉ định, thời điểm |
 Access requested | Principal, đối tác, lý do, resource, hạn |
 Access approved/denied | Approver, điều kiện, phiên bản policy, quyết định |
 Provisioning result | Hệ thống đích, trạng thái và correlation ID |
 Mover | Grant trước–sau, sponsor, approver, thời gian |
 Sponsor reassigned | Sponsor cũ–mới, quyết định review và ngoại lệ |
 Review completed | Reviewer, keep/reduce/revoke, lý do và expiry mới |
 Leaver requested | Nguồn sự kiện, phạm vi, thời điểm hiệu lực |
 Revocation verified | Ứng dụng đích đã xác nhận, lỗi còn mở |
 Emergency exception | Người quyết định, điều kiện, hạn, hậu kiểm |

Việc sponsor bấm “Approve” chỉ là một bước. Audit cần bao phủ quyết định và hiệu lực kỹ thuật, chống sửa trái phép, phân quyền đọc và lưu theo retention policy. Không ghi password, private key, access token, refresh token hoặc session cookie còn dùng được.

### 14.2. KPI vận hành

| Chỉ số | Ý nghĩa |
|---|---|
 Tỷ lệ grant bên thứ ba không có sponsor hợp lệ | Phát hiện quyền mồ côi |
 Số sponsor inactive còn bảo trợ quyền active | Chậm bàn giao trách nhiệm |
 Tỷ lệ recertification đúng hạn | Đo việc xác minh nhu cầu định kỳ |
 Số grant quá expiry nhưng vẫn active | Lỗ hổng thực thi thời hạn |
 Thời gian xử lý Leaver đến khi verified | Độ trễ thu hồi quyền thực tế |
 Số quyền đặc biệt thiếu phê duyệt độc lập | Nguy cơ vượt thẩm quyền |
 Số yêu cầu revoke chờ remediation | Phát hiện lỗi downstream chưa xử lý |
 Số OAuth client/workload không có owner | Credential và tích hợp thiếu người chịu trách nhiệm |

KPI cần phản ánh chất lượng quyết định và độ bao phủ kiểm chứng, tránh ép sponsor xác nhận nhanh mà không có thông tin. SLA và ngưỡng cảnh báo được đặt theo độ nhạy và rủi ro.

## 15. Case study: hai sponsor trong một hợp đồng với B

Công ty A thuê công ty B tích hợp hệ thống vận chuyển trong bốn tháng. Hai kỹ sư B cần truy cập cổng hỗ trợ, còn một workload đồng bộ trạng thái đơn hàng. Dự án P42 do nhóm vận hành X sở hữu, dự án P51 do nhóm tích hợp Y sở hữu.

### 15.1. Phân công sponsor

| Danh tính | Nhu cầu ban đầu | Sponsor | Resource owner | Hạn |
|---|---|---|---|---|
 Kỹ sư U của B | Đọc log staging P42 | S-X | Owner X | 30 ngày |
 Kỹ sư V của B | Xem ticket P42 | S-X | Owner X | 30 ngày |
 OAuth client của B | Ghi trạng thái qua API P51 | S-Y | API Owner Y | Theo hợp đồng, có review |

Guest của U/V và workload cần danh tính riêng; workload không được chạy bằng tài khoản con người hoặc dùng chung credential nhiều đối tác.

### 15.2. Diễn tiến

| Thời điểm | Sự kiện | Trách nhiệm sponsor | Hành động IAM |
|---|---|---|---|
 Ngày 1 | Khởi động hợp đồng | S-X và S-Y xác nhận scope, thời hạn | Xác minh B, mở requests |
 Ngày 2 | U/V cần đăng nhập | S-X xác nhận người, dự án | OIDC/guest linking, MFA, quyền P42 |
 Ngày 3 | Client P51 bắt đầu dùng API | S-Y duyệt mục đích và scope | Client riêng, owner, credential bảo vệ |
 Ngày 14 | U cần hỗ trợ production | S-X cung cấp ticket và business need | Resource owner duyệt PAM/JIT có hạn |
 Ngày 25 | V chuyển sang P51 | S-X kết thúc P42; S-Y xin quyền P51 | Revoke P42, duyệt P51, đối soát |
 Ngày 40 | S-X chuyển công tác | Owner team chỉ định S-Z | Reassignment và review grants |
 Ngày 50 | U nghỉ việc ở B | S-Z xác nhận toàn bộ quyền cần gỡ | Disable U, revoke grants/phiên, kiểm chứng |
 Ngày 90 | P42 hoàn thành | S-Z đóng nhu cầu còn lại | Thu hồi P42; P51 vẫn hợp lệ |
 Ngày 120 | Hợp đồng kết thúc | S-Y xác nhận cả workload không còn cần | Offboard user/client, key và quyền đích |

### 15.3. Lỗi Mover: quyền cũ không được gỡ

Ngày 25, nếu IAM chỉ thêm role P51 cho V, quyền P42 vẫn tồn tại. S-X có trách nhiệm đánh dấu nhu cầu P42 kết thúc; S-Y đề nghị P51; resource owner Y phê duyệt; IAM cập nhật cả hai phía. Kiểm tra backend cần cho thấy V bị **DENY tại P42** và chỉ được phép hành động đã duyệt tại P51.

### 15.4. Lỗi sponsor mồ côi

Ngày 40, nếu chỉ thay tên S-X bằng S-Z mà không gửi danh sách grants, sponsor mới không thể review. S-Z cần biết U/V, role, hạn, app đích, hợp đồng và các quyền tạm. S-Z chỉ giữ quyền nào còn lý do hợp lệ; quyền production JIT đã hết hạn phải được xác minh không còn tồn tại.

### 15.5. Leaver người và Leaver hợp đồng khác nhau

Ngày 50, U rời B nhưng OAuth client P51 vẫn cần cho hợp đồng. IAM chỉ thu hồi quyền U theo scope. Ngày 120, khi toàn bộ hợp đồng kết thúc, phải thu hồi thêm client, key/secret, grant và các user còn liên quan. **Khóa guest không chứng minh đã offboard workload.**

## 16. Sai lầm thường gặp về sponsor

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
 Không có sponsor cho guest | Quyền không ai chịu trách nhiệm | Bắt buộc sponsor/owner theo scope |
 Sponsor là email nhóm vô chủ | Review không có người xác nhận | Team owner và người được ủy quyền rõ ràng |
 Sponsor tự yêu cầu, duyệt, cấp admin | Bỏ qua phân tách nhiệm vụ | Resource owner/Security duyệt độc lập |
 Chỉ lưu sponsor cấp user | Không biết ai sở hữu grants nhiều dự án | Ownership theo relationship/grant |
 Sponsor nghỉ việc mà grants vẫn active | Tài khoản mồ côi | Reassignment và recertification |
 Im lặng đồng nghĩa đồng ý gia hạn | Quyền cũ sống vô hạn | Escalation và expiry |
 Review chỉ dựa vào last login | Thiếu cơ sở nhu cầu và quyền thực tế | Review hợp đồng, scope, application grants |
 Tin toàn bộ group do IdP B gửi | Đối tác tự nâng quyền | Role mapping do A kiểm soát |
 Mover chỉ cấp quyền mới | Tích lũy quyền không còn dùng | So sánh quyền trước–sau, revoke cũ |
 Chỉ khóa IdP hoặc đóng ticket Leaver | Session/ACL còn sống | Revoke kỹ thuật, reconciliation |
 Workload không gắn hợp đồng/owner | API chạy sau khi hợp tác chấm dứt | Technical owner và business sponsor |
 Trạng thái applied được coi như verified | Báo thu hồi thành công dù app lỗi | Theo dõi kết quả ứng dụng đích |

## 17. Checklist triển khai sponsor lifecycle

### Joiner

- [ ] Sponsor nội bộ được chỉ định và đủ điều kiện theo hợp đồng/dự án.
- [ ] Có principal, đối tác, lý do, tenant, resource, action và expiry.
- [ ] Resource owner/approver có thẩm quyền quyết định entitlement.
- [ ] IdP/SSO được xác minh, guest hoặc workload liên kết danh tính ổn định.
- [ ] SSO, SCIM/JIT và authorization được kiểm soát như các lớp riêng.
- [ ] IAM ghi kết quả provisioning và thông báo trạng thái cho sponsor.

### Mover và review

- [ ] Sponsor nhận biết khi thay đổi người, hợp đồng, vai trò hoặc dự án.
- [ ] Quyền cũ được thu hồi trước/cùng lúc với việc cấp quyền mới.
- [ ] Sponsor mới được chỉ định khi sponsor cũ mất hiệu lực; có review chuyển giao.
- [ ] Access review trình bày quyền thực tế, sponsor, hợp đồng và resource owner.
- [ ] Có escalation và expiry khi sponsor không phản hồi.
- [ ] PAM/JIT và service account có owner, hạn và chính sách riêng.

### Leaver

- [ ] Tín hiệu Leaver có nguồn tin cậy và scope rõ.
- [ ] IAM chặn cấp quyền mới, gỡ group/grant và xử lý local principal.
- [ ] Session/token, quyền PAM và quyền chia sẻ tại ứng dụng đích được xử lý.
- [ ] Workload/client/credential còn liên quan được rà soát và thu hồi đúng lúc.
- [ ] Reconciliation chứng minh actual access đã được loại bỏ hoặc có ngoại lệ rõ.
- [ ] Audit được giữ an toàn và tuân thủ chính sách lưu trữ.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Sponsor A bảo trợ một kỹ sư B vào P42. Điều này có cho phép B tự nhận quyền admin mọi ứng dụng A?

**Trả lời:** Không. Sponsor xác nhận nhu cầu, còn quyền trên tài nguyên cần resource owner và policy phù hợp phê duyệt; API giới hạn role, tenant, project và thời hạn.

**Câu 2.** IdP B vẫn cho U đăng nhập dù hợp đồng A–B đã hết hạn. Có được cho U truy cập A không?

**Trả lời:** Không chỉ dựa vào SSO. Quyết định phải kiểm tra relationship, principal, grants và thời hạn tại A; Leaver cần xử lý phiên và quyền downstream.

**Câu 3.** Sponsor nghỉ việc, có thể chỉ thay sponsor_id sang quản lý mới và giữ toàn bộ grants?

**Trả lời:** Không nên tự động. Sponsor mới phải nhận trách nhiệm, đánh giá lại nhu cầu/quyền và xử lý grants không còn hợp lệ.

**Câu 4.** U chuyển từ P42 sang P51. Vì sao sponsor phải yêu cầu gỡ P42?

**Trả lời:** Để tránh quyền tích lũy và truy cập tồn dư. Mover cần thu hồi quyền cũ không còn cần, rồi cấp quyền mới theo phê duyệt đúng tài nguyên.

**Câu 5.** SCIM đã đặt user inactive. Có thể khẳng định toàn bộ quyền bị thu hồi ngay không?

**Trả lời:** Không. Session, access token và ACL tại hệ thống đích có thể còn. Cần thu hồi và đối soát theo khả năng thực tế.

**Câu 6.** Vì sao một guest có thể cần hai sponsor?

**Trả lời:** Hai dự án có owner, mục đích, hạn và phạm vi khác nhau. Gắn sponsor theo grant giúp thu hồi một dự án mà không làm mất quyền hợp lệ ở dự án khác.

**Câu 7.** OAuth client do vendor B vận hành có cần sponsor không?

**Trả lời:** Cần chủ thể chịu trách nhiệm nhu cầu kinh doanh/hợp đồng theo chính sách và technical owner cho credential. Workload có lifecycle riêng và phải được thu hồi khi tích hợp kết thúc.

**Câu 8.** Sponsor chỉ thấy tên user và lần đăng nhập cuối. Có đủ dữ liệu review không?

**Trả lời:** Chưa. Cần partner, hợp đồng, project, entitlement, resource owner, expiry, lịch sử phê duyệt và trạng thái quyền thực tế.

## Kết luận

**Sponsor** gắn quyền truy cập bên thứ ba với **nhu cầu công việc, người chịu trách nhiệm và thời hạn rõ ràng**. Trong **Joiner–Mover–Leaver**, sponsor khởi tạo nhu cầu, phối hợp cấp quyền; cập nhật thay đổi để gỡ quyền thừa; kích hoạt Leaver và theo dõi kết quả thu hồi. Sponsor phải phối hợp với **IdP, SSO, SCIM, RBAC/ABAC, PAM, service account, audit và access review**, đồng thời tôn trọng thẩm quyền phê duyệt và kiểm tra kỹ thuật của IAM và chủ tài nguyên. Khi có bàn giao sponsor, recertification và đối soát quyền thực tế, tổ chức giảm được tài khoản mồ côi và **quyền truy cập tồn dư** sau khi người dùng, dự án hoặc hợp đồng kết thúc.
