# Tạo account thủ công trong Account provisioning: quy trình, kiểm soát và xác minh

Trong **Identity and Access Management (IAM)**, **tạo account thủ công** (*manual account provisioning*) là việc một người vận hành được ủy quyền dùng giao diện quản trị hoặc thủ tục được phê duyệt để tạo tài khoản trên một hệ thống đích. Cách này thường áp dụng khi ứng dụng chưa hỗ trợ **SCIM**, API quản trị phù hợp hoặc kết nối provisioning tự động; đôi khi được dùng cho trường hợp đặc biệt cần xử lý có kiểm soát.

**Thủ công không có nghĩa là cấp quyền tùy ý.** Mỗi account vẫn phải liên kết với đúng danh tính, có căn cứ nghiệp vụ, được cấp đúng quyền, có dấu vết về người phê duyệt và người thực hiện, được kiểm tra sau khi tạo và tiếp tục được quản lý khi chủ thể thay đổi vai trò hoặc rời tổ chức.

Bài thuộc chương **Account provisioning** trong module quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**. Nội dung kết nối nguồn dữ liệu nhân sự, xác minh danh tính, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán, đối soát và giảm quyền truy cập tồn dư. Mục tiêu là thiết kế một quy trình **có thể vận hành và kiểm toán** cho bước tạo account thủ công, kể cả khi công cụ IAM không thể trực tiếp thao tác trên hệ thống đích.

## 1. Tạo account thủ công là gì?

**Account** là một thực thể do ứng dụng hoặc nền tảng cụ thể quản lý: ví dụ tài khoản trong ERP, CRM, dịch vụ thư mục, công cụ quản lý mã nguồn hoặc hệ thống vận hành cũ. Một **identity** đại diện cho người hoặc workload có thể liên kết với nhiều account khác nhau.

Ở bước provisioning tự động, connector thường gửi API/SCIM và nhận kết quả. Ở bước provisioning thủ công, hệ thống IAM có thể tạo **ticket hoặc task**, còn quản trị viên ứng dụng mở giao diện đích để thao tác. Dù thao tác bằng tay, quyết định có được cấp tài khoản hay không vẫn phải xuất phát từ **nguồn có thẩm quyền, chính sách và phê duyệt hợp lệ**.

| Nội dung | Tạo account thủ công | Provisioning tự động |
| --- | --- | --- |
| Ai tạo account tại hệ thống đích? | Quản trị viên hoặc người vận hành được phân quyền, thông qua UI/quy trình đã duyệt. | Connector/IAM service qua SCIM, API hoặc cơ chế tích hợp. |
| Đầu vào | Yêu cầu được xác minh, phê duyệt và kế hoạch quyền. | Sự kiện, chính sách và dữ liệu đã qua kiểm soát tương ứng. |
| Rủi ro đặc trưng | Nhập sai định danh, bỏ qua một bước, cấp thừa role, quên ghi kết quả. | Mapping sai, lỗi API, xử lý sự kiện trùng hoặc không đồng bộ hoàn tất. |
| Bằng chứng tối thiểu | Request/approval, actor thực hiện, target account ID, entitlement, thời điểm, readback. | Event/policy, API result, account mapping và readback/reconciliation. |
| Trách nhiệm vòng đời | Phải có chủ sở hữu để cập nhật, rà soát và thu hồi về sau. | Cũng phải có owner, giám sát và đối soát; tự động không bảo đảm đúng hoàn toàn. |

**Ví dụ:** ứng dụng ERP cũ chỉ có màn hình “User Administration”. HR xác nhận nhân viên mới; IAM tính quyền cơ bản và sinh yêu cầu; application owner phê duyệt quyền cần thiết; quản trị viên ERP tạo account, gán role rồi ghi lại **ID tài khoản tại ERP** cùng bằng chứng kiểm tra. Sau đó IAM lưu mapping giữa identity và ERP account để xử lý **Mover/Leaver**. Nếu về sau ứng dụng hỗ trợ SCIM, quy trình có thể được tự động hóa, nhưng vẫn cần bảo toàn các kiểm soát và lịch sử.

### 1.1. Phân biệt các khái niệm liên quan

| Khái niệm | Câu hỏi chính | Không nên đánh đồng |
| --- | --- | --- |
| **Identity enrollment** | Đã xác minh và lập bản ghi danh tính cho đúng chủ thể chưa? | Có identity không đồng nghĩa đã có account trong mọi ứng dụng. |
| **Account provisioning** | Account ở hệ thống đích đã được tạo/cập nhật để dùng chưa? | Có account không đồng nghĩa có mọi quyền cần thiết. |
| **Entitlement provisioning** | Role, group, license hoặc permission nào đã được cấp? | Có thể diễn ra cùng lúc hoặc sau khi tạo account. |
| **Authentication (AuthN)** | Chủ thể chứng minh danh tính khi đăng nhập thế nào? | SSO/MFA không tự quyết định entitlement nghiệp vụ. |
| **Authorization (AuthZ)** | Hành động lên tài nguyên có được cho phép không? | Tồn tại account không tự động cho phép mọi hành động. |
| **Reconciliation** | Trạng thái account và quyền thực tế có khớp trạng thái mong muốn không? | “Đã bấm Save” chưa phải bằng chứng quyền đúng. |
| **Deprovisioning** | Quyền/tài khoản được thu hồi, vô hiệu hóa hoặc xóa theo chính sách thế nào? | Khóa account tại IdP không nhất thiết khóa mọi đường đăng nhập ứng dụng. |

**Lưu ý về thuật ngữ “manual”:** tài khoản được **tạo thủ công** vẫn có thể đăng nhập bằng **SSO**. Ngược lại, một ứng dụng dùng SSO chưa chắc có cơ chế tạo tài khoản tự động. Nếu ứng dụng hỗ trợ **Just-in-Time (JIT) user provisioning** khi người dùng đăng nhập lần đầu, việc tạo user có thể diễn ra tự động ở ứng dụng; đó là cơ chế khác với quy trình tạo account thủ công. **JIT user provisioning** cũng khác **JIT privileged access** (cấp quyền đặc quyền tạm thời).

## 2. Khi nào cần tạo account thủ công?

Các tình huống thường gặp:

1. **Ứng dụng legacy** chỉ hỗ trợ tạo user qua màn hình quản trị, không có SCIM/API quản lý tài khoản.
2. **Kết nối tự động chưa sẵn sàng** nhưng tổ chức vẫn phải triển khai quyền đã được phê duyệt trong phạm vi kiểm soát.
3. **Quyền đặc thù** cần kiểm tra bổ sung trước khi account được kích hoạt, như ứng dụng tài chính, hệ thống vận hành hoặc hệ thống quản trị nhạy cảm.
4. **Khối lượng thấp và có owner rõ**: một ứng dụng ít người dùng, có quy trình tạo/thu hồi thủ công được quản lý chặt.
5. **Trường hợp ngoại lệ** như tài khoản nhà thầu, tài khoản kỹ thuật có lý do riêng hoặc giai đoạn chuyển đổi hệ thống.

