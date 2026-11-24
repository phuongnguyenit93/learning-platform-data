# Đăng ký thiết bị (Device enrollment) trong IAM

> **Chương:** Identity enrollment  
> **Chủ đề:** Đăng ký thiết bị và đưa thiết bị vào phạm vi quản lý danh tính, quyền truy cập.  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Bối cảnh học tập:** Quản lý vòng đời danh tính theo Joiner–Mover–Leaver (JML), kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và xử lý quyền truy cập tồn dư.

## 1. Vì sao cần đăng ký thiết bị?

Một nhân viên có thể xác thực đúng tên đăng nhập, mật khẩu và MFA nhưng đang dùng một máy tính bị mất quyền quản lý, hệ điều hành quá cũ hoặc thiết bị không được tổ chức chấp nhận. Với tài nguyên nhạy cảm, **biết người dùng là ai chưa đủ**: hệ thống còn cần biết thiết bị nào đang tham gia và mức độ tin cậy của thiết bị đó.

Giả sử nhân viên Lan được cấp tài khoản công ty và quyền xem báo cáo tài chính. Lan đăng nhập từ ba thiết bị:

- Laptop công ty đã được đăng ký, có chính sách quản lý, mã hóa ổ đĩa và bản vá phù hợp.
- Điện thoại cá nhân được cho phép truy cập email nhưng chưa được quản lý toàn bộ.
- Máy tính công cộng không được tổ chức biết đến.

Cả ba đều có thể đưa ra thông tin xác thực của Lan. Tuy nhiên, quyết định truy cập nên khác nhau tùy **chính sách, loại tài nguyên, mức độ quản lý và tín hiệu rủi ro**. Đối với báo cáo tài chính, doanh nghiệp có thể chỉ cho tải tệp trên thiết bị đáp ứng yêu cầu kiểm soát; trên thiết bị chưa đạt yêu cầu, hệ thống từ chối hoặc chỉ cho truy cập hạn chế nếu chính sách hỗ trợ.

**Đăng ký thiết bị (device enrollment)** là quá trình nhận diện và đưa một thiết bị vào quan hệ quản lý/tin cậy phù hợp để phục vụ quản trị thiết bị, kiểm soát truy cập và vận hành vòng đời. Tùy sản phẩm, enrollment có thể bao gồm đăng ký với hệ thống quản lý thiết bị (MDM/UEM), thiết lập danh tính thiết bị với IdP, cấp chứng chỉ hoặc cấu hình kiểm soát bảo mật.

Điểm cần nhớ ngay từ đầu: **đăng ký thành công không tự động đồng nghĩa thiết bị an toàn, người dùng có mọi quyền, hoặc mọi truy cập đều được chấp nhận**.

## 2. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Mục đích chính | Bằng chứng/trạng thái thường gặp | Điều không tự bảo đảm |
|---|---|---|---|
| **Device registration** | Gắn thiết bị với một hệ thống danh tính hoặc danh mục thiết bị | Device ID, bản ghi đăng ký, khóa/chứng chỉ thiết bị | Thiết bị đã được quản lý đầy đủ hoặc tuân thủ chính sách |
| **Device enrollment** | Đưa thiết bị vào quy trình quản lý/tin cậy, thường qua MDM/UEM | Hồ sơ enrollment, kênh quản lý, cấu hình nhận từ hệ thống | Mọi bản vá, mọi ứng dụng và mọi tín hiệu rủi ro đều đạt yêu cầu |
| **Directory/device join** | Liên kết thiết bị với miền/directory hoặc mô hình tham gia IdP cụ thể | Trạng thái join, đối tượng directory, cơ chế đăng nhập hệ điều hành | MDM đã triển khai chính sách hoặc mọi tài khoản local đã kiểm soát |
| **Device identity** | Biểu diễn thiết bị như một chủ thể kỹ thuật có thể nhận biết | ID ổn định, public key, certificate, attestation metadata | Người đang cầm thiết bị được quyền truy cập tài nguyên |
| **Device compliance** | Đánh giá thiết bị có đáp ứng bộ chính sách hiện tại không | Mã hóa, phiên bản OS, trạng thái bảo vệ, chính sách mật mã | Thiết bị không bị xâm nhập hoặc không có rủi ro khác |
| **Device posture** | Tập tín hiệu về tình trạng và mức rủi ro tại một thời điểm | EDR, sức khỏe thiết bị, quản lý, cập nhật, phát hiện bất thường | Tín hiệu luôn chính xác hoặc luôn được cập nhật tức thời |
| **Conditional access** | Ra quyết định truy cập có xét các điều kiện của yêu cầu | User, app, device, vị trí/ngữ cảnh, rủi ro | Không thay thế quyền truy cập bên trong từng ứng dụng |
| **Device deprovisioning** | Rút thiết bị khỏi quan hệ quản lý/tin cậy khi không còn hợp lệ | Khóa, thu hồi chứng chỉ/khóa, gỡ đăng ký, xóa dữ liệu được quản lý | Mọi phiên ứng dụng hoặc dữ liệu đã tải từ trước tự biến mất |

Các thuật ngữ có thể được đặt tên khác nhau trên từng nền tảng. Khi thiết kế IAM, hãy xác định chính xác **enrollment ở hệ thống nào** và **trạng thái nào có thể được hệ thống cấp quyền tiêu thụ**.

### 2.1. Đăng ký thiết bị không đồng nghĩa cấp tài khoản người dùng

Người dùng và thiết bị là hai loại chủ thể khác nhau:

- **User identity:** đại diện cho nhân viên, nhà thầu hoặc đối tác; quyền thường gắn với nhiệm vụ và vai trò.
- **Device identity:** đại diện cho thiết bị hoặc môi trường thực thi; tín hiệu có thể được dùng để quyết định thiết bị có đủ điều kiện truy cập.
- **Application identity:** đại diện cho ứng dụng/workload, chẳng hạn tác vụ đồng bộ hoặc agent được chạy trên thiết bị.

Một laptop có thể được nhiều người sử dụng theo ca; một người có thể có nhiều laptop/điện thoại. Quan hệ **user–device** là dữ liệu cần quản lý, không nên coi tên người dùng lưu ở thiết bị là chứng cứ vĩnh viễn về quyền sở hữu.

