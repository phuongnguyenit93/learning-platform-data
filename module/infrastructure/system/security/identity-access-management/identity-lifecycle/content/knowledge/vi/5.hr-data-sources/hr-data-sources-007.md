# Location: thuộc tính địa điểm trong nguồn dữ liệu nhân sự phục vụ IAM lifecycle

Trong **Identity and Access Management (IAM)**, **Location** là thông tin về địa điểm hoặc phạm vi làm việc được tổ chức ghi nhận cho một nhân sự. Ví dụ, hồ sơ HRIS (Human Resources Information System) có thể xác định một nhân viên thuộc văn phòng **Hồ Chí Minh**, làm việc tại một cơ sở cụ thể, thuộc quốc gia **Việt Nam**, hoặc được quản lý theo mô hình **remote/hybrid**. IAM sử dụng dữ liệu này cùng với trạng thái nhân sự, vai trò, phòng ban và chính sách để xác định việc **tạo tài khoản, cấp quyền, thay đổi quyền và thu hồi quyền**.

Địa điểm là một thuộc tính dễ bị hiểu sai. **Địa điểm làm việc được HR ghi nhận** không nhất thiết là **vị trí thực tế của thiết bị tại thời điểm đăng nhập**, **địa chỉ cư trú**, **nơi đặt dữ liệu**, hoặc **đơn vị pháp lý sử dụng lao động**. Phân biệt các khái niệm này là điều kiện cần để triển khai vòng đời danh tính **Joiner–Mover–Leaver (JML)** an toàn và có thể kiểm toán.

Bài học thuộc chương **Nguồn dữ liệu nhân sự**, tập trung vào việc thu thập, định nghĩa, chuẩn hóa, đồng bộ và sử dụng thuộc tính Location trong IAM. Các ví dụ minh họa sự liên kết giữa **HRIS → IAM/IGA → IdP/Directory → SSO/SCIM → ứng dụng đích**, cùng mô hình quyền **RBAC/ABAC** và cơ chế giảm **quyền truy cập tồn dư**.

## 1. Location trả lời câu hỏi gì?

Tùy chính sách tổ chức, Location có thể được dùng để trả lời:

- Nhân viên **thuộc văn phòng/cơ sở làm việc nào** để nhận thiết bị, dịch vụ, danh sách liên lạc hoặc nhóm truy cập nội bộ?
- Người đó **được phép sử dụng những tài nguyên chỉ dành cho một địa điểm** nào, chẳng hạn hệ thống điều hành tòa nhà hoặc máy in tại cơ sở?
- Một sự kiện **chuyển văn phòng/chuyển quốc gia làm việc** có cần thay đổi entitlement hoặc kích hoạt phê duyệt bổ sung không?
- Ai là **đơn vị vận hành/owner** tại địa điểm chịu trách nhiệm xác minh quyền, tài sản hoặc tài khoản?
- Dữ liệu nhân sự ghi nhận tại Location nào; thông tin có **hiệu lực từ ngày nào** và có đủ đáng tin để đưa vào chính sách không?

Location thường là **một đầu vào của chính sách**, không phải kết luận rằng người có địa điểm X phải có mọi quyền của X. Quyền cuối cùng còn phụ thuộc chức danh, đơn vị, loại hợp đồng, trạng thái làm việc, phạm vi dự án, nhu cầu thực tế và phê duyệt theo mức nhạy cảm.

### 1.1. Sáu ý nghĩa khác nhau của “địa điểm”

| Thuật ngữ | Ý nghĩa | Có nên dùng thay cho work location trong IAM? |
| --- | --- | --- |
| **Work location / Assigned location** | Địa điểm làm việc được HR hoặc nguồn có thẩm quyền chính thức gán cho nhân sự. | **Có thể**, khi được định nghĩa và duy trì đúng quy trình. |
| **Office / Site / Facility** | Cơ sở vật lý cụ thể, ví dụ tòa nhà hoặc chi nhánh; có site code riêng. | Phù hợp với quyền theo cơ sở, nhưng không thay thế mọi thông tin nhân sự khác. |
| **Work country / Region** | Quốc gia hoặc vùng làm việc theo hồ sơ nghiệp vụ. | Hữu ích cho phân vùng dịch vụ/chính sách phù hợp; không mặc nhiên là vị trí hiện tại. |
| **Remote / Hybrid work arrangement** | Hình thức làm việc từ xa, kết hợp, hoặc tại văn phòng. | Là **thuộc tính khác**; nên được mô hình hóa riêng nếu chính sách cần. |
| **Residential / Mailing address** | Nơi cư trú hoặc địa chỉ liên hệ/gửi thư. | **Không**; đây là dữ liệu cá nhân với mục đích xử lý riêng. |
| **Current / Session location** | Vị trí được suy ra ở thời điểm truy cập, ví dụ IP, tín hiệu thiết bị hoặc mạng; có độ tin cậy và sai số nhất định. | **Không**; thuộc ngữ cảnh xác thực/rủi ro, không phải thuộc tính HR chính thức. |

Ví dụ, nhân viên được gán **site HCM-01**, có mô hình làm việc **hybrid**, đang công tác tại **Hà Nội** và có địa chỉ cư trú ở một tỉnh khác. Bốn giá trị này có thể cùng đúng. Nếu lấy vị trí IP hoặc địa chỉ cá nhân để ghi đè site trong HRIS, IAM có thể vô tình thu hồi quyền văn phòng hợp lệ hoặc cấp quyền sai.

