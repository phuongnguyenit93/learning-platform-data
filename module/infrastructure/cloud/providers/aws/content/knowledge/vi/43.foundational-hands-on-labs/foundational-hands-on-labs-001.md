# Thiết lập sandbox an toàn với SSO và cảnh báo ngân sách

## Mục tiêu học tập

Sau bài thực hành này, bạn có thể:

- Giải thích vì sao sandbox nên nằm trong một AWS member account riêng.
- Phân biệt AWS Organizations, AWS Control Tower và IAM Identity Center trong quy trình cấp tài khoản và đăng nhập.
- Chọn đúng organization instance của IAM Identity Center để cấp quyền truy cập AWS accounts.
- Tạo group, user và bật MFA cho người học.
- Tạo permission set theo least privilege và gán quyền vào đúng sandbox account.
- Đăng nhập AWS Management Console và AWS CLI bằng SSO, không tạo access key dài hạn.
- Bật quyền IAM truy cập Billing console theo quy trình bootstrap an toàn.
- Tạo monthly cost budget với cảnh báo actual và forecasted spend.
- Kiểm tra email/SNS subscribers và hiểu độ trễ của dữ liệu chi phí.
- Phân biệt budget alert với cơ chế giới hạn chi tiêu thực tế.
- Thu hồi quyền lab và giữ lại các guardrails cần thiết sau khi hoàn tất.

## 1. Kết quả cần đạt

Cuối lab, kiến trúc có một AWS account dành riêng cho thực hành, một nhóm người dùng đăng nhập qua IAM Identity Center, một permission set giới hạn quyền, và một cost budget gửi cảnh báo tới người phụ trách.

~~~mermaid
flowchart TD
    IDP["Identity Center directory / external IdP"] --> SSO["IAM Identity Center organization instance"]
    SSO --> G["Group: Sandbox-Learners"]
    G --> PS["Permission set: Sandbox-ViewOnly"]
    PS --> A["Sandbox member account"]
    ROOT["Account root: bootstrap only + MFA"] --> BILL["Enable IAM access to Billing"]
    BILL --> B["Monthly AWS Budget"]
    B --> N["Email / SNS notifications"]
    A --> W["Lab resources in allowed Regions"]
    W --> COST["Cost and usage data"]
    COST --> B
~~~

Tài khoản sandbox là ranh giới cô lập quan trọng nhất. SSO cung cấp danh tính và phiên đăng nhập tạm thời; permission set xác định quyền trong account; budget cảnh báo khi chi phí tiến gần ngưỡng đã đặt.

## 2. Mô hình an toàn và phạm vi lab

Một AWS account có thể tạo ra chi phí và chứa tài nguyên độc lập với tài khoản đăng nhập. Vì vậy, không dùng management account của AWS Organizations làm nơi chạy thử workload nếu đã có thể tạo member account riêng.

Mô hình khuyến nghị:

- **Management account:** quản lý AWS Organization, IAM Identity Center và chính sách cấp tài khoản.
- **Sandbox OU:** chứa member account dành cho học tập, thử nghiệm và tài nguyên có thể xóa.
- **Sandbox member account:** nơi người học triển khai lab.
- **IAM Identity Center:** cấp quyền theo user/group và permission set.
- **AWS Budgets:** theo dõi chi phí của sandbox account và gửi cảnh báo.

Lab này chỉ cấu hình identity, quyền và ngân sách. Các ví dụ không tạo EC2, RDS hoặc tài nguyên workload có chi phí. Khi dùng account thật, hãy xem xét giá dịch vụ, Region và thời gian tồn tại trước khi tạo tài nguyên.

Không coi một sandbox account là môi trường miễn phí. Một số dịch vụ tính phí theo thời gian, dung lượng, request, data transfer hoặc tài nguyên đã cấp dù không có traffic.

## 3. Điều kiện cần chuẩn bị

Trước khi bắt đầu, cần có:

- Một AWS account do bạn hoặc tổ chức quản lý hợp pháp.
- Quyền quản trị AWS Organizations management account nếu phải tạo member account hoặc bật organization instance.
- Quyền quản trị IAM Identity Center để tạo group, permission set và account assignment.
- Một email có thể nhận và xác nhận thông báo ngân sách.
- Một thiết bị MFA như security key hoặc authenticator app.
- AWS CLI phiên bản 2 nếu muốn kiểm tra SSO từ terminal.
- Region dự kiến dùng cho IAM Identity Center và Region triển khai workload.

Nếu đây là tài khoản do công ty cấp, hãy xin một sandbox member account và nhóm SSO từ cloud/platform administrator. Không tự tạo AWS Organization hoặc thay đổi identity source của tổ chức nếu chưa được giao quyền.

## 4. Chọn cách tạo sandbox account

### 4.1 Tổ chức đã dùng AWS Control Tower

Dùng AWS Control Tower Account Factory để tạo member account trong OU dành cho sandbox. Account Factory áp dụng baseline và controls theo landing zone đã cấu hình.

Quy trình tổng quát:

1. Đăng nhập AWS Control Tower bằng identity được cấp quyền provisioning.
2. Mở phần Organizations hoặc Account Factory.
3. Chọn Create account.
4. Đặt tên rõ ràng, ví dụ aws-sandbox-learning.
5. Dùng email chưa gắn với một AWS account khác cho root identity của account mới.
6. Chọn Sandbox OU đã đăng ký trong Control Tower.
7. Kiểm tra account owner/SSO access configuration.
8. Tạo account và đợi provisioning hoàn tất.
9. Xác nhận account xuất hiện trong đúng OU.

