# Thay đổi địa điểm trong Mover lifecycle: cập nhật danh tính, quyền và điều kiện truy cập

**Thay đổi địa điểm (location change)** là một biến cố thuộc **Mover lifecycle** khi nơi làm việc, cơ sở, khu vực phụ trách hoặc địa điểm được phép sử dụng tài nguyên của một danh tính thay đổi. Ví dụ, nhân viên chuyển từ văn phòng Hà Nội sang văn phòng Thành phố Hồ Chí Minh; nhà thầu chuyển sang cơ sở khách hàng khác; hoặc nhân sự làm việc tạm thời tại quốc gia khác theo thỏa thuận. Biến cố này có thể làm thay đổi **thuộc tính danh tính, quyền vào hệ thống, dữ liệu theo khu vực, truy cập mạng và ra vào cơ sở vật lý**, dù chức danh của người đó không đổi.

Trong **Identity and Access Management (IAM)**, một bản cập nhật địa chỉ đơn thuần không bảo đảm quyền đã đúng. Hệ thống cần biết **địa điểm nào là nguồn thông tin có thẩm quyền**, **thay đổi có hiệu lực khi nào**, **quyền nào cần cấp thêm và thu hồi**, **chính sách truy cập theo ngữ cảnh có còn phù hợp**, và **ứng dụng đích đã áp dụng thay đổi hay chưa**.

Bài học thuộc chương **Mover lifecycle** của mô-đun quản lý vòng đời danh tính **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung liên hệ mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh và tạo tài khoản lúc gia nhập đến điều chỉnh quyền khi chuyển địa điểm và thu hồi quyền truy cập tồn dư khi địa điểm hoặc quan hệ làm việc không còn hợp lệ. Những thành phần **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** cùng tham gia bảo đảm quyền thực tế được cập nhật chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **địa điểm công tác chính thức** với **vị trí truy cập mạng hoặc thiết bị tại thời điểm đăng nhập**.
2. Xác định các biến cố chuyển địa điểm thường gặp, nguồn dữ liệu và thời điểm hiệu lực của từng biến cố.
3. Tính **quyền cần thêm, quyền cần thu hồi và quyền giữ nguyên** khi người dùng chuyển cơ sở, khu vực hoặc quốc gia.
4. Thiết kế luồng đồng bộ thuộc tính qua IAM, IdP, SSO, SCIM/API và kiểm tra quyền tại ứng dụng.
5. Đánh giá tác động đến **RBAC, ABAC, conditional access, VPN/ZTNA, quyền ra vào vật lý, dữ liệu theo khu vực** và phiên truy cập.
6. Phát hiện sai lệch trạng thái, quyền địa điểm cũ còn hiệu lực và các rủi ro kiểm toán hoặc quyền riêng tư.
7. Đề xuất quy trình xử lý tình huống chuyển địa điểm vĩnh viễn, tạm thời hoặc làm việc từ xa.

## 2. “Địa điểm” trong IAM gồm nhiều khái niệm

Nếu cùng dùng một trường `location` cho mọi mục đích, hệ thống dễ đưa ra quyết định sai. Cần tách các loại thông tin:

| Khái niệm | Ví dụ | Nguồn dữ liệu thường gặp | Có thể tác động đến |
|---|---|---|---|
| **Địa điểm công tác chính thức** (*work location*) | Văn phòng Hà Nội | HR hoặc hệ thống quản lý nhà thầu | Quyền cơ sở, nhóm nội bộ, chính sách theo nơi làm việc |
| **Cơ sở/văn phòng được phân công** (*site assignment*) | Site `HCM-02` | HR, cơ sở vật chất, sponsor được ủy quyền | Badge, mạng nội bộ, máy in, phòng lab |
| **Khu vực nghiệp vụ** (*business region*) | Miền Nam | Hệ thống phân công kinh doanh hoặc owner dữ liệu | Phạm vi hồ sơ khách hàng, báo cáo, tenant |
| **Quốc gia làm việc có thẩm quyền** | Việt Nam | HR/hợp đồng và nguồn có thẩm quyền liên quan | Quy tắc truy cập xuyên biên giới, kiểm soát dữ liệu |
| **Địa điểm làm việc tạm thời** (*temporary assignment*) | Công tác tại Singapore 5 ngày | Đề nghị công tác/phê duyệt chính thức | Ngoại lệ có thời hạn, điều kiện truy cập |
| **Địa điểm hiện tại của phiên** | Địa chỉ IP được suy ra ở một khu vực | Tín hiệu mạng/thiết bị khi đăng nhập | Phát hiện bất thường, conditional access |
| **Địa chỉ liên lạc/cư trú** | Địa chỉ nhận thư | Hồ sơ cá nhân đã xác minh theo chính sách | Nghiệp vụ liên lạc, không mặc định cấp quyền |

**Nguyên tắc quan trọng:** Vị trí suy ra từ IP, GPS hoặc điểm truy cập Wi-Fi **không đồng nghĩa** địa điểm làm việc chính thức. IP có thể bị ảnh hưởng bởi VPN, proxy, mạng doanh nghiệp, thiết bị di động hoặc cơ sở dữ liệu định vị chưa chính xác. Tín hiệu vị trí phiên hữu ích cho đánh giá rủi ro nhưng không tự nó sửa được thuộc tính HR hoặc cho phép người dùng có quyền vào dữ liệu của khu vực khác.

