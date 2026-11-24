# Xác minh hoàn tất Joiner trong quản lý vòng đời danh tính IAM

## 1. “Hoàn tất Joiner” có nghĩa là gì?

Trong **Identity and Access Management (IAM)**, **Joiner** là giai đoạn đưa một chủ thể mới vào phạm vi quản lý danh tính của tổ chức: tiếp nhận thông tin từ nguồn có thẩm quyền, xác minh danh tính, tạo hoặc liên kết tài khoản, thiết lập khả năng đăng nhập và cấp quyền phù hợp với công việc. **Xác minh hoàn tất Joiner** là bước kiểm tra có bằng chứng rằng những yêu cầu bắt buộc của quá trình này đã được thực hiện chính xác, ở đúng hệ thống và đúng thời điểm.

Ví dụ, bộ phận nhân sự xác nhận An bắt đầu làm việc vào ngày 01/12. IAM đã tạo tài khoản trên nhà cung cấp danh tính (Identity Provider – **IdP**) và gửi yêu cầu tạo tài khoản sang ba ứng dụng. **Chỉ vì IAM đã gửi đủ ba yêu cầu không có nghĩa Joiner đã hoàn tất**: ứng dụng thứ ba có thể từ chối tạo tài khoản; một tài khoản khác có thể được cấp sai nhóm quản trị; hoặc An chưa được đăng ký phương thức xác thực cần thiết.

Để xác nhận hoàn tất, hệ thống cần phân biệt ít nhất ba mốc:

| Mốc | Ý nghĩa | Ví dụ bằng chứng |
| --- | --- | --- |
| **Sẵn sàng kỹ thuật** (*technical readiness*) | Danh tính và các tài khoản/quyền bắt buộc đã được cấp, kiểm chứng chính xác và sẵn sàng theo chính sách | Account tồn tại đúng identity, entitlement hiệu lực và MFA/điều kiện đăng nhập đã được xử lý |
| **Người dùng kích hoạt** (*user activation*) | Người dùng đã thực hiện các bước tự thân được yêu cầu, nếu có | Hoàn thành đăng ký MFA, kích hoạt tài khoản hoặc đăng nhập lần đầu hợp lệ |
| **Bàn giao và đóng Joiner** (*business closure*) | Các điều kiện nghiệm thu của người quản lý, chủ ứng dụng và bộ phận vận hành được đáp ứng | Người phụ trách xác nhận quyền cần thiết, các ngoại lệ có quyết định rõ |

Tên và thứ tự trạng thái có thể khác nhau giữa các tổ chức. **Không nên bắt buộc chờ người dùng đăng nhập lần đầu nếu tiêu chuẩn “hoàn tất kỹ thuật” chỉ yêu cầu môi trường đã sẵn sàng**; thay vào đó hãy theo dõi riêng “chưa kích hoạt”. Ngược lại, nếu chính sách bắt buộc đăng ký MFA trước khi cho phép làm việc, không nên đánh dấu hoàn tất toàn bộ khi MFA chưa được thiết lập.

Mục tiêu của bước xác minh là bảo đảm **đúng người, đúng thời điểm, đúng tài khoản, đúng tài nguyên, đúng quyền, đúng điều kiện xác thực và có thể truy vết**. Đây là phần đầu của vòng đời **Joiner–Mover–Leaver (JML)**; bằng chứng Joiner về sau trở thành đường chuẩn để rà soát và thu hồi quyền khi nhân viên thay đổi vai trò hoặc rời tổ chức.

## 2. Các điều kiện cần có trong tiêu chí nghiệm thu

Một quy trình hoàn tất Joiner không nên dựa vào một cờ `success = true` duy nhất. Các tiêu chí được xác định theo **loại danh tính, vai trò, mức nhạy cảm và hệ thống bắt buộc**.

| Nhóm điều kiện | Câu hỏi kiểm chứng | Dấu hiệu đạt |
| --- | --- | --- |
| **Nguồn nhân sự** | HRIS/nguồn bảo trợ đã xác nhận quan hệ làm việc chưa? | Bản ghi đã duyệt, mã ổn định, ngày hiệu lực, loại lao động hợp lệ |
| **Xác minh danh tính** | Identity đã gắn đúng người hoặc workload chưa? | Quy trình xác minh theo mức đảm bảo được yêu cầu, không trùng hoặc liên kết nhầm |
| **Trạng thái vòng đời** | Người này đã đến ngày được kích hoạt chưa? | Trạng thái, lịch kích hoạt và thời hạn đúng chính sách |
| **Tài khoản IdP** | Tài khoản đã được tạo/liên kết chính xác chưa? | Có account ID đúng, trạng thái đăng nhập phù hợp, không có bản ghi trùng |
| **Xác thực và phục hồi** | Chính sách MFA, khôi phục tài khoản, yêu cầu bảo mật đã sẵn sàng chưa? | Đáp ứng các yêu cầu bắt buộc theo giai đoạn nghiệm thu |
| **Tài khoản ứng dụng** | Các ứng dụng bắt buộc đã provision thành công chưa? | Tài khoản thực sự tồn tại ở đích và liên kết đúng identity |
| **Quyền truy cập** | Nhóm, vai trò, entitlement có khớp công việc và phê duyệt không? | Không thiếu quyền bắt buộc và không có quyền vượt phạm vi |
| **Thực thi chính sách** | Người dùng có thể dùng đúng tài nguyên mà chính sách cho phép không? | Quyền hiệu lực tại ứng dụng/API phù hợp, không rò sang tài nguyên ngoài phạm vi |
| **Kiểm toán** | Có thể giải thích ai yêu cầu, ai duyệt, đã cấp gì và kết quả ra sao không? | Nhật ký liên kết nguồn HR, quyết định IAM và xác nhận từ đích |
| **Ngoại lệ** | Có hạng mục chậm, bị từ chối hoặc đang chờ người dùng không? | Được đánh dấu, phân công xử lý và chỉ đóng khi đạt tiêu chí |

