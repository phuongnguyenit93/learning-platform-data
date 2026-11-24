# Device posture — Trạng thái bảo mật thiết bị trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Device posture (tư thế/trạng thái bảo mật thiết bị)  
> **Phạm vi:** Quản lý vòng đời danh tính IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, cấp tài khoản và quyền đến rà soát, thay đổi và thu hồi. Bài liên kết tín hiệu thiết bị với **IdP, SSO, SCIM, RBAC/ABAC**, danh tính máy, kiểm toán và xử lý quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **device posture** là gì, vì sao nó ảnh hưởng đến quyết định truy cập Zero Trust và vì sao thiết bị “compliant” không tự động được tin cậy hoàn toàn.
2. Phân biệt **danh tính thiết bị**, **quản lý thiết bị (managed)**, **tuân thủ chính sách (compliant)**, **tình trạng bảo vệ (healthy)** và **rủi ro hiện tại**.
3. Xác định nguồn tín hiệu: **MDM/UEM**, giải pháp bảo vệ endpoint/EDR, chứng chỉ, attestation, bản vá, mã hóa, cấu hình thiết bị và hệ thống quản trị tài sản.
4. Thiết kế chính sách truy cập kết hợp **danh tính người dùng, vai trò, tài nguyên, hành động, thiết bị và ngữ cảnh**, đồng thời xử lý tình trạng thiết bị *unknown*, *stale* hoặc không tuân thủ.
5. Gắn việc đăng ký, bàn giao, đổi chủ, mất thiết bị và thu hồi thiết bị với **Joiner–Mover–Leaver**, phiên SSO, token và quyền ở ứng dụng đích.
6. Đề xuất cách triển khai, khắc phục và kiểm thử cho **thiết bị công ty, BYOD, máy dùng chung, thiết bị đặc biệt và workload tự động**.
7. Đo được độ mới của tín hiệu, thời gian phản ứng khi thiết bị mất tuân thủ, độ phủ kiểm soát và tỷ lệ chặn nhầm.

## 2. Device posture là gì?

**Device posture** là tập hợp các thuộc tính và bằng chứng phản ánh mức độ đáp ứng yêu cầu bảo mật của một thiết bị tại hoặc gần thời điểm truy cập. Nó có thể mô tả hệ điều hành và bản vá, trạng thái mã hóa ổ đĩa, màn hình khóa, phần mềm bảo vệ, cấu hình quản lý, tình trạng rủi ro và độ tin cậy của thông tin nhận được.

Trong Zero Trust, quyết định truy cập không nên dựa vào suy luận “máy đang ở mạng nội bộ nên an toàn”. Hệ thống cần xem xét những bằng chứng thích hợp về **người dùng, thiết bị, phiên, tài nguyên và hành động**.

**Ví dụ:** Nhân viên Bình dùng tài khoản Finance đăng nhập SSO thành công. Bình có quyền đọc hóa đơn tenant A, nhưng đang sử dụng máy chưa bật mã hóa ổ đĩa, thiếu bản vá bắt buộc và chưa nhận trạng thái quản lý từ hệ thống thiết bị. Theo chính sách, ứng dụng có thể từ chối tải dữ liệu nhạy cảm về máy đó, cho phép xem thông tin ít nhạy cảm hoặc hướng dẫn Bình khắc phục thiết bị trước khi tiếp tục.

Sự hiện diện của thiết bị đạt chính sách **không cấp thêm quyền** cho Bình: nếu hóa đơn thuộc tenant B thì vẫn bị từ chối dù thiết bị hoàn toàn compliant.

### Một số cách hiểu dễ nhầm

| Nhận định | Cách hiểu chính xác |
|---|---|
| “Thiết bị thuộc công ty là đáng tin.” | Quyền sở hữu là một thuộc tính; thiết bị công ty vẫn có thể mất bản vá, bị nhiễm mã độc hoặc bị mất. |
| “Đã enroll MDM thì luôn compliant.” | **Managed** nghĩa là thiết bị có quan hệ quản lý phù hợp; **compliant** là kết quả đánh giá chính sách ở một thời điểm. |
| “Có phần mềm EDR thì thiết bị khỏe.” | Có EDR là một tín hiệu; còn phải xem cảm biến hoạt động, thông tin có mới và có cảnh báo rủi ro không. |
| “Có client gửi device_id thì biết đúng thiết bị.” | Device ID do client tự khai không đủ tin cậy; cần cơ chế liên kết đáng tin giữa thiết bị, bằng chứng và phiên. |
| “MFA mạnh thì không cần posture.” | MFA giúp chứng minh người đang xác thực; nó không tự chứng minh thiết bị đang đáp ứng yêu cầu bảo vệ dữ liệu. |
| “Thiết bị compliant cho phép mọi API.” | Vẫn phải kiểm tra **action, resource, tenant, role và trạng thái vòng đời**. |
| “Không có tín hiệu nghĩa là thiết bị an toàn.” | **Unknown** không tương đương **healthy**; phải xử lý theo chính sách và mức nhạy cảm tài nguyên. |

**Nguyên tắc chính:** Device posture là **một yếu tố đầu vào của quyết định truy cập**, không phải nguồn cấp quyền nghiệp vụ hoặc bằng chứng tuyệt đối rằng thiết bị không thể bị xâm nhập.

## 3. Năm khái niệm phải tách biệt

### 3.1. Device identity — danh tính thiết bị

Danh tính thiết bị là cách hệ thống nhận biết một endpoint hoặc một thực thể máy. Nó có thể liên quan đến **device record**, chứng chỉ thiết bị, khóa được bảo vệ bởi phần cứng, thông tin đăng ký MDM hoặc cơ chế attestation. Một số mã như hostname, địa chỉ IP hoặc chuỗi user-agent có thể thay đổi hay bị giả mạo, nên không đủ làm bằng chứng mạnh riêng lẻ.

Dù biết chính xác **đây là thiết bị D-42**, hệ thống vẫn cần kiểm tra **D-42 có còn hợp lệ, đang tuân thủ và có được phép dùng cho tài nguyên này hay không**.

### 3.2. Managed — đang được quản lý

Một thiết bị được gọi là managed khi có quan hệ quản lý đã thiết lập với hệ thống và chính sách thiết bị, chẳng hạn qua MDM/UEM. Mức quản lý có thể khác nhau giữa máy công ty và BYOD.

Đăng ký (enrollment) thành công không chứng minh rằng thiết bị luôn đạt mọi kiểm soát. Thiết bị có thể bị mất liên lạc, cấu hình lệch hoặc tồn tại một trạng thái *retired* cần xử lý.

### 3.3. Compliant — đáp ứng chính sách

Compliant là **kết quả đánh giá** một tập yêu cầu: ví dụ có mã hóa, bản vá bắt buộc, không vượt ngưỡng rủi ro, có khóa màn hình, có tính năng bảo vệ cần thiết. Tập yêu cầu thay đổi theo tổ chức, nền tảng, loại dữ liệu và mức rủi ro.

Một thiết bị có thể compliant với chính sách truy cập dữ liệu nội bộ thông thường nhưng **chưa đạt yêu cầu cho export dữ liệu tài chính**.

### 3.4. Healthy — trạng thái bảo vệ/vận hành

Healthy thường phản ánh tình trạng của endpoint và công cụ bảo vệ: cảm biến đang chạy, có hoặc không có cảnh báo nguy cơ, dịch vụ bảo mật còn hoạt động. Nó không đồng nhất với compliant: một máy chạy EDR tốt vẫn có thể thiếu mã hóa bắt buộc; một máy có cấu hình đúng vẫn có thể phát cảnh báo độc hại.

### 3.5. Trusted/assured — mức tin cậy đã xác minh

Trong một quyết định truy cập, “trusted” là **kết luận có điều kiện của chính sách tại thời điểm nhất định**, dựa trên danh tính thiết bị, mức đảm bảo của bằng chứng, độ mới và trạng thái. Không nên biến nó thành một cờ **trusted=true** vĩnh viễn.

Một mô hình dễ nhớ:

**Device posture decision = Evidence(source, integrity, device binding, observed time, policy requirements)**

Trong đó *device binding* là cách chứng minh bằng chứng posture gắn với **chính thiết bị/phiên đang gửi yêu cầu**, tránh việc thiết bị không compliant lấy lại kết quả đánh giá của thiết bị khác.