Ví dụ: An được điều chuyển chính thức từ Hà Nội vào Thành phố Hồ Chí Minh, nhưng đang đăng nhập khi đi công tác tại Đà Nẵng. `assignedSite=HCM-02` vẫn có thể là thông tin hợp lệ cho quyền nghiệp vụ; còn vị trí mạng hiện tại có thể là một tín hiệu để đánh giá rủi ro phiên.

### Địa điểm là thuộc tính, không phải danh tính mới

Chuyển văn phòng thông thường **không phải tạo một người dùng mới**. Danh tính ổn định, lịch sử kiểm toán, tài khoản và phương thức xác thực có thể tiếp tục được sử dụng theo chính sách. Hệ thống cập nhật thuộc tính và quyền liên quan mà vẫn giữ khả năng truy vết **cùng một chủ thể trước và sau thay đổi**.

Cần tránh tạo hai identity cho cùng một người chỉ vì mã văn phòng hoặc tên đăng nhập có thay đổi. Nếu hệ thống cũ ràng buộc account với site, phải đánh giá cách **di chuyển hoặc liên kết account an toàn**, tránh tạo tài khoản mồ côi.

## 3. Những biến cố Mover có yếu tố địa điểm

| Biến cố | Bản chất thay đổi | Hệ quả IAM cần xem xét |
|---|---|---|
| **Chuyển văn phòng vĩnh viễn** | Nơi làm việc chính thức thay đổi | Thu hồi quyền cơ sở cũ, cấp quyền cơ sở mới |
| **Đổi khu vực phụ trách** | Vùng dữ liệu/nghiệp vụ thay đổi dù vẫn cùng văn phòng | Thay đổi ABAC scope, nhóm báo cáo, quyền khách hàng |
| **Công tác ngắn hạn** | Có mặt tại địa điểm khác trong khoảng thời gian được duyệt | Quyền khách/cơ sở tạm thời, TTL và điều kiện phiên |
| **Làm việc từ xa/hybrid** | Chính sách nơi làm việc thay đổi hoặc người dùng luân phiên địa điểm | Kiểm tra thiết bị, mạng và quyền truy cập theo chính sách |
| **Chuyển giữa các quốc gia** | Nơi công tác và bối cảnh quản trị dữ liệu thay đổi | Đánh giá chính sách xuyên biên giới, phạm vi dữ liệu và cấp phép |
| **Thay địa điểm của nhà thầu** | Cơ sở dự án hoặc phạm vi khách hàng thay đổi | Kiểm tra sponsor, site được phê duyệt, ngày hết hạn |
| **Địa điểm đóng cửa/đổi mã** | Thay đổi cấu trúc tổ chức, không nhất thiết thay người | Di chuyển mapping site và quyền phụ thuộc, tránh bỏ sót |
| **Tạm đình chỉ ra vào cơ sở** | Quyền vật lý bị giới hạn do sự kiện riêng | Xử lý badge và các hệ thống liên quan, không suy luận quyền số nếu không có chính sách |

Mỗi biến cố cần ghi rõ **địa điểm cũ, địa điểm mới, loại thay đổi, ngày hiệu lực, thời hạn nếu tạm thời và nguồn chấp thuận**. Với trường hợp công tác, một quyền tạm thời có thể tồn tại song song với quyền nơi làm việc chính trong thời hạn cho phép; còn chuyển vĩnh viễn thường yêu cầu rà soát và thu hồi quyền địa điểm cũ.

## 4. Nguồn thông tin có thẩm quyền và chất lượng dữ liệu

Mover theo địa điểm thường khởi đầu từ **HR**, hệ thống quản lý nhà thầu (VMS), quản lý cơ sở, hệ thống phân công dự án hoặc nguồn nghiệp vụ được chỉ định. Tổ chức cần phân định hệ thống nào **có thẩm quyền cập nhật từng thuộc tính**, thay vì chọn dữ liệu đến cuối cùng.

| Thuộc tính | Ví dụ | Câu hỏi cần xác minh |
|---|---|---|
| `personId` | `P-2048` | Có phải định danh ổn định của cùng cá nhân? |
| `previousSiteId` | `HN-01` | Trạng thái cũ đã được ghi nhận đáng tin cậy? |
| `newSiteId` | `HCM-02` | Site có tồn tại, đang hoạt động và được phép? |
| `businessRegion` | `south` | Khu vực nghiệp vụ có đổi theo site hay là thuộc tính riêng? |
| `effectiveAt` | Mốc thay đổi có múi giờ rõ | Quyền mới và quyền cũ phải xử lý vào thời điểm nào? |
| `temporaryUntil` | Ngày hết hạn công tác | Quyền tạm thời có tự thu hồi? |
| `approvalReference` | Mã quyết định điều chuyển | Ai chấp thuận và với phạm vi nào? |
| `eventVersion` | Phiên bản hoặc số thứ tự biến cố | Có nguy cơ sự kiện cũ ghi đè dữ liệu mới? |
| `sponsorId` | Chủ nhiệm dự án | Có cần phê duyệt lại với nhà thầu? |

Một ví dụ sự kiện nghiệp vụ đã được chuẩn hóa, **không phải schema chuẩn bắt buộc**:

~~~json
{
  "eventType": "WORK_LOCATION_CHANGED",
  "eventId": "EVT-3021",
  "personId": "P-2048",
  "oldSiteId": "HN-01",
  "newSiteId": "HCM-02",
  "effectiveAt": "2026-12-01T00:00:00+07:00",
  "permanent": true,
  "approvedBy": "M-117",
  "eventVersion": 8
}
~~~