**Phân biệt thêm:** Location của nhân viên không tự quyết định **data residency** (nơi dữ liệu được lưu hoặc xử lý), **legal entity** (pháp nhân tuyển dụng) hay **payroll location**. Các quyết định này có thể liên quan nhau nhưng cần nguồn chuẩn và quy tắc riêng. Không được suy ra nghĩa pháp lý từ tên site hay mã quốc gia nếu chưa có chính sách nghiệp vụ.

## 2. Cách mô hình hóa Location trong hồ sơ nhân sự

### 2.1. Dùng mã định danh ổn định, không dựa vào tên hiển thị

Một thiết kế thường gồm **location code** ổn định và dữ liệu mô tả được quản lý riêng:

| Thuộc tính minh họa | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| `identityId` | `person-2048` | Khóa danh tính nội bộ được IAM dùng để liên kết; không dùng Location để nhận diện con người. |
| `workLocationCode` | `VN-HCM-01` | Mã location được HR gán; là khóa tham chiếu đến danh mục địa điểm. |
| `workLocationName` | `Ho Chi Minh City Office 01` | Tên hiển thị; có thể đổi khi đổi tên văn phòng. |
| `workCountryCode` | `VN` | Mã quốc gia theo quy ước được tổ chức chọn, ví dụ ISO 3166-1 alpha-2. |
| `workRegionCode` | `VN-SOUTH` | Mã vùng **nội bộ**, nếu tổ chức có phân vùng vận hành. |
| `workArrangement` | `HYBRID` | Hình thức làm việc, khác với vị trí văn phòng gán cho nhân viên. |
| `locationEffectiveAt` | `2026-04-01T00:00:00+07:00` | Thời điểm thay đổi địa điểm bắt đầu có hiệu lực. |
| `locationSource` | `HRIS` | Nguồn có thẩm quyền cho thuộc tính này. |

Các trường trên là **mô hình ví dụ nội bộ**, không phải schema chuẩn bắt buộc của HRIS, SCIM hoặc IdP. Tên trường tùy hệ thống; ý nghĩa, tập giá trị, chủ sở hữu và quy tắc thay đổi cần được định nghĩa trong **data dictionary**.

**Lưu ý về mã:** mã `VN-HCM-01` là ví dụ do tổ chức đặt; không phải một chuẩn location code toàn cầu. Nếu cơ sở đổi tên, code nên được giữ ổn định khi có thể. Nếu đóng cơ sở và tái sử dụng mã cho nơi khác, dữ liệu lịch sử hoặc chính sách cũ có thể liên kết sai; nên có quy định về vòng đời mã và mapping chuyển đổi.

### 2.2. Danh mục Location (location master data)

Nguồn HR có thể giữ mã trong hồ sơ nhân viên, còn danh mục địa điểm cung cấp ngữ nghĩa chi tiết:

~~~json
{
  "locationCode": "VN-HCM-01",
  "displayName": "Ho Chi Minh City Office 01",
  "countryCode": "VN",
  "regionCode": "VN-SOUTH",
  "siteType": "OFFICE",
  "active": true,
  "validFrom": "2024-01-01",
  "validTo": null,
  "siteOwner": "workplace-operations"
}
~~~

Đây là dữ liệu minh họa, **không phải hợp đồng API**. Việc mã location còn `active` không chứng minh nhân viên đang làm việc tại đó; IAM cần kiểm tra bản ghi nhân sự được gán và thời điểm hiệu lực. Ngược lại, một mã location đã ngừng sử dụng trong danh mục có thể vẫn xuất hiện trong lịch sử kiểm toán.

Để dùng được cho IAM, nên thống nhất:

1. **Ai sở hữu danh mục?** HR, Workplace/Facilities hay nhóm quản lý dữ liệu? Ai được tạo, đổi, đóng site?
2. **Phạm vi mã có duy nhất không?** Toàn tập đoàn hay chỉ theo pháp nhân/quốc gia?
3. **Một người có thể có mấy Location?** Có site chính, site phụ, nơi công tác tạm thời hay các assignment có ngày hiệu lực khác nhau không?
4. **Chính sách xử lý thay đổi mã** khi sáp nhập văn phòng, đổi tên hoặc tái tổ chức là gì?
5. **Giá trị trống và ngoại lệ** được biểu diễn thế nào? `UNKNOWN`, `UNASSIGNED` hoặc `REMOTE` chỉ được dùng khi ý nghĩa đã thống nhất; không nên mặc nhiên coi `REMOTE` là mã địa điểm.

### 2.3. Chọn nguồn có thẩm quyền theo từng thuộc tính

Không phải mọi trường gọi là “location” đều nên lấy từ cùng một hệ thống:

| Dữ liệu | Nguồn có thẩm quyền thường gặp | Dùng cho |
| --- | --- | --- |
| Địa điểm làm việc chính thức, ngày hiệu lực | HRIS hoặc nguồn quản lý hợp đồng được tổ chức công nhận. | Lifecycle, điều kiện cấp entitlement theo site. |
| Thông tin cơ sở, trạng thái hoạt động, mã vùng | Danh mục site/Facilities được quản trị. | Kiểm tra mã hợp lệ và tra cứu site. |
| Nơi công tác tạm thời đã được phê duyệt | Hệ thống assignment/travel do tổ chức quy định. | Quyền tạm thời theo thời hạn và người bảo trợ. |
| IP, mạng đang truy cập, độ tin cậy thiết bị | IdP, mạng doanh nghiệp hoặc hệ thống đánh giá ngữ cảnh. | Đánh giá rủi ro đăng nhập/ABAC tại thời điểm truy cập. |
| Phạm vi dữ liệu một ứng dụng cho phép truy cập | Application/data owner, chính sách nghiệp vụ. | Điều kiện authorization đối với tài nguyên của ứng dụng. |

