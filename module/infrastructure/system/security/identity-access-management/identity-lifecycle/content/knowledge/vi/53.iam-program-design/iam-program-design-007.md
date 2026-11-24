# Xác định review khi thiết kế chương trình IAM

Trong một chương trình **Identity and Access Management (IAM)**, việc cấp quyền đúng tại thời điểm nhân viên gia nhập chưa bảo đảm quyền đó còn hợp lệ sau sáu tháng. Người dùng có thể đổi vị trí, rời dự án, hết hợp đồng hoặc được cấp quyền đặc biệt để xử lý sự cố rồi không ai thu hồi. Vì vậy IAM cần cơ chế **review (rà soát, tái chứng nhận quyền truy cập)** để xác minh định kỳ hoặc theo sự kiện rằng **tài khoản và quyền đang tồn tại vẫn có lý do nghiệp vụ, chủ sở hữu và phạm vi hợp lệ**.

Bài học thuộc chương **Thiết kế chương trình IAM** của module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Chủ đề gắn trực tiếp với vòng đời **Joiner–Mover–Leaver (JML)**, nguồn danh tính, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và mục tiêu giảm quyền tồn dư.

Một đợt review được xem là hữu ích khi nó tìm ra quyền không còn cần thiết **và quyết định xử lý đã được thực thi, xác minh ở hệ thống đích**. Chỉ gửi bảng cho quản lý rồi thu về hàng trăm nút “Đồng ý giữ quyền” không chứng minh hệ thống đã kiểm soát được rủi ro.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **access review**, approval, access request, JML automation, access certification và reconciliation.
2. Xác định đối tượng, phạm vi, thời điểm, người rà soát và căn cứ quyết định cho từng đợt review.
3. Thiết kế **review matrix** theo loại tài khoản, mức đặc quyền, độ nhạy tài nguyên, thời hạn quyền và nguồn vòng đời.
4. Kiểm kê **quyền truy cập hiệu lực** từ role, nhóm lồng nhau, quyền cấp trực tiếp, tài khoản local và quyền theo phạm vi tenant.
5. Chuẩn hóa kết quả **Keep / Revoke / Modify / Investigate / Exception**, đi kèm lý do và quy trình xử lý.
6. Liên kết review với Mover, Leaver, kết thúc hợp đồng, tài khoản dịch vụ, SoD và quyền đặc quyền có thời hạn.
7. Kiểm thử và đo **review completion, remediation completion, quyền tồn dư, ngoại lệ và tính chính xác của chứng cứ**.

## 2. Review trong IAM là gì?

**Access review** là hoạt động kiểm tra các account, role, entitlement hoặc quan hệ truy cập đang tồn tại, để người hoặc bộ phận có thẩm quyền xác nhận xem chúng **có còn phù hợp với công việc, quan hệ danh tính, chính sách và rủi ro hiện tại hay không**.

**Access certification / recertification** nhấn mạnh kết quả chứng nhận quyền được phép duy trì. Trong một số công cụ, access review và certification được dùng gần tương đương. Cần quan tâm nghĩa và bằng chứng thực tế hơn tên màn hình.

| Hoạt động | Câu hỏi chính | Thời điểm |
|---|---|---|
| **Identity verification** | Danh tính hoặc mối quan hệ này đã được xác minh chưa? | Khi tạo/cập nhật danh tính và khi có nghi vấn. |
| **Access request + approval** | Có được cấp một quyền mới hoặc gia hạn không? | Trước khi cấp hoặc mở rộng quyền. |
| **Provisioning** | Tài khoản/quyền đã được tạo, sửa hoặc thu hồi tại đích chưa? | Sau sự kiện JML hoặc quyết định được duyệt. |
| **Access review / certification** | Quyền **đang có** còn cần thiết và có owner hợp lệ không? | Theo lịch hoặc sự kiện kích hoạt. |
| **Reconciliation** | Trạng thái tài khoản/quyền ở đích có khớp trạng thái mong muốn? | Liên tục hoặc định kỳ, kể cả sau review. |
| **Runtime authorization** | Hành động hiện tại có được cho phép với tài nguyên này không? | Tại thời điểm API/ứng dụng xử lý yêu cầu. |
| **Audit** | Ai quyết định điều gì, theo dữ liệu nào và kết quả thực thi là gì? | Xuyên suốt quy trình. |

**Review không thay thế Leaver.** Nếu HRIS đã xác nhận nhân viên nghỉ việc, quyền phải được thu hồi theo chính sách và thời điểm có hiệu lực. Không được chờ đến đợt review quý sau hoặc yêu cầu quản lý “xác nhận có nên xóa quyền” để trì hoãn hành động bắt buộc.

**Review cũng không đồng nghĩa chỉ kiểm tra tài khoản ở IdP.** Một người có thể đăng nhập SSO nhưng vẫn có quyền trực tiếp ở SaaS, cloud, database hoặc tài khoản local. Để đánh giá đúng, reviewer cần nhìn thấy **các quyền hiệu lực và nguồn gốc cấp quyền** trong phạm vi chịu trách nhiệm.

## 3. Vì sao cần xác định review ngay ở bước thiết kế chương trình?

Hệ thống IAM có thể làm tốt Joiner nhưng sau nhiều lần Mover dễ tích lũy entitlement:

- Người từ Finance sang Engineering vẫn có nhóm xem dữ liệu tài chính.
- Nhà thầu được gia hạn account nhưng phạm vi hợp đồng mới đã nhỏ hơn.
- Nhân viên dự án kết thúc nhiệm vụ nhưng role tạm thời không có ngày hết hạn.
- Một quyền quản trị được cấp trực tiếp tại cloud, nằm ngoài role catalog.
- Service account của hệ thống đã ngừng chạy nhưng credential và quyền vẫn còn.
- Một approver đã nghỉ việc, khiến quyền của đơn vị không còn người chứng nhận.

Thiết kế review giúp phát hiện các vấn đề này, xác định người chịu trách nhiệm và tạo **đầu ra có thể thực thi**. Review cần kế hoạch cho cả **lúc kết luận** lẫn **sau khi kết luận**, đặc biệt đối với quyết định thu hồi hoặc điều chỉnh quyền.

### Ba câu hỏi phải được trả lời

1. **Review cái gì?** Tài khoản, role assignment, quyền thực tế, group membership, phạm vi dữ liệu, tài khoản phi con người hoặc chính sách nào?
2. **Ai có thể kết luận?** Manager xác nhận nhu cầu công việc; owner ứng dụng hoặc dữ liệu xác nhận phạm vi và rủi ro; service owner xác nhận workload vẫn cần quyền.
3. **Khi kết luận xong thì sao?** Giữ nguyên có điều kiện, thu hồi, giảm scope, gia hạn có thời hạn, mở điều tra hoặc ngoại lệ; thao tác phải có owner, hạn xử lý và bằng chứng readback.

## 4. Xác định đối tượng và phạm vi review

Review thường phải đi sâu hơn inventory account. Một account có thể mang nhiều entitlement từ nhiều nguồn cấp và hiệu lực trên các tenant khác nhau. Vì vậy đối tượng quyết định nên được định danh rõ.

