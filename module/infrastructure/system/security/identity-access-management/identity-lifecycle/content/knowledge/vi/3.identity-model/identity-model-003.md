# Định danh dịch vụ

> **Chương:** Mô hình identity  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Phạm vi:** Danh tính dịch vụ trong Identity and Access Management (IAM), đặc biệt cách nhận diện và kiểm soát tác nhân phi con người trong vòng đời Joiner–Mover–Leaver (JML).

## 1. Vì sao một dịch vụ cũng cần có danh tính?

Khi một nhân viên truy cập ứng dụng, hệ thống cần biết người đó là ai và được làm gì. Cùng câu hỏi xuất hiện khi **một chương trình gọi chương trình khác**:

- Dịch vụ đặt hàng đọc thông tin sản phẩm từ dịch vụ kho.
- Job sao lưu ghi dữ liệu lên kho lưu trữ.
- Pipeline CI/CD triển khai phiên bản mới lên môi trường kiểm thử.
- Ứng dụng chạy trên Kubernetes đọc một bí mật từ secret manager.
- Một tiến trình đồng bộ dữ liệu được chạy theo lịch mà không có người đăng nhập.

Các tác nhân này cần được xác thực và phân quyền, dù không có tên, mật khẩu đăng nhập tương tác hoặc nhân sự trực tiếp thao tác tại thời điểm gọi.

**Định danh dịch vụ (service identity)** là danh tính được quản lý cho một dịch vụ, chương trình tự động hoặc workload để hệ thống có thể nhận biết tác nhân kỹ thuật, gán quyền cho tác nhân đó và ghi lại hành động của nó. Định danh dịch vụ là một trường hợp quan trọng của **định danh phi con người (non-human identity, NHI)**.

Ví dụ: nếu cả ứng dụng thanh toán và ứng dụng gửi email cùng sử dụng một khóa quản trị chung, nhật ký chỉ cho biết “khóa quản trị đã được dùng”. Hệ thống khó phân biệt ứng dụng nào thực hiện hành động, khó giới hạn quyền riêng cho từng ứng dụng và khó thu hồi một ứng dụng mà không ảnh hưởng ứng dụng còn lại.

Thay vào đó, mỗi workload có danh tính và quyền riêng:

| Workload | Danh tính đại diện | Quyền cần thiết |
|---|---|---|
| Dịch vụ thanh toán | payment-api-prod | Gửi yêu cầu thu tiền qua API thanh toán |
| Dịch vụ gửi email | notification-worker-prod | Gửi email qua dịch vụ thông báo |
| Job sao lưu | backup-job-prod | Đọc nguồn sao lưu và ghi vào vùng backup được chỉ định |
| Pipeline triển khai | deploy-pipeline-staging | Triển khai phiên bản lên môi trường staging |

Khi cần khóa dịch vụ gửi email, tổ chức có thể vô hiệu hóa danh tính của nó mà không phải đổi credential hoặc thu hồi quyền của dịch vụ thanh toán.

## 2. Phân biệt identity, principal, account, credential và quyền

Năm khái niệm dưới đây liên quan nhưng không đồng nghĩa:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Service identity** | Tác nhân kỹ thuật nào đang hoạt động? | Workload xử lý đơn hàng của hệ thống bán hàng |
| **Security principal** | Thực thể nào được hệ thống bảo mật nhận diện để xét chính sách? | Principal định danh ứng dụng xử lý đơn hàng trong một IdP/IAM |
| **Service account** | Tài khoản nào được nền tảng dùng để đại diện cho tiến trình? | Kubernetes ServiceAccount hoặc tài khoản dịch vụ trong ứng dụng |
| **Credential** | Tác nhân chứng minh danh tính bằng cách nào? | Chứng chỉ mTLS, token ngắn hạn, khóa bí mật hoặc API key |
| **Entitlement / role / policy** | Tác nhân được phép làm gì, trên tài nguyên nào? | Chỉ được đọc hàng đợi đơn hàng của môi trường production |

Một **service identity** có thể được ánh xạ tới một hoặc nhiều đối tượng principal/account trên các hệ thống. Một principal có thể sử dụng credential khác nhau theo thời điểm. Quyền lại là tập quyết định chính sách gắn với principal hoặc với thuộc tính của nó.

Do đó, **credential không phải identity**: thay khóa bí mật không có nghĩa là thay chủ thể được cấp quyền. Ngược lại, vô hiệu hóa một account tại một nền tảng không bảo đảm mọi credential độc lập hoặc quyền cục bộ trên các nền tảng khác đã mất hiệu lực.

### 2.1. Service account, service principal và workload identity

Ba thuật ngữ hay xuất hiện trong tài liệu nhưng chỉ những lớp khác nhau:

