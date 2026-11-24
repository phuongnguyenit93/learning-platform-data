# Tỷ lệ account hợp lệ trong IAM: định nghĩa, đo lường và hành động

**Tỷ lệ account hợp lệ** (*valid account ratio*) cho biết bao nhiêu phần trăm tài khoản trong phạm vi kiểm soát đáp ứng các điều kiện tồn tại và truy cập đã được tổ chức phê duyệt. Đây là một chỉ số quan trọng trong quản lý vòng đời danh tính (*Identity Lifecycle Management*) vì nó giúp tìm tài khoản vẫn có khả năng truy cập dù chủ thể đã nghỉ việc, tài khoản dịch vụ thiếu người chịu trách nhiệm, account không liên kết được với danh tính chuẩn hoặc quyền truy cập không còn phù hợp.

Trong IAM, **identity** đại diện cho chủ thể (con người hoặc thực thể phi con người); **account** là tài khoản tại một hệ thống cụ thể; **entitlement** là một quyền hoặc khả năng truy cập. Một identity có thể có nhiều account, mỗi account lại có nhiều quyền. Vì vậy, tỷ lệ account hợp lệ phải dựa trên **đơn vị account**, không dùng số nhân viên, số identity trong IdP, số phiên SSO hay số quyền để thay thế.

Trong mô hình **Joiner–Mover–Leaver (JML)**, chỉ số này kết nối quy trình xác minh và cấp account, thay đổi vai trò theo RBAC/ABAC, provisioning qua SCIM, thu hồi khi nghỉ việc, kiểm soát tài khoản dịch vụ và bằng chứng kiểm toán.

## 1. Thế nào là một account hợp lệ?

Account **enabled** nghĩa là hệ thống đích cho phép sử dụng tài khoản theo trạng thái kỹ thuật của nó. Điều đó **không tự chứng minh** account vẫn được phép tồn tại và sử dụng theo chính sách IAM.

Một account được xem là **hợp lệ tại một thời điểm** khi thỏa tất cả điều kiện áp dụng cho loại account đó:

| Điều kiện | Câu hỏi kiểm chứng | Bằng chứng thường dùng |
|---|---|---|
| **Liên kết danh tính** | Có truy vết account về một chủ thể đáng tin cậy? | Khóa identity chuẩn, mapping account–identity |
| **Tư cách còn hiệu lực** | Người dùng, nhà thầu hoặc workload còn được phép truy cập? | HRIS, hợp đồng, service inventory, trạng thái IdP |
| **Chủ sở hữu** | Có người/nhóm chịu trách nhiệm rõ ràng? | Manager, service owner, đội vận hành |
| **Nhu cầu và phê duyệt** | Mục đích sử dụng còn chính đáng và được phê duyệt? | Yêu cầu cấp quyền, ticket, ngoại lệ còn hạn |
| **Quyền phù hợp** | Các role, permission, scope hiện tại có đúng chính sách? | RBAC, ABAC, rà soát quyền, kiểm tra SoD |
| **Thời hạn, rà soát** | Account và các phê duyệt đã được tái chứng nhận theo chu kỳ? | Ngày hết hạn, bản ghi access review |
| **Kiểm toán, provisioning** | Có thể giải thích account được tạo, thay đổi và thu hồi như thế nào? | Nhật ký JML, SCIM/API, audit log ứng dụng |

Các điều kiện này là **một bộ quy tắc vận hành mẫu**, không phải chuẩn bắt buộc duy nhất. Mỗi tổ chức cần ban hành tiêu chí theo loại account, mức độ quan trọng của hệ thống và chính sách ngoại lệ.

Đặc biệt:

- **Tài khoản con người:** phải truy được tới một identity được xác minh, tư cách nhân sự/đối tác còn hiệu lực và quyền được cho phép.
- **Tài khoản dịch vụ, bot, workload:** không cần có hồ sơ HRIS như nhân viên, nhưng cần identity máy hoặc bản ghi đăng ký tương ứng, owner, mục đích, giới hạn quyền và cơ chế rà soát.
- **Account đặc quyền hoặc break-glass:** phải có quy tắc ngoại lệ riêng, chủ sở hữu, phạm vi, thời hạn và nhật ký sử dụng; không nên tự động gộp vào nhóm account thông thường.
- **Account bị vô hiệu hóa:** có thể được lưu để kiểm toán hoặc giữ dữ liệu đúng chính sách, nhưng không còn trong phạm vi **account enabled** theo định nghĩa chính của bài.