### 2.2. MDM/UEM, IdP và EDR làm những việc khác nhau

- **MDM (Mobile Device Management)/UEM (Unified Endpoint Management)** thường xử lý enrollment, cấu hình, kiểm tra tuân thủ, triển khai ứng dụng và thao tác quản lý từ xa theo khả năng nền tảng.
- **IdP (Identity Provider)** xác thực người dùng/ứng dụng, quản lý một số đối tượng danh tính thiết bị tùy sản phẩm và hỗ trợ chính sách truy cập theo tín hiệu thiết bị.
- **EDR (Endpoint Detection and Response)** thu thập và phản ứng với dấu hiệu đe dọa trên endpoint; tín hiệu này có thể được đưa vào chính sách nếu có tích hợp.
- **Hệ thống tài sản/CMDB** hỗ trợ trả lời thiết bị thuộc ai, đang ở đâu, tình trạng cấp phát và lịch sử bàn giao.
- **Ứng dụng đích** thực thi quyền đối với chức năng, API và dữ liệu của chính nó.

Các hệ thống có thể cùng tham gia một workflow nhưng không nên suy ra rằng một trạng thái “enrolled” trong MDM tự động đủ để mọi IdP, API và ứng dụng chấp nhận thiết bị.

## 3. Mô hình danh tính thiết bị và quan hệ với người dùng

Hệ thống cần một bản ghi đủ rõ để phát hiện thiết bị trùng, xác định owner và thu hồi khi cần.

| Trường/quan hệ | Mục đích | Ví dụ minh họa |
|---|---|---|
| Device ID nội bộ | Nhận diện bản ghi không phụ thuộc tên hiển thị | dev-8c24 |
| Nguồn đăng ký | Xác định nơi tạo trạng thái tin cậy | corporate-enrollment |
| Asset ID/serial (nếu thích hợp) | Đối chiếu tài sản, bảo hành, tồn kho | asset-LT-024 |
| Chủ sở hữu tài sản | Công ty hay cá nhân | corporate |
| Người dùng/nhóm đang được cấp | Xác định trách nhiệm và phạm vi dùng | employee-1042 |
| Loại và môi trường | Laptop, điện thoại, kiosk, thiết bị IoT | laptop / production-user |
| Enrollment state | Chưa đăng ký, chờ duyệt, enrolled, suspended, retired | enrolled |
| Compliance state và thời điểm | Tín hiệu đạt/không đạt/chưa biết và độ mới của dữ liệu | compliant, checkedAt |
| Khóa/chứng chỉ hoặc trust binding | Liên kết đăng ký với bằng chứng thiết bị | certificate thumbprint |
| Quyền được phép / hạn chế | Các chính sách truy cập theo ứng dụng/dữ liệu | finance-report:managed-device-required |
| Owner vận hành | Đơn vị có trách nhiệm xử lý | endpoint-security |
| Sự kiện vòng đời | Lịch sử cấp, chuyển giao, mất, thu hồi | device-retired |

**Không coi serial number, địa chỉ MAC, tên máy hoặc một trường do client tự khai báo là bằng chứng xác thực mạnh.** Những giá trị đó có thể dùng để hỗ trợ quản lý tài sản, nhưng khả năng chứng minh thiết bị hợp lệ phụ thuộc cơ chế khóa, chứng chỉ, trust và mức xác thực nguồn.

### 3.1. Liên kết danh tính thiết bị với chứng cứ mật mã

Một số nền tảng có thể tạo/cấp khóa cho thiết bị, giữ khóa riêng trong phần cứng bảo vệ như TPM hoặc Secure Enclave khi hỗ trợ, và dùng chứng chỉ hoặc bằng chứng đã ký để chứng minh quyền kiểm soát khóa.

Điều quan trọng:

1. **Đăng ký khóa:** một khóa công khai được liên kết với bản ghi thiết bị sau khi quy trình enrollment xác nhận điều kiện hợp lệ.
2. **Bảo vệ khóa riêng:** ưu tiên cơ chế không xuất khóa nếu khả năng phần cứng/nền tảng cho phép; hạn chế sao chép credential.
3. **Thử thách–phản hồi hoặc phiên xác thực phù hợp:** hệ thống xác minh thiết bị đang kiểm soát khóa liên kết, thay vì chỉ tin một ID gửi qua request.
4. **Quản lý hạn sử dụng:** chứng chỉ/khóa có thời hạn, chính sách xoay vòng và khả năng thu hồi.
5. **Phân tách chủ thể:** chứng minh thiết bị là thiết bị đã đăng ký **không chứng minh** người đang sử dụng được quyền đọc dữ liệu.

Một thiết bị đã có certificate vẫn có thể không tuân thủ chính sách hoặc đã bị xâm nhập; do đó kiểm tra khóa chỉ là một tín hiệu trong quyết định truy cập.

### 3.2. Device attestation làm được gì?

**Attestation** là cơ chế cung cấp bằng chứng về một số thuộc tính của thiết bị hoặc trạng thái môi trường thực thi, thường dựa trên thành phần tin cậy của nền tảng. Bên xác minh đánh giá bằng chứng theo chính sách: nguồn phát, tính toàn vẹn, thời điểm, các phép đo và mức độ tin cậy được hỗ trợ.

Attestation hữu ích khi muốn tăng độ tin cậy vào nguồn gốc thiết bị/khóa hoặc một số đặc điểm khởi động. Tuy nhiên, nó **không** thay việc xác minh owner, không khẳng định toàn bộ phần mềm luôn an toàn, không bảo đảm dữ liệu sẽ không bị lộ và không tự cấp quyền nghiệp vụ.

## 4. Quy trình enrollment từ yêu cầu đến thiết bị được tin cậy

Quy trình cụ thể phụ thuộc loại thiết bị và nền tảng. Ví dụ dưới đây giả định tổ chức muốn quản lý laptop công ty trước khi cho phép truy cập hệ thống tài chính.

