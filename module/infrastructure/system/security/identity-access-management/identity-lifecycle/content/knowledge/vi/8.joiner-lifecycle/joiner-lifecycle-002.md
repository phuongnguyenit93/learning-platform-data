# Sự kiện bắt đầu việc trong Joiner lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **sự kiện bắt đầu việc** (work start / employment start event) là gì và phân biệt với quyết định tuyển dụng, ký hợp đồng, tạo hồ sơ ứng viên hoặc tạo tài khoản sớm.
- Xác định **nguồn có thẩm quyền**, chủ thể, quan hệ làm việc, ngày giờ hiệu lực và dữ liệu tối thiểu để một sự kiện khởi phát **Joiner lifecycle** an toàn.
- Thiết kế cách nhận sự kiện từ HRIS/hệ thống hợp đồng, đối chiếu danh tính, xác minh điều kiện trước kích hoạt và tạo tài khoản/đăng ký phương thức xác thực tại **IdP**.
- Giải thích cách sự kiện dẫn tới cấp quyền theo **RBAC/ABAC**, đồng bộ **SCIM/API**, hỗ trợ **SSO** và xác minh quyền thực tế ở hệ thống đích.
- Phân tích tình huống bắt đầu việc trong tương lai, hủy ngày nhận việc, thay đổi ngày bắt đầu, tái tuyển dụng, nhà thầu, bản ghi trùng và sự kiện đến trễ.
- Đề xuất cách giám sát, kiểm toán, xử lý lỗi và đo lường thời gian cấp quyền nhằm giảm tài khoản mồ côi, quyền cấp sai và quyền truy cập tồn dư.

## 1. Sự kiện bắt đầu việc là gì?

Trong quy trình **Joiner–Mover–Leaver (JML)**, sự kiện bắt đầu việc là **thông tin nghiệp vụ từ nguồn được công nhận xác nhận rằng một quan hệ làm việc hoặc hợp tác bắt đầu có hiệu lực vào một thời điểm xác định**. Đó là một tín hiệu quan trọng để IAM quyết định **khi nào** cần kích hoạt danh tính, tài khoản và bộ quyền phục vụ công việc.

Ví dụ, một nhân viên đã nhận thư mời vào ngày 10/11, ký hợp đồng ngày 16/11 và có ngày bắt đầu làm việc là **01/12/2026, 08:00**. Những mốc này liên quan nhưng không đồng nghĩa:

| Mốc | Điều nó chứng minh | IAM có thể làm gì? |
| --- | --- | --- |
| **Được chọn / nhận offer** | Tổ chức có dự định tuyển dụng | Có thể tạo hồ sơ ứng viên; chưa mặc nhiên cấp quyền ứng dụng nội bộ |
| **Ký hợp đồng / hồ sơ được phê duyệt** | Có cơ sở nghiệp vụ cho việc gia nhập theo điều kiện cụ thể | Chuẩn bị danh tính, lịch hẹn xác minh, quy trình cấp phát nếu chính sách cho phép |
| **Sự kiện bắt đầu việc có hiệu lực** | Quan hệ làm việc thực sự bắt đầu theo nguồn có thẩm quyền | Đánh giá các điều kiện và kích hoạt quyền được phê duyệt đúng thời điểm |
| **Tài khoản/role đã provision** | Một hoặc nhiều hệ thống thực thi cấp phát | Phải kiểm tra kết quả thực tế, không suy diễn từ sự kiện HR |
| **Người dùng đăng nhập lần đầu** | Chủ thể sử dụng một account đã kích hoạt | Không nhất thiết là ngày bắt đầu việc; không phải điều kiện xác định trạng thái nhân sự |

**Sự kiện bắt đầu việc không đồng nghĩa “bật ngay mọi tài khoản”.** Nó là dữ liệu đầu vào để bộ điều phối IAM thực hiện chính sách dựa trên trạng thái nhân sự, xác minh danh tính, người quản lý, vai trò, ngày có hiệu lực và phê duyệt.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, sự kiện này đặc biệt quan trọng vì quyết định đầu vào khi **Joiner** ảnh hưởng toàn bộ vòng đời: liên kết nhầm chủ thể có thể khiến Mover không gỡ hết quyền hoặc Leaver bỏ sót tài khoản sau này.

### 1.1. Khác nhau giữa business event và technical event

- **Business event:** nguồn nhân sự xác nhận quan hệ làm việc bắt đầu, được sửa hoặc hủy. Sự kiện thể hiện **ý nghĩa nghiệp vụ**.
- **IAM lifecycle event:** hệ thống quản trị danh tính suy ra rằng cần thực hiện bước **Joiner** theo chính sách và điều kiện hiện tại.
- **Provisioning event:** thao tác cụ thể như tạo account IdP, thêm nhóm, gán role hoặc gửi SCIM đến ứng dụng.
- **Verification event:** hệ thống kiểm tra lại trạng thái tài khoản và quyền thực tế, xác nhận hoàn tất hoặc đưa lỗi vào xử lý.

Sự tách biệt này cho phép HRIS chính xác về quan hệ việc làm mà IAM vẫn ghi nhận lỗi cấp phát. Nếu HRIS phát sự kiện thành công nhưng ứng dụng CRM lỗi API, **sự kiện nghiệp vụ không sai**; lỗi nằm ở việc thực thi và đối soát tài nguyên.

## 2. Nguồn nào được quyền phát sinh sự kiện bắt đầu việc?

Nguồn có thẩm quyền (**authoritative source**) là nơi được tổ chức giao trách nhiệm xác nhận một loại dữ liệu nghiệp vụ nhất định. Không nên để mọi hệ thống đều có thể phát lệnh “người này đã bắt đầu làm” với độ tin cậy như nhau.

| Loại chủ thể | Nguồn nghiệp vụ thường có thẩm quyền | Điều cần xác nhận |
| --- | --- | --- |
| Nhân viên | HRIS / quy trình tuyển dụng – nhân sự đã được duyệt | Mã người, employment relationship, start date, đơn vị, loại lao động |
| Thực tập sinh hoặc nhân viên thời vụ | HRIS hoặc hệ thống quản lý lao động theo chính sách | Ngày bắt đầu/kết thúc, sponsor/manager, thời hạn |
| Nhà thầu và đối tác | Hệ thống quản lý hợp đồng/vendor hoặc nguồn sponsor được công nhận | Hợp đồng còn hiệu lực, người bảo lãnh, ngày hết hạn, phạm vi truy cập |
| Khách mời dự án | Hệ thống quản lý khách mời có approval | Lý do mời, người chịu trách nhiệm, thời hạn và tài nguyên |
| Service account / workload | Danh mục dịch vụ, nền tảng hạ tầng hoặc hệ thống đăng ký workload | Workload, owner, môi trường, quyền và vòng đời riêng |

