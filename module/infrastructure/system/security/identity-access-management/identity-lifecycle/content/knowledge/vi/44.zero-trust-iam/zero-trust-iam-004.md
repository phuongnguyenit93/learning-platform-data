# Assume breach — Thiết kế IAM với giả định có thể đã bị xâm nhập

> **Chương:** Zero Trust IAM  
> **Bài học:** Assume breach (giả định có xâm nhập)  
> **Phạm vi module:** Quản lý vòng đời danh tính và truy cập trong IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thay đổi vai trò và thu hồi. Bài học kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau khi học, người học có thể:

1. Giải thích **Assume breach** là nguyên tắc thiết kế và vận hành của Zero Trust, không phải kết luận rằng hệ thống chắc chắn đang bị tấn công.
2. Phân tích tác động khi một **danh tính, phiên SSO, access token, credential của workload hoặc thiết bị** bị chiếm quyền.
3. Thiết kế kiểm soát ngăn kẻ tấn công dùng một danh tính để di chuyển ngang, nâng quyền và truy cập lan rộng sang các tài nguyên khác.
4. Áp dụng kiểm soát IAM trong **Joiner–Mover–Leaver**, bao gồm quyền tồn dư, tài khoản mồ côi và token còn hiệu lực sau thu hồi.
5. Phác thảo quy trình **phát hiện → xác minh sự cố → khoanh vùng → thu hồi → phục hồi → cải tiến**, có bằng chứng kiểm toán và mốc thời gian.
6. Đề xuất kiểm thử và chỉ số để chứng minh khả năng giới hạn **blast radius** (phạm vi ảnh hưởng) và rút ngắn thời gian kẻ tấn công có thể dùng danh tính bị xâm nhập.

## 2. Hiểu đúng nguyên tắc Assume breach

Zero Trust thường được mô tả qua ba định hướng bổ trợ nhau:

- **Verify explicitly:** xác minh bằng chứng và chính sách thích hợp khi truy cập.
- **Use least privilege access:** cấp quyền hẹp nhất đủ cho công việc, giới hạn theo hành động, tài nguyên, phạm vi và thời gian.
- **Assume breach:** thiết kế như thể một hoặc nhiều thành phần có thể bị vượt qua, từ đó **giảm phạm vi ảnh hưởng, làm khó di chuyển ngang, phát hiện bất thường và hỗ trợ phục hồi**.

Assume breach không bảo rằng mọi người dùng đều xấu hoặc mọi request phải bị từ chối. Đây là tư duy kiểm soát thiệt hại: **nếu một mắt xích đáng tin đã thất bại, hệ thống còn những lớp bảo vệ nào?**

Ví dụ: nhân viên Phương đã đăng nhập qua IdP, có MFA và access token hợp lệ. Nếu trình duyệt hoặc thiết bị của Phương bị chiếm quyền, bên tấn công có thể lợi dụng phiên đã xác thực. Không có một dấu hiệu nào bảo đảm toàn bộ các request tiếp theo đều do Phương thực hiện. Thiết kế IAM tốt phải hạn chế những gì phiên đó có thể làm, phát hiện hành vi bất thường và cho phép vô hiệu hóa truy cập khi có bằng chứng rủi ro.

### Giả định khác với phát hiện sự cố

| Khái niệm | Ý nghĩa | Câu hỏi điều hành |
|---|---|---|
| **Assume breach** | Đặt giả định mất một hoặc nhiều lớp bảo vệ khi thiết kế | Nếu token của nhân viên bị đánh cắp, có thể truy cập những gì? |
| **Threat modeling** | Mô hình hóa tài sản, đường tấn công và biện pháp kiểm soát | Đường nào cho phép từ một tài khoản Support tới dữ liệu Finance? |
| **Detection** | Tìm tín hiệu thực tế có thể phản ánh hành vi bất thường | Vì sao một service account bắt đầu dùng API chưa từng gọi? |
| **Incident response** | Điều tra, khoanh vùng, xử lý và phục hồi một sự cố nghi ngờ/đã xác nhận | Cần thu hồi phiên/key nào và làm sao chứng minh đã chặn? |
| **Business continuity** | Duy trì hoặc khôi phục hoạt động cần thiết trong điều kiện suy giảm | Nếu IdP/PDP gặp sự cố khi đang khoanh vùng, quy trình có còn an toàn? |

Mục tiêu không phải đạt “không thể bị xâm nhập” mà là **không phụ thuộc vào một điểm tin cậy duy nhất** và giảm khả năng một sự cố cục bộ trở thành sự cố diện rộng.

## 3. Danh tính là tài sản có thể bị lợi dụng

Trong một môi trường hiện đại, nhiều loại bằng chứng có thể được dùng để đại diện cho danh tính:

| Đối tượng có thể bị xâm nhập | Tình huống minh họa | Rủi ro đối với IAM |
|---|---|---|
| **Mật khẩu/yếu tố xác thực** | Lộ thông tin đăng nhập, lừa xác thực, khôi phục tài khoản bị lạm dụng | Đăng nhập trái phép, chiếm phiên |
| **Phiên trình duyệt/SSO** | Cookie hoặc phiên ứng dụng bị chiếm | Truy cập tiếp mà không cần thực hiện lại bước xác thực ban đầu |
| **OAuth access token/refresh token** | Token bị lộ qua cấu hình, log hoặc thiết bị | Gọi API với quyền của chủ thể; refresh token có thể kéo dài quyền |
| **Tài khoản nội bộ có quyền cao** | Admin workstation hoặc credential bị xâm nhập | Thay đổi quyền, vô hiệu hóa kiểm soát, truy cập nhiều hệ thống |
| **Service account/workload identity** | Secret pipeline bị lộ, workload được chạy ở môi trường không tin cậy | Truy cập tự động quy mô lớn, khó phân biệt với job hợp lệ |
| **API key, PAT, SSH key, chứng chỉ** | Credential lâu ngày không luân chuyển | Đường truy cập không qua phiên SSO hoặc MFA của con người |
| **Danh tính bên thứ ba/đối tác** | Đối tác bị xâm nhập nhưng quyền vẫn mở | Vượt ranh giới tổ chức bằng một kết nối được cấp phép |

**Xác thực thành công không chứng minh máy hoặc phiên vẫn an toàn mãi mãi.** Ngược lại, một lần yêu cầu bất thường cũng chưa đủ kết luận chắc chắn có xâm nhập. Cần kết hợp bằng chứng, phân loại rủi ro và quy trình xác minh trước khi đưa ra biện pháp tương xứng.

### Khả năng của kẻ tấn công phụ thuộc quyền hiệu lực

Giả sử một tài khoản có:

- Quyền đọc các ticket thuộc tenant A;
- Quyền xuất dữ liệu khách hàng trên mọi tenant do ngoại lệ sáu tháng trước;
- Quyền quản trị cloud production vì từng hỗ trợ sự cố;
- Quyền tạo token cho một service account chung.

