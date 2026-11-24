# Vendor identity: quản lý danh tính nhà cung cấp trong vòng đời IAM

## 1. Vendor identity là gì?

Trong **Identity and Access Management (IAM)**, **vendor identity** là tập hợp danh tính, thuộc tính tin cậy, quan hệ hợp đồng và quyền truy cập dùng để xác định **nhà cung cấp (vendor/supplier)** cùng những con người và hệ thống đại diện cho họ khi làm việc với tài nguyên của một tổ chức.

Nhà cung cấp có thể phát triển phần mềm, triển khai sản phẩm, bảo trì hạ tầng, vận hành dịch vụ thuê ngoài, cung ứng thiết bị, quản lý chuỗi cung ứng hoặc xử lý dữ liệu theo hợp đồng. Để hoàn thành công việc, vendor có thể cần truy cập cổng mua hàng, kho mã nguồn, hệ thống ticket, môi trường staging/production, dashboard hoặc API. Các quyền đó cần được quản lý xuyên suốt **Joiner–Mover–Leaver**, từ xác minh danh tính, tạo tài khoản và cấp quyền đến rà soát, thay đổi và thu hồi.

Một quan hệ vendor thường chứa ba lớp danh tính:

1. **Tổ chức cung ứng:** doanh nghiệp hoặc pháp nhân, hợp đồng, loại dịch vụ, trạng thái hợp tác và người chịu trách nhiệm nội bộ.
2. **Con người:** kỹ sư hỗ trợ, chuyên viên tư vấn, nhân viên triển khai, kiểm toán viên thuê ngoài, nhân sự nhà thầu phụ.
3. **Workload/tích hợp:** OAuth client, service account, workload identity, chứng thư số, tác vụ đồng bộ dữ liệu và pipeline CI/CD do vendor sử dụng.

**Ví dụ xuyên suốt:** Công ty A thuê B bảo trì hệ thống đơn hàng. B có hai kỹ sư được xem log trong staging, một kỹ sư trực sự cố có thể xin quyền production theo ticket và một API client gửi kết quả chẩn đoán cho A. Cả danh tính con người lẫn client đều phải gắn với hợp đồng và bị thu hồi khi không còn nhu cầu.

### Vendor, partner và external user khác nhau thế nào?

| Khái niệm | Trọng tâm | Ví dụ |
|---|---|---|
| External user | Một cá nhân bên ngoài cần truy cập hệ thống | Kỹ sư B đăng nhập cổng hỗ trợ A |
| Partner identity | Quan hệ tin cậy với tổ chức hợp tác, có thể cùng kinh doanh hoặc tích hợp | Đại lý B cùng phân phối sản phẩm A |
| **Vendor identity** | Quan hệ cung ứng dịch vụ/sản phẩm, quyền phát sinh từ hợp đồng và phạm vi công việc | B được A thuê bảo trì máy chủ |
| Workload identity | Danh tính tiến trình/ứng dụng, có thể do vendor hoặc nội bộ vận hành | Client B gọi API A |

Các khái niệm giao nhau nhưng không đồng nhất. Một nhân viên vendor là external user; một vendor có thể đồng thời là partner. Điểm nhấn của vendor identity là **quản lý rủi ro truy cập trong quan hệ cung ứng**, kể cả đặc quyền hỗ trợ kỹ thuật, nhà thầu phụ và credential máy.

## 2. Vì sao vendor identity phức tạp?

Với nhân sự nội bộ, hệ thống HR thường phát sự kiện tuyển dụng, chuyển vị trí và nghỉ việc. Với vendor, tổ chức A không luôn biết khi nhân viên B chuyển dự án, rời công ty hoặc mất quyền đại diện. Tín hiệu có thể đến từ mua sắm, pháp chế, hệ thống hợp đồng, sponsor, IdP của B hoặc email từ đầu mối vendor.

Những rủi ro phổ biến:

- **Thiếu nguồn Leaver kịp thời:** tài khoản vendor có thể còn hoạt động sau khi người dùng rời dự án.
- **Quyền kỹ thuật nhạy cảm:** nhân viên hỗ trợ đôi khi cần truy cập production, log có dữ liệu khách hàng hoặc công cụ triển khai.
- **Truy cập không thường xuyên:** tài khoản chỉ dùng khi sự cố xảy ra, dễ bị bỏ quên nhiều tháng.
- **Nhiều lớp nhà thầu:** B có thể thuê C thực hiện một phần công việc, nhưng C không mặc nhiên có quyền vào tài nguyên A.
- **Tích hợp máy chạy lâu dài:** API token, certificate và service account thường không nằm trong quy trình nhân sự.
- **Quyền phân tán:** một người có thể có group trên IdP, role trong SaaS, quyền kho mã và ACL trực tiếp ở ứng dụng.
- **Phạm vi hợp đồng thay đổi:** vendor còn active nhưng một dự án hoặc môi trường đã hết quyền.

**Mục tiêu IAM:** mọi quyền phải có lý do, owner, phạm vi, thời hạn và bằng chứng; khi mục đích chấm dứt, quyền phải được thu hồi và kiểm chứng trên hệ thống đích.

## 3. Mô hình dữ liệu cho vendor identity