- **Service account:** tài khoản dành cho phần mềm hoặc automation, không phải tài khoản cá nhân. Tùy nền tảng, account có thể là một object danh tính riêng, tên người dùng kỹ thuật hoặc đối tượng Kubernetes ServiceAccount.
- **Service principal:** principal được hệ thống danh tính/ủy quyền sử dụng để biểu diễn một ứng dụng hay workload. Đây thường là đối tượng nhận vai trò và chính sách trong hệ thống IAM cụ thể.
- **Workload identity:** cơ chế hoặc mô hình gắn danh tính cho một workload đang chạy, có thể dựa vào môi trường thực thi và token ngắn hạn thay vì khóa chia sẻ lưu lâu dài.

Tên và quan hệ chính xác phụ thuộc nhà cung cấp. Không nên suy ra rằng một “service account” ở mọi môi trường đều có cùng khả năng đăng nhập, đồng bộ, cấp token hoặc gán chính sách.

### 2.2. Danh tính con người và danh tính dịch vụ

| Khía cạnh | Danh tính con người | Danh tính dịch vụ |
|---|---|---|
| Nguồn thẩm quyền | HR, hợp đồng, hệ thống khách hàng/đối tác | Danh mục ứng dụng, kho cấu hình, CI/CD, chủ hệ thống được duyệt |
| Bằng chứng xác thực | Mật khẩu, passkey, MFA, thiết bị | Workload token, chứng chỉ, federated identity, secret |
| Chủ sở hữu | Người được định danh; có quản lý hoặc đơn vị nghiệp vụ | Nhóm/cá nhân chịu trách nhiệm vận hành và phê duyệt |
| Sự kiện thay đổi | Tuyển dụng, chuyển vai trò, nghỉ việc | Tạo ứng dụng, thay môi trường/chức năng, chuyển đội, ngừng triển khai |
| Phát hiện rủi ro | Tài khoản cũ, quyền dư, đăng nhập bất thường | Secret lưu lâu, khóa không có chủ, đặc quyền quá rộng, workload đã ngừng mà quyền còn |
| Kết thúc vòng đời | Chặn quyền của người đã rời tổ chức | Thu hồi trust, credential, quyền, tài khoản và phụ thuộc của workload đã kết thúc |

Danh tính dịch vụ **không thể làm MFA như người dùng tương tác**. Thay vào đó, hệ thống phải xác thực nguồn gốc workload và môi trường thực thi bằng cơ chế phù hợp, chẳng hạn chứng chỉ, token có thời hạn ngắn hoặc liên kết danh tính giữa hai nền tảng.

## 3. Mô hình dữ liệu tối thiểu của service identity

Chỉ có tên tài khoản “bot-prod” là chưa đủ để quản lý vòng đời. Một bản ghi định danh dịch vụ nên chứa ít nhất:

1. **ID ổn định** để tham chiếu xuyên hệ thống, tránh phụ thuộc tên hiển thị có thể đổi.
2. **Loại và mục đích sử dụng:** dịch vụ web, batch job, pipeline, agent, tích hợp đối tác…
3. **Chủ sở hữu:** đội vận hành, người phê duyệt, chủ hệ thống; có người thay thế khi chủ chính rời tổ chức.
4. **Phạm vi:** ứng dụng, môi trường (dev/staging/prod), tenant, hệ thống đích, tài nguyên được dùng.
5. **Nguồn cấp danh tính:** nền tảng chạy workload hoặc hệ thống nào có thẩm quyền phát/ghi nhận danh tính.
6. **Phương thức xác thực:** federated token, managed identity, mTLS, secret hoặc API key; ngày hết hạn và cách rotation nếu có.
7. **Quyền và điều kiện:** vai trò, scope, ràng buộc resource, thời hạn, ngữ cảnh truy cập.
8. **Trạng thái vòng đời:** đề xuất, đã duyệt, hoạt động, tạm khóa, ngừng sử dụng, thu hồi hoàn tất.
9. **Dấu vết quản trị:** yêu cầu tạo, phê duyệt, lần cập nhật, lần dùng gần nhất, kết quả rà soát và bằng chứng thu hồi.

Ví dụ dưới đây là **mô hình minh họa**, không phải schema bắt buộc của một nền tảng IAM:

~~~json
{
  "identityId": "svc-4d71",
  "displayName": "inventory-sync-prod",
  "kind": "WORKLOAD",
  "application": "inventory-platform",
  "environment": "production",
  "ownerTeam": "platform-integration",
  "ownerContact": "team-owned-oncall",
  "trustSource": "production-kubernetes-cluster",
  "subject": "system:serviceaccount:inventory:sync-worker",
  "allowedAudience": "inventory-api",
  "authenticationMethod": "WORKLOAD_IDENTITY_FEDERATION",
  "entitlements": [
    {"resource": "inventory-api", "action": "read:stock"}
  ],
  "status": "ACTIVE",
  "reviewRequired": true
}
~~~

Trong ví dụ, *subject* xác định workload bên trong Kubernetes, còn *audience* là dịch vụ dự kiến nhận token. Việc hệ thống thực sự tin cậy subject và audience phải dựa trên một cấu hình quan hệ tin cậy có kiểm soát, không phải chỉ nhờ dữ liệu JSON tự khai báo.

