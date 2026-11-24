# End date: ngày kết thúc quan hệ nhân sự và tác động đến vòng đời danh tính IAM

## 1. End date là gì?

Trong **nguồn dữ liệu nhân sự** (Human Resources Information System — HRIS), **end date** là thông tin về ngày kết thúc một quan hệ hoặc một giai đoạn công việc được hệ thống nhân sự quản lý. Tùy mô hình dữ liệu, trường này có thể là ngày kết thúc **hợp đồng lao động, quan hệ làm việc, đợt phân công, vị trí, dự án hoặc quyền bảo trợ cho nhà thầu**. Vì thế, chỉ nhìn thấy tên trường `endDate` chưa đủ để kết luận rằng mọi tài khoản của một người phải bị khóa.

Trong **Identity and Access Management (IAM)**, end date là một đầu vào quan trọng để kích hoạt thay đổi trong vòng đời **Joiner–Mover–Leaver (JML)**:

- **Joiner:** người sắp vào tổ chức có hợp đồng ngắn hạn hoặc chương trình thực tập đã biết trước ngày kết thúc; IAM cần dự kiến thời điểm hết quyền ngay từ khi cấp.
- **Mover:** một phân công dự án hoặc vai trò kết thúc, trong khi quan hệ lao động vẫn tiếp tục; IAM cần thu hồi **quyền theo phân công** mà không vô hiệu hóa nhầm danh tính chính.
- **Leaver:** quan hệ làm việc không còn hiệu lực; IAM cần thu hồi những đường truy cập dựa vào quan hệ đó theo thời điểm và chính sách được phê duyệt.

End date là **dữ liệu nghiệp vụ**, không phải bằng chứng rằng thao tác thu hồi đã được thực thi. Một bản ghi HR báo `endDate = 2026-11-30` và một ứng dụng vẫn chấp nhận token của người đó vào ngày 01/12 có thể cùng tồn tại khi quy trình IAM bị trễ hoặc chưa xử lý hết mọi đường truy cập.

**Mục tiêu học tập:** hiểu cách diễn giải end date theo đúng phạm vi, xác định thời điểm IAM phải xử lý, liên kết với IdP/SSO/SCIM và RBAC/ABAC, kiểm tra tài khoản dịch vụ và chứng minh quyền tồn dư đã được thu hồi.

## 2. Phân biệt các ngày dễ nhầm với end date

Một hồ sơ nhân sự có thể chứa nhiều ngày. Cần xác định **đối tượng mà ngày đó áp dụng** trước khi dùng nó để cấp hoặc thu hồi quyền.

| Trường hoặc khái niệm | Ý nghĩa thường gặp | Hành động IAM cần cân nhắc |
| --- | --- | --- |
| **Employment end date** | Ngày quan hệ lao động/hợp đồng kết thúc | Xét Leaver nếu không còn quan hệ làm việc hợp lệ khác |
| **Contract end date** | Ngày hợp đồng cụ thể hết hiệu lực | Thu hồi quyền gắn hợp đồng, rà soát việc gia hạn hoặc hợp đồng khác |
| **Assignment / project end date** | Ngày kết thúc phân công/vai trò/dự án | Thu hồi nhóm, entitlement và tài nguyên dự án; không mặc nhiên khóa tài khoản IdP |
| **Last working day** | Ngày làm việc cuối cùng, có thể khác ngày chấm dứt pháp lý | Căn cứ nghiệp vụ có thể ảnh hưởng thời điểm cần chặn truy cập |
| **Termination effective date** | Ngày quyết định kết thúc có hiệu lực theo HR | Dùng với chính sách để tính thời điểm thu hồi |
| **Account expiration** | Mốc hệ thống tài khoản hết hiệu lực | Kết quả kỹ thuật được thiết lập từ chính sách, có thể khác ngày HR |
| **Entitlement expiration** | Thời hạn của một quyền hoặc ngoại lệ riêng lẻ | Chỉ thu hồi quyền đó khi hết hạn |
| **Leave start/end date** | Thời gian tạm nghỉ, chưa chắc kết thúc quan hệ làm việc | Áp dụng chính sách nghỉ/tạm dừng tương ứng |
| **Record updated at** | Thời điểm HRIS sửa bản ghi | Giúp đối soát sự kiện, không tự xác định hiệu lực nghiệp vụ |

Ví dụ: Lan có hợp đồng lao động chưa xác định ngày kết thúc, nhưng được giao quản lý **Dự án Atlas đến 30/11**. End date của phân công Atlas chỉ nên dẫn tới rà soát/thu hồi quyền Atlas. Nếu coi đó là ngày kết thúc hợp đồng, IAM có thể khóa nhầm toàn bộ tài khoản làm việc của Lan.

Không có một cách đặt tên trường hoặc giá trị trạng thái thống nhất cho mọi HRIS. Một thiết kế tích hợp bắt buộc phải mô tả rõ **ngữ nghĩa** của từng trường, không suy đoán chỉ từ tên `endDate`.