Định dạng thời gian cần nhất quán theo múi giờ và mốc nghiệp vụ được chấp thuận. Nên giữ **định danh site chuẩn** tách khỏi tên hiển thị như “HCM”, “TP.HCM” hay “Ho Chi Minh City”; nếu không, việc so khớp bằng chuỗi tự do dễ gây lỗi.

**Chất lượng dữ liệu quyết định chất lượng quyền.** Nếu site mới chưa được ánh xạ trong danh mục địa điểm hoặc dữ liệu mâu thuẫn, IAM nên giữ yêu cầu ở trạng thái cần xử lý, không tự gán một site mặc định có quyền rộng.

## 5. Quy trình xử lý thay đổi địa điểm từ đầu đến cuối

Một mô hình thực tế gồm:

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền<br/>HR / VMS / site owner"] --> B["Nhận biến cố địa điểm<br/>ID, site cũ/mới, thời gian"]
    B --> C{"Hợp lệ, đúng chủ thể<br/>và đúng phiên bản?"}
    C -->|Chưa| X["Dừng / xử lý sai lệch<br/>không tự cấp quyền"]
    C -->|Có| D["Tính trạng thái và quyền mong muốn<br/>RBAC / ABAC / ngoại lệ"]
    D --> E["Xác định quyền cần thêm,<br/>cần thu hồi, giữ nguyên"]
    E --> F["Áp thay đổi vào IdP,<br/>nhóm, app, mạng và badge"]
    F --> G["Readback từng hệ thống<br/>quyền hiệu dụng và trạng thái"]
    G --> H{"Đã khớp trạng thái<br/>và mốc hiệu lực?"}
    H -->|Có| I["Lưu bằng chứng và thông báo<br/>Mover hoàn tất"]
    H -->|Chưa| J["Báo lỗi, theo dõi, đối soát<br/>theo chính sách"]
    J --> F
    I --> K["Rà soát định kỳ / Leaver<br/>thu hồi quyền tồn dư"]
~~~

### Bước 1 — Nhận và xác minh biến cố

Kiểm tra người chuyển địa điểm đang có trạng thái hợp lệ, thông tin sự kiện không lỗi thời, site mới có trong danh mục được công nhận và ngày hiệu lực được xác nhận. Với contractor, cần kiểm tra **engagement, sponsor và địa điểm được phép** còn hiệu lực.

Không nên để một sự kiện cũ đến trễ ghi đè site đã được cập nhật gần hơn. Dùng phiên bản từ nguồn, dấu thời gian đáng tin cậy, trạng thái hiện hành và cơ chế đối soát.

### Bước 2 — Xác định tác động đến quyền

Cần phân biệt quyền gắn với **vai trò**, **site**, **khu vực dữ liệu**, **điều kiện truy cập** và **ngoại lệ tạm thời**. Chuyển địa điểm không nhất thiết làm thay đổi toàn bộ vai trò, nhưng có thể làm thay đổi những quyền được suy ra từ thuộc tính.

Ví dụ, nhân viên kế toán vẫn giữ vai trò `finance_analyst`, nhưng quyền xem chứng từ của cơ sở `HN-01` phải chuyển thành quyền tương ứng của `HCM-02` nếu chính sách tổ chức quy định quyền dữ liệu theo cơ sở.

### Bước 3 — Lập kế hoạch thêm và thu hồi

Tránh mô hình **chỉ thêm nhóm site mới**. Một kế hoạch Mover phải tính cả quyền cần loại bỏ khỏi site cũ.

Nếu hệ thống phải hỗ trợ chuyển công việc không gián đoạn, có thể tổ chức việc cấp/thu hồi theo **mốc hiệu lực và cửa sổ được phê duyệt**, nhưng không tự kéo dài quyền nhạy cảm ngoài chính sách. Những thao tác phụ thuộc cần có chủ sở hữu và phương án xử lý thất bại.

### Bước 4 — Thực thi qua hệ thống liên quan

Tùy hệ thống, có thể gồm:

- Cập nhật thuộc tính site/khu vực tại IAM và IdP.
- Điều chỉnh nhóm hoặc role điều khiển quyền ứng dụng.
- Đồng bộ thuộc tính, user/group qua SCIM hoặc API phù hợp.
- Sửa phạm vi truy cập dữ liệu nghiệp vụ, phân vùng hoặc tenant.
- Cập nhật VPN, ZTNA, chính sách thiết bị và truy cập mạng theo vị trí làm việc được phê duyệt.
- Cấp quyền ra vào cơ sở mới và thu hồi quyền badge/cơ sở cũ.
- Rà soát quyền chia sẻ trực tiếp, quyền trong repo, môi trường cloud, hệ thống vận hành hoặc công cụ đặc thù của site.

### Bước 5 — Đối soát và thông báo

Chỉ tuyên bố hoàn tất khi các đích bắt buộc đã được xác minh. Nếu IdP đã cập nhật nhưng ứng dụng chưa thay đổi quyền, trạng thái tổng hợp vẫn là **đang đồng bộ hoặc lỗi một phần**.

Người dùng cần được hướng dẫn nơi làm việc mới sẽ dùng những ứng dụng/kết nối nào và khi nào quyền mới có hiệu lực. Helpdesk cần thấy trạng thái từng đích, không chỉ một nhãn “đã chuyển địa điểm”.

## 6. Tính lại quyền: thêm, giữ và thu hồi

Giả sử trước khi chuyển, một nhân viên có các quyền:

~~~text
Hiện tại:
  base.email.use
  finance.invoice.read@HN-01
  building.entry@HN-01
  network.internal@HN-01

Quyền mong muốn sau chuyển:
  base.email.use
  finance.invoice.read@HCM-02
  building.entry@HCM-02
  network.internal@HCM-02

Quyền thêm:
  finance.invoice.read@HCM-02
  building.entry@HCM-02
  network.internal@HCM-02

Quyền thu hồi:
  finance.invoice.read@HN-01
  building.entry@HN-01
  network.internal@HN-01

Quyền giữ:
  base.email.use
~~~

Về khái niệm:

~~~text
add    = desired - effective
revoke = effective - desired
keep   = desired ∩ effective
~~~

Nhưng **effective access** có thể hình thành từ nhiều nguồn: nhóm RBAC, điều kiện ABAC, gán trực tiếp, nhóm lồng nhau, chia sẻ tài nguyên hoặc ngoại lệ có hạn. Không nên xóa một quyền hợp lệ đang được một **engagement khác** bảo trợ. Tốt nhất quản lý **nguồn cấp quyền (grant provenance)** để phân biệt quyền site cũ cần thu hồi với quyền độc lập vẫn hợp lệ.

### 6.1. RBAC theo site

Tổ chức có thể dùng role `site_hn_staff` và `site_hcm_staff`. Mover cần thay role theo quyết định của nguồn có thẩm quyền. RBAC dễ hiểu nhưng có thể sinh quá nhiều role nếu tổ hợp site × phòng ban × dự án × môi trường quá lớn.

### 6.2. ABAC theo thuộc tính

ABAC có thể dùng `assignedSite`, `businessRegion`, `engagementStatus`, thuộc tính tài nguyên và ngữ cảnh để giới hạn quyền. Điều này hữu ích khi vai trò công việc không đổi nhưng phạm vi dữ liệu đổi theo địa điểm.

Ví dụ **mã giả**, không phải policy triển khai hoàn chỉnh:

~~~python
def can_view_site_document(user, document, session, now):
    if user.engagement_status != "active":
        return False
    if not session.is_valid or not session.meets_assurance_policy:
        return False
    if "finance_analyst" not in user.roles:
        return False
    if user.assigned_site_id is None:
        return False
    if user.assignment_effective_at > now:
        return False
    if document.site_id != user.assigned_site_id:
        return False
    if not document.is_approved_for_finance_role:
        return False
    return True
~~~

Nếu người dùng đã đổi sang `HCM-02`, request đọc chứng từ của `HN-01` không còn đáp ứng điều kiện site, trừ khi một chính sách hợp lệ khác cho phép. ABAC cần được **thực thi ở API và truy vấn dữ liệu**, không chỉ dựa vào nút giao diện.

### 6.3. Không suy diễn site từ vai trò một cách máy móc

Một người giữ chức danh `regional_manager` có thể cần nhiều site; một nhà thầu kỹ thuật có thể chỉ được vào phòng máy của site được bảo trợ. Quyền phải bám **phạm vi nhiệm vụ thực sự**, chính sách dữ liệu và các phê duyệt, không chỉ ánh xạ “mỗi người = đúng một site” nếu nghiệp vụ cho phép nhiều site.

## 7. IdP, SSO, SCIM và application entitlement

**IdP** thường lưu nhóm hoặc thuộc tính hỗ trợ đăng nhập, còn **SSO** liên kết xác thực đến ứng dụng. **SCIM** hỗ trợ đồng bộ user/group khi đích triển khai tương thích. Tuy nhiên, thay đổi site không tự động cập nhật mọi quyền chỉ vì một trường tại IdP đã đổi.

| Lớp | Ví dụ thay đổi | Bằng chứng cần kiểm tra |
|---|---|---|
| **HR/VMS** | `assignedSite=HCM-02` hiệu lực từ ngày mới | Nguồn, quyết định và thời gian |
| **IAM policy** | Quyền HN bị bỏ, HCM được tính theo chính sách | Bộ quyền mong muốn và lý do |
| **IdP** | Nhóm site hoặc thuộc tính liên quan đổi | Account/nhóm/claim hiện hành |
| **SCIM/API** | Thuộc tính hoặc nhóm được đồng bộ tới ứng dụng | Kết quả readback của account đích |
| **Ứng dụng** | Quyền dữ liệu theo site và hành động được cập nhật | Kiểm tra authorization thực tế |
| **SSO/session** | Token/claim cũ có thể vẫn chứa site trước đó | Chính sách làm mới phiên, thời gian token, thu hồi khi cần |
| **VPN/ZTNA/badge** | Mạng và quyền cơ sở thay đổi | Trạng thái thực tế ở thiết bị/hệ thống ra vào |

SCIM User có thể có thông tin địa chỉ theo schema, nhưng **địa chỉ liên lạc không nhất thiết là thuộc tính site có thẩm quyền để phân quyền**. Các trường tùy biến như `assignedSiteId` cần schema extension, mapping hoặc API phù hợp từng nền tảng. Không suy đoán khả năng đồng bộ của một ứng dụng chỉ từ việc nó “có SCIM”.

Đặc biệt, một **SSO token đã phát hành** có thể phản ánh thuộc tính trước khi chuyển. Cần xác định khi nào ứng dụng kiểm tra lại quyền/thuộc tính, thời hạn token, cơ chế cập nhật phiên và mức rủi ro. Với quyền nhạy cảm bị thu hồi, không thể chỉ chờ người dùng đăng nhập lại nếu chính sách yêu cầu ngừng truy cập sớm hơn.