## 4. Các tín hiệu posture và giới hạn của chúng

| Tín hiệu | Điều có thể cho biết | Hạn chế cần ghi nhớ |
|---|---|---|
| **Thiết bị đã đăng ký và còn active** | Thiết bị có bản ghi, owner hoặc liên kết quản lý | Bản ghi có thể cũ; enrollment không chứng minh máy hiện an toàn |
| **Hệ điều hành/bản vá** | Phiên bản và mức cập nhật đáp ứng baseline | Thông tin báo cáo có thể trễ; “mới nhất” không có nghĩa không tồn tại lỗ hổng |
| **Mã hóa lưu trữ** | Kiểm soát dữ liệu khi ổ lưu trữ bị lấy cắp, nếu được cấu hình đúng | Không ngăn mọi hình thức truy cập trái phép trong phiên đang mở |
| **Khóa màn hình và cấu hình bảo vệ** | Thiết bị đáp ứng một phần yêu cầu sử dụng an toàn | Một cấu hình đạt chuẩn không loại bỏ hoàn toàn nguy cơ |
| **EDR/endpoint protection** | Tình trạng cảm biến, cảnh báo, dấu hiệu mã độc hoặc bất thường | Cảm biến có thể bị tắt, trễ hoặc không có trên thiết bị đặc biệt |
| **Secure boot, TPM/hardware-backed key** | Hỗ trợ chuỗi khởi động và bảo vệ khóa tùy nền tảng | Chỉ hữu ích khi việc xác minh/attestation triển khai đúng; không chứng minh mọi phần mềm đều sạch |
| **Jailbreak/root detection** | Phát hiện một số tình trạng thay đổi bảo vệ hệ thống | Có thể có false positive/false negative; không dùng làm bằng chứng duy nhất |
| **Ứng dụng quản lý thiết bị** | Tình trạng UEM/MDM, cấu hình bắt buộc, khả năng nhận chính sách | Agent có thể mất kết nối, phiên bản cũ hoặc bị giả mạo nếu kiểm tra yếu |
| **Chứng chỉ thiết bị** | Bằng chứng thiết bị có khóa/chứng chỉ được cấp theo quy trình | Chứng chỉ còn hạn không khẳng định posture hiện tại; cần bảo vệ khóa và thu hồi |
| **Tín hiệu mạng và vị trí thô** | Bổ sung ngữ cảnh/rủi ro của kết nối | VPN, NAT và chuyển mạng làm thay đổi IP; vị trí không tạo quyền truy cập |
| **Tình trạng mất/thu hồi tài sản** | Thiết bị bị đánh dấu lost, retired, stolen, unenrolled | Event phải tới được điểm thực thi và chặn phiên đang active |
| **Thời điểm cập nhật cuối** | Bằng chứng còn đủ mới theo policy không | Tín hiệu quá hạn phải thành stale/unknown theo quy định |

Không phải nền tảng thiết bị nào cũng hỗ trợ mọi tín hiệu. Ví dụ một thiết bị IoT hoặc máy kiosk có thể không cài EDR thông thường; khi đó cần **kiểm soát thay thế có căn cứ** như phân đoạn mạnh, chứng thực máy, quyền API hẹp và giới hạn dữ liệu.

### Ví dụ diễn giải một bản ghi posture

~~~yaml
# Mẫu khái niệm; đây không phải cấu trúc bắt buộc của MDM/IdP.
device:
  device_id: "dev-042"
  enrollment_state: "managed"
  lifecycle_state: "active"
  device_owner: "company"
  operating_system: "Windows"
posture:
  compliance_state: "compliant"
  disk_encryption: true
  endpoint_protection: "healthy"
  patch_baseline: "met"
  high_severity_threat: false
evidence:
  source: "corporate-device-posture-service"
  observed_at: "2026-11-23T07:00:00Z"
  valid_until: "2026-11-23T07:10:00Z"
  device_binding: "verified"
~~~

Ở 07:05Z, ứng dụng có thể đánh giá chứng cứ này theo chính sách. **Sau 07:10Z, không tự kéo dài trạng thái compliant** nếu chưa có bằng chứng mới hoặc một cơ chế cache được phép rõ ràng. Mốc thời gian là ví dụ; thực tế phụ thuộc mức nhạy cảm, độ trễ nguồn và khả năng hệ thống.

## 5. Bằng chứng đến từ đâu và ai chịu trách nhiệm?

Một giải pháp hoàn chỉnh thường cần nhiều thành phần:

| Thành phần | Vai trò với device posture | Điều không nên mặc định |
|---|---|---|
| **Asset inventory** | Ghi nhận thiết bị, chủ sở hữu, loại, ngày bàn giao và trạng thái vòng đời | Có tài sản trong danh mục = có thể truy cập |
| **MDM/UEM** | Enroll, cấu hình, kiểm tra compliance, retire thiết bị | Managed = thiết bị không bị xâm nhập |
| **EDR/endpoint protection** | Báo rủi ro, trạng thái bảo vệ, hành vi nghi ngờ | Không có alert = chắc chắn an toàn |
| **Device certificate/PKI** | Hỗ trợ chứng thực danh tính thiết bị và bảo vệ kênh | Chứng chỉ hợp lệ = mọi điều kiện posture đã đạt |
| **Attestation service** | Xác minh một số thuộc tính nền tảng/khóa/trạng thái có chứng cứ | Attestation đầy đủ cho mọi phần mềm và mọi thời điểm |
| **IdP/SSO** | Xác thực người dùng, kiểm tra điều kiện phiên và có thể dùng tín hiệu device trust | SSO tự biết tenant/owner của mọi bản ghi ứng dụng |
| **Policy engine/PDP** | Kết hợp tín hiệu thiết bị với danh tính, action, resource, rủi ro | Mọi PDP đều có chức năng truy vấn thiết bị như nhau |
| **Application/API/PEP** | Thực thi allow/deny/step-up; kiểm tra đối tượng truy cập | Gateway biết được mọi thuộc tính tài nguyên |
| **IAM lifecycle/HRIS** | Cung cấp sự kiện Joiner–Mover–Leaver và quyền hiện tại | SCIM hoặc HR event tự dừng mọi phiên |
| **SIEM/SOC/operations** | Tương quan sự kiện, cảnh báo, điều tra và khoanh vùng | Mọi alert posture đều là xâm nhập đã xác nhận |

Luồng dữ liệu phải xác định rõ **nguồn authoritative** cho từng thuộc tính. Không nên dùng giá trị “device_compliant=true” do frontend, SDK tự do gửi lên làm bằng chứng nếu backend không xác minh nguồn và **liên kết với thiết bị thực đang yêu cầu**.

### Bằng chứng bị tách khỏi phiên là điểm yếu lớn

Giả sử thiết bị A compliant và thiết bị B không compliant. Nếu API tin một header tự khai:

~~~http
GET /api/reports/quarterly
Authorization: Bearer <access-token>
X-Device-ID: dev-A
X-Device-Compliant: true
~~~

Một request từ B có thể giả khai rằng nó đến từ A. **Header này không đủ chứng minh posture**. Cần phương án phù hợp: IdP/conditional access phát hành tín hiệu được bảo vệ và có liên kết phiên, chứng chỉ/khóa gắn với thiết bị, device attestation có xác minh, hoặc PEP đáng tin kiểm tra trạng thái từ nguồn có kiểm soát.

Dù posture được gắn trong token đã ký, vẫn cần xét **tuổi claim và khả năng thay đổi sau khi token được cấp**.

## 6. Liên kết danh tính người dùng, thiết bị và phiên

Một chính sách Zero Trust thường phải gắn ba đối tượng:

1. **User identity:** ai đang sử dụng? Tài khoản active, thuộc tenant/đơn vị nào, được cấp role gì?
2. **Device identity/posture:** thiết bị nào, có bằng chứng đáng tin, trạng thái hiện tại ra sao?
3. **Session/request:** phiên nào, được xác thực bằng phương thức nào, đang yêu cầu action gì trên resource nào?

Nếu chỉ có user identity, ứng dụng không biết người đó dùng thiết bị phù hợp không. Nếu chỉ có device identity, ứng dụng không biết ai đang thao tác. Nếu có cả hai nhưng **không liên kết đúng với phiên**, kết quả posture của một máy có thể bị sử dụng sai nơi.