**Không dùng sự kiện nhân sự để kích hoạt tự động tài khoản dịch vụ.** Danh tính phi con người không “bắt đầu đi làm” theo nghĩa HRIS. Khi người quản lý workload bắt đầu hoặc kết thúc việc làm, chỉ cần đánh giá thay đổi ownership và credential/role liên quan theo chính sách.

Một hệ thống email, CRM hoặc IdP có thể cho biết tài khoản tồn tại, nhưng thông thường **không phải nguồn quyết định quan hệ lao động đã bắt đầu**. Vì vậy, IAM nên truy nguồn trạng thái nhân sự/hợp đồng và không suy luận Joiner chỉ vì có ai đó đăng nhập lần đầu.

### 2.1. Bốn nhóm thông tin cần kiểm chứng từ nguồn

1. **Ai bắt đầu:** định danh nguồn của chủ thể và cách liên kết với identityId nội bộ.
2. **Quan hệ nào bắt đầu:** employee, contractor, internship, loại hợp đồng, pháp nhân hoặc organization.
3. **Khi nào bắt đầu:** ngày giờ có hiệu lực và múi giờ/điều kiện áp dụng.
4. **Vì sao và ai chịu trách nhiệm:** quyết định phê duyệt, người quản lý/sponsor, hồ sơ nguồn còn hợp lệ.

Thông tin “tên người dùng” hoặc “email dự kiến” không đủ làm căn cứ xác định chủ thể. Email có thể thay đổi hoặc được cấp lại; mã quan hệ việc làm và **định danh nội bộ ổn định** cần được ánh xạ rõ ràng.

## 3. Thời gian: yếu tố quyết định ý nghĩa sự kiện

Một bản ghi HR có thể được tạo trước ngày đi làm nhiều ngày, bị chỉnh sửa sau đó hoặc truyền tới IAM khi đã quá giờ hiệu lực. Vì vậy cần phân biệt ít nhất các mốc sau:

| Thuộc tính thời gian | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **recordCreatedAt** | Thời điểm tạo bản ghi HR | 23/11, 09:00 |
| **eventPublishedAt** | Thời điểm nguồn phát sự kiện | 23/11, 09:10 |
| **receivedAt** | Thời điểm IAM nhận thông báo | 23/11, 09:11 |
| **startEffectiveAt** | Khi quan hệ làm việc bắt đầu có hiệu lực | 01/12, 08:00 |
| **provisionedAt** | Khi tài khoản/nhóm được tạo hoặc thay đổi | Có thể trước hoặc sau startEffectiveAt |
| **accessActivatedAt** | Khi quyền sử dụng thực sự được phép | Theo chính sách, thường gần startEffectiveAt |
| **verifiedAt** | Khi IAM xác nhận trạng thái thực tế | Sau khi các hệ thống đích phản hồi |

Các mốc là ví dụ về mô hình dữ liệu. Tên field phụ thuộc từng HRIS và pipeline của doanh nghiệp.

**Tạo trước khác kích hoạt trước.** Doanh nghiệp có thể chuẩn bị tài khoản IdP, mailbox hoặc thiết bị trước ngày bắt đầu nhằm giúp onboarding đúng giờ; nhưng **quyền sử dụng dữ liệu và ứng dụng nhạy cảm** vẫn phải tuân theo chính sách và thời điểm có hiệu lực.

### 3.1. Date-only, múi giờ và ranh giới ngày

HRIS có thể chỉ lưu `startDate: 2026-12-01` mà không có thời gian. Không nên mặc định “bắt đầu lúc 00:00 UTC” nếu nghiệp vụ hiểu là **08:00 tại văn phòng**. Tổ chức cần định nghĩa quy tắc quy đổi cụ thể, chẳng hạn:

- Sự kiện chỉ có ngày có hiệu lực theo múi giờ của **đơn vị sử dụng lao động** hoặc địa điểm làm việc.
- Quyền nào được mở từ đầu ngày, quyền nào cần chờ **giờ ca làm**.
- Người làm việc đa quốc gia hoặc từ xa dùng múi giờ nào.
- Cách xử lý thay đổi giờ mùa hè, nếu có, tại địa điểm áp dụng.
- Nếu giờ hiệu lực chưa đủ dữ liệu, hệ thống có cho phép chuẩn bị account nhưng chặn đặc quyền không.

Ví dụ, 08:00 ngày 01/12 tại Việt Nam tương đương 01:00 UTC. Bỏ qua offset có thể khiến account được mở **sớm hoặc trễ nhiều giờ**.

### 3.2. Sự kiện tương lai, sửa ngày và hủy nhận việc

Một Joiner có thể chuyển từ dự kiến 01/12 sang 07/12 hoặc bị hủy trước ngày bắt đầu. IAM cần nhận **sự kiện thay thế/hủy** và cập nhật lịch kích hoạt.

Ví dụ:

~~~text
23/11: HR phát START_SCHEDULED (01/12 08:00)
25/11: HR phát START_DATE_CHANGED (07/12 08:00)
28/11: HR phát JOINER_CANCELLED

Hành vi mong muốn:
- Không kích hoạt tài khoản ngày 01/12 theo lịch cũ.
- Hủy lịch ngày 07/12 khi nhận sự kiện hủy.
- Khóa hoặc gỡ tài khoản/quyền đã chuẩn bị nếu không còn cơ sở nghiệp vụ.
- Lưu audit cho cả ba sự kiện và kết quả xử lý.
~~~

Trường hợp đã cấp sớm quyền hạn chế cho người chuẩn bị nhận việc, khi sự kiện bị hủy phải **thu hồi quyền đó** và kiểm tra các hệ thống đích. Nếu không, tài khoản “chưa từng là nhân viên chính thức” có thể trở thành tài khoản mồ côi.

## 4. Hợp đồng sự kiện bắt đầu việc

Một hệ thống IAM không nên phải đoán ý nghĩa chỉ từ tên event. Sự kiện nên mang dữ liệu đủ để đối chiếu nguồn và chống xử lý trùng/sai thứ tự.

### 4.1. Mẫu sự kiện minh họa