Khi phiên của tài khoản đó bị chiếm, “blast radius” không còn chỉ là ticket của tenant A. Các **quyền tồn dư và đường nâng quyền gián tiếp** có thể mở ra dữ liệu và hệ thống khác.

Vì thế, Assume breach đặt câu hỏi: **Nếu một danh tính bị mất quyền kiểm soát, các quyền trực tiếp, quyền kế thừa, phiên và ủy quyền nào sẽ làm sự cố lan rộng?**

## 4. Mô hình đường tấn công để giới hạn phạm vi ảnh hưởng

Một chuỗi sự cố minh họa:

1. Bên tấn công có được phiên của tài khoản nhân viên Support.
2. Sử dụng phiên để truy cập API hợp lệ và xem dữ liệu trong phạm vi hiện có.
3. Tìm thấy quyền cũ cho phép export dữ liệu trên phạm vi rộng hoặc tham gia nhóm có quyền quản trị.
4. Dùng quyền đó để lấy thêm credential hoặc truy cập hệ thống khác.
5. Tạo quyền mới, service principal mới hoặc token có thời hạn dài để duy trì truy cập.
6. Thực hiện truy vấn bất thường, thay đổi dữ liệu hoặc lấy dữ liệu ngoài phạm vi công việc.

Bài học cần rút ra là **phá chuỗi từ nhiều điểm**, thay vì trông chờ duy nhất vào kiểm tra đăng nhập ở bước 1.

| Giai đoạn rủi ro | Kiểm soát danh tính/quyền phù hợp | Bằng chứng cần quan sát |
|---|---|---|
| Phiên bị chiếm | Xác thực chống phishing, bảo vệ phiên, thiết bị được quản trị, phát hiện phiên bất thường | Dấu hiệu phiên/tokens dùng lệch thói quen, xác thực mới hoặc device risk |
| Sử dụng quyền đã có | Scope nhỏ, kiểm tra action/resource/tenant ở API, hạn chế xuất dữ liệu | Access decision, request volume, tài nguyên được truy cập |
| Mở rộng sang ứng dụng khác | Phân đoạn quyền theo ứng dụng, audience của token, giới hạn kết nối và tenant | Cross-app access, token audience mismatch, denied attempts |
| Nâng quyền | JIT/PAM, SoD, workflow phê duyệt, tách admin identity | Sự kiện role grant, elevation, tạo API key, thay đổi IAM policy |
| Duy trì quyền | Quản trị vòng đời token/key/service account, phát hiện principal mồ côi | Token được tạo mới, credential rotation, thay đổi owner |
| Che giấu/tiếp tục khai thác | Log độc lập, bảo vệ quyền sửa/xóa audit, giám sát bất thường | Khoảng trống log, thay đổi cấu hình giám sát, tăng số lần bị từ chối |

**Di chuyển ngang (lateral movement)** trong IAM không chỉ diễn ra giữa máy chủ. Một tài khoản có quyền xuyên SaaS, cloud, repository và API có thể đi qua nhiều hệ thống bằng quyền liên kết, delegation hoặc credential. Mỗi ranh giới phải có điều kiện truy cập và khả năng kiểm toán riêng.

## 5. Kiến trúc nhiều lớp: mất một lớp vẫn còn lớp khác

~~~mermaid
flowchart LR
    A["Người dùng / workload"] --> B["Xác thực IdP, MFA, workload identity"]
    B --> C["Phiên / token giới hạn audience và TTL"]
    C --> D["PEP: Gateway / API / Proxy"]
    D --> E{"PDP: subject + action + resource + context"}
    E -->|"Allow"| F["Tầng ứng dụng: tenant, ownership, SoD"]
    E -->|"Deny / step-up"| X["Từ chối / yêu cầu bằng chứng bổ sung"]
    F --> G["Dữ liệu và dịch vụ được phân đoạn"]
    F -->|"Không đủ quyền"| X
    H["JML / HR / hợp đồng / IdP / SCIM"] --> E
    H --> C
    I["Rủi ro phiên, thiết bị, workload"] --> E
    D --> L["Audit / detection"]
    E --> L
    F --> L
    L --> M["Incident response / revoke / containment"]
    M --> H
    M --> C
    M --> D
~~~

Các lớp có vai trò khác nhau:

- **IdP/SSO** giúp quản trị xác thực; thành công ở IdP không tự động cho phép mọi thao tác tại ứng dụng.
- **Access token** cung cấp thông tin về phạm vi hoặc quyền do bên phát hành cấp; phía API vẫn cần kiểm tra chữ ký hoặc introspection, issuer, audience, thời hạn và chính sách với tài nguyên.
- **PEP/PDP** kiểm tra điều kiện quyết định truy cập; phía backend vẫn phải thực thi quyền ở cấp dữ liệu thực tế khi gateway chưa có đủ thuộc tính.
- **Vòng đời JML và SCIM** giúp cập nhật tài khoản/quyền; cần xử lý độ trễ và thất bại đồng bộ.
- **Telemetry và incident response** hỗ trợ xác định truy cập đang diễn ra, ra quyết định khoanh vùng và chứng minh việc thu hồi.

NIST SP 800-207 mô tả các vai trò Policy Enforcement Point (PEP), Policy Decision Point (PDP) và Policy Administrator (PA) trong kiến trúc Zero Trust. Vị trí triển khai có thể thay đổi: PDP có thể tập trung hoặc nằm trong dịch vụ; một ứng dụng có thể có nhiều điểm thực thi bổ sung nhau.

### Bốn ranh giới nên kiểm tra độc lập

1. **Ranh giới danh tính:** ai là subject, còn active không, ai chịu trách nhiệm?
2. **Ranh giới phiên và ứng dụng:** credential này dành cho API nào, phạm vi và tuổi của token là bao nhiêu?
3. **Ranh giới tài nguyên:** action nào trên tenant, project, record hoặc dữ liệu nào?
4. **Ranh giới đặc quyền và quản trị:** ai có thể thay đổi IAM policy, phát hành credential hoặc tắt logging?

Nếu một nhân viên đọc được ticket hợp lệ nhưng không được gọi API export dữ liệu ngoài tenant, sự cố có thể bị giữ trong phạm vi nhỏ hơn. Nếu nhân viên đồng thời có quyền sửa chính sách IAM và tắt logging, ranh giới đã bị xóa bỏ.

## 6. Các kỹ thuật giới hạn blast radius qua IAM

### 6.1. Quyền tối thiểu phải đo trên quyền hiệu lực

Tách **role**, **permission**, **resource scope** và **thời hạn**. Một danh tính có thể có role support_agent nhưng vẫn kế thừa quyền admin từ nhóm cũ. Tính toán **effective permissions** cần xem:

- Direct grant và group/role kế thừa;
- Resource policy hoặc delegation;
- Quyền trong IdP, SaaS, cloud, database và ứng dụng cục bộ;
- Quyền tạm thời/JIT còn hiệu lực;
- Token/phiên phát hành trước khi role thay đổi.

