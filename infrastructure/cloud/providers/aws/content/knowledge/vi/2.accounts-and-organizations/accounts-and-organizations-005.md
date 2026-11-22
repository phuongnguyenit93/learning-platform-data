# Service Control Policy và giới hạn quyền của tổ chức

## 1. Bối cảnh và mục tiêu học tập

Khi một doanh nghiệp chỉ có một tài khoản AWS, quản trị viên có thể quản lý phần lớn quyền truy cập thông qua AWS Identity and Access Management (IAM). Nhưng khi doanh nghiệp mở rộng thành nhiều tài khoản cho phát triển, kiểm thử, sản xuất, bảo mật và thanh toán, việc đặt cùng một quy tắc an toàn trong từng tài khoản dễ dẫn tới cấu hình thiếu nhất quán. **AWS Organizations** giải quyết bài toán quản trị tập trung đó; **Service Control Policy (SCP)** là một trong các công cụ quan trọng để thiết lập giới hạn quyền trên phạm vi tổ chức.

Bài này thuộc lộ trình **CLOUD_PROVIDERS_AWS**. Kiến thức về SCP kết nối trực tiếp với những chủ đề AWS như Region/Availability Zone, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, serverless, giám sát, phục hồi và kiểm soát chi phí. Khi lựa chọn hoặc triển khai dịch vụ, nhóm kỹ thuật cần hiểu không chỉ một vai trò IAM *được cấp* quyền gì, mà cả tổ chức *cho phép vai trò đó sử dụng tối đa* những quyền nào.

Sau bài học, bạn có thể:

- Giải thích SCP làm gì, khác IAM policy ở đâu và vì sao SCP không tự cấp quyền.
- Xác định phạm vi áp dụng của SCP trên Root, Organizational Unit (OU) và tài khoản thành viên.
- Phân tích kết quả của các quy tắc `Allow`/`Deny` khi nhiều SCP cùng tác động.
- Viết và đọc SCP dạng JSON để bảo vệ các hoạt động nhạy cảm hoặc giới hạn Region.
- Lập quy trình thử nghiệm, triển khai, giám sát và khôi phục khi một SCP chặn nhầm thao tác hợp lệ.

## 2. SCP là gì?

**Service Control Policy** là một loại *organization policy* trong AWS Organizations. SCP xác định **giới hạn tối đa của các quyền có thể sử dụng** bởi các principal chịu sự chi phối của SCP trong tài khoản thành viên. SCP được gắn với **Root của Organizations**, **OU** hoặc **tài khoản thành viên**, rồi tác động theo cấu trúc phân cấp.

Điểm cốt lõi: **một câu lệnh `Allow` trong SCP không cấp quyền thực hiện API**. Principal vẫn cần được cấp quyền thông qua cơ chế phân quyền AWS phù hợp, chẳng hạn IAM identity-based policy. Ngược lại, một `Deny` trong SCP có thể chặn thao tác mà IAM policy đã cho phép, kể cả khi principal có `AdministratorAccess` trong tài khoản thành viên.

Ví dụ: vai trò `DeploymentRole` có IAM policy cho phép `ec2:RunInstances`. Nếu SCP hiệu lực của tài khoản chứa vai trò đó từ chối `ec2:RunInstances`, vai trò vẫn không thể tạo EC2 instance. Việc gắn thêm một IAM policy `Allow ec2:*` không vượt qua được SCP.

### 2.1. SCP giải quyết bài toán nào?

| Nhu cầu quản trị | Vai trò có thể có của SCP | Cơ chế bổ sung cần xem xét |
| --- | --- | --- |
| Không cho tài khoản thành viên rời tổ chức | Chặn `organizations:LeaveOrganization` | Quy trình quản trị Organizations và quyền tại management account |
| Giảm nguy cơ ngừng ghi nhật ký CloudTrail | Chặn `cloudtrail:StopLogging`, `cloudtrail:DeleteTrail` | CloudTrail, cấu hình giám sát và bảo vệ nơi lưu log |
| Hạn chế nơi triển khai workload | Chặn thao tác của dịch vụ cụ thể ở Region không được phê duyệt | Chiến lược Region, dữ liệu, dịch vụ toàn cục, kiểm thử thực tế |
| Ngăn một nhóm tài khoản sử dụng dịch vụ không được duyệt | Thiết kế ranh giới `Deny` hoặc danh sách `Allow` | IAM, quy trình cấp ngoại lệ, kiểm soát chi phí |

