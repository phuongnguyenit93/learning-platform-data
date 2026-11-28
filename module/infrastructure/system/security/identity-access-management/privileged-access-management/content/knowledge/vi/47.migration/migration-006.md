# Migrate cloud role

## 1. Mục tiêu và phạm vi

Di chuyển cloud role trong một chương trình Privileged Access Management (PAM) là chuyển cách một người hoặc workload nhận, sử dụng và mất quyền đặc quyền trên cloud từ mô hình cũ sang mô hình được kiểm soát. Công việc này không chỉ là tạo role mới rồi sao chép policy. Một role có thể đã giới hạn quyền tốt nhưng vẫn bị truy cập qua trust quá rộng, credential dài hạn, role chaining hoặc một đường cấp quyền nằm ngoài PAM.

Sau bài học, người học có thể:

- Kiểm kê đầy đủ role, quyền, đối tượng được nhận quyền và các hệ thống phụ thuộc.
- Phân biệt permission, trust, assignment, session và giới hạn tổ chức khi lập phương án di chuyển.
- Thiết kế role đích theo least privilege cho quản trị viên và workload.
- Chạy pilot, kiểm thử quyền dương và quyền âm, thực hiện cutover theo từng đợt.
- Thu hồi đường truy cập cũ, kiểm tra phiên còn sống và lưu bằng chứng phục vụ kiểm toán.
- Rollback theo từng nhóm người dùng hoặc workload mà không khôi phục vô điều kiện các đặc quyền cũ.

Trong bài này, “cloud role” được dùng theo nghĩa tổng quát. Các nhà cung cấp có mô hình khác nhau: có nền tảng dùng role gắn permission policy và trust policy; có nền tảng dùng role definition cùng role assignment tại một scope; có nền tảng gán một role cho principal qua policy binding. Không nên coi tên gọi tương tự là những đối tượng có ngữ nghĩa giống nhau.

Các mẫu YAML và mã giả trong bài dùng để diễn tả thiết kế, không phải cấu hình có thể áp dụng trực tiếp vào một nhà cung cấp cụ thể.

## 2. Xác định đang di chuyển điều gì

Một dự án có thể mang tên “migrate role” nhưng thực tế thuộc nhiều loại thay đổi.

| Loại thay đổi | Ví dụ | Rủi ro chính |
|---|---|---|
| Thay đường xác thực | Từ tài khoản dùng access key sang federation | Đường cũ vẫn còn hoạt động |
| Thay cách cấp quyền | Từ quyền thường trực sang activation có thời hạn | Hết thời gian phê duyệt nhưng assignment chưa bị xóa |
| Tách role | Từ một role quản trị chung thành các role theo tác vụ | Thiếu dependency hoặc giữ lại quyền thừa |
| Thay phạm vi | Từ toàn tổ chức sang một account, subscription hoặc project | Cấp nhầm vào scope cha hoặc scope rộng hơn |
| Thay danh tính workload | Từ khóa của service account sang workload identity | Claim, audience hoặc môi trường triển khai không khớp |
| Thay nền tảng PAM | Chuyển broker hoặc hệ thống phê duyệt | Hai hệ thống cùng có quyền cấp đặc quyền |
| Chuyển cloud hoặc cấu trúc tổ chức | Từ một mô hình tài nguyên sang mô hình khác | Ánh xạ theo tên nhưng sai ngữ nghĩa quyền |

Phải ghi rõ những loại thay đổi nào được thực hiện trong đợt hiện tại. Nếu vừa đổi identity provider, policy, phân vùng môi trường và công cụ triển khai, khi có lỗi sẽ khó xác định nguyên nhân.

Một baseline tốt trả lời được:

1. Ai đang có khả năng nhận role?
2. Ai đã thực sự sử dụng role và cho tác vụ nào?
3. Role có thể tác động tới tài nguyên nào?
4. Đường nào có thể tiếp tục cấp hoặc khôi phục quyền cũ?
5. Điều kiện nào chứng minh quá trình chuyển đổi đã hoàn tất?

Việc di chuyển thành công phải thể hiện bằng hành vi truy cập và khả năng thu hồi, không chỉ bằng sự tồn tại của role đích.

## 3. Mô hình hóa quyền hiệu lực

### 3.1. Năm thành phần cần tách riêng

**Principal** là người dùng, nhóm, danh tính dịch vụ hoặc workload muốn thực hiện một hành động.

**Permission** mô tả hành động và tài nguyên mà role cho phép. Trong một số hệ thống, role chỉ là tập permission; việc gán role mới đưa quyền đến principal.

**Trust hoặc federation relationship** xác định ai có thể nhận hoặc mạo danh danh tính đó, từ issuer nào, với claim và điều kiện nào. Không phải nền tảng nào cũng gắn trust trực tiếp vào role.

