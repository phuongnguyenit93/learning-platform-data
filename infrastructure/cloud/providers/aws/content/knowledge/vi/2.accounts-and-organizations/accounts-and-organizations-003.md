# AWS Organizations, organizational unit và tài khoản thành viên

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao một hệ thống AWS phát triển lâu dài thường cần nhiều tài khoản thay vì gom mọi môi trường vào một tài khoản.
- Phân biệt **AWS Organization**, **organization root**, **organizational unit (OU)**, **management account** và **member account**.
- Thiết kế cây OU phù hợp với các nhóm tài khoản có yêu cầu bảo mật và vận hành khác nhau.
- Giải thích cách kế thừa chính sách trong Organizations, đặc biệt là mối quan hệ giữa **service control policy (SCP)** và quyền **IAM**.
- Mô tả quy trình thêm tài khoản, di chuyển giữa các OU và quản lý chi phí tập trung.

## 1. Vì sao cần AWS Organizations?

Giả sử một công ty vận hành ứng dụng thương mại điện tử trên AWS. Ban đầu, nhóm dùng một AWS account chứa cả môi trường phát triển, kiểm thử và production. Khi quy mô tăng, cách tổ chức này tạo ra các vấn đề:

1. **Phạm vi ảnh hưởng lớn:** cấu hình sai hoặc tài khoản bị xâm nhập có thể ảnh hưởng đến nhiều môi trường trong cùng account.
2. **Khó phân quyền:** lập trình viên cần quyền thử nghiệm ở dev nhưng không nên có quyền tương tự với production.
3. **Khó kiểm soát chi phí:** chi phí các đội, sản phẩm và môi trường bị trộn lẫn, dù vẫn có thể dùng tag để phân bổ.
4. **Khó chuẩn hóa vận hành:** mỗi account cần áp dụng các nguyên tắc như ghi log, bảo vệ dữ liệu và giới hạn thao tác nguy hiểm.
5. **Giới hạn tài nguyên:** nhiều quota của AWS được quản lý theo từng account và Region; tách account giúp quản lý từng workload rõ ràng hơn nhưng không loại bỏ mọi hạn mức.

**AWS Organizations** giải quyết bài toán quản trị **nhiều AWS account** từ một tổ chức chung. Nó cung cấp cây phân nhóm account, quản lý chính sách ở cấp tổ chức, tích hợp với một số dịch vụ AWS và hợp nhất thông tin thanh toán. Organizations không tự tạo mạng chung, không tự cấp quyền IAM cho người dùng và không tự triển khai ứng dụng.

Đây là nền tảng của cách tiếp cận **multi-account**, rất hữu ích khi học các chủ đề tiếp theo như IAM, VPC, dịch vụ tính toán, lưu trữ, giám sát và kiểm soát chi phí.

## 2. Các thành phần của một Organization

| Thành phần | Ý nghĩa | Cần nhớ |
| --- | --- | --- |
| **Organization** | Tập hợp các AWS account được quản lý chung. | Một Organization có một cây phân cấp duy nhất. |
| **Organization root** | Nút cao nhất của cây; được tạo khi tạo Organization. | Khác hoàn toàn với **root user** của một AWS account. |
| **Management account** | Account quản lý Organizations và chịu trách nhiệm thanh toán hợp nhất. | Nên hạn chế chạy workload thông thường tại đây. |
| **Member account** | Account thuộc Organization, dùng để chứa workload, dữ liệu và tài nguyên AWS. | Vẫn có ranh giới danh tính, quyền, tài nguyên và nhiều quota riêng. |
| **Organizational unit (OU)** | Nhóm các account hoặc OU con cùng nhu cầu quản trị. | OU giúp áp dụng chính sách chung; không phải một AWS account. |
| **Organization policy** | Chính sách áp dụng ở root, OU hoặc account tùy loại. | Mỗi loại chính sách có cơ chế và phạm vi tác động riêng. |

Một Organization có đúng **một management account** và **một root**, có thể có nhiều member account và OU. Mỗi account chỉ nằm trực tiếp dưới **một** phần tử cha trong cây: root hoặc một OU. OU có thể chứa các OU con, tối đa **năm cấp OU** bên dưới root.

### Ví dụ cây Organization