### 3.1. Bản ghi cấp tổ chức

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| vendor_id | Khóa nội bộ ổn định | VEN-2084 |
| legal_entity_ref | Pháp nhân đã được xác minh | Hồ sơ doanh nghiệp B |
| relationship_id / contract_ref | Quan hệ hợp đồng tạo ra quyền | SUP-2026-093 |
| vendor_status | requested, active, suspended, offboarded... | active |
| sponsor / vendor owner | Người phía A chịu trách nhiệm | Trưởng nhóm vận hành |
| verified_vendor_contact | Đầu mối B được xác minh | Quản trị viên kỹ thuật B |
| resource_scope | Ứng dụng, dự án, môi trường, dữ liệu | staging / project-F1 |
| valid_from / expires_at | Khoảng thời gian quan hệ | Hết hạn 31/12/2026 |
| trust_profile | IdP, issuer, certificate hoặc client đã duyệt | OIDC issuer B |
| review_date | Ngày rà soát tiếp theo | Theo mức rủi ro |

**Vendor ID, tenant ID và IdP issuer là ba thực thể khác nhau.** Một vendor có thể có nhiều hợp đồng, nhiều tenant hoặc nhiều IdP; một IdP cũng có thể được nhiều tổ chức dùng chung. Cần quản lý ánh xạ tường minh, không suy danh tính tổ chức chỉ từ tên hiển thị hoặc đuôi email.

### 3.2. Bản ghi principal

Mỗi người hoặc workload cần có:

1. Principal ID nội bộ và loại danh tính (human/workload);
2. Định danh ổn định và nguồn xác thực đã kiểm tra;
3. Vendor ID, quan hệ/hợp đồng và membership tương ứng;
4. Sponsor, owner ứng dụng và người phê duyệt;
5. Role, entitlement, tenant/project/environment scope;
6. Ngày hết hạn, trạng thái active/suspended/revoked và lịch review;
7. Lịch sử tạo, cập nhật, truy cập và thu hồi.

Với **OIDC**, khóa liên kết user thường nên dựa trên cặp **(issuer, subject)** sau khi xác minh token. Với **SAML**, cần định danh ổn định được thỏa thuận và liên kết với issuer tin cậy. Email có thể đổi hoặc được tái sử dụng nên không đủ để ghép tài khoản tự động. Với workload, định danh có thể là OAuth client gắn với authorization server, chứng thư đã xác thực hoặc subject của workload federation.

### 3.3. Trách nhiệm các bên

| Vai trò | Trách nhiệm |
|---|---|
| Procurement / vendor manager | Xác minh quan hệ cung ứng, hợp đồng, thời hạn và đầu mối B |
| Business sponsor A | Xác nhận nhu cầu, bảo trợ tài khoản, yêu cầu thu hồi khi hết việc |
| Resource owner A | Phê duyệt quyền cụ thể trên ứng dụng và dữ liệu |
| IAM / Security A | Cấu hình tin cậy, policy, provisioning, kiểm soát rủi ro và audit |
| App owner A | Thực thi phân quyền và xác minh revoke tại hệ thống đích |
| Vendor admin B | Xác minh nhân sự B, báo thay đổi và vận hành theo thỏa thuận |
| Incident responder | Điều phối ngắt truy cập khi có nghi vấn hoặc sự cố |

Việc A ủy quyền cho B quản lý một số user không đồng nghĩa B được tự cấp quyền admin toàn cục. **Trần quyền và quyết định cho phép truy cập tài nguyên của A do A quản lý.**

## 4. Kiến trúc tin cậy trong truy cập vendor

Mỗi yêu cầu truy cập cần trả lời ba câu hỏi độc lập:

1. **Quan hệ hợp lệ?** Vendor, hợp đồng và phạm vi dịch vụ còn hiệu lực?
2. **Danh tính xác thực?** Con người hoặc workload chứng minh được danh tính qua nguồn được tin cậy?
3. **Hành động được phép?** Role, scope và các điều kiện của tài nguyên yêu cầu có khớp?

~~~mermaid
flowchart LR
    subgraph V["Nhà cung cấp B"]
      U["Kỹ sư B"] --> IDP["IdP B"]
      C["Workload/API client B"]
    end
    subgraph A["Tổ chức A"]
      SSO["SSO / cổng vendor / ZTNA"]
      API["API Gateway"]
      IAM["Vendor registry + IAM"]
      POL["RBAC / ABAC / PAM policy"]
      RES["Ứng dụng, log, hạ tầng"]
      AUD["Audit + access review"]
      SSO --> POL
      API --> POL
      POL --> IAM
      POL --> RES
      IAM --> AUD
      RES --> AUD
    end
    IDP -->|"OIDC hoặc SAML"| SSO
    C -->|"OAuth/mTLS khi phù hợp"| API
    OWN["Sponsor / Resource owner A"] -->|"Duyệt, review"| IAM
    SCIM["Hệ thống provisioning"] -->|"SCIM nếu có"| IAM
~~~

**IdP/SSO** phục vụ xác thực, **SCIM** có thể đồng bộ vòng đời bản ghi, **RBAC/ABAC** quyết định quyền, **PAM** kiểm soát đặc quyền, còn backend/resource server phải thực thi kết quả. Một token hợp lệ hoặc việc kết nối VPN thành công không tự tạo ra quyền vào mọi hệ thống.

## 5. Joiner: tiếp nhận nhà cung cấp và cấp quyền

Joiner diễn ra ở **cấp quan hệ vendor** trước, sau đó tới **từng human/workload principal**. Trình tự này cho phép IAM liên kết quyền với hợp đồng và chủ động thu hồi khi hợp đồng thay đổi.

