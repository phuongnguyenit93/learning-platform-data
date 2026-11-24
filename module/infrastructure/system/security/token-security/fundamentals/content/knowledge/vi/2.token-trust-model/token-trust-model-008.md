# Confused deputy trong hệ thống token

## 1. Mục tiêu bài học

Trong chương **Mô hình tin cậy** của **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một vấn đề quan trọng không chỉ là token có hợp lệ hay không, mà còn là **dịch vụ đang thực hiện hành động bằng quyền của ai, cho ai và trên tài nguyên nào**. Bài học này tập trung vào lỗ hổng **confused deputy** (đại diện có đặc quyền bị đánh lừa) trong các hệ thống sử dụng access token, JWT, opaque token, OAuth 2.0 và OpenID Connect (OIDC).

Sau khi học, bạn có thể:

- Nhận diện một dịch vụ có đặc quyền đang bị bên ít quyền hơn khiến nó thực hiện hành động ngoài quyền của bên yêu cầu.
- Phân biệt **caller**, **subject**, **client**, **actor/deputy**, **issuer** và **resource server** khi một request đi qua nhiều dịch vụ.
- Hiểu tại sao JWT có chữ ký đúng, token còn hạn và scope hợp lệ vẫn có thể xuất hiện trong một vụ confused deputy.
- Xác định vai trò của **audience**, **scope**, **tenant**, quyền sở hữu tài nguyên và token được ủy quyền khi thiết kế luồng gọi API.
- Lựa chọn các cách phòng tránh như kiểm tra quyền theo đối tượng, giảm quyền dịch vụ, cấp token cho đúng đích, token exchange/on-behalf-of, quản lý ranh giới tin cậy và chống token bị đánh cắp hoặc phát lại.

## 2. Confused deputy là gì?

**Deputy** là một thành phần có khả năng hoặc đặc quyền để thay mặt thành phần khác thực hiện công việc. **Confused deputy** xảy ra khi bên yêu cầu có ít quyền hơn điều khiển deputy sử dụng đặc quyền của chính deputy để làm một việc mà bên yêu cầu **không được phép** làm.

Ví dụ, một người dùng chỉ được đọc hóa đơn của công ty A nhưng lại yêu cầu dịch vụ báo cáo xuất hóa đơn thuộc công ty B. Dịch vụ báo cáo vốn có một tài khoản dịch vụ được cấp quyền đọc hóa đơn của mọi công ty để xử lý tác vụ nội bộ. Nếu nó dùng quyền rộng đó để đáp ứng yêu cầu mà không kiểm tra người dùng có được đọc hóa đơn của B hay không, dịch vụ báo cáo đã trở thành **confused deputy**.

Lỗ hổng nằm ở việc **trộn lẫn hai nguồn thẩm quyền**:

1. **Quyền của người yêu cầu:** người dùng/client chỉ được làm một số việc trên một số tài nguyên.
2. **Quyền của deputy:** dịch vụ có quyền rộng hơn để hoàn thành nhiệm vụ vận hành.

Khi deputy quyết định hành động chỉ dựa trên khả năng kỹ thuật của chính nó, thay vì giới hạn theo quyền của bên đã yêu cầu, đặc quyền có thể bị lợi dụng.

### 2.1. Những thành phần trong một cuộc tấn công

| Thành phần | Vai trò trong ví dụ |
|---|---|
| **Attacker / caller** | Người dùng hợp lệ hoặc bên gửi request có quyền hạn chế, kiểm soát một phần dữ liệu đầu vào |
| **Deputy** | Dịch vụ báo cáo có khả năng gọi API hóa đơn với token của tài khoản dịch vụ |
| **Issuer / Authorization Server** | Hệ thống phát hành access token cho người dùng và dịch vụ |
| **Resource server đích** | API hóa đơn, nơi tài nguyên nhạy cảm được lưu trữ |
| **Authority** | Quyền mà token dịch vụ hoặc cơ chế định danh nội bộ cấp cho deputy |
| **Target resource** | Hóa đơn thuộc tenant/tổ chức khác mà caller không có quyền xem |

Không nhất thiết có token giả mạo hoặc mật khẩu bị đánh cắp. Người tấn công **có thể sở hữu một access token hoàn toàn hợp lệ** và chỉ cần tìm được API khiến deputy sử dụng quyền vượt quá quyền của họ.

### 2.2. Phân biệt với lỗi liên quan

| Khái niệm | Điểm cốt lõi | Quan hệ với confused deputy |
|---|---|---|
| **Broken Object Level Authorization (BOLA/IDOR)** | API không kiểm tra người gọi có quyền trên đối tượng được chỉ định bằng ID hay không | Một confused deputy có thể bắt đầu từ thiếu kiểm tra ownership/tenant, nhưng không phải mọi BOLA đều có deputy riêng |
| **Privilege escalation** | Bên ít quyền đạt được khả năng thực hiện thao tác có quyền cao hơn | Confused deputy là một cơ chế dẫn đến leo thang quyền qua thành phần trung gian |
| **Token substitution / audience confusion** | Token phát hành cho mục đích hoặc dịch vụ này được chấp nhận ở ngữ cảnh khác | Có thể tạo ra hoặc tăng mức độ nghiêm trọng của confused deputy khi ranh giới token không được kiểm tra |
| **SSRF** | Thành phần máy chủ gửi request đến địa chỉ do kẻ tấn công tác động | Có thể bị khai thác để biến máy chủ thành deputy truy cập mạng/tài nguyên nội bộ, nhưng cơ chế kiểm soát địa chỉ khác với kiểm tra quyền nghiệp vụ |
| **Replay token** | Kẻ tấn công dùng lại token hoặc bằng chứng xác thực đã lấy được | Là kiểu lạm dụng khác; sender-constrained token giảm replay nhưng chưa tự giải quyết confused deputy |

