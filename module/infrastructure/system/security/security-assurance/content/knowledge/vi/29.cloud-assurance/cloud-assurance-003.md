# Cloud account: ranh giới quản trị và bằng chứng bảo đảm an toàn trên đám mây

Trong **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện và bảo đảm liên tục khi phát triển, vận hành. **Cloud account** là một đối tượng quan trọng của quá trình đó. Nếu không biết tài khoản đám mây nào đang tồn tại, ai chịu trách nhiệm, quyền quản trị được cấp thế nào và nhật ký được bảo vệ ra sao, tổ chức khó chứng minh các kiểm soát bảo mật thật sự có hiệu lực.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cloud account là gì, phân biệt tài khoản quản trị tài nguyên với danh tính người dùng hoặc ứng dụng.
2. Nhận diện ranh giới quản trị tương ứng ở AWS, Microsoft Azure và Google Cloud; hiểu vì sao chúng không hoàn toàn tương đương.
3. Thiết kế vòng đời quản lý cloud account với chủ sở hữu, phân vùng môi trường, chính sách và quyền truy cập phù hợp.
4. Xây dựng bộ tiêu chí assurance, thu thập bằng chứng và xác minh bằng kiểm thử kỹ thuật thay vì chỉ dựa vào tuyên bố cấu hình.
5. Phát hiện, xử lý các sai lệch phổ biến như tài khoản không có chủ sở hữu, quyền quản trị tồn tại quá lâu hoặc nhật ký bị thiếu.

## 1. Cloud account là gì?

**Cloud account** là phạm vi logic mà khách hàng sử dụng để quản lý một phần hoặc toàn bộ tài nguyên và quyền kiểm soát trên nền tảng đám mây. Tùy nhà cung cấp, phạm vi đó có thể gắn với hợp đồng, thanh toán, danh tính, chính sách, quota, tài nguyên hoặc tất cả các yếu tố trên.

Một cloud account thường chứa hoặc liên kết với:

- **Tài nguyên:** máy ảo, cơ sở dữ liệu, mạng, bucket, khóa mã hóa, dịch vụ ứng dụng.
- **Quyền truy cập:** người dùng, nhóm, vai trò, danh tính workload, quan hệ tin cậy liên tài khoản.
- **Chính sách quản trị:** giới hạn triển khai, vùng được phép sử dụng, chính sách bảo mật và quy tắc gắn nhãn.
- **Nhật ký và tín hiệu giám sát:** thao tác quản trị, truy cập tài nguyên, sự kiện phát hiện nguy cơ và thay đổi cấu hình.
- **Trách nhiệm vận hành:** chủ sở hữu nghiệp vụ, đội vận hành, đội an ninh, chi phí và quy trình xử lý sự cố.

**Cloud account không đồng nghĩa với tài khoản đăng nhập cá nhân.** Một kỹ sư có thể sử dụng cùng một danh tính doanh nghiệp để truy cập nhiều cloud account; ngược lại, một cloud account có thể được nhiều người và workload sử dụng thông qua những vai trò khác nhau.

### 1.1. Phân biệt giữa các nhà cung cấp

| Nhà cung cấp | Ranh giới cần quan tâm | Cấp tổ chức/quản trị liên quan | Lưu ý khi đánh giá |
|---|---|---|---|
| **AWS** | AWS account | AWS Organizations, organizational unit (OU), management account, member account | AWS account là ranh giới quan trọng cho tài nguyên, IAM và thanh toán; service control policy (SCP) đặt giới hạn quyền tại cấp tổ chức. |
| **Microsoft Azure** | Subscription, resource group | Microsoft Entra tenant, management group | Subscription là phạm vi quản trị và thanh toán quan trọng; danh tính và một số cấu hình chung nằm ở tenant, nên tách subscription chưa chắc tách hoàn toàn mặt phẳng danh tính. |
| **Google Cloud** | Project | Organization, folder, billing account | Project là phạm vi cơ bản của tài nguyên, API và nhiều quyền IAM; một billing account có thể thanh toán cho nhiều project. |

Các đơn vị trên **tương tự về vai trò quản trị**, nhưng không phải các thực thể giống hệt nhau. Khi thiết kế control hoặc viết báo cáo assurance đa đám mây, phải chỉ rõ loại đối tượng đang đánh giá: AWS account, Azure subscription/tenant hay Google Cloud project/organization.

Ví dụ, kiểm tra "tất cả account đều ghi nhận thao tác quản trị" là yêu cầu cấp tổ chức. Cách triển khai và bằng chứng kỹ thuật sẽ khác: CloudTrail của AWS, Azure Activity Log và Cloud Audit Logs của Google Cloud có phạm vi, loại sự kiện, chính sách lưu giữ và cơ chế xuất log khác nhau.

### 1.2. Cloud account là một ranh giới, không phải lá chắn tuyệt đối

Việc chia tài nguyên thành nhiều cloud account hỗ trợ:

- Cô lập quyền và giới hạn phạm vi tác động khi tài khoản hoặc workload bị xâm phạm.
- Áp chính sách khác nhau cho môi trường production, staging, development và sandbox.
- Tách quyền quản trị, vận hành, kiểm toán và thanh toán.
- Làm rõ ai chịu trách nhiệm về cấu hình, dữ liệu và chi phí.

Tuy nhiên, **một account riêng không tự động tạo ra hệ thống an toàn**. Quyền quản trị cấp tổ chức, danh tính liên kết, kết nối mạng, khóa mã hóa, hệ thống CI/CD hoặc cơ chế chia sẻ dữ liệu vẫn có thể nối các account với nhau. Assurance phải kiểm tra những đường liên kết đó.

## 2. Vị trí của cloud account trong mô hình trách nhiệm chung

Nhà cung cấp đám mây chịu trách nhiệm đối với những phần hạ tầng và dịch vụ thuộc phạm vi họ quản lý. Khách hàng vẫn phải quản lý các cấu hình, danh tính, quyền, dữ liệu và cách sử dụng dịch vụ trong phạm vi trách nhiệm của mình. Ranh giới thay đổi theo IaaS, PaaS, SaaS và từng sản phẩm cụ thể.

Chẳng hạn, nhà cung cấp có thể bảo vệ phần cứng và hạ tầng điều khiển dịch vụ, nhưng không tự xác nhận rằng đội dự án đã:

- Chỉ định đúng chủ sở hữu cho subscription hoặc project.
- Áp đúng quyền truy cập tối thiểu cho vai trò triển khai.
- Bật và chuyển đủ các nhóm nhật ký cần thiết sang nơi lưu giữ được bảo vệ.
- Loại bỏ khóa truy cập tồn tại lâu ngày.
- Thu hồi quyền khi một nhân sự chuyển bộ phận.

Vì vậy, đối tượng assurance không chỉ là bản thân cloud account mà còn là **cách tổ chức kiểm soát account và bằng chứng cho thấy kiểm soát đó đang hoạt động**.

## 3. Thiết kế cấu trúc account và phân vùng môi trường

Một kiến trúc thường tách account dùng cho điều hành tổ chức, lưu nhật ký, công cụ an ninh và các môi trường chạy ứng dụng. Sơ đồ dưới đây minh họa cách tổ chức theo các phạm vi trách nhiệm, không áp đặt một cấu trúc giống hệt cho mọi nhà cung cấp:

~~~mermaid
flowchart TB
    ORG["Cấp tổ chức / tenant"] --> GOV["Quản trị chính sách và danh tính"]
    ORG --> LOG["Không gian lưu nhật ký tập trung"]
    ORG --> SEC["Dịch vụ giám sát và an ninh"]
    ORG --> PROD["Tài khoản / subscription / project production"]
    ORG --> NONPROD["Tài khoản / subscription / project non-production"]
    PROD --> APP1["Workload thanh toán"]
    PROD --> APP2["Workload khách hàng"]
    NONPROD --> TEST["Dev, test, sandbox"]
    APP1 -. "Sự kiện bảo mật" .-> LOG
    APP2 -. "Sự kiện bảo mật" .-> LOG
    TEST -. "Sự kiện bảo mật" .-> LOG
    LOG --> SEC
~~~

Mục đích của mô hình này là giảm việc tập trung quá nhiều đặc quyền vào một phạm vi và bảo vệ tính độc lập của bằng chứng. Ví dụ, người quản trị workload production không nên đương nhiên có quyền xóa cả nhật ký lịch sử trong nơi lưu trữ của đội kiểm toán.

**Nguyên tắc thiết kế:**

1. **Tách theo mức rủi ro:** production, non-production, môi trường thử nghiệm có dữ liệu thật, hệ thống chịu quy định riêng có thể cần các phạm vi độc lập.
2. **Tách quyền quản trị:** quyền triển khai ứng dụng không mặc nhiên bao gồm quyền sửa chính sách tổ chức hoặc xóa kho log.
3. **Tách chức năng kiểm soát:** audit, phát hiện đe dọa và lưu bằng chứng nên có quyền và quy trình bảo vệ riêng.
4. **Quản trị từ cấp trên:** áp guardrail ở organization, management group hoặc folder khi phù hợp; xác minh phạm vi kế thừa xuống account.
5. **Hạn chế chia sẻ xuyên ranh giới:** các vai trò liên tài khoản, kết nối mạng và đường truyền dữ liệu phải có mục đích, chủ sở hữu và đánh giá rủi ro.
6. **Theo dõi tài khoản ngoài cấu trúc chuẩn:** một tài khoản do cá nhân mở riêng có thể không nhận được chính sách và nhật ký tập trung; cần quy trình đối soát bổ sung.

Với AWS, cần đặc biệt bảo vệ **management account** vì tài khoản này có đặc quyền quản trị tổ chức; một SCP áp dụng cho member account không tạo ra giới hạn tương đương đối với management account. Với Azure, cần xem xét cả quyền cấp tenant lẫn quyền cấp subscription. Với Google Cloud, cần xem xét quyền trên organization/folder và các project trực thuộc.

## 4. Vòng đời cloud account