Nếu cần thực hiện thủ công, việc đánh giá phải xét **toàn bộ vòng đời**, không chỉ nỗ lực tạo mới. Ứng dụng có thể chỉ có vài yêu cầu Joiner mỗi tháng nhưng phát sinh rất nhiều Mover, Leaver, thay đổi nhóm và rà soát quyền; không có owner cho các bước tiếp theo sẽ làm tăng quyền tồn dư.

### 2.1. Những trường hợp phải thận trọng hơn

- **Tài khoản đặc quyền:** yêu cầu thẩm quyền phê duyệt, bảo vệ credential, kiểm soát phiên và khả năng thu hồi phù hợp mức rủi ro.
- **Ứng dụng quản lý dữ liệu nhạy cảm:** role cần gắn với phạm vi tài nguyên, phê duyệt của data/application owner và kiểm soát SoD nếu liên quan.
- **Tài khoản có xác thực local:** tạo account đồng thời tạo đường đăng nhập riêng; phải quản lý mật khẩu, MFA, khóa account và phiên độc lập với IdP.
- **Shared account:** khó quy trách nhiệm cho từng cá nhân; ưu tiên account riêng, chỉ dùng account chung khi có lý do và kiểm soát bổ sung.
- **Service account:** phải có định danh workload, owner, mục đích, phạm vi quyền, cơ chế cấp/thu hồi secret và vòng đời riêng.
- **Truy cập khẩn cấp:** không thể dựa vào “cần gấp” để bỏ qua việc ghi nhận, theo dõi, hạn chế quyền và rà soát sau sự kiện.

## 3. Điều kiện đầu vào trước khi tạo account

Quản trị viên chỉ nên thao tác khi yêu cầu đã đủ căn cứ và dữ liệu có thể đối chiếu.

| Nhóm thông tin | Nội dung cần có | Mục đích |
| --- | --- | --- |
| **Chủ thể** | Identity ID, loại đối tượng (nhân viên, nhà thầu, workload), tham chiếu HR/contractor phù hợp. | Xác định đúng người hoặc hệ thống sở hữu account. |
| **Nguồn có thẩm quyền** | Trạng thái quan hệ, ngày bắt đầu/kết thúc hoặc quyết định cấp quyền. | Ngăn tạo hoặc kích hoạt account khi chưa được phép. |
| **Ứng dụng đích** | Tên/ID hệ thống, tenant, môi trường, loại account. | Tránh tạo trong nhầm môi trường production/test hoặc sai tenant. |
| **Mục đích nghiệp vụ** | Công việc cần làm, sponsor/manager, yêu cầu hoặc ticket ID. | Có lý do cấp tài khoản và người chịu trách nhiệm. |
| **Entitlement mong muốn** | Role/group/license/scope cụ thể, thời hạn, điều kiện RBAC/ABAC. | Giới hạn quyền theo least privilege. |
| **Phê duyệt** | Người có thẩm quyền, quyết định, thời điểm, ngoại lệ/SoD nếu có. | Chứng minh quyền được cấp hợp lệ. |
| **Thông tin account** | Quy tắc username, khóa account có sẵn, yêu cầu liên kết SSO và MFA. | Tránh tạo trùng hoặc liên kết sai người. |
| **Kế hoạch bàn giao** | Thời điểm cho phép truy cập, cách mời/kích hoạt, owner hỗ trợ. | Không mở đường đăng nhập trước khi đủ điều kiện. |
| **Kế hoạch vòng đời** | Quy trình xử lý Mover/Leaver, ngày hết hạn và cách kiểm tra. | Bảo đảm account không bị bỏ quên sau khi tạo. |

**Nguồn có thẩm quyền** không nhất thiết là một hệ thống cho tất cả thuộc tính. HRIS có thể chuẩn cho trạng thái lao động, hệ thống quản lý đối tác chuẩn cho hợp đồng nhà thầu, còn application owner mới quyết định vai trò nhạy cảm của ERP. Quy trình cần chỉ rõ trường nào lấy từ đâu.

### 3.1. Người mới chưa có employee identifier

Nếu HR chưa cấp employee number, IAM có thể dùng **identity ID nội bộ** hoặc tham chiếu được phê duyệt để theo dõi yêu cầu đang chờ; không nên gán mã giả chung cho nhiều người. Có thể chuẩn bị account **chưa hoạt động** theo chính sách, nhưng kích hoạt và cấp quyền phải dựa trên điều kiện có hiệu lực.

Không nên chỉ dựa vào tên, email hoặc số điện thoại để kết luận một account đã tồn tại thuộc đúng người. Khi phát hiện trùng, cần kiểm tra **account correlation** dựa trên các khóa và bằng chứng được tổ chức công nhận.

### 3.2. Ma trận trách nhiệm tham khảo

| Hoạt động | Người/nhóm thường thực hiện | Trách nhiệm giải trình cần xác định |
| --- | --- | --- |
| Xác nhận người mới/nhà thầu | HR hoặc sponsor theo phạm vi. | Chủ sở hữu bản ghi nhân sự/hợp đồng. |
| Xác định nhu cầu và role | Manager, business owner. | Owner của quyền nghiệp vụ và phạm vi truy cập. |
| Phê duyệt quyền nhạy cảm | Application/data owner và bên liên quan theo policy. | Người có thẩm quyền đối với entitlement đó. |
| Tạo account thủ công | Application admin/operator được phân quyền. | Owner vận hành và người thực hiện cụ thể. |
| Kiểm tra việc tạo/quyền | Operator khác, IAM hoặc reviewer độc lập theo rủi ro. | Người chịu trách nhiệm chấp nhận bằng chứng hoàn thành. |
| Rà soát, thu hồi, khắc phục lỗi | Application owner, IAM, service desk, security tùy công việc. | Chủ quy trình và owner của từng target. |

Đây là ví dụ phân vai, không phải một RACI bắt buộc. Với account nhạy cảm, nên tách **người yêu cầu**, **người phê duyệt**, **người thực hiện** và **người kiểm tra** phù hợp với yêu cầu **Segregation of Duties (SoD)**. Một người thao tác trong UI không được tự tạo ra thẩm quyền phê duyệt cho chính mình chỉ vì họ có quyền quản trị kỹ thuật.

## 4. Quy trình tạo account thủ công đầu cuối

~~~mermaid
flowchart TD
    A["HRIS / sponsor: Joiner hoặc access request"] --> B["IAM xác minh identity, trạng thái, effective date"]
    B --> C{"Account đã tồn tại?"}
    C -->|Có, khớp| D["Liên kết account; rà soát quyền cần thay đổi"]
    C -->|Có, không chắc| E["Dừng và xử lý trùng / conflict"]
    C -->|Chưa có| F["Tính quyền cần thiết, owner và thời hạn"]
    F --> G{"Policy, approval, SoD đạt?"}
    G -->|Không| H["Chờ duyệt / từ chối"]
    G -->|Có| I["Tạo ticket có scope và điều kiện kích hoạt"]
    I --> J["Operator tạo account ở ứng dụng"]
    J --> K["Gán role tối thiểu, thiết lập xác thực phù hợp"]
    K --> L["Readback account ID, trạng thái và entitlement"]
    D --> L
    L --> M{"Khớp desired state?"}
    M -->|Không| N["Giao owner khắc phục, cập nhật ticket"]
    N --> L
    M -->|Có| O["Ghi binding, audit evidence, đóng yêu cầu"]