Điểm nhận biết đặc trưng: **tài nguyên đích thấy quyền của deputy là hợp lệ**, trong khi **nguồn gốc yêu cầu và phạm vi ủy quyền thực sự của caller đã bị đánh mất hoặc bị hiểu sai**.

## 3. Tình huống thực tế: report-service bị lợi dụng

Giả sử hệ thống SaaS đa khách hàng có:

- **Authorization Server:** https://login.example.com.
- **Frontend client:** report-web.
- **Report Service:** https://reports.example.com, nhận yêu cầu tạo báo cáo.
- **Billing API:** https://billing.example.com, quản lý hóa đơn của các tenant.
- **Alice:** người dùng thuộc **tenant-A**, chỉ được xem hóa đơn của tenant-A.
- **Invoice B-900:** hóa đơn thuộc **tenant-B**.

Trong một thiết kế thiếu kiểm soát, Report Service có token ứng dụng được cấp quyền **invoices:read:all** để phục vụ nghiệp vụ nội bộ. Alice đăng nhập hợp lệ, nhận access token cho Report Service và gửi yêu cầu tạo báo cáo với invoiceId của tenant-B.

~~~mermaid
sequenceDiagram
    actor A as Alice (tenant-A)
    participant C as Client: report-web
    participant R as Report Service (deputy)
    participant I as Issuer / Authorization Server
    participant B as Billing API (resource server)
    A->>C: Chọn invoiceId=B-900
    C->>R: Yêu cầu báo cáo + user access token
    Note over R: Kiểm tra token còn hạn và scope reports:create
    Note over R: BỎ QUA kiểm tra tenant/ownership của hóa đơn
    R->>I: Lấy service access token
    I-->>R: Token của report-service, scope invoices:read:all
    R->>B: GET /invoices/B-900 bằng service token
    Note over B: Token hợp lệ, có scope đọc mọi hóa đơn
    B-->>R: Dữ liệu hóa đơn tenant-B
    R-->>C: Báo cáo chứa dữ liệu tenant-B
    C-->>A: Xem dữ liệu không được phép
~~~

**Điểm gây lỗi:** Report Service nhận chỉ dẫn từ Alice nhưng lại sử dụng quyền đọc toàn bộ hóa đơn của chính Report Service mà **không ràng buộc quyền đó với Alice và tenant-A**.

### 3.1. Token nào cũng có thể hợp lệ

Access token Alice gửi tới Report Service có thể mang claims minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": "https://reports.example.com",
  "client_id": "report-web",
  "scope": "reports:create",
  "tenant_id": "tenant-A"
}
~~~

Token dịch vụ mà Report Service sử dụng khi gọi Billing API:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "svc-report",
  "aud": "https://billing.example.com",
  "client_id": "report-service",
  "scope": "invoices:read:all"
}
~~~

Đây chỉ là **payload JWT minh họa, chưa có chữ ký và không phải token để dùng thực tế**. Claim **tenant_id** là claim tùy biến cần được issuer định nghĩa và bảo đảm; việc có **sub** cho service account phụ thuộc profile token và chính sách của issuer.

Xét riêng từng token:

1. Token của Alice có thể hợp lệ cho Report Service, đúng issuer, audience, scope và thời hạn.
2. Token của report-service có thể hợp lệ cho Billing API, đúng issuer, audience, scope và thời hạn.
3. Billing API có thể cho phép đọc B-900 vì service token có quyền rộng đã được cấp trước đó.
4. **Yêu cầu của Alice vẫn không hợp lệ về mặt phân quyền nghiệp vụ** vì Alice không được đọc B-900.

Vậy đây là lỗi **ủy quyền qua các ranh giới tin cậy**, không nhất thiết là lỗi thuật toán ký JWT hoặc xác thực token.

### 3.2. Xác định đúng điểm cần kiểm soát

| Vị trí | Điều kiện phải được giữ |
|---|---|
| Frontend/client | Chỉ gửi token đến API đúng đối tượng nhận; không quyết định quyền dựa trên dữ liệu tự khai báo |
| Report Service khi nhận request | Xác minh token Alice và quyền **reports:create**; xác định tenant/principal từ dữ liệu tin cậy |
| Report Service trước khi dùng quyền rộng | Chứng minh Alice được yêu cầu báo cáo trên hóa đơn B-900, hoặc chuyển ngữ cảnh ủy quyền đã xác minh sang Billing qua cơ chế hỗ trợ |
| Authorization Server khi cấp token downstream | Chỉ cấp token theo client, grant, resource/audience, scope và policy được phép; không tự động giữ mọi quyền từ token đầu vào |
| Billing API | Xác minh token cho chính nó và policy truy cập hóa đơn, đặc biệt nếu nhận token đại diện người dùng |

Chỉ kiểm tra ở API Gateway rằng Alice đã đăng nhập là chưa đủ: quyền đọc hóa đơn nào vẫn phải được kiểm tra đúng nơi có ngữ cảnh để quyết định.

## 4. Gốc rễ: nhầm lẫn danh tính và quyền ở đâu?

### 4.1. Caller khác deputy

**Caller** là bên khởi phát hành động; **deputy** là thành phần thực hiện hành động. Trong hệ thống phân tán, một dịch vụ có thể đồng thời là **resource server** khi nhận request từ frontend và là **OAuth client** khi gọi dịch vụ khác.

~~~text
Alice ──(access token của Alice)──> Report Service
                                     |
                                     | (service access token của Report Service)
                                     v
                                 Billing API
~~~