## 3. End date là ngày lịch hay thời điểm chính xác?

Đây là rủi ro thường gặp nhất trong vận hành Leaver. Trường `endDate: "2026-11-30"` có dạng **date-only**: nó không chứa giờ và múi giờ. Để quyết định lúc nào tài khoản phải mất quyền, cần có **quy tắc hiệu lực được thống nhất**:

1. Ngày kết thúc có phải là **ngày cuối cùng còn được làm việc** (*inclusive*) không?
2. Hay đó là **ngày đầu tiên không còn được phép làm việc** (*exclusive*)?
3. Đồng hồ dùng **múi giờ của đơn vị tuyển dụng, địa điểm làm việc hay múi giờ chuẩn UTC**?
4. Quyết định thu hồi có phải **ngay lập tức** vì nghỉ việc khẩn cấp không?
5. Có ngoại lệ bàn giao được phê duyệt và thời hạn riêng không?

Hai cách diễn giải dẫn tới kết quả khác nhau:

| Quy ước của HRIS | Giá trị HR | Thời điểm mất quyền minh họa trong múi giờ Việt Nam |
| --- | --- | --- |
| **Ngày kết thúc là ngày cuối cùng được phép làm việc** | 30/11/2026 | Bắt đầu **01/12/2026 00:00 +07:00** |
| **Ngày kết thúc là ngày đầu tiên không còn hiệu lực** | 30/11/2026 | Bắt đầu **30/11/2026 00:00 +07:00** |

Hai hàng trên là **hai chính sách khác nhau**, không phải hai cách viết tương đương. Ví dụ trong bài sẽ dùng quy ước **ngày cuối cùng còn hiệu lực, tính bao gồm ngày kết thúc**. Theo quy ước này:

~~~text
HR employmentEndDate = 2026-11-30
HR businessTimeZone    = Asia/Ho_Chi_Minh
Quy ước                = last-active-day-inclusive
IAM revokeAt           = 2026-12-01T00:00:00+07:00
Tương đương UTC        = 2026-11-30T17:00:00Z
~~~

Đây là phép tính **minh họa** cho trường hợp đơn giản. Với tổ chức có nhiều múi giờ, lịch làm việc, quy tắc pháp lý hoặc ứng dụng cloud vận hành khác địa phương, cần lấy quy ước chính thức làm đầu vào. Không nên tự ghép `23:59:59` hoặc giả định ngày đó luôn là UTC. Đặc biệt, việc dùng “cuối ngày” với độ chính xác từng giây hoặc mili giây có thể tạo khoảng hở; mô hình **đầu khoảng thời gian không còn hiệu lực** thường rõ ràng hơn khi tính toán.

### Một date-only không nên được đổi thành timestamp một cách tùy tiện

Giá trị `2026-11-30` biểu diễn ngày lịch, còn `2026-11-30T00:00:00Z` là một thời điểm cụ thể. Chuyển trực tiếp từ dạng thứ nhất sang dạng thứ hai mà không có chính sách múi giờ có thể khiến tài khoản bị chặn sớm nhiều giờ. Hệ thống nên lưu **giá trị gốc và nguồn** đồng thời lưu **thời điểm đã suy diễn theo chính sách**, để kiểm toán có thể truy ngược quyết định.

## 4. End date phải gắn với đúng thực thể

Để tránh khóa nhầm hoặc bỏ sót, cần hiểu quan hệ giữa **person — employment/assignment — IAM identity — account — entitlement**.

~~~mermaid
flowchart TD
    P["Person<br/>Con người"] --> E1["Employment A<br/>Quan hệ làm việc"]
    P --> E2["Employment B<br/>Quan hệ làm việc khác, nếu có"]
    E1 --> J["Assignment Atlas<br/>Có end date riêng"]
    E1 --> I["IAM identity<br/>Danh tính số"]
    E2 --> I
    I --> A["Account tại IdP và ứng dụng"]
    J -->|"căn cứ chính sách"| R["Entitlement Atlas"]
    A -->|"sử dụng theo quyền thực tế"| T["Tài nguyên"]
    R --> T
~~~

Một người có thể có nhiều hợp đồng, nhiều phân công, hoặc hai tư cách làm việc hợp lệ. Vì vậy cần làm rõ:

- **End date của employment**: có còn quan hệ làm việc hợp lệ khác không? Nếu còn, quyền của quan hệ hết hạn phải được loại bỏ nhưng identity dùng chung có thể tiếp tục hợp lệ.
- **End date của assignment**: chỉ rút những quyền phát sinh từ nhiệm vụ đã kết thúc; giữ lại quyền nền tảng nếu vẫn có căn cứ.
- **End date của entitlement ngoại lệ**: đóng đúng phạm vi, không suy diễn rằng toàn bộ account hết hạn.
- **End date của contractor sponsorship**: khi không còn sponsor/chủ quản hợp lệ, phải xử lý quyền theo chính sách đối tác; không chờ một employee record không tồn tại trong HRIS.