~~~mermaid
flowchart TD
    A[Thiết bị mới hoặc có yêu cầu đăng ký] --> B[Xác định owner, loại thiết bị, nguồn cấp phát]
    B --> C{Đủ điều kiện enrollment?}
    C -- Không --> X[Từ chối, ghi lý do, hướng dẫn xử lý]
    C -- Có --> D[Xác minh người thực hiện và tính hợp lệ của thiết bị]
    D --> E[Thiết lập hồ sơ quản lý và danh tính thiết bị]
    E --> F[Phân phối cấu hình, khóa/chứng chỉ theo khả năng nền tảng]
    F --> G[Thu thập tín hiệu tuân thủ và độ mới]
    G --> H{Đáp ứng policy?}
    H -- Không hoặc chưa biết --> I[Hạn chế truy cập, khắc phục hoặc rà soát]
    H -- Có --> J[Thiết bị được xét cho quyền truy cập theo ứng dụng]
    J --> K[Đối soát trạng thái và lưu dấu vết audit]
    I --> G
    K --> L[Rà soát liên tục, Mover/Leaver khi có sự kiện]
~~~

### Bước 1: xác định yêu cầu và nguồn có thẩm quyền

Hệ thống cần biết thiết bị được đăng ký theo luồng nào:

- Laptop của doanh nghiệp được đặt hàng/cấp phát qua danh mục tài sản.
- Điện thoại BYOD đăng ký theo chính sách cho phép sử dụng thiết bị cá nhân.
- Máy dùng chung tại quầy, phòng lab hoặc địa điểm sản xuất.
- Thiết bị chuyên dụng/IoT do một nhóm vận hành chịu trách nhiệm.

**Không nên tự động chấp nhận mọi yêu cầu do một người dùng có tài khoản hợp lệ gửi**, đặc biệt với thiết bị có thể truy cập dữ liệu nhạy cảm. Quy trình phải quy định nguồn chứng nhận tài sản hoặc quyền enrollment, loại thiết bị cho phép, số lượng, người phê duyệt và hạn chế cần thiết.

### Bước 2: xác minh người đăng ký và tính hợp lệ của thiết bị

Xác minh người có quyền đăng ký và quan hệ của họ với thiết bị. Tùy mô hình, có thể yêu cầu người dùng đăng nhập MFA, thiết bị nằm trong danh sách tài sản công ty hoặc nguồn cấp phát tự động đã được phê duyệt.

Cần tránh hai nhầm lẫn:

- **MFA của người đăng ký** xác minh một phiên người dùng; bản thân nó không chứng minh mọi thuộc tính phần cứng của thiết bị.
- **Thiết bị nằm trong danh sách mua sắm** chưa đủ để khẳng định thiết bị đang thực sự kiểm soát khóa danh tính đã được đăng ký.

Với hệ thống hỗ trợ attestation hoặc đăng ký gắn khóa, kiểm tra bổ sung có thể giúp giảm nguy cơ giả mạo thiết bị.

### Bước 3: đăng ký danh tính và kênh quản lý

Tạo hoặc liên kết bản ghi device identity với owner, loại thiết bị và enrollment source. Khi dùng MDM/UEM, thiết lập kênh quản lý, chứng chỉ/hồ sơ cấu hình và các quyền quản trị theo chính sách.

Tài khoản đăng ký của người dùng không nên được mặc định là owner vĩnh viễn: cần hỗ trợ chuyển giao thiết bị, người dùng thay thế và kết thúc cấp phát.

### Bước 4: cấu hình và xác định mức tuân thủ

Các kiểm soát có thể gồm:

- Mã hóa dữ liệu lưu trữ trên thiết bị khi nền tảng hỗ trợ.
- Khóa màn hình, PIN/mật khẩu, chính sách xác thực cục bộ.
- Phiên bản hệ điều hành, bản vá tối thiểu, trạng thái root/jailbreak theo khả năng phát hiện.
- Trạng thái antivirus/EDR, firewall, bảo vệ endpoint phù hợp.
- Chứng chỉ doanh nghiệp, VPN hoặc cấu hình ứng dụng cần thiết.
- Giới hạn truyền dữ liệu hoặc quản lý ứng dụng doanh nghiệp đối với BYOD khi hỗ trợ.

Không nên dùng một cờ compliance duy nhất để mô tả toàn bộ rủi ro. Cần biết **policy nào**, **khi nào được đánh giá** và **thiếu tín hiệu nào**.

### Bước 5: liên kết với chính sách truy cập

IdP hoặc tầng kiểm soát truy cập nhận tín hiệu có căn cứ về thiết bị để ra quyết định cho từng ứng dụng. Ví dụ:

- Ứng dụng chấm công: cho đăng nhập trên thiết bị cá nhân với MFA theo chính sách.
- Báo cáo tài chính: chỉ cho tải xuống trên thiết bị đã được quản lý và compliant.
- Bảng điều khiển sản xuất: yêu cầu thêm điều kiện về mạng, vai trò và phiên đặc quyền.

**Enrollment là đầu vào của chính sách, không phải quyết định ALLOW cuối cùng.** Ứng dụng vẫn phải kiểm tra user role, entitlement, quyền trên dữ liệu và các điều kiện bảo mật tương ứng.

### Bước 6: đối soát và ghi bằng chứng

Sau thao tác, cần đọc lại trạng thái ở các hệ thống liên quan: MDM có thấy thiết bị chưa, IdP có liên kết danh tính đúng không, compliance có hiệu lực không và truy cập thử có tuân chính sách không.

Lệnh enrollment trả về thành công về mặt API **không bảo đảm** tất cả policy hoặc certificate đã được áp dụng đúng trên thiết bị.

## 5. Các trạng thái thiết bị trong IAM

Một mô hình trạng thái minh họa:

| Trạng thái | Ý nghĩa quản trị | Hành động mong đợi |
|---|---|---|
| DISCOVERED | Thiết bị được phát hiện nhưng chưa đủ thông tin | Đối chiếu nguồn, owner và loại thiết bị |
| PENDING_VERIFICATION | Đang xác minh người đăng ký/tính hợp lệ | Chưa gán mức tin cậy cao |
| ENROLLED | Có bản ghi và quan hệ quản lý/tin cậy hợp lệ | Bắt đầu đánh giá policy và lấy telemetry |
| NONCOMPLIANT | Không đạt một hoặc nhiều điều kiện | Thực hiện hạn chế truy cập và hướng dẫn khắc phục theo chính sách |
| UNKNOWN / STALE | Tín hiệu thiếu hoặc quá cũ | Áp dụng hành vi mặc định an toàn phù hợp mức rủi ro |
| SUSPENDED | Tạm dừng tin cậy vì sự cố/nghi ngờ | Hạn chế hoặc chặn, điều tra trước khi khôi phục |
| RETIRED | Thiết bị đã kết thúc vòng đời | Thu hồi quan hệ tin cậy/credential, đối soát và lưu hồ sơ |