~~~

### Bước 1 — Tiếp nhận và xác minh yêu cầu

Một ticket hợp lệ cần gắn với sự kiện nhân sự, yêu cầu truy cập hoặc nhiệm vụ được phê duyệt. Xác minh **identityId**, nguồn, quan hệ đang có hiệu lực, thời điểm kích hoạt và ứng dụng đích. Nếu dữ liệu mâu thuẫn, người vận hành phải chuyển về **cần xác minh** thay vì đoán.

Ví dụ, HR đã ghi nhận nhân viên bắt đầu ngày 01/10; ngày 25/09 bộ phận hỗ trợ đề nghị chuẩn bị ERP. Có thể tạo account ở trạng thái khóa/chờ nếu nền tảng cho phép, nhưng không nên mở quyền thao tác giao dịch trước ngày có hiệu lực chỉ vì ticket đã được tạo.

### Bước 2 — Kiểm tra account hiện có và chống tạo trùng

Trước khi bấm **Create User**, tra cứu theo tiêu chí được phép: target account ID đã lưu, mã định danh liên kết với HR/IAM, username hiện tại và lịch sử account của ứng dụng. Xác định kết quả thuộc một trong ba trường hợp:

1. **Đã tồn tại, liên kết chắc chắn:** cập nhật mapping và quyền nếu cần; không tự tạo account thứ hai.
2. **Chưa tồn tại:** tiếp tục tạo mới theo quy tắc username và tenant.
3. **Có bản ghi giống hoặc không rõ chủ sở hữu:** tạm dừng và chuyển xử lý identity collision; không tự merge hoặc cấp quyền cho account chưa xác minh.

Nhiều ứng dụng không có khóa thống nhất với IdP. Vì vậy, cần lưu **identity ID + hệ thống đích + target account ID** làm binding sau thao tác. Username/email có thể thay đổi và có thể được tái sử dụng, không nên là căn cứ duy nhất cho các quyết định có rủi ro.

### Bước 3 — Xác định entitlement và phê duyệt

Trước khi tạo, ghi rõ tập quyền mong muốn. Phân biệt:

- **Baseline access:** quyền cơ bản được phép tự cấp theo chính sách đã duyệt.
- **Business role:** trách nhiệm nghiệp vụ dùng để chọn quyền.
- **Technical entitlement:** group/role/license/permission cụ thể của ứng dụng.
- **Temporary/exception access:** quyền có lý do, owner, thời điểm hết hạn và kiểm tra bổ sung.
- **Privileged access:** quyền quản trị nhạy cảm, thường cần bảo vệ/giám sát mạnh hơn.

**RBAC** gắn quyền với role; **ABAC** có thể xét thêm đơn vị, địa điểm, dự án, mức nhạy cảm và ngữ cảnh khi thực thi. Account được tạo thủ công vẫn phải nằm trong phạm vi chính sách RBAC/ABAC chung. Nếu người vận hành không hiểu ứng dụng đang ánh xạ role sang permission nào, nên yêu cầu application owner xác nhận trước khi chọn role rộng.

**SoD** có thể ngăn một người cùng có quyền tạo và duyệt thanh toán. Kiểm tra nên xét **quyền đang có trong các ứng dụng liên quan**, không chỉ role sắp cấp trong ticket.

### Bước 4 — Tạo account trong đúng ứng dụng và môi trường

Người được giao nhiệm vụ vào UI quản trị **đúng tenant/môi trường** và thao tác theo runbook đã được quản trị. Những điểm cần bảo đảm:

1. Chọn chính xác loại account: human, contractor, service hay privileged theo khả năng ứng dụng.
2. Nhập thông tin định danh đã được kiểm tra, dùng username theo quy tắc được duyệt; tránh dùng email làm khóa danh tính bất biến.
3. Liên kết với **IdP/SSO** nếu ứng dụng được cấu hình hỗ trợ và quy trình yêu cầu; kiểm tra mapping subject/account.
4. Chọn trạng thái phù hợp ngày hiệu lực, ví dụ disabled/staged cho tài khoản chuẩn bị sớm nếu ứng dụng hỗ trợ.
5. Gán **role, group, phạm vi dữ liệu** đúng quyết định đã phê duyệt; không để role mặc định quá rộng không được xem xét.
6. Ghi nhận **target account ID** mà ứng dụng trả về hoặc hiển thị, thời điểm thao tác và danh tính operator.
7. Không gửi thông tin xác thực nhạy cảm vào ticket/chat/email không bảo vệ; dùng cơ chế mời người dùng hoặc kênh cấp phát credential phù hợp.

Trong nhiều sản phẩm, tạo user sẽ tự gán role, license hoặc kích hoạt quyền mặc định. Vì thế **trước khi bấm lưu** và **sau khi lưu**, cần kiểm tra default groups/roles. Không được coi “màn hình tạo chỉ có một checkbox” là bằng chứng ứng dụng không tự cấp thêm quyền.

### Bước 5 — Thiết lập đường đăng nhập an toàn

**Hai mô hình đăng nhập khác nhau cần được kiểm soát riêng:**

| Mô hình | Việc cần kiểm tra |
| --- | --- |
| **SSO qua IdP** | Account ứng dụng có liên kết với subject đúng người không? Người dùng có MFA/chính sách AuthN tại IdP không? Ứng dụng có login local độc lập cần khóa hoặc giám sát không? |
| **Xác thực local tại ứng dụng** | Cơ chế mời/kích hoạt hoặc đặt credential có an toàn không? MFA có hỗ trợ/bắt buộc không? Password reset, lockout, session và thu hồi credential do ai chịu trách nhiệm? |

Ưu tiên **invitation/activation link có giới hạn thời gian** hoặc quy trình tự thiết lập mật khẩu qua kênh chính thức khi ứng dụng hỗ trợ. Nếu hệ thống buộc dùng mật khẩu tạm, cần tạo theo chính sách mạnh, chuyển qua kênh bảo mật, yêu cầu thay đổi khi dùng lần đầu nếu có thể và xóa/hạn chế bản sao không cần thiết. **Không ghi mật khẩu tạm, secret, API key hoặc token đầy đủ trong ticket** để chứng minh account đã tạo.

**MFA** nên áp dụng theo mức nhạy cảm và khả năng ứng dụng. Một account được tạo nhưng chưa đăng ký yếu tố xác thực bắt buộc có thể ở trạng thái **chờ hoàn tất onboarding**, thay vì được coi là sẵn sàng sử dụng.

### Bước 6 — Đọc lại từ ứng dụng và kiểm chứng

Người kiểm tra phải xác nhận **actual state** từ nguồn đáng tin ở hệ thống đích:

| Đối tượng kiểm tra | Câu hỏi |
| --- | --- |
| **Account identity** | Target account ID và username có liên kết với đúng IAM identity không? |
| **Status** | Account active/disabled/staged có khớp ngày hiệu lực và quyết định không? |
| **Role/group/license** | Đúng quyền mong muốn? Có role mặc định, quyền kế thừa hoặc direct grant không được duyệt? |
| **Data scope** | Quyền xem/sửa có giới hạn theo đúng đơn vị, khách hàng, môi trường hoặc tài nguyên không? |
| **Login path** | SSO/local login được cấu hình đúng; MFA và yêu cầu kích hoạt có đạt không? |
| **Expiration** | Nếu là nhà thầu/quyền tạm, ngày hết hạn hoặc tác vụ thu hồi có được ghi nhận không? |
| **Evidence** | Ai thực hiện, ai kiểm tra, lúc nào, bằng chứng nào xác nhận kết quả? |

Với quyền nhạy cảm, một người khác operator có thể kiểm tra độc lập theo chính sách. Ảnh chụp màn hình có thể hỗ trợ, nhưng nên hạn chế dữ liệu cá nhân/secret và ưu tiên log/export trạng thái có thời điểm, account ID và nguồn rõ ràng nếu công cụ cho phép.

**Lưu ý:** thao tác “Save successful” chỉ cho biết ứng dụng nhận thao tác. Nó không chứng minh tất cả quyền đã được áp dụng đúng hoặc account đang bị chặn đúng trạng thái. Nếu hệ thống xử lý bất đồng bộ, cần đọc lại sau khi đồng bộ ổn định theo điều kiện được định nghĩa.

### Bước 7 — Ghi binding, hoàn tất và bàn giao vòng đời

Sau khi kiểm chứng:

- Lưu mapping **IAM identity ID → application/tenant → target account ID** với trạng thái có hiệu lực.
- Ghi entitlement được cấp, căn cứ phê duyệt, owner ứng dụng, ngày bắt đầu/kết thúc và **correlation/ticket ID**.
- Ghi kết quả kiểm chứng tại đích, lỗi còn tồn tại hoặc ngoại lệ đã được chấp thuận.
- Bảo đảm account xuất hiện trong nguồn kiểm kê để xử lý **Mover/Leaver** và **access review**.
- Chỉ đóng ticket ở trạng thái **verified complete** khi các điều kiện bắt buộc đã đạt.

Account tạo thủ công không nằm trong inventory IAM là một nguy cơ tạo **orphaned account**: về sau không xác định được account thuộc ai để thu hồi.

## 5. Mẫu ticket và bằng chứng cho thao tác thủ công

Dưới đây là **schema minh họa nội bộ**, không phải một chuẩn SCIM hay API cố định. Trong hệ thống thực tế, trường thông tin phải theo chính sách tổ chức và khả năng service desk/IAM.

~~~yaml
requestId: IAM-REQ-4821
requestType: MANUAL_ACCOUNT_CREATE
source:
  system: HRIS
  eventId: JOINER-2026-1284
identity:
  identityId: person-2048
  subjectType: HUMAN
  employmentStatus: PRE_START
target:
  application: LegacyFinanceERP
  tenant: VN-PROD
  requestedAccountType: STANDARD_USER
businessNeed:
  requestedBy: manager-731
  purpose: Read assigned financial reports
  effectiveAt: "2026-10-01T08:00:00+07:00"
access:
  roles:
    - FINANCE_REPORT_READER
  scope: VN-FINANCE
  needsMfa: true
approval:
  policyRef: finance-access-policy-v4
  applicationOwner: owner-finance-erp
  decision: APPROVED
  approvalRef: APR-3512
workflow:
  status: READY_FOR_OPERATOR
  assignedOperator: app-admin-29
  requireReadback: true
  requireAccountBinding: true
~~~

Các giá trị ID, ngày và role chỉ để minh họa. Ticket không nên chứa bản sao giấy tờ proofing, password hoặc thông tin cá nhân không cần cho người thao tác. Nếu yêu cầu bị sửa sau phê duyệt, phải kiểm tra **phê duyệt còn bao phủ đúng role/scope đã sửa hay không**; không dùng approval cũ để hợp thức hóa quyền mới rộng hơn.

### 5.1. Ví dụ bản ghi hoàn tất

~~~json
{
  "requestId": "IAM-REQ-4821",
  "outcome": "VERIFIED",
  "identityId": "person-2048",
  "target": {
    "application": "LegacyFinanceERP",
    "tenant": "VN-PROD",
    "accountId": "erp-user-90018",
    "accountState": "ACTIVE",
    "observedRoles": ["FINANCE_REPORT_READER"],
    "observedScope": "VN-FINANCE"
  },
  "execution": {
    "operatorId": "app-admin-29",
    "executedAt": "2026-10-01T08:02:00+07:00",
    "method": "ADMIN_UI"
  },
  "verification": {
    "verifierId": "iam-reviewer-08",
    "verifiedAt": "2026-10-01T08:05:00+07:00",
    "status": "MATCHED_APPROVED_ACCESS"
  },
  "references": {
    "approvalId": "APR-3512",
    "auditEvent": "ERP-AUDIT-1184"
  }
}
~~~

Đây là dữ liệu **minh họa kết quả**, có thể được tổng hợp từ ticket và log đích; không nhất thiết ứng dụng ERP tự xuất ra đúng một đối tượng JSON như trên. Trường **observedRoles** chứng minh quyền đã được kiểm tra, còn **accountId** phục vụ đối soát và thu hồi sau này.

### 5.2. Trạng thái workflow nên phân biệt

| Trạng thái | Ý nghĩa | Có thể đóng như đã cấp hoàn tất? |
| --- | --- | --- |
| **REQUESTED** | Đã nhận yêu cầu nhưng chưa đủ kiểm tra. | Không. |
| **PENDING_APPROVAL** | Đang chờ thẩm quyền phê duyệt. | Không. |
| **READY_FOR_OPERATOR** | Dữ liệu và approval hợp lệ; có người được giao thao tác. | Không. |
| **IN_PROGRESS** | Operator đang thao tác, có thể đã tạo một phần. | Không. |
| **PENDING_ACTIVATION** | Account có thể đã được tạo nhưng chưa đến ngày hiệu lực/chưa hoàn tất MFA. | Không, nếu điều kiện kích hoạt là bắt buộc. |
| **PENDING_VERIFICATION** | Đã nhập thao tác; chưa đọc lại account/entitlement. | Không. |
| **FAILED / NEEDS_REMEDIATION** | Có lỗi hoặc trạng thái thực tế không khớp. | Không; phải có owner và hành động xử lý. |
| **VERIFIED** | Account, quyền, trạng thái và bằng chứng đã khớp điều kiện phải kiểm tra. | Có, theo tiêu chí đóng của quy trình. |
| **CANCELLED / REJECTED** | Yêu cầu không còn hợp lệ hoặc không được duyệt. | Đóng theo lý do từ chối/hủy, không báo đã cấp. |

Nên tách **kết quả tạo account** với **kết quả cấp entitlement** nếu sản phẩm cho phép theo dõi từng bước. Ví dụ account đã tạo nhưng không gán được role; để trạng thái chung là “Success” sẽ che giấu lỗi chưa xử lý.