### 5.1. Xác minh doanh nghiệp, hợp đồng và người đại diện

Trước khi mở truy cập, cần làm rõ:

- Vendor nào cung cấp dịch vụ, pháp nhân và đầu mối chính thức là ai?
- Công việc nào cần thực hiện, dữ liệu/tài nguyên nào được hợp đồng cho phép?
- Ai ở A là sponsor và resource owner?
- Có nhà thầu phụ không, và có được A phê duyệt không?
- Vendor sử dụng IdP, MFA, thiết bị và phương thức kết nối nào?
- Ai thông báo khi nhân viên nghỉ việc, đổi vai trò hoặc có sự cố?
- Truy cập có ngày bắt đầu và kết thúc rõ ràng không?

Thẩm định rủi ro chuỗi cung ứng có thể bổ sung điều kiện an ninh và riêng tư. Tuy nhiên, **vendor đã qua thẩm định không có nghĩa mọi nhân viên của họ đều được cấp quyền**; mỗi principal vẫn phải có nhu cầu và phê duyệt hợp lệ.

### 5.2. Yêu cầu cấp quyền có trách nhiệm

| Trường yêu cầu | Nội dung |
|---|---|
| Requester / sponsor | Ai yêu cầu và bảo trợ |
| Principal | Người hoặc workload cụ thể |
| Business justification | Hợp đồng, ticket, dự án hoặc hạng mục công việc |
| Resources | Ứng dụng, host, API, repository, môi trường |
| Permissions | Đọc log, ghi trạng thái, triển khai, quản trị... |
| Scope | Tenant, project, môi trường, loại dữ liệu |
| Validity | Thời điểm bắt đầu và hết hạn |
| Approval | Resource owner, phê duyệt bổ sung khi quyền nhạy cảm |
| Security conditions | MFA, thiết bị, ZTNA, PAM, ghi phiên nếu cần |

Ví dụ: B được quyền đọc log staging để xử lý ticket F42 trong 14 ngày. Không có căn cứ để tự cấp quyền production admin vô thời hạn.

### 5.3. Khởi tạo danh tính và cấu hình xác thực

Một số lựa chọn:

- **Federation OIDC/SAML:** nhân viên B xác thực qua IdP B; A kiểm tra issuer và token/assertion, duy trì local membership và chính sách quyền của mình.
- **Guest account tại A:** A quản lý tài khoản khách và invitation, áp dụng kiểm soát truy cập phù hợp.
- **SCIM/pre-provisioning:** bản ghi người dùng/nhóm được tạo, cập nhật và vô hiệu hóa qua kênh đồng bộ có kiểm soát.
- **Just-in-time (JIT) user provisioning:** tạo local user khi đăng nhập lần đầu, nhưng vẫn đòi hỏi sponsor, invitation hoặc điều kiện membership đã được duyệt.
- **Workload onboarding:** tạo riêng client, certificate hoặc workload identity có owner, scope và ngày review.

**JIT tạo tài khoản** khác với **JIT elevation cấp đặc quyền trong thời gian ngắn**. Cần chọn và ghi rõ cơ chế nào đang được sử dụng.

### 5.4. Kiểm thử trước khi mở truy cập

1. User B đọc đúng log staging được duyệt nhưng không đọc được production.
2. User khác từ cùng IdP B nhưng không có grant không tự nhận quyền.
3. Role viewer không thể cập nhật dữ liệu hoặc cấp quyền cho người khác.
4. Token sai issuer, audience, signature hoặc hết hạn bị từ chối.
5. Request chéo tenant/vendor bị từ chối ở backend.
6. Khi contract/grant hết hạn, mọi request mới phải bị từ chối theo chính sách.
7. API client chỉ gọi được endpoint với audience/scope và resource phù hợp.

## 6. Mover: quản lý thay đổi trong thời gian cung ứng

Mover có thể đến từ **thay đổi nhân sự, hợp đồng, dự án, đầu mối, IdP hoặc tích hợp**. Quan trọng nhất là tính lại nhu cầu quyền và thu hồi những quyền không còn phù hợp.

| Sự kiện | Quyền cần đánh giá lại | Xử lý |
|---|---|---|
 Kỹ sư B chuyển từ triển khai sang hỗ trợ | Repo/CI/CD và công cụ hỗ trợ | Gỡ quyền cũ, duyệt role mới |
 Một ticket khẩn cấp cần sửa production | Đặc quyền theo ticket | Cấp JIT/PAM có hạn và theo dõi phiên |
 Hợp đồng gia hạn nhưng thu hẹp scope | Quyền ngoài phạm vi mới | Cập nhật expiry đúng phần còn hiệu lực, thu hồi phần bị loại |
 B đổi nhà thầu phụ | Quyền của người/đơn vị cũ và mới | Offboard bên cũ, xác minh và duyệt bên mới |
 B đổi IdP hoặc signing certificate | Nguồn xác thực đã được A tin cậy | Thẩm định thay đổi, chuyển đổi có kiểm soát |
 Sponsor phía A rời vị trí | Ai tiếp tục chịu trách nhiệm? | Chỉ định owner mới và review các grants |
 B ngừng một API integration | Client/credential liên quan | Vô hiệu hóa client và key cũ |

**Không chỉ cộng thêm role:** Mover đúng phải kiểm tra quyền trước–sau, loại quyền cũ và kiểm chứng trạng thái trên hệ thống đích. Nếu kỹ sư B chuyển sang dự án F51, quyền dự án F42 không được tồn tại chỉ vì đã từng được phê duyệt.