Không tạo member account trực tiếp qua AWS Organizations để bỏ qua Account Factory nếu landing zone của tổ chức yêu cầu Control Tower baseline. Account được tạo ngoài Account Factory có thể chưa được enroll hoặc chưa có controls mong muốn.

### 4.2 Tổ chức dùng AWS Organizations nhưng chưa có Control Tower

Đăng nhập management account bằng một role quản trị được phê duyệt, mở AWS Organizations, chọn AWS accounts và tạo member account. Dùng email duy nhất chưa được gắn với AWS account khác. Sau khi tạo xong, chuyển account vào Sandbox OU và áp dụng Service Control Policies (SCPs) hoặc guardrails do tổ chức quản lý.

AWS Organizations member account là account riêng về identity và billing, nhưng billing có thể được hợp nhất ở management account. Tài nguyên workload của sandbox nên được tạo trong member account.

SCP đặt giới hạn tối đa cho những quyền có thể dùng trong member accounts; SCP không tự cấp quyền cho user hoặc role. Người dùng vẫn cần permission set/IAM policy cho phép hành động.

### 4.3 Bạn chỉ có một standalone AWS account

Có thể bật IAM Identity Center bằng organization instance. Khi thực hiện từ standalone account, AWS sẽ tạo AWS Organization và account hiện tại trở thành management account của organization đó. Sau đó có thể tạo một member account riêng để làm sandbox.

Một account instance của IAM Identity Center không hỗ trợ permission sets và không cấp quyền đăng nhập vào AWS accounts. Account instance chỉ phục vụ các ứng dụng được hỗ trợ trong chính account đó. Nếu mục tiêu là SSO vào AWS account, hãy dùng organization instance.

Nếu chưa có quyền hoặc chưa sẵn sàng quản lý AWS Organization, dùng sandbox account do giảng viên hoặc tổ chức cấp. Không biến account production thành management account chỉ để hoàn thành một bài lab.

## 5. Bảo vệ root user và hoàn tất bootstrap

Root user có toàn quyền trên account. Chỉ dùng root cho các tác vụ bootstrap hoặc account-level settings thực sự yêu cầu root.

Thực hiện các bước sau cho account mới:

1. Đặt mật khẩu root mạnh, duy nhất và lưu trong password manager.
2. Đăng ký MFA cho root, ưu tiên security key hoặc authenticator mạnh.
3. Không tạo root access keys.
4. Không dùng root để chạy AWS CLI, tạo workload hoặc đăng nhập hằng ngày.
5. Cập nhật billing, security và operations alternate contacts bằng email nhóm phù hợp.
6. Xác nhận thông tin thanh toán và account owner.
7. Đăng xuất root sau khi hoàn thành tác vụ bootstrap.

Root email nên được kiểm soát bởi account owner hoặc quy trình quản trị công ty. Không dùng email cá nhân của một nhân viên làm địa chỉ duy nhất có thể khôi phục account doanh nghiệp.

## 6. Bật IAM Identity Center organization instance

Organization instance là loại IAM Identity Center hỗ trợ multi-account permissions và permission sets. AWS khuyến nghị dùng organization instance cho quản lý workforce access tập trung.

Các bước:

1. Đăng nhập AWS Organizations management account bằng role quản trị.
2. Chọn Region sẽ lưu trữ và quản lý IAM Identity Center.
3. Mở IAM Identity Center console.
4. Nếu chưa có instance, chọn Enable.
5. Chọn enable với AWS Organizations để tạo organization instance.
6. Xác nhận Region và cấu hình instance.
7. Đợi instance chuyển sang trạng thái enabled.

Chọn Region cẩn thận. IAM Identity Center organization instance có primary Region; không thể đổi primary Region sau khi tạo. Tài nguyên workload trong sandbox vẫn có thể chạy ở các Region khác nếu policy cho phép. Multi-Region replication là cấu hình bổ sung, không bắt buộc cho lab một Region.

Nếu tổ chức đã có IAM Identity Center organization instance, không tạo instance thứ hai. Hãy dùng instance hiện có và xin administrator cấp group/permission set.

## 7. Chọn identity source

IAM Identity Center có thể dùng directory tích hợp, Active Directory hoặc external identity provider.

| Identity source | Khi phù hợp | Việc cần chuẩn bị |
|---|---|---|
| Identity Center directory | Lab cá nhân hoặc nhóm nhỏ | Tạo user/group trong Identity Center |
| External IdP như Entra ID/Okta | Tổ chức đã quản lý workforce identity tập trung | SAML federation, SCIM provisioning và MFA ở IdP |
| Active Directory | Tổ chức dùng Microsoft AD | Directory connectivity, group mapping và MFA strategy |

Đối với lab cá nhân, Identity Center directory là cách đơn giản nhất. Với doanh nghiệp, giữ identity lifecycle trong IdP trung tâm; không tạo user rời rạc ở nhiều hệ thống nếu đã có nguồn danh tính chuẩn.

Khi dùng external IdP, cấu hình MFA nằm ở IdP. IAM Identity Center MFA settings không thay thế policy MFA của external IdP.

## 8. Cấu hình MFA cho AWS access portal

MFA giúp giảm rủi ro khi mật khẩu bị lộ. Với Identity Center directory, mở IAM Identity Center, vào Settings, tab Authentication, phần Multi-factor authentication và chọn Configure.

Đối với môi trường học tập hoặc production có yêu cầu bảo mật cao:

- Chọn yêu cầu người dùng đăng ký MFA trước khi truy cập.
- Chọn Prompt users for MFA là Every time they sign in nếu chính sách yêu cầu xác thực ở mỗi lần đăng nhập.
- Cho phép security keys hoặc authenticator apps theo policy.
- Khuyến khích người dùng đăng ký phương thức dự phòng.
- Kiểm tra quy trình khôi phục khi mất thiết bị MFA.

Context-aware MFA có thể giảm số lần prompt khi thiết bị và ngữ cảnh đăng nhập đáng tin cậy, nhưng có mức bảo vệ khác với always-on. Không chọn Never/disabled cho workforce portal nếu không có lý do bảo mật được phê duyệt.

## 9. Tạo group và user cho sandbox

Mở IAM Identity Center:

1. Chọn Users và tạo user dành cho người học, ví dụ learner01.
2. Dùng email thật mà người học kiểm soát để nhận thông báo và khôi phục.
3. Chọn Groups và tạo group Sandbox-Learners.
4. Thêm user learner01 vào group.
5. Nếu dùng external IdP, tạo group ở IdP và đồng bộ bằng SCIM theo cấu hình tổ chức.
6. Xác nhận user và group xuất hiện trong Identity Center.

Nên gán quyền cho group thay vì gán trực tiếp cho từng user. Khi một người rời nhóm học, chỉ cần loại họ khỏi group hoặc thu hồi assignment theo quy trình.

Không tạo một user dùng chung cho cả lớp. Mỗi người cần danh tính riêng để audit, MFA và thu hồi quyền chính xác.

## 10. Tạo permission set theo least privilege

Permission set là template chứa IAM policies mà Identity Center provision thành IAM role trong AWS account được gán. Khi permission set thay đổi, Identity Center cập nhật role tương ứng trong account.

Tạo permission set:

1. Vào IAM Identity Center, Multi-account permissions, Permission sets.
2. Chọn Create permission set.
3. Chọn Custom permission set nếu cần inline policy hoặc predefined permission set nếu dùng AWS managed policy.
4. Đặt tên, ví dụ Sandbox-ViewOnly.
5. Chọn session duration một giờ cho lab ngắn.
6. Review permissions và tạo permission set.

Để kiểm tra SSO an toàn, có thể dùng AWS managed policy ViewOnlyAccess trên sandbox account. Policy này cho phép xem nhiều tài nguyên; không gán nó vào production account nếu không cần.

Nếu lab sau này cần tạo tài nguyên, tạo một permission set riêng với policy giới hạn theo dịch vụ, bucket, Region và resource ARN. Không nâng Sandbox-Learners lên AdministratorAccess chỉ để tránh lỗi AccessDenied.

### 10.1 Ví dụ policy giới hạn một S3 lab bucket

Ví dụ dưới đây cho phép khám phá account và đọc/ghi object trong một bucket đã được administrator tạo sẵn. Thay tên bucket bằng bucket lab thực tế. Policy không cho phép tạo bucket hoặc truy cập object ở bucket khác.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DiscoverLabEnvironment",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeRegions",
        "ec2:DescribeAvailabilityZones",
        "s3:ListAllMyBuckets",
        "cloudwatch:ListMetrics",
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ListOnlyLabBucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::aws-lab-example-123456"
    },
    {
      "Sid": "ManageOnlyLabObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::aws-lab-example-123456/*"
    }
  ]
}
~~~

Đây là policy mẫu cho một bài lab S3, không phải policy chung cho mọi AWS service. Nếu bucket dùng SSE-KMS, cần bổ sung quyền KMS được scope đúng key và key policy phải cho phép role. Nếu cần multipart upload hoặc object tagging, cần thêm actions tương ứng theo use case.

Không thêm iam:CreateRole, iam:AttachRolePolicy, iam:PutRolePolicy hoặc iam:PassRole một cách rộng rãi vào permission set dành cho người học. Quyền tạo hoặc chuyển IAM role có thể mở đường nâng quyền nếu không giới hạn chặt.

## 11. Gán group vào sandbox account

Trong IAM Identity Center, mở Multi-account permissions, AWS accounts:

1. Chọn đúng sandbox member account.
2. Chọn Assign users or groups.
3. Chọn group Sandbox-Learners.
4. Chọn permission set Sandbox-ViewOnly.
5. Review account ID, group và permission set.
6. Chọn Submit.
7. Đợi provisioning hoàn tất.

Một user có thể được gán nhiều permission sets. Với một tài khoản học tập, hãy gán quyền cần dùng cho sandbox account duy nhất. Không gán group người học vào management account.

Khi cần quyền billing riêng, dùng group/permission set dành cho cost administrators. Người học chỉ cần xem tài nguyên không nhất thiết phải được phép sửa budgets hoặc payment settings.

## 12. Đăng nhập AWS access portal

Mở user portal URL được hiển thị trong IAM Identity Center Settings. Người học thực hiện:

1. Đăng nhập bằng username và password của identity source.
2. Hoàn thành MFA.
3. Tìm sandbox account trong danh sách AWS accounts.
4. Chọn account và permission set được gán.
5. Chọn Management console để mở AWS Console.
6. Kiểm tra account ID ở menu account phía trên bên phải.

Nếu portal hiển thị nhiều accounts, chọn đúng account có nhãn sandbox. Không suy luận account chỉ từ display name; so sánh 12-digit account ID với thông tin administrator cung cấp.

