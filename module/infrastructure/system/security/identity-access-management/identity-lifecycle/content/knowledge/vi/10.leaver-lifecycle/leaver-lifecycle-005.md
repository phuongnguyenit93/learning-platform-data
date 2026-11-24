# Thu hồi token trong Leaver lifecycle

## 1. Vì sao Leaver phải thu hồi token?

Trong **Identity and Access Management (IAM)**, *thu hồi token* (token revocation) là quá trình khiến một token không còn được chấp nhận theo chính sách, có thể diễn ra trước thời điểm hết hạn tự nhiên. Đây là bước quan trọng của **Leaver lifecycle**: khi nhân viên, nhà thầu hoặc đối tác rời tổ chức, IAM phải chặn những đường truy cập còn hiệu lực, bao gồm credential đã được phát hành từ trước.

Ví dụ, người dùng đã đăng nhập vào ứng dụng báo cáo qua **Single Sign-On (SSO)** và nhận access token có hạn 30 phút. Sau 5 phút, bộ phận nhân sự xác nhận người đó nghỉ việc và hệ thống **Identity Provider (IdP)** khóa tài khoản. Nếu API báo cáo chỉ kiểm tra chữ ký và thời hạn của token, access token cũ vẫn có thể được chấp nhận cho tới khi hết hạn. **Khóa account không mặc nhiên thu hồi mọi token và session đã được cấp.**

Một quy trình đầy đủ cần trả lời:

1. Danh tính này có những **token, phiên, khóa API hoặc credential nào**, ở những hệ thống nào?
2. **Ai phát hành** token và **ai thực thi** quyết định chấp nhận token?
3. Cơ chế thu hồi của từng loại token có tác dụng **ngay lập tức, có độ trễ hay chỉ khi hết hạn**?
4. Quyết định thu hồi có căn cứ từ **nguồn HR, người bảo trợ hoặc chính sách quyền** nào?
5. Sau khi gửi lệnh thu hồi, **bằng chứng nào** cho thấy API và ứng dụng đích thực sự đã chặn truy cập?

Đích đến của bước này là giảm **quyền truy cập tồn dư** (*residual access*) trong toàn bộ mô hình **Joiner–Mover–Leaver (JML)**, không chỉ thay đổi trạng thái một bản ghi tài khoản.

## 2. Phân biệt các đối tượng cần thu hồi

Trong IAM, danh tính, tài khoản, phiên đăng nhập, token và quyền truy cập có vòng đời khác nhau:

| Đối tượng | Mục đích | Hành động khi Leaver |
| --- | --- | --- |
| **Identity** | Bản ghi danh tính số của chủ thể | Chuyển trạng thái theo quan hệ làm việc còn hiệu lực |
| **Account** | Tài khoản tại IdP hoặc ứng dụng | Vô hiệu hóa hoặc thu hồi theo chính sách |
| **SSO session** | Phiên đăng nhập tại IdP | Kết thúc hoặc chặn khả năng tái xác thực |
| **Application session** | Phiên riêng của ứng dụng, thường gắn cookie | Kết thúc tại ứng dụng đích |
| **Access token** | Cho phép gọi API/tài nguyên trong phạm vi và thời hạn | Làm resource server từ chối token không còn hợp lệ |
| **Refresh token** | Được client dùng để xin access token mới | Thu hồi refresh token hoặc grant liên quan |
| **ID token (OIDC)** | Chứng minh sự kiện xác thực cho client | Quản lý phiên ứng dụng, không dùng như access token gọi API |
| **Entitlement** | Vai trò, nhóm, quyền trên tài nguyên | Thu hồi hoặc tính lại quyền hiệu lực |
| **PAT, API key, SSH key** | Credential đặc thù sản phẩm hoặc tích hợp | Thu hồi theo cơ chế riêng của hệ thống cấp phát |

Một số tình huống dễ nhầm:

- Thu hồi **refresh token** có thể ngăn cấp access token mới, nhưng access token đã cấp có thể vẫn được chấp nhận.
- Kết thúc phiên IdP có thể chặn đăng nhập mới nhưng không tự kết thúc tất cả session của từng ứng dụng.
- Xóa nhóm trong IdP không tự thu hồi token đang mang claim quyền cũ nếu resource server không đánh giá lại.
- SCIM báo tài khoản đã bị vô hiệu hóa không đủ để chứng minh API key, PAT hoặc token ứng dụng cục bộ cũng đã mất hiệu lực.
- Thu hồi một token không bảo đảm những token khác của cùng người trên thiết bị và client khác đã bị thu hồi.

## 3. Những loại token quan trọng trong Leaver

### 3.1. Access token

Access token thường được cấp bởi **authorization server** cho một client dùng khi yêu cầu tài nguyên từ **resource server**. Token có thể mang hoặc gắn với audience, scope, thời hạn và quyền. Hai dạng thường gặp:

- **Opaque token:** chuỗi không tự chứa toàn bộ thông tin để API tự kết luận; resource server có thể cần hỏi authorization server hoặc kho trạng thái.
- **Self-contained token, thường là JWT:** API có thể kiểm tra chữ ký, issuer, audience, thời hạn và claim mà không cần gọi máy chủ phát hành cho mỗi request.

JWT không phải là loại token “không thể thu hồi”. Vấn đề nằm ở **cách kiểm tra token tại resource server**. Nếu API chỉ kiểm tra chữ ký hợp lệ và token chưa hết hạn thì việc thay đổi trạng thái người dùng tại IdP không làm token cũ tự mất hiệu lực.

### 3.2. Refresh token

Refresh token cho phép client lấy access token mới mà không cần yêu cầu người dùng đăng nhập lại mỗi lần. Vì có thể kéo dài thời gian truy cập, refresh token hoặc grant liên quan thường phải được thu hồi khi Leaver. Hệ thống có thể hỗ trợ **refresh token rotation**, quản lý token family và phát hiện tái sử dụng; phạm vi thu hồi tùy nhà cung cấp và cách cấu hình.

**Không mặc định** rằng khi revoke một refresh token thì tất cả access token và phiên ứng dụng liên quan đều bị hủy ngay. Hành vi đó cần được kiểm chứng tại nền tảng sử dụng.

### 3.3. ID token

Trong **OpenID Connect (OIDC)**, ID token thể hiện kết quả xác thực cho client trong một ngữ cảnh đăng nhập. **ID token không phải token được thiết kế để thay access token khi gọi API**. Khi Leaver, cần xử lý logout và session của client, đồng thời bảo đảm API không chấp nhận ID token sai mục đích.

### 3.4. Session cookie, SAML và token cục bộ

Một ứng dụng có thể tạo session cookie riêng sau khi xác thực bằng OIDC hoặc **SAML**. Khi IdP khóa người dùng, session ứng dụng vẫn có thể còn hạn nếu không có cơ chế liên kết trạng thái hoặc logout. Các ứng dụng SaaS và công cụ DevOps còn có thể cấp **personal access token (PAT)**, CLI token hay API key độc lập. Những credential này cần kiểm kê và thu hồi riêng ở hệ thống đích.

## 4. Mô hình trách nhiệm của các hệ thống

~~~mermaid
flowchart TD
    HR["HRIS / nguồn bảo trợ<br/>Sự kiện Leaver có thẩm quyền"] --> IAM["IAM governance<br/>Đối soát danh tính và phạm vi quyền"]
    IAM --> IDP["IdP / Authorization Server<br/>Vô hiệu account, thu hồi grant/session"]
    IAM --> APP["Ứng dụng đích<br/>Kết thúc session, PAT, token cục bộ"]
    IAM --> PROV["Provisioning / SCIM / API<br/>Thu hồi tài khoản, nhóm, role"]
    IDP --> RS["Resource Server / API<br/>Quyết định chấp nhận access token"]
    APP --> RS
    PROV --> VERIFY["Đối soát trạng thái thực tế"]
    RS --> VERIFY
    VERIFY --> AUD["Bằng chứng / audit / ngoại lệ"]
~~~

**HRIS** xác định trạng thái quan hệ lao động và mốc hiệu lực; **IAM** ra quyết định theo chính sách và điều phối; **IdP/authorization server** quản lý account và những token, grant, session thuộc quyền của nó; **resource server** là nơi thực thi việc từ chối request mang token; **ứng dụng** có thể giữ session và credential riêng.

**SCIM (System for Cross-domain Identity Management)** thường giúp đồng bộ vòng đời user và group, nhưng **không phải giao thức thu hồi access token hay phiên SSO**. Vì vậy, phản hồi SCIM thành công chỉ chứng minh một phần quy trình, không thay thế bằng chứng từ resource server và ứng dụng đích.

## 5. Nguồn phát sinh Leaver và mốc thu hồi

Một sự kiện Leaver có thể đến từ HRIS, hệ thống quản trị nhà thầu hoặc quy trình khẩn cấp được ủy quyền. Cần xác minh nguồn tin cậy, đối chiếu đúng **person, worker, employment, identity và account**, đồng thời lưu phiên bản hoặc mã sự kiện để tránh xử lý sai dữ liệu cũ.

| Trường hợp | Ý nghĩa với token |
| --- | --- |
| Nghỉ việc theo lịch | Tính mốc cắt quyền từ ngày hiệu lực và múi giờ được phê duyệt |
| Chấm dứt khẩn cấp | Thu hồi theo quyết định khẩn cấp được ủy quyền, không chờ batch thông thường |
| Hết phân công dự án | Thu hồi quyền/token gắn phạm vi dự án đã hết hạn nếu cần, không nhất thiết khóa toàn bộ identity |
| Chuyển vai trò hoặc organization | Đánh giá lại token mang role, claim, scope cũ để tránh quyền tồn dư |
| Kết thúc một trong nhiều hợp đồng | Tính lại quyền từ mọi quan hệ còn hợp lệ; thu hồi đúng phần đã hết căn cứ |
| Gia hạn hoặc hủy quyết định nghỉ việc | Cập nhật lịch theo bản ghi mới nhất; kiểm tra lại các quyền được phép duy trì |