**Nguyên tắc quan trọng:** cần phân biệt **định danh chuẩn trong danh mục IAM** và **định danh kỹ thuật tại từng nền tảng**. Hai định danh này có thể khác chuỗi ký tự nhưng phải ánh xạ rõ ràng để truy vết quyền và thao tác thu hồi.

## 4. Một service identity được xác thực như thế nào?

Trong mô hình chung, một workload chứng minh mình là tác nhân đã được đăng ký; hệ thống xác thực kiểm chứng bằng chứng, rồi cấp quyền hoặc phát hành token để workload gọi tài nguyên đích.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant T as Nền tảng tin cậy / IdP / STS
    participant A as API đích
    participant L as Audit log
    W->>T: Cung cấp bằng chứng workload
    T->>T: Xác minh issuer, subject, audience, trust policy
    T-->>W: Token ngắn hạn giới hạn phạm vi
    W->>A: Gọi API kèm token
    A->>A: Kiểm tra chữ ký, thời hạn, audience, quyền
    A-->>W: Trả kết quả hoặc từ chối
    A->>L: Ghi principal, hành động, tài nguyên, quyết định
~~~

Sơ đồ là mô hình tổng quát: nếu dùng mTLS hoặc API key, bước xác thực và cách mang credential sẽ khác. Các môi trường có thể dùng một hoặc nhiều hệ thống quản lý danh tính, không nhất thiết phải có một IdP duy nhất.

### 4.1. API key hoặc secret tĩnh

Một dịch vụ có thể được cấp API key hoặc client secret để chứng minh quyền gọi API. Ưu điểm là dễ tích hợp, nhưng rủi ro nằm ở thời gian tồn tại dài, khả năng bị sao chép và khó xác định nơi đang sử dụng.

Nếu bắt buộc dùng secret tĩnh:

- Cấp riêng cho từng workload, môi trường và mục đích; tránh một secret chung cho toàn công ty.
- Lưu trong secret manager hoặc cơ chế bảo vệ chuyên dụng; không commit vào repository, image, tài liệu hoặc log.
- Giới hạn quyền, thu hẹp nguồn gọi và đặt ngày hết hạn nếu nền tảng cho phép.
- Thiết kế rotation an toàn, bao gồm giai đoạn chuyển đổi và xác minh credential cũ đã bị vô hiệu hóa.
- Giám sát các lần dùng bất thường hoặc key tồn tại mà không có chủ sở hữu.

Không dùng API key làm căn cứ duy nhất để khẳng định tác nhân là ứng dụng nào nếu nhiều ứng dụng cùng có thể đọc hoặc sao chép key đó.

### 4.2. OAuth 2.0 cho giao tiếp máy với máy

Với luồng **client credentials**, một client đã được đăng ký xác thực với authorization server để xin access token cho API. Token có thể chứa các scope phù hợp với mục đích của dịch vụ, ví dụ quyền đọc dữ liệu tồn kho.

Điều cần phân biệt:

- Client credentials đại diện cho **client/application**, không đại diện cho một người dùng đang đăng nhập.
- Authorization server quyết định cấp token; API vẫn phải kiểm tra chữ ký/cơ chế xác minh token, issuer, audience, thời hạn và quyền cần thiết.
- Cách client xác thực (secret, private key, mTLS…) và vòng đời credential cần quản lý riêng.
- Token còn hiệu lực có thể tiếp tục được dùng theo chính sách và khả năng thu hồi của hệ thống, ngay cả sau khi cấu hình tài khoản đã thay đổi.

Không nên nhúng token tĩnh vào source code hoặc coi access token là một định danh ổn định có thể tái sử dụng vô hạn.

### 4.3. Workload identity federation và credential ngắn hạn

Khi hỗ trợ, hệ thống có thể **tin cậy định danh do môi trường thực thi phát hành**: ví dụ token của job CI/CD hoặc service account trong Kubernetes. Workload trao đổi bằng chứng đó để nhận token truy cập tài nguyên bên ngoài theo chính sách.

Phương án này thường giúp giảm nhu cầu phát secret dài hạn cho từng job. Tuy nhiên, federated identity chỉ an toàn khi quan hệ tin cậy được ràng buộc đủ chặt:

- **Issuer:** nguồn phát hành bằng chứng phải được tin cậy.
- **Subject:** chỉ workload/repository/namespace/service account được chỉ định.
- **Audience:** token phải được phát hành cho đối tượng nhận phù hợp.
- **Thời hạn:** token sống ngắn; bên nhận kiểm tra hiệu lực.
- **Ngữ cảnh:** môi trường, nhánh triển khai, tenant, điều kiện khác khi cơ chế hỗ trợ.

Ví dụ: job triển khai production chỉ được quyền khi token phát từ workflow đã định danh và chạy trên nhánh/tag được phê duyệt; workflow của nhánh thử nghiệm không được mặc nhiên chia sẻ quyền production.