```text
Organization: ExampleCommerce
│
└── Root (r-xxxx)
    ├── Management account (billing + quản trị tổ chức)
    ├── OU: Security
    │   ├── Account: LogArchive
    │   └── Account: SecurityTooling
    ├── OU: Infrastructure
    │   └── Account: SharedNetworking
    ├── OU: Workloads
    │   ├── OU: Production
    │   │   ├── Account: StorefrontProd
    │   │   └── Account: PaymentsProd
    │   └── OU: NonProduction
    │       ├── Account: StorefrontDev
    │       └── Account: StorefrontTest
    └── OU: Sandbox
        └── Account: Experiment
```

Trong ví dụ trên:

- **Management account** dùng để quản lý tổ chức và thanh toán, không phải nơi chứa toàn bộ EC2, RDS hay VPC của công ty.
- **Security OU** tập trung những account phục vụ log và công cụ bảo mật để giảm sự phụ thuộc vào account chạy ứng dụng.
- **Production OU** có thể nhận chính sách chặt hơn **NonProduction OU**.
- **Sandbox OU** có thể hạn chế các dịch vụ hoặc thao tác không được phép trong môi trường thử nghiệm.

Các tên OU và account chỉ mang tính minh họa. Khi thiết kế thực tế, ưu tiên nhóm theo **mức độ kiểm soát và chức năng** (security, infrastructure, production, sandbox) hơn là sao chép nguyên sơ đồ phòng ban. Một OU không tạo ra mạng riêng hay hệ thống IAM riêng; những ranh giới đó chủ yếu nằm ở account và các dịch vụ được cấu hình bên trong.

### Phân biệt `root`, `root user` và `management account`

Ba khái niệm dễ bị nhầm:

- **Organization root:** đối tượng trong AWS Organizations, làm nút gốc của cây OU/account và là nơi có thể gắn chính sách cấp tổ chức.
- **Root user:** danh tính có đặc quyền cao nhất của **một AWS account**, gắn với email đăng ký account; không phải một OU hoặc đối tượng quản lý cây.
- **Management account:** AWS account tạo/quản lý Organization và chịu trách nhiệm thanh toán, có root user của chính account đó.

Không nên đăng nhập root user để làm việc hằng ngày. Sử dụng cơ chế truy cập quản trị được cấp quyền phù hợp, ưu tiên IAM Identity Center và MFA.

## 3. Management account và member account khác nhau thế nào?

| Khía cạnh | Management account | Member account |
| --- | --- | --- |
| Vai trò chính | Quản trị cấu trúc tổ chức, tính năng và thanh toán tập trung. | Chạy ứng dụng, lưu trữ dữ liệu, mạng, cơ sở dữ liệu hoặc dịch vụ dùng chung. |
| Hóa đơn | Chịu trách nhiệm thanh toán chi phí các member account theo cơ chế consolidated billing. | Phát sinh chi phí từ tài nguyên do account sử dụng. |
| Chính sách SCP | **Không bị SCP giới hạn** khi các principal thuộc management account thực hiện thao tác. | IAM principal và root user của member account chịu các SCP áp dụng; kể cả member account được chỉ định làm delegated administrator. |
| Tài nguyên | Có thể chứa tài nguyên AWS nhưng cần giới hạn để giảm rủi ro. | Có ranh giới tài nguyên, quyền và cấu hình riêng. |
| Quản trị truy cập | Có quyền thực hiện các tác vụ Organizations nếu danh tính có quyền cần thiết. | Có IAM riêng và có thể cho phép truy cập từ account khác bằng cross-account role. |

**Điểm quan trọng:** việc hai account cùng nằm trong một Organization **không mặc nhiên cho phép** người dùng ở account này truy cập tài nguyên account kia. Muốn truy cập xuyên account cần cấu hình quyền rõ ràng, chẳng hạn IAM role với trust policy và quyền `sts:AssumeRole`, hoặc cơ chế tương ứng của dịch vụ.

Để quản lý quyền đăng nhập của con người vào nhiều account, có thể tích hợp **AWS IAM Identity Center** với Organizations và phân bổ permission set đến các account. Organizations quản lý cấu trúc account; IAM/IAM Identity Center quản lý việc cấp quyền truy cập phù hợp.

## 4. Hai chế độ tính năng của AWS Organizations