Một HRIS có thể là **source of truth cho work location**, nhưng không có nghĩa nó xác định toàn bộ điều kiện truy cập ứng dụng. Địa điểm bị nhập sai vẫn phải có quy trình sửa tại nguồn, kiểm soát lịch sử và phát lại các sự kiện liên quan.

## 3. Location đi qua hệ thống IAM như thế nào?

~~~mermaid
flowchart LR
    HR["HRIS: identity + workLocationCode + effectiveAt"] --> EV["IAM ingestion: xác thực nguồn, chuẩn hóa, kiểm tra"]
    CAT["Location master: code, trạng thái, metadata"] --> EV
    EV --> POL["IGA/IAM: đánh giá JML, RBAC/ABAC, approval"]
    POL --> IDP["Directory / IdP: thuộc tính, nhóm"]
    POL --> CON["Provisioning: SCIM / API / thủ công"]
    IDP --> SSO["SSO / ứng dụng"]
    CON --> APP["Ứng dụng đích: account / entitlement"]
    APP --> REC["Reconciliation & audit"]
    REC --> POL
~~~

**Luồng minh họa:**

1. **HRIS phát sự kiện hoặc IAM đọc dữ liệu**: identity `person-2048` đổi `workLocationCode` từ `VN-HCM-01` sang `VN-HAN-02`, có `effectiveAt`.
2. **Ingestion kiểm tra và chuẩn hóa**: mã Location có tồn tại, còn hợp lệ tại thời điểm hiệu lực, có trùng event hay đến muộn không? Mapping có giữ đúng identity không?
3. **Policy engine tính desired access mới**: nhóm truy cập theo địa điểm cũ có còn cần không? Location mới có cấp quyền tự động hay phải xin phê duyệt?
4. **Provisioning cập nhật từng đích**: directory, nhóm IdP, ứng dụng vận hành cơ sở, kho dữ liệu hoặc hệ thống đặc thù nếu có chính sách liên quan.
5. **Đối soát xác nhận actual state**: quyền theo site cũ đã gỡ, quyền mới đã cấp đúng, lỗi kết nối đã có người xử lý.

**SSO không thay thế provisioning.** IdP có thể chứa thuộc tính Location để truyền cho ứng dụng hoặc đánh giá chính sách, nhưng việc người dùng đăng nhập qua SSO không tự chứng minh một entitlement đã được thêm/xóa tại ứng dụng. Tương tự, **SCIM hỗ trợ quản lý tài khoản và nhóm**, nhưng không tự quyết định nên cấp role nào cho Location nào.

### 3.1. Truyền Location qua SCIM: tránh tự giả định tên trường

Trong **SCIM 2.0**, đối tượng User tiêu chuẩn có `addresses` (có thể biểu diễn địa chỉ làm việc với `type = "work"`), nhưng **không có thuộc tính lõi bắt buộc tên `workLocationCode`**. Enterprise User extension có các trường như `department`, `division`, `costCenter`, `employeeNumber`, `manager`, v.v.; **không nên mặc nhiên dùng một trường trong số đó làm mã Location**.

Nếu ứng dụng hỗ trợ extension tùy biến, tổ chức có thể định nghĩa thuộc tính Location trong **schema extension đã thống nhất**. Nếu ứng dụng chỉ nhận nhóm, có thể ánh xạ `workLocationCode` thành membership phù hợp. Mỗi cách triển khai cần kiểm chứng schema mà ứng dụng đích thực sự hỗ trợ.

Ví dụ về **bản đồ ánh xạ logic**, không phải payload SCIM chuẩn:

~~~yaml
source:
  system: HRIS
  field: workLocationCode
  value: VN-HCM-01
targetA:
  system: CorporateIdP
  attribute: custom.workLocationCode
  value: VN-HCM-01
targetB:
  system: FacilityAccess
  entitlement: access-site-hcm-01
  condition: employee-active-and-site-approved
~~~

Một địa chỉ văn phòng dạng text trong `addresses` có thể thuận tiện cho danh bạ, nhưng không lý tưởng làm khóa phân quyền: địa chỉ bị đổi cách viết, đa ngôn ngữ hoặc chuyển tòa nhà dễ tạo sai lệch. Hãy dùng **mã đã chuẩn hóa và mapping rõ ràng** cho những quyết định cần tính nhất quán.

### 3.2. Nhóm tại IdP và claim từ SSO có ý nghĩa khác nhau

- **Nhóm Location tại directory/IdP** có thể dùng để gán ứng dụng, tạo quyền theo nhóm hoặc làm dữ liệu đầu vào cho ứng dụng.
- **Claim Location trong SAML/OIDC** có thể giúp ứng dụng nhận thông tin người dùng khi đăng nhập, nếu được IdP và ứng dụng thống nhất. Một `locationCode` tự đặt không phải claim được mọi giao thức và mọi ứng dụng hiểu sẵn.
- **Phân quyền tại ứng dụng** vẫn cần kiểm tra claim có đến từ issuer tin cậy, còn hợp lệ và có phù hợp với tài nguyên/hành động hay không. Token hoặc phiên tồn tại lâu có thể chứa thuộc tính cũ sau sự kiện Mover.
- **SCIM/API deprovisioning** tác động đến account/nhóm/quyền tại ứng dụng, có thể phải kết hợp chấm dứt phiên hoặc thu hồi token tùy khả năng ứng dụng.