~~~json
{
  "eventId": "hr-start-20261201-00721",
  "eventType": "WORK_START_EFFECTIVE",
  "sourceSystem": "HRIS",
  "sourcePersonId": "employee-00721",
  "employmentRelationshipId": "employment-31024",
  "identityId": "person-11023",
  "workerType": "EMPLOYEE",
  "employmentStatus": "ACTIVE",
  "organizationUnit": "Finance",
  "positionCode": "FIN-ANALYST",
  "managerIdentityId": "person-00308",
  "startEffectiveAt": "2026-12-01T08:00:00+07:00",
  "endEffectiveAt": null,
  "eventPublishedAt": "2026-11-30T17:00:00+07:00",
  "sourceRecordVersion": 15,
  "correlationId": "joiner-5e81c"
}
~~~

Đây là **JSON minh họa do hệ thống thiết kế**, không phải schema tiêu chuẩn do SCIM, OIDC hay HRIS bắt buộc. Tùy nguồn, trường `identityId` có thể **chưa tồn tại** khi sự kiện đến; bộ điều phối cần phân giải danh tính từ hồ sơ nguồn và tạo/link ID đúng trước khi cấp phát.

### 4.2. Các trường quan trọng

| Nhóm | Field ví dụ | Mục đích |
| --- | --- | --- |
| Định danh sự kiện | eventId, correlationId | Nhận diện bản tin, lần xử lý, toàn bộ chuỗi audit |
| Nguồn | sourceSystem, sourcePersonId | Xác thực hệ thống phát và ánh xạ hồ sơ |
| Quan hệ | employmentRelationshipId, workerType | Tránh nhầm một người có nhiều quan hệ với tổ chức |
| Đối tượng nội bộ | identityId (nếu có) | Liên kết danh tính bền vững |
| Ngữ cảnh vai trò | organizationUnit, positionCode, managerIdentityId | Tính quyền và xác định người phê duyệt |
| Trạng thái | eventType, employmentStatus | Diễn giải hành động nghiệp vụ |
| Thời gian | startEffectiveAt, eventPublishedAt | Lập lịch, đối chiếu độ trễ |
| Phiên bản | sourceRecordVersion | Phát hiện sự kiện cũ đến trễ |
| Kết thúc | endEffectiveAt (nếu có) | Quản lý hợp đồng có hạn và lên lịch Leaver |

**Sự kiện chỉ chứa `email` và `isActive=true` là không đủ an toàn** cho quá trình Joiner tự động: không rõ người nào, nguồn nào, hiệu lực khi nào, hợp đồng nào và có phải bản ghi mới nhất hay không.

### 4.3. Xác thực và giảm dữ liệu trong sự kiện

Event bus hoặc webhook nhân sự phải kiểm tra nguồn gửi, cơ chế xác thực/chữ ký nếu áp dụng, phân quyền subscriber và tính toàn vẹn. Payload chỉ nên chứa dữ liệu phục vụ điều phối; không đưa mật khẩu, private key, bản quét giấy tờ định danh hoặc dữ liệu cá nhân không cần thiết vào mọi hàng đợi.

Event log và dead-letter queue cũng cần quyền truy cập phù hợp và thời hạn lưu. Dữ liệu nhân sự nhạy cảm không nên bị phát tán sang các ứng dụng không có quyền biết.

## 5. Từ sự kiện HR đến quy trình Joiner

~~~mermaid
flowchart TD
  A["HRIS / Nguồn hợp đồng"] --> B["Sự kiện bắt đầu việc"]
  B --> C{"Nguồn, định danh, phiên bản hợp lệ?"}
  C -->|"Không"| X["Đưa ngoại lệ / xử lý có owner"]
  C -->|"Có"| D["Xác minh hoặc liên kết identity"]
  D --> E{"Ngày có hiệu lực đã đến?"}
  E -->|"Chưa"| F["Chuẩn bị theo policy + lập lịch"]
  F --> E
  E -->|"Rồi"| G{"Proofing, approval, điều kiện bảo mật đủ?"}
  G -->|"Chưa"| Y["Chờ điều kiện / cảnh báo"]
  G -->|"Đủ"| H["Tính quyền tối thiểu theo role/attributes"]
  H --> I["IdP, directory, SCIM/API, ứng dụng"]
  I --> J["Đọc quyền và trạng thái thực tế"]
  J --> K{"Các hệ thống trong scope đã đúng?"}
  K -->|"Chưa"| L["Retry, alert, remediation"]
  L --> J
  K -->|"Đã đúng"| M["Đóng workflow + audit"]
~~~

Sơ đồ thể hiện **lô-gic điều phối**, không bắt buộc mọi hệ thống phải provision sau đúng thời điểm hiệu lực. Một số account có thể tạo trước theo chính sách; cần có biện pháp bảo đảm khả năng truy cập được **kích hoạt đúng thời điểm**.

### 5.1. Bước 1 – Tiếp nhận và kiểm tra sự kiện

Kiểm tra nguồn phát, schema, eventId, mã hồ sơ, loại quan hệ và phiên bản. Nếu có hai hệ thống cùng công bố sự kiện “bắt đầu” cho một người, phải xác định **nguồn nào có thẩm quyền cho quan hệ đó**.

Tình huống thiếu eventId, status chưa rõ hoặc nguồn mới thêm mã trạng thái phải được đưa vào luồng xử lý rõ ràng. Không tự mặc định một sự kiện lạ là “hợp lệ để cấp account”.

### 5.2. Bước 2 – Phân giải và xác minh danh tính

**Identity resolution** xác định hồ sơ này có tương ứng một danh tính nội bộ đã tồn tại không. **Identity proofing** thiết lập độ tin cậy rằng đúng chủ thể được gắn với hồ sơ. **Authenticator binding** bảo đảm phương thức đăng nhập được đăng ký cho đúng danh tính.

Ví dụ, khi nhân viên tên An bắt đầu việc, hệ thống phải tránh liên kết account cũ chỉ vì email hiện tại trùng tên đăng nhập cũ. Dùng định danh nguồn, mối quan hệ, lịch sử và quy tắc rehire theo chính sách.

Các trường hợp cần chú ý:

- Người mới chưa được proofing đủ cho tài nguyên có mức rủi ro yêu cầu.
- Hai hồ sơ HR tương tự nhưng thuộc **hai người khác nhau**.
- Một người tái tuyển dụng có identity cũ cần được đối chiếu chặt chẽ.
- Nhà thầu dùng nguồn hợp đồng khác với HRIS nhân viên.
- Một người có nhiều employment relationships tại các pháp nhân khác nhau.

**Không cấp quyền khi chưa liên kết chắc chắn account với đúng chủ thể**, trừ quy trình ngoại lệ có thẩm quyền và biện pháp giới hạn phù hợp.

