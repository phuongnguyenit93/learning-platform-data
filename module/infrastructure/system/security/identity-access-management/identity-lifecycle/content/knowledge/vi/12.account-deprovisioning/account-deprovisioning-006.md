# Thu hồi group membership trong Account deprovisioning

Trong **Identity and Access Management (IAM)**, **thu hồi group membership** là thao tác xóa quan hệ thành viên giữa một chủ thể hoặc tài khoản với một nhóm (*group*) khi quan hệ đó không còn hợp lệ. Nhóm có thể dùng để tổ chức người dùng, cấp quyền truy cập ứng dụng, ánh xạ tới role hoặc áp dụng chính sách. Vì vậy, việc rời nhóm thường là một bước quan trọng của **account deprovisioning**, đặc biệt khi nhân viên đổi vai trò hoặc nghỉ việc.

Ví dụ, nhân viên thuộc nhóm `prod-deployers` được phép triển khai ứng dụng lên môi trường production. Khi chuyển từ nhóm vận hành sang bộ phận phân tích, người đó cần được gỡ khỏi nhóm triển khai. Nếu hệ thống chỉ cập nhật chức danh trong HRIS mà quên thu hồi membership tại directory, ứng dụng hoặc nền tảng cloud, quyền triển khai có thể vẫn tồn tại. Ngược lại, nếu gỡ nhầm nhóm dùng chung `all-employees`, nhân viên đang làm việc có thể mất các dịch vụ cần thiết.

Bài học thuộc chương **Account deprovisioning** của module quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**. Nội dung tập trung vào việc xác định **group nào cần gỡ, nguồn nào có thẩm quyền, thao tác gỡ ở đâu, cách kiểm tra quyền thực tế đã mất** và cách lưu bằng chứng. Luồng xử lý liên quan HRIS, IdP/Directory, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và mục tiêu giảm **quyền truy cập tồn dư** (*residual access*).

## 1. Hiểu đúng quan hệ group membership

Một group membership là quan hệ **một thành viên thuộc một nhóm**. Thành viên có thể là tài khoản người dùng, đối tượng directory hoặc đôi khi là nhóm khác, tùy khả năng hệ thống. Quan hệ này thường được dùng để đơn giản hóa quản lý, nhưng **membership không đồng nghĩa với permission**: quyền có thể được ánh xạ từ nhóm sang role, policy hoặc tài nguyên ở nhiều lớp.

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity** | Bản ghi đại diện một chủ thể được IAM quản lý. | `person-2048` đại diện nhân viên Minh. |
| **Account** | Đối tượng ở một directory/ứng dụng cụ thể. | `idp-user-581`, `git-user-902`. |
| **Group** | Tập hợp thành viên theo quy tắc quản lý của hệ thống. | `ops-prod-deployers`. |
| **Direct membership** | Thành viên được gán trực tiếp vào nhóm. | User Minh được thêm vào `ops-prod-deployers`. |
| **Nested / Indirect membership** | Quyền thành viên có hiệu lực thông qua một nhóm cha/con, nếu hệ thống hỗ trợ. | Minh thuộc `ops-team`; nhóm này thuộc `prod-deployers`. |
| **Dynamic group** | Membership được tính từ quy tắc hoặc thuộc tính thay vì cập nhật bằng danh sách trực tiếp. | Người có `department=Finance` tự thuộc nhóm `finance-users`. |
| **Entitlement** | Đơn vị quyền có thể cấp/thu hồi ở ứng dụng hoặc nền tảng. | Role `production-deployer`. |
| **Group-to-role mapping** | Quy tắc ánh xạ nhóm thành vai trò hoặc quyền. | `ops-prod-deployers` → `cloud:deploy`. |
| **Effective access** | Quyền thực sự có hiệu lực sau khi xét các đường cấp quyền và điều kiện kiểm tra. | Minh vẫn deploy được vì có direct role dù đã rời nhóm. |

**Thu hồi membership** là xóa một quan hệ thành viên đã xác định. Nó khác với **xóa group**, **xóa account**, **disable account** hay **thu hồi mọi phiên/token**. Những biện pháp đó có thể cần phối hợp trong Leaver hoặc khi có rủi ro cao, nhưng mỗi hành động có đối tượng, phạm vi và bằng chứng riêng.

### 1.1. Bốn kết quả cần phân biệt

Giả sử IAM quyết định gỡ Minh khỏi nhóm `prod-deployers`:

1. **Decision:** chính sách/owner xác định membership không còn hợp lệ.
2. **Execution:** hệ thống gửi lệnh remove membership tới đúng directory hoặc ứng dụng.
3. **Observed membership:** đọc lại và xác nhận Minh không còn là thành viên theo kiểu quan hệ cần gỡ.
4. **Effective access:** kiểm tra Minh không còn khả năng triển khai production qua các đường quyền khác thuộc phạm vi thu hồi.

Một phản hồi API thành công ở bước 2 **không tự chứng minh** bước 3 và 4 đạt. Nếu chỉ cập nhật nhóm ở IdP nhưng target lưu role riêng, việc thu hồi cần tiếp tục tại ứng dụng. Nếu quyền được nhúng vào token hoặc session có thời hạn, quyền có thể còn hiệu lực trong một khoảng thời gian dù membership đã biến mất.

## 2. Những nhóm nào có thể cần thu hồi?

Group không chỉ là “nhóm người trong directory”. Từng loại có thể có thẩm quyền quản lý và hậu quả khác nhau:

| Loại nhóm | Ví dụ | Tác động thường gặp khi gỡ thành viên |
| --- | --- | --- |
| **Nhóm tổ chức/đơn vị** | `department-operations` | Cập nhật danh sách, nhóm ứng dụng hoặc quyền nội bộ theo bộ phận. |
| **Nhóm cấp ứng dụng** | `crm-sales-users` | Có thể mất quyền vào CRM hoặc license được gán qua group. |
| **Nhóm đặc quyền** | `production-admins` | Có thể bị thu hồi quyền quản trị/deploy hoặc chức năng nhạy cảm. |
| **Nhóm tài nguyên** | `data-finance-readers` | Có thể mất quyền đọc dữ liệu được phân quyền theo scope. |
| **Nhóm dự án** | `project-alpha-members` | Ngừng quyền với repo, môi trường hoặc dữ liệu của dự án. |
| **Nhóm bảo mật/điều kiện truy cập** | `high-assurance-users` | Có thể ảnh hưởng chính sách xác thực hoặc chính sách khác; không tự suy ra là một role nghiệp vụ. |
| **Nhóm cloud IAM** | `cloud-platform-operators` | Có thể ngừng kế thừa policy ở một account/project/subscription. |
| **Nhóm dành cho service account** | `etl-readers` | Có thể thay đổi quyền của workload, cần đánh giá ảnh hưởng vận hành. |

**Nguyên tắc:** không quyết định mức độ rủi ro chỉ từ tên nhóm. Phải biết **group ID, hệ thống sở hữu, thành viên, quyền cấp ra, nhóm lồng nhau và ứng dụng phụ thuộc**. Hai nhóm trùng tên trên hai tenant có thể hoàn toàn khác nhau.

### 2.1. Quan hệ trực tiếp và quyền gián tiếp