Một sai lầm phổ biến là coi claim `locationCode` từ phiên SSO cũ là nguồn sự thật bất biến. Với thay đổi Location ảnh hưởng quyền nhạy cảm, hệ thống cần cơ chế cập nhật có kiểm soát (ví dụ phiên ngắn phù hợp, re-evaluate quyền, đồng bộ trạng thái, hoặc thu hồi phiên khi cần).

## 4. Location trong mô hình Joiner–Mover–Leaver

### 4.1. Joiner: gán đúng site ngay từ đầu

Một nhân viên mới được tiếp nhận tại văn phòng **HCM-01**. Sau khi đã xác minh danh tính và quan hệ lao động, HRIS gửi mã site và ngày bắt đầu. IAM có thể dựa vào Location để **đề xuất quyền cần thiết** như nhóm máy in cơ sở, ứng dụng đặt phòng hoặc kênh thông báo tại văn phòng.

Tuy nhiên, Location một mình không đủ để cấp quyền nhạy cảm. Một người làm việc ở HCM-01 không tự động cần quyền quản trị hệ thống của HCM-01; quyền này vẫn phải căn cứ **role, trách nhiệm và phê duyệt**.

Quy trình joiner nên xác nhận:

1. Identity và `workLocationCode` liên kết đúng nhân viên.
2. Site hợp lệ, mã không bị nhầm với nhãn hiển thị.
3. Chính sách xác định rõ entitlement nào **được tự động cấp**, entitlement nào cần phê duyệt.
4. Cấp tài khoản và quyền tại các hệ thống đích thành công; kết quả được đối soát.
5. Nếu HR chưa xác định Location, quyền theo site nhạy cảm được giữ ở trạng thái chưa cấp cho tới khi có dữ liệu đáng tin cậy.

### 4.2. Mover: chuyển Location phải tính cả quyền cũ

Một nhân viên chuyển từ **VN-HCM-01** sang **VN-HAN-02**. Sự kiện này có thể không thay đổi phòng ban hoặc job title, nhưng vẫn tác động đến quyền theo cơ sở:

| Trạng thái | Hệ quả IAM minh họa |
| --- | --- |
| **Trước khi chuyển** | Có quyền `facility:hcm-01:employee` và nhóm thông báo HCM. |
| **Ngày chuyển có hiệu lực** | Tính lại desired access theo Location mới, vai trò hiện tại và các ngoại lệ còn hiệu lực. |
| **Quyền cần gỡ** | Gỡ `facility:hcm-01:employee` khi không còn nhu cầu hoặc không có phê duyệt giữ quyền. |
| **Quyền cần cấp** | Cấp `facility:han-02:employee` sau khi thỏa điều kiện/được duyệt nếu cần. |
| **Sau đồng bộ** | Xác minh nhóm/entitlement tại các hệ thống đích khớp chính sách mới. |

**Cấp quyền mới mà không thu hồi quyền theo site cũ** tạo ra **access accumulation** (quyền tích lũy) và **residual access** (quyền truy cập tồn dư). Có thể có giai đoạn bàn giao hợp lệ giữa hai site, nhưng phải được xác định rõ thời gian, thẩm quyền phê duyệt và lịch thu hồi; không mặc nhiên giữ quyền cũ vô thời hạn.

**Lưu ý thời điểm:** một sự kiện thay đổi được nhập ngày 25/03 nhưng có hiệu lực 01/04 không nên đồng nghĩa với quyền theo site mới được cấp toàn bộ ngay ngày 25/03. Hệ thống phải biết lúc nào nên áp dụng, có cần chuẩn bị account trước hay không và khi nào thu hồi quyền cũ.

### 4.3. Leaver: trạng thái nhân sự quan trọng hơn Location

Khi nhân viên rời tổ chức, các quyền theo Location cũng phải nằm trong phạm vi offboarding. Tuy vậy, **thay đổi hoặc xóa Location trong HRIS không phải tín hiệu đáng tin cậy duy nhất để kết luận Leaver**. Quyết định nghỉ việc phải dựa trên sự kiện/trạng thái nhân sự được nguồn có thẩm quyền xác nhận.

Quy trình Leaver cần kiểm tra:

- IdP/Directory account được vô hiệu hóa theo thời điểm hiệu lực và chính sách.
- Quyền theo site, nhóm nội bộ và entitlement tại ứng dụng đích được thu hồi.
- Các đường đăng nhập riêng, session, API key hoặc token còn khả dụng được xử lý khi cần.
- Bản ghi kiểm toán còn liên kết được với Location cũ để phục vụ điều tra, dù account đã bị disable hoặc xóa theo retention.
- Lỗi deprovisioning phải được cảnh báo và có owner; không ghi “hoàn tất” khi quyền thực tế vẫn tồn tại.

### 4.4. Thay đổi Location tạm thời, đa địa điểm và tái tuyển dụng

Không phải sự kiện nào cũng là chuyển site vĩnh viễn:

- **Đi công tác:** có thể cấp quyền tạm thời cho một địa điểm khác với ngày bắt đầu/kết thúc được phê duyệt; không cần ghi đè Location chính trong HRIS.
- **Hybrid/remote:** có thể cần site chính để quản trị nhân sự nhưng lại không có mặt thường xuyên tại cơ sở; quyền ra vào vật lý có thể do policy riêng quyết định.
- **Phụ trách nhiều site:** cần mô hình danh sách assignment hoặc entitlement bổ sung; trường Location đơn trị không thể diễn đạt đúng toàn bộ phạm vi nếu nghiệp vụ thực sự cho phép nhiều site.
- **Rehire:** phải liên kết lại danh tính theo quy trình xác minh, tính desired access mới; không tự khôi phục mọi entitlement theo Location cũ.

Những trường hợp này đòi hỏi định nghĩa rõ **primary location**, **secondary assignment** và **temporary access**, thay vì biến một trường văn bản thành nơi chứa nhiều giá trị ghép bằng dấu phẩy.

## 5. Location tham gia RBAC/ABAC như thế nào?

### 5.1. RBAC: Location là tiêu chí bổ sung để gán role

Trong **Role-Based Access Control**, quyền được gắn với role; Location có thể giúp chọn một role hoặc nhóm phù hợp. Ví dụ, một **nhân viên hỗ trợ tại site HCM-01** được gán `support-hcm-operator`, trong khi người cùng vai trò tại HAN-02 được gán `support-han-operator`.

Nên phân biệt:

- **Business role:** `support-operator` — thể hiện nhiệm vụ.
- **Scope/site constraint:** `VN-HCM-01` — giới hạn nơi hoặc tài nguyên được tác động.
- **Technical entitlement:** `ticketing:queue-hcm:read` — quyền cụ thể của ứng dụng.

Nếu tạo một role riêng cho mọi tổ hợp `department × job × location × project`, số lượng role có thể tăng rất nhanh và khó bảo trì. Tùy khả năng nền tảng, có thể dùng role nghiệp vụ kết hợp nhóm scope hoặc chính sách ABAC thay cho việc nhân bản hàng trăm role.

### 5.2. ABAC: kết hợp Location với thuộc tính khác

Trong **Attribute-Based Access Control**, chính sách có thể xét thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh. Ví dụ minh họa:

~~~text
ALLOW read site-document
WHEN
    subject.employmentStatus == "ACTIVE"
    AND subject.jobRole == "SITE_SUPPORT"
    AND subject.workLocationCode == resource.siteCode
    AND resource.classification != "RESTRICTED"

ELSE DENY
~~~

Đây là **pseudocode**, không phải cú pháp của một policy engine cụ thể. Chính sách thực tế còn cần xử lý thuộc tính trống/không tin cậy, quyền ngoại lệ, thứ tự đánh giá và các điều kiện bảo vệ khác.

Trong ví dụ:

1. `subject.workLocationCode` đến từ HRIS hoặc nguồn đã được IAM chuẩn hóa.
2. `resource.siteCode` là thuộc tính tài nguyên do chủ sở hữu ứng dụng quản lý.
3. `employmentStatus` và `jobRole` giới hạn người được truy cập.
4. `classification` có thể yêu cầu chính sách khác cho tài liệu hạn chế.

Không sử dụng cùng một chuỗi `location` không rõ nghĩa để so sánh giữa **site nhân sự** và **geo-IP phiên đăng nhập**. Nếu muốn áp dụng chính sách dựa trên mạng hay quốc gia đăng nhập, hãy đặt tên tách biệt như `session.networkZone` hoặc `session.estimatedCountry` và đánh giá độ tin cậy của tín hiệu.

### 5.3. Nguyên tắc khi thiếu hoặc sai Location

- **Thiếu Location:** không suy ra rằng nhân viên thuộc site có nhiều quyền nhất hoặc site mặc định của hệ thống. Với quyền site nhạy cảm, nên tránh tự cấp cho đến khi giải quyết dữ liệu thiếu.
- **Location chưa hợp lệ:** đưa sự kiện vào luồng kiểm tra/mapping, theo dõi bằng ticket hoặc hàng chờ lỗi; không âm thầm chuyển thành mã có ý nghĩa khác.
- **Location bị cập nhật trễ:** đánh giá tác động tới quyền cũ/mới và thời điểm hiệu lực; không tin rằng xử lý sự kiện theo thứ tự nhận là đủ.
- **Hai nguồn mâu thuẫn:** sử dụng precedence do tổ chức quy định, lưu căn cứ và khắc phục tại nguồn. Không để hệ thống đích tùy ý ghi đè nguồn HR có thẩm quyền.
- **Quyền đã được phê duyệt ngoại lệ:** ghi rõ scope, reason, người phê duyệt và ngày hết hạn; đổi Location có thể buộc đánh giá lại ngoại lệ.

**Nguyên tắc:** một thuộc tính Location không hợp lệ không nhất thiết làm mất mọi quyền cơ bản của người dùng; hệ quả phải dựa trên mức độ rủi ro của từng quyền. Nhưng với quyền đòi hỏi Location xác thực, không nên mở rộng đặc quyền chỉ vì dữ liệu trống.

## 6. Tính đúng đắn của dữ liệu và đồng bộ thay đổi

### 6.1. Data quality của thuộc tính Location

