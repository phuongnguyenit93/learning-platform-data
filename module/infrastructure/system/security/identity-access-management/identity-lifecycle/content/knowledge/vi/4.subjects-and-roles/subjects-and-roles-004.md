# Contractor trong IAM: quản lý danh tính nhà thầu xuyên suốt vòng đời truy cập

Trong **Identity and Access Management (IAM)**, *Contractor* là một **chủ thể con người** làm việc cho tổ chức theo hợp đồng, thỏa thuận dịch vụ hoặc nhiệm vụ có giới hạn, nhưng thường không có quan hệ lao động giống nhân viên chính thức. Contractor có thể là chuyên gia tư vấn, lập trình viên thuê ngoài, kỹ thuật viên bảo trì, kiểm toán viên độc lập hoặc nhân sự của một nhà cung cấp dịch vụ. Tùy chính sách và pháp luật áp dụng, ranh giới giữa contractor, temporary worker, partner và employee có thể khác nhau; điều quan trọng trong IAM là **căn cứ quan hệ công việc, người chịu trách nhiệm, quyền cần thiết và thời hạn hợp lệ**.

Bài học thuộc chương **Chủ thể và vai trò**, trong mô-đun quản lý vòng đời danh tính **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung liên hệ trực tiếp với quy trình **Joiner–Mover–Leaver (JML)**: xác minh nhà thầu, thiết lập danh tính, tạo tài khoản, cấp quyền theo nhiệm vụ, rà soát, thay đổi hoặc gia hạn hợp đồng, rồi thu hồi quyền truy cập kịp thời. Các cơ chế **IdP, SSO, SCIM, RBAC/ABAC, kiểm toán** và quản trị tài khoản dịch vụ cùng tham gia kiểm soát rủi ro **quyền truy cập tồn dư**.

**Ý tưởng trung tâm:** Contractor có thể cần quyền truy cập sâu vào hệ thống để thực hiện công việc hợp lệ. Tuy nhiên, quyền đó phải **gắn với cá nhân, nhiệm vụ, người bảo trợ, phạm vi dữ liệu và thời hạn được phê duyệt**; không nên mặc định kéo dài chỉ vì tài khoản vẫn tồn tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt contractor với employee, partner và service account dưới góc nhìn IAM.
2. Xác định các dữ liệu cần có để quản lý danh tính nhà thầu: người thật, đơn vị cung cấp, hợp đồng, người bảo trợ, dự án, trạng thái và mốc hiệu lực.
3. Thiết kế hành trình **onboarding → cấp quyền → thay đổi/gia hạn → offboarding** gắn với JML và nguồn dữ liệu có thẩm quyền.
4. Chọn cơ chế phù hợp giữa **federated identity/SSO**, tài khoản được tổ chức quản lý, provisioning qua SCIM/API và phân quyền RBAC/ABAC.
5. Nhận diện rủi ro từ quyền cấp thủ công, tài khoản mồ côi, hợp đồng hết hạn, token/phiên tồn tại và đặc quyền không còn phục vụ dự án.
6. Đề xuất quy trình phê duyệt, kiểm toán và các chỉ số để chứng minh rằng quyền nhà thầu được cấp và thu hồi thực sự.

## 2. Contractor là chủ thể nào?

Trong một yêu cầu truy cập, **chủ thể (subject)** là thực thể đang thực hiện hành động. Với nhà thầu, subject thường là **một cá nhân đã được xác định**, sử dụng danh tính và phương thức xác thực được tổ chức chấp nhận. Danh tính này có thể được thể hiện bởi tài khoản nội bộ hoặc tài khoản ở IdP của tổ chức đối tác.

| Loại chủ thể | Đặc điểm chính | Ví dụ | Cách quản lý đáng chú ý |
|---|---|---|---|
| **Employee** | Làm việc theo quan hệ nhân sự của tổ chức | Nhân viên vận hành chính thức | Thường lấy biến cố vòng đời từ HR |
| **Contractor** | Cá nhân làm việc theo nhiệm vụ/hợp đồng có thời hạn | Chuyên gia bên ngoài triển khai hệ thống | Cần sponsor, đơn vị/hợp đồng, phạm vi và ngày kết thúc |
| **Partner user** | Người dùng thuộc tổ chức hợp tác có quyền vào tài nguyên dùng chung | Nhân viên đại lý vào cổng đối tác | Cần ranh giới tổ chức, dữ liệu đối tác và chính sách chia sẻ |
| **Service account / workload identity** | Danh tính không phải con người, được ứng dụng hoặc tác vụ sử dụng | Tiến trình đồng bộ hóa đơn | Cần chủ sở hữu kỹ thuật, bí mật/token, quyền máy đến máy và vòng đời riêng |

Các loại này có thể **giao nhau trong thực tế**. Ví dụ, một chuyên gia của đối tác có thể là contractor đối với dự án nội bộ và đồng thời đăng nhập qua IdP của đối tác. IAM không nên suy đoán mức quyền chỉ từ một nhãn `contractor`.

### Danh tính khác với tài khoản, vai trò và hợp đồng

Bốn khái niệm liên quan nhưng không đồng nhất:

- **Danh tính (identity):** Bản ghi đại diện cho một cá nhân được xác minh và liên kết đến quan hệ công việc.
- **Tài khoản (account):** Bản ghi đăng nhập hoặc quyền sử dụng tại IdP, ứng dụng, kho mã nguồn hay nền tảng đám mây.
- **Vai trò/quyền (role/entitlement):** Những hành động và tài nguyên mà cá nhân được phép sử dụng.
- **Hợp đồng/nhiệm vụ (engagement):** Cơ sở nghiệp vụ xác định lý do, phạm vi và thời hạn hợp lệ của truy cập.

Một nhà thầu có thể có **một hồ sơ danh tính** nhưng nhiều tài khoản trong các ứng dụng. Một hợp đồng có thể có nhiều cá nhân, song **không nên dùng một tài khoản chung cho tất cả** chỉ vì các cá nhân thuộc cùng nhà cung cấp.

## 3. Điều kiện đầu vào để quản lý Contractor