### 4.4. Chứng chỉ và mTLS

Với **mutual TLS (mTLS)**, cả client và server có thể trình chứng chỉ, giúp xác thực hai đầu giao tiếp. Một hệ thống cấp danh tính workload có thể cung cấp chứng chỉ ngắn hạn gắn với định danh dịch vụ, hạn chế rủi ro phát khóa thủ công.

Trong mô hình dùng **SPIFFE**, workload có thể nhận định danh dạng SPIFFE ID và sử dụng cơ chế tin cậy tương ứng, chẳng hạn hạ tầng SPIRE, để cấp/xoay vòng tài liệu danh tính. Đây là một lựa chọn thiết kế, không phải điều kiện bắt buộc của mọi hệ thống IAM.

**Xác thực thành công vẫn chưa đồng nghĩa có quyền thực hiện mọi hành động.** Phân quyền theo tài nguyên và điều kiện vẫn cần ở API hoặc tầng kiểm soát truy cập.

## 5. Service identity trong bối cảnh IdP, SSO, SCIM, RBAC và ABAC

Các thành phần IAM thường được nhắc cùng nhau nhưng đảm nhiệm vai trò khác nhau.

| Thành phần | Đóng góp cho định danh dịch vụ | Điểm cần lưu ý |
|---|---|---|
| **IdP / IAM** | Đăng ký principal, quản lý quan hệ tin cậy, credential, role và phát hành token tùy nền tảng | Phải biết principal nào đang đại diện workload nào |
| **SSO** | Chủ yếu hỗ trợ người dùng đăng nhập tập trung vào ứng dụng | Không tự cấp định danh cho mọi workload hay bảo đảm thu hồi API key và phiên máy với máy |
| **SCIM** | Có thể tự động hóa provisioning danh tính và nhóm ở hệ thống có hỗ trợ | Không mặc nhiên quản lý toàn bộ service principal, workload token hoặc quyền cloud của mọi nền tảng |
| **RBAC** | Gán vai trò định nghĩa trước cho principal dịch vụ | Role cấp quá rộng gây rủi ro khi workload bị chiếm quyền |
| **ABAC** | Quyết định theo thuộc tính danh tính, tài nguyên, hành động và ngữ cảnh | Phải tin cậy các thuộc tính dùng xét chính sách |
| **Access review / audit** | Xác minh quyền và chủ sở hữu còn phù hợp; lưu bằng chứng | Cần hoàn tất cả bước thực thi thu hồi, không dừng ở nút “đã duyệt” |

### 5.1. RBAC: phân quyền theo vai trò dịch vụ

Ví dụ, IAM cấp role “inventory-reader” cho dịch vụ đồng bộ kho. Role cho phép đọc số lượng tồn và không cho phép thay đổi giá bán hay xóa sản phẩm.

Ưu điểm: vai trò dễ quản lý nhất quán cho nhiều workload cùng nhóm trách nhiệm. Nhược điểm: nếu role gom cả quyền đọc và ghi chỉ để phục vụ một vài ứng dụng, mọi workload được gán role có thể nhận dư quyền.

### 5.2. ABAC: giới hạn quyền theo thuộc tính và ngữ cảnh

Trong trường hợp nhiều môi trường, có thể thêm điều kiện:

- Thuộc tính principal: **environment = production**, **service = inventory-sync**.
- Thuộc tính tài nguyên: **project = inventory**, **environment = production**.
- Hành động: chỉ **read**.
- Điều kiện sử dụng: token do issuer tin cậy phát, audience phù hợp, principal đang hoạt động.

RBAC thường trả lời **vai trò này được làm những gì**; ABAC bổ sung **trong điều kiện và phạm vi nào**. Hệ thống có thể kết hợp hai cách nếu nền tảng hỗ trợ.

### 5.3. Hai danh tính trong một yêu cầu “thay mặt người dùng”

Giả sử một người dùng đăng nhập vào website để yêu cầu tải báo cáo. Backend gọi API tạo báo cáo. Khi kiểm toán, cần phân biệt:

1. **Danh tính dịch vụ:** backend đã gọi API bằng quyền của workload nào?
2. **Danh tính người yêu cầu:** người nào khởi tạo hành động này, có được phép đọc báo cáo không?

Nếu backend chỉ dùng service identity quyền rất rộng rồi tin mọi dữ liệu do client gửi, hệ thống dễ xảy ra lỗi phân quyền. Nếu giao thức hỗ trợ delegated access hoặc token exchange, việc ủy quyền phải được xác minh chính thức; không tùy ý coi một header tự khai báo là bằng chứng danh tính người dùng.

Nhật ký nên phản ánh cả **actor kỹ thuật** và **người khởi tạo/ngữ cảnh được ủy quyền**, phù hợp mức độ dữ liệu được phép lưu.

