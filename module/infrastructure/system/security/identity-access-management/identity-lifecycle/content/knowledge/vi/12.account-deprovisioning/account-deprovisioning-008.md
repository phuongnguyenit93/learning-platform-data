# Khắc phục account không còn owner: nhận diện, quy trách nhiệm và thu hồi an toàn trong IAM

**Account không còn owner (ownerless account)** là tài khoản tồn tại trong một hệ thống nhưng tổ chức **không xác định được người hoặc đơn vị đang chịu trách nhiệm hợp lệ** cho việc duy trì, cấp quyền, giám sát và kết thúc vòng đời tài khoản đó. Đây là vấn đề trọng yếu của **account deprovisioning**: tài khoản thiếu chủ sở hữu rất dễ tiếp tục hoạt động sau khi nhân viên nghỉ việc, nhà thầu hết hợp đồng, ứng dụng ngừng vận hành hoặc nhóm dự án giải thể.

Tuy nhiên, **không phải cứ thiếu trường `ownerId` là phải xóa tài khoản ngay**. Một tài khoản người dùng có thể vẫn được liên kết chính xác với nhân viên đang làm việc nhưng bản ghi quản lý ứng dụng bị thiếu owner; một service account có thể đang chạy quy trình sản xuất quan trọng dù người tạo đã rời tổ chức. Ngược lại, một tài khoản được gán owner trên giấy tờ vẫn có thể là **quyền truy cập tồn dư** nếu owner không còn có thẩm quyền hoặc căn cứ sử dụng không còn hiệu lực.

Bài học thuộc chương **Account deprovisioning** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung đặt việc khắc phục account không còn owner trong toàn bộ **Joiner–Mover–Leaver (JML)**, kết nối dữ liệu từ nguồn nhân sự/hợp đồng, **IdP, SSO, SCIM, RBAC/ABAC**, danh tính người và tài khoản dịch vụ, hoạt động rà soát và bằng chứng kiểm toán.

**Thông điệp trung tâm:** Mục tiêu không phải “điền cho đủ cột owner”, mà là **chứng minh tài khoản có chủ thể và mục đích hợp lệ, có người chịu trách nhiệm thực sự, quyền vừa đủ và cơ chế thu hồi khi mất điều kiện**. Nếu không thể chứng minh, phải giảm rủi ro và xử lý theo chính sách, đồng thời bảo đảm không vô tình phá vỡ dịch vụ thiết yếu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **ownerless account**, **orphan account**, account không được liên kết danh tính và account hợp lệ nhưng metadata thiếu.
2. Xác định loại chủ thể, nguồn cấp và các bên có trách nhiệm đối với tài khoản người, tài khoản máy, tài khoản khẩn cấp và tài khoản liên kết từ đối tác.
3. Phát hiện account nghi vấn thông qua đối soát giữa **HR/VMS, IAM, IdP, ứng dụng đích, danh mục dịch vụ, vault và log**, thay vì chỉ xem một trường dữ liệu.
4. Đánh giá rủi ro, phụ thuộc vận hành và lựa chọn giữa **xác minh lại owner, chuyển giao ownership, giảm quyền, tạm khóa, thu hồi credential hoặc deprovision**.
5. Thiết kế quy trình khắc phục có **người chịu trách nhiệm, thời hạn, phê duyệt, biện pháp giảm thiểu và kết quả đọc lại**.
6. Phân tích lỗi vòng đời khiến account không còn owner và đề xuất cơ chế phòng ngừa ngay từ **Joiner, Mover, Leaver**.
7. Đánh giá hoàn tất bằng quyền hiệu dụng, trạng thái phiên/token, kết quả ở ứng dụng đích và bằng chứng kiểm toán.

## 2. Account, chủ thể và owner là các khái niệm khác nhau

Để xử lý chính xác, cần tách bốn thực thể:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Subject / identity** | Ai hoặc workload nào đang được tài khoản đại diện? | Nhân viên Minh; job đồng bộ hóa đơn |
| **Account** | Bản ghi truy cập ở hệ thống nào? | User trong IdP, Git, cloud, cơ sở dữ liệu |
| **Owner** | Ai chịu trách nhiệm rằng tài khoản vẫn cần thiết và được quản trị? | Quản lý ứng dụng, sponsor, owner dịch vụ |
| **Entitlement** | Account có thể làm gì, với tài nguyên nào? | Đọc dữ liệu dự án A; chạy job trên staging |

Một người có thể có nhiều account. Một ứng dụng có thể có nhiều service account. Owner có thể là **cá nhân được chỉ định hoặc vai trò/đơn vị có cơ chế chịu trách nhiệm rõ ràng**, tùy chính sách, nhưng phải có người có thẩm quyền phản hồi và phê duyệt. Không nên ghi `owner=IT` nếu “IT” không có nhóm nhận việc, quy trình chuyển giao và người phê duyệt rõ ràng.

### 2.1. Các dạng “không còn owner” dễ bị nhầm

| Dạng | Mô tả | Ví dụ | Hướng điều tra |
|---|---|---|---|
| **Owner metadata missing** | Trường owner rỗng/không đồng bộ | Account ứng dụng có người dùng hợp lệ nhưng catalog trống owner | Kiểm tra mapping, nguồn metadata |
| **Owner departed** | Owner đã rời tổ chức hoặc hết vai trò | Người quản lý service account nghỉ việc | Tìm successor, rà soát credential và quyền |
| **Owner unresponsive** | Có tên owner nhưng không thể xác nhận nhu cầu | Không ai nhận trách nhiệm cho job cũ | Escalate và đánh giá phụ thuộc |
| **Identity correlation missing** | Chưa ánh xạ account với subject chính xác | Local user không có `personId` hay external ID | Resolution, đối soát và xác minh |
| **Orphan account** | Không còn chủ thể/quan hệ hay mục đích hợp lệ được xác nhận | Account của contractor đã hết hợp đồng | Xem xét thu hồi theo chính sách |
| **Stale entitlement** | Account còn hợp lệ nhưng một quyền không còn căn cứ | Nhân viên chuyển nhóm vẫn giữ role cũ | Thu hồi quyền không cần xóa account |
| **Unowned workload credential** | Bí mật/API key vẫn hoạt động nhưng không rõ ai quản lý | Key của pipeline sau khi dự án đóng | Truy vết workload, owner và vòng đời secret |

**Không đánh đồng:** Thiếu owner là **tín hiệu rủi ro**; orphan account là một kết luận có căn cứ về **thiếu chủ thể/mục đích hoặc quan hệ hợp lệ**. Cần xác minh trước khi đưa ra quyết định cuối cùng.

## 3. Vì sao account bị mất owner?

Các tình huống lặp lại trong vòng đời IAM gồm:

- **Joiner:** Tài khoản được tạo thủ công mà không ghi identity, sponsor hoặc service owner.
- **Mover:** Nhân viên đổi bộ phận; tài khoản máy vẫn gắn với quản lý cũ, owner mới không được chuyển giao.
- **Leaver:** Chủ tài khoản hoặc sponsor rời tổ chức nhưng các account thứ cấp không đi qua quy trình thu hồi.
- **Đổi nhà thầu/đối tác:** Hợp đồng hết hiệu lực, danh tính liên kết còn tồn tại hoặc account local chưa được kiểm kê.
- **Chuyển hệ thống/migration:** Account cũ được chuyển sang hệ thống mới nhưng mất `externalId`, owner hoặc nguồn cấp quyền.
- **Ứng dụng ngừng hoạt động:** Dịch vụ tắt một phần, tài khoản cloud, API key hoặc backup automation vẫn còn.
- **Tích hợp không hoàn chỉnh:** SCIM đồng bộ user ở ứng dụng A nhưng không hỗ trợ quản lý account local ở ứng dụng B.
- **Quyền dùng chung:** Nhiều người dùng chung credential, không thể chứng minh người đã thao tác hoặc ai chịu trách nhiệm.
- **Sai lệch danh mục:** CMDB, IAM và vault dùng các tên khác nhau cho cùng một service hoặc owner.

Một account có thể đồng thời gặp nhiều vấn đề: ví dụ owner đã nghỉ, quyền admin còn rộng và token không hết hạn. Khi đó không thể chỉ sửa metadata mà phải đánh giá **toàn bộ khả năng truy cập thực tế**.

## 4. Chủ sở hữu hợp lệ của từng loại account

Không áp cùng một quy tắc owner cho mọi account. Hãy phân loại trước.

| Loại account | Owner và nguồn có thẩm quyền thường gặp | Điều kiện quan trọng |
|---|---|---|
| **Employee account** | Danh tính nhân viên từ HR; quản lý và application owner theo trách nhiệm | Quan hệ làm việc còn hiệu lực, quyền theo vai trò |
| **Contractor account** | Danh tính cá nhân, hợp đồng, sponsor và chủ ứng dụng | Có thời hạn, sponsor hợp lệ, phạm vi dự án |
| **Partner/federated account** | Tổ chức đối tác và sponsor nội bộ, hệ thống nhận quyền | Tin cậy federation, mapping và thời hạn truy cập nội bộ |
| **Service account** | Service owner, team vận hành và danh mục workload | Mục đích máy, owner kỹ thuật, credential/quyền |
| **Break-glass account** | Đơn vị an ninh/vận hành có thẩm quyền được chỉ định | Quy trình sử dụng khẩn cấp, bảo vệ credential, kiểm tra định kỳ |
| **Shared/legacy account** | Owner ứng dụng tạm chịu trách nhiệm và kế hoạch loại bỏ/kiểm soát | Cần đánh giá khả năng truy vết và thay thế bằng account riêng |
| **Privileged admin account** | Chủ thể người hoặc owner hệ thống theo chính sách PAM | Phạm vi đặc quyền, phê duyệt, phiên và kiểm toán |
| **Automation/bot account** | Owner của workflow và người quản trị credential | Không nhầm bot với người nhân viên tạo ra bot |

### 4.1. Owner không phải là “người tạo account”

Nhân viên DevOps tạo service account `svc_invoice_sync` để chạy job. Sau khi nhân viên đó chuyển việc, **service account vẫn có thể cần cho hệ thống**, nhưng owner phải gắn với **dịch vụ và đơn vị chịu trách nhiệm hiện hành**, không phải gắn vĩnh viễn vào người thực hiện lệnh CREATE.

### 4.2. Owner khác người sử dụng

Một external contractor sử dụng account với sponsor nội bộ. Người sử dụng là contractor, còn sponsor là người chịu trách nhiệm nghiệp vụ trong tổ chức. Hai bên có trách nhiệm khác nhau. Chuyển sponsor không nhất thiết là cấp một danh tính mới; phải xác minh quan hệ và quyền.

### 4.3. Tài khoản khẩn cấp phải được quản trị đặc biệt

Break-glass account có thể không gắn với một người dùng thường ngày, nhưng **không được ownerless về mặt quản trị**. Cần một nhóm/role có thẩm quyền với người phụ trách cụ thể, quy trình sử dụng và kiểm tra credential, nhật ký và cảnh báo. Không tự xóa account này chỉ vì không thấy employee ID; phải đánh giá yêu cầu sẵn sàng trong tình huống khẩn cấp.

## 5. Phát hiện account không còn owner

Một cơ chế phát hiện đáng tin cậy cần **đối soát nhiều nguồn** và ghi nhận độ chắc chắn, thay vì quét một cột rỗng rồi tự động vô hiệu hóa tất cả.

### 5.1. Các nguồn đối chiếu

| Nguồn | Thông tin hữu ích | Giới hạn cần nhớ |
|---|---|---|
| **HR** | Trạng thái nhân viên, manager, thay đổi Mover/Leaver | Không luôn bao phủ contractor hay workload |
| **VMS/hợp đồng** | Sponsor, engagement, ngày hết hạn contractor | Không chứng minh mọi account ứng dụng đã được thu hồi |
| **IAM/IGA** | Identity–account mapping, role, request, certification | Có thể thiếu account cấp ngoài luồng |
| **IdP/SSO** | Account, nhóm, danh tính liên kết, trạng thái đăng nhập | Không bao phủ đầy đủ tài khoản local và token ứng dụng |
| **Ứng dụng đích / SCIM/API** | User thực tế, role/nhóm, trạng thái, external ID | Khả năng connector và trạng thái có thể khác nhau |
| **Cloud / Git / database** | Local accounts, service principals, keys, ACL | Cần phân biệt machine identity, admin và user |
| **CMDB / service catalog** | Owner dịch vụ, hệ thống phụ thuộc, trạng thái vận hành | Dữ liệu catalog có thể lỗi thời |
| **Secret manager / vault / PAM** | Credential, owner, rotation, quyền truy cập bí mật | Có thể không biết bản sao secret đã bị lấy ra |
| **Access logs** | Sử dụng gần nhất, địa chỉ nguồn, dịch vụ gọi tới | Ít sử dụng không chứng minh account không cần thiết |

### 5.2. Các quy tắc phát hiện

Có thể dùng các điều kiện gợi ý:

1. `ownerId` trống, owner không tồn tại hoặc owner ở trạng thái Leaver.
2. Account không ánh xạ được tới `personId`, engagement hoặc workload ID hợp lệ.
3. Account được tạo thủ công nhưng không có request, sponsor hoặc service owner.
4. Account vẫn active sau khi quan hệ làm việc và thời gian được phép đã kết thúc.
5. Service account không có chủ sở hữu hiện hành hoặc dịch vụ đã ngừng.
6. Quyền đặc quyền vẫn hoạt động nhưng không có owner/nhật ký phê duyệt.
7. Account và token vẫn tồn tại dù application catalog báo đã ngừng sử dụng.
8. Owner được ghi là nhóm chung không có người nhận trách nhiệm và quy trình rà soát.

Những quy tắc này tạo **danh sách cần điều tra**; chưa đủ để xác định tất cả account phải bị xóa. Cần xác minh **đúng account ID, hệ thống đích và nguồn dữ liệu** trước khi áp dụng hành động gây gián đoạn.

### 5.3. Ví dụ báo cáo phát hiện