Việc xác định đúng đối tượng phụ thuộc các mã định danh ổn định như `personId`, `workerId`, `employmentId`, `assignmentId`, `identityId`. Email, họ tên, username có thể thay đổi hoặc được tái sử dụng; không nên dùng riêng những giá trị này để nối hồ sơ nhân sự với tài khoản khi thu hồi quyền.

## 5. Dữ liệu cần có khi tích hợp end date vào IAM

Một sự kiện hoặc snapshot về end date chỉ đủ tin cậy nếu hệ thống biết **nguồn có thẩm quyền, thực thể áp dụng, trạng thái phê duyệt và thời điểm hiệu lực**.

| Dữ liệu | Ví dụ minh họa | Tác dụng |
| --- | --- | --- |
| `workerId`, `employmentId` | `worker-510`, `emp-2026-19` | Xác định quan hệ làm việc chính xác |
| `assignmentId` khi áp dụng cho dự án | `assignment-atlas-04` | Chỉ thu hồi phạm vi phân công liên quan |
| `endDate` | `2026-11-30` | Giá trị ngày gốc đã được HR xác nhận |
| `dateSemantics` | `last_active_day_inclusive` | Giải thích cách tính mốc thu hồi |
| `businessTimeZone` | `Asia/Ho_Chi_Minh` | Chuyển ngày sang thời điểm thực thi |
| `employmentStatus` | `active`, `terminated` | Đối chiếu trạng thái với end date |
| `approvalStatus` | `approved` | Phân biệt dự thảo với quyết định chính thức |
| `sourceSystem` | `example-hris` | Truy ra hệ thống có thẩm quyền |
| `sourceVersion` và `eventId` | `21`, `event-902` | Ngăn lặp hoặc ghi đè bằng sự kiện cũ |
| `recordedAt`, `effectiveAt` | Thời điểm nhập và thời điểm hiệu lực | Xác định độ trễ, xử lý thay đổi hồi tố |
| `reasonCode` (nếu được phép) | Mã lý do nghiệp vụ ở mức tối thiểu | Định tuyến quy trình phù hợp, tránh phát tán chi tiết nhạy cảm |

Không phải tổ chức nào cũng cần từng trường trên trong cùng một event. Nếu thiếu thông tin đủ để xác định quyền thu hồi an toàn, cần **đưa vào hàng xử lý ngoại lệ**, làm rõ theo nguồn có thẩm quyền và áp dụng chính sách rủi ro; không tự giả định giờ, trạng thái hay mục tiêu tài khoản.

## 6. Từ end date trong HRIS đến quyết định deprovisioning

Một luồng điển hình có thể được mô tả như sau:

~~~mermaid
flowchart TD
    H["HRIS: end date đã phê duyệt"] --> N["Kiểm tra ID, phiên bản, ngữ nghĩa ngày và timezone"]
    N --> Q{"Kết thúc employment,<br/>assignment hay quyền ngoại lệ?"}
    Q -->|"Employment"| E["Xác định các quan hệ làm việc còn hiệu lực"]
    Q -->|"Assignment / quyền"| A["Xác định entitlement thuộc phạm vi hết hạn"]
    E --> D["Tính tập quyền cần thu hồi theo chính sách JML"]
    A --> D
    D --> P["Lập lịch hoặc thực thi thu hồi tại mốc hiệu lực"]
    P --> I["IdP / provisioning / SCIM hoặc API đích"]
    I --> V["Đối soát account, nhóm, ACL, session/token và quyền thực tế"]
    V --> O{"Đã thu hồi đủ?"}
    O -->|"Chưa"| X["Retry, cảnh báo, xử lý ngoại lệ"]
    X --> V
    O -->|"Rồi"| L["Ghi nhận kiểm toán và đóng yêu cầu"]
~~~

Các bước chính:

1. **Tiếp nhận:** lấy từ HRIS hoặc nguồn quản trị được chỉ định, xác minh chữ ký/kết nối và tình trạng phê duyệt nếu có.
2. **Chuẩn hóa:** kiểm tra kiểu ngày, múi giờ, tính nhất quán với trạng thái, phiên bản và ID.
3. **Liên kết:** tìm đúng employment/assignment và các danh tính, tài khoản liên quan.
4. **Đánh giá chính sách:** xác định quyền được cấp theo quan hệ sắp kết thúc và quyền nào vẫn hợp lệ qua quan hệ khác.
5. **Tính thời điểm:** chuyển end date theo quy tắc nghiệp vụ và xử lý yêu cầu khẩn cấp khi được phép.
6. **Thực thi:** cập nhật IdP, nhóm/vai trò, ứng dụng đích, quyền trực tiếp và cơ chế phiên/token khi cần.
7. **Đối soát:** chứng minh quyền đã bị thu hồi tại nơi thực thi; retry hoặc chuyển xử lý thủ công khi phát hiện chênh lệch.
8. **Kiểm toán:** ghi căn cứ, quyết định, người phê duyệt (nếu có), mốc thời gian và kết quả thực tế.