| Kiểm tra | Câu hỏi | Hành động phù hợp |
| --- | --- | --- |
| **Completeness** — đầy đủ | Nhân viên thuộc đối tượng yêu cầu site đã có `workLocationCode` chưa? | Gửi yêu cầu bổ sung hoặc xử lý ngoại lệ rõ ràng. |
| **Validity** — hợp lệ | Mã có trong danh mục và hợp lệ tại thời điểm hiệu lực? | Chặn mapping sai; báo owner dữ liệu. |
| **Uniqueness/Scope** — phạm vi mã | Cùng mã có nghĩa giống nhau trong mọi pháp nhân hoặc tenant? | Định nghĩa namespace hoặc khóa ghép rõ ràng. |
| **Consistency** — nhất quán | Country/region có phù hợp với mã site và quan hệ được HR ghi nhận? | Đối chiếu với master data và chính sách nghiệp vụ. |
| **Timeliness** — kịp thời | IAM biết thay đổi trước thời điểm áp dụng? Có độ trễ chưa xử lý? | Đo latency, xử lý sự kiện đến muộn. |
| **History** — lịch sử | Có biết giá trị cũ, mới, lý do và thời điểm thay đổi? | Ghi event audit, version hoặc lịch sử hiệu lực. |
| **Correlation** — liên kết | Sự kiện thuộc đúng identity và đúng account của từng hệ thống? | Dùng identifier ổn định và account linking. |

Phân biệt **thiếu dữ liệu** với **không áp dụng**: nhà thầu remote có thể không có site vật lý; nếu `workLocationCode` được định nghĩa bắt buộc cho toàn bộ nhân viên nhưng không áp dụng cho nhà thầu, dữ liệu nên phản ánh khác biệt theo policy thay vì gán tùy tiện một mã văn phòng.

### 6.2. Xử lý sự kiện theo thời gian và chống cập nhật ngược

Ví dụ, HRIS phát:

~~~json
{
  "eventId": "hr-location-1007",
  "identityId": "person-2048",
  "eventType": "WORK_LOCATION_CHANGED",
  "oldWorkLocationCode": "VN-HCM-01",
  "newWorkLocationCode": "VN-HAN-02",
  "effectiveAt": "2026-04-01T00:00:00+07:00",
  "recordedAt": "2026-03-28T09:30:00+07:00",
  "source": "HRIS",
  "sourceVersion": 18
}
~~~

Đây là **event nội bộ minh họa**, không phải định dạng chuẩn của HRIS hay SCIM. `recordedAt` cho biết lúc nguồn ghi nhận; `effectiveAt` là thời điểm Location mới có hiệu lực; `sourceVersion` giúp nhận diện thứ tự thay đổi khi nguồn hỗ trợ version. Cần thiết kế để:

1. **Idempotency:** nhận lại `eventId` không tạo nhóm/tài khoản trùng và không chạy cấp quyền sai.
2. **Ordering:** một sự kiện cũ đến muộn không ghi đè trạng thái mới đã có hiệu lực. So sánh version hoặc thời điểm hiệu lực theo quy tắc có thẩm quyền, không chỉ thứ tự nhận tin.
3. **Scheduling:** áp dụng thay đổi đúng ngày; quyền chuẩn bị trước và quyền có hiệu lực phải được phân biệt.
4. **Retry:** lỗi SCIM/API cần retry có giới hạn và cơ chế cảnh báo, tránh lặp thao tác nguy hiểm.
5. **Readback:** sau cập nhật, lấy trạng thái tại đích hoặc qua cơ chế đối soát đáng tin để xác định thực sự đã thay đổi.

Nếu HR hiệu chỉnh **ngược ngày** (retroactive correction), quy trình cần đánh giá lại quyền tại thời điểm hiện tại và ghi lịch sử thay đổi; không được xóa dấu vết của các quyết định từng được thực thi.

### 6.3. Desired state và actual state

Giả sử policy yêu cầu nhân viên chuyển sang HAN-02 chỉ có quyền ra vào HAN-02. IAM xác định:

| | Quyền ra vào HCM-01 | Quyền ra vào HAN-02 |
| --- | --- | --- |
| **Desired state sau ngày hiệu lực** | Không | Có |
| **Actual state sau khi đồng bộ lỗi** | Có | Có |
| **Đánh giá** | Quyền HCM-01 là **residual access** cần xử lý. | Quyền HAN-02 đã cấp thành công. |

Sự kiện cập nhật Location tại HRIS hoặc IdP **không đủ** để khẳng định quyền vật lý đã được thu hồi ở hệ thống cửa ra vào. IAM phải theo dõi trạng thái từng đích, báo lỗi đúng owner và kiểm chứng sau xử lý.

## 7. Accountability, kiểm toán và bảo vệ dữ liệu Location

Location là dữ liệu nhân sự; trong một số bối cảnh, việc kết hợp với lịch làm việc hoặc dữ liệu vị trí chi tiết có thể tiết lộ hoạt động của cá nhân. Hệ thống nên thu thập và truyền **mức độ chi tiết cần thiết** cho mục đích quản lý quyền.

### 7.1. Những bằng chứng nên lưu

Một thay đổi Location có ảnh hưởng tới quyền truy cập nên có:

- **Identity ID**, mã Location cũ/mới, hệ thống nguồn, thời điểm nguồn ghi nhận và thời điểm hiệu lực.
- **Mã sự kiện/correlation ID**, người hoặc hệ thống có thẩm quyền thay đổi, chính sách/version dùng để đánh giá.
- **Entitlement cần cấp, cần giữ, cần gỡ**, lý do ngoại lệ và người phê duyệt khi cần.
- **Tác vụ provisioning**, target system, kết quả xử lý, retry, lỗi và owner khắc phục.
- **Kết quả reconciliation**: quyền thực tế sau thay đổi, thời điểm kiểm chứng và trạng thái đóng ticket.

