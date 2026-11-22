# Thiết kế truy cập ứng dụng đơn tenant và đa tenant

Một ứng dụng Azure có thể chỉ phục vụ nhân viên trong một tổ chức, hoặc cung cấp dịch vụ cho người dùng thuộc nhiều tổ chức khác nhau. Hai mô hình này có cách đăng ký ứng dụng, chọn điểm đăng nhập, chấp thuận quyền, xác thực token và cô lập dữ liệu khác nhau. Việc chọn sai mô hình có thể khiến người dùng không đăng nhập được, buộc quản trị viên phải cấp quyền quá rộng, hoặc dẫn đến nguy cơ truy cập chéo dữ liệu giữa các khách hàng.

Bài học thuộc chương **Danh tính với Microsoft Entra ID** trong module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu Azure từ subscription, resource group và Entra ID đến mạng ảo, compute, storage, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí. Trong kiến trúc đó, Microsoft Entra ID đảm nhiệm xác thực danh tính và cấp token cho ứng dụng. Bài học tập trung thiết kế quyền truy cập **single-tenant** (đơn tenant) và **multi-tenant** (đa tenant), từ trải nghiệm đăng nhập đến bảo mật API và dữ liệu.

Sau khi học, bạn có thể:

- Phân biệt tenant, app registration, application object, service principal và enterprise application.
- Chọn single-tenant, single-tenant kết hợp B2B guest, hoặc multi-tenant theo yêu cầu thực tế.
- Cấu hình các loại tài khoản được hỗ trợ, redirect URI và điểm cuối xác thực.
- Mô tả luồng OpenID Connect/OAuth 2.0, delegated permission, application permission và consent.
- Thiết kế xác thực token, kiểm soát tenant được phép truy cập và phân quyền bên trong ứng dụng.
- Xây dựng quy trình onboarding/offboarding khách hàng cho ứng dụng SaaS multi-tenant.
- Đánh giá rủi ro như chấp nhận nhầm issuer, tin vào email thay vì danh tính đã xác thực, và lộ dữ liệu giữa các tenant.

## 1. Các khái niệm nền tảng

**Tenant Microsoft Entra ID** là ranh giới quản lý danh tính của một tổ chức. Mỗi tenant có định danh riêng (tenant ID), người dùng, nhóm, ứng dụng doanh nghiệp và chính sách truy cập. Tenant là khái niệm danh tính, khác với **Azure subscription**, vốn chủ yếu tổ chức tài nguyên, quyền quản trị và thanh toán. Một tenant có thể liên kết nhiều subscription.

Để tích hợp ứng dụng với Entra ID, cần hiểu các đối tượng sau:

| Khái niệm | Ý nghĩa | Vai trò trong thiết kế |
|---|---|---|
| App registration | Cấu hình ứng dụng trong tenant sở hữu: tên, client ID, redirect URI, đối tượng tài khoản hỗ trợ, quyền API | Nơi nhà phát triển mô tả ứng dụng |
| Application object | Đối tượng định nghĩa ứng dụng, tồn tại trong **home tenant** nơi ứng dụng được đăng ký | Mẫu cấu hình dùng cho các tenant tiếp nhận |
| Service principal | Danh tính/cá thể ứng dụng trong một tenant cụ thể | Cơ sở để tenant đó quản lý quyền truy cập và consent |
| Enterprise application | Giao diện quản trị service principal trong tenant | Quản lý người dùng được gán, SSO, chính sách và quyền ứng dụng |
| Client ID (Application ID) | Định danh của ứng dụng, thường là GUID | Ứng dụng khai báo định danh khi yêu cầu token |
| Tenant ID (Directory ID) | Định danh của tenant | Dùng để chọn tenant, kiểm tra issuer và cô lập dữ liệu |

Với một ứng dụng single-tenant, application object và service principal thường đều nằm trong tenant sở hữu. Với ứng dụng multi-tenant, **application object vẫn thuộc home tenant**, còn **service principal có thể được tạo ở từng tenant khách hàng** khi ứng dụng được chấp thuận/sử dụng theo quy trình Entra ID.

Ví dụ một nhà cung cấp đăng ký ứng dụng trong tenant **Vendor**. Khi khách hàng A và B chấp thuận ứng dụng, mỗi tenant khách hàng có service principal riêng cho cùng một application ID. Nhờ đó, quản trị viên khách hàng có thể kiểm soát ứng dụng được phép dùng trong tổ chức của mình.

~~~text
Home tenant: Vendor
  |
  +-- Application object: SaaS Portal (Client ID: app-123)
  +-- Service principal của SaaS Portal tại Vendor

Tenant khách hàng A
  +-- Service principal của SaaS Portal (app-123)
  +-- Người dùng, nhóm, chính sách và quyền của tenant A

Tenant khách hàng B
  +-- Service principal của SaaS Portal (app-123)
  +-- Người dùng, nhóm, chính sách và quyền của tenant B
~~~

Việc có service principal ở tenant khách hàng **không tự động chứng minh khách hàng đã mua dịch vụ, được phép truy cập dữ liệu hoặc đã được ứng dụng kích hoạt**. Ứng dụng cần một lớp quản lý khách hàng riêng để xác định tenant nào đã được tiếp nhận.

## 2. Single-tenant và multi-tenant khác nhau thế nào?