SCP là **rào chắn quyền truy cập**, không phải công cụ thay thế giám sát vận hành, bảo vệ dữ liệu hay hạn mức chi tiêu tuyệt đối. Một lệnh tạo tài nguyên bị chặn không tự làm các tài nguyên đang chạy ngừng phát sinh chi phí; quản trị ngân sách còn cần AWS Budgets, cảnh báo và quy trình vận hành.

## 3. Phạm vi áp dụng: Root, OU và tài khoản

Giả sử tổ chức AWS được sắp xếp như sau:

```text
Organizations Root
├── OU: Security
│   └── Account: security-audit
└── OU: Workloads
    ├── OU: Development
    │   └── Account: dev-app
    └── OU: Production
        ├── Account: prod-app
        └── Account: prod-data
```

- SCP gắn với **Organizations Root** ảnh hưởng đến các tài khoản thành viên bên dưới cây tổ chức.
- SCP gắn với **OU Workloads** ảnh hưởng tới các tài khoản thuộc OU này và các OU con, nhưng không tác động tới tài khoản dưới OU Security.
- SCP gắn với **OU Production** ảnh hưởng đến `prod-app` và `prod-data`, không ảnh hưởng tới `dev-app`.
- SCP gắn trực tiếp vào **Account prod-app** chỉ tác động tới tài khoản đó.

Mỗi tài khoản thành viên chịu ảnh hưởng từ **toàn bộ chuỗi Root → các OU cha → tài khoản**. Chuyển một tài khoản sang OU khác có thể khiến tập giới hạn quyền của nó thay đổi ngay cả khi IAM policy trong tài khoản vẫn giữ nguyên.

> **Phân biệt hai loại “root”:** *Organizations Root* là nút cao nhất của cây quản trị Organizations. *Root user* là danh tính gốc của một tài khoản AWS. Đây là hai khái niệm khác nhau.

### 3.1. Những đối tượng SCP có và không có hiệu lực

SCP áp dụng lên các principal như IAM user, IAM role và **root user của tài khoản thành viên**. Giới hạn của SCP cũng có hiệu lực đối với vai trò IAM nằm trong tài khoản thành viên khi vai trò đó được giả định từ nơi khác.

Các ngoại lệ và giới hạn cần nhớ:

1. **SCP không giới hạn các principal trong management account** của Organizations. Vì vậy, phải bảo vệ management account bằng các biện pháp IAM và an ninh riêng; không thể dựa vào SCP để khóa quyền của chính tài khoản này.
2. **SCP không áp dụng lên service-linked role**. Đây là loại vai trò được một dịch vụ AWS tạo và quản lý cho mục đích tích hợp với dịch vụ đó.
3. SCP giới hạn **principal thuộc tài khoản thành viên**, không phải mọi truy cập vào mọi tài nguyên của tài khoản. Với truy cập xuyên tài khoản, cần đánh giá thêm resource-based policy, trust policy và vị trí của principal gọi API; SCP của tài khoản chứa tài nguyên không tự thay thế những kiểm soát này.
4. SCP không tự tạo hoặc sửa IAM user, IAM role, permission boundary hay chính sách tài nguyên. Các cơ chế đó tiếp tục có vai trò độc lập.

Muốn sử dụng SCP, AWS Organizations phải được bật chế độ **All features** và loại chính sách **Service control policies** phải được kích hoạt. Tài khoản quản lý tổ chức cần có quyền thực hiện các thao tác quản trị Organizations tương ứng.

## 4. AWS đánh giá quyền khi có SCP như thế nào?

Đối với một principal trong tài khoản thành viên, hãy hình dung SCP là **giới hạn bên ngoài** của các quyền mà principal có thể nhận. IAM policy và các chính sách liên quan quyết định thao tác nào được cấp; SCP đặt giới hạn cho những thao tác đó. **`Deny` tường minh có ưu tiên cao hơn `Allow`.** Các điều kiện như permission boundary, session policy và resource policy cũng có thể ảnh hưởng đến kết quả cuối cùng.