Giới hạn theo **need-to-know**, **Separation of Duties (SoD)** và **time-bound access** nhằm giảm giá trị của credential nếu bị lấy cắp. Đối với thao tác đặc quyền, ưu tiên Just-in-Time (JIT), Just-Enough-Administration (JEA) và Privileged Access Management (PAM) theo khả năng hệ thống.

### 6.2. Phân đoạn theo tài nguyên và hành động

Cùng một tài khoản finance_analyst không nên được đọc hóa đơn của mọi pháp nhân. Chính sách cần ràng buộc tenant, business unit, dữ liệu nhạy cảm và action cụ thể.

~~~text
ALLOW invoice.read IF
    subject.status == active
    AND subject.hasRole("finance_analyst")
    AND subject.tenantId == resource.tenantId
    AND resource.businessUnit IN subject.approvedBusinessUnits
    AND context.meetsRequiredAssurance
ELSE DENY

ALLOW payment.approve IF
    subject.status == active
    AND subject.hasRole("finance_approver")
    AND subject.id != resource.createdBy
    AND subject.tenantId == resource.tenantId
    AND context.stepUpSatisfied
ELSE DENY
~~~

Đây là pseudocode mô tả quyết định chính sách, không phải cấu hình triển khai. Thuộc tính như resource.tenantId, createdBy phải đến từ **nguồn backend đáng tin**, không dựa vào header client tự khai báo. Nếu tài khoản analyst bị chiếm, các điều kiện vẫn ngăn nhiều hành động ngoài scope, ngay cả khi đăng nhập ban đầu hợp lệ.

### 6.3. Tách danh tính quản trị và công việc thường ngày

Một kỹ sư có thể cần tài khoản công việc để đọc tài liệu và tài khoản/phiên quản trị riêng cho vận hành production. Giảm quyền của môi trường làm việc thông thường để một sự cố trên email hoặc trình duyệt không ngay lập tức thành đặc quyền admin.

Với quyền cao:

- Chỉ nâng quyền theo ticket/justification và thời hạn được phê duyệt.
- Giới hạn hành động và tài nguyên cụ thể thay vì “cloud admin tất cả”.
- Yêu cầu xác thực tăng cường phù hợp, kiểm tra trạng thái thiết bị và SoD.
- Ghi nhận elevation, thao tác nhạy cảm và mốc kết thúc.
- Có cơ chế thu hồi khẩn cấp và kiểm thử với phiên/token đã nâng quyền.

**Break-glass** dành cho trường hợp khẩn cấp không thể dùng đường thông thường, cần bảo vệ credential, phân quyền owner, kiểm toán và rà soát riêng. Không biến break-glass thành tài khoản dùng hằng ngày.

### 6.4. Ranh giới mạng và thiết bị là các lớp bổ sung

Segmentation, mTLS, service mesh và bảo vệ endpoint giúp giảm đường đi của sự cố. Tuy nhiên, một service đã xác thực trong cùng cluster vẫn có thể gọi API sai tenant nếu thiếu authorization. **Mạng nội bộ không phải giấy phép dữ liệu**; thiết bị compliant cũng không tự động có quyền quản trị.

## 7. Assume breach trong vòng đời Joiner–Mover–Leaver

Nếu vòng đời quản lý yếu, một sự cố có thể khai thác **danh tính chưa xác minh, quyền tích lũy hoặc quyền tồn dư sau khi rời đi**.

| Giai đoạn | Giả định rủi ro | Biện pháp chủ động | Dấu hiệu kiểm chứng |
|---|---|---|---|
| **Joiner** | Tài khoản mới được tạo sai người/không rõ owner; cấp quyền quá rộng ngay từ đầu | Xác minh danh tính và hợp đồng; cấp quyền chuẩn tối thiểu; MFA; thời hạn cho nhà thầu; phê duyệt ngoại lệ | Nguồn Joiner, subject ID, owner, thời điểm hiệu lực, quyền ban đầu |
| **Mover** | Quyền cũ được giữ sau chuyển bộ phận, token cũ còn được phép gọi API | Reconcile desired–actual, thu hồi role/grant cũ, kiểm tra token/phiên, xử lý SoD | Diff quyền trước/sau, kết quả thực thi tại ứng dụng, mốc thu hồi |
| **Leaver** | User bị disable tại IdP nhưng còn local account, API key, refresh token hoặc quyền ứng dụng | Revoke sessions/tokens, deprovision, xoay key, chuyển owner automation, đối soát tài khoản đích | Thời gian từ Leaver đến khi không còn đường truy cập, lỗi chưa giải quyết |
| **Đánh giá định kỳ** | Quyền mồ côi, principal không owner, ngoại lệ không hết hạn | Access review theo rủi ro, rà soát quyền hiệu lực và quyền chưa sử dụng | Quyết định keep/revoke, người phê duyệt, bằng chứng hoàn tất |

### 7.1. Joiner: giảm thiệt hại từ ngày đầu tiên

Một nhà thầu có hợp đồng 30 ngày cần tài khoản riêng, sponsor, ngày kết thúc, phạm vi dự án và quyền chỉ cho những công cụ cần thiết. Tránh dùng lại tài khoản của người tiền nhiệm hoặc cấp quyền admin “tạm thời” mà không có ngày hết hạn.

Với tài khoản quyền cao mới, xác thực danh tính mạnh, kiểm tra thiết bị và phê duyệt theo nhiều cấp có thể cần thiết tùy rủi ro. Giữ **subject ID ổn định** để truy vết khi email hoặc tên hiển thị thay đổi.

### 7.2. Mover: thời điểm dễ có quyền chồng chéo

Giả sử Hòa chuyển từ Support sang Finance lúc 09:00. IdP đã gỡ nhóm Support lúc 09:01 nhưng ứng dụng CRM chưa nhận bản cập nhật SCIM, còn access token cấp lúc 08:50 hết hạn lúc 10:50.

Nếu CRM tin hoàn toàn claim role trong token cũ, Hòa vẫn có thể gọi các API Support trong khoảng thời gian đó. Khi xem xét Assume breach, không chỉ hỏi “có tạo request SCIM chưa?”, mà hỏi:

- **Quyền cũ còn sử dụng được đến khi nào?**
- Có thể chặn ngay bằng cập nhật phiên, policy version, kiểm tra quyền hiện tại hoặc phương án khác không?
- Có đường truy cập thứ cấp qua grant trực tiếp hoặc API key cá nhân không?
- Nếu CRM SCIM lỗi, ai nhận cảnh báo và xử lý?
- Hành động nào phải bị chặn ngay vì chứa dữ liệu nhạy cảm?

Một khoảng chuyển giao được phê duyệt có thể hợp lệ, nhưng phải có **scope, lý do và mốc hết hạn rõ ràng**, kèm kiểm soát SoD.