**Bắt buộc** và **tùy chọn** phải được phân loại trước. Một ứng dụng không liên quan tới vai trò của An không nên ngăn hoàn tất Joiner. Một ứng dụng bắt buộc để An thực hiện công việc hoặc một kiểm soát bảo mật trọng yếu lại không được bỏ qua chỉ để tỷ lệ hoàn tất đạt mục tiêu.

## 3. Cần xác định chính xác phạm vi của một ca Joiner

Một Joiner case nên có **mã hồ sơ duy nhất**, chủ thể được xác minh, loại quan hệ làm việc, phiên bản nguồn, thời điểm hiệu lực, chính sách và danh sách hạng mục phải hoàn tất.

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `joinerCaseId` | `joiner-2026-1842` | Theo dõi mọi bước và retry trong cùng ca |
| `personId` / `workerId` | `person-482` / `worker-915` | Liên kết nguồn nhân sự đáng tin cậy |
| `employmentId` | `employment-2026-38` | Xác định quan hệ làm việc hiện hành |
| `identityId` | `iam-id-482` | Liên kết tới danh tính số trung tâm |
| `workerType` | `employee` hoặc `contractor` | Chọn bộ chính sách phù hợp |
| `startAt` / `endAt` | Mốc có hiệu lực đã được chuẩn hóa | Điều khiển kích hoạt, hết hạn và các công việc theo lịch |
| `organizationId`, `jobCode`, `assignmentId` | Mã tổ chức, chức danh, dự án | Tính tập quyền được cấp |
| `policyVersion` | `joiner-policy-v12` | Biết bộ tiêu chí nghiệm thu tại thời điểm xử lý |
| `requiredTargets` | Danh sách ứng dụng/kiểm soát bắt buộc | Phân biệt thành công toàn bộ với thành công một phần |

Nếu nhân viên cũ được tuyển lại (*rehire*), việc có `personId` cũ không đủ để tiếp tục quyền của đợt làm việc trước. Cần xác minh quan hệ mới, kiểm tra các tài khoản cũ còn tồn tại và tính lại quyền theo vai trò mới. Với một người có nhiều hợp đồng hoạt động song song, ca Joiner phải gắn đúng **quan hệ làm việc**; không tự cấp quyền của hợp đồng A sang B.

Nhà thầu hoặc đối tác có thể đến từ hệ thống quản lý đối tác thay vì HRIS. Trường hợp đó, hồ sơ Joiner cần **sponsor**, tổ chức chịu trách nhiệm và ngày hết hạn tương ứng. Danh tính máy có quy trình đăng ký riêng, không mặc nhiên sử dụng employee record của một nhân viên làm bản ghi của workload.

## 4. Kiểm tra nguồn có thẩm quyền và danh tính đã được xác minh

### 4.1. Xác thực sự kiện từ HRIS hoặc nguồn bảo trợ

Trước khi kết luận một Joiner hợp lệ, cần kiểm tra:

1. Sự kiện hoặc bản ghi đến từ **nguồn có thẩm quyền** đối với loại danh tính này.
2. Trạng thái tuyển dụng hoặc bảo trợ đã được xác nhận, không chỉ là đề nghị dự kiến.
3. `workerId`, `employmentId` và organization được ánh xạ đúng; bản ghi không bị trùng hoặc không xác định chủ thể.
4. **Ngày bắt đầu có hiệu lực** được hiểu đúng theo chính sách và múi giờ. Tài khoản chuẩn bị trước ngày nhận việc có thể cần giữ trạng thái chưa được phép đăng nhập.
5. Mã phiên bản hoặc thời điểm hiệu lực phù hợp với bản ghi hiện hành; không dùng một sự kiện cũ bị thay thế để kích hoạt ca Joiner đã hủy.

Một hồ sơ tuyển dụng bị rút lại hoặc ngày nhận việc được dời sang kỳ sau phải làm thay đổi lịch và trạng thái Joiner. Không để tài khoản đã chuẩn bị trước tự động kích hoạt theo lịch cũ mà không kiểm tra nguồn mới nhất.

### 4.2. Xác minh chủ thể và tránh gộp nhầm

**Identity proofing** là việc thu thập và kiểm chứng bằng chứng về chủ thể ở mức phù hợp chính sách. Cách xác minh phụ thuộc việc nhân viên làm trực tiếp, làm từ xa, là đối tác hay là workload. IAM cần lưu **kết quả và dấu vết xác minh** ở mức cần thiết, tránh sao chép tràn lan giấy tờ cá nhân sang log hoặc token.

**Identity correlation** là việc nối đúng danh tính trung tâm với tài khoản ở hệ thống đích. Không nên coi email hoặc họ tên trùng nhau là bằng chứng đủ để gộp hai người: email có thể đổi, tái sử dụng hoặc chuyển tiếp. Một tài khoản cục bộ không rõ chủ sở hữu phải được xác minh trước khi liên kết.

Việc xác minh danh tính thành công chỉ là điều kiện ban đầu. Nó không tự chứng minh ứng dụng đã cấp đúng nhóm, quyền hay khả năng đăng nhập.

## 5. Kiểm tra tạo tài khoản và khả năng đăng nhập an toàn

### 5.1. Tài khoản IdP

Khi Joiner dùng một **Identity Provider (IdP)**, cần kiểm chứng:

- Tài khoản được tạo hoặc liên kết tới đúng `identityId` và mã nhân sự/nguồn có thẩm quyền.
- Tên đăng nhập, định danh nội bộ, trạng thái, organization và các thuộc tính bắt buộc được tạo đúng.
- Tài khoản chưa được kích hoạt quá sớm; các chính sách xác thực áp dụng đúng cho vai trò và nhóm rủi ro.
- Không tạo trùng account khi sự kiện được gửi lại, hoặc dùng account đã thuộc người khác.
- Quyền quản trị, quyền khôi phục tài khoản, quyền đổi thông tin bảo mật được tách theo chính sách.