### Những cơ chế có thể hỗ trợ liên kết

- **Chứng chỉ và khóa bảo vệ trên thiết bị:** cho phép client chứng minh việc nắm khóa gắn với device record và phiên/kết nối.
- **Đăng ký thiết bị tại IdP:** một số nền tảng có thể đưa device identifier và compliance vào các quyết định truy cập có điều kiện.
- **mTLS:** hỗ trợ xác thực máy/ứng dụng theo chứng chỉ ở kết nối phù hợp; vẫn cần xác minh trạng thái thiết bị.
- **Sender-constrained token:** ràng buộc token với bằng chứng nắm khóa như mTLS/DPoP trong các luồng hỗ trợ, giúp giảm khả năng dùng bearer token bị đánh cắp từ thiết bị khác.
- **Attestation/health assertion:** cung cấp bằng chứng có xác minh về thuộc tính nền tảng hoặc thiết bị, tùy khả năng phần cứng/phần mềm.
- **Sự kiện về session và device:** khi thiết bị retired hoặc phát hiện rủi ro, các PEP liên quan cần nhận biết và phản ứng.

Không có cơ chế nào tự chứng minh mọi hành vi từ thiết bị đều là hợp lệ. **Một thiết bị compliant vẫn có thể bị lợi dụng trong phiên đã đăng nhập**; authorization theo action/resource và khả năng giám sát vẫn bắt buộc.

### Khi người dùng có nhiều thiết bị

Mỗi thiết bị có thể có posture riêng: laptop công ty compliant, điện thoại cá nhân unmanaged và máy dự phòng đã bị retired. Một phiên tạo trên laptop không được coi là bằng chứng để điện thoại truy cập dữ liệu nhạy cảm. Cần ràng buộc và đánh giá **theo phiên/thiết bị thực**, không gắn trạng thái compliance vĩnh viễn vào riêng hồ sơ người dùng.

## 7. Chính sách theo danh tính, hành động và độ nhạy dữ liệu

Device posture hữu ích nhất khi được kết hợp với **RBAC/ABAC** và phân loại tài nguyên. Câu hỏi không chỉ là “thiết bị có compliant không?” mà là **“hành động này trên tài nguyên này cần mức bảo đảm thiết bị nào?”**

### Ma trận chính sách minh họa

| Tài nguyên/hành động | Điều kiện danh tính/quyền | Điều kiện thiết bị minh họa | Kết quả nếu thiếu posture |
|---|---|---|---|
| Xem thông báo nhân sự ít nhạy cảm | Nhân viên active, có quyền xem | Có thể chấp nhận BYOD theo chính sách | Có thể cho phép với bảo vệ phù hợp |
| Xem ticket khách hàng được giao | Support active, đúng tenant/ticket | Thiết bị managed, mức bảo vệ đáp ứng chuẩn | Deny hoặc hướng dẫn thiết bị hợp lệ |
| Tải dữ liệu khách hàng hàng loạt | Quyền export, phê duyệt, đúng tenant | Compliant, mã hóa, EDR khỏe, tín hiệu mới | Deny khi thiếu điều kiện bắt buộc |
| Duyệt thanh toán | Approver, SoD đạt, đúng tenant | Thiết bị đáp ứng yêu cầu cao, phiên MFA phù hợp | Deny/step-up theo nguyên nhân |
| Thay đổi IAM policy production | Admin JIT được phê duyệt | Thiết bị quản trị riêng, có attestation phù hợp nếu triển khai | Chặn, chuyển sang đường quản trị được bảo vệ |
| Truy cập công khai không cần đăng nhập | Không yêu cầu danh tính nội bộ | Không yêu cầu posture của thiết bị người đọc | Không thu thập posture vô ích |

**Các giá trị và cấp độ trong bảng chỉ là ví dụ thiết kế.** Tổ chức phải định nghĩa mức rủi ro, loại thiết bị cho phép, mục đích truy cập và biện pháp khắc phục theo yêu cầu thực tế.

### Chính sách có điều kiện minh họa

~~~yaml
# Pseudocode chính sách, không phải cấu hình triển khai của sản phẩm cụ thể.
policy_id: crm.customer.export
effect: allow
request:
  action: customer.export
require:
  subject:
    status: active
    role: crm_exporter
    tenant_scope: resource_tenant
  resource:
    classification: approved_for_export
  session:
    authenticated: true
    assurance_level: sufficient_for_export
  device:
    lifecycle_state: active
    enrollment_state: managed
    posture_evidence_verified: true
    posture_evidence_fresh: true
    compliance_state: compliant
    endpoint_protection: healthy
  governance:
    export_approval: active
default: deny
when_authentication_insufficient: step_up
when_device_noncompliant: deny_and_remediate
when_required_device_signal_unknown: deny
~~~

**Step-up không tự chữa được thiết bị thiếu mã hóa hoặc nhiễm mã độc.** Nếu vấn đề là mức MFA chưa đủ, gửi challenge; nếu vấn đề là posture, phải có luồng khắc phục thiết bị hoặc sử dụng kênh/thiết bị phù hợp. Nếu sai role, action hoặc tenant, yêu cầu MFA lại cũng không cấp thêm quyền.

### RBAC + ABAC theo tài nguyên

Một nhân viên Support chỉ cần:

- Role support_agent;
- Action ticket.read hoặc ticket.comment;
- Ticket thuộc tenant được phép và được giao;
- Tài khoản còn active;
- Posture đạt điều kiện của dữ liệu khách hàng.

Công thức tư duy:

**Allow = AuthN hợp lệ ∧ AuthZ(subject, action, resource) ∧ DevicePosture phù hợp ∧ Context đạt yêu cầu.**

Toán tử logic nhấn mạnh rằng **một điều kiện đúng không bù cho điều kiện khác sai**. Chính sách cụ thể có thể cần nghĩa vụ như ghi audit, giới hạn tải xuống hoặc áp dụng kênh truy cập được bảo vệ.

## 8. Luồng quyết định truy cập sử dụng device posture

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant D as Thiết bị / Agent
    participant M as MDM / EDR / Posture Service
    participant I as IdP / SSO
    participant E as App / API / PEP
    participant P as PDP / Policy Engine
    participant R as Resource Service
    participant L as Audit

    D->>M: Báo cáo/bằng chứng sức khỏe và cấu hình
    M-->>I: Trạng thái đăng ký, compliance, rủi ro có nguồn và thời gian
    U->>I: Đăng nhập / tạo phiên từ thiết bị
    I->>I: Xác thực user và kiểm tra điều kiện thiết bị hỗ trợ
    I-->>U: Phiên/token phù hợp nếu đủ điều kiện
    U->>E: Yêu cầu action trên resource
    E->>E: Xác minh credential, issuer, audience, expiry
    E->>P: Subject, action, resource, session, device binding
    P->>M: Lấy/kiểm tra posture hiện tại hoặc assertion hợp lệ
    M-->>P: Trạng thái và độ mới bằng chứng
    P-->>E: Allow / Deny / Challenge hoặc remediation
    alt Đạt điều kiện
        E->>R: Kiểm tra quyền tài nguyên thực, thực thi
        R-->>U: Kết quả trong phạm vi được phép
    else Thiếu điều kiện
        E-->>U: Chặn hoặc yêu cầu khắc phục/xác thực bổ sung
    end
    E->>L: Ghi quyết định và lý do
    Note over M,E: Thay đổi posture có thể kích hoạt đánh giá lại phiên/truy cập
~~~

Sơ đồ chỉ thể hiện trách nhiệm logic; các sản phẩm có thể tích hợp trực tiếp tại IdP hoặc trong PEP/PDP, và không nhất thiết truy vấn MDM cho mỗi HTTP request. **Bằng chứng có thể được cache có kiểm soát**, nhưng phải thiết kế cách phản ánh trạng thái *noncompliant, retired, lost* và *unknown* kịp thời.

### Hai điểm thực thi quan trọng

**Điểm đăng nhập/SSO:** truy cập có điều kiện có thể từ chối hoặc yêu cầu đổi thiết bị khi tạo phiên mới. Đây là lớp bảo vệ có giá trị, nhưng không tự làm mọi access token/phiên ứng dụng đã phát hành biến mất.