Khác với nhân viên mà nguồn biến cố thường đến từ hệ thống HR, hồ sơ nhà thầu có thể do **Vendor Management System (VMS)**, quản lý hợp đồng, bộ phận mua sắm, đội dự án hoặc hệ thống quản lý nhân sự bên ngoài cung cấp. Tổ chức cần quy định **nguồn nào có thẩm quyền** cho từng thuộc tính; không mặc định mọi thông tin do nhà cung cấp gửi đều được tin cậy.

| Thuộc tính | Ví dụ | Mục đích trong IAM |
|---|---|---|
| Định danh nhà thầu | ID nội bộ ổn định và ánh xạ tới định danh bên ngoài | Tránh tạo bản ghi trùng, hỗ trợ đối soát |
| Người được xác minh | Họ tên và bằng chứng/điều kiện xác minh phù hợp chính sách | Liên kết quyền với đúng cá nhân |
| Tổ chức cung cấp | Công ty cung ứng hoặc cá nhân độc lập | Phân biệt ranh giới trách nhiệm và nguồn xác thực |
| **Sponsor** | Quản lý dự án nội bộ chịu trách nhiệm | Phê duyệt nhu cầu, xác nhận quyền và xử lý khi nhiệm vụ thay đổi |
| Engagement / dự án | Mã hợp đồng, dự án, mô tả công việc | Giải thích vì sao quyền tồn tại |
| Trạng thái | Pending, active, suspended, ended… | Xác định liệu danh tính có đủ điều kiện truy cập |
| Ngày bắt đầu và kết thúc | Mốc hiệu lực được phê duyệt | Kích hoạt/thu hồi tự động và lập lịch rà soát |
| Phạm vi/độ nhạy dữ liệu | Dự án A, môi trường kiểm thử, dữ liệu đã khử định danh | Tính chính sách truy cập |
| Người phê duyệt/owner dữ liệu | Chủ sở hữu ứng dụng hoặc dữ liệu | Quyết định các quyền ngoài gói tiêu chuẩn |
| Điều kiện bảo mật | MFA, thiết bị, đào tạo/chấp thuận chính sách nếu được yêu cầu | Kiểm tra khả năng đáp ứng điều kiện truy cập |

**Nguyên tắc dữ liệu:** Chỉ thu thập và giữ thông tin cần thiết cho mục đích danh tính và an toàn; áp dụng quy tắc bảo vệ, quyền truy cập và thời hạn lưu phù hợp. Không nhất thiết phải sao chép toàn bộ tài liệu hợp đồng hoặc giấy tờ định danh vào hệ thống IAM.

### Sponsor không phải chỉ là một ô metadata

Sponsor là **đầu mối chịu trách nhiệm nghiệp vụ** trong tổ chức. Vai trò này thường gồm:

- Xác nhận nhà thầu còn phục vụ nhiệm vụ nào và đến ngày nào.
- Phê duyệt hoặc đề xuất cấp quyền theo phạm vi có căn cứ.
- Xem xét quyền khi nhiệm vụ thay đổi, hợp đồng gia hạn hoặc cá nhân rời dự án.
- Xử lý trường hợp nhà cung cấp thông báo thay người hoặc chấm dứt hợp tác sớm.
- Hỗ trợ kiểm toán và chứng nhận lại quyền thuộc phạm vi bảo trợ.

Nếu sponsor nghỉ việc hoặc chuyển vị trí, IAM cần **chuyển giao ownership** và xử lý các danh tính nhà thầu bị thiếu người chịu trách nhiệm. Sponsor trống không nên trở thành lý do để kéo dài quyền vô thời hạn.

## 4. Mô hình định danh và xác thực cho Contractor

Không có một cách đăng nhập duy nhất phù hợp với mọi nhà thầu. Có thể chọn theo độ tin cậy của đối tác, độ nhạy tài nguyên, khả năng quản trị và yêu cầu hỗ trợ.

### 4.1. Tài khoản do tổ chức quản lý

Tổ chức tạo tài khoản contractor trong IdP hoặc hệ thống tài khoản riêng do mình quản lý.

**Ưu điểm:** Chủ động áp dụng MFA, chính sách truy cập có điều kiện, vô hiệu hóa tài khoản và thống kê truy cập theo chuẩn nội bộ.  
**Thách thức:** Cần quy trình xác minh, cấp phát, hỗ trợ và thu hồi tài khoản; nguy cơ giữ tài khoản sau khi hợp đồng kết thúc.

### 4.2. Danh tính liên kết qua IdP bên ngoài

Nhà thầu đăng nhập bằng tài khoản do tổ chức cung cấp dịch vụ quản lý, thông qua **federation/SSO** dựa trên cơ chế tin cậy được cấu hình phù hợp.

**Ưu điểm:** Giảm số lượng thông tin đăng nhập độc lập, có thể tận dụng bước xác thực và quản lý người dùng ở tổ chức nguồn.  
**Thách thức:** Tổ chức nhận truy cập vẫn phải quyết định **được làm gì, trên tài nguyên nào và đến khi nào**. Không nên mặc định rằng đối tác đã xác minh người dùng ở mức đáp ứng yêu cầu nội bộ; cần quy định mức bảo đảm danh tính, MFA, chứng nhận thuộc tính, xử lý khi bên ngoài thay đổi tài khoản và cơ chế chặn truy cập tại hệ thống nhận.

**Lưu ý:** Dù dùng tài khoản liên kết, ứng dụng vẫn có thể lưu **tài khoản/nhóm/role cục bộ**, phiên và token riêng. Đăng nhập SSO thành công không thay thế kiểm tra quyền và thu hồi.

### 4.3. Tài khoản trong ứng dụng đích

Một số hệ thống chỉ cho phép tạo tài khoản contractor cục bộ hoặc hỗ trợ một tập nhỏ API quản trị. Khi không thể tích hợp hoàn toàn với IdP/SCIM, cần quy trình thay thế có **chủ sở hữu, hạn xử lý, bước xác minh đã cấp/thu hồi và đối soát định kỳ**.

Tránh giải quyết vấn đề bằng cách dùng chung một tài khoản admin hoặc để mật khẩu trong tài liệu dự án.

### 4.4. Chọn mô hình theo rủi ro