**Không nên đóng quy trình chỉ vì HRIS đã có end date hay SCIM trả về thông báo gửi thành công.** Cần xác nhận quyền cuối cùng ở ứng dụng hoặc tài nguyên đích.

## 7. End date trong Joiner–Mover–Leaver

### 7.1. Joiner: hợp đồng có hạn ngay từ đầu

Giả sử nhà thầu bắt đầu ngày 01/11 và hợp đồng kết thúc sau ngày 30/11. IAM có thể tạo danh tính và tài khoản theo mốc bắt đầu, đồng thời **đặt lịch kết thúc quyền ngay khi phê duyệt cấp ban đầu**. Nếu tài khoản được tạo trước ngày làm việc đầu tiên, nó có thể ở trạng thái chưa được phép sử dụng cho đến khi điều kiện Joiner hoàn tất.

Việc biết end date sớm giúp tránh quyền vô thời hạn cho cộng tác viên, thực tập sinh và thành viên dự án ngắn hạn. Tuy nhiên, không nên nhầm hạn của **hợp đồng** với hạn của từng **quyền**: quyền truy cập dữ liệu nhạy cảm có thể cần thời hạn ngắn hơn, phê duyệt bổ sung và rà soát riêng.

### 7.2. Mover: kết thúc phân công nhưng chưa rời tổ chức

Một kỹ sư hết nhiệm vụ ở Dự án Alpha ngày 30/11 và sang Dự án Beta từ 01/12. IAM cần:

- Thu hồi quyền dự án Alpha theo mốc kết thúc phân công và ngoại lệ bàn giao hợp lệ.
- Cấp quyền dự án Beta sau khi các điều kiện và phê duyệt cần thiết được đáp ứng.
- Giữ tài khoản và quyền nền tảng nếu quan hệ lao động vẫn đang có hiệu lực.
- Kiểm tra các quyền Alpha bị gán trực tiếp hoặc qua nhóm lồng nhau, không chỉ nhóm “Alpha Developers” chính.

Nếu chỉ thêm quyền Beta mà không xử lý **assignment end date** của Alpha, người dùng sẽ tích lũy quyền (*privilege accumulation*) và tăng bề mặt tấn công.

### 7.3. Leaver: end date của quan hệ làm việc

Khi quan hệ làm việc kết thúc, IAM cần xác định tất cả đường truy cập phát sinh từ quan hệ đó:

| Đối tượng | Hành động cần xem xét |
| --- | --- |
| **IAM identity** | Chuyển trạng thái thích hợp khi không còn quan hệ làm việc hợp lệ |
| **Tài khoản IdP** | Vô hiệu hóa đăng nhập, thu hồi nhóm/role liên quan |
| **Ứng dụng qua SCIM/API** | Vô hiệu hóa hoặc thu hồi account/nhóm/entitlement tùy khả năng ứng dụng |
| **Tài khoản ứng dụng cục bộ** | Xử lý các account không đồng bộ qua IdP/SCIM |
| **Session, token, API key** | Thu hồi hoặc giới hạn tiếp tục sử dụng theo cơ chế của từng sản phẩm |
| **ACL và chia sẻ trực tiếp** | Loại bỏ các quyền không nằm trong nhóm trung tâm |
| **Tài nguyên và workload do người đó quản lý** | Chuyển giao chủ sở hữu, rà soát đặc quyền, khóa và quy trình vận hành |

End date là **tín hiệu**; quyết định xóa/vô hiệu hóa từng thực thể còn phụ thuộc chính sách tổ chức, nghĩa vụ lưu giữ hồ sơ và các quan hệ hợp lệ còn tồn tại. Đặc biệt cần phân biệt **vô hiệu hóa quyền** với **xóa vĩnh viễn bản ghi**: bản ghi danh tính hoặc lịch sử có thể cần giữ để phục vụ kiểm toán.

## 8. IdP, SSO, SCIM và giới hạn của một mốc end date

Trong chuỗi IAM:

- **IdP (Identity Provider)** kiểm soát trạng thái và xác thực danh tính. Khi tới mốc thu hồi, IdP có thể chặn phiên đăng nhập mới và điều chỉnh nhóm/thuộc tính.
- **SSO (Single Sign-On)** giảm số lần người dùng đăng nhập bằng nhiều tài khoản nhưng **không có nghĩa** mọi phiên trong ứng dụng tự kết thúc ngay khi trạng thái IdP đổi.
- **SCIM (System for Cross-domain Identity Management)** hỗ trợ cập nhật, vô hiệu hóa tài khoản và thành viên nhóm trên ứng dụng có hỗ trợ. SCIM không bảo đảm xử lý mọi vai trò cục bộ, ACL, key hoặc phiên đã cấp.
- **RBAC/ABAC** đánh giá vai trò và thuộc tính để xác định quyền. Việc một employment/assignment hết hạn phải được phản ánh trong **quyền hiệu lực**, không chỉ trên hồ sơ HR hoặc claim cũ.