**Provisioning success** là trạng thái tài khoản đã được tạo/điều chỉnh; **authentication readiness** là khả năng hoàn thành các điều kiện đăng nhập. Hai trạng thái này có thể khác nhau.

### 5.2. SSO và MFA

**Single Sign-On (SSO)** giúp dùng danh tính từ IdP để xác thực vào ứng dụng. Phần kiểm chứng nên bao gồm cấu hình dự kiến của **OpenID Connect (OIDC)** hoặc **SAML** tùy nền tảng, liên kết đúng account, phạm vi claim cần thiết và chính sách đăng nhập phù hợp. Không nên phát tán token thật trong nhật ký hoặc coi kết quả tạo account là bằng chứng giao thức SSO đã chạy đúng.

Với **Multi-Factor Authentication (MFA)** và phương thức khôi phục, cần phân biệt:

1. **Chính sách MFA đã được gán:** IdP có yêu cầu đúng mức bảo vệ?
2. **Người dùng đã đăng ký phương thức hợp lệ:** có thể là hạng mục do người dùng phải thực hiện sau khi nhận thiết bị hoặc tài khoản.
3. **MFA được thực thi khi truy cập:** đường đăng nhập thực tế không có ngoại lệ làm vô hiệu yêu cầu bảo mật.

Nếu quy trình yêu cầu người dùng chủ động đăng ký MFA ở lần đầu, trạng thái nên thể hiện rõ **sẵn sàng để kích hoạt** và **chờ người dùng hoàn tất**. Việc nhân viên chưa đăng nhập ngày đầu không phải mặc nhiên là lỗi provisioning; tiêu chí đóng nghiệp vụ phải do tổ chức quyết định.

Không gửi mật khẩu tạm thời hoặc mã khôi phục vào log kiểm toán, thông báo không phù hợp hoặc các bản ghi trạng thái Joiner. Quy trình bàn giao thông tin kích hoạt phải dùng kênh được tổ chức phê duyệt.

## 6. Kiểm chứng provisioning qua SCIM và các ứng dụng đích

**System for Cross-domain Identity Management (SCIM)** có thể đồng bộ người dùng và nhóm từ IdP sang ứng dụng có hỗ trợ. Một ca Joiner thường có cả ứng dụng SCIM, ứng dụng dùng API riêng và hệ thống cấp tài khoản qua quy trình thủ công được phê duyệt.

Cần phân biệt các bước:

| Bước | Thông tin đã có | Chưa chứng minh được |
| --- | --- | --- |
| IAM tạo lệnh provisioning | Đã có yêu cầu đúng mục tiêu | Ứng dụng đã nhận hoặc xử lý |
| Connector trả `accepted` | Yêu cầu đã được tiếp nhận | Account được tạo và có quyền |
| Ứng dụng trả về account ID | Đã có account tại hệ thống đích | Role, nhóm, ACL và đăng nhập đúng |
| Đồng bộ group hoàn tất | Thành viên nhóm đã được cập nhật | Mọi entitlement cục bộ và quyền hiệu lực |
| Đối soát tài khoản và quyền tại đích | Trạng thái thực tế khớp mục tiêu ở thời điểm kiểm tra | Các bước người dùng chủ động cần làm sau đó, nếu chưa thực hiện |

Không phải ứng dụng nào cũng dùng cấu trúc quyền giống IdP. SCIM thường hỗ trợ vòng đời người dùng/nhóm, nhưng **không mặc nhiên quản lý mọi entitlement cục bộ, vai trò ứng dụng, thư mục chia sẻ, API key hoặc token**. Với mỗi hệ thống bắt buộc, cần định nghĩa cơ chế đọc lại trạng thái và người chịu trách nhiệm xác minh.

### Ma trận ứng dụng bắt buộc

Ví dụ với vị trí nhân viên phân tích:

| Mục tiêu | Bắt buộc để hoàn tất kỹ thuật? | Điều kiện xác minh |
| --- | --- | --- |
| IdP doanh nghiệp | Có | Đúng identity, trạng thái và chính sách xác thực |
| Ứng dụng phân tích số liệu | Có | Account tồn tại, quyền xem đúng dashboard được phê duyệt |
| Kho tài liệu nhóm | Có | Có quyền vào workspace của nhóm, không có quyền thư mục nhạy cảm ngoài nhóm |
| Công cụ thiết kế chuyên dụng | Không, nếu không thuộc vai trò | Không cần provision; không chặn Joiner |
| Quyền quản trị cloud | Không mặc định | Chỉ được cấp nếu có nhu cầu, phê duyệt và kiểm soát đặc quyền riêng |

Danh sách trên là ví dụ; không có một bộ ứng dụng bắt buộc giống nhau cho mọi nhân viên hoặc tổ chức.

## 7. Kiểm tra quyền: vừa không thiếu, vừa không thừa

Một Joiner có thể hoạt động sai theo hai hướng: **thiếu quyền bắt buộc** khiến không làm được việc, hoặc **thừa quyền** gây nguy cơ lộ dữ liệu và chiếm đoạt đặc quyền. Bước xác minh cần kiểm cả hai.

**RBAC (Role-Based Access Control)** thường dùng chức danh/nhóm chức năng để gán role, còn **ABAC (Attribute-Based Access Control)** có thể xét thuộc tính như trạng thái làm việc, tổ chức, dự án, khu vực, độ nhạy tài nguyên hoặc ngữ cảnh. Không nên cấp role chỉ dựa vào một giá trị do người dùng tự khai; thuộc tính dùng để quyết định quyền phải có nguồn tin cậy.

Giả sử An thuộc Dự án Atlas và có role `Analyst`. Chính sách minh họa:

~~~text
CHO PHÉP An xem báo cáo NẾU:
    identity.status = ACTIVE
    VÀ employment.status = ACTIVE
    VÀ assignedProject(identity) = report.projectId
    VÀ hasApprovedRole(identity, "Analyst", report.projectId)
    VÀ action = READ
    VÀ mọi điều kiện bảo mật bổ sung đều được đáp ứng
    VÀ không có quy tắc từ chối ưu tiên cao hơn