Mô hình trên chỉ để học tập, không phải enum chuẩn của mọi IdP hoặc MDM. Thực tế **enrollment state** và **compliance state** thường là hai chiều độc lập: thiết bị có thể ENROLLED nhưng NONCOMPLIANT.

### 5.1. Trạng thái tuân thủ có thể lỗi thời

Giả sử MDM ghi nhận laptop compliant lúc 9:00. Đến 11:00 laptop mất kết nối và bị vô hiệu hóa phần mềm bảo vệ. Nếu quyết định truy cập lúc 14:00 vẫn tin trạng thái 9:00 mà không xem độ mới dữ liệu, mức bảo vệ thực tế có thể thấp hơn kỳ vọng.

Thiết kế cần quy định:

- Tuổi tối đa của tín hiệu theo mức độ rủi ro.
- Cách xử lý khi thiết bị offline hoặc nguồn posture không phản hồi.
- Cơ chế yêu cầu đánh giá lại, làm mới token/session hoặc bước khắc phục.
- Khả năng ghi nhận lý do quyết định để hỗ trợ điều tra.

Không có chính sách “mọi ứng dụng đều bắt buộc chặn khi offline” phù hợp với mọi doanh nghiệp; chính sách tùy dữ liệu, rủi ro và tính liên tục hoạt động.

## 6. Device enrollment trong IdP, SSO, SCIM, RBAC và ABAC

### 6.1. IdP và SSO: người dùng đăng nhập trên thiết bị nào?

IdP có thể dựa vào danh tính thiết bị và tín hiệu quản lý để áp dụng điều kiện truy cập trong hoặc sau luồng đăng nhập SSO. Một yêu cầu có thể gồm:

1. **Who:** danh tính user đã xác minh, vai trò, nhóm và trạng thái nhân sự.
2. **What:** ứng dụng và tài nguyên cần truy cập.
3. **Which device:** thiết bị đã đăng ký chưa, có ràng buộc tin cậy không, có đáp ứng compliance không.
4. **Context:** mức nhạy cảm, rủi ro phiên, thời gian, mạng hoặc yêu cầu MFA.
5. **Decision:** cho phép, từ chối hoặc yêu cầu bổ sung kiểm soát.

SSO giúp xác thực thống nhất nhưng không tự động quản lý thiết bị. Ngược lại, thiết bị compliant không miễn yêu cầu xác thực và phân quyền người dùng.

### 6.2. SCIM có phải chuẩn quản lý thiết bị?

**SCIM** chủ yếu được dùng để quản lý các tài nguyên danh tính như User và Group giữa hệ thống cấp phát và ứng dụng hỗ trợ. Không nên mặc định SCIM là cơ chế dùng để **enroll thiết bị**, đánh giá compliance hay thu hồi khóa thiết bị. Các thao tác này thường dùng MDM/UEM, API thiết bị, chứng chỉ, IdP device registration hoặc cơ chế quản lý đặc thù.

Tình huống cụ thể: khi nhân viên nghỉ việc, SCIM có thể vô hiệu hóa tài khoản người dùng trong một SaaS; **thiết bị được cấp cho nhân viên** vẫn cần được xử lý trong workflow tài sản/MDM riêng.

### 6.3. RBAC: vai trò nghiệp vụ vẫn quan trọng

RBAC có thể cho nhân viên role “finance-reader”. Enrollment không thay đổi sự thật rằng chỉ người được cấp role mới được xem báo cáo. Một người không có role không nên được truy cập báo cáo tài chính chỉ vì dùng laptop công ty đã compliant.

### 6.4. ABAC: điều kiện truy cập theo thuộc tính thiết bị

ABAC có thể kết hợp thuộc tính user, device, resource và môi trường.

| Loại thuộc tính | Ví dụ | Yêu cầu về nguồn |
|---|---|---|
| User | employeeStatus=active, department=finance | Hệ thống HR/IdP có thẩm quyền |
| Device | managed=true, compliance=compliant, lastCheckedAt | MDM/UEM hoặc nguồn posture được tích hợp |
| Resource | classification=confidential, tenant=corp | Chủ dữ liệu/hệ thống tài nguyên |
| Action | view, download, edit, approve | API/ứng dụng xác định |
| Environment | sessionRisk, networkZone, time | Nguồn tín hiệu được kiểm tra |

Pseudocode minh họa:

~~~text
function canDownloadFinancialReport(request):
    user = verifyUserIdentity(request)
    device = resolveVerifiedDeviceContext(request)

    if user.status != ACTIVE:
        return DENY
    if not hasRole(user, "finance-reader"):
        return DENY
    if not canAccessReport(user, request.reportId):
        return DENY
    if device is UNKNOWN:
        return DENY
    if not device.managed or not device.compliant:
        return DENY
    if device.postureEvidenceIsStale:
        return REQUIRE_REEVALUATION

    return ALLOW
~~~

Đây là **pseudocode**, không phải một chính sách chung cho mọi hệ thống. Việc xác minh device context phải dựa vào IdP hoặc tín hiệu có bảo đảm, không tin dữ liệu như header “X-Device-Compliant: true” do client tự gửi. Hệ thống cũng cần đánh giá riêng các rủi ro về session/token, quyền tải xuống và biện pháp kiểm soát tại API.

## 7. Các mô hình enrollment theo loại thiết bị

### 7.1. Laptop thuộc sở hữu công ty

Tổ chức thường có quyền áp dụng quản trị chặt chẽ hơn: tự động enrollment qua nguồn cấp phát được phê duyệt, cài cấu hình, mã hóa, agent bảo vệ, chính sách cập nhật và khả năng khóa/xóa theo quy định.