### 5.3. Bước 3 – Kiểm tra trạng thái nghiệp vụ và điều kiện kích hoạt

Sự kiện bắt đầu việc phải được đối chiếu với trạng thái nhân sự **mới nhất có thẩm quyền**. Nếu vừa có một sự kiện hủy trước giờ kích hoạt, không được mở quyền chỉ vì lịch đã được lập từ tuần trước.

Ngoài `startEffectiveAt`, IAM có thể kiểm tra:

- Hồ sơ đã được phê duyệt và xác minh đủ chưa.
- Người quản lý/sponsor vẫn đang hoạt động và có thẩm quyền chưa.
- Người lao động có loại hợp đồng và ngày kết thúc phù hợp không.
- Có lệnh chặn bảo mật hoặc tạm đình chỉ cần ưu tiên không.
- Có phạm vi truy cập được phê duyệt và điều kiện thiết bị/MFA cần thiết không.

**HRIS ACTIVE không tự động xóa mọi chặn bảo mật tại IdP.** Nếu tài khoản bị khóa do nghi ngờ chiếm quyền, sự kiện HR phải qua quy trình mở khóa đúng thẩm quyền, không tự bật lại.

### 5.4. Bước 4 – Xác định quyền khởi tạo

Quyền cần được tính từ **vai trò, phòng ban, vị trí, nhu cầu công việc và thuộc tính hiện tại**, không chỉ từ sự kiện “đã bắt đầu”.

Ví dụ nhân viên Finance mới cần:

1. Một danh tính IdP để đăng nhập.
2. Nhóm nhân viên chung và MFA theo chính sách.
3. Quyền đọc báo cáo thuộc đơn vị Finance sau approval.
4. Không có quyền `admin` chỉ vì thuộc nhóm Finance.
5. Không có quyền truy cập dự án cũ của một người trùng tên hoặc role mẫu rộng quá mức.

**RBAC** mô tả quyền theo vai trò; **ABAC** giới hạn theo thuộc tính như đơn vị, địa điểm, phân loại dữ liệu và thời gian. Các quyền ngoại lệ nên có **người phê duyệt, lý do và hạn sử dụng**.

### 5.5. Bước 5 – Tạo account, đăng ký xác thực và đồng bộ quyền

Quá trình có thể gồm:

- **Identity registry/IGA:** tạo hoặc liên kết danh tính và lưu workflow.
- **IdP / directory:** cấp tài khoản và liên kết đúng identityId.
- **Authentication enrollment:** đăng ký MFA/passkey hoặc cơ chế phù hợp, tránh để credential rơi vào tay sai người.
- **SSO:** thiết lập quan hệ đăng nhập với ứng dụng theo chính sách.
- **SCIM/API:** tạo tài khoản ứng dụng, thêm nhóm hoặc cập nhật trường có hỗ trợ.
- **RBAC/ABAC / application entitlement:** cấp quyền theo quyết định đã được phê duyệt.

**SSO chủ yếu giải quyết xác thực**, không tự bảo đảm mỗi ứng dụng đã có đúng role. **SCIM hỗ trợ provisioning**, song phạm vi hỗ trợ khác nhau giữa các ứng dụng; quyền cấp cục bộ, phiên hoặc token có thể cần cơ chế quản lý riêng.

### 5.6. Bước 6 – Đối soát và hoàn tất

Sau khi gửi lệnh, hệ thống cần kiểm tra **observed state** tại hệ thống đích so với **desired state** đã được phê duyệt:

| Thành phần | Trạng thái mong muốn | Cách xác minh |
| --- | --- | --- |
| IdP | Account đúng identity, trạng thái kích hoạt hợp lệ | Đọc tài khoản, ID, trạng thái và điều kiện bảo vệ |
| Ứng dụng SaaS | Account tồn tại, đúng nhóm/role | Đọc lại user/group/entitlement qua API hoặc báo cáo |
| VPN / cloud | Chỉ có quyền nằm trong scope | Tra quyền hiệu lực và phiên liên quan |
| Access review | Những quyền nhạy cảm có owner và approval | Kiểm tra bản ghi phê duyệt và hạn quyền |
| Nhật ký | Có nguồn HR, policy, actor, request và kết quả | Correlation ID nối các bước |

Chỉ đánh dấu Joiner **COMPLETED** khi đáp ứng **tiêu chí hoàn tất** mà tổ chức đặt ra cho các hệ thống thuộc phạm vi sự kiện. Có thể có trạng thái `PARTIAL` hoặc `BLOCKED` khi một ứng dụng lỗi; cần người chịu trách nhiệm và thời hạn xử lý.

## 6. Mô hình trạng thái: chuẩn bị, kích hoạt, hoàn tất

Một workflow Joiner thường được triển khai dưới dạng **máy trạng thái**, giúp giải thích tại sao “có account” khác “được làm việc”.

~~~mermaid
stateDiagram-v2
  [*] --> RECEIVED: Có event hợp lệ
  RECEIVED --> PREPARING: Ngày bắt đầu chưa tới
  RECEIVED --> VALIDATING: Ngày bắt đầu đã tới
  PREPARING --> VALIDATING: Đến effectiveAt
  VALIDATING --> BLOCKED: Thiếu proofing / approval / nguồn sai
  BLOCKED --> VALIDATING: Điều kiện được bổ sung
  VALIDATING --> PROVISIONING: Đủ điều kiện
  PROVISIONING --> VERIFYING: Các thao tác đã gửi
  VERIFYING --> PARTIAL: Hệ thống đích chưa xác nhận
  PARTIAL --> VERIFYING: Retry / remediation
  VERIFYING --> COMPLETED: Desired = observed
  PREPARING --> CANCELLED: Hủy nhận việc
  BLOCKED --> CANCELLED: Hủy nhận việc
  CANCELLED --> [*]
  COMPLETED --> [*]
~~~

Đây là **mô hình trạng thái minh họa**, không phải workflow chuẩn bắt buộc.

**Tình huống hủy sau khi đã provision một phần:** không chỉ chuyển cờ `CANCELLED`, mà còn phải thu hồi account/quyền đã tạo, xử lý credential, xác minh kết quả và lưu audit. Nếu không, trạng thái workflow có thể đã “đóng” nhưng quyền truy cập vẫn tồn tại.

Trong môi trường có nhiều hệ thống, nên lưu từng **subtask** theo ứng dụng, gồm request, trạng thái đích, lần thử, lỗi và người phụ trách. Điều này tránh tình trạng một hệ thống thất bại khiến toàn bộ workflow trở nên khó truy vết.