NGƯỢC LẠI: TỪ CHỐI
~~~

Nghiệm thu nên kiểm cả:

- **Positive check:** tài khoản kiểm thử được quản lý hoặc bằng chứng quyền hiệu lực cho thấy An có quyền `READ` với báo cáo Atlas được duyệt.
- **Negative check:** An không có quyền `DELETE` báo cáo, xem dữ liệu nhân sự hay đọc báo cáo dự án khác khi không có căn cứ.
- **Truy cập qua API/backend:** chính sách được thực thi tại điểm kiểm soát tin cậy; chỉ ẩn nút trên giao diện không bảo vệ được tài nguyên.
- **Đường cấp quyền thay thế:** quyền qua nhóm lồng nhau, role kế thừa hoặc ACL trực tiếp không làm tài khoản có thêm quyền vượt phạm vi.
- **Điều kiện có thời hạn:** quyền dự án hoặc quyền hỗ trợ tạm thời được đặt hạn và có chủ tài nguyên chịu trách nhiệm.

Các bước kiểm chứng không được biến thành hành động xem dữ liệu thật trái phép. Có thể dùng môi trường thử nghiệm, tài nguyên kiểm thử, mô phỏng chính sách hoặc API đọc trạng thái quyền có phân quyền phù hợp. Việc **không có bằng chứng quyền hiệu lực** khác với việc đã xác nhận rằng quyền đúng.

## 8. Mô hình quy trình xác minh hoàn tất Joiner

Quy trình có thể chia thành các cổng nghiệm thu tuần tự hoặc bất đồng bộ:

~~~mermaid
flowchart TD
    A["HRIS / nguồn bảo trợ xác nhận Joiner"] --> B["Xác minh danh tính, nguồn, ngày hiệu lực"]
    B --> C["Xác định chính sách và danh sách mục tiêu bắt buộc"]
    C --> D["Tạo/liên kết account IdP và ứng dụng"]
    D --> E["Thiết lập MFA/SSO và cấp nhóm, role, entitlement"]
    E --> F["Đọc lại account và quyền hiệu lực ở hệ thống đích"]
    F --> G{"Đủ mọi điều kiện bắt buộc?"}
    G -->|"Không"| H["PARTIAL / BLOCKED, lưu lỗi và người xử lý"]
    H --> I["Retry hoặc sửa dữ liệu theo phê duyệt"]
    I --> F
    G -->|"Có"| J["Ghi bằng chứng, đánh dấu sẵn sàng kỹ thuật"]
    J --> K{"Có yêu cầu kích hoạt / xác nhận nghiệp vụ?"}
    K -->|"Có"| L["Theo dõi user activation / business sign-off"]
    K -->|"Không"| M["Đóng Joiner theo tiêu chí đã định"]
    L --> M
~~~

Một số kiểm tra như kích hoạt MFA ở lần đăng nhập đầu có thể xảy ra **sau** khi môi trường đã sẵn sàng kỹ thuật. Khi đó, trạng thái phải biểu diễn rõ **mốc đã đạt** và **mốc đang chờ**, không ghi một cờ `completed` gây hiểu lầm.

### Mô hình trạng thái khuyến nghị

Các tên sau chỉ là thiết kế minh họa, cần ánh xạ với quy trình hiện hữu:

| Trạng thái | Ý nghĩa | Có được đóng Joiner chưa? |
| --- | --- | --- |
| `PENDING_SOURCE` | Chờ xác nhận HR/nguồn bảo trợ hoặc ngày có hiệu lực | Chưa |
| `IDENTITY_VERIFIED` | Đã xác minh, liên kết đúng identity | Chưa |
| `PROVISIONING` | Đang tạo account, nhóm và quyền | Chưa |
| `PARTIAL` | Một số mục tiêu thành công, có mục tiêu bắt buộc chưa đạt | Chưa |
| `BLOCKED` | Lỗi xác minh, phê duyệt hoặc kiểm soát bảo mật | Chưa |
| `TECHNICALLY_READY` | Đã chứng minh đầy đủ điều kiện kỹ thuật bắt buộc | Tùy yêu cầu đóng nghiệp vụ |
| `AWAITING_ACTIVATION` | Cần người dùng hoàn thành bước tự thân theo chính sách | Chưa đạt các bước yêu cầu đó |
| `COMPLETED` | Tất cả cổng nghiệm thu của ca Joiner đã được xác nhận | Có |
| `CANCELLED` | Joiner không còn hợp lệ, ví dụ tuyển dụng bị hủy | Không; cần xử lý các tài khoản chuẩn bị trước |

Hệ thống có thể lưu các trạng thái theo **nhiều chiều** thay vì bắt tất cả vào một chuỗi duy nhất; ví dụ `technicalReady = true`, `userActivated = false`, `businessAccepted = false`. Điều quan trọng là định nghĩa **điều kiện chuyển trạng thái** và **bằng chứng** cho từng mốc.

## 9. Bằng chứng kỹ thuật và dữ liệu kiểm toán cần lưu

Một dòng log `Joiner completed` không đủ để truy vết khi phát hiện quyền thừa hoặc mất tài khoản. Bản ghi nghiệm thu nên liên kết **ca Joiner, nguồn dữ liệu, quyết định chính sách, từng hệ thống đích và thời điểm kiểm chứng**.

Ví dụ cấu trúc JSON **minh họa**, không phải schema chuẩn:

~~~json
{
  "joinerCaseId": "joiner-2026-1842",
  "identityId": "iam-id-482",
  "sourceReference": "employment-2026-38",
  "sourceVersion": 12,
  "policyVersion": "joiner-policy-v12",
  "technicalReadiness": "verified",
  "activation": "pending_user_action",
  "businessClosure": "pending",
  "targetChecks": [
    {
      "system": "enterprise-idp",
      "accountRef": "user-482",
      "required": true,
      "accountState": "ready",
      "authenticationPolicy": "assigned",
      "checkStatus": "passed"
    },
    {
      "system": "analytics-app",
      "accountRef": "analytics-482",
      "required": true,
      "expectedEntitlement": "atlas-report-reader",
      "effectiveEntitlement": "atlas-report-reader",
      "checkStatus": "passed"
    }
  ],
  "checkedAt": "2026-11-30T08:00:00+07:00",
  "result": "TECHNICALLY_READY"
}
~~~

Bản ghi này **chỉ chứng minh trạng thái sẵn sàng kỹ thuật tại thời điểm kiểm tra**; người dùng còn phải kích hoạt và bộ phận nghiệp vụ còn phải chấp nhận nếu quy trình yêu cầu. Trong sản phẩm thật, bằng chứng có thể là ID sự kiện, phiên bản snapshot, kết quả truy vấn quyền, ID phê duyệt hoặc bản ghi kiểm toán được lưu riêng.

Nên có các nhóm dữ liệu:

1. **Định danh và nguồn:** mã ca, identity, worker/employment, người bảo trợ, nguồn thẩm quyền và phiên bản.
2. **Tiêu chí áp dụng:** chính sách và danh sách mục tiêu bắt buộc được chốt tại thời điểm xử lý.
3. **Phê duyệt và quyền:** nhóm, role, entitlement, chủ tài nguyên, phạm vi và hạn dùng.
4. **Kết quả từng mục tiêu:** account ID đích, trạng thái thao tác, trạng thái đọc lại và dấu thời gian.
5. **Xác thực an toàn:** trạng thái áp dụng chính sách SSO/MFA, không lưu password, recovery code hay token.
6. **Ngoại lệ và xử lý:** lỗi, người phụ trách, retry, thời hạn khắc phục, kết quả rà soát.
7. **Dấu mốc đóng:** ai hoặc tiến trình nào xác nhận hoàn tất, theo tiêu chí nào, lúc nào.

Quyền truy cập những bản ghi kiểm toán này cũng phải được giới hạn; dữ liệu HR và thông tin cấp quyền có thể tiết lộ cơ cấu tổ chức hoặc tài nguyên nhạy cảm.

## 10. Mã giả kiểm tra hoàn tất và nguyên tắc idempotency

Một bộ kiểm tra có thể chạy sau mỗi sự kiện provisioning và chạy lại định kỳ cho ca đang mở. Mã giả sau nhấn mạnh rằng **chỉ các điều kiện bắt buộc đã được xác minh mới được dùng để đóng ca**:

~~~text
verifyJoiner(caseId):
    case = loadJoinerCase(caseId)
    source = loadCurrentAuthoritativeRecord(case.sourceReference)

    if source.isCancelled or source.isNoLongerEligible:
        markCancelled(caseId)
        reconcilePreparedAccountsForCancellation(caseId)
        return CANCELLED

    if not source.isApproved or not identityLinkIsVerified(case.identityId):
        return BLOCKED

    policy = loadPinnedPolicy(case.policyVersion)
    required = requiredChecksFor(case, policy)
    results = []

    for check in required:
        actual = readActualStateFromTarget(check.target, case.identityId)
        results.add(evaluate(check.expectedState, actual, source.effectiveTime))

    recordEvidence(caseId, source.version, policy.version, results)

    if any(result.hasSecurityViolation for result in results):
        alertOwnerAndRemediate(caseId, results)
        return BLOCKED

    if any(not result.passed for result in results):
        assignOutstandingItems(caseId, results)
        return PARTIAL

    markTechnicalReadinessVerified(caseId)

    if not requiredUserActionsComplete(caseId, policy):
        return AWAITING_ACTIVATION
    if not requiredBusinessAcceptanceComplete(caseId, policy):
        return TECHNICALLY_READY

    markCompletedWithAuditEvidence(caseId)
    return COMPLETED
~~~

Đây là **mã giả giáo dục**: trong hệ thống thật, cần thêm kiểm soát quyền truy cập, timeout, phân quyền thao tác, xử lý bất đồng bộ, phiên bản nguồn, khóa cạnh tranh và xác nhận đọc lại.

Các tính chất quan trọng:

- **Idempotency:** chạy lại ca không tạo trùng người dùng, tài khoản, membership hoặc quyền.
- **Event versioning:** sự kiện HR đến trễ không được ghi đè trạng thái tuyển dụng mới hơn.
- **Reconciliation:** phải đọc trạng thái đích để phát hiện thao tác đã gửi nhưng chưa áp dụng hoặc sai phạm vi.
- **Monotonic evidence có điều kiện:** bằng chứng đạt ở thời điểm cũ có thể không còn hợp lệ sau khi role, assignment hoặc ngày bắt đầu thay đổi; cần kiểm tra lại những điều kiện liên quan.
- **Xử lý lỗi có chủ sở hữu:** không chuyển hạng mục `failed` thành `skipped` nếu nó vẫn bắt buộc.