Một account hoàn toàn có thể đăng nhập được nhưng **không hợp lệ**. Ngược lại, account bị disabled để chờ xóa theo chính sách có thể được quản trị đúng vòng đời dù không còn quyền truy cập.

## 2. Xác định tử số, mẫu số và thời điểm chốt

Để tập trung vào nguy cơ truy cập tồn dư, bài này sử dụng định nghĩa **tỷ lệ account đang enabled và đã được xác minh hợp lệ**:

- **Mẫu số:** số account **enabled** tại hệ thống đích, thuộc danh sách ứng dụng/tenant/môi trường đang kiểm soát, tại một thời điểm chốt xác định.
- **Tử số:** số account thuộc mẫu số **đồng thời** đạt mọi tiêu chí bắt buộc: chủ thể hợp lệ, liên kết identity rõ ràng, owner khi cần, mục đích và phê duyệt còn hiệu lực, quyền phù hợp, không quá hạn kiểm soát.
- **Khóa đếm:** bộ định danh duy nhất trong hệ thống, ví dụ **(system_id, tenant_id, account_id)**. Một người dùng có account ở ba ứng dụng được đếm thành ba account khác nhau.

Gọi \(A(t)\) là tập các account enabled thuộc phạm vi tại thời điểm \(t\), và \(V(a,t)\) là kết quả đánh giá tính hợp lệ của account \(a\):

\[
R_{\mathrm{valid}}(t)
=\frac{|\{a\in A(t): V(a,t)=\mathrm{PASS}\}|}{|A(t)|}\times100\%.
\]

Nếu tất cả account đã được phân loại độc quyền vào ba trạng thái **PASS**, **FAIL**, **UNKNOWN**, thì:

\[
N_{\mathrm{enabled}}=N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}+N_{\mathrm{UNKNOWN}}.
\]

| Trạng thái | Ý nghĩa | Tính vào tử số? |
|---|---|---|
| **PASS** | Có đủ bằng chứng account đạt các điều kiện áp dụng | Có |
| **FAIL** | Có bằng chứng account vi phạm ít nhất một điều kiện | Không |
| **UNKNOWN** | Thiếu thông tin cần thiết hoặc kết quả kiểm tra chưa tin cậy | Không; theo dõi riêng |
| **EXCLUDED** | Ngoài phạm vi hoặc không enabled tại thời điểm chốt | Không nằm trong mẫu số |

**Không gộp UNKNOWN vào PASS.** Thiếu mapping, không lấy được kết quả từ ứng dụng đích hoặc dữ liệu stale đều không chứng minh account hợp lệ. Tuy nhiên, cũng không nên gọi mọi UNKNOWN là vi phạm đã được xác nhận.

Nếu mẫu số bằng **0**, tỷ lệ không xác định (**N/A**); không mặc định là 100%. Báo cáo phải nêu rõ thời điểm chốt, múi giờ, độ trễ đồng bộ, phạm vi account, định nghĩa trạng thái enabled và tiêu chí đối với ngoại lệ.

### Định nghĩa khác: tỷ lệ account được quản trị hợp lệ

Một số doanh nghiệp có thể đo **tỷ lệ account đang được quản trị đúng quy trình trên toàn bộ inventory**, bao gồm cả account disabled có biên bản thu hồi và đang trong thời gian lưu trữ được phép. Đây cũng là một chỉ số hợp lý **nếu mẫu số và tiêu chí được định nghĩa lại nhất quán**. Không trộn báo cáo đó với tỷ lệ **account enabled hợp lệ** của bài này: hai tỷ lệ giải đáp các câu hỏi khác nhau.

## 3. Ví dụ tính toán và cách diễn giải

Giả sử doanh nghiệp kiểm kê account enabled trong các ứng dụng CRM, Git và hệ thống dữ liệu:

| Loại account | Tổng trong phạm vi | PASS | FAIL | UNKNOWN |
|---|---:|---:|---:|---:|
| Human (nhân viên, đối tác, nhà thầu) | 160 | 144 | 12 | 4 |
| Non-human (dịch vụ, bot, workload) | 40 | 28 | 8 | 4 |
| **Tổng** | **200** | **172** | **20** | **8** |