Assurance hiệu quả bắt đầu trước khi account được tạo và tiếp tục đến khi không còn dữ liệu, quyền và nghĩa vụ lưu giữ liên quan.

| Giai đoạn | Hành động cần có | Bằng chứng nên giữ |
|---|---|---|
| **Đề xuất** | Nêu mục đích, phân loại môi trường/dữ liệu, xác định chủ sở hữu và mức rủi ro | Yêu cầu tạo account, phê duyệt, đánh giá rủi ro |
| **Cấp phát** | Tạo qua quy trình chuẩn, đưa vào cấu trúc tổ chức, gắn baseline, tích hợp danh tính và logging | Dấu vết cấp phát, cấu hình ban đầu, kết quả kiểm tra baseline |
| **Vận hành** | Quản lý quyền, log, sự kiện và drift; kiểm kê tài nguyên; đánh giá ngoại lệ | Dữ liệu API, sự kiện thay đổi, lịch sử kiểm tra, ticket |
| **Thay đổi** | Rà soát khi đổi chủ sở hữu, loại dữ liệu, môi trường, kết nối hoặc quyền đặc biệt | Yêu cầu thay đổi, đánh giá tác động, xác minh sau thay đổi |
| **Ngừng sử dụng** | Khóa quyền, xử lý dữ liệu và khóa, chốt chi phí, bảo toàn log theo thời hạn lưu giữ, đóng phạm vi | Biên bản đóng, xác nhận lưu giữ/xóa dữ liệu, kết quả kiểm tra cuối |

**Tình huống:** một sandbox dùng để thử API ban đầu chỉ có dữ liệu giả. Sau đó đội phát triển đưa bản sao dữ liệu khách hàng vào để tái hiện lỗi. Nếu không có bước đánh giá lại phân loại dữ liệu và quyền truy cập, sandbox đã chuyển sang mức rủi ro cao hơn trong khi các guardrail cũ vẫn giữ nguyên.

### 4.1. Hồ sơ account tối thiểu

Mỗi account cần có bản ghi inventory liên kết được với ID thật do nhà cung cấp cấp, với các trường đủ để truy trách nhiệm và đối chiếu chính sách. Ví dụ minh họa:

~~~yaml
provider: aws
account_id: "111122223333"        # ID giả định, dùng làm ví dụ
name: "payments-production"
environment: production
business_service: "payments-api"
business_owner: "payments-product"
technical_owner: "platform-team"
security_contact: "secops-team"
data_classification: restricted
organization_unit: production
approved_regions:
  - ap-southeast-1
baseline_version: "cloud-account-baseline-v3"
lifecycle_status: active
exception_ids: []
~~~

Cần lưu account ID ở dạng chuỗi vì đó là **định danh**, không phải đại lượng để tính toán. Inventory phải có cơ chế đồng bộ với dữ liệu thực tế từ nhà cung cấp. Một bảng khai báo thủ công lâu không kiểm tra không đủ để chứng minh phạm vi quản lý đã đầy đủ.

## 5. Các mối đe dọa và mục tiêu bảo mật

Một số kịch bản rủi ro điển hình:

- **Chiếm quyền danh tính quản trị:** kẻ tấn công dùng phiên đăng nhập hoặc khóa bị lộ để sửa quyền, tạo tài nguyên, đọc dữ liệu hoặc vô hiệu hóa kiểm soát.
- **Leo thang quyền:** một vai trò cấp quyền vượt nhu cầu thực tế, hoặc cho phép tự cấp thêm đặc quyền.
- **Tin cậy xuyên account quá rộng:** workload development có thể giả mạo hoặc sử dụng vai trò trong production.
- **Account ngoài kiểm kê:** account do nhóm riêng mở, không nhận baseline và không được SOC theo dõi.
- **Mất khả năng điều tra:** log không được bật, xuất không đủ loại sự kiện, bị ngắt hoặc bị xóa cùng với tài khoản gặp sự cố.
- **Sai cấu hình do thay đổi:** guardrail, nhãn owner, quyền truy cập hay dịch vụ an ninh bị chỉnh sửa nhưng không được phát hiện.
- **Không kết thúc vòng đời:** account cũ còn dữ liệu, vai trò hoặc tài nguyên đang chạy dù dự án đã đóng.

Các mục tiêu assurance tương ứng có thể được phát biểu như sau:

1. **Quản trị:** mọi account trong phạm vi đánh giá có chủ sở hữu và trạng thái vòng đời rõ ràng.
2. **Bảo vệ danh tính:** quyền đặc biệt được cấp có kiểm soát, xác thực phù hợp với mức rủi ro và có khả năng thu hồi.
3. **Cô lập:** môi trường và dữ liệu nhạy cảm nằm trong những ranh giới được phê duyệt; quan hệ tin cậy xuyên ranh giới được giới hạn.
4. **Quan sát:** có nhật ký và tín hiệu phát hiện đủ để tái dựng sự kiện quan trọng.
5. **Toàn vẹn bằng chứng:** đội vận hành workload khó có thể đơn phương sửa hoặc hủy dấu vết cần cho kiểm toán.
6. **Liên tục:** sai lệch được phát hiện, ưu tiên khắc phục, kiểm tra lại và theo dõi theo thời gian.