## 11. Những lỗi thường gặp khiến Joiner chưa thể hoàn tất

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tài khoản IdP đã tạo nhưng người dùng không vào được ứng dụng | SSO mapping sai, account ứng dụng chưa có, MFA chưa đăng ký | Kiểm tra từng lớp xác thực và provisioning; xác minh tại đích |
| SCIM trả về thành công nhưng account không có đúng role | Mapping nhóm/role sai hoặc ứng dụng giữ ACL riêng | Đọc quyền hiệu lực, sửa mapping và xử lý quyền cục bộ |
| Hai tài khoản cho cùng một người | Retry không idempotent hoặc identity correlation sai | Dừng cấp quyền mới, xác minh chủ thể và hợp nhất theo quy trình |
| Người mới có quyền quản trị quá rộng | Gán role theo nhóm mặc định hoặc nhầm policy | Cô lập/thu hồi quyền vượt mức, rà soát nguồn phê duyệt |
| Chưa đến ngày nhận việc nhưng tài khoản đã active | Sai timezone hoặc diễn giải thời điểm HR | Điều chỉnh lịch kích hoạt, trạng thái và bằng chứng kiểm soát |
| Nhân viên mới không có quyền báo cáo bắt buộc | Ứng dụng chậm đồng bộ hoặc thiếu phê duyệt | Theo dõi `PARTIAL`, sửa lỗi theo chủ sở hữu và kiểm chứng lại |
| Nhà thầu có account không thời hạn | Thiếu ngày hết hạn hoặc sponsor | Định nghĩa hạn, người bảo trợ và cơ chế rà soát |
| Người dùng đã đăng nhập nhưng Joiner vẫn bị đánh dấu lỗi | Dùng trạng thái kỹ thuật và trạng thái kích hoạt không nhất quán | Tách cổng nghiệm thu; kiểm tra đúng tiêu chí từng mốc |
| HR rút lại tuyển dụng nhưng tài khoản vẫn tồn tại | Job theo lịch chưa được hủy; sự kiện mới chưa được xử lý | Hủy ca, vô hiệu hóa/thu hồi account và quyền đã chuẩn bị |

### Lỗi kỹ thuật tạm thời và lỗi chính sách cần xử lý khác nhau

Một connector timeout có thể được retry an toàn nếu thao tác idempotent và còn hợp lệ. Trái lại, người dùng chưa được xác minh, không có hợp đồng hợp lệ, thiếu phê duyệt cho quyền nhạy cảm hoặc bị phát hiện sai identity là **lỗi điều kiện bảo mật**: phải chờ xác minh và quyết định phù hợp. Không vượt qua các cổng chính sách bằng cách lặp thao tác tạo quyền.

Nếu một hệ thống bắt buộc không khả dụng kéo dài, cần phân công xử lý và thông báo tiến độ cho đầu mối onboarding. Có thể dùng quy trình thay thế được phê duyệt, nhưng **không tự bỏ yêu cầu bảo mật để đạt cờ hoàn tất**.

## 12. Kiểm tra bất đồng bộ, thời hạn và những trường hợp thay đổi

Việc cấp quyền có thể xảy ra qua nhiều hệ thống với thời gian xử lý khác nhau. Một ca Joiner có thể nhận kết quả không theo thứ tự và nhiều lần:

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / Joiner workflow
    participant IdP as Identity Provider
    participant App as Ứng dụng đích
    participant Owner as Người quản lý / chủ tài nguyên
    HR->>IAM: Xác nhận nhân sự và ngày bắt đầu
    IAM->>IAM: Xác minh identity và tính quyền mục tiêu
    IAM->>Owner: Yêu cầu phê duyệt nếu cần
    Owner-->>IAM: Phê duyệt phạm vi quyền
    IAM->>IdP: Tạo/liên kết account, nhóm, chính sách
    IdP->>App: SCIM / API provisioning
    App-->>IAM: Kết quả thao tác / account ID
    IAM->>App: Đọc lại account và quyền hiệu lực
    App-->>IAM: Trạng thái thực tế tại đích
    IAM->>IAM: Đánh giá các cổng nghiệm thu và lưu bằng chứng
    IAM-->>Owner: Báo trạng thái sẵn sàng hoặc hạng mục còn mở
~~~

Những trường hợp cần tính trước:

- **Ngày bắt đầu bị dời:** lịch kích hoạt, quyền tạm thời và kiểm tra lại phải dùng bản ghi HR mới nhất có thẩm quyền.
- **Tuyển dụng bị hủy:** account chuẩn bị trước, lời mời, credential và entitlement phải được thu hồi hoặc vô hiệu hóa theo chính sách.
- **Người chuyển vai trò ngay trong onboarding:** tính lại danh sách mục tiêu bắt buộc thay vì dùng policy cho vai trò cũ.
- **Ứng dụng trả kết quả chậm:** đánh dấu `PARTIAL` hoặc `PENDING` kèm retry, deadline và owner, không cho qua vì đã quá thời gian.
- **Người có nhiều quan hệ làm việc:** một lần Joiner mới không được làm mất quyền hợp lệ của quan hệ khác hoặc tái sử dụng sai account.
- **Đăng nhập trước khi công việc bắt đầu:** chính sách phải quyết định có được phép vào cổng chuẩn bị onboarding hay không; nếu được phép, giới hạn tài nguyên và thời hạn.

SLA kỹ thuật cho từng hệ thống nên được xác định từ mức quan trọng của ứng dụng, yêu cầu công việc và rủi ro. Không có một ngưỡng thời gian chung áp dụng cho mọi tổ chức.

## 13. Quyền đặc biệt, tài khoản dịch vụ và người chịu trách nhiệm

**Một nhân viên mới không mặc nhiên cần tài khoản quản trị hoặc service account.** Nếu công việc đòi hỏi quyền đặc biệt, quá trình Joiner nên tạo một nhánh phê duyệt và nghiệm thu riêng:

| Trường hợp | Kiểm tra bổ sung |
| --- | --- |
| Tài khoản đặc quyền | Đúng chủ thể, tách tài khoản khi chính sách yêu cầu, xác thực mạnh, phạm vi hẹp, log truy cập |
| Quyền truy cập dữ liệu nhạy cảm | Chủ tài nguyên phê duyệt, scope theo dự án/tenant, thời hạn và kiểm tra truy cập ngoài phạm vi |
| Tài khoản dịch vụ do người mới phụ trách | Xác minh **ownership** của workload, không tự gán credential máy vào tài khoản cá nhân |
| Workload identity mới | Có ứng dụng/môi trường chịu trách nhiệm, entitlement tối thiểu, vòng đời khóa/credential và người phê duyệt |
| Quyền hỗ trợ tạm thời | Cần thời hạn, lý do, phê duyệt và tự thu hồi theo chính sách |

Nếu người mới được chỉ định quản trị một bot triển khai đang chạy, cần cập nhật quan hệ **người chịu trách nhiệm** và quyền cá nhân cần thiết. Không nên nhân bản service account chỉ vì nhân viên mới bắt đầu, hay chuyển secret thô qua kênh onboarding không được phép.