~~~text
Account inventory snapshot:
------------------------------------------------------------
target        accountId        owner        trạng thái
------------------------------------------------------------
CRM           CRM-2028         (null)       ACTIVE
Git           git-binh         U-1040       ACTIVE
Cloud         svc-reporting    U-0912*      ACTIVE
VPN           vpn-external-7   sponsor-X*   ACTIVE

* U-0912: đã rời tổ chức
* sponsor-X: engagement đã hết hạn

Kết quả:
- CRM-2028: cần kiểm tra identity mapping/owner metadata
- git-binh: kiểm tra role và engagement, chưa đủ căn cứ orphan
- svc-reporting: cần tìm service owner thay thế, đánh giá secret
- vpn-external-7: ưu tiên xác minh hết hạn và thu hồi quyền
~~~

Quy tắc đánh giá nên dựa trên **định danh kỹ thuật ổn định** (`accountId`, `personId`, workload ID) thay vì tên hiển thị hoặc email đơn thuần.

## 6. Phân loại rủi ro và ưu tiên xử lý

Không phải mọi ownerless account có rủi ro giống nhau. Nên xét **quyền hiệu dụng, tính phơi lộ, trạng thái identity, loại credential và ảnh hưởng nếu chặn account**.

| Yếu tố | Gợi ý đánh giá |
|---|---|
| **Đặc quyền** | Admin, production, khả năng tạo user/secret, truy cập dữ liệu nhạy cảm |
| **Khả năng truy cập từ ngoài** | Internet, VPN, federation, API endpoint công khai |
| **Trạng thái hợp đồng/người dùng** | Leaver, contractor hết hạn, sponsor không hợp lệ |
| **Loại credential** | Password chung, API key dài hạn, SSH key, token tự tạo |
| **Bằng chứng sử dụng** | Có hoạt động bất thường, lần dùng gần đây, nguồn request |
| **Khả năng phụ thuộc sản xuất** | Job tài chính, backup, CI/CD, dịch vụ khách hàng |
| **Khả năng thu hồi** | Có API/readback, chỉ thao tác thủ công, phiên không thể hủy tức thì |
| **Chất lượng owner và inventory** | Chưa rõ chủ thể, thiếu service mapping, không xác minh được nguồn |

Một account người dùng của contractor hết hạn vẫn có quyền admin vào hệ thống Internet-facing thường cần **ưu tiên bảo vệ và thu hồi sớm** theo chính sách. Một service account chạy tác vụ backup sản xuất nhưng mất owner cũng đáng ưu tiên, song **vô hiệu hóa vội** có thể làm mất khả năng khôi phục dữ liệu. Cần đồng thời **giảm rủi ro credential và xác minh phụ thuộc**, thay vì dùng một hành động duy nhất cho mọi trường hợp.

### Không dùng “không có log gần đây” làm quyết định xóa

Một job có thể chạy theo quý; break-glass account chỉ dùng khi sự cố; hệ thống có thể không ghi log đầy đủ. **Không thấy sử dụng** là tín hiệu hữu ích nhưng không chứng minh **không có phụ thuộc hoặc không cần nữa**. Đối chiếu với lịch chạy, dependency, owner dịch vụ và khả năng ghi log.

## 7. Quy trình khắc phục an toàn từ phát hiện đến đóng

~~~mermaid
flowchart TD
    A["Inventory / access review<br/>phát hiện account nghi vấn"] --> B["Lấy account ID, target,<br/>loại subject, quyền, log"]
    B --> C{"Identity / workload<br/>và nguồn hợp lệ xác định được?"}
    C -->|Chưa| D["Điều tra, phân loại rủi ro<br/>và kiểm tra phụ thuộc"]
    C -->|Có| E["Đối chiếu owner,<br/>engagement và mục đích"]
    D --> E
    E --> F{"Còn nhu cầu và owner<br/>có thẩm quyền xác nhận?"}
    F -->|Có| G["Chuyển/gán owner đúng quy trình<br/>rà soát lại quyền và hạn"]
    F -->|Không| H["Lập kế hoạch thu hồi<br/>và bảo vệ dịch vụ liên quan"]
    F -->|Không rõ| I["Escalate, giới hạn rủi ro<br/>và giữ trạng thái chờ"]
    I --> F
    G --> J["Thực thi qua IdP/SCIM/API/PAM<br/>hoặc quy trình có kiểm soát"]
    H --> J
    J --> K["Readback trạng thái account,<br/>entitlement, phiên, credential"]
    K --> L{"Tất cả điều kiện<br/>và bằng chứng đạt?"}
    L -->|Có| M["Lưu quyết định và audit<br/>đóng finding"]
    L -->|Chưa| N["Theo dõi lỗi/ngoại lệ<br/>owner và hạn xử lý"]
    N --> J
~~~

**Chú ý:** Nhánh `Không rõ` không được mặc định trở thành “giữ vô thời hạn”. Hạng mục phải có người chịu trách nhiệm điều tra, mốc rà soát và biện pháp giảm thiểu theo rủi ro.

### Bước 1 — Khóa phạm vi điều tra

Ghi rõ account ở hệ thống nào, account ID là gì, trạng thái hiện hành, nguồn quyền, loại account, bằng chứng owner hiện tại và lý do nghi vấn. Tránh sửa/xóa khi chưa biết chính xác **đối tượng nào đang bị tác động**.

### Bước 2 — Tìm lại chủ thể hoặc workload

- Với human account, đối chiếu mapping từ IdP, HR/VMS, request và account target.
- Với federated user, kiểm tra external subject ID và sponsor nội bộ; không suy luận từ email đối tác.
- Với service account, tra service catalog, cấu hình workload, pipeline, lịch job, dependency, vault và runbook.
- Với break-glass, đối chiếu chính sách tài khoản khẩn cấp và chủ trách nhiệm đặc biệt.

Nếu account đã được **tái sử dụng sai** hoặc xuất hiện mapping mâu thuẫn, chuyển xử lý điều tra. Không tự hợp nhất identity hoặc gán một account cho người mới chỉ vì username giống.

### Bước 3 — Xác định quyết định nghiệp vụ

Có ba hướng phổ biến:

1. **Giữ và sửa ownership:** Tài khoản còn cần, owner hợp lệ nhận trách nhiệm, quyền được rà soát.
2. **Giới hạn/tạm đình chỉ trong khi điều tra:** Chưa đủ dữ liệu, rủi ro cao hoặc cần ngăn lạm dụng nhưng chưa thể kết thúc toàn bộ account an toàn.
3. **Thu hồi/deprovision:** Không còn nhu cầu hoặc quan hệ hợp lệ, áp quy trình thu hồi theo mức độ khẩn cấp và phụ thuộc.

Một account có thể được giữ nhưng một số **entitlement quá rộng** phải bị thu hồi ngay. Quyết định owner và quyết định quyền là **hai bước riêng**.

### Bước 4 — Thực thi và kiểm chứng

Cập nhật owner, hạn và quyền qua hệ thống quản trị có thẩm quyền; đồng bộ khi cần và **đọc lại trạng thái ở đích**. Với deprovision, kiểm tra session/token, quyền trực tiếp, credential và các đường truy cập độc lập.

### Bước 5 — Lưu bằng chứng và phòng tái phát