Khi B đổi IdP, không tự ghép tài khoản mới với tài khoản cũ qua email. Phải xác minh yêu cầu từ đầu mối B đã được xác thực, đăng ký issuer/khóa mới, liên kết identity cũ–mới bằng bằng chứng đáng tin, kiểm tra membership và vô hiệu hóa trust cũ theo kế hoạch.

## 7. Leaver: thu hồi quyền khi công việc kết thúc

Leaver của vendor có ba phạm vi:

| Phạm vi | Cần thu hồi | Không nên ảnh hưởng |
|---|---|---|
 Một nhân viên B nghỉ việc | Guest/local principal, group, grants, session/token cá nhân | Các nhân viên B hợp lệ khác |
 Một tích hợp B ngừng hoạt động | OAuth client, API key, service account, cert, webhook, grants | Những tích hợp B vẫn hợp lệ |
 Toàn bộ hợp đồng hoặc vendor chấm dứt | Tất cả quyền phát sinh từ relationship, cả người và máy | Audit evidence/dữ liệu phải giữ theo chính sách |

### Quy trình Leaver có kiểm chứng

1. **Nhận và xác minh sự kiện:** từ vendor manager, hợp đồng, sponsor, IdP/SCIM hoặc incident; xác định đúng phạm vi.
2. **Chặn cấp quyền mới:** đặt principal hoặc relationship vào trạng thái suspended/revoked theo chính sách.
3. **Gỡ quyền ở IAM và ứng dụng đích:** role, group, SaaS ACL, repository, VPN/ZTNA, cloud IAM, dashboard, data share, quyền CI/CD.
4. **Xử lý session/token:** hủy session và refresh token nơi được hỗ trợ; với access token đã phát hành cần TTL ngắn, token introspection, kiểm tra trạng thái tại resource server hoặc cơ chế thu hồi phù hợp.
5. **Thu hồi credential máy:** disable client/service account, revoke API key/certificate, xoay secret dùng chung nếu cần.
6. **Ngăn tái cấp quyền ngoài ý muốn:** tránh sync SCIM trễ, JIT tự tạo lại user hoặc workflow cũ tái kích hoạt grants đã thu hồi.
7. **Đối soát:** so sánh trạng thái IAM với tài khoản và quyền thực tế trong ứng dụng, ghi lỗi còn tồn tại và bằng chứng hoàn thành.
8. **Xử lý dữ liệu:** trả, lưu hoặc xóa theo hợp đồng, chính sách và nghĩa vụ pháp lý; giữ audit trail cần thiết.

**Lưu ý:** Khóa tài khoản tại IdP vendor không tự làm mọi phiên hoặc JWT đang tồn tại tại A vô hiệu lập tức. SCIM deactivate cũng không đảm bảo các hệ thống ngoài phạm vi đồng bộ đã thu hồi quyền.

~~~mermaid
flowchart TD
    E["Sự kiện Leaver vendor"] --> S{"Phạm vi?"}
    S -->|"Một người"| U["Disable principal và user grants"]
    S -->|"Một workload"| W["Disable client và credential"]
    S -->|"Toàn bộ vendor/hợp đồng"| V["Suspend relationship và related grants"]
    U --> R["Xử lý session/token"]
    W --> R
    V --> R
    R --> A["Thu hồi ở hệ thống đích"]
    A --> C{"Đối soát đầy đủ?"}
    C -->|"Chưa"| F["Xử lý lỗi, kiểm tra lại"]
    F --> C
    C -->|"Rồi"| D["Lưu bằng chứng và đóng yêu cầu"]
~~~

## 8. Xác thực vendor: IdP, SSO và federation

### 8.1. OIDC và SAML

Nếu B có IdP riêng, A có thể nhận xác thực qua **OIDC** hoặc **SAML** theo quan hệ tin cậy đã đăng ký. Ứng dụng phía A cần kiểm tra những điều kiện liên quan đến giao thức:

- Với **OIDC**: chữ ký, issuer, audience, thời gian hiệu lực, nonce/flow binding khi áp dụng và ánh xạ cặp (issuer, subject) tới principal đã duyệt.
- Với **SAML**: chữ ký, issuer, audience, recipient/destination, điều kiện thời gian, InResponseTo/chống replay khi áp dụng.
- Với cả hai: định danh đối tác, chính sách session, xử lý trust rotation, điều kiện MFA và quyền được A phê duyệt.

Nếu IdP B gửi claim role mang giá trị admin, A **không tự động trao quyền admin**. Mọi role mapping phải theo danh sách ánh xạ được A kiểm soát và phải giới hạn tenant/project/contract.

### 8.2. MFA, ZTNA và quản lý phiên

MFA, ưu tiên cơ chế chống phishing ở vị trí nhạy cảm, giúp giảm rủi ro chiếm tài khoản. Có thể kết hợp điều kiện thiết bị, ngữ cảnh truy cập, mức độ rủi ro và ZTNA/VPN theo kiến trúc. Tuy nhiên **kết nối mạng nội bộ không đủ để cấp quyền toàn mạng**; ứng dụng và backend vẫn phải phân quyền theo tài nguyên.

Phiên vendor nên có thời hạn và điều kiện tái xác thực phù hợp với mức rủi ro. Quyền hỗ trợ production có thể được cấp theo ticket và timebox, sau đó tự thu hồi; không nên chuyển thành quyền admin thường trực.