**Tình huống cần phòng tránh:** cùng một asset được gán cho hai nhân viên vì hồ sơ bàn giao chưa cập nhật. Khi chuyển máy, cần cập nhật quan hệ chủ sở hữu, phiên và credential liên quan.

### 7.2. Thiết bị cá nhân (BYOD)

BYOD cần cân bằng quản lý an toàn với quyền riêng tư. Doanh nghiệp có thể sử dụng:

- App protection hoặc quản lý dữ liệu ứng dụng trong vùng doanh nghiệp.
- Work profile/container hoặc quản lý theo mô hình cho phép của nền tảng.
- Chính sách ngăn tải/xuất dữ liệu nhạy cảm trên thiết bị chưa đạt yêu cầu.
- **Selective wipe:** xóa tài liệu, token và cấu hình công ty trong phạm vi quản lý, nếu nền tảng hỗ trợ.

Không mặc định rằng doanh nghiệp được xóa toàn bộ dữ liệu cá nhân. Trước enrollment cần mô tả rõ **dữ liệu gì được thu thập, quyền quản trị gì được cấp, thao tác nào có thể diễn ra khi mất thiết bị/rời công ty** và chính sách theo pháp luật/quy định áp dụng.

### 7.3. Thiết bị dùng chung và kiosk

Một máy ở quầy giao dịch có thể do nhiều nhân viên đăng nhập trong các ca khác nhau. Device identity gắn với máy; user identity gắn với phiên làm việc từng người.

Yêu cầu quan trọng:

- Cô lập session giữa các ca, thoát phiên và xóa credential/cache theo thiết kế.
- Giới hạn account quản trị và ứng dụng có thể chạy trên máy dùng chung.
- Không dùng một tài khoản cá nhân chung để “tiết kiệm” quản trị.
- Ghi audit theo cả user và device ID khi phù hợp.

### 7.4. Thiết bị IoT, đầu cuối tự động và hệ thống không có người dùng

Một cảm biến hoặc thiết bị chuyên dụng có thể không hỗ trợ màn hình đăng nhập, MDM truyền thống hay MFA tương tác. Enrollment có thể dựa vào chứng chỉ, cơ chế provisioning của nhà sản xuất hoặc PKI nội bộ với owner kỹ thuật.

Các thiết bị này cần:

- Danh tính riêng và quyền chỉ dùng dịch vụ/tài nguyên cần thiết.
- Cơ chế cấp/xoay vòng khóa hoặc chứng chỉ theo khả năng phần cứng.
- Phân đoạn mạng và giới hạn kết nối nếu phù hợp.
- Danh mục owner, firmware, thời điểm hỗ trợ/kết thúc sử dụng.
- Kế hoạch thu hồi khóa khi thay thiết bị hoặc ngừng vận hành.

**Device identity của IoT** không đồng nghĩa tài khoản dịch vụ của backend nhận dữ liệu. Hai principal có thể thuộc hai miền bảo mật và cần được kiểm soát riêng.

## 8. Device Joiner–Mover–Leaver và mối liên hệ với người lao động

JML của nhân viên và JML của thiết bị liên quan nhưng không trùng nhau.

| Giai đoạn | Sự kiện đối với nhân viên | Sự kiện đối với thiết bị | Việc IAM/enrollment cần làm |
|---|---|---|---|
| Joiner | Nhân viên mới nhận việc | Laptop mới được cấp | Xác minh, enroll, gắn owner, kiểm tra compliance, chỉ mở quyền đúng ngày hiệu lực |
| Mover | Chuyển vai trò/phòng ban | Đổi người sử dụng hoặc thay mức độ nhạy cảm | Rà soát quyền user, thay owner, profile/ứng dụng, khóa hoặc policy nếu cần |
| Leaver | Nhân viên nghỉ việc | Laptop được thu hồi/cấp lại | Chặn tài khoản user, kết thúc session, gỡ dữ liệu/credential doanh nghiệp, đối soát tài sản |
| Device retirement | Nhân viên vẫn làm việc | Thiết bị hỏng/mất/ngừng dùng | Thu hồi device trust/chứng chỉ, xử lý phiên, ghi nhận thiết bị thay thế |

### 8.1. Joiner: ngày đầu nhân viên nhận laptop

Ví dụ Mai vào bộ phận kế toán:

1. HR xác thực hồ sơ Mai và ngày hiệu lực.
2. Bộ phận tài sản ghi nhận laptop công ty sẽ bàn giao cho Mai.
3. Nhóm endpoint hoặc cơ chế tự động thực hiện enrollment vào MDM/UEM.
4. Thiết bị nhận cấu hình bảo mật và được đánh giá tuân thủ.
5. IdP liên kết tín hiệu device và chính sách truy cập; quyền nghiệp vụ của Mai vẫn dựa trên RBAC/ABAC.
6. Tổ chức kiểm thử Mai có thể dùng công cụ cần thiết, nhưng không thể truy cập dữ liệu/ứng dụng ngoài quyền.
7. Cả hai vòng đời user và device đều được ghi dấu vết.

Đăng ký laptop trước ngày làm việc có thể hợp lý về vận hành; **quyền sử dụng tài nguyên nhạy cảm phải tuân theo ngày hiệu lực và chính sách**.

### 8.2. Mover: chuyển thiết bị hoặc thay mức độ rủi ro

Mai chuyển từ kế toán sang bộ phận phân tích. Laptop vẫn thuộc công ty, nhưng các ứng dụng, dữ liệu và phạm vi quyền có thể thay đổi.

Quy trình Mover cần so sánh trạng thái cũ/mới:

- Thu hồi quyền trên ứng dụng kế toán khi không còn nhiệm vụ hợp lệ.
- Gỡ ứng dụng/credential chuyên biệt của bộ phận cũ nếu cần.
- Cấp quyền và chính sách phù hợp vai trò mới.
- Xem xét lại điều kiện truy cập theo nhạy cảm của dữ liệu mới.
- Nếu laptop được bàn giao cho người khác, thực hiện quy trình làm sạch dữ liệu, hủy phiên/credential và cập nhật owner theo chính sách.
- Đọc lại trạng thái để phát hiện quyền tồn dư của user hoặc khóa thiết bị cũ.