Ở bước gọi thứ hai, Billing có thể nhìn thấy **chỉ danh tính dịch vụ**, không có bằng chứng nào về việc Alice là người khởi phát yêu cầu. Nếu Report Service gửi thêm header **X-User-Id: alice-123**, Billing cũng không được xem đó là bằng chứng ủy quyền trừ khi header được truyền qua một kênh có xác thực và được bảo vệ bằng hợp đồng tin cậy rõ ràng. Header tùy ý do client bên ngoài gửi lên càng không đáng tin.

### 4.2. Có quyền kỹ thuật chưa có nghĩa được phép sử dụng quyền đó cho mọi người

Giả sử scope **invoices:read:all** cho phép một tác vụ nội bộ đồng bộ dữ liệu. Scope đó **không tự động ủy quyền** cho Alice truy cập mọi hóa đơn qua tác vụ đồng bộ.

Một request hợp lệ phải thỏa mãn **ít nhất hai lớp quyết định**:

~~~text
ALLOW(request) =
    token_caller_hop_hien_tai_hop_le
    AND hanh_dong_duoc_cho_phep
    AND caller_co_quyen_tren_tai_nguyen_cu_the
    AND deputy_duoc_phep_dung_quyen_nay_cho_muc_dich_do
~~~

Đây là biểu diễn chính sách ở mức khái niệm. Triển khai cụ thể có thể còn xét tenant, chính sách tổ chức, ngữ cảnh phiên, device risk, mục đích xử lý dữ liệu và giới hạn theo thời gian.

### 4.3. Subject, client và actor không luôn đồng nhất

| Khái niệm | Ví dụ | Cần nhớ |
|---|---|---|
| **Subject (sub)** | alice-123 | Người dùng/principal mà token mô tả theo quy tắc của issuer |
| **Client (client_id)** | report-web | Ứng dụng đã xin hoặc được cấp token |
| **Deputy / actor** | report-service | Dịch vụ thực hiện công việc downstream |
| **Issuer (iss)** | https://login.example.com | Bên phát hành được resource server tin cậy |
| **Audience (aud)** | https://billing.example.com | Đích được cấp để nhận và sử dụng token |
| **Resource owner** | Chủ thể có quyền đối với dữ liệu hóa đơn theo mô hình nghiệp vụ | Không thể suy quyền sở hữu dữ liệu chỉ từ việc token có sub |

Một token với **sub=alice-123** không có nghĩa mọi hành động mà Report Service thực hiện đều được Alice cho phép. Ngược lại, một token có **sub=svc-report** không có nghĩa request phát sinh từ tác vụ nội bộ đáng tin cậy; request có thể bắt nguồn từ hành động do người dùng bên ngoài điều khiển.

### 4.4. Đứt mạch ủy quyền (authorization context)

Ngữ cảnh quan trọng có thể mất ở bước chuyển tiếp:

- **Ai khởi phát?** Định danh principal và issuer đã xác minh.
- **Ứng dụng nào?** client_id và chính sách được cấp cho client.
- **Thay mặt ai?** Người dùng, dịch vụ, hoặc chuỗi đại diện có kiểm soát.
- **Trên tài nguyên nào?** Invoice ID, owner, tenant và resource server đích.
- **Được làm gì?** Hành động, scope và quyền nghiệp vụ cụ thể.
- **Vì mục đích nào?** Tác vụ được phép sử dụng quyền dịch vụ.

Nếu deputy giữ lại mỗi **invoiceId** nhưng bỏ mất thông tin người yêu cầu, API downstream chỉ còn thấy token dịch vụ có quyền cao. Thiết kế an toàn phải **giữ hoặc tái xác lập ngữ cảnh ủy quyền đáng tin cậy trước khi dùng quyền**.

## 5. Vì sao kiểm tra JWT đúng vẫn chưa đủ?

Một resource server có thể kiểm tra kỹ thuật đầy đủ và vẫn tham gia vào luồng confused deputy. Kiểm tra JWT giải quyết **nguồn gốc và tính hợp lệ của token**; phân quyền nghiệp vụ giải quyết **request này có được phép làm việc này hay không**.

### 5.1. Kiểm tra ở từng hop

Khi Report Service nhận user access token, nó cần kiểm tra:

1. **iss** nằm trong tập issuer được cấu hình tin cậy.
2. Với JWT, chữ ký hợp lệ theo thuật toán và khóa được phép; với opaque token, kết quả introspection hoặc nguồn xác minh tương đương là tin cậy.
3. **aud** chỉ Report Service; token dùng đúng loại, không lấy ID token thay access token.
4. **exp**, **nbf** (nếu có), trạng thái token và các giới hạn thời gian phù hợp.
5. Scope/permission cho phép **tạo báo cáo**.
6. Quyền đối với **hóa đơn được yêu cầu** và tenant, xét theo dữ liệu nghiệp vụ tin cậy.

Khi Billing API nhận downstream access token, nó kiểm tra tương tự, nhưng **audience phải chỉ Billing API** và policy phải phù hợp loại token/service principal. Nếu token đại diện người dùng thì phải áp dụng giới hạn người dùng; nếu token dịch vụ có quyền đọc rộng thì phải có chính sách chặt chẽ về ai được gọi endpoint, cho mục đích nào và bằng chứng ủy quyền ở đâu.

### 5.2. Một số claim dễ bị hiểu sai