| Tiêu chí | Single-tenant | Multi-tenant |
|---|---|---|
| Đối tượng chính | Danh tính trong một tenant Entra ID đã chọn | Danh tính từ nhiều tenant Entra ID |
| App registration | Chỉ hỗ trợ tài khoản của home tenant | Hỗ trợ tài khoản của nhiều tổ chức |
| Điểm đăng nhập | Authority cụ thể của tenant | Authority hỗ trợ nhiều tổ chức hoặc tenant cụ thể sau khi xác định khách hàng |
| Service principal | Trong tenant sở hữu | Ở home tenant và các tenant khách hàng sau khi tiếp nhận/consent |
| Consent | Theo quy trình của một tenant | Từng tenant khách hàng có chính sách và trạng thái consent riêng |
| Kiểm tra tenant | Thường cố định tenant ID đã chọn | Bắt buộc kiểm tra issuer, tenant ID và danh sách tenant được ứng dụng cho phép |
| Dữ liệu | Thường một miền tổ chức | Cần cô lập dữ liệu theo từng khách hàng/tenant |
| Vận hành | Ít quy trình onboarding khách hàng | Cần onboarding, consent, phân quyền và offboarding cho mỗi tenant |

**Single-tenant** thường dành cho cổng nhân sự, hệ thống kế toán nội bộ, dashboard vận hành hoặc một ứng dụng phục vụ một doanh nghiệp. **Multi-tenant** phù hợp với sản phẩm SaaS có khách hàng là các tổ chức độc lập, chẳng hạn hệ thống quản lý hóa đơn cho nhiều công ty.

Một ứng dụng phục vụ nhiều phòng ban trong cùng một tenant **không nhất thiết phải multi-tenant**. Ngược lại, ứng dụng phục vụ hai tổ chức có hai tenant độc lập thường cần multi-tenant hoặc một kiến trúc mời khách B2B vào tenant được chọn.

## 3. Chọn mô hình theo yêu cầu nghiệp vụ

Trước khi chọn Supported account types, hãy trả lời:

1. Ai là người dùng: nhân viên một doanh nghiệp, khách mời đối tác, hay khách hàng của nhiều doanh nghiệp?
2. Các danh tính thuộc cùng một tenant hay các tenant độc lập?
3. Mỗi khách hàng có cần tự quản trị consent, MFA, Conditional Access và việc gán người dùng không?
4. Dữ liệu được chia sẻ trong một tổ chức hay phải cách ly tuyệt đối theo khách hàng?
5. Ứng dụng chỉ phục vụ người dùng tương tác, hay còn có tác vụ nền truy cập API?
6. Có cần hỗ trợ tài khoản Microsoft cá nhân (MSA) ngoài tài khoản công việc/trường học không?

### Tình huống A: ứng dụng nội bộ

Công ty có tenant **Corp-A** và một cổng nhân viên. Nhân viên chỉ được đăng nhập bằng danh tính do Corp-A quản lý. Chọn **single-tenant**. Dùng tenant ID của Corp-A để cấu hình authority và các chính sách cấp quyền nội bộ.

### Tình huống B: một ít đối tác bên ngoài

Đội dự án Corp-A mời 15 chuyên gia từ công ty đối tác để cùng dùng một cổng cộng tác. Có thể dùng **Microsoft Entra B2B collaboration** để mời người dùng bên ngoài làm **guest** trong tenant Corp-A, rồi để ứng dụng tiếp tục ở mô hình single-tenant.

Guest được biểu diễn bằng một đối tượng người dùng trong tenant Corp-A. Token dùng để truy cập ứng dụng single-tenant thường gắn với tenant tài nguyên này; danh tính gốc của guest có thể nằm ở tenant khác. Vì vậy, **single-tenant không đồng nghĩa chỉ có nhân viên cơ hữu** và multi-tenant không phải điều kiện bắt buộc để mời vài đối tác.

### Tình huống C: sản phẩm SaaS cho nhiều doanh nghiệp

Nhà cung cấp bán phần mềm quản lý tài sản cho A, B, C. Mỗi khách hàng muốn nhân viên đăng nhập bằng tenant Entra ID của chính mình, quản lý consent và chính sách truy cập. Chọn **multi-tenant** và thiết kế quá trình tiếp nhận tenant, phân quyền, cô lập dữ liệu, nhật ký kiểm toán và thu hồi truy cập.

### Tình huống D: ứng dụng cho người dùng cá nhân

Nếu sản phẩm phải hỗ trợ tài khoản Microsoft cá nhân, cần chọn loại Supported account types cho phép **personal Microsoft accounts**, đồng thời dùng các endpoint và quy trình phù hợp. Đây là lựa chọn riêng, không tự động đi kèm với multi-tenant dành cho các tổ chức. Nếu cần quản lý tài khoản khách hàng phổ thông, cũng nên đánh giá Microsoft Entra External ID theo nhu cầu quản lý khách hàng.

## 4. Supported account types và authority

Trong Azure Portal, mở **Microsoft Entra ID > App registrations > New registration**. Phần **Supported account types** quyết định loại tài khoản mà đăng ký ứng dụng chấp nhận.

| Tùy chọn | Ý nghĩa thiết kế |
|---|---|
| Accounts in this organizational directory only | Single-tenant trong một tenant xác định |
| Accounts in any organizational directory | Multi-tenant cho các tenant Microsoft Entra ID của tổ chức |
| Accounts in any organizational directory and personal Microsoft accounts | Tổ chức đa tenant cùng tài khoản Microsoft cá nhân |
| Personal Microsoft accounts only | Chỉ tài khoản Microsoft cá nhân, khi loại ứng dụng và trường hợp sử dụng hỗ trợ |

**Authority** là địa chỉ dịch vụ xác thực dùng khi ứng dụng điều hướng đăng nhập và yêu cầu token. Với điểm cuối Microsoft identity platform v2:

~~~text
Single-tenant:
https://login.microsoftonline.com/<TENANT_ID>/v2.0