## 7. Xử lý sự kiện lặp, đến trễ và sai thứ tự

Tích hợp HRIS–IAM thường không bảo đảm một sự kiện chỉ được giao đúng một lần, hoặc sự kiện đến theo đúng thứ tự nghiệp vụ. Các tình huống:

- Worker nhận cùng một event nhiều lần do retry.
- Event `START_SCHEDULED` đến sau event `JOINER_CANCELLED`.
- HRIS sửa ngày bắt đầu nhưng job đã được đặt lịch theo ngày cũ.
- Sau khi Leaver có hiệu lực, một bản tin Joiner cũ đến muộn.
- Nguồn nhân sự chỉnh sửa hồi tố một ngày đã qua.

### 7.1. Idempotency

**Idempotency** nghĩa là xử lý lại cùng yêu cầu không làm sai trạng thái hoặc cấp quyền thừa. Ví dụ: nhận lại sự kiện `hr-start-00721` không được tạo thêm IdP account mới hoặc cấp thêm quyền `admin`.

Một thiết kế có thể lưu **eventId đã xử lý**, phiên bản hồ sơ, trạng thái hoàn tất từng hệ thống và khóa nghiệp vụ ổn định (`sourceSystem + employmentRelationshipId`). Nếu thao tác cấp phát đã thành công một phần, lần retry phải **tiếp tục các bước còn thiếu** thay vì lặp lại mọi thao tác gây trùng.

### 7.2. Phiên bản và trạng thái nguồn hiện tại

Có thể áp dụng quy tắc:

~~~text
onStartEvent(event):
    verifyTrustedSource(event)
    current = loadAuthoritativeEmployment(event.employmentRelationshipId)

    if duplicateEventId(event.eventId):
        return existingProcessingResult

    if event.version isOlderThan current.version:
        recordStaleEvent(event)
        return NO_NEW_ACCESS

    if current.isCancelled or current.isTerminated:
        cancelPendingActivation()
        ensurePreparedAccessIsRevoked()
        return BLOCKED_OR_REVOKING

    if now < current.startEffectiveAt:
        scheduleActivationFor(current.startEffectiveAt)
        return PREPARED

    if not current.identityProofed or not current.approvalsSatisfied:
        return WAITING_FOR_CONDITIONS

    desiredAccess = calculateMinimumRequiredAccess(current)
    provisionAndReconcile(desiredAccess)
    return confirmedStatus()
~~~

Đây là **mã giả**, không phải API sẵn có. Dòng `event.version` giả định nguồn cung cấp version tăng nhất quán cho từng quan hệ việc làm; nếu không, đội tích hợp phải dùng chiến lược nhận diện bản ghi hiện hành phù hợp, tránh chỉ dựa vào thời điểm nhận sự kiện.

**Không tự coi sự kiện mới nhận là dữ liệu mới hơn.** Quy tắc phải phân biệt `publishedAt`, `effectiveAt`, version và trạng thái nghiệp vụ mới nhất.

### 7.3. Tác vụ theo lịch phải kiểm tra lại điều kiện

Khi lịch kích hoạt đến giờ, worker nên **đọc lại trạng thái hiện tại** trước khi mở quyền. Đây là chốt kiểm soát quan trọng để ngăn việc một lịch cũ khôi phục account đã bị hủy hoặc đang bị chặn bảo mật.

Ngoài ra, tác vụ cần theo dõi **timezone**, retry và cách xử lý downtime. Nếu hệ thống điều phối ngừng chạy trong giờ kích hoạt, khi phục hồi phải quyết định rõ: cấp quyền muộn, gửi cảnh báo và tính độ trễ, hay yêu cầu phê duyệt bổ sung nếu sự kiện đã quá cũ.

## 8. Các trường hợp đặc biệt của sự kiện bắt đầu việc

### 8.1. Preboarding và cấp quyền trước ngày đi làm

**Preboarding** có thể bao gồm chuẩn bị thiết bị, tài khoản, thư chào mừng hoặc cổng thông tin nhập hồ sơ. Rủi ro nảy sinh nếu những tài khoản chuẩn bị trước được cấp quyền xem dữ liệu nội bộ không cần thiết.

Cách triển khai an toàn thường tách:

- **Account được tạo:** tồn tại để chuẩn bị nhưng quyền đăng nhập hoặc truy cập dữ liệu được giới hạn.
- **Quyền preboarding:** chỉ cho những dịch vụ cần thiết, có hạn sử dụng và kiểm soát.
- **Quyền ngày bắt đầu:** chỉ mở sau khi kiểm tra `effectiveAt`, proofing, approval và trạng thái mới nhất.
- **Hủy nhận việc:** thu hồi account/quyền đã chuẩn bị, ngăn đăng nhập tiếp theo, kiểm tra quyền tồn dư.

Việc cấp trước một quyền nhất định không tự là sai; mức cấp trước phải được **phê duyệt theo chính sách và có giới hạn**.

### 8.2. Nhà thầu thời hạn ngắn

Một nhà thầu nhận việc hai tuần cần cả **ngày bắt đầu** và **ngày hết hạn** để IAM lập lịch Joiner lẫn Leaver. Nếu quy trình không có `endEffectiveAt` hoặc người chịu trách nhiệm, account có thể tồn tại vô thời hạn.

Kiểm soát nên có **sponsor**, hợp đồng đang hiệu lực, quyền chỉ trong phạm vi dự án, cách gia hạn và thu hồi khi hết hạn, kể cả khi hợp đồng kết thúc sớm.

### 8.3. Rehire – người cũ quay lại

Một người nghỉ việc rồi quay lại có thể giữ cùng định danh nội bộ nếu chính sách và bằng chứng cho phép, nhưng **quan hệ việc làm mới** có ngày hiệu lực, vai trò và phê duyệt mới.

Quy trình cần:

1. Kiểm tra hồ sơ cũ có tương ứng đúng chủ thể không.
2. Xác minh lại danh tính hoặc authenticator khi mức rủi ro yêu cầu.
3. Đánh giá có thể dùng lại account hay phải tạo account mới theo chính sách.
4. **Tính mới toàn bộ quyền hợp lệ**, không tự động kích hoạt quyền cũ hoặc credential đã thu hồi.
5. Kiểm tra các hệ thống đích và ghi rõ liên hệ giữa hai quan hệ làm việc.

Một lỗi nguy hiểm là dùng `ACTIVE` từ HRIS để bật lại account bị khóa do bảo mật hoặc role quản trị của lần làm việc trước.

### 8.4. Chuyển pháp nhân hoặc nhiều quan hệ đồng thời