~~~mermaid
flowchart LR
    U["Account Minh"] -->|Direct member| T["ops-team"]
    T -->|Nested member| P["prod-deployers"]
    P -->|Maps to| R["Role production-deploy"]
    U -->|Direct grant khác| X["Role production-deploy"]
    R --> A["Ứng dụng production"]
    X --> A
~~~

Trong sơ đồ, **gỡ Minh khỏi `ops-team`** có thể làm mất đường quyền qua nhóm lồng nhau, nhưng **direct grant** vẫn còn. **Gỡ Minh khỏi `prod-deployers`** có thể không hiệu quả nếu Minh vốn không được gán trực tiếp vào nhóm đó mà nhận membership qua `ops-team`. Người vận hành phải tìm đúng cạnh quan hệ đang tạo quyền.

Một vài nền tảng không hỗ trợ nested group, hoặc không truyền membership lồng nhau sang ứng dụng khi SSO/provisioning. Trước khi viết logic thu hồi, phải kiểm chứng **ngữ nghĩa membership thực tế của từng hệ thống**, bao gồm việc nhóm lồng nhau có tác động tới authorization hay chỉ dùng để hiển thị.

### 2.2. Nhóm động cần thay đổi nguồn thuộc tính

Với nhóm **dynamic** dựa trên điều kiện `department == "Operations"`, việc “remove member” trực tiếp trong UI có thể không được hỗ trợ, hoặc membership sẽ tự xuất hiện lại sau lần tính toán tiếp theo. Khi Mover chuyển sang Finance, hướng đúng thường là:

1. HRIS hoặc nguồn quản lý nghiệp vụ cập nhật `department` theo sự kiện có hiệu lực.
2. Directory/IdP nhận thuộc tính mới qua kênh đồng bộ tin cậy.
3. Cơ chế dynamic-group đánh giá lại, loại thành viên khỏi nhóm cũ.
4. IAM kiểm tra membership và quyền hiệu lực tại các ứng dụng phụ thuộc.

Nếu nhóm động còn sử dụng điều kiện khác khiến người đó vẫn đủ điều kiện, phải điều tra **chính sách nhóm**, không tự tạo ngoại lệ trái với nguồn thuộc tính. Với trường hợp khẩn cấp, có thể cần chặn một đường truy cập ngay theo cơ chế được hỗ trợ, đồng thời xử lý nguyên nhân khiến membership tái sinh.

## 3. Thu hồi group membership theo Joiner–Mover–Leaver

### 3.1. Joiner: sửa cấp sai hoặc hủy yêu cầu trước khi bắt đầu

Trong Joiner, hệ thống có thể chuẩn bị group membership trước ngày nhân viên bắt đầu. Nếu bản ghi HR bị hủy, ngày hiệu lực đổi hoặc quyền được duyệt nhầm, IAM phải **gỡ membership chưa hợp lệ** và xác minh không có entitlement phát sinh. Việc tài khoản mới chưa từng đăng nhập không bảo đảm group chưa cấp quyền truy cập.

Đối với một sự kiện provisioning lặp, hệ thống phải tránh tạo/gỡ membership sai do race condition: ví dụ workflow cũ cấp `app-users` sau khi yêu cầu đã bị hủy. Nên đối chiếu desired state mới nhất và phiên bản nguồn thay vì chỉ chạy lại tác vụ từ event cũ.

### 3.2. Mover: gỡ nhóm theo vai trò cũ

Mover thường là tình huống rõ nhất của thay đổi membership:

- Nhân viên chuyển từ **Operations** sang **Finance**.
- Identity và account đăng nhập có thể giữ nguyên.
- Nhóm chung `all-employees` vẫn hợp lệ.
- Nhóm `ops-prod-deployers` phải gỡ nếu không còn nhiệm vụ.
- Nhóm `finance-report-readers` có thể cấp nếu đủ điều kiện.

Quy trình phải xác định riêng các nhóm **KEEP**, **REMOVE** và **GRANT**, kể cả membership được cấp từ dự án hoặc yêu cầu ngoại lệ còn thời hạn. Nếu một người đang giữ **hai assignment hợp lệ**, không được tự gỡ nhóm cần thiết cho assignment còn lại.

**SoD (Segregation of Duties)** đặc biệt quan trọng khi nhóm cũ và mới tạo tổ hợp quyền xung đột. Ví dụ, người sắp có quyền **duyệt thanh toán** không nên đồng thời giữ quyền **tạo thanh toán** trên cùng phạm vi nếu chính sách cấm. Có thể cần xác minh thu hồi nhóm cũ trước khi kích hoạt nhóm mới.

### 3.3. Leaver: thu hồi nhóm phải đi cùng chặn truy cập

Khi người dùng rời tổ chức, việc xóa group membership giúp giảm quyền tồn dư và làm sạch trạng thái tài khoản. Nhưng với leaver có rủi ro, **đợi gỡ từng nhóm rồi mới khóa đường đăng nhập** có thể không phù hợp. Quy trình thường ưu tiên chặn các phương thức truy cập cần thiết theo thời điểm chính sách, sau đó xử lý chi tiết entitlement và membership ở từng đích.

| Hành động | Mục tiêu | Điều cần xác minh |
| --- | --- | --- |
| **Disable/chặn account** | Ngừng khả năng truy cập bằng account theo cơ chế hỗ trợ. | Account bị khóa ở từng hệ thống liên quan; local account không bị bỏ sót. |
| **Remove group membership** | Loại bỏ vai trò và quyền được kế thừa từ group. | Cạnh membership thật sự không còn; quyền hiệu lực được đánh giá lại. |
| **Revoke token/credential/session** | Giảm đường truy cập còn hiệu lực sau khi thay đổi account/group. | Token, session hoặc credential được xử lý theo cơ chế đích và chính sách. |
| **Delete/retain account data** | Dọn dẹp và lưu giữ hồ sơ theo quy định. | Dữ liệu quan trọng được bàn giao/lưu giữ/xóa đúng thẩm quyền. |

**SSO không tự thu hồi group membership ở mọi ứng dụng.** IdP có thể chặn đăng nhập mới, nhưng app đã thiết lập phiên riêng, API key hoặc local password có thể vẫn hoạt động. Việc offboarding hoàn thành phải dựa vào **trạng thái thực tế và các đường truy cập đã kiểm tra**, không chỉ số lượng nhóm đã được cập nhật.

### 3.4. Đối tác và quyền tạm thời

Nhà thầu, nhà cung cấp và cộng tác viên có thể thuộc các nhóm do sponsor bảo trợ, với **ngày hết hạn** khác nhân viên chính thức. Nếu hợp đồng hoặc dự án kết thúc, IAM phải gỡ membership tương ứng ngay cả khi account đối tác còn dùng cho một quan hệ hợp lệ khác.

Với quyền tạm thời (time-bound access), nên lưu thời điểm hết hạn và có tác vụ thu hồi/đối soát. Nếu người dùng cần gia hạn, quyết định mới phải được duyệt; không giữ group membership vĩnh viễn chỉ vì người vận hành chưa nhận được ticket gỡ.

## 4. Xác định đúng membership phải thu hồi

Một thao tác sai đối tượng có thể khiến người dùng mất quyền cần thiết hoặc duy trì quyền nhạy cảm. Trước khi gỡ cần phân biệt bốn định danh:

| Thành phần | Ví dụ | Vì sao cần |
| --- | --- | --- |
| **IAM identity ID** | `person-2048` | Liên kết sự kiện JML với đúng chủ thể qua thời gian. |
| **Target account ID** | `idp-user-581` | Xác định đúng account tại hệ thống quản lý group. |
| **Target group ID** | `group-ops-deploy-12` | Xác định chính xác nhóm; tên hiển thị có thể đổi hoặc trùng. |
| **Relationship / grant source** | `HR_ROLE`, `PROJECT`, `APPROVED_EXCEPTION` | Biết vì sao account thuộc group và còn quan hệ nào hợp lệ. |

**Employee number, username và email** có thể giúp tra cứu, nhưng không nên dùng làm khóa thực thi duy nhất nếu không có hợp đồng dữ liệu bảo đảm độ ổn định và phạm vi duy nhất. Với nhiều tenant hoặc ứng dụng, dùng tổ hợp **provider/tenant + account ID + group ID** để tránh gỡ sai.

### 4.1. Trạng thái mong muốn so với trạng thái thực tế

Giả sử tại thời điểm Mover có:

- `C`: các membership thực tế đã được phát hiện ở một target và trong phạm vi quản lý.
- `D`: các membership mong muốn dựa trên vai trò, dự án còn hiệu lực và ngoại lệ được duyệt.
- `R = C − D`: các membership không còn hợp lệ cần được đánh giá gỡ.
- `K = C ∩ D`: các membership cần giữ lại.
- `G = D − C`: các membership hợp lệ còn thiếu, có thể cần cấp bổ sung.

Đây là **mô hình khái niệm**, không phải quy tắc “xóa toàn bộ phần chênh” vô điều kiện. Cần đánh giá **ownership, nguồn cấp, độ tin cậy dữ liệu, nhóm hệ thống bắt buộc và quyền có hiệu lực từ nhiều quan hệ**. Với nhóm ngoài phạm vi điều khiển IAM hoặc quyền khẩn cấp có căn cứ, phải đưa vào quy trình xem xét theo chính sách trước khi sửa.

| Nhóm | Membership thực tế | Desired state sau Mover | Hướng xử lý |
| --- | --- | --- | --- |
| `all-employees` | Có | Có | Giữ. |
| `ops-prod-deployers` | Có | Không | Gỡ và xác minh quyền deploy đã mất. |
| `finance-readers` | Chưa | Có sau phê duyệt/chính sách | Cấp đúng thời điểm. |
| `incident-response` | Có qua assignment tạm | Hợp lệ đến ngày hết hạn | Giữ đến hạn rồi thu hồi có bằng chứng. |
| `cloud-admins` | Có qua nested group khác | Không còn căn cứ | Tìm và gỡ đường membership thực tế tạo quyền. |

### 4.2. Câu hỏi preflight trước khi thực thi

1. **Sự kiện nguồn có hiệu lực chưa?** Quyết định từ HRIS/IGA, access review hay owner ứng dụng có thẩm quyền không?
2. **Đúng account chưa?** Có trùng username, đổi email, account mới hoặc multi-account chưa liên kết không?
3. **Đúng group chưa?** Group ID, tenant, ứng dụng và loại nhóm đã được xác minh?
4. **Tại sao có membership này?** Nó đến từ business role cũ, project, quyền trực tiếp hay dynamic-group rule?
5. **Còn lý do nào để giữ không?** Assignment khác, yêu cầu ngoại lệ, quyền tạm thời đã duyệt?
6. **Nhóm cấp quyền gì?** Có quyền quản trị, quyền tài chính, SoD hoặc tài nguyên trọng yếu không?
7. **Ai có thẩm quyền gỡ?** Có owner, quy trình thay đổi và người chịu trách nhiệm kết quả không?
8. **Ứng dụng đích xử lý ra sao?** Có SCIM, directory API, UI thủ công, nhóm lồng nhau hay thời gian lan truyền không?

Không nên diễn giải **gỡ membership do Leaver** thành một yêu cầu phải chờ phê duyệt cấp quyền như Joiner; quy trình cần đủ nhanh để chặn rủi ro, đồng thời vẫn xác thực nguồn sự kiện và ghi dấu vết quyết định.

## 5. Quy trình thu hồi group membership đầu cuối

~~~mermaid
flowchart TD
    SRC["HRIS / access review / approved request"] --> CHECK["Kiểm tra identity, effective time, source"]
    CHECK --> DESIRED["Tính desired membership từ role, assignment, exception"]
    DESIRED --> GRAPH["Tra direct/nested/dynamic membership và quyền thực tế"]
    GRAPH --> DEC{"Có quyền cần thu hồi?"}
    DEC -->|Không| NOOP["Ghi NO_CHANGE có căn cứ"]
    DEC -->|Có| PLAN["Chọn đúng target, group ID, cạnh cần gỡ"]
    PLAN --> EXEC["SCIM / API / Directory / UI thủ công"]
    EXEC --> OBS["Readback membership và effective access"]
    OBS --> MATCH{"Desired và observed đã khớp?"}
    MATCH -->|Không| FIX["Cảnh báo, owner, retry/khắc phục"]
    FIX --> OBS
    MATCH -->|Có| DONE["Lưu bằng chứng và kết thúc workflow"]
~~~

### Bước 1 — Nhận yêu cầu và xác định thời điểm hiệu lực

Nguồn có thể là **Leaver event** từ HRIS, **Mover event**, kết quả **access review/recertification**, yêu cầu chủ sở hữu ứng dụng, hoặc hết hạn quyền tạm. Cần lưu **event ID, version, effectiveAt, subject identity, lý do và thẩm quyền**.

Nếu HR thông báo nhân viên chuyển vai trò vào ngày 01/12 nhưng ghi quyết định từ 25/11, việc gỡ nhóm theo vai trò cũ phải bám **thời điểm hiệu lực** và điều kiện chính sách. Với rủi ro cao có thể có biện pháp kiểm soát bổ sung theo quyết định hợp lệ; không tự chọn mốc ngày nhận event làm ngày áp dụng.

### Bước 2 — Phân giải account và nhóm theo ID

Tra **identity–account binding** để tìm account trên directory/IdP và các ứng dụng liên quan. Xác định group theo ID của đúng hệ thống. Không chỉ so tên `Operations`: nhiều tenant có thể cùng dùng tên này, hoặc group đã đổi tên.

Nếu phát hiện account không có owner, gán sai người hoặc thiếu binding, đưa vào quy trình **account reconciliation / identity correlation**. Đối với trường hợp Leaver cần khóa nhanh, áp dụng biện pháp chặn truy cập theo chính sách trong khi xử lý việc đối chiếu.

### Bước 3 — Phân tích nguồn membership và đường cấp quyền

Kiểm tra account được gán trực tiếp, qua nhóm lồng nhau, nhóm động, nhóm đồng bộ từ hệ thống khác, hoặc quyền tại ứng dụng. Đối với dynamic group, quy trình thường cần **sửa thuộc tính nguồn hoặc điều kiện** rồi chờ membership được tính lại. Với nested group, phải tìm đúng quan hệ tạo đường quyền để gỡ.

Đồng thời kiểm tra **direct grants** hoặc role được cấp ngoài group. Mục tiêu quản lý quyền là bảo đảm **không còn quyền trái chính sách**, không phải chỉ đạt được danh sách group đẹp trên một màn hình.