**Assignment hoặc binding** nối principal với role tại một scope và có thể kèm điều kiện, thời hạn hoặc cơ chế activation.

**Session hoặc token** là vật mang quyền được sử dụng sau khi cấp quyền. Vòng đời của token có thể không trùng với vòng đời request, approval hoặc assignment.

Ngoài các thành phần trên, quyền hiệu lực còn chịu ảnh hưởng của policy ở tổ chức, tài nguyên, permission boundary, deny policy, mạng, thiết bị và các cơ chế khác tùy nền tảng.

Có thể dùng mô hình tư duy:

~~~text
Yêu cầu truy cập
    |
    v
Xác minh principal và nguồn danh tính
    |
    v
Kiểm tra trust / binding / assignment
    |
    v
Đánh giá permission + scope + condition + policy liên quan
    |
    v
Cấp hoặc sử dụng token / session
    |
    v
Tài nguyên đích quyết định cho phép hay từ chối
~~~

Đây không phải công thức đánh giá policy dùng chung cho mọi cloud. Thứ tự, cách kết hợp allow/deny và hành vi cache phải được xác nhận theo nền tảng được triển khai.

### 3.2. JIT cấp quyền khác với token ngắn hạn

Just-in-time (JIT) cấp đặc quyền trong một khoảng thời gian hoặc một nhu cầu cụ thể. Token ngắn hạn làm giảm thời gian tồn tại của vật mang quyền. Hai cơ chế bổ sung cho nhau nhưng không thay thế nhau.

Một role cho phép nhận token ngắn hạn liên tục, không cần activation, vẫn có thể tạo ra quyền truy cập thường trực trên thực tế. Ngược lại, một approval hết hạn sau 20 phút không bảo đảm token đã được cấp cũng hết hiệu lực sau 20 phút.

Cần quản lý ít nhất các mốc:

- Thời điểm request được phê duyệt.
- Thời điểm assignment hoặc activation bắt đầu và kết thúc.
- Thời điểm từng token được phát hành và hết hạn.
- Khả năng đổi, làm mới hoặc nhận tiếp token.
- Độ trễ truyền policy và độ trễ thực thi thu hồi.
- Các phiên hoặc kết nối lâu dài đã thiết lập với dịch vụ đích.

Khi thiết kế thời hạn, không chỉ lấy con số nhỏ nhất rồi cho rằng đã có hiệu lực. Phải kiểm tra hệ thống phát token có thực sự giới hạn thời gian còn lại của activation hay không. Nếu không hỗ trợ, cần chọn token lifetime, khoảng đệm và cơ chế kết thúc phiên phù hợp với rủi ro.

## 4. Kiểm kê role và các đường truy cập

### 4.1. Những dữ liệu cần thu thập

Với mỗi role nguồn, lập hồ sơ tối thiểu:

| Nhóm dữ liệu | Nội dung |
|---|---|
| Định danh | ID bất biến của role, tên hiển thị, môi trường, scope |
| Chủ sở hữu | Chủ dịch vụ, chủ dữ liệu, nhóm IAM, người phê duyệt |
| Người và máy sử dụng | User, group, service principal, workload, bên thứ ba |
| Quyền | Policy trực tiếp, policy kế thừa, quyền dữ liệu và quyền quản trị |
| Trust và binding | Issuer, principal được tin cậy, claim, điều kiện, scope |
| Phiên | Thời hạn token, khả năng renewal, role chaining, kết nối dài hạn |
| Dependency | Pipeline, scheduler, script, SDK, template hạ tầng, đường khôi phục |
| Dấu vết sử dụng | Tác vụ đã chạy, tài nguyên đã chạm, lỗi bị từ chối |
| Đường vòng | Credential cũ, nhóm khác, role dự phòng, quyền cấp hoặc mạo danh role |
| Ràng buộc | Giới hạn tổ chức, vùng, mạng, thiết bị, lịch vận hành |

Không suy ra rằng một role không cần thiết chỉ vì không thấy hoạt động trong một cửa sổ log ngắn. Tác vụ theo quý, phục hồi thảm họa, failover hoặc xử lý sự cố có thể chưa xuất hiện. Kết hợp log, cấu hình, lịch chạy và xác nhận của owner.

### 4.2. Quan hệ phụ thuộc quan trọng hơn danh sách role

Ví dụ một pipeline triển khai có thể đi qua chuỗi:

~~~text
CI workload
  -> danh tính federation
  -> role triển khai tại môi trường production
  -> khả năng gán danh tính runtime cho ứng dụng
  -> ứng dụng truy cập dữ liệu và khóa mã hóa