| Đối tượng review | Ví dụ | Điều cần xem xét |
|---|---|---|
| **Identity / relationship** | Nhân viên `EMP-1042`, nhà thầu `CTR-308` | Quan hệ hiện còn hiệu lực, sponsor và ngày hết hạn hợp lệ? |
| **Account** | `(crm, tenant-vn, nativeUser-77)` | Account này còn cần thiết, liên kết đúng chủ thể, có thể đăng nhập độc lập không? |
| **Role assignment** | `FINANCE_ANALYST` gán cho user ở tenant VN | Có còn phù hợp chức năng, scope và phê duyệt không? |
| **Technical entitlement** | Nhóm `grp-finance-read`, quyền DB SELECT | Quyền có vượt nhu cầu hoặc là quyền trực tiếp ngoài role catalog? |
| **Privileged access** | Cloud administrator, PAM role | Có cần đặc quyền thường trực, đã hết phiên JIT, có SoD và logging? |
| **Application / data scope** | Quyền xuất báo cáo trong tenant SG | Dữ liệu/tài nguyên có đúng tenant và phạm vi công việc không? |
| **Non-human identity** | Service principal hoặc CI/CD bot | Workload còn hoạt động, owner còn hợp lệ, quyền và credential còn cần? |
| **Shared/break-glass account** | Account khôi phục quản trị | Có owner, kiểm soát truy cập, nhật ký sử dụng và diễn tập không? |
| **External access** | Vendor/partner được cấp quyền | Hợp đồng và quan hệ bảo trợ còn hiệu lực? |

### Phân biệt account scope và review scope

**Account scope** nói những tài khoản nào IAM chịu trách nhiệm quản trị. **Review scope** nói những đối tượng cụ thể nào, ở kỳ nào, được ai chứng nhận và theo tiêu chí gì. Review scope có thể nhỏ hơn toàn bộ account scope trong một chiến dịch, nhưng phải có **kế hoạch bao phủ tổng thể**, không tạo vùng ngoài kiểm soát kéo dài vô thời hạn.

Ví dụ tổ chức có ba tenant SaaS. Chiến dịch reviewer chỉ nhìn thấy quyền tenant VN thì báo cáo phải ghi rõ **tenant SG và production-admin nằm ở chiến dịch khác**. Không được gọi kết quả đó là “toàn bộ quyền ứng dụng đã review”.

### Nhiều nguồn cùng cấp một quyền

Một người có thể nhận entitlement `report:read` từ cả role `FINANCE_ANALYST` và một assignment dự án còn hợp lệ. Nếu reviewer quyết định bỏ role thứ nhất, hệ thống phải xác định liệu entitlement thực tế còn có nguồn cấp hợp lệ khác. Không được gỡ nhầm quyền còn cần thiết; cũng không được coi entitlement đã xử lý xong khi nguồn cấp trực tiếp trái chính sách vẫn còn.

Nên quản trị **grant provenance** — nguồn gốc từng quyền: policy birthright, business role, approved request, quyền thủ công, group lồng nhau, IAM cloud role hay cơ chế chia sẻ tài nguyên.

## 5. Ma trận thiết kế review theo rủi ro

Không có chu kỳ duy nhất phù hợp mọi account. Cần xác định **mức rủi ro**, tần suất và người chịu trách nhiệm, đồng thời phân biệt review định kỳ với hành động tự động theo JML.

| Nhóm quyền | Tín hiệu rủi ro | Reviewer thích hợp | Thời điểm gợi ý |
|---|---|---|---|
| Role cơ sở nhân viên | Quyền thông thường, ít nhạy cảm | Owner role hoặc IAM theo chính sách | Định kỳ hoặc khi role policy thay đổi. |
| Role nghiệp vụ | Có thể xem/sửa dữ liệu theo chức năng | Manager + application owner tùy chính sách | Khi Mover và theo chu kỳ được duyệt. |
| Dữ liệu nhạy cảm | Xuất dữ liệu, truy cập nhiều tenant, phân loại cao | Data owner có authority theo phạm vi | Chu kỳ ngắn hơn; khi chuyển dự án hoặc phạm vi dữ liệu. |
| Quyền production/privileged | Tác động hệ thống quan trọng, thay chính sách bảo mật | Privileged/resource owner độc lập | Thường xuyên hơn; sau nâng quyền hoặc sự kiện rủi ro. |
| Nhà thầu/đối tác | Quan hệ hết hạn hoặc sponsor thay đổi | Contract sponsor + resource owner | Theo hợp đồng, đổi scope và review định kỳ. |
| Service/workload account | Quyền tĩnh lớn, owner biến mất, key lâu đời | Service owner + resource owner | Khi triển khai/ngừng dịch vụ, đổi owner và chu kỳ rủi ro. |
| Shared/break-glass | Khó quy trách nhiệm cá nhân, rủi ro cao | Security owner và owner hạ tầng | Định kỳ, sau sử dụng, sau thay người giữ quyền. |
| Orphan account | Không xác định được identity hoặc owner | Security/IAM + owner hệ thống | Điều tra ưu tiên; không chờ đến kỳ thường niên. |

Các chu kỳ như **hàng tháng, hàng quý, nửa năm** chỉ là tùy chọn tổ chức cần cân nhắc, không phải quy định chung cho mọi hệ thống. Ví dụ một doanh nghiệp có thể chọn **quý** cho quyền quản trị production và **nửa năm** cho role nội bộ ít rủi ro; phải dựa trên dữ liệu nhạy cảm, tốc độ biến động nhân sự, khả năng thu hồi và nghĩa vụ thực tế.

**Risk-based review** không có nghĩa quyền ít rủi ro được giữ vô hạn. Nó có nghĩa phân bổ công sức và bằng chứng kiểm tra theo ảnh hưởng có thể xảy ra, đồng thời mọi quyền vẫn có owner, cơ chế phát hiện sai lệch và thời điểm xem xét.

## 6. Các loại review và sự kiện kích hoạt

### 6.1. Review định kỳ (periodic certification)

Một chiến dịch định kỳ chốt phạm vi tại thời điểm xác định, lấy snapshot quyền và phân bổ từng mục tới reviewer. Thường dùng để phát hiện quyền tích lũy, quyền không sử dụng hoặc quyền đã lệch khỏi nhiệm vụ.

Ví dụ, mỗi kỳ rà soát quý nhóm Security gửi danh sách cloud admin thuộc production để resource owner xác nhận lý do nghiệp vụ, thời hạn, SoD và cơ chế JIT.

### 6.2. Review theo sự kiện (event-triggered)

Thay vì chờ hết quý, các thay đổi có thể kích hoạt đánh giá ngay:

- **Mover:** thay phòng ban, chức danh, quản lý, dự án, tenant, phạm vi hợp đồng.
- **Leaver / contract ended:** thu hồi bắt buộc; review bổ sung để tìm account local, quyền đặc biệt và quyền còn tồn dư.
- **Rehire:** xem xét lại quyền hiện tại, không tự động khôi phục toàn bộ quyền trước đó.
- **Resource ownership changed:** dữ liệu/tài nguyên chuyển owner hoặc thay phân loại nhạy cảm.
- **Service owner changed / workload retired:** rà soát account phi con người, credential và role.
- **Role/policy mapping changed:** thay đổi entitlement của một role có thể mở rộng quyền của mọi người đang giữ role.
- **Security incident / exception expiry:** kiểm tra quyền đang tồn tại sau sự cố hoặc ngoại lệ.
- **Dormancy / drift detected:** tài khoản không hoạt động, quyền cấp trực tiếp hoặc trạng thái thực tế khác desired state.