Tỷ lệ account hợp lệ là:

\[
R_{\mathrm{valid}}=\frac{172}{200}\times100\%=\boxed{86\%}.
\]

Các tỷ lệ bổ trợ: **FAIL đã xác nhận 10%** (20/200), **UNKNOWN 4%** (8/200). Theo loại account: human **90%** (144/160) và non-human **70%** (28/40). Tỷ lệ chung **86%** là tỷ lệ theo tổng account, không phải trung bình số học của 90% và 70%.

Ví dụ phân loại **20 account FAIL** theo *một nguyên nhân chính duy nhất* để tránh cộng trùng:

| Nguyên nhân chính | Số account | Hướng xử lý |
|---|---:|---|
| Leaver đã hết tư cách nhưng account đích vẫn enabled | 6 | Khoá, xác minh thu hồi phiên/token và log |
| Không truy ra chủ thể hoặc nguồn dữ liệu hợp lệ | 5 | Điều tra account local, mapping, tài khoản tạo ngoài quy trình |
| NHI thiếu owner có trách nhiệm | 4 | Xác nhận owner và mục đích sử dụng |
| Phê duyệt hoặc hợp đồng hết hạn | 3 | Thu hồi hoặc phê duyệt lại theo quy trình |
| Entitlement vượt chính sách RBAC/ABAC | 2 | Thu hồi quyền thừa, kiểm tra SoD |
| **Tổng** | **20** | |

Một account có thể vi phạm **nhiều** điều kiện. Nếu báo cáo chi tiết hiển thị tất cả cờ lỗi thì tổng số lỗi theo nguyên nhân có thể lớn hơn số account FAIL; dashboard phải ghi rõ cách tính. Để đánh giá rủi ro cần xem **cả số lượng tuyệt đối, độ nghiêm trọng và tỷ lệ**, bởi một account đặc quyền bất hợp lệ có thể nguy hiểm hơn hàng chục account ít quyền.

## 4. Tính hợp lệ theo vòng đời Joiner–Mover–Leaver

### 4.1. Joiner: từ xác minh tới cấp quyền

Một nhân viên mới bắt đầu từ bản ghi có thẩm quyền tại HRIS hoặc hệ thống nhân sự tương đương. Quá trình xác minh tạo/liên kết identity tại IdP, áp dụng role khởi tạo và cấp account qua SCIM hoặc API của ứng dụng đích.

Trong quy trình an toàn, account có thể được tạo trước ở trạng thái **pending/disabled**, chỉ kích hoạt khi xác minh danh tính, phê duyệt và gán quyền hoàn tất. Account chưa enabled **chưa nằm trong mẫu số** theo quy ước bài này. Nếu bị bật trước khi đủ thông tin, phải đánh giá là **FAIL** hoặc **UNKNOWN**, thay vì mặc nhiên PASS chỉ vì SCIM báo provisioning thành công.

**Ví dụ biến động:** Ban đầu có 100 account enabled và 95 PASS, tỷ lệ 95%. Kích hoạt thêm 10 account đều hợp lệ thì tỷ lệ mới là \(105/110\approx95{,}45\%\). Nếu 3 trong 10 account mới chưa có bằng chứng phê duyệt thì chỉ có 102 PASS, tỷ lệ \(102/110\approx92{,}73\%\). Số account cùng tăng 10 nhưng chất lượng kiểm soát rất khác nhau.

### 4.2. Mover: một identity, quyền có thể không còn phù hợp

Khi nhân viên chuyển bộ phận hoặc thay đổi nhiệm vụ, account thường vẫn tồn tại. Tuy nhiên role và entitlement cũ cần được rà soát theo chính sách **Role-Based Access Control (RBAC)** và **Attribute-Based Access Control (ABAC)**:

1. HRIS hoặc nguồn quản lý nhân sự phát sự kiện đổi vai trò.
2. IdP cập nhật thuộc tính, nhóm và thông tin tổ chức.
3. IAM đối chiếu quyền cũ với quyền cần có cho vai trò mới.
4. SCIM/API thu hồi quyền không còn phù hợp và cấp quyền mới đã được phê duyệt.
5. Hệ thống đích xác nhận trạng thái thực tế; kiểm tra xung đột phân nhiệm (*Separation of Duties — SoD*).