## 9. Provisioning qua SCIM và kiểm soát sai lệch

**SCIM** là cơ chế quản lý bản ghi người dùng/nhóm qua API được chuẩn hóa; chỉ áp dụng khi các hệ thống thực sự hỗ trợ và có cấu hình tin cậy. SCIM khác với SSO và không thay thế kiểm tra quyền tại resource server.

| Sự kiện | Xử lý mong muốn | Kiểm soát |
|---|---|---|
 Create user | Tạo/liên kết user đúng vendor | Chống trùng, kiểm tra sponsor |
 Add group | Cấp grant theo mapping được duyệt | Không cho vendor tự nâng admin |
 Change attributes | Cập nhật thuộc tính hợp lệ | Xác minh nguồn và phạm vi |
 Remove group | Gỡ grant phụ thuộc | Kiểm tra ACL trong app |
 Deactivate user | Chặn tài khoản, kích hoạt revoke | Xử lý session và ứng dụng ngoài SCIM |
 Sync failure | Retry và cảnh báo | Reconciliation desired/actual state |

Ví dụ PATCH SCIM vô hiệu hóa user:

~~~http
PATCH /scim/v2/Users/7841 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "Replace", "path": "active", "value": false}
  ]
}
~~~

API provisioning phải xác thực nguồn, giới hạn quyền và kiểm tra kết quả tại hệ thống đích. Khi hợp đồng bị chấm dứt, chính sách IAM phải ngăn bản ghi từ nguồn đồng bộ cũ tái cấp quyền. **SCIM không tự hủy tất cả session, credential máy hoặc quyền ngoài phạm vi tích hợp.**

## 10. RBAC, ABAC và Zero Trust cho vendor

### 10.1. RBAC: vai trò theo công việc

Một role chung có tên vendor chỉ thể hiện phân loại nguồn người dùng, chưa đủ để cấp quyền an toàn. Nên thiết kế vai trò theo hành động và trách nhiệm.

| Vai trò minh họa | Hành động được phép | Giới hạn bổ sung |
|---|---|---|
| vendor_ticket_viewer | Xem ticket được gán | Vendor, project, hợp đồng |
| vendor_staging_operator | Đọc log và thao tác staging cho ứng dụng được duyệt | Chỉ staging và tài nguyên cụ thể |
| vendor_release_assistant | Hỗ trợ quy trình release | Không tự phê duyệt thay đổi nhạy cảm của mình |
| vendor_prod_support_jit | Thao tác production theo sự cố | Ticket, phê duyệt, thời hạn ngắn |
| vendor_api_reader | Đọc dữ liệu qua API | Audience, scope, tenant/resource |

Nguyên tắc **Separation of Duties (SoD)** rất quan trọng với release và thanh toán. Nếu quy trình yêu cầu hai người độc lập duyệt và triển khai, vendor không nên được phép tự tạo yêu cầu rồi tự phê duyệt và tự triển khai một thay đổi nhạy cảm.

### 10.2. ABAC: điều kiện theo quan hệ

**Attribute-Based Access Control (ABAC)** đánh giá thêm tình trạng vendor, hạn hợp đồng, membership, môi trường, tenant, dữ liệu, ticket và mức độ nhạy cảm. Mã giả:

~~~text
authorize(principal, request, context):
    if not context.authentication_valid: DENY
    if principal.status != "active": DENY

    vendor = load_vendor(principal.vendor_id)
    if vendor.status != "active": DENY

    relationship = load_relationship(vendor.id, request.project_id)
    if relationship.status != "active": DENY
    if now >= relationship.expires_at: DENY

    grant = load_effective_grant(principal, request.resource_id)
    if grant is missing: DENY
    if now >= grant.expires_at: DENY
    if request.action not in grant.actions: DENY
    if request.tenant_id != grant.tenant_id: DENY
    if request.environment not in grant.environments: DENY

    if request.requires_privilege:
        if not context.approved_jit_session: DENY

    ALLOW
~~~

Đây là logic minh họa. Trong thực tế cần xử lý policy conflict, nguồn thuộc tính đáng tin, hiệu lực thời gian, cách cache quyền và trạng thái khi thành phần IAM không khả dụng. Các API chứa dữ liệu nhạy cảm nên áp dụng **deny by default** khi thiếu bằng chứng cần thiết.

### 10.3. Bẫy cross-tenant và truy cập object trực tiếp

Giả sử B bảo trì dữ liệu dự án F42 còn C bảo trì F51. Nếu API chỉ kiểm tra role vendor_ticket_viewer mà không kiểm tra **ticket.project_id và vendor membership**, nhân viên B có thể thay ID trên URL để đọc ticket F51. Backend phải kiểm tra quyền trên chính **object/tài nguyên được yêu cầu**, không phụ thuộc vào việc giao diện đã ẩn link.

Trong tư duy **Zero Trust**, mỗi request được kiểm tra theo danh tính, trạng thái và ngữ cảnh thích hợp; người dùng không tự có quyền toàn mạng vì đã kết nối VPN, từng xác thực thành công hoặc có hợp đồng với tổ chức.

## 11. PAM và JIT elevation cho vendor hỗ trợ production

**Privileged Access Management (PAM)** tập trung quản lý quyền đặc biệt như truy cập máy chủ, tài khoản quản trị hoặc khả năng thao tác production. **Just-in-Time elevation** chỉ nâng quyền khi có yêu cầu hợp lệ và trong khoảng thời gian giới hạn.