Đóng finding khi quyết định đã thực thi và chứng minh được kết quả; đồng thời sửa nguyên nhân gốc như mapping SCIM thiếu, workflow không chuyển ownership hoặc service catalog không có owner kế nhiệm.

## 8. Ma trận quyết định khắc phục theo loại tài khoản

| Tình trạng | Hướng xử lý thường phù hợp | Điều kiện để quyết định |
|---|---|---|
| Account người dùng còn active, HR xác nhận đang làm việc, trường owner trống | Liên kết lại identity/manager và rà soát quyền | Chứng minh đúng person và căn cứ truy cập |
| Account của người đã nghỉ, không còn engagement hợp lệ | Disable/deprovision, thu hồi quyền và session/token | Xác minh account thuộc đúng người, theo chính sách |
| Contractor hết hợp đồng nhưng còn account local | Thu hồi hoặc đình chỉ theo mốc kết thúc, đối soát | Nguồn hợp đồng/sponsor và target |
| Service account còn chạy sản xuất, owner nghỉ việc | Bổ nhiệm owner mới, đánh giá quyền và credential, kế hoạch chuyển giao | Xác nhận workload, dependency, owner nhận trách nhiệm |
| Service account thuộc dự án đã ngừng, không có phụ thuộc xác nhận | Thu hồi credential/quyền và deprovision sau kiểm tra | Bằng chứng không còn nhu cầu và tác động được đánh giá |
| Break-glass không có employee ID | Xác nhận owner quản trị đặc biệt; kiểm tra kiểm soát và log | Chính sách tài khoản khẩn cấp |
| Shared admin account không truy vết cá nhân | Giới hạn rủi ro và lên kế hoạch thay thế bằng danh tính riêng | Phụ thuộc, khả năng quản trị/PAM |
| Account có owner được khai báo nhưng owner phủ nhận trách nhiệm | Escalate và kiểm tra lại nguồn, tạm kiểm soát theo rủi ro | Không tự coi owner là hợp lệ |
| Account còn entitlement cho dự án cũ, subject vẫn làm việc | Thu hồi phần quyền cũ, giữ account hợp lệ | Xác định grant provenance và nhiệm vụ mới |

## 9. Cách chuyển giao ownership đúng

Đối với account còn cần thiết, **chuyển ownership** là một giao dịch quản trị cần được xác nhận, không phải thao tác điền tên ngẫu nhiên vào trường metadata.

### 9.1. Tiêu chí chọn owner mới

- Có **thẩm quyền** đối với ứng dụng, dịch vụ hoặc nhiệm vụ sử dụng account.
- Có khả năng **xác nhận mục đích, phạm vi quyền, thời gian và người vận hành**.
- Chấp nhận trách nhiệm xử lý access review, sự cố, thay đổi credential và deprovision.
- Không vi phạm yêu cầu **phân tách nhiệm vụ (SoD)** hoặc quy tắc phê duyệt.
- Có cơ chế kế nhiệm khi người đó thay vai trò/rời tổ chức.

Với service account, owner nên liên hệ đến **dịch vụ đang hoạt động** và nhóm có năng lực vận hành, không chỉ người trực tiếp tạo script. Với contractor, sponsor mới cần được xác nhận từ quy trình hợp đồng/dự án, không dựa vào lựa chọn tùy ý của người dùng.

### 9.2. Các bước chuyển giao

1. Xác nhận account ID, loại account và tài nguyên mà account đang truy cập.
2. Thu thập căn cứ còn cần thiết, thời hạn và dependency quan trọng.
3. Xác định owner mới từ nguồn và quy trình thẩm quyền.
4. Owner mới **chấp nhận trách nhiệm**; phê duyệt bổ sung nếu chính sách yêu cầu.
5. Cập nhật owner tại **nguồn dữ liệu chuẩn**, sau đó đồng bộ sang IAM, catalog/vault nếu phù hợp.
6. Rà soát và giảm quyền vượt nhu cầu; xử lý secret, mật khẩu, certificate và token theo rủi ro.
7. Kiểm tra owner hiển thị đúng tại các hệ thống cần thiết và hoàn tất hành động liên quan.
8. Lên lịch rà soát hoặc expiry; lưu bằng chứng quyết định.

**Đừng coi chuyển owner là “đóng xong”.** Nếu account vẫn có quyền admin không còn cần thiết, chứa secret bị lộ hoặc không thể xác định workload, vẫn phải xử lý các vấn đề đó.

## 10. Khắc phục service account không còn owner

Service account là trường hợp **rủi ro cao lẫn tác động vận hành cao**. Một account thiếu owner có thể đang dùng để sao lưu, đẩy dữ liệu, chạy CI/CD, đọc secret hoặc gọi API sản xuất. Xóa/vô hiệu hóa khi chưa khảo sát có thể dừng dịch vụ.

### 10.1. Điều tra dependency

Cần xác định:

- Workload, container, VM, pipeline hoặc job nào đang sử dụng account?
- Tài khoản gọi tới hệ thống/tài nguyên nào và bằng giao thức gì?
- Có lịch chạy hiếm, batch cuối tháng hoặc quy trình khôi phục khẩn cấp không?
- Credential được lưu ở đâu? Vault, secret manager, file cấu hình hay hệ thống triển khai?
- Ai có thể xem, sao chép, cấp lại hoặc luân chuyển credential?
- Có account thay thế hoặc cơ chế workload identity an toàn hơn được nền tảng hỗ trợ không?
- Quyền hiện hành có rộng hơn mục đích hay không?

Dữ liệu log chỉ hỗ trợ phân tích; **thiếu log không chứng minh tài khoản an toàn để xóa**.

### 10.2. Thứ tự khắc phục thực tế

Một cách tiếp cận có kiểm soát:

1. Gán **owner điều tra** và đánh giá rủi ro ngay khi phát hiện.
2. Xác nhận hệ thống phụ thuộc, mục đích nghiệp vụ và owner vận hành tương lai.
3. Giảm các quyền không cần thiết nếu có thể mà không làm gián đoạn chức năng hợp lệ.
4. Chuyển ownership, tài liệu và quy trình quản lý credential cho người phụ trách.
5. Đánh giá khả năng secret cũ bị người đã rời tổ chức giữ bản sao; **rotate/revoke** theo mức rủi ro và kế hoạch không làm gián đoạn.
6. Nếu tài khoản không còn cần, lên lịch vô hiệu hóa/thu hồi theo thay đổi được phê duyệt rồi kiểm tra ứng dụng liên quan.
7. Readback account, quyền, secret/version, trạng thái job và bằng chứng kiểm toán.

**Ưu tiên kỹ thuật khi phù hợp:** Workload identity hoặc credential ngắn hạn, quyền tối thiểu theo môi trường, rotation có kiểm soát, tách quyền quản trị secret khỏi quyền dùng ứng dụng.

### 10.3. Tài khoản máy không trở thành tài khoản người

Không gắn `personId` của nhân viên mới làm “chủ thể” của service account chỉ để có owner. Cần tách **machine subject/workload ID**, **owner chịu trách nhiệm** và **người có quyền quản trị**. Những mối liên kết này có vòng đời khác nhau.