## 8. Conditional access và tín hiệu vị trí đăng nhập

**Conditional access** áp điều kiện truy cập dựa trên ngữ cảnh như mức xác thực, thiết bị, mạng, rủi ro phiên và đôi khi khu vực kết nối. **Location change chính thức** có thể yêu cầu cập nhật quy tắc truy cập theo địa điểm, nhưng không nên nhầm với **phát hiện thay đổi vị trí IP**.

Ví dụ:

- Nhân viên đã chuyển văn phòng từ Hà Nội đến HCM: quyền cơ sở mới được cấp theo nguồn HR; đăng nhập qua một IP tại Hà Nội trong chuyến công tác chưa đủ để kết luận dữ liệu HR sai.
- Một phiên xuất hiện từ mạng không quen thuộc: IdP có thể yêu cầu xác thực bổ sung hoặc chặn theo chính sách, dù site công tác không thay đổi.
- Tín hiệu “di chuyển bất khả thi” (*impossible travel*) là **dấu hiệu rủi ro cần đánh giá**; VPN, proxy, định vị IP sai hoặc tuyến mạng có thể tạo cảnh báo giả.

| Tín hiệu | Vai trò phù hợp | Không nên dùng để |
|---|---|---|
| Site HR được phê duyệt | Thuộc tính nghiệp vụ chính thức | Đoán vị trí vật lý hiện tại chính xác |
| Quốc gia công tác được xác nhận | Đánh giá chính sách dữ liệu và quyền theo phạm vi | Thay thế kiểm tra quyền trong ứng dụng |
| IP/geolocation của phiên | Tín hiệu điều kiện truy cập và phát hiện bất thường | Tự đổi phòng ban/site trong HR |
| Thiết bị được quản lý | Điều kiện bảo vệ truy cập | Chứng minh vị trí làm việc theo hợp đồng |
| Kết quả MFA/step-up | Tăng độ tin cậy phiên theo chính sách | Tự cấp quyền dữ liệu site khác |

Tổ chức cần cân bằng khả năng phòng vệ với **quyền riêng tư và tính chính xác của tín hiệu vị trí**. Không thu thập vị trí GPS liên tục chỉ vì có yêu cầu phân quyền theo site nếu mục tiêu có thể đạt được bằng dữ liệu phân công được phê duyệt.

## 9. Truy cập vật lý, mạng và tài nguyên theo site

Thay đổi địa điểm có thể tác động đồng thời đến truy cập số và vật lý:

| Tài nguyên | Có thể cần thêm | Có thể cần thu hồi |
|---|---|---|
| **Thẻ ra vào/khóa cửa** | Cửa, tầng, phòng lab tại cơ sở mới | Cửa và khu vực hạn chế của cơ sở cũ |
| **Mạng doanh nghiệp/VPN/ZTNA** | Chính sách kết nối đến dịch vụ mới phù hợp vai trò | Nhóm mạng/VPN cũ chỉ dùng cho site trước |
| **Máy chủ và hệ thống vận hành** | Hệ thống phụ trách tại site mới | Quyền SSH, console, jump host cũ |
| **Ứng dụng nghiệp vụ** | Dữ liệu hoặc workflow vùng mới | Khách hàng, chứng từ, ticket vùng cũ |
| **Chia sẻ tài liệu/kho mã** | Nhóm/không gian dự án mới | Truy cập tài liệu site trước không còn hợp lệ |
| **Thiết bị và ngoại vi** | Máy in, ứng dụng họp, thiết bị phòng lab theo nhu cầu | Thiết bị chỉ gắn với site cũ |

**Badge và account số thường do các hệ thống khác nhau quản lý.** Một Mover có thể đã được cập nhật trong IdP nhưng thẻ ra vào cơ sở cũ vẫn hoạt động. Cần xác định **owner của từng hệ thống**, cách nhận sự kiện và điều kiện readback.

Ngược lại, không nhất thiết phải thu hồi mọi quyền truy cập mạng khi đổi văn phòng; một số quyền là quyền tổ chức toàn cầu. Chỉ thay đổi những phần mà chính sách và căn cứ nghiệp vụ gắn với site.

## 10. Chuyển địa điểm vĩnh viễn, tạm thời và đa địa điểm

### 10.1. Chuyển vĩnh viễn

**Tình huống:** Nhân viên An từ văn phòng `HN-01` chuyển tới `HCM-02` vào ngày 01/12.

Quy trình mong muốn:

1. HR xác nhận điều chuyển và mốc hiệu lực.
2. IAM tính nhóm/quyền site mới, thu hồi nhóm/quyền chỉ hợp lệ ở site cũ.
3. Cập nhật thuộc tính site, danh sách ứng dụng, VPN và badge theo từng hệ thống.
4. Xác nhận quyền dữ liệu HCM hoạt động đúng, quyền HN đã hết hiệu lực nếu không còn căn cứ.
5. Thông báo cách truy cập cơ sở mới và trạng thái các hệ thống cần người dùng kích hoạt lại.

Việc cấp trước một số tài nguyên để sẵn sàng ngày đầu phải được kiểm soát về **thời điểm có hiệu lực**; không mặc nhiên có khoảng trùng quyền dài ngày.

### 10.2. Công tác ngắn hạn

**Tình huống:** An làm việc ba ngày tại văn phòng Hà Nội rồi trở lại HCM.