### Luồng truy cập theo ticket

~~~mermaid
sequenceDiagram
    participant V as Kỹ sư vendor B
    participant P as Cổng hỗ trợ A
    participant O as Resource owner A
    participant PAM as PAM / JIT
    participant S as Production system
    V->>P: Yêu cầu xử lý INC-2048
    P->>O: Trình phạm vi, lý do, thời hạn
    O-->>P: Phê duyệt theo chính sách
    P->>PAM: Kích hoạt quyền tạm theo ticket
    PAM->>S: Thiết lập phiên/credential giới hạn
    V->>S: Thực hiện thao tác được phép
    S-->>PAM: Event và dấu vết phiên
    PAM->>S: Thu hồi quyền khi hết hạn/kết thúc
    PAM->>P: Xác nhận và bằng chứng
~~~

Các yếu tố vận hành:

1. Xác thực mạnh, kiểm tra user và vendor vẫn active.
2. Gắn yêu cầu với ticket, tài nguyên, hành động và lý do.
3. Phê duyệt bởi người đủ thẩm quyền; áp dụng nguyên tắc tối thiểu.
4. Hạn thời gian rõ ràng; credential không bị lộ trực tiếp khi hệ thống hỗ trợ.
5. Ghi log, giám sát hoặc recording theo chính sách an ninh và quyền riêng tư.
6. Tự thu hồi và kiểm tra lại khi phiên kết thúc hoặc ticket đóng.

Trường hợp khẩn cấp có thể cần **break-glass** được thiết kế trước với thời hạn, người chịu trách nhiệm, giám sát và hậu kiểm. Break-glass không phải lý do cấp admin thường trực cho vendor.

## 12. Workload và service account do vendor vận hành

Vendor có thể cần agent giám sát, đồng bộ dữ liệu, API nhận trạng thái hoặc pipeline CI/CD. Những tác vụ này không có người đăng nhập tại thời điểm chạy và cần **workload identity riêng** gắn với vendor, service owner, hợp đồng và mục đích.

### 12.1. OAuth 2.0 client credentials cho tích hợp máy

~~~mermaid
sequenceDiagram
    participant C as Workload B
    participant AS as Authorization Server
    participant API as API của A
    participant IAM as Vendor IAM/policy
    C->>AS: Client authentication + client_credentials
    AS-->>C: Access token (audience, scope, expiry)
    C->>API: HTTPS request + access token
    API->>API: Validate issuer/signature/audience/expiry
    API->>IAM: Check vendor, client, contract, tenant, scope
    IAM-->>API: ALLOW hoặc DENY
    API-->>C: Response
~~~

Token phải được xác thực đúng bởi resource server và client phải được liên kết với vendor hợp lệ. Chỉ đọc client_id do người gọi tự khai không phải xác thực. **OIDC ID token dùng cho xác thực người dùng, không thay thế access token khi gọi API.**

### 12.2. Credential quản lý thế nào?

- Tạo workload identity/client riêng theo vendor, ứng dụng, môi trường và mục đích; không chia sẻ chung giữa nhiều vendor.
- Ưu tiên phương thức xác thực máy phù hợp như private_key_jwt, mTLS, workload federation khi kiến trúc hỗ trợ; nếu phải dùng client secret, bảo vệ trong secret manager.
- Hạn chế scope/audience/TTL của access token và kiểm tra entitlement theo tài nguyên ở API.
- Không đưa secret, private key hoặc access token còn dùng được vào ticket, repository hay log.
- Gán owner, chu kỳ review và kế hoạch rotation, thay thế khẩn cấp, thu hồi.
- Khi Leaver, tìm cả client, service account, key, webhook, certificate trust và quyền CI/CD liên quan.

**mTLS không tự quyết định quyền nghiệp vụ.** Chứng thư được xác minh có thể chứng minh khả năng sở hữu khóa và quan hệ tin cậy được cấu hình; ứng dụng vẫn cần kiểm tra client thuộc vendor nào, có quyền trên dữ liệu gì và hợp đồng còn hiệu lực hay không.

### 12.3. Tài khoản hỗ trợ dùng chung

Tài khoản như vendor_support được nhiều kỹ sư sử dụng làm mất khả năng quy thao tác về một cá nhân. Nên ưu tiên danh tính từng người và PAM có dấu vết người yêu cầu/phiên. Nếu hệ thống cũ bắt buộc dùng một tài khoản kỹ thuật, cần vault credential, cấp phát theo phiên, rotation, log truy cập và kế hoạch thay thế dần.

## 13. Access review, audit và đối soát

### 13.1. Rà soát quyền theo rủi ro

Người rà soát cần đối chiếu quyền với **công việc hiện tại và điều kiện hợp đồng**, không chỉ kiểm tra tài khoản còn active:

- Vendor, hợp đồng và project còn hiệu lực không?
- Sponsor và resource owner có còn làm đúng vai trò không?
- Người dùng có còn thuộc nhóm vendor được phép, kể cả nhà thầu phụ?
- Quyền production, CI/CD, database, repo, cloud và SaaS có còn cần?
- Grant tạm thời có vô tình trở thành quyền lâu dài không?
- Client/workload nào không hoạt động, không có owner hoặc chưa được rotation/review?
- IAM và hệ thống đích có trùng trạng thái quyền không?