## 6. Vòng đời Joiner – Mover – Leaver của định danh dịch vụ

JML không chỉ áp dụng cho người lao động. Định danh dịch vụ cũng được tạo khi workload ra đời, thay đổi khi nhiệm vụ/môi trường đổi và thu hồi khi workload kết thúc.

| Giai đoạn | Sự kiện ví dụ | Kiểm soát bắt buộc |
|---|---|---|
| **Joiner** | Đăng ký microservice mới hoặc job tích hợp | Có chủ sở hữu, mục đích, nguồn tin cậy, quyền tối thiểu, phê duyệt và bằng chứng cấp phát |
| **Mover** | Chuyển đội quản lý, thêm API, đổi môi trường chạy hoặc tách hệ thống | Đánh giá quyền hiện tại, cập nhật quan hệ tin cậy/credential, thu hồi quyền không còn cần |
| **Leaver** | Ngừng service, xóa pipeline, hết hợp đồng tích hợp | Chặn sử dụng danh tính, thu hồi credential và quyền, xử lý tài nguyên phụ thuộc, đối soát hệ thống đích |

### 6.1. Joiner: đăng ký dịch vụ trước khi cấp quyền

Quy trình tham khảo:

1. **Đề nghị tạo:** chủ hệ thống cung cấp ứng dụng, mục đích, owner, môi trường và tài nguyên cần gọi.
2. **Xác thực nguồn gốc workload:** liên kết service với repository, pipeline, cluster hoặc nền tảng chạy đã được phê duyệt.
3. **Đánh giá chính sách:** chọn quyền tối thiểu, thời hạn, môi trường và điều kiện; kiểm tra xung đột vai trò nếu liên quan.
4. **Cấp định danh và credential:** ưu tiên cơ chế không dùng secret dài hạn khi hạ tầng hỗ trợ; nếu dùng secret thì có chính sách lưu trữ và rotation.
5. **Xác minh tại đích:** thử truy cập hợp lệ và kiểm tra các hành động ngoài phạm vi bị từ chối.
6. **Đăng ký vận hành:** bổ sung vào inventory, chủ sở hữu, ngày rà soát và cơ chế cảnh báo.

Danh tính cần được tạo theo quy trình chính thức trước khi cấp quyền production. Tránh cho nhân viên tự tạo service account quyền quản trị rồi bàn giao bằng tin nhắn.

### 6.2. Mover: thay đổi mà không cộng dồn quyền

Một job trước đây chỉ đọc bảng kiểm thử, nay được chuyển sang tổng hợp báo cáo tài chính. Nếu chỉ thêm quyền đọc dữ liệu tài chính mà không thu hồi quyền kiểm thử cũ, sẽ xuất hiện **quyền tồn dư**.

Mover của dịch vụ có thể yêu cầu:

- Thay đổi người/đội chịu trách nhiệm và xác minh người kế nhiệm thực sự nhận quản trị.
- Đánh giá quyền cũ và mới theo nhiệm vụ, tài nguyên và môi trường.
- Cập nhật issuer/subject/trust policy nếu workload chuyển sang cluster hoặc pipeline khác.
- Xoay vòng/thu hồi credential cũ khi thay đổi kiến trúc, người quản trị bí mật hoặc điểm tích hợp.
- Giới hạn thời gian chồng lấn để duy trì dịch vụ, có phê duyệt và hạn chót rõ ràng.
- Kiểm tra rằng quyền ở hệ thống cũ đã thực sự bị thu hồi.

Dùng duy nhất một định danh có đặc quyền ở **dev, staging và production** khiến ranh giới môi trường bị xóa nhòa. Thông thường nên tách principal và quyền giữa các môi trường khi phạm vi tin cậy và tác động rủi ro khác nhau.

### 6.3. Leaver: dừng workload không có nghĩa là đã thu hồi quyền

Khi một dịch vụ bị ngừng triển khai, service identity có thể tiếp tục tồn tại trong IdP, cloud IAM, API gateway hoặc hệ thống đích. Cần đóng vòng đời có kiểm chứng:

1. Xác nhận dịch vụ đã hết nhu cầu, ai phê duyệt ngừng và những hệ thống phụ thuộc.
2. Chặn việc phát sinh phiên/token mới theo khả năng của hệ thống.
3. Thu hồi các trust binding, role, nhóm, policy và entitlement ở từng đích.
4. Vô hiệu hóa/thu hồi secret, API key, khóa SSH, chứng chỉ và cơ chế federation có liên quan.
5. Xử lý thời hạn còn sống của token/phiên đã phát hành; áp dụng biện pháp khẩn cấp nếu rủi ro đòi hỏi.
6. Chuyển giao quyền sở hữu tài nguyên (dữ liệu, hàng đợi, job, artifact) theo kế hoạch.
7. Đối soát trạng thái từng hệ thống và ghi rõ những khoản thu hồi đang chờ xử lý.
8. Lưu bằng chứng rồi mới xóa bản ghi kỹ thuật theo chính sách lưu giữ.