Ở đây **site công tác chính thức có thể không đổi**. Tổ chức có thể cấp quyền thẻ khách hoặc quyền phòng họp tại HN với thời hạn ngắn, thay vì gán lại tất cả quyền nghiệp vụ theo site và rồi đảo ngược.

Các thuộc tính tạm thời nên có **người phê duyệt, phạm vi, thời điểm bắt đầu, thời điểm kết thúc và kiểm tra thu hồi**. Khi công tác kết thúc sớm, cần cơ chế xử lý thu hồi trước hạn.

### 10.3. Làm việc tại nhiều cơ sở

Người hỗ trợ đa địa điểm có thể có `allowedSites={HN-01,HCM-02}` theo nhu cầu đã xác minh. Việc có nhiều site hợp lệ phải là một **quy tắc nghiệp vụ có căn cứ**, không phải kết quả tích lũy nhóm sau nhiều lần chuyển địa điểm.

Cần kiểm tra quyền hiệu dụng ở từng site, tránh việc vô tình cho đọc dữ liệu toàn vùng chỉ vì được phép vào nhiều tòa nhà.

### 10.4. Chuyển quốc gia hoặc truy cập xuyên biên giới

Thay đổi quốc gia có thể liên quan đến **quy định hợp đồng, quyền truy cập dữ liệu, chính sách lưu trữ/xử lý dữ liệu, phân loại thông tin và cam kết với khách hàng**. Không có một quy tắc pháp lý chung áp dụng cho mọi tổ chức và mọi bộ dữ liệu. IAM nên nhận chính sách từ bộ phận có thẩm quyền và **thực thi điều kiện truy cập đã được xác nhận**, thay vì tự suy luận “quốc gia mới luôn được/chưa được” từ tên quốc gia.

Nếu quyền dữ liệu ở site mới cần phê duyệt bổ sung, phải thể hiện trạng thái rõ ràng và không tự cấp quyền vượt điều kiện chỉ để tránh gián đoạn.

## 11. Xử lý tài khoản dịch vụ và danh tính máy

**Service account** không có địa điểm công tác như một nhân viên, nhưng **địa điểm triển khai workload** hoặc site của tài nguyên có thể thay đổi. Ví dụ, một agent giám sát được chuyển từ cơ sở HN sang HCM hoặc một dịch vụ được chạy ở region đám mây khác.

Trong trường hợp đó, cần kiểm tra:

- **Owner của workload** và mục đích dịch vụ có còn hợp lệ không?
- Quyền truy cập endpoint, mạng, bucket hoặc tài nguyên cloud cũ có còn cần thiết không?
- Credential, token và workload identity có gắn sai môi trường hoặc site không?
- Có cần cập nhật chính sách kết nối, firewall, DNS, endpoint hoặc quyền truy cập dữ liệu theo vùng không?
- Log và bằng chứng kiểm toán có thể truy vết tới workload/owner chứ không chỉ một tên tài khoản chung không?

Không tự đổi thuộc tính HR của con người để phản ánh vị trí máy chủ. Đối với service account, **nguồn có thẩm quyền** thường là hệ thống quản lý dịch vụ, hạ tầng hoặc owner kỹ thuật; vòng đời quyền máy đến máy cần vận hành độc lập nhưng có thể liên kết với Mover/Leaver của người từng sở hữu credential.

## 12. Lỗi thường gặp khi xử lý location change

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Người dùng đã chuyển văn phòng nhưng vẫn vào phòng lab cũ | Badge chưa được thu hồi | Đồng bộ hệ thống ra vào, đọc lại quyền cửa |
| Xem được dữ liệu cả vùng cũ lẫn vùng mới | Chỉ thêm nhóm/role, không tính lại quyền | Tính lại quyền mong muốn và đối soát nguồn grant |
| Một ứng dụng vẫn hiện site cũ | SCIM/API không đồng bộ hoặc dữ liệu ứng dụng cache | Kiểm tra mapping, lỗi tích hợp và cơ chế làm mới |
| Đăng nhập SSO được nhưng chức năng nghiệp vụ bị từ chối | Claim hoặc account ứng dụng chưa cập nhật | Xác định khác biệt authentication/provisioning/authorization |
| Người đi công tác bị đổi site HR sai | Dùng IP hoặc GPS như nguồn chính thức | Phân biệt thuộc tính phân công và vị trí phiên |
| Công tác kết thúc nhưng quyền cửa tạm thời vẫn còn | Thiếu expiry hoặc quy trình thu hồi | TTL, owner và xác minh sau hết hạn |
| Chuyển site tạo tài khoản thứ hai | Mã site được đưa vào khóa identity thiếu kiểm soát | Dùng định danh ổn định và mapping account |
| Sự kiện cũ ghi đè site mới | Không kiểm tra phiên bản/sự kiện đến trễ | Kiểm tra current state và ordering |
| Chuyển quốc gia nhưng quyền dữ liệu giữ nguyên không xét chính sách | Thiếu đánh giá tác động theo tài nguyên | Chủ dữ liệu/chính sách quyết định, IAM thực thi |
| Quyền bị thu hồi trong nhóm nhưng phiên cũ vẫn dùng được | Ứng dụng giữ claim/token cũ | Xác định cơ chế token/session và giới hạn thu hồi |

**Không nên kết luận “đã xong” chỉ dựa vào trạng thái HR hoặc IdP.** Một site change chỉ hoàn tất khi những hệ thống thuộc phạm vi phải thay đổi đã nhận và thực thi đúng quyền mới.