**Điểm ứng dụng/API:** khi đọc tài nguyên nhạy cảm hoặc khi posture thay đổi, backend/PEP phải có cách kiểm tra trạng thái theo chính sách. Nhờ vậy một phiên đã tạo khi thiết bị tốt có thể bị giới hạn nếu sau đó thiết bị mất tuân thủ hoặc quyền nghiệp vụ đã đổi.

## 9. Vòng đời thiết bị và vòng đời danh tính JML

Quản lý device posture có quan hệ mật thiết với **identity lifecycle**. Một thiết bị có thể thuộc về công ty nhưng đã được chuyển chủ, mất hoặc nghỉ sử dụng; một nhân viên có thể active nhưng không còn được dùng thiết bị cũ.

### 9.1. Joiner — cấp thiết bị trước khi cấp truy cập nhạy cảm

Quy trình minh họa cho nhân viên mới:

1. Nguồn HR/hợp đồng xác minh người gia nhập, ngày bắt đầu, bộ phận, người quản lý và phạm vi quyền.
2. IAM tạo subject ID, user tại IdP và cấp quyền nghiệp vụ tối thiểu.
3. Bộ phận thiết bị bàn giao máy, liên kết **device record, owner và assignment** với người dùng đúng quy trình.
4. MDM/UEM thực hiện enroll, áp chính sách cấu hình, mã hóa, khóa màn hình, bảo vệ endpoint và xác nhận posture.
5. IdP và ứng dụng chỉ cho truy cập tài nguyên phù hợp khi **user active, role đúng và thiết bị đáp ứng điều kiện**.
6. Nếu thiết bị chưa sẵn sàng, người dùng được hướng dẫn enroll/khắc phục, hoặc dùng kênh truy cập thay thế được phê duyệt.

**Bẫy:** tạo tài khoản trên IdP hoặc cấp thiết bị vật lý thành công không đồng nghĩa rằng máy đã có bằng chứng compliance đáng tin tại thời điểm truy cập.

### 9.2. Mover — đổi vai trò, đổi thiết bị hoặc mức dữ liệu

Nhân viên Lan chuyển từ Support sang Finance. Thiết bị trước đây có thể đáp ứng chuẩn Support nhưng chưa đáp ứng chuẩn Finance, ví dụ thiếu yêu cầu bảo vệ dữ liệu tải xuống hoặc chưa thuộc nhóm máy quản trị phù hợp.

Cần phối hợp:

- **IAM:** tính lại desired entitlements, thu hồi quyền Support, phê duyệt quyền Finance.
- **Device management:** kiểm tra máy được phép dùng cho dữ liệu Finance, cập nhật baseline/chính sách hoặc cấp máy khác nếu cần.
- **IdP/SSO:** bảo đảm phiên mới được đánh giá với điều kiện thiết bị và mức xác thực tương ứng.
- **Application/API:** deny quyền Support đã bị gỡ, kiểm tra posture và quyền Finance theo yêu cầu hiện tại.
- **Reconciliation:** theo dõi thay đổi role, device assignment, SCIM provisioning và token/phiên đã tạo trước Mover.

Tránh hành vi chỉ thêm quyền Finance trong khi **role Support, quyền trực tiếp, API key và phiên cũ** vẫn hoạt động. Tình trạng thiết bị đúng không làm quyền cũ hợp lệ trở lại.

### 9.3. Leaver — thu hồi cả phiên và liên kết thiết bị

Khi người dùng nghỉ việc hoặc hợp đồng kết thúc:

1. Đặt user về trạng thái không còn được phép truy cập, thu hồi nhóm/role và quyền ứng dụng theo lịch hiệu lực.
2. Chặn đăng nhập mới, xử lý phiên/refresh token và các access token còn hạn theo khả năng kỹ thuật, đồng thời đối soát các ứng dụng đích.
3. **Thu hồi liên kết giữa user và device**, khóa hoặc retire device record, thu hồi chứng chỉ/khóa thiết bị theo quy trình.
4. Thu hồi máy vật lý hoặc thực hiện phương án xử lý thiết bị từ xa nếu có thẩm quyền và nền tảng hỗ trợ.
5. Thu hồi API key, PAT, SSH key và credential cá nhân độc lập với phiên SSO.
6. Chuyển ownership của những thiết bị/service account vẫn phục vụ nghiệp vụ cho owner mới, có phê duyệt và kiểm soát.
7. Kiểm thử quyền thực tế tại những ứng dụng quan trọng, ghi bằng chứng hệ thống đích đã chặn.

**Remote wipe không phải hành động đồng nghĩa với revoke quyền IAM.** Wipe có thể không thực thi khi thiết bị offline và có thể ảnh hưởng dữ liệu cá nhân ở BYOD. Cần phân biệt thu hồi phiên, thu hồi chứng chỉ, retire thiết bị, xóa dữ liệu công ty và xử lý tài sản vật lý theo chính sách.

### Ma trận trách nhiệm JML

| Sự kiện | Chủ sở hữu thường gặp | Thay đổi tại IdP/IAM | Thay đổi tại quản lý thiết bị | Bằng chứng hoàn tất |
|---|---|---|---|---|
| Joiner | HR + quản lý + IT | Tạo user, role chuẩn, điều kiện MFA | Enroll, baseline, owner, posture | Có thể đăng nhập đúng quyền từ máy phù hợp |
| Mover | HR + chủ sở hữu nghiệp vụ + IT | Gỡ quyền cũ, cấp quyền mới, đánh giá phiên | Đổi baseline, đổi owner/nhóm máy nếu cần | Không còn dùng quyền cũ; posture đủ cho nhiệm vụ mới |
| Leaver | HR + IAM + IT/Security | Disable/revoke/deprovision | Retire/unassign, xử lý thiết bị và chứng chỉ | Quyền bị chặn tại đích; tình trạng tài sản được xác nhận |
| Thiết bị mất | IT/Security + chủ thiết bị | Thu hồi/giới hạn các phiên và credential liên quan | Mark lost, khóa/retire, xử lý dữ liệu theo policy | Request từ thiết bị bị mất không còn được cho phép |
| Thiết bị thay chủ | IT + quản lý nghiệp vụ | Cập nhật session/device binding và quyền tương ứng | Wipe/re-enroll theo quy trình, gán owner mới | Không dùng lại phiên/credential của owner cũ |

## 10. BYOD, thiết bị không quản lý và các trường hợp ngoại lệ

**BYOD (Bring Your Own Device)** đòi hỏi cân bằng bảo mật, quyền riêng tư và khả năng hoàn thành công việc. Không phải mọi thiết bị cá nhân đều phải được quản lý ở mức tương đương máy công ty.

Một số mô hình có thể cân nhắc theo rủi ro:

| Mô hình | Trường hợp phù hợp | Kiểm soát và giới hạn |
|---|---|---|
| Thiết bị công ty được quản lý đầy đủ | Nhân sự dùng dữ liệu nhạy cảm, công việc quản trị | Enrollment, baseline, telemetry, xử lý mất thiết bị |
| BYOD có quản lý công việc trong vùng riêng | Công việc từ xa được chính sách cho phép | Quản lý dữ liệu/ứng dụng công việc theo khả năng nền tảng, giảm thu thập dữ liệu cá nhân |
| BYOD truy cập trình duyệt hạn chế | Xem nội dung ít nhạy cảm hoặc phục vụ tác vụ đơn giản | Giới hạn tải xuống, phiên, action và phạm vi dữ liệu nếu kiến trúc hỗ trợ |
| Virtual desktop / ứng dụng từ xa | Yêu cầu cô lập dữ liệu khi endpoint không đủ điều kiện | Kiểm soát kênh truy cập, clipboard, download; vẫn xác thực danh tính và quyền |
| Kiosk/thiết bị dùng chung | Quầy dịch vụ hoặc môi trường vận hành đặc biệt | Phiên theo từng người, logout rõ, quyền hẹp, không lưu credential người trước |
| Thiết bị legacy/IoT đặc biệt | Không cài MDM/EDR thông thường | Danh tính máy, segmentation, proxy, allowlist nhiệm vụ, giám sát và kiểm soát bù có ngày rà soát |

**Không nên áp dụng quy tắc “unmanaged = bị tấn công”** như kết luận sự cố. Unmanaged nói rằng hệ thống thiếu một số bằng chứng/khả năng quản lý; chính sách có thể hạn chế dữ liệu hoặc yêu cầu kênh khác. Với action nhạy cảm, thiếu bằng chứng bắt buộc thường dẫn tới deny.