Multi-tenant cho tài khoản tổ chức:
https://login.microsoftonline.com/organizations/v2.0

Đa tổ chức và tài khoản Microsoft cá nhân, nếu app registration cho phép:
https://login.microsoftonline.com/common/v2.0

Đăng nhập bằng tenant đã xác định:
https://login.microsoftonline.com/<CUSTOMER_TENANT_ID>/v2.0
~~~

Các giá trị **organizations**, **common** và **consumers** là những phân đoạn đặc biệt của điểm đăng nhập; chúng không phải tenant ID thực tế của khách hàng. **organizations** nhắm đến tài khoản công việc/trường học. **common** cho phép chọn tài khoản tổ chức hoặc cá nhân khi ứng dụng được cấu hình hỗ trợ. **consumers** hướng đến tài khoản Microsoft cá nhân.

Với ứng dụng multi-tenant, dùng **organizations** để bắt đầu đăng nhập không có nghĩa là chấp nhận mọi tenant cho truy cập sản phẩm. Sau khi xác thực, máy chủ ứng dụng vẫn phải kiểm tra issuer và tenant được phép sử dụng dịch vụ.

Không nhầm **Tenant ID** với **Client ID**: Tenant ID xác định thư mục danh tính; Client ID xác định ứng dụng. Cả hai thường đều là GUID nên rất dễ sao chép nhầm.

## 5. Luồng xác thực: đăng nhập và gọi API

Ứng dụng web thường dùng **OpenID Connect (OIDC)** để xác thực người dùng, dựa trên **OAuth 2.0 Authorization Code Flow** để nhận các token cần thiết. Với SPA và ứng dụng public client, phải sử dụng **PKCE**. Ứng dụng web có backend thường dùng confidential client và giữ thông tin xác thực phía server; không đưa client secret vào JavaScript chạy trong trình duyệt.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant W as Web app
    participant E as Microsoft Entra ID
    participant A as API
    U->>W: Chọn Đăng nhập
    W->>E: Authorization request (state, nonce, PKCE nếu áp dụng)
    E->>U: Xác thực, MFA/Conditional Access nếu áp dụng
    U->>E: Hoàn tất đăng nhập
    E-->>W: Authorization code
    W->>E: Đổi code lấy token qua kênh phù hợp
    E-->>W: ID token và/hoặc access token
    W->>W: Xác thực danh tính, tenant, quyền và tạo session
    W->>A: Yêu cầu kèm access token dành cho API
    A->>A: Xác thực chữ ký, issuer, audience, expiry, tenant, quyền
    A-->>W: Kết quả theo phạm vi dữ liệu được phép
~~~

Các khái niệm token phải được tách bạch:

| Thành phần | Dùng để làm gì | Không nên dùng để làm gì |
|---|---|---|
| **ID token** | Cho client biết kết quả xác thực người dùng theo OIDC | Thay access token để gọi API |
| **Access token** | Chứng minh quyền truy cập đến **một resource/API cụ thể** | Làm bằng chứng cấp quyền cho API khác audience |
| **Refresh token** | Hỗ trợ nhận access token mới theo chính sách và loại ứng dụng | Lưu không bảo vệ hoặc gửi tới API như access token |
| **Session cookie** | Duy trì phiên ứng dụng web sau khi xác thực | Làm bằng chứng quyền tùy ý nếu server không kiểm soát phiên |

Một giao diện web đăng nhập thành công chưa chứng minh người dùng được đọc mọi dữ liệu trong API. **API phải tự xác thực access token có audience của chính mình và kiểm tra quyền**. Mô hình này quan trọng đặc biệt với multi-tenant, vì cùng một API có thể nhận yêu cầu từ nhiều tổ chức.

## 6. Thiết kế ứng dụng single-tenant

Giả sử công ty A triển khai cổng quản lý chi phí nội bộ. Yêu cầu: chỉ danh tính trong tenant A được truy cập; một số người dùng có vai trò xem, số khác có vai trò quản trị.

### Bước 1: đăng ký ứng dụng

1. Mở **Azure Portal > Microsoft Entra ID > App registrations > New registration**.
2. Đặt tên, ví dụ **Contoso Expense Portal**.
3. Chọn **Accounts in this organizational directory only**.
4. Chọn loại nền tảng phù hợp và nhập redirect URI của ứng dụng, ví dụ **https://expenses.contoso.example/signin-oidc**.
5. Hoàn tất đăng ký, lưu **Application (client) ID** và **Directory (tenant) ID**.

Redirect URI phải được đăng ký chính xác theo nền tảng và môi trường. Tránh redirect URI quá rộng hoặc cho phép redirect tùy ý theo tham số người dùng. Đối với môi trường dev/test/prod, quản lý các URI và credential theo chính sách tách môi trường.

### Bước 2: cấu hình xác thực

Ví dụ các tham số cấu hình khái niệm:

~~~yaml
identity:
  authority: "https://login.microsoftonline.com/<TENANT_A_ID>/v2.0"
  clientId: "<WEB_APP_CLIENT_ID>"
  redirectUri: "https://expenses.contoso.example/signin-oidc"
  supportedTenants:
    - "<TENANT_A_ID>"
  flow: "authorization_code"
  usePkce: true
~~~

Đây là ví dụ mô tả thiết kế, không phải cấu hình có thể dùng nguyên văn cho mọi framework. Trong ứng dụng thực tế, dùng thư viện hỗ trợ như **MSAL** hoặc **Microsoft.Identity.Web** để xử lý OIDC, token cache, state/nonce và đổi authorization code.

### Bước 3: thiết kế quyền truy cập