**Một event có thể kích hoạt cả hành động tự động lẫn review.** Ví dụ Mover làm mất điều kiện giữ role Finance thì role phải bị thu hồi theo policy; reviewer đánh giá những quyền đặc biệt không tự suy ra được, không dùng review để trì hoãn thu hồi quyền đã chắc chắn hết hiệu lực.

### 6.3. Review khi yêu cầu gia hạn hoặc hoàn tất nhiệm vụ

Quyền theo dự án hoặc phiên nâng quyền nên có `effectiveUntil`/expiry. Khi đến hạn, chính sách phải thu hồi mặc định theo điều kiện đã duyệt; reviewer hoặc approver chỉ quyết định **có nên gia hạn dựa trên nhu cầu mới**.

Ví dụ tài khoản được cấp role quản trị hai giờ để khắc phục sự cố. Quyền phải kết thúc đúng hạn dù người phê duyệt chưa trả lời về việc gia hạn.

## 7. Chọn reviewer có thẩm quyền

Người rà soát phải có khả năng trả lời **vì sao quyền vẫn cần thiết** và chịu trách nhiệm trong đúng phạm vi. Giao tất cả quyền cho quản lý trực tiếp có thể khiến họ phải chứng nhận các quyền kỹ thuật hoặc dữ liệu mà họ không hiểu.

| Reviewer | Phù hợp khi | Hạn chế cần xử lý |
|---|---|---|
| **Line manager** | Xác nhận nhiệm vụ, vị trí, dự án và nhu cầu nghiệp vụ của nhân viên. | Có thể không hiểu permission của ứng dụng hoặc dữ liệu nhạy cảm. |
| **Application owner** | Kiểm tra role native, account local, quyền đặc biệt trong ứng dụng. | Không tự quyết định tính hợp lệ của quan hệ nhân sự. |
| **Data owner** | Xác nhận mục đích và scope dữ liệu, tenant, phân loại. | Cần nguồn owner chính xác và quyền quyết định trong tenant. |
| **Privileged/security owner** | Chứng nhận quyền admin, SoD, PAM/JIT, ngoại lệ. | Cần độc lập với người nhận quyền khi policy yêu cầu. |
| **Contract sponsor** | Khẳng định nhà thầu/đối tác còn nhiệm vụ, thời hạn và phạm vi. | Không được tự gia hạn quyền vượt hợp đồng hoặc chấp thuận thay data owner. |
| **Service owner** | Xác nhận workload còn hoạt động, purpose, owner và yêu cầu quyền kỹ thuật. | Cần đối chiếu resource owner cho quyền production nhạy cảm. |
| **IGA/IAM reviewer** | Xem xét chất lượng dữ liệu, orphan, policy drift và bằng chứng. | Không mặc nhiên thay thế owner nghiệp vụ khi không có authority. |

### Tách trách nhiệm và tránh tự chứng nhận

**Self-certification** (người dùng tự chấp nhận quyền của chính mình) có thể tạo xung đột lợi ích, đặc biệt với quyền nhạy cảm. Policy phải xác định:

1. Chủ thể nào được phép review loại quyền này?
2. Reviewer có đang là người giữ quyền, người yêu cầu hoặc người hưởng lợi không?
3. Có cần hai ý kiến độc lập: manager xác nhận nhu cầu và data owner xác nhận phạm vi?
4. Người được ủy quyền có đúng phạm vi, loại quyền và thời hạn ủy quyền không?
5. Khi approver/reviewer không còn làm việc hoặc không có dữ liệu owner, chuyển tới ai?

Không nên ngầm chuyển quyền cho một thành viên nhóm bất kỳ hoặc tự đánh dấu `KEEP` khi reviewer không phản hồi. Các trường hợp thiếu authority cần được xử lý theo kênh escalation có kiểm soát.

## 8. Dữ liệu reviewer cần thấy để quyết định

Một chiến dịch review không nên chỉ xuất danh sách username và tên nhóm khó hiểu. Reviewer cần **bối cảnh nghiệp vụ**, phạm vi và mức rủi ro.

| Dữ liệu cần hiển thị | Mục đích |
|---|---|
| `identityId`, loại quan hệ và trạng thái | Biết ai thực sự sở hữu quyền và quan hệ còn hiệu lực không. |
| `sourceSystem`, `sourceRecordId` | Có thể kiểm chứng trạng thái từ hệ thống có thẩm quyền. |
| `targetSystemId`, `tenantId`, `nativeAccountId` | Biết quyền tồn tại tại đâu; không gộp account khác tenant. |
| `entitlementId`, mô tả quyền và resource scope | Hiểu thực tế có thể đọc/sửa/xuất dữ liệu gì. |
| `roleId` và `grantProvenance` | Xác định quyền đến từ role, request, group lồng nhau hay grant trực tiếp. |
| `grantedAt`, `lastReviewedAt`, `effectiveUntil` | Đánh giá thời gian tồn tại và tính hợp lệ. |
| `lastUsedAt` hoặc chỉ số sử dụng đáng tin | Hỗ trợ phân tích nhưng không tự quyết định quyền còn cần. |
| `managerId`, `projectId`, `serviceOwnerId` | Xác minh trách nhiệm và công việc liên quan. |
| `riskTier`, SoD/drift flags | Ưu tiên kiểm soát quyền đặc biệt hoặc nghi ngờ sai lệch. |
| `approvalRef`, `policyVersion` | Truy nguồn quyết định cấp trước đó. |
| `snapshotAt`, `observedAt` | Biết dữ liệu mới đến mức nào và có cần kiểm tra lại không. |

**Tên role không phải mô tả quyền.** Nếu reviewer chỉ thấy `GRP-6742`, họ khó biết đó là quyền xem báo cáo hay quản trị toàn bộ tài khoản khách hàng. Role catalog và entitlement catalog cần diễn giải tên kỹ thuật thành hành động và dữ liệu chịu ảnh hưởng.

### Chất lượng dữ liệu quyết định

- Tránh ghép tài khoản bằng email/username nếu hệ thống có native ID ổn định.
- Không tự suy rằng `lastUsedAt=null` chắc chắn là quyền không được sử dụng; có thể ứng dụng không thu thập chỉ số này.
- Với quyền dự án ít sử dụng nhưng cực kỳ quan trọng, owner phải giải thích nhu cầu theo kỳ công việc.
- Phân biệt quyền **được gán** và quyền **hiệu lực** sau kế thừa nhóm, policy cloud và giới hạn ABAC.
- Snapshot có thể lỗi thời trong lúc campaign diễn ra; bước thực thi phải kiểm tra lại trạng thái và nguồn gốc quyền mới nhất.

## 9. Quy trình review từ snapshot đến remediation