| Claim / dữ liệu | Ý nghĩa có thể sử dụng | Điều không được tự suy ra |
|---|---|---|
| **iss** | Xác định issuer sau khi token được xác minh | Issuer tin cậy nghĩa là mọi request đều được phép |
| **sub** | Định danh subject trong phạm vi issuer | Subject sở hữu tất cả resource ID có trong request |
| **aud** | Dịch vụ/token recipient dự kiến | Audience đúng nghĩa là mọi hành động trên dịch vụ đều hợp lệ |
| **scope** | Phạm vi quyền được issuer cấp và API hiểu | Scope đọc dữ liệu tương đương quyền đọc mọi đối tượng của mọi tenant |
| **client_id** | Client được cấp token trong profile hoặc phản hồi tương ứng | Client là chính người dùng hoặc được tự do hành động thay người dùng |
| **azp** | Authorized party trong những ngữ cảnh OIDC hỗ trợ | Có thể dùng chung quy tắc với client_id trên mọi access token |
| **act** | Actor/delegation context trong token exchange khi profile hỗ trợ | Chuỗi actor tự động chứng minh mọi sự ủy quyền là hợp lệ |
| **tenant_id** | Tenant theo hợp đồng claim của issuer, sau khi xác minh | Tenant do client nhập trong query/header là tenant đáng tin |
| **jti** | Định danh token khi issuer cung cấp | Có jti thì token tự động chống replay hoặc đã được thu hồi đúng cách |

**Không tự lấy JWKS URL từ JWT chưa xác minh để tải khóa tin cậy**, không cho client tùy chọn issuer hoặc audience ngoài tập cho phép. Nếu có nhiều issuer/tenant, phải phân biệt các subject theo issuer và ngữ cảnh tenant phù hợp; cùng một chuỗi sub ở hai issuer có thể là hai thực thể khác nhau.

### 5.3. JWT, opaque, access, refresh và ID token giữ vai trò khác nhau

- **JWT** là định dạng token có claims; chữ ký bảo vệ tính toàn vẹn và nguồn phát hành khi được xác minh đúng. Nó không tự thể hiện quyền trên bản ghi nghiệp vụ.
- **Opaque token** không cần được client/API giải mã; API dùng introspection hoặc cơ chế do hệ thống quy định. Phản hồi token **active=true** chưa có nghĩa mọi thao tác đều được cho phép.
- **Access token** là credential client dùng với resource server đúng audience, scope và chính sách.
- **ID token** trong OIDC cung cấp thông tin kết quả xác thực cho **client**; không dùng thay access token khi gọi API.
- **Refresh token** dùng tại token endpoint để xin access token mới, không gửi tới Billing API. Nếu bị đánh cắp có thể làm tăng thời gian kẻ tấn công duy trì quyền truy cập; bảo vệ/rotation/thu hồi cần thiết nhưng không tự sửa lỗi deputy.

Trong mọi trường hợp, token phải được xem là **đầu vào của quyết định truy cập**, không phải câu trả lời hoàn chỉnh về quyền nghiệp vụ.

## 6. Các kiểu confused deputy trong kiến trúc token

### 6.1. Dịch vụ dùng service token quá rộng

**Mẫu lỗi:** API công khai nhận resource ID do caller chọn, sau đó dùng client credentials của chính mình để đọc/ghi resource có quyền rộng. Caller có thể khiến dịch vụ đọc dữ liệu người khác hoặc sửa quyền không được phép.

**Giải pháp:** kiểm tra quyền caller trên resource trước khi thực hiện hành động có đặc quyền; tách nhiệm vụ nội bộ với API nhận input của bên ngoài; giảm scope và phạm vi dữ liệu của service account; dùng token đại diện người dùng khi hệ thống hỗ trợ.

### 6.2. Chuyển tiếp access token sang API khác mà không xét audience

**Mẫu lỗi:** token được cấp cho Report Service được chuyển thẳng tới Billing API, và Billing API chỉ kiểm tra chữ ký/hạn mà không kiểm tra **aud**. Token vốn được cấp cho dịch vụ A trở thành credential được chấp nhận ở dịch vụ B.

**Giải pháp:** mỗi resource server kiểm tra token được phát hành cho chính mình; cấp token mới có audience/resource phù hợp cho bước downstream thông qua luồng Authorization Server cho phép. Việc đổi token phải chịu kiểm soát quyền, không chỉ thay tên audience.

Lưu ý: **từ chối sai audience là yêu cầu bảo mật cơ bản**, nhưng riêng điều đó chưa ngăn được Report Service dùng **service token hợp lệ, quyền quá rộng** như tình huống mục 3.

### 6.3. Nhầm quyền của ứng dụng với quyền của người dùng

**Mẫu lỗi:** service token được cấp bởi client credentials dùng để xử lý request người dùng; ứng dụng coi quyền dịch vụ như quyền của user mà không có bước kiểm tra ràng buộc. Ngược lại, API nhìn thấy một subject mà mặc nhiên coi đó là người dùng.

**Giải pháp:** phân biệt **application permission** và **delegated/user permission**; ghi rõ loại principal và các grant/profile được API hỗ trợ; dùng token/luồng cấp quyền đáp ứng đúng mô hình được ủy quyền.

### 6.4. Nhầm tenant hoặc resource owner

**Mẫu lỗi:** caller thuộc tenant-A gửi body:

~~~json
{
  "tenantId": "tenant-B",
  "invoiceId": "B-900"
}
~~~

Deputy tin tenantId do caller nhập rồi dùng token quyền rộng đọc B-900. Đây là vấn đề dù token caller có thêm claim tenant_id: việc đối chiếu claim với dữ liệu resource vẫn phải thực hiện theo policy.

**Giải pháp:** tenant của principal lấy từ danh tính đã xác minh; tenant/owner của resource lấy từ nguồn nghiệp vụ tin cậy; kiểm tra quan hệ trước thao tác nhạy cảm. Với người dùng có quyền truy cập nhiều tenant, phải xác minh **tenant đang được chọn và quyền đối với tenant đó**, thay vì đơn giản so bằng một chuỗi duy nhất.

### 6.5. Tin các header định danh hoặc kết quả kiểm tra không được bảo vệ