Một sự kiện thu hồi có thể hoàn tất ở cloud nhưng chưa hoàn tất ở ứng dụng legacy. IAM phải phản ánh trạng thái **thu hồi một phần** và giao trách nhiệm xử lý, không tuyên bố “đã vô hiệu hóa” cho toàn hệ thống.

## 7. Ví dụ thực tế: định danh cho job CI/CD

Một tổ chức dùng pipeline tự động để triển khai web API lên môi trường production. Trước đây, pipeline lưu một khóa truy cập cloud tồn tại vô thời hạn và có quyền quản trị toàn bộ tài khoản.

### 7.1. Phân tích điểm yếu

- **Khó truy vết:** tất cả job dùng cùng khóa thì audit khó biết workflow nào thực thi.
- **Phạm vi quyền quá rộng:** khóa có thể thay đổi cả những tài nguyên không liên quan đến web API.
- **Secret lưu lâu:** nếu khóa bị lộ trong log, biến môi trường hoặc artifact, kẻ tấn công có thể tiếp tục sử dụng.
- **Leaver không hiệu quả:** xóa pipeline chưa chắc xóa khóa đã được cấp từ trước.

### 7.2. Thiết kế lại theo mô hình định danh dịch vụ

~~~mermaid
flowchart LR
    A[Pipeline đã được phê duyệt] --> B[Token định danh workload]
    B --> C[Trust policy kiểm tra issuer, subject, audience]
    C --> D[STS / hệ thống phát token]
    D --> E[Credential ngắn hạn]
    E --> F[Deploy role giới hạn tài nguyên ứng dụng]
    F --> G[API quản lý triển khai]
    G --> H[Nhật ký principal và deployment]
~~~

Giải pháp có thể áp dụng khi hạ tầng hỗ trợ workload federation:

- Mỗi pipeline/môi trường được xác định rõ, chẳng hạn danh tính riêng cho staging và production.
- Hệ thống tin cậy chỉ chấp nhận token từ workflow và ngữ cảnh được phê duyệt; không cho mọi pipeline tùy ý nhận quyền production.
- Quyền triển khai chỉ gắn với tài nguyên cần cập nhật, không cấp vai trò quản trị tổng quát.
- Token sống ngắn, được phát khi job chạy, không lưu khóa truy cập dài hạn trong repository.
- Nhật ký ghi workload principal, workflow, bản triển khai và quyền đã sử dụng.
- Khi pipeline bị ngừng, thu hồi trust binding và role; đối soát để không còn quyền tồn dư.

**Khi chưa thể dùng federation**, vẫn có thể dùng service principal với credential do secret manager quản lý, rotation, phân quyền tối thiểu và giám sát. Mục tiêu là kiểm soát được vòng đời và nguồn gốc quyền truy cập.

## 8. Ví dụ thực tế: Kubernetes ServiceAccount và quyền cloud

Một Pod trong namespace **orders** cần đọc một hàng đợi trong cloud. Kubernetes ServiceAccount giúp gắn danh tính Kubernetes cho Pod. Tùy nền tảng cloud, có thể cấu hình quan hệ tin cậy để workload sử dụng danh tính đó xin quyền ở cloud.

Ví dụ manifest cấu trúc cơ bản:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-consumer
  namespace: orders
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
    spec:
      serviceAccountName: order-consumer
      containers:
        - name: worker
          image: registry.example.org/orders/consumer:1.0.0
~~~

Đoạn YAML này chỉ minh họa cách Pod sử dụng **một Kubernetes ServiceAccount cụ thể**; **nó chưa tự cấu hình quyền cloud hay trust federation**. Cần bổ sung cấu hình danh tính và policy theo nền tảng, bao gồm ràng buộc issuer, namespace, service account subject, audience và quyền truy cập tài nguyên.

Một số lưu ý quan trọng:

- Kubernetes ServiceAccount mặc định không mang nghĩa “có quyền truy cập cloud”; quyền cloud chỉ có nếu cơ chế tích hợp và policy được cấu hình.
- Không dùng một ServiceAccount dùng chung cho mọi Pod có chức năng và mức tin cậy khác nhau.
- Quyền Kubernetes RBAC và quyền trên API cloud là **hai miền phân quyền** cần kiểm soát riêng.
- Khi xóa Pod, ServiceAccount, cloud principal hoặc quan hệ trust có thể vẫn còn; cần quản lý vòng đời chúng như các đối tượng độc lập.
- Tránh ghi token của Pod vào log và tránh sao chép token sang môi trường không được phê duyệt.

## 9. Kiểm toán và phát hiện định danh dịch vụ tồn dư

Một service identity có thể còn khả năng truy cập dù không có người dùng “sở hữu” theo cách truyền thống. Vì thế, tổ chức cần **inventory toàn bộ NHI** và đối soát với hệ thống đang chạy.