## 13. Cấu hình AWS CLI bằng SSO

Dùng AWS CLI version 2. Không chạy aws configure với access key/secret key cho lab này.

Chạy:

~~~bash
aws configure sso --profile aws-sandbox
~~~

CLI sẽ hỏi:

- SSO session name, ví dụ company-sso.
- SSO start URL, lấy từ IAM Identity Center.
- SSO Region, là Region của IAM Identity Center.
- SSO registration scopes, thường dùng sso:account:access.
- Account và permission set muốn dùng.
- Default CLI Region cho workload, ví dụ ap-southeast-1.
- Output format, ví dụ json.

Đăng nhập:

~~~bash
aws sso login --profile aws-sandbox
~~~

Kiểm tra danh tính:

~~~bash
aws sts get-caller-identity --profile aws-sandbox
~~~

Kết quả phải có Account là sandbox account ID và ARN chứa role được provision từ permission set. Nếu account ID là management account hoặc account production, dừng lại và sửa profile trước khi chạy lệnh tạo tài nguyên.

Đăng xuất khi kết thúc:

~~~bash
aws sso logout --profile aws-sandbox
~~~

Ví dụ cấu hình trong file config của AWS CLI sau khi chạy configure:

~~~ini
[sso-session company-sso]
sso_start_url = https://d-1234567890.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access

[profile aws-sandbox]
sso_session = company-sso
sso_account_id = 111122223333
sso_role_name = Sandbox-ViewOnly
region = ap-southeast-1
output = json
~~~

Thay start URL, account ID và role name bằng giá trị thực. Không commit file config chứa account metadata nội bộ nếu repository không được phép lưu. File config không chứa access key; CLI cache temporary credentials sau khi SSO login.

## 14. Kiểm tra quyền sau khi đăng nhập

Chạy:

~~~bash
aws sts get-caller-identity --profile aws-sandbox
aws ec2 describe-regions --profile aws-sandbox --region ap-southeast-1
aws s3 list-buckets --profile aws-sandbox --region ap-southeast-1
~~~

Với permission set ViewOnlyAccess, các lệnh đọc phù hợp sẽ thành công. Thử một thao tác ghi như tạo bucket chỉ trong lab được cấp phép; nếu permission set không cho phép thì AccessDenied là kết quả mong muốn.

Kiểm tra thêm:

- Account ID đúng sandbox account.
- Role name đúng permission set.
- Session duration theo cấu hình.
- MFA đã được yêu cầu.
- Không có access key dài hạn trong environment.
- Không dùng root profile hoặc IAM user profile.

Nếu một API trả AccessDenied, kiểm tra permission set, account assignment, SCP, resource policy và Region. Không giải quyết bằng cách gán AdministratorAccess ngay lập tức.

## 15. Cho phép SSO role truy cập Billing console

Mặc định IAM users và roles không được truy cập Billing and Cost Management console chỉ nhờ một IAM policy. Account root user phải bật tùy chọn IAM user and role access to Billing information.

Thực hiện riêng trong account nơi budget được quản lý:

1. Mở Billing and Cost Management, vào Account settings.
2. Tìm IAM user and role access to Billing information.
3. Kiểm tra Activate IAM access. Nếu setting đang tắt, account root user phải bật và lưu thay đổi.
4. Với member accounts mới được tạo trong AWS Organizations, setting này thường đã được bật mặc định; vẫn kiểm tra trước khi điều tra lỗi quyền.
5. Nếu cần thay đổi setting, dùng root chỉ cho tác vụ account-level này rồi đăng xuất.
6. Đăng nhập lại bằng SSO role có permissions phù hợp.

Setting này chỉ kiểm soát IAM access tới các trang Billing console; nó không tự cấp quyền đọc hoặc sửa budgets. Role vẫn cần IAM policies tương ứng. Setting này không kiểm soát quyền gọi Billing and Cost Management SDK APIs như AWS Budgets API.

Nếu tổ chức tạo budget tập trung ở management account, root/admin phải bật IAM billing access trong management account và SSO role phải được cấp quyền ở account đó. Member account không tự động nhìn thấy budget được tạo ở management account.

## 16. Tạo permission set riêng cho người quản lý ngân sách

Không nên gán quyền quản lý budgets cho toàn bộ người học. Tạo group riêng như Sandbox-Cost-Admins và permission set Sandbox-Budget-Manager.

AWS Budgets sử dụng các IAM actions như:

- budgets:ViewBudget để đọc budget và thông tin liên quan.
- budgets:ModifyBudget để tạo, sửa, xóa budget và cấu hình notification/subscriber.
- budgets:CreateBudgetAction hoặc các action quản lý budget action nếu tổ chức chủ động dùng budget actions.

Đối với lab chỉ tạo notification, chỉ cấp quyền xem và sửa budget theo yêu cầu. Không cấp budget-action execution permissions nếu chưa có quy trình phê duyệt và kiểm thử. Khi tạo budget qua console, AWS cũng yêu cầu quyền xem billing information, tạo CloudWatch alarms và tạo SNS notifications; quyền chính xác phụ thuộc vào cách gửi alert và policy của tổ chức. Với automation qua Budgets API, dùng role riêng và IAM actions được scope theo nhu cầu.

Assign permission set này cho nhóm cost administrators trong account nơi budget được quản lý. Người học có thể chỉ được gán Sandbox-ViewOnly.

## 17. Tạo monthly cost budget

Mở Billing and Cost Management, chọn Budgets, sau đó Create budget.

Cấu hình minh họa:

| Trường | Giá trị ví dụ |
|---|---|
| Budget name | sandbox-monthly-cost |
| Budget type | Cost budget |
| Period | Monthly |
| Budget amount | 25 USD |
| Cost metric | Unblended cost hoặc metric theo chính sách FinOps |
| Account scope | Sandbox account |
| Region/service filter | Chỉ thêm nếu cần theo dõi một phần chi phí |

25 USD chỉ là con số minh họa để thực hành cấu hình. Chọn ngân sách thực tế theo workload, Region, support plan, data transfer, storage và thời gian giữ tài nguyên. Không có một con số budget chung bảo đảm account không phát sinh chi phí vượt ngưỡng.

Nếu tạo budget trong member account, budget mặc định theo dõi chi phí của account đó. Nếu tạo budget từ management account và muốn theo dõi một member account, dùng Linked account filter để giới hạn đúng account ID.

## 18. Cấu hình alert thresholds

Với lab đầu tiên, tạo một actual threshold và một forecasted threshold:

| Loại | Threshold | Ý nghĩa |
|---|---:|---|
| Actual | 50% | Cảnh báo sớm khi chi phí đã phát sinh |
| Forecasted | 80% | Cảnh báo khi dự báo cuối kỳ có thể vượt 80% |

Với budget 25 USD, ngưỡng 80% tương đương 20 USD. Có thể dùng absolute value hoặc percentage of budget.

Khi đã hiểu cách notification hoạt động, có thể thêm các ngưỡng khác theo quy trình FinOps của tổ chức. Mỗi budget có giới hạn số notifications; kiểm tra quota và hành vi alert của từng threshold trước khi nhân rộng.

Actual alert được gửi khi chi phí thực tế chạm ngưỡng. Forecasted alert dựa trên dự báo chi phí cuối kỳ; dự báo có thể thay đổi theo dữ liệu usage.

Không cấu hình budget action tự động dừng EC2/RDS hoặc gắn SCP trong bài lab cơ bản. Chỉ dùng notifications để học cách theo dõi và xác nhận cảnh báo.

## 19. Gửi alert qua email hoặc SNS

Trong Notification preferences:

- Thêm email của account owner hoặc nhóm FinOps.
- Có thể thêm tối đa 10 email recipients cho mỗi notification.
- Người nhận phải xác minh email trước khi nhận budget alerts.
- Nếu dùng SNS topic, nhập đúng topic ARN và xác nhận SNS subscription qua email.
- Có thể dùng SNS để route cảnh báo tới Lambda, SQS hoặc hệ thống thông báo đã được tổ chức phê duyệt.

Sau khi tạo budget, kiểm tra trạng thái subscriber. Nếu dùng SNS, mở email subscription confirmation và chọn Confirm subscription. Một topic chưa được xác nhận có thể khiến cảnh báo không tới được người nhận.

## 20. Hiểu độ trễ của AWS Budgets

AWS Budgets không phải hệ thống đo chi phí real-time.

- Dữ liệu Budgets được cập nhật tối đa ba lần mỗi ngày; thường cách lần cập nhật trước khoảng 8–12 giờ.
- Có độ trễ giữa lúc tài nguyên phát sinh usage và lúc usage được ghi nhận trong billing data.
- Actual alerts chỉ được gửi một lần cho mỗi budget trong một budget period khi ngưỡng actual được chạm lần đầu.
- Forecasted alert có thể gửi nhiều lần nếu dự báo vượt ngưỡng, giảm xuống rồi lại vượt ngưỡng.
- AWS cần khoảng năm tuần usage history để tạo forecast; forecast alert có thể chưa hoạt động trong giai đoạn đầu account mới.

Vì vậy, một account có thể phát sinh chi phí vượt threshold trước khi email cảnh báo được gửi. Chi phí thực tế cũng có thể tiếp tục tăng sau khi alert đến. Không dùng budget notification làm cơ chế chặn chi tiêu tuyệt đối.

## 21. Kiểm tra budget và notification

Sau khi tạo budget:

1. Mở Budgets và chọn sandbox-monthly-cost.
2. Kiểm tra budget amount, period và cost metric.
3. Kiểm tra account/service/Region filters.
4. Kiểm tra actual và forecasted thresholds.
5. Kiểm tra danh sách email subscribers.
6. Kiểm tra SNS subscription status nếu dùng SNS.
7. Kiểm tra budget được tạo trong đúng account.
8. Ghi lại owner, ngày review và email nhận cảnh báo.

Có thể dùng AWS CLI để xem danh sách budgets:

~~~bash
aws budgets describe-budgets \
  --account-id 111122223333 \
  --region us-east-1 \
  --profile aws-sandbox
~~~

AWS Budgets API endpoint là global service endpoint; lệnh CLI vẫn yêu cầu Region cho cấu hình client. Dùng đúng account ID của account sở hữu budget. Nếu CLI role không có quyền budgets:ViewBudget, lệnh sẽ trả AccessDenied.

## 22. Budget action và spend control

AWS Budgets hỗ trợ budget actions trong một số tình huống. Một action có thể áp dụng IAM policy, gắn Service Control Policy từ management account hoặc nhắm tới EC2/RDS resources. Action có thể yêu cầu approval hoặc tự chạy tùy cấu hình.

Budget action là một biện pháp phản ứng có tác động vận hành. Ví dụ, policy deny có thể làm pipeline dừng, SCP có thể chặn thao tác quản trị, và stop EC2/RDS có thể làm gián đoạn ứng dụng. Chỉ triển khai khi:

- Có owner chịu trách nhiệm.
- Có kiểm thử trên sandbox.
- Có action role với quyền tối thiểu.
- Có quy trình approve/rollback.
- Có thông báo cho người dùng bị ảnh hưởng.

Budget alert vẫn không phải hard spending cap. Nếu cần giới hạn chi phí cho một project mới có tính năng spend limit riêng, hãy đánh giá đúng loại account/project và điều kiện hỗ trợ của AWS; không nhầm nó với cost budget notification thông thường.

## 23. Tổ chức tags và cost visibility

Để phân tích chi phí theo lab hoặc nhóm, thống nhất tag keys trước khi tạo workload:

| Tag key | Ví dụ | Mục đích |
|---|---|---|
| Project | aws-learning | Nhóm chi phí theo project |
| Environment | sandbox | Phân biệt môi trường |
| Owner | learner-team | Tìm người chịu trách nhiệm |
| CostCenter | training | Phân bổ chi phí nội bộ |
| ExpiryDate | 2026-12-01 | Nhắc cleanup |

Cost allocation tags cần được kích hoạt trong Billing console trước khi xuất hiện trong các báo cáo phân bổ chi phí tương ứng. Không phải mọi service đều áp dụng tags theo cùng cách. Tags không tự động chặn chi phí hoặc tự xóa resource hết hạn.

Đối với sandbox, đặt tên tài nguyên có prefix nhất quán và ghi expiry date. Dùng AWS Config, automation hoặc inventory reports để tìm tài nguyên quên cleanup nếu tổ chức đã triển khai.

## 24. Case study: nhóm học AWS dùng sandbox account

Một nhóm 12 người cần thực hành S3, Lambda và CloudWatch trong hai tuần. Tổ chức có AWS Organizations và Control Tower.

### Thiết kế

1. Platform team tạo account aws-training-sandbox bằng Account Factory trong Sandbox OU.
2. Control Tower baseline và SCP của tổ chức được áp dụng.
3. IAM Identity Center group Sandbox-Learners chứa 12 người học.
4. Permission set Sandbox-ViewOnly cấp quyền quan sát.
5. Permission set Sandbox-Builder riêng giới hạn vào bucket, Lambda functions và log groups được chỉ định.
6. Group Sandbox-Cost-Admins có quyền quản lý budgets.
7. Budget sandbox-monthly-cost đặt mức 25 USD với actual 50% và forecast 80%.
8. Email alerts gửi đến shared mailbox của nhóm và người phụ trách FinOps.

### Cách vận hành

- Người học đăng nhập bằng SSO và MFA.
- Mọi CLI commands dùng profile aws-sandbox.
- Platform team kiểm tra account ID trước mỗi workshop.
- Budget alerts được gửi đến shared mailbox.
- Cuối buổi, người học xóa lab resources; platform team rà soát leftovers.
- Budget được giữ lại để tiếp tục cảnh báo trong thời gian account còn hoạt động.

### Kết quả mong đợi

Mỗi người có danh tính riêng, quyền được quản lý tập trung, workload nằm trong account tách biệt và chi phí được giám sát theo một ngưỡng chung. Nếu có người rời nhóm, administrator thu hồi group membership hoặc assignment mà không phải xoay vòng access keys.

## 25. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy AWS accounts trong portal | Dùng account instance hoặc chưa có account assignment | Kiểm tra organization instance và group/permission set assignment |
| Không tạo được permission set | IAM Identity Center account instance không hỗ trợ permission sets | Dùng organization instance |
| User đăng nhập được nhưng không thấy sandbox | Chưa gán group vào account hoặc provisioning chưa hoàn tất | Kiểm tra AWS accounts assignments |
| AccessDenied khi mở service | Permission set, SCP hoặc resource policy chặn | Xác định explicit deny và xin quyền tối thiểu cần thiết |
| CLI báo thiếu SSO profile | AWS CLI chưa cấu hình hoặc version cũ | Dùng AWS CLI v2 và chạy aws configure sso |
| CLI trả sai account ID | Chọn nhầm account/profile | Kiểm tra aws sts get-caller-identity |
| MFA không xuất hiện | MFA do external IdP quản lý hoặc setting không áp dụng | Kiểm tra identity source và MFA policy ở đúng nơi |
| SSO role không mở được Billing console | IAM Billing access chưa bật trong account | Root bật Activate IAM access; kiểm tra policy của role |
| Không tạo được budget | Thiếu budgets:ModifyBudget hoặc billing permissions | Kiểm tra permission set và Billing console access |
| Không xem được budget | Thiếu budgets:ViewBudget hoặc đang ở sai account | Kiểm tra permission set và account ID |
| Budget alert không gửi email | Email chưa verified hoặc sai subscriber address | Xác minh email và xem lại notification |
| SNS không nhận alert | SNS subscription chưa confirm hoặc topic ARN sai | Xác nhận subscription và kiểm tra topic policy |
| Forecast alert chưa hoạt động | Account chưa có đủ lịch sử usage | Chờ khoảng năm tuần dữ liệu hoặc dùng actual alert |
| Chi phí vượt ngưỡng trước alert | Billing data và Budgets có độ trễ | Kiểm tra Cost Explorer/Bills; budget không phải real-time cap |
| Budget hiển thị không đúng chi phí sandbox | Budget được tạo ở management account nhưng thiếu linked account filter | Thêm đúng Linked account filter |
| User vẫn vào được sau khi bị xóa group | Session hoặc assignment chưa hết hiệu lực | Revoke assignment, kết thúc active session và kiểm tra group sync |
| Member account không có Control Tower controls | Account được tạo ngoài Account Factory hoặc chưa enroll | Làm theo quy trình enrollment/baseline của Control Tower |