~~~

Pipeline có thể không trực tiếp đọc dữ liệu nhưng có quyền gán hoặc thay đổi một danh tính có thể đọc dữ liệu. Khi đó, chỉ kiểm tra danh sách hành động trực tiếp của role sẽ đánh giá thấp đặc quyền.

Cần nhận diện các quyền bắc cầu như:

- Tạo hoặc sửa role, policy, assignment và binding.
- Thay trust hoặc cấu hình nguồn federation.
- Mạo danh principal hoặc gán danh tính cho compute.
- Sửa pipeline, artifact, bootstrap hoặc cấu hình ứng dụng đặc quyền.
- Đọc, thay hoặc sử dụng secret, khóa mã hóa và credential.
- Tắt hoặc sửa audit log, cảnh báo và lưu trữ bằng chứng.

Các quyền này không phải lúc nào cũng tạo được đường leo thang trong mọi cấu hình. Phân tích theo tài nguyên đích, điều kiện đi kèm và các quyền khác mà cùng principal đang sở hữu.

### 4.3. Baseline phải bao gồm cách cấu hình được duy trì

Xóa một assignment bằng thao tác thủ công có thể chỉ có hiệu lực tới lần chạy tiếp theo của Terraform, công cụ đồng bộ nhóm hoặc reconciler nội bộ.

Trước khi cutover, xác định nguồn cấu hình có thẩm quyền:

- Hạ tầng được quản lý trong repository nào?
- Hệ thống nào tự động tạo lại role hoặc assignment?
- Có job đồng bộ từ directory hoặc ticketing không?
- Pipeline nào có quyền sửa IAM?
- Ai có thể thay policy ngoài quy trình?

Thay đổi phải được phản ánh tại nguồn cấu hình và kiểm chứng trên cloud thực tế. Một plan hợp lệ không chứng minh trạng thái đang chạy đã đúng; ngược lại, trạng thái hiện tại đúng cũng không chứng minh nó sẽ được giữ nguyên sau lần reconcile tiếp theo.

## 5. Thiết kế role đích theo least privilege

### 5.1. Ánh xạ theo tác vụ và tài nguyên

Không ánh xạ chỉ bằng tên như “AdminOld” thành “AdminNew”. Một role quản trị cũ có thể chứa nhiều mục đích cần tách:

| Nhu cầu cũ | Hướng thiết kế đích | Ranh giới cần kiểm tra |
|---|---|---|
| Xem trạng thái production | Role quan sát | Không đọc secret hoặc nội dung dữ liệu nhạy cảm ngoài nhu cầu |
| Khởi động lại dịch vụ | Role vận hành có activation | Không tự sửa IAM hoặc danh tính runtime |
| Triển khai phiên bản | Role dành cho pipeline | Giới hạn môi trường, artifact và tài nguyên |
| Thay IAM | Role quản trị danh tính riêng | Phê duyệt độc lập và bằng chứng thay đổi |
| Khôi phục khẩn cấp | Đường break-glass riêng | Kiểm tra định kỳ, giới hạn và cảnh báo mọi lần dùng |

Các ranh giới trên là mục tiêu thiết kế. Phải kiểm thử cụ thể vì một hành động tưởng hẹp có thể mở ra đặc quyền khác. Ví dụ quyền triển khai mã vào một dịch vụ đang chạy với danh tính mạnh có thể cho phép mã đó sử dụng quyền runtime.

Nếu nền tảng không hỗ trợ điều khiển ở độ chi tiết mong muốn, có thể giới hạn thêm bằng scope, tài nguyên trung gian, approval, môi trường thực thi và giám sát. Không mô tả một giới hạn là đã được cưỡng chế nếu nó chỉ tồn tại trong tài liệu quy trình.

### 5.2. Tách truy cập con người và workload

Đối với con người:

- Dùng danh tính cá nhân để giữ khả năng quy trách nhiệm.
- Yêu cầu xác thực phù hợp với mức đặc quyền, có thể gồm MFA và tín hiệu thiết bị.
- Gắn activation với mục đích, ticket, scope và thời hạn.
- Tách người yêu cầu và người phê duyệt cho tác vụ cần phân tách trách nhiệm.
- Giới hạn khả năng chuyển tiếp sang role hoặc danh tính khác.

Đối với workload:

- Dùng danh tính workload hoặc cơ chế federation phù hợp nếu nền tảng hỗ trợ.
- Giới hạn issuer, audience, subject và claim liên quan tới repository, môi trường hoặc service cụ thể.
- Phân biệt workload production và non-production.
- Không áp dụng luồng MFA tương tác của người dùng cho một job tự động.
- Kiểm soát credential bootstrap và quyền sửa cấu hình federation.
- Có owner, lịch rà soát và cơ chế kết thúc quyền khi workload bị ngừng sử dụng.