### Ngoại lệ cần có phạm vi và thời hạn

Nếu một nhóm sử dụng thiết bị đặc biệt không thể đạt baseline, ngoại lệ nên ghi:

- Thiết bị/nhóm thiết bị và owner;
- Lý do, tài nguyên và action thực sự cần;
- Biện pháp kiểm soát bù;
- Người phê duyệt, ngày hiệu lực và ngày kết thúc;
- Chỉ số giám sát, điều kiện dừng và lần rà soát tiếp theo.

Đừng tạo nhóm **bypass-device-posture-forever** rồi cấp quyền nhạy cảm vô thời hạn. Một ngoại lệ phải được kiểm chứng tương đương với các quyền khác trong IAM.

## 11. Posture thay đổi giữa phiên: token, cache và thu hồi

Một thiết bị có thể compliant lúc 08:00 nhưng bị đánh dấu noncompliant lúc 09:10. Nếu ứng dụng chỉ kiểm tra posture khi tạo phiên SSO, **access token hoặc cookie đã phát hành trước 09:10 có thể còn được sử dụng**.

### Ví dụ dòng thời gian

~~~text
08:00  User đăng nhập SSO từ thiết bị dev-042, trạng thái compliant.
08:01  IdP cấp phiên; API chấp nhận access token đến 10:01.
09:10  EDR phát hiện rủi ro cao, device posture đổi thành noncompliant.
09:11  Hệ thống device gửi sự kiện thay đổi cho dịch vụ quản lý phiên.
09:12  PEP/PDP cập nhật hoặc làm mất hiệu lực cache cho dev-042.
09:13  User yêu cầu export dữ liệu bằng token cũ còn hạn.
09:13  API từ chối vì device hiện không còn đáp ứng yêu cầu.
09:20  Thiết bị được xử lý/khôi phục; có bằng chứng mới.
09:21  Policy đánh giá lại theo quyền hiện hành trước khi cho phép.
~~~

Nếu API chỉ kiểm tra chữ ký và thời gian JWT, nó có thể vẫn cho phép request lúc 09:13. **Việc device bị đặt thành noncompliant không tự thu hồi mọi token ở mọi ứng dụng.**

### Các kỹ thuật phối hợp

- **Token tuổi ngắn theo độ nhạy:** giảm thời gian dùng thông tin cũ, nhưng không tạo khả năng thu hồi tức thì.
- **Revocation/refresh token/session control:** chặn cấp token mới và quản lý phiên đang hoạt động theo công nghệ hỗ trợ.
- **Event-driven access evaluation:** sự kiện posture, mất thiết bị, user Leaver hoặc thay role kích hoạt đánh giá lại.
- **Kiểm tra tại request theo action:** với action nhạy cảm, có thể yêu cầu tín hiệu posture đủ mới từ PDP/nguồn có kiểm soát.
- **Cache theo chính sách:** giới hạn TTL của posture assertion/decision, có cách invalidation và theo dõi event bị trễ/mất.
- **Sender-constrained credential:** giảm khả năng token bị dùng từ thiết bị khác, nhưng không thay việc đánh giá posture của thiết bị gốc.

Khi thiết bị đang noncompliant, **step-up MFA không thay thế yêu cầu khắc phục thiết bị**. Nếu thiết bị bị mất hoặc đã retired, có thể cần thu hồi phiên và ràng buộc thiết bị thay vì chỉ yêu cầu xác thực lại người dùng.

### Một khung SLA minh họa

| Loại thay đổi | Ưu tiên phản ứng | Bằng chứng cần quan sát |
|---|---|---|
| Thiết bị bị báo mất/đánh cắp | Khẩn cấp theo quy trình rủi ro | Phiên/chứng chỉ/token liên quan bị hạn chế; request nhạy cảm bị chặn |
| EDR xác nhận rủi ro cao | Nhanh với dữ liệu quan trọng | Tín hiệu đến PEP/PDP và audit quyết định deny |
| Máy thiếu bản vá bắt buộc | Theo baseline và thời hạn khắc phục | Deadline, remediation, quyền bị giới hạn khi quá hạn |
| MDM mất kết nối | Theo độ mới tín hiệu và mức nhạy cảm | Chuyển trạng thái thành stale/unknown, policy áp dụng đúng |
| Thiết bị đổi owner | Trước khi bàn giao lại | Phiên/khóa cũ không được sử dụng; enrollment mới được xác nhận |

Không có một thời hạn tuyệt đối cho tất cả hệ thống. Tổ chức cần định nghĩa SLA theo rủi ro, khả năng công nghệ và mức nhạy cảm dữ liệu; sau đó **đo tại điểm truy cập thực tế**.

## 12. Xử lý trạng thái unknown, stale và lỗi nguồn posture

Đây là điểm dễ tạo lỗ hổng hoặc làm gián đoạn hoạt động. Cần phân biệt:

- **Compliant:** có bằng chứng đáng tin, đủ mới và thỏa chính sách.
- **Noncompliant:** có bằng chứng cho thấy một hoặc nhiều điều kiện không đạt.
- **Unknown:** không đủ bằng chứng để quyết định thiết bị đạt điều kiện.
- **Stale:** bằng chứng từng có nhưng đã vượt thời hạn chấp nhận.
- **Error/indeterminate:** thành phần kiểm tra không thể hoàn thành đánh giá.

**Không biến unknown/stale/error thành compliant bằng mặc định.**

### Ma trận xử lý lỗi minh họa

| Trạng thái | Hành động ít nhạy cảm | Hành động xuất dữ liệu/đặc quyền | Trải nghiệm và vận hành |
|---|---|---|---|
| Compliant, bằng chứng mới | Có thể allow nếu đủ quyền | Có thể allow nếu mọi điều kiện khác đạt | Không yêu cầu thao tác thừa |
| Noncompliant | Có thể giới hạn theo chính sách | Deny | Thông báo điều kiện cần khắc phục |
| Unknown chưa enroll | Có thể cho luồng enrollment hoặc tài nguyên giới hạn | Deny | Hướng dẫn đăng ký thiết bị |
| Stale do MDM offline | Cân nhắc cache còn hạn được phê duyệt | Deny khi bằng chứng mới là bắt buộc | Cung cấp trạng thái mất kết nối |
| Rủi ro cao từ EDR | Giới hạn hoặc khóa theo mức độ | Deny, kích hoạt điều tra | Có runbook Security/IT |
| PDP/Posture Service lỗi | Chế độ suy giảm đã định rõ | Fail closed với action nhạy cảm | Alert, correlation ID, phương án khôi phục |

Một số tổ chức có thể thiết kế **limited mode**: người dùng chỉ xem hướng dẫn khắc phục hoặc công việc ít nhạy cảm khi thiết bị chưa đạt, nhưng không thể tải dữ liệu trọng yếu. Phải bảo đảm đường khắc phục **không mở quyền rộng** và không để người dùng tự sửa trạng thái posture trên client để vượt qua chính sách.

### Các lỗi kỹ thuật cần nghĩ tới

1. **Sự kiện đến trễ hoặc sai thứ tự:** event “compliant” cũ đến sau “noncompliant” mới, khiến thiết bị được cho phép trở lại nếu không so version/timestamp.
2. **Event trùng lặp:** không được làm hệ thống cấp lại phiên/quyền cũ.
3. **Cache không được invalidation:** thiết bị retired nhưng API tiếp tục tin kết quả compliant cũ.
4. **Sai định danh thiết bị:** đổi tên máy hoặc re-enroll gây trùng record/owner.
5. **Clock skew:** thời điểm bằng chứng và kiểm tra lệch nhau, dẫn đến sai freshness.
6. **Mất kết nối:** nguồn posture và policy engine không đáp ứng, cần timeout/circuit breaker có kiểm soát.
7. **Tín hiệu chất lượng thấp:** EDR lỗi/false positive tạo deny nhầm; phải có xác minh và khắc phục phù hợp.

Nguồn posture cần xác thực, giới hạn quyền phát tín hiệu và chống **replay**. Độ mới và version không chỉ là metadata để hiển thị mà phải ảnh hưởng trực tiếp tới quyết định chính sách.