Chu kỳ review dựa trên độ nhạy: quyền đặc biệt cần điều kiện chặt hơn quyền đọc ticket ít nhạy cảm. Ngoài lịch định kỳ, những sự kiện như thay đổi hợp đồng, sponsor, danh sách nhân sự hoặc sự cố phải kích hoạt đánh giá khi thích hợp.

### 13.2. Audit evidence

| Loại sự kiện | Cần ghi |
|---|---|
 Vendor/contract onboarding | vendor_id, hợp đồng, sponsor, thời hạn, người xác minh |
 Tạo principal | ID, nguồn danh tính, owner, vai trò, scope |
 Thay federation/credential | Issuer/certificate/client reference trước–sau, người duyệt |
 Cấp/đổi/thu hồi quyền | Lý do, request/ticket, người duyệt, trạng thái trước–sau |
 Privileged access | Người thực hiện, ticket, phiên, tài nguyên, thời hạn |
 Request ứng dụng/API | Vendor, principal, tenant, resource, action, allow/deny |
 SCIM/reconciliation | Nguồn đồng bộ, kết quả, retry, sai lệch chưa xử lý |
 Leaver/access review | Sự kiện, hệ thống đã thu hồi, xác nhận, lỗi |

Audit log cần được bảo vệ tính toàn vẹn và hạn chế quyền đọc, có retention policy và correlation ID để nối yêu cầu IAM với hành động ở resource server. Không log mật khẩu, private key, access token hoặc dữ liệu cá nhân không cần thiết.

### 13.3. Desired state và actual state

Khi IAM gỡ một group, ứng dụng BI có thể vẫn giữ ACL độc lập. Khi vendor tắt user ở IdP, token còn hạn hoặc session đã mở có thể tiếp tục tồn tại. **Reconciliation** phát hiện sai khác giữa quyền dự kiến và quyền thực tế.

~~~text
for each vendor in registry:
    expected = compute_approved_access(
        vendor.status, active_contracts, approved_grants
    )
    actual = collect_access_from_target_systems(vendor.id)
    differences = compare(expected, actual)
    if differences:
        notify_responsible_owner(vendor.id, differences)
        remediate_and_verify(differences)
~~~

Đây là mã giả vận hành. Hệ thống không có API đọc quyền có thể đòi hỏi cơ chế kiểm tra khác và phải nêu rõ giới hạn độ bao phủ.

### 13.4. Chỉ số hữu ích

| Chỉ số | Điều cho thấy |
|---|---|
 Số user/vendor active sau khi hợp đồng hết hạn | Nguy cơ quyền truy cập tồn dư |
 Tỷ lệ principal có owner, scope và expiry | Mức độ đầy đủ của quản trị |
 Thời gian từ sự kiện Leaver đến xác minh revoke | Khả năng thu hồi theo SLA/rủi ro |
 Số grant quá hạn review | Điểm mù về nhu cầu truy cập |
 Số quyền production admin thường trực | Rủi ro đặc quyền bên thứ ba |
 Số workload không có owner hoặc credential overdue | Rủi ro danh tính máy |
 Số lỗi đồng bộ/quyền khác biệt còn mở | Chênh lệch desired và actual state |

Ngưỡng cảnh báo và lịch review do tổ chức xác định theo tính nhạy cảm và yêu cầu hợp đồng. Không mặc định một con số là phù hợp với mọi vendor.

## 14. Kịch bản thực tế: vendor bảo trì hệ thống thanh toán

Giả sử A vận hành nền tảng thanh toán; B cung cấp dịch vụ bảo trì trong sáu tháng. Hai kỹ sư B cần truy cập ticket và staging; một API client của B gửi kết quả chẩn đoán; đôi khi phải có phiên hỗ trợ production được phê duyệt.

| Mốc | Sự kiện | Xử lý IAM |
|---|---|---|
 Ngày 1 | Ký hợp đồng | Xác minh B, tạo vendor_id và contract_ref, gán sponsor, scope và expiry |
 Ngày 2 | Hai kỹ sư cần truy cập | Liên kết định danh OIDC/guest, MFA, cấp ticket/staging role theo dự án |
 Ngày 3 | API gửi kết quả chẩn đoán | Tạo client riêng, cấp scope ghi kết quả theo đúng tenant |
 Ngày 15 | Sự cố production | Cấp PAM/JIT theo ticket, resource owner duyệt, ghi sự kiện và timebox |
 Ngày 30 | Một kỹ sư B nghỉ việc | Thu hồi membership, role và session; xác minh tại hệ thống đích |
 Ngày 60 | B thay nhà thầu phụ | Xác minh/duyệt chủ thể mới và gỡ quyền cũ |
 Ngày 150 | Thu hẹp phạm vi hỗ trợ | Thu hồi quyền kho mã và CI/CD không còn cần |
 Ngày 180 | Hết hợp đồng | Suspend relationship, revoke user/workload, trust và grants phù hợp, đối soát |

**Ca kiểm thử 1:** Kỹ sư B có role staging_operator nhưng gửi request đọc production logs. Đăng nhập OIDC vẫn hợp lệ, nhưng backend phải **DENY** vì environment sai scope.

**Ca kiểm thử 2:** Trong sự cố đã duyệt, kỹ sư B nhận grant tạm cho host X. Hết phiên, PAM thu hồi grant trong khi tài khoản guest vẫn có thể tiếp tục xem các ticket được giao. Điều này cho phép thu hồi **đặc quyền tạm** mà không phải xóa mọi quyền hợp lệ.

