# Xác minh hoàn tất Leaver: chứng minh quyền truy cập đã được thu hồi

Trong quản lý vòng đời danh tính **Identity and Access Management (IAM)**, **Leaver** là giai đoạn một cá nhân kết thúc quan hệ làm việc, hợp đồng hoặc nhiệm vụ có liên quan đến quyền truy cập. **Xác minh hoàn tất Leaver (*leaver completion verification*)** là bước kiểm tra có bằng chứng rằng các hành động cần thiết đã thực sự đưa hệ thống về **trạng thái truy cập mong muốn**, theo đúng thời điểm và phạm vi chính sách đã quy định.

Điểm quan trọng nhất là phân biệt **đã yêu cầu thu hồi** với **đã thu hồi thành công**. Một lệnh vô hiệu hóa ở **Identity Provider (IdP)**, một phản hồi API thành công hoặc một ticket có trạng thái “Done” chưa tự chứng minh rằng mọi tài khoản ứng dụng, nhóm, quyền trực tiếp, phiên SSO, token hoặc lối truy cập còn lại đã hết hiệu lực.

Bài học thuộc chương **Leaver lifecycle** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Chủ đề kết nối toàn bộ quá trình **Joiner–Mover–Leaver (JML)**: lúc Joiner cần định danh, tạo tài khoản và cấp quyền đúng; lúc Mover phải cập nhật quyền theo vai trò; lúc Leaver phải thu hồi và **đối soát** quyền trên từng hệ thống đích. **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, quản lý phiên và kiểm toán** đều cung cấp dữ liệu để kết luận chính xác, hạn chế **quyền truy cập tồn dư (*residual access*)**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **khi nào một quy trình Leaver đủ điều kiện đóng** và những trạng thái trung gian không được coi là hoàn tất.
2. Xác định **danh sách tài khoản, ứng dụng, nhóm, vai trò, quyền đặc biệt, phiên, token và lối truy cập vật lý** cần kiểm tra.
3. Phân biệt **bằng chứng thực thi lệnh**, **bằng chứng trạng thái đích** và **bằng chứng quyền hiệu dụng**.
4. Thiết kế cơ chế **readback, đối soát, retry có kiểm soát và xử lý lỗi một phần** khi thu hồi qua IdP, SSO, SCIM/API và ứng dụng.
5. Xây dựng **tiêu chí chấp nhận, hồ sơ kiểm toán, người chịu trách nhiệm và quy tắc ngoại lệ** cho kết quả Leaver.
6. Xử lý tình huống một người có **nhiều quan hệ công việc**, contractor có ngày kết thúc hợp đồng, hoặc tài khoản dịch vụ từng do Leaver vận hành.
7. Đánh giá tính hoàn tất dựa trên **trạng thái truy cập thực tế và bằng chứng đáng tin cậy** thay vì chỉ nhìn trạng thái ở nguồn nhân sự.

## 2. “Hoàn tất” có nghĩa là gì?

Một quy trình Leaver đạt yêu cầu khi **mọi nghĩa vụ thu hồi trong phạm vi của biến cố** đã được thực thi, kiểm chứng và ghi nhận theo chính sách. Cần trả lời đồng thời ba câu hỏi:

- **Đúng chủ thể và phạm vi chưa?** Những account nào thuộc cá nhân hoặc quan hệ làm việc kết thúc? Có quyền nào còn căn cứ hợp lệ từ một hợp đồng khác không?
- **Đúng trạng thái bảo mật chưa?** Tài khoản, quyền, khả năng đăng nhập, phiên/token và đường truy cập liên quan đã bị chặn, thu hồi hoặc hết hiệu lực theo tiêu chí từng hệ thống chưa?
- **Có chứng minh được không?** Có dữ liệu đọc lại từ các đích, log/kết quả kiểm tra và người chịu trách nhiệm cho hạng mục chưa hoàn tất không?

Không phải mọi hệ thống đều phải **xóa hẳn account**. Tùy chính sách, hệ thống có thể vô hiệu hóa account và giữ hồ sơ để đáp ứng lưu trữ, bảo toàn giao dịch và kiểm toán. Đối với truy cập, câu hỏi chính là **người hoặc credential không còn được phép có tiếp tục sử dụng được tài nguyên hay không**.

| Mốc trạng thái | Ý nghĩa | Được coi là hoàn tất? |
|---|---|---|
| **Leaver recorded** | Nguồn có thẩm quyền đã ghi nhận nghỉ việc/hết hợp đồng | Chưa |
| **Deprovision requested** | IAM đã lập kế hoạch và gửi lệnh thu hồi | Chưa |
| **Request accepted** | IdP/SCIM/API nhận hoặc đưa lệnh vào hàng đợi | Chưa |
| **Target updated** | Có xác nhận trạng thái account/quyền tại đích | Chưa chắc, cần kiểm tra toàn phạm vi |
| **Access verified** | Các lối truy cập bắt buộc đã được xác minh hết hiệu lực theo chính sách | Có thể đạt điều kiện đóng |
| **Audit closed** | Hoàn tất kiểm soát, lưu bằng chứng và xử lý các lỗi/ngoại lệ | Đã hoàn tất quy trình theo tiêu chí đã duyệt |

**Ví dụ:** Hệ thống nhân sự ghi trạng thái `terminated`, IAM gửi SCIM `active=false` và nhận HTTP thành công. Tuy nhiên, ứng dụng vẫn giữ một phiên đăng nhập cũ có quyền đọc dữ liệu. Hệ thống đã **thực thi một phần**, nhưng chưa thể kết luận toàn bộ lối truy cập đã được thu hồi nếu phiên này nằm trong yêu cầu phải chặn.

## 3. Chọn đúng chủ thể, quan hệ công việc và mốc thu hồi

Bước kiểm chứng phải bắt đầu từ **biến cố Leaver có thẩm quyền**, không phải từ một danh sách account bị khóa ngẫu nhiên.

### 3.1. Dữ liệu nguồn cần xác nhận