Không cấp workload một role con người chỉ để thuận tiện. Ngược lại, không cho quản trị viên dùng danh tính workload làm lối đi vòng approval.

### 5.3. Trust đích là một phần của thay đổi quyền

Một permission policy rất hẹp vẫn có thể gây rủi ro nếu bất kỳ workload nào từ cùng một tổ chức đều có thể nhận role.

Với federation, cần xác minh:

1. Nguồn phát token nào được tin cậy?
2. Token được cấp cho đối tượng nhận nào?
3. Subject hoặc tập claim có định danh đủ chặt workload không?
4. Claim có do bên phát token bảo đảm hay do người gọi tự cung cấp?
5. Những ai có thể sửa repository, nhánh, môi trường hoặc định nghĩa job mà trust đang dựa vào?
6. Có đường dùng token từ môi trường thử nghiệm để nhận quyền production không?

Không dùng email, nhãn hoặc tên dễ đổi làm bằng chứng duy nhất cho danh tính nếu nền tảng có định danh ổn định và claim đáng tin cậy phù hợp hơn. Không giả định session tag hay thuộc tính truyền từ người gọi đã được xác minh ở mọi bước.

## 6. Lập manifest và tiêu chí chấp nhận

Manifest giúp nhóm triển khai đối chiếu từng role nguồn với thiết kế đích. Nó là hồ sơ thiết kế, không chứa token hoặc secret.

~~~yaml
migration:
  id: pam-cloud-wave-03
  environment: production
  source:
    roleRef: legacy-prod-operations
    scopeRef: payments-production
    configurationOwner: platform-iam
  target:
    roleRef: payments-operations-jit
    permissionProfile: restart-and-observe
    scopeRef: payments-production
    accessClass: human
    activation:
      requestedMinutes: 20
      approvalRequired: true
      independentApprover: true
    session:
      requestedMaximumMinutes: 15
      refreshAfterActivationEnds: false
      terminationBehavior: must-be-verified
  dependencies:
    - scheduled-maintenance
    - incident-runbook
  validation:
    positive:
      - observe-service-health
      - restart-approved-service
    negative:
      - change-iam-assignment
      - read-production-secret
      - access-nonapproved-scope
  cutover:
    owner: platform-operations
    evidenceRef: pam-cloud-wave-03-evidence
    rollbackUnit: service-and-principal-cohort
~~~

Các trường thời gian chỉ ghi ý định thiết kế. Trước khi triển khai phải đối chiếu với giới hạn thực tế của nhà cung cấp, cơ chế PAM và dịch vụ đích. Nếu không thực thi được, cần sửa thiết kế hoặc ghi rõ kiểm soát bù và rủi ro đã được chấp thuận.

Tiêu chí chấp nhận phải đo được. Ví dụ:

- Principal trong pilot hoàn thành các tác vụ vận hành đã xác định.
- Principal ngoài pilot không nhận được role mới.
- Activation production không tự phê duyệt.
- Token không thể được nhận mới sau khi activation kết thúc.
- Hành vi của token đã cấp và phiên dài hạn được kiểm tra, có thời hạn dư được ghi nhận.
- Quyền IAM, đọc secret và scope ngoài kế hoạch bị từ chối.
- Audit event truy ngược được về đúng người hoặc workload.
- Assignment cũ bị gỡ tại nguồn cấu hình và trên cloud, không tự xuất hiện lại.
- Có đường khẩn cấp đã được kiểm chứng nếu dịch vụ PAM không sẵn sàng.

Mỗi tiêu chí cần người chịu trách nhiệm, phép thử và bằng chứng. Các ngưỡng thời gian được chọn theo rủi ro của hệ thống, không lấy một bộ số cố định làm tiêu chuẩn cho mọi môi trường.

## 7. Chuẩn bị pilot và kiểm thử

### 7.1. Chọn pilot có tính đại diện

Pilot không nên chỉ gồm role chỉ đọc dễ chuyển. Nên có đại diện cho các đường chính:

- Một nhóm người dùng có activation tương tác.
- Một workload chạy định kỳ.
- Một pipeline có federation.
- Một trường hợp truy cập chéo ranh giới account, project hoặc tenant nếu có.
- Một tác vụ ít xảy ra nhưng quan trọng như bảo trì hoặc phục hồi.

Tập pilot phải đủ nhỏ để kiểm soát tác động. Những nhóm khác tiếp tục theo kế hoạch hiện tại cho tới khi được giao lịch chuyển rõ ràng.

### 7.2. Ma trận kiểm thử