| Chế độ | Có gì? | Khi nào dùng? |
| --- | --- | --- |
| **Consolidated billing features** | Gom thanh toán và theo dõi chi phí giữa các account. | Trường hợp chỉ cần hợp nhất hóa đơn. |
| **All features** | Bao gồm consolidated billing và những chức năng quản trị mở rộng như organization policies và tích hợp dịch vụ được hỗ trợ. | Lựa chọn phù hợp cho hầu hết mô hình multi-account cần bảo mật và quản trị tập trung. |

Khi tạo Organization hiện nay, **All features** là lựa chọn mặc định. Có thể nâng cấp từ consolidated billing lên all features, nhưng không chuyển ngược lại sau khi đã bật all features. Với account được mời tham gia, việc bật all features cho một tổ chức đang ở chế độ billing-only có thể cần sự xác nhận theo quy trình AWS.

Ví dụ, doanh nghiệp chỉ muốn gộp hóa đơn chưa cần SCP có thể bắt đầu ở consolidated billing. Khi cần áp chính sách cấm các thao tác rủi ro lên Production OU, tổ chức phải hỗ trợ all features và bật loại chính sách tương ứng.

## 5. Tổ chức tài khoản thành các OU

### OU dùng để làm gì?

OU giúp **nhóm những account cần chung một tập kiểm soát**. Khi gắn một chính sách hỗ trợ tính kế thừa vào OU, các account thuộc OU đó và các OU con sẽ nhận ảnh hưởng của chính sách theo quy tắc của từng loại policy.

Ví dụ, toàn bộ account thuộc `Workloads/Production` cần được bảo vệ trước thao tác tắt CloudTrail. Ta gắn một SCP hạn chế thao tác đó vào `Production`. Account `StorefrontProd` và `PaymentsProd` đều chịu giới hạn này. Account `StorefrontDev` thuộc `NonProduction` sẽ không nhận SCP riêng của `Production`.

### Account di chuyển giữa các OU thì sao?

Khi chuyển `StorefrontDev` từ `NonProduction` sang `Production`, các chính sách hiệu lực từ nhánh cũ sẽ được thay bằng tập chính sách kế thừa từ nhánh mới (và những chính sách gắn trực tiếp trên account vẫn cần xét theo loại policy). Chuyển OU **không tự chuyển** EC2, VPC, S3 bucket hay dữ liệu sang một account khác; account vẫn là account cũ.

Do chính sách mới có thể chặn thao tác vốn đang chạy bình thường, cần đánh giá ảnh hưởng với pipeline CI/CD, dịch vụ vận hành, IAM role và quyền truy cập trước khi di chuyển account, đặc biệt vào OU production.

### Quy tắc thiết kế cây OU

1. Đặt các guardrail cần áp dụng rộng ở cấp root, nhưng chỉ khi chắc chắn về phạm vi và loại policy.
2. Dùng OU để phản ánh **sự khác nhau về yêu cầu kiểm soát**: production và sandbox thường không có cùng chính sách.
3. Giữ cấu trúc dễ hiểu; tránh phân cấp sâu chỉ vì có nhiều phòng ban.
4. Tách account thu thập log và công cụ bảo mật khỏi account chạy workload quan trọng.
5. Đánh giá thay đổi chính sách trên một OU thử nghiệm trước khi mở rộng phạm vi.

## 6. Chính sách tổ chức và quyền thực tế

### 6.1. SCP là "giới hạn quyền tối đa", không phải quyền được cấp

**Service control policy (SCP)** đặt **giới hạn trên** cho quyền mà các IAM principal trong member account được sử dụng. SCP có thể gắn vào root, OU hoặc member account và được đánh giá theo toàn bộ đường đi từ root đến account.

Nếu một thao tác bị SCP **Deny** ở bất kỳ cấp nào trong đường đi, principal của member account không thực hiện được thao tác đó, ngay cả khi IAM gắn `AdministratorAccess`. Để một thao tác được SCP cho phép, thao tác ấy phải nằm trong phạm vi được `Allow` ở từng cấp; một lệnh `Deny` rõ ràng luôn thắng. AWS thường gắn SCP quản lý `FullAWSAccess` để không giới hạn quyền ngay khi kích hoạt SCP; việc gỡ nó mà không có chính sách Allow thay thế có thể khóa nhiều thao tác ngoài ý muốn.

**SCP không cấp quyền IAM.** Nếu IAM role không có quyền `s3:ListBucket` thì việc SCP không cấm hành động đó cũng không biến role thành người có quyền. Quyền thực tế còn chịu ảnh hưởng của các cơ chế khác như resource policy, permission boundary, session policy và điều kiện truy cập tương ứng.