## 6. Liên hệ IdP, SSO, SCIM và phân quyền

### 6.1. SSO không đồng nghĩa có account ở ứng dụng

**Identity Provider (IdP)** xác thực một người dùng và có thể phát hành SAML assertion hoặc OIDC ID token cho ứng dụng tin cậy. **Single Sign-On (SSO)** là cơ chế/luồng giúp truy cập nhiều ứng dụng dựa trên thông tin đăng nhập tập trung.

Một ERP hỗ trợ đăng nhập SAML nhưng **không hỗ trợ SCIM** vẫn có thể yêu cầu quản trị viên **tạo user trước trong ERP** và ánh xạ với subject/NameID của IdP. Nếu tên đăng nhập ở ERP không khớp cấu hình nhận dạng, người dùng có thể đăng nhập IdP thành công nhưng ứng dụng từ chối hoặc ánh xạ nhầm account.

Do đó, một bước tạo account thủ công phải kiểm tra **định danh được ứng dụng sử dụng để liên kết SSO**, không mặc nhiên đồng nhất với email hoặc employee number. Khi đổi username, domain hoặc IdP, cần giữ mapping có lịch sử và kiểm chứng lại.

### 6.2. SCIM xử lý provisioning, không tự phê duyệt quyền

**SCIM 2.0** cung cấp mô hình User/Group và giao thức để quản lý danh tính giữa các hệ thống. Một ứng dụng không hỗ trợ SCIM có thể cần thao tác thủ công hoặc API riêng. Nếu chỉ có **một phần** chức năng được SCIM hỗ trợ, tổ chức có thể tự động tạo User nhưng vẫn gán một số entitlement bằng tay; mỗi bước phải có owner và bằng chứng riêng.

SCIM không tự thay thế **decision engine** của IAM. Việc user tồn tại trong SCIM chưa chứng minh business owner đã duyệt quyền. Ngược lại, lỗi SCIM chưa chắc cho phép operator tự tạo account ngoài quy trình mà không kiểm tra bản ghi đã tồn tại, vì có thể ứng dụng đã tạo user nhưng response thất lạc.

### 6.3. RBAC/ABAC và quyền mặc định

- **RBAC:** gán role đã định nghĩa theo trách nhiệm công việc, ví dụ “Finance Report Reader”.
- **ABAC:** ứng dụng có thể xét thêm thuộc tính department, resource owner, tenant hoặc độ nhạy dữ liệu khi người dùng thực hiện hành động.
- **Least privilege:** cấp đúng quyền và phạm vi cần thiết trong đúng thời gian.
- **SoD:** đánh giá tổ hợp role có thể tạo xung đột, như người vừa tạo vừa tự phê duyệt thanh toán.
- **Access review:** sau khi cấp, owner định kỳ xác nhận quyền còn cần.

Khi tạo account bằng tay, admin dễ chọn một role “Power User” vì nó chắc chắn làm chức năng hoạt động. Cách này có thể vượt quyền đã được duyệt. Nếu role nhỏ nhất không đáp ứng nghiệp vụ, quy trình phải ghi thiếu quyền và xin quyết định mở rộng theo policy, không tự nâng đặc quyền rồi quên thu hồi.

### 6.4. Provisioning thủ công không làm mất nghĩa vụ deprovisioning

Một account không được tạo qua SCIM **vẫn phải được IAM nhìn thấy**. Khi HR báo nhân viên nghỉ việc, quy trình phải tạo ticket vô hiệu hóa/gỡ quyền cho đúng account. Nếu chỉ quản lý những account được tạo tự động, các account thủ công dễ trở thành đường truy cập tồn dư.

## 7. Vòng đời Joiner–Mover–Leaver với account thủ công

### 7.1. Joiner: tạo đúng và chỉ kích hoạt khi hợp lệ

Quy trình Joiner phải xác minh người/quan hệ, lựa chọn account cần có theo role, phê duyệt quyền đặc biệt, tạo account và thiết lập xác thực. Nếu ngày vào làm chưa đến, lựa chọn **staged/disabled** được ưu tiên khi hệ thống hỗ trợ và chính sách yêu cầu. Nếu không hỗ trợ trạng thái chờ, cần một phương án tránh truy cập sớm được owner phê duyệt, chẳng hạn chỉ thực hiện tạo gần ngày hiệu lực.

**Mục tiêu kiểm tra:** không có account trùng, username thuộc đúng identity, entitlement khớp approval và ứng dụng có thể xác thực theo luồng dự kiến sau khi kích hoạt.

### 7.2. Mover: giữ account nhưng thay đổi quyền

Khi người dùng chuyển từ vận hành sang tài chính, nhiều ứng dụng vẫn giữ cùng account ID; **quyền bên trong account** cần cập nhật. Với ứng dụng manual, IAM phải tạo ticket:

1. Xác định quyền cũ phải gỡ và quyền mới cần cấp theo business role/ABAC.
2. Kiểm tra xung đột SoD và phê duyệt quyền mới nhạy cảm.
3. Gỡ group/role/direct entitlement cũ theo thời điểm hiệu lực, có kiểm tra quyền qua đường khác.
4. Cấp quyền mới được phê duyệt, tránh cấp quá sớm khi tạo xung đột.
5. Readback tập quyền thực tế; chỉ đóng Mover khi mọi đích bắt buộc khớp chính sách.

**Tạo thêm account mới** cho cùng người chỉ vì đổi role có thể tạo account không được quản lý hoặc dư quyền cũ. Quyết định tạo account riêng phải dựa vào chính sách phân tách nhiệm vụ và ứng dụng cụ thể.

### 7.3. Leaver: thu hồi account thủ công cũng là việc bắt buộc

Khi nguồn nhân sự hoặc người bảo trợ xác nhận kết thúc quan hệ, IAM phải xác định mọi account liên quan, bao gồm **ứng dụng không hỗ trợ provisioning tự động**. Với từng target, lập tác vụ theo policy:

- **Disable/lock account** để chặn đăng nhập mới, xác minh trạng thái.
- **Revoke entitlement** hoặc xóa nhóm/quyền truy cập theo hợp đồng ứng dụng.
- **Thu hồi session/token/credential** khi có cơ chế và yêu cầu, lưu ý local login có thể độc lập IdP.
- **Xử lý ownership và dữ liệu** theo chính sách bàn giao, lưu giữ và xóa sau này.
- **Đối soát và lưu bằng chứng**: người thao tác, thời điểm hiệu lực, kết quả tại đích, lỗi và ticket khắc phục.

**Disable tài khoản tại IdP chưa chắc disable account local trong ERP.** SSO có thể đang dùng phiên đã tạo; một số ứng dụng cho phép fallback local password. Với leaver, phải xem các đường truy cập thực tế để quyết định bước thu hồi thích hợp.

### 7.4. Tài khoản nhà thầu và thời hạn truy cập