| Tình huống | Phương án cân nhắc | Kiểm soát bắt buộc theo chính sách |
|---|---|---|
| Chuyên gia ngoài đọc tài liệu dự án | Tài khoản khách mời hoặc federation | MFA phù hợp, hạn hợp đồng, phân vùng dữ liệu |
| Nhà thầu dùng nhiều ứng dụng nội bộ | IdP/SSO + provisioning tự động nếu hỗ trợ | Gói quyền theo nhiệm vụ, đối soát trạng thái ứng dụng |
| Chuyên gia cần thao tác production | Quyền đặc quyền tạm thời/JIT + kiểm soát phiên phù hợp | Phê duyệt, giới hạn thao tác, ghi vết, tự thu hồi |
| Đối tác không có IdP đạt yêu cầu | Tài khoản nội bộ được quản lý | Xác minh, MFA, thiết bị/chính sách truy cập, thời hạn |
| Hệ thống legacy không có SCIM | Quy trình quản lý tài khoản riêng có theo dõi | Kiểm chứng cấp/thu hồi và rà soát quyền cục bộ |

## 5. Vòng đời Joiner–Mover–Leaver của nhà thầu

**JML áp dụng cho contractor, nhưng biến cố gốc phải phản ánh hợp đồng và nhiệm vụ, không chỉ hồ sơ nhân viên.** Một contractor có thể chuyển giữa hai dự án, thay sponsor, gia hạn hợp đồng hoặc bị thu hồi quyền trước ngày kết thúc dự kiến.

| Biến cố | Dữ liệu kích hoạt | IAM cần làm | Kết quả cần kiểm chứng |
|---|---|---|---|
| **Joiner** | Hợp đồng/nhiệm vụ được duyệt và đến mốc bắt đầu | Xác minh, tạo danh tính/tài khoản, áp điều kiện bảo mật, cấp quyền tối thiểu | Đúng cá nhân truy cập được đúng nhiệm vụ |
| **Mover – đổi dự án** | Chuyển team, dự án, scope hoặc sponsor | Tính lại quyền và kiểm tra SoD; thêm quyền mới và thu hồi quyền cũ | Không tồn tại quyền từ dự án trước nếu không còn căn cứ |
| **Extension – gia hạn** | Hợp đồng và thời hạn mới được phê duyệt | Xác minh lại sponsor, nhu cầu và mọi ngoại lệ; cập nhật expiry phù hợp | Quyền chỉ duy trì trong phạm vi còn hợp lệ |
| **Suspension** | Tạm ngừng nhiệm vụ hoặc có yêu cầu kiểm soát | Tạm dừng truy cập theo chính sách, bảo toàn thông tin cần thiết để xử lý | Không thể sử dụng quyền đang bị đình chỉ |
| **Leaver** | Hết hợp đồng, thôi dự án, bị thay người hoặc chấm dứt sớm | Thu hồi ứng dụng, nhóm, phiên, token, quyền chia sẻ và tài khoản liên quan | Đường truy cập đã hết điều kiện không còn hiệu lực |
| **Rejoiner** | Cá nhân trở lại với hợp đồng mới | Xác minh quan hệ mới, đánh giá lại quyền | Không tự khôi phục quyền lỗi thời |

### Sơ đồ vòng đời

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền<br/>VMS / hợp đồng / sponsor"] --> B{"Hồ sơ và nhiệm vụ hợp lệ?"}
    B -->|Không| X["Chờ bổ sung / từ chối cấp quyền"]
    B -->|Có| C["Xác minh và liên kết danh tính"]
    C --> D["Tạo/cập nhật tài khoản<br/>IdP / SCIM / API / quy trình thay thế"]
    D --> E["Áp RBAC/ABAC<br/>phạm vi + thời hạn + phê duyệt"]
    E --> F["Kiểm chứng quyền tại ứng dụng"]
    F --> G["Rà soát liên tục"]
    G --> H{"Biến cố mới?"}
    H -->|Đổi nhiệm vụ| I["Tính lại và thay thế quyền"]
    I --> F
    H -->|Gia hạn hợp lệ| J["Xác minh, cập nhật expiry<br/>và rà soát quyền"]
    J --> F
    H -->|Tạm ngừng| K["Đình chỉ quyền"]
    K --> G
    H -->|Kết thúc| L["Thu hồi tài khoản, quyền, phiên/token"]
    L --> M["Đối soát từng hệ thống<br/>và lưu bằng chứng"]
    H -->|Chưa có| G
~~~

**Điểm dễ bị bỏ sót:** “Hợp đồng chưa hết hạn” không bảo đảm mọi quyền cấp trước đó vẫn cần thiết. Nếu nhà thầu đã ngừng tham gia dự án A nhưng tiếp tục làm dự án B, quyền A phải được đánh giá và thu hồi tại mốc thay đổi phù hợp.

### 5.1. Joiner: xác minh rồi mới mở truy cập

Một trình tự onboarding có thể gồm:

1. Tiếp nhận yêu cầu từ sponsor hoặc nguồn hợp đồng có thẩm quyền; kiểm tra tình trạng hợp đồng, ngày bắt đầu và danh sách người được phép tham gia.
2. Xác minh danh tính cá nhân theo mức độ phù hợp với tài nguyên sẽ truy cập; xử lý trường hợp tên/email trùng hoặc nhà thầu từng tham gia trước đó.
3. Gán định danh nội bộ ổn định, liên kết với engagement và sponsor; ghi thời hạn và phạm vi được duyệt.
4. Tạo/cập nhật tài khoản tại IdP, nhóm/role nền tảng và ứng dụng đích khi đủ điều kiện.
5. Đảm bảo phương thức xác thực đáp ứng chính sách, chẳng hạn MFA, thiết bị/điều kiện phiên nếu cần.
6. Kiểm tra thực tế rằng cá nhân được truy cập đúng tài nguyên, đồng thời **không** sở hữu đặc quyền ngoài yêu cầu.
7. Thông báo đường đăng nhập chính thức, quy trình hỗ trợ và thời hạn quyền.

Không nên cấp quyền production trước ngày hiệu lực chỉ vì hồ sơ đã nhập xong. Nếu phải chuẩn bị tài khoản trước, có thể tạo ở trạng thái **chưa được phép sử dụng tài nguyên** cho tới khi đủ điều kiện.