| Trường | Ví dụ | Vai trò |
|---|---|---|
| `personId` | `P-2408` | Định danh ổn định của cá nhân, không chỉ email |
| `engagementId` | `ENG-713` | Quan hệ làm việc/dự án bị kết thúc |
| `eventId` / phiên bản | `LV-2026-031` | Truy vết, chống xử lý sự kiện trùng/cũ |
| `leaverType` | Nghỉ việc, hết hợp đồng, chấm dứt nhiệm vụ | Xác định phạm vi theo chính sách |
| `effectiveAt` | `2026-12-01T17:00:00+07:00` | Mốc quyền cần chấm dứt |
| Nguồn có thẩm quyền | HR, VMS/hợp đồng hoặc quy trình được duyệt | Căn cứ ra quyết định |
| Sponsor/manager | Quản lý nội bộ chịu trách nhiệm | Xác nhận phạm vi và bàn giao |
| Danh sách ngoại lệ hợp lệ | Engagement khác, nghĩa vụ riêng | Ngăn thu hồi nhầm hoặc giữ sai quyền |

**Không chỉ dùng địa chỉ email** để xác định các account cần thu hồi. Email có thể thay đổi hoặc được dùng lại; một người có nhiều account ở các hệ thống, và account cũ có thể dùng tên khác. Cần liên kết **identity ổn định → account ID tại từng đích → nguồn cấp quyền** đã được quản lý từ lúc Joiner.

### 3.2. Phân biệt Leaver toàn tổ chức và kết thúc một engagement

Một cá nhân có thể đồng thời là nhân viên chính thức và cố vấn của dự án khác, hoặc contractor tham gia hai hợp đồng. Khi kết thúc một engagement, không nên mặc định **xóa mọi account và quyền** nếu vẫn còn quan hệ hợp lệ. Ngược lại, tài khoản vẫn active không chứng minh rằng **quyền dự án đã kết thúc** được phép giữ.

Hai trường hợp cần kết quả khác nhau:

- **Toàn bộ quan hệ hợp lệ kết thúc:** Phải chặn khả năng truy cập của cá nhân vào tài nguyên không còn được phép, theo thời hạn chính sách và xử lý các phiên/credential liên quan.
- **Chỉ một dự án hoặc vai trò kết thúc:** Thu hồi quyền thuộc engagement đã chấm dứt, giữ các quyền được chứng minh còn hợp lệ bởi engagement khác.

Một quy trình hoàn tất phải lưu căn cứ cho cả **quyền đã thu hồi** lẫn **quyền chủ động giữ lại**. Việc giữ một quyền không có nguồn bảo trợ rõ ràng là dấu hiệu cần điều tra.

## 4. Phạm vi kiểm chứng phải rộng hơn IdP

Đầu tiên cần xây dựng **inventory các đường truy cập** từ dữ liệu Identity Governance/Administration (IGA), IdP, danh mục ứng dụng, nguồn quyền trực tiếp, quản lý đặc quyền, tài khoản máy và hệ thống vật lý.

| Thành phần cần xác minh | Ví dụ quyền còn sót | Bằng chứng nên thu thập |
|---|---|---|
| **IdP / tài khoản chính** | Account vẫn enabled hoặc khôi phục lại do đồng bộ trễ | Trạng thái account, nhóm, thời điểm áp dụng và readback |
| **SSO / federation** | Phiên còn hợp lệ hoặc ứng dụng vẫn chấp nhận token đã phát hành | Trạng thái phiên/token, hành vi ứng dụng và chính sách hết hiệu lực |
| **SCIM / provisioning** | Ứng dụng chưa thực hiện `active=false` hoặc chưa bỏ nhóm | Trạng thái user/group thực tế ở đích, lỗi đồng bộ |
| **Ứng dụng nghiệp vụ** | Role cục bộ, quyền export, quyền approval | Entitlement hiệu dụng, trạng thái user, cấp trực tiếp |
| **PAM / tài khoản đặc quyền** | Admin local, đặc quyền JIT chưa hết, quyền truy cập jump host | Trạng thái vault, role, session/checkout và quyền quản trị |
| **API / OAuth / personal access token** | Token cá nhân hoặc refresh token tiếp tục gọi API | Thu hồi/hết hiệu lực token và xác minh cơ chế thực thi |
| **Kho mã / cloud / CI/CD** | SSH key, deploy key, IAM policy, quyền repo trực tiếp | Membership, key, role, resource policy thực tế |
| **Dữ liệu và chia sẻ** | Thư mục chia sẻ trực tiếp, ACL, quyền báo cáo | Danh sách chia sẻ, ACL và quyền hiệu dụng |
| **VPN / ZTNA / thiết bị** | Tài khoản VPN, chứng thư thiết bị cá nhân | Trạng thái truy cập mạng, chứng thư và phiên liên quan |
| **Ra vào vật lý** | Thẻ nhân viên vẫn mở cửa hoặc quyền vào khu vực hạn chế | Trạng thái badge và quyền theo cửa/site |
| **Hệ thống legacy / shadow account** | User local không liên kết IdP, chưa có connector | Bằng chứng kiểm kê, quy trình thủ công và kết quả xác minh |
| **Danh tính máy liên quan** | Secret/credential nhà thầu từng giữ hoặc biết | Kết quả chuyển owner, rà soát và xoay vòng/thu hồi khi cần |

**Phạm vi xác minh** là tập hệ thống và loại quyền mà tổ chức đã xác định cần thu hồi theo biến cố này. Không nên cho rằng một connector SCIM bao phủ toàn bộ tài khoản và quyền tồn tại trong ứng dụng. Phải có **danh mục các target bắt buộc** và owner chịu trách nhiệm kiểm tra từng đích.

### Bốn lớp thường bị nhầm

1. **Authentication:** IdP hoặc ứng dụng có còn chấp nhận người này đăng nhập không?
2. **Provisioning:** User account có bị vô hiệu hóa/xóa và nhóm có được cập nhật tại đích không?
3. **Authorization:** API và dữ liệu có còn cho phép hành động nhờ role, ACL, token, nhóm hoặc điều kiện ABAC không?
4. **Session/credential control:** Những phiên, khóa và token đã phát trước biến cố có còn sử dụng được không?

Hoàn tất ở lớp thứ hai không tự bảo đảm ba lớp còn lại đã an toàn.