**Không nên chỉ thêm ứng dụng mới**, để mọi quyền/phần mềm của vai trò cũ tồn tại vô thời hạn.

### 8.3. Leaver: người nghỉ việc nhưng thiết bị chưa thu hồi

Một sai lầm là cho rằng khóa tài khoản IdP của Mai nghĩa là laptop đã an toàn. Nếu thiết bị vẫn chứa dữ liệu offline, secret, session cache hoặc tài khoản local, còn nhiều đường truy cập cần xử lý.

Các bước phù hợp với quyền quản lý và loại thiết bị:

1. Vô hiệu hóa user identity và quyền ứng dụng theo chính sách Leaver.
2. Thu hồi hoặc chấm dứt phiên, token, chứng chỉ/khóa truy cập và kênh kết nối liên quan khi có thể.
3. Kích hoạt quy trình thu hồi thiết bị vật lý hoặc xác nhận tình trạng mất/hỏng.
4. Với thiết bị công ty: khóa hoặc xóa dữ liệu theo quyết định có thẩm quyền, kiểm tra khả năng thiết bị đã nhận lệnh; chuẩn bị cấp lại.
5. Với BYOD: thu hồi quyền ứng dụng và chỉ xóa vùng dữ liệu/cấu hình doanh nghiệp trong phạm vi đã được công bố/chấp thuận.
6. Gỡ liên kết user–device, thu hồi device trust khi thiết bị không còn đủ điều kiện.
7. Đối soát ở IdP, MDM/UEM, ứng dụng quan trọng và hệ thống tài sản; ghi nhiệm vụ đang chờ cho thiết bị offline.

**Lệnh remote wipe được gửi đi không có nghĩa dữ liệu trên thiết bị đã được xóa.** Thiết bị offline có thể chưa nhận lệnh. Trạng thái kiểm toán phải phân biệt “lệnh đã gửi”, “thiết bị đã xác nhận” và “cần điều tra”.

### 8.4. Mất hoặc bị đánh cắp thiết bị: Leaver khẩn cấp của device trust

Khi laptop bị mất:

- Đánh dấu thiết bị bị mất, hạn chế các truy cập sử dụng trust của thiết bị.
- Thu hồi/khóa device certificate, token phiên và quyền liên quan theo khả năng nền tảng.
- Đánh giá dữ liệu tại chỗ: mã hóa, dữ liệu đã tải, loại tài liệu, độ mới backup.
- Yêu cầu xử lý tài khoản người dùng nếu có dấu hiệu credential bị lộ.
- Gửi lệnh khóa/wipe theo chính sách nếu quản lý cho phép, ghi nhận xác nhận/không xác nhận.
- Ghi sự cố, cập nhật asset inventory và đưa thiết bị thay thế qua Joiner mới.

Không tự suy ra rằng chỉ cần thu hồi chứng chỉ thiết bị là mọi token đã phát hành hết hiệu lực tức thời; phụ thuộc thời hạn và cách kiểm tra token của mỗi hệ thống.

## 9. Tình huống thực tế: laptop hợp lệ nhưng người dùng không có quyền

Giả sử tổ chức dùng ứng dụng FinanceDesk để phê duyệt thanh toán.

**Chính sách:**
- Nhân viên phải đăng nhập qua IdP với MFA phù hợp.
- Chức năng phê duyệt chỉ cho role finance-approver theo quy trình nghiệp vụ.
- Thiết bị phải managed và compliant để xử lý phê duyệt.
- Nhân viên chỉ được phê duyệt giao dịch thuộc đơn vị và hạn mức được ủy quyền.

Bốn yêu cầu:

| Yêu cầu | User | Device | Kết quả minh họa |
|---|---|---|---|
| A | Đúng role và phạm vi | Managed, compliant | Có thể ALLOW nếu các điều kiện khác đều thỏa |
| B | Không có role phê duyệt | Managed, compliant | DENY vì thiếu quyền nghiệp vụ |
| C | Có role | Chưa đăng ký | DENY hoặc hạn chế theo chính sách tài nguyên |
| D | Có role | Enrolled nhưng noncompliant | DENY/REMEDIATE theo chính sách |

Việc tách điều kiện cho thấy **device enrollment không thay RBAC**, và role của user **không thay điều kiện kiểm tra thiết bị**.

### 9.1. Luồng kiểm tra theo request

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant D as Thiết bị
    participant I as IdP / Conditional Access
    participant M as MDM / Posture source
    participant A as FinanceDesk
    U->>I: Đăng nhập và yêu cầu ứng dụng
    D-->>I: Bằng chứng/tín hiệu danh tính thiết bị
    I->>M: Kiểm tra trạng thái quản lý/tuân thủ theo tích hợp
    M-->>I: Trạng thái và thời điểm đánh giá
    I->>I: Xét user, MFA, device, ngữ cảnh
    I-->>A: Kết quả xác thực/ủy quyền theo luồng được hỗ trợ
    A->>A: Kiểm tra quyền phê duyệt, đơn vị, hạn mức
    A-->>U: Cho phép hoặc từ chối thao tác
~~~

Đây là luồng khái niệm. Trong hệ thống thật, tín hiệu device và quyết định truy cập có thể được đóng gói trong token, phiên, thông tin đối soát hoặc cơ chế khác; API không nên tin dữ liệu do browser tự khai báo mà không có bằng chứng tin cậy.

## 10. Rủi ro và biện pháp kiểm soát thường gặp