**End date dạng ngày lịch** cần quy tắc rõ ràng. Chẳng hạn nếu ngày 30/11/2026 là **ngày cuối cùng còn hiệu lực** theo múi giờ Việt Nam, mốc cắt quyền minh họa là **01/12/2026 00:00 +07:00**, tức **30/11/2026 17:00 UTC**. Nếu HR dùng ngữ nghĩa khác, mốc cắt cũng khác. Không tự đổi ngày lịch thành 00:00 UTC khi chưa xác định quy tắc.

Ngoài mốc nghiệp vụ, cần phân biệt **thời điểm IAM nhận sự kiện**, **thời điểm gửi lệnh thu hồi** và **thời điểm API thực sự từ chối truy cập**. Một sự kiện HR đã qua hạn không cho phép ghi lùi thời gian thực thi kỹ thuật.

## 6. Kiểm kê token và các đường truy cập

Trước khi đóng ca Leaver, IAM cần liệt kê những hệ thống mà người rời tổ chức có tài khoản, grant, session và credential liên quan.

| Nguồn cần kiểm tra | Đường truy cập có thể còn | Biện pháp phù hợp |
| --- | --- | --- |
| IdP | Refresh token, grant, SSO session | Chặn đăng nhập, thu hồi grant và phiên được hỗ trợ |
| Ứng dụng OIDC/OAuth | Application session, access token, refresh token | Revoke token và logout theo khả năng ứng dụng |
| Ứng dụng SAML | Phiên tại Service Provider, cookie | Kết thúc phiên SP, phối hợp logout nếu hỗ trợ |
| SaaS qua SCIM | Account, group, role, PAT nội bộ | Deactivate và xử lý riêng token/ACL ứng dụng |
| Cloud hoặc DevOps | CLI token, PAT, session đặc quyền, SSH key | Thu hồi principal, khóa, credential hoặc quyền đặc biệt |
| API nội bộ | JWT cũ, cache quyền, access token tự phát hành | Kiểm tra trạng thái thu hồi ở gateway/resource server |
| Thiết bị, ứng dụng di động | Token và phiên lưu trên thiết bị | Thu hồi khi online, xử lý giới hạn TTL/offline |
| Service/workload identity | Client credential, API key, certificate | Đánh giá owner, secret và grant đúng phạm vi workload |

**Không coi việc đã đăng xuất web là bằng chứng PAT hoặc CLI token không thể gọi API.** Chúng có thể hoạt động độc lập. Tương tự, việc một danh tính không còn trong nhóm IdP không chứng minh mọi ACL trực tiếp và tài khoản cục bộ đã bị xóa.

### Thu hồi theo đúng scope

Trong tổ chức đa tenant hoặc người có nhiều hợp đồng, một người có thể rời organization A nhưng vẫn có quan hệ được duyệt với B. IAM phải phân biệt grant thuộc A và B, xác định account nào là dùng chung, đồng thời tránh vô hiệu nhầm quyền hợp lệ của B. Ngược lại, không được để token phạm vi A tiếp tục hoạt động chỉ vì người đó vẫn làm ở B.

## 7. Cơ chế thu hồi OAuth 2.0

### 7.1. Token revocation theo RFC 7009

OAuth 2.0 mô tả cơ chế client yêu cầu **authorization server** thu hồi token. Tùy triển khai, có thể thu hồi refresh token, access token và ảnh hưởng grant/token liên quan. Client phải thực hiện xác thực client theo yêu cầu của authorization server.

Ví dụ minh họa yêu cầu tới một endpoint giả định:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.invalid
Content-Type: application/x-www-form-urlencoded

token=TOKEN_PLACEHOLDER&token_type_hint=refresh_token
~~~

Đây là hình thức minh họa, không có token hoặc client secret thật, và chưa bao gồm phần xác thực client cần thiết. **token_type_hint** là gợi ý loại token; khả năng hỗ trợ và phạm vi thu hồi phụ thuộc nhà cung cấp.

**Phản hồi thành công của endpoint không chứng minh mọi token/phiên đã hết hiệu lực.** Giao thức có thể trả phản hồi thành công cho cả token vốn đã không hợp lệ. Phải xác minh phạm vi revoke và trạng thái ở nơi sử dụng.

### 7.2. Token introspection theo RFC 7662

Resource server có thể hỏi authorization server về trạng thái token thông qua **introspection**, nếu hệ sinh thái hỗ trợ. Sau khi authorization server đánh dấu token bị thu hồi, API có thể từ chối token dựa trên trạng thái trả về.

Tuy nhiên:

- Introspection có thể dùng **cache**, gây độ trễ thấy trạng thái mới.
- Resource server vẫn phải kiểm tra audience, scope và quyền truy cập thực tế.
- Hệ thống cần quy định hành vi khi endpoint introspection không sẵn sàng.
- Một kết quả token còn active không có nghĩa request được phép truy cập mọi tài nguyên.

## 8. JWT xác thực offline và phương án chặn trước hạn

Với JWT có chữ ký hợp lệ và chưa hết hạn, API xác minh offline có thể tiếp tục chấp nhận dù IdP đã vô hiệu tài khoản. Một số phương án:

1. **TTL access token ngắn:** thu hẹp khoảng thời gian token cũ còn được chấp nhận khi không có kiểm tra chủ động.
2. **Denylist theo mã token hoặc định danh jti:** resource server/gateway kiểm tra token cụ thể có bị thu hồi hay không.
3. **Security epoch hoặc phiên bản quyền:** API so sánh thời điểm/phần version của token với mốc chặn hoặc quyền hiện hành.
4. **Tra cứu trạng thái phiên/grant hoặc policy:** xác minh qua cơ chế có trạng thái đủ mới tại mỗi request hoặc tại điểm kiểm soát tập trung.
5. **Gateway xác thực tập trung:** tập trung logic thu hồi, với điều kiện mọi đường truy cập cần bảo vệ đi qua gateway.

Ví dụ, access token có TTL 15 phút, được cấp sát trước mốc nghỉ việc. Nếu không có cơ chế chặn trước hạn, token có thể được chấp nhận gần **15 phút sau mốc Leaver** (còn phụ thuộc độ lệch đồng hồ và chính sách kiểm tra). TTL ngắn **giới hạn** rủi ro chứ không thay thế khả năng revoke tức thời.

Việc xoay **khóa ký JWT dùng chung** chỉ để thu hồi token của một người có thể vô hiệu hóa rất nhiều token hợp lệ. Đây không phải phương án mặc định cho từng ca Leaver; xoay khóa cần quy trình riêng và đánh giá phạm vi tác động.

Token ràng buộc với client hoặc khóa, chẳng hạn **mTLS** hoặc **DPoP** khi được hỗ trợ, có thể giảm nguy cơ phát lại token bị đánh cắp. Tuy nhiên, cơ chế ràng buộc này **không thay thế việc chặn quyền** khi quan hệ lao động đã kết thúc.

## 9. Kết thúc SSO session và phiên ứng dụng

Khi người dùng đăng nhập SSO, có thể tồn tại đồng thời **session IdP**, session của nhiều ứng dụng web, phiên mobile và token gọi API. Các hoạt động này cần được xử lý theo khả năng sản phẩm:

| Hành động | Kết quả thường đạt | Còn cần kiểm tra |
| --- | --- | --- |
| Vô hiệu account IdP | Ngăn xác thực mới tại IdP | Access token và phiên ứng dụng hiện hữu |
| Revoke refresh token/grant | Chặn khả năng làm mới token trong phạm vi grant | Access token đã cấp |
| Logout IdP | Kết thúc session SSO tại IdP | Session riêng của từng ứng dụng |
| Logout ứng dụng | Kết thúc phiên tại ứng dụng đó | Phiên ở IdP và ứng dụng khác |
| Back-channel logout / API session | Kết thúc phiên ở hệ thống hỗ trợ | Hệ thống không hỗ trợ và token API độc lập |
| SCIM deactivation | Thay trạng thái user ở hệ thống hỗ trợ | PAT, cookie, ACL và token không tự thu hồi |

Với **OIDC**, cơ chế như RP-initiated logout hoặc back-channel logout có thể hỗ trợ đồng bộ phiên nếu triển khai đúng. Với **SAML**, cần kiểm tra khả năng Single Logout và vòng đời phiên của **Service Provider (SP)**. Không giả định mọi ứng dụng tự kết thúc phiên khi IdP thay đổi trạng thái.

### Thời điểm thu hồi và tình huống race condition

Một yêu cầu làm mới token có thể chạy **đồng thời** với thao tác revoke. Thiết kế cần kiểm tra trạng thái grant/identity một cách nhất quán để không phát hành token mới sau mốc mất quyền. Nếu token đã kịp phát hành, resource server vẫn cần cơ chế từ chối quyền không còn hợp lệ.

## 10. Phối hợp RBAC, ABAC và provisioning

Thu hồi token phải đi cùng việc đánh giá lại **quyền thực tế**:

- **RBAC (Role-Based Access Control):** thu hồi role hoặc group không còn căn cứ công việc; kiểm tra role kế thừa và role ứng dụng cục bộ.
- **ABAC (Attribute-Based Access Control):** cập nhật các thuộc tính có thẩm quyền như trạng thái làm việc, assignment, organization và thời hạn; đảm bảo policy engine/API đánh giá thông tin mới.
- **Provisioning/deprovisioning:** cập nhật IdP, SCIM hoặc API để vô hiệu hóa account và entitlement ở hệ thống đích.
- **Resource server:** thực thi quyền trên từng request; không dùng một claim đã cũ làm căn cứ duy nhất nếu yêu cầu thu hồi phải có hiệu lực trước lúc token hết hạn.