## 6. Baseline bảo mật dành cho cloud account

Một **baseline** là tập yêu cầu tối thiểu được phê duyệt để mỗi account phải đáp ứng trước và trong vận hành. Dưới đây là ví dụ bộ control cấp account; các điều kiện cụ thể cần điều chỉnh theo nền tảng, loại dịch vụ, rủi ro và quy định nội bộ.

| ID | Control | Điều kiện đạt mong muốn | Bằng chứng và phép kiểm |
|---|---|---|---|
| CA-01 | Inventory và ownership | Account có ID, môi trường, chủ sở hữu, phân loại dữ liệu và trạng thái hợp lệ | So khớp inventory với danh sách account từ API tổ chức, kiểm tra trường bắt buộc |
| CA-02 | Cấu trúc tổ chức | Account thuộc đúng organization/tenant, OU/management group/folder, nhận đúng guardrail | Xuất cây phân cấp, chính sách được gắn và đánh giá phạm vi áp dụng |
| CA-03 | Danh tính quản trị | Quyền quản trị dùng danh tính tập trung khi phù hợp, MFA cho đường đăng nhập đặc quyền, có quy trình truy cập khẩn cấp | Cấu hình IdP, phân quyền, phương thức xác thực, hồ sơ kiểm tra truy cập khẩn cấp |
| CA-04 | Quyền tối thiểu | Vai trò con người/workload có mục đích, giới hạn phạm vi, được rà soát định kỳ; tránh khóa dài hạn khi có cơ chế thay thế | IAM/RBAC policies, vai trò tin cậy, bản ghi phê duyệt, lịch sử sử dụng quyền |
| CA-05 | Logging | Sự kiện quản trị và những loại sự kiện dữ liệu cần thiết được thu thập theo phạm vi đã định, chuyển về nơi lưu giữ được bảo vệ | Trạng thái thu log, cấu hình nguồn và đích, sự kiện mẫu đã được nhận |
| CA-06 | Bảo vệ log | Quyền xóa/sửa log tách khỏi quyền vận hành thông thường; áp chính sách lưu giữ và cảnh báo thay đổi | ACL/policy của kho log, retention, thử nghiệm truy cập bị từ chối, cảnh báo |
| CA-07 | Monitoring và drift | Thay đổi quyền, guardrail, logging, cấu hình nguy hiểm được phát hiện và có đầu mối xử lý | Rule phát hiện, sự kiện thử, ticket và thời điểm phản hồi |
| CA-08 | Khóa và bí mật | Quyền dùng khóa/bí mật được giới hạn; khóa dài hạn được kiểm soát và thu hồi khi không cần | Key policy, quyền truy cập secret, quy trình xoay/thu hồi, lịch sử kiểm tra |
| CA-09 | Khu vực và tài nguyên | Vùng triển khai, loại dịch vụ hoặc cách công khai tài nguyên có giới hạn theo yêu cầu tổ chức | Chính sách giới hạn, inventory tài nguyên, kết quả quét cấu hình |
| CA-10 | Kết thúc vòng đời | Account ngừng sử dụng được xử lý dữ liệu, thu hồi quyền, khóa và kết nối; bằng chứng còn được lưu theo quy định | Checklist đóng account, phê duyệt, xác nhận lưu giữ và đối soát cuối |

### 6.1. Guardrail phòng ngừa và kiểm soát phát hiện

Không nên dùng một loại policy để chứng minh mọi mục tiêu bảo mật.

- **Phòng ngừa (preventive):** giới hạn hành động không được phép, ví dụ ràng buộc tổ chức hạn chế vùng triển khai hoặc quyền vô hiệu hóa logging, khi nền tảng hỗ trợ.
- **Phát hiện (detective):** nhận biết thay đổi ngoài baseline, hành vi bất thường và account thiếu log.
- **Khắc phục (corrective):** yêu cầu chủ sở hữu xử lý, tự động sửa cấu hình trong phạm vi an toàn, hoặc cô lập quyền theo quy trình sự cố.
- **Bù trừ (compensating):** biện pháp thay thế được đánh giá, phê duyệt có thời hạn khi chưa thể áp dụng control chuẩn.

Ví dụ, **AWS SCP đặt giới hạn quyền tối đa** cho các principal chịu tác động trong member account; SCP tự nó không cấp quyền và không thay thế IAM policy. **Azure Policy** tập trung vào quản trị và đánh giá sự phù hợp của tài nguyên, không thay thế toàn bộ Azure RBAC. **Google Cloud Organization Policy** đặt các ràng buộc được hỗ trợ và cần được xem xét cùng IAM. Vì thế, việc thấy một policy đã được gắn chưa đủ để kết luận quyền hay cấu hình cuối cùng đã đúng.

### 6.2. Tài khoản đặc quyền và truy cập khẩn cấp