**Ca kiểm thử 3:** Ngày 180, A đã khóa hai user nhưng vẫn để client chẩn đoán B hoạt động. Đây là Leaver chưa hoàn tất: một workload vẫn có quyền gọi API. IAM phải liên kết cả user và client với quan hệ vendor để truy vết và thu hồi đầy đủ.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
 Dùng chung tài khoản hỗ trợ cho mọi kỹ sư | Không quy trách nhiệm cho từng người | Account riêng, MFA, PAM session |
 Cấp admin vĩnh viễn để tiện xử lý sự cố | Quyền đặc biệt tồn dư | JIT elevation theo ticket, hết hạn tự động |
 Tin email domain là đủ để xác định vendor | Ghép nhầm danh tính và vượt phê duyệt | Vendor ID và nguồn danh tính đã xác minh |
 Tin role do IdP vendor tự gửi là quyền admin tại A | Vendor có thể tự nâng quyền | Role mapping do A quản lý |
 Chỉ xử lý Leaver ở IdP/SCIM | Session, token và ACL còn tồn tại | Revoke xuyên hệ thống và reconciliation |
 Quên API client, khóa và service account | Tích hợp máy vẫn chạy sau hợp đồng | Workload identity có owner và expiry |
 Không kiểm tra tenant/resource trên backend | Truy cập chéo khách hàng | ABAC scope ở điểm thực thi |
 Bỏ qua nhà thầu phụ | Chủ thể chưa được duyệt vẫn vào hệ thống | Xác minh và phê duyệt subcontractor |
 Để nguồn đồng bộ cũ tái kích hoạt user | Quyền đã thu hồi quay lại | Kiểm tra partner/contract state trước provisioning |
 Xóa sạch audit khi kết thúc hợp đồng | Không điều tra/đối soát được | Retention đúng hợp đồng và chính sách |

## 16. Checklist triển khai

1. Vendor có danh tính tổ chức ổn định, pháp nhân/đầu mối được xác minh, sponsor và hợp đồng hợp lệ.
2. Mỗi human/workload có principal riêng, owner, scope, trạng thái và hạn sử dụng.
3. Joiner yêu cầu tài nguyên, mục đích, phê duyệt và điều kiện bảo mật cụ thể.
4. Federation OIDC/SAML hoặc guest access được cấu hình và kiểm tra xác thực đúng giao thức.
5. Quyền RBAC/ABAC giới hạn tenant, dự án, môi trường và trạng thái hợp đồng tại backend.
6. PAM/JIT được áp dụng cho tác vụ đặc quyền theo rủi ro.
7. Credential API/service account được bảo vệ, review, rotation và có khả năng revoke.
8. Mover đánh giá quyền trước–sau khi đổi nhân sự, IdP, hợp đồng hoặc hạng mục.
9. Leaver thu hồi user, workload, session, token và quyền ứng dụng đích; có kiểm chứng.
10. Access review, audit, SCIM monitoring và reconciliation phát hiện quyền tồn dư.

## 17. Tự kiểm tra

**Câu 1:** B có hợp đồng active và nhân viên B đăng nhập thành công qua SSO. Có thể cấp quyền production admin không?

**Trả lời:** Chưa. Phải có nhu cầu cụ thể, resource owner phê duyệt, scope, thời hạn và kiểm soát rủi ro; có thể dùng PAM/JIT thay quyền admin thường trực.

**Câu 2:** SCIM đã vô hiệu hóa một kỹ sư. Điều đó có nghĩa mọi quyền của người ấy đã bị thu hồi?

**Trả lời:** Không. Phải kiểm tra session/token, grant tại ứng dụng đích, ACL và hệ thống ngoài SCIM; đối soát kết quả.

**Câu 3:** Vì sao không dùng cùng một OAuth client cho hai vendor?

**Trả lời:** Dùng chung làm mờ trách nhiệm, quyền và nhật ký sử dụng, đồng thời khó thu hồi chọn lọc khi chỉ một vendor kết thúc hợp đồng. Cần client và scope riêng theo quan hệ.

**Câu 4:** Một vendor viewer thay ticket ID để đọc ticket khách hàng khác. Kiểm soát nào ngăn sự cố?

**Trả lời:** Backend phải kiểm tra đồng thời principal, vendor membership, project/tenant ownership, entitlement và trạng thái hợp đồng cho **từng tài nguyên**, không chỉ vai trò viewer.

**Câu 5:** Vendor B đổi nhà thầu phụ từ C sang D, xử lý IAM thế nào?

**Trả lời:** Xác minh D được phép tham gia và danh tính người thực hiện, sponsor/resource owner phê duyệt quyền mới; thu hồi quyền C không còn hợp lệ và xác minh tại hệ thống đích.

## Kết luận

**Vendor identity** kết nối quản lý danh tính của **nhà cung cấp, con người và workload** với phạm vi quan hệ cung ứng. Mô hình **Joiner–Mover–Leaver** giúp kiểm soát việc xác minh và cấp quyền ban đầu, thay đổi nhiệm vụ, gia hạn hoặc thu hẹp hợp đồng, rồi thu hồi khi không còn nhu cầu. Phối hợp **IdP, SSO, SCIM, RBAC/ABAC, PAM, service account, access review, audit và reconciliation** giúp tổ chức kiểm soát truy cập bên thứ ba, giảm quyền tồn dư và có bằng chứng rõ ràng khi hợp đồng hoặc hoạt động hỗ trợ kết thúc.