| Nhóm kiểm thử | Cách quan sát | Kết quả cần đạt |
|---|---|---|
| Tác vụ được phép | Chạy bằng principal và scope pilot | Thành công, có audit |
| Tác vụ ngoài nhu cầu | Gọi hành động không nằm trong hồ sơ quyền | Bị từ chối |
| Sai principal | Dùng danh tính ngoài nhóm được phép | Không nhận được quyền |
| Sai claim hoặc issuer | Dùng trường hợp âm có kiểm soát | Không được chấp nhận |
| Sai môi trường | Workload thử nghiệm yêu cầu role production | Bị từ chối |
| Hết activation | Thử nhận token mới | Không được cấp mới |
| Token đã tồn tại | Thử hành động trước và sau mốc thu hồi | Khớp hành vi và thời hạn đã thiết kế |
| Phiên dài hạn | Giữ kết nối qua mốc hết hạn | Hành vi được xác minh riêng |
| Role chaining hoặc mạo danh | Thử đường chuyển sang danh tính khác | Chỉ đường đã phê duyệt hoạt động |
| PAM hoặc IdP gián đoạn | Thực hiện bài diễn tập giới hạn | Kiểm soát truy cập và khôi phục theo thiết kế |
| Reconcile cấu hình | Chạy quy trình quản lý cấu hình | Không phục hồi assignment cũ |

Policy simulator hoặc công cụ phân tích tĩnh giúp phát hiện lỗi nhưng không thay thế thử nghiệm trên đường truy cập thật. Chúng có thể không bao quát mọi resource policy, điều kiện động, cache hoặc hành vi của dịch vụ đích.

Kiểm thử quyền âm phải sử dụng tài nguyên thử nghiệm và thao tác không gây thiệt hại. Không cần đọc dữ liệu nhạy cảm thật để chứng minh rằng quyền đọc dữ liệu đã bị từ chối.

### 7.3. Bằng chứng cần giữ

Mỗi phép thử nên lưu:

- ID kế hoạch, role nguồn và role đích.
- Phiên bản hoặc fingerprint của cấu hình policy và trust.
- Principal thực hiện, scope và thời gian theo nguồn đồng hồ được thống nhất.
- Request, approval và activation tương ứng.
- Kết quả gọi API hoặc thao tác quản trị đã được làm sạch dữ liệu nhạy cảm.
- Audit event ID, session ID hoặc correlation ID nếu có.
- Kết quả mong đợi, kết quả thực tế và quyết định xử lý.

Một mã HTTP hoặc một dòng “AccessDenied” riêng lẻ chưa chứng minh role mới đúng. Nó có thể xuất phát từ mạng, sai tài nguyên hoặc một policy khác. Phải đối chiếu danh tính, yêu cầu và policy hiệu lực của đúng trường hợp kiểm thử.

## 8. Cutover theo từng đợt

Một quy trình thực tế có thể gồm các bước sau.

### Bước 1: Chốt baseline và cửa sổ thay đổi

Ghi nhận cấu hình hiện tại, danh sách dependency, owner và cách truy cập khẩn cấp. Chốt nguồn cấu hình có thẩm quyền và cơ chế phát hiện drift. Nếu có thay đổi đồng thời vào IAM, phải đưa vào cùng quy trình hoặc tạm giới hạn chúng trong cửa sổ cutover.

Không vô hiệu hóa audit để giảm nhiễu trong đợt chuyển đổi.

### Bước 2: Tạo và kiểm tra đường đích

Tạo role, trust, binding, workflow activation và log phù hợp. Ban đầu chỉ cho nhóm pilot hoặc workload đã chọn sử dụng. Kiểm tra quyền thực tế của tài khoản hoặc automation thực hiện migration; không cấp cho công cụ migration quyền quản trị toàn tổ chức lâu dài chỉ vì nó cần tạo một số assignment.

### Bước 3: Chuyển một đơn vị rollback

Với người dùng, chuyển một nhóm principal và một scope xác định. Với workload, cập nhật cấu hình nhận danh tính, tham chiếu role hoặc cơ chế token cho đúng deployment.

Sau cập nhật, phải chứng minh tác vụ đang dùng danh tính mới. Một job chạy thành công có thể vẫn đang dùng credential cũ do thứ tự lựa chọn credential của SDK, cache, biến môi trường hoặc cấu hình còn sót.

### Bước 4: Quan sát và đối chiếu

Theo dõi lỗi xác thực, lỗi phân quyền, số lần activation, các quyền nhạy cảm và audit correlation. So sánh với lịch tác vụ thực, kể cả job theo lịch chưa chạy ngay sau triển khai.

Không tự động bổ sung wildcard permission khi gặp một lỗi từ chối. Tìm hành động, tài nguyên, principal và điều kiện gây lỗi; xác định nhu cầu rồi mới chỉnh phạm vi nhỏ nhất cần thiết.