~~~mermaid
flowchart TD
    A["Xác định scope / risk / campaign owner"] --> B["Thu thập trạng thái account + quyền thực tế"]
    B --> C["Tương quan identity / owner / grant provenance"]
    C --> D["Tạo snapshot + review item"]
    D --> E["Gán reviewer có authority"]
    E --> F{"Reviewer quyết định"}
    F -- "Keep" --> G["Ghi căn cứ, thời hạn review tiếp"]
    F -- "Revoke / Modify" --> H["Revalidate identity, scope, SoD và quyền hiện tại"]
    F -- "Investigate" --> I["Điều tra owner / nguồn / drift"]
    F -- "Exception" --> J["Kiểm tra phê duyệt ngoại lệ và biện pháp bù trừ"]
    I --> F
    J --> H
    H --> K["Gửi hành động đến IdP / SCIM / API / PAM / manual"]
    K --> L["Đọc lại trạng thái quyền ở hệ thống đích"]
    L --> M{"Quyền đã đúng trạng thái mong muốn?"}
    M -- "Chưa" --> N["Retry / incident / escalation / owner"]
    N --> L
    M -- "Rồi" --> O["Đóng remediation + audit evidence"]
    G --> P["Tổng kết campaign và kỳ tiếp theo"]
    O --> P
~~~

Một workflow có thể dùng nhiều trạng thái, nhưng cần tách **review decision** khỏi **remediation result**. Ví dụ người duyệt chọn `REVOKE`, trong khi SaaS trả lỗi. Không thể báo `COMPLETED` chỉ vì quyết định đã được lưu.

### Các trạng thái nên theo dõi riêng

**Campaign/review item:**

~~~text
SCHEDULED -> SNAPSHOTTED -> ASSIGNED -> IN_REVIEW
                                       |-> KEEP_DECIDED
                                       |-> REVOKE_DECIDED
                                       |-> MODIFY_DECIDED
                                       |-> INVESTIGATE
                                       |-> EXCEPTION_REVIEW
                                       |-> ESCALATED / OVERDUE
~~~

**Remediation:**

~~~text
NOT_REQUIRED
OR
PLANNED -> DISPATCHED -> IN_PROGRESS -> CONFIRMED
                                  |-> FAILED -> RETRYING
                                  |-> EXCEPTION / MANUAL_VERIFICATION
~~~

Một campaign chỉ được chốt là **remediation-complete** khi mọi hành động bắt buộc đã được xác minh hoặc các ngoại lệ chưa đóng được mô tả chính xác theo tiêu chí kết thúc được phê duyệt. Nếu một quyền đang tồn dư ở ứng dụng, báo cáo cần nêu rõ **chưa giải quyết**, dù chiến dịch đã hết hạn.

## 10. Các quyết định review và hành động tương ứng

| Decision | Ý nghĩa nghiệp vụ | Hành động / bằng chứng cần có |
|---|---|---|
| **KEEP** | Quyền vẫn cần thiết trong phạm vi được mô tả. | Lưu lý do, reviewer, thời điểm, bằng chứng; theo dõi hạn hoặc kỳ review tiếp. |
| **REVOKE** | Không còn căn cứ hợp lệ để giữ quyền. | Tạo lệnh thu hồi đúng grant/entitlement; xác minh ở đích. |
| **MODIFY / REDUCE** | Chỉ cần một phần quyền hoặc phạm vi hẹp hơn. | Tạo kế hoạch thu hồi phần thừa và cấp phần cần thiết theo policy; kiểm tra SoD. |
| **INVESTIGATE** | Không có đủ dữ liệu hoặc owner để quyết định. | Tạo case với owner, mức rủi ro và hạn xử lý; có thể hạn chế truy cập theo policy. |
| **EXCEPTION** | Tạm giữ quyền bất thường với lý do được chấp thuận. | Chủ thể chấp nhận rủi ro, biện pháp bù trừ, expiry, lịch hậu kiểm và chứng cứ. |
| **DELEGATE / REASSIGN** | Reviewer hiện tại không có thẩm quyền. | Chuyển tới người đủ authority; không coi là quyết định về quyền. |

**KEEP không phải “phê duyệt toàn bộ mọi quyền của người này”.** Decision cần gắn với **reviewItemId**, target entitlement hoặc account, scope và snapshot version. Khi reviewer quyết định giữ quyền đọc trong tenant VN, không được dùng kết quả đó để hợp thức hóa quyền xuất dữ liệu tenant SG.

### Khi reviewer chọn Revoke nhưng quyền được cấp từ nhiều nguồn

Giả sử entitlement `report:read` được cấp từ role `FINANCE_ANALYST` và từ assignment `PROJECT_A_REVIEWER`. Reviewer có thể kết luận role Finance không còn hợp lệ sau khi người dùng Mover. IAM phải:

1. Xác định grant cụ thể nào reviewer đang quyết định.
2. Thu hồi role hoặc assignment không còn lý do hợp lệ.
3. Đánh giá lại **quyền hiệu lực** từ các grant còn lại.
4. Nếu quyền vẫn còn vì một grant hợp lệ khác, ghi bằng chứng và tiếp tục quản trị grant đó.
5. Nếu một grant trực tiếp không có căn cứ vẫn tồn tại, tạo finding riêng; không đánh dấu toàn bộ nguy cơ đã giải quyết.

Không được gửi lệnh “remove native group” một cách mù quáng nếu hành động đó xóa entitlement đang được các role hợp lệ khác cùng dùng. Cần mô hình quyền và cơ chế ownership đủ chính xác.

## 11. Thiết kế review trong Joiner–Mover–Leaver

### Joiner — kiểm tra quyền cấp ban đầu

Khi nhân viên gia nhập, hệ thống đánh giá trạng thái danh tính, account scope, policy birthright và những role cần phê duyệt. Review thường **không dùng để thay request approval trước khi cấp**. Tuy nhiên có thể có **hậu kiểm** sau onboarding để phát hiện cấp nhầm quyền vượt baseline, quyền nhân bản từ người cũ hoặc application role được cấu hình quá rộng.

Ví dụ nhân viên mới chỉ cần account cổng thông tin và ứng dụng quản lý công việc. Nếu phát hiện quyền export toàn bộ dữ liệu tài chính được gán trực tiếp, review bất thường phải đưa ra `REVOKE` hoặc điều tra căn cứ cấp.

### Mover — cơ chế giảm privilege creep

Khi một người thay vai trò công việc, chính sách IAM cần tính lại role mong muốn từ HRIS và các approval còn hợp lệ:

~~~text
desired = evaluateAuthoritativeIdentityAndActivePolicies(identity)
actual  = observeEffectiveAccessAcrossTargets(identity)

mandatoryRevocations = invalidOrExpiredGrants(actual, desired)
executeRequiredRevocations(mandatoryRevocations)

reviewCandidates = exceptionalOrAmbiguousGrants(actual, desired)
assignToAuthorizedReviewers(reviewCandidates)
trackAndVerifyAllRemediations()
~~~

Việc bắt buộc thu hồi entitlement đã không còn hợp lệ phải theo mốc hiệu lực, **không chờ người review bấm nút**. Review xử lý những trường hợp còn phụ thuộc bối cảnh nghiệp vụ, chẳng hạn role dự án được cấp ngoài role chuẩn hoặc quyền nhạy cảm cần owner tái xác nhận.

Ví dụ nhân viên chuyển Finance → Engineering: role tài chính cơ sở có thể bị gỡ theo policy, trong khi quyền xem một báo cáo thuộc dự án chuyển tiếp phải được data owner xác minh scope và thời hạn, nếu được phép.

### Leaver — thu hồi, rồi đối soát quyền tồn dư

Khi HRIS/VMS xác nhận quan hệ kết thúc, IAM thu hồi quyền theo chính sách JML. Review ở đây đóng vai trò **kiểm chứng và điều tra sai lệch**:

- Có account local, tài khoản đặc quyền hoặc token không liên kết với IdP?
- Đã gỡ nhóm ở SaaS nhưng còn quyền chia sẻ trực tiếp?
- Có quyền còn tồn tại do connector lỗi, tài khoản dịch vụ gắn nhầm với con người hoặc tenant bị bỏ sót?
- Có yêu cầu review/cấp quyền đang chờ phải hủy vì beneficiary đã nghỉ?

**Không dùng review để hỏi “có nên giữ quyền của Leaver không?”** khi nguồn có thẩm quyền và policy đã xác định quyền phải kết thúc. Nếu cần lưu dữ liệu/hồ sơ vì pháp lý, lưu giữ không đồng nghĩa duy trì khả năng đăng nhập.

### Rehire và chuyển loại quan hệ

Người từng là nhân viên có thể trở lại dưới quan hệ nhà thầu. Review phải phân biệt **quan hệ cũ** với **quan hệ mới**, nguồn và ngày hiệu lực; không mặc định giữ role, approval hay ngoại lệ từ lần làm việc trước. Account có thể được tái sử dụng kỹ thuật nếu chính sách cho phép, nhưng entitlement cần được xác minh lại theo quan hệ hiện tại.

## 12. Review tài khoản dịch vụ, workload và tài khoản chia sẻ

Không thể hỏi một service account “bạn có còn cần quyền này không?” như hỏi nhân viên. Review cần gán tới **service owner** và **resource owner**, với chứng cứ từ service catalog, CI/CD và môi trường vận hành.

### Mẫu câu hỏi cho non-human identity

| Câu hỏi | Bằng chứng mong đợi |
|---|---|
| Workload/dịch vụ có còn hoạt động? | `serviceId`, trạng thái triển khai, owner, ticket thay đổi. |
| Quyền này dùng cho chức năng nào? | Job/workload, resource, action và scope. |
| Có thể giảm quyền hoặc tách vai trò không? | Quyền đang dùng, chính sách least privilege, phân loại môi trường. |
| Credential đang được quản lý ra sao? | Hình thức workload identity, token/key/certificate, owner và lịch rotation. |
| Có tài khoản hoặc credential trùng lặp không? | Inventory và liên kết tới workload/tenant. |
| Khi owner nghỉ việc thì sao? | Quy trình chuyển giao, kiểm tra credential gắn với người đó và review owner mới. |
| Dịch vụ đã retired chưa? | Event từ service catalog/orchestration và bằng chứng thu hồi tại đích. |

Nếu kỹ sư tạo robot CI/CD nghỉ việc, reviewer phải xác nhận người tiếp quản và đánh giá quyền/credential. **Không tự xóa robot còn phục vụ production chỉ vì owner cá nhân đã nghỉ**, nhưng cũng không được mặc định duy trì quyền vô thời hạn khi không có service owner xác định.

### Tài khoản chia sẻ và break-glass

Tài khoản chia sẻ cần chứng minh lý do tồn tại, người có thể sử dụng, cơ chế ghi nhận danh tính từng người, việc bảo vệ credential và kế hoạch chuyển sang tài khoản cá nhân khi khả thi. Tài khoản break-glass cần kiểm tra khả năng khôi phục, quyền đặc biệt, quản lý secret, cảnh báo sử dụng và luân chuyển credential sau sự kiện.

Khi một người được ủy quyền sử dụng break-glass rời tổ chức, cập nhật người được phép sử dụng/credential theo chính sách mà vẫn duy trì khả năng khôi phục đã thiết kế. Review thông thường không nên vô hiệu hóa hàng loạt account khẩn cấp đang là đường khôi phục duy nhất.

## 13. Một mô hình review campaign có thể kiểm toán

### Hợp đồng cấu hình chiến dịch

~~~yaml
# Ví dụ minh họa, không phải schema bắt buộc của một sản phẩm IAM.
campaign:
  id: review-privileged-prod-q4
  name: Rà soát quyền quản trị production
  ownerTeam: IdentityGovernance
  scope:
    environments: [production]
    accountTypes: [PRIVILEGED_USER, SERVICE_ACCOUNT]
    includeDirectGrants: true
    includeNestedGroups: true
    includeLocalAccounts: true
    systems:
      - cloud-prod
      - database-prod
  reviewPolicy:
    riskTier: HIGH
    reviewerAuthorities:
      - RESOURCE_OWNER
      - SERVICE_OWNER_FOR_WORKLOAD
    forbidSelfCertification: true
    allowKeepWithoutReason: false
    overdueAction: ESCALATE
  schedule:
    snapshotAt: "2026-10-01T00:00:00Z"
    decisionDueAt: "2026-10-15T17:00:00Z"
    remediationDueAt: "2026-10-22T17:00:00Z"
  completion:
    requireTargetReadback: true
    trackUnresolvedExceptions: true
~~~

Thời điểm, hệ thống và chu kỳ là ví dụ; phải chọn theo rủi ro và kế hoạch của tổ chức. Nên tách rõ **hạn reviewer ra quyết định** và **hạn hành động thu hồi hoàn tất**. Nếu người review chưa phản hồi, `overdueAction: ESCALATE` không có nghĩa tự động chứng nhận giữ quyền.

### Dữ liệu một review item

~~~json
{
  "campaignId": "review-privileged-prod-q4",
  "reviewItemId": "ri-8042",
  "subject": {
    "identityId": "idn-1042",
    "identityType": "EMPLOYEE",
    "source": "HRIS",
    "sourceRecordId": "EMP-1042"
  },
  "account": {
    "systemId": "cloud-prod",
    "tenantId": "production",
    "nativeAccountId": "user-9120"
  },
  "access": {
    "entitlementId": "prod-iam-admin",
    "scope": "project/reporting",
    "grantProvenance": "approved-request/ar-773",
    "grantedAt": "2026-08-10T12:00:00Z",
    "effectiveUntil": "2026-09-10T12:00:00Z"
  },
  "observedAt": "2026-10-01T00:00:00Z",
  "riskTier": "CRITICAL",
  "reviewer": {
    "identityId": "idn-2001",
    "authority": "RESOURCE_OWNER"
  },
  "decision": "PENDING",
  "remediation": "NOT_STARTED"
}
~~~

Ví dụ cho thấy entitlement đặc quyền **đã quá hạn nhưng vẫn tồn tại tại đích**. Review phải đặt mức rủi ro cao, đồng thời hệ thống cần tiến hành **thu hồi theo chính sách expiry/JML** thay vì đợi reviewer phản hồi. Một review item là bằng chứng về sai lệch và tiến trình xử lý; nó không cấp quyền tiếp tục sử dụng.

### Mẫu bản ghi quyết định

~~~json
{
  "reviewItemId": "ri-8042",
  "decision": "REVOKE",
  "reasonCode": "ACCESS_EXPIRED",
  "reviewerIdentityId": "idn-2001",
  "reviewedAt": "2026-10-02T09:10:00Z",
  "snapshotVersion": 18,
  "remediation": {
    "actionId": "act-9810",
    "state": "CONFIRMED",
    "targetObservedState": "ENTITLEMENT_ABSENT",
    "verifiedAt": "2026-10-02T09:11:30Z"
  }
}
~~~

Đây là dữ liệu minh họa. Khi readback thất bại thì không được tự điền `CONFIRMED` chỉ dựa trên việc connector trả HTTP 200; cần kiểm tra entitlement thực tế hoặc bằng chứng thủ công được chính sách chấp nhận.