## 26. Cleanup sau lab

Giữ lại những guardrails cần thiết:

- Giữ monthly cost budget và notifications trong thời gian account còn dùng.
- Giữ MFA và root account protections.
- Giữ group và permission set nếu lớp học còn tiếp tục.
- Xóa tài nguyên workload được tạo trong các lab khác theo checklist riêng.
- Thu hồi permission set assignment của user không còn tham gia.
- Xóa user thử nghiệm chỉ khi không còn phụ thuộc hoặc lịch sử cần giữ.
- Xác nhận SSO CLI logout và không còn access keys tạm tạo trong môi trường.
- Rà soát Budgets subscribers khi email owner thay đổi.

Không xóa IAM Identity Center organization instance hoặc đóng AWS account chỉ để cleanup một lab ngắn. Nếu cần đóng sandbox account, phải theo quy trình account closure của tổ chức và xác nhận không còn tài nguyên, invoice hoặc workload phụ thuộc.

## 27. Bài tập tự luyện

1. Vì sao sandbox workload nên nằm trong member account riêng?
2. Management account của AWS Organizations dùng để làm gì?
3. AWS Control Tower Account Factory giúp gì khi tạo sandbox account?
4. Organization instance và account instance của IAM Identity Center khác nhau thế nào?
5. Loại IAM Identity Center nào hỗ trợ permission sets và AWS account access?
6. Vì sao phải chọn Region IAM Identity Center cẩn thận?
7. Identity Center MFA có áp dụng thay cho external IdP MFA không?
8. Vì sao mỗi người học cần user riêng?
9. Permission set là gì?
10. Vì sao nên gán group vào account thay vì gán user thủ công?
11. ViewOnlyAccess phù hợp với giai đoạn nào?
12. Vì sao không nên cấp AdministratorAccess cho cả lớp?
13. AWS CLI SSO dùng lệnh nào để cấu hình profile?
14. Lệnh nào xác nhận account ID và principal hiện tại?
15. Vì sao root user không nên dùng hằng ngày?
16. Tùy chọn Activate IAM access có tự cấp quyền Billing không?
17. Cost budget và budget action khác nhau thế nào?
18. Vì sao budget alert không phải hard spending cap?
19. AWS Budgets cập nhật dữ liệu thường xuyên đến mức nào?
20. Forecast alert cần khoảng bao nhiêu tuần usage history?
21. Actual alert và forecast alert khác nhau thế nào?
22. Email subscriber cần làm gì trước khi nhận notification?
23. Vì sao cần Linked account filter khi tạo budget ở management account?
24. Tags có tự động ngăn tài nguyên phát sinh chi phí không?
25. Khi nào nên dùng budget action?

### Gợi ý đáp án

1. Account riêng tạo ranh giới về quyền, chi phí, resource và cleanup.
2. Quản lý organization, member accounts, OUs và policies.
3. Provision member account theo baseline và controls của landing zone.
4. Organization instance hỗ trợ quản lý multi-account và permission sets; account instance chỉ hỗ trợ một số ứng dụng trong một account.
5. Organization instance.
6. Primary Region của organization instance không thể đổi sau khi tạo.
7. Không. External IdP tự quản lý MFA cho danh tính của nó.
8. Để audit, MFA, thu hồi và phân quyền theo cá nhân.
9. Template các IAM policies được provision thành role trong account được gán.
10. Quản lý lifecycle và access assignment nhất quán.
11. Khi người học chỉ cần quan sát và xác minh SSO.
12. Quyền rộng làm tăng blast radius và nguy cơ tạo tài nguyên tốn phí.
13. aws configure sso.
14. aws sts get-caller-identity.
15. Root có toàn quyền và khó giới hạn; chỉ dùng cho tác vụ account-level đặc biệt.
16. Không. Nó chỉ cho phép IAM identities truy cập Billing console khi policy cũng cho phép.
17. Budget action có thể thực hiện biện pháp phản ứng; budget alert chỉ gửi thông báo.
18. Billing data và notifications có độ trễ; tài nguyên vẫn có thể phát sinh chi phí.
19. Tối đa ba lần mỗi ngày, thường cách nhau khoảng 8–12 giờ.
20. Khoảng năm tuần.
21. Actual dựa trên chi phí đã ghi nhận; forecast dựa trên dự báo cuối kỳ.
22. Xác minh email hoặc confirm SNS subscription.
23. Để budget chỉ tính chi phí của đúng member account.
24. Không. Tags phục vụ phân loại và phân bổ chi phí.
25. Khi đã có owner, policy, approval, rollback và đã kiểm thử tác động.

## 28. Câu hỏi phỏng vấn

### Vì sao AWS khuyến nghị organization instance của IAM Identity Center?

Vì nó hỗ trợ đầy đủ multi-account permissions, permission sets, centralized identity management và application assignments trong AWS Organization. Account instance chỉ phù hợp cho một số ứng dụng được hỗ trợ trong một account.

### Permission set có phải IAM role không?

Không trực tiếp. Permission set là template trong IAM Identity Center. Khi gán vào AWS account, Identity Center provision IAM role được quản lý trong account đó và attach policies tương ứng.

### MFA có thay thế least privilege không?