Xác thực danh tính và ủy quyền là hai bước khác nhau. Bạn có thể tạo app roles như **Expenses.Reader** và **Expenses.Admin**, rồi gán người dùng hoặc nhóm theo nhu cầu. Ứng dụng kiểm tra role để xác định ai xem báo cáo, ai phê duyệt hay cấu hình chính sách.

Nếu nghiệp vụ yêu cầu chỉ một nhóm được phép đăng nhập, hãy xem xét thiết lập **User assignment required** trong **Enterprise applications** và gán người dùng/nhóm phù hợp, bên cạnh việc kiểm tra quyền tại ứng dụng. Việc gán user trong Entra ID không thay thế quy tắc phân quyền chi tiết cho từng bản ghi.

### Bước 4: xem xét khách mời

Nếu cần cộng tác với một đối tác, có thể mời họ làm guest qua Entra B2B vào tenant A và gán quyền theo nguyên tắc tối thiểu. Phải rà soát chính sách cross-tenant access, guest access và Conditional Access của tổ chức. Không kết luận rằng mọi guest đều được tự do truy cập ứng dụng chỉ vì họ đã được mời vào tenant.

## 7. Thiết kế ứng dụng multi-tenant cho SaaS

Giả sử nhà cung cấp **Vendor** vận hành ứng dụng quản lý hợp đồng cho các khách hàng A và B. Người dùng của từng khách hàng xác thực qua tenant Entra ID của chính họ; dữ liệu A và B phải cách ly.

### Kiến trúc tham chiếu

~~~text
                +-------------------------------+
                | SaaS web frontend / backend   |
                | Home tenant: Vendor           |
                | App registration: multi-tenant|
                +---------------+---------------+
                                |
                      OIDC / OAuth 2.0
                                |
                +---------------+---------------+
                | Microsoft Entra ID            |
                +---------------+---------------+
                                |
                +---------------+---------------+
                | SaaS API                      |
                | Validate token + tenant       |
                | Authorize user/app roles      |
                +---------------+---------------+
                                |
              +-----------------+------------------+
              |                                    |
     +--------v---------+                 +--------v---------+
     | Customer tenant A|                 | Customer tenant B|
     | Data partition A |                 | Data partition B |
     +------------------+                 +------------------+
~~~

Sơ đồ biểu diễn logic: tổ chức A/B có tenant danh tính độc lập, còn việc triển khai dữ liệu có thể nằm trong cùng một Azure subscription, nhiều subscription, một cơ sở dữ liệu có phân vùng hoặc các database riêng. **Multi-tenant identity** và **multi-tenant data architecture** là hai quyết định liên quan nhưng không đồng nhất.

### Bước 1: đăng ký ứng dụng

1. Trong home tenant của Vendor, vào **App registrations > New registration**.
2. Chọn **Accounts in any organizational directory** nếu chỉ phục vụ tài khoản công việc/trường học.
3. Cấu hình redirect URI đúng với kiểu web/SPA/mobile và môi trường.
4. Ghi lại client ID; xác định endpoint đăng nhập **organizations** hoặc tenant-specific sau khi người dùng chọn tổ chức.
5. Nếu backend API là một resource riêng, đăng ký/cấu hình API tương ứng, chỉ rõ scope hoặc app role mà client cần gọi.

Không mở rộng sang tài khoản Microsoft cá nhân nếu bài toán SaaS chỉ phục vụ khách hàng tổ chức. Một lựa chọn đăng ký quá rộng sẽ tăng số kịch bản xác thực và phân quyền cần kiểm thử.

### Bước 2: thiết kế tenant onboarding

Một quy trình onboarding an toàn thường gồm:

1. Khách hàng cung cấp hoặc xác nhận **tenant ID** của tổ chức.
2. Người có thẩm quyền trong tenant khách hàng xem xét ứng dụng và cấp **consent** khi các quyền được yêu cầu cần chấp thuận.
3. Entra ID tạo/quản lý service principal của ứng dụng tại tenant khách hàng theo luồng consent/provisioning phù hợp.
4. Backend xác thực kết quả đăng nhập hoặc callback từ consent flow; kiểm tra state, tenant, quyền và trạng thái phê duyệt.
5. Hệ thống SaaS gắn tenant ID với hồ sơ khách hàng, subscription sản phẩm và cấu hình phân vùng dữ liệu.
6. Admin khách hàng được gán vai trò quản trị trong sản phẩm và mời/gán người dùng theo chính sách.
7. Ứng dụng đánh dấu tenant **active** khi điều kiện về hợp đồng, consent và cấu hình đã đáp ứng.

Không nhận tenant ID từ một tham số HTTP rồi lập tức cấp quyền truy cập dữ liệu hoặc tạo khách hàng đã được kích hoạt. Tenant ID nhận từ đầu vào chỉ là dữ liệu để tra cứu/khởi đầu; chỉ sử dụng thông tin danh tính từ **token đã được xác thực** và bản ghi onboarding tin cậy để quyết định truy cập.

### Bước 3: yêu cầu consent phù hợp

Mỗi tenant có chính sách riêng về việc người dùng có được tự consent hay phải do quản trị viên duyệt. Quyền nhạy cảm hoặc application permission thường cần admin consent; các quyền delegated ít nhạy cảm có thể được người dùng chấp thuận tùy cấu hình và chính sách tenant.

Một ví dụ quản trị viên khách hàng có thể phải đồng ý cho SaaS đọc dữ liệu trong API riêng của SaaS hoặc truy cập Microsoft Graph theo quyền đã công bố. Chỉ yêu cầu những quyền ứng dụng thật sự cần để thực hiện tính năng đã nêu.