### 5.2. Mover: thay đổi phạm vi mà không tích lũy quyền

Ví dụ, nhà thầu từ **dự án Migration** chuyển sang **dự án Analytics**. Cần tính lại quyền:

~~~text
Quyền đang có:
- đọc log của dịch vụ migration
- ghi cấu hình môi trường migration-staging

Quyền mong muốn cho Analytics:
- đọc báo cáo tổng hợp đã được cấp phép
- không có quyền sửa cấu hình migration

Hành động:
- thêm quyền đọc báo cáo Analytics
- thu hồi quyền log/cấu hình Migration không còn căn cứ
- đối soát lại nhóm, quyền trực tiếp, token và vai trò ở từng ứng dụng
~~~

Chỉ thêm nhóm mới mà giữ nguyên nhóm cũ tạo ra **quyền tích lũy (*permission creep*)**. Nguy cơ càng lớn khi contractor tham gia nhiều dự án liên tiếp.

### 5.3. Gia hạn: quyền không tự kéo dài

Một hợp đồng được gia hạn không đồng nghĩa mọi đặc quyền nên được gia hạn. Cần kiểm tra:

- Hợp đồng mới đã được phê duyệt, mốc thời gian có hiệu lực và danh tính có trùng đúng người không.
- Sponsor có còn chịu trách nhiệm và nhu cầu đã thay đổi hay chưa.
- Vai trò, tài nguyên, mức nhạy cảm và SoD có còn phù hợp.
- Quyền ngoại lệ/JIT, token, key hay truy cập production có cần phê duyệt lại không.

Mô hình an toàn hơn là **gia hạn có căn cứ rõ ràng**, thay vì tự tăng thời hạn khi không có biến cố đáng tin cậy. Nếu chưa xác nhận gia hạn trước mốc hết hiệu lực, IAM cần tuân thủ chính sách thu hồi/đình chỉ đã đặt ra.

### 5.4. Leaver: chấm dứt quyền thực tế

Khi hợp đồng kết thúc hoặc nhà thầu thôi dự án, IAM phải chủ động xử lý:

1. Đánh dấu engagement/danh tính không còn đủ điều kiện ở nguồn có thẩm quyền.
2. Vô hiệu hóa hoặc thu hồi nhóm/role ứng dụng phù hợp chính sách.
3. Hủy hoặc cho hết hiệu lực các **phiên, access token, refresh token, khóa/API credential** mà contractor được phép sở hữu hoặc có thể sử dụng, theo cơ chế từng hệ thống.
4. Xóa hoặc chuyển giao quyền truy cập tài liệu, kho mã, dự án cloud, ticket, vault, kết nối máy từ xa và các thư mục chia sẻ.
5. Chuyển giao quyền sở hữu công việc/dữ liệu cần thiết cho người có thẩm quyền; bảo toàn log và bản ghi phục vụ kiểm toán theo quy định.
6. Đối soát trạng thái sau thu hồi; xử lý các ứng dụng lỗi provisioning, tài khoản cục bộ hoặc quyền cấp trực tiếp.

**Phải phân biệt thu hồi quyền với xóa dữ liệu.** Việc giữ log, hồ sơ thanh toán hay nội dung công việc có thể tuân theo nghĩa vụ lưu giữ riêng. Không tự xóa chứng cứ hoặc tài sản dự án chỉ để hoàn tất offboarding.

## 6. Phân quyền nhà thầu bằng RBAC và ABAC

**RBAC (Role-Based Access Control)** gắn tập quyền với vai trò. **ABAC (Attribute-Based Access Control)** áp các điều kiện dựa vào thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh. Đối với contractor, kết hợp cả hai thường giúp tránh cấp một vai trò quá rộng.

### 6.1. Ví dụ gói vai trò

| Vai trò nghiệp vụ | Quyền tối thiểu tiêu biểu | Giới hạn cần xét |
|---|---|---|
| `contractor_project_reader` | Đọc tài liệu của dự án được giao | Không thấy tài liệu dự án khác |
| `contractor_dev` | Đọc/ghi mã nguồn trong repo và nhánh được phê duyệt | Không tự có quyền quản trị tổ chức Git |
| `contractor_support` | Xem ticket và log liên quan khách hàng/dịch vụ phụ trách | Giới hạn tenant, dữ liệu nhạy cảm và thời hạn |
| `contractor_auditor` | Đọc bằng chứng kiểm toán trong cửa sổ cho phép | Không sửa hoặc xóa bằng chứng |
| `contractor_ops_jit` | Thực hiện thao tác vận hành nhạy cảm khi được kích hoạt tạm thời | Phê duyệt, MFA/step-up, thời hạn và log riêng |

Tên vai trò chỉ là ví dụ thiết kế; mỗi tổ chức cần ánh xạ sang quyền thực tế ở ứng dụng và API. Không nên tạo một vai trò chung `contractor_full_access` cho mọi nhà thầu.

### 6.2. Thuộc tính hỗ trợ ABAC

Một quyết định truy cập có thể phụ thuộc vào:

- **Chủ thể:** `identity_type=contractor`, `engagement_status=active`, `sponsor_status=active`, `approved_projects`, `role`.
- **Tài nguyên:** `project_id`, `classification`, `environment`, `owner`.
- **Hành động:** `read`, `write`, `deploy`, `approve`.
- **Ngữ cảnh:** Thời gian hiệu lực, mức xác thực phiên, trạng thái thiết bị hoặc kết quả đánh giá rủi ro theo chính sách.

Ví dụ chính sách ở dạng **mã giả minh họa**, không phải policy triển khai hoàn chỉnh:

~~~python
def can_read_project_report(user, report, session, now):
    # Thiếu dữ liệu hoặc điều kiện cần thiết => từ chối
    if user.identity_type != "contractor":
        return False
    if user.engagement_status != "active":
        return False
    if user.sponsor_status != "active":
        return False
    if not (user.start_at <= now < user.end_at):
        return False
    if "project_report_reader" not in user.roles:
        return False
    if report.project_id not in user.approved_project_ids:
        return False
    if not session.is_valid or not session.mfa_satisfies_policy:
        return False
    if not report.is_approved_for_external_access:
        return False
    return True