### 7.3. Leaver: thu hồi phải được xác nhận tại tài nguyên

Người rời tổ chức có thể vẫn nắm giữ:

- Phiên SaaS hoặc IdP chưa kết thúc;
- Refresh token hoặc access token còn hạn;
- Local account riêng không đồng bộ với IdP;
- API key/PAT/SSH key hoặc chứng chỉ do cá nhân tạo;
- Chia sẻ file, delegation, cloud role hoặc quyền phê duyệt;
- Script tự động chạy bằng service account dùng chung.

Quy trình phải **chặn đăng nhập mới, xử lý phiên và credential, vô hiệu hóa quyền ở từng ứng dụng, thu hồi hoặc chuyển giao automation hợp lệ**, đối soát các đích và kiểm thử quyền còn tồn dư. Nếu cần lưu hồ sơ phục vụ pháp lý/nghiệp vụ, thực hiện theo chính sách bảo quản dữ liệu thay vì xóa mọi dấu vết.

**Quyền đã thu hồi ở hệ thống quản trị không đồng nghĩa mọi request đều bị chặn tức thời.** Trong Assume breach, đó chính là một khoảng nguy cơ phải đo và có biện pháp giảm thiểu.

## 8. Phiên và token: khi bằng chứng từng đúng có thể bị lạm dụng

### 8.1. Phân biệt ba loại bằng chứng thông dụng

| Bằng chứng | Mục đích thường gặp | Điểm cần lưu ý khi bị lộ |
|---|---|---|
| **ID token (OIDC)** | Cung cấp phát biểu về xác thực cho client | Không dùng mặc định thay access token để gọi API |
| **OAuth 2.0 access token** | Cho phép resource server đánh giá quyền truy cập API theo audience/scope | Bearer token có thể bị sử dụng trái phép nếu bị lộ; API phải xác minh và kiểm tra AuthZ |
| **Refresh token** | Xin access token mới trong phiên/ủy quyền tương ứng | Nếu bị chiếm và không được thu hồi, có thể kéo dài khả năng lấy access token mới |

JWT access token tự chứa có thể được chấp nhận cho tới khi hết hạn nếu API chỉ kiểm tra chữ ký và thời gian. **Disable user tại IdP không tự động làm mọi access token đã phát hành mất hiệu lực.** Khả năng thu hồi phụ thuộc thiết kế: introspection, danh sách phiên bị thu hồi, token version/claim age, sự kiện thay đổi quyền hoặc tra cứu trạng thái hiện tại ở những tài nguyên quan trọng.

### 8.2. Giới hạn rủi ro khi token bị đánh cắp

Áp dụng kết hợp tùy mô hình tin cậy:

1. **Giới hạn tuổi và phạm vi:** access token có thời hạn phù hợp, audience và scope hẹp, tránh token dùng được ở mọi API.
2. **Bảo vệ token:** hạn chế lưu vào log, URL, source code, local storage không được bảo vệ; dùng cơ chế lưu giữ thích hợp với loại client.
3. **Sender constraints khi phù hợp:** các kỹ thuật như mTLS hoặc DPoP có thể ràng buộc token với bên nắm khóa, giảm nguy cơ phát lại bearer token bị lộ; cần bảo vệ khóa.
4. **Quản lý phiên:** phát hiện phiên bất thường, hủy refresh token, kết thúc phiên ứng dụng/IdP và tái xác thực cho thao tác nhạy cảm.
5. **Đánh giá quyền tại API:** kiểm tra subject active, action, resource, tenant và ngữ cảnh; không xem access token là giấy phép toàn hệ thống.
6. **Phản ứng sự kiện:** khi đổi vai trò hoặc phát hiện rủi ro, truyền thông tin thu hồi đủ nhanh tới các PEP quan trọng.

**MFA chống phishing giảm rủi ro chiếm tài khoản**, nhưng không chữa được mọi tình huống phiên đã bị đánh cắp hoặc API key bị lộ. Cần các lớp bổ sung.

### 8.3. Một yêu cầu API có token hợp lệ nhưng vẫn phải bị từ chối

~~~http
GET /api/customers/customer-901
Authorization: Bearer <access-token>
~~~

Dịch vụ có thể xác nhận token do issuer tin cậy phát hành, chưa hết hạn, đúng audience. Tuy nhiên, bản ghi customer-901 thuộc tenant B trong khi subject chỉ được quyền với tenant A. Kết quả đúng là **deny** dù mọi kiểm tra xác thực token đều thành công.

Điều này giới hạn rủi ro ngay cả khi token của người dùng tenant A bị lộ. Nếu API chấp nhận tenant từ query parameter mà không đối chiếu với quyền thực tế, kẻ tấn công có thể vượt ranh giới dữ liệu.

## 9. Tài khoản dịch vụ và quyền máy: một đường xâm nhập khác

Máy móc và workload cũng là danh tính: CI runner, service-to-service API, Kubernetes workload, scheduled job, bot, ứng dụng đối tác. Chúng thường không có người đăng nhập tương tác nên việc phát hiện và thu hồi phải dựa trên owner, scope và telemetry.

### Nguyên tắc thiết kế

- **Một workload, một danh tính rõ ràng:** tránh dùng chung API key admin giữa nhiều dịch vụ, nhóm và môi trường.
- **Quyền theo mục đích:** job báo cáo chỉ đọc tập dữ liệu được chỉ định, không được tạo/xóa principal hoặc đổi IAM policy.
- **Chứng thực ngắn hạn:** ưu tiên workload identity/federation hoặc credential ngắn hạn khi nền tảng hỗ trợ; lưu và xoay secret đúng quy trình nếu không thể loại bỏ.
- **Tách quyền triển khai với runtime:** credential của pipeline deployment không nên có sẵn cho ứng dụng chạy production.
- **Ràng buộc ranh giới:** audience, namespace/project, môi trường, repository/branch được phê duyệt hoặc chứng thực workload phù hợp.
- **Vòng đời:** có owner, lý do, ngày rà soát; revoke khi ứng dụng bị decommission, owner thay đổi hoặc key nghi bị lộ.
- **Audit và cảnh báo:** giám sát principal mới, hành động chưa từng dùng, quyền bị nâng hoặc gọi tới tài nguyên ngoài dự kiến.

### Tình huống: một khóa API dùng chung

Ba job ETL cùng sử dụng khóa svc-admin với quyền đọc/ghi mọi bucket. Một job bị chiếm, kẻ tấn công có thể truy cập dữ liệu của các job khác, khó xác định job khởi nguồn từ log vì cùng principal.

Thiết kế cải thiện:

~~~text
etl-customer-A:
  identity = workload-etl-customer-A
  allowed = object.read[tenant-A/import/]
  allowed = object.write[tenant-A/processed/]
  denied  = iam.modify, object.delete[all]