Consent **không thay thế authorization của SaaS**. Sau khi đã consent, người dùng thuộc tenant khách hàng vẫn có thể cần được gán vai trò sản phẩm, được cho phép truy cập một workspace và tuân theo chính sách bảo mật của tổ chức.

### Bước 4: tenant discovery và tenant-specific sign-in

Khi chưa biết tổ chức của người dùng, ứng dụng có thể bắt đầu với endpoint **organizations** để hỗ trợ đăng nhập đa tenant. Sau khi xác nhận tổ chức và tenant đã onboard, ứng dụng có thể dùng authority dạng **/CUSTOMER_TENANT_ID/v2.0** cho những tương tác cần ràng buộc tenant cụ thể.

Đừng phân định tenant bằng cách lấy phần tên miền email sau ký tự @. Một tổ chức có thể sở hữu nhiều domain; guest có thể dùng email thuộc tổ chức khác; email hoặc preferred username có thể đổi. Ưu tiên tenant ID từ token hợp lệ và danh sách tenant khách hàng đã xác thực.

## 8. OAuth 2.0 permissions: delegated, application, scope và app role

Trong kiến trúc có web frontend gọi API, cần phân biệt hai kiểu truy cập:

| Kiểu | Có người dùng đang đăng nhập? | Cấp quyền thường gặp | Luồng phổ biến |
|---|---|---|---|
| Delegated permissions | Có; ứng dụng hành động thay mặt người dùng | OAuth scopes, có thể kết hợp roles | Authorization code, On-Behalf-Of |
| Application permissions | Không cần người dùng; dịch vụ hành động với danh tính ứng dụng | Application roles/app permissions | Client credentials |

**Scope** mô tả quyền một client yêu cầu từ API thay mặt người dùng, ví dụ **Contracts.Read** hoặc **Contracts.Write**. Với access token delegated, claim **scp** thường chứa danh sách scope được cấp (các tên cách nhau bởi dấu cách).

**App role** có thể được gán cho người dùng/nhóm hoặc ứng dụng, tùy cấu hình. Access token có thể mang claim **roles**. Đừng giả định cứ có roles là luôn có người dùng; application token cũng thường chứa app roles khi được cấp application permissions.

Ví dụ:

~~~text
Frontend gọi API:
  Người dùng đăng nhập
  --> client xin scope api://<API_CLIENT_ID>/Contracts.Read
  --> API kiểm tra scp và quyền trên hợp đồng

Worker đồng bộ tự động:
  Không có người dùng
  --> client credentials xin quyền ứng dụng được consent
  --> API kiểm tra roles, danh tính caller và tenant được phép
~~~

Với client credentials, yêu cầu token đến resource thường dùng scope **{resource}/.default**, kết hợp quyền ứng dụng đã được cấu hình và consent; không dùng đây như cách vượt qua quy trình chấp thuận quyền.

Nếu một frontend/API thực hiện lời gọi đến một API khác thay mặt người dùng, có thể cân nhắc **On-Behalf-Of (OBO)**. Mỗi tầng phải sử dụng đúng token dành cho resource của mình; không chuyển tiếp ID token tới API downstream.

## 9. Xác thực và ủy quyền token trong single-tenant/multi-tenant

Một lỗi thiết kế nguy hiểm là chỉ giải mã JWT rồi tin vào các claim mà không xác thực chữ ký, issuer và audience. JWT có thể đọc được phần payload trước khi xác thực; dữ liệu đó **chưa đáng tin cậy**.

### Kiểm tra token bắt buộc

API cần sử dụng middleware/thư viện đã được kiểm chứng để:

1. Xác thực chữ ký theo các khóa ký của Microsoft Entra ID lấy từ OpenID Connect metadata đáng tin cậy, có quản lý thay đổi khóa.
2. Kiểm tra token chưa hết hạn, thời điểm hiệu lực và các điều kiện thời gian theo chính sách.
3. Xác nhận **aud** đúng với API/resource mà token được cấp cho.
4. Xác nhận **iss** hợp lệ và phù hợp tenant phát hành, không chấp nhận tùy tiện issuer không tin cậy.
5. Kiểm tra tenant ID (**tid**) sau khi token đã được xác thực.
6. Kiểm tra loại token, quyền delegated (**scp**) hoặc application role (**roles**) cùng các điều kiện riêng của endpoint.
7. Kiểm tra quyền ở cấp đối tượng nghiệp vụ: workspace, bản ghi, dự án, hợp đồng và phạm vi dữ liệu khách hàng.

Với single-tenant, chính sách issuer thường ràng buộc tenant đã chọn. Với multi-tenant, token từ những tenant khác nhau có issuer khác nhau. Ứng dụng cần dùng **tenant-aware issuer validation** theo hướng dẫn của Microsoft, rồi áp dụng chính sách tenant allowlist/onboarding của chính sản phẩm.

Tài liệu metadata OIDC cho một tenant cụ thể có dạng:

~~~text
https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration
~~~

Các thành phần như **organizations** hoặc **common** được dùng trong quá trình khám phá điểm đăng nhập; không coi chuỗi **common** là issuer thực của mọi access token. Để tránh lỗi bảo mật, hãy dùng thư viện chính thức phù hợp (MSAL/Microsoft.Identity.Web cùng middleware xác thực API), cấu hình issuer validation đúng theo loại ứng dụng và tenant.

### Các claim thường gặp