### Bước 4 — Lập kế hoạch thu hồi và kiểm soát SoD

Kế hoạch nên nêu:

- Account ID, group ID, target system/tenant, thao tác cần thực hiện.
- Membership phải gỡ, mốc có hiệu lực, yêu cầu gỡ nhanh nếu có rủi ro.
- Quyền khác phải giữ do assignment còn hiệu lực, ngoại lệ được duyệt hay điều kiện hệ thống.
- Người thực hiện/owner, phương thức (SCIM/API/UI), expected state và cách kiểm chứng.
- Các bước phối hợp nếu nhóm có ảnh hưởng tới session, application role, cloud policy hoặc quyền đặc biệt.

Nếu Mover tạo **SoD conflict** giữa role cũ/mới, sắp xếp thứ tự xử lý theo policy, ví dụ gỡ và xác minh quyền lập thanh toán cũ trước khi kích hoạt quyền duyệt thanh toán mới.

### Bước 5 — Gỡ membership tại nơi có thẩm quyền

Thực hiện qua **directory API**, **SCIM**, **API riêng**, giao diện IdP hoặc UI quản trị của ứng dụng theo hỗ trợ thực tế. Nếu một group do hệ thống nguồn đồng bộ quản lý, việc xóa trực tiếp ở hệ thống đích có thể bị ghi đè trở lại; cần cập nhật **nguồn được ủy quyền**.

Tránh thao tác rộng như “xóa cả group” khi mục tiêu chỉ là một thành viên. Không thay thế toàn bộ danh sách thành viên nếu chỉ cần xóa một quan hệ mà chưa có cơ chế kiểm soát đồng thời, vì có thể vô tình ghi đè cập nhật của người khác.

### Bước 6 — Readback và kiểm tra quyền hiệu lực

Sau khi công cụ trả phản hồi, cần:

1. **Đọc lại group** hoặc quan hệ thành viên tại nguồn điều khiển có thẩm quyền.
2. Kiểm tra **nested/dynamic membership** còn đưa người đó vào cùng quyền hay không.
3. Kiểm tra **ứng dụng đích** đã nhận thay đổi và gỡ role tương ứng, nếu ứng dụng có bản sao membership riêng.
4. Đánh giá **session/token/credential** đang tồn tại có thể tiếp tục sử dụng quyền cũ hay không.
5. Đối chiếu **desired state** và **observed/effective access**, lưu thời điểm kiểm chứng.

Nếu một số hệ thống xử lý bất đồng bộ, cần đánh dấu **PENDING_VERIFICATION** và theo dõi đến khi hội tụ hoặc hết thời hạn. Không tuyên bố thu hồi hoàn tất ngay chỉ vì request trả HTTP thành công.

### Bước 7 — Xử lý sai lệch và lưu bằng chứng

Nếu membership chưa mất, quyền vẫn hiệu lực hoặc API lỗi, workflow phải có người nhận xử lý và thời hạn phù hợp rủi ro. Tác vụ retry cần an toàn trước việc bị phát lại, đồng thời tránh việc sự kiện cấp quyền cũ khôi phục membership đã bị gỡ.

Khi hoàn thành, giữ các thông tin có thể kiểm toán: **ai/nguồn nào quyết định, ai thực hiện, group nào, account nào, lúc nào, phản hồi ra sao, quyền thực tế có còn hay không và ai xác minh**.

## 6. Thu hồi membership qua SCIM 2.0

**SCIM (System for Cross-domain Identity Management)** cung cấp giao thức và mô hình tài nguyên chuẩn cho user/group provisioning. Với **Group**, thuộc tính `members` biểu diễn danh sách thành viên theo schema/khả năng provider. Khi ứng dụng đích hỗ trợ **PATCH Group** và lọc `members`, IAM có thể gửi một phép **Remove** tới group tương ứng.

### 6.1. SCIM PATCH: xóa đúng một thành viên

Ví dụ minh họa: IdP/IAM đã xác định user SCIM tại ứng dụng có **User.id = `u-2819`**, và group cần sửa có **Group.id = `g-ops-42`**. Một request có thể là:

~~~http
PATCH /scim/v2/Groups/g-ops-42 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"u-2819\"]"
    }
  ]
}
~~~

Ví dụ dùng cú pháp **SCIM PATCH filter** của thành viên. ID thực tế do service provider quản lý, và cách endpoint/khả năng PATCH được công bố bởi từng provider. Một số dịch vụ có giới hạn implementation hoặc yêu cầu cách cập nhật membership khác; client phải kiểm tra schema, capabilities và hành vi trả lỗi trước khi tích hợp.

**Không nhầm ba loại ID:**

- `identityId` trong IAM xác định người/workload nội bộ.
- `User.id` ở SCIM provider xác định tài nguyên User của **chính provider đó**.
- `Group.id` ở SCIM provider xác định tài nguyên Group cần cập nhật.

Không dùng email hoặc mã nhân viên thay `User.id` trong phép lọc nếu provider lưu giá trị thành viên theo SCIM resource ID. Nếu client chỉ có `externalId` hoặc username, cần giải quyết đúng **account mapping** trước khi PATCH.

### 6.2. Đọc lại Group sau PATCH

Khi provider chấp nhận PATCH, kết quả có thể là một phản hồi thành công theo chuẩn và tùy cách cung cấp biểu diễn tài nguyên. Ví dụ một bước kiểm chứng tiếp theo là gọi **GET Group** rồi kiểm tra `members`:

~~~http
GET /scim/v2/Groups/g-ops-42 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/scim+json
~~~

Một response minh họa khi nhóm còn một thành viên khác:

~~~json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
  "id": "g-ops-42",
  "displayName": "ops-prod-deployers",
  "members": [
    {
      "value": "u-9100",
      "type": "User"
    }
  ]
}
~~~

Ở đây user `u-2819` đã vắng khỏi danh sách. **Đây là readback một quan hệ group**, chưa chứng minh user đã mất toàn bộ quyền production: có thể còn một nhóm khác, role cấp trực tiếp, một token cũ hoặc entitlement tại hệ thống ngoài SCIM.

### 6.3. Thận trọng khi dùng PUT/Replace danh sách

Một số API yêu cầu gửi toàn bộ danh sách thành viên mới. Nếu hai quản trị viên cùng sửa nhóm và một bên gửi lại snapshot cũ, họ có thể vô tình **thêm lại thành viên vừa bị gỡ** hoặc **xóa thành viên mới của người khác**. Khi phải replace:

1. Đọc phiên bản và membership hiện hành.
2. Tính danh sách mới trên chính phiên bản đó.
3. Dùng cơ chế điều kiện ghi như **ETag/`If-Match` nếu provider hỗ trợ**, hoặc cơ chế khóa/điều phối tương đương.
4. Khi phát hiện thay đổi đồng thời, đọc lại và tính lại thao tác thay vì ghi đè mù.
5. Readback và đối soát sau khi ghi.

Không tự giả định mọi SCIM provider hỗ trợ thao tác PATCH, ETag, lọc thành viên hay phân trang theo cùng cách. Một kết nối phải có **kiểm thử khả năng thực tế** và đường xử lý khi API thiếu tính năng.

### 6.4. SCIM và SSO giải quyết hai việc khác nhau