Ví dụ, token có claim role=ProjectReader khi được phát hành cho Dự án Atlas. Sau khi người dùng đổi dự án, claim không tự đổi thành Nova. Nếu resource server chỉ dựa vào claim ấy, việc xóa role Atlas tại IdP có thể chưa đủ để chặn truy cập. IAM cần bảo đảm API **đánh giá lại entitlement hoặc từ chối token cũ** theo chính sách.

### Thu hồi tài khoản dịch vụ khác với người rời việc

Người phụ trách một workload rời tổ chức không đồng nghĩa workload đó không còn cần thiết. Cần chuyển trách nhiệm sở hữu, rà soát client credential/secret và thu hồi mọi PAT hoặc khóa cá nhân đã được workload dùng. Nếu workload cũng ngừng hoạt động, áp dụng deprovisioning cho **chính workload identity** và token liên quan.

## 11. Quy trình thu hồi token có thể xác minh

~~~mermaid
flowchart TD
    A["HRIS / sponsor xác nhận Leaver"] --> B["Kiểm tra nguồn, identity, ngày hiệu lực"]
    B --> C["Kiểm kê tài khoản, client, grant, token, session và PAT"]
    C --> D["Tính quyền còn hợp lệ và quyền phải thu hồi"]
    D --> E["Chặn xác thực mới và phát hành token mới"]
    E --> F["Revoke refresh token/grant, kết thúc phiên"]
    F --> G["Chặn access token cũ tại resource server"]
    G --> H["Thu hồi account, role, ACL, token cục bộ"]
    H --> I["Đối soát quyền và kiểm tra hệ thống đích"]
    I --> J{"Đủ bằng chứng thu hồi?"}
    J -->|"Có"| K["Đóng hạng mục, lưu audit"]
    J -->|"Không"| L["PARTIAL / FAILED, retry và xử lý ngoại lệ"]
    L --> I
~~~

Các hành động độc lập **có thể thực hiện song song**, đặc biệt khi phải chặn truy cập khẩn cấp. Sơ đồ thể hiện các phụ thuộc logic và cổng xác minh, không yêu cầu chờ hệ thống này kết thúc rồi mới được xử lý hệ thống khác.

**Bước 1 – Xác nhận sự kiện.** Lấy nguồn có thẩm quyền, liên kết chính xác person/worker/employment/identity và mốc mất quyền. Kiểm tra bản ghi mới nhất để không dùng sự kiện đã bị gia hạn hoặc hủy.

**Bước 2 – Xác định phạm vi.** Tìm mọi tài khoản, grant, client, session, PAT, khóa và quyền phát sinh từ quan hệ đã kết thúc; kiểm tra những quan hệ công việc vẫn còn hiệu lực.

**Bước 3 – Ngăn cấp mới.** Vô hiệu khả năng xác thực và cấp token/grant mới theo chính sách, xử lý refresh token và các session liên quan.

**Bước 4 – Thu hồi quyền hiện hữu.** Kích hoạt cơ chế từ chối access token còn hạn ở API, chấm dứt phiên ứng dụng, thu hồi PAT/API key và xóa ACL, role, group không còn căn cứ.

**Bước 5 – Đọc lại kết quả.** Kiểm tra account, grant, session và quyền hiệu lực tại các điểm thực thi; xử lý các mục chưa đạt bằng retry idempotent, cảnh báo và phân công owner.

**Bước 6 – Đóng khi có chứng cứ.** Chỉ đánh dấu hoàn tất khi mọi hệ thống **bắt buộc** đạt tiêu chí hoặc ngoại lệ còn mở đã được báo rõ, không trình bày kết quả một phần thành thành công toàn bộ.

## 12. Mã giả cho luồng Leaver

Ví dụ dưới đây chỉ minh họa trách nhiệm kỹ thuật, không phải API thực tế của một nhà cung cấp:

~~~text
handleLeaver(event):
    requireTrustedAuthoritativeSource(event)
    requireApprovedOrAuthorizedEmergencyAction(event)
    identity = correlateIdentity(event.workerId, event.employmentId)
    rejectStaleEventVersion(event, identity)

    cutoff = resolveEffectiveCutoff(event)
    remainingAccess = evaluateOtherValidEmploymentAndAssignments(identity, cutoff)
    impacted = findAccessNoLongerAuthorized(identity, remainingAccess)
    case = upsertRevocationCaseIdempotently(event.eventId, event.version)

    blockNewAuthenticationAndTokenGrants(impacted)
    revokeRefreshTokensAndGrants(impacted)
    terminateSupportedIdPSessionsAndAppSessions(impacted)
    enforceAccessTokenRevocationAtResourceServers(impacted)
    revokeLocalPATsKeysAndCredentials(impacted)
    deactivateAccountsAndRemoveObsoleteEntitlements(impacted)

    for target in impacted:
        actual = readBackTargetState(target)
        result = verifyEffectiveAccessIsDenied(target, actual, cutoff)
        case.recordEvidence(target, result)
        if not result.passed:
            case.openException(target, responsibleOwner(target))

    return COMPLETED if case.allRequiredTargetsVerified() else PARTIAL