Không. MFA bảo vệ xác thực người dùng; permission set và IAM policies kiểm soát hành động người dùng được phép thực hiện sau khi đăng nhập.

### Vì sao không nên dùng PowerUserAccess cho mọi người học?

PowerUserAccess rất rộng trên nhiều AWS services. Nếu gán nhầm account hoặc người học có thể tạo tài nguyên lớn, chi phí và blast radius tăng. Hãy dùng permission set chuyên biệt và resource scope.

### AWS Budgets có thể dừng toàn bộ chi tiêu khi đạt 100% không?

Không theo cơ chế cost budget alert thông thường. Budget action có thể thực hiện một số hành động IAM/SCP/EC2/RDS theo cấu hình, nhưng có độ trễ và có thể gây gián đoạn. Không coi nó là hard cap toàn account.

### Vì sao actual và forecasted alerts cần được cấu hình riêng?

Actual alerts phát khi chi phí đã ghi nhận đạt threshold; forecasted alerts cảnh báo sớm theo dự báo. Forecast cần lịch sử usage và có thể thay đổi nhiều lần trong kỳ.

### Khi nào cần bật IAM Billing access?

Khi muốn IAM roles/users truy cập Billing and Cost Management console. Setting phải được root bật trong account tương ứng; IAM policy vẫn cần cấp actions cụ thể.

### Vì sao phải xác minh account ID trước khi chạy CLI commands?

Một profile SSO có thể được cấu hình cho nhiều account/permission sets. Account ID giúp ngăn lệnh tạo hoặc xóa tài nguyên chạy nhầm vào management/production account.

## 29. Checklist production

### Account isolation

- [ ] Sandbox là member account riêng hoặc account học tập đã được tổ chức phê duyệt.
- [ ] Management account không chứa workload thực hành.
- [ ] Sandbox OU có guardrails/SCPs phù hợp.
- [ ] Nếu dùng Control Tower, account được provision/enroll theo Account Factory.
- [ ] Alternate contacts và payment details đã được cập nhật.

### Root và SSO

- [ ] Root user có MFA mạnh.
- [ ] Root không có access keys.
- [ ] Organization instance được bật trong đúng Region.
- [ ] Identity source và MFA policy được xác nhận.
- [ ] Mỗi người dùng có danh tính riêng.
- [ ] Group và permission sets theo least privilege.
- [ ] Session duration hợp lý.
- [ ] User portal và CLI login đã được kiểm thử.

### Permissions

- [ ] Permission set chỉ được gán vào đúng sandbox account.
- [ ] Không cấp AdministratorAccess cho group người học.
- [ ] Resource-specific policies dùng ARN và Region đúng.
- [ ] IAM PassRole/CreateRole không được cấp rộng.
- [ ] Cost management permissions tách khỏi developer permissions.
- [ ] SCP và resource policies đã được xem xét.

### Budget và alerts

- [ ] Monthly cost budget có owner.
- [ ] Budget amount phù hợp workload và currency.
- [ ] Actual thresholds được cấu hình.
- [ ] Forecast threshold được cấu hình nếu đủ lịch sử.
- [ ] Email recipients đã verify.
- [ ] SNS subscriptions đã confirm.
- [ ] Account/Region/service filters đúng.
- [ ] Owner hiểu độ trễ và không coi budget alert là hard cap.
- [ ] Budget actions chỉ bật sau review, approval và rollback test.

### Operations

- [ ] Có quy trình kiểm tra cost hàng ngày hoặc theo lịch.
- [ ] Có quy trình cleanup tài nguyên lab.
- [ ] Có owner cho SSO group và permission sets.
- [ ] Có quy trình thu hồi assignment khi người dùng rời nhóm.
- [ ] Có runbook cho AccessDenied, MFA recovery và budget alert.
- [ ] Có lịch review budget amount và subscribers.

## 30. Tài liệu tham khảo chính thức

### AWS account và isolation

- [AWS Organizations: Create a member account](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_create.html)
- [AWS Control Tower: Account Factory](https://docs.aws.amazon.com/controltower/latest/userguide/account-factory.html)
- [Provision accounts in AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/methods-of-provisioning.html)
- [AWS account root user best practices](https://docs.aws.amazon.com/accounts/latest/reference/root-user.html)
- [Update alternate contacts for an AWS account](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-update-contact-alternate.html)

### IAM Identity Center và SSO

- [Organization and account instances of IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-instances.html)
- [Organization instances of IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/organization-instances-identity-center.html)
- [Enable IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html)
- [Manage AWS accounts with permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetsconcept.html)
- [Create and manage permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsets.html)
- [Assign user or group access to AWS accounts](https://docs.aws.amazon.com/singlesignon/latest/userguide/assignusers.html)
- [Configure MFA in IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/mfa-configure.html)
- [Prompt users for MFA](https://docs.aws.amazon.com/singlesignon/latest/userguide/mfa-getting-started.html)
- [Configure user access with the default Identity Center directory](https://docs.aws.amazon.com/singlesignon/latest/userguide/quick-start-default-idc.html)
- [Configure AWS CLI to use IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)

### Billing và AWS Budgets

- [Manage access permissions for Billing and Cost Management](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/control-access-billing.html)
- [Create a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html)
- [Best practices for AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)
- [Managing costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [Configure a budget action](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-action-configure.html)
- [AWS Budgets IAM actions and resource types](https://docs.aws.amazon.com/service-authorization/latest/reference/list_budgets.html)
- [CreateBudget API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_budgets_CreateBudget.html)