~~~

Trong hệ thống thật cần bổ sung kiểm tra phân loại dữ liệu, xung đột quyền, khả năng thu hồi tức thời, lỗi đồng bộ và quyền kế thừa. **Thực thi phía máy chủ/API** là cần thiết: việc chỉ ẩn nút trên giao diện không ngăn được yêu cầu API trực tiếp.

### 6.3. Quyền đặc quyền và phân tách nhiệm vụ

Nhà thầu vận hành hệ thống đôi khi cần quyền có thể làm gián đoạn dịch vụ. Khi đó có thể sử dụng:

- **Privileged Access Management (PAM)** để kiểm soát phiên đặc quyền và chứng cứ sử dụng nếu nền tảng hỗ trợ.
- **Just-in-Time (JIT) access**: chỉ kích hoạt quyền trong cửa sổ được duyệt, tự động hết hạn.
- **Step-up authentication** cho thao tác rủi ro cao.
- **Separation of Duties (SoD)**: nhà thầu không được tự cấp, tự phê duyệt và tự xác nhận việc sử dụng cùng một quyền khi chính sách cấm.
- **Scope theo môi trường:** Quyền ở staging không tự chuyển thành quyền production.

Những biện pháp này cần dựa trên mức độ rủi ro và khả năng hệ thống, thay vì áp một quy trình giống nhau cho mọi nhu cầu.

## 7. IdP, SSO, SCIM và ứng dụng đích phối hợp như thế nào?

Có ba lớp thường bị nhầm:

1. **Xác thực (authentication):** Người đang đăng nhập có chứng minh được danh tính hay không, thường do IdP/SSO và MFA hỗ trợ.
2. **Cấp phát (provisioning):** Đã tạo/cập nhật tài khoản, nhóm hoặc thông tin nhà thầu ở ứng dụng đích hay chưa; SCIM/API có thể hỗ trợ tự động hóa.
3. **Ủy quyền (authorization):** Người đó có được thực hiện một hành động cụ thể trên tài nguyên cụ thể hay không, do chính sách và ứng dụng quyết định.

~~~mermaid
flowchart LR
    V["VMS / nguồn hợp đồng<br/>Sponsor + ngày hiệu lực"] --> I["IAM Lifecycle<br/>Quyền mong muốn"]
    I --> P["IdP / federation / SSO<br/>Xác thực và nhóm"]
    I --> S["SCIM / API / quy trình thay thế<br/>Cấp phát & thu hồi"]
    P --> A["Ứng dụng<br/>Kiểm tra quyền nghiệp vụ"]
    S --> A
    A --> R["Readback / đối soát<br/>Quyền thực tế"]
    R --> I
    I --> L["Nhật ký / bằng chứng kiểm toán"]
    A --> L
~~~

**SCIM là giao thức đồng bộ danh tính**, không phải cam kết rằng mọi ứng dụng đều hỗ trợ đầy đủ create/update/deactivate/delete, đồng bộ nhóm và thu hồi phiên. Mỗi tích hợp cần được kiểm tra khả năng và kết quả thực tế. Với federation, tổ chức nhận vẫn cần áp đặt phạm vi và thời hạn truy cập riêng.

### Lỗi minh họa: tài khoản đã khóa ở IdP nhưng quyền vẫn tồn tại

Một nhà thầu đã bị vô hiệu hóa ở IdP nhưng còn **phiên ứng dụng cũ**, **token truy cập độc lập**, **tài khoản local** hoặc **API key** do nhà thầu quản lý. Trong một số hệ thống, các đường truy cập này có thể còn hiệu lực đến khi hết hạn hoặc bị thu hồi riêng.

Vì vậy, điều kiện hoàn thành Leaver phải dựa trên **quyền truy cập thực tế không còn hiệu lực trong phạm vi cần thu hồi**, thay vì chỉ kiểm tra một cờ `disabled=true` ở IdP.

## 8. Quản trị ngoại lệ và quyền truy cập tạm thời

Không thể dự đoán mọi nhiệm vụ bằng gói quyền chuẩn. Contractor có thể cần truy cập khẩn cấp để xử lý sự cố, kiểm thử đặc biệt hoặc đọc tập dữ liệu ngoài scope ban đầu. Ngoại lệ hợp lệ vẫn cần cấu trúc.

Một yêu cầu ngoại lệ tốt nên ghi:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| Người yêu cầu và danh tính | Contractor C-1042 | Tránh quyền dùng chung vô danh |
| Sponsor và owner dữ liệu | Quản lý dự án và chủ dữ liệu | Người chịu trách nhiệm nghiệp vụ |
| Mục đích | Phân tích lỗi dịch vụ trong lần triển khai | Liên kết quyền với nhiệm vụ |
| Hành động/tài nguyên | Đọc log dịch vụ X ở production | Giới hạn quyền |
| Thời gian | Từ lúc kích hoạt đến mốc hết hạn được duyệt | Tránh ngoại lệ vĩnh viễn |
| Điều kiện | MFA, thiết bị, kết nối và giám sát phù hợp | Giảm rủi ro |
| Phê duyệt và bằng chứng | Quyết định, người duyệt, mã yêu cầu | Có thể kiểm toán |
| Hoàn tất | Trạng thái thu hồi đã xác nhận | Khép kín vòng đời |

Đối với trường hợp khẩn cấp, tổ chức có thể đặt quy trình phê duyệt nhanh hơn nhưng vẫn phải có **nhật ký, owner, giới hạn thời gian và bước hậu kiểm**. Không biến trường hợp khẩn cấp thành lý do duy trì quyền admin sau sự cố.

## 9. Nhận diện và xử lý quyền truy cập tồn dư

**Residual access** là quyền vẫn tồn tại dù không còn căn cứ hợp lệ từ hợp đồng, dự án, vai trò hoặc chính sách. Với contractor, rủi ro này đáng chú ý vì các thay đổi hợp đồng và nhà cung cấp có thể diễn ra ngoài hệ thống nhân sự chính.

Những nguồn tạo quyền tồn dư thường gặp:

| Nguồn sai lệch | Ví dụ | Kiểm soát khắc phục |
|---|---|---|
| Không quản lý ngày hết hạn | Nhà thầu kết thúc hợp đồng nhưng tài khoản vẫn active | Expiry bắt buộc và tác vụ thu hồi theo nguồn có thẩm quyền |
| Gia hạn vô điều kiện | Gia hạn hợp đồng kéo dài cả quyền admin cũ | Rà soát scope và phê duyệt lại quyền nhạy cảm |
| Chuyển dự án chỉ thêm quyền | Quyền repo/dữ liệu dự án A vẫn giữ khi sang B | Tính lại tập quyền mong muốn, thu hồi quyền cũ |
| Cấp quyền trực tiếp ngoài IAM | Owner tài liệu chia sẻ trực tiếp cho email cá nhân | Kiểm kê quyền trực tiếp và quy tắc chia sẻ |
| Nhóm lồng nhau và vai trò kế thừa | Xóa một nhóm nhưng quyền vẫn đến từ nhóm khác | Phân tích nguồn quyền hiệu dụng |
| SCIM/API lỗi một phần | IdP đã cập nhật, ứng dụng chưa xử lý | Theo dõi lỗi, retry có kiểm soát, readback |
| Phiên/token còn hiệu lực | Ứng dụng không hủy phiên khi tài khoản mất quyền | Xác định cơ chế chặn/thu hồi phiên-token từng đích |
| Tài khoản dịch vụ bị dùng chung | Nhà thầu biết secret vẫn còn hoạt động | Kiểm kê, chuyển ownership, xoay vòng/thu hồi secret theo mức độ phơi lộ |
| Không còn sponsor | Quản lý dự án nghỉ việc, không ai tái chứng nhận | Quy trình chuyển sponsor, escalation và xử lý quyền thiếu owner |
| Tái gia nhập dùng lại quyền cũ | Hợp đồng mới nhưng vai trò cũ tự khôi phục | Tính quyền theo engagement mới |

**Nguyên tắc đối soát:** So sánh tập quyền **mong muốn** theo chính sách với quyền **hiệu dụng** trên từng ứng dụng. Cần tính đến các nguồn cấp quyền hợp lệ đồng thời: role, nhóm, cấp trực tiếp, chia sẻ tài nguyên và ngoại lệ. Chỉ xóa một nhóm không đủ để khẳng định một quyền đã biến mất.

### Đối soát tập quyền minh họa

~~~text
Contractor: C-1042
Engagement: Project-A (đã kết thúc)

Quyền mong muốn: {}
Quyền thực tế:
    git/project-A/read
    cloud/staging/deploy
    docs/project-A/read

Sai lệch cần xử lý:
    git/project-A/read
    cloud/staging/deploy
    docs/project-A/read

Sau thu hồi:
    readback ứng dụng + kiểm tra đường truy cập liên quan
    lưu trạng thái COMPLETED khi mọi hạng mục bắt buộc đều đã xác minh
~~~

Nếu nhà thầu có **hợp đồng thứ hai còn hiệu lực**, không nên xóa máy móc mọi tài khoản/quyền. Phải xác định chính xác **quyền nào còn được quan hệ nào bảo trợ**, rồi thu hồi các quyền không còn căn cứ. Đây là lý do nên tách **identity**, **engagement** và **entitlement** trong mô hình dữ liệu.

## 10. Kiểm toán, rà soát và chứng nhận lại quyền

Với contractor, việc kiểm toán nên trả lời được:

- **Ai** là cá nhân đứng sau yêu cầu, tài khoản hay phiên đã sử dụng?
- **Vì sao** người đó được truy cập? Hợp đồng, dự án và sponsor nào là căn cứ?
- **Quyền gì** đã được phê duyệt và có hiệu lực tại thời điểm nào?
- **Ai duyệt**, áp dụng chính sách nào, có ngoại lệ hay xung đột SoD không?
- **Khi nào** quyền thay đổi/hết hạn, và kết quả thu hồi ở từng ứng dụng thế nào?
- **Có còn lối truy cập khác** qua tài khoản local, nhóm kế thừa, chia sẻ trực tiếp, token hoặc key không?

### 10.1. Access review cần đủ ngữ cảnh

Một màn hình rà soát quyền nhà thầu nên cung cấp ít nhất:

| Thông tin | Vì sao cần |
|---|---|
| Danh tính, tổ chức cung cấp, engagement | Phân biệt đúng người và đúng hợp đồng |
| Sponsor/owner hiện hành | Xác định người chịu trách nhiệm xác nhận |
| Trạng thái và ngày kết thúc | Phát hiện quyền đã quá hạn |
| Ứng dụng, vai trò, quyền hiệu dụng | Biết phạm vi thực sự được truy cập |
| Nguồn cấp và lý do quyền | Phân biệt role chuẩn, cấp trực tiếp và ngoại lệ |
| Thời điểm sử dụng gần nhất nếu đáng tin cậy | Hỗ trợ đánh giá quyền không còn cần thiết |
| Quyền nhạy cảm, môi trường và SoD | Ưu tiên xem xét rủi ro cao |
| Quyết định giữ/sửa/thu hồi và bằng chứng kết quả | Kiểm chứng hành động sau review |

Một lượt “approve tất cả” không có bằng chứng về nhu cầu hiện tại không chứng minh quyền đã đúng. Sponsor phải có khả năng **từ chối, yêu cầu thu hồi, thay đổi hạn** và theo dõi quyết định đã được thực thi.

### 10.2. Các chỉ số có ích

| Chỉ số | Cách hiểu | Lưu ý |
|---|---|---|
| Tỷ lệ contractor có sponsor hợp lệ | Số contractor đang hoạt động có owner / tổng số contractor đang hoạt động | Owner phải là người thực sự chịu trách nhiệm |
| Tỷ lệ engagement có hạn rõ ràng | Số engagement có start/end được xác nhận / tổng số engagement | Hạn tài khoản không được vượt căn cứ hợp lệ |
| Thời gian cấp quyền hợp lệ | Từ mốc được phép cấp đến lúc quyền dùng được | Đo cả ứng dụng, không chỉ IdP |
| Thời gian thu hồi sau Leaver | Từ mốc yêu cầu thu hồi đến lúc quyền thực tế không còn hiệu lực | Định nghĩa rõ phạm vi session/token/local account |
| Số quyền quá hạn/tồn dư | Entitlement không có engagement/chính sách hợp lệ | Xét quyền kế thừa và ngoại lệ |
| Tỷ lệ lỗi đồng bộ được xử lý | Sự kiện SCIM/API lỗi có readback khắc phục / tổng sự kiện lỗi | Không coi gửi lệnh là đã thành công |
| Tỷ lệ access review có hành động hoàn tất | Quyền đã giữ/sửa/thu hồi và xác minh / quyền đến kỳ | Tách quyết định và triển khai |