### 9.1. Những dấu hiệu cần rà soát

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Service account không có owner | Nhóm tạo đã giải thể hoặc người quản lý nghỉ việc | Xác minh workload thực tế, chỉ định owner hoặc lên kế hoạch thu hồi |
| Credential sống lâu, chưa xoay vòng | Phụ thuộc vào secret tĩnh | Đánh giá thay bằng token ngắn hạn; thực hiện rotation có kiểm thử |
| Quyền production cho workload staging | Sao chép vai trò qua môi trường | Tách principal, role và trust theo môi trường |
| Không ghi nhận hoạt động trong thời gian dài | Workload bị ngừng hoặc chỉ chạy hiếm khi | Xác nhận bằng chủ hệ thống và lịch vận hành trước khi vô hiệu hóa |
| Key có nhiều hệ thống cùng sử dụng | Dùng account chia sẻ để đơn giản tích hợp | Tạo danh tính riêng để truy vết và thu hồi độc lập |
| Quyền ở API legacy còn dù IdP đã khóa | Chưa tích hợp provisioning/thu hồi | Xác minh và xử lý trực tiếp ở ứng dụng đích |
| Token dùng sai audience hoặc nguồn | Cấu hình trust quá rộng, token bị dùng nhầm | Kiểm tra issuer/subject/audience và thắt chặt chính sách |

**Không thấy đăng nhập gần đây không đủ để kết luận tài khoản có thể xóa ngay.** Có những job chỉ chạy mỗi quý hoặc được dùng trong tình huống khẩn cấp. Cần kết hợp bằng chứng kỹ thuật với xác nhận của owner và kế hoạch dự phòng.

### 9.2. Bằng chứng kiểm toán nên có

Một bản ghi cấp/đổi/thu hồi service identity nên truy ngược được:

- **Nguồn sự kiện:** yêu cầu ứng dụng, ticket, deployment hoặc quyết định ngừng hệ thống.
- **Chủ sở hữu và người phê duyệt:** ai chịu trách nhiệm sử dụng, ai duyệt quyền nhạy cảm.
- **Tác nhân và quyền:** identity ID, tài nguyên, hành động, điều kiện, thời điểm có hiệu lực.
- **Thực thi:** hệ thống nào đã nhận thay đổi, trạng thái thành công/thất bại, mã đối soát.
- **Kết quả cuối:** readback cho thấy quyền thực sự đã cấp hoặc đã thu hồi.
- **Đường dẫn điều tra:** correlation ID gắn yêu cầu nghiệp vụ, deployment và nhật ký tài nguyên đích.

Ví dụ cấu trúc sự kiện minh họa:

~~~json
{
  "eventId": "iam-nhi-0217",
  "identityId": "svc-4d71",
  "eventType": "REVOKE_ENTITLEMENT",
  "trigger": "WORKLOAD_RETIRED",
  "approvedBy": "service-owner",
  "targetResource": "inventory-api",
  "requestedPermission": "read:stock",
  "executionStatus": "SUCCESS",
  "verificationStatus": "CONFIRMED_REVOKED",
  "correlationId": "change-2981"
}
~~~

Dữ liệu minh họa không mang token, private key hoặc credential thô. Nhật ký thực tế cần tuân thủ chính sách bảo vệ thông tin, thời hạn lưu giữ và quyền truy cập audit.

### 9.3. Các chỉ số đánh giá

Một số chỉ số phù hợp để theo dõi theo thời gian:

1. **Tỷ lệ danh tính có owner hợp lệ** trên tổng số định danh dịch vụ phát hiện được.
2. **Tỷ lệ NHI dùng credential ngắn hạn hoặc cơ chế không lưu secret dài hạn**, với mẫu số và ngoại lệ được xác định.
3. **Số entitlement trái chính sách** được phát hiện sau thay đổi hoặc ngừng workload.
4. **Thời gian thu hồi đã xác minh** từ thời điểm Leaver có hiệu lực tới khi tài nguyên đích xác nhận.
5. **Tỷ lệ hoàn tất access review**, tính cả việc thực thi quyết định chứ không chỉ phê duyệt.
6. **Số định danh/credential không còn liên kết workload còn hoạt động** sau khi đã đối soát với chủ hệ thống.

Các chỉ số cần phân nhóm theo môi trường và mức độ nhạy cảm; không nên coi số lượng identity ít nhất là mục tiêu, vì nhiều dịch vụ chia sẻ một identity còn làm tăng rủi ro.

## 10. Những sai lầm thiết kế phổ biến

### “Mọi dịch vụ dùng chung một tài khoản sẽ dễ quản lý hơn”

Ngắn hạn có thể ít tài khoản hơn, nhưng khó truy vết từng workload, khó thu hồi độc lập và thường tạo quyền quá rộng. Nên tách danh tính theo ranh giới tin cậy và chức năng.

### “Dùng service account thì không cần xác minh owner”