Một người có thể chấm dứt quan hệ với công ty A nhưng bắt đầu quan hệ với công ty B trong cùng tập đoàn. Một event `TERMINATED` của A và `WORK_START_EFFECTIVE` của B không nhất thiết nghĩa là **toàn bộ danh tính doanh nghiệp** bị xóa rồi tạo lại.

Cần mô hình hóa **employment relationship** theo pháp nhân/đơn vị, xác định quyền nào thuộc từng quan hệ, và tránh gỡ tài khoản chung mà B còn cần. Ngược lại, không được để quyền thuộc A tồn tại chỉ vì người đó có quan hệ mới với B.

### 8.5. Nhân viên chưa hoàn tất xác minh danh tính

HRIS có thể báo start date đã tới nhưng người lao động chưa hoàn tất proofing hoặc chưa nhận đúng thiết bị xác thực. IAM cần ghi rõ **điều kiện còn thiếu**, luồng hỗ trợ, người phê duyệt và cách cấp quyền tối thiểu/khẩn cấp nếu chính sách có cho phép.

Không bỏ qua bước binding MFA/passkey vào đúng chủ thể bằng cách gửi secret cho một địa chỉ cá nhân chưa được xác nhận.

### 8.6. Đã bắt đầu việc nhưng thông tin vai trò còn thiếu

Nếu HRIS báo ACTIVE nhưng `department`, `manager` hoặc `positionCode` chưa có, IAM có thể tạo danh tính hoặc account cơ bản theo chính sách, đồng thời **chưa cấp quyền nghiệp vụ nhạy cảm** cho tới khi dữ liệu đủ và phê duyệt rõ.

Điều này giảm rủi ro cấp quyền rộng chỉ để “giúp người mới làm được việc”. Cần có cơ chế cảnh báo và SLA để tránh tình trạng onboarding bị kẹt không có người xử lý.

### 8.7. Nhân viên không xuất hiện vào ngày bắt đầu

Sự kiện start đã có hiệu lực nhưng người lao động không đến hoặc không xác nhận. Tổ chức cần xác định nguồn nào ghi nhận **no-show**, ai có thẩm quyền hủy/đổi hiệu lực, và cách thu hồi quyền đã cấp. Không suy luận “không đăng nhập ngày đầu” là đã nghỉ; có thể người đó dùng thiết bị khác, bị lỗi mạng hoặc bắt đầu bằng công việc không cần hệ thống.

## 9. Liên kết IdP, SSO, SCIM, RBAC/ABAC

### 9.1. IdP và vòng đời account

IdP quản lý tài khoản và phương thức xác thực. Sự kiện bắt đầu việc có thể khiến IAM kích hoạt tài khoản đã chuẩn bị, mở đăng ký passkey/MFA, thêm nhóm hoặc đồng bộ thuộc tính. Tuy nhiên, thay đổi tại IdP là **hành động kỹ thuật** cần ghi kết quả riêng với sự kiện HRIS.

### 9.2. SSO không thay thế provisioning

SSO qua OIDC/SAML cho phép ứng dụng dựa vào IdP xác thực chủ thể. Một số ứng dụng có **Just-in-Time provisioning** khi người dùng đăng nhập lần đầu; những ứng dụng khác cần SCIM/API trước đó. Cả hai trường hợp phải kiểm soát đúng **account linking** và quyền mặc định, tránh tạo account trái chính sách hoặc cấp nhầm quyền nếu email bị tái sử dụng.

### 9.3. SCIM và tài khoản ứng dụng

SCIM thường hỗ trợ tạo, sửa, kích hoạt/vô hiệu hóa user và nhóm theo phạm vi ứng dụng hỗ trợ. Ví dụ:

~~~text
HRIS START EFFECTIVE
       |
       v
IAM: verify identity + approvals + start time
       |
       +--> IdP account: enabled, MFA required
       +--> SCIM app A: User created, group "Finance-Readers"
       +--> API app B: project-specific membership
       +--> Cloud IAM: no admin role by default
       |
       v
Reconcile: observed user/group/entitlements
~~~

**SCIM trả về thành công không chứng minh ứng dụng đã cấu hình mọi quyền nghiệp vụ**, vì có thể còn role trong hệ thống hoặc tài khoản cục bộ được quản lý ngoài SCIM. IAM cần chỉ ra nguồn chịu trách nhiệm đối với từng entitlement.

### 9.4. RBAC và ABAC dựa trên trạng thái hiện hành

RBAC gán role có trách nhiệm rõ ràng, còn ABAC bổ sung điều kiện theo thuộc tính và ngữ cảnh. Một ví dụ logic cấp quyền:

~~~text
ALLOW finance_report.read IF
    subject.employmentRelationship.status == ACTIVE
    AND subject.proofingStatus == VERIFIED
    AND subject.department == FINANCE
    AND subject.hasApprovedRole("FinanceReader")
    AND resource.organizationUnit == subject.organizationUnit
ELSE DENY
~~~

Mã giả này minh họa các điều kiện; hệ thống thực tế cần xác định **nguồn và độ mới của thuộc tính**, mức bảo đảm xác thực, nghĩa của quan hệ làm việc và yêu cầu của từng tài nguyên. Không nên xem `status == ACTIVE` như điều kiện duy nhất để cho mọi quyền.

## 10. Rủi ro và biện pháp kiểm soát

| Rủi ro | Nguyên nhân thường gặp | Cách giảm thiểu |
| --- | --- | --- |
| Cấp quyền trước ngày hiệu lực | Phân biệt không rõ ngày tạo hồ sơ và startEffectiveAt | Tách chuẩn bị với kích hoạt; kiểm tra lịch và nguồn trước khi mở |
| Hủy nhận việc nhưng account vẫn tồn tại | Không có sự kiện cancel hoặc tác vụ thu hồi | Quy trình hủy, đối soát account đã chuẩn bị và credential |
| Tạo account cho nhầm người | Match theo email/tên, không proofing | identityId ổn định, xác minh, xử lý trùng và rehire |
| Sự kiện bị giao lặp tạo account trùng | Không có idempotency | eventId, khóa nghiệp vụ, upsert và kiểm tra đã provision |
| Sự kiện cũ bật lại quyền sau Leaver | Event đến sai thứ tự, lịch chưa hủy | Version, đọc trạng thái nguồn hiện tại, chặn stale activation |
| Quyền mẫu quá rộng | RBAC chưa quản trị, thiếu approval | Least privilege, role review, điều kiện ABAC |
| Lỗi SCIM hoặc ứng dụng đích | Timeout, rate limit, sai mapping | Retry có kiểm soát, dead-letter queue, reconciliation |
| Thiếu owner hoặc thời hạn nhà thầu | Không liên kết nguồn hợp đồng | Sponsor, endDate, review định kỳ và Leaver có lịch |
| SSO thành công nhưng không đúng role | Claim/group mapping sai hoặc entitlement riêng | Kiểm tra app authorization và quyền hiệu lực |
| Account được tạo mà không ai nhận | Người mới no-show, onboarding bị hủy | Phát hiện orphan, xử lý no-show, thu hồi và audit |
| Quyền khôi phục sai khi tái tuyển dụng | Bật lại account/role cũ | Proofing/reapproval, tính lại desired access |
| Dữ liệu nhân sự lộ qua event bus | Payload chứa thông tin không cần thiết | Tối thiểu hóa dữ liệu, phân quyền subscriber, retention |