Nếu một nhân viên chuyển khỏi bộ phận Tài chính nhưng account còn quyền đọc bảng lương, account có thể bị đánh giá **FAIL về entitlement**, dù nhân viên vẫn đang active. Vì vậy, số identity không đổi nhưng tỷ lệ account hợp lệ có thể giảm khi Mover không được xử lý hết.

### 4.3. Leaver: vô hiệu hóa IdP chưa bảo đảm account đích đã bị thu hồi

Khi nhân viên nghỉ việc, hệ thống nguồn phát Leaver; IdP ngừng đăng nhập tập trung; SCIM/provisioning hoặc API gửi yêu cầu khoá/xóa account; application phải áp dụng kết quả. Các lỗi thường gặp gồm tài khoản local không đi qua SSO, connector SCIM lỗi, token/API key còn hiệu lực hoặc đồng bộ bị chậm.

Một account vẫn **enabled ở hệ thống đích** sau khi chủ thể không còn tư cách là **FAIL**, ngay cả khi IdP đã disabled identity. Khi account đích đã bị khóa thực sự, nó ra khỏi mẫu số enabled; sự kiện khắc phục vẫn phải được lưu để kiểm toán.

Ví dụ có 50 account thuộc các Leaver cần thu hồi, 48 đã disabled và 2 còn enabled. Hai account còn enabled phải được điều tra và khắc phục. **Tỷ lệ thu hồi account Leaver đúng SLA** là một chỉ số khác, với mẫu số là account **cần thu hồi trong kỳ**, không được thay mẫu số của valid account ratio bằng 50.

## 5. Thu thập dữ liệu từ IdP, SSO, SCIM và các ứng dụng

Một dashboard IAM chính xác cần kiểm chứng ít nhất hai mặt: **chủ thể có còn tư cách** và **account tại ứng dụng đích đang ở trạng thái/quyền nào**.

~~~mermaid
flowchart TD
    A[HRIS / nguồn đối tác] --> D[Kho identity chuẩn]
    B[Service registry / CMDB] --> D
    C[IdP và thuộc tính danh tính] --> D
    C --> E[SSO / SCIM / API provisioning]
    E --> F[Inventory account hệ thống đích]
    D --> G[Đối chiếu account - identity]
    F --> G
    H[RBAC / ABAC / access review / approval] --> G
    G --> I[PASS / FAIL / UNKNOWN]
    I --> J[Dashboard theo snapshot]
    I --> K[Điều tra, thu hồi, bằng chứng kiểm toán]
~~~

| Nguồn | Dữ liệu sử dụng | Giới hạn cần kiểm soát |
|---|---|---|
| HRIS, hợp đồng, registry đối tác | Joiner, Mover, Leaver, tư cách hợp lệ | Không đại diện đầy đủ cho NHI |
| IdP | Identity, thuộc tính, trạng thái, nhóm | Không bảo đảm account local ở ứng dụng đã bị khóa |
| SSO | Dấu vết xác thực tập trung | Không bao phủ mọi API key và local login |
| SCIM/provisioning | Yêu cầu cấp, thay đổi, thu hồi account | Cần xác nhận kết quả ở hệ thống đích |
| Ứng dụng đích | Account ID, enabled, entitlement, thời gian hoạt động | Có thể tồn tại nhiều account cho cùng identity |
| Service registry/CMDB | Owner, workload, mục đích, môi trường | Thiếu owner là nguy cơ quản trị NHI |
| Approval và access review | Bằng chứng quyền còn được phép | Quyền thực tế có thể lệch quyết định đã phê duyệt |

**Khóa liên kết:** không mặc định email, display name hoặc username là khóa định danh chuẩn vì chúng có thể thay đổi hoặc tái sử dụng. Với từng account, nên lưu **system_id**, **tenant_id**, **account_id**, **canonical_identity_id**, nguồn mapping và độ tin cậy của liên kết. Đối với SCIM, trường **externalId** có thể hỗ trợ liên kết nếu hệ thống triển khai và quản lý tính duy nhất đúng quy ước.