Ví dụ, ở thời điểm mất quyền theo end date, IdP đã chuyển identity sang `disabled`, nhưng người dùng vẫn có session đang mở trong ứng dụng báo cáo. Nếu ứng dụng không đánh giá lại phiên và chưa thu hồi token, truy cập vẫn có thể tiếp diễn cho đến khi session/token hết hạn hoặc bị vô hiệu hóa tại ứng dụng. Quy trình Leaver cần biết khả năng revocation của từng hệ thống và đối soát phù hợp với yêu cầu rủi ro.

**Điểm kiểm soát:** không suy diễn “`active = false` trong IdP” đồng nghĩa “không còn quyền ở mọi resource”. Cần xác minh tại hệ thống đích, đặc biệt với tài nguyên nhạy cảm, ứng dụng không liên kết hoặc credential máy.

## 9. Ví dụ HR data và chính sách chuyển thành thời điểm thực thi

Dữ liệu dưới đây **chỉ minh họa**, không phải schema bắt buộc của HRIS, IdP hay SCIM:

~~~json
{
  "eventId": "hr-evt-902",
  "sourceSystem": "example-hris",
  "eventType": "employment.end_date_confirmed",
  "workerId": "worker-510",
  "employmentId": "emp-2026-19",
  "endDate": "2026-11-30",
  "dateSemantics": "last_active_day_inclusive",
  "businessTimeZone": "Asia/Ho_Chi_Minh",
  "approvalStatus": "approved",
  "sourceVersion": 21,
  "recordedAt": "2026-11-23T09:00:00+07:00"
}
~~~

Ví dụ **chính sách nghiệp vụ**: ngày 30/11 là ngày cuối cùng quan hệ còn hiệu lực; từ 00:00 ngày kế tiếp theo `Asia/Ho_Chi_Minh`, quyền dựa trên quan hệ đó không còn hợp lệ. IAM diễn giải:

~~~text
endDate của HR:           2026-11-30 (date-only)
effective cutoff:        2026-12-01T00:00:00+07:00
cutoff theo UTC:         2026-11-30T17:00:00Z
phạm vi:                 employmentId = emp-2026-19
hành động dự kiến:       đánh giá các quan hệ còn hiệu lực,
                         thu hồi quyền thuộc employment đã kết thúc,
                         vô hiệu hóa identity nếu không có quan hệ hợp lệ khác
bằng chứng hoàn tất:     trạng thái quyền tại các hệ thống đích
~~~

Mã giả minh họa cách diễn giải, **không phải cú pháp API thực tế**:

~~~text
onApprovedHrEvent(event):
    ensureIdempotent(event.eventId, event.sourceVersion)
    employment = resolveEmployment(event.workerId, event.employmentId)
    rejectIfStaleOrUntrusted(event, employment)

    rule = getApprovedEndDatePolicy(employment)
    revokeAt = convertBusinessDateToInstant(
        event.endDate, rule.dateSemantics, rule.businessTimeZone
    )

    if event.isEmergencyLeaver:
        revokeAt = applyApprovedEmergencyRule(event)

    affectedGrants = findGrantsDerivedFrom(employment)
    remainingRelations = findOtherValidRelations(employment.personId, revokeAt)
    targetChanges = recalculateEffectiveAccess(
        affectedGrants, remainingRelations, revokeAt
    )

    scheduleOrExecute(targetChanges, revokeAt)
    reconcileAtTargetSystemsAndAudit(event.eventId)
~~~

Trong mã giả này, `ensureIdempotent`, `rejectIfStaleOrUntrusted` và `recalculateEffectiveAccess` biểu đạt **trách nhiệm thiết kế**: hệ thống thật cần triển khai theo mô hình dữ liệu, quy tắc phê duyệt và công cụ cung cấp quyền của tổ chức.

## 10. Tình huống khó cần xử lý trước khi tự động hóa

### 10.1. End date còn để trống

`endDate = null` có thể nghĩa là **hợp đồng chưa có ngày kết thúc**, nhưng cũng có thể là **dữ liệu chưa nhập hoặc nguồn không hỗ trợ**. Không nên coi cả hai trường hợp là “quyền vĩnh viễn”. Cần dùng trạng thái, loại quan hệ làm việc, quy trình HR và yêu cầu rà soát định kỳ; tài khoản đối tác có thể bị giới hạn thời gian ngay cả khi HR không cung cấp end date.

### 10.2. Gia hạn hoặc hủy ngày kết thúc