**SCIM** điều khiển trạng thái tài nguyên User/Group ở ứng dụng đích. **SSO** qua SAML/OIDC giúp ứng dụng dựa vào kết quả xác thực của IdP. Khi membership thay đổi, SSO có thể phát claim nhóm mới ở lần xác thực/token tiếp theo, nhưng **SSO tự thân không bảo đảm nhóm tại ứng dụng đã bị gỡ**.

Với hệ thống chỉ dùng group claim trong token, cần hiểu **thời hạn token**, cách ứng dụng kiểm tra quyền và khi nào claim được làm mới. Với hệ thống lưu group local qua SCIM, cần đảm bảo đồng bộ Group membership thực sự thành công. Hai kiểu triển khai có thể cùng tồn tại và tạo độ trễ/đường quyền khác nhau.

## 7. Gỡ thành viên thủ công khi không có SCIM

Nhiều hệ thống legacy chỉ cho phép gỡ group membership qua UI hoặc công cụ quản trị riêng. Quy trình thủ công vẫn cần **tính nhất quán với desired state** và có bằng chứng:

| Bước | Nội dung | Bằng chứng |
| --- | --- | --- |
| **1. Ticket** | Nhận yêu cầu Mover/Leaver/review đã xác minh; biết account, group và ngày hiệu lực. | Request ID, identity ID, approval/policy, effective time. |
| **2. Xác nhận target** | Tra đúng tenant, group ID và account ID; phân biệt direct với nested membership. | Snapshot hoặc bản ghi tra cứu account/group trước thao tác. |
| **3. Thực thi** | Admin được phân quyền gỡ đúng thành viên; không xóa cả group. | Admin actor, audit event, thời điểm, kết quả UI/API. |
| **4. Kiểm chứng** | Đọc lại danh sách thành viên/quyền thực tế từ nguồn tin cậy. | Snapshot sau thao tác, target account/group ID, reviewer nếu cần. |
| **5. Hoàn tất** | Cập nhật IAM inventory, đóng ticket khi quyền bắt buộc đã được thu hồi. | Workflow status, verification timestamp, owner. |

Với quyền nhạy cảm, có thể cần **phân tách nhiệm vụ** giữa người đề nghị/ra quyết định, operator và người kiểm tra. Không dùng một tin nhắn “đã xóa nhóm” không có account/group ID và bằng chứng readback làm chứng minh hoàn tất.

Nếu UI trả lỗi mạng sau khi bấm Save, cần **kiểm tra trạng thái ở target trước khi thử lại**. Việc lặp tác vụ không được thay đổi một group khác hoặc vô tình làm mất quyền hợp lệ. Nếu thao tác bị hủy giữa chừng, cần lưu trạng thái phần việc đã hoàn thành và những target còn chờ.

## 8. Độ trễ đồng bộ, phiên, token và quyền truy cập tồn dư

Đối với một người đã bị gỡ khỏi group tại IdP, có thể tồn tại nhiều trạng thái khác nhau:

| Lớp | Trạng thái có thể còn | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| **HRIS/IGA** | Vai trò mới đã có hiệu lực nhưng desired group chưa tính lại. | Kiểm tra event processing, role/attribute và policy version. |
| **Directory/IdP** | Group membership còn lưu hoặc dynamic rule tính lại sai. | Readback group/attribute, xem direct/indirect membership. |
| **Provisioning connector** | Event đang chờ, retry lỗi, mapping group sai. | Theo dõi queue/job, response, dead-letter và owner xử lý. |
| **Ứng dụng đích** | Group/role local chưa thay đổi hoặc còn direct grant. | Đọc lại entitlement và account binding tại ứng dụng. |
| **SSO/token** | Token/claim cũ còn hợp lệ đến khi hết hạn hoặc bị thu hồi. | Đánh giá token TTL, session revocation và enforcement theo khả năng. |
| **Access policy/PDP** | Policy dựa trên cache, dữ liệu nhóm cũ hoặc quyền theo đường khác. | Kiểm tra cách quyết định được làm mới và quyền hiệu lực. |
| **Credential độc lập** | Personal access token, API key, local password vẫn tạo được yêu cầu. | Quản lý credential/đường đăng nhập riêng theo mức rủi ro. |

**Một group membership không còn trong directory** chưa đồng nghĩa mọi request đang dùng token cũ sẽ bị từ chối ngay. Nếu hệ thống dùng JWT chứa scope/claim tại lúc phát hành, quyền có thể còn tùy cách resource server kiểm tra. Với ứng dụng có session server-side, việc gỡ group có thể chỉ có hiệu lực ở lần truy cập hoặc đăng nhập tiếp theo, tùy sản phẩm.

Khi thu hồi quyền **đặc quyền**, IAM cần xác định có phải:

- Buộc xác thực lại hoặc kết thúc phiên quản trị?
- Thu hồi/giảm thời hạn token và refresh token khi cơ chế hỗ trợ?
- Gỡ thêm role trực tiếp, tài khoản local hoặc grant tại tài nguyên đích?
- Thay đổi khóa/secret mà chủ thể còn kiểm soát hoặc biết?

Những thao tác này cần dựa trên **chính sách, rủi ro và khả năng kỹ thuật của hệ thống đích**. Không tuyên bố chúng xảy ra tự động chỉ vì một group đã bị cập nhật.

## 9. Tài khoản dịch vụ, group đặc quyền và nhóm dùng chung

### 9.1. Service account có vòng đời riêng

Một workload như `etl-exporter` có thể là thành viên nhóm `report-readers` để gọi API. Tài khoản này không nhận sự kiện JML trực tiếp từ HRIS, nên **không được gỡ khỏi mọi group chỉ vì chủ sở hữu con người nghỉ việc**. Khi owner Mover/Leaver:

1. Bàn giao owner hoặc nhóm chịu trách nhiệm vận hành workload.
2. Rà soát ai có quyền quản trị service account và secret của nó.
3. Thu hồi quyền cá nhân, token hoặc credential mà người cũ còn kiểm soát nếu cần.
4. Xác định workload còn cần membership nào dựa trên mục đích, tài nguyên và least privilege.
5. Khi workload ngừng hoạt động, deprovision account và group memberships theo vòng đời dịch vụ, rồi xác minh.

Điều này tránh cả hai sai lầm: để lại **orphaned service account** không có owner và vô tình làm gián đoạn dịch vụ bằng cách gỡ quyền kỹ thuật còn hợp lệ.

### 9.2. Privileged group cần tiêu chí nghiêm ngặt hơn

Với các nhóm như `cloud-admins`, `db-owners`, `production-deployers`, `security-operators`:

- Rõ owner quyền và điều kiện cấp/thu hồi.
- Ghi lịch sử người thay đổi membership, approval và lý do.
- Tìm nested groups, quyền kế thừa và direct grants ngoài group.
- Xem **PAM/JIT** (quyền quản trị tạm thời), session và credential đã cấp.
- Kiểm tra quyền thực tế ở tài nguyên quan trọng sau khi gỡ.
- Theo dõi độ trễ thu hồi theo mức độ rủi ro.

Với **break-glass** hoặc tài khoản khẩn cấp, không tự gỡ membership làm mất khả năng khôi phục hệ thống nếu policy yêu cầu tài khoản đó tồn tại. Cần thủ tục đặc thù có owner, bảo vệ credential, giới hạn sử dụng, audit và rà soát sau sự kiện.