**Thời gian hiệu lực:** một Leaver có hiệu lực lúc 17:00 nhưng snapshot account lấy lúc 16:50 sẽ không thể đánh giá từ dữ liệu không đồng bộ như thể cả hai cùng thời điểm. Nên dùng cùng thời điểm đối soát, lưu dấu thời gian từ từng nguồn, định nghĩa độ trễ chấp nhận được và phân loại UNKNOWN khi thiếu dữ liệu thiết yếu.

## 6. Mô hình dữ liệu và SQL minh họa

Giả sử tổ chức có hai bảng snapshot đã chuẩn hóa:

- **iam_account_snapshot**: một hàng cho mỗi account tại mỗi ngày, khóa duy nhất **(snapshot_date, system_id, tenant_id, account_id)**; gồm **in_scope**, **enabled**, **account_kind** (**human**/**service**), **canonical_identity_id**, **responsible_team_id**, **business_approval_valid**, **entitlements_policy_valid**, **review_current**, **account_not_expired**.
- **iam_identity_snapshot**: mỗi identity chuẩn một hàng tại ngày chốt, gồm **canonical_identity_id**, **lifecycle_state**, **source_verified**.

Truy vấn PostgreSQL sau tính số lượng account enabled và account có **bằng chứng PASS đầy đủ**:

~~~sql
WITH assessed AS (
    SELECT
        a.snapshot_date,
        a.system_id,
        a.tenant_id,
        a.account_id,
        CASE
            WHEN a.canonical_identity_id IS NOT NULL
             AND i.canonical_identity_id IS NOT NULL
             AND i.lifecycle_state = 'active'
             AND i.source_verified IS TRUE
             AND a.account_kind IN ('human', 'service')
             AND (
                 a.account_kind = 'human'
                 OR a.responsible_team_id IS NOT NULL
             )
             AND a.business_approval_valid IS TRUE
             AND a.entitlements_policy_valid IS TRUE
             AND a.review_current IS TRUE
             AND a.account_not_expired IS TRUE
            THEN TRUE
            ELSE FALSE
        END AS verified_valid
    FROM iam_account_snapshot AS a
    LEFT JOIN iam_identity_snapshot AS i
      ON i.snapshot_date = a.snapshot_date
     AND i.canonical_identity_id = a.canonical_identity_id
    WHERE a.snapshot_date = DATE '2026-11-22'
      AND a.in_scope IS TRUE
      AND a.enabled IS TRUE
)
SELECT
    snapshot_date,
    COUNT(*) AS enabled_accounts,
    COUNT(*) FILTER (WHERE verified_valid) AS valid_accounts,
    COUNT(*) FILTER (WHERE NOT verified_valid) AS not_verified_valid,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE verified_valid)
        / NULLIF(COUNT(*), 0),
        2
    ) AS valid_ratio_pct
FROM assessed
GROUP BY snapshot_date;
~~~

**Điều kiện sử dụng:** bảng phải có khóa duy nhất và mapping một identity duy nhất cho mỗi account ở một thời điểm. Nếu join bị nhân bản, **COUNT(*)** sẽ cho kết quả sai. Các cột boolean phải được đánh giá từ chứng cứ và chính sách tổ chức; không được đặt mặc định TRUE chỉ để “đủ dữ liệu”. Account không có chứng cứ bị loại khỏi tử số như truy vấn trên.

Truy vấn cố ý gộp **FAIL và UNKNOWN** trong cột **not_verified_valid**. Hệ thống thật cần lưu trạng thái ba mức cùng mã nguyên nhân riêng; việc gộp ở truy vấn minh họa không cho phép kết luận tất cả account chưa PASS đều vi phạm. Nếu không có account enabled trong phạm vi, **NULLIF** giữ tỷ lệ là NULL, tức N/A.

Phát hiện trùng account trước khi tính:

~~~sql
SELECT
    snapshot_date, system_id, tenant_id, account_id,
    COUNT(*) AS duplicate_rows
FROM iam_account_snapshot
GROUP BY snapshot_date, system_id, tenant_id, account_id
HAVING COUNT(*) > 1;
~~~

Nếu có kết quả, phải điều tra việc nhập dữ liệu hoặc bản ghi nhiều phiên bản. Không sử dụng DISTINCT tùy tiện để che lỗi nguồn. Ngoài ra, truy vấn mẫu chỉ mô tả **human/service thông thường**; account break-glass, tài khoản chia sẻ có phê duyệt đặc biệt hoặc NHI nhạy cảm cần quy tắc kiểm chứng bổ sung, không nên ép kiểu để đạt PASS.

## 7. Đọc xu hướng và kiểm soát độ bao phủ

Tỷ lệ 98% không tự chứng minh IAM an toàn nếu 2% còn lại là tài khoản đặc quyền, hoặc dashboard chỉ kiểm kê được một phần ứng dụng. Nên theo dõi đồng thời:

| Chỉ số bổ trợ | Vai trò |
|---|---|
| **Số account enabled trong phạm vi** | Nhận biết thay đổi mẫu số qua từng kỳ |
| **Số FAIL và UNKNOWN tuyệt đối** | Tách vi phạm đã xác nhận khỏi thiếu bằng chứng |
| **Tỷ lệ mapping account–identity đầy đủ** | Tìm account local, orphan hoặc lỗi liên kết |
| **Account Leaver còn enabled quá SLA** | Phản ánh truy cập tồn dư do thu hồi trễ |
| **NHI không có owner hoặc không được tái chứng nhận** | Kiểm soát bot, service và workload |
| **Thời gian khắc phục FAIL** | Theo dõi backlog và hiệu quả vận hành |
| **Tỷ lệ bao phủ ứng dụng/account inventory** | Tránh đánh giá tốt giả do thiếu dữ liệu |
| **Số quyền đặc quyền sai chính sách, SoD conflicts** | Phản ánh mức nghiêm trọng của sai lệch |

Nên phân tách theo tenant, ứng dụng, production/test, human/NHI, nhóm đặc quyền và đơn vị. Khi tích hợp thêm hệ thống legacy, tỷ lệ có thể giảm vì **phát hiện được nhiều account chưa kiểm soát**, không nhất thiết vì quy trình mới kém hiệu quả. Công bố thay đổi phạm vi cùng kết quả giúp so sánh công bằng.

Ngưỡng cảnh báo phải dựa trên mức độ quan trọng của từng ứng dụng, SLA thu hồi, chính sách rủi ro và lịch sử phát hiện. Không tồn tại một ngưỡng 95% hay 99% chung bắt buộc cho mọi tổ chức. Một account admin của Leaver đang hoạt động cần được ưu tiên điều tra ngay cả khi tỷ lệ tổng chỉ giảm rất ít.

## 8. Xử lý account FAIL/UNKNOWN và lưu dấu kiểm toán

Với một account bị đánh dấu, quy trình xử lý cần đi qua các bước:

1. **Xác minh dữ liệu:** đọc lại trạng thái account tại ứng dụng đích, thời điểm chốt, nguồn định danh, quyền và các ngoại lệ.
2. **Phân loại:** xác định FAIL hay UNKNOWN, mức độ truy cập, tính đặc quyền, ảnh hưởng sản xuất và SLA áp dụng.
3. **Chọn biện pháp:** thu hồi account Leaver; xóa quyền thừa sau Mover; bổ sung owner cho service hợp lệ; điều tra account local/orphan; xử lý lỗi SCIM.
4. **Thực thi có kiểm soát:** account dịch vụ có thể đòi hỏi xoay vòng credential và thay thế tích hợp trước khi khóa; tài khoản rủi ro cao phải ưu tiên giảm khả năng truy cập thực tế.
5. **Xác nhận trên hệ thống đích:** kiểm tra trạng thái account, các token/API key hoặc phiên liên quan theo khả năng của hệ thống; gửi lệnh disable thành công **chưa đủ**.
6. **Lưu bằng chứng:** ID account/identity, mã lỗi, nguồn, thời gian, người chịu trách nhiệm, biện pháp, phê duyệt ngoại lệ, kết quả xác nhận và thời điểm đóng.

Ví dụ audit record:

| Trường | Giá trị minh họa |
|---|---|
| Account | **crm/prod/acc-0412** |
| Identity | **employee-247** |
| Phát hiện | **FAIL: LEAVER_STILL_ENABLED** |
| Nguồn | HRIS cho biết đã nghỉ, CRM snapshot vẫn enabled |
| Hành động | Vô hiệu hóa tại CRM, thu hồi khả năng truy cập còn hiệu lực |
| Xác nhận | Readback CRM disabled; lưu log và người phê duyệt |
| Theo dõi | Owner xử lý, deadline và mã sự cố |

Chính khả năng truy từ con số tổng **đến từng account, căn cứ đánh giá và trạng thái khắc phục** làm cho chỉ số IAM hữu ích trong kiểm toán. Giữ lại bản ghi các account đã disabled hoặc xóa theo chính sách lưu trữ bằng chứng, không xóa dấu vết chỉ để cải thiện tỷ lệ.

## 9. Những lỗi thường gặp

1. **Lấy tổng identity làm mẫu số:** một identity có thể có nhiều account, làm sai đơn vị đo.
2. **Coi enabled nghĩa là hợp lệ:** chưa chứng minh được tư cách, owner, mục đích, phê duyệt và quyền.
3. **Coi không đăng nhập lâu ngày là mặc nhiên FAIL:** sự thiếu hoạt động là tín hiệu rà soát; service chạy theo lịch hoặc account dự phòng có thể hợp lệ.
4. **Chỉ đọc trạng thái IdP:** có thể bỏ sót local login, key/API, tài khoản trên ứng dụng không tích hợp SSO/SCIM.
5. **Xem NHI không có HRIS là tài khoản mồ côi:** service identity cần registry và service owner riêng.
6. **Tính UNKNOWN thành PASS:** dữ liệu thiếu chưa thể xác minh quyền truy cập còn được phép.
7. **Không kiểm soát dữ liệu trùng và thời điểm snapshot:** tính sai mẫu số hoặc tạo biến động giả.
8. **Chỉ nhìn phần trăm tổng:** bỏ sót ứng dụng trọng yếu, đặc quyền, số lượng FAIL thực và độ bao phủ nguồn.
9. **Không lưu bằng chứng thu hồi:** không thể chứng minh sự cố đã được xử lý ở ứng dụng đích.
10. **Đổi chính sách giữa các kỳ nhưng vẫn so sánh trực tiếp:** tỷ lệ không còn cùng định nghĩa.

## 10. Tình huống tự kiểm tra

**Câu 1.** Có 400 account enabled thuộc phạm vi: 350 PASS, 30 FAIL, 20 UNKNOWN. Tỷ lệ account hợp lệ bằng bao nhiêu? **Đáp án:** 350/400 × 100% = **87,5%**; FAIL 7,5%, UNKNOWN 5%.

**Câu 2.** Nhân viên đã nghỉ, IdP disabled identity nhưng account ERP local vẫn enabled. Account ERP hợp lệ không? **Đáp án:** **Không**; chủ thể hết tư cách và account đích chưa thu hồi. Cần xử lý trực tiếp tại ERP.

**Câu 3.** Một service account không có hồ sơ HRIS, nhưng có identity dịch vụ, owner, phê duyệt, thời hạn và quyền phù hợp. Có thể PASS không? **Đáp án:** **Có**, nếu đáp ứng chính sách NHI tương ứng và có bằng chứng.

**Câu 4.** Nhân viên Mover giữ nguyên account nhưng còn quyền của phòng ban cũ. Số identity có thể không đổi trong khi tỷ lệ account hợp lệ giảm không? **Đáp án:** **Có**; quyền không còn phù hợp làm account FAIL.

**Câu 5.** Sau khi kiểm kê thêm ứng dụng legacy, tỷ lệ hợp lệ giảm mạnh. Có thể kết luận IAM đã yếu đi không? **Đáp án:** **Chưa**. Cần xem thay đổi độ bao phủ, số FAIL/UNKNOWN thực tế, mức độ nghiêm trọng và tiến độ khắc phục.

## Ghi nhớ

Để đo **tỷ lệ account hợp lệ**, hãy thống nhất **account nào nằm trong mẫu số, điều kiện PASS, khóa đếm, thời điểm snapshot và độ bao phủ dữ liệu**. Với định nghĩa account enabled hợp lệ, chỉ account có đầy đủ bằng chứng về identity, tư cách, owner, mục đích, phê duyệt và quyền mới được tính vào tử số. Theo dõi riêng FAIL/UNKNOWN, đối soát IdP–SSO–SCIM với tài khoản thực tế ở ứng dụng đích, và liên kết phát hiện với sự kiện **Joiner–Mover–Leaver**, **RBAC/ABAC**, tài khoản dịch vụ và kiểm toán để giảm quyền truy cập tồn dư.