| Rủi ro | Ví dụ | Biện pháp giảm thiểu |
|---|---|---|
| Enrollment giả mạo | Người tấn công tự khai báo serial của laptop hợp lệ | Xác minh người có quyền enroll, nguồn tài sản và chứng cứ gắn khóa/attestation khi hỗ trợ |
| Enrollment trùng | Một thiết bị tạo nhiều bản ghi, không rõ bản nào hiện hành | Dùng ID ổn định và quy tắc đối soát, xử lý đổi khóa/tái cài đặt |
| Mất hoặc sao chép credential | Khóa thiết bị nằm trong file có thể copy | Bảo vệ key phần cứng nếu có, credential có hạn, phát hiện bất thường, thu hồi kịp thời |
| Device posture lỗi thời | Laptop từng compliant nhưng nay không còn | Giới hạn độ mới tín hiệu, giám sát và đánh giá lại theo rủi ro |
| Token/phiên tồn dư | IdP đã xóa device nhưng ứng dụng còn session | Thiết kế timeout, thu hồi session/token khi hỗ trợ và đối soát |
| Dữ liệu BYOD không được kiểm soát | Tài liệu công ty lưu ngoài vùng quản lý | Giới hạn kênh xuất dữ liệu, app protection và chính sách selective wipe |
| Thiết bị cũ cấp lại | Người mới nhận máy có cache/token của người trước | Quy trình bàn giao, làm sạch, tạo lại profile và xác minh các khóa cũ bị thu hồi |
| Tài khoản dịch vụ chạy trên device | Agent còn khóa API sau khi device retired | Quản lý service account và secret theo vòng đời riêng, thu hồi khi kết thúc |
| Giao diện truy cập bỏ qua policy | App chỉ kiểm tra icon “managed” ở UI | Thực thi authorization tại IdP/API/resource, không tin trạng thái hiển thị |
| Enrollment không ai chịu trách nhiệm | Thiết bị không có owner hoặc offline lâu | Inventory, owner, ticket, SLA và kiểm tra ngoại lệ định kỳ |

### 10.1. “Thiết bị đáng tin cậy” không phải trạng thái vĩnh viễn

Khi mua mới, thiết bị có thể đạt yêu cầu; sau một năm, hệ điều hành có thể hết hỗ trợ hoặc khóa bảo mật bị lộ. Vì vậy trust phải có **căn cứ**, **thời gian**, **người chịu trách nhiệm** và **cơ chế thu hồi**.

Một chính sách phù hợp nên phân biệt:

- Thiết bị được tổ chức **biết đến**.
- Thiết bị hiện **được quản lý**.
- Thiết bị hiện **đạt điều kiện tuân thủ**.
- Thiết bị **được phép truy cập ứng dụng/tài nguyên cụ thể**.

Không coi bốn điều kiện đó là một.

### 10.2. Tối thiểu hóa dữ liệu và quyền riêng tư

Quản lý thiết bị có thể thu thập loại hệ điều hành, phiên bản, định danh phần cứng, trạng thái ứng dụng hoặc một số tín hiệu vị trí tùy cấu hình. Tổ chức cần thông báo minh bạch và giới hạn dữ liệu thu thập theo mục đích bảo mật hợp pháp, đặc biệt với BYOD.

Nhật ký audit nên ghi nhận ID thiết bị, trạng thái/chính sách và kết quả quyết định, tránh ghi dữ liệu cá nhân không liên quan, bí mật xác thực hoặc toàn bộ nội dung người dùng lưu trên thiết bị.

## 11. Đối soát, kiểm toán và vận hành sự cố enrollment

### 11.1. Một bản ghi audit minh họa

~~~json
{
  "eventId": "device-enroll-2026-037",
  "eventType": "DEVICE_ENROLLMENT",
  "deviceId": "dev-8c24",
  "actorIdentityId": "employee-1042",
  "ownerTeam": "endpoint-security",
  "ownershipType": "CORPORATE",
  "enrollmentSource": "approved-corporate-provisioning",
  "requestedAt": "2026-11-23T08:15:00+07:00",
  "policyVersion": "endpoint-v3",
  "enrollmentResult": "SUCCESS",
  "complianceResult": "PENDING_EVALUATION",
  "verificationResult": "NOT_YET_CONFIRMED",
  "correlationId": "ticket-8134"
}
~~~

Đây là JSON giả lập để minh họa trường thông tin, **không phải schema chuẩn**. Khi compliance vẫn đang được đánh giá, không nên ghi thiết bị đã hoàn tất mọi điều kiện truy cập.

### 11.2. Các bằng chứng nên giữ

- Yêu cầu đăng ký, nguồn tài sản và người được phép thực hiện.
- Thời điểm enrollment, device ID, loại thiết bị và môi trường.
- Quan hệ giữa device identity, user hiện hành và owner vận hành.
- Phiên bản chính sách, trạng thái compliance và thời điểm nhận tín hiệu.
- Quyết định truy cập/khắc phục cùng lý do để giải thích các trường hợp bị từ chối.
- Lịch sử thay đổi/thu hồi certificate, token, trust binding.
- Kết quả readback khi thiết bị chuyển trạng thái, bị mất hoặc ngừng sử dụng.
- Ngoại lệ thủ công, người phê duyệt, phạm vi và hạn hết hiệu lực.

### 11.3. Những chỉ số có ý nghĩa

| Chỉ số | Cách hiểu |
|---|---|
| Thời gian từ khi cấp phát tới enrollment sẵn sàng | Khả năng hỗ trợ Joiner đúng ngày |
| Tỷ lệ thiết bị có owner và nguồn đăng ký hợp lệ | Chất lượng inventory và trách nhiệm |
| Tỷ lệ compliant theo chính sách và độ mới tín hiệu | Mức đáp ứng yêu cầu tại thời điểm đánh giá |
| Số thiết bị stale/unknown có quyền nhạy cảm | Điểm mù cần rà soát |
| Thời gian khóa/thu hồi sau báo mất hoặc Leaver | Tốc độ phản ứng rủi ro |
| Tỷ lệ deprovision đã xác minh | Số thiết bị thực sự hết trust/quyền trên tổng số cần thu hồi |
| Số ngoại lệ enrollment quá hạn | Rủi ro do quy trình thủ công |

Cần xác định rõ mẫu số, kỳ đo và hệ thống cung cấp bằng chứng. **Đã gửi lệnh khóa**, **đã nhận phản hồi API** và **đã xác minh không còn truy cập** là những trạng thái khác nhau.

## 12. Các sai lầm phổ biến

**“Người dùng MFA thành công thì thiết bị chắc chắn an toàn.”** MFA xác minh người dùng theo cơ chế đã cấu hình; tình trạng thiết bị cần bằng chứng và chính sách riêng.

**“Laptop có device ID trong IdP nên đã compliant.”** Device registration không tự chứng minh policy MDM, bản vá hay EDR đang đạt yêu cầu.

