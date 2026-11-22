# Rà soát quyền định kỳ và quy trình truy cập khẩn cấp

## 1. Mục tiêu và tình huống xuyên suốt

Một hệ thống Oracle Cloud Infrastructure (OCI) có thể được phân quyền hợp lý lúc triển khai nhưng dần tích lũy quyền thừa: nhân sự chuyển nhóm vẫn giữ quyền production, tài khoản pipeline không còn chủ sở hữu hoặc một lần cấp quyền xử lý sự cố chưa được thu hồi. Đồng thời, tổ chức vẫn cần khôi phục truy cập khi nhà cung cấp danh tính bên ngoài gặp lỗi hoặc người quản trị thường trực không sẵn sàng.

Trong chương **An toàn thông tin và kiểm toán** của module `CLOUD_PROVIDERS_ORACLE`, bài này kết nối hai công việc: định kỳ xác nhận quyền còn cần thiết và chuẩn bị đường truy cập khẩn cấp có kiểm soát. Phạm vi bao gồm tenancy, compartment, IAM, các danh tính triển khai hạ tầng và bằng chứng vận hành cho workload OCI.

Sau bài học, người học có thể:

- Lập phạm vi rà soát cho người dùng, nhóm, policy, vai trò identity domain và danh tính máy.
- Truy ngược nguồn tạo ra quyền hiệu lực, kể cả quyền kế thừa hoặc nhận qua nhóm khác.
- Ghi quyết định giữ, giảm hoặc thu hồi quyền kèm người chịu trách nhiệm và bằng chứng thực thi.
- Thiết kế truy cập khẩn cấp khi đường cấp quyền thông thường còn hoạt động hoặc đã gặp sự cố.
- Kiểm chứng thu hồi quyền, đóng sự cố và duy trì khả năng khôi phục truy cập.

**Tình huống:** doanh nghiệp vận hành một ứng dụng Java trong compartment `ProductionApps`. Ứng dụng dùng Compute, Object Storage và cơ sở dữ liệu Oracle; nhóm mạng quản lý VCN ở một compartment khác. Nhân viên đăng nhập qua IdP của doanh nghiệp, còn pipeline triển khai có danh tính riêng. Cuối quý, đội bảo mật phát hiện một kỹ sư đã chuyển nhóm vẫn có quyền cập nhật hạ tầng production. Trong một sự cố khác, IdP không khả dụng khiến người trực không đăng nhập được OCI Console.

Hai tình huống cần chung một nền tảng: biết quyền đến từ đâu, ai chịu trách nhiệm và bằng chứng nào chứng minh quyền đã được kiểm soát.

## 2. Rà soát quyền phải xem quyền hiệu lực

### 2.1. Mô hình một quyết định truy cập

Có thể mô tả đường cấp quyền như sau:

```text
Danh tính hoặc tài nguyên gọi API
→ Nhóm, ánh xạ federation hoặc dynamic group
→ Policy statement và điều kiện áp dụng
→ Loại tài nguyên, thao tác và phạm vi compartment
→ Quyền có thể sử dụng trong tình huống cụ thể
```

Đối với quản trị identity domain, cần thêm đường cấp quyền qua administrator role. Không nên dùng một danh sách thành viên nhóm làm đại diện cho tất cả quyền.

Một ví dụ policy để đọc thông tin Compute:

```text
Allow group Workforce/ProdObservers to read instance-family in compartment ProductionApps
```

`Workforce` và `ProdObservers` là tên domain và nhóm minh họa. OCI cho phép định danh nhóm bằng cặp domain/nhóm hoặc OCID; cần lưu đúng định danh để tránh nhầm các nhóm có tên giống nhau ở hai domain. [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

Khi reviewer đánh giá dòng policy này, các câu hỏi cần trả lời gồm: ai thuộc nhóm, nhu cầu đọc còn tồn tại không, phạm vi compartment có phù hợp không và người đó còn nhận quyền mạnh hơn từ nơi khác không.

### 2.2. Quyền cộng dồn và kế thừa

Các policy OCI IAM cấp quyền bằng statement `Allow`. Quyền cần cho một thao tác có thể đến từ nhiều statement hoặc nhiều nhóm; thêm một policy hẹp không tự triệt tiêu quyền rộng đã được cấp ở nơi khác. Cần loại bỏ hoặc thu hẹp đường cấp quyền không còn phù hợp. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm).