**Mẫu lỗi:** API nội bộ nhận **X-User-Id**, **X-Tenant-Id**, **X-Role** từ request bên ngoài hoặc từ một proxy chưa được xác thực; deputy dùng các giá trị đó để bỏ qua kiểm tra quyền.

**Giải pháp:** chặn/ghi đè header nhạy cảm tại ranh giới vào hệ thống, xác thực kết nối giữa các dịch vụ và chỉ nhận identity context theo giao thức nội bộ có integrity, provenance và policy rõ ràng. Quan hệ nội bộ hoặc cùng mạng không khiến dữ liệu tự động đáng tin.

### 6.6. Tác vụ bất đồng bộ và hàng đợi đánh mất người yêu cầu

**Mẫu lỗi:** frontend tạo job xuất dữ liệu; queue chỉ chứa **jobId** và **resourceId**. Worker vài giờ sau chạy bằng service account có quyền đọc toàn bộ dữ liệu, không biết ai đặt job hoặc quyền đã thay đổi.

**Giải pháp:** lưu **ngữ cảnh ủy quyền đã xác minh, được bảo vệ** gắn với job; cân nhắc kiểm tra lại quyền ở thời điểm xử lý theo yêu cầu nghiệp vụ; ràng buộc tenant, target, action và người yêu cầu; không lưu bearer access token dài hạn trong payload job một cách tùy tiện. Phân biệt job do người dùng yêu cầu và job hệ thống được lên lịch từ nội bộ.

### 6.7. Callback hoặc tích hợp bên thứ ba lạm dụng quyền hệ thống

**Mẫu lỗi:** endpoint webhook hoặc integration action được phép kích hoạt backend có nhiều quyền. Bên ngoài điều khiển tham số tài nguyên nhưng backend bỏ qua phạm vi mà webhook/client được ủy quyền.

**Giải pháp:** xác minh danh tính nguồn gọi, chữ ký webhook khi áp dụng, quyền của client/tích hợp trên đối tượng cụ thể; gán khả năng truy cập theo từng integration/tenant và giới hạn những thao tác có thể ủy quyền. Chữ ký webhook hợp lệ chỉ chứng minh nguồn thông điệp theo cơ chế đã thiết kế, không mặc nhiên cho phép thao tác mọi dữ liệu.

## 7. Thiết kế phòng tránh theo từng ranh giới tin cậy

### 7.1. Cách A: giữ quyền của caller và kiểm tra quyền trên tài nguyên

Nếu Report Service có đủ dữ liệu đáng tin cậy để xác định invoice thuộc ai, nó có thể kiểm tra trước khi gọi Billing. Ví dụ pseudocode:

~~~text
function createInvoiceReport(verifiedCallerToken, invoiceId):
    require verifiedCallerToken.audience contains "https://reports.example.com"
    require verifiedCallerToken.scopes contains "reports:create"

    caller = Principal(
        issuer = verifiedCallerToken.issuer,
        subject = verifiedCallerToken.subject,
        tenant = trustedTenantFor(verifiedCallerToken)
    )

    invoiceAccess = permissionService.authorize(
        principal = caller,
        action = "invoice:read",
        resource = invoiceId
    )
    require invoiceAccess.allowed

    return billingClient.fetchInvoiceForAuthorizedReport(
        invoiceId = invoiceId,
        verifiedContext = invoiceAccess.context
    )
~~~

Mọi giá trị **verifiedCallerToken** trong ví dụ phải đến từ tầng đã xác thực token. Hàm **permissionService.authorize** phải dùng dữ liệu quyền/ownership đáng tin cậy; việc truyền **verifiedContext** sang Billing chỉ an toàn nếu có cơ chế bảo vệ và Billing được cấu hình tin cậy cơ chế đó.

Điểm cần suy nghĩ: nếu Report Service **không có cách xác minh quyền trên invoice** mà phải gọi Billing trước, việc tải toàn bộ invoice của tenant-B rồi mới lọc là không phù hợp. Nên thiết kế endpoint Billing có thể kiểm tra và trả **chỉ dữ liệu caller được phép đọc** hoặc cung cấp API kiểm tra quyền không để lộ dữ liệu nhạy cảm.

### 7.2. Cách B: dùng delegated token / on-behalf-of khi được hỗ trợ

Authorization Server có thể hỗ trợ **OAuth 2.0 Token Exchange (RFC 8693)** hoặc cơ chế **on-behalf-of** có hợp đồng rõ ràng. Thay vì luôn dùng service token toàn quyền, Report Service xin một access token cho **Billing API** với quyền giới hạn theo chủ thể, actor, resource và policy.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant R as Report Service
    participant AS as Authorization Server
    participant B as Billing API
    U->>R: Yêu cầu báo cáo + access token cho Report Service
    R->>R: Xác minh caller, scope và request
    R->>AS: Xin token downstream với subject_token, actor/client, resource và scope phù hợp
    AS->>AS: Kiểm tra chính sách ủy quyền và giới hạn quyền cấp
    AS-->>R: Access token dành cho Billing API, thể hiện ngữ cảnh được phép
    R->>B: GET /invoices/{id} + access token downstream
    B->>B: Xác minh token, delegation, tenant và quyền trên invoice
    B-->>R: Dữ liệu được phép hoặc 403
    R-->>U: Báo cáo hoặc thông báo không đủ quyền
~~~

Ví dụ payload **minh họa** của downstream access token có actor context:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": "https://billing.example.com",
  "client_id": "report-service",
  "scope": "invoices:read",
  "tenant_id": "tenant-A",
  "act": {
    "sub": "svc-report"
  }
}
~~~