Quyền đặc quyền có thể nằm ở nhiều tầng: tài khoản gốc, danh tính cấp tenant, vai trò quản trị subscription, organization admin, IAM admin hoặc quyền kiểm soát hệ thống xác thực tập trung.

Một quy trình phù hợp thường bao gồm:

1. Sử dụng đăng nhập liên kết với danh tính doanh nghiệp và xác thực mạnh cho công việc hằng ngày.
2. Tách quyền quản trị tổ chức khỏi quyền vận hành ứng dụng; sử dụng quyền có thời hạn hoặc được phê duyệt theo yêu cầu khi có thể.
3. Bảo vệ thông tin đăng nhập root/super-admin và đường truy cập khẩn cấp; khi tài khoản root có thông tin xác thực riêng thì cần kiểm soát chặt, bật MFA theo khả năng hỗ trợ và tránh tạo khóa truy cập dài hạn.
4. Kiểm soát ai có thể giả định vai trò (assume role), tạo khóa, sửa trust policy hoặc cấp quyền cho chính mình.
5. Kiểm tra định kỳ tài khoản không sử dụng, credential tồn tại lâu ngày và đặc quyền không còn gắn với nhiệm vụ.

Với **truy cập khẩn cấp (break-glass)**, vừa cần bảo đảm có thể sử dụng khi hệ thống IdP gặp sự cố, vừa phải hạn chế khả năng lạm dụng: bảo quản riêng, kiểm soát số người biết, ghi nhận việc sử dụng, cảnh báo và đánh giá sau mỗi lần kích hoạt. Không đánh giá đạt chỉ vì tài liệu quy trình tồn tại; nên kiểm thử có kiểm soát khả năng truy cập và khả năng ghi nhận sự kiện.

## 7. Đánh giá assurance: yêu cầu → control → bằng chứng → kết luận

Một cấu hình trông hợp lý chưa phải là bằng chứng rằng control đang hoạt động. Đánh giá assurance cần trả lời được **đang đánh giá đối tượng nào, tại thời điểm nào, bằng phép kiểm nào và với tiêu chí đạt nào**.

Quy trình tham chiếu:

~~~mermaid
flowchart LR
    R["Rủi ro và mục tiêu"] --> Q["Yêu cầu kiểm soát"]
    Q --> I["Triển khai control"]
    I --> E["Thu bằng chứng"]
    E --> T["Kiểm thử, đối soát"]
    T --> F{"Đạt tiêu chí?"}
    F -- "Có" --> P["Ghi kết quả và giám sát liên tục"]
    F -- "Không" --> N["Finding, owner, hạn xử lý"]
    N --> X["Khắc phục và kiểm thử lại"]
    X --> E
~~~

### 7.1. Các thuộc tính của bằng chứng tốt

**Bằng chứng đáng tin cậy** cần đạt những thuộc tính sau:

- **Nguồn rõ ràng:** API, cloud inventory, log hệ thống, nền tảng quản lý danh tính hoặc hồ sơ phê duyệt có nguồn truy xuất.
- **Phạm vi đầy đủ:** account IDs, vùng/region, loại sự kiện, chính sách và mốc thời gian được chỉ ra; kiểm tra một account không chứng minh cho toàn bộ tổ chức.
- **Kịp thời:** có thời gian thu thập và kỳ đánh giá; bằng chứng trước một thay đổi lớn có thể đã hết giá trị.
- **Có thể đối chiếu:** nối được control ID, account ID, dấu vết kỹ thuật và kết quả phép kiểm.
- **Khó bị sửa đổi trái phép:** phân quyền kho bằng chứng, theo dõi truy cập, kiểm tra tính toàn vẹn và retention thích hợp.
- **An toàn dữ liệu:** loại bỏ token, khóa bí mật và dữ liệu nhạy cảm không cần thiết; hạn chế người xem theo vai trò.

**Ảnh chụp giao diện** có thể hỗ trợ mô tả nhưng dễ thiếu phạm vi, thời điểm và khả năng lặp lại. Với control quan trọng, nên ưu tiên dữ liệu API, log và kết quả kiểm thử được lưu trong pipeline đánh giá có phân quyền.

### 7.2. Phương pháp lấy mẫu và độ bao phủ

Không phải mọi tổ chức đều có thể kiểm thử thủ công từng account ở cùng độ sâu. Có thể kết hợp:

- **Kiểm tra toàn bộ bằng máy:** các điều kiện đo được bằng API như account được đăng ký, gắn baseline, cấu hình log và trạng thái chính sách.
- **Kiểm tra theo rủi ro:** ưu tiên production, dữ liệu nhạy cảm, quyền quản trị cấp tổ chức và các account đã có finding.
- **Lấy mẫu có lý do:** dùng cho quy trình phê duyệt, đánh giá chủ sở hữu hay kiểm thử break-glass; ghi rõ cách chọn và giới hạn suy rộng.
- **Kiểm tra sau thay đổi:** chạy lại các control bị ảnh hưởng khi tạo account, thay đổi cấu trúc tổ chức, điều chỉnh IAM hoặc logging.