Audit trail cần phân biệt người **đề xuất thay đổi dữ liệu nhân sự**, người **duyệt quyền nghiệp vụ**, actor **thực thi thay đổi kỹ thuật** và người **chịu trách nhiệm xử lý sai lệch**. Một service account chạy connector là executor, không phải người đã quyết định chính sách cấp quyền.

### 7.2. Bảo mật dữ liệu Location

1. **Least data:** chỉ chuyển Location ở mức site/vùng đủ cho mục đích; tránh truyền địa chỉ cư trú, tọa độ GPS hay lịch di chuyển chi tiết khi không cần.
2. **Access control:** chỉ những hệ thống và vai trò được phép mới đọc/sửa các thuộc tính nhân sự; ghi log thay đổi theo trách nhiệm.
3. **Audit integrity:** hạn chế sửa/xóa log, thống nhất timestamp và giữ lịch sử theo quy định retention áp dụng.
4. **Purpose separation:** tín hiệu rủi ro đăng nhập như IP/geo-IP dùng cho security context, không tự biến thành địa điểm chính thức trên hồ sơ HR.
5. **Retention/Deletion:** giữ hoặc xóa dữ liệu theo quy định tổ chức và pháp lý áp dụng, cân bằng yêu cầu kiểm toán với bảo vệ dữ liệu cá nhân.
6. **Không ghi secret vào log:** token, credential hay dữ liệu nhạy cảm không cần thiết phải được loại bỏ hoặc che giấu.

### 7.3. Tài khoản dịch vụ không tự nhận Location từ owner cá nhân

**Service account** và **workload identity** có vòng đời độc lập với nhân viên. Khi owner của một service chuyển từ HCM sang HAN, không nên tự sửa `workLocationCode` của workload hay thu hồi quyền dịch vụ như thể nó là tài khoản cá nhân. Thay vào đó, phải đánh giá theo:

- **Vị trí hoặc môi trường thực thi của workload**, nếu chính sách ứng dụng thực sự cần.
- **Owner mới** có trách nhiệm quản trị và phê duyệt quyền.
- **Tài nguyên được truy cập**, credential đang có và yêu cầu least privilege.
- **Kế hoạch chuyển giao**, xoay vòng secret khi cần, thay đổi entitlement hoặc deprovision khi dịch vụ ngừng hoạt động.

Location của owner nhân sự, **region triển khai workload** và **location của dữ liệu** là ba thuộc tính khác nhau. Việc mô hình hóa riêng giúp tránh các thay đổi quyền kỹ thuật không liên quan đến nghiệp vụ.

## 8. Tình huống thực tế: chuyển từ Hồ Chí Minh sang Hà Nội

**Bối cảnh:** Lan đang làm việc tại `VN-HCM-01`, có quyền sử dụng hệ thống quản lý ra vào văn phòng HCM. HR xác nhận Lan chuyển về `VN-HAN-02` kể từ **01/06**. Lan vẫn giữ vai trò nghiệp vụ `support-specialist`, không có phê duyệt sử dụng cơ sở HCM sau ngày chuyển.

**Bước 1 — Nguồn dữ liệu:** HRIS cập nhật `workLocationCode`, giữ `identityId` của Lan và phát sự kiện với effective date. Danh mục site xác nhận cả hai mã tồn tại và đúng phạm vi.

**Bước 2 — Policy evaluation:** IAM vẫn giữ các quyền gắn với vai trò hỗ trợ chung. Đối với quyền theo site, IAM tính:

~~~text
KEEP:   support:ticket-read
REMOVE: facility:VN-HCM-01:employee
GRANT:  facility:VN-HAN-02:employee
REVIEW: any time-bound exception for VN-HCM-01
~~~

**Bước 3 — Đồng bộ:** IAM cập nhật nhóm/entitlement tại hệ thống kiểm soát ra vào, cập nhật thuộc tính Location ở IdP nếu cần và ghi lại kết quả từng target. Nếu một ứng dụng chỉ nhận cấu hình thủ công, tác vụ cần được giao owner và xác nhận.

**Bước 4 — Đối soát:** hệ thống ra vào HAN đã cấp quyền nhưng HCM còn quyền cũ vì một connector trả lỗi. IAM tạo cảnh báo, yêu cầu khắc phục và kiểm tra lại quyền thực tế. Trước khi khép sự kiện Mover, phải xác minh entitlement HCM không còn hoặc có ngoại lệ hợp lệ, có thời hạn.

**Bước 5 — Kiểm toán:** khi được hỏi “Vì sao Lan có quyền ra vào HAN?”, tổ chức chỉ ra HR location assignment, chính sách cấp quyền theo site, event ID và kết quả provisioning. Khi được hỏi “Quyền HCM đã thu hồi chưa?”, phải xuất trình được kết quả xác minh thực tế và thời điểm hoàn tất, không chỉ thông báo từ HRIS.

**Biến thể:** nếu Lan công tác tại HCM ba ngày trong tháng 7, quyền tạm thời nên được cấp theo yêu cầu được phê duyệt, có thời gian hết hạn, mà không nhất thiết thay đổi **primary work location**. Nếu Lan nghỉ việc trong thời gian công tác, quy trình Leaver vẫn phải thu hồi mọi quyền còn hoạt động theo chính sách.

## 9. Các lỗi triển khai Location thường gặp