## 11. IdP, SSO, SCIM và account local: vì sao không thể chỉ sửa một chỗ?

Một account không còn owner có thể xuất hiện tại IdP nhưng **không có trong danh mục IAM**, hoặc ngược lại, chỉ tồn tại cục bộ ở một ứng dụng.

~~~mermaid
flowchart LR
    H["HR / VMS / nguồn engagement"] --> I["IAM / IGA<br/>Identity + account mapping"]
    C["Service catalog / CMDB<br/>Workload + owner"] --> I
    I --> D["IdP / SSO<br/>Account + nhóm"]
    I --> S["SCIM / API / quy trình thay thế"]
    D --> A["Ứng dụng và dữ liệu<br/>Account local + entitlement"]
    S --> A
    A --> R["Readback & reconciliation<br/>Trạng thái thực tế"]
    R --> I
    I --> V["Audit / review<br/>Owner, quyết định, expiry"]
~~~

Các khả năng và giới hạn:

| Thành phần | Hỗ trợ gì? | Không thể mặc nhiên bảo đảm |
|---|---|---|
| **IdP** | Xác thực, account, nhóm, thuộc tính | Không bao phủ mọi account và credential tại ứng dụng |
| **SSO** | Dùng phiên nhận dạng đáng tin cậy giữa ứng dụng | Không tự tạo owner hoặc thu hồi mọi session |
| **SCIM** | Đồng bộ user/group khi ứng dụng hỗ trợ | Không luôn bao phủ local admin, API key, direct ACL, session |
| **RBAC** | Gắn quyền với vai trò | Không tự chứng minh vai trò còn có mục đích hợp lệ |
| **ABAC** | Kiểm tra thuộc tính và ngữ cảnh | Thuộc tính sai/owner lỗi thời có thể gây quyết định sai |
| **PAM / vault** | Quản lý đặc quyền, secret, phiên | Không thay thế kiểm kê workload và quyết định owner |
| **Ứng dụng đích** | Quyền hiệu dụng và trạng thái user thực tế | Có thể có tài khoản/permission ngoài IAM |

### 11.1. Trường owner không phải thuộc tính chuẩn ở mọi hệ thống

Nhiều ứng dụng không có trường owner tùy ý hoặc không hỗ trợ đồng bộ metadata owner qua SCIM. Khi đó, **nguồn quản lý ownership** có thể nằm ở IAM/IGA hoặc catalog, và được liên kết với target account bằng ID ổn định. Không ép trường không được hỗ trợ vào một mapping tùy tiện khiến hệ thống tự động mất dữ liệu.

### 11.2. Deprovision thực tế

Nếu account cần thu hồi:

1. Xác định đúng account đích từ mapping đã được kiểm chứng.
2. Gửi lệnh disable/delete hoặc revoke theo API và chính sách của hệ thống.
3. Kiểm tra group, role, direct grant, token, khóa và phiên liên quan.
4. Đọc lại trạng thái tại ứng dụng, không chỉ kiểm tra yêu cầu đã gửi.
5. Lưu kết quả và xử lý lỗi một phần.

**Disable không đồng nghĩa xóa dữ liệu**, và **xóa user không đồng nghĩa xóa mọi credential độc lập**. Giữ hay xóa hồ sơ phải theo chính sách lưu giữ và nghĩa vụ nghiệp vụ.

## 12. Phân quyền và kiểm toán sau khi tìm thấy owner

Một account được chuyển ownership nhưng vẫn có quyền vượt mục đích thì chưa được khắc phục đầy đủ. Cần đánh giá:

- **RBAC:** Role nào được gán? Owner mới xác nhận vai trò cần thiết chưa?
- **ABAC:** Thuộc tính `status`, `project`, `environment`, `region`, `expiry` có đúng không?
- **SoD:** Owner và người phê duyệt có bị xung đột nhiệm vụ không?
- **Quyền trực tiếp:** Có ACL/resource policy, nhóm lồng nhau, quyền chia sẻ hoặc tài khoản local không được IAM ghi nhận không?
- **JIT/PAM:** Các quyền đặc quyền ngắn hạn có còn thời hạn/phiên hoạt động ngoài mong đợi không?
- **Credential:** Token/SSH key/certificate cũ có thể tiếp tục sử dụng khi owner đã thay đổi không?

### Ví dụ về quyền hiệu dụng

~~~text
Account: svc-invoice-export
Owner cũ: U-0788 (đã nghỉ việc)

Các grant:
  - storage.invoice.read@production   (cần cho job hiện hành)
  - storage.customer.export@production (không có căn cứ mới)
  - cloud.project.admin                (role cấp trực tiếp)

Kết luận:
  Chuyển owner không tự hợp thức hóa hai quyền không cần.
  Phải kiểm tra dependency, giữ quyền đọc hóa đơn nếu được duyệt,
  thu hồi quyền export/admin không có căn cứ và xác minh lại.
~~~

Nên đo **quyền mong muốn** theo chính sách và **quyền hiệu dụng** tại ứng dụng. Với nhiều nguồn cấp quyền, gỡ một role không nhất thiết làm mất quyền nếu còn grant trực tiếp khác.

## 13. Xử lý tình huống chưa xác định được owner

Có những account không thể xác định chủ thể hoặc dịch vụ ngay. Đây là tình huống cần **quản trị rủi ro**, không phải lý do đánh dấu đã xong.

### 13.1. Quy trình điều tra có hạn

- Tạo finding với account ID, target, loại truy cập, quyền, thời điểm phát hiện và mức độ rủi ro.
- Gán **owner xử lý tạm thời** có thẩm quyền (ví dụ ứng dụng/IAM/security operations), phân biệt với owner sử dụng chính thức.
- Kiểm tra dependency, log, cấu hình workload, dữ liệu HR/VMS và hồ sơ cấp quyền.
- Đặt hạn xử lý, kênh escalation và điều kiện phải ra quyết định.
- Áp biện pháp giảm thiểu đã phê duyệt: giới hạn mạng, tạm khóa credential, thu hồi quyền nhạy cảm, tăng giám sát hoặc chặn truy cập theo rủi ro.
- Khi đủ căn cứ, chọn **chuyển giao owner hợp lệ hoặc deprovision**; nếu chưa đủ, giữ finding mở với kiểm soát và lịch rà soát.

Nếu có dấu hiệu account bị chiếm dụng hay truy cập trái phép, cần phối hợp **quy trình ứng phó sự cố bảo mật**. Việc bảo toàn chứng cứ và thứ tự thao tác có thể quan trọng hơn quy trình ownership thường ngày.

### 13.2. Phân biệt trạng thái case và trạng thái account