**“SCIM đã vô hiệu hóa nhân viên nên có thể bỏ qua laptop.”** SCIM user provisioning không tự thay thế thu hồi device trust, secret, phiên và dữ liệu offline.

**“Thiết bị công ty luôn được phép vào mọi ứng dụng.”** Quyền nghiệp vụ của user, độ nhạy cảm tài nguyên và điều kiện truy cập vẫn phải được xét.

**“Remote wipe đã gửi nghĩa là thiết bị đã xóa dữ liệu.”** Thiết bị có thể offline hoặc không thực thi được lệnh; cần trạng thái xác nhận và xử lý tồn đọng.

**“Đổi người dùng laptop chỉ cần đổi tên owner.”** Có thể cần thu hồi credential/phiên, làm sạch dữ liệu doanh nghiệp và cấp lại profile theo quy trình.

**“Không thấy thiết bị hoạt động lâu thì xóa ngay.”** Có thiết bị chỉ hoạt động theo quý, thiết bị dự phòng hoặc phục vụ xử lý khẩn cấp; cần xác nhận owner và mục đích trước khi retirement.

**“Certificate hợp lệ chứng minh user đang được phép xem báo cáo.”** Chứng chỉ gắn thiết bị chỉ đóng góp tín hiệu thiết bị; user authorization là kiểm soát độc lập.

## 13. Tình huống tự kiểm tra

### Tình huống A: thiết bị chưa được quản lý

An có role nhân sự và MFA hợp lệ nhưng đăng nhập ứng dụng lưu hồ sơ nhân sự từ máy công cộng. Ứng dụng yêu cầu managed + compliant device.

**Phân tích:** Có thể từ chối truy cập hoặc yêu cầu thiết bị đủ điều kiện theo chính sách. IAM không nên tự “enroll” máy công cộng chỉ vì An có tài khoản hợp lệ.

### Tình huống B: nhân viên nghỉ nhưng điện thoại BYOD còn ứng dụng

Bình nghỉ việc, điện thoại cá nhân vẫn chứa dữ liệu email doanh nghiệp trong ứng dụng được bảo vệ.

**Phân tích:** Thu hồi user session/token, tước quyền ứng dụng và xóa dữ liệu doanh nghiệp trong phạm vi quản lý theo chính sách. Không mặc định được xóa toàn bộ ảnh, tin nhắn và dữ liệu cá nhân của Bình.

### Tình huống C: đổi laptop giữa hai nhân viên

Lan trả máy, Minh nhận lại cùng laptop. MDM hiện vẫn hiển thị Lan là người được cấp; browser của Lan có thể còn phiên cũ.

**Phân tích:** Mover/retirement–reenrollment cần cập nhật owner, thu hồi session/credential, làm sạch cấu hình người cũ và readback ở IdP/MDM, không chỉ thay tên trên biên bản bàn giao.

### Tình huống D: máy compliant nhưng thiếu role

Một laptop công ty đạt mọi điều kiện compliance, nhưng người dùng không được cấp role finance-approver.

**Phân tích:** API vẫn phải từ chối yêu cầu phê duyệt. Device posture không tạo quyền nghiệp vụ.

### Tình huống E: thiết bị mất kết nối MDM

Một laptop không gửi tín hiệu posture trong 30 ngày nhưng vẫn có certificate chưa hết hạn.

**Phân tích:** Chính sách cần xử lý trạng thái stale/unknown theo rủi ro. Certificate còn hiệu lực không chứng minh compliance hiện tại; có thể yêu cầu đánh giá lại trước khi truy cập tài nguyên nhạy cảm.

## 14. Checklist thiết kế Device enrollment

Khi triển khai hoặc kiểm tra một luồng đăng ký thiết bị, lần lượt trả lời:

1. **Nguồn đăng ký:** Ai có thẩm quyền đăng ký thiết bị và nguồn nào chứng minh được quyền đó?
2. **Đối tượng thiết bị:** Phân loại thiết bị công ty, BYOD, kiosk, IoT; loại nào được phép enroll?
3. **Bằng chứng danh tính:** Device identity được liên kết với khóa/chứng chỉ hoặc nguồn tin cậy nào; chống đăng ký giả mạo ra sao?
4. **Owner:** Ai chịu trách nhiệm tài sản, người đang sử dụng, nhóm vận hành và người phê duyệt?
5. **Tích hợp:** MDM/UEM, IdP, asset inventory, EDR và ứng dụng đích trao đổi trạng thái qua cơ chế nào?
6. **Chính sách:** Cần managed, compliant, MFA, RBAC/ABAC hay điều kiện nào cho từng tài nguyên?
7. **Độ mới tín hiệu:** Khi posture bị thiếu hoặc đã cũ, hệ thống xử lý ra sao?
8. **JML:** Khi người dùng chuyển vai trò, đổi thiết bị, nghỉ việc hoặc báo mất, ai cập nhật quyền và trust?
9. **Credential và phiên:** Khi deprovision, khóa/chứng chỉ, token, cache và account cục bộ được xử lý thế nào?
10. **Quyền riêng tư:** Với BYOD, tổ chức có quyền đọc/xóa dữ liệu gì và đã thông báo rõ chưa?
11. **Audit và readback:** Có bằng chứng thiết bị đã được đăng ký, bị hạn chế hoặc đã thu hồi thực tế không?
12. **Ngoại lệ:** Ai phê duyệt thiết bị chưa đạt yêu cầu, quyền ngoại lệ kéo dài bao lâu và ai xử lý quá hạn?

**Ghi nhớ:** Đăng ký thiết bị là bước đưa **device identity và trạng thái quản lý** vào chuỗi kiểm soát IAM. Quyền truy cập thực tế vẫn phụ thuộc người dùng/ứng dụng, tài nguyên, chính sách RBAC/ABAC, bằng chứng thiết bị và ngữ cảnh tại thời điểm yêu cầu. Khi kết hợp enrollment với vòng đời **Joiner–Mover–Leaver**, đối soát trạng thái IdP–MDM–ứng dụng và quy trình thu hồi có xác nhận, tổ chức có thể giảm thiết bị mồ côi, credential còn hiệu lực và quyền truy cập tồn dư.