Về sau, khi người đó **Mover** hoặc **Leaver**, quan hệ sở hữu và những quyền cá nhân phát sinh từ Joiner phải được rà soát, chuyển giao hoặc thu hồi. Bằng chứng ca Joiner cần đủ để truy ngược quyền nào được cấp do chính sách mặc định, quyền nào do phê duyệt và quyền nào thuộc phạm vi công việc tạm thời.

## 14. Tình huống thực tế: Joiner hoàn tất một phần

**Bối cảnh:** Linh là nhân viên phân tích dữ liệu, có ngày bắt đầu 01/12. HRIS đã xác nhận thông tin và IAM xác minh đúng identity của Linh. Chính sách Joiner yêu cầu IdP, MFA, công cụ báo cáo và kho tài liệu nhóm; quyền cloud administrator không nằm trong nhu cầu công việc.

Trạng thái đối soát sáng ngày đầu:

| Hạng mục | Trạng thái | Nhận định |
| --- | --- | --- |
| Nguồn HR và ngày có hiệu lực | Xác minh đạt | Có căn cứ cho Joiner |
| Identity và account IdP | Đã tạo, đúng liên kết | Đạt điều kiện tài khoản trung tâm |
| Chính sách MFA | Đã áp dụng, chờ Linh đăng ký phương thức | Chưa hoàn tất bước kích hoạt nếu chính sách yêu cầu |
| Account công cụ báo cáo | Có account, nhóm `data-analysts` | Cần đọc lại quyền dashboard cụ thể |
| Dashboard Dự án Atlas | Thiếu quyền đọc | Quyền bắt buộc chưa đạt |
| Kho tài liệu nhóm | Đúng quyền xem | Đạt |
| Role `cloud-admin` | Bị cấp nhầm | Vi phạm quyền tối thiểu; phải xử lý ngay |

**Đánh giá:** Không thể kết luận Joiner hoàn tất. Cần thu hồi role `cloud-admin` được cấp nhầm, cấp đúng quyền dashboard Atlas theo chính sách/phê duyệt, kiểm tra lại quyền hiệu lực và xử lý trạng thái MFA. Việc Linh đăng nhập thành công vào một ứng dụng khác **không làm hợp lệ** quyền quản trị cấp nhầm.

Quy trình khắc phục:

1. Ghi nhận **sai lệch quyền** với mức ưu tiên phù hợp, thu hồi `cloud-admin` và xác minh không còn đường quyền quản trị khác.
2. Đối chiếu mapping vai trò hoặc group đã gây sai lệch để ngăn lặp cho Joiner tiếp theo.
3. Kiểm tra phê duyệt quyền dashboard Atlas, cấp quyền còn thiếu, đọc lại trạng thái thực tế.
4. Theo dõi Linh hoàn thành bước MFA theo kênh được phê duyệt; không lấy mã OTP hoặc token làm bằng chứng lưu trong hồ sơ.
5. Cập nhật trạng thái từng hạng mục, lưu người xử lý, nguồn quyết định và thời điểm kiểm chứng.
6. Khi các cổng bắt buộc đạt, ghi `TECHNICALLY_READY` hoặc `COMPLETED` theo tiêu chí quy trình đã định.

Một lỗi được sửa **không xóa lịch sử sai lệch**. Bản ghi kiểm toán cần giữ đủ dấu vết để giải thích khi nào quyền quản trị bị cấp nhầm, khi nào đã thu hồi và đã xác minh bằng cách nào.

## 15. Checklist nghiệm thu Joiner

Trước khi đóng một ca Joiner, người thực hiện có thể dùng checklist sau. Đối với hạng mục không áp dụng, cần ghi rõ lý do theo chính sách:

| Điều kiện kiểm tra | Trạng thái cần đạt |
| --- | --- |
| Nguồn nhân sự/bảo trợ có thẩm quyền, trạng thái và ngày hiệu lực hợp lệ | **PASS** |
| Danh tính được xác minh và liên kết đúng người/workload, không có gộp nhầm | **PASS** |
| Organization, job/assignment, manager/sponsor được xác định đúng | **PASS** |
| Tài khoản IdP được tạo/liên kết, trạng thái hoạt động đúng thời điểm | **PASS** |
| Chính sách đăng nhập, MFA, recovery được thiết lập; bước cần người dùng làm được theo dõi | **PASS hoặc PENDING theo cổng nghiệm thu** |
| Danh sách ứng dụng bắt buộc được chốt từ chính sách và vai trò | **PASS** |
| Mỗi ứng dụng bắt buộc có account thực tế liên kết đúng identity | **PASS** |
| Các entitlement bắt buộc có căn cứ, scope, phê duyệt và hạn thích hợp | **PASS** |
| Không có role/nhóm/quyền quá rộng hay truy cập ngoài phạm vi | **PASS** |
| Đã đọc lại và đối soát quyền hiệu lực tại hệ thống đích | **PASS** |
| Quyền nhạy cảm, tài khoản đặc quyền/workload (nếu áp dụng) có owner và kiểm soát riêng | **PASS hoặc NOT_APPLICABLE có căn cứ** |
| Không còn lỗi provisioning bắt buộc hoặc ngoại lệ bảo mật chưa xử lý | **PASS** |
| Có dấu vết audit theo từng hạng mục và người chịu trách nhiệm | **PASS** |
| User activation và business sign-off (nếu bắt buộc) đã hoàn tất | **PASS để đóng nghiệp vụ** |

Một giá trị `SKIPPED` chỉ hợp lệ nếu **hạng mục không áp dụng** theo chính sách đã định, không phải cách che lỗi. Nếu thiếu bằng chứng hoặc mục tiêu bắt buộc đang lỗi, cần giữ ca ở trạng thái chưa hoàn tất và hiển thị người chịu trách nhiệm cùng bước xử lý tiếp theo.