| Case status | Ý nghĩa | Account có thể đang thế nào? |
|---|---|---|
| `DISCOVERED` | Vừa phát hiện account nghi vấn | Active/inactive/unknown |
| `TRIAGING` | Đang phân loại chủ thể, quyền và phụ thuộc | Có thể vẫn active dưới kiểm soát |
| `OWNER_VALIDATION` | Chờ xác nhận sponsor/service owner | Active/limited |
| `CONTAINED` | Đã áp giảm thiểu rủi ro | Có thể bị giới hạn, chưa kết thúc điều tra |
| `TRANSFER_PENDING` | Chuyển owner đang chờ xác nhận | Không được tự coi đã có owner |
| `DEPROVISION_PENDING` | Đã quyết định thu hồi nhưng chưa đủ bằng chứng | Có thể vẫn còn truy cập |
| `VERIFIED_REMEDIATED` | Đạt mọi điều kiện và readback cần thiết | Owner/quyền đúng hoặc truy cập đã thu hồi |
| `EXCEPTION_TRACKED` | Ngoại lệ được phê duyệt và theo dõi | Chưa nên giả là fully remediated |

Các trạng thái chỉ là mô hình tham khảo, không phải schema chuẩn của một sản phẩm IAM. Quan trọng là **không đồng nhất case đã được giao xử lý với account đã an toàn**.

## 14. Mã giả đánh giá account thiếu owner

Dưới đây là **mã giả minh họa logic đánh giá**, không được dùng trực tiếp để vô hiệu hóa tài khoản sản xuất.

~~~python
def recommend_ownerless_account_action(account, identity, workload, policy):
    # Ưu tiên từ chối quyết định tự động khi thiếu dữ liệu trọng yếu.
    if not account.target_id or not account.account_id:
        return "INVESTIGATE_IDENTITY_MAPPING"

    if account.has_suspected_compromise:
        return "ESCALATE_SECURITY_INCIDENT"

    if account.is_break_glass:
        return "VERIFY_EMERGENCY_GOVERNANCE"

    if account.kind == "HUMAN":
        if identity is None:
            return "INVESTIGATE_HUMAN_IDENTITY"

        if identity.has_active_valid_engagement:
            if not account.owner_is_authoritative:
                return "VALIDATE_OR_TRANSFER_OWNER"
            return "REVIEW_ENTITLEMENTS"

        if identity.has_no_valid_engagements:
            return "PLAN_REVOKE_AND_VERIFY"

        return "PENDING_ENGAGEMENT_CHECK"

    if account.kind == "SERVICE":
        if workload is None or not workload.dependencies_confirmed:
            return "INVESTIGATE_WORKLOAD_DEPENDENCIES"

        if workload.is_retired:
            return "PLAN_DEPROVISION_WITH_DEPENDENCY_CHECK"

        if not workload.owner_has_accepted_responsibility:
            return "TRANSFER_SERVICE_OWNERSHIP"

        return "REVIEW_PRIVILEGES_AND_CREDENTIALS"

    return "MANUAL_CLASSIFICATION_REQUIRED"
~~~

**Không nên đặt logic tự động kiểu `if owner == null: delete_account()`.** Khắc phục cần xét loại subject, quan hệ hợp lệ, phụ thuộc, mức quyền và trạng thái triển khai; còn thao tác thực thi cần **phê duyệt, idempotency, ghi vết và readback**.

## 15. Ví dụ dữ liệu case và bằng chứng khắc phục

Một bản ghi khắc phục có thể chứa **tối thiểu thông tin đủ để kiểm toán**, không chứa mật khẩu hoặc secret:

~~~json
{
  "caseId": "ORPHAN-2026-027",
  "target": "production-reporting",
  "accountId": "svc-report-export",
  "accountType": "SERVICE",
  "finding": "OWNER_DEPARTED",
  "previousOwnerId": "U-0788",
  "riskLevel": "HIGH",
  "workloadId": "WL-240",
  "dependenciesConfirmed": true,
  "decision": "TRANSFER_AND_REDUCE_PRIVILEGES",
  "newOwnerId": "TEAM-DATA-PLATFORM",
  "ownerAcceptance": "CONFIRMED",
  "actions": [
    "OWNER_MAPPING_UPDATED",
    "UNNEEDED_ADMIN_ROLE_REVOKED",
    "EXPOSED_CREDENTIAL_ROTATED"
  ],
  "verification": {
    "targetReadback": "PASS",
    "effectivePermissionsReview": "PASS",
    "credentialStatusCheck": "PASS",
    "serviceHealthCheck": "PASS"
  },
  "caseStatus": "VERIFIED_REMEDIATED"
}
~~~

Đây là **ví dụ học tập**. Trong hệ thống thật cần lưu thời điểm, người thực hiện, phiên bản chính sách, ID thay đổi và nguồn bằng chứng, đồng thời bảo vệ dữ liệu khỏi người không có quyền. Không cần sao chép nội dung credential vào hồ sơ kiểm toán để chứng minh đã xoay vòng.

### Tiêu chí readback tùy loại quyết định

| Quyết định | Bằng chứng tối thiểu cần tìm |
|---|---|
| Chuyển owner | Owner mới đã xác nhận; nguồn chuẩn và hệ thống liên quan hiển thị đúng |
| Giảm quyền | Quyền hiệu dụng tại ứng dụng đích không còn các grant thừa |
| Tạm giới hạn | Chính sách chặn/giới hạn đã áp dụng vào đường truy cập cần kiểm soát |
| Thu hồi tài khoản | Account không thể truy cập trái chính sách; trạng thái target và phiên/token phù hợp |
| Xoay vòng secret | Credential cũ không còn hợp lệ theo cơ chế hệ thống; workload dùng credential mới và hoạt động bình thường |
| Deprovision workload | Dependency ngừng đúng quy trình; quyền, key và account không còn cần thiết đã xử lý |
| Đóng case | Không còn action bắt buộc chưa có kết quả; ngoại lệ được quản trị minh bạch |

## 16. Tình huống thực hành 1: contractor rời dự án nhưng account vẫn active

**Bối cảnh:** Nhà thầu Bình được sponsor nội bộ cấp quyền vào repository và công cụ quản lý ticket của dự án A trong ba tháng. Hợp đồng đã hết hạn hai tuần; sponsor chuyển bộ phận và không còn quản lý dự án. Trong ứng dụng ticket, `ownerId` rỗng. Account vẫn active; quyền repo được cấp trực tiếp ngoài IAM.

### Cách xử lý sai

- Chỉ đổi owner của account sang helpdesk để không còn trường trống.
- Tin rằng IdP đã chặn đăng nhập nên không cần kiểm tra repo và token.
- Không đối chiếu VMS/hợp đồng, không ghi nhận account local.
- Đóng case ngay sau khi cập nhật metadata.

Cách này có thể che giấu **quyền tồn dư** và không xác định được ai phê duyệt giữ quyền.

### Cách xử lý phù hợp

1. Xác minh đúng Bình qua identity mapping và đối chiếu account ID tại IdP, ticket và repo.
2. Kiểm tra nguồn VMS: hợp đồng A đã kết thúc; có engagement khác còn hiệu lực không?
3. Nếu không còn căn cứ, quyết định thu hồi theo chính sách; owner điều tra chịu trách nhiệm xử lý cho đến khi hoàn tất.
4. Thu hồi group/role, account local, quyền repo trực tiếp và token liên quan theo cơ chế mỗi hệ thống.
5. Xác minh readback từng target, bao gồm khả năng token hoặc phiên vẫn còn dùng được.
6. Chỉ đóng khi mọi mục bắt buộc đạt hoặc có ngoại lệ được phê duyệt và theo dõi đúng.
7. Sửa quy trình gốc để khi sponsor thay vai trò hoặc contractor hết hạn, account được kiểm kê và xử lý tự động hơn.