| Quyền từ IAM và các cơ chế liên quan | SCP hiệu lực | Kết quả minh họa |
| --- | --- | --- |
| Cho phép `ec2:RunInstances` | Cho phép và không có `Deny` liên quan | Có thể được phép, nếu các điều kiện khác cũng thỏa |
| Cho phép `ec2:RunInstances` | Có `Deny` cho `ec2:RunInstances` | **Bị từ chối** |
| Không có quyền cho `ec2:RunInstances` | Có `Allow` trong SCP | **Bị từ chối** vì SCP không cấp quyền |
| Principal có `AdministratorAccess` | SCP chặn `cloudtrail:StopLogging` | **Bị từ chối** đối với thao tác đó |

Đối với chính sách theo kiểu danh sách cho phép (*allow-list*), một hành động cần được cho phép **tại từng cấp trên đường đi** từ Organizations Root qua OU đến tài khoản. Chỉ một cấp thiếu `Allow` phù hợp cũng khiến hành động vượt khỏi giới hạn được cho phép, ngay cả khi IAM có `Allow`.

### 4.1. Hai mô hình phổ biến: deny-list và allow-list

**Mô hình deny-list** thường dễ triển khai khi mới áp dụng SCP:

- Giữ chính sách `FullAWSAccess` tại các nút cần thiết để phạm vi quyền mặc định không bị thu hẹp.
- Gắn thêm các SCP có những câu lệnh `Deny` cho các hành động bị cấm.
- Mỗi `Deny` tại Root, OU hoặc tài khoản đều có thể chặn hành động tương ứng ở các tài khoản chịu ảnh hưởng.

`FullAWSAccess` là SCP mặc định cho phép tất cả hành động *ở lớp SCP*. Nó **không** cấp quyền IAM và **không** vô hiệu hóa một `Deny` tường minh trong SCP khác.

**Mô hình allow-list** sử dụng SCP `Allow` có chọn lọc để thu hẹp tập API được sử dụng:

- Phải đảm bảo có `Allow` phù hợp **ở mọi cấp** Root → OU → tài khoản.
- Nếu giữ `FullAWSAccess` tại một cấp đang muốn thu hẹp bằng allow-list, chính sách đó có thể tiếp tục cho phép nhiều hành động tại cấp ấy; cần thiết kế lại các SCP gắn trực tiếp vào nút liên quan.
- Cần đánh giá các hành động phụ trợ mà ứng dụng hoặc dịch vụ thường gọi, chẳng hạn các lệnh `Describe*`, thao tác IAM hoặc thao tác ghi log. Allow-list quá hẹp có thể làm workload ngừng hoạt động.

Ví dụ mang tính khái niệm: Root chỉ cho phép `ec2:*`, OU chỉ cho phép `ec2:Describe*`, tài khoản cho phép `*`; khi không có những `Allow` khác, giới hạn chung ở lớp SCP chỉ còn các thao tác `ec2:Describe*`. Dù vậy, IAM policy vẫn phải cấp quyền cụ thể thì principal mới thực hiện được thao tác.

## 5. Ví dụ 1: Bảo vệ nhật ký và tư cách thành viên tổ chức