Cần ghi rõ sự khác biệt giữa **"không phát hiện lỗi trong mẫu"** và **"toàn bộ phạm vi đạt yêu cầu"**. Hai kết luận này có mức độ đảm bảo khác nhau.

## 8. Ví dụ kỹ thuật: kiểm tra account AWS

Giả sử tổ chức quản lý nhiều AWS account bằng AWS Organizations. Đội assurance muốn xác minh một account production mới đã được kiểm kê và có dấu vết hoạt động quản trị.

Các lệnh sau **chỉ minh họa quy trình đọc dữ liệu**; profile phải được cấu hình trước và được cấp quyền tương ứng. Giá trị account ID và tên trail sử dụng trong ví dụ là giả định.

### Bước 1 — Xác minh mình đang kiểm tra bằng danh tính nào

~~~bash
aws sts get-caller-identity --profile audit
~~~

Kết quả giúp xác định principal hiện tại và AWS account đang dùng để gọi API. Nếu kiểm tra nhầm account hoặc nhầm vai trò, toàn bộ kết luận phía sau có thể sai phạm vi.

### Bước 2 — Đối chiếu danh sách account trong tổ chức

~~~bash
aws organizations list-accounts --profile org-audit --output json
~~~

Lệnh thường cần chạy từ ngữ cảnh có quyền thích hợp trong tổ chức. Đối chiếu danh sách trả về với inventory được quản lý: có account nào thiếu owner, thuộc sai môi trường hoặc chưa được đưa vào quy trình giám sát? Việc chỉ nhìn thấy account trong Organizations **không chứng minh** account đã nhận đủ baseline.

### Bước 3 — Kiểm tra nguồn CloudTrail và trạng thái ghi log

~~~bash
aws cloudtrail describe-trails \
  --include-shadow-trails \
  --region ap-southeast-1 \
  --profile audit

aws cloudtrail get-trail-status \
  --name arn:aws:cloudtrail:ap-southeast-1:111122223333:trail/org-trail \
  --region ap-southeast-1 \
  --profile audit
~~~

Cần đánh giá xem trail có thực sự áp dụng cho account mục tiêu, các region và loại sự kiện yêu cầu hay không; liệu sự kiện đã được gửi tới đích tập trung và đích đó có được bảo vệ hay không. Trạng thái một trail riêng lẻ **không đủ** để xác minh độ bao phủ toàn bộ tổ chức, tất cả region hoặc mọi sự kiện dữ liệu. CloudTrail có những loại log và tùy chọn cấu hình khác nhau; chỉ ghi lại sự kiện quản trị không có nghĩa là mọi hoạt động đọc dữ liệu đều được theo dõi.

### Bước 4 — Đối chiếu bằng chứng nhiều nguồn

Ví dụ, nếu CA-05 yêu cầu mọi account production có log quản trị được chuyển về kho tập trung, bộ kiểm chứng cần liên kết:

1. Danh sách account production trong inventory và dữ liệu organization tại thời điểm kiểm tra.
2. Cấu hình logging có hiệu lực trên từng account/region thuộc phạm vi.
3. Quyền của hệ thống nhận log và chính sách retention.
4. Một số sự kiện thử hợp lệ đã xuất hiện tại đích trong cửa sổ thời gian kỳ vọng.
5. Lịch sử thay đổi cấu hình logging và cảnh báo khi cấu hình bị vô hiệu hóa.

Tương tự ở Azure, có thể đối chiếu subscription, quyền Azure RBAC, Azure Policy, Azure Activity Log và đích xuất log. Ở Google Cloud, có thể đối chiếu project/folder, IAM, Organization Policy, Cloud Audit Logs và cấu hình đích log. Với mỗi nhà cung cấp, cần đọc đúng mô tả về loại sự kiện và ngoại lệ của dịch vụ đang dùng.

## 9. Ví dụ một bộ hồ sơ bằng chứng

Một báo cáo assurance nên lưu đủ metadata để người khác kiểm thử lại. Tệp sau minh họa **cấu trúc dữ liệu tham khảo**, không phải định dạng bắt buộc của nhà cung cấp:

~~~yaml
assessment_id: "CA-2026-11-028"
control_id: "CA-05"
control_name: "Management activity logging"
provider: "aws"
target:
  account_id: "111122223333"
  environment: "production"
  regions_assessed:
    - "ap-southeast-1"
assessed_at: "2026-11-28T08:00:00Z"
baseline_version: "cloud-account-baseline-v3"
required_condition: >
  Sự kiện quản trị thuộc phạm vi đã xác định được thu thập,
  gửi đến kho log tập trung và bảo vệ theo chính sách.
evidence:
  - type: "api-export"
    reference: "evidence/CA-05/organizations-accounts.json"
  - type: "configuration-export"
    reference: "evidence/CA-05/trail-config.json"
  - type: "delivery-check"
    reference: "evidence/CA-05/delivery-check.json"
result: "PASS_WITH_SCOPE"
limitations:
  - "Chỉ đánh giá region và nhóm sự kiện đã khai báo"
assessor: "cloud-assurance-team"
~~~