Không có một ngưỡng SLA chung phù hợp cho mọi môi trường. Độ khẩn cấp thu hồi phụ thuộc vào chính sách, mức nhạy cảm và rủi ro; tuy nhiên, phải có **mốc kiểm soát rõ ràng, đo được và được giám sát**.

## 11. Tình huống thực tế: contractor vận hành nền tảng trong sáu tuần

**Bối cảnh:** Một chuyên gia ngoài tên An được thuê hỗ trợ tối ưu hạ tầng cho dự án Orion trong sáu tuần. Sponsor là quản lý vận hành nội bộ. An cần xem log và dashboard của môi trường staging, có thể cần thao tác restart một dịch vụ production nếu phát sinh sự cố và được phê duyệt.

### Thiết kế không phù hợp

- Cấp một tài khoản admin chung cho mọi nhà thầu trong dự án.
- Gán quyền quản trị production ngay từ ngày đầu để “đỡ xin lại”.
- Không ghi sponsor hoặc ngày hết hạn của quyền.
- Đăng nhập SSO thành công thì coi như đủ an toàn, không kiểm tra role trong ứng dụng.
- Kết thúc dự án chỉ vô hiệu hóa tài khoản ở IdP, bỏ sót quyền chia sẻ log, token và phiên ứng dụng.

Hậu quả là khó truy vết ai đã thao tác, đặc quyền được giữ quá lâu và có thể tồn tại các đường truy cập ngoài quy trình thu hồi.

### Thiết kế phù hợp hơn

**Bước 1 – Xác minh:** Nhận yêu cầu từ nguồn hợp đồng có thẩm quyền, xác nhận An là đúng cá nhân, sponsor và cửa sổ sáu tuần.

**Bước 2 – Thiết lập danh tính:** Tạo hoặc liên kết danh tính riêng cho An, dùng SSO/federation và cơ chế MFA phù hợp; gắn engagement `Orion-Operations` với ngày hết hạn.

**Bước 3 – Cấp quyền nền tảng:** Gán quyền **đọc log/dashboard staging của Orion**. Không cho đọc dữ liệu dự án khác và không mặc định có quyền restart production.

**Bước 4 – Quyền nhạy cảm:** Khi có sự cố, An yêu cầu quyền restart đúng dịch vụ với mục đích, cửa sổ thời gian ngắn và phê duyệt của người có thẩm quyền. Dùng JIT/PAM nếu có và kiểm tra hành động ở ứng dụng/API.

**Bước 5 – Đối soát:** IAM kiểm tra quyền hiện có, quyền mới được cấp, thông tin phiên/token và kết quả ở từng ứng dụng; ghi vết thao tác.

**Bước 6 – Mover/Extension:** Nếu An chuyển sang dự án khác hoặc hợp đồng gia hạn, sponsor phải xác nhận lại quyền, thời hạn và mọi ngoại lệ. Quyền Orion không tự đi theo hợp đồng mới.

**Bước 7 – Leaver:** Khi sáu tuần kết thúc, hệ thống thu hồi các quyền thuộc engagement Orion, chặn phiên và credential cần thiết, chuyển giao công việc rồi xác minh ở ứng dụng đích. Nếu An còn engagement khác hợp lệ, giữ riêng các quyền thực sự thuộc engagement ấy.

**Điểm kiểm tra quan trọng:** Không thể kết luận an toàn chỉ vì An không còn đăng nhập mới qua IdP. IAM phải kiểm tra các quyền và đường truy cập khác có thể vẫn hoạt động.

## 12. Những quyết định thiết kế thường gây tranh luận

### Có bắt buộc mọi contractor dùng tài khoản nội bộ không?

Không nhất thiết. **Federation** có thể phù hợp khi có cơ chế tin cậy và các điều kiện xác thực, quản trị, thu hồi đáp ứng yêu cầu. Tài khoản nội bộ có thể phù hợp khi tổ chức cần quyền kiểm soát trực tiếp hoặc đối tác không đáp ứng điều kiện. Dù chọn cách nào, **authorization và thời hạn hợp đồng** vẫn thuộc trách nhiệm hệ thống nhận truy cập.

### Có nên xóa ngay toàn bộ danh tính khi hợp đồng kết thúc?

Cần **thu hồi truy cập kịp thời** theo chính sách. Việc xóa hẳn bản ghi danh tính, dữ liệu giao dịch hoặc log có thể bị ràng buộc bởi quy định lưu giữ, điều tra và kiểm toán. Có thể giữ hồ sơ cần thiết ở trạng thái không còn truy cập, với bảo vệ dữ liệu phù hợp.

### Một người ký nhiều hợp đồng thì nên có bao nhiêu danh tính?

Nên thiết kế để có thể **liên kết các engagement với đúng cá nhân** mà vẫn truy vết rõ từng quyền. Không suy luận người là cùng một chỉ từ email hiển thị; các hệ thống liên kết nên dựa trên định danh và bằng chứng đáng tin cậy. Một danh tính có thể phục vụ nhiều engagement, nhưng quyền và ngày hết hạn cần gắn với từng căn cứ. Thiết kế cụ thể tùy kiến trúc IdP và chính sách tổ chức.

### Nhà thầu có thể dùng tài khoản dịch vụ để chạy tác vụ không?

Có thể được giao trách nhiệm đối với một **service account** của hệ thống, nhưng không nên đồng nhất tài khoản dịch vụ với danh tính cá nhân. Tài khoản máy cần owner kỹ thuật, quyền tối thiểu, quản lý credential và kiểm toán riêng. Khi nhà thầu rời đi, phải rà soát khả năng họ còn biết, sở hữu hoặc sử dụng bí mật/token liên quan; xoay vòng hoặc thu hồi khi chính sách và rủi ro yêu cầu.