### 9.3. Shared group và shared account không đồng nghĩa

Một nhóm có nhiều thành viên là bình thường. **Shared account** là một account được nhiều người sử dụng chung, gây khó gán hành động cho đúng người. Nếu shared account thuộc một nhóm nhạy cảm, chỉ gỡ một cá nhân khỏi hệ thống IAM có thể **không đủ** để ngăn họ tiếp tục dùng credential chung.

Cần ưu tiên account riêng; nếu buộc duy trì shared account, có thể cần PAM broker, ghi nhận người nhận phiên, giới hạn thời gian và xoay vòng secret khi quan hệ lao động/ủy quyền thay đổi.

## 10. Kiểm toán và accountability của việc thu hồi group

Một workflow có trách nhiệm giải trình phải phân biệt **người yêu cầu**, **nguồn quyết định**, **người thực thi** và **người kiểm chứng**. Nếu connector SCIM dùng service account để gửi PATCH, service account là *technical actor*, không nhất thiết là người có thẩm quyền quyết định quyền.

| Bằng chứng | Câu hỏi được trả lời |
| --- | --- |
| Identity/account/group ID kèm tenant/target | Đã gỡ đúng người khỏi đúng nhóm ở đâu? |
| HR event, access review hoặc request ID | Vì sao quyền không còn hợp lệ? |
| Policy/version, approval/exception reference | Ai hoặc chính sách nào quyết định? |
| `effectiveAt`, `attemptedAt`, `verifiedAt` | Quyền phải hết từ khi nào, đã thao tác và xác minh lúc nào? |
| Connector job/API/UI audit event | Ai/công cụ nào đã thực hiện và kết quả ra sao? |
| Direct/nested/dynamic membership path | Đã tìm đúng nguồn membership tạo quyền chưa? |
| Target readback, entitlement snapshot, access check | Quyền thực tế đã bị loại bỏ ở lớp cần thiết chưa? |
| Remediation ticket, owner và completion evidence | Ai khắc phục lỗi và kết luận dựa trên bằng chứng nào? |

### 10.1. Ví dụ dữ liệu sự kiện thu hồi

Đoạn JSON dưới đây là **schema minh họa nội bộ**, không phải định dạng SCIM hoặc audit chuẩn bắt buộc:

~~~json
{
  "workflowId": "iam-revoke-group-2048",
  "sourceEventId": "hr-mover-2026-0142",
  "reason": "MOVER_ROLE_NO_LONGER_REQUIRES_GROUP",
  "identityId": "person-2048",
  "target": {
    "system": "CorporateIdP",
    "tenant": "company",
    "accountId": "idp-user-581",
    "groupId": "group-ops-deploy-12"
  },
  "authority": {
    "policyRef": "role-access-policy-v5",
    "desiredMember": false,
    "effectiveAt": "2026-09-01T00:00:00+07:00"
  },
  "execution": {
    "actor": "provisioning-connector",
    "operationId": "scim-patch-910",
    "result": "SUCCEEDED"
  },
  "verification": {
    "checkedAt": "2026-09-01T00:00:25+07:00",
    "directMembershipPresent": false,
    "effectivePrivilegedAccess": "NOT_PRESENT",
    "status": "VERIFIED"
  }
}
~~~

**Không đồng nhất** `execution.result = SUCCEEDED` với `verification.status = VERIFIED`. Trường hợp chưa xác minh quyền qua nested group hoặc token còn hiệu lực, phải biểu diễn trạng thái tương ứng, ví dụ `PENDING_VERIFICATION` hoặc `PENDING_REMEDIATION`, thay vì ghi `VERIFIED` không có căn cứ.

### 10.2. Bảo vệ audit log và dữ liệu cá nhân

Audit trail cần đủ thông tin để nối các sự kiện theo **event ID, request ID, target account/group ID** nhưng nên giảm thiểu dữ liệu cá nhân được sao chép. Không ghi mật khẩu, secret, access token hoặc refresh token đầy đủ vào log. Đồng bộ thời gian giữa hệ thống, phân quyền đọc/sửa log, bảo vệ tính toàn vẹn và áp dụng retention phù hợp chính sách/pháp lý.

Nếu cần điều tra một thay đổi group sai, phải giữ được lịch sử **trước/sau**, người thao tác và lý do, kể cả khi nhóm hoặc account đã đổi tên hoặc bị xóa sau đó.

## 11. Xử lý lỗi, sự kiện đến muộn và quyền tự xuất hiện trở lại

### 11.1. Những lỗi điển hình

| Tình huống | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| API báo thành công nhưng membership vẫn có. | Đọc cache, sync chậm, cập nhật sai target, dynamic rule hoặc nested membership. | Kiểm tra nguồn có thẩm quyền, target ID, effective state và thời gian hội tụ. |
| Membership vừa gỡ lại tự xuất hiện. | HR role cũ vẫn có hiệu lực hoặc job provisioning cũ phát lại. | Kiểm tra desired state, event version, source/ownership và idempotency. |
| Gỡ khỏi IdP nhưng ứng dụng vẫn có role. | App sync theo lịch, mapping sai hoặc có direct grant. | Readback app, thực thi deprovisioning ở target và kiểm tra entitlement. |
| Một member có nhiều đường được thêm vào group. | Direct + nested hoặc nhiều assignment cùng cấp quyền. | Tìm tất cả đường hợp lệ; gỡ đúng nguồn quyền không còn căn cứ. |
| Worker/UI thiếu quyền sửa group. | Group owner khác, scope quản trị giới hạn. | Giao đúng owner/operator và theo dõi SLA; không dùng account admin không được duyệt. |
| HTTP timeout sau PATCH. | Request có thể đã được thực thi nhưng response thất lạc. | Đọc lại trạng thái trước khi retry; tránh thao tác dựa trên giả định thất bại. |
| PUT ghi đè thay đổi thành viên khác. | Ghi danh sách từ snapshot cũ, thiếu concurrency control. | Dùng PATCH hoặc If-Match/ETag nếu có, rồi đối soát. |
| Leaver còn dùng được token/phiên cũ. | Claim được cache, token chưa hết hạn hoặc có local credential. | Kiểm tra các đường truy cập và thu hồi bổ sung theo khả năng. |
| Gỡ nhầm nhóm dùng chung khi Mover. | Policy bỏ qua assignment khác hoặc nhầm group ID. | Khôi phục theo quy trình có phê duyệt, sửa policy và kiểm tra tác động. |

### 11.2. Idempotency và ordering

Giả sử HRIS phát:

- **Event 41:** nhân viên chuyển từ Operations sang Finance, phải gỡ `ops-prod-deployers`.
- **Event 42:** nhân viên được giao một nhiệm vụ vận hành tạm thời, có quyền đọc log nhưng không được deploy production.

Nếu queue gửi lại **Event 40** (role cũ) sau khi Event 41/42 đã áp dụng, một connector xử lý thuần theo thứ tự nhận có thể cấp lại nhóm deploy. IAM cần:

1. Xác thực nguồn, định danh event và kiểm tra version/effective time.
2. Chống thực thi trùng, nhưng vẫn cho phép xử lý các điều chỉnh hợp lệ.
3. Trước khi áp dụng quyền, tính hoặc xác nhận **desired state hiện hành** cho đúng assignment.
4. Không để lệnh cấp quyền cũ ghi đè quyết định thu hồi mới.
5. Khi reconciliation phát hiện membership tự quay lại, tạo cảnh báo và khắc phục ở **nguồn gây tái cấp**.

**Idempotency** nghĩa là xử lý lặp cùng thao tác không làm thay đổi kết quả mong muốn hoặc tạo tác động phụ sai; **ordering** giải quyết thứ tự diễn biến nghiệp vụ. Hai thuộc tính đều cần thiết nhưng không đồng nghĩa.

### 11.3. Một workflow có trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: Mover / Leaver / Review
    REQUESTED --> VALIDATING
    VALIDATING --> NEEDS_REVIEW: Identity/group/source mâu thuẫn
    VALIDATING --> PLANNED: Quyết định hợp lệ
    NEEDS_REVIEW --> PLANNED: Đã giải quyết
    PLANNED --> EXECUTING: Đến thời điểm hiệu lực
    EXECUTING --> VERIFYING: Đã gửi/thực hiện thao tác
    EXECUTING --> REMEDIATION: Lỗi hoặc kết quả chưa rõ
    VERIFYING --> VERIFIED: Membership và access phù hợp
    VERIFYING --> REMEDIATION: Sai lệch chưa xử lý
    REMEDIATION --> VERIFYING: Retry/khắc phục + readback
    VERIFIED --> [*]
~~~

Đây là **mô hình vận hành tham khảo**, không bắt buộc từng sản phẩm phải dùng đúng tên trạng thái. Trường hợp không cần gỡ gì nên có trạng thái **NO_CHANGE_VERIFIED** hoặc tương đương với căn cứ, để tránh phân biệt nhầm “không chạy” với “đã kiểm tra và không cần thay đổi”.

## 12. Tình huống xuyên suốt: thu hồi group triển khai production

**Bối cảnh:** Minh có identity `person-2048`, account IdP `idp-user-581`, đồng thời có account Git và cloud đã liên kết. HRIS xác nhận Minh chuyển từ kỹ sư vận hành sang chuyên viên phân tích ngày 01/09. Quyền cũ `ops-prod-deployers` phải hết hiệu lực; Minh vẫn giữ `all-employees` và sẽ nhận quyền đọc báo cáo mới theo chính sách.

### 12.1. Trạng thái trước và sau

| Quyền/đường cấp | Trước Mover | Desired sau Mover | Hành động |
| --- | --- | --- | --- |
| `all-employees` tại IdP | Thành viên | Thành viên | Giữ. |
| `ops-prod-deployers` tại IdP | Thành viên trực tiếp | Không | Gỡ membership. |
| `ops-team` → group deploy ở cloud | Thành viên gián tiếp | Không còn quyền deploy | Tìm và gỡ đường quyền còn hiệu lực theo owner. |
| `git-release-maintainer` trực tiếp tại Git | Có | Không | Thu hồi entitlement tại Git. |
| `finance-report-readers` | Không | Có khi đủ điều kiện | Cấp riêng theo chính sách/approval. |
| Refresh token hoặc session Git | Có thể còn | Không được duy trì quyền cũ ngoài thời điểm cho phép | Kiểm tra khả năng thu hồi và chính sách phiên. |

### 12.2. Diễn biến thực thi

1. **25/08:** HRIS ghi nhận Mover có hiệu lực 01/09. IAM liên kết đúng identity và tính desired membership.
2. **01/09:** IAM gửi lệnh gỡ user khỏi `ops-prod-deployers` qua API/SCIM; IdP xác nhận group không còn user.
3. **01/09:** Đối soát tại cloud phát hiện Minh vẫn nằm trong một nested group cấp quyền deploy. Tác vụ chưa được coi là hoàn tất.
4. **01/09:** Owner của group cloud gỡ đường membership không còn hợp lệ, kiểm tra role thực tế, đồng thời xử lý session/token có liên quan theo policy.
5. **01/09:** Git vẫn có direct grant `release-maintainer` được cấp thủ công trước đó. IAM tạo ticket deprovisioning để application owner thu hồi.
6. **Sau khắc phục:** IAM readback IdP, cloud và Git. Khi quyền triển khai cũ không còn hiệu lực qua các đường đã biết, workflow ghi `VERIFIED` và lưu bằng chứng.

**Bài học:** “Đã rời một group” là kết quả ở **một lớp**. Mục tiêu cuối là đảm bảo **quyền không còn căn cứ thực sự không thể sử dụng** trên các tài nguyên nằm trong phạm vi kiểm soát.

### 12.3. Pseudocode triển khai theo desired state

~~~text
revokeGroupAccess(event):
    require authoritativeSourceAndValidEvent(event)
    identity = resolveVerifiedIdentity(event.subject)
    require correctEffectiveTimeAndVersion(event)

    if eventAlreadyApplied(event.id):
        return existingRecordedOutcome(event.id)

    desired = calculateApprovedMemberships(
        identity,
        allActiveAssignments(identity),
        validExceptions(identity),
        policyVersionFor(event)
    )

    observed = discoverRelevantMembershipsAndAccess(identity)
    candidates = findMembershipsNoLongerJustified(observed, desired)

    plan = resolveTargetsAndMembershipPaths(candidates)
    require noUnresolvedIdentityOrGroupConflict(plan)
    persistDecisionAndPlan(event, plan)

    for each targetAction in plan:
        executeSafeRemovalAtAuthoritativeTarget(targetAction)
        recordResultAndRetryIfNeeded(targetAction)

    latest = readbackMembershipsAndEffectiveAccess(plan)
    if latest conflicts with approvedDesiredAccess(identity):
        createAlertAndAssignRemediationOwner(event, latest)
        return PENDING_REMEDIATION

    recordVerifiedResult(event, latest)
    return VERIFIED
~~~

Đây là **pseudocode**, không phải chương trình triển khai trực tiếp. Cần làm rõ ngữ nghĩa source/version, membership nhiều nguồn, quyền từ nested/dynamic groups, eventual consistency, retry, điều kiện quyền đặc biệt và mức độ kiểm chứng cho từng target. Nếu hệ thống không thể đọc trực tiếp quyền hiệu lực, kết quả phải thể hiện **giới hạn kiểm chứng** và biện pháp bù trừ được phê duyệt.

## 13. Đo lường chất lượng thu hồi membership

| Chỉ số | Gợi ý định nghĩa | Điều dễ đo sai |
| --- | --- | --- |
| **Revocation coverage** | Số membership phải gỡ được xác định có target owner và kế hoạch ÷ tổng membership cần gỡ trong phạm vi. | Chỉ tính nhóm được IAM nhìn thấy, bỏ qua target thiếu tích hợp. |
| **Verified membership removal rate** | Số thao tác gỡ có readback xác nhận ÷ tổng thao tác gỡ đến hạn. | Coi HTTP success hoặc đóng ticket là verified. |
| **Effective access closure rate** | Số trường hợp quyền thực tế được xác minh đã mất ÷ tổng trường hợp cần kiểm chứng trong phạm vi. | Không kiểm tra nested group, direct grant, session/token. |
| **Revocation latency** | Khoảng từ mốc phải thu hồi theo policy đến lúc quyền thực tế bị chặn. | Lấy thời điểm tạo ticket làm mốc thay vì effective time. |
| **Membership reappearance rate** | Tỷ lệ membership bị cấp lại sau khi đã thu hồi có kiểm chứng. | Không phân biệt tái cấp hợp lệ với event cũ hoặc drift. |
| **Stale privileged membership** | Số membership đặc quyền không còn căn cứ hoặc quá hạn review. | Đánh giá bằng tên nhóm thay vì quyền thực tế. |
| **Remediation SLA** | Tỷ lệ lỗi thu hồi được xử lý và xác minh trong thời hạn quy định. | Đóng ticket khi mới bắt đầu retry. |