Giá trị **PASS_WITH_SCOPE** là quy ước trong ví dụ, nhắc người đọc rằng kết luận chỉ có giá trị trong phạm vi được mô tả. Một hệ thống thật có thể dùng PASS, FAIL, NOT_APPLICABLE, INCONCLUSIVE; cần định nghĩa các trạng thái nhất quán trước khi tổng hợp KPI.

Khi có lỗi, hồ sơ cần thêm **finding ID, tác động, bằng chứng, severity có căn cứ, người chịu trách nhiệm, hạn xử lý, biện pháp khắc phục và bằng chứng kiểm thử lại**. Đừng đánh dấu finding là đã xử lý chỉ vì ticket chuyển sang trạng thái "Done".

## 10. Tình huống thực hành: account production mất một phần nhật ký

Một công ty có 18 AWS account, trong đó 6 account production. Đội vận hành vừa tạo account **payments-prod-02**, đưa vào OU production và cấp quyền triển khai qua role. Dashboard cấu hình cho thấy CloudTrail được bật; đội assurance bắt đầu kiểm tra CA-05.

**Phát hiện:** dữ liệu API cho thấy một trail đang hoạt động nhưng tập trung vào một số sự kiện quản trị; các sự kiện truy cập đối tượng dữ liệu mà chính sách nội bộ yêu cầu ghi lại chưa được cấu hình cho bucket xử lý giao dịch. Kho log tập trung chưa nhận được sự kiện thử tương ứng.

Điều này có nghĩa là:

- Không đủ căn cứ kết luận CA-05 **đạt** đối với phạm vi dữ liệu giao dịch.
- Không nên suy diễn rằng "toàn bộ CloudTrail bị tắt"; loại sự kiện quản trị có thể vẫn được ghi bình thường.
- Cần xác định bucket nào thuộc phạm vi yêu cầu, loại data event cần bật, chi phí ghi log và cách bảo vệ dữ liệu trong log.

**Hành động khắc phục có kiểm chứng:**

1. Ghi finding với phạm vi chính xác, owner, mức độ ảnh hưởng và hạn xử lý.
2. Cập nhật cấu hình thu thập data event cho các tài nguyên thuộc phạm vi đã phê duyệt; cập nhật baseline provisioning để account mới không lặp lại lỗi.
3. Tạo sự kiện thử được phép và xác minh sự kiện đến kho log trung tâm với trường account, resource và timestamp phù hợp.
4. Đánh giá lại chính sách truy cập, lưu giữ và cảnh báo thay đổi đối với kho log.
5. Đính kèm kết quả kiểm thử lại, đóng finding khi tiêu chí đã đạt và tiếp tục theo dõi drift.

Bài học là **assurance phải kiểm chứng hiệu quả kiểm soát trên các hoạt động có rủi ro**, không dừng ở trạng thái "enabled" xuất hiện trên một trang cấu hình.

## 11. Liên tục giám sát, ngoại lệ và chỉ số

Một lần đánh giá đạt không đảm bảo account sẽ luôn đạt. Thay đổi quyền, cấu trúc tổ chức, dịch vụ mới hoặc một account ngoài kiểm kê đều có thể tạo sai lệch. Vì vậy, nên đưa kiểm tra baseline vào quy trình tạo account và tái chạy định kỳ hoặc khi nhận sự kiện thay đổi.

Các chỉ số hữu ích:

| Chỉ số | Cách tính hoặc quan sát | Lưu ý diễn giải |
|---|---|---|
| Độ bao phủ inventory | Số account phát hiện có bản ghi owner hợp lệ / tổng account phát hiện thuộc phạm vi | Cần thêm cách phát hiện account ngoài organization; mẫu số không đầy đủ khiến tỷ lệ đẹp nhưng sai |
| Độ bao phủ logging | Số account đáp ứng **toàn bộ tiêu chí logging được định nghĩa** / tổng account cần logging | Không chỉ đếm "đã bật dịch vụ"; phải xét loại sự kiện, region, đích và tính liên tục |
| Độ bao phủ đánh giá quyền đặc biệt | Số principal đặc quyền đã được rà soát hợp lệ / số principal đặc quyền trong phạm vi | Cần xét vai trò dùng qua federation và tài khoản kỹ thuật |
| Sai lệch baseline còn mở | Số finding đang mở, theo severity và thời gian tồn tại | Giảm số lượng finding không đồng nghĩa giảm rủi ro nếu phạm vi quét bị thu hẹp |
| Thời gian xử lý | Thời gian từ lúc phát hiện đến lúc kiểm chứng đã khắc phục | Tách thời gian triển khai sửa và thời gian xác minh |
| Ngoại lệ quá hạn | Số ngoại lệ đã hết hạn nhưng control chưa đạt hoặc chưa được tái phê duyệt | Mọi ngoại lệ nên có owner, lý do, kiểm soát bù trừ và ngày hết hạn |

Ví dụ, báo cáo "100% account đã bật logging" chưa đáng tin nếu chỉ có 15 account trong inventory nhưng thực tế tổ chức còn 3 account không được quản lý. Chất lượng mẫu số quan trọng không kém chất lượng phép kiểm.