**Rủi ro nặng nhất thường không nằm ở một lệnh create account**, mà ở việc quá trình tạo/kích hoạt tài khoản không còn tương thích với **trạng thái quan hệ làm việc mới nhất** hoặc cấp quyền vượt nhu cầu.

### 10.1. Phòng ngừa và phát hiện phải song hành

- **Phòng ngừa:** kiểm tra nguồn, proofing, phê duyệt, quyền tối thiểu, thiết kế ngày hiệu lực và chặn sự kiện cũ.
- **Phát hiện:** đối soát account với HRIS/hợp đồng, kiểm tra quyền hiệu lực, cảnh báo thiếu owner, đo độ trễ event.
- **Ứng phó:** thu hồi account/quyền, hủy token/phiên khi cần, phân công remediation, kiểm tra lại trạng thái đích.
- **Cải tiến:** phân tích nguyên nhân lỗi onboarding và điều chỉnh mapping, policy, kiểm thử giao thức.

## 11. Kiểm toán và truy vết sự kiện bắt đầu việc

Một **audit trail** tốt phải cho phép trả lời: *Nguồn nào nói người này bắt đầu? Có hiệu lực lúc nào? Ai xác minh/phê duyệt? IAM quyết định quyền gì? Tài khoản đã được mở từ khi nào? Tại sao ứng dụng X chưa đúng?*

Nên ghi:

1. **eventId, correlationId, sourceSystem, sourceRecordId**, employmentRelationshipId.
2. **startEffectiveAt**, thời điểm nhận/phát, phiên bản nguồn và trạng thái workflow.
3. Kết quả phân giải danh tính/proofing, chủ thể hoặc policy dùng để kiểm tra.
4. Các **approval** về role, quyền đặc biệt, thời hạn quyền.
5. Danh sách hệ thống đích trong scope và yêu cầu provisioning riêng.
6. Kết quả thực thi: appliedAt, userId/accountId, entitlement được cấp/thu hồi, mã lỗi.
7. **verifiedAt** và bằng chứng desired/observed đã khớp.
8. Ngoại lệ, lần retry, người xử lý, thời điểm đóng và lý do điều chỉnh.

Không ghi mật khẩu, mã khôi phục, token hoặc giấy tờ định danh đầy đủ vào log. Bảo vệ phân quyền và tính toàn vẹn của audit; chính sách lưu giữ phải tương xứng mục đích kiểm toán và bảo vệ dữ liệu.

### 11.1. Ví dụ truy vấn phát hiện kích hoạt sớm

~~~sql
SELECT
    a.identity_id,
    a.system_name,
    a.account_id,
    a.access_activated_at,
    e.start_effective_at
FROM application_accounts AS a
JOIN employment_relationships AS e
  ON a.employment_relationship_id = e.relationship_id
WHERE a.access_activated_at < e.start_effective_at
  AND a.account_type = 'HUMAN'
  AND a.access_scope = 'BUSINESS_APPLICATION';
~~~

Đây là truy vấn **minh họa trên schema giả định**. Không phải mọi account kích hoạt trước ngày bắt đầu đều là vi phạm: doanh nghiệp có thể cho phép preboarding, quyền self-service hoặc một số quyền có thời hạn. Kết quả cần so với **policy ngoại lệ được phê duyệt**, loại ứng dụng và quyền thực tế.

## 12. Các chỉ số vận hành cần đo

| Chỉ số | Cách hiểu | Điều giúp phát hiện |
| --- | --- | --- |
| **Tỷ lệ Joiner hoàn tất trước giờ bắt đầu** | Tỷ lệ workflow đủ điều kiện và hệ thống đích trong scope đã đúng khi đến giờ | Khả năng sẵn sàng làm việc |
| **Thời gian từ hiệu lực đến xác minh** | verifiedAt trừ startEffectiveAt, phân theo ứng dụng | Cấp quyền chậm |
| **Tỷ lệ cấp quyền quá sớm** | Số quyền nghiệp vụ mở trước effectiveAt mà không có approval | Sai chính sách kích hoạt |
| **Số Joiner bị hủy còn account enabled** | Đối chiếu cancel/no-show với observed account | Account mồ côi và quyền tồn dư |
| **Tỷ lệ account không liên kết được** | Account không ánh xạ identity/relationship hợp lệ | Lỗi phân giải danh tính |
| **Tỷ lệ provisioning lỗi/partial** | Workflow có bước không xác minh thành công / tổng workflow | Lỗi SCIM/API hoặc ứng dụng |
| **Số quyền vượt role khởi tạo** | Observed entitlements ngoài approved desired access | Role template rộng hoặc cấp trực tiếp |
| **Tỷ lệ event bị lặp/trễ/cũ** | Phân loại từ event pipeline và bản ghi nguồn | Chất lượng vận hành đồng bộ |
| **Tỷ lệ Joiner thiếu sponsor/manager** | Hồ sơ thiếu owner hợp lệ khi cần duyệt | Ngoại lệ bị bỏ quên |

Cần định nghĩa rõ **mẫu số** khi tính tỷ lệ: một Joiner cần 5 ứng dụng khác một Joiner chỉ cần IdP; các tài khoản chuẩn bị trước cũng khác quyền nghiệp vụ được mở sớm. Đo **trạng thái tại hệ thống đích**, không chỉ kết quả gửi yêu cầu.

## 13. Tình huống tổng hợp: nhân viên mới, đổi ngày, hủy và tái tuyển dụng

Giả sử **Mai** dự kiến vào bộ phận Finance ngày 01/12/2026. HRIS đã có mã `employment-31024`, người quản lý và tình trạng `PRE_HIRE`. Nhóm IAM có thể chuẩn bị tài khoản IdP trong trạng thái chưa cho phép truy cập dữ liệu nghiệp vụ.