etl-finance-B:
  identity = workload-etl-finance-B
  allowed = object.read[tenant-B/finance-input/]
  denied  = tenant-A/*, iam.modify
~~~

Các ví dụ là cách mô tả quyền khái niệm. Việc kiểm tra phải tính **effective permissions** trên nền tảng thật, bao gồm quyền kế thừa và resource policy. Khi cần phản ứng sự cố, có thể vô hiệu hóa riêng principal của job bị ảnh hưởng thay vì làm gián đoạn toàn bộ hệ thống dùng chung khóa.

## 10. Phát hiện xâm nhập từ tín hiệu IAM

Khả năng phát hiện phải dựa vào log và sự kiện ở **nhiều nơi**, vì một attacker có thể dùng credential hợp lệ nhưng hành vi sai mục đích.

| Nguồn telemetry | Sự kiện đáng chú ý | Cần phân biệt |
|---|---|---|
| **IdP/SSO** | Đăng nhập bất thường, đăng ký/chuyển phương thức MFA, khôi phục tài khoản, phiên mới rủi ro | Công tác/đổi thiết bị hợp lệ với chiếm quyền |
| **IAM/PAM** | Gán role admin, privilege elevation trái quy trình, tạo service principal hoặc key | Thay đổi theo ticket/được phê duyệt với thay đổi không rõ nguồn |
| **Ứng dụng/API** | Export bất thường, tăng số request, tenant mismatch, nhiều quyết định deny | Chạy báo cáo theo lịch với hành vi ngoài baseline |
| **SCIM/JML** | Leaver/Mover không cập nhật được đích, quyền xuất hiện lại sau revoke | Lỗi tích hợp với hành vi tái cấp trái phép |
| **Cloud/CI/CD** | Workload gọi API mới, credential sử dụng ngoài môi trường, role policy bị sửa | Đợt release hợp lệ với hoạt động không có ticket |
| **Audit/security logging** | Vô hiệu hóa log, thay đổi quyền đọc/xóa log, khoảng trống telemetry | Bảo trì được phê duyệt với che giấu hoạt động |

**Không nên đưa ra quyết định cực đoan chỉ dựa trên một tín hiệu yếu.** Ví dụ đăng nhập từ vị trí lạ có thể do VPN công ty. Với hệ thống có dữ liệu nhạy cảm, những tín hiệu kết hợp như phiên mới + thay MFA + export lớn + tạo API key đáng ưu tiên hơn.

### Một sự kiện audit minh họa

~~~json
{
  "timestamp": "2026-11-23T08:46:11Z",
  "event_type": "authorization_decision",
  "subject_id": "usr-248",
  "session_id_hash": "hash-only-example",
  "application": "crm-api",
  "resource_type": "customer_dataset",
  "resource_scope": "tenant-B",
  "action": "customer.export",
  "decision": "deny",
  "reason_code": "TENANT_SCOPE_MISMATCH",
  "policy_id": "crm.customer.export",
  "policy_version": 12,
  "risk_signals": ["new_device", "export_anomaly"],
  "correlation_id": "req-91e4"
}
~~~

Đây là mẫu minh họa, không phải schema bắt buộc. **Không ghi bearer token, refresh token, mật khẩu, private key hoặc toàn bộ dữ liệu khách hàng vào log.** Session ID nên được xử lý phù hợp với quy định riêng tư và yêu cầu điều tra, ví dụ băm có kiểm soát thay vì ghi nguyên văn. Bảo vệ tính toàn vẹn của audit và giới hạn quyền sửa/xóa log.

### Từ cảnh báo đến quyết định

Một luồng xử lý gọn:

1. Hệ thống nhận sự kiện bất thường và liên kết bằng correlation ID/subject ID.
2. Làm giàu tín hiệu: danh tính active không, JML gần đây, quyền nào đang có, thiết bị/phiên/nguồn request nào, có ticket hợp lệ không.
3. Phân loại mức rủi ro và độ tin cậy; xác định tài nguyên và những đường truy cập đang bị đe dọa.
4. Chọn biện pháp theo runbook: yêu cầu step-up, khóa phiên/token cụ thể, chặn action, cô lập workload hoặc disable principal khi đủ cơ sở.
5. Theo dõi những truy cập còn diễn ra, không kết thúc sự cố chỉ vì một lệnh revoke được gửi thành công.

## 11. Quy trình xử lý sự cố danh tính theo Assume breach

Quy trình tham chiếu dưới đây dành cho tình huống nghi chiếm quyền một danh tính. Tổ chức cần điều chỉnh theo quy định, mức độ nghiêm trọng và công nghệ hiện có.

### Giai đoạn 1 — Xác nhận và định phạm vi

- Ghi nhận alert, thời điểm, subject, ứng dụng, thiết bị/workload, tài nguyên và dấu hiệu hành vi.
- Xác định danh tính có quyền **direct, inherited, delegated, JIT** và các tài khoản liên kết nào.
- Tìm phiên đang active, refresh token, API key, PAT, SSH key và các service principal mà chủ thể có thể điều khiển.
- Đối chiếu dấu hiệu với lịch sử ticket, thay đổi JML, release hoặc hoạt động nghiệp vụ hợp lệ.
- Thu thập chứng cứ cần thiết theo quy trình, hạn chế truy cập trái phép vào dữ liệu điều tra.

### Giai đoạn 2 — Khoanh vùng quyền truy cập

Tùy rủi ro và bằng chứng, đội phụ trách có thể:

- Khóa/giới hạn danh tính hoặc session bị nghi chiếm; yêu cầu xác thực lại qua kênh đáng tin.
- Thu hồi refresh token/phiên, thực hiện phương án chặn access token còn hiệu lực khi kiến trúc hỗ trợ.
- Vô hiệu hóa elevation JIT, quyền admin, delegation hoặc quyền mới phát sinh bất thường.
- Thu hồi/xoay API key và credential có khả năng đã lộ; cô lập workload hoặc tích hợp nếu cần.
- Tại API, tăng kiểm tra quyền hiện tại, chặn action nhạy cảm hoặc resource scope cụ thể.
- Thực thi biện pháp cô lập mạng/thiết bị qua đội endpoint hoặc hạ tầng khi sự cố đòi hỏi.

**Lệnh disable user chưa phải bằng chứng hoàn tất khoanh vùng.** Các ứng dụng có session cục bộ hoặc token tự chứa có thể tiếp tục chấp nhận request. Cần xác nhận bằng kiểm tra tại những điểm truy cập quan trọng và telemetry thực tế.

### Giai đoạn 3 — Loại bỏ nguyên nhân và khôi phục có kiểm soát

- Xử lý nguyên nhân chiếm quyền theo kết quả điều tra: thiết bị, phiên, secret, cơ chế khôi phục tài khoản hoặc cấu hình IAM sai.
- Rà soát role/grant/policy thay đổi trong thời gian sự cố; loại bỏ backdoor như service principal lạ hoặc key mới.
- Cấp lại credential khi cần, bằng đường xác minh danh tính đáng tin; tránh khôi phục một phiên không rõ an toàn.
- Khôi phục quyền tối thiểu cần thiết cho công việc, qua phê duyệt và ghi audit.
- Theo dõi hành vi sau phục hồi trong khoảng thời gian phù hợp với mức độ sự cố.

### Giai đoạn 4 — Đánh giá sau sự cố

- Tính thời gian phát hiện, thời gian khoanh vùng và thời gian còn đường truy cập trái phép.
- Xác định bước nào trong Joiner–Mover–Leaver, provisioning, kiểm tra API hoặc quản lý token đã không thực thi đúng kỳ vọng.
- Cập nhật policy, cấu hình session, alert, playbook, owner, phạm vi quyền và bài kiểm thử hồi quy.
- Đảm bảo bằng chứng được bảo quản theo chính sách; phân biệt dữ liệu cần lưu với thông tin nhạy cảm không cần thu thập.

## 12. Kịch bản minh họa: token cũ và quyền tồn dư sau Mover

**Bối cảnh:** Nhân viên Minh chuyển từ nhóm Support sang Finance lúc 09:00. Minh có quyền xem ticket tenant A và một quyền **customer.export** cũ chưa hết hạn. Đồng thời có access token CRM phát hành lúc 08:55, hết hạn 10:55.

### Dòng thời gian giả lập

| Thời gian | Sự kiện | Rủi ro hoặc kiểm soát |
|---|---|---|
| 08:55 | CRM cấp token cho phiên của Minh | Token còn hạn đến 10:55 |
| 09:00 | HRIS phát sự kiện Mover | Quyền Support không còn phù hợp sau hiệu lực |
| 09:02 | IdP gỡ nhóm Support, thêm Finance | Group IdP đã đổi nhưng không tự vô hiệu mọi token cũ |
| 09:03 | SCIM cập nhật Finance thành công; CRM báo lỗi | Có nguy cơ role cũ còn ở CRM |
| 09:30 | Hệ thống phát hiện request export lượng lớn qua token cũ | Cần kiểm tra ngữ cảnh và quyền hiện tại |
| 09:31 | PDP/API kiểm tra role mới và chặn export CRM | Giới hạn phạm vi, ghi decision deny |
| 09:32 | Incident workflow thu hồi phiên/refresh token và điều tra | Không chỉ dựa vào token tự hết hạn |
| 09:40 | Reconciliation xác nhận không còn grant customer.export | Kiểm tra cả quyền trực tiếp lẫn quyền kế thừa |

### Các cách triển khai dẫn tới kết quả khác nhau

- **Thiết kế yếu:** CRM chỉ kiểm tra chữ ký và claim Support trên token, chấp nhận request export tới 10:55. Nếu token bị đánh cắp, kẻ tấn công có thể sử dụng quyền lỗi thời.
- **Thiết kế có phòng thủ nhiều lớp:** CRM có authorization theo quyền hiện hành, action và tenant; sự kiện Mover khiến export bị từ chối dù token chưa hết hạn. Cảnh báo từ SCIM/PDP được liên kết để điều tra.
- **Thiết kế có thu hồi/giám sát đầy đủ:** ngoài chặn quyền, hệ thống kết thúc phiên phù hợp, xử lý token còn hạn, phát hiện credential cá nhân còn lưu và xác minh những đường truy cập khác.

Lưu ý: khả năng và tốc độ thu hồi token cụ thể phụ thuộc giao thức, IdP, cấu hình ứng dụng và cách resource server kiểm tra. Không có một thao tác “revoke tất cả token” bảo đảm ngay lập tức trên mọi kiến trúc.

### Bài học vận hành

Khoảng trễ JML là một rủi ro có thể đo. Cần biết **sự kiện vai trò có hiệu lực lúc nào**, **đích nào chưa cập nhật**, **request nào vẫn được cho phép sau mốc đó** và **khi nào mọi đường truy cập quan trọng đã bị chặn**.

## 13. Kiểm soát chính sách minh họa cho tình huống bị chiếm quyền

Đoạn dưới là **pseudocode chính sách**, không thuộc cú pháp của một nhà cung cấp IAM cụ thể.

~~~yaml
policy_id: crm.customer.export
version: 12
action: customer.export
default: deny
require:
  subject:
    status: active
    role: crm_exporter
    lifecycle_version: current
  resource:
    tenant_scope: within_subject_approved_scope
    classification: allowed_for_export
  session:
    valid_for_audience: crm-api
    authentication_strength: phishing_resistant_mfa
    authentication_age_minutes_max: 15
    not_revoked: true
  context:
    device_compliant: true
    risk_level: low_or_medium
  governance:
    active_export_approval: true
on_missing_required_signal: deny
on_policy_evaluation_error: deny
audit:
  include: [subject_id, resource_scope, action, decision, policy_version, correlation_id]
  exclude: [access_token, refresh_token, passwords, secrets, raw_customer_data]
~~~

Chính sách minh họa chặn export trong các trường hợp:

- Danh tính đã chuyển vai trò, không còn crm_exporter;
- Tài nguyên không thuộc phạm vi dữ liệu được phê duyệt;
- Phiên không đạt yêu cầu xác thực mới hoặc thiết bị không đáp ứng;
- Tín hiệu bắt buộc mất hoặc policy engine không thể đánh giá an toàn.

Trong môi trường thật, “lifecycle_version: current” phải được hiện thực bằng cơ chế đáng tin, như nguồn quyền hiện hành, version/epoch của phiên hoặc revocation phù hợp. Chỉ ghi field này trong YAML không làm JWT cũ tự mất hiệu lực. Mức MFA, thời hạn 15 phút và ngưỡng rủi ro chỉ mang tính minh họa.

### Nguyên tắc hành vi khi kiểm tra không khả dụng

Nếu nguồn policy/risk/identity gặp sự cố, xử lý tùy mức độ dữ liệu và yêu cầu vận hành:

- Với export, duyệt thanh toán, thay IAM policy hoặc truy cập secret: ưu tiên **fail closed** khi không xác minh được điều kiện bắt buộc.
- Với thao tác ít rủi ro: cân nhắc quyết định đã cache **có thời hạn và scope hẹp**, chỉ khi được chính sách cho phép.
- Với ứng phó khẩn cấp: dùng đường break-glass được bảo vệ và kiểm toán, tránh cấp quyền chung theo kiểu “tạm mở hết”.
- Đo và kiểm thử các trường hợp lỗi để chính sách không làm hệ thống mất khả dụng ngoài dự kiến.

## 14. Kiểm thử kiểu Assume breach

Thay vì chỉ xác nhận “người dùng hợp lệ có thể đăng nhập”, hãy kiểm thử **nếu một lớp đã bị vượt qua thì hệ thống còn chặn được gì**.

| ID | Giả định kiểm thử | Hành động thử | Kết quả mong đợi |
|---|---|---|---|
| B1 | Access token còn hạn nhưng user đã Leaver | Gọi API nghiệp vụ quan trọng | Bị chặn trong SLA thu hồi theo thiết kế |
| B2 | User vừa Mover, JWT còn claim role cũ | Truy cập tài nguyên thuộc vai trò cũ | Deny nhờ quyền hiện hành/kiểm soát thu hồi |
| B3 | Token hợp lệ cho API A | Gọi API B | Deny do audience không phù hợp |
| B4 | Support account bị chiếm | Đọc ticket tenant B từ tài khoản tenant A | Deny ở cấp đối tượng/tenant |
| B5 | User role analyst | Gọi approve hoặc export nhạy cảm | Deny hoặc step-up theo chính sách, không kế thừa quyền tự động |
| B6 | Quyền JIT đã hết TTL | Sử dụng lại phiên nâng quyền cũ | Deny trong SLA đã xác định |
| B7 | Secret của ETL tenant A bị lộ | Thử gọi API tenant B hoặc sửa IAM | Deny nhờ scope riêng |
| B8 | SCIM thất bại khi Leaver | Quan sát trạng thái ứng dụng đích | Cảnh báo và đối soát; không ghi nhận hoàn tất khi chưa xác minh |
| B9 | PDP không khả dụng | Yêu cầu export hoặc sửa policy nhạy cảm | Fail closed theo thiết kế |
| B10 | Một principal mới có quyền cao được tạo trái quy trình | Kiểm tra alert và audit | Phát hiện, gắn owner/risk, có quy trình xử lý |
| B11 | Refresh token đã bị thu hồi | Thử xin access token mới | Bị từ chối |
| B12 | Đăng nhập hợp lệ từ thiết bị rủi ro | Thử hành động được phân loại nhạy cảm | Step-up hoặc deny tùy chính sách |
| B13 | Audit store bị thử thay đổi | Kiểm tra quyền ghi/xóa và cảnh báo | Chỉ principal được ủy quyền có quyền cần thiết, bất thường có telemetry |
| B14 | Một service account bị xóa owner/hết hợp đồng | Chạy workload không còn được phép | Bị thu hồi hoặc đưa vào điều tra theo policy |

**An toàn kiểm thử:** dùng principal, tenant và dữ liệu thử nghiệm có ủy quyền; không sử dụng dữ liệu khách hàng thật để cố tạo sự cố. Những phép thử về tài khoản quyền cao và xử lý sự cố nên theo kế hoạch thử nghiệm được tổ chức chấp thuận.

### Kiểm thử phải nhìn thấy kết quả cuối cùng

Với B2, việc IdP báo group đã xóa chưa đủ. Cần gọi tới endpoint thực tế bằng token/phiên còn hạn và xác nhận:

1. Hệ thống trả deny hoặc không cung cấp dữ liệu không còn quyền;
2. Audit ghi đúng subject, action, resource, policy và lý do;
3. Không còn đường truy cập phụ qua local account, API key hoặc delegation;
4. Thời gian từ sự kiện JML đến thời điểm chặn nằm trong SLA.

Cần phân biệt **kiểm thử chặn ở control plane** (quyền đã được cập nhật) và **kiểm thử chặn ở data plane** (request thực tế đã không còn truy cập được).

## 15. Chỉ số vận hành để biết khả năng chống chịu có tiến bộ

| Chỉ số | Cách đo | Ý nghĩa |
|---|---|---|
| **Mean Time to Detect (MTTD)** | Từ mốc sự cố xác định được đến alert/nhận diện | Đánh giá tốc độ phát hiện; cần ghi rõ nguồn mốc khi khó xác định chính xác |
| **Mean Time to Contain (MTTC)** | Từ phát hiện/xác nhận đến khi đường truy cập chính đã bị chặn, theo định nghĩa nội bộ | Đánh giá khả năng khoanh vùng |
| **Revocation latency** | Từ Mover/Leaver/revoke đến lúc quyền thật sự không thể dùng | Phát hiện khoảng hở do token, SCIM và cache |
| **Blast-radius exposure** | Số tài nguyên/tenant/app và action nhạy cảm mà một principal có thể truy cập | Đánh giá phạm vi quyền hiệu lực có thể bị lạm dụng |
| **Standing privileged access** | Số lượng principal có quyền cao liên tục, phân theo owner và hệ thống | Đánh giá rủi ro đặc quyền thường trực |
| **JIT coverage** | Tỷ lệ tác vụ admin dùng quyền tạm thời có thời hạn, có audit | Theo dõi giảm quyền admin thường trực |
| **Orphaned identity rate** | Số tài khoản/credential không có owner hoặc quan hệ còn hiệu lực | Tìm đường tồn dư dễ bị bỏ quên |
| **Deprovisioning failure age** | Thời gian các lỗi vô hiệu hóa ở ứng dụng đích chưa được giải quyết | Ưu tiên các ngoại lệ kéo dài |
| **Policy enforcement coverage** | Tỷ lệ endpoint/hành động nhạy cảm được kiểm tra resource/action/tenant | Đo độ phủ của lớp ngăn chặn tại API |
| **Telemetry completeness** | Tỷ lệ quyết định và thay đổi quyền có audit đủ subject, action, scope, timestamp, correlation | Chứng minh khả năng điều tra và truy vết |

Đừng chỉ đếm số alert: alert quá nhiều, chất lượng thấp có thể khiến đội vận hành bỏ sót sự cố. Nên cân bằng **tín hiệu hữu ích, false positive, quyền riêng tư và khả năng phản ứng**, đồng thời ưu tiên chỉ số mức tác động thực tế.

## 16. Bài tập tình huống: thiết kế containment cho một danh tính bị chiếm

**Bối cảnh**

Một công ty sử dụng IdP + SSO cho CRM, Finance, Cloud Console và một hệ thống CI/CD. Nhân viên An là thành viên nhóm Support tenant A. An vừa đổi phòng ban nhưng CRM chưa cập nhật thay đổi vì SCIM lỗi. Một hệ thống giám sát phát hiện trong phiên cũ của An:

- Request đọc ticket tăng đột biến;
- Có request export dữ liệu tenant A với số lượng lớn;
- Xuất hiện hành động tạo API key mới;
- Có lần thử gọi API Finance và thay quyền cloud dù công việc hiện tại không cần.

An cũng từng sở hữu một bot tích hợp đã ngừng sử dụng nhưng service account của bot vẫn active.

### Câu hỏi

1. Những đường nào có thể làm sự cố vượt phạm vi ticket của tenant A?
2. Cần khoanh vùng quyền và phiên nào trước; làm sao tránh kết luận thiếu bằng chứng?
3. Quyền tồn dư từ Mover và bot cũ tạo ra rủi ro nào?
4. Sau khi gửi lệnh disable và revoke, cần kiểm chứng những gì?
5. Chọn ba chỉ số để theo dõi cải thiện sau sự cố.

### Gợi ý lời giải

**1. Đường lan rộng:** quyền export lớn, khả năng tạo API key, quyền Cloud/Finance nếu có grant trực tiếp hoặc kế thừa, service account bot không có owner đang hoạt động. Phải xác định **effective permissions** và xem API có kiểm tra tenant/action/resource không.

**2. Khoanh vùng:** kiểm tra alert, tài nguyên đang được dùng và ticket/ngữ cảnh hợp lệ; với rủi ro cao có thể khóa phiên hoặc danh tính nghi xâm nhập, thu hồi refresh token/phiên, chặn action export, ngừng credential mới, xử lý những quyền đặc biệt đang active. Giữ log, correlation ID và quyết định rõ ràng về mức tác động.

**3. Quyền tồn dư:** token CRM cũ hoặc local account có thể còn hiệu lực sau thay đổi; bot có thể giữ secret độc lập với An. Cần đối soát JML, thu hồi quyền trực tiếp và xem lại ownership, chuyển automation còn hợp lệ sang workload identity riêng trước khi thu hồi credential cũ.

**4. Xác minh sau revoke:** thử những endpoint quan trọng với phiên/token được kiểm thử hợp lệ theo kế hoạch; kiểm tra ứng dụng đích đã disable, API key đã bị thu hồi, không còn service principal lạ và telemetry không còn request được cho phép sai chính sách. Đo thời gian chặn, ghi ngoại lệ SCIM chưa giải quyết.

**5. Chỉ số:** thời gian thu hồi quyền (p95/p99), số principal/quyền tồn dư không có owner, thời gian từ alert đến khoanh vùng (MTTC). Có thể thêm coverage kiểm tra cấp tài nguyên và tỷ lệ SCIM lỗi quá SLA.

**Bài tập mở rộng:** Nếu khóa toàn bộ IdP khiến hàng nghìn nhân viên mất truy cập, tổ chức có những phương án khoanh vùng theo **principal/phiên/action/resource** nào để giữ hoạt động thiết yếu? Nêu điều kiện để giới hạn phạm vi, ai phê duyệt và cách xác minh biện pháp có hiệu lực.

## 17. Checklist và tài liệu đọc tiếp

### Checklist triển khai

- [ ] Đã xác định các danh tính người, đối tác, service account, workload và đường truy cập quyền cao.
- [ ] Có mô hình đường tấn công giả định từ một phiên/credential bị lộ tới các tài nguyên nhạy cảm.
- [ ] Role, scope, quyền kế thừa và các ngoại lệ có thời hạn được rà soát theo effective permissions.
- [ ] API kiểm tra đúng subject, action, resource, tenant và ngữ cảnh, có deny mặc định.
- [ ] Token có issuer/audience/TTL phù hợp; có phương án xử lý refresh token, phiên và quyền cũ khi bị xâm nhập.
- [ ] Thiết kế JML chặn quyền tồn dư và xác minh kết quả tại ứng dụng đích, kể cả SCIM lỗi.
- [ ] Quyền admin được giới hạn bằng JIT/JEA/PAM, SoD và audit; break-glass có bảo vệ riêng.
- [ ] Workload/service account có owner và scope nhỏ, credential được quản lý, thu hồi khi decommission.
- [ ] Telemetry liên kết sự kiện đăng nhập, thay đổi role, token/secret, policy decision và hành vi truy cập.
- [ ] Có runbook khoanh vùng danh tính, phiên, token, credential và service account theo mức rủi ro.
- [ ] Có kiểm thử access denial, tenant isolation, token cũ, PDP/SCIM lỗi, phát hiện privilege escalation.
- [ ] Đo được revocation latency, thời gian phát hiện/khoanh vùng và mức ảnh hưởng tiềm năng.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Assume breach** | Giả định một lớp có thể bị vượt qua và thiết kế để giới hạn/khắc phục tác động |
| **Blast radius** | Phạm vi tài nguyên, hệ thống và dữ liệu có thể bị ảnh hưởng |
| **Lateral movement** | Di chuyển từ một quyền/điểm truy cập sang hệ thống hoặc tài nguyên khác |
| **Credential / session compromise** | Mất quyền kiểm soát bí mật xác thực hoặc phiên đã được xác thực |
| **Containment** | Khoanh vùng quyền/truy cập để ngăn sự cố tiếp diễn hoặc lan rộng |
| **JML** | Joiner–Mover–Leaver: gia nhập, thay đổi vai trò, rời đi |
| **Residual access** | Quyền/phiên/credential còn sử dụng được dù không còn nhu cầu hợp lệ |
| **RBAC/ABAC** | Phân quyền theo vai trò và theo thuộc tính/chính sách ngữ cảnh |
| **IdP/SSO/SCIM** | Xác thực tập trung, đăng nhập liên kết, đồng bộ vòng đời tài khoản và nhóm |
| **PEP/PDP** | Điểm thực thi truy cập và thành phần quyết định chính sách |
| **JIT/PAM** | Truy cập đặc quyền tạm thời và quản lý quyền/phiên đặc quyền |
| **MTTD/MTTC** | Thời gian phát hiện và thời gian khoanh vùng theo định nghĩa vận hành |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** cơ sở của kiến trúc Zero Trust, xác minh truy cập và hạn chế tin cậy ngầm.
- **NIST SP 800-61 — Computer Security Incident Handling / Incident Response:** nguyên tắc chuẩn bị, phát hiện, xử lý và cải tiến ứng phó sự cố.
- **NIST SP 800-53 — Security and Privacy Controls:** các nhóm kiểm soát AC (Access Control), IA (Identification and Authentication), AU (Audit) và IR (Incident Response).
- **NIST SP 800-63 — Digital Identity Guidelines:** xác minh danh tính, xác thực và quản lý phiên/bằng chứng.
- **RFC 7643 / RFC 7644 — SCIM:** đồng bộ user/group, liên quan trực tiếp tới quy trình thay đổi/thu hồi quyền.
- **OWASP API Security Top 10:** các lỗi phân quyền ở cấp đối tượng/chức năng và bảo vệ API.
- **MITRE ATT&CK:** từ điển chiến thuật/kỹ thuật có thể dùng để mô hình hóa các hành vi như lạm dụng tài khoản hợp lệ, thay đổi quyền và di chuyển ngang.

**Điểm cốt lõi:** Assume breach biến câu hỏi “làm sao ngăn tất cả tấn công?” thành một thiết kế có thể kiểm chứng: **“Nếu một danh tính, phiên hoặc workload bị chiếm, điều gì vẫn ngăn sự cố lan rộng, ai phát hiện, ai thu hồi, và bao lâu mới chứng minh được truy cập đã bị chặn?”**. Trong IAM, câu trả lời nằm ở quyền hẹp, kiểm tra tại tài nguyên, vòng đời JML kịp thời, danh tính máy riêng, telemetry và quy trình khoanh vùng có thể thực thi.