HR có thể gia hạn hợp đồng từ 30/11 sang 31/12 hoặc hủy quyết định kết thúc. IAM phải hủy/điều chỉnh lịch thu hồi **dựa trên phiên bản và phê duyệt mới nhất**. Không được để một job cũ tiếp tục khóa nhầm tài khoản vào 01/12.

Nếu việc thu hồi **đã diễn ra**, việc kéo dài hợp đồng sau đó không nhất thiết cho phép khôi phục toàn bộ quyền cũ; cần đánh giá lại quyền hiện tại và điều kiện cấp theo chính sách.

### 10.3. Chấm dứt khẩn cấp

Trường hợp nghiêm trọng có thể yêu cầu cắt quyền **ngay khi nhận lệnh được ủy quyền**, không đợi hết ngày hoặc batch định kỳ. Chính sách phải xác định nguồn tín hiệu, người được phép ra quyết định, phạm vi thu hồi, xử lý phiên/token và cách ghi lại thời điểm thực thi. Không để một `endDate` trong tương lai trì hoãn hành động khẩn cấp đã được phê duyệt.

### 10.4. HR nhập lùi ngày hoặc gửi sự kiện đến muộn

Nếu ngày kết thúc đã qua nhưng sự kiện tới IAM hôm nay, hệ thống cần phản ứng theo chính sách hiện hành và kiểm tra độ trễ. **Không ghi lùi thời điểm thực thi** để báo cáo như thể tài khoản đã bị khóa từ ngày HR ghi nhận. Cần giữ cả `businessEffectiveAt`, `receivedAt`, `executedAt` và bằng chứng từ hệ thống đích.

### 10.5. Sự kiện trùng hoặc đảo thứ tự

Nguồn có thể gửi cùng một sự kiện nhiều lần hoặc một bản cập nhật cũ đến sau bản gia hạn mới. Dùng `eventId`, phiên bản nguồn, trạng thái có thẩm quyền và cơ chế **idempotency** để không tạo job thu hồi trùng hay ghi đè ngày mới bằng ngày cũ. Đối soát snapshot HRIS giúp phát hiện sự kiện bị thất lạc.

### 10.6. Nghỉ việc rồi quay lại

Với **rehire**, cần xác minh người và quan hệ tuyển dụng mới. Tài khoản cũ, nếu được phép tái sử dụng, phải được đánh giá lại phương thức xác thực, nhóm, role, entitlement, token và quyền chia sẻ trực tiếp. Không tự bật lại tất cả quyền từng có vì employee record mới trùng personId với đợt làm việc trước.

### 10.7. Nhiều hợp đồng hoặc nhiều vai trò đồng thời

Một người có thể kết thúc hợp đồng tại đơn vị A nhưng vẫn còn quan hệ hợp lệ tại B. IAM cần thu hồi đúng **quyền xuất phát từ hợp đồng A** và tính lại toàn bộ quyền hiệu lực. Nếu tất cả quan hệ hợp lệ đã hết, chính sách Leaver mới quyết định trạng thái identity tổng thể.

### 10.8. Tài khoản cục bộ, service account và chủ sở hữu rời tổ chức

Một nhân viên là owner của workload có thể nghỉ việc trong khi dịch vụ vẫn chạy hợp lệ. Không nên xóa workload identity tùy tiện theo end date của người đó. Thay vào đó, cần chuyển owner, xác nhận đội vận hành tiếp quản, rà soát role/secret của workload và thu hồi các đặc quyền cá nhân đã cấp cho người rời tổ chức.

## 11. Đối soát quyền tồn dư sau end date

**Quyền truy cập tồn dư** (*residual access*) là khả năng truy cập còn tồn tại sau khi nhu cầu hoặc quan hệ làm việc hợp lệ đã kết thúc. Với end date, đây là vấn đề cần kiểm soát tới **tài nguyên thực tế**.

Các đường truy cập thường bị bỏ sót:

| Đường truy cập | Vì sao có thể còn sau mốc kết thúc? | Cách xác minh |
| --- | --- | --- |
| Tài khoản IdP | Job khóa bị trễ, ID ánh xạ sai | Trạng thái IAM/IdP và kết quả thử xác thực hợp lệ theo quy trình |
| Ứng dụng SaaS | Đồng bộ SCIM/API lỗi hoặc chưa hỗ trợ | Trạng thái account, nhóm và entitlement thực tế |
| Tài khoản cục bộ | Không liên kết SSO/SCIM | Kiểm kê và đối soát tài khoản với identity |
| Quyền chia sẻ trực tiếp | ACL không đi qua nhóm tập trung | Kiểm tra ACL, link chia sẻ và quyền hiệu lực |
| Session và token | Token đã phát hành chưa bị thu hồi, cache hoặc phiên chưa hết hạn | Log xác thực, cơ chế thu hồi phiên/token, thời hạn còn lại |
| Khóa API, SSH, credential máy | Credential tồn tại ngoài quy trình HR | Kiểm kê, thu hồi và thay credential theo chủ sở hữu |
| Nhóm hoặc vai trò kế thừa | Còn đường quyền qua nhóm khác | Tính lại toàn bộ effective permission ở hệ thống đích |