Trong ví dụ, **sub** chỉ principal người dùng và **act** cho biết dịch vụ đang hành động ở vai trò actor. Claim **act** được định nghĩa trong RFC 8693 cho ngữ cảnh delegation, nhưng **không phải mọi issuer/token exchange đều phát hành cấu trúc này**. Tên client_id, tenant_id, cách biểu diễn actor và việc Billing diễn giải chúng phải theo profile/hợp đồng cụ thể. Không được tự tin một trường act do caller nhét vào payload chưa xác thực.

**Token exchange không tự đảm bảo giảm quyền**. Authorization Server phải kiểm tra token đầu vào, client được quyền trao đổi, đích nhận token, phạm vi truy cập và chính sách delegation. Billing vẫn phải kiểm tra quyền đối với invoice cụ thể; chỉ việc cấp **invoices:read** chưa nói được Alice có quyền đọc B-900 hay không.

### 7.3. Cách C: phải dùng service token thì cô lập quyền rõ ràng

Không phải luồng nào cũng có người dùng để delegation; ví dụ batch đồng bộ được kích hoạt theo lịch có thể dùng client credentials chính đáng. Khi deputy buộc phải dùng service token:

- Tách endpoint/luồng **job nội bộ** khỏi endpoint cho **caller bên ngoài**.
- Dùng danh tính dịch vụ và scope giới hạn theo tác vụ, không cấp mặc định quyền toàn hệ thống.
- Nếu hệ thống hỗ trợ, ràng buộc quyền dịch vụ theo tenant, loại resource, operation hoặc workload.
- Buộc deputy kiểm tra đầy đủ request và nguồn khởi phát **trước khi sử dụng quyền cao**.
- Buộc resource server đích giới hạn những thao tác/đối tượng mà client dịch vụ được gọi; không chỉ dựa vào tên dịch vụ đáng tin.
- Ghi lại mối liên hệ từ yêu cầu gốc đến hành động downstream để điều tra và kiểm toán.

Một token quyền cao có thể vẫn cần trong một số tác vụ quản trị, nhưng **khả năng dùng token phải được đặt sau chính sách về mục đích và nguồn yêu cầu**, không trở thành đường đi mặc định cho mọi request.

### 7.4. Cách D: cấp token đúng đích và giới hạn quyền

Trong OAuth 2.0, **resource indicators (RFC 8707)** cho phép client yêu cầu token cho resource cụ thể khi Authorization Server hỗ trợ. Trong token exchange, client cũng có thể yêu cầu audience/resource và scope cho hệ thống đích. Mục tiêu:

~~~text
Request đến Report Service:
    token.aud = https://reports.example.com

Report Service gọi Billing API:
    downstream_token.aud = https://billing.example.com
    downstream_token.scope = invoices:read
    downstream_token.subject/delegation = theo quyền caller được cấp
~~~

Điều kiện quan trọng là **Authorization Server cấp quyền cho đúng đối tượng nhận và giới hạn theo policy**; resource server phải **tự kiểm tra audience**. Không chỉnh tay claim aud trong JWT, không tái sử dụng token sai audience, không cho phép API tự chọn khóa/issuer từ đầu vào không tin cậy.

### 7.5. Chống bị đánh cắp và phát lại: biện pháp bổ trợ

Confused deputy có thể xảy ra khi token hoàn toàn hợp lệ và được cầm bởi chủ thể đúng. Tuy vậy, thiết kế bảo vệ token vẫn cần:

- Luôn dùng TLS/HTTPS; không đưa access token, refresh token vào URL, log, crash report hay analytics.
- Giới hạn thời gian sống, audience, scope và chính sách thu hồi; nhớ rằng JWT offline có thể còn dùng được tới hạn nếu không có cơ chế kiểm tra trạng thái bổ sung.
- Dùng refresh token rotation/phát hiện tái sử dụng nếu chính sách cấp refresh token yêu cầu.
- Cân nhắc **DPoP (RFC 9449)** hoặc **mTLS sender-constrained token (RFC 8705)** để giảm khả năng kẻ khác sử dụng lại access token bị lấy cắp, khi hạ tầng và client hỗ trợ.
- Với token opaque, dùng introspection từ Authorization Server tin cậy; chú ý tính nhất quán và khoảng thời gian cache trạng thái token.

Các biện pháp này bảo vệ credential, nhưng **không thay thế kiểm tra caller có quyền với resource và deputy có được dùng quyền đó hay không**.

## 8. Ví dụ đối chiếu cách viết API

Giả sử Report Service có endpoint:

~~~http
POST /api/reports/invoices HTTP/1.1
Host: reports.example.com
Authorization: Bearer <ALICE_ACCESS_TOKEN>
Content-Type: application/json

{"invoiceId": "B-900"}
~~~

### 8.1. Cách dễ mắc lỗi

~~~java
// Pseudocode Java để minh họa lỗi, không phải mã triển khai hoàn chỉnh.
Report createReport(VerifiedPrincipal caller, String invoiceId) {
    requireScope(caller, "reports:create");

    // BUG: invoiceId do caller chọn, không kiểm tra quyền trên hóa đơn.
    // Service token được cấp quyền đọc hóa đơn toàn hệ thống.
    Invoice invoice = billingAdminClient.getInvoice(invoiceId);

    return renderReport(invoice);
}
~~~

Vấn đề không nằm ở cú pháp Java mà ở **điểm quyết định truy cập bị thiếu trước khi gọi bằng token có quyền rộng**. Endpoint chỉ kiểm tra scope **reports:create** của Alice; Billing lại chỉ nhìn thấy quyền **invoices:read:all** của Report Service.

### 8.2. Cách triển khai có ràng buộc quyền