| Claim | Ý nghĩa | Cách dùng phù hợp |
|---|---|---|
| **tid** | Tenant phát hành token | Ánh xạ khách hàng đã onboard, sau khi token hợp lệ |
| **iss** | Issuer của token | Kiểm tra nguồn phát hành có được tin cậy |
| **aud** | Resource mà token hướng tới | Đảm bảo API chỉ nhận token của chính API đó |
| **oid** | Object ID của người dùng hoặc service principal trong tenant | Tạo khóa danh tính với tid khi thích hợp |
| **sub** | Định danh subject theo phạm vi ứng dụng | Có thể dùng làm subject đã xác thực theo thiết kế |
| **scp** | Delegated scopes được cấp | Kiểm tra thao tác người dùng có quyền thực hiện |
| **roles** | App roles/application permissions | Xác định vai trò và quyền gọi API |
| **azp** hoặc **appid** | Danh tính client gọi, tùy phiên bản token | Kiểm tra ứng dụng gọi khi API cần hạn chế client |

**UPN, preferred_username, name, email và domain** thường dùng cho hiển thị hoặc liên hệ, không nên là khóa cấp quyền ổn định. Với tài khoản guest, email có thể khác tenant quản lý đối tượng. Với dữ liệu ứng dụng, cặp **(tid, oid)** thường phù hợp để định danh đối tượng trong bối cảnh tenant khi các claim này có mặt và đã được xác thực.

### Ví dụ logic bảo vệ API

Mã sau là **giả mã** mô tả chính sách, không phải middleware JWT hoàn chỉnh:

~~~text
token = microsoftEntraJwtMiddleware.validate(
    signature = required,
    issuer = validTenantAwareIssuer,
    audience = expectedApiAudience,
    lifetime = required
)

tenantId = token.claim("tid")
if tenantId not in onboardedActiveTenants:
    reject(403, "Tenant chưa được kích hoạt")

if endpointRequiresDelegatedScope:
    requireScope(token, "Contracts.Read")
if endpointRequiresApplicationRole:
    requireAppRole(token, "Contracts.Sync")

customer = customerDirectory.lookupByTenantId(tenantId)
record = contractRepository.getByCustomerAndId(customer.id, request.contractId)
if record is missing or caller lacks access to record:
    reject(403, "Không có quyền truy cập")

return record
~~~

Middleware phải **xác thực token trước khi** ứng dụng tin và sử dụng tid, oid, scp hoặc roles. Trong mô hình SaaS, kiểm tra tenant active và kiểm tra quyền trên dữ liệu là lớp bảo vệ bắt buộc thêm ngoài việc xác thực JWT.

## 10. Cô lập dữ liệu trong ứng dụng multi-tenant

Đăng nhập đa tenant chỉ giải quyết câu hỏi **ai được xác thực**. Nó không tự ngăn người dùng khách hàng A truy vấn dữ liệu của khách hàng B. Phân tách dữ liệu phải được thiết kế và kiểm thử trong ứng dụng.

### Các mô hình lưu trữ

| Mô hình | Lợi ích | Điều cần kiểm soát |
|---|---|---|
| Chung database, chung bảng và có cột CustomerId/TenantId | Tiết kiệm tài nguyên, vận hành tập trung | Mọi truy vấn phải lọc theo tenant; cân nhắc row-level security |
| Chung database, schema hoặc tập bảng riêng | Phân tách logic rõ hơn | Migration, cấu hình và quyền truy cập theo từng schema |
| Database riêng cho từng tenant | Cách ly dữ liệu và backup thuận tiện hơn cho một số yêu cầu | Chi phí, provisioning, migration và giám sát từng tenant |
| Subscription hoặc môi trường triển khai riêng | Phù hợp khách hàng có yêu cầu cách ly và chính sách mạnh | Chi phí và độ phức tạp vận hành cao hơn |

Ví dụ nguy hiểm: API nhận **GET /contracts/123** và truy vấn chỉ bằng ID hợp đồng, không lọc customer. Người dùng A có thể thử ID của B và nhận dữ liệu nếu endpoint thiếu kiểm tra tenant.

Thiết kế an toàn:

~~~sql
SELECT ContractId, CustomerId, Title
FROM Contracts
WHERE ContractId = @contractId
  AND CustomerId = @customerIdFromValidatedTenantContext;
~~~

Giá trị **customerIdFromValidatedTenantContext** phải xuất phát từ ánh xạ tenant ID đã xác thực với hồ sơ khách hàng trong backend. Không được lấy từ query string, request body hay header do client tự gửi và tin nó là quyền hạn.

Ngoài lọc dữ liệu khi đọc, phải áp dụng cùng nguyên tắc cho tạo, cập nhật, xóa, export, cache, hàng đợi, file storage, search index, log và backup. Cần tránh dùng cache key chỉ chứa ID bản ghi mà không phân biệt khách hàng.

### Quyền quản trị từng khách hàng

Một người dùng có thể là admin trong tenant A nhưng chỉ là người đọc ở tenant B, hoặc có thể được mời làm guest ở nhiều tổ chức. Đừng gắn quyền vĩnh viễn với email. Hãy lưu mối quan hệ giữa danh tính đã xác thực, customer ID, membership và role trong ứng dụng; cập nhật khi khách hàng thay đổi phân quyền.

## 11. Consent, Conditional Access và vòng đời khách hàng

Trong multi-tenant SaaS, consent và phân quyền liên quan nhưng không đồng nhất:

- **Authentication:** Entra ID xác nhận danh tính và phát hành token theo cấu hình, chính sách áp dụng.
- **Consent:** người dùng hoặc admin chấp thuận những quyền ứng dụng yêu cầu theo chính sách của tenant.
- **Authorization:** API và hệ thống SaaS quyết định người gọi được thực hiện nghiệp vụ nào trên dữ liệu nào.
- **Provisioning:** bổ sung hoặc cập nhật người dùng, nhóm, role và tenant trong hệ thống SaaS.