~~~

Một hệ thống triển khai thật còn cần quyền gọi API, retry, timeout, rate limit, kiểm soát cập nhật cạnh tranh, lưu trạng thái công việc bất đồng bộ và xác nhận đã đọc lại ở từng đích. **Idempotency** giúp xử lý sự kiện trùng mà không gây tác động lặp ngoài ý muốn; **versioning** giúp ngăn sự kiện HR cũ ghi đè quyết định mới.

## 13. Thời gian thu hồi thực tế và giới hạn cache

Ngay cả sau khi một grant đã được thu hồi, độ trễ vẫn có thể xuất hiện:

- **TTL access token** và độ lệch đồng hồ được cho phép khi xác minh.
- **Cache introspection** hoặc cache quyền trên API.
- **Thời gian lan truyền trạng thái revoke** tới nhiều gateway, node hoặc region.
- **Session cookie** tại ứng dụng không đồng bộ ngay với IdP.
- **Credential ngoại tuyến** hoặc thiết bị chưa kết nối lại.
- **Thời gian retry** khi đích bị lỗi hoặc chậm.

Cần lưu tách biệt:

~~~text
businessCutoffAt       = 2026-12-01T00:00:00+07:00
revokeRequestedAt      = 2026-12-01T00:00:02+07:00
grantRevokedAt         = 2026-12-01T00:00:04+07:00
accessDeniedVerifiedAt = 2026-12-01T00:00:11+07:00
~~~

Trong ví dụ, API được xác minh đã từ chối sau mốc cắt **11 giây**. Kết quả này **chỉ chứng minh phạm vi API đã kiểm tra**, không tự chứng minh mọi SaaS hoặc API khác đều bị chặn.

Với những API nhạy cảm, cần quy định cách xử lý khi hệ thống introspection hoặc nguồn trạng thái thu hồi không sẵn sàng. Việc **fail-open** có thể tiếp tục cho truy cập dù không xác minh được quyền; **fail-closed** hạn chế rủi ro nhưng ảnh hưởng tính sẵn sàng. Chính sách dự phòng phải được chọn theo mức rủi ro và thiết kế trước.

## 14. Tài khoản dịch vụ, robot và credential người dùng bị dùng sai mục đích

Trong môi trường DevOps, một nhân viên có thể tạo **PAT cá nhân** cho pipeline CI/CD, lưu API key trong secret store hoặc dùng token CLI chạy tác vụ tự động. Nếu nhân viên nghỉ việc, những credential đó phải được rà soát:

| Tình huống | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| PAT cá nhân dùng cho pipeline | Pipeline vẫn hoạt động dưới danh tính đã nghỉ | Di chuyển sang workload identity có owner, thu hồi PAT cũ |
| API key biết bởi người nghỉ việc | Người cũ có thể giữ bản sao key | Xoay/thu hồi key, kiểm tra client và giới hạn phạm vi |
| Workload identity không còn owner | Không ai chịu trách nhiệm quyền và secret | Chỉ định owner/đội vận hành mới và rà soát quyền |
| OAuth client có quyền quá rộng | Token máy ảnh hưởng nhiều tài nguyên | Giảm scope/role, áp dụng phân tách theo môi trường/tenant |
| Tài khoản bot không còn workload | Credential tồn dư dù dịch vụ ngừng chạy | Vô hiệu workload identity, token và secret |

Không nên xóa ngay bot sản xuất vẫn có nhiệm vụ hợp lệ chỉ vì người owner nghỉ việc. Quy trình cần **chuyển quyền sở hữu và thu hồi đặc quyền cá nhân**, đồng thời đánh giá credential máy riêng. Với workload đã kết thúc, phải thu hồi đúng token và quyền của workload đó.

## 15. Bằng chứng kiểm toán và tiêu chí hoàn tất

Một log “revoke request sent” chỉ chứng minh đã gửi yêu cầu, chưa chứng minh thành công. Hồ sơ Leaver nên lưu:

| Dữ liệu kiểm toán | Mục đích |
| --- | --- |
| Mã sự kiện HR và nguồn có thẩm quyền | Truy ra căn cứ bắt đầu thu hồi |
| Identity/account/client/tenant tham chiếu | Xác định đúng phạm vi mà không ghi secret |
| Thời điểm nghiệp vụ và thời điểm xử lý | Tính độ trễ |
| Phạm vi grant/session/token/PAT phải thu hồi | Không bỏ sót đường truy cập |
| Chính sách và phiên bản, người phê duyệt khi cần | Giải thích quyết định |
| Kết quả từng target, thời điểm đọc lại và bằng chứng | Đánh giá quyền hiệu lực thực tế |
| Ngoại lệ, retry, owner, thời hạn khắc phục | Không che các đường truy cập chưa chặn |