## 14. Đối soát, retry và xử lý dữ liệu thay đổi giữa chiến dịch

Campaign thường kéo dài nhiều ngày. Trong thời gian đó, identity có thể Mover, Leaver, role bị sửa hoặc grant được cấp lại. Quy trình phải **kiểm tra dữ liệu hiện hành khi ra quyết định và khi thực thi**.

~~~text
applyReviewDecision(reviewItem, decision):
    verifyReviewerAuthority(reviewItem, decision.reviewer)
    verifyDecisionMatchesItemAndSnapshot(reviewItem, decision)
    current = loadAuthoritativeIdentityAndTargetGrants(reviewItem)

    if current.subjectIsTerminated:
        ensureMandatoryLeaverRevocation(current)
        recordReviewAsSupersededByLifecycleAction()
        return

    if current.grantChangedSinceSnapshot:
        reconcileOrRequireFreshReview(current, decision)
        return

    if decision == KEEP:
        requireBusinessReasonAndValidPolicy(current)
        recordCertificationEvidence()
        return

    if decision == REVOKE:
        planRemovalOfReviewedGrant(current)
        enqueueIdempotentRevocationAction()
        verifyObservedTargetState()
        recordRemediationEvidence()
        return

    if decision == MODIFY:
        requireApprovedNewScopeAndSodChecks()
        applyAndVerifyLeastPrivilegeChange()
        return

    openInvestigationOrAuthorizedException()
~~~

Giả mã thể hiện các điều kiện an toàn, không phải chương trình có thể chạy trực tiếp. Khi quyền được cấp từ nhiều nguồn, việc “remove reviewed grant” phải xét đúng cơ chế native của hệ thống đích. Nếu người dùng vẫn có entitlement từ nguồn hợp lệ khác, không được tuyên bố đã gỡ toàn bộ quyền hiệu lực; cần ghi đúng kết quả và lý do.

### Ba vấn đề đồng bộ thường gặp

**1. Quyền bị xóa trước khi reviewer quyết định.** Reviewer bấm `KEEP` dựa trên snapshot cũ. Hệ thống không được tái cấp quyền đã bị thu hồi bởi Leaver hoặc SoD; cần invalidated/đối soát lại.

**2. Quyền bị đổi scope.** Review cho quyền tenant VN không thể áp cho entitlement tenant SG được tạo sau snapshot. Đánh dấu đối tượng cũ đã thay đổi, tạo review item mới nếu cần.

**3. Connector bị lỗi.** Reviewer chọn `REVOKE`, API SaaS chưa cập nhật. Giữ remediation ở `FAILED`/`RETRYING`, gán owner, escalation và kiểm tra lại trạng thái. Phân biệt **quyết định đã hoàn thành** với **thu hồi đã được xác nhận**.

### Quy tắc kỹ thuật nên có

- Snapshot, review item và lệnh remediation có ID/version ổn định.
- Review decision được ghi nhận với identity của reviewer và thời điểm, tránh sửa ngược lịch sử không có audit.
- Retry có idempotency key, không nhân bản yêu cầu hoặc cấp lại quyền bị thu hồi.
- Bản ghi trạng thái mong muốn và quyền đọc lại ở đích tách biệt.
- Ghi correlation ID từ campaign → review item → action → target evidence.
- Rà soát phụ thuộc và scope của entitlement trước khi thu hồi để tránh tác động ngoài ý muốn.
- Quyền bắt buộc phải thu hồi theo JML, SoD hoặc expiry được xử lý ưu tiên, không chờ campaign.

## 15. Các tình huống review thực tế

### Tình huống A — Nhân viên đã Mover nhưng còn role cũ

HRIS cho biết nhân viên đã chuyển Finance → Engineering từ đầu tháng. IAM thấy role `FINANCE_ANALYST` và entitlement xem báo cáo vẫn còn tại ứng dụng.

**Cách xử lý:** nếu policy định nghĩa role chỉ hợp lệ cho Finance thì thu hồi theo sự kiện Mover; review xác nhận nguyên nhân, phát hiện quyền ngoài luồng và lưu bằng chứng ứng dụng đã gỡ. Nếu nhân viên còn một assignment dự án độc lập được duyệt, cần kiểm tra scope riêng thay vì xóa mọi quyền giống tên.

### Tình huống B — Nhà thầu có tài khoản sau khi hết hợp đồng

VMS báo hợp đồng đã hết hiệu lực; SaaS vẫn liệt kê account `ACTIVE`. Sponsor không trả lời yêu cầu tái chứng nhận.

**Cách xử lý:** không mặc định `KEEP` vì quá hạn. Kích hoạt Leaver và thu hồi theo nguồn có thẩm quyền, kiểm tra dữ liệu SaaS, ghi incident/exception nếu lỗi. Sponsor có thể cung cấp hợp đồng mới nhưng không thay thế bằng chứng quan hệ hiện tại chỉ bằng một lựa chọn trên màn hình review.

### Tình huống C — Privileged role không có lần sử dụng gần đây

Một quyền cloud admin đã không được sử dụng trong sáu tháng theo log khả dụng, nhưng owner nói quyền cần cho khôi phục khẩn cấp.

**Cách xử lý:** xem xét liệu đây có phải break-glass thật sự với quy trình bảo vệ/diễn tập, hay chỉ là đặc quyền vĩnh viễn không cần thiết. Nếu cần khôi phục, có thể thay bằng tài khoản break-glass quản trị riêng hoặc quy trình PAM/JIT phù hợp; có owner, chứng cứ thử nghiệm và vòng review độc lập.

### Tình huống D — Service account thiếu owner

Robot đồng bộ dữ liệu vẫn chạy; kỹ sư từng được ghi owner đã nghỉ việc. Review snapshot không có người có thẩm quyền xác nhận.

**Cách xử lý:** đánh dấu `INVESTIGATE` với mức ưu tiên theo đặc quyền. Tìm service owner từ catalog/đội vận hành, xác minh workload còn nhu cầu, chuyển ownership, rà soát credential/rotation. Không tự approve vì robot đang hoạt động; cũng không dừng workload production tùy tiện khi chưa có kế hoạch an toàn.

### Tình huống E — Manager chọn giữ tất cả quyền trong vài giây

Một reviewer nhận 200 entitlement, bấm `KEEP` hàng loạt mà không có lý do, trong đó nhiều quyền truy cập dữ liệu nhạy cảm khác tenant.

**Cách xử lý:** yêu cầu lý do cho quyền rủi ro cao, hiển thị mô tả quyền và scope, kiểm tra authority của reviewer, đưa trường hợp bất thường vào quality review. Có thể áp ngưỡng và xác nhận bổ sung theo chính sách; không dựa riêng vào số giây để kết luận quyết định là sai, mà kiểm chứng bằng quyền và bằng chứng.

## 16. Kiểm thử thiết kế review

Các ca kiểm thử cần bao phủ **dữ liệu, quyết định, authority, hành động và bằng chứng**:

| Ca kiểm thử | Đầu vào | Kết quả kỳ vọng |
|---|---|---|
| 1. Role hợp lệ | Nhân viên còn đúng công việc, role và scope | Reviewer có authority chọn `KEEP` với căn cứ, ghi lần review tiếp theo. |
| 2. Mover mất điều kiện | Đã chuyển bộ phận, entitlement cũ còn ở SaaS | Thu hồi bắt buộc, xác nhận trạng thái tại đích. |
| 3. Leaver trong campaign | HRIS xác nhận `TERMINATED` khi review chưa xong | Không cho `KEEP` khôi phục quyền; theo dõi deprovision. |
| 4. Tài khoản local | IdP không có account nhưng ERP vẫn có account riêng | Đưa vào scope, gán owner và chứng cứ kiểm tra/thu hồi. |
| 5. Quyền trực tiếp cloud | Entitlement không đến từ role catalog | Hiện rõ grant provenance, reviewer phù hợp, điều tra/cấp căn cứ hoặc thu hồi. |
| 6. Nhóm lồng nhau | User có quyền qua group cha/con | Hiển thị quyền hiệu lực, xử lý đúng quan hệ khi đổi group. |
| 7. Hai grant cùng entitlement | Một nguồn cấp bị revoke, nguồn khác còn hợp lệ | Thu hồi đúng grant, không phá quyền hợp lệ khác; audit chính xác quyền hiệu lực. |
| 8. Sai tenant | Reviewer chỉ có authority tenant VN, item tenant SG | Chặn quyết định và chuyển reviewer đủ thẩm quyền. |
| 9. Reviewer tự chứng nhận | User là beneficiary và reviewer của quyền đặc biệt | Chặn self-certification theo policy, chuyển reviewer độc lập. |
| 10. Review quá hạn | Reviewer không phản hồi trước due date | Escalate/điều tra, không tự động `KEEP`. |
| 11. Privileged role hết hạn | Expiry đã qua, account vẫn mang quyền | Thu hồi theo policy; campaign lưu drift và evidence. |
| 12. Service owner nghỉ việc | Workload còn chạy, owner không hợp lệ | Mở điều tra/chuyển owner và review credential; xử lý rủi ro. |
| 13. Snapshot cũ | Grant thay đổi sau khi reviewer mở item | Revalidate, invalidated hoặc yêu cầu review trên dữ liệu mới. |
| 14. Connector không phản hồi | Reviewer chọn `REVOKE` nhưng API lỗi | Remediation chưa hoàn tất, retry có kiểm soát, cảnh báo và theo dõi. |
| 15. HTTP thành công nhưng đích không đổi | SCIM trả thành công, quyền vẫn còn | Không đánh dấu `CONFIRMED`; đối soát tiếp. |
| 16. Modify giảm quyền | Reviewer yêu cầu chỉ đọc thay vì admin | Kiểm tra policy/SoD, gỡ đặc quyền thừa và xác minh scope mới. |
| 17. Ngoại lệ hết hạn | Exception có expiry đã qua | Kích hoạt khắc phục/thu hồi theo chính sách, không gia hạn im lặng. |
| 18. Dữ liệu `lastUsedAt` thiếu | Hệ thống không thu thập được log truy cập | Ghi thiếu dữ liệu, không suy account không dùng rồi tự xóa. |

Một bài test chỉ xem status của review item là chưa đủ. Với `REVOKE` hoặc `MODIFY`, cần kiểm chứng **đúng entitlement, đúng hệ thống/tenant, đúng native account** và không phát sinh lỗi cấp/thu hồi ngoài phạm vi.

## 17. Đo lường chất lượng review

**Tỷ lệ quyết định được trả lời** không đồng nghĩa với **tỷ lệ quyền sai đã được sửa**. Nên đo riêng:

| Chỉ số | Cách tính/ý nghĩa |
|---|---|
| **Review item decision completion** | Số item có quyết định hợp lệ / số item phải được quyết định trong scope. |
| **Remediation confirmation rate** | Số hành động bắt buộc đã xác minh ở đích / tổng hành động bắt buộc phát sinh. |
| **Overdue review rate** | Item quá hạn quyết định / item đang cần quyết định. |
| **Overdue remediation rate** | Action quá hạn xử lý / action bắt buộc chưa đóng hoặc toàn bộ action theo định nghĩa đã công bố. |
| **Reviewer authority coverage** | Item được gán reviewer có thẩm quyền / tổng item trong scope. |
| **Orphan/uncorrelated access** | Tài khoản/quyền chưa gắn được identity hoặc service owner hợp lệ. |
| **Privilege creep findings** | Quyền không còn phù hợp sau Mover, dự án kết thúc hoặc expiry. |
| **Direct grant drift** | Quyền cấp ngoài role/policy được phê duyệt. |
| **SoD findings** | Xung đột quyền hiệu lực hoặc quyền trong giao dịch chưa được giải quyết. |
| **Revocation latency** | Thời gian từ khi quyết định thu hồi có hiệu lực đến khi đích xác nhận đã gỡ quyền. |
| **Repeated KEEP without evidence** | Các quyết định giữ quyền thiếu căn cứ, nhất là quyền nhạy cảm; chỉ số chất lượng cần điều tra. |
| **Exception aging** | Ngoại lệ quá hạn hoặc thiếu owner/biện pháp bù trừ. |

### Ví dụ đọc kết quả chiến dịch

Giả sử chiến dịch có **100 review item**. Reviewer đã quyết định **95** item: 70 Keep, 20 Revoke, 5 Modify. Như vậy:

- **Decision completion = 95/100 = 95%**.
- Có **25** item yêu cầu thay đổi, tương ứng **20 Revoke + 5 Modify**.
- Nếu trong 25 hành động bắt buộc mới có 18 hành động được xác nhận tại đích thì **remediation confirmation = 18/25 = 72%**.

Không thể tuyên bố 95% review completion nghĩa là 95% rủi ro đã xử lý. Còn **5 item chưa có quyết định** và **7 remediation chưa xác nhận**; các đối tượng chưa đóng cần được phân loại theo mức rủi ro và có owner/SLA.

Cần ghi mẫu số rõ ràng để tránh báo cáo sai: tính theo item, theo entitlement, theo account hay theo action sẽ cho kết quả khác nhau. Với quyền production rủi ro cao, có thể phân tích riêng thay vì bị che khuất trong tỷ lệ tổng.

## 18. Các bước thiết kế access review program

Một lộ trình triển khai thực tế:

1. **Xác định mục tiêu và phạm vi:** kiểm soát quyền tồn dư, privileged access, dữ liệu nhạy cảm, nhà thầu, non-human identity; thống nhất hệ thống và tenant.
2. **Kiểm kê tài khoản/quyền:** tổng hợp nguồn danh tính, role catalog, IdP, ứng dụng, PAM, cloud, nhóm lồng nhau và quyền cấp trực tiếp.
3. **Đặt review policy theo rủi ro:** phạm vi, trigger, chu kỳ, người xét, quyền phải thu hồi tự động và các hạn quyết định.
4. **Chuẩn hóa dữ liệu chứng nhận:** grant provenance, owner, account/native ID, scope, expiry, last use nếu đáng tin, policy/approval ref.
5. **Giải quyết reviewer authority:** nguồn manager, sponsor, data/application/service owner; quy tắc independence, delegation và escalation.
6. **Thiết kế decision workflow:** Keep, Revoke, Modify, Investigate, Exception; khóa nội dung quyết định với version của item.
7. **Kết nối remediation:** SCIM/API/PAM/IaC/ticket có bằng chứng; action idempotent và readback entitlement ở đích.
8. **Kiểm thử end-to-end:** giả lập Mover/Leaver, reviewer sai authority, snapshot cũ, orphan, service owner nghỉ và connector lỗi.
9. **Pilot nhóm rủi ro cao:** đánh giá số item, chất lượng mô tả quyền, thời gian reviewer xử lý và tỉ lệ remediation đã xác minh.
10. **Vận hành và cải tiến:** theo dõi drift, quyền không sử dụng, tỷ lệ ngoại lệ, reviewer response và thay đổi account scope.