Một báo cáo rà soát chỉ cho thấy “đã bỏ người dùng khỏi nhóm X” **không đủ** nếu người đó còn quyền qua nhóm Y hoặc ACL trực tiếp. Quy trình nên lưu bản chụp **quyền dự kiến** và đối chiếu với **quyền thực tế**, bao gồm ngoại lệ bàn giao còn hiệu lực.

### Chỉ số nên theo dõi

- **Time to revoke:** thời gian từ mốc phải thu hồi theo chính sách đến khi hệ thống đích xác nhận quyền thực tế đã bị chặn.
- **Overdue leavers:** số quan hệ lao động hết hạn nhưng còn tài khoản hoặc quyền đang hoạt động không có căn cứ.
- **Stale scheduled jobs:** số lịch thu hồi chưa cập nhật sau gia hạn, hủy hoặc thay đổi phiên bản HR.
- **Orphan accounts:** tài khoản không ánh xạ được về người hoặc quan hệ làm việc có thẩm quyền.
- **Residual entitlements:** số quyền vẫn có hiệu lực sau end date của assignment, employment hoặc ngoại lệ.
- **Reconciliation failures:** số hệ thống chưa xác nhận kết quả thu hồi hoặc đang xử lý lỗi đồng bộ.

Không có một ngưỡng chấp nhận phù hợp mọi tổ chức; SLA thu hồi phải phản ánh độ nhạy của tài nguyên, loại danh tính và yêu cầu nội bộ.

## 12. Kiểm toán và bảo vệ dữ liệu nhân sự

End date liên quan đến trạng thái công việc của con người nên cần được xử lý với **nguyên tắc tối thiểu hóa dữ liệu**. IAM thường chỉ cần mã tham chiếu đáng tin cậy, loại quan hệ, trạng thái/phê duyệt cần thiết, ngày/thời điểm hiệu lực và nguồn sự kiện; không cần sao chép hồ sơ nhân sự đầy đủ sang mọi ứng dụng hoặc token SSO.

Một dấu vết kiểm toán có thể ghi:

~~~json
{
  "sourceEventId": "hr-evt-902",
  "workerRef": "worker-510",
  "employmentRef": "emp-2026-19",
  "policy": "last-active-day-inclusive",
  "businessEndDate": "2026-11-30",
  "revokeAt": "2026-12-01T00:00:00+07:00",
  "target": "example-reporting-app",
  "action": "deactivate_account",
  "sourceVersion": 21,
  "executedAt": "2026-12-01T00:00:08+07:00",
  "result": "confirmed"
}
~~~

Đây là ví dụ về **một hành động**, không phải bằng chứng rằng mọi hệ thống đã thu hồi xong. Nếu cần đóng Leaver, phải tổng hợp trạng thái các mục tiêu liên quan và ghi nhận lỗi/ngoại lệ còn mở. Audit nên giữ được:

- **Căn cứ nghiệp vụ:** nguồn có thẩm quyền, phiên bản, approval và nghĩa của end date.
- **Quyết định IAM:** phạm vi quyền bị ảnh hưởng, quy tắc tính thời điểm và ngoại lệ.
- **Bằng chứng kỹ thuật:** thời điểm gửi, kết quả từng hệ thống đích, retry và xác nhận quyền hiệu lực.
- **Khả năng truy vết:** ai thay đổi end date hoặc phê duyệt ngoại lệ, khi nào và trên đối tượng nào.

Chỉ người có trách nhiệm được quyền đọc/sửa dữ liệu này; log không nên chứa giấy tờ cá nhân, thông tin chấm dứt hợp đồng chi tiết hoặc token. Thời gian lưu phải theo chính sách và nghĩa vụ áp dụng.

## 13. Tình huống thực hành

**Bối cảnh:** Hoàng là nhà thầu thuộc Dự án Nova với `employmentId = contract-44`. HR xác nhận **ngày cuối cùng còn hiệu lực là 30/11/2026** theo `Asia/Ho_Chi_Minh`. Hoàng sử dụng SSO để vào ứng dụng quản lý mã nguồn, có membership `nova-readers`, được chia sẻ trực tiếp một tài liệu và là người bảo trợ cho bot triển khai.

Ngày 23/11, HR xác nhận end date. Ngày 26/11, hợp đồng được gia hạn đến 15/12 và HR phát sự kiện mới. Tuy nhiên, một lịch deprovisioning cũ vẫn dự kiến chạy từ mốc 30/11.

**Yêu cầu xử lý đúng:**