Một tài khoản phi con người vẫn phải có **người/nhóm chịu trách nhiệm**. Nếu không có owner, không ai có đủ ngữ cảnh để phê duyệt thay đổi, xác minh hết nhu cầu hoặc xử lý sự cố credential.

### “Có token hợp lệ thì API nào cũng phải chấp nhận”

Sai. API đích phải xác minh nguồn phát hành, audience, thời hạn và quyền cần thiết. Token dành cho API A không nên tự động có hiệu lực ở API B chỉ vì chữ ký hợp lệ.

### “Service identity chỉ là một tài khoản trong IdP”

Thiếu. Nó còn liên quan đến workload thực tế, trust binding, quyền cục bộ, credential, môi trường, owner và bằng chứng đối soát trên hệ thống đích.

### “Xóa Deployment là hoàn tất Leaver”

Deployment có thể biến mất nhưng ServiceAccount, principal cloud, secret, policy hoặc token đã cấp vẫn tồn tại. Phải rà soát những đối tượng này theo vòng đời riêng.

### “Luân chuyển secret luôn là đủ”

Rotation giảm thời gian một khóa bị lộ có hiệu lực, nhưng không giải quyết được quyền quá rộng, account dùng chung hoặc trust policy sai. Cần kiểm soát cả **danh tính, cấp quyền, credential, vòng đời và kiểm toán**.

## 11. Checklist thiết kế định danh dịch vụ

Dùng các câu hỏi sau khi thêm một service, bot hoặc pipeline vào IAM:

| Câu hỏi | Dấu hiệu đáp ứng |
|---|---|
| Workload nào cần định danh? | Có ứng dụng, runtime, môi trường và mục đích rõ ràng |
| Ai là owner và ai duyệt quyền? | Có owner nhóm/cá nhân, người thay thế và quy trình phê duyệt |
| Nó chứng minh danh tính bằng cách nào? | Cơ chế trust rõ; hạn chế secret dài hạn; có rotation/expiry khi cần |
| Nó được truy cập gì? | Chính sách giới hạn tài nguyên, hành động, môi trường và thời hạn |
| Có tách production với môi trường khác? | Không để một principal không kiểm soát dùng quyền trên nhiều môi trường |
| Có kiểm tra ở hệ thống đích? | Readback xác nhận cả cấp quyền hợp lệ và thu hồi |
| Khi ứng dụng đổi vai trò, ai thu hồi quyền cũ? | Mover có bước đánh giá và xử lý quyền tồn dư |
| Khi dịch vụ ngừng, danh tính bị xử lý ra sao? | Leaver có phụ thuộc, credential, trust, role và bằng chứng đầy đủ |
| Có truy vết yêu cầu thay mặt người dùng? | Audit phân biệt service actor và user/delegated context khi áp dụng |

## 12. Tình huống tự kiểm tra

**Tình huống A:** Một job staging dùng chung principal với job production. Cả hai đều có quyền ghi lên bucket production. Khi staging bị lộ thông tin, nguy cơ nào xuất hiện?

**Phân tích:** Quyền sản xuất có thể bị lợi dụng qua workload ít được bảo vệ hơn. Cần tách danh tính và policy theo môi trường, chỉ cấp quyền phù hợp và giới hạn trust source.

**Tình huống B:** Dịch vụ đã ngừng chạy ba tháng nhưng tài khoản IAM và API key của nó vẫn tồn tại. Có thể xóa ngay không?

**Phân tích:** Trước hết xác minh chủ hệ thống, lịch chạy và phụ thuộc để tránh gián đoạn những tác vụ ít xuất hiện. Khi có quyết định Leaver, chặn truy cập, thu hồi key, quyền và trust binding rồi kiểm chứng trạng thái tại các đích.

**Tình huống C:** API nhận một access token có chữ ký hợp lệ nhưng token được phát cho API khác. Có nên chấp nhận?

**Phân tích:** Không. Phải kiểm tra audience, issuer, thời hạn và quyền; chữ ký hợp lệ chỉ là một phần của xác minh.

**Tình huống D:** Backend dùng service identity để lấy báo cáo theo yêu cầu của người dùng. Backend có thể bỏ qua quyền của người dùng không?

**Phân tích:** Không. Backend cần kiểm tra người dùng được phép truy cập báo cáo nào và ghi nhận mối quan hệ giữa user request với hành động của service; quyền của workload không tự động thay thế quyền của user.

---

**Ghi nhớ:** Định danh dịch vụ là **một danh tính được quản trị xuyên vòng đời**, chứ không đơn thuần là mật khẩu dùng cho chương trình. Thiết kế tốt phải xác định chính xác workload, owner, nguồn tin cậy, credential, quyền truy cập và cách xác minh thu hồi. Áp dụng Joiner–Mover–Leaver cho danh tính phi con người giúp hệ thống IdP/IAM, chính sách RBAC/ABAC, cơ chế cấp token và quy trình kiểm toán cùng hướng tới mục tiêu giảm quyền truy cập tồn dư.