Nhà thầu thường có **sponsor**, hợp đồng và ngày hết hạn riêng. Account thủ công phải có owner và expiration/renewal task. Nếu ứng dụng không có tính năng tự hết hạn, IAM cần lên lịch thu hồi và cảnh báo trước ngày hết hạn, thay vì để trạng thái active vô thời hạn.

Nếu nhà thầu được gia hạn, yêu cầu mới phải có quyết định hợp lệ và thời hạn rõ ràng. Việc **gia hạn account** không mặc nhiên gia hạn toàn bộ đặc quyền cũ.

## 8. Tài khoản dịch vụ, đặc quyền và trường hợp ngoại lệ

### 8.1. Service account được tạo thủ công

Một hệ thống legacy có thể cần account **batch-reporter** để chạy tác vụ định kỳ. Không nên gán employee identifier của lập trình viên như thể workload là nhân viên. Hồ sơ cần:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Workload/service ID | batch-reporter | Xác định workload sử dụng account. |
| Owner/team | reporting-platform | Nhóm chịu trách nhiệm vòng đời. |
| Purpose | Xuất báo cáo nội bộ hằng đêm | Có căn cứ để đánh giá quyền. |
| Target resource | legacy-erp/report-api | Hạn chế phạm vi truy cập. |
| Entitlement | REPORT_READ_ONLY | Tránh dùng role admin cho job đọc dữ liệu. |
| Credential handling | Vault hoặc cơ chế workload identity phù hợp | Tránh lưu mật khẩu/secret trong mã nguồn và ticket. |
| Review/expiry | Theo chính sách rủi ro và vòng đời dịch vụ | Phát hiện account không còn dùng. |

Khi owner chuyển vai trò hoặc nghỉ việc, phải bàn giao ownership, đánh giá người từng biết secret và luân chuyển credential nếu cần. Không xóa service account đang phục vụ workload chỉ vì owner cá nhân rời tổ chức; cũng không để account không có owner.

### 8.2. Privileged và break-glass account

Với account quản trị, xác định rõ:

- Có lý do sử dụng account riêng biệt và quyền đặc biệt không?
- Ai phê duyệt, ai thao tác, ai kiểm tra độc lập?
- Có thể dùng **PAM/JIT privileged access** để giảm quyền thường trực không?
- Có giới hạn phiên, ghi audit, MFA hoặc biện pháp kiểm soát credential không?
- Khi hết thời hạn hoặc kết thúc khẩn cấp, ai thu hồi/đổi credential và kiểm tra?

**Break-glass account** cần phục vụ tình huống khẩn cấp theo quy trình đặc biệt, có owner, phạm vi, log và kiểm tra sau sử dụng. Không dùng quy trình khẩn cấp thường xuyên như đường vòng để tạo account bình thường mà không có approval.

### 8.3. Shared account và attribution

Nếu nhiều người cùng dùng một account, nhật ký ứng dụng có thể chỉ ghi tên account chung. Điều này gây khó **accountability** (trách nhiệm giải trình). Ưu tiên tài khoản cá nhân; nếu không tránh được, dùng biện pháp như PAM broker, phê duyệt theo phiên, lưu người nhận quyền sử dụng, giới hạn thời gian và theo dõi phiên theo chính sách.

## 9. Quản lý lỗi, tác vụ trùng và kết quả một phần

Tạo account thủ công đặc biệt dễ phát sinh **partial completion**: user đã tạo nhưng role chưa gán, MFA chưa hoàn tất, hoặc có hai operator cùng nhận một yêu cầu.

### 9.1. Chống thao tác trùng

Trước khi thao tác lại sau lỗi hoặc mất phiên:

1. Đọc ticket hiện tại và xác nhận trạng thái, operator đang sở hữu, event/request ID.
2. Kiểm tra trực tiếp target account đã tồn tại chưa; không tạo lại chỉ vì UI không hiện thông báo thành công.
3. Nếu account tồn tại, xác minh identity binding và trạng thái quyền; tiếp tục phần còn thiếu.
4. Nếu account không tồn tại, mới thực hiện tạo theo approval còn hiệu lực.
5. Ghi rõ event retry và kết quả; không xóa dấu vết thao tác trước.

Để giảm race condition, mỗi yêu cầu nên có **một owner vận hành đang nhận task**, khóa/đánh dấu xử lý phù hợp và quy trình bàn giao khi chuyển người. Account correlation phải được kiểm tra ở đúng ứng dụng/tenant, không dựa duy nhất vào username.

### 9.2. Xử lý lỗi theo trạng thái thực tế

| Lỗi / phát hiện | Hành động phù hợp |
| --- | --- |
| Approval thiếu hoặc sai scope | Dừng cấp quyền, chuyển phê duyệt hợp lệ. |
| Trùng username hoặc nghi ngờ account của người khác | Không tạo mới/ghi đè; điều tra identity/account linking. |
| Account đã tạo nhưng role gán sai | Gỡ/sửa quyền ngoài phê duyệt và xác minh; ghi audit/incident nếu cần. |
| Account đã tạo nhưng chưa thể bật MFA | Giữ trạng thái hạn chế/khóa nếu cần; theo dõi cho đến khi điều kiện hoàn tất. |
| Không thấy tài khoản sau khi Save | Kiểm tra hệ thống đích và audit trước khi thử tạo lần nữa. |
| Ticket bị hủy sau khi user đã tạo | Đánh giá/thu hồi account và entitlement vừa phát sinh; lưu kết quả. |
| HR sửa ngày bắt đầu hoặc thay đổi vai trò | Đánh giá lại approval, account status và role trước khi kích hoạt. |
| Không thể disable account khi Leaver | Cảnh báo mức rủi ro, owner xử lý, áp dụng biện pháp chặn đường truy cập khả thi và kiểm chứng sau khắc phục. |

Một hệ thống SaaS và service desk không tự có **transaction nguyên tử chung**. Nếu bước thứ hai lỗi, không thể mặc nhiên rollback mọi thay đổi bước một. Quy trình phải có trạng thái riêng cho thao tác đã hoàn thành, trạng thái thực tế và **compensating action** được kiểm soát, như disable account vừa tạo nếu yêu cầu không còn hợp lệ.

### 9.3. Pseudocode minh họa một workflow thủ công

~~~text
requestManualAccount(identity, target, requestedAccess):
    require verifiedAuthoritativeIdentity(identity)
    require allowedRelationshipAtEffectiveTime(identity)
    require approvedPolicyAndSoD(requestedAccess)

    task = createIdempotentTicket(identity, target, requestedAccess)
    existing = lookupTargetAccountAndBinding(identity, target)

    if existing is CONFLICTING:
        return NEEDS_IDENTITY_REVIEW

    if existing is VERIFIED:
        task.action = REVIEW_OR_UPDATE_ACCOUNT
    else:
        task.action = CREATE_ACCOUNT

    assignAuthorizedOperator(task)
    return READY_FOR_OPERATOR

operatorProcess(task):
    assert task.approvalStillValid
    assert targetAndIdentityMatch(task)
    assert noOtherOperatorOwnsActiveTask(task)

    account = findExistingTargetAccount(task)
    if account is absent:
        account = createAccountByApprovedRunbook(task)

    applyApprovedStatusAndEntitlements(account, task)
    recordOperatorAndTargetAccountId(task, account)
    markTask(PENDING_VERIFICATION)