**Lưu ý:** Nếu Bình vẫn có hợp đồng B hợp lệ, cần tính quyền theo B và chỉ thu hồi phần thuộc A; không xóa nhầm khả năng truy cập được B bảo trợ.

## 17. Tình huống thực hành 2: service account không owner nhưng chạy hệ thống sản xuất

**Bối cảnh:** Tài khoản `svc_daily_invoice` chạy job đối soát hóa đơn vào cuối ngày trên môi trường production. Người tạo account đã nghỉ việc. CMDB không có owner; credential cũ lưu trong secret manager. Audit phát hiện account có quyền đọc hóa đơn và quyền quản trị một số cấu hình hệ thống.

### Nếu vô hiệu hóa ngay

Job có thể ngừng; báo cáo tài chính, hóa đơn hoặc đối soát bị gián đoạn. Đây là rủi ro vận hành, không chứng minh rằng quyền admin cũ là hợp lệ.

### Cách xử lý phù hợp

1. Gán owner điều tra tạm thời, đánh dấu rủi ro và xác định workload thực tế.
2. Tra lịch chạy, hệ thống gọi đến, service catalog, quyền và những người từng truy cập secret.
3. Nhóm vận hành mới chấp nhận owner, xác nhận mục đích và thời hạn của job.
4. Tính quyền mong muốn; loại role quản trị không cần nếu kiểm tra phụ thuộc cho phép.
5. Đánh giá secret cũ: nếu người đã nghỉ có thể có bản sao, lên kế hoạch **rotate/revoke** mà không làm gián đoạn hệ thống.
6. Cập nhật mapping service owner tại nguồn quản trị; giảm quyền và cập nhật secret theo quy trình thay đổi.
7. Chạy kiểm tra phù hợp để xác minh job còn hoạt động, credential cũ bị vô hiệu hóa theo yêu cầu và quyền hiệu dụng đã đúng.
8. Ghi bằng chứng, lịch rà soát và cơ chế tự phát hiện khi owner mới rời vai trò.

**Kết luận:** Khắc phục thành công có thể là **giữ account nhưng có owner hợp lệ, quyền tối thiểu và credential được quản lý an toàn**. Không bắt buộc mọi finding phải kết thúc bằng xóa tài khoản.

## 18. Tình huống thực hành 3: break-glass account không có employee ID

**Bối cảnh:** Hệ thống quản trị đám mây có một account khẩn cấp không liên kết tới nhân viên thường xuyên. Công cụ quét liệt kê account là “orphan” vì không tìm thấy `personId`.

**Phân tích:** Kết quả quét là một **cảnh báo kiểm tra**, không phải chứng cứ tài khoản trái phép. Nếu đây là break-glass chính thức, cần đối chiếu với chính sách tài khoản khẩn cấp, owner của quy trình, người có quyền truy cập credential, kiểm tra định kỳ và nhật ký sử dụng.

Các hành động phù hợp có thể là:

- Gắn account với **loại chủ thể/khả năng quản trị** đúng trong inventory.
- Xác định owner quản trị và cơ chế phê duyệt sử dụng khẩn cấp.
- Đánh giá phương thức bảo vệ credential, cảnh báo và log.
- Thu hồi/điều chỉnh nếu account thực tế không còn trong phương án khẩn cấp được phê duyệt.

Xóa account vì thiếu employee ID có thể làm mất khả năng phục hồi khi IdP/SSO gặp sự cố. Ngược lại, giữ một break-glass account không owner và không kiểm toán cũng không chấp nhận được.

## 19. Phòng ngừa account mất owner ngay trong Joiner–Mover–Leaver

### 19.1. Tại Joiner hoặc khi tạo service account

- Bắt buộc gắn **identity hoặc workload ID** và **owner có thẩm quyền** khi tạo.
- Xác định căn cứ cấp quyền, sponsor/manager và thời hạn cho contractor.
- Lưu mapping account–identity–target từ lúc provision, gồm cả account do ứng dụng cấp ID.
- Không dùng account chung khi có thể sử dụng danh tính riêng có kiểm toán.
- Thiết lập gói quyền tối thiểu, expiry và lịch access review thích hợp.

### 19.2. Tại Mover

- Khi cá nhân đổi nhóm, dự án hoặc role, cập nhật ownership của service account mà họ chịu trách nhiệm.
- Kiểm tra có owner kế nhiệm và người nhận trách nhiệm.
- Tính lại quyền mới, thu hồi quyền cũ không còn căn cứ; đừng chỉ thêm quyền.
- Đồng bộ sponsor hoặc application owner mới tới các hệ thống quản trị cần thiết.

### 19.3. Tại Leaver

- Truy vấn không chỉ account cá nhân mà cả **service account, vault, API key, repo và resource** do Leaver sở hữu/quản trị.
- Xác định tài nguyên cần chuyển giao trước khi người phụ trách rời tổ chức.
- Thu hồi quyền admin cá nhân đối với workload, xử lý secret có thể bị biết hoặc sao chép.
- Vô hiệu hóa/deprovision account không còn mục đích và đối soát ở ứng dụng.
- Phát cảnh báo với tài nguyên vẫn trỏ owner đến identity Leaver.

**Cơ chế phòng ngừa đặc biệt quan trọng:** Một account có owner hợp lệ hôm nay vẫn có thể thành ownerless ngày mai. Cần sự kiện **owner departed/role changed** để tự động mở quy trình reassignment hoặc review.

## 20. Kiểm toán và chỉ số chất lượng khắc phục

Một hồ sơ kiểm toán nên trả lời:

1. Account nào bị đánh dấu, tại target nào, dựa trên quy tắc phát hiện gì?
2. Chủ thể hoặc workload có được liên kết đúng không, nguồn xác minh nào?
3. Owner cũ và owner mới là ai, ai chịu trách nhiệm quyết định?
4. Quyền hiệu dụng, credential và phụ thuộc trước khắc phục là gì?
5. Quyết định là giữ, chuyển owner, giới hạn hay deprovision; có phê duyệt phù hợp không?
6. Lệnh đã thực thi ở các hệ thống nào và kết quả **readback** ra sao?
7. Có phiên/token, role trực tiếp hoặc ngoại lệ chưa xử lý không?
8. Khi nào finding được đóng, có kiểm tra tái xuất hiện không?