Compartment con nhận ảnh hưởng của policy áp dụng từ phạm vi cha. Vì vậy, rà soát riêng policy nằm tại `ProductionApps` có thể bỏ sót một quyền cấp từ tenancy hoặc compartment tổ tiên. [Oracle: Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

Ví dụ kỹ sư An có hai đường truy cập:

```text
An → Workforce/ProdObservers → đọc Compute ở ProductionApps
An → Workforce/LegacyOperators → quản trị Compute ở phạm vi cha
```

Xóa An khỏi `ProdObservers` chưa loại bỏ quyền quản trị. Kết luận thu hồi phải dựa vào tập đường cấp quyền còn lại và một phép kiểm chứng thực tế phù hợp.

### 2.3. Phân biệt quản trị domain với quản trị tenancy

Vai trò quản trị identity domain và policy quản lý tài nguyên OCI có phạm vi khác nhau. Administrator role có thể cho phép quản lý người dùng, nhóm, ứng dụng hoặc cấu hình xác thực trong domain; các quyền này cũng phải nằm trong đợt rà soát. [Oracle: Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm).

Default identity domain chứa nhóm `Administrators` với quyền quản trị tenancy. Ngược lại, quyền quản trị một domain khác không tự đồng nghĩa quản trị toàn tenancy. OCI yêu cầu nhóm `Administrators` luôn có ít nhất một thành viên; không dùng việc xóa thành viên cuối cùng làm biện pháp kết thúc truy cập khẩn cấp. [Oracle: The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm).

Với ứng dụng Java trong bài, quyền quản lý một DB system qua OCI cũng cần được phân biệt với tài khoản SQL, database role, tài khoản hệ điều hành và quyền bên trong ứng dụng. Đợt rà soát phải ghi rõ lớp nào đã được kiểm tra, lớp nào có quy trình riêng.

## 3. Chốt phạm vi, trách nhiệm và chu kỳ

### 3.1. Đơn vị rà soát

Đơn vị review hữu ích là một quan hệ cấp quyền có đủ ngữ cảnh:

```text
Danh tính + nguồn cấp quyền + phạm vi tài nguyên
+ nhu cầu công việc + người phê duyệt + bằng chứng
```

Một dòng chỉ ghi tên người và chữ “đồng ý” không giúp giải thích người đó được làm gì hoặc cách thu hồi.

| Đối tượng | Nội dung cần rà soát |
| --- | --- |
| Nhân viên và nhà thầu | Trạng thái công việc, nhóm, domain, phạm vi production, thời hạn |
| Nhóm người dùng | Thành viên, nguồn đồng bộ, chủ sở hữu, policy liên quan |
| Policy | Subject, thao tác, resource type, compartment, điều kiện và quyền kế thừa |
| Vai trò quản trị domain | Người hoặc nhóm được gán, nhu cầu và khả năng thay đổi xác thực |
| Danh tính pipeline | Chủ sở hữu, cách xác thực, môi trường và quyền triển khai |
| Dynamic group | Matching rule, tài nguyên hiện tại và tài nguyên có thể gia nhập |
| Credential | Loại, chủ sở hữu, trạng thái, nơi sử dụng và phương án thay thế |
| Tài khoản khẩn cấp | Khả năng sử dụng, người bảo quản, đường đăng nhập và giám sát |
| Truy cập liên tenancy | Bên nhận quyền, phạm vi, mục đích và hiệu lực thỏa thuận |

Đối với credential, chỉ thu metadata cần thiết như ID, fingerprint, thời điểm tạo hoặc người chịu trách nhiệm. Báo cáo review không cần private key, password, auth token hay secret thực tế.

### 3.2. Phân công rõ người quyết định và người thực hiện

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Chủ workload | Xác nhận nhu cầu công việc và ảnh hưởng khi giảm quyền |
| Quản lý nhân sự hoặc nhà thầu | Xác nhận tình trạng làm việc và thay đổi vai trò |
| Reviewer bảo mật | Đánh giá mức quyền, xung đột trách nhiệm và ngoại lệ |
| Quản trị IAM hoặc tự động hóa | Thực hiện thay đổi tại đúng nguồn cấp quyền |
| Người xác minh độc lập | Đọc lại cấu hình và kiểm tra kết quả thu hồi |
| Chủ quy trình khẩn cấp | Duy trì tài khoản dự phòng, diễn tập và đóng sự cố |

Với quyền đặc biệt, tránh để một người tự yêu cầu, tự phê duyệt, tự thực hiện và tự kết luận hoàn thành. Trong đội nhỏ, có thể gộp một số vai trò nhưng cần ghi nhận người kiểm tra độc lập và thời điểm kiểm tra.

### 3.3. Lịch dựa trên rủi ro

Ví dụ lịch nội bộ có thể là review hằng tháng cho quyền quản trị mạnh, mỗi quý cho quyền thông thường và review ngay khi nhân sự rời tổ chức, đổi vai trò hoặc kết thúc hợp đồng. Đây là **lịch minh họa**, không phải thời hạn bắt buộc chung của OCI.

Một sự kiện cần thu hồi khẩn không được chờ tới kỳ tiếp theo. Đợt rà soát định kỳ bổ sung khả năng phát hiện quyền bị bỏ sót; quy trình nghỉ việc hoặc ứng cứu phải xử lý theo thời hạn riêng.

Khi thay đổi policy quan trọng, matching rule, mapping IdP hoặc phạm vi compartment, nên kích hoạt review bổ sung cho nhóm bị ảnh hưởng thay vì chỉ chờ lịch cố định.

## 4. Thu thập dữ liệu đủ để ra quyết định

### 4.1. Ghi nhận phạm vi và giới hạn của bản chụp

Mỗi lần thu thập cần có thời điểm UTC, tenancy, domain, compartment, danh tính thu thập, nguồn dữ liệu và giới hạn quyền nhìn thấy. Khi API trả lỗi hoặc reviewer không có quyền xem một phạm vi, đánh dấu **chưa kiểm tra được**; không diễn giải thành “không có quyền cấp”.

Nên đối chiếu các nguồn sau:

- Dữ liệu nhân sự, chủ hợp đồng và danh sách người trực.
- Người dùng, nhóm, membership, administrator role và mapping IdP.
- Policy ở tenancy, các compartment tổ tiên và phạm vi workload.
- Matching rule cùng danh sách tài nguyên liên quan tới danh tính máy.
- Audit, hoạt động đăng nhập và lịch sử thay đổi.
- Ticket cấp quyền, ngoại lệ, lịch sử triển khai và nhu cầu kinh doanh.

Bản chụp tại một thời điểm có thể nhanh chóng lỗi thời. Khi thực hiện thu hồi sau nhiều ngày, đọc lại đường cấp quyền trước khi thay đổi và kiểm tra những thay đổi phát sinh sau thời điểm chụp.

### 4.2. Ví dụ đọc policy bằng OCI CLI

Các lệnh sau là ví dụ đọc dữ liệu để người học sử dụng trong môi trường đã được cấp quyền. Chúng không tự xác định toàn bộ quyền hiệu lực.

```powershell
$ReviewProfile = '<OCI-CLI-profile-duoc-cap-quyen-doc>'
$IamRegion = '<region-endpoint-IAM-phu-hop>'
$TenancyId = '<OCID-tenancy>'
$ParentCompartmentId = '<OCID-compartment-cha>'
$WorkloadCompartmentId = '<OCID-ProductionApps>'

$PolicyScopeIds = @(
  $TenancyId
  $ParentCompartmentId
  $WorkloadCompartmentId
) | Select-Object -Unique

foreach ($PolicyScopeId in $PolicyScopeIds) {
  Write-Output "Policy scope: $PolicyScopeId"
  oci iam policy list `
    --compartment-id $PolicyScopeId `
    --all `
    --profile $ReviewProfile `
    --region $IamRegion

  if ($LASTEXITCODE -ne 0) {
    throw "Khong doc duoc policy scope: $PolicyScopeId"
  }
}
```

Bổ sung tất cả compartment tổ tiên nếu cây có nhiều mức. `--all` lấy các trang kết quả của lần gọi đó; nó không tự duyệt mọi compartment. `policy list` trả policy nằm trong compartment được chỉ định, và phải đọc statement để phân tích đối tượng được cấp quyền. [Oracle CLI: policy list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/policy/list.html).

### 4.3. Đọc đúng identity domain

Ví dụ liệt kê người dùng bằng endpoint của domain cần rà soát:

```powershell
$ReviewProfile = '<OCI-CLI-profile-duoc-cap-quyen-doc>'
$IdentityDomainEndpoint = '<URL-endpoint-identity-domain>'

oci identity-domains users list `
  --endpoint $IdentityDomainEndpoint `
  --all `
  --profile $ReviewProfile

if ($LASTEXITCODE -ne 0) {
  throw 'Khong doc duoc danh sach nguoi dung trong domain.'
}
```

Lệnh yêu cầu endpoint của identity domain; một domain không đại diện cho toàn bộ danh tính trong tenancy. Kết quả người dùng cũng chưa thay thế danh sách nhóm, membership, role và ứng dụng. [Oracle CLI: identity-domains users list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/identity-domains/users/list.html).

Nếu quyền được đồng bộ từ IdP hoặc hệ thống quản trị danh tính, ghi rõ nguồn nào có thẩm quyền. Xóa membership ở OCI nhưng giữ nguyên quyền tại nguồn đồng bộ có thể khiến quyền quay lại ở lần đồng bộ tiếp theo.

### 4.4. Không kết luận chỉ từ lần đăng nhập cuối

Không thấy đăng nhập Console không chứng minh một danh tính không hoạt động: pipeline hoặc người dùng có thể gọi API bằng credential khác. Ngược lại, có hoạt động gần đây cũng không chứng minh quyền rộng còn cần thiết.

Hãy dùng log để bổ sung ngữ cảnh cho nhu cầu công việc. Với quyền dự phòng, ít sử dụng có thể là đúng thiết kế; cần kiểm tra chủ sở hữu, mục đích và khả năng sử dụng thay vì tự động xóa theo một tiêu chí “không đăng nhập”.

## 5. Ra quyết định, thực thi và xác minh

### 5.1. Câu hỏi dành cho reviewer

Với mỗi quan hệ cấp quyền, reviewer cần trả lời:

1. Danh tính và người chịu trách nhiệm có còn hợp lệ không?
2. Nhiệm vụ nào đòi hỏi quyền này, ở môi trường nào?
3. Thao tác và phạm vi có thể giảm không?
4. Có đường cấp quyền rộng khác hoặc quyền thay đổi cơ chế cấp quyền không?
5. Nguồn cấp quyền thực sự nằm ở OCI, IdP hay hệ thống khác?
6. Nếu giảm quyền, luồng vận hành nào cần kiểm chứng?
7. Khi nào cần xem lại hoặc tự động kết thúc quyền tạm?

Đặc biệt đánh giá quyền quản lý membership, credential, policy và cấu hình xác thực. Những quyền này có thể làm thay đổi khả năng truy cập của người khác, nên tác động của chúng rộng hơn tên vai trò nghiệp vụ gợi ý.

### 5.2. Phân loại kết quả

| Kết quả | Điều kiện ghi nhận | Bước tiếp theo |
| --- | --- | --- |
| Giữ | Có nhu cầu, phạm vi phù hợp, chủ sở hữu rõ | Ghi lý do và ngày review tiếp theo |
| Giảm | Cần truy cập nhưng mức hoặc phạm vi quá rộng | Thiết kế quyền thay thế, kiểm chứng rồi bỏ đường cấp rộng |
| Thu hồi | Không còn nhu cầu hoặc danh tính không hợp lệ | Thực hiện tại nguồn, đọc lại và thử quyền |
| Ngoại lệ có hạn | Có nhu cầu tạm và rủi ro được chấp nhận | Ghi người phê duyệt, biện pháp bù đắp và hạn kết thúc |
| Chưa quyết định | Thiếu chủ sở hữu hoặc bằng chứng | Giao người xử lý, thời hạn và biện pháp trong khi chờ |

Không tự chuyển các mục quá hạn thành “giữ”. Một mục chỉ có quyết định thu hồi vẫn là công việc đang mở cho tới khi thay đổi được thực hiện và kiểm chứng.

### 5.3. Đường hoàn thành một mục review

```mermaid
flowchart LR
    A[Thu thập quan hệ cấp quyền] --> B[Reviewer xác nhận nhu cầu]
    B --> C[Quyết định và lý do]
    C --> D[Thay đổi tại nguồn cấp quyền]
    D --> E[Đọc lại cấu hình]
    E --> F[Kiểm chứng quyền và workload]
    F --> G[Đóng mục review với bằng chứng]
```

Với An trong tình huống đầu bài, kết quả có thể là bỏ membership nhóm vận hành production tại nguồn IdP, giữ quyền đọc cho nhiệm vụ hỗ trợ mới, kiểm tra mapping và xác nhận không còn đường quản trị kế thừa. Không cần xóa toàn bộ tài khoản nếu An vẫn đang làm việc và còn nhiệm vụ hợp lệ.

Ngược lại, khi nhân sự rời tổ chức, phạm vi xử lý có thể gồm danh tính, credential và phiên truy cập theo hệ thống liên quan. Đổi mật khẩu Console không tự chứng minh API key, auth token hoặc tài khoản cơ sở dữ liệu riêng đã bị vô hiệu hóa.

Sau thay đổi, ghi nhận thời gian lan truyền và kiểm tra bằng đúng loại truy cập cần thu hồi. Không giả định mọi phiên, token hoặc cache mất hiệu lực ngay lập tức. Khi nghi ngờ credential bị lộ, dùng quy trình ứng cứu để kiểm tra và xử lý từng loại credential, thay vì chỉ gỡ một membership.

## 6. Danh tính máy và quyền quản trị gián tiếp

Một dynamic group xác định thành viên theo matching rule; tài nguyên mới đáp ứng điều kiện có thể trở thành principal nhận quyền. Vì vậy, review phải đánh giá cả **ai đang khớp** và **tài nguyên nào có thể khớp trong tương lai**. [Oracle: Managing Dynamic Groups](https://docs.oracle.com/iaas/Content/Identity/dynamicgroups/managingdynamicgroups.htm).

Ví dụ một rule minh họa:

```text
ALL {instance.compartment.id = '<OCID-compartment-pipeline>'}
```

Rule này cần được đánh giá cùng quyền tạo và quản trị instance ở compartment đó. Nếu phạm vi thành viên quá rộng so với mục đích pipeline, chủ workload phải đề xuất điều kiện phù hợp và kiểm chứng tác động lên các tác vụ hợp lệ.

| Đối tượng máy | Câu hỏi bổ sung |
| --- | --- |
| Pipeline triển khai | Danh tính có riêng cho từng môi trường không? Ai quản lý cấu hình và credential? |
| Instance principal | Workload nào dùng quyền? Ai có thể tạo hoặc điều khiển instance liên quan? |
| Resource principal | Resource type, compartment và điều kiện có đúng mục đích không? |
| Credential tích hợp | Hệ thống nào đang dùng? Có thể thay thế và thu hồi mà không dừng dịch vụ không? |
| Ứng dụng trong domain | Quyền quản trị hoặc quyền ứng dụng được gán cho ai? |

Sau khi đổi matching rule, không kiểm chứng quá sớm rồi kết luận thay đổi không hiệu quả. Oracle nêu thời gian khoảng một giờ để thay đổi matching rule có hiệu lực; kế hoạch thu hồi cần tính đến đặc điểm này. [Oracle: Updating Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/Updating_Dynamic_Groups.htm).

Các trường hợp cần kiểm tra chặt gồm danh tính có thể cập nhật policy của chính workload, người có quyền điều khiển tài nguyên nhận quyền mạnh và tài khoản tích hợp dùng chung cho nhiều ứng dụng. Mục tiêu của review là xác định phạm vi thực tế và phương án giảm quyền phù hợp, đồng thời giữ được các luồng hợp lệ.

## 7. Hai hình thức truy cập khẩn cấp

### 7.1. Quyền tạm thời khi hệ thống cấp quyền còn hoạt động

Ví dụ người trực cần thay một instance lỗi, còn IdP và quy trình IAM vẫn sử dụng được. Có thể cấp quyền có phạm vi cho danh tính cá nhân hoặc nhóm trực đã chuẩn bị trước, gắn với incident và thời hạn. Mức quyền phải bám thao tác cần khôi phục, không mặc định dùng toàn quyền tenancy.

Hồ sơ cần chỉ rõ ai hoặc cơ chế nào thu hồi khi hết thời hạn. Một timestamp trong ticket hoặc tên nhóm có chữ `Temporary` không tự làm membership hay OCI policy hết hiệu lực. Nếu tổ chức dùng tự động hóa hoặc điều kiện thời gian, phải kiểm chứng rằng chúng thực sự giới hạn quyền và có người xử lý khi bước thu hồi lỗi.

### 7.2. Tài khoản khôi phục khi đường đăng nhập chính lỗi

Khi IdP bên ngoài không khả dụng, yêu cầu thêm thành viên qua chính IdP đó có thể không thực hiện được. Cần một đường đăng nhập cục bộ được chuẩn bị từ trước và không phụ thuộc cùng điểm lỗi. Oracle khuyến nghị giữ khả năng dùng tài khoản quản trị local cho tình huống federation gặp sự cố, đồng thời kiểm soát việc tiếp cận credential và theo dõi hoạt động. [Oracle: IAM Federation](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Federation.htm).

Trong mô hình tài khoản khẩn cấp quản trị tenancy, Oracle mô tả user local ở Default identity domain, thuộc nhóm `Administrators`, được bảo vệ bằng MFA và giám sát việc sử dụng. Yếu tố xác thực cần sẵn sàng khi xảy ra sự cố; khóa bảo mật FIDO được lưu giữ có kiểm soát là một lựa chọn được tài liệu đề cập. [Oracle: Managing Emergency Access Accounts in OCI](https://www.oracle.com/a/ocom/docs/security/oci-iam-emergency-access-accounts-v1.8.pdf).

Tài khoản này có thể giữ quyền quản trị thường trực để khôi phục khi cần. Đối tượng được giới hạn thời gian trong vận hành là **quyền tiếp cận và sử dụng tài khoản cho từng sự cố**, cùng các quyền bổ sung đã cấp trong lúc xử lý. Không giả định quyền quản trị của tài khoản tự biến mất khi đóng ticket.

| Thuộc tính | Cấp quyền tạm cho người trực | Tài khoản khôi phục local |
| --- | --- | --- |
| Tình huống | Đường cấp quyền thông thường còn dùng được | Đường đăng nhập hoặc quản trị chính bị gián đoạn |
| Danh tính | Cá nhân được ghi nhận rõ | Tài khoản chuyên dụng, có người sử dụng được ghi nhận theo incident |
| Phạm vi | Giới hạn theo thao tác và workload | Có thể là quản trị tenancy để phục hồi đường truy cập |
| Chuẩn bị trước | Nhóm, policy, phê duyệt và cơ chế thu hồi | Tài khoản, xác thực, bảo quản và đường đăng nhập đã thử |
| Kết thúc | Thu hồi quyền được cấp cho incident | Kết thúc phiên, xử lý credential và đưa về trạng thái dự phòng |

Đường local vẫn phụ thuộc dịch vụ OCI IAM và các thành phần hạ tầng liên quan. Nó không bảo đảm truy cập nếu chính dịch vụ xác thực OCI bị gián đoạn, cũng không bỏ qua Security Zones hoặc ràng buộc của từng dịch vụ.

## 8. Chuẩn bị khả năng khôi phục trước sự cố

### 8.1. Lập bản đồ phụ thuộc

Đội vận hành nên đánh giá các phụ thuộc của đường khẩn cấp:

```text
Người trực được ủy quyền
→ Lấy được runbook và thông tin tenancy/domain
→ Tiếp cận được credential qua cơ chế bảo quản
→ Sử dụng được yếu tố MFA
→ Tới được đường đăng nhập local
→ Thực hiện được thao tác khôi phục
→ Người giám sát nhận được thông báo và bằng chứng
```

Với mỗi mũi tên, đặt câu hỏi: nếu IdP doanh nghiệp hoặc tài khoản của người quản trị chính không hoạt động thì bước này còn thực hiện được không? Nếu cần đăng nhập SSO mới đọc được runbook, mở kho bí mật hoặc nhận mã xác thực, đường dự phòng vẫn có thể bị khóa cùng hệ thống chính.

Không cần loại bỏ mọi phụ thuộc bằng mọi giá. Cần xác định điểm lỗi chung, phương án thay thế phù hợp và chứng minh chúng trong một lần diễn tập.

### 8.2. Bảo quản và quy trách nhiệm

Thiết kế đề xuất cho tổ chức:

- Có người sở hữu tài khoản, người quản lý vật liệu xác thực và người thay thế khi vắng mặt.
- Việc tiếp cận credential có nhật ký, incident ID, người nhận và thời gian trả về trạng thái bảo quản.
- Với quyền rất mạnh, áp dụng kiểm tra của người thứ hai theo khả năng vận hành của đội.
- Phương thức khôi phục tài khoản, email liên quan và thay đổi MFA cũng được kiểm soát.
- Không dùng tài khoản khẩn cấp cho công việc hằng ngày hoặc tác vụ pipeline.
- Không tạo API key thường trực cho tài khoản này chỉ để thuận tiện đăng nhập tự động.

Các điểm trên là thiết kế quy trình đề xuất, cần được điều chỉnh theo tổ chức. Nếu nhiều người có thể sử dụng cùng tài khoản chuyên dụng, log principal đơn lẻ chưa xác định người đang thao tác; phải liên kết với nhật ký bàn giao, thời điểm và incident. Không dùng tài khoản đó làm danh tính dùng chung cho sinh hoạt vận hành thông thường.

### 8.3. Kiểm tra cấu hình đăng nhập

Trước khi đưa đường khẩn cấp vào sử dụng, kiểm chứng tài khoản active, mật khẩu khả dụng, MFA đã đăng ký và sign-on policy cho phép cách đăng nhập dự kiến. Đánh giá điều kiện mạng, thứ tự rule và những ràng buộc có thể vô tình chặn người trực.

Khi sửa cấu hình có nguy cơ khóa quản trị, giữ một phiên quản trị đang hoạt động và kiểm thử bằng phiên trình duyệt độc lập trước khi kết thúc phiên cũ. Một phiên đã đăng nhập từ trước không chứng minh đường đăng nhập mới vẫn dùng được.

MFA cho Console cũng không thay thế việc kiểm soát credential API. Phạm vi của policy MFA cho OCI Console là truy cập Console; review phải xét loại xác thực thực sự dùng ở mỗi đường truy cập. [Oracle: IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

### 8.4. Chuẩn bị thông báo và giám sát

Một lần sử dụng tài khoản khẩn cấp cần được người giám sát biết tới, kể cả đăng nhập để diễn tập. Đội vận hành nên kiểm chứng phát hiện cho các tình huống:

- Đăng nhập thành công hoặc nhiều lần thất bại bất thường.
- Đổi mật khẩu, phương thức khôi phục hoặc MFA.
- Thay đổi membership, role hoặc policy liên quan tài khoản.
- Tạo credential mới trong cửa sổ xử lý sự cố.
- Dùng tài khoản ngoài cửa sổ đã ghi nhận.

Chọn tích hợp cảnh báo phù hợp với nguồn sự kiện được hỗ trợ trong tenancy và kiểm thử thông báo từ đầu đến cuối. Có thể chuyển tới hệ thống giám sát hoặc người trực qua dịch vụ thông báo, nhưng một email đã được cấu hình chưa chứng minh người cần xử lý thực sự nhận được nó. Cần đo độ trễ và có kênh thay thế phù hợp với sự cố IdP đang xét.

## 9. Runbook kích hoạt, sử dụng và kết thúc

### 9.1. Điều kiện kích hoạt

Các ví dụ hợp lệ theo quy trình nội bộ có thể gồm mất đăng nhập do IdP, cấu hình quyền làm nhóm vận hành không thực hiện được thao tác phục hồi hoặc người giữ quyền quản trị cần thiết không sẵn sàng trong sự cố nghiêm trọng.

Không dùng cơ chế khẩn cấp để giải quyết sự bất tiện thông thường, né review hoặc thực hiện yêu cầu chưa có căn cứ. Khi còn đường cấp quyền có phạm vi hoạt động, ưu tiên đường đó theo thiết kế của tổ chức.

### 9.2. Các bước vận hành

| Bước | Việc cần làm | Bằng chứng tối thiểu |
| --- | --- | --- |
| 1. Mở incident | Mô tả ảnh hưởng, mục tiêu khôi phục và đường truy cập bị lỗi | Incident ID, thời gian, phạm vi |
| 2. Chọn đường truy cập | Quyền tạm có phạm vi hoặc tài khoản khôi phục local | Lý do lựa chọn và thao tác cần làm |
| 3. Ghi nhận ủy quyền | Xác định người thao tác, người theo dõi, cửa sổ và điểm dừng | Người chịu trách nhiệm, thời hạn, kênh liên lạc |
| 4. Kích hoạt | Cấp quyền tạm hoặc bàn giao quyền dùng tài khoản đã chuẩn bị | Thời điểm và danh tính thực hiện |
| 5. Kiểm tra ban đầu | Xác nhận đúng tenancy, domain, compartment và principal | Kết quả kiểm tra, trạng thái trước thay đổi |
| 6. Khôi phục | Thực hiện thao tác cần thiết, ghi thay đổi theo thời gian | Request ID, tài nguyên bị ảnh hưởng, kết quả |
| 7. Bàn giao lại | Kiểm chứng đường truy cập bình thường và sức khỏe workload | Người xác nhận và phép kiểm chứng |
| 8. Kết thúc quyền | Thu hồi quyền tạm, xử lý phiên và credential liên quan | Cấu hình sau thay đổi, kết quả kiểm tra |
| 9. Đóng và đánh giá | Hoàn tất bằng chứng, đánh giá độc lập và việc cần cải tiến | Biên bản đóng, chủ công việc còn mở |

Nếu người phê duyệt chính không sẵn sàng, runbook phải có người thay thế hoặc cơ chế ủy quyền đã được thống nhất trước. Không để một đường dự phòng kỹ thuật tồn tại nhưng không có ai được phép quyết định sử dụng trong thời gian cần thiết.

### 9.3. Kỷ luật trong cửa sổ khẩn cấp

Người thực hiện chỉ xử lý mục tiêu đã xác định, ghi các thay đổi liên quan và dừng khi phát sinh yêu cầu ngoài phạm vi để người phụ trách đánh giá. Nếu cửa sổ kết thúc mà chưa khôi phục xong, cần ghi quyết định gia hạn, chủ sở hữu mới hoặc phương án thay thế.

Không ghi secret vào ticket, ảnh chụp màn hình hoặc lịch sử lệnh được chia sẻ. Bằng chứng nên chứa thời gian, loại thao tác, resource ID và kết quả đủ để điều tra.

Một thay đổi khẩn cấp có thể tạo tài nguyên mới, backup, log hoặc quyền cho một nhóm hỗ trợ. Ghi rõ chúng để bước đóng sự cố còn biết cần thu hồi hoặc dọn dẹp gì và tránh chi phí tồn đọng.

### 9.4. Đóng sự cố theo đúng loại truy cập

**Với quyền tạm:** gỡ membership, role hoặc statement được cấp riêng cho incident ở đúng nguồn; kiểm tra không còn đường quyền thay thế ngoài dự kiến; thực hiện các bước xử lý phiên, token hoặc credential mà thiết kế yêu cầu.

**Với tài khoản khôi phục:** kết thúc các phiên liên quan bằng cơ chế được hỗ trợ, xử lý credential đã sử dụng hoặc phát sinh, cập nhật nơi bảo quản và kiểm chứng đường dự phòng còn hoạt động. Việc đổi mật khẩu không tự chứng minh mọi phiên hoặc credential khác đã bị thu hồi.

Không xóa hoặc vô hiệu hóa tài khoản khôi phục duy nhất chỉ vì sự cố đã đóng. Cần giữ khả năng quản trị dự phòng, đồng thời loại bỏ quyền tạm cấp cho các danh tính khác và mọi thay đổi ngoài thiết kế.

## 10. Bằng chứng kiểm toán và chỉ số vận hành

### 10.1. Liên kết quyết định với hành động

Một gói bằng chứng đủ dùng nên nối được:

```text
Đợt review hoặc incident
→ Danh tính và đường cấp quyền
→ Quyết định cùng người chịu trách nhiệm
→ Thay đổi thực tế
→ Trạng thái sau thay đổi
→ Phép kiểm chứng và người xác nhận
```

Trong OCI Audit, tìm theo đúng compartment, khoảng thời gian và thao tác; chú ý quy đổi múi giờ khi đối chiếu với nhật ký nội bộ. Oracle nêu log thường được bổ sung trong khoảng 15 phút sau API call nhưng thời gian xử lý có thể thay đổi. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Không có log trong một lần tìm kiếm chưa chứng minh thao tác không xảy ra. Trước tiên kiểm tra phạm vi, quyền đọc, nguồn sự kiện, độ trễ và thời gian UTC.

Đối với tích hợp log identity domain, không xây mới dựa vào giả định endpoint `AuditEvents` cũ còn nhận dữ liệu mới. Oracle thông báo endpoint này và một số template Reports API ngừng trả dữ liệu mới sau ngày 15/12/2024, hướng tới OCI Audit. Cần kiểm tra nguồn dữ liệu mà tích hợp của tổ chức đang sử dụng. [Oracle: Using the Audit Event APIs](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/usingauditeventapis.htm).

### 10.2. Các chỉ số có ý nghĩa

| Chỉ số | Cách hiểu |
| --- | --- |
| Tỷ lệ phạm vi được thu thập | Phần đối tượng thực sự có dữ liệu trên tổng phạm vi dự kiến |
| Tỷ lệ review đã xác minh | Phần mục đã quyết định, thực thi và kiểm chứng hoàn tất |
| Số quyết định thu hồi chưa thực thi | Công việc còn mở dù reviewer đã chọn thu hồi |
| Thời gian hoàn tất thu hồi | Từ quyết định tới lúc xác minh quyền không còn dùng được |
| Ngoại lệ quá hạn | Quyền hết thời hạn được chấp nhận nhưng chưa xử lý xong |
| Lần dùng tài khoản khẩn cấp chưa giải trình | Hoạt động chưa liên kết được với incident hợp lệ |
| Thời gian lấy lại truy cập | Từ kích hoạt tới lúc thực hiện được thao tác khôi phục đã định |
| Kết quả diễn tập | Truy cập được, cảnh báo tới nơi và kết thúc đúng trạng thái |

Ví dụ, một đợt có 100 mục, reviewer đã quyết định cả 100 nhưng 8 quyết định thu hồi chưa áp dụng. Không báo cáo 100% hoàn thành kiểm soát; phải tách tỷ lệ ra quyết định với tỷ lệ đã xác minh thực thi.

## 11. Thực hành: review và thu hồi trong compartment lab

### 11.1. Chuẩn bị

Sử dụng một compartment lab, một danh tính thử riêng và một Compute instance lab đã được chuẩn bị. Không dùng tài khoản khẩn cấp quản trị tenancy thật cho bài kiểm tra membership này.

Điều kiện:

- Người quản trị lab có quyền tạo nhóm và cấp quyền trong phạm vi được giao.
- Danh tính thử không thuộc nhóm quản trị và không có đường đọc instance từ nơi khác.
- Có profile CLI xác thực đúng danh tính thử; nếu dùng user local, cấu hình xác thực theo chính sách tổ chức.
- Biết OCID instance, compartment, identity domain và region của lab.
- Có người ghi nhận trạng thái trước và sau thay đổi.

Lab không yêu cầu tạo thêm tài nguyên Compute nếu đã có tài nguyên thử thích hợp. Mục tiêu là kiểm tra quyền bằng thao tác đọc, tránh dùng thao tác xóa hoặc thay đổi trạng thái instance làm phép thử phủ định.

### 11.2. Tạo một mục review

Ví dụ ghi nhận ngay trong phiếu thực hành:

```text
Review ID: AR-LAB-001
Danh tinh: user-lab-review
Domain: LabDomain
Nguon cap quyen: membership truc tiep cua nhom LabComputeReaders
Tai nguyen: mot Compute instance thu trong compartment lab
Nhu cau: doc thong tin instance de xac minh sau trien khai
Quyet dinh sau bai thu: thu hoi vi ket thuc nhiem vu
Nguoi thuc hien: quan tri lab
Nguoi xac minh: reviewer duoc phan cong
```

Đây là mẫu thông tin minh họa, không chứa credential. Nếu thực hành ở domain có đồng bộ từ bên ngoài, phải xác định trước nơi thay đổi membership để tránh quyền bị đồng bộ lại.

### 11.3. Ba thời điểm kiểm chứng

Trên Console, quản trị viên tạo nhóm `LabComputeReaders` ở đúng domain và policy đọc instance trong compartment lab. Thay các tên trong ví dụ bằng giá trị thực:

```text
Allow group LabDomain/LabComputeReaders to read instances in compartment AccessReviewLab
```

Thực hiện phép kiểm tra bằng **profile của danh tính thử**:

```powershell
$LabProfile = '<profile-cua-user-lab-review>'
$LabRegion = '<region-cua-instance-lab>'
$LabInstanceId = '<OCID-instance-lab>'

oci compute instance get `
  --instance-id $LabInstanceId `
  --profile $LabProfile `
  --region $LabRegion

$AccessProbeExitCode = $LASTEXITCODE
Write-Output "Exit code: $AccessProbeExitCode"
```

| Thời điểm | Thao tác quản trị | Kỳ vọng khi chạy lệnh bằng danh tính thử |
| --- | --- | --- |
| A. Chưa có membership | Chưa thêm user thử vào nhóm | Không đọc được instance do thiếu quyền |
| B. Trong nhiệm vụ | Thêm user thử vào nhóm đã cấp policy | Đọc được instance sau khi quyền có hiệu lực |
| C. Kết thúc nhiệm vụ | Gỡ user khỏi nhóm theo quyết định review | Không còn đọc được sau khi thay đổi có hiệu lực |

Phải xác nhận principal, target và đường xác thực ở cả ba thời điểm. Mã thoát khác không chỉ có ý nghĩa khi đã loại trừ sai region, sai OCID, lỗi mạng hoặc credential không hợp lệ. Đối chiếu thông báo và cấu hình để phân biệt lỗi xác thực với lỗi phân quyền.

Nếu thời điểm C vẫn đọc được, kiểm tra quyền từ nhóm khác, policy kế thừa, nguồn đồng bộ, thời gian lan truyền và phiên truy cập. Không cấp thêm quyền hoặc đổi profile sang quản trị để làm cho phép thử “đạt”.

### 11.4. Điều kiện hoàn thành lab

Một mục review đạt khi có đủ trạng thái trước thay đổi, quyết định thu hồi, người thực hiện, membership sau thay đổi và phép thử chứng minh quyền đã mất. Đồng thời kiểm tra policy lab không cấp quyền ngoài compartment dự kiến.

Sau đó dọn nhóm, policy và credential chỉ tạo cho bài thực hành theo phạm vi lab; không xóa tài nguyên dùng chung để luyện tập thu hồi. Nếu bước dọn dẹp còn mở, ghi rõ người chịu trách nhiệm và thời hạn.

## 12. Diễn tập sự cố IdP theo kịch bản có kiểm soát

Diễn tập đường khẩn cấp là một hoạt động riêng với lab membership. Không cần cố ý gây lỗi IdP production; có thể mô phỏng bằng cách yêu cầu người tham gia sử dụng đường đăng nhập local đã được chuẩn bị, trong một cửa sổ có người theo dõi.

Kịch bản đề xuất:

1. Mở incident diễn tập và thống nhất một thao tác đọc vô hại để chứng minh khả năng quản trị.
2. Người được phân công lấy runbook, thông tin tenancy/domain và vật liệu xác thực qua cơ chế dự phòng.
3. Đăng nhập bằng một phiên trình duyệt độc lập, thực hiện MFA và xác nhận đúng principal.
4. Kiểm tra người giám sát nhận được thông báo và nối được với incident.
5. Thực hiện thao tác đã định, ghi thời gian và bằng chứng.
6. Kết thúc phiên, xử lý credential theo runbook và hoàn trả trạng thái bảo quản.
7. Người xác minh kiểm tra không có quyền tạm hay credential mới bị bỏ lại.
8. Ghi thời gian thực hiện, điểm vướng và chủ công việc cải tiến.

Các điều kiện đạt cần bao gồm **truy cập được**, **theo dõi được** và **kết thúc được đúng trạng thái**. Chỉ kiểm tra rằng mật khẩu còn tồn tại trong kho không đủ chứng minh khả năng khôi phục.

Sau khi đổi MFA, mật khẩu, sign-on policy, người quản lý vật liệu xác thực hoặc cơ chế lưu giữ, nên diễn tập lại phần bị ảnh hưởng. Chọn chu kỳ diễn tập phù hợp với rủi ro và các thay đổi thực tế.

## 13. Khi cần tự động hóa bằng Access Governance

Oracle Access Governance hỗ trợ các chiến dịch review một lần, định kỳ và theo sự kiện, cùng các dạng review người dùng, policy hoặc nhóm quyền. Đây là khả năng bổ sung để tổ chức các đợt rà soát ở quy mô lớn; cần cấu hình kết nối và phạm vi trước khi coi dữ liệu là đầy đủ. [Oracle: Access Governance](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security-access-gov.htm).

Reviewer có thể đưa ra quyết định với identity access, group membership hoặc policy theo loại task và workflow được cấu hình. Tài liệu mô tả yêu cầu remediation được gửi tới hệ thống đích khi thu hồi. Khi vận hành, cần theo dõi kết quả tại hệ thống đích để biết thay đổi đã áp dụng được hay còn lỗi. [Oracle: Perform Access Reviews](https://docs.oracle.com/en-us/iaas/Content/access-governance/perform-access-reviews.htm).

Trước khi mở rộng tự động hóa, tổ chức nên kiểm chứng một chu trình đầy đủ:

```text
Thu dữ liệu từ nguồn
→ Reviewer nhìn đúng danh tính và quyền
→ Quyết định thu hồi
→ Hệ thống đích nhận thay đổi
→ Quyền thực sự không còn dùng được
→ Bằng chứng liên kết trở lại mục review
```

Không để khuyến nghị tự động thay thế việc xác nhận nhu cầu đối với quyền khẩn cấp ít sử dụng. Cũng cần dự toán chi phí dịch vụ, tích hợp và lưu bằng chứng theo cấu hình hiện hành; số công việc tự động hóa không tự chứng minh chi phí vận hành giảm.

## 14. Mẫu hồ sơ và tiêu chí áp dụng cho workload OCI

### 14.1. Mẫu tối thiểu cho một quan hệ cấp quyền

| Trường | Nội dung cần ghi |
| --- | --- |
| Review hoặc incident ID | Liên kết tới đợt rà soát hay sự cố |
| Subject | Loại principal, ID, domain và chủ sở hữu |
| Grant source | Nhóm, role, policy, mapping hoặc matching rule |
| Scope | Tenancy, compartment và loại tài nguyên |
| Business purpose | Nhiệm vụ cụ thể cần quyền |
| Decision | Giữ, giảm, thu hồi hoặc ngoại lệ |
| Decision owner | Người ra quyết định và lý do |
| Effective window | Thời hạn nếu có, cơ chế kết thúc và người xử lý lỗi |
| Implementation | Thay đổi thực tế, người thực hiện, thời gian và tham chiếu |
| Verification | Cấu hình đọc lại và phép kiểm chứng |
| Final state | Hoàn thành hoặc công việc còn mở |

### 14.2. Tiêu chí hoàn thành ở cấp hệ thống

Với ứng dụng Java trong bài, một chu kỳ kiểm soát đầy đủ cần chứng minh:

- Danh sách người và máy có quyền được đối chiếu với đúng domain, nguồn cấp quyền và compartment.
- Quyền của kỹ sư đã chuyển nhóm được xử lý tại nguồn, không còn đường quản trị production ngoài nhu cầu.
- Pipeline giữ được luồng triển khai hợp lệ sau khi giảm quyền và có chủ sở hữu rõ ràng.
- Quyền OCI đối với mạng, lưu trữ và cơ sở dữ liệu được phân biệt với quyền bên trong OS, database và ứng dụng.
- Đường khẩn cấp local hoạt động trong kịch bản IdP không dùng được, có người theo dõi và nhật ký quy trách nhiệm.
- Quyền tạm, phiên và credential liên quan sự cố được xử lý theo loại; khả năng khôi phục tenancy vẫn được duy trì.
- Kết quả review, remediation và diễn tập có bằng chứng cùng công việc cải tiến còn mở.

Rà soát quyền duy trì mức truy cập phù hợp với công việc hiện tại. Quy trình khẩn cấp duy trì khả năng khôi phục khi đường thông thường thất bại. Hai công việc liên kết ở bằng chứng: ai đã có quyền, vì sao cần quyền, quyền đã được sử dụng thế nào và trạng thái cuối có đúng thiết kế hay chưa.