## 13. Bài tập tự kiểm tra

### Tình huống A: Nhà thầu chuyển dự án

Công ty đối tác cử Bình làm dự án A trong hai tháng. Sau một tháng, Bình được chuyển sang dự án B. Tài khoản Bình vẫn active, có quyền đọc kho mã của A và được bổ sung quyền sửa kho mã của B.

**Câu hỏi:** Vì sao đây là một dấu hiệu cần điều tra? IAM cần làm gì?

**Gợi ý:** Phải xác định engagement A đã kết thúc hay còn nhiệm vụ hợp lệ, rồi **thu hồi quyền A không còn căn cứ**. Không nên suy ra rằng tài khoản còn active thì mọi quyền cũ đều hợp lệ. Cần kiểm tra nhóm, quyền trực tiếp, quyền kế thừa, repo và token, sau đó đối soát.

### Tình huống B: Hợp đồng hết hạn nhưng SSO vẫn có phiên

Hà là chuyên gia kiểm thử bên ngoài. Hợp đồng kết thúc vào thứ Sáu. Thứ Hai, tài khoản tại IdP đã bị disable, nhưng Hà vẫn có thể dùng một phiên đang mở trong công cụ quản lý dự án.

**Câu hỏi:** Quy trình Leaver đã hoàn tất chưa? Cần khắc phục ở đâu?

**Gợi ý:** Chưa thể coi là hoàn tất nếu đường truy cập cần thu hồi vẫn hoạt động. Cần kiểm tra ứng dụng quản lý dự án, phiên và token của ứng dụng, khả năng thu hồi phiên hoặc chặn truy cập ở tầng ứng dụng, quyền cục bộ và bằng chứng readback.

### Tình huống C: Nhà thầu giữ tài khoản máy

Một contractor từng quản trị pipeline CI/CD bằng secret được lưu trong cấu hình dự án. Hợp đồng kết thúc nhưng pipeline vẫn chạy bình thường.

**Câu hỏi:** Có cần xóa ngay service account không? Rủi ro nào còn lại?

**Gợi ý:** Không nên xóa tùy tiện nếu tài khoản là một phụ thuộc sản xuất hợp lệ. Cần chuyển ownership, xác định nhà thầu có biết/kiểm soát secret nào, xoay vòng hoặc thu hồi secret theo rủi ro, rà soát quyền và nhật ký truy cập. Danh tính máy tiếp tục tồn tại chỉ khi có chủ sở hữu và mục đích hợp lệ.

### Câu hỏi củng cố

1. Sponsor khác người phê duyệt quyền truy cập như thế nào?
2. Tại sao SCIM đã cập nhật thành công vẫn chưa chắc ứng dụng chặn được mọi phiên cũ?
3. Contractor đã gia hạn hợp đồng có được tự gia hạn toàn bộ quyền admin không?
4. Thế nào là quyền tồn dư khi một người có hai engagement đang hoạt động?
5. Những bằng chứng tối thiểu nào cho thấy quy trình Leaver đã hoàn tất?

Hãy giải thích câu trả lời dựa trên **căn cứ cấp quyền, trạng thái thực tế tại hệ thống và phạm vi từng engagement**.

## 14. Checklist triển khai quản lý Contractor trong IAM

Trước khi cấp hoặc duy trì quyền cho một nhà thầu, cần xác minh:

- [ ] **Danh tính:** Đúng cá nhân, có cách liên kết định danh đáng tin cậy và không dùng tài khoản chung.
- [ ] **Căn cứ:** Có hợp đồng/nhiệm vụ hợp lệ từ nguồn có thẩm quyền, dự án và mục đích rõ ràng.
- [ ] **Owner:** Có sponsor còn trách nhiệm, chủ sở hữu dữ liệu và đường escalation.
- [ ] **Thời gian:** Ngày bắt đầu/kết thúc được định nghĩa; gia hạn phải được phê duyệt và kiểm tra lại.
- [ ] **Phân quyền:** Chỉ có hành động, tài nguyên, môi trường và dữ liệu phục vụ nhiệm vụ; RBAC/ABAC/SoD áp dụng phù hợp.
- [ ] **Xác thực:** IdP/SSO hoặc tài khoản được quản lý, MFA và chính sách phiên đáp ứng yêu cầu.
- [ ] **Provisioning:** SCIM/API hoặc quy trình thay thế được theo dõi; quyền thực tế được đọc lại.
- [ ] **Thay đổi:** Chuyển dự án/sponsor sẽ tính lại cả quyền cần cấp và quyền cần thu hồi.
- [ ] **Đặc quyền:** Quyền nhạy cảm có phê duyệt, thời hạn và ghi vết; ưu tiên JIT/PAM khi phù hợp.
- [ ] **Offboarding:** Thu hồi tài khoản, nhóm, quyền trực tiếp, truy cập chia sẻ, phiên, token và credential liên quan.
- [ ] **Danh tính máy:** Tài khoản dịch vụ nhà thầu từng vận hành có owner mới, quyền phù hợp và credential được xử lý.
- [ ] **Kiểm toán:** Có bằng chứng về biến cố JML, người duyệt, trạng thái từng ứng dụng, kết quả đối soát và quyền tồn dư.
- [ ] **Rà soát:** Định kỳ xác nhận engagement, sponsor và các entitlement nhạy cảm vẫn còn cần thiết.

**Ghi nhớ:** Contractor trong IAM không chỉ là “một tài khoản ngoài công ty”. Đó là **một danh tính con người gắn với quan hệ công việc có thể thay đổi hoặc chấm dứt**, được quản trị bằng **nguồn xác thực đáng tin, sponsor, phạm vi quyền, thời hạn và bằng chứng thu hồi**. Thiết kế đúng vòng đời Joiner–Mover–Leaver, phối hợp IdP/SSO/SCIM với RBAC/ABAC và đối soát quyền hiệu dụng là nền tảng để giảm **quyền truy cập tồn dư** mà vẫn giúp nhà thầu làm việc đúng nhiệm vụ.