Ví dụ JSON minh họa:

~~~json
{
  "caseId": "leaver-2026-091",
  "sourceEventId": "hr-event-091",
  "identityId": "iam-id-482",
  "businessCutoffAt": "2026-12-01T00:00:00+07:00",
  "policyVersion": "leaver-revoke-v3",
  "targets": [
    {
      "name": "enterprise-idp",
      "control": "revoke_grants_and_sessions",
      "status": "verified",
      "verifiedAt": "2026-12-01T00:00:09+07:00"
    },
    {
      "name": "analytics-api",
      "control": "deny_revoked_access_token",
      "status": "verified",
      "verifiedAt": "2026-12-01T00:00:11+07:00"
    },
    {
      "name": "external-saas",
      "control": "revoke_local_pat",
      "status": "pending",
      "ownerTeam": "saas-operations"
    }
  ],
  "overallStatus": "PARTIAL"
}
~~~

**PARTIAL** có nghĩa chưa được xác nhận hoàn tất vì SaaS còn PAT chưa có bằng chứng thu hồi. Nếu hệ thống thực tế có nhiều client và token, cần trạng thái riêng cho những hạng mục bắt buộc, không dùng một cờ chung che lỗi.

**Không ghi nguyên access token, refresh token, cookie, client secret, private key hoặc mã khôi phục** trong log hay tài liệu. Nếu cần liên kết sự kiện, dùng mã token hoặc giá trị tham chiếu/định danh băm phù hợp chính sách, đồng thời bảo vệ chính log khỏi truy cập không có thẩm quyền.

## 16. Kiểm thử và giám sát quyền truy cập tồn dư

### Kiểm thử theo từng lớp

| Kiểm tra | Kết quả mong đợi | Điều chưa thể kết luận |
| --- | --- | --- |
| Đăng nhập mới qua IdP | Bị từ chối theo trạng thái Leaver | Token cũ đã bị chặn ở API |
| Yêu cầu làm mới bằng grant đã revoke | Không thể xin access token mới | Access token cũ đã mất hiệu lực |
| Yêu cầu API bằng token đã revoke trên tài nguyên kiểm thử | API từ chối theo chính sách | Mọi API khác cũng đã từ chối |
| Đọc lại session tại ứng dụng | Session không còn hợp lệ | Phiên của client/thiết bị khác đã mất hiệu lực |
| Đọc lại SCIM/account/role | Trạng thái đích khớp mục tiêu | PAT và khóa riêng của ứng dụng cũng đã thu hồi |
| Kiểm kê credential máy/cá nhân | Không còn credential do người Leaver sở hữu trái chính sách | Tất cả secret chưa quản trị đã được phát hiện |

Các phép thử cần được thực hiện bởi hệ thống hoặc người được ủy quyền, ưu tiên **token kiểm thử có phạm vi hẹp và tài nguyên thử nghiệm**. Không đưa bearer token sản xuất vào lịch sử shell, ticket, báo cáo hoặc tài liệu học tập.

### Chỉ số vận hành

- **Time to effective revocation:** độ trễ từ mốc mất quyền đến lúc hệ thống đích xác nhận từ chối truy cập.
- **Unrevoked grants:** số grant/refresh token vẫn có thể cấp credential mới sau Leaver.
- **Active sessions after cutoff:** số phiên còn sử dụng được ngoài giới hạn chính sách.
- **Revocation propagation lag:** độ trễ đồng bộ denylist, introspection, epoch hoặc cache.
- **Local token/PAT orphaned:** token không còn chủ thể hoặc quan hệ làm việc hợp lệ.
- **Targets pending/failed:** những hệ thống chưa xử lý hoặc chưa có bằng chứng.
- **Use of revoked token:** tín hiệu token bị dùng lại, có thể do retry, cache hoặc hành vi bất thường cần xem xét.

Không có một TTL hay SLA chung phù hợp tất cả tổ chức. Ngưỡng cần phản ánh độ nhạy tài nguyên, các ràng buộc vận hành và rủi ro của từng loại danh tính.

## 17. Tình huống thực hành

**Bối cảnh:** Bình đăng nhập bằng SSO vào hệ thống báo cáo và một SaaS có SCIM. Quyết định chấm dứt hợp đồng có hiệu lực lúc **15:00 ngày 23/11/2026** theo giờ Việt Nam. IAM nhận sự kiện đúng giờ, IdP đã khóa tài khoản và SCIM đã đặt account SaaS về trạng thái inactive.

Tại **15:03**, một JWT cũ của Bình vẫn gọi được API báo cáo vì token có hạn đến **15:14**; API chỉ kiểm tra chữ ký và exp. Ngoài ra, Bình có một **PAT** được SaaS phát hành độc lập.