## 5. Luồng xác minh hoàn tất Leaver

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền<br/>Leaver event + mốc hiệu lực"] --> B["Xác minh identity, engagement,<br/>danh sách account và target"]
    B --> C["Tính trạng thái truy cập mong muốn<br/>theo chính sách và ngoại lệ còn hiệu lực"]
    C --> D["Phát lệnh deprovision<br/>IdP, SCIM/API, app, PAM, badge"]
    D --> E["Theo dõi kết quả từng đích"]
    E --> F["Readback trạng thái account,<br/>quyền hiệu dụng, phiên/token"]
    F --> G{"Mọi hạng mục bắt buộc<br/>đã đạt tiêu chí?"}
    G -->|Có| H["Ghi bằng chứng, thời điểm<br/>và xác nhận hoàn tất"]
    G -->|Có lỗi hoặc chưa rõ| I["Tạo issue, owner, deadline<br/>và biện pháp kiểm soát"]
    I --> J["Khắc phục / retry có kiểm soát<br/>hoặc xử lý ngoại lệ được duyệt"]
    J --> F
    H --> K["Đối soát hậu kiểm<br/>phát hiện quyền tái xuất hiện"]
~~~

### Bước 1 — Chốt căn cứ, mốc hiệu lực và phạm vi

Kiểm tra biến cố từ HR/VMS, trạng thái identity, các engagement và hệ thống đích cần xử lý. Với chấm dứt bất thường, chính sách có thể yêu cầu **thu hồi ngay**; với kết thúc hợp đồng có kế hoạch, có thể chuẩn bị hành động trước mốc nhưng chỉ cấp/quyền phù hợp cho đến thời điểm được phép.

### Bước 2 — Tính trạng thái truy cập mong muốn

Tập quyền mong muốn sau Leaver có thể là rỗng đối với danh tính không còn bất kỳ quan hệ hợp lệ nào. Với người vẫn tham gia dự án khác, tập quyền mong muốn chỉ giữ phần có căn cứ còn hiệu lực. Cần kiểm tra **RBAC, ABAC, nhóm lồng nhau, direct grants, policy resource và ngoại lệ có thời hạn**.

### Bước 3 — Thu hồi bằng cơ chế của từng đích

IAM dùng IdP, SCIM/API, PAM hoặc quy trình thủ công có kiểm soát để vô hiệu hóa user và thu hồi quyền. Các hệ thống có thể xử lý **bất đồng bộ**; cần theo dõi job, trạng thái nhận lệnh, xử lý lỗi một phần và readback.

### Bước 4 — Đối soát trạng thái thực tế

Đọc lại account/quyền tại target hoặc lấy bằng chứng tương đương đáng tin. Nếu cần kiểm tra khả năng truy cập, ưu tiên **phương pháp kiểm thử được phép, không gây tác động** như kiểm tra chính sách, token revocation/status hoặc thử hành động chỉ đọc trên dữ liệu kiểm thử. Không thực hiện thao tác nghiệp vụ nguy hiểm chỉ để chứng minh quyền đã hết.

### Bước 5 — Ghi bằng chứng và đóng có điều kiện

Kết luận `COMPLETED` chỉ khi **toàn bộ các hạng mục bắt buộc** có kết quả đạt theo tiêu chí cụ thể, hoặc có ngoại lệ được quản trị riêng phù hợp chính sách. Không được âm thầm biến lỗi/đích chưa kiểm tra thành “đã thu hồi”. Bước hậu kiểm giúp phát hiện quyền bị tạo lại từ đồng bộ sai hoặc nguồn cấp quyền ngoài quy trình.

## 6. Phân biệt bằng chứng lệnh đã chạy và bằng chứng quyền đã hết

| Bằng chứng | Chứng minh được điều gì? | Giới hạn |
|---|---|---|
| Sự kiện HR/VMS kết thúc | Có căn cứ nghiệp vụ để bắt đầu Leaver | Chưa chứng minh bất kỳ account đã bị khóa |
| Lệnh API/SCIM được gửi | IAM đã yêu cầu thay đổi | Lệnh có thể timeout hoặc xử lý sau |
| HTTP 2xx / job accepted | Đích chấp nhận thao tác hoặc đã xử lý một phần theo đặc tả | Chưa chắc session, token, ACL, ứng dụng phụ bị thu hồi |
| Đọc lại `active=false` | Bản ghi người dùng ở đích ở trạng thái inactive | Có thể vẫn tồn tại token độc lập, account khác hoặc quyền chia sẻ |
| Đọc lại nhóm/role/ACL | Quyền cấu hình trên đích đã thay đổi | Cần xét quyền kế thừa, cấp trực tiếp và cache |
| Kiểm tra phiên/token | Một tập phiên/credential cụ thể đã bị thu hồi hoặc hết hạn | Phải xét khả năng kiểm tra và các loại token khác |
| Kiểm tra quyền hiệu dụng | Quyết định authorization cho hành động/tài nguyên được kiểm tra đã từ chối | Chỉ bao phủ phạm vi hành động/tài nguyên kiểm tra |
| Đối soát toàn bộ inventory bắt buộc | Các trạng thái cần kiểm chứng đều đạt | Phụ thuộc inventory đầy đủ, chất lượng nguồn và thời điểm đọc |
| Hồ sơ đóng có owner và thời gian | Quy trình được xác nhận theo chính sách | Không thay thế các bằng chứng kỹ thuật bên trên |

Từ “readback” nghĩa là **đọc lại dữ liệu đã áp dụng tại hệ thống đích**, hoặc nguồn quan sát có độ tin cậy và độ mới phù hợp. Đọc lại một bản cache của hệ thống gửi lệnh có thể chỉ chứng minh **ý định thay đổi**, không xác nhận hệ thống đích thực thi.

### Tính cập nhật của bằng chứng

Đối với hệ thống xử lý bất đồng bộ, một lần đọc quá sớm có thể thấy trạng thái cũ; quá trình đóng phải quy định **mốc thời gian kiểm tra, giới hạn chờ/đối soát và tiêu chí kết quả cuối**. Nếu đích không thể xác minh trong giới hạn cho phép, hạng mục phải ở trạng thái `PENDING_VERIFICATION` hoặc `FAILED` và được xử lý theo chính sách. Không suy đoán thành công.