### Bước 5: Ngăn cấp mới qua đường nguồn

Tùy nền tảng và mô hình, có thể phải gỡ binding cũ, thay trust, khóa khả năng nhận role hoặc vô hiệu hóa credential dài hạn. Các hành động phải được lựa chọn theo cơ chế thực tế, có kiểm thử và có owner.

Mục tiêu ở bước này là không phát sinh thêm quyền qua đường cũ. Chưa được kết luận rằng mọi token hoặc phiên đã tồn tại đều chấm dứt.

### Bước 6: Xử lý token, phiên và kết nối cũ

Xác định những token đã được cấp, khả năng revoke, thời hạn còn lại và các dịch vụ vẫn chấp nhận chúng. Khi có chức năng thu hồi, phải kiểm tra phạm vi áp dụng và hiệu quả đối với đúng loại token.

Nếu không thể thu hồi ngay, cần chặn nhận mới, áp dụng biện pháp hạn chế phù hợp nếu có, theo dõi tới khi hết thời gian dư và xác minh không còn sử dụng. Với đặc quyền rủi ro cao, thời gian dư không chấp nhận được có thể là lý do chưa cho phép cutover.

Đổi trust hoặc xóa role không được mặc định là cách vô hiệu hóa tức thì mọi token và kết nối đã cấp.

### Bước 7: Dọn đường cũ và chốt đợt

Loại bỏ tham chiếu cũ trong pipeline, script, tài liệu vận hành và cấu hình. Gỡ nhóm hoặc assignment không còn cần; xử lý credential, secret và quyền automation migration theo kế hoạch.

Sau một chu kỳ reconcile, kiểm tra đường cũ không được tạo lại. Giữ bản cấu hình và bằng chứng theo thời hạn lưu trữ đã xác định, nhưng không giữ credential hoạt động để làm “backup”.

Chỉ mở đợt kế tiếp khi tiêu chí của đợt hiện tại đạt hoặc những tồn tại đã có quyết định xử lý rõ ràng.

## 9. Đồng tồn tại và rollback có kiểm soát

### 9.1. Đồng tồn tại phải có giới hạn

Trong pilot, đường cũ và mới có thể cùng tồn tại trong một khoảng thời gian. Điều đó tạo ra nguy cơ quyền hiệu lực lớn hơn thiết kế đích.

Ví dụ người dùng đã nhận role mới chỉ cho phép restart nhưng vẫn thuộc nhóm quản trị cũ. Một phép thử restart thành công không chứng minh quyền mới là đủ, và một phép thử đọc secret thành công có thể đến từ nhóm cũ.

Cần xác minh riêng danh tính và đường cấp quyền được dùng trong phép thử. Khi thử quyền âm của role mới, tránh để quyền khác của cùng principal làm sai kết quả; sử dụng principal hoặc phiên kiểm thử có quyền được kiểm soát.

Khoảng đồng tồn tại cần có:

- Mục đích, phạm vi và thời điểm kết thúc.
- Danh sách principal còn dùng đường cũ.
- Cảnh báo cho hoạt động từ đường cũ sau cutover.
- Người có quyền quyết định kéo dài.
- Tiêu chí đóng và bằng chứng thu hồi.

### 9.2. Rollback theo nguyên nhân

Rollback là khôi phục khả năng thực hiện tác vụ cần thiết trong một phạm vi đã xác định. Nó không đồng nghĩa khôi phục toàn bộ đặc quyền cũ.

| Tình huống | Hướng xử lý |
|---|---|
| Thiếu permission cho một tác vụ hợp lệ | Bổ sung tối thiểu qua quy trình hoặc rollback riêng workload |
| Sai claim khiến workload không nhận được role | Sửa trust có kiểm chứng hoặc quay lại cấu hình nhận danh tính của deployment |
| Lỗi dịch vụ PAM | Dùng đường khẩn cấp đã phê duyệt theo runbook |
| Role mới cấp quyền vượt phạm vi | Ngăn nhận mới, xử lý phiên và sửa policy trước khi tiếp tục |
| Credential hoặc role cũ nghi bị lộ | Cô lập và thay credential; không bật lại đường bị nghi ngờ |
| Hệ thống tự tạo lại binding cũ | Sửa nguồn cấu hình và reconciler, rồi xác minh trạng thái |

Một trigger rollback nên cụ thể, chẳng hạn tác vụ production quan trọng bị chặn ngoài thời gian khôi phục cho phép, hoặc mất audit correlation cho đặc quyền. Giá trị ngưỡng do owner quyết định trước cutover.