### Đầu ra nên bàn giao cho đội vận hành

- **Review scope matrix:** loại account/entitlement, hệ thống/tenant, mức rủi ro, chu kỳ/trigger, reviewer và owner.
- **Review policy:** tiêu chí Keep/Revoke/Modify, SoD, authority, expiry, escalation và ngoại lệ.
- **Data contract:** account/identity ID, grant provenance, mô tả quyền, snapshot version và trạng thái quan sát.
- **Workflow và SLA:** decision deadlines, remediation deadlines, trạng thái và đường retry.
- **Evidence contract:** ai xét, căn cứ gì, đã thực thi thao tác nào ở đích và được xác minh lúc nào.
- **Dashboard:** decision completion tách khỏi remediation completion, quá hạn, privileged drift và quyền tồn dư.

## 19. Những sai lầm thường gặp

- **Chỉ gửi danh sách tài khoản IdP:** bỏ qua account local, quyền cloud trực tiếp, nhóm lồng nhau và service account.
- **Cho reviewer duyệt tất cả mà không có mô tả entitlement:** biến access review thành thao tác xác nhận mang tính hình thức.
- **Giao mọi quyền cho manager:** manager có thể biết nhu cầu công việc nhưng không có authority với dữ liệu tenant hoặc quyền admin.
- **Cho beneficiary tự chứng nhận quyền nhạy cảm:** tạo xung đột lợi ích, thiếu thẩm quyền độc lập.
- **Tự `KEEP` khi hết hạn phản hồi:** giữ quyền bất thường chỉ vì reviewer vắng mặt.
- **Nhầm review với approval cấp quyền mới:** reviewer chứng nhận quyền đang có; quyền mới vẫn cần eligibility/approval/provisioning phù hợp.
- **Đợi review để thu hồi Leaver:** tăng thời gian quyền tồn dư sau khi quan hệ đã kết thúc.
- **Chỉ đánh dấu Revoke mà không thực thi:** dashboard báo hoàn thành dù quyền tại ứng dụng vẫn active.
- **Gỡ entitlement sai nguồn cấp:** xóa nhầm quyền hợp lệ do nhiều role cùng cấp hoặc không xử lý được direct grant trái policy.
- **Không kiểm tra snapshot đã cũ:** quyết định Keep có thể áp lại quyền đã bị thu hồi do Mover/Leaver.
- **Không xác định owner service account:** robot có quyền production nhưng không ai xác minh mục đích và credential.
- **KPI gộp quyết định với remediation:** làm mờ các trường hợp rủi ro cao chưa được khắc phục.
- **Ngoại lệ không có hạn và người chịu trách nhiệm:** quyền tạm thời dần trở thành quyền vĩnh viễn.

## 20. Bài tập thực hành: xây dựng chiến dịch review IAM

Một doanh nghiệp có HRIS cho nhân viên, VMS cho nhà thầu, IdP dùng SSO, ứng dụng quản lý chi phí hỗ trợ SCIM, hệ thống ERP local, cloud production và ba service account CI/CD. Đầu quý, nhóm IAM cần thực hiện review đối với:

1. Nhân viên A đã chuyển Finance sang Engineering nhưng vẫn có `FINANCE_ANALYST`.
2. Nhân viên B còn quyền quản trị cloud production được cấp cho sự cố đã kết thúc.
3. Nhà thầu C hết hợp đồng nhưng SaaS vẫn hiển thị account `ACTIVE`.
4. Nhân viên D có quyền `report:read` vừa từ business role vừa từ một request dự án.
5. Robot E truy cập bucket production, service owner cũ đã nghỉ việc.
6. Account break-glass F còn tồn tại và chưa được kiểm tra từ đợt diễn tập trước.

**Yêu cầu:** thiết kế chiến dịch để quản trị được cả quyết định reviewer và việc xử lý quyền thực tế.

1. Xây dựng **review scope matrix** cho sáu trường hợp, gồm system/tenant, loại account, quyền hiệu lực, risk tier, reviewer và trigger.
2. Chỉ ra trường hợp nào **phải thu hồi ngay theo JML/expiry** và trường hợp nào cần reviewer giải thích nhu cầu nghiệp vụ.
3. Viết một review item JSON cho tài khoản B, chứa native account ID, scope cloud, grant provenance, snapshotAt, reviewer authority và expiry.
4. Đề xuất quy tắc không cho self-certification và cơ chế xử lý khi manager, sponsor hoặc service owner không tồn tại.
5. Với nhân viên D, mô tả cách thu hồi đúng một nguồn grant mà không làm mất quyền hợp lệ từ nguồn khác.
6. Với robot E, xác định người cần xác nhận, cách chuyển owner, rà soát credential và xử lý khi workload không còn hoạt động.
7. Thiết kế luồng xử lý `REVOKE` cho SaaS và ERP local, có bước đọc lại trạng thái và escalation khi connector lỗi.
8. Đề xuất ít nhất tám ca kiểm thử, trong đó có snapshot lỗi thời, sai tenant, reviewer không có thẩm quyền và `REVOKE` chưa được xác nhận.
9. Từ một chiến dịch có 100 item, 95 decision và 18/25 remediation confirmed, tính các tỷ lệ và nêu điều chưa được phép kết luận.

### Tiêu chí nghiệm thu

Thiết kế review đủ khả năng triển khai khi:

- Có **phạm vi bao phủ rõ theo hệ thống, tenant, loại account và entitlement**.
- Có **owner/reviewer đủ authority**, kiểm soát tự chứng nhận, ủy quyền và quá hạn.
- Reviewer thấy **quyền hiệu lực, nguồn cấp, role/approval, trạng thái vòng đời, scope và rủi ro**.
- Đã phân biệt **hành động JML/expiry bắt buộc** với quyết định review cần phán đoán nghiệp vụ.
- Kết quả Keep/Revoke/Modify/Investigate/Exception có lý do và record phiên bản.
- Mỗi quyết định thu hồi/điều chỉnh có **action ID, trạng thái xử lý và bằng chứng quyền thực tế ở đích**.
- Có quy trình xử lý account local, direct grant, nhóm lồng nhau, workload và quyền đặc biệt.
- Dashboard phân biệt **review completion** và **remediation confirmation**, đồng thời phơi bày quyền tồn dư và ngoại lệ chưa hoàn tất.

**Xác định review là thiết kế cơ chế xác nhận rằng quyền truy cập vẫn có căn cứ hợp lệ trong suốt vòng đời danh tính.** Review có giá trị khi phát hiện được quyền không còn phù hợp, đưa ra quyết định bởi đúng owner và biến quyết định thành thay đổi đã được xác minh tại hệ thống đích. Kết hợp với JML, RBAC/ABAC, IdP, SCIM và đối soát liên tục, nó giúp giảm quyền truy cập tồn dư và tạo bằng chứng kiểm toán đáng tin cậy.