## 7. IdP, SSO và phiên đăng nhập: những gì cần xác minh

**IdP** thường là điểm đầu tiên để chặn đăng nhập mới. Tuy nhiên, khả năng truy cập vào từng ứng dụng còn phụ thuộc **phiên SSO, phiên nội bộ, token được phát hành, cơ chế federation và cách ứng dụng thực thi authorization**.

### 7.1. Trạng thái account tại IdP

Nên kiểm tra:

- Account gắn với đúng identity có trạng thái không còn được phép đăng nhập.
- Nhóm, role hoặc các quyền do IdP quản lý đã được bỏ theo chính sách.
- Chính sách không có tác vụ tự động hoặc đồng bộ ngược **tái kích hoạt** account từ bản ghi cũ.
- Các phương thức xác thực và khôi phục tài khoản không cho phép tự mở lại truy cập trái điều kiện.

### 7.2. Phiên SSO và token

Một người có thể đang có:

- Phiên đăng nhập tại IdP.
- Phiên riêng của ứng dụng nhận SSO.
- Access token đã phát hành, token tự chứa có thời hạn (*self-contained token*).
- Refresh token dùng để xin access token mới.
- Personal access token, API key hoặc token do ứng dụng tạo trực tiếp.

**Vô hiệu hóa người dùng ở IdP không bảo đảm mọi token và phiên đã phát hành bị hủy lập tức.** Cần đánh giá cơ chế của từng ứng dụng: session revocation, kiểm tra trạng thái account mỗi request, giới hạn tuổi token, token introspection, thu hồi refresh token, back-channel logout hoặc giải pháp khác được hỗ trợ.

Không tuyên bố “thu hồi tức thì” nếu hệ thống chỉ dựa trên **token có hạn còn hiệu lực đến lúc hết hạn**. Khi chính sách đòi chặn truy cập sớm hơn, cần cơ chế bổ sung ở ứng dụng/API hoặc biện pháp kiểm soát phù hợp.

### 7.3. Xác minh quyền tại tầng ứng dụng

Một thao tác API được phép hay không phải được quyết định theo **quyền hiện hành**, không chỉ sự tồn tại của giao diện đăng nhập. Các đường API độc lập, endpoint legacy hoặc role nội bộ phải nằm trong rà soát nếu có thể truy cập tài nguyên nhạy cảm.

## 8. SCIM, tài khoản ứng dụng và lỗi đồng bộ một phần

**System for Cross-domain Identity Management (SCIM)** hỗ trợ quản lý user/group giữa các hệ thống, nhưng việc ứng dụng hỗ trợ đầy đủ thao tác nào và tác động đến session/role ra sao phụ thuộc từng implementation.

Ví dụ payload cập nhật trạng thái user theo SCIM, chỉ mang tính minh họa:

~~~http
PATCH /scim/v2/Users/12345
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

`active=false` có thể mô tả việc user không còn hoạt động ở resource SCIM. **Không được tự suy ra** rằng mọi role, group, phiên, khóa API hoặc tài khoản khác trong ứng dụng đã được xóa. Hãy kiểm chứng hành vi thực tế của tích hợp.

### Ví dụ lỗi một phần

~~~text
Leaver event: LV-2026-031
Identity: P-2408
Mốc thu hồi: 17:00

IdP:
    DISABLED       - readback PASS
CRM:
    INACTIVE       - readback PASS
Code repository:
    USER REMOVED   - readback PASS
Finance application:
    SCIM ERROR     - readback FAIL
VPN:
    SESSION ACTIVE - verification FAIL

Trạng thái tổng:
    PARTIAL / NOT COMPLETED
    Finance owner xử lý connector
    Network owner xử lý phiên VPN
~~~

Hệ thống không nên đóng Leaver chỉ vì **đa số** target đã đạt. Với target bắt buộc chưa xử lý, phải ghi rõ **mức rủi ro, người chịu trách nhiệm, thời điểm phát hiện, giới hạn xử lý và biện pháp tạm thời** theo chính sách.

### Retry an toàn

- Kiểm tra trạng thái thực tế trước khi thử lại; lệnh trước có thể thành công dù phản hồi bị timeout.
- Dùng ID sự kiện, correlation ID và logic idempotency để không thao tác nhầm account.
- Không tạo hoặc kích hoạt account mới do xử lý nhầm sự kiện cũ.
- Không xóa account thuộc người khác khi tên/email trùng; giải quyết xung đột định danh.
- Sau mỗi thay đổi cần **readback**, không chỉ lưu mã phản hồi mới.

## 9. RBAC/ABAC và quyền truy cập hiệu dụng

Khi Leaver rời tổ chức, IAM thường phải thu hồi các quyền có được từ **vai trò (RBAC)** và làm cho điều kiện **thuộc tính/ngữ cảnh (ABAC)** không còn đáp ứng. Tuy vậy, quyền có thể tồn tại ngoài vai trò chính.

Ví dụ:

~~~text
Quyền đọc báo cáo được cấp bởi:
  Nhóm "finance-readers"                -> đã thu hồi
  Chia sẻ trực tiếp tới user P-2408      -> vẫn còn
  Role cục bộ "report-exporter"          -> vẫn còn

Kết quả:
  Bỏ nhóm chưa đủ để chứng minh không còn quyền đọc/xuất.
~~~

**Effective entitlement (quyền hiệu dụng)** cần xét các nguồn liên quan:

- Quyền do nhóm, vai trò và nhóm lồng nhau.
- Quyền cấp trực tiếp tới user, email hoặc account ứng dụng.
- Policy gắn ở tài nguyên (*resource policy*) hoặc chia sẻ ngoài IAM.
- Ngoại lệ tạm thời, quyền đặc quyền và quyền còn trong phiên hiện tại.
- Điều kiện ABAC như `engagementStatus`, `projectId` và thời điểm hiệu lực.

### Tính trạng thái mong muốn

Có thể mô tả bằng tập hợp:

~~~text
EffectiveBefore = quyền thực tế trước Leaver
DesiredAfter    = quyền còn được phép theo mọi engagement hợp lệ
ToRevoke        = EffectiveBefore - DesiredAfter
ToKeep          = EffectiveBefore ∩ DesiredAfter

Không có engagement hợp lệ:
    DesiredAfter = {}

Có engagement khác:
    DesiredAfter = quyền riêng còn căn cứ hợp lệ của engagement đó
~~~

Đây là công thức khái niệm. Trong thực tế cần lưu **nguồn cấp quyền** (*grant provenance*) để loại đúng grant hết căn cứ; xóa một grant có thể không làm mất quyền hiệu dụng nếu còn grant khác. Đánh giá hoàn tất phải dựa trên **khả năng truy cập cuối cùng**, không chỉ số lượng nhóm bị xóa.

## 10. Credential, API key và tài khoản dịch vụ có liên quan

Một Leaver có thể từng vận hành **service account**, tạo API key, quản trị secret hoặc nắm giữ quyền khôi phục của hệ thống. Tài khoản máy có thể tiếp tục phục vụ hệ thống sản xuất, nên không phải cứ người rời đi là phải xóa ngay toàn bộ tài khoản dịch vụ.

Cần phân biệt:

1. **Danh tính cá nhân:** Account và quyền do người rời tổ chức trực tiếp sở hữu hoặc điều khiển.
2. **Credential mà người đó có thể tiếp tục sử dụng:** API key, SSH key, token, mật khẩu máy dùng chung hoặc bí mật đã biết.
3. **Danh tính workload hợp lệ:** Tài khoản máy phục vụ ứng dụng, có thể cần duy trì nhưng phải có owner và secret an toàn.

### Kiểm chứng tối thiểu cho tài khoản dịch vụ

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Tài khoản máy phục vụ workload nào? | Danh mục dịch vụ, owner kỹ thuật và phạm vi tài nguyên |
| Leaver từng có quyền đọc hoặc quản lý credential nào? | Quyền vault/repository, nhật ký truy cập hoặc bằng chứng bàn giao |
| Còn secret/token nào có nguy cơ bị Leaver giữ bản sao? | Danh sách credential cần thay thế theo đánh giá rủi ro |
| Đã chuyển chủ sở hữu và phân quyền quản trị? | Owner mới, role quản trị/vault đã cập nhật |
| Đã xoay vòng hoặc thu hồi credential cần thiết? | Trạng thái secret/key mới và cũ; xác minh hệ thống vẫn vận hành |
| Quyền service account có còn vừa đủ? | Policy hiện hành, quyền hiệu dụng và lịch rà soát |

Nếu một credential cá nhân bị rò rỉ hoặc có thể tiếp tục dùng sau Leaver, việc chỉ bỏ quyền truy cập vào **secret manager** không luôn vô hiệu hóa bản sao secret đã được lấy từ trước. Cần quyết định **rotate/revoke** theo rủi ro và kiểm tra các hệ thống đang tiêu thụ credential đó.

## 11. Quyền vật lý, thiết bị và tài sản số

Leaver có thể vẫn giữ badge, máy tính, chứng thư VPN hoặc tài khoản quản lý thiết bị. Đây là các phần cần xác minh theo chính sách và phạm vi nhiệm vụ.

| Tài sản / đường truy cập | Tiêu chí kiểm chứng |
|---|---|
| **Badge, mã cửa, bãi xe, phòng máy** | Quyền ra vào đã thu hồi theo hệ thống kiểm soát vật lý |
| **VPN/ZTNA và mạng không dây doanh nghiệp** | Account, chứng thư và phiên truy cập thuộc phạm vi đã bị chặn |
| **Thiết bị được quản lý** | Trạng thái bàn giao, quyền quản trị máy, khóa/chứng thư liên quan được xử lý |
| **Kho mã/repository** | Membership, SSH key, token cá nhân và access trực tiếp được thu hồi |
| **Tài liệu/chia sẻ dữ liệu** | Quyền chia sẻ, ACL, liên kết có quyền của người đó đã được xử lý |
| **Mailbox, lịch, kho tài liệu** | Chặn đăng nhập; chuyển giao công việc và lưu giữ dữ liệu theo chính sách |
| **Quyền chủ sở hữu tài nguyên** | Chuyển owner cho người được ủy quyền, tránh tài nguyên mồ côi |

**Thu hồi quyền không đồng nghĩa xóa hết dữ liệu.** Tổ chức có thể cần giữ thư điện tử, log, bằng chứng giao dịch hoặc tài liệu theo quy định. Bằng chứng đóng Leaver phải tách riêng **đã chấm dứt khả năng truy cập** với **đã bàn giao/tái phân công tài sản** và **đã xử lý nghĩa vụ lưu giữ**.

## 12. Trạng thái, tiêu chí đóng và xử lý ngoại lệ

Một workflow nên có trạng thái đủ chính xác:

| Trạng thái | Ý nghĩa vận hành | Có được đánh dấu `COMPLETED`? |
|---|---|---|
| `PENDING_EFFECTIVE_DATE` | Chờ mốc Leaver có hiệu lực | Không |
| `DEPROVISIONING` | Đang gửi và theo dõi hành động thu hồi | Không |
| `PARTIALLY_REVOKED` | Một số target thành công, còn target chưa hoàn tất | Không |
| `PENDING_VERIFICATION` | Đã có thay đổi nhưng thiếu bằng chứng readback đáng tin cậy | Không |
| `BLOCKED_BY_TARGET` | Lỗi API/SCIM, ứng dụng không hỗ trợ hoặc xung đột account | Không |
| `RISK_REVIEW_REQUIRED` | Có quyền/credential đặc biệt chưa có kết luận | Không |
| `VERIFIED_REVOKED` | Từng hạng mục bắt buộc đã đạt tiêu chí thu hồi | Sẵn sàng chốt kiểm toán |
| `COMPLETED` | Verification và bằng chứng kiểm toán đã được xác nhận đủ | Có |
| `EXCEPTION_TRACKED` | Ngoại lệ được ghi nhận, kiểm soát và theo dõi riêng | Chỉ theo quy tắc được chính sách cho phép, không được ngụy trang thành đã thu hồi |