Mỗi rollback phải ghi lại trạng thái trước và sau, principal được khôi phục quyền, thời hạn ngoại lệ và kế hoạch quay lại role đích. Nếu cần cấp quyền tạm, quyền đó cũng phải có người chịu trách nhiệm và thời điểm thu hồi.

## 10. Ví dụ: chuyển role vận hành production sang PAM

### 10.1. Trạng thái nguồn

Nhóm vận hành dùng một role chung có quyền rộng trên toàn môi trường production. Một nhóm directory có thể nhận role bất kỳ lúc nào. Pipeline triển khai cũng dùng role này qua credential được lưu trong hệ thống CI.

Vấn đề:

- Không tách quản trị viên với pipeline.
- Người dùng có quyền thường trực.
- Một phạm vi bị lỗi hoặc bị xâm nhập có thể ảnh hưởng nhiều dịch vụ.
- Khó phân biệt thao tác con người với automation.
- Credential CI tồn tại lâu hơn một lần chạy.

### 10.2. Thiết kế đích

Tách thành ba đường:

1. Role quan sát dành cho người dùng trong scope dịch vụ.
2. Role vận hành JIT cho các tác vụ đã xác định, cần approval khi vào production.
3. Role triển khai dành riêng cho workload CI, dùng federation và giới hạn trust theo workload và môi trường.

Quản trị IAM vẫn nằm ở đường riêng. Nếu pipeline cần gán danh tính runtime, quyền đó được phân tích riêng để ngăn việc chọn tùy ý một danh tính mạnh hơn.

### 10.3. Trình tự chuyển

~~~text
Kiểm kê role chung và dependency
  -> Tạo ba đường đích, cấu hình audit
  -> Pilot nhóm vận hành + một pipeline
  -> Chứng minh tác vụ dùng đúng danh tính mới
  -> Kiểm thử âm và hành vi hết activation/token
  -> Chặn nhận role chung qua cả người dùng và CI
  -> Xử lý phiên/credential cũ
  -> Kiểm tra reconcile và đóng role nguồn
~~~

Hai phép thử đặc biệt quan trọng:

- Người dùng vận hành không thể sửa trust của role triển khai.
- Workload CI ngoài môi trường được chấp thuận không thể nhận role production.

Sau cutover, nếu job vẫn thành công nhưng log cho thấy principal cũ, đợt chuyển chưa đạt. Cần tìm credential cũ hoặc đường fallback trước khi xóa cấu hình nguồn.

### 10.4. Bằng chứng đóng đợt

Hồ sơ kết thúc gồm mapping role, kết quả test, request và approval mẫu, audit của thao tác đích, bằng chứng không nhận thêm token qua đường cũ, kết quả kiểm tra phiên tồn dư và kết quả reconcile.

Chủ dịch vụ xác nhận cả tác vụ thường ngày và tác vụ theo lịch đã được bao phủ. Nhóm IAM xác nhận trust và quyền không mở rộng ngoài thiết kế. Nhóm vận hành giữ runbook khôi phục đã cập nhật.

## 11. Các lỗi thường gặp và cách xử lý

### Lỗi 1: Sao chép nguyên policy quản trị cũ

**Biểu hiện:** role mới vẫn có quyền rộng, chỉ khác tên và công cụ cấp quyền.

**Xử lý:** phân loại tác vụ, tách người và máy, thu hẹp scope, kiểm tra quyền bắc cầu. Với quyền chưa thể thu hẹp, ghi rõ lý do và kế hoạch xử lý thay vì coi migration đã giải quyết least privilege.

### Lỗi 2: Chỉ đổi permission, bỏ qua trust

**Biểu hiện:** workload hoặc principal ngoài kế hoạch vẫn có thể nhận role.

**Xử lý:** rà issuer, audience, subject, assignment, nhóm lồng nhau và quyền sửa cấu hình nguồn. Chạy trường hợp âm cho principal và môi trường sai.

### Lỗi 3: Cho rằng hết approval là hết quyền

**Biểu hiện:** sau khi activation kết thúc, token đã cấp vẫn gọi được API.

**Xử lý:** tách vòng đời approval, assignment, token và kết nối. Kiểm tra khả năng revoke thực tế; giới hạn token và renewal từ đầu theo nhu cầu.

### Lỗi 4: Chỉ kiểm thử “happy path”

**Biểu hiện:** tác vụ cần thiết chạy được nhưng chưa biết người dùng có đọc secret hoặc sửa IAM được không.

**Xử lý:** lập ma trận negative test trước cutover, dùng principal có quyền được kiểm soát và đối chiếu log quyết định truy cập.

### Lỗi 5: Giữ credential cũ để dự phòng vô thời hạn