### 11.1. Quản lý ngoại lệ

Một số workload chưa thể đáp ứng baseline vì giới hạn kỹ thuật hay giai đoạn chuyển đổi. Ngoại lệ có kiểm soát phải chỉ rõ: control bị lệch, account/resource bị ảnh hưởng, rủi ro, nguyên nhân, biện pháp bù trừ, người phê duyệt, thời hạn và kế hoạch đưa về chuẩn. Không được biến ngoại lệ thành miễn trừ vĩnh viễn chỉ vì cấu hình khó sửa.

### 11.2. Chu kỳ cải tiến

Một vòng đánh giá có thể vận hành như sau:

1. **Khi tạo account:** tự kiểm tra inventory, owner, phân vùng, danh tính và log trước khi bàn giao.
2. **Khi cấu hình thay đổi:** kiểm tra lại policy, quyền, kết nối và logging theo sự kiện.
3. **Hằng ngày hoặc theo mức rủi ro:** phát hiện drift, account không được quản lý và tín hiệu bất thường.
4. **Theo kỳ kiểm toán:** kiểm chứng mẫu việc phê duyệt, sử dụng đặc quyền, truy cập khẩn cấp và đóng finding.
5. **Sau sự cố hoặc thay đổi lớn:** cập nhật threat model, tiêu chí baseline, nguồn bằng chứng và phương pháp phát hiện.

Tần suất cụ thể phải dựa trên mức rủi ro và khả năng vận hành, không nên áp một con số cho mọi tổ chức.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| "Đã có account riêng nên production được cô lập." | Phải kiểm tra vai trò xuyên account, mạng, CI/CD, chính sách cấp tổ chức và luồng dữ liệu. |
| "Đã gắn guardrail là mọi thao tác nguy hiểm đều bị chặn." | Cần xác minh policy nào thực sự có hiệu lực, với principal và hành động nào, cùng những ngoại lệ của nền tảng. |
| "Bật CloudTrail/Activity Log/Audit Logs là đủ." | Cần xác minh phạm vi loại sự kiện, tài nguyên, region, đường chuyển log, retention và quyền bảo vệ. |
| "Không còn người dùng IAM/role có nghĩa là không còn quyền truy cập." | Cần kiểm tra danh tính liên kết, service principal, workload identity, khóa, trust policy và quyền cấp cao hơn. |
| "Ảnh dashboard màu xanh chứng minh control đạt." | Ảnh có thể thiếu phạm vi và thời điểm; cần đối chiếu API, log, kiểm thử hoặc hồ sơ phê duyệt. |
| "Account đã đóng thì không còn nghĩa vụ." | Có thể vẫn còn trách nhiệm lưu giữ log, xử lý dữ liệu, hồ sơ audit và xác nhận chi phí/quyền liên quan. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một nhân viên dùng Microsoft Entra ID để quản trị ba Azure subscription. Ba subscription có tương ứng với ba danh tính đăng nhập độc lập không?

**Gợi ý trả lời:** Không nhất thiết. Danh tính có thể được quản lý ở tenant và cấp quyền tại nhiều subscription. Khi kiểm toán phải xem cả tầng tenant/danh tính và quyền có hiệu lực trên từng subscription.

**Câu 2.** Một AWS account có CloudTrail đang ghi sự kiện quản trị. Có thể kết luận mọi thao tác đọc đối tượng trong bucket đều được ghi log không?

**Gợi ý trả lời:** Không. Phải xem cấu hình loại sự kiện và tài nguyên áp dụng, cùng kiểm chứng sự kiện tới đích lưu trữ. Management events và data events có phạm vi khác nhau.

**Câu 3.** Vì sao hệ thống inventory cần so khớp với API của nhà cung cấp?

**Gợi ý trả lời:** Vì bản ghi thủ công có thể bỏ sót account mới, account không có chủ sở hữu hoặc account nằm ngoài cấu trúc quản trị chuẩn. Mẫu số thiếu khiến KPI và kết luận assurance sai lệch.

**Câu 4.** Đội vận hành đã sửa policy theo ticket. Khi nào có thể đóng finding?

**Gợi ý trả lời:** Khi có bằng chứng kiểm thử lại cho thấy điều kiện kiểm soát đã đạt trong phạm vi bị ảnh hưởng, dữ liệu đánh giá được cập nhật và người có trách nhiệm xác nhận theo quy trình.

## Kết luận

Cloud account là điểm neo của **quản trị danh tính, cô lập môi trường, áp chính sách, theo dõi hoạt động và truy trách nhiệm** trên nền tảng đám mây. Trong chương trình security assurance, việc quản lý account phải chuyển hóa thành các tiêu chí đo được: **account nào thuộc phạm vi, yêu cầu nào áp dụng, control nào đang hoạt động, bằng chứng thu ở đâu, sai lệch được xử lý và kiểm chứng lại như thế nào**. Chỉ khi chuỗi này đầy đủ, tổ chức mới có cơ sở đưa ra kết luận đáng tin cậy về mức độ bảo đảm bảo mật của hạ tầng cloud.