Đây là **bộ trạng thái tham khảo**, không phải schema của một sản phẩm IAM cụ thể. Tổ chức có thể dùng trạng thái khác nhưng phải giữ được phân biệt **chưa làm, đã yêu cầu, đã thực thi, đã kiểm chứng và có ngoại lệ**.

### Tiêu chí chấp nhận gợi ý

Một Leaver chỉ có thể hoàn tất khi:

- Đúng identity/engagement và mốc thu hồi đã được xác định từ nguồn đáng tin cậy.
- Danh sách target và loại quyền bắt buộc đã được lập đầy đủ, có owner.
- Các target bắt buộc đạt kết quả thu hồi, vô hiệu hóa hoặc trạng thái mong muốn tương ứng.
- Những phiên/token/credential có khả năng truy cập sau thời điểm yêu cầu đã được xử lý theo chính sách.
- Quyền hiệu dụng còn lại có căn cứ hợp lệ hoặc được xử lý theo quy trình ngoại lệ chính thức.
- Kết quả readback đủ mới, gắn với đúng account, đúng ứng dụng và đúng biến cố.
- Mọi lỗi/ngoại lệ được ghi rõ, có owner, mức độ rủi ro, biện pháp giảm thiểu và thời hạn xử lý.
- Hồ sơ chứng minh người xác nhận, thời điểm, phiên bản chính sách và kết quả cuối đã được lưu.

**Trường hợp ngoại lệ:** Nếu một hệ thống không hỗ trợ kiểm tra trực tiếp, tổ chức có thể xác định **bằng chứng thay thế và biện pháp bù trừ** đã phê duyệt. Trạng thái phải thể hiện trung thực rằng kết luận có ngoại lệ, chứ không giả làm bằng chứng readback đầy đủ.

## 13. Mẫu bản ghi xác minh Leaver

Hồ sơ dưới đây là **ví dụ khái niệm**, không phải schema chuẩn, dữ liệu thật hay bằng chứng rằng hệ thống đã thực hiện thu hồi:

~~~json
{
  "leaverEventId": "LV-2026-031",
  "personId": "P-2408",
  "engagementId": "ENG-713",
  "effectiveAt": "2026-12-01T17:00:00+07:00",
  "source": "AUTHORITATIVE_HR",
  "verificationPolicyVersion": "leaver-policy-v3",
  "targets": [
    {
      "system": "corporate-idp",
      "accountId": "IDP-108",
      "expected": "DISABLED",
      "observed": "DISABLED",
      "observedAt": "2026-12-01T17:01:12+07:00",
      "verification": "TARGET_READBACK",
      "status": "PASS"
    },
    {
      "system": "finance-app",
      "accountId": "FIN-224",
      "expected": "ACCESS_REVOKED",
      "observed": "UNKNOWN",
      "observedAt": null,
      "verification": "PENDING",
      "status": "PENDING"
    }
  ],
  "overallStatus": "PENDING_VERIFICATION",
  "assignedOwner": "IAM_OPERATIONS",
  "closedAt": null
}
~~~

Dữ liệu cần được bảo vệ bằng phân quyền và chính sách lưu giữ thích hợp. Trong môi trường thật nên có **mã tương quan, nguồn readback, kết quả kiểm tra quyền, lỗi, người phê duyệt ngoại lệ** và đường dẫn chứng cứ được bảo vệ. Không ghi access token, mật khẩu hoặc secret vào log.

**Điểm đáng chú ý:** Đích IdP đã PASS, nhưng `finance-app` vẫn `UNKNOWN`. Trạng thái tổng phải còn `PENDING_VERIFICATION` cho đến khi đủ bằng chứng hoặc có cách xử lý ngoại lệ phù hợp chính sách.

## 14. Mã giả đánh giá điều kiện hoàn tất

Một bộ kiểm tra hoàn tất nên **từ chối đóng khi thiếu bằng chứng**, thay vì mặc định rằng thiếu dữ liệu nghĩa là đã thu hồi.

~~~python
# Pseudocode minh họa; cần ánh xạ theo policy và target thực tế.
def evaluate_leaver_completion(leaver_event, required_targets, results):
    if not leaver_event.authoritative or not leaver_event.is_effective:
        return "PENDING_SOURCE_OR_EFFECTIVE_TIME"

    if not required_targets or not leaver_event.inventory_confirmed:
        return "PENDING_INVENTORY"

    for target in required_targets:
        observed = results.get(target.target_id)

        if observed is None:
            return "PENDING_VERIFICATION"

        if observed.identity_id != leaver_event.person_id:
            return "BLOCKED_IDENTITY_MISMATCH"

        if observed.status in ("UNKNOWN", "FAILED", "PENDING"):
            return "PARTIALLY_REVOKED"

        if not observed.evidence_is_trustworthy_and_fresh:
            return "PENDING_VERIFICATION"

        if not observed.access_matches_expected_state:
            return "PARTIALLY_REVOKED"

        if observed.credential_or_session_risk_unresolved:
            return "RISK_REVIEW_REQUIRED"

    if leaver_event.unresolved_required_exceptions:
        return "RISK_REVIEW_REQUIRED"

    if not leaver_event.audit_record_ready:
        return "PENDING_AUDIT_CLOSURE"

    return "COMPLETED"
~~~

Mã này có mục đích **diễn giải điều kiện đóng**, không thay thế logic quản lý đa engagement, deadline, credential, chính sách riêng từng ứng dụng hoặc ngoại lệ có phê duyệt. Với hệ thống thực, việc đối soát phải xét cả khả năng **quyền bị cấp lại** sau readback do đồng bộ vòng lặp hoặc nguồn dữ liệu cũ.

## 15. Tình huống thực tế: Leaver chưa hoàn tất dù IdP đã khóa

**Bối cảnh:** Một nhân viên phân tích tài chính nghỉ việc lúc 17:00 thứ Sáu. HR phát biến cố Leaver. IAM đã vô hiệu hóa IdP và bỏ nhóm `finance-readers`. Tuy nhiên, người này từng có:

- Tài khoản cục bộ trong ứng dụng quản lý hóa đơn.
- Personal access token truy cập API báo cáo.
- Chia sẻ trực tiếp tới một thư mục dữ liệu tài chính.
- Phiên VPN đang hoạt động.
- Quyền quản lý một service account đồng bộ báo cáo.