| Chỉ số | Mục đích | Bẫy thường gặp |
|---|---|---|
| **Ownerless-account rate** | Tỷ lệ account không có owner đã được xác nhận | Không tính lẫn tài khoản đúng loại nhưng thiếu field không áp dụng |
| **Time to verified remediation** | Từ phát hiện đến lúc khắc phục có bằng chứng | Không dùng thời điểm giao ticket làm mốc hoàn tất |
| **Orphan account count** | Account không còn identity/engagement/workload hợp lệ | Cần inventory đầy đủ, tránh phân loại nhầm |
| **Owner reassignment acceptance** | Owner mới đã nhận trách nhiệm và hệ thống ghi nhận | Điền ownerId chưa phải được chấp nhận |
| **Residual privileged access** | Quyền đặc quyền còn lại không có căn cứ | Kiểm tra quyền hiệu dụng, direct grants và token |
| **Service account coverage** | Tỷ lệ account máy có owner, workload và chính sách credential | Không chỉ dựa vào tên account có tiền tố `svc_` |
| **Exception aging** | Finding chưa giải quyết kéo dài bao lâu | Mọi ngoại lệ phải có owner, hạn và kiểm soát |
| **Readback coverage** | Tỷ lệ hành động được xác minh ở đích | API 2xx không thay kết quả target |
| **Owner drift recurrence** | Account tái mất owner sau khi đã khắc phục | Phát hiện lỗ hổng của workflow Mover/Leaver |

Các ngưỡng xử lý phải phù hợp mức rủi ro, hệ thống và chính sách tổ chức; không có một SLA cố định cho mọi ngành hoặc mọi loại account.

## 21. Bài tập tự kiểm tra

### Câu 1 — OwnerId rỗng nhưng người dùng vẫn đang làm việc

Một account CRM có `ownerId=null`. IdP cho thấy account ánh xạ với nhân viên còn active trong HR, và CRM có quyền đúng vị trí hiện tại.

**Hỏi:** Có cần deprovision ngay?

**Gợi ý:** Chưa đủ căn cứ. Kiểm tra mapping, dữ liệu owner/manager từ nguồn chuẩn và quyền hiệu dụng, rồi sửa metadata/quy trình đồng bộ theo chính sách. Tuy nhiên, phải ghi nhận finding và kiểm chứng kết quả thay vì bỏ qua.

### Câu 2 — Service account không có log 90 ngày

Một account chạy batch theo quý, owner đã nghỉ. Trong 90 ngày không có log sử dụng.

**Hỏi:** Có thể kết luận không còn cần thiết và xóa không?

**Gợi ý:** Không. Cần khảo sát lịch chạy, dependency và owner service; vắng log không chứng minh không có nhu cầu. Sau đó quyết định chuyển owner hoặc deprovision có kiểm soát.

### Câu 3 — Chỉ đổi owner và đóng finding

Một account sản xuất có role admin không còn phục vụ job hiện tại. Nhóm vận hành mới đã nhận ownership.

**Hỏi:** Finding đã thực sự được xử lý an toàn chưa?

**Gợi ý:** Chưa chắc. Phải kiểm tra và thu hồi quyền vượt nhu cầu, đánh giá credential, đọc lại target và lưu bằng chứng. Chuyển owner chỉ giải quyết một chiều của vấn đề.

### Câu 4 — Break-glass bị phát hiện “mồ côi”

Công cụ tự động không tìm được `personId` cho tài khoản khẩn cấp của hạ tầng.

**Hỏi:** Nên xóa account không?

**Gợi ý:** Không tự động. Kiểm tra loại account, owner governance, bảo vệ credential, log, kiểm tra định kỳ và chính sách khẩn cấp. Chỉ deprovision nếu xác định không còn căn cứ hoặc có phương án thay thế được duyệt.

### Câu 5 — Contractor đã rời tổ chức, token còn hiệu lực

Account contractor bị disabled ở IdP, nhưng personal access token của công cụ báo cáo vẫn hoạt động.

**Hỏi:** Có thể đóng case không?

**Gợi ý:** Không nếu token nằm trong phạm vi phải thu hồi. Cần chặn/thu hồi token hoặc quyền tại ứng dụng và kiểm chứng kết quả thực tế.

### Câu 6 — Một người có hai engagement hợp lệ

Một contractor hết hợp đồng dự án A nhưng vẫn làm dự án B. Account dùng chung để đăng nhập, owner sponsor A đã nghỉ.

**Hỏi:** Phải xử lý gì?

**Gợi ý:** Xác nhận sponsor B, liên kết engagement, tính lại quyền chỉ còn B, thu hồi entitlement A và chuyển owner đúng quy trình. Không mặc định xóa toàn bộ identity nếu B vẫn hợp lệ.

## 22. Checklist khắc phục account không còn owner

- [ ] **Xác định account:** Có target, account ID ổn định, loại account và trạng thái hiện hành?
- [ ] **Xác định chủ thể:** Có identity cá nhân, engagement hoặc workload đáng tin cậy; tránh ghép theo email/tên?
- [ ] **Nguồn có thẩm quyền:** Có căn cứ HR/VMS, service catalog, sponsor hoặc owner ứng dụng để quyết định?
- [ ] **Phân loại finding:** Thiếu metadata, owner departed, owner không nhận trách nhiệm hay orphan thực sự?
- [ ] **Đánh giá rủi ro:** Quyền đặc quyền, Internet-facing, token dài hạn, dữ liệu nhạy cảm và dấu hiệu bất thường?
- [ ] **Đánh giá tác động:** Có dependency sản xuất, job định kỳ, tài khoản khẩn cấp hoặc nghĩa vụ lưu giữ?
- [ ] **Owner xử lý:** Có người chịu trách nhiệm điều tra, mốc rà soát và đường escalation?
- [ ] **Owner sử dụng:** Nếu giữ account, owner mới có thẩm quyền và đã chấp nhận trách nhiệm?
- [ ] **Quyền:** Đã tính quyền mong muốn so với quyền hiệu dụng qua RBAC/ABAC, nhóm lồng nhau và cấp trực tiếp?
- [ ] **Secret/credential:** Đã đánh giá credential từng bị owner cũ biết hoặc kiểm soát; rotate/revoke khi cần?
- [ ] **Thực thi:** Hành động gán owner, giới hạn, disable/deprovision qua IdP/SCIM/API/PAM hoặc quy trình thay thế?
- [ ] **Phiên/token:** Đã xử lý các session, refresh token, API key, SSH key và lối truy cập độc lập trong phạm vi?
- [ ] **Readback:** Có bằng chứng ở từng target và quyền hiệu dụng đã đúng; không chỉ thấy ticket/API thành công?
- [ ] **Audit:** Đã ghi quyết định, người duyệt, owner, thời điểm, chính sách, kết quả và ngoại lệ?
- [ ] **Ngăn tái phát:** Có trigger khi Mover/Leaver hoặc service owner thay đổi, access review và cảnh báo owner drift?
- [ ] **Đóng finding:** Không còn hạng mục bắt buộc chưa xác minh hoặc ngoại lệ bị che giấu?

**Ghi nhớ:** **Account không còn owner không phải một loại tài khoản được phép giữ vô thời hạn hay một tín hiệu để xóa vô điều kiện.** Cách khắc phục đúng là **xác minh chủ thể và mục đích, đánh giá quyền và phụ thuộc, xác lập owner có trách nhiệm hoặc thu hồi quyền không còn căn cứ**, rồi **kiểm chứng trạng thái thực tế** qua IdP, SCIM, ứng dụng, phiên/token và tài khoản dịch vụ liên quan. Làm tốt các bước này giúp quy trình **account deprovisioning** khép kín, hỗ trợ kiểm toán và giảm quyền truy cập tồn dư xuyên suốt **Joiner–Mover–Leaver**.