**Vấn đề:** khóa IdP chặn đăng nhập mới nhưng chưa đủ với JWT xác minh offline; SCIM deactivation có thể không tự thu hồi PAT. Vì thế, trạng thái Leaver vẫn phải là **chưa xác minh hoàn tất**.

**Hướng xử lý:**

1. Kiểm tra sự kiện HR, danh tính và phạm vi quyền cần chấm dứt.
2. Ngăn cấp token mới và revoke refresh token/grant liên quan.
3. Áp dụng cơ chế chặn JWT cũ tại resource server: denylist, security epoch hoặc policy recheck nếu nền tảng hỗ trợ. Nếu chỉ có TTL, ghi rõ **giới hạn cửa sổ truy cập tồn dư** và biện pháp xử lý rủi ro.
4. Kết thúc phiên IdP và ứng dụng; thu hồi PAT tại SaaS qua API/quy trình riêng.
5. Đọc lại account, group, role và quyền hiệu lực tại từng hệ thống; dùng kiểm thử được ủy quyền để xác minh API từ chối.
6. Ghi thời điểm đã yêu cầu, thời điểm từng hệ thống hoàn tất và thời điểm xác minh; giao owner xử lý mục còn mở.

**Câu hỏi tự kiểm tra:**

1. **Revoke refresh token có luôn làm JWT access token cũ mất hiệu lực không?** Không; tùy cơ chế của authorization server và resource server.
2. **RFC 7009 trả kết quả thành công là đủ bằng chứng chưa?** Chưa; cần xác định phạm vi thu hồi và kiểm tra nơi sử dụng.
3. **SCIM inactive có bảo đảm PAT riêng của SaaS đã bị hủy không?** Không mặc nhiên; cần kiểm tra cách SaaS quản lý PAT.
4. **Nếu Bình vẫn còn hợp đồng hợp lệ với organization khác?** Cần tính lại quyền, thu hồi phần hết căn cứ và giữ phần thực sự được phép.
5. **Vì sao TTL ngắn chưa bảo đảm revoke tức thì?** Token cũ vẫn có thể được chấp nhận đến khi hết hạn nếu resource server không kiểm tra trạng thái mới.

## 18. Checklist triển khai

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Sự kiện Leaver đúng người, đúng thời điểm? | Nguồn có thẩm quyền, phiên bản mới nhất và ID ổn định |
| Đã kiểm kê token/grant/session/PAT? | Tất cả hệ thống, client, thiết bị và tenant liên quan |
| Đã chặn phát hành credential mới? | IdP, grant/refresh token và phiên phù hợp |
| Access token đã phát hành bị chặn thế nào? | Introspection, denylist, security epoch, policy recheck hoặc TTL đã được chấp nhận |
| Đã xử lý SSO và session ứng dụng? | Kiểm tra từng ứng dụng, RP/SP và thiết bị liên quan |
| Đã xử lý token ứng dụng cục bộ? | PAT, API key, SSH key, CLI token ngoài IdP |
| Quyền thực tế đã bị thu hồi? | Role, group, ACL, quyền chia sẻ, kiểm soát RBAC/ABAC |
| Có quan hệ làm việc khác còn hiệu lực? | Thu hồi đúng scope, không vô hiệu nhầm quyền hợp lệ |
| Workload/service account có phụ thuộc người Leaver? | Chuyển owner, xoay secret khi cần, thu hồi credential cá nhân |
| Có sự kiện đến trễ, trùng hoặc gia hạn? | Idempotency, versioning, cập nhật lịch đúng mốc |
| Có target chưa xác minh? | Trạng thái PARTIAL/FAILED, owner, retry và cảnh báo |
| Có bằng chứng kiểm toán an toàn? | Mốc HR, quyết định IAM, kết quả đích, không lộ token |

## 19. Tổng kết

**Thu hồi token trong Leaver lifecycle** là quá trình chặn việc sử dụng credential đã phát hành, ngăn cấp credential mới, kết thúc phiên và loại bỏ quyền truy cập thực tế khi một quan hệ công việc không còn hợp lệ. **HRIS/nguồn bảo trợ** cung cấp căn cứ; **IAM** điều phối; **IdP/authorization server** quản lý account, grant và phiên; **SSO/SCIM** hỗ trợ các phần việc tương ứng; còn **resource server và ứng dụng đích** phải thực sự từ chối token hoặc quyền đã hết căn cứ.

Trong mô hình **Joiner–Mover–Leaver**, việc phân biệt access token, refresh token, ID token, session và PAT; hiểu giới hạn của JWT xác minh offline, cache, TTL; cùng với quản lý tài khoản dịch vụ, quyền theo từng organization và kiểm toán có thể kiểm chứng là điều kiện thiết yếu để giảm **quyền truy cập tồn dư**. Chỉ nên coi hạng mục hoàn tất khi mọi điểm kiểm soát bắt buộc đã được xác minh hoặc ngoại lệ còn mở đã được ghi rõ phạm vi, người chịu trách nhiệm và thời hạn xử lý.