### Nếu chỉ kiểm tra IdP

Hệ thống có thể báo `DONE` vì user tại IdP không đăng nhập mới được. Nhưng một số lối truy cập có thể **vẫn tồn tại**, nên chưa đáp ứng điều kiện thu hồi thực tế.

### Các bước kiểm chứng phù hợp

1. **Xác định đúng người:** Đối chiếu `personId`, sự kiện HR, account ID tại ứng dụng hóa đơn và dữ liệu inventory.
2. **Kiểm tra IdP:** Account đã disabled, nhóm đã đổi, phiên cần thu hồi đã được xử lý phù hợp.
3. **Kiểm tra ứng dụng hóa đơn:** Account cục bộ đã bị vô hiệu hóa hoặc mất quyền; không còn role trực tiếp được phép sử dụng.
4. **Kiểm tra token báo cáo:** Token cá nhân đã bị thu hồi/hết hiệu lực hoặc đường API đã từ chối theo chính sách; xác nhận phạm vi.
5. **Kiểm tra chia sẻ:** ACL trực tiếp trên thư mục được gỡ và quyền hiệu dụng không còn.
6. **Kiểm tra VPN:** Tài khoản/certificate và phiên liên quan đã ngừng theo yêu cầu.
7. **Kiểm tra service account:** Quyền quản trị của Leaver bị thu hồi; owner mới xác nhận credential cần xoay vòng hoặc thu hồi theo rủi ro mà không làm hỏng pipeline.
8. **Đọc lại và lưu vết:** Mỗi target có thời điểm readback, kết quả, owner. Chỉ đóng khi các hạng mục bắt buộc đạt.

### Giả sử tài khoản ứng dụng hóa đơn vẫn hoạt động

Trạng thái phải là **chưa hoàn tất**, ghi lỗi và người chịu trách nhiệm. Tùy chính sách và khả năng kỹ thuật, có thể cần biện pháp kiểm soát tạm như chặn ở tầng ứng dụng/mạng hoặc khóa credential liên quan trong khi sửa connector. Phải kiểm tra tác dụng thực tế và không nhầm “đã có biện pháp tạm” với “đã thu hồi đầy đủ”.

## 16. Hai tình huống khác cần phân tích

### Tình huống A — Nhà thầu kết thúc dự án A nhưng còn dự án B

Nhà thầu Minh làm song song dự án A và B. Hợp đồng A hết hạn, hợp đồng B còn hiệu lực ba tuần. Account tại IdP dùng chung cho cả hai dự án.

**Yêu cầu:** Xác minh hoàn tất Leaver cho engagement A mà không làm gián đoạn quyền của B.

**Cách xử lý:** Kiểm kê quyền gắn với từng engagement; tính quyền mong muốn theo B; thu hồi quyền A, token và quyền chia sẻ chỉ thuộc A. **Giữ account nếu vẫn cần cho B và đáp ứng điều kiện chính sách.** Hồ sơ đóng phải giải thích quyền nào được giữ vì B, quyền nào đã thu hồi vì A.

### Tình huống B — Ứng dụng legacy không có API thu hồi

Một ứng dụng nội bộ chỉ cho quản trị viên khóa user trực tiếp trên giao diện. IAM đã tạo ticket, người vận hành báo “đã thực hiện”, nhưng không có readback từ hệ thống.

**Yêu cầu:** Xác minh có thể đóng Leaver không?

**Cách xử lý:** Cần cơ chế bằng chứng được tổ chức chấp nhận, ví dụ kết quả tra cứu trạng thái account, log từ hệ thống, ảnh chụp trạng thái bảo vệ hoặc kiểm tra khác được phép và có thời điểm/người thực hiện. Nếu vẫn không có bằng chứng đủ tin cậy thì giữ `PENDING_VERIFICATION` hoặc xử lý ngoại lệ được phê duyệt. Một lời xác nhận không có bằng chứng không tự tương đương với thu hồi đã kiểm chứng.

## 17. Đo lường chất lượng xác minh hoàn tất

Các chỉ số nên đánh giá **kết quả thực sự**, không chỉ hoạt động thực hiện:

| Chỉ số | Định nghĩa gợi ý | Điều cần phân biệt |
|---|---|---|
| **Verified leaver completion rate** | Số biến cố đáp ứng toàn bộ tiêu chí bắt buộc / tổng biến cố đến hạn | Không tính ticket đã đóng nhưng còn target lỗi |
| **Time to verified revocation** | Từ mốc cần thu hồi đến khi kết quả cuối được xác minh | Có thể khác thời điểm gửi lệnh |
| **Residual access count** | Quyền còn hiệu lực không có căn cứ sau Leaver | Bao gồm direct grants và quyền kế thừa |
| **Target verification coverage** | Tỷ lệ target bắt buộc có bằng chứng readback thích hợp | Inventory thiếu làm số liệu sai |
| **Unresolved sessions/tokens** | Số phiên/credential thuộc phạm vi chưa xác định trạng thái | Phải phân biệt “không kiểm tra được” và “đã hết hiệu lực” |
| **Partial deprovision rate** | Tỷ lệ Leaver có ít nhất một đích lỗi/chờ xác minh | Đo theo ứng dụng/connector và nguyên nhân |
| **Exception aging** | Thời gian các ngoại lệ vẫn chưa được xử lý | Có owner, hạn và mức rủi ro |
| **Reactivation after closure** | Account/quyền tái xuất hiện sau khi đã đóng | Phát hiện luồng đồng bộ hoặc nguồn cũ |
| **Orphan account discovery** | Tài khoản không có identity/owner/engagement còn hợp lệ | Bao gồm ứng dụng legacy và danh tính máy |

Không có một SLA chung phù hợp cho mọi ngành và mức rủi ro. Tổ chức phải xác định **thời hạn thu hồi, thời hạn kiểm chứng và mức ưu tiên** theo chính sách, tính nhạy cảm tài nguyên, pháp lý và khả năng kỹ thuật. Việc kiểm chứng bị trễ cần được ghi nhận đúng, không chỉnh lại thời điểm sự kiện để khiến chỉ số trông đẹp hơn.