### Onboarding

Quy trình cần ghi nhận tenant ID, thời điểm admin chấp thuận, quyền đã cấp, hồ sơ khách hàng, người quản trị đầu tiên và trạng thái kích hoạt. Khi khách hàng chỉ chấp thuận một phần quyền, ứng dụng phải xử lý rõ tính năng nào chưa hoạt động.

### Vận hành

Tenant khách hàng có thể áp dụng MFA, Conditional Access, giới hạn user consent hoặc chặn ứng dụng chưa được phê duyệt. Nhà cung cấp SaaS nên hỗ trợ thông báo lỗi và hướng dẫn admin kiểm tra **Enterprise applications**, quyền API, user assignment và sign-in logs. Việc một ứng dụng đăng ký là multi-tenant không thể vượt qua chính sách bảo mật của tenant khách hàng.

### Offboarding

Khi khách hàng ngừng dùng sản phẩm, backend phải vô hiệu hóa tenant trong danh sách khách hàng, chấm dứt quyền truy cập và thực hiện quy trình xử lý/xóa dữ liệu theo hợp đồng và chính sách lưu giữ. Admin khách hàng có thể thu hồi consent hoặc xóa enterprise application của SaaS tại tenant của họ. Tuy nhiên, **xóa service principal ở tenant khách hàng không tự xóa dữ liệu mà SaaS đang lưu**.

## 12. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Người dùng tenant B không đăng nhập được | App registration vẫn là single-tenant hoặc dùng authority của tenant A | Kiểm tra Supported account types và authority |
| Tài khoản Microsoft cá nhân không đăng nhập được | Ứng dụng chỉ hỗ trợ organizational accounts | Xác định có thật sự cần MSA và chọn loại tài khoản phù hợp |
| Xuất hiện lỗi cần admin approval | Quyền yêu cầu cần admin consent hoặc chính sách tenant giới hạn user consent | Giảm quyền không cần thiết, chuẩn bị luồng admin consent |
| Đăng nhập thành công nhưng API báo 401 | Dùng ID token gọi API, audience sai, token hết hạn hoặc issuer không hợp lệ | Kiểm tra access token dành cho API, audience và issuer validation |
| API trả 403 sau khi đăng nhập | Tenant chưa được onboard, thiếu scope/role hoặc không có quyền trên đối tượng | Kiểm tra tenant active, consent, app role và quyền nghiệp vụ |
| Người dùng thuộc tenant lạ vẫn đến được màn hình sau login | Ứng dụng chỉ kiểm tra token hợp lệ, chưa kiểm soát danh sách khách hàng | Bổ sung tenant onboarding/allowlist và chặn các tenant chưa kích hoạt |
| Truy cập nhầm dữ liệu khách hàng khác | Backend tin tenantId trong request hoặc không lọc dữ liệu theo tenant | Ràng buộc customer context với token hợp lệ; kiểm tra từng truy vấn |
| Đổi tenant nhưng session vẫn hiển thị dữ liệu cũ | Session/cache không gắn tenant hoặc chưa làm mới dữ liệu | Ràng buộc cache/session theo tenant, xóa dữ liệu cũ khi đổi ngữ cảnh |
| Guest không thấy ứng dụng | Chưa được mời/gán quyền hoặc chính sách B2B/assignment chặn | Kiểm tra đối tượng guest, user assignment và chính sách truy cập |

Khi phân tích sự cố, nên ghi lại correlation ID/request ID, tenant ID, thời gian đăng nhập và mã lỗi. Không ghi access token hoặc refresh token thô vào log; nếu cần xem claim để gỡ lỗi, sử dụng công cụ an toàn và tránh chia sẻ token đang còn hiệu lực.

## 13. Bài thực hành thiết kế: cổng nội bộ và SaaS nhiều tổ chức

Bài tập gồm hai phương án. Có thể hoàn thành phần thiết kế mà không cần subscription trả phí hoặc quyền admin ở nhiều tenant. Nếu muốn thao tác trên Portal, sử dụng môi trường thử nghiệm được cấp quyền.

### Phần A: cổng nội bộ một tenant

Yêu cầu: doanh nghiệp **Alpha** có một tenant Entra ID, 200 nhân viên, một cổng quản lý dự án. Chỉ người dùng được gán quyền mới có thể xem dữ liệu; một số chuyên gia đối tác cần cộng tác trong 2 tháng.

Thiết kế:

1. Chọn app registration **single-tenant** tại tenant Alpha.
2. Chỉ định authority bằng tenant ID của Alpha.
3. Tạo app roles **Projects.Reader** và **Projects.Manager**.
4. Chỉ gán người dùng/nhóm có quyền sử dụng; mời chuyên gia bên ngoài bằng Entra B2B guest nếu chính sách cho phép.
5. API xác thực token, issuer và audience; kiểm tra role và quyền trên dự án.
6. Xác định cách thu hồi tài khoản guest và quyền khi kết thúc 2 tháng.

Sản phẩm đầu ra là sơ đồ thành phần, bảng nhóm quyền và các điều kiện từ chối truy cập.

### Phần B: SaaS phục vụ Alpha và Beta

Yêu cầu: nhà cung cấp **Vendor** có ứng dụng quản lý hợp đồng. Hai khách hàng Alpha và Beta có tenant độc lập, mỗi bên có administrator riêng; dữ liệu không được lộ giữa hai bên.

Thiết kế:

1. Đăng ký ứng dụng **Accounts in any organizational directory** trong home tenant Vendor.
2. Sử dụng endpoint **organizations** cho đăng nhập đa tổ chức hoặc tenant-specific authority sau khi xác định khách hàng.
3. Tạo quy trình admin consent và onboarding cho mỗi tenant.
4. Lưu ánh xạ **validated tid → customer ID**, trạng thái active và quyền quản trị khách hàng.
5. API kiểm tra chữ ký, issuer, audience, thời gian token, tenant active, scopes/app roles.
6. Mọi truy vấn dữ liệu bắt buộc lọc customer ID từ context phía server.
7. Tạo quy trình offboarding: thu hồi quyền, khóa truy cập, xử lý dữ liệu và ghi nhận audit.

### Ma trận kiểm thử tối thiểu

| Tình huống | Kỳ vọng |
|---|---|
| Nhân viên Alpha đăng nhập cổng single-tenant và có role phù hợp | Đăng nhập và chỉ thao tác trong quyền được gán |
| Người dùng tenant Beta không được mời vào Alpha thử cổng single-tenant | Không được truy cập |
| Guest được mời vào Alpha nhưng chưa gán quyền ứng dụng | Không được truy cập phần nội dung yêu cầu assignment |
| Nhân viên Alpha đăng nhập SaaS khi Alpha đã onboard | Được truy cập dữ liệu Alpha theo quyền |
| Nhân viên Beta đăng nhập SaaS khi Beta đã onboard | Được truy cập dữ liệu Beta theo quyền |
| Token hợp lệ từ tenant chưa onboard | Bị từ chối truy cập dịch vụ |
| Token có audience dành cho API khác | Bị API từ chối |
| Người dùng Alpha thử đọc contract ID của Beta | Bị từ chối, không lộ dữ liệu Beta |
| Ứng dụng nền chưa có application role/consent cần thiết | Không gọi API được theo quyền yêu cầu |
| Beta bị offboard nhưng còn session cũ | Backend từ chối các yêu cầu mới theo trạng thái tenant |

### Câu hỏi tự kiểm tra

1. Vì sao nhiều phòng ban dùng chung một Entra tenant không nhất thiết cần ứng dụng multi-tenant?
2. Application object và service principal khác nhau như thế nào khi SaaS được nhiều khách hàng chấp thuận?
3. Khi nào dùng B2B guest thay cho app registration multi-tenant?
4. Endpoint **organizations** khác với authority chứa tenant ID ở điểm nào?
5. Vì sao đăng nhập thành công và có token hợp lệ vẫn chưa đủ để truy cập dữ liệu SaaS?
6. API cần kiểm tra gì trong **iss**, **aud**, **tid**, **scp** và **roles**?
7. Vì sao **email** không phải khóa tin cậy để cô lập dữ liệu nhiều tenant?
8. Offboarding khách hàng cần làm gì ngoài việc thu hồi consent?

## 14. Checklist trước khi đưa ứng dụng vào production

- [ ] Supported account types đúng với đối tượng khách hàng và chính sách doanh nghiệp.
- [ ] Đăng ký chính xác redirect URI; dùng authorization code flow/PKCE khi phù hợp.
- [ ] Client secret/certificate được bảo vệ phía server; ưu tiên credential an toàn và vòng đời rõ ràng.
- [ ] Client và API sử dụng đúng token dành cho audience; API xác thực chữ ký, issuer, thời hạn và claims.
- [ ] Với multi-tenant, chỉ tenant đã onboard và active được truy cập.
- [ ] Scope, app roles, admin consent và user assignment tuân theo quyền tối thiểu.
- [ ] Dữ liệu, cache, log và tác vụ nền được cách ly theo customer/tenant.
- [ ] Có kiểm thử truy cập chéo tenant, session cũ, guest và tenant bị thu hồi quyền.
- [ ] Có quy trình kiểm soát onboarding, offboarding, audit và xử lý sự cố đăng nhập.
- [ ] MFA/Conditional Access và quy định bảo mật của từng tenant được xem xét trong thiết kế.

## 15. Tài liệu tham khảo

- [Microsoft identity platform application model](https://learn.microsoft.com/entra/identity-platform/application-model) — app registration, application object và service principal.
- [Supported account types](https://learn.microsoft.com/entra/identity-platform/supported-accounts-validation) — xác định loại tài khoản được ứng dụng hỗ trợ.
- [OpenID Connect on the Microsoft identity platform](https://learn.microsoft.com/entra/identity-platform/v2-protocols-oidc) — endpoint và luồng đăng nhập.
- [Microsoft identity platform OAuth 2.0 authorization code flow](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow) — authorization code và PKCE.
- [Permissions and consent](https://learn.microsoft.com/entra/identity-platform/permissions-consent-overview) — delegated/application permissions và mô hình chấp thuận.
- [Microsoft Entra B2B collaboration](https://learn.microsoft.com/entra/external-id/what-is-b2b) — cộng tác với người dùng ngoài tổ chức.
- [Microsoft identity platform access tokens](https://learn.microsoft.com/entra/identity-platform/access-tokens) — token, claims, audience và xác thực API.

Thiết kế nên bắt đầu từ **đối tượng người dùng và ranh giới dữ liệu**, sau đó mới chọn loại app registration. Single-tenant phù hợp khi ứng dụng hoạt động trong phạm vi một tenant (có thể gồm guest B2B); multi-tenant phù hợp khi nhiều tenant cần xác thực độc lập. Ở cả hai mô hình, Entra ID chịu trách nhiệm danh tính và phát hành token, còn ứng dụng vẫn chịu trách nhiệm kiểm soát quyền nghiệp vụ và dữ liệu.