## 13. Kiểm toán và đối soát trong Mover địa điểm

Bản ghi kiểm toán nên đủ để trả lời:

1. **Ai** chuyển địa điểm, identity và account nào bị tác động?
2. **Ai xác nhận** và **nguồn nào** có thẩm quyền cho địa điểm mới?
3. **Khi nào** biến cố có hiệu lực và ở múi giờ nào?
4. **Những quyền nào đã thêm, thu hồi, giữ nguyên**, dựa trên chính sách hoặc phê duyệt nào?
5. **Hệ thống nào** đã xử lý và trả về kết quả nào?
6. **Có lỗi một phần, ngoại lệ, token cũ hoặc quyền trực tiếp nào** cần tiếp tục xử lý?
7. **Kết quả cuối** ở từng ứng dụng, mạng và thẻ ra vào đã được đọc lại chưa?

Nên liên kết audit trail giữa **ID biến cố Mover → identity → grant/revoke decisions → target account → readback**. Tránh ghi token, mật khẩu, thông tin giấy tờ hoặc dữ liệu vị trí nhạy cảm không cần thiết vào log.

Một số chỉ số vận hành:

| Chỉ số | Ý nghĩa |
|---|---|
| **Mover completion rate** | Tỷ lệ thay đổi site đã triển khai và xác minh đủ hệ thống bắt buộc |
| **Time to correct access** | Từ mốc hiệu lực đến khi quyền địa điểm mới dùng được và quyền cũ cần thu hồi đã hết |
| **Residual location access** | Quyền thuộc site cũ không còn căn cứ nhưng vẫn hiệu lực |
| **Failed target updates** | Số ứng dụng/VPN/badge bị lỗi hoặc chưa đồng bộ |
| **Temporary access overdue** | Quyền site tạm thời đã hết hạn nhưng chưa xác nhận thu hồi |
| **Unexpected location policy denials** | Các lần từ chối do sai mapping hoặc dữ liệu thiếu, cần phân tích nguyên nhân |
| **Orphan site assignments** | Nhóm/site không còn owner hoặc không ánh xạ tới danh mục địa điểm |

Các ngưỡng/SLA phụ thuộc mức nhạy cảm, nhu cầu nghiệp vụ, khả năng kỹ thuật và chính sách; không tự áp một con số chung cho mọi doanh nghiệp.

## 14. Tình huống thực hành: chuyển Hà Nội vào Thành phố Hồ Chí Minh

**Bối cảnh:** Mai thuộc bộ phận hỗ trợ khách hàng. Từ ngày 15/12, Mai chuyển công tác chính thức từ `HN-01` sang `HCM-02`, tiếp tục giữ vai trò `support_agent` nhưng phụ trách nhóm khách hàng miền Nam. Mai đang có quyền vào hệ thống ticket khu vực Bắc, một phòng hỗ trợ tại văn phòng HN và nhóm VPN riêng của cơ sở đó.

### Cách xử lý chưa đúng

- Chỉ sửa trường `office=HCM` trong hồ sơ người dùng.
- Giữ toàn bộ role ticket miền Bắc và badge HN.
- Thêm nhóm HCM để Mai có thể bắt đầu làm việc.
- Không kiểm tra application authorization; chỉ nhìn IdP và kết luận hoàn tất.
- Khi người dùng báo vẫn thấy khách hàng miền Bắc, cho rằng đó là “dữ liệu cache” mà không điều tra quyền hiệu dụng.

Hệ quả là Mai có thể tích lũy **quyền dữ liệu và quyền vật lý không còn thuộc trách nhiệm**.

### Cách xử lý có kiểm soát

1. **Nguồn:** HR phát sự kiện có định danh Mai, site cũ/mới và mốc hiệu lực. Hệ thống phân công khách hàng xác nhận region mới.
2. **Phân tích:** IAM giữ vai trò `support_agent`, tính quyền ticket `region=south`, quyền site `HCM-02`; đánh dấu quyền Bắc/HN không còn căn cứ.
3. **Thực thi:** Cập nhật nhóm/thuộc tính tại IdP, đồng bộ ứng dụng ticket qua cơ chế hỗ trợ; cập nhật chính sách VPN và badge.
4. **Xác minh:** Đọc lại quyền ticket, kiểm tra dữ liệu thuộc region miền Nam có thể truy cập đúng, dữ liệu Bắc bị từ chối nếu không còn lý do hợp lệ; kiểm chứng quyền cửa cũ đã bị thu hồi.
5. **Thông báo:** Cho Mai biết thời điểm bắt đầu sử dụng tài nguyên HCM, cách truy cập ứng dụng và kênh hỗ trợ nếu còn lỗi.
6. **Theo dõi:** Nếu một target chưa cập nhật, ghi trạng thái lỗi một phần, owner và phương án khắc phục; không báo Mover hoàn tất.
7. **Hậu kiểm:** Rà soát quyền chia sẻ trực tiếp hoặc quyền ngoại lệ còn gắn với HN, cùng các phiên/token có thể giữ thông tin cũ.

Nếu Mai có nhiệm vụ được duyệt tiếp tục hỗ trợ một số ticket Bắc, cần một **grant riêng có phạm vi và thời hạn** thay vì giữ nguyên mọi quyền Bắc do vai trò cũ.

## 15. Bài tập tự kiểm tra

### Tình huống A — Di chuyển IP, không di chuyển nơi công tác

Một nhân viên vẫn làm ở văn phòng Hà Nội nhưng kết nối qua VPN có IP hiển thị ở Singapore.