## 18. Bài tập tự kiểm tra

**Câu 1:** HR đã đánh dấu một người nghỉ việc, SCIM trả HTTP thành công, nhưng không có bằng chứng từ ứng dụng. Có thể đóng Leaver không?

**Đáp án gợi ý:** Chưa đủ nếu ứng dụng nằm trong phạm vi bắt buộc. Cần readback đáng tin về trạng thái account/quyền, hoặc xử lý theo chính sách ngoại lệ nếu không thể kiểm tra.

**Câu 2:** Account IdP đã disabled, nhưng personal access token vẫn gọi API được. Mục nào chưa đạt?

**Đáp án gợi ý:** Kiểm soát credential/token và quyền hiệu dụng ở ứng dụng/API chưa đạt. Phải thu hồi token hoặc chặn quyền theo cách được hỗ trợ rồi xác minh.

**Câu 3:** Người rời dự án A nhưng vẫn có hợp đồng B. Có nên disable toàn bộ identity?

**Đáp án gợi ý:** Chỉ làm vậy nếu chính sách và quan hệ hợp lệ yêu cầu. Phải phân biệt engagement và quyền, thu hồi các grant của A, giữ quyền của B có căn cứ và kiểm chứng.

**Câu 4:** Service account tiếp tục chạy sau khi người tạo account nghỉ việc. Điều đó có tự động là lỗi Leaver?

**Đáp án gợi ý:** Không nhất thiết. Cần đánh giá ownership, quyền quản trị của người nghỉ, các credential người đó có thể biết và việc xoay vòng/thu hồi theo rủi ro. Danh tính máy có thể tiếp tục hợp lệ với owner mới.

**Câu 5:** Đích trả trạng thái “inactive” nhưng session cũ vẫn có thể đọc báo cáo. Bằng chứng nào quan trọng hơn đối với mục tiêu chặn truy cập?

**Đáp án gợi ý:** Phải đánh giá khả năng truy cập thực tế và điều kiện của chính sách. Trạng thái account không tự thay thế bằng chứng ứng dụng/phiên đã ngừng cho phép quyền.

**Câu 6:** Có 12 ứng dụng bắt buộc, 11 đã PASS và 1 target `UNKNOWN`. Tỷ lệ hoàn tất nên là bao nhiêu?

**Đáp án gợi ý:** Biến cố Leaver chưa hoàn tất theo điều kiện “tất cả target bắt buộc đạt”. Có thể ghi tiến độ 11/12, nhưng không nên đánh dấu event `COMPLETED`.

## 19. Checklist xác minh hoàn tất Leaver

Dùng danh sách sau như một khung rà soát; cách áp dụng cụ thể theo chính sách từng tổ chức:

- [ ] **Nguồn và thời điểm:** Biến cố Leaver có thẩm quyền, đúng `personId`, đúng engagement và mốc hiệu lực.
- [ ] **Phạm vi:** Inventory account, ứng dụng, nhóm, role, quyền trực tiếp, đặc quyền, hệ thống vật lý và những target bắt buộc đã đầy đủ.
- [ ] **Nhiều engagement:** Những quyền còn hợp lệ được xác định rõ nguồn cấp; không xóa nhầm account hoặc giữ quyền không căn cứ.
- [ ] **IdP/SSO:** Account, nhóm và khả năng xác thực mới đã bị chặn theo chính sách; phiên SSO liên quan được đánh giá.
- [ ] **SCIM/API:** Mỗi hệ thống đích có trạng thái cập nhật và bằng chứng đọc lại, không chỉ log gửi lệnh.
- [ ] **Ứng dụng:** Các role nội bộ, ACL, quyền trực tiếp, nhóm lồng nhau, tài nguyên chia sẻ và authorization hiệu dụng đã được xem xét.
- [ ] **Session/token:** Phiên, refresh token, personal token, key, certificate và các đường truy cập độc lập được xử lý theo rủi ro và chính sách.
- [ ] **PAM/quyền nhạy cảm:** Quyền admin, JIT, vault, jump host và những phiên đặc quyền còn mở đã được kiểm tra.
- [ ] **Danh tính máy:** Chủ sở hữu service account đã được chuyển nếu cần; quyền/secret mà Leaver từng nắm giữ được đánh giá và xử lý.
- [ ] **Thiết bị/vật lý:** Badge, VPN/ZTNA, quyền thiết bị và những tài sản có đường truy cập đã được bàn giao/thu hồi phù hợp.
- [ ] **Lỗi và ngoại lệ:** Không có target bắt buộc `UNKNOWN`/`FAILED` bị che giấu; mọi ngoại lệ có owner, hạn xử lý, căn cứ và kiểm soát.
- [ ] **Bằng chứng:** Readback gắn đúng ID account, đúng target, đúng thời điểm, đủ độ tin cậy và có đường truy xuất kiểm toán.
- [ ] **Đóng quy trình:** Người có thẩm quyền xác nhận kết quả và lưu thời điểm, chính sách, trạng thái cuối; không nhầm “gửi lệnh” với “đã xác minh”.
- [ ] **Hậu kiểm:** Có cơ chế phát hiện quyền còn sót, account mồ côi hoặc quyền tái xuất hiện sau khi đóng.
- [ ] **Quyền riêng tư và lưu giữ:** Log/bản ghi được bảo vệ; dữ liệu phải lưu giữ được xử lý riêng với việc thu hồi quyền.

**Ghi nhớ:** **Xác minh hoàn tất Leaver** là bài kiểm tra cuối cùng cho toàn bộ vòng đời danh tính: tổ chức phải chứng minh rằng **đúng tài khoản và đúng quyền đã thực sự mất hiệu lực ở đúng hệ thống, tại thời điểm chính sách yêu cầu**. Quyết định đóng cần dựa trên **readback, kiểm chứng quyền hiệu dụng, quản lý phiên/token, xử lý ngoại lệ và bằng chứng kiểm toán**. Chỉ khi có những dữ kiện đó, IAM mới có cơ sở giảm quyền truy cập tồn dư sau giai đoạn Joiner–Mover–Leaver.