**Biểu hiện:** mọi tác vụ đã chuyển nhưng key cũ vẫn còn trong CI hoặc secret store.

**Xử lý:** xác định owner, hạn chót và bằng chứng vô hiệu hóa; thay đường dự phòng bằng runbook khẩn cấp được kiểm soát.

### Lỗi 6: Đánh giá quyền bằng log sử dụng duy nhất

**Biểu hiện:** loại bỏ quyền cho tác vụ phục hồi chưa xuất hiện trong kỳ log.

**Xử lý:** bổ sung lịch công việc, diễn tập, xác nhận owner và tài liệu dependency. Coi log là bằng chứng về điều đã thấy, không phải toàn bộ nhu cầu hợp lệ.

### Lỗi 7: Gỡ quyền trên cloud nhưng giữ cấu hình cũ trong mã

**Biểu hiện:** assignment quay trở lại sau một lần deploy.

**Xử lý:** sửa nguồn cấu hình, chặn pipeline tái tạo đường cũ, kiểm tra drift sau reconcile.

### Lỗi 8: Audit chỉ ghi danh tính broker hoặc role chung

**Biểu hiện:** thấy có thao tác đặc quyền nhưng không truy ra người yêu cầu hoặc lần chạy workload.

**Xử lý:** bảo toàn chuỗi định danh từ request tới session và cloud event bằng các cơ chế nền tảng hỗ trợ. Kiểm tra claim và nhãn tương quan có độ tin cậy, không chỉ dựa vào chuỗi do người gọi tự đặt.

## 12. Bài tập thực hành

### Đề bài

Một dịch vụ thanh toán có ba nhu cầu:

- Nhóm vận hành xem log và restart dịch vụ.
- Pipeline triển khai phiên bản production.
- Nhóm bảo mật sửa assignment khi có yêu cầu đã duyệt.

Hiện tất cả dùng một role quản trị chung. Role này có credential dài hạn trong CI; nhóm vận hành có thể nhận role bất kỳ lúc nào. Một job đối soát chạy mỗi tuần cũng đang dùng role nhưng chưa có owner trong danh sách migration.

Hãy lập phương án di chuyển cloud role sang PAM.

### Sản phẩm cần tạo

1. Hồ sơ role nguồn, principal và dependency, bao gồm job đối soát.
2. Mapping role đích theo tác vụ, scope và loại danh tính.
3. Thiết kế trust và thời hạn cho con người và workload.
4. Ma trận ít nhất tám trường hợp kiểm thử có cả quyền âm.
5. Runbook cutover theo từng đơn vị rollback.
6. Tiêu chí đóng đường cũ và hồ sơ bằng chứng.

Không đưa secret hoặc token thật vào hồ sơ bài tập.

### Gợi ý tự đánh giá

- Job đối soát có owner và tác vụ được xác nhận trước khi chuyển hoặc gỡ quyền không?
- Pipeline có thể chọn danh tính runtime tùy ý hoặc sửa trust của chính mình không?
- Người vận hành có thể vượt approval qua nhóm cũ hay role chaining không?
- Quyền triển khai có gián tiếp cho phép mã chạy với danh tính mạnh hơn không?
- Có kiểm tra credential provider chain để chứng minh CI dùng đường mới không?
- Có kiểm thử token đã tồn tại sau khi activation hết hạn không?
- Rollback có phục hồi credential nghi bị lộ không?
- Reconciler có khả năng tạo lại assignment cũ không?
- Có thể nối một cloud event với đúng người dùng hoặc lần chạy workload không?
- Tiêu chí hoàn tất có bao gồm thu hồi đường cũ thay vì chỉ tạo role mới không?

Một phương án hợp lý sẽ tách vận hành, triển khai và quản trị IAM; xử lý job đối soát như một workload có owner riêng; kiểm tra trust, quyền bắc cầu và phiên tồn dư; đồng thời giữ phạm vi rollback đủ nhỏ để khôi phục dịch vụ có kiểm soát.

## 13. Điểm cần ghi nhớ

Di chuyển cloud role trong PAM là chuyển toàn bộ đường cấp và sử dụng đặc quyền: principal, trust, permission, assignment, token, audit và cơ chế thu hồi.

Role đích phải được chứng minh bằng tác vụ được phép, tác vụ bị từ chối và khả năng quy trách nhiệm. Hết approval, gỡ binding hoặc thay trust không tự chứng minh rằng mọi token đã ngừng hoạt động.

Đợt migration chỉ đóng khi đường mới đáp ứng nhu cầu, đường cũ không còn cấp hoặc duy trì quyền ngoài kế hoạch, cấu hình không tái tạo đặc quyền cũ và bằng chứng đủ để một người khác kiểm tra lại quyết định chuyển đổi.