**Câu hỏi:** Có nên cập nhật `assignedSite` sang Singapore và cấp quyền của site đó?

**Gợi ý:** Không. IP là tín hiệu ngữ cảnh của phiên; location chính thức phải đến từ nguồn có thẩm quyền. Có thể đánh giá rủi ro đăng nhập theo chính sách mà không thay đổi quyền nghiệp vụ.

### Tình huống B — Chuyển site và quyền dữ liệu tồn dư

Một analyst chuyển từ site A sang site B, nhưng cả hai nhóm dữ liệu vẫn còn trong IdP.

**Câu hỏi:** Vì sao chỉ thấy nhóm B đã xuất hiện chưa đủ để kết luận thành công?

**Gợi ý:** Mover cần kiểm tra quyền hiệu dụng từ cả hai nhóm và các nguồn grant khác, thu hồi quyền site A không còn căn cứ, rồi kiểm chứng ở ứng dụng thực tế.

### Tình huống C — Công tác một tuần

Một kỹ sư đến cơ sở khác trong bảy ngày để bảo trì máy móc. Quản lý muốn cấp badge vào phòng thiết bị trong tuần đó.

**Câu hỏi:** Có nên đổi nơi làm việc chính thức và mọi quyền dữ liệu sang site mới?

**Gợi ý:** Thường nên xét đây là **quyền tạm thời có thời hạn** gắn với nhiệm vụ, chứ không suy ra cần Mover vĩnh viễn. Cần phê duyệt, phạm vi, TTL và xác nhận thu hồi.

### Tình huống D — SCIM báo thành công nhưng app vẫn hiện dữ liệu cũ

Sau điều chuyển, hệ thống IAM đã cập nhật trường site ở IdP và gửi yêu cầu đồng bộ. Ứng dụng vẫn cho phép nhân viên xem báo cáo của site trước.

**Câu hỏi:** Phải kiểm tra tiếp những gì?

**Gợi ý:** Kiểm tra mapping thuộc tính sang ứng dụng, role/quyền hiệu dụng, policy thực thi ở API, cache, token/phiên, cấp trực tiếp và kết quả readback. Việc gửi lệnh thành công không thay thế kiểm chứng authorization.

### Tình huống E — Hai engagement song song

Một contractor kết thúc nhiệm vụ ở site A nhưng vẫn hỗ trợ site B theo hợp đồng khác đang có hiệu lực.

**Câu hỏi:** Có thể vô hiệu hóa toàn bộ identity hoặc xóa tất cả quyền không?

**Gợi ý:** Cần xác định quyền nào dựa trên engagement A và quyền nào vẫn hợp lệ theo B, sau đó thu hồi phần hết căn cứ. Tách identity khỏi engagement giúp tránh thu hồi sai.

## 16. Checklist cho quy trình thay đổi địa điểm

- [ ] **Nguồn:** Đã xác minh sự kiện Mover từ HR/VMS hoặc nguồn có thẩm quyền, không suy từ IP/GPS?
- [ ] **Danh tính:** Identity ổn định và mapping account đúng người, không tạo trùng do đổi site?
- [ ] **Ngữ nghĩa:** Đã phân biệt nơi làm việc, khu vực nghiệp vụ, công tác tạm thời và vị trí phiên?
- [ ] **Thời gian:** Có mốc hiệu lực, múi giờ, thời hạn và phiên bản biến cố phù hợp?
- [ ] **Phạm vi:** Đã xác định site cũ/mới, dự án, vùng dữ liệu, owner và ngoại lệ hợp lệ?
- [ ] **Quyền:** Đã tính cả quyền cần **thêm, giữ và thu hồi**, gồm quyền trực tiếp và kế thừa?
- [ ] **Chính sách:** RBAC/ABAC/SoD và điều kiện truy cập vẫn phù hợp với vai trò/nhiệm vụ mới?
- [ ] **Đồng bộ:** IdP, SCIM/API, app, VPN/ZTNA và badge liên quan đều có owner và trạng thái?
- [ ] **Phiên:** Đã xét hiệu lực token, cache thuộc tính và việc thu hồi truy cập nhạy cảm khi cần?
- [ ] **Bảo vệ dữ liệu:** Không suy cấp phép xuyên biên giới, không thu thập vị trí quá mức?
- [ ] **Readback:** Đã xác minh quyền thực tế tại từng đích và phân biệt lỗi một phần?
- [ ] **Kiểm toán:** Có nguồn, phê duyệt, ID biến cố, thay đổi quyền và kết quả kiểm chứng?
- [ ] **Vòng đời:** Đã lập cơ chế rà soát quyền địa điểm cũ và xử lý Leaver về sau?
- [ ] **Danh tính máy:** Nếu workload/site triển khai đổi, đã rà soát owner và quyền của service account riêng?

**Ghi nhớ:** **Thay đổi địa điểm** là một biến cố **Mover lifecycle** tác động đến nhiều lớp IAM. Muốn quản lý đúng, cần cập nhật thuộc tính địa điểm từ **nguồn đáng tin**, tính lại **quyền theo vai trò và ngữ cảnh**, thực thi **cấp mới và thu hồi quyền cũ** qua IdP, SSO, SCIM, ứng dụng, mạng và hệ thống vật lý, rồi **đối soát trạng thái thực tế**. Chính việc đọc lại và xử lý quyền còn sót mới giúp giảm **quyền truy cập tồn dư** xuyên suốt vòng đời Joiner–Mover–Leaver.