1. Đối soát phiên bản nguồn và xác nhận sự kiện gia hạn là trạng thái mới nhất có thẩm quyền.
2. Tính lại thời điểm kết thúc từ ngày **15/12** theo quy tắc **ngày cuối cùng còn hiệu lực**: mốc chặn theo ví dụ là **16/12 lúc 00:00 +07:00**.
3. Hủy hoặc cập nhật job 30/11 để tránh khóa nhầm Hoàng trước thời hạn đã duyệt.
4. Rà soát entitlement riêng lẻ: gia hạn hợp đồng **không mặc nhiên gia hạn** mọi quyền đặc biệt; mỗi quyền vẫn tuân theo chủ sở hữu/phê duyệt/hạn tương ứng.
5. Khi đến mốc kết thúc hợp lệ, vô hiệu hóa/thu hồi các quyền thuộc hợp đồng, kiểm tra account ứng dụng, membership, chia sẻ trực tiếp, session/token và quyền đích.
6. Chuyển giao trách nhiệm owner của bot triển khai và xem xét credential/role của bot theo quy trình workload.
7. Ghi cả lịch cũ, sự kiện gia hạn, phiên bản HR, thời điểm thực thi cuối cùng và kết quả xác minh.

**Câu hỏi tự kiểm tra:**

1. Nếu HR chỉ gửi `endDate: "2026-11-30"` mà không mô tả inclusive/exclusive, có nên tự đổi thành `2026-11-30T00:00:00Z` không? **Không**; phải xác định quy tắc nghiệp vụ và múi giờ.
2. End date của phân công Dự án Nova có luôn buộc khóa IdP không? **Không**; nó có thể chỉ kết thúc quyền dự án, còn employment/identity vẫn hợp lệ.
3. IdP đã bị khóa nhưng ứng dụng vẫn chấp nhận token cũ: đã hoàn tất thu hồi chưa? **Chưa**; phải xử lý khả năng phiên/token theo cơ chế đích và đánh giá quyền hiệu lực.
4. Hợp đồng được gia hạn sau khi job khóa đã tạo thì sao? **Đối soát phiên bản mới nhất, tính lại chính sách và cập nhật/hủy job cũ**; không được để lịch lỗi thực thi.
5. Owner của bot nghỉ việc, có xóa ngay bot không? **Không mặc nhiên**; cần chuyển owner, rà soát đặc quyền và bảo đảm quy trình thu hồi không gây gián đoạn ngoài yêu cầu.

## 14. Checklist thiết kế quy trình sử dụng end date

Trước khi đưa một trường end date vào quy trình cấp/thu hồi tự động, đội HR, IAM và chủ hệ thống cần thống nhất:

| Câu hỏi thiết kế | Kết quả cần rõ |
| --- | --- |
| End date áp dụng cho thực thể nào? | Employment, contract, assignment hay entitlement |
| Nguồn nào có thẩm quyền sửa ngày này? | HRIS hoặc nguồn được phân quyền; tình trạng phê duyệt |
| Date-only mang ý nghĩa gì? | Inclusive/exclusive, timezone, mốc cắt quyền chính xác |
| Có sự kiện khẩn cấp hoặc khác ngày kết thúc không? | Quy tắc ưu tiên theo thẩm quyền và mức rủi ro |
| Một person có nhiều quan hệ hợp lệ không? | Quy tắc tính lại identity và entitlement khi một quan hệ hết |
| Hệ thống nào thực thi thu hồi? | IdP, SCIM, API, tài khoản cục bộ, ACL, token/credential |
| Nếu HR thay đổi hoặc gia hạn thì sao? | Hủy/cập nhật lịch cũ, kiểm tra phiên bản, xử lý hồi tố |
| Nếu một hệ thống đích lỗi thì sao? | Retry, cảnh báo, người xử lý, đối soát quyền hiệu lực |
| Chứng minh hoàn tất như thế nào? | Audit từ nguồn HR đến quyền thực tế ở từng hệ thống |

## 15. Kết luận

**End date** là thuộc tính quan trọng của **nguồn dữ liệu nhân sự** để IAM xác định **khi nào một quan hệ làm việc, phân công hay quyền có thời hạn hết hiệu lực**. Dùng đúng end date đòi hỏi hiểu loại bản ghi, nguồn có thẩm quyền, quy tắc ngày lịch và múi giờ, thời điểm nghiệp vụ có hiệu lực và trạng thái phê duyệt. Trong mô hình **Joiner–Mover–Leaver**, end date giúp cấp quyền có thời hạn từ đầu, xử lý chuyển vai trò không để lại quyền cũ và thu hồi có kiểm chứng khi người dùng rời tổ chức.

**HRIS cung cấp căn cứ, IAM quyết định theo chính sách, IdP/SSO/SCIM và các ứng dụng thực thi những phần việc của mình, còn kiểm toán phải xác nhận quyền hiệu lực cuối cùng.** Việc xử lý gia hạn, nhiều hợp đồng, sự kiện trễ, phiên/token, tài khoản dịch vụ và quyền chia sẻ trực tiếp là điều kiện cần để giảm quyền truy cập tồn dư.