## 13. Thực thi quyền tại API: ví dụ kỹ thuật

Giả sử endpoint xuất dữ liệu khách hàng thuộc tenant. Một thiết kế có thể kiểm tra posture và authorization theo thứ tự hợp lý:

~~~java
// Java pseudocode: diễn giải trách nhiệm, chưa phải mã production.
ExportResult exportCustomers(AuthenticatedPrincipal caller, ExportRequest request) {
    AccessToken token = tokenVerifier.verify(
        caller.accessToken(),
        "crm-api" // expected audience
    );

    SubjectState subject = identityStore.currentState(token.subjectId());
    ExportScope scope = customerRepository.resolveAuthorizedScope(request.datasetId());

    DeviceBinding binding = deviceTrust.verifySessionDeviceBinding(
        caller.sessionId(),
        token,
        caller.presentedDeviceProof()
    );

    DevicePosture posture = deviceTrust.currentPosture(binding.deviceId());

    PolicyDecision decision = policyEngine.decide(
        subject,
        "customer.export",
        scope,                  // tenant, classification, owner từ backend
        caller.authContext(),  // mức/tuổi xác thực
        posture,               // nguồn, observedAt, status, risk
        binding
    );

    audit.record(
        subject.id(), "customer.export", scope.id(), decision,
        posture.observedAt(), policyEngine.version()
    );

    if (!decision.allowed()) {
        throw new AccessDeniedException("Access requirements not met");
    }

    return exportService.exportOnlyPermittedRecords(subject, scope);
}
~~~

**Cần hiểu giới hạn của pseudocode:** tên hàm chỉ minh họa API logic; sản phẩm thực cần xử lý lỗi, timeout, transaction, thông tin trả về không lộ dữ liệu, cache và những ràng buộc xác thực giao thức. Việc liên kết phiên với thiết bị phải có **bằng chứng bảo mật thực**, không phải hàm nhận một chuỗi ID bất kỳ từ trình duyệt.

Nếu API trả 200 cho thao tác export nhưng chứa dữ liệu của tenant khác, kiểm tra posture hoàn hảo vẫn không cứu được **lỗi authorization ở cấp đối tượng**.

### Những vị trí thường đặt PEP

- **Identity access policy:** điều kiện trước khi cấp phiên SSO.
- **API gateway/zero-trust proxy:** chặn request và kiểm tra một phần bằng chứng.
- **Backend/service:** kiểm tra action, resource ownership và tenant thực.
- **Data access layer:** row-level/column-level protection hoặc lọc dữ liệu tùy kiến trúc.
- **Privileged access entry point:** bastion/PAM hoặc kênh quản trị đã xác minh posture.

Có thể kết hợp nhiều lớp, nhưng cần tránh mâu thuẫn chính sách và bảo đảm backend **không bị gọi vòng qua đường kiểm tra**.

## 14. Device posture đối với service account và workload

Service account, CI/CD runner, máy chủ, container, VM và service-to-service client cũng là các **chủ thể truy cập**. Tuy nhiên, không nên áp nguyên mẫu tiêu chí laptop (khóa màn hình, mã hóa ổ người dùng, MDM) lên mọi workload.

### Tín hiệu phù hợp hơn với workload

| Loại workload | Bằng chứng có thể hữu ích | Kiểm soát truy cập |
|---|---|---|
| Server/VM quản lý tập trung | Inventory, agent protection, patch/vulnerability state, chứng chỉ máy | Service principal riêng, scope/resource policy |
| Kubernetes pod/service | Workload identity, service account binding, namespace, admission policy, image provenance | Quyền API tối thiểu, service mesh policy, segmentation |
| CI/CD runner | Danh tính job, repository/branch/environment, tính hợp lệ của runner và artifact | Token ngắn hạn, quyền deploy đúng môi trường, phê duyệt |
| SaaS integration | Client ID, credential vòng đời, owner, source allowlist khi phù hợp | Chỉ các API/tenant được ủy quyền |
| Thiết bị kiosk/IoT | Danh tính thiết bị, firmware/update status, attestation khi có, network segment | Proxy/gateway, quyền hẹp, kiểm soát thiết bị chuyên dụng |

Ví dụ bot đối soát hóa đơn chạy từ runner không còn được phép nên bị từ chối lấy token mới, kể cả API key cũ chưa hết hạn. Cần cơ chế **revoke/rotate**, giới hạn TTL và kiểm tra quyền tại API theo khả năng nền tảng.

Một workload chạy trong cluster “nội bộ” không có nghĩa được tin tự động. **Device/workload posture và workload identity** bổ trợ nhau: posture cho biết môi trường có đạt điều kiện hay không; identity và policy quyết định service được gọi action/resource nào.

### Tách danh tính máy khỏi danh tính người

Nếu pipeline dùng API key cá nhân của kỹ sư, khi kỹ sư Mover/Leaver việc thu hồi sẽ khó xác định tác động. Nên cấp danh tính workload riêng, có owner nhóm, scope hẹp, chứng thực ngắn hạn và quy trình thay owner/retire độc lập. Lịch sử audit phải quy trách nhiệm được cả **workload** và **người/phê duyệt triển khai** ở mức phù hợp.

## 15. Trải nghiệm khắc phục thiết bị và quyền riêng tư

Đối với người dùng hợp lệ, một quyết định **deny vì posture** cần chỉ ra đường khắc phục phù hợp và tránh lộ thông tin nhạy cảm.

### Luồng khắc phục

1. Ứng dụng thông báo truy cập bị hạn chế vì thiết bị chưa đáp ứng yêu cầu; không hiển thị chi tiết nhạy cảm của policy hoặc dữ liệu.
2. Người dùng nhận hướng dẫn cụ thể, chẳng hạn **cập nhật hệ điều hành**, bật mã hóa, khởi động lại agent hoặc liên hệ IT khi thiếu quyền khắc phục.
3. Hệ thống quản lý thiết bị thu thập lại tín hiệu, xác nhận chính sách và cập nhật thời điểm đánh giá.
4. IdP/PEP/PDP nhận trạng thái mới, vô hiệu hóa cache cũ theo thiết kế.
5. Người dùng thử lại; **quyền nghiệp vụ vẫn được kiểm tra** trước khi cho phép action.
6. Nếu tiếp tục thất bại, tạo ticket có correlation ID và thông tin đủ điều tra, không thu thập bí mật xác thực.

Không nên chỉ hiện “Access denied” trong khi người dùng không có cách biết mình cần cập nhật máy hay xin quyền tài nguyên. Đồng thời không nên hướng dẫn người dùng vô hiệu hóa EDR hoặc giảm chính sách để qua kiểm tra.

### Quyền riêng tư khi dùng BYOD

Posture có thể liên quan dữ liệu nhạy cảm của người dùng nếu thu thập quá mức. Thiết kế cần:

- **Giảm thiểu dữ liệu:** chỉ nhận trạng thái cần thiết, ví dụ compliant/noncompliant và lý do đã chuẩn hóa, thay vì thu toàn bộ danh sách ứng dụng cá nhân.
- **Giới hạn mục đích:** sử dụng vì bảo mật truy cập với thông báo và chính sách tổ chức phù hợp.
- **Hạn chế quyền truy cập telemetry:** dữ liệu thiết bị chỉ cho các vai trò cần thiết; ghi audit khi thay đổi/đọc dữ liệu.
- **Lưu giữ có thời hạn:** định nghĩa retention cho thông tin posture, event và hồ sơ xử lý.
- **Phân biệt công ty/cá nhân:** với BYOD, quản lý dữ liệu công việc theo cơ chế phù hợp; thao tác xóa từ xa cần đúng phạm vi được cho phép.
- **Tránh theo dõi không cần thiết:** không dùng vị trí chính xác, ảnh chụp màn hình hoặc dữ liệu đời sống riêng nếu không có căn cứ.
- **Cơ chế phản hồi sai lệch:** người dùng có thể yêu cầu IT kiểm tra trạng thái false noncompliant và được hướng dẫn làm việc qua kênh hợp lệ.

Độ tin cậy của tín hiệu và mức xâm phạm quyền riêng tư là hai tiêu chí cần được đánh giá cùng nhau.

## 16. Kiểm toán và chỉ số vận hành