Một doanh nghiệp muốn các tài khoản ứng dụng không tự rời AWS Organizations, đồng thời không được ngừng ghi hoặc xóa trail của CloudTrail. Chính sách SCP dạng JSON sau thể hiện hai quy tắc ấy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyLeavingOrganization",
      "Effect": "Deny",
      "Action": "organizations:LeaveOrganization",
      "Resource": "*"
    },
    {
      "Sid": "DenyDisablingCloudTrail",
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

Giải thích từng phần:

- `Version` là phiên bản ngôn ngữ chính sách JSON của AWS; `2012-10-17` là giá trị thường dùng.
- `Statement` chứa một hoặc nhiều quy tắc. `Sid` giúp người vận hành nhận diện mục đích quy tắc.
- `Effect: Deny` thiết lập từ chối tường minh đối với các hành động trong `Action`.
- `Resource: "*"` thể hiện quy tắc áp dụng trên mọi tài nguyên phù hợp với hành động; một số API cấp tổ chức không có tài nguyên cụ thể để khai báo theo ARN.

Nếu chính sách này được gắn vào OU Workloads, nó ảnh hưởng tới các tài khoản `dev-app`, `prod-app`, `prod-data` trong sơ đồ, nhưng không ảnh hưởng tới `security-audit` ở OU khác. Một IAM administrator trong tài khoản sản xuất vẫn bị chặn hai loại thao tác trên.

**Giới hạn của ví dụ:** Chính sách chỉ ngăn các API được liệt kê. Nó chưa bao phủ mọi cách làm suy giảm khả năng giám sát, chẳng hạn thay đổi nơi nhận log, các cấu hình ghi log khác hoặc quyền truy cập vào bucket lưu log. Cần thiết kế quyền IAM, cấu hình CloudTrail và giám sát thay đổi song song.

## 6. Ví dụ 2: Giới hạn Region cho EC2

Giả sử doanh nghiệp phê duyệt workload EC2 tại Singapore (`ap-southeast-1`) và Sydney (`ap-southeast-2`). SCP sau chặn thao tác EC2 khi API được gửi đến Region khác:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEC2OutsideApprovedRegions",
      "Effect": "Deny",
      "Action": "ec2:*",
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": [
            "ap-southeast-1",
            "ap-southeast-2"
          ]
        }
      }
    }
  ]
}
```

`aws:RequestedRegion` kiểm tra Region của **điểm cuối API nhận yêu cầu**. Trong ví dụ, các hành động EC2 ở ngoài hai Region được chỉ định sẽ gặp `Deny`; trong hai Region được duyệt, SCP này không chặn, nhưng IAM và các giới hạn khác vẫn quyết định quyền thực tế.

**Không nên sao chép nguyên điều kiện Region rồi áp vào `Action: "*"` mà chưa đánh giá kỹ.** Nhiều dịch vụ có API toàn cục hoặc hành vi liên Region; một số thao tác gửi tới endpoint tại một Region nhưng tác động đến tài nguyên ở Region khác. Điều kiện `aws:RequestedRegion` không phải công cụ khẳng định tuyệt đối vị trí lưu trữ mọi dữ liệu. Khi thiết kế chính sách ở quy mô tổ chức, hãy xác định dịch vụ cần áp dụng, các ngoại lệ cần thiết và thử nghiệm ở tài khoản không trọng yếu.

## 7. Ví dụ phân tích quyền trong tổ chức nhiều OU

Xét các SCP sau và giả định `FullAWSAccess` vẫn gắn ở từng cấp:

| Vị trí gắn SCP | Quy tắc |
| --- | --- |
| Organizations Root | `Deny organizations:LeaveOrganization` |
| OU Workloads | `Deny cloudtrail:StopLogging` |
| OU Production | `Deny ec2:*` nếu Region không thuộc Singapore/Sydney |
| Account prod-app | Không có `Deny` bổ sung |

Một vai trò `AppAdmin` trong `prod-app` có IAM policy cho phép `ec2:*` và `cloudtrail:*` sẽ có kết quả:

| Yêu cầu | Kết quả | Giải thích |
| --- | --- | --- |
| Tạo EC2 instance tại `ap-southeast-1` | Có thể được phép | Không bị SCP trên chặn; vẫn phải đủ quyền và điều kiện khác |
| Tạo EC2 instance tại `eu-west-1` | Bị từ chối | SCP kế thừa từ OU Production |
| Gọi `cloudtrail:StopLogging` | Bị từ chối | SCP kế thừa từ OU Workloads |
| Gọi `organizations:LeaveOrganization` | Bị từ chối | SCP kế thừa từ Organizations Root |

Nếu chuyển tài khoản `prod-app` từ OU Production sang OU Development, quy tắc hạn chế Region gắn riêng với OU Production sẽ không còn áp dụng thông qua nhánh OU cũ. Hai quy tắc trên Root và Workloads vẫn có hiệu lực vì tài khoản vẫn thuộc nhánh đó. Đây là lý do thao tác **move account** cần được xem như thay đổi kiểm soát bảo mật.

## 8. Quy trình triển khai SCP an toàn

### Bước 1 — Xác định hành động và phạm vi

Chuyển yêu cầu kinh doanh thành danh sách API cụ thể. Ví dụ, “không cho tắt CloudTrail” nên được phân rã thành các hành động liên quan, rồi kiểm tra những đường thay đổi cấu hình khác có thể ảnh hưởng tới mục tiêu. Chọn vị trí áp dụng: Root nếu toàn bộ tài khoản thành viên cần ràng buộc; OU nếu chỉ một nhóm; hoặc tài khoản nếu đang thử nghiệm.

Kiểm tra Organizations đang ở chế độ **All features** và SCP đã được kích hoạt. Ghi nhận các SCP đang gắn tại Root, OU và account, nhất là `FullAWSAccess` và các quy tắc `Deny` hiện hữu.

### Bước 2 — Soạn chính sách và rà soát tác động

Đánh giá chính sách dưới góc nhìn của người dùng console, ứng dụng, pipeline CI/CD, vai trò vận hành và tự động hóa. Một hành động cấp cao thường kéo theo nhiều API phụ trợ. Sử dụng bảng đối chiếu hành động cần dùng với các `Deny` hoặc `Allow` đang áp dụng trước khi gắn chính sách.

Đặc biệt xem xét các dịch vụ liên quan đến Region, hoạt động liên tài khoản, service-linked role và các yêu cầu khôi phục sự cố. Cần có đường quản trị an toàn từ management account để điều chỉnh hoặc tháo SCP khi chính sách chặn nhầm.

### Bước 3 — Thử nghiệm trên OU hoặc tài khoản không trọng yếu

Trong AWS Management Console, có thể vào **AWS Organizations → Policies → Service control policies**, tạo policy rồi gắn vào đối tượng phù hợp. Nếu loại chính sách chưa được bật, cần thực hiện bước kích hoạt trước.

Với AWS CLI, ví dụ lưu JSON của mục 5 vào `scp-guardrails.json` rồi tạo chính sách:

```bash
aws organizations create-policy --name GuardrailsBase --description "Protect CloudTrail and organization membership" --type SERVICE_CONTROL_POLICY --content file://scp-guardrails.json
```

Lệnh trả về một `PolicyId` thật. Sau khi xác minh đúng ID và OU thử nghiệm, có thể gắn chính sách:

```bash
aws organizations attach-policy --policy-id p-EXAMPLE --target-id ou-EXAMPLE-EXAMPLE
aws organizations list-policies-for-target --target-id ou-EXAMPLE-EXAMPLE --filter SERVICE_CONTROL_POLICY
```

`p-EXAMPLE` và `ou-EXAMPLE-EXAMPLE` chỉ là chỗ giữ chỗ để minh họa, phải thay bằng ID thực tế. `list-policies-for-target` liệt kê chính sách **gắn trực tiếp** vào target; để kiểm tra SCP kế thừa, cần lần theo các OU cha và Organizations Root.

Ở môi trường thử nghiệm, hãy thực hiện cả thao tác **dự kiến được phép** lẫn thao tác **dự kiến bị từ chối** bằng các vai trò thực tế. Kiểm tra thông báo lỗi `AccessDenied`, CloudTrail và đường đi của vai trò CI/CD. Khi có kết quả phù hợp, mới mở rộng sang OU sản xuất theo quy trình thay đổi của tổ chức.

### Bước 4 — Theo dõi, vận hành và khôi phục

Theo dõi các thay đổi quản trị như `CreatePolicy`, `UpdatePolicy`, `AttachPolicy`, `DetachPolicy` qua CloudTrail và quy trình rà soát cấu hình. Lưu phiên bản JSON, lý do thay đổi, người phê duyệt và kế hoạch hoàn tác.

Nếu phát hiện SCP chặn nhầm một tác vụ quan trọng, người có thẩm quyền ở management account có thể sửa hoặc tháo chính sách tại target thích hợp. Hãy kiểm tra toàn bộ đường Root → OU → tài khoản trước khi sửa: lỗi có thể đến từ SCP kế thừa ở cấp cao hơn, không nằm ở tài khoản đang phát sinh lỗi.

## 9. Những nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Gắn SCP `Allow s3:*` là đã cấp quyền S3 cho nhân viên.” | SCP chỉ cho phép quyền đó nằm trong giới hạn tối đa; principal vẫn cần quyền IAM hoặc cơ chế cấp quyền phù hợp. |
| “AdministratorAccess hoặc root user của tài khoản thành viên vượt được SCP.” | `Deny` trong SCP vẫn có hiệu lực với những principal này. Ngoại lệ quan trọng gồm principal trong management account và service-linked role. |
| “Có FullAWSAccess thì mọi lệnh đều được chạy.” | FullAWSAccess không tự cấp IAM permission và không thắng được `Deny` tường minh. |
| “SCP chỉ áp dụng nếu được gắn trực tiếp lên account.” | Tài khoản còn kế thừa các SCP từ OU cha và Organizations Root. |
| “Chặn tạo EC2 ở Region khác đồng nghĩa toàn bộ dữ liệu luôn ở Region được duyệt.” | `aws:RequestedRegion` kiểm soát endpoint của yêu cầu; cần đánh giá hành vi dịch vụ, dữ liệu, các luồng liên Region. |
| “SCP là công cụ đặt giới hạn tiền AWS.” | SCP giới hạn các thao tác API; chi phí đã phát sinh và tài nguyên đang chạy cần các công cụ quản lý chi phí khác. |
| “SCP ở Organizations Root sẽ khóa cả management account.” | SCP không giới hạn principal trong management account; phải bảo vệ tài khoản này độc lập. |

## 10. Tình huống áp dụng và tự kiểm tra

**Tình huống A — Pipeline sản xuất gặp AccessDenied.** Pipeline sử dụng role `DeployProd` có IAM `AdministratorAccess`, nhưng lệnh tạo EC2 tại `eu-west-1` thất bại. Tài khoản thuộc OU Production với SCP mục 6. Nguyên nhân hợp lý nhất là `DenyEC2OutsideApprovedRegions`, vì IAM `Allow` không vượt qua giới hạn từ OU. Hướng xử lý là kiểm tra Region dự kiến của workload và xin điều chỉnh guardrail theo quy trình, thay vì thêm IAM `Allow`.

**Tình huống B — Kỹ sư được xem thông tin S3 nhưng không tải được đối tượng.** SCP cho phép hành động liên quan đến S3 và không có `Deny` phù hợp. Điều này **chưa chứng minh** kỹ sư được phép `s3:GetObject`: cần kiểm tra IAM policy, bucket policy, quyền KMS (nếu đối tượng được mã hóa), điều kiện truy cập và các giới hạn khác.

**Tình huống C — Nhóm Security đề xuất gắn SCP chặn mọi thao tác ngoài một Region.** Trước khi áp dụng trên toàn Root, nhóm cần liệt kê các dịch vụ có endpoint toàn cục, hành động liên Region, dịch vụ hạ tầng quan trọng và phương án khôi phục. Một chính sách Region quá rộng có thể làm gián đoạn IAM, hệ thống triển khai hoặc công cụ giám sát ngoài dự kiến. Thử nghiệm từ phạm vi nhỏ và giới hạn hành động theo từng dịch vụ là cách tiếp cận an toàn hơn.

## 11. Ghi nhớ

SCP giúp AWS Organizations áp đặt các **ranh giới quyền tập trung** trên tài khoản thành viên. Quyền thực hiện một API chỉ có thể tồn tại khi cơ chế cấp quyền thích hợp cho phép **và** các SCP hiệu lực không loại bỏ quyền đó. Để thiết kế hạ tầng AWS an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí, hãy kết hợp SCP với IAM, phân chia tài khoản/OU hợp lý, CloudTrail, bảo vệ tài nguyên, thử nghiệm triển khai và quản trị thay đổi.

### Tài liệu AWS tham khảo

- [Service control policies — AWS Organizations User Guide](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [Service control policy examples — AWS Organizations User Guide](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_examples.html)
- [Policy evaluation logic — IAM User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