verifyAndClose(task):
    actual = independentlyReadTargetState(task.targetAccountId)
    desired = approvedDesiredStateAtEffectiveTime(task)

    if actual is not equivalent to desired:
        assignRemediationOwner(task, actual)
        return NEEDS_REMEDIATION

    persistAccountBindingAndEvidence(task, actual)
    enrollAccountIntoJMLAndAccessReview(task)
    return VERIFIED
~~~

Đây là **pseudocode mô tả ý tưởng**, không phải một chương trình có thể chạy nguyên trạng. Triển khai cần kiểm soát lỗi nghiệp vụ, quyền tác vụ, trạng thái bất đồng bộ, đồng thời và cơ chế xác minh của từng ứng dụng. Quy trình có thể dùng hệ thống ticket và UI, nhưng phải bảo đảm các bước quan trọng đều có **owner và bằng chứng**.

## 10. Đối soát và kiểm toán các account tạo thủ công

### 10.1. Inventory là cầu nối từ tạo đến thu hồi

Account được tạo trực tiếp trong UI mà không ghi về IAM/inventory dễ biến thành **orphaned account**. Một bản ghi kiểm kê nên có:

- IAM identity ID hoặc workload identity ID; target application/tenant/account ID.
- Account owner, sponsor, loại account, trạng thái active/disabled.
- Role/group/entitlement được phép, phạm vi dữ liệu và ngày hết hạn khi có.
- Request/approval reference, người thực hiện, thời điểm và nguồn bằng chứng.
- Đường đăng nhập: SSO hay local, MFA/credential owner theo mức cần thiết.
- Ngày review tiếp theo và cách tạo task khi Mover/Leaver.

**Access review** xác định quyền hiện tại còn cần hay không. **Reconciliation** so sánh **desired state** với **actual state** để tìm thiếu/thừa quyền hoặc account ngoài quản lý. Một account tạo đúng hôm nay vẫn có thể trở thành quyền tồn dư sau khi người dùng chuyển vai trò.

### 10.2. Các nguồn sai lệch thường gặp

| Desired state | Actual state | Phát hiện |
| --- | --- | --- |
| Nhân viên chỉ được đọc ERP theo bộ phận. | Admin ERP gán thêm role ghi toàn cục. | Entitlement vượt chính sách; cần điều tra và sửa. |
| Nhà thầu đã hết hợp đồng. | Account local vẫn active. | Leaver/expiry chưa được thực hiện hoặc kiểm chứng. |
| Nhân viên đã chuyển vai trò. | Group/role của nhóm cũ vẫn còn. | Mover thiếu bước gỡ entitlement hoặc bị lỗi. |
| Một identity có một account được duyệt. | Ứng dụng có hai account trùng người. | Account correlation hoặc tạo trùng có lỗi. |
| Workload đã ngừng hoạt động. | Service account vẫn có credential và quyền. | Non-human identity chưa được deprovision. |

Không nên “sửa” tự động một sai lệch nếu IAM chưa đủ dữ liệu hoặc nếu có sự kiện khẩn cấp/ngoại lệ cần xác minh. Tuy nhiên, mọi sai lệch phải có **người nhận xử lý, hạn đánh giá và kết quả được kiểm tra**, đặc biệt khi liên quan đặc quyền.

### 10.3. Đo chất lượng quy trình

Một số chỉ số tham khảo:

| Chỉ số | Cách tính / diễn giải |
| --- | --- |
| **Verified manual provisioning rate** | Ticket tạo account thủ công có readback đầy đủ ÷ ticket đã hoàn tất trong phạm vi. |
| **Approval coverage** | Account/entitlement yêu cầu phê duyệt có bằng chứng hợp lệ ÷ tổng account/entitlement thuộc diện đó. |
| **Unlinked account rate** | Account không có binding/owner hợp lệ ÷ tổng account được kiểm kê. |
| **Manual provisioning latency** | Thời gian từ mốc yêu cầu hợp lệ đến khi account/quyền được xác minh. |
| **Manual deprovisioning latency** | Thời gian từ mốc phải chặn truy cập đến lúc actual access được xác minh đã bị chặn. |
| **Rework / correction rate** | Ticket phải sửa account/role do thao tác sai hoặc dữ liệu thiếu ÷ ticket đã xử lý. |
| **Overdue review / expiry tasks** | Số account thủ công quá hạn review hoặc thu hồi theo policy. |

Chỉ số phải ghi rõ mẫu số, loại ứng dụng và mức rủi ro. Một account quản trị production chưa thu hồi có thể nghiêm trọng hơn hàng chục account ít quyền đã được xử lý đúng.

## 11. Tình huống thực tế: tạo user trên ERP không hỗ trợ SCIM

**Bối cảnh:** Ngân bắt đầu làm nhân viên phân tích tài chính ngày 01/10. HRIS có identity ID **person-2048** và trạng thái đã được xác nhận. Công ty dùng IdP cho SSO nhưng ERP legacy không hỗ trợ SCIM. Người dùng ERP phải do application admin tạo trong UI. Role đúng theo công việc là **FINANCE_REPORT_READER** chỉ đọc báo cáo thuộc đơn vị được phân công.

| Bước | Diễn biến | Trạng thái/bằng chứng cần có |
| --- | --- | --- |
| 1. HR xác nhận | Quan hệ lao động và ngày vào làm được nguồn chuẩn ghi nhận. | HR event, identity ID, effective time. |
| 2. IAM quyết định | Tính baseline access; role reader được phép theo chính sách, không có quyền duyệt thanh toán. | Policy ID/version, scope, yêu cầu approval nếu có. |
| 3. Chuyển task | Ticket gửi application admin, ghi rõ tenant production và mốc kích hoạt. | Request ID, assignee, policy, dữ liệu tối thiểu. |
| 4. Operator thao tác | Tra account trước, tạo user nếu chưa có, liên kết SSO đúng subject và gán role reader. | Target account ID, operator, thời điểm, admin audit log. |
| 5. Kiểm chứng | Đọc lại trạng thái, role, scope; xác minh không có role mặc định quá rộng. | Verified actual state, reviewer, thời điểm. |
| 6. Đăng ký vòng đời | Lưu account binding và owner để hỗ trợ Mover/Leaver. | Inventory record, review/expiry rule. |

**Biến thể Mover:** ba tháng sau Ngân chuyển sang đội vận hành, ERP không còn cần thiết. IAM tạo task **remove role/disable account** (tùy chính sách và nhu cầu giữ dữ liệu), operator thực hiện, reviewer đối soát. Việc Ngân vẫn đăng nhập được IdP không cho phép giữ lại quyền ERP.

**Biến thể Leaver:** HR xác nhận Ngân nghỉ việc. Tắt IdP account là một phần, nhưng admin ERP còn phải kiểm tra account local, session/token và mọi quyền còn hoạt động. Nếu ERP offline hoặc UI quản trị lỗi, ticket phải giữ trạng thái chưa hoàn tất, có owner và biện pháp giảm rủi ro phù hợp cho đến khi xác minh được quyền đã chặn.