### Ngày 23/11: chuẩn bị

- Nhận sự kiện `START_SCHEDULED` với effectiveAt ngày 01/12.
- Đối chiếu hồ sơ, kiểm tra trùng và đặt lịch proofing phù hợp.
- Tạo danh tính, xác nhận phê duyệt role FinanceReader nhưng chưa mở ứng dụng nghiệp vụ trái chính sách.
- Ghi eventId và kết quả chuẩn bị.

### Ngày 25/11: đổi ngày bắt đầu

- HRIS sửa effectiveAt sang ngày **07/12**.
- IAM đánh dấu phiên bản cũ hết hiệu lực và hủy lịch kích hoạt 01/12.
- Lịch mới được đặt theo trạng thái nguồn hiện tại; account chuẩn bị vẫn ở trạng thái phù hợp.

### Ngày 28/11: hủy nhận việc

- HRIS phát sự kiện cancel cho `employment-31024`.
- IAM hủy lịch 07/12 và thu hồi tài khoản, quyền preboarding hoặc authenticator đã chuẩn bị trong scope.
- Chạy đối soát để chứng minh không còn quyền truy cập trái chính sách và lưu kết quả.

### Sáu tháng sau: Mai được tuyển lại

- Nguồn nhân sự tạo quan hệ mới và đưa bằng chứng phù hợp để nhận diện đúng chủ thể.
- IAM xem xét tái sử dụng identity/account theo chính sách, thực hiện proofing hoặc đăng ký lại authenticator nếu cần.
- Role được tính lại cho **công việc hiện tại**, không mở lại quyền từ onboarding đã hủy.
- Các hệ thống đích xác minh quyền cuối và ghi trace của lần Joiner mới.

**Bài học:** sự kiện bắt đầu việc phải được quản lý theo **quan hệ làm việc và phiên bản hiện tại**, chứ không phải một yêu cầu tạo account vĩnh viễn. Đổi lịch, hủy và tái gia nhập đều có thể thay đổi quyết định kích hoạt quyền.

## 14. Bảng kiểm tra dành cho nhóm tích hợp HRIS–IAM

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Sự kiện bắt đầu do nguồn nào phát, nguồn có thẩm quyền không? | Source contract, định danh hệ thống, owner dữ liệu |
| Đã phân biệt offer, ký hợp đồng và ngày bắt đầu hiệu lực chưa? | Event type, startEffectiveAt và quy tắc nghiệp vụ |
| Có mã hồ sơ và relationship ID ổn định không? | Identity linking không dùng email làm khóa chính |
| Có xét timezone, lịch tương lai và thay đổi ngày không? | Quy tắc effective date, hủy lịch cũ và đọc lại trạng thái |
| Có xử lý hủy nhận việc hoặc no-show không? | Event cancel, quyền/account đã được thu hồi, audit |
| Có proofing và binding authenticator đúng người không? | Kết quả xác minh và liên kết identityId–accountId |
| Role khởi tạo có được kiểm tra least privilege không? | Approved desired entitlements, RBAC/ABAC, SoD |
| Có tách account chuẩn bị khỏi quyền dùng ứng dụng không? | Trạng thái account, điều kiện kích hoạt và chính sách |
| SCIM/API lỗi có được retry, theo dõi và đối soát không? | Queue lỗi, trạng thái từng hệ thống, owner remediation |
| Có chặn event lặp/cũ làm khôi phục account không? | Idempotency, version, current-state check |
| Có xử lý nhà thầu, thực tập sinh, rehire và nhiều quan hệ không? | Nguồn hợp đồng, sponsor, policy theo worker type |
| Có biết khi nào Joiner thực sự hoàn tất không? | observed state, verifiedAt, audit theo correlation ID |
| Có phân định service account khỏi start event nhân sự không? | Lifecycle workload và quản trị owner riêng |

## 15. Câu hỏi tự đánh giá

1. Vì sao việc HRIS tạo hồ sơ tuyển dụng ngày 23/11 không đồng nghĩa phải mở toàn bộ quyền ứng dụng từ ngày đó?
2. Hai dữ liệu `eventPublishedAt` và `startEffectiveAt` có thể khác nhau ra sao? Hậu quả nếu nhầm hai mốc này?
3. Một người có hai hợp đồng tại hai đơn vị khác nhau. Vì sao cần `employmentRelationshipId` bên cạnh `identityId`?
4. Nếu event `START_SCHEDULED` đến sau `JOINER_CANCELLED`, IAM cần áp dụng cơ chế nào để không mở quyền?
5. Account IdP đã tạo xong nhưng SCIM của ứng dụng CRM thất bại. Workflow Joiner đã hoàn tất chưa?
6. Một nhân viên được tái tuyển dụng. Có thể bật lại toàn bộ role của lần làm việc cũ không? Vì sao?
7. Vai trò của proofing khác với approval và quyền RBAC/ABAC như thế nào?
8. Vì sao việc SSO thành công không chứng minh mọi quyền ứng dụng đã được cấp đúng?
9. Khi hồ sơ HR ghi ACTIVE nhưng account bị khóa bởi sự cố bảo mật, điều gì cần xảy ra?
10. Những chỉ số nào chứng minh hệ thống vừa kích hoạt quyền đúng thời điểm vừa không giữ account của người bị hủy nhận việc?

## 16. Ghi nhớ

**Sự kiện bắt đầu việc** là tín hiệu nghiệp vụ có **nguồn có thẩm quyền, chủ thể/quan hệ làm việc được nhận diện và thời điểm hiệu lực rõ ràng**. Nó khởi phát các quyết định trong Joiner lifecycle, nhưng **không thay thế identity proofing, approval, authorization hoặc xác minh kết quả tại ứng dụng**.

Để vận hành an toàn, IAM cần tiếp nhận và chuẩn hóa sự kiện, đối chiếu danh tính, xử lý lịch tương lai và các thay đổi/hủy, áp dụng **IdP/SSO, SCIM, RBAC/ABAC** theo nguyên tắc quyền tối thiểu, đối soát **desired access** với **observed access**, và lưu audit đầu cuối. Tài khoản dịch vụ phải theo vòng đời riêng. Một Joiner chỉ có thể được xem là hoàn tất khi các **quyền hợp lệ đã được cấp đúng người, đúng vai trò, đúng thời điểm và được xác minh**; mọi tài khoản hoặc quyền được chuẩn bị nhưng không còn cơ sở cần được thu hồi để tránh truy cập tồn dư.