| Tình huống | IAM cho phép? | SCP cho phép? | Kết quả về mặt IAM/SCP |
| --- | --- | --- | --- |
| Role có `s3:ListBucket`, không có SCP chặn. | Có | Có | Có thể được phép, nếu các kiểm soát liên quan khác cũng cho phép. |
| Role có `s3:DeleteBucket`, SCP của Production OU từ chối. | Có | Không | **Bị từ chối.** |
| Role không có `ec2:TerminateInstances`, SCP là `FullAWSAccess`. | Không | Có | **Bị từ chối** do IAM không cấp quyền. |

SCP **không áp dụng** cho IAM principal trong management account và không giới hạn service-linked role. Khi cần bảo vệ tài nguyên, không nên coi SCP là biện pháp duy nhất; còn phải cấu hình IAM, logging, resource policy và các kiểm soát dịch vụ phù hợp.

### 6.2. Ví dụ SCP bảo vệ thao tác ghi log

Giả sử `Production` có yêu cầu không cho principal trong các member account tự ý dừng ghi log hoặc xóa trail của AWS CloudTrail. Một SCP minh họa:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyStoppingOrDeletingCloudTrail",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail"
      ],
      "Resource": "*"
    }
  ]
}
```

Đây là **ví dụ để hiểu cơ chế**, chưa phải bộ chính sách CloudTrail hoàn chỉnh cho production. Các thao tác thay đổi cấu hình khác vẫn cần được xem xét, cũng như quy trình thay đổi và phục hồi trong tình huống khẩn cấp. Khi thử nghiệm chính sách `Deny` trên OU, phải duy trì những chính sách `Allow` cần thiết ở tất cả các cấp và kiểm tra tác động trong môi trường thử nghiệm.

### 6.3. Những loại policy khác

AWS Organizations còn hỗ trợ các loại chính sách khác tùy tính năng và loại policy đã bật, ví dụ:

- **Resource control policy (RCP):** giới hạn quyền truy cập vào tài nguyên thuộc member account đối với các dịch vụ/tài nguyên được hỗ trợ; có góc nhìn dựa trên tài nguyên, khác SCP thiên về principal.
- **Tag policy:** chuẩn hóa quy ước tag và có thể hỗ trợ thực thi quy tắc tag ở các trường hợp được AWS hỗ trợ.
- **Backup policy:** quản lý kế hoạch backup cho nhiều account qua tích hợp AWS Backup.
- **Một số chính sách cấu hình tập trung khác:** có cơ chế áp dụng và kế thừa riêng theo từng dịch vụ AWS.

**Không nên suy ra** mọi policy đều tác động giống SCP. Chẳng hạn, các declarative policy có quy tắc hợp nhất và phạm vi riêng; một số có thể ảnh hưởng cả management account, trong khi SCP thì không.

## 7. Thêm và quản lý member account

Có hai cách chính đưa account vào Organization:

| Cách | Thực hiện | Điểm cần chú ý |
| --- | --- | --- |
| **Create account** | Management account tạo một AWS account mới ngay trong Organization. | Account mới ban đầu được đặt dưới root; AWS Organizations thường tạo IAM role quản trị xuyên account với tên mặc định `OrganizationAccountAccessRole`, trừ khi chọn tên khác. |
| **Invite account** | Gửi lời mời tới một AWS account đã tồn tại; chủ account chấp nhận để tham gia. | Organizations **không tự tạo** `OrganizationAccountAccessRole` ở account được mời. Phải cấu hình truy cập quản trị xuyên account riêng nếu cần. |

Trong cả hai trường hợp, member account chịu chính sách phù hợp với vị trí trong cây khi gia nhập. Các account vẫn giữ ID, tài nguyên và thiết lập riêng. Với account được **tạo mới** qua Organizations, AWS có cơ chế quản lý quyền root tập trung; không nên giả định account mới có sẵn thông tin đăng nhập root để sử dụng hằng ngày.

Ví dụ quy trình thêm môi trường test:

1. Từ management account, tạo `StorefrontTest` bằng AWS Organizations, cung cấp tên account và địa chỉ email hợp lệ chưa được dùng cho AWS account khác.
2. Xác nhận account mới xuất hiện dưới root, sau đó chuyển vào `Workloads/NonProduction`.
3. Kiểm tra chính sách hiệu lực, IAM roles và cách nhân sự đăng nhập qua IAM Identity Center.
4. Bật các cấu hình cần thiết cho account mới: log, giám sát, phát hiện mối đe dọa, tagging và ngân sách.
5. Chỉ sau đó triển khai ứng dụng, ví dụ VPC, EC2/Lambda, S3 và RDS theo thiết kế của hệ thống.

Nếu tổ chức sử dụng **AWS Control Tower**, nên dùng quy trình cấp phát và đăng ký account/OU tương ứng của Control Tower để duy trì landing zone và các control liên quan. Organizations là nền tảng quản lý account; Control Tower hỗ trợ thiết lập, quản trị môi trường multi-account có cấu trúc.

## 8. Consolidated billing và kiểm soát chi phí

Consolidated billing cho phép management account xem và thanh toán chi phí các member account trong tổ chức. AWS có thể tính các ưu đãi về mức sử dụng và chia sẻ một số lợi ích giảm giá theo quy tắc của từng dịch vụ/chương trình. **Hợp nhất thanh toán không có nghĩa hợp nhất tài nguyên hoặc quyền truy cập.**

Ví dụ, `StorefrontProd` chạy EC2 và RDS, `StorefrontDev` sử dụng Lambda và S3. Chi phí của chúng vẫn có thể được xem và phân tích theo account, dù management account chịu trách nhiệm thanh toán tổng hợp.

Một phương án quản lý chi phí gồm:

- Tách workload production và non-production ở các account khác nhau để thấy nguồn phát sinh chi phí.
- Áp dụng quy tắc đặt tên và tag như `Environment`, `Team`, `CostCenter` cho tài nguyên phù hợp; kích hoạt cost allocation tags khi cần báo cáo.
- Dùng **AWS Cost Explorer**, **AWS Budgets** hoặc các công cụ báo cáo chi phí được cấp quyền để quan sát xu hướng, đặt cảnh báo và theo dõi ngân sách.
- Rà soát tài nguyên thử nghiệm còn chạy và quyền tạo các loại tài nguyên tốn kém ở Sandbox OU.

Chi phí và quyền truy cập của từng account nên được xem là hai bài toán liên quan nhưng khác nhau: **Billing** cho biết tiền đi đâu; **IAM và Organizations policies** quyết định ai được làm gì.

## 9. Thực hành đọc cây Organization bằng AWS CLI

Các lệnh dưới đây là minh họa, không tự thực thi. Cần cấu hình AWS CLI với danh tính có quyền Organizations phù hợp, thường sử dụng vai trò quản trị tại management account. Các ID chỉ là giá trị giả định.

**Bước 1 — Xem chế độ tính năng và root hiện có:**

```bash
aws organizations describe-organization
aws organizations list-roots
```

Từ kết quả, chú ý `FeatureSet` (`ALL` hoặc `CONSOLIDATED_BILLING`) và `Id` của root có dạng `r-...`.

**Bước 2 — Liệt kê OU và account:**

```bash
aws organizations list-organizational-units-for-parent --parent-id r-a1b2
aws organizations list-accounts --query 'Accounts[].{Name:Name,Id:Id,State:State}' --output table
```

Danh sách account có thể hiển thị trạng thái hoạt động và ID; hãy đối chiếu account đang ở OU nào bằng `list-parents`.

```bash
aws organizations list-parents --child-id 111122223333
```

**Bước 3 — Tạo OU hoặc di chuyển account (chỉ trên môi trường được phép):**

```bash
aws organizations create-organizational-unit \
  --parent-id r-a1b2 \
  --name NonProduction