### 11.1. Một sơ đồ bản ghi xuyên suốt

~~~text
HRIS event JOINER-2026-1284
  -> IAM identity person-2048
     -> Approved access request IAM-REQ-4821
        -> Manual operator app-admin-29
           -> ERP account erp-user-90018
              -> Entitlement FINANCE_REPORT_READER
              -> Verification ERP-AUDIT-1184
                 -> Account inventory / access review / JML follow-up
~~~

Mỗi mũi tên cần có khóa hoặc tham chiếu đủ để truy vết, không chỉ một câu ghi chú “đã cấp”. Khi role đổi hoặc quan hệ chấm dứt, hệ thống cần đi ngược theo binding để tìm đúng account cần sửa/khóa.

## 12. Những lỗi thiết kế dễ mắc

| Lỗi | Hậu quả | Cách kiểm soát |
| --- | --- | --- |
| Tạo account theo lời nhắn mà không kiểm tra request/approval. | Cấp quyền ngoài thẩm quyền, khó giải trình. | Bắt buộc ticket và chính sách duyệt đúng scope. |
| Lấy email làm khóa duy nhất, không lưu target account ID. | Đổi email hoặc trùng tên gây cập nhật nhầm. | Liên kết identity với ID account thực tế ở target. |
| Operator tự chọn role mạnh để tránh thiếu quyền. | Vi phạm least privilege và có thể SoD conflict. | Role mapping được owner duyệt, từ chối nâng quyền không có approval. |
| Không kiểm tra role mặc định sau khi tạo. | Account có quyền ngoài mong muốn. | Readback status, group, role và data scope. |
| Gửi mật khẩu tạm, API key hoặc token trong ticket. | Lộ credential và mất kiểm soát truy cập. | Kênh kích hoạt an toàn, MFA, vault/secret management khi thích hợp. |
| Account tồn tại nhưng không ghi về IAM inventory. | Không được Mover/Leaver tìm thấy để thu hồi. | Bắt buộc binding và ownership trước khi đóng yêu cầu. |
| Tạo lại khi UI mất phản hồi mà không kiểm tra target. | Account trùng, permission phân tán. | Kiểm tra target, ticket idempotency, owner độc nhất cho task. |
| Chỉ tắt IdP rồi xem ERP đã khóa. | Local login hoặc phiên ứng dụng vẫn có thể hoạt động. | Deprovision trực tiếp theo target, kiểm tra session/token. |
| Nhà thầu không có expiration owner. | Account tồn tại sau ngày hết hạn hợp đồng. | Sponsor, expiration task, alert và review. |
| Xóa toàn bộ service account khi nhân viên owner chuyển vai trò. | Workload đang chạy bị gián đoạn. | Tách owner con người khỏi workload lifecycle, bàn giao và xoay vòng secret khi cần. |
| Ticket hoàn tất ngay sau khi bấm Save. | Thực tế thiếu role, sai scope hoặc chưa kích hoạt MFA. | Readback và tiêu chí verified completion. |
| Không có owner cho lỗi tạo/khóa account. | Quyền truy cập tồn dư kéo dài. | Phân công, deadline, retry/khắc phục và đối soát. |

## 13. Checklist vận hành và bài tập

### 13.1. Checklist cho người thực hiện và người kiểm tra

- [ ] Yêu cầu có identity ID và nguồn có thẩm quyền, loại quan hệ và ngày hiệu lực hợp lệ.
- [ ] Ứng dụng, tenant, môi trường và loại account được xác định chính xác.
- [ ] Đã tra cứu account cũ/trùng; mọi collision đều được giải quyết có bằng chứng.
- [ ] Role, entitlement, scope, thời hạn và phê duyệt đúng với chính sách; SoD được xét khi cần.
- [ ] Operator có quyền thực hiện; quyền yêu cầu/phê duyệt/thao tác được phân tách theo rủi ro.
- [ ] Đã tạo/liên kết account đúng identity, áp dụng trạng thái kích hoạt theo thời điểm hiệu lực.
- [ ] SSO hoặc local authentication, MFA và đường cấp credential được thiết lập an toàn.
- [ ] Không có role/default group/direct grant ngoài phạm vi đã duyệt.
- [ ] Đã đọc lại account ID, trạng thái, entitlement và scope từ ứng dụng đích.
- [ ] Đã lưu bằng chứng, người thao tác/người kiểm tra, thời điểm, approval và target account binding.
- [ ] Account đã được đưa vào inventory và workflow Mover/Leaver/access review.
- [ ] Mọi lỗi hoặc ngoại lệ chưa giải quyết có owner và trạng thái theo dõi, chưa bị báo hoàn tất.

### 13.2. Tình huống A — Trùng tài khoản khi tạo

Ticket yêu cầu tạo ERP account cho nhân viên có email mới, nhưng hệ thống đã có một account cùng họ tên và email cũ. Làm thế nào để phân biệt đây là account của cùng người, account của người khác hay một account mồ côi? Khi nào được liên kết thay vì tạo mới?

### 13.3. Tình huống B — SSO đã có nhưng ứng dụng chưa có user

Người dùng đăng nhập IdP thành công qua SAML, song ERP báo “user not found”. Hãy phân biệt vấn đề **AuthN/SSO** với **manual provisioning/account mapping**, và liệt kê các thông tin operator cần kiểm chứng mà không tiết lộ credential.

### 13.4. Tình huống C — Role admin không nằm trong approval

Application admin thấy role “Reader” không thể xuất báo cáo theo mong muốn; role “Administrator” thì dùng được. Có được tự nâng quyền không? Hãy đề xuất cách ghi thiếu permission, xác minh scope thực sự cần và xin phê duyệt theo least privilege/SoD.

### 13.5. Tình huống D — Tạo account cho nhà thầu

Một nhà thầu chỉ tham gia dự án hai tuần, ứng dụng không hỗ trợ tự hết hạn user. Hãy thiết kế ticket tạo, task thu hồi, owner, review và cách đối soát để không còn quyền truy cập sau hợp đồng.

### 13.6. Tình huống E — ERP ngừng phản hồi sau khi bấm Save

Operator bấm “Save User”, trình duyệt báo timeout. Ticket chưa có target account ID. Hãy mô tả các bước kiểm tra target trước khi thử lại, cách xử lý account đã tạo một phần và bằng chứng để không phát sinh duplicate account.

**Điểm cần ghi nhớ:** Tạo account thủ công là một **cách thực thi account provisioning**, vẫn phải tuân theo chính sách IAM về **xác minh danh tính, phê duyệt, quyền tối thiểu, bảo vệ xác thực, kiểm toán và trách nhiệm giải trình**. Thành công kỹ thuật chỉ được xác nhận sau khi **đọc lại trạng thái account và entitlement tại hệ thống đích**, lưu binding với identity, đưa account vào kiểm kê và bảo đảm có đường **Mover/Leaver để cập nhật, thu hồi và đối soát quyền** trong suốt vòng đời.