~~~java
// Pseudocode khái niệm: mọi lớp bên dưới phải được thiết kế và bảo vệ.
Report createReport(VerifiedPrincipal caller, String invoiceId) {
    requireScope(caller, "reports:create");

    // Kiểm tra quyền của caller trên invoice theo dữ liệu đáng tin cậy.
    AuthorizationDecision decision = invoicePolicy.authorize(
        caller.issuer(),
        caller.subject(),
        caller.tenant(),
        "invoice:read",
        invoiceId
    );
    if (!decision.allowed()) {
        throw new ForbiddenException();
    }

    // Lấy token downstream cho Billing, giới hạn theo chính sách delegation.
    AccessToken token = authorizationClient.getDelegatedBillingToken(
        caller,
        "invoices:read"
    );

    // Billing cũng phải kiểm tra token và quyền trên invoice.
    Invoice invoice = billingClient.getInvoice(invoiceId, token);
    return renderReport(invoice);
}
~~~

Với Java/Spring Security, **OAuth2 Resource Server** có thể đảm nhiệm việc xác minh bearer token và chuyển claims đã xác minh thành Authentication/authorities. Annotation như **@PreAuthorize** hữu ích để kiểm tra quyền ở cấp endpoint, nhưng **hasAuthority('SCOPE_reports:create')** chỉ là điều kiện coarse-grained. Logic nghiệp vụ phải kiểm tra thêm ownership/tenant/permission của invoice, và Billing API phải có policy cho token nó nhận.

Ví dụ trên dùng kiểu **VerifiedPrincipal**, **AuthorizationDecision** và **getDelegatedBillingToken** giả định để nhấn mạnh kiến trúc; đây **không phải API có sẵn** của Spring Security. Việc triển khai token exchange/on-behalf-of phụ thuộc Authorization Server, loại client và contract giữa các dịch vụ. Nếu chưa hỗ trợ delegated token, vẫn phải có cách kiểm tra quyền đáng tin cậy trước khi dùng service token và giới hạn quyền trong Billing.

### 8.3. Vì sao check mỗi tenant từ request body là sai?

Sai:

~~~java
String tenant = request.getTenantId();
return billingAdminClient.getInvoice(tenant, request.getInvoiceId());
~~~

Tốt hơn về nguyên tắc:

~~~text
principalTenant = tenant của caller đã xác minh
resourceTenant  = tenant thực của invoice từ dữ liệu nghiệp vụ tin cậy
authorization   = policy(principal, action, invoice, tenant)

require authorization == ALLOW
thực hiện thao tác chỉ trong phạm vi quyền đã cho phép
~~~

Không chỉ so sánh hai chuỗi tenant là đủ cho mọi mô hình: có người dùng được ủy quyền qua nhiều tenant, chia sẻ dữ liệu hoặc vai trò quản trị có giới hạn. Policy cần biết **quan hệ và loại quyền thực sự**; client không được tự gắn quyền chỉ bằng cách thay tenantId.

## 9. Checklist thiết kế và kiểm thử

### 9.1. Checklist cho thiết kế API

| Câu hỏi | Kết quả mong muốn |
|---|---|
| API này nhận request từ ai? | Xác định caller là người dùng, client, tác vụ nội bộ hay integration bằng chứng xác thực tin cậy |
| Deputy có quyền mạnh hơn caller không? | Liệt kê từng credential/quyền mà deputy có thể sử dụng |
| Request chỉ định target nào? | Có policy kiểm tra quyền trên resource ID, tenant và action cụ thể |
| Token nào dùng ở mỗi hop? | Mỗi token có issuer, audience, loại token và scope phù hợp resource server đích |
| Có giữ được user/delegation context không? | Context được issuer/authority đáng tin xác nhận hoặc được kiểm tra lại, không chỉ dựa vào header tùy ý |
| Khi gọi downstream bằng service token, ai chịu trách nhiệm phân quyền? | Trách nhiệm rõ ràng, có kiểm tra ở deputy và/hoặc downstream theo hợp đồng |
| Quyền của service account có quá rộng không? | Dùng least privilege, tách loại tác vụ và giới hạn khách hàng/tài nguyên nếu hỗ trợ |
| Nếu job chạy lại hoặc retry thì sao? | Ngữ cảnh ủy quyền, idempotency và trạng thái quyền được xử lý phù hợp; không dùng lại token trái mục đích |
| Nếu token hết hạn, bị thu hồi hoặc bị lộ? | Có chính sách lifetime, refresh/revocation và phản ứng sự cố, giới hạn tác động khi credential bị lạm dụng |

### 9.2. Kiểm thử lỗi mà happy path thường bỏ sót

| Trường hợp | Kết quả đúng |
|---|---|
| Alice tenant-A yêu cầu invoice thuộc tenant-A và có quyền | Cho phép, nếu mọi điều kiện khác đều đạt |
| Alice tenant-A yêu cầu invoice thuộc tenant-B | **403 Forbidden** hoặc kết quả không tiết lộ dữ liệu theo chính sách API |
| Alice đổi tenantId trong body thành tenant-B | Không mở rộng quyền; đánh giá dựa trên principal và resource thật |
| Token có chữ ký đúng nhưng aud là API khác | **401 Unauthorized** hoặc thông báo invalid token phù hợp giao thức |
| Token caller thiếu scope reports:create | Từ chối theo chính sách; không khởi tạo hành động dùng service credential |
| Client gửi header X-Role: admin hoặc X-User-Id khác | Header không tạo ra quyền mới |
| Billing nhận ID token thay access token | Từ chối token sai mục đích |
| Deputy dùng token client credentials cho hành động do user khởi phát | Phải có kiểm soát ủy quyền tương ứng trước khi hoàn thành; không lộ tài nguyên ngoài quyền user |
| Job xuất hóa đơn được chạy sau khi quyền user thay đổi | Hành vi tuân theo chính sách kiểm tra lại quyền/vòng đời quyền đã định nghĩa |
| Cùng sub ở hai issuer khác nhau | Không gộp nhầm danh tính và quyền chỉ theo sub |