aws organizations move-account \
  --account-id 111122223333 \
  --source-parent-id r-a1b2 \
  --destination-parent-id ou-a1b2-f6g7h111
```

Thay `r-a1b2`, `ou-a1b2-f6g7h111` và `111122223333` bằng ID thực tế; ví dụ giả định account ban đầu nằm trực tiếp dưới root. Trước khi chạy `move-account`, xác minh OU đích và các chính sách kế thừa. Account **không** được chuyển tự động sang OU vừa tạo; các lệnh trên minh họa hai hành động độc lập.

**Bước 4 — Xem SCP được gắn vào OU:**

```bash
aws organizations list-policies-for-target \
  --target-id ou-a1b2-f6g7h111 \
  --filter SERVICE_CONTROL_POLICY
```

Lệnh này trả về các SCP **gắn trực tiếp** vào OU đích; khi phân tích quyền phải kiểm tra thêm chính sách ở root, các OU cha và account, cùng chính sách IAM và những cơ chế quyền liên quan. Nếu tổ chức chưa bật loại policy tương ứng, lệnh có thể không mang lại kết quả như mong đợi.

## 10. Tình huống thiết kế và sai lầm thường gặp

**Tình huống:** nhóm vận hành muốn cho lập trình viên triển khai tự do ở dev, nhưng không được xóa trail ghi log tại production. Đồng thời bộ phận tài chính muốn xem chi phí tách biệt của dev và production.

Một thiết kế khả thi:

1. Dùng các account khác nhau cho `StorefrontDev` và `StorefrontProd`.
2. Đặt hai account vào `Workloads/NonProduction` và `Workloads/Production`.
3. Áp SCP hạn chế thao tác nhạy cảm vào Production OU sau khi thử nghiệm.
4. Cấp quyền IAM/Identity Center phù hợp: lập trình viên có quyền triển khai dev, còn production chỉ cấp quyền cần thiết cho quy trình phát hành.
5. Theo dõi chi phí theo account trong hệ thống thanh toán hợp nhất, bổ sung tag để phân tích sâu theo ứng dụng và nhóm.

**Sai lầm 1: "Đã gắn SCP Allow thì người dùng được phép gọi API."** Sai. SCP chỉ xác định phạm vi quyền tối đa, IAM vẫn phải cấp quyền tương ứng.

**Sai lầm 2: "Một OU giống một AWS account lớn hoặc một VPC."** Sai. OU là nhóm quản trị logic, không chứa tài nguyên dịch vụ theo cách account/VPC làm.

**Sai lầm 3: "Gắn SCP vào root là khóa được management account."** Sai. SCP không giới hạn IAM principal của management account; cần bảo vệ management account bằng cơ chế riêng.

**Sai lầm 4: "Mời account vào Organization là có quyền administrator xuyên account ngay."** Sai. Account được mời không tự có `OrganizationAccountAccessRole`; phải thiết lập truy cập nếu cần.

**Sai lầm 5: "Chuyển account sang OU khác chỉ là đổi nhãn."** Sai. Thao tác này có thể thay đổi chính sách hiệu lực và khiến một workload hoặc pipeline bị từ chối quyền.

## 11. Tự kiểm tra

**Câu 1.** Công ty muốn cấm xóa CloudTrail trong tất cả account production nhưng vẫn cho phép dev thử nghiệm. Nên gắn SCP ở đâu?

**Đáp án:** Ở Production OU (hoặc phạm vi tương ứng chỉ chứa các account cần kiểm soát), sau khi thử nghiệm. Không gắn bừa vào root nếu không có yêu cầu áp dụng toàn tổ chức.

**Câu 2.** IAM role trong member account được cấp `AdministratorAccess` nhưng thao tác `cloudtrail:DeleteTrail` bị SCP `Deny`. Thao tác có thành công không?

**Đáp án:** Không. SCP đặt giới hạn quyền tối đa cho principal trong member account.

**Câu 3.** Tổ chức muốn vừa gộp chi phí vừa dùng SCP, nên sử dụng feature set nào?

**Đáp án:** **All features**, vì consolidated billing-only không cung cấp khả năng quản lý SCP.

**Câu 4.** Account `StorefrontDev` đang ở NonProduction OU được chuyển sang Production OU. Có phải di chuyển dữ liệu S3 sang account khác không?

**Đáp án:** Không. Account và tài nguyên vẫn giữ nguyên; cần kiểm tra lại chính sách hiệu lực do vị trí trong cây thay đổi.

## Tài liệu AWS chính thức

- [AWS Organizations – Terminology and concepts](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_getting-started_concepts.html)
- [Managing organizational units (OUs)](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_ous.html)
- [Service control policies (SCPs)](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [SCP evaluation](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_evaluation.html)
- [Creating a member account](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_create.html)
- [Accessing member accounts](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_access.html)
- [Consolidated billing](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)

**Ghi nhớ:** AWS Organizations quản lý **cấu trúc và chính sách của nhiều account**; OU là nhóm để áp quản trị; member account là ranh giới chính chứa workload; IAM cấp quyền; SCP đặt giới hạn cho các quyền đó; consolidated billing giúp nhìn và thanh toán chi phí tập trung.