Không có một ngưỡng chung đúng cho mọi tổ chức. Với nhóm có quyền production, tài chính hoặc bí mật nhạy cảm, rủi ro của một membership tồn dư có thể lớn hơn nhiều membership thông thường. Nên phân tầng mức độ ưu tiên và phạm vi giám sát theo **quyền thực tế**.

## 14. Các sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gỡ nhóm theo display name thay vì group ID đúng tenant. | Nhầm group hoặc gỡ sai ứng dụng. | Liên kết identity/account/group theo ID và source. |
| Chỉ gỡ direct membership trong khi quyền đến từ nested group. | Người dùng vẫn có quyền. | Khám phá đường kế thừa và gỡ đúng nguồn membership tạo quyền. |
| Xóa user thủ công khỏi dynamic group. | Người dùng tự xuất hiện trở lại. | Cập nhật thuộc tính/chính sách có thẩm quyền, rồi đối soát. |
| Coi nhóm IdP đã đổi là toàn bộ ứng dụng đã đổi. | Role local, group đồng bộ chậm hoặc direct grant vẫn còn. | Readback từng target và effective access. |
| Gỡ tất cả nhóm khi Mover không xét assignment khác. | Làm mất quyền công việc vẫn hợp lệ. | Tính desired state từ mọi quan hệ và ngoại lệ đang có hiệu lực. |
| Dùng PUT danh sách member cũ mà không kiểm soát đồng thời. | Ghi đè thay đổi của quản trị viên khác. | PATCH có mục tiêu, version/ETag/If-Match nếu hỗ trợ. |
| Không kiểm tra token/session khi gỡ nhóm đặc quyền. | Quyền có thể tiếp tục qua phiên cũ. | Bổ sung kiểm soát phiên/token theo risk và khả năng đích. |
| Gỡ quyền của service account theo sự kiện HR owner. | Gián đoạn workload hợp lệ hoặc orphaned identity. | Tách human lifecycle, service lifecycle và owner handover. |
| Lỗi connector nhưng workflow đánh dấu thành công. | Residual access không ai xử lý. | Trạng thái pending, retry, owner và verification. |
| Quyền vừa gỡ tự được provisioning job cũ cấp lại. | Quyền tồn dư lặp lại. | Idempotency, source event ordering và reconciliation. |
| Chỉ ghi log “remove succeeded”. | Không chứng minh đã hết quyền hiệu lực. | Lưu cả quyết định, thực thi, readback và trạng thái tài nguyên. |

## 15. Checklist vận hành và bài tập

### 15.1. Checklist trước khi đóng task gỡ group

- [ ] Có sự kiện JML/review/request hợp lệ, nguồn và `effectiveAt` được xác minh.
- [ ] Xác định đúng IAM identity, account ID, group ID, target và tenant.
- [ ] Biết membership là **direct, nested hay dynamic**, và nơi có thẩm quyền chỉnh sửa.
- [ ] Đã tính desired state từ role, project, assignment và ngoại lệ còn hiệu lực.
- [ ] Không gỡ quyền đang cần bởi quan hệ khác; đã xét xung đột SoD nếu là Mover.
- [ ] Kế hoạch gỡ có owner, mốc thời gian và xử lý đặc quyền/khẩn cấp nếu cần.
- [ ] SCIM/API/UI thực thi đúng một quan hệ cần gỡ; lỗi hoặc timeout được xử lý an toàn.
- [ ] Readback xác minh group membership tại nguồn và các ứng dụng phụ thuộc.
- [ ] Đã kiểm tra **effective access**, gồm nested groups, direct grants và token/session khi liên quan.
- [ ] Đã xử lý nguy cơ membership tái xuất hiện do dynamic rule hoặc provisioning event cũ.
- [ ] Lỗi còn lại có remediation owner và deadline; không đóng giả thành công.
- [ ] Audit evidence lưu quyết định, executor, target, thời điểm và kết quả verification.

### 15.2. Tình huống A — Nhóm lồng nhau

Một nhân viên đã bị gỡ trực tiếp khỏi `cloud-admins` nhưng vẫn có quyền cloud admin qua `platform-team`. Hãy xác định **đường membership nào còn tạo quyền**, dữ liệu cần đọc ở directory/cloud và bằng chứng cần có để xác nhận mất quyền.

### 15.3. Tình huống B — Dynamic group theo phòng ban

HR xác nhận nhân viên chuyển sang Finance nhưng nhóm `operations-users` vẫn chứa account. Người quản trị thử remove qua UI, sau đó account tự xuất hiện lại. Hãy phân tích **nguồn thuộc tính, rule, đồng bộ và thời điểm hiệu lực**; đề xuất cách xử lý không gây tái cấp.

### 15.4. Tình huống C — SCIM PATCH thành công, ứng dụng vẫn cho deploy

SCIM trả phản hồi thành công khi gỡ user khỏi Group, GET Group cũng không còn user. Tuy nhiên ứng dụng vẫn cho deploy. Hãy nêu các khả năng như **direct role, nested membership, local account hoặc session/token cũ** và cách kiểm tra theo từng lớp.

### 15.5. Tình huống D — Hai assignment

Một kỹ sư đã chuyển khỏi Operations nhưng vẫn hỗ trợ dự án vận hành hai tuần theo phê duyệt. Hãy xác định nhóm nào phải gỡ ngay, nhóm nào có thể giữ có thời hạn và cách bảo đảm SoD, owner, expiration và readback sau khi hết hạn.

### 15.6. Tình huống E — Owner service account nghỉ việc

Một service account `etl-exporter` thuộc nhóm `analytics-readers`; nhân viên chịu trách nhiệm account vừa nghỉ việc. Có nên gỡ ngay nhóm `analytics-readers` của workload? Hãy phân biệt việc **chặn quyền cá nhân**, **bàn giao owner**, **xử lý secret** và **vòng đời quyền thực tế của service**.

**Điểm cần ghi nhớ:** **Thu hồi group membership** là thay đổi một quan hệ cấp quyền có thể ảnh hưởng nhiều lớp IAM. Quy trình đúng bắt đầu từ **nguồn quyết định hợp lệ**, xác định **đúng user/account, group, đường membership và thời điểm hiệu lực**, thực thi qua cơ chế được hệ thống hỗ trợ, rồi **đọc lại group và quyền truy cập thực tế**. Đặc biệt với Mover và Leaver, phải tìm **quyền trực tiếp, nhóm lồng nhau, nhóm động, phiên/token và các tài khoản ngoài IdP** để giảm quyền truy cập tồn dư, đồng thời giữ đầy đủ bằng chứng kiểm toán và người chịu trách nhiệm xử lý sai lệch.