| Lỗi | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Dùng địa chỉ text hoặc display name làm khóa phân quyền. | Viết hoa, đổi tên hoặc dịch địa chỉ khiến mapping sai. | Dùng mã Location chuẩn và danh mục tham chiếu. |
| Coi geo-IP đăng nhập là Location nhân sự. | Đi công tác/VPN bị hiểu thành chuyển văn phòng. | Tách **HR work location** và **session location**. |
| Gán quyền theo Location mà không xét employment status và role. | Cấp quá nhiều quyền cho mọi nhân sự tại một site. | Kết hợp RBAC/ABAC, least privilege và phê duyệt. |
| Khi chuyển site chỉ cấp thêm quyền mới. | Quyền site cũ tồn dư, đặc biệt ở hệ thống local. | Tính diff desired state và thu hồi quyền cũ. |
| Ghi đè Location bằng sự kiện cũ đến muộn. | Quyền bị chuyển ngược về site trước. | Kiểm tra source version/effective date, idempotency và ordering. |
| Thiếu Location thì gán mặc định site lớn nhất. | Cấp quyền không có căn cứ. | Phân biệt missing/unknown/not applicable; xử lý ngoại lệ có kiểm soát. |
| Coi trường `addresses` của SCIM là mã site chuẩn. | Ứng dụng nhận dữ liệu nhưng không hiểu hoặc mapping sai entitlement. | Thống nhất schema extension/mapping từng target. |
| Đổi Location tại IdP rồi coi mọi quyền đã cập nhật. | Nhóm/entitlement local và token/session cũ có thể còn. | Deprovision, đối soát target và xử lý phiên khi cần. |
| Không có lịch sử Location cũ/mới và thời điểm hiệu lực. | Không giải thích được quyền đã được cấp/thu hồi tại thời điểm nào. | Audit event, identity correlation và dữ liệu hiệu lực. |
| Gắn Location của service account theo vị trí người sở hữu. | Thay đổi quyền workload không phù hợp khi owner chuyển site. | Mô hình identity của workload và owner độc lập. |

## 10. Checklist thiết kế và bài tập tự kiểm tra

Khi xây dựng hoặc rà soát một kết nối **HRIS → IAM** cho thuộc tính Location, hãy xác nhận:

1. **Ngữ nghĩa:** Location đang biểu diễn site chính, site phụ, vùng nghiệp vụ hay hình thức làm việc? Có định nghĩa và ví dụ nhất quán không?
2. **Nguồn chuẩn:** ai sở hữu trường, mã nào hợp lệ, ai phê duyệt sửa dữ liệu và khi nào thay đổi có hiệu lực?
3. **Mapping:** location code có ổn định, duy nhất theo phạm vi, được chuyển tới đúng IdP/SCIM/API target không?
4. **JML:** joiner thiếu site được xử lý ra sao? Mover có **remove old / grant new**? Leaver có gỡ quyền theo site?
5. **Authorization:** quyền nào thực sự phụ thuộc Location? Có kiểm tra role, trạng thái, đặc quyền và SoD?
6. **An toàn sự kiện:** xử lý event đến muộn, trùng, sửa ngược ngày, site đóng/mở và assignment tạm thời thế nào?
7. **Đối soát:** trạng thái quyền theo site ở từng ứng dụng đích có được xác minh? Ai nhận cảnh báo khi thất bại?
8. **Kiểm toán và quyền riêng tư:** có đủ bằng chứng quy trách nhiệm và bảo vệ dữ liệu Location theo mục đích cần thiết không?

### Bài tập tình huống

**Tình huống A — Nhân viên remote:** Một nhân viên làm việc remote tại Đà Nẵng nhưng được HR quản lý theo site `VN-HCM-01`. Hệ thống phát hiện IP ở Đà Nẵng và tự chuyển `workLocationCode` thành `VN-DAN-01`. Hãy giải thích nguồn dữ liệu nào bị dùng sai và cách tách kiểm tra rủi ro đăng nhập khỏi thay đổi hồ sơ HR.

**Tình huống B — Mover trễ sự kiện:** HRIS phát sự kiện đổi từ HCM-01 sang HAN-02 phiên bản 18; sau đó một hàng đợi gửi lại phiên bản 17. Hãy mô tả cách dùng version/effective date để tránh ghi đè ngược và cách kiểm chứng quyền cũ đã thu hồi.

**Tình huống C — Site phụ:** Một kỹ sư cần tiếp cận hai phòng máy trong hai tuần để bảo trì, nhưng trường `workLocationCode` chỉ chứa site chính. Hãy thiết kế một entitlement tạm thời có owner, approval, scope và expiry mà không sửa sai ý nghĩa của Location chính.

**Tình huống D — Quyền tồn dư:** Khi một nhân viên đã chuyển site, IdP cập nhật thuộc tính thành công nhưng nhóm quyền ở hệ thống cửa ra vào vẫn chưa thay đổi. Hãy chỉ ra sự khác nhau giữa **source update**, **provisioning success** và **verified actual access**, cũng như người cần chịu trách nhiệm xử lý.

**Điểm cần nhớ:** Trong IAM lifecycle, **Location là dữ liệu nhân sự có ngữ nghĩa và nguồn sở hữu rõ ràng**. Khi được chuẩn hóa và đồng bộ đúng, nó giúp chính sách RBAC/ABAC xác định phạm vi truy cập phù hợp cho Joiner, Mover và Leaver. Khi được dùng sai hoặc không đối soát, Location có thể tạo quyền vượt nhu cầu và quyền truy cập tồn dư. Để kiểm soát rủi ro, luôn tách **địa điểm được HR gán**, **ngữ cảnh đăng nhập hiện tại** và **địa điểm của tài nguyên**, rồi xác minh kết quả cấp/thu hồi quyền tại từng hệ thống đích.