Một quyết định sử dụng posture nên cho phép truy vết **thiết bị nào, bằng chứng từ đâu, mới đến mức nào, chính sách nào được áp dụng, ai yêu cầu hành động gì và kết quả ra sao**.

### Bản ghi audit minh họa

~~~json
{
  "timestamp": "2026-11-23T07:12:18Z",
  "event_type": "access_decision",
  "correlation_id": "req-73b1",
  "subject_id": "usr-204",
  "device_id": "dev-042",
  "device_binding_status": "verified",
  "device_lifecycle_state": "active",
  "posture_status": "noncompliant",
  "posture_evidence_source": "corporate-device-posture-service",
  "posture_observed_at": "2026-11-23T07:11:40Z",
  "application": "crm-api",
  "action": "customer.export",
  "resource_scope": "tenant-A",
  "policy_id": "crm.customer.export",
  "policy_version": 6,
  "decision": "deny",
  "reason_code": "DEVICE_POSTURE_NOT_MET"
}
~~~

Đây là **schema minh họa**. Tránh ghi access/refresh token, mật khẩu, private key, session cookie và dữ liệu khách hàng nguyên văn vào audit. Cần bảo đảm **tính toàn vẹn, đồng bộ thời gian, phân quyền xem và lưu giữ đúng chính sách**.

### Các chỉ số đề xuất

| Chỉ số | Cách tính/đọc | Ý nghĩa |
|---|---|---|
| **Managed device coverage** | Tỷ lệ thiết bị thuộc phạm vi yêu cầu đã được enroll/ghi owner | Đánh giá độ phủ quản lý |
| **Compliant device rate** | Tỷ lệ thiết bị đủ điều kiện trong tập mục tiêu, phân theo loại và đơn vị | Theo dõi chất lượng baseline |
| **Posture freshness** | Độ tuổi tín hiệu tại lúc ra quyết định; p95/p99 và số vượt TTL | Phát hiện thiết bị offline, cache cũ |
| **Risk-to-enforcement latency** | Từ lúc nguồn ghi nhận trạng thái rủi ro đến khi action nhạy cảm bị chặn | Đo tốc độ phản ứng thực tế |
| **Unknown/stale decision rate** | Tỷ lệ request có posture unknown/stale theo action | Phát hiện thiếu telemetry và độ ổn định |
| **Remediation completion time** | Từ deny do posture đến khi thiết bị đạt lại chính sách | Đo trải nghiệm khắc phục và năng lực IT |
| **False posture denial rate** | Tỷ lệ deny bị xác minh là sai trong số sự kiện được điều tra | Cân bằng chất lượng tín hiệu và tác động |
| **Device lifecycle drift** | Số thiết bị lost/retired/đổi owner vẫn có phiên/credential active | Phát hiện quyền tồn dư gắn thiết bị |
| **Policy coverage** | Tỷ lệ action nhạy cảm thực sự sử dụng tín hiệu thiết bị khi quy định | Tránh chỉ kiểm tra ở màn hình đăng nhập |
| **BYOD exception age** | Số ngoại lệ quá hạn hoặc thiếu owner | Phát hiện đường bypass tồn tại lâu |

**Không nên kết luận hiệu quả bảo mật chỉ từ tỷ lệ compliant.** Một tổ chức có 99% thiết bị compliant nhưng API xuất dữ liệu không hề kiểm tra posture hoặc tenant vẫn có rủi ro lớn. Đánh giá cần kết hợp **chính sách, khả năng thực thi và thử nghiệm theo rủi ro**.

## 17. Ma trận kiểm thử Device posture

Mỗi kiểm thử nên có principal, device record, resource, action và kết quả dự kiến rõ ràng. Dùng môi trường/thiết bị có ủy quyền và dữ liệu thử nghiệm khi thực hiện.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| D1 | User active, đúng role/tenant, thiết bị managed + compliant, bằng chứng mới | Allow nếu mọi điều kiện khác đạt |
| D2 | Cùng user thử đọc bản ghi tenant khác | Deny do sai resource scope dù thiết bị compliant |
| D3 | Thiết bị managed nhưng thiếu mã hóa bắt buộc | Deny action nhạy cảm và hướng dẫn remediation |
| D4 | Device ID được khai bằng header client nhưng không có binding đáng tin | Không coi posture đã được chứng minh; deny action yêu cầu device trust |
| D5 | Thiết bị bị đánh dấu lost/retired sau khi phiên tạo | Chặn đường truy cập nhạy cảm trong SLA |
| D6 | Posture evidence quá TTL | Xử lý stale, không dùng như compliant vô hạn |
| D7 | MDM tạm mất kết nối, endpoint cần export | Deny/fail closed khi thiếu bằng chứng bắt buộc |
| D8 | EDR phát cảnh báo rủi ro cao giữa phiên | Đánh giá lại, hạn chế action theo chính sách và ghi audit |
| D9 | Token còn hạn, thiết bị đổi thành noncompliant | Không tiếp tục cho phép action nhạy cảm chỉ vì JWT hợp lệ |
| D10 | User hoàn thành MFA mạnh trên thiết bị noncompliant | Không tự chuyển thành compliant; vẫn cần xử lý posture |
| D11 | User vừa Mover, máy compliant nhưng role cũ đã gỡ | Deny quyền cũ ở API |
| D12 | User Leaver còn local session/app token | Truy cập bị chặn theo SLA offboarding |
| D13 | BYOD unmanaged truy cập tài nguyên chỉ dành cho máy quản lý | Deny hoặc chuyển sang luồng làm việc được phê duyệt |
| D14 | Event compliant cũ đến sau event noncompliant mới | Không ghi đè trạng thái mới; dùng version/timestamp tin cậy |
| D15 | Workload dùng credential hợp lệ nhưng gọi API ngoài scope | Deny theo authorization |
| D16 | Một kiosk đổi người dùng | Không tái sử dụng phiên/quyền của người dùng trước |
| D17 | Hệ thống policy lỗi | Action nhạy cảm fail closed theo thiết kế; audit có reason |
| D18 | Thiết bị đã remediation thành công và có bằng chứng mới | Cho phép lại chỉ những action đúng quyền |

### Kiểm thử sâu đối với thiết bị mất

Giả sử người dùng báo mất laptop lúc 14:00. Bài kiểm thử cần ghi:

1. **14:00:** nguồn tài sản/IT đánh dấu device lost và ghi ticket.
2. **Sau sự kiện:** IdP/PEP/PDP nhận trạng thái mới hoặc kích hoạt cơ chế chặn đủ nhanh.
3. **Với phiên còn hạn:** thử request được phép trước đây trong môi trường kiểm thử có ủy quyền; xác nhận action nhạy cảm bị deny.
4. **Với token mới:** kiểm tra thiết bị mất không thể lấy credential đủ điều kiện truy cập.
5. **Với key/chứng chỉ cũ:** xác nhận đường truy cập phụ đã bị thu hồi hoặc hạn chế.
6. **Với thiết bị thay thế:** user cần enrollment/binding mới, quyền nghiệp vụ được kiểm tra lại.

Đây là cách chứng minh **device lifecycle đã tác động đến thực thi IAM**, vượt qua việc chỉ nhìn thấy cờ “lost” trong bảng MDM.

## 18. Bài tập tình huống: máy công ty, BYOD và một phiên cũ

### Bối cảnh

Công ty sử dụng IdP + SSO, MDM/UEM và EDR cho ứng dụng CRM và Finance. Nhân viên Hương làm việc trong Finance, có quyền **invoice.read** cho tenant A và quyền phê duyệt thanh toán theo workflow. Chính sách nội bộ yêu cầu máy managed và compliant khi xem tài chính nhạy cảm; duyệt thanh toán còn cần MFA đủ mức và kiểm tra SoD.

Tại 09:00 có ba tình huống:

- **Thiết bị A:** laptop công ty, managed, compliant lúc 08:55, EDR healthy, posture assertion gắn đúng phiên.
- **Thiết bị B:** laptop cá nhân chưa enroll, kết nối mạng VPN công ty và đã đăng nhập SSO bằng MFA.
- **Thiết bị C:** laptop công ty đã managed, nhưng EDR phát cảnh báo rủi ro cao lúc 08:59. Access token Finance trên C phát hành từ 08:30 và còn hạn.
- **09:10:** HRIS ghi Hương chuyển sang bộ phận không còn quyền Finance; SCIM ứng dụng Finance chưa xử lý thành công.