Trong HTTP, **401** thường biểu thị thiếu hoặc không hợp lệ credential; **403** thường biểu thị credential đã được xác thực nhưng không đủ quyền. Ứng dụng có thể dùng **404** để giảm tiết lộ sự tồn tại của tài nguyên nếu chính sách đã định, miễn sao không trả dữ liệu nhạy cảm.

### 9.3. Theo dõi và điều tra khi có sự cố

Khi một service account thực hiện hành động, log và trace nên đủ để trả lời:

- Request gốc đến từ principal/issuer/client nào; kết quả xác thực và phân quyền ra sao?
- Deputy nào đã thực hiện hành động, bằng danh tính dịch vụ nào?
- Target resource, tenant, action, kết quả allow/deny, correlation ID và thời điểm là gì?
- Có token exchange hoặc delegation hay không; policy nào đã giới hạn quyền?

Log chỉ nên lưu **metadata tối thiểu và đã được kiểm soát**, không lưu bearer token hay refresh token ở dạng nguyên vẹn. Để phát hiện lạm dụng, có thể theo dõi các thao tác quản trị được kích hoạt từ endpoint công khai, truy cập chéo tenant bất thường, việc dùng scope rộng ngoài tác vụ nội bộ và mức tăng đột biến lỗi authorization.

## 10. Câu hỏi suy luận

**Tình huống 1.** Người dùng A sở hữu JWT còn hạn và đúng issuer. Report Service kiểm tra scope tạo báo cáo rồi gọi Billing bằng token dịch vụ có scope đọc tất cả hóa đơn. Người dùng A yêu cầu hóa đơn của B. Ai là deputy?

**Trả lời:** Report Service là deputy vì nó nhận chỉ dẫn từ A và sử dụng đặc quyền của chính mình để truy cập Billing. Token hợp lệ của A chỉ chứng minh điều kiện truy cập endpoint ở mức đã kiểm tra; không chứng minh quyền đọc hóa đơn của B.

**Tình huống 2.** Nếu Billing API kiểm tra đúng audience của service token và chữ ký, cuộc tấn công trên có biến mất không?

**Trả lời:** Không. Trong ví dụ, service token vốn có **aud=Billing API** và phạm vi đọc rộng. Vấn đề là quyền đó được dùng để đáp ứng yêu cầu chưa được ủy quyền của Alice. Cần kiểm tra quyền trên hóa đơn và ràng buộc tác vụ với nguồn yêu cầu.

**Tình huống 3.** Có thể khắc phục bằng cách thêm claim **tenant_id** do frontend gửi vào payload JSON không?

**Trả lời:** Không. Dữ liệu frontend tự khai không đáng tin. Tenant/principal phải đến từ danh tính đã được xác minh hoặc hệ thống quyền đáng tin cậy, rồi được đối chiếu với tenant thực của tài nguyên theo policy.

**Tình huống 4.** Token exchange có giải quyết triệt để confused deputy không?

**Trả lời:** Không tự động. Authorization Server phải kiểm soát điều kiện trao đổi, audience và quyền delegation; API đích vẫn phải kiểm tra quyền trên tài nguyên. Token exchange giúp mang ngữ cảnh caller sang đúng dịch vụ nhận và giới hạn quyền **nếu** được cấu hình, cấp phát và xác minh đúng.

**Tình huống 5.** Nếu chuyển từ JWT sang opaque token thì sao?

**Trả lời:** Resource server thay đổi cách xác minh, chẳng hạn bằng introspection, nhưng lỗi confused deputy vẫn tồn tại nếu một dịch vụ dùng quyền cao của mình để thực hiện hành động ngoài quyền caller. Định dạng token không thay thế quyết định phân quyền nghiệp vụ.

## 11. Ghi nhớ

Để nhận ra confused deputy trong một luồng token, hãy lần theo **chuỗi yêu cầu và chuỗi quyền**:

1. **Ai yêu cầu hành động?** Caller được xác thực bằng token nào và có quyền gì?
2. **Ai thực hiện hành động?** Deputy dùng credential của chính mình hay quyền được ủy quyền?
3. **Quyền có bị mở rộng khi qua hop không?** Scope, audience, subject, client, actor và tenant có được ràng buộc đúng?
4. **Tài nguyên thực sự thuộc ai?** Đã kiểm tra authorization đối với đúng resource ID và action chưa?
5. **Ai chịu trách nhiệm từ chối?** Mỗi dịch vụ có kiểm tra đúng phần trách nhiệm của mình hay chỉ tin vào dịch vụ trước?

**Nguyên tắc cốt lõi:** một thành phần không được dùng đặc quyền của mình để thỏa mãn chỉ dẫn của bên khác nếu chưa xác minh bên đó được quyền yêu cầu hành động cụ thể. **Token đúng chữ ký, đúng audience và đúng scope vẫn chỉ là một phần của quyết định bảo mật**. Muốn bảo vệ hệ thống token, phải kết hợp vòng đời token, kiểm soát issuer/claims, giới hạn quyền và authorization trên từng tài nguyên xuyên suốt các ranh giới dịch vụ.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): mô hình các vai trò client, authorization server và resource server.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange, subject token, actor và delegation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu access token cho resource cụ thể.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim của JWT access token, audience và token typing.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh token, thuật toán, issuer và audience.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các khuyến nghị OAuth 2.0 security hiện hành.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái opaque token/access token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token và bảo vệ chống replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): token ràng buộc chứng chỉ và mTLS.