## 16. Chỉ số chất lượng và cải tiến quy trình

Xác minh Joiner cũng cung cấp dữ liệu cải tiến vận hành, chứ không chỉ phục vụ một ca nhân sự:

- **Tỷ lệ sẵn sàng kỹ thuật đúng ngày bắt đầu:** số Joiner đủ các mục tiêu bắt buộc theo thời điểm quy định.
- **Thời gian từ nguồn HR được xác nhận đến lúc quyền hiệu lực:** đo ở hệ thống đích, không chỉ lúc connector nhận lệnh.
- **Số Joiner có quyền vượt nhu cầu:** phát hiện cấp sai role/nhóm hoặc ACL.
- **Tỷ lệ account không liên kết được identity:** phát hiện tài khoản mồ côi, trùng hoặc mapping lỗi.
- **Tỷ lệ provisioning thành công nhưng reconciliation thất bại:** chỉ ra hệ thống trả kết quả thành công nhưng thực thi chưa đúng.
- **Số ca chờ activation/MFA:** phân biệt lỗi kỹ thuật với bước người dùng chưa thực hiện.
- **Tỷ lệ thay đổi Joiner do HR điều chỉnh ngày hoặc vai trò:** đánh giá chất lượng dữ liệu đầu vào và quy tắc xử lý sự kiện mới.
- **Tỷ lệ hạng mục bắt buộc quá hạn:** giúp phân công xử lý và xác định nút thắt vận hành.

Các số liệu nên được phân loại theo loại danh tính và mức quan trọng của hệ thống để tránh tỷ lệ “hoàn tất” che giấu sự cố ở một ứng dụng nhạy cảm. Khi đo thời gian, cần giữ riêng **mốc nghiệp vụ có hiệu lực**, **thời điểm IAM nhận**, **thời điểm thao tác kỹ thuật** và **thời điểm hệ thống đích xác nhận**.

### Liên kết với Mover và Leaver

Danh sách account và entitlement được nghiệm thu khi Joiner là **đường chuẩn kiểm soát quyền** trong vòng đời. Khi một người chuyển vai trò, IAM cần so sánh quyền đang có với quyền mới, thu hồi phần không còn căn cứ. Khi người đó rời tổ chức, hệ thống cần tìm đủ account, nhóm, ACL, phiên, token và quyền truy cập đã được cấp trong quá trình Joiner hoặc phát sinh về sau.

Không nên coi việc Joiner đã hoàn tất là bảo đảm quyền vẫn đúng mãi mãi. Các thay đổi về HR, nhóm, ứng dụng hoặc quyền cấp trực tiếp cần được rà soát liên tục để giảm **quyền truy cập tồn dư**.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Một hệ thống báo “SCIM user created: success”, nhưng người mới vẫn chưa xem được dashboard cần thiết. Joiner đã hoàn tất chưa?

**Trả lời:** Chưa nếu dashboard là quyền bắt buộc. Cần xác minh account, mapping nhóm/role, quyền hiệu lực tại dashboard và cơ chế thực thi ở ứng dụng.

**Câu 2:** Người mới chưa đăng nhập lần đầu vì còn chưa nhận thiết bị. Có được ghi “technical readiness = verified” không?

**Trả lời:** Có thể, nếu mọi cổng kỹ thuật bắt buộc đã được chứng minh và đăng nhập lần đầu được theo dõi ở cổng activation riêng. Nếu MFA hoặc bước kích hoạt thực tế là điều kiện bắt buộc cho mốc đang nghiệm thu, phải thể hiện trạng thái còn chờ.

**Câu 3:** Một nhân viên chỉ cần quyền đọc dự án nhưng bị gán nhóm admin. Nếu các ứng dụng khác đều chạy được thì có thể đóng Joiner không?

**Trả lời:** Không. Đây là quyền vượt phạm vi, cần thu hồi, đánh giá nguyên nhân và xác minh lại.

**Câu 4:** HRIS dời ngày bắt đầu sau khi tài khoản đã được tạo. Trạng thái Joiner phải làm gì?

**Trả lời:** Áp dụng phiên bản nguồn có thẩm quyền mới nhất, tính lại lịch kích hoạt và các quyền liên quan, ngăn tài khoản được dùng quá sớm, ghi nhận việc điều chỉnh và đọc lại trạng thái đích.

**Câu 5:** Vì sao cần lưu kết quả xác minh Joiner khi đã có danh sách nhóm trong IdP?

**Trả lời:** Vì nhóm IdP có thể khác quyền hiệu lực trong ứng dụng, và cần có căn cứ HR, phê duyệt, thời hạn, kết quả đồng bộ, chứng cứ quyền đã cấp để quản trị Mover/Leaver và kiểm toán.

## 18. Tổng kết

**Xác minh hoàn tất Joiner** là bước chứng minh một danh tính mới đã được đưa vào IAM **đúng chủ thể, đúng thời điểm, đúng tài khoản, đúng phạm vi quyền và đúng yêu cầu bảo mật**. Một ca Joiner chỉ đạt mốc hoàn tất khi **mọi điều kiện bắt buộc của mốc đó** được kiểm chứng và có dấu vết truy vết; việc đã gửi lệnh provisioning hoặc tạo thành công tài khoản IdP chỉ là bằng chứng cho một phần quy trình.

Trong mô hình **Joiner–Mover–Leaver**, HRIS hoặc nguồn bảo trợ cung cấp căn cứ, IAM quản trị vòng đời và quyết định theo chính sách, IdP/SSO hỗ trợ xác thực, SCIM/API giúp cung cấp tài khoản, còn RBAC/ABAC và hệ thống đích quyết định quyền thực tế. Phân biệt **sẵn sàng kỹ thuật**, **kích hoạt bởi người dùng** và **đóng nghiệp vụ**, đồng thời đối soát cả quyền thiếu và quyền thừa, giúp tổ chức onboarding hiệu quả và có cơ sở giảm quyền truy cập tồn dư trong những giai đoạn sau.