Hương yêu cầu ba hành động:

1. Xem hóa đơn của tenant A từ thiết bị A trước khi Mover có hiệu lực.
2. Duyệt khoản thanh toán do chính mình tạo từ thiết bị B.
3. Sau Mover, đọc hóa đơn Finance bằng access token cũ từ thiết bị C.

### Câu hỏi

1. Với mỗi hành động, nên allow/deny/step-up trong điều kiện đã nêu? Giải thích từng lớp.
2. Vì sao kết nối VPN và MFA trên B không thay thế trạng thái thiết bị?
3. Vì sao access token còn hạn trên C không đủ để tiếp tục truy cập?
4. Thiết kế các event và cách xác nhận việc thu hồi khi Mover xảy ra.
5. Nếu MDM mất kết nối 30 phút và policy yêu cầu bằng chứng mới cho hành động nhạy cảm, ứng dụng cần xử lý thế nào?
6. Đề xuất hai chỉ số để đánh giá cả **bảo mật** và **trải nghiệm người dùng**.

### Hướng dẫn lời giải

**Hành động 1:** Có thể **allow** vì người dùng có quyền đọc đúng tenant, thiết bị A managed/compliant với bằng chứng mới và phiên đạt yêu cầu, giả sử không có điều kiện khác chưa đáp ứng. Vẫn cần kiểm tra thuộc tính invoice ở backend.

**Hành động 2:** **Deny** do SoD: người tạo không được tự duyệt. Thiết bị B cũng không đạt yêu cầu managed/compliant cho hành động nhạy cảm. **MFA mạnh hoặc kết nối VPN không cấp thêm authorization** và không chứng minh posture. Sau khi khắc phục thiết bị, SoD vẫn khiến action bị từ chối.

**Hành động 3:** **Deny** vì quyền Finance đã bị thu hồi theo Mover và thiết bị C đã có tín hiệu rủi ro cao. JWT chưa hết hạn chỉ phản ánh một số claim tại thời điểm phát hành. Cần đánh giá quyền hiện tại và posture mới; xử lý phiên/token theo kiến trúc thu hồi. Nếu ứng dụng chỉ kiểm tra JWT offline, đây là khoảng hở phải khắc phục.

**Event cần theo dõi:** thời điểm HRIS thay đổi vai trò, desired entitlements mới, lệnh SCIM/revoke, xác nhận ở Finance, trạng thái session/token, cập nhật quyền tại PDP, event noncompliant từ EDR và các quyết định deny/allow sau thời điểm Mover. Giám sát đích lỗi đến khi thu hồi thực tế được xác minh.

**Mất MDM:** Không tự coi thiết bị compliant khi thiếu bằng chứng mới bắt buộc; với action nhạy cảm, áp dụng deny/fail-closed hoặc luồng khắc phục, ghi lý do và cảnh báo. Một thao tác ít rủi ro có thể có chính sách cache hạn chế riêng nếu được phê duyệt.

**Chỉ số:** Đo **risk-to-enforcement latency** từ rủi ro thiết bị đến API deny; đo **false posture denial/remediation completion time** để cải thiện trải nghiệm và chất lượng tín hiệu. Có thể bổ sung revocation latency sau Mover và tỷ lệ unknown/stale của tín hiệu.

## 19. Checklist triển khai và tài liệu đọc tiếp

### Checklist

- [ ] Có định nghĩa nhất quán về **device identity, managed, compliant, healthy, unknown, stale**.
- [ ] Biết nguồn authoritative cho owner, enrollment, compliance, EDR risk và lifecycle state.
- [ ] Chứng minh được posture gắn với **thiết bị/phiên gửi request**, không tin header client tự khai.
- [ ] Policy sử dụng subject, action, resource, tenant, ngữ cảnh và posture phù hợp mức nhạy cảm.
- [ ] Backend kiểm tra quyền ở cấp tài nguyên; thiết bị compliant không cấp thêm role/tenant.
- [ ] IdP/SSO và PEP/API có phương án đánh giá lại khi posture đổi giữa phiên.
- [ ] Posture evidence có timestamp, nguồn, version/TTL; cache và event có cơ chế invalidation.
- [ ] Có xử lý rõ cho noncompliant, unknown, stale, lost, retired và policy-source outage.
- [ ] Luồng Joiner gắn user-device đúng, Mover đánh giá lại baseline, Leaver thu hồi phiên và thiết bị.
- [ ] BYOD có chính sách riêng, giới hạn dữ liệu và bảo vệ quyền riêng tư.
- [ ] Thiết bị đặc biệt/workload có kiểm soát phù hợp loại môi trường, có owner và danh tính riêng.
- [ ] Có UX remediation, runbook IT/Security và ngoại lệ scope hẹp có thời hạn.
- [ ] Audit có nguồn, độ mới, policy và kết quả; không log credential hay dữ liệu cá nhân quá mức.
- [ ] Kiểm thử token cũ, device lost, EDR risk, sai binding, cross-tenant, event out-of-order và fail-closed.
- [ ] Đo risk-to-enforcement latency, posture freshness, coverage và false deny.

### Từ khóa quan trọng

| Thuật ngữ | Ghi nhớ |
|---|---|
| **Device posture** | Tập hợp bằng chứng về mức đáp ứng yêu cầu bảo mật của thiết bị |
| **Device identity** | Cách nhận diện và xác thực thiết bị phù hợp với hệ thống |
| **MDM/UEM** | Quản lý thiết bị/endpoint, enrollment, cấu hình và compliance |
| **EDR** | Phát hiện/ứng phó rủi ro ở endpoint; cung cấp tín hiệu bổ trợ |
| **Managed vs. compliant** | Được quản lý không đồng nghĩa đang đạt mọi chính sách |
| **Device binding** | Liên kết bằng chứng thiết bị với session/request thực |
| **Attestation** | Bằng chứng có thể kiểm tra về một số thuộc tính nền tảng/hệ thống |
| **Posture freshness** | Độ mới và hạn sử dụng của bằng chứng trạng thái thiết bị |
| **Conditional access** | Điều kiện truy cập theo danh tính, thiết bị, ứng dụng và rủi ro |
| **RBAC/ABAC** | Quyền theo vai trò / quyền theo thuộc tính và ngữ cảnh |
| **PEP/PDP** | Điểm thực thi và điểm quyết định chính sách |
| **BYOD** | Sử dụng thiết bị cá nhân cho công việc theo chính sách |
| **JML** | Joiner–Mover–Leaver: quản lý danh tính khi gia nhập, đổi vai trò, rời đi |
| **Residual access** | Phiên, token, quyền hoặc credential còn dùng được dù không còn ủy quyền |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** đánh giá danh tính, trạng thái thiết bị, ngữ cảnh và điều kiện truy cập trong kiến trúc Zero Trust.
- **NIST SP 800-63 — Digital Identity Guidelines:** khái niệm xác thực người dùng, mức bảo đảm, quản lý phiên và bằng chứng xác thực.
- **NIST SP 800-53 — Security and Privacy Controls:** các nhóm kiểm soát truy cập, cấu hình, hệ thống/thiết bị, xác thực và kiểm toán.
- **NIST SP 800-124 — Guidelines for Managing the Security of Mobile Devices in the Enterprise:** quản lý bảo mật thiết bị di động.
- **RFC 7643 / RFC 7644 — SCIM:** mô hình và giao thức đồng bộ tài khoản/nhóm liên quan đến vòng đời IAM.
- **OpenID Connect / OAuth 2.0:** phiên/token và những ràng buộc cần đánh giá khi tín hiệu thay đổi.
- **OWASP API Security Top 10:** các lỗi về authorization, đặc biệt kiểm soát quyền ở cấp đối tượng và chức năng.

**Điểm cần ghi nhớ:** Device posture giúp trả lời **“thiết bị đang dùng có đủ điều kiện bảo mật cho yêu cầu này, ở thời điểm này, dựa trên bằng chứng có thể xác minh không?”**. Để vận hành đúng trong Zero Trust IAM, câu trả lời phải được gắn với người dùng, phiên, hành động và tài nguyên thực; phản ánh thay đổi theo **JML**, xử lý tín hiệu lỗi thời, và có khả năng **chặn quyền truy cập tồn dư ngay cả khi một token cũ vẫn còn hạn**.
